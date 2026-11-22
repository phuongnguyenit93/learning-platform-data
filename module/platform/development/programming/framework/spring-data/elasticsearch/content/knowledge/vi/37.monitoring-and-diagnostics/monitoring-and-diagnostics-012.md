# Theo dõi độ trễ, lỗi, thông lượng và độ trễ đồng bộ

Một hệ thống Spring Data Elasticsearch có thể vẫn trả HTTP 200 nhưng trải nghiệm tìm kiếm đã chậm, dữ liệu đồng bộ bị trễ hoặc một phần document trong bulk đã thất bại. Chỉ theo dõi trạng thái node xanh và số request tổng thể không đủ để biết ứng dụng có đang đáp ứng yêu cầu hay không. Cần quan sát ít nhất bốn nhóm tín hiệu: **độ trễ (latency), lỗi (errors), thông lượng (throughput) và độ trễ đồng bộ (synchronization lag)**.

Các chỉ số này cần được đo ở cả phía ứng dụng và Elasticsearch. Ứng dụng biết thời gian người dùng thực sự chờ, số item thành công/thất bại và thời điểm event đi qua từng bước. Elasticsearch cho biết thời gian xử lý search/index, áp lực thread pool, heap, refresh, merge và shard. Kết hợp hai phía giúp xác định chậm ở client/network, service, queue, cluster hay pipeline đồng bộ.

Trong Spring Boot, Micrometer và Actuator là nền tảng thuận tiện để phát metric; tracing có thể dùng Micrometer Observation/OpenTelemetry; Elasticsearch cung cấp Node Stats, Index Stats và Cluster APIs. Với đồng bộ bất đồng bộ, cần ghi timestamp hoặc offset xuyên suốt từ lúc nguồn commit đến lúc document có thể được search, thay vì chỉ đo thời gian gọi `save()`.

## 1. Bốn nhóm tín hiệu cần theo dõi

| Nhóm | Câu hỏi cần trả lời | Ví dụ chỉ số |
|---|---|---|
| Latency | Người dùng/job phải chờ bao lâu? | Search p50/p95/p99, bulk request duration, queue wait |
| Errors | Có bao nhiêu thao tác không thành công và vì sao? | HTTP 4xx/5xx, 409 conflict, 429 rejection, bulk item failures |
| Throughput | Hệ thống xử lý được bao nhiêu công việc mỗi đơn vị thời gian? | Search requests/s, documents indexed/s, events processed/s, bytes/s |
| Sync lag | Dữ liệu nguồn mất bao lâu mới xuất hiện trong search? | Event age, consumer lag, source-to-search-visible duration |

Không nên tối ưu một nhóm riêng lẻ. Ví dụ tăng concurrency có thể tăng throughput trong thời gian ngắn nhưng làm p99 latency, 429 và queue depth tăng. Một pipeline có thể ghi rất nhanh vào Elasticsearch nhưng search vẫn thấy dữ liệu trễ do refresh interval hoặc consumer lag.

## 2. Phân biệt latency ở các tầng

Một thao tác tìm kiếm từ client đi qua nhiều tầng:

```text
Client
  |
  v
API gateway / load balancer
  |
  v
Spring WebFlux / MVC controller
  |
  v
Service + query construction
  |
  v
Elasticsearch Java client / connection pool
  |
  v
Network -> coordinating node -> shard execution
  |
  v
Response decode -> mapping DTO -> HTTP response
```

Thời gian người dùng cảm nhận là end-to-end latency. Nó bao gồm các khoảng chờ và xử lý ở các tầng trên. Chỉ đo thời gian Elasticsearch trả về không đủ để đại diện cho toàn bộ request.

### Những latency nên tách riêng

- **HTTP/API latency:** từ khi ứng dụng nhận request đến khi trả response.
- **Service latency:** thời gian xử lý logic, validate, authorization và mapping.
- **Elasticsearch client latency:** thời gian gọi qua client, gồm chờ connection, network và chờ server response.
- **Elasticsearch `took`:** thời gian Elasticsearch báo đã dùng để xử lý search request; không bao gồm toàn bộ thời gian người dùng chờ ở gateway, ứng dụng, network và mapping response.
- **Queue wait:** thời gian event/job nằm chờ trước khi consumer bắt đầu xử lý.
- **Processing latency:** thời gian consumer biến đổi dữ liệu và gửi write request.
- **Search visibility lag:** khoảng từ khi nguồn commit đến khi dữ liệu có thể được search sau refresh.

### Ví dụ phân tích

Giả sử API search có p95 là 900 ms, trong khi Elasticsearch `took` p95 là 180 ms. Phần chênh lệch khoảng 720 ms có thể nằm ở gateway, connection acquisition, network, service processing, response mapping hoặc các request phụ. Không thể kết luận chính xác chỉ bằng phép trừ; cần tracing và metric từng span để tìm đoạn chậm.

Nếu API latency và `took` cùng tăng, cần xem query, shard, thread pool và tài nguyên cluster. Nếu `took` ổn định nhưng API latency tăng, tập trung vào ứng dụng, connection pool, gateway, network hoặc payload/serialization.

## 3. Dùng percentile thay vì chỉ nhìn average

Average latency hữu ích để quan sát xu hướng tổng thể nhưng có thể che giấu các request rất chậm. Với API tìm kiếm, nên theo dõi:

- **p50:** một nửa request nhanh hơn hoặc bằng giá trị này.
- **p95:** 95% request nhanh hơn hoặc bằng giá trị này.
- **p99:** 99% request nhanh hơn hoặc bằng giá trị này; thể hiện tail latency.
- **Max:** request chậm nhất trong cửa sổ đo, thường nhạy với outlier.

Ví dụ:

| Chỉ số | Thời gian |
|---|---:|
| p50 | 80 ms |
| p95 | 350 ms |
| p99 | 1.800 ms |
| Max | 5.200 ms |

