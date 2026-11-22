# STEP_6_NEW — PRIME ONLY: QA Knowledge, Related, Phase 5 và xuất Assessments

## Mục tiêu

STEP 6 NEW tiếp nhận **toàn bộ công việc QA/refactor Knowledge và sáu
metadata từng bài từ workflow QA cũ**, đồng thời mỗi Worker chương
**xét Related cho Quiz, Interview và Case Study**. Sau tất cả chương,
Prime ghép Related, nâng ba status Assessment lên **Phase 5**, xuất ba
YAML chính thức và dọn staging. Không dùng Google Sheets hoặc Gradle.

- **Một job = một Menu cấp 1** (một chương). Worker đọc đầy đủ và QA/refactor
  mọi Markdown bài học của chương để kiểm soát độ chính xác, chiều sâu và trùng
  lặp. Bài đã tốt thì giữ nguyên byte.
- Prime chạy `script/module/step6/split_menu.py` để tách từng chương từ
  `content/knowledge/<lang>/menu-detail-status.yml` ra `temp/step6/`.
- Worker điền metadata **từng bài trong file YAML riêng của chương**:
  `difficult`, `focus`, `problemSolved`, `mechanism`,
  `applicationValue`, `summary`; sau khi QA/readback PASS, Worker đặt
  `status: WRITTEN` trong **file trạng thái riêng của chương**, nhưng
  **chỉ sau** khi ba file Related của chương đã QA/readback.
- Worker được đọc ba YAML `content/temp/step5/format/*.yml` nhưng
  **không ghi trực tiếp vào đó**. Chỉ sửa ba file `readme-related/<chapter-slug>/*.yml`
  do script khởi tạo STEP 5 tạo sẵn.
- Bốn trường `focus`, `problemSolved`, `mechanism`, `applicationValue`
  cung cấp dữ liệu so sánh giữa các bài; frontend có thể dựng bảng từ các
  trường này khi cần.
- Khi tất cả status chương đều `WRITTEN` và Prime QA PASS, chạy
  `script/module/step6/merge_menu.py` để ghép lại `menu-detail-status.yml`.
- Sau Knowledge merge, Prime chạy `merge-readme-related.py` để ghép đúng
  `readmeRelated.anchorList` vào ba `format/*.yml` và **Prime nâng Phase 5**.
  Worker chương **không được** đánh dấu Phase 5.
- Cuối cùng Prime chạy `export-casestudy-quiz-interview.py` để copy
  **nguyên byte** sang `content/{quiz,interview,casestudy}/<lang>/*.yml`.
  Chỉ sau export/readback PASS mới chạy `delete_temp_split_menu.py`
  để cleanup STEP 6 staging và STEP 5 staging. Không tự xóa trước.

## 0. Prime preflight và phạm vi

1. Đọc `GENERAL_AGENT_RULES.md` và rules chung về Worker/QA/ownership phù hợp,
   cùng `STEP_6_NEW.md` và `worker/STEP_6_WORKER_NEW.md`. Phân công NORMAL
   tối đa 3 Worker theo pool hiện hành, SPECIAL chỉ theo chỉ định người dùng;
   một chapter/Worker/lượt, ưu tiên reuse Worker SLEEPING.
2. Xác minh đúng `<MODULE_LOCATION>` nằm trong `java-learning/learning-platform-data/module/`,
   `module_activate.json.isModule = true`, có `module-info.json`; chọn một
   ngôn ngữ đã được module khai báo ở `MODULE_LANGUAGE.VALUE`.
3. **Prime tự đọc nội dung** `SERVICE_NAME.VALUE`,
   `SERVICE_NAME_DESCRIBE.VALUE`, `SPECIAL_NOTE.VALUE` từ `module-info.json`.
   Truyền nguyên văn cả ba giá trị đến Worker mỗi lần giao; `SPECIAL_NOTE`
   có thể rỗng hoặc nhiều dòng. Không giao file metadata cho Worker.
4. STEP 4 phải đã hoàn tất `refresh_menu_status.py --verify`: mọi bài đều có
   `status: WRITTEN` và Markdown không rỗng, chapter/slug/title đúng Menu.
   Không tự reset status, tự sinh Markdown mới hay sửa bài thuộc module khác.
   **STEP 5 NEW phải hoàn thành**, `status/quiz.yml = Phase 3`,
   `status/interview.yml = Phase 4`, `status/casestudy.yml = Phase 4`,
   cả ba `format/*.yml` có `index` 0-based trong từng group và
   `readmeRelated.anchorList: []`.
