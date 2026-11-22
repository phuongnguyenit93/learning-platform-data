# Giới hạn đồng thời, thời hạn và số lần thử lại

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Thực hành tổng hợp  
**Mục tiêu:** Thiết kế luồng reactive có giới hạn số thao tác đồng thời, deadline rõ ràng và retry hữu hạn; phối hợp giới hạn từng request với connection pool và quota toàn hệ thống; tránh retry storm, duplicate side effect và giữ tài nguyên quá lâu.

## 1. Vì sao phải thiết kế ba chính sách cùng nhau?

Một service nhận 200 mã đơn hàng, gọi API đối tác cho từng mã rồi tổng hợp kết quả. Ba quyết định ảnh hưởng trực tiếp đến tải và độ tin cậy:

- **Concurrency:** tại một thời điểm, tối đa bao nhiêu request con được chạy?
- **Timeout/deadline:** một lần gọi được phép chờ bao lâu, và toàn bộ nghiệp vụ phải kết thúc trước thời điểm nào?
- **Retry:** lỗi nào được thử lại, tối đa bao nhiêu lần và chờ bao lâu giữa các lần?

Chỉ đặt một trong ba chính sách là chưa đủ. Concurrency cao nhưng không có timeout khiến inner Publisher bị treo và giữ slot. Timeout ngắn nhưng retry vô hạn có thể tạo vòng lặp request liên tục. Retry có backoff nhưng không có concurrency cap vẫn có thể tạo hàng nghìn lần thử đồng thời. Local concurrency nhỏ nhưng nhiều request cha cùng chạy có thể nhân tổng tải. Retry POST không idempotent có thể tạo giao dịch trùng khi response bị mất sau khi upstream đã xử lý thành công.

Một pipeline ổn định cần có **ngân sách tài nguyên**, **ngân sách thời gian** và **ngân sách thử lại** được xác định trước.

## 2. Mô hình xử lý tổng thể

```text
Incoming request
      |
      v
Validate batch size and caller quota
      |
      v
flatMap(mapper, concurrency, prefetch)
      |
      +---- Item A
      |       +-- attempt timeout
      |       +-- retry filter / backoff / jitter
      |       +-- per-item deadline
      |
      +---- Item B
      |       +-- attempt timeout
      |       +-- retry filter / backoff / jitter
      |       +-- per-item deadline
      |
      +---- Item C ...
      |
      v
Aggregate / map partial results
      |
      v
Batch deadline and response
```

`flatMap` giới hạn số inner Publisher đang in-flight trong một subscription. Mỗi inner có timeout và retry policy riêng. Nếu toàn batch cũng có deadline, phải đặt thêm giới hạn cho thời gian của toàn workflow. Những giới hạn này phục vụ các mục tiêu khác nhau.

## 3. Giới hạn concurrency ở điểm gọi tài nguyên

`Flux.flatMap(mapper, concurrency, prefetch)` có hai tham số quan trọng:

| Tham số | Ý nghĩa | Điều chỉnh |
|---|---|---|
| `concurrency` | Số inner Publisher tối đa được subscribe đồng thời trong một subscription | Số thao tác con in-flight |
| `prefetch` | Demand ban đầu được yêu cầu từ mỗi inner Publisher | Buffer/demand khi inner phát nhiều phần tử |

Ví dụ:

```java
Flux<Result> results = orderIds.flatMap(
        id -> partnerClient.fetch(id),
        8,
        1);
```

Tối đa tám inner Publisher được xử lý đồng thời trong subscription này. Đây không phải tám thread riêng. Với WebClient, inner thường là network I/O non-blocking; với R2DBC, chúng có thể giữ connection hoặc transaction resource.

`prefetch` không phải giới hạn số request đang chạy. Nó quan trọng hơn khi inner là `Flux` phát nhiều item; nếu mỗi inner là `Mono` chỉ phát một kết quả, prefetch thường ít ảnh hưởng hơn. Nhiều inner operators có default prefetch phổ biến là 32, nhưng cần kiểm tra Javadoc của đúng Reactor version.

### 3.1. Concurrency local và giới hạn toàn hệ thống

Giới hạn 8 chỉ áp dụng cho một subscription. Nếu 25 HTTP request cùng chạy và mỗi request tạo `flatMap(..., 8)`, tổng số thao tác con có thể tiến gần 200.

Phân biệt:

- **Local concurrency:** số inner tối đa của một pipeline.
- **Global bulkhead:** số thao tác tối đa của một workload trên toàn process hoặc cụm.
- **Connection pool cap:** số connection transport được cấp.
- **Rate limit:** số lần bắt đầu thao tác trong một đơn vị thời gian.

Một pool có 40 connection không đồng nghĩa một request được phép chiếm cả 40. Chia ngân sách cho health check, workload khác, tác vụ quản trị và headroom. Đặt giới hạn pending queue để quá tải được phát hiện sớm thay vì giữ hàng đợi không giới hạn.

### 3.2. Chọn C theo resource phía sau

