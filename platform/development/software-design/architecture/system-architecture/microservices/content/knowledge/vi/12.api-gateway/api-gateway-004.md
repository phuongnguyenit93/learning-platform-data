# Tổng hợp dữ liệu và giới hạn xử lý nghiệp vụ tại gateway

## 1. Vấn đề: một màn hình cần dữ liệu từ nhiều microservice

Trong hệ thống Microservices, mỗi dịch vụ sở hữu một phần miền nghiệp vụ. Order Service quản lý đơn hàng, Payment Service quản lý giao dịch thanh toán, Inventory Service quản lý tồn kho, Shipping Service quản lý giao vận. Tuy nhiên một màn hình chi tiết đơn hàng lại thường cần dữ liệu từ nhiều dịch vụ cùng lúc.

Nếu ứng dụng mobile gọi trực tiếp từng service, nó phải biết địa chỉ nội bộ, cách xác thực, version của nhiều hợp đồng, thứ tự gọi, timeout và cách xử lý khi một nguồn dữ liệu không sẵn sàng. Số lượt đi về qua mạng tăng, logic tích hợp bị nhân bản giữa mobile, web và đối tác. Điều này làm client phụ thuộc quá chặt vào cấu trúc backend.

**API Gateway** đóng vai trò điểm vào chung. Nó có thể định tuyến, áp dụng chính sách ở biên và trong một số trường hợp **tổng hợp dữ liệu (API aggregation/response composition)** để client gọi một endpoint thay vì nhiều endpoint.

Nhưng gateway có một ranh giới rất quan trọng:

> Gateway có thể tổng hợp dữ liệu phục vụ client và thực thi chính sách giao tiếp; **quyết định nghiệp vụ, bất biến và quyền sở hữu dữ liệu phải nằm ở dịch vụ nghiệp vụ có trách nhiệm**.

Một gateway nhận Payment=CAPTURED và Inventory=RESERVED không được tự sửa Order thành CONFIRMED chỉ vì các trường trông có vẻ đầy đủ. Order Service hoặc Checkout Application Service phải quyết định khi nào đơn được xác nhận, vì nó hiểu chính sách và trạng thái nghiệp vụ.

### 1.1. Mục tiêu học tập

Sau bài này, người đọc có thể:

1. Phân biệt **API Gateway**, **BFF**, **API Composition Service** và **business orchestrator**.
2. Thiết kế một endpoint tổng hợp có hợp đồng rõ về dữ liệu bắt buộc, tùy chọn, lỗi một phần và độ mới.
3. Giảm fan-out, N+1 calls và latency bằng song song hóa, batching, cache hoặc read model.
4. Xác định logic nào có thể xử lý ở gateway và logic nào phải trả về bounded context owner.
5. Thiết kế timeout, retry, circuit breaker, authorization và quan sát vận hành cho endpoint tổng hợp.
6. Nhận diện trường hợp nên chuyển composition sang BFF/service chuyên trách hoặc CQRS projection.

## 2. Các lớp trách nhiệm liên quan

| Thành phần | Trách nhiệm chủ đạo | Không nên tự làm |
| --- | --- | --- |
| API Gateway | Routing, TLS, authentication ở biên, rate limit, quota, tracing, policy kỹ thuật | Quyết định thu tiền, trừ tồn, điều kiện hủy đơn |
| Backend for Frontend (BFF) | API và representation riêng cho mobile/web/partner | Trở thành source of truth của Payment/Order |
| API Composition Service | Đọc nhiều nguồn, ghép DTO, xử lý fallback trình bày và độ mới | Thực thi command nghiệp vụ có bất biến mạnh |
| Application Service | Chạy use case, bảo vệ workflow và gọi domain services | Chỉ đóng vai trò proxy vô nghĩa nếu domain không cần |
| Domain Service / Aggregate | Quy tắc nghiệp vụ, trạng thái, bất biến và quyền quyết định | Phụ thuộc trực tiếp vào schema hiển thị của một client |
| Workflow/Saga Orchestrator | Điều phối các bước ghi xuyên miền, trạng thái quy trình và compensation | Đặt state machine giao dịch bên trong gateway mỏng |
| Read Model / Projection | Biểu diễn dẫn xuất tối ưu cho đọc, được cập nhật từ nguồn gốc | Tự nhận là nguồn sự thật của những miền khác |

Những tên gọi này mô tả **vai trò kiến trúc**, không bắt buộc số deployable. Một BFF và composition service có thể nằm trong cùng một ứng dụng. Một modular monolith vẫn có thể phân tách các lớp trách nhiệm như vậy.

### 2.1. API Gateway chuẩn

Gateway thông thường giải quyết cross-cutting concerns: route theo path/header, kiểm tra token ở biên, CORS, quota, rate limiting, chuẩn hóa trace headers, ghi metrics và trong vài trường hợp biến đổi payload đơn giản.

Cấu hình routing có thể có dạng:

~~~text
GET /api/orders/{id}        -> Order Service
GET /api/catalog/products   -> Catalog Service
GET /api/order-details/{id} -> Order Details BFF
~~~

Một gateway mỏng dễ phát hành và vận hành. Nếu mọi nhóm đưa hàng trăm đoạn rule tùy biến vào cùng một gateway, thành phần biên có thể trở thành **distributed monolith bottleneck** dù mỗi domain service ở sau vẫn triển khai riêng.

### 2.2. BFF: tối ưu theo client

Web quản trị có thể cần thông tin hoàn tiền, audit và thao tác quản lý; mobile chỉ cần trạng thái đơn và vận đơn; partner cần một representation chuẩn hóa theo hợp đồng B2B. BFF cho phép mỗi nhóm client có API phù hợp mà không bắt domain service biết mọi nhu cầu trình bày.

~~~text
                 Client requests
                        |
                        v
                  API Gateway
                        |
            +-----------+-----------+
            |                       |
            v                       v
        Mobile BFF               Admin BFF
            |                       |
            +-------+-------+-------+
                    |       |
                    v       v
                   Order  Payment ...
