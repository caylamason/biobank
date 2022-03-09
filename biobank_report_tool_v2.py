# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.

import pandas as pd
import streamlit as st
import numpy as np
from datetime import datetime
from io import BytesIO
from pyxlsb import open_workbook as open_xlsb


# export/downloading files function
# https://discuss.streamlit.io/t/download-button-for-csv-or-xlsx-file/17385
def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Sheet1')
    workbook = writer.book
    worksheet = writer.sheets['Sheet1']
    format1 = workbook.add_format({'num_format': '0.00'})
    worksheet.set_column('A:A', None, format1)
    writer.save()
    processed_data = output.getvalue()
    return processed_data


def update_inventory():
    # upload files
    st.write('Upload files. Do not include *any* patient identifiers.')
    specimen_file = st.file_uploader('Sample log', type=['xls', 'xlsx'])
    inventory_file = st.file_uploader('Inventory', type=['xls', 'xlsx'])

    if (specimen_file is not None) & (inventory_file is not None):
        samples = pd.read_excel(specimen_file, sheet_name='Sheet1', index_col=None)
        inv = pd.read_excel(inventory_file, sheet_name='Main Biobank Inventory',
                            index_col=None)

        # --- fix the files ---
        # remove any whitespace and newline character from Subject
        inv['Subject'] = inv['Subject'].astype(str).str.strip().str.replace(' ', '')
        samples['Subject'] = samples['Subject'].astype(str).str.strip().str.replace(' ', '')
        # ensure Tissue is a string object
        inv.Tissue = inv.Tissue.astype(str)
        samples.Tissue = samples.Tissue.astype(str)
        # remove all spaces and periods from column names
        inv.columns = inv.columns.str.replace(' ', '_').str.replace('.', '')
        samples.columns = samples.columns.str.replace(' ', '_').str.replace('.', '')
        # remove the 'Vials_Remaining' column from samples df
        samples.drop(columns=['Vials_Remaining'], inplace=True)
        # convert the 'Date_of_Sample' column to datetime format
        inv['Date_of_Sample'] = pd.to_datetime(inv['Date_of_Sample'])

        # --- filter inventory and count ---
        # filter out all specimens that were used
        i = inv.loc[(inv.Taken_By.isnull()) | (inv.Date_Taken.isnull())].reset_index(drop=True)
        # group by Subject, Tissue, Date and get count
        i = i.groupby(['Subject', 'Tissue']).Date_of_Sample.value_counts()
        i = i.rename('Vials_Remaining').to_frame().reset_index()

        # --- merge and export ---
        # merge first on Subject and Date
        merged = samples.merge(i, on=['Subject', 'Date_of_Sample'], how='left')
        # merge again based on Tissue
        merged = merged.drop(columns=['Tissue_y'])
        merged.rename(columns={'Tissue_x': 'Tissue'}, inplace=True)
        merged = merged.merge(i, on=['Subject', 'Date_of_Sample', 'Tissue'], how='left')
        # keep non-null values
        merged['Vials_Remaining'] = np.where(merged.Vials_Remaining_y.isnull(),
                                             merged.Vials_Remaining_x,
                                             merged.Vials_Remaining_y)
        merged = merged.drop(columns=['Vials_Remaining_x', 'Vials_Remaining_y'])
        # replace NaN with 0 in Vials_Remaining
        merged['Vials_Remaining'] = np.where(merged.Vials_Remaining.isnull(),
                                             0,
                                             merged.Vials_Remaining)
        # remove timestamp from date
        merged.Date_of_Sample = merged.Date_of_Sample.dt.date
        # remove 'nan' from tissue column
        merged['Tissue'] = np.where(merged.Tissue == 'nan', '', merged.Tissue)

        return merged


# A = General inventory
def program_A():
    merged = update_inventory()
    if merged is not None:
        # export
        excelFileName = datetime.today().strftime('%Y-%m-%d') + ' Inventory.xlsx'
        df_xlsx = to_excel(merged)
        st.download_button(label='📥 Download', data=df_xlsx, file_name=excelFileName)


