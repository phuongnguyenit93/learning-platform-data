# Ẩn token, cookie và dữ liệu nhạy cảm trong log

Trong hệ thống microservices dùng **Spring Cloud LoadBalancer**, log giúp tìm nguyên nhân lỗi khi `RestClient`, `WebClient` hoặc OpenFeign chọn `ServiceInstance`, gọi HTTP, retry hoặc timeout. Nhưng cùng một log có thể trở thành **đường rò rỉ thông tin xác thực và dữ liệu cá nhân** nếu ứng dụng ghi nguyên `Authorization`, `Cookie`, URL chứa token, response body hoặc exception có thông tin nhạy cảm.

Ví dụ, để chẩn đoán lỗi gọi `catalog-service`, ta thường chỉ cần biết **service ID, thao tác logic, HTTP method, status, thời gian xử lý, loại lỗi và trace ID hợp lệ**. Ta **không cần** biết JWT, session cookie, mật khẩu hoặc dữ liệu thanh toán được gửi trong request.

Bài thuộc chương **Bảo mật giao tiếp** này hướng dẫn thiết kế log theo hướng **chỉ ghi những trường được cho phép (allowlist)**, xử lý tình huống nhiều tầng client tự bật DEBUG/wiretap, kiểm tra log không chứa bí mật và xử lý khi dữ liệu nhạy cảm đã bị ghi ra ngoài.

> Quy tắc nền tảng: **đừng đưa bí mật vào sự kiện log ngay từ đầu**. Che chuỗi sau khi bí mật đã được ghi vào file, log collector hoặc trace là quá muộn để coi dữ liệu đã được bảo vệ.

## 1. Vì sao đây là rủi ro bảo mật, không chỉ là vấn đề log quá dài?

Một request thông thường có thể chứa nhiều loại dữ liệu cần bảo vệ:

~~~http
GET /orders/42?access_token=LAB_ONLY_TOKEN HTTP/1.1
Host: order-service
Authorization: Bearer LAB_ONLY_JWT
Cookie: SESSION=LAB_ONLY_SESSION
X-Request-Id: lab-request-001
~~~

Trong ví dụ, các giá trị đều là **dữ liệu giả để minh họa**. Với request thực tế, nếu token/cookie bị ghi vào log:

- Người hoặc hệ thống có quyền đọc log có thể dùng thông tin xác thực chưa hết hạn để giả danh người dùng hoặc một dịch vụ.
- Log thường được nhân bản sang máy tập trung, search index, tracing backend, dashboard, hệ thống hỗ trợ khách hàng và bản sao lưu.
- Dữ liệu có thể tồn tại lâu hơn thời hạn cần thiết cho debugging.
- Một URL có token trong query có thể lan sang access log, APM, analytics, proxy và exception message.
- Một bản ghi log không được kiểm soát có thể gây vi phạm chính sách nội bộ, yêu cầu hợp đồng hoặc quy định bảo vệ dữ liệu áp dụng.

**HTTPS chỉ mã hóa dữ liệu trên đường truyền.** Nó không ngăn ứng dụng, HTTP client, reverse proxy hoặc hệ thống quan sát ghi chính các header/body đó vào log ở điểm đã giải mã.

### Ba nhóm dữ liệu cần phân biệt

| Nhóm | Ví dụ | Hành động mặc định |
|---|---|---|
| **Bí mật có thể cấp quyền** | Bearer token, API key, refresh token, session cookie, mật khẩu, secret ký, private key | **Không log giá trị** |
| **Dữ liệu cá nhân/nghiệp vụ nhạy cảm** | Email, số điện thoại, địa chỉ, mã định danh khách hàng, thông tin thanh toán, hồ sơ sức khỏe, nội dung đơn hàng | Không log raw; chỉ dùng trường tổng hợp/được phép theo chính sách |
| **Metadata vận hành cần giới hạn** | Service ID, route template, thời gian, status, error category, trace ID, instance ID | Có thể log theo allowlist, kiểm tra khả năng chứa định danh hoặc dữ liệu do người dùng đưa vào |

Ngay cả `instanceId`, hostname hoặc internal IP có thể làm lộ sơ đồ hạ tầng. Không mặc định mọi metadata của `ServiceInstance` đều an toàn để ghi log công khai.

## 2. Những vị trí có thể vô tình ghi lộ dữ liệu

Không chỉ một dòng `logger.debug(...)` trong mã nghiệp vụ mới gây rò rỉ:

| Nguồn log | Dữ liệu có thể xuất hiện | Rủi ro thường gặp |
|---|---|---|
| Controller/filter inbound | URL, headers, form, JSON request | Ghi `Authorization`, `Cookie`, mật khẩu |
| `RestClient` / `RestTemplate` interceptor | URI, request headers/body, response | In cả `request.getHeaders()` hoặc body |
| `WebClient` exchange filter | `ClientRequest`, `ClientResponse`, URI | `toString()`, header dump, body buffering để debug |
| OpenFeign logger | Method, URL, status, headers, body theo mức log | `HEADERS` hoặc `FULL` phơi lộ token/cookie |
| Apache HttpClient wire/header log | HTTP header hoặc dữ liệu truyền theo cấu hình | Debug mức transport in request thực |
| Reactor Netty `wiretap` | Network events, hex/text payload | `HEX_DUMP` hoặc `TEXTUAL` có thể ghi dữ liệu nhạy cảm |
| Gateway/proxy/service mesh | Request target, headers, error page | Access log ghi query hoặc auth headers |
| Exception handler | `exception.getMessage()`, request/response body | URL có secret, nội dung lỗi chứa dữ liệu người dùng |
| Tracing/Micrometer/MDC | Span attributes, baggage, metric labels | Đưa token/user ID/URL thực vào telemetry |
| Logging/observability agent | Captured request/response, stacktrace, custom attributes | Dữ liệu bị gửi sang hệ thống thứ ba |
| Actuator/admin endpoints | Env, configprops, HTTP exchanges, dump | Exposure không phù hợp với access policy |

