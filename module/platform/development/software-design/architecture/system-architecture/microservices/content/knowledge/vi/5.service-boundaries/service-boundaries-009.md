# Ghi nhận và quản lý sự tiến hóa ranh giới theo thời gian

## 1. Ranh giới dịch vụ là một quyết định có vòng đời

Trong kiến trúc Microservices, **ranh giới dịch vụ (service boundary)** xác định phần trách nhiệm nghiệp vụ, mô hình, dữ liệu, hợp đồng tích hợp và quyền vận hành thuộc về một dịch vụ. Ranh giới được chọn tại một thời điểm dựa trên hiểu biết hiện có về miền nghiệp vụ, tốc độ thay đổi, mô hình tổ chức và các yêu cầu phi chức năng. Những yếu tố đó có thể đổi theo thời gian; vì vậy ranh giới ban đầu không nên được xem là một cấu trúc bất biến.

Một thiết kế tách dịch vụ có thể hợp lý khi hệ thống chỉ có hàng nghìn đơn hàng mỗi ngày, nhưng sau đó trở nên bất tiện khi xuất hiện thanh toán trả góp, kênh đối tác, hoàn tiền nhiều bước hoặc nhiều đội phát hành song song. Ngược lại, hai dịch vụ từng cần tách để vận hành riêng có thể trở nên quá nhỏ và thường xuyên phải thay đổi cùng nhau khi sản phẩm thu hẹp.

**Quản lý sự tiến hóa ranh giới** là quá trình có chủ đích gồm:

1. **Ghi nhận** ranh giới đang tồn tại, lý do lựa chọn và những giả định lúc thiết kế.
2. **Theo dõi** tín hiệu thực tế cho thấy ranh giới còn phù hợp hay đang cản trở thay đổi.
3. **Đánh giá** các phương án giữ nguyên, tách, hợp nhất, chuyển trách nhiệm hoặc thay đổi cách tích hợp.
4. **Tiến hóa an toàn** thông qua hợp đồng tương thích, chuyển quyền sở hữu dữ liệu, kế hoạch chuyển đổi và quan sát vận hành.
5. **Cập nhật lại quyết định và bản đồ miền** để mô hình tài liệu phản ánh hệ thống sau thay đổi.

Mục tiêu là giữ cho các năng lực nghiệp vụ có **tính kết dính cao (high cohesion)** và **mức phụ thuộc ngoài ranh giới được kiểm soát (low coupling)**, đồng thời bảo đảm hệ thống có thể phát hành, kiểm thử, vận hành và thay đổi theo nhịp phù hợp với doanh nghiệp.

### 1.1. Cần phân biệt các lớp ranh giới

| Lớp ranh giới | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Nghiệp vụ | Năng lực nào và quy tắc nào thuộc cùng một trách nhiệm? | Tính phí vận chuyển thuộc Shipping hay Checkout? |
| Mô hình miền | Thuật ngữ, trạng thái và bất biến nào nhất quán trong một bounded context? | “Đã hoàn tất” trong Order khác “Đã đối soát” trong Payment |
| Dữ liệu | Ai có quyền ghi và xác nhận nguồn sự thật? | Payment sở hữu kết quả giao dịch; Order chỉ giữ trạng thái chiếu |
| Hợp đồng | Bên ngoài tương tác qua API/event nào? | Order gửi yêu cầu giữ hàng cho Inventory |
| Triển khai | Đơn vị nào được build, release, scale và rollback riêng? | Refund có pipeline phát hành riêng |
| Tổ chức | Đội nào chịu trách nhiệm quyết định, chất lượng và sự cố? | Nhóm Payments sở hữu giao dịch và hoàn tiền |

Các lớp này liên quan nhưng **không luôn trùng một-một**. Một bounded context có thể nằm trong một module của modular monolith; một microservice có thể triển khai nhiều mô hình nhỏ nhưng cùng một trách nhiệm. Việc chuyển ranh giới nghiệp vụ không phải lúc nào cũng cần tạo service mới. Trước khi thay đổi deployment topology, cần xác định **ranh giới nào thật sự đang gây vấn đề**.

### 1.2. Vì sao cần lịch sử thay đổi?

Nếu chỉ nhìn sơ đồ hiện tại, người đến sau dễ không biết vì sao Payment sở hữu một bảng, vì sao Order phát một sự kiện hoặc vì sao có lớp chuyển đổi giữa hai context. Khi các giả định cũ bị quên, đội ngũ có thể vô tình đưa phụ thuộc ngược trở lại.

Ví dụ, một quyết định ban đầu là để Order giữ thông tin phí vận chuyển vì mọi mức phí đều cố định theo vùng. Sau này phí tính theo kích thước gói hàng và chính sách từng hãng vận chuyển. Nếu không lưu giả định ban đầu, đội mới có thể tiếp tục bổ sung nhiều rule trong Order chỉ vì “trước giờ vẫn thế”, khiến ranh giới nghiệp vụ ngày càng sai lệch.

Lịch sử ranh giới cần giải thích **quyết định nào đã được đưa ra, dựa vào bằng chứng gì, giới hạn của quyết định và điều kiện nào khiến nó cần được xem xét lại**.

## 2. Những nguyên nhân khiến ranh giới tiến hóa

Sự tiến hóa thường bắt đầu từ thay đổi trong domain, tổ chức hoặc cách vận hành, chứ không chỉ từ ý muốn hiện đại hóa công nghệ.

### 2.1. Năng lực nghiệp vụ xuất hiện hoặc tách biệt

Một hệ thống bán hàng ban đầu có chức năng hoàn tiền đơn giản trong Payment. Sau đó doanh nghiệp hỗ trợ hoàn tiền một phần, hoàn tiền theo đợt, hoàn tiền khiếu nại và quy trình duyệt rủi ro. **Refund** lúc này có thể phát triển thành một năng lực với vòng đời, chính sách, dữ liệu và người sở hữu riêng.

Dấu hiệu chính không phải số endpoint tăng lên; đó là **tập quy tắc, thuật ngữ, nhịp phát triển và trách nhiệm riêng** đã đủ rõ để đặt một ranh giới.

### 2.2. Nhiều khả năng từng tách riêng lại thay đổi cùng nhau

Hai dịch vụ Pricing và Promotion có thể phải sửa và triển khai cùng mỗi khi thay đổi quy tắc giảm giá. Nếu các bất biến và dữ liệu của chúng luôn được cập nhật trong cùng một giao dịch nghiệp vụ, cần đặt câu hỏi liệu chúng nên là hai context riêng, hai module trong cùng một deployable, hay một năng lực hợp nhất.

Tuy nhiên, tần suất thay đổi cùng nhau chưa đủ kết luận. Có những đợt phát triển lớn mang tính tạm thời; một ranh giới cần được đánh giá qua **mẫu thay đổi lặp lại và cấu trúc nghiệp vụ**.

### 2.3. Thay đổi quy mô, độ trễ hoặc tính sẵn sàng

Một năng lực phải xử lý tải tăng đột biến hoặc có yêu cầu độ trễ khác hẳn phần còn lại có thể hưởng lợi khi triển khai và scale riêng. Ngược lại, một chuỗi gọi đồng bộ rất nhỏ giữa nhiều dịch vụ có thể làm tăng độ trễ và điểm lỗi đến mức ranh giới triển khai cần được xem lại.

Cần phân biệt **rào cản tài nguyên** với **rào cản mô hình miền**. Tối ưu query, cache, hàng đợi, capacity hoặc hợp đồng giao tiếp đôi khi giải quyết vấn đề mà không phải di chuyển trách nhiệm nghiệp vụ.

### 2.4. Quyền sở hữu đội ngũ thay đổi

Khi doanh nghiệp lập nhóm vận hành thanh toán riêng, phần nghiệp vụ thanh toán cần quyền quyết định và chu kỳ phát hành tương ứng. Nhưng không nên ép một sơ đồ đội ngũ đang thay đổi ngắn hạn thành kiến trúc cố định. Phải xem xét khả năng duy trì ownership, kỹ năng vận hành và quan hệ phối hợp giữa các nhóm.

### 2.5. Phát hiện thuật ngữ và bất biến khác biệt

Ban đầu “khách hàng” có thể chỉ là một entity dùng chung. Khi triển khai hệ thống hóa đơn, đội ngũ phát hiện “bên được xuất hóa đơn”, “người đặt hàng” và “người dùng sản phẩm” có thể là ba chủ thể khác nhau. Phát hiện ngôn ngữ miền mới làm thay đổi mô hình, nguồn sự thật và ranh giới context.

### 2.6. Hệ thống cũ hoặc tích hợp đối tác thay đổi

