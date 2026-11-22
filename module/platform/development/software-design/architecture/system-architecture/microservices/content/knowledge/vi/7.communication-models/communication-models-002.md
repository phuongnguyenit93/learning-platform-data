# Giao tiếp đồng bộ, bất đồng bộ và các phương án kết hợp trong Microservices

## Mục tiêu học tập

Khi ứng dụng được chia thành các microservice, một nghiệp vụ không còn là một chuỗi hàm trong cùng tiến trình. Order có thể cần dữ liệu từ Catalog, kết quả giữ hàng từ Inventory, xác nhận thanh toán từ Payment và thông báo từ Notification. Mỗi ranh giới làm xuất hiện độ trễ mạng, lỗi truyền thông, thay đổi hợp đồng và câu hỏi về thời điểm hoàn thành.

Bài học tập trung vào ba lựa chọn:

- **Giao tiếp đồng bộ (synchronous):** Bên gọi chờ phản hồi để quyết định bước tiếp theo trong cùng luồng xử lý.
- **Giao tiếp bất đồng bộ (asynchronous):** Bên gửi có thể chấp nhận hoặc phát công việc trước; việc xử lý và kết quả diễn ra sau, qua queue, event, callback hay trạng thái lưu trữ.
- **Phương án kết hợp (hybrid):** Chọn đồng bộ hoặc bất đồng bộ cho từng đoạn nghiệp vụ theo điều kiện thời gian, tính đúng đắn, khả năng chịu lỗi và nhu cầu người dùng.

Sau bài học, người học có thể:

1. Phân biệt **synchronous/asynchronous** với **blocking/non-blocking**, và phân biệt **query**, **command**, **event** với kiểu transport.
2. Lựa chọn HTTP/REST, gRPC, queue hoặc event bus dựa trên nhu cầu cụ thể thay vì công nghệ phổ biến.
3. Phân tích ảnh hưởng của mỗi mô hình đến **latency, temporal coupling, availability, backpressure, consistency** và vận hành.
4. Thiết kế hợp đồng API/event có idempotency, schema, correlation, lỗi và trạng thái rõ ràng.
5. Sử dụng những mô hình lai phổ biến: **sync acceptance + async processing**, **async events + sync read model**, **saga**, **request–reply qua broker**, và **fan-out song song có phản hồi từng phần**.
6. Giải thích khi nào timeout, retry, message trùng, event lệch thứ tự hoặc consumer chậm làm sai trạng thái nghiệp vụ.
7. Vẽ luồng Order–Inventory–Payment, thử các failure path và chứng minh kết quả cuối cùng.

**Nguyên tắc:** “Dùng Kafka” không tự tạo event-driven architecture đúng nghĩa; “dùng REST” cũng không mặc nhiên tạo coupling sai. Kiến trúc được xác định bởi **ngữ nghĩa nghiệp vụ và hợp đồng**, còn transport là phương tiện triển khai.

## 1. Bối cảnh: gọi qua mạng khác gọi hàm nội bộ

Một lời gọi nội bộ có thể kết thúc bằng kết quả hoặc exception trong cùng tiến trình. Khi Order gọi Inventory qua mạng, một timeout có thể xảy ra ở nhiều thời điểm:

- Request chưa được gửi hoặc chưa đến Inventory.
- Inventory đã nhận request nhưng đang xếp hàng.
- Inventory đã bắt đầu xử lý.
- Inventory đã commit reservation nhưng phản hồi bị chậm.
- Inventory đã gửi response nhưng một proxy hoặc đường mạng làm mất kết quả.
- Order hết deadline và ngừng chờ, còn Inventory vẫn tiếp tục.

Do đó **không nhận được response không chứng minh thao tác chưa thực thi**. Đặc điểm này ảnh hưởng cả request–response lẫn messaging. Một lệnh gửi lại hoặc một event giao lại có thể kích hoạt side effect trùng nếu không có idempotency.

Trước khi chọn cơ chế giao tiếp, cần trả lời:

- Ai là **chủ sở hữu quyết định nghiệp vụ** và dữ liệu nguồn sự thật?
- Người dùng cần kết quả **ngay trong request hiện tại** hay chỉ cần biết yêu cầu được tiếp nhận?
- Điều gì được coi là **hoàn thành**, điều gì chỉ là **đang xử lý**?
- Nếu bên nhận lỗi hoặc phản hồi muộn, bên gửi thực hiện gì?
- Có thể chấp nhận **eventual consistency** trong bao lâu?
- Có cần nhiều consumer độc lập nhận cùng một sự kiện?
- Hệ thống theo dõi và phục hồi operation đang PENDING bằng cách nào?

## 2. Ba trục khái niệm cần tách bạch

### 2.1. Synchronous và asynchronous

**Synchronous communication** thể hiện quan hệ thời gian trong một tương tác: bên gọi cần chờ phản hồi để tiếp tục. Ví dụ Order gọi Inventory và đợi kết quả ReserveInventory trước khi trả trạng thái đơn.

**Asynchronous communication** cho phép bên gửi tiếp tục sau khi đã giao công việc hoặc công bố một sự kiện, còn bên nhận xử lý và báo kết quả sau. Ví dụ Order lưu PENDING, gửi ReserveInventory vào queue, rồi trả orderId để người dùng theo dõi.

Một HTTP POST trả **202 Accepted** là request–response đồng bộ ở tầng tiếp nhận, nhưng **nghiệp vụ bên trong** có thể hoàn thành bất đồng bộ. Phải nói rõ tầng đang xét để không nhầm “server đã nhận việc” với “nghiệp vụ thành công”.

### 2.2. Blocking và non-blocking

**Blocking** mô tả tài nguyên thực thi bị giữ trong lúc chờ; **non-blocking** mô tả cách sử dụng tài nguyên/I/O không giữ thread chỉ để đợi.

- REST với reactive/non-blocking HTTP client có thể vẫn là **nghiệp vụ đồng bộ** nếu Order phải nhận kết quả Inventory trước khi trả response.
- Worker lấy message từ queue có thể dùng **blocking database call**, dù giao tiếp giữa producer và worker là bất đồng bộ.
- Virtual thread giúp giảm chi phí chờ trong nhiều tình huống, nhưng không loại bỏ temporal coupling giữa service.

Không chọn đồng bộ/bất đồng bộ chỉ vì framework hỗ trợ CompletableFuture, reactive streams, coroutine hay virtual thread. Đó là công cụ hiện thực, không phải hợp đồng nghiệp vụ.

### 2.3. Query, command và event

| Kiểu thông điệp | Ý nghĩa | Ví dụ | Trách nhiệm |
|---|---|---|---|
| Query | Hỏi dữ liệu hoặc trạng thái | GetAvailability | Owner trả dữ liệu đúng hợp đồng |
| Command | Yêu cầu bên sở hữu thực hiện hành động | ReserveInventory | Bên nhận quyết định chấp nhận/từ chối |
| Event | Thông báo sự thật nghiệp vụ đã xảy ra | InventoryReserved | Producer sở hữu sự thật đã công bố |
| Request–reply | Yêu cầu và nhận kết quả tương quan | GetPrice → PriceResult | Hai bên có reply contract |
| Notification | Báo thay đổi hoặc kết quả | OrderConfirmed webhook | Có quy tắc gửi, nhận và retry |

