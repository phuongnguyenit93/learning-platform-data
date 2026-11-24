# Điều tra một request chậm

Khi một request Spring Boot phản hồi chậm, chỉ nhìn log lỗi hoặc thời gian trung bình thường không đủ để tìm nguyên nhân. Metrics cho biết độ trễ đang ảnh hưởng đến bao nhiêu request và bắt đầu từ khi nào; distributed trace cho biết thời gian được tiêu thụ ở từng service và operation; logs cung cấp chi tiết theo đúng request để xác nhận điều đã xảy ra. Kết hợp ba tín hiệu này giúp đi từ triệu chứng đến nguyên nhân có bằng chứng.

Bài thực hành này mô phỏng sự cố ở hệ thống đặt hàng. API của checkout phản hồi chậm, trong khi CPU và tỷ lệ lỗi vẫn bình thường. Bạn sẽ dùng Micrometer metrics, trace context và log correlation để lần theo request qua các service, nhận diện lời gọi nhà cung cấp tồn kho bị chậm và tìm ra transaction đang giữ kết nối cơ sở dữ liệu trong lúc chờ HTTP. Cuối bài, bạn sẽ đề xuất cách sửa và tiêu chí xác nhận sau khi triển khai.

## Mục tiêu thực hành

Sau bài này, bạn có thể:

- Xác định thời điểm và phạm vi ảnh hưởng của latency tăng bằng metrics.
- Chọn trace đại diện và đọc quan hệ cha-con, duration, timestamp và span attribute.
- Dùng trace ID để ghép log của cùng một request qua nhiều service.
- Phân biệt truy vấn database chậm, downstream chậm và connection pool bị bão hòa.
- Đề xuất thay đổi có thể kiểm chứng, rồi xác nhận bằng cùng bộ tín hiệu sau khi sửa.

## Bối cảnh sự cố

Hệ thống có ba service chính. Người dùng gọi checkout để xem thông tin đơn hàng; checkout đọc dữ liệu đơn, gọi inventory để kiểm tra tồn kho và gọi pricing để lấy giá hiện tại.

~~~mermaid
flowchart LR
    U[Client] --> C[checkout-api]
    C --> I[inventory-service]
    C --> P[pricing-service]
    I --> DB[(Inventory DB)]
    I --> S[Supplier API]
    C -. metrics, logs, traces .-> O[Observability backend]
    I -. metrics, logs, traces .-> O
    P -. metrics, logs, traces .-> O
~~~

Trong khoảng 10 phút gần đây, dashboard ghi nhận:

| Chỉ số | Baseline | Hiện tại |
| --- | ---: | ---: |
| checkout GET p50 | 85 ms | 110 ms |
| checkout GET p95 | 240 ms | 1.8 s |
| checkout GET p99 | 420 ms | 3.5 s |
| HTTP 5xx | 0.3% | 0.4% |
| CPU checkout | 42% | 45% |
| CPU inventory | 39% | 41% |

Độ trễ ở p95 và p99 tăng rõ rệt nhưng error rate và CPU gần như ổn định. Đây là dấu hiệu cho thấy một nhóm request đang phải chờ một tài nguyên hoặc dependency; CPU thấp không có nghĩa ứng dụng khỏe nếu các thread đang chờ I/O, connection hoặc lock.

Một request cụ thể có các thông tin đã được ghi nhận:

- Route: GET /api/orders/{id}
- Service nhận request: checkout-api
- Trace ID: 4f6c2d8e9a104c3fb78a2e5c1d9a7b21
- Tổng thời gian: khoảng 3.42 giây
- Kết quả HTTP: 200

ID trong ví dụ chỉ dùng để minh họa. Trong môi trường thật, không đưa order ID, user ID hay dữ liệu cá nhân vào metric tag. Hãy dùng trace ID để tra cứu request và chỉ hiển thị định danh nghiệp vụ khi chính sách dữ liệu cho phép.

## Bước 1: Khoanh vùng bằng metrics

Trước khi mở một trace riêng lẻ, xác nhận sự cố có phạm vi đủ lớn để giải thích cảnh báo. Kiểm tra latency theo service, route, method và status; sau đó đối chiếu request rate, error rate, tài nguyên và các dependency.

Để có dữ liệu minh họa bên dưới, ứng dụng cần có Actuator, registry Prometheus và tracing bridge/exporter tương ứng. Cấu hình tối thiểu có thể bắt đầu như sau:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: 0.1
~~~

