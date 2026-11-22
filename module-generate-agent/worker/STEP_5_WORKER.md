# STEP 5 — WORKER ONLY: QA rowXX.md, Difficult và Group Summary

## Phạm vi duy nhất

**Một lượt giao = một Menu Cấp 1 = một folder `GroupX/`.** Chỉ đọc file worker-only này và các nguồn được Prime giao; không đọc STEP Prime/General/rules/STEP khác hoặc lịch sử chat làm đề bài. Không tự chọn chương, file, hàng khác hoặc spawn worker.

Prime gửi **đúng bốn dòng**:

```text
<VERIFIED_SHEET_TAB_URL>
READ=A1,B1,<PARENT_A_B_C>,<EXACT_CHILD_A_B_ROWS>,<SPECIAL_NOTE_TITLE_CELL>,<SPECIAL_NOTE_VALUE_CELL>,<ALL_ASSIGNED_rowXX.md_PATHS>,/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/GroupX/info-group.yml,/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/GroupX/summary.yml
WRITE=<ALL_ASSIGNED_rowXX.md_PATHS>,/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/GroupX/summary.yml
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_5_WORKER.md
```

**Được ghi:** đúng các file **`rowXX.md` được Prime giao** sau QA/refactor, cùng `GroupX/summary.yml` (`chapter`, `lessons[].difficult`, `lessons[].markdownSummary`). **Không được ghi:** C:N, O hoặc AC trên Sheet (Prime PUBLISH code-only); A/B/C identity, Menu, header, nhóm khác, `GroupX/info-group.yml`, `rowXX-info.yml`, master.json, Java/module config, metadata/bảng assessment hoặc tab khác.

## W1 — Preflight và bản đồ Knowledge

1. Xác minh URL/gid/tab của lượt giao. Đọc nguyên văn `A1,B1`, Special Note (nhãn và ô ngay dưới), đúng A/B/C của hàng cha, **A/B các hàng con** được chỉ định, cùng **toàn bộ `rowXX.md` đúng danh sách Prime giao**, `info-group.yml` và `summary.yml`. Mỗi Group chứa **một chapter**, các children đúng thứ tự; A-child IDs đã được STEP 3 cấp. **Không đọc Knowledge từ C:N hoặc Difficulty từ O để thay thế nguồn file.**
2. `info-group.yml` là metadata bất biến: `groupIndex,parentRow,menuLevel1,filename,baseId,children:[{row,id,menuLevel2}]` và thông tin Sheet. Đối chiếu từng row/id/title với Sheet và file `summary.yml` (mảng `lessons` đúng thứ tự, `row/id` cố định). Nếu lệch/trùng/mất/chip/formula ngoài quyền → `BLOCKER: STEP5_GROUP_IDENTITY`; không đổi identity hoặc tạo group mới.
3. Đọc **đầy đủ** Markdown Knowledge trong từng file `rowXX.md` (file UTF-8 toàn văn). Kiểm tra thiếu/truncated, code fence, cú pháp/thuật ngữ, cơ chế, code/stdout, ví dụ, giới hạn, giá trị thực tế, khả năng tự học. Đọc đủ cả chương trước khi sửa để lập bản đồ bài, kiểm soát phần lặp. Không suy đoán nội dung từ tên Menu.
4. Snapshot nguyên văn **toàn bộ file `rowXX.md` được cấp** và `summary.yml` trước WRITE. STEP 4 **không PUBLISH C:N**, vì vậy không cần baseline Sheet C:N và Worker không đọc/sửa `knowledgeBaseline` legacy nếu có trong `info-group.yml`. Worker không gọi Google API ghi Knowledge/Difficulty/Summary. Không overwrite tệp ngoài quyền, không xóa/đổi tên file.

## W2 — Review/refactor Knowledge toàn chương

1. QA sự chính xác, đầy đủ, ngữ nghĩa, code, Markdown và sự trùng lặp gây hại **trên toàn chương**. Mỗi bài phải đứng được độc lập ở phạm vi hợp lý; bảo toàn một nơi giải thích chính của mỗi khái niệm, nhưng cho phép nhắc lại ngắn hay áp dụng ở bài khác. Không biến mọi bài thành khuôn WHAT/WHY/HOW; không ép độ dài hoặc giảm chất lượng chỉ để giảm lặp.
2. Bài đã tốt → **giữ nguyên byte file `rowXX.md`**. Bài cần sửa → soạn bản đầy đủ trong **chính `rowXX.md`** đã được giao; giới hạn tương ứng tối đa 12 ô C:N × 30.000 UTF-16 units/ô (tổng tối đa 360.000 units). **Không tự chia C:N**; Gradle PUBLISH sẽ split an toàn và xóa đuôi cũ khi cần. Không tạo file Knowledge thay thế, không sửa bài ngoài Group, không cắt dở Markdown.
3. Sau khi sửa, **exact-readback file UTF-8** từng bài và QA lại **toàn chương**. Không coi Worker COMPLETED nếu còn bài chưa đọc/QA hoặc bất kỳ Knowledge có blocker. **Worker không được cập nhật trực tiếp C:N**.
4. Không đổi A-child ID, A-parent title, B-child title, B-parent filename, C-parent slug hoặc tên/ID trong file Group.

