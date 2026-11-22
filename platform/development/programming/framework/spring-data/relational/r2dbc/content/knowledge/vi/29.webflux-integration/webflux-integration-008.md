# Nguy cơ giữ kết nối lâu khi phía nhận tiêu thụ dữ liệu chậm

Trong ứng dụng Spring Data Relational R2DBC kết hợp Spring WebFlux, một truy vấn có thể trả về `Flux<T>` và được truyền trực tiếp tới HTTP response. Mô hình này giúp xử lý dữ liệu theo luồng mà không phải chặn thread để chờ từng hàng. Tuy nhiên, nếu phía nhận đọc response chậm, pipeline có thể bị backpressure. Khi database result vẫn đang được tiêu thụ, connection dùng cho truy vấn có thể tiếp tục bị giữ trong connection pool.

Đây là điểm cần phân biệt: **non-blocking không có nghĩa là không chiếm tài nguyên**. Thread xử lý request có thể không bị chặn, nhưng connection database, transaction, buffer và bộ nhớ vẫn có vòng đời. Một vài response stream kéo dài có thể chiếm nhiều connection trong thời gian dài; khi pool hết connection, request mới phải chờ hoặc timeout.

Bài học này giải thích vì sao tốc độ tiêu thụ của downstream ảnh hưởng tới thời gian giữ connection, cách backpressure truyền qua WebFlux và R2DBC, các toán tử dễ tạo buffer, tác động của transaction, cách theo dõi pool và các chiến lược như phân trang keyset, batch hữu hạn hoặc export bất đồng bộ.

## 1. Từ database result tới HTTP response

Một endpoint có thể trả trực tiếp `Flux<CustomerView>`:

```java
@GetMapping(value = "/customers/stream",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<CustomerView> streamCustomers() {
    return customerService.streamCustomers();
}
```

Service dùng `DatabaseClient`:

```java
public Flux<CustomerView> streamCustomers() {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY id
            """)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

Khi WebFlux ghi response, framework subscribe vào publisher và yêu cầu dữ liệu theo nhu cầu của encoder/network. Với media type dạng streaming như NDJSON hoặc Server-Sent Events, response có thể được ghi theo từng phần tử hoặc từng event. Cách flush và buffering cụ thể còn phụ thuộc codec, media type, server connector và proxy phía trước.

Luồng xử lý khái quát:

```text
PostgreSQL
    |
    v
R2DBC driver / Result
    |
    v
DatabaseClient Flux<CustomerView>
    |
    v
WebFlux encoder
    |
    v
HTTP server / network buffers
    |
    v
Proxy / client
```

Nếu client đọc nhanh, demand được đáp ứng nhanh và truy vấn có thể hoàn tất sớm. Nếu client đọc chậm hoặc tạm dừng đọc, downstream giảm demand. Khi pipeline vẫn đang tiêu thụ cùng một database result, connection có thể tiếp tục được giữ cho tới khi result hoàn tất, lỗi hoặc bị hủy và quá trình cleanup kết thúc.

## 2. Vì sao connection bị giữ lâu?

Với truy vấn reactive, connection thường được lấy khi publisher được subscribe. Driver thực thi statement và cung cấp result. Spring Data/DatabaseClient cần giữ connection trong thời gian result được tiêu thụ, sau đó mới giải phóng hoặc trả connection về pool.

Một response stream có thể kéo dài do:

- Query trả về hàng trăm nghìn hoặc hàng triệu hàng.
- Client tải dữ liệu qua mạng chậm.
- Proxy hoặc gateway giới hạn tốc độ truyền.
- Client xử lý mỗi phần tử tốn nhiều thời gian.
- Downstream gọi thêm service hoặc thực hiện tính toán trước khi yêu cầu phần tử tiếp theo.
- Một toán tử buffer hoặc prefetch làm thay đổi tốc độ tiêu thụ giữa các tầng.
- Transaction bao trùm toàn bộ stream và chỉ kết thúc khi stream hoàn tất.

Ví dụ, một truy vấn chỉ mất vài trăm mili giây nếu đọc hết nhanh có thể giữ connection nhiều giây hoặc lâu hơn khi response được gửi tới một client chậm. Thời gian SQL chạy và thời gian connection bị chiếm dụng không nhất thiết bằng nhau.

### 2.1. Thời gian giữ connection khác với thời gian thực thi SQL

Có thể phân biệt các khoảng thời gian:

| Khoảng thời gian | Ý nghĩa |
|---|---|
| Connection acquire | Chờ lấy connection từ pool |
| Statement execution | Driver gửi câu lệnh và database xử lý |
| Result consumption | Ứng dụng/driver đọc các hàng kết quả |
| Downstream processing | Mapping, encode, xử lý nghiệp vụ và truyền response |
| Cleanup/release | Đóng result/statement và trả connection về pool |

Với một result stream, các giai đoạn có thể chồng lấn. Nếu downstream chỉ yêu cầu thêm dữ liệu khi đã ghi xong phần trước, thời gian result consumption có thể kéo dài theo tốc độ ghi HTTP. Do đó, đo riêng query latency chưa đủ để phát hiện connection bị giữ lâu.

### 2.2. Non-blocking vẫn chiếm connection

R2DBC dùng I/O bất đồng bộ để tránh chặn thread trong lúc chờ database. Tuy nhiên, connection là tài nguyên có giới hạn. Một connection đang phục vụ result stream không thể đồng thời được cấp cho request khác theo cách thông thường của connection pool.

Vì vậy, ứng dụng có thể dùng ít thread nhưng vẫn cạn pool. Đây là một trong những nguyên nhân khiến hệ thống reactive có độ trễ tăng dù CPU không cao.

## 3. Backpressure truyền từ WebFlux tới R2DBC như thế nào?

Reactive Streams dùng demand: subscriber yêu cầu một số lượng phần tử bằng `request(n)`. Publisher phát tối đa số phần tử đã được yêu cầu theo hợp đồng. Khi downstream tiêu thụ chậm, nó có thể giảm tốc độ yêu cầu và backpressure truyền ngược qua pipeline nếu các thành phần hỗ trợ.

Ví dụ khái quát:

```text
Client đọc chậm
      |
      v
