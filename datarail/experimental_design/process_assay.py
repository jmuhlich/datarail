import pandas as pd
import numpy as np
from collections import OrderedDict
from itertools import groupby
import datarail.experimental_design.edge_fingerprint as edge_fingerprint
import warnings


def read_input(file, plate_dims, fingerprint_prefix,
               encode_plate=False, num_replicates=1):
    """ Function takes tsv file provided by user and constructs
    dicts for all treatments, also provides error warning if well allotments
    are incorrect

    Parameters
    ----------
    tsv_file: tsv_file

    plate_dims: list

    fingerprint_prefix: str

    encode_plate: boolean

    num_replicates: int

    Returns
    -------
    drug_treatments: dict

    nc_treatments: dict

    pc_treatments: dict

    fprt_treatments: dict
    """

    if file.endswith('.csv'):
        df = pd.read_csv(file)
    elif file.endswith('.tsv'):
        df = pd.read_table(file)
    drugs = df.Compound_Name[df.Role == 'treatment'].tolist()
    positive_controls = df.Compound_Name[df.Role ==
                                         'positive_control'].tolist()
    negative_controls = df.Compound_Name[df.Role ==
                                         'negative_control'].tolist()
    fingerprint_treatments = df.Compound_Name[
        df.Role == 'fingerprint'].tolist()

    drug_treatments = OrderedDict()
    for drug in drugs:
        max_dose = df['Highest_Dose'].ix[
            df['Compound_Name'] == drug].values[0]
        num_doses = df['num_wells'].ix[
            df['Compound_Name'] == drug].values[0]
        max_dose_value, _ = split_text(max_dose)
        conc = float(max_dose_value) * 1e-4 * np.logspace(0, 4, num_doses)
        drug_treatments[drug] = {'doses': conc, 'role': 'treatment'}

    nwells_total = plate_dims[0] * plate_dims[1]
    num_dr_treatments = sum(len(v['doses']) for v
                            in drug_treatments.itervalues())
    num_edge_wells = get_boundary_cell_count(plate_dims)
    inner_wells_available = nwells_total - num_dr_treatments - num_edge_wells

    nc_treatments = OrderedDict()
    for nc in negative_controls:
        max_dose = df['Highest_Dose'].ix[
            df['Compound_Name'] == nc].values[0]
        num_wells = df['num_wells'].ix[
            df['Compound_Name'] == nc].values[0]
        try:
            max_dose_value, _ = split_text(max_dose)
        except ValueError:
            max_dose_value = 0
        except TypeError:
            max_dose_value = 0
        nc_treatments[nc] = {'doses': [max_dose] * num_wells,
                             'role': 'negative_control'}
    num_nc_treatments = sum(len(v['doses']) for v
                            in nc_treatments.itervalues())
    total_control_wells = num_nc_treatments

    if num_nc_treatments < 8:
        print ""
        warnings.warn(
            'Insufficent number of wells alloted for negative controls')
        print "Atleast 8 wells have to be assigned for negative controls,"\
            " recommended number is 12, user has currently alloted %d wells"\
            " for negative_controls" % num_nc_treatments

    pc_treatments = OrderedDict()
    try:
        for pc in positive_controls:
            max_dose = df['Highest_Dose'].ix[
                df['Compound_Name'] == pc].values[0]
            num_wells = df['num_wells'].ix[
                df['Compound_Name'] == pc].values[0]
            max_dose_value, _ = split_text(max_dose)
            # pc_name = 'pc_' + pc
            pc_treatments[pc] = {'doses': [float(max_dose_value)] * num_wells,
                                 'role': 'positive_control'}
        num_pc_treatments = sum(len(v['doses']) for v
                                in pc_treatments.itervalues())
        total_control_wells += num_pc_treatments
    except NameError:
        pass

    if total_control_wells > inner_wells_available:
        print ""
        warnings.warn(
            'Number of wells alloted for controls exceeds available wells')
        print "%d wells are available for controls, user has alloted %d wells"\
            " for negative controls and %d for positive controls" % (
                inner_wells_available, num_nc_treatments, num_pc_treatments)
    elif total_control_wells < inner_wells_available:
        print ""
        warnings.warn(
            'Plate will have untreated inner wells')
        print 'There are %d untreated wells on the inner plate.'\
            ' Consider alloting more wells to negative controls' % (
                inner_wells_available - total_control_wells)

    total_treatments = num_dr_treatments + total_control_wells
    total_inner_wells = nwells_total - num_edge_wells
    error_msg = "total number of treatments for drugs and controls (%d) "\
                "exceed number of inner wells (%d)" % (
                    total_treatments, total_inner_wells)
    assert total_treatments <= total_inner_wells, error_msg

    fprt_treatments = OrderedDict()
    if encode_plate:
        try:
            for fprt in fingerprint_treatments:
                max_dose = df['Highest_Dose'].ix[
                    df['Compound_Name'] == fprt].values[0]
                num_wells = df['num_wells'].ix[
                    df['Compound_Name'] == fprt].values[0]
                max_dose_value, _ = split_text(max_dose)
                # fprt_name = 'fprt_' + fprt
                fprt_treatments[fprt] = {'doses': [float(max_dose_value)] * num_wells,
                                     'role': 'Fingerprint'}
            num_fprt_treatments = sum(len(v['doses']) for v
                                    in fprt_treatments.itervalues())

            fingerprints = [fingerprint_prefix + chr(65+i)
                        for i in range(num_replicates)]
            num_fprt_wells = [len(edge_fingerprint.encode_fingerprint(fprt))
                            for fprt in fingerprints]
            max_fprt_wells = max(num_fprt_wells)
            if num_fprt_treatments < max_fprt_wells:
                warnings.warn(
                    'Insufficent number of wells alloted for encodng fingerprint')
                print "fingerprint requires %d wells, user has alloted %d wells"\
                    % (max_fprt_wells, num_fprt_treatments)
        except NameError:
            print ""
            warnings.warn('treatments for fingerprint not specified')

    return drug_treatments, nc_treatments, pc_treatments, fprt_treatments


