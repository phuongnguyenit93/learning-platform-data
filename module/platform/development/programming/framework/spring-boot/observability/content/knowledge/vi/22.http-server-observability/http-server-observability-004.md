# URI template

Trong chương **HTTP server observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, URI template là mẫu đường dẫn mà framework dùng để mô tả endpoint đã xử lý request, trước khi thay các biến path bằng giá trị thực tế. Ví dụ, endpoint /orders/{orderId} có thể nhận các request /orders/1001 và /orders/1002. Cả hai request thuộc cùng một route template: /orders/{orderId}.

Với Spring Boot, HTTP server Observation thường tạo meter có tên http.server.requests. Tag uri được ghi dưới dạng URI template nếu framework xác định được route pattern. Đây là một lựa chọn quan trọng cho observability: metric có thể nhóm request theo endpoint mà không tạo một time series mới cho từng ID. Nếu thay template bằng raw path, cardinality có thể tăng theo số người dùng, đơn hàng hoặc resource được truy cập, khiến metrics backend tốn bộ nhớ và khó truy vấn.

Bài này tập trung vào URI template trong HTTP server observability bằng Spring Boot, Micrometer Observation và distributed tracing. Bạn sẽ hiểu route pattern được lấy ở đâu, tag uri khác request URI thế nào, cách kiểm tra MVC/WebFlux, xử lý route không khớp và tùy chỉnh observation convention mà vẫn giữ cardinality ổn định.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích URI template và phân biệt nó với raw request URI, URL và query string.
2. Hiểu vai trò của tag uri trong http.server.requests.
3. Giải thích vì sao URI template giúp kiểm soát metric cardinality.
4. Theo dõi cách Spring MVC và Spring WebFlux cung cấp route pattern cho Observation.
5. Phân biệt route đã được match với request chưa được resolve vào một handler.
6. Kiểm tra URI template trong Actuator metrics endpoint và backend metrics.
7. Tùy chỉnh ServerRequestObservationConvention khi có nhu cầu bổ sung hoặc thay đổi tags.
8. Tránh đưa path variables, query parameters và identifiers vào low-cardinality metrics.
9. Kết hợp URI template với logs, spans và trace correlation để điều tra một request cụ thể.
10. Viết kiểm thử cho route templates, unmatched routes và cardinality.

## 2. URI template là gì?

URI template biểu diễn cấu trúc của path bằng các biến thay vì giá trị cụ thể.

Ví dụ:

| Request thực tế | URI template |
| --- | --- |
| /orders/1001 | /orders/{orderId} |
| /orders/1002 | /orders/{orderId} |
| /customers/c-918/profile | /customers/{customerId}/profile |
| /products/sku-77/reviews/5 | /products/{productId}/reviews/{reviewId} |

Hai hoặc nhiều request có path khác nhau có thể thuộc cùng một route template. Điều này giúp metrics trả lời câu hỏi như "endpoint nào đang chậm?" thay vì tạo một nhóm riêng cho từng order ID.

### Phân biệt các khái niệm

| Khái niệm | Ví dụ | Mục đích |
| --- | --- | --- |
| **Raw request URI/path** | /orders/1001 | Đường dẫn thực tế request gửi tới server. |
| **URI template / route pattern** | /orders/{orderId} | Mẫu route do framework/router xác định. |
| **Full URL** | https://api.example.com/orders/1001?expand=items | Scheme, host, path và query string. |
| **Query string** | ?expand=items | Tham số truy vấn sau dấu ?. |
| **Path variable** | orderId=1001 | Giá trị thực tế được gắn vào biến route. |
| **HTTP route** | Handler xử lý /orders/{orderId} | Endpoint logic mà request match. |

URI template không phải URL đầy đủ. Nó thường chỉ mô tả route path và không chứa host, query string hoặc giá trị path variables.

### Vì sao template cần xuất hiện trong metrics?

Giả sử hệ thống có 500.000 orders và mỗi order được truy cập ít nhất một lần. Nếu tag uri giữ raw path, backend có thể nhìn thấy hàng trăm nghìn giá trị khác nhau:

~~~text
uri=/orders/1001
uri=/orders/1002
uri=/orders/1003
...
~~~

Nếu dùng route template, các request được gom vào một tag value:

~~~text
uri=/orders/{orderId}
~~~

