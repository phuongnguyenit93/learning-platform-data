# Chọn giao thức theo độ trễ, tính nhất quán và mức liên kết

> Trong hệ thống microservices, REST, gRPC, message queue, publish/subscribe hay event streaming không có một lựa chọn “tốt nhất” cho mọi luồng. Cần chọn **kiểu tương tác và giao thức cụ thể theo yêu cầu nghiệp vụ**: người gọi cần kết quả sau bao lâu, dữ liệu phải nhất quán đến mức nào, các thành phần có cần cùng hoạt động tại một thời điểm hay không, và ai sở hữu quyết định cuối cùng.

Bài học tập trung vào cách ra quyết định khi thiết kế **mô hình giao tiếp giữa các dịch vụ**. Kỹ sư cần phân biệt yêu cầu mà giao thức hỗ trợ với đảm bảo thật sự của cả luồng nghiệp vụ: dùng message broker không tự tạo eventual consistency đúng, và dùng HTTP đồng bộ không tự tạo giao dịch nhất quán xuyên database.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **giao tiếp đồng bộ (synchronous request/response)**, **bất đồng bộ (asynchronous command/event/message)** và **streaming**.
2. Phân tích ba chiều quyết định: **độ trễ**, **tính nhất quán** và **mức liên kết (coupling)**.
3. Lựa chọn REST/HTTP, gRPC, message queue, publish/subscribe hoặc event stream theo từng use case, thay vì chọn đồng loạt cho toàn hệ thống.
4. Phân biệt tính nhất quán của **bất biến nghiệp vụ**, **transaction cục bộ**, **dữ liệu đọc dạng projection** và **quy trình xuyên dịch vụ**.
5. Thiết kế timeout, retry, idempotency, event schema, outbox, dead-letter handling và quan sát luồng phù hợp.
6. Giải thích các đánh đổi qua tình huống đặt hàng, giữ tồn kho, thanh toán, gửi thông báo và cập nhật báo cáo.

## 2. Ba câu hỏi nền tảng trước khi chọn công nghệ

Một sơ đồ microservices thường cho thấy các ô service và mũi tên trao đổi dữ liệu. Để biến sơ đồ thành quyết định kỹ thuật, cần hỏi:

**Câu 1 — Người gọi cần biết kết quả khi nào?**  
Ví dụ, lúc khách nhấn “Đặt hàng”, giao diện có thể cần xác nhận yêu cầu đã được chấp nhận ngay; nhưng kết quả giao hàng không thể có ngay. Một số bước có ngưỡng latency chặt, bước khác có thể xử lý vài giây hoặc vài phút sau.

**Câu 2 — Trạng thái nào phải đúng tức thời, trạng thái nào được phép cập nhật trễ?**  
Việc chống giữ hàng quá số lượng có thể đòi hỏi một transaction nhất quán trong Inventory. Trong khi đó báo cáo doanh thu có thể trễ vài giây. Không phải mọi màn hình đều cần đọc dữ liệu mới nhất từ mọi service.

**Câu 3 — Hai hệ thống có bắt buộc cùng hoạt động và cùng phát hành không?**  
Một lời gọi đồng bộ thường yêu cầu bên nhận sẵn sàng phản hồi trong giới hạn thời gian. Một message queue có thể tách thời điểm producer gửi và consumer xử lý; nhưng vẫn có thể tồn tại coupling qua schema, ngữ nghĩa event, thứ tự và quy trình nghiệp vụ.

Đây là ba **trục phân tích độc lập tương đối**. Không nên suy luận máy móc “latency thấp thì luôn REST”, “nhất quán mạnh thì luôn gRPC”, “loosely coupled thì cứ dùng Kafka”. Tính nhất quán thuộc về **hành vi nghiệp vụ và cơ chế quản lý trạng thái**, còn giao thức chỉ là một phần của thiết kế.

## 3. Tách khái niệm: pattern tương tác và giao thức truyền thông

**Interaction pattern** mô tả cách các bên phối hợp:

- **Request/response:** bên gọi gửi yêu cầu và mong nhận phản hồi để quyết định bước tiếp theo.
- **Fire-and-forget có theo dõi:** bên gọi gửi lệnh, nhận ACK xác nhận đã tiếp nhận; kết quả hoàn tất đến sau hoặc được truy vấn riêng.
- **Publish/subscribe:** bên phát công bố sự kiện; nhiều subscriber có thể xử lý theo mục đích riêng.
- **Point-to-point queue:** producer đưa một work item vào hàng đợi; một consumer trong nhóm cạnh tranh nhận xử lý.
- **Streaming:** trao đổi một chuỗi dữ liệu theo thời gian, có thể là server streaming, client streaming, bidirectional hoặc event log.
- **Batch/file transfer:** trao đổi dữ liệu theo lô trong thời gian không yêu cầu phản hồi tức thời.

**Protocol/transport** là cách triển khai pattern: HTTP/1.1 hoặc HTTP/2, REST/JSON, gRPC/Protocol Buffers, AMQP, Kafka protocol, WebSocket, Server-Sent Events (SSE) và các giao thức khác.

Một API REST thông thường dùng request/response, nhưng HTTP cũng hỗ trợ streaming hoặc chỉ xác nhận tiếp nhận rồi trả 202 Accepted. gRPC có unary request/response và các kiểu streaming. Kafka là nền tảng log phân tán phục vụ các luồng record bền vững, chứ bản thân nó không phải một giao thức RPC. RabbitMQ có mô hình queue/routing phù hợp nhiều bài toán gửi việc; broker cụ thể có giới hạn và hành vi riêng.

**Quyết định theo nhu cầu tương tác trước; chọn công nghệ phù hợp sau.**

## 4. So sánh các lựa chọn thường gặp

| Lựa chọn | Mô hình nổi bật | Độ trễ cảm nhận | Đặc điểm nhất quán | Mức liên kết và đánh đổi |
| --- | --- | --- | --- | --- |
| **REST/HTTP + JSON** | Request/response | Có thể nhanh; chịu network latency và xử lý server | Caller biết kết quả từ response, nhưng transaction xuyên service không tự động có | Dễ tích hợp, dễ kiểm tra; temporal coupling khi caller cần response |
| **gRPC unary** | Request/response qua HTTP/2 + Protobuf | Thường phù hợp giao tiếp hiệu năng cao; phụ thuộc workload thực tế | Tương tự RPC: không tự đảm bảo atomic commit giữa database | Contract typed, streaming/deadline tốt; client/server cần tương thích schema và tooling |
| **gRPC streaming** | Luồng dữ liệu dài hạn | Tốt khi truyền nhiều thông điệp liên tục; cần quản lý luồng và backpressure | Mỗi message vẫn cần định nghĩa thứ tự, idempotency và lưu bền vững nếu cần | Kết nối sống lâu, quan sát và vận hành phức tạp hơn |
| **Message queue** | Asynchronous work/command | ACK tiếp nhận có thể nhanh, hoàn tất thật sự sau đó | Thường cần trạng thái trung gian, retry/idempotency; thứ tự tùy broker/config | Giảm phụ thuộc thời điểm, tăng xử lý trễ và vận hành broker |
| **Pub/sub event** | One-to-many notification | Producer không chờ từng consumer hoàn tất | Downstream thường hội tụ dần; phải quy định event contract | Thêm subscriber linh hoạt, nhưng dễ coupling ngữ nghĩa và dữ liệu |
| **Event streaming/log** | Luồng sự kiện có offset, replay và xử lý theo nhóm | Phù hợp throughput và tái xử lý; latency tùy cấu hình và tải | Có ordering trong phạm vi broker bảo đảm; cross-system vẫn cần xử lý consistency | Hữu ích cho projections, analytics; vận hành và thiết kế schema phức tạp |
| **WebSocket / SSE** | Push dữ liệu thời gian thực đến client | Phù hợp cập nhật liên tục | Trạng thái chính thức vẫn cần backend lưu và kiểm soát | Quản lý kết nối dài hạn; không thay thế domain messaging |
| **Batch transfer** | Đồng bộ định kỳ, xử lý lô | Không phù hợp đáp ứng tương tác tức thì | Chấp nhận độ trễ được công bố | Đơn giản và tiết kiệm cho tích hợp không cần realtime |