def make_treatment_dataframe(treatments_dict,
                             plate_dims, combo_pairs=[], combo_doses=[]):
    """ Function that returns a long table Dataframe for
    drug treatments with n_columns  = len(drugs) and n_rows = n_wells

    Parameters
    ----------
    drug_treatment_dict: dict
             dictionary of drugs & negative_controls(nc) as keys
             and the corresponding doses as values
    args:
       default parameters for plate_dims, stock_concentration
    combo_pairs: list of tuples
              list of drug combinations to be used in the experiment
    combo_doses: dict
             dictionary of drugs as keys and the corresponding doses used in
             combination treatment

    Returns
    -------
    treatment_df: pandas dataframe
             long table dataframe where columns are drugs/nc and rows are wells
    """
    drug_treatment_dict = treatments_dict[0]
    nc_treatments_dict = treatments_dict[1]
    pc_treatments_dict = treatments_dict[2]
    n_wells = np.dot(plate_dims[0], plate_dims[1])
    d1 = drug_treatment_dict.copy()
    d1.update(nc_treatments_dict)
    if pc_treatments_dict:
        d1.update(pc_treatments_dict)
    total_treatments = len(d1.keys())
    all_treatments = np.zeros([total_treatments, n_wells])
    count = 0
    tr_numwells = {comp: i for i, comp in enumerate(d1.keys())}
    role = []
    for tr in d1.keys():
        n_treatments = len(d1[tr]['doses'])
        all_treatments[tr_numwells[tr],
                       count:count+n_treatments] = d1[tr]['doses']
        count += n_treatments
        role += [d1[tr]['role']] * n_treatments
    for pair in combo_pairs:
        n_treatments = len(combo_doses[pair[1]])
        for i in range(len(combo_doses[pair[0]])):
            all_treatments[tr_numwells[pair[0]],
                           count:count+n_treatments] = combo_doses[pair[0]][i]
            all_treatments[tr_numwells[pair[1]],
                           count:count+n_treatments] = combo_doses[pair[1]]
            count += n_treatments
    tr_df = pd.DataFrame(all_treatments.T,
                         columns=d1.keys())
    tr_df = tr_df.loc[(tr_df != 0).any(axis=1)]
    tr_df.loc[:, 'Role'] = role
    return tr_df


def split_text(s):
    for k, g in groupby(s, str.isalpha):
        yield ''.join(list(g))


def get_boundary_cell_count(plate_dims, exclude_outer=1):
    """ get number of wells in outer or inner edges

    Parameter
    ---------
    plate_dims: array
         dimensions of plate

    Returns
    -------
    boundary_cell_count: int
           number of wells in the edges
    """
    boundary_cell_count = 2 * (plate_dims[0] + plate_dims[1] - 2)
    if exclude_outer == 2:
        boundary_cell_count += 2 * (plate_dims[0]-2 + plate_dims[1]-2 - 2)
    return boundary_cell_count


def set_dosing(num_doses, max_dose, num_replicates=1):
    dose_range = max_dose * 1e-4 * np.logspace(0, 4, num_doses)
    dose_range = sorted(list(set(dose_range)) * num_replicates)
    return dose_range


def exclude_treatment(df, drug, doses):
    df2 = df.copy()
    df2 = df2[~((df2.agent == drug) & (df2.concentration.isin(doses)))]
    return df2