5. Đọc `content/knowledge/<lang>/menu.yml`,
   `menu-level-1-slug.yml`, `menu-detail-status.yml` và cặp `.yml`/`.md` của
   mỗi bài. Đối chiếu thứ tự, chapter index, slug/identity chính xác.
   `menu-detail-status.yml` phải có các field:
   `difficult`, `focus`, `problemSolved`, `mechanism`,
   `applicationValue`, `summary`. Nếu cấu trúc không hợp lệ hoặc thiếu
   field bắt buộc → **BLOCKER: STEP6_SCHEMA_INVALID**; không tự sửa schema.
6. **Chỉ Prime chạy SPLIT**, sau khi preflight PASS. Script xác minh tất cả
   lesson đã `WRITTEN`, cấu trúc và danh tính chapter, rồi sinh staging theo
   `SERVICE_NAME` và `lang`. Nếu staging đã tồn tại từ một lượt đang chạy,
   script chỉ xác minh rồi **tiếp tục**, không ghi đè nội dung Worker.
   `manifest.json` ghi checksum bản Knowledge và fingerprints không-Related
   của ba assessments; phát hiện nguồn bị thay đổi bất hợp lệ thì BLOCKER.

## 1. Split — tạo file theo từng chương

Từ root `java-learning`, Prime chạy:

```powershell
# Chỉ kiểm tra, không tạo staging.
python script/module/step6/split_menu.py --module "<MODULE_LOCATION>" --lang vi --dry-run

# Tách các chương để giao Worker.
python script/module/step6/split_menu.py --module "<MODULE_LOCATION>" --lang vi
```

Staging được cách ly theo `SERVICE_NAME` và `lang`, không trộn các module:

```text
temp/step6/<SERVICE_NAME>/<lang>/
  manifest.json
  1-overview.yml
  1-overview-status.yml
  2-application.yml
  2-application-status.yml
```

Mỗi `<index>-<chapter-slug>.yml` giữ **toàn bộ dữ liệu chương** trong
`menu:` gồm đúng một chapter, đúng `slug`/`title`/`childs`/thứ tự từ nguồn;
script sao chép phần YAML chương mà không biên tập lại nội dung của Worker.
Mỗi `<index>-<chapter-slug>-status.yml` có đúng một field:

```yaml
status: ""
```

File status này là **tiến độ xử lý chương trong STEP 6**; không liên quan
`childs[].status: WRITTEN` của STEP 4. `manifest.json` lưu index/slug/
identity và checksum nguồn để phát hiện thay đổi ngoài dự kiến.
Ba file Related của mỗi chương đã được tạo rỗng tại
`<MODULE_LOCATION>/content/temp/step5/readme-related/<chapter-slug>/`
trong STEP 5, **không phải trong `temp/step6`**.

## 2. Prime giao Worker theo chương

Prime đọc manifest và lập ledger **một job = một chương**, ánh xạ chapter
index (1-based), slug, title và folder Knowledge tương ứng
`content/knowledge/<lang>/<index>.<chapter-slug>/`. Một file YAML riêng và
một file status riêng được giao cho đúng một Worker; các Worker có thể
**ghi song song** mà không sửa cùng một file YAML.

Handoff mẫu; mọi placeholder phải thay bằng giá trị hoặc nội dung thật:

```text
MODULE_LOCATION=<ABSOLUTE_MODULE_LOCATION>
LANG=<lang>
SERVICE_NAME=<nguyên nội dung SERVICE_NAME.VALUE>
SERVICE_NAME_DESCRIBE=<nguyên nội dung SERVICE_NAME_DESCRIBE.VALUE>
SPECIAL_NOTE=<nguyên văn SPECIAL_NOTE.VALUE; có thể rỗng hoặc nhiều dòng>
CHAPTER_INDEX=<số thứ tự chapter, bắt đầu từ 1>
CHAPTER_SLUG=<slug đã xác minh>
CHAPTER_TITLE=<title đã xác minh>
CHAPTER_YAML=<java-learning>/temp/step6/<SERVICE_NAME>/<lang>/<index>-<slug>.yml
CHAPTER_STATUS=<java-learning>/temp/step6/<SERVICE_NAME>/<lang>/<index>-<slug>-status.yml
KNOWLEDGE_FOLDER=<ABSOLUTE_MODULE_LOCATION>/content/knowledge/<lang>/<index>.<slug>/
ASSESSMENTS=<MODULE_LOCATION>/content/temp/step5/format/{quiz,interview,casestudy}.yml
RELATED_FOLDER=<MODULE_LOCATION>/content/temp/step5/readme-related/<CHAPTER_SLUG>/
READ=<CHAPTER_YAML>,<CHAPTER_STATUS>,<danh sách đủ lesson .yml và .md trong KNOWLEDGE_FOLDER>,<ASSESSMENTS>,<RELATED_FOLDER>
WRITE=<CHAPTER_YAML>,<CHAPTER_STATUS>,<danh sách đủ lesson .md của chapter>,<RELATED_FOLDER>/quiz.yml,<RELATED_FOLDER>/interview.yml,<RELATED_FOLDER>/casestudy.yml
INSTRUCTIONS=<java-learning>/learning-platform-data/module-generate-agent/worker/STEP_6_WORKER_NEW.md
```