Average có thể trông chấp nhận được trong khi một nhóm nhỏ người dùng phải chờ vài giây. Vì vậy, SLO thường nên đặt theo p95/p99 và phân loại theo endpoint/workload.

### Tách workload

Không gộp mọi request vào một timer duy nhất. Search tương tác, autocomplete, dashboard aggregation, export và bulk ingestion có đặc tính khác nhau. Theo dõi riêng theo operation hoặc endpoint có cardinality thấp để biết workload nào gây ra tail latency.

## 4. Xác định SLI và SLO trước khi đặt alert

SLI (Service Level Indicator) là chỉ số phản ánh mức độ dịch vụ đáp ứng yêu cầu. SLO (Service Level Objective) là mục tiêu đặt cho SLI trong một khoảng thời gian.

Ví dụ minh họa:

| SLI | SLO ví dụ | Phạm vi |
|---|---|---|
| Search API p95 | Dưới 400 ms | Request tìm kiếm tương tác |
| Search success rate | Trên 99,9% | Request hợp lệ, loại trừ lỗi input do client |
| Bulk item success | Trên 99,5% trong một cửa sổ | Item ingestion trước retry/DLQ |
| Projection freshness p95 | Dưới 30 giây | Source commit đến search-visible |
| Consumer backlog age | Dưới 2 phút | Event stream đồng bộ liên tục |

Các con số trên chỉ là ví dụ. Hãy chọn SLO theo yêu cầu sản phẩm, workload thực tế và khả năng vận hành. Đừng lấy một ngưỡng chung cho cả search tương tác và export hàng triệu document.

### Định nghĩa success rate rõ ràng

Một HTTP 200 từ Bulk API không đồng nghĩa tất cả item thành công. Với ingestion, nên có hai chỉ số:

- Bulk request success: request tới Elasticsearch hoàn tất ở cấp HTTP/client.
- Bulk item success: số action thành công chia cho tổng action được gửi.

Ngoài ra, có thể theo dõi tỷ lệ item cuối cùng được xử lý thành công sau retry. Phân biệt các mẫu số để dashboard không che giấu partial failure.

## 5. Đo latency ở Spring Boot bằng Micrometer

Micrometer cung cấp `Timer` để ghi thời gian và số lần thực hiện. Với Spring Boot Actuator, các metric có thể được expose cho hệ thống giám sát như Prometheus tùy registry được cấu hình.

Dependency thường dùng với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Spring Boot dependency management nên quản lý version Micrometer tương thích. Không ghim một version Micrometer khác với BOM nếu không có lý do rõ ràng.

Ví dụ cấu hình endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Chỉ expose endpoint metrics cho mạng/role giám sát được phép. Không công khai metrics, health details hoặc thông tin nội bộ Elasticsearch ra Internet nếu không có lớp xác thực và network policy phù hợp.

## 6. Ghi Timer cho thao tác Spring Data Elasticsearch

Ví dụ đo thời gian lưu một document bằng `ElasticsearchOperations`:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductWriter {

    private final ElasticsearchOperations operations;
    private final MeterRegistry registry;

    public ProductWriter(
            ElasticsearchOperations operations,
            MeterRegistry registry) {
        this.operations = operations;
        this.registry = registry;
    }

    public ProductDocument save(ProductDocument document) {
        return Timer.builder("app.elasticsearch.write")
            .description("Time spent saving a product document")
            .tag("operation", "save")
            .tag("index", "products")
            .register(registry)
            .record(() -> operations.save(
                document,
                IndexCoordinates.of("products")
            ));
    }
}
```

Đây là ví dụ cho API đồng bộ. Với API reactive, không dùng `Timer.record(Supplier)` theo cách bao quanh việc tạo `Mono` rồi kết luận timer đã đo thời gian hoàn tất. Phải đo từ lúc subscribe đến terminal signal.

### Đo reactive publisher

Ví dụ dùng `Timer.Sample` và `doFinally`:

```java
public Mono<ProductDocument> saveReactive(ProductDocument document) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        AtomicReference<String> outcome = new AtomicReference<>("success");

        return reactiveOperations.save(document)
            .doOnError(error -> outcome.set(classifyOutcome(error)))
            .doFinally(signal -> sample.stop(
                Timer.builder("app.elasticsearch.write")
                    .tag("operation", "save")
                    .tag("outcome", outcome.get())
                    .register(registry)
            ));
    });
}
```

`doFinally` chạy khi publisher complete, error hoặc cancel, vì vậy timer đo toàn bộ lifecycle subscription. Trong production, `classifyOutcome` nên trả một tập giá trị hữu hạn như `success`, `conflict`, `rejected`, `timeout`, `client_error`, `server_error` hoặc `cancelled`; không dùng exception message làm metric tag.

Với `Flux`, quyết định timer đo toàn bộ stream hay từng phần tử. Nếu đo cả stream, thời gian sẽ phụ thuộc số phần tử và consumer demand; nếu đo từng request search page, đặt timer quanh thao tác request cụ thể.

## 7. Theo dõi lỗi bằng Counter

`Counter` phù hợp để đếm số lỗi hoặc sự kiện theo loại:

```java
Counter.builder("app.elasticsearch.errors")
    .description("Elasticsearch operation failures")
    .tag("operation", "bulk")
    .tag("error_type", "rejected")
    .register(registry)
    .increment();
```

Không tạo một counter mới cho từng exception message. Tag phải là tập giá trị hữu hạn và ổn định để tránh cardinality tăng không kiểm soát.

### Tỷ lệ lỗi

Có thể đếm tổng operation và operation lỗi riêng:

```java
Counter.builder("app.elasticsearch.operations")
    .tag("operation", "search")
    .register(registry)
    .increment();

Counter.builder("app.elasticsearch.errors")
    .tag("operation", "search")
    .tag("error_type", "timeout")
    .register(registry)
    .increment();