Chuyển đổi đối tác vận chuyển, thay ERP, di chuyển khỏi database dùng chung hoặc thay giao thức tích hợp có thể khiến một ranh giới cần được điều chỉnh. Không mặc định mỗi hệ thống bên ngoài tương ứng một service riêng. Ranh giới chống tham nhũng mô hình (**Anti-Corruption Layer**) đôi khi đã đủ để bảo vệ domain hiện tại khỏi thay đổi bên ngoài.

## 3. Nhận diện tín hiệu cần xem lại ranh giới

Để tránh refactor theo cảm tính, hãy theo dõi tín hiệu kèm **bằng chứng, mức độ lặp lại, ảnh hưởng và giả thuyết nguyên nhân**.

| Tín hiệu quan sát được | Câu hỏi điều tra | Khả năng cần xem xét |
| --- | --- | --- |
| Một tính năng thường phải sửa cùng lúc nhiều service | Các thay đổi có xuất phát từ cùng quy tắc miền không? | Ranh giới nghiệp vụ quá chia nhỏ hoặc hợp đồng quá chặt |
| Nhiều bản phát hành buộc triển khai cùng nhau | Do API phá vỡ tương thích, thư viện chung hay giao dịch xuyên service? | Thiếu tương thích hoặc ownership chưa tách |
| Service khác ghi trực tiếp bảng nội bộ | Ai thực sự có quyền bảo vệ bất biến và source of truth? | Rò rỉ ranh giới dữ liệu |
| Mỗi thay đổi nhỏ phải có nhiều đội phê duyệt | Phối hợp do quy định bắt buộc hay do ownership mơ hồ? | Ranh giới trách nhiệm chưa rõ |
| Service có nhiều domain rule khác nhau | Có nhóm quy tắc/thuật ngữ phát triển độc lập không? | Ứng viên tách context hoặc tách module |
| Nhiều service chỉ cung cấp CRUD cho cùng một mô hình | Có đang chia theo lớp kỹ thuật thay vì năng lực không? | Ứng viên hợp nhất |
| Một sự cố nhỏ làm hỏng nhiều năng lực không liên quan | Có chuỗi call, retry, timeout hoặc tài nguyên chung nào? | Cần giảm phụ thuộc vận hành; chưa chắc cần tách |
| Cùng thuật ngữ nhưng nghĩa khác nhau | Người thuộc các nhóm có dùng cùng luật và trạng thái không? | Bounded context khác nhau cần được làm rõ |
| Chính sách và vòng đời mới xuất hiện | Các quy tắc mới thuộc năng lực cũ hay một subdomain mới? | Cân nhắc chuyển/tách trách nhiệm |

Một tín hiệu có thể có nhiều nguyên nhân. Ví dụ việc hai service deploy cùng lúc có thể do một chiến dịch phối hợp theo kế hoạch, không phải bằng chứng ranh giới sai. Do đó cần quan sát **chuỗi sự kiện thực, lịch sử thay đổi, sự phụ thuộc và quyết định nghiệp vụ**.

### 3.1. Chứng cứ nên thu thập

- **Change history:** các pull request, ticket, commit và bản phát hành thường xuyên đi cùng nhau.
- **Dependency graph:** lời gọi đồng bộ, luồng message, package dùng chung, truy cập database và các công việc batch.
- **Data ownership:** service nào tạo/ghi/sửa từng thực thể; service nào chỉ đọc bản chiếu hoặc đồng bộ.
- **Incident evidence:** lỗi dây chuyền, thời gian phục hồi, bước can thiệp thủ công và điểm nghẽn.
- **Domain examples:** ca thành công, thất bại, hủy, hoàn tác, xử lý chậm, đối soát và các ngoại lệ.
- **Stakeholder feedback:** người chịu trách nhiệm nghiệp vụ và vận hành có thể giải thích ranh giới hiện tại hay không.
- **Release coordination:** bao nhiêu thay đổi yêu cầu nhiều nhóm sắp lịch chung, và vì lý do gì.
- **Quality attributes:** độ trễ, throughput, tính sẵn sàng, yêu cầu giao dịch và độ phức tạp triển khai.

Không dùng một ngưỡng duy nhất như “hơn 10 endpoint thì tách” hoặc “service trên 5.000 dòng thì tách”. Những thước đo đó không tự phản ánh cohesion, tính tự chủ hay tri thức miền.

## 4. Ghi nhận đường cơ sở của ranh giới đang tồn tại

Trước khi đổi ranh giới, cần có **baseline** để biết chính xác những gì đang được di chuyển. Baseline không nhất thiết là tài liệu khổng lồ; phải đủ rõ để truy nguyên nghĩa vụ nghiệp vụ và quyền sở hữu.

### 4.1. Service boundary register

Mỗi ứng viên hoặc ranh giới đang vận hành có thể có một bản ghi:

| Trường | Ý nghĩa |
| --- | --- |
| Boundary ID | Định danh ổn định cho ranh giới, ví dụ BC-PAYMENT; không phụ thuộc tên repository |
| Tên và mô tả | Năng lực nghiệp vụ, kết quả và phạm vi trách nhiệm |
| Bounded context / subdomain | Mô hình miền áp dụng và từ ngữ quan trọng |
| Owner | Đội chịu trách nhiệm, người xác nhận quy tắc nghiệp vụ và đầu mối sự cố |
| In-scope | Những quyết định, use case, dữ liệu nằm trong ranh giới |
| Out-of-scope | Những trách nhiệm dễ nhầm nhưng thuộc bên khác |
| Source of truth | Aggregate, bảng, event hoặc mô hình dữ liệu mà context sở hữu |
| Published contracts | API, command, event, schema và cam kết tương thích |
| Consumers / dependencies | Ai phụ thuộc vào hợp đồng và các giới hạn chất lượng |
| Deployment | Đơn vị phát hành, pipeline, môi trường và phương thức khôi phục |
| Decision history | Link ADR, vấn đề mở và quyết định kế nhiệm |
| Lifecycle | Proposed, Active, Transitioning, Deprecated hoặc Retired |
| Last review / next trigger | Lần đánh giá gần nhất và điều kiện xem xét lại |

Ví dụ ngắn:

~~~yaml
boundaryId: BC-PAYMENT
name: Payment
status: Active
businessCapability: Xu ly giao dich thanh toan
ownerTeam: Payments
sourceOfTruth:
  - payment_attempt
  - transaction
publishedContracts:
  - POST /payments
  - PaymentCaptured.v1
dependencies:
  - PaymentProvider
relatedBoundaries:
  - BC-ORDER
  - BC-REFUND
decisionRecords:
  - ADR-012
lastReviewed: 2026-11-11
reviewTriggers:
  - Thay doi quy tac thu tien va hoan tien
  - Nhieu thay doi buoc phat hanh dong thoi voi Order
~~~

Đoạn YAML trên chỉ là **mẫu minh họa nội dung bản ghi**, không yêu cầu hệ thống dùng đúng trường hoặc tên file đó. Cần dùng một định dạng dễ quản lý và phù hợp công cụ hiện có của dự án.

### 4.2. Context map có phiên bản

**Context map** cho thấy các bounded context cùng quan hệ giữa chúng: ai cung cấp hợp đồng, ai tiêu thụ, nơi phải dịch ngôn ngữ miền, nơi dữ liệu được sao chép và mức phụ thuộc. Một bản đồ tốt có mốc phiên bản hoặc thời điểm hiệu lực.

Ví dụ:

~~~text
Truoc:
[Order Context]
   | goi /payments
   v
[Payment Context: Charge + Refund]
   | provider API
   v
[Payment Provider]

Sau:
[Order Context] ------> [Payment Context: Charge]
      |                       |
      | yeu cau hoan           | thong tin giao dich
      v                       v
[Refund Context] <------------+
      |
      v
[Payment Provider]
~~~

Bản đồ chỉ là mô tả tương tác; phải có chú thích hợp đồng và quyền sở hữu thực tế. Khi mô hình thay đổi, lưu lại **bản trước, bản dự kiến và bản sau** để giải thích được quá trình tiến hóa.

### 4.3. Sự khác biệt giữa hiện trạng và mục tiêu

Một ranh giới có thể trải qua nhiều tuần chuyển đổi. Đừng sửa sơ đồ hiện trạng để trông giống đích ngay từ khi có quyết định. Nên giữ ba góc nhìn:

- **Current:** thứ đang chạy trong production và nguồn dữ liệu thực sự đang được dùng.
- **Target:** ranh giới đã được chấp nhận sau khi hoàn tất chuyển đổi.
- **Transition:** các lớp tương thích, bridge, dữ liệu được đồng bộ và tuyến traffic tạm thời.

Điều này giúp người vận hành không nhầm một service đã được lên sơ đồ với một service thực sự đã có quyền sở hữu chính thức.

## 5. Lưu quyết định bằng ADR và lịch sử thay đổi

