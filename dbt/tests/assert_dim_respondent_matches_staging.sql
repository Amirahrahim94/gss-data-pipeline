-- Joining age in must not add or lose respondents.
select 'row count differs' as problem
where (select count(*) from {{ ref('dim_respondent') }})
   <> (select count(*) from {{ ref('stg_gss__respondents') }})
