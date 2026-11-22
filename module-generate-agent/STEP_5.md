# STEP 5 — PRIME ONLY: Group folder, Knowledge QA, Difficulty & Summary

## Contract hiện hành

**STEP 5 là file-first cho cả Knowledge review và Summary/Difficulty.** PREPARE/PUBLISH là Gradle **100% code-only, không AI**. Worker QA/refactor nội dung **trong từng file local `rowXX.md` của STEP 4**, không đọc/sửa Knowledge C:N trên Sheet. Worker ghi `GroupX/summary.yml` gồm Summary chương, `markdownSummary` từng bài và `difficult` từng bài. **Prime là người duy nhất gọi task PUBLISH** để đồng bộ file Knowledge → C:N, `difficult` → O, Summary → AC trên Sheet.

STEP 3 đã cấp B-parent filename/C-parent base slug/A-child IDs. STEP 4 đã tạo `learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/manifest.yml`, `rowXX-info.yml` và `rowXX.md`, **VERIFY local thành công rồi checkpoint mà KHÔNG ghi Knowledge C:N**. STEP 5 mới là bước đầu tiên PUBLISH Knowledge lên Sheet; **không** cấp/đổi identity A/B/C, cũng không viết lại Knowledge từ đầu khi không cần refactor. Các `rowXX-info.yml` mới của STEP 4 không chứa field Summary; field `summary` legacy nếu đã có thì giữ nguyên, không dùng làm nguồn STEP 5.

**Mỗi Menu Cấp 1 = một folder `GroupX/` theo thứ tự chapter thực trên Sheet**, không liên quan `groupID` Interview/Quiz/Case Study của STEP 6. Không tạo file assessment trong STEP 5. **Knowledge chỉ tồn tại trong `rowXX.md`**, không sao chép Knowledge vào `summary.yml`.

## 1. Cấu trúc local và ownership

```text
learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/
  manifest.yml
  row21-info.yml
  row21.md                 # Worker STEP 5 review/refactor trực tiếp
  row22-info.yml
  row22.md                 # Worker STEP 5 review/refactor trực tiếp
  ...
  Group1/
    info-group.yml         # Gradle PREPARE, read-only với Worker
    summary.yml            # Gradle tạo skeleton, Worker STEP 5 điền
  Group2/
    info-group.yml
    summary.yml
```

`Group1/info-group.yml` chứa **chỉ metadata** (không có field `summary`, `interview`, `quiz`, `casestudy`):

```yaml
schemaVersion: 1
groupIndex: 1
spreadsheetId: <VERIFIED_SPREADSHEET_ID>
gid: 700001
sheetName: <SHEET_NAME>
moduleLocation: module/...
parentRow: 20
menuLevel1: "Thiết kế Class"
filename: ClassDesign.md
baseId: class-design
children:
  - row: 21
    id: class-design-001
    menuLevel2: "Nguyên tắc thiết kế Class"
  - row: 22
    id: class-design-002
    menuLevel2: "Cohesion và Coupling"
```

`Group1/summary.yml` là **nguồn local duy nhất được Worker STEP 5 chỉnh sửa**:

```yaml
chapter:
  version: 1
  type: LEARNING_ROADMAP
  title: ''
  roadmapHeading: ''
  roadmap: []
  comparisonMarkdown: ''
lessons:
  - row: 21
    id: class-design-001
    difficult: ''
    markdownSummary: ''
  - row: 22
    id: class-design-002
    difficult: ''
    markdownSummary: ''
```

Worker **chỉ điền nội dung** `chapter.title`, `roadmapHeading`, `roadmap`, `comparisonMarkdown`, các `lessons[].markdownSummary` và `lessons[].difficult` (một trong `BASIC/INTERMEDIATE/ADVANCED`); **không sửa** `info-group.yml`, `lessons[].row/id`, `version/type`, số lượng hoặc thứ tự bài. Không thêm các trường dẫn xuất `id/order/title/to` trong `chapter.roadmap`. `markdownSummary` là Markdown **từng bài**, khác với `chapter` là Summary **cả chương**. Không tạo `knowledgeBaseline` vì STEP 4 không upload C:N; metadata legacy đã có field này được giữ nguyên nhưng **không dùng cho phép overwrite**.

## 2. Prime — đầu STEP 5

