# STEP_6_WORKER_NEW — WORKER ONLY: QA Knowledge + Metadata + Related của một chương

## Phạm vi duy nhất

**Một lượt giao = một Menu cấp 1 = một chapter trong `content/knowledge/<lang>/`.**
Worker **đọc toàn bộ Knowledge, QA/refactor chất lượng, phân loại độ khó,
viết Summary từng bài, so sánh các bài và **tìm Related cho ba loại assessment**.
Metadata được ghi vào đúng
`childs[]` của file YAML **riêng của chương** trong
`temp/step6/<SERVICE_NAME>/<lang>/`.

Chỉ đọc file hướng dẫn Worker này và các file Prime cấp; không tự đọc tài
liệu Prime/STEP khác, lịch sử chat, file bài/chapter khác, file metadata
hay tự tìm scope rộng hơn. Không spawn Worker, không commit/push
hoặc chạy các STEP tiếp theo.

## W0 — Handoff và ownership

Prime phải gửi **nội dung thực** (không gửi file `module-info.json`):

```text
MODULE_LOCATION=<ABSOLUTE_MODULE_LOCATION>
LANG=<lang>
SERVICE_NAME=<nội dung SERVICE_NAME.VALUE>
SERVICE_NAME_DESCRIBE=<nội dung SERVICE_NAME_DESCRIBE.VALUE>
SPECIAL_NOTE=<nguyên văn SPECIAL_NOTE.VALUE, kể cả khi rỗng hay nhiều dòng>
CHAPTER_INDEX=<1-based chapter index>
CHAPTER_SLUG=<verified slug>
CHAPTER_TITLE=<verified title>
CHAPTER_YAML=<java-learning>/temp/step6/<SERVICE_NAME>/<lang>/<index>-<slug>.yml
CHAPTER_STATUS=<java-learning>/temp/step6/<SERVICE_NAME>/<lang>/<index>-<slug>-status.yml
KNOWLEDGE_FOLDER=<ABSOLUTE_MODULE_LOCATION>/content/knowledge/<lang>/<index>.<slug>/
ASSESSMENTS=<MODULE_LOCATION>/content/temp/step5/format/{quiz,interview,casestudy}.yml
RELATED_FOLDER=<MODULE_LOCATION>/content/temp/step5/readme-related/<CHAPTER_SLUG>/
READ=<CHAPTER_YAML>,<CHAPTER_STATUS>,<đầy đủ lesson .yml và .md của KNOWLEDGE_FOLDER>,<ASSESSMENTS>,<RELATED_FOLDER>
WRITE=<CHAPTER_YAML>,<CHAPTER_STATUS>,<đầy đủ lesson .md của đúng chapter>,<RELATED_FOLDER>/quiz.yml,<RELATED_FOLDER>/interview.yml,<RELATED_FOLDER>/casestudy.yml
INSTRUCTIONS=<java-learning>/learning-platform-data/module-generate-agent/worker/STEP_6_WORKER_NEW.md
```

Prime phải liệt kê **toàn bộ bài của chương** và cung cấp ba giá trị metadata
đầy đủ; `SPECIAL_NOTE` có thể là chuỗi rỗng nhưng phải nói rõ, không tự bịa.
Đây là ngữ cảnh học tập, không phải quyền đọc/ghi mới.

**WRITE được phép:**

1. Đúng các `<lesson-slug>.md` Prime giao, chỉ khi Knowledge QA cần refactor.
2. **Đúng sáu field** `difficult`, `focus`, `problemSolved`, `mechanism`,
   `applicationValue`, `summary` của các `childs[]` thuộc **chapter được
   chỉ định** trong `CHAPTER_YAML`.
3. **Duy nhất field `status` của `CHAPTER_STATUS`**, sau khi Markdown, YAML,
   Related và exact readback của toàn chương PASS.
4. **Đúng ba file** `RELATED_FOLDER/{quiz,interview,casestudy}.yml`
   do Prime khởi tạo rỗng trong STEP 5. Worker có thể ghi song song vì
   mỗi chương có **thư mục riêng**; không ghi trực tiếp assessment tổng.