**OrderCreated** diễn đạt một sự kiện đã xảy ra. **ReserveInventory** diễn đạt ý định yêu cầu Inventory thực hiện thao tác. Nếu Order công bố OrderCreated rồi ngầm giả định Inventory đã giữ hàng thành công, hệ thống đang thiếu hợp đồng quyết định và trạng thái rõ ràng.

## 3. Đồng bộ request–response

### 3.1. Luồng cơ bản

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Order API
    participant I as Inventory API
    U->>O: GET /orders/preview?sku=X
    O->>I: GET /inventory/availability?sku=X
    I-->>O: available=true
    O-->>U: Preview hiện tại
~~~

Trong ví dụ này, người dùng cần biết tồn kho để hiển thị. Query đồng bộ có thể phù hợp nếu Inventory đáp ứng deadline. Tuy vậy, **kết quả xem trước không phải quyền giữ hàng**; trước khi cam kết bán, Inventory vẫn phải xác nhận invariant theo dữ liệu hiện tại.

### 3.2. Ưu điểm

- Luồng điều khiển rõ: gửi yêu cầu, chờ, nhận kết quả hoặc lỗi.
- Phù hợp với query và quyết định mà người dùng cần ngay.
- HTTP/REST và gRPC có công cụ hỗ trợ contract, test, tracing và vận hành phong phú.
- Dễ biểu diễn lỗi trong cùng request bằng status code, error body, deadline.
- Giảm số thành phần phải quản lý khi không có nhu cầu queue hay event fan-out.

### 3.3. Giới hạn

**Temporal coupling:** Bên gọi phụ thuộc việc bên nhận phản hồi vào đúng thời điểm yêu cầu. Nếu Inventory lỗi, yêu cầu của Order có thể lỗi theo.

**Tail latency:** Độ trễ tổng thường chịu ảnh hưởng lớn của dependency chậm nhất hoặc tổng các hop tuần tự. Một dịch vụ p99 chậm có thể kéo toàn bộ user journey chậm.

**Tài nguyên:** Connection, thread (nếu blocking), connection pool và concurrency slot bị sử dụng trong lúc chờ. Nhiều request đang chờ có thể tạo hiệu ứng dây chuyền.

**Failure propagation:** Timeout và retry không giới hạn có thể biến sự cố một dependency thành bão tải trên nhiều tầng.

**Không có distributed ACID tự động:** Việc gọi Inventory rồi Payment qua HTTP không làm transaction của hai database trở thành một transaction nguyên tử.

### 3.4. REST và gRPC

**REST/HTTP** thích hợp cho public API, truy vấn tài nguyên, gateway, browser và tích hợp phổ biến. Có thể dùng JSON hay định dạng khác; cần quy định status, pagination, error và caching semantics.

**gRPC** thích hợp cho nhiều tương tác giữa service, hợp đồng schema rõ, deadline và một số kiểu streaming. Nó cũng đòi chiến lược compatibility, timeout, load balancing và tracing. gRPC không giải quyết bản chất của coupling nếu business flow vẫn gọi quá nhiều service nối tiếp.

REST và gRPC đều có blocking/non-blocking clients. Không nên suy luận transport sẽ tự xử lý idempotency, authorization hay lỗi kết quả mơ hồ.

### 3.5. Khi nên chọn đồng bộ

- Kết quả cần thiết để quyết định trong cùng màn hình hoặc request.
- Tác vụ có duration dự đoán được trong overall deadline.
- Dependency có SLO và phương án suy giảm hợp lý.
- Lỗi nghiệp vụ và lỗi kỹ thuật có thể phân biệt.
- Không cần buffer công việc kéo dài hoặc fan-out đến nhiều consumer.
- Đã có cơ chế khi server thành công nhưng client timeout.

**Ví dụ phù hợp:** GetProductDetail, GetAvailabilityPreview, ValidateCoupon, lấy tỉ giá hiện tại từ một owner tin cậy. Tùy domain, một command ngắn cũng có thể dùng đồng bộ.

## 4. Bất đồng bộ qua queue và event

### 4.1. Command qua queue

Order ghi PENDING rồi gửi ReserveInventory để consumer xử lý sau:

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Order
    participant B as Broker
    participant I as Inventory
    U->>O: POST /orders
    O->>O: Commit PENDING + outbox
    O-->>U: 202 + orderId
    O->>B: ReserveInventory
    B->>I: ReserveInventory
    I->>I: Ghi reservation theo invariant
    I->>B: InventoryReserved / InventoryRejected
    B->>O: Kết quả
    O->>O: Cập nhật Order
    U->>O: GET /orders/{id}
    O-->>U: Trạng thái mới nhất
~~~

Lợi ích chính là Order không bắt buộc đợi Inventory hoàn tất trước khi xác nhận **đã nhận yêu cầu**. Nhưng việc queue nhận message và việc Inventory giữ hàng thành công là hai mốc khác nhau.

### 4.2. Event-driven publish–subscribe

Một sự kiện **OrderConfirmed** được công bố, nhiều consumer có thể phản ứng:

~~~mermaid
flowchart LR
    O["Order"] --> B["OrderConfirmed"]
    B --> N["Notification"]
    B --> A["Analytics"]
    B --> L["Loyalty"]
~~~

Order không cần biết Notification đang chạy ở đâu. Notification có thể retry gửi email khi SMTP lỗi, Analytics có thể cập nhật báo cáo chậm hơn, Loyalty áp dụng điểm thưởng theo hợp đồng của nó.

Tuy nhiên OrderConfirmed đã được publish **không chứng minh Notification gửi email xong**, cũng không chứng minh Analytics đã cập nhật. Consumer có thể lag, lỗi hoặc nhận trùng.

### 4.3. Ưu điểm

- **Decoupling theo thời gian:** Producer có thể giao việc cho broker/queue bền vững khi consumer chưa sẵn sàng.
- **Buffer burst:** Queue hấp thụ một phần đỉnh tải trong giới hạn năng lực, retention và dung lượng.
- **Fan-out:** Thêm consumer độc lập dựa trên contract mà producer không phải gọi từng consumer đồng bộ.
- **Xử lý dài:** Phù hợp với tạo báo cáo, xử lý hình ảnh, xác nhận thanh toán kéo dài, thông báo.
- **Read projection:** Consumer có thể xây view phục vụ truy vấn, không cần fan-out mọi lần đọc.

### 4.4. Giới hạn

- **Eventual consistency:** Các view khác nhau có thể không cập nhật cùng lúc.
- **Duplicate/out-of-order messages:** Cần idempotent handler, version, ordering hoặc state transition guard.
- **Khó theo dõi:** Request ban đầu có thể kết thúc trước khi lỗi xảy ra; cần state machine, correlation ID, logs/traces và cảnh báo.
- **Broker/queue cũng có sự cố:** Consumer lag, partition, retention, ACL, publish failure và khả năng replay phải được vận hành.
- **Không có transaction xuyên các bên:** DB commit, broker delivery và tác dụng ở payment provider là những ranh giới độc lập.
- **Hợp đồng event tồn tại lâu dài:** Đổi nghĩa trường hoặc cấu trúc payload có thể phá consumer cũ.

