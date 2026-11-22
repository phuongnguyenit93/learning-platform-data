# Đo riêng thời gian phía ứng dụng và thời gian Elasticsearch

Khi một API dùng Spring Data Elasticsearch chậm, chỉ đo thời gian từ lúc controller nhận request đến lúc trả response chưa đủ để biết nguyên nhân. Thời gian đó có thể bao gồm xử lý nghiệp vụ, chờ thread hoặc connection pool, serialize request, truyền dữ liệu qua mạng, xử lý trên Elasticsearch, nhận response, deserialize và map kết quả thành entity.

Muốn chẩn đoán đúng, cần tách ít nhất hai góc nhìn:

- **Thời gian phía ứng dụng (application elapsed time):** thời gian mà ứng dụng quan sát được quanh một thao tác gọi Elasticsearch. Nó bao gồm chi phí client và thời gian chờ từ góc nhìn caller.
- **Thời gian Elasticsearch báo cáo (server execution time):** thời lượng do Elasticsearch trả về trong response, ví dụ trường took của Search API hoặc SearchHits.getExecutionDuration() trong những phiên bản Spring Data Elasticsearch hỗ trợ.

Hai con số này đo các khoảng thời gian khác nhau. Không nên lấy thời gian ứng dụng trừ thời gian Elasticsearch rồi kết luận phần còn lại chính xác là network latency. Phần chênh lệch còn có thể chứa chờ connection, serialization, response mapping, callback, scheduling và các chi phí khác.

## 1. Vì sao cần đo hai phía?

Giả sử một endpoint tìm kiếm mất 420 ms theo log của ứng dụng. Search response từ Elasticsearch báo took = 95 ms.

Điều này cho biết Elasticsearch báo cáo khoảng xử lý search là 95 ms, trong khi ứng dụng mất tổng cộng 420 ms cho khoảng được đo. Phần còn lại có thể đến từ:

- Ứng dụng xử lý và chuẩn bị criteria.
- Chờ lấy connection từ HTTP connection pool.
- Serialize query thành HTTP request.
- Truyền request tới node Elasticsearch.
- Chờ qua proxy, load balancer hoặc mạng nội bộ.
- Deserialize response và map hit thành entity.
- Chuyển SearchHits thành DTO.
- Xử lý sau tìm kiếm trước khi trả HTTP response.

Đây là ví dụ minh họa, không phải phép phân rã chính xác. Nếu chỉ nhìn application latency, có thể nhầm rằng query Elasticsearch chậm. Nếu chỉ nhìn took, có thể bỏ qua việc ứng dụng đang chờ connection hoặc xử lý response quá lâu.

## 2. Xác định ranh giới đo

Trước khi thêm timer, cần định nghĩa rõ điểm bắt đầu và kết thúc.

Một luồng đồng bộ có thể được mô tả:

~~~text
HTTP request vào controller
          |
          v
   Validate / nghiệp vụ
          |
          v
    Build Search Query
          |
          v
  Gọi Spring Data / Client
          |
          +------------------------------+
          |                              |
          v                              v
  Client serialize                 Elasticsearch
  / connection / network            xử lý request
          |                              |
          |                         Server took
          |                              |
          +---------------+--------------+
                          |
                          v
                 Nhận response
                          |
                          v
              Deserialize / map entity
                          |
                          v
                Map DTO / response
                          |
                          v
                 HTTP response ra
~~~

Có thể đo nhiều khoảng:

| Timer | Bắt đầu | Kết thúc | Mục đích |
|---|---|---|---|
| HTTP request | Request vào ứng dụng | Response được gửi | Góc nhìn người gọi API |
| Search service | Service bắt đầu xử lý | Service trả kết quả | Chi phí nghiệp vụ và tìm kiếm trong service |
| Elasticsearch call | Ngay trước lời gọi client | Lời gọi hoàn tất | Thời gian ứng dụng chờ thao tác Elasticsearch |
| Elasticsearch took | Theo ranh giới đo của server | Response server báo | Thời gian Elasticsearch báo cáo |
| Mapping/DTO | Bắt đầu chuyển kết quả | Có DTO hoàn chỉnh | Chi phí xử lý kết quả trong ứng dụng |

