-- Every layer keeps every respondent-year once, and the response table has one row per
-- respondent-year per answer variable. Returns one row of counts when anything differs.
with counts as (

    select
        (select count(*) from (select distinct "year", id_ from {{ source('raw', 'gss_responses') }}))
                                                                          as raw_respondent_years,
        (select count(*) from {{ ref('stg_gss__respondents') }})          as staging_rows,
        (select count(*) from {{ ref('dim_respondent') }})                as dim_rows,
        (select count(distinct respondent_year_id) from {{ ref('fct_response') }})
                                                                          as fct_respondent_years,
        (select count(*) from {{ ref('fct_response') }})                  as fct_rows,
        (select count(*) from (
            select respondent_year_id, variable_name
            from {{ ref('fct_response') }}
            group by respondent_year_id, variable_name
        ))                                                                as fct_distinct_answers,
        {{ var('answer_variables') | length }}                            as variables_per_respondent

)

select *
from counts
where raw_respondent_years <> staging_rows
   or staging_rows <> dim_rows
   or dim_rows <> fct_respondent_years
   or fct_rows <> fct_distinct_answers
   or fct_rows <> staging_rows * variables_per_respondent
