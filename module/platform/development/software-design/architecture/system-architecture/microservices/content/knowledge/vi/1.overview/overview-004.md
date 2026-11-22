# Đặc trưng tự chủ, triển khai độc lập và sở hữu theo năng lực nghiệp vụ

## 1. Vị trí của ba đặc trưng trong kiến trúc Microservices

Microservices là cách tổ chức một hệ thống thành các dịch vụ nhỏ tương đối độc lập, mỗi dịch vụ đảm nhận một phần nghiệp vụ có ranh giới rõ ràng. Ba đặc trưng quan trọng liên kết chặt chẽ với nhau:

- **Tự chủ (autonomy):** dịch vụ có quyền quyết định và kiểm soát phần nghiệp vụ, dữ liệu, triển khai và vận hành thuộc phạm vi của mình.
- **Triển khai độc lập (independent deployment):** có thể đưa một thay đổi của một dịch vụ lên môi trường chạy mà không phải đồng thời phát hành những dịch vụ không liên quan.
- **Sở hữu theo năng lực nghiệp vụ (business-capability ownership):** ranh giới dịch vụ và trách nhiệm của đội ngũ được xác định bởi kết quả nghiệp vụ mà họ chịu trách nhiệm, ví dụ quản lý đơn hàng, thanh toán hoặc tồn kho.

Ba yếu tố tạo thành một quan hệ nhân quả: **ranh giới nghiệp vụ rõ → quyền sở hữu rõ → ít phụ thuộc thay đổi → triển khai độc lập khả thi**. Chỉ tách mã nguồn thành nhiều ứng dụng không tự động đem lại các lợi ích này. Nếu mọi thay đổi đều phải sửa đồng loạt năm dịch vụ, chờ một lịch phát hành chung và truy cập trực tiếp cùng một cơ sở dữ liệu, hệ thống vẫn bị ghép chặt dù chạy qua mạng.

Một microservice không cần “độc lập tuyệt đối”. Dịch vụ vẫn phối hợp qua API, sự kiện, hạ tầng chung và chính sách kỹ thuật chung. Mục tiêu là **kiểm soát phụ thuộc tại các ranh giới đã công bố**, đặc biệt là phụ thuộc khiến thay đổi của một nhóm kéo theo thay đổi bắt buộc của nhóm khác.

## 2. Tự chủ của một microservice nghĩa là gì?

Tự chủ không đơn giản là mỗi dịch vụ có tiến trình riêng. Đó là khả năng đưa ra thay đổi trong phạm vi mình sở hữu, với hợp đồng tương tác ổn định và trách nhiệm vận hành xác định.

| Khía cạnh | Biểu hiện của tự chủ | Dấu hiệu bị ghép chặt |
| --- | --- | --- |
| Nghiệp vụ | Quy tắc và trạng thái của một năng lực được quản lý trong một ranh giới | Một quy tắc phải sửa đồng thời ở nhiều dịch vụ |
| Mã nguồn | Dịch vụ có mã nguồn, kiểm thử và chu kỳ thay đổi rõ | Nhiều dịch vụ bắt buộc cập nhật chung một thư viện nghiệp vụ |
| Dữ liệu | Dịch vụ là chủ sở hữu việc ghi và diễn giải dữ liệu của mình | Dịch vụ khác cập nhật trực tiếp bảng dữ liệu nội bộ |
| Hợp đồng | Khách hàng dùng API hoặc event có phiên bản, quy tắc tương thích | Khách hàng phụ thuộc cột DB, class nội bộ hoặc thứ tự gọi ngầm |
| Triển khai | Có pipeline, gói triển khai và khả năng rollback/roll-forward phù hợp | Chỉ phát hành được khi toàn bộ hệ thống cùng lên phiên bản mới |
| Vận hành | Có metric, log, trace, cảnh báo, SLO và người chịu trách nhiệm | Lỗi xảy ra nhưng không xác định được dịch vụ/người sở hữu |

### 2.1. Tự chủ nghiệp vụ

Một dịch vụ nên tự thực thi các **bất biến nghiệp vụ** (business invariants) nằm trong ranh giới của nó. Ví dụ, Inventory Service phải giữ quy tắc “không xác nhận giữ hàng vượt quá tồn kho khả dụng”; Payment Service kiểm soát trạng thái giao dịch thanh toán; Order Service kiểm soát vòng đời đơn hàng.

