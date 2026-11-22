# Thiết kế cảnh báo lỗi, cạn pool và truy vấn chậm

Trong ứng dụng Spring Data Relational R2DBC, một request chậm hoặc thất bại có thể bắt nguồn từ nhiều lớp: WebFlux, reactive pipeline, R2DBC connection pool, driver, database hoặc dịch vụ phụ trợ. Nếu chỉ theo dõi CPU và số HTTP 5xx, đội vận hành thường phát hiện sự cố muộn và khó biết connection pool đang cạn, query nào chậm hay lỗi nào đang tăng.

Một hệ thống cảnh báo hữu ích cần gắn với hành vi người dùng và khả năng phục vụ của ứng dụng. Với R2DBC, nên quan sát tối thiểu ba nhóm tín hiệu: **lỗi**, **tình trạng connection pool** và **độ trễ truy vấn**. Các tín hiệu này cần được kết hợp với latency/error rate của HTTP, transaction duration, logs có cấu trúc và distributed traces. Cảnh báo phải chỉ ra tác động, phạm vi và bước điều tra đầu tiên; cảnh báo quá nhạy hoặc quá nhiều sẽ bị bỏ qua.

## 1. Mục tiêu của observability trong R2DBC

Observability giúp trả lời ba câu hỏi:

- **Metrics:** hệ thống đang hoạt động thế nào và xu hướng thay đổi ra sao?
- **Logs:** một sự kiện cụ thể đã xảy ra với ngữ cảnh nào?
- **Traces:** request đã đi qua những thành phần nào và thời gian bị tiêu tốn ở đâu?

Với Spring Data Relational R2DBC, nên nối các tín hiệu theo cùng operation, service, environment và trace/correlation ID. Khi HTTP latency tăng, có thể kiểm tra xem thời gian tăng nằm ở pool acquire, SQL execution, result mapping hay downstream processing.

Một sơ đồ tín hiệu cơ bản:

```text
HTTP request / WebFlux
        |
        +---- request rate, error rate, latency
        |
        v
Service / reactive pipeline
        |
        +---- operation outcome, retries, cancellations
        |
        v
R2DBC connection pool
        |
        +---- acquired, idle, pending, acquire latency/timeouts
        |
        v
R2DBC driver / database
        |
        +---- query duration, SQL errors, lock waits, slow statements
        |
        v
Metrics + structured logs + traces + database telemetry
        |
        v
Dashboards, alerts and runbooks
```

Không cần thu thập mọi thứ ở mọi tầng với độ chi tiết tối đa. Hãy bắt đầu từ các tín hiệu trả lời được câu hỏi vận hành và bổ sung chi tiết khi có nhu cầu.

## 2. Thiết kế cảnh báo theo tác động, không chỉ theo ngưỡng kỹ thuật

Một metric vượt ngưỡng chưa chắc là sự cố người dùng. Ví dụ active connection đạt 90% pool trong vài giây có thể là đỉnh tải bình thường nếu không có request chờ và latency vẫn ổn định. Ngược lại, chỉ một vài pending acquire kéo dài cũng có thể gây timeout cho endpoint quan trọng dù CPU và database vẫn thấp.

Mỗi cảnh báo nên xác định:

1. **Tín hiệu:** metric hoặc sự kiện nào kích hoạt?
2. **Phạm vi:** service, environment, database, pool hay operation nào?
3. **Điều kiện thời gian:** vượt ngưỡng trong bao lâu và có cần traffic tối thiểu không?
4. **Tác động:** người dùng thấy lỗi, chậm, timeout hay chỉ có nguy cơ tài nguyên?
5. **Mức độ:** cần xử lý ngay hay chỉ cần theo dõi?
6. **Hành động:** dashboard, truy vấn hoặc runbook nào cần mở đầu tiên?

Ví dụ, cảnh báo “R2DBC pool đang dùng 95%” ít hữu ích hơn “pool customer-db đã bão hòa trong 5 phút, có request chờ connection và acquire timeout tăng”. Cảnh báo thứ hai cho thấy cả mức sử dụng lẫn dấu hiệu tác động.

### 2.1. Phân biệt cảnh báo triệu chứng và cảnh báo nguyên nhân

- **Triệu chứng:** HTTP 5xx tăng, request latency tăng, timeout tăng.
- **Nguyên nhân tiềm năng:** pool pending tăng, query duration tăng, database lock wait tăng, connection creation thất bại.

Triệu chứng cho biết người dùng bị ảnh hưởng. Metric nguyên nhân giúp khoanh vùng. Nên có cả hai lớp, nhưng tránh tạo một page alert riêng cho mọi metric có thể liên quan đến cùng sự cố.

### 2.2. Chọn mức độ nghiêm trọng

Một phân loại thực tế:

| Mức | Ý nghĩa | Ví dụ |
|---|---|---|
| Critical / Page | Dịch vụ chính đang mất khả năng phục vụ hoặc SLO bị ảnh hưởng nghiêm trọng | 5xx tăng mạnh, pool cạn và acquire timeout lan rộng |
| Warning / Ticket | Có xu hướng xấu hoặc rủi ro, chưa ảnh hưởng diện rộng | Pool utilization cao kéo dài nhưng chưa có pending acquire |
| Informational | Thông tin vận hành cần xem trên dashboard | Số retry tăng nhẹ sau một đợt deploy |

Tên mức độ và kênh gửi phụ thuộc quy trình trực vận hành của tổ chức. Điều quan trọng là mỗi mức phải có kỳ vọng phản hồi rõ ràng.

## 3. Bộ chỉ số nền tảng: RED và USE

Hai cách tổ chức metrics thường hữu ích:

- **RED** cho request/service: Rate, Errors, Duration.
- **USE** cho tài nguyên: Utilization, Saturation, Errors.

Áp dụng vào ứng dụng R2DBC:

| Nhóm | Câu hỏi | Ví dụ metric |
|---|---|---|
| Rate | Có bao nhiêu request/query mỗi giây? | HTTP requests, DB operations, statements |
| Errors | Bao nhiêu thao tác thất bại? | HTTP 5xx, R2DBC exceptions, acquire timeout |
| Duration | Mất bao lâu? | HTTP latency, pool acquire latency, query duration |
| Utilization | Tài nguyên đang dùng bao nhiêu? | Acquired/max connections |
| Saturation | Có công việc phải chờ không? | Pending acquire, queue wait, DB lock wait |
| Errors của resource | Tài nguyên có lỗi không? | Connection creation/validation failure |

