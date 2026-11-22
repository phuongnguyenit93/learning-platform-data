# Phân tích trace, span và đường đi quan trọng của yêu cầu

## 1. Mục tiêu

Khi hệ thống chuyển từ ứng dụng đơn khối sang Microservices, một yêu cầu có thể đi qua API Gateway, nhiều service, cache, database, message broker và nhà cung cấp bên ngoài. Nếu người dùng phàn nàn rằng thao tác thanh toán mất 3 giây, log của từng service thường không trả lời đầy đủ: 3 giây đó được tiêu ở đâu, service nào đang chờ service nào, có retry hay không, và tối ưu thành phần nào sẽ thực sự giảm độ trễ cuối cùng?

**Distributed tracing** theo dõi luồng xử lý của một hoạt động qua các ranh giới tiến trình và hạ tầng. **Trace** mô tả hành trình tổng thể, **span** mô tả một đơn vị công việc trong hành trình ấy, còn **critical path** là chuỗi phụ thuộc khiến yêu cầu chưa thể hoàn thành sớm hơn.

Bài này giúp người học:

- Đọc trace ID, span ID, parent span, span kind, duration, attributes, events, status và links.
- Quan sát một waterfall timeline, call tree và các lời gọi chạy song song.
- Phân biệt tổng thời gian request với thời gian của một RPC, truy vấn database hoặc hàng đợi.
- Tìm đúng đoạn chặn tiến trình (critical path) thay vì chọn bừa span dài nhất.
- Nhận diện retry storm, N+1 query, fan-out, queue lag, connection pool wait, lock contention và instrumentation gap.
- Phân tích trace khi có timeout, lỗi lan truyền, sampling, clock skew và tác vụ bất đồng bộ.
- Liên kết trace với log, metrics và SLO để quyết định tối ưu và xác minh tác động.

Ví dụ xuyên suốt là một request POST /checkout, từ lúc người dùng xác nhận giỏ hàng tới lúc hệ thống tạo đơn.

## 2. Trace là gì?

Một **trace** là tập hợp các span được liên kết nhằm mô tả một hoạt động, thường được xác định bởi một **trace ID** chung. Trace có thể đi qua nhiều service và có cả các span thành công lẫn thất bại. Một trace không nhất thiết chỉ có một lời gọi: nó có thể phản ánh nhiều RPC, truy vấn và bước xử lý nghiệp vụ.

Ví dụ kiến trúc:

~~~text
Client
  |
  v
API Gateway --> Checkout Service
                    |
                    +----> User Service ----> PostgreSQL
                    |
                    +----> Inventory Service -> Cache -> Database
                    |
                    +----> Pricing Service ---> Cache
                    |
                    v
               Payment Service ---> Provider API
                    |
                    v
               Order Service -----> Database
                    |
                    v
                 HTTP 201
~~~

Nếu tất cả các thành phần truyền đúng trace context, người vận hành có thể tìm một trace ID và xem các hoạt động liên quan thay vì dò từng log bằng tay.

Trace ID **không phải** token xác thực, cũng không chứng minh rằng người gọi có quyền xem mọi tài nguyên. Quyền truy cập dữ liệu observability cần quản lý riêng.

## 3. Span là gì?

Một **span** là một đơn vị công việc có điểm bắt đầu và kết thúc. Ví dụ:

- Inbound HTTP request POST /checkout: span kiểu SERVER.
- Checkout Service gọi Payment Service: span kiểu CLIENT.
- Payment Service nhận và xử lý lời gọi: span kiểu SERVER.
- Pricing Service tính giá: span kiểu INTERNAL.
- Producer đưa message lên queue: span kiểu PRODUCER.
- Consumer nhận và xử lý message: span kiểu CONSUMER.

Một bản ghi span thường chứa:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| trace_id | Định danh trace | 4bf92f...e4736 |
| span_id | Định danh span trong trace | 00f067...7b |
| parent_span_id | Span cha nếu có | 9ca88...21 |
| name | Tên thao tác ổn định | POST /checkout |
| kind | SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER | SERVER |
| start/end | Mốc thời gian thực hiện | 10:00:00.100 → 10:00:00.350 |
| duration | end - start | 250 ms |
| attributes | Thuộc tính có cấu trúc | http.request.method, service.name |
| events | Sự kiện xảy ra trong span | retry.scheduled |
| status | Tình trạng theo tracing API | UNSET, OK, ERROR |
| links | Liên kết span context không cùng quan hệ cha-con | message source, fan-in |

### Span cha và con

~~~text
checkout.request [SERVER]
  |
  +-- user.fetch [CLIENT]
  |     +-- user.fetch [SERVER]
  |            +-- db.get_user [CLIENT]
  |
  +-- payment.authorize [CLIENT]
        +-- payment.authorize [SERVER]
               +-- provider.charge [CLIENT]
~~~

Cùng một RPC có thể có CLIENT span ở bên gửi và SERVER span ở bên nhận. Đây là góc nhìn hai đầu của cùng tương tác, không phải bằng chứng một request đã được gọi hai lần.

Quan hệ parent-child thường thể hiện **ngữ cảnh thực thi**. Nó không luôn tương đương với việc parent phải chờ con hoàn thành; trong async workflows, một span có thể kết thúc sau khi đã lên lịch task con.

## 4. Phân biệt các loại thời gian

**Wall-clock duration** của span là thời điểm kết thúc trừ thời điểm bắt đầu. Đó không đồng nghĩa với CPU time. Span dài có thể phần lớn là chờ socket, database connection, network, lock hoặc scheduler.