Không nên yêu cầu Order Service tự cập nhật bảng tồn kho để tạo đơn, vì như vậy Order Service phải biết cấu trúc dữ liệu và quy tắc riêng của Inventory. Nó nên gửi yêu cầu giữ hàng qua giao diện công bố, hoặc tham gia một quy trình phối hợp được thiết kế rõ ràng.

### 2.2. Tự chủ dữ liệu

“Sở hữu dữ liệu” có nghĩa là một dịch vụ chịu trách nhiệm **nguồn sự thật** (source of truth), quy tắc ghi và ý nghĩa của dữ liệu thuộc năng lực đó. Có thể sử dụng chung máy chủ cơ sở dữ liệu vì lý do hạ tầng, nhưng cần ranh giới quyền truy cập rõ: lý tưởng là mỗi dịch vụ có database/schema và tài khoản riêng; dịch vụ khác không ghi trực tiếp vào bảng của chủ sở hữu.

Ví dụ, Payment Service là nguồn sự thật cho giao dịch thanh toán. Order Service có thể lưu bản chiếu (projection) trạng thái thanh toán để phục vụ hiển thị, nhưng bản chiếu này phải được đồng bộ qua hợp đồng API hoặc event, không được coi là chủ sở hữu chính thức của dữ liệu thanh toán.

### 2.3. Tự chủ công nghệ và vận hành

Tự chủ có thể cho phép một dịch vụ dùng ngôn ngữ hoặc kho dữ liệu phù hợp với yêu cầu riêng. Tuy nhiên, **tự do công nghệ không đồng nghĩa chọn công nghệ tùy ý**. Tiêu chuẩn bảo mật, quan sát hệ thống, quản lý bí mật, giao thức giao tiếp và quy trình khôi phục vẫn cần thống nhất đủ mức để hệ thống có thể vận hành.

Một đội được xem là sở hữu dịch vụ trọn vòng đời khi họ có khả năng hiểu yêu cầu, phát triển, kiểm thử, triển khai, theo dõi, xử lý sự cố và cải thiện chính dịch vụ đó; việc này có thể được hỗ trợ bởi đội nền tảng và đội vận hành chung.

## 3. Thiết kế ranh giới theo năng lực nghiệp vụ

**Năng lực nghiệp vụ (business capability)** mô tả một việc doanh nghiệp cần làm để tạo giá trị, chẳng hạn “quản lý đơn hàng”, “thu tiền” hoặc “kiểm soát tồn kho”. Đây là cơ sở tốt hơn tên lớp kỹ thuật khi quyết định ranh giới dịch vụ.

Xét hệ thống bán hàng trực tuyến:

| Năng lực | Dịch vụ minh họa | Trách nhiệm cốt lõi và dữ liệu sở hữu |
| --- | --- | --- |
| Quản lý danh mục | Catalog Service | Sản phẩm, mô tả, trạng thái công bố |
| Quản lý đơn hàng | Order Service | Vòng đời đơn hàng, dòng hàng đã đặt, trạng thái đơn |
| Quản lý tồn kho | Inventory Service | Số lượng khả dụng, giữ hàng, xuất/hoàn tồn |
| Thanh toán | Payment Service | Yêu cầu thanh toán, giao dịch, hoàn tiền |
| Giao vận | Shipping Service | Lệnh giao hàng, trạng thái giao, vận đơn |

Các tên gọi trên chỉ là **mô hình minh họa**. Ranh giới thực tế phải xuất phát từ miền nghiệp vụ, cách tổ chức vận hành, quy tắc giao dịch, nhu cầu mở rộng và tần suất thay đổi. Một năng lực có thể đủ nhỏ để nằm trong một dịch vụ, hoặc cần chia tiếp thành nhiều bounded context khi miền nghiệp vụ lớn và các mô hình có ý nghĩa khác nhau.

### 3.1. Liên hệ với DDD và bounded context

Trong Domain-Driven Design (DDD), **bounded context** là ranh giới trong đó một mô hình, thuật ngữ và tập quy tắc nghiệp vụ có ý nghĩa nhất quán. Đây là một gợi ý mạnh để nhận diện ranh giới dịch vụ; không nhất thiết mọi bounded context đều phải được triển khai thành một microservice riêng.