~~~

BFF không có nghĩa mỗi màn hình phải có một service. Quyết định theo khối lượng composition, nhịp thay đổi và đội sở hữu.

### 2.3. Aggregator: tổng hợp một read use case

**API Composition Pattern** truy vấn các nguồn cần thiết và tạo một composite response. Nó đặc biệt phù hợp với **truy vấn**, ví dụ xem chi tiết đơn hàng, trang hồ sơ khách hoặc dashboard nhiều năng lực.

**Business orchestration** khác: nó ra lệnh giữ hàng, thanh toán, xác nhận, hoàn tiền, hủy đơn, và xử lý kết quả từng bước. Quy trình đó cần trạng thái bền vững, retry, idempotency, compensation và owner nghiệp vụ. Không đặt nó trong gateway chỉ vì có nhiều HTTP calls.

## 3. Đặt ranh giới giữa tổng hợp dữ liệu và xử lý nghiệp vụ

### 3.1. Những gì thường phù hợp ở gateway/BFF

- Định tuyến tới published APIs và xác định version contract.
- Truyền identity/trace context hợp lệ.
- Gọi nhiều API đọc rồi ghép representation.
- Chọn một số field cho client, đổi tên field presentation.
- Chuyển định dạng ngày giờ theo locale **nếu dữ liệu có timezone rõ**.
- Batch lookup, giới hạn page size, giảm số round trip.
- Gán metadata về component thiếu, độ mới, thời điểm tạo response.
- Thực hiện cache phù hợp quyền truy cập và yêu cầu độ mới.
- Timeout, retry an toàn cho thao tác đọc, circuit breaker và bulkhead.
- Chuẩn hóa lỗi giao tiếp, bảo vệ quota/rate limit.
- Chuyển đổi hợp đồng cũ sang hợp đồng mới nếu không làm sai nghĩa nghiệp vụ.

### 3.2. Những gì phải thuộc domain owner

- Tính giá chốt, chính sách chiết khấu, phí và thuế.
- Quyết định đơn hàng có thể hủy, xác nhận hoặc hoàn tất.
- Tạo reservation và bảo đảm không giữ tồn vượt khả năng.
- Xác minh giao dịch thực sự thu tiền hay chỉ mới được ủy quyền.
- Kiểm tra giới hạn hoàn tiền và phòng chống lặp.
- Chuyển trạng thái với audit và event nghiệp vụ.
- Phê duyệt hay từ chối command theo quyền nghiệp vụ cụ thể.
- Điều phối một workflow phân tán có compensation.
- Ghi nguồn sự thật vào database của bounded context.

Một tiêu chí đơn giản: **nếu thay giao diện mobile bằng một batch job thì quy tắc này có vẫn phải được áp dụng không?** Nếu có, nó thường không phải presentation logic của BFF.

### 3.3. Ví dụ ranh giới đúng và sai

Phản mẫu:

~~~text
Gateway GET /orders/{id}
Gateway GET /payments?orderId={id}
Gateway tự quyết:
  if payment.status == CAPTURED:
      PATCH /orders/{id} {"status":"CONFIRMED"}
~~~

Vấn đề: Payment=CAPTURED có thể chưa đủ để Order confirmed nếu còn điều kiện giữ hàng, kiểm tra gian lận, chính sách thanh toán hoặc hạn chót. Gateway đang định nghĩa lại state machine của Order.

Thiết kế tốt hơn:

~~~text
Gateway gửi request đến Order Application
Order Application thực hiện use case
Order/Checkout owner đánh giá các bất biến
Order công bố trạng thái cuối qua published contract
Gateway chỉ trả representation của trạng thái đã công bố
~~~

Tương tự, để hiển thị nút hủy đơn, gateway nên tiêu thụ capability như **canCancel** do Order owner công bố, không tự so sánh vài enum từ nhiều service rồi ra quyết định.

### 3.4. Chính sách có vẻ “nghiệp vụ” ở biên

Một gateway có thể áp rate limit khác nhau cho các gói dịch vụ nếu quota được hệ thống quản lý subscription công bố. Ở đây gateway **thực thi policy được giao**; nó không trở thành nơi tự định nghĩa giá gói, thời hạn hợp đồng hay điều kiện thanh toán. Cần ghi rõ policy owner và nguồn cấu hình có thẩm quyền.

## 4. Thiết kế composite resource theo nhu cầu của client

Giả sử mobile cần:

- ID, dòng hàng, tổng tiền và trạng thái Order.
- Payment summary.
- Shipment tracking.
- Tên và ảnh sản phẩm hiện tại.

Một endpoint có thể là:

~~~http
GET /api/order-details/ORD-1001 HTTP/1.1
Authorization: Bearer <token>
Accept: application/json
~~~

Response minh họa:

~~~json
{
  "orderId": "ORD-1001",
  "orderStatus": "CONFIRMED",
  "total": {
    "amount": "350000",
    "currency": "VND"
  },
  "items": [
    {
      "sku": "SKU-01",
      "name": "Sổ tay",
      "quantity": 2
    }
  ],
  "payment": {
    "status": "CAPTURED",
    "updatedAt": "2026-11-11T08:30:00Z"
  },
  "shipment": {
    "status": "IN_TRANSIT",
    "trackingCode": "TRK-001"
  },
  "completeness": "COMPLETE"
}
~~~

Đây là **read view tổng hợp**. Không có một transaction ACID chung tự nhiên cho JSON được ghép từ Order, Payment, Shipping và Catalog. Gateway phải xác định trường nào lấy từ nguồn nào.

### 4.1. Bảng ownership