Không nên gộp các timer có ranh giới khác nhau dưới cùng một metric name. Tên metric và tag cần nói rõ đo phần nào.

## 3. Đo elapsed time trong Java bằng System.nanoTime

Đối với đoạn code đồng bộ, dùng System.nanoTime() để đo thời lượng. Đây là đồng hồ đơn điệu phù hợp để tính khoảng thời gian; không dùng System.currentTimeMillis() để benchmark elapsed time vì đồng hồ lịch có thể bị điều chỉnh.

Ví dụ:

~~~java
long started = System.nanoTime();

try {
    SearchHits<Product> hits =
            operations.search(query, Product.class);

    long elapsedNanos = System.nanoTime() - started;
    Duration applicationDuration =
            Duration.ofNanos(elapsedNanos);

    log.info(
            "Elasticsearch call completed in {} ms",
            applicationDuration.toMillis()
    );

    return hits;
} catch (RuntimeException exception) {
    long elapsedNanos = System.nanoTime() - started;
    log.warn(
            "Elasticsearch call failed after {} ms",
            Duration.ofNanos(elapsedNanos).toMillis()
    );
    throw exception;
}
~~~

Timer bắt đầu ngay trước operations.search và kết thúc khi method trả về hoặc ném exception. Khoảng này là thời gian ứng dụng quan sát được quanh lời gọi Spring Data. Nó có thể bao gồm request serialization, chờ connection, network, server processing, response transfer, deserialization và mapping kết quả.

Nó không nhất thiết bằng thời gian người dùng nhìn thấy trên toàn endpoint. Nếu service còn validate, build query, map DTO hoặc gọi dịch vụ khác, hãy đo các khoảng đó riêng.

### 3.1. Ghi nhận cả request thất bại

Trong code thực tế, nên bảo đảm timer được ghi cả khi request thất bại. Có thể ghi outcome thành tag:

~~~java
Timer.Sample sample = Timer.start(meterRegistry);
String outcome = "success";

try {
    return operations.search(query, Product.class);
} catch (RuntimeException exception) {
    outcome = "error";
    throw exception;
} finally {
    sample.stop(Timer.builder("app.elasticsearch.call")
            .tag("operation", "search")
            .tag("outcome", outcome)
            .register(meterRegistry));
}
~~~

Timer.Sample bắt đầu bằng clock của registry và dừng vào Timer được đăng ký với tag outcome tương ứng. Cách này ghi được cả request thành công lẫn request thất bại mà không gọi method không tồn tại trên Timer.

Không chỉ ghi timer ở nhánh thành công. Lỗi timeout, connection failure hoặc rejection cũng là dữ liệu hiệu năng quan trọng.

## 4. Đo thời gian Elasticsearch từ Search response

Elasticsearch Search API trả về trường took trong response. Đây là thời gian xử lý được node điều phối báo cáo, tính bằng milliseconds. Nó khác với elapsed time đo từ ứng dụng vì không bao gồm toàn bộ thời gian client quan sát được, chẳng hạn thời gian truyền request/response và xử lý trước/sau lời gọi.

Với Elasticsearch Java Client, response tìm kiếm có thể cung cấp took():

~~~java
SearchResponse<ProductDocument> response =
        elasticsearchClient.search(
                request -> request
                        .index("products")
                        .query(query),
                ProductDocument.class
        );

long elasticsearchTookMillis = response.took();
~~~

Với Spring Data Elasticsearch, một số phiên bản cung cấp execution duration trên SearchHits<T>:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

Duration elasticsearchDuration =
        hits.getExecutionDuration();
~~~

getExecutionDuration() phản ánh duration được chuyển từ search response theo API của Spring Data tương ứng. Hãy kiểm tra Javadoc/dependency version đang dùng nếu method này không có trong release train của dự án. Khi cần metadata gốc của Elasticsearch, có thể dùng Elasticsearch Java Client trực tiếp và đọc SearchResponse.took().

### 4.1. Ghi hai con số cạnh nhau

Ví dụ:

~~~java
long started = System.nanoTime();

SearchHits<Product> hits =
        operations.search(query, Product.class);

Duration applicationDuration =
        Duration.ofNanos(System.nanoTime() - started);

Duration elasticsearchDuration =
        hits.getExecutionDuration();

