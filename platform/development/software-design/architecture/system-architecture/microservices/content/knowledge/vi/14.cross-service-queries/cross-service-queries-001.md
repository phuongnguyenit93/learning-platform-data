# Nhận diện nhu cầu đọc dữ liệu từ nhiều dịch vụ

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Truy vấn liên dịch vụ

## 1. Bài toán: một màn hình nghiệp vụ, nhiều nguồn dữ liệu

Trong kiến trúc microservices, mỗi dịch vụ nên có trách nhiệm rõ ràng đối với dữ liệu và quy tắc nghiệp vụ của mình. Nhưng một người dùng thường không thao tác với “dịch vụ” theo cách các lập trình viên phân chia. Họ nhìn thấy **một màn hình, một báo cáo, một thao tác nghiệp vụ** và mong có đủ thông tin để hiểu hoặc quyết định.

Ví dụ màn hình “Chi tiết đơn hàng” cần:

- Thông tin đơn và danh sách dòng hàng từ Ordering.
- Trạng thái thanh toán từ Payment.
- Thông tin giao hàng từ Shipping.
- Tên và ảnh của sản phẩm từ Catalog.
- Thông tin chăm sóc khách hàng hoặc địa chỉ giao nhận theo quyền truy cập phù hợp.

Nếu dữ liệu nằm ở nhiều service, câu hỏi kiến trúc không chỉ là “gọi REST endpoint nào?”. Trước tiên cần **nhận diện chính xác nhu cầu đọc**: ai cần, để làm gì, dữ liệu nào bắt buộc, độ mới ra sao, phản hồi cần trong bao lâu, và kết quả đọc có được dùng để thực hiện một quyết định nghiệp vụ hay không.

Một mô hình minh họa:

```text
Browser / Mobile
      |
      | GET /order-overview/ORD-1042
      v
Order Overview / BFF
      |
      +-------> Ordering: order, order items
      +-------> Payment: payment state
      +-------> Shipping: tracking state
      '-------> Catalog: display information
      |
      v
Một mô hình đọc phục vụ giao diện
```

**Mối quan tâm cốt lõi:** dữ liệu được sở hữu theo **ranh giới nghiệp vụ**, còn nhu cầu đọc được xác định theo **use case**. Hai cách chia này thường không trùng nhau.

Mục tiêu của bài là phát hiện nhu cầu đọc liên dịch vụ một cách có hệ thống, trước khi quyết định dùng API composition, batch API, cache, read model, CQRS projection, search index, reporting store hay phương án khác.

## 2. Định nghĩa: thế nào là một truy vấn liên dịch vụ?

**Truy vấn liên dịch vụ (cross-service query)** là nhu cầu lấy thông tin cho một use case mà dữ liệu cần thiết do hai hoặc nhiều service độc lập sở hữu.

Ví dụ:

1. **Order Overview:** hiển thị đơn, thanh toán và giao hàng.
2. **Product Search:** tìm kiếm sản phẩm với tên, giá, tình trạng sẵn bán và tiêu chí lọc.
3. **Customer 360:** hỗ trợ viên cần xem thông tin khách, đơn hàng và các yêu cầu chăm sóc.
4. **Sales Dashboard:** tổng hợp số lượng đơn, thanh toán thành công và hoàn tiền.
5. **Checkout:** cần một số thông tin từ Catalog, Pricing, Inventory và Payment để xác định bước tiếp theo.

Không phải mọi ví dụ trên đều nên xử lý giống nhau. Màn hình phân tích có thể chấp nhận dữ liệu trễ vài phút; thao tác xác nhận thanh toán có thể đòi tính đúng đắn tại thời điểm thực hiện; màn hình chi tiết có thể chấp nhận thiếu một ảnh sản phẩm nhưng không được bịa tình trạng thanh toán.

### 2.1. Phân biệt “đọc” với “phối hợp thay đổi trạng thái”

Một API đọc đơn hàng có thể hỏi ba service rồi ghép response. Nhưng một API “đặt hàng” phải giữ tồn kho và xác nhận thanh toán không chỉ là bài toán read composition. Nó là quy trình thay đổi trạng thái, có invariant, transaction hoặc saga tùy thiết kế.

```text
GET /orders/{id}/overview
    -> truy vấn/tổng hợp để hiển thị

POST /orders/{id}/confirm
    -> command cần bảo vệ bất biến nghiệp vụ
```

Không nên biến một command quan trọng thành “chạy mấy GET rồi quyết định ở gateway” nếu dữ liệu có thể thay đổi giữa lúc kiểm tra và lúc ghi.

### 2.2. Truy vấn liên dịch vụ không đồng nghĩa với distributed SQL JOIN

Nếu Ordering và Payment có database riêng, phép JOIN trực tiếp giữa bảng của hai service không phải là lựa chọn mặc định. Shared database, cross-database JOIN hoặc đọc bảng nội bộ của service khác có thể tạo coupling mạnh với schema, quyền truy cập, migration và vòng đời triển khai.

**Quyền sở hữu dữ liệu** không biến mất chỉ vì người dùng cần một màn hình tổng hợp. Có thể kết hợp dữ liệu ở tầng API hoặc xây một mô hình đọc riêng mà không cho service khác tự ý ghi/đọc sâu vào cấu trúc lưu trữ nội bộ.

## 3. Khi nào cần nhận diện nhu cầu này?

Những dấu hiệu thường xuất hiện trong backlog, thiết kế UX hoặc code:

| Dấu hiệu | Ví dụ | Câu hỏi cần đặt |
| --- | --- | --- |
| Một màn hình ghép nhiều khối | Đơn, thanh toán, vận chuyển | Mỗi khối thuộc service nào? |
| API client gọi nhiều endpoint rồi join | Mobile gọi 8 endpoint để dựng 1 trang | Có cần BFF/API composition không? |
| UI có bộ lọc qua nhiều domain | Lọc đơn theo trạng thái thanh toán và khu vực giao hàng | Filter/sort/pagination được thực hiện ở đâu? |
| Một endpoint gọi N lần cùng service | Mỗi sản phẩm lại gọi Catalog một lần | Có thể bulk/batch hoặc dùng projection không? |
| Dashboard yêu cầu dữ liệu nhiều nguồn | Doanh thu, hủy đơn, hoàn tiền | Có chấp nhận eventual consistency và warehouse không? |
| Service muốn đọc database service khác | SupportService JOIN bảng Payment | Có contract công khai hoặc read model không? |
| Mọi request đều gọi nhiều service đồng bộ | Một trang phải đợi 6 downstream | Đâu là critical path và điểm nghẽn? |
| Dữ liệu hiển thị không khớp sau cập nhật | Đơn “PAID” nhưng giao hàng chưa cập nhật | Có cần một snapshot nhất quán hay chỉ cần hiển thị trạng thái theo từng nguồn? |

Nếu chưa thấy dấu hiệu, không nên xây sẵn một “generic query engine” phức tạp. Một dịch vụ có thể phục vụ phần lớn thao tác độc lập; chỉ những use case thực sự cần nhiều nguồn mới cần thiết kế liên dịch vụ.

## 4. Bắt đầu từ câu hỏi của người dùng, không từ endpoint

Lấy ví dụ một nhân viên chăm sóc khách hàng hỏi:

> “Đơn ORD-1042 đã thanh toán chưa và kiện hàng đang ở đâu?”

Hãy phân tích câu hỏi thay vì mở IDE và bắt đầu thêm `GET /everything`.

**Đầu ra cần thiết:**

```json
{
  "orderId": "ORD-1042",
  "orderStatus": "CONFIRMED",
  "payment": {
    "status": "CAPTURED",
    "asOf": "2026-11-11T09:00:00Z"
  },
  "shipment": {
    "status": "IN_TRANSIT",
    "trackingCode": "TRK-782",
    "asOf": "2026-11-11T08:58:00Z"
  }
}
```