Chỉ xem utilization chưa đủ. Pool dùng 100% nhưng không có pending request có thể là một trạng thái ngắn hạn chấp nhận được; pool dùng 75% nhưng pending acquire tăng liên tục có thể đáng báo động do connection đang được giữ lâu hoặc pool không đáp ứng burst.

## 4. Theo dõi lỗi của ứng dụng và database

Không gộp mọi lỗi thành một counter duy nhất. Phân loại lỗi giúp xác định hành động phù hợp.

Các nhóm nên quan sát:

- Lỗi kết nối: không mở được connection, connection reset, network failure.
- Lỗi pool: acquire timeout, pool closed, validation failure.
- Timeout: statement timeout, Reactor timeout, transaction timeout.
- Lỗi toàn vẹn dữ liệu: unique, foreign key, `NOT NULL`, `CHECK`.
- Lỗi transaction: deadlock, serialization failure, rollback.
- Lỗi SQL/mapping: syntax error, column/type mismatch, conversion error.
- Lỗi cancellation/disconnect: caller hủy request hoặc publisher bị cancel.

Không phải tất cả đều cần page alert. Duplicate key có thể là conflict nghiệp vụ bình thường; nếu tăng đột biến mới cần cảnh báo. Lỗi kết nối và acquire timeout thường đáng chú ý hơn vì có thể ảnh hưởng nhiều operation.

### 4.1. Đo error rate thay vì chỉ đếm số lỗi

Một counter lỗi tăng 100 lần có thể đáng kể với endpoint chỉ nhận 200 request, nhưng không đáng kể nếu service xử lý hàng triệu request. Nên tính tỷ lệ:

\[
\text{Error rate} =
\frac{\text{Số thao tác lỗi}}{\text{Tổng số thao tác}}\times 100\%
\]

Ví dụ dashboard có thể hiển thị tổng request, tổng lỗi và tỷ lệ lỗi theo operation. Cần có traffic minimum hoặc cách xử lý mẫu số nhỏ để tránh báo động sai khi chỉ có một request lỗi trong một cửa sổ rất ít traffic.

### 4.2. Phân loại lỗi theo metadata có cấu trúc

Với R2DBC, có thể dùng exception type, SQLSTATE và vendor error code để phân loại. Ví dụ PostgreSQL dùng SQLSTATE `23505` cho unique violation; các SQLSTATE nhóm `08` thường liên quan tới connection exception, nhóm `23` liên quan tới integrity constraint và nhóm `40` liên quan tới transaction rollback.

Không parse `exception.getMessage()` làm nguồn phân loại chính. Message thay đổi theo driver, database version và locale, đồng thời có thể chứa SQL hoặc dữ liệu nhạy cảm.

Một enum nội bộ giúp metric ổn định:

```java
public enum DatabaseErrorCategory {
    CONNECTION,
    POOL_ACQUIRE,
    TIMEOUT,
    DATA_INTEGRITY,
    TRANSACTION,
    SQL_OR_MAPPING,
    CANCELLED,
    UNKNOWN
}
```

Service hoặc lớp exception translator có thể ánh xạ lỗi sang category này rồi tăng counter. Không dùng raw exception message làm tag metric.

### 4.3. Cảnh báo lỗi theo operation

Nếu mọi lỗi database được gộp lại, một endpoint ít quan trọng có thể che lấp sự cố của endpoint thanh toán. Nên gắn operation name ổn định như:

- `customer.find-by-id`
- `order.create`
- `payment.capture`
- `report.export-page`

Operation name phải là tập giá trị hữu hạn do code định nghĩa. Không dùng URL đầy đủ có path parameter, customer ID, SQL statement hoặc giá trị bind làm label.

## 5. Quan sát R2DBC connection pool

Pool là một tài nguyên hữu hạn giữa ứng dụng và database. Những metric quan trọng thường gồm:

| Metric | Ý nghĩa |
|---|---|
| Acquired/active | Connection đang được ứng dụng giữ |
| Idle | Connection rảnh trong pool |
| Allocated/total | Tổng connection pool đã tạo |
| Max size | Giới hạn connection tối đa |
| Pending acquire | Request đang chờ connection |
| Acquire duration | Thời gian từ lúc yêu cầu tới lúc được cấp connection |
| Acquire timeout | Số lần chờ quá hạn mà không lấy được connection |
| Creation/validation failure | Không tạo hoặc xác thực được connection |
| Release/close | Connection được trả về hoặc đóng |

Tên metric chính xác phụ thuộc `r2dbc-pool`, Micrometer, Spring Boot và phiên bản đang dùng. Hãy kiểm tra metrics thực tế được export trong môi trường chạy; không sao chép tên metric từ một phiên bản khác mà chưa xác nhận.

### 5.1. Pool utilization

Một tỷ lệ đơn giản:

\[
\text{Pool utilization} =
\frac{\text{Acquired connections}}{\text{Max pool size}}
\]

Ví dụ pool tối đa 40 connection và 32 đang acquired thì utilization là 80%. Đây là tín hiệu để theo dõi, nhưng không nên tự động page chỉ vì tỷ lệ cao trong một vài giây.

Kết hợp utilization với:

- Pending acquire có tăng không?
- Acquire latency có tăng không?
- Acquire timeout có xuất hiện không?
- HTTP latency/error rate có xấu đi không?
- Database có đang quá tải hoặc chờ lock không?

### 5.2. Pending acquire là dấu hiệu saturation quan trọng

`pending acquire` cho biết có request đang chờ connection. Khi metric này duy trì lớn hơn 0, pool không thể đáp ứng ngay mọi nhu cầu tại thời điểm đo.

Một cảnh báo pool saturation nên kết hợp điều kiện như:

- Acquired gần max trong một khoảng thời gian đủ dài.
- Pending acquire lớn hơn 0 hoặc acquire duration tăng.
- Có acquire timeout hoặc HTTP latency tăng.