## W2.4 — Difficult của từng bài trong `summary.yml`

Chọn đúng **một** nhãn cho mỗi B-child dựa trên **nội dung thực SAU review**:

- `BASIC`: kiến thức nền, thuật ngữ/cơ chế cơ bản.
- `INTERMEDIATE`: ứng dụng, kết hợp nhiều cơ chế, so sánh và trade-off.
- `ADVANCED`: cơ chế sâu, ngoại lệ, edge cases, giới hạn, kiến trúc và phân tích nâng cao.

Ghi **đúng `lessons[].difficult` trong `GroupX/summary.yml`** ở bài tương ứng (`row/id` giữ nguyên), không ghi O con hoặc O cha trực tiếp. Worker chọn độ khó dựa trên **`rowXX.md` cuối cùng sau QA**; nếu `difficult` cũ hợp lệ và đúng thì giữ nguyên; thiếu thì điền; sai/mâu thuẫn/human-owned không rõ quyền → `BLOCKER`, không overwrite mù. **Task Prime PUBLISH sẽ ghi O con, giữ dropdown/format và exact-readback.**

## W2.5 — Summary từng bài trong `lessons[].markdownSummary`

**Chỉ bắt đầu sau khi toàn bộ `rowXX.md` trong chương đã QA/refactor và exact-readback file PASS.** Mỗi `lessons[i].markdownSummary` thuộc đúng row/id đã có và là **một tài liệu Markdown độc lập** về đúng `menuLevel2` của hàng con đó. **Không ghi AC trực tiếp**, không sao chép cùng một Summary cho nhiều bài, không chèn Summary vào Knowledge file.

**Barem bắt buộc:** đúng bốn heading 0 → 1 → 2 → 3 theo thứ tự:

```markdown
# 0. Định hướng học tập

## 1. Mục đích của bài học

**<Tên chính xác Menu Cấp 2 ở B child>**

<Lý do học, vấn đề cần giải quyết và giá trị khi vận dụng.>

## 2. Những câu hỏi người học phải tự trả lời được

### <Tên nhóm hỏi mở thực tế>
1. <Câu hỏi về bản chất/cơ chế?>
2. <Câu hỏi về nguyên nhân hoặc tình huống áp dụng?>

## 3. Sau khi học xong, người học phải đạt được điều gì?

| Năng lực | Kết quả mong đợi |
| --- | --- |
| <Năng lực cụ thể> | <Hành động đánh giá được> |
```

- Mục 0 **chỉ có heading**, không prose chung chung. Mục 1 ghi **đúng tên bài in đậm** và giải thích mục đích gắn với Knowledge thật.
- Mục 2 có một hoặc nhiều nhóm theo `###` với **câu hỏi mở, numbered list, có dấu hỏi**, không đặt câu hỏi vượt nội dung hay ghi sẵn đáp án. Không áp quota câu/nhóm, không hỏi giống nhau cho nhiều bài.
- Mục 3 có **đúng bảng hai cột** `Năng lực` và `Kết quả mong đợi` với năng lực cụ thể → hành động có thể quan sát/kiểm chứng; không chỉ “hiểu/biết”.
- GFM chuẩn, heading/bold, dòng trống, numbered list, bảng đủ pipe và escape `|` nếu trong cell. **Không có placeholder `<...>` trong output, TODO, YAML/JSON/code fence bao toàn Summary, HTML giả, báo cáo nội bộ.** Không ép số từ/đoạn; tối đa **30.000 Unicode code points và 32.767 UTF-16 units** cho một `markdownSummary` vì sẽ vào một ô AC con.
- Nội dung trùng lặp có hại, lệch Summary sau Knowledge refactor hoặc Special Note yêu cầu điều chưa được dạy → `BLOCKER: STALE_OBJECTIVES/UNSUPPORTED_LEARNING_OBJECTIVES`; không bịa để lấp chỗ trống.

## W2.6 — Summary tổng chương tại `summary.yml.chapter`

Worker viết trong **duy nhất object `chapter`** sau khi tất cả `markdownSummary` đã có, không tạo YAML AC cha riêng. `chapter` có **chính xác sáu key**:

```yaml
chapter:
  version: 1
  type: LEARNING_ROADMAP
  title: "Learning flow của chương"
  roadmapHeading: "Lộ trình học"
  roadmap:
    - description: "Bài đầu tiên đóng vai trò gì"
      transition:
        description: "Tại sao cần chuyển sang bài kế tiếp"
    - description: "Bài cuối đóng vai trò gì"
      transition: null
  comparisonMarkdown: |-
    ## So sánh các bài trong chương

    | Tiêu chí | Bài thứ nhất | Bài thứ hai |
    | --- | --- | --- |
    | Trọng tâm | ... | ... |
    | Vấn đề giải quyết | ... | ... |
    | Cơ chế | ... | ... |
    | Giá trị ứng dụng | ... | ... |
```