# C = Demographics info
def program_C():
    # upload file
    st.write('Upload file. Do not include identifiers. Only need the following columns:')
    """
    * Consent_Date
    * Ethnicity
        * Hispanic
        * Non-hispanic
    * Race
        * American Indian/Alaska Native
        * Asian        
        * Black or African American
        * More than one race
        * Native Hawaiian or Other Pacific Islander
        * White
    * Sex
    """
    consent_file = st.file_uploader('Consent log', type=['xls', 'xlsx'])

    # filter according to date
    filter_date = st.radio('Filter consents by date?', ('Yes', 'No'))
    if filter_date == 'Yes':
        start_date = st.date_input('Starting when?')
        start_date = pd.to_datetime(start_date)

    if consent_file is not None:
        consents = pd.read_excel(consent_file, sheet_name='Sheet1', index_col=None)
        consents = consents[['Consent_Date', 'Ethnicity', 'Race', 'Sex']].reset_index()

        if filter_date == 'Yes':
            consents = consents[consents.Consent_Date >= start_date]

        consents.drop(columns='Consent_Date', inplace=True)

        # count per ethnicity, race, and sex
        counts = consents.groupby(['Ethnicity', 'Race']).Sex.value_counts().rename('Count').to_frame().reset_index()
        counts = counts.pivot(index=['Ethnicity', 'Race'], columns=['Sex'], values='Count').reset_index().fillna(0)

        # export
        excelFileName = datetime.today().strftime('%Y-%m-%d') + ' Demographics.xlsx'
        df_xlsx = to_excel(counts)
        st.download_button(label='📥 Download', data=df_xlsx, file_name=excelFileName)


# D = Specimen counts according to diagnosis, sex, and age
def program_D():
    merged = update_inventory()

    if merged is not None:
        # filter out any expended samples
        merged = merged[merged.Vials_Remaining > 0]

        # fill out simple diagnosis
        merged.Simple_Diagnosis = np.select(
            [
                merged.Diagnosis.str.contains('AML', case=False) | merged.Diagnosis.str.contains(
                    'acute myeloid leukemia',
                    case=False),
                merged.Diagnosis.str.contains('CML', case=False) | merged.Diagnosis.str.contains(
                    'chronic myeloid leukemia',
                    case=False),
                merged.Diagnosis.str.contains('MF', case=False) | merged.Diagnosis.str.contains('myelofibrosis',
                                                                                                case=False),
                merged.Diagnosis.str.contains('MDS', case=False) | merged.Diagnosis.str.contains(
                    'myelodysplastic syndrome',
                    case=False),
                merged.Diagnosis.str.contains('MM', case=False) | merged.Diagnosis.str.contains('myeloma', case=False),
                (merged.Diagnosis.str.contains('AVN', case=False) | merged.Diagnosis.str.contains('osteoarthritis',
                                                                                                  case=False) | merged.Diagnosis.str.contains(
                    'aNBM', case=False) | merged.Diagnosis.str.contains('normal',
                                                                        case=False) | merged.Diagnosis.str.contains(
                    'Kulidjian', case=False)) & merged.Tissue.str.contains('BM', case=False),
                merged.Diagnosis.str.contains('PV', case=False) | merged.Diagnosis.str.contains('polycythemia',
                                                                                                case=False),
                merged.Diagnosis.str.contains('ET', case=False) | merged.Diagnosis.str.contains('essential',
                                                                                                case=False) | merged.Diagnosis.str.contains(
                    'thrombo', case=False),
                merged.Diagnosis.str.contains('CB', case=False) | merged.Diagnosis.str.contains('cord blood',
                                                                                                case=False) | merged.Tissue.str.contains(
                    'CB', case=False)
            ],
            [
                'AML',
                'CML',
                'MF',
                'MDS',
                'MM',
                'aNBM',
                'PV',
                'ET',
                'Cord Blood'
            ],
            default=merged.Diagnosis)

        # get average age per diagnosis
        age = merged.groupby(['Simple_Diagnosis']).Age.mean().rename('Avg Age').to_frame().reset_index()

        # get number of samples according to sex
        sex = merged.groupby(['Simple_Diagnosis']).Sex.value_counts().rename('Count').to_frame().reset_index()
        sex = sex.pivot(index='Simple_Diagnosis', columns='Sex', values='Count').reset_index().fillna(0)
        sex['Total'] = sex['M'] + sex['F']
        samples_age_sex = sex.merge(age, on='Simple_Diagnosis', how='left')

        # export
        excelFileName = datetime.today().strftime('%Y-%m-%d') + ' Specimen Counts by Diagnosis and Sex.xlsx'
        df_xlsx = to_excel(samples_age_sex)
        st.download_button(label='📥 Download', data=df_xlsx, file_name=excelFileName)


# menu options
A = 'Update the sample list with inventory'
B = 'IRB annual report / continuing review'
C = 'Demographics info (NIH)'
D = 'Specimen counts with diagnosis, age, and sex'


def menu(menu_choice):
    if menu_choice == A:
        program_A()
    elif menu_choice == C:
        program_C()
    else:
        program_D()


# subjects_file = st.file_uploader('Consent log', type=['xls', 'xlsx'])
# subjects = pd.read_excel(subjects_file, sheet_name='Sheet1', index_col=None)


# ===== Streamlit App =====
# header
st.title('Biobank Report Tool')
st.subheader('Generate reports for annual IRB continuing review, update the inventory, and create sample tables.')

menu_choice = st.radio('What do you need?', (A, C, D))
menu(menu_choice)