Với template, số lượng route thường gần với số endpoint được khai báo và được kiểm soát hơn. Nó không bảo đảm cardinality luôn nhỏ: ứng dụng vẫn có thể tạo route động hoặc có hàng nghìn route templates. Nhưng template loại bỏ một nguồn cardinality lớn đến từ giá trị của path variables.

## 3. URI template trong http.server.requests

Spring Boot auto-configures HTTP server instrumentation cho những stack được hỗ trợ như Spring MVC và Spring WebFlux. Observation ở tầng framework có tên http.server.requests. Khi Observation được nối với Micrometer metrics, nó tạo timer cho thời gian xử lý request; khi tracing được bật, cùng Observation có thể tạo span.

Một số tag mặc định thường gặp gồm:

| Tag | Ý nghĩa |
| --- | --- |
| method | HTTP method như GET, POST, PUT, DELETE. |
| uri | URI template trước khi thay biến, nếu framework xác định được. |
| status | HTTP response status như 200, 404 hoặc 500. |
| outcome | Nhóm kết quả dựa trên response status. |
| exception | Tên class exception nếu có exception được ghi nhận. |

Tên tag hoặc chi tiết của stack cụ thể có thể khác theo Spring Boot/Spring Framework version và convention được cấu hình. Hãy xác minh meter thực tế trong ứng dụng. Tài liệu Spring Boot mô tả URI tag là template trước khi substitution, ví dụ /api/person/{id}. [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

### Observation tạo cả metrics và trace

~~~mermaid
flowchart TD
    Request["HTTP request: GET /orders/1001"]
    Router["Spring MVC / WebFlux route matching"]
    Context["ServerRequestObservationContext"]
    Convention["ServerRequestObservationConvention"]
    Observation["http.server.requests Observation"]
    Metrics["Micrometer Timer + tags"]
    Trace["Tracing handler tạo server span"]
    Request --> Router --> Context --> Convention --> Observation
    Observation --> Metrics
    Observation --> Trace
~~~

URI template được dùng trong Observation convention để tạo low-cardinality key-value. Với metrics, template là cách nhóm endpoint. Với tracing, span có thể mang thêm các thuộc tính chi tiết khác theo semantic conventions và cấu hình instrumentation. Không nên giả định tất cả các tags của meter đều được sao chép nguyên trạng thành span attributes.

## 4. Spring MVC lấy URI template từ đâu?

Trong ứng dụng Servlet/Spring MVC, DispatcherServlet phối hợp với HandlerMapping để tìm handler phù hợp với request. Khi một controller mapping được match, framework có thể xác định pattern của route.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getOrder(@PathVariable String orderId) {
        return orderService.find(orderId);
    }
}
~~~

Các request sau:

~~~text
GET /orders/1001
GET /orders/1002
GET /orders/9f2a
~~~

đều match cùng mapping /orders/{orderId}. Server request Observation có thể dùng route pattern này làm URI low-cardinality tag.

### Filter và observation lifecycle

Với Servlet applications, Spring Framework dùng ServerHttpObservationFilter để tạo HTTP server observations. Filter cần nằm đúng trong servlet filter chain và hoạt động cùng framework mapping. Spring Boot auto-configuration thường thiết lập instrumentation cho stack được hỗ trợ; nếu tự cấu hình filter hoặc thay thế web infrastructure, cần xác nhận filter observation không bị bỏ qua hoặc đăng ký trùng.

Đối với exception, observation thường chỉ ghi nhận là error khi exception chưa được framework xử lý và bubble lên filter. Exception được @ExceptionHandler hoặc cơ chế ProblemDetail xử lý có thể không tự động trở thành error tag. Nếu cần ghi nhận handled exception, ứng dụng cần đặt error vào observation context theo hướng dẫn Spring Framework phù hợp với version. Điều này quan trọng khi đối chiếu URI template và status/outcome.

## 5. Spring WebFlux lấy URI template từ đâu?

Trong WebFlux, framework có thể tạo HTTP server observations cho annotated controllers và functional endpoints.

Ví dụ annotated controller:

~~~java
@RestController
@RequestMapping("/catalog")
class CatalogController {

    @GetMapping("/{productId}")
    Mono<ProductResponse> find(@PathVariable String productId) {
        return productService.find(productId);
    }
}
~~~