1. Đọc `GENERAL_AGENT_RULES.md`, toàn bộ `rules/`, `module-generate-info.txt`, file Prime và Worker STEP 5. Xác minh URL/gid/tab/I3, B1, Special Note nguyên văn, `master.json` và checkpoint STEP 4. **Không làm việc nếu STEP 4 chưa VERIFY đủ file Markdown local** hoặc Menu STEP 3 identity sai/trùng. **Không yêu cầu Sheet C:N đã có nội dung.**
2. Prime cấu hình module như STEP 5 cũ: `MODULE_TYPE.VALUE="SERVLET"`, `BUILD_SWAGGER.VALUE="TRUE"` khi cần, không tạo `USE_SWAGGER`. Gradle configuration sync, exact readback `master.json`/properties/Swagger/Application duy nhất; kiểm tra git dirty để không xóa thay đổi ngoài phạm vi. Lỗi → `BLOCKER: MODULE_CONFIG_SYNC_FAILED`, chưa giao Worker.
3. Prime xác minh header `C19:N19 = Câu trả lời`, `O19 = Difficulty`; provision **chính xác AC18=Summary, AC19=Summary YAML** và grid columnCount ≥29 theo quy trình snapshot/metadata/preflight hiện hành. Không sửa Template hoặc nội dung người khác; AC legacy/full-schema có nội dung cần migration với phép riêng, không tự overwrite.
4. Chạy **Gradle root PREPARE** sau khi xác minh `SHEET_NAME`. Task đọc I3 thật từ Sheet, tự xác định module an toàn, đọc A19:C và STEP 4 manifest, kiểm tra row/ID/filename/slug/uniqueness, xác minh các file `rowXX.md` local có nội dung và vừa giới hạn; tạo `Group1/...` đến `GroupN/...`. **Không đọc/đòi C:N Sheet khớp `rowXX.md`; C:N bình thường còn trống.** File info/summary đã có thì bảo toàn nội dung; `summary.yml` cũ thiếu `difficult` chỉ bổ sung field rỗng, giữ `markdownSummary` và Summary chương. Lỗi identity/thiếu Markdown → `BLOCKER: STEP5_GROUP_IDENTITY`.
5. Prime đọc toàn bộ `info-group.yml` và `summary.yml` đã chuẩn bị, lập ledger **một job = một Group = một Menu Cấp 1**. Tuân thủ Mode A tối đa ba Worker ACTIVE+SLEEPING hoặc Mode B=N chỉ khi user yêu cầu, tái sử dụng Worker SLEEPING. Không giao cùng Group đồng thời cho hai Worker.

### Gradle tasks (100% code, không gọi AI)

Từ root repository, thay đúng URL, gid và tên tab; **không cần module USE_TASK=TRUE**:

```powershell
# Đầu STEP 5: chỉ tạo file local, KHÔNG ghi Sheet
.\gradlew.bat :prepareStep5Groups -PfileUrl="<SHEET_URL>" -PsheetID=<GID> -PsheetName="<SHEET_NAME>" -PsheetMode=APPLY

# Sau khi tất cả Group được Worker QA/refactor rowXX.md và điền Summary/Difficulty:
.\gradlew.bat :publishStep5Summary -PfileUrl="<SHEET_URL>" -PsheetID=<GID> -PsheetName="<SHEET_NAME>" -PsheetMode=DRY_RUN
.\gradlew.bat :publishStep5Summary -PfileUrl="<SHEET_URL>" -PsheetID=<GID> -PsheetName="<SHEET_NAME>" -PsheetMode=APPLY
```

Hai task được đăng ký **ở Gradle root**, tự xác minh I3 của URL/gid và tìm module folder; do đó vẫn hoạt động khi module `USE_TASK=FALSE`. Alias module-scoped có sẵn khi module bật `SheetsTaskPlugin`. PREPARE bắt buộc `APPLY` vì tạo file local; PUBLISH có DRY_RUN/APPLY. Không chạy task trên Sheet thật khi chưa có xác minh/ủy quyền trong nhiệm vụ thực tế.

## 3. Prime → Worker: đúng bốn dòng

Prime phải xác định từ Group metadata **chính xác** A/B/C cha, A/B con và **danh sách đầy đủ `rowXX.md` của từng bài**, kèm `Special Note` hai ô đã định vị. Không gửi nội dung/gợi ý Summary cho Worker; Worker **không đọc/ghi C:N/O/AC trực tiếp**.

```text
<LINK_TAB_ĐÃ_XÁC_MINH>
READ=A1,B1,<PARENT_A_B_C>,<CHILD_A_B_ROWS>,<SPECIAL_NOTE_TITLE_CELL>,<SPECIAL_NOTE_VALUE_CELL>,<ALL_ASSIGNED_rowXX.md_PATHS>,/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/GroupX/info-group.yml,/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/GroupX/summary.yml
WRITE=<ALL_ASSIGNED_rowXX.md_PATHS>,/java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/GroupX/summary.yml
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_5_WORKER.md
```

Worker của mỗi Group được quyền **QA/refactor các `rowXX.md` local được cấp**, **điền `difficult` và `markdownSummary` từng bài**, Summary chương vào `GroupX/summary.yml`. **Không ghi C:N, O, AC lên Sheet**, A/B/C identity, nhóm khác, `info-group.yml` hoặc `rowXX-info.yml`. Worker tự đọc toàn bộ file worker-only, không đọc tài liệu Prime/rules/STEP khác.