Worker chỉ được refactor đúng Markdown trong folder được giao, điền sáu
field trong `childs[]` của **CHAPTER_YAML**. Giữ `slug`, `title`,
`childs[].status`, danh sách/thứ tự bài và YAML riêng của từng bài.
Worker **không đọc/ghi `menu-detail-status.yml` gốc**, `manifest.json` hoặc
file staging của chương khác. Worker ghi ba Related files của chương:

```yaml
groups:
  - groupID: 1
    items:
      - index: 0
        readmeRelated:
          - overview-001
          - overview-003
```

`groupID` của assessment bắt đầu từ 1; `index` của item bắt đầu từ
**0 trong từng group**. Slug chỉ được thuộc **chính chương đó**, đối chiếu
với `menu-detail-status.yml` và Markdown đã QA; không tự tạo ID hoặc gán
liên kết theo keyword chung. Nếu không tìm thấy liên kết cho một loại,
file tương ứng phải có **`groups: []`** sau khi xét toàn bộ assessment,
không được để file rỗng hay tự sinh liên kết.

Sau khi đã QA/refactor tất cả Markdown, điền metadata và ba file Related,
parse YAML, exact readback PASS, Worker đổi **duy nhất `CHAPTER_STATUS.status`** từ `""` thành
`WRITTEN`. Nếu chưa hoàn tất hoặc có BLOCKER, giữ status rỗng. Prime theo dõi
file status và readback để điều phối; không dựa trên báo cáo Worker thay cho
kiểm tra file.

## 3. QA/refactor Knowledge toàn chương

Worker phải **đọc đầy đủ toàn bộ Markdown trong chương trước khi refactor**;
không chỉ xem title hay summary. Đối chiếu:

- Chính xác về kiến thức, thuật ngữ, cơ chế, ví dụ/code/stdout, giới hạn và
  trade-off; không bịa các kết quả chưa chạy hoặc API không có bằng chứng.
- Bố cục Markdown dễ học, code fence/bảng/link đúng, bài đủ chiều sâu và tự
  đứng độc lập trong phạm vi hợp lý.
- Trùng lặp gây hại giữa các bài: chỉ giữ một nơi giải thích trọng tâm,
  cho phép các bài khác nhắc lại ngắn hoặc áp dụng; không xóa chiều sâu để
  giảm lặp và không ép mọi bài vào khuôn WHAT/WHY/HOW.
- `SPECIAL_NOTE` Prime cung cấp phải được tôn trọng nguyên văn. Nếu yêu cầu
  vượt bằng chứng hoặc xung đột phạm vi, báo BLOCKER, không tự bịa kiến thức.
- Bài đã QA tốt: **không ghi lại file**. Bài cần sửa: chỉnh trực tiếp đúng `.md`
  được giao, readback nguyên văn, QA lại toàn chương; không sinh file mới.

Không đánh dấu STEP 6 hoàn tất nếu bất kỳ bài nào chưa được đọc/QA hoặc còn
vấn đề nội dung. Bài mới ghi ở STEP 4 có `status: WRITTEN` vẫn cần QA STEP 6.

## 4. Metadata STEP 6 NEW trong file YAML chương

Mỗi `menu[0].childs[]` trong `<index>-<chapter-slug>.yml` có các field
sau (các field `slug`/`title`/`status` do STEP 3/4 quản lý,
Worker **không sửa**):

```yaml
menu:
  - slug: overview
    title: Tổng quan
    childs:
      - slug: overview-001
        title: "Data Oriented Programming là gì?"
        status: WRITTEN
        difficult: BASIC
        focus: "Các nguyên tắc tổ chức dữ liệu và hành vi"
        problemSolved: "Giảm phụ thuộc giữa dữ liệu và thao tác"
        mechanism: "Tách dữ liệu bất biến khỏi các phép biến đổi"
        applicationValue: "Giúp mô hình miền dễ kiểm tra và mở rộng"
        summary: |-
          # 0. Định hướng học tập

          ## 1. Mục đích của bài học

          **Data Oriented Programming là gì?**

          Giải thích mục tiêu học dựa trên nội dung bài.

          ## 2. Những câu hỏi người học phải tự trả lời được

          ### Nguyên lý
          1. Cách tiếp cận này khác gì OOP?

          ## 3. Sau khi học xong, người học phải đạt được điều gì?

          | Năng lực | Kết quả mong đợi |
          | --- | --- |
          | Nhận diện cách tổ chức dữ liệu | Giải thích được khi nào cần áp dụng |
```