**Architecture Decision Record (ADR)** là bản ghi ngắn giải thích một quyết định kiến trúc trong bối cảnh cụ thể. Đối với tiến hóa ranh giới, ADR nên nối được **vấn đề → bằng chứng → lựa chọn → quyết định → điều kiện xem lại → kế hoạch thực hiện**.

### 5.1. Khung ADR cho thay đổi ranh giới

~~~markdown
# ADR-027: Chuyen quy tac hoan tien sang Refund Context

Status: Accepted
Decision date: YYYY-MM-DD
Owners: Payments Team, Order Team
Related boundaries: BC-PAYMENT, BC-ORDER, BC-REFUND
Supersedes: ADR-012 (phan trach nhiem hoan tien)

## Boi canh
- Business outcome can dat
- Quy tac nghiep vu moi
- Hanh vi/phu thuoc hien tai va bang chung
- Rang buoc giao dich, bao mat, van hanh

## Van de
- Thay doi nao dang bi can tro?
- Bat bien nao dang bi chia cat?

## Lua chon
1. Giu nguyen, cai tien contract va module noi bo
2. Tach Refund thanh context rieng trong cung deployable
3. Tach Refund thanh service trien khai doc lap

## Quyet dinh
- Chon phuong an ...
- Trach nhiem, du lieu, contract thuoc moi boundary
- Ly do va danh doi chap nhan

## Ke hoach chuyen doi
- Expand hop dong va schema
- Di chuyen read/write ownership
- Chuyen traffic, theo doi, xu ly rollback
- Goi deprecation va dieu kien loai bo duong cu

## Dieu kien xem xet lai
- Metrics / business trigger / risk threshold
- Ai quyet dinh tai thoi diem review

## Bang chung hoan thanh
- Contract tests
- Data reconciliation
- Release history va observability
- Owner chap nhan handoff
~~~

Có thể dùng Markdown trong repository, một hệ thống quản lý ADR hoặc wiki có version history; quan trọng là ADR **có thể tìm, liên kết và đọc lại**.

### 5.2. Vòng đời của một quyết định

| Trạng thái | Ý nghĩa |
| --- | --- |
| Proposed | Đề xuất đang khảo sát, chưa là quyết định cần áp dụng |
| Accepted | Phương án được đồng thuận trong phạm vi đã xác định |
| Implementing | Đang chuyển đổi; có thể tồn tại cả hợp đồng cũ và mới |
| Implemented | Quyền sở hữu và hành vi production phù hợp mục tiêu đã chấp nhận |
| Superseded | Quyết định mới thay thế, cần liên kết hai chiều |
| Rejected | Phương án không được chấp nhận, có ghi lý do |
| Retired | Quyết định chỉ còn giá trị lịch sử |

Không xóa ADR cũ khi thiết kế thay đổi. Hãy đánh dấu **Superseded** và liên kết tới ADR kế nhiệm. Việc giữ lịch sử giúp giải thích nguyên nhân tồn tại của một hợp đồng cũ hoặc một quyết định về migration.

### 5.3. Quyết định nào xứng đáng ghi ADR?

Ghi khi thay đổi tạo tác động đáng kể tới một hay nhiều yếu tố:

- Quyền sở hữu nghiệp vụ hoặc nguồn sự thật dữ liệu.
- Bounded context, quan hệ context map hoặc giao tiếp liên miền.
- Khả năng triển khai độc lập hay mức độ phải phối hợp nhiều đội.
- Hợp đồng công khai, cơ chế nhất quán, tính tương thích và thời hạn deprecation.
- Phương án migration có rủi ro hoặc khó đảo ngược.

Không cần ADR cho việc đổi tên biến, di chuyển class trong cùng module mà không ảnh hưởng trách nhiệm, hoặc điều chỉnh nhỏ không thay đổi quyết định kiến trúc.

## 6. Quy trình xem xét ranh giới theo thời gian

Một nhóm có thể đặt chu kỳ đánh giá theo các thay đổi lớn của sản phẩm hoặc theo đợt cải tiến kiến trúc. Đồng thời cần các **trigger theo sự kiện** để không chờ tới buổi họp định kỳ khi đã xuất hiện rủi ro.

### 6.1. Trigger nên mở phiên xem xét

- Khởi động năng lực nghiệp vụ mới hoặc thay đổi chính sách ảnh hưởng nhiều context.
- Nhiều sprint liên tiếp chứng kiến các service phải triển khai đồng thời.
- Có dữ liệu bị ghi từ nhiều service, không xác định nguồn sự thật.
- Incident lớn do phụ thuộc xuyên ranh giới, giao dịch phân tán hoặc tương thích API.
- Một đội chịu trách nhiệm mới được thành lập/giải thể hoặc chuyển ownership.
- Một context cần yêu cầu vận hành hoặc scale khác đáng kể.
- Chuẩn bị thay database, tích hợp đối tác, hoặc bỏ một hệ thống cũ.

Gắn trigger với **người phụ trách đánh giá và thời điểm quyết định**. Tránh mở cuộc tái thiết kế toàn hệ thống cho mọi thay đổi nhỏ.

### 6.2. Các bước phiên đánh giá

**Bước 1 — Tuyên bố bài toán.** Viết một câu đo được, ví dụ: “Trong ba tháng gần đây, phần lớn thay đổi chính sách hoàn tiền đòi sửa Payment và Order cùng lúc; cần xác định vì sao không có một nguồn sự thật rõ cho yêu cầu hoàn tiền.”

**Bước 2 — Thu thập bằng chứng.** Lấy case thực, diff, sơ đồ gọi, dữ liệu sự cố và câu trả lời từ chuyên gia miền.

**Bước 3 — Phân biệt root cause.** Do policy thuộc sai context, contract không tương thích, shared library, thiếu kiểm thử hay một quy trình phê duyệt quá chậm?

**Bước 4 — Đề xuất lựa chọn.** Ít nhất xét phương án giữ nguyên và cải thiện bên trong; sau đó so sánh tách, gộp hoặc chuyển trách nhiệm khi có bằng chứng.

**Bước 5 — Đánh giá trade-off.** Xét coherence của domain, tính toàn vẹn dữ liệu, thay đổi các team, chi phí vận hành, yêu cầu phối hợp, độ trễ và khả năng đảo ngược.

**Bước 6 — Ghi quyết định.** Đặt ranh giới mục tiêu, chủ sở hữu, các hợp đồng mới, thứ tự di chuyển và điều kiện thành công.

**Bước 7 — Chuyển đổi từng bước.** Thực hiện các giai đoạn tương thích, kiểm thử và quan sát thay vì chuyển tất cả cùng lúc khi không bắt buộc.

**Bước 8 — Tổng kết.** Sau khi ổn định, cập nhật boundary register, context map, ADR và runbook; đo xem vấn đề ban đầu đã được giải quyết hay chưa.

## 7. So sánh các lựa chọn tiến hóa ranh giới

Không phải mọi tín hiệu đều dẫn đến tách service. Cần đặt các lựa chọn cạnh nhau.

| Lựa chọn | Khi phù hợp | Điều cần cân nhắc |
| --- | --- | --- |
| Giữ nguyên và làm rõ module | Vấn đề nằm ở code, naming, ownership hoặc API | Có thể sửa cấu trúc trong cùng deployable trước |
| Đổi hợp đồng tích hợp | Business boundary tốt nhưng consumer ghép chặt | API version, event schema và migration consumer |
| Chuyển một trách nhiệm | Một capability thực sự thuộc context khác | Chuyển quy tắc, dữ liệu, người sở hữu và luồng lỗi |
| Tách bounded context | Hai tập ngôn ngữ và bất biến phát triển khác nhau | Context map, hợp đồng và quyền sở hữu dữ liệu |
| Tách deployment | Cần phát hành, scale hoặc cô lập vận hành độc lập | CI/CD, quan sát, bảo mật, latency và distributed data |
| Hợp nhất service | Hai service quá vụn, thường phải đổi chung | Di chuyển consumer, dữ liệu, địa chỉ API và ownership |
| Dùng Anti-Corruption Layer | Mô hình ngoài làm nhiễm mô hình miền bên trong | Chi phí chuyển đổi dữ liệu và vận hành adapter |
| Thay giao tiếp đồng bộ bằng bất đồng bộ | Cần giảm phụ thuộc thời gian và chịu được trễ | Idempotency, eventual consistency, quan sát và bù lỗi |

### 7.1. Tách một service thành hai trách nhiệm

Tách khi có **mô hình nghiệp vụ riêng, dữ liệu và người chịu trách nhiệm riêng**, cùng lợi ích về nhịp thay đổi hoặc vận hành. Tách ra để giảm số dòng code chưa đủ.

