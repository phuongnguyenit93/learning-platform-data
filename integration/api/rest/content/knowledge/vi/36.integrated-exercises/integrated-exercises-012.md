# Thực hành tổng hợp: Gọi API từ client Java và trình duyệt để kiểm tra CORS, lỗi

## 1. Mục tiêu và bài nộp

Một API REST có thể trả kết quả đúng khi gọi bằng Java `HttpClient` hoặc `curl` nhưng lại thất bại trong trình duyệt. Nguyên nhân thường nằm ở chính sách **Cross-Origin Resource Sharing (CORS)**, yêu cầu `OPTIONS` kiểm tra trước (*preflight*), xác thực hoặc cách client phân loại lỗi. Bài thực hành này yêu cầu chạy cùng một hợp đồng API qua **hai môi trường client** để biết chính xác lỗi phát sinh ở đâu và cách xử lý.

Đây là bài **Thực hành tổng hợp** thuộc module **INTEGRATION_API_REST**: vận dụng resource, URI, phương thức và mã trạng thái HTTP, hợp đồng dữ liệu, xử lý lỗi, xác thực/phân quyền, kiểm thử API; kết nối với các khái niệm cache, idempotency và retry đã học. Trọng tâm là tích hợp Java/Spring với ứng dụng trình duyệt, không xây dựng một hệ thống thương mại điện tử hoàn chỉnh.

Sau bài học, người học có thể:

1. Gọi `GET`, `POST` qua Java `HttpClient` và `fetch`, đọc status, header, body kể cả khi mã trạng thái là lỗi.
2. Phân biệt **lỗi HTTP**, **lỗi mạng**, **lỗi phân tích JSON**, **lỗi timeout** và **yêu cầu bị trình duyệt chặn bởi CORS**.
3. Giải thích khi nào trình duyệt gửi `OPTIONS`, cách cấu hình CORS theo origin/method/header và cách xem kết quả trong DevTools.
4. Xử lý `400`, `401`, `403`, `404`, `422`, `429`, `500` theo hợp đồng; không thử lại bừa bãi các yêu cầu có tác dụng phụ.
5. Thiết kế bảng kiểm thử đối chiếu Java, trình duyệt và server trước khi phát hành API.

**Bài nộp** gồm: mã client Java; mã trang thử nghiệm với `fetch`; ảnh hoặc bản ghi DevTools Network cho `GET`, `POST` và preflight; bảng test case có kết quả mong đợi/thực tế; phần giải thích tối thiểu ba lỗi được cố ý gây ra và cách sửa.

## 2. Hợp đồng API dùng trong phòng thực hành

Giả sử một API quản lý đơn hàng thử nghiệm chạy ở `http://localhost:8080`, còn trang HTML chạy ở `http://localhost:5500`. Hai địa chỉ này có **khác origin** vì khác port, dù cùng máy.

| Phương thức và URI | Điều kiện | Kết quả kỳ vọng |
| --- | --- | --- |
| `GET /api/lab/orders/100` | Đơn có sẵn | `200 OK`, JSON đơn hàng |
| `GET /api/lab/orders/9999` | Đơn không tồn tại | `404 Not Found`, `application/problem+json` |
| `POST /api/lab/orders` | JSON có `sku` và `quantity > 0` | `201 Created`, `Location`, JSON đơn mới |
| `POST /api/lab/orders` | `quantity <= 0` hoặc `sku` rỗng | `422 Unprocessable Content`, Problem Details |
| `POST /api/lab/orders` | Body JSON sai cú pháp | `400 Bad Request`, Problem Details |
| `GET /api/lab/orders/100` + `X-Lab-Failure: 401` | Mô phỏng xác thực thất bại | `401 Unauthorized`, `WWW-Authenticate: Bearer` |
| `GET /api/lab/orders/100` + `X-Lab-Failure: 403` | Mô phỏng thiếu quyền | `403 Forbidden` |
| `GET /api/lab/orders/100` + `X-Lab-Failure: 429` | Mô phỏng giới hạn tốc độ | `429 Too Many Requests`, `Retry-After: 2` |
| `GET /api/lab/orders/100` + `X-Lab-Failure: 500` | Mô phỏng lỗi server | `500 Internal Server Error` |