Dữ liệu trên chỉ để minh họa, không mô tả một đơn hàng có thật.

Các câu hỏi thiết kế cần trả lời:

- `orderStatus`, `payment.status`, `shipment.status` do ai sở hữu?
- Có cần đọc theo cùng một mốc thời gian hay có thể dùng giá trị ở các thời điểm khác nhau?
- Nếu ShippingService lỗi, support có thể vẫn xem thanh toán không?
- Nếu PaymentService lỗi, có được kết luận đơn “chưa thanh toán” không? **Không**, nếu trạng thái thực chưa biết.
- Có cần độ trễ dưới 500 ms, 1 giây hay có thể đợi vài giây?
- Người gọi có được quyền đọc mã vận đơn và thông tin khách hàng không?
- Truy vấn một đơn hay truy vấn hàng nghìn đơn có filter/sort/pagination?

Những câu hỏi này quyết định mô hình đọc; tên công nghệ chỉ đến sau.

## 5. Sáu chiều phân loại một nhu cầu đọc

### 5.1. Mục đích: hiển thị, phân tích hay ra quyết định?

**Hiển thị:** dữ liệu phục vụ UX, thường có thể chấp nhận phần tùy chọn thiếu hoặc đọc cache nếu mức độ mới được nêu rõ.

**Phân tích:** truy vấn qua nhiều miền, thường theo thời gian dài và có tổng hợp; có thể chuyển sang warehouse/reporting store, batch hoặc read projection.

**Ra quyết định:** dữ liệu là điều kiện cho command như thanh toán, cấp quyền, giữ hàng. Lúc này đọc một snapshot cũ có thể gây sai lệch. Cần giữ quyền xác nhận invariant tại service authoritative hoặc quy trình nghiệp vụ phù hợp.

Đặt một truy vấn vào đúng nhóm giúp tránh việc dùng dashboard cache để kiểm tra tồn kho thực khi khách đặt hàng.

### 5.2. Tính cấp thiết của từng phần dữ liệu

Một kết quả có thể gồm:

- **Required:** thiếu thì phản hồi không còn đúng hợp đồng.
- **Optional:** thiếu thì vẫn có câu trả lời hữu ích và được công bố partial.
- **Can-be-stale:** chấp nhận giá trị đã lưu trong giới hạn rõ.
- **Can-load-later:** có thể tải riêng sau khi màn hình hiển thị phần chính.

Ví dụ tên sản phẩm trong lịch sử đơn có thể lấy từ snapshot đã ghi lúc mua. Hình ảnh gợi ý có thể bỏ qua khi Catalog chậm. Trạng thái thu tiền không nên được bịa thành `PAID` hoặc `UNPAID` khi Payment không trả lời.

### 5.3. Mức độ mới (freshness)

Hãy diễn đạt một yêu cầu có thể kiểm chứng:

- “Giá trị mới nhất tại thời điểm người dùng gửi request, theo owner” là yêu cầu mạnh và có thể khó đạt tuyệt đối trong hệ phân tán.
- “Chấp nhận thông tin chậm tối đa 30 giây” là một điều kiện rõ hơn cho projection.
- “Báo cáo cập nhật vào cuối ngày” có thể phù hợp với batch.
- “Giá sản phẩm đúng lúc tạo đơn” là **snapshot theo thời điểm giao dịch**, khác với giá hiện tại ở Catalog.

**Freshness** không đồng nghĩa **consistency**. Một read model cập nhật nhanh chưa chắc bảo đảm phản ánh các thay đổi của hai nguồn trong cùng một transaction toàn hệ thống.

### 5.4. Cardinality, lượng dữ liệu và cách lọc

Truy vấn một `orderId` đơn giản khác hoàn toàn:

```text
Liệt kê 100.000 đơn hàng
  where paymentStatus = CAPTURED
    and shippingRegion = NORTH
  order by confirmedAt desc
  limit 50 offset 1000
```

Ở tình huống thứ hai, dữ liệu lọc và sắp xếp thuộc nhiều service. Nếu chỉ lấy 50 đơn trước rồi gọi Payment/Shipping để lọc sau, kết quả phân trang có thể sai. Cần xem xét **một mô hình đọc tích hợp có index phù hợp**, hoặc một query service chuyên trách và quy tắc độ mới dữ liệu.

Cần phân tích:

- Tập dữ liệu lớn bao nhiêu và tăng như thế nào?
- Filter/sort thực hiện trước hay sau khi ghép dữ liệu?
- Pagination có chính xác và ổn định không?
- Có nhiều-to-many joins hoặc dữ liệu lặp không?
- Có nhu cầu tìm kiếm full-text, thống kê, aggregation hay group-by không?

### 5.5. Độ trễ và độ sẵn sàng

Một trang cá nhân phải hiển thị nhanh; một báo cáo phân tích có thể chạy nền. Nhu cầu về p95/p99 latency và availability ảnh hưởng lớn đến việc chọn API composition hay projection.

Nếu một request cần tất cả bốn downstream đồng bộ cùng sẵn sàng, xác suất thành công toàn hành trình có thể thấp hơn từng nhánh. Trong trường hợp giả định **độc lập** và mỗi nhánh có xác suất thành công 0,99:

```text
P(all 4 required calls succeed) = 0.99 ^ 4 ≈ 0.9606
```

Con số chỉ minh họa giả định đơn giản; thực tế lỗi có tương quan do mạng, hạ tầng chung hoặc tải. Nhưng nó cho thấy thêm một dependency required vào critical path có thể làm giảm độ sẵn sàng của endpoint tổng hợp.

### 5.6. Bảo mật, tenant và quyền sử dụng

Service tổng hợp dữ liệu phải kiểm tra:

- Quyền truy cập trên từng `orderId`, `customerId`, `paymentId`.
- Dữ liệu nào được phép xuất hiện ở client/role cụ thể.
- Có được cache theo tenant/user hay không.
- Có cần che thông tin định danh cá nhân, địa chỉ hoặc dữ liệu giao dịch.
- Có nguy cơ truy vấn nhiều service làm rò rỉ sự tồn tại của resource bị cấm xem.

**“Có thể truy vấn” không đồng nghĩa “được phép hiển thị”.** Query facade không tự có quyền truy cập mọi data chỉ vì nó ở lớp tổng hợp.

## 6. Lập bản đồ quyền sở hữu dữ liệu (data ownership map)

Trước khi thiết kế endpoint, tạo ma trận ngắn:

| Dữ liệu cần | Service sở hữu | Định danh công khai | Độ mới yêu cầu | Mục đích |
| --- | --- | --- | --- | --- |
| Đơn và dòng hàng | Ordering | `orderId` | Hiển thị hiện tại hoặc snapshot lịch sử | Order detail |
| Trạng thái payment | Payment | `paymentId`/`orderId` qua contract | Theo thời điểm truy vấn | Trạng thái thu tiền |
| Kiện và mã vận đơn | Shipping | `shipmentId`/`orderId` | Trễ ngắn có thể chấp nhận khi hiển thị | Tracking |
| Tên/ảnh sản phẩm | Catalog | `productId` | Có thể dùng snapshot/cache theo use case | UX |
| Tình trạng giữ hàng | Inventory | `sku`, `reservationId` | Quyết định phải theo owner | Command |
| Số liệu lịch sử | Reporting/Analytics | Batch key, date range | Theo lịch đồng bộ | Dashboard |

Ma trận làm rõ hai vấn đề dễ bị bỏ qua:

1. **Ai có thẩm quyền xác định giá trị?** Một bản copy `paymentStatus` ở Ordering có thể chỉ là snapshot, không phải sự thật authoritative của Payment.
2. **Có khóa liên hệ công khai và ổn định không?** Một phép ghép dùng `dbRowId` hoặc khóa ngoại nội bộ từ database service khác làm tăng coupling. Nên dùng business identifier được định nghĩa trong integration contract.

### 6.1. Không ép các bounded context dùng chung entity

Một customer trong CRM và buyer trong Ordering có thể có vòng đời, ý nghĩa và dữ liệu khác nhau. Một `customerId` không nhất thiết đủ để chứng minh mọi record đều một-một. Có thể cần mapping, snapshot hoặc quy tắc hợp nhất định danh.

Mô hình đọc có thể tạo một **view theo nhu cầu** nhưng không nên buộc các service đồng bộ database schema hoặc cùng triển khai một class domain chung.

## 7. Khi nào dùng API composition trực tiếp?

**API composition** là cách gọi các service có dữ liệu cần thiết trong lúc request đang được xử lý rồi ghép response.

Ví dụ:

```text
GET /orders/ORD-1042/overview
  |
  v
OrderOverviewBFF
  +---> Ordering.get(ORD-1042)
  +---> Payment.getByOrder(ORD-1042)
  '---> Shipping.getByOrder(ORD-1042)
  |
  v
Combine -> Response
```

**Thường phù hợp khi:**

- Chủ yếu truy vấn một entity hoặc một tập dữ liệu nhỏ.
- Cần thông tin tương đối mới tại thời điểm request.
- Số downstream nhỏ và có thể quản lý deadline.
- Những lời gọi có contract rõ, có thể thực hiện song song khi độc lập.
- Lỗi của từng nhánh được định nghĩa theo required/optional.
- Chưa có lý do chịu chi phí xây read projection riêng.

**Ít phù hợp hơn khi:**

- Mỗi request phải gọi hàng trăm service/record.
- Cần lọc/sắp xếp/trang hóa trên dữ liệu của nhiều service.
- Truy vấn analytic nặng và chạy thường xuyên.
- Nhiều màn hình đều lặp lại cùng tổ hợp dữ liệu.
- Độ trễ hoặc availability của nhiều downstream không đáp ứng SLO.

### 7.1. Tính gần đúng độ trễ

Nếu ba lời gọi độc lập có thời gian minh họa:

```text
Ordering:  100 ms
Payment:   180 ms
Shipping:  140 ms
```

Nối tiếp: gần `100 + 180 + 140 = 420 ms` chưa gồm overhead.

Song song: gần `max(100, 180, 140) = 180 ms` cộng scheduling, mạng và ghép dữ liệu.

Đây là thời gian một lần quan sát, **không có nghĩa p99 aggregator bằng max p99 của từng nhánh**. Tail latency cần đo trên request end-to-end, vì tương quan, queue, retry và pool contention có thể thay đổi kết quả.

### 7.2. Required và optional phải xuất hiện trong contract

```json
{
  "order": {
    "id": "ORD-1042",
    "status": "CONFIRMED"
  },
  "payment": {
    "status": "CAPTURED",
    "dataStatus": "AVAILABLE"
  },
  "shipment": {
    "dataStatus": "UNAVAILABLE",
    "reasonCode": "UPSTREAM_TIMEOUT"
  },
  "partial": true
}
```

Với màn hình đọc, Shipping có thể optional. Nếu Payment là required, không được trả `CAPTURED` giả để tránh lỗi. Một partial response 200 có thể hợp lệ **nếu hợp đồng endpoint định nghĩa nó như một kết quả đúng**; không nên âm thầm biến một nguồn không có dữ liệu thành “đơn không có thanh toán”.

## 8. Nhận diện N+1 và gọi dịch vụ quá nhiều

Một vấn đề phổ biến:

```text
Ordering.listOrders(customerId) -> 50 orders
For each order:
    Payment.getByOrder(orderId)  -> 50 calls
    Shipping.getByOrder(orderId) -> 50 calls
```

Một màn hình “50 đơn gần đây” có thể tạo 101 lời gọi outbound (1 cho danh sách, 50 payment, 50 shipment). Với 200 client request/giây, số lời gọi tăng rất mạnh. Nếu retry hoặc fan-out tiếp diễn ở service đích, tải có thể khuếch đại tiếp.

Các dấu hiệu N+1:

- Một vòng lặp qua danh sách rồi gọi HTTP/gRPC.
- Trace có nhiều span giống nhau chỉ khác ID.
- Số remote calls/request tỉ lệ với số item trong trang.
- Trang 10 item nhanh, trang 100 item rất chậm.
- Downstream nhận đột biến request đồng thời khi user tải danh sách.

### 8.1. Giảm số calls trước khi tăng concurrency

Phương án có thể là:

- **Batch API:** `POST /payments/statuses:batch` nhận danh sách order IDs và trả mapping.
- **Bulk endpoint theo business use case:** Owner cung cấp truy vấn hữu ích ở mức domain, không chỉ từng row.
- **Read model:** duy trì projection cho màn hình list.
- **Snapshot:** lưu một số thông tin hiển thị khi giao dịch diễn ra nếu domain cho phép.
- **Lazy loading:** tải widget ít quan trọng khi cần.
- **Pagination hợp lý:** giới hạn tập bản ghi ban đầu và kích thước payload.

Nếu downstream không hỗ trợ batch, có thể dùng concurrency có giới hạn và deadline trong giai đoạn chuyển tiếp, nhưng nó **không xóa bản chất N+1**. Một lớp thread pool lớn không thay thế thiết kế query phù hợp.

### 8.2. Batch API cũng cần hợp đồng

Với batch API, phải rõ:

- Số ID tối đa trong một batch.
- Có giữ thứ tự request hay trả theo key?
- Một ID không tồn tại hoặc không có quyền thì biểu diễn thế nào?
- Một ID lỗi có làm cả batch lỗi hay trả partial per-item?
- Có giới hạn payload, deadline và deduplication?
- Có thể bị lợi dụng để truy vấn dữ liệu của nhiều tenant không?

Một batch endpoint không nên vô tình cho phép client gửi hàng trăm ID bất kỳ để vượt qua kiểm tra authorization theo từng resource.

## 9. Khi nào dùng CQRS read model hoặc materialized projection?

**CQRS (Command Query Responsibility Segregation)** phân tách mô hình xử lý thay đổi trạng thái khỏi mô hình phục vụ truy vấn khi lợi ích vượt chi phí. Trong bối cảnh liên dịch vụ, một **read model/projection** có thể gom những trường dữ liệu đã công bố từ nhiều nguồn vào một cấu trúc tối ưu cho việc đọc.

```text
Ordering -- OrderConfirmed ---------+
                                    |
Payment  -- PaymentCaptured --------+--> Event consumers
                                    |       |
Shipping -- ShipmentDispatched -----+       v
                                   OrderOverviewProjection
                                           |
                                           v
                                     Query API / BFF
                                           |
                                           v
                                         Client
```

Một record đọc có thể chứa:

```json
{
  "orderId": "ORD-1042",
  "orderStatus": "CONFIRMED",
  "paymentStatus": "CAPTURED",
  "shipmentStatus": "IN_TRANSIT",
  "lastUpdatedAt": "2026-11-11T09:10:00Z"
}
```

**Thường phù hợp khi:**

- Query rất thường xuyên, lặp lại một tổ hợp dữ liệu.
- Cần filter/sort/pagination qua nhiều miền.
- Fan-out đồng bộ quá tốn hoặc không đáp ứng p95/p99.
- Chấp nhận dữ liệu hội tụ sau một độ trễ được công bố.
- Có năng lực vận hành event schema, consumer, replay, đối soát và rebuild projection.
- Use case đọc có vòng đời/khả năng mở rộng khác với thao tác ghi.

