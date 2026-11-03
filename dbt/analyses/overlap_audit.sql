-- Overlap audit between the two cuts. A respondent is a respondent-year (survey year + id).
-- Reads raw, because staging already keeps one copy of each. The last two columns show the
-- modelled tables count each respondent-year once.

with raw_respondents as (

    select distinct extract_id, "year", id_
    from {{ source('raw', 'gss_responses') }}

),

per_respondent as (

    select
        "year", id_,
        count(*) as cuts_holding_it,
        count(*) filter (where extract_id = (select min(extract_id) from raw_respondents)) as in_first_cut,
        count(*) filter (where extract_id = (select max(extract_id) from raw_respondents)) as in_second_cut
    from raw_respondents
    group by "year", id_

)

select
    (select min(extract_id) from raw_respondents)                      as first_cut,
    (select max(extract_id) from raw_respondents)                      as second_cut,
    sum(in_first_cut)                                                  as respondents_first_cut,
    sum(in_second_cut)                                                 as respondents_second_cut,
    count(*) filter (where cuts_holding_it = 2)                        as in_both,
    count(*)                                                           as distinct_respondents,
    round(100.0 * count(*) filter (where cuts_holding_it = 2) / sum(in_first_cut), 1)
                                                                       as overlap_pct_of_first_cut,
    round(100.0 * count(*) filter (where cuts_holding_it = 2) / sum(in_second_cut), 1)
                                                                       as overlap_pct_of_second_cut,
    (select count(*) from {{ ref('dim_respondent') }})                 as rows_in_dim_respondent,
    (select count(distinct respondent_year_id) from {{ ref('fct_response') }})
                                                                       as respondents_in_fct_response
from per_respondent