Ví dụ functional route:

~~~java
@Bean
RouterFunction<ServerResponse> catalogRoutes(CatalogHandler handler) {
    return RouterFunctions.route()
            .GET("/catalog/{productId}", handler::find)
            .build();
}
~~~

Cả hai kiểu route có thể cung cấp pattern để Observation mô tả endpoint. Khi dùng functional routing, kiểm tra version và cách handler mapping cung cấp matched pattern cho Observation.

### Giữ context trong reactive pipeline

Reactive pipeline có thể chạy qua nhiều thread. URI template được xác định trong request handling context; nếu code tự tạo Observation hoặc ghi log ngoài context propagation đúng cách, correlation có thể mất dù route match bình thường.

Không tự lấy raw path từ ServerRequest rồi thêm vào low-cardinality tags để thay thế route template. Nếu cần log chính xác path đã được bảo vệ, hãy cân nhắc ghi vào log event theo policy riêng, với retention/access phù hợp và không dùng nó làm metric label.

## 6. URI template và cardinality

Cardinality là số lượng giá trị khác nhau của một dimension/tag. Mỗi tag value có thể tạo thêm time series trong backend metrics. Nếu tag uri chứa raw path, mỗi identifier khác nhau có thể tạo một series mới.

Ví dụ một route có 200.000 order IDs:

| Cách tag | Số giá trị uri có thể phát sinh |
| --- | ---: |
| Raw path: /orders/1001, /orders/1002, ... | Có thể tới 200.000 |
| Template: /orders/{orderId} | 1 |
| Chỉ dùng route name cố định | 1 cho endpoint đó |

Tổng số series còn phụ thuộc method, status, exception, outcome, instance và các tags khác. Nếu 1 route có 5 methods/status combinations và 20 service instances, số time series có thể tăng theo tích của các dimensions.

### Một phép tính cardinality đơn giản

Giả sử:
- 40 URI templates.
- 5 HTTP methods.
- 6 response status values.
- 4 outcome values.
- 3 exception categories.

Số tổ hợp tối đa theo tích đơn giản là:

~~~text
40 * 5 * 6 * 4 * 3 = 14,400 tag combinations
~~~

Đây chỉ là upper bound lý thuyết trước khi xét combinations không thể xảy ra, histogram buckets và dimensions khác. Cộng raw path hoặc user ID vào một tag sẽ làm số giá trị tăng mạnh và có thể tạo hàng triệu series.

### Không phải cứ ít route là luôn an toàn

Một ứng dụng có route được tạo động từ tenant hoặc plugin vẫn có nguy cơ cardinality cao dù mỗi template không có ID. Đặt quy tắc route ổn định và tránh build mapping từ dữ liệu request. Khi thiết kế metric tags, cần kiểm tra toàn bộ dimensions chứ không chỉ tag uri.

## 7. Route không match và URI không xác định

Không phải mọi request đều đi tới một controller mapping rõ ràng. Một số tình huống:

- Request tới đường dẫn không tồn tại.
- Method không được hỗ trợ cho path đó.
- Request bị từ chối trước khi DispatcherServlet hoặc router xử lý.
- Static resource handler xử lý request.
- Proxy/gateway rewrite path không như ứng dụng kỳ vọng.
- Custom servlet/filter kết thúc request trước khi route mapping diễn ra.

Trong các tình huống này, framework có thể không có URI template cụ thể. Giá trị uri có thể là giá trị fallback do convention/framework sử dụng, hoặc request không xuất hiện trong meter theo đúng cách bạn mong đợi tùy stack/version.

Không tự thay fallback bằng raw request path. Nếu mọi unknown path được ghi nguyên dạng, một endpoint bị scan hoặc bot request có thể làm cardinality tăng không giới hạn.

### Phân nhóm unmatched routes

Nếu cần theo dõi request không match, ưu tiên một giá trị nhóm ổn định, chẳng hạn route category not-found hoặc fallback path đã chuẩn hóa. Việc phân nhóm cần được thực hiện qua observation convention/filter phù hợp và phải test trên stack thực tế. Đừng thay route template của các request đã match chỉ để gom tất cả vào một nhãn.

Các metric hữu ích bổ trợ:
- Số lượng 404/405 theo outcome/status.
- Request rate vào fallback handler.
- Logs có request ID đã được kiểm soát.
- Security events cho scans hoặc suspicious paths.

