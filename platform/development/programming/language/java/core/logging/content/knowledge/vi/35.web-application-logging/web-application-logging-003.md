# Request path trong logging của ứng dụng web Java

## 1. Request path là gì và tại sao cần ghi log?

Trong một ứng dụng web Java, **request path** là phần đường dẫn của HTTP request trỏ tới tài nguyên hoặc endpoint mà client yêu cầu, chẳng hạn `/api/orders/42`. Ghi nhận đường dẫn giúp tìm API phát sinh lỗi, kiểm tra phân bố traffic, điều tra 404/403, đối chiếu các request qua hệ thống phân tán và phân tích thời gian đáp ứng.

Tuy nhiên, **request path không đồng nghĩa toàn bộ URL**. Nếu ghi nguyên URL, ứng dụng có thể vô tình lưu token trong query string, dữ liệu cá nhân trong path segment hoặc tạo hàng triệu giá trị khác nhau cho hệ thống metrics. Mục tiêu của bài học là hiểu phần nào nên ghi trong operational log, phần nào chỉ dùng cho phân tích bảo mật hạn chế quyền, và cách làm đúng với Servlet, Spring MVC và Java thuần.

Xét HTTP request minh họa:

```http
GET /shop/orders/42?access_token=example-token&view=full HTTP/1.1
Host: api.example.test
```

Có thể phân tách:

| Khái niệm | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| HTTP method | `GET` | Hành động HTTP |
| Scheme | `https` nếu kết nối bên ngoài là HTTPS | Không nằm trong request-target dạng origin-form |
| Host | `api.example.test` | Máy chủ được yêu cầu; có thể bị ảnh hưởng bởi proxy |
| Request path | `/shop/orders/42` | Phần đường dẫn, **không gồm query string** |
| Query string | `access_token=example-token&view=full` | Phần sau dấu `?`, có thể chứa dữ liệu nhạy cảm |
| Route template | `/shop/orders/{orderId}` | Mẫu route do ứng dụng/framework xác định |
| Path variable | `orderId=42` | Giá trị động trích từ đường dẫn |
| Full URL | `https://api.example.test/shop/orders/42?access_token=example-token&view=full` | Bao gồm scheme, authority, path và query |

Các thành phần trên phục vụ mục đích khác nhau. Đối với **log truy vấn theo endpoint**, route template thường phù hợp hơn raw path. Đối với **điều tra một request cụ thể**, dùng request ID/trace ID, route, status và thông tin cần thiết. Chỉ giữ raw path có kiểm soát khi có nhu cầu điều tra và chính sách riêng.

**Không được suy ra path an toàn chỉ vì query string đã bị bỏ.** Đường dẫn như `/users/alice@example.com`, `/reset/example-token` hoặc `/documents/medical-record-123` vẫn có thể chứa thông tin nhạy cảm.

## 2. Phân biệt path, raw path, URI, URL và route

### Path và query là hai thành phần riêng

Theo cú pháp URI, dấu `?` ngăn phần path khỏi phần query. Ví dụ:

```text
/api/products/20?sort=price&page=2
└──── path ──────┘ └──── query ────┘
```

HTTP client có thể gửi URL đầy đủ hoặc request target theo nhiều dạng tùy proxy/protocol; ở tầng ứng dụng web thông thường, Servlet hoặc HTTP framework đã phân tích request thành các phần có thể truy cập qua API. **Không tự tách chuỗi bằng `split("?")` rồi coi đó là parser URL đáng tin.** Dấu `?` có thể xuất hiện dưới dạng encoded trong path, ký tự không hợp lệ cần xử lý khác nhau và request-target cũng có những hình thức đặc biệt như `*` hoặc authority-form đối với một số phương thức.

### Raw path và decoded path

Path có thể chứa percent-encoding:

```text
Raw path:     /api/users/alice%40example.com
Decoded path: /api/users/alice@example.com
```

**Raw path** giữ nguyên biểu diễn percent-encoded (trong phạm vi thông tin mà HTTP server cung cấp); **decoded path** diễn giải các mã `%HH` theo quy tắc URI và ký tự. Hai chuỗi không hoàn toàn thay thế nhau:

- Dấu `%2F` có thể đại diện slash; container, proxy và routing framework có thể xử lý encoded slash theo những chính sách khác nhau.
- `%2e`, `..`, dấu backslash, nhiều slash liên tiếp và double-encoding có thể dẫn tới khác biệt giữa kiểm tra bảo mật, routing và logging.
- Percent-decoding không giống `application/x-www-form-urlencoded`: trong URI path, dấu `+` không mặc nhiên là khoảng trắng. Không sử dụng `URLDecoder` như một bộ chuẩn hóa path chung.
- Unicode, chữ hoa/thường và dấu phân cách có thể bị chuẩn hóa khác nhau tại reverse proxy và backend.