**Inclusive time** là toàn bộ duration của span, kể cả khi có child span đang chạy bên trong. **Exclusive/self time** trong một công cụ thường là phần thời gian không do các child span đã quan sát chiếm dụng; cách tính thực tế tùy công cụ và đặc điểm overlap.

**Queue wait** là thời gian một công việc nằm trong hàng đợi trước khi consumer thực thi. **Service time** là thời gian xử lý khi đã được phục vụ; ranh giới và instrumentation phải đủ rõ mới tách được.

Ví dụ một parent dài 600 ms và hai child chạy song song:

~~~text
Parent:    [========================================] 600 ms
Child A:        [======================]             300 ms
Child B:           [==========================]       350 ms
~~~

Nếu cộng 300 + 350 = 650 ms rồi trừ khỏi parent 600 ms, sẽ có self time âm. Điều này là sai vì các child overlap. Để tính thời gian parent nằm ngoài child, phải lấy **hợp của các khoảng child** và các đoạn thời gian không overlap. Kể cả phần thời gian còn lại cũng không nhất thiết là CPU: nó có thể là công việc chưa được instrument.

**Sai lầm thường gặp:** cộng duration của parent và mọi child như các bước tuần tự. Đó là đếm trùng khi span lồng nhau và chồng lấn.

## 5. Hiểu waterfall timeline

Waterfall là biểu đồ thể hiện span thành thanh ngang trên một trục thời gian chung.

~~~text
ms         0      200      400      600      800     1000
           |--------|--------|--------|--------|--------|
checkout   [============================================]
auth         [===]
cart.read      [======]
inventory           [======================]
pricing             [=======]
profile             [==========]
payment                                    [============]
save.order                                               [==]
~~~

Thanh bắt đầu càng về bên phải thì span bắt đầu càng muộn. Các thanh cùng mốc và overlap có thể là lời gọi song song. Thanh cha dài hơn các thanh con có thể chứa overhead, logic nghiệp vụ hoặc khoảng chờ chưa instrument.

Đọc waterfall theo trình tự:

1. Chọn **root span** và đọc duration, endpoint, service, status.
2. Xác định các nhánh chính: bước nào nối tiếp, bước nào chạy song song.
3. Xem các span dài gần mốc request kết thúc và điểm chuyển giữa các giai đoạn.
4. Đối chiếu lỗi ở child, retry, thời gian chờ và các khoảng trống.
5. Mở attributes/events để biết vì sao một span kéo dài.
6. So sánh với trace nhanh cùng endpoint và thời gian gần đó.
7. Kiểm tra metrics/logs trước khi kết luận nguyên nhân.

Một số công cụ sắp xếp waterfall theo call tree, không phải hoàn toàn theo start time. Hãy đọc timestamp và duration khi các thanh khiến thứ tự khó hiểu.

## 6. Critical path: khái niệm cốt lõi

**Đường đi quan trọng** là chuỗi công việc có quan hệ phụ thuộc quyết định mốc hoàn tất. Nếu rút ngắn một bước trên đường này, tổng latency có thể giảm; nếu rút ngắn một bước ngoài đường này mà nhánh khác vẫn chặn, tổng latency không thay đổi.

Critical path không đơn giản là:

- Span dài nhất của trace.
- Tổng duration các span.
- Nhánh nhiều span nhất.
- Nhánh parent-child dài nhất nếu không tính overlap và quan hệ chờ.

Trong hệ thống phân tán, cần hiểu **thời điểm**, **quan hệ phụ thuộc**, **điểm đồng bộ** và **các khoảng chờ**.

### 6.1. Chuỗi tuần tự

~~~text
Validate        100 ms
Read cart       150 ms
Calculate       200 ms
Payment         650 ms
Persist order   100 ms
Response         50 ms
----------------------
Tổng          1.250 ms
~~~

Nếu sáu bước thực sự nối tiếp, không overlap và không có overhead bổ sung, tổng là 1.250 ms. Giảm Payment từ 650 xuống 350 ms có thể giảm latency xuống 950 ms.

Trường hợp này toàn bộ chuỗi là critical path.

### 6.2. Fan-out/fan-in song song

Giả sử ba lời gọi Inventory, Pricing và Profile bắt đầu cùng thời điểm. Payment chỉ chạy sau khi có **đầy đủ cả ba kết quả**.

~~~text
           +---- Inventory: 700 ms ----+
Checkout --+---- Pricing:   250 ms ----+--> Join --> Payment: 400 ms
           +---- Profile:   450 ms ----+
                                                 --> Save: 100 ms
~~~

Với giả định không có overhead:

~~~text
Tổng = max(700, 250, 450) + 400 + 100
     = 1.200 ms
~~~

Inventory là nhánh critical của giai đoạn song song. Giảm Pricing từ 250 xuống 50 ms không cải thiện tổng request. Giảm Inventory từ 700 xuống 400 ms khiến Profile 450 ms trở thành nhánh critical; tổng còn khoảng 950 ms.

**Nút thắt chuyển chỗ sau khi tối ưu** là hiện tượng bình thường. Không thể chọn một nhánh để tối ưu mãi mà không đo lại critical path.

### 6.3. Join không phải lúc nào chờ tất cả

Một hệ thống có thể chỉ cần kết quả thành công đầu tiên, quorum 2/3, hoặc một số nhánh là tùy chọn.

~~~text
Replica A: 250 ms
Replica B: 600 ms
Replica C: 900 ms
~~~

