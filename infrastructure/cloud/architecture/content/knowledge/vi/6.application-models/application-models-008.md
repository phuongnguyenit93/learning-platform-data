# Nhận diện nguyên khối phân tán và tách dịch vụ quá sớm

## 1. Vấn đề kiến trúc: nhiều dịch vụ nhưng vẫn phải thay đổi cùng nhau

Trong thiết kế ứng dụng đám mây, đội ngũ thường cân nhắc chuyển từ một ứng dụng nguyên khối (monolith) sang microservices để triển khai độc lập, mở rộng linh hoạt hoặc giới hạn ảnh hưởng của sự cố. Tuy nhiên, **số lượng dịch vụ triển khai không chứng minh được mức độ độc lập của kiến trúc**. Một hệ thống gồm mười container, nhiều repository, API gateway và message broker vẫn có thể buộc tất cả thành phần phải thay đổi, phát hành và phục hồi cùng nhau.

Tình trạng này thường được gọi là **distributed monolith (nguyên khối phân tán)**: ứng dụng được chia thành nhiều tiến trình hoặc đơn vị triển khai, nhưng các phần vẫn **phụ thuộc chặt về nghiệp vụ, dữ liệu, thời điểm hoặc chu kỳ phát hành**. Hệ thống phải chịu thêm độ trễ mạng, lỗi từng phần và chi phí vận hành phân tán trong khi khó tận dụng tính tự chủ vốn được kỳ vọng ở các dịch vụ.

Một nguyên nhân phổ biến là **premature service decomposition (tách dịch vụ quá sớm)**: chia ứng dụng thành dịch vụ trước khi hiểu ổn định về ranh giới nghiệp vụ, dữ liệu sở hữu, mô hình thay đổi, quy mô tải và năng lực vận hành. Tách sớm không phải lúc nào cũng sai, nhưng sẽ rủi ro nếu quyết định chủ yếu dựa trên mong muốn dùng công nghệ mới, số lượng bảng dữ liệu hoặc sơ đồ tổ chức hiện tại.

Ví dụ, nền tảng đặt phòng tách Booking, Room, Price, Coupon, Payment và Notification thành sáu dịch vụ. Mỗi lần xác nhận đặt phòng, Booking phải chờ lần lượt năm dịch vụ; tất cả cùng đọc và ghi một cơ sở dữ liệu; đổi cột trong bảng booking phải phát hành lại cả sáu. Mặc dù trông giống microservices trên sơ đồ, **mức độ độc lập thực tế rất thấp**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt nguyên khối truyền thống, nguyên khối có module rõ ràng, microservices và nguyên khối phân tán.
2. Nhận ra các dấu hiệu phụ thuộc chặt ở mã nguồn, dữ liệu, luồng chạy, triển khai và vận hành.
3. Giải thích tác động của việc tách dịch vụ quá sớm lên độ tin cậy, bảo mật, hiệu năng, chi phí và đội ngũ.
4. Quyết định khi nào nên giữ modular monolith, khi nào nên tách một capability thành dịch vụ riêng.
5. Đề xuất lộ trình giảm phụ thuộc và tách dần, có phép đo và phương án phục hồi.

## 2. Bốn khái niệm dễ bị nhầm lẫn

| Mô hình | Cấu trúc và triển khai | Đặc điểm đáng chú ý |
|---|---|---|
| **Monolith không có module rõ** | Nhiều chức năng nằm chung một khối mã, thường triển khai cùng nhau | Thay đổi và kiểm thử dễ lan rộng; vận hành ban đầu tương đối đơn giản |
| **Modular monolith** | Một đơn vị triển khai, bên trong có các module nghiệp vụ với API và quyền sở hữu rõ | Dễ bảo vệ giao dịch trong tiến trình/DB chung; có thể giữ coupling thấp ở mức mã nguồn |
| **Microservices có ranh giới tốt** | Nhiều dịch vụ, mỗi dịch vụ sở hữu năng lực và hợp đồng, có khả năng tiến hóa tương đối độc lập | Cần xử lý mạng, giao dịch phân tán, bảo mật và vận hành; mức độc lập phụ thuộc cách thiết kế thực tế |
| **Distributed monolith** | Nhiều dịch vụ/tiến trình nhưng phụ thuộc chặt ở nhiều chiều | Gánh chi phí phân tán và vẫn khó phát hành, mở rộng hoặc phục hồi độc lập |

**Monolith không mặc định là thiết kế tồi.** Với đội nhỏ, domain còn thay đổi hoặc nghiệp vụ cần giao dịch mạnh, một modular monolith được thiết kế tốt có thể là lựa chọn đáng tin cậy và tiết kiệm hơn.

**Microservices không mặc định là phân tán nguyên khối.** Những phụ thuộc đồng bộ thật sự cần thiết vẫn có thể tồn tại; điểm quyết định là **hợp đồng, tính tự chủ và khả năng chịu lỗi của hệ thống khi phụ thuộc không sẵn sàng**.

### Nhìn qua hai sơ đồ

~~~mermaid
flowchart TD
    Client["Người dùng"] --> Gateway["API Gateway"]
    Gateway --> Booking["Booking service"]
    Booking --> Room["Room service"]
    Room --> Pricing["Pricing service"]
    Pricing --> Coupon["Coupon service"]
    Booking --> Payment["Payment service"]
    Payment --> Notify["Notification service"]
    Booking --> SharedDB[("Shared DB")]
    Room --> SharedDB
    Pricing --> SharedDB
    Coupon --> SharedDB
    Payment --> SharedDB
    Notify --> SharedDB
~~~

*Ví dụ có nguy cơ là distributed monolith: chuỗi gọi dài, nhiều bên sửa dữ liệu chung, khó tách lỗi và phải phối hợp phát hành. Sơ đồ chỉ minh họa một phản mẫu; cần kiểm chứng bằng thực tế mã nguồn và vận hành.*