## 8. Kiểm tra URI template qua Actuator

Trong ứng dụng có Actuator và endpoint metrics được expose phù hợp, có thể truy vấn meter http.server.requests.

Ví dụ request:

~~~http
GET /actuator/metrics/http.server.requests
~~~

Endpoint metrics có thể trả về measurements tổng hợp cùng available tag keys/values. Cách expose Actuator endpoint cần được cấu hình an toàn; không mở rộng endpoint metrics ra public internet chỉ để debug.

Ví dụ output minh họa:

~~~json
{
  "name": "http.server.requests",
  "measurements": [
    { "statistic": "COUNT", "value": 2.0 },
    { "statistic": "TOTAL_TIME", "value": 0.084 }
  ],
  "availableTags": [
    {
      "tag": "uri",
      "values": ["/orders/{orderId}"]
    },
    {
      "tag": "method",
      "values": ["GET"]
    },
    {
      "tag": "status",
      "values": ["200"]
    }
  ]
}
~~~

Payload thực tế có thể có tag khác và giá trị khác theo app/version. Dùng endpoint để xác nhận framework đang tạo template thay vì raw path.

### Kiểm tra theo tag value

Actuator cho phép lọc meter theo tag đã có. Ví dụ minh họa:

~~~http
GET /actuator/metrics/http.server.requests?tag=uri:/orders/{orderId}
~~~

Khi tạo URL trong shell hoặc browser, ký tự đặc biệt cần được URL encode đúng cách. Endpoint metrics là công cụ kiểm tra, không phải metrics backend truy vấn time series dài hạn.

## 9. Tùy chỉnh ServerRequestObservationConvention

Có thể bổ sung hoặc thay thế tags bằng ServerRequestObservationConvention. Spring Boot documentation khuyến nghị cung cấp bean convention để thêm tags, thường bằng cách mở rộng DefaultServerRequestObservationConvention; nếu muốn thay hoàn toàn tập tags, có thể implement ServerRequestObservationConvention phù hợp.

Ví dụ minh họa thêm một tag có tập giá trị hữu hạn:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.observation.ServerRequestObservationContext;

@Configuration(proxyBeanMethods = false)
class HttpObservationConfiguration {

    @Bean
    DefaultServerRequestObservationConvention serverRequestObservationConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {
                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of("application", "order-api"));
            }
        };
    }
}
~~~

Ví dụ này minh họa hướng mở rộng convention mặc định trong Servlet stack. Import/package/API có thể khác giữa Servlet và Reactive applications; dùng đúng convention type thuộc stack đang chạy. Đừng đăng ký một convention custom mà không gọi dữ liệu mặc định nếu vẫn muốn giữ các tags mặc định.

### Khi cần thay đổi uri tag

Một số trường hợp có thể cần chuẩn hóa alias hoặc phân nhóm một vài route. Spring Framework cung cấp ServerRequestObservationConvention và context tương ứng để tùy chỉnh low-cardinality values. Có thể mở rộng default convention và override phần tạo URI KeyValue, giữ nguyên behavior mặc định cho phần còn lại.

~~~java
@Override
protected KeyValue uri(ServerRequestObservationContext context) {
    KeyValue uri = super.uri(context);
    // Chỉ chuẩn hóa những route được nhận diện rõ ràng.
    return uri;
}
~~~

Đây là skeleton minh họa điểm mở rộng, không phải logic hoàn chỉnh. Không thay uri bằng raw path hoặc string chứa identifiers. Nếu route không match, dùng fallback an toàn và ổn định. Kiểm thử cả matched và unmatched requests trước khi phát hành.

### Thêm tag hay thay tag?

- Mở rộng DefaultServerRequestObservationConvention khi chỉ cần thêm một vài low-cardinality tags, vẫn giữ tags chuẩn.
- Implement ServerRequestObservationConvention khi cần kiểm soát đầy đủ low/high-cardinality values.
- Giữ nguyên ý nghĩa của tags chuẩn như method, status, outcome và uri để dashboard/alert dùng được.
- Không đưa tenant ID, user ID, request ID hoặc full URL vào low-cardinality values.
- Nếu cần high-cardinality attribute cho traces, chỉ thêm khi có mục đích điều tra rõ ràng và đã kiểm tra privacy.

