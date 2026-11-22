# STEP 2 — PRIME ONLY: Điều phối Roadmap Title / Purpose / Objectives



**Reference VI thuộc STEP 2:** Worker soạn tài liệu `references: [...]` trực tiếp tại `L3` (header `L2=Reference`), Prime QA nội dung và exact readback trên Sheet. Phạm vi ghi chỉ gồm Roadmap, Introduction và Reference đã giao; có thể hoàn thiện riêng L3 mà không viết lại F:H/B17 đã QA.

**Hợp đồng Reference trên Sheet:** `K2/K3` là Special Note (read-only). `L3` chứa đúng một YAML với root `references`, mỗi phần tử có `title`, `url` thực và có thể có `description`; đối chiếu C2/Special Note, tối đa 30.000 Unicode code points và 32.767 UTF-16 units. L3 trống là chưa hoàn thành STEP 2 mới; `references: []` chỉ hợp lệ khi có căn cứ cho danh mục rỗng. Prime QA Roadmap, Introduction và Reference trên Sheet trước checkpoint.

## Mục tiêu và phân tách PRIME / WORKER

Giao cho **đúng một sub-worker** thực hiện **toàn bộ Roadmap của một tab module** từ **nguyên văn câu hỏi `C2`**. Kết quả gồm các milestone `F = Title`, `G = Purpose`, `H = Objectives` **và phần giới thiệu cơ bản của module tại `B17`**, dùng cho `content/readme/docs/vi/BASE.md`. Không chia roadmap giữa nhiều worker, không tạo đề bài mới thay cho `C2`, không ép WHAT/WHY/HOW hoặc số milestone trái với câu hỏi.

- **File `STEP_2.md` này chỉ dành cho Prime. Worker KHÔNG đọc.**
- **Toàn bộ chỉ dẫn thực thi dành cho worker nằm trong `/java-learning/learning-platform-data/module-generate-agent/worker/STEP_2_WORKER.md`.** Mỗi worker chỉ đọc **toàn văn đúng file worker-only đó**; không đọc file Prime, STEP khác, General Rules, rules folder, TXT hoặc câu trả lời từ task khác.
- Prime phải tự đọc `learning-platform-data/module-generate-agent/GENERAL_AGENT_RULES.md`, **liệt kê và đọc đầy đủ mọi file hiện có trong `learning-platform-data/module-generate-agent/rules/`**, `module-generate-info.txt`, toàn văn **cả `STEP_2.md` và `worker/STEP_2_WORKER.md`** trước khi giao việc. Nếu mất context hoặc không chắc chắn, đọc lại.
- **Một lần giao = toàn bộ Roadmap một tab = một lượt làm trọn** (đọc → tạo/hoàn thiện → kiểm tra → ghi → readback → báo cáo → SLEEPING). Không cần PREPARED, pha chờ thứ hai, hoặc Prime bổ sung giải thích giữa chừng.
- **Tin nhắn Prime gửi worker CHỈ có bốn dòng:** link tab, **tọa độ `C2`, `A17`, `B17`, ô tiêu đề `Special Note` và ô giá trị của nó**, vùng Roadmap giới hạn chính xác và đường dẫn `worker/STEP_2_WORKER.md`. **Tuyệt đối không chép, diễn giải, tóm tắt hoặc chuyển tiếp nội dung Special Note trong tin giao việc**; không kèm lời chào, nội dung đề bài, rule, hint, ghi chú hay ví dụ. Worker tự đọc trực tiếp tất cả ô được giao.

## 1. Bố cục và giới hạn của STEP 2

