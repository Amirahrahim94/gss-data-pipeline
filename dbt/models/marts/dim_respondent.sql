{#- One row per respondent-year: who the respondent is, which ballot and weight they carry.

    Demographics come from the classified long table, not from staging, so a special missing
    code can never sit in a demographic column looking like an answer. The max() ... filter
    pattern turns long rows into columns; a respondent has one row per variable, so max() only
    picks that one value. Each demographic has a
    readable value that is null unless the respondent gave a real answer, and a
    <variable>_response_type column that says what the null means (dont_know, no_answer, ...).
      - age_number   age in years; 89 means "89 or older" (top-coded)
      - educ_years   highest year of school completed (0-20); educ is the readable label
      - is_working   true for working full time, part time, or with a job but temporarily
                     away; false for any other real work_status; null when wrkstat has no
                     real answer. Defined once here so analyses do not repeat the labels. -#}

with demographics as (

    select
        respondent_year_id,
        max(answer_label)  filter (where variable_name = 'sex'    and response_type = 'answer') as sex,
        max(response_type) filter (where variable_name = 'sex')                                 as sex_response_type,
        max(answer_label)  filter (where variable_name = 'region' and response_type = 'answer') as region,
        max(response_type) filter (where variable_name = 'region')                              as region_response_type,
        max(answer_label)  filter (where variable_name = 'educ'   and response_type = 'answer') as educ,
        max(answer_code)   filter (where variable_name = 'educ'   and response_type = 'answer') as educ_years,
        max(response_type) filter (where variable_name = 'educ')                                as educ_response_type,
        max(answer_number) filter (where variable_name = 'age')                                 as age_number,
        max(response_type) filter (where variable_name = 'age')                                 as age_response_type,
        max(answer_label)  filter (where variable_name = 'wrkstat' and response_type = 'answer') as work_status,
        max(response_type) filter (where variable_name = 'wrkstat')                              as work_status_response_type
    from {{ ref('int_gss__responses_long') }}
    where variable_name in ('sex', 'region', 'educ', 'age', 'wrkstat')
    group by respondent_year_id

)

select
    s.respondent_year_id,
    s.survey_year,
    s.respondent_id,
    s.ballot,
    s.weight,
    s.extract_count,
    d.sex,
    d.sex_response_type,
    d.region,
    d.region_response_type,
    d.educ,
    d.educ_years,
    d.educ_response_type,
    d.age_number,
    d.age_response_type,
    d.work_status,
    d.work_status_response_type,
    d.work_status in (
        'Working full time',
        'Working part time',
        'With a job, but not at work because of temporary illness, vacation, strike'
    ) as is_working
from {{ ref('stg_gss__respondents') }} as s
left join demographics as d
    on d.respondent_year_id = s.respondent_year_id