log.info(
        "product search: app={} ms, elasticsearch={} ms, totalHits={}",
        applicationDuration.toMillis(),
        elasticsearchDuration.toMillis(),
        hits.getTotalHits()
);
~~~

Log này giúp quan sát hai góc nhìn trong cùng một request. Trong hệ thống production, nên gắn correlation/trace ID để tìm đúng request và đối chiếu với trace, slow log hoặc server metrics.

Không log query đầy đủ nếu query có dữ liệu nhạy cảm hoặc có thể làm log phình lớn. Có thể log tên operation, index alias, loại query, page size, outcome và trace ID.

## 5. took không phải toàn bộ thời gian của người dùng

Search took là duration phía Elasticsearch được trả trong response. Nó giúp biết phần server báo cáo mất bao lâu, nhưng không bao gồm mọi bước của request từ góc nhìn ứng dụng.

Không dùng took như:

- Thời gian từ khi người dùng bấm nút đến khi UI nhận dữ liệu.
- Thời gian từ khi controller bắt đầu đến khi controller kết thúc.
- Thời gian serialize request ở client.
- Thời gian ứng dụng chờ connection pool.
- Thời gian nhận toàn bộ response qua mạng và map thành object.

took cũng không phải phép đo riêng từng shard. Một search có thể đi qua nhiều shard; node điều phối tổng hợp kết quả và trả một duration ở response. Muốn phân tích query/fetch trên shard, cần công cụ khác như Profile API hoặc slow logs.

### 5.1. Không lấy app time trừ took để gọi là network time

Giả sử:

~~~text
Application elapsed: 420 ms
Elasticsearch took:   95 ms
Difference:          325 ms
~~~

Không thể kết luận network mất 325 ms. Chênh lệch có thể bao gồm:

- Chờ connection pool hoặc client thread.
- Serialization/deserialization.
- Network và proxy.
- Map response sang SearchHit/entity.
- Callback hoặc logic nằm trong ranh giới timer.
- Các khoảng chờ không được tính cùng ranh giới với server took.

Muốn đo network hoặc connection acquisition cụ thể, cần tracing/instrumentation ở client transport và hạ tầng mạng. Chênh lệch chỉ là tín hiệu cho thấy còn chi phí ngoài server duration.

## 6. Không phải API nào cũng có took

Search response thường có took. Một số API chạy tác vụ hàng loạt như Bulk hoặc Update By Query cũng có duration riêng trong response. Tuy nhiên, không phải mọi write response đơn lẻ đều cung cấp một trường server-side duration tương đương.

| API | Thông tin thời gian có thể dùng | Ghi chú |
|---|---|---|
| Search | took | Server-reported duration cho search |
| Bulk | took, và có thể có ingest_took | Duration của bulk request; ingest duration chỉ liên quan phần ingest pipeline |
| Update By Query | took | Tác vụ có thể chạy lâu và hỗ trợ theo dõi task |
| Reindex | took | Tác vụ dài, nên theo dõi task và tiến độ |
| Index một document | Không có trường took tổng quát trong response index thông thường | Đo app elapsed và dùng tracing/metrics để phân tích phía server |
| Get theo ID | Response thông thường không có took tương đương Search | Đo app elapsed và tracing |

Đừng tạo một metric elasticsearch.took giả bằng cách lấy app time cho những response không cung cấp server duration. Hãy đặt tên metric đúng với nguồn dữ liệu, ví dụ app.elasticsearch.call.

## 7. Đo bằng Micrometer

Micrometer Timer phù hợp để ghi thời lượng và phân tích phân phối latency. Với Spring Boot, registry có thể xuất metric tới Prometheus, OTLP hoặc backend được cấu hình.

Ví dụ một service đo lời gọi search:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class ProductSearchService {

    private final ElasticsearchOperations operations;
    private final MeterRegistry meterRegistry;

    public ProductSearchService(
            ElasticsearchOperations operations,
            MeterRegistry meterRegistry
    ) {
        this.operations = operations;
        this.meterRegistry = meterRegistry;
    }

    public SearchHits<Product> search(Query query) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";

        try {
            return operations.search(query, Product.class);
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(Timer.builder("app.elasticsearch.call")
                    .description("Elapsed time around a Spring Data Elasticsearch call")
                    .tag("operation", "search")
                    .tag("index", "products")
                    .tag("outcome", outcome)
                    .register(meterRegistry));
        }
    }
}
~~~