Ngưỡng cụ thể cần được hiệu chỉnh theo tải bình thường và SLA. Không có một con số utilization phù hợp cho mọi ứng dụng.

### 5.3. Acquire timeout

Acquire timeout là tín hiệu mạnh hơn utilization đơn lẻ vì một thao tác thực sự không lấy được connection trong deadline cấu hình. Theo dõi:

- Số lần timeout theo pool/database.
- Tỷ lệ timeout trên tổng số lần acquire.
- Khoảng thời gian timeout kéo dài.
- Operation nào đang tạo nhu cầu connection cao.

Nếu acquire timeout tăng, điều tra connection bị giữ lâu, query chậm, transaction dài, pool size, database max connections và các workload khác dùng chung database.

## 6. Không tăng pool size một cách mù quáng

Khi pool bão hòa, tăng `maxSize` có thể giảm hàng đợi trong ngắn hạn, nhưng cũng có thể làm database nhận nhiều query đồng thời hơn. Nếu database đã quá tải, tăng pool làm lock contention, CPU, memory hoặc I/O tệ hơn.

Trước khi thay pool size, hãy xác định nguyên nhân:

- Query có chậm do thiếu index hoặc execution plan xấu không?
- Có transaction giữ connection trong khi chờ HTTP hoặc xử lý CPU không?
- Có stream trả `Flux` lớn tới client chậm không?
- Có `collectList`, buffer hoặc prefetch làm pipeline giữ tài nguyên lâu không?
- Có retry storm sau lỗi tạm thời không?
- Có thao tác quên cleanup hoặc connection leak không?
- Nhiều application instance có tổng pool size vượt ngân sách connection của database không?

### 6.1. Tính ngân sách connection toàn hệ thống

Pool size cần được xét trên tổng số instance, không chỉ một pod:

\[
\text{Tổng connection tối đa} =
\text{Số instance} \times
\text{Max pool size mỗi instance}
\]

Ví dụ 8 instance, mỗi instance pool tối đa 30 connection, có thể tạo tới 240 connection cho một service. Nếu có thêm worker, migration job, dashboard và service khác dùng cùng database, tổng nhu cầu còn cao hơn.

Hãy dành capacity cho DBA/admin, replication, migration và workload khác. Database có giới hạn connection riêng; không đặt pool size chỉ dựa trên số thread hoặc số CPU của application.

### 6.2. Pool size và concurrency phải đi cùng nhau

`flatMap` concurrency cao, nhiều export đồng thời hoặc retry không giới hạn có thể làm nhu cầu connection tăng đột biến. Pool size hợp lý cần đi cùng giới hạn concurrency ở application layer, bulkhead cho endpoint nặng và quota cho job nền.

## 7. Theo dõi truy vấn chậm

Không có một metric query latency duy nhất mô tả toàn bộ thời gian của một thao tác R2DBC. Nên tách:

- Pool acquire time: thời gian chờ connection.
- Statement execution time: thời gian database/driver thực thi câu lệnh.
- Result consumption time: thời gian đọc hết result.
- Mapping time: thời gian chuyển row thành object.
- Downstream time: thời gian xử lý/serialize/gửi dữ liệu.
- End-to-end operation time: toàn bộ thời gian service operation.

Nếu chỉ đo thời gian từ lúc gọi repository đến khi `Flux` complete, metric đó có thể bao gồm cả thời gian downstream tiêu thụ. Nó không nhất thiết là thời gian SQL chạy trong database.

### 7.1. Histogram và percentile

Độ trễ thường có phân phối lệch: phần lớn query nhanh, một số query rất chậm. Average có thể che giấu tail latency.

Theo dõi các percentile như:

- p50: latency trung vị.
- p90/p95: tail latency ở mức phổ biến.
- p99: tail latency của nhóm request chậm nhất.

Ví dụ dashboard có thể hiển thị p50/p95/p99 của `order.find-by-id` trong từng khoảng thời gian. Histogram phù hợp để tính percentile trên tập request được tổng hợp từ nhiều instance; cách export và query cụ thể phụ thuộc metrics backend.

Không chỉ nhìn p99 khi traffic quá thấp vì percentile có thể thiếu ổn định. Kết hợp count/sample volume và latency của request thực tế.

### 7.2. Slow query threshold

Ngưỡng slow query nên dựa trên loại operation và SLO. Một lookup theo khóa chính có thể cần ngưỡng khác report aggregate hoặc export page. Có thể định nghĩa threshold theo nhóm:

| Nhóm operation | Ví dụ mục tiêu theo thiết kế |
|---|---|
| Lookup tương tác | Query theo primary/unique key |
| Ghi giao dịch | INSERT/UPDATE trong use case ngắn |
| Search/list | Query có filter và page size |
| Aggregate/report | GROUP BY, SUM, nhiều bảng hoặc dữ liệu lớn |
| Export page | Query page có thể lâu hơn nhưng có giới hạn |

Các ngưỡng trong bảng dashboard là chính sách nội bộ, không phải giới hạn mặc định của R2DBC. Hãy đo baseline rồi đặt cảnh báo theo SLO.

## 8. Dùng database telemetry để xác định query thật sự chậm

Metrics ở application cho biết operation nào chậm; database telemetry cho biết câu SQL, execution plan và nguyên nhân ở phía server.

Với PostgreSQL, các nguồn thường dùng gồm:

- `pg_stat_activity`: session và query đang hoạt động, trạng thái wait.
- `pg_stat_statements`: thống kê tổng hợp theo normalized query nếu extension được bật.
- `EXPLAIN (ANALYZE, BUFFERS)`: execution plan và buffer usage cho query được chọn.
- Database logs: statement duration, deadlock, lock timeout và connection events theo cấu hình.
- Lock/wait views: session nào đang chờ và session nào giữ lock.

Không bật log toàn bộ statement kèm bind values ở production nếu chưa đánh giá dữ liệu nhạy cảm và chi phí log. Dùng normalized query fingerprint hoặc query name khi có thể.

### 8.1. Phân biệt query chậm với chờ lock

Một statement có thể có elapsed time cao vì:

- Query plan tốn CPU/I/O.
- Thiếu index hoặc index không phù hợp.
- Đọc quá nhiều hàng.
- Lock wait hoặc transaction khác giữ khóa.
- Database quá tải hoặc thiếu I/O capacity.
- Network/driver/result consumption chậm.

