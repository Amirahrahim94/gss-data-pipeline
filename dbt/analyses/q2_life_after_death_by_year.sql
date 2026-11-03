-- Q2. What share of respondents believe in life after death, by survey year? Show how many
-- were not asked alongside the result.  Variable: postlife.
-- pct_yes_of_answered is the weighted share of YES among YES and NO answers only.
-- Every respondent-year falls in exactly one of the count columns:
--   yes_count, no_count      real answers
--   not_asked                not in the survey that year, or not_asked_on_ballot (derived
--                            from observed ballot coverage; see int_gss__responses_long)
--   inapplicable             ".i" on a ballot where others answered. In 2016 and 2018 there are none;
--                            in 2022 about half the sample is ".i", consistent with a split
--                            questionnaire form that the extract does not carry, so treat
--                            these as "not asked" when reading the 2022 figure.
--   no_usable_answer         don't know, no answer or skipped on the web

select
    respondent.survey_year,
    count(*)                                                          as respondents,
    count(*) filter (where answer.is_answer and answer.answer_label = 'YES') as yes_count,
    count(*) filter (where answer.is_answer and answer.answer_label = 'NO')  as no_count,
    count(*) filter (where answer.response_type in
        ('not_asked_on_ballot', 'unavailable_that_year'))             as not_asked,
    count(*) filter (where answer.response_type = 'inapplicable')     as inapplicable,
    count(*) filter (where not answer.is_answer and answer.response_type not in
        ('not_asked_on_ballot', 'unavailable_that_year', 'inapplicable'))
                                                                      as no_usable_answer,
    round(100 * sum(respondent.weight) filter (where answer.is_answer and answer.answer_label = 'YES')
              / sum(respondent.weight) filter (where answer.is_answer), 1) as pct_yes_of_answered
from {{ ref('fct_response') }} as answer
inner join {{ ref('dim_respondent') }} as respondent using (respondent_year_id)
where answer.variable_name = 'postlife'
group by respondent.survey_year
order by respondent.survey_year