~~~mermaid
flowchart TD
    Client["Người dùng"] --> API
    subgraph AppBoundary["Modular Monolith - một đơn vị triển khai"]
        API["API / Application layer"]
        BookingM["Booking module"]
        PricingM["Pricing module"]
        NotificationM["Notification module"]
        API --> BookingM
        BookingM --> PricingM
        BookingM -. "Sự kiện nội bộ" .-> NotificationM
    end
    BookingM --> DB[("Database có phân quyền sở hữu logic")]
    PricingM --> DB
    NotificationM --> DB
~~~

*Minh họa modular monolith: các module vẫn có thể dùng một cơ sở dữ liệu vật lý nhưng phải tuân thủ ranh giới logic. Một ứng dụng triển khai chung không cấm module có chủ sở hữu, hợp đồng hoặc kiểm thử riêng.*

## 3. Dấu hiệu nhận diện nguyên khối phân tán

Không nên chẩn đoán từ sơ đồ topology một mình. Hãy hỏi đội phát triển và vận hành **một thay đổi nhỏ hoặc một lỗi đơn lẻ lan đi xa đến đâu**.

| Dấu hiệu | Cách kiểm chứng | Vì sao đáng lo |
|---|---|---|
| **Phải phát hành đồng thời** | Một field mới buộc nhiều repository/đội release cùng lúc | Hợp đồng không tương thích hoặc quyền sở hữu ranh giới chưa rõ |
| **Nhiều dịch vụ cùng sửa bảng** | Truy vết quyền truy cập DB, migration và truy vấn SQL | Không có nguồn sự thật và đường ghi thống nhất; lỗi dữ liệu lan rộng |
| **Chuỗi gọi đồng bộ dài** | Dùng distributed tracing, đo fan-out và độ sâu chuỗi | Độ trễ, timeout và lỗi phụ thuộc cộng dồn trên đường người dùng |
| **Dịch vụ gọi nhau quá chi tiết** | Một thao tác nghiệp vụ cần hàng chục RPC nhỏ | Ranh giới chia theo hàm/bảng thay vì năng lực |
| **Một dịch vụ lỗi khiến toàn bộ giao dịch lỗi** | Thử tắt thành phần phụ, quan sát hành vi | Chưa cô lập phần có thể suy giảm hoặc xử lý sau |
| **Mọi dịch vụ dùng thư viện domain dùng chung** | Xem import và tần suất nâng phiên bản bắt buộc | Quy tắc nghiệp vụ và schema lan sang nhiều nơi |
| **Giao dịch phân tán không có mô hình trạng thái** | Tìm các chuỗi ghi nhiều DB và logic hoàn tác | Có thể sinh trạng thái dở dang, gửi lặp hoặc sai bất biến |
| **Triển khai độc lập trên giấy** | So sánh release history và việc rollback cùng nhau | Đơn vị deploy riêng nhưng vẫn phụ thuộc vận hành |
| **Scale một dịch vụ kéo theo nghẽn toàn hệ thống** | Load test theo workload, đo pool, quota, lock và hàng đợi | Tài nguyên chung chưa được cô lập hợp lý |
| **Không rõ ai sở hữu sự cố/dữ liệu** | Diễn tập incident, hỏi owner của một trạng thái lỗi | Ranh giới dịch vụ không khớp trách nhiệm |

Một dấu hiệu riêng lẻ **chưa đủ kết luận**. Ví dụ, một công việc có thể cần ba lời gọi đồng bộ để bảo toàn hành vi nghiệp vụ; một thay đổi quy định pháp lý lớn cũng có thể buộc nhiều dịch vụ đổi cùng lúc. Cần xem **mẫu lặp lại qua nhiều thay đổi, sự cố và hành trình**.

### Ba phép thử thực tế

**Phép thử thay đổi:** “Ngày mai đổi công thức phí hủy, thành phần nào phải sửa mã và deploy?” Nếu Booking, Payment, Email, Search và Report đều phải phát hành cùng phiên bản, cần rà lại ranh giới quy tắc.

**Phép thử lỗi:** “Nếu Notification ngừng hoạt động 30 phút, người dùng có tiếp tục đặt phòng hợp lệ không?” Nếu gửi email chỉ là bước phụ sau xác nhận, việc bắt Booking chờ Notification là phụ thuộc thời điểm không cần thiết.

**Phép thử mở rộng:** “Khi Search tăng tải 10 lần, có thể tăng compute Search mà không làm nghẽn DB transaction của Booking không?” Nếu các dịch vụ dùng chung tài nguyên nút thắt, tính độc lập khi scale mới ở mức deployment.

## 4. Các chiều coupling cần đo, không chỉ số lượng repository

### 4.1. Coupling ở mã nguồn và hợp đồng

Một API có hợp đồng ổn định giúp che giấu chi tiết hiện thực. Ngược lại, nếu consumer phụ thuộc chính xác vào cấu trúc entity nội bộ, giá trị enum chưa được version hoặc thứ tự các bước không được tài liệu hóa, đổi logic bên trong có thể phá consumer.

Ví dụ xấu: dịch vụ Report import class **BookingEntity** từ thư viện riêng của Booking, sau đó truy cập các field phù hợp với schema DB. Khi Booking đổi sang nhiều bảng, Report vừa phải nâng thư viện vừa phải đổi query.

Hướng cải thiện: Report dùng **read model** hoặc hợp đồng dữ liệu/sự kiện chuyên dụng, có định nghĩa ý nghĩa nghiệp vụ, phiên bản và chính sách tương thích. Không nên trích xuất một thư viện domain chung chỉ để né việc thiết kế hợp đồng.

### 4.2. Coupling dữ liệu

**Shared database** có thể rất hợp lý trong modular monolith; rủi ro xuất hiện khi các **dịch vụ triển khai độc lập** tự ghi vào cùng một schema nội bộ mà không có quyền sở hữu và kiểm soát migration.

Những câu hỏi cần trả lời:

- Ai là nguồn sự thật của trạng thái đặt phòng và thông tin giá đã chốt?
- Ai có quyền ghi và kiểm soát transaction ảnh hưởng bất biến “không đặt trùng”?
- Consumer nhận dữ liệu qua API, event, view/read model hay truy vấn thẳng bảng?
- Khi sửa schema, có thể hỗ trợ cả producer cũ và mới trong một khoảng chuyển tiếp không?