`pg_stat_activity` và lock telemetry giúp phân biệt query đang chạy với query đang chờ. Một cảnh báo “query duration cao” nên dẫn tới kiểm tra wait event và execution plan, không mặc định kết luận thiếu index.

### 8.2. pg_stat_statements

Extension PostgreSQL `pg_stat_statements` tổng hợp thống kê cho các statement đã chạy, thường gồm số lần gọi và thời gian thực thi tổng/trung bình/min/max. Cần cấu hình extension và quyền truy cập phù hợp trên database.

Có thể dùng nó để tìm nhóm query có tổng thời gian cao hoặc mean/max bất thường. Thống kê có thể reset và có giới hạn số statement được theo dõi; hãy lưu ý thời điểm reset khi so sánh dashboard.

Không đưa raw query text vào label metric. Query text có thể chứa literal, schema detail hoặc dữ liệu nhạy cảm nếu ứng dụng ghép chuỗi SQL sai cách.

## 9. Gắn tên operation cho query R2DBC

Để phân tích theo use case, nên đặt tên operation ở service hoặc repository boundary:

```java
public Mono<Order> findOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .name("order.find-by-id")
        .tag("component", "r2dbc");
}
```

Các operator `name`/`tag` là metadata Reactor có thể được sử dụng bởi instrumentation tương thích. Việc chúng xuất hiện thành metric/trace tag phụ thuộc Micrometer/Reactor instrumentation đang cấu hình. Không giả định chỉ gọi `.name()` là metrics tự động được export.

Một cách khác là instrument ở service boundary bằng Observation/Micrometer theo chuẩn của phiên bản Spring Boot đang dùng. Dù chọn cách nào, operation name cần ổn định và có cardinality thấp.

### 9.1. Không gắn ID động vào tag

Không nên:

```java
// Không nên: mỗi orderId có thể tạo một time series riêng.
Timer.builder("r2dbc.operation.duration")
    .tag("orderId", orderId.toString())
    .register(registry);
```

Số lượng time series có thể tăng theo số order, gây tốn bộ nhớ và chi phí truy vấn metrics. Hãy dùng tag có tập giá trị hữu hạn như operation, database, outcome, error category hoặc deployment environment.

Không dùng email, username, tenant ID, SQL text, bind parameter, request ID hoặc trace ID làm metric label. Những giá trị này phù hợp hơn với log/trace có kiểm soát và vẫn phải tuân theo chính sách dữ liệu.

## 10. Metrics với Micrometer và Spring Boot

Spring Boot Actuator/Micrometer có thể cung cấp metrics cho HTTP, JVM, connection pool và observation tùy dependency, cấu hình và phiên bản. Với R2DBC, hãy xác nhận pool đang dùng có instrumented metrics và chúng được bind vào registry.

Các bước triển khai:

1. Thêm Actuator/Micrometer registry phù hợp với nền tảng metrics.
2. Bật endpoint metrics theo chính sách bảo mật.
3. Kiểm tra pool metrics có xuất hiện sau khi tạo và sử dụng connection.
4. Bổ sung timer/counter cho operation nghiệp vụ nếu instrumentation mặc định chưa đủ.
5. Gắn tag hữu hạn như `operation`, `database`, `outcome`, `error_category`.
6. Đưa metrics tới Prometheus hoặc backend tương ứng.
7. Xây dashboard và alert rule dựa trên SLO/baseline.

Tên meter, binder và property cấu hình thay đổi giữa Spring Boot, Micrometer và R2DBC Pool versions. Đọc tài liệu đúng phiên bản của dự án và kiểm tra endpoint `/actuator/metrics` hoặc scrape output ở môi trường test; không copy property cũ một cách máy móc.

### 10.1. Counter cho lỗi theo category

Ví dụ sử dụng `MeterRegistry` để tăng counter:

```java
public void recordDatabaseFailure(
        MeterRegistry registry,
        String operation,
        DatabaseErrorCategory category) {

    registry.counter(
        "app.database.operations",
        "operation", operation,
        "outcome", "error",
        "error_category", category.name()
    ).increment();
}
```

Đây là ví dụ instrumentation thủ công. Hãy bảo đảm `operation` và `category` đến từ enum/constant nội bộ có tập giá trị hữu hạn. Nếu mọi lần lỗi đều tăng counter cùng tag set, backend có thể tính rate theo thời gian.

### 10.2. Timer cho operation

```java
public Mono<Customer> findCustomer(Long id) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return customerRepository.findById(id)
            .doFinally(signal -> sample.stop(
                Timer.builder("app.database.operation.duration")
                    .tag("operation", "customer.find-by-id")
                    .tag("signal", signal.name().toLowerCase(Locale.ROOT))
                    .register(meterRegistry)
            ));
    });
}
```

Timer này đo thời gian từ lúc subscribe tới khi publisher complete/error/cancel. Với `Mono`, đó thường là thời gian end-to-end của operation. Với `Flux`, timer có thể bao gồm thời gian downstream tiêu thụ và không chỉ là SQL execution. Hãy đặt tên metric và mô tả semantics chính xác.

Nếu muốn đo riêng acquire hoặc statement duration, cần instrumentation ở đúng lớp pool/driver/Observation. Đừng gọi timer end-to-end là “SQL duration” nếu nó bao gồm mapping hoặc HTTP streaming.

## 11. Thiết kế cảnh báo pool exhaustion

Một cảnh báo pool hữu ích thường kết hợp nhiều tín hiệu thay vì một ngưỡng đơn:

**Warning:** utilization cao liên tục và pending acquire bắt đầu xuất hiện, nhưng chưa có acquire timeout đáng kể.

**Critical:** pending acquire duy trì, acquire latency vượt budget hoặc acquire timeout tăng, đồng thời HTTP error/latency cho thấy tác động.

Pseudo rule, không gắn với tên metric cụ thể:

```text
IF acquired_connections / max_connections > 0.90
AND pending_acquire > 0
FOR 5 minutes
THEN alert = R2DBC_POOL_SATURATED
```

Một rule khác có thể dựa trên tỷ lệ acquire timeout:

```text
IF rate(pool_acquire_timeouts[5m]) > 0
AND request_rate > minimum_traffic
FOR 2 minutes
THEN alert = R2DBC_POOL_ACQUIRE_TIMEOUTS
```

Các ngưỡng 90%, 5 phút và 2 phút chỉ là ví dụ để minh họa. Cần hiệu chỉnh theo pool size, burst pattern, SLA, traffic và khả năng scale của database.

### 11.1. Vì sao không cảnh báo utilization cao đơn lẻ?

Pool có thể được dùng hiệu quả ở utilization cao mà không gây queue. Cảnh báo utilization đơn lẻ dễ tạo false positive trong giờ cao điểm. Pending acquire, acquire duration và timeout cho biết có nhu cầu thực sự đang phải chờ.

### 11.2. Cảnh báo theo pool/database

Nếu ứng dụng có nhiều `ConnectionFactory` hoặc nhiều pool, mỗi pool cần danh tính ổn định. Gắn label `pool` hoặc `database` từ cấu hình nội bộ, ví dụ `primary`, `reporting`. Không đưa connection URL hoặc hostname có thông tin bí mật vào label công khai.

## 12. Thiết kế cảnh báo query chậm

Một cảnh báo query chậm có thể dựa trên p95/p99 hoặc số query vượt ngưỡng:

```text
IF p95(operation_duration{operation="order.find-by-id"}) > 300ms
AND operation_count > minimum_sample_count
FOR 10 minutes
THEN alert = ORDER_LOOKUP_SLOW
```

Đây là rule minh họa. Nếu timer đo toàn bộ publisher, metric có thể bao gồm downstream processing. Với query `Flux`, thời gian complete phụ thuộc số hàng và tốc độ tiêu thụ. Nên dùng operation-specific latency và tách query execution/result consumption khi có thể.

### 12.1. Cảnh báo số query vượt slow threshold

Ngoài percentile, có thể đếm số lần query vượt ngưỡng:

```text
slow_query_count = count(query_duration > threshold)
```

Số lượng tuyệt đối giúp phát hiện các query hiếm nhưng rất chậm. Tỷ lệ slow query trên tổng query giúp so sánh khi traffic thay đổi.

### 12.2. Không page cho mọi query chậm đơn lẻ

Một query report có thể chậm hợp lệ hơn lookup giao dịch. Phân loại theo operation và SLO. Cảnh báo nên kích hoạt khi vấn đề lặp lại hoặc có tác động, đồng thời có thể dùng log/trace để điều tra từng outlier.

## 13. Cảnh báo error rate và SLO

Nếu service có SLO về availability hoặc latency, hãy thiết kế alert theo mức tiêu hao error budget thay vì chỉ dùng một ngưỡng lỗi cố định.

Ví dụ SLI availability:

\[
\text{Availability} =
1 - \frac{\text{Eligible failed requests}}{\text{Eligible requests}}
\]

Định nghĩa “eligible failed request” cần rõ: có tính lỗi validation/client 4xx không, timeout upstream không, cancellation do client rời đi không? Không nên đưa mọi lỗi thành server failure nếu chúng không phản ánh chất lượng service.

Với SLO 99.9%, error budget trong một kỳ là phần 0.1% request được phép thất bại theo định nghĩa SLI. Burn rate đo tốc độ tiêu hao budget so với tốc độ đều trong kỳ.

Multi-window/multi-burn-rate alert có thể phát hiện:

- Sự cố nghiêm trọng đang đốt error budget nhanh trong cửa sổ ngắn.
- Sự cố nhỏ hơn nhưng kéo dài, có thể làm hết budget trong kỳ.

Không cần áp dụng một công thức alert phức tạp nếu service chưa có SLO rõ ràng. Bắt đầu bằng error ratio và latency theo operation, sau đó chuyển sang error budget khi SLI/SLO đã được thống nhất.

## 14. Correlate lỗi HTTP với lỗi R2DBC

Một request có thể phát sinh lỗi ở nhiều tầng. Ví dụ HTTP 503 có thể do pool acquire timeout; HTTP 500 có thể do SQL syntax/mapping; HTTP 409 có thể là unique conflict nghiệp vụ.

Hãy giữ các chiều phân tích:

- HTTP route template và status class.
- Service operation.
- Database/pool name.
- Error category.
- Trace ID hoặc correlation ID trong log/trace.
- Deployment version.

Không dùng path cụ thể chứa ID làm metric label. Dùng route template như `/orders/{id}` để giữ cardinality thấp.

Khi có trace, có thể quan sát các span như:

```text
HTTP POST /orders
  └── order.create
       ├── r2dbc.pool.acquire
       ├── db INSERT orders
       └── db INSERT order_lines
```

Tên span và cách instrumentation tự động tạo chúng phụ thuộc Micrometer Observation/Tracing và driver. Sơ đồ là minh họa cấu trúc, không phải tên span mặc định của mọi stack.

## 15. Logs có cấu trúc hỗ trợ cảnh báo

Metrics cho thấy xu hướng; log giúp xem một lần lỗi cụ thể. Một log event phù hợp có thể gồm:

```text
event=database.operation.failed
service=order-service
operation=order.create
database=primary
error_category=CONNECTION
exception_type=R2dbcTransientResourceException
correlation_id=...
deployment_version=...
```

Các trường này là ví dụ. Dùng operation/database/category có tập giá trị hữu hạn. Correlation ID giúp tra cứu trace, nhưng không nên dùng làm metric label.

### 15.1. Không ghi raw SQL hoặc bind values

SQL và giá trị bind có thể chứa email, token, dữ liệu thanh toán hoặc nội dung người dùng. Không bật TRACE cho driver/statement logging trong production một cách mặc định. Nếu cần điều tra, dùng query fingerprint hoặc operation name và metadata đã được phê duyệt.

### 15.2. Giữ cause nhưng kiểm soát log output

Có thể giữ exception cause trong pipeline và log loại lỗi/category an toàn ở boundary. Không nhất thiết truyền toàn bộ `Throwable` vào logger nếu message/stack trace có thể chứa SQL hoặc dữ liệu nhạy cảm. Nếu cần stack trace, chỉ ghi vào sink được phân quyền và có chính sách redaction/retention phù hợp.