Ví dụ Payment hiện xử lý **Charge** và **Refund**. Khi Refund phát triển quy trình phê duyệt, chính sách chống gian lận và lịch đối soát riêng, có thể tạo Refund Context. Bước đầu tiên có thể chỉ là hai module với giao diện rõ trong cùng ứng dụng, rồi cân nhắc tách deployable sau khi quyền sở hữu và hợp đồng ổn định.

### 7.2. Hợp nhất hai service

Nếu Pricing và Promotion thường phải cập nhật cùng một bất biến, không có ý nghĩa nghiệp vụ độc lập và gây nhiều gọi mạng, hợp nhất có thể giảm chi phí. Khi hợp nhất, cần lập kế hoạch cho endpoint cũ, client bên ngoài, event subscriber, kho dữ liệu và lịch sử release.

Hợp nhất **không đồng nghĩa nén mọi model thành một entity lớn**. Các module nội bộ vẫn có thể giữ ranh giới rõ và chỉ thống nhất một đơn vị triển khai/ownership khi điều đó phù hợp.

### 7.3. Chuyển một capability giữa hai context

Đôi khi chỉ cần chuyển trách nhiệm tính phí từ Order sang Shipping, hoặc chuyển quy tắc eligibility của coupon từ Checkout sang Promotion. Cần xác định:

1. Quy tắc nào được chuyển và đâu là bất biến phải bảo vệ?
2. Dữ liệu nguồn sự thật nào được chuyển theo?
3. Ai sở hữu API, command, event sau khi đổi?
4. Những consumer nào có thể tiếp tục chạy hợp đồng cũ trong thời gian chuyển đổi?
5. Ai điều phối quy trình liên miền và xử lý tình trạng đang xử lý dở?
6. Khi nào chính thức ngừng quyền ghi và gỡ phần triển khai cũ?

Tên service có thể không đổi nhưng ý nghĩa ranh giới đã thay đổi. Vì vậy cần ghi ADR và cập nhật catalog dù không tạo repository mới.

## 8. Mô hình thực hiện thay đổi an toàn

Một thay đổi ranh giới là quá trình **dịch chuyển hành vi và quyền sở hữu**, không chỉ chuyển file code hoặc copy một bảng. Có thể quản lý bằng chuỗi bước với điều kiện hoàn thành rõ.

### Giai đoạn 0 — Xác định giới hạn thay đổi

- Chốt phạm vi nghiệp vụ, dữ liệu, APIs/events và những luồng được tác động.
- Chỉ rõ **invariant** phải giữ, chẳng hạn không hoàn tiền vượt số tiền đã thu.
- Liệt kê consumer, job định kỳ, reporting, batch import và tích hợp ngoài hệ thống.
- Chỉ rõ owner trước/sau, người quyết định cutover và người xử lý sự cố.
- Chụp baseline metric, trạng thái dữ liệu và dependency graph.
- Ghi ADR mục tiêu và phương án rollback hoặc roll-forward.

**Điều kiện qua bước:** mọi trách nhiệm cần chuyển đã có owner đích và cách kiểm chứng; không còn nhầm lẫn về nguồn sự thật.

### Giai đoạn 1 — Tạo ranh giới logic mới

Trước khi đưa traffic qua service mới, có thể tách module nội bộ, tạo adapter hoặc interface mới. Giữ hành vi có thể quan sát của người dùng ổn định. Viết contract tests cho giao tiếp giữa context cũ và mới.

Ví dụ trong một ứng dụng Java, thay vì để Order gọi trực tiếp repository của Payment, Order có thể phụ thuộc một cổng nghiệp vụ:

~~~java
public interface PaymentStatusPort {
    PaymentStatus currentStatus(String orderId);
}
~~~

Adapter hiện tại đọc từ hệ thống cũ. Sau khi thiết lập Payment Context có hợp đồng riêng, thay adapter bằng API client hoặc consumer event tương ứng. Ví dụ thể hiện nguyên tắc **đưa phụ thuộc qua hợp đồng**, không áp đặt mọi dự án phải dùng interface theo hình thức này.

### Giai đoạn 2 — Mở rộng hợp đồng và mô hình dữ liệu

Công bố API/event mới theo hướng **backward compatible**. Thêm các trường/cấu trúc đích mà chưa xóa trường cũ; dùng expand–migrate–contract khi thay đổi phá vỡ tương thích.

Đối với dữ liệu, tạo schema/partition hoặc kho dữ liệu cho context đích; định nghĩa cách copy, bổ sung dữ liệu mới, xử lý cập nhật phát sinh trong lúc migration và cách xác minh khớp. Tránh thao tác “di chuyển bảng rồi đổi tất cả endpoint trong một lần deploy” khi hệ thống cần liên tục phục vụ.

### Giai đoạn 3 — Chuyển luồng đọc theo từng phần

Phát triển consumer đọc dữ liệu từ hợp đồng mới. Có thể chạy **shadow read** hoặc so sánh kết quả ở môi trường giới hạn để phát hiện khác biệt, nhưng không để luồng shadow vô tình tạo hành động nghiệp vụ. Theo dõi độ trễ, tỉ lệ lỗi, sự khác biệt giá trị và quyền truy cập.

Nếu hệ thống đích chưa có toàn bộ lịch sử, cần quy tắc rõ cho dữ liệu cũ: backfill, truy vấn lưu trữ hoặc một lớp tương thích tạm thời.

### Giai đoạn 4 — Chuyển quyền ghi dữ liệu

Đây thường là giai đoạn quan trọng nhất: **mỗi sự thật nghiệp vụ phải có một chủ sở hữu ghi rõ ràng tại một thời điểm**. Cần xác định thời điểm chuyển authority và đảm bảo các request đồng thời không tạo hai bản ghi mâu thuẫn.

Các kỹ thuật có thể kết hợp gồm:

- **Single writer:** ghi chính thức qua đúng một owner; các thành phần khác gọi hợp đồng.
- **Outbox pattern:** ghi dữ liệu cục bộ và bản ghi sự kiện trong cùng giao dịch DB; tiến trình công bố sự kiện sau đó.
- **Change Data Capture (CDC):** đồng bộ thay đổi từ nguồn trong giai đoạn chuyển tiếp, có quản trị thứ tự và xử lý lỗi.
- **Idempotency:** các lệnh hoặc message bị gửi lại không tạo hiệu ứng nghiệp vụ trùng.
- **Reconciliation:** so sánh trạng thái và số liệu giữa nguồn cũ và mới theo khóa định danh, mốc thời gian và quy tắc hợp lệ.

Nếu tạm thời có **dual write**, phải chỉ rõ vì sao cần, cơ chế khôi phục sai khác và nguồn được xem là có thẩm quyền. Hai lần ghi độc lập vào hai database không tạo ra một giao dịch nguyên tử; không được giả định “gửi cả hai và đều trả thành công” là an toàn.

### Giai đoạn 5 — Cắt chuyển traffic và kiểm chứng

Chuyển một phần request/consumer có kiểm soát qua hợp đồng mới (nếu nghiệp vụ cho phép), mở rộng dần sau khi các chỉ số nằm trong giới hạn chấp nhận. Quan sát lỗi, p95/p99 latency, số yêu cầu lặp, backlog, sai lệch dữ liệu, số bản ghi cần bù và kết quả nghiệp vụ cuối.

Có một **cutover owner** và quy tắc ra quyết định cụ thể: dừng rollout, roll back đường đọc, hoặc roll forward khi đã vượt điểm không thể an toàn quay lại.

### Giai đoạn 6 — Thu hẹp đường cũ

Chỉ khi consumer đã di chuyển và dữ liệu được đối soát, mới bỏ endpoint, event, bảng và quyền truy cập cũ. Công bố lịch deprecation, theo dõi usage và xác minh không còn job/consumer chạy ngầm phụ thuộc.

**Điều kiện hoàn thành:** không còn nguồn sự thật cạnh tranh, không còn consumer bắt buộc sử dụng hợp đồng cũ, owner đích đã nhận trách nhiệm vận hành và sơ đồ hiện trạng đã được cập nhật.

## 9. Quản lý hợp đồng khi ranh giới thay đổi

Các dịch vụ có thể triển khai độc lập chỉ khi hợp đồng tương tác cho phép phiên bản cũ và mới cùng tồn tại đủ lâu trong giai đoạn chuyển đổi.

### 9.1. API synchronous

Giả sử trước kia Order đọc trực tiếp trạng thái hoàn tiền từ Payment. Sau khi Refund Context xuất hiện, nên cung cấp một API có ý nghĩa nghiệp vụ thay vì yêu cầu Order truy vấn bảng refund:

~~~http
GET /refunds/RF-1001

HTTP/1.1 200 OK
Content-Type: application/json