```

Tỷ lệ lỗi trong một cửa sổ thời gian:

\[
\text{Error rate} = \frac{\text{failed operations}}{\text{total operations}} \times 100\%
\]

Với bulk, nên tính thêm tỷ lệ item lỗi:

\[
\text{Bulk item failure rate} = \frac{\text{failed items}}{\text{submitted items}} \times 100\%
\]

Đừng cộng lẫn HTTP request failure và item failure vì chúng có mẫu số khác nhau.

## 8. Tránh metric cardinality cao

Metric label/tag được dùng để phân nhóm time series. Nếu đưa giá trị có thể tăng gần như vô hạn vào tag, hệ thống metrics có thể tiêu tốn nhiều memory và làm Prometheus hoặc backend giám sát quá tải.

Không nên dùng các tag như:

- Document ID.
- User ID hoặc email.
- Request ID/correlation ID.
- Query text nguyên văn.
- Exception message.
- Timestamp chính xác.
- URL chứa ID động.

Nên dùng tag có cardinality thấp:

- `operation=search|save|bulk|delete`.
- `outcome=success|error|cancelled`.
- `error_type=timeout|rejected|conflict|mapping|other`.
- `workload=interactive|dashboard|bulk_import`.
- `index_alias=products|orders` nếu tập alias nhỏ, ổn định.

Thông tin chi tiết theo request nên nằm trong trace/log có sampling và retention phù hợp, không phải metric label.

## 9. Đo thông lượng

Throughput thể hiện số lượng công việc hoàn tất trong một khoảng thời gian. Tùy workload, cần đo nhiều loại throughput:

- Search requests per second.
- Documents indexed per second.
- Bulk requests per second.
- Bulk items succeeded per second.
- Events consumed per second.
- Bytes indexed per second.
- Search hits returned per second nếu đây là chỉ số sản phẩm cần quan sát.

Ví dụ:

\[
\text{Documents/sec} = \frac{\text{successful indexed documents}}{\text{elapsed seconds}}
\]

Với bulk, nên đếm item thành công thay vì chỉ đếm bulk request. Một request có 500 item và một request có 5 item không đóng góp cùng throughput.

### Counter và rate

Micrometer `Counter` tăng theo số document thành công. Backend metrics như Prometheus có thể tính rate theo cửa sổ thời gian. Nếu ghi throughput trực tiếp, phải xác định rõ đơn vị và thời gian đo để tránh nhầm counter tích lũy với rate tức thời.

Ví dụ:

```java
Counter.builder("app.elasticsearch.documents.indexed")
    .description("Number of successfully indexed documents")
    .tag("index", "products")
    .register(registry)
    .increment(successCount);
```

Chỉ tăng `successCount` sau khi đã kiểm tra item response thành công, không tăng theo số item gửi đi.

## 10. Đo throughput và partial failure của Bulk API

Bulk API có thể trả HTTP 200 trong khi `errors: true`. Vì vậy, sau mỗi response cần duyệt item:

```java
int submitted = response.items().size();
int succeeded = 0;
int failed = 0;

for (BulkResponseItem item : response.items()) {
    if (item.error() == null) {
        succeeded++;
    } else {
        failed++;
        recordBulkItemFailure(item);
    }
}

registry.counter("app.elasticsearch.bulk.items", "outcome", "submitted")
    .increment(submitted);
registry.counter("app.elasticsearch.bulk.items", "outcome", "success")
    .increment(succeeded);
registry.counter("app.elasticsearch.bulk.items", "outcome", "failure")
    .increment(failed);
```

Kiểu `BulkResponseItem` và accessor phụ thuộc client/API được dùng; đoạn code minh họa cách tính. Trong implementation thực tế, ánh xạ response item của Elasticsearch Java API Client hoặc Spring Data response type đúng version.

Nên phân loại failed item theo loại lỗi và theo dõi retry riêng:

- Submitted items.
- Successful items on first attempt.
- Retried items.
- Successful items after retry.
- Permanent failures/DLQ.
- Items still pending.

Nhờ vậy, throughput ban đầu không bị đánh đồng với throughput cuối cùng sau retry.

## 11. Đo độ trễ của bulk request

Một bulk job có thể có throughput cao nhưng từng batch mất quá lâu. Đo thời gian mỗi bulk request và phân tích theo batch size:

- Batch item count.
- Payload bytes.
- Request duration p50/p95/p99.
- Item success/failure count.
- Retry count.
- Number of concurrent bulk requests.

Không đưa batch size chính xác hoặc document ID vào metric tag nếu chúng tạo quá nhiều time series. Có thể dùng histogram cho duration và ghi batch size/payload bytes ở log hoặc metric distribution phù hợp.

Nếu p95 tăng khi batch size tăng nhưng throughput không tăng tương ứng, batch có thể đã quá lớn. Nếu latency ổn định nhưng throughput thấp và CPU/cluster còn dư, có thể thử tăng concurrency có kiểm soát.

## 12. Theo dõi độ trễ đồng bộ (synchronization lag)

Độ trễ đồng bộ là khoảng thời gian từ khi dữ liệu thay đổi ở nguồn chuẩn đến khi thay đổi đó được phản ánh trong search projection và có thể được truy vấn.

Một luồng event-driven có thể có các mốc:

```text
Source transaction commit
          |
          v
Outbox event created
          |
          v
Event published to broker
          |
          v
Consumer receives event
          |
          v
Projection transformation
          |
          v
Elasticsearch write acknowledged
          |
          v
Index refresh
          |
          v