Ví dụ pool có 40 connection: 6 connection dành làm headroom, 10 connection dành cho workload khác, còn 24 connection là ngân sách tối đa cho batch lookup.

Có thể bắt đầu với local concurrency 4 và global bulkhead 24, sau đó load test. Nếu có 20 request cha cùng lúc, local cap 4 vẫn có thể tạo 80 thao tác con; global cap mới bảo vệ tổng tải.

Không chọn C chỉ dựa vào số CPU core. WebClient có thể I/O-bound; database có thể bị giới hạn bởi connection hoặc query execution; CPU transform lại có giới hạn khác.

### 3.3. Tính fan-out lồng nhau

Nếu outer `flatMap` có concurrency 8 và inner `flatMap` có concurrency 5, một subscription có thể tạo tối đa khoảng 40 leaf operations khi mọi nhánh đều có đủ công việc.

Nếu 10 request cha cùng chạy, con số lý thuyết có thể lên đến 400. Hãy tính fan-out ở tất cả tầng và áp dụng bulkhead tại resource dùng chung.

### 3.4. Chọn operator theo thứ tự

- `flatMap`: cho phép inner chạy đồng thời, output có thể interleave.
- `flatMapSequential`: subscribe inner song song nhưng giữ thứ tự output; có thể buffer kết quả của inner hoàn thành sớm.
- `concatMap`: chỉ chạy một inner tại một thời điểm, giữ thứ tự.

Nếu các lệnh cập nhật phụ thuộc thứ tự hoặc dùng cùng một transaction-bound connection không hỗ trợ truy vấn song song, cân nhắc `concatMap`. Nếu công việc độc lập, `flatMap` thường tận dụng tài nguyên tốt hơn.

## 4. Timeout: giới hạn một lần thử và toàn bộ nghiệp vụ

Một outbound HTTP call có thể chờ ở DNS resolution, connection pool acquire, TCP connect, TLS handshake hoặc proxy tunnel, gửi request, đọc response, decode body và xử lý kết quả. Không có một timeout duy nhất mô tả tất cả giai đoạn.

| Giai đoạn | API/cấu hình | Ý nghĩa |
|---|---|---|
| Chờ connection pool | `pendingAcquireTimeout` | Thời gian tối đa chờ connection |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` | Thời gian thiết lập TCP |
| TLS | `handshakeTimeout` | Thời gian hoàn thành TLS handshake |
| DNS | Resolver query timeout | Giới hạn tra cứu hostname |
| Response | `HttpClient.responseTimeout` | Giới hạn chờ/đọc response theo semantics transport |
| Toàn publisher | Reactor `timeout(Duration)` | Deadline của publisher được bọc |

Ví dụ cấu hình Reactor Netty:

```java
ConnectionProvider pool =
        ConnectionProvider.builder("partner")
                .maxConnections(24)
                .pendingAcquireMaxCount(48)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .build();

HttpClient httpClient = HttpClient.create(pool)
        .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                1_000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient partnerClient = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://partner.example.org")
        .build();
```

Đây là snippet cấu hình, cần các import Reactor Netty, Netty và Spring WebFlux. `ConnectionProvider` tùy chỉnh có vòng đời riêng; ứng dụng production phải dispose theo lifecycle của Spring bean. Không tạo pool mới cho từng request.

### 4.1. Timeout của từng attempt

Một attempt nên có timeout hữu hạn:

```java
Mono<Result> oneAttempt =
        partnerClient.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .bodyToMono(Result.class)
                .timeout(Duration.ofSeconds(2));
```

Timeout giúp giải phóng subscription khi upstream không phản hồi trong ngân sách. Tuy nhiên timeout không chứng minh upstream chưa xử lý request. Server có thể đã commit nhưng response bị mất.

### 4.2. Deadline cho một item, bao gồm cả retry

Giả sử mỗi attempt tối đa 800 ms, retry tối đa hai lần và backoff là 100 ms rồi 200 ms. Tổng thời gian tối đa lý thuyết:

```text
3 × 800 ms + 100 ms + 200 ms = 2,700 ms
```

Cộng thêm scheduling và overhead. Có thể đặt deadline tổng 3 giây cho item:

```java
Mono<Result> callOne(String id) {
    return Mono.defer(() -> callPartner(id))
            .timeout(Duration.ofMillis(800))
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(3));
}
```

Timeout đầu nằm **bên trong retry**, nên mỗi attempt có ngân sách 800 ms. Timeout cuối nằm **bên ngoài retry**, nên toàn bộ chuỗi attempt và backoff phải kết thúc trong 3 giây.

Nếu chỉ đặt timeout sau retry, 3 giây là ngân sách chung; một attempt có thể tiêu hết phần lớn thời gian và không còn cơ hội cho retry tiếp theo:

```java
return Mono.defer(() -> callPartner(id))
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(3));
```

### 4.3. Deadline của cả batch

Nếu batch hữu hạn và có thể aggregate với kích thước giới hạn, có thể đặt deadline cho `Mono` tổng hợp:

```java
Mono<List<Result>> batch =
        ids.flatMap(this::callOne, 8, 1)
                .collectList()
                .timeout(Duration.ofSeconds(8));