### 4.5. Khi nên chọn bất đồng bộ

- User chấp nhận PENDING và nhận kết quả sau.
- Tác vụ có duration biến động, cần xử lý theo batch hoặc hàng đợi.
- Producer không cần consumer online ngay tại thời điểm gửi.
- Nhiều consumer cần phản ứng độc lập với cùng sự kiện.
- Có nhu cầu hấp thụ burst, giới hạn concurrency hoặc chống overload.
- Dữ liệu có thể nhất quán cuối cùng và có cách đối soát khi chậm.

## 5. Bảng so sánh lựa chọn

| Tiêu chí | Đồng bộ | Bất đồng bộ |
|---|---|---|
| Mốc trả kết quả | Trong lời gọi đang chờ | Qua event, callback, status hay message sau đó |
| Dependency online cùng lúc | Thường cần phản hồi kịp thời | Broker có thể nhận khi consumer offline, tùy mức bền vững |
| Tác động lên UX | Thích hợp kết quả tức thời | Cần PENDING, progress, polling hoặc notification |
| Latency nhìn từ client | Gồm thời gian dependency | Acceptance có thể nhanh, completion có thể chậm |
| Backpressure | Rate limit, concurrency limit, circuit breaker | Queue depth, consumer capacity, lag, admission control |
| Data consistency | Response không biến nhiều DB thành ACID | Thường cần eventual consistency và state machine |
| Duplicate requests | Retry timeout có thể tạo side effect trùng | Broker redelivery/retry có thể giao lặp |
| Quan sát | Trace request thường dễ theo hơn | Cần correlation xuyên message và thời gian |
| Thay đổi contract | API schema và error semantics | Event schema, consumer compatibility |
| Failure handling | Timeout, retry, fallback, degradation | Delayed retry, DLQ, replay, reconciliation |
| Runtime | HTTP/gRPC client, discovery, gateway | Broker, consumer group, retention, outbox |
| Phù hợp | Query và quyết định tức thời | Workflow dài, fan-out, tác vụ nền |

Không có cột nào “đúng hơn” ở mọi trường hợp. Có thể dùng cùng một giao thức trong nhiều kịch bản, nhưng hợp đồng nghiệp vụ và thời hạn quyết định cách áp dụng.

## 6. Phương án kết hợp: nhận yêu cầu đồng bộ, xử lý nền bất đồng bộ

Đây là một thiết kế thường gặp trong Microservices:

1. Client gọi POST.
2. Order xác thực, kiểm tra điều kiện cục bộ và **lưu bền vững** operation ở trạng thái PENDING.
3. Order đồng thời ghi outbox/job cùng transaction cục bộ để bảo đảm có thể tiếp tục.
4. Order trả 202 Accepted, operationId và statusUrl.
5. Worker/broker phối hợp Inventory, Payment.
6. Client polling, SSE/WebSocket hoặc nhận notification để biết trạng thái cuối.

~~~http
POST /orders
Content-Type: application/json
Idempotency-Key: checkout-O-101-v1

{
  "customerId": "C-7",
  "items": [{"sku": "SKU-8", "quantity": 2}]
}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /orders/O-101
Content-Type: application/json

{
  "orderId": "O-101",
  "status": "PENDING",
  "statusUrl": "/orders/O-101"
}
~~~

**Quan trọng:** 202 Accepted chỉ có nghĩa hệ thống đã nhận công việc theo contract. Không được hiển thị “Đặt hàng thành công” nếu Inventory hoặc Payment còn có thể từ chối.

Một anti-pattern nghiêm trọng là trả 202 trước khi ghi được dữ liệu/job bền vững, sau đó chạy background task in-memory. Khi process restart, công việc có thể mất dù client đã nhận Accepted.

### Các cách trả tiến độ

| Cơ chế | Đặc điểm | Rủi ro cần xử lý |
|---|---|---|
| GET polling | Client hỏi trạng thái định kỳ | Tần suất quá cao, thừa request, cần backoff |
| Server-Sent Events | Server đẩy cập nhật một chiều | Reconnect, last-event-id, trạng thái nguồn |
| WebSocket | Kênh hai chiều | Kết nối lâu, reconnect, auth, scale |
| Webhook | Server gửi callback tới server khác | Xác thực/ký, retry, replay và idempotency |
| Broker event | Consumer nội bộ subscribe | Quyền topic, delivery, lag, DLQ |

Nếu browser dùng SSE hoặc WebSocket để nhận tiến độ, nên có một API đọc lại **trạng thái chuẩn** sau reconnect. Việc bỏ lỡ một update giao diện không được làm mất sự thật nghiệp vụ.

## 7. Phương án kết hợp: cập nhật read model bằng event, đọc đồng bộ

Trang “Chi tiết đơn” cần Order, Payment, Catalog. Có thể gọi cả ba service đồng bộ, nhưng mỗi lần mở trang sẽ chịu latency và availability của tất cả. Một read model tổng hợp là phương án khác:

~~~mermaid
flowchart LR
    O["Order"] -->|OrderUpdated| B["Event Bus"]
    P["Payment"] -->|PaymentUpdated| B
    C["Catalog"] -->|ProductChanged| B
    B --> R["Order Read Model"]
    U["UI"] -->|GET /orders/{id}/view| Q["Query API"]
    Q --> R
~~~

Trong mô hình này, **việc cập nhật view là bất đồng bộ**, còn **lời gọi đọc view là đồng bộ**. Lợi ích:

- Không phải fan-out đến nhiều service cho mỗi query.
- View tối ưu theo nhu cầu hiển thị và chỉ mục truy vấn.
- Producer vẫn sở hữu dữ liệu nguồn sự thật.
- Giảm temporal coupling trong đường đọc.

Điều kiện:

- Phải chấp nhận read model có thể trễ.
- Phải theo dõi consumer lag và độ mới dữ liệu.
- Phải xử lý event trùng, event đến muộn/sai thứ tự.
- Cần cách rebuild read model nếu state bị lỗi.
- Không dùng projection stale để thực hiện invariant cốt lõi nếu chưa có cơ chế xác thực tại owner.

**CQRS** có thể tách mô hình đọc/ghi, nhưng không bắt buộc dùng event sourcing. **Event sourcing** lưu chuỗi event như nguồn sự thật và là một quyết định sâu hơn về storage, replay và evolution.

## 8. Phương án kết hợp: đồng bộ cho quyết định cục bộ, bất đồng bộ cho workflow

Trong một nghiệp vụ đặt hàng, mỗi service vẫn cần transaction cục bộ để giữ invariant, trong khi các service phối hợp qua command và event:

- Inventory giữ hàng và bảo đảm quy tắc không vượt số lượng khả dụng.
- Payment quản lý đúng một logical charge và kết quả giao dịch.
- Order điều phối quy trình đặt hàng, trạng thái PENDING/CONFIRMED/CANCELLED.
- Notification gửi email sau khi đơn được xác nhận.

