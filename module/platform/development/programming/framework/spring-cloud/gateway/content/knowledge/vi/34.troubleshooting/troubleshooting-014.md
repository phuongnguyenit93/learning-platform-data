# Thu thập bằng chứng từ Actuator, access log, metrics và tracing

Khi một request đi qua Spring Cloud Gateway gặp lỗi hoặc phản hồi chậm, chỉ nhìn vào HTTP status thường không đủ để xác định nguyên nhân. Gateway có thể không chọn được route, một filter có thể từ chối request, service discovery có thể trả về instance không còn hoạt động, hoặc dịch vụ phía sau có thể xử lý chậm. Muốn phân biệt các trường hợp này, cần ghép bằng chứng từ bốn nguồn: Actuator cho biết trạng thái và cấu hình đang chạy, access log ghi lại từng request, metrics cho thấy xu hướng theo thời gian, còn tracing mô tả request đi qua những thành phần nào.

Bài học này tập trung vào Spring Cloud Gateway chạy trên WebFlux và Reactor Netty. Các nguyên tắc tương quan bằng chứng vẫn áp dụng cho những biến thể khác, nhưng cách bật access log và một số endpoint quản trị có thể khác theo phiên bản Spring Boot, Spring Cloud Gateway và máy chủ HTTP đang dùng.

## 1. Xác định câu hỏi cần trả lời

Trước khi mở dashboard hoặc đọc log, hãy mô tả sự cố bằng một request cụ thể. Tối thiểu cần có:

- Thời điểm xảy ra, kèm múi giờ.
- HTTP method, đường dẫn đã được che dữ liệu nhạy cảm và route dự kiến.
- HTTP status trả về, thời gian phản hồi quan sát được và số lần tái hiện.
- Request ID hoặc trace ID nếu hệ thống đã phát sinh các giá trị này.
- Phiên bản ứng dụng và môi trường xảy ra sự cố nếu có nhiều bản triển khai.

Các giá trị này tạo thành khóa để đối chiếu. Thời gian giúp giới hạn cửa sổ tìm kiếm; route ID giúp lọc metrics; request ID giúp tìm một dòng log; trace ID giúp mở toàn bộ dấu vết phân tán. Không dùng URL đầy đủ chứa query string, token, email hoặc dữ liệu cá nhân làm khóa tìm kiếm trong log.

Một request đi qua Gateway thường có các chặng: client hoặc load balancer gửi request, Gateway chọn route bằng predicate, chuỗi filter xử lý request, Gateway định tuyến đến upstream, rồi nhận và trả response. Mỗi nguồn quan sát trả lời một câu hỏi khác nhau:

| Nguồn | Câu hỏi chính | Bằng chứng thường dùng |
|---|---|---|
| Actuator | Gateway đang chạy và đăng ký route/filter nào? | Health, danh sách route, global filter, metric hiện có |
| Access log và application log | Request cụ thể đã đến đâu và kết thúc thế nào? | Method, path đã làm sạch, route ID, status, thời lượng, request ID |
| Metrics | Lỗi hoặc độ trễ có tăng theo route và thời gian không? | Request rate, tỷ lệ lỗi, p95/p99, phân bố status |
| Tracing | Thời gian nằm ở Gateway hay dịch vụ phía sau? | Trace ID, span, thời lượng từng chặng, lỗi trong trace |

Không nên kết luận từ một nguồn đơn lẻ. Ví dụ, status 404 có thể do Gateway không tìm thấy route hoặc do upstream trả về 404; cần kiểm tra route ID và trace để phân biệt.

## 2. Dùng Actuator kiểm tra trạng thái runtime

Spring Boot Actuator cung cấp các endpoint quản trị. Với Gateway, chúng giúp xác nhận ứng dụng còn sống, kiểm tra route đã được nạp và đọc metrics đang được ghi nhận. Cần thêm dependency Actuator và cấu hình expose có chủ đích.

Ví dụ cấu hình YAML cho ứng dụng Spring Boot:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,gateway
  endpoint:
    gateway:
      enabled: true
  metrics:
    tags:
      application: spring-cloud-gateway

spring:
  cloud:
    gateway:
      metrics:
        enabled: true
```

Đây là cấu hình minh họa; endpoint `gateway` và các thuộc tính điều khiển endpoint cần được đối chiếu với phiên bản Spring Cloud Gateway đang chạy. Nếu hệ thống không dùng Prometheus thì có thể bỏ `prometheus`. Endpoint chỉ xuất hiện khi dependency, cấu hình và phiên bản tương ứng hỗ trợ nó.

Các endpoint thường hữu ích:

| Endpoint | Mục đích kiểm tra |
|---|---|
| `GET /actuator/health` | Xem trạng thái tổng thể và các health indicator được cấu hình |
| `GET /actuator/health/readiness` | Kiểm tra khả năng nhận traffic nếu readiness group đã được bật |
| `GET /actuator/gateway/routes` | Xác nhận route ID, URI đích, predicate và filter đã được nạp |
| `GET /actuator/gateway/routes/{id}` | Xem chi tiết một route theo ID |
| `GET /actuator/gateway/globalfilters` | Kiểm tra các global filter đang được đăng ký và thứ tự của chúng |
| `GET /actuator/metrics` | Liệt kê meter mà ứng dụng đang ghi nhận |
| `GET /actuator/metrics/spring.cloud.gateway.requests` | Xem số liệu tổng hợp của request qua Gateway |
| `GET /actuator/prometheus` | Xuất metrics theo định dạng Prometheus khi đã cài registry tương ứng |

Ví dụ đọc danh sách route từ máy có quyền truy cập management endpoint:

```bash
curl -sS http://localhost:8080/actuator/gateway/routes
```

Khi route mong đợi không xuất hiện, hãy kiểm tra cấu hình route, profile đang chạy, quá trình refresh cấu hình và service discovery. Khi route có xuất hiện, điều đó chỉ xác nhận route đã được nạp; chưa chứng minh upstream đang khỏe hoặc filter xử lý request đúng.

Endpoint `gateway` có thể cung cấp cả thao tác thay đổi trạng thái như refresh hoặc sửa route tùy phiên bản. Trong quá trình chẩn đoán thông thường, chỉ cần các thao tác đọc. Không mở endpoint quản trị có khả năng thay đổi runtime cho mạng công cộng. Hãy giới hạn management port hoặc đường dẫn bằng network policy, firewall và xác thực; chỉ expose đúng endpoint cần dùng. Tránh expose hàng loạt endpoint như `*` trong môi trường production.

## 3. Ghi access log có thể đối chiếu

Access log của Reactor Netty ghi lại thông tin request ở tầng HTTP server. Có thể bật bằng system property của JVM:

```bash
java -Dreactor.netty.http.server.accessLogEnabled=true -jar gateway.jar
```

System property cần được đặt trước khi server khởi động. Nếu chạy trong container, đặt nó vào JVM options của tiến trình Gateway. Access log hữu ích để biết request đã đến cổng vào, method, URI, status và thời lượng ở tầng server; định dạng cụ thể phụ thuộc phiên bản Reactor Netty.

Access log không nhất thiết biết route ID hoặc trace ID của ứng dụng. Để tương quan sâu hơn, có thể bổ sung một `GlobalFilter` ghi log lúc response kết thúc. Ví dụ sau minh họa các trường cơ bản:

```java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;

@Component
public class GatewayRequestEvidenceFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(GatewayRequestEvidenceFilter.class);

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        long startedAt = System.nanoTime();

        return chain.filter(exchange).doFinally(signal -> {
            Route route = exchange.getAttribute(
                    ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
            HttpStatusCode status = exchange.getResponse().getStatusCode();
            String routeId = route != null ? route.getId() : "unmatched";
            String path = exchange.getRequest().getPath()
                    .pathWithinApplication().value();
            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt);

            log.info(
                    "gateway_request method={} path={} routeId={} status={} durationMs={} requestId={} signal={}",
                    exchange.getRequest().getMethod(),
                    path,
                    routeId,
                    status != null ? status.value() : "none",
                    durationMs,
                    exchange.getRequest().getId(),
                    signal);
        });
    }
}
```

Filter này đo thời gian từ lúc bắt đầu chuỗi filter đến khi publisher kết thúc. `requestId` ở ví dụ là ID do WebFlux cung cấp; nó không tự động đồng nhất với trace ID. Route có thể chưa được gắn trong những trường hợp request không khớp route, vì vậy log dùng giá trị `unmatched` khi không có route attribute. Nếu cần phân biệt request bị từ chối sớm bởi một thành phần nằm trước filter này, hãy đối chiếu thêm access log ở tầng server.

Trước khi dùng ví dụ trong production, hãy chuẩn hóa đường dẫn. Đường dẫn thực tế có thể chứa mã khách hàng, email hoặc ID tài nguyên; nên ghi route template hoặc phiên bản đã che dữ liệu. Không ghi request body, `Authorization`, cookie, access token hay toàn bộ header. Nếu cần log một header tương quan do hệ thống tin cậy sinh ra, hãy giới hạn độ dài, xác thực nguồn và không cho client tùy ý dùng giá trị đó để gây nhiễu log.

Một dòng log tốt thường có timestamp kèm timezone, application/instance, method, route ID, status, duration, request ID và trace ID. Log dạng key-value hoặc JSON giúp truy vấn chính xác hơn chuỗi thông báo tự do. Đồng bộ thời gian giữa Gateway, upstream và hệ thống thu thập log để tránh tìm sai cửa sổ sự cố.

## 4. Dùng metrics để nhận ra xu hướng

Khi Actuator và Micrometer được cấu hình phù hợp, Gateway có thể ghi timer `spring.cloud.gateway.requests`. Metric này thường có các tag như `routeId`, `routeUri`, `outcome`, `status`, `httpStatusCode` và `httpMethod`. Tên metric và tag có thể thay đổi theo dòng phiên bản; hãy kiểm tra danh sách meter thực tế tại `/actuator/metrics`.

Đọc metric tổng hợp:

```bash
curl -sS \
  'http://localhost:8080/actuator/metrics/spring.cloud.gateway.requests'
```

Lọc theo route ID:

```bash
curl -sS \
  'http://localhost:8080/actuator/metrics/spring.cloud.gateway.requests?tag=routeId:catalog'
```

Actuator trả về các thống kê của meter, chẳng hạn count, total time và max. Đây là dữ liệu tổng hợp tại thời điểm đọc, phù hợp để kiểm tra nhanh. Để phân tích xu hướng và percentile ổn định, hãy scrape metrics bằng Prometheus hoặc hệ thống tương đương, đồng thời bật histogram cho timer cần theo dõi.

Ví dụ bật histogram cho timer Gateway:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "spring.cloud.gateway.requests": true
```

Với Prometheus, các chuỗi truy vấn thường có dạng sau nếu registry xuất timer theo tên chuẩn:

```promql
# Số request mỗi giây theo route
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count[5m])
)

# p95 thời gian request theo route; cần histogram bucket được xuất
histogram_quantile(
  0.95,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket[5m])
  )
)
```

Tên metric và tên label trong Prometheus phụ thuộc registry và cấu hình naming convention. Nếu truy vấn không có dữ liệu, kiểm tra `/actuator/prometheus` trước để xác nhận tên thực tế, sau đó sửa truy vấn theo đúng metric và label đang được xuất.

Khi đọc dashboard, nên theo dõi đồng thời:

- **Request rate:** lưu lượng tăng đột ngột có thể làm lộ giới hạn tài nguyên hoặc rate limiter.
- **Tỷ lệ lỗi:** phân tách theo HTTP status, outcome và route ID để biết lỗi tập trung ở route nào.
- **Latency:** xem p50, p95 và p99; giá trị trung bình có thể che khuất một nhóm request rất chậm.
- **Saturation:** CPU, heap, số kết nối, event loop và connection pool giúp nhận ra Gateway có bị quá tải hay không.

Không đưa request ID, trace ID, user ID hoặc URL chứa ID tài nguyên vào metric tag. Mỗi giá trị mới tạo thêm một time series; cardinality tăng nhanh có thể làm Prometheus tốn bộ nhớ và làm hệ thống metrics mất ổn định. Hãy giữ tag ở mức có giới hạn như route ID, method và status.

## 5. Dùng tracing để tìm chặng gây chậm hoặc lỗi

Metrics cho biết vấn đề xảy ra ở đâu theo xu hướng; tracing giúp điều tra một request cụ thể qua nhiều service. Khi tracing được bật, mỗi trace có một trace ID và gồm nhiều span. Span thể hiện một thao tác hoặc một chặng xử lý, chẳng hạn nhận request tại Gateway, gọi service catalog và truy cập cơ sở dữ liệu.

Với Spring Boot 3, hệ thống thường tích hợp Micrometer Tracing cùng bridge cho OpenTelemetry và exporter OTLP. Dependency cụ thể phải khớp với phiên bản Spring Boot đang dùng. Ví dụ cấu hình lấy mẫu và endpoint collector:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Giá trị `0.1` minh họa lấy mẫu khoảng 10% request; chọn tỷ lệ phù hợp với lưu lượng, yêu cầu điều tra và chi phí lưu trữ. Trong giai đoạn xử lý sự cố có thể cần tăng sampling tạm thời theo quy trình vận hành, nhưng cần theo dõi tải của collector và backend tracing. Tên thuộc tính exporter và cách cấu hình có thể khác giữa các phiên bản Spring Boot; kiểm tra tài liệu đúng phiên bản và xác nhận trace thực sự đến collector.

Các hệ thống dùng W3C Trace Context thường truyền thông tin tương quan qua header `traceparent` và có thể có `tracestate`. Khi các service được instrument đúng cách, trace có thể tiếp tục từ Gateway sang downstream. Hãy kiểm tra trace ID trong log và giao diện tracing; log có trace ID nhưng trace không xuất hiện có thể do sampling, exporter, network hoặc cấu hình propagation.

Khi mở một trace chậm, hãy xem:

1. Span nào bắt đầu và kết thúc muộn nhất; đây thường là nơi giữ phần lớn thời gian.
2. Khoảng thời gian giữa các span; khoảng trống có thể phản ánh chờ connection, retry, queue hoặc xử lý chưa được instrument.
3. Span có trạng thái lỗi, exception hoặc status code bất thường.
4. Các lần gọi lặp lại đến cùng upstream; đây có thể là retry hoặc fan-out.
5. Trace có đi qua đúng service và instance dự kiến hay không.

Không tự tạo trace ID từ dữ liệu client tùy ý rồi coi đó là bằng chứng tin cậy. Hãy để thư viện tracing quản lý context; nếu hệ thống nhận header từ bên ngoài, cân nhắc ranh giới tin cậy và chính sách làm sạch header tại ingress. Không đưa dữ liệu cá nhân hoặc bí mật vào baggage vì baggage có thể được truyền sang nhiều service.

## 6. Ghép bốn nguồn để phân loại sự cố

Bảng sau là điểm bắt đầu khi điều tra. Mã HTTP chỉ là dấu hiệu; cần xác nhận bằng route ID, log và trace trước khi kết luận.

| Triệu chứng | Bằng chứng nên kiểm tra | Hướng điều tra |
|---|---|---|
| Gateway trả 404 | Route list, log có `routeId=unmatched`, method và path | Predicate không khớp, sai path sau rewrite, sai method hoặc route chưa được nạp. Nếu có route ID, kiểm tra xem 404 có đến từ upstream hay không |
| Gateway trả 401/403 | Log của filter bảo mật, status theo route, trace nếu có | Token thiếu/hết hạn, quyền không phù hợp, hoặc filter xác thực/phân quyền từ chối request |
| Gateway trả 429 | Metrics theo status và route, cấu hình rate limiter, log key được dùng để giới hạn | Kiểm tra quota, replenish rate, burst capacity và khóa phân vùng; xác nhận request có thực sự vượt giới hạn |
| Gateway trả 502/503 | Health, route URI, service discovery, log lỗi kết nối và trace | Upstream không tồn tại, không có instance khả dụng, DNS/connect lỗi hoặc upstream đóng kết nối |
| Gateway trả 504 hoặc latency tăng | p95/p99 theo route, timeout log, trace của request chậm | Upstream chậm, timeout không phù hợp, connection pool cạn hoặc retry làm tăng tổng thời gian |
| Chỉ một route tăng lỗi | Metrics có tag `routeId`, route detail, trace của một request lỗi | Cấu hình route/filter riêng, một upstream hoặc một nhóm instance gặp vấn đề |
| Tất cả route cùng chậm | CPU, memory, event loop, connection pool, request rate và latency tổng thể | Gateway quá tải, downstream dùng chung bị nghẽn, network hoặc hạ tầng nền có vấn đề |

Một quy trình thực hành có thể đi theo thứ tự sau:

1. **Chốt mẫu request:** ghi thời điểm, method, path đã che dữ liệu, route dự kiến, status, duration và trace/request ID.
2. **Kiểm tra runtime:** gọi health endpoint, sau đó xem route list và route detail để xác nhận cấu hình đang chạy.
3. **Tìm log:** tìm theo request ID hoặc trace ID trong khoảng thời gian đã chốt; đọc access log và application log để xác định request đã vào Gateway, chọn route và kết thúc ở đâu.
4. **So sánh metrics:** lọc theo route ID và cửa sổ thời gian; so request rate, tỷ lệ lỗi và p95/p99 với baseline trước sự cố.
5. **Mở trace:** xem span Gateway và các downstream span để tìm chặng chiếm thời gian hoặc phát sinh lỗi.
6. **Kiểm chứng giả thuyết:** thay đổi một yếu tố theo quy trình vận hành, gửi lại request tương đương và so sánh log, metrics, trace trước/sau.

### Ví dụ: request đến route catalog bị chậm

Giả sử client báo `GET /api/catalog/items` đôi lúc mất 4 giây. Có thể điều tra như sau:

- Actuator xác nhận route `catalog` đang được nạp và URI đích trỏ đến service catalog.
- Metrics cho thấy p95 của route `catalog` tăng, trong khi các route khác vẫn gần baseline. Điều này thu hẹp phạm vi vào route hoặc upstream của nó.
- Access log cho thấy request cụ thể trả 200 sau khoảng 4 giây, kèm request ID. Không có bằng chứng Gateway từ chối request.
- Tìm trace tương ứng cho thấy span gọi catalog chiếm gần hết thời gian; span tại Gateway chỉ có phần nhỏ. Khi đó nên kiểm tra service catalog, các lần gọi phụ thuộc và connection pool của client thay vì chỉnh predicate của route.

Nếu trace cho thấy thời gian chủ yếu nằm trước khi có span upstream, hãy xem filter chain, rate limiter, retry, connection acquisition và cấu hình timeout tại Gateway. Kết luận phải dựa trên thời gian của span và log tương ứng, không suy ra chỉ từ tổng latency.

## 7. Các nguyên tắc vận hành khi thu thập bằng chứng

- **Bảo vệ management endpoint:** chỉ cho phép mạng vận hành truy cập, bật xác thực và expose tối thiểu endpoint cần thiết. Không công khai route detail hoặc endpoint có thao tác thay đổi runtime.
- **Giảm dữ liệu nhạy cảm trong log:** không ghi body, token, cookie, mật khẩu hoặc header xác thực. Che path và query có thể chứa thông tin cá nhân.
- **Giữ metric cardinality thấp:** không dùng ID theo từng request hoặc người dùng làm tag. Dùng route ID và nhóm status có số lượng giới hạn.
- **Đồng bộ thời gian:** cấu hình NTP cho các node và lưu timestamp có timezone. Sai lệch đồng hồ làm việc ghép log và trace khó chính xác.
- **Chọn sampling có chủ đích:** sampling thấp giảm chi phí nhưng có thể bỏ qua request lỗi hiếm; cần có cách tăng quan sát trong sự cố và giới hạn thời gian áp dụng.
- **Kiểm tra dữ liệu đã đến backend:** endpoint trả metrics hoặc cấu hình tracing chưa đảm bảo collector nhận được dữ liệu. Xác nhận scrape target, exporter log và trace trong giao diện quan sát.
- **Giữ một khóa tương quan nhất quán:** ưu tiên trace ID cho luồng phân tán; dùng request ID cho log tại một dịch vụ. Ghi rõ hai ID này khác nhau nếu hệ thống sử dụng cả hai.

## 8. Bài tập thực hành

1. Bật Actuator và chỉ expose `health`, `metrics` cùng endpoint Gateway cần đọc trong môi trường phát triển. Gọi route list và ghi lại route ID, URI đích.
2. Bật Reactor Netty access log. Gửi một request hợp lệ và một request không khớp route; so sánh status và thông tin có trong access log.
3. Thêm log có route ID, status, duration và request ID. Gửi nhiều request đến hai route khác nhau rồi lọc log theo route ID.
4. Đọc meter `spring.cloud.gateway.requests`, lọc theo một route ID và so sánh count/status sau khi gửi request thành công và request lỗi.
5. Bật tracing với sampling phù hợp trong môi trường phát triển. Gửi request qua Gateway đến một service đã instrument, rồi xác nhận trace có các span của hai thành phần.
6. Tạo một tình huống upstream phản hồi chậm trong môi trường thử nghiệm. Dùng metrics để phát hiện route bị ảnh hưởng, log để tìm request cụ thể và trace để xác định span gây chậm.

Sau bài tập, hãy thử giải thích một sự cố bằng ba bằng chứng có thể kiểm tra lại: route runtime từ Actuator, một request cụ thể từ log và một xu hướng hoặc trace tương ứng. Nếu ba nguồn không cùng chỉ về một nguyên nhân, hãy ghi rõ điểm chưa khớp và thu thập thêm dữ liệu trước khi thay đổi cấu hình.