Nguyên tắc thường dùng là **dịch vụ sở hữu dữ liệu và đường ghi của nó**. Điều đó không nhất thiết đòi hỏi một máy chủ DB vật lý riêng cho mỗi dịch vụ; cách tách schema, quyền và tài nguyên phải dựa trên rủi ro, độ độc lập và chi phí.

### 4.3. Coupling thời điểm (temporal coupling)

Một thao tác đồng bộ cần cả caller và dependency khả dụng đúng thời điểm. Với chuỗi gồm nhiều lời gọi bắt buộc, một khâu chậm có thể làm toàn hành trình chậm. Nếu có retry thiếu giới hạn, áp lực còn có thể tăng đúng lúc dependency đang quá tải.

Ví dụ: Booking chờ Pricing, Inventory, Payment, Notification và Loyalty mới trả kết quả. Cần phân biệt:

- Kiểm tra **quyền đặt chỗ**, **giá áp dụng** hoặc **kết quả thanh toán** có thể là điều kiện cần trước khi xác nhận.
- Gửi **email**, cộng **điểm thưởng** hoặc cập nhật **analytics** thường có thể xử lý sau nếu nghiệp vụ chấp nhận độ trễ.

Không nên đưa tất cả sang hàng đợi nếu quy trình vẫn đòi hỏi kết quả ngay. **Tính nhất quán, độ trễ và trải nghiệm người dùng** phải được quyết định cùng chủ sở hữu nghiệp vụ.

### 4.4. Coupling triển khai và vận hành

Hai dịch vụ có thể dùng DB riêng nhưng vẫn bị gắn chặt nếu phải đồng thời triển khai do breaking API, dùng một release train cố định, hoặc chỉ có một pipeline với quyền quản trị quá rộng. Ngược lại, việc cùng phát hành vì quyết định tổ chức chưa chứng minh thiết kế code kém; cần tách nguyên nhân kỹ thuật và quy trình.

Các chỉ báo hữu ích:

- Tỷ lệ release phải phối hợp với dịch vụ khác.
- Thời gian hoàn thành một thay đổi nhỏ so với thời gian chạy test và chờ deploy liên nhóm.
- Số lần rollback liên dịch vụ vì API/schema không tương thích.
- Bao nhiêu workload bị ảnh hưởng khi một DB pool, DNS, quota hoặc message broker bị lỗi.
- Số runbook, cảnh báo và người trực phải tham gia vào một sự cố thường gặp.

## 5. Vì sao tách dịch vụ quá sớm làm tăng rủi ro?

### 5.1. Ranh giới nghiệp vụ chưa rõ

Khi sản phẩm còn tìm kiếm mô hình nghiệp vụ, quy tắc thường thay đổi. Nếu ranh giới được vẽ từ các bảng **User**, **Room**, **Booking**, **Price** mà chưa hiểu quy tắc giá, giữ chỗ và hủy, hệ thống dễ phải liên tục chuyển logic qua lại giữa dịch vụ.

Một cách tách hữu ích hơn là hỏi: **những bất biến nghiệp vụ nào cần được giữ nhất quán trong cùng một ranh giới?** Chẳng hạn, “không xác nhận trùng một phòng trong cùng kỳ” có thể cần giữ logic kiểm tra xung đột và ghi booking trong một transaction hoặc cơ chế điều khiển đồng thời phù hợp. Tách Inventory và Booking không rõ quyền sở hữu có thể biến việc bảo vệ bất biến thành bài toán giao dịch phân tán khó hơn.

### 5.2. Lựa chọn kỹ thuật kéo theo chi phí vận hành

Mỗi dịch vụ mới có thể cần các thành phần sau tùy nền tảng:

| Nhu cầu | Công việc bổ sung |
|---|---|
| **Triển khai** | Build, pipeline, cấu hình, rollout, rollback, tương thích API |
| **Giao tiếp** | DNS/service discovery, TLS/mTLS hoặc cơ chế bảo mật phù hợp, timeout, retry, version hợp đồng |
| **Dữ liệu** | Sở hữu và migration schema, CDC/event hoặc sao chép read model, khôi phục dữ liệu |
| **Quan sát** | Log, metrics, tracing, correlation ID, dashboard, cảnh báo và runbook |
| **An ninh** | Workload identity, IAM, secrets, quét cấu hình/dependency, chính sách mạng |
| **Phục hồi** | Xử lý lỗi từng phần, idempotency, retry/backoff, replay, kiểm thử sự cố |
| **Chi phí** | Compute nền, DB/queue, traffic xuyên zone/region, log ingestion và công trực vận hành |

Trên cloud, autoscaling và managed services giảm một phần công sức nhưng không xóa các trách nhiệm về thiết kế hành vi khi lỗi, quyền truy cập, billing và sự cố.

### 5.3. Độ tin cậy không tăng tự động khi chia nhỏ

Giả sử một request bắt buộc chờ phản hồi của năm dependency. Nếu mỗi dependency độc lập có xác suất sẵn sàng **99,9%** trong cùng khoảng đo và giả định tất cả đều cần thành công, xác suất thành công của toàn chuỗi theo mô hình đơn giản là:

\[
0{,}999^{5} \approx 99{,}50\%
\]

Đây là **ví dụ toán học minh họa**, không phải cách tính SLO production: sự cố thực tế thường tương quan, các luồng có retry, cache, dự phòng hoặc đường suy giảm khác nhau. Nó cho thấy khi một request phụ thuộc vào nhiều dịch vụ bắt buộc, **độ tin cậy đầu cuối phải được đo tại hành trình người dùng** thay vì suy ra từ SLO riêng lẻ.

### 5.4. Tính bảo mật và quyền cũng phức tạp hơn