def construct_well_level_df(spec_file, plate_dims=[16, 24],
                            barcode=None, exclude_outer=1):
    df_spec = pd.read_csv(spec_file)
    drugs, doses, role = [], [], []
    df_tr = df_spec[df_spec.Role == 'treatment'].copy()
    for drug in df_tr.Compound.tolist():
        max_dose = df_tr[df_tr.Compound == drug]['Max_dose_(uM)'].values[0]
        num_doses = df_tr[df_tr.Compound == drug]['Num_doses'].values[0]
        num_replicates = df_tr[df_tr.Compound == drug][
            'num_replicates'].values[0]
        dose_range = set_dosing(9, max_dose, num_replicates)
        doses += dose_range
        drugs += [drug] * len(dose_range)
        role += ['treatment'] * len(dose_range)
    if 'positive_control' in df_spec.Role.unique():
        dfp = df_spec[df_spec.Role == 'positive_control'].copy()
        for drug in dfp.Compound.tolist():
            max_dose = dfp[dfp.Compound == drug]['Max_dose_(uM)'].values[0]
            num_replicates = dfp[dfp.Compound == drug][
                'num_replicates'].values[0]
            doses += [max_dose] * num_replicates
            drugs += [drug] * num_replicates
            role += ['positive_control'] * num_replicates
    else:
        warnings.warn(
            'Experimental design does not have positive_controls')
    num_outer_wells = get_boundary_cell_count(plate_dims, exclude_outer)
    num_available_wells = (plate_dims[0] * plate_dims[1]) - num_outer_wells
    num_treatment_wells = len(doses)
    if num_available_wells < num_treatment_wells:
        warnings.warn('Number of treatment wells required (%d)'
                      'exceed available wells (%d)' % (
                         num_treatment_wells, num_available_wells))
    df_well = pd.DataFrame(zip(drugs, doses, role),
                           columns=['agent', 'concentration', 'role'])
    return df_well


def add_dmso_control(df, plate_dims=[16, 24], exclude_outer=1):
    num_treatment_wells = len(df)
    num_outer_wells = get_boundary_cell_count(plate_dims, exclude_outer)
    num_available_wells = (plate_dims[0] * plate_dims[1]) - num_outer_wells 
    num_nc_wells = num_available_wells - num_treatment_wells
    if num_nc_wells < 8:
        print ""
        warnings.warn(
            'Insufficent number of wells alloted for negative controls')
        print "Atleast 8 wells have to be assigned for negative controls,"\
            " recommended number is 12, user has currently alloted %d wells"\
            " for negative_controls" % num_nc_wells
    role = df.role.tolist()
    doses = df.concentration.tolist()
    drugs = df.agent.tolist()
    role += ['negative_control'] * num_nc_wells
    doses += [np.nan] * num_nc_wells
    drugs += ['DMSO'] * num_nc_wells
    df_well = pd.DataFrame(zip(drugs, doses, role),
                           columns=['agent', 'concentration', 'role'])
    return df_well



def assign_fingerprint_wells(fingerprint, treatment, dose):
    fingerprint_wells = edge_fingerprint.encode_fingerprint(fingerprint)
    treatment_list = [treatment] * len(fingerprint_wells)
    dose_list = [dose] * len(fingerprint_wells)
    role = ['fingerprint'] * len(fingerprint_wells)
    df = pd.DataFrame(zip(fingerprint_wells, treatment_list, dose_list, role),
                      columns=['well', 'agent', 'concentration', 'role'])
    return df


def define_treatment_wells(exclude_outer=1):
    cols = ["%02d" % s for s in range(1, 25)]
    rows = [chr(65+n) for n in range(16)]
    wells = []
    for row in rows:
        for col in cols:
            wells.append("%s%s" % (row, col))
    exclude_pttrn = ['A', 'P', '01', '24']
    if exclude_outer == 2:
        exclude_pttrn = ['A', 'B', 'O', 'P', '01', '02', '23', '24']
    exclude_wells = []
    for well in wells:
        for ep in exclude_pttrn:
            if well.find(ep) != -1:
                exclude_wells.append(well)
    tr_wells = [s for s in wells if s not in exclude_wells]
    return tr_wells, list(set(exclude_wells))


def randomize_wells(df, fingerprints=['BCA2_A']):
    tr_wells, _ = define_treatment_wells(exclude_outer=1)
    df['well'] = tr_wells
    ordered_wells = df.well.tolist()
    cols = ["%02d" % s for s in range(1, 25)]
    rows = [chr(65+n) for n in range(16)]
    wells = []
    for row in rows:
        for col in cols:
            wells.append("%s%s" % (row, col))
    df_list = []
    for rep_num, fingerprint in enumerate(fingerprints):
        np.random.seed(rep_num+1)
        randomized_wells = np.random.choice(ordered_wells,
                                            size=len(ordered_wells),
                                            replace=False)
        df['well'] = randomized_wells
        df.index = df['well']
        df_fp = assign_fingerprint_wells(fingerprint, 'Staurosporine', 1)
        df_fp.index = df_fp['well']
        dfc = pd.concat([df_fp, df])
        dfc['plate'] = [fingerprint] * len(dfc)
        remainder_wells = [w for w in wells if w not in dfc.well.tolist()]
        dfo = pd.DataFrame(zip(remainder_wells, [fingerprint] * len(
            remainder_wells)), columns=['well', 'plate'])
        dfc2 = pd.concat([dfo, dfc])
        dfc2 = dfc2.sort(['well'])
        df_list.append(dfc2)
    dfr = pd.concat(df_list)
    dfr['agent'] = dfr['agent'].replace([np.nan], '')
    dfr['role'] = dfr['role'].replace([np.nan], '')
    dfr = dfr.fillna(0)
    return dfr
