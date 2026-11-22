# STEP 3 — WORKER PHASE 2 ONLY: Chapter Filename & Stable Base ID

**Một Worker PHASE 2 sở hữu toàn bộ Menu của một tab.** Chỉ bắt đầu **sau khi Prime xác nhận PHASE 1 đã ghi, readback và QA PASS**. Worker PHASE 2 không tạo/sửa tiêu đề Menu Cấp 1/Cấp 2 và **không sinh A-child IDs**; Prime chạy Gradle task thuần code để sinh ID sau PHASE 2.

**Chỉ đọc tài liệu worker-only này**, không đọc `STEP_3.md`, file worker PHASE 1, STEP khác, General Rules, rules, TXT hoặc history. Prime gửi đúng bốn dòng:

```text
<LINK_TAB_ĐÃ_XÁC_MINH>
B1, C3, A19:C<END_ROW>, <SPECIAL_NOTE_TITLE_CELL>, <SPECIAL_NOTE_VALUE_CELL>
<DANH_SÁCH_ĐẦY_ĐỦ_CÁC_Ô_B_C_HÀNG_CHA: B20,C20,B29,C29,...>
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_3_WORKER/STEP_3_WORKER_PHASE_2.md
```

Prime **không dán dữ liệu Sheet vào handoff**. Dòng 3 phải liệt kê **tọa độ B/C của toàn bộ hàng cha**, không phải khoảng liên tiếp gồm cả hàng con. Worker đối chiếu danh sách với toàn Menu trước WRITE; thiếu/thừa ô cha → `BLOCKER: INVALID_PHASE_2_WRITE_SCOPE`, không tự mở rộng quyền. Worker chỉ đọc những ô/cột được chỉ định, không tự xin quyền ghi A-child.

## W1. Preflight trên toàn tab

1. Mở chính xác tab/gid đã nhận. Đọc `B1`, `C3`, hai ô nhãn/giá trị Special Note và toàn bộ `A19:C<END_ROW>` (giá trị và metadata khi preflight). Xác minh `A19=Menu Cấp 1`, `B19=Menu Cấp 2`; `C3` và Special Note chỉ là nguồn ngữ nghĩa, không được sửa.
2. Lập danh sách **tất cả hàng Menu Cấp 1** từ `A20:B<END>` theo đúng cấu trúc của PHASE 1: A hàng cha là tên chương, B hàng cha ban đầu trống; B con là tên mục, A con ban đầu trống. Nếu chạy lại sau một phần PHASE 2, B cha có thể đã là filename `.md`, C cha có thể có slug; phân loại bằng **hàng cha chứa tên chương A, B cùng hàng trống/filename**, và **hàng con A trống với tên bài trong B**. Khi A con đã là ID ở lần chạy lại, nhận diện bằng pattern `[a-z][a-z0-9]*(?:-[a-z0-9]+)*-[0-9]{3,}` gắn với base chương. Nếu cấu trúc mơ hồ/sai, thiếu con, có hàng trắng giữa Menu → BLOCKER, không tự suy đoán.
3. **Lập một bảng toàn tab trước khi ghi**: `parentRow, A-title, B-filename, C-baseSlug, childRows/B-titles`. Filename phải đại diện toàn chương, không chỉ một bài con; cân nhắc thứ tự các chương để tránh đặt tên mơ hồ/trùng nhau. Không dùng tên file để tạo Menu Cấp 2; chỉ dùng tên Menu đã có từ PHASE 1.

## W2. Đặt tên filename B cha và base slug C cha