**Giá trị được log không được dùng làm nguồn chân lý cho quyết định phân quyền.** Ứng dụng phải dựa vào path/route mà server thực sự đã dùng để định tuyến và policy, đồng thời giữ đủ thông tin chẩn đoán an toàn khi proxy và backend bất đồng.

### Route template khác request path

Route `/api/orders/{orderId}` có thể khớp hàng triệu path thực tế như `/api/orders/42`, `/api/orders/43`... Nếu mỗi path thực trở thành một label/tên metric riêng, số chuỗi thời gian có thể tăng không kiểm soát.

Do đó:

- **Log chuẩn:** nên có `http.method`, `http.route`, `http.status_code`, `request_id`, `duration_ms` và service metadata phù hợp.
- **Metric HTTP:** nhãn `route` nên dùng template đã xác định hoặc một hằng số bounded như `UNMATCHED`, không dùng ID động hay path gốc.
- **Điều tra riêng:** chỉ lưu path đã redaction/giới hạn, trong một kênh có quyền truy cập và retention phù hợp.

Không tự tạo route template bằng cách thay mọi dãy số trong path bằng `{id}` rồi coi đó là route thật: có thể nhầm endpoint, làm mất cấu trúc và che dấu vấn đề routing. Lấy route pattern do web framework đã match; nếu chưa match, dùng fallback có số lượng giá trị hữu hạn.

## 3. Request path trong Servlet API

Với ứng dụng Java Servlet dùng `HttpServletRequest`, một số API liên quan:

| API | Nội dung chính | Điểm cần chú ý |
| --- | --- | --- |
| `request.getRequestURI()` | Phần URI path mà client yêu cầu trong phạm vi container, **không gồm query** | Bao gồm context path và phần đường dẫn còn lại; thường trả về dạng chưa decode, nhưng hành vi với input bất thường còn phụ thuộc container |
| `request.getContextPath()` | Context path của web application, có thể là chuỗi rỗng | Ví dụ `/shop` nếu deploy dưới context `shop` |
| `request.getServletPath()` | Phần path tương ứng servlet mapping | Không nhất thiết là route template của MVC controller |
| `request.getPathInfo()` | Path bổ sung sau phần servlet mapping, có thể `null` | Không phải lựa chọn phổ quát cho mọi servlet mapping |
| `request.getQueryString()` | Query string chưa decode, hoặc `null` | Có thể chứa token, mật khẩu hoặc dữ liệu cá nhân; tránh ghi trực tiếp |
| `request.getRequestURL()` | `StringBuffer` chứa URL được dựng lại đến hết path | Không gồm query; scheme/host/port có thể cần xem xét proxy/forwarded headers |
| `request.getMethod()` | HTTP method | Kiểm tra các phương thức bất thường theo policy |
| `response.getStatus()` | HTTP response status hiện có | Đo ở thời điểm completion có ý nghĩa, đặc biệt request async |

Ví dụ với context path `/shop` và route trong ứng dụng `/orders/{id}`, request URI có thể là `/shop/orders/42`. Nhưng `getServletPath()` và `getPathInfo()` còn phụ thuộc servlet mapping. Không ghép mọi trường bằng công thức cứng để suy ra MVC route.

Servlet `javax.servlet.*` được dùng trong những hệ thống cũ; các hệ thống dùng Jakarta EE/Spring Boot 3+ dùng `jakarta.servlet.*`. Bản chất phân biệt request URI/query vẫn quan trọng, nhưng tên package và tích hợp phải khớp dependency thực tế.

### Đoạn minh họa bên trong Filter

```java
String method = request.getMethod();
String rawRequestUri = request.getRequestURI();
String query = request.getQueryString();

// Không ghi rawRequestUri hoặc query trực tiếp vào access log mặc định.
// Chúng có thể chứa path variable, token hoặc thông tin cá nhân.
```

Đây **không phải chương trình độc lập**; nó giả định các biến `request` và `response` là Servlet API objects. Trong production, chọn trường log bằng framework routing metadata, không tự tin rằng mọi `getRequestURI()` đều an toàn vì nó không chứa query.

## 4. Request path trong Spring MVC

Spring MVC định tuyến controller dựa trên mapping, chẳng hạn:

```java
@GetMapping("/api/orders/{orderId}")
public ResponseEntity<OrderDto> findOrder(@PathVariable long orderId) {
    // Trả dữ liệu theo nghiệp vụ và chính sách phân quyền.
}
```

