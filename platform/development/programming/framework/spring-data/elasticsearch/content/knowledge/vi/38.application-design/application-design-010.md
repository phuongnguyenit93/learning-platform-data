# Lựa chọn đồng bộ hoặc reactive theo mô hình tải thực tế

Spring Data Elasticsearch cung cấp hai nhóm API để ứng dụng làm việc với Elasticsearch: API imperative (đồng bộ) và API reactive (không chặn). Việc chọn mô hình nào nên dựa trên đặc điểm tải, kiến trúc ứng dụng, cách các dependency khác hoạt động và năng lực vận hành của đội phát triển.

API đồng bộ thường phù hợp với service request-response thông thường, CRUD vừa phải, ứng dụng Spring MVC và các luồng nghiệp vụ dễ biểu diễn tuần tự. API reactive có lợi khi ứng dụng phải giữ nhiều request I/O đang chờ cùng lúc, đã dùng Reactor/WebFlux xuyên suốt hoặc cần xử lý publisher theo luồng với backpressure.

Reactive không làm Elasticsearch xử lý một query nhanh hơn và cũng không tự tăng throughput của cluster. Nó giúp ứng dụng sử dụng thread hiệu quả hơn khi chờ I/O, đồng thời cung cấp cách biểu diễn luồng dữ liệu và điều tiết demand. Nếu tăng concurrency quá mức, reactive application vẫn có thể làm Elasticsearch quá tải, tạo HTTP 429, timeout và queue backlog.

Một quyết định tốt cần xem xét request rate, concurrency, latency, kích thước kết quả, batch size, thời gian xử lý CPU, số dependency blocking và mức độ phức tạp mà hệ thống có thể vận hành.

## 1. Hai mô hình trong Spring Data Elasticsearch

Spring Data Elasticsearch có API imperative và reactive với các abstraction tương ứng:

| Mô hình | Repository | Template/Operations | Kiểu kết quả phổ biến |
|---|---|---|---|
| Imperative | ElasticsearchRepository | ElasticsearchOperations / ElasticsearchTemplate | Entity, Optional, List, Page, SearchHits |
| Reactive | ReactiveElasticsearchRepository | ReactiveElasticsearchOperations / ReactiveElasticsearchTemplate | Mono<T>, Flux<T>, Mono<SearchHits<T>> hoặc Flux<SearchHit<T>> tùy API |

Ví dụ repository imperative:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);

    List<Product> findByStatus(String status);
}
```

Repository reactive:

```java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByStatus(String status);
}
```

Hai repository mô tả cùng một domain operation nhưng khác cách biểu diễn kết quả và cách caller chờ dữ liệu.

### 1.1. Imperative: gọi và chờ kết quả

Với API imperative, lời gọi repository trả kết quả sau khi thao tác hoàn tất:

```java
public Product findRequired(String id) {
    return repository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));
}
```

Thread thực hiện lời gọi sẽ chờ I/O hoàn tất trước khi tiếp tục. Cách viết này dễ đọc, dễ debug theo call stack và phù hợp với mô hình lập trình tuần tự.

### 1.2. Reactive: trả về một publisher

Với API reactive, service trả publisher mô tả kết quả trong tương lai:

```java
public Mono<Product> findRequired(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)));
}
```

Publisher thường lazy: request được thực thi khi có subscriber. Thread không cần ngồi chờ response từ Elasticsearch; khi I/O hoàn tất, tín hiệu được phát về subscriber và Reactor tiếp tục chain.

Reactive API phù hợp khi các tầng phía trên cũng hiểu publisher, ví dụ WebFlux controller trả Mono/Flux. Nếu cuối cùng gọi block ở mọi request, phần lớn lợi ích non-blocking bị mất.

## 2. Phân biệt blocking I/O và non-blocking I/O

Trong mô hình blocking, một thread thường thực hiện request, chờ response rồi mới xử lý tiếp. Nếu có nhiều request đồng thời, ứng dụng thường cần nhiều thread request để giữ các request đang chờ.

Trong mô hình non-blocking, thread khởi tạo I/O rồi nhường quyền thực thi trong lúc chờ. Khi dữ liệu sẵn sàng, runtime phát callback/signal để tiếp tục xử lý. Một nhóm event-loop thread có thể phục vụ nhiều kết nối I/O đồng thời.

```text
Blocking
Request A: [process] [wait for Elasticsearch] [process response]
Request B: [process] [wait for Elasticsearch] [process response]
Request C: [process] [wait for Elasticsearch] [process response]
             mỗi request giữ một thread trong lúc chờ

Non-blocking
Event loop: [start A] [start B] [start C] [handle A] [handle C] [handle B]
             thread được dùng lại trong lúc các request chờ I/O
```

Điều này không có nghĩa reactive không dùng thread hoặc Elasticsearch tự xử lý nhanh hơn. Reactive vẫn cần thread để xử lý callback, serialize/deserialize, mapping và logic ứng dụng. Khác biệt chính là thread không bị giữ chỉ để chờ network I/O.

### 2.1. Blocking không đồng nghĩa với thiết kế kém

Một service có vài request mỗi giây, query nhanh và logic đơn giản có thể hoạt động rất tốt với API imperative. Sự đơn giản của call stack, exception handling và transaction boundary có thể đáng giá hơn việc chuyển toàn bộ code sang reactive.

### 2.2. Non-blocking không đồng nghĩa với parallel

Reactive chain không tự chạy mọi bước đồng thời. Ví dụ:

```java
return repository.save(product)
        .flatMap(saved -> repository.findById(saved.getId()));