| Trường composite | Nguồn có thẩm quyền | Ghi chú |
| --- | --- | --- |
| orderId, orderStatus | Order | Không tự tạo status từ Payment |
| order item, quantity lúc đặt | Order | Snapshot đơn có thể khác Catalog hiện tại |
| total lúc đặt | Order/Pricing theo hợp đồng đã chốt | Không tự cộng giá hiện tại của Catalog |
| payment.status | Payment | Đừng map AUTHORIZED thành CAPTURED |
| shipment.trackingCode | Shipping | Có thể chưa xuất hiện nếu chưa giao |
| product.name hiện tại | Catalog | Có thể khác tên snapshot lúc đặt |
| canCancel | Order application/domain | Quyết định nghiệp vụ do owner cung cấp |

Một API tổng hợp không nhất thiết trả raw DTO của downstream. Nó nên công bố **contract của màn hình** và giữ khả năng thay đổi schema nội bộ độc lập.

### 4.2. Nên tách field hiển thị và sự thật nghiệp vụ

Một tên sản phẩm ở Catalog có thể được đổi sau khi khách mua. Nếu màn hình là “hóa đơn chốt lúc mua”, nó cần tên sản phẩm đã ghi trên Order hoặc Billing, không phải tên Catalog hiện tại. Nếu là “mua lại”, tên hiện tại có thể hữu ích.

Cùng một field **name** nhưng mục đích nghiệp vụ khác nhau. Gateway/BFF chỉ được map sau khi hiểu **ý nghĩa và thời điểm** của dữ liệu.

## 5. Quy trình fan-out và tối ưu độ trễ

**Fan-out** là việc một request ngoài tạo ra nhiều request nội bộ. Nó giảm gánh nặng ở client nhưng chuyển chi phí sang gateway và downstream.

### 5.1. Gọi tuần tự so với song song

Ví dụ 3 lời gọi có độ trễ riêng 80 ms, 100 ms và 120 ms:

~~~text
Tuần tự:
  Order (80) -> Payment (100) -> Shipping (120)
  Tổng downstream xấp xỉ 300 ms

Song song nếu độc lập:
  +-- Order (80) ---+
  +-- Payment (100)-+--> compose
  +-- Shipping (120)+
  Tổng downstream lý tưởng xấp xỉ 120 ms
~~~

Đây chỉ là phép tính minh họa, chưa có network overhead, queuing, JSON parsing và tải thực. Một số lời gọi **cần tuần tự**: chẳng hạn xác minh người dùng có quyền xem Order và lấy paymentId trước khi truy vấn Payment.

### 5.2. Càng nhiều dependency bắt buộc, càng dễ lỗi toàn bộ

Nếu response cần tất cả downstream thành công, thất bại ở bất kỳ nguồn nào có thể làm cả response thất bại. Với ba dependency độc lập và mỗi dependency đạt tỷ lệ thành công 99,9% trong một khoảng quan sát, xác suất lý tưởng tất cả thành công khoảng:

~~~text
0,999 × 0,999 × 0,999 ≈ 99,7%
~~~

Giả định độc lập chỉ để minh họa; lỗi thực có thể tương quan qua mạng, hạ tầng hoặc database chung. Không nên coi phép tính này là SLO chuẩn cho hệ thống. Ý chính: **giảm dependency bắt buộc và thiết kế partial failure hợp lệ** sẽ cải thiện khả năng phục vụ view.

### 5.3. N+1 calls

Một Order có 50 item. Nếu composer gọi Catalog 50 lần để lấy thông tin sản phẩm, tải tăng tuyến tính theo số item. Hướng cải thiện:

- Gọi batch API **GET /products?ids=...** hoặc một published batch lookup.
- Lấy snapshot đã lưu trong Order nếu đúng mục tiêu hiển thị.
- Cache product summary khi không nhạy cảm và độ mới cho phép.
- Xây projection nếu use case đọc thường xuyên với nhiều item.

Batch cũng cần **max size, validation, quyền và xử lý item thiếu**, không gửi danh sách không giới hạn.

### 5.4. Hạn mức fan-out và concurrency

Một external request tạo 6 downstream requests; 1.000 request/s có thể tạo tới 6.000 calls/s ở phía trong khi cache không có hiệu lực. Cần đo **calls per external request**, giới hạn concurrency theo route/tenant, connection pool, queue, timeout và bảo vệ downstream.

Reactive/async code giúp không giữ thread chờ theo một số mô hình nhưng **không loại bỏ chi phí CPU, network, memory, socket hoặc kết nối tới DB**.

## 6. Deadline, timeout, retry và cách ly lỗi

### 6.1. Đặt ngân sách thời gian tổng

Giả sử endpoint có deadline từ client là 800 ms. Composer có thể dự trù:

~~~text
Xác thực/routing:       50 ms
Truy vấn + ghép dữ liệu: 650 ms
Serialization/return:  100 ms
~~~

Các con số chỉ là ví dụ. Mỗi lời gọi downstream phải tuân thủ **thời gian còn lại**. Nếu đã mất 600 ms ở một dependency, không nên bắt đầu hai lần retry mỗi lần 500 ms rồi vẫn kỳ vọng đáp ứng deadline.

### 6.2. Retry có điều kiện

**GET** thường an toàn để thử lại về ngữ nghĩa HTTP, nhưng vẫn phải giới hạn số lần, thời gian, backoff và jitter. Với **POST/command có side effect**, cần idempotency key và cách tra cứu trạng thái nếu timeout để không tạo đơn/thu tiền nhiều lần.

Không retry mù khi:

- Caller không có quyền (403).
- Tài nguyên thực sự không tồn tại (404 theo hợp đồng).
- Dữ liệu nghiệp vụ bị từ chối (409/422 theo định nghĩa).
- Client đã cancel và không còn lý do giữ công việc đọc.
- Deadline tổng đã hết.

### 6.3. Tránh retry amplification

Nếu gateway retry hai lần, BFF retry thêm ba lần và downstream client retry hai lần, một request có thể gây ra lượng calls lớn hơn nhiều so với dự tính. Hãy xác định tầng nào chịu trách nhiệm retry và cung cấp retry budget. Theo dõi retry count, timeout, 429, 503 và số request đang chờ.

### 6.4. Circuit breaker và bulkhead