Nhiều dịch vụ hơn thường đồng nghĩa nhiều workload identity, giao diện mạng, policy, secret và nguồn dữ liệu. Nếu đội nhỏ chưa có cơ chế cấp quyền tối thiểu, kiểm soát cấu hình, rotation và quan sát audit, việc tách sớm có thể làm tăng bề mặt cấu hình sai. Tách dịch vụ có thể giúp cô lập tài nguyên và dữ liệu **khi ranh giới quyền thực sự được thực thi**.

## 6. Tình huống xuyên suốt: nền tảng đặt phòng trên cloud

Một đội sáu kỹ sư phát triển nền tảng cho thuê chỗ ở. Để “chuẩn microservices ngay từ đầu”, nhóm tạo:

- **RoomService:** tra cứu thông tin phòng và tình trạng phòng.
- **AvailabilityService:** kiểm tra chỗ trống.
- **ReservationService:** tạo giữ chỗ, xác nhận đặt phòng.
- **PriceService:** tính báo giá và chiết khấu.
- **PaymentService:** kết nối nhà cung cấp thanh toán.
- **EmailService:** gửi thư xác nhận.

Mỗi service có container và pipeline riêng nhưng tất cả cùng truy cập bảng **rooms**, **reservations**, **prices** trong một DB. Reservation gọi Room rồi Availability rồi Price rồi Payment rồi Email trong một request HTTP. Mọi môi trường dùng chung một bộ migration và deploy đồng thời mỗi lần đổi cột.

### 6.1. Những vấn đề nhận diện được

| Quan sát | Cơ chế gây vấn đề | Câu hỏi phản biện |
|---|---|---|
| Room và Availability đều quyết định trạng thái còn chỗ | Không rõ nguồn sự thật và bất biến đặt trùng | Đâu là nơi duy nhất có quyền chấp nhận xác nhận? |
| Reservation chờ Email trả thành công | Giao tiếp không cần thiết trên đường critical path | Email lỗi có nên làm hủy một booking đã hợp lệ? |
| PriceService và Reservation cùng sửa cột tổng tiền | Coupling dữ liệu và thiếu quyền sở hữu giá đã chốt | Ai xác định và lưu snapshot giá có hiệu lực? |
| Mỗi service dùng cùng migration DB | Không có tự chủ thay đổi schema | Có thể áp dụng expand–migrate–contract không? |
| Cùng release một buổi tối | Phụ thuộc triển khai che giấu trong hợp đồng | Có thể triển khai consumer trước rồi producer tương thích? |
| Sáu dashboard nhưng thiếu SLI nghiệp vụ | Quan sát theo tài nguyên, thiếu hành trình đặt phòng | Bao nhiêu yêu cầu đặt phòng hợp lệ hoàn tất đúng SLO? |

### 6.2. Lỗi điển hình lúc khuyến mại

Khi lưu lượng tăng, EmailService trả lời chậm. Reservation vẫn chờ email dù DB đã ghi đặt chỗ. Người dùng thấy timeout và thử lại. Nếu thiếu **idempotency key** hoặc logic chống xử lý trùng, các lần thử lại có thể tạo thêm thao tác không mong muốn. Nếu Reservation tự retry đồng loạt mà không có backoff, EmailService còn bị dồn tải hơn.

Cách khắc phục không chỉ là tăng số replica EmailService. Trước hết cần xác định **gửi email có phải điều kiện xác nhận đặt chỗ không**. Nếu không, nên tách công việc thông báo khỏi đường phản hồi người dùng; đồng thời xử lý việc publish sự kiện sau commit, retry và trạng thái thông báo thất bại.

### 6.3. Thiết kế đơn giản hơn cho giai đoạn đầu

Nhóm có thể dùng **modular monolith** với các module Catalog, Pricing, Booking/Inventory, Payment Integration và Notification; giữ luật kiểm tra/chốt chỗ ở cùng ranh giới nhất quán. Các module tương tác qua hợp đồng nội bộ và chỉ có Booking/Inventory quyền cập nhật trạng thái quyết định đặt chỗ.

~~~mermaid
flowchart LR
    User["Web / Mobile"] --> App["Application / API"]
    subgraph AppBoundary["Một workload với các module"]
        App --> Catalog["Catalog"]
        App --> Pricing["Pricing"]
        App --> Booking["Booking + Inventory"]
        App --> Payment["Payment Integration"]
        App --> Notify["Notification Worker"]
    end
    Booking --> DB[("Booking DB")]
    Pricing --> DB
    Booking --> Outbox[("Transactional Outbox")]
    Outbox -. "Publisher" .-> Notify
    Payment --> Provider["Payment Provider"]
    Notify --> Mail["Email Provider"]
~~~

*Đây là sơ đồ logic minh họa, không phải quy tắc buộc mọi module phải cùng DB hoặc dùng queue. Trạng thái thanh toán và đặt chỗ phải được mô hình hóa phù hợp quy tắc nghiệp vụ. Outbox và worker có thể được triển khai trong cùng hệ thống ban đầu; nếu sử dụng, phải có cơ chế xử lý lặp và quan sát tác vụ.*

Khi Search tăng trưởng nhanh với kiểu tải đọc khác biệt, đội ngũ có thể **tách Search trước** nếu dữ liệu đọc, hợp đồng cập nhật và giới hạn độ mới đã rõ. Tách Booking/Inventory sớm chỉ vì có hai bảng thường nguy hiểm hơn vì quy tắc nhất quán chặt chẽ.

## 7. Ranh giới dịch vụ nên dựa trên điều gì?

### 7.1. Năng lực nghiệp vụ và lý do thay đổi

Một ranh giới tốt gom những quy tắc có **cùng mục đích, cùng vòng đời và thường thay đổi cùng nhau**, đồng thời giảm việc dịch vụ khác cần biết chi tiết nội bộ.

Ví dụ:

- Đổi công thức khuyến mại chủ yếu ảnh hưởng **Pricing**.
- Đổi quy tắc giữ phòng ảnh hưởng **Booking/Inventory**.
- Đổi nội dung SMS/email ảnh hưởng **Notification**.
- Đổi cấu hình tìm kiếm/đánh chỉ mục ảnh hưởng **Search**.