Một hệ thống có thể giữ log ứng dụng an toàn nhưng vẫn lộ token ở **proxy access log**. Vì vậy phải kiểm tra **toàn tuyến quan sát**, từ caller tới backend và pipeline log.

## 3. Nguyên tắc cốt lõi: allowlist tốt hơn redact một bản ghi thô

Có hai cách thường được đề xuất:

**Cách rủi ro:** ghi nguyên headers, URL và body, sau đó chạy regex thay `Authorization` hoặc `password` bằng `***`.

**Cách ưu tiên:** từ đầu chỉ tạo sự kiện log với các trường đã được phê duyệt, không truy cập dữ liệu bí mật nếu không cần.

Ví dụ:

~~~text
KHÔNG NÊN:
  outbound request=<full URL with query>
  headers=<all request headers>
  body=<full JSON payload>

NÊN:
  event=downstream_http
  service=catalog-service
  operation=catalog.getProduct
  method=GET
  route=/products/{id}
  status=200
  headerLatencyMs=43
  errorCategory=NONE
  traceId=<validated trace identifier>
~~~

`operation` và `route` ở ví dụ là **giá trị định sẵn từ code**, không lấy từ `request.getURI().toString()`. Nếu URI thực chứa `?token=...`, nó không đi vào sự kiện log.

### Bảng phân loại trường

| Trường định log | Cho phép mặc định? | Lưu ý |
|---|---|---|
| Service ID cố định do ứng dụng định nghĩa | Có | Không đưa metadata registry tùy ý vào tag |
| HTTP method | Có | Chỉ giá trị enum như GET/POST |
| Route template `/products/{id}` | Có, nếu đã phê duyệt | Không thay bằng path đã expand chứa ID |
| HTTP status | Có | Không tự log response body cùng status |
| Thời gian / timeout category | Có | Dùng số liệu tổng hợp, tránh per-user high cardinality |
| `Content-Type` | Tùy chính sách | Chỉ allowlist media type, tránh header tùy ý quá dài |
| Raw URL / query string | **Không** | Có thể có token, email, signed URL |
| `Authorization` / `Proxy-Authorization` | **Không** | Credential trực tiếp |
| `Cookie` / `Set-Cookie` | **Không** | Session, CSRF, tracking identifiers |
| `X-API-Key` và các auth headers riêng | **Không** | Danh sách header có thể khác theo dự án |
| Request/response body | **Không** mặc định | JSON, multipart, file, stacktrace từ upstream |
| `exception.getMessage()` | Không mặc định | Có thể chứa URL, headers hoặc body |
| Exception class/category | Có sau kiểm tra | Không in stacktrace kèm message nếu chưa qua kiểm soát |
| Trace ID được tạo/xác thực | Có theo chính sách | Không coi header client gửi tùy ý là an toàn |
| Instance ID/host/IP | Hạn chế | Có thể tiết lộ topology; cần role và retention phù hợp |

Redaction bằng regex vẫn có thể dùng như **lớp phòng thủ bổ sung**, chẳng hạn ở logging pipeline, nhưng không thay thế allowlist tại nơi tạo log. Regex thường bỏ sót tên header tự định nghĩa, giá trị URL-encoded, JSON lồng nhau, multipart và định dạng binary/hex.

## 4. Authorization, Cookie và những dữ liệu ít được chú ý

### 4.1. Header nhạy cảm

Ít nhất cần tránh ghi giá trị của:

- `Authorization`: Bearer, Basic hoặc cơ chế khác.
- `Proxy-Authorization`.
- `Cookie` và `Set-Cookie`.
- `X-API-Key`, `Api-Key`, `X-Auth-Token` và tên header riêng của tổ chức.
- Header mang client assertion, signed request, session ID hoặc token chống giả mạo.
- Bất kỳ header nào có thông tin cá nhân hoặc bí mật theo hợp đồng API.

**Không nên chỉ chặn những tên có chữ “token”.** Nhiều hệ thống sử dụng header tên tùy chỉnh như `X-Credential` hoặc gửi khóa ký qua tên khác.

### 4.2. Dữ liệu trong URL

Các vị trí dễ bị bỏ qua:

~~~text
GET /reset-password?code=LAB_ONLY_RESET_CODE
GET /callback?state=LAB_ONLY_STATE
GET /files?signature=LAB_ONLY_SIGNED_QUERY
GET /orders/customer@example.test
GET /download/ONE_TIME_TOKEN/path
~~~

