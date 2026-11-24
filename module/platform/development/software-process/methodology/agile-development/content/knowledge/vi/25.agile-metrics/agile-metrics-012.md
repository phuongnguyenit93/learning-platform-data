# Kiểm tra chất lượng dữ liệu và điều kiện so sánh trước khi kết luận

Một nhóm phát triển nền tảng học trực tuyến công bố: **“Sau khi áp dụng Kanban, throughput tăng 50%, cycle time giảm 30%; vậy quy trình mới chắc chắn tốt hơn.”** Trên bảng thống kê, số thẻ Done mỗi tuần tăng từ 24 lên 36 và đường biểu diễn thời gian hoàn tất đi xuống rõ rệt. Lãnh đạo chuẩn bị áp dụng cách làm tương tự cho tất cả các đội.

Nhưng khi tìm hiểu cách dữ liệu được tạo ra, nhóm phát hiện:

- Ở giai đoạn đầu, **Done** nghĩa là phần mềm đã tích hợp, kiểm thử và đáp ứng Definition of Done (DoD); giai đoạn sau, một số thẻ được tính Done ngay khi code hoàn tất.
- Một user story trước kia được ghi thành một thẻ, nay thường chia thành **UI, API, test, cấu hình** riêng và mỗi thẻ đều được tính vào throughput.
- Báo cáo cycle time chỉ lấy những thẻ đã Done; một số thẻ khó vẫn đang bị chặn và ngày càng “già” hơn nhưng không xuất hiện trong mẫu.
- Ngày bắt đầu của một số thẻ được nhập khi Developer bấm “In Progress”, trong khi các thẻ khác chỉ được ghi sau khi qua phân tích.
- Đợt sau có ít tính năng tích hợp đối tác hơn và nhiều thay đổi nội dung nhỏ; loại công việc không còn giống đợt trước.

Con số 24, 36 hay 30% có thể **được tính chính xác từ cơ sở dữ liệu**, nhưng **kết luận về cải thiện năng lực giao sản phẩm không còn chắc chắn**. Sai lầm không nhất thiết nằm ở công thức; nó nằm ở **chất lượng dữ liệu, định nghĩa phép đo và điều kiện so sánh**.

Trong Agile, đo lường giúp đội **kiểm tra thực tế, ra quyết định và cải tiến liên tục**, không phải tạo một bảng thành tích đẹp. Vì vậy, trước mọi tuyên bố “nhanh hơn”, “tốt hơn”, “năng suất tăng” hoặc “khách hàng hài lòng hơn”, hãy kiểm tra **dữ liệu đã đại diện đúng điều muốn biết chưa**, **hai đối tượng có so sánh được không** và **có lời giải thích thay thế nào cho chênh lệch**.

Bài học thuộc chương **Đo lường Agile** của module **AGILE_DEVELOPMENT**, gắn với mục tiêu hiểu giá trị, nguyên tắc Agile, nhận phản hồi sớm, giao phần mềm tăng dần, thực hành user story, backlog, Scrum, Kanban, XP và đo dòng công việc để chọn cách phối hợp phù hợp. Chủ đề này đi sâu vào **cách đọc đúng chỉ số trước khi hành động** — không dừng ở việc biết tên KPI hoặc viết được công thức.

> **Nguyên tắc cốt lõi:** Một phép tính đúng chưa bảo đảm một nhận định đúng. **Dữ liệu phải đáng tin, định nghĩa phải nhất quán, nhóm so sánh phải đủ tương đồng và mức độ chắc chắn phải được nói rõ** trước khi đưa ra quyết định.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **chất lượng dữ liệu**, **tính hợp lệ của phép đo**, **khả năng so sánh** và **khả năng suy luận nguyên nhân**.
2. Kiểm tra dữ liệu Agile theo các chiều **đầy đủ, chính xác, nhất quán, kịp thời, duy nhất, hợp lệ, truy vết được và đại diện đúng phạm vi**.
3. Tạo **metric contract**: tên chỉ số, đối tượng đo, ranh giới bắt đầu–kết thúc, đơn vị, cửa sổ, tiêu chí loại trừ, nguồn và các điều kiện xem lại.
4. Nhận diện lỗi thường gặp với **throughput, WIP, cycle time, work item age, lead time, SLE**, cũng như các tỷ lệ về chất lượng hoặc outcome.
5. Phát hiện khi so sánh trước–sau bị méo bởi **đổi Definition of Done, chia nhỏ ticket, thay loại việc, thay mức tải, đổi công cụ hoặc mốc thời gian**.
6. Giải thích **selection bias, survivorship bias, Simpson's paradox, seasonality, sample size và confounding** bằng ví dụ gần với phát triển sản phẩm.
7. Thực hiện kiểm tra dữ liệu tối thiểu, đối chiếu nguồn gốc, phân nhóm hợp lý, công bố bất định và tránh dùng biến động ngắn hạn làm bằng chứng nhân quả chắc chắn.
8. Áp dụng một quy trình ra quyết định gồm **câu hỏi → dữ liệu → kiểm tra → so sánh → diễn giải → hành động → kiểm chứng lại**, có guardrails về chất lượng và người dùng.

## 1. Ba câu hỏi khác nhau thường bị gộp thành một

Một dashboard cho thấy đường cycle time đi xuống. Có ít nhất **ba câu hỏi** cần trả lời riêng:

1. **Dữ liệu đáng tin không?** Các mốc thời gian và trạng thái có đầy đủ, đúng và không trùng không?
2. **Chỉ số có đo đúng hiện tượng không?** “Cycle time” bắt đầu/kết thúc ở cùng ranh giới workflow qua các giai đoạn không? Done có cùng ý nghĩa không?
3. **Chênh lệch có thể quy cho thay đổi quy trình không?** Loại việc, nhân sự, tải, phụ thuộc hoặc mùa vụ có đổi đồng thời không?

### 1.1. Bốn lớp của một kết luận dựa trên dữ liệu

| Lớp | Câu hỏi | Ví dụ vấn đề |
|---|---|---|
| **Dữ liệu nguồn** | Bản ghi có đúng, đủ, hợp lệ và truy vết được? | Một thẻ có hai sự kiện Done; mốc started bị thiếu |
| **Định nghĩa chỉ số** | Quy tắc tính có phù hợp với mục tiêu đo? | Cycle time tính từ Ready ở đội A nhưng từ Development ở đội B |
| **Thiết kế so sánh** | Những nhóm/giai đoạn có thể đối chiếu không? | Đợt trước nhiều sự cố phức tạp, đợt sau nhiều ticket tài liệu |
| **Suy luận quyết định** | Chênh lệch phản ánh điều gì, với mức chắc chắn nào? | Có cải thiện đồng thời CI và môi trường test, không chỉ Kanban |

Một lớp sai có thể làm hỏng kết luận dù các lớp khác hoàn hảo. Ví dụ: phép tính trung bình cycle time hoàn toàn chính xác từ bảng event nhưng bảng event thiếu nhiều thẻ đã bắt đầu. **Chất lượng dữ liệu nguồn phải được xem trước khi chọn biểu đồ đẹp.**

### 1.2. “Đo đúng” khác “đo điều có ích”

Giả sử công cụ thống kê **số lần Developer nhấn nút Save** chính xác đến từng lần. Đây là dữ liệu có thể chính xác, nhưng không trả lời **người học có nhận được phần mềm có ích hay không**.

Tương tự:

- **Story point** là thang ước lượng tương đối của một đội khi đội dùng cách đó, không phải đơn vị năng suất phổ quát.
- **Số commit** không cho biết phần mềm đã tích hợp an toàn hay tạo giá trị.
- **Test pass rate** không cho biết bao nhiêu rủi ro người dùng được kiểm chứng.
- **Ticket Done** không tự đồng nghĩa Increment đạt DoD hoặc khả năng đã được phát hành.
- **Thời gian làm một tác vụ** không tự cho biết tác vụ có nên làm hay không.

Đầu tiên phải xác định **quyết định cần hỗ trợ**. Sau đó mới chọn phép đo và kiểm tra điều kiện để nó có ý nghĩa.

### 1.3. Một ví dụ nhỏ về kết luận quá mức

**Quan sát:** throughput tăng sau khi áp dụng WIP limit.

**Kết luận thận trọng:** “Trong các tuần quan sát với cách tính đã công bố, số work item được đánh dấu hoàn tất mỗi tuần tăng. Cần kiểm tra loại item, DoD, số item đang dở và thay đổi khác trước khi quy kết nguyên nhân.”

**Kết luận quá mức:** “Kanban chứng minh đã giúp mỗi Developer làm việc hiệu quả hơn 50%.”

Kết luận thứ hai tự thêm **nguyên nhân**, **đối tượng cá nhân** và **mức cải thiện năng suất** mà dữ liệu throughput đơn thuần không hỗ trợ.

## 2. Các chiều chất lượng dữ liệu quan trọng với Agile metrics

Dữ liệu Agile thường đến từ công cụ backlog, pull request, CI/CD, hệ thống kiểm thử, monitoring, analytics sản phẩm và phản hồi hỗ trợ. Mỗi nguồn có những quy tắc và vùng thiếu dữ liệu khác nhau. Vì vậy đội cần **kiểm tra chất lượng trước khi tổng hợp**.

### 2.1. Bảng kiểm tra chất lượng dữ liệu

| Chiều chất lượng | Ý nghĩa | Ví dụ lỗi | Cách phát hiện và xử lý |
|---|---|---|---|
| **Đầy đủ (completeness)** | Các item/sự kiện trong phạm vi đều có dữ liệu cần thiết | Thiếu started_at của 20% item | Đếm tỷ lệ thiếu theo loại việc/giai đoạn; truy lại event log hoặc công bố giới hạn |
| **Chính xác (accuracy)** | Giá trị phản ánh sự kiện thực | Người dùng bấm Done nhầm rồi chuyển lại | Kiểm tra history, đối chiếu với build/release và quy tắc trạng thái |
| **Hợp lệ (validity)** | Tuân theo cấu trúc và quy tắc được phép | finished_at sớm hơn started_at mà không có giải thích | Ràng buộc định dạng, thứ tự thời gian, domain trạng thái |
| **Nhất quán (consistency)** | Dữ liệu không mâu thuẫn giữa nguồn và giai đoạn | Dashboard ghi Done nhưng CI cho biết chưa tích hợp | Đối chiếu DoD, dữ liệu workflow và release/build |
| **Duy nhất (uniqueness)** | Không đếm cùng sự kiện/item ngoài ý muốn | Một webhook Done được nhận hai lần | Khóa định danh bất biến, deduplicate theo event ID và logic |
| **Kịp thời (timeliness)** | Dữ liệu được cập nhật đủ gần thời điểm dùng | Item đóng hôm qua chưa vào kho dữ liệu | Đo độ trễ ingest, nêu ngày chốt dữ liệu |
| **Truy vết được (lineage)** | Biết dữ liệu đến từ đâu, được biến đổi thế nào | Không rõ tool tính cycle time từ cột nào | Lưu nguồn, phiên bản truy vấn, logic loại trừ và metric contract |
| **Đại diện (representativeness)** | Mẫu đo bao quát đúng đối tượng muốn kết luận | Chỉ lấy các item dễ Done, bỏ item blocked | Định nghĩa population, kiểm tra coverage theo nhóm và status |
| **Ổn định định nghĩa (semantic stability)** | Cùng tên chỉ số có cùng nghĩa qua thời gian | “Done” trước là release-ready, sau là code-complete | Ghi version của workflow/DoD, đánh dấu điểm gãy chuỗi |

**Đầy đủ** không có nghĩa phải có mọi thuộc tính cho mọi ticket: một câu hỏi hỗ trợ có thể không cần story points. Vấn đề là những trường **bắt buộc để tính chỉ số đã chọn** có bị thiếu một cách thiên lệch hay không.

### 2.2. Phân biệt thiếu dữ liệu với giá trị bằng không