- N bài con ⇒ đúng N phần tử roadmap theo **thứ tự B-child thực**, mỗi phần tử chỉ `description` và `transition`. N−1 transition dạng map chỉ có `description` giải thích vì sao tiếp theo; phần tử cuối `transition: null`.
- **Cấm authored `id/order/title/to`** tại roadmap hoặc transition. Các thông tin này được importer tính từ A-child IDs/B-child titles/row order sau PUBLISH.
- `comparisonMarkdown`: một bảng GFM **N+1 cột**, hàng header và separator, tối thiểu bốn tiêu chí thật có giá trị so sánh, heading rõ nghĩa; không link giả/mũi tên giả, không văn mẫu, không lạm dụng lời kết. `chapter` phải có chiều sâu, gắn với cả chương.
- Toàn YAML của `chapter` khi serialize phải vừa **một ô AC cha** (≤30.000 code points, ≤32.767 UTF-16 units). Bất kỳ mâu thuẫn schema hoặc legacy `chapter` đã có derived fields phải báo `BLOCKER: STEP5_AC_SCHEMA_CONFLICT`, không tự xóa/hạ schema.

## W3 — Viết và xác minh file `summary.yml`

1. Preflight file `summary.yml` đã được Prime PREPARE; `chapter` và `lessons` tồn tại, đúng row/id/order/fields **`difficult` và `markdownSummary`**. **Không thay toàn bộ file bằng mẫu mới**, không xóa field khác/human-owned, không làm mất Summary valid đã có. Nếu Summary đã hợp lệ và vẫn khớp Knowledge sau review, giữ nguyên; nếu stale/khác provenance, báo blocker và yêu cầu quyền sửa rõ ràng.
2. Sau khi soạn đủ nội dung, cập nhật đúng `chapter` và từng **`lessons[].difficult` + `lessons[].markdownSummary`** của **chính Group**; giữ `row/id`, thứ tự, `version/type` và cấu trúc bất biến. Đọc lại YAML, parse, đối chiếu đủ N bài, mỗi difficult là BASIC/INTERMEDIATE/ADVANCED, mọi heading/bảng, version/type, N roadmap descriptions, transition cuối null và bảng GFM N+1 cột. Không cần tạo `GroupX/summary.md` hoặc các file phụ.
3. **Không gọi Gradle PUBLISH** và không gọi Sheets API cho C:N/O/AC. Prime là người duy nhất QA file và chạy `publishStep5Summary` DRY_RUN → APPLY. Nếu write/readback file lỗi hoặc file đang bị thay đổi đồng thời, dừng và báo chính xác path/tình trạng, không claim PASS.
4. C:N/O/AC chỉ được **Gradle PUBLISH** cập nhật từ `rowXX.md` và `summary.yml`; Worker không làm thay đổi formula/note/format/validation của Sheet, không sửa ngoài quyền.

## W4 — Báo cáo và SLEEPING

Báo một lần các trường:

- `STATUS=COMPLETED/BLOCKER/FAILED`, `GROUP=GroupX`, `PARENT_ROW`, `CHILD_ROWS`, `INFO_GROUP_PATH`, `SUMMARY_PATH`, số bài phải đọc/đã đọc toàn văn/đã QA.
- `KNOWLEDGE_QA`: danh sách `rowXX.md` giữ nguyên, bài sửa, lý do, readback file, có trùng/lỗi còn tồn đọng; **không report đã ghi C:N**.
- `DIFFICULT`: từng row/id → `summary.yml.lessons[].difficult` → BASIC/INTERMEDIATE/ADVANCED và lý do, readback YAML; **không report đã ghi O**.
- `MARKDOWN_SUMMARY`: từng row/id → độ dài, bốn mục, câu hỏi mở/bảng năng lực, consistency với Knowledge, QA/readback file.
- `CHAPTER_SUMMARY`: authored-only 6 keys, N roadmap, final transition null, comparison table N+1 cột, source grounding, QA/readback file.
- `PRESERVED`: identity `A/B/C`, `info-group.yml`, `rowXX-info.yml`, toàn bộ C:N/O/AC trên Sheet và assessment không bị Worker sửa; `BLOCKERS` theo path nếu có.

**COMPLETED = Worker đã QA/refactor Knowledge trong `rowXX.md` và lưu Difficult/Summary local**, **không** có nghĩa C:N/O/AC đã được publish hoặc STEP 5 checkpoint. Sau báo cáo, release ownership, về `SLEEPING` để Prime QA/publish/điều phối tiếp.