- Query có thể chứa mã xác thực, signed URL hoặc khóa truy cập.
- Path có thể chứa email, mã khách hàng, token reset password hoặc mã định danh người dùng.
- URI có thể được tự động chèn vào exception, tracing span hoặc HTTP access log.
- Fragment của URL thường không được gửi lên HTTP server, nhưng có thể xuất hiện ở log client/browser nếu ứng dụng tự ghi chuỗi URL gốc.

Ngay cả với `GET`, **không log nguyên URL**. Thay bằng `route template` hoặc operation name an toàn.

### 4.3. Body và multipart

Request body có thể chứa:

- `password`, `refreshToken`, `clientSecret`.
- Hồ sơ người dùng, địa chỉ, số điện thoại, email.
- Thông tin thanh toán hoặc số tài khoản.
- File upload, ảnh tài liệu, nội dung chat.
- Dữ liệu nhạy cảm gửi trong multipart form fields.

Không dựa vào phương thức HTTP để cho rằng `GET` an toàn còn `POST` nguy hiểm: query của `GET` và body của `POST` đều có thể lộ dữ liệu.

## 5. Spring Cloud LoadBalancer cần log gì để debug?

Spring Cloud LoadBalancer chọn `ServiceInstance` từ service ID thông qua discovery, cache, health check và các chính sách chọn/lọc. Để phân tích lỗi, các câu hỏi thường là:

1. Caller gọi **service ID** nào?
2. Có bao nhiêu instance ứng viên được trả về?
3. Có chọn được instance không?
4. Có kết nối thành công và nhận HTTP status không?
5. Có retry không, attempt thứ mấy?
6. Thời gian chờ đến từ discovery, pool, connect, response hay business logic?
7. Lỗi là `NO_INSTANCE`, `NETWORK`, `HTTP_STATUS`, `DECODE` hay `CONTRACT`?

Không cần log token/cookie để trả lời những câu hỏi này.

~~~mermaid
flowchart TD
    A["Ứng dụng gọi catalog-service"]
    B["LoadBalancer chọn ServiceInstance"]
    C["HTTP transport thực thi request"]
    D["Response hoặc exception"]
    E["Sự kiện log có kiểm soát"]
    X["Token / Cookie / Body / Raw URL"]
    A --> B --> C --> D --> E
    B -->|"service ID, kết quả chọn"| E
    C -->|"method, duration, category"| E
    X -.->|"Không đưa vào log"| E
~~~

Trong môi trường đa vùng, có thể bổ sung **nhãn vùng được cho phép**, trạng thái fallback hoặc thuật toán chọn instance. Nhưng `metadata` do registry cung cấp có thể mang thông tin tùy ý: phải chọn field theo allowlist, không in cả `ServiceInstance.getMetadata()`.

### Chú ý high cardinality

Nếu metric tag hoặc log index chứa `userId`, raw URL, token hay một instance ID không giới hạn, hệ thống quan sát có thể phình to rất nhanh và dữ liệu riêng tư trở thành khóa tìm kiếm. Metrics nên dùng các nhãn ổn định như `serviceId`, `operation`, `statusGroup` và `errorCategory`.

## 6. RestClient: interceptor chỉ ghi metadata đã được cho phép

Một `RestClient` được tích hợp LoadBalancer có thể được khai báo bằng `@LoadBalanced RestClient.Builder`. Ví dụ sau **không đọc hoặc ghi** header, URI thực, request body, response body và exception message.

~~~java
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class SafeCatalogClientConfiguration {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeCatalogClientConfiguration.class);

    @Bean("safeCatalogBuilder")
    @LoadBalanced
    RestClient.Builder safeCatalogBuilder() {
        return RestClient.builder().requestInterceptor(
                (request, body, execution) -> {
                    long start = System.nanoTime();

                    try {
                        ClientHttpResponse response =
                                execution.execute(request, body);

                        LOG.info(
                                "event=downstream_http service={} "
                                + "operation={} method={} status={} "
                                + "headersElapsedMs={}",
                                "catalog-service",
                                "catalog.api",
                                request.getMethod().name(),
                                response.getStatusCode().value(),
                                elapsedMillis(start));
                        return response;
                    } catch (IOException | RuntimeException ex) {
                        LOG.warn(
                                "event=downstream_http_failed "
                                + "service={} operation={} "
                                + "errorType={} headersElapsedMs={}",
                                "catalog-service",
                                "catalog.api",
                                ex.getClass().getSimpleName(),
                                elapsedMillis(start));
                        throw ex;
                    }
                });
    }

    @Bean("safeCatalogClient")
    RestClient safeCatalogClient(
            @Qualifier("safeCatalogBuilder") RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }

    private static long elapsedMillis(long start) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
    }
}
~~~

Ở ví dụ trên, `catalog.api` là **nhãn cố định** cho client; nếu cần biết từng thao tác, đặt tên operation tại service adapter bằng hằng số đã được duyệt hoặc sử dụng observation conventions an toàn. Không cố suy luận operation bằng cách ghi nguyên `request.getURI()`.

**Giới hạn của phép đo:** interceptor ở đây đo thời gian đến khi `execution.execute(...)` trả response và có thể **chưa bao gồm đọc hết response body**. Không ghi nhãn này là “toàn bộ thời gian nghiệp vụ”. Với retry, mỗi attempt có thể sinh sự kiện riêng tùy vị trí interceptor trong chain.