## 16. Distributed tracing cho truy vấn chậm

Trace giúp phân biệt thời gian ở các tầng:

- Chờ connection pool.
- Gửi statement và chờ database.
- Đọc result.
- Mapping dữ liệu.
- Gọi service ngoài.
- Serialize/ghi HTTP response.

Nếu trace chỉ có một span database tổng thể, vẫn có thể thấy operation chậm nhưng khó phân biệt pool wait với SQL execution. Bổ sung instrumentation ở pool/driver hoặc ghi event/timer riêng khi cần.

### 16.1. Sampling

Trace mọi request có thể tốn dung lượng và chi phí. Có thể dùng sampling theo tỷ lệ, đồng thời ưu tiên giữ trace có lỗi hoặc latency cao nếu tracing backend hỗ trợ tail-based sampling. Cần bảo đảm policy không làm mất toàn bộ trace của operation hiếm nhưng quan trọng.

Không dùng trace ID làm tag metric vì cardinality gần như mỗi request một giá trị. Trace ID thuộc log/trace context.

## 17. Cardinality và chi phí metrics

Một lỗi thường gặp là tạo metric tag từ dữ liệu động:

- `customerId`, `orderId`, `email`.
- Raw SQL hoặc query parameter.
- Request ID, trace ID.
- URL có path variable.
- Exception message.

Mỗi tổ hợp tag tạo một time series riêng. Cardinality cao làm tăng memory, storage, scrape/ingestion cost và làm dashboard chậm.

Ưu tiên tag hữu hạn:

- `operation`: enum/constant.
- `database`: tên logical pool.
- `outcome`: `success`, `error`, `cancelled`.
- `error_category`: enum.
- `environment`: `prod`, `staging`.
- `status_class`: `2xx`, `4xx`, `5xx`.

Nếu cần tìm một order cụ thể, dùng log/trace có kiểm soát thay vì metric label.

## 18. Cảnh báo retry storm và connection creation

Retry có thể làm tăng tải database đúng lúc database đang gặp sự cố. Theo dõi:

- Retry attempts theo operation và error category.
- Tỷ lệ retry thành công/thất bại.
- Số attempt trung bình trên một operation.
- Backoff duration.
- Connection creation rate và creation failures.
- Pending acquire và query rate trong thời gian retry.

Nếu nhiều instance retry đồng thời mà không có backoff/jitter, database có thể bị dồn tải sau khi phục hồi. Cảnh báo retry storm nên kết hợp retry rate tăng nhanh với error rate hoặc pool saturation.

Không retry lỗi validation, duplicate key hoặc SQL syntax. Chỉ retry nhóm lỗi tạm thời được xác định và phải có giới hạn, deadline tổng thể cùng idempotency cho thao tác ghi.

## 19. Dashboard vận hành nên có gì?

Một dashboard R2DBC có thể chia thành các khu vực:

### 19.1. Sức khỏe request

- Request rate theo route template/operation.
- Error rate và status class.
- p50/p95/p99 HTTP latency.
- Request timeout/cancellation.
- Deployment version và thời điểm rollout.

### 19.2. Connection pool

- Acquired, idle, allocated và max size.
- Pending acquire.
- Acquire latency p95/p99.
- Acquire timeout và connection creation failure.
- Utilization theo từng logical pool.

### 19.3. Database operations

- Query/operation count.
- Error rate theo error category.
- p50/p95/p99 duration theo operation.
- Số slow query vượt threshold.
- Retry attempts.
- Transaction duration/rollback nếu có instrumentation.

### 19.4. Database server

- Active sessions và connection limit.
- CPU, memory, I/O, storage latency.
- Lock waits/deadlocks.
- Cache hit/physical read nếu hệ quản trị cung cấp.
- Top normalized statements theo total time/call count.
- Replication lag nếu có replica.

### 19.5. JVM

- Heap used/after GC.
- Allocation rate và GC pause.
- Thread/scheduler utilization.
- Direct buffer/native memory nếu có số liệu.
- Container memory và restart/OOM.

Dashboard nên cho phép lọc theo service, environment, database/pool và operation. Đừng đặt mọi metric vào một màn hình mà không có thứ tự điều tra.

## 20. Ví dụ PromQL mang tính minh họa

Tên metric thực tế phụ thuộc binder và cấu hình. Các biểu thức sau dùng tên placeholder để thể hiện cách suy nghĩ; hãy thay bằng tên metric đã xác minh trong hệ thống.

### 20.1. Tỷ lệ lỗi operation

```promql
sum(rate(app_database_operations_total{outcome="error"}[5m]))
/
clamp_min(sum(rate(app_database_operations_total[5m])), 1)
```

Có thể group theo `operation` hoặc `database` nếu tag set có cardinality thấp. `clamp_min` tránh chia cho 0; vẫn cần xử lý traffic thấp để không tạo cảnh báo gây nhiễu.

### 20.2. Pool utilization

```promql
app_r2dbc_pool_acquired
/
clamp_min(app_r2dbc_pool_max, 1)
```

Nếu có nhiều pool, group theo logical pool name. Chỉ alert khi utilization cao đi cùng pending acquire hoặc acquire latency.

### 20.3. Pending acquire

```promql
max_over_time(app_r2dbc_pool_pending[5m]) > 0
```

Rule thực tế nên cân nhắc thời gian duy trì, mức pending và tác động tới request. Một spike ngắn có thể không cần page.

### 20.4. p95 operation duration

Với histogram metric có bucket:

```promql
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(app_database_operation_duration_seconds_bucket[5m])
  )
)
```

Tên `_bucket` và đơn vị phụ thuộc metric thực tế. Nếu timer không export histogram buckets, không thể tính percentile theo cách này; cần bật histogram theo cấu hình Micrometer/backend phù hợp.

### 20.5. Acquire timeout rate

```promql
sum by (pool) (
  rate(app_r2dbc_pool_acquire_timeouts_total[5m])
)
```

Đặt alert khi rate tăng trong một cửa sổ phù hợp và có traffic. Với hệ thống ít request, có thể dùng số lần timeout tuyệt đối cùng thời gian duy trì.

## 21. Ví dụ cảnh báo và hành động đề xuất