**Không sửa:** `status`, `slug`, `title`, thứ tự `menu/childs`,
`<lesson-slug>.yml`, `menu.yml`, `menu-level-1-slug.yml`, chapter khác,
`module-info.json`, `menu-detail-status.yml` gốc, `manifest.json` hoặc file
ngoài quyền. Không sửa `content/temp/step5/format/*.yml` hoặc
`content/temp/step5/status/*.yml`: **Phase 5 do Prime đánh giá/cập nhật**,
không phải Worker. Worker chỉ có file Related của đúng chương và cặp
file Knowledge chapter riêng. Không chỉnh status của file chương khác.

## W1 — Preflight và bản đồ Knowledge toàn chương

1. Xác minh module/lang/chapter/index/slug, kiểm tra `CHAPTER_YAML` chứa
   duy nhất `menu:` với **một chương**, đúng `slug`/`title` và `childs[]`.
   Đối chiếu từng bài với `<lesson-slug>.yml` và `.md` trong
   `KNOWLEDGE_FOLDER`; đúng `menuLevel1`/`menuLevel2`, thứ tự đầy đủ,
   không trùng file hoặc bỏ sót bài. Không tự sửa identity sai.
2. Tất cả bài phải có `status: WRITTEN` trong YAML riêng và tương ứng với
   `CHAPTER_YAML.menu[0].childs[]`; Markdown phải tồn tại, không rỗng.
   `CHAPTER_STATUS` phải có duy nhất field `status`, `""` khi còn chờ xử lý;
   nếu đã là `WRITTEN` từ lượt trước, kiểm tra lại toàn bộ kết quả và giữ
   nguyên nếu đúng, không tự reset.
   Nếu chưa xong STEP 4 → `BLOCKER: STEP4_NOT_VERIFIED`.
3. Xác minh sáu field STEP 6 có mặt và đúng kiểu chuỗi; `difficult` rỗng hoặc
   `BASIC`/`INTERMEDIATE`/`ADVANCED`. Nếu thiếu field bắt buộc hoặc có
   trường không đúng schema, báo `BLOCKER: STEP6_SCHEMA_INVALID`;
   không tự sửa cấu trúc.
4. Đọc **toàn văn** từng Markdown `.md`, không suy nội dung từ tên bài hoặc
   một đoạn Summary. Dùng `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`,
   `SPECIAL_NOTE` Prime giao để hiểu phạm vi, không tự đọc metadata gốc.
5. Chụp snapshot `.md`, YAML bài (read-only), toàn văn `CHAPTER_YAML` trước
   WRITE. Phát hiện thay đổi đồng thời, identity xung đột hoặc Worker khác
   sở hữu chapter → BLOCKER; không overwrite dựa vào snapshot đã lỗi thời.
6. Đọc toàn bộ `ASSESSMENTS` (ba file) **read-only**. Xác nhận mỗi group
   có `groupID` từ 1, mỗi phần tử trong `questions[]` hoặc `cases[]` có
   `index` 0, 1, 2... **bắt đầu lại từ 0 trong từng group**, không nhảy/trùng.
   Dùng nội dung thật của câu hỏi, lời giải, kiến thức và lời giải thích
   để xét Related; không chỉ dựa trên groupName hoặc keyword.

## W2 — QA/refactor Knowledge toàn chương

QA sự chính xác, tính đầy đủ, độ sâu, thuật ngữ, cơ chế, ví dụ, code/stdout,
edge case, trade-off, Markdown, link và tính hữu ích trong tự học. Đánh giá
**quan hệ giữa các bài trong cả chương**: tránh trùng lặp gây hại, giữ một
nơi giải thích chủ đạo mỗi khái niệm nhưng chấp nhận liên hệ ngắn/vận dụng ở
bài khác. Mỗi bài phải tự đứng được trong phạm vi hợp lý; **không ép bài
thành khuôn WHAT/WHY/HOW**, không rút ngắn để giảm lặp, không tự bịa số liệu,
giới hạn, API hoặc kết quả thực thi.