Bảng trên mô tả xu hướng, **không phải benchmark**. Không có giao thức nào luôn nhanh nhất trong mọi điều kiện; kết quả phụ thuộc số byte, số request, số hop, serialization, network, số kết nối, broker topology, CPU, DB và cấu hình runtime.

## 5. Trục thứ nhất: độ trễ và deadline

### 5.1. Độ trễ là ngân sách của toàn đường xử lý

Giả sử một yêu cầu checkout đi qua API Gateway, Ordering, Pricing và Inventory:

~~~text
Browser
  |
  v
API Gateway
  |
  v
Ordering ----> Pricing
  |
  +----------> Inventory
  |
  v
Response to browser
~~~

Độ trễ đến người dùng gồm cả network, xử lý, hàng đợi, serialization, connection acquisition và những lời gọi xuống dưới. Nếu Ordering gọi Pricing rồi chờ xong mới gọi Inventory, chi phí nằm trên đường **tuần tự (critical path)**. Nếu hai lời gọi thực sự độc lập và có thể gọi song song, thời gian hoàn thành gần với nhánh chậm hơn cộng overhead, nhưng sẽ thêm concurrency và tải ở downstream.

Công thức ước lượng đơn giản cho lời gọi tuần tự:

~~~text
T_total ~= T_gateway + T_ordering_local
         + T_pricing_rpc + T_inventory_rpc
         + T_db + T_other_overheads
~~~

Đây là sơ đồ khái niệm, không phải đẳng thức đo lường chính xác. Mỗi thành phần có phân phối độ trễ, không phải hằng số.

Ví dụ minh họa:

~~~text
Gateway overhead             10 ms
Ordering local computation   15 ms
Pricing call                 45 ms
Inventory call               65 ms
DB operation                 35 ms
Other overhead               15 ms
---------------------------------
Rough sequential estimate   185 ms
~~~

Các số chỉ để thấy cách lập ngân sách. Không được suy ra p95/p99 tổng bằng tổng p95/p99 của từng call. Cần đo trace end-to-end dưới tải tương ứng và tính đến các đuôi phân phối.

### 5.2. Latency SLO, timeout và deadline

**SLO (service level objective)** là mục tiêu đo trải nghiệm hoặc hành vi, chẳng hạn “99% yêu cầu báo giá trả trong 300 ms trong điều kiện tải đã định”. **Deadline** là mốc kết thúc thời gian hợp lệ của một tác vụ; **timeout** là giới hạn chờ một thao tác cụ thể.

Nếu frontend cần kết quả trong 800 ms, không nên cấu hình mỗi downstream RPC timeout 3 giây rồi retry bốn lần. Tổng retry có thể vượt deadline, chiếm thread/connection pool và gây retry storm.

Ví dụ về phân bổ ngân sách theo giả định:

~~~text
Client request deadline: 800 ms
  Gateway + auth:          80 ms
  Ordering local + DB:    160 ms
  Downstream calls:       400 ms
  Serialization/margin:   160 ms
~~~

Timeout cho một downstream cần nằm trong ngân sách còn lại của toàn request; deadline phải được truyền hoặc suy ra nhất quán qua nhiều lớp. Cần cân nhắc connect timeout, read timeout, pool acquisition timeout, và cancellation. Retry chỉ hợp lý với lỗi tạm thời, khi thao tác có thể lặp an toàn và còn thời gian.

### 5.3. Cái gì phải ở trên đường trả lời?

Khi khách đặt đơn:

- **Cần trên critical path:** xác thực yêu cầu, bảo đảm điều kiện đặt đơn theo chính sách, nhận trạng thái tiếp nhận/đặt hàng phù hợp.
- **Có thể đẩy ra sau:** gửi email xác nhận, cập nhật dashboard nội bộ, đồng bộ recommendation, ghi vào data warehouse.
- **Tùy nghiệp vụ:** giữ hàng, xác nhận thanh toán, xác thực coupon hoặc đánh giá gian lận. Một số doanh nghiệp chỉ cho phép xác nhận đơn sau các bước này; nơi khác chấp nhận order trạng thái PENDING rồi xử lý tiếp.

Không đẩy một bước lên async chỉ vì muốn API phản hồi nhanh nếu sản phẩm đang hứa “đơn đã thanh toán và chắc chắn có hàng”. Phản hồi 202 Accepted hoặc “đang xử lý” phải khác về ngữ nghĩa với 201 Created/“đã xác nhận” nếu điều kiện thật sự chưa được bảo đảm.

### 5.4. Latency thấp không đồng nghĩa đồng bộ

Một worker xử lý message được cấu hình tốt có thể hoàn tất nhanh; một RPC đồng bộ có thể bị chậm bởi connection pool hoặc DB. Vấn đề là người gọi **cần chờ kết quả ngay không** và hệ thống chịu được mô hình lỗi nào. Hãy dùng latency distribution thực tế để quyết định.

## 6. Trục thứ hai: tính nhất quán và quyền sở hữu bất biến

### 6.1. Chia thành ba loại trạng thái

**Loại A — Bất biến phải luôn được giữ ở nơi sở hữu dữ liệu.**  
Ví dụ Inventory không được chấp nhận hai reservation khiến lượng cam kết vượt ngưỡng được phép. Cần cơ chế đồng bộ trong Inventory như transaction database, lock hoặc atomic conditional update theo thiết kế cụ thể. Dùng message broker trước Inventory **không thay thế** cơ chế bảo vệ bất biến cục bộ.

**Loại B — Quy trình nghiệp vụ xuyên nhiều dịch vụ.**  
Ví dụ Order, Inventory và Payment cần phối hợp để xác nhận giao dịch. Một transaction cục bộ không thể tự thực hiện atomic commit ở các database độc lập. Thường phải dùng trạng thái trung gian và cơ chế **Saga / process manager / orchestration**, cộng với thao tác bù và reconciliation khi lỗi.

**Loại C — Dữ liệu phái sinh phục vụ đọc.**  
Ví dụ dashboard doanh thu hoặc lịch sử đơn trên màn hình hỗ trợ có thể trễ một vài giây nếu nghiệp vụ chấp nhận. Đây là ứng viên tốt cho event-driven projection hoặc đồng bộ bất đồng bộ.

Thay vì hỏi chung “hệ thống có cần strong consistency không?”, hãy hỏi: **bất biến cụ thể nào không bao giờ được sai; ai có quyền quyết định nó; một phần khác được phép nhìn thấy dữ liệu cũ trong bao lâu?**

### 6.2. Phân biệt strong consistency và eventual consistency

