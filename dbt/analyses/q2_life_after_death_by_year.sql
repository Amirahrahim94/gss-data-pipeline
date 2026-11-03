-- Q2. What share of respondents believe in life after death, by survey year? Show how many
-- were not asked alongside the result.  Variable: postlife.
-- pct_yes_of_answered is the weighted share of YES among YES and NO answers only.
-- not_asked is the inapplicable code (the question was not put to them); no_usable_answer is
-- don't know, no answer or skipped on the web.

select
    respondent.survey_year,
    count(*)                                                          as respondents,
    count(*) filter (where answer.is_answer and answer.answer_label = 'YES') as yes_count,
    count(*) filter (where answer.is_answer and answer.answer_label = 'NO')  as no_count,
    count(*) filter (where answer.response_type = 'inapplicable')     as not_asked,
    count(*) filter (where not answer.is_answer
                     and answer.response_type <> 'inapplicable')      as no_usable_answer,
    round(100 * sum(respondent.weight) filter (where answer.is_answer and answer.answer_label = 'YES')
              / sum(respondent.weight) filter (where answer.is_answer), 1) as pct_yes_of_answered
from {{ ref('fct_response') }} as answer
inner join {{ ref('dim_respondent') }} as respondent using (respondent_year_id)
where answer.variable_name = 'postlife'
group by respondent.survey_year
order by respondent.survey_year
