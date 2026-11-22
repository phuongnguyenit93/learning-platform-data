# API đồng bộ, bất đồng bộ hoặc phản ứng (reactive) theo khả năng driver

## 1. Một truy vấn NoSQL có ba cách viết Java — nhưng không có ba database khác nhau

Một ứng dụng Java cần đọc hồ sơ khách hàng theo khóa:

~~~text
GET /customers/cus-42
       |
       v
Java application
       |
       v
NoSQL database (MongoDB / Cassandra / DynamoDB / Redis)
~~~

Cùng một yêu cầu nghiệp vụ có thể được triển khai theo các kiểu API:

~~~java
// Dạng đồng bộ - ví dụ minh họa:
Customer customer = repository.findById("cus-42");

// Dạng bất đồng bộ - ví dụ minh họa:
CompletionStage<Customer> future =
    repository.findByIdAsync("cus-42");

// Dạng reactive - ví dụ minh họa:
Mono<Customer> publisher =
    repository.findByIdReactive("cus-42");
~~~

Ba chữ ký này **không tự mang lại cùng tính năng driver**, và cũng **không tự khác nhau về consistency của dữ liệu**. Chúng thể hiện cách **chương trình Java chờ kết quả, phối hợp công việc, quản lý tài nguyên, xử lý lỗi và điều tiết luồng dữ liệu**. Consistency, transaction, durability và điều kiện query còn phụ thuộc NoSQL engine, API cụ thể và cấu hình yêu cầu.

Đây là chủ đề **“API đồng bộ, bất đồng bộ hoặc phản ứng (reactive) theo khả năng driver”** thuộc chương **“Kết nối Java”** của module **Database No SQL**.

### Sau bài này, bạn sẽ làm được gì?

1. Phân biệt *synchronous/blocking*, *asynchronous*, *non-blocking* và *reactive* theo đúng phạm vi.
2. Đọc tài liệu driver để biết API nào thật sự được hỗ trợ, API nào chỉ là wrapper của thư viện khác.
3. Viết Java với `ResultSet`/`Document`, `CompletionStage`/`CompletableFuture` và `Publisher`/`Mono`/`Flux`.
4. Phân tích thread, connection pool, network I/O, cancellation, deadline và retry ở từng mô hình.
5. Hiểu Reactive Streams demand/backpressure và vấn đề lazy subscription.
6. Chọn cách kết nối cho request/response, streaming, batch/CDC và ứng dụng dùng virtual threads.
7. Tránh biến sync thành “giả async” bằng một executor không giới hạn.
8. Tránh gọi `block()` trong event loop và tránh xử lý chặn ngay trong callback I/O.
9. Kiểm thử dữ liệu đúng, tài nguyên không rò rỉ và khả năng phục hồi sau failover/timeout.
10. Xây quyết định kỹ thuật có số đo thay vì suy luận “reactive luôn nhanh hơn”.

---

## 2. Bốn thuật ngữ thường bị dùng lẫn

| Thuật ngữ | Điều đang mô tả | Điều **không** được suy ra |
|---|---|---|
| **Synchronous** | Lệnh gọi trả kết quả/exception trực tiếp khi hoàn thành | Mọi I/O đều được thực hiện trên đúng một OS thread |
| **Blocking** | Thread gọi không thể tiếp tục làm việc hữu ích khác trong lúc chờ | Database đã ngừng xử lý khi thread bị interrupt |
| **Asynchronous** | Kết quả đến sau qua callback/future/event | Toàn bộ đường chạy là non-blocking |
| **Non-blocking I/O** | Cơ chế chờ I/O không giữ một thread cho mỗi thao tác đợi | Tự có backpressure, retry hoặc giới hạn đồng thời |
| **Reactive** | Giao diện publisher/subscriber và các phép biến đổi stream; thường tích hợp demand, cancellation, error signals | Mọi operator/nguồn dữ liệu đều non-blocking hoặc mọi side effect an toàn khi retry |

Một API `CompletableFuture<T>` có thể được hiện thực bằng native asynchronous network I/O, **hoặc** bằng thread pool chạy lệnh đồng bộ. Cùng một chữ ký future không cho biết cách thư viện dùng thread bên trong.

Một API `Mono<T>` có thể bọc kết nối NoSQL native reactive, nhưng cũng có thể bọc code blocking qua `boundedElastic()`. Ở trường hợp thứ hai, ta đã **di chuyển chỗ blocking**, chưa biến thao tác thành non-blocking network I/O.

### 2.1. Đồng bộ theo góc nhìn caller

~~~java
Document document = collection.find(eq("_id", id)).first();

// Dòng tiếp theo chỉ chạy khi thao tác trên trả kết quả
// hoặc ném exception.
process(document);
~~~

Java gọi và đợi kết quả. Cách suy luận control flow tuyến tính, `try/catch/finally` dễ đọc, nhưng thread có thể bị giữ khi I/O chậm.

### 2.2. Bất đồng bộ theo góc nhìn caller

~~~java
CompletionStage<Document> stage = findDocumentAsync(id);

stage.thenAccept(document -> {
    process(document);
});

// Caller có thể tiếp tục xử lý việc khác.
~~~

`stage` mô tả kết quả tương lai. Caller không cần chờ ngay, nhưng việc thực thi `process` trên thread nào phụ thuộc upstream completion và cách dùng callback.

### 2.3. Reactive theo mô hình subscription

~~~java
Mono<Document> mono = findDocumentReactive(id);

Mono<String> response = mono.map(document ->
    document == null
        ? "NOT_FOUND"
        : document.getString("name")
);
~~~

Tạo pipeline chưa chắc đã gửi query. Với nhiều driver reactive và Reactor sources dạng *cold*, thao tác bắt đầu khi có **subscription**. Nhưng không được suy mọi publisher đều cold hoặc mỗi subscription đều an toàn; phải xem contract từng publisher.

---

## 3. Sơ đồ ba kiểu thực thi

~~~mermaid
flowchart TD
    A["Incoming request"] --> B{"Kiểu API được chọn"}
    B --> C["Sync / blocking call"]
    B --> D["Async Future / callback"]
    B --> E["Reactive Publisher"]
    C --> F["Thread chờ kết quả"]
    D --> G["Completion được phát sau"]
    E --> H["Subscriber yêu cầu dữ liệu bằng demand"]
    F --> I["Map DB result -> API response"]
    G --> I
    H --> I
~~~

### 3.1. Cùng câu SQL/CQL/document query không nhất thiết cùng API

Một NoSQL driver có thể cung cấp:

- Đồng bộ và bất đồng bộ, nhưng không có reactive API chính thức.
- API reactive cho cursor/stream nhưng thao tác quản trị vẫn sync.
- Publisher chuyên biệt cho paginated operations.
- Một “reactive repository” từ framework bọc driver phù hợp.
- Một API async trả `Future` nhưng không hỗ trợ cancel thật ở server.

**Đọc capability matrix của đúng phiên bản driver** trước khi xây kiến trúc.

### 3.2. Không nên quyết định chỉ từ tên framework

Chạy Spring WebFlux không tự khiến driver đồng bộ thành reactive. Ngược lại, một Spring MVC application vẫn có thể dùng API bất đồng bộ hoặc virtual threads ở những nơi phù hợp. Kiểu HTTP framework và kiểu NoSQL driver là hai quyết định có liên hệ, nhưng không đồng nhất.

---

## 4. API đồng bộ: đơn giản, hữu ích và có giới hạn

Ví dụ đồng bộ ở tầng repository:

~~~java
public Customer loadCustomer(String id) {
    Customer customer = repository.findById(id);
    if (customer == null) {
        throw new CustomerNotFoundException(id);
    }
    return customer;
}
~~~

### 4.1. Lợi ích

- Control flow tuyến tính, đọc như mã Java thông thường.
- `try/catch/finally` và transaction boundary thường dễ hiểu.
- Có thể tận dụng thư viện/sản phẩm chỉ cung cấp blocking API.
- Dễ debug từng bước trong nhiều ứng dụng nhỏ và batch sequential.
- Với Java virtual threads, blocking I/O phù hợp có thể trở nên dễ mở rộng về **thread allocation** mà không viết callback chain.

### 4.2. Đánh đổi

- Mỗi request đang chờ I/O có thể giữ một platform thread (trong mô hình thread-per-request truyền thống).
- Một số thread pools bị cạn khi database latency tăng.
- Nếu query chậm, HTTP workers và connection acquisition queues có thể tích tụ.
- `for` loop gọi từng key một có thể khiến workload tuần tự chậm.
- Bị cám dỗ tạo quá nhiều threads thay vì quản lý in-flight query count.

### 4.3. Sync không nhất thiết chậm

Với 50 requests/s, p99 DB là 10 ms, service đơn giản và pool đủ, API sync có thể đáp ứng SLO tốt với chi phí phức tạp thấp hơn.

Không đổi toàn bộ code sang reactive chỉ vì backend NoSQL có driver reactive. **Điều cần chứng minh là capacity, latency hoặc composition đang có vấn đề.**

### 4.4. Một thread được chặn không đồng nghĩa CPU bận

Thread chờ network có thể dùng ít CPU, nhưng vẫn chiếm scheduling/memory/stack và vị trí trong pool. Nếu hàng nghìn request cùng đợi, các tài nguyên quản lý thread và queue vẫn quan trọng.

---

## 5. API bất đồng bộ: kết quả là một giá trị trong tương lai

Java có `Future<T>`, `CompletionStage<T>` và `CompletableFuture<T>`:

- `Future.get()` là cách chờ **blocking**.
- `CompletionStage` mô tả chuỗi xử lý hoàn tất, kết hợp/biến đổi kết quả.
- `CompletableFuture` vừa implement `Future`, vừa là `CompletionStage`, có khả năng hoàn tất bằng code.
- Driver có thể trả `CompletionStage<T>`, `CompletableFuture<T>`, `RedisFuture<T>` hoặc loại future riêng.

Ví dụ:

~~~java
CompletionStage<Customer> customerStage =
    repository.findByIdAsync("cus-42");

CompletionStage<String> nameStage =
    customerStage.thenApply(Customer::displayName);
~~~

### 5.1. Không dùng `.get()` ngay sau mỗi async call

Sai về mục tiêu giải phóng caller:

~~~java
Customer customer = repository
    .findByIdAsync("cus-42")
    .toCompletableFuture()
    .get(); // Blocking.
~~~

Nó có thể đúng nếu cần một **blocking boundary có chủ đích**, chẳng hạn chương trình CLI hay test. Nhưng nếu dùng trong event loop/WebFlux handler, nó thường phản tác dụng.

### 5.2. `thenApply` và `thenCompose`

`thenApply` biến đổi giá trị đồng bộ:

~~~java
CompletionStage<String> name =
    findCustomerAsync(id)
        .thenApply(Customer::displayName);
~~~

`thenCompose` nối một phép xử lý **cũng trả stage**:

~~~java
CompletionStage<Order> order =
    findCustomerAsync(id)
        .thenCompose(customer ->
            findLatestOrderAsync(customer.id())
        );
~~~

Nếu dùng `thenApply` cho lời gọi trả stage, bạn tạo `CompletionStage<CompletionStage<Order>>` thay vì một stage đã flatten.

### 5.3. `thenCombine` cho hai lời gọi độc lập

~~~java
CompletionStage<CustomerView> view =
    findCustomerAsync(id)
        .thenCombine(
            findPreferencesAsync(id),
            (customer, preferences) ->
                new CustomerView(customer, preferences)
        );
~~~

Hai lời gọi có thể cùng được phát, nên latency có thể tốt hơn tuần tự; đồng thời **DB in-flight tăng**. Không phát hàng vạn stages song song không giới hạn.

### 5.4. `CompletableFuture.allOf` không tự gom result

~~~java
CompletableFuture<Void> all =
    CompletableFuture.allOf(
        customerFuture,
        preferencesFuture
    );
~~~

Nó chỉ biểu diễn kết quả hoàn tất tổng hợp; để lấy các giá trị, cần truy xuất từng future sau khi `all` hoàn tất theo thiết kế. Khi một stage lỗi, cần quy tắc rollback/cancellation/fallback, không giả định tất cả được hủy.

