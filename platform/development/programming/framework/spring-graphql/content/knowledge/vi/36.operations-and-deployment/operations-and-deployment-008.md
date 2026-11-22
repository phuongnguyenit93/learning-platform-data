# Metrics và alert GraphQL

GraphQL gom nhiều field vào một endpoint. Một HTTP request có thể chạy một query đơn giản, một mutation có nhiều bước hoặc một query lồng sâu với nhiều DataFetcher và DataLoader. Vì vậy, chỉ theo dõi số HTTP request và thời gian phản hồi tổng thể chưa đủ để biết GraphQL đang chậm ở resolver nào, lỗi xuất phát từ đâu hay DataLoader có giảm được N+1 hay không.

Spring for GraphQL tích hợp Micrometer Observation để đo thời gian và tạo trace cho GraphQL request, các DataFetcher không tầm thường và DataLoader. Spring Boot Actuator đưa các meter này tới hệ thống giám sát như Prometheus, Datadog hoặc OTLP. Từ các tín hiệu đó, đội vận hành có thể xây dashboard, xác định SLI/SLO và tạo alert khi người dùng thực sự bị ảnh hưởng.

Bài học này đi từ các observation mặc định của Spring for GraphQL đến cấu hình Actuator, histogram và PromQL, sau đó xây alert có thời gian duy trì, dashboard, runbook, kiểm soát cardinality và quy trình kiểm thử monitoring.

## 1. Vì sao GraphQL cần metrics riêng?

Giả sử client gửi query:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      id
      name
    }
    reviews {
      rating
      reviewer {
        name
      }
    }
  }
}
~~~

Một HTTP request này có thể kích hoạt:

1. Root DataFetcher tải Book.
2. Resolver Author tải tác giả.
3. Resolver Reviews tải danh sách review.
4. Resolver Reviewer tải người đánh giá cho từng review.
5. DataLoader gom các lần tải Reviewer thành batch.

Nếu chỉ đo HTTP latency, bạn biết request mất 900 ms nhưng chưa biết 850 ms nằm ở database, remote service, resolver Reviews hay nhiều lần tải Reviewer.

Các lớp metrics cần quan sát:

| Lớp | Câu hỏi cần trả lời | Tín hiệu |
| --- | --- | --- |
| Transport | HTTP/WebSocket có lỗi hoặc nghẽn không? | HTTP server metrics, connection metrics |
| GraphQL request | Operation nào chậm, tỷ lệ lỗi bao nhiêu? | **graphql.request** |
| DataFetcher | Resolver nào thường chậm hoặc lỗi? | **graphql.datafetcher** |
| DataLoader | Batch loader nào chậm hoặc lỗi? | **graphql.dataloader** |
| Infrastructure | JVM, database pool, executor có cạn tài nguyên? | JVM, datasource, pool và executor metrics |

Metrics trả lời xu hướng và mức độ ảnh hưởng. Traces và logs giúp tìm một request cụ thể. Ba loại telemetry cần liên kết với nhau.

## 2. Metrics, traces và logs khác nhau

| Loại telemetry | Dùng để | Ví dụ |
| --- | --- | --- |
| Metrics | Đo xu hướng tổng hợp, cảnh báo và SLO | p95 latency, error ratio, request rate |
| Traces | Theo dấu một request qua nhiều thành phần | GraphQL request → DataFetcher → HTTP client → database |
| Logs | Lưu chi tiết một sự kiện hoặc lỗi | Exception, operation name, execution ID, error path |

Không ghi toàn bộ GraphQL document và variables vào metric. Query text có thể chứa thông tin nhạy cảm, còn mỗi document hoặc biến thể query có thể tạo một series riêng nếu đưa vào label.

Một quy trình điều tra thường là:

1. Alert cho biết p95 GraphQL latency vượt SLO.
2. Dashboard cho thấy **graphql.request** tăng nhưng transport latency không tăng tương ứng.
3. Drill down theo **graphql.field.name** để thấy resolver Reviews chậm.
4. Mở trace tương ứng bằng execution ID hoặc trace ID.
5. Kiểm tra log để tìm lỗi database hoặc remote service.

## 3. Ba observation mặc định của Spring for GraphQL

Spring for GraphQL tích hợp Micrometer Observation. Khi **ObservationRegistry** được cấu hình và **GraphQlObservationInstrumentation** được đăng ký, instrumentation tạo ba observation chính:

| Observation name | Phạm vi | Khi nào được tạo |
| --- | --- | --- |
| **graphql.request** | Toàn bộ GraphQL request execution | Query, mutation và subscription trên các transport được hỗ trợ |
| **graphql.datafetcher** | Một thao tác DataFetcher | Các DataFetcher không tầm thường; property fetcher đơn giản trên Java object không được tính |
| **graphql.dataloader** | Một lần gọi DataLoader | **@BatchMapping** và DataLoader đăng ký thủ công |

Observation có thể tạo cả Timer metric và span trace tùy cấu hình handler. Observation chỉ được publish khi ứng dụng có ObservationRegistry và các handler tương ứng.

### 3.1. graphql.request