Ví dụ, “trạng thái đơn hàng” trong Order Service và “trạng thái giao dịch” trong Payment Service là hai mô hình khác nhau. Tránh dùng chung một entity Order chứa toàn bộ thông tin thanh toán, tồn kho, giao vận và bắt mọi dịch vụ phụ thuộc vào entity này.

Các câu hỏi hữu ích khi xác định ranh giới:

1. Năng lực nào thay đổi do cùng một nhóm quy tắc nghiệp vụ?
2. Dữ liệu nào cần đảm bảo nhất quán mạnh trong **một giao dịch cục bộ**?
3. Ai có thể giải thích và chịu trách nhiệm về các quyết định nghiệp vụ?
4. Những thay đổi nào thường đi cùng nhau, và những thay đổi nào nên tách nhau?
5. API/event nào đủ ổn định để hợp tác với các dịch vụ khác?
6. Ranh giới này có giúp một đội triển khai và xử lý sự cố mà không cần phối hợp rộng hay không?

### 3.2. Tránh chia dịch vụ theo tầng kỹ thuật

Cách chia “Controller Service – Business Logic Service – Database Service” chỉ tái hiện mô hình phân tầng qua mạng. Mỗi yêu cầu buộc đi qua nhiều dịch vụ và mỗi tính năng thường đụng tất cả các tầng; các nhóm khó triển khai độc lập.

Ngược lại, Order Service có thể **chứa đầy đủ controller, application service, domain model và repository của riêng nó**. Catalog Service cũng như vậy. Mỗi dịch vụ là một lát cắt dọc theo năng lực nghiệp vụ, thay vì một lát cắt ngang theo công nghệ.

Một dấu hiệu ranh giới quá vụn là “một endpoint CRUD = một microservice” dù các endpoint cùng thuộc một giao dịch hoặc cùng một mô hình nghiệp vụ. Dịch vụ càng nhỏ không mặc nhiên càng tốt; chi phí liên lạc mạng, triển khai, quan sát và quản trị cũng tăng.

## 4. Triển khai độc lập: định nghĩa và điều kiện thực tế

**Triển khai độc lập** nghĩa là khi Order Service bổ sung một trường trả về tương thích, nhóm Order có thể build, kiểm thử, phát hành và theo dõi phiên bản mới mà không cần buộc Payment Service hoặc Inventory Service lên phiên bản mới tại cùng thời điểm.

Cần phân biệt:

- **Triển khai độc lập:** một thành phần có thể phát hành một mình.
- **Thay đổi nghiệp vụ độc lập:** thay đổi có thể hoàn thành trong một ranh giới nghiệp vụ; một tính năng liên miền vẫn có thể yêu cầu nhiều đội phối hợp.
- **Mở rộng độc lập:** tăng/giảm số instance hoặc tài nguyên cho riêng dịch vụ có nhu cầu.
- **Khả năng sẵn sàng độc lập:** một dịch vụ có thể giảm ảnh hưởng khi phụ thuộc lỗi, nhưng không bảo đảm mọi luồng nghiệp vụ vẫn hoạt động khi dịch vụ khác ngừng.

### 4.1. Các điều kiện cần

**Hợp đồng tương thích:** API và event cần cho phép client cũ cùng tồn tại với phiên bản server mới trong giai đoạn chuyển đổi. Thêm trường tùy chọn thường an toàn hơn xóa/đổi nghĩa trường đang dùng; không được giả định mọi consumer tự chấp nhận thay đổi.

**Pipeline riêng:** mỗi dịch vụ có thể tạo artifact bất biến, chạy kiểm thử tự động, kiểm tra bảo mật, phát hành và theo dõi kết quả. Có thể dùng chung công cụ CI/CD, nhưng không buộc mọi dịch vụ cùng phát hành.

**Thay đổi dữ liệu an toàn:** migration phải được thiết kế để phiên bản ứng dụng đang chạy và phiên bản mới có thể cùng làm việc trong thời gian chuyển đổi. Một migration phá vỡ schema ngay khi deploy sẽ làm mất tính độc lập.

**Tài nguyên và cấu hình tách bạch:** dịch vụ có cấu hình, secret, chính sách tài nguyên và health check phù hợp; quy trình deploy của một dịch vụ không thay thế hoặc restart không cần thiết toàn bộ hệ thống.