```

Lệnh find phụ thuộc vào kết quả save, vì vậy chỉ bắt đầu sau khi save phát ra giá trị. Reactive giúp thread không phải block trong lúc chờ; nó không loại bỏ quan hệ tuần tự của nghiệp vụ.

Nếu có nhiều thao tác độc lập, có thể kết hợp bằng zip hoặc flatMap có giới hạn concurrency. Cần chọn operator dựa trên quan hệ phụ thuộc và tải cho phép.

## 3. Mô hình tải quan trọng hơn nhãn đồng bộ/reactive

Trước khi chọn API, hãy mô tả tải ứng dụng:

- Request rate trung bình và đỉnh (requests/second).
- Số request đồng thời tại thời điểm cao điểm.
- p50, p95 và p99 latency của Elasticsearch.
- Tỷ lệ thao tác đọc/ghi.
- Kích thước request/response và số document mỗi lần.
- Thời gian CPU để transform, validate và map dữ liệu.
- Số dependency được gọi trong cùng một request.
- Tỷ lệ timeout, retry, HTTP 429 và lỗi từng item bulk.
- Mức tăng tải theo thời gian và yêu cầu latency/SLA.

Hai ứng dụng cùng có 100 request/second có thể có nhu cầu rất khác. Một ứng dụng xử lý request trong 5 ms và một ứng dụng chờ Elasticsearch 300 ms có số request đang in-flight khác nhau đáng kể.

### 3.1. Request rate và concurrency

Một ước lượng hữu ích từ định luật Little:

```text
Số request đang in-flight xấp xỉ
    throughput (request/second) x latency (second)
```

Ví dụ, nếu ứng dụng xử lý 200 request/second và thời gian một request chờ dependency trung bình là 50 ms:

```text
200 request/second x 0.05 second = khoảng 10 request in-flight
```

Đây chỉ là ước lượng cho hệ thống ổn định, không phải công thức sizing thread hoặc connection pool trực tiếp. Hãy đo cả thời gian xử lý CPU, queue, burst và phân bố latency.

Khi latency tăng, số request in-flight có thể tăng dù request rate không đổi. Nếu ứng dụng không giới hạn concurrency, backlog có thể tăng và gây timeout dây chuyền.

### 3.2. Tải I/O-bound và CPU-bound

| Loại tải | Ví dụ | Tác động của reactive |
|---|---|---|
| I/O-bound | Chờ Elasticsearch, database hoặc HTTP service | Có thể dùng thread hiệu quả hơn khi có nhiều request đang chờ. |
| CPU-bound | Phân tích ảnh, mã hóa nặng, tính toán lớn, transform document phức tạp | Không tự giảm lượng CPU cần thiết; cần worker/scheduler và giới hạn CPU riêng. |
| Mixed | Query Elasticsearch rồi xử lý nhiều dữ liệu trong ứng dụng | Có lợi ở phần I/O, nhưng cần cô lập phần CPU nặng khỏi event loop. |

Nếu phần lớn thời gian là CPU, chuyển sang reactive không làm CPU có thêm năng lực. Nếu phần lớn thời gian là chờ I/O và có nhiều request đồng thời, reactive có thể giảm nhu cầu tạo nhiều platform thread.

## 4. Khi nào API imperative thường phù hợp?

Chọn API imperative khi phần lớn các điều kiện sau đúng:

- Ứng dụng dùng Spring MVC và dependency chủ yếu là blocking.
- Request-response có số bước ít, tuần tự, dễ biểu diễn bằng lời gọi đồng bộ.
- Mức concurrency vừa phải và đã đáp ứng SLA.
- Service không cần stream kết quả liên tục cho downstream.
- Các thao tác batch có thể được xử lý bằng job/worker có giới hạn.
- Đội phát triển ưu tiên call stack trực tiếp, debug và xử lý exception đơn giản.
- Không có bằng chứng đo lường cho thấy thread chờ I/O là bottleneck.

Ví dụ service imperative:

```java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(Product product) {
        return repository.save(product);
    }

    public Product getRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }
}
```

Controller Spring MVC:

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping
    public Product create(@RequestBody Product product) {
        return service.create(product);
    }

    @GetMapping("/{id}")
    public Product get(@PathVariable String id) {
        return service.getRequired(id);
    }
}
```

Mô hình này dễ đọc và thường là điểm khởi đầu hợp lý cho CRUD service. Nếu đo đạc cho thấy số thread/platform thread tăng cao do I/O wait, mới cần đánh giá thêm lựa chọn non-blocking hoặc virtual threads.

## 5. Khi nào reactive thường phù hợp?

Reactive đáng cân nhắc khi:

- Ứng dụng có nhiều request I/O-bound đang chờ đồng thời.
- Phần lớn dependency đã có API non-blocking.
- Ứng dụng dùng Spring WebFlux/Reactor xuyên suốt.
- Cần kết hợp nhiều publisher và điều khiển concurrency rõ ràng.
- Có luồng dữ liệu lớn cần xử lý theo demand thay vì gom tất cả vào bộ nhớ.
- Cần cancellation/deadline propagation trong workflow bất đồng bộ.
- Đội ngũ hiểu Reactor, backpressure, context propagation và cách debug reactive chain.

Ví dụ service reactive:

```java
@Service
public class ReactiveProductService {

    private final ReactiveProductRepository repository;

    public ReactiveProductService(ReactiveProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> create(Product product) {
        return repository.save(product);
    }

    public Mono<Product> getRequired(String id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)));
    }

    public Flux<Product> findActive() {
        return repository.findByStatus("ACTIVE");
    }
}
```

WebFlux controller:

```java
@RestController
@RequestMapping("/products")
public class ReactiveProductController {

    private final ReactiveProductService service;

    public ReactiveProductController(ReactiveProductService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Product product) {
        return service.create(product);
    }

    @GetMapping("/{id}")
    public Mono<Product> get(@PathVariable String id) {
        return service.getRequired(id);
    }

    @GetMapping
    public Flux<Product> findActive() {
        return service.findActive();
    }
}
```

Controller trả publisher để WebFlux runtime quản lý subscription và response lifecycle. Service không tự subscribe và không gọi block.

