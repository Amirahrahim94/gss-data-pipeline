-- Q3. For each education level, which industry is most common among working respondents?
-- Variables: educ (highest year of school completed, 0-20), indus10 (industry, 2010
-- classification), wrkstat (working = is_working in dim_respondent: full time, part time, or
-- with a job but temporarily away).
-- The extracts carry years of schooling, not degree, so "education level" is a band of
-- years: 12 is roughly high school and 16 roughly a four-year college course, but the bands
-- are an approximation of degree, not a measure of it. Banding replaces 21 small groups with
-- five usable ones. Adding the GSS degree variable to the extracts would answer this directly.
-- Counts are unweighted. Ties are all shown (rank 1). Small cells are weak evidence, so
-- respondents_in_level is shown too.

with working as (

    select
        respondent_year_id,
        case
            when educ_years < 12  then 1
            when educ_years = 12  then 2
            when educ_years < 16  then 3
            when educ_years = 16  then 4
            else 5
        end as education_band,
        case
            when educ_years < 12  then 'Under 12 years (no high school diploma)'
            when educ_years = 12  then '12 years (high school)'
            when educ_years < 16  then '13-15 years (some college)'
            when educ_years = 16  then '16 years (four years of college)'
            else '17+ years (postgraduate study)'
        end as education_level
    from {{ ref('dim_respondent') }}
    where is_working and educ_years is not null

),

industry as (

    select respondent_year_id, answer_label as industry
    from {{ ref('fct_response') }}
    where variable_name = 'indus10' and is_answer

),

counted as (

    select
        working.education_band,
        working.education_level,
        industry.industry,
        count(*) as respondents,
        sum(count(*)) over (partition by working.education_band) as respondents_in_level
    from working
    inner join industry using (respondent_year_id)
    group by working.education_band, working.education_level, industry.industry

),

ranked as (

    select *, rank() over (partition by education_band order by respondents desc) as industry_rank
    from counted

)

select
    education_level,
    industry,
    respondents,
    respondents_in_level,
    round(100.0 * respondents / respondents_in_level, 1) as pct_of_education_level
from ranked
where industry_rank = 1
order by education_band
