# STEP 3 — PRIME ONLY: Hai phase tuần tự, Worker có thể tái sử dụng

## Mục tiêu và thứ tự

**STEP 3 gồm đúng hai phase tuần tự, mỗi phase là một lượt giao việc độc lập. Prime được phép dùng lại cùng Worker cho PHASE 2 sau khi PHASE 1 đã hoàn thành, nghiệm thu và release ownership; cũng có thể dùng Worker khác. Không bắt buộc hai Worker khác nhau.** Cả hai phase đều làm việc trực tiếp trên Google Sheets, nhưng có quyền ghi riêng biệt:

- **PHASE 1 — Worker phụ trách Menu:** tạo toàn bộ Menu hai cấp như STEP 3 cũ. A cha = tên Menu Cấp 1; B con = tên Menu Cấp 2. Hàng cha B trống, hàng con A trống, không chạm C. **Logic, nội dung và preflight của PHASE 1 giữ nguyên.**
- **PHASE 2 — Worker phụ trách filename/slug:** đọc **toàn bộ Menu trên cùng tab**, chọn/ghi **B cha = filename `.md`**, **C cha = chapter base slug**; không sửa tên Menu A cha/B con, không ghi A con, không ghi C:N con. Sau khi PHASE 2 QA/readback PASS, **Prime** chạy task code-only `fillModuleLessonIdsFromSheetByLocation` (DRY_RUN → APPLY → readback) để cấp các A-child Knowledge IDs.
- **Chỉ checkpoint STEP 3 sau cả PHASE 1 + PHASE 2 + task ID PASS**. PHASE 1 hoàn thành không được ghi `CURRENT_STEP="3"` hoặc `J3="STEP 3"`.

Các file riêng biệt:
- Prime: `/java-learning/learning-platform-data/module-generate-agent/STEP_3.md` (file này).
- Worker PHASE 1: `/java-learning/learning-platform-data/module-generate-agent/worker/STEP_3_WORKER/STEP_3_WORKER_PHASE_1.md`.
- Worker PHASE 2: `/java-learning/learning-platform-data/module-generate-agent/worker/STEP_3_WORKER/STEP_3_WORKER_PHASE_2.md`.

Prime đọc đầy đủ `GENERAL_AGENT_RULES.md`, **liệt kê/đọc tất cả file trong `rules/`**, `module-generate-info.txt`, `STEP_3.md` và **hai file Worker** trước khi phân công. Worker **chỉ đọc đúng file worker-only của phase được giao**, không đọc STEP Prime, file phase còn lại, General, rules, TXT hoặc lịch sử hội thoại. Khi context bị rút gọn, Prime/Worker đọc lại đúng tài liệu vai trò.

## 1. Bố cục Sheet và quyền sở hữu

| Vùng | PHASE 1 — Worker | PHASE 2 — Worker | Prime task ID |
| --- | --- | --- | --- |
| `C3` + hai ô Special Note | Đọc nguyên văn | Đọc nguyên văn để đặt tên | Không sửa |
| `A18:B19` | Đọc xác minh header | Đọc header | Đọc header |
| `A<PARENT>` | **Tạo tên chương** | Chỉ đọc | Giữ nguyên |
| `B<PARENT>` | Để trống | **Filename `.md`** | Chỉ đọc |
| `C<PARENT>` | Không ghi | **Base slug theo filename** | Chỉ đọc/validate |
| `A<CHILD>` | Để trống | Không ghi | **Tạo ID vào ô còn trống** |
| `B<CHILD>` | **Tạo tên bài** | Chỉ đọc | Chỉ đọc |
| `C:N<CHILD>` | Không ghi | Không ghi | Không ghi |

**Header bắt buộc:** `A18` = Khu vực Menu, `A19` = Menu Cấp 1, `B19` = Menu Cấp 2. Menu bắt đầu hàng **20**, liên tục, không hàng trống/cấp 3. Mỗi hàng cha có A tên, B ban đầu trống; ngay dưới là hàng con có B tên và A trống; chương tiếp theo sát hàng con cuối. **Không ghép cha/con cùng hàng**. `<END>` lấy từ `rowCount` thực tế của tab.

C chapter base ID không phải nội dung Knowledge: `C<PARENT>` chỉ chứa slug; **`C:N<CHILD>` vẫn được để trống cho STEP 4**. ID `A<CHILD>` là canonical anchor ổn định để STEP 4/5/7/9 sử dụng, không phải Markdown filename.

## 2. Prime — preflight chung