## 10. Không nhầm URI template với URL trong trace

Metrics và traces có thể lưu những thuộc tính khác nhau. URI template phù hợp làm metric dimension ổn định. Trace span có thể có http.route theo semantic conventions và những thuộc tính HTTP khác như request method/status. Raw URL hoặc query string không nên được lưu nếu chứa dữ liệu nhạy cảm hoặc làm lộ identifiers.

Ví dụ:

| Nơi ghi | Giá trị nên dùng | Tránh |
| --- | --- | --- |
| Metrics tag uri | /orders/{orderId} | /orders/1001 |
| Trace attribute http.route | /orders/{orderId} | Raw path có customer ID |
| Log field route | /orders/{orderId} | Toàn bộ query string chứa token |
| Log correlation | request ID đã được sinh và quản lý | Session cookie hoặc bearer token |

Với trace, high-cardinality attribute đôi khi có thể hữu ích cho điều tra một request cụ thể, nhưng không có nghĩa mọi dữ liệu path đều an toàn. Hãy tuân theo data classification và masking policy của mô-đun.

## 11. Custom routes, gateway rewrite và reverse proxy

Ứng dụng thường được triển khai sau reverse proxy, ingress hoặc API gateway. Những thành phần này có thể:
- Thay đổi prefix trước khi chuyển request tới ứng dụng.
- Forward original path qua header.
- Rewrite host/scheme.
- Route tới service bằng path khác với public URL.

URI template mà Spring MVC/WebFlux nhìn thấy thường dựa trên request path sau khi request đến ứng dụng và được handler mapping xử lý. Nó có thể khác public route ở gateway. Đừng mặc định route template trong meter thể hiện URL bên ngoài mà khách hàng đã gọi.

Nếu cần phân tích public route:
1. Xác định gateway có route template riêng hay không.
2. Chỉ forward metadata route đã chuẩn hóa và được tin cậy.
3. Không tin bất kỳ header original-url nào từ caller công khai nếu proxy chưa loại/ghi đè.
4. Không copy raw forwarded URI thành metric tag.
5. Giữ mapping public route và internal route trong dashboard/documentation.

## 12. Ảnh hưởng của URI template tới alert và dashboard

Dùng route template ổn định giúp so sánh request rate, error rate và latency qua thời gian. Ví dụ metric http.server.requests có thể được truy vấn theo uri, method và status.

Một dashboard có thể hiển thị:
- Request rate theo route template.
- P95/P99 latency theo route template và method.
- Tỷ lệ lỗi theo outcome/status.
- Số request vào fallback/not-found route.
- So sánh latency giữa version/service instances.

Ví dụ PromQL (tên metric có thể được backend chuyển đổi từ tên Micrometer):

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    application="order-api"
  }[5m])
)
~~~

P95 minh họa khi histogram đã được export và backend có bucket phù hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri, method) (
    rate(http_server_requests_seconds_bucket{
      application="order-api"
    }[5m])
  )
)
~~~

Tên metric và label thực tế phụ thuộc registry/exporter. Xác minh qua metrics backend trước khi copy query vào dashboard. Không phải mọi backend/registry đều dùng chính xác tên Prometheus như ví dụ.

Alert theo template giúp nhận diện endpoint có vấn đề. Nhưng tránh alert riêng cho từng raw path value; điều đó vừa tạo nhiều series vừa gây nhiễu khi path chứa identifiers.

## 13. Kiểm thử URI template và cardinality

Một test nên xác minh các request có path variables khác nhau cùng tạo một URI template.

Ví dụ dùng Spring Boot test với MockMvc (minh họa):

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpServerUriTemplateTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void requestsWithDifferentIdsShareUriTemplate() throws Exception {
        mockMvc.perform(get("/orders/1001")).andExpect(status().isOk());
        mockMvc.perform(get("/orders/1002")).andExpect(status().isOk());

        Timer timer = meterRegistry.find("http.server.requests")
                .tag("uri", "/orders/{orderId}")
                .tag("method", "GET")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(2);
    }
}
~~~

Test trên giả định controller, dependencies và endpoint test được cấu hình tương ứng. Tag values có thể khác theo framework version hoặc route handling. Nếu dùng WebFlux, dùng WebTestClient và kiểm tra meter tương ứng.