```

`collectList()` giữ toàn bộ kết quả trong bộ nhớ, chỉ dùng khi batch size có giới hạn. Với batch lớn hoặc stream dài, xử lý theo lô hoặc phát kết quả từng phần; không gom một stream vô hạn.

Lưu ý: `Flux.timeout(Duration)` thường giới hạn **khoảng im lặng giữa các tín hiệu**, không phải tổng lifetime của một stream nhiều phần tử. Với `Mono` một kết quả, timeout thường biểu đạt deadline của lần gọi đó. Với SSE/stream dài, cần idle timeout/heartbeat riêng và deadline tuyệt đối nếu nghiệp vụ yêu cầu.

### 4.4. Timeout tầng transport không thay deadline nghiệp vụ

`responseTimeout` bảo vệ giai đoạn đọc response của Reactor Netty; nó không thay thế deadline toàn chuỗi. Ngược lại, `Mono.timeout` tổng thể có thể hủy thao tác nhưng không cho biết chính xác đang chờ pool, connect hay response.

Cấu hình timeout theo tầng để lỗi có thể chẩn đoán được. Đảm bảo deadline của downstream không dài hơn deadline của request cha; nếu request cha chỉ còn 500 ms thì không nên bắt đầu attempt mới có timeout 2 giây.

## 5. Retry: chỉ thử lại lỗi có khả năng hồi phục

Retry phù hợp khi lỗi có tính tạm thời và lần gọi lại có khả năng thành công. Nó không phải cách xử lý mọi exception.

| Nhóm lỗi | Chính sách thường dùng |
|---|---|
| Connection reset, lỗi mạng tạm thời | Có thể retry hữu hạn |
| HTTP 502/503/504 | Có thể retry theo policy và deadline |
| HTTP 429 | Tuân thủ `Retry-After` hoặc quota; không retry dồn dập |
| Timeout | Chỉ retry khi thao tác an toàn/idempotent và còn deadline |
| HTTP 400/401/403 | Thường không retry |
| Validation/domain error | Không retry |
| DB constraint violation | Không retry mù quáng |
| Bug lập trình, serialization lỗi | Không retry để che lỗi |

Cần phân loại exception cụ thể. Một `WebClientResponseException` có thể chứa 404, 429 hoặc 503; không retry tất cả status chỉ vì chúng cùng một class.

### 5.1. Số lần thử lại khác tổng số attempt

Trong Reactor:

```java
Retry.backoff(2, Duration.ofMillis(100))
```

Số 2 là số lần **retry sau lần gọi đầu tiên**, nên tổng số attempt tối đa là 3.

| Lần | Hành động |
|---:|---|
| 1 | Gọi ban đầu |
| 2 | Retry lần 1 sau backoff |
| 3 | Retry lần 2 sau backoff |
| Sau đó | Phát lỗi cuối nếu vẫn thất bại |

Tên biến nên rõ như `maxRetries`, tránh đặt `maxAttempts=2` rồi truyền trực tiếp vào `Retry.backoff` và hiểu sai tổng số lần gọi.

### 5.2. Exponential backoff và jitter

Không retry ngay lập tức theo vòng lặp. Khi nhiều client cùng gặp lỗi, retry tức thời có thể tạo **thundering herd**: tất cả cùng gọi lại một thời điểm và tiếp tục làm upstream quá tải.

Exponential backoff tăng khoảng chờ theo từng lần retry. Jitter thêm độ ngẫu nhiên để phân tán thời điểm gọi lại.

```java
Retry retryPolicy = Retry.backoff(
                2,
                Duration.ofMillis(100))
        .maxBackoff(Duration.ofMillis(500))
        .jitter(0.5)
        .filter(this::isTransientFailure)
        .onRetryExhaustedThrow(
                (spec, signal) -> signal.failure());
```

`Retry.backoff` nhận số retry tối đa và backoff tối thiểu. `maxBackoff` giới hạn thời gian chờ tăng lên; `jitter` giúp tránh đồng bộ retry. `filter` chỉ cho phép lỗi transient. Khi hết retry, ví dụ trên phát lại lỗi gốc để tầng gọi xử lý.

Trong test cần thời gian xác định, có thể đặt `.jitter(0d)` và dùng virtual time. Trong production, jitter hữu ích khi nhiều instance có thể retry cùng lúc.

### 5.3. Lọc lỗi trước khi retry

Ví dụ khung phân loại:

```java
boolean isTransientFailure(Throwable error) {
    if (error instanceof TimeoutException) {
        return true;
    }

    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();
        return status == 502
                || status == 503
                || status == 504;
    }

    return error instanceof IOException;
}
```

Đây là snippet cần imports và policy domain cụ thể. Không tự động coi 429 là retry giống 503; nên đọc `Retry-After`, áp quota và giới hạn thời gian chờ. Cũng không retry 401/403 nếu chưa có cơ chế refresh credential rõ ràng.

## 6. Đặt retry ở đúng ranh giới của flatMap

Đây là quyết định quan trọng để tránh chạy lại cả batch ngoài ý muốn.

**Retry riêng từng item:**

```java
Flux<Result> results = ids.flatMap(
        id -> Mono.defer(() -> callPartner(id))
                .timeout(Duration.ofSeconds(2))
                .retryWhen(retryPolicy),
        8,
        1);