**graphql.request** đo thời gian thực thi operation và thêm các KeyValue mặc định:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| **graphql.operation.type** | Low | query, mutation, subscription hoặc operation nếu không parse được document |
| **graphql.outcome** | Low | Kết quả xử lý GraphQL request |
| **graphql.execution.id** | High | Execution ID của request |
| **graphql.operation.name** | High | Operation name do client gửi |

graphql.operation.type hữu ích để tách tải query, mutation và subscription. Operation name và execution ID có thể có rất nhiều giá trị nên được dùng trong trace/log, không nên trở thành metric label.

Giá trị mặc định của graphql.outcome:

| Giá trị | Ý nghĩa trong Spring for GraphQL |
| --- | --- |
| SUCCESS | Response GraphQL hợp lệ và không có errors |
| REQUEST_ERROR | Request không parse được hoặc response có errors, miễn không có error thuộc loại INTERNAL_ERROR |
| INTERNAL_ERROR | Không tạo được GraphQL response hợp lệ hoặc response có ít nhất một error thuộc loại INTERNAL_ERROR |

**Lưu ý:** REQUEST_ERROR là tên outcome trong observation convention, không phải phép phân loại HTTP status. Một response có partial data và lỗi ở nested field cũng có thể mang outcome này. Vì vậy, không dùng điều kiện graphql.outcome khác SUCCESS làm server availability error ratio một cách máy móc.

### 3.2. graphql.datafetcher

**graphql.datafetcher** đo các DataFetcher không tầm thường. Property fetcher đơn giản đọc field từ Java object thường không tạo observation.

Các KeyValue mặc định:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| **graphql.error.type** | Low | Class name của lỗi khi DataFetcher thất bại |
| **graphql.field.name** | Low | Tên field đang được resolve |
| **graphql.outcome** | Low | SUCCESS hoặc ERROR |
| **graphql.field.path** | High | Đường dẫn field trong response, ví dụ /bookById/author |

graphql.field.name giúp tìm resolver chậm theo field. graphql.field.path có thể khác nhau giữa các nhánh dữ liệu hoặc alias nên được giữ ở high-cardinality metadata cho trace.

Không phải mọi field trong query đều có graphql.datafetcher observation. Khi một property được đọc trực tiếp từ object nguồn, không có DataFetcher tùy chỉnh để đo.

### 3.3. graphql.dataloader

**graphql.dataloader** quan sát các lần gọi @BatchMapping và DataLoader đăng ký thủ công.

Các KeyValue mặc định:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| **graphql.error.type** | Low | Class name của lỗi |
| **graphql.loader.name** | Low | Tên DataLoader |
| **graphql.outcome** | Low | SUCCESS hoặc ERROR |
| **graphql.loader.size** | High | Số phần tử được load trong batch |

graphql.loader.name hữu ích để so sánh các batch loader. graphql.loader.size có thể thay đổi theo từng request nên được đưa vào high-cardinality metadata, không nên dùng làm metric label mặc định.

Nếu cần histogram batch size để cảnh báo batch quá nhỏ hoặc quá lớn, hãy tạo metric riêng có loader name hữu hạn và ghi nhận size bằng DistributionSummary. Không chuyển trực tiếp high-cardinality key mặc định thành tag của Timer.

Ví dụ metric batch size riêng:

~~~java
DistributionSummary batchSize = DistributionSummary.builder("graphql.dataloader.batch.size")
        .description("Number of keys loaded by a DataLoader batch")
        .tag("loader", "bookAuthors")
        .register(meterRegistry);

batchSize.record(bookIds.size());
~~~

Chỉ dùng tag loader có danh sách hữu hạn, được kiểm soát bởi server. Nếu tên loader được tạo động theo tenant hoặc request, hãy chuẩn hóa nó về một nhóm cố định.

## 4. Bật GraphQL Observation trong Spring Boot

Với ứng dụng Spring Boot, các dependency thường dùng:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Spring Boot auto-configure ObservationRegistry khi có observability infrastructure. Các phiên bản Spring Boot 3.x và 4.x có auto-configuration cho GraphQL observation khi có ObservationRegistry và Spring GraphQL trên classpath. Kiểm tra phiên bản Boot đang dùng và không đăng ký instrumentation thủ công lần thứ hai nếu auto-configuration đã tạo bean.

Với ứng dụng Spring Framework không dùng Boot hoặc một cấu hình GraphQL tùy chỉnh, cần bảo đảm GraphQlObservationInstrumentation được gắn vào GraphQL source. API và cách đăng ký có thể khác theo phiên bản Spring for GraphQL; tham khảo Javadoc của dependency thực tế.

### Kiểm tra observation đã hoạt động

Sau khi khởi động ứng dụng:

1. Gửi một query GraphQL thành công.
2. Gửi một query có lỗi validation hoặc lỗi DataFetcher.
3. Gửi query có nested field được resolve qua @SchemaMapping.
4. Gửi query sử dụng @BatchMapping hoặc DataLoader.
5. Kiểm tra /actuator/metrics xem có meter graphql.request, graphql.datafetcher và graphql.dataloader tương ứng hay chưa.