- Bài đã đúng và tốt: **giữ nguyên byte Markdown**, không rewrite chỉ để
  thay văn phong.
- Bài cần sửa: refactor **chính `.md` được giao**, bảo toàn nội dung đúng,
  cơ chế, ví dụ/code, tính độc lập và Special Note; không tạo file khác.
- Sau thay đổi: exact readback UTF-8, QA lại toàn chương. Không coi PASS
  khi còn bài chưa đọc/QA, code fence hỏng, nội dung trống/truncated hoặc
  lỗi chưa giải quyết được.
- STEP 4 `status: WRITTEN` không phải chứng nhận QA STEP 6; **không sửa
  status** để báo QA.

## W3 — Điền sáu field từng bài (sau Knowledge QA)

Chỉ bắt đầu sau khi đã QA/refactor **toàn bộ `.md` trong chương** và readback
PASS. Thực hiện lần lượt theo đúng thứ tự `childs[]`:

### 3.1. Difficulty

Chọn đúng một trong ba enum từ nội dung **sau QA**:

- `BASIC` — kiến thức nền, thuật ngữ, cơ chế cơ bản.
- `INTERMEDIATE` — vận dụng, phối hợp cơ chế, so sánh, đánh đổi.
- `ADVANCED` — cơ chế sâu, ngoại lệ, edge case, hạn chế/kiến trúc và phân tích.

Không tự đồng nhất bài có nhiều chữ hoặc nhiều code với ADVANCED. Không sửa
`status` hay file YAML bài riêng.

### 3.2. Bốn tiêu chí so sánh để frontend dựng bảng sau này

Mỗi child chứa bốn field **chuỗi plain text, không tự dựng bảng Markdown**:

| YAML field | Tên tiêu chí | Cần thể hiện |
| --- | --- | --- |
| `focus` | **Trọng tâm** | Kiến thức/cơ chế chủ đạo phân biệt bài này |
| `problemSolved` | **Vấn đề giải quyết** | Vấn đề cụ thể bài giải quyết/giúp nhận diện |
| `mechanism` | **Cơ chế** | Cách hoạt động, kỹ thuật hoặc nguyên lý then chốt |
| `applicationValue` | **Giá trị ứng dụng** | Lợi ích thực tế, ngữ cảnh hoặc điều kiện áp dụng |

Bốn giá trị phải **phân biệt về ý nghĩa** và có căn cứ từ Markdown thực; câu
ngắn gọn nhưng không vô nghĩa như “hiểu kiến thức”, “áp dụng thực tế”.
So sánh các bài trong chương để nêu được điểm giống/khác mà không bịa thêm.
Không sao chép cùng một bộ tiêu chí cho nhiều bài.

### 3.3. Summary từng bài — cấu trúc 0→1→2→3

`childs[].summary` là một tài liệu Markdown độc lập đúng `menuLevel2`,
**không phải phần tóm tắt toàn chương**, không chèn vào Markdown Knowledge.

Phải có **đúng bốn heading cấp chính** theo thứ tự:

```markdown
# 0. Định hướng học tập

## 1. Mục đích của bài học

**<Tên chính xác của Menu cấp 2>**

<Giá trị học tập và vấn đề thực tế mà bài giúp giải quyết.>

## 2. Những câu hỏi người học phải tự trả lời được

### <Nhóm câu hỏi có ý nghĩa>
1. <Câu hỏi mở về nguyên lý/cơ chế?>
2. <Câu hỏi mở về tình huống áp dụng hay giới hạn?>

## 3. Sau khi học xong, người học phải đạt được điều gì?

| Năng lực | Kết quả mong đợi |
| --- | --- |
| <Năng lực cụ thể> | <Hành động có thể quan sát/kiểm chứng> |
```