Chỉ expose endpoint quản trị trong mạng và phạm vi đã được bảo vệ. Tỷ lệ sampling 0.1 là ví dụ để minh họa; chọn giá trị theo traffic, chi phí và yêu cầu điều tra. Sampling thấp có thể bỏ sót request chậm hiếm gặp, còn sampling cao làm tăng lượng trace cần ingest và lưu trữ.

Nếu Prometheus nhận histogram từ Micrometer, có thể tính p95 của HTTP server request bằng truy vấn sau. Tên metric và label thực tế phụ thuộc registry, convention và phiên bản cấu hình:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/orders/{id}",
      method="GET"
    }[5m])
  )
)
~~~

Đối chiếu với p99 và error ratio:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/orders/{id}",
      method="GET"
    }[5m])
  )
)
~~~

~~~promql
sum(rate(http_server_requests_seconds_count{
  uri="/api/orders/{id}",
  method="GET",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  uri="/api/orders/{id}",
  method="GET"
}[5m]))
~~~

Histogram phải được bật và scrape đúng thì truy vấn phân vị mới có dữ liệu phù hợp. Nếu chỉ có timer count/sum, bạn có thể tính throughput và latency trung bình, nhưng không thể suy ra p95 hoặc p99 chính xác từ hai giá trị đó. Không dùng average để kết luận rằng request chậm đã biến mất.

Kiểm tra metric của một meter trực tiếp qua Actuator khi endpoint được expose và bảo vệ phù hợp:

~~~bash
curl -G "http://localhost:8080/actuator/metrics/http.server.requests" \
  --data-urlencode "tag=uri:/api/orders/{id}" \
  --data-urlencode "tag=method:GET"
~~~

Kết quả Actuator cho biết meter có tồn tại, các tag được hỗ trợ và thống kê count/total phù hợp với meter. Đây là cách kiểm tra tại một instance; dashboard Prometheus hoặc backend metrics vẫn cần được dùng để xem xu hướng toàn cụm.

Tiếp theo, so sánh latency của các service và dependency trong cùng khoảng thời gian. Trong tình huống này, checkout chậm cùng lúc inventory chậm; pricing vẫn gần baseline. Điều đó giúp ưu tiên kiểm tra nhánh inventory trước khi xem xét database của checkout hoặc serialization ở gateway.

## Bước 2: Chọn trace có ích

Mở trace có trace ID đã lấy từ request log hoặc công cụ quan sát. Kiểm tra service, operation, thời gian bắt đầu, tổng duration, trạng thái và các span con. Chọn trace chậm thuộc đúng route, phiên bản và khoảng thời gian bị ảnh hưởng; sau đó so sánh với một trace bình thường của cùng route.

Trace minh họa của request có cấu trúc như sau:

| Span | Service | Duration |
| --- | --- | ---: |
| HTTP GET /api/orders/{id} | checkout-api | 3,420 ms |
| order.repository.findById | checkout-api | 18 ms |
| HTTP GET /api/inventory/{sku} | checkout-api → inventory-service | 3,150 ms |
| HTTP GET /api/prices/{sku} | checkout-api → pricing-service | 42 ms |

Ba nhánh không nhất thiết chạy tuần tự trong mọi ứng dụng. Khi đọc waterfall, hãy dựa vào timestamp bắt đầu và thời gian kết thúc để xác định span nào thực sự nằm trên critical path. Không cộng duration của các span chạy song song rồi coi tổng đó là thời gian request.

Lời gọi inventory chiếm gần hết thời gian của request. Mở trace phía inventory bằng context được propagation qua HTTP. Trace phân rã ở service này cho thấy:

| Operation trong inventory | Duration |
| --- | ---: |
| inventory.lookup | 3,100 ms |
| inventory.repository.findStock | 16 ms |
| supplier.client.getStatus | 2,910 ms |
| Xử lý còn lại | khoảng 174 ms |

Truy vấn database chỉ mất 16 ms, trong khi lời gọi Supplier API chiếm gần 3 giây. Điều này loại bỏ giả thuyết “câu SQL chính là nguyên nhân chính” cho request đang xem. Nó cũng chỉ ra dependency cần được điều tra tiếp.

Khi đọc trace, kiểm tra thêm:

- Parent-child: span client có liên kết đúng với span server ở service đích không?
- Propagation: trace ID có được giữ qua HTTP boundary không, hay trace bị tách thành hai cây độc lập? Với HTTP client/server được instrument phù hợp, Micrometer Tracing có thể inject/extract context theo định dạng như W3C traceparent.
- Status và event: có exception, timeout, retry hoặc event bất thường trong span không?
- Attribute: method, route template, peer service, status code và phiên bản có đủ để phân loại không?
- Sampling: trace đang xem có phải trace đã được lấy mẫu theo cấu hình hiện tại không?