**Strong consistency** trong một phạm vi nhất định cho phép các bên đọc trạng thái theo một bảo đảm mới nhất/tuần tự đã xác định. Ở database, cần nói rõ isolation level, linearizability hoặc cơ chế thực tế; không nên dùng từ “strong” mà không định nghĩa.

**Eventual consistency** nghĩa các bản sao/projection có thể tạm khác nhau nhưng sẽ hội tụ về trạng thái phù hợp khi việc cập nhật và xử lý tiếp tục thành công, với các giả định cần thiết. Nó **không có nghĩa mọi sai lệch cuối cùng tự sửa mà không cần thiết kế**. Phải có chiến lược replay, retry, dead-letter handling, giám sát dữ liệu lệch và đối soát.

Ví dụ một Order vừa được CONFIRMED:

- Ordering đã commit trạng thái order chính thức.
- Search hoặc Customer Support projection có thể chưa thấy order mới trong 1–2 giây.
- UI có thể lấy kết quả trực tiếp từ Ordering hoặc báo trạng thái “đang đồng bộ”.
- Báo cáo không được tự suy ra “chưa có đơn” chỉ vì consumer chưa xử lý event.

Khả năng đọc stale data cần được **thỏa thuận bằng yêu cầu nghiệp vụ**, không áp dụng ngầm cho tất cả màn hình.

### 6.3. Giao thức không tự quyết định mức nhất quán

REST/gRPC trả response tức thì vẫn có thể trả trạng thái đã đọc từ cache cũ. Còn event-driven pipeline có thể bảo vệ rất tốt một bất biến nếu mọi lệnh cập nhật đi qua một owner có xử lý tuần tự và transaction phù hợp.

Ngược lại, gửi request đồng bộ từ Ordering sang Inventory không tạo được một transaction ACID bao trùm cả database của Ordering và Inventory. Nếu Order lưu rồi Inventory thất bại, phải có trạng thái và hành vi nghiệp vụ rõ.

**Quy tắc:** giữ invariant trong đúng context; chọn giao thức để phối hợp các context theo latency và failure semantics chấp nhận được.

## 7. Trục thứ ba: mức liên kết (coupling)

Liên kết giữa các dịch vụ có nhiều chiều:

| Chiều liên kết | Câu hỏi đánh giá | Thiết kế để giảm liên kết |
| --- | --- | --- |
| **Temporal coupling** | Consumer có cần provider online cùng lúc không? | Queue, lưu yêu cầu bền vững, xử lý kết quả sau khi dependency hồi phục |
| **Availability coupling** | Provider lỗi có làm request của consumer thất bại ngay không? | Timeout, circuit breaker/bulkhead, fallback hợp lệ, phân tầng critical path |
| **Schema coupling** | Thêm/sửa field có làm consumer phải sửa cùng lúc không? | Hợp đồng phiên bản, mở rộng tương thích, contract tests |
| **Semantic coupling** | Consumer có phải hiểu luật và trạng thái nội bộ của provider không? | Domain events rõ nghĩa, chống rò rỉ entity, anti-corruption layer |
| **Deployment coupling** | Hai service có phải deploy lockstep mỗi lần thay đổi không? | Backward/forward compatibility, phased rollout |
| **Data coupling** | Consumer có đọc/ghi trực tiếp schema của provider không? | Data ownership, API/event/projection theo contract |
| **Operational coupling** | Một nghẽn tài nguyên có làm hệ khác cạn tài nguyên không? | Resource isolation, giới hạn concurrency, queue, backpressure |

### 7.1. RPC đồng bộ có temporal coupling

Trong một request thông thường:

~~~text
Ordering --(HTTP/gRPC request)--> Pricing
Ordering <--(response)----------- Pricing
~~~

Ordering cần Pricing phản hồi đúng hạn để tiếp tục nếu giá là điều kiện bắt buộc. Đây là coupling về **thời điểm**. Nó có thể hoàn toàn phù hợp khi yêu cầu nghiệp vụ cần quyết định ngay, chẳng hạn khách muốn xem báo giá mới nhất trước khi chốt.

Không nên cố loại bỏ mọi lời gọi đồng bộ; thay vào đó tối thiểu hóa chuỗi RPC nối tiếp, lập deadline, tránh gọi chéo vòng và chỉ đặt dependency thật sự cần thiết trên critical path.

### 7.2. Async messaging giảm temporal coupling nhưng tạo trách nhiệm khác

~~~text
Ordering -> [Durable queue] -> Email Worker
                       |
                 retry / dead letter
~~~

Ordering có thể hoàn tất transaction và tiếp tục mà không cần Email Worker đang online. Queue có thể giữ thông điệp cho worker xử lý sau. Tuy nhiên:

- Broker phải tiếp nhận và lưu bền vững theo cấu hình phù hợp.
- Message phải có định danh, schema và ngữ nghĩa rõ.
- Worker phải xử lý thông điệp trùng và retry.
- Producer phải biết sự kiện có được phát thành công khi transaction commit hay không.
- Phải quan sát queue lag, dead letter, thất bại kéo dài và xử lý hồi phục.

Async giúp **tách thời điểm thực thi**, chứ không xóa schema/semantic coupling. Một event OrderUpdated mang toàn bộ entity nội bộ vẫn buộc nhiều consumer hiểu chi tiết Ordering.

### 7.3. Sự kiện và lệnh khác nhau

**Command** yêu cầu một bên chịu trách nhiệm thực hiện điều gì đó, ví dụ ReserveStock(orderId, sku, quantity). Bên nhận có thể từ chối vì quy tắc nghiệp vụ hoặc trạng thái hiện tại.

**Event** thông báo điều đã xảy ra, ví dụ OrderConfirmed(orderId, confirmedAt) hoặc StockReserved(reservationId, orderId). Một event không tự mang ý nghĩa “consumer phải làm việc này”, trừ khi hợp đồng và quy trình nghiệp vụ đã định như vậy.

Lưu ý:

~~~text
Command:    ReserveStock
Meaning:    "Hãy thử giữ lượng hàng này."

Event:      StockReserved
Meaning:    "Việc giữ hàng đã thành công."

Event:      OrderConfirmed
Meaning:    "Đơn đã được xác nhận theo chính sách Ordering."
~~~

Nếu sự kiện được đặt tên mơ hồ như DatabaseRowChanged, consumer thường phải suy luận nghiệp vụ từ cấu trúc lưu trữ; mức liên kết có thể tăng.

## 8. Khi nào nên dùng REST/HTTP?

REST/HTTP + JSON thường phù hợp với **public API, web/mobile client, BFF, truy vấn dữ liệu, lệnh có phản hồi trực tiếp** và tích hợp cần khả năng tương tác rộng.

Ví dụ:

- Frontend yêu cầu Product Catalog trả dữ liệu sản phẩm cho trang chi tiết.
- Ordering cần Pricing trả báo giá hiện tại trước khi hiện màn xác nhận.
- Hệ thống quản trị gửi lệnh đổi trạng thái một yêu cầu có kết quả ngay.
- Gateway gọi một backend có hợp đồng HTTP ổn định.

Ưu điểm: dùng hệ sinh thái rộng, dễ debug bằng HTTP tooling, rõ status code, cache có kiểm soát cho GET, tương tác tốt với browser và các hệ thống khác.

Hạn chế:

- Dễ tạo chuỗi gọi đồng bộ dài, làm độ trễ và phạm vi lỗi tăng.
- 200 OK chỉ nói request được xử lý theo contract, **không** tự nói cả workflow phân tán đã hoàn tất.
- Retry POST không được thiết kế idempotent có thể nhân đôi thao tác.
- Không tự quản lý consistency xuyên các database.

### 8.1. Dùng status code đúng ngữ nghĩa

Với một tác vụ đã **hoàn tất và có kết quả**, response 200/201 có thể phù hợp theo API contract. Với một tác vụ đã **được tiếp nhận để xử lý sau**, 202 Accepted là lựa chọn thường gặp, kèm operationId hoặc đường truy vấn trạng thái. Với lỗi xác thực, xung đột, hết hạn hoặc điều kiện nghiệp vụ không thỏa, cần thiết kế phản hồi rõ và không biến mọi trường hợp thành 500.

Ví dụ:

~~~http
POST /api/orders
Content-Type: application/json
Idempotency-Key: req-1001

{"customerId":"C-01","items":[{"sku":"SKU-7","quantity":2}]}
~~~

Nếu tạo đơn hoàn tất ngay:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":"O-1001","status":"CONFIRMED"}
~~~

Nếu mới tiếp nhận:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"orderId":"O-1001","status":"PENDING"}
~~~

Hai response thể hiện lời hứa nghiệp vụ khác nhau. Không được trả CONFIRMED chỉ vì message đã vào queue trong khi Inventory chưa bảo đảm giữ hàng.

## 9. Khi nào cân nhắc gRPC?

gRPC thường phù hợp cho **service-to-service RPC nội bộ**, nơi contract typed và hiệu quả serialization/streaming có giá trị. Protocol Buffers hỗ trợ định nghĩa message và method tương đối rõ; HTTP/2 hỗ trợ multiplexing và streaming. Với workload nhiều call hoặc payload nhỏ, có thể hiệu quả, nhưng **không mặc định nhanh hơn HTTP/JSON cho mọi tình huống**.

Một hợp đồng gRPC unary minh họa:

~~~proto
syntax = "proto3";

package inventory.v1;

service InventoryReservations {
  rpc ReserveStock (ReserveStockRequest) returns (ReserveStockReply);
}

message ReserveStockRequest {
  string command_id = 1;
  string order_id = 2;
  string sku = 3;
  int32 quantity = 4;
}

message ReserveStockReply {
  string reservation_id = 1;
  bool accepted = 2;
  string rejection_reason = 3;
}
~~~

Khi chọn gRPC, xem:

- Client/server có hỗ trợ phiên bản, Protobuf tooling và deadline propagation hay không.
- Có cần streaming thực tế hay chỉ unary RPC?
- Kết nối lâu dài, load balancer, proxy và observability có hoạt động đúng không?
- Browser có cần truy cập trực tiếp không; có thể cần gateway/gRPC-Web tùy môi trường.
- Có thực sự thấy lợi ích qua benchmark p50/p95/p99, CPU, payload và throughput không?
- Các tác vụ có đảm bảo idempotency và business error semantics chưa?

**gRPC không làm mất temporal coupling của RPC.** Nếu Pricing không online, Order vẫn phải quyết định chờ, dùng fallback hợp lệ hoặc trả lỗi, dù payload được serialize bằng Protobuf.

## 10. Khi nào dùng queue cho công việc bất đồng bộ?

Message queue phù hợp với công việc có thể được tiếp nhận trước và xử lý sau, cần **buffer đỉnh tải**, retry hoặc tách lifecycle của producer/worker.

Các ví dụ:

- Gửi email, SMS, push notification sau khi đơn được xác nhận.
- Xử lý tạo PDF/invoice nền khi khách không cần chờ bản PDF hoàn tất để nhận kết quả đặt hàng.
- Tạo thumbnail, indexing, làm giàu dữ liệu.
- Đồng bộ dữ liệu qua các hệ thống có tốc độ xử lý khác nhau.
- Thực hiện bước workflow có trạng thái PENDING và kết quả bất đồng bộ được công bố.

Luồng:

~~~text
Order transaction
      |
      v
Outbox record in Ordering DB
      |
      v
Outbox publisher ---> [Durable broker] ---> Notification worker
                                           | success: ACK
                                           | transient failure: retry
                                           | poison/invalid: DLQ + alert
~~~

### 10.1. Queue không có nghĩa xử lý đúng một lần

Nhiều cấu hình broker dùng **at-least-once delivery**: một message có thể được gửi lại nếu consumer đã xử lý nhưng ACK bị mất. Vì vậy consumer cần idempotency, ví dụ unique constraint theo eventId hoặc commandId.

Một số nền tảng có tính năng giao hàng/transaction mang tên “exactly once”, nhưng phạm vi bảo đảm thường bị giới hạn theo broker hoặc topology cụ thể. Không suy ra “thanh toán sẽ đúng một lần” trên toàn hệ thống chỉ vì một tùy chọn broker. **Business exactly-once effect** cần idempotency, uniqueness và đối soát ở nơi sở hữu nghiệp vụ.

### 10.2. Thứ tự message không phải thứ tự toàn cục mặc định

Các message về cùng một order có thể cần giữ thứ tự; các order khác nhau có thể xử lý song song. Cấu hình partition/key, consumer group và batch cần phản ánh phạm vi ordering mong muốn. Khi retry, message cũ có thể đến muộn; consumer nên kiểm tra version/sequence hoặc trạng thái hiện tại thay vì tin mọi event đến đúng một trình tự toàn cục.

### 10.3. Retry và DLQ

Retry phù hợp khi lỗi **tạm thời**: dependency unavailable, network timeout, overload. Nhưng message sai schema hoặc vi phạm bất biến lâu dài có thể không bao giờ thành công nếu cứ retry. Cần giới hạn retry, backoff, dead-letter queue (DLQ), cảnh báo, công cụ replay và nguyên tắc không làm mất khả năng audit.

**Đưa vào DLQ không phải hoàn tất nghiệp vụ.** Một đơn đang PENDING vì message lỗi cần được theo dõi và có phương án xử lý, kể cả bù trừ hoặc can thiệp có kiểm soát.

## 11. Khi nào dùng publish/subscribe và event streaming?

Pub/sub phù hợp khi một sự kiện có nhiều consumer độc lập về **mục đích xử lý**:

~~~text
OrderConfirmed
    |
    v
[Event broker / event log]
    |------------> Notification: send confirmation
    |------------> Analytics: update sales projection
    |------------> Loyalty: grant points
    +------------> Fulfillment: prepare packing request
~~~

Producer chỉ cần công bố sự thật “Order đã CONFIRMED theo định nghĩa Ordering”. Notification, Analytics, Loyalty và Fulfillment tiêu thụ theo logic riêng.

**Lợi ích:** thêm subscriber mới có thể không cần sửa luồng điều khiển synchronous của Ordering; tải xử lý nền được tách khỏi thời gian trả lời checkout.

**Đánh đổi:** consumer tiến triển với độ trễ; sự kiện có thể bị trùng, gửi lại hoặc xử lý sai thứ tự; schema thay đổi phải tương thích; nhiều workflow xuyên consumer sẽ khó nhìn nếu không có tracing và correlation.

### 11.1. Event log/streaming hữu ích ở đâu?

Nền tảng như Kafka phù hợp cho các trường hợp có nhiều luồng sự kiện, throughput lớn, consumer groups, replay và xử lý projection. Một topic có thể được partition theo key và dùng offset theo dõi vị trí tiêu thụ.