Nếu response đã đủ dữ liệu từ Replica A ở 250 ms và các request còn lại được hủy đúng cách, Replica C dài 900 ms không nhất thiết chi phối latency người dùng. Với quorum 2/3, điểm hoàn tất phụ thuộc kết quả thành công thứ hai và lỗi của từng nhánh.

Raw span tree thường không chứa đầy đủ join policy. Muốn phân tích chính xác phải biết logic nghiệp vụ hoặc có event ghi mốc "đã đủ kết quả để tiếp tục".

## 7. Quy trình tìm đường đi quan trọng từ một trace

### Bước 1 — Xác định phạm vi yêu cầu

Ghi root operation, route, service, version, environment, trace ID, start/end, duration và kết quả. Nếu root span không có do sampling/drop hoặc do client nằm ngoài vùng instrument, dùng dữ liệu khác để hiểu phạm vi quan sát.

### Bước 2 — Phân đoạn xử lý

Chia một request thành các giai đoạn như validate, read, fan-out, join, payment, persist và response. Tìm các đoạn có mốc bắt đầu/kết thúc rõ.

### Bước 3 — Tìm điểm chờ

Đọc thời điểm chuyển sang giai đoạn tiếp. Nếu Payment bắt đầu chỉ sau khi Inventory hoàn tất, hãy kiểm tra Checkout chờ tất cả response hay chỉ một. Xác định span hoặc event thực sự **mở khóa** bước tiếp theo.

### Bước 4 — Truy ngược từ lúc request kết thúc

Đi ngược từ response end tới công việc cuối cùng cần hoàn thành. Ở mỗi điểm join, chọn nhánh mà việc hoàn thành của nó quyết định thời điểm tiếp tục. Tiếp tục tới root start. Đường thu được là một ứng viên critical path.

### Bước 5 — Tránh đếm trùng

Nếu span cha bao phủ các child, không cộng parent duration vào đường đi. Phân đoạn thời gian thực thành local work, child work, waiting và overhead; nếu không đủ dữ liệu thì nêu rõ đây là ước lượng.

### Bước 6 — Giải thích nguyên nhân thời gian dài

Một span 800 ms có thể gồm 500 ms chờ DB pool, 100 ms chạy SQL, 200 ms network/serialization. Dùng attributes/events, metrics, log và các span con để đi sâu.

### Bước 7 — Ước lượng lợi ích

Nếu hai nhánh song song kết thúc ở 700 và 600 ms, tăng tốc nhánh đầu tối đa 100 ms trước khi nhánh thứ hai trở thành critical, nếu giữ nguyên các phần khác.

### Bước 8 — Xác nhận trên nhiều request

Một trace đơn lẻ có thể đại diện cache miss, cold start, một instance kém hoặc ngoại lệ tạm thời. Xem phân bố request nhanh/chậm, error/success, deployment version và vùng dữ liệu trước khi thay đổi.

## 8. Ví dụ thực hành: Checkout mất 1.800 ms

Cho dữ liệu trace:

| Span | Start (ms) | End (ms) | Duration (ms) | Vai trò |
|---|---:|---:|---:|---|
| checkout.request | 0 | 1800 | 1800 | Root |
| authenticate | 20 | 100 | 80 | Local |
| cart.read | 120 | 280 | 160 | DB |
| inventory.reserve | 300 | 1050 | 750 | RPC |
| price.calculate | 300 | 520 | 220 | RPC song song |
| shipping.quote | 300 | 680 | 380 | RPC song song |
| payment.authorize | 1080 | 1640 | 560 | Sau join |
| order.save | 1660 | 1750 | 90 | Transaction |
| response.encode | 1750 | 1800 | 50 | Local |

Inventory/Pricing/Shipping chạy đồng thời sau cart.read. Payment bắt đầu sau khi tất cả kết thúc. Vì Inventory hoàn tất sau cùng, đường đi quan trọng đi qua:

~~~text
authenticate -> cart.read -> inventory.reserve
             -> payment.authorize -> order.save -> response.encode
~~~

Tổng các duration trên đường này là 80 + 160 + 750 + 560 + 90 + 50 = 1.690 ms. Còn **110 ms khoảng trống** ở các đoạn 0–20, 100–120, 280–300, 1050–1080 và 1640–1660. Cần giải thích bằng overhead, scheduling, instrumentation hoặc bước khác. Không được bỏ 110 ms chỉ vì không có child span.

Nếu tối ưu Shipping từ 380 xuống 100 ms, tổng vẫn gần 1.800 ms vì Inventory chưa đổi. Nếu tối ưu Inventory từ 750 xuống 300 ms, Shipping 380 ms sẽ trở thành nhánh chặn; Payment có thể bắt đầu khoảng 710 ms thay vì 1080 ms, nên tổng gần 1.430 ms nếu những phần còn lại giữ nguyên.

Ví dụ cho thấy **khả năng cải thiện end-to-end** khác với số millisecond giảm được của một thành phần.

## 9. Đọc CLIENT span và SERVER span của một RPC

Giả sử:

~~~text
Service A CLIENT span: [=======================] 400 ms
Service B SERVER span:    [=================]     300 ms
~~~

CLIENT span có thể bao gồm lấy connection, DNS/TLS, middleware, gửi request, chờ response, đọc/deserialize và retry. SERVER span thường đo đoạn xử lý tại service nhận, tùy instrumentation.

Nếu CLIENT dài 800 ms nhưng SERVER chỉ 50 ms, không nên tự động kết luận mạng mất 750 ms. Có thể là:

- Chờ connection pool trước khi gửi request.
- Retry nhiều lần và một span CLIENT bao trùm mọi attempt.
- Proxy/load balancer xếp hàng request.
- Request/response lớn gây serialization hoặc streaming.
- Lệch đồng hồ giữa các host.
- Server span bỏ sót phần thời gian xử lý.
- Context propagation làm các span thuộc các trace khác nhau.
- Client vẫn chờ callback sau khi server đã gửi response.

Hãy kiểm tra timeline từng attempt, thời gian pool acquire, proxy metrics và log ở hai đầu trước khi đưa ra chẩn đoán.

## 10. Các mẫu hiệu năng cần nhận diện

### 10.1. N+1 queries

~~~text
orders.list
  db.list_orders        24 ms
  db.get_customer_1      8 ms
  db.get_customer_2      7 ms
  db.get_customer_3      9 ms
  ...
  db.get_customer_100    9 ms
~~~

Dấu hiệu là nhiều query tương tự lặp theo số record. Truy vấn riêng lẻ nhanh, nhưng tổng latency lớn. Cân nhắc batch fetch, JOIN đúng mục đích, prefetch, DataLoader hoặc sửa ranh giới API. Xem thêm query plan và lưu lượng DB để tránh tạo JOIN quá rộng.

### 10.2. Retry và backoff

~~~text
inventory.attempt_1   120 ms --> 503
retry.wait            200 ms
inventory.attempt_2   140 ms --> 503
retry.wait            400 ms
inventory.attempt_3   130 ms --> 200
~~~

Một parent span kéo dài vì các attempt lặp và khoảng chờ. Có thể thêm event retry.scheduled (attempt, delay) để giải thích. Kiểm tra bounded retry, jitter, deadline, idempotency và retry ở nhiều tầng khi thấy sự khuếch đại lời gọi.

### 10.3. Connection pool wait

~~~text
db.acquire_connection   450 ms
db.query                 30 ms
~~~

Không nên tập trung tối ưu query 30 ms khi request chủ yếu chờ pool 450 ms. Kiểm tra pool active/idle/waiters, transaction sống lâu, concurrency và DB saturation.

### 10.4. Database lock contention

~~~text
db.update_order  800 ms
  lock.wait      700 ms
  statement       80 ms
~~~

Nếu tracing chưa instrument lock wait, cần dùng DB wait event, slow query log, execution plan hoặc transaction metrics để xác định nguyên nhân.

### 10.5. Fan-out quá lớn

Một request đồng thời gọi 80 dependency. Tổng duration child có thể lên hàng chục giây dù root chưa tới một giây, vì overlap. Điều đáng lo là tải connection pool, memory, CPU, queue, quota và xác suất gặp lỗi. Kiểm tra giới hạn concurrency, batching và hợp đồng tổng hợp kết quả.

### 10.6. Queue lag

~~~text
message.produce        15 ms
queue.wait          8000 ms
message.consume      200 ms
~~~

HTTP có thể trả 202 sau 15 ms, nhưng người dùng đợi hơn 8 giây để thấy kết quả. Cần đo thêm **business completion latency**, backlog và tuổi message. Không chỉ dùng latency của inbound HTTP.

### 10.7. Cold start và cache miss

Một số trace chậm xuất hiện trên instance mới sau deploy, khi khởi tạo TLS, database pool, cache hoặc class loading. So sánh theo instance/version/cache.hit để phân biệt chậm hệ thống kéo dài với cold start ngắn hạn.

### 10.8. Instrumentation gap

Parent span có duration 900 ms nhưng các child chỉ chiếm một khoảng rất nhỏ. Không vội kết luận local CPU chậm: có thể đang chờ lock, GC, task async, scheduler hoặc thiếu instrumentation. Bổ sung một vài span/event nghiệp vụ có ý nghĩa rồi đo lại.

## 11. Attributes, events, status và exception

Một span có giá trị phân tích khi cung cấp thông tin có thể hành động:

~~~text
Span payment.authorize
  attributes:
    payment.provider = provider-a
    retry.max_attempts = 3
    operation.type = authorization
  events:
    100 ms: provider.timeout
    120 ms: retry.scheduled (delay_ms=250)
    370 ms: retry.attempt (attempt=2)
    700 ms: provider.response (outcome=success)
~~~

Attributes là thông tin cấu trúc; events ghi mốc trong span; exception có thể được ghi qua API instrumentation; status cung cấp phân loại chung.

Trong OpenTelemetry, status thường là UNSET, OK hoặc ERROR. **UNSET không tự động có nghĩa là lỗi**. Một child lỗi không nhất thiết khiến root lỗi nếu ứng dụng có fallback hoặc retry thành công. Ngược lại, một request thất bại ở ngoài tầm instrumentation có thể không được đánh dấu đúng. Luôn đối chiếu final outcome.

Các attribute hữu ích có thể là service.name, service.version, deployment environment, http route đã chuẩn hóa, db.system, db.operation, messaging destination, error.type, retry attempt và cache.hit. Tên cụ thể tùy semantic conventions đang dùng; không hardcode giả định về mọi phiên bản thư viện.

Đặt tên span ổn định:

~~~text
Tốt:  GET /orders/{id}
Kém: GET /orders/123456789
~~~

Không dùng raw URL chứa PII hoặc token làm tên span. Không tạo span cho từng dòng code hoặc hàng trăm thao tác cực nhỏ nếu không phục vụ mục tiêu vận hành.

## 12. Propagation: nối trace qua service

Để các span ở nhiều service cùng thuộc một trace, cần truyền **trace context** qua ranh giới mạng và bất đồng bộ. Với HTTP, chuẩn W3C Trace Context phổ biến dùng traceparent và tracestate.