{
  "refundId": "RF-1001",
  "orderId": "ORD-1001",
  "status": "PENDING_APPROVAL",
  "requestedAmount": 150000,
  "currency": "VND"
}
~~~

Trong thời gian chuyển đổi, adapter tại Payment có thể tiếp tục phục vụ endpoint cũ dựa trên dữ liệu được công bố bởi Refund, miễn là luồng tương thích rõ và tránh vòng gọi. Khi consumer cũ đã chuyển, endpoint adapter được deprecate theo kế hoạch.

Một trường hợp đổi nghĩa **status** từ “đã gửi yêu cầu” sang “đã hoàn tiền thành công” là thay đổi phá vỡ ngữ nghĩa, dù vẫn giữ kiểu string và cùng schema JSON. Việc thiết kế hợp đồng phải kiểm soát **ngữ nghĩa** bên cạnh cấu trúc.

### 9.2. Contract cho event bất đồng bộ

Sự kiện phải là một sự thật đã xảy ra, có cấu trúc và phiên bản phù hợp. Ví dụ:

~~~json
{
  "eventId": "evt-rf-1001-2",
  "eventType": "RefundApproved",
  "schemaVersion": 2,
  "occurredAt": "2026-11-11T08:30:00Z",
  "refundId": "RF-1001",
  "orderId": "ORD-1001",
  "approvedAmount": 150000,
  "currency": "VND"
}
~~~

Lựa chọn event versioning phụ thuộc khả năng tiêu thụ và quy định hợp đồng. Một schema có thể thay đổi tương thích bằng cách thêm trường tùy chọn; việc xóa/đổi nghĩa trường hoặc sửa cấu trúc làm consumer cũ sai thường cần phiên bản mới hoặc thời gian chuyển đổi.

Mỗi consumer cần xác định cách xử lý:

- Message trễ, lặp hoặc đảo thứ tự.
- Event từ phiên bản cũ còn tồn tại trong hàng đợi.
- Event được phát lại để tái tạo projection.
- Schema mới chứa trường chưa biết.
- Business invariant cần kiểm tra khi trạng thái nằm ở nhiều context.

Tránh dùng event như lối truy cập trực tiếp vào schema nội bộ. Event nên công bố sự thật cần thiết cho tương tác giữa context; không tự động chuyển toàn bộ entity hoặc bảng sang mọi consumer.

### 9.3. Consumer-driven contract tests

Khi thay đổi ranh giới có nhiều consumer, dùng contract tests để chứng minh producer mới vẫn đáp ứng các giả định thiết yếu của consumer đã biết. Producer phải công bố hành vi có thể kiểm thử: response/error codes, field semantics, event shape và các điều kiện retry.

Tests không thay thế được việc đối chiếu nghiệp vụ. Ví dụ schema cho phép **status = APPROVED**, nhưng nếu Order hiểu giá trị này là đã chuyển tiền thành công thì contract đúng về kiểu dữ liệu vẫn có thể sai về nghĩa.

## 10. Di chuyển dữ liệu và chuyển nguồn sự thật

Việc di chuyển quyền sở hữu dữ liệu thường khó hơn việc di chuyển code. Cần giải quyết lịch sử, truy vấn đang hoạt động, concurrency, khóa ngoại liên miền, dữ liệu tham chiếu và nguồn sự thật trong lúc chuyển đổi.

### 10.1. Lập bản đồ dữ liệu

| Dữ liệu | Owner trước | Owner sau | Cách chuyển | Bằng chứng |
| --- | --- | --- | --- | --- |
| Refund request | Payment | Refund | Backfill + incremental changes | Đối chiếu số yêu cầu theo trạng thái |
| Refund approval | Payment | Refund | Chuyển rule và lịch sử quyết định | So sánh kết quả policy trên case thực |
| Payment transaction | Payment | Payment | Giữ nguyên | Refund chỉ tham chiếu transactionId |
| Order status | Order | Order | Giữ nguyên | Order nhận kết quả refund qua contract |
| Refund projection cho UI | Order/Payment | Context đọc phù hợp | Subscribe event hoặc gọi API | Thông tin hiển thị theo độ trễ cam kết |

Bảng này làm rõ điều gì **di chuyển**, điều gì **vẫn thuộc context cũ** và điều gì chỉ là **bản sao phục vụ đọc**.

### 10.2. Chọn chiến lược dữ liệu theo tính chất nghiệp vụ

**Snapshot + backfill:** phù hợp khi có thể lấy ảnh dữ liệu tại một thời điểm và sao chép toàn bộ dữ liệu lịch sử; cần cơ chế thu các thay đổi diễn ra trong lúc backfill.

**Snapshot + CDC/event replay:** phù hợp khi dữ liệu tiếp tục được ghi; cần quản lý thứ tự áp dụng thay đổi, khóa định danh, sự kiện lặp và điểm bắt đầu replay.

**Lazy migration:** chỉ chuyển dữ liệu khi được truy cập; giảm chi phí di chuyển ban đầu nhưng làm tăng phức tạp đọc và có thể kéo dài thời gian cần giữ hệ cũ.

**Chuyển nghiệp vụ theo từng nhóm dữ liệu:** ví dụ theo merchant, thị trường hoặc loại refund; phù hợp khi các nhóm có mức độc lập rõ, có thể so sánh kết quả và đảo hướng traffic.

Không có phương án tốt nhất cho mọi trường hợp. Quyết định dựa trên lưu lượng ghi, yêu cầu dừng dịch vụ, tính nhất quán, lịch sử dữ liệu và khả năng khôi phục.

### 10.3. Quản lý ID và liên kết liên miền

Một thay đổi ownership không nên làm mất định danh đã được các context khác tham chiếu. Có thể giữ **stable business ID** và mapping giữa ID cũ/mới nếu cần. Không để consumer phải biết khóa nội bộ của bảng đích hoặc truy cập trực tiếp database đích chỉ để tra cứu.

Ví dụ Refund có **refundId**, tham chiếu **paymentId** và **orderId** bằng ID công bố. Khả năng xác minh nguồn dữ liệu, quyền truy cập và trạng thái giao dịch phải được định nghĩa qua contract.

### 10.4. Đối soát dữ liệu

Một hoạt động migration cần kiểm tra nhiều hơn tổng số dòng:

- Đếm dữ liệu theo loại và trạng thái nghiệp vụ.
- So sánh tổng số tiền và currency theo nhóm, tránh cộng dữ liệu không đồng đơn vị.
- So sánh các khóa định danh thiếu, trùng, không có tham chiếu.
- So sánh tính hợp lệ của chuyển trạng thái.
- Xác minh dữ liệu từ đúng thời điểm cutover và các thay đổi đến trễ.
- Kiểm tra khả năng phục hồi khi backfill/replay chạy lại.

Với dữ liệu tài chính, cần tránh những tiêu chí đối soát quá sơ sài như “số dòng bằng nhau” nếu một record có thể bị thay số tiền hoặc trạng thái. Quy tắc đối soát phải được chuyên gia nghiệp vụ chấp nhận.

## 11. Bảo toàn bất biến và xử lý giao dịch xuyên ranh giới

Ranh giới mới thay đổi nơi có thể dùng giao dịch ACID cục bộ. Một quy tắc vốn được kiểm tra trong cùng transaction có thể thành quy trình qua API hoặc message.

### 11.1. Chỉ rõ bất biến cục bộ và liên miền

Ví dụ:

- **Payment invariant:** không thu cùng payment attempt hai lần vì cùng một request idempotency.
- **Refund invariant:** tổng số tiền hoàn thành công không vượt mức hoàn được phép của các giao dịch đã thu.
- **Order invariant:** trạng thái hủy/đóng đơn phải phản ánh chính sách về giao hàng, hoàn tiền và các quyền hạn tương ứng.

Khi Refund tách khỏi Payment, không đơn giản đưa cả hai cùng tự sửa số tiền đã hoàn. Cần thiết kế rõ **ai giữ hạn mức và ai ra quyết định cuối**, hoặc có một giao thức phối hợp đủ chặt cho invariant. Nếu invariant phải được bảo đảm nguyên tử trong một transaction mà chi phí phối hợp quá lớn, đó là lý do nghiêm túc để cân nhắc giữ chung ranh giới dữ liệu.

### 11.2. Eventual consistency và trạng thái trung gian

Một quy trình Refund có thể đi qua:

~~~text
RefundRequested
      |
      v
PENDING_APPROVAL
      |
      +--> REJECTED
      |
      v
APPROVED
      |
      v
SUBMITTED_TO_PROVIDER
      |
      +--> FAILED / NEEDS_RECONCILIATION
      |
      v
SETTLED
~~~