Timer trên đo thời gian ứng dụng quan sát quanh lời gọi operations.search. Nó không tự đo riêng took; nếu cần server duration, ghi thêm giá trị từ SearchHits.getExecutionDuration() hoặc response gốc.

### 7.1. Đo server duration thành một metric riêng

Sau khi nhận SearchHits, có thể ghi duration do server báo cáo:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

Timer.builder("elasticsearch.search.server_duration")
        .tag("index", "products")
        .register(meterRegistry)
        .record(hits.getExecutionDuration());
~~~

Đây là metric minh họa cho các phiên bản Spring Data có getExecutionDuration(). Nếu không có method này, lấy took từ Elasticsearch Java Client hoặc response metadata phù hợp. Không thay thế bằng elapsed time phía ứng dụng.

### 7.2. Tag cần có cardinality thấp

Các tag thường hữu ích:

- operation: search, get, bulk, update.
- index: tên alias/index ổn định.
- outcome: success, error, timeout.
- query_type: loại truy vấn được kiểm soát như full_text, filtered, aggregation.

Tránh tag có cardinality cao:

- Document ID.
- User ID.
- Từ khóa tìm kiếm.
- Query DSL đầy đủ.
- URL có ID động.
- Trace ID hoặc request ID.

Các giá trị này có thể tạo hàng triệu time series và làm hệ thống metrics quá tải. Trace ID nên nằm trong tracing/logging, không phải metric tag.

## 8. Đo reactive operation đúng cách

Với Reactive Spring Data Elasticsearch, method có thể trả Mono hoặc Flux. Gọi method chỉ tạo publisher; request thực sự có thể chưa được thực thi cho đến khi publisher được subscribe.

Do đó, đoạn code sau có thể đo sai:

~~~java
long started = System.nanoTime();
Mono<SearchPage<Product>> result =
        reactiveOperations.searchForPage(query, Product.class);
long elapsed = System.nanoTime() - started;
~~~

Khoảng thời gian trên chủ yếu đo thời gian tạo publisher, không đo thời gian thực thi request.

Đo bên trong publisher bằng defer và doFinally:

~~~java
Mono<SearchPage<Product>> measuredSearch =
        Mono.defer(() -> {
            long started = System.nanoTime();

            return reactiveOperations.searchForPage(
                            query,
                            Product.class
                    )
                    .doFinally(signalType -> {
                        long elapsed = System.nanoTime() - started;
                        applicationTimer.record(
                                elapsed,
                                TimeUnit.NANOSECONDS
                        );
                    });
        });
~~~

Mono.defer đặt điểm bắt đầu ở thời điểm subscribe. doFinally ghi nhận thời gian khi publisher kết thúc thành công, lỗi hoặc bị hủy. Với Flux, áp dụng nguyên tắc tương tự nhưng cần hiểu timer đo đến khi toàn bộ stream kết thúc hoặc bị cancel.

Nếu stream có thể chạy rất lâu hoặc caller chỉ đọc một phần rồi hủy, duration phản ánh thời gian subscription tồn tại, không nhất thiết là thời gian server xử lý toàn bộ kết quả. Hãy định nghĩa semantics của metric trước khi dùng nó để so sánh.

## 9. Đo từng giai đoạn ở phía ứng dụng

Một timer quanh operations.search chỉ cho biết thời gian của toàn lời gọi Spring Data. Nếu timer cao nhưng server took thấp, cần chia nhỏ thêm:

1. Validate và chuẩn hóa criteria.
2. Build Query/NativeQuery.
3. Chờ và gửi request qua client.
4. Deserialize và map response.
5. Chuyển SearchHits thành DTO.
6. Serialize HTTP response.

Ví dụ đo riêng query building và Elasticsearch call:

~~~java
long buildStarted = System.nanoTime();
Query query = queryBuilder.build(criteria, pageable);
Duration buildDuration =
        Duration.ofNanos(System.nanoTime() - buildStarted);

long searchStarted = System.nanoTime();
SearchHits<Product> hits =
        operations.search(query, Product.class);