**Không ghi `ex.getMessage()` hoặc truyền nguyên `ex` vào logger trong ví dụ bảo vệ dữ liệu**, vì message/stacktrace có thể chứa URL/headers/body hoặc giá trị do downstream đưa vào. Nếu cần debug lỗi sâu, định nghĩa mã lỗi chuẩn và cơ chế thu thập sự cố có kiểm soát, không dựa vào raw exception trong log sản xuất.

### 6.1. Các lỗi cần tránh

~~~java
// KHÔNG NÊN: những giá trị dưới đây có thể chứa bí mật.
log.debug("uri={}", request.getURI());
log.debug("headers={}", request.getHeaders());
log.debug("body={}", new String(body, StandardCharsets.UTF_8));
log.error("HTTP call failed", exception);
~~~

Đây là những **mẫu chống chỉ định**, không phải code để sử dụng trong ứng dụng thực. Đặc biệt, `new String(body)` còn giả định body là text; với binary upload có thể ghi dữ liệu lớn, hỏng encoding và gây áp lực bộ nhớ.

Nếu muốn đo kích thước request, chỉ cân nhắc giá trị `body.length` khi interception đã có byte array, nhưng cần hiểu một số interceptor/request factory có thể ảnh hưởng đến buffering và streaming. Không bật body buffering chỉ để ghi log kích thước upload.

### 6.2. Khả năng quan sát của Spring Boot

Ví dụ tự tạo `RestClient.builder()` tập trung minh họa nguyên tắc log. Trong ứng dụng Spring Boot, nếu cần giữ các auto-customizer của framework (observation/tracing, JSON converter, authentication interceptor), cân nhắc `RestClientBuilderConfigurer` hoặc builder được Boot quản lý. Không đánh đổi khả năng quan sát có kiểm soát để tạo interceptor ghi raw request.

## 7. WebClient: exchange filter không cần đọc headers hoặc body

Với `WebClient`, có thể gắn `ExchangeFilterFunction` để ghi status và thời gian mà **không đụng tới dữ liệu nhạy cảm**:

~~~java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class SafeCatalogWebClientConfiguration {

    private static final Logger LOG =
            LoggerFactory.getLogger(
                    SafeCatalogWebClientConfiguration.class);

    @Bean
    @LoadBalanced
    WebClient.Builder safeCatalogWebClientBuilder() {
        ExchangeFilterFunction safeLogging = (request, next) -> {
            long started = System.nanoTime();

            return next.exchange(request)
                    .doOnNext(response -> LOG.info(
                            "event=downstream_http service={} "
                            + "operation={} status={} headersElapsedMs={}",
                            "catalog-service",
                            "catalog.api",
                            response.statusCode().value(),
                            millis(started)))
                    .doOnError(error -> LOG.warn(
                            "event=downstream_http_failed "
                            + "service={} operation={} errorType={} "
                            + "headersElapsedMs={}",
                            "catalog-service",
                            "catalog.api",
                            error.getClass().getSimpleName(),
                            millis(started)));
        };

        return WebClient.builder().filter(safeLogging);
    }

    private static long millis(long start) {
        return TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start);
    }
}
~~~

Đoạn code không gọi `ClientRequest.url()`, không in `ClientRequest.headers()`, không dùng `ClientResponse.bodyToMono(String.class)` để log. Nó cũng không subscribe thêm vào response body — một lỗi thường gặp khi viết filter debug reactive.

**Lưu ý:** thời gian được đo đến khi có response headers, chưa chắc bao gồm việc tiêu thụ hết body; nếu có retry/resubscription, số event phụ thuộc vị trí filter trong reactive chain. Một logging filter không thể tự bảo đảm các tầng thấp hơn không bật wiretap.

### Với streaming, tuyệt đối không buffer body chỉ để debug

`Flux<DataBuffer>` hoặc response stream có thể chứa file, video, SSE hay dữ liệu lớn. Nếu cố `collectList()` toàn bộ stream để log:

- Có thể giữ lượng dữ liệu lớn trong RAM.
- Có nguy cơ phá backpressure, không giải phóng buffer đúng cách hoặc làm chậm consumer.
- Có thể đưa thông tin nhạy cảm vào log/traces.
- Với stream vô hạn, thao tác thu thập toàn bộ không có điểm kết thúc.

Với streaming, ưu tiên tổng số byte, thời lượng, số chunks, trạng thái hoàn tất/hủy và mã lỗi đã được chuẩn hóa — không ghi payload.

## 8. OpenFeign: mức NONE, BASIC, HEADERS và FULL

Theo tài liệu Spring Cloud OpenFeign, `Logger.Level` có bốn mức:

| Mức Feign | Có thể ghi gì? | Đánh giá rủi ro |
|---|---|---|
| `NONE` | Không log request/response ở logger Feign | Lựa chọn an toàn nhất nếu không cần wire-level Feign logs |
| `BASIC` | Method, **URL**, status, elapsed | URL có query/path chứa token hoặc thông tin cá nhân vẫn có thể lộ |
| `HEADERS` | BASIC + request/response headers | Có thể lộ `Authorization`, `Cookie`, `Set-Cookie` |
| `FULL` | Headers và body request/response | Rủi ro cao nhất: lộ cả bí mật và dữ liệu nghiệp vụ |