### Các trường hợp cần kiểm thử

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Hai ID khác nhau cùng route | Một template tag, không phải hai raw paths. |
| Route lồng nhau | Template chứa đúng path variables. |
| Route có optional segment | Pattern đúng theo mapping thực tế. |
| Request không match | Fallback/404 behavior không tạo tag raw path mới cho mỗi request. |
| Method không hỗ trợ | Status/outcome được ghi đúng và route grouping ổn định. |
| Exception được xử lý | Error/status tag phản ánh policy quan sát dự kiến. |
| Async/reactive request | Observation kết thúc đúng và context được giữ. |
| Proxy prefix/rewrite | Route template phản ánh path mà application router thực sự match. |

### Kiểm tra cardinality bằng nhiều request

Gửi nhiều request có identifier ngẫu nhiên tới cùng một route, sau đó đếm số giá trị tag uri. Số URI values không được tăng theo số identifiers nếu template được cung cấp đúng.

Không chỉ nhìn số meter tổng. Kiểm tra tag values và time series trong registry/backend. Đồng thời kiểm tra các tags khác: tenant, exception message, query, user ID hoặc custom tag có thể vẫn làm cardinality tăng dù uri đúng.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| uri tag chứa /orders/1001 | Convention nhận raw path hoặc instrumentation/router không cung cấp route pattern. | Kiểm tra matched route, convention và framework version. |
| Mọi request có uri=UNKNOWN | Route mapping không được cung cấp tới Observation, instrumentation/filter bị thiếu hoặc request kết thúc quá sớm. | Kiểm tra filter/router integration và request lifecycle. |
| Request 404 tạo nhiều uri values | Raw unmatched path đang được ghi vào metric tag. | Chuẩn hóa fallback; không ghi raw path vào low-cardinality tag. |
| MVC có template nhưng WebFlux không | Cấu hình hoặc convention thuộc stack khác. | Kiểm tra đúng Servlet/Reactive instrumentation và package. |
| Metrics không có http.server.requests | Actuator/Micrometer instrumentation không hoạt động hoặc meter bị filter. | Kiểm tra dependency, registry và observation configuration. |
| Có metric nhưng trace không có route | Tracing handler/exporter khác pipeline metrics hoặc trace attributes khác convention. | Kiểm tra tracing bridge, span payload và semantic attributes. |
| Đã thêm convention nhưng tag không đổi | Bean không được dùng, type không đúng stack hoặc config có nhiều convention cạnh tranh. | Kiểm tra bean auto-configuration và application context. |
| Dashboard có quá nhiều series | Raw path hoặc custom tags có cardinality cao. | Kiểm tra toàn bộ tag dimensions và registry filters. |
| Route tag khác public URL | Gateway rewrite/prefix thay đổi path trước ứng dụng. | So sánh gateway route và internal handler mapping. |
| 500 không có exception tag như mong đợi | Exception đã được xử lý trước khi tới observation filter. | Đặt error vào ObservationContext theo hướng dẫn framework nếu cần. |

## 15. Runbook: xác minh URI template trong production-like environment

1. **Xác định web stack:** Spring MVC/Servlet, WebFlux/Reactive hoặc Jersey.
2. **Xác định route mappings:** liệt kê các route templates đã khai báo; không lấy danh sách từ raw request logs.
3. **Kiểm tra Observation:** xác nhận http.server.requests được tạo cho request đã match.
4. **Đọc meter:** dùng Actuator metrics endpoint trong môi trường nội bộ để xem tag uri.
5. **Tạo request thử:** gửi cùng route với nhiều path variable values khác nhau.
6. **Đếm tag values:** xác nhận URI template giữ số giá trị ổn định.
7. **Thử unmatched route:** kiểm tra fallback và 404 không tạo raw-path series.
8. **Kiểm tra proxy:** đối chiếu internal route với gateway route/rewrite.
9. **Rà soát custom convention:** kiểm tra tất cả low-cardinality tags và high-cardinality attributes.
10. **Kiểm tra metrics backend:** xem series count, ingest và query latency.
11. **Kiểm tra trace correlation:** xác nhận server spans liên kết đúng request và route attribute không lộ dữ liệu nhạy cảm.
12. **Theo dõi sau rollout:** quan sát cardinality/series growth và rollback convention nếu xuất hiện raw path.

