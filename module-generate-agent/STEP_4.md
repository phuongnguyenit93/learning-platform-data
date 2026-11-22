# STEP 4 — PRIME ONLY: Soạn Knowledge local và xác minh đủ bài (KHÔNG PUBLISH)

## Mục tiêu / quyền sở hữu

**STEP 4 chỉ tạo `rowXX-info.yml` và `rowXX.md`, giao Worker viết nội dung vào Markdown, xác minh đủ tất cả bài rồi checkpoint STEP 4.** Không đồng bộ Knowledge lên Google Sheets C:N, không ghi Difficulty O hay Summary AC; không QA/refactor nội dung. **STEP 5** mới review/refactor Markdown và PUBLISH `rowXX.md → C:N`, `difficult → O`, Summary → AC.

Worker STEP 4 không dùng Google Sheets API, không gọi Gradle task, không sửa file khác hoặc status tiến độ chung. Prime điều phối theo `GENERAL_AGENT_RULES.md`, `rules/PRIME_RULES.md`; sau khi hoàn thành toàn STEP mới cập nhật `master.json.CURRENT_STEP.VALUE="4"` và **online** `J3="STEP 4"` bằng quy trình checkpoint hiện có. **Không nhầm việc checkpoint J3 với ghi Knowledge C:N.**

## 1. Ba task (100% code, không AI)

1. `prepareStep4Knowledge` (**module-scoped**) — Prime đọc đúng tab/gid/I3, `B1`, Special Note và A/B Menu đã có ID từ STEP 3; tạo `manifest.yml`, `rowXX-info.yml`, `rowXX.md` trong `learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/`. File cũ có nội dung giữ nguyên, không reset status. Info mới không có Summary.
2. `refreshStep4KnowledgeStatus` (**root-only, local**) — sau mỗi đợt Worker hoặc restart, lấy status từ `rowXX-info.yml`/file Markdown và đồng bộ manifest. Không cần URL/gid/ADC, không truy cập Google Sheets.
3. `verifyStep4Knowledge` (**root-only, local**) — sau khi tất cả Worker báo hoàn thành: tự refresh và **đòi hỏi mọi bài đều không PENDING**, file Markdown tồn tại, không rỗng, định dạng info/row hợp lệ, danh sách con của manifest nhất quán, nội dung Markdown vừa giới hạn kỹ thuật tối đa 12 ô × 30.000 UTF-16 units/ô. Trả `READY` hoặc fail. **Không đọc/ghi C:N, không tạo/cập nhật nội dung Knowledge.**

**Đã gỡ `publishStep4Knowledge`** khỏi Gradle: không được gọi legacy publisher dù DRY_RUN/APPLY. Cơ chế tạo Fragment/Sheet upload nay thuộc `publishStep5Summary` của STEP 5.

### Lệnh Prime

```powershell
# Một lần đầu STEP 4, cần URL/gid và đúng module Gradle.
.\gradlew.bat :<MODULE_GRADLE_PATH>:prepareStep4Knowledge -PfileUrl="<SHEET_URL>" -PsheetID=<GID> -PsheetName="<SHEET_NAME>" -PsheetMode=APPLY

# Sau từng đợt Worker và sau Prime restart: hoàn toàn local.
.\gradlew.bat :refreshStep4KnowledgeStatus -PsheetName="<SHEET_NAME>"

# Sau khi mọi row đã WRITTEN: hoàn toàn local, chỉ check.
.\gradlew.bat :verifyStep4Knowledge -PsheetName="<SHEET_NAME>"
```

Nếu module có `USE_TASK=FALSE`, chạy `:prepareStep4Knowledge` ở Gradle root
với cùng các tham số `-PfileUrl`, `-PsheetID`, `-PsheetName`, `-PsheetMode=APPLY`.
Task root xác minh `I3` và suy ra thư mục module từ chính tab đã chọn;
không cần bật `USE_TASK` hoặc đổi `master.json` để PREPARE.

Không chạy STEP 5 hoặc commit/push nếu chưa có ủy quyền riêng.

## 2. File và trạng thái

```text
learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/
  manifest.yml
  row21-info.yml
  row21.md
  row22-info.yml
  row22.md
  ...
```