### 5.1. Reactive có lợi khi nhiều dependency cùng non-blocking

Ví dụ request cần gọi Elasticsearch và một HTTP service khác:

```java
public Mono<ProductView> loadProductView(String id) {
    Mono<Product> product = productRepository.findById(id);
    Mono<Inventory> inventory = inventoryClient.getInventory(id);

    return Mono.zip(product, inventory)
            .map(tuple -> new ProductView(
                    tuple.getT1(),
                    tuple.getT2()
            ));
}
```

Hai thao tác độc lập có thể chạy đồng thời và được kết hợp khi cả hai có kết quả. Với API blocking, code tương đương thường cần hai thread hoặc thực hiện tuần tự. Lợi ích thực tế phụ thuộc latency từng dependency và concurrency của hệ thống.

Nếu một dependency vẫn blocking, cần xử lý riêng; chỉ bọc toàn bộ luồng bằng Mono không biến lời gọi blocking thành non-blocking.

## 6. So sánh theo tiêu chí vận hành

| Tiêu chí | Imperative | Reactive |
|---|---|---|
| Mô hình lập trình | Call/return tuần tự | Publisher, signal và operator |
| Thread khi chờ I/O | Thường bị giữ | Có thể được dùng lại |
| Nhiều request đồng thời | Thường cần nhiều request thread hơn | Event loop có thể phục vụ nhiều I/O đang chờ |
| Backpressure | Thường tự quản lý qua queue/worker/batch | Có cơ chế demand trong Reactive Streams |
| Debug | Call stack trực tiếp | Chain/operator và context phức tạp hơn |
| Exception | try/catch và throw | onError signal và error operators |
| Cancellation | Thường theo thread/request/task | Có subscription cancellation, nhưng không đảm bảo server rollback |
| Kết hợp dependency | Gọi tuần tự hoặc dùng concurrency utilities | zip/flatMap/concatMap và publisher composition |
| Tích hợp blocking library | Tự nhiên | Phải cô lập trên scheduler hoặc adapter |
| Độ phức tạp đội ngũ | Thường thấp hơn | Cần kiến thức Reactor và observability phù hợp |
| Hiệu năng | Tốt với tải vừa và mô hình đơn giản | Có thể hiệu quả hơn ở I/O concurrency cao |
| Elasticsearch capacity | Bị giới hạn bởi cluster/client | Vẫn bị giới hạn bởi cluster/client |

Không có mô hình nào luôn nhanh hơn. Đánh giá bằng workload thật và các chỉ số end-to-end.

## 7. Hiểu đúng về thread và connection pool

Reactive không loại bỏ giới hạn connection. Dù event-loop thread không block, request vẫn cần connection/socket và Elasticsearch vẫn phải xử lý request.

Một ứng dụng có thể có:

- Event-loop threads.
- HTTP connection pool.
- Queue chờ lấy connection.
- Request đang in-flight.
- Buffer dữ liệu nhận/gửi.
- Worker dành cho CPU hoặc tác vụ blocking.

Nếu pool chỉ cho phép một số connection nhất định, tăng số publisher không làm số request thực thi đồng thời tăng vô hạn. Ngược lại, tạo quá nhiều publisher có thể làm queue, memory và latency tăng.

### 7.1. Giới hạn connection không phải giới hạn concurrency duy nhất

Concurrency thực tế còn phụ thuộc:

- Connection pool và số connection khả dụng.
- HTTP transport.
- Số node và phân bố shard.
- Queue/thread pool phía Elasticsearch.
- Request size và thời gian xử lý.
- Số request từ các service khác cùng dùng cluster.

Không nên tăng connection pool chỉ để xóa hiện tượng queue. Nếu Elasticsearch đang bão hòa, nhiều connection hơn có thể khiến overload nặng hơn.

### 7.2. Connection pool trong mô hình imperative

Client imperative thường dùng connection pool để tái sử dụng connection. Thread có thể chờ khi connection chưa sẵn sàng hoặc request chưa hoàn tất. Cần theo dõi pool acquisition timeout, số connection leased/available và thời gian request.

### 7.3. Connection pool trong mô hình reactive

Client reactive cũng có giới hạn connection và pending acquire queue. Non-blocking chỉ thay đổi cách ứng dụng chờ; nó không biến một pool hữu hạn thành tài nguyên vô hạn. Cần đặt giới hạn pending acquire và in-flight work phù hợp với capacity cluster.

## 8. Reactive không tự tăng throughput của Elasticsearch

Giả sử cluster có thể xử lý ổn định 1.000 thao tác ghi/giây trong workload hiện tại. Việc chuyển client từ imperative sang reactive không tự biến capacity thành 2.000 thao tác/giây.

Reactive có thể giúp ứng dụng:

- Duy trì nhiều request đang chờ mà không cần một platform thread cho mỗi request.
- Kết hợp các I/O độc lập.
- Điều tiết demand ở một số pipeline.
- Giảm context switching do quá nhiều thread chờ.

Nhưng throughput của cluster vẫn phụ thuộc CPU, disk, shard, refresh, replica, mapping, ingest pipeline và kích thước request. Nếu reactive cho phép ứng dụng gửi nhanh hơn, cluster có thể nhận nhiều request hơn mức nó xử lý được và bắt đầu trả 429.

### 8.1. Tăng concurrency có thể làm p99 xấu hơn

Khi tải thấp, tăng concurrency có thể tăng throughput. Khi cluster gần bão hòa, tăng thêm concurrency thường làm queue và tail latency tăng. p50 có thể vẫn ổn trong khi p99 tăng mạnh do một số request phải chờ lâu hoặc retry.

Hãy đo p50/p95/p99, 429, timeout và queue depth trước khi tăng concurrency.

## 9. Backpressure và giới hạn tải

Reactive Streams có cơ chế demand: subscriber yêu cầu số phần tử mà nó có thể xử lý. Điều này giúp điều tiết luồng dữ liệu giữa publisher và subscriber.