```

Mỗi item có retry policy riêng. Một item lỗi không nhất thiết làm các item khác chạy lại; tuy nhiên mặc định lỗi cuối của một inner có thể làm `flatMap` kết thúc bằng error và cancel các inner còn lại.

**Retry toàn bộ batch:**

```java
Flux<Result> results = ids.flatMap(
        this::callPartner,
        8,
        1)
        .retryWhen(retryPolicy);
```

Nếu một item phát error, `retryWhen` ở ngoài có thể subscribe lại toàn bộ Flux nguồn. Các item đã thành công trước đó có thể được gọi lại, đặc biệt nếu nguồn là cold Publisher. Với write side effect, điều này có thể tạo dữ liệu trùng.

Chỉ retry cả batch khi nguồn và toàn bộ side effect được thiết kế để chạy lại an toàn, hoặc khi có checkpoint/deduplication phù hợp. Trong nhiều batch API, retry per item là ranh giới rõ hơn.

### 6.1. Retry giữ slot concurrency trong thời gian backoff

Khi retry nằm bên trong mapper, inner Publisher chưa hoàn tất trong lúc chờ backoff. Vì vậy slot của `flatMap` vẫn được giữ. C vẫn giới hạn số item đang được xử lý, kể cả item đang chờ retry.

Ưu điểm: không mở vô hạn item mới trong khi một nhóm item đang lỗi. Nhược điểm: nếu nhiều inner cùng backoff, throughput batch giảm vì các slot đang được giữ.

Không cố giải phóng slot bằng cách đẩy retry vào queue không giới hạn. Nếu cần tách retry scheduling khỏi request flow, phải có queue bounded, global retry budget và admission control riêng.

### 6.2. Không retry nhiều tầng một cách vô thức

Nếu gateway retry 3 lần, service retry 3 lần và SDK retry 3 lần, số attempt tới upstream có thể nhân lên tới 27 (3 × 3 × 3), nếu mỗi lớp định nghĩa 3 là tổng attempt.

Chọn một tầng sở hữu retry chính, hoặc ghi rõ ngân sách mỗi tầng. Tính tổng attempt và tổng deadline xuyên suốt toàn bộ chuỗi.

## 7. Retry và tính idempotent

Timeout thường tạo ra kết quả không chắc chắn: client không nhận response, nhưng upstream có thể đã xử lý thành công. Nếu client gửi lại lệnh tạo đơn hàng hoặc thanh toán, side effect có thể xảy ra lần thứ hai.

Các biện pháp:

- Dùng idempotency key duy nhất cho một thao tác nghiệp vụ.
- Lưu kết quả theo key ở phía server và trả lại kết quả cũ khi nhận request trùng.
- Có unique constraint hoặc deduplication record ở database.
- Chỉ retry POST/command khi contract hỗ trợ idempotency.
- Phân biệt lỗi trước khi gửi request với lỗi sau khi upstream có thể đã nhận.
- Không đổi idempotency key giữa các lần retry của cùng một nghiệp vụ.

Retry không tự biến thao tác không idempotent thành an toàn. Với event/message delivery, thiết kế consumer idempotent và chấp nhận at-least-once nếu đó là semantics thực tế.

## 8. Deadline phải được chia sẻ xuyên suốt workflow

Một request cha có deadline 5 giây. Nếu service A dùng hết 4 giây rồi gọi service B với timeout mặc định 5 giây, toàn workflow có thể kéo dài 9 giây hoặc lâu hơn.

Thiết kế deadline:

1. Tạo hoặc nhận deadline ở boundary tin cậy.
2. Tính thời gian còn lại trước mỗi downstream call.
3. Dùng timeout của attempt không vượt quá phần ngân sách còn lại.
4. Không bắt đầu retry mới nếu backoff và attempt tiếp theo không còn đủ thời gian.
5. Truyền deadline/remaining budget qua metadata hoặc context theo contract nội bộ.
6. Ghi nhận timeout stage để biết ngân sách cạn ở đâu.

Công thức ước lượng cho một item:

```text
T_item_max ≈
    attempts × attempt_timeout
    + sum(backoff_delays)
    + local_queue_and_scheduling_overhead
