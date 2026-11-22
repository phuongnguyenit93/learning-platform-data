# Chọn giới hạn flatMap concurrency theo tài nguyên phía sau

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Hiệu năng và tải  
**Mục tiêu:** Chọn giới hạn đồng thời cho các inner Publisher của Reactor dựa trên sức chứa database, connection pool, API đối tác, CPU và bộ nhớ; phân biệt concurrency với prefetch, rate limit và global bulkhead; kiểm chứng giới hạn bằng test và metrics.

## 1. Vấn đề cần giải quyết

Một endpoint nhận danh sách 500 mã đơn hàng rồi gọi dịch vụ đối tác cho từng mã. Nếu viết:

```java
Flux<Result> results = ids.flatMap(partnerClient::fetch);
```

các request con có thể được subscribe đồng thời theo cấu hình mặc định của Reactor. Nếu upstream phát nhanh, dịch vụ đối tác có thể nhận quá nhiều request cùng lúc, connection pool bị bão hòa, pending queue tăng, latency kéo dài và request bắt đầu timeout.

Có thể đặt trần cho số công việc con đang được xử lý trong một pipeline:

```java
Flux<Result> results = ids.flatMap(
        partnerClient::fetch,
        8,
        1);
```

Số 8 là concurrency: số inner Publisher tối đa đang in-flight. Số 1 là prefetch: lượng demand được yêu cầu trước từ mỗi inner Publisher. Hai tham số có ý nghĩa khác nhau. Không chọn concurrency chỉ vì một con số có vẻ nhỏ; cần biết mỗi inner đang giữ resource nào, resource có giới hạn bao nhiêu và có bao nhiêu request cha chạy cùng lúc.

**Nguyên tắc:** đặt concurrency theo nút thắt tài nguyên thực tế ở downstream, sau đó kiểm chứng bằng tải đại diện và metrics. Không tối ưu dựa trên số core CPU hoặc kích thước thread pool một cách máy móc.

## 2. flatMap concurrency thực sự giới hạn điều gì?

`Flux.flatMap(mapper, concurrency, prefetch)` thực hiện ba việc:

1. Nhận một phần tử từ upstream và gọi mapper để tạo inner Publisher.
2. Subscribe vào inner Publisher một cách eager, cho phép nhiều inner chạy đồng thời.
3. Merge kết quả của các inner Publisher thành một Flux downstream; các giá trị có thể interleave và không bảo toàn thứ tự đầu vào.

| Tham số | Ý nghĩa | Tác động |
|---|---|---|
| `concurrency` / `maxConcurrency` | Số inner Publisher tối đa được subscribe và xử lý đồng thời | Giới hạn số thao tác con in-flight trong một subscription |
| `prefetch` | Số phần tử được yêu cầu trước từ mỗi inner Publisher | Điều chỉnh demand và buffering của từng inner, ảnh hưởng bộ nhớ và thông lượng |

Concurrency cũng quyết định lượng demand ban đầu mà `flatMap` phát ngược lên upstream. Khi một inner hoàn thành, operator có thể yêu cầu phần tử nguồn tiếp theo để mở slot mới. Đây là cách operator phối hợp backpressure với giới hạn số inner.

Ví dụ:

```java
Flux.range(1, 100)
        .flatMap(this::callPartner, 6, 1);
```

Trong một subscription, `flatMap` giữ tối đa sáu inner Publisher đang hoạt động. Khi một inner kết thúc, slot đó được tái sử dụng cho phần tử kế tiếp. Nếu mapper trả `Mono`, mỗi inner thường biểu diễn một request con. Nếu trả `Flux`, một inner có thể phát nhiều item; khi đó prefetch có ý nghĩa rõ hơn.

### 2.1. Concurrency không phải số thread

`flatMap(..., 8, ...)` không có nghĩa Reactor tạo tám thread riêng. Concurrency là số inner subscription đang in-flight. Các publisher có thể dùng event loop, callback I/O, scheduler hoặc driver riêng.

`flatMap` cũng không tự chuyển công việc sang scheduler khác. Với WebClient, I/O là non-blocking; concurrency giới hạn số request con đang chạy, không tạo tám thread để chờ socket.

Nếu mapper gọi một hàm blocking, nó có thể chặn thread phát tín hiệu. Hãy cô lập blocking call và vẫn giới hạn số công việc:

```java
Flux<Result> results = ids.flatMap(
        id -> Mono.fromCallable(() -> legacyBlockingLookup(id))
                .subscribeOn(Schedulers.boundedElastic()),
        8,
        1);
```

Đây là cách cô lập API blocking cũ; nó không biến API đó thành non-blocking. Scheduler `boundedElastic` có giới hạn thread và hàng đợi riêng, nên phải tính cả hai giới hạn.