### Saga có điều phối

~~~mermaid
stateDiagram-v2
    [*] --> ORDER_PENDING
    ORDER_PENDING --> INVENTORY_RESERVED: InventoryReserved
    ORDER_PENDING --> REJECTED: InventoryRejected
    INVENTORY_RESERVED --> PAYMENT_PENDING: AuthorizePayment
    PAYMENT_PENDING --> CONFIRMED: PaymentAuthorized
    PAYMENT_PENDING --> RELEASE_PENDING: PaymentRejected
    RELEASE_PENDING --> CANCELLED: InventoryReleased
    CONFIRMED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
~~~

Saga không phải một transaction ACID xuyên service. Một bước đã commit phải được xử lý bằng **compensation nghiệp vụ** nếu cần đảo hậu quả. Ví dụ Payment từ chối sau khi Inventory đã giữ hàng thì Order yêu cầu ReleaseInventory. Nếu Release thất bại, phải giữ trạng thái RELEASE_PENDING hoặc tương đương, rồi retry/đối soát; không tuyên bố đã hủy thành công chỉ vì gửi lệnh.

### Choreography và orchestration

| Khía cạnh | Choreography | Orchestration |
|---|---|---|
| Cách phối hợp | Consumer phản ứng với event | Coordinator điều hành các bước |
| Luồng ngắn | Ít thành phần điều phối | Có thể tăng độ phức tạp không cần thiết |
| Luồng dài, nhiều bù trừ | Dễ thiếu một nơi thấy toàn bộ flow | Có state machine và ownership rõ hơn |
| Coupling | Producer không cần biết consumer; vẫn có coupling semantic event | Coordinator biết contract và flow |
| Failure handling | Cần correlating events xuyên nhiều consumer | Cần lưu coordinator state, retry, compensation |
| Rủi ro | Event chain ngầm, vòng sự kiện | Coordinator trở thành nơi chứa quá nhiều domain logic |

Không bắt buộc chọn một trong hai tuyệt đối. Có thể dùng orchestrator cho quy trình đặt hàng, đồng thời dùng choreography cho Analytics/Notification. Trách nhiệm domain vẫn thuộc các owner tương ứng.

### Đồng bộ một bước, bất đồng bộ bước khác

Nếu Inventory luôn có thể xác nhận giữ hàng trong deadline ngắn, Order có thể gọi ReserveInventory đồng bộ, rồi xử lý Payment bất đồng bộ. Hoặc ngược lại, một số authorization phải được quyết định ngay trước khi phát event.

Mô hình đúng phụ thuộc việc **người dùng cần biết gì ngay** và **invariant nào phải thỏa trước khi cam kết kết quả**, không phụ thuộc mong muốn “mọi service đều dùng queue”.

## 9. Phương án kết hợp: request–reply qua message broker

Một hệ thống có thể gửi request qua broker và nhận reply trên topic/queue khác, tương quan bằng correlationId:

~~~json
{
  "messageId": "REQ-101",
  "correlationId": "CORR-O-101",
  "type": "GetRiskDecision",
  "replyTo": "order.risk.reply",
  "payload": {"orderId": "O-101"}
}
~~~

Reply:

~~~json
{
  "messageId": "REP-102",
  "correlationId": "CORR-O-101",
  "type": "RiskDecisionCompleted",
  "payload": {"decision": "APPROVED"}
}
~~~

Order cần giữ mapping giữa pending request và correlationId, timeout, xử lý reply lặp hoặc reply đến sau deadline.

**Đặt request–reply trên broker không tự loại bỏ temporal coupling.** Nếu Order vẫn block để chờ reply Risk trong 500 ms thì business flow vẫn cần Risk phản hồi kịp thời. Broker có thể giúp buffering hoặc routing, nhưng thêm queue lag, latency và vận hành. Không nên dùng broker request–reply chỉ để thay thế HTTP theo khẩu hiệu.

## 10. Phương án kết hợp: fan-out song song và trả từng phần

Một BFF cần thông tin Catalog, Ratings, Recommendation để xây màn hình sản phẩm:

~~~mermaid
flowchart TD
    U["UI"] --> B["BFF"]
    B --> C["Catalog"]
    B --> R["Ratings"]
    B --> M["Recommendations"]
    C --> B
    R --> B
    M --> B
    B --> U
~~~

Nếu các query độc lập, gọi song song có thể giảm thời gian chờ so với tuần tự. Song song không xóa latency, mà chuyển hạn chế sang **nhánh chậm nhất**, tăng concurrency và đòi quản lý cancel/deadline.

Nếu Catalog là dữ liệu bắt buộc còn Recommendation tùy chọn, BFF có thể trả thông tin Catalog khi Recommendation timeout. Hợp đồng response cần phân biệt **không có recommendation** với **không tải được recommendation**.

Đặt câu hỏi:

- Nhánh nào bắt buộc, nhánh nào tùy chọn?
- Overall deadline là bao nhiêu?
- Nếu client cancel thì các nhánh chưa xong có được dừng?
- Có thể trả partial response hoặc stream kết quả không?
- Mỗi nhánh retry bao nhiêu lần và ai sở hữu policy?
- Khi một nhánh chậm, tài nguyên của các nhánh khác có bị giữ quá lâu không?

Hybrid không nhất thiết phải có message broker. Có thể kết hợp sync fan-out, async logging, cache và event projection tùy nhu cầu.

## 11. Timeout, deadline, retry và cancellation trong mô hình đồng bộ

Với ba service gọi nối tiếp, không nên đặt timeout 2 giây cho mỗi service rồi tin request người dùng luôn hoàn thành trong 2 giây. Cần **overall deadline** và tính phần thời gian còn lại.

Ví dụ minh họa với ngân sách 2.000 ms:

| Đoạn xử lý | Budget |
|---|---:|
| Validate và xử lý cục bộ | 150 ms |
| Inventory | 450 ms |
| Payment | 900 ms |
| Lưu trạng thái/response | 150 ms |
| Dự phòng network và queue | 350 ms |
| **Tổng** | **2.000 ms** |

Đây chỉ là ví dụ định hướng. Giá trị thực tế phải dựa trên SLO, latency p95/p99, tải và điều kiện nghiệp vụ. Khi chuyển sang bước tiếp theo, hệ thống cần trừ elapsed time, không cấp lại toàn bộ budget.

**Retry** chỉ có ích với lỗi tạm thời và thao tác có thể lặp an toàn. Cần max attempts, backoff, jitter, retry budget và một tầng chịu trách nhiệm rõ. Nếu client, gateway và service đều retry ba lần, một request có thể nhân thành nhiều attempts ngoài ý định.

**Idempotency** đặc biệt quan trọng với POST tạo payment hoặc giữ hàng. Cùng logical operation cần dùng cùng idempotency key; server phải kiểm tra uniqueness, payload fingerprint và kết quả đã lưu, không chỉ nhìn header rồi bỏ qua.

**Cancellation** là tín hiệu người gọi không muốn tiếp tục đợi hoặc làm việc. Nó không chứng minh remote service đã dừng hay transaction đã rollback. Hủy một reservation/charge đã commit cần transition hoặc compensation nghiệp vụ có hợp đồng riêng.