Tuy vậy, trước khi chọn Kafka nên tự hỏi: cần retention dài hạn, replay, nhiều nhóm consumer độc lập hoặc throughput lớn thật không? Nếu chỉ cần gửi một job email đơn giản, một queue gọn hoặc thậm chí cơ chế worker được quản lý sẵn có thể đơn giản hơn.

**Broker và protocol không thể sửa một mô hình event sai.** Nếu mọi consumer phải phân tích một payload CustomerRowUpdated chứa 60 cột JPA, kiến trúc vẫn coupling theo schema lưu trữ.

### 11.2. Công bố sự kiện sau commit: vấn đề dual write

Mã sau có thể sai khi hệ thống lỗi giữa hai bước:

~~~text
1. INSERT/UPDATE order trong database.
2. Publish OrderConfirmed tới broker.
~~~

Nếu database commit thành công nhưng publish lỗi, các consumer không nhận được event. Nếu publish thành công trước commit nhưng transaction rollback, consumer có thể xử lý một đơn chưa từng được xác nhận.

**Transactional outbox** là mẫu phổ biến:

~~~text
Local DB transaction:
  UPDATE orders SET status = 'CONFIRMED' WHERE id = ...
  INSERT INTO outbox(event_id, type, payload, created_at) VALUES (...)
COMMIT

Independent publisher:
  Read unpublished outbox
  Publish to broker
  Mark published / checkpoint safely
~~~

Outbox giúp liên kết thay đổi trạng thái chính thức và việc **ghi nhận ý định phát sự kiện** trong cùng transaction nội bộ. Publisher vẫn có thể phát trùng khi retry, vì vậy downstream vẫn cần idempotency. Outbox không làm các database consumer cùng commit nguyên tử.

## 12. Tính nhất quán trong giao dịch đặt hàng

Giả sử một yêu cầu đặt hàng phải kiểm tra giá, giữ hàng và xử lý thanh toán. Không nhất thiết có một thứ tự tối ưu cho mọi doanh nghiệp. Dưới đây là **một thiết kế minh họa**:

~~~text
Browser
  |
  | PlaceOrder
  v
Ordering
  |-- synchronous PriceQuote ---> Pricing
  |<-- quote with validity ------
  |
  | Local transaction: create Order(PENDING), store process state
  |
  | Publish ReserveStock command via outbox
  v
Message broker ------------------> Inventory
                                    |
                                  Reserve stock
                                    |
                        StockReserved / StockRejected
                                    |
                                    v
                          Ordering process manager
                                    |
                          if reserved -> initiate Payment
                                    |
                                Payment result
                                    |
                     OrderConfirmed / OrderFailed
                                    |
                          downstream notifications
~~~

### 12.1. Vì sao báo giá có thể đồng bộ?

Trong ví dụ, UI muốn hiện số tiền cuối cùng trước khi khách đồng ý, vì vậy cần quote trong ngân sách latency tương tác. Giao tiếp request/response hợp lý, dù REST hay gRPC phải lựa chọn theo client, contract và workload.

### 12.2. Vì sao giữ hàng có thể bất đồng bộ?

Nếu doanh nghiệp chấp nhận đơn PENDING trong lúc hệ thống kho xác nhận reservation, Ordering không phải giữ HTTP connection cho toàn bộ quy trình. Lệnh ReserveStock được lưu qua outbox; Inventory xử lý và phát kết quả. Nhưng UI cần thông báo “đang xử lý”, có đường tra trạng thái/nhận push và chính sách hết hạn rõ.

**Nếu chính sách sản phẩm yêu cầu xác nhận còn hàng tức thì trước khi hiển thị thành công**, Order có thể dùng RPC đồng bộ trong critical path thay vì async. Quyết định theo yêu cầu nghiệp vụ chứ không theo khẩu hiệu event-driven.

### 12.3. Chống vượt tồn kho nằm ở đâu?

Inventory phải bảo đảm reserve là thao tác atomic trong phạm vi dữ liệu nó sở hữu: kiểm tra/ghi lượng hàng với concurrency control phù hợp. Việc gửi lệnh từ Ordering qua queue hoặc HTTP **không được coi là bảo đảm đủ hàng** trước khi Inventory xác nhận.

### 12.4. Chống thanh toán hai lần

Payment cần idempotency key ổn định cho cùng một ý định thanh toán. Nếu response của Payment timeout sau khi giao dịch đã thành công, Ordering không tự tạo payment attempt mới và thu lại tiền. Cần tra cứu trạng thái, nhận event bền vững hoặc reconciliation theo hợp đồng. Tình huống thất bại kéo dài cần chính sách bù giữ hàng/hoàn tiền nếu phù hợp.

## 13. Một luồng hỗn hợp có thể là thiết kế tốt

Không phải chọn “toàn REST” hoặc “toàn Kafka”. Một hệ thống thực tế thường kết hợp:

- **HTTP/REST** cho public API, dữ liệu hiển thị và các lệnh yêu cầu phản hồi nhanh.
- **gRPC** cho một số RPC nội bộ có contract typed hoặc streaming liên tục khi có nhu cầu đã đo.
- **Queue** cho background jobs và các command được phép xử lý sau.
- **Domain events qua pub/sub/stream** cho projection và phối hợp nhiều consumer.
- **SSE/WebSocket** cho cập nhật trạng thái hướng về browser.
- **Batch** cho đối soát, báo cáo hoặc tích hợp không yêu cầu realtime.

Ví dụ:

~~~text
[Browser]
   | REST PlaceOrder
   v
[Ordering API] ---- REST/gRPC PriceQuote ---> [Pricing]
   |
   +---- Outbox -> queue ReserveStock ------> [Inventory]
   |                                            |
   |<--- event StockReserved/Rejected ----------+
   |
   +---- command CapturePayment --------------> [Payment]
   |                                            |
   |<--- event PaymentCaptured/Failed ----------+
   |
   +---- event OrderConfirmed -------------> [Notification]
   |                                       -> [Analytics]
   +---- SSE OrderStatus ------------------> [Browser]
~~~

Một hệ thống có nhiều giao thức không tự động trở nên tốt hơn. Mỗi lựa chọn cần lý do cụ thể về latency, consistency, coupling, khả năng vận hành và mức độ hiểu biết của đội ngũ.

## 14. Lựa chọn giao thức qua khung câu hỏi

Khi thiết kế một mũi tên giao tiếp giữa hai context, hãy trả lời theo thứ tự sau.

### Bước 1 — Đây là query, command hay event?

- **Query:** ai đang sở hữu dữ liệu chuẩn và caller có cần kết quả ngay?
- **Command:** ai có quyền chấp nhận/từ chối thay đổi? Kết quả cần ngay hay được phép đến sau?
- **Event:** điều gì đã xảy ra; có consumer nào quan tâm; có cần phát sự kiện bền vững không?

Đừng dùng tên công nghệ để thay thế mô tả ý nghĩa nghiệp vụ.

### Bước 2 — Người dùng hoặc hệ thống chờ được bao lâu?

Ghi rõ giới hạn: “p95 dưới 300 ms cho báo giá” hoặc “hóa đơn PDF sẵn trong 30 giây” là yêu cầu kiểm chứng được. “Càng nhanh càng tốt” không đủ cho thiết kế.