Nếu một yêu cầu “đổi phí hủy” luôn buộc sửa 4–5 dịch vụ, hãy kiểm tra quy tắc có đang bị phân tán quá mức hay không.

### 7.2. Bất biến dữ liệu và ranh giới transaction

**Bất biến** là điều phải đúng sau mọi thao tác hợp lệ. Ví dụ, không có hai booking đã xác nhận chồng lấn cho cùng một tài sản nếu sản phẩm cấm trùng lịch. Nên xác định nơi sở hữu bất biến và cách bảo vệ nó trước khi quyết định tách database hay deployment.

Đặt nhiều dịch vụ trên cùng một chuỗi **check-then-write** không tự đảm bảo tính nguyên tử. Có thể cần giao dịch DB, khóa/ràng buộc dữ liệu, optimistic concurrency hoặc thiết kế khác phù hợp. Khi tách ra nhiều ranh giới, cần xác định điều gì có thể nhất quán sau (eventual consistency) và điều gì phải xác nhận ngay.

### 7.3. Tính độc lập thực tế của đội ngũ

Microservices hữu ích hơn khi một nhóm có thể **phát triển, kiểm thử, triển khai, quan sát và xử lý sự cố** của một năng lực mà không phải kéo nhiều nhóm khác vào mỗi thay đổi. Ngược lại, nếu cùng vài kỹ sư duy trì toàn bộ dịch vụ, nhiều repository/pipeline có thể tăng công việc hành chính mà không tăng tốc độ phát triển.

Không dùng số lượng nhân sự cố định như ngưỡng cứng: năng lực tự động hóa, độ phức tạp domain và yêu cầu tuân thủ cũng tác động.

### 7.4. Yêu cầu scale, cô lập và tuân thủ

Cân nhắc tách một service nếu:

- Tải hoặc đặc tính tài nguyên khác hẳn (ví dụ Search cần tối ưu CPU/đọc, Booking cần transaction và I/O).
- Có yêu cầu triển khai/phục hồi riêng, với ranh giới lỗi và phương án tương thích rõ.
- Dữ liệu hoặc chức năng cần kiểm soát quyền khác biệt, có thể thiết lập ranh giới bảo mật thật sự.
- Đội sở hữu thay đổi độc lập đủ thường xuyên để lợi ích vượt chi phí vận hành.

Không nên tách chỉ để “tận dụng Kubernetes” hoặc “sử dụng autoscaling”. Một ứng dụng nguyên khối vẫn có thể scale ngang; việc tách mới đem lại lợi ích nếu tối ưu tài nguyên hoặc vòng đời các phần khác nhau.

## 8. Quyết định giữa modular monolith và microservices

| Tiêu chí | Nghiêng về **modular monolith** | Nghiêng về **microservices** |
|---|---|---|
| **Domain** | Nghiệp vụ còn đổi thường xuyên, ranh giới chưa ổn định | Capability và bất biến có chủ sở hữu rõ |
| **Đội ngũ** | Nhóm nhỏ, vận hành tập trung, ít nhu cầu release độc lập | Nhiều nhóm đủ năng lực tự vận hành và phát hành |
| **Giao dịch** | Nhiều quy tắc cần tính nguyên tử trên cùng dữ liệu | Có thể mô hình hóa trạng thái và nhất quán xuyên ranh giới |
| **Tải** | Phần lớn thành phần tăng/giảm cùng kiểu tải | Có workload có nhu cầu scale rất khác biệt |
| **Độ tin cậy** | Ít nhu cầu cô lập runtime; đường mạng tối giản | Cần giới hạn ảnh hưởng, và đã có timeout, fallback, quan sát |
| **Chi phí** | Ngân sách cloud/nhân lực hạn chế, ưu tiên đơn giản | Chi phí độc lập runtime, DB, network và telemetry được biện minh |
| **Bảo mật** | Kiểm soát trong cùng ứng dụng đủ đáp ứng phân quyền nghiệp vụ | Cần ranh giới danh tính/quyền/dữ liệu riêng và đủ năng lực quản trị |
| **Tốc độ thay đổi** | Số lượng thay đổi liên module thấp hoặc chưa đo | Nhiều lần thay đổi cục bộ bị kẹt vì lịch release chung |

Không có một ngưỡng “trên N người dùng phải dùng microservices”. Cần đo **tải thực, nút nghẽn, lịch sử thay đổi và năng lực vận hành**. Thậm chí sau khi chọn microservices, vẫn có thể giữ các module khác trong một đơn vị triển khai.

## 9. Tách dịch vụ theo từng bước, không tách đồng loạt

### Bước 1 — Thu thập bằng chứng hiện trạng

Chọn một hành trình cụ thể, chẳng hạn **tìm phòng → giữ chỗ → thanh toán → xác nhận**. Dùng trace, logs và sơ đồ dữ liệu để ghi nhận:

- Các thành phần tham gia, phương thức gọi và điều kiện bắt buộc.
- Ai sở hữu các bảng/trạng thái, nơi nào thay đổi cùng nhau.
- Độ trễ p95/p99, tỷ lệ lỗi, số retry, nút nghẽn DB/queue và chi phí.
- Lịch sử deployment, rollback, sự cố, mức độ phối hợp liên nhóm.

Đừng vẽ microservices tương lai trước khi nhìn thấy luồng dữ liệu và giới hạn của hệ thống hiện tại.

### Bước 2 — Định nghĩa module và hợp đồng trước

Trong monolith, gom logic theo capability và quy định module nào được truy cập dữ liệu nào. Tạo API nội bộ hoặc interface cho những tương tác thật sự có nhu cầu:

~~~java
// Hợp đồng do module Booking công bố.
public interface BookingFacade {
    BookingResult confirm(ConfirmBookingCommand command);
    BookingStatus getStatus(BookingId bookingId);
}

// Consumer chỉ biết yêu cầu nghiệp vụ.
public record ConfirmBookingCommand(
        String bookingId,
        String quoteId,
        String idempotencyKey) {}
~~~