## 4. Giữ nguyên barem Summary STEP 5 cũ

- **Summary từng bài:** sau QA Knowledge toàn chương, mỗi `lessons[].markdownSummary` là tài liệu Markdown nguyên vẹn có đúng 4 mục 0 → 1 → 2 → 3; mục 1 có tên chính xác B-child in đậm; mục 2 có nhóm câu hỏi mở, không chèn đáp án; mục 3 có bảng hai cột `Năng lực` / `Kết quả mong đợi`; căn cứ Knowledge thực, không placeholder hoặc văn mẫu. Giới hạn ≤30.000 Unicode code points và ≤32.767 UTF-16 units cho một ô AC con.
- **Summary tổng chương:** `chapter` giữ đúng sáu khóa authored-only (`version,type,title,roadmapHeading,roadmap,comparisonMarkdown`). `roadmap` có N mục bằng số bài, **mỗi mục chỉ `description` và `transition`**; N−1 transition là `{description: ...}`, transition cuối là `null`. `comparisonMarkdown` một bảng GFM có **N+1 cột**, ít nhất bốn tiêu chí, không giả link/arrow. Không thêm `id/order/title/to` vào YAML authored; ID/title/order/to được code suy ra từ A/B con khi importer chạy. Toàn YAML `chapter` phải vừa ô AC cha.
- Worker **đọc đủ** `rowXX.md` từng bài, không chỉ tiêu đề; nhận diện trùng lặp không cần thiết trong toàn chương nhưng bảo toàn chiều sâu, tính độc lập, cơ chế, ví dụ, code/stdout, Markdown, Special Note. Bài đã tốt thì giữ nguyên; bài cần refactor thì sửa ngay `rowXX.md` được cấp. `lessons[].difficult` chọn `BASIC`, `INTERMEDIATE`, `ADVANCED` dựa nội dung file sau review. **Worker không ghi O**; task PUBLISH giữ dropdown/format của Sheet.
- File `summary.yml` đã có nội dung authored hợp lệ → Worker có thể giữ nguyên, không sửa cho hay hơn. Nội dung sai/stale/human-owned khác → báo `BLOCKER` và cần quyền xử lý rõ ràng, không overwrite mù. Sau khi Knowledge được refactor, Summary phải cập nhật tương ứng trên đúng quyền Group.

## 5. Prime — QA, PUBLISH và checkpoint

1. Nhận report từng Worker, xác minh toàn bộ `rowXX.md` sau QA/refactor trong Group, `summary.yml` có đúng row/id, đủ N `difficult` và `markdownSummary`, đúng barem 0/1/2/3 và chapter authored-only, comparison GFM N+1 cột. Kiểm tra Menu A/B/C và `info-group.yml` không đổi; phát hiện lỗi trả Worker đúng owner sửa. Worker DONE là **hoàn thành file local**, chưa PUBLISH Sheet.
2. Khi **mọi Group QA PASS**, chạy `publishStep5Summary` DRY_RUN → APPLY. Task chỉ đọc local và WRITE **`rowXX.md` → C:N**, **`lessons[].difficult` → O con**, **`chapter` → AC cha**, **`lessons[].markdownSummary` → AC con**, bằng `RAW`. Task kiểm tra toàn bộ nguồn và mọi C:N/O/AC đích **trước lần ghi đầu**; C:N chỉ ghi khi **toàn hàng còn trống** hoặc giữ nguyên nếu đã có Knowledge **trùng chính xác toàn văn file local**. Nếu C:N có nội dung khác/công thức, `BLOCKER`: **không overwrite theo baseline**. O/AC chỉ fill khi trống hoặc giữ nếu đã khớp. Nếu thay đổi đồng thời → dừng. Mỗi row/ô ghi có readback chính xác. Ghi C:N đủ 12 ô gồm các ô đuôi rỗng để tránh dữ liệu dư; rerun idempotent.
3. **Chỉ khi toàn bộ** Group Knowledge QA, Difficult và Summary local, cùng C:N/O/AC PUBLISH exact readback PASS, không còn worker ACTIVE, blocker hoặc dữ liệu mismatch, Prime mới checkpoint `master.json.CURRENT_STEP.VALUE="5"` và online `J3="STEP 5"` đúng tab/gid/I3 theo `rules/PRIME_RULES.md §2`. Không checkpoint khi chỉ PREPARE hoặc Worker COMPLETED.
4. Không tạo Interview/Quiz/Case Study tại STEP 5. Folder `GroupX` được giữ cho các STEP kế tiếp, nhưng **Group ordinal không đồng nghĩa groupID assessment**. STEP 6/7 giữ nguyên các phase và nguồn/cột hiện hành cho tới khi được thiết kế lại riêng. Không tự commit/push, không đụng Sheet dữ liệu ngoài quyền.