Nếu chỉ thấy graphql.request nhưng không thấy graphql.datafetcher, hãy kiểm tra instrumentation và xác nhận query thực sự gọi một DataFetcher không tầm thường. Nếu không có graphql.dataloader, hãy xác nhận query đã kích hoạt batch loader.

## 5. Expose metrics qua Actuator và Prometheus

Spring Boot cung cấp Actuator endpoint để xem metrics và scrape Prometheus.

Ví dụ application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: catalog-graphql
~~~

Dependency micrometer-registry-prometheus cho phép Spring Boot cung cấp endpoint /actuator/prometheus. Endpoint phải được expose rõ ràng; chỉ có dependency không có nghĩa endpoint đã public.

Prometheus scrape cấu hình:

~~~yaml
scrape_configs:
  - job_name: catalog-graphql
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - catalog-graphql:8080
~~~

Tên meter trong Actuator thường dùng dạng Micrometer như graphql.request. Khi export Prometheus, naming convention chuyển dấu chấm thành dấu gạch dưới và Timer được biểu diễn theo đơn vị giây, ví dụ:

| Meter name trong Actuator | Prometheus series |
| --- | --- |
| graphql.request | graphql_request_seconds_count, graphql_request_seconds_sum |
| graphql.datafetcher | graphql_datafetcher_seconds_count, graphql_datafetcher_seconds_sum |
| graphql.dataloader | graphql_dataloader_seconds_count, graphql_dataloader_seconds_sum |

Khi bật histogram, mỗi Timer có thêm series _seconds_bucket.

### Bảo vệ Actuator endpoint

Không expose toàn bộ Actuator ra Internet công khai. Endpoint metrics có thể tiết lộ tên meter, tag, topology hoặc thông tin vận hành.

Các lựa chọn thường dùng:

- Chỉ mở endpoint Prometheus trong mạng nội bộ mà Prometheus có quyền truy cập.
- Dùng management port hoặc management interface riêng.
- Áp dụng authentication/authorization ở Spring Security hoặc ingress.
- Chỉ expose các endpoint cần thiết.
- Không đưa secret, user ID hoặc query variables vào tags.

Ví dụ trên chỉ minh họa danh sách endpoint cần expose; cần cấu hình security phù hợp với môi trường triển khai.

## 6. Histogram và latency percentile

Timer của Micrometer ghi nhận tổng số lần đo và tổng thời gian. Khi bật histogram, backend có thể tính percentile trên tập dữ liệu đã tổng hợp.

Với Prometheus, histogram phù hợp để tính p50, p95 hoặc p99 qua histogram_quantile. Percentile tính ở phía client không thể tổng hợp chính xác giữa nhiều instance như histogram bucket.

Ví dụ bật histogram và SLO buckets cho GraphQL request:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        graphql.request: true
        graphql.datafetcher: true
      slo:
        graphql.request: 100ms,300ms,1s,3s
~~~

Các ngưỡng trong ví dụ chỉ là điểm bắt đầu. Chọn bucket theo latency thực tế và mục tiêu dịch vụ. Histogram làm tăng số time series và bộ nhớ, vì vậy chỉ bật cho những meter cần phân tích latency.

### Tính p95 GraphQL request

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(graphql_request_seconds_bucket[5m])
  )
)
~~~

Tách theo operation type:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, graphql_operation_type) (
    rate(graphql_request_seconds_bucket[5m])
  )
)
~~~

Tách theo operation type giúp so sánh query, mutation và subscription nếu observation của transport/operation có cùng semantics. Với subscription sống lâu, hãy đánh giá riêng thời gian sống stream và latency của từng event thay vì trộn trực tiếp với request ngắn.

### Tính request rate

~~~promql
sum by (graphql_operation_type) (
  rate(graphql_request_seconds_count[5m])
)
~~~

Đây là số GraphQL execution mỗi giây theo operation type. Nó không nhất thiết bằng HTTP request rate vì transport có thể có request không phải GraphQL, batch request hoặc subscription connection kéo dài.

### Tính average latency

~~~promql
sum(rate(graphql_request_seconds_sum[5m]))
/
sum(rate(graphql_request_seconds_count[5m]))
~~~

Average latency hữu ích để theo dõi xu hướng tổng thể, nhưng có thể che khuất một nhóm request rất chậm. Dùng p95/p99 song song khi đã bật histogram.

## 7. Cardinality: chọn tag đúng

Cardinality là số lượng chuỗi thời gian khác nhau được tạo bởi tên metric và tập label/tag. Mỗi label có nhiều giá trị sẽ nhân số series lên.

Ví dụ metric:

~~~text
graphql_request_seconds_count{
  application="catalog-graphql",
  graphql_operation_type="query",
  graphql_outcome="SUCCESS"
}
~~~

Các giá trị query, mutation, subscription và outcome hữu hạn là low cardinality. Ngược lại, execution ID có thể khác nhau ở mỗi request.

### Phân loại mặc định của Spring GraphQL