Document becomes searchable
```

Các timestamp hữu ích:

- `source_committed_at`: thời điểm nguồn chuẩn commit thay đổi.
- `event_created_at`: thời điểm event được tạo.
- `event_published_at`: thời điểm publisher gửi event.
- `event_received_at`: thời điểm consumer nhận event.
- `projection_started_at`: thời điểm bắt đầu xử lý.
- `elasticsearch_acknowledged_at`: thời điểm write được xác nhận.
- `search_visible_at`: thời điểm document đã searchable, nếu có cách đo đáng tin cậy.

Không nhất thiết phải lưu mọi timestamp trong document production. Có thể ghi trong event metadata, tracing span hoặc log/metrics. Điều quan trọng là dùng một định nghĩa thống nhất và đồng hồ được đồng bộ.

## 13. Phân rã sync lag thành từng đoạn

Tổng sync lag có thể được phân tích thành các thành phần:

\[
L_{total} = L_{publish} + L_{queue} + L_{processing} + L_{write} + L_{refresh}
\]

Trong đó:

- `L_publish`: từ source commit đến khi event được publish.
- `L_queue`: event nằm chờ trong broker trước khi consumer nhận.
- `L_processing`: thời gian deserialize, đọc nguồn liên quan, map projection và chuẩn bị bulk action.
- `L_write`: thời gian Elasticsearch xử lý và xác nhận write.
- `L_refresh`: từ khi write được xác nhận đến khi document có thể search.

Đây là mô hình phân tích; cách đo thực tế cần xác định rõ mốc timestamp và không cộng trùng các khoảng thời gian.

### Ví dụ

| Thành phần | p95 |
|---|---:|
| Publish | 100 ms |
| Queue wait | 4.000 ms |
| Processing | 250 ms |
| Elasticsearch write | 180 ms |
| Refresh visibility | 900 ms |
| Tổng xấp xỉ | 5.430 ms |

Trong ví dụ, queue wait là thành phần lớn nhất. Tăng tốc Elasticsearch write không giải quyết nguyên nhân chính; cần tăng consumer capacity, giảm nguồn event hoặc xử lý backlog.

## 14. Đo consumer lag và tuổi event

Nếu dùng Kafka, consumer lag thường được thể hiện qua chênh lệch offset giữa log end offset và consumer committed/current offset. Đây là chỉ số số lượng record chưa xử lý, không phải trực tiếp là thời gian trễ.

Nên theo dõi cả:

- Record/offset lag.
- Tuổi của event cũ nhất đang chờ.
- Thời gian xử lý event p50/p95/p99.
- Consumer throughput.
- Số partition đang bị chậm.
- Retry/DLQ count.

Một backlog 10.000 event có thể được xử lý trong vài giây nếu throughput cao, hoặc kéo dài nhiều giờ nếu consumer bị nghẽn. Event age giúp đo freshness trực tiếp hơn số record lag.

### Không chỉ đo timestamp của event mới nhất

Nếu consumer xử lý nhanh event mới nhưng một partition bị kẹt ở event cũ, timestamp của event vừa xử lý có thể khiến dashboard trông khỏe. Hãy quan sát oldest unprocessed event hoặc lag theo partition để phát hiện điểm nghẽn cục bộ.

## 15. Đo thời điểm searchable

Write acknowledgement và search visibility là hai mốc khác nhau. Một request `index` thành công không đồng nghĩa document lập tức xuất hiện trong search; document cần được refresh.

Có thể đo visibility lag bằng một trong các cách:

- Dùng `refresh=wait_for` trong workflow test/đo có kiểm soát và ghi thời gian chờ.
- Ghi event ID/source version vào document, sau đó kiểm tra search theo ID/version ở một probe có giới hạn.
- Đo khoảng từ bulk response tới lần refresh kế tiếp nếu có instrumentation phù hợp.
- Dùng một synthetic document canary định kỳ để đo source-to-search-visible.

Không nên thực hiện một search probe cho mọi document trong production chỉ để đo visibility; nó có thể tạo tải không cần thiết. Dùng sample hoặc canary và phân biệt metric đo trực tiếp với ước lượng.

### `refresh=wait_for` trong luồng ghi

`wait_for` chờ lần refresh tiếp theo làm thay đổi searchable. Nó không ép refresh ngay như `refresh=true`, nhưng thời gian chờ có thể tăng nếu refresh bị trì hoãn hoặc periodic refresh tắt. Dùng có chọn lọc cho read-after-write cần thiết, không thêm vào mọi bulk request chỉ để dashboard lag đẹp hơn.

## 16. Đo sync lag bằng source version

Ngoài timestamp, version nghiệp vụ có thể giúp phát hiện projection tụt hậu. Ví dụ nguồn chuẩn phát `aggregateVersion=42` và search document lưu `sourceVersion=41`; projection chưa áp dụng thay đổi mới nhất.

Các chỉ số có thể theo dõi:

- Số aggregate có source version mới hơn projection version.
- Khoảng cách version nếu version tăng đơn điệu.
- Số event bị bỏ qua vì cũ hoặc trùng.
- Số document chưa có projection.
- Số projection version không tương thích.

Không phải version gap luôn tương đương số event bị mất; version có thể tăng do thay đổi không liên quan tới projection hoặc event bị gộp. Hãy định nghĩa semantics của version trước khi dùng làm SLI.

## 17. Dùng timestamp và đồng hồ nhất quán

Đo sync lag bằng cách trừ timestamp từ nhiều service đòi hỏi đồng hồ được đồng bộ. Nếu máy nguồn nhanh hơn máy consumer 2 giây, phép tính có thể tạo lag âm hoặc sai lệch.

Khuyến nghị:

- Đồng bộ host/container clock qua NTP hoặc cơ chế thời gian của nền tảng.
- Lưu timestamp ở UTC, ưu tiên `Instant`.
- Phân biệt event time và processing time.
- Ghi timestamp theo một định dạng thống nhất.
- Xử lý trường hợp event đến muộn hoặc timestamp nguồn bị sai.
- Dùng broker offset/monotonic sequence để đo backlog bổ sung khi timestamp không đáng tin.

Trong code Java, dùng `Clock` được inject để dễ kiểm thử và tránh logic thời gian rải rác.

## 18. Theo dõi lỗi theo taxonomy

Không gom mọi lỗi thành một counter `error`. Các loại lỗi có ý nghĩa vận hành khác nhau:

| Nhóm | Ví dụ | Ý nghĩa | Hành động thường gặp |
|---|---|---|---|
| Validation/client | 400, invalid query, mapping input sai | Request hoặc dữ liệu đầu vào không hợp lệ | Sửa caller/payload; không retry mù quáng |
| Authorization | 401/403 | Credential hoặc quyền không đủ | Kiểm tra auth/role; không retry liên tục |
| Not found | 404 document/index | ID hoặc index không tồn tại | Kiểm tra semantics; có thể là kết quả hợp lệ |
| Version conflict | 409 | Document đã thay đổi | Đọc lại token, đánh giá nghiệp vụ và retry có điều kiện |
| Rejection/overload | 429, rejected execution | Cluster không nhận thêm tải | Backoff, giảm concurrency và backlog |
| Timeout/network | timeout, connection reset | Không rõ request đã được xử lý tới đâu | Kiểm tra idempotency trước retry |
| Server/transient | 5xx | Lỗi tạm thời hoặc cluster gặp sự cố | Retry có giới hạn, kiểm tra cluster |
| Mapping/serialization | mapper parsing, conversion exception | Source không tương thích mapping/model | Sửa dữ liệu hoặc mapping, DLQ nếu cần |
| Partial bulk | Một số item thất bại | Request thành công một phần | Phân loại từng item |

### Đừng retry mọi exception

Retry lỗi validation hoặc mapping không làm chúng tự hết. Retry conflict bằng cùng `if_seq_no`/`if_primary_term` cũ cũng sẽ tiếp tục conflict. Retry timeout có thể lặp một thao tác đã thành công nhưng response bị mất. Chính sách retry phải dựa trên error type và tính idempotent của thao tác.

## 19. Theo dõi Elasticsearch bằng Node Stats

Elasticsearch cung cấp Node Stats API để xem tài nguyên và hoạt động của từng node:

```http
GET /_nodes/stats
```

Có thể chỉ lấy một số nhóm thống kê để giảm payload:

```http
GET /_nodes/stats/jvm,process,os,fs,thread_pool,indices,breaker
```

Các nhóm đáng chú ý:

- `jvm`: heap, garbage collection và memory pressure.
- `process`/`os`: CPU và tài nguyên hệ điều hành.
- `fs`: dung lượng và hoạt động filesystem.
- `thread_pool`: active, queue và rejected theo pool.
- `indices`: search, indexing, refresh, merge, query cache và request cache.
- `breaker`: circuit breaker trips và estimated usage.
- `indexing_pressure`: áp lực memory liên quan tới indexing nếu version hỗ trợ.

Node Stats là dữ liệu cấp cluster/node; cần kết hợp với app metrics để biết request nào tạo tải. Tránh poll toàn bộ stats với tần suất quá cao hoặc parse mọi trường nếu dashboard chỉ cần một số tín hiệu.

## 20. Theo dõi Index Stats

Index Stats giúp khoanh vùng theo index:

```http
GET /products/_stats
```

Có thể giới hạn metric cần lấy:

```http
GET /products/_stats/indexing,search,refresh,merge,segments,store
```

Các trường hữu ích:

| Nhóm | Chỉ số cần quan sát | Ý nghĩa |
|---|---|---|
| `indexing` | `index_total`, `index_time_in_millis`, `index_failed` | Số thao tác index, thời gian và lỗi |
| `search` | `query_total`, `query_time_in_millis`, `fetch_total`, `fetch_time_in_millis` | Lượng search và thời gian query/fetch |
| `refresh` | `total`, `total_time_in_millis` | Tần suất và chi phí refresh |
| `merge` | `total`, `total_time_in_millis`, `current` | Hoạt động merge segment |
| `segments` | số segment, memory | Phân mảnh segment và bộ nhớ liên quan |
| `store` | size | Dung lượng index |

Các bộ đếm thường là giá trị tích lũy từ khi node/index khởi động hoặc từ lần reset phù hợp. Khi tính rate, lấy chênh lệch giữa hai lần scrape cùng node/index trong một khoảng thời gian, xử lý trường hợp counter reset hoặc node restart.

## 21. Theo dõi thread pool và rejection

Khi search hoặc bulk chậm, cần xem thread pool queue và rejected count:

```http
GET /_nodes/stats/thread_pool
```

Các trường thường quan tâm:

- `active`: số thread đang hoạt động.
- `queue`: số task đang chờ.
- `rejected`: số task bị từ chối.
- `completed`: số task hoàn tất.

Tên pool và cách tổ chức thay đổi theo Elasticsearch version. Không dựa vào tên pool cũ từ một bài hướng dẫn khác mà không kiểm tra cluster thực tế.

Nếu queue tăng liên tục, latency thường tăng trước khi rejection xuất hiện. Nếu rejected tăng, cluster đã từ chối một phần công việc. Cần xác định pool nào bị áp lực và loại request tương ứng; không chỉ tăng queue size vì điều đó có thể làm request chờ lâu hơn và tiêu thụ memory.

## 22. Theo dõi indexing pressure, heap và merge

Indexing pressure cho biết áp lực bộ nhớ do hoạt động indexing trên node. Heap cao kéo dài và GC pause lớn có thể làm tăng latency ở cả search lẫn write. Merge tiêu tốn CPU và I/O khi các segment được hợp nhất.

Khi ingestion throughput tăng nhưng search latency xấu đi, xem đồng thời:

- Indexing pressure và rejection.
- JVM heap usage và GC pause.
- Merge current/total time.
- Refresh frequency và segment count.
- Disk I/O và filesystem saturation.
- Shard distribution và hot shard.

Không kết luận “Elasticsearch chậm” chỉ từ CPU cao. Một workload bulk có thể làm merge hoặc disk I/O thành bottleneck; một query aggregation có thể gây heap pressure; một shard nóng có thể chậm trong khi node trung bình vẫn bình thường.

## 23. Cluster health và shard allocation

Cluster Health API:

```http
GET /_cluster/health
```

Các trạng thái:

- `green`: primary và replica shards đều được allocate.
- `yellow`: primary shards được allocate nhưng một số replica chưa được allocate.
- `red`: có primary shard chưa được allocate; một phần dữ liệu có thể không truy cập được.

Cluster health quan trọng nhưng không phải chỉ số latency/throughput. Cluster `green` vẫn có thể quá tải, query chậm hoặc consumer lag. Ngược lại, cluster `yellow` trong một môi trường single-node có thể là trạng thái thiết kế nếu replica không thể được allocate trên cùng node.

Theo dõi thêm unassigned shards, relocating shards và pending tasks khi điều tra thay đổi hiệu năng.

## 24. Slow logs và query profiling

Elasticsearch search slow logs ghi lại query hoặc fetch phase vượt ngưỡng cấu hình. Indexing slow logs có thể ghi các thao tác index chậm. Đây là công cụ điều tra những query/document cụ thể gây chậm.

Slow log hữu ích để:

- Tìm query có latency cao.
- Phân biệt query phase và fetch phase.
- Nhận diện shard hoặc index có workload bất thường.
- Phát hiện mapping/query pattern không phù hợp.

Không nên đặt threshold quá thấp hoặc log mọi request; log volume có thể tăng nhanh và gây overhead. Điều chỉnh theo workload, bật có chọn lọc và bảo vệ nội dung log nếu query/source có dữ liệu nhạy cảm.

Search Profile API giải thích cách Elasticsearch thực thi query ở mức chi tiết, nhưng có overhead và không đại diện chính xác cho latency production bình thường. Dùng profile để điều tra có mục tiêu, không bật trên mọi request.

## 25. Distributed tracing từ API đến Elasticsearch

Metrics cho biết xu hướng; trace cho biết một request cụ thể đi qua những bước nào. Một trace cho search request có thể có các span:

```text
HTTP GET /products/search
  ├── authenticate-and-authorize
  ├── build-search-query
  ├── elasticsearch.search
  │     ├── connection-acquire
  │     └── client-request
  ├── map-search-hits
  └── serialize-response