---

## 6. Native async khác bọc sync trong `supplyAsync`

Ví dụ bọc một lời gọi blocking:

~~~java
ExecutorService blockingPool =
    Executors.newFixedThreadPool(16);

CompletableFuture<Document> future =
    CompletableFuture.supplyAsync(
        () -> syncCollection.find(eq("_id", id)).first(),
        blockingPool
    );
~~~

API bề ngoài là bất đồng bộ với caller, nhưng **một worker vẫn bị block khi truy vấn NoSQL**.

### 6.1. Khi nào wrapper có thể dùng?

- Chỉ có blocking driver.
- Cần tích hợp vào một pipeline async khác.
- Khối lượng có giới hạn và có executor **bounded**.
- Chấp nhận chi phí thread trong capacity plan.
- Cần cô lập blocking khỏi event loop.

### 6.2. Khi nào không nên dùng như chiến lược mặc định?

- Dự kiến hàng chục nghìn requests đang chờ I/O.
- Mỗi nơi tự tạo executor.
- Executor có queue vô hạn.
- Query có thể treo lâu nhưng không có driver/socket timeout.
- Dùng common pool cho các nhiệm vụ blocking kéo dài.
- Tin rằng wrap sync bằng future làm network driver trở thành native non-blocking.

### 6.3. Nếu driver có native async

Ưu tiên đánh giá native async theo chính tài liệu/capability matrix của driver: có thể dùng event-driven I/O, quản lý pagination/cancellation và callback phù hợp, tránh một blocking thread cho mỗi I/O chờ. Nhưng **native async cũng không bảo đảm throughput vô hạn**; database vẫn có giới hạn CPU/IOPS/quorum.

---

## 7. Chú ý thread của callback và blocking trong callback

Một callback có thể chạy trên thread được dùng để hoàn tất future, bao gồm thread thuộc driver hoặc I/O event loop, tùy thư viện.

Không nên làm:

~~~java
dbFuture.thenApply(document -> {
    Thread.sleep(5_000); // Blocking trong callback.
    return heavyCalculate(document);
});
~~~

nếu không biết callback thực thi trên thread nào.

### 7.1. Dùng executor riêng cho CPU-heavy work

~~~java
ExecutorService cpuExecutor =
    Executors.newFixedThreadPool(4);

CompletionStage<Report> report =
    dbFuture.thenApplyAsync(
        document -> buildCpuIntensiveReport(document),
        cpuExecutor
    );
~~~

Chú ý:

- Executor phải có queue/admission phù hợp, không vô hạn.
- CPU-heavy khác blocking I/O; chọn pool theo workload.
- `thenApplyAsync` không đảm bảo DB query trước đó native non-blocking.
- Callback exception sẽ được truyền vào stage thất bại theo semantics của CompletableFuture.

### 7.2. `whenComplete`, `handle`, `exceptionally`

~~~java
CompletionStage<Document> observed =
    dbFuture.whenComplete((value, error) -> {
        recordLatencyAndOutcome(error);
    });

CompletionStage<Document> recovered =
    dbFuture.exceptionally(error -> {
        return safeFallbackForRead(error);
    });
~~~

`whenComplete` thường phù hợp telemetry/cleanup; `exceptionally` hoặc `handle` có thể đổi trạng thái lỗi thành fallback. **Không biến mọi write timeout thành “success”** bằng `exceptionally`.

### 7.3. Giữ context qua callback

ThreadLocal-based tracing, security context, transaction context và MDC có thể không tự truyền qua asynchronous boundaries. Nên dùng cơ chế context propagation được driver/framework hỗ trợ và kiểm tra bằng test, tránh `ThreadLocal` như nguồn duy nhất của tenant authorization.

---

## 8. Reactive Streams: có nhiều giá trị và điều tiết nhu cầu

Reactive Streams dùng mô hình:

~~~text
Publisher<T>
     |
     | subscribe
     v
Subscriber<T>
     |
     | request(n)
     v
onNext(T)... onComplete() / onError(Throwable)
~~~

Một số API Java dùng `org.reactivestreams.Publisher<T>`; Java 9 còn có `java.util.concurrent.Flow.Publisher<T>`. Hai interface thuộc **không gian tên khác nhau**, không nên giả định có thể gán trực tiếp cho nhau mà không dùng adapter thích hợp.

### 8.1. Bốn giao diện chính

- `Publisher<T>`: nguồn phát dữ liệu theo protocol.
- `Subscriber<T>`: phía nhận.
- `Subscription`: cho subscriber yêu cầu `request(n)` và `cancel()`.
- `Processor<T,R>`: vừa nhận vừa phát, trong những thiết kế cần.

### 8.2. Demand là gì?

Nếu subscriber yêu cầu 10 phần tử, một publisher tuân thủ Reactive Streams không nên phát quá demand chưa được cấp theo protocol.

~~~text
Subscriber: request(2)
Publisher:  onNext(row-1)
Publisher:  onNext(row-2)

Subscriber: request(1)
Publisher:  onNext(row-3)
~~~

**Backpressure là giao thức điều tiết phát phần tử**, không có nghĩa database hoặc network luôn ngừng mọi công việc ngay khi subscriber chưa request tiếp.

### 8.3. Mono và Flux

Trong Project Reactor:

- `Mono<T>` biểu diễn 0 hoặc 1 kết quả.
- `Flux<T>` biểu diễn 0 đến nhiều kết quả.

Ví dụ:

~~~java
Mono<Customer> one = findCustomerReactive(id);
Flux<Order> many = findOrdersReactive(customerId);
~~~

`Mono`/`Flux` là abstractions của Reactor, **không phải kiểu bắt buộc của mọi reactive NoSQL driver**.

### 8.4. Dòng lỗi là terminal signal

Một stream có thể kết thúc bởi `onComplete` hoặc `onError`. Không mặc định nó tiếp tục nhận event sau `onError`. Nếu cần retry/resubscribe, phải kiểm tra source là cold/hot, idempotency và effect của một subscription mới.

---

## 9. Cold Publisher, Hot Publisher và bẫy subscribe hai lần

Nhiều query publishers là *cold*: mô tả công việc, và mỗi lần subscribe có thể **thực hiện lại truy vấn**.

~~~java
Mono<InsertOneResult> insert =
    Mono.from(reactiveCollection.insertOne(document));

// Với một cold publisher từ driver, mỗi subscription
// có thể kích hoạt lại operation.
insert.subscribe();
insert.subscribe();
~~~

Nếu database operation là insert/create, hai subscription có thể gửi **hai attempts**. Có thể bị duplicate key hoặc side effect trùng, tùy ID và retry contract.

### 9.1. Không dùng `subscribe()` tùy tiện trong service

Sai trong một WebFlux handler:

~~~java
public Mono<Void> handle(Command command) {
    repository.save(command).subscribe();
    return Mono.empty();
}
~~~

Handler trả thành công trước khi save hoàn tất; lỗi save nằm ngoài response pipeline, cancellation/context cũng mất.

Đúng về hướng kiến trúc:

~~~java
public Mono<Void> handle(Command command) {
    return repository.save(command).then();
}
~~~

Framework/subscriber ở boundary sẽ subscribe đúng pipeline.

### 9.2. `cache()` không phải giải pháp tổng quát cho mọi write

Reactor `cache()` có thể chia sẻ tín hiệu đã phát giữa subscriptions theo semantics của nó, nhưng không thay thế idempotency ở database. Cache có lifecycle/memory/TTL riêng và không bảo vệ process crash hoặc retry từ client khác.

### 9.3. Cold và Hot cần xem nguồn

Change stream/pubsub có thể hành xử khác query publisher. Một nguồn hot có thể phát khi subscriber không theo kịp và cần buffer/drop/replay policy. Không áp cùng giả định cho MongoDB `find`, Redis Pub/Sub và Kafka consumer.

---

## 10. Backpressure không tự giải quyết mọi overload

Giả sử một reactive query phát 100.000 rows. Subscriber chỉ xử lý được 100 rows/s.

Khi backpressure được tôn trọng, publisher có thể giảm lượng phát xuống downstream. Nhưng hệ vẫn có các giới hạn:

- DB server có thể đã chạy một phần query.
- Cursor và connection có thể được giữ.
- Prefetch/batch nội bộ vẫn có buffer.
- Một số push sources không thể ngừng phát.
- Toán tử `publishOn`, `flatMap`, `buffer` có các queue/prefetch riêng.
- Một subscriber chậm có thể giữ transaction/cursor quá lâu.
- Cancellation có thể đến trễ hoặc không đảo tác động đã commit.

### 10.1. `flatMap` cần concurrency có giới hạn

Sai theo mục tiêu capacity:

~~~java
Flux.fromIterable(ids)
    .flatMap(id -> repository.findByIdReactive(id));
~~~

Nếu một upstream lớn kết hợp với chính sách concurrency/prefetch không kiểm soát, nó có thể phát nhiều calls cùng lúc hơn năng lực DB. Dạng điều tiết rõ:

~~~java
Flux.fromIterable(ids)
    .flatMap(
        id -> repository.findByIdReactive(id),
        16 // max concurrent inner publishers
    );
~~~

Đây là **một giới hạn cục bộ trong pipeline**; còn phải xét có bao nhiêu pipeline chạy đồng thời, driver pool và limit toàn cluster.

### 10.2. `concatMap` cho xử lý tuần tự

~~~java
Flux.fromIterable(commands)
    .concatMap(repository::applyReactive);
~~~

Nó có thể hữu ích khi thao tác cần thứ tự trong **một stream**. Nhưng không tạo một global serialization guarantee cho nhiều JVM instances hoặc nhiều partition consumers.

### 10.3. `collectList()` có thể phá lợi ích streaming

~~~java
Mono<List<Order>> all =
    repository.findAllReactive().collectList();
~~~

Câu này gom toàn bộ stream vào memory. Với 10 triệu orders, nó có thể dẫn đến memory pressure/OOM. Dùng paging, bounded batching, streaming processing hoặc aggregation phía DB tùy yêu cầu.

### 10.4. `onBackpressureBuffer()` không có nghĩa an toàn

Nếu buffer không được giới hạn và producer nhanh hơn consumer, memory vẫn tăng. Cần chọn capacity và overflow strategy theo nghiệp vụ. Drop event chỉ được phép khi contract cho phép mất dữ liệu.

---

## 11. Cách nhận biết driver hỗ trợ những mô hình nào

Đừng chọn thư viện bằng việc đoán từ tên artifact hoặc một blog cũ. Kiểm tra:

1. **Official client/driver family** và phiên bản được support.
2. **Sync API** cho point read/write/transaction/bulk.
3. **Async API** cho single operations, pagination, stream, transactions.
4. **Reactive API** chính thức hay adapter của Spring/Reactor.
5. **Return types**: `T`, `CompletionStage<T>`, `Publisher<T>`, `Mono<T>`, `Flux<T>`.
6. **I/O model**: native event-driven hay blocking offload.
7. **Resource lifecycle**: client/session/connection/publisher/cursor.
8. **Thread safety** của client, session và connection.
9. **Cancellation semantics**: hủy local subscription hay gửi server cancellation.
10. **Retry and idempotency policy**: driver tự retry gì, được cấu hình thế nào.
11. **Transaction and consistency support** ở từng API.
12. **Pagination semantics**: chỉ một page hay tự tiếp tục sang các pages.
13. **Backpressure semantics** ở `Publisher`.
14. **Tracing/context/security integration**.
15. **Compatibility** với JDK, Spring version và event-loop runtime.

### 11.1. Bảng tham chiếu về hình thức API