Ví dụ trên chỉ mô tả **ranh giới hợp đồng**. Việc kiểm tra quote, giữ chỗ, thanh toán và trạng thái idempotency phải được triển khai theo quy tắc nghiệp vụ; khai báo interface không tự đảm bảo các tính chất đó.

Nếu một interface chỉ phản chiếu từng cột bảng và bắt caller gọi mười lần mới hoàn thành một thao tác, hợp đồng cần được thiết kế lại theo **ý nghĩa nghiệp vụ**, không phải chuyển nguyên thao tác CRUD sang HTTP.

### Bước 3 — Kiểm thử ranh giới và tính tương thích

- Unit/domain tests kiểm tra bất biến và chuyển trạng thái.
- Architecture tests chặn import xuyên package/module không hợp lệ.
- Contract tests kiểm tra producer/consumer khi API hoặc event thay đổi.
- Load/fault tests đánh giá timeout, idempotency, backlog và khả năng suy giảm.
- Review quyền dữ liệu, log nhạy cảm, secret và audit cho từng ranh giới.

Cần có **fitness functions** (phép kiểm chứng kiến trúc) mà team thực sự chạy trong CI hoặc quy trình review. Không cần phức tạp hóa công cụ trước khi nhu cầu rõ.

### Bước 4 — Chọn một capability có lợi ích tách rõ

Ví dụ, tách **Search** khi tải tìm kiếm vượt trội, read model có thể cập nhật theo sự kiện và chấp nhận một độ trễ nhất định; hoặc tách **Notification** khi vòng đời gửi/đặt lịch khác biệt và ranh giới lỗi đã rõ.

Đặt giả thuyết cụ thể: “Tách Search giúp mở rộng compute đọc riêng, giảm tranh chấp tài nguyên với Booking, trong khi giá trị p95 và chi phí mỗi truy vấn vẫn đạt mục tiêu”. Có giả thuyết mới biết kết quả tách có hiệu quả không.

### Bước 5 — Chuyển giao dữ liệu và hợp đồng an toàn

Quy trình tham khảo:

1. Xác định **source of truth** và ai có quyền ghi trong từng giai đoạn.
2. Tạo hợp đồng tương thích ngược; dùng **expand → migrate → contract** cho schema/API khi phù hợp.
3. Sao chép hoặc backfill dữ liệu cần thiết; đo độ trễ, kiểm tra sai lệch và cơ chế xử lý bản ghi lỗi.
4. Chuyển một nhóm lưu lượng nhỏ qua endpoint mới hoặc routing có kiểm soát.
5. So sánh kết quả nghiệp vụ, lỗi, hiệu năng, chi phí và SLO; rollback hoặc tiếp tục theo tiêu chí định trước.
6. Sau khi đã đổi quyền sở hữu, loại bỏ đường ghi cũ, dữ liệu/cấu hình dư thừa và cập nhật tài liệu.

**Tránh ghi hai nguồn dữ liệu độc lập mà không có quy tắc đối soát.** Dual-write qua hai DB có thể tạo trạng thái lệch nếu một bên thành công và bên kia thất bại. Nếu phải dùng CDC, outbox hay đồng bộ sự kiện, cần cơ chế giao lại, xử lý trùng, quan sát độ trễ và kế hoạch khôi phục.

### Bước 6 — Vận hành độc lập và đóng vòng đo lường

Chỉ coi một dịch vụ là thực sự độc lập khi đội sở hữu có thể triển khai hợp đồng tương thích, theo dõi SLO, xử lý lỗi và phục hồi **trong phạm vi đã định**, không đòi hỏi toàn bộ hệ thống cùng rollback cho phần lớn thay đổi thường ngày.

Nếu chi phí, sự cố hoặc thời gian phối hợp tăng mà lợi ích chưa đạt, cân nhắc **giữ chung hoặc nhập lại ranh giới**. Ranh giới dịch vụ là quyết định có thể điều chỉnh, không phải mục tiêu một chiều.

## 10. Thiết kế giao tiếp để tránh tái tạo nguyên khối phân tán

### 10.1. Đồng bộ khi thực sự cần kết quả ngay

Ví dụ, thao tác xác nhận đặt chỗ có thể cần giá đã chấp nhận và kiểm tra tình trạng còn chỗ trước khi báo thành công. Với RPC/HTTP đồng bộ:

- Xác định **timeout budget** cho hành trình; các cuộc gọi con phải nằm trong giới hạn đó.
- Giới hạn retry với backoff/jitter khi phù hợp; không retry thao tác không idempotent nếu không có cơ chế an toàn.
- Có circuit breaker, bulkhead, rate limit hoặc backpressure tùy ngữ cảnh.
- Mô tả trường hợp không thể tiếp tục: từ chối rõ ràng, giữ trạng thái chờ hay dùng nguồn dữ liệu đã được xác nhận trước đó.
- Dùng authentication/authorization giữa workload, mã hóa đường truyền và quan sát request ID/trace ID.

**Fallback không được phá bất biến.** Nếu hệ thống Inventory không phản hồi, không thể tùy tiện dùng cache tìm kiếm để khẳng định còn phòng.

### 10.2. Bất đồng bộ khi nghiệp vụ chấp nhận xử lý sau

Đối với thông báo, analytics hoặc một số tích hợp hậu giao dịch, event/queue giúp giảm coupling thời điểm. Nhưng phải chấp nhận **eventual consistency**, sự kiện có thể đến trễ hoặc lặp và cần quan sát trạng thái.

~~~mermaid
sequenceDiagram
    participant U as Khách hàng
    participant B as Booking
    participant DB as DB + Outbox
    participant Q as Queue
    participant N as Notification
    U->>B: Xác nhận đặt phòng (idempotency key)
    B->>DB: Transaction kiểm tra bất biến + ghi Booking + outbox
    alt Không hợp lệ
        DB-->>B: Rollback / conflict
        B-->>U: Thất bại rõ lý do
    else Commit thành công
        DB-->>B: Commit
        B-->>U: Trạng thái đã xác nhận
        Note over DB,Q: Relay chuyển sự kiện sau commit
        DB-->>Q: BookingConfirmed
        Q-->>N: Nhận sự kiện (có thể nhận lại)
        N->>N: Kiểm tra idempotency / retry
    end