**Đánh đổi:** read model tăng độ phức tạp, vì tồn tại bản sao dữ liệu, lag, event có thể đến trễ/trùng, schema thay đổi và khả năng sai lệch tạm thời. Nó không miễn trừ trách nhiệm bảo vệ dữ liệu cá nhân hoặc quyền sở hữu nguồn dữ liệu.

### 9.1. Read model không phải nguồn thẩm quyền cho mọi quyết định

Nếu `paymentStatus=CAPTURED` trong projection trễ 5 giây, có thể đủ cho trang lịch sử, nhưng không nhất thiết đủ cho lệnh hoàn tiền. Một command nhạy cảm phải hỏi hoặc giao quyền quyết định cho owner của invariant.

Nên xác định rõ:

- **Authoritative state:** trạng thái do service sở hữu.
- **Derived state:** bản sao dùng để đọc.
- **Staleness:** thời gian từ nguồn phát tới khi projection cập nhật.
- **Repair strategy:** cách phát hiện và sửa projection lệch nguồn.

### 9.2. Event không nhất thiết mang đủ data để dựng projection

Nếu event chỉ có `orderId`, consumer có thể phải gọi API nguồn để lấy thêm dữ liệu. Nhiều event dồn tới cùng lúc tạo event-triggered N+1. Có thể chọn **event-carried state transfer có chọn lọc**, tức công bố những trường nghiệp vụ ổn định cần cho projection mà không serialize toàn bộ database entity.

Điều cần cân bằng:

- Payload nhỏ và contract đơn giản.
- Tải query bổ sung về nguồn.
- Dữ liệu nhạy cảm và quyền truy cập.
- Khả năng tái dựng lịch sử chính xác.
- Thay đổi schema và tính tương thích consumer.

## 10. Những thách thức của một projection liên dịch vụ

### 10.1. Event trùng

At-least-once delivery có thể khiến một event được xử lý lại. Nếu consumer dùng event `PaymentCaptured` để cộng tổng doanh thu hoặc tạo record, phải có idempotency theo `eventId` hoặc business key phù hợp.

Một projection kiểu overwrite trạng thái có thể tự chịu lặp tốt hơn phép tăng counter, nhưng vẫn cần chú ý event cũ đến sau.

### 10.2. Event đến sai thứ tự

```text
OrderConfirmed (version 7)
OrderCancelled (version 8)
```

Nếu consumer nhận version 8 trước rồi version 7, việc “ghi đè bằng event đến sau” có thể làm projection trở về CONFIRMED. Nếu domain công bố aggregate version, consumer có thể chỉ chấp nhận sự kiện mới hơn theo quy ước; nếu thiếu phiên bản, cần cách xử lý/reconciliation khác.

Không mặc định có total ordering giữa các topic/partition/producer. Thứ tự của nhiều domain như Payment và Shipping có thể độc lập.

### 10.3. Event bị thiếu

Khi consumer ngừng quá lâu, broker retention có thể hết. Hoặc lỗi schema khiến event vào DLQ và projection thiếu bản cập nhật. Cần có khả năng:

- Quan sát consumer lag và DLQ.
- Replay từ vị trí còn hợp lệ.
- Rebuild projection từ nguồn dữ liệu/snapshot và các sự kiện còn lưu.
- Đối soát theo khóa nghiệp vụ để phát hiện sai lệch.
- Đánh dấu projection `STALE` hoặc `DEGRADED` khi không bảo đảm mức độ mới.

### 10.4. Đồng bộ dữ liệu giữa nhiều miền không phải transaction toàn cục

Payment và Shipping có thể thay đổi ở các thời điểm khác nhau. Projection đọc được `PaymentCaptured` trước khi `ShipmentDispatched`, hoặc ngược lại. Một màn hình tổng quan có thể hiển thị tổ hợp trạng thái được cập nhật ở các mốc khác nhau.

Đừng mặc định dữ liệu trong một row projection phản ánh một snapshot transaction nguyên tử của toàn hệ thống. Nếu use case đòi một bất biến liên miền, cần mô hình hóa workflow/orchestration hoặc ranh giới ownership để tạo một trạng thái nghiệp vụ được chốt rõ ràng.

## 11. Cache, snapshot và dữ liệu có thể cũ: ba chiến lược khác nhau

### 11.1. Cache query

Lưu tạm kết quả từ source hoặc query composition để giảm latency và tải.

Có thể dùng cache khi:

- Thông tin thường được đọc nhiều và ít thay đổi.
- Tolerated staleness được định nghĩa.
- Cache key bảo vệ tenant/user/permission.
- Có TTL, invalidation và observability.

**Rủi ro:** cache stampede, stale data, cache poisoning, trả dữ liệu sai quyền và kích thước bộ nhớ quá lớn.

### 11.2. Snapshot tại thời điểm nghiệp vụ

Một đơn hàng nên giữ số tiền/đơn giá/địa chỉ giao hàng theo những quy tắc snapshot của giao dịch. Nếu luôn đọc giá hiện tại của Catalog để hiển thị lịch sử, đơn hàng hôm qua có thể bị thể hiện bằng giá hôm nay.

Snapshot không phải là cache cần refresh liên tục. Nó là **bằng chứng của trạng thái ở một thời điểm nghiệp vụ** do domain quyết định.

### 11.3. Materialized read model

Đây là bản sao được cập nhật qua event, CDC đã thiết kế hoặc job đồng bộ để phục vụ truy vấn cụ thể. Nó có vòng đời, schema, versioning và cơ chế rebuild riêng; không chỉ là cache “đặt TTL 10 phút”.

Bảng so sánh:

| Cơ chế | Dùng cho | Điều cần kiểm soát |
| --- | --- | --- |
| Cache | Giảm tải/latency của dữ liệu có thể tải lại | TTL, invalidation, quyền, cache stampede |
| Snapshot | Giữ giá trị đúng tại mốc nghiệp vụ | Quy tắc thời điểm, nguồn gốc, bất biến |
| Projection | Tối ưu truy vấn qua nhiều domain | Event/schema, lag, replay, đối soát |
| API composition | Lấy dữ liệu hiện tại theo request | Fan-out, timeout, availability, partial |

Các cơ chế có thể được kết hợp. Ví dụ BFF có thể dùng projection cho danh sách đơn, rồi gọi service authoritative khi người dùng mở một hành động nhạy cảm.

## 12. Filter, sort và pagination qua nhiều nguồn dữ liệu

Đây là một dấu hiệu mạnh cho thấy việc ghép một vài API response đơn giản có thể chưa đủ.

### 12.1. Vì sao “paginate trước rồi filter sau” có thể sai?

Yêu cầu:

> “Lấy 20 đơn đã thanh toán và đã giao, mới nhất trước.”

Nếu Ordering trả 20 đơn mới nhất rồi BFF gọi Payment/Shipping để lọc, có thể chỉ 3 đơn đáp ứng điều kiện. Nhưng phía sau còn hàng trăm đơn cũ hơn cũng đáp ứng. Phản hồi “3 đơn” không hẳn là trang đầu đúng nghĩa, và `totalCount` thường sẽ sai.

Tương tự, nếu sort theo `paidAt` mà dữ liệu này nằm ở Payment, lấy một trang theo `createdAt` của Ordering trước rồi sort lại sẽ không tạo thứ tự toàn cục đúng.

### 12.2. Những lựa chọn có thể cân nhắc