```

Với ingestion:

```text
consume ProductUpdated
  ├── load-source-data
  ├── build-projection
  ├── elasticsearch.bulk
  ├── inspect-item-results
  └── acknowledge-event
```

Micrometer Observation và OpenTelemetry có thể kết nối metric/tracing theo cấu hình Spring Boot. Tên span và auto-instrumentation phụ thuộc client/version; nếu client không tự tạo span, có thể bọc operation bằng Observation/Timer ở tầng service.

### Correlation ID và trace ID

Giữ trace/correlation ID xuyên suốt API, event, consumer và projector nếu kiến trúc cho phép. Event có thể mang `correlationId` hoặc `causationId` để liên kết thay đổi nguồn với thao tác cập nhật projection.

Không dùng trace ID làm metric label. Dùng nó trong log/trace để tra cứu một execution cụ thể.

## 26. Ghi log có cấu trúc

Log nên giúp trả lời:

- Operation nào chậm hoặc thất bại?
- Request/event thuộc index alias nào?
- Bulk batch có bao nhiêu item và byte?
- Có bao nhiêu item thành công, retry hoặc vào DLQ?
- Source version nào được xử lý?
- Event đã nằm trong queue bao lâu?
- Trace/correlation ID là gì?

Ví dụ log cấu trúc:

```json
{
  "event": "elasticsearch.bulk.completed",
  "index_alias": "products-write",
  "batch_size": 500,
  "payload_bytes": 4200000,
  "success_count": 497,
  "failure_count": 3,
  "duration_ms": 245,
  "retryable_count": 2,
  "permanent_failure_count": 1,
  "trace_id": "..."
}
```

Log mẫu không chứa document source hoặc dữ liệu cá nhân. Với item lỗi, ghi ID đã được bảo vệ/ẩn danh theo chính sách và error category; không log access token, secret hoặc toàn bộ payload nhạy cảm.

### Log và metric có vai trò khác nhau

- Metric: xu hướng, tỷ lệ, percentile và alert.
- Log: chi tiết sự kiện và nguyên nhân cho một lần thực thi.
- Trace: thứ tự và thời gian giữa các bước trong một request/job.

Không cố dùng log thay cho metric time series hoặc metric thay cho log chi tiết.

## 27. Dashboard vận hành nên có gì?

Một dashboard cho Spring Data Elasticsearch có thể chia thành các khu vực:

### Search/API

- Request rate.
- p50/p95/p99 latency theo endpoint/workload.
- Error rate theo status/error category.
- Timeout và client connection errors.
- Elasticsearch `took` so với end-to-end latency.
- Hits/page size và response bytes.

### Indexing/Bulk

- Bulk requests/s.
- Documents/items succeeded per second.
- Item failure rate theo loại.
- Batch size/payload bytes.
- Bulk latency p50/p95/p99.
- 429/rejected và retry count.
- In-flight bulk requests.

### Synchronization

- Events received/processed per second.
- Consumer lag theo partition.
- Oldest event age.
- Source-to-search-visible lag p50/p95/p99.
- Retry queue/DLQ depth.
- Source version so với projection version.

### Elasticsearch cluster

- Cluster health và unassigned shards.
- CPU, heap, GC pause.
- Search/index thread pool active, queue, rejected.
- Indexing pressure.
- Refresh/merge time.
- Disk I/O, free disk và shard distribution.

Nên có dashboard tổng quan cho on-call và dashboard chuyên sâu theo workload. Mọi chart cần ghi rõ đơn vị, cửa sổ thời gian và mẫu số.

## 28. Thiết kế alert có hành động

Alert nên phản ánh ảnh hưởng dịch vụ và gợi ý hướng điều tra. Tránh alert chỉ vì một counter tăng đơn lẻ trong thời gian ngắn.

Ví dụ nhóm alert:

| Alert | Điều kiện ví dụ | Hướng điều tra |
|---|---|---|
| Search latency high | p95 vượt SLO trong nhiều cửa sổ liên tiếp | Query latency, `took`, shard, thread pool, network |
| Search error rate high | Tỷ lệ 5xx/timeout vượt ngưỡng | Cluster health, connection pool, breaker, node logs |
| Bulk rejection | 429/rejected tăng liên tục | Giảm concurrency, indexing pressure, thread pool |
| Bulk item failure | Mapping/permanent failures vượt ngưỡng | Mapping, payload schema, DLQ |
| Sync lag high | Oldest event age hoặc source-to-visible p95 vượt SLO | Consumer lag, processing, write, refresh |
| Backlog growing | Arrival rate lớn hơn processing rate kéo dài | Consumer capacity, downstream throughput |
| Cluster degraded | Red health hoặc unassigned primary | Allocation, disk, node failure |

Các ngưỡng cụ thể phải dựa trên SLO và baseline. Alert nên có thời gian duy trì (for duration) hoặc burn-rate logic để tránh cảnh báo do một spike ngắn không ảnh hưởng đáng kể.

## 29. Phân biệt backlog count và backlog age

Backlog count cho biết còn bao nhiêu event đang chờ. Backlog age cho biết event cũ nhất đã chờ bao lâu.

Ví dụ:

| Tình huống | Backlog count | Oldest age | Diễn giải |
|---|---:|---:|---|
| A | 50.000 | 5 giây | Throughput xử lý cao, có thể đang nhận batch lớn |
| B | 500 | 20 phút | Có thể một partition/job bị kẹt |
| C | 10.000 | 15 phút và tăng | Consumer đang tụt lại phía sau |

Không alert chỉ theo count nếu tốc độ xử lý đủ cao. Ngược lại, backlog nhỏ nhưng event age lớn có thể cho thấy một event poison hoặc partition bị block.

## 30. Xác định bottleneck bằng quan hệ giữa các chỉ số

Một số mẫu chẩn đoán thường gặp:

| Quan sát | Nguyên nhân có thể | Bước tiếp theo |
|---|---|---|
| API latency tăng, ES `took` ổn định | Gateway, network, connection pool, mapping response | Xem trace span và client metrics |
| ES `took` tăng, search queue tăng | Search node/thread pool quá tải | Xem query, shard, CPU, heap và concurrency |
| Bulk latency tăng, 429 tăng | Ingestion vượt năng lực cluster | Giảm bulk concurrency/batch, backoff |
| Bulk write nhanh nhưng sync lag cao | Consumer queue hoặc publish chậm | Xem oldest event age và consumer throughput |
| Write ack nhanh nhưng search visibility chậm | Refresh interval hoặc refresh bị trì hoãn | Đo refresh lag và kiểm tra refresh policy |
| Average ổn định nhưng p99 tăng | Hot shard, outlier query, GC hoặc queue burst | Phân tích tail traces và shard/node metrics |
| Error rate tăng nhưng HTTP 200 không đổi | Bulk item partial failures | Kiểm tra `errors` và từng item response |
| CPU thấp nhưng latency cao | Network, lock/queue, storage I/O hoặc downstream | Xem span, disk, connection pool và queue |

Đây là các giả thuyết điều tra, không phải kết luận tự động. Dùng trace/log và thay đổi từng yếu tố để xác nhận nguyên nhân.

## 31. Đo freshness bằng synthetic canary

Một canary có thể tạo document có ID duy nhất, ghi timestamp nguồn, rồi định kỳ search document đó và đo thời gian cho tới khi xuất hiện.

```text
Canary writer
    |
    | write {id, createdAt}
    v
