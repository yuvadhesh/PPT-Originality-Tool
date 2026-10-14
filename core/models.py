from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class RuleType(str, Enum):
    CONTENT = "Content"
    ALIGNMENT = "Alignment"
    FONT = "Font"


class SlideStatus(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"


@dataclass
class BoundingBox:
    left_emu: int
    top_emu: int
    width_emu: int
    height_emu: int

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left_emu, self.top_emu, self.width_emu, self.height_emu)


@dataclass
class Issue:
    slide_num: Any  # int or "Deck"
    element_name: str
    rule_type: RuleType
    issue_type: str  # e.g. "Missing Text", "Shifted Position", "Changed Font Size", etc.
    description: str
    original_value: str = ""
    remediated_value: str = ""
    difference: str = ""
    is_error: bool = True  # False for Info-level
    issue_num: int = 0  # 1-indexed unique issue number
    orig_box: Optional[BoundingBox] = None
    rem_box: Optional[BoundingBox] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_num": self.issue_num,
            "slide_num": self.slide_num,
            "element_name": self.element_name,
            "rule": self.rule_type.value,
            "issue_type": self.issue_type,
            "severity": "Error" if self.is_error else "Info",
            "description": self.description,
            "original_value": self.original_value,
            "remediated_value": self.remediated_value,
            "difference": self.difference,
        }


@dataclass
class HyperlinkInfo:
    text: str
    url: str
    shape_name: str


@dataclass
class TableInfo:
    shape_id: int
    name: str
    rows: int
    cols: int
    cell_texts: List[List[str]] = field(default_factory=list)


@dataclass
class ParagraphInfo:
    text: str
    alignment: str = "DEFAULT"  # "LEFT", "CENTER", "RIGHT", "JUSTIFY", etc.
    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    is_bold: Optional[bool] = None
    is_italic: Optional[bool] = None
    is_underline: Optional[bool] = None
    color_hex: Optional[str] = None


@dataclass
class ShapeInfo:
    shape_id: int
    name: str
    shape_type: str
    left_emu: int
    top_emu: int
    width_emu: int
    height_emu: int
    rotation: float = 0.0
    z_order: int = 0
    text: str = ""
    paragraphs: List[ParagraphInfo] = field(default_factory=list)
    vertical_anchor: Optional[str] = None  # "TOP", "MIDDLE", "BOTTOM", etc.
    font_name: Optional[str] = None
    font_size_pt: Optional[float] = None
    is_bold: Optional[bool] = None
    is_italic: Optional[bool] = None
    is_underline: Optional[bool] = None
    color_hex: Optional[str] = None
    is_image: bool = False
    image_hash: Optional[str] = None
    is_chart: bool = False
    is_table: bool = False
    is_group: bool = False
    is_placeholder: bool = False
    placeholder_type: Optional[str] = None
    hyperlinks: List[HyperlinkInfo] = field(default_factory=list)
    parent_group_id: Optional[int] = None


@dataclass
class SlideData:
    slide_id: int
    slide_index: int  # 1-indexed
    title: str = ""
    text_blocks: List[str] = field(default_factory=list)
    text_content: str = ""
    shapes: List[ShapeInfo] = field(default_factory=list)
    tables: List[TableInfo] = field(default_factory=list)
    notes: str = ""
    hyperlinks: List[HyperlinkInfo] = field(default_factory=list)
    images_count: int = 0
    charts_count: int = 0
    tables_count: int = 0
    shapes_count: int = 0
    slide_width_emu: int = 9144000
    slide_height_emu: int = 6858000


@dataclass
class SlideMatch:
    orig_index: Optional[int]  # 1-indexed, None if added
    rem_index: Optional[int]   # 1-indexed, None if deleted
    match_type: str            # "MATCHED", "ADDED", "DELETED", "REORDERED"
    similarity_score: float    # 0.0 to 100.0


@dataclass
class SlideDiffResult:
    slide_key: str             # e.g., "Slide 1"
    orig_index: Optional[int]
    rem_index: Optional[int]
    match_type: str
    similarity_score: float
    issues: List[Issue] = field(default_factory=list)
    orig_image_path: Optional[str] = None
    rem_image_path: Optional[str] = None
    diff_image_path: Optional[str] = None
    status: SlideStatus = SlideStatus.PASS

    def update_status(self) -> None:
        has_error = any(i.is_error for i in self.issues)
        self.status = SlideStatus.FAIL if has_error else SlideStatus.PASS

    @property
    def content_issues(self) -> List[Issue]:
        return [i for i in self.issues if i.rule_type == RuleType.CONTENT]

    @property
    def alignment_issues(self) -> List[Issue]:
        return [i for i in self.issues if i.rule_type == RuleType.ALIGNMENT]

    @property
    def font_issues(self) -> List[Issue]:
        return [i for i in self.issues if i.rule_type == RuleType.FONT]


@dataclass
class DeckMetadata:
    title: str = ""
    author: str = ""
    slide_count: int = 0
    slide_width_emu: int = 9144000
    slide_height_emu: int = 6858000


@dataclass
class DeckComparisonResult:
    orig_filename: str
    rem_filename: str
    orig_metadata: DeckMetadata
    rem_metadata: DeckMetadata
    slide_matches: List[SlideMatch]
    slide_results: List[SlideDiffResult]
    deck_issues: List[Issue] = field(default_factory=list)
    processing_time_sec: float = 0.0
    check_fonts: bool = False

    @property
    def all_issues(self) -> List[Issue]:
        issues = list(self.deck_issues)
        for s in self.slide_results:
            issues.extend(s.issues)
        return issues

    @property
    def rule1_content_issues(self) -> List[Issue]:
        return [i for i in self.all_issues if i.rule_type == RuleType.CONTENT]

    @property
    def rule2_alignment_issues(self) -> List[Issue]:
        return [i for i in self.all_issues if i.rule_type == RuleType.ALIGNMENT]

    @property
    def font_issues(self) -> List[Issue]:
        return [i for i in self.all_issues if i.rule_type == RuleType.FONT]

    @property
    def rule1_errors_count(self) -> int:
        return sum(1 for i in self.rule1_content_issues if i.is_error)

    @property
    def rule2_errors_count(self) -> int:
        return sum(1 for i in self.rule2_alignment_issues if i.is_error)

    @property
    def font_errors_count(self) -> int:
        return sum(1 for i in self.font_issues if i.is_error)

    @property
    def total_errors_count(self) -> int:
        return sum(1 for i in self.all_issues if i.is_error)

    @property
    def pass_slides_count(self) -> int:
        return sum(1 for s in self.slide_results if s.status == SlideStatus.PASS)

    @property
    def fail_slides_count(self) -> int:
        return sum(1 for s in self.slide_results if s.status == SlideStatus.FAIL)
