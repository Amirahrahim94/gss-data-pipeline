-- Every distinct respondent-year must have exactly one row per answer variable.
select s.respondent_year_id
from {{ ref('stg_gss__respondents') }} as s
left join (
    select respondent_year_id, count(*) as n
    from {{ ref('int_gss__responses_long') }}
    group by respondent_year_id
) as l using (respondent_year_id)
where coalesce(l.n, 0) <> {{ var('answer_variables') | length }}