Giá trị trong ví dụ chỉ minh họa schema; Worker viết theo Markdown thật, không
sao chép nội dung mẫu.

| Field | Tiêu chí hiển thị | Quy tắc viết |
| --- | --- | --- |
| `difficult` | Độ khó | Chọn `BASIC` / `INTERMEDIATE` / `ADVANCED` dựa trên Markdown **sau QA** |
| `focus` | Trọng tâm | Kiến thức/cơ chế trọng tâm riêng của bài |
| `problemSolved` | Vấn đề giải quyết | Vấn đề mà bài này giúp nhận diện hoặc giải quyết |
| `mechanism` | Cơ chế | Nguyên lý, các bước hoạt động, cách thức kỹ thuật được giải thích |
| `applicationValue` | Giá trị ứng dụng | Tình huống áp dụng, giá trị thực tế và điều kiện áp dụng |
| `summary` | Summary từng bài | Markdown **bốn mục 0→1→2→3** theo cấu trúc quy định |

Bốn tiêu chí so sánh phải **ngắn gọn, cụ thể, không trùng nhau về ngữ nghĩa,
không chung chung**, nhưng đủ ngữ cảnh để frontend về sau dựng một bảng
`N+1` cột từ tất cả bài trong chương. Đây là **dữ liệu so sánh có cấu trúc**,
không phải một bảng Markdown đã render.

### Summary từng bài

`summary` của từng bài là một tài liệu Markdown **độc lập**, theo đúng
`menuLevel2`, với các yêu cầu:

1. `# 0. Định hướng học tập` — **chỉ có heading**, không thêm prose khuôn mẫu.
2. `## 1. Mục đích của bài học` — tên bài cấp 2 **in đậm, khớp nguyên văn**,
   nói rõ lý do học, vấn đề và giá trị.
3. `## 2. Những câu hỏi người học phải tự trả lời được` — ít nhất một nhóm
   `###` gồm câu hỏi **mở**, dạng numbered list, có dấu hỏi, không tự đưa đáp án
   hoặc vượt quá nội dung đã dạy.
4. `## 3. Sau khi học xong, người học phải đạt được điều gì?` — đúng bảng GFM
   hai cột `Năng lực` và `Kết quả mong đợi`, ghi hành động có thể kiểm chứng,
   không chỉ ghi “hiểu/biết”.

Không placeholder/TODO, không bịa, không dùng cùng một Summary cho các bài.
Summary **phải cập nhật tương ứng sau khi Markdown bị refactor**. Đảm bảo
Markdown đầy đủ, đúng chủ đề, UTF-8 và dung lượng hợp lý.

Nếu giá trị STEP 6 đã có và vẫn đúng với Markdown sau QA, **giữ nguyên**.
Nếu đã có dữ liệu tác giả khác hoặc Summary stale/xung đột, báo BLOCKER và
xin Prime xử lý đúng quyền, không overwrite mù. Việc điền field phải giữ
nguyên `status`, `slug`, `title`, số lượng và thứ tự các bài trong chương.

## 5. Prime QA, Merge, Export, Cleanup và nghiệm thu

1. Sau mỗi Worker, Prime đọc đúng `CHAPTER_YAML` và `CHAPTER_STATUS` được giao,
   đối chiếu chapter/lesson identity, nội dung sáu field, barem Summary,
   Markdown và ba file Related đã readback, `groupID/index`, slug thuộc
   chương, không duplicate, `groups: []` hợp lệ, tuân thủ SPECIAL_NOTE.
   `CHAPTER_STATUS.status`
   chỉ được là `WRITTEN` nếu toàn chương QA PASS; `childs[].status` vẫn là
   `WRITTEN` của STEP 4, không được dùng thay trạng thái của chapter.