| Key | Low/High | Có nên làm metric label? |
| --- | --- | --- |
| graphql.operation.type | Low | Có |
| graphql.outcome | Low | Có |
| graphql.operation.name | High | Không mặc định |
| graphql.execution.id | High | Không |
| graphql.field.name | Low | Có |
| graphql.field.path | High | Không |
| graphql.error.type | Low theo convention | Có, nếu tập class name được kiểm soát |
| graphql.loader.name | Low | Có |
| graphql.loader.size | High | Không |

Micrometer chỉ dùng low-cardinality KeyValue làm meter tag. High-cardinality KeyValue thường dành cho tracing và log backend có thể lưu nhiều giá trị hơn.

### Không đưa các giá trị sau vào metric tags

- Execution ID, request ID hoặc trace ID.
- User ID, email, tenant ID hoặc session ID.
- GraphQL document/query text.
- Variables hoặc input payload.
- URL đã thay thế path parameter bằng giá trị thật.
- Operation hash hoặc operation name do client tùy ý tạo nếu không có danh sách hữu hạn.

Các giá trị này có thể được giữ trong trace/log đã kiểm soát quyền truy cập và retention. Metric labels cần tập giá trị hữu hạn để chi phí lưu trữ không tăng theo số người dùng.

### Khi nào nên thêm custom tag?

Tag phù hợp:

- graphql.client.type với danh sách hữu hạn như web, ios, android, service.
- graphql.tenant.tier với các mức cố định như free, standard, enterprise.
- graphql.schema.version nếu số phiên bản đang chạy có giới hạn và được quản lý.

Tag không phù hợp:

- graphql.client.id nếu có hàng nghìn client riêng biệt.
- graphql.tenant.id nếu tenant không giới hạn.
- graphql.operation.name nếu client có thể tự đặt tên tùy ý.

Nếu cần phân tích theo client cụ thể, ghi structured log hoặc trace attribute có kiểm soát, không biến client ID thành metric label.

## 8. SLI và SLO cho GraphQL

SLI là chỉ số đo chất lượng dịch vụ. SLO là mục tiêu cho SLI trong một cửa sổ thời gian.

Một GraphQL service có thể chọn:

| SLI | Định nghĩa ví dụ | Mục đích |
| --- | --- | --- |
| Availability | Tỷ lệ operation hoàn thành theo tiêu chí success của dịch vụ | Đo độ sẵn sàng |
| Latency | Tỷ lệ request dưới ngưỡng thời gian | Đo độ nhanh |
| Error ratio | Tỷ lệ operation có lỗi ảnh hưởng người dùng | Đo độ ổn định |
| Freshness | Tuổi dữ liệu tối đa hoặc thời gian đồng bộ | Đo độ mới dữ liệu nếu nghiệp vụ cần |

Ví dụ SLO ban đầu:

- 99.9% GraphQL request thuộc nhóm operation quan trọng hoàn thành theo tiêu chí success trong 30 ngày.
- 95% query quan trọng hoàn thành trong 500 ms.
- 99% query quan trọng hoàn thành trong 1.5 giây.

Các con số này chỉ là ví dụ. SLO thật phải dựa trên trải nghiệm người dùng, baseline và khả năng vận hành.

### Định nghĩa success cho GraphQL cẩn thận

GraphQL cho phép partial data cùng errors. Do đó, “có HTTP 200” không có nghĩa tất cả field đều thành công.

Ngược lại, không phải mọi GraphQL error đều là server outage:

- Validation error do client gửi field không tồn tại có thể là lỗi client.
- Lỗi nghiệp vụ như không tìm thấy một entity có thể là behavior dự kiến.
- Lỗi một field phụ có thể không ảnh hưởng luồng chính.
- INTERNAL_ERROR thường là tín hiệu server-side cần điều tra.

graphql.outcome mặc định của Spring for GraphQL phân loại response có errors (trừ INTERNAL_ERROR) thành REQUEST_ERROR. Đây là observation outcome, không phải nhãn HTTP client error. Nếu lấy graphql.outcome khác SUCCESS làm SLI availability, bạn có thể tính cả lỗi input hợp lệ hoặc lỗi nghiệp vụ vào error budget.

Hãy định nghĩa success theo nghiệp vụ. Ví dụ:

- Request parse/validation lỗi được thống kê riêng.
- Domain error có thể được tính là expected outcome nếu schema contract quy định rõ.
- Internal server error và lỗi phụ thuộc hạ tầng được tính là bad event.
- Partial data được đánh giá theo mức độ quan trọng của field bị lỗi.

Nếu cần SLI riêng cho phân loại này, tạo custom low-cardinality outcome convention hoặc metric nghiệp vụ, thay vì diễn giải lại mặc định graphql.outcome.

## 9. Dashboard GraphQL

Một dashboard vận hành tốt cần trả lời nhanh: có ảnh hưởng người dùng không, bắt đầu khi nào, phạm vi nào và thành phần nào chậm/lỗi.

### Hàng 1: Tổng quan request