Ví dụ một traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Nó gồm version, trace ID, parent span ID và trace flags. Đây là thông tin tracing, không phải credential bảo mật.

Luồng khái niệm:

~~~text
Checkout Service:
  tạo CLIENT span
  inject trace context vào request
             |
             v
Inventory Service:
  extract trace context
  tạo SERVER span liên kết cùng trace
  tạo INTERNAL/CLIENT span cho bước con
~~~

Nếu một service quên inject hoặc extract, trace có thể bị tách thành nhiều root/trace. Với asynchronous executors hoặc reactive pipelines, context có thể bị mất khi chuyển thread nếu runtime không tự propagate. Phải kiểm tra instrumentation của framework và đóng scope đúng cách.

**Không coi trace context từ bên ngoài là đáng tin về mặt bảo mật.** Có thể cần sanitize, giới hạn header size, kiểm soát baggage và quyết định tiếp tục hay bắt đầu trace mới tại trust boundary.

## 13. Async, queue, event và span links

Trong messaging, PRODUCER span thường ghi gửi message; CONSUMER span ghi việc xử lý message. Nếu một consumer xử lý batch từ nhiều message độc lập, lựa chọn một parent duy nhất có thể làm sai quan hệ nhân quả. **Span links** hỗ trợ tham chiếu nhiều span context khác nhau mà không áp quan hệ cha/con không đúng.

Ví dụ:

~~~text
Trace A: order.created PRODUCER ----\
                                     \ links
                                      >-- batch.process CONSUMER
                                     /
Trace B: order.updated PRODUCER ----/
~~~

Với replay/redelivery, không tự coi các lần nhận cùng event là các nghiệp vụ độc lập. Gắn message ID, attempt/redelivery state theo chính sách bảo mật và dùng idempotency ở consumer.

Nếu một saga kéo dài nhiều ngày, giữ một root span mở nhiều ngày thường không hiệu quả. Có thể dùng nhiều trace ngắn liên kết qua business correlation ID, job ID và span links; đo business completion latency bằng metrics riêng.

## 14. Sampling và partial trace

Không phải tất cả request đều được lưu trace.

| Chính sách | Cách hoạt động | Ảnh hưởng |
|---|---|---|
| Always-on | Thu mọi trace | Tốn chi phí ingestion/storage |
| Head-based | Quyết định sampling gần đầu request | Có thể bỏ sót lỗi hiếm hoặc p99 |
| Parent-based | Tuân theo quyết định sampling từ parent | Giữ quyết định nhất quán giữa các nhánh |
| Tail-based | Chờ thấy đủ dữ liệu trước khi quyết định | Có thể ưu tiên lỗi/chậm, tốn buffer |
| Rule-based | Chọn theo endpoint, error hoặc nhóm nghiệp vụ | Dễ tạo bias nếu dùng để suy ra tỷ lệ lỗi |

**Đừng đếm tỷ lệ trace lỗi trong tập tail-sampled rồi gọi đó là error rate toàn hệ thống.** Tập này có thể giữ phần lớn lỗi nhưng chỉ một phần request thành công. Dùng metric counter/histogram đã được tính đúng để đánh giá SLI/SLO; trace dùng để chẩn đoán trường hợp cụ thể.

Phân biệt các hiện tượng:

- **Sampling:** trace không được chọn lưu.
- **Drop:** span bị mất do SDK/collector queue, exporter hoặc quota.
- **Propagation lỗi:** các thành phần tạo trace ID không liên kết.
- **Ingestion delay:** span đến backend chậm và có thể xuất hiện sau.
- **Instrumentation thiếu:** code chạy nhưng không tạo span.

Khi thấy một trace "không gọi dependency", không thể chắc nó thực sự không gọi nếu chưa kiểm tra mức độ đầy đủ.

## 15. Clock skew và timestamp xuyên host

Span ở nhiều máy dùng đồng hồ khác nhau. Đồng bộ thời gian kém có thể khiến SERVER span bắt đầu "trước" thời điểm CLIENT gửi hoặc parent kết thúc trước child theo dữ liệu ghi nhận.

Khi gặp timestamp bất hợp lý:

1. Xác định các span có nằm cùng host/clock domain hay không.
2. Kiểm tra NTP/time synchronization và thay đổi thời gian hệ thống.
3. Dựa vào quan hệ nhân quả (request send/receive) và context, không dựa hoàn toàn vào số timestamp.
4. Xem công cụ tracing có áp dụng clock-skew correction hay không.
5. Với duration một thao tác nội bộ, ưu tiên nguồn đo thời gian đơn điệu nếu SDK/runtime hỗ trợ.

Critical path đòi hỏi quan hệ chờ chính xác. Một waterfall đẹp nhưng được dựng từ đồng hồ lệch vẫn có thể gây hiểu nhầm.

## 16. Phân tích đồ thị phụ thuộc

Nếu công việc được mô hình thành DAG (directed acyclic graph), mỗi node là một **task với duration riêng** và cạnh biểu diễn phụ thuộc hoàn tất, critical path có thể tính bằng longest path trên DAG.

Ví dụ:

~~~text
                 +-- B: 300 ms --+
A: 100 ms -------+                +--> D: 200 ms
                 +-- C: 500 ms --+
~~~

B và C bắt đầu sau A; D chờ cả B/C:

~~~text
earliestFinish(A) = 100
earliestFinish(B) = 100 + 300 = 400
earliestFinish(C) = 100 + 500 = 600
earliestFinish(D) = max(400,600) + 200 = 800
critical path = A -> C -> D
~~~