### 2.2. Concurrency không phải rate limit

Concurrency giới hạn số thao tác đang chạy cùng lúc. Rate limit giới hạn số lần bắt đầu thao tác trong một khoảng thời gian.

Ví dụ, tám request cùng chạy và mỗi request mất trung bình 200 ms có thể hoàn tất khoảng 40 request/giây trong điều kiện ổn định. Nhưng nếu đối tác quy định tối đa 10 request/giây, `flatMap(..., 8)` không tự tuân thủ quota đó. Cần token bucket, rate limiter hoặc cơ chế pacing riêng.

### 2.3. Concurrency không phải global bulkhead

Giới hạn 8 chỉ áp dụng cho một subscription của operator đó. Nếu có 30 HTTP request đồng thời, mỗi request tạo pipeline riêng với `flatMap(..., 8)`, tổng số thao tác con có thể tiến gần 240.

Để bảo vệ pool hoặc upstream dùng chung, cần giới hạn toàn cục bổ sung: bulkhead, admission control, giới hạn queue/pool hoặc một điểm điều phối chung. Không dùng semaphore blocking trên event-loop; chọn reactive bulkhead hoặc cơ chế acquire không chặn.

## 3. Chọn operator theo thứ tự và mức đồng thời

| Operator | Số inner đồng thời | Thứ tự output | Đặc điểm |
|---|---:|---|---|
| `flatMap(mapper, C, P)` | Tối đa C | Không đảm bảo theo thứ tự nguồn | Merge ngay khi inner phát dữ liệu; phù hợp công việc độc lập |
| `flatMapSequential(mapper, C, P)` | Tối đa C | Giữ thứ tự nguồn | Subscribe inner sớm nhưng buffer kết quả của inner sau nếu inner trước chậm |
| `concatMap(mapper, P)` | Một inner tại một thời điểm | Giữ thứ tự nguồn | Tuần tự, dễ kiểm soát resource và side effect phụ thuộc thứ tự |

Giả sử request A mất 500 ms còn B mất 50 ms. `flatMap` có thể phát kết quả B trước A. `flatMapSequential` vẫn subscribe B trong khi A đang chạy, nhưng giữ kết quả B trong queue cho đến khi A phát xong. `concatMap` chỉ subscribe B sau khi A hoàn tất.

```java
// Công việc độc lập, không yêu cầu thứ tự.
Flux<Result> merged = ids.flatMap(this::fetch, 8, 1);

// Có thể chạy song song nhưng phải phát theo thứ tự nguồn.
Flux<Result> ordered = ids.flatMapSequential(this::fetch, 8, 1);

// Phải hoàn tất từng thao tác trước khi bắt đầu thao tác kế tiếp.
Flux<Result> serial = ids.concatMap(this::writeSequentially, 1);
```

Dùng `concatMap` khi side effect phải theo thứ tự hoặc khi các bước dùng chung một resource không hỗ trợ thao tác song song. Dùng `flatMapSequential` khi có thể chạy inner song song nhưng output phải theo thứ tự; lưu ý head-of-line blocking và bộ nhớ queue.

## 4. Xác định resource bottleneck

Trước khi chọn C, liệt kê mỗi inner Publisher sử dụng những gì:

| Tác vụ trong mapper | Resource bị chiếm | Giới hạn cần biết |
|---|---|---|
| WebClient gọi đối tác | Connection, pending acquire slot, quota đối tác | Max connections, pool queue, API in-flight/rate quota |
| R2DBC query độc lập | Connection DB, transaction, server execution slot | Pool size, DB connection budget, query capacity |
| Ghi file | File handle, disk bandwidth, buffer | Số file đồng thời, throughput, dung lượng tạm |
| Decode/transform CPU-heavy | CPU time, heap, object allocation | Core CPU, CPU quota, allocation/GC |
| Gọi dịch vụ nhiều tầng | Nhiều pool và timeout | Nút thắt nhỏ nhất trên toàn chuỗi |
| Gửi message | Producer buffer, broker quota | Pending send, broker throughput, retry queue |

Một inner Publisher có thể giữ nhiều resource trong suốt lifecycle. Ví dụ, nếu transaction mở connection rồi chờ thêm một HTTP request chậm, connection DB vẫn có thể bị giữ. Không chỉ đếm số lời gọi HTTP; phải xem resource nào bị giữ và trong bao lâu.

Công thức thực dụng:

```text
C_local <= min(
    downstream_inflight_budget,
    connection_budget_per_pipeline,
    memory_budget,
    CPU_or_scheduler_budget,
    business_policy_limit
)
```