| Panel | Truy vấn/metric | Câu hỏi |
| --- | --- | --- |
| Request rate | rate(graphql_request_seconds_count[5m]) | Lượng query/mutation đang chạy |
| Error ratio | Tỷ lệ internal error hoặc business bad event | Người dùng có gặp lỗi không? |
| p50/p95/p99 | Histogram của graphql.request | Latency thay đổi thế nào? |
| Outcome distribution | graphql.outcome | Request đang thành công, request error hay internal error? |

### Hàng 2: Resolver và DataLoader

| Panel | Metric | Câu hỏi |
| --- | --- | --- |
| DataFetcher p95 | graphql.datafetcher histogram | Resolver nào chậm? |
| DataFetcher error rate | graphql.datafetcher với outcome ERROR | Field nào lỗi nhiều? |
| DataLoader p95 | graphql.dataloader histogram | Batch loader nào chậm? |
| DataLoader errors | graphql.dataloader với outcome ERROR | Loader nào thất bại? |
| Batch size distribution | Custom DistributionSummary nếu cần | Batch có quá nhỏ hoặc quá lớn? |

### Hàng 3: Infrastructure

Theo dõi cùng dashboard:

- JVM heap, garbage collection và CPU.
- Active/idle/max database connections.
- HikariCP pending connection threads.
- HTTP client latency và error rate.
- Executor queue, active threads và rejected tasks.
- Pod restart, container CPU/memory và readiness.

Một GraphQL resolver chậm có thể chỉ là biểu hiện của database pool cạn hoặc remote service chậm. Dashboard nên giúp nối các tín hiệu này.

## 10. Alert: báo khi người dùng bị ảnh hưởng

Alert tốt nên:

- Phản ánh triệu chứng của người dùng.
- Có ngưỡng và thời gian duy trì để lọc spike ngắn.
- Chỉ page khi có người cần hành động ngay.
- Có dashboard và runbook đi kèm.
- Có owner và severity rõ ràng.
- Không tạo một alert riêng cho mọi metric nội bộ.

Prometheus hỗ trợ thuộc tính for để giữ điều kiện liên tục trước khi chuyển sang firing và keep_firing_for để tránh alert chập chờn khi tín hiệu vừa hồi phục.

### 10.1. Alert tỷ lệ internal error

Ví dụ PromQL:

~~~promql
(
  sum(rate(graphql_request_seconds_count{
    graphql_outcome="INTERNAL_ERROR"
  }[5m]))
  /
  sum(rate(graphql_request_seconds_count[5m]))
) > 0.01
and
sum(rate(graphql_request_seconds_count[5m])) > 0.2
~~~

Điều kiện này chỉ xét internal error, yêu cầu tỷ lệ vượt 1% và traffic vượt 0.2 request/giây để tránh alert do mẫu quá nhỏ. Các ngưỡng chỉ minh họa; hãy điều chỉnh theo SLO và tải thực tế.

### 10.2. Alert p95 latency

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(graphql_request_seconds_bucket[5m])
  )
) > 1.5
~~~

Ví dụ này báo khi p95 vượt 1.5 giây. Không page chỉ vì một spike rất ngắn; thêm for trong rule để yêu cầu điều kiện duy trì.

### 10.3. Alert DataFetcher lỗi tăng

~~~promql
sum by (graphql_field_name) (
  rate(graphql_datafetcher_seconds_count{
    graphql_outcome="ERROR"
  }[5m])
) > 0.5
~~~

Đây có thể là alert dạng ticket hoặc cảnh báo trên dashboard, không nhất thiết phải page. Một field có thể trả lỗi nghiệp vụ dự kiến; hãy lọc hoặc phân loại error type trước khi coi đây là sự cố.

### 10.4. Ví dụ Prometheus alert rules

~~~yaml
groups:
  - name: graphql-service
    rules:
      - alert: GraphQLInternalErrorRatioHigh
        expr: |
          (
            sum(rate(graphql_request_seconds_count{graphql_outcome="INTERNAL_ERROR"}[5m]))
            /
            sum(rate(graphql_request_seconds_count[5m]))
          ) > 0.01
          and
          sum(rate(graphql_request_seconds_count[5m])) > 0.2
        for: 5m
        keep_firing_for: 2m
        labels:
          severity: page
          service: catalog-graphql
        annotations:
          summary: "GraphQL internal error ratio is high"
          description: "Internal GraphQL errors exceeded 1% for 5 minutes."
          runbook_url: "https://runbooks.example.com/catalog-graphql/internal-errors"

      - alert: GraphQLP95LatencyHigh
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (rate(graphql_request_seconds_bucket[5m]))
          ) > 1.5
        for: 10m
        labels:
          severity: ticket
          service: catalog-graphql
        annotations:
          summary: "GraphQL p95 latency is high"
          description: "GraphQL p95 latency has exceeded 1.5 seconds for 10 minutes."
          runbook_url: "https://runbooks.example.com/catalog-graphql/latency"
~~~

Thay domain, service label, URL runbook và threshold bằng cấu hình thật của tổ chức. Rule latency cần có traffic floor hoặc áp dụng cho operation group có đủ request để percentile ổn định.

### 10.5. Alert fatigue