```

Nếu pool acquire, connect và response timeout đều nằm bên trong attempt, đừng cộng chúng thêm lần nữa khi tính tổng. Hãy xác định rõ timeout nào lồng trong timeout nào để tránh đếm trùng ngân sách.

Với batch, thời gian hoàn tất phụ thuộc số item, concurrency, latency phân phối và retry. Không lấy `itemCount × timeout` làm deadline mặc định; load test và SLA mới quyết định.

## 9. Error handling sau khi retry hết

**Fail fast:** để lỗi cuối kết thúc batch khi mọi kết quả đều bắt buộc.

```java
return ids.flatMap(this::callWithRetry, 8, 1);
```

**Kết quả từng item:** chuyển lỗi thành một kiểu kết quả domain rõ ràng để các item khác tiếp tục.

```java
return ids.flatMap(
        id -> callWithRetry(id)
                .map(value -> ItemResult.success(id, value))
                .onErrorResume(error ->
                        Mono.just(ItemResult.failure(
                                id, classify(error)))),
        8,
        1);
```

`flatMapDelayError` có thể trì hoãn phát lỗi cho đến khi các inner khác được xử lý theo semantics của operator. Nó không phải overload protection và có thể tiếp tục giữ resource sau lỗi đầu tiên.

Không dùng `onErrorResume(error -> Mono.empty())` cho mọi exception. Làm vậy có thể biến lỗi mất dữ liệu thành batch “thành công” nhưng thiếu item. Kết quả partial phải có status/error code để caller biết item nào thất bại.

## 10. Cancellation và cleanup

Timeout hoặc client disconnect có thể phát cancellation xuống pipeline. Reactor có thể hủy inner Publisher và timer đang chờ, nhưng không thể bảo đảm một HTTP side effect đã gửi sẽ được upstream hoàn tác.

Mỗi inner cần cleanup đúng lifecycle:

- Release connection/buffer/file handle khi complete, error hoặc cancel.
- Không tự gọi `subscribe()` để tách công việc khỏi request.
- Dùng `using`/`usingWhen` cho resource có lifecycle.
- Không retry cancellation; cancellation không phải lỗi `onError`.
- Với thao tác có side effect, kiểm tra idempotency và trạng thái nghiệp vụ trước khi retry.
- Không giữ transaction hoặc DB connection trong khi chờ backoff lâu nếu có thể thiết kế lại boundary.

`doFinally` hữu ích để quan sát complete/error/cancel, nhưng cleanup resource phải dùng API ownership phù hợp; log callback không thay thế việc đóng resource.

## 11. Metrics để điều chỉnh concurrency, timeout và retry

| Metric | Điều cần phát hiện |
|---|---|
| Active inner calls | Mức concurrency thực tế |
| Pending pool acquire | Queue chờ connection |
| Connection active/idle/max | Pool có bị bão hòa không |
| Attempt count theo loại lỗi | Retry có đang khuếch đại tải |
| Retry exhausted | Số item thất bại sau retry |
| Attempt latency và total item latency | Timeout nằm ở attempt hay toàn item |
| Timeout theo stage | Pool, connect, TLS, response hay deadline |
| HTTP 429/5xx | Quota và tình trạng upstream |
| Cancellation count | Client bỏ request hoặc timeout |
| p50/p95/p99 | Tail latency khi tăng C |
| Queue depth, heap, GC | Buffer và backlog có tăng không |

Không đưa order ID, email, token hoặc raw URL vào metric label. Dùng route/workload/status/error category có cardinality hữu hạn.

Nếu tăng C mà throughput không tăng nhưng pending queue, p99 và retry tăng, giảm concurrency và tìm bottleneck. Retry không nên được đánh giá chỉ bằng tỷ lệ request cuối cùng thành công; phải nhìn cả số attempt và tải phát sinh.

## 12. Ví dụ Java 17+ chạy được: bounded concurrency + retry + timeout

Ví dụ dùng Reactor Core, Java 17 và Maven. Một service nhận `Function<String, Mono<String>>` đại diện cho client downstream. Mỗi item có timeout cho từng attempt, retry hữu hạn với backoff, và deadline tổng cho item. `flatMap` giới hạn số item được xử lý cùng lúc.

**Cấu trúc project:**

```text
reactive-reliability-demo/
├── pom.xml
└── src/
    ├── main/java/demo/ResilientBatchService.java
    └── test/java/demo/ResilientBatchServiceTest.java