Nếu tác vụ phải hoàn tất trong thời gian request rất ngắn, ưu tiên local logic hoặc RPC có deadline phù hợp. Nếu có thể xử lý sau, cân nhắc queue. Nhưng cần phân biệt thời gian **ACK tiếp nhận** và thời gian **hoàn tất nghiệp vụ**.

### Bước 3 — Nhất quán mạnh ở đâu và stale data được phép bao lâu?

Xác định bất biến, data owner, nơi commit transaction, người cần biết kết quả cuối cùng và độ trễ cho phép của projection. Nếu nghiệp vụ yêu cầu hai thao tác nguyên tử xuyên boundary, cần xem lại ranh giới hoặc thiết kế workflow có compensation; đừng kỳ vọng một protocol giải quyết mặc nhiên.

### Bước 4 — Có cần bên nhận online ngay không?

Nếu không cần và có thể lưu yêu cầu bền vững, async giảm temporal coupling. Nếu cần xác nhận một quyết định tức thời, RPC thường trực quan hơn. Tùy trường hợp, một HTTP 202 kèm operationId có thể là lớp ngoài của một workflow async.

### Bước 5 — Có bao nhiêu consumer và họ độc lập đến mức nào?

Một job chỉ có một worker phù hợp queue. Một event nhiều consumer độc lập thường phù hợp pub/sub hoặc stream. Một caller cần câu trả lời có kiểu dữ liệu rõ phù hợp request/response.

### Bước 6 — Khối lượng và hình dạng dữ liệu như thế nào?

Đo request rate, message size, số hop, payload compression, throughput, p95/p99, backlog và chi phí serialization. Cân nhắc gRPC/streaming khi có khối lượng dữ liệu và yêu cầu contract chứng minh lợi ích; không chọn chỉ vì nghe “hiệu năng hơn”.

### Bước 7 — Đội ngũ có vận hành được không?

Hệ thống broker cần monitoring, recovery, retention, partition, key, DLQ và schema governance. RPC cần timeout, connection pool, observability và client compatibility. Chọn mô hình mà đội ngũ có thể triển khai và xử lý sự cố đáng tin cậy.

### Bước 8 — Hợp đồng được tiến hóa và kiểm thử ra sao?

Với REST/gRPC, cần contract compatibility và consumer/provider tests. Với event, cần schema evolution, semantics và replay/backfill strategy khi consumer thay đổi. Không để mọi service phải deploy đồng thời vì thay một field không liên quan.

## 15. Ví dụ Java/Spring Boot: gọi đồng bộ với ranh giới rõ

Trong một Ordering Context, miền nghiệp vụ có thể chỉ biết một cổng báo giá:

~~~java
package example.ordering.application;

import java.util.List;

public interface PricingPort {
    PriceQuote getQuote(PriceQuoteRequest request);
}

public record PriceQuoteRequest(
        String customerId,
        List<Line> lines) {
    public record Line(String sku, int quantity) {}
}

public record PriceQuote(
        String quoteId,
        String currency,
        long totalMinorUnits,
        long expiresAtEpochMillis) {}
~~~

Một adapter có thể gọi Pricing qua Spring RestClient:

~~~java
package example.ordering.infrastructure.pricing;

import example.ordering.application.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class HttpPricingAdapter implements PricingPort {
    private final RestClient restClient;

    public HttpPricingAdapter(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://pricing.internal")
                .build();
    }

    @Override
    public PriceQuote getQuote(PriceQuoteRequest request) {
        return restClient.post()
                .uri("/v1/quotes")
                .body(request)
                .retrieve()
                .body(PriceQuote.class);
    }
}
~~~

Đoạn code chỉ minh họa **đường tương tác và phân lớp adapter**. Trong production cần cấu hình timeout ở HTTP client phù hợp, xác thực service-to-service, TLS, kiểm soát lỗi HTTP và nghiệp vụ, tracing, circuit breaker/bulkhead khi cần, cache nếu được phép, và resilience có giới hạn. Không tự động retry một POST có side effect nếu không có idempotency được thiết kế từ hợp đồng.

**Ý nghĩa thiết kế:** domain Order phụ thuộc vào PricingPort theo ngôn ngữ nghiệp vụ, không trực tiếp phụ thuộc vào HTTP framework hoặc entity nội bộ của Pricing. Điều này giúp giữ bounded context, và cho phép đổi transport theo nhu cầu mà không đổi core domain.

### 15.1. Ví dụ timeout không phải “giá bằng 0”

Giả sử HTTP Pricing timeout. Những cách xử lý có thể hợp lệ:

- Trả trạng thái “chưa lấy được báo giá, vui lòng thử lại”.
- Sử dụng quote đã được Pricing xác thực còn hiệu lực nếu contract cho phép.
- Tiếp nhận yêu cầu xử lý sau và hiển thị PENDING nếu sản phẩm hỗ trợ.

Cách nguy hiểm: trả total = 0 hoặc lấy giá cũ tùy ý để hoàn tất checkout. Fallback là quyết định **nghiệp vụ**, không chỉ là một tính năng kỹ thuật.

## 16. Ví dụ Java/Spring Boot: xử lý sự kiện bất đồng bộ

Giả sử Ordering công bố OrderConfirmed để Notification gửi email sau. Trong mô hình event, không nên đặt lệnh SendEmail bên trong domain Ordering vì cách thông báo thuộc consumer.

Một event contract minh họa:

~~~java
package example.contracts.order;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        String customerId,
        int schemaVersion) {}
~~~

Consumer có thể xử lý:

~~~java
package example.notification.application;

import example.contracts.order.OrderConfirmed;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationHandler {
    private final ProcessedEventStore processedEvents;
    private final EmailSender emails;

    public OrderConfirmationHandler(
            ProcessedEventStore processedEvents,
            EmailSender emails) {
        this.processedEvents = processedEvents;
        this.emails = emails;
    }

    public void handle(OrderConfirmed event) {
        if (processedEvents.alreadyProcessed(event.eventId())) {
            return;
        }

        emails.sendOrderConfirmation(event.orderId(), event.customerId());
        processedEvents.markProcessed(event.eventId());
    }
}
~~~

Đây là **mã khái niệm** để chỉ rõ ý tưởng deduplication, không phải triển khai exactly-once đã hoàn chỉnh. Nếu gửi email thành công rồi process chết trước markProcessed, event có thể được gửi lại và email bị gửi lần nữa. Trong production cần thiết kế cơ chế idempotency tương ứng, ví dụ lưu unique work item/outbox của Notification và cung cấp deduplication key cho nhà cung cấp gửi email nếu hỗ trợ. Không thể coi hai câu lệnh send và mark ở hai hệ thống khác nhau là một transaction.

**Một điểm quan trọng:** xử lý event trùng dựa trên eventId chỉ đúng khi eventId được giữ ổn định qua retry; tạo eventId mới mỗi lần phát lại sẽ phá cơ chế deduplication.

## 17. Những trường hợp cần xử lý đặc biệt

### 17.1. Request chậm và timeout dây chuyền

Một request đi qua 5 RPC đồng bộ có thể khuếch đại lỗi khi một dependency chậm. Retry đồng loạt tăng tải ngay lúc hệ thống đang yếu. Hãy giới hạn fan-out, thiết kế deadline cho toàn request, dùng backoff/jitter phù hợp, circuit breaker/bulkhead, giới hạn concurrency và bỏ retry khi deadline đã hết.