Đây là cách xác định trần ban đầu, không phải công thức dự đoán throughput. Sau đó còn phải xét số pipeline/request chạy song song để tính global capacity.

## 5. Ví dụ tính theo connection pool

Giả sử R2DBC pool có 40 connection:

- 6 connection dành làm headroom cho health check, tác vụ quản trị và biến động tải.
- 10 connection dự kiến được các luồng nghiệp vụ khác sử dụng.
- Phần ngân sách còn lại cho batch lookup là 24 connection.

Nếu một pipeline duy nhất tạo một query độc lập trên mỗi inner và mỗi inner giữ một connection, giới hạn ban đầu có thể là 24 hoặc thấp hơn. Nếu query có thể chạy lâu, bắt đầu ở 8–12 rồi đo sẽ an toàn hơn.

Nhưng nếu 20 request HTTP cùng lúc, mỗi request có `flatMap(..., 12)`, tổng nhu cầu lý thuyết có thể là 240 query. Local concurrency 12 không bảo vệ pool toàn cục 40 connection. Cần thêm bulkhead toàn cục hoặc chia ngân sách theo loại công việc.

```text
Pool capacity                    = 40
Operational reserve              = 6
Other workload budget            = 10
Maximum budget for this workload = 24

Per-request flatMap concurrency  = 4
Global bulkhead for this workload = 24
```

Khi đó, `flatMap` local = 4 giới hạn fan-out của từng request; global bulkhead = 24 giới hạn tổng hoạt động của nhóm workload.

### 5.1. Transaction-bound connection

Trong một reactive transaction R2DBC, nhiều query có thể dùng chung connection được bind trong Reactor Context. Một connection không mặc nhiên hỗ trợ nhiều query đồng thời độc lập. Driver/database có thể yêu cầu các thao tác tuần tự hoặc giới hạn concurrency trên cùng connection.

Nếu nhiều bước phải nằm trong cùng transaction và cùng connection, thường dùng:

```java
return commands.concatMap(repository::applyChange);
```

Không tăng `flatMap` concurrency lên 8 chỉ để chạy tám query cùng lúc trong một transaction. Nếu nghiệp vụ cho phép các transaction độc lập, có thể chạy song song, nhưng mỗi transaction tiêu thụ resource pool riêng và phải có global budget.

## 6. Ước lượng bằng thời gian và Little's Law

Little's Law mô tả quan hệ trung bình:

```text
L = λ × W
```

Trong đó L là số công việc trung bình đang in-flight, λ là throughput trung bình (công việc/giây), W là thời gian trung bình một công việc ở trong hệ thống (giây).

Ví dụ muốn xử lý 80 request/giây, latency trung bình 150 ms:

```text
L = 80 × 0.150 = 12 concurrent requests (average)
```

Điều này nói rằng để đạt throughput đó trong điều kiện ổn định, hệ thống có khoảng 12 request đang in-flight trung bình. Nó không có nghĩa đặt concurrency đúng 12 sẽ bảo đảm 80 request/giây. Còn phải xét tail latency, lỗi, pool wait, downstream capacity và độ biến động tải.

Quy trình an toàn:

1. Đo latency trung bình và p95/p99 ở tải đại diện.
2. Ước lượng số thao tác in-flight cần thiết để đạt throughput mục tiêu.
3. So sánh với connection/API/CPU/memory budget.
4. Bắt đầu thấp hơn ngưỡng tài nguyên, tăng dần trong load test.
5. Dừng tăng khi throughput không tăng nhưng latency, queue, timeout hoặc GC tăng.

Không dùng concurrency để bù cho downstream đã quá tải. Khi queue tăng và latency tăng, tăng C có thể làm tình trạng nặng hơn.

## 7. Chọn concurrency cho WebClient và API đối tác

Với WebClient, mỗi inner thường là một HTTP call:

```java
Flux<Product> products = productIds.flatMap(
        id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class),
        8,
        1);
```

Xem các giới hạn:

- Connection pool `maxConnections`.
- Pending acquire queue và `pendingAcquireTimeout`.
- Giới hạn in-flight của API đối tác.
- Rate quota theo API key/tenant.
- Response size, codec aggregation và memory.
- Connect/response timeout và deadline toàn nghiệp vụ.
- Retry/backoff khi đối tác trả lỗi transient.

Nếu pool có 20 connection nhưng nhiều luồng khác cũng dùng pool, không dành toàn bộ 20 slot cho pipeline này. Nếu đối tác chỉ cho 5 request đồng thời, concurrency của nhóm workload không vượt ngân sách 5 dù client pool có 100 connection.