Ví dụ một item không có \`blocked_duration\`:

- Có thể item chưa từng bị chặn: **0 giờ** nếu log ghi nhận đáng tin và chính sách xác nhận như vậy.
- Có thể hệ thống không thu sự kiện block: **không biết**.
- Có thể item chưa bắt đầu: trường blocked duration **chưa áp dụng**.

Điền mọi ô trống bằng 0 có thể làm **thời gian chặn trung bình giảm giả tạo**. Cần phân biệt \`0\`, \`NULL\` và **không thuộc population**.

### 2.3. Dữ liệu được tạo bởi con người mang bối cảnh công việc

Một thẻ có thể được:

- Tạo trước nhiều tháng nhưng chỉ được đưa vào thực hiện hôm nay.
- Đổi loại từ “bug” thành “feature”.
- Tách làm ba thẻ nhỏ; thẻ cha được đóng mà không có Increment mới.
- Chuyển Done rồi Reopen.
- Chờ đối tác nhưng vẫn hiển thị “In Progress”.
- Được đóng vì quyết định không làm, không phải vì tạo khả năng mới.

Nếu tính tất cả thành “công việc hoàn tất có giá trị” hoặc “cycle time của việc phát triển”, dữ liệu sẽ bị méo.

### 2.4. Chất lượng dữ liệu có thể khác nhau theo nhóm

Ví dụ đội bảo trì ghi mọi bug có đầy đủ lịch sử trạng thái, còn đội phát triển tính năng mới chỉ ghi ngày bắt đầu ở một phần PBI. Nếu tổng hợp hai đội rồi so trung bình, nhóm có thể vô tình **ưu ái đội ghi ít dữ liệu**.

Trước khi so sánh, hãy xem **tỷ lệ đầy đủ và logic nhập liệu theo từng nhóm**. Đôi khi hành động tốt nhất là **cải thiện thu thập dữ liệu** và chưa công bố bảng xếp hạng.

## 3. Metric contract: định nghĩa phép đo trước khi nhìn kết quả

Một **metric contract** là thỏa thuận thực dụng giúp mọi bên hiểu phép đo đang trả lời câu hỏi gì, dữ liệu được lấy và biến đổi ra sao, giới hạn ở đâu và khi nào phải xem lại. Đây **không phải artifact bắt buộc của Scrum, Kanban hoặc XP**; nó là công cụ tránh tranh luận do định nghĩa mơ hồ.

### 3.1. Mẫu metric contract

~~~text
TEN CHI SO:
  [Vi du: Cycle time cua PBI da Done]

CAU HOI / QUYET DINH:
  [Rui ro / muc tieu nao duoc ho tro?]

DON VI QUAN SAT:
  [PBI, bug, incident, request, cohort nguoi dung...]

POPULATION:
  [Nhung doi, luong cong viec, loai item duoc tinh]

START:
  [Su kien bat dau + ranh gioi workflow]

END:
  [Su kien Done + dieu kien chat luong]

THOI GIAN VA DON VI:
  [UTC, timezone hien thi, ngay lich/ngay lam viec, gio]

CUA SO:
  [Tuan/chu ky/cohort nao, chot du lieu luc nao]

TRU SO / MAU SO:
  [Neu la ty le; khai bao ngay ca khi hien nhien]

LOAI TRU:
  [Cancelled, duplicate, test data, outlier... va ly do]

SU KIEN LAP / REOPEN / MISSING:
  [Chinh sach de-dup, viec mo lai, gia tri null]

NGUON DU LIEU / LINEAGE:
  [Issue history, CI, product analytics, query version]

NHOM SO SANH:
  [Work type, size band, service, channel, doi tuong]

GIOI HAN VA GIA DINH:
  [Nhung gi metric khong cho biet]

GUARDRAILS:
  [DoD, an toan, chat luong, tinh toan ven, khoi luong]

OWNER / MOC XEM LAI:
  [Ai bao tri dinh nghia; khi nao can doi version]
~~~

Không nhất thiết điền 20 trường vào mỗi báo cáo nhỏ; nhưng với chỉ số dùng để quyết định **thay đổi tổ chức, ưu tiên hoặc cam kết ngày**, độ rõ của định nghĩa rất đáng đầu tư.

### 3.2. Metric contract mẫu: throughput

**Câu hỏi:** Trong một tuần, bao nhiêu **work item thực sự đi đến điểm hoàn tất đã thống nhất**?

**Ví dụ quy tắc:**

- Đối tượng: PBI và bug thuộc cùng một workflow phát triển, báo riêng theo loại.
- Điểm Done: khi các điều kiện workflow/DoD tương ứng được đáp ứng, không tính \`Code Complete\` là Done.
- Một item có ID ổn định được tính một lần khi vượt qua ranh giới Done theo chính sách; nếu reopen, ghi riêng và điều chỉnh theo quy tắc đã công bố.
- Item canceled hoặc duplicate không được tính như chức năng hoàn tất; ghi chúng thành luồng khác khi có ích.
- Cửa sổ: tuần lịch theo timezone đã thống nhất; chốt dữ liệu sau độ trễ ingest xác định.
- Không dùng throughput **đếm PBI** để so năng suất cá nhân hoặc so các đội có cách chia PBI khác nhau.

Một biểu đồ throughput có ích khi những điều này đủ ổn định hoặc sự khác biệt được nêu rõ.

### 3.3. Metric contract mẫu: cycle time

**Câu hỏi:** Với item đã Done trong workflow này, mất bao lâu từ lúc thực sự bắt đầu tới khi hoàn tất?

**Ví dụ quy tắc:**

- Start = chuyển vào bước đầu tiên thuộc WIP của workflow.
- End = đạt Done theo chính sách chất lượng.
- Đo **thời gian lịch** từ timestamp đến timestamp; thời gian chờ, blocked hoặc verification vẫn nằm trong cycle time nếu thuộc workflow.
- Chỉ tính trên item đã hoàn tất trong cửa sổ phân tích, nhưng **cần xem work item age của item còn mở** để tránh survivorship bias.
- Item đã reopen có chính sách rõ: ví dụ giữ nguyên start ban đầu và Done cuối nếu cùng một item chưa thực sự hoàn tất; ghi lịch sử để phân tích.
- Báo phân phối, trung vị và percentile phù hợp; không chỉ trung bình.
- Nếu đổi start/end hoặc DoD, **không nối chuỗi như thể không có thay đổi**.

### 3.4. Metric contract mẫu: tỷ lệ người học vào bài đầu

**Câu hỏi:** Có bao nhiêu học viên đủ điều kiện bắt đầu học thành công sau khi hoàn tất đăng ký?

Một định nghĩa giả định:

\[
\text{Tỷ lệ vào bài đầu}
=
\frac{\text{Số học viên đủ điều kiện đã vào bài đầu trong 24 giờ}}
{\text{Số học viên đủ điều kiện hoàn tất đăng ký trong cohort}}
\times100\%
\]

Cần xác định thêm:

- “Đủ điều kiện” theo quy tắc nào? Khóa miễn phí/trả phí, tài khoản bị khóa?
- Một học viên có nhiều khóa được tính theo **người**, **đơn** hay **lượt đăng ký**?
- Cửa sổ 24 giờ là lựa chọn kinh doanh minh họa, **không phải chuẩn Agile**.
- Nếu tracking event mất, có thể xác nhận hành vi bằng nguồn đáng tin khác không?
- Các học viên đăng ký gần cuối giai đoạn đã đủ 24 giờ để quan sát chưa?
- Những nhóm thiếu điều kiện không nên bị loại tùy tiện sau khi nhìn dữ liệu.

### 3.5. Versioning khi định nghĩa đổi

Giả sử từ Sprint 8 đội đổi Done từ “code merged” sang “Increment đạt DoD”. Hai chuỗi không đo cùng sự kiện.

Một báo cáo trung thực có thể chú thích:

~~~text
CycleTime.v1:
  Start = In Progress
  Done = Code Merged
  Ap dung den ngay D1

CycleTime.v2:
  Start = Development started
  Done = Integrated + DoD achieved
  Ap dung tu ngay D2

SO SANH:
  Khong tu dong tinh % cai thien xuyen D1/D2.
  Neu can, tinh lai lich su tu event raw bang cung dinh nghia,
  hoac chi so sanh trong tung version.
~~~

Nếu không có lịch sử đủ để tính lại, **công bố đứt gãy chuỗi** thay vì điền số giả.

## 4. Bốn flow metrics Kanban và những sai lệch hay gặp

The Kanban Guide nêu bốn flow metrics tối thiểu: **WIP**, **Throughput**, **Work Item Age** và **Cycle Time**. Chúng bổ sung nhau; chỉ chọn một con số thường bỏ qua phần còn lại của hệ thống.

### 4.1. WIP — những gì đã bắt đầu nhưng chưa Done

**Work in Progress (WIP)** là số work item đã bắt đầu nhưng chưa hoàn tất trong ranh giới workflow. Ví dụ tại thời điểm chốt:

~~~text
Development: 3
Verification: 2
Blocked (van la item da bat dau): 1
Tong WIP: 6
~~~

Ví dụ chỉ có nghĩa khi **Blocked** là trạng thái riêng ngoài hai cột trên. Nếu blocked đã được tính trong Development hoặc Verification, cộng thêm một lần sẽ thành **đếm trùng**.

**Sai lệch phổ biến:**

- Chuyển item bị chặn ra bảng khác để “giảm” WIP nhưng item vẫn chưa Done.
- Gộp item Ready chưa bắt đầu vào WIP mà không nói rõ ranh giới.
- Đếm subtask và parent đồng thời.
- Chỉ chụp snapshot ngày cuối tuần, bỏ qua dao động lớn trong tuần.
- So WIP giữa các đội có workflow khác nhau rồi kết luận đội ít WIP làm tốt hơn.

**Kiểm tra:** định nghĩa start/end, trạng thái blocked, ID duy nhất, snapshot timestamp và đối tượng đếm.

### 4.2. Throughput — bao nhiêu item hoàn tất mỗi khoảng

Ví dụ một tuần có 12 PBI Done và 8 bug Done:

\[
\text{Throughput toàn bộ}=12+8=20\ \text{items/tuần}
\]

Nhưng nếu ở tuần trước nhóm tính cả 30 subtask còn tuần sau chỉ tính PBI, so **30 với 20** không phản ánh cùng đơn vị công việc. Cũng không nên kết luận số lượng PBI hoàn tất bằng số năng lực người dùng được cung cấp, vì một PBI có thể là lát cắt UI không độc lập hoặc một thay đổi cấu hình.

**Kiểm tra:** loại item, chính sách Done, duplicate/reopen, cửa sổ thời gian, work mix và cách chia item.

### 4.3. Work Item Age — thời gian item chưa Done đã tồn tại trong WIP

**Work item age** đo thời gian từ khi một item **bắt đầu** đến **thời điểm hiện tại** khi nó vẫn chưa Done.

Ví dụ một item bắt đầu từ 12 ngày trước và vẫn chờ tích hợp:

\[
\text{Age} = 12\ \text{ngày lịch}
\]

Nó không có cycle time cuối cùng, vì chưa Done. Nếu đội chỉ lấy những item đã hoàn tất để báo “cycle time trung bình 4 ngày”, item 12 ngày tuổi **không xuất hiện** trong giá trị đó.

**Kiểm tra:** snapshot ngày nào, item còn mở hay đã Done, start boundary, thời gian chờ được tính thế nào và SLE có phù hợp loại item không.

### 4.4. Cycle Time — phân phối của những item đã Done

Giả sử 10 item tương đối cùng loại có cycle time ngày lịch đã xác minh, sắp tăng dần:

~~~text
2, 3, 3, 4, 5, 5, 7, 8, 13, 21
~~~

Một số mô tả:

- **Trung vị:** \((5+5)/2=5\) ngày.
- **Trung bình:** \(71/10=7{,}1\) ngày.
- **Percentile 85 theo nearest-rank minh họa:** vị trí \(\lceil0{,}85\times10\rceil=9\), giá trị **13 ngày**.
- **Khoảng quan sát:** từ 2 tới 21 ngày.

**Không có một quy ước tính percentile duy nhất trong mọi công cụ.** Với mẫu nhỏ, các thuật toán nội suy có thể cho kết quả khác. Hãy nêu **phương pháp percentile**, quy mô mẫu và bối cảnh; đừng hứa chính xác rằng “85% mọi item tương lai sẽ xong trong 13 ngày” chỉ vì một mẫu 10 item như trên.

### 4.5. Dùng Cycle Time và Work Item Age cùng nhau

Giả sử bốn item Done trong tuần có cycle time **2, 3, 4, 7 ngày**; trung vị là:

\[
\frac{3+4}{2}=3{,}5\text{ ngày}
\]

Nhưng hai item đang mở có tuổi **14 và 18 ngày**. Nếu không đưa chúng lên bảng:

> “Các item hoàn tất trong tuần có trung vị 3,5 ngày, **đồng thời còn hai item mở đã 14 và 18 ngày tuổi**; chưa có đủ cơ sở kết luận toàn bộ dòng công việc đã nhanh hơn.”

Đây là ví dụ của **survivorship bias/censoring**: nhóm đã Done có thể thiên về các item dễ, trong khi các item khó bị giữ ở WIP. Không nên gán cycle time tưởng tượng cho item chưa Done; hãy **báo age/blocked và dùng phương pháp phân tích dữ liệu chưa hoàn tất phù hợp** nếu cần dự báo chuyên sâu.

### 4.6. Service Level Expectation (SLE)

Trong Kanban, **SLE** là kỳ vọng về thời gian một work item có thể đi qua workflow, bao gồm **thời lượng và xác suất**. Ví dụ:

> “Với nhóm item nhỏ thuộc workflow này, dựa trên dữ liệu lịch sử đủ đại diện, chúng ta kỳ vọng khoảng **85%** item hoàn tất trong **10 ngày lịch** sau khi started.”

Đây là **ví dụ chính sách**, không phải giá trị chuẩn bắt buộc. Một SLE không bao gồm xác suất hoặc chỉ lấy “cam kết 10 ngày” sẽ che sự bất định. Nếu cách chia item, loại việc và điểm Done đổi, cần **xem lại SLE**.

Không được dùng SLE làm cách ép Developers hạ DoD hoặc đóng item trước khi kiểm thử.

### 4.7. Lead time là một tên dễ lệch định nghĩa

Nhiều đội đo **lead time** từ lúc người dùng/khách hàng đặt yêu cầu đến lúc khả năng được giao. Một đội khác có thể dùng “lead time” từ commit tới production theo DevOps. Vì vậy cần ghi:

~~~text
LeadTime.Product:
  start = yeu cau duoc chap nhan vao he thong
  end   = kha nang duoc cung cap theo chinh sach

LeadTime.Change:
  start = thay doi ma duoc dua vao pipeline
  end   = thay doi duoc deploy theo pham vi da cong bo
~~~

Không tự gộp hai định nghĩa vì đều mang tên “lead time”.

## 5. Kiểm tra thời gian và lịch sử trạng thái trước khi tính

Dữ liệu thời gian là nguồn sai lệch rất phổ biến vì công cụ hiển thị mốc ngày “có vẻ hiển nhiên” nhưng khác múi giờ, khác giai đoạn và khác cách chuyển trạng thái.

### 5.1. Múi giờ và giờ địa phương

Ví dụ:

~~~text
Started: 2026-05-04 23:00 UTC
Done:    2026-05-05 01:00 UTC
Cycle:   2 gio
~~~

Nếu chuyển sang giờ Việt Nam (UTC+07:00), hai sự kiện thành **06:00** và **08:00 ngày 05/05**, vẫn cách nhau **2 giờ**. Nếu hệ thống tính theo phần ngày lịch mà không chuyển đúng múi giờ, nó có thể báo qua một ngày hoặc qua hai ngày khác nhau.

**Kiểm tra:**

- Lưu hoặc chuẩn hóa timestamp với timezone rõ.
- Tính duration bằng **instant** hoặc mốc thời gian có offset đúng.
- Khi gom theo “ngày”, công bố timezone hoạt động.
- Không nhầm \`2026-05-04\` (date-only) với một timestamp chính xác tới giờ.
- Chú ý quy tắc daylight saving nếu đội làm việc với những vùng có chuyển giờ; Việt Nam hiện không dùng DST nhưng hệ thống toàn cầu có thể gặp.

### 5.2. Ngày lịch và ngày làm việc

Một item bắt đầu 16:00 thứ Sáu, Done 10:00 thứ Hai có:

- **Thời gian lịch:** 66 giờ (nếu không có đổi giờ địa phương trong ví dụ).
- **Thời gian theo giờ làm việc:** phụ thuộc lịch, ngày nghỉ, giờ làm của đội, có thể rất khác.

Vì vậy “cycle time 3 ngày” phải trả lời:

- Có bao gồm cuối tuần và ngày lễ không?
- Thời gian waiting/block có được tính không?
- Đội làm ca hoặc on-call có lịch khác nhau không?

Trong đo flow Kanban, việc dùng **elapsed calendar time** thường giúp nhìn cả thời gian chờ. Nếu đo **working time** riêng, nên đặt tên và công bố, không tự gọi tương đương cycle time đã định nghĩa khác.

### 5.3. History thay vì chỉ đọc trạng thái hiện tại

Một bản ghi chỉ có cột \`status = Done\` không cho biết:

- Item đã chuyển qua các bước nào?
- Khi nào thực sự started?
- Có reopen không?
- Có bị chặn bao lâu?
- Done theo phiên bản DoD nào?

Nên lưu/đọc **event history** hoặc dữ liệu được xây từ history với logic nhất quán, nhất là khi phân tích cycle time và blocked time. Nếu công cụ chỉ lưu snapshot cuối, cần công bố những phân tích không thể thực hiện đáng tin.

### 5.4. Reopen và việc tính hai lần

Giả sử:

~~~text
Ngày 01: Started
Ngày 03: Done
Ngày 04: Reopened vì thiếu kiểm thử
Ngày 08: Done thật theo DoD
~~~

Nếu tính hai lần Done là hai item hoàn tất, throughput bị tăng giả. Nếu lấy ngày 03 làm end, cycle time bỏ qua khoảng làm lại. Một chính sách có thể là **một item chỉ được tính Done tại lần hoàn tất cuối được xác nhận** trong vòng đời đang xét; khi cần phân tích lần đóng lại, dùng metric rework riêng. Quan trọng là **chính sách được công bố và áp dụng nhất quán**, đặc biệt khi lịch sử xuất hiện sau ngày chốt báo cáo.

### 5.5. Canceled, split, merged và parent-child

Trong Product Backlog refinement, một item lớn có thể được tách thành các lát cắt. Nếu dùng parent-child:

- Không đếm **cả parent và tất cả children** như cùng một đơn vị throughput nếu chúng cùng đại diện một phần giá trị.
- Không coi canceled là “Done” theo nghĩa giao phần mềm nếu canceled chỉ là bỏ yêu cầu.
- Khi merge item, cần đối chiếu nguồn gốc và tránh đếm hai lần.
- Nếu thay cách chia item, không so số lượng mà thiếu ghi nhận điểm gãy về granularity.

Đặc biệt, **tăng throughput do chia ticket nhỏ hơn** không tự là gian lận: lát cắt nhỏ có thể là cải tiến thực sự giúp phản hồi sớm. Nhưng kết luận phải là **“hệ thống hoàn tất nhiều item nhỏ hơn”**, không được tự nhảy sang **“năng suất tăng tương ứng”**.

## 6. Điều kiện so sánh: hai con số phải nói về cùng một hiện tượng

Trong một báo cáo trước–sau, câu hỏi không chỉ là **“số nào lớn hơn?”** mà là **“hai số có đo đúng cùng thứ, trong điều kiện đủ tương đồng không?”**

### 6.1. Mười hai điều kiện nên kiểm tra

| Điều kiện | Câu hỏi trước khi so sánh | Hệ quả nếu bỏ |
|---|---|---|
| **1. Cùng đối tượng đo** | Cả hai là PBI, bug hay task? | So số PBI với số subtask |
| **2. Cùng ranh giới workflow** | Start/Done có cùng ý nghĩa? | Cycle time giảm vì cắt thời gian chờ ra ngoài |
| **3. Cùng DoD/chất lượng** | Done có cùng điều kiện kiểm chứng? | Ticket Done tăng khi thực chất kiểm thử bị hoãn |
| **4. Cùng đơn vị thời gian** | Giờ, ngày lịch hay ngày làm việc? | Sai kết luận vì đổi đơn vị |
| **5. Cùng độ dài cửa sổ** | 4 tuần so 4 tuần hay một Sprint so một tháng? | Throughput tăng vì kỳ dài hơn |
| **6. Cùng mức đầy đủ dữ liệu** | Tỷ lệ thiếu timestamp/sự kiện tương tự? | Đội ghi thiếu trông “nhanh” hơn |
| **7. Cùng cấu trúc loại việc** | Tỷ lệ bug, feature, spike, incident có khác nhiều? | Mẫu đợt sau dễ hơn nhưng gọi là cải tiến |
| **8. Cùng cách chia item** | Kích thước/granularity có đổi? | Nhiều ticket nhỏ bị xem là năng suất tăng |
| **9. Cùng điều kiện năng lực** | Nhân sự, chuyên môn, môi trường, công cụ và phụ thuộc có thay đổi? | Gán hiệu quả cho một thực hành không phải nguyên nhân duy nhất |
| **10. Cùng mùa vụ/mức tải** | Kỳ khai giảng, campaign, sự cố lớn có xuất hiện? | So tuần cao điểm với tuần bình thường |
| **11. Cùng dân số/cohort** | Người dùng mới/cũ, web/mobile, khóa miễn phí/trả phí có khác? | Conversion thay vì do tính năng lại do cơ cấu người dùng |
| **12. Cùng mức trưởng thành dữ liệu** | Event có đến muộn, item còn mở, người dùng chưa hết thời gian theo dõi? | Kỳ gần nhất bị đánh giá thấp/cao vì chưa đủ quan sát |

Không phải mọi điều kiện phải **giống hệt** mới được so. Điều cần thiết là **biết sự khác biệt, phân tích tác động hoặc giới hạn kết luận**. Ví dụ nếu số người trong đội tăng từ bốn lên tám, có thể nói tổng throughput tăng, nhưng không tự kết luận mỗi cá nhân hiệu quả hơn.

### 6.2. So tuần lịch với Sprint

Ví dụ đội A làm Sprint hai tuần, đội B làm Kanban với dịch vụ liên tục.

- Đội A báo **40 item/Sprint**.
- Đội B báo **24 item/tuần**.

Không thể so 40 với 24 trực tiếp. Nếu hai tuần thực sự tương đương, đội A có throughput trung bình thô **20 item/tuần**. Nhưng vẫn còn khác về **định nghĩa item, DoD, loại việc và tải**. Đơn vị thống nhất là **điều kiện cần, không phải điều kiện đủ**.

### 6.3. Không so velocity story point giữa các đội

Đội A báo 50 story points/Sprint, đội B báo 30 points/Sprint. Story points thường là thang ước lượng **tương đối và nội bộ**, phụ thuộc cách đội hiểu độ lớn/độ phức tạp và hiệu chỉnh qua thời gian. **50 > 30 không cho phép kết luận đội A năng suất hơn**.

Ngay cả trong cùng một đội, nếu thay thang ước lượng hoặc chia story, velocity có thể đổi mà không có thay đổi giá trị người dùng.

**Dùng velocity đúng bối cảnh:** hỗ trợ một đội dự báo phạm vi theo lịch sử tương đối ổn định, kèm bất định; không dùng để thưởng/phạt cá nhân hoặc so đội khác như thước đo phổ quát.

### 6.4. Tỷ lệ cần cùng mẫu số

Ví dụ hai Sprint:

| | Sprint trước | Sprint sau |
|---|---:|---:|
| Lần thử thanh toán hợp lệ | 500 | 1.000 |
| Lần thanh toán thành công | 450 | 850 |
| Tỷ lệ thành công | 90% | 85% |

Số giao dịch thành công tăng từ 450 lên 850, nhưng **tỷ lệ thành công giảm** từ 90% còn 85%. Nếu chỉ nhìn số lượng thành công, kết luận “trải nghiệm thanh toán tốt hơn” là không đủ.

Ngược lại, nếu kỳ sau có thêm nhiều người mới, kênh khác hoặc loại giao dịch khó hơn, tỷ lệ giảm cũng chưa chứng minh **code xấu đi**. Phải phân nhóm theo điều kiện.

### 6.5. Cohort chưa có đủ thời gian quan sát

Nhóm đo “tỷ lệ học viên vào bài trong 24 giờ sau ghi danh”. Báo cáo chốt vào 17:00 thứ Sáu nhưng vẫn đưa người vừa đăng ký lúc 16:58 vào mẫu số. Họ mới có **2 phút** để hoàn thành hành trình, chưa phải 24 giờ.

Cách xử lý:

- Chỉ đưa vào cohort đánh giá **những lượt đã có đủ cửa sổ 24 giờ** tính từ thời điểm đủ điều kiện.
- Hoặc dùng phương pháp phân tích dữ liệu theo thời gian với trường hợp chưa hoàn tất/censored phù hợp.
- Công bố **thời điểm chốt và độ trễ dữ liệu**, tránh so cohort chưa trưởng thành với cohort đã đủ thời gian.

Nếu loại người chưa đủ cửa sổ, phải làm theo một **quy tắc định trước và nhất quán**, không chọn sau khi nhìn kết quả.

### 6.6. So khối lượng theo giá trị không chỉ số ticket

Giả sử:

~~~text
Truoc:
  1 user story = UI + API + DB + tests + DoD
  8 stories Done -> 8 hanh vi tich hop duoc kiem chung

Sau:
  Cung mot hanh vi duoc tach thanh 4 ticket UI/API/DB/Test
  24 tickets Done -> co the chi lien quan 6 hanh vi
~~~

Nếu hệ thống sau chỉ đếm ticket, kết luận throughput tăng từ 8 lên 24 **không phản ánh cùng đơn vị**. Tuy nhiên, nếu team thực sự giao sáu lát cắt nhỏ có phản hồi sớm hơn, điều đó vẫn có thể là cải tiến ở chiều **flow và feedback**. Hãy đo cả **item flow** lẫn **Increment/outcome**, không ép một con số trả lời mọi câu hỏi.

## 7. Simpson's paradox: khi xu hướng tổng ngược với xu hướng từng nhóm

Một kết luận sai rất phổ biến là nhìn **tỷ lệ tổng** rồi bỏ qua sự thay đổi về **cơ cấu các nhóm**.

### 7.1. Ví dụ hai loại yêu cầu ghi danh

Giả sử nhóm theo dõi tỷ lệ hoàn tất hợp lệ đối với:

- **Nhóm đơn giản:** ghi danh khóa miễn phí theo luồng ít bước.
- **Nhóm phức tạp:** thanh toán khóa trả phí qua đối tác và xác nhận quyền.

Số liệu giả định:

| Giai đoạn | Loại yêu cầu | Thành công | Tổng đủ điều kiện | Tỷ lệ |
|---|---|---:|---:|---:|
| **Trước** | Đơn giản | 90 | 100 | 90% |
| **Trước** | Phức tạp | 20 | 100 | 20% |
| **Sau** | Đơn giản | 19 | 20 | 95% |
| **Sau** | Phức tạp | 45 | 180 | 25% |

Trong **từng nhóm**, tỷ lệ đều tăng:

- Đơn giản: **90% → 95%**.
- Phức tạp: **20% → 25%**.

Nhưng tổng lại là:

\[
\text{Trước}=\frac{90+20}{100+100}=\frac{110}{200}=55\%
\]

\[
\text{Sau}=\frac{19+45}{20+180}=\frac{64}{200}=32\%
\]

Tỷ lệ tổng **giảm từ 55% xuống 32%**, dù cả hai nhóm riêng đều tốt lên. Lý do là giai đoạn sau có **nhiều yêu cầu phức tạp hơn** — 180/200 so với 100/200.

Hiện tượng này minh họa **Simpson's paradox**: xu hướng ở dữ liệu tổng có thể khác hoặc đảo chiều khi xét những phân nhóm có cơ cấu khác nhau.

### 7.2. Kết luận nào được hỗ trợ?

**Đúng với dữ liệu giả định:**

> “Tỷ lệ thành công trong từng phân nhóm được định nghĩa ở đây tăng, trong khi tỷ lệ tổng giảm vì cơ cấu chuyển mạnh về các yêu cầu khó hơn.”

**Chưa đủ căn cứ:**

> “Code chắc chắn tốt hơn ở mọi tình huống, bất kể người dùng, thời gian và tải.”

> “Sản phẩm sau chắc chắn xấu đi vì tỷ lệ tổng giảm.”

Để suy luận về chất lượng, còn cần xem:

- Mỗi nhóm có thực sự **cùng tiêu chuẩn thành công** ở hai kỳ không?
- Kỳ sau có người dùng mới, thiết bị khác, đối tác khác không?
- Số mẫu nhóm đơn giản sau chỉ có **20**, nên mức 95% khá nhạy với một vài trường hợp.
- Có dữ liệu event mất hoặc đếm trùng trong nhóm phức tạp không?
- Có sự cố hoặc thay đổi sản phẩm nào khác đồng thời không?

### 7.3. Chuẩn hóa cơ cấu minh họa

Nếu muốn so theo **cùng trọng số giả định 50% đơn giản và 50% phức tạp**, có thể tính:

\[
R_{\text{trước, chuẩn hóa}}=0{,}5\times90\%+0{,}5\times20\%=55\%
\]

\[
R_{\text{sau, chuẩn hóa}}=0{,}5\times95\%+0{,}5\times25\%=60\%
\]

Khi cố định cơ cấu 50/50, tỷ lệ tăng **55% → 60%**. Đây là phép **standardization minh họa để tách ảnh hưởng cơ cấu**, không phải tuyên bố kết quả cho dân số thực. Trọng số phải được chọn và giải thích từ population mục tiêu, không tùy chỉnh để làm báo cáo đẹp.

### 7.4. Áp dụng Simpson vào Agile flow metrics

Không chỉ conversion mới gặp hiện tượng tương tự. Ví dụ:

- Cycle time trong từng nhóm **bug nhỏ** và **feature tích hợp** đều cải thiện.
- Nhưng tỷ lệ feature tích hợp ở kỳ sau tăng mạnh.
- Cycle time tổng có thể tăng do nhiều item khó hơn.

Vì vậy, trước khi đánh giá một chính sách Kanban hoặc thay đổi năng lực đội:

1. Phân loại các item theo **luồng, loại công việc và mức độ so sánh được**.
2. Xem cả **tổng** và **theo nhóm**.
3. Nêu cơ cấu mỗi nhóm theo thời gian.
4. Nếu cần, dùng trọng số cố định với giả định được công bố.
5. Không cắt dữ liệu thành quá nhiều nhóm nhỏ khiến mẫu thiếu đáng tin.

## 8. Selection bias, survivorship bias và các sai lệch khó thấy

### 8.1. Chỉ chọn item đã Done

Đội khoe cycle time trung bình 3 ngày vì 15 item dễ Done. Nhưng 5 item quan trọng bị chặn đã 20–30 ngày.

Chỉ xem item Done có thể tạo **survivorship bias**: các item khó chưa hoàn tất bị bỏ khỏi bảng. **Cách khắc phục:** luôn đi kèm work item age, WIP/blocked và phân phối các item đang mở; cần nêu giới hạn khi chỉ tính cycle time của items Done.

### 8.2. Chỉ dùng những user truy cập thành công

Nhóm khảo sát mức hài lòng chỉ trên người đã vào bài đầu. Những học viên gặp lỗi thanh toán và bỏ dở bị loại khỏi khảo sát. Điểm hài lòng có thể cao trong mẫu **đã vượt qua trở ngại**, nhưng không đại diện cho toàn bộ người bắt đầu ghi danh.

**Cách khắc phục:** nêu population mục tiêu, nhóm không phản hồi, các điểm rơi của funnel và khả năng tiếp cận nhóm bị lỗi.

### 8.3. Thay đổi công cụ làm thay đổi “lượng lỗi”

Sau khi bổ sung monitoring, đội phát hiện nhiều lỗi hơn. Không thể tự kết luận chất lượng xấu đi; một phần có thể do **khả năng phát hiện tốt hơn**.

Ngược lại, nếu tắt kiểm tra hoặc khiến báo bug khó hơn, số lỗi ghi nhận giảm cũng không chứng minh chất lượng tốt lên.

**Cách khắc phục:** ghi lại thay đổi cơ chế phát hiện, xét severity và ảnh hưởng người dùng, không tối ưu KPI số bug bằng cách che tín hiệu.

### 8.4. Mẫu thuận tiện và nguồn phản hồi thiên lệch

Ví dụ chỉ hỏi những học viên tham gia thử nghiệm chủ động, có thiết bị mới và mạng mạnh. Không nên tự suy luận kết quả cho học viên dùng thiết bị cũ hoặc kết nối yếu.

**Cách khắc phục:** phân biệt exploratory feedback với đại diện thống kê, nêu đối tượng và điều kiện thử, chọn bổ sung mẫu khi quyết định đòi hỏi.

### 8.5. Dữ liệu đến muộn và việc chỉnh sửa quá khứ

Một hệ thống analytics có sự kiện phát sinh ngày 10 nhưng chỉ nhận được ngày 12. Nếu dashboard dùng timestamp nhận dữ liệu thay timestamp sự kiện, sự kiện có thể bị tính vào kỳ sai.

Ngoài ra, một PBI được reopen sau ngày báo cáo có thể thay đổi cách hiểu Done của kỳ trước. Cần quyết định:

- Dùng **event time** hay **ingestion time** cho phép đo?
- Có một thời điểm **data cutoff** để chốt báo cáo không?
- Cho phép **restatement** (tính lại số kỳ cũ) hay đóng băng và ghi điều chỉnh riêng?
- Nếu dữ liệu thay đổi, ai được thông báo và phiên bản nào dùng cho quyết định?

Không có một quy tắc duy nhất; điều cần là **nhất quán và truy vết được**.

## 9. Biến động ngẫu nhiên, kích thước mẫu và giới hạn suy luận

Đội thường nhìn một Sprint rồi tuyên bố “quy trình mới làm cycle time giảm 20%”. Nhưng Agile metrics có biến động do loại item, con người, môi trường, chờ đợi, tải và ngẫu nhiên. Cần phân biệt **tín hiệu có ý nghĩa** với dao động thông thường.

### 9.1. Mẫu nhỏ rất nhạy

Giả sử một nhóm có đúng **10 người dùng thử**, trong đó 9 hoàn tất tác vụ:

\[
\text{Completion}=9/10=90\%
\]

Chỉ cần **một người** không hoàn tất, tỷ lệ thành:

\[
8/10=80\%
\]

Chênh lệch **10 điểm phần trăm** xuất hiện chỉ từ một quan sát. Nếu kết luận mọi người dùng tương lai sẽ đạt 90%, độ chắc chắn bị phóng đại. Cần xem quy mô, cách chọn mẫu, chất lượng tracking, điều kiện dùng và mức tác động.

### 9.2. Trend qua nhiều kỳ tốt hơn một điểm

Ví dụ throughput theo tuần:

~~~text
Tuần:       W1 W2 W3 W4 W5 W6 W7 W8
Throughput:  9 13 11  8 12 10 14  9
~~~

Từ W4 lên W5 là 8 → 12, tăng 50% trong một tuần, nhưng chuỗi dài hơn cho thấy dao động 8–14 item/tuần. **Chỉ một bước tăng chưa chứng minh hệ thống được cải thiện bền vững**.

Đội có thể dùng run chart, control chart khi điều kiện phù hợp, so phân phối và quan sát đủ nhiều kỳ; cần chú thích khi policy, DoD, công cụ hoặc loại item đổi.

### 9.3. Khoảng bất định và percentile

Khi báo tỷ lệ thành công hoặc quantile cycle time, có thể cần:

- Quy mô mẫu và khoảng thời gian.
- Phân phối/biến động theo kỳ.
- Khoảng tin cậy hoặc bootstrap nếu phù hợp với giả định dữ liệu.
- Phân loại item/cohort.
- Mức độ tương quan giữa các quan sát (ví dụ cùng một người thử nhiều lần).

**Không bắt buộc tính một khoảng tin cậy cho mọi stand-up.** Nhưng nếu kết quả được dùng cho quyết định lớn, cần tránh trình bày một ước lượng mỏng manh như sự thật chính xác.

### 9.4. So sánh nhiều chỉ số làm tăng nguy cơ chọn “điểm sáng”

Nếu dashboard có 40 chỉ số, đôi khi một số sẽ biến động mạnh **chỉ do ngẫu nhiên**. Sau đó đội chỉ chọn con số tốt nhất để chứng minh một thực hành có ích là một dạng **cherry-picking**.

**Cách giảm:** xác định trước một vài chỉ số chính và guardrails gắn với giả thuyết; báo cả tín hiệu trái chiều, không chỉ biểu đồ được chọn sau khi thấy kết quả.

### 9.5. Mùa vụ và sự kiện bất thường

Nền tảng học trực tuyến có thể có:

- **Cao điểm khai giảng:** lượng đăng ký/khắc phục giao dịch tăng.
- **Chiến dịch marketing:** nhiều người dùng mới, hành vi khác nhóm cũ.
- **Tuần nghỉ lễ:** năng lực team, đối tác và lịch phản hồi thay đổi.
- **Sự cố đối tác:** cycle time, availability và ticket khẩn tăng.
- **Release lớn/migration:** công việc không giống chu kỳ bình thường.

Khi so sánh trước–sau, ghi các biến cố và thử xem cùng mùa/cùng loại việc/cùng điều kiện nếu có. Không mặc định tuần nào cũng đại diện cho tuần khác.

## 10. Tương quan, nguyên nhân và thử nghiệm cải tiến

Một chỉ số thay đổi **sau** khi áp dụng thực hành mới không tự chứng minh **vì** thực hành đó.

### 10.1. Những thay đổi đồng thời thường bị bỏ sót

Giả sử trong một tháng, đội:

- Áp dụng WIP limits.
- Nâng cấp CI để giảm thời gian chờ build.
- Thêm một Developer giàu kinh nghiệm.
- Loại bỏ một phụ thuộc API đã gây lỗi nhiều lần.
- Chuyển từ các feature tích hợp lớn sang chỉnh sửa nội dung nhỏ.

Cycle time giảm. **WIP limits có thể đóng góp**, nhưng dữ liệu trước–sau thuần túy không tách riêng được ảnh hưởng của từng thay đổi.

**Kết luận phù hợp:** “Nhóm thay đổi nhiều điều và quan sát cycle time giảm; cần phân tích loại việc, WIP, độ trễ CI và phụ thuộc trước khi khẳng định phần đóng góp của từng cơ chế.”

### 10.2. Ba mức độ kết luận nên dùng

| Mức | Ví dụ câu nói | Bằng chứng cần có |
|---|---|---|
| **Mô tả** | “Median cycle time của các item Done giảm từ 8 còn 6 ngày theo định nghĩa hiện tại.” | Dữ liệu được kiểm tra, phép đo đúng |
| **So sánh có điều kiện** | “Các PBI tương đồng giảm median cycle time trong ba kỳ sau thay đổi, không thấy chất lượng giảm theo chỉ số đang theo dõi.” | Cùng định nghĩa, phân nhóm, đủ kỳ, guardrails |
| **Suy luận nguyên nhân** | “Giảm WIP đã góp phần làm cycle time thấp hơn.” | Thiết kế kiểm chứng tác động và loại bớt lời giải thích thay thế |

Không cần mọi retrospective phải chứng minh nhân quả ở mức nghiên cứu khoa học, nhưng phải **nói đúng mức chắc chắn** để tránh quyết định sai.

### 10.3. Thử nghiệm có kiểm soát khi khả thi

Nếu sản phẩm và an toàn cho phép, đội có thể thử:

- **A/B testing** cho trải nghiệm người dùng, với phân bổ hợp lý và metric được định nghĩa trước.
- **Phát hành theo cohort** để quan sát phản hồi và giảm ảnh hưởng.
- **Thử một workflow policy** trong phạm vi dịch vụ đủ độc lập, theo dõi trước–sau có đối chứng phù hợp nếu có.
- **Interrupted time series** hoặc run chart với chú thích sự kiện thay đổi.

Cần cẩn trọng:

- Đội và người dùng có thể không độc lập, tạo ảnh hưởng chéo.
- Thời gian quan sát quá ngắn và dữ liệu quá ít không đủ kết luận.
- Một lỗi an toàn không được đem A/B trên người dùng thật chỉ để lấy số.
- Thay metric sau khi nhìn kết quả có thể tạo thiên lệch.
- Thử nghiệm không tự khắc phục lỗi chất lượng dữ liệu.

### 10.4. Không có đối chứng vẫn có thể học, nhưng phải khiêm tốn

Một đội nhỏ có thể không thể chạy A/B hoặc giữ một nhóm đối chứng. Họ vẫn có thể:

1. Nêu **giả thuyết** cụ thể trước khi thay đổi.
2. Chọn một số tín hiệu chính và guardrails.
3. Ghi đường cơ sở với định nghĩa nhất quán.
4. Thực hiện thay đổi trong phạm vi nhỏ.
5. Quan sát đủ kỳ so sánh.
6. Tìm lời giải thích thay thế.
7. Quyết định giữ/sửa/dừng và công bố bất định.

Đây là **học theo dữ liệu**, không phải phép chứng minh chắc chắn.

## 11. Đừng bỏ chất lượng và outcome để đổi lấy một số flow đẹp

Nếu mục tiêu là giao phần mềm hữu ích và đáng tin, một cải tiến flow chỉ thực sự có ý nghĩa khi **không làm xấu các điều kiện quan trọng khác**.

### 11.1. Bộ chỉ số cân bằng

| Nhóm | Tín hiệu có thể xem | Câu hỏi |
|---|---|---|
| **Flow** | WIP, throughput, work item age, cycle time, SLE | Công việc đi đến Done thế nào? |
| **Chất lượng** | DoD đạt, lỗi hồi quy, sự cố sau release, kiểm chứng bảo mật | Done có đáng tin và an toàn không? |
| **Outcome người dùng** | Tỷ lệ học viên vào bài đầu, lỗi tác vụ, phản hồi hỗ trợ | Sản phẩm có giải quyết vấn đề thực không? |
| **Năng lực duy trì** | CI reliability, thời gian sửa lỗi, mức công việc khẩn, tải nhân sự | Đội có thể tiếp tục cải tiến bền vững không? |
| **Bằng chứng dữ liệu** | Missing rate, duplicate rate, data freshness, metric version | Số liệu có đáng tin để ra quyết định không? |

Không nên cộng năm nhóm này thành một “Agile score 86/100” nếu không có mô hình được kiểm chứng. Một lỗi phân quyền nghiêm trọng **không thể được bù** bằng throughput cao.

### 11.2. Guardrails là điều kiện quyết định

Ví dụ nhóm thử chia story nhỏ hơn để giảm cycle time, nhưng:

- Nếu các story nhỏ chỉ kết thúc ở UI chưa tích hợp, kết quả chưa đạt DoD.
- Nếu số ticket tăng nhưng người dùng vẫn không vào được bài, output chưa thể hiện outcome.
- Nếu bảo mật bị giảm để đẩy nhanh completion, không gọi đó là cải tiến.
- Nếu công việc bị hủy được tính Done, throughput không còn cùng ý nghĩa.

**Guardrails** có thể gồm DoD, tính toàn vẹn dữ liệu, bảo mật, chất lượng kiểm thử, độ tin cậy release, quyền người dùng và nhịp làm việc bền vững.

### 11.3. Phân biệt chuyển việc qua cột với tạo Increment

Trong Scrum, Product Backlog Item chưa đạt **Definition of Done** không thuộc Increment. Một bảng Kanban có thể ghi Done ở ranh giới dịch vụ khác nhau, nên muốn nối số item flow với Increment cần kiểm tra **ranh giới đó có bao gồm yêu cầu chất lượng hay không**.

Không phải mọi task nội bộ đều phải là PBI hay Increment độc lập; các thước đo cần giữ đúng đơn vị:

- **Task completion:** việc kỹ thuật/hoạt động đã xong.
- **PBI completed:** hạng mục backlog đã đáp ứng điều kiện được chọn, trong Scrum cần đạt DoD để thuộc Increment.
- **Increment/release:** phần sản phẩm có thể sử dụng theo chuẩn và điều kiện phát hành.
- **Outcome:** người dùng đạt kết quả thực trong bối cảnh sử dụng.

So số task Done của đội này với Increment của đội khác là **so khác đối tượng**.

## 12. Quy trình kiểm tra dữ liệu trước khi vẽ biểu đồ

Một báo cáo flow metric có thể được tạo bằng SQL, notebook, spreadsheet hoặc dashboard tool. Công cụ không thay thế **kỷ luật định nghĩa và kiểm tra**.

### 12.1. Bản ghi tối thiểu cho một work item

Một bảng phân tích minh họa có thể có:

| Trường | Chức năng |
|---|---|
| \`item_id\` | Định danh ổn định để không đếm trùng |
| \`work_type\` | Bug, feature/PBI, incident, spike... |
| \`workflow_version\` | Phiên bản trạng thái và ranh giới áp dụng |
| \`created_at\` | Lúc yêu cầu được tạo; không tự là started |
| \`started_at\` | Lúc item thực sự bước vào WIP |
| \`done_at\` | Lúc đạt điều kiện Done của workflow |
| \`status_at_cutoff\` | Trạng thái tại thời điểm chốt dữ liệu |
| \`reopened_count\` | Số lần mở lại theo chính sách |
| \`parent_id\` | Quan hệ phân nhỏ/gộp để phát hiện đếm trùng |
| \`service_id\` | Dòng giá trị/dịch vụ thuộc phạm vi đo |
| \`blocked_flag\` hoặc blocked events | Trạng thái điểm chặn/độ tuổi liên quan |
| \`data_version\` | Nguồn và lần xây dữ liệu phân tích |

Nếu dữ liệu nguồn là event log, bảng này nên được **suy ra theo chính sách lịch sử** thay vì tự ý chọn timestamp ngẫu nhiên.

### 12.2. Một bộ dữ liệu nhỏ để phát hiện lỗi

Giả sử dashboard lấy các record sau, với \`cutoff\` là một thời điểm đã thống nhất:

| ID | Type | Started | Done | Status | Ghi chú |
|---|---|---|---|---|---|
| F-01 | Feature | Ngày 01 | Ngày 04 | Done | Đạt DoD |
| F-02 | Feature | Ngày 02 | Ngày 05 | Done | Đạt DoD |
| F-03 | Feature | Ngày 03 | — | Blocked | Vẫn trong WIP |
| F-04 | Feature | — | Ngày 06 | Done | Thiếu start |
| F-04 | Feature | — | Ngày 06 | Done | Dữ liệu trùng bản ghi |
| F-05 | Feature | Ngày 07 | Ngày 06 | Done | Thời gian không hợp lệ |
| B-01 | Bug | Ngày 04 | Ngày 05 | Canceled | Không phải Done chức năng |

Trước khi tính:

- **F-04** không thể cho cycle time đáng tin vì thiếu start và xuất hiện trùng.
- **F-05** cần điều tra thứ tự timestamp hoặc timezone; không lấy duration âm.
- **F-03** cần hiện trong WIP và work item age.
- **B-01** không được tự tính throughput nếu chỉ là canceled.
- **F-01/F-02** có thể được tính khi ranh giới ngày và DoD đã xác nhận.

**Không nên chỉ xóa mọi hàng “xấu” rồi báo kết quả tốt hơn.** Cần biết dữ liệu xấu tập trung ở loại công việc nào, vì nếu các item khó thường thiếu timestamp thì kết quả còn lại sẽ thiên lệch.

### 12.3. Một số phép kiểm tra tự động đơn giản

Ví dụ SQL minh họa trên bảng phân tích \`work_item_fact\`:

~~~sql
-- 1. Kiem tra trung ID trong bang mong doi mot dong moi item.
SELECT item_id, COUNT(*) AS n
FROM work_item_fact
GROUP BY item_id
HAVING COUNT(*) > 1;

-- 2. Tim item Done thieu moc thoi gian de tinh cycle time.
SELECT item_id, work_type, started_at, done_at
FROM work_item_fact
WHERE status_at_cutoff = 'Done'
  AND (started_at IS NULL OR done_at IS NULL);

-- 3. Tim duration nguoc thu tu.
SELECT item_id, started_at, done_at
FROM work_item_fact
WHERE started_at IS NOT NULL
  AND done_at IS NOT NULL
  AND done_at < started_at;

-- 4. Kiem tra work_type bi thieu theo tung workflow.
SELECT workflow_version, work_type, COUNT(*) AS n
FROM work_item_fact
GROUP BY workflow_version, work_type
ORDER BY workflow_version, work_type;
~~~

**Lưu ý:** đây là SQL minh họa để người học hình dung kiểm tra dữ liệu; tên bảng/trường là giả định, không phải truy vấn dùng trực tiếp cho mọi tool. Nếu bảng chứa nhiều event cho một item, truy vấn đầu tiên không tự chứng minh lỗi: cần xây bảng **một item một dòng tại cutoff** hoặc truy vấn sự kiện với khóa phù hợp.

### 12.4. Đối chiếu nguồn dữ liệu khác nhau

Đừng giả định trạng thái \`Done\` trong issue tool luôn có cùng nghĩa với:

- Pull request merged.
- CI checks passed.
- Increment đáp ứng Definition of Done.
- Tính năng đã được deploy.
- Người dùng đã có quyền sử dụng.

Các sự kiện khác nhau là **các mốc khác nhau**. Một bản ghi đối chiếu có thể:

~~~text
ITEM F-21:
  Ticket: Done 2026-05-07
  Pull Request: Merged 2026-05-06
  CI: Integration test fail 2026-05-07
  DoD evidence: chua day du
  Release: chua co

KET LUAN:
  Khong tu coi ticket Done la Increment dat DoD.
  Can kiem tra quy tac workflow va chinh sua/chu thich.
~~~

Không phải mỗi PBI phải phát hành riêng ngay sau DoD; trong Scrum, Increment có thể đạt DoD mà chưa được phát hành. Cần phân biệt **Done**, **released** và **outcome** theo đúng mục tiêu đo.

### 12.5. Phân biệt sự kiện đến muộn với thông tin được sửa

Một ETL pipeline có thể cập nhật sự kiện của tuần cũ sau khi chốt báo cáo. Đội có thể chọn:

- **Số liệu as-of cutoff:** báo trạng thái được biết ở ngày chốt, giữ nguyên phiên bản để truy vết.
- **Số liệu restated:** tính lại lịch sử khi biết event mới, gắn version và giải thích chênh lệch.

Chính sách nào cũng có công dụng; điều sai là **thay đổi số lịch sử im lặng** rồi dùng nó để chứng minh một quyết định trước đó là chính xác.

### 12.6. Kiểm tra tính hợp lệ của metric pipeline bằng test

Một số test minh họa:

~~~text
TEST-A:
  Given item Started roi Done
  Then throughput = 1, cycle time = Done - Started

TEST-B:
  Given item Started roi Blocked nhung chua Done
  Then throughput = 0, WIP van bao gom item, Age van tang

TEST-C:
  Given mot event Done bi gui lap cung event_id
  Then throughput khong tang hai lan

TEST-D:
  Given item Done roi Reopened vi khong dat DoD
  Then chinh sach rework va Done cuoi duoc ap dung nhat quan

TEST-E:
  Given completed_at < started_at
  Then ban ghi bi danh dau can kiem tra, khong tinh duration am

TEST-F:
  Given workflow_version doi start/end
  Then bao cao phan biet metric version, khong noi chuoi sai
~~~

Chất lượng của **pipeline đo lường** cũng phải được kiểm tra. Nếu metrics được tự động hóa nhưng SQL sai, cả tổ chức có thể ra quyết định dựa trên dữ liệu méo với tốc độ rất nhanh.

## 13. Tình huống xuyên suốt: “Throughput tăng 50%” ở đội ghi danh khóa học

> **Toàn bộ số liệu, tên item và diễn biến trong tình huống sau là giả định để học tập**, không phải số liệu vận hành thực tế hay tiêu chuẩn đánh giá một Scrum Team/Kanban team.

Đội phát triển module ghi danh khóa học dùng Scrum với Sprint hai tuần và bổ sung các thực hành Kanban để kiểm soát WIP. Họ áp dụng TDD/CI cho logic cấp quyền và nhắm mục tiêu người học có thể đăng ký, thanh toán hợp lệ và vào bài đầu an toàn.

Sau một đợt cải tiến, dashboard cho thấy:

<table>
<tr><th>Chỉ số được báo</th><th>4 tuần trước</th><th>4 tuần sau</th></tr>
<tr><td>Ticket Done</td><td>96</td><td>144</td></tr>
<tr><td>Throughput trung bình</td><td>24/tuần</td><td>36/tuần</td></tr>
<tr><td>Median cycle time (báo cáo)</td><td>8 ngày</td><td>5 ngày</td></tr>
<tr><td>Test count</td><td>800</td><td>1.100</td></tr>
</table>

Lãnh đạo đọc là “50% throughput, 37,5% cycle time tốt hơn và thêm 300 test”. Nhưng nhóm kiểm tra lại các điều kiện.

### 13.1. Phát hiện 1 — Không cùng định nghĩa Done

Trước thay đổi:

~~~text
Done = Da tich hop + kiem chung + dap ung DoD.
~~~

Sau thay đổi, một số thẻ đi qua:

~~~text
Development -> Code Complete (= Done cho dashboard)
            -> Waiting Verification -> Actual Done
~~~

Phần chờ Verification **biến mất khỏi cycle time được báo** dù công việc chưa đạt DoD. Số ticket Done tăng không tương đương Increment hoàn tất.

**Hành động:** không sửa dashboard bằng cách tự gán “chất lượng sau tăng”; trước tiên thống nhất lại điểm End và tính lại lịch sử nếu raw events cho phép.

### 13.2. Phát hiện 2 — Đơn vị item thay đổi

Trước kỳ cải tiến, một số PBI gồm UI, API, DB và kiểm thử trong một hạng mục; kỳ sau nhóm tách subtask rồi đưa cả subtask vào throughput.

Ví dụ kiểm kê:

| | Trước | Sau |
|---|---:|---:|
| Ticket Done trên dashboard | 96 | 144 |
| Item được xác nhận thuộc tập đơn vị **PBI/bug so sánh được** | 64 | 70 |
| Những ticket khác (subtask, task, trạng thái khác) | 32 | 74 |
| Số PBI thực sự đạt DoD trong kỳ (ví dụ giả định) | 18 | 20 |

**Lưu ý:** các hàng không phải phân loại song song cùng một khái niệm ở mọi tool; bảng minh họa cách **đối chiếu đơn vị** để tránh đếm một phần việc như một kết quả độc lập. Số PBI Done **18 → 20** có thể là cải thiện, nhưng **không chứng minh năng suất tăng 50%**.

### 13.3. Phát hiện 3 — Những item khó chưa Done bị bỏ khỏi cycle time

Đội sau có:

- Nhiều hạng mục nhỏ đã Done nhanh.
- Ba hạng mục tích hợp đối tác đang blocked với work item age **16, 21 và 25 ngày**.

Cycle time trung vị của item đã Done có thể giảm nhưng người dùng vẫn chờ khả năng cốt lõi. Nếu chỉ báo 5 ngày rồi bỏ age, dashboard tạo **tranh ảnh thiếu phần đuôi khó**.

**Hành động:** thêm work item age/blocked của item mở, đặc biệt theo rủi ro, độ lớn và mục tiêu sản phẩm.

### 13.4. Phát hiện 4 — Loại việc và tải đã khác

Đợt trước có nhiều feature tích hợp nhà cung cấp thanh toán và thay mô hình quyền; đợt sau nhiều sửa giao diện, thông báo và bug nhỏ. Số lượng item dễ Done tăng. Đồng thời CI đã được nâng cấp và hai người mới gia nhập.

**Hành động:** báo số theo **work type/service/cohort** với kích cỡ mẫu; ghi những thay đổi đồng thời. Không tự quy toàn bộ chênh lệch cho WIP limit.

### 13.5. Phát hiện 5 — Outcome chưa chắc tốt hơn

Lãnh đạo hỏi: “Nếu ticket nhiều hơn thì học viên vào bài dễ hơn chưa?” Đội nhìn dữ liệu sản phẩm:

| Tín hiệu giả định | Trước | Sau | Điều kiện cần kiểm tra |
|---|---:|---:|---|
| Tỷ lệ học viên đủ điều kiện vào bài đầu | 88% | 90% | Cùng định nghĩa cohort, cửa sổ và kênh? |
| Lỗi nghiêm trọng được xác nhận sau release | 2 | 1 | Mức ảnh hưởng, lượng người dùng và khả năng phát hiện? |
| Số ticket hỗ trợ về thanh toán | 80 | 76 | Lượng giao dịch, thay cách ghi ticket và mức độ phức tạp? |
| Độ trễ phản hồi trạng thái PENDING | Chưa có SLI | Có SLI | Không thể tính % cải thiện khi trước chưa đo |

Các tín hiệu có thể hữu ích, nhưng vẫn cần **mẫu số và điều kiện tương đồng**. Ví dụ ticket hỗ trợ giảm từ 80 xuống 76 không đủ kết luận trải nghiệm tốt hơn nếu số đơn giảm một nửa.

### 13.6. Một báo cáo sau kiểm tra có trách nhiệm

> **Quan sát ban đầu:** throughput ticket tăng 24 → 36/tuần, median cycle time dashboard giảm 8 → 5 ngày.
>
> **Kiểm tra chất lượng dữ liệu:** cách chia item và điểm Done đã thay đổi; một số ticket bị tính hoàn tất trước Verification. Có item đang mở với age 16–25 ngày.
>
> **Dữ liệu so sánh lại:** số PBI đạt DoD trong các kỳ minh họa tăng 18 → 20; chưa đủ cơ sở quy đổi thành năng suất phần trăm. Các work types và năng lực/CI cũng thay đổi.
>
> **Kết luận hỗ trợ được:** đội đã thay đổi cách tổ chức công việc và một số tín hiệu cải thiện; chưa thể khẳng định WIP limit tạo mức tăng 50% về khả năng giao phần mềm.
>
> **Điều cần làm:** ổn định metric contract, loại khỏi throughput các đơn vị không tương đồng, báo WIP/age/DoD/outcome, kiểm chứng phụ thuộc và xem xu hướng qua thêm chu kỳ.

Đây là báo cáo **có ích cho lãnh đạo hơn một con số phấn khởi nhưng không tin cậy**, vì nó cho biết điều gì có thể dùng để ra quyết định và điều gì chưa thể.

### 13.7. Bảng kế hoạch cải tiến sau phân tích

| Vấn đề | Hành động | Bằng chứng kỳ vọng | Guardrail |
|---|---|---|---|
| Done không nhất quán | Thống nhất DoD/End boundary và version metric | Không còn ticket “Done” khi chưa đạt điều kiện đo | Không hạ chất lượng |
| Subtask bị đếm lẫn | Gắn loại item, parent-child; báo riêng | So sánh cùng loại item | Không xóa thông tin công việc nhỏ có ích |
| Item blocked bị che | Hiện WIP và work item age | Hạng mục già tuổi được xử lý sớm | Không chuyển blocked khỏi WIP |
| Work mix biến động | Phân nhóm bug/feature/integration, nêu số mẫu | Báo cáo có thể giải thích cơ cấu | Không chọn nhóm sau khi thấy số đẹp |
| Outcome chưa đủ tin | Metric contract cho hành trình vào bài | Có tử/mẫu số, cohort, độ trễ và nguồn | Không loại người dùng gặp lỗi vô lý |
| Cải tiến khó quy nguyên nhân | Ghi thay đổi CI, nhân lực, workflow | Có bối cảnh để đánh giá dần | Không tuyên bố nhân quả quá mức |

## 14. Một quy trình tám bước để kết luận và ra quyết định

Quy trình dưới đây là **checklist thực dụng** cho báo cáo Agile metrics quan trọng, không phải sự kiện bắt buộc của Scrum, Kanban hay XP.

### Bước 1 — Nêu quyết định trước khi chọn KPI

Ví dụ:

> “Có nên tiếp tục dùng WIP limit hiện tại để giảm thời gian chờ Verification mà vẫn giữ Increment đạt DoD không?”

Không bắt đầu bằng mục tiêu “làm cho biểu đồ xanh hơn”.

### Bước 2 — Đọc metric contract và xác định population

Xác nhận:

- Đối tượng là PBI, bug hay item của workflow nào?
- Start/Done ở đâu?
- Cửa sổ quan sát và timezone nào?
- Có item reopen/canceled/subtask không?
- Chỉ số giúp quyết định gì và không cho biết điều gì?

Nếu không có metric contract, **viết bản tối thiểu trước khi so**.

### Bước 3 — Chạy các phép kiểm tra dữ liệu

Kiểm tra:

- Mốc thời gian thiếu, âm hoặc sai timezone.
- Trùng ID/event.
- Status không hợp lệ hoặc Done không nhất quán.
- Số lượng item mở, blocked và late arriving data.
- Tỷ lệ dữ liệu thiếu theo work type/cohort.
- Nguồn và phiên bản truy vấn.

Nếu tỷ lệ thiếu hoặc sai có thể làm lệch kết luận, **tạm dừng kết luận mạnh** và ghi mức ảnh hưởng.

### Bước 4 — Đối chiếu với nguồn và người thực hiện công việc

Chọn một số item đại diện, kiểm tra history, CI/release, DoD và trường hợp blocked. Hỏi nhóm có thay cách dùng tool hoặc đổi quy trình nhập dữ liệu không.

**Không lấy trải nghiệm cá nhân làm bằng chứng thay số liệu**, nhưng dùng nó để phát hiện lỗi ngữ nghĩa trong dữ liệu.

### Bước 5 — Xác định điều kiện so sánh

So:

- Ranh giới workflow, Done và đơn vị.
- Độ dài cửa sổ, lịch và seasonality.
- Loại việc, độ lớn, mức tải, phụ thuộc.
- Nhân sự, tool, CI/CD và chính sách.
- Cohort, denominator và data maturity.

Nếu không đủ tương đồng, **phân nhóm, chuẩn hóa khi có cơ sở hoặc giới hạn câu kết luận**.

### Bước 6 — Xem phân phối, đuôi và tín hiệu trái chiều

Không chỉ lấy trung bình. Với flow, báo **median/percentiles (có phương pháp), WIP, item age, throughput**; với outcome, báo **tử/mẫu số, cohort và độ tin cậy đo**; với chất lượng, xem **sự cố và rủi ro còn mở**.

Một item già tuổi hoặc lỗi an toàn nghiêm trọng cần được thấy, không bị trung bình che.

### Bước 7 — Viết kết luận theo đúng mức chắc chắn

Mẫu câu:

> “Trong khoảng A–B, với PBI loại X theo metric contract v2, median cycle time của các item Done giảm từ M xuống N. Hai kỳ có cùng DoD và ranh giới start/end; nhưng loại tích hợp và nhân lực có thay đổi, và còn K item mở đã quá SLE. Vì vậy đây là **tín hiệu để tiếp tục điều tra/cải tiến**, chưa phải bằng chứng chắc chắn rằng một thực hành đơn lẻ đã gây ra mức giảm.”

Không cần cố nhồi nhiều thuật ngữ thống kê; cần **trung thực về điều đã đo và điều chưa biết**.

### Bước 8 — Chọn một hành động và mốc kiểm chứng lại

Ví dụ:

> “Trong ba chu kỳ tới, đội thử giảm WIP ở Development theo năng lực Verification, giữ DoD, theo dõi work item age của item blocked và số Increment hoàn tất. Sau đó đối chiếu cùng loại việc, chất lượng và outcome để quyết định giữ hoặc điều chỉnh.”

Chỉ số chỉ tạo giá trị khi giúp **thay đổi hành vi có kiểm soát và học từ kết quả**, không phải khi chỉ tăng số biểu đồ được lưu.

## 15. Cách viết một báo cáo Agile metrics có khả năng kiểm toán

### 15.1. Mẫu báo cáo ngắn

~~~text
CAU HOI CAN QUYET DINH:
  [Vi du: WIP limit co giam blocked va tang Increment Done khong?]

PHAM VI / DON VI:
  [Team/service, item type, version workflow]

DINH NGHIA:
  [Start, Done/DoD, cua so, timezone, ty le neu co]

NGUON:
  [Issue event history, CI, release, product analytics]

DATA CUT-OFF:
  [Thoi diem chot, late events, kha nang restatement]

KIEM TRA DATA:
  Missing:
  Duplicate:
  Invalid timestamps:
  Reopened/canceled:
  Blocked/open age:
  Query/metric version:

DIEU KIEN SO SANH:
  [Work mix, item granularity, capacity, seasonality, dependencies]

KET QUA:
  [Bang so + phan phoi + co cau + so mau]

GUARDRAILS:
  [DoD, regression, security, reliability, outcome]

KET LUAN DUOC HO TRO:
  [Mo ta hay so sanh co dieu kien, muc chac chan]

KHONG THE KET LUAN:
  [Nguyen nhan, nhom khac, tuong lai... neu chua co evidence]

HANH DONG VA MOC XEM LAI:
  [Quyet dinh, owner, su kien/ky danh gia]
~~~

Không phải mỗi buổi Daily Scrum cần báo cáo theo mẫu này; nó phù hợp hơn với **retrospective, operational review, cải tiến hệ thống, điều chỉnh cam kết hoặc quyết định nhân rộng quy trình**.

### 15.2. Mẫu bảng kiểm tra trước khi gửi dashboard

| Kiểm tra | Ví dụ ghi nhận |
|---|---|
| **Metric version** | CycleTime.v2, Done = DoD |
| **Đơn vị** | PBI/bug riêng, không gộp subtask |
| **Cửa sổ** | 4 tuần lịch, timezone UTC+07 |
| **Số mẫu** | N item Done theo từng nhóm |
| **Missing/invalid** | 2 item thiếu start; đã xác minh hoặc loại có chú thích |
| **Open/blocked** | 5 item trong WIP, 2 vượt ngưỡng age cần xem |
| **Reopen/canceled** | Xử lý theo chính sách, không đếm Done trùng |
| **Work mix** | Feature 40%, bug 50%, spike 10%; so kỳ trước |
| **Bối cảnh** | Có sự cố nhà cung cấp và thay công cụ CI |
| **Guardrails** | DoD không đổi; security issue chưa mở rộng |
| **Kết luận** | Mô tả được mức thay đổi, nêu giới hạn |

### 15.3. Các câu hỏi người phản biện dashboard nên hỏi

- Nếu item blocked nằm ngoài bảng, con số còn đại diện cho workflow không?
- Vì sao chọn window này thay vì một khoảng dài hơn?
- Nếu dùng cùng định nghĩa Done cho hai kỳ, kết quả còn như cũ không?
- Nếu chỉ xét feature tích hợp, xu hướng còn giữ không?
- Có chỉ số nào đổi chiều khi xét theo cohort?
- Có thay đổi số lượng người dùng hoặc điều kiện tải?
- Trong tổng số item, bao nhiêu item thực sự tạo Increment có thể dùng?
- Nếu số tăng vì đo được lỗi nhiều hơn, chúng ta có đang phạt khả năng phát hiện tốt hơn?
- Số liệu có được dùng để hỗ trợ đội hay tạo áp lực chỉnh ticket?
- Người ra quyết định có biết điều chưa được đo không?

### 15.4. Ngôn ngữ kết luận tránh lạm dụng

| Tránh nói | Nên nói khi phù hợp dữ liệu |
|---|---|
| “Đội tăng năng suất 50%” | “Số item Done/tuần tăng 50% theo metric contract đang dùng; cần kiểm tra granularity và DoD” |
| “Cycle time giảm, mọi thứ đều nhanh hơn” | “Cycle time của các item đã Done giảm; WIP age của item mở còn cần xem” |
| “Kanban làm hiệu quả tăng” | “Sau thay đổi chính sách và một số điều kiện khác, các chỉ số flow có tín hiệu cải thiện; chưa tách nguyên nhân” |
| “99% test pass nghĩa là chất lượng 99%” | “99% các test được chọn chạy đạt trong build/môi trường cụ thể; một số rủi ro còn chưa kiểm tra” |
| “Tỷ lệ ghi danh tốt hơn 10%” | “Tỷ lệ từ X lên Y theo cùng tử/mẫu số và cohort; cần xem mức sử dụng, bối cảnh” |
| “Không có bug nên chất lượng hoàn hảo” | “Không có lỗi được ghi nhận trong cửa sổ này theo cơ chế phát hiện hiện có” |

## 16. Dự báo Agile: dữ liệu lịch sử phải đủ so sánh được trước khi dự báo tương lai

Một đội thường muốn biết “chúng ta hoàn tất bao nhiêu item trong bốn tuần tới?” hoặc “hạng mục này có khả năng hoàn tất trong bao lâu?”. Có thể dùng dữ liệu throughput/cycle time làm đầu vào **dự báo**, nhưng cần nhớ **dự báo phụ thuộc điều kiện và tính đại diện của lịch sử**.

### 16.1. Vì sao một trung bình không phải cam kết?

Giả sử throughput trong năm tuần của một luồng công việc tương đối ổn định:

~~~text
3, 5, 4, 4, 6 item/tuần
~~~

Trung bình:

\[
\overline{T}=\frac{3+5+4+4+6}{5}=4{,}4\text{ item/tuần}
\]

Nếu backlog còn 22 item tương đối cùng loại và không thêm việc mới:

\[
\frac{22}{4{,}4}=5\text{ tuần}
\]

**Năm tuần chỉ là phép chia trung bình thô**, không phải lời hứa 100% hoặc một khoảng dự báo có xác suất. Nó chưa xét:

- Sự khác biệt về độ lớn/độ phức tạp.
- Item bị blocked hoặc phụ thuộc bên ngoài.
- Sự cố, nghỉ phép và biến động năng lực.
- Việc mới xuất hiện và thay đổi ưu tiên.
- Sự thay đổi DoD, workflow hoặc cách chia item.
- Sai lệch dữ liệu và mẫu lịch sử chỉ có năm tuần.

**Kiểm tra:** với các item còn lại, liệu loại việc và cách chia có tương đồng với dữ liệu quá khứ? Nếu không, một phép chia đẹp không có ý nghĩa dự báo.

### 16.2. Dự báo xác suất cần phân phối và giả định

Một nhóm có thể dùng mô phỏng dựa trên lịch sử throughput (ví dụ mô phỏng Monte Carlo) để ước lượng **phân phối các ngày có thể hoàn tất**, thay vì một ngày duy nhất.

Nhưng mô phỏng không khắc phục:

- Lịch sử bị đếm task/parent không nhất quán.
- Thay đổi WIP limits hoặc chính sách Done giữa các kỳ.
- Backlog tương lai gồm các feature lớn chưa được chia nhưng lịch sử chỉ có bug nhỏ.
- Một đối tác sắp ngừng hoạt động hoặc năng lực giảm mạnh.
- Mẫu lịch sử quá ít hoặc bị chọn vì “trông đẹp”.

Không nên trình bày “85% hoàn tất trước ngày D” nếu mô hình và dữ liệu không có cơ sở cho mức xác suất đó. Cần nêu **cửa sổ lịch sử, population, cách lấy mẫu, điều kiện cố định và rủi ro ngoài mô hình**.

### 16.3. Little's Law là quan hệ có điều kiện, không phải phép màu

Trong hệ thống dòng công việc ổn định đủ điều kiện, **Little's Law** liên hệ trung bình WIP, throughput rate và thời gian trong hệ thống:

\[
L = \lambda W
\]

Trong đó:

- \(L\): trung bình số item trong hệ thống (WIP theo ranh giới đã chọn).
- \(\lambda\): throughput rate trung bình trong cùng hệ thống.
- \(W\): thời gian trung bình item ở trong hệ thống.

Ví dụ minh họa nếu hệ thống đủ ổn định:

\[
L=12\ \text{items},\quad \lambda=3\ \text{items/ngày}
\]

\[
W=\frac{12}{3}=4\ \text{ngày}
\]

Không dùng quan hệ này để khẳng định mọi item mất đúng bốn ngày. Nó liên quan **giá trị trung bình dài hạn với các giả định phù hợp**; thực tế có phân phối và rủi ro chờ. Hơn nữa:

- WIP và throughput phải cùng **ranh giới workflow và loại item hợp lý**.
- Không lấy một ảnh chụp WIP cuối ngày thay trung bình cả kỳ mà không xem sai lệch.
- Nếu hệ thống đang tích lũy backlog/WIP không ổn định, diễn giải phải thận trọng.
- Không dùng công thức để ép team đóng thẻ sớm hơn DoD.

Một phép toán đúng nhưng điều kiện áp dụng sai có thể là nguồn của dự báo tệ.

### 16.4. Cumulative Flow Diagram (CFD) và đổi chính sách

**CFD** có thể giúp nhìn số lượng item ở các bước workflow theo thời gian và phát hiện hàng chờ tăng. Nhưng nếu đội:

- Thêm/xóa cột trạng thái.
- Thay ranh giới Ready/Started.
- Chuyển nhóm item blocked sang một workflow khác.
- Nhập nhiều item lịch sử cùng lúc.

Biểu đồ có thể đổi hình do **cách thu thập và định nghĩa**, không hoàn toàn do dòng công việc cải thiện. Hãy gắn sự kiện đổi policy vào biểu đồ và xem lại nguyên liệu trước khi suy luận.

### 16.5. Cách sử dụng dự báo có trách nhiệm

Một dự báo tốt trả lời:

1. **Chúng ta dự báo điều gì?** Item Done, Increment đạt DoD hay khả năng người dùng nhận được?
2. **Lịch sử nào được dùng?** Thời kỳ, loại việc, version metric, cách chia.
3. **Điều kiện nào cần giữ?** Năng lực, phụ thuộc, WIP, DoD và phạm vi.
4. **Mức chắc chắn là bao nhiêu?** Khoảng hoặc kịch bản nếu có cơ sở.
5. **Khi nào cập nhật?** Khi xuất hiện thông tin mới về backlog, dữ liệu hoặc môi trường.

Trong Agile, dự báo để **hỗ trợ lựa chọn và phối hợp**, không phải dùng dữ liệu thô để bắt mọi điều kiện trở nên chắc chắn.

## 17. Hai mươi phản mẫu khi diễn giải Agile metrics

### 17.1. “Tính được thì chắc chắn đúng”

**Sai lầm:** chỉ kiểm tra công thức, bỏ qua dữ liệu thiếu/trùng/khác định nghĩa.

**Hướng xử lý:** kiểm tra chất lượng dữ liệu, lineage, population và metric contract trước khi xem kết quả.

### 17.2. “Cùng tên metric nghĩa là cùng định nghĩa”

**Sai lầm:** cycle time từ In Progress → Code Complete được so với Started → DoD.

**Hướng xử lý:** công bố start/end/DoD, version metric và điểm đứt chuỗi.

### 17.3. “Ticket Done nhiều hơn là năng suất nhiều hơn”

**Sai lầm:** đếm cả subtask, parent, item canceled hoặc Code Complete.

**Hướng xử lý:** làm rõ đơn vị item, dedup, work type và Increment/outcome; báo mục tiêu tương ứng.

### 17.4. “Bỏ item bị chặn thì cycle time đẹp hơn”

**Sai lầm:** chỉ báo item Done nhanh, giấu những item đã già tuổi trong WIP.

**Hướng xử lý:** báo song song work item age, WIP và blocked, không đánh tráo population.

### 17.5. “Không có timestamp nghĩa là 0 ngày”

**Sai lầm:** biến \`NULL\` thành 0 để tính trung bình.

**Hướng xử lý:** phân biệt thiếu dữ liệu, không áp dụng và thời gian thực sự bằng 0; điều tra tính thiên lệch.

### 17.6. “Reopen vẫn được cộng một Done nữa”

**Sai lầm:** tăng throughput vì cùng một item đóng hai lần.

**Hướng xử lý:** theo dõi lifecycle, chính sách Done cuối và rework riêng.

### 17.7. “WIP trên bảng không bao gồm blocked”

**Sai lầm:** chuyển blocked sang bảng ẩn, xem như đã giải phóng năng lực.

**Hướng xử lý:** item đã bắt đầu chưa Done vẫn thuộc WIP của workflow; chỉ thay ranh giới có chủ đích và ghi version.

### 17.8. “Số lỗi giảm nghĩa là chất lượng tăng”

**Sai lầm:** ngừng logging hoặc giảm điều kiện báo lỗi, vẫn tuyên bố sản phẩm tốt hơn.

**Hướng xử lý:** xem cả khả năng phát hiện, mức độ nghiêm trọng, phạm vi người dùng và cửa sổ quan sát.

### 17.9. “Đội A có velocity cao nên hơn đội B”

**Sai lầm:** so story points không có thang đo chung.

**Hướng xử lý:** giữ velocity làm dữ liệu dự báo nội bộ khi hữu ích; không dùng so năng suất giữa đội.

### 17.10. “Có một tuần tốt là quy trình mới thành công”

**Sai lầm:** biến động tự nhiên được xem là cải tiến bền vững.

**Hướng xử lý:** nhìn nhiều kỳ, phân phối, dữ liệu theo cùng định nghĩa và sự kiện bất thường.

### 17.11. “Hai giai đoạn có cùng tổng mẫu nên so được”

**Sai lầm:** tổng 200 người trước/sau nhưng cơ cấu đơn giản–phức tạp đổi mạnh.

**Hướng xử lý:** kiểm tra cohort/work mix và nguy cơ Simpson's paradox.

### 17.12. “Tỷ lệ tăng vì sản phẩm tốt hơn”

**Sai lầm:** mẫu số thay đổi, loại người dùng thất bại hoặc đổi tiêu chí hoàn tất.

**Hướng xử lý:** metric contract cho tử/mẫu số, tiêu chí loại trừ và cửa sổ.

### 17.13. “Dữ liệu từ CI và issue tool luôn giống nhau”

**Sai lầm:** merged, Done, released và user outcome bị xem cùng một mốc.

**Hướng xử lý:** xác định rõ sự kiện từng nguồn và cơ chế đối chiếu.

### 17.14. “Median tốt nên mọi item đều tốt”

**Sai lầm:** bỏ phần đuôi dài, outlier và item còn mở.

**Hướng xử lý:** báo phân phối, percentile có phương pháp, age/blocked và rủi ro item quan trọng.

### 17.15. “Đã tính Little's Law nên cam kết ngày chắc chắn”

**Sai lầm:** dùng trung bình và giả định ổn định để hứa một ngày duy nhất.

**Hướng xử lý:** nêu điều kiện hệ thống, phân phối, bất định và xem lại dự báo.

### 17.16. “Sau thay đổi nghĩa là do thay đổi”

**Sai lầm:** gán hết chênh lệch cho Kanban/XP/Scrum trong khi CI, năng lực và loại việc đổi.

**Hướng xử lý:** ghi confounders, dùng thử nghiệm/so sánh hợp lý và kết luận theo mức chắc chắn.

### 17.17. “Chỉ số nào đẹp nhất cũng là bằng chứng”

**Sai lầm:** theo dõi hàng chục KPI rồi chọn chỉ số tăng nhiều nhất.

**Hướng xử lý:** xác định trước metrics chính và guardrails; báo cả tín hiệu bất lợi.

### 17.18. “Nếu số không đẹp, đổi định nghĩa Done”

**Sai lầm:** cải thiện báo cáo bằng cách chuyển QA ra ngoài workflow.

**Hướng xử lý:** giữ minh bạch và chất lượng; giải quyết điểm nghẽn thực thay vì thay nhãn cột.

### 17.19. “Dữ liệu kỳ gần nhất luôn đã đầy đủ”

**Sai lầm:** kết luận conversion giảm vì người dùng vừa đăng ký chưa đủ thời gian hoàn tất, hoặc event đến muộn.

**Hướng xử lý:** data cutoff, maturity window, late events và chính sách restatement.

### 17.20. “Mọi metric đều nên đưa vào KPI cá nhân”

**Sai lầm:** dùng throughput, velocity hoặc defect count để xếp hạng cá nhân, tạo động lực tối ưu cục bộ.

**Hướng xử lý:** dùng dữ liệu để hỗ trợ **cải tiến hệ thống và quyết định sản phẩm**, không khuyến khích chỉnh số, bỏ test hoặc né item khó.

## 18. Workshop: phản biện một dashboard trước khi quyết định

Một workshop 75–90 phút có thể giúp Product Owner, Developers, Scrum Master, người phụ trách dữ liệu và người có chuyên môn kiểm thử cùng thực hành. Đây là **hoạt động học tập gợi ý**, không phải event Scrum bắt buộc.

### 18.1. Bối cảnh

Nhóm có dashboard:

~~~text
AGILE KPI DASHBOARD
Period A: 20 ticket Done/tuần, median cycle time 9 ngày
Period B: 34 ticket Done/tuần, median cycle time 5 ngày
Test pass rate: 99%
User completion: 82% -> 86%

TUYEN BO:
  "Áp dụng Kanban giúp đội nhanh hơn 70% và chất lượng tốt hơn."
~~~

Người hướng dẫn phát lần lượt các thẻ thông tin:

- **Thẻ 1:** Ở period B, Done chuyển từ DoD sang Code Complete.
- **Thẻ 2:** Một số PBI được tách thành bốn subtask và đều được tính.
- **Thẻ 3:** Sáu item khó vẫn blocked hơn 20 ngày và không có trong cycle time.
- **Thẻ 4:** Period B có chiến dịch thu hút người dùng mới; tỷ lệ khóa miễn phí/trả phí đổi.
- **Thẻ 5:** Một số integration tests fail nhưng bị loại khỏi CI chính.
- **Thẻ 6:** Nâng cấp CI và thay một đối tác thanh toán cũng diễn ra cùng kỳ.

### 18.2. Các vòng hoạt động

| Thời lượng | Hoạt động | Kết quả |
|---|---|---|
| **0–10 phút** | Nêu quyết định lãnh đạo định đưa ra | Một câu hỏi đo lường rõ |
| **10–25 phút** | Kiểm tra metric contract, DoD, unit và dữ liệu thiếu | Danh sách lỗi định nghĩa/dữ liệu |
| **25–40 phút** | Phân loại item, xem open WIP và age, so cohort | Bảng so sánh có điều kiện |
| **40–55 phút** | Phân tích nguyên nhân có thể và chất lượng | Các lời giải thích thay thế/guardrails |
| **55–70 phút** | Soạn báo cáo mới và quyết định tiếp theo | Kết luận hỗ trợ được, mức bất định |
| **70–85 phút** | Thiết kế thử nghiệm và kế hoạch đo lại | Giả thuyết, owner, mốc kiểm tra |
| **85–90 phút** | Tóm tắt bài học | Một hành động cải tiến dữ liệu |

### 18.3. Vai trò

**Product Owner:** Đưa mục tiêu người dùng và quyết định ưu tiên; hỏi liệu học viên có vào bài đầu tốt hơn không.

**Developers:** Làm rõ ranh giới start/end và ý nghĩa Done; giải thích thay đổi cách chia PBI và tác động CI.

**Scrum Master/người cải tiến flow:** Hỏi về WIP, blocked, tuổi item, nguyên nhân thực của tắc nghẽn và sự phối hợp.

**Người phân tích dữ liệu:** Kiểm tra mẫu số, dữ liệu thiếu, timestamp, trùng ID, work mix, metric version và Simpson.

**Người kiểm thử/vận hành:** Xác nhận điều kiện chất lượng, các test bị bỏ và lỗi người dùng chịu ảnh hưởng.

### 18.4. Tiêu chí đánh giá bài làm

Một báo cáo tốt:

1. Không tự dùng throughput ticket để khẳng định năng suất cá nhân.
2. Phát hiện Done đổi định nghĩa và phân biệt DoD với Code Complete.
3. Kiểm tra các item mở/blocked thay vì chỉ completed items.
4. Đối chiếu loại việc và cách chia item giữa hai kỳ.
5. Tách dữ liệu outcome theo population/cohort hợp lý.
6. Nêu ảnh hưởng có thể có của CI/đối tác/thay đổi khác.
7. Giữ guardrails về bảo mật, chất lượng và người dùng.
8. Đưa ra quyết định có giới hạn, mốc xem lại và nguồn dữ liệu cần cải thiện.

## 19. Bài tập vận dụng

### Bài tập A — “Done” khác nhau giữa hai kỳ

Một đội có dữ liệu:

| | Trước | Sau |
|---|---:|---:|
| Ticket được gắn Done | 50 | 80 |
| Định nghĩa Done | Đạt DoD | Code Complete |
| Item còn chờ Integration/QA | 0 trong nhóm Done | 25 trong nhóm Done |

**Yêu cầu:** Có thể kết luận throughput thực sự tăng 60% không? Hãy đưa ra cách tính/diễn giải phù hợp hơn.

<details>
<summary>Gợi ý đáp án</summary>

Không thể so 50 và 80 như cùng một throughput vì ranh giới Done thay đổi. Nếu trong 80 ticket sau có 25 chưa đạt DoD, thì số **đã đáp ứng DoD** tối đa là 55 trong giả định không còn điều kiện khác; cần xác nhận từng item và tránh đếm trùng. Nếu 55 là số hoàn tất thực, so 50 → 55 là tăng 10% về số item đạt DoD trong phạm vi được xác minh, **vẫn chưa chứng minh năng suất hoặc giá trị tăng 10%** vì còn khác granularity, loại việc và năng lực. Tốt nhất tính lại lịch sử bằng một metric contract thống nhất và báo rõ giới hạn.

</details>

### Bài tập B — Cycle time của item Done và work item age

Trong một tuần, bốn item cùng loại đã Done có cycle time **2, 3, 4, 7 ngày**. Hai item chưa Done có work item age **14 và 18 ngày**.

**Yêu cầu:** Tính trung vị của các item Done. Có thể nói “toàn bộ công việc hiện mất trung vị 3,5 ngày” không? Nêu báo cáo đúng.

<details>
<summary>Gợi ý đáp án</summary>

Trung vị của các item Done là \((3+4)/2=3{,}5\) ngày. Không thể nói toàn bộ item trong hệ thống đều có cycle time trung vị 3,5 ngày, vì hai item mở chưa có cycle time cuối và đã 14/18 ngày tuổi. Cần báo “Median cycle time của bốn item Done là 3,5 ngày; đồng thời còn hai item WIP tuổi 14 và 18 ngày, cần xem tình trạng blocked và rủi ro”. Nên dùng thêm throughput, WIP, SLE và các kỳ khác trước khi kết luận cải tiến.

</details>

### Bài tập C — Kiểm tra trùng ID và tình trạng canceled

Báo cáo raw events có:

~~~text
Item A: Started -> Done
Item B: Started -> Done
Item B: Duplicate Done event
Item C: Started -> Canceled
Item D: Started -> Blocked
~~~

**Yêu cầu:** Nếu chính sách throughput chỉ đếm item thực sự đạt Done đúng một lần và không tính canceled, throughput là bao nhiêu? WIP gồm item nào tại cutoff, giả sử các trạng thái cuối như trên?

<details>
<summary>Gợi ý đáp án</summary>

Throughput = **2 item** (A và B). B có hai Done event nhưng là một item; C bị canceled không phải item Done theo quy tắc; D đang blocked vẫn thuộc WIP nếu started và chưa Done. Nếu workflow coi canceled là đã rời hệ thống, C không còn trong WIP theo ranh giới đã công bố, nhưng cần báo riêng số canceled khi hữu ích. Không cộng cùng một work item hai lần.

</details>

### Bài tập D — Dữ liệu thiếu gây thiên lệch

Một đội có 40 item Done, trong đó 8 item thiếu \`started_at\`. Cả 8 item thiếu đều thuộc loại **tích hợp đối tác**, còn 32 item có dữ liệu thuộc các bug nhỏ.

**Yêu cầu:** Tỷ lệ thiếu là bao nhiêu? Có thể bỏ 8 item rồi báo cycle time trung bình đại diện cho cả đội không?

<details>
<summary>Gợi ý đáp án</summary>

Tỷ lệ thiếu là \(8/40\times100\%=20\%\). Không nên bỏ rồi kết luận cho toàn đội: missingness tập trung ở loại việc thường phức tạp, nên mẫu còn lại có thể có cycle time thấp không đại diện. Cần tìm event lịch sử để khôi phục mốc start nếu có, báo tỷ lệ thiếu theo work type và chỉ giới hạn kết luận cho 32 bug đủ dữ liệu khi phù hợp; nâng chất lượng ghi nhận trước khi so cả đội.

</details>

### Bài tập E — Phân biệt ngày lịch và ngày làm việc

Một item Started lúc **16:00 thứ Sáu** và Done lúc **10:00 thứ Hai**, cùng timezone và không có chuyển giờ trong khoảng đó.

**Yêu cầu:** Tính elapsed calendar time bằng giờ. Vì sao không thể tự quy về “1,5 ngày làm việc” mà chưa có lịch công việc?

<details>
<summary>Gợi ý đáp án</summary>

Từ thứ Sáu 16:00 tới thứ Bảy 00:00 là 8 giờ, hai ngày cuối tuần 48 giờ, từ thứ Hai 00:00 tới 10:00 là 10 giờ; tổng \(8+48+10=66\) giờ = 2,75 ngày 24 giờ. “Ngày làm việc” phụ thuộc giờ làm, ngày nghỉ, ca kíp và định nghĩa đo. Nếu team làm 09:00–17:00, kết quả có thể khác nếu một ngày nghỉ đặc biệt hoặc on-call; không tự lấy calendar time so với working time.

</details>

### Bài tập F — Tỷ lệ tổng trái chiều theo nhóm

Giả sử:

| | Trước thành công/tổng | Sau thành công/tổng |
|---|---|---|
| Đăng ký đơn giản | 90/100 | 19/20 |
| Đăng ký phức tạp | 20/100 | 45/180 |

**Yêu cầu:** Tính tỷ lệ tổng trước/sau; kết luận gì khi mỗi nhóm đều tăng nhưng tổng giảm?

<details>
<summary>Gợi ý đáp án</summary>

Đơn giản tăng 90% → 95%, phức tạp tăng 20% → 25%, nhưng tổng trước \((90+20)/(100+100)=55\%\), tổng sau \((19+45)/(20+180)=32\%\). Cơ cấu sau chuyển mạnh về nhóm phức tạp nên tỷ lệ tổng giảm dù tỷ lệ mỗi nhóm tăng; đây là tình huống Simpson's paradox. Phải báo phân nhóm, cơ cấu và số mẫu; không tuyên bố sản phẩm chắc chắn xấu đi chỉ từ tỷ lệ tổng, cũng không tuyên bố mọi thứ tốt hơn dựa trên các nhóm nếu còn thay đổi khác.

</details>

### Bài tập G — Chuẩn hóa trọng số

Dùng dữ liệu Bài tập F. Giả sử tổ chức muốn đánh giá hai kỳ với cơ cấu chuẩn **50% yêu cầu đơn giản, 50% yêu cầu phức tạp**.

**Yêu cầu:** Tính tỷ lệ chuẩn hóa trước/sau. Giải thích vì sao không được chọn trọng số sau khi thấy kết quả chỉ để làm số đẹp.

<details>
<summary>Gợi ý đáp án</summary>

Trước \(0{,}5\times90\%+0{,}5\times20\%=55\%\). Sau \(0{,}5\times95\%+0{,}5\times25\%=60\%\). Theo trọng số chuẩn đã nêu, tỷ lệ tăng 5 điểm phần trăm. Trọng số phải phản ánh population/điều kiện muốn kết luận và được công bố, không điều chỉnh tùy tiện để tạo xu hướng mong muốn. Cần lưu ý mẫu nhóm đơn giản sau chỉ 20 và còn bất định.

</details>

### Bài tập H — Báo cáo tỷ lệ hoàn tất của cohort chưa trưởng thành

Chỉ số đo học viên vào bài đầu trong **24 giờ sau ghi danh**. Báo cáo chốt 17:00 hôm nay nhưng đưa cả học viên ghi danh lúc 16:30 vào mẫu số “không hoàn tất trong 24 giờ”.

**Yêu cầu:** Đây là lỗi gì và cách sửa hợp lý?

<details>
<summary>Gợi ý đáp án</summary>

Đây là lỗi **cửa sổ theo dõi chưa đủ thời gian** (immature cohort/right censoring). Học viên đăng ký lúc 16:30 mới có 30 phút, chưa đủ điều kiện kết luận không hoàn tất trong 24 giờ. Có thể chỉ tính cohort đã qua đủ 24 giờ kể từ sự kiện bắt đầu hoặc dùng phương pháp phân tích thời gian phù hợp; công bố cutoff, late events và cách loại trừ nhất quán, không loại chọn lọc sau khi thấy số.

</details>

### Bài tập I — Dự báo 22 item từ throughput

Lịch sử năm tuần: **3, 5, 4, 4, 6 item/tuần**. Backlog hiện có 22 item.

**Yêu cầu:** Tính throughput trung bình và dự báo chia thô. Nêu tối thiểu bốn điều kiện phải kiểm tra trước khi dùng làm kế hoạch.

<details>
<summary>Gợi ý đáp án</summary>

Trung bình \((3+5+4+4+6)/5=4{,}4\) item/tuần; 22/4,4 = **5 tuần** là dự báo trung bình thô. Phải kiểm tra loại/kích thước item, granularity, DoD/Done, nguồn và chất lượng lịch sử, WIP/blocked, năng lực nhân sự, phụ thuộc, sự cố và liệu có item mới xuất hiện. Không coi năm tuần là lời hứa; cần xem phân phối và cập nhật dự báo khi có bằng chứng mới.

</details>

### Bài tập J — Little's Law và điều kiện áp dụng

Một workflow có WIP trung bình **15 item** và throughput trung bình **3 item/ngày** trong một giai đoạn đủ ổn định.

**Yêu cầu:** Tính thời gian trung bình suy từ Little's Law; giải thích vì sao kết quả không chứng minh mỗi item sẽ hoàn tất trong đúng số ngày đó.

<details>
<summary>Gợi ý đáp án</summary>

Với \(L=\lambda W\), \(W=L/\lambda=15/3=5\) ngày. Đây là quan hệ giá trị trung bình trong điều kiện hệ thống đủ ổn định và ranh giới/đơn vị đo nhất quán. Các item cụ thể có phân phối khác nhau, có thể chờ lâu hoặc bị blocked. Snapshot WIP đơn lẻ không thay trung bình thích hợp; không dùng công thức làm ngày cam kết không điều kiện.

</details>

### Bài tập K — Hai giai đoạn thay đổi đồng thời nhiều thứ

Sau khi đội áp dụng WIP limits, họ cũng tăng nhân sự, nâng cấp CI và dừng tích hợp một API hay lỗi. Median cycle time giảm.

**Yêu cầu:** Có thể khẳng định WIP limits là nguyên nhân duy nhất không? Đề xuất câu kết luận và kế hoạch học tiếp.

<details>
<summary>Gợi ý đáp án</summary>

Chưa thể quy toàn bộ thay đổi cho WIP limits vì có các confounders. Có thể nói “median cycle time giảm trong giai đoạn có nhiều cải tiến đồng thời; cần kiểm tra loại việc, DoD, WIP, CI và phụ thuộc để xem khả năng đóng góp của từng thay đổi”. Hãy cố định metric contract, quan sát nhiều kỳ, phân nhóm item, xem guardrails và thử một chính sách nhỏ trong phạm vi có thể so sánh, không tuyên bố quan hệ nhân quả quá mức.

</details>

### Bài tập L — Velocity khác thang đo

Đội A hoàn tất **50 story points/Sprint**, đội B hoàn tất **30 story points/Sprint**. Cả hai đều dùng Planning Poker nhưng tự hiệu chỉnh thang điểm theo lịch sử riêng.

**Yêu cầu:** Có thể kết luận đội A năng suất hơn 67% không? Tín hiệu nào phù hợp hơn với quyết định cải tiến?

<details>
<summary>Gợi ý đáp án</summary>

Không. Story points không phải đơn vị chuẩn giữa các đội, nên tỷ lệ \(50/30\) không đo năng suất chéo đội. Nên xem mục tiêu sản phẩm, khả năng tạo Increment đạt DoD, rủi ro, chất lượng, outcome và flow trong **bối cảnh từng hệ thống**; khi so cùng một thực hành, cần kiểm tra cùng workflow, loại việc và định nghĩa. Velocity có thể dùng để hỗ trợ đội tự dự báo nếu thang nội bộ ổn định.

</details>

### Bài tập M — Phản biện quality scorecard

Một báo cáo gồm:

~~~text
Test pass: 99%
Ticket Done: +40%
Cycle time: -25%
Security incident: 1 loi lo du lieu chua xu ly
Users cannot access first lesson: van con
~~~

Quản lý muốn lấy trung bình ba chỉ số đầu và tuyên bố Agile đạt kết quả xuất sắc.

**Yêu cầu:** Bạn sẽ phản hồi thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Không thể bù một rủi ro dữ liệu nghiêm trọng bằng test pass hoặc throughput cao. Cần xác minh và xử lý security incident trong phạm vi có thẩm quyền; không coi 99% test pass là chất lượng 99%. Cần kiểm tra metric contract và Done cho số ticket/cycle time, đồng thời nhìn outcome người dùng chưa đạt. Báo theo guardrails, rủi ro và bằng chứng trước khi đưa ra quyết định phát hành/cải tiến.

</details>

### Bài tập N — Soạn báo cáo trung thực cho Prime/Leadership

Tổ chức muốn áp dụng một chính sách mới cho mọi đội vì đội thí điểm báo throughput tăng. Bạn biết đội thí điểm có:

- 4 tuần quan sát.
- Cách chia ticket đổi.
- Một số item blocked vẫn chưa Done.
- CI được cải thiện đồng thời.
- Chưa có dữ liệu outcome đáng tin.

**Yêu cầu:** Viết một đoạn báo cáo ngắn, nêu được điều quan sát, điều chưa biết và bước tiếp theo.

<details>
<summary>Gợi ý đáp án</summary>

Một mẫu hợp lý:

> “Trong bốn tuần thí điểm, throughput ticket theo dashboard tăng. Tuy nhiên cách chia ticket đã đổi, có các item mở bị chặn và CI được cải thiện đồng thời; dữ liệu outcome còn thiếu. Vì vậy chưa đủ bằng chứng kết luận chính sách mới làm tăng năng lực giao sản phẩm, cũng chưa đủ căn cứ nhân rộng toàn tổ chức. Đề xuất thống nhất metric contract/DoD, theo dõi WIP age, chất lượng và outcome, so cùng loại việc qua thêm các chu kỳ, rồi quyết định điều chỉnh hoặc mở rộng dựa trên tín hiệu đã kiểm chứng.”

Đoạn báo cáo không cần giả vờ có số liệu mà người viết không sở hữu. Sự trung thực về giới hạn là một phần của chất lượng quyết định.

</details>

## 20. Checklist tự đánh giá trước khi kết luận từ Agile metrics

Chọn **một kết luận có ảnh hưởng thực** — ví dụ “chu kỳ phát triển nhanh hơn”, “đội có thể nhận thêm việc”, “chất lượng đã cải thiện” — và kiểm tra:

### 20.1. Chất lượng dữ liệu

1. Có biết chính xác **nguồn dữ liệu**, lần cập nhật và phiên bản truy vấn không?
2. Các item/sự kiện trong population có **đầy đủ** không?
3. Trường start/end của item dùng tính duration có bị thiếu không?
4. Có timestamp ngược thứ tự, sai timezone hoặc định dạng không hợp lệ không?
5. Event Done có bị nhận lặp hoặc ID trùng không?
6. Có phân biệt item canceled, duplicate, split, merged và reopen không?
7. Tỷ lệ dữ liệu thiếu có khác nhau theo loại việc/đội/cohort không?
8. Có trường hợp \`NULL\` bị biến thành 0 không?
9. Có event đến muộn khiến kỳ gần nhất thiếu dữ liệu không?
10. Có chính sách data cutoff và tính lại lịch sử khi cần không?
11. Những giá trị bất thường đã được điều tra, không chỉ xóa cho biểu đồ đẹp?
12. Dữ liệu có thể đối chiếu một số item thật trong event history/CI/release không?

### 20.2. Định nghĩa phép đo

13. Câu hỏi/ra quyết định cần hỗ trợ có được nêu trước khi chọn KPI?
14. Metric contract có định nghĩa đơn vị quan sát và population không?
15. Ranh giới Started/Done có rõ và phù hợp workflow thực không?
16. Done có nghĩa đạt DoD hay chỉ code complete? Có được nêu rõ không?
17. WIP có tính những item blocked đã bắt đầu chưa Done không?
18. Cycle time, work item age, throughput và lead time có được phân biệt đúng không?
19. Các tỷ lệ có tử số/mẫu số và điều kiện loại trừ công khai không?
20. Khoảng thời gian, timezone, calendar vs working time được công bố không?
21. Percentile và các cách thống kê có ghi phương pháp, số mẫu không?
22. Các số đo có kết nối với **Increment, chất lượng hoặc outcome** thay vì chỉ task count không?

### 20.3. Điều kiện so sánh

23. Hai kỳ có cùng **metric version, Done và loại item** không?
24. Nếu workflow đổi, có khả năng tính lại hoặc phải đánh dấu điểm đứt chuỗi không?
25. Cách chia ticket/story có thay đổi làm số item không còn so được không?
26. Work mix (bug, feature, incident, spike, phụ thuộc đối tác) có tương đồng không?
27. Độ dài cửa sổ, kỳ nghỉ, cao điểm hoặc mùa vụ có được xét không?
28. Năng lực nhân sự, CI, môi trường, khách hàng và đối tác có đổi đồng thời không?
29. Có xem cả completed items và open/blocked age để tránh survivorship bias không?
30. Cohort người dùng có cùng điều kiện và đủ thời gian quan sát chưa?
31. Có kiểm tra nguy cơ Simpson's paradox bằng phân nhóm phù hợp không?
32. Trọng số chuẩn hóa hoặc điều kiện loại trừ có được chọn dựa trên mục tiêu, không chọn để làm đẹp số không?
33. Số mẫu và biến động có đủ cho mức kết luận đang đưa ra không?
34. Có tránh so story points/velocity khác đội như cùng đơn vị năng suất không?

### 20.4. Diễn giải và hành động

35. Kết luận đang **mô tả**, **so sánh có điều kiện** hay **khẳng định nguyên nhân**?
36. Có lời giải thích thay thế hợp lý nào chưa được loại trừ không?
37. Số liệu trái chiều hoặc guardrails về chất lượng/bảo mật có được nêu không?
38. Có đang dùng một chỉ số đẹp để che một rủi ro lớn không?
39. Dự báo có công bố lịch sử, loại item và giả định ổn định không?
40. Các phép tính như Little's Law hoặc Monte Carlo có được dùng đúng điều kiện không?
41. Các kết luận có ghi mức bất định và những phần chưa đo được không?
42. Đội có một hành động cải tiến cụ thể và mốc kiểm tra lại không?
43. Người có thẩm quyền về ưu tiên, chất lượng và tổ chức có tham gia quyết định phù hợp không?
44. Dữ liệu có được dùng để học và cải tiến hệ thống thay vì gây động lực chỉnh số/xếp hạng cá nhân không?

**Nếu chưa trả lời được nhiều câu, đừng viết “chắc chắn cải thiện”.** Có thể thay bằng “quan sát ban đầu cho thấy…”, công bố khoảng trống và ưu tiên thu thập/chuẩn hóa những dữ liệu quyết định trước.

## 21. Tổng kết

- **Dữ liệu đúng công thức chưa chắc tạo ra kết luận đúng.** Phải kiểm tra dữ liệu nguồn, tính hợp lệ của phép đo, điều kiện so sánh và mức độ chắc chắn.
- **Metric contract là nền tảng:** một đơn vị, một ranh giới Started/Done, một cửa sổ, một quy tắc loại trừ, một nguồn và một phiên bản rõ ràng.
- **Flow metrics phải đọc cùng nhau.** Throughput nhiều hơn không tự là giá trị nhiều hơn; cycle time của item Done giảm không có nghĩa những item blocked đã hết rủi ro. Cần WIP, work item age và phân phối.
- **Scrum, Kanban và XP không được thay bằng dashboard.** DoD và Increment phản ánh chất lượng, Kanban giúp nhìn dòng việc, XP giúp phản hồi sớm qua kỹ thuật; số lượng task/test không thay chúng.
- **Hai kỳ phải có điều kiện so sánh được** về DoD, cách chia item, loại việc, năng lực, thời gian, cohort và cách thu dữ liệu. Nếu đổi, cần phân nhóm, tính lại hoặc công bố giới hạn.
- **Simpson's paradox và selection bias là rủi ro thực.** Tỷ lệ tổng có thể đảo chiều khi cơ cấu công việc/người dùng thay đổi; chỉ lấy completed items dễ che phần khó còn mở.
- **Đừng quy nguyên nhân chỉ từ trước–sau.** CI, nhân sự, mùa vụ và phụ thuộc có thể thay đổi cùng lúc. Hãy kết luận theo đúng mức bằng chứng.
- **Dự báo cần điều kiện và bất định.** Trung bình, percentile, Little's Law hay mô phỏng không biến tương lai thành lời hứa chắc chắn.
- **Chất lượng và outcome là guardrails.** Không thể đánh đổi an toàn, DoD hoặc khả năng người dùng hoàn tất tác vụ để tăng ticket Done.
- **Đo lường Agile hữu ích khi thay đổi quyết định và cải thiện hệ thống**, không khi tối ưu biểu đồ hoặc xếp hạng cá nhân.

Trước khi gửi một biểu đồ với tiêu đề **“Hiệu suất tăng”**, hãy tự hỏi:

> **“Số liệu đã đầy đủ và đúng nguồn chưa? Hai kỳ có đang đếm cùng một điều không? Những item/người dùng nào không xuất hiện trong mẫu? Có nguyên nhân khác giải thích chênh lệch không? Người dùng và chất lượng thực nhận được gì?”**

Nếu có thể trả lời minh bạch, dữ liệu trở thành **công cụ kiểm tra và thích ứng đáng tin**, đúng tinh thần Agile: phản hồi sớm, giao giá trị tăng dần và cải tiến liên tục.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị Agile về phần mềm hoạt động, tương tác, hợp tác với khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm thường xuyên, coi phần mềm hoạt động là thước đo tiến triển chủ yếu và cải tiến liên tục.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, kiểm soát WIP, bốn flow metrics và Service Level Expectation.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Goal, Sprint Goal, Definition of Done, Increment, Scrum events và cơ chế minh bạch–kiểm tra–thích ứng.
- [Scrum.org — Evidence-Based Management](https://www.scrum.org/resources/evidence-based-management): góc nhìn thực nghiệm về giá trị, khả năng giao giá trị và cải thiện tổ chức; cần xem ngữ cảnh khi lựa chọn phép đo.
- [DORA](https://dora.dev/): nghiên cứu và tài liệu về năng lực giao phần mềm, thay đổi và vận hành; cần dùng định nghĩa chính thức của từng metric.
- **Daniel S. Vacanti — _Actionable Agile Metrics for Predictability_**: quản lý dòng công việc qua cycle time, age, throughput, WIP và dự báo dựa trên dữ liệu.
- **Douglas W. Hubbard — _How to Measure Anything_**: tư duy về bất định, định nghĩa phép đo và cách dùng dữ liệu khi ra quyết định.
- **Donald T. Campbell & Julian C. Stanley — _Experimental and Quasi-Experimental Designs for Research_**: các mối đe dọa đối với suy luận nguyên nhân–kết quả; tham khảo khi thiết kế so sánh trước–sau hoặc thử nghiệm.
- [Google SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/): cách định nghĩa chỉ số dịch vụ và mục tiêu chất lượng khi liên kết với kết quả vận hành.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): đặc tả hành vi bằng ví dụ, hữu ích để phân biệt điều kiện chấp nhận với bằng chứng test đã chạy.