Elasticsearch index
    |
    | periodic search probe
    v
Canary reader
    |
    v
visibleAt - createdAt = observed visibility lag
```

Canary nên:

- Dùng index/tenant riêng hoặc namespace an toàn.
- Có tần suất thấp, không gây tải đáng kể.
- Có cleanup/retention cho document canary.
- Dùng timestamp UTC và đồng hồ đồng bộ.
- Đo riêng write ack và search-visible time.
- Báo động khi canary không xuất hiện trong ngưỡng cho phép.

Canary đo đường đi tổng thể nhưng không thay thế metric consumer lag theo partition. Nó là phép đo end-to-end bổ sung hữu ích.

## 32. Theo dõi đồng bộ khi dùng Outbox hoặc CDC

Với transactional outbox, theo dõi:

- Số row outbox chưa publish.
- Tuổi row chưa publish cũ nhất.
- Publish attempts và lỗi.
- Thời gian từ commit tới publish.
- Số row được cleanup.

Với CDC, theo dõi:

- Source log position/offset.
- Connector lag.
- Số change event phát ra.
- Connector restart/failure.
- Schema change/error.
- Consumer lag ở downstream.

Nếu projector đọc lại trạng thái nguồn thay vì dùng payload event, đo thêm latency của các lần gọi source service/database. Nếu nhiều source được kết hợp, có thể một dependency chậm làm toàn bộ projection lag.

## 33. Theo dõi retry và DLQ

Retry là một phần của throughput và sync lag. Nếu chỉ đếm event thành công cuối cùng, một hệ thống retry liên tục có thể trông khỏe nhưng tiêu tốn tài nguyên lớn và kéo dài freshness.

Theo dõi:

- Retry attempts per event/item.
- Retry delay và thời gian nằm trong retry queue.
- Tỷ lệ retry thành công.
- Số event vượt max attempts.
- DLQ depth và oldest message age.
- Replay success/failure.
- Lý do permanent failure.

DLQ có message không nhất thiết là sự cố nếu có quy trình xử lý, nhưng DLQ tăng liên tục hoặc message cũ vượt retention/SLO cần alert. Cần có dashboard và runbook để sửa dữ liệu rồi replay an toàn.

## 34. Tích hợp Observation/Tracing trong Spring

Spring Boot có thể tích hợp Micrometer Observation để tạo observation thống nhất, từ đó nối metric và tracing theo registry/exporter đã cấu hình.

Ví dụ khái niệm bọc thao tác service:

```java
Observation.createNotStarted("product.search", observationRegistry)
    .lowCardinalityKeyValue("operation", "search")
    .observe(() -> searchService.execute(query));