2. Khi **tất cả file `*-status.yml` trong manifest đều `WRITTEN`**, ledger
   của Prime có QA PASS và không còn Worker ACTIVE/BLOCKER, Prime chạy MERGE:

   ```powershell
   python script/module/step6/merge_menu.py --module "<MODULE_LOCATION>" --lang vi --dry-run
   python script/module/step6/merge_menu.py --module "<MODULE_LOCATION>" --lang vi
   ```

   Merge đối chiếu đầy đủ index/slug/title/thứ tự/lesson status, yêu cầu sáu
   field có dữ liệu hợp lệ và Summary đúng barem; so checksum
   `menu-detail-status.yml` gốc với thời điểm SPLIT. Nếu nguồn bị sửa ngoài
   dự kiến, thiếu file/status hoặc kết quả sai → **BLOCKER**, không ghi một
   phần. MERGE ghi file tổng hợp an toàn, exact readback rồi lưu
   `merged.json` trong staging. **MERGE không xóa staging**.
3. Prime đọc lại `menu-detail-status.yml` mới, đối chiếu **toàn bộ chương** và
   số bài, trường nội dung, identity, trạng thái. Sau đó merge Related bằng:

   ```powershell
   python script/module/step6/merge-readme-related.py --module "<MODULE_LOCATION>" --lang vi --dry-run
   python script/module/step6/merge-readme-related.py --module "<MODULE_LOCATION>" --lang vi
   ```

   Script đọc 100% Related proposals đã hoàn thành, kiểm slug hợp lệ,
   `(type,groupID,index)` tồn tại, loại duplicate, ghép theo thứ tự chương.
   **Chỉ field `readmeRelated.anchorList` được thay đổi** trong ba YAML
   `format`. Script không được tự thay `answer`/`explanation`/`knowledge`/
   `resolve`/`groupName`/`index`. Ba `status` do **Prime** cập nhật
   thành `Phase 5` **chỉ sau QA/readback merge PASS** (Quiz Phase 3→5,
   Interview/Case Study Phase 4→5). Có lỗi thì giữ trạng thái trước và
   phục hồi output khi có thể; không cho Worker tự đánh dấu Phase 5.
4. Khi cả ba Phase 5 PASS, Prime xuất đúng byte dữ liệu:

   ```powershell
   python script/module/step6/export-casestudy-quiz-interview.py --module "<MODULE_LOCATION>" --lang vi --dry-run
   python script/module/step6/export-casestudy-quiz-interview.py --module "<MODULE_LOCATION>" --lang vi
   ```

   Đích: `content/quiz/vi/quiz.yml`, `content/interview/vi/interview.yml`,
   `content/casestudy/vi/casestudy.yml`. Nguồn là bản `format` đã merge.
   Copy **byte-for-byte**, không đổi schema/serialize; kiểm SHA/readback.
   Nếu đích tồn tại với nội dung **khác**, exporter BLOCKER; chỉ Prime được
   phép chạy lại với `--replace-existing` **khi đã xác minh/cho phép thay thế**.
   Không ghi file đích khác, không import DB.
5. **Sau khi xuất thành công toàn bộ ba loại**, chạy script dọn staging:

   ```powershell
   python script/module/step6/delete_temp_split_menu.py --module "<MODULE_LOCATION>" --lang vi --dry-run
   python script/module/step6/delete_temp_split_menu.py --module "<MODULE_LOCATION>" --lang vi
   ```

   Script xác minh Knowledge merge, tất cả Related, ba `Phase 5`, ba file
   đích **trùng byte** rồi mới dọn **đúng** `temp/step6/<SERVICE_NAME>/<lang>/`
   và `<MODULE_LOCATION>/content/temp/step5/`. File lạ/xung đột → BLOCKER,
   không đụng module khác. Bảo toàn file chính thức và bài Knowledge.
6. Báo cáo `MODULE_LOCATION`, `LANG`, `TOTAL_CHAPTERS`, `TOTAL_LESSONS`,
   `KNOWLEDGE_REVIEWED`, `KNOWLEDGE_CHANGED`, `DIFFICULTY_QA`,
   `COMPARISON_FIELDS_QA`, `SUMMARY_QA`, `ALL_CHAPTER_STATUS_WRITTEN`,
   `MERGE_READBACK`, `RELATED_QA`, `PHASE5_READBACK`, `EXPORT_EXACT_BYTES`,
   `CLEANUP`, `OWNERSHIP`, `BLOCKERS`.
   Chỉ cập nhật `module-info.json.CURRENT_STEP.VALUE = "6"` khi toàn bộ
   gate PASS và quy trình checkpoint NEW được cho phép, không ghi lùi.

STEP 6 **không tạo mới câu hỏi**: chỉ bổ sung Related cho ba assessment
đã được STEP 5 tạo, xuất bản cuối; không thay nội dung nghiệp vụ, không
chạy Java/STEP 8, không commit/push hoặc tự chuyển bước.