## 12. Delivery semantics trong giao tiếp bất đồng bộ

### 12.1. At-most-once, at-least-once và exactly-once

**At-most-once:** Message có thể mất, không tự giao lại trong phạm vi cam kết.

**At-least-once:** Message được nỗ lực giao đủ, có thể được giao lại. Consumer phải chịu được duplicate.

**Exactly-once:** Một số nền tảng có thể cung cấp cơ chế xử lý đúng một lần trong phạm vi transaction hoặc luồng cụ thể. Không tự mở rộng sang side effect tại database ngoài, email provider hay payment gateway.

Vì vậy cần thiết kế **idempotent business effect**, không chỉ kỳ vọng broker không giao trùng.

### 12.2. EventId, operationId và idempotency

Ví dụ:

~~~json
{
  "eventId": "EVT-501",
  "eventType": "InventoryReserved",
  "schemaVersion": 1,
  "aggregateId": "O-101",
  "aggregateVersion": 3,
  "correlationId": "CORR-O-101",
  "causationId": "CMD-481",
  "occurredAt": "2026-11-11T09:00:00Z",
  "payload": {
    "orderId": "O-101",
    "reservationId": "RES-501"
  }
}
~~~

- **eventId:** Chống xử lý trùng một event cụ thể.
- **aggregateId:** Danh tính domain dùng cho phân vùng hoặc tương quan.
- **aggregateVersion:** Phát hiện event cũ hoặc không theo thứ tự.
- **correlationId:** Nối các bước của cùng luồng nghiệp vụ.
- **causationId:** Chỉ ra message hoặc thao tác gây nên event.
- **operationId/idempotency key:** Giúp ngăn cùng một logical charge/reservation bị thực hiện nhiều lần, kể cả khi dùng nhiều messageId khác nhau.

Consumer có thể lưu processedEventId trong transaction cập nhật trạng thái. Nếu cùng event được giao lại, trả kết quả đã xử lý hoặc bỏ qua side effect; business operation vẫn phải có guard riêng.

### 12.3. Thứ tự event

Giả sử projection nhận:

~~~text
OrderConfirmed (version 4)
OrderCancelled (version 5)
~~~

Nếu phiên bản 5 đến trước phiên bản 4, projection không được cập nhật ngược từ CANCELLED thành CONFIRMED chỉ vì xử lý muộn. Có thể dùng aggregateVersion, state transition guard, partition key theo aggregate và cơ chế xử lý sequence gap.

Không mặc định broker có total ordering toàn hệ thống. Nhiều nền tảng chỉ bảo đảm thứ tự trong phạm vi partition/key hoặc không bảo đảm thứ tự theo cách ứng dụng đang cần.

### 12.4. Retry, dead-letter queue và replay

Consumer có thể lỗi do database chậm (transient) hoặc payload sai schema (permanent). Retry vô hạn một poison message làm tắc xử lý.

Cần phân loại lỗi, retry có giới hạn/backoff, đưa message không thể xử lý vào DLQ, cảnh báo owner và có runbook replay sau khi sửa nguyên nhân. Khi replay, vẫn phải idempotent.

**Message vào DLQ không đồng nghĩa business operation đã FAILED cuối.** State owner cần biết tình trạng và đối soát để người dùng không nhìn thấy PENDING vĩnh viễn.

### 12.5. Backpressure

Nếu producer phát 12.000 message/giây nhưng consumer xử lý 2.000/giây, backlog tăng thêm 10.000/giây. Queue chỉ **đệm** tải, không tạo capacity vô hạn.

Cần theo dõi queue depth, oldest message age, consumer lag, processing time, DLQ count, retention, storage và bottleneck tại database/external API. Có thể giới hạn producer, tăng consumer, batching hoặc concurrency limit tùy thực tế.

## 13. Transactional outbox để tránh mất công việc

Một rủi ro:

~~~text
1. Order commit Order(PENDING) vào database.
2. Order publish ReserveInventory lên broker.
~~~

Nếu process chết giữa bước 1 và 2, đơn đã lưu nhưng không có command để xử lý tiếp. Nếu publish trước DB commit, event có thể xuất hiện dù business transaction sau đó rollback.

**Transactional outbox** ghi cùng transaction cục bộ:

~~~text
BEGIN TRANSACTION
  INSERT order(orderId, status = PENDING)
  INSERT outbox(eventId, type, payload, status = NEW)
COMMIT

Relay:
  đọc các outbox chưa phát
  publish tới broker
  ghi nhận trạng thái phát
~~~

Nếu relay publish thành công rồi crash trước khi đánh dấu delivered, event có thể được phát lần nữa. Vì vậy consumer vẫn cần idempotency. Outbox cải thiện độ tin cậy giữa business commit và việc công bố, không tạo một distributed ACID transaction toàn hệ thống.

Relay có thể polling outbox hoặc dùng CDC. CDC là cơ chế chuyển thay đổi đã commit, không thay thế việc định nghĩa event schema, ownership và xử lý trùng.

Một **inbox/processed-message table** ở consumer giúp kết hợp dedup và cập nhật business state trong cùng transaction cục bộ. Với external payment provider, cần thêm idempotency key do provider hỗ trợ và reconciliation.

## 14. Contract cho API và event

### 14.1. Hợp đồng đồng bộ

~~~http
POST /inventory/reservations
Idempotency-Key: order-O-101-reserve-v1
Content-Type: application/json

{
  "orderId": "O-101",
  "items": [{"sku": "SKU-8", "quantity": 2}]
}
~~~

Response minh họa:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "reservationId": "RES-501",
  "status": "RESERVED",
  "expiresAt": "2026-11-11T09:15:00Z"
}
~~~

Hợp đồng cần xác định:

- Request này hoàn thành thao tác thật hay mới tiếp nhận xử lý?
- Kết quả từ chối nghiệp vụ có mã/trạng thái gì?
- Khi timeout, có thể truy vấn reservation theo orderId/idempotency key không?
- Key idempotency có phạm vi và thời hạn thế nào?
- Có thể rollback hoặc release reservation theo điều kiện nào?
- Thay đổi schema có tương thích với consumer còn chạy phiên bản cũ không?

### 14.2. Hợp đồng event

Một event cần chủ sở hữu semantic rõ, thường có eventType, schemaVersion, eventId, aggregateId, occurredAt và payload. Nếu workflow cần ordering/correlation thì bổ sung aggregateVersion, correlationId, causationId.

**Tương thích về cấu trúc không đồng nghĩa tương thích về ý nghĩa.** Nếu InventoryReserved từng có nghĩa “đã giữ hàng”, rồi bị đổi ngầm thành “đã nhận yêu cầu giữ hàng”, consumer cũ có thể xác nhận đơn sai dù JSON schema không đổi.

Các nguyên tắc:

- Không tùy tiện đổi nghĩa trường đã công bố.
- Bổ sung trường theo chính sách backward/forward compatibility.
- Có giai đoạn deprecate/migration cho breaking changes.
- Dùng contract test và schema compatibility checks.
- Consumer phải chịu được message từ producer/consumer khác version trong phạm vi hỗ trợ.
- Replay event cũ phải được thiết kế theo hợp đồng version và retention.