| Vị trí | Ý nghĩa | Quyền |
| --- | --- | --- |
| `C2` | Câu hỏi Roadmap gốc, bao gồm mọi lưu ý | Chỉ đọc |
| Ô có tiêu đề `Special Note` và ô giá trị ngay dưới nó (hiện tại là `K2`/`K3`) | Ghi chú riêng của module, có thể có nội dung hoặc để trống | Worker **phải đọc nguyên văn cả hai ô**, không ghi |
| **`A17`** | Nhãn/ngữ cảnh giới thiệu module | Worker **phải đọc, chỉ đọc, không sửa** |
| `F1:H1` | Nhãn/khu vực Roadmap | Giữ nguyên |
| `F2:H2` | Header `Tiêu đề` / `Mục đích` / `Mục tiêu học tập` | Chỉ bổ sung nếu cả ba ô trống; nếu đã có, giữ nguyên |
| `F3:F<END>` | **Title**, ngắn để hiển thị trên sơ đồ | Chỉ fill mới; đã có nội dung trong vùng đích → BLOCKER |
| `G3:G<END>` | **Purpose**, thông thường 1–2 câu | Chỉ fill mới; đã có nội dung trong vùng đích → BLOCKER |
| `H3:H<END>` | **Objectives**, thông thường 2–4 mục tiêu, mỗi mục một dòng **trong cùng ô** | Chỉ fill mới; đã có nội dung trong vùng đích → BLOCKER |
| **`B17`** | **Introduction** — bài giới thiệu Markdown phù hợp Roadmap, `A17` và Special Note, dành cho `BASE.md` | Worker **phải đọc; chỉ fill nếu trống**, có nội dung → BLOCKER và dừng |
| **`L2`** | **Reference** — nhãn YAML catalog | Chỉ đọc, phải là `Reference` |
| **`L3`** | **Reference YAML** — danh mục Reference VI của module | Chỉ fill khi trống hoặc kiểm chứng UNCHANGED nếu đã hợp lệ; không tự overwrite |

`<END>` là **hàng cuối Prime đã xác minh còn thuộc Roadmap**, không vượt sang Menu/Knowledge. Prime phải xác định từ **bố cục thật** của tab (vị trí nhãn Menu, header và số hàng có thể dùng). **`B17` phải được Prime xác minh không thuộc Menu, không có header/giá trị khác cần bảo toàn; nếu trùng vùng cấu trúc hiện hữu thì `BLOCKER: INTRODUCTION TARGET`, không tự dịch ô.** Cột `I` trở đi **ngoại trừ đúng `L3` được giao để viết Reference**, Knowledge `C:N` dưới vùng Menu, Difficulty `O` và Video `X:AA`, `CURRENT_STEP.VALUE` và vùng `Special Note` không thuộc vùng worker được ghi.

Mỗi milestone = **một bộ ba F/G/H trên cùng hàng**. Trong lượt STEP 2 mới, nếu **bất kỳ ô nội dung `F3:H<END>` hoặc `B17`** đã có nội dung, Prime/worker phải báo `BLOCKER: EXISTING TARGET CONTENT` và dừng phần Roadmap/Introduction, **không điền nốt những ô còn trống**. **Ngoại lệ Reference backfill được người dùng phê duyệt:** Roadmap/B17 đã hoàn thành thì chỉ xử lý L3, không viết lại các vùng đã có. Không dời/thêm hàng hoặc thay đổi nội dung cũ.

## 2. Prime — xác minh tab và giao việc