| Hệ NoSQL / thư viện Java | Sync | Async | Reactive / Publisher | Lưu ý |
|---|---|---|---|---|
| MongoDB Java driver | Sync client API | Tùy driver family/API được chọn; không giả định sync client tự có async | MongoDB Reactive Streams Java driver | Sync và reactive có types/client riêng |
| Apache Cassandra Java Driver 4.x | `CqlSession.execute` | `executeAsync` → `CompletionStage` | `executeReactive` → Reactive Streams publisher | Paging và backpressure cần đọc API |
| AWS SDK for Java v2 – DynamoDB | `DynamoDbClient` | `DynamoDbAsyncClient` → future | Paginators/SDK publishers; có enhanced async API | Publisher trên một số đường pagination, không phải mọi operation trả Flux |
| Redis Lettuce | `sync()` | `async()` → `RedisFuture` | `reactive()` với Reactor types | Một connection/client có nhiều command interfaces |
| Redis Jedis | Chủ yếu API sync trong nhiều usage phổ biến | Kiểm tra phiên bản/tính năng cụ thể | Không mặc định API reactive chính thức giống Lettuce | Không trộn capability hai thư viện |
| Elasticsearch Java API Client | `ElasticsearchClient` | `ElasticsearchAsyncClient` | Có thể tích hợp adapter/framework khác | Kiểm tra phiên bản, bulk streaming và transport |
| Spring Data NoSQL | Blocking repository/template tùy module | Có thể bridge/async tùy module | `ReactiveMongoRepository`, reactive templates ở những module hỗ trợ | Framework API không thay driver capability |

Đây là **bảng định hướng khái niệm**, không phải kiểm kê hoàn chỉnh của mọi phiên bản. Khi chọn thư viện cho dự án, xem tài liệu chính thức đúng phiên bản vì packages, artifact names và supported features có thể thay đổi.

---

## 12. MongoDB Java: sync client

Với MongoDB Java synchronous driver, code kiểu:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;

public final class SyncMongoExample {

    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> customers =
                client.getDatabase("shop")
                    .getCollection("customers");

            Document customer = customers
                .find(eq("_id", "cus-42"))
                .first();

            System.out.println(customer);
        }
    }
}
~~~

### 12.1. Tính chất

- `find(...)` xây query iterable theo API sync.
- `.first()` thực hiện fetch để lấy document đầu và có thể chờ I/O.
- API trả `Document` hoặc `null`.
- Driver xử lý pool/topology nội bộ theo config.
- Không nên tạo `MongoClient` mới cho mỗi HTTP request.

### 12.2. Resource ownership

`MongoClient` thường được chia sẻ theo lifecycle của ứng dụng và đóng lúc shutdown. Nếu đóng client sau từng request, bạn tự phá connection pooling, tăng overhead và gây nghẽn.

### 12.3. Cursor và query lớn