```

Với publisher reactive, cần dùng API Observation/reactive instrumentation phù hợp với phiên bản Spring/Micrometer để span bao trọn lifecycle subscription, không chỉ thời gian tạo publisher. Nếu dùng `Mono`/`Flux`, kiểm tra tích hợp context propagation và instrumentation của client.

### Low-cardinality và high-cardinality key values

- Low-cardinality: operation, outcome, workload; có thể dùng cho metric.
- High-cardinality: trace ID, request ID, document ID; chỉ dùng trong trace/log khi cần.

Không đưa high-cardinality key vào metric dimension.

## 35. Kiểm thử metrics và instrumentation

Instrumentation cũng cần được kiểm thử ở mức phù hợp:

- Thành công tăng operation counter và ghi timer.
- Error tăng error counter đúng category.
- Bulk item success/failure được đếm theo item, không chỉ theo request.
- Cancellation được phân loại nếu nghiệp vụ cần.
- Retry counter tăng theo số lần thực sự thử lại.
- Queue gauge phản ánh độ sâu hiện tại.
- Metric tags không chứa ID hoặc message động.
- Reactive timer chỉ dừng khi publisher terminal/cancel.

Micrometer cung cấp `SimpleMeterRegistry` phù hợp cho unit test:

```java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

// Invoke the instrumented service and verify its publisher with StepVerifier.