1. **Đọc đầy đủ context/rules** ở đầu file. Mỗi tab STEP 2 chỉ giao cho **một worker tại một thời điểm**. Kiểm tra pool `ACTIVE + SLEEPING` theo **Mode A/B của session** (A=3 mặc định; B=N do user cung cấp, thiếu N → BLOCKER); **ưu tiên tái sử dụng SLEEPING** và tuyệt đối không spawn khi còn worker SLEEPING; nếu phải spawn thì tạo lần lượt mỗi lệnh một worker theo Prime Rules. Không giao nhiệm vụ thứ hai cho worker ACTIVE; tôn trọng lệnh dừng/loại trừ worker.
2. Đọc `learning-platform-data/module-generate-agent/module-generate-info.txt`: lấy `Excel Page URL` và mapping **`<TÊN MODULE> sheet id : <SHEET_ID>`** đúng module. `SHEET_ID` là **gid của tab**, không phải ID file spreadsheet. Chuẩn hóa URL và lập `<URL_GỐC>/edit?gid=<SHEET_ID>#gid=<SHEET_ID>`.
3. **Xác minh** spreadsheet, gid, tên tab và `B1` đúng module. Nếu mapping không có/trùng/sai hoặc không đọc được tab: **BLOCKER**, không chọn tab theo suy đoán.
4. **Xác định từ Sheet thực tế hai tọa độ Special Note:** tìm **ô tiêu đề có đúng nhãn `Special Note`** trong vùng `Module Project` của tab đích; xác định **ô giá trị ngay bên dưới, cùng cột** (ví dụ hiện tại `K2` và `K3`). Xác minh duy nhất, đúng cấu trúc, cả hai ô tồn tại và đọc được. Nếu thiếu nhãn, vị trí mơ hồ hoặc ô giá trị không truy cập được: **`BLOCKER: SPECIAL NOTE LOCATION`**, không tự giả định `K2/K3` hay giao thiếu tọa độ. **Prime chỉ gửi địa chỉ hai ô, TUYỆT ĐỐI không tóm tắt, sao chép, viết lại hay chuyển nội dung Special Note cho worker, kể cả khi nội dung dài.** Ô giá trị trống vẫn là vị trí hợp lệ và phải gửi để worker tự kiểm tra.
5. Đọc **metadata/bố cục tab** để xác định giới hạn `F2:H<END>` nằm hoàn toàn phía trên Menu; kiểm tra header `F2:H2` và toàn vùng nội dung `F3:H<END>`, kể cả giá trị/công thức/ghi chú/chip. **Prime đọc và xác minh cả `A17` và `B17`**: A17 là nhãn/ngữ cảnh chỉ đọc, B17 phải là đích Introduction hợp lệ, không trùng Menu/header và chưa có nội dung/metadata cần bảo toàn. Không đoán từ tab khác.
6. **Nếu bất kỳ ô nội dung `F3:H<END>` hoặc `B17` đã được điền** (kể cả Roadmap chỉ có Title, có dữ liệu một phần hoặc đã hoàn chỉnh), báo `BLOCKER: EXISTING TARGET CONTENT` và **dừng phần Roadmap/Introduction, không giao worker fill phần còn lại**. **Riêng khi cả Roadmap và Introduction cũ đã hoàn thành/QA hợp lệ**, Prime có thể giao **Reference-only backfill** chỉ đọc L2/L3 và viết L3, không đọc/ghi lại Roadmap/B17. Header đúng schema ở F2:H2 và nhãn A17 là nguồn/ngữ cảnh, không phải content cần sinh. Header xung đột, scope không an toàn hoặc thiếu chỉ thị thay thế rõ ràng thì báo BLOCKER.
7. Chỉ giao **bốn dòng định vị** theo mẫu dưới. Không gửi nội dung `C2`, **nội dung/diễn giải/tóm tắt Special Note**, roadmap cũ, câu trả lời gợi ý, cách viết hay bất kỳ văn bản khác. Worker tự đọc `C2`, **cả nhãn và giá trị Special Note**, **`A17`, `B17`, `L2`, `L3`**, `F2:H<END>` trực tiếp, dùng `worker/STEP_2_WORKER.md` làm chỉ dẫn duy nhất. Với lượt **Reference-only backfill**, chỉ cấp nguồn C2/Special Note + L2/L3 và quyền ghi duy nhất L3, không cấp lại quyền ghi F:H/B17.
8. Nhận báo cáo; **Prime tự đọc lại F2:H<END>, A17, B17 và L2/L3** để kiểm tra Roadmap, nhãn A17 không đổi, giới thiệu Markdown **và Reference YAML có URL đáng tin cậy**. Chỉ chấp nhận `COMPLETED` khi worker `READBACK PASS` và **Prime QA PASS** cho cả ba đầu ra của STEP 2; lượt Reference-only chỉ QA Reference và xác minh Roadmap/Introduction không đổi. Nếu có blocker/failed, không retry ghi mù.
9. Sau khi Roadmap `F3:H<END>`, Introduction `B17` và Reference `L3` đều có nội dung hợp lệ, mọi worker release và Prime QA/exact readback PASS, Prime cập nhật/readback `master.json.CURRENT_STEP.VALUE="2"` cùng online `J3="STEP 2"` trên đúng tab/gid/I3 theo `rules/PRIME_RULES.md §2`. Reference-only backfill đã được nghiệm thu không được ghi đè Roadmap/B17 hay nâng lùi checkpoint.


### Tin nhắn Prime gửi một worker — CHỈ bốn dòng

```text
<LINK_TAB_ĐÃ_XÁC_MINH>
C2, <SPECIAL_NOTE_TITLE_CELL>, <SPECIAL_NOTE_VALUE_CELL>, A17, B17, L2, L3
F2:H<END_ROW_ĐÃ_XÁC_MINH>, B17, L3
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_2_WORKER.md
```

**Handoff riêng khi chỉ backfill Reference (4 dòng, không giao lại Roadmap/B17):**