Ví dụ:

```java
Flux<Product> products = repository.findByStatus("ACTIVE");

products
        .limitRate(100)
        .map(this::toExportRow)
        .subscribe(exportWriter::write);
```

limitRate điều chỉnh cách Reactor yêu cầu dữ liệu từ upstream. Nó không có nghĩa Elasticsearch chỉ truy vấn đúng 100 document tổng cộng; nó cũng không tự giới hạn tổng kết quả. Nếu cần giới hạn tổng số phần tử, dùng take(n) hoặc cấu hình query size phù hợp.

Backpressure chỉ hiệu quả xuyên suốt khi các publisher/operator và nguồn dữ liệu tôn trọng demand. Nếu code chuyển toàn bộ dữ liệu vào một List, gọi collectList hoặc đẩy vào queue không giới hạn, ứng dụng vẫn có thể dùng nhiều heap.

### 9.1. flatMap có thể tạo quá nhiều request

Ví dụ không giới hạn concurrency:

```java
Flux<Void> writes = products
        .flatMap(product -> repository.save(product))
        .then();
```

Với nguồn lớn, nhiều save có thể được subscribe đồng thời. Điều đó có thể tạo áp lực lên connection pool và Elasticsearch.

Giới hạn concurrency:

```java
Mono<Void> writes = products
        .flatMap(product -> repository.save(product), 8)
        .then();
```

Hoặc xử lý tuần tự khi thứ tự là yêu cầu:

```java
Mono<Void> writes = products
        .concatMap(repository::save)
        .then();
```

Giá trị 8 chỉ là ví dụ. Cần benchmark và theo dõi rejection/latency để chọn concurrency phù hợp.

### 9.2. concatMap, flatMap và flatMapSequential

| Operator | Hành vi | Khi phù hợp |
|---|---|---|
| concatMap | Subscribe inner publisher lần lượt; chờ publisher hiện tại complete. | Cần thứ tự và concurrency thấp. |
| flatMap | Cho phép inner publisher chạy đồng thời; output có thể interleave. | Các thao tác độc lập và có giới hạn concurrency. |
| flatMapSequential | Inner publisher có thể chạy đồng thời nhưng output giữ thứ tự nguồn. | Muốn concurrency nhưng cần thứ tự phát kết quả. |

Không chọn operator chỉ dựa trên tốc độ. Nếu các thao tác cập nhật cùng một document, thứ tự có thể là một phần của tính đúng đắn.

## 10. Tải đọc lớn: streaming hay pagination?

Một endpoint trả vài chục sản phẩm có thể dùng query/page thông thường. Một export hàng triệu document cần thiết kế khác:

- Giới hạn số hit mỗi lần.
- Xử lý từng batch thay vì giữ toàn bộ kết quả trong heap.
- Dùng PIT và search_after cho duyệt tập dữ liệu lớn khi phù hợp.
- Có checkpoint để tiếp tục sau lỗi.
- Giới hạn tốc độ downstream (file writer, object storage, message broker).
- Đóng tài nguyên/scroll/PIT theo đúng lifecycle.

Reactive có thể biểu diễn luồng xử lý downstream bằng Flux, nhưng không tự bảo đảm query Elasticsearch luôn streaming từng document từ server mà không buffer. Hành vi phụ thuộc API Spring Data, cách search được thực hiện và phiên bản client. Kiểm tra API cụ thể và đo memory thực tế.

Imperative cũng có thể xử lý dữ liệu lớn bằng batch, scroll/PIT, iterator hoặc worker bounded. Không cần chuyển cả ứng dụng sang reactive chỉ vì có một tác vụ export.

## 11. Tải ghi lớn: bulk quan trọng hơn lựa chọn reactive

Đối với ghi nhiều document, những yếu tố chính là:

- Bulk request thay vì một request cho từng document.
- Batch size theo byte và số item.
- Số request bulk đang in-flight.
- Mapping, analyzer và ingest pipeline.
- Shard distribution và refresh policy.
- Retry 429 có backoff/jitter.
- Checkpoint và dead-letter cho item thất bại.

Một pipeline reactive có thể tạo batch rồi gửi với concurrency giới hạn. Một job imperative có thể dùng worker pool và bulk adapter. Cả hai đều có thể hiệu quả nếu giới hạn queue và batch hợp lý.

Ví dụ reactive batch:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .concatMap(batch -> bulkWriter.write(batch))
            .then();
}
```

Ví dụ giới hạn hai batch đang chạy:

```java
Mono<Void> importProducts(Flux<Product> source) {
    return source
            .buffer(500)
            .flatMap(batch -> bulkWriter.write(batch), 2)
            .then();
}
```

Các ví dụ minh họa cách điều phối; bulkWriter.write cần có contract xử lý item-level failures, retry và checkpoint. Không giả định saveAll(Publisher) luôn tương đương một Bulk API request duy nhất.

Nếu nguồn dữ liệu là JDBC blocking, việc dùng Flux ở downstream không làm JDBC trở thành non-blocking. Có thể dùng batch reader/worker riêng hoặc cô lập blocking source trên scheduler phù hợp.

## 12. Spring MVC, WebFlux và mô hình persistence

### 12.1. Spring MVC + imperative repository

```text
HTTP request
    |
Spring MVC request thread
    |
Service imperative
    |
ElasticsearchRepository
    |
Blocking HTTP client
    |
Elasticsearch
```

Thread request chờ kết quả. Cần sizing thread pool, connection pool và timeout theo tải.

### 12.2. WebFlux + reactive repository

```text
HTTP request
    |
WebFlux event loop
    |
Reactive service (Mono/Flux)
    |
ReactiveElasticsearchRepository
    |
Non-blocking HTTP client
    |