~~~

**Transactional outbox** giúp giải quyết khoảng trống giữa commit dữ liệu nghiệp vụ và phát sự kiện bằng cách ghi event vào outbox cùng transaction, sau đó relay gửi đi. Nó **không** mặc nhiên đảm bảo thư email chỉ gửi đúng một lần: việc giao lại event, retry worker và hành vi provider vẫn cần cơ chế phù hợp.

### 10.3. Không đẩy mọi giao dịch thành Saga chỉ vì có microservices

**Saga** mô hình hóa chuỗi bước cục bộ với hành động bù trừ khi quy trình xuyên nhiều ranh giới, chẳng hạn giữ chỗ, yêu cầu thanh toán rồi xác nhận. Saga đòi hỏi xác định trạng thái trung gian, thời hạn chờ, kết quả không rõ, retry an toàn và cả trường hợp bù trừ thất bại.

Nếu một bất biến có thể được giữ trong **một ranh giới transaction đơn giản**, không nên chia nó ra nhiều dịch vụ rồi tạo Saga để vá hậu quả. Saga hữu ích với quy trình thực sự dài và nhiều chủ sở hữu; không thay thế thiết kế nhất quán dữ liệu.

## 11. Đo chi phí và lợi ích của việc tách

Một thiết kế chỉ nên được đánh giá qua **thực tế vận hành và thay đổi**:

| Chỉ số | Trước khi tách | Sau khi tách cần kiểm chứng |
|---|---|---|
| **Lead time cho một thay đổi cục bộ** | Thời gian từ commit đến deploy an toàn | Có giảm mà không tăng sự cố không? |
| **Deployment coupling** | Bao nhiêu release cần phối hợp nhiều module/dịch vụ | Có thể deploy độc lập phần lớn thay đổi không? |
| **Thời gian khôi phục (MTTR)** | Bao lâu tìm và khắc phục sự cố | Phạm vi ảnh hưởng có nhỏ hơn và khôi phục nhanh hơn không? |
| **Độ trễ p95/p99** | Hành trình quan trọng trước tách | Số network hop mới có làm vượt ngưỡng không? |
| **Lỗi đầu cuối** | SLI thành công của tạo booking/checkout | Có cải thiện dù dependency cục bộ còn lỗi không? |
| **Tải tài nguyên** | CPU, DB pool, lock, I/O, queue, quota | Có scale đúng workload mà không tạo bottleneck chung không? |
| **Chi phí mỗi giao dịch** | Compute, storage, egress, telemetry và vận hành | Lợi ích mới có tương xứng chi phí nền và mạng không? |
| **Số nhóm tham gia một thay đổi/sự cố** | Độ phức tạp phối hợp | Chủ sở hữu có rõ hơn không? |

Ví dụ, một đội đặt mục tiêu giảm tỷ lệ phát hành phối hợp từ 70% xuống dưới 20% trong những thay đổi thuộc riêng Search và giữ p95 tìm kiếm trong SLO. Các con số **chỉ là ví dụ về cách thiết lập tiêu chí**, không phải ngưỡng chuẩn cho mọi sản phẩm.

Phải thống nhất khoảng đo, tải so sánh và cách phân bổ chi phí trước/sau. Nếu chỉ đo số container hoặc số deploy mỗi tuần, đội ngũ có thể tối ưu một biểu hiện kỹ thuật mà không cải thiện giá trị nghiệp vụ.

## 12. Đánh đổi theo tư duy Well-Architected

| Góc nhìn | Tách đúng ranh giới có thể giúp | Tách quá sớm có thể gây |
|---|---|---|
| **Operational excellence** | Đội sở hữu rõ, triển khai và khắc phục độc lập | Nhiều pipeline, runbook, dashboard; phối hợp sự cố phức tạp |
| **Reliability** | Giới hạn lỗi, cô lập workload, khôi phục theo thành phần | Nhiều điểm lỗi mạng, retry storm, dữ liệu bất nhất |
| **Security** | IAM và phạm vi dữ liệu theo capability | Nhiều danh tính, secret, endpoint và policy dễ cấu hình sai |
| **Performance efficiency** | Scale riêng workload có nhu cầu khác nhau | Network hop, serialization, fan-out và DB contention |
| **Cost optimization** | Tránh cấp dư cho mọi thành phần, tối ưu theo tải | Chi phí compute nền, gateway, broker, DB, network, log/traces |
| **Sustainability** | Sử dụng tài nguyên đúng tải, giảm lãng phí khi cần | Nhiều dịch vụ nhàn rỗi, dữ liệu sao chép và giao tiếp không cần thiết |

Độ tin cậy phải bao gồm các kịch bản sự cố phù hợp. **RTO** mô tả mục tiêu thời gian khôi phục và **RPO** mô tả mức mất dữ liệu chấp nhận được theo thời gian; tách dịch vụ không tự động đạt các mục tiêu đó. Cần kiểm tra lỗi zone/region, khôi phục DB, sai cấu hình IAM, broker ngừng hoạt động và khả năng quay lại phiên bản an toàn.

Một lưu ý cho kiến trúc mạng: nếu nhiều dịch vụ chạy trong cùng cluster/zone nhưng mọi cuộc gọi phải qua một gateway hay NAT trung tâm, việc “phân tán” có thể tăng độ trễ, chi phí và điểm lỗi chung. Cần đo **đường đi thực**, routing, DNS, quota và quyền giữa dịch vụ thay vì chỉ đếm nơi deploy.

## 13. ADR: quyết định chưa tách Booking và Inventory

~~~text
ADR-021 — Giữ Booking và Inventory trong cùng ranh giới lúc đầu
Trạng thái: Accepted

Bối cảnh
  Sản phẩm còn thay đổi quy tắc giữ chỗ và hủy.
  Một bất biến quan trọng là không xác nhận trùng chỗ.
  Đội hiện có ít người, chưa cần triển khai riêng hai capability.