1. Chọn filename ngắn, rõ nghĩa bằng tiếng Anh, ưu tiên PascalCase/acronym có nghĩa, **đúng regex `^[A-Za-z][A-Za-z0-9]*\.md$`**. Ví dụ `ClassDesign.md` cho chương thiết kế class. Không dùng `Chapter1.md`, `Topic.md`, các basename Windows reserved (`CON, PRN, AUX, NUL, COM1..9, LPT1..9`), dấu, space, gạch, underscore, slash hoặc extension khác.
2. `C<PARENT_ROW>` là slug **suy ra chính xác theo thuật toán `ReadmeSheetImportService.slugFromStem(B-filename-without-md)`**, gồm quy tắc acronym/camel-case trước khi lowercase-kebab-case: `ClassDesign.md → class-design`, `OOPBasic.md → oop-basic`. **Không tự chọn C slug độc lập với filename**.
3. Kiểm tra **trên toàn Sheet** không trùng filename bất kể chữ hoa/thường và không trùng base slug sau chuẩn hóa. Kiểm tra cả những B/C cha đã được điền từ trước. Nếu có xung đột, phải xử lý kế hoạch tên **trước khi có A-child IDs**; nếu đã có A-child IDs, **không tự đổi B/C cha** vì sẽ thay namespace ID. Báo BLOCKER để Prime xử lý migration theo quyền riêng.
4. **FILL-ONLY:** chỉ điền `B<PARENT>` khi trống, chỉ điền `C<PARENT>` khi trống. B đã có filename hợp lệ → giữ nguyên; C đã có slug đúng từ filename → giữ nguyên. B/C đã có giá trị mâu thuẫn, sai định dạng, formula/chip/note human-owned, hoặc không xác định được owner → BLOCKER, không overwrite. Nếu có B đúng, C trống, chỉ bổ sung C đúng. Nếu B trống, C đã có, chỉ điền B khi tên chọn ra khớp chính xác slug C; nếu không thì BLOCKER.
5. **Không ghi `A<PARENT>`, `A<CHILD>`, `B<CHILD>`, `C:N<CHILD>`**, header, Special Note, Roadmap, Difficulty O, Summary AC, Video, metadata, tab khác hoặc file local. **Không sinh A-child IDs bằng AI** và không chạy Gradle task ID: Prime sở hữu phần đó.

## W3. Ghi và readback

1. Snapshot `A19:C<END>` và metadata ô đích B/C cha. Mỗi ô dự định ghi phải trống cả userEnteredValue/formula, effective/formattedValue, note, chipRuns và dữ liệu do người khác sở hữu; không xóa/đè format, validation. Nếu có thay đổi giữa lúc preflight và WRITE, dừng/đối chiếu lại thay vì overwrite mù.
2. Ghi các B/C cha trống đã được phân loại, **có thể batch trong cùng Sheet**, chỉ cập nhật `userEnteredValue` cho ô có dữ liệu mới. Không tự viết lại các ô đã có giá trị đúng. Không ghi một phần nếu phát hiện collision chưa giải quyết hoặc không kiểm tra đủ các chương.
3. Readback **toàn bộ B/C cha** và Menu A/B con. Phải khớp danh sách filename/slug đã lập, không trùng toàn tab, tất cả hàng con/tiêu đề giữ nguyên; không ghi A con. Khi WRITE không xác nhận được, kiểm tra dữ liệu thực tế và báo `BLOCKER: SHEET_WRITE_UNVERIFIED` thay vì retry/ghi đè mù.
4. Chỉ báo `COMPLETED` khi tất cả hàng cha đều có filename + base slug hợp lệ và readback PASS. **Không tự cập nhật `master.json.CURRENT_STEP` hay `J3`**; STEP 3 chỉ checkpoint sau khi Prime chạy task ID và readback toàn bộ A con.

## W4. Báo cáo rồi SLEEPING

Báo một lần: `STATUS=COMPLETED/BLOCKER/FAILED`, tab/gid, `PHASE=2`, `CHAPTER_COUNT`, `CHILD_COUNT`, `FILENAME_COUNT`, `BASE_SLUG_COUNT`, danh sách `A<PARENT> → B<PARENT>, C<PARENT>`, phân loại `NEW/UNCHANGED`, `GLOBAL_UNIQUENESS`, `READBACK`, `PRESERVED`, `BLOCKERS`. Không claim A-child đã được sinh; task code-only do Prime chạy sau.

Sau báo cáo, release ownership và về SLEEPING; **không nhận nhiệm vụ PHASE 1, STEP 4/5 hay sửa phạm vi khác**.