Công thức:

~~~text
EF(v) = duration(v) + max(EF(u) với u là predecessor của v)
EF(v) = duration(v) nếu không có predecessor
~~~

Duyệt theo topological order, lưu predecessor có EF lớn nhất rồi truy ngược từ node kết thúc.

**Không áp dụng trực tiếp công thức này lên raw parent-child span tree** vì parent thường bao trùm child; dùng cả duration parent làm node riêng sẽ đếm trùng. Cần chuyển trace thành các đoạn công việc/chờ không overlap hoặc một DAG phụ thuộc đã được instrument đầy đủ.

Ví dụ parent 620 ms chứa local compute 50 ms, hai RPC song song 300/500 ms, rồi local compute 70 ms. Critical path có thể là 50 + 500 + 70 = 620 ms, không cộng thêm một lần 620 ms của parent.

Nếu không biết chính xác join policy, scheduling hoặc trạng thái các dependency, kết quả phải được xem là **ước lượng có điều kiện**. Tăng instrumentation vào các mốc fork/join để kết luận chắc chắn hơn.

## 17. Kết nối trace, metrics và logs

Ba tín hiệu quan sát bổ trợ nhau:

| Tín hiệu | Câu hỏi trả lời tốt nhất |
|---|---|
| Metrics | Hệ thống đang chậm/lỗi bao nhiêu, xu hướng có vượt SLO không? |
| Traces | Một request cụ thể đi qua đâu, chờ ai và thất bại tại bước nào? |
| Logs | Khi lỗi xảy ra có sự kiện chi tiết nào, mã lỗi và ngữ cảnh chẩn đoán là gì? |

Luồng điều tra:

~~~text
Alert: p95 /checkout tăng
  |
  v
Metric: xác định route, thời gian, version, traffic, error rate
  |
  v
Chọn exemplar hoặc trace chậm liên quan
  |
  v
Trace: đọc waterfall, critical path, retry, queue/DB wait
  |
  v
Log + metrics dependency: xác nhận nguyên nhân
  |
  v
Thay đổi -> đo lại SLI và trace sau triển khai
~~~

Log nên mang trace ID và span ID khi có current span, giúp chuyển từ log sang trace và ngược lại. **Exemplar** có thể nối một mẫu quan sát metric (như histogram latency) tới một trace tiêu biểu. Chi tiết triển khai tùy nền tảng.

Một trace cực chậm không chứng minh p95 toàn hệ thống chậm; dùng dashboard metrics để đo phân bố và chỉ dùng trace để giải thích nguyên nhân.

## 18. Ví dụ Java với OpenTelemetry API

Auto-instrumentation có thể tạo span cho HTTP, JDBC, messaging và nhiều framework. Với bước nghiệp vụ đáng chú ý như reserve inventory, có thể thêm một INTERNAL span thủ công.

Ví dụ mã Java có cấu trúc tối thiểu:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryApplicationService {
    private final Tracer tracer;
    private final InventoryClient inventoryClient;

    public InventoryApplicationService(
            Tracer tracer,
            InventoryClient inventoryClient
    ) {
        this.tracer = tracer;
        this.inventoryClient = inventoryClient;
    }

    public ReservationResult reserve(String orderId) {
        Span span = tracer.spanBuilder("inventory.reserve-business")
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("business.operation", "reserve");
            ReservationResult result = inventoryClient.reserve(orderId);
            span.addEvent("inventory.reservation.completed");
            return result;
        } catch (RuntimeException exception) {
            span.recordException(exception);
            span.setStatus(StatusCode.ERROR, "reservation failed");
            throw exception;
        } finally {
            span.end();
        }
    }
}
~~~

InventoryClient và ReservationResult ở đây là type ứng dụng cần định nghĩa. Tracer phải được cấp từ instrumentation/SDK đang cấu hình. Nếu HTTP client đã auto-instrument, outbound CLIENT span thường được tạo dưới current span.

Không tùy tiện ghi orderId hoặc toàn bộ payload vào span attribute. Những giá trị đó có thể chứa dữ liệu cá nhân hoặc làm tăng cardinality và chi phí. Nên ưu tiên tên operation, mã loại nghiệp vụ và thuộc tính đã được duyệt.

### 18.1. Context propagation qua thread pool

Một thread pool không nhất thiết tự mang context theo task. Với OpenTelemetry API, có thể capture context rồi attach trong task:

~~~java
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;

Context parentContext = Context.current();
executor.submit(() -> {
    try (Scope outer = parentContext.makeCurrent()) {
        Span span = tracer.spanBuilder("pricing.calculate").startSpan();
        try (Scope inner = span.makeCurrent()) {
            pricing.calculate();
        } finally {
            span.end();
        }
    }
});
~~~

Đây là ví dụ khái niệm; cần có executor, tracer, pricing và các import tương ứng. Nếu framework cung cấp context-aware executor hoặc instrumentation tự động, nên dùng cơ chế chuẩn đó để giảm lỗi gắn nhầm trace giữa các task. Xác minh bằng trace thực tế, đặc biệt với reactive runtime.

### 18.2. Events cho các điểm nghiệp vụ

Một span dài nên ghi các mốc phục vụ phân tích:

~~~text
checkout.process
  event cart.loaded
  event fanout.started
  event pricing.finished
  event inventory.finished
  event dependencies.ready
  event payment.authorized
  event order.committed
~~~

Event dependencies.ready giúp nhìn rõ điểm join thay vì phải đoán từ khoảng thanh waterfall.