assertThat(registry.get("app.elasticsearch.errors")
    .tag("operation", "search")
    .counter()
    .count()).isEqualTo(1.0);
```

Đây là khung minh họa; test cần đăng ký registry vào service và kiểm tra đúng tên/tag metric mà implementation tạo ra. Với timer, có thể kiểm tra count và total time thay vì assert một duration chính xác phụ thuộc scheduler.

## 36. Runbook khi latency hoặc sync lag tăng

Khi có alert, điều tra theo thứ tự:

1. Xác định workload bị ảnh hưởng: search, dashboard, bulk hay sync pipeline.
2. Kiểm tra SLI: p95/p99, error rate, throughput và oldest event age.
3. So sánh API latency với Elasticsearch `took`/client latency.
4. Xem trace mẫu để xác định span chậm.
5. Kiểm tra node health, CPU, heap, GC, disk và shard allocation.
6. Kiểm tra thread pool queue/rejected và indexing pressure.
7. Với bulk, xem batch size, concurrency, 429, item failure và retry.
8. Với sync lag, xem publish lag, consumer lag, processing time, write time và refresh lag.
9. Xác định thay đổi gần đây: deployment, mapping, query, refresh interval, shard/replica hoặc ingest pipeline.
10. Áp dụng giảm tải có kiểm soát: hạ concurrency, pause consumer, giảm batch hoặc tách workload.
11. Theo dõi metric sau thay đổi và xác nhận backlog/latency hồi phục.
12. Ghi lại nguyên nhân và hành động phòng ngừa.

Không tăng thread pool hoặc queue size ngay khi thấy rejection mà chưa xác định bottleneck. Tăng queue có thể biến lỗi từ từ chối nhanh thành chờ lâu và heap pressure lớn hơn.

## 37. Quy trình triển khai observability

Một trình tự triển khai thực tế:

1. Liệt kê operation quan trọng: search, get, save, update, delete, bulk và projector.
2. Định nghĩa latency, error, throughput và sync lag với đơn vị/mẫu số rõ ràng.
3. Chọn SLI/SLO theo workload và freshness requirement.
4. Thêm Micrometer Timer/Counter/Gauge ở application boundary.
5. Bổ sung metrics theo item cho Bulk API và retry/DLQ.
6. Bật Actuator/Prometheus hoặc exporter phù hợp và bảo vệ endpoint.
7. Thu thập Elasticsearch Node Stats, Index Stats và Cluster Health.
8. Thêm trace/correlation xuyên API, event consumer và projector.
9. Ghi timestamp/version ở các mốc đồng bộ để tính lag.
10. Xây dashboard tách Search, Bulk, Sync và Cluster.
11. Tạo alert dựa trên SLO, backlog age và rejection.
12. Viết runbook, kiểm thử instrumentation và diễn tập một số tình huống lỗi.

## 38. Kết luận

Theo dõi Elasticsearch hiệu quả cần kết hợp latency, errors, throughput và synchronization lag. Đo end-to-end latency ở ứng dụng, tách client time khỏi Elasticsearch `took`, dùng p50/p95/p99 để nhìn tail latency và định nghĩa success rate đúng mẫu số. Với bulk, đếm item thành công/thất bại thay vì chỉ đếm request. Với đồng bộ bất đồng bộ, đo event age và phân rã lag thành publish, queue, processing, write và refresh visibility.

Trong Spring Boot/Spring Data Elasticsearch, Micrometer Timer/Counter/Gauge và Actuator giúp phát metric; Elasticsearch Node Stats, Index Stats, thread pool, indexing pressure, refresh và merge giúp giải thích tải phía cluster; tracing/log có cấu trúc giúp điều tra từng request/event. Đặt SLI/SLO theo workload, tránh metric cardinality cao, bảo vệ endpoint giám sát và tạo alert có runbook. Khi các tín hiệu được định nghĩa nhất quán từ nguồn commit tới search-visible, đội vận hành có thể biết hệ thống chậm ở đâu, lỗi thuộc loại nào, cluster đang xử lý được bao nhiêu việc và dữ liệu tìm kiếm đang tụt hậu bao lâu.

## Tài liệu tham khảo

- [Spring Boot – Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer – Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Elasticsearch – Node Stats API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-nodes-stats)
- [Elasticsearch – Index Stats API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-stats)
- [Elasticsearch – Cluster Health API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-cluster-health)
- [Elasticsearch – Search slow log](https://www.elastic.co/docs/deploy-manage/monitor/logging-configuration/slow-logs)
- [Elasticsearch – Indexing slow log](https://www.elastic.co/docs/deploy-manage/monitor/logging-configuration/slow-logs)
- [OpenTelemetry – Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