**Khả năng phát hiện và phục hồi:** metric, distributed tracing, log có correlation ID, cảnh báo, rollback hoặc roll-forward, và cách xử lý lỗi dữ liệu cho phép đội ngũ đánh giá nhanh bản phát hành.

**Quản lý phụ thuộc:** hợp đồng dịch vụ, thư viện dùng chung và chính sách thay đổi được kiểm soát; tránh bắt tất cả repository nâng phiên bản thư viện nghiệp vụ trong một lần phát hành.

### 4.2. Ví dụ thay đổi API theo hướng tương thích

Giả sử Order Service có API:

~~~http
GET /orders/ORD-1001

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "ORD-1001",
  "status": "CONFIRMED",
  "totalAmount": 350000
}
~~~

Nhóm Order muốn thêm thời điểm xác nhận. Cách triển khai thường phù hợp là thêm trường **confirmedAt** tùy chọn và giữ nguyên nghĩa các trường cũ; cần xác nhận consumer hiện tại xử lý được trường mới. Nếu cần đổi tên hoặc xóa **status**, có thể đi theo chu kỳ mở rộng rồi thu hẹp (*expand–migrate–contract*):

1. **Mở rộng:** cung cấp cả giao diện cũ và mới; bổ sung trường hoặc endpoint mới mà chưa bỏ phiên bản cũ.
2. **Di chuyển consumer:** cập nhật lần lượt các consumer, theo dõi mức sử dụng và kiểm thử hợp đồng.
3. **Thu hẹp:** chỉ bỏ giao diện cũ khi không còn consumer phụ thuộc và đã thông báo/chốt chính sách tương thích.

Thay đổi event schema cũng cần quy tắc tương tự. Sự kiện đã lưu hoặc đang nằm trong hàng đợi có thể được đọc bởi consumer ở phiên bản khác; cần kiểm thử cả dữ liệu cũ lẫn mới.

### 4.3. Ví dụ migration cơ sở dữ liệu

Nếu cần thay cột tên khách hàng từ **customer_name** sang **customer_display_name**, không nên xóa cột cũ ngay trước khi tất cả instance chuyển phiên bản. Có thể triển khai theo giai đoạn:

1. Thêm cột mới và cập nhật code để đọc/ghi tương thích trong giai đoạn chuyển tiếp.
2. Chạy backfill, theo dõi dữ liệu và di chuyển hết các instance/consumer.
3. Ngừng dùng cột cũ, rồi xóa ở một đợt migration sau khi xác minh an toàn.

Chiến lược cụ thể phụ thuộc DB, cơ chế ghi, thời gian hỗ trợ hai phiên bản và yêu cầu nhất quán. Nguyên tắc cốt lõi là **một lần phát hành không được buộc tất cả phiên bản khác chuyển đổi đồng thời**.

## 5. Sở hữu theo năng lực nghiệp vụ và trách nhiệm của đội ngũ

Sở hữu ở đây bao gồm **quyền quyết định có giới hạn và trách nhiệm đến cùng** đối với một năng lực. Một đội phụ trách Payment Service cần biết điều gì tạo nên một giao dịch hợp lệ, cách xử lý xác nhận chậm, hoàn tiền, đối soát và sự cố liên quan đến thanh toán.

Một mô hình trách nhiệm tối thiểu thường gồm:

| Hạng mục | Nhóm sở hữu dịch vụ chịu trách nhiệm |
| --- | --- |
| Quy tắc nghiệp vụ | Hiểu yêu cầu, duy trì bất biến và quyết định thay đổi |
| Giao diện công bố | API/event schema, phiên bản, tài liệu, kiểm thử hợp đồng |
| Dữ liệu | Mô hình, migration, chất lượng dữ liệu, quyền truy cập và phục hồi |
| Chất lượng | Unit/integration/contract tests và kiểm thử các luồng quan trọng |
| Phát hành | Pipeline, chiến lược rollout, giám sát, rollback/roll-forward |
| Vận hành | Dashboard, SLO, alert, runbook, xử lý và điều tra sự cố |

