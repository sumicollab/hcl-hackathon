"""Turn authoritative calculation results into readable sentences, without an LLM."""
import json


def answer_text(response):
    if response["answer_type"] != "calculated":
        return response["answer"]
    result = json.loads(response["answer"])
    values = {rule["parameter"]: rule["value"] for rule in response["applied_rules"]}
    if "attendance_pct" in result:
        course = result["course_code"]
        text = (f"Your attendance in {course} is {result['attendance_pct']:g}%. "
                f"You attended {result['classes_attended']} out of {result['classes_held']} classes.")
        if "result" in result:
            met = result["result"] == "ATTENDANCE_REQUIREMENT_MET"
            decision = "meet" if met else "do not meet"
            text += (f"\n\nYou {decision} the attendance requirement for the {course} exam. "
                     f"The applicable minimum attendance is {float(values['min_attendance_pct']):g}%.")
        return text
    if "cgpa" in result:
        met = result["result"] == "PROFILE_REQUIREMENTS_MET"
        decision = "meet" if met else "do not meet"
        return (f"You {decision} the CGPA and backlog requirements for placement.\n\n"
                f"Your CGPA is {result['cgpa']:g}, and you have {result['active_backlogs']} active backlogs. "
                f"The applicable requirements are a minimum CGPA of {float(values['min_cgpa']):g} "
                f"and no more than {float(values['max_backlogs']):g} active backlogs.")
    if "records" in result:
        return "\n\n".join(
            f"For {row['course_code']} ({row['exam_session']}, {row['exam_type']}), "
            f"you scored {row['total_marks']:g} out of {row['max_marks']:g}. "
            f"Your recorded result is {row['result']}."
            for row in result["records"]
        )
    return "The calculation completed. Contact the student services office to review this result."