Không tạo alert page cho từng DataFetcher, từng exception class hoặc từng database query. Một sự cố database có thể đồng thời làm hàng chục resolver lỗi; page từng field sẽ gửi nhiều thông báo cho cùng một nguyên nhân.

Hãy page ở tầng triệu chứng request hoặc dependency quan trọng. Resolver/loader metrics giúp điều tra và có thể tạo ticket cho xu hướng kéo dài.

## 11. Alert theo error budget và burn rate

Nếu đã có SLO, có thể alert theo tốc độ tiêu thụ error budget thay vì một ngưỡng lỗi cố định.

Ví dụ SLO availability 99.9% có error budget 0.1% trong cửa sổ 30 ngày. Burn rate cho biết tốc độ tiêu thụ budget so với tốc độ cho phép:

~~~text
burn rate = observed error ratio / allowed error ratio
~~~

Burn rate 1 nghĩa là đang tiêu thụ budget đúng tốc độ để dùng hết budget trong cửa sổ SLO. Burn rate 10 nghĩa là tiêu thụ nhanh gấp 10 lần.

Một cách tiếp cận multi-window:

- Cửa sổ ngắn để phát hiện sự cố đang gây ảnh hưởng lớn.
- Cửa sổ dài để xác nhận ảnh hưởng kéo dài, tránh page do spike.
- Cảnh báo ticket khi budget tiêu hao chậm nhưng liên tục.

Ví dụ Google SRE Workbook đưa ra các mốc burn rate minh họa cho page/ticket. Không sao chép máy móc các ngưỡng này; điều chỉnh theo traffic, SLO và khả năng on-call của dịch vụ.

## 12. Custom ObservationConvention

Spring for GraphQL cho phép tùy chỉnh metadata của observation bằng các convention:

- ExecutionRequestObservationConvention
- DataFetcherObservationConvention
- DataLoaderObservationConvention

Convention phù hợp khi cần thêm một số low-cardinality KeyValue có giá trị hữu hạn hoặc chuẩn hóa error type. Trong ứng dụng Spring Boot, đăng ký convention dưới dạng bean là cách cấu hình được ưu tiên.

Ví dụ, có thể bổ sung graphql.client.type với tập giá trị cố định:

~~~java
public class ClientTypeExecutionConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("graphql.client.type", "web"));
    }
}
~~~

Ví dụ cố định web chỉ minh họa cách mở rộng convention. Nếu client type thay đổi theo request, phải lấy từ metadata đã xác thực và giới hạn tập giá trị, chẳng hạn web, ios, android, service.

Các import chính của ví dụ:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
~~~

Trong ứng dụng Spring Boot, expose instance convention này dưới dạng bean theo API phiên bản đang dùng để auto-configuration sử dụng nó. Không tự thêm một GraphQlObservationInstrumentation thứ hai nếu Boot đã đăng ký instrumentation mặc định.

Không thêm operation name, execution ID, raw query hoặc tenant ID vào low-cardinality KeyValues. Nếu cần những giá trị này để tìm trace, hãy thêm chúng vào high-cardinality metadata theo API của convention phù hợp phiên bản.

### Chuẩn hóa error type

Mặc định graphql.error.type dùng class name của lỗi. Nếu ứng dụng có nhiều exception class không ổn định hoặc class được sinh động, có thể map chúng về nhóm cố định như:

- VALIDATION
- NOT_FOUND
- AUTHORIZATION
- DEPENDENCY
- INTERNAL

Nhóm lỗi hữu hạn giúp dashboard và alert dễ đọc hơn. Tuy nhiên, không làm mất thông tin chi tiết cần thiết trong logs/traces.

## 13. Metrics nghiệp vụ bổ sung

Observation mặc định không đo mọi thứ mà sản phẩm quan tâm. Có thể bổ sung metrics riêng cho:

- Query complexity/cost sau khi validation.
- Số node hoặc alias trong operation.
- Cache hit ratio của resolver.
- Số request bị từ chối bởi query depth/complexity limit.
- Batch size thực tế nếu cần histogram.
- Số event subscription bị drop hoặc queue overflow.
- Tỷ lệ retry của dependency.

Ví dụ đo query cost bằng DistributionSummary:

~~~java
@Component
public class GraphQlQueryCostMetrics {

    private final DistributionSummary queryCost;

    public GraphQlQueryCostMetrics(MeterRegistry registry) {
        this.queryCost = DistributionSummary.builder("graphql.query.cost")
                .description("Estimated GraphQL query cost")
                .baseUnit("cost")
                .register(registry);
    }

    public void record(int cost) {
        queryCost.record(cost);
    }
}
~~~

Ghi nhận cost sau khi tính toán query cost và trước khi thực thi hoặc tại instrumentation phù hợp. Không gắn raw query text làm tag. Nếu cần phân biệt operation class, dùng nhóm cố định như simple, standard, expensive.

Custom metric phải có owner, định nghĩa và mục đích rõ ràng. Tránh tạo một metric cho mọi field hoặc mọi operation name.

## 14. Trace và correlation