**End-to-end ownership** không nhất thiết đòi một đội tự vận hành toàn bộ máy chủ, message broker, Kubernetes hay mạng. Một platform team có thể cung cấp hạ tầng chuẩn, template CI/CD, giám sát và cơ chế bảo mật dùng chung; nhóm sở hữu dịch vụ vẫn chịu trách nhiệm chất lượng và hành vi nghiệp vụ của dịch vụ.

Cũng không nên diễn giải ownership thành “không ai được cộng tác”. Một quy trình liên miền, ví dụ đặt hàng và thanh toán, cần thỏa thuận rõ API, hành vi lỗi, thời gian chờ và trách nhiệm xử lý sự cố giữa các đội. Sở hữu rõ ràng giúp phối hợp có người chịu trách nhiệm, thay vì khiến mọi quyết định phải qua một nhóm trung tâm.

## 6. Cách các dịch vụ phối hợp mà vẫn giữ tự chủ

Microservices cần phối hợp để hoàn thành quy trình lớn hơn từng năng lực. Hai cách thường gặp là **gọi đồng bộ** (HTTP/gRPC) và **trao đổi bất đồng bộ** (event/message). Không có cách nào tự động bảo đảm tự chủ; thiết kế hợp đồng, dữ liệu và lỗi mới quyết định mức độ ghép chặt.

### 6.1. Gọi đồng bộ qua API

Ví dụ, Order Service gửi yêu cầu tới Inventory Service:

~~~http
POST /reservations
Content-Type: application/json
Idempotency-Key: ORD-1001-reserve-v1

{
  "orderId": "ORD-1001",
  "items": [
    { "sku": "SKU-01", "quantity": 2 }
  ]
}
~~~

Inventory Service tự xác định có thể giữ hàng hay không và trả về trạng thái rõ ràng. Order Service **không sửa bảng tồn kho**; Inventory không cần biết database của Order. Giao diện cần mô tả timeout, lỗi tạm thời, idempotency, retry và trường hợp kết quả chưa xác định.

Nhược điểm của lời gọi đồng bộ là độ trễ và tính sẵn sàng của luồng nghiệp vụ có thể phụ thuộc vào các dịch vụ được gọi. Tránh chuỗi gọi quá dài, retry vô hạn và giả định mạng luôn thành công. Dùng timeout, giới hạn retry có backoff, circuit breaker khi phù hợp và bảo vệ nguồn lực.

### 6.2. Giao tiếp qua sự kiện

Sau khi đơn hàng được tạo, Order Service có thể phát sự kiện:

~~~json
{
  "eventId": "evt-9081",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T09:00:00Z",
  "orderId": "ORD-1001",
  "items": [
    { "sku": "SKU-01", "quantity": 2 }
  ]
}
~~~

Inventory Service có thể nhận sự kiện để xử lý giữ hàng; một dịch vụ phân tích có thể tạo báo cáo mà không cần Order Service gọi trực tiếp. Người phát không cần biết mọi consumer, giúp tách nhịp thay đổi. Tuy nhiên, consumer cần chấp nhận **giao hàng lặp, trễ, đảo thứ tự** tùy cơ chế message broker và thiết kế hệ thống.

Các biện pháp thường dùng gồm khóa **eventId** để xử lý idempotent, outbox pattern để gắn sự kiện với thay đổi dữ liệu cục bộ, retry có giới hạn, dead-letter queue, theo dõi độ trễ và cơ chế đối soát. Không nên giả định “publish xong là toàn hệ thống đã cập nhật tức thì”.

### 6.3. Nhất quán dữ liệu qua các ranh giới

Giao dịch ACID cục bộ thường chỉ bảo vệ dữ liệu bên trong một dịch vụ. Một quy trình đi qua Order, Inventory và Payment có thể cần **nhất quán cuối cùng** (*eventual consistency*) và cơ chế xử lý bù (*compensation*). Cách thiết kế phổ biến là Saga; nó có thể được phối hợp bởi một orchestrator hoặc qua các sự kiện choreography, tùy mức phức tạp và khả năng theo dõi.

Chẳng hạn, khi thanh toán thất bại sau khi giữ hàng, quy trình phải yêu cầu Inventory giải phóng phần giữ hàng. Lệnh giải phóng cần idempotent để retry không làm tăng tồn kho hai lần. Order Service hiển thị **PENDING_PAYMENT** trong lúc chờ thay vì cam kết ngay một trạng thái **CONFIRMED** chưa được xác minh.