**Circuit breaker** giảm lời gọi vào dependency lỗi liên tục; **bulkhead** giữ một dependency chậm không chiếm toàn bộ tài nguyên. **Backpressure** kiểm soát lưu lượng khi downstream xử lý chậm.

Đây là các biện pháp vận hành, **không phải lý do để trả một trạng thái nghiệp vụ giả**. Nếu Payment lỗi, fallback “PAID” là sai; fallback “UNAVAILABLE” hoặc lỗi có cấu trúc có thể phù hợp hơn.

## 7. Lỗi một phần: hợp đồng phải nói rõ

Một response tổng hợp có thể thiếu một phần do downstream không sẵn sàng. Điều này chỉ hợp lệ khi người dùng và client hiểu đúng mức độ hoàn chỉnh.

### 7.1. Required và optional component

| Nguồn dữ liệu | Trường hợp sử dụng | Khi lỗi |
| --- | --- | --- |
| Order | Chi tiết Order | Thường bắt buộc; nếu không có, response lỗi |
| Payment | Xác nhận đã thu tiền | Bắt buộc khi ra quyết định tài chính |
| Shipping | Trang tổng quan đơn | Có thể tùy chọn; hiển thị chưa tải được |
| Catalog image | Màn hình đơn hàng | Có thể dùng placeholder |
| Recommendation | Sản phẩm gợi ý | Có thể bỏ qua mà không chặn Order |

Mức bắt buộc phụ thuộc use case. Trong màn hình đối soát, Shipping proof có thể là bắt buộc; trong một trang tổng quan đơn, nó có thể tùy chọn.

### 7.2. Response partial có cấu trúc

Khi Shipping timeout nhưng Order và Payment sẵn sàng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "orderId": "ORD-1001",
  "orderStatus": "CONFIRMED",
  "payment": {
    "status": "CAPTURED"
  },
  "shipment": null,
  "completeness": "PARTIAL",
  "unavailableComponents": [
    {
      "component": "shipment",
      "reason": "TEMPORARILY_UNAVAILABLE"
    }
  ]
}
~~~

**200** ở đây chỉ nói endpoint đã trả thành công một **representation partial theo contract**. Không được dùng nếu client luôn kỳ vọng dữ liệu đầy đủ; khi ấy cần phản hồi lỗi tương ứng.

### 7.3. Null không phải lúc nào cũng có nghĩa “không có”

Cần phân biệt:

- **NOT_CREATED:** chưa tồn tại shipment vì đơn chưa giao.
- **NOT_FOUND:** không có resource được xác nhận theo hợp đồng.
- **UNAVAILABLE:** truy vấn lỗi, chưa biết hiện trạng.
- **FORBIDDEN:** caller không có quyền xem.
- **STALE:** hiện có bản đọc nhưng quá cũ theo yêu cầu.

Nếu cùng trả **shipment: null**, client có thể hiển thị “chưa giao” khi thực ra service đang lỗi. Thiết kế contract nên có trường lý do/metadata hoặc cấu trúc trạng thái rõ.

### 7.4. Status code cho lỗi bắt buộc

- **404 Not Found:** Order thật sự không có theo nguồn có thẩm quyền và chính sách tiết lộ thông tin.
- **403 Forbidden:** không đủ quyền; trong một số tình huống bảo mật, 404 có thể được dùng để không tiết lộ sự tồn tại.
- **502 Bad Gateway:** upstream trả phản hồi không hợp lệ.
- **503 Service Unavailable:** chức năng tạm không khả dụng.
- **504 Gateway Timeout:** gateway không nhận phản hồi upstream kịp.

Không trả **404** chỉ vì Order Service timeout. “Không tìm thấy” khác “không xác minh được”.

### 7.5. Không lạm dụng mã 207

**207 Multi-Status** là một mã liên quan WebDAV; nó không phải quy tắc chung buộc REST aggregation dùng cho phản hồi partial. Thường tốt hơn là công bố contract riêng với completeness/parts, cùng mã HTTP phản ánh kết quả request tổng hợp như đã định nghĩa.

## 8. Nhất quán, độ mới và lệch pha giữa các miền

Composite response đọc từ nhiều service không mặc nhiên tạo một snapshot nguyên tử cùng thời điểm.

~~~text
10:00:00 Order: PENDING_PAYMENT
10:00:01 Payment: CAPTURED
10:00:02 Order nhận event và chuyển CONFIRMED

Gateway tại 10:00:01.5 có thể đọc:
  Order.status = PENDING_PAYMENT
  Payment.status = CAPTURED
~~~

Không nhất thiết có lỗi: hai service có thể dùng eventual consistency. Gateway **không được tự ghi Order=CONFIRMED** để che độ trễ cập nhật.

### 8.1. Mức độ mới theo use case

- **Catalog hiển thị:** có thể chấp nhận chậm một khoảng đã công bố.
- **Theo dõi shipment:** phụ thuộc chu kỳ cập nhật của đối tác; cần timestamp.
- **Trang chi tiết đơn:** có thể chấp nhận trạng thái trung gian rõ.
- **Quyết định xuất hàng:** cần các điều kiện do domain owner bảo vệ, không dựa vào JSON ghép có thể cũ.
- **Đối soát tài chính:** cần nguồn dữ liệu xác thực, tính đúng đắn và mốc đối soát.

### 8.2. Metadata “asOf”

Có thể dùng:

~~~json
{
  "order": {
    "status": "CONFIRMED",
    "asOf": "2026-11-11T10:00:02Z"
  },
  "payment": {
    "status": "CAPTURED",
    "asOf": "2026-11-11T10:00:01Z"
  },
  "generatedAt": "2026-11-11T10:00:03Z"
}
~~~

Nhưng **asOf** phải có nghĩa rõ: thời điểm phát event, ghi DB, cập nhật projection hay trả response. Không tự gắn timestamp hiện tại lên bản ghi cũ rồi coi đó là dữ liệu mới.