| Cảnh báo | Tín hiệu gợi ý | Hành động đầu tiên |
|---|---|---|
| HTTP error rate tăng | 5xx ratio vượt SLO | Mở trace lỗi, xem deployment và error category |
| R2DBC pool saturation | Acquired gần max + pending acquire | Kiểm tra acquire duration, query/transaction đang giữ connection |
| Pool acquire timeout | Timeout counter tăng | Kiểm tra pool metrics, connection leak, database max connections |
| Query latency tăng | p95/p99 theo operation vượt baseline | Mở normalized query, execution plan, lock/wait telemetry |
| Database connection failures | Creation/validation failures tăng | Kiểm tra network, credentials rotation, DB availability và connection limit |
| Retry storm | Attempts tăng mạnh theo operation | Kiểm tra lỗi gốc, backoff/jitter, retry filter và idempotency |
| Transaction quá dài | Transaction duration p95/p99 tăng | Tìm network/CPU work trong transaction và stream dài |
| Cancellation tăng bất thường | Cancel count tăng theo endpoint | Kiểm tra client disconnect, gateway timeout và response latency |

Mỗi alert nên liên kết tới dashboard phù hợp và runbook. Đừng chỉ gửi một thông báo “threshold exceeded” không có operation, pool hoặc environment.

## 22. Runbook điều tra pool cạn

Khi nhận cảnh báo pool saturation hoặc acquire timeout:

1. Xác nhận phạm vi: một pool hay toàn bộ database; một instance hay tất cả instance.
2. Kiểm tra acquired/max, idle, pending acquire và acquire latency.
3. Kiểm tra HTTP request rate, 5xx và latency cùng thời điểm.
4. Tìm operation có query duration hoặc request duration tăng.
5. Kiểm tra transaction dài, stream lớn và client chậm.
6. Kiểm tra database active sessions, lock wait, CPU/I/O và connection limit.
7. Kiểm tra retry rate và connection creation failures.
8. Nếu cần giảm tải, giới hạn concurrency/export hoặc tạm dừng workload nền theo quy trình.
9. Chỉ tăng pool size khi database còn capacity và đã xác định pool là nút thắt thực sự.
10. Sau khắc phục, xác nhận pending acquire về 0, acquire latency bình thường và HTTP SLO phục hồi.

Không kill session hoặc thay đổi database setting trong production nếu chưa xác định tác động và quy trình vận hành cho phép. Runbook nên chỉ rõ người có quyền thực hiện các thao tác đó.

## 23. Runbook điều tra query chậm

Khi p95/p99 hoặc slow query count tăng:

1. Xác định operation và thời điểm bắt đầu.
2. So sánh query duration với pool acquire và end-to-end duration.
3. Kiểm tra query fingerprint/normalized statement tương ứng.
4. Xem `pg_stat_activity`, wait event và lock chain nếu dùng PostgreSQL.
5. Kiểm tra `pg_stat_statements` để tìm thay đổi call count/mean/total time.
6. Chạy `EXPLAIN` hoặc `EXPLAIN ANALYZE` trên môi trường phù hợp với dữ liệu đại diện.
7. Kiểm tra index, số hàng đọc, join, sort, filter và parameter selectivity.
8. Kiểm tra thay đổi schema, statistics, data volume và deployment gần đây.
9. Đánh giá tác động của query fix bằng latency, pool utilization và database load.

`EXPLAIN ANALYZE` thực thi query thật. Với câu lệnh ghi hoặc query nặng, hãy chọn môi trường và transaction an toàn; không chạy tùy tiện trên production.

## 24. Tránh alert fatigue

Một hệ thống cảnh báo tốt không chỉ phát hiện sự cố mà còn giúp người trực biết phải làm gì. Các nguyên nhân gây alert fatigue:

- Cảnh báo cho spike vài giây không ảnh hưởng người dùng.
- Cảnh báo cùng một sự cố từ nhiều metric không được group.
- Ngưỡng cố định không xét traffic hoặc baseline.
- Alert không có owner/runbook.
- Cảnh báo informational gửi cùng kênh với critical page.
- Metric cardinality cao khiến dashboard và alert evaluation chậm.
- Không có quy trình mute/maintenance window khi deploy hoặc bảo trì.

Hãy review alert sau mỗi sự cố và định kỳ:

- Alert có phát hiện vấn đề trước khi người dùng báo không?
- Có false positive không?
- Có cảnh báo nào trùng nhau không?
- Người trực có thể hành động từ nội dung alert không?
- Ngưỡng có còn phù hợp sau khi traffic tăng không?
- Alert nào chưa từng được sử dụng và có thể bỏ?

## 25. Kiểm thử cảnh báo trước khi đưa vào production

Cảnh báo cũng là một phần của sản phẩm vận hành và cần được kiểm thử.

### 25.1. Kiểm thử instrumentation

- Gây một lỗi database có kiểm soát trong môi trường test.
- Xác nhận counter error tăng đúng operation/category.
- Xác nhận success counter không tăng nhầm.
- Xác nhận cancellation được phân loại riêng nếu cần.
- Kiểm tra tag không chứa ID hoặc dữ liệu nhạy cảm.

### 25.2. Kiểm thử pool saturation

Trong môi trường test, cấu hình pool nhỏ, ví dụ `maxSize = 1`, giữ một connection có kiểm soát rồi yêu cầu connection thứ hai. Xác nhận pending/acquire metrics tăng theo dự kiến và timeout được ghi nhận. Sau khi release connection đầu, xác nhận pool phục hồi.

Không dùng cách này trên production. Test cần đóng pool và database fixture sau khi hoàn tất.

### 25.3. Kiểm thử slow query alert

- Tạo query chậm trong database test (ví dụ PostgreSQL `pg_sleep` nếu dùng PostgreSQL).
- Xác nhận timer/trace ghi duration đúng semantics.
- Xác nhận alert rule kích hoạt khi điều kiện và cửa sổ thời gian thỏa.
- Xác nhận query nhanh không kích hoạt alert.

### 25.4. Kiểm thử retry và retry storm

- Mô phỏng lỗi transient.
- Xác nhận retry count và backoff.
- Mô phỏng duplicate/validation error và xác nhận không retry.
- Hủy publisher trong backoff và xác nhận không có attempt mới.
- Kiểm tra metric attempts có tag hữu hạn.