Ví dụ `row21-info.yml`:

```yaml
row: 21
topic: "Java"
specialNote: "Áp dụng ví dụ Java 17+"
menuLevel1: "Class và Object"
menuLevel2: "Class là gì?"
status: ''
```

Worker chỉ được viết `rowXX.md` UTF-8 toàn văn, **không tự chia C:N**, sau khi lưu/readback thành công mới đổi **duy nhất `status`** sang `WRITTEN`. Không tạo Summary. Các field `summary` legacy nếu tồn tại trong info cũ vẫn giữ nguyên, không tự migrate/xóa/ghi đè. `manifest.yml` lưu `spreadsheetId`, `gid`, `sheetName`, `moduleLocation`, `chapters:[{parentRow,title,childRows}]`, `rows:[{row,parentRow,info,markdown,status}]`.

- `PENDING`: info `status` trống; file Markdown có thể đang soạn dở, **không coi hoàn tất**.
- `WRITTEN`: Worker lưu xong Markdown, đánh dấu hoàn thành nội dung local; **đây là trạng thái chuẩn để checkpoint STEP 4 mới**.
- `UPLOADED`/`SKIPPED_EXISTING`: chỉ là trạng thái legacy từ workflow trước; REFRESH/VERIFY cho phép khi Markdown hợp lệ, **không tự tạo trạng thái này nữa**. Nếu muốn đồng bộ Sheet, dùng STEP 5 và xử lý khác nội dung theo rule FILL-ONLY.

## 3. Điều phối Prime

1. Đọc General, toàn bộ rules, module info, STEP 4 Prime + Worker. Xác minh sheet URL, tab title thật, gid, I3, master.json; `<SHEET_NAME>` phải là tên tab thật được Google Sheets plugin xác nhận, Windows-safe. Không suy tên từ tên module, không dùng folder khác. PREPARE đọc `B1`, Special Note và Menu A19:B; hàng 20+ theo parent/children, không ghép row/ID thành title.
2. Chạy PREPARE một lần để tạo staging; kiểm tra manifest và các file. Bảo vệ staging hiện hữu, không overwrite Markdown hoặc info người khác.
3. Sau restart hoặc mỗi đợt Worker, chạy REFRESH. Từ manifest đã refresh, giao **một row cho một Worker mỗi lượt**, theo pool Mode A=3 mặc định hoặc Mode B=N user chỉ định; không giao trùng row ACTIVE, tái sử dụng Worker SLEEPING.
4. Handoff đúng ba dòng (Worker chỉ đọc file worker-only và info được giao):
   ```text
   /java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/row21-info.yml
   /java-learning/learning-platform-data/module-generate-agent/temp/<SHEET_NAME>/row21.md
   /java-learning/learning-platform-data/module-generate-agent/worker/STEP_4_WORKER.md
   ```
5. Worker báo DONE thì REFRESH. Không nhận `WRITTEN` nếu chưa có file Markdown hợp lệ. Nếu file trống, status sai, thiếu file hoặc worker còn ACTIVE → BLOCKER. **Không QA chuyên môn/đúng sai Knowledge tại STEP 4**; STEP 5 đảm nhiệm.
6. Khi queue đã hết, chạy `verifyStep4Knowledge`. Chỉ khi `READY`, không còn row PENDING hoặc Worker ACTIVE/blocker, Prime mới cập nhật/readback `master.json.CURRENT_STEP.VALUE="4"` và Google Sheets online `J3="STEP 4"` theo `PRIME_RULES.md §2`.
7. Không PUBLISH C:N, không nhập dữ liệu module, không xóa files temp/legacy, không chỉnh P/Q. STEP 5 sẽ đọc/refactor trực tiếp `rowXX.md` và Gradle PUBLISH lên Sheet sau khi QA.

**Bất biến:** STEP 4 chỉ làm file-first Knowledge authoring + local completeness; **không có task nào của STEP 4 ghi C:N/O/AC**. Nếu người dùng chạy lại PREPARE/REFRESH/VERIFY, không mất nội dung đã viết và không tạo dữ liệu Sheet mới.