### 8.3. Tính toán trên dữ liệu nhiều nguồn

Nếu cần tổng hợp số tiền để trình bày, nên xác định **source of truth cho phép tính**. Không tự cộng thanh toán và giảm giá thành “số tiền phải thu” ở gateway nếu domain đã có một giá trị chốt riêng. Các phép diễn giải domain cần thuộc owner, kể cả khi mapper có khả năng tính toán.

## 9. Cache và materialized view

### 9.1. Cache phù hợp với quyền và độ mới

Một gateway có thể cache dữ liệu catalog công khai với TTL. Nhưng Order/Payment là dữ liệu nhạy cảm, phụ thuộc identity/tenant và có thể thay đổi liên tục.

Các chính sách thường gặp:

- **Cache-Control: public:** chỉ khi representation an toàn để shared cache.
- **private:** chỉ phù hợp cache theo client.
- **no-store:** yêu cầu không lưu dữ liệu nhạy cảm.
- **no-cache:** có thể lưu nhưng cần xác minh lại trước khi dùng.
- **ETag / If-None-Match:** kiểm tra representation đã đổi chưa.
- **Vary:** phân biệt response dựa trên header liên quan.

Không đặt cache key chỉ là **orderId** nếu các user có quyền thấy những field khác nhau. Cache phải xét tenant, identity, scope, locale, API version và các yếu tố ảnh hưởng representation, hoặc tránh cache nếu không bảo đảm an toàn.

### 9.2. Invalidating composite cache

Order, Payment và Shipping có thể thay đổi độc lập. Chiến lược invalidate có thể gồm TTL, event invalidation, refresh khi đọc hoặc phân tách các phần có độ mới khác nhau. Event invalidation cũng có thể đến trễ; cần biết mức stale tối đa chấp nhận.

### 9.3. Materialized read model / CQRS

Nếu hàng triệu request cùng cần Order Details, runtime fan-out vào bốn service mỗi lần có thể không phù hợp. Có thể xây projection từ event:

~~~text
OrderUpdated ------+
                   |
PaymentCaptured ---+--> OrderDetails Projector --> Read DB
                   |                              |
ShipmentUpdated ---+                              v
                                        GET /order-details/{id}
~~~

Projection là **mô hình đọc dẫn xuất**, không phải nguồn sự thật của Order/Payment/Shipping. Nó cần idempotency, xử lý event trùng/sai thứ tự, replay, schema migration, metrics lag, security và reconciliation.

| Tiêu chí | Runtime aggregation | Materialized view |
| --- | --- | --- |
| Độ mới | Gần nguồn lúc gọi nhưng vẫn lệch pha | Phụ thuộc độ trễ projection |
| Phụ thuộc runtime | Phụ thuộc nhiều downstream | Thấp hơn trong mỗi request |
| Chi phí mỗi request | Nhiều network calls | Ít calls, đọc từ model |
| Complexity ban đầu | Thường đơn giản hơn | Cần event pipeline/storage |
| Tải lớn | Có thể tốn chi phí fan-out | Thường phù hợp đọc nhiều |
| Khôi phục dữ liệu | Dựa vào downstream | Cần replay/snapshot/đối soát |

Không chọn CQRS chỉ vì hệ thống được gọi là microservices; cần dựa trên lưu lượng, latency, độ mới và khả năng vận hành.

## 10. Bảo mật xuyên các service

### 10.1. Authentication tại biên không đủ

Gateway có thể xác thực token và kiểm tra scope tổng quát, nhưng **Order Service phải xác minh caller được xem đúng đơn**, Payment Service kiểm soát quyền xem giao dịch và Shipping Service kiểm soát dữ liệu nhạy cảm của vận chuyển.

Một trường hợp nguy hiểm: gateway có credential toàn quyền đọc mọi đơn rồi trả thông tin theo orderId mà không xác minh resource ownership. Đây là nguy cơ **IDOR/BOLA và confused deputy**.

### 10.2. Identity và quyền delegated

Khi gateway gọi downstream, có thể truyền principal/delegation context hoặc dùng service credential có phạm vi rõ. Các service phải xác minh nguồn tin cậy của context, không tin header người dùng tự đặt.

Không giả định “nằm trong private network” nghĩa là được đọc mọi dữ liệu. Dùng service identity, mTLS hoặc token theo kiến trúc được lựa chọn.

### 10.3. Data minimization

Một composite response không nên vô tình chứa:

- Token thanh toán hoặc thông tin thẻ.
- Thông tin liên hệ nhạy cảm không cần cho use case.
- Trường audit nội bộ hoặc dữ liệu risk scoring.
- Thông tin khách khác tenant.
- Stack trace, connection string, credential ở phần lỗi.

Ẩn các field không cần thiết và chỉ ghi log các định danh/metadata vận hành đã được cho phép. Không log toàn bộ payload nhạy cảm để tiện debug.

### 10.4. Rate limit và request amplification

Một request bên ngoài có thể sinh nhiều calls bên trong. Cần hạn mức không chỉ theo số request client, mà còn theo chi phí route, số phần tử được fetch, query depth, concurrency và mức bảo vệ của downstream. Các service đích vẫn cần tự giới hạn tài nguyên.

## 11. Data mapping có trách nhiệm

Aggregator được đổi representation, nhưng không nên thay đổi sự thật nghiệp vụ.

**Mapping thường phù hợp:**

- Đổi **tracking_number** thành **trackingCode**.
- Chuyển timestamp có timezone hợp lệ sang định dạng client cần.
- Gộp product summaries vào Order items theo SKU/ID.
- Trả link/public URL phù hợp thay vì internal storage path.
- Bổ sung completeness, source timestamp hoặc dữ liệu fallback được công bố.
- Chọn một tập field và đổi cấu trúc JSON cho client.

**Mapping nguy hiểm:**