**Ranh giới dịch vụ làm lộ ra các vấn đề phân tán:** trễ mạng, thông điệp trùng, mất kết nối, thay đổi schema, trạng thái tạm thời không đồng bộ. Đây là chi phí cần chấp nhận và thiết kế nếu lựa chọn microservices.

## 7. Minh họa xuyên suốt: xử lý đơn hàng

Giả sử khách hàng đặt hai sản phẩm và chọn thanh toán điện tử. Một thiết kế chia theo năng lực có thể như sau:

~~~text
Khách hàng / Web App
         |
      API / BFF
         |
     Order Service -----> Inventory Service
      | Order DB           | Inventory DB
      |
      +------------------> Payment Service
      |                     | Payment DB
      |
      +------------------> Shipping Service
                            | Shipping DB
~~~

Các mũi tên thể hiện tương tác qua hợp đồng công bố; thực tế có thể là API, message hoặc kết hợp. BFF/API Gateway là lớp truy cập phù hợp khi cần, không phải điều kiện bắt buộc cho microservices.

Một luồng minh họa:

1. **Order Service** nhận yêu cầu và tạo đơn ở trạng thái **PENDING_STOCK** với mã đơn duy nhất.
2. **Inventory Service** nhận yêu cầu giữ hàng, kiểm tra tồn khả dụng và ghi nhận reservation trong dữ liệu của nó. Kết quả có thể là **RESERVED**, **REJECTED** hoặc đang chờ xác nhận.
3. Khi giữ hàng thành công, quy trình chuyển sang **PENDING_PAYMENT** và tạo yêu cầu thanh toán qua **Payment Service**.
4. **Payment Service** làm việc với bên thanh toán và ghi lại trạng thái giao dịch. Sau khi nhận xác nhận có hiệu lực, nó trả kết quả hoặc phát sự kiện.
5. **Order Service** xác nhận đơn (**CONFIRMED**) khi các điều kiện đã thỏa; **Shipping Service** tiếp nhận yêu cầu giao hàng theo hợp đồng riêng.
6. Nếu thanh toán bị từ chối, quy trình chuyển trạng thái đơn phù hợp và gửi yêu cầu giải phóng reservation. Các bước lỗi phải có cơ chế thử lại, bù và đối soát.

Điểm cần quan sát: Order Service không tự tính tồn kho; Payment Service không quyết định trạng thái giao hàng; Shipping Service không thay đổi bản ghi thanh toán. Mỗi dịch vụ giữ quyền sở hữu quy tắc và dữ liệu, trong khi toàn bộ quy trình hoàn thành bằng hợp đồng giữa các năng lực.

### 7.1. Một thay đổi được phát hành độc lập

Nhóm Payment cần bổ sung phương thức thanh toán mới. Nếu thay đổi nằm sau hợp đồng hiện có và các consumer tương thích, nhóm Payment có thể triển khai phiên bản mới mà không bắt Order, Inventory và Shipping cùng phát hành. Họ vẫn phải kiểm thử hợp đồng, bảo đảm phương thức cũ hoạt động và quan sát lỗi tăng sau rollout.

Ngược lại, nếu cả ba dịch vụ đều đọc trực tiếp cột **payment_method** trong bảng chung và giả định một tập giá trị cố định, việc thêm phương thức mới có thể đòi deploy đồng loạt. Đây là dấu hiệu phụ thuộc bị rò rỉ qua ranh giới dữ liệu, làm suy yếu tính tự chủ.

### 7.2. Một thay đổi đòi phối hợp nhưng không cần phát hành đồng thời

Doanh nghiệp muốn hỗ trợ **thanh toán từng phần**. Đây là thay đổi liên miền ảnh hưởng tới Order và Payment. Hai đội vẫn phải thống nhất khái niệm, trạng thái và hợp đồng, nhưng có thể triển khai theo từng bước: Payment bổ sung khả năng mới có tương thích, Order chuyển dần sang hợp đồng mới, rồi dọn hợp đồng cũ sau khi hoàn tất. **Phối hợp về nghiệp vụ không đồng nghĩa bắt buộc deploy cùng một thời điểm.**

## 8. Những nguyên tắc vận hành giúp ba đặc trưng tồn tại lâu dài

### Hợp đồng và quản trị thay đổi

