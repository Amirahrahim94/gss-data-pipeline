-- Q3. For each education level, which industry is most common among working respondents?
-- Variables: educ (years of schooling), indus10 (industry, 2010 classification), wrkstat
-- (working = full time, part time, or with a job but temporarily away).
-- Ties are all shown (rank 1). Small cells are weak evidence, so n_working is shown too.

with working as (

    select respondent_year_id
    from {{ ref('fct_response') }}
    where variable_name = 'wrkstat'
      and answer_label in (
          'Working full time',
          'Working part time',
          'With a job, but not at work because of temporary illness, vacation, strike'
      )

),

education as (

    select respondent_year_id, answer_code as education_code, answer_label as education
    from {{ ref('fct_response') }}
    where variable_name = 'educ' and is_answer

),

industry as (

    select respondent_year_id, answer_label as industry
    from {{ ref('fct_response') }}
    where variable_name = 'indus10' and is_answer

),

counted as (

    select
        education.education_code,
        education.education,
        industry.industry,
        count(*) as respondents,
        sum(count(*)) over (partition by education.education_code) as n_working_with_industry
    from working
    inner join education using (respondent_year_id)
    inner join industry using (respondent_year_id)
    group by education.education_code, education.education, industry.industry

),

ranked as (

    select *, rank() over (partition by education_code order by respondents desc) as industry_rank
    from counted

)

select
    education_code,
    education,
    industry,
    respondents,
    n_working_with_industry,
    round(100.0 * respondents / n_working_with_industry, 1) as pct_of_education_level
from ranked
where industry_rank = 1
order by education_code
