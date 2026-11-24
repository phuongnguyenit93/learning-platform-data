# Công bố Prometheus text hoặc OpenMetrics theo khả năng của client

Micrometer có thể xuất metrics qua Prometheus registry dưới dạng Prometheus text exposition hoặc OpenMetrics. Hai định dạng có chung mục tiêu biểu diễn metric name, type, label và sample, nhưng khác nhau về content type, quy tắc exposition và khả năng biểu diễn metadata. Ứng dụng cần chọn định dạng mà cả registry/client lẫn hệ thống scrape đều hỗ trợ.

Trong môi trường Spring Boot, endpoint Actuator thường đảm nhiệm phần lớn công việc serialize và thương lượng định dạng. Với endpoint tự xây dựng, ứng dụng phải trả đúng Content-Type tương ứng với payload và chỉ chọn định dạng mà client có thể tạo. Không nên đổi header để gắn nhãn một payload thành OpenMetrics nếu nội dung thực tế vẫn là Prometheus text.

## 1. Exposition format là gì?

Prometheus không đọc trực tiếp object MeterRegistry của Micrometer. Prometheus scrape một HTTP endpoint và phân tích nội dung metrics được xuất ra theo một exposition format đã thỏa thuận.

Luồng dữ liệu cơ bản:

~~~text
Counter / Gauge / Timer / DistributionSummary
                    |
                    v
              MeterRegistry
                    |
                    v
          PrometheusMeterRegistry
                    |
                    v
          Serialize exposition format
                    |
             HTTP response
                    |
                    v
          Prometheus scrape target
                    |
                    v
          Time series database
                    |
                    v
          PromQL / dashboard / alert
~~~

Prometheus registry chuyển meter và tag của Micrometer thành metric name, label, metadata và sample. Endpoint HTTP cung cấp payload cho Prometheus theo chu kỳ scrape.

Exposition format là hợp đồng giữa phía xuất metrics và phía đọc metrics. Hợp đồng này gồm:

- Cấu trúc dòng metadata như HELP và TYPE.
- Tên metric và tên label.
- Giá trị sample và timestamp nếu có.
- Cách biểu diễn histogram, summary và exemplar.
- Content-Type trong HTTP response.
- Quy tắc kết thúc payload của định dạng được chọn.

Prometheus text và OpenMetrics đều có thể biểu diễn các metric phổ biến, nhưng không thể giả định mọi client hoặc mọi phiên bản đều hỗ trợ cả hai.

## 2. Prometheus text exposition

Prometheus text exposition là định dạng văn bản truyền thống được dùng rộng rãi. Phiên bản phổ biến là text format 0.0.4, thường được nhận diện bằng content type:

~~~text
text/plain;version=0.0.4;charset=utf-8
~~~

Một payload minh họa:

~~~text
# HELP orders_created_total Total number of created orders
# TYPE orders_created_total counter
orders_created_total{channel="web"} 42
orders_created_total{channel="mobile"} 17
~~~

Các thành phần:

- HELP mô tả ý nghĩa metric.
- TYPE khai báo kiểu metric, ví dụ counter, gauge hoặc histogram.
- Sample chứa tên metric, label và giá trị.
- Mỗi tổ hợp label tạo một chuỗi dữ liệu riêng trong backend.

Histogram có thể được xuất thành nhiều sample theo bucket, sum và count:

~~~text
# HELP api_request_duration_seconds Request duration
# TYPE api_request_duration_seconds histogram
api_request_duration_seconds_bucket{le="0.1"} 80
api_request_duration_seconds_bucket{le="0.5"} 96
api_request_duration_seconds_bucket{le="+Inf"} 100
api_request_duration_seconds_sum 18.2
api_request_duration_seconds_count 100
~~~

Ví dụ chỉ minh họa cấu trúc exposition. Tên metric thực tế phụ thuộc vào tên meter, base unit và quy tắc chuẩn hóa của Prometheus registry.

Prometheus text format dễ kiểm tra bằng curl hoặc trình duyệt, được hỗ trợ rộng rãi và thường là lựa chọn tương thích cho hệ thống cũ. Nếu client chỉ hỗ trợ text 0.0.4, endpoint nên trả đúng định dạng này.

## 3. OpenMetrics

OpenMetrics là một định dạng exposition có đặc tả riêng, phát triển từ mô hình metrics của Prometheus để tăng khả năng tương tác và biểu diễn metadata. Phiên bản phổ biến hiện nay là OpenMetrics 1.0.0, thường dùng content type:

~~~text
application/openmetrics-text;version=1.0.0;charset=utf-8
~~~

Một payload OpenMetrics text có thể trông như sau:

~~~text
# HELP orders_created_total Total number of created orders
# TYPE orders_created_total counter
orders_created_total{channel="web"} 42
# EOF
~~~

Điểm dễ nhận biết là marker kết thúc # EOF. OpenMetrics có các quy tắc metadata và biểu diễn bổ sung, ví dụ unit, metric family và exemplar khi client cùng backend hỗ trợ.

OpenMetrics hữu ích khi hệ sinh thái scrape và client đã hỗ trợ giao thức này, đặc biệt khi cần các khả năng mở rộng của đặc tả. Tuy nhiên, việc một server có thể trả OpenMetrics không đồng nghĩa mọi Prometheus server, proxy hoặc công cụ trung gian trong đường truyền đều có thể parse nó.

Không tự thêm # EOF vào payload Prometheus text để biến nó thành OpenMetrics. Serializer phải tạo đúng cấu trúc, metadata và content type của định dạng đã chọn.

## 4. So sánh Prometheus text và OpenMetrics

| Tiêu chí | Prometheus text 0.0.4 | OpenMetrics 1.0.0 |
|---|---|---|
| Content-Type | text/plain; version=0.0.4 | application/openmetrics-text; version=1.0.0 |
| Khả năng tương thích | Rộng, phù hợp nhiều client cũ | Cần client và scraper hỗ trợ |
| Kết thúc payload | Không yêu cầu marker EOF | Có marker # EOF |
| Metadata | HELP, TYPE và sample theo text format | Có quy tắc metadata mở rộng hơn |
| Exemplar | Khả năng biểu diễn hạn chế theo format cũ | Có thể biểu diễn exemplar theo đặc tả |
| Lựa chọn | Tương thích và đơn giản | Hệ sinh thái hỗ trợ OpenMetrics |

Lựa chọn format cần dựa trên khả năng chung của các thành phần:

1. Micrometer Prometheus registry có hỗ trợ format hay không.
2. Prometheus Java client được registry sử dụng có serializer tương ứng hay không.
3. Endpoint hoặc framework có thể chọn format theo request hay không.
4. Prometheus server có chấp nhận format đó trong cấu hình scrape hay không.
5. Proxy hoặc gateway ở giữa có giữ nguyên Content-Type và body hay không.

Nếu một mắt xích không hỗ trợ OpenMetrics, hãy dùng Prometheus text để bảo đảm scrape ổn định.

## 5. Khả năng phụ thuộc Prometheus client và Micrometer registry

Micrometer cung cấp registry tích hợp với các thế hệ Prometheus Java client khác nhau. Registry mới dựa trên Prometheus Java client 1.x và registry tương thích với simpleclient cũ có khả năng, API và package khác nhau.

Trong các phiên bản Micrometer có hỗ trợ cả hai lựa chọn, artifact thường gặp gồm:

- micrometer-registry-prometheus: registry dựa trên Prometheus Java client mới.
- micrometer-registry-prometheus-simpleclient: registry tương thích với Prometheus simpleclient cũ.

Tên artifact và package có thể thay đổi theo phiên bản Micrometer/Spring Boot. Hãy dùng dependency management của Spring Boot hoặc BOM tương ứng, kiểm tra tài liệu đúng phiên bản và tránh kéo đồng thời hai implementation registry nếu không có chủ đích.

Ví dụ dependency với Spring Boot:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Spring Boot quản lý phiên bản tương thích của Micrometer thông qua dependency management. Nếu dự án dùng registry simpleclient cũ, hãy chọn artifact tương ứng với phiên bản Micrometer đang dùng thay vì tự thêm một bộ client không đồng bộ.

Không suy ra khả năng OpenMetrics chỉ từ tên endpoint /actuator/prometheus. Cần kiểm tra registry implementation, API scrape, phiên bản framework và phản hồi thực tế.

## 6. Xuất Prometheus text bằng PrometheusMeterRegistry

Trong ứng dụng Micrometer thuần, có thể gọi phương thức scrape() của PrometheusMeterRegistry để lấy payload mặc định:

~~~java
String body = prometheusMeterRegistry.scrape();
~~~

Phương thức scrape() mặc định thường trả Prometheus text format. Đây là lựa chọn tương thích khi endpoint không cần thương lượng format hoặc client registry chỉ hỗ trợ text.

Khi registry hỗ trợ OpenMetrics, một số phiên bản cung cấp overload nhận content type để chọn định dạng:

~~~java
String contentType =
    "application/openmetrics-text;version=1.0.0;charset=utf-8";

String body = prometheusMeterRegistry.scrape(contentType);
~~~

API cụ thể và content type được hỗ trợ phụ thuộc phiên bản registry. Hãy xác minh overload trong phiên bản Micrometer đang sử dụng. Nếu registry không hỗ trợ content type được yêu cầu, không được giả định rằng nó sẽ tự chuyển đổi payload đúng chuẩn.

### Tạo HTTP endpoint thủ công

Nếu tự triển khai HTTP handler, response cần giữ content type nhất quán với body:

~~~java
String contentType = "text/plain;version=0.0.4;charset=utf-8";
String body = prometheusMeterRegistry.scrape(contentType);

byte[] payload = body.getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders().set("Content-Type", contentType);
exchange.sendResponseHeaders(200, payload.length);

try (OutputStream output = exchange.getResponseBody()) {
    output.write(payload);
}
~~~

Ví dụ trên chọn cố định Prometheus text. Cần import StandardCharsets và OutputStream theo API HTTP server đang dùng. Nếu muốn hỗ trợ OpenMetrics, endpoint phải chọn content type phù hợp với Accept header, kiểm tra registry hỗ trợ định dạng đó, gọi serializer tương ứng và trả cùng Content-Type.

Không trả body OpenMetrics với header text/plain hoặc ngược lại. Scraper có thể chọn parser dựa trên Content-Type và từ chối payload không khớp.

## 7. Thương lượng định dạng qua Accept header

Trong HTTP content negotiation, client gửi Accept để mô tả các định dạng mà nó có thể đọc. Server chọn một định dạng được cả hai phía hỗ trợ và trả Content-Type tương ứng.

Ví dụ request:

~~~http
GET /actuator/prometheus HTTP/1.1
Host: orders-service:8080
Accept: application/openmetrics-text;version=1.0.0;charset=utf-8, text/plain;version=0.0.4;charset=utf-8
~~~

Nếu registry và endpoint hỗ trợ OpenMetrics, server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/openmetrics-text;version=1.0.0;charset=utf-8
~~~

Nếu chỉ hỗ trợ Prometheus text, server nên chọn text format nếu đó là định dạng chung được chấp nhận. Nếu không có định dạng nào tương thích, endpoint cần xử lý theo hợp đồng HTTP đã thiết kế, thay vì trả một body không thể parse.

Khi triển khai content negotiation:

1. Đọc Accept header của request.
2. Xác định danh sách format mà client yêu cầu và thứ tự ưu tiên nếu có.
3. Giao với danh sách format mà registry thực sự hỗ trợ.
4. Chọn format chung phù hợp.
5. Serialize body bằng đúng serializer.
6. Trả Content-Type khớp chính xác với format đã chọn.

Không tự viết parser Accept đơn giản chỉ tìm chuỗi "openmetrics" nếu cần hỗ trợ q-value, nhiều media type hoặc wildcard. Dùng cơ chế content negotiation của framework hoặc thư viện HTTP.

### Prometheus scrape protocol

Prometheus có thể thương lượng giao thức scrape dựa trên cấu hình và Accept header mà nó gửi. Tập giao thức được hỗ trợ và thứ tự ưu tiên phụ thuộc phiên bản Prometheus.

Do đó, cần kiểm tra cấu hình scrape protocol của Prometheus server cùng khả năng của exporter. Nếu muốn chuyển toàn bộ target sang OpenMetrics, hãy triển khai thử trên một target, kiểm tra Content-Type và log scrape trước khi áp dụng rộng.

## 8. Tích hợp endpoint Prometheus với Spring Boot Actuator

Với Spring Boot Actuator và Prometheus registry, endpoint thường được cung cấp tại /actuator/prometheus.

Cấu hình expose endpoint:

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.metrics.tags.application=orders-service
~~~

Prometheus có thể scrape endpoint qua cấu hình job:

~~~yaml
scrape_configs:
  - job_name: "orders-service"
    metrics_path: "/actuator/prometheus"
    scrape_interval: 15s
    static_configs:
      - targets:
          - "orders-service:8080"
~~~

Actuator endpoint giúp ứng dụng không phải tự viết HTTP serializer và thường tích hợp content negotiation theo khả năng của registry và phiên bản Spring Boot. Tuy vậy, hãy kiểm tra phản hồi thực tế vì các phiên bản framework và registry có thể khác nhau.

Nếu muốn hỗ trợ cả hai format, đừng giới hạn endpoint bằng một cấu hình produces chỉ cho text/plain ở controller hoặc reverse proxy. Cấu hình đó có thể ngăn OpenMetrics negotiation ngay cả khi registry hỗ trợ.

Endpoint metrics có thể tiết lộ thông tin về cấu trúc ứng dụng, tên dịch vụ, route, trạng thái dependency và mức tải. Chỉ expose trong mạng giám sát hoặc bảo vệ bằng cơ chế truy cập phù hợp. Không đưa thông tin bí mật, token hoặc dữ liệu cá nhân vào label.

## 9. Quy tắc đặt tên và label khi serialize

Prometheus registry chuyển tên meter và tag của Micrometer sang quy ước metric name và label của Prometheus. Tên có dấu chấm thường được chuẩn hóa thành dấu gạch dưới; đơn vị có thể được thể hiện trong hậu tố tên metric.

Ví dụ minh họa:

| Micrometer | Dạng Prometheus thường gặp |
|---|---|
| orders.created | orders_created_total |
| http.server.requests (Timer) | http_server_requests_seconds |
| process.memory.usage (bytes) | process_memory_usage_bytes |
| Tag channel=web | Label channel="web" |

Tên xuất thực tế phụ thuộc loại meter, base unit, registry và phiên bản. Luôn kiểm tra payload đã scrape trước khi viết PromQL hoặc dashboard.

Các nguyên tắc quan trọng:

- Giữ tên metric ổn định và mô tả một đại lượng rõ ràng.
- Dùng đơn vị cơ sở nhất quán, ví dụ seconds và bytes.
- Tag phải có tập giá trị hữu hạn.
- Không đưa user ID, request ID, order ID hoặc URL đầy đủ vào label.
- Tránh dùng các label key dành riêng cho cấu trúc histogram hoặc summary.
- Để serializer xử lý escaping cho HELP, label và sample.

Không tự nối chuỗi metrics bằng tay. Serializer của registry chịu trách nhiệm chuẩn hóa tên, escape label, xuất HELP/TYPE và cấu trúc histogram theo format.

## 10. Kiểm tra payload bằng HTTP và công cụ scrape

Có thể kiểm tra endpoint trực tiếp bằng curl:

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Quan sát:

- HTTP status phải thành công.
- Content-Type phải là Prometheus text hoặc OpenMetrics tương ứng.
- Body có HELP, TYPE và sample hợp lệ.
- Histogram có bucket, sum và count nếu đã bật histogram.
- OpenMetrics text có marker # EOF.
- Không có HTML trang đăng nhập, trang lỗi hoặc JSON thay cho exposition.

Thử yêu cầu OpenMetrics nếu endpoint hỗ trợ:

~~~bash
curl -i \
  -H "Accept: application/openmetrics-text;version=1.0.0;charset=utf-8" \
  http://localhost:8080/actuator/prometheus
~~~

Nếu server vẫn trả Prometheus text, hãy xác minh đó là fallback được thiết kế hay endpoint chưa hỗ trợ OpenMetrics. Không kết luận chỉ từ Accept header; kiểm tra cả Content-Type và payload.

Nếu Prometheus báo lỗi parse, hãy so sánh ba yếu tố:

1. Format mà Prometheus yêu cầu.
2. Content-Type mà endpoint trả về.
3. Cấu trúc payload thực tế.

Ba yếu tố này phải thống nhất. Nếu proxy đổi Content-Type hoặc biến đổi body, hãy kiểm tra response ở cả phía exporter và phía Prometheus.

## 11. Kiểm thử format trong ứng dụng

Có thể dùng PrometheusMeterRegistry để kiểm tra payload được tạo ra theo format mà registry hỗ trợ.

Các đoạn dưới đây giả sử test đã tạo một PrometheusMeterRegistry dùng implementation và phiên bản client mà ứng dụng triển khai; cách khởi tạo registry khác nhau giữa các thế hệ client.

Ví dụ kiểm tra Prometheus text:

~~~java
import io.micrometer.core.instrument.Counter;

Counter.builder("orders.created")
    .description("Total number of created orders")
    .tag("channel", "web")
    .register(prometheusMeterRegistry)
    .increment();

String text = prometheusMeterRegistry.scrape();

assertTrue(text.contains("# HELP"));
assertTrue(text.contains("# TYPE"));
assertTrue(text.contains("orders_created"));
~~~

Với OpenMetrics, nếu phiên bản registry hỗ trợ overload content type:

~~~java
String openMetrics = prometheusMeterRegistry.scrape(
    "application/openmetrics-text;version=1.0.0;charset=utf-8"
);

assertTrue(openMetrics.contains("# EOF"));
~~~

Các assertion chỉ minh họa kiểm tra cấu trúc cơ bản. Trong test thật, nên xác minh metric name, type, label, sample value và content type ở HTTP layer. Đối với OpenMetrics, cần kiểm tra serializer tạo payload đúng chuẩn; chỉ thấy chuỗi # EOF không đủ để chứng minh mọi metadata đều hợp lệ.

Nên có integration test cho endpoint:

- Gửi Accept Prometheus text và xác minh Content-Type/body.
- Gửi Accept OpenMetrics khi client hỗ trợ và xác minh Content-Type/body.
- Gửi Accept không được hỗ trợ và xác minh hành vi fallback hoặc lỗi.
- Xác minh proxy/gateway không thay đổi body hoặc Content-Type.
- Scrape endpoint bằng phiên bản Prometheus mục tiêu trong môi trường kiểm thử.

## 12. Các lỗi thường gặp

- **Gắn Content-Type OpenMetrics cho body Prometheus text:** parser có thể từ chối payload.
- **Giả định mọi Prometheus client đều hỗ trợ OpenMetrics:** khả năng phụ thuộc registry và phiên bản client.
- **Chỉ đổi Accept header mà không đổi serializer:** body vẫn có thể là format cũ.
- **Tự thêm # EOF:** không biến text format thành OpenMetrics hợp lệ.
- **Giới hạn endpoint produces chỉ là text/plain:** có thể vô hiệu hóa content negotiation.
- **Dùng đồng thời registry/client không tương thích:** gây xung đột dependency hoặc khác biệt API.
- **Không kiểm tra tên metric đã chuẩn hóa:** PromQL tham chiếu sai series.
- **Tự serialize metrics bằng chuỗi:** dễ sai escaping, HELP/TYPE, histogram và label.
- **Để proxy đổi Content-Type hoặc nén sai:** Prometheus không parse được response.
- **Expose endpoint không kiểm soát:** metrics có thể tiết lộ thông tin nội bộ.

## 13. Checklist triển khai

- [ ] Xác định Prometheus registry và phiên bản Java client đang sử dụng.
- [ ] Xác minh client hỗ trợ Prometheus text, OpenMetrics hay cả hai.
- [ ] Chọn content type tương ứng với serializer.
- [ ] Nếu thương lượng định dạng, xử lý Accept theo đúng quy tắc HTTP.
- [ ] Trả Content-Type khớp với body.
- [ ] Không tự sửa payload bằng cách thêm marker hoặc đổi header.
- [ ] Dùng Spring Boot Actuator endpoint khi phù hợp.
- [ ] Kiểm tra dependency và tránh trộn registry implementation không chủ đích.
- [ ] Kiểm tra tên metric, label, unit, HELP/TYPE và histogram.
- [ ] Kiểm thử cả endpoint HTTP và Prometheus scraper.
- [ ] Kiểm tra proxy/gateway giữ nguyên format.
- [ ] Bảo vệ endpoint và kiểm soát dữ liệu label.

Prometheus text là lựa chọn tương thích rộng, còn OpenMetrics cung cấp một đặc tả exposition mở rộng khi registry và scraper hỗ trợ. Hãy chọn định dạng dựa trên khả năng chung của các thành phần, thương lượng qua Accept khi cần và luôn trả Content-Type khớp payload. Kiểm tra trực tiếp response cùng phiên bản Prometheus triển khai sẽ giúp phát hiện lỗi giao thức trước khi đưa endpoint vào vận hành.