Đây là **mã minh họa**, không chạy độc lập: cần Spring MVC, `OrderDto`, controller class và implementation. Với request `GET /api/orders/42`, **route pattern** do framework biết là `/api/orders/{orderId}`. Khi muốn phân tích request theo endpoint, ưu tiên pattern này thay vì gắn path `/api/orders/42` lên metric.

Trong một thành phần của Spring MVC có quyền truy cập vào Servlet request, framework có thể cung cấp route đã match qua:

```java
Object pattern = request.getAttribute(
        org.springframework.web.servlet.HandlerMapping
                .BEST_MATCHING_PATTERN_ATTRIBUTE);
String route = pattern == null ? "UNMATCHED" : pattern.toString();
```

Đây cũng là **đoạn minh họa**, không phải file Java chạy độc lập. Cần kiểm kiểu giá trị, giai đoạn dispatch và phiên bản Spring MVC đang dùng. Attribute có thể **chưa tồn tại trước khi handler được match**, chẳng hạn Filter chạy trước DispatcherServlet, hoặc với 404, error handling, security rejection xảy ra trước controller mapping.

### Ghi một event sau khi request hoàn tất

Có thể dùng `HandlerInterceptor`, Filter hoặc cơ chế observation/access logging của framework, nhưng phải xác định thời điểm hoàn tất thực tế. Với HandlerInterceptor, ý tưởng là:

```java
@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler, Exception ex) {
    Object matched = request.getAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
    String route = matched == null ? "UNMATCHED" : matched.toString();

    accessLogger.info(
            "http request completed method={} route={} status={}",
            request.getMethod(), route, response.getStatus());
}
```

Đoạn này cần class triển khai `HandlerInterceptor`, import đúng `jakarta.servlet.*` hoặc `javax.servlet.*` theo stack, `HandlerMapping` và `accessLogger`. Đây **không phải chương trình chạy độc lập**. `afterCompletion` áp dụng cho những request đi qua interceptor theo vòng đời Spring MVC; **không bao phủ mặc định mọi 404, lỗi trước routing hoặc mọi tình huống async**. Nếu yêu cầu access logging đầy đủ cả error/async dispatch, cần thiết kế một cơ chế bao phủ tương ứng, kiểm thử thực tế và tránh ghi trùng trên nhiều dispatch.

### Spring WebFlux khác Servlet MVC

Spring WebFlux dùng reactive request/exchange API; không sử dụng `HttpServletRequest` như một API bắt buộc. Đường dẫn có thể lấy từ `ServerHttpRequest`/`ServerWebExchange`, còn matched route phải lấy từ metadata của router/handler mapping theo stack. Với reactive hoặc async Java, MDC thường gắn theo thread nên không tự đi cùng request context xuyên mọi callback. Chọn cơ chế context propagation được framework hỗ trợ thay vì ghi một `ThreadLocal` rồi giả định mọi operator đều đọc đúng.

## 5. Ví dụ Java 17 chạy độc lập: chỉ log route an toàn

Ví dụ này chỉ dùng JDK 17, không cần Servlet, Spring Boot, Maven hay thư viện ngoài. Nó mô phỏng ba request đã được server xử lý, phân tích request-target bằng `java.net.URI` và tạo **JSON access log** chỉ gồm những trường giới hạn. Ngay cả khi request path chứa ID hoặc thông tin cá nhân, chương trình chỉ ghi **route template đáng tin** hoặc `UNMATCHED`; query string không được đưa vào log.

Mã nguồn minh họa **không phải router cho HTTP production**: mapping regex chỉ phục vụ demo. Trong Servlet/Spring MVC thật, hãy dùng route mà framework đã match, cùng trạng thái response thực tế.

Lưu thành file `RequestPathLoggingDemo.java`:

```java
import java.net.URI;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

public final class RequestPathLoggingDemo {
    private static final Pattern ORDER_DETAIL =
            Pattern.compile("^/api/orders/[0-9]+$");

    record Sample(
            String method, String requestTarget,
            int status, String requestId) {}

    private static String routeFor(String rawPath) {
        if (ORDER_DETAIL.matcher(rawPath).matches()) {
            return "/api/orders/{orderId}";
        }
        return "UNMATCHED";
    }

    private static String jsonString(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) ch));
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static void log(Sample sample) {
        URI parsed = URI.create(sample.requestTarget());
        String rawPath = parsed.getRawPath();
        if (rawPath == null || rawPath.isEmpty()) {
            throw new IllegalArgumentException("Missing request path");
        }

        String matchedRoute = routeFor(rawPath);

        String line = "{"
                + "\"event\":\"http.request.completed\","
                + "\"method\":" + jsonString(sample.method()) + ","
                + "\"route\":" + jsonString(matchedRoute) + ","
                + "\"status\":" + sample.status() + ","
                + "\"request_id\":" + jsonString(sample.requestId())
                + "}";

        // Không log rawPath, rawQuery hoặc token.
        System.out.println(line);
    }

    public static void main(String[] args) {
        List<Sample> requests = List.of(
                new Sample(
                        "GET",
                        "/api/orders/42?access_token=example-token",
                        200, "req-001"),
                new Sample(
                        "GET",
                        "/api/users/alice%40example.com/reset"
                                + "?token=example-token",
                        404, "req-002"),
                new Sample(
                        "POST",
                        "/api/orders/99?debug=true",
                        403, "req-003"));

        requests.forEach(RequestPathLoggingDemo::log);
    }
}
```