Duration applicationSearchDuration =
        Duration.ofNanos(System.nanoTime() - searchStarted);

long mappingStarted = System.nanoTime();
ProductSearchResponse response = mapper.toResponse(hits);
Duration mappingDuration =
        Duration.ofNanos(System.nanoTime() - mappingStarted);
~~~

Từ các số liệu này, có thể xác định phần build query hoặc mapping có đáng kể hay không. Tránh thêm quá nhiều timer nhỏ nếu không có câu hỏi chẩn đoán cụ thể; instrumentation quá dày cũng làm code và metrics khó quản lý.

## 10. Dùng distributed tracing để tìm đoạn chờ

Metrics cho biết latency phân phối theo thời gian, nhưng không luôn chỉ ra request đã chờ ở đâu. Distributed tracing có thể tạo span cho:

- HTTP request vào service.
- Gọi repository/service.
- Elasticsearch client request.
- Các dịch vụ downstream khác.

Nếu client instrumentation hỗ trợ, trace có thể liên kết span ứng dụng với lời gọi Elasticsearch. Khi có trace ID, đối chiếu với log ứng dụng và server logs để tìm request cụ thể.

Với Spring Boot, có thể dùng Micrometer Observation/Tracing và exporter tương ứng. Khả năng tự động tạo span cho Elasticsearch phụ thuộc phiên bản Spring Boot, Elasticsearch Java Client và cấu hình instrumentation. Hãy xác minh span thực sự được tạo thay vì giả định chỉ vì đã thêm tracing dependency.

Tracing bổ sung góc nhìn chuỗi request; nó không thay thế server-side took, slow logs hoặc node metrics.

## 11. Elasticsearch slow logs

Slow logs ghi nhận các truy vấn vượt ngưỡng thời gian cấu hình trên từng shard. Chúng giúp xác định query phase hoặc fetch phase đang chậm và lưu lại thông tin phục vụ điều tra.

Hai nhóm thường cần phân biệt:

- **Query slow log:** thời gian shard xử lý query phase, tìm document và tính điểm.
- **Fetch slow log:** thời gian shard lấy nội dung document và chuẩn bị kết quả.

Một request có query đơn giản nhưng trả rất nhiều field hoặc source lớn có thể tốn thời gian ở fetch phase. Vì vậy, không chỉ nhìn query slow log.

Có thể cấu hình threshold theo cấp index bằng index settings. Ví dụ minh họa:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "search": {
      "slowlog": {
        "threshold": {
          "query": {
            "warn": "2s",
            "info": "1s",
            "debug": "500ms"
          },
          "fetch": {
            "warn": "1s",
            "info": "500ms",
            "debug": "250ms"
          }
        }
      }
    }
  }
}
~~~

Các threshold trên chỉ là ví dụ. Cấu trúc setting, cấp độ log và tên logger cần được xác nhận theo phiên bản Elasticsearch. Đặt threshold quá thấp có thể tạo lượng log rất lớn. Bắt đầu với ngưỡng phù hợp SLA rồi điều chỉnh theo lưu lượng và dung lượng log.

Slow logs là số đo theo shard/phase, không phải một phép đo thay thế application elapsed hoặc toàn bộ response took.

## 12. Profile API để phân tích query

Elasticsearch Profile API cung cấp thông tin chi tiết về thời gian các thành phần query trên shard:

~~~http
GET /products/_search
Content-Type: application/json

