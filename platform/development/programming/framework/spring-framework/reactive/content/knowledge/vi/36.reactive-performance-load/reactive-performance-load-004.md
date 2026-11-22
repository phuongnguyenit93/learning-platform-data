# Điều chỉnh prefetch, buffer và kích thước connection pool trong Spring WebFlux

## 1. Ba loại giới hạn thường bị nhầm lẫn

Trong ứng dụng Spring WebFlux, throughput và độ trễ chịu ảnh hưởng bởi nhiều lớp. Ba tham số thường được điều chỉnh cùng nhau nhưng kiểm soát ba tài nguyên khác nhau:

- **Prefetch**: lượng demand mà một operator yêu cầu trước từ upstream, hoặc số phần tử có thể được giữ sẵn trong một hàng đợi nội bộ của operator.
- **Buffer**: lượng dữ liệu được tích lũy để gom batch hoặc chờ consumer xử lý. Buffer có thể nằm trong một operator, ở ranh giới scheduler, trong queue của ứng dụng hoặc trong bộ đệm mạng.
- **Connection pool size**: số kết nối tới một remote host mà HTTP client được phép giữ/cho mượn đồng thời; với Reactor Netty đây là cấu hình của `ConnectionProvider`.

Chúng tương tác nhưng không thay thế nhau. Tăng prefetch không làm tăng số TCP connection. Tăng pool không làm consumer xử lý nhanh hơn. Tăng buffer có thể làm giảm dao động ngắn hạn nhưng cũng có thể tăng memory và latency khi downstream chậm.

| Tham số | Giới hạn chính | Đơn vị cần nghĩ tới |
| --- | --- | --- |
| `flatMap(..., concurrency, prefetch)` | Số inner Publisher đang chạy và số item được yêu cầu từ mỗi inner | Inner subscription / item |
| `publishOn(scheduler, prefetch)` | Hàng đợi tại asynchronous boundary | Item |
| `limitRate(highTide, lowTide)` | Kích thước các đợt request gửi upstream | Item / request batch |
| `buffer(maxSize)` | Số item được gom trong mỗi batch | Item / batch |
| `onBackpressureBuffer(maxSize)` | Số item được giữ khi consumer không theo kịp | Item / queue |
| `ConnectionProvider.maxConnections` | Số connection active tối đa trong một pool | TCP channel / host |
| `pendingAcquireMaxCount` | Số yêu cầu chờ connection tối đa | Pending request |
| `pendingAcquireTimeout` | Thời gian chờ connection | Thời gian |

Mục tiêu tuning là kiểm soát concurrency, demand và memory sao cho service downstream chịu được tải, latency ổn định và hệ thống có thể từ chối tải vượt năng lực một cách có kiểm soát.

## 2. Reactive Streams demand và backpressure

Reactive Streams truyền áp lực từ consumer về producer bằng `Subscription.request(n)`. Subscriber yêu cầu số item nó sẵn sàng nhận:

~~~text
        Downstream consumer
                |
                | request(8)
                v
         Operator / queue
                |
                | request(n) được điều chỉnh
                v
          Upstream source
                |
                v
            onNext(...)
~~~

Các điểm quan trọng:

- Demand là số phần tử downstream cho phép upstream phát thêm.
- `request(Long.MAX_VALUE)` biểu diễn demand không giới hạn.
- `cancel()` yêu cầu upstream dừng phát và giải phóng tài nguyên.
- Backpressure chỉ có tác dụng nếu upstream tôn trọng Reactive Streams demand hoặc có adapter điều tiết nguồn đó.
- Nguồn callback/hot source bên ngoài có thể phát nhanh hơn consumer; khi đó phải chọn buffer, drop, latest hoặc overflow policy.

### 2.1. Những thao tác thường yêu cầu unbounded demand

Các cách subscribe tiện lợi như `subscribe()` với lambda, `block()`, `blockFirst()`, `blockLast()`, `toIterable()` và `toStream()` thường yêu cầu unbounded demand. Đây là lý do không nên tự subscribe hoặc block trong controller/service WebFlux.

~~~java
// Không nên trong WebFlux handler:
source.subscribe(this::process);

// Cũng không nên trên Netty event loop:
Result result = source.block();
~~~

Hãy compose publisher rồi trả về framework:

~~~java
return source
        .concatMap(this::processReactive)
        .then();
~~~

`block()` có thể phù hợp ở boundary của command-line demo hoặc test đồng bộ, nhưng không nên dùng trong reactive request pipeline.

### 2.2. Backpressure không phải rate limiting theo giây

`limitRate(32)` chia demand thành các đợt tối đa 32 item. Nó không có nghĩa chỉ cho phép 32 item mỗi giây. Muốn giới hạn tốc độ theo thời gian, cần rate limiter/token bucket hoặc chính sách tương ứng ở tầng ứng dụng.

## 3. Prefetch thực sự điều chỉnh điều gì?

Prefetch là số item operator yêu cầu trước từ upstream để có dữ liệu sẵn khi downstream cần. Nó thường xuất hiện ở operator có queue hoặc xử lý Publisher lồng nhau.

Ví dụ:

~~~java
Flux<Result> results = ids.flatMap(
        id -> service.fetch(id),
        8,  // maxConcurrency
        4   // prefetch per inner Publisher
);
~~~

Ý nghĩa:

- Tối đa 8 inner Publisher được subscribe đồng thời.
- Với mỗi inner Publisher, operator có thể yêu cầu trước tối đa 4 item theo cấu hình prefetch.
- Với nguồn nhiều item, số item đang được yêu cầu/giữ sẵn có thể tăng theo concurrency và prefetch.
- Nếu mỗi inner là `Mono<Result>`, nó chỉ phát tối đa một item nên prefetch 4 không tạo ra bốn kết quả cho mỗi request.

Prefetch **không** có nghĩa là:

- Số thread được tạo.
- Số TCP connection.
- Số request mỗi giây.
- Số item chắc chắn nằm trong RAM mọi lúc.
- Giới hạn tổng số item mà toàn bộ pipeline sẽ xử lý.

Nó là một phần của cơ chế demand/queue. Một operator có thể phát ít hơn mức prefetch nếu nguồn hoàn tất sớm hoặc downstream không cần thêm dữ liệu.

### 3.1. Giá trị mặc định phụ thuộc operator

Tài liệu Reactor ghi nhận nhiều operator dùng prefetch mặc định 32, nhưng không nên suy rộng con số đó thành mặc định cho mọi operator. Một số operator còn có tham số concurrency riêng; các default có thể khác nhau theo operator và phiên bản Reactor.

Khi cần hành vi dễ dự đoán ở điểm nóng, chỉ định rõ overload có prefetch:

~~~java
Flux<Result> result = source.flatMap(
        this::callRemote,
        12,
        2);
~~~

Con số 12 và 2 chỉ là cấu hình ví dụ. Phải chọn dựa trên latency downstream, kích thước payload, số kết nối khả dụng và memory budget.

## 4. Prefetch ở các operator quan trọng

### 4.1. flatMap: concurrency và prefetch là hai tham số khác nhau

~~~java
Flux<Product> products = productIds.flatMap(
        id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class),
        16,
        1);
~~~

- `16` là số inner request có thể đang chạy đồng thời.
- `1` là prefetch của từng inner Publisher.
- Vì inner ở đây là `Mono`, prefetch 1 thường thể hiện đúng bản chất một response cho mỗi ID.
- Output của flatMap có thể xen kẽ theo thời điểm request hoàn tất; không bảo đảm giữ thứ tự ID ban đầu.

Nếu concurrency là 16 nhưng pool chỉ cho 4 connection tới host đó, có thể chỉ 4 request đang giữ connection, phần còn lại chờ acquire. Đây là một hàng đợi khác với prefetch queue.

### 4.2. concatMap: tuần tự và giữ thứ tự

~~~java
Flux<Result> results = ids.concatMap(
        id -> service.fetch(id),
        8);
~~~

`concatMap` chỉ subscribe inner Publisher kế tiếp khi inner trước hoàn tất. Nó giữ thứ tự đầu vào và tránh nhiều tác vụ inner chạy đồng thời. Tham số prefetch ở đây điều chỉnh demand với **nguồn đầu vào**, không có nghĩa chạy 8 request đồng thời.

Dùng khi các command phụ thuộc thứ tự hoặc cùng cập nhật một state. Nếu remote call độc lập và throughput là yêu cầu chính, concatMap có thể giới hạn concurrency quá chặt.

### 4.3. flatMapSequential: chạy song song nhưng phát đúng thứ tự

~~~java
Flux<Result> results = ids.flatMapSequential(
        id -> service.fetch(id),
        8,
        2);
~~~

Operator có thể subscribe tối đa 8 inner Publisher đồng thời, nhưng kết quả được phát theo thứ tự nguồn. Nếu item đầu tiên xử lý chậm còn các item sau hoàn tất nhanh, kết quả của những inner sau phải chờ trong queue.

Đây là head-of-line blocking ở tầng phát kết quả. Dùng khi cần song song nhưng contract yêu cầu thứ tự; không chọn chỉ vì muốn “có cả concurrency lẫn order” mà không tính memory queue.

### 4.4. publishOn: queue tại ranh giới Scheduler

~~~java
Flux<Result> results = source
        .publishOn(Schedulers.parallel(), 32)
        .map(this::cpuBoundTransform);
~~~

`publishOn` chuyển xử lý downstream sang Scheduler được chỉ định. Prefetch là capacity/demand tại asynchronous boundary. Nếu upstream nhanh và downstream xử lý chậm, các item có thể chờ trong queue của publishOn.

Một `publishOn` không tạo một pool TCP mới. Nó cũng không biến I/O blocking thành non-blocking. Chỉ dùng Scheduler phù hợp với loại công việc: CPU-bound, blocking I/O hoặc event-loop không có cùng đặc tính.

### 4.5. limitRate: chia nhỏ request

~~~java
Flux<Event> events = eventSource
        .limitRate(64, 48);
~~~

`highTide` là mức request ban đầu/giới hạn mỗi đợt; `lowTide` là lượng demand được bổ sung khi đã tiêu thụ đủ item. Ví dụ 64 và 48 tạo các đợt request có kiểm soát.

Nếu chỉ dùng `limitRate(64)`, Reactor dùng chiến lược replenish mặc định theo tỷ lệ của prefetch. Đây là điều chỉnh demand, không loại bỏ item và không đặt giới hạn tổng số item.

## 5. Buffer: gom batch hay hàng đợi chờ consumer?

Từ “buffer” xuất hiện ở nhiều operator nhưng ý nghĩa khác nhau.

| Cơ chế | Mục đích | Khi nào phát item tiếp? |
| --- | --- | --- |
| `buffer(100)` | Gom 100 item thành một List | Khi đủ 100 item hoặc nguồn complete |
| `bufferTimeout(100, Duration.ofMillis(50))` | Gom theo kích thước hoặc thời gian | Khi đủ 100 item hoặc hết 50 ms |
| `publishOn(scheduler, 32)` | Queue qua ranh giới Scheduler | Theo downstream demand |
| `onBackpressureBuffer(256)` | Giữ tối đa 256 item khi downstream chậm | Khi downstream có demand |
| Queue/Sink do ứng dụng quản lý | Nối callback/event producer với reactive consumer | Theo policy queue của ứng dụng |

Không dùng từ “buffer” chung chung khi debug. Hãy xác định đó là batch buffer, operator queue, scheduler queue, network buffer hay queue nghiệp vụ.

### 5.1. buffer(N) làm thay đổi hình dạng demand

Nếu downstream yêu cầu 2 buffer và mỗi buffer chứa 10 item, operator có thể cần yêu cầu 20 item từ upstream để tạo đủ 2 buffer:

~~~text
Downstream request(2 batches)
            |
            v
      buffer(10)
            |
            v
Upstream request(2 x 10 = 20 items)
~~~

Điều này quan trọng khi upstream là database paging hoặc API có chi phí cho mỗi lần request. Tăng batch size có thể giảm số lần round trip nhưng cũng làm tăng memory, latency chờ đủ batch và kích thước giao dịch.

### 5.2. bufferTimeout để cân bằng throughput và latency

~~~java
Flux<List<Event>> batches = events.bufferTimeout(
        100,
        Duration.ofMillis(50));
~~~

Batch được phát khi đủ 100 event hoặc khi đã đến 50 ms. Cách này hữu ích khi muốn giảm số lần ghi database/broker nhưng vẫn có giới hạn chờ.

- Batch lớn hơn: ít round trip hơn, nhưng memory và latency chờ batch tăng.
- Batch nhỏ hơn: phản hồi nhanh hơn, nhưng overhead mỗi lần ghi tăng.
- Timeout ngắn hơn: batch có thể ít item, tăng số lần gọi downstream.
- Timeout dài hơn: batch đầy hơn nhưng item đầu tiên chờ lâu hơn.

Đo p95/p99 và throughput thực tế; đừng chỉ đo số item/giây.

### 5.3. onBackpressureBuffer phải có giới hạn

~~~java
Flux<Event> safe = hotSource.onBackpressureBuffer(500);
~~~

Overload giới hạn kích thước giúp queue không tăng vô hạn. Khi vượt giới hạn, pipeline phát lỗi overflow theo semantics của operator. Ứng dụng phải quyết định xử lý lỗi đó: từ chối producer, đóng kết nối, retry có giới hạn hoặc ghi vào durable queue.

Không dùng buffer vô hạn cho stream có thể chạy lâu hoặc producer không kiểm soát được. Nếu mỗi event giữ 32 KiB và queue có 10.000 event, riêng payload thô đã xấp xỉ 312,5 MiB, chưa tính object overhead và các queue khác.

### 5.4. Chọn drop, latest hay buffer theo nghiệp vụ

| Chiến lược | Hành vi | Dùng khi |
| --- | --- | --- |
| Buffer hữu hạn | Giữ item chờ consumer; overflow thành lỗi hoặc policy khác | Không muốn mất item trong burst ngắn |
| Drop | Bỏ item mới khi không có demand | Telemetry có thể mất mẫu |
| Latest | Giữ giá trị mới nhất, loại giá trị cũ chưa tiêu thụ | Trạng thái hiện tại, giá trị sensor |
| Error | Báo lỗi khi upstream vượt khả năng tiếp nhận | Muốn fail-fast và kiểm soát tải |

Không drop command thanh toán, audit hoặc sự kiện cần bảo toàn nếu chưa có persistence/replay. Với trạng thái có thể thay thế, latest/coalescing có thể hợp lý hơn buffer dài.

## 6. Ước lượng memory do prefetch và queue

Prefetch và buffer phải được tính theo **kích thước item**, không chỉ số lượng.

Một ước lượng đơn giản cho queue:

\[
M_{\text{queue}} \approx
\sum_i Q_i \times S_i
\]

Trong đó:

- \(Q_i\): số item tối đa có thể chờ ở queue i.
- \(S_i\): kích thước trung bình item được giữ (payload + object graph liên quan).

Ví dụ:

- `flatMap` concurrency = 16.
- Prefetch mỗi inner = 8.
- Kích thước item trung bình = 64 KiB.

Ước lượng thô số item có thể được giữ trong các inner queue:

\[
16 \times 8 \times 64\text{ KiB} = 8\text{ MiB}
\]

Con số này **không phải tổng memory của ứng dụng**. Nó chưa tính source queue, publishOn queue, buffer batch, decoded object, Netty direct buffers, response bodies, pending connection requests và overhead JVM. Nó chỉ cho thấy concurrency × prefetch × payload size có thể tạo footprint đáng kể.

Nếu tăng concurrency từ 16 lên 64 trong khi prefetch và payload không đổi, lượng item đang được yêu cầu/giữ có thể tăng nhiều lần. Nếu downstream vẫn chậm, việc tăng concurrency có thể làm memory tăng mà không cải thiện latency.

## 7. Connection pool trong Reactor Netty

`WebClient` thường dùng Reactor Netty connector trong Spring Boot WebFlux. `HttpClient.create()` sử dụng `ConnectionProvider` để quản lý các kết nối có thể tái sử dụng.

Một pool quản lý các connection theo remote host; host được hiểu là kết hợp hostname và port.

~~~text
                 WebClient
                     |
                 HttpClient
                     |
              ConnectionProvider
                     |
       +-------------+-------------+
       |             |             |
   Connection 1  Connection 2  Connection 3
       |             |             |
       +-------------+-------------+
                     |
                Remote API
~~~

Với HTTP/1.1 thông thường, mỗi connection thường phục vụ một request đang sử dụng tại một thời điểm; sau khi response được đọc/giải phóng, connection có thể trở lại pool để tái sử dụng.

Các khái niệm:

- **Active connection:** đang được request sử dụng.
- **Idle connection:** sẵn sàng được request khác mượn.
- **Pending acquire:** request đang chờ connection.
- **Max connections:** giới hạn active channel trong pool.
- **Acquire timeout:** thời gian tối đa request chờ mượn connection.
- **Max idle time:** thời gian connection có thể nằm idle.
- **Max life time:** tuổi thọ tối đa của connection.

Connection pool là bulkhead ở tầng transport: nó giới hạn mức concurrency tới một downstream host. Nhưng nếu pending queue không giới hạn hoặc timeout quá dài, request chờ có thể tích lũy ở phía trước pool.

## 8. Các tham số ConnectionProvider quan trọng