Feign logging cũng thường chỉ phát ra khi logger của Feign client được bật mức **DEBUG**. Vì vậy, mở DEBUG cho package/interface Feign và tăng `loggerLevel` có thể thay đổi lượng dữ liệu ghi ra đáng kể.

### 8.1. Cấu hình hạn chế logging

Ví dụ với client `@FeignClient(name = "catalog-service")`:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            loggerLevel: NONE

logging:
  level:
    com.example.orders.client.CatalogFeignClient: INFO
~~~

`NONE` đặt Feign logger không ghi request/response; `INFO` cũng tránh bật DEBUG logger dành cho client này. **Cả hai không vô hiệu hóa** những logger khác do application interceptor, HTTP transport, gateway hoặc APM đã cấu hình.

### 8.2. Vì sao BASIC chưa chắc an toàn?

Một URL như:

~~~text
GET /files/download?signature=LAB_ONLY_SIGNED_URL
~~~

có thể bị ghi ở mức `BASIC` vì URL nằm trong thông tin cơ bản. Do đó, nếu ứng dụng có thể truyền credential trong query/path, **không coi BASIC là mức đã redact**.

Nếu tổ chức buộc phải dùng debug Feign chuyên sâu, nên thực hiện trên môi trường có dữ liệu tổng hợp, dùng logger tùy biến đã được kiểm thử chính sách masking và giới hạn thời gian/phạm vi. Không bật `FULL` với token thật chỉ vì gặp lỗi timeout.

### 8.3. Feign không phải tầng duy nhất

Với Spring Cloud LoadBalancer, `FeignBlockingLoadBalancerClient` giúp chọn instance. HTTP delegate phía dưới Feign (Apache HttpClient 5 hoặc transport khác) có logging riêng. Đặt `loggerLevel: NONE` cho Feign không bảo đảm HTTP delegate đã tắt wire/header logging.

## 9. Apache HttpClient và Reactor Netty wiretap

HTTP transport có thể ghi dữ liệu ở mức thấp hơn các Spring client API.

### Apache HttpClient 5

Khi mở DEBUG/TRACE hoặc wire logs ở các category tương ứng, có thể xuất hiện request/response headers hoặc nội dung HTTP. Tên logger phụ thuộc version và transport đang dùng; cần kiểm tra cấu hình logging của các dependency thực tế.

Một cấu hình phòng thủ minh họa:

~~~yaml
logging:
  level:
    org.apache.hc.client5.http.wire: OFF
    org.apache.hc.client5.http.headers: OFF
    org.apache.hc.core5.http.wire: OFF
~~~

Đây **không phải bảo đảm tổng quát** rằng mọi logger của Apache hoặc thư viện do bên thứ ba tạo đã ngừng ghi payload. Cần kiểm tra các logger thực sự đang được bật bằng integration test và quan sát log từ cả client lẫn proxy.

### Reactor Netty

Reactor Netty có tính năng `wiretap`, mặc định không bật. Các formatter có đặc điểm:

- `SIMPLE`: chủ yếu các sự kiện và kích thước bytes, không chủ đích ghi nội dung payload.
- `HEX_DUMP`: có thể ghi nội dung HTTP dưới dạng hex; **hex vẫn là dữ liệu có thể giải mã**, không phải hình thức ẩn danh.
- `TEXTUAL`: có thể ghi nội dung dạng text, bao gồm headers/body ở những tình huống phù hợp.

Trong production, **ưu tiên tắt wiretap và dùng WebClient filter/observation an toàn**. Ngay cả `SIMPLE` có thể cho thấy địa chỉ kết nối hoặc metadata hạ tầng; chỉ bật nếu chính sách tổ chức cho phép.

~~~text
NÊN trong production:
  Reactor Netty wiretap: disabled
  HTTP event logging: allowlisted fields

CHỈ trong lab với dữ liệu giả:
  Wiretap hoặc logger cấp transport để phân tích protocol
  Không dùng Bearer token, cookie hoặc PII thật
~~~

Nếu bật debug HTTP ở một môi trường staging dùng dữ liệu sao chép từ production, đó vẫn là môi trường có rủi ro lộ dữ liệu thật.

## 10. Không để dữ liệu nhạy cảm chảy qua exception và error handler

Một chuỗi lỗi thường gặp:

~~~text
RestClient/WebClient/Feign request lỗi
  -> HTTP/transport exception
  -> exception message có thể chứa URL, response hoặc chi tiết upstream
  -> global exception handler gọi logger.error("...", exception)
  -> centralized log nhận thông tin không mong muốn
~~~

Các thao tác cần xem xét kỹ:

- `error.getMessage()` / `error.toString()`.
- `logger.error("failed", exception)`: stacktrace kèm message/cause.
- `RestClientResponseException.getResponseBodyAsString()`.
- `WebClientResponseException.getResponseBodyAsString()`.
- `FeignException.contentUTF8()` hoặc truy cập raw response body.
- `request.getURI().toString()` / `response.getHeaders().toString()`.