Trạng thái chỉ là ví dụ minh họa; điều kiện chuyển phải do nghiệp vụ quyết định. Khi Order nhận thông tin trễ, UI có thể hiển thị “đang xử lý hoàn tiền” thay vì công bố đã trả tiền thành công. Sự khác biệt trạng thái trong thời gian ngắn không mặc nhiên là lỗi, nhưng phải có **độ trễ chấp nhận được, thời hạn xử lý và cách phát hiện mắc kẹt**.

### 11.3. Saga và hành động bù

Khi một quy trình đi qua nhiều service mà không có transaction phân tán chung, có thể sử dụng **Saga** với các bước thành công và hành động bù. Hành động bù là nghiệp vụ độc lập: không phải lúc nào cũng có thể hoàn tác nguyên vẹn một hành động đã diễn ra bên ngoài.

Ví dụ khi một giao dịch hoàn tiền đã gửi thành công cho payment provider nhưng Order chưa nhận sự kiện, không “rollback” tiền bằng thao tác xóa record. Cần tiếp tục đồng bộ, đối soát và đưa các context về trạng thái thống nhất có chứng cứ.

### 11.4. Chống xử lý lặp

Các message, HTTP retry và job hồi phục có thể chạy nhiều lần. Dùng idempotency key, version và trạng thái chuyển hợp lệ để ngăn thực thi nghiệp vụ trùng. Chỉ dựa vào câu “broker giao đúng một lần” là không đủ để bảo vệ logic nghiệp vụ khi có retry hoặc lỗi giữa các bước.

## 12. Ví dụ chi tiết: tiến hóa Payment và Refund

### 12.1. Hiện trạng và tín hiệu

Một nền tảng thương mại điện tử có Payment Service xử lý cả thu tiền và hoàn tiền. Order Service đọc trạng thái hoàn tiền thông qua API cũ của Payment.

Ban đầu, hoàn tiền là một thao tác đơn giản. Sau khi mở rộng kinh doanh, Refund có thêm:

- Hoàn tiền một phần theo từng sản phẩm trong đơn.
- Quy định phê duyệt tùy số tiền và nguyên nhân.
- Hoàn tiền nhiều lần với hạn mức tổng.
- Phân biệt yêu cầu được chấp nhận và tiền đã thực sự chuyển.
- Đối soát với nhiều nhà cung cấp thanh toán.
- Các job nhắc và xử lý giao dịch cần kiểm tra thủ công.

Hai nhóm phát triển thường xuyên phối hợp sửa cùng một bộ quy tắc; Service Payment có cả trạng thái thanh toán và workflow phê duyệt hoàn tiền khiến ownership mơ hồ. Đây là lý do **đánh giá ứng viên Refund Context**, chưa phải bằng chứng bắt buộc tách deployable.

### 12.2. Ranh giới trước và sau được đề xuất

**Trước:**

~~~text
Order Context
    |
    | refund status, payment status
    v
Payment Context
    | charge, refund request, refund approval
    | payment DB + refund tables
    v
Payment Provider
~~~

**Mục tiêu:**

~~~text
Order Context -----> Refund Context
      |               | refund request, approval,
      |               | refund lifecycle / audit
      |               |
      v               v
Payment Context <-----+
      | charge/payment records
      v
Payment Provider
~~~

Mũi tên thể hiện hợp đồng giữa context, không nhất thiết là các cuộc gọi HTTP đồng bộ. Quy trình cần xác định ai điều phối, ai nhận kết quả cuối cùng và ai xử lý ngoại lệ.

**Payment Context** giữ quyền sở hữu giao dịch thu tiền và bằng chứng từ payment provider. **Refund Context** sở hữu yêu cầu hoàn, phê duyệt, quy tắc eligibility và vòng đời hoàn tiền. Order sở hữu trạng thái đơn của nó và có thể giữ projection khi cần. Trách nhiệm thực hiện việc trả tiền cụ thể phải được hai đội chốt trong hợp đồng; có thể để Payment thực thi lệnh từ Refund nếu nó là nơi quản lý giao dịch provider.

### 12.3. ADR minh họa

~~~markdown
# ADR-027: Tao Refund Context rieng

Status: Accepted

Context:
- Refund co workflow phu duyet va doi soat rieng
- Cac thay doi refund thuong cham vao Payment va Order
- Chua co owner duy nhat cho refund eligibility

Decision:
- Refund Context so huu refund request, approval va lifecycle
- Payment Context so huu payment transaction va provider integration
- Refund yeu cau thuc thi qua published contract cua Payment
- Order nhan trang thai hoan tien qua event/API duoc cong bo
- Trong giai doan dau, Refund co the la module rieng trong
  cung deployable; tach deploy sau khi contract/on-call on dinh

Consequences:
- Giam thay doi rule refund trong Payment
- Tang nhu cau contract, consistency va reconciliation
- Can migration du lieu refund cu va consumer cu

Review triggers:
- Muc do phoi hop release giua Payment va Refund
- Loi do workflow phan tan va thoi gian doi soat
- Nhu cau scale va van hanh Refund doc lap
~~~

Tên và nội dung chỉ nhằm minh họa phương pháp ghi quyết định. Không dùng ADR như bản thay thế cho làm rõ invariant hoặc nguồn dữ liệu.

### 12.4. Kế hoạch chuyển đổi theo giai đoạn

**Đợt A — Làm rõ miền.** Nhóm Payment, Order, Refund và người phụ trách nghiệp vụ thống nhất các khái niệm: Request, Approval, Submission, Settlement, Failed, Cancelled. Họ xác định hạn mức hoàn, quy tắc trùng và nguồn bằng chứng cuối.

**Đợt B — Tạo module/contract Refund.** Tách các rule xét duyệt khỏi phần tích hợp nhà cung cấp. Công bố interface quản lý refund và contract tests; đường cũ vẫn hoạt động.

**Đợt C — Xây kho dữ liệu và chuyển lịch sử.** Tạo dữ liệu Refund có ID ổn định, backfill lịch sử, thu thay đổi diễn ra trong lúc chuyển và đối soát theo transaction/paymentId.

**Đợt D — Chuyển consumer đọc.** Order và công cụ hỗ trợ khách hàng chuyển dần qua contract mới. Đo chênh lệch trạng thái với hệ thống cũ, giữ luồng cũ như adapter tạm nếu cần.

**Đợt E — Chuyển quyền ghi.** Refund trở thành nơi duy nhất quyết định và ghi trạng thái yêu cầu/phê duyệt hoàn. Payment nhận lệnh thực thi hoàn theo contract và ghi bằng chứng giao dịch. Quy định rõ trách nhiệm xử lý webhook/retry.

**Đợt F — Cắt chuyển và quan sát.** Thực hiện với lưu lượng giới hạn, đo tỉ lệ hoàn hợp lệ, trùng, giao dịch cần đối soát và thời gian end-to-end. Mở rộng khi kết quả đạt ngưỡng đã định.

**Đợt G — Thu dọn.** Ngừng endpoint và quyền ghi cũ sau khi không còn consumer phụ thuộc; cập nhật tài liệu và ownership.

### 12.5. Tiêu chí xác nhận quá trình tiến hóa

- **Nghiệp vụ:** các chính sách Refund được điều chỉnh trong Refund Context; hạn mức và trạng thái có nguồn sự thật rõ.
- **Kỹ thuật:** các contract mới có test, consumer cũ được bảo vệ trong giai đoạn chuyển; không có ghi chéo DB.
- **Dữ liệu:** số tiền và trạng thái đối soát nhất quán theo quy định nghiệp vụ; các sai lệch được xử lý hoặc ghi nhận có chủ sở hữu.
- **Vận hành:** dashboard, alert và người trực của Refund rõ ràng; có khả năng xác định lỗi tại từng bước.
- **Tổ chức:** đội Refund có thể thay đổi rule riêng mà không cần cập nhật triển khai bắt buộc của Order/Payment cho những thay đổi tương thích.

Nếu mục tiêu triển khai độc lập chưa đạt mà hệ thống tăng đáng kể độ phức tạp, cần quay lại phương án module trong cùng deployable hoặc đổi cách tích hợp. Quyết định ranh giới cần được kiểm chứng bằng kết quả thật.

## 13. Rollback, roll-forward và điểm không thể đảo đơn giản

Khi đổi ranh giới, “rollback bản code” không có nghĩa dữ liệu và kết quả nghiệp vụ tự trở lại trạng thái trước đó.

### 13.1. Phân biệt các dạng quay lại

- **Rollback routing:** đưa một nhóm request quay lại adapter/endpoint cũ; thường khả thi khi chưa chuyển quyền ghi hoặc còn hợp đồng tương thích.
- **Rollback code:** triển khai lại bản phần mềm cũ; chỉ an toàn nếu schema và dữ liệu vẫn tương thích.
- **Data recovery:** khôi phục hoặc tái đồng bộ dữ liệu theo nguồn sự thật; đòi hỏi kiểm soát thay đổi đã phát sinh.
- **Business compensation:** thực hiện hành động nghiệp vụ bù khi kết quả ngoài hệ thống đã xảy ra, chẳng hạn xử lý một giao dịch thu/hoàn tiền đã thực hiện.