~~~java
try (var cursor = customers.find(eq("tenantId", tenantId))
        .batchSize(200)
        .iterator()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
~~~

Lặp theo cursor giúp không phải gom tất cả documents vào một list. Tuy nhiên cursor vẫn có server-side resource, network batches và timeouts; cần đóng đúng cách và giới hạn phạm vi query.

---

## 13. MongoDB Java Reactive Streams: Publisher và Reactor adapter

MongoDB có driver reactive dùng các types khác sync client:

~~~java
import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import com.mongodb.reactivestreams.client.MongoCollection;
import org.bson.Document;
import reactor.core.publisher.Mono;

import static com.mongodb.client.model.Filters.eq;

public final class ReactiveMongoExample {

    private final MongoClient client;
    private final MongoCollection<Document> customers;

    public ReactiveMongoExample(String uri) {
        client = MongoClients.create(uri);
        customers = client.getDatabase("shop")
            .getCollection("customers");
    }

    public Mono<Document> findCustomer(String id) {
        return Mono.from(
            customers.find(eq("_id", id)).first()
        );
    }

    public void shutdown() {
        client.close();
    }
}
~~~

### 13.1. Những gì `Mono.from(...)` làm

Nó adapter một `org.reactivestreams.Publisher` sang Reactor `Mono`, phù hợp cho nguồn 0/1 phần tử. Nó **không tự thay query semantics** hoặc biến write thành transaction.

### 13.2. Nhiều documents

~~~java
Flux<Document> findByTenant(
        MongoCollection<Document> collection,
        String tenantId) {

    return Flux.from(
        collection.find(eq("tenantId", tenantId))
            .batchSize(100)
    );
}
~~~

Giới hạn batch/query và deadline vẫn cần. `batchSize(100)` không phải giới hạn **tổng số kết quả**, chỉ ảnh hưởng batch fetch theo driver/server semantics.

### 13.3. Không tạo MongoClient trong `Mono.defer` cho từng request

Nếu mỗi subscription mở một client mới mà không quản lý cleanup, connection/resource leak sẽ xảy ra. Dùng lifecycle phù hợp (dependency injection, application singleton hoặc managed bean) rồi đóng khi ứng dụng kết thúc.

### 13.4. Ghi reactive

~~~java
Mono<?> write =
    Mono.from(
        customers.insertOne(
            new Document("_id", "cus-42")
                .append("name", "An")
        )
    );
~~~

Nếu pipeline được subscribed lại, thao tác có thể được thực thi lại; dùng `_id` ổn định và business idempotency theo contract. Không cho rằng `Mono` biến `insertOne` thành exactly-once.

### 13.5. Spring Data MongoDB

Trong ứng dụng dùng Spring Data Reactive MongoDB, có thể dùng `ReactiveMongoTemplate` hoặc repository trả `Mono`/`Flux`. Đây là API tầng framework, cần driver reactive phù hợp và configuration riêng. Không inject `MongoTemplate` đồng bộ rồi gọi `.block()`/`.subscribeOn()` tùy tiện để tuyên bố toàn bộ pipeline đã reactive.

---

## 14. Cassandra Java Driver: sync, async và reactive trong cùng family

Trong Apache Cassandra Java Driver 4.x, `CqlSession` cung cấp các đường execution khác nhau.

### 14.1. Đồng bộ

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class CassandraSync {

    public static Row readById(
            CqlSession session,
            PreparedStatement query,
            String id) {

        ResultSet rows =
            session.execute(query.bind(id));

        return rows.one();
    }
}
~~~

`CqlSession` thường được dùng lại theo lifecycle của ứng dụng; prepared query/execute cần có cấu hình keyspace, datacenter, connection và permissions phù hợp.

### 14.2. Bất đồng bộ

~~~java
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public CompletionStage<Row> readOneAsync(
        CqlSession session,
        PreparedStatement query,
        String id) {

    return session.executeAsync(query.bind(id))
        .thenApply(AsyncResultSet::one);
}
~~~

`AsyncResultSet` là cấu trúc phân trang: `currentPage()` cho page hiện tại, và `fetchNextPage()` cho page tiếp theo khi có. **Đừng nhầm `executeAsync()` với “đã tải mọi rows của query”.**

### 14.3. Reactive

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ReactiveRow;
import reactor.core.publisher.Flux;

public Flux<ReactiveRow> readReactive(
        CqlSession session,
        PreparedStatement query,
        String id) {

    return Flux.from(
        session.executeReactive(query.bind(id))
    );
}
~~~

Đường reactive có thể tự quản demand/paging theo API. Tuy nhiên tên type và behavior phải đối chiếu đúng version driver; ví dụ nhằm cho thấy phân biệt `ResultSet`, `CompletionStage<AsyncResultSet>` và Publisher.

### 14.4. Không lẫn lộn paging

Với async:

~~~java
CompletionStage<AsyncResultSet> first =
    session.executeAsync(query.bind(id));

CompletionStage<AsyncResultSet> second =
    first.thenCompose(page ->
        page.hasMorePages()
            ? page.fetchNextPage()
            : CompletableFuture.completedFuture(page)
    );
~~~

Đây chỉ lấy **page kế tiếp nếu có**, không tự gom toàn bộ dataset. Cần quy trình lặp/batching/cancellation có giới hạn nếu muốn nhiều pages.

### 14.5. Consistency level không thay theo kiểu API

Một `LOCAL_QUORUM` request qua sync và cùng request qua async/reactive có thể có consistency contract tương ứng nếu statement options giống nhau. Reactive không khiến eventual reads trở thành strong reads, cũng không tự làm LWT/conditional update nhanh hơn.

### 14.6. Driver callback và request class

Nếu dùng hàng trăm kết nối đồng thời tới một partition hot, các kiểu API đều có thể overload cùng Cassandra replicas. Hãy đặt limit theo keyspace/table/statement class và xem driver throttling, speculative execution, retry policy.

---

## 15. DynamoDB với AWS SDK for Java v2: sync client

DynamoDB synchronous client:

~~~java
import java.util.Map;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.GetItemResponse;

public final class DynamoSync {

    public static void main(String[] args) {
        try (DynamoDbClient client = DynamoDbClient
                .builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            GetItemRequest request = GetItemRequest.builder()
                .tableName("Customers")
                .key(Map.of(
                    "customerId",
                    AttributeValue.builder()
                        .s("cus-42")
                        .build()
                ))
                .build();

            GetItemResponse response =
                client.getItem(request);

            System.out.println(response.item());
        }
    }
}
~~~

Cấu hình region/credentials/endpoints trong ví dụ là minh họa, không phải giá trị hardcode cần sao chép cho production. Credentials nên được cung cấp qua provider chain và quyền tối thiểu.

---

## 16. DynamoDB async client: CompletableFuture

AWS SDK for Java v2 có `DynamoDbAsyncClient` cho nhiều thao tác bất đồng bộ:

~~~java
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbAsyncClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.GetItemResponse;

public final class DynamoAsync {

    public static CompletableFuture<GetItemResponse> read(
            DynamoDbAsyncClient client,
            String customerId) {

        GetItemRequest request = GetItemRequest.builder()
            .tableName("Customers")
            .key(Map.of(
                "customerId",
                AttributeValue.builder()
                    .s(customerId)
                    .build()
            ))
            .build();

        return client.getItem(request);
    }

    public static void main(String[] args) {
        try (DynamoDbAsyncClient client =
                DynamoDbAsyncClient.builder()
                    .region(Region.AP_SOUTHEAST_1)
                    .build()) {

            read(client, "cus-42")
                .thenAccept(result ->
                    System.out.println(result.item())
                )
                .join(); // Chỉ ở ranh giới CLI để đợi kết quả.
        }
    }
}
~~~

### 16.1. `join()` ở CLI khác `join()` trong event loop

Ở `main`, đợi future xong trước khi đóng client có chủ đích. Trong WebFlux/Netty event loop, `.join()` sẽ chặn đường phục vụ request và có thể gây nghẽn.

### 16.2. Async paginator và Publisher

Với các operations phân trang được SDK hỗ trợ, `queryPaginator(...)` có thể cung cấp `SdkPublisher<QueryResponse>`. Publisher đó có thể được tích hợp bằng Reactive Streams:

~~~java
import reactor.core.publisher.Flux;
import software.amazon.awssdk.services.dynamodb.DynamoDbAsyncClient;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

public Flux<QueryResponse> queryPages(
        DynamoDbAsyncClient client,
        QueryRequest request) {

    return Flux.from(
        client.queryPaginator(request)
    );
}
~~~

Không nhầm **publisher của nhiều pages** với `CompletableFuture<QueryResponse>` trả **một page**. Một page có thể chứa nhiều items; query có thể cần rất nhiều pages.

### 16.3. DynamoDB Enhanced Async Client

AWS SDK v2 có enhanced async APIs giúp ánh xạ table/item và truy vấn phân trang. Nhưng việc một API trả publisher **không có nghĩa mọi phương thức DynamoDB đều trả Flux/Mono**, hoặc tất cả transactions, queries, conditionals đều có semantics giống nhau.

### 16.4. Retry và throttling

DynamoDB có throttling, capacity units và các giới hạn theo partition/index. SDK có thể tự retry trong phạm vi policy; app phải tính cả retries của SDK khi đặt retry budget. Đổi sync sang async không làm tăng capacity của partition hot.

---

## 17. Redis Lettuce: một thư viện, ba dạng commands

Lettuce là ví dụ rõ cho ba command interfaces:

~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisFuture;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import io.lettuce.core.api.async.RedisAsyncCommands;
import io.lettuce.core.api.reactive.RedisReactiveCommands;
import reactor.core.publisher.Mono;

public final class LettuceModes {

    public static void main(String[] args) {
        RedisClient client =
            RedisClient.create("redis://localhost:6379");

        try (StatefulRedisConnection<String, String> connection =
                client.connect()) {

            RedisCommands<String, String> sync =
                connection.sync();

            RedisAsyncCommands<String, String> async =
                connection.async();

            RedisReactiveCommands<String, String> reactive =
                connection.reactive();

            String immediate =
                sync.get("customer:42");

            RedisFuture<String> future =
                async.get("customer:42");

            Mono<String> publisher =
                reactive.get("customer:42");

            // Chỉ minh họa các return types.
            // Không block()/join() trong HTTP event loop.
            System.out.println(immediate);
            System.out.println(future.isDone());
            System.out.println(publisher);
        } finally {
            client.shutdown();
        }
    }
}
~~~

### 17.1. Async command trả `RedisFuture`

Lettuce `RedisFuture` có thể tích hợp với `CompletionStage` theo API của thư viện. Nó không giống một Redis Stream feed; đây là completion của **một command**.

### 17.2. Reactive command là pipeline theo subscription

`reactive.get(key)` trả Reactor-compatible publisher. Nên kết hợp trong pipeline và để framework subscribe, không gọi `block()` trong reactive handler.

### 17.3. Connection thread-safety và blocking

Một số Lettuce connection interfaces được thiết kế cho concurrent usage, nhưng vẫn phải đọc hướng dẫn về thread safety, blocking commands, transactions và pub/sub. **Một connection được share không đồng nghĩa mọi command/pipeline đều nên share cùng connection trong mọi tình huống.**

### 17.4. Redis là điểm nghẽn server-side

Một Lua script chặn lâu hoặc hot key vẫn gây chậm dù caller sync/async/reactive. Đừng khắc phục server-side contention bằng cách cho thêm 10.000 in-flight commands.

---

## 18. Một API REST dùng Spring MVC với driver đồng bộ

Đường request/response truyền thống:

~~~java
@RestController
@RequestMapping("/customers")
public final class CustomerController {

    private final CustomerRepositorySync repository;

    public CustomerController(
            CustomerRepositorySync repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public ResponseEntity<Customer> find(
            @PathVariable String id) {

        Customer customer = repository.findById(id);

        if (customer == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(customer);
    }
}
~~~

Những types `Customer`/`CustomerRepositorySync` là ví dụ trừu tượng; imports Spring MVC được lược bỏ để tập trung vào kiểu API.

### 18.1. Vì sao cách này vẫn hợp lý?

Với service vừa phải, team quen Spring MVC, consistency/transaction requirements rõ và driver sync ổn định, code dễ kiểm thử và vận hành.

### 18.2. Giới hạn vẫn cần

- HTTP executor threads hoặc virtual-thread mode.
- Connection pool.
- Max in-flight DB calls.
- Query timeout/deadline.
- Queue có giới hạn.
- Retry/idempotency.
- Không chạy full-table scan trong request latency-sensitive.

### 18.3. Một request không phải luôn một query

`findById()` có thể kéo theo lookup thứ hai, cache miss hoặc nhiều read models. Cần đo số DB calls thực tế, không chỉ số HTTP requests.

---

## 19. Spring WebFlux với reactive repository

Một controller phù hợp khi repository thực sự có reactive API:

~~~java
@RestController
@RequestMapping("/customers")
public final class ReactiveCustomerController {

    private final CustomerRepositoryReactive repository;

    public ReactiveCustomerController(
            CustomerRepositoryReactive repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Customer>> find(
            @PathVariable String id) {

        return repository.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(
                ResponseEntity.notFound().build()
            );
    }
}
~~~

### 19.1. Không gọi `subscribe()` trong handler

WebFlux tự subscribe ở boundary phù hợp. Một service cần trả `Mono` hoặc `Flux` cho caller phối hợp, xử lý error và cancellation.

### 19.2. Không gọi `block()` để biến lại thành sync

Sai:

~~~java
@GetMapping("/{id}")
public Customer find(@PathVariable String id) {
    return repository.findById(id).block();
}
~~~

Trong event-loop model, `.block()` có thể gây runtime error hoặc nghẽn throughput. Nếu code phải blocking, chọn kiến trúc boundary phù hợp hoặc tách nó vào scheduler giới hạn.

### 19.3. Không tự chuyển transactional context bằng ThreadLocal

Reactive transaction context thường đi theo reactive context/protocol, không nhất thiết là ThreadLocal của blocking transaction manager. Nếu dùng Spring reactive transactions, cần `ReactiveTransactionManager`, `TransactionalOperator` hoặc annotation semantics đúng module và version.

### 19.4. `Flux` không tự đảm bảo stream tới browser hoàn chỉnh

HTTP response có thể buffer/serialize; network backpressure và content type ảnh hưởng. Nếu muốn streaming responses, dùng content type và serialization hợp lý, tránh collect toàn bộ kết quả trước khi gửi.

---

## 20. Chỉ có sync driver nhưng app chạy WebFlux thì sao?

Một cách tạm thời là tách blocking work sang bounded scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<Customer> findCustomer(String id) {
    return Mono.fromCallable(
            () -> blockingRepository.findById(id)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

### 20.1. Ý nghĩa chính xác

- Reactor sắp xếp thực thi callable trên scheduler dành cho blocking work có giới hạn phù hợp theo cấu hình.
- Thread thực thi vẫn chờ blocking DB call.
- Không biến blocking JDBC/NoSQL driver thành native non-blocking.
- Số operations đang chạy và hàng đợi scheduler vẫn cần được quản lý.
- Transaction context và thread affinity phải được đánh giá riêng.

### 20.2. Khi nào nên dùng?

Khi cần kết nối một thư viện blocking vào pipeline reactive ở một ranh giới nhỏ, với concurrency có thể dự đoán và budget rõ.

### 20.3. Khi nào nên đổi driver?

Nếu phần lớn request đều dùng database, concurrency lớn và mục tiêu non-blocking là yêu cầu kiến trúc, việc dùng native reactive driver có thể phù hợp hơn. Cần benchmark tổng workload và xem driver feature parity trước khi migrate.

### 20.4. Không offload CPU-heavy vào boundedElastic chỉ vì tiện

CPU-bound workload có thể cần scheduler riêng với số threads theo CPU. Blocking I/O và CPU-bound cần lựa chọn tài nguyên khác nhau.

---

## 21. Java virtual threads: vẫn sync nhưng không cần một platform thread cho mỗi request

Java 21 cung cấp virtual threads. Code blocking quen thuộc có thể chạy trên virtual threads:

~~~java
import java.util.concurrent.Executors;

public final class VirtualThreadDemo {

    public static void main(String[] args) throws Exception {
        try (var executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            var future = executor.submit(
                () -> blockingRepositoryCall("cus-42")
            );

            System.out.println(future.get());
        }
    }

    static String blockingRepositoryCall(String id) {
        // Sử dụng một sync NoSQL driver thực tế ở đây.
        return "customer:" + id;
    }
}
~~~

### 21.1. Điều gì cải thiện?

Khi chờ I/O tương thích với virtual threads, scheduler có thể tách virtual thread khỏi carrier platform thread. Nó giúp giảm nhu cầu platform threads cho lượng lớn tác vụ blocking đồng thời.

### 21.2. Điều gì không cải thiện?

- Database không có thêm disk IOPS.
- Hot partition không tự được chia.
- Driver connection pool không tự lớn hơn.
- Network quota không tự tăng.
- Query thiếu index vẫn chậm.
- Retry storm vẫn nhân tải.

### 21.3. Không dùng “một virtual thread mỗi request” làm rate limiter

Nhiều virtual threads nhẹ hơn **không có nghĩa** chúng không tốn memory hoặc tài nguyên downstream. Phải có semaphore/bulkhead và bounded admission.

### 21.4. Pinning và native/blocking operations

Một số kiểu blocking native code hoặc vùng `synchronized` ở những phiên bản JDK/driver khác nhau có thể ảnh hưởng scheduler/pinning. Hành vi thay đổi theo phiên bản JDK; cần đo Java Flight Recorder và benchmark trong JDK mục tiêu, không áp một kết luận cũ cho mọi phiên bản.

### 21.5. Chọn virtual threads hay reactive?

Nếu cần control flow tuyến tính, hệ sinh thái sync driver trưởng thành và workload chủ yếu chờ I/O, virtual threads có thể là lựa chọn đơn giản. Nếu cần xử lý stream dài, demand/backpressure và pipeline reactive đồng bộ từ HTTP đến driver, reactive API có thể phù hợp hơn. **Không có lựa chọn nào luôn thắng.**

---

## 22. Connection pool, session và transport resources

Dù dùng API nào, driver vẫn cần:

- TCP/TLS connections hoặc channels.
- Authentication/credentials.
- Server discovery/topology metadata.
- Request ID/correlation.
- Connection pooling/multiplexing.
- Buffers.
- Server-side cursor/stream resources.
- Retry/backoff/heartbeat.
- Timeouts.
- Metrics/tracing.

### 22.1. Pool size không phải concurrency ceiling chung cho mọi driver

Một kết nối có thể hỗ trợ nhiều multiplexed requests; một operation có thể dùng nhiều connections trong fan-out/quorum. Đặt pool 50 không đủ để suy hệ chỉ thực thi 50 requests.

### 22.2. Tạo client một lần theo lifecycle

Không làm:

~~~java
public Customer find(String id) {
    try (var client = createDatabaseClient()) {
        return query(client, id);
    }
}
~~~

trong mỗi HTTP request nếu driver client được thiết kế để share và kết nối lại tốn kém. Sử dụng bean/application lifecycle phù hợp, đóng ở shutdown.

### 22.3. Reactive cursor cũng là tài nguyên

Một Flux chậm có thể giữ cursor/connection lâu. Khi client ngắt kết nối, cần cancel/cleanup theo driver/framework; không suy server sẽ giải phóng tức thời ở mọi deployment.

### 22.4. Async futures cũng cần lifecycle

Không được `close()` client ngay sau khi gọi `executeAsync()` nếu operations còn đang chạy, trừ khi API quy định shutdown chờ/cho phép. Kế hoạch graceful shutdown phải tính in-flight operations và deadline.

---

## 23. Giới hạn đồng thời để tránh tự làm nghẽn database

Một sync API thường dễ thấy thread pool bị cạn. Với async/reactive, rất dễ phát quá nhiều operations vì caller trả về nhanh.

~~~text
10.000 incoming requests
   |
   +--> 10.000 futures created
   |
   +--> all try to hit same hot partition
   |
   +--> DB throttles / times out
   |
   +--> retries multiply load
~~~

### 23.1. Ba giới hạn khác nhau

| Giới hạn | Đơn vị | Mục đích |
|---|---|---|
| Rate limit | Requests/s | Điều tiết tốc độ đến |
| Concurrency limit | Số in-flight operations | Chặn saturation |
| Bounded queue | Số tasks chờ | Không biến latency thành memory blow-up |

### 23.2. Global vs per-shard

NoSQL có hot key/partition. Một limit toàn service có thể vẫn để một tenant chiếm hết permits. Có thể cần:

- Global DB permits.
- Per-tenant/per-key budgets.
- Query class bulkheads.
- Read vs write limits.
- Background vs foreground separation.

### 23.3. Reactive demand và database concurrency khác nhau

`request(1)` kiểm soát lượng dữ liệu publisher được phép phát, nhưng **không thay thế** giới hạn số query publishers được subscribe đồng thời. Dùng `flatMap(..., concurrency)`, application admission và driver throttling nếu có.

### 23.4. Queue vô hạn là bẫy chung

Nếu DB throughput không đủ, queue vô hạn chỉ giữ request quá hạn. Khi queue đầy, reject sớm có thể bảo vệ goodput; không phải mọi requests đều cần “chờ đến khi nào thành công”.

---

## 24. Timeout, deadline và cancellation

Một NoSQL request có thể có:

- HTTP deadline.
- Connection acquisition timeout.
- Socket/read/write timeout.
- Driver request timeout.
- Database server query timeout.
- Transaction timeout.
- Reactor `.timeout(...)`.
- `CompletableFuture.orTimeout(...)`.

### 24.1. Deadline phải đi từ trên xuống

~~~text
HTTP end-to-end budget: 500 ms
Authentication:           30 ms
Queue wait:               50 ms
Serialization:            10 ms
Remaining for DB + reply: 410 ms
~~~

Nếu DB driver được cấp timeout 5 giây sau khi HTTP chỉ còn 410 ms, server có thể tiếp tục tạo tải cho request đã vô ích.

### 24.2. `orTimeout` không đồng nghĩa đã hủy DB operation

~~~java
CompletableFuture<GetItemResponse> future =
    client.getItem(request);

future.orTimeout(300, TimeUnit.MILLISECONDS);
~~~

Với `CompletableFuture`, timeout có thể hoàn tất future bằng exception. **Không tự kết luận remote request đã bị hủy hoặc DB write chắc chắn không commit**. Kiểm tra SDK cancellation semantics và backend operation.

### 24.3. Reactive `.timeout` cũng không rollback write

~~~java
Mono<Void> save = repository.save(command)
    .timeout(Duration.ofMillis(300))
    .then();
~~~

Timeout/cancellation có thể ngừng quan sát pipeline. Nếu write đã tới server, outcome vẫn có thể là `UNKNOWN`.

### 24.4. Timeout ghi cần idempotency

Nếu write đã commit nhưng ACK bị mất, retry tạo ID mới có thể gây hai đơn hàng, hai lần trừ tồn kho hoặc hai lần charge. Dùng stable request ID, conditional write/transaction và authoritative outcome verification.

### 24.5. Server resource cleanup

Một số drivers hủy cursor/stream khi subscription cancel, một số operations còn tiếp tục trong server theo protocol. Cần đọc cụ thể, quan sát pending requests và thiết kế timeout đủ nhiều tầng.

---

## 25. Retry, driver retries và reactive resubscription

Retry có thể xảy ra ở:

~~~text
Gateway
  -> Application service
      -> HTTP/Reactive pipeline
          -> NoSQL driver retry
              -> Replica redirect/retry
~~~

Nếu mỗi tầng cho 3 attempts, worst-case sâu nhất có thể nhân rất lớn.

### 25.1. Retry nên có một nơi chịu trách nhiệm chính

Không để gateway, Spring Reactor `.retryWhen`, custom future loop và SDK driver đồng thời replay một non-idempotent write mà không chia tổng retry budget.

### 25.2. Retry read có điều kiện

~~~java
Mono<Document> read = repository.findByIdReactive(id)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientReadFailure)
    );
~~~

Đây là **mã minh họa** nằm trong class có `isTransientReadFailure`. Nó chưa có deadline tổng/aggregate retry budget. Cần phân loại lỗi theo driver và tránh retry validation/conflict errors.

### 25.3. Retry publisher là resubscribe

Trong nhiều trường hợp reactive `retry` thực hiện subscription lại vào nguồn. Nếu nguồn là write cold publisher, operation có thể được **gửi lại**. `retry(3)` không phải tính năng exactly-once.

### 25.4. Retry futures là tạo attempt mới

Một future đã thất bại không tự “thực thi lại” khi gọi `thenApply` hoặc `join`. Muốn retry một native async operation, cần gọi supplier của **một attempt mới** với cùng business request ID, trong deadline và retry budget.

### 25.5. Idempotent statement không đồng nghĩa không mất dữ liệu

Một `SET key = value` có thể idempotent trong phạm vi nào đó, nhưng vẫn cần hiểu timestamps, race với update khác, consistency, TTL và side effects. Không gắn nhãn idempotent chỉ dựa vào HTTP method hay câu lệnh trông giống update.

---

## 26. Một hạn mức async request bằng Java Semaphore

Một pattern đơn giản để giới hạn số `CompletionStage` operations được bắt đầu:

~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

public final class AsyncGate {

    private final Semaphore permits;

    public AsyncGate(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException(
                "maxInFlight must be positive"
            );
        }
        permits = new Semaphore(maxInFlight);
    }

    public <T> CompletionStage<T> call(
            Supplier<? extends CompletionStage<T>> operation) {

        Objects.requireNonNull(operation);

        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new IllegalStateException(
                    "DB concurrency capacity exhausted"
                )
            );
        }

        try {
            CompletionStage<T> stage =
                Objects.requireNonNull(operation.get());

            return stage.whenComplete((value, error) -> {
                permits.release();
            });
        } catch (Throwable failure) {
            permits.release();
            throw failure;
        }
    }
}
~~~

### 26.1. Phạm vi ví dụ

- Không block một thread để đợi permit.
- Từ chối khi không còn permit.
- Release permit khi stage trả về hoàn tất.
- Release khi supplier ném lỗi đồng bộ.
- Không tạo queue vô hạn bên trong gate.

### 26.2. Điều cần bổ sung production

- Kiểm soát lỗi `Error` và chính sách trả typed overload.
- Metrics/rejected/active permits.
- Global budget qua nhiều app instances.
- Per-tenant/per-key fairness.
- Deadline/timeout của underlying operation.
- Cancellation đã hoàn tất wrapper nhưng DB vẫn chạy (permit release quá sớm nếu chỉ timeout local).
- Circuit breaker và retry budget.
- Graceful shutdown.

**Chốt quan trọng:** Nếu stage bị hoàn tất sớm do timeout/cancellation mà remote operation vẫn chạy, release permit ngay có thể khiến số DB requests thực sự in-flight vượt limit. Hãy giới hạn theo lifecycle **request thực tế** nếu driver cung cấp tín hiệu phù hợp, hoặc đặt ngân sách an toàn bù cho trường hợp này.

---

## 27. Ví dụ reactive có bounded fan-out

Một ứng dụng cần đọc 1.000 hồ sơ theo IDs:

~~~java
import reactor.core.publisher.Flux;

public Flux<Customer> loadCustomers(
        Iterable<String> ids) {

    return Flux.fromIterable(ids)
        .flatMap(
            id -> reactiveRepository.findById(id),
            12
        );
}
~~~

### 27.1. Concurrency 12 là giới hạn mỗi subscription

Nếu có 100 HTTP requests cùng chạy pipeline này, tổng theoretical in-flight có thể cao hơn 12 rất nhiều. Cần budget toàn service/tenant.

### 27.2. Không dùng một giant list để bỏ pagination

Nếu client cần 100 trang, cân nhắc API paging/cursor thay vì tải mọi kết quả. Reactive streaming có thể điều tiết phần tử nhưng không khắc phục query không có index hoặc scan quá rộng.

### 27.3. Bảo toàn thứ tự

`flatMap` có thể phát kết quả theo thời gian hoàn tất, không nhất thiết theo thứ tự IDs. Nếu cần giữ input order, cân nhắc `flatMapSequential`/`concatMap` theo semantics và chi phí phù hợp.

### 27.4. Nhiều reads cùng lúc không phải transaction snapshot

Nếu các records thay đổi trong lúc đọc song song, kết quả có thể từ những thời điểm khác nhau. Muốn snapshot/transaction consistency, phải dùng cơ chế của NoSQL engine, không suy từ việc dùng `Flux` hoặc `Mono`.

---

## 28. Xử lý stream lớn: paging, buffering và giới hạn memory

Một query trả 2 triệu documents với kích thước trung bình 2 KiB có logical payload khoảng:

\[
2\,000\,000\times2\text{ KiB}
\approx3.81\text{ GiB}.
\]

Gom hết vào `List<Document>` có thể vượt heap và còn tốn object overhead.

### 28.1. Đồng bộ nhưng streaming

Dùng cursor, đọc từng batch, xử lý và đóng resource.

### 28.2. Bất đồng bộ phân trang

Dùng `AsyncResultSet.fetchNextPage()` hoặc paginator tương ứng, **giới hạn số pages/items đồng thời** và checkpoint nếu processing kéo dài.

### 28.3. Reactive stream

Dùng `Flux`/`Publisher` với demand, `limitRate`/batching khi phù hợp, xử lý từng phần. Tuy nhiên `collectList()` gom toàn bộ vẫn tạo memory pressure.

### 28.4. Một số query không nên chạy trong API interactive

Export nhiều triệu records có thể dùng async job, durable checkpoint, object storage và phân quyền. Không vì có reactive driver mà cho phép một HTTP request giữ cursor 30 phút không quản lý.

### 28.5. Backpressure xuyên nhiều hệ

Khi stream từ NoSQL sang Kafka hoặc một external API, áp lực ngược chỉ có tác dụng end-to-end nếu producer, buffer, consumer và transport có chính sách bounded thích hợp. Một sink không thể chậm vô hạn mà không làm backlog tăng đâu đó.

---

## 29. Transaction và session: kiểm tra feature parity

Một operation có transaction semantics phụ thuộc database và driver API.

### 29.1. MongoDB

Có sync `ClientSession` và reactive session/transaction APIs theo driver family. Reactive transaction phải giữ session/context qua pipeline đúng; không dùng blocking session trong một pipeline reactive rồi mong transaction tự lan.

### 29.2. Cassandra

Regular writes, batches và LWT có phạm vi/semantics khác. `executeReactive` không biến một nhóm CQL statements thành transaction ACID xuyên partitions. Consistency và transaction isolation cần được đọc riêng.

### 29.3. DynamoDB

`TransactWriteItems` có phạm vi và giới hạn theo DynamoDB contract. `DynamoDbAsyncClient.transactWriteItems(...)` trả future, nhưng việc dùng async không thay tính atomic do service cung cấp.

### 29.4. Redis

`MULTI/EXEC`, Lua scripts và các command blocks có semantics riêng. Không nên interleave transaction state sai trên shared connection chỉ vì API async/reactive cho phép gửi commands nhanh.

### 29.5. Cross-service transactions

Không một kiểu Java API nào tự tạo transaction xuyên NoSQL, broker và payment service. Khi cần consistency workflow, cân nhắc outbox, idempotency, saga/compensation và reconciliation.

---

## 30. Query consistency không phụ thuộc `Mono` hay `Future`

Một bảng phân biệt:

| Câu hỏi | Điều quyết định |
|---|---|
| Read có nhìn thấy write vừa ACK không? | Read/write consistency, session token, routing |
| Write bền qua failover không? | Durability, write concern, replication protocol |
| Conditional update có atomic không? | Database operation/transaction scope |
| Hai replica đồng bộ chậm bao lâu? | Replication/repair và workload |
| Client có nhận kết quả trực tiếp hay tương lai? | Sync/async API |
| Client có thể xin từng batch kết quả? | Cursor/publisher/paging API |
| Ứng dụng có bao nhiêu DB calls in-flight? | Admission, concurrency limits, driver pool |

**Cùng một CQL statement `LOCAL_QUORUM` gửi qua sync và async vẫn phải được đánh giá bởi Cassandra consistency contract**, không phải Java return type.

---

## 31. Cancellation và ghi đang dang dở

Giả sử:

~~~text
T0: API nhận POST /orders.
T1: Reactive pipeline gửi conditional write.
T2: NoSQL commit.
T3: HTTP client disconnect.
T4: Publisher nhận cancel hoặc timeout.
~~~

Không được suy:

~~~text
Reactive cancel => Database rolled back.
~~~

### 31.1. Cần một trạng thái UNKNOWN

Nếu client không nhận ACK và không thể xác minh, nên xem outcome là `UNKNOWN` cho tới khi tra cứu authoritative state/idempotency ledger.

### 31.2. Gửi lại cùng request ID

Nếu retry, giữ `orderId`/`idempotencyKey` ổn định. Dùng `insert-if-absent`, conditional update hoặc transaction theo DBMS để không tạo hai business effects.

### 31.3. Không phát email trong `doOnNext` trước commit evidence

Một callback `doOnNext` có thể chạy do một giá trị trung gian, trước khi workflow đầy đủ commit. External side effects cần đặt đúng ranh giới hoặc được xử lý bằng outbox/idempotency.

### 31.4. `doFinally` chỉ là lifecycle hook local

~~~java
pipeline.doFinally(signal -> recordTermination(signal));
~~~

Nó giúp cleanup/telemetry khi complete/error/cancel; không có quyền hủy remote write đã commit.

---

## 32. So sánh lỗi và exception propagation

| Tình huống | Sync | Async | Reactive |
|---|---|---|---|
| Database trả lỗi | Ném exception khi call | Stage completes exceptionally | `onError` |
| Timeout ở caller | Exception/timeout | Future timeout/error | Terminal error/cancel theo operator |
| Query không tìm thấy | Null/empty Optional theo API | Future với null/Optional | Empty publisher/Mono theo API |
| Nhiều rows | Iterator/cursor | Async pages/stages | Publisher/Flux |
| Cleanup | `try/finally`, try-with-resources | `whenComplete`/lifecycle | `doFinally`, `usingWhen` tùy resource |
| Retry | Loop/policy có kiểm soát | Supplier tạo attempts mới | Resubscribe qua retry operator |
| Cancellation | Interrupt/driver-specific | Future cancel/driver-specific | Subscription cancel/driver-specific |
| Return trực tiếp cho caller | `T` | `CompletionStage<T>` | `Publisher<T>`/`Mono<T>` |

### 32.1. `CompletionException` và `ExecutionException`

Khi dùng `.join()`/`.get()` có thể nhận wrapper exceptions. Đừng mất cause khi phân loại driver errors; retry cần nhận diện lỗi transient, conflict, validation và unknown commit outcome đúng.

### 32.2. Reactive `onErrorResume` phải phân loại lỗi

~~~java
Mono<Customer> result =
    repository.findByIdReactive(id)
        .onErrorResume(
            TemporaryReadException.class,
            error -> loadFromSafeCache(id)
        );
~~~

Chỉ fallback cho lỗi/nguồn dữ liệu được phép. Không biến authorization error thành anonymous data, hay đổi write timeout thành success giả.

### 32.3. Empty vs error

Một `Mono.empty()` có thể nghĩa không tìm thấy record; một `Mono.error()` thể hiện lỗi. Nếu consumer dùng `.defaultIfEmpty(...)` để che timeout, contract trở nên sai. Hãy phân biệt typed not-found và transport failure.

---

## 33. Monitoring đúng theo kiểu API

### 33.1. Sync

- Active request threads.
- Thread pool queue/queue wait.
- Connection acquisition wait.
- Driver request latency.
- Server read/write latency.
- Timeouts và interrupted requests.

### 33.2. Async

- In-flight stages/underlying requests.
- Completion latency.
- Callback executor queue.
- Driver event loop saturation.
- Number of futures retained.
- Cancels, timeouts, unreconciled writes.
- Exceptions not observed.

### 33.3. Reactive

- Number of active subscriptions.
- Demand/prefetch/buffer occupancy.
- Requests started vs completed.
- Cancel/error/complete rates.
- Stream lifetime.
- FlatMap concurrency.
- Event-loop blocking/slow callbacks.
- Backpressure overflow.
- Cursor/server resource age.

### 33.4. Mọi kiểu đều cần metric backend

- Queries per shard/partition.
- Network I/O, connection pool.
- Database CPU, memory, disk/IOPS.
- Replica lag/compaction.
- p95/p99 and timeout rates.
- Retries per logical request.
- Throttling/rejected capacity.
- Correctness/invariant violations.

### 33.5. Tách offered load và goodput

Một driver async có thể phát 20.000 attempts/s, nhưng chỉ 5.000 logical requests/s thực sự thành công vì retries. Đừng dùng attempted throughput để kết luận kiến trúc tốt hơn.

---

## 34. Chọn mô hình theo loại workload

| Workload | Sync | Async | Reactive | Gợi ý lựa chọn |
|---|---|---|---|---|
| CLI một vài lệnh | Rất phù hợp | Có thể dư phức tạp | Thường không cần | Sync |
| Spring MVC CRUD mức vừa | Phù hợp | Có ích khi fan-out | Nếu hệ đã reactive | Đo trước |
| API hàng nghìn I/O concurrent | Platform threads có thể tốn | Phù hợp native async | Phù hợp nếu end-to-end | Async/reactive/virtual threads |
| Query trả một item | Đơn giản | Một future | Một Mono | Theo codebase |
| Query paginated hàng triệu rows | Cursor loop | Async pagination | Demand streaming | Theo lifecycle/backpressure |
| Change streams/CDC | Blocking cursor tùy API | Callback/async streams | Publisher thường tiện | Stream-focused |
| Background batch | Sync với bounded workers | Bounded futures | Flux với concurrency limit | Cả ba hợp lệ |
| Business transaction tuần tự | Dễ đọc | Async chain phức tạp hơn | Context cần cẩn thận | Theo transaction support |
| CPU-heavy processing | Không liên quan trực tiếp | Có thể offload CPU | Scheduler riêng | Không đẩy CPU lên I/O event loop |
| Virtual-thread HTTP service | Hợp về phong cách | Vẫn dùng được | Không bắt buộc | Bounded sync có thể tốt |

Không thể chọn chỉ theo số requests/giây. Cần **tỉ lệ I/O wait, fan-out, query size, transaction requirements, memory, deployment size, driver support và kỹ năng team**.

---

## 35. Chọn theo năng lực driver, không theo sở thích cú pháp

Quy trình đề xuất:

~~~mermaid
flowchart TD
    A["Xác định workload + SLO"] --> B{"Driver hỗ trợ gì?"}
    B --> C["Sync"]
    B --> D["Native async"]
    B --> E["Reactive publisher"]
    C --> F{"Tải in-flight và thread model chấp nhận?"}
    F -->|Có| G["Sync / virtual threads"]
    F -->|Không| H["Xem bounded offload hoặc đổi driver"]
    D --> I["CompletionStage + bounded concurrency"]
    E --> J["Publisher + demand + bounded fan-out"]
    G --> K["Benchmark + correctness tests"]
    H --> K
    I --> K
    J --> K
~~~

### 35.1. Nhiều driver trong cùng application có thể được chọn khác nhau

Một service có thể dùng sync MongoDB driver cho admin CLI, async DynamoDB SDK cho API và reactive MongoDB driver cho streaming. Nhưng cần tránh duplicate clients, tình trạng phiên bản phụ thuộc xung đột và việc cùng transaction bị chia qua hai driver families không hỗ trợ context chung.

### 35.2. Tiêu chí phải đo

- End-to-end p95/p99.
- Goodput logical requests/s.
- Memory/GC.
- CPU/threads.
- Connections.
- Database QPS and throttling.
- Error and retry rate.
- Recovery after failover.
- Developer complexity/testability.

### 35.3. Đừng giữ abstraction “universal NoSQL repository” quá mỏng

Nếu áp API `Flux<T>` cho Redis GET, MongoDB transaction, DynamoDB paginator và Cassandra LWT mà không thể mô tả consistency/transaction/ordering semantics của từng engine, abstraction có thể che rủi ro. Chuẩn hóa ở **business boundary**, nhưng giữ các options quan trọng minh bạch.

---

## 36. Migration từ sync sang async: làm từng boundary

Một lộ trình:

1. Đo trạng thái hiện tại: thread/connection wait, p99, throughput.
2. Chọn một endpoint I/O-bound đại diện.
3. Xác nhận native async API có feature parity.
4. Tách repository interface cho async result.
5. Đổi service composition từ call–wait sang `thenCompose`/`thenCombine`.
6. Giới hạn in-flight operations.
7. Thiết lập deadline propagation.
8. Phân loại lỗi và retry theo idempotency contract.
9. Thêm tests failure/timeout/cancel.
10. Benchmark với cùng data/query/consistency settings.
11. Canary và rollback có kế hoạch.
12. Chỉ mở rộng khi lợi ích đo được lớn hơn complexity.

### 36.1. Không đổi chỉ return type

Sai:

~~~java
CompletionStage<Customer> findAsync(String id) {
    return CompletableFuture.completedFuture(
        syncRepository.findById(id)
    );
}
~~~

Nó gọi database **đồng bộ trước** khi trả completed future, nên caller vẫn phải chờ I/O. Đây không phải asynchronous request execution.

### 36.2. Native async không thể chỉ “đổi chữ ký method” ở service

Phải xem:

- Transaction/session context.
- Exception wrapping.
- Resource lifecycle.
- Callback execution.
- Connection pool.
- Paging.
- Retry strategy.
- Testing timing/races.

### 36.3. Tránh all-or-nothing rewrite

Nên giữ một số endpoints sync nếu chúng ổn định, bắt đầu với đường nhiều I/O wait hoặc data streaming. Di chuyển từng boundary giảm rủi ro và đo lợi ích dễ hơn.

---

## 37. Migration từ async sang reactive: chú ý semantics của stream

`CompletionStage<List<T>>` khác `Publisher<T>`:

~~~text
CompletionStage<List<Row>>:
  Một completion, rồi đã có cả List.

Flux<Row>:
  Nhiều onNext signals theo subscription và demand.
~~~

### 37.1. Khi reactive có lợi

- Đọc cursor/stream lớn.
- Xử lý source→transform→sink liên tục.
- Muốn demand/backpressure rõ.
- HTTP streaming endpoints.
- Integration với reactive pipeline sẵn có.

### 37.2. Khi chỉ là `Mono<T>` cho một điểm đọc

Sự khác biệt với `CompletionStage<T>` có thể chủ yếu là **composition, context và lifecycle**, không phải throughput cao hơn đáng kể. Nên benchmark.

### 37.3. Thay đổi observable contract

Khi method trả Publisher thay vì future:

- Caller phải subscribe.
- Source có thể lazy.
- Mỗi subscription có thể chạy lại operation.
- Cancellation đi theo subscription.
- Errors là terminal signals.
- Context propagation có thể khác.
- Resource release phải theo reactive lifecycle.

Không chỉ dùng adapter `Mono.fromFuture` và coi mọi semantic đã tương đương; phải xét **eager future creation vs lazy publisher creation**.

### 37.4. `Mono.fromFuture` là adapter hữu ích

~~~java
Mono<GetItemResponse> mono =
    Mono.fromFuture(
        dynamoAsyncClient.getItem(request)
    );
~~~

Trong ví dụ, `getItem(request)` được gọi trước khi tạo Mono nên DB attempt có thể bắt đầu **eagerly**. Nếu cần bắt đầu operation khi subscribe, dùng deferred supplier theo Reactor API và version tương ứng. Điều này đặc biệt quan trọng khi retry/resubscribe.

---

## 38. Kiểm thử đơn vị: semantics của sync, async và reactive

### 38.1. Sync test

~~~java
@Test
void readsExistingCustomer() {
    Customer customer =
        syncRepository.findById("cus-42");

    assertEquals("cus-42", customer.id());
}
~~~

### 38.2. Async test

~~~java
@Test
void asyncReadCompletesWithCustomer() {
    Customer customer = asyncRepository
        .findByIdAsync("cus-42")
        .toCompletableFuture()
        .orTimeout(1, TimeUnit.SECONDS)
        .join();

    assertEquals("cus-42", customer.id());
}
~~~

Blocking ở **test boundary** có chủ đích và có timeout. Trong service handler, không sao chép `.join()` máy móc.

### 38.3. Reactive test với StepVerifier

~~~java
@Test
void reactiveReadEmitsOneCustomer() {
    StepVerifier.create(
            reactiveRepository.findById("cus-42")
        )
        .assertNext(customer ->
            assertEquals("cus-42", customer.id())
        )
        .verifyComplete();
}
~~~

`StepVerifier` thuộc `reactor-test`. Test cần dependency và imports phù hợp; code minh họa đặt trong class có repositories đã được inject hoặc fake.

### 38.4. Test `Mono.empty()`

Nếu lookup không có dữ liệu:

~~~java
StepVerifier.create(
        reactiveRepository.findById("missing")
    )
    .verifyComplete();
~~~

Chú ý phân biệt empty hợp lệ với lỗi network/authorization.

### 38.5. Test subscription count

Với publisher cold, kiểm tra một business request có gửi đúng số attempts mong đợi. Nếu handler vô tình subscribe trong service và framework lại subscribe ở controller, có thể tạo double write.

---

## 39. Kiểm thử backpressure, cancellation và thread blocking

Một suite nâng cao nên có:

| Test | Kịch bản | Oracle |
|---|---|---|
| B01 | Subscriber chỉ request 1 item | Không phát quá demand theo protocol |
| B02 | Subscriber xử lý chậm | Buffers không vượt policy |
| B03 | `flatMap` concurrency=8 | Không quá 8 inner subscriptions trong một pipeline |
| B04 | 50 pipelines cùng chạy | Tổng budget cluster không vượt |
| B05 | Client cancel trước subscribe | Cold operation không bị gửi ngoài dự kiến |
| B06 | Client cancel giữa read stream | Cursor cleanup theo driver contract |
| B07 | Client cancel sau write gửi | Không báo chắc chắn rollback; outcome handled |
| B08 | Subscriber hai lần vào write | Idempotency/dedup đúng |
| B09 | Callback chạy CPU-heavy | I/O event loop không bị chặn |
| B10 | Future callback ném exception | Stage completes exceptionally |
| B11 | Driver timeout rồi retry | Retry budget và same request ID |
| B12 | Query trả triệu rows | Không gom vô hạn trong heap |
| B13 | Publisher emits error after rows | Partial result contract rõ |
| B14 | Quorum timeout/failover | Consistency/outcome semantics không bị đổi |
| B15 | Application shutdown | In-flight policy và resources cleanup |

### 39.1. BlockHound hoặc công cụ tương tự

Có thể dùng công cụ phát hiện blocking calls trên non-blocking threads trong môi trường phù hợp. Phải xem JDK/Reactive runtime compatibility và không coi một tool là bằng chứng tất cả I/O operations non-blocking.

### 39.2. Dùng thời gian ảo khi test backoff

Reactor Test có các tiện ích virtual time cho những sequences phụ thuộc scheduler và không có external real I/O. Không dùng virtual time để chứng minh DB driver thực tế đã hoàn thành network request trong đúng số millisecond.

### 39.3. Kiểm thử dữ liệu thật trong staging

Integration tests cần kiểm cả path query, indexes, page size và failover theo engine. Một mock publisher in-memory không tái hiện connection pool, cursor timeout hoặc server-side cancellation.

---

## 40. Benchmark công bằng giữa ba mô hình

Một benchmark sai có thể cho reactive “nhanh hơn gấp 10” chỉ vì:

- Sync chạy một worker, reactive chạy 200 concurrent calls.
- Sync dùng read concern mạnh, reactive dùng eventual read.
- Reactive query có index, sync query thiếu index.
- Một bên giữ connection warm, bên kia tạo client liên tục.
- Một bên gom tất cả rows, bên kia chỉ lấy 10 rows.
- Một bên retry nhiều, bên kia không retry.
- Một bên đo client latency, bên kia chỉ đo time-to-first-element.

### 40.1. Chuẩn hóa thí nghiệm

Giữ cố định:

1. Dataset, index, partition distribution.
2. Query semantics, consistency/durability options.
3. Cluster topology/network/AZ.
4. Connection pooling đã warm.
5. Offered load và request mix.
6. Deadline/retry policy.
7. Number of app instances.
8. Batching/page sizes.
9. CPU/memory limits.
10. Metrics và cách tính success.

### 40.2. Đo ba mức latency

- **Time to first result.**
- **Time to last result / full completion.**
- **End-to-end response latency** đối với một logical user request.

Reactive streaming có thể gửi phần tử đầu sớm nhưng tổng stream dài; không nên dùng time-to-first-row để tuyên bố toàn report hoàn thành nhanh hơn.

### 40.3. Throughput có ích

Nếu A xử lý 8.000 DB attempts/s nhưng 3.000 là retry của requests đã timeout, còn B xử lý 6.000 attempts/s với 5.500 logical successes, B có thể tốt hơn về goodput.

### 40.4. P99 và tail under degradation

Cần benchmark khi có:

- Hot partition.
- Compaction.
- Replica lag.
- Network jitter.
- Failover.
- Throttling.
- Slow subscriber.

Hệ chạy tốt lúc khỏe không đủ chứng minh failure behavior tốt.

---

## 41. Tình huống 1: chọn API cho CRUD backend nhỏ

Bài toán:

~~~text
Spring MVC service
300 requests/s
Mỗi request 1-2 point lookups
Database p99=20 ms
Team quen Java blocking
Không có long-lived streams
~~~

**Lựa chọn hợp lý:** bắt đầu với synchronous driver, pooling, deadlines, indexes và concurrency limits; dùng virtual threads nếu môi trường/JDK phù hợp và đo thấy có lợi.

Không cần viết lại sang Reactor chỉ vì MongoDB có reactive client.

Câu hỏi cần test:

- p99 end-to-end.
- Số threads/connection wait.
- Query/index usage.
- Failure behavior và retry.
- Load khi một replica chậm.

---

## 42. Tình huống 2: hàng nghìn I/O calls đến nhiều key

Bài toán:

~~~text
API nhận một batch 500 IDs.
Có 10 application instances.
Một số keys rất nóng.
Backend có async API.
~~~

Không phát đồng thời `500 × 10 = 5.000` requests mỗi khi load tăng mà không có limit.

Thiết kế:

- Batch/chunk theo API hỗ trợ.
- Semaphore/cap tổng in-flight.
- Per-key/per-tenant limits.
- Deadlines.
- `CompletionStage` composition không block.
- Retry theo classified failures.
- Partial result policy rõ.
- Metrics: attempted vs successful logical lookups.

Nếu cần stream kết quả dần và bảo toàn backpressure, reactive có thể phù hợp hơn; nhưng native async futures cộng bounded batch vẫn có thể đáp ứng tốt.

---

## 43. Tình huống 3: CDC/change stream và downstream chậm

Một pipeline:

~~~text
MongoDB change stream / NoSQL CDC
        |
        v
Java transformer
        |
        v
Search index / Kafka / analytics
~~~

Nếu downstream chỉ xử lý 1.000 events/s nhưng nguồn tạo 5.000/s:

- Một bounded queue cục bộ sẽ sớm đầy.
- Reactive backpressure có thể điều tiết nơi hỗ trợ demand.
- Broker/CDC log retention phải đủ.
- Snapshot/replay/checkpoint cần rõ.
- Consumer idempotent theo event ID.
- Không gọi `.collectList()` cho stream vô hạn.
- Khi restart, phân biệt duplicate và missing event.
- Nếu log retention hết, cần rebootstrap/rebuild theo protocol.

**Reactive API có lợi cho biểu diễn stream**, nhưng không tạo thêm capacity của search index hoặc lưu trữ backlog vô hạn miễn phí.

---

## 44. Tình huống 4: write quan trọng sau failover

Bài toán:

~~~text
POST /reserve-seat
Leader/primary chuyển trong lúc DB write.
HTTP client timeout.
Client retry.
~~~

Cách triển khai an toàn:

1. Giữ `reservationId`/`idempotencyKey`.
2. Dùng conditional update/CAS/transaction theo engine.
3. Không coi timeout là chưa commit.
4. Xác minh outcome từ authoritative store.
5. Giới hạn retry và dùng backoff/jitter.
6. Không gửi payment/email chỉ vì một publisher emit trung gian.
7. Dùng outbox cho downstream event khi cần.
8. Theo dõi số request `UNKNOWN` đang cần reconciliation.

Điều này **đúng cho cả sync, async và reactive**. Kiểu Java API không thay thế business correctness.

---

## 45. Tình huống 5: kết hợp sync library vào reactive ứng dụng

Một third-party library chỉ cung cấp sync Redis operation hoặc sync filesystem access. WebFlux app cần gọi nó.

Hướng xử lý:

- Cô lập bằng bounded scheduler/executor.
- Đặt deadline và timeout thực tế ở library.
- Giới hạn concurrency.
- Không block Netty event loop.
- Kiểm context/transaction/tenant identity.
- Đo số tasks đang chờ.
- Cân nhắc thư viện native async/reactive nếu volume lớn.

Cần giải thích rõ trong ADR: đây là **blocking offload**, không phải native reactive end-to-end.

---

## 46. Bài tập 1: phân loại các đoạn code

Với mỗi đoạn, xác định caller blocking, native async hay reactive; nêu rủi ro.

~~~java
// A
var doc = syncCollection.find(eq("_id", id)).first();

// B
var future = asyncClient.getItem(request);

// C
var doc = asyncClient.getItem(request).join();

// D
var stage = CompletableFuture.supplyAsync(
    () -> syncRepository.load(id)
);

// E
var mono = Mono.from(reactiveCollection.find(eq("_id", id)).first());

// F
var value = reactiveRepository.findById(id).block();

// G
var flux = Flux.from(ids)
    .flatMap(reactiveRepository::findById, 8);

// H
reactiveRepository.save(command).subscribe();
return Mono.empty();
~~~

Gợi ý:

- A sync/blocking.
- B async caller không cần block.
- C blocking ở caller.
- D là blocking offload, không native async DB I/O.
- E reactive adapter.
- F blocking boundary, nguy hiểm trên event loop.
- G reactive fan-out cục bộ giới hạn 8.
- H có thể fire-and-forget sai lifecycle, mất error/commit evidence.

---

## 47. Bài tập 2: tính in-flight bằng Little's Law

Cho một service ổn định:

~~~text
Throughput: 1.200 requests/s
Mean DB execution latency: 25 ms
~~~

1. In-flight DB operations trung bình?
2. Nếu latency tăng lên 200 ms trong khi throughput vẫn 1.200/s, in-flight trung bình là bao nhiêu?
3. Connection pool 50 có đủ khi driver không multiplex không?
4. Nếu đồng thời DB sustainable throughput giảm còn 800/s, vì sao không dùng Little's Law của trạng thái ổn định để hứa hệ vẫn đáp ứng?
5. Với async/reactive, tăng number of in-flight từ 50 lên 500 có chắc làm throughput tăng không?
6. Nên đo queue wait, throttle, retry rate nào?

Gợi ý:

\[
L=1200\times0.025=30
\]

và nếu giữ trạng thái ổn định cùng throughput:

\[
L=1200\times0.2=240.
\]

Không suy được p99 từ mean.

---

## 48. Bài tập 3: rewrite async composition

Code ban đầu:

~~~java
Customer customer = repository.findById(id);
Preferences prefs = preferencesRepo.findByCustomerId(id);
Orders orders = ordersRepo.findRecentByCustomerId(id);

return new CustomerDashboard(customer, prefs, orders);
~~~

Yêu cầu:

1. Viết lại sử dụng `CompletionStage` không gọi `.get()`/`.join()` trong service.
2. Chạy ba calls song song nếu chúng độc lập và không phá consistency.
3. Dùng `thenCombine` hoặc `allOf` với error handling rõ.
4. Giới hạn concurrency toàn request.
5. Propagate deadline.
6. Nếu preferences lỗi nhưng allowed fallback, phân loại riêng.
7. Nếu customer không tồn tại, không báo dashboard thành công với dữ liệu lẫn tenant.
8. Viết test failover/timeouts.

---

## 49. Bài tập 4: streaming 1 triệu documents

Một API admin cần export 1 triệu documents từ MongoDB:

~~~text
Each document ~ 4 KiB
JVM heap 2 GiB
Network destination slower than DB source
~~~

Hãy so sánh:

- Sync cursor.
- Async pagination nếu driver hỗ trợ theo API tương ứng.
- Reactive `Flux` với downstream demand.
- Collect toàn bộ `List<Document>`.
- Checkpoint sau batch.
- Cursor TTL và cancellation.
- Tenant filtering và audit.
- Nên xử lý async job hay HTTP streaming?

Tính dung lượng logic xấp xỉ:

\[
1\,000\,000\times4\text{ KiB}
\approx3.81\text{ GiB}.
\]

Đây chưa bao gồm Java object overhead, nên gom cả vào heap 2 GiB là lựa chọn nguy hiểm.

---

## 50. Bài tập 5: bảo vệ reactive write khỏi duplicate subscription

Cho:

~~~java
Mono<InsertOneResult> save =
    Mono.from(collection.insertOne(doc));

save.subscribe();
save.subscribe();
~~~

1. Với cold publisher, điều gì có thể xảy ra?
2. Nếu `_id` được sinh mới mỗi attempt, nguy cơ gì?
3. Nếu `_id` ổn định và unique, duplicate exception nên được diễn giải thế nào?
4. Có nên chỉ dùng `.cache()` để bảo vệ payment?
5. Làm thế nào dùng request ID/idempotency ledger?
6. Nếu timeout sau commit nhưng trước ACK, nên trả outcome gì?
7. Cách sửa handler WebFlux để không subscribe tùy tiện?

---

## 51. Bài tập 6: driver capability matrix

Hãy tự lập bảng cho **phiên bản thư viện đang dùng** của:

- MongoDB Java Driver.
- Apache Cassandra Java Driver.
- AWS SDK v2 DynamoDB.
- Lettuce.
- Redis Jedis nếu project đang dùng.

Với mỗi driver, điền:

~~~text
Supported JDK:
Sync API:
Async API:
Reactive API:
Future/Publisher types:
Paging/streaming:
Transactions:
Consistency/write concern:
Cancellation:
Retries:
Connection pooling:
Metrics/tracing:
Known limitations:
~~~

Không suy từ API của thư viện này sang thư viện khác, không dùng blog của phiên bản cũ làm bằng chứng cho release hiện tại.

---

## 52. Bài tập 7: kiểm thử overload trong staging

Kịch bản:

~~~text
5 application instances
Each receives 300 req/s
DB p99 increases from 30 ms to 900 ms
Gateway retries 2 attempts
Driver retries 3 attempts
One hot partition receives 40% operations
~~~

Thiết kế:

1. Bounded global concurrency.
2. Per-hot-partition budget.
3. Retry ownership và attempt budget.
4. Backoff/jitter.
5. Phân biệt read vs non-idempotent write.
6. Sync thread pool/async callback/reactive subscription metrics.
7. HTTP 429/503 khi pre-admission reject.
8. Cancellation xử lý unknown write outcome.
9. Recovery mở dần traffic.
10. Test cùng consistency/read/write options để so sánh ba API.

Không dùng fault injection phá cluster production ngoài quy trình được phê duyệt.

---

## 53. Bài tập 8: phát hiện bẫy transaction context

Một Spring WebFlux service có đoạn:

~~~java
@Transactional
public Mono<Void> confirmOrder(String orderId) {
    blockingRepository.updateOrder(orderId);
    return reactivePublisher.publishOrderEvent(orderId);
}
~~~

Yêu cầu:

1. Phân tích phần nào blocking.
2. `@Transactional` ở đây dùng transaction manager nào?
3. DB update và event publish có atomic không?
4. Liệu event có thể publish khi DB rollback không?
5. Nếu client cancel Mono, DB update có thể đã xảy ra không?
6. Viết lại thiết kế dùng local transaction/outbox hoặc workflow có recovery.
7. Dùng context transaction phù hợp reactive stack nếu dùng reactive storage.
8. Test crash sau DB commit trước publish.

---

## 54. Runbook khi đổi API gây giảm hiệu năng

### Bước 1 — Xác nhận thay đổi

- Driver version và API family nào đổi?
- Sync → async, sync → reactive hay chỉ đổi framework wrapper?
- Query, read concern, consistency và index có giữ nguyên?
- Codec/serialization có khác không?
- Pool, max in-flight và retry policy có đổi?

### Bước 2 — Xác định nơi tắc

- JVM threads hay event-loop blocking?
- Executor queue hay connection acquisition?
- Reactive buffer/prefetch?
- Server QPS/IOPS?
- Hot key, repair/compaction?
- Retry amplification?

### Bước 3 — Giảm tải an toàn

Giảm concurrency, batch size và background workload; giữ requests có deadline, reject sớm phần không thể phục vụ. Không tạo queue vô hạn chỉ để giữ tỷ lệ “accepted” cao.

### Bước 4 — Kiểm tra functional correctness

- Query vẫn trả đúng key/tenant?
- Async pages đã được đọc đủ?
- Reactive stream có bị subscribe hai lần?
- Cancellation/timeout làm lost/duplicate write?
- Transaction/session context còn đúng?
- GSI/secondary reads có stale như trước?
- Event side effects có idempotent?

### Bước 5 — Khôi phục theo kế hoạch

Rollback driver/API nếu tương thích với data và transactions đang chạy, hoặc chỉnh limiter/pool/deadline. Không force rollback schema/data một cách mù quáng.

### Bước 6 — Xác nhận SLO

Đo p95/p99 end-to-end, goodput, actual DB attempts, retry rate, memory/GC, in-flight subscriptions và active connections sau khi hệ ổn định.

### Bước 7 — Ghi kết luận

Tách nguyên nhân “driver model không phù hợp” với “query thiếu index”, “pool quá nhỏ”, “hot partition” hoặc “retry storm”. Một migration async không đúng yêu cầu không có nghĩa tất cả async API đều tệ.

---

## 55. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Async luôn non-blocking I/O.” | Có thể là blocking offload |
| “Reactive luôn nhanh hơn sync.” | Phụ thuộc workload, overhead, driver và capacity |
| “`CompletableFuture` tự bắt đầu background thread.” | Nó là completion primitive, không bắt buộc một thread riêng |
| “`supplyAsync(syncCall)` là native async driver.” | Vẫn giữ worker chờ I/O |
| “`thenApply` chắc chắn chạy trên thread riêng.” | Có thể chạy trên thread completion |
| “Callback có thể block thoải mái.” | Có thể nghẽn I/O/event loop |
| “`get()` và `join()` không block.” | Chúng chờ kết quả |
| “WebFlux làm blocking driver thành reactive.” | Cần native reactive hoặc bounded offload |
| “`Mono` được tạo nghĩa DB đã query.” | Cold publisher thường lazy |
| “Subscribe hai lần chỉ đọc cache của publisher.” | Có thể chạy operation hai lần |
| “Gọi `.subscribe()` trong service là đủ.” | Có thể tách mất error/cancellation/lifecycle |
| “Backpressure giới hạn toàn bộ DB requests.” | Nó điều tiết emissions, không tự giới hạn concurrent subscriptions |
| “`Flux.collectList()` phù hợp stream lớn.” | Có thể giữ tất cả kết quả trong heap |
| “Virtual threads tăng throughput DB vô hạn.” | DB IOPS/partition/pool vẫn hữu hạn |
| “Pool 50 nghĩa chỉ có 50 in-flight requests.” | Phụ thuộc multiplexing/driver |
| “Cancel reactive write là rollback.” | Remote write có thể đã commit |
| “`orTimeout` chắc chắn hủy server call.” | Future timeout không tự bảo đảm remote cancellation |
| “Retry publisher đảm bảo exactly-once.” | Thường là resubscribe/re-execute |
| “Async bỏ được CAS/idempotency.” | Correctness thuộc storage/business contract |
| “Cassandra reactive biến CQL thành transaction.” | Consistency/transaction semantics không đổi |
| “DynamoDB paginator trả một item.” | Có thể phát nhiều pages |
| “Lettuce reactive và Jedis giống nhau.” | Driver capabilities khác |
| “Một `Mono.empty()` chắc là DB bị lỗi.” | Có thể là not-found hợp lệ |
| “Reactive transaction tự dùng ThreadLocal của JDBC.” | Reactive context/manager có semantics riêng |
| “Async results tự tải toàn bộ rows.” | Nhiều API trả từng page |
| “Tăng fan-out giảm latency mà không có giá.” | Tăng DB concurrency và network |
| “Server không cần giới hạn queue khi driver async.” | Async cũng có memory/backlog |
| “Đổi return type là xong migration.” | Cần lifecycle, context, timeout, tests |
| “Time-to-first-row là toàn bộ query latency.” | Phải đo full completion |
| “Benchmark khác consistency options vẫn công bằng.” | Phải giữ query/consistency tương đương |

---

## 56. Checklist trước khi chọn API trong dự án Java

- [ ] Xác định sync/async/reactive chính thức theo driver version.
- [ ] Phân biệt native async và wrapper offload.
- [ ] Kiểu trả kết quả (`T`, `CompletionStage`, `Publisher`) được ghi rõ.
- [ ] Có hiểu publisher cold/hot và subscription semantics.
- [ ] Không gọi `.block()`/`.join()` trong event loop.
- [ ] Callback không chạy blocking/CPU-heavy work trên I/O thread.
- [ ] Connection client/session lifecycle đúng.
- [ ] Pool, multiplexing và in-flight limits được đo.
- [ ] Global/per-tenant/per-key concurrency budgets có thiết kế.
- [ ] Queue và backpressure buffers bounded.
- [ ] Pagination, batch size và total-result limits rõ.
- [ ] Không gom dữ liệu streaming quá lớn trong heap.
- [ ] End-to-end deadline được truyền xuống driver.
- [ ] Cancel/timeout không bị nhầm với rollback.
- [ ] Retry budget, driver retries và idempotency phối hợp.
- [ ] Transaction/consistency/write concern giống yêu cầu nghiệp vụ.
- [ ] Context propagation cho auth/tenant/trace an toàn.
- [ ] Resource cleanup khi complete/error/cancel được kiểm.
- [ ] JVM threads, event loops, memory/GC và DB metrics có dashboard.
- [ ] Integration tests gồm failover/throttle/large result/duplicate subscription.
- [ ] Benchmark so cùng query, index, consistency và dataset.
- [ ] Có phương án canary, rollback và đối soát writes `UNKNOWN`.
- [ ] Đội phát triển hiểu cách debug errors trong futures và reactive signals.

---

## 57. Tổng kết

Khi kết nối Java với một hệ NoSQL, lựa chọn API đồng bộ, bất đồng bộ hoặc reactive nên bắt đầu từ **năng lực thật của driver** và **đặc tính workload**, không phải từ việc framework nào đang được xem là hiện đại hơn.

Các điểm cốt lõi:

1. **Sync** phù hợp control flow tuyến tính, dễ debug; thread model và concurrency phải được quản lý.
2. **Async** giúp caller không cần chờ tại điểm gọi, nhưng `CompletableFuture` không tự chứng minh native non-blocking I/O.
3. **Reactive** tổ chức nguồn dữ liệu theo Publisher/Subscriber và demand; rất hữu ích cho streaming, nhưng subscription, buffer và cancellation cần hiểu kỹ.
4. **Backpressure không thay admission/concurrency limit**. Nhiều subscribers hoặc một hot partition vẫn có thể làm DB quá tải.
5. **Đừng block event loop** bằng `.join()`, `.get()` hoặc `.block()`; blocking offload cần bounded resources.
6. **Virtual threads là một lựa chọn thực tế cho synchronous style**, nhưng không tạo thêm capacity ở database.
7. **Paging, transaction, consistency và durability do driver + NoSQL engine quyết định**, không do return type `Mono` hay `Future`.
8. **Retry/resubscribe/cancel có thể làm write chưa rõ kết quả**; stable IDs, idempotency, conditional writes và reconciliation vẫn bắt buộc khi nghiệp vụ cần.
9. **Resource lifecycle phải được kiểm cả khi complete, error và cancel**; cursor, connection và stream không tự an toàn chỉ vì code là reactive.
10. **Chọn bằng đo lường có kiểm soát**: goodput, p99, memory, threads, backend capacity, overload behavior và correctness.

**Câu cần nhớ: “Đồng bộ, bất đồng bộ và reactive là ba cách phối hợp I/O và kết quả trong Java. Chọn cách mà driver thực sự hỗ trợ và hệ của bạn vận hành an toàn nhất; đừng nhầm một API không chặn caller với một database không còn giới hạn tải, thời gian và tính đúng đắn.”**