Ví dụ tạo pool riêng cho một downstream:

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("inventory-api")
                .maxConnections(32)
                .pendingAcquireMaxCount(64)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(2))
                .evictInBackground(Duration.ofSeconds(30))
                .metrics(true)
                .build();
~~~

| API | Ý nghĩa | Cách chọn |
| --- | --- | --- |
| `maxConnections(32)` | Active connection tối đa trong mỗi host pool | Dựa trên concurrency, latency và năng lực upstream |
| `pendingAcquireMaxCount(64)` | Số request tối đa được xếp hàng chờ | Giới hạn burst và memory |
| `pendingAcquireTimeout(500ms)` | Thời gian chờ connection trước khi lỗi | Phù hợp SLA request |
| `maxIdleTime(20s)` | Tuổi idle tối đa | Nên bằng hoặc thấp hơn idle timeout của server/proxy |
| `maxLifeTime(2m)` | Tuổi thọ tối đa của connection | Dùng khi cần xoay connection theo policy |
| `evictInBackground(30s)` | Chu kỳ kiểm tra/eviction nền | Dùng khi muốn pool dọn connection idle hết hạn định kỳ |
| `metrics(true)` | Bật tích hợp metrics Reactor Netty | Cần Micrometer/registry phù hợp để quan sát |

Các con số trên chỉ là ví dụ minh họa. Đừng copy 32/64/500 ms vào mọi dịch vụ.

### 8.1. Phân biệt default của HttpClient.create() và custom provider

Tài liệu Reactor Netty hiện hành mô tả hai tình huống khác nhau:

- Shared provider mặc định dùng bởi `HttpClient.create()` có fixed pool với tối đa 500 active channels và 1000 pending acquire attempts cho mỗi remote host.
- Khi tự tạo `ConnectionProvider.builder(...)`, default `maxConnections` được tính theo 2 × số processor khả dụng, tối thiểu 16; default pending acquire count là 2 × max connections.
- Default `pendingAcquireTimeout` là 45 giây.
- `maxIdleTime` và `maxLifeTime` không được đặt mặc định trong bảng cấu hình pool.

Các default phụ thuộc phiên bản Reactor Netty và có thể bị thay đổi bởi system properties. Khi tạo custom provider, hãy cấu hình rõ các giới hạn phù hợp với workload thay vì dựa vào default của shared provider.

### 8.2. Pending queue là một hàng đợi thật

Nếu `maxConnections=10` và `pendingAcquireMaxCount=20`, tối đa 10 request giữ connection còn 20 request có thể chờ acquire trong pool đó. Những request tiếp theo bị từ chối theo pool policy.

Queue hữu hạn giúp hệ thống từ chối overload trước khi request chờ vô hạn. `pendingAcquireTimeout` quá dài có thể khiến request đã gần hết deadline vẫn nằm trong queue.

Không cấu hình `pendingAcquireMaxCount(-1)` hoặc `pendingAcquireTimeout(-1)` một cách tùy tiện để “không còn pool timeout”. Hệ thống có thể tích lũy lượng chờ không giới hạn và cạn memory.

### 8.3. MaxIdleTime nên tính theo timeout phía server

Nếu reverse proxy đóng connection sau 30 giây idle, đặt client maxIdleTime dài hơn đáng kể có thể khiến client mượn phải connection đã bị peer đóng. Tài liệu Reactor Netty khuyến nghị chọn maxIdleTime bằng hoặc ngắn hơn idle timeout của target server để giảm lỗi I/O do connection stale.

Không có một giá trị chung cho mọi upstream. Kiểm tra load balancer, gateway và server timeout trước khi đặt.

## 9. HTTP/2: số connection không bằng số request đồng thời

HTTP/2 hỗ trợ multiplex nhiều stream trên cùng một TCP connection. Do đó:

- `maxConnections` vẫn giới hạn số channel/connection trong pool.
- Một connection HTTP/2 có thể mang nhiều stream đồng thời theo giới hạn peer/protocol.
- Số request đồng thời còn phụ thuộc stream capacity, server SETTINGS và các giới hạn client.
- Metrics HTTP/2 có thể cung cấp active streams và pending streams.

Không lấy công thức HTTP/1.1 “một connection = một request active” để tính pool HTTP/2. Khi bật HTTP/2, quan sát stream metrics và giới hạn peer trước khi giảm hoặc tăng connection count.

## 10. Tính kích thước pool bằng concurrency và latency

Một điểm bắt đầu hữu ích là định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống.
- \(\lambda\): throughput trung bình (request/giây).
- \(W\): thời gian trung bình một request chiếm tài nguyên (giây).

Ví dụ:

- Downstream nhận 120 request/giây.
- Thời gian trung bình từ lúc acquire đến khi connection được release là 80 ms = 0,08 giây.

\[
L = 120 \times 0.08 = 9.6
\]

Như vậy trung bình khoảng 10 connection đang được sử dụng nếu tất cả request đi tới cùng host và mô hình HTTP/1.1 một request/connection.

Đây chỉ là **concurrency trung bình**, không phải con số maxConnections bắt buộc. Cần thêm headroom cho burst và tail latency, đồng thời tôn trọng giới hạn mà upstream chịu được.

### 10.1. Quy trình sizing thực tế

1. Đo throughput dự kiến tới từng downstream host.
2. Đo thời gian connection bị giữ (request gửi tới lúc response body được consume/release).
3. Tính concurrency trung bình bằng Little's Law.
4. Đo p95/p99 và burst pattern.
5. Chọn maxConnections có headroom nhưng không vượt khả năng upstream.
6. Chọn pendingAcquireMaxCount nhỏ, đủ hấp thụ burst ngắn.
7. Đặt pendingAcquireTimeout ngắn hơn phần deadline còn lại của request.
8. Chạy load test, quan sát active/idle/pending, latency và error rate.
9. Thay đổi một tham số mỗi lần để biết tác động.
10. Lặp lại với nhiều host và nhiều profile tải.