Công bố API/event schema rõ ràng, có kiểm thử tương thích giữa producer và consumer, có chính sách deprecation và thời gian chuyển đổi. Tránh dùng một model chia sẻ khắp hệ thống như giao diện ngầm giữa các dịch vụ. Khi cần thư viện chung, ưu tiên các tiện ích kỹ thuật ít thay đổi; mô hình nghiệp vụ thường nên thuộc về từng bounded context.

### Dữ liệu, bảo mật và quyền truy cập

Chỉ chủ sở hữu được phép thay đổi dữ liệu nguồn sự thật của mình. Dịch vụ khác truy cập qua API, sự kiện hoặc bản chiếu được phép. Áp dụng xác thực, phân quyền theo vai trò dịch vụ, mã hóa, quản lý secret và nguyên tắc đặc quyền tối thiểu. Ranh giới dữ liệu đồng thời là ranh giới quyền hạn và trách nhiệm.

### Tự động hóa phát hành và quan sát

Mỗi dịch vụ nên có artifact phiên bản hóa, kiểm thử tự động, quy trình release riêng, health/readiness probe, dashboard, log và tracing có khả năng liên kết các bước trong một yêu cầu. Với thay đổi rủi ro cao, cân nhắc canary/rolling rollout, feature flag và phương án rollback hoặc roll-forward. Một pipeline “xanh” chưa đủ nếu không theo dõi hành vi sau phát hành.

### Đội nền tảng và tiêu chuẩn chung

Tận dụng nền tảng chung để giảm chi phí nhận thức của từng nhóm: logging, observability, service discovery, configuration, CI/CD templates, secret management và policy bảo mật. Các tiêu chuẩn này phải đủ mạnh để hệ thống nhất quán mà không biến mọi thay đổi nhỏ thành yêu cầu xin phép tập trung.

## 9. Đánh giá mức độ tự chủ bằng bằng chứng

Thay vì chỉ đếm số dịch vụ, hãy xem các câu hỏi có thể kiểm chứng:

| Câu hỏi | Bằng chứng cần tìm |
| --- | --- |
| Một sửa lỗi của Order có cần phát hành Payment không? | Lịch sử release, dependency và hợp đồng tương thích |
| Ai quyết định sửa quy tắc giữ hàng? | Owner rõ ràng, tài liệu bất biến và quyền thay đổi |
| Service nào là nguồn sự thật của trạng thái thanh toán? | Sơ đồ ownership dữ liệu, quyền DB và luồng đồng bộ |
| Đổi schema có buộc dừng cả hệ thống? | Kế hoạch migration, kiểm thử hỗ trợ phiên bản cũ/mới |
| Một dịch vụ lỗi có lan thành sự cố diện rộng? | Timeout/retry, dashboard dependency, kiến trúc chịu lỗi |
| Khi sự cố xảy ra, ai nhận cảnh báo và xử lý? | SLO, on-call, runbook, trace và lịch sử incident |

Các chỉ báo phụ trợ có thể gồm **deployment frequency**, **lead time for changes**, **change failure rate**, **time to restore service**, số lần cần phát hành đồng thời và tỉ lệ thay đổi phải phối hợp nhiều repository. Không dùng một chỉ số đơn lẻ để kết luận kiến trúc tốt hay xấu; cần đánh giá cùng bối cảnh đội ngũ và độ phức tạp nghiệp vụ.

## 10. Hiểu lầm và phản ví dụ thường gặp

**“Mỗi microservice phải có một ngôn ngữ và database engine khác.”** Không đúng. Tự chủ là quyền thay đổi trong ranh giới phù hợp; thống nhất stack thường giúp giảm chi phí vận hành. Sự khác biệt công nghệ chỉ có ích khi có lý do đáng kể.

**“Có container riêng tức là triển khai độc lập.”** Container chỉ hỗ trợ đóng gói. Nếu tất cả container phải cùng đổi phiên bản API/schema, hệ thống vẫn cần release đồng bộ.

**“Dịch vụ chỉ gọi qua API thì đã lỏng ghép.”** API có thể ghép chặt nếu hợp đồng quá chi tiết, phụ thuộc thứ tự gọi, buộc release đồng thời, hoặc chuỗi gọi đồng bộ dài. Chất lượng hợp đồng và hành vi khi lỗi quan trọng hơn giao thức.