1. Từ `module-generate-info.txt` lấy URL và mapping `<TÊN MODULE> sheet id : <GID>`; **sheet id trong mapping là tab gid**, không phải spreadsheet ID. Xác minh tab đúng, `A1`, `B1`, `I3` module path và `master.json`.
2. Xác định **nhãn `Special Note` trong Module Project và ô giá trị ngay dưới cùng cột** (ví dụ K2/K3), kiểm tra duy nhất/đọc được. Giá trị trống hợp lệ; Prime gửi **tọa độ**, không sao chép/tóm tắt/diễn giải nội dung ghi chú cho Worker.
3. Xác minh `A18:B19`, xác định `<END>` bằng metadata `rowCount`, đọc toàn vùng `A20:C<END>` để biết Menu/identity đã tồn tại. Không tự coi dữ liệu đã có là chỗ trống và ghi đè.
4. Tuân thủ worker pool Mode A (tối đa 3 ACTIVE+SLEEPING) hoặc Mode B (N user chỉ định rõ), ưu tiên tái sử dụng Worker SLEEPING phù hợp, **kể cả Worker vừa hoàn thành PHASE 1 để giao PHASE 2** sau khi đã QA/readback và release ownership. Có thể giao Worker khác nếu phù hợp; không bắt buộc tạo thêm Worker. Không giao hai phase song song, không vượt giới hạn pool.

## 3. PHASE 1 — Worker phụ trách, Menu hai cấp (giữ nguyên nghiệp vụ STEP 3 cũ)

1. Chỉ khi toàn bộ vùng Menu `A20:B<END>` thật sự trống, giao **một worker** tạo **toàn bộ Menu** của tab từ nguyên văn `C3` và Special Note. Không chia chương/nhóm cho worker khác.
2. Handoff PHASE 1 **đúng bốn dòng**, không gửi nội dung ô:

```text
<LINK_TAB_ĐÃ_XÁC_MINH>
C3, A18:B19, <SPECIAL_NOTE_TITLE_CELL>, <SPECIAL_NOTE_VALUE_CELL>
A20:B<END_ROW_ĐÃ_XÁC_MINH>
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_3_WORKER/STEP_3_WORKER_PHASE_1.md
```

3. Worker PHASE 1 tự đọc nguyên văn `C3` và hai ô Special Note, soạn Menu, tự QA cấu trúc/chủ đề, preflight, WRITE `A20:B<END>` **chỉ vào ô trống**, exact-readback; báo cáo rồi release/SLEEPING. **File PHASE 1 kế thừa đầy đủ STEP 3 Worker cũ, không mở quyền filename/base ID/Knowledge.**
4. Prime đọc lại **toàn bộ Menu**, xác minh coverage theo C3/Special Note, đúng thứ tự và cấu trúc, metadata ngoài quyền không bị sửa; **PHASE_1_QA/READBACK PASS** mới chuyển sang PHASE 2.
5. Nếu Menu đã tồn tại từ phiên trước, **không giao lại PHASE 1 để ghi đè**. Prime xác minh Menu đó hoàn chỉnh, readback/QA; nếu hợp lệ thì ghi nhận `PHASE_1=UNCHANGED_VERIFIED` và chuyển thẳng sang PHASE 2. Nếu chưa đầy đủ/xung đột → `BLOCKER` và không sửa mù. **Restart sau PHASE 1 không yêu cầu tái sinh Menu.**

## 4. PHASE 2 — Worker phụ trách, filename và base slug toàn tab

1. Sau PHASE 1 PASS, giao **một Worker (có thể là Worker của PHASE 1 đã SLEEPING hoặc Worker khác)** đọc `B1`, `C3`, hai ô Special Note và **toàn bộ `A19:C<END>`**. Không chia theo chapter. Worker PHASE 2 phân biệt hàng cha/con từ cấu trúc A/B và row position do PHASE 1 tạo.
2. Handoff **đúng bốn dòng**:

```text
<LINK_TAB_ĐÃ_XÁC_MINH>
B1, C3, A19:C<END_ROW_ĐÃ_XÁC_MINH>, <SPECIAL_NOTE_TITLE_CELL>, <SPECIAL_NOTE_VALUE_CELL>
<DANH_SÁCH_ĐẦY_ĐỦ_CÁC_Ô_B_C_HÀNG_CHA: B20,C20,B29,C29,...>
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_3_WORKER/STEP_3_WORKER_PHASE_2.md
```

