-- Q1. How is prayer frequency distributed among respondents, by the religion they were
-- raised in?  Variables: pray (prayer frequency), relig16 (religion in which raised).
-- Rows with is_answer = false are respondents who were not asked or gave no usable answer;
-- they are kept so the reader sees how many there are. pct_in_group is the weighted share
-- within a religion, among answers (is_answer) or among non-answers (not is_answer).

with prayer as (

    select respondent_year_id, answer_label as prayer_frequency, is_answer
    from {{ ref('fct_response') }}
    where variable_name = 'pray'

),

raised as (

    select respondent_year_id, answer_label as religion_raised, is_answer
    from {{ ref('fct_response') }}
    where variable_name = 'relig16'

),

joined as (

    select
        raised.religion_raised,
        prayer.prayer_frequency,
        prayer.is_answer and raised.is_answer as is_answer,
        respondent.weight
    from prayer
    inner join raised using (respondent_year_id)
    inner join {{ ref('dim_respondent') }} as respondent using (respondent_year_id)

)

select
    religion_raised,
    prayer_frequency,
    is_answer,
    count(*) as respondents,
    round(100 * sum(weight) / sum(sum(weight)) over (partition by religion_raised, is_answer), 1)
        as pct_in_group
from joined
group by religion_raised, prayer_frequency, is_answer
order by religion_raised, is_answer desc, respondents desc