Nếu Pricing trả response sau khi Ordering đã timeout, cần biết yêu cầu đó có side effect hay không. Với một query thuần đọc, retry có thể tương đối an toàn; với lệnh ghi, phải có idempotency và khả năng truy vấn kết quả.

### 17.2. Giao dịch ngân hàng hoặc thanh toán

Không chuyển từ đồng bộ sang async chỉ để giảm latency nếu điều đó làm giao diện tuyên bố sai “thành công” khi thực tế chỉ mới nhận lệnh. Có thể dùng 202 + paymentId và cung cấp trạng thái chính thức sau, nhưng UX và quy tắc hạch toán phải đúng với lời hứa nghiệp vụ. Idempotency và reconciliation quan trọng hơn tên transport.

### 17.3. Cập nhật tồn kho với mức tải cao

Queue có thể buffer lệnh giữ hàng; nhưng Inventory vẫn phải kiểm soát cạnh tranh ghi trên SKU và kho. Partition theo SKU có thể hữu ích nếu cần thứ tự, nhưng khi có nhiều kho/partition hoặc cân bằng tải phải cẩn thận với phạm vi ordering và invariant. Không dùng “message đến đúng thứ tự” làm lý do bỏ cơ chế chống overselling.

### 17.4. Báo cáo doanh thu

Nếu dashboard cho phép trễ 10 giây, có thể tiêu thụ OrderConfirmed/PaymentCaptured rồi cập nhật read model. Màn hình nên hiển thị thời điểm dữ liệu gần nhất và phân biệt doanh thu từ đơn xác nhận với doanh thu đã captured. Khi consumer bị lag, cần metric và cảnh báo; khi schema thay đổi, cần migration/rebuild projection.

### 17.5. Tìm kiếm sản phẩm

Search index thường là projection từ Catalog, phù hợp event-driven đồng bộ thay đổi sản phẩm. Nhưng khi người quản trị vừa đổi tên sản phẩm, trang quản trị có thể cần đọc ngay dữ liệu chính thức từ Catalog thay vì đợi index. Hai nhu cầu có thể dùng hai đường đọc khác nhau, miễn là ngữ nghĩa rõ.

### 17.6. Push trạng thái tới browser

Sau khi server trả 202 Accepted cho đơn PENDING, frontend có thể poll theo operationId hoặc nhận SSE/WebSocket. SSE/WebSocket chỉ giúp truyền cập nhật đến browser; chúng không bảo đảm event được ghi bền vững hoặc thứ tự nghiệp vụ, và client phải có cách query lại trạng thái chính thức sau reconnect.

## 18. Những sai lầm phổ biến

| Sai lầm | Vì sao không đúng | Cách suy nghĩ phù hợp |
| --- | --- | --- |
| “gRPC luôn nhanh hơn REST.” | Tùy payload, tải, network, codec và runtime | Benchmark trên workload và SLO cụ thể |
| “Kafka làm tất cả service loosely coupled.” | Vẫn có schema, semantic, ordering và broker coupling | Thiết kế event contract và governance |
| “Gửi message là đã hoàn tất tác vụ.” | ACK broker khác kết quả nghiệp vụ | Theo dõi trạng thái xử lý và failure |
| “HTTP 200 nghĩa cả workflow đã commit.” | Có thể chỉ commit một phần local | Định nghĩa trạng thái và lời hứa của API |
| “REST là strong consistency; async là eventual consistency.” | Consistency phụ thuộc data owner và protocol nghiệp vụ | Xác định bất biến và transaction boundary |
| “Retry là cách chữa mọi timeout.” | Gây trùng thao tác, retry storm hoặc lỗi lớn hơn | Deadline, idempotency, backoff và lỗi có thể retry |
| “Exactly-once của broker giúp charge tiền đúng một lần.” | Hạn chế phạm vi bảo đảm broker | Business idempotency, unique key, reconciliation |
| “Mọi domain event phải kích hoạt service khác.” | Event là sự thật đã xảy ra, không phải lệnh ẩn | Phân biệt command và event |
| “Chỉ nên dùng một giao thức cho toàn hệ thống.” | Use case có yêu cầu khác nhau | Chọn theo từng đường tương tác |
| “Tất cả dữ liệu phải cập nhật real-time.” | Làm tăng coupling và chi phí không cần thiết | Xác định stale window được phép |
| “Queue luôn giảm latency.” | Có thể giảm thời gian ACK nhưng tăng thời gian hoàn tất | Tách latency phản hồi và latency xử lý |
| “Có event streaming thì không cần outbox.” | Dual write vẫn có thể mất hoặc phát event sai | Bảo vệ việc ghi event cùng transaction local |

## 19. Một bảng quyết định theo use case

| Use case | Điều quan trọng nhất | Lựa chọn khởi đầu thường hợp lý | Những câu cần xác minh |
| --- | --- | --- | --- |
| Truy vấn thông tin sản phẩm từ browser | Phản hồi ngay, dễ tích hợp | REST/HTTP | Có cần cache và stale tolerance không? |
| Báo giá tại checkout | Latency tương tác và quote chính xác | REST/gRPC unary | Giá có hiệu lực bao lâu; timeout thì sao? |
| Giữ tồn kho trước xác nhận đơn | Bất biến stock, kết quả accepted/rejected | RPC nếu cần kết quả ngay; command async nếu chấp nhận PENDING | Ai sở hữu transaction; xử lý trùng và timeout thế nào? |
| Thu/hoàn tiền | Tránh trùng giao dịch, trạng thái chính thức | API/command với idempotency và reconciliation | Khi response mất, xác định kết quả ra sao? |
| Gửi email xác nhận | Không chặn checkout, retry | Queue/event consumer | Chống email trùng, DLQ và audit ra sao? |
| Đồng bộ search index | Projection có thể trễ | Pub/sub/event stream | Lag được phép, replay và rebuild ra sao? |
| Cập nhật analytics | Throughput, nhiều consumer, replay | Event stream hoặc batch theo nhu cầu | Dữ liệu nguồn, độ trễ, đối soát ra sao? |
| Trạng thái xử lý tới browser | Cập nhật UX sau ACK | Polling/SSE/WebSocket | Reconnect, state query, giới hạn kết nối? |
| Trao đổi dữ liệu định kỳ với ERP | Dung lượng và độ tin cậy theo lịch | Batch/file transfer hoặc queue | Đối soát, lịch chạy, xử lý thất bại? |

Bảng là điểm khởi đầu thảo luận. Khi ràng buộc thay đổi, cùng một nghiệp vụ có thể dùng giao thức khác.

## 20. Bài tập và lời giải định hướng

### Bài tập 1 — Tạo đơn và gửi email

Một hệ thống yêu cầu endpoint đặt hàng phản hồi trong 500 ms. Gửi email đôi khi mất 4 giây. Nên để Ordering gọi Email Service đồng bộ rồi mới trả response không?

**Gợi ý:** Nếu email không quyết định đơn có được chấp nhận hay không, nó không nên nằm trên critical path của tạo đơn. Ordering commit trạng thái thích hợp rồi phát sự kiện qua outbox; Notification xử lý async, có retry và theo dõi. Không được công bố OrderConfirmed trước khi Ordering thật sự commit trạng thái tương ứng.

### Bài tập 2 — Đặt hàng khi Inventory chậm

Inventory đôi lúc trả lời sau 3 giây, trong khi UX yêu cầu nhanh. Sản phẩm chấp nhận trạng thái “đơn đang được xử lý”. Chọn pattern nào?

