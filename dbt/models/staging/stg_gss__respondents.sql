{#- One row per distinct respondent-year.

    Raw keeps one row per respondent-year per extract, so a respondent-year in both extracts
    appears twice. The loader guarantees those copies have identical answers (and the
    assert_shared_respondent_years_agree test re-checks it), so keeping the first copy
    loses nothing. Keys and the weight are typed here; the survey answers stay as received
    (text, with special missing codes such as ".i:  Inapplicable") and are classified in the
    intermediate layer. try_cast turns an unusable key or weight into NULL so the not_null
    tests fail loudly instead of the build stopping. The answer columns come from the
    answer_variables setting in dbt_project.yml, so a new variable is added there once. -#}

with source as (

    select * from {{ source('raw', 'gss_responses') }}

),

ranked as (

    select
        *,
        row_number() over (partition by "year", id_ order by extract_id) as extract_rank,
        count(*)     over (partition by "year", id_)                     as extract_count
    from source

)

select
    cast(try_cast("year" as integer) as varchar) || '-' || cast(try_cast(id_ as integer) as varchar)
                                    as respondent_year_id,
    try_cast("year" as integer)     as survey_year,
    try_cast(id_ as integer)        as respondent_id,
    ballot,
    try_cast(wtssnrps as double)    as weight,
    extract_count,
    {%- for variable in var('answer_variables') %}
    {{ variable }}{{ "," if not loop.last }}
    {%- endfor %}
from ranked
where extract_rank = 1