```

### 12.1. pom.xml

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
    <artifactId>reactive-reliability-demo</artifactId>
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

Spring Boot parent quản lý phiên bản Reactor tương thích với dòng Boot 3.5. Project không cần HTTP server vì trọng tâm là policy của publisher; trong ứng dụng thật, `remoteCall` sẽ gọi WebClient/R2DBC hoặc SDK reactive.

### 12.2. ResilientBatchService.java

```java
package demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class ResilientBatchService {

    private final Function<String, Mono<String>> remoteCall;
    private final int concurrency;
    private final int prefetch;
    private final Duration attemptTimeout;
    private final Duration itemDeadline;
    private final Retry retryPolicy;

    private final AtomicInteger activeAttempts =
            new AtomicInteger();

    private final AtomicInteger maxObservedAttempts =
            new AtomicInteger();

    public ResilientBatchService(
            Function<String, Mono<String>> remoteCall,
            int concurrency,
            int prefetch,
            Duration attemptTimeout,
            Duration itemDeadline,
            Retry retryPolicy) {

        if (concurrency < 1 || prefetch < 1) {
            throw new IllegalArgumentException(
                    "concurrency and prefetch must be positive");
        }
        if (attemptTimeout.isZero() || attemptTimeout.isNegative()
                || itemDeadline.isZero() || itemDeadline.isNegative()) {
            throw new IllegalArgumentException(
                    "timeouts must be positive");
        }

        this.remoteCall = remoteCall;
        this.concurrency = concurrency;
        this.prefetch = prefetch;
        this.attemptTimeout = attemptTimeout;
        this.itemDeadline = itemDeadline;
        this.retryPolicy = retryPolicy;
    }

    public Mono<String> fetchOne(String id) {
        return Mono.defer(() -> remoteCall.apply(id))
                .doOnSubscribe(subscription -> {
                    int current = activeAttempts.incrementAndGet();
                    maxObservedAttempts.accumulateAndGet(
                            current, Math::max);
                })
                .doFinally(signal ->
                        activeAttempts.decrementAndGet())
                .timeout(attemptTimeout)
                .retryWhen(retryPolicy)
                .timeout(itemDeadline);
    }

    public Flux<String> fetchAll(List<String> ids) {
        return Flux.fromIterable(ids)
                .flatMap(this::fetchOne, concurrency, prefetch);
    }

    public int activeAttempts() {
        return activeAttempts.get();
    }

    public int maxObservedAttempts() {
        return maxObservedAttempts.get();
    }
}
```

Các ranh giới quan trọng:

- `Mono.defer` gọi `remoteCall` lại ở mỗi subscription/attempt; nguồn phải lazy để không gửi request trước khi được subscribe.
- `doOnSubscribe` tăng counter cho từng attempt, còn `doFinally` giảm khi complete/error/cancel.
- `timeout(attemptTimeout)` nằm trước `retryWhen`, nên từng attempt có deadline riêng.
- `retryWhen(retryPolicy)` chỉ retry lỗi policy cho phép.
- `timeout(itemDeadline)` nằm sau retry, nên bao gồm toàn bộ attempt và backoff.
- `flatMap(..., concurrency, prefetch)` giới hạn số inner item của một subscription.

Counter đo attempt đang thực hiện ở downstream; trong khoảng backoff, attempt trước đã kết thúc và counter giảm, nhưng inner item vẫn chưa hoàn tất nên slot `flatMap` vẫn được giữ.

### 12.3. ResilientBatchServiceTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.assertj.core.api.Assertions.assertThat;

class ResilientBatchServiceTest {

    private Retry retryPolicy() {
        return Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(200))
                .jitter(0d)
                .filter(error ->
                        error instanceof TransientRemoteException)
                .onRetryExhaustedThrow(
                        (spec, signal) -> signal.failure());
    }

    @Test
    void batchNeverExceedsConfiguredActiveConcurrency() {
        ResilientBatchService service =
                new ResilientBatchService(
                        id -> Mono.delay(Duration.ofMillis(20))
                                .thenReturn("ok-" + id),
                        3,
                        1,
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(3),
                        retryPolicy());

        java.util.List<String> ids =
                java.util.stream.IntStream.rangeClosed(1, 20)
                        .mapToObj(Integer::toString)
                        .toList();

        StepVerifier.create(service.fetchAll(ids))
                .expectNextCount(20)
                .verifyComplete();

        assertThat(service.maxObservedAttempts())
                .isGreaterThan(0)
                .isLessThanOrEqualTo(3);

        assertThat(service.activeAttempts()).isZero();
    }

    @Test
    void transientFailureRetriesAndThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() -> {
                    ResilientBatchService service =
                            new ResilientBatchService(
                                    id -> Mono.defer(() -> {
                                        int attempt =
                                                attempts.incrementAndGet();
                                        if (attempt < 3) {
                                            return Mono.error(
                                                    new TransientRemoteException());
                                        }
                                        return Mono.just("success");
                                    }),
                                    2,
                                    1,
                                    Duration.ofSeconds(2),
                                    Duration.ofSeconds(5),
                                    retryPolicy());

                    return service.fetchOne("order-A");
                })
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("success")
                .verifyComplete();

        assertThat(attempts).hasValue(3);
    }

    @Test
    void nonRetryableFailureIsAttemptedOnlyOnce() {
        AtomicInteger attempts = new AtomicInteger();

        ResilientBatchService service =
                new ResilientBatchService(
                        id -> Mono.defer(() -> {
                            attempts.incrementAndGet();
                            return Mono.error(
                                    new IllegalArgumentException("invalid order"));
                        }),
                        2,
                        1,
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(3),
                        retryPolicy());

        StepVerifier.create(service.fetchOne("bad-order"))
                .expectError(IllegalArgumentException.class)
                .verify();

        assertThat(attempts).hasValue(1);
    }

    @Test
    void totalItemDeadlineIncludesTheAttempt() {
        StepVerifier.withVirtualTime(() -> {
                    ResilientBatchService service =
                            new ResilientBatchService(
                                    id -> Mono.delay(Duration.ofSeconds(10))
                                            .thenReturn("too-late"),
                                    1,
                                    1,
                                    Duration.ofSeconds(8),
                                    Duration.ofSeconds(2),
                                    retryPolicy());

                    return service.fetchOne("slow-order");
                })
                .thenAwait(Duration.ofSeconds(2))
                .expectError(TimeoutException.class)
                .verify();
    }

    @Test
    void cancellationReleasesActiveAttemptCounter() {
        ResilientBatchService service =
                new ResilientBatchService(
                        id -> Mono.never(),
                        1,
                        1,
                        Duration.ofSeconds(10),
                        Duration.ofSeconds(15),
                        retryPolicy());

        StepVerifier.create(service.fetchOne("cancel-me"))
                .thenCancel()
                .verify();

        assertThat(service.activeAttempts()).isZero();
    }
}

final class TransientRemoteException extends RuntimeException {
}
```