graphql.request observation có thể tạo span và ghi GraphQL errors thành span events. DataFetcher và DataLoader observations có thể tạo span con giúp tìm điểm chậm.

Các thông tin thường hữu ích trong trace:

- Operation type và operation name.
- Execution ID.
- Field path.
- DataLoader name và batch size.
- Error type và error message đã được kiểm soát.
- Trace ID dùng để nối với transport và downstream dependency.

Execution ID là high-cardinality; dùng để tìm một request cụ thể trong trace/log, không dùng làm metric label.

### Exemplars

Với Prometheus histogram, exemplar có thể liên kết một bucket sample với trace ID. Khi p95 tăng, dashboard có thể mở một trace đại diện để điều tra.

Micrometer và Spring Boot hỗ trợ exemplar khi tracing context được cấu hình phù hợp. Cần cấu hình cả phía exporter và Prometheus/OpenMetrics theo phiên bản đang dùng; không giả định exemplar tự xuất hiện chỉ vì đã bật histogram.

### Sampling

Không phải mọi request đều cần trace chi tiết. Dùng sampling phù hợp:

- Giữ tỷ lệ trace cơ bản để phân tích xu hướng.
- Tăng khả năng giữ trace có lỗi hoặc latency cao nếu tracing backend hỗ trợ tail sampling.
- Giữ execution ID/trace ID ở trace/log, không chuyển sang metric tags.
- Bảo vệ dữ liệu nhạy cảm trong GraphQL document, variables và span attributes.

## 15. Kiểm thử metrics và alert

Monitoring cũng là một phần của chất lượng ứng dụng. Một dashboard trống có thể là do chưa có traffic, nhưng cũng có thể do instrumentation bị thiếu.

### Kiểm thử observation

Trong integration test:

1. Tạo GraphQL source với ObservationRegistry và meter handler phù hợp.
2. Gửi query thành công.
3. Gửi query có DataFetcher error.
4. Gửi query có @BatchMapping.
5. Kiểm tra Timer và tags đã được ghi nhận.

Với Spring Boot, có thể kiểm tra endpoint Actuator trong test hoặc dùng SimpleMeterRegistry/test registry. Không phụ thuộc vào tên Prometheus normalized khi truy vấn Actuator metrics endpoint; endpoint dùng tên meter gốc của Micrometer.

Ví dụ integration test dùng GraphQlTester và MeterRegistry:

~~~java
@SpringBootTest
class GraphQlObservationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsGraphQlRequestTimer() {
        graphQlTester.document("""
                query {
                    books {
                        id
                    }
                }
                """)
                .execute();