{
  "profile": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

Profile có thể cho biết các query component và collector đã tốn bao lâu theo góc nhìn shard. Nó hữu ích khi cần xác định clause nào gây chi phí lớn.

Không bật Profile API thường trực cho mọi request production:

- Profiling tạo overhead và có thể làm query chậm hơn.
- Kết quả chi tiết, nhiều dữ liệu và khó tổng hợp thành metric SLA.
- Profile không đo toàn bộ thời gian từ ứng dụng, network và client mapping.
- Thời gian các component không nhất thiết cộng thành took hoặc application elapsed.

Chỉ bật cho request điều tra có kiểm soát, trên dữ liệu và môi trường phù hợp.

## 13. Theo dõi node, thread pool và index statistics

Nếu took tăng đồng thời với queue/rejection hoặc CPU cao, vấn đề có thể nằm ở tải cluster thay vì một query riêng.

Các nguồn dữ liệu hữu ích:

| Nguồn | Điều cần quan sát |
|---|---|
| Node stats | CPU, heap, garbage collection, thread pool, filesystem |
| Thread pool stats | Queue và rejected tasks của search/write pools |
| Index stats | Search query/fetch count và thời gian tích lũy, indexing, refresh, merge |
| Tasks API | Tác vụ dài như update-by-query, reindex, search task |
| Hot threads | Thread đang tiêu tốn CPU trong thời điểm điều tra |
| Slow logs | Query/fetch chậm ở shard |

Ví dụ đọc search thread pool:

~~~http
GET /_nodes/stats/thread_pool
~~~

Đọc thống kê search của index:

~~~http
GET /products/_stats/search
~~~

Đọc tác vụ đang chạy:

~~~http
GET /_tasks?detailed=true&actions=*search
~~~

Các thống kê tích lũy như query_time_in_millis cần được xem cùng delta và khoảng thời gian lấy mẫu. Không chia tổng thời gian tích lũy cho một request đơn lẻ rồi coi đó là latency hiện tại.

## 14. Thiết kế benchmark có thể so sánh

Một phép đo chỉ có ý nghĩa khi các lần chạy có điều kiện tương đương. Khi so sánh hai query hoặc hai cách triển khai, giữ ổn định:

- Dataset và số lượng document.
- Mapping và analyzer.
- Số primary shard và replica.
- Routing và số shard thực sự được truy vấn.
- Refresh interval và trạng thái refresh.
- Query DSL, sort, highlight, aggregation.
- Page size và số field/source cần trả về.
- Mức concurrency và workload nền.
- Trạng thái cache và warm-up.

Không so sánh một query chạy trên index vừa được warm với một query chạy trên index vừa khởi động rồi kết luận chênh lệch đến từ DSL.

### 14.1. Warm-up và JIT

Lần chạy đầu có thể chịu chi phí khởi tạo connection, class loading, JIT compilation hoặc cache lạnh. Hãy chạy một số lượt warm-up trước khi lấy mẫu. Ghi rõ đang đo cold-start hay steady-state vì hai mục tiêu này khác nhau.

### 14.2. Đo p50, p95 và p99

Không chỉ báo cáo average. Phân phối latency thường có đuôi dài:

- p50 mô tả request điển hình.
- p95 cho biết 5% request chậm hơn ngưỡng đó.
- p99 cho biết tail latency ở nhóm request chậm nhất.

Ghi thêm throughput, error rate, timeout và mức concurrency. Một thay đổi giảm average nhưng làm p99 xấu đi có thể gây trải nghiệm kém cho một nhóm người dùng.

### 14.3. Thay đổi từng yếu tố

Nếu cùng lúc đổi page size, analyzer, số shard và refresh interval, sẽ khó biết thay đổi nào tạo ra kết quả. Thử từng yếu tố trong điều kiện kiểm soát, sau đó mới kiểm tra kết hợp.

Không dùng Profile API trong lượt benchmark latency thông thường vì profiling tự thêm chi phí. Dùng nó ở lượt chẩn đoán riêng sau khi đã xác định query cần điều tra.

## 15. Các yếu tố dễ làm sai lệch số đo

### 15.1. Refresh policy

refresh=true có thể ép refresh ngay và làm write request tốn thêm thời gian. refresh=wait_for có thể khiến ứng dụng chờ refresh kế tiếp. Application timer quanh write sẽ phản ánh khoảng chờ đó, trong khi không phải mọi write response đều cung cấp một server took tương ứng.

Không so sánh hai lần ghi nếu một lần dùng refresh mặc định và lần kia dùng refresh=wait_for mà không ghi nhận khác biệt này.

### 15.2. Connection pool

Khi connection pool cạn hoặc có connection phải thiết lập mới, ứng dụng có thể chờ trước khi Elasticsearch nhận request. Kiểm tra connection reuse, pool limits, pending acquisition và lỗi connection.

### 15.3. Response size

Page size lớn, _source lớn, highlight nhiều fragment hoặc inner hits sâu có thể làm tăng truyền dữ liệu và mapping. Server took có thể không phản ánh đầy đủ thời gian ứng dụng deserialize và chuyển đổi response.

Thử nghiệm với cùng response shape và kích thước kết quả khi so sánh.

### 15.4. Retry và timeout

Một lời gọi từ ứng dụng có thể chứa retry hoặc timeout ở transport/client layer. Application elapsed có thể bao gồm nhiều lần thử. Server có thể chỉ báo thời gian của request đã đến node, hoặc mỗi request riêng lẻ có duration riêng.

Ghi nhận retry count và outcome. Không gộp nhiều lần thử thành một took giả định.

### 15.5. Concurrency và tải nền

Query nhanh khi chạy đơn lẻ có thể chậm dưới tải do queue, CPU, heap, I/O hoặc contention. Benchmark cần concurrency gần workload thực tế và theo dõi cluster cùng lúc.

## 16. Đọc kết quả để xác định hướng điều tra

| Quan sát | Hướng điều tra tiếp |
|---|---|
| App time cao, server took thấp | Connection pool, network, serialization, mapping, callback, application thread |
| App time và server took cùng cao | Query, shard load, fetch, aggregation, cluster resource |
| Query slow log cao, fetch thấp | Query DSL, analyzer, scoring, filter, shard distribution |
| Query thấp, fetch cao | _source size, page size, stored fields, highlight, inner hits |
| p50 tốt nhưng p99 xấu | Queue, GC, contention, hot shard, tải nền, retry |
| Server took cao cùng search queue tăng | Search thread pool saturation hoặc node quá tải |
| Chỉ endpoint tổng thể chậm, ES call bình thường | Business logic, downstream service, DTO mapping, response serialization |
| Bulk app time cao nhưng bulk took thấp | Client preparation, payload serialization, network hoặc response handling |

Các dòng trong bảng là hướng dẫn chẩn đoán, không phải kết luận tự động. Cần đối chiếu trace, logs, metrics và workload thực tế.

## 17. Checklist đo lường trong production

- [ ] Định nghĩa rõ application timer bắt đầu/kết thúc ở đâu.
- [ ] Dùng System.nanoTime() hoặc Micrometer Timer để đo elapsed.
- [ ] Ghi cả success, error, timeout và cancellation.
- [ ] Ghi server took riêng khi response cung cấp.
- [ ] Không suy ra server duration từ app elapsed.
- [ ] Không gọi app time trừ took là network time chính xác.
- [ ] Dùng metric tags cardinality thấp.
- [ ] Dùng trace ID cho đối chiếu request cụ thể.
- [ ] Theo dõi p50, p95, p99, throughput và error rate.
- [ ] Kiểm tra query/fetch slow logs khi server search chậm.
- [ ] Chỉ bật Profile API trong lượt điều tra có kiểm soát.
- [ ] Theo dõi thread pool queue/rejection, CPU, heap và index stats.
- [ ] Giữ ổn định dataset, mapping, shard, refresh và concurrency khi benchmark.
- [ ] Đo reactive publisher từ lúc subscribe đến terminal signal.

## 18. Kết luận

Thời gian phía ứng dụng và thời gian Elasticsearch là hai số đo khác nhau. Application elapsed phản ánh khoảng thời gian caller chờ một thao tác Spring Data/client hoàn tất, bao gồm nhiều chi phí client, network, server và mapping. Search took hoặc SearchHits.getExecutionDuration() phản ánh duration Elasticsearch báo cáo trong response, hữu ích để đánh giá phần xử lý phía server.

Hãy đo application elapsed bằng System.nanoTime() hoặc Micrometer Timer, đồng thời ghi server duration riêng khi API cung cấp. Với những write response không có took tương ứng, dùng tracing, slow logs và node/index metrics để điều tra; không tạo ra một con số server giả bằng cách dùng app elapsed.

Khi app time cao nhưng server took thấp, điều tra connection pool, network, serialization và mapping. Khi cả hai đều cao, xem query/fetch slow logs, Profile API trong lượt chẩn đoán riêng và tài nguyên cluster. Benchmark với warm-up, concurrency, dữ liệu và response shape ổn định; theo dõi p50/p95/p99 thay vì chỉ nhìn average. Ranh giới đo rõ ràng giúp tìm đúng nơi gây chậm và tránh tối ưu nhầm tầng.