HTTP response writer giảm demand
      |
      v
WebFlux encoder phát chậm hơn
      |
      v
Reactor pipeline yêu cầu ít phần tử hơn
      |
      v
R2DBC result được tiêu thụ chậm hơn
      |
      v
Connection có thể được giữ lâu hơn
```

Backpressure giúp tránh việc một producer phát vô hạn dữ liệu vào một consumer không theo kịp. Nó không tự giải phóng connection sớm. Trong một truy vấn đang stream, giảm tốc độ tiêu thụ thường có nghĩa là result và connection tồn tại lâu hơn.

### 3.1. Backpressure không bảo đảm database chỉ gửi đúng một hàng mỗi lần

Từ subscriber tới driver có thể có nhiều tầng buffer:

- Reactor operator prefetch.
- Buffer trong R2DBC driver.
- Buffer của giao thức database và socket.
- Buffer của HTTP server và network stack.
- Buffer ở reverse proxy hoặc client.

Do đó, demand của subscriber không đồng nghĩa mỗi `request(1)` tạo đúng một network round trip tới database. Driver có thể đọc trước một số hàng hoặc dùng cursor/fetch strategy riêng. Hành vi này phụ thuộc driver và cấu hình.

Nếu driver hỗ trợ fetch size hoặc cursor-based fetching, có thể cấu hình theo tài liệu của driver. R2DBC SPI có API liên quan như `Statement.fetchSize(int)` trong các phiên bản hỗ trợ, nhưng driver có thể không hỗ trợ hoặc áp dụng semantics riêng. Không giả định `fetchSize` có cùng tác dụng trên mọi database.

### 3.2. Backpressure chỉ hữu ích khi pipeline không phá vỡ nó

Một số toán tử có thể yêu cầu upstream phát nhanh hơn rồi lưu dữ liệu vào buffer. Ví dụ:

- `onBackpressureBuffer()` có thể giữ dữ liệu chờ downstream.
- `publishOn` có hàng đợi prefetch để chuyển tín hiệu sang scheduler khác.
- `collectList()` tiêu thụ toàn bộ nguồn và giữ mọi phần tử trong bộ nhớ.
- `buffer(n)` gom phần tử thành batch trước khi phát.
- `flatMap` có thể chạy nhiều inner publisher và giữ kết quả đang chờ.

Các toán tử này không nhất thiết sai, nhưng thay đổi vị trí và kích thước buffer. Nếu buffer không giới hạn, một downstream chậm có thể làm heap tăng nhanh.

## 4. Streaming HTTP có thể kéo dài vòng đời truy vấn

Ví dụ endpoint stream hàng:

```java
@GetMapping(value = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<EventView> events() {
    return eventService.findAllEvents();
}
```

Khi client đọc từng dòng NDJSON, WebFlux có thể yêu cầu thêm phần tử theo tiến độ ghi. Nếu client nhận dữ liệu qua mạng di động chậm, response writer bị backpressure và pipeline có thể tiếp tục giữ result database.

Điều này phù hợp với stream có vòng đời được giới hạn và số lượng consumer nhỏ. Nó có thể trở thành vấn đề nếu endpoint stream hàng triệu bản ghi, client giữ kết nối lâu hoặc có nhiều người tải dữ liệu cùng lúc.

### 4.1. Media type ảnh hưởng tới cách response được encode

Các kiểu response thường gặp:

| Media type | Đặc điểm |
|---|---|
| `application/x-ndjson` | Mỗi JSON object được phân tách bằng newline; phù hợp truyền từng record |
| `text/event-stream` | Server-Sent Events; mỗi event có framing riêng |
| `application/json` | JSON document/array; cách encode, flush và buffering phụ thuộc codec và server |

Nếu client cần xử lý từng record khi dữ liệu đến, NDJSON hoặc SSE thường thể hiện semantics streaming rõ ràng hơn một JSON array thông thường. Nhưng chỉ đổi media type không giải quyết vấn đề giữ connection nếu publisher vẫn gắn trực tiếp với truy vấn dài.

### 4.2. Proxy có thể buffer response

Reverse proxy, ingress controller, API gateway hoặc CDN có thể buffer response trước khi gửi tới client. Điều này có thể làm giảm backpressure trực tiếp từ client tới ứng dụng hoặc thay đổi thời gian ghi response. Ngược lại, proxy có thể giữ kết nối upstream mở trong khi downstream đọc chậm.

Hãy kiểm tra cấu hình streaming/buffering của hạ tầng thực tế. Không suy luận hành vi production chỉ từ test gọi trực tiếp WebFlux server trên localhost.

## 5. Tác động của transaction lên thời gian giữ connection

Reactive transaction thường gắn với subscription và connection được transaction manager quản lý. Nếu method `@Transactional` trả về một `Flux` dài, transaction có thể tồn tại cho tới khi Flux hoàn tất hoặc bị hủy.

Ví dụ:

```java
@Transactional(readOnly = true)
public Flux<CustomerView> streamCustomers() {
    return customerRepository.findAll()
        .map(this::toView);
}
```

Nếu publisher này được dùng trực tiếp làm HTTP response và client tiêu thụ chậm, transaction-bound connection có thể bị giữ trong toàn bộ thời gian stream. `readOnly = true` không có nghĩa connection được trả về pool ngay sau khi query bắt đầu.

Transaction kéo dài còn có thể:

- Giữ snapshot đọc lâu hơn tùy isolation level và database.
- Làm tăng nguy cơ giữ lock nếu transaction có thao tác ghi hoặc lock đọc.
- Tăng thời gian giữ connection trong pool.
- Làm transaction timeout hoặc application deadline bị vượt.
- Ảnh hưởng vacuum/cleanup hoặc replication tùy database và isolation semantics.

Không mở transaction chỉ để bọc một response stream lớn nếu nghiệp vụ không yêu cầu một transaction xuyên suốt. Nếu cần tính nhất quán snapshot, hãy cân nhắc trade-off giữa snapshot và tài nguyên connection.

### 5.1. Không giữ transaction khi chờ công việc mạng chậm

Không nên để một transaction database mở trong lúc gọi HTTP service, chờ client hoặc xử lý CPU dài nếu không cần thiết:

```java
@Transactional(readOnly = true)
public Flux<CustomerView> streamCustomers() {
    return customerRepository.findAll()
        .flatMap(customer -> profileClient.fetch(customer.getId())
            .map(profile -> toView(customer, profile)));
}
```

Mỗi phần tử có thể chờ HTTP service. Nếu truy vấn database và transaction vẫn đang mở trong khi các inner publisher xử lý chậm, connection có thể bị giữ lâu hơn nhiều so với thời gian SQL cần thiết.

Nếu cần enrich dữ liệu ngoài database, cân nhắc lấy dữ liệu theo batch hữu hạn, hoàn tất query rồi gọi service ngoài, hoặc dùng một workflow riêng với concurrency và timeout được giới hạn.

### 5.2. Transaction không tự tạo snapshot xuyên nhiều request phân trang

Nếu mỗi page là một query riêng và mỗi query dùng connection/transaction riêng, các page có thể quan sát dữ liệu ở những thời điểm khác nhau. Ngược lại, giữ một transaction snapshot cho toàn bộ export có thể giữ connection lâu.

Hãy quyết định liệu use case cần:

- Dữ liệu gần nhất ở từng page, chấp nhận thay đổi trong lúc đọc.
- Một tập dữ liệu ổn định theo thời điểm/cutoff.
- Một snapshot database nhất quán xuyên toàn bộ quá trình.

Yêu cầu nhất quán quyết định chiến lược phân trang, watermark, snapshot và thời gian giữ connection.

## 6. Connection pool có thể cạn dù CPU thấp

Connection pool có số connection tối đa. Khi các stream dài giữ connection, request mới phải chờ connection rảnh. Nếu thời gian chờ vượt acquire timeout, request thất bại dù database có thể chưa quá tải CPU.

Một cách ước lượng trực giác dựa trên định luật Little:

\[
\text{Số connection đang bận trung bình}
\approx
\text{Tốc độ request dùng DB}
\times
\text{Thời gian giữ connection trung bình}
\]

Ví dụ định tính: nếu số request bắt đầu truy vấn mỗi giây không đổi nhưng thời gian giữ connection tăng gấp nhiều lần do client tải chậm, số connection bận trung bình cũng tăng tương ứng. Khi gần chạm `maxSize`, hàng đợi acquire bắt đầu tăng.

Không giải quyết vấn đề bằng cách chỉ tăng pool size. Pool lớn hơn có thể tăng số connection đồng thời lên database và gây thêm tải, trong khi nguyên nhân là mỗi stream giữ connection quá lâu.

## 7. Theo dõi connection pool và thời gian giữ connection

Các chỉ số hữu ích gồm:

| Chỉ số | Ý nghĩa |
|---|---|
| Allocated connections | Số connection pool đã tạo |
| Acquired/active connections | Số connection đang được ứng dụng sử dụng |
| Idle connections | Số connection rảnh có thể cấp |
| Pending acquire | Số request đang chờ connection |
| Acquire duration | Thời gian chờ lấy connection |
| Acquire timeout count | Số lần không lấy được connection trong thời hạn |
| Connection hold duration | Thời gian từ khi cấp tới khi trả connection, nếu hệ thống đo được |
| Query/statement duration | Thời gian thực thi statement hoặc nhận result theo cách đo của instrumentation |
| Cancellation count | Số subscription bị hủy khi đang xử lý |

Tên metric chính xác phụ thuộc R2DBC pool, Micrometer, Spring Boot và phiên bản thư viện. Hãy xác định metric thực tế trong môi trường chạy thay vì hardcode tên từ một phiên bản khác.

### 7.1. Dấu hiệu stream chậm đang giữ pool

Một số dấu hiệu:

- Active connections tăng và idle connections về gần 0.
- Pending acquire tăng trong khi CPU ứng dụng vẫn thấp.
- Acquire latency tăng theo số lượng client tải stream.
- Endpoint stream có response duration dài bất thường.
- Query execution time không tăng tương ứng với connection hold duration.
- Khi client ngắt kết nối, active connection giảm chậm hoặc cancellation/cleanup bị trễ.

Kết hợp metrics pool, HTTP response duration, query timing và trace để phân biệt query chậm với downstream chậm.

### 7.2. Đo thời gian ở các ranh giới

Có thể ghi timestamp tại thời điểm bắt đầu publisher, khi phần tử đầu tiên đến và khi pipeline kết thúc:

```java
public Flux<CustomerView> streamCustomers() {
    return customerRepository.findAll()
        .doOnSubscribe(subscription -> log.debug("Customer stream subscribed"))
        .doOnNext(customer -> recordFirstOrNextRow(customer.getId()))
        .doFinally(signal -> recordStreamFinished(signal));
}
```

Trong code thực tế, không log ID hoặc dữ liệu cá nhân nếu không cần. Dùng timer/metrics thay cho log từng hàng để tránh log volume lớn. `doFinally` quan sát complete, error hoặc cancel; nó không thay thế metric connection hold duration của pool.

## 8. Các toán tử dễ làm tăng buffering hoặc giữ nguồn lâu

### 8.1. collectList()

```java
return customerRepository.findAll()
    .collectList()
    .flatMapMany(Flux::fromIterable);
```

`collectList()` tiêu thụ toàn bộ nguồn trước khi phát danh sách. Ưu điểm là query có thể hoàn tất và connection được trả về pool trước khi danh sách được gửi dần tới HTTP client. Nhược điểm là:

- Toàn bộ kết quả được giữ trong heap.
- Client không nhận được phần tử đầu tiên cho tới khi query hoàn tất.
- Latency và memory tăng theo số lượng hàng.
- Một tập dữ liệu lớn có thể gây `OutOfMemoryError`.

Chỉ dùng `collectList()` khi kích thước có giới hạn rõ ràng, ví dụ một trang tối đa vài chục hoặc vài trăm bản ghi theo SLA của hệ thống. Không dùng nó cho toàn bộ bảng lớn.

### 8.2. buffer(n)

```java
return customerRepository.findAll()
    .buffer(100)
    .concatMap(this::processBatch);
```

`buffer(100)` gom tối đa 100 phần tử thành một list rồi phát. Nó giới hạn kích thước từng batch nhưng không tự tách query thành nhiều connection hoặc bảo đảm connection được release giữa các batch. Nếu upstream là một result stream duy nhất, connection có thể vẫn được giữ tới khi toàn bộ nguồn hoàn tất.

Muốn release connection giữa các page, cần thực sự thực hiện nhiều query có giới hạn, tiêu thụ xong từng query rồi mới phát page và bắt đầu query tiếp theo.

### 8.3. onBackpressureBuffer()

```java
return customerRepository.findAll()
    .onBackpressureBuffer();
```

Buffer không giới hạn có thể biến áp lực downstream thành áp lực heap. Khi consumer chậm, ứng dụng tích lũy các hàng thay vì làm producer chậm lại. Với kết quả database lớn, đây là rủi ro nghiêm trọng.

Nếu thực sự cần buffer, hãy đặt giới hạn và chính sách overflow:

```java
return source.onBackpressureBuffer(
    500,
    dropped -> metrics.counter("stream.buffer.overflow").increment()
);
```

API overload và hành vi cụ thể phụ thuộc Reactor version. Chính sách overflow cần phù hợp nghiệp vụ; không drop dữ liệu database một cách tùy tiện chỉ để giữ pipeline chạy.

### 8.4. publishOn()

`publishOn` chuyển xử lý downstream sang scheduler khác và thường có prefetch queue. Nó có thể giúp tách xử lý CPU khỏi thread thực thi upstream, nhưng queue giữ các phần tử trong bộ nhớ và không tự trả connection sớm.

```java
return customerRepository.findAll()
    .publishOn(Schedulers.parallel(), 64)
    .map(this::expensiveMapping);
```

Prefetch nhỏ hơn có thể giới hạn lượng phần tử chờ trong queue, nhưng không thay thế pagination hoặc fetch-size configuration. Không thêm scheduler nếu chỉ để “làm reactive nhanh hơn”; đo trước và xác định rõ công việc CPU/blocking.

### 8.5. flatMap()

```java
return customerRepository.findAll()
    .flatMap(customer -> profileClient.fetch(customer.getId()));
```

`flatMap` có thể giữ nhiều inner publisher đang chạy và nhiều kết quả chờ downstream. Nếu inner publisher chậm, số connection/HTTP request hoặc buffer có thể tăng. Đặt concurrency hữu hạn:

```java
return customerRepository.findAll()
    .flatMap(customer -> profileClient.fetch(customer.getId()), 8);
```

Giới hạn concurrency giảm số công việc phụ đang chạy cùng lúc, nhưng nếu `findAll()` vẫn là một result stream thì connection nguồn vẫn có thể bị giữ cho tới khi nguồn hoàn tất.

## 9. Hủy subscription khi client ngắt kết nối

Khi client đóng kết nối trước khi response hoàn tất, WebFlux có thể hủy subscription của response publisher. Cancellation có thể truyền qua Reactor tới R2DBC driver, giúp dừng tiêu thụ result và kích hoạt cleanup connection.

Tuy nhiên:

- Cancellation không bảo đảm database dừng statement tức thì.
- Driver có thể cần thời gian gửi cancel hoặc drain/close protocol state.
- Một số thao tác đã hoàn tất ở database trước khi cancellation tới.
- Proxy có thể giữ upstream request trong một khoảng thời gian sau khi client đóng.
- Transaction đang mở có thể cần rollback/cleanup trước khi connection được trả pool.

Không dựa vào cancellation như cách duy nhất để giới hạn tài nguyên. Hãy kết hợp query limit, timeout, page size, transaction boundary và giới hạn số stream đồng thời.

### 9.1. take(n) và giới hạn số hàng

Nếu API chỉ cần tối đa một số lượng hàng, hãy giới hạn ngay trong SQL:

```sql
SELECT id, name
FROM customer
ORDER BY id
LIMIT :limit;
```

Hoặc dùng `.take(n)` như giới hạn ở pipeline:

```java
return customerRepository.findAll()
    .take(100);
```

`take(100)` hủy upstream sau 100 phần tử, nhưng database có thể đã prefetch thêm dữ liệu tùy driver. Đặt `LIMIT` ở SQL thường diễn đạt rõ ràng hơn và giúp database không cần tạo result lớn. Có thể dùng cả hai như lớp bảo vệ, nhưng cần hiểu semantics.

## 10. Timeout ở nhiều tầng

Một endpoint stream nên có ngân sách thời gian và giới hạn tài nguyên phù hợp. Các timeout khác nhau bảo vệ các giai đoạn khác nhau:

| Timeout | Bảo vệ điều gì |
|---|---|
| Pool acquire timeout | Thời gian chờ connection rảnh |
| Connection creation timeout | Thời gian thiết lập connection mới |
| Statement/query timeout | Thời gian thực thi statement theo hỗ trợ driver/database |
| Reactor `timeout` | Thời gian publisher không phát tín hiệu theo cấu hình operator |
| Transaction timeout | Thời gian transaction tồn tại theo transaction manager |
| HTTP response timeout | Thời gian response được phép tồn tại theo server/gateway/client |
| Idle timeout | Khoảng thời gian không có dữ liệu trước khi kết nối bị đóng |

Ví dụ dùng Reactor timeout:

```java
return customerService.streamCustomers()
    .timeout(Duration.ofMinutes(2));
```

`timeout` có thể hủy upstream khi hết hạn và phát `TimeoutException` hoặc chuyển sang fallback. Nó không thay thế query timeout ở database, và không bảo đảm mọi driver hủy statement ngay lập tức.

Đối với stream có thể kéo dài lâu nhưng có dữ liệu đều đặn, timeout tổng thể và idle timeout có ý nghĩa khác nhau. Một stream phát đều có thể vượt tổng thời gian dự kiến nhưng không bị idle; ngược lại, một stream bị treo không phát dữ liệu có thể cần idle timeout.

Không đặt timeout quá ngắn cho mọi endpoint. Chọn theo SLA, kích thước kết quả, tốc độ mạng và loại client.

## 11. Chiến lược 1: giới hạn kết quả ngay tại SQL

Nếu use case chỉ cần một tập hữu hạn, dùng `LIMIT`/`FETCH FIRST` hoặc API phân trang phù hợp database.

```java
Flux<CustomerView> findRecentCustomers(int limit) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """)
        .bind("limit", limit)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all();
}
```

Hãy kiểm tra `limit` trong khoảng hợp lệ trước khi bind. Không cho client yêu cầu hàng triệu bản ghi chỉ bằng cách gửi một query parameter lớn.

Giới hạn SQL làm giảm số hàng cần đọc và thường rút ngắn thời gian giữ connection. Nó là lựa chọn tốt nhất khi nghiệp vụ không thực sự cần toàn bộ tập dữ liệu.

## 12. Chiến lược 2: phân trang để release connection giữa các page

Nếu cần duyệt một tập dữ liệu lớn, có thể thực hiện nhiều query page nhỏ. Mỗi query hoàn tất, connection được release; sau đó ứng dụng mới gửi page cho downstream và bắt đầu query tiếp theo khi cần.

### 12.1. Keyset pagination

Keyset pagination dùng giá trị cuối của page trước làm cursor:

```sql
SELECT id, name, email
FROM customer
WHERE id > :afterId
ORDER BY id
LIMIT :pageSize;
```

Giả sử `id` là khóa duy nhất và thứ tự tăng ổn định. Page đầu dùng cursor khởi tạo phù hợp với miền ID; các page sau dùng ID cuối cùng của page trước.

So với `OFFSET`, keyset thường tránh phải bỏ qua số lượng hàng lớn khi đi sâu vào tập dữ liệu. Nó cũng ít bị dịch chuyển vị trí hơn khi có INSERT mới ở phía trước cursor. Tuy nhiên, cần chọn cursor dựa trên một thứ tự ổn định và duy nhất.

### 12.2. Ví dụ lấy một page và hoàn tất query trước khi phát page

```java
private Mono<List<CustomerView>> fetchPage(long afterId, int pageSize) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            WHERE id > :afterId
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("afterId", afterId)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all()
        .collectList();
}
```

`collectList()` ở đây chỉ thu thập một page có kích thước bị giới hạn bởi `pageSize`. Khi `.all()` hoàn tất, result của page đã được tiêu thụ và connection của query có thể được trả về pool trước khi page được truyền dần cho HTTP client.

### 12.3. Nối các page tuần tự

```java
public Flux<CustomerView> streamByPages(int pageSize) {
    return fetchPages(0L, pageSize);
}

private Flux<CustomerView> fetchPages(long afterId, int pageSize) {
    return Flux.defer(() -> fetchPage(afterId, pageSize))
        .flatMapMany(page -> {
            if (page.isEmpty()) {
                return Flux.empty();
            }

            long nextAfterId = page.get(page.size() - 1).id();

            return Flux.fromIterable(page)
                .concatWith(Flux.defer(() ->
                    fetchPages(nextAfterId, pageSize)
                ));
        });
}
```

Ví dụ giả định ID là số dương tăng và `CustomerView` có accessor `id()`. Trong ứng dụng thực tế, hãy xác thực `pageSize` có giới hạn tối đa và dùng cursor khởi tạo phù hợp. `Flux.defer` trì hoãn query page tiếp theo cho tới khi nhánh trước được subscribe; `concatWith` chỉ chuyển sang page tiếp theo sau khi các phần tử page hiện tại đã được tiêu thụ.

Điểm khác biệt với `findAll().buffer(pageSize)` là mỗi page ở đây là một SQL statement riêng. Query hiện tại hoàn tất trước khi dữ liệu page được gửi ra downstream; connection không phải giữ cho toàn bộ tập kết quả.

### 12.4. Cursor cần có thứ tự duy nhất

Nếu sort theo `created_at`, nhiều hàng có thể cùng timestamp. Chỉ dùng timestamp làm cursor có thể bỏ sót hoặc lặp hàng. Dùng thêm khóa duy nhất làm tie-breaker:

```sql
SELECT id, created_at, name
FROM customer
WHERE (created_at, id) > (:afterCreatedAt, :afterId)
ORDER BY created_at, id
LIMIT :pageSize;
```

Row-value comparison như trên phù hợp PostgreSQL và một số database; cú pháp có thể khác theo dialect. Nếu dùng nhiều cột cursor, phải dùng cùng thứ tự trong điều kiện và `ORDER BY`.

## 13. Pagination thay đổi semantics nhất quán dữ liệu

Mỗi page là một statement riêng, do đó dữ liệu có thể thay đổi giữa hai lần đọc:

- Hàng mới được INSERT sau khi page trước hoàn tất.
- Hàng bị DELETE trước khi page tiếp theo được đọc.
- Giá trị cursor hoặc cột sort được UPDATE.
- Hàng được chuyển từ phía sau cursor lên phía trước hoặc ngược lại.

Keyset pagination tránh nhiều vấn đề của OFFSET nhưng không tự tạo snapshot nhất quán cho toàn bộ export.

Nếu chấp nhận dữ liệu thay đổi trong lúc đọc, mô tả semantics này rõ cho caller. Nếu cần tập dữ liệu ổn định, có thể:

- Chọn một cutoff/version nghiệp vụ và thêm điều kiện lọc cố định cho mọi page.
- Dùng một snapshot database phù hợp nếu hệ quản trị/isolation hỗ trợ, chấp nhận connection/transaction có thể được giữ lâu.
- Tạo export job với snapshot hoặc danh sách khóa được chốt trước theo một thiết kế phù hợp.
- Dùng bảng staging/export snapshot để tách quá trình chuẩn bị dữ liệu khỏi quá trình tải xuống.

Không dùng một transaction dài chỉ vì muốn pagination nhất quán mà chưa đánh giá tác động lên connection pool và database.

## 14. Chiến lược 3: đọc nhanh vào bộ nhớ có giới hạn rồi trả response

Với tập dữ liệu nhỏ và giới hạn rõ ràng, có thể đọc hết trước khi bắt đầu ghi response:

```java
public Mono<List<CustomerView>> loadCustomerPage(int pageSize) {
    return databaseClient.sql("""
            SELECT id, name, email
            FROM customer
            ORDER BY id
            LIMIT :pageSize
            """)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new CustomerView(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email", String.class)
        ))
        .all()
        .collectList();
}
```

Khi publisher database hoàn tất, connection có thể được release. Sau đó WebFlux serialize danh sách đã có trong bộ nhớ. Client chậm không còn kéo dài thời gian đọc result database.

Đổi lại:

- Bộ nhớ tỷ lệ với số hàng và kích thước mỗi object.
- Client phải chờ query hoàn tất mới nhận dữ liệu đầu tiên.
- Không phù hợp cho export không giới hạn.
- Nếu có nhiều request cùng lúc, tổng bộ nhớ có thể tăng đáng kể.

Đây là chiến lược phù hợp cho page nhỏ, response bounded hoặc dữ liệu tổng hợp có giới hạn. Nó không phải cách thay thế an toàn cho streaming mọi bảng.

## 15. Chiến lược 4: export bất đồng bộ cho tập dữ liệu rất lớn

Nếu người dùng cần tải hàng triệu hàng, giữ một HTTP request và một connection database xuyên suốt quá trình tải thường không phải thiết kế tốt.

Có thể chuyển thành export job:

1. API nhận yêu cầu export và tạo job record.
2. Worker đọc dữ liệu theo keyset page với batch size hữu hạn.
3. Worker ghi kết quả vào file/object storage theo luồng có giới hạn bộ nhớ.
4. Mỗi page query hoàn tất và release connection trước khi xử lý tiếp nếu thiết kế pipeline như vậy.
5. Worker cập nhật tiến độ và trạng thái job.
6. API trả job ID; client kiểm tra trạng thái hoặc nhận notification khi hoàn tất.
7. Khi file sẵn sàng, client tải file từ endpoint/download service riêng.

Ưu điểm:

- Không giữ HTTP request mở trong thời gian dài.
- Connection được dùng theo từng page thay vì toàn bộ thời gian client tải file.
- Có thể retry/resume và theo dõi tiến độ.
- Có thể áp quota và giới hạn số export đồng thời.
- Tách tốc độ đọc database khỏi tốc độ tải của client.

Worker vẫn phải có giới hạn concurrency, timeout, checkpoint và chính sách xóa file. Nếu export cần snapshot nhất quán, cần thiết kế snapshot/cutoff rõ ràng.

## 16. Không giữ connection trong lúc xử lý dữ liệu chậm

Một pipeline có thể thực hiện mapping hoặc enrichment sau khi đọc row. Nếu công việc sau database chậm, connection nguồn có thể bị giữ trong lúc downstream xử lý.

Ví dụ:

```java
return customerRepository.findAll()
    .flatMap(customer -> slowExternalService.enrich(customer)
        .map(this::toView), 4);
```

`flatMap` concurrency 4 giới hạn số enrichment đang chạy. Nhưng `findAll()` vẫn là một nguồn database liên tục; nếu downstream không tiêu thụ hết, result connection có thể vẫn tồn tại.

Nếu có thể, tách thành hai pha:

1. Đọc một page hữu hạn và hoàn tất query.
2. Sau khi connection được release, xử lý page với external service có concurrency hữu hạn.
3. Khi page đã xử lý xong, mới lấy page tiếp theo.

Ví dụ cấu trúc:

```java
private Mono<List<Customer>> fetchCustomerPage(long afterId, int size) {
    return customerRepository.findPageAfter(afterId, size)
        .collectList();
}

private Flux<CustomerView> processPages(long afterId, int size) {
    return Flux.defer(() -> fetchCustomerPage(afterId, size))
        .flatMapMany(page -> {
            if (page.isEmpty()) {
                return Flux.empty();
            }

            long next = page.get(page.size() - 1).getId();

            return Flux.fromIterable(page)
                .flatMap(this::enrichCustomer, 4)
                .concatWith(Flux.defer(() -> processPages(next, size)));
        });
}
```

Ví dụ minh họa việc hoàn tất truy vấn page trước khi gọi dịch vụ ngoài. Nếu cần giữ thứ tự đầu ra, thay `flatMap` bằng `concatMap` hoặc sắp xếp lại theo khóa. Hãy xác nhận repository page query có thứ tự ổn định.

## 17. Dùng fetch size/cursor khi driver hỗ trợ

Với tập dữ liệu lớn, một số database driver hỗ trợ cursor hoặc fetch size để lấy result theo từng đợt thay vì tải toàn bộ result về client cùng lúc. R2DBC SPI có API `Statement.fetchSize(int)` trong phiên bản hỗ trợ, nhưng đây là gợi ý cho driver; khả năng và semantics phụ thuộc implementation.

Các câu hỏi cần kiểm tra theo driver:

- `fetchSize` có được hỗ trợ hay bị bỏ qua?
- Có cần transaction mở trong lúc cursor được tiêu thụ không?
- Driver dùng server-side cursor, portal hay cơ chế prefetch nào?
- Khi subscriber giảm demand, driver có dừng fetch tiếp không?
- Khi cancel, cursor/portal được đóng và connection được trả như thế nào?
- Có giới hạn kích thước batch hoặc số hàng trong buffer không?

Không đặt fetch size quá lớn chỉ để giảm round trip; nó có thể tăng bộ nhớ. Fetch size quá nhỏ có thể làm tăng round trip và giảm throughput. Hãy benchmark theo kích thước hàng, độ trễ mạng và tốc độ consumer.

### 17.1. fetchSize không giải quyết việc giữ connection

Fetch size có thể giới hạn số hàng driver lấy mỗi lần, nhưng nếu toàn bộ result vẫn được stream tới client chậm, connection có thể vẫn cần tồn tại tới khi cursor hoàn tất. Fetch size chủ yếu điều chỉnh buffering/fetch behavior; pagination mới tạo ranh giới query hoàn tất giữa các page.

## 18. Giới hạn số stream và công việc đồng thời

Không phải endpoint stream nào cũng cần phục vụ số lượng client không giới hạn. Có thể đặt quota hoặc concurrency limit ở tầng ứng dụng:

- Giới hạn số export/stream đồng thời theo tenant hoặc user.
- Giới hạn số hàng, thời gian và tốc độ đọc.
- Dùng rate limiter hoặc bulkhead cho các endpoint tốn nhiều connection.
- Tách pool riêng cho workload báo cáo nếu kiến trúc và ngân sách database cho phép.
- Ưu tiên query page ngắn cho request tương tác.
- Dùng queue cho export dài và batch lớn.

Pool riêng không tạo thêm capacity vô hạn cho database. Tổng connection của tất cả pool và ứng dụng phải nằm trong ngân sách server.

### 18.1. Bulkhead cho endpoint stream

Bulkhead có thể giới hạn số tác vụ stream đồng thời để một nhóm client không chiếm toàn bộ tài nguyên của API. Khi vượt giới hạn, trả lỗi quá tải có thể retry sau hoặc đưa yêu cầu vào queue.

Không chỉ dựa vào semaphore giữ một permit mà không có timeout/cleanup. Permit phải được release khi complete, error hoặc cancel; dùng abstraction có hỗ trợ reactive lifecycle.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả `Flux` của query không giới hạn trực tiếp cho client chậm | Result và connection có thể tồn tại lâu | Giới hạn kết quả hoặc dùng page query |
| Nghĩ non-blocking đồng nghĩa không chiếm tài nguyên | Pool có thể cạn dù CPU thấp | Theo dõi connection hold time và active/pending pool metrics |
| Bọc toàn bộ stream trong `@Transactional` | Transaction/connection có thể sống theo response | Chỉ dùng transaction dài khi cần snapshot/atomicity rõ ràng |
| Dùng `collectList()` cho toàn bảng | Heap tăng theo tổng kết quả và latency first byte cao | Chỉ collect page nhỏ có giới hạn |
| Nghĩ `buffer(n)` tự release connection mỗi batch | Một result stream có thể vẫn giữ cùng connection | Thực hiện query riêng cho từng page |
| Dùng `onBackpressureBuffer()` không giới hạn | Buffer tăng và có thể OOM | Giữ backpressure hoặc dùng buffer bounded có overflow policy |
| Dùng `publishOn` để hy vọng query kết thúc sớm | Queue thêm buffer nhưng connection vẫn có thể mở | Tách query khỏi downstream bằng page/bounded materialization |
| `flatMap` không giới hạn gọi service ngoài | Quá nhiều request và kết quả chờ | Đặt concurrency hữu hạn |
| Enrich từng row bằng HTTP trong transaction | Connection bị giữ khi chờ mạng | Hoàn tất query theo page rồi enrich ngoài transaction |
| Chỉ dùng `take(n)` nhưng SQL vẫn không giới hạn | Driver có thể prefetch thêm và query plan không rõ mục tiêu | Đặt `LIMIT` ở SQL |
| Không kiểm tra cancellation | Client rời đi nhưng tài nguyên có thể được giải phóng trễ | Đo cancellation/cleanup và kiểm thử driver |
| Chỉ tăng pool size | Tăng connection pressure mà không giảm hold time | Giảm thời gian giữ connection và giới hạn stream |
| Dùng OFFSET sâu cho export lớn | Database phải bỏ qua nhiều hàng và hiệu năng giảm | Dùng keyset pagination với cursor ổn định |
| Cursor không có tie-breaker duy nhất | Có thể lặp hoặc bỏ sót hàng giữa page | Dùng khóa duy nhất trong ORDER BY và cursor |
| Phân trang nhưng giả định có snapshot nhất quán | Dữ liệu thay đổi giữa các page | Dùng cutoff/version/snapshot theo yêu cầu |
| Dựa vào fetchSize để release connection | Cursor vẫn có thể giữ connection đến cuối result | Dùng page query nếu cần release giữa các phần |
| Không giới hạn export đồng thời | Một nhóm request có thể chiếm toàn pool | Quota, bulkhead và export job |

## 20. Quy trình điều tra connection bị giữ lâu

Khi thấy request mới chờ connection hoặc pool thường xuyên hết capacity, hãy điều tra theo trình tự:

1. **Đo pool:** xem active/acquired, idle, pending acquire, acquire duration và timeout.
2. **Đo query:** so sánh thời gian execute/result với thời gian connection được giữ.
3. **Tìm stream dài:** xác định endpoint trả `Flux`, NDJSON, SSE hoặc export lớn.
4. **Kiểm tra downstream:** tốc độ client, proxy buffering, response duration và disconnect.
5. **Kiểm tra transaction:** xác định transaction có bao trùm toàn bộ Flux hoặc gọi HTTP/CPU lâu không.
6. **Kiểm tra operator:** tìm `collectList`, buffer không giới hạn, prefetch lớn, `flatMap` concurrency cao hoặc `publishOn` queue.
7. **Kiểm tra driver:** xác nhận fetch size, cursor, buffering và cancellation semantics.
8. **Tái hiện với client chậm:** mô phỏng tốc độ đọc thấp và ngắt kết nối giữa chừng.
9. **Thử chiến lược page:** đo thời gian giữ connection sau mỗi query page và mức bộ nhớ.
10. **Đặt giới hạn:** page size, query timeout, response timeout, concurrency và số stream đồng thời.

Không kết luận connection leak chỉ vì active connection tăng trong lúc stream đang chạy. Connection có thể đang được dùng hợp lệ. Leak được nghi ngờ khi subscription đã complete/error/cancel nhưng connection không được release theo thời hạn dự kiến, hoặc số connection bị giữ tăng dần mà không giảm.

## 21. Kiểm thử với downstream chậm và cancellation

Test thông thường đọc hết Flux ngay lập tức thường không phát hiện vấn đề giữ connection. Cần test các tình huống tiêu thụ chậm:

### 21.1. Mô phỏng consumer chậm

```java
Flux<CustomerView> slowConsumer = customerService.streamCustomers()
    .delayElements(Duration.ofMillis(100));
```

Đây là cách đơn giản để giảm tốc độ tiêu thụ trong test. Nó không mô phỏng đầy đủ network backpressure của HTTP client, nhưng có thể giúp quan sát thời gian publisher hoàn tất và connection hold duration.

### 21.2. Kiểm thử HTTP client đọc chậm

Với integration test WebFlux:

- Gọi endpoint streaming bằng client có thể điều khiển demand hoặc đọc response body từng phần.
- Giữ client đọc chậm trong khi quan sát active connection.
- Xác nhận connection được release sau khi response hoàn tất.
- Hủy request giữa chừng và kiểm tra cleanup/cancellation.
- Gọi endpoint khác đồng thời để xác nhận pool còn capacity.

### 21.3. Kiểm tra page query release connection

So sánh hai cách:

- Một `Flux` result duy nhất được tiêu thụ chậm tới hết.
- Nhiều page query nhỏ, mỗi page được `collectList()` rồi gửi dần.

Quan sát active connections và thời gian giữ connection trong lúc client đang đọc page. Với cách page, connection có thể rảnh giữa các page, trong khi bộ nhớ chỉ giữ page hiện tại.

### 21.4. Kiểm thử transaction

Nếu method có `@Transactional` hoặc dùng `TransactionalOperator`, xác nhận transaction kết thúc khi publisher hoàn tất hoặc bị hủy. Kiểm tra connection trả về pool sau complete, error và cancel. Với driver/database mục tiêu, xác nhận cancellation không để transaction hoặc cursor tồn tại ngoài dự kiến.

## 22. Chọn chiến lược theo use case

| Use case | Chiến lược nên cân nhắc | Lý do |
|---|---|---|
| Trang danh sách tương tác | SQL LIMIT + page nhỏ | Response nhanh, connection được dùng ngắn |
| Client cần stream vài trăm record | Flux streaming có giới hạn | Có thể giữ connection trong thời gian stream nhưng phạm vi được kiểm soát |
| Tải hàng triệu record | Export job + keyset page + file/object storage | Tách tốc độ client khỏi connection database |
| Dashboard cần dữ liệu nhỏ | `collectList()` hoặc aggregate có giới hạn | Release query trước khi response hoàn tất |
| Enrich mỗi record qua HTTP | Page query rồi enrich có concurrency hữu hạn | Tránh giữ connection khi chờ mạng |
| Đọc dữ liệu cần snapshot nhất quán | Snapshot/cutoff được thiết kế rõ | Đánh đổi giữa consistency và thời gian giữ transaction |
| SSE/event stream liên tục | Không giữ query R2DBC vô hạn | Dùng broker/event source phù hợp thay vì database cursor dài hạn |

## 23. Nguyên tắc cần nhớ

- Non-blocking giúp thread không bị chặn nhưng connection, transaction và buffer vẫn bị chiếm dụng.
- Với result stream, connection thường được giữ tới khi result hoàn tất, lỗi hoặc bị hủy và cleanup xong.
- Downstream tiêu thụ chậm có thể làm backpressure lan ngược tới R2DBC và kéo dài thời gian giữ connection.
- Backpressure không đồng nghĩa driver không prefetch hoặc không buffer; kiểm tra fetch behavior của driver.
- Streaming media type như NDJSON/SSE giúp biểu diễn response từng phần tử, nhưng codec/proxy vẫn ảnh hưởng buffering.
- Transaction bao trùm `Flux` có thể tồn tại tới cuối stream; `readOnly` không tự release connection sớm.
- `collectList()` giải phóng query trước khi gửi response nhưng giữ toàn bộ dữ liệu trong heap và tăng time-to-first-byte.
- `buffer(n)` không tự tạo query page mới và không bảo đảm release connection giữa batch.
- Buffer không giới hạn, prefetch và `flatMap` concurrency cao có thể làm tăng memory hoặc số công việc đang chờ.
- Giới hạn dữ liệu ngay trong SQL bằng `LIMIT` khi nghiệp vụ không cần toàn bộ tập.
- Dùng keyset pagination với cursor ổn định và tie-breaker duy nhất cho tập lớn.
- Mỗi page query hoàn tất có thể trả connection về pool trước khi gửi page chậm tới client.
- Pagination không tự bảo đảm snapshot nhất quán giữa các page; chọn cutoff/version/snapshot theo yêu cầu.
- Dùng fetch size/cursor chỉ khi driver hỗ trợ và hiểu rằng nó không nhất thiết release connection giữa result.
- Tách query khỏi HTTP/CPU/HTTP-service work chậm bằng page hoặc bounded materialization.
- Với export lớn, cân nhắc job bất đồng bộ và file thay vì giữ một response/connection lâu.
- Theo dõi active/idle/pending pool, acquire latency, connection hold duration, query duration và HTTP response duration.
- Kiểm thử client chậm, cancellation, timeout và cleanup trên WebFlux server cùng R2DBC driver thực tế.

Nguy cơ giữ kết nối lâu xuất hiện khi vòng đời database result gắn trực tiếp với tốc độ tiêu thụ của downstream. Backpressure giúp điều tiết dữ liệu nhưng không làm connection được trả về pool khi result chưa hoàn tất. Với stream nhỏ và có giới hạn, giữ connection trong lúc truyền có thể chấp nhận được. Với tập dữ liệu lớn hoặc client chậm, hãy rút ngắn từng lần truy vấn bằng page hữu hạn, giải phóng connection giữa các page, kiểm soát buffer/concurrency và tách export dài khỏi HTTP request. Kết hợp metrics pool với thời gian response và kiểm thử cancellation sẽ giúp phát hiện sớm tình trạng pool bị chiếm dụng dù ứng dụng vẫn non-blocking.