Không phải mọi exception chắc chắn chứa secret; vấn đề là **không được bảo đảm rằng chúng không chứa secret**. Vì vậy, log ứng dụng cần phân loại exception thành category ổn định:

| Nhóm lỗi an toàn để ghi | Căn cứ phân loại |
|---|---|
| `NO_INSTANCE` | LoadBalancer không chọn được ứng viên |
| `CONNECT_FAILURE` | Lỗi mở kết nối theo loại exception đã kiểm tra |
| `TIMEOUT` | Connect/read/pool timeout đã được nhận diện |
| `HTTP_4XX` / `HTTP_5XX` | HTTP status family |
| `DECODE_FAILURE` | JSON/codec decoding không phù hợp |
| `CIRCUIT_OPEN` | Circuit breaker không cho thực thi |
| `UNKNOWN` | Không phân loại được mà không cần in raw message |

Một lỗi chưa phân loại nên ghi `UNKNOWN` cùng trace/correlation ID an toàn, để đội vận hành tra cứu qua telemetry đã được kiểm soát. Không dùng `error.getMessage()` làm metric tag hoặc thông báo hiển thị cho người dùng.

### Lỗi từ downstream trả về client

Không phản chiếu nội dung exception của downstream vào HTTP response dành cho người dùng cuối. Dùng error contract có mã ổn định (ví dụ `DOWNSTREAM_UNAVAILABLE`) và correlation ID; chi tiết nội bộ chỉ tồn tại trong công cụ điều tra có quyền truy cập phù hợp.

## 11. MDC, trace ID và baggage cũng cần được kiểm tra

Distributed tracing giúp ghép lời gọi giữa `order-service`, `catalog-service` và các bản sao được LoadBalancer chọn. Nhưng có thể xảy ra rò rỉ nếu đưa dữ liệu nhạy cảm vào các trường:

- MDC: `MDC.put("authorization", token)` là sai.
- Baggage: không truyền email, token hoặc số tài khoản theo mọi span.
- Span attributes: không gắn raw URL, query string hoặc response body.
- Metric tags: không dùng user ID, access token, email hoặc exception message làm label.
- Trace ID/correlation ID: nếu lấy từ header người dùng cung cấp, cần xác thực cú pháp và giới hạn độ dài.

### Correlation ID an toàn

Nếu ứng dụng tiếp nhận `X-Request-Id` từ request bên ngoài:

1. Chỉ chấp nhận một định dạng đã kiểm tra, chẳng hạn ASCII letters/digits, dấu gạch nối/gạch dưới và tối đa 64 ký tự.
2. Nếu không hợp lệ, tạo ID mới ở biên tin cậy.
3. Không log giá trị header gốc khi validation thất bại.
4. Không dùng một correlation ID làm khóa bảo mật hoặc bằng chứng xác thực.

Ví dụ logic minh họa:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