Connection pool là một hàng rào ở transport, không thay thế concurrency limit trong business flow. Nếu pool queue không giới hạn hoặc quá dài, request có thể tích lũy và giữ nhiều state trước khi được cấp connection.

## 8. CPU-bound và blocking work

Nếu mapper thực hiện tính toán CPU nặng, concurrency cao hơn số core khả dụng thường không làm tính toán nhanh hơn. Nó có thể tăng context switching, allocation và GC. Cân nhắc `Schedulers.parallel()`/`ParallelFlux` hoặc `publishOn` với scheduler phù hợp, rồi benchmark theo CPU quota thực tế.

```java
Flux<Score> scores = ids.flatMap(
        id -> Mono.fromCallable(() -> expensiveScore(id))
                .subscribeOn(Schedulers.parallel()),
        4,
        1);
```

Nếu gọi JDBC blocking, filesystem blocking hoặc SDK đồng bộ, đừng chạy trực tiếp trên Netty event loop. Có thể cô lập bằng `Schedulers.boundedElastic()`:

```java
Flux<Value> values = ids.flatMap(
        id -> Mono.fromCallable(() -> blockingSdk.lookup(id))
                .subscribeOn(Schedulers.boundedElastic()),
        6,
        1);
```

Giới hạn 6 bảo vệ số tác vụ của pipeline này; scheduler vẫn có giới hạn thread/queue dùng chung. Nếu nhiều endpoint cùng dùng boundedElastic, cần xét global pressure. Không tăng concurrency đến hàng nghìn rồi để scheduler queue giữ hàng nghìn request chờ.

## 9. Prefetch và bộ nhớ

`prefetch` không phải concurrency thứ hai. Với `flatMap(mapper, C, P)`, Reactor có thể có tối đa C inner Publisher in-flight; mỗi inner có thể được yêu cầu trước tối đa P phần tử theo semantics của operator. Khi inner phát dữ liệu, operator có thể replenish demand theo cơ chế nội bộ.

Ước lượng bộ nhớ thô cho inner Publisher phát nhiều item:

```text
Approximate queued payload memory
    ≈ concurrency × prefetch × average item size
```

Ví dụ C=8, P=4, mỗi item đã decode trung bình 256 KiB:

```text
8 × 4 × 256 KiB = 8 MiB
```

Đây chỉ là ước lượng cho payload trong các queue tương ứng; chưa tính object overhead, outer queue, operator queue, decoder buffer, connection buffer, response aggregation và dữ liệu đang được business logic giữ.

Cách chọn:

- Inner là `Mono<T>` chỉ phát một item: prefetch thường ít ảnh hưởng hơn vì inner không phải stream dài.
- Inner là `Flux<T>` nhiều item: giảm prefetch nếu mỗi item lớn hoặc downstream chậm.
- Inner cần throughput cao và item nhỏ: có thể tăng prefetch sau khi đo.
- Payload lớn/không tin cậy: ưu tiên streaming và byte budget; không chỉ giảm prefetch rồi coi là đủ.

Trong nhiều Reactor inner operators, default prefetch phổ biến là 32, nhưng default có thể khác theo operator/version. Đặt tường minh khi memory profile quan trọng và kiểm tra Javadoc đúng Reactor version của ứng dụng.

## 10. Concurrency lồng nhau có thể nhân tải

Hai `flatMap` lồng nhau:

```java
Flux<Result> results = accounts.flatMap(
        account -> account.getOrders().flatMap(
                this::fetchDetails,
                5,
                1),
        8,
        1);
```

Trong trường hợp mỗi account có đủ order, pipeline có thể mở đến 8 × 5 = 40 inner detail calls cho một subscription. Đây là giới hạn lý thuyết của fan-out lồng nhau, không phải 8 hoặc 5 riêng lẻ.

Nếu mỗi HTTP request lại chạy pipeline trên và có 10 HTTP request đồng thời, nhu cầu tổng có thể tăng tới 400 detail calls. Hãy tính tất cả tầng fan-out và số request cha đang active.

Cách đơn giản hơn là gom các item thành một stream duy nhất và đặt giới hạn tại điểm gọi resource chung, hoặc dùng global bulkhead cho downstream. Khi không thể gom, ghi rõ budget của từng tầng và kiểm thử tải kết hợp.

## 11. Retry, timeout và error handling ảnh hưởng slot

### 11.1. Retry giữ inner slot trong thời gian retry

```java
Flux<Result> results = ids.flatMap(
        id -> fetch(id)
                .retryWhen(Retry.backoff(
                        2,
                        Duration.ofMillis(100))),
        8,
        1);
```