Không biến mọi lệnh code thành một span hoặc event; instrumentation quá dày có thể ảnh hưởng hiệu năng, cardinality và chi phí.

## 19. Đọc lỗi, timeout và cancellation

Lỗi trên trace có thể là **nguyên nhân**, **hậu quả lan truyền** hoặc **một lần thử lại không thành công nhưng request cuối vẫn thành công**.

Ví dụ:

~~~text
checkout.request              ERROR
  payment.authorize CLIENT    ERROR, timeout
    payment.authorize SERVER  OK, xử lý thành công
  retry.wait                  200 ms
  payment.authorize CLIENT    ERROR, duplicate/conflict
~~~

Server có thể đã ghi giao dịch nhưng response bị mất trên đường về. Retry cùng lệnh thanh toán cần idempotency key và đối soát trạng thái, không được hiểu timeout là server chưa thực hiện.

Nếu client hủy request, backend vẫn có thể xử lý một thời gian nếu cancellation không được lan truyền. Trace cần phản ánh cancellation phù hợp, đồng thời metrics theo dõi task bị bỏ lại, connection còn giữ và side effects.

Với HTTP 4xx, không nhất thiết đánh dấu lỗi hạ tầng: một request input không hợp lệ có thể là phản hồi dự kiến. Quy tắc error classification phải nhất quán với metric SLI và semantic convention.

## 20. Quy trình xử lý incident khi p99 tăng

Giả sử lúc 14:00, p99 của /checkout tăng từ 1,2 giây lên 3,5 giây, error rate thay đổi ít.

**Bước 1: Xác định phạm vi.** Chọn environment, endpoint, traffic, service version, vùng và thời điểm deploy; xem p50/p95/p99, CPU, memory, saturation, queue depth.

**Bước 2: Chọn trace đại diện.** Lấy vài trace nhanh trước 14:00 và trace chậm sau đó. Phân nhóm theo instance, cache hit/miss, user flow và thành công/thất bại.

**Bước 3: Tìm critical path.** Xem giai đoạn chặn response: inventory, payment, database hay queue. Chú ý khoảng trống và retry.

**Bước 4: Xác nhận với dependency metrics.** Ví dụ trace cho thấy db.acquire_connection tăng 1.200 ms; kiểm tra pool active/idle/waiters, DB query, transaction duration và saturation.

**Bước 5: Sửa nguyên nhân.** Có thể là transaction giữ connection quá lâu, N+1, concurrency bùng nổ hoặc cấu hình pool thiếu phù hợp. Không mặc định tăng pool size: database có thể đã quá tải.

**Bước 6: Đo lại.** So sánh SLI, trace distribution và dependency metrics sau thay đổi ở điều kiện tải tương tự. Nếu payment trở thành nhánh critical mới, đó là dấu hiệu bottleneck đã chuyển, không có nghĩa tối ưu trước vô ích.

Những bước này biến tracing thành công cụ ra quyết định thay vì chỉ xem biểu đồ.

## 21. Sampling và trace search khi điều tra

Trong các giao diện như Jaeger, Tempo hoặc các tracing UI khác, thao tác thường là:

1. Chọn khoảng thời gian metric có bất thường.
2. Lọc theo service, route, environment, status và duration nếu có.
3. Mở trace chậm liên quan, xem root span và waterfall.
4. Xem chi tiết span, attributes, events, errors và các span links.
5. So sánh với trace nhanh cùng endpoint, phiên bản và điều kiện.
6. Đối chiếu log, dependency metrics và tình trạng instrumentation.

Nếu không tìm thấy trace, kiểm tra sampling/retention, exporter/collector, ingest delay, quyền truy cập và propagation. **Không thấy trace không có nghĩa request đã không chạy**.

Với trace quá lớn, bắt đầu từ root, các nhánh quan trọng, error đầu tiên, fan-out và khoảng trống; không cần đọc mọi span theo thứ tự.

## 22. Bảo vệ thông tin trong tracing

Trace thường được gửi qua agent, collector, backend storage và UI mà nhiều người có thể truy cập. Tránh thu thập dữ liệu nhạy cảm:

- Không đưa access token, cookie, mật khẩu, API key, PAN thẻ, PII hoặc request body thô vào span.
- Chuẩn hóa http route; tránh dùng raw URL chứa ID hoặc query nhạy cảm làm span name.
- Kiểm soát baggage vì nó có thể truyền đi nhiều service.
- Giới hạn độ dài attribute, số lượng events/links và tổng span per trace.
- Áp dụng access control, mã hóa đường truyền, retention và audit cho hệ thống quan sát.
- Dùng SDK/collector filtering khi cần, nhưng ưu tiên loại bỏ dữ liệu nhạy cảm **ngay tại nguồn**.
- Theo dõi exporter failure, spans dropped, collector queue và sampling rate.
- Thiết kế pipeline observability theo hướng không làm đình trệ nghiệp vụ khi backend trace quá tải.

Không nên gắn user ID hoặc order ID trực tiếp vào span name. Nếu cần correlation cụ thể, dùng cơ chế được kiểm soát truy cập và chính sách dữ liệu phù hợp.

## 23. Kiểm chứng instrumentation

Các kịch bản kiểm thử nên tập trung vào hành vi quan sát cốt lõi:

