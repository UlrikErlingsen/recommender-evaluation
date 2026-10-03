"""User-facing errors raised by Recommend Signal."""


class DataProblem(ValueError):
    """Raised when uploaded data cannot support the requested evaluation."""


def out_of_memory_message(subject: str = "this evaluation") -> str:
    return (
        f"There is not enough memory for {subject} on this computer. Close other programs, keep only the needed "
        "columns and period, or use a computer with more memory. Recommend Signal itself sets no size limit."
    )