Inner Publisher chưa hoàn tất trong thời gian chờ retry, nên slot concurrency vẫn bị chiếm. Điều này thường hữu ích để không mở thêm quá nhiều công việc khi upstream đang lỗi. Nhưng retry có thể khuếch đại tải nếu không có backoff, jitter, giới hạn số lần và deadline.

Chỉ retry lỗi transient phù hợp. Với POST có side effect, cần idempotency key hoặc cơ chế deduplication; timeout không chứng minh đối tác chưa xử lý request.

### 11.2. Timeout và lỗi

```java
Flux<Result> results = ids.flatMap(
        id -> fetch(id)
                .timeout(Duration.ofSeconds(2)),
        8,
        1);
```

Khi inner timeout, nó phát error và `flatMap` mặc định fail-fast: lỗi có thể kết thúc outer sequence và cancel các inner còn lại. Nếu muốn xử lý lỗi theo từng item, đặt fallback trong mapper:

```java
Flux<Outcome> results = ids.flatMap(
        id -> fetch(id)
                .map(Outcome::success)
                .onErrorResume(error ->
                        Mono.just(Outcome.failure(id))),
        8,
        1);
```

Khi đó một item lỗi có thể trở thành `Outcome.failure` và các item khác tiếp tục. Đừng nuốt mọi lỗi một cách mù quáng; phân loại timeout, validation, 4xx, 5xx và lỗi không thể retry.

`flatMapDelayError(mapper, C, P)` cho phép trì hoãn phát error cho đến khi các inner/backlog hiện tại được xử lý theo semantics của operator. Nó hữu ích khi muốn thu thập nhiều lỗi, nhưng có thể tiếp tục tiêu thụ tài nguyên sau lỗi đầu tiên. Đây không phải cơ chế overload protection.

## 12. Backpressure và tính lazy của mapper

`flatMap` sử dụng demand để không mở vô hạn inner Publisher cùng lúc. Nhưng nguồn có thể là hot publisher, callback tự phát hoặc SDK không tuân thủ Reactive Streams. Khi nguồn không thể chậm lại, cần policy bounded buffer/drop/error và quota.

Mapper nên tạo công việc lazy:

```java
Flux<Result> results = ids.flatMap(
        id -> Mono.defer(() -> partnerClient.fetch(id)),
        8,
        1);
```

Nếu `partnerClient.fetch(id)` tự gửi request ngay khi được gọi thay vì khi subscribe, nó có thể khởi động side effect trước khi operator quản lý subscription. Kiểm tra contract của API/SDK; bọc `defer` không sửa được một SDK vốn đã thực hiện side effect trước khi trả Publisher.

`limitRate` điều chỉnh cách request theo lô ở upstream; nó không thay thế giới hạn số inner đang active. Với fan-out, chọn concurrency của `flatMap` tại đúng điểm tạo các thao tác con.

## 13. Đưa giới hạn vào configuration

Không hard-code số concurrency ở nhiều service. Đưa giá trị vào configuration theo workload:

```properties
app.partner.max-concurrency=8
app.partner.prefetch=1
app.database.batch-concurrency=4
app.database.batch-prefetch=1
```

Một class cấu hình có thể validate:

```java
@ConfigurationProperties(prefix = "app.partner")
@Validated
public record PartnerProperties(
        @Min(1) @Max(32) int maxConcurrency,
        @Min(1) @Max(16) int prefetch) {
}
```

Đây là snippet Spring Boot cần bật configuration properties scanning hoặc đăng ký bằng `@EnableConfigurationProperties`. Giá trị max phải được chọn theo capacity đã đo, không phải cứ đặt `@Max(32)` là 32 an toàn.

Khi thay cấu hình trong production, cần rollout có kiểm soát và theo dõi connection pool/latency. Đừng thay concurrency giữa tải cao mà không biết số pipeline đã tạo trước đó có giữ cấu hình cũ hay không.

## 14. Ví dụ Java 17+ chạy được: đo giới hạn active inner Publisher

Ví dụ độc lập dùng Reactor Core. Mỗi ID tạo một inner `Flux` phát ba phần kết quả với độ trễ nhỏ. Service đo số inner đang hoạt động và số lớn nhất quan sát được. Test xác nhận xử lý đủ dữ liệu nhưng không bao giờ vượt concurrency đã cấu hình.

**Cấu trúc project:**

```text
flatmap-concurrency-demo/
├── pom.xml
└── src/
    ├── main/java/demo/PartnerBatchService.java
    └── test/java/demo/PartnerBatchServiceTest.java
```

### 14.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>flatmap-concurrency-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Spring Boot parent quản lý phiên bản Reactor tương thích. Project dùng Java 17; không cần chạy HTTP server vì mục tiêu là kiểm tra semantics của `flatMap` trực tiếp.