Elasticsearch
```

Event-loop thread không bị giữ chỉ để chờ Elasticsearch response. Các dependency khác trong cùng request cũng nên non-blocking để giữ lợi ích end-to-end.

### 12.3. Spring MVC có thể trả publisher không?

Spring MVC có hỗ trợ một số reactive return types và có thể thích nghi với publisher. Tuy nhiên, việc trả Mono/Flux từ controller không tự biến toàn bộ ứng dụng thành WebFlux hoặc làm các dependency blocking trở thành non-blocking.

Hãy xem xét toàn bộ request lifecycle, executor, streaming response và dependency trước khi quyết định. Không chọn WebFlux chỉ vì một controller trả Flux.

### 12.4. Không gọi blocking repository trên event loop

Đây là anti-pattern:

```java
@GetMapping("/{id}")
public Mono<Product> get(@PathVariable String id) {
    Product product = blockingRepository.findById(id).orElseThrow();
    return Mono.just(product);
}
```

Lời gọi repository đã block trước khi Mono được trả về. Event-loop thread bị giữ trong lúc chờ.

Nếu chưa thể thay dependency blocking, có thể cô lập nó:

```java
@GetMapping("/{id}")
public Mono<Product> get(@PathVariable String id) {
    return Mono.fromCallable(() ->
                    blockingRepository.findById(id).orElseThrow())
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là cầu nối tạm thời. Nó vẫn là blocking I/O, chỉ được chuyển sang scheduler dành cho tác vụ blocking. Cần giới hạn tải và lên kế hoạch thay thế nếu workload yêu cầu non-blocking end-to-end.

Không gọi block trên WebFlux event-loop thread.

## 13. Có nên dùng reactive cho một ứng dụng chỉ gọi Elasticsearch?

Không nhất thiết. Nếu request chỉ gọi một repository method, xử lý vài field rồi trả response, API imperative có thể đơn giản và đủ nhanh.

Reactive có thể vẫn hữu ích nếu:

- Request concurrency rất cao và thời gian chờ Elasticsearch chiếm phần lớn lifecycle.
- Thread pool hiện tại là bottleneck đã được đo.
- Ứng dụng cần giữ nhiều kết nối streaming.
- Các dependency khác cũng đã có API reactive.

Ngược lại, nếu Elasticsearch là dependency duy nhất nhưng phần còn lại là JPA/JDBC blocking, filesystem blocking và thư viện đồng bộ, chuyển một phần sang reactive có thể tạo ra nhiều ranh giới chuyển đổi và khó kiểm soát hơn lợi ích thu được.

Hãy quyết định dựa trên số liệu, không dựa vào việc reactive được xem là mô hình hiện đại hơn.

## 14. Virtual threads và API imperative

Với Java 21 trở lên, virtual threads có thể làm cho mô hình blocking dễ mở rộng hơn trong ứng dụng I/O-bound. Virtual thread cho phép nhiều task blocking tồn tại mà không cần một platform thread riêng cho mỗi task trong phần lớn tình huống phù hợp.

Điều này làm thay đổi trade-off giữa imperative và reactive:

- Code imperative giữ call stack và exception flow đơn giản.
- Nhiều task I/O-bound có thể chờ trên virtual thread với chi phí thread thấp hơn platform thread.
- Không cần chuyển toàn bộ ứng dụng sang Reactor chỉ để tránh tạo quá nhiều platform thread.
- Connection pool, Elasticsearch capacity, CPU, memory và queue vẫn là giới hạn.
- Một số thao tác blocking/native hoặc synchronized region có thể ảnh hưởng khả năng unmount virtual thread tùy JDK/version.

Virtual threads không làm client imperative thành non-blocking. Chúng thay đổi cách JVM quản lý thread chờ. Cần benchmark với JDK, Spring Boot, HTTP client và workload thực tế.

Nếu dự án đã dùng WebFlux/Reactor end-to-end, reactive vẫn có lợi thế composition, backpressure và streaming. Nếu ứng dụng MVC dùng blocking libraries và muốn giữ code đơn giản, virtual threads là một lựa chọn đáng đánh giá.

## 15. Không trộn imperative và reactive tùy tiện

Một ứng dụng có thể dùng cả hai mô hình ở những boundary khác nhau, nhưng nên có quy tắc rõ ràng.

Tránh các trường hợp:

- Service reactive gọi block để lấy kết quả imperative.
- Service imperative gọi subscribe rồi trả về trước khi công việc hoàn tất.
- WebFlux event loop gọi JDBC hoặc Elasticsearch imperative trực tiếp.
- Reactive pipeline chuyển liên tục qua nhiều scheduler không cần thiết.
- Một luồng retry ở cả HTTP client, service và queue consumer mà không có retry budget tổng.

### 15.1. Không dùng subscribe để tạo fire-and-forget trong service

Ví dụ không nên dùng:

```java
public void save(Product product) {
    reactiveRepository.save(product).subscribe();
}
```

Caller không biết thao tác đã hoàn tất hay thất bại. Error có thể không được xử lý đúng, và lifecycle của request không còn bao gồm thao tác lưu.

Hãy trả publisher:

```java
public Mono<Product> save(Product product) {
    return reactiveRepository.save(product);
}
```

Nếu thật sự cần background job, hãy dùng scheduler/queue/job runner có ownership rõ ràng, lưu trạng thái, xử lý lỗi và quản lý shutdown.

### 15.2. Không dùng block như adapter mặc định

Ví dụ:

```java
public Product find(String id) {
    return reactiveRepository.findById(id).block();
}
```

Đoạn code biến API reactive thành blocking. Nếu được gọi từ event loop, nó có thể gây lỗi hoặc starvation. Nếu tầng gọi là imperative, cân nhắc dùng repository imperative tương ứng hoặc thiết kế boundary riêng; không chuyển qua lại ở mọi method.

## 16. Quản lý CPU-bound work trong reactive application

Reactor event loop cần được giữ thông thoáng. Không thực hiện công việc CPU nặng hoặc blocking lâu trực tiếp trên event-loop thread.

Ví dụ:

```java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::expensiveCpuTransformation);
```

Scheduler phù hợp phụ thuộc loại công việc. Schedulers.parallel() thường dùng cho tác vụ CPU-bound ngắn; Schedulers.boundedElastic() dành cho blocking task. Không chuyển mọi thao tác reactive sang scheduler khác nếu không có lý do.

Nếu transform nặng, giới hạn concurrency và theo dõi queue/scheduler saturation. Một Flux có thể nhận dữ liệu nhanh hơn CPU downstream xử lý; backpressure/buffer phải được thiết kế có giới hạn.

## 17. Timeout, cancellation và retry trong hai mô hình

Imperative:

- Timeout thường được biểu diễn qua client/request timeout và exception.
- Caller chờ cho đến khi kết quả hoặc lỗi được trả về.
- Cancellation có thể liên quan đến interrupt hoặc hủy request tùy client.

Reactive:

- Có thể dùng operator timeout cho deadline của publisher.
- Subscriber cancellation dừng việc chờ/tiếp nhận tín hiệu ở phía ứng dụng.
- Cancellation không bảo đảm Elasticsearch rollback một write đã đến server.
- Retry được biểu diễn bằng operator nhưng vẫn cần idempotency và retry budget.

Ví dụ reactive timeout:

```java
return repository.findById(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(TimeoutException.class,
                error -> new ProductSearchTimeoutException(id, error));
```

Timeout của publisher không nhất thiết giống timeout ở HTTP transport. Cần cấu hình và quan sát cả connection timeout, response timeout, application deadline và proxy timeout.

Không retry mọi timeout một cách mù quáng. Với write, server có thể đã xử lý request trước khi response bị mất. Dùng ID ổn định, version hoặc cơ chế đối soát.

## 18. Tải đọc: chọn theo kích thước và cách tiêu thụ kết quả

| Use case | Gợi ý |
|---|---|
| GET theo ID và trả một document | Imperative hoặc reactive đều phù hợp; chọn theo stack ứng dụng. |
| Search trả vài chục kết quả cho API | Imperative thường đơn giản; reactive hữu ích nếu request đã nằm trong WebFlux stack. |
| Nhiều search độc lập trong một request | Reactive có thể kết hợp publisher; imperative có thể dùng concurrency utilities. |
| Export dữ liệu lớn | Dùng batch/cursor/PIT, giới hạn memory và checkpoint; reactive là một lựa chọn chứ không phải yêu cầu. |
| Streaming response tới client | Reactive/WebFlux có thể phù hợp nếu cả đường đi hỗ trợ streaming và backpressure. |
| Search có aggregation lớn | Tối ưu query/mapping và kích thước aggregation quan trọng hơn lựa chọn API. |

Với export lớn, tránh gom toàn bộ dữ liệu vào List hoặc collectList. Dùng batch/cursor và ghi dần ra destination. Đóng PIT/scroll khi hoàn tất hoặc bị hủy.

## 19. Tải ghi: chọn theo batching và độ tin cậy

Đối với ghi nhiều document, những yếu tố chính là:

- Bulk API và batch size.
- Payload byte size.
- Số batch in-flight.
- Refresh policy.
- Retry 429 và item-level failures.
- Idempotency và checkpoint.
- Dead-letter cho dữ liệu không hợp lệ.

Imperative job có thể đọc từng batch, gọi bulk operation và xử lý response. Reactive job có thể biểu diễn nguồn bằng Flux, buffer thành batch và giới hạn concurrency. Cả hai cần kiểm tra từng item trong bulk response.

Không giả định ReactiveElasticsearchRepository.saveAll tự động gửi một bulk request tối ưu hoặc đảm bảo mọi item thành công. Kiểm tra API/implementation của phiên bản đang dùng và dùng bulk API rõ ràng nếu yêu cầu throughput.

## 20. Ma trận quyết định theo mô hình tải

| Mô hình tải/kiến trúc | Lựa chọn khởi đầu | Lý do |
|---|---|---|
| CRUD nội bộ, concurrency thấp/vừa, Spring MVC | Imperative | Đơn giản, dễ vận hành, thường đủ năng lực. |
| API request-response, một query Elasticsearch | Imperative hoặc reactive theo stack hiện tại | Không nên đổi stack chỉ vì một repository call. |
| WebFlux end-to-end, dependency đều non-blocking | Reactive | Giữ được non-blocking từ HTTP đến Elasticsearch. |
| Rất nhiều request I/O-bound đồng thời | Đánh giá reactive hoặc virtual threads | Giảm số platform thread bị giữ khi chờ I/O. |
| Nhiều dependency reactive cần kết hợp | Reactive | Publisher composition rõ ràng và hỗ trợ cancellation/backpressure. |
| CPU-bound transformation nặng | Cả hai, có worker model phù hợp | Reactive không làm giảm lượng CPU cần thiết. |
| Import/export khối lượng lớn | Batch + bounded concurrency; imperative hoặc reactive | Batching, memory và checkpoint quyết định nhiều hơn API style. |
| Ứng dụng dùng JPA/JDBC blocking xuyên suốt | Imperative thường đơn giản hơn | Tránh nhiều ranh giới blocking/reactive. |
| Java 21+ MVC, workload I/O-bound | Benchmark imperative với virtual threads và reactive | Hai lựa chọn có trade-off khác nhau. |
| Đội chưa có kinh nghiệm Reactor | Imperative trước | Giảm rủi ro vận hành và chi phí học tập. |

Ma trận chỉ định hướng lựa chọn ban đầu. Kết quả benchmark và số liệu production mới là cơ sở kết luận.

## 21. Quy trình benchmark trước khi chuyển đổi

Không quyết định dựa trên một microbenchmark đơn lẻ. Hãy mô phỏng request path thực tế:

1. Dùng cùng Elasticsearch version, mapping, shard và dữ liệu.
2. Dùng cùng query, sort, aggregation và result size.
3. Dùng cùng HTTP client timeout, connection limit và TLS/security config.
4. Mô phỏng tải thấp, tải trung bình, peak và burst.
5. Đo p50/p95/p99 latency, throughput và error rate.
6. Theo dõi CPU, heap, GC, platform thread, event-loop utilization và connection pool.
7. Theo dõi Elasticsearch thread pool, indexing pressure, 429 và search latency.
8. Chạy đủ lâu để quan sát queue/backlog và memory behavior.
9. Thử lỗi dependency, timeout, retry và cancellation.
10. So sánh độ phức tạp code, khả năng debug và chi phí vận hành.

Nếu so sánh imperative với reactive, không thay đổi đồng thời batch size, connection pool, shard count hoặc query. Nếu thay nhiều yếu tố cùng lúc, không thể biết cải thiện đến từ đâu.

### 21.1. Chỉ số cần thu thập

| Nhóm | Chỉ số |
|---|---|
| Request | Requests/second, in-flight requests, p50/p95/p99 latency. |
| Lỗi | HTTP 429, timeout, 5xx, mapping errors, bulk item failures. |
| JVM | CPU, heap, GC pause, allocation rate, platform thread count. |
| Reactive runtime | Event-loop utilization, scheduler queue, pending task. |
| HTTP client | Connection leased/available, pending acquire, connection timeout. |
| Elasticsearch | Search/write latency, thread pool queue/rejected, indexing pressure, node CPU/disk. |
| Pipeline | Batch count/bytes, queue depth, retry count, DLQ count, checkpoint lag. |

Không chỉ nhìn throughput trung bình. Một cấu hình có throughput cao hơn nhưng p99 tăng mạnh hoặc lỗi 429 nhiều hơn có thể không phù hợp SLA.

## 22. Các dấu hiệu chọn sai mô hình hoặc cấu hình

### 22.1. Dấu hiệu imperative cần được đánh giá lại

- Platform thread count tăng mạnh theo số request đang chờ.
- Thread pool thường xuyên cạn hoặc request queue tăng.
- I/O wait chiếm phần lớn thời gian request.
- Nhiều request đồng thời chỉ chờ các dependency non-blocking-capable.
- Tải đỉnh gây thread exhaustion dù Elasticsearch vẫn còn capacity.

Các dấu hiệu này chưa tự chứng minh cần reactive. Có thể tối ưu timeout, pool, cache, query, dùng virtual threads hoặc giảm số round trip trước.

### 22.2. Dấu hiệu reactive đang tạo tải quá mức

- HTTP 429/rejection tăng khi tăng concurrency.
- Pending connection acquire hoặc scheduler queue tăng.
- Heap tăng do buffer/collectList/queue không giới hạn.
- p99 tăng dù throughput không tăng.
- Event loop bị block bởi JDBC, logging hoặc CPU-heavy transformation.
- Retry chồng tầng tạo request amplification.

Hướng xử lý là giảm in-flight work, thêm backpressure, giới hạn buffer/concurrency và loại bỏ blocking khỏi event loop.

## 23. Kiến trúc lai có thể hợp lý

Một hệ thống không bắt buộc mọi module phải cùng một mô hình. Ví dụ:

```text
Spring MVC API
   |
   +---- ProductService (imperative)
   |          |
   |          +---- ElasticsearchRepository
   |
   +---- ExportJob
              |
              +---- ReactiveElasticsearchOperations
                        |
                        +---- bounded Flux -> file/object storage
```

Kiến trúc lai có thể hợp lý nếu boundary rõ ràng:

- API CRUD dùng imperative vì dependency và workload phù hợp.
- Một export worker dùng reactive publisher để điều phối streaming.
- Một bulk import worker dùng batch queue và bounded concurrency.

Không nên trộn hai mô hình bên trong cùng một call chain mà không có adapter/lifecycle rõ ràng. Chọn đúng API theo module và tránh gọi block/subscribe tùy tiện.

## 24. Kiểm thử theo mô hình đã chọn

Imperative service:

- JUnit/Mockito cho logic service.
- Repository integration test với Elasticsearch thật/Testcontainers.
- Kiểm tra timeout, lỗi mapping và bulk partial failure ở adapter.

Reactive service:

- StepVerifier kiểm tra onNext/onComplete/onError.
- Kiểm tra empty result, cancellation và timeout.
- Kiểm tra concurrency/backpressure ở pipeline quan trọng.
- Repository integration test dùng Elasticsearch thật và refresh tường minh cho Search API.
- Kiểm tra không có blocking call trên event-loop thread trong các đường đi quan trọng.

Ví dụ reactive service test:

```java
when(repository.findById("P-100"))
        .thenReturn(Mono.just(product));

StepVerifier.create(service.getRequired("P-100"))
        .expectNext(product)
        .verifyComplete();
```

Ví dụ kiểm tra publisher rỗng:

```java
when(repository.findById("P-404"))
        .thenReturn(Mono.empty());

StepVerifier.create(service.getRequired("P-404"))
        .expectError(ProductNotFoundException.class)
        .verify();
```

Unit test reactive không thay thế integration test. Mock publisher không xác minh query hoặc mapping trên Elasticsearch.

## 25. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chuyển sang reactive nhưng latency query không giảm | Thời gian chủ yếu nằm ở Elasticsearch/query/network. | Tối ưu query, mapping, shard và payload; reactive không tăng tốc engine. |
| Reactive app gặp 429 nhiều hơn | Concurrency tăng vượt capacity cluster. | Giới hạn in-flight work, backoff và đo thread pool/indexing pressure. |
| WebFlux event loop bị block | Gọi repository imperative, JDBC hoặc thư viện blocking trực tiếp. | Dùng API reactive hoặc cô lập blocking trên boundedElastic. |
| Dùng Mono nhưng request vẫn blocking | Gọi blocking method trước khi tạo publisher. | Bọc đúng boundary hoặc thay dependency bằng API non-blocking. |
| Gọi block trong controller | Chuyển reactive thành đồng bộ trên event loop. | Trả Mono/Flux cho WebFlux runtime. |
| Dữ liệu không được lưu dù gọi save | Publisher bị bỏ mà không subscribe/return. | Nối publisher vào workflow và trả về caller. |
| Background error bị mất | Gọi subscribe nội bộ không có lifecycle/error handler. | Trả publisher hoặc dùng job runner có quản lý trạng thái. |
| Heap tăng khi export | collectList, buffer hoặc queue không giới hạn. | Streaming/batch bounded, giới hạn page và demand. |
| flatMap tạo quá nhiều request | Không giới hạn concurrency trên Flux lớn. | Dùng flatMap concurrency, concatMap hoặc bounded queue. |
| Reactive code khó debug | Chain dài, context propagation không rõ. | Chia method theo bước, gắn trace context và test bằng StepVerifier. |
| Tăng connection pool nhưng latency xấu hơn | Elasticsearch đã bão hòa. | Giảm tải và tìm bottleneck thay vì chỉ tăng connection. |
| API reactive gọi JPA/JDBC blocking | Dependency không đồng nhất mô hình. | Cân nhắc imperative stack hoặc cô lập blocking dependency. |
| Bulk reactive vẫn mất item | Chỉ kiểm tra request completion, bỏ qua item-level errors. | Phân tích từng item, retry/DLQ và checkpoint. |
| Dùng reactive chỉ vì dữ liệu lớn | Nhầm reactive với bulk/streaming tối ưu tự động. | Thiết kế batch/cursor và giới hạn memory; benchmark cả hai mô hình. |

## 26. Quy trình lựa chọn cho một dự án mới

1. **Mô tả workload:** request rate, peak concurrency, latency target, read/write ratio và payload size.
2. **Xác định dependency:** Elasticsearch, database, HTTP service, filesystem và message broker đang dùng API blocking hay non-blocking.
3. **Xác định mô hình web:** Spring MVC, WebFlux hoặc worker/job không có HTTP request.
4. **Phân loại công việc:** I/O-bound, CPU-bound, request-response, streaming hay bulk.
5. **Chọn mô hình đơn giản đáp ứng yêu cầu:** imperative nếu phù hợp; reactive khi có lợi ích cụ thể về I/O concurrency/streaming.
6. **Đặt giới hạn:** connection pool, in-flight request, batch size, queue capacity, page size và timeout.
7. **Thiết kế lỗi:** retry budget, backoff/jitter, idempotency, DLQ và checkpoint.
8. **Đo baseline:** thu thập latency, throughput, thread, memory và Elasticsearch metrics.
9. **Benchmark dưới tải đại diện:** bao gồm peak, burst và dependency chậm.
10. **Kiểm thử failure mode:** 429, timeout, cancellation, partial bulk failure và cluster unavailable.
11. **Đánh giá chi phí vận hành:** khả năng debug, tracing, context propagation và năng lực đội ngũ.
12. **Chỉ chuyển đổi khi có bằng chứng:** ghi lại mục tiêu, chỉ số trước/sau và giới hạn của thay đổi.

## 27. Những điểm cần nhớ

- Spring Data Elasticsearch có API imperative và reactive; cả hai đều sử dụng cùng cluster và chịu cùng giới hạn tài nguyên phía Elasticsearch.
- Imperative thường phù hợp với Spring MVC, CRUD và workload vừa phải khi dependency chủ yếu blocking.
- Reactive hữu ích khi có nhiều I/O-bound request đồng thời, WebFlux/Reactor end-to-end hoặc pipeline cần backpressure.
- Reactive không làm query Elasticsearch nhanh hơn và không tự tăng throughput của cluster.
- Concurrency không giới hạn có thể làm tăng HTTP 429, timeout, queue và p99 latency.
- Backpressure chỉ có tác dụng khi pipeline giữ demand và không gom toàn bộ dữ liệu vào bộ nhớ.
- Bulk size, byte size, retry, checkpoint và idempotency thường quan trọng hơn việc chọn imperative hay reactive cho import/export lớn.
- Không gọi blocking repository trên WebFlux event loop; không dùng block/subscribe như cách nối tầng mặc định.
- CPU-bound transformation cần worker/scheduler phù hợp; reactive không tạo thêm CPU capacity.
- Virtual threads trên Java 21+ là một lựa chọn bổ sung cho workload blocking I/O; vẫn cần benchmark và giới hạn connection/cluster.
- Có thể dùng kiến trúc lai nếu boundary và lifecycle rõ ràng.
- Đo p50/p95/p99, throughput, thread, memory, connection pool, 429 và Elasticsearch queue trước khi quyết định.
- Chọn mô hình đơn giản nhất đáp ứng SLA và khả năng vận hành, sau đó thay đổi dựa trên số liệu.

Lựa chọn đồng bộ hay reactive là quyết định kiến trúc dựa trên mô hình tải thực tế. Imperative đem lại cách tổ chức đơn giản cho nhiều service request-response; reactive giúp quản lý nhiều I/O đang chờ và luồng dữ liệu có demand rõ ràng. Cả hai đều cần giới hạn concurrency, connection, batch và retry. Khi đo workload, hiểu dependency và theo dõi cả ứng dụng lẫn Elasticsearch, đội phát triển có thể chọn mô hình phù hợp mà không đánh đổi tính ổn định để chạy theo một phong cách lập trình.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Spring Data Elasticsearch — Reactive repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/reactive-repositories.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams — Specification](https://www.reactive-streams.org/)
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Java — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch — Thread pool settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html)