**“Tách database chắc chắn giải quyết mọi phụ thuộc.”** Cô lập DB chặn phụ thuộc truy cập trực tiếp, nhưng phụ thuộc vẫn có thể đi qua event schema không tương thích, shared library hoặc luồng nghiệp vụ quá chặt. Cần thiết kế nhất quán tổng thể.

**“Đội sở hữu dịch vụ có thể bỏ qua tiêu chuẩn chung.”** Quyền sở hữu bao gồm trách nhiệm tuân thủ các hợp đồng và yêu cầu hệ thống: bảo mật, khả năng quan sát, quản trị lỗi và bảo vệ dữ liệu.

**“Nhiều dịch vụ hơn luôn tốt hơn.”** Ranh giới chia quá nhỏ làm tăng chi phí phân tán, độ trễ và phối hợp. Nếu một tính năng thường buộc sửa đồng loạt nhiều dịch vụ, cần xem lại ranh giới; một modular monolith có thể là bước đi phù hợp hơn khi tổ chức và nền tảng chưa cần nhiều release độc lập.

## 11. Cách áp dụng khi thiết kế một hệ thống mới

Một trình tự suy nghĩ thực tế:

1. Xác định **năng lực nghiệp vụ** từ quy trình, thuật ngữ và kết quả đầu ra; trao đổi với người hiểu nghiệp vụ.
2. Nhóm các quy tắc và dữ liệu cần nhất quán cục bộ; phác thảo **bounded context** và người sở hữu từng phạm vi.
3. Vẽ luồng giữa các context, chỉ ra thông tin trao đổi qua **API/event** và tình huống lỗi cần xử lý.
4. Chọn ranh giới dịch vụ dựa trên **nhu cầu thay đổi, mức độc lập cần thiết và chi phí vận hành**; không bắt buộc triển khai mỗi context thành một process.
5. Quy định rõ dữ liệu nguồn sự thật, hợp đồng có phiên bản, cách migration tương thích và quyền truy cập.
6. Chuẩn bị pipeline, kiểm thử hợp đồng, đo lường, tracing và trách nhiệm trực vận hành trước khi tăng số dịch vụ.
7. Kiểm chứng bằng một thay đổi thật: thử phát hành một dịch vụ độc lập trong khi consumer giữ phiên bản cũ và đánh giá tác động.

### Bài tập tư duy

Giả sử ứng dụng bán vé có **Booking**, **Payment** và **Seat Inventory**. Hiện tại, cả ba truy cập chung bảng **booking** và một lần thêm trạng thái **REFUNDED** phải triển khai cả ba ứng dụng cùng lúc.

Hãy phác họa ranh giới sở hữu: ai nắm giữ ghế, ai quản lý booking, ai nắm giao dịch hoàn tiền; dữ liệu nào phải được di chuyển khỏi DB chung; hợp đồng API hoặc event nào thay thế truy cập bảng trực tiếp; làm sao thêm **REFUNDED** qua hai giai đoạn mà consumer cũ vẫn chạy. Cuối cùng, mô tả cách thử lại và xử lý bù nếu hoàn tiền thành công nhưng thông báo cập nhật booking bị trễ.

Mục tiêu của bài tập là thấy rằng **tự chủ phải được tạo ra từ ranh giới nghiệp vụ, dữ liệu và hợp đồng**, còn khả năng triển khai độc lập là bằng chứng vận hành của thiết kế đó.

## 12. Ghi nhớ

- **Autonomy:** từng dịch vụ sở hữu quyết định, quy tắc và dữ liệu trong ranh giới của mình; phối hợp qua hợp đồng rõ.
- **Independent deployment:** thay đổi tương thích có thể lên production theo nhịp riêng, với pipeline, migration và quan sát hỗ trợ.
- **Business-capability ownership:** mỗi dịch vụ/đội ngũ gắn với một kết quả nghiệp vụ, có trách nhiệm xuyên suốt từ thay đổi tới vận hành.
- **Đánh đổi:** tăng quyền thay đổi độc lập đồng thời làm phát sinh chi phí về mạng, dữ liệu phân tán, hợp đồng, giám sát và vận hành. Chỉ nên tách khi lợi ích tự chủ tương xứng với chi phí này.