- Mục `0` **chỉ có heading**; không thêm đoạn giới thiệu chung chung.
- Mục `1`: tên bài **in đậm và khớp nguyên văn**, nói rõ mục đích học và
  giá trị dựa trên Knowledge đã QA.
- Mục `2`: một hoặc nhiều nhóm `###`, mỗi nhóm chứa numbered list
  **câu hỏi mở có dấu hỏi**, không tự trả lời, không hỏi vượt điều đã dạy;
  không áp quota câu hỏi/nhóm cứng.
- Mục `3`: đúng bảng GFM hai cột `Năng lực` / `Kết quả mong đợi`,
  ghi năng lực có thể kiểm chứng; tránh chỉ “hiểu”/“biết”.
- Không TODO/placeholder trong kết quả thực, copy Summary sang bài khác,
  YAML/JSON bao quanh Summary, hoặc thông tin không dựa trên Markdown.
- Nếu Markdown vừa refactor, `summary` phải khớp bản nội dung **cuối cùng**,
  giữ độ sâu cần thiết và nội dung hữu ích.

### 3.4. Giá trị có sẵn

Nếu một field đã có nội dung **đúng, đầy đủ, vẫn phù hợp sau QA**, giữ nguyên.
Nếu dữ liệu hiện hữu không đúng/không còn phù hợp, mâu thuẫn với nguồn hoặc
không rõ quyền sửa, báo `BLOCKER: STEP6_AUTHORED_CONFLICT` cho Prime trước khi
thay. Không ghi đè mù Summary hoặc field do tác giả đã chỉnh.

## W4 — Related theo chapter (sau khi QA xong Knowledge)

Đọc lại **Markdown cuối cùng sau QA** và metadata của mọi bài trong chương.
Đối chiếu với **toàn bộ câu hỏi Quiz, Interview và Case Study** thuộc module.
Chỉ liên kết khi Knowledge của bài thực sự dạy hoặc giải thích được
khái niệm/cơ chế mà câu hỏi hoặc tình huống đang kiểm tra. Không ép mỗi
câu có link, không ép quota links; nhiều chương có thể cùng đề xuất link
cho một item. Worker chỉ được dùng `childs[].slug` thuộc chương đang giao,
không dùng slug chương, title, ID tự chế, hoặc slug bài thuộc chương khác.

Ghi ba file `RELATED_FOLDER/{quiz,interview,casestudy}.yml`, mỗi file
theo **cùng một schema**:

```yaml
groups:
  - groupID: 1
    items:
      - index: 0
        readmeRelated:
          - overview-001
          - overview-002
      - index: 2
        readmeRelated:
          - overview-003
  - groupID: 2
    items:
      - index: 0
        readmeRelated:
          - overview-004
```

- `groupID` phải khớp Assessment, `index` là index **0-based bên trong group**,
  không phải số thứ tự toàn module. Có thể bỏ qua item không liên quan.
- Mỗi `readmeRelated` của một item chứa **ít nhất một slug cấp 2 thật** của
  chính chương này, không trùng; không dùng `readmeRelated.anchorList` ở
  file đề xuất (chỉ file tổng sau merge mới có `anchorList`).
- Nếu toàn bộ assessment của **một loại** không có liên kết với chương,
  file tương ứng **bắt buộc** ghi `groups: []` thay vì để trống.
- Mỗi file chỉ có root `groups`; không thêm status hay chú thích giả.
  Đảm bảo mọi group/item được kê đều có thật trong YAML tổng. Không sửa
  câu hỏi, đáp án, explanation, groupID, index hoặc bất kỳ data khác.
- Nếu phát hiện vấn đề sai chuyên môn trong STEP 5, báo Prime review thay
  vì tự sửa file tổng. Chưa thể kiểm tra đầy đủ → BLOCKER, **không ghi
  `WRITTEN`**.

## W5 — Ghi, readback và bảo toàn dữ liệu