Không mặc định có thể restore snapshot DB để xóa một chuỗi sự kiện tài chính sau khi đã giao dịch với bên ngoài.

### 13.2. Định nghĩa cutover checkpoint

Trước mỗi bước, ghi rõ:

1. **Điểm bắt đầu:** trạng thái hợp đồng, schema, owner và traffic lúc bắt đầu.
2. **Điều kiện phát hành:** contract tests, dữ liệu đã backfill, khả năng đọc tương thích, giám sát sẵn sàng.
3. **Điều kiện dừng:** tỉ lệ lỗi, sai lệch dữ liệu, backlog, độ trễ hoặc ảnh hưởng khách hàng vượt ngưỡng chấp nhận.
4. **Cách quay lại:** thao tác nào có thể an toàn đảo ngược, phần nào buộc roll-forward hoặc đối soát.
5. **Người quyết định:** owner nghiệp vụ, owner kỹ thuật và đầu mối phản ứng sự cố.
6. **Bằng chứng hoàn thành:** lưu biên bản cutover, thời điểm, kiểm thử và chỉ số thực tế.

Một **point of no simple rollback** có thể xuất hiện sau khi context mới là nơi duy nhất ghi dữ liệu và đã tạo giao dịch mà hệ cũ không hiểu. Sau điểm này, phương án chính thường là sửa và tiến tới an toàn; kế hoạch phải ghi rõ từ trước.

## 14. Đo mức phù hợp của ranh giới sau thay đổi

Sự tiến hóa thành công phải giải quyết vấn đề ban đầu mà không tạo chi phí quá lớn. Theo dõi theo cả góc độ nghiệp vụ, thay đổi phần mềm và vận hành.

### 14.1. Các nhóm chỉ số

| Nhóm | Ví dụ phép đo | Ý nghĩa cần diễn giải |
| --- | --- | --- |
| Tốc độ thay đổi | Lead time, số bước phối hợp, thời gian chờ review | Ranh giới có làm chậm một thay đổi nghiệp vụ không? |
| Triển khai | Deployment frequency, số release phải đồng bộ | Có thể phát hành một năng lực theo nhịp riêng không? |
| Chất lượng | Change failure rate, lỗi hợp đồng, lỗi migration | Việc tách có làm tăng rủi ro phát hành không? |
| Sẵn sàng | SLO, thời gian khôi phục, failure propagation | Một lỗi lan qua ranh giới như thế nào? |
| Dữ liệu | Sai lệch projection, backlog replay, độ trễ đối soát | Dữ liệu sở hữu và bản sao có vận hành đúng không? |
| Phụ thuộc | Số direct DB access, chuỗi call, shared domain packages | Có giảm ghép chặt hay chỉ chuyển hình thức phụ thuộc? |
| Tổ chức | Owner không rõ, số lần chuyển nhóm, số bước phê duyệt | Trách nhiệm có xác định và thực thi được không? |
| Giá trị nghiệp vụ | Tỉ lệ hoàn tiền xử lý đúng, thời gian xử lý yêu cầu | Thay đổi có giúp đạt business outcome không? |

Các metric như lead time và deployment frequency cần xem **xu hướng và bối cảnh**, không dùng để xếp hạng đội nhóm hay tự chứng minh microservices tốt hơn modular monolith.

### 14.2. Quyết định giữ hay chỉnh tiếp

Đánh giá theo **thời điểm trước và sau thay đổi**, trong khoảng đủ quan sát các chu kỳ phát hành và sự cố thực. Nếu một ranh giới mới tạo nhiều message, nhiều đường retry, khó trace hơn nhưng không giúp đội ngũ thay đổi độc lập, cần xem lại phạm vi, hợp đồng hoặc lựa chọn triển khai.

Một số dấu hiệu cải thiện:

- Tính năng thuộc Refund được thay đổi trong một context rõ.
- Consumer dùng published contracts, không cần biết schema nội bộ.
- Những thay đổi API tương thích được phát hành theo nhịp riêng.
- Lỗi của một bước có người chịu trách nhiệm và cách khôi phục xác định.
- Người mới đọc context map, ADR và glossary có thể hiểu vì sao ranh giới hiện tại tồn tại.

## 15. Quản trị quyền sở hữu khi chuyển ranh giới

Ranh giới dịch vụ gắn với con người. Việc tạo repo hoặc đổi route mà không chuyển ownership có thể làm hệ thống xuất hiện “dịch vụ không ai chăm sóc”.

### 15.1. Handover trách nhiệm

Một đợt thay đổi cần xác nhận:

- **Business owner:** ai có thẩm quyền chốt quy tắc, ngoại lệ và kết quả nghiệp vụ.
- **Engineering owner:** ai chịu trách nhiệm thiết kế, kiểm thử, bảo mật và thay đổi code.
- **Data owner:** ai quản lý schema, migration, retention và quyền truy cập.
- **Contract owner:** ai công bố version, deprecation, compatibility và thông báo consumer.
- **Operational owner:** ai nhận alert, có quyền truy cập dashboard và giải quyết incident.
- **Cutover coordinator:** ai quyết định tiến/dừng, ghi biên bản và điều phối thời điểm chuyển.

Các vai trò có thể cùng một đội, nhưng phải được xác nhận bằng người/nhóm có trách nhiệm thực tế.

### 15.2. Tránh governance thành nút nghẽn

Một ADR không có nghĩa mọi endpoint đều phải qua một hội đồng kiến trúc lớn. Có thể thống nhất nguyên tắc chung và để các đội tự quyết trong phạm vi sở hữu, chỉ đưa vấn đề lên cấp phối hợp khi thay đổi hợp đồng hoặc dữ liệu của bên khác.

Tổ chức có thể đặt một **boundary review** nhẹ trước các thay đổi lớn: hai bên producer/consumer, domain expert, platform/security khi liên quan. Kết quả là quyết định rõ, lịch chuyển đổi và người theo dõi. Không biến lịch review thành một barrier trì hoãn các thay đổi nhỏ.

### 15.3. Tài liệu nào cần cập nhật sau mỗi thay đổi?

| Tài liệu/hiện vật | Điều cần cập nhật |
| --- | --- |
| Boundary register | Phạm vi, owner, trạng thái và dữ liệu sở hữu mới |
| Context map | Quan hệ giữa context và hợp đồng thực tế |
| ADR | Quyết định mới, liên kết superseded và kết quả |
| API/event docs | Schema, ví dụ, lỗi, phiên bản và thời hạn hỗ trợ |
| Data catalog | Source of truth, projection và luồng đồng bộ |
| Ownership/on-call | Đầu mối phát hành, sự cố và runbook |
| Architecture diagram | Current, target và transition tại đúng thời điểm |
| Migration log | Cutover, trạng thái backfill, data reconciliation và đường cũ cần xóa |

Tài liệu nên được cập nhật **cùng thời điểm thay đổi có hiệu lực**, tránh tình trạng bản đồ “mục tiêu” bị hiểu nhầm là hiện trạng.

## 16. Các lỗi phổ biến khi tiến hóa ranh giới

### 16.1. Tách một service chỉ vì số lượng class lớn

Một dịch vụ lớn có thể chứa nhiều rule liên quan chặt chẽ và cần một transaction nhất quán. Tách thuần theo kích thước có thể biến lời gọi nội bộ thành chuỗi mạng khó kiểm soát.

**Hướng xử lý:** cải thiện module và dependency trong cùng deployable trước; chỉ tách boundary khi có bằng chứng về domain, ownership hoặc nhu cầu triển khai riêng.

### 16.2. Đổi sơ đồ mà không đổi quyền sở hữu dữ liệu

Nếu Refund Service mới tồn tại nhưng Payment và Order vẫn cùng ghi bảng refund, tình trạng bất nhất còn nguyên hoặc tệ hơn.

**Hướng xử lý:** đánh dấu single writer, nguồn sự thật, quyền truy cập và điều kiện chuyển authority; loại bỏ direct DB access xuyên context theo kế hoạch.

### 16.3. “Big bang” migration

Đổi schema, event, API và triển khai mọi consumer cùng lúc làm tăng phạm vi sự cố. Một consumer không thể nâng phiên bản kịp sẽ khiến toàn hệ thống bị chặn.

**Hướng xử lý:** dùng expand–migrate–contract, adapter tương thích, thời gian deprecation và các checkpoint có thể quan sát.

### 16.4. Hai nguồn sự thật trong thời gian dài