Chạy từ thư mục project với JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả logic mong đợi:** năm test PASS và Maven exit code 0.

| Test | Điều chứng minh |
|---|---|
| `batchNeverExceedsConfiguredActiveConcurrency` | 20 item hoàn tất, số attempt active không vượt C=3 |
| `transientFailureRetriesAndThenSucceeds` | Hai lỗi transient đầu được retry, lần thứ ba thành công |
| `nonRetryableFailureIsAttemptedOnlyOnce` | Lỗi validation không bị retry |
| `totalItemDeadlineIncludesTheAttempt` | Deadline tổng kết thúc item chậm bằng `TimeoutException` |
| `cancellationReleasesActiveAttemptCounter` | Cancel giải phóng counter attempt |

`Retry.backoff(2, ...)` có tối đa hai retry sau lần gọi đầu, nên test transient mong đợi tổng cộng ba lần gọi. Test virtual time tạo service trong supplier để retry scheduler được thiết lập trong ngữ cảnh virtual time. Không khẳng định thời gian build hoặc thứ tự log cố định.

## 13. Ví dụ cấu hình Reactor Netty trong Spring WebClient

Một cấu hình production cần pool bounded, pending queue bounded và các timeout transport rõ:

```java
@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerPool() {
        return ConnectionProvider.builder("partner")
                .maxConnections(24)
                .pendingAcquireMaxCount(48)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .build();
    }

    @Bean
    WebClient partnerWebClient(
            ConnectionProvider partnerPool,
            WebClient.Builder builder) {

        HttpClient httpClient =
                HttpClient.create(partnerPool)
                        .option(
                                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                1_000)
                        .responseTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("https://partner.example.org")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Đây là snippet Spring cần imports tương ứng. `destroyMethod="dispose"` giải phóng custom pool khi bean context đóng. Hãy kiểm tra API lifecycle theo Reactor Netty version được Boot quản lý.

Pool size 24 chỉ là ví dụ. Nếu `flatMap` local concurrency là 8 nhưng 10 request cha cùng chạy, pool có thể nhận tới 80 yêu cầu; pool sẽ tạo tối đa 24 connection và phần còn lại chờ queue hoặc timeout. Pool cap không thay global bulkhead vì nó có thể chỉ biến overload thành pending queue.

## 14. Những lỗi thường gặp

1. **Chỉ đặt concurrency mà không có timeout.** Inner treo giữ slot và resource lâu.
2. **Chỉ đặt timeout mà không có retry budget.** Caller có thể retry liên tục và tạo retry storm.
3. **Retry vô hạn.** Tăng tải đúng lúc upstream đang gặp sự cố.
4. **Nhầm maxRetries với tổng attempts.** `Retry.backoff(2, ...)` là hai lần retry cộng lần đầu.
5. **Retry tất cả exception.** Validation, 401/403 và bug không tự hồi phục.
6. **Retry HTTP 429 ngay lập tức.** Có thể vi phạm quota; cần tôn trọng `Retry-After`.
7. **Không dùng jitter.** Nhiều instance retry đồng thời sau cùng một backoff.
8. **Đặt timeout ngoài retry nhưng tưởng đó là timeout mỗi attempt.** Timeout đó là ngân sách chung cho cả chuỗi.
9. **Đặt timeout trong retry nhưng thiếu deadline tổng.** Nhiều attempt và backoff có thể kéo dài quá SLA.
10. **Đặt retry ngoài toàn batch.** Một item lỗi có thể làm cả nguồn cold chạy lại, lặp side effect đã thành công.
11. **Retry POST không idempotency.** Có thể tạo đơn hàng/thanh toán trùng.
12. **Không tính backoff vào deadline.** Attempt còn đủ thời gian riêng nhưng toàn item đã hết ngân sách.
13. **Retry ở nhiều tầng.** Gateway, service và SDK nhân số lần gọi.
14. **Tăng C để chữa timeout.** Downstream bão hòa có thể tệ hơn.
15. **Dùng local concurrency như global cap.** Nhiều request cha nhân tổng fan-out.
16. **Đặt C bằng toàn bộ connection pool.** Không còn headroom cho workload khác.
17. **Pending acquire queue không giới hạn.** Overload biến thành backlog dài và tăng memory.
18. **Dùng `Flux.timeout(Duration)` như deadline tuyệt đối.** Với Flux nhiều item, nó thường là idle timeout giữa tín hiệu.
19. **Dùng `collectList()` cho batch không giới hạn.** Tích lũy toàn bộ kết quả vào heap.
20. **Không giải phóng resource khi cancel.** Timeout/client disconnect có thể để lại connection/file/buffer.
21. **Coi cancel đồng nghĩa upstream rollback.** Side effect có thể đã commit.
22. **Không phân biệt timeout stage.** Pool, DNS, TCP, TLS và response có nguyên nhân khác nhau.
23. **Retry trong lúc giữ transaction/connection không cần thiết.** Resource có thể bị chiếm trong backoff.
24. **Không đo attempt count.** Tỷ lệ success cuối cùng có thể che tải retry rất lớn.
25. **Không test nhiều request cha cùng lúc.** Local cap pass nhưng global resource vẫn quá tải.

## 15. Quy trình chọn thông số

1. Xác định downstream: DB, HTTP partner, broker hay CPU.
2. Tính ngân sách connection, quota, memory và CPU; giữ headroom cho workload khác.
3. Chọn local concurrency thấp ban đầu và global bulkhead phù hợp.
4. Chọn prefetch theo kiểu inner và kích thước payload.
5. Đặt timeout riêng cho pool acquire, connect, TLS và response.
6. Đặt attempt timeout và deadline tổng cho item.
7. Chọn số retry nhỏ, hữu hạn; lọc transient errors.
8. Chọn exponential backoff, max backoff và jitter.
9. Kiểm tra idempotency trước khi retry side-effecting operation.
10. Load test với nhiều request cha, downstream chậm, 429/5xx, timeout và cancellation.
11. Quan sát active/pending, attempt count, latency p95/p99, pool, heap và GC.
12. Điều chỉnh một tham số mỗi lần và ghi lại kết quả.

Một bộ cấu hình tốt không nhất thiết tối đa throughput trong benchmark ngắn. Nó phải giữ latency và resource headroom ổn định khi downstream chậm hoặc lỗi.

## 16. Checklist trước production

- `flatMap` có concurrency tường minh tại điểm gọi resource giới hạn?
- Đã phân biệt local cap, global bulkhead, pool cap và rate limit?
- Có tính fan-out lồng nhau và số request cha đồng thời?
- Pool có max connection, pending queue hữu hạn và acquire timeout?
- Mỗi attempt có timeout hữu hạn?
- Toàn item có deadline bao gồm retry/backoff?
- Deadline downstream có tôn trọng thời gian còn lại của request cha?
- `Retry.backoff` có max retries hữu hạn, max backoff và jitter?
- Chỉ retry lỗi transient được phân loại rõ?
- 429/503 có xử lý quota/`Retry-After` phù hợp?
- Retry được đặt per item hay whole batch có chủ đích?
- Side effect có idempotency key/deduplication?
- Có tránh retry lồng nhau ở gateway/service/SDK?
- Cancellation/error/timeout giải phóng resource đúng lifecycle?
- Có phân biệt Mono deadline với Flux inter-signal timeout?
- Có test concurrency cap, transient retry, non-retryable error, deadline và cancellation?
- Có load test nhiều request cha và downstream chậm?
- Có metrics active/pending, attempt, retry exhaustion, timeout stage và p95/p99?
- Có cảnh báo khi retry rate hoặc pool pending tăng đột biến?

**Ghi nhớ:** `flatMap` giới hạn số inner đang chạy trong một subscription; global bulkhead mới bảo vệ resource dùng chung giữa nhiều request. Timeout của một attempt nằm bên trong retry, còn deadline của item nằm bên ngoài retry để tính cả backoff. `Retry.backoff(N, ...)` cho phép N lần retry sau lần đầu; chỉ retry lỗi transient, có jitter, deadline và idempotency phù hợp. Timeout không chứng minh side effect chưa xảy ra, cancellation không tự rollback upstream, và retry ở ngoài cả batch có thể chạy lại các item đã thành công. Chọn thông số từ resource budget và load test, rồi theo dõi active/pending/attempt/latency trong production.

## Tài liệu tham khảo

- Project Reactor 3.8 — [Flux API: flatMap, concurrency and prefetch](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor 3.8 — [Retry API: Retry.backoff and retry limits](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html).
- Project Reactor — [Reference Guide: Backpressure, prefetch and demand](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [Reference Guide: Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
- Reactor Netty 1.3 — [HTTP Client: Connection Pool, timeouts and metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- Spring Framework — [WebClient reactive HTTP client](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Framework — [Reactive transaction management and Reactor Context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