### 25.5. Kiểm thử alert routing và runbook

- Xác nhận critical và warning đi đúng kênh.
- Xác nhận alert group cùng sự cố thay vì gửi hàng loạt notification.
- Kiểm tra link dashboard/runbook mở đúng môi trường.
- Xác nhận alert có owner và thông tin operation/pool.
- Chạy tabletop exercise để người trực thực hành theo runbook.

## 26. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ cảnh báo CPU hoặc HTTP 5xx | Bỏ sót pool saturation và query chậm | Kết hợp RED/USE, pool và DB telemetry |
| Alert khi utilization cao trong vài giây | False positive vào giờ cao điểm | Kết hợp pending acquire, latency và thời gian duy trì |
| Chỉ nhìn average query latency | Tail latency bị che khuất | Theo dõi histogram/p95/p99 và sample count |
| Gọi end-to-end Flux duration là SQL duration | Nhầm downstream chậm với database chậm | Tách acquire, statement, result và response timing |
| Gộp mọi lỗi thành một counter | Không biết lỗi connection hay integrity | Phân loại theo exception type/SQLSTATE/category |
| Parse exception message để phân loại | Rule dễ hỏng theo driver/version | Dùng metadata có cấu trúc |
| Tăng max pool size ngay khi pending tăng | Có thể làm database quá tải hơn | Điều tra query/transaction/concurrency trước |
| Chỉ xem pool một instance | Tổng pool của nhiều instance vượt DB limit | Tính ngân sách connection toàn hệ thống |
| Không đo pending acquire | Không thấy request đang phải chờ | Export pending/acquire duration/timeouts |
| Metric tag dùng orderId/email/SQL | Cardinality bùng nổ và có thể lộ dữ liệu | Dùng operation/category hữu hạn |
| Log toàn bộ SQL bind values | Rò rỉ PII/secret và tăng log volume | Dùng query fingerprint, redaction và allowlist |
| Alert không có runbook | Người trực mất thời gian tìm hướng xử lý | Gắn dashboard, owner và bước điều tra |
| Page cho mọi lỗi duplicate | Alert noise do conflict nghiệp vụ bình thường | Phân loại, alert theo tỷ lệ/xu hướng bất thường |
| Retry không giới hạn | Retry storm làm tăng tải database | Backoff, jitter, retry filter và deadline |
| Không kiểm thử alert rule | Alert không kích hoạt hoặc kích hoạt sai | Test metric, threshold, routing và runbook |

## 27. Quy trình triển khai observability và alerting

Có thể triển khai theo trình tự:

1. **Xác định SLO:** availability, latency và các operation quan trọng.
2. **Liệt kê tín hiệu:** HTTP RED, R2DBC pool USE, DB query/lock, retry và transaction.
3. **Bật instrumentation:** Actuator/Micrometer, pool metrics, tracing và database telemetry.
4. **Chuẩn hóa operation/error category:** dùng enum/constant ổn định, cardinality thấp.
5. **Xây dashboard:** request, pool, operation, database server và JVM.
6. **Thiết kế alert:** error ratio, pool saturation, acquire timeout, query tail latency và retry storm.
7. **Đặt cửa sổ/traffic minimum:** tránh spike và mẫu số quá nhỏ.
8. **Viết runbook:** bước điều tra, dashboard, truy vấn và owner.
9. **Kiểm thử:** mô phỏng lỗi, pool cạn, query chậm, retry và alert routing.
10. **Hiệu chỉnh:** review false positive/negative sau deploy và sau mỗi sự cố.

## 28. Nguyên tắc cần nhớ

- Theo dõi lỗi, pool và query cùng HTTP latency để thấy cả tác động lẫn nguyên nhân.
- Dùng RED cho request/service và USE cho tài nguyên pool/database.
- Phân loại lỗi theo exception type, SQLSTATE hoặc vendor code; tránh parse message.
- Error rate có ý nghĩa hơn số lỗi tuyệt đối khi traffic thay đổi; xử lý mẫu số nhỏ.
- Pool utilization cần đi cùng pending acquire, acquire latency và timeout.
- Pending acquire/acquire timeout là tín hiệu saturation trực tiếp hơn utilization đơn lẻ.
- Tính tổng connection tối đa từ mọi instance/pool và so với ngân sách database.
- Không tăng pool size mù quáng; điều tra query chậm, transaction dài, stream, retry và concurrency.
- Đo p50/p95/p99 bằng histogram và sample count; không chỉ nhìn average.
- Tách acquire time, statement time, result consumption và end-to-end operation time.
- Dùng database telemetry như `pg_stat_activity`, `pg_stat_statements`, wait events và execution plan khi phù hợp.
- Gắn operation name ổn định; không dùng ID, SQL text, bind values, email hoặc trace ID làm metric label.
- Logs có cấu trúc cần allowlist và không ghi raw SQL/bind values hoặc secret.
- Tracing giúp nối HTTP, service, pool và database nhưng cần sampling/cardinality hợp lý.
- Cảnh báo nên có điều kiện duy trì, mức độ, owner, dashboard và runbook.
- Alert theo tác động/SLO và error budget khi có định nghĩa rõ; tránh page cho mọi spike nhỏ.
- Theo dõi retry rate để phát hiện retry storm; chỉ retry lỗi transient với giới hạn/backoff.
- Kiểm thử instrumentation, pool saturation, slow query, alert routing và runbook trước production.

Thiết kế cảnh báo cho Spring Data Relational R2DBC cần nối được chất lượng request với trạng thái tài nguyên và hành vi database. HTTP error/latency cho biết người dùng đang bị ảnh hưởng; pool acquired/pending/acquire timeout cho biết ứng dụng có lấy được connection hay không; query duration và database wait telemetry giúp xác định câu lệnh hoặc lock gây chậm. Khi các tín hiệu được phân loại ổn định, gắn operation name có cardinality thấp, đặt ngưỡng theo SLO và đi kèm runbook, cảnh báo sẽ giúp đội vận hành phát hiện sớm sự cố và xử lý đúng nguyên nhân thay vì chỉ phản ứng với một con số vượt ngưỡng.