### 14.2. PartnerBatchService.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;

public final class PartnerBatchService {

    private final int maxConcurrency;
    private final int prefetch;

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger maxObserved = new AtomicInteger();

    public PartnerBatchService(
            int maxConcurrency,
            int prefetch) {

        if (maxConcurrency < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrency must be positive");
        }
        if (prefetch < 1) {
            throw new IllegalArgumentException(
                    "prefetch must be positive");
        }

        this.maxConcurrency = maxConcurrency;
        this.prefetch = prefetch;
    }

    public Flux<Integer> fetchAll(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException(
                    "itemCount must not be negative");
        }

        return Flux.range(1, itemCount)
                .flatMap(
                        this::fetchThreeParts,
                        maxConcurrency,
                        prefetch);
    }

    private Flux<Integer> fetchThreeParts(int id) {
        return Flux.defer(() -> {
                    int now = active.incrementAndGet();
                    maxObserved.accumulateAndGet(
                            now, Math::max);

                    return Flux.range(1, 3)
                            .delayElements(
                                    Duration.ofMillis(10))
                            .map(part -> id * 10 + part);
                })
                .doFinally(signal ->
                        active.decrementAndGet());
    }

    public int activeCalls() {
        return active.get();
    }

    public int maxObservedConcurrency() {
        return maxObserved.get();
    }
}
```

Điểm quan trọng:

- `Flux.defer` chỉ tăng counter khi inner thực sự được subscribe.
- Mỗi inner đại diện cho một thao tác downstream và phát ba item.
- `flatMap` nhận `maxConcurrency` và `prefetch` từ constructor.
- `doFinally` giảm counter khi inner complete, error hoặc cancel.
- `maxObserved` là số active lớn nhất trong lần chạy, không phải cấu hình tự khai báo.

Trong ứng dụng thật, thay `Flux.range(...).delayElements(...)` bằng publisher từ WebClient, R2DBC hoặc SDK reactive. Không dùng `Thread.sleep` để mô phỏng I/O trong event loop.

### 14.3. PartnerBatchServiceTest.java

```java
package demo;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class PartnerBatchServiceTest {

    @Test
    void activeInnerPublishersNeverExceedConfiguredLimit() {
        int concurrencyLimit = 4;
        PartnerBatchService service =
                new PartnerBatchService(concurrencyLimit, 1);

        StepVerifier.create(service.fetchAll(20))
                .expectNextCount(60)
                .verifyComplete();

        assertThat(service.maxObservedConcurrency())
                .isGreaterThan(0)
                .isLessThanOrEqualTo(concurrencyLimit);

        assertThat(service.activeCalls()).isZero();
    }

    @Test
    void emptyInputDoesNotStartAnyInnerPublisher() {
        PartnerBatchService service =
                new PartnerBatchService(4, 1);

        StepVerifier.create(service.fetchAll(0))
                .verifyComplete();

        assertThat(service.maxObservedConcurrency())
                .isZero();

        assertThat(service.activeCalls()).isZero();
    }

    @Test
    void constructorRejectsInvalidLimits() {
        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalArgumentException.class,
                () -> new PartnerBatchService(0, 1));

        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalArgumentException.class,
                () -> new PartnerBatchService(4, 0));
    }
}
```

Chạy từ thư mục project bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** ba test PASS; Maven exit code `0`.

- Test đầu nhận 60 phần tử (20 inner × 3 item), xác nhận số inner active lớn nhất không vượt 4 và sau complete không còn inner active.
- Test thứ hai xác nhận input rỗng không tạo inner.
- Test thứ ba xác nhận cấu hình concurrency/prefetch không hợp lệ bị từ chối.

Không khẳng định `maxObservedConcurrency()` luôn bằng đúng 4; scheduler và timing có thể khiến số đo nhỏ hơn. Điều cần chứng minh là nó luôn nằm trong khoảng 1–4 khi có công việc.

## 15. Kiểm thử hệ thống thật và metrics

Test trên chứng minh một publisher tôn trọng giới hạn operator trong process. Nó chưa chứng minh database pool hoặc API đối tác không bị vượt tải khi nhiều request cùng chạy.

Một bộ integration/load test nên đo:

1. Số inner đang active theo từng workload.
2. Số connection đang dùng và pending acquire trong pool.
3. Số request đồng thời mà downstream quan sát.
4. Latency p50/p95/p99, throughput và error rate.
5. Số timeout, 429, 5xx, retry và cancellation.
6. Queue depth, heap, allocation rate và GC pause.
7. Hành vi khi nhiều HTTP request cha đồng thời.
8. Hành vi khi downstream chậm hoặc ngắt kết nối.
9. Hành vi khi một inner lỗi giữa batch.
10. Tổng tài nguyên sau khi request complete/cancel.

Dùng test server giả lập có giới hạn concurrency hoặc database test có pool size rõ. Nếu cần chứng minh global cap, chạy nhiều request cha đồng thời và đo tổng active operations tại resource dùng chung; test từng subscription riêng là chưa đủ.

| Dấu hiệu | Khả năng nguyên nhân | Hành động |
|---|---|---|
| Pool pending acquire tăng liên tục | C lớn hơn connection budget hoặc query quá chậm | Giảm C, đặt queue/acquire timeout, tối ưu query |
| Upstream trả 429 | Vượt quota hoặc rate limit | Giảm C nếu in-flight cao; thêm rate limiter nếu quota theo thời gian |
| Latency p95/p99 tăng nhưng throughput đứng | Downstream bão hòa/queueing | Giảm C, giảm queue, tìm bottleneck |
| Heap/GC tăng theo C × P | Buffer/inner output tích lũy | Giảm prefetch, payload size, dùng streaming |
| CPU 100% và throughput không tăng | CPU-bound hoặc serialization | Giảm cạnh tranh, profile CPU |
| Scheduler queue tăng | Blocking hoặc quá nhiều task | Loại blocking, giới hạn admission, kiểm tra scheduler |
| Timeout/retry tăng cùng lúc | Overload bị khuếch đại bởi retry | Giảm C, backoff+jitter, deadline và retry budget |
| Một request chiếm hết pool | Chỉ có local concurrency, thiếu global bulkhead | Đặt global cap và chia sẻ công bằng |

Theo dõi cả active và pending. Nếu chỉ xem số request thành công, bạn có thể bỏ qua queue đang tăng trước khi lỗi xuất hiện.

## 16. Quy trình điều chỉnh và lỗi thường gặp

Quy trình điều chỉnh:

1. Xác định resource: mỗi inner gọi DB, API, file hay CPU? Một inner giữ bao nhiêu resource và trong bao lâu?
2. Tìm capacity: pool size, downstream quota, scheduler limit, memory budget và phần dự trữ cho workload khác.
3. Tách local/global: chọn giới hạn mỗi request và bulkhead toàn hệ thống; tính fan-out lồng nhau.
4. Chọn C thấp ban đầu, ví dụ 2 hoặc 4.
5. Chọn P: inner Mono thường không cần prefetch lớn; inner Flux với payload lớn bắt đầu P thấp.
6. Load test: tăng dần số request cha, batch size và tốc độ đến; đo throughput cùng p95/p99.
7. Quan sát điểm bão hòa: nếu tăng C không tăng throughput nhưng queue/latency/GC tăng, quay về giá trị thấp hơn.
8. Thêm pool pending limit, acquire timeout, rate limiter, bulkhead, deadline và cancellation cleanup.
9. Test downstream 429/500/timeout, client cancel, retry và nhiều request đồng thời.
10. Đặt cấu hình riêng theo workload; không dùng một C cho mọi endpoint/backend.

Các lỗi thường gặp:

1. **Không truyền concurrency vào `flatMap`.** Default có thể không phù hợp capacity downstream; chọn tường minh khi gọi resource giới hạn.
2. **Nhầm concurrency với thread count.** Concurrency giới hạn inner subscription, không tạo thread riêng.
3. **Nhầm concurrency với rate limit.** Giới hạn in-flight không giới hạn số lần bắt đầu trong một giây.
4. **Tưởng local concurrency là global limit.** Mỗi request có subscription riêng; tổng tải có thể nhân theo số request.
5. **Quên fan-out lồng nhau.** Outer 8 × inner 5 có thể tạo 40 leaf operations.
6. **Đặt C bằng toàn bộ pool size.** Workload khác và vận hành cần connection reserve.
7. **Chỉ nhìn CPU.** I/O-bound service có thể bị giới hạn bởi pool/API, không phải core.
8. **Tăng C để sửa latency.** Nếu downstream đã bão hòa, queue và tail latency còn tăng.
9. **Bỏ qua prefetch.** Inner Flux có thể buffer nhiều item trên mỗi inner.
10. **Coi prefetch là tổng bộ nhớ.** Còn queue, decoder, object overhead và buffer ở các tầng khác.
11. **Dùng `flatMapSequential` mà không tính queue.** Inner sau có thể hoàn tất nhưng bị giữ chờ inner trước.
12. **Dùng `flatMap` khi side effect cần thứ tự.** Output và thứ tự thực thi không được bảo toàn như `concatMap`.
13. **Dùng `concatMap` cho mọi việc.** Tuần tự hóa có thể làm mất throughput khi các thao tác độc lập.
14. **Chạy JDBC blocking trên event loop.** Concurrency thấp không làm blocking call trở nên an toàn.
15. **Chạy query song song trên một transaction-bound connection.** Driver có thể không hỗ trợ; dùng tuần tự nếu cùng transaction.
16. **Không dùng `defer` với publisher cần lazy side effect.** Công việc có thể bắt đầu trước khi operator quản lý subscription.
17. **Retry không giới hạn.** Retry storm làm downstream quá tải hơn.
18. **Dùng `flatMapDelayError` như overload protection.** Nó trì hoãn lỗi, không giảm tải và có thể giữ nhiều công việc tiếp tục chạy.
19. **Nuốt mọi lỗi bằng `onErrorResume`.** Có thể che outage và tạo kết quả thành công giả.
20. **Không xử lý cancellation.** Inner đang giữ resource có thể bị bỏ dở nếu API không cleanup đúng.
21. **Dùng semaphore blocking trên event loop.** Có thể chặn cả event loop; dùng reactive bulkhead.
22. **Không đặt timeout cho pool acquire.** Queue chờ có thể tích lũy vô hạn.
23. **Chỉ test một request cha.** Không phát hiện global fan-out vượt capacity.
24. **Assert concurrency phải luôn đạt đúng C.** Timing/scheduler có thể khiến max quan sát nhỏ hơn; kiểm tra trần là contract quan trọng.
25. **Đổi C mà không đo p95/p99.** Throughput tăng nhẹ có thể đổi lấy tail latency xấu.
26. **Dùng một C chung cho DB, HTTP và CPU.** Mỗi resource có capacity và thời gian giữ khác nhau.
27. **Không giới hạn batch size đầu vào.** Concurrency có trần nhưng backlog source vẫn có thể quá lớn.
28. **Coi pool tự bảo vệ toàn bộ hệ thống.** Pool queue có thể chỉ chuyển overload thành thời gian chờ và timeout.

## 17. Checklist trước production

- Mapper tạo publisher lazy và không tự `subscribe()`?
- Mỗi inner dùng resource gì và giữ resource bao lâu?
- `concurrency` đã được đặt tường minh theo capacity?
- `prefetch` phù hợp số item và kích thước payload của inner?
- Cần `flatMap`, `flatMapSequential` hay `concatMap` theo yêu cầu thứ tự?
- Có phân biệt concurrency với rate limit?
- Có tính số HTTP request đồng thời và fan-out lồng nhau?
- Có global bulkhead/admission control cho pool/upstream dùng chung?
- Pool có max connection, pending queue và acquire timeout?
- Transaction-bound connection có bị query song song không phù hợp?
- CPU/blocking work có scheduler và quota riêng?
- Retry có bounded attempts, backoff, jitter, deadline và idempotency?
- Timeout/error/cancel có cleanup connection, buffer và file handle?
- Memory budget đã tính gần đúng C × P × payload size và các queue khác?
- Có metrics active, pending, pool usage, latency p95/p99, 429, timeout và GC?
- Load test có nhiều request cha đồng thời và downstream chậm?
- Test chứng minh không vượt concurrency cap nhưng không yêu cầu max phải luôn bằng C?
- Có kế hoạch giảm concurrency hoặc shed load khi downstream quá tải?

**Ghi nhớ:** `flatMap(mapper, C, P)` giới hạn số inner Publisher in-flight bằng C và điều chỉnh demand mỗi inner bằng P. C chỉ giới hạn **một subscription**; muốn bảo vệ pool dùng chung phải tính fan-out của nhiều request và đặt global bulkhead. Chọn C theo resource budget và latency đo được; dùng `concatMap` khi cần tuần tự, `flatMapSequential` khi cần output có thứ tự nhưng vẫn chấp nhận buffering. Concurrency không thay rate limit, timeout, pool cap hoặc overload policy. Đo active/pending/latency/GC dưới tải thực trước khi chốt cấu hình.

## Tài liệu tham khảo

- Project Reactor 3.7 — [Flux API: flatMap concurrency and prefetch](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Reference Guide: operators that change demand and prefetch](https://projectreactor.io/docs/core/3.8.1/reference/).
- Project Reactor — [ParallelFlux API and inner publisher concurrency](https://docs.spring.io/projectreactor/reactor-core/docs/current/api/reactor/core/publisher/ParallelFlux.html).
- Reactor Netty — [HTTP Client Connection Pool and pending acquire configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- Spring Framework — [WebClient: reactive HTTP client](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Boot 3.5 — [R2DBC connection configuration](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html).
- Spring Framework — [Reactive transaction management and Reactor Context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