final class CorrelationIds {

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    static String acceptedOrGenerated(String inbound) {
        if (inbound != null &&
                SAFE.matcher(inbound).matches()) {
            return inbound;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Đây là minh họa kiểm tra cú pháp để tránh giá trị quá dài hoặc ký tự xuống dòng trong log. **Nó không chứng minh ID do client cung cấp là đáng tin cậy**; các hệ thống cần tracing boundary nghiêm ngặt có thể luôn tự tạo ID hoặc dùng trace context có kiểm tra.

Nếu log backend kết hợp MDC và JSON encoder, hãy giới hạn tên/value của MDC được phép ghi. Cấu hình `%X` hoặc ghi toàn bộ MDC map có thể vô tình xuất ra key do thư viện khác chèn.

## 12. Actuator và cấu hình bảo vệ dữ liệu quan sát

Spring Boot Actuator có các endpoint như `/actuator/env` và `/actuator/configprops`, có cơ chế sanitize giá trị cấu hình nhạy cảm. Tuy nhiên:

- Sanitization của Actuator **không làm sạch application logs** đã được tạo bởi `logger.info(...)` hoặc Feign/wiretap.
- Các endpoint quản trị vẫn cần authentication, authorization và giới hạn exposure.
- Không bật hiển thị giá trị đầy đủ chỉ để debug nếu có cấu hình chứa secret.
- `httpexchanges`, nếu được bật và có repository phù hợp, cần xem xét những thông tin HTTP được lưu và quyền truy cập; không mặc định là một nơi an toàn để chứa dữ liệu riêng tư.

Ví dụ chính sách bảo thủ cho giá trị cấu hình:

~~~yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Cấu hình trên chỉ nhằm minh họa việc hạn chế Actuator exposure. Nó không tự bảo vệ ingress logs, access logs, proxy logs, application logs hay logs của transport. Hãy kiểm tra bảo mật quản trị theo phiên bản Spring Boot và chính sách thực tế.

## 13. Masking ở tầng log pipeline: chỉ là phòng thủ bổ sung

Nếu hệ thống bắt buộc xử lý những bản ghi cũ hoặc dữ liệu từ thư viện không thể sửa ngay, log collector có thể áp dụng quy tắc redaction trước khi indexing/storage. Nhưng cần hiểu giới hạn:

| Phương pháp | Lợi ích | Điểm yếu |
|---|---|---|
| Không log raw, chỉ cho phép các field xác định | Ngăn secret xuất hiện từ đầu | Cần thiết kế sự kiện log rõ ràng |
| Mask một tập header nhạy cảm | Giảm rủi ro một số log cấu trúc | Có thể bỏ sót header tự định nghĩa |
| Regex thay `Bearer ...` | Có thể lọc một số chuỗi | Bỏ sót token ở URL, JSON, encoding khác, line wrap |
| DLP scanner tại ingest | Phát hiện thêm dạng secret/PII | False positive/false negative, dữ liệu đã đi tới scanner |
| Hạn chế quyền truy cập và retention | Giảm phạm vi/phơi nhiễm | Không biến secret đã lộ thành vô hại |
| Mã hóa log storage | Giảm rủi ro truy cập trái phép vào storage | Người có quyền đọc log vẫn có thể thấy raw secret |

**Tránh log rồi mới redact trong cùng tiến trình nếu có thể**: một appender khác, APM agent, async queue hoặc debug console có thể nhận bản ghi gốc trước bộ lọc.

### Trường hợp cần fingerprint một token

Đôi khi đội vận hành muốn biết hai request có dùng cùng credential hay không. **Không tự log SHA-256(token)** như giải pháp mặc định: hash ổn định vẫn tạo định danh liên kết request, có thể có rủi ro riêng tư hoặc bị khai thác nếu không gian bí mật nhỏ.

Ưu tiên dùng **operation ID hoặc correlation ID độc lập**. Nếu thật sự cần fingerprint credential, phải có thiết kế được phê duyệt (ví dụ keyed HMAC, khóa quản lý an toàn, scope/retention rõ ràng) và không để giá trị này trở thành metric tag công khai.

## 14. Thực hành: kiểm tra không lộ token khi gọi qua LoadBalancer

Dùng hai instance `catalog-service` ở môi trường local/test, mỗi instance trả một giá trị `/whoami` để quan sát LoadBalancer. Không sử dụng credentials thật.

### 14.1. Chuẩn bị yêu cầu giả lập

Ví dụ input:

~~~http
GET http://catalog-service/orders/42?access_token=LAB_CANARY_QUERY_001
Authorization: Bearer LAB_CANARY_BEARER_001
Cookie: SESSION=LAB_CANARY_COOKIE_001
X-API-Key: LAB_CANARY_APIKEY_001
X-Request-Id: safe-lab-123
~~~

Đây là các **canary string giả**. Dùng một response JSON thử nghiệm:

~~~json
{
  "customerEmail": "canary@example.test",
  "password": "LAB_CANARY_PASSWORD_001",
  "result": "ok"
}
~~~

Không đưa các canary vào log “an toàn”; chúng chỉ là dấu hiệu để **bài test tìm và thất bại nếu bất kỳ lớp logging nào làm lộ**.

### 14.2. Kịch bản test

1. Cấu hình `@LoadBalanced RestClient.Builder` với safe interceptor ở mục 6.
2. Gọi một endpoint test có thể tiếp nhận header và query giả, đồng thời backend trả body có canary.
3. Xác nhận request thực sự đã được xử lý (server trả status, hoặc test assertion trên handler) mà không in input.
4. Thu thập log ứng dụng, HTTP client, gateway/proxy lab và bản ghi của hệ thống observability được dùng trong môi trường thử nghiệm.
5. Tìm các canary string ở tất cả output đó.
6. Bật một lần cấu hình Feign ở mức `NONE`, sau đó nếu cần khảo sát rủi ro `FULL`, chỉ dùng dữ liệu giả và môi trường cô lập; xác nhận vì sao `FULL` vi phạm chính sách khi có secret.
7. Với WebClient, thử khi wiretap tắt, sau đó (chỉ trong lab) bật wiretap để hiểu loại dữ liệu có thể bị ghi.
8. Kiểm tra cả lỗi HTTP 401/403/503, timeout và exception đường mạng; nhánh thất bại cũng không được chứa bí mật.

### 14.3. Assertions cho log capture

Pseudocode kiểm thử, phụ thuộc framework ghi log/integration test đang dùng:

~~~java
String allCapturedLogs = captureLogsFromTheTestRun();

assertFalse(allCapturedLogs.contains("LAB_CANARY_BEARER_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_COOKIE_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_QUERY_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_APIKEY_001"));
assertFalse(allCapturedLogs.contains("LAB_CANARY_PASSWORD_001"));
assertFalse(allCapturedLogs.contains("canary@example.test"));

assertTrue(allCapturedLogs.contains("service=catalog-service"));
assertTrue(allCapturedLogs.contains("status=200"));
~~~

Hàm `captureLogsFromTheTestRun()` là **placeholder của test harness**, không phải API có sẵn trong Spring. Khi dùng Logback, có thể dùng in-memory appender trong test; khi dùng JSON logs/async appender, phải kiểm tra output cuối cùng. Nếu canary không xuất hiện chỉ vì request chưa chạy hoặc logs không được capture, đó là **false pass**.

Đảm bảo test có **positive control**: một sự kiện log không nhạy cảm xác nhận pipeline đã được capture, và HTTP request đã đến backend.

### 14.4. Ma trận cần kiểm tra

| Kịch bản | Điều cần không xuất hiện trong log | Điều vẫn nên quan sát được |
|---|---|---|
| Request thành công HTTP 200 | Token, cookie, raw body | Service, operation, status, latency |
| HTTP 401/403 | Auth header, error body nhạy cảm | Status, loại lỗi auth |
| HTTP 503/timeout | Full URI, raw exception message có URL | Error category, attempt, timing |
| Retry sang instance khác | Credential trong header của mỗi attempt | Attempt number, service ID, outcome |
| OpenFeign `BASIC`/`HEADERS`/`FULL` trong lab | Báo cáo mức nào có nguy cơ lộ | Cơ sở để chọn `NONE` cho production |
| Reactor Netty wiretap | Payload thật không đi vào output production | Event/metric không nhạy cảm |
| URI có query/path mang canary | Raw URL hoặc mã đặt trong path | Route template và HTTP method |
| Response JSON chứa PII | Raw JSON, email/password | Status, content type loại đã duyệt |
| Tracing/MDC có input từ client | Header không qua validation, token/baggage | Trace ID an toàn |
| Actuator/admin endpoints | Giá trị config secret khi chưa cấp quyền | Health/info đã giới hạn exposure |

## 15. Xử lý khi phát hiện secret đã bị ghi vào log

Nếu một token hoặc session cookie thật đã lọt vào log, **không đủ** để chỉ sửa code và chờ log cũ tự hết hạn. Cần có quy trình ứng phó theo chính sách tổ chức:

1. **Ngăn phát sinh thêm:** tắt logger/feature gây lộ, triển khai bản sửa, kiểm tra các môi trường và thư viện liên quan.
2. **Đánh giá phạm vi:** xác định service, khoảng thời gian, loại secret, log sink, index, dashboard, backup và các hệ thống downstream đã nhận bản ghi.
3. **Thu hồi/đổi credential:** revoke token, invalidate session, rotate API keys/secrets tương ứng theo mức độ rủi ro.
4. **Hạn chế truy cập:** thu hẹp quyền xem log, bật audit access, xử lý các bản chia sẻ hoặc export không cần thiết.
5. **Xử lý dữ liệu lưu:** thực hiện deletion/redaction theo chính sách retention, backup và yêu cầu pháp lý, đồng thời bảo toàn bằng chứng cần thiết theo quy trình ứng phó sự cố.
6. **Kiểm tra lặp lại:** thêm regression tests với canary; xác minh không còn dữ liệu ở log mới, trace, metrics, gateway và APM.
7. **Rút kinh nghiệm:** áp dụng allowlist chung, chuẩn hóa logger và quy trình phê duyệt bật DEBUG trên production.

Không tải log nghi chứa token thật sang các công cụ công cộng, ticket không được bảo vệ hoặc chat nhóm rộng chỉ để nhờ phân tích. Hãy dùng kênh xử lý sự cố có kiểm soát.

## 16. Checklist khi triển khai logging an toàn

- Đã định nghĩa rõ loại token, cookie, PII và dữ liệu nghiệp vụ nào **không bao giờ được log** chưa?
- Có dùng allowlist các field ổn định thay vì dump toàn bộ headers/URL/body không?
- Có ghi route template và operation name, không ghi raw URI/query/path variables nhạy cảm?
- `RestClient` interceptor và `WebClient` filter có tránh truy cập/log body, headers, exception message không?
- OpenFeign `Logger.Level` có được giữ ở `NONE` hoặc cơ chế đã được kiểm duyệt; có ngăn bật `FULL` trên production không?
- Apache HttpClient/Netty wiretap, gateway, proxy và APM có được kiểm tra riêng?
- Logs, MDC, baggage và metrics tags có tránh token, user ID, email và high-cardinality values không?
- Correlation ID từ bên ngoài có được xác thực cú pháp/giới hạn độ dài hoặc tạo lại?
- Các lỗi HTTP 4xx/5xx, timeout, retry, decoder và circuit breaker có được log bằng category an toàn?
- `/actuator/env`, `/actuator/configprops`, `/actuator/httpexchanges` và các endpoint quản trị có bị hạn chế hợp lý?
- Quyền đọc log, thời gian giữ, storage encryption, log export và audit access có được kiểm soát?
- Đã chạy integration test dùng canary qua **đường log thực tế**, cả happy path lẫn error path?
- Có runbook xử lý leak: thu hồi token, xác minh log sink và hồi quy chính sách?

**Kết luận:** Log an toàn cho Spring Cloud LoadBalancer không phải là log ít đến mức không debug được, mà là **ghi đúng metadata cần thiết ở từng tầng**. Service ID, operation, kết quả chọn instance, HTTP status, latency, error category và trace ID được kiểm soát thường đủ để chẩn đoán. `Authorization`, `Cookie`, signed URL, request/response body và raw exception message không được đưa vào log mặc định. Hãy ưu tiên **allowlist tại nguồn**, tắt wire-level payload logging trong production, kiểm thử bằng canary và bảo vệ toàn bộ pipeline quan sát.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud OpenFeign – Feign Logging](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Framework – REST Clients và Client Interceptors](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Reactor Netty – HTTP Client Wire Logger](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Spring Boot – Actuator Endpoints và Sanitize Sensitive Values](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