- Payment.AUTHORIZED → paid=true khi chỉ CAPTURED mới là thu tiền.
- Inventory.RESERVED → shipped=true.
- Shipment.DELIVERED → Order.CLOSED khi còn điều kiện kiểm nhận.
- Payment timeout → UNPAID.
- Giá Catalog hiện tại → giá Order tại thời điểm đặt.

Nếu cần một kết luận như **canRefund**, **canCancel**, **paymentSettled**, service owner nên công bố query/capability rõ ràng. Gateway không nên tái triển khai domain policy của nhiều nhóm.

## 12. Ví dụ triển khai Java/Spring theo lớp

Có thể dùng Spring MVC với async HTTP client, Spring WebFlux hoặc framework khác. Mã dưới đây mô tả nguyên tắc; chi tiết import, timeout và security phụ thuộc phiên bản thư viện.

### 12.1. DTO tổng hợp riêng

~~~java
record Money(String amount, String currency) {}
record PaymentSummary(String status, Instant updatedAt) {}
record ShipmentSummary(String status, String trackingCode) {}

record OrderDetailsResponse(
    String orderId,
    String orderStatus,
    Money total,
    PaymentSummary payment,
    ShipmentSummary shipment,
    String completeness,
    List<String> unavailableComponents
) {}
~~~

DTO phục vụ **client contract**, không bắt các downstream dùng chung Java class này.

### 12.2. Pseudocode composition

~~~java
public final class OrderDetailsComposer {
    private final OrderClient orders;
    private final PaymentClient payments;
    private final ShippingClient shipping;

    public Mono<OrderDetailsResponse> getDetails(
        String orderId,
        CallerContext caller
    ) {
        return orders.getAuthorizedOrder(orderId, caller)
            .flatMap(order -> {
                Mono<PaymentSummary> payment =
                    payments.getSummary(order.id(), caller);

                Mono<Optional<ShipmentSummary>> shipment =
                    shipping.getSummary(order.id(), caller)
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty())
                        .onErrorResume(
                            TemporaryUnavailable.class,
                            ex -> Mono.just(Optional.empty())
                        );

                return Mono.zip(payment, shipment)
                    .map(parts -> mapForClient(
                        order, parts.getT1(), parts.getT2()
                    ));
            });
    }
}
~~~

Ý tưởng:

1. Order là nguồn bắt buộc và cần xác minh quyền.
2. Payment là nguồn bắt buộc theo use case minh họa.
3. Shipping có thể thiếu khi lỗi **tạm thời được phép fallback**, không phải khi 403 hoặc schema hỏng.
4. Sau khi Order xác nhận, Payment và Shipping có thể được gọi song song.
5. Mapping tạo representation, không sửa nguồn sự thật.
6. Mọi call cần timeout, deadline, metrics, trace và giới hạn concurrency.

Đây là pseudocode, không phải implementation đã có đầy đủ imports, cancellation, Reactor context hoặc error mappings. Với reactive operators, cần chú ý cách xử lý Mono rỗng để response không biến mất bất ngờ.

### 12.3. Phân chia mã nguồn

~~~text
api/
  OrderDetailsController.java
application/
  OrderDetailsComposer.java
clients/
  OrderClient.java
  PaymentClient.java
  ShippingClient.java
mapping/
  OrderDetailsMapper.java
observability/
  CompositionMetrics.java
~~~

Đừng đưa repository truy cập trực tiếp bảng Payment/Shipping vào BFF. Không viết **OrderPricingService** ở gateway nếu nó tự quyết định giá trị phải thu.

### 12.4. Kiểm soát side effect

Một route GET tổng hợp phải có ngữ nghĩa đọc. Không thực hiện command như:

~~~java
// Phản mẫu:
if (payment.status().equals("CAPTURED")
    && order.status().equals("PENDING_PAYMENT")) {
    orderClient.markConfirmed(order.id());
}
~~~

Để sửa trạng thái Order, hãy phát lệnh qua application owner với các điều kiện, idempotency và transaction phù hợp. Gateway chỉ trình bày trạng thái đã công bố.

## 13. GraphQL Gateway: thuận tiện nhưng không miễn phí

Một GraphQL API có thể cho phép client chọn field của nhiều nguồn trong một request:

~~~graphql
query OrderDetails($id: ID!) {
  order(id: $id) {
    id
    status
    total { amount currency }
    payment { status }
    shipment { status trackingCode }
  }
}
~~~

Resolver có thể gọi domain APIs hoặc read model. Tuy nhiên:

- GraphQL không tự khử N+1; cần batching/DataLoader nếu phù hợp.
- Một query sâu có thể gây hàng nghìn calls; cần depth/complexity limit.
- Authorization phải áp đến field/resource phù hợp.
- Một số field có thể lỗi; GraphQL response partial cần chính sách error và nullability rõ.
- Caching/ETag phức tạp hơn khi field selection thay đổi.
- Resolver không được tự định nghĩa nghiệp vụ mới.

Với nhu cầu ít endpoint và contract ổn định, REST BFF thường đơn giản hơn. Chọn GraphQL khi tính linh hoạt truy vấn mang lại giá trị đủ lớn để chịu governance và vận hành bổ sung.

## 14. Khi nào tách composition ra khỏi gateway chung?

### 14.1. Giữ gateway mỏng khi có thể

Nếu gateway chỉ route và xử lý cross-cutting concerns, cấu hình dễ phát hành. Một số phép mapping rất đơn giản có thể ở gateway khi được kiểm thử và không làm domain coupling tăng cao.

### 14.2. Chuyển sang BFF hoặc composition service khi

- Có nhiều client cần representation khác nhau.
- Fan-out có logic fallback và cache phức tạp.
- Mỗi thay đổi màn hình buộc thay đổi gateway lõi.
- Đội frontend cần phát triển API presentation theo nhịp riêng.
- Composer cần tracing/metrics riêng và ownership rõ.
- Code gateway bắt đầu hiểu trạng thái domain, làm gateway khó release.

### 14.3. Chuyển sang read model khi