Header `X-Lab-Failure` là **công tắc gây lỗi phục vụ học tập**, không phải cơ chế xác thực/phân quyền và tuyệt đối không đưa vào API thật. Trong hệ thống thật, `401`/`403` phải xuất phát từ tầng bảo mật và chính sách quyền; `429` phải xuất phát từ bộ giới hạn yêu cầu. Server mẫu giữ đơn trong bộ nhớ, dữ liệu sẽ mất khi khởi động lại.

### Quy ước response

Ví dụ thành công:

~~~http
GET /api/lab/orders/100 HTTP/1.1
Host: localhost:8080
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"id":100,"sku":"BOOK-JAVA","quantity":2,"status":"draft"}
~~~

Ví dụ lỗi nghiệp vụ:

~~~http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json

{"type":"about:blank","title":"Unprocessable Entity","status":422,
 "detail":"sku không được rỗng và quantity phải lớn hơn 0",
 "code":"INVALID_ORDER"}
~~~

Trong thiết kế thực tế, `type` thường là URI tài liệu định nghĩa lỗi; bài thực hành dùng cấu trúc tối giản của `ProblemDetail`. Client dựa trên **status HTTP** để nhận diện nhóm lỗi và `code` để hiển thị hành động nghiệp vụ phù hợp; không tự đoán bằng chuỗi `detail` vốn có thể thay đổi.

## 3. Dựng API thử nghiệm bằng Spring Boot

Tạo project Spring Boot 3.x hoặc phiên bản tương thích, Java 17 trở lên, với dependency **Spring Web**. Đặt class dưới đây trong source root của package `lab.cors`, ví dụ `src/main/java/lab/cors/CorsLabApplication.java`. Trong `application.properties` đặt `server.address=127.0.0.1` và `server.port=8080` để dịch vụ thử nghiệm chỉ lắng nghe trên máy local.

~~~java
package lab.cors;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class CorsLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsLabApplication.class, args);
    }

    @Bean
    WebMvcConfigurer corsPolicy() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/lab/**")
                    .allowedOrigins("http://localhost:5500")
                    .allowedMethods("GET", "POST", "OPTIONS")
                    .allowedHeaders(
                        "Content-Type", "Authorization", "X-Lab-Failure")
                    .exposedHeaders(
                        "Location", "Retry-After", "WWW-Authenticate")
                    .maxAge(600);
            }
        };
    }

    @RestController
    @RequestMapping("/api/lab/orders")
    static class OrdersController {
        record CreateOrder(String sku, Integer quantity) {}
        record Order(long id, String sku, int quantity, String status) {}

        private final AtomicLong ids = new AtomicLong(100);
        private final Map<Long, Order> orders = new ConcurrentHashMap<>();

        OrdersController() {
            orders.put(100L, new Order(100, "BOOK-JAVA", 2, "draft"));
        }

        @GetMapping("/{id}")
        ResponseEntity<?> get(
            @PathVariable long id,
            @RequestHeader(name = "X-Lab-Failure", required = false)
                String simulatedFailure
        ) {
            // Chỉ dùng để quan sát các nhánh lỗi từ client.
            if ("401".equals(simulatedFailure)) {
                return fail(HttpStatus.UNAUTHORIZED,
                    "AUTH_REQUIRED", "Thiếu hoặc hết hạn token");
            }
            if ("403".equals(simulatedFailure)) {
                return fail(HttpStatus.FORBIDDEN,
                    "PERMISSION_DENIED", "Người gọi không có quyền");
            }
            if ("429".equals(simulatedFailure)) {
                return fail(HttpStatus.TOO_MANY_REQUESTS,
                    "RATE_LIMITED", "Thử lại sau");
            }
            if ("500".equals(simulatedFailure)) {
                return fail(HttpStatus.INTERNAL_SERVER_ERROR,
                    "SERVER_ERROR", "Hệ thống tạm thời gặp lỗi");
            }
            Order order = orders.get(id);
            if (order == null) {
                return fail(HttpStatus.NOT_FOUND,
                    "ORDER_NOT_FOUND", "Không tìm thấy đơn");
            }
            return ResponseEntity.ok(order);
        }

        @PostMapping
        ResponseEntity<?> create(@RequestBody CreateOrder input) {
            if (input.sku() == null || input.sku().isBlank()
                || input.quantity() == null || input.quantity() <= 0) {
                return fail(HttpStatus.UNPROCESSABLE_ENTITY,
                    "INVALID_ORDER",
                    "sku không được rỗng và quantity phải lớn hơn 0");
            }
            long id = ids.incrementAndGet();
            Order result = new Order(
                id, input.sku(), input.quantity(), "draft");
            orders.put(id, result);
            return ResponseEntity
                .created(URI.create("/api/lab/orders/" + id))
                .body(result);
        }

        static ResponseEntity<ProblemDetail> fail(
            HttpStatus status, String code, String detail
        ) {
            ProblemDetail payload =
                ProblemDetail.forStatusAndDetail(status, detail);
            payload.setProperty("code", code);
            var response = ResponseEntity.status(status)
                .contentType(MediaType.parseMediaType(
                    "application/problem+json"));
            if (status == HttpStatus.UNAUTHORIZED) {
                response.header("WWW-Authenticate", "Bearer");
            }
            if (status == HttpStatus.TOO_MANY_REQUESTS) {
                response.header("Retry-After", "2");
            }
            return response.body(payload);
        }
    }

    @RestControllerAdvice
    static class BadJsonAdvice {
        @ExceptionHandler(HttpMessageNotReadableException.class)
        ResponseEntity<ProblemDetail> malformedJson(
            HttpMessageNotReadableException exception
        ) {
            return OrdersController.fail(HttpStatus.BAD_REQUEST,
                "MALFORMED_JSON", "Body JSON không đúng cú pháp hoặc kiểu");
        }
    }
}
~~~

Chạy ứng dụng bằng cách khởi động class `CorsLabApplication` trong IDE, hoặc dùng `mvn spring-boot:run` trong project có cấu hình Maven tương ứng. Kiểm tra:

~~~powershell
curl.exe -i http://localhost:8080/api/lab/orders/100
curl.exe -i http://localhost:8080/api/lab/orders/9999
~~~

Lưu ý khi tích hợp **Spring Security**: preflight `OPTIONS` thường không mang token nên tầng bảo mật phải xử lý CORS trước khi yêu cầu xác thực. Cấu hình ở trên là Spring MVC khi ứng dụng chỉ có Spring Web; trong project dùng Spring Security, kích hoạt hỗ trợ CORS trên `SecurityFilterChain`, ví dụ `http.cors(Customizer.withDefaults())`, đồng thời đảm bảo security lấy đúng CORS policy. Không vô hiệu hóa CSRF hàng loạt nếu ứng dụng dùng cookie/session. Nếu sử dụng bearer token trong header `Authorization`, hãy kiểm tra cả quy tắc bảo mật của endpoint thật, thay cho công tắc giả lập của phòng lab.

## 4. Client Java: đọc status, header và body

Tạo class `ClientLab.java` chạy với JDK 17 hoặc mới hơn. Java `HttpClient` sử dụng HTTP trực tiếp; **nó không tự thi hành cơ chế chặn CORS của trình duyệt**. Vì vậy cùng một URI có thể chạy từ Java và bị chặn khi gọi bằng `fetch`.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class ClientLab {
    static final String BASE = "http://localhost:8080/api/lab/orders";

    static HttpRequest.Builder request(String path) {
        return HttpRequest.newBuilder(URI.create(BASE + path))
            .timeout(Duration.ofSeconds(5))
            .header("Accept", "application/json, application/problem+json");
    }

    static void send(HttpClient client, HttpRequest request) {
        try {
            HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
            int status = response.statusCode();
            String contentType = response.headers()
                .firstValue("Content-Type").orElse("");
            System.out.println("\n" + request.method() + " "
                + request.uri() + " => " + status);
            System.out.println("Content-Type: " + contentType);
            System.out.println("Location: " + response.headers()
                .firstValue("Location").orElse("(không có)"));
            System.out.println("Retry-After: " + response.headers()
                .firstValue("Retry-After").orElse("(không có)"));
            if (status >= 400) {
                System.out.println("HTTP error; body: "
                    + response.body());
            } else {
                System.out.println("Success; body: "
                    + response.body());
            }
        } catch (HttpTimeoutException ex) {
            System.out.println("TIMEOUT: hết thời gian chờ kết quả");
        } catch (IOException ex) {
            System.out.println("NETWORK: " + ex.getClass().getSimpleName());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.out.println("INTERRUPTED: yêu cầu bị gián đoạn");
        }
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        send(client, request("/100").GET().build());
        send(client, request("/9999").GET().build());

        send(client, request("")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(
                "{\"sku\":\"BOOK-JAVA\",\"quantity\":2}"))
            .build());

        send(client, request("")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(
                "{\"sku\":\"BOOK-JAVA\",\"quantity\":0}"))
            .build());

        send(client, request("/100")
            .header("X-Lab-Failure", "429")
            .GET().build());
    }
}
~~~

Ví dụ dùng cách khai báo tương thích JDK 17. Kể từ JDK 21, `HttpClient` hỗ trợ `AutoCloseable` và có thể dùng `try-with-resources` để quản lý vòng đời client. Trong ứng dụng thật, nên chia sẻ một instance `HttpClient` thay vì khởi tạo mới cho mỗi request.

Điểm cần quan sát:

- `404`, `422`, `429` là **HTTP response nhận thành công ở tầng giao vận**. `client.send` không tự ném exception chỉ vì status là 4xx hoặc 5xx.
- `IOException` thường liên quan kết nối, DNS, TLS hoặc mạng; `HttpTimeoutException` chỉ ra timeout cụ thể; `InterruptedException` cần khôi phục cờ interrupt.
- Không log giá trị token, cookie, thông tin khách hàng; ví dụ chỉ in response của API thử nghiệm.
- Nếu làm client sản xuất, hãy parse `application/problem+json` thành DTO lỗi có `status`, `code`, `detail` và thiết lập chính sách retry, không dùng `contains("error")` trên body.

## 5. Client trình duyệt: `fetch`, CORS và Problem Details

Tạo `index.html` trong một thư mục tạm và phục vụ file qua web server, ví dụ công cụ Live Server của VS Code trên **`http://localhost:5500`**. Có thể dùng `npx http-server . -p 5500 -c-1` trong thư mục HTML nếu máy có Node.js. Không mở HTML trực tiếp bằng `file://` vì khi đó origin có thể là `null` và phép thử không còn đúng cấu hình.

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>REST Client / CORS Lab</title>
</head>
<body>
  <h1>Thử REST API từ trình duyệt</h1>
  <p>Frontend: localhost:5500 — API: localhost:8080</p>
  <div>
    <button data-test="ok">GET 200</button>
    <button data-test="missing">GET 404</button>
    <button data-test="create">POST 201</button>
    <button data-test="invalid">POST 422</button>
    <button data-test="badJson">POST 400</button>
    <button data-test="unauthorized">GET 401</button>
    <button data-test="forbidden">GET 403</button>
    <button data-test="rate">GET 429</button>
    <button data-test="server">GET 500</button>
  </div>
  <pre id="result" aria-live="polite"></pre>

  <script>
    const BASE = "http://localhost:8080/api/lab/orders";
    const result = document.querySelector("#result");
    const cases = {
      ok: {path: "/100"},
      missing: {path: "/9999"},
      create: {method: "POST", body: {sku: "BOOK-JAVA", quantity: 2}},
      invalid: {method: "POST", body: {sku: "BOOK-JAVA", quantity: 0}},
      badJson: {method: "POST", body: "{broken"},
      unauthorized: {path: "/100", failure: "401"},
      forbidden: {path: "/100", failure: "403"},
      rate: {path: "/100", failure: "429"},
      server: {path: "/100", failure: "500"}
    };

    function display(data) {
      // textContent hiển thị dữ liệu như văn bản, không thực thi HTML từ API.
      result.textContent = JSON.stringify(data, null, 2);
    }

    async function run(test) {
      const {path = "", method = "GET", body, failure} = test;
      const headers = {"Accept": "application/json, application/problem+json"};
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (failure) headers["X-Lab-Failure"] = failure;

      const options = {method, mode: "cors", credentials: "omit", headers};
      if (body !== undefined) {
        options.body = typeof body === "string" ? body : JSON.stringify(body);
      }
      const abort = new AbortController();
      options.signal = abort.signal;
      const timer = setTimeout(() => abort.abort(), 5000);
      display({state: "loading", method, path});

      try {
        const response = await fetch(BASE + path, options);
        const contentType = response.headers.get("Content-Type") || "";
        const raw = response.status === 204 || response.status === 304
          ? "" : await response.text();
        let payload = raw;
        if (raw && contentType.includes("json")) {
          try {
            payload = JSON.parse(raw);
          } catch (parseError) {
            display({kind: "BAD_RESPONSE_JSON",
              status: response.status, raw});
            return;
          }
        }
        display({
          kind: response.ok ? "SUCCESS" : "HTTP_ERROR",
          status: response.status,
          location: response.headers.get("Location"),
          retryAfter: response.headers.get("Retry-After"),
          wwwAuthenticate: response.headers.get("WWW-Authenticate"),
          payload
        });
      } catch (error) {
        if (error.name === "AbortError") {
          display({kind: "TIMEOUT_OR_ABORT", message: error.message});
        } else {
          display({
            kind: "FETCH_REJECTED",
            message: error.message,
            action: "Kiểm tra Console và Network để phân biệt CORS với mất mạng"
          });
        }
      } finally {
        clearTimeout(timer);
      }
    }

    document.querySelectorAll("button[data-test]").forEach(button => {
      button.addEventListener("click", () => run(cases[button.dataset.test]));
    });
  </script>
</body>
</html>
~~~

Ở giao diện trên, `fetch` **không reject chỉ vì server trả `401`, `404` hoặc `500`**; Promise vẫn resolve thành một `Response`, `response.ok` là `false`. Chỉ khi trình duyệt không cung cấp response cho JavaScript (ví dụ kết nối thất bại, bị CORS chặn, yêu cầu bị abort) thì `fetch` reject. Script không thể xác định chắc chắn CORS hay lỗi mạng chỉ từ `TypeError: Failed to fetch`; phải đối chiếu **DevTools Console và Network**.

Khi sửa ứng dụng thành client có bearer token thật, chỉ thêm header `Authorization: Bearer …` sau khi đã có token hợp lệ; tuyệt đối không nhúng token hoặc bí mật cố định trong file HTML công khai. Trong ví dụ hiện tại `credentials: "omit"` ngăn gửi cookie/credentials tự động; API lab không dùng cookie hay token.

## 6. Hiểu và tái hiện CORS preflight

**Origin** là bộ ba `scheme + host + port`. Chẳng hạn `http://localhost:5500` khác `http://localhost:8080`, `http://127.0.0.1:5500`, và `https://localhost:5500`. CORS là chính sách do **trình duyệt thực thi đối với JavaScript đọc response cross-origin**; nó không phải thay thế cho xác thực hay phân quyền ở server.

### Khi nào có `OPTIONS`?

- `GET` với các header safelisted như `Accept` thường **không cần preflight**.
- `POST` có `Content-Type: application/json` cần preflight vì đó không phải một trong các Content-Type safelisted của CORS.
- `GET` có header tùy biến `X-Lab-Failure` hoặc `Authorization` cũng cần preflight.
- `PUT`, `PATCH`, `DELETE` thường cần preflight; chỉ những phương thức/headers cho phép mới được gọi tiếp.

Ví dụ trình duyệt kiểm tra trước khi gửi `POST`:

~~~http
OPTIONS /api/lab/orders HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type

HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 600
~~~

Đây là một **minh họa**; mã phản hồi preflight có thể là `200` hoặc `204` tùy framework/cấu hình, và danh sách header/method có thể khác cách trình bày. Yêu cầu chính là trình duyệt xác nhận đủ `Access-Control-Allow-Origin`, method và các request header. Nếu preflight không thành công, browser thường **không gửi POST thực tế**.

Có thể kiểm tra trực tiếp bằng `curl.exe` (PowerShell/Windows):

~~~powershell
curl.exe -i -X OPTIONS "http://localhost:8080/api/lab/orders" -H "Origin: http://localhost:5500" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type"
curl.exe -i -X OPTIONS "http://localhost:8080/api/lab/orders/100" -H "Origin: http://localhost:5500" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: x-lab-failure"
curl.exe -i -X OPTIONS "http://localhost:8080/api/lab/orders" -H "Origin: http://localhost:5501" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type"
~~~

Lệnh cuối cố tình thay origin thành `5501` nên **không được cấp phép** theo policy của ví dụ. Tùy framework, server có thể trả `403` hoặc response không có `Access-Control-Allow-Origin` hợp lệ; điều quan trọng là trình duyệt không tiếp tục xử lý request cross-origin bị từ chối.

> `curl` có thể gửi header `Origin` để **quan sát** CORS response, nhưng bản thân `curl` vẫn có thể đọc response bị trình duyệt chặn. Gọi `curl -X OPTIONS` là một phép kiểm tra server, không thay thế được test trong browser.

### CORS không đồng nghĩa client được đọc mọi header

Ngay cả khi browser đọc được JSON body, các header như `Location`, `Retry-After`, `WWW-Authenticate` **không tự động được JavaScript nhìn thấy** nếu chưa nằm trong danh sách header được phép truy cập. Cấu hình mẫu dùng `exposedHeaders` để các nút thử nghiệm có thể hiển thị chúng. Header `Content-Type` thuộc nhóm response header được expose mặc định.

Nếu hệ thống sử dụng cookie cross-origin, phải xét đồng thời `credentials: "include"`, `Access-Control-Allow-Credentials: true`, origin cụ thể (không dùng `*`), các thuộc tính `SameSite`/`Secure` và chống CSRF. Bài này không dùng cookie. **Cho phép CORS không làm tăng quyền truy cập dữ liệu trên server**: vẫn phải kiểm tra token, scope và quyền trên từng resource.

### Luồng ra quyết định của client và trình duyệt

~~~mermaid
flowchart TD
    A["JavaScript gọi fetch() cross-origin"] --> B{"Method/header có cần preflight?"}
    B -->|Có| C["Browser gửi OPTIONS kèm Origin"]
    C --> D{"CORS policy cho phép?"}
    D -->|Không| E["Browser chặn; fetch reject"]
    D -->|Có| F["Browser gửi request thật"]
    B -->|Không| F
    F --> G{"Kết nối và CORS response hợp lệ?"}
    G -->|Không| E
    G -->|Có| H{"HTTP status?"}
    H -->|2xx| I["Đọc body thành công"]
    H -->|4xx hoặc 5xx| J["fetch resolve; kiểm tra response.ok = false"]
    J --> K["Đọc application/problem+json"]
~~~

Một status `403` trên **preflight** là lỗi chính sách cross-origin, khác với `403` trên **GET/POST thật** do server từ chối quyền nghiệp vụ. Trong trường hợp đầu, JavaScript có thể chỉ nhận `TypeError` chứ không đọc được status `403`.

## 7. Các bài thí nghiệm chẩn đoán lỗi

Mở DevTools → tab **Network** (bật lọc **Fetch/XHR** hoặc **All**) và **Console**. Với từng phép thử, ghi method, request URL, Origin, response status, các header CORS và output JavaScript. Preflight có thể được cache tối đa theo `Access-Control-Max-Age`; nếu không thấy `OPTIONS` ở lần gọi sau, không kết luận là request không cần preflight. Thử một URL/phiên mới hoặc đợi cache hết hạn nếu cần quan sát.

| Thí nghiệm | Thao tác | Dấu hiệu kỳ vọng và kết luận |
| --- | --- | --- |
| A. Same machine, khác origin | Chạy web `:5500`, API `:8080`, bấm `GET 200` | `GET 200`, có `Access-Control-Allow-Origin`; không cần `OPTIONS` nếu chỉ header safelisted |
| B. JSON preflight | Bấm `POST 201` | Thường thấy `OPTIONS` rồi `POST 201`; đọc được `Location` do đã expose |
| C. Sai nội dung nghiệp vụ | Bấm `POST 422` | `OPTIONS` thành công; `POST 422` có Problem Details và `response.ok=false` |
| D. JSON sai cú pháp | Bấm `POST 400` | Server trả `400` từ xử lý parse; client đọc được JSON lỗi |
| E. Token thiếu hoặc hết hạn giả lập | Bấm `GET 401` | Preflight do `X-Lab-Failure`, sau đó `401`; client thấy `WWW-Authenticate` |
| F. Quyền bị từ chối giả lập | Bấm `GET 403` | Preflight thành công, sau đó `403`; khác với preflight bị từ chối |
| G. Rate limit giả lập | Bấm `GET 429` | `Retry-After=2` hiển thị; không tự retry vô hạn |
| H. Lỗi server giả lập | Bấm `GET 500` | `fetch` vẫn resolve, `response.ok=false`; lỗi có body theo hợp đồng |
| I. Origin không được phép | Đổi frontend sang `http://localhost:5501` nhưng giữ policy chỉ `5500` | Console báo CORS; JavaScript không đọc được response |
| J. API không chạy | Dừng server rồi bấm `GET 200` | `fetch` reject; Network báo kết nối thất bại, không thể kết luận là lỗi CORS |
| K. Backend Java | Chạy `ClientLab` với URL `:8080` | Java đọc được status/body mà không cần CORS; khác biệt xác nhận chính sách thuộc browser |
| L. Header mới | Thêm `X-Debug-Id` vào browser request nhưng chưa cho phép trong `allowedHeaders` | Preflight bị từ chối; thêm header chính xác vào policy rồi thử lại |

**Thực nghiệm bổ sung về mã lỗi:** chạy Java client với `GET` `/9999` (404) và thử client gọi `PUT /api/lab/orders/100`. Với Java, server có thể trả `405 Method Not Allowed`. Với trình duyệt, nếu policy CORS không cho phép `PUT`, browser có thể chặn ngay ở preflight trước khi server xử lý method. Hai kết quả không mâu thuẫn vì chúng diễn ra ở các lớp khác nhau.

## 8. Cách xử lý lỗi đúng ở ứng dụng client

Trong ứng dụng thực, tách các tình huống sau thành nhánh xử lý rõ ràng:

| Nhóm | Cách nhận biết | Hành động đề xuất |
| --- | --- | --- |
| HTTP 400/422 | Có `Response`, mã lỗi, Problem Details | Gắn lỗi vào form; sửa dữ liệu; không gửi lại nguyên xi |
| HTTP 401 | Response có `401` và thường có `WWW-Authenticate` | Yêu cầu đăng nhập hoặc refresh token theo hợp đồng, giới hạn số lần thử |
| HTTP 403 | Response có `403` từ request thật | Thông báo thiếu quyền, không retry với cùng quyền |
| HTTP 404 | Resource không tồn tại/không thể nhìn thấy | Hiển thị không tìm thấy, kiểm tra ID và quyền phù hợp |
| HTTP 409/412 | Xung đột nghiệp vụ hoặc điều kiện ETag thất bại | GET lại resource, đối chiếu trạng thái rồi mới quyết định sửa |
| HTTP 429 | Response có `429`, có thể có `Retry-After` | Lùi thời điểm gọi theo header, backoff + jitter và giới hạn retry |
| HTTP 500/502/503 | Server/gateway gặp lỗi | Trả thông báo tạm thời; retry có giới hạn với thao tác an toàn |
| Timeout/abort | Java `HttpTimeoutException` hoặc JS `AbortError` | Nêu rõ trạng thái chưa biết; đối soát trước khi lặp yêu cầu ghi |
| CORS/network bị từ chối | Browser `fetch` reject, DevTools xác nhận nguyên nhân | Sửa policy server/đường kết nối; không tìm cách tắt bảo vệ CORS của browser |
| Body sai định dạng | Header báo JSON nhưng parse thất bại, hoặc schema khác contract | Ghi nhận lỗi hợp đồng, cung cấp correlation ID, không gán nhầm là 400 của client |

**Retry và idempotency:** `GET` là phương thức an toàn về mặt ngữ nghĩa nên có thể áp dụng retry giới hạn khi lỗi thoáng qua. `POST` tạo đơn trong ví dụ phòng lab **chưa có Idempotency-Key**; nếu POST timeout sau khi server đã tạo đơn, client không biết đã commit hay chưa. Không tự động retry POST đó. Trong API sản xuất, thiết kế idempotency key hoặc cơ chế tra cứu/đối soát trước khi thêm retry cho thao tác tạo mới.

**Cache:** nếu client lưu response của `GET`, phải tuân thủ `Cache-Control`, quyền và điều kiện xác thực; dữ liệu đơn của người dùng không nên được công khai qua shared cache. Phần ví dụ tập trung vào CORS/lỗi nên chưa đưa ETag và conditional requests vào API lab. Không dùng `cache: "no-cors"` (đây không phải một chế độ cache hợp lệ) hay `mode: "no-cors"` để “vượt” chặn: response `opaque` sẽ không cho JavaScript đọc status/body.

## 9. Checklist review và kiểm thử chấp nhận

Trước khi kết luận đã tích hợp xong, hoàn thành bảng sau cho cả Java và browser:

| ID | Tiêu chí | Đạt khi |
| --- | --- | --- |
| TC-01 | GET hợp lệ | Java và browser thấy `200` và JSON đúng schema |
| TC-02 | GET không tồn tại | Cả hai đọc được `404` cùng mã `ORDER_NOT_FOUND` |
| TC-03 | POST JSON hợp lệ | Có `201`, header `Location`, GET theo URL mới trả đơn vừa tạo |
| TC-04 | POST sai nghiệp vụ | `422` và `code=INVALID_ORDER`, không tạo đơn |
| TC-05 | POST JSON hỏng | `400` và `code=MALFORMED_JSON` |
| TC-06 | Request dùng header tùy biến | Browser gửi preflight và chỉ gọi request thật khi policy cho phép |
| TC-07 | Origin bị chặn | Browser không đọc body; Java vẫn có thể gọi trực tiếp |
| TC-08 | 401/403 mô phỏng | Client phân biệt tình huống và không nhầm với lỗi CORS |
| TC-09 | 429 mô phỏng | Client đọc được `Retry-After` và biết giới hạn retry |
| TC-10 | 500 mô phỏng | Client nhận HTTP error có thể hiển thị, không quy thành lỗi mạng |
| TC-11 | Server offline | Java xử lý IOException/timeout; browser xử lý rejected fetch |
| TC-12 | Phân tích JSON | Client bắt lỗi response sai JSON độc lập với HTTP status |
| TC-13 | Kiểm tra bảo mật thật | Khi tích hợp Security, token hết hạn → 401, thiếu scope → 403, quyền sở hữu resource được kiểm tra phía server |
| TC-14 | Review hợp đồng | Tên field, media type, header CORS, status và Problem Details được thống nhất giữa client/backend |

**Mẫu biên bản thực hành**:

~~~text
Environment:
  API       : http://localhost:8080
  Frontend  : http://localhost:5500
  Java      : <JDK version>
  Browser   : <browser version>
Case ID     : TC-06
Request     : POST /api/lab/orders; Content-Type: application/json
Preflight   : OPTIONS; Origin: http://localhost:5500
Observed    : <status/header của OPTIONS và POST>
Expected    : OPTIONS được chấp nhận; POST trả 201
Result      : PASS / FAIL
Evidence    : <ảnh DevTools hoặc bản ghi HAR đã loại token>
Root cause  : <nếu FAIL>
Fix / Retest: <quyết định sửa, người phụ trách, kết quả thử lại>
~~~

### Câu hỏi mở rộng

1. Vì sao `curl` trả `200` nhưng browser báo `TypeError: Failed to fetch`? Những header và dòng nào trong Network cần xem trước?
2. Vì sao preflight `OPTIONS` phải được phép đi qua cơ chế CORS ngay cả khi endpoint thật yêu cầu bearer token?
3. Khi browser thấy `403` trong Network, điều gì giúp phân biệt preflight `403` với lỗi phân quyền từ `GET` thật?
4. Tại sao `Access-Control-Allow-Origin: *` không phù hợp khi gửi cookie cross-origin?
5. Nếu response có `Location` mà JavaScript đọc `response.headers.get("Location")` nhận `null`, cần kiểm tra cấu hình gì?
6. Với POST đã gửi nhưng bị timeout, vì sao retry ngay có thể tạo đơn trùng, và API cần thêm cơ chế nào?

**Gợi ý đối chiếu:** (1) kiểm tra origin, OPTIONS, header allow và kết nối; (2) preflight không mang credential của request thật và cần được xử lý trước auth; (3) kiểm tra method của dòng lỗi và request thật có được gửi không; (4) wildcard không được dùng với credentialed CORS; (5) `Access-Control-Expose-Headers`; (6) cần idempotency key hoặc đối soát kết quả.

Khi hoàn tất, người học phải chứng minh được **cùng một HTTP contract** được Java client sử dụng ra sao và được browser cho phép hay chặn ra sao. Bản ghi DevTools, kết quả Java và ma trận lỗi sẽ là bằng chứng cho quyết định sửa CORS, hợp đồng API hoặc logic client trước khi triển khai ứng dụng thật.