1. Đối chiếu snapshot và quyền sở hữu. Mở lại `CHAPTER_YAML` bản **mới nhất**
   trước khi ghi, kiểm tra đúng một chapter, slug, title, thứ tự children
   và các field; không phục hồi snapshot đã lỗi thời.
2. Thay **chỉ sáu field** của đúng `childs[]` trong `CHAPTER_YAML`,
   giữ nguyên `childs[].status`, `slug`, `title` và YAML bài riêng.
3. Serialize YAML UTF-8 an toàn (đối với Markdown dài trong `summary` dùng
   block scalar), không làm hỏng multiline, dấu tiếng Việt hay dấu `:`
   trong ví dụ. Không ghi `summary` vào `.md`.
4. Parse/readback toàn bộ `CHAPTER_YAML`, kiểm tra duplicate key, chỉ có
   một chương, danh sách child không đổi, enum valid, bốn tiêu chí nonblank
   và Summary đúng bốn mục/bảng. So sánh identity và mọi field bất biến
   với snapshot.
5. Parse/readback **ba file Related** sau khi ghi, kiểm nội dung, slug theo
   đúng chapter, `(groupID,index)` khớp từng Assessment, không trùng và
   không có file trống (không liên quan vẫn phải là `groups: []`).
   Re-read tất cả Markdown sau QA để bảo đảm link không stale.
6. Nếu có write conflict, hỏng YAML hoặc readback mismatch → BLOCKER và
   báo Prime; **không đổi `CHAPTER_STATUS` thành `WRITTEN`**.
7. **Chỉ sau khi toàn bộ `.md`, `CHAPTER_YAML` và ba Related YAML PASS**, sửa duy nhất
   `CHAPTER_STATUS.status: WRITTEN`; parse/readback status, bảo đảm không
   sửa field khác. Nếu chưa hoàn thành giữ `status: ""` và báo BLOCKER.
   Không chạy script `merge_menu.py`, `merge-readme-related.py`,
   `export-casestudy-quiz-interview.py` hoặc `delete_temp_split_menu.py`;
   đây là quyền Prime.

## W6 — REPORT và SLEEPING

Gửi Prime:

- `STATUS=COMPLETED/BLOCKER/FAILED`, `MODULE_LOCATION`, `LANG`,
  `SERVICE_NAME`, `CHAPTER_INDEX`, `CHAPTER_SLUG`,
  `CHAPTER_YAML`, `CHAPTER_STATUS`,
  `SPECIAL_NOTE=APPLIED/EMPTY/CONFLICT`, `CONTEXT_QA`.
- `KNOWLEDGE_QA`: số Markdown đã đọc đầy đủ; danh sách bài giữ nguyên và
  bài refactor + lý do; exact readback; điểm trùng lặp được xử lý.
- `DIFFICULT`: mỗi slug và enum + lý do dựa trên nội dung đã QA.
- `COMPARISON_FIELDS`: mỗi slug có đủ bốn field, không placeholder,
  có khả năng so sánh toàn chương.
- `SUMMARY_QA`: mỗi slug có 4 mục, tên bài chính xác, câu hỏi mở và bảng
  năng lực; nhất quán với Markdown sau refactor.
- `RELATED_QA`: tên và readback của ba Related YAML, số item được xét,
  số link có bằng chứng theo loại, danh sách `(groupID,index,slug)`,
  `groups: []` khi thật sự không có link; không còn BLOCKER.
- `CHAPTER_YAML_READBACK`, `CHAPTER_STATUS=WRITTEN/EMPTY`,
  `OUT_OF_SCOPE_UNCHANGED`, `OWNERSHIP_RELEASED`, `BLOCKERS`.

`COMPLETED` chỉ có nghĩa **một chapter đã QA/refactor, metadata + ba
Related YAML của chương đã ghi/QA và `CHAPTER_STATUS.status = WRITTEN`**;
chưa có nghĩa STEP 6
toàn module hoàn thành. Release và trở về SLEEPING/Idle; không tự nhận chương
khác, tự merge/cleanup hoặc tự checkpoint.