- Một phép tổng hợp được dùng thường xuyên với lưu lượng đọc rất cao.
- Dependency runtime khiến p99 và availability không đạt mục tiêu.
- Dữ liệu có thể chậm một mức được định nghĩa.
- Tổ chức sẵn sàng vận hành event consumers, replay, schema migrations và reconciliation.

### 14.4. Chuyển về application/workflow owner khi

- Logic quyết định trạng thái, tiền hoặc quyền thực hiện command.
- Có giao dịch cần compensation hoặc trạng thái quy trình dài.
- Cần audit, idempotency, recovery sau crash.
- Có bất biến phải được bảo đảm dù client gọi qua kênh nào.

Không nhất thiết mỗi lựa chọn tạo service mới. Có thể làm module rõ trong một deployable trước rồi tách khi cần triển khai/scale riêng.

## 15. Quan sát, SLO và quản trị vận hành

### 15.1. Metric thiết yếu

| Metric | Tác dụng |
| --- | --- |
| Requests/s theo route/client | Đo tải ngoài |
| Downstream calls per request | Đo fan-out amplification |
| p50/p95/p99 latency composite | Trải nghiệm client |
| Downstream latency/failure rate | Xác định dependency gây chậm/lỗi |
| Full response rate | Tỷ lệ đáp ứng đầy đủ |
| Partial response rate | Tỷ lệ fallback trình bày |
| Timeout/retry count | Phát hiện lỗi dây chuyền |
| Circuit breaker open / in-flight | Áp lực hệ thống |
| Cache hit rate và stale age | Hiệu quả/độ mới của cache |
| Authorization denial | Khả năng bảo vệ dữ liệu |
| Projection lag/reconciliation backlog | Rủi ro độ mới khi dùng CQRS |

Nếu HTTP 200 tăng nhưng 80% response chỉ có thông tin thiếu Shipping, gateway có thể trông “xanh” về transport nhưng trải nghiệm đang kém. Vì vậy phải đo cả **completeness** và business outcome tại domain owner.

### 15.2. Distributed tracing

Một trace minh họa:

~~~text
GET /order-details/ORD-1001          400 ms
  +-- GET Order                        80 ms
  +-- GET Payment                     110 ms
  +-- GET Shipping                    300 ms
  +-- Compose + Serialize              20 ms
~~~

Thời gian giữa các span có thể chồng lấn vì chạy song song; không cộng tất cả duration thành end-to-end latency. Trace cần truyền correlation context, nhưng không chứa secret hoặc payload thanh toán nhạy cảm.

### 15.3. Ownership và contract governance

Cần xác định:

- Đội sở hữu composite contract và tài liệu OpenAPI.
- Đội sở hữu từng published downstream contract.
- Ai chốt mapping khi hai context có thuật ngữ khác nhau.
- Ai vận hành gateway, BFF, read model và on-call.
- Chính sách versioning/deprecation của composite API.
- Quy trình đánh giá breaking changes, timeout budget, cache và security.

Gateway không nên trở thành điểm phải chờ mọi đội phê duyệt cho một thay đổi presentation nhỏ, nhưng các domain rule phải do owner tương ứng xác nhận.

## 16. Kiểm thử cho composition API

### 16.1. Contract tests

- Response đủ các trường, type, currency, timestamps theo hợp đồng.
- Mapping không đổi nghĩa trạng thái domain.
- Unknown enum có hành vi an toàn, không tự được coi là thành công.
- Consumer cũ không hỏng khi downstream schema thêm field.
- API version và deprecation được quản lý khi composite thay đổi.

### 16.2. Integration tests

- Order tồn tại, đủ quyền, downstream đều thành công.
- Order không tồn tại trả 404 đúng.
- Order không được phép đọc không làm lộ dữ liệu.
- Shipping timeout trả partial nếu contract cho phép.
- Payment timeout không trả paid=true.
- Catalog thiếu sản phẩm có fallback hợp lệ.
- Cùng orderId ở hai tenant không bị trộn cache.
- Gateway không truy cập trực tiếp database của downstream.
- Request bị cancel không gây resource leak.
- Retry/timeout không gây bão request.

### 16.3. Performance và failure tests

- Load test với Order có 1, 20, 100 item.
- Kiểm tra batch Catalog để tránh N+1.
- Kiểm tra fan-out khi nhiều client request đồng thời.
- Mô phỏng Payment chậm, Shipping down, connection pool đầy.
- Kiểm tra fallback đúng loại lỗi (không che 403).
- Đo latency và partial rate khi cache miss.
- Mô phỏng query GraphQL có độ sâu và số node lớn.
- Kiểm tra trạng thái read model chậm và dữ liệu lệch pha.

Một test tốt phải xác minh **kết quả hiển thị đúng nghĩa nghiệp vụ**, không chỉ status 200 và JSON parse được.

## 17. Các phản mẫu cần tránh

### 17.1. Gateway thành monolith nghiệp vụ

Gateway chứa PricingPolicy, RefundEligibility, InventoryAllocator và state machine Order. Mọi tính năng phải sửa gateway chung, phá quyền tự chủ của domain. **Khắc phục:** đưa quyết định về context owner, gateway chỉ gọi contract.

### 17.2. Database join xuyên service

Gateway JOIN bảng Order với Payment và Shipping. Schema coupling và quyền truy cập làm lộ nội bộ. **Khắc phục:** public APIs hoặc read projection có owner, không truy cập trực tiếp database của các context khác.

### 17.3. Trả 200 với null cho mọi lỗi

Client không biết tài nguyên chưa tồn tại hay downstream đang lỗi. **Khắc phục:** status và completeness/metadata rõ, phân biệt unavailable/forbidden/not created.

### 17.4. Fan-out N+1

Mỗi item lại gọi Catalog một lần. **Khắc phục:** batch lookup, projection, cache và phân trang.

### 17.5. Retry không giới hạn

Một outage làm gateway, BFF, domain cùng retry. **Khắc phục:** deadline, jitter/backoff, retry budget, giới hạn in-flight.