1. **Read projection có index phù hợp:** chứa `orderId`, `paidAt`, `deliveredAt`, `customerId` và các khóa lọc đã công bố; query một mô hình đọc tối ưu.
2. **Search index:** phù hợp truy vấn nhiều filter/full text nhưng cần chấp nhận độ trễ cập nhật và kế hoạch rebuild.
3. **Analytics warehouse:** phù hợp các báo cáo scan/aggregation lớn, không nhất thiết dùng cho traffic request thời gian thực.
4. **Query service chuyên dụng:** nhận trách nhiệm phục vụ use case với contract ổn định và cơ chế đọc được phép, không tự truy vấn DB nội bộ service khác.
5. **Composition với tập nhỏ:** nếu caller đã có danh sách rất nhỏ xác định rõ và không cần tổng số hoặc phân trang toàn cục, ghép trực tiếp có thể chấp nhận.

### 12.3. Keyset pagination và dữ liệu động

Khi dữ liệu liên tục đổi, offset pagination có thể làm bản ghi bị lặp hoặc bỏ sót giữa các trang. Keyset/cursor pagination có thể giảm một số vấn đề và cải thiện hiệu năng, nhưng khi sort/filter liên miền và projection đang cập nhật vẫn cần chính sách consistency, mốc đọc hoặc cách xử lý cursor.

Không dùng một cursor được tạo ở Ordering rồi giả định nó cũng định nghĩa thứ tự trên trạng thái Payment nếu hai domain chưa thống nhất ý nghĩa.

## 13. Độ nhất quán của một màn hình tổng hợp

Một màn hình ghép dữ liệu từ nhiều service thường không phải “ảnh chụp tại cùng một thời điểm”. Xét:

```text
T0: Order = CONFIRMED
T1: Payment = CAPTURED
T2: Shipping = IN_TRANSIT

Request bắt đầu gần T1, gọi các service với độ trễ khác nhau.
```

Response có thể chứa `orderStatus=CONFIRMED`, `paymentStatus=CAPTURED`, `shippingStatus=CREATED`. Đây có thể là trạng thái hợp lệ trong một hành trình đang chuyển tiếp.

Để hiểu kết quả cần xác định:

- Mỗi field là “giá trị hiện tại khi service đích xử lý” hay một snapshot?
- Có metadata `asOf`, `lastUpdatedAt`, version hoặc watermark không?
- Có cần **read-your-writes**, tức người vừa thao tác thấy ngay cập nhật của chính mình?
- Có thể trả PENDING khi dữ liệu chưa hội tụ không?
- Có business invariant nào không được suy luận từ trạng thái của nhiều service chưa đồng bộ?

### 13.1. Read-your-writes khi dùng projection

Sau khi người dùng hủy đơn, query từ projection có thể vẫn hiển thị CONFIRMED trong một khoảng ngắn. Một số cách xử lý:

- Trả trạng thái `CANCELLATION_REQUESTED` hoặc result token từ command.
- Client giữ trạng thái optimistic có nhãn “đang xử lý” khi phù hợp.
- BFF hỏi trực tiếp Ordering cho chính đơn vừa thay đổi trong một khoảng chuyển tiếp.
- Dùng version/watermark để chờ projection bắt kịp **trong giới hạn deadline**.
- Thể hiện rõ sự chậm hội tụ nếu quá deadline.

Không cố tạo read-your-writes bằng cách chờ vô hạn hoặc coi projection đã cập nhật khi chưa có bằng chứng.

### 13.2. Consistent snapshot qua nhiều service là yêu cầu khác

Nếu báo cáo kiểm toán yêu cầu dữ liệu tại thời điểm đóng sổ, có thể cần một cơ chế batch/snapshot theo watermark hoặc transaction boundary được thiết kế riêng. Gọi nhiều GET đồng bộ trong vài mili giây không bảo đảm dữ liệu được chụp cùng một thời điểm toàn cục.

## 14. Quyền truy cập và bảo vệ thông tin liên dịch vụ

Khi tổng hợp dữ liệu, quyền cần được đánh giá theo use case và ranh giới service.

### 14.1. Không dùng service account toàn quyền để bỏ qua authorization

Một BFF có thể gọi Payment bằng danh tính máy. Nhưng nó vẫn phải bảo đảm người dùng được phép xem payment tương ứng với đơn của mình. Một service account mạnh không chứng minh end-user có quyền.

Có thể cần kết hợp:

- End-user identity / delegated claims.
- Resource-level authorization ở owner.
- Scope/audience của access token.
- Kiểm tra quan hệ giữa `orderId` và `customerId`.
- Audit log cho truy vấn dữ liệu nhạy cảm.

### 14.2. Cache isolation

Với query cá nhân hóa:

```text
Cache key nguy hiểm:
  "order-overview:ORD-1042"

Cache key cần xét:
  tenant + authorized subject / access policy
  + orderId + relevant representation version
```

Không phải lúc nào cũng đặt user ID vào mọi cache key; điều quan trọng là chính sách cache phải bảo đảm dữ liệu không được chia cho chủ thể không có quyền, và việc thu hồi quyền được xử lý theo yêu cầu.

### 14.3. Projection sao chép dữ liệu làm tăng bề mặt bảo mật

Một read projection có tên, email, địa chỉ, số tiền và lịch sử giao hàng của nhiều bounded context có thể nhạy cảm hơn từng nguồn riêng. Cần phân loại PII, thời hạn lưu, mã hóa, masking, kiểm soát quyền query, quyền quản trị, backup và cách xử lý yêu cầu xóa/giới hạn dữ liệu.

Không đưa toàn bộ entity lên broker hoặc warehouse chỉ để tiện JOIN. Tập trường công bố phải có lý do và quyền sử dụng rõ.

## 15. API Gateway, BFF và GraphQL có giúp giải quyết bài toán không?

**API Gateway** thường tập trung vào routing, auth, rate limiting và các chính sách biên. **BFF** có thể cung cấp API phù hợp với một màn hình hoặc loại client. **GraphQL** cho phép client khai báo tập trường cần truy vấn, nhưng bản thân GraphQL không tự giải quyết data ownership, N+1, timeout hoặc nhất quán.

Ví dụ:

```graphql
query OrderOverview($id: ID!) {
  order(id: $id) {
    id
    status
    payment { status }
    shipment { trackingCode status }
  }
}
```

Nếu resolver của `payment` và `shipment` gọi riêng service tương ứng cho mỗi order, GraphQL chỉ thay đổi **hình dạng API**, còn fan-out vẫn có thể rất lớn. DataLoader/batching, caching, concurrency limits và permission checks vẫn cần thiết.

**Chọn BFF hoặc GraphQL khi nó phù hợp với trải nghiệm và hợp đồng client**, không vì kỳ vọng nó biến một truy vấn liên dịch vụ thành một transaction nhất quán.

### 15.1. Chống tạo “god aggregator”

Một aggregator có thể dần biết mọi bảng, enum và quy tắc business của mọi domain. Khi đó nó trở thành monolith điều phối mọi thay đổi, và mỗi service phải đồng bộ với nó.

Để tránh:

- BFF sở hữu **presentation/query contract**, không sở hữu invariant của Payment hay Inventory.
- Gọi các API công khai có ý nghĩa, không truy vấn thẳng bảng.
- Dùng DTO riêng cho view, mapping rõ từ contract.
- Tách endpoint theo use case khi hợp lý, không xây `GET /all-data` vô hạn.
- Đưa logic tính toán authoritative về đúng domain owner.

## 16. Case study A: trang chi tiết đơn hàng

### 16.1. Xác định nhu cầu

Người dùng xem đơn `ORD-1042`. Cần thông tin cốt lõi về đơn, trạng thái thanh toán, giao hàng; ảnh sản phẩm là yếu tố phụ trợ.

Bảng yêu cầu:

| Phần | Owner | Required? | Freshness | Gợi ý |
| --- | --- | --- | --- | --- |
| Order header/items | Ordering | Có | Current/snapshot theo contract | Gọi Ordering |
| Payment status | Payment | Có với nghiệp vụ cụ thể | Tương đối mới; không được bịa | Gọi Payment hoặc projection có quy tắc rõ |
| Shipping status | Shipping | Có thể tùy chọn ở view | Chấp nhận trễ ngắn | API/cache/projection |
| Product images | Catalog | Không | Có thể cache | Batch API/cache |