Biên dịch và chạy:

```bash
javac RequestPathLoggingDemo.java
java RequestPathLoggingDemo
```

**Stdout chính xác:**

```json
{"event":"http.request.completed","method":"GET","route":"/api/orders/{orderId}","status":200,"request_id":"req-001"}
{"event":"http.request.completed","method":"GET","route":"UNMATCHED","status":404,"request_id":"req-002"}
{"event":"http.request.completed","method":"POST","route":"/api/orders/{orderId}","status":403,"request_id":"req-003"}
```

Phân tích:

1. Event đầu nhận request-target có query `access_token`, nhưng `URI.getRawPath()` chỉ trả `/api/orders/42`. Route được ánh xạ thành `/api/orders/{orderId}`; ID 42 và giá trị query không xuất hiện trong log.
2. Event thứ hai có email được percent-encode trong path và token ở query. Vì không match route đã biết, detector ghi `UNMATCHED`; không lưu email hay token trong event.
3. Event thứ ba khớp cùng route template với event thứ nhất nhưng có method/status khác. Điều này giúp phân tích lỗi theo method, status và route thay vì tạo một label cho mỗi `orderId`.
4. Hàm `jsonString` escape dấu nháy, backslash và control characters để dữ liệu đi vào một JSON string; trong production nên dùng JSON encoder chuẩn của logging backend.
5. `status` và `requestId` ở ví dụ được cung cấp từ `Sample`; ứng dụng thật phải lấy từ HTTP response đã hoàn tất và một request ID tin cậy, tránh để client tự ý áp đặt trường log.
6. Demo không log duration vì không mô phỏng xử lý request thực. Khi có request thật, đo duration bằng clock thích hợp và ghi cùng event sau completion.

**Không nên dùng regex ở ví dụ để quyết định quyền truy cập hay normalize security path.** Đây chỉ là bộ ánh xạ tối giản để giải thích sự khác nhau giữa path gốc và matched route. Server và security framework quyết định route/permission theo pipeline riêng.

## 6. Thiết kế một access log event có cấu trúc

Một event cho request hoàn tất có thể mang:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "event.name": "http.request.completed",
  "service.name": "orders-api",
  "deployment.environment.name": "prod",
  "http.method": "GET",
  "http.route": "/api/orders/{orderId}",
  "http.status_code": 200,
  "duration_ms": 12.4,
  "request_id": "req-001",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

Đây là schema JSON minh họa. **Tên attribute của OpenTelemetry và cách một cloud backend ánh xạ field có thể khác theo phiên bản**; không mặc định hệ thống log nhận `http.route` hoặc `http.status_code` như một trường đặc biệt nếu chưa cấu hình parse/encode. Cần đối chiếu schema hiện dùng trong tổ chức.

Ý nghĩa từng trường:

| Trường | Tác dụng | Lưu ý |
| --- | --- | --- |
| `timestamp` | Thời điểm event được phát hoặc request hoàn tất | UTC/offset nhất quán; phân biệt ingest timestamp |
| `event.name` | Loại sự kiện log ổn định | Ví dụ `http.request.completed` |
| `http.method` | Phân loại thao tác | Giá trị method phải lấy từ request thật; có thể có method không chuẩn |
| `http.route` | Endpoint template đã match | Dùng bounded fallback khi không match |
| `http.status_code` | Kết quả giao thức | Lấy status cuối; status 200 chưa chứng minh nghiệp vụ thành công |
| `duration_ms` | Thời gian xử lý request | Đo bằng monotonic clock; đơn vị rõ ràng |
| `request_id` | Tìm log theo request | Tạo/xác minh ở ingress tin cậy; có thể propagate |
| `trace_id` / `span_id` | Nối log với distributed tracing | Truyền context đúng; span hiện hành khác request ID |
| `service.name` / environment | Phân biệt service, môi trường | Gắn metadata từ deployment tin cậy |

Không buộc mọi access log chứa username, email, IP hoặc toàn bộ headers. Các trường bổ sung cần có mục đích cụ thể, phân loại dữ liệu và retention thích hợp. Nếu route template đã chứa một đoạn ID động theo framework, không copy giá trị động thành metric label.

### Path có thể vẫn cần trong một số điều tra

Có trường hợp cần biết khách hàng đã yêu cầu path nào để phân tích 404, kiểm tra lỗi rewrite ở gateway hoặc điều tra dấu hiệu path traversal. Không có nghĩa phải **ghi raw path vào mọi event**. Có thể thiết kế:

- Event access log mặc định chỉ lưu `http.route` hoặc `UNMATCHED`.
- Kênh forensic/debug có quyền hạn riêng lưu path **đã giới hạn, escape, kiểm tra dữ liệu nhạy cảm và có retention ngắn**.
- Với lỗi routing, ghi mã lỗi, tên rule, request ID và metadata ingress, sau đó truy vấn hệ thống gateway/WAF bằng ID để xem bằng chứng phù hợp.
- Với các endpoint có token hoặc email trong path, cần sửa cả thiết kế API khi có thể: truyền dữ liệu bí mật qua cơ chế thích hợp thay vì nằm trong URL hoặc path; ngay cả proxy, browser history và analytics có thể đã lưu chúng.

**Redaction không có tính chất hoàn hảo nếu chỉ dùng một regex che “token”**. Token có thể xuất hiện trong segment không tên, dạng mã hóa khác hoặc đường dẫn tùy ý. Ưu tiên allowlist trường và route template, kết hợp các bộ lọc tại tầng thu thập.

## 7. Thứ tự middleware/filter và logging đúng một lần

Một request có thể qua nhiều lớp:

```text
Client
  -> CDN / WAF / API gateway / reverse proxy
  -> Servlet container / reactive server
  -> Authentication / authorization filters
  -> Router / controller
  -> Exception handler / response processing
  -> access log / exporter
```

Nếu logging chạy **trước routing**, nó thường chưa biết route template. Nếu ghi log ở controller, những request 404 hoặc 401/403 bị từ chối trước controller có thể không được ghi. Nếu ghi trong nhiều filter và interceptor, một request có thể tạo hai hoặc ba dòng access log có cùng ý nghĩa.

Cần xác định:

1. **Thời điểm bắt đầu:** chụp monotonic time ở điểm ingress phù hợp nếu cần latency.
2. **Thời điểm hoàn tất:** ghi khi response đã thực sự hoàn tất theo hợp đồng framework, đặc biệt async servlet, streaming response hoặc WebFlux.
3. **Tập request được bao phủ:** matched route, 404, authentication failure, exception, redirect, timeout và rejected requests.
4. **Correlation:** nếu gateway và service đều ghi access log, dùng request ID/trace ID để nối và phân biệt nguồn, không tự coi nhiều dòng là duplicate bug.
5. **Một event cho một request tại từng tầng:** định nghĩa event name/phase rõ; nếu ghi start và completion thì hai event phải khác loại, không đếm chúng như hai request.
6. **Async/error dispatch:** filter có thể được kích hoạt ở nhiều dispatch; framework có hook riêng và một request có thể hoàn tất ngoài thread ban đầu. Kiểm thử tránh ghi trùng/mất event.
7. **Đồng bộ context:** với thread pool hoặc reactive chain, `MDC`/`ThreadLocal` không tự đi theo mọi luồng; dọn/khôi phục context sau request.

Có thể lưu request ID trong MDC để mỗi log của cùng request dễ truy vấn. Với thread-bound request, dùng `try/finally` hoặc cơ chế scope được framework hỗ trợ để xóa MDC sau khi xử lý. Tuy nhiên một MDC entry là dữ liệu quan sát, không phải nguồn xác thực cho phân quyền.

## 8. Reverse proxy, API gateway và forwarded headers

Một proxy có thể thay đổi path trước khi gửi đến ứng dụng. Ví dụ:

```text
External:  https://api.example.test/public/orders/42
Gateway:   strip /public
Internal:  http://orders-service/api/orders/42
Route:     /api/orders/{orderId}
```

Nếu log từ backend chỉ ghi `/api/orders/42`, nó có thể khác đường dẫn mà client nhìn thấy. Nếu log từ gateway ghi `/public/orders/42`, lại có thêm một góc quan sát khác. Hai giá trị đều có thể đúng theo **vị trí phát log**. Cần phân biệt đường dẫn ở edge và đường dẫn nội bộ, không tự kết luận một trong hai bị lỗi.

Các header như `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` hoặc `X-Forwarded-Prefix` thường được dùng để truyền thông tin từ proxy. Nhưng client bên ngoài có thể gửi các header giả nếu ranh giới proxy không xóa/thay thế chúng. **Chỉ tin forwarded headers từ danh sách proxy/cấu hình mạng được phép**, theo cơ chế framework/container, và phân biệt path từ header với path server thực sự route.

Tránh dựng full URL bằng các header chưa xác thực rồi ghi vào log, tạo link điều tra hoặc đưa vào redirect. Host header cũng là đầu vào có thể bị điều khiển. Nếu cần địa chỉ public-facing, nên dùng cấu hình canonical external URL hoặc thông tin từ trusted gateway.

Để phát hiện lỗi rewrite, kết hợp event của gateway và ứng dụng bằng trace/request ID cùng metadata về chặng, sau đó so sánh route hoặc path theo chính sách dữ liệu. Đừng chuyển mọi path client-supplied thành labels cho metrics.

## 9. Request path và các lỗi bảo mật thường gặp

### Query string chứa token, mật khẩu hoặc PII

Ví dụ các pattern nguy hiểm nếu log nguyên:

```text
/reset-password?token=...
/login?password=...
/users?email=...
/oauth/callback?code=...
```

Ngay cả khi ứng dụng bỏ query khỏi log, reverse proxy hoặc access log ở tầng trước có thể vẫn giữ full URL. Cần kiểm **mọi điểm ghi**: gateway, load balancer, WAF, servlet access log, application log, tracing attributes, APM agent và cloud collector. Không coi chính sách ở một lớp là đủ cho toàn hệ thống.

### Dữ liệu nhạy cảm trong path segment

Path như `/users/alice@example.com/profile` có thể lộ danh tính. `/invites/{secret}` hoặc `/download/{signedToken}` đặc biệt cần tránh raw path logging. Nếu cần điều tra, log matched route, mã loại sự kiện và ID nội bộ không bí mật.

### CRLF/log injection

Client có thể gửi một path chứa percent-encoded control characters hoặc chuỗi cố tình giống bản ghi hệ thống. Nếu ứng dụng decode rồi nối trực tiếp vào text log, payload có thể làm sai ranh giới dòng log. Dùng JSON encoder chuẩn để escape, tránh chấp nhận tùy tiện newline/control chars, giới hạn kích thước và validate event schema. **Escape giúp bảo vệ định dạng; nó không xác thực nguồn dữ liệu.**

### Encoded slash, traversal và double encoding

Một URL `/files/%2e%2e/private` có thể được proxy và backend diễn giải khác nhau. Đừng tự normalize một chuỗi để “làm đẹp log” rồi dùng chính giá trị đó làm quyết định security hoặc bằng chứng duy nhất. Giữ event bảo mật riêng ghi kết quả kiểm tra quyền, route/handler xử lý và mã lý do từ thành phần tin cậy. Nếu cần raw evidence, lưu có giới hạn và phân quyền phù hợp.

### 404 và path tùy ý gây cardinality cao

Một attacker hoặc scanner có thể thử hàng nghìn path không tồn tại. Nếu mỗi path trở thành metric label, số series có thể bùng nổ. Với metrics, dùng route `UNMATCHED` hoặc phân loại bounded `NOT_FOUND`; lưu event điều tra có kiểm soát ở kênh riêng nếu thực sự cần xem từng path. Rate limiting, sampling có chính sách và giới hạn payload bảo vệ pipeline logging khỏi quá tải; **không âm thầm drop các sự kiện bảo mật bắt buộc**.

## 10. Request path trong metrics và distributed tracing

Không nên coi mọi trường trong log đều thích hợp làm **metric label**. Log store thường hỗ trợ tìm kiếm nhiều giá trị khác nhau, trong khi hệ thống time-series metrics chịu chi phí lớn khi cardinality tăng.

Ví dụ:

```text
Không nên:
  http_requests_total{path="/api/orders/42"}
  http_requests_total{path="/api/orders/43"}
  http_requests_total{path="/api/orders/44"}
  ...

Nên:
  http_requests_total{route="/api/orders/{orderId}",method="GET",status="200"}
```

Đây là mô hình minh họa; cú pháp nhãn và tên metric tùy hệ thống observability. Khi không có route matched, sử dụng giá trị bounded như `UNMATCHED` hoặc `UNKNOWN`, không dùng raw URI chứa ID tùy ý.

Trong OpenTelemetry, semantic convention về HTTP có attribute đại diện route template và các thành phần URL. **Tên attribute và hành vi instrumentation có thể đổi theo phiên bản**, nên cần kiểm SDK/agent thật và schema backend thay vì hardcode tất cả tên cũ. Tránh bật collection query string hoặc raw path nhạy cảm chỉ để tiện debug mà không đánh giá privacy.

Distributed tracing nên gắn `trace_id`/`span_id` với access log để xem các span đi qua service. Một trace có nhiều span; request ID có thể do gateway tạo; hai loại ID không đồng nhất. Trace sampling có thể khiến trace không được lưu, nhưng access log vẫn có thể cần lưu theo chính sách riêng.

## 11. Đo request latency và status cùng route

Path có giá trị hơn khi đi cùng **status và thời gian thực thi**. Để tìm endpoint chậm, nên có:

```text
event=http.request.completed
method=GET
route=/api/orders/{orderId}
status=503
duration_ms=245.6
request_id=req-001
```

Đây chỉ là output minh họa. Với Java, `System.nanoTime()` thích hợp đo elapsed time trong cùng JVM:

```java
long started = System.nanoTime();
try {
    // Xử lý request.
} finally {
    long elapsedNanos = System.nanoTime() - started;
    double durationMs = elapsedNanos / 1_000_000.0;
    // Ghi durationMs cùng method, matched route và response status.
}
```

Đoạn trên **không chạy độc lập**, cần đặt trong request processing code. Dùng `Instant.now()` cho thời điểm sự kiện, không dùng chênh lệch hai đồng hồ wall-clock để đo elapsed time nếu có thể bị điều chỉnh giờ.

**Chú ý async:** nếu một request trả về control ngay nhưng response còn được gửi bởi async handler/stream, `finally` ở filter ban đầu có thể chạy trước lúc request thực sự kết thúc. Cần dùng callback/hook completion đúng với framework và định nghĩa rõ latency là server handler time hay end-to-end response time. Không coi thời điểm gọi controller return luôn là thời điểm client nhận đủ dữ liệu.

HTTP status 200 chưa chắc hành động nghiệp vụ thành công; nhiều API trả lỗi trong body. Nếu muốn phát hiện lỗi nghiệp vụ, ghi thêm business outcome/error code có schema riêng. Ngược lại, các status 401/403 trước route match vẫn cần log theo chính sách bảo mật.

## 12. Kiểm thử request path logging

Một bài test tốt kiểm đúng **phần nào được ghi** và **phần nào tuyệt đối không được ghi**. Các kịch bản đáng có:

| Kịch bản | Giá trị cần xác nhận |
| --- | --- |
| GET `/api/orders/42` | Route template `/api/orders/{orderId}`, method GET, status cuối |
| GET `/api/orders/43?token=secret` | Cùng route; query và token không có trong log |
| Path chứa email `/users/alice%40example.com` | Không đưa email/path nguyên bản vào log thông thường |
| 404 không match handler | Route fallback bounded; access event vẫn xuất khi chính sách yêu cầu |
| 401/403 trước controller | Không mất request vì chỉ hook vào controller |
| Exception trong handler | Status cuối/error type đúng; không ghi trùng nhiều event không chủ đích |
| Async request | Completion event chỉ phát khi request thật sự hoàn tất |
| Error dispatch/retry | Không ghi trùng cùng request event do nhiều dispatch nội bộ |
| Nhiều request song song | Request ID/MDC không rò rỉ giữa thread |
| Reverse proxy rewrite prefix | Log route nội bộ đúng và có cách đối chiếu edge theo request ID |
| Encoded `%2F`, `%2e`, Unicode, newline | Không làm parser log sai, routing/security theo container |
| Query có access token, signed URL | Token không xuất hiện ở app/gateway/APM logs ngoài policy |
| Nhiều path động | Metric cardinality không tăng theo ID; route labels bounded |

Với Spring MVC, có thể dùng integration test ở tầng `MockMvc` hoặc server thực để kiểm mapping, interceptor/filter, exception handler, async và header forwarding. Với WebFlux, dùng test harness reactive tương ứng. Unit test chỉ kiểm formatter/route extraction không chứng minh toàn bộ pipeline logging hoạt động đúng khi được deploy.

Nếu dùng async appender hoặc collector, đợi event bằng điều kiện và timeout hợp lý, không dựa vào `Thread.sleep(1000)` để khẳng định log đã được chuyển xong. Đối chiếu event ID/request ID và số lượng để phát hiện thiếu hoặc trùng.

### Trình tự tự chẩn đoán một trường hợp log sai path

1. **Chụp ví dụ an toàn:** method, status, request ID, route, ingress/service name và thời điểm.
2. **Xác định nơi ghi:** reverse proxy, servlet container, access logger, controller hay tracing agent; cùng một request có thể tạo nhiều event.
3. **Kiểm giai đoạn:** route đã được match chưa? Event được ghi trong filter trước routing, afterCompletion hay async callback?
4. **Đối chiếu dạng path:** raw request URI, context path, servlet mapping, query string và external rewrite ở gateway — chỉ truy cập raw evidence khi được phép.
5. **Kiểm cấu hình bảo mật:** encoder có escape, redaction được áp dụng ở tất cả tầng và forwarded headers có trusted proxy boundary chưa?
6. **Kiểm chất lượng dữ liệu:** có token lộ, labels cardinality cao, event thiếu status/duration hoặc mất request ID không?
7. **Kiểm kết quả ở đích:** log đã vào backend đúng service, môi trường, schema và retention chưa; dashboard có lọc theo route template được không?

## 13. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Log nguyên `request.getQueryString()` | Dễ lộ token/password/PII | Mặc định không log query; allowlist rất hẹp nếu cần |
| Tin rằng `getRequestURI()` luôn an toàn | Path segment vẫn có thể chứa bí mật/PII | Dùng matched route; raw path ở kênh kiểm soát |
| Dùng path thật cho metric label | Cardinality tăng theo mọi ID | Dùng route template/fallback bounded |
| Log trong controller nhưng bỏ 404/401 | Không thấy request bị từ chối trước mapping | Thiết kế hook bao phủ các điểm lỗi phù hợp |
| Log trong filter trước routing và đòi route ngay | Matched pattern chưa có | Lấy pattern sau routing hoặc fallback |
| Ghi cả gateway và app thành cùng event không phân biệt | Đếm trùng HTTP requests | Gắn layer/service/event phase, correlation ID |
| Dùng `URLDecoder` để chuẩn hóa URI path | Xử lý dấu `+` và encoded slash sai | Dựa vào URI parser/framework/router phù hợp |
| Tin `X-Forwarded-*` từ mọi client | Có thể giả mạo host, proto hoặc prefix | Chỉ chấp nhận qua trusted proxy |
| Đưa path/user input trực tiếp vào text log | CRLF/log injection, parser hỏng | JSON encoder, validation và size limit |
| Đọc MDC từ thread pool mà không cleanup | Request ID bị rò sang request khác | Context propagation và `finally`/scope |
| Đo thời gian bằng wall-clock hoặc trước khi async hoàn thành | Latency sai | Monotonic clock và lifecycle completion phù hợp |
| Ghi status trước exception handler | Status khác response cuối | Đọc status ở giai đoạn completion |
| Tự gán route bằng regex log và dùng để authorize | Bất đồng với HTTP router | Lấy route/security decision từ framework đáng tin |
| Chỉ kiểm console trên local | Không thấy parser/cloud ingest lỗi | Test từ ứng dụng đến log backend theo schema |

## 14. Checklist triển khai cho web service Java

- [ ] Phân biệt rõ **URL, URI path, query, route template, path variable, context path**?
- [ ] Access log dùng `http.route`/route pattern thay vì raw path khi không cần raw evidence?
- [ ] Không ghi query string, token, email hoặc secret trong path/headers vào log thông thường?
- [ ] Nếu phải lưu raw path để điều tra, đã có redaction, escape, giới hạn độ dài, quyền truy cập và retention riêng?
- [ ] Servlet/Spring MVC/WebFlux đang lấy đúng thông tin từ framework và đúng thời điểm route match?
- [ ] Filter/interceptor bao phủ 404, 401/403, exception và async theo yêu cầu, không tạo duplicate event?
- [ ] Request ID/trace ID được tạo hoặc kiểm chứng tại ingress tin cậy và propagate đúng qua thread/task?
- [ ] Proxy rewrite và forwarded headers đã có ranh giới tin cậy, không cho client giả mạo metadata?
- [ ] Metrics gắn route template với số giá trị hữu hạn, không dùng user ID/raw path làm label?
- [ ] Đã kiểm lỗi encoded path, CRLF injection, Unicode và path chứa PII?
- [ ] Latency dùng monotonic clock; status được lấy sau khi request hoàn tất?
- [ ] Đã kiểm event thật ở log backend và chắc chắn các trường nhạy cảm không bị agent/gateway ghi ngoài ý muốn?

**Ghi nhớ:** với logging web Java, “request path” là một nguồn ngữ cảnh quan trọng nhưng cũng có thể chứa dữ liệu nhạy cảm và giá trị động. **Để log request phục vụ vận hành, hãy ưu tiên route template + method + status + duration + correlation ID**; tách query/raw path khỏi luồng log mặc định, thu thập theo chính sách bảo mật khi thực sự cần và luôn lấy matched route từ framework ở thời điểm thích hợp. Việc phân biệt path bên ngoài gateway với route nội bộ giúp log chính xác, dễ phân tích và an toàn hơn.