### 17.6. Cache nhầm dữ liệu private

Một response Order được cache theo orderId và phục vụ cho user khác. **Khắc phục:** identity/tenant-aware cache hoặc no-store, kiểm thử cross-tenant.

### 17.7. Che eventual consistency

Order trả PENDING, Payment trả CAPTURED; gateway tự biến thành CONFIRMED. **Khắc phục:** trình bày trạng thái có thật, timestamp và xử lý pending theo contract.

### 17.8. Không phân biệt quyền ở gateway và service

Gateway xác thực token rồi downstream tin mọi request. **Khắc phục:** resource-level authorization và service identity ở owner.

### 17.9. Mỗi màn hình một service ngay từ đầu

Tạo hàng chục BFF không có nhu cầu triển khai riêng làm tăng chi phí vận hành. **Khắc phục:** khởi đầu bằng module rõ, tách deployment khi nhịp thay đổi/scale và ownership chứng minh cần.

### 17.10. Dùng read model để thực thi command

Projection có thể stale; nếu lấy projection để quyết định giữ tồn hoặc hoàn tiền, bất biến có thể bị phá. **Khắc phục:** command được xác minh tại domain owner.

## 18. Bài thực hành: Order Details dành cho mobile

Giả sử hệ thống có bốn dịch vụ:

- Order: Order ID, line items, trạng thái, tổng tiền chốt.
- Payment: Payment status, payment attempt.
- Shipping: Shipment status, tracking code.
- Catalog: tên, ảnh và mô tả sản phẩm hiện tại.

Mobile cần một endpoint GET /api/order-details/{id}; khách có thể xem thông tin đơn và nút hủy nếu policy cho phép.

**Phần A — Xác định dữ liệu.** Vẽ mapping field → service owner, phân biệt dữ liệu chốt lúc mua và Catalog hiện tại.

**Phần B — Ranh giới nghiệp vụ.** Giải thích vì sao **canCancelOrder** phải do Order owner công bố. Nêu ba trường hợp gateway tự tính rule có thể gây sai.

**Phần C — Fan-out.** Thiết kế thứ tự gọi, phần nào song song, API batch Catalog và deadline tổng 800 ms. Giới hạn một Order tối đa 100 item.

**Phần D — Lỗi một phần.** Định nghĩa response khi Shipping timeout, Payment timeout, Order 404, Order 403, Catalog thiếu một SKU. Phân biệt no data và data unavailable.

**Phần E — Bảo mật.** Xác định cách xác minh caller thuộc tenant nào, quyền trên Order, credential nội bộ, cache key và log có thể giữ.

**Phần F — Tải lớn.** Nếu endpoint đạt 10.000 request/s, so sánh composition trực tiếp với OrderDetails projection, nêu trade-off về độ mới và chi phí replay.

**Phần G — Kiểm thử.** Viết danh sách test cho N+1, retry storm, stale data, partial response, unknown Payment status và cross-tenant cache.

Bài tập hoàn thành khi client nhận được view hữu ích, mỗi service vẫn sở hữu dữ liệu và quyết định của mình, còn gateway có thể thất bại hoặc thiếu dữ liệu một cách minh bạch thay vì tự bịa ra trạng thái nghiệp vụ.

## 19. Checklist triển khai

- [ ] Đã xác định owner và nguồn sự thật cho từng field.
- [ ] Đã phân biệt presentation mapping với quyết định domain.
- [ ] Gateway/BFF không ghi trực tiếp database của service khác.
- [ ] Đã chọn required/optional component theo use case.
- [ ] Composite contract mô tả null/missing/unavailable/stale.
- [ ] Có timeout/deadline tổng, retry budget và concurrency limit.
- [ ] Có batch lookup tránh N+1.
- [ ] Có phân quyền resource/tenant tại service owner.
- [ ] Cache không làm rò dữ liệu và có chính sách độ mới.
- [ ] Khi domain state thay đổi, gateway không tự ép trạng thái.
- [ ] Có contract/integration/performance tests cho partial failure.
- [ ] Có tracing và metrics fan-out/completeness/latency.
- [ ] Đã xem xét BFF hoặc projection nếu logic đọc phức tạp.
- [ ] Đã có owner, versioning và runbook cho endpoint composite.

## 20. Ghi nhớ

**API Gateway giúp giảm độ phức tạp truy cập từ phía client, nhưng không được tập trung hóa quyền quyết định nghiệp vụ của các microservice.** Tổng hợp dữ liệu thành một read view là một trách nhiệm riêng với các yêu cầu về contract, phân quyền, độ mới, timeout và khả năng quan sát.

Tư duy lựa chọn:

~~~text
Client cần một view nhiều nguồn
               |
               v
Xác định field và domain owner
               |
               v
Đánh giá fan-out, consistency, security
               |
       +-------+-------+
       |               |
       v               v
Runtime composition  Read projection
(BFF/composer)       (CQRS khi phù hợp)
       |               |
       +-------+-------+
               |
               v
Contract + partial failure + monitoring
               |
               v
Business decision vẫn ở domain owner
~~~

**Năm nguyên tắc trọng tâm:**

1. **Gateway là lớp biên, không phải siêu service nghiệp vụ.**
2. **Composition là hợp đồng đọc riêng**, cần trả dữ liệu đúng nghĩa và thể hiện lỗi một phần trung thực.
3. **Fan-out không miễn phí**; batching, parallelism, deadline, cache và projection cần được cân nhắc.
4. **Source of truth và invariant nằm ở domain owner**, ngay cả khi gateway đọc dữ liệu của nhiều context.
5. **Nâng cấp vị trí composition theo nhu cầu**, bắt đầu đơn giản, tách BFF/composer/read model khi lưu lượng, sự phức tạp và ownership có lý do thực tế.

Thiết kế đúng giúp client có API nhất quán mà từng microservice vẫn giữ được **tính tự chủ, bảo mật, khả năng phát hành độc lập và trách nhiệm nghiệp vụ rõ ràng**.