Nếu số downstream nhỏ, API composition ở BFF có thể là cách khởi đầu.

### 16.2. Luồng minh họa

```text
Client GET /orders/ORD-1042/overview
          |
          v
       OrderBFF
          |
          +-- call Ordering (required)
          +-- call Payment (required per contract)
          +-- call Shipping (optional)
          '-- call Catalog batch (optional)
          |
          +-- combine with deadline
          |
          v
       Response
```

Ví dụ response:

```json
{
  "order": {"id": "ORD-1042", "status": "CONFIRMED"},
  "payment": {"status": "CAPTURED", "available": true},
  "shipment": {"available": false, "reason": "TIMEOUT"},
  "productDisplay": {"available": true},
  "partial": true
}
```

BFF không coi `shipment.available=false` là “đơn chưa giao”; nó nói rõ dữ liệu vận chuyển chưa sẵn sàng. Contract phải xác định khi nào được trả HTTP 200 với `partial=true`, khi nào phải trả lỗi.

### 16.3. Khi lượng truy vấn tăng

Nếu 10 triệu lượt xem mỗi ngày đều gọi bốn service, cần đo QPS, latency, cache hit, downstream saturation và số lần request cần dữ liệu thực sự mới. Có thể chuyển một phần sang projection/caching mà không thay đổi ý nghĩa nghiệp vụ của API.

## 17. Case study B: màn hình danh sách đơn có filter xuyên miền

Yêu cầu nhân viên vận hành:

> “Cho tôi 50 đơn đặt trong tuần này, đã thu tiền, giao thất bại, sắp xếp theo thời gian thu tiền giảm dần.”

Thông tin nằm ở Ordering, Payment và Shipping. Nếu Ordering tự lấy 50 đơn rồi BFF lọc theo Payment/Shipping, có thể không tìm được đúng 50 kết quả cũng như tổng số.

Ở đây cần một query model có thể filter/sort trên các trường đã đồng bộ:

```text
Ordering event ----+
Payment event  ----+--> OperationsOrderIndex
Shipping event ----+       |
                           v
               GET /operations/orders
                 ?payment=CAPTURED
                 &delivery=FAILED
                 &sort=-paidAt
                 &limit=50
```

Cần quy định độ trễ index, cách phát hiện lag và cơ chế cập nhật/tái dựng. Nếu vận hành cần quyết định hoàn tiền từ một record đã chọn, hành động phải được validate lại ở Payment/Ordering theo invariant của họ.

**Dấu hiệu chọn projection:** filter/sort/pagination phụ thuộc nhiều nguồn, kết quả cần đúng ở quy mô lớn và truy vấn lặp lại thường xuyên.

## 18. Case study C: checkout và dữ liệu đọc trước khi command

Khách đặt hàng cần biết giá và khả năng giữ hàng. Client có thể đọc:

```text
Catalog: tên sản phẩm
Pricing: giá hiển thị
Inventory: chỉ báo sẵn bán
```

Nhưng thông tin “còn hàng” trên màn hình có thể cũ khi khách bấm xác nhận. Do đó không nên để BFF tự quyết định giữ hàng chỉ dựa trên lần đọc trước đó.

Luồng hợp lý có thể là:

1. Client hiển thị một bản dự kiến về giá và tồn kho.
2. Khi xác nhận, gửi **command** với idempotency key.
3. Owner của Pricing/Inventory thực hiện kiểm tra authoritative trong phần trách nhiệm của họ.
4. Workflow Ordering điều phối kết quả, có thể trả `CONFIRMED`, `PENDING` hoặc từ chối theo business rule.
5. Client đọc trạng thái cuối theo contract.

**Đọc liên dịch vụ để hỗ trợ quyết định của người dùng khác với cam kết rằng quyết định nghiệp vụ đã được bảo toàn.** Đừng tự làm hai thao tác GET + POST thành một transaction ảo.

## 19. Case study D: báo cáo doanh thu và dữ liệu lớn

Một dashboard tài chính cần tổng hợp đơn được xác nhận, tiền đã thu, hoàn tiền và phí. Nếu mỗi lần mở dashboard đều gọi Ordering, Payment và Refund trên hàng triệu bản ghi, hệ thống tạo tải lớn và khó đạt độ trễ phù hợp.

Một giải pháp có thể là:

- Producer phát integration events đã được định nghĩa với số tiền và thời điểm nghiệp vụ có ý nghĩa.
- Reporting pipeline ingest, kiểm tra trùng, xác định watermark và aggregate.
- Warehouse/OLAP store phục vụ truy vấn theo ngày, khu vực, sản phẩm hoặc thị trường.
- Có đối soát số liệu và chính sách chốt kỳ báo cáo.

**Không tự đồng nhất `OrderConfirmed` với doanh thu đã thu.** Payment capture, refund và accounting recognition có thể khác nhau. Ngay cả schema event đúng kiểu vẫn cần domain semantic để tính KPI đúng.

Báo cáo có thể cần dữ liệu “as of cuối ngày” thay vì “mọi nguồn vừa trả tại thời điểm request”. Đây là nhu cầu consistency khác với trang chi tiết đơn.

## 20. Quyết định phương án theo đặc tính truy vấn

| Đặc tính | API composition | Cache / snapshot | Read projection / CQRS | Analytics store |
| --- | --- | --- | --- | --- |
| Truy vấn một ID, vài nguồn | Thường phù hợp | Có thể hỗ trợ | Có thể chưa cần | Thường quá nặng |
| Đòi phản ánh dữ liệu nguồn gần thời điểm request | Có lợi nếu các nguồn đáp ứng | Phụ thuộc độ mới | Phụ thuộc lag | Thường không phù hợp |
| Nhiều filter/sort xuyên miền | Dễ phức tạp/sai phân trang | Hạn chế | Phù hợp | Phù hợp cho thống kê |
| Đọc nhiều và lặp lại | Fan-out tốn chi phí | Có lợi | Có lợi | Tùy workload |
| Query analytic khối lượng lớn | Thường không phù hợp | Hạn chế | Có thể | Thường phù hợp |
| Có thể chịu eventual consistency | Không bắt buộc | Có | Có | Có |
| Chi phí vận hành | Tương đối thấp lúc đầu | Cần invalidation | Cần event, replay, reconciliation | Cần pipeline, governance |
| Khả năng trả partial | Tự nhiên theo contract | Theo nguồn | Cần trạng thái lag/độ mới | Theo kỳ cập nhật |
| Độ sẵn sàng phụ thuộc runtime downstream | Cao khi mọi nhánh required | Có thể giảm | Có thể giảm | Giảm trên đường đọc trực tuyến |

Bảng không phải “luật chọn công nghệ”. Một hệ thống có thể dùng projection cho danh sách, API composition cho trang chi tiết, snapshot cho lịch sử đơn và warehouse cho dashboard. **Đừng chọn một phương án duy nhất cho tất cả truy vấn.**

## 21. Phác thảo một BFF tổng hợp có giới hạn

Ví dụ pseudo-Java, tập trung vào tư duy thiết kế:

```java
OrderOverview getOverview(String orderId, RequestContext ctx) {
    authorizeOrderRead(ctx.user(), orderId);

    Deadline deadline = ctx.deadline();

    CompletableFuture<Order> order = boundedAsync(
        "ordering",
        () -> orderClient.get(orderId, deadline.child(350))
    );

    CompletableFuture<PaymentView> payment = boundedAsync(
        "payment",
        () -> paymentClient.getByOrder(orderId, deadline.child(350))
    );

    CompletableFuture<ShipmentView> shipping = boundedAsync(
        "shipping",
        () -> shippingClient.getByOrder(orderId, deadline.child(200))
    );

    // Hai nhánh cốt lõi; lỗi được xử lý theo contract.
    Order o = awaitRequired(order, deadline);
    PaymentView p = awaitRequired(payment, deadline);

    // Nhánh tùy chọn: lỗi có thể tạo partial response.
    Optional<ShipmentView> s = awaitOptional(shipping, deadline);

    return OrderOverview.from(o, p, s);
}
```

`Deadline`, `boundedAsync`, `awaitRequired` và `awaitOptional` chỉ là abstraction minh họa, không phải thư viện có sẵn hay code hoàn chỉnh. Triển khai thật phải giới hạn executor/queue, transport timeout, connection pool và đối chiếu quyền; `CompletableFuture.orTimeout` không tự dừng một HTTP request bên dưới.

Một lưu ý nữa: `authorizeOrderRead` trong BFF không nhất thiết thay thế resource-level authorization ở service đích. Nếu owner cần kiểm tra quyền cuối cùng, hãy đảm bảo context được truyền phù hợp.

## 22. Deadline, timeout và partial response trong truy vấn liên dịch vụ

Giả sử client cần phản hồi trong 900 ms, gateway/BFF dùng 100 ms cho auth/routing và cần 100 ms cho response. Ngân sách downstream còn tối đa khoảng 700 ms, chưa kể buffer khác.

Nếu một nhánh optional có p99 cao, không hợp lý để nó chặn phần cốt lõi tới hết deadline. Có thể cho nhánh đó budget riêng 200 ms rồi trả partial nếu không kịp.

Các câu hỏi bắt buộc:

- Request tổng có deadline không?
- Có truyền thời gian còn lại xuống mỗi downstream không?
- Nhánh required và optional được chờ khác nhau không?
- Khi timeout, có hủy/bỏ công việc còn lại khi có thể không?
- Có retry nhiều tầng gây khuếch đại request không?
- Client có hiểu trạng thái thiếu dữ liệu không?
- Với side effect, timeout có bị diễn giải sai thành “chưa thực hiện” không?

Một truy vấn đọc thuần có thể retry có giới hạn theo policy, nhưng vẫn cần tôn trọng deadline. Với command có tác dụng phụ trong cùng hành trình, idempotency và trạng thái không chắc chắn phải được thiết kế riêng.

## 23. Observability: nhận biết nhu cầu bằng số liệu, không chỉ code

Distributed tracing cho thấy một request đã gọi những service nào, bao nhiêu lần, chờ ở đâu. Metrics giúp nhận diện truy vấn tổng hợp thật sự trở thành bottleneck.

### 23.1. Các chỉ số nên theo dõi

| Nhóm | Chỉ số hữu ích |
| --- | --- |
| Request tổng hợp | QPS, p50/p95/p99 latency, success rate |
| Fan-out | Số outbound calls/request, fan-out depth, số downstream khác nhau |
| Dependency | Latency và error rate theo service/method |
| Bounded concurrency | In-flight requests, queue depth, rejections, pool wait |
| Degradation | Partial-response rate, fallback rate, số nhánh thiếu |
| Cache | Hit ratio, miss rate, staleness, invalidation lag |
| Projection | Consumer lag, update latency, event age, rebuild progress |
| Truy vấn | Rows examined, query time, index usage, page size |
| Nghiệp vụ | Tỷ lệ mismatch, trạng thái UNKNOWN, tác động của dữ liệu stale |
| Bảo mật | Unauthorized access attempts, anomalous broad queries, cross-tenant rejects |

Các metrics phải được gắn nhãn có giới hạn cardinality; không đưa raw `orderId` hoặc PII vào label có cardinality lớn.

### 23.2. Trace mẫu

```text
GET /orders/ORD-1042/overview  520 ms
    Auth                         35 ms
    BFF Compose                 450 ms
       Ordering.getOrder        140 ms
       Payment.getByOrder       430 ms
       Shipping.getByOrder      210 ms
    Serialize                   35 ms
```

Các span thể hiện Payment là nhánh chậm nhất trên critical path. Nhưng một trace không đủ kết luận kiến trúc sai; cần xem tần suất, phân bố latency, mức độ bắt buộc của nhánh và yêu cầu use case. Có thể chỉ cần tối ưu Payment endpoint, thêm cache đúng chỗ hoặc tách phần Payment thành widget tải sau—không nhất thiết xây event-driven projection ngay.

## 24. Những sai lầm kiến trúc thường gặp

### 24.1. Mỗi service đọc trực tiếp database của service khác

Làm như vậy có thể tạo cross-schema coupling, phá ownership, khó nâng version và khó bảo vệ quyền. Query model dùng chung có thể hợp lệ khi đó là **hệ thống đọc được sở hữu và vận hành rõ**, không phải lời mời cho các service tự cập nhật bảng của nhau.

### 24.2. Dùng mọi API GET để quyết định command

Hai bước `GET inventory` rồi `POST reserve` có một cửa sổ cạnh tranh. Nếu có nhiều khách cùng đặt, dữ liệu đọc có thể cũ ngay sau khi nhận. Bất biến giữ hàng phải được thực thi tại owner, bằng cơ chế đồng thời và transaction phù hợp.

### 24.3. Lấy trang trước, lọc/sort theo service khác sau

Kết quả có thể thiếu, sai thứ tự và sai tổng số. Khi filter xuyên miền ở quy mô lớn, phải xem một projection/index được thiết kế cho query.

### 24.4. Gọi N+1 rồi tăng thread pool

Song song hóa có thể giảm latency của một request nhưng làm tăng in-flight load và saturation. Cần giảm số calls bằng batch, cache hoặc projection trước khi chỉ tăng concurrency.

### 24.5. Dùng cache không rõ độ mới và không tách tenant

Cache giúp nhanh hơn nhưng có thể trả dữ liệu sai quyền hoặc tạo quyết định sai. Cache key, freshness, invalidation và authorization phải là phần thiết kế.

### 24.6. Dùng event stream như bản sao toàn bộ entity

Phát nguyên domain entity/ORM object làm consumer phụ thuộc schema nội bộ, tăng payload và phơi bày dữ liệu. Nên dùng integration event hoặc state transfer được thiết kế có chủ đích.

### 24.7. Coi read model là nhất quán tức thời

Eventual consistency có nghĩa có khoảng trễ và có thể nhận event trùng/sai thứ tự. Đừng dùng projection trễ làm chứng cứ cuối cùng cho thao tác nhạy cảm.

### 24.8. BFF tự làm business rule của mọi domain

BFF đọc Payment và Inventory rồi tự phê duyệt giao dịch, bỏ qua owner. Điều này tạo một nguồn logic thứ hai, dễ khác phiên bản và làm sai bất biến.

### 24.9. Coi GraphQL tự loại bỏ N+1

GraphQL giúp client chọn trường nhưng resolver có thể tạo đúng dạng N+1 như REST. Cần batching/limits và thiết kế nguồn đọc đúng.

### 24.10. Không phân biệt “không có dữ liệu” và “không đọc được dữ liệu”

Trả `paymentStatus=UNPAID` vì Payment timeout gây hiểu sai nghiệp vụ. `NOT_FOUND`, `UNAVAILABLE`, `PENDING` và `UNKNOWN` có ý nghĩa khác nhau, cần được xác định trong contract.

### 24.11. Tạo read projection khi chưa đo tải

Projection mang chi phí event contract, consumer, lag, backup và rebuild. Với một màn hình nhỏ, ít traffic và hai nguồn ổn định, API composition có thể đơn giản và phù hợp hơn.

## 25. Checklist nhận diện trước khi thiết kế giải pháp