Khi mỗi context nghĩ rằng mình có quyền ghi dữ liệu, sự khác nhau giữa bản ghi có thể bị che khuất đến khi sự cố xảy ra.

**Hướng xử lý:** thống nhất authority, giới hạn giai đoạn chuyển đổi, có quy trình reconcile và xóa các lối ghi tạm ngay sau cutover.

### 16.5. Coi đổi tên là giải quyết domain

Đổi Payment thành Billing hay đổi package không giải quyết việc một quy tắc thuộc sai context. Ngôn ngữ, policy, dữ liệu, hợp đồng và ownership cần di chuyển đúng nghĩa.

### 16.6. Không theo dõi consumer cũ

Một service có thể tuyên bố migration đã hoàn tất trong khi batch report cuối tháng hoặc một đối tác vẫn sử dụng hợp đồng trước đó.

**Hướng xử lý:** có inventory consumer, usage metrics, thông báo deprecation, contract tests và điều kiện loại bỏ hợp đồng cũ.

### 16.7. Chỉ nhìn dữ liệu thành công

Kết quả bình thường có thể trùng nhau trong khi các case timeout, callback lặp, hủy, hoàn tiền một phần hoặc retry gây sai khác nghiêm trọng.

**Hướng xử lý:** kiểm thử theo business invariant và nhánh lỗi; theo dõi dữ liệu cần đối soát trong quá trình chuyển.

### 16.8. Xóa bỏ quyết định cũ

Không giữ ADR và bối cảnh khiến người đến sau dễ lặp lại quyết định từng gây lỗi.

**Hướng xử lý:** ghi trạng thái Superseded/Retired và liên kết quyết định kế tiếp; không làm mất lịch sử.

### 16.9. Biến tiến hóa ranh giới thành dự án không bao giờ kết thúc

Nếu mọi thay đổi đều bổ sung adapter/bridge mà không có hạn gỡ bỏ, chi phí vận hành và độ khó hiểu tăng dần.

**Hướng xử lý:** mỗi lớp chuyển tiếp cần có chủ sở hữu, tiêu chí kết thúc, dấu hiệu không còn consumer và việc dọn dẹp đã được lên kế hoạch.

## 17. Checklist thực hành cho một thay đổi ranh giới

Trước khi quyết định:

- Đã mô tả được **vấn đề nghiệp vụ** và chứng cứ từ các thay đổi/sự cố thực?
- Đã phân biệt lỗi ranh giới miền với lỗi hợp đồng, code hoặc vận hành?
- Đã nêu được các lựa chọn giữ nguyên, tách, gộp hoặc chuyển trách nhiệm?
- Đã xác định bounded context, ngôn ngữ, invariant và owner trước/sau?
- Đã xác định dữ liệu nguồn sự thật, các đường đọc/ghi và consumer?
- Đã ghi ADR, bối cảnh, trade-off và trigger xem lại?

Trong khi chuyển đổi:

- Có thiết kế contract tương thích và kiểm thử producer/consumer?
- Có chiến lược dữ liệu, idempotency, backfill, CDC/replay và reconciliation phù hợp?
- Có người quyết định cutover, tiêu chí dừng và chiến lược quay lại/tiến tới an toàn?
- Đã tính tới các nhánh lỗi, công việc batch, event đến trễ và quyền truy cập?
- Đã chuẩn bị dashboard, tracing, cảnh báo và runbook?
- Có giới hạn thời gian cho adapter và đường ghi cũ?

Sau khi hoàn tất:

- Đã xác minh quyền ghi thực tế thuộc owner đích?
- Đã gỡ các phụ thuộc bắt buộc và quyền truy cập trực tiếp không còn cần?
- Đã xác nhận không còn consumer dùng contract bị loại bỏ?
- Đã đối soát dữ liệu và xử lý các sai lệch còn tồn?
- Đã cập nhật context map, ADR, boundary register, owner và tài liệu vận hành?
- Đã đánh giá kết quả so với vấn đề và metric ban đầu?

Checklist là một công cụ ghi nhớ và phối hợp; mức độ chi tiết của bằng chứng tùy tính rủi ro và ảnh hưởng của thay đổi.

## 18. Bài thực hành: tiến hóa ranh giới giỏ hàng và khuyến mãi

Một công ty thương mại điện tử đang có hai service:

- **Cart Service:** quản lý giỏ hàng, tính tổng tiền và lưu coupon code.
- **Promotion Service:** lưu danh sách chương trình, điều kiện áp dụng và giá trị giảm giá.

Mỗi chiến dịch khuyến mãi mới thường làm hai đội phải thay đổi code, do Cart chứa logic tính ưu đãi đặc biệt. Cùng từ “giá sau giảm” nhưng Cart và Promotion tính khác nhau trong trường hợp áp dụng đồng thời coupon và voucher. Đội vận hành gặp lỗi chênh lệch tổng tiền và khó xác định owner.

### Yêu cầu A — Lập hiện trạng

Vẽ context map, liệt kê source of truth và các API/event giữa hai service. Phân biệt loại thông tin giỏ hàng thực sự sở hữu với quy tắc giảm giá mà Promotion có thể sở hữu.

### Yêu cầu B — Thu thập tín hiệu

Chọn tối thiểu ba bằng chứng: lịch sử thay đổi cùng lúc, sai lệch số tiền, phụ thuộc shared library, hoặc lần phát hành bị buộc đồng bộ. Nêu rõ tại sao từng bằng chứng có thể hoặc chưa thể kết luận ranh giới sai.

### Yêu cầu C — So sánh lựa chọn

So sánh:

1. Giữ hai service nhưng chuyển toàn bộ thuật toán ưu đãi sang Promotion, còn Cart chỉ tiêu thụ kết quả.
2. Hợp nhất logic tính giá và khuyến mãi thành một bounded context hoặc deployable phù hợp.
3. Tách tính giá thành Pricing Context và giữ Promotion quản lý chương trình, đồng thời định nghĩa contract rõ.

Đánh giá theo bất biến tính tiền, dependency, dữ liệu, nhịp phát hành và tác động vận hành. Không kết luận chỉ từ số endpoint.

### Yêu cầu D — Viết ADR và kế hoạch chuyển đổi

Viết một ADR với bối cảnh, lựa chọn, quyết định, trách nhiệm và điều kiện xem lại. Phác thảo cách chuyển contract theo hướng tương thích; mô tả một luồng so sánh kết quả tính tiền trong giai đoạn shadow, tránh tạo đơn hàng thật hai lần.

### Yêu cầu E — Định nghĩa bằng chứng hoàn thành

Nêu chỉ số theo dõi sai lệch tổng tiền, tần suất phối hợp release, lỗi hợp đồng, thời gian xử lý một thay đổi chính sách và sự rõ ràng của ownership. Chỉ rõ điều kiện ngừng đường tính toán cũ.

Bài thực hành hoàn thành khi người đọc có thể truy nguyên **tại sao cần đổi, ranh giới mục tiêu là gì, thay đổi được chuyển an toàn ra sao và bằng chứng nào cho biết nó hiệu quả**.

## 19. Tóm lược kiến thức

Ranh giới Microservices là một **giả thuyết kiến trúc dựa trên hiểu biết nghiệp vụ ở một thời điểm**. Khi domain, tổ chức hoặc yêu cầu vận hành thay đổi, ranh giới có thể cần chỉnh lại. Việc tiến hóa có trách nhiệm đòi hỏi giữ được **lịch sử quyết định, nguồn sự thật của dữ liệu, hợp đồng tương thích, người sở hữu và khả năng xác minh kết quả**.

Một vòng tiến hóa điển hình là:

~~~text
Phat hien tin hieu
       |
       v
Thu thap bang chung + xac minh domain
       |
       v
So sanh cac phuong an giu / tach / gop / chuyen
       |
       v
Ghi ADR + context map muc tieu + ownership
       |
       v
Expand contract/schema -> migrate -> cutover
       |
       v
Doi soat, quan sat, don duong cu
       |
       v
Cap nhat boundary register va danh gia lai
~~~

Ba nguyên tắc cần nhớ:

1. **Ranh giới thay đổi vì tri thức và nhu cầu nghiệp vụ đổi.** Số lượng service không phải thước đo thành công.
2. **Chuyển ranh giới là chuyển trách nhiệm và nguồn sự thật.** Code, database, API, event, quyền hạn và vận hành phải được giải quyết đồng bộ về nghĩa, dù các bản phát hành có thể diễn ra theo từng giai đoạn.
3. **Một quyết định tốt phải có lịch sử và điều kiện xem lại.** ADR, context map, evidence và metric giúp các thế hệ đội ngũ hiểu vì sao ranh giới tồn tại và khi nào cần tiếp tục tiến hóa.