```text
<LINK_TAB_ĐÃ_XÁC_MINH>
C2, <SPECIAL_NOTE_TITLE_CELL>, <SPECIAL_NOTE_VALUE_CELL>, L2, L3
L3
/java-learning/learning-platform-data/module-generate-agent/worker/STEP_2_WORKER.md
```

`<END_ROW_ĐÃ_XÁC_MINH>` là **số hàng cụ thể**, ví dụ `17` nếu Menu bắt đầu ở hàng 18. Hai tọa độ Special Note phải được thay bằng **địa chỉ ô thực**, ví dụ `K2, K3` nếu đã xác minh đúng; không gửi ký hiệu `...`, placeholder hay nội dung ô khi giao thật. Mọi yêu cầu thực thi nằm trong file worker-only.

## 3. Báo cáo và nghiệm thu

Prime yêu cầu/đối chiếu các trường báo cáo của worker:

- `STATUS=COMPLETED/BLOCKER/FAILED`, tab/gid, `SOURCE=C2`.
- `OUTPUT`: chính xác ô/vùng đã ghi, số ô, số milestone; tách rõ Title cũ được giữ với Title/Purpose/Objectives mới được điền.
- `PREFLIGHT`: header/nhãn nguồn không thay đổi; **toàn vùng nội dung Roadmap F3:H<END> và B17 trống trước WRITE**; có sẵn nội dung → BLOCKER/dừng toàn nhiệm vụ, không ghi một phần.
- `INTRODUCTION_LABEL`: đã tự đọc `A17` và xác minh nhãn giữ nguyên; `B17` là ô Introduction được đọc trước/sau ghi.
- `SPECIAL_NOTE`: xác nhận worker **đọc trực tiếp cả ô tiêu đề và ô giá trị**, ghi trạng thái có nội dung/trống và đã áp dụng vào kết quả nếu có; **không cần chuyển lại nguyên văn ghi chú trong báo cáo**.
- `CONSISTENCY`: số bộ ba F/G/H hoàn chỉnh, thứ tự và chất lượng mục tiêu.
- `READBACK=PASS/FAIL`, `CONTENT_QA`, `PRESERVED`, `BLOCKERS`; Prime tự QA nội dung và các ô không thuộc phạm vi.
- `CURRENT_STEP`: chỉ Prime báo kết quả ghi/readback `master.json.CURRENT_STEP.VALUE = "2"` **và Google Sheets online `J3="STEP 2"`** trên đúng tab/gid/I3 sau khi toàn STEP đạt yêu cầu; báo readback hai nơi theo `rules/PRIME_RULES.md §2`.
- `ROADMAP_QA`: đúng `F2:H<END>`, milestone đầy đủ, readback và đối chiếu nguồn `C2`/Special Note.
- `INTRODUCTION_QA`: `A17` bất biến; `B17` Markdown hoàn chỉnh, readback và tương thích Roadmap.
- `REFERENCE_QA`: `L2=Reference`, `L3` YAML hợp lệ với URL đã kiểm chứng, readback và bảo toàn ô ngoài scope.

## 4. Phạm vi và điều kiện hoàn thành

- STEP 2 **chỉ** tạo mới Roadmap trong `F:H` khi vùng nội dung đích còn trống, header `F2:H2` khi cả ba ô trống, milestone từ hàng 3 tới trước Menu, **đồng thời điền giới thiệu module ở B17** khi trống. Worker **phải đọc A17 và B17**, không sửa A17. Có nội dung cũ tại F3:H<END> hoặc B17 → BLOCKER/dừng. Không sinh Menu, Knowledge hoặc Video; không sửa `C2`, `B1`, `K3`, vùng khác/tab khác.
- Worker độc lập từ `C2` **và Special Note tự đọc nguyên văn trong Sheet**, không dùng lịch sử/context cũ, không tự tìm tab, không spawn, không commit/push, không chạy STEP tiếp theo.
- **Toàn STEP 2 chỉ COMPLETED** khi Roadmap, B17 **và Reference L3** đúng yêu cầu, dữ liệu ngoài scope bảo toàn, worker/Prime readback QA PASS, `master.json.CURRENT_STEP.VALUE` **và online `J3`** được cập nhật/readback an toàn. Module cũ chỉ backfill Reference không phải lý do để sửa lại Roadmap/Introduction hoặc nâng CURRENT_STEP.VALUE. Nếu thiếu một trong ba, báo `BLOCKER/FAILED` thực tế.