**Gợi ý:** Có thể trả 202/PENDING sau khi tiếp nhận yêu cầu bền vững và dùng async ReserveStock command, kết quả cập nhật sau. Cần timeout/hạn xử lý, idempotency, trạng thái chờ rõ và đường nhận kết quả. Nếu chính sách bắt buộc xác nhận stock tức thời, yêu cầu UX cần được điều chỉnh hoặc hệ thống phải có nguồn dữ liệu/nguồn quyết định đáp ứng deadline mà vẫn bảo vệ invariant.

### Bài tập 3 — Một thay đổi giá làm sai đơn lịch sử

Ordering dùng GET /prices/latest khi hiển thị lịch sử đơn. Pricing đổi giá hôm nay khiến tổng tiền đơn hôm qua thay đổi. Đổi sang gRPC có giải quyết không?

**Gợi ý:** Không. Đây là vấn đề mô hình dữ liệu và ownership, không phải transport. Ordering cần lưu snapshot giá đã được khách chấp thuận ở thời điểm mua, cùng metadata cần thiết. Protocol có thể giữ nguyên.

### Bài tập 4 — Event được xử lý hai lần

Notification nhận OrderConfirmed hai lần sau khi broker reconnect và gửi hai email. Đội vận hành muốn bật cấu hình “exactly-once” và bỏ logic deduplication.

**Gợi ý:** Cần làm rõ phạm vi bảo đảm của broker; email provider là hệ thống bên ngoài. Tạo idempotency key/work item bền vững, lưu trạng thái gửi, tận dụng cơ chế dedup của provider khi có, và đối soát trường hợp response thất lạc. Không suy ra exactly-once end-to-end từ một cấu hình broker.

### Bài tập 5 — Streaming thay polling

Một ứng dụng cần cập nhật vị trí xe giao hàng mỗi vài giây. Có nên gọi gRPC unary lặp lại cho từng tọa độ?

**Gợi ý:** Có thể dùng SSE, WebSocket hoặc streaming tùy client, mạng, số kết nối, hai chiều hay một chiều và yêu cầu phục hồi. Tuy nhiên cần phân biệt vị trí mới nhất theo thời gian thực với dữ liệu bền vững bắt buộc ghi, và có cơ chế reconnect/đọc lại state.

### Bài tập 6 — Sổ cái giao dịch

Bộ phận tài chính yêu cầu số dư không bao giờ vi phạm quy tắc hạch toán nội bộ. Có thể đẩy tất cả transaction qua Kafka và coi eventual consistency là đủ không?

**Gợi ý:** Không. Bất biến số dư phải được bảo vệ trong ranh giới sở hữu phù hợp, bằng transaction/concurrency control và quy tắc sổ cái rõ ràng. Kafka có thể đưa lệnh/sự kiện qua các thành phần, nhưng không thay thế tính đúng đắn cục bộ.

### Bài tập 7 — Chọn giữa REST và gRPC

Hai service nội bộ có 100 request/giây với payload 2 KB. Một người đề nghị chuyển gRPC chỉ vì “gRPC nhẹ hơn”.

**Gợi ý:** Chưa đủ bằng chứng. Đo p95/p99, CPU, byte transfer, connection behavior, lỗi và nhu cầu contract/tooling; cân nhắc chi phí chuyển đổi. Với tải nhỏ và latency hiện đáp ứng SLO, giữ HTTP/JSON có thể là lựa chọn tốt.

### Bài tập 8 — Mỗi service một kiểu giao thức

Hệ thống dùng REST cho public API, gRPC giữa hai dịch vụ tính toán, queue cho email và event stream cho analytics. Thiết kế này có “không nhất quán” vì nhiều protocol không?

**Gợi ý:** Không nhất thiết. Nếu mỗi đường giao tiếp có lý do rõ ràng, hợp đồng được quản trị, tracing xuyên luồng hoạt động và đội vận hành có năng lực, kiến trúc hỗn hợp có thể hợp lý. Rủi ro là tăng công cụ và cách xử lý lỗi, cần đánh giá chi phí thật.

## 21. Checklist thiết kế một đường giao tiếp

Trước khi triển khai, ghi rõ:

- [ ] Đây là query, command hay event; chủ sở hữu nghiệp vụ là ai?
- [ ] Consumer cần kết quả ngay hay có thể nhận ACK/PENDING?
- [ ] SLO, deadline và timeout của cả đường xử lý là bao nhiêu?
- [ ] Trạng thái/bất biến nào phải được giữ cục bộ trong transaction?
- [ ] Phần nào được eventual consistency và stale window được phép là bao nhiêu?
- [ ] Có cần bên nhận online đồng thời; khi dependency lỗi thì caller làm gì?
- [ ] Hợp đồng có schema, version, semantics và error behavior rõ chưa?
- [ ] Với thao tác ghi, có idempotency key và xử lý unknown outcome chưa?
- [ ] Với async, có outbox/inbox hoặc cơ chế tránh mất/trùng theo phạm vi cần thiết chưa?
- [ ] Thứ tự sự kiện có quan trọng; ordering key và partition có phù hợp chưa?
- [ ] Có giới hạn retry, backoff, DLQ, replay và reconciliation chưa?
- [ ] Có tracing/correlation ID, logs, metrics và alert cho cả luồng chưa?
- [ ] Đã đo tải, độ trễ, fan-out, queue lag và chi phí vận hành chưa?
- [ ] Đã xác minh phương án đơn giản hơn đáp ứng được yêu cầu chưa?

Checklist giúp làm rõ giả định, không phải lời khẳng định rằng mọi giao tiếp đều cần đủ mọi hạ tầng kể trên. Chỉ dùng thành phần phục vụ ràng buộc thực tế.

## 22. Ghi nhớ

1. **Chọn theo tương tác và yêu cầu nghiệp vụ trước, chọn công nghệ sau.** REST, gRPC, queue, pub/sub và streaming phục vụ các kiểu phối hợp khác nhau.
2. **Độ trễ là ngân sách end-to-end.** Quan sát critical path, fan-out, timeout, retry và SLO; ACK nhanh không có nghĩa tác vụ hoàn tất nhanh.
3. **Tính nhất quán gắn với invariant và quyền sở hữu dữ liệu.** Giao thức đồng bộ không tự tạo atomic transaction giữa hai service; async không tự tạo eventual consistency đúng.
4. **Coupling có nhiều dạng.** Messaging giảm temporal coupling nhưng vẫn cần quản lý schema, semantics, ordering, deployment và operation.
5. **Chọn REST/gRPC cho những lời gọi cần phản hồi trực tiếp; dùng queue/event khi công việc có thể hoàn tất sau hoặc nhiều consumer cần phản ứng độc lập.** Đây là xu hướng khởi đầu, không phải luật cứng.
6. **Các failure mode quyết định độ tin cậy:** timeout không đồng nghĩa thất bại, retry có thể gây trùng, event có thể đến muộn và downstream projection có thể stale.
7. **Outbox, idempotency, deadline, contract versioning, tracing và reconciliation** thường quan trọng hơn việc đổi tên giao thức.
8. **Kiến trúc hỗn hợp có thể tốt.** Một hệ thống có thể dùng HTTP, gRPC và messaging tại các ranh giới khác nhau nếu chúng giải quyết đúng yêu cầu và đội ngũ vận hành được.