Một trace riêng lẻ giải thích đường đi của một request, nhưng chưa chứng minh toàn bộ traffic có cùng nguyên nhân. Dùng metrics để kiểm tra tính phổ biến và trace để hiểu chi tiết từng đường đi.

## Bước 3: Ghép logs bằng trace ID

Sau khi xác định span Supplier API chậm, tìm log của đúng trace để xem timeout, retry, response status và các mốc thời gian. Các service cần ghi trace ID và span ID vào log context. Khi dùng Micrometer Tracing, các giá trị này có thể được đưa vào MDC; cấu hình pattern phải giữ chúng trong log output.

Ví dụ một pattern level cho Logback:

~~~yaml
logging:
  pattern:
    level: "%5p [%X{traceId:-},%X{spanId:-}]"
~~~

Nếu dùng JSON encoder hoặc hệ thống thu thập log khác, ánh xạ các trường tương đương thành field có cấu trúc như service, trace_id, span_id, event và duration_ms. Tên field có thể khác giữa pipeline; cần thống nhất mapping trước khi truy vấn.

Log mẫu của cùng trace:

~~~json
{
  "timestamp": "2026-11-22T07:18:31.420Z",
  "level": "WARN",
  "service": "inventory-service",
  "event": "supplier.request.slow",
  "duration_ms": 2910,
  "http_method": "GET",
  "http_status": 200,
  "trace_id": "4f6c2d8e9a104c3fb78a2e5c1d9a7b21",
  "span_id": "8d7a1c2e3f4b5a60"
}
~~~

Truy vấn log theo trace ID trong hệ thống log của bạn, ví dụ về mặt logic:

~~~text
trace_id = "4f6c2d8e9a104c3fb78a2e5c1d9a7b21"
~~~

Đọc log theo timestamp và span ID để giữ đúng thứ tự. Một trace có thể có nhiều log ở nhiều service; trace ID ghép chúng vào cùng request, còn span ID giúp xác định log phát ra từ operation nào. Nếu log không có trace ID, hãy kiểm tra cấu hình MDC, log pattern/encoder và việc context có bị mất khi chuyển sang executor hoặc thread khác.

Không thêm trace ID vào metric tag. Trace ID có giá trị gần như duy nhất cho mỗi request, khiến cardinality tăng theo traffic. Hãy dùng trace ID trong traces và logs; metrics chỉ nên có dimension với tập giá trị hữu hạn như service, route template, method, status hoặc outcome.

## Bước 4: Kiểm tra connection pool và transaction

Log cho thấy Supplier API phản hồi chậm nhưng request vẫn thành công. Để biết sự chậm trễ này có ảnh hưởng lan sang request khác hay không, kiểm tra metrics của HikariCP ở inventory trong cùng khoảng thời gian:

| Metric | Quan sát |
| --- | ---: |
| hikaricp.connections.max | 20 |
| hikaricp.connections.active | 20 |
| hikaricp.connections.idle | 0 |
| hikaricp.connections.pending | 17 |
| hikaricp.connections.acquire p95 | 2.8 s |

Active chạm giới hạn, idle bằng 0 và pending tăng cho thấy request đang phải chờ kết nối. Acquire duration tăng xác nhận thời gian lấy connection là một vấn đề thực tế trong giai đoạn này; p95 của timer chỉ có thể truy vấn khi histogram hoặc percentile tương ứng được cấu hình. Tên metric Prometheus có thể được chuyển thành dạng underscore, ví dụ hikaricp_connections_active; hãy kiểm tra tên và tag do registry đang xuất.

Các metrics này cho biết pool bị bão hòa, nhưng chưa tự giải thích tại sao connection bị giữ lâu. Đối chiếu code path và trace operation với ranh giới transaction. Giả sử code hiện tại có dạng:

~~~java
@Service
public class InventoryService {
    private final StockRepository stockRepository;
    private final SupplierClient supplierClient;

    public InventoryService(
            StockRepository stockRepository,
            SupplierClient supplierClient) {
        this.stockRepository = stockRepository;
        this.supplierClient = supplierClient;
    }

    @Transactional(readOnly = true)
    public InventoryView lookup(String sku) {
        Stock stock = stockRepository.findBySku(sku)
                .orElseThrow();
        SupplierStatus status = supplierClient.getStatus(sku);
        return new InventoryView(stock, status);
    }
}
~~~

Transaction bao trùm cả truy vấn database và lời gọi HTTP đến Supplier API. Connection được lấy cho transaction có thể tiếp tục bị giữ trong khi thread chờ network response. Khi Supplier API chậm và có nhiều request đồng thời, các connection bị giữ lâu làm pool cạn; request khác phải xếp hàng chờ connection. Như vậy một dependency chậm có thể khuếch đại thành hiện tượng chậm trên nhiều request trong inventory.

Trace của một request cho thấy Supplier API là phần tiêu tốn thời gian trực tiếp. Metrics HikariCP cho thấy pool bị bão hòa trong cùng khoảng thời gian. Ranh giới transaction trong code giải thích mối liên hệ giữa hai dấu hiệu. Cần giữ riêng ba kết luận này: trace chỉ ra critical path của request; pool metrics chỉ ra trạng thái tài nguyên toàn service; code xác định cách tài nguyên bị giữ.

## Bước 5: Đề xuất và thực hiện thay đổi

Có hai vấn đề cần xử lý. Thứ nhất, Supplier API phản hồi chậm nên request hiện tại vẫn phải đợi. Thứ hai, transaction giữ DB connection trong lúc chờ network, khiến độ trễ của dependency lan thành connection pool starvation. Sửa transaction boundary sẽ giảm áp lực lên pool, nhưng tự nó không làm Supplier API nhanh hơn và cũng không đảm bảo p95 của request giảm nếu request vẫn phải chờ cùng lời gọi đó.

Với luồng đọc này, có thể giới hạn transaction vào phần đọc database bằng một bean riêng:

~~~java
@Service
public class StockReader {
    private final StockRepository stockRepository;

    public StockReader(StockRepository stockRepository) {
        this.stockRepository = stockRepository;
    }

    @Transactional(readOnly = true)
    public StockSnapshot find(String sku) {
        Stock stock = stockRepository.findBySku(sku)
                .orElseThrow();
        return new StockSnapshot(
                stock.getSku(),
                stock.getAvailableQuantity());
    }
}

public record StockSnapshot(String sku, int availableQuantity) {}
~~~

~~~java
@Service
public class InventoryService {
    private final StockReader stockReader;
    private final SupplierClient supplierClient;

    public InventoryService(
            StockReader stockReader,
            SupplierClient supplierClient) {
        this.stockReader = stockReader;
        this.supplierClient = supplierClient;
    }

    public InventoryView lookup(String sku) {
        StockSnapshot stock = stockReader.find(sku);
        SupplierStatus status = supplierClient.getStatus(sku);
        return new InventoryView(stock, status);
    }
}
~~~

StockReader là bean riêng để lời gọi đi qua Spring transaction proxy. Khi phương thức find kết thúc, transaction đọc hoàn tất trước khi InventoryService gọi Supplier API. Tránh gọi một phương thức @Transactional khác trong cùng object rồi kỳ vọng self-invocation kích hoạt proxy.

Tiếp theo, xử lý latency của Supplier API theo yêu cầu nghiệp vụ:

- Đặt connect timeout và response/read timeout hữu hạn, phù hợp với ngân sách latency của request cha.
- Dùng bulkhead hoặc giới hạn concurrency để một dependency chậm không chiếm hết tài nguyên xử lý.
- Dùng circuit breaker nếu cần ngừng gọi dependency đang lỗi kéo dài; xác định rõ response fallback có an toàn cho nghiệp vụ hay không.
- Chỉ retry lỗi có thể retry, giới hạn số lần và tổng thời gian retry; tránh retry đồng loạt làm tăng tải khi Supplier API đang quá tải.
- Cân nhắc cache cho dữ liệu trạng thái có thể chấp nhận độ cũ, với TTL và quy tắc invalidation rõ ràng.

Không tăng max pool một cách máy móc. Pool lớn hơn có thể đẩy áp lực sang database, che khuất transaction giữ connection quá lâu và làm tăng số truy vấn đồng thời. Chỉ điều chỉnh pool sau khi đo được concurrency cần thiết và giới hạn của database.

Nếu nghiệp vụ cần một transaction nguyên tử bao trùm nhiều bước, không tự ý tách transaction làm thay đổi tính đúng đắn. Hãy xem xét thiết kế workflow, saga, outbox hoặc cơ chế bù trừ phù hợp thay vì giữ connection database trong một lời gọi mạng dài.

## Bước 6: Xác nhận sau thay đổi

Triển khai thay đổi ở phạm vi nhỏ và so sánh canary với phiên bản ổn định dưới cùng loại traffic. Giữ nguyên bộ dashboard, truy vấn và khoảng thời gian đủ dài để có số mẫu đại diện.

Các dấu hiệu mong đợi:

| Tín hiệu | Kết quả cần xác nhận |
| --- | --- |
| Trace inventory | Transaction kết thúc sau thao tác database; supplier call nằm ngoài transaction |
| HikariCP | Active không bị giữ ở max kéo dài; pending giảm; acquire p95 trở về gần baseline |
| Supplier client | Duration giảm sau tối ưu dependency, hoặc timeout/fallback được kích hoạt đúng ngân sách |
| checkout HTTP | p95/p99 giảm khi critical path thực sự ngắn lại |
| Logs | Trace ID/span ID vẫn liên kết được qua các service; không tăng timeout hoặc retry bất thường |
| Error rate | Không tăng lỗi nghiệp vụ hoặc lỗi do timeout/fallback |

Nếu chỉ tách transaction mà Supplier API vẫn mất gần 3 giây, HikariCP có thể phục hồi nhưng request vẫn chậm gần như cũ. Nếu Supplier API nhanh hơn nhưng transaction vẫn bao trùm network call, pool vẫn có nguy cơ cạn khi tải tăng. Xác nhận từng kết quả riêng để biết thay đổi nào đã giải quyết vấn đề nào.

Rollback hoặc dừng rollout nếu error rate tăng, dữ liệu nghiệp vụ sai, fallback làm thay đổi hành vi ngoài dự kiến, hoặc connection pool và latency xấu đi. Ghi lại trace, dashboard snapshot, log và phiên bản cấu hình để có thể so sánh trước/sau.

## Các giả thuyết khác cần loại trừ

Không phải mọi request chậm đều do downstream hoặc connection pool. Dùng dấu hiệu trong cả ba tín hiệu để kiểm tra các khả năng khác:

| Giả thuyết | Dấu hiệu trong metrics | Dấu hiệu trong trace/log |
| --- | --- | --- |
| SQL chậm | DB query duration tăng, DB load hoặc lock wait tăng | JDBC span dài, log query chậm |
| Downstream chậm | Client latency tăng theo dependency | Client span dài; server span phía đích cũng dài nếu propagation hoạt động |
| Pool starvation | Hikari active chạm max, pending và acquire duration tăng | Request chờ tài nguyên; operation giữ connection có thể kéo dài |
| CPU hoặc GC | CPU cao, throttling hoặc GC pause tăng | Nhiều span trong process chậm cùng lúc; log GC có pause tương ứng |
| Lock contention | Thread blocked/wait tăng, throughput giảm | Span chứa đoạn chờ lock kéo dài; thread dump hỗ trợ xác minh |
| Serialization hoặc xử lý trong ứng dụng | CPU/request hoặc thời gian xử lý tăng dù dependency ổn định | Span nội bộ dài, không có client/DB span tương ứng |

Nếu trace không xuất hiện, chưa thể kết luận request không xảy ra. Có thể request không được sampling, trace context không được propagation, hoặc exporter/backend đang lỗi. Dùng metrics để xác nhận traffic, kiểm tra log correlation và trạng thái exporter trước khi kết luận. Với head-based sampling, một request chậm hiếm gặp có thể không được giữ lại; có thể cần sampling policy phù hợp hoặc tail sampling ở collector nếu kiến trúc hỗ trợ.

## Checklist điều tra request chậm

- [ ] Xác định route, service, phiên bản và khoảng thời gian có latency tăng.
- [ ] Kiểm tra p50/p95/p99, request rate và error rate; không chỉ xem average.
- [ ] So sánh service và dependency để khoanh vùng critical path.
- [ ] Mở trace chậm và trace bình thường của cùng route để đối chiếu.
- [ ] Xác nhận trace context được propagation qua các service boundary.
- [ ] Ghép logs bằng trace ID và dùng span ID để xác định operation phát log.
- [ ] Kiểm tra pool, database, thread, CPU, GC và các tài nguyên liên quan.
- [ ] Đối chiếu số liệu với code path và ranh giới transaction trước khi kết luận nguyên nhân.
- [ ] Đưa ra thay đổi có giả thuyết, ngưỡng rollback và chỉ số xác nhận rõ ràng.
- [ ] Sau triển khai, xác minh riêng latency, error rate, tài nguyên và chất lượng telemetry.

Một cuộc điều tra tốt kết thúc bằng chuỗi bằng chứng có thể kiểm tra lại: metrics xác định phạm vi và thời điểm; trace chỉ ra operation nằm trên critical path; logs bổ sung sự kiện của đúng request; metrics tài nguyên và code giải thích cơ chế gây chậm. Khi cả ba tín hiệu nhất quán, nhóm vận hành có thể sửa đúng nguyên nhân và đo được tác động của thay đổi.