### 10.2. Tăng pool quá lớn có thể làm hệ thống tệ hơn

Pool lớn có thể:

- Tăng số TCP/TLS handshake đồng thời.
- Tăng file descriptor, socket memory và Netty buffer usage.
- Đẩy nhiều request hơn vào một upstream đang quá tải.
- Tăng lock/contention hoặc queue ở database/API đích.
- Làm tăng connect timeout hoặc premature close khi tạo quá nhiều connection cùng lúc.

Tài liệu Reactor Netty cảnh báo pool maxConnections quá cao trong high load có thể dẫn đến `PrematureCloseException` với root cause Connect Timeout do quá nhiều connection được mở/acquire.

Nếu upstream chỉ chịu 20 request đồng thời, đặt pool 500 không làm nó nhanh hơn. Nó có thể chỉ chuyển queue từ client sang server.

## 11. Đồng bộ concurrency của flatMap với pool

Giả sử:

- `flatMap` concurrency = 24.
- `ConnectionProvider.maxConnections` = 8.
- Mỗi inner publisher thực hiện một HTTP request tới cùng host.

Có thể hình dung:

~~~text
             flatMap concurrency = 24
           /          |           \
      8 active      8 pending    8 not yet active
          |             |
          v             v
     Pool max=8     acquire queue
          |
          v
       Remote API
~~~

Thực tế số pending và thời điểm tạo inner còn phụ thuộc demand/operator; sơ đồ chỉ minh họa áp lực khi concurrency vượt khả năng pool.

Hướng lựa chọn:

- Nếu muốn giới hạn tổng số remote calls, đặt flatMap concurrency gần với số connection/stream capacity mà downstream chấp nhận.
- Nếu muốn có một pending queue nhỏ để hấp thụ burst, concurrency có thể cao hơn maxConnections một mức có kiểm soát.
- Nếu pending connections luôn cao, hãy xem lại latency upstream, pool size, concurrency và deadline.
- Nếu pool active thấp nhưng flatMap backlog lớn, có thể bottleneck ở nguồn dữ liệu hoặc scheduler chứ không phải connection.

Không cần ép flatMap concurrency luôn bằng maxConnections. Hai lớp có mục đích riêng, nhưng phải có ngân sách tổng thể rõ ràng.

## 12. Cấu hình WebClient với pool dùng chung

Trong ứng dụng Spring Boot, nên tạo provider và WebClient như bean dùng chung theo downstream dependency:

~~~java
@Configuration
class PartnerClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerConnectionProvider() {
        return ConnectionProvider.builder("partner-api")
                .maxConnections(32)
                .pendingAcquireMaxCount(64)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(2))
                .metrics(true)
                .build();
    }

    @Bean
    WebClient partnerWebClient(
            ConnectionProvider partnerConnectionProvider) {

        HttpClient httpClient =
                HttpClient.create(partnerConnectionProvider)
                        .option(
                                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                1_000)
                        .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
                .baseUrl("https://partner.example.test")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

Ví dụ cần các import Spring WebFlux, Reactor Netty và Netty tương ứng. Host `partner.example.test` là địa chỉ minh họa; thay bằng endpoint thật của hệ thống.

Điểm thiết kế:

- Provider được tạo một lần và tái sử dụng.
- Tên pool giúp phân biệt metrics.
- Pool có giới hạn active và pending.
- Timeout acquire, connect và response có mục đích riêng.
- `destroyMethod="dispose"` giúp Spring giải phóng custom provider khi context đóng.

Không tạo một `ConnectionProvider` mới trong mỗi request/controller invocation. Làm vậy phá khả năng tái sử dụng connection và tạo nhiều pool không cần thiết.

### 12.1. Pool riêng theo downstream để bulkhead

Nếu một API chậm, không để toàn bộ downstream share một pool duy nhất mà không có lý do. Có thể tạo pool riêng cho inventory, billing và notification để giới hạn tài nguyên theo dependency.

Pool riêng không cô lập hoàn toàn CPU, event loop, heap hay database, nhưng giúp kiểm soát concurrency và pending acquire ở từng remote host/service.

### 12.2. Khi nào không dùng pool?

`HttpClient.newConnection()` tạo connection mới cho mỗi request thay vì dùng pool. Đây không phải lựa chọn mặc định cho workload HTTP thông thường. Có thể dùng cho test, kết nối đặc biệt hoặc trường hợp muốn tránh reuse có chủ đích; phải tính chi phí handshake và socket.

## 13. Metrics để biết nên chỉnh tham số nào

Reactor Netty có thể xuất metrics qua Micrometer. Với pooled ConnectionProvider, prefix là:

`reactor.netty.connection.provider`

Các metric quan trọng:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| `total.connections` | Tổng active + idle connection | Tăng bất thường hoặc không giảm |
| `active.connections` | Connection đang được sử dụng | Luôn sát max |
| `idle.connections` | Connection đang rảnh trong pool | Quá thấp khi có burst |
| `max.connections` | Giới hạn active connection | Đối chiếu với cấu hình |
| `pending.connections` | Request đang chờ acquire | Tăng liên tục |
| `pending.connections.time` | Thời gian chờ acquire | p95/p99 cao |
| `max.pending.connections` | Giới hạn pending | Thường xuyên chạm trần |

HTTP client metrics còn có `reactor.netty.http.client.response.time`, connect time, TLS handshake time, data sent/received và errors. Khi cần HTTP/2, theo dõi active/pending streams.

Bật metrics:

~~~java
ConnectionProvider provider =
        ConnectionProvider.builder("partner-api")
                .maxConnections(32)
                .metrics(true)
                .build();
~~~

Đảm bảo Micrometer dependency và metrics registry phù hợp được cấu hình trong ứng dụng. Không đưa raw URL/ID user vào metric tag vì cardinality có thể tăng không giới hạn.

### 13.1. Đọc pattern metrics

| Quan sát | Hướng điều tra |
| --- | --- |
| Active luôn bằng max, pending tăng, response time ổn định | Pool có thể quá nhỏ so với throughput cần thiết hoặc concurrency quá cao |
| Active bằng max, pending tăng, response time upstream tăng | Upstream chậm; tăng pool có thể làm upstream quá tải thêm |
| Pending acquire time tăng nhưng active thấp | Pool acquisition/connection lifecycle hoặc host pool mapping có vấn đề |
| Active thấp, event-loop pending tasks cao | Có thể bottleneck ở event loop/CPU, không phải pool |
| Pool ổn định nhưng heap/direct memory tăng | Tìm buffer, response aggregation, queue hoặc leak |
| Pending chạm max rồi acquire timeout | Hệ thống đang từ chối tải vượt giới hạn |

Không kết luận từ một metric đơn lẻ. Đối chiếu latency, error rate, CPU, heap/direct memory, event-loop tasks và metrics của upstream.

## 14. Tuning prefetch, buffer và pool theo từng tình huống

### 14.1. CPU-bound transformation

Nếu xử lý CPU nặng, tăng flatMap concurrency hoặc prefetch có thể không giúp khi CPU đã bão hòa. Dùng bounded scheduler/parallelism phù hợp và giữ queue hữu hạn:

~~~java
Flux<Result> result = source
        .publishOn(Schedulers.parallel(), 16)
        .map(this::expensiveTransform);
~~~

Theo dõi CPU, scheduler queue và latency. Không thêm nhiều publishOn liên tiếp nếu không có boundary cần thiết.

### 14.2. Remote API chậm

- Đặt pool max theo năng lực upstream.
- Giới hạn flatMap concurrency.
- Đặt pending queue nhỏ.
- Đặt acquire/connect/response timeout phù hợp.
- Không tăng prefetch nếu inner là Mono và vấn đề nằm ở latency connection.
- Dùng retry có giới hạn và idempotency cho thao tác có side effect.

### 14.3. Database paging

Có thể dùng limitRate hoặc buffer để điều chỉnh lượng request/page:

~~~java
Flux<Row> rows = repository.streamAll()
        .limitRate(128, 96);
~~~

Nếu cần batch insert:

~~~java
Flux<Void> writes = rows
        .bufferTimeout(100, Duration.ofMillis(100))
        .concatMap(batch -> repository.insertBatch(batch));
~~~

Batch write tuần tự giúp kiểm soát tải database. Nếu batch độc lập có thể chạy song song, dùng flatMap với concurrency thấp và đo lock/connection pool ở database driver.

### 14.4. Event stream nhiều hơn tốc độ consumer

Nếu source có thể phát nhanh:

- Ưu tiên backpressure end-to-end.
- Nếu source không hỗ trợ demand, dùng queue hữu hạn.
- Chọn drop/latest chỉ khi nghiệp vụ cho phép mất item.
- Với sự kiện cần bảo toàn, dùng broker/durable storage và consumer offset thay vì RAM queue.
- Theo dõi overflow/drop count.

### 14.5. Response body lớn

Không tăng mọi buffer để “đỡ chậm”. Hãy streaming response bằng `bodyToFlux` nếu protocol cho phép, đặt giới hạn memory, consume body để connection được release và tránh gom tất cả vào một List/String quá lớn.

## 15. Load test: thay đổi từng biến một

Một kế hoạch thực nghiệm có thể gồm:

1. **Baseline:** pool/concurrency/prefetch nhỏ, buffer hữu hạn.
2. **Warm-up:** khởi tạo connection, DNS/TLS và JIT.
3. **Steady load:** tăng request rate từng bậc.
4. **Burst:** tạo tải đột biến ngắn để xem pending queue.
5. **Soak:** giữ tải lâu để phát hiện memory/connection leak.
6. **Slow downstream:** mô phỏng upstream tăng latency.
7. **Failure:** trả 429/503 hoặc đóng connection.
8. **Recovery:** kiểm tra pool và pending queue có trở về baseline không.

Mỗi lần chỉ đổi một nhóm tham số:

- Prefetch: 4 → 8 → 16.
- flatMap concurrency: 4 → 8 → 16.
- Pool maxConnections: 8 → 16 → 24.
- Pending queue: 8 → 16 → 32.
- Batch size: 32 → 64 → 128.

Ghi lại:

- Throughput.
- p50, p95, p99 latency.
- Error/timeout rate.
- Active/idle/pending connections.
- Pending acquire time.
- Heap và direct memory.
- CPU và event-loop pending tasks.
- Upstream latency, 429/503 và connection errors.

Giữ cấu hình đem lại throughput tốt **mà không làm p99, error rate hoặc memory vượt ngưỡng**. Tuning không phải cuộc thi tối đa hóa maxConnections.

## 16. Chương trình Java 17+ chạy được: giới hạn pool ở hai connection

Ví dụ này dùng JDK HttpServer local và WebClient/Reactor Netty. Sáu HTTP request được phát với flatMap concurrency 6, nhưng custom pool chỉ cho phép hai connection active. Server đo số request đồng thời để minh họa giới hạn transport.

Chương trình không gọi internet, không cần Identity Provider hay API bên ngoài.

### 16.1. Cấu trúc dự án

~~~text
webflux-pool-demo/
  pom.xml
  src/main/java/example/pool/PoolSizingDemo.java
~~~

Yêu cầu JDK 17+, Maven 3.6.3+ và Spring Boot 4.1.2.

### 16.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-pool-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 16.3. PoolSizingDemo.java

~~~java
package example.pool;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

public final class PoolSizingDemo {

    private static void handle(
            HttpExchange exchange,
            AtomicInteger active,
            AtomicInteger maximum) {

        int current = active.incrementAndGet();
        maximum.accumulateAndGet(current, Math::max);

        try {
            Thread.sleep(150);

            String path = exchange.getRequestURI().getPath();
            String id = path.substring("/work/".length());
            byte[] body = ("ok-" + id)
                    .getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");

            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        }
        catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            exchange.close();
        }
        catch (IOException error) {
            exchange.close();
        }
        finally {
            active.decrementAndGet();
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        ExecutorService serverExecutor =
                Executors.newFixedThreadPool(8);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.setExecutor(serverExecutor);
        server.createContext("/work", exchange ->
                handle(exchange, active, maximum));
        server.start();

        ConnectionProvider provider =
                ConnectionProvider.builder("demo-pool")
                        .maxConnections(2)
                        .pendingAcquireMaxCount(10)
                        .pendingAcquireTimeout(
                                Duration.ofSeconds(3))
                        .build();

        try {
            HttpClient transport = HttpClient.create(provider)
                    .option(
                            ChannelOption.CONNECT_TIMEOUT_MILLIS,
                            1_000)
                    .responseTimeout(Duration.ofSeconds(2));

            WebClient client = WebClient.builder()
                    .baseUrl("http://127.0.0.1:"
                            + server.getAddress().getPort())
                    .clientConnector(
                            new ReactorClientHttpConnector(transport))
                    .build();

            List<String> responses = Flux.range(1, 6)
                    .flatMap(
                            id -> client.get()
                                    .uri("/work/{id}", id)
                                    .retrieve()
                                    .bodyToMono(String.class),
                            6,
                            1)
                    .sort()
                    .collectList()
                    .block(Duration.ofSeconds(10));

            List<String> expected = List.of(
                    "ok-1", "ok-2", "ok-3",
                    "ok-4", "ok-5", "ok-6");

            if (!expected.equals(responses)) {
                throw new AssertionError(
                        "Unexpected responses: " + responses);
            }

            if (maximum.get() > 2) {
                throw new AssertionError(
                        "Pool limit exceeded: " + maximum.get());
            }

            System.out.println("responses=" + responses);
            System.out.println(
                    "max-server-in-flight=" + maximum.get());
        }
        finally {
            provider.disposeLater()
                    .block(Duration.ofSeconds(3));
            server.stop(0);
            serverExecutor.shutdownNow();
        }
    }
}
~~~

### 16.4. Chạy chương trình

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.pool.PoolSizingDemo
~~~

**Stdout dự kiến:**

~~~text
responses=[ok-1, ok-2, ok-3, ok-4, ok-5, ok-6]
max-server-in-flight=2
~~~

Giải thích:

- `Flux.range(1, 6)` tạo sáu ID.
- `flatMap(..., 6, 1)` cho phép tối đa sáu inner request cùng hoạt động; prefetch mỗi Mono là 1.
- `ConnectionProvider.maxConnections(2)` giới hạn hai connection active trong pool tới host local.
- Các request còn lại chờ acquire, rồi lần lượt sử dụng connection khi request trước hoàn tất.
- JDK HttpServer theo dõi số handler đang chạy; assertion bảo đảm con số không vượt 2.
- `sort()` làm thứ tự response ổn định trước khi in.

Đây là demo HTTP/1.1 local. HTTP/2 có multiplex nhiều stream trên một connection nên không thể suy ra số request active chỉ từ số connection.

## 17. Cách đọc kết quả demo và mở rộng thử nghiệm

Thử thay:

~~~java
.maxConnections(4)
~~~

và giữ `flatMap concurrency=6`. Server có thể xử lý tối đa bốn request đồng thời.

Thử thay:

~~~java
.maxConnections(2)
.pendingAcquireMaxCount(1)
~~~

Khi nhiều request cùng acquire, một số yêu cầu có thể bị từ chối vì pending queue quá nhỏ. Đây là ví dụ về backpressure/bulkhead ở tầng connection pool; không nên coi lỗi acquire là lỗi JSON hoặc lỗi nghiệp vụ.

Thử thay `flatMap concurrency` thành 2 trong khi pool vẫn là 2: số request được tạo đồng thời cũng bị giới hạn ở pipeline trước khi chạm pool. Điều này giúp phân biệt queue do flatMap với queue do ConnectionProvider.

Demo cố tình dùng server local để kết quả không phụ thuộc internet. Thời gian mỗi request có thể thay đổi theo máy, nhưng giới hạn active connection vẫn phải không vượt 2.

## 18. Những lỗi tuning thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tăng prefetch để tăng TCP connections | Không tác động connection pool | Chỉnh maxConnections riêng |
| Tăng maxConnections để chữa queue CPU | Tạo nhiều request hơn nhưng CPU vẫn bão hòa | Đo event-loop/CPU/scheduler |
| Tăng flatMap concurrency vô hạn | Tăng inner subscriptions và áp lực downstream | Giới hạn concurrency |
| Dùng prefetch lớn cho payload rất lớn | Queue giữ nhiều memory | Giảm prefetch hoặc stream nhỏ |
| buffer() trên stream vô hạn | Không phát batch cho tới khi complete, memory tăng vô hạn | buffer(maxSize) hoặc bufferTimeout |
| onBackpressureBuffer không giới hạn | Queue tăng theo producer khi consumer chậm | Buffer hữu hạn + overflow policy |
| Dùng drop cho event cần bảo toàn | Mất command/audit/business event | Durable queue hoặc fail-fast |
| Pool có max lớn hơn upstream capacity | Đẩy overload sang upstream | Sizing theo SLA và load test |
| Pending queue không giới hạn | Request chờ tích lũy, latency và memory tăng | pendingAcquireMaxCount hữu hạn |
| pendingAcquireTimeout quá dài | Request chờ khi deadline đã hết | Align với deadline nghiệp vụ |
| Tạo ConnectionProvider mỗi request | Mất reuse, tăng socket/TLS churn | Provider singleton theo downstream |
| maxIdleTime lớn hơn server timeout | Dễ reuse stale connection | Đặt bằng hoặc thấp hơn peer idle timeout |
| Bỏ qua HTTP/2 multiplexing | Sizing connection sai | Quan sát active streams |
| Dùng flatMapSequential cho mọi flow | Head-of-line queue và latency | Chỉ dùng khi cần output order |
| Chỉ nhìn throughput trung bình | Bỏ qua p99 và burst | Đo latency percentile và error rate |
| Tăng nhiều tham số cùng lúc | Không biết nguyên nhân cải thiện/xấu đi | Thay từng biến một |

## 19. Checklist trước khi đưa tuning vào production

- [ ] Biết source có hỗ trợ Reactive Streams backpressure hay là hot/callback source.
- [ ] Biết operator nào tạo queue và capacity của nó.
- [ ] Chọn flatMap concurrency theo downstream capacity.
- [ ] Chọn prefetch theo số item và kích thước payload.
- [ ] Phân biệt prefetch của inner publisher với prefetch của publishOn.
- [ ] Dùng limitRate khi cần chia demand thành batch.
- [ ] Chỉ buffer khi có batch/queue policy rõ ràng.
- [ ] Mọi queue có thể tăng theo tải đều có giới hạn hoặc durable storage.
- [ ] Có overflow policy phù hợp với semantics nghiệp vụ.
- [ ] Biết HTTP protocol là HTTP/1.1 hay HTTP/2.
- [ ] Có ConnectionProvider dùng chung theo downstream host/service.
- [ ] Đặt maxConnections theo concurrency và upstream capacity.
- [ ] Giới hạn pendingAcquireMaxCount.
- [ ] Đặt pendingAcquireTimeout theo deadline request.
- [ ] maxIdleTime phù hợp timeout của server/proxy.
- [ ] Bật metrics và theo dõi active/idle/pending connections.
- [ ] Theo dõi p95/p99, errors, CPU, heap và direct memory.
- [ ] Load test steady, burst, slow downstream và recovery.
- [ ] Không block event loop hoặc tự subscribe trong WebFlux handler.
- [ ] Không tăng pool chỉ để che upstream latency hoặc lỗi capacity.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Prefetch là gì?

Lượng demand operator yêu cầu trước từ upstream hoặc số item có thể được giữ sẵn trong queue nội bộ của operator.

**Câu 2.** Prefetch có phải số thread không?

Không. Thread/Scheduler là execution resource; prefetch là demand/queue capacity.

**Câu 3.** flatMap concurrency khác prefetch thế nào?

Concurrency giới hạn số inner Publisher đang chạy; prefetch giới hạn lượng item được yêu cầu trước từ mỗi inner Publisher.

**Câu 4.** publishOn prefetch kiểm soát gì?

Capacity/demand tại asynchronous boundary nơi tín hiệu được chuyển sang Scheduler.

**Câu 5.** limitRate(32) có nghĩa 32 item/giây không?

Không. Nó chia upstream demand thành các đợt tối đa 32 item.

**Câu 6.** buffer(10) có thể thay đổi request thế nào?

Nếu downstream yêu cầu hai batch, buffer có thể yêu cầu 20 item từ upstream để tạo đủ hai batch.

**Câu 7.** Vì sao buffer vô hạn nguy hiểm?

Producer có thể phát nhanh hơn consumer trong thời gian dài, khiến queue giữ quá nhiều object/payload và làm cạn memory.

**Câu 8.** ConnectionProvider.maxConnections giới hạn gì?

Số connection active tối đa trong một pool tới remote host.

**Câu 9.** pendingAcquireMaxCount là gì?

Giới hạn số request đang chờ acquire connection khi pool đã đạt maxConnections.

**Câu 10.** pendingAcquireTimeout khác responseTimeout thế nào?

Acquire timeout giới hạn thời gian chờ connection từ pool; responseTimeout của Reactor Netty kiểm soát khoảng im lặng khi đọc response theo semantics của connector.

**Câu 11.** Vì sao không nên tạo ConnectionProvider mỗi request?

Mất lợi ích tái sử dụng connection và tạo quá nhiều pool/socket, làm tăng resource churn.

**Câu 12.** HTTP/2 có một request cho mỗi connection không?

Không. HTTP/2 multiplex nhiều stream trên một connection; phải quan sát stream capacity/metrics.

**Câu 13.** Dùng Little's Law để làm gì?

Ước lượng concurrency trung bình từ throughput và thời gian request chiếm tài nguyên.

**Câu 14.** Nếu pending connection tăng nhưng active luôn ở max, nên kiểm tra gì?

Latency upstream, maxConnections, flatMap concurrency, acquire timeout và khả năng chịu tải của remote service.

**Câu 15.** Khi nào dùng drop/latest?

Khi nghiệp vụ cho phép loại item cũ hoặc item mới; không dùng cho sự kiện cần bảo toàn nếu chưa có persistence/replay.

## 21. Tài liệu tham khảo chính thức

- [Project Reactor — On Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): Reactive Streams demand, prefetch, buffer và limitRate.
- [Project Reactor — Flux JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): flatMap, concatMap, flatMapSequential, publishOn, buffer và limitRate.
- [Project Reactor — Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): publishOn/subscribeOn và execution context.
- [Reactor Netty — HTTP Client Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#connection-pool): maxConnections, pendingAcquireMaxCount, idle/lifetime và leasing.
- [Reactor Netty — HTTP Client Metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html#_metrics): pool metrics, pending acquisition, active/idle connections và HTTP client latency.
- [Reactor Netty — Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration): pending acquire, connect, response và timeout theo phase.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client và connector integration.
- [Spring Boot — WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html): cấu hình WebClient và builder trong Spring Boot.

**Ghi nhớ:** Prefetch kiểm soát demand/queue của operator; buffer gom hoặc giữ item; connection pool giới hạn connection tới remote host. Điều chỉnh concurrency và prefetch theo kích thước dữ liệu, queue theo memory budget, pool theo throughput × thời gian giữ connection và năng lực upstream. Giới hạn pending acquire, quan sát active/idle/pending metrics và load test p95/p99 trước khi thay đổi cấu hình production.