Các phương án
  A. Tách Booking và Inventory thành hai dịch vụ/DB ngay.
  B. Giữ chung trong một module nghiệp vụ có transaction rõ;
     công bố API ổn định cho module khác.

Quyết định
  Chọn B trong giai đoạn này.

Lý do
  Giảm phối hợp giao dịch phân tán, đơn giản hóa kiểm thử
  concurrency và vận hành, giữ ranh giới nghiệp vụ rõ.

Hệ quả
  + Dễ kiểm soát bất biến và chỉnh sửa rule.
  - Booking/Inventory chưa scale hoặc deploy độc lập.
  - Phải giữ discipline về module boundary và quyền ghi.

Kiểm chứng
  - Concurrency tests cho quy tắc không đặt trùng.
  - Đo latency, DB pool, tỷ lệ lỗi và release coupling.
  - Theo dõi thay đổi nghiệp vụ buộc chạm cả hai module.

Xem lại khi
  Nhu cầu scale, quyền sở hữu hoặc chu kỳ release khác biệt
  xuất hiện rõ và có phương án đảm bảo consistency.
~~~

ADR phải mô tả **vì sao quyết định phù hợp trong bối cảnh hiện tại**, tác động và điều kiện xem lại. Không nên ghi “chọn microservices vì đó là chuẩn hiện đại” như lý do kỹ thuật.

## 14. Checklist phát hiện và phòng tránh nguyên khối phân tán

Trước khi chia một hệ thống thành nhiều dịch vụ, hãy kiểm tra:

- [ ] Đã xác định mục tiêu nghiệp vụ và vấn đề hiện tại mà việc tách phải giải quyết.
- [ ] Các capability và bất biến cần giữ nhất quán có chủ sở hữu rõ.
- [ ] Mỗi dịch vụ có một lý do thay đổi tương đối tập trung và công bố hợp đồng có ý nghĩa nghiệp vụ.
- [ ] Không có việc nhiều dịch vụ tự ghi cùng dữ liệu nội bộ ngoài một quy trình quản lý rõ ràng.
- [ ] Có chiến lược tương thích API, schema và event khi producer/consumer triển khai lệch phiên bản.
- [ ] Đã thử trường hợp một dependency chậm, lỗi hoặc xử lý trùng; có timeout, retry và fallback phù hợp.
- [ ] Đã phân biệt bước nghiệp vụ bắt buộc đồng bộ với công việc có thể xử lý sau.
- [ ] Đã thiết kế cơ chế bảo vệ bất biến, giao dịch và trạng thái trung gian khi tách dữ liệu.
- [ ] Mỗi dịch vụ có owner, IAM/secret, observability, runbook và cách khôi phục tương ứng.
- [ ] Có baseline đo release coupling, p95/p99, SLI/SLO, chi phí và phạm vi sự cố trước khi tách.
- [ ] Đã so sánh với phương án modular monolith hoặc tách module nội bộ trước.
- [ ] Có kế hoạch chuyển giao dữ liệu từng bước, rollback/roll-forward và loại bỏ đường ghi cũ.
- [ ] Quyết định tách được ghi trong ADR cùng lợi ích kỳ vọng, đánh đổi và tiêu chí xem lại.

## 15. Bài tập thực hành

**Tình huống:** Một startup quản lý cho thuê xe có bốn kỹ sư. Hệ thống hiện là một ứng dụng Java với các module Reservation, Fleet, Pricing, Billing và Notification. Đội dự định chia thành năm microservices, mỗi dịch vụ có DB riêng, deploy lên Kubernetes. Các yêu cầu hiện có: không được đặt trùng xe, phải xuất hóa đơn, thời gian tìm xe có thể tăng đột biến vào cuối tuần; đội chưa có người trực SRE chuyên trách.

Hãy xây dựng đề xuất kiến trúc:

1. Xác định **những bất biến cần xử lý nhất quán** và những tác vụ có thể hoàn thành sau giao dịch chính.
2. Chỉ ra ít nhất **bốn rủi ro** nếu tách toàn bộ năm dịch vụ ngay bây giờ.
3. Đề xuất một **modular monolith** có ranh giới rõ hoặc một phần dịch vụ đáng tách riêng, giải thích vì sao.
4. Vẽ luồng **đặt xe** và mô tả hành vi khi Billing hoặc Notification không phản hồi.
5. Đặt **ba giả thuyết có thể đo** để xem khi nào cần tách Search/Fleet hoặc Notification.
6. Viết ADR ngắn ghi quyết định, hệ quả và điều kiện xem lại.

**Gợi ý định hướng:** Ranh giới giữ xe và xác nhận đặt xe cần bảo vệ bất biến bằng transaction/cơ chế đồng thời phù hợp. Notification thường có thể xử lý bất đồng bộ; Billing có thể đòi hỏi quy trình trạng thái tùy quy tắc phát hành hóa đơn/thanh toán. Tải tìm kiếm tăng là dấu hiệu nên tối ưu dữ liệu đọc, cache hoặc scale workload trước khi quyết định tách toàn bộ domain. Mọi phương án đều cần giám sát, phân quyền và phục hồi tương ứng.

## 16. Ghi nhớ

**Nguyên khối phân tán** xuất hiện khi hệ thống mang hình thức nhiều dịch vụ nhưng vẫn bị ràng buộc bởi dữ liệu, luồng chạy, phiên bản hoặc quy trình phát hành chung. **Tách dịch vụ quá sớm** thường khiến đội ngũ giải bài toán mạng, giao dịch phân tán và vận hành trước khi hiểu rõ ranh giới nghiệp vụ cần bảo vệ.

Thiết kế tốt bắt đầu từ **capability, bất biến, dữ liệu sở hữu, tải và quyền vận hành**, rồi chọn mô hình triển khai phù hợp. Một modular monolith có ranh giới tốt có thể là nền tảng để tiến hóa sang microservices khi có bằng chứng rõ; microservices chỉ tạo ra giá trị khi quyền tự chủ và khả năng chịu lỗi đủ thực chất để bù đắp chi phí phân tán.