3. Worker 2 đối chiếu **danh sách ô được cấp bao phủ đúng tất cả các hàng cha** trước WRITE; thiếu/thừa → BLOCKER, không tự mở rộng ownership. Worker xem **tên chương và toàn bộ tên bài con** để chọn filename tiếng Anh đại diện cho chương, regex `^[A-Za-z][A-Za-z0-9]*\.md$`, ưu tiên PascalCase. Tên file không được trùng case-insensitive trên tab, không chung chung kiểu `Chapter1.md`, `Topic.md`, không dùng tên Windows reserved. Worker suy ra `C<PARENT>` bằng **cùng quy tắc** `ReadmeSheetImportService.slugFromStem(B-parent-without-md)`: `OOPBasic.md → oop-basic`; kiểm tra slug toàn tab không trùng.
4. **FILL-ONLY cho B/C cha**: hai ô trống → điền mới; đã có filename/base đúng → giữ nguyên; một ô đúng còn một ô trống → chỉ bổ sung ô thiếu tương thích. Mâu thuẫn, formula/chip/note, trùng hoặc filename/base sai → BLOCKER; **không overwrite và không rename nếu A-child IDs đã tồn tại**. Không chạm bất kỳ B con, A con hay C:N con.
5. Prime exact-readback toàn bộ filename/slug B/C cha, kiểm tra uniqueness/sự phù hợp Menu cùng tất cả hàng con, không có ô nào còn thiếu; chỉ khi `PHASE_2_QA/READBACK PASS` mới chạy task ID. Lỗi Phase 2 không quay lại Phase 1; chỉ giao lại Phase 2 cho worker 2 sau khi xử lý blocker an toàn.

## 5. Prime — task cấp Knowledge ID, code-only

**Đây là logic đã có từ STEP 5, chuyển ownership/thời điểm chạy về cuối STEP 3. Không để AI tự sinh/ghi A-child IDs.**

Sau toàn tab B filename và C base slug hợp lệ, không worker đang ghi các ô liên quan, Prime chạy **cùng task** `fillModuleLessonIdsFromSheetByLocation`:

```powershell
.\gradlew.bat :fillModuleLessonIdsFromSheetByLocation -PfileUrl="<SHEET_URL>" -PsheetID=<GID> -PsheetMode=DRY_RUN
.\gradlew.bat :fillModuleLessonIdsFromSheetByLocation -PfileUrl="<SHEET_URL>" -PsheetID=<GID> -PsheetMode=APPLY
```

Task root **tái sử dụng `MenuLessonIdFillService` hiện có**; xác minh module path ở I3 và cấp ID `<chapter-base>-001`, `-002`... **chỉ cho A-child trống**, giữ nguyên ID hợp lệ đã có, không reuse gap khi cần cấp thêm, kiểm tra toàn tab không trùng/không lệch base; readback đầy đủ sau APPLY. Không sửa B/C cha, Menu A cha/B con, Knowledge C:N con. Bất kỳ mismatch, duplicate, write/readback failure → `BLOCKER: LESSON_ID_SYNC`, không checkpoint. Nếu đã có ID hợp lệ toàn bộ, `UNCHANGED` được chấp nhận. Không tự cập nhật C3/Special Note/headers hoặc nhập dữ liệu module ở đây.

**Module-specific alias cũ có thể còn tồn tại để tương thích**, nhưng STEP 3 dùng lệnh root rõ ràng, hoạt động ngay cả khi module `USE_TASK=FALSE`.

## 6. Nghiệm thu và checkpoint

Prime chỉ ghi/readback `master.json.CURRENT_STEP.VALUE="3"` và `J3="STEP 3"` **sau**:

- `PHASE_1_QA=PASS` hoặc `UNCHANGED_VERIFIED`, Menu đúng C3/Special Note, hàng liền mạch, không thiếu/ghi đè.
- `PHASE_2_QA=PASS`, toàn bộ hàng cha có filename B và base slug C nhất quán, không trùng/sai format; tất cả Menu A/B giữ nguyên.
- Task ID `DRY_RUN → APPLY → readback PASS/UNCHANGED`, A-child đầy đủ/duy nhất và đúng base; không worker đang ghi hay blocker.
- Tab/gid/I3 và tiến độ hiện hành đã xác minh, checkpoint cả hai nơi theo `rules/PRIME_RULES.md §2`, không ghi lùi.

**STEP 3 chỉ tạo Menu và identity, không tạo Knowledge, Difficulty, Summary, Video hay Java source.** STEP 4 PREPARE đọc A/B đã có ID/filename, Worker soạn `rowXX.md`, Prime REFRESH/VERIFY hoàn toàn local rồi checkpoint; **STEP 4 không PUBLISH C:N**. STEP 5 QA/refactor `rowXX.md`, soạn `summary.yml` (`difficult`, `markdownSummary`, chapter) và Prime PUBLISH `rowXX.md → C:N`, `difficult → O`, Summary → AC. Không tự đổi B/C cha hoặc A-child IDs. Không commit/push mặc định.