Hãy tạo một **query requirement card** cho mỗi use case có dấu hiệu cần nhiều nguồn:

| Thuộc tính | Câu hỏi cần ghi |
| --- | --- |
| Business question | Người dùng thật sự muốn biết hoặc quyết định điều gì? |
| Consumer | Web, mobile, backoffice, batch, partner hay service khác? |
| Data fields | Trường nào bắt buộc; trường nào tùy chọn? |
| Data owners | Ai sở hữu từng field và nghĩa của nó? |
| Join keys | Có business ID ổn định và quyền liên hệ dữ liệu không? |
| Consistency | Cần ảnh chụp thống nhất, read-your-writes hay eventual consistency? |
| Freshness | Dữ liệu cũ tối đa bao lâu được chấp nhận? |
| Scale | Một ID, danh sách nhỏ, hàng triệu record hay aggregate? |
| Query shape | Filter/sort/page theo trường của những owner nào? |
| Latency & availability | SLO p95/p99, yêu cầu phần nào bắt buộc? |
| Failure behavior | Khi một nguồn lỗi, trả partial, cache hay fail? |
| Authorization | Ai được xem dữ liệu; có multi-tenant không? |
| Operations | Ai sở hữu, giám sát và sửa projection/BFF? |
| Evolution | Hợp đồng và schema thay đổi độc lập ra sao? |

Sau khi điền đầy đủ, viết một câu quyết định:

> “Use case **[X]** cần đọc dữ liệu từ **[A, B, C]**, để phục vụ **[hiển thị/ra quyết định/báo cáo]**, với mức độ mới **[T]**, độ trễ **[SLO]** và phép lọc **[F]**; vì vậy chúng tôi chọn **[API composition/batch/projection/warehouse]** và xử lý lỗi theo **[contract]**.”

Nếu chưa thể trả lời, tranh luận REST hay Kafka, GraphQL hay CQRS thường đang đi trước vấn đề thực tế.

## 26. Quy trình quyết định theo từng bước

1. **Tìm hiểu use case** bằng lời của người dùng, không theo endpoint đã tồn tại.
2. **Liệt kê field cần xuất hiện** và tách required/optional.
3. **Xác định service owner** cho từng field, không suy từ bảng hiện có.
4. **Định nghĩa business keys** để liên kết dữ liệu mà không lộ cấu trúc lưu trữ.
5. **Phân loại query:** single-entity, list, cross-filter, analytics, command prerequisite.
6. **Ghi yêu cầu freshness/consistency** bằng tiêu chí có thể kiểm chứng.
7. **Đặt SLO và failure semantics:** khi thiếu nguồn, kết quả nào còn đúng?
8. **Ước lượng fan-out và cardinality:** outbound calls, rows, payload, QPS.
9. **Chọn giải pháp đơn giản nhất:** composition hoặc batch trước khi thêm projection nếu đủ.
10. **Nếu cần projection:** định nghĩa event contract, lag budget, dedup, replay, rebuild, auth và đối soát.
11. **Kiểm chứng bằng load/failure test:** latency, error, partial, cache staleness, downstream saturation.
12. **Quan sát và điều chỉnh:** thay đổi workload hoặc UX có thể làm lựa chọn ban đầu không còn phù hợp.

Không bắt buộc đi hết tất cả bước bằng một tài liệu lớn. Một trang thiết kế đủ rõ và số liệu đo đáng tin cậy thường giá trị hơn một sơ đồ microservices phức tạp không gắn với nhu cầu cụ thể.

## 27. Bài tập thực hành

Một nền tảng thương mại có các service: Catalog, Pricing, Ordering, Payment, Inventory, Shipping, Notification và Analytics.

Hãy phân loại sáu nhu cầu:

**A. Trang chi tiết đơn:** lấy đơn, trạng thái thanh toán, giao hàng, ảnh sản phẩm. Dữ liệu trạng thái quan trọng cần có, ảnh có thể thiếu.

**B. Tìm kiếm sản phẩm:** lọc hàng nghìn sản phẩm theo tên, khoảng giá, tình trạng hàng, sắp xếp giá tăng dần và phân trang 20 sản phẩm.

**C. Màn hình checkout:** hiển thị tổng giá ước tính và khả năng đặt, sau đó cần xác nhận giữ hàng và thanh toán khi khách bấm đặt.

**D. Dashboard doanh thu:** thống kê doanh thu đã thu, hoàn tiền và số đơn theo ngày, với độ trễ cập nhật cho phép 15 phút.

**E. Danh sách đơn gần đây:** hiển thị 10 đơn và trạng thái vận chuyển; số lượt truy cập rất thấp.

**F. Backoffice:** tìm 50 đơn đã thanh toán, giao thất bại, sắp xếp theo `paidAt` và có tổng số kết quả đúng.

Với từng trường hợp, hãy trả lời:

1. Field nào thuộc về service nào?
2. Có business key nào ghép dữ liệu an toàn không?
3. Query là hiển thị, phân tích hay tiền đề của command?
4. Cần độ mới bao nhiêu? Có chấp nhận eventual consistency không?
5. Có filter/sort/pagination xuyên domain không?
6. Cần API composition, batch, projection, warehouse hay một workflow command khác?
7. Khi một dependency lỗi, có thể trả partial hay phải ngừng?
8. Làm sao tránh N+1, data leak và trạng thái nghiệp vụ giả?
9. Cần metrics nào để chứng minh giải pháp đáp ứng SLO?
10. Khi schema/event version thay đổi, consumer có vẫn đọc được dữ liệu cũ không?

### Định hướng thảo luận

- **A:** API composition/BFF có thể phù hợp lúc đầu; optional image có thể cache hoặc trả partial.
- **B:** Tìm kiếm xuyên Catalog/Pricing/Inventory ở quy mô lớn gợi ý search index/read model, với quy tắc cập nhật và độ mới rõ.
- **C:** Việc đọc dữ liệu chỉ hỗ trợ hiển thị; bước xác nhận là command cần invariant, không đơn thuần là ghép GET.
- **D:** Reporting pipeline/warehouse và watermark phù hợp hơn việc fan-out hàng triệu request đồng bộ.
- **E:** Một BFF nhỏ hoặc batch API có thể đủ; không cần projection khi chưa có bằng chứng.
- **F:** Filter/sort/pagination xuyên miền là dấu hiệu mạnh cho một projection/index chuyên dụng.

Đây không phải đáp án duy nhất. Cần biện minh dựa trên contract nghiệp vụ, cardinality, độ mới và vận hành.

## 28. Kết luận

**Nhận diện nhu cầu đọc liên dịch vụ** là bước xác định chính xác một use case cần những thông tin gì, do ai sở hữu, theo thời điểm nào và với hợp đồng lỗi nào. Đó là công việc đi trước quyết định về API Gateway, GraphQL, CQRS, Kafka, cache hoặc database.

Một truy vấn một ID qua vài service có thể bắt đầu bằng **API composition** và batch calls. Một danh sách có filter/sort/pagination xuyên miền có thể cần **read projection hoặc search index**. Một dashboard phân tích khối lượng lớn có thể cần **reporting store/warehouse**. Một thao tác giữ hàng hoặc thu tiền phải dựa vào **quy trình command và invariant authoritative**, không thể an toàn chỉ nhờ kết hợp dữ liệu đọc.

Điều quan trọng là bảo vệ ranh giới sở hữu, tránh N+1, công bố mức độ mới và trạng thái thiếu dữ liệu, giữ quyền truy cập đúng, cùng khả năng đo lường và sửa sai lệch. **Kiến trúc đọc tốt không gom tất cả dữ liệu vào một nơi bằng mọi giá; nó cung cấp đúng góc nhìn cần thiết với mức nhất quán, chi phí và độ tin cậy phù hợp cho từng use case.**