        Timer timer = meterRegistry.find("graphql.request")
                .tag("graphql.operation.type", "query")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

Test giả định schema có query books và ứng dụng đã bật GraphQL Observation. Nếu test environment dùng registry khác hoặc observation handler tùy chỉnh, điều chỉnh cách lấy meter theo cấu hình đó.

### Kiểm tra Prometheus scrape

- /actuator/prometheus trả exposition format.
- Prometheus target ở trạng thái UP.
- Có series _count và _sum sau khi có request.
- Có _bucket nếu đã bật histogram.
- Tags như graphql_operation_type và graphql_outcome có giá trị đúng.

### Kiểm thử alert rule

Prometheus cung cấp promtool test rules để kiểm tra alert expression với chuỗi sample giả lập. Nên có test cho:

- Tỷ lệ lỗi vượt ngưỡng.
- Traffic thấp không tạo alert giả.
- Latency trở lại bình thường làm alert resolve.
- Alert có đúng labels và annotations.
- Missing series hoặc scrape failure được xử lý theo policy.

Không chỉ kiểm tra cú pháp YAML; cần kiểm tra cả logic PromQL và điều kiện for.

## 16. Runbook khi GraphQL alert kích hoạt

### Khi GraphQLInternalErrorRatioHigh

1. Mở dashboard GraphQL request và xác định operation type bị ảnh hưởng.
2. So sánh HTTP 5xx, graphql.outcome và DataFetcher errors.
3. Xem trace để tìm field path hoặc dependency gây lỗi.
4. Kiểm tra database pool, remote HTTP client và executor.
5. Xác định lỗi có bắt đầu sau deploy hoặc schema change không.
6. Giảm tải, rollback hoặc tắt dependency path nếu có biện pháp đã được phê duyệt.
7. Xác nhận error ratio giảm và người dùng khôi phục.

### Khi GraphQLP95LatencyHigh

1. So sánh p95 request với p95 DataFetcher.
2. Xác định field/resolver chậm nhất theo trace.
3. Kiểm tra DataLoader có batch đúng hay vẫn phát sinh N+1.
4. Kiểm tra database query plan, connection pool và lock wait.
5. Kiểm tra dependency latency và retry.
6. So sánh với traffic, payload size và operation mix.
7. Xác nhận p95 trở về SLO sau khi xử lý.

### Khi DataLoader error tăng

1. Xác định graphql.loader.name.
2. Kiểm tra graphql.error.type và trace của batch loader.
3. Xác minh batch key mapping và thứ tự kết quả.
4. Kiểm tra database/service dependency.
5. Xem batch size và queue/backpressure nếu có custom metrics.
6. Kiểm tra timeout, retry và cancellation behavior.

## 17. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có graphql.request | Thiếu ObservationRegistry hoặc instrumentation | Kiểm tra Boot auto-configuration và GraphQL source |
| Có request metric nhưng không có DataFetcher metric | Chỉ dùng property fetcher hoặc thiếu instrumentation | Thêm resolver không tầm thường và kiểm tra instrumentation |
| Không có DataLoader metric | Query không kích hoạt loader hoặc instrumentation chưa bật | Kiểm tra @BatchMapping, DataLoader registration |
| Tưởng REQUEST_ERROR là HTTP 400 | Nhầm observation outcome với transport status | Phân biệt GraphQL outcome và HTTP status |
| Error ratio luôn cao | Tính mọi GraphQL errors là server outage | Phân loại lỗi client, domain và internal |
| P95 không hiển thị | Chưa bật histogram hoặc không có traffic | Cấu hình histogram và kiểm tra bucket |
| Metric backend có quá nhiều series | Dùng execution ID, operation name hoặc tenant ID làm tag | Chuyển high-cardinality data sang trace/log |
| Dashboard chỉ thấy latency tổng | Không có DataFetcher/DataLoader observations | Bật instrumentation và thêm panels theo resolver/loader |
| Batch size không query được | graphql.loader.size là high-cardinality key | Tạo DistributionSummary riêng nếu cần metric |
| Alert chập chờn | Không có for/keep_firing_for hoặc threshold quá nhạy | Dùng cửa sổ phù hợp và slack |
| Page quá nhiều lần | Alert theo từng dependency/field thay vì triệu chứng | Page ở tầng request, ticket ở tầng component |
| Metrics endpoint bị truy cập công khai | Expose Actuator mà thiếu security | Giới hạn mạng và quyền truy cập |
| Trace thiếu parent span | Transport propagation hoặc context propagation chưa cấu hình | Kiểm tra HTTP/WebFlux transport instrumentation |
| Alert không có trace để điều tra | Sampling quá thấp hoặc exemplar chưa cấu hình | Điều chỉnh sampling và exemplar |

## 18. Nguyên tắc vận hành

- Bật Micrometer Observation cho GraphQL request, DataFetcher và DataLoader.
- Dùng Actuator để kiểm tra meter và Prometheus endpoint để scrape.
- Theo dõi cả transport, GraphQL request, DataFetcher, DataLoader và infrastructure.
- Dùng histogram khi cần percentile có thể tổng hợp giữa nhiều instance.
- Chọn SLI/SLO theo trải nghiệm người dùng và phân loại lỗi thực tế.
- Không coi mọi REQUEST_ERROR là lỗi server.
- Dùng low-cardinality tags cho metrics; giữ execution ID và field path ở traces/logs.
- Tạo alert theo triệu chứng, có for, severity và runbook.
- Dùng dashboard để drill down thay vì page cho từng resolver.
- Kiểm thử instrumentation, scrape target và alert rules.
- Bảo vệ Actuator endpoint và dữ liệu GraphQL nhạy cảm.
- Chỉ thêm custom metrics khi có câu hỏi vận hành cụ thể cần trả lời.

## 19. Bài tập thực hành

Thiết lập monitoring cho Spring for GraphQL API thư viện:

1. Thêm Spring Boot Actuator và Prometheus registry.
2. Xác nhận ObservationRegistry và GraphQlObservationInstrumentation hoạt động.
3. Gửi query có @SchemaMapping và query có @BatchMapping.
4. Kiểm tra ba meter graphql.request, graphql.datafetcher, graphql.dataloader.
5. Expose /actuator/prometheus trong mạng nội bộ.
6. Cấu hình Prometheus scrape ứng dụng.
7. Bật histogram cho graphql.request và graphql.datafetcher.
8. Viết PromQL cho request rate, p95 và internal error ratio.
9. Tạo Grafana dashboard với request, error, resolver, loader và infrastructure panels.
10. Viết alert rule có for, severity và runbook URL.
11. Mô phỏng DataFetcher exception và xác nhận alert/trace phản ánh đúng.
12. Tạo custom metric cho query cost hoặc batch size nếu dashboard cần.
13. Kiểm tra metric labels không chứa execution ID, user ID hoặc raw query.
14. Dùng promtool test rules kiểm tra alert.
15. Viết runbook cho hai alert quan trọng nhất.

Sau bài tập, bạn cần giải thích được cách GraphQL observation được chuyển thành metrics/traces, cách phân biệt request outcome với HTTP status, và cách thiết kế alert không gây nhiễu cho đội on-call.

## 20. Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/observation/GraphQlObservationAutoConfiguration.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Alerting Practices](https://prometheus.io/docs/practices/alerting/)
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

Metrics cho biết hệ thống đang hoạt động thế nào trên diện rộng; traces và logs giúp giải thích một request cụ thể. Khi ba nguồn này được nối với SLO và runbook, đội vận hành có thể phát hiện sự cố sớm và xử lý đúng thành phần gây ảnh hưởng.