| Tình huống | Mong đợi |
|---|---|
| A gọi B qua HTTP | Trace context được propagate; CLIENT/SERVER spans liên kết |
| Một request gọi hai RPC song song | Các span overlap hợp lý, parent đúng |
| Request tạo task trong executor | Span async giữ đúng context |
| Message producer → consumer | Có parent/link/correlation theo model |
| Batch gom nhiều message | Không gán một parent sai cho toàn batch |
| Dependency timeout rồi retry | Thấy attempt, error và khoảng backoff nếu instrument |
| Lỗi child nhưng fallback thành công | Root phản ánh kết quả cuối cùng |
| Context từ request trước trong thread pool | Không rò trace context sang request mới |
| Request có token/PII | Không ghi giá trị nhạy cảm vào span/event |
| Collector bị nghẽn | Có metric về drop/export failure |
| Nhiều service/host | Timestamps/causality có thể kiểm tra, phát hiện clock skew |
| Synchronous và background workflow | Đo riêng HTTP latency và completion latency |

Có thể dùng in-memory exporter hoặc span processor thử nghiệm của thư viện OpenTelemetry để assert span count, trace ID, parent ID, kind, status và event. Kiểm thử cấu trúc span không thay thế load test và phân tích latency trong môi trường thật.

## 24. Checklist phân tích một trace chậm

- [ ] Có root operation, service, version, environment, start/end và latency?
- [ ] Đã xác định các giai đoạn tuần tự, song song, queue và async?
- [ ] Đã tìm join point và nhánh thực sự chặn request?
- [ ] Không cộng duration parent/child và các span overlap?
- [ ] Đã xem các khoảng trống, self time và khả năng thiếu instrumentation?
- [ ] Đã kiểm tra retry, timeout, cancellation, connection pool và DB locks?
- [ ] Đã đọc span attributes, events, status và exception theo hợp đồng?
- [ ] Đã xác minh trace context qua mọi ranh giới liên quan?
- [ ] Đã xét sampling, partial trace, ingest delay và clock skew?
- [ ] Đã so sánh nhiều trace tương đồng, không chỉ một trường hợp bất thường?
- [ ] Đã đối chiếu metrics/logs để xác nhận nguyên nhân?
- [ ] Đã ước lượng lợi ích end-to-end khi tối ưu đoạn được chọn?
- [ ] Đã đo lại SLI và critical path sau thay đổi?

## 25. Bài tập thực hành

Một endpoint /recommendations chạy ba engine sau 40 ms chuẩn bị:

~~~text
T=0 ms: request bắt đầu.
T=40 ms: gửi các lời gọi song song.
Engine A: trả lúc T=480 ms.
Engine B: trả lúc T=630 ms.
Engine C: trả lúc T=390 ms.
Combine: 90 ms sau khi đủ ba kết quả.
Render: 30 ms sau combine.
~~~

**Câu hỏi 1:** Khi bỏ qua overhead khác, request hoàn tất ở thời điểm nào?

**Đáp án:** max(480,630,390) + 90 + 30 = **750 ms**. Mốc engine là timestamp tuyệt đối từ T=0, không phải duration kể từ T=40.

**Câu hỏi 2:** Nhánh critical trước combine là nhánh nào?

**Đáp án:** Engine B vì trả cuối ở T=630.

**Câu hỏi 3:** Nếu Engine A nhanh hơn 200 ms thì tổng latency đổi không?

**Đáp án:** Không, vì Engine B vẫn chặn điểm join.

**Câu hỏi 4:** Nếu Engine B nhanh hơn 250 ms thì latency còn bao nhiêu?

**Đáp án:** Engine B trả lúc 380 ms, Engine A vẫn tới 480 ms; tổng là 480 + 90 + 30 = **600 ms**.

**Câu hỏi 5:** Nếu chỉ cần kết quả của hai engine bất kỳ thì còn dùng max của cả ba được không?

**Đáp án:** Không. Cần mô hình điểm thành công thứ hai, lỗi/quorum, việc hủy nhánh thừa và mục tiêu chất lượng kết quả.

**Câu hỏi 6:** Nếu span của Engine B không có trong trace vì bị drop, được kết luận Engine A là critical không?

**Đáp án:** Không; cần trace đầy đủ hoặc dữ liệu khác xác minh những công việc đang chặn.

**Câu hỏi 7:** Nếu parent span combine dài 690 ms và các child overlap bên trong, được cộng 690 ms vào tất cả child không?

**Đáp án:** Không; parent đã bao trùm thời gian con. Phải phân tích timeline và quan hệ phụ thuộc.

## 26. Ghi nhớ

**Trace** cho biết đường đi của một yêu cầu, **span** cho biết đơn vị công việc cùng thời điểm và ngữ cảnh. **Waterfall** cho thấy các hoạt động chồng lấn, nhưng chỉ quan hệ phụ thuộc và điểm đồng bộ mới giúp tìm **critical path**.

Span dài không tự chứng minh CPU chậm; có thể là network, queue, lock, pool, retry, GC hoặc instrumentation thiếu. Tổng duration của các span không bằng thời gian request khi chúng lồng nhau hoặc chạy song song. Sampling và mất context có thể khiến trace không đầy đủ; đồng hồ xuyên host có thể làm sai các mốc.

Metrics cho biết quy mô vấn đề; traces cho biết hành trình cụ thể; logs và số liệu dependency giúp xác nhận nguyên nhân. Sau mỗi lần tối ưu, hãy đo lại vì nhánh chi phối latency có thể đổi.

**Câu hỏi cần trả lời khi nhìn một trace chậm không phải chỉ là "Span nào dài nhất?", mà là "Phần việc nào đang ngăn request kết thúc, vì sao nó kéo dài và rút ngắn phần đó sẽ cải thiện end-to-end bao nhiêu?"**