## 15. Sở hữu dữ liệu và ngữ nghĩa nghiệp vụ quyết định giao tiếp

Trong mô hình Order–Inventory–Payment:

| Context | Sở hữu | Không nên làm |
|---|---|---|
| Order | Vòng đời đơn, state machine, điều phối quy trình | Tự ghi stock hoặc transaction của Payment |
| Inventory | Tồn kho khả dụng, reservation, release | Cho service khác cập nhật bảng stock trực tiếp |
| Payment | Payment intent, giao dịch, đối soát, hoàn tiền | Để Order tự sửa bảng payment |
| Notification | Gửi thông báo, retry và trạng thái gửi | Quyết định OrderConfirmed theo lỗi SMTP |

Giao tiếp tốt thực hiện qua contract owner công bố. Nếu mọi service đều đọc/ghi một bảng chung, việc dùng event bus không tự tạo business autonomy. Tương tự, mỗi service có container và DB riêng cũng không bảo đảm mô hình nghiệp vụ được phân ranh phù hợp.

## 16. Quy trình mẫu hoàn chỉnh Order–Inventory–Payment

### 16.1. Yêu cầu

- UI nhận được operationId nhanh.
- Inventory quyết định việc giữ hàng.
- Payment không thu tiền trùng cùng logical attempt.
- Nếu Payment bị từ chối sau khi đã giữ hàng, Inventory phải giải phóng reservation.
- Notification có thể chậm mà không làm OrderConfirmed mất hiệu lực.
- Người dùng tra cứu trạng thái cuối và các trạng thái chưa rõ.

### 16.2. Happy path

~~~mermaid
sequenceDiagram
    participant U as User
    participant O as Order
    participant B as Broker
    participant I as Inventory
    participant P as Payment
    participant N as Notification
    U->>O: POST /orders + Idempotency-Key
    O->>O: Commit PENDING + outbox
    O-->>U: 202 + orderId
    O->>B: ReserveInventory
    B->>I: ReserveInventory
    I->>I: Commit reservation
    I->>B: InventoryReserved
    B->>O: InventoryReserved
    O->>B: AuthorizePayment
    B->>P: AuthorizePayment
    P->>P: Commit idempotent result
    P->>B: PaymentAuthorized
    B->>O: PaymentAuthorized
    O->>O: Commit CONFIRMED + outbox
    O->>B: OrderConfirmed
    B->>N: OrderConfirmed
    N->>N: Gửi thông báo và retry riêng
    U->>O: GET /orders/{id}
    O-->>U: CONFIRMED
~~~

**Các đoạn sync:** POST tiếp nhận và GET trạng thái.

**Các đoạn async:** ReserveInventory command, InventoryReserved event, AuthorizePayment command, PaymentAuthorized event, OrderConfirmed event.

**Các transaction cục bộ:** Từng service cập nhật dữ liệu do chính nó sở hữu; không có distributed transaction toàn bộ flow.

### 16.3. Inventory hết hàng

~~~text
PENDING
  -> ReserveInventory
  -> InventoryRejected(reason=OUT_OF_STOCK)
  -> REJECTED
~~~

Order không phát AuthorizePayment khi chưa đáp ứng điều kiện giữ hàng.

### 16.4. Payment bị từ chối

~~~text
INVENTORY_RESERVED
  -> AuthorizePayment
  -> PaymentRejected
  -> ReleaseInventory
  -> InventoryReleased
  -> CANCELLED
~~~

Nếu ReleaseInventory lỗi, Order chuyển **COMPENSATION_PENDING** và đối soát. Không kết luận CANCELLED khi compensation chưa hoàn tất theo contract.

### 16.5. Payment thành công nhưng response/event bị mất

Payment có thể đã commit hoặc provider đã charge trong khi Order vẫn thấy PAYMENT_PENDING. Recovery cần dùng cùng operationId/idempotency key, event replay hoặc query Payment theo transaction reference. Không phát charge mới với key khác khi chưa xác định kết quả.

### 16.6. Notification thất bại

Khi Order đã CONFIRMED, lỗi gửi email thường không được biến đơn thành thất bại. Notification sở hữu retry, DLQ, alert và trạng thái gửi; Order vẫn giữ business state đã xác nhận.

### 16.7. Trạng thái gợi ý

| State | Ý nghĩa |
|---|---|
| PENDING | Yêu cầu đã được lưu và đang xử lý |
| INVENTORY_PENDING | Đang đợi kết quả giữ hàng |
| PAYMENT_PENDING | Đang đợi kết quả Payment |
| CONFIRMED | Đã đáp ứng điều kiện xác nhận đơn |
| REJECTED | Điều kiện nghiệp vụ không đáp ứng |
| COMPENSATION_PENDING | Đang hoàn tác bước đã commit |
| CANCELLED | Quy trình hủy hợp lệ hoàn thành |
| REVIEW_REQUIRED | Kết quả không rõ, cần đối soát |

Tên trạng thái phụ thuộc domain, nhưng không nên che giấu trạng thái trung gian chỉ để UI có hai nhãn SUCCESS/FAILED. Khi kết quả không rõ, hệ thống phải công bố đúng sự thật hiện tại.

## 17. Một số mẫu code/pseudocode

### 17.1. Query đồng bộ qua port

~~~java
public interface InventoryQueryPort {
    Availability getAvailability(String sku, Duration deadline);
}

// Pseudocode của application service:
Availability a = inventoryQuery.getAvailability(
        "SKU-8", Duration.ofMillis(300)
);
return a.canSell(2) ? Preview.available() : Preview.unavailable();
~~~

Các kiểu Availability và Preview là ví dụ domain do ứng dụng tự định nghĩa. Query xem trước không được coi là bằng chứng reservation đã commit.

### 17.2. Tiếp nhận async và outbox

~~~text
submitOrder(command):
    validate command
    transaction:
        existing = findByIdempotencyKey(command.key)
        if existing exists:
            return existing.orderId and status
        order = createOrder(PENDING)
        insertOutbox(ReserveInventory, order.id, stableMessageId)
    return Accepted(order.id, statusUrl)
~~~

Bản ghi công việc phải được lưu bền vững **trước** khi trả Accepted.

### 17.3. Consumer idempotent

~~~text
on PaymentAuthorized(event):
    transaction:
        if event.id already processed:
            return
        order = loadOrder(event.orderId)
        if order.status == PAYMENT_PENDING:
            order.transition(CONFIRMED)
            insertOutbox(OrderConfirmed)
        else:
            reconcile unexpected transition
        mark event.id processed
~~~

Không cập nhật trạng thái vô điều kiện khi nhận event; cần transition hợp lệ và bảo vệ event trùng/đến muộn.

### 17.4. GET status

~~~http
GET /orders/O-101

HTTP/1.1 200 OK
Content-Type: application/json

{
  "orderId": "O-101",
  "status": "PAYMENT_PENDING",
  "lastUpdatedAt": "2026-11-11T09:02:00Z"
}
~~~

Nếu dùng WebSocket/SSE để đẩy trạng thái, client vẫn cần cách đồng bộ lại từ GET khi kết nối bị ngắt hoặc bỏ lỡ update.

## 18. Observability: theo dõi cả acceptance và completion

Trong mô hình sync, một trace request có thể thấy hầu hết đường đi đang chờ. Với async, operation có thể kéo dài qua hàng chục message và process restart. Cần nối **business operation ID** với **technical trace/correlation**.

- **traceId:** Liên kết span trong distributed tracing; async có thể dùng propagation hoặc span links.
- **correlationId:** Liên kết các message của cùng luồng nghiệp vụ.
- **causationId:** Chỉ ra thao tác gây ra message hiện tại.
- **operationId/orderId:** Định danh ổn định cho người dùng và đối soát.
- **eventId/messageId:** Nhận diện message phục vụ dedup/tracking.
- **attempt:** Lần thử thứ mấy để đo retry amplification.

Không dùng orderId/customerId làm label metric cardinality cao; log/trace có kiểm soát là nơi thích hợp hơn. Không log token hoặc dữ liệu nhạy cảm.

### Các chỉ số cần đo

| Chỉ số | Mục đích |
|---|---|
| API p50/p95/p99 latency | Độ trễ của lời gọi sync |
| Timeout/error rate | Lỗi mạng, dependency và deadline |
| In-flight requests/connections | Mức tài nguyên chờ |
| Retry attempts và retry budget | Có khuếch đại tải khi lỗi không? |
| Queue depth và oldest message age | Consumer có đang tụt lại không? |
| Consumer processing duration | Nút thắt của worker |
| DLQ count và replay count | Công việc không tự phục hồi |
| Accepted → Completed duration | Thời gian thật của business operation |
| Stuck operations | Số operation ở trạng thái trung gian quá ngưỡng |
| Compensation/reconciliation rate | Lỗi quy trình phân tán và hiệu quả phục hồi |
| End-to-end success rate | Kết quả nghiệp vụ thực tế |

Nếu POST /orders trả 202 trong 50 ms nhưng chỉ 70% đơn hoàn thành trong 5 phút, không thể coi trải nghiệm đã tốt dựa trên API response latency. Cần SLO tách biệt **acceptance** và **business completion**.

## 19. Bảo mật trong mô hình giao tiếp

**Sync API:** Xác thực caller/service, authorization theo tài nguyên, TLS, rate limit, payload validation, deadline và quyền gọi API nội bộ. Không tin mọi header forwarded chỉ vì request đi qua gateway.

**Async messaging:** Xác định ACL topic/queue, danh tính producer/consumer, giới hạn payload và dữ liệu nhạy cảm, retention/replay policies. Message trong DLQ có thể tồn tại lâu; cần quyền truy cập phù hợp.

**Webhook:** Xác thực nguồn gửi bằng chữ ký hoặc cơ chế phù hợp; kiểm tra tính mới/chống replay và idempotent consumer. Callback đến từ bên ngoài không nên tự động có quyền thay đổi mọi domain state.

**Hybrid status/cancel API:** POST tạo operation, GET trạng thái và lệnh cancel phải kiểm tra cùng phạm vi authorization. Không được cho người dùng A đọc hoặc hủy operation của người dùng B chỉ vì đoán được operationId.

## 20. Những anti-pattern cần tránh

1. **Chuỗi gọi sync quá sâu:** Client → Gateway → Order → Inventory → Pricing → Promotion → Payment. Availability và latency dễ phụ thuộc dây chuyền. Rà soát boundary, read model, song song hoặc async hậu xử lý.
2. **Publish event rồi chờ mọi consumer:** Event bus chỉ thay transport, temporal coupling vẫn còn nếu producer buộc đợi Notification/Analytics trước khi trả.
3. **Dùng event thay command không rõ owner:** OrderCreated không tự có nghĩa Inventory phải giữ hàng và Payment phải thu tiền; cần workflow contract.
4. **Trả 200/201 khi mới enqueue:** Người dùng hiểu nhầm đã hoàn tất. Dùng 202 và trạng thái khi mới Accepted.
5. **Fire-and-forget trong process:** Trả Accepted rồi chạy thread không lưu job; restart có thể mất việc.
6. **Retry POST với key mới:** Gây double payment/duplicate reservation khi lần đầu đã commit nhưng response mất.
7. **Tin broker giao đúng một lần sẽ đảm bảo side effect đúng một lần:** Consumer vẫn cần idempotency ở business boundary.
8. **Event chứa toàn bộ schema nội bộ:** Consumer phụ thuộc producer implementation và breaking changes trở nên thường xuyên.
9. **Không theo dõi queue lag/DLQ:** Công việc tồn đọng vô hạn nhưng API vẫn trả 202 nhanh.
10. **Mọi service đọc/ghi chung database:** Giao tiếp qua broker không có ý nghĩa tự chủ nếu business ownership và data ownership vẫn lẫn lộn.
11. **Request–reply qua queue nhưng chờ bằng blocking timeout ngắn:** Có broker nhưng không giảm temporal coupling; còn tăng hop và queue lag.
12. **Một timeout được hiểu là thất bại nghiệp vụ chắc chắn:** Phải đối soát vì side effect có thể đã xảy ra.
13. **Mọi thay đổi contract buộc release đồng thời:** Cần schema evolution, contract test và versioning.
14. **Lạm dụng async cho thao tác bắt buộc phản hồi ngay:** Tăng complexity mà không tăng giá trị; cân nhắc query sync.
15. **Tăng consumer vô hạn để giải quyết backlog:** Nút thắt có thể nằm ở DB hoặc external API; cần backpressure và capacity planning.

## 21. Ma trận chọn mô hình theo use case

| Use case | Cần biết ngay | Có thể xử lý sau | Phương án phù hợp |
|---|---|---|---|
| Xem chi tiết sản phẩm | Thông tin hiển thị | Analytics lượt xem | Sync query + async analytics |
| Xem tồn kho ước lượng | Giá trị hiện tại | Cập nhật projection | Sync query hoặc read model |
| Áp mã khuyến mãi | Hợp lệ và mức giảm | Thống kê áp mã | Sync decision + async telemetry |
| Tạo đơn có nhiều bước | Đã nhận orderId | Giữ hàng, thanh toán, thông báo | Sync acceptance + async saga |
| Thanh toán cần kết quả ngay | Kết quả authorization | Settlement/notification | Sync step nếu SLO đáp ứng + async hậu xử lý |
| Xuất báo cáo lớn | Đã tạo job | Tạo file, thông báo | Async job + GET status |
| Gửi email sau đặt hàng | Không cần trong request | Retry gửi email | Async event/queue |
| Trang tổng hợp đơn hàng | View để hiển thị | Đồng bộ dữ liệu nhiều domain | Async projection + sync query |
| Quy trình phê duyệt nhiều bước | Trạng thái yêu cầu hiện tại | Các bước phê duyệt | Async workflow + status |
| BFF lấy nhiều nội dung | Thông tin bắt buộc | Recommendation tùy chọn | Parallel sync + partial fallback |

Các lựa chọn là gợi ý; cần xác thực độ trễ, tính nhất quán và điều kiện nghiệp vụ trong từng hệ thống.

## 22. Bài thực hành: thiết kế hybrid flow và kiểm chứng lỗi

**Đề bài:** Thiết kế một hệ thống Order–Inventory–Payment–Notification. Inventory có thể phản hồi nhanh trong điều kiện thường, Payment đôi khi chờ xác nhận lâu, Notification có thể lỗi nhiều phút.

### Bước 1 — Viết hợp đồng trách nhiệm

Lập bảng:

- GetAvailabilityPreview: query, owner Inventory;
- CreateOrder: command, owner Order;
- ReserveInventory: command, owner Inventory;
- InventoryReserved/Rejected: event của Inventory;
- AuthorizePayment: command, owner Payment;
- PaymentAuthorized/Rejected: event của Payment;
- OrderConfirmed: event của Order;
- SendConfirmationEmail: công việc của Notification.

Xác định bước nào người dùng cần biết ngay và bước nào có thể chờ.

### Bước 2 — Vẽ ba sơ đồ

Vẽ một phiên bản tất cả sync HTTP, một phiên bản async hoàn toàn và một phiên bản hybrid. Nêu temporal coupling, consistency, nơi lưu business state và cách phục hồi cho mỗi phiên bản.

### Bước 3 — Thiết kế API và event

Tạo mẫu POST /orders, GET /orders/{id}, ReserveInventory và PaymentAuthorized. Ghi đủ idempotency key, correlationId, eventId, version, trạng thái và error semantics.

### Bước 4 — Thiết kế transaction/outbox

Viết pseudocode thể hiện Order(PENDING) và outbox được commit cùng transaction. Giải thích trường hợp relay publish lặp, consumer crash trước ACK, Payment hoàn tất nhưng Order chưa nhận event.

### Bước 5 — Tiêm lỗi

Mô phỏng:

1. Inventory trả hết hàng.
2. Payment commit rồi response/event thất lạc.
3. Broker không khả dụng.
4. Consumer nhận duplicate/out-of-order event.
5. Notification liên tục lỗi SMTP.
6. Người dùng gửi lại POST sau timeout.

Mỗi trường hợp phải có trạng thái cuối hợp lệ, không trùng business side effect và tín hiệu quan sát được.

### Bước 6 — Đo SLO

Theo dõi acceptance latency, time to complete, consumer lag, DLQ, retry count, compensation pending và số operation cần đối soát. Đề xuất ngưỡng theo nhu cầu thực tế.

### Bước 7 — Viết ADR

Ghi vì sao chọn sync, async hoặc hybrid cho từng interaction; nêu phương án thay thế, trade-off, rủi ro, cách rollback/replay, lý do dựa trên nghiệp vụ và điều kiện đánh giá lại.

**Sản phẩm thực hành:** Bảng chọn mô hình, hai hoặc ba sequence diagram, API/event contracts, state machine, outbox pseudocode, kết quả tiêm lỗi và một ADR có thể review.

## 23. Câu hỏi ôn tập

1. Synchronous communication khác blocking I/O ở điểm nào?
2. HTTP trả 202 Accepted là đồng bộ hay bất đồng bộ? Trả lời theo hai lớp: request và business workflow.
3. Khi nào GetAvailabilityPreview nên dùng sync HTTP, và khi nào cần read projection?
4. Vì sao event OrderCreated không đồng nghĩa Payment đã hoàn tất?
5. Một broker request–reply có thể vẫn có temporal coupling như thế nào?
6. Tại sao không nên nối chuỗi 6–7 dependency sync trên đường người dùng chờ?
7. Nếu Notification chết, nên để OrderConfirmed thất bại không? Phụ thuộc điều kiện nào?
8. Outbox giải quyết cửa sổ lỗi nào giữa DB commit và publish message?
9. Vì sao dùng outbox vẫn cần consumer idempotent?
10. Khi Order POST timeout nhưng Payment đã commit, cần idempotency và reconciliation ra sao?
11. Có thể dùng event-driven mà vẫn bị semantic coupling như thế nào?
12. Saga orchestration và choreography khác nhau ở cách sở hữu flow và compensation ra sao?
13. Khi nào nên dùng polling, SSE, WebSocket hay webhook để trả kết quả async?
14. Consumer nhận event version 5 rồi version 4, làm sao ngăn trạng thái quay ngược?
15. Tại sao queue depth thấp không đủ chứng minh completion SLO tốt?
16. Khi message vào DLQ, ai chịu trách nhiệm trạng thái nghiệp vụ?
17. Tại sao thay REST bằng broker không tự biến một transaction liên miền thành ACID?
18. Với BFF fan-out, dữ liệu nào có thể được trả partial khi một dependency timeout?
19. Làm sao đo lợi ích thật của hybrid so với chỉ đo thời gian POST trả 202?
20. Bạn sẽ dựa vào các tiêu chí gì để chọn transport cho một use case mới?

## 24. Checklist trước khi đưa mô hình giao tiếp vào vận hành

- [ ] Mỗi tương tác được phân loại query, command hoặc event với owner rõ.
- [ ] Phân biệt thời điểm **Accepted** và **BusinessCompleted**.
- [ ] Các bước bắt buộc phản hồi tức thời có deadline và SLO phù hợp.
- [ ] Quy trình async có operationId, state machine và cách tra cứu tiến độ.
- [ ] API có error contract, idempotency, timeout/retry policy rõ.
- [ ] Message có schema/version, eventId, correlationId và metadata cần thiết.
- [ ] Consumer chịu được duplicate, event đến muộn và out-of-order.
- [ ] Các ghi business state và công bố event có chiến lược outbox hoặc cơ chế bền vững tương đương.
- [ ] Retry có giới hạn, backoff, jitter và không khuếch đại tải vô hạn.
- [ ] Queue có lag/oldest-age metrics, DLQ và replay runbook.
- [ ] Workflow đa dịch vụ có compensation và reconciliation khi cần.
- [ ] UI không coi 202 là thành công cuối; timeout không bị coi là thất bại nghiệp vụ chắc chắn.
- [ ] Có SLO cho acceptance và end-to-end business completion.
- [ ] Auth/authz được áp dụng trên API, broker, webhook và status endpoints.
- [ ] Đã thử response mất sau commit, broker outage, duplicate event, consumer restart và compensation failure.
- [ ] Công cụ được chọn phục vụ yêu cầu nghiệp vụ, latency, consistency, throughput và chi phí vận hành.

**Kết luận:** Giao tiếp đồng bộ phù hợp khi cần kết quả đúng hạn để quyết định ngay. Bất đồng bộ phù hợp cho xử lý kéo dài, tích hợp qua sự kiện và hấp thụ tải bằng queue trong giới hạn. Trong hệ thống Microservices thực tế, **mô hình kết hợp** thường cho phép giữ trải nghiệm người dùng tốt mà vẫn tách được các công việc hậu xử lý và quy trình liên miền. Tính đúng đắn phụ thuộc vào contract, state machine, data ownership, idempotency, outbox, quan sát và đối soát xuyên các ranh giới dịch vụ.