## 16. Bài tập tự kiểm tra

### Bài 1 — Chọn URI tag

Hai request GET /customers/21 và GET /customers/22 cùng match một controller mapping /customers/{customerId}. Giá trị uri nào nên xuất hiện trong http.server.requests?

**Đáp án:** /customers/{customerId}. Cả hai request cùng thuộc một route template.

### Bài 2 — Cardinality

Một API có một triệu order IDs. Vì sao không nên dùng raw request path làm low-cardinality tag?

**Đáp án:** Mỗi order ID có thể tạo một tag value và time series riêng, làm tăng cardinality, memory, index cost và độ phức tạp truy vấn. Dùng URI template để gom các request vào endpoint /orders/{orderId}.

### Bài 3 — Request không match

Một bot gửi hàng nghìn path ngẫu nhiên không có route tương ứng. Nếu metric ghi raw path vào tag uri, chuyện gì có thể xảy ra?

**Đáp án:** Cardinality có thể tăng theo từng path ngẫu nhiên. Dùng fallback/nhóm ổn định cho unmatched requests và giữ chi tiết cần điều tra ở logs có kiểm soát hoặc security telemetry.

### Bài 4 — Public route khác internal route

Gateway nhận /api/v1/orders/1001 rồi rewrite thành /orders/1001 trước khi gọi Spring Boot. URI template nội bộ có thể là gì?

**Đáp án:** /orders/{orderId}, vì Spring handler mapping nhìn thấy path nội bộ sau rewrite. Muốn phân tích public route cần metadata route đã chuẩn hóa từ gateway và được tin cậy.

### Bài 5 — Có metrics, thiếu trace route

Meter có uri template đúng nhưng trace backend không thấy route attribute. Có nhất thiết URI template của metrics bị lỗi không?

**Đáp án:** Không. Metrics và traces có handlers/exporters/semantic attributes riêng. Kiểm tra tracing integration và span payload; không suy luận từ meter tags sang span attributes.

### Bài 6 — Tùy chỉnh convention

Một nhóm muốn thêm tenant ID vào uri tag để phân tích từng khách hàng. Có nên không?

**Đáp án:** Không nên đưa raw tenant ID vào low-cardinality metric tag. Nó có thể tạo series theo tenant. Dùng một nhóm tenant tier có số giá trị hữu hạn nếu có ích và được phê duyệt; dữ liệu cần điều tra từng tenant có thể nằm trong logs/traces theo access và retention policy.

## 17. Checklist triển khai

- [ ] Hiểu URI template là route pattern trước khi thay path variables.
- [ ] Phân biệt route template, raw request URI, full URL và query string.
- [ ] HTTP server Observation http.server.requests hoạt động cho web stack được dùng.
- [ ] Tag uri dùng template của route đã match khi framework cung cấp.
- [ ] Không đưa raw path, path IDs hoặc query parameters vào low-cardinality metric tags.
- [ ] Route definitions ổn định, không tạo mapping động từ request values.
- [ ] Unmatched requests có fallback/nhóm ổn định, không tạo series theo raw paths.
- [ ] ServerRequestObservationConvention được chọn đúng cho Servlet hay Reactive stack.
- [ ] Khi mở rộng default convention, vẫn giữ tags chuẩn cần thiết.
- [ ] Custom tags có cardinality hữu hạn và không chứa PII/secrets.
- [ ] Actuator metrics endpoint được expose trong phạm vi an toàn.
- [ ] Test nhiều IDs cùng route tạo một URI template tag.
- [ ] Test 404/405, exception handling và proxy rewrite.
- [ ] Metrics backend được kiểm tra về series count/cardinality.
- [ ] Logs/traces được dùng để điều tra request cụ thể với correlation và privacy controls.

**Ghi nhớ:** URI template mô tả endpoint ở dạng mẫu, ví dụ /orders/{orderId}; raw path mô tả một request cụ thể, ví dụ /orders/1001. Với HTTP server observability của Spring Boot, dùng route template cho tag uri giúp metrics nhóm request theo endpoint và giữ cardinality ổn định. Hãy xác minh template qua Observation/Actuator, xử lý unmatched routes bằng fallback an toàn và dùng logs/traces có kiểm soát khi cần chi tiết của một request riêng.
