# Đường đi tổng quát từ kết nối mạng đến mã nghiệp vụ và phản hồi

## 1. Hiểu đúng phạm vi

Khi người dùng gửi một yêu cầu HTTP tới ứng dụng Spring Boot, phương thức trong `@RestController` không được gọi trực tiếp từ mạng. Yêu cầu phải đi qua lớp kết nối, máy chủ HTTP, các lớp xử lý chung của ứng dụng, bộ định tuyến của Spring, rồi mới tới mã nghiệp vụ. Kết quả sau đó được chuyển thành phản hồi HTTP và gửi ngược về phía client.

Trong module **Spring Boot - web-runtime**, cần phân biệt hai cách triển khai phổ biến:

- **Spring MVC (Servlet stack):** thường chạy trên embedded Tomcat, cũng có thể dùng Jetty hoặc máy chủ Servlet tương thích. `DispatcherServlet` là điểm điều phối request trong Spring MVC.
- **Spring WebFlux (reactive stack):** thường chạy trên Reactor Netty, nhưng cũng có thể hoạt động trên máy chủ Servlet hỗ trợ. `DispatcherHandler` đảm nhiệm điều phối ở tầng WebFlux.

Hai stack có nhiều bước logic giống nhau (route → handler → service → tạo response), nhưng giao diện xử lý HTTP và mô hình thực thi khác nhau. Phần 2–5 đi theo luồng Servlet/MVC làm ví dụ chính; phần 6 đối chiếu WebFlux.

## 2. Sơ đồ một vòng request/response

```text
Client (trình duyệt, mobile app, curl, service khác)
    │  HTTP request: method + URL + headers + body (nếu có)
    ▼
DNS / kết nối TCP / TLS khi cần
    │  Có thể đi qua reverse proxy / load balancer / API gateway
    ▼
Máy chủ HTTP nhúng (ví dụ Tomcat)
    │  Nhận, phân tích HTTP và tạo đối tượng request/response
    ▼
Servlet Filter chain
    │  Logging, CORS, security... nếu được cấu hình
    │  Có thể chặn và trả response ngay tại đây
    ▼
DispatcherServlet
    │  HandlerMapping tìm route, HandlerAdapter gọi handler
    │  Resolve tham số, chuyển kiểu, đọc body, validate khi áp dụng
    ▼
Controller (@RestController)
    ▼
Service (quy tắc nghiệp vụ)
    │
    ├── Repository / database (nếu cần)
    └── API, cache, message broker... (nếu cần)
    │
    ▼
Giá trị trả về / lỗi nghiệp vụ
    ▼
Spring MVC xử lý kết quả
    │  Quyết định status + headers; serialize JSON, render view...
    ▼
Servlet Filter chain hoàn tất → máy chủ HTTP gửi bytes
    ▼
Proxy trung gian (nếu có) → Client nhận HTTP response
```

Sơ đồ biểu diễn **thứ tự xử lý logic**, không có nghĩa mỗi request luôn mở một kết nối TCP mới, luôn đi qua proxy, luôn truy cập database hoặc nhất thiết giữ một thread duy nhất. HTTP keep-alive tái sử dụng kết nối; HTTP/2 có thể truyền đồng thời nhiều stream trên một kết nối.

## 3. Điều gì đã có sẵn trước khi request tới?

Khi gọi `SpringApplication.run(...)`, Spring Boot tạo `ApplicationContext`, tải bean/configuration, auto-configure hạ tầng web theo dependencies và cấu hình, khởi động embedded web server, đăng ký các filter, dispatcher và mapping cần thiết. Ví dụ, `spring-boot-starter-web` thường kích hoạt Spring MVC và Tomcat mặc định; ứng dụng đăng ký route từ `@RequestMapping`, `@GetMapping`, v.v.

Tại thời điểm server đã sẵn sàng nhận request, controller/service thường đã là các bean được Spring tạo và tiêm phụ thuộc. Route `GET /api/orders/{id}` không phải được dựng mới mỗi khi người dùng gọi: Spring đã biết mapping và dùng thông tin đó để tìm handler ở thời gian chạy.

Cấu hình `server.port`, context path, TLS và cổng proxy quyết định nơi request đi vào. Nếu TLS kết thúc ở reverse proxy, Tomcat có thể nhận HTTP nội bộ dù URL công khai là HTTPS; không nên mặc định request nào cũng trực tiếp tới embedded server.

## 4. Các bước chi tiết trên Spring MVC / Servlet

### Bước 1 — Client hình thành request và thiết lập đường truyền

Client chuẩn bị method (GET/POST/...), path, query string, headers và body tùy yêu cầu. DNS có thể phân giải tên miền; client thiết lập hoặc tái sử dụng kết nối, thực hiện TLS handshake nếu cần. Proxy/gateway có thể kết thúc TLS, kiểm tra hoặc chuyển tiếp request. **TCP/TLS lo vận chuyển; HTTP mô tả request và response.**

Ví dụ request từ client:

```http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

### Bước 2 — Máy chủ HTTP tiếp nhận

Tomcat nhận dữ liệu, phân tích request line, headers và body, thiết lập đối tượng `HttpServletRequest`/`HttpServletResponse` rồi chạy Servlet processing pipeline. Trong xử lý đồng bộ thông thường, một request đang được thực thi trên một worker thread của container. Điều này **không đồng nghĩa** mỗi kết nối mở luôn chiếm một thread hoặc cơ chế async cũng giữ nguyên mô hình ấy.

Nếu request không thể được phân tích hoặc bị từ chối ở tầng server/proxy (ví dụ lỗi giao thức, kích thước vượt giới hạn), nó có thể kết thúc **trước khi controller chạy**.

### Bước 3 — Filter chain chạy trước dispatcher

Servlet `Filter` (thường triển khai qua `OncePerRequestFilter` nếu cần) có thể đo thời gian, ghi correlation ID, kiểm tra CORS, bọc request, chỉnh headers hoặc kiểm soát truy cập. Nếu có Spring Security, `FilterChainProxy` phối hợp các security filters để xác thực/phân quyền trước khi cho request tiếp tục.

Filter gọi `chain.doFilter(request, response)` để chuyển tiếp; nó cũng có thể kết thúc request bằng một phản hồi, chẳng hạn 401/403, mà không gọi controller. Phần code **trước** `chain.doFilter` chạy trước các filter/dispatcher phía sau; phần **sau** lệnh này thường chạy khi chuỗi xử lý quay về. Thứ tự thực tế phụ thuộc cấu hình filter và loại dispatch (REQUEST/ASYNC/ERROR).

### Bước 4 — `DispatcherServlet` chọn handler

`DispatcherServlet` là front controller của Spring MVC. Nó nhờ `HandlerMapping` tìm handler phù hợp với HTTP method và path; sau đó `HandlerAdapter` chuẩn bị và thực hiện việc gọi handler. Ví dụ `GET /api/orders/42` khớp `@GetMapping("/{id}")` của controller có prefix `/api/orders`.

Spring dùng các argument resolvers để gắn `@PathVariable`, `@RequestParam`, `@RequestHeader`; đọc `@RequestBody` thông qua `HttpMessageConverter`; chuyển kiểu dữ liệu và kích hoạt validation nếu có cấu hình/annotation phù hợp (ví dụ `@Valid`). Lỗi binding/validation có thể tạo HTTP 400 trước khi thân phương thức controller chạy.

`HandlerInterceptor`, nếu đăng ký, có thể chạy `preHandle` trước handler, `postHandle` sau xử lý thành công và `afterCompletion` khi kết thúc. Interceptor nằm trong luồng Spring MVC, không phải Servlet Filter; thứ tự callback có các ngoại lệ khi xử lý async hoặc lỗi.

### Bước 5 — Controller điều phối mã nghiệp vụ

Controller nhận dữ liệu đã được binding và gọi service đã tiêm qua constructor. Service áp dụng quy tắc nghiệp vụ, có thể gọi repository, database, cache hoặc hệ thống khác. Nếu dùng `@Transactional`, ranh giới transaction thường nằm ở service; transaction chỉ thực sự có khi đã cấu hình transaction manager và phương thức được áp dụng transaction đúng cách.

Giữ controller tập trung vào giao thức HTTP, binding và chọn response; đặt quy tắc nghiệp vụ ở service giúp kiểm thử và tái sử dụng. Không phải mọi request đều cần database.

### Bước 6 — Spring tạo phản hồi HTTP

Controller có thể trả `ResponseEntity<T>` (quyết định status, headers, body), object DTO từ `@RestController`, `String`, view name hoặc response streaming, tùy loại endpoint. Với JSON DTO trong Spring MVC, một `HttpMessageConverter` phù hợp (thường dùng Jackson) chuyển object Java thành JSON theo content negotiation, cấu hình serializer và headers.

Kết quả thành **HTTP status + headers + body bytes**, chẳng hạn 200, `Content-Type: application/json` và JSON. Spring không gửi nguyên object Java qua mạng. Nếu dùng `@Controller` trả view name, có thể đi theo đường giải quyết/render view thay vì serialize JSON.

### Bước 7 — Ngoại lệ và luồng lỗi

Exception có thể xảy ra ở filter, argument binding, controller, service hoặc lúc tạo response. Trong Spring MVC, các `HandlerExceptionResolver` và `@ExceptionHandler`/`@RestControllerAdvice` có thể ánh xạ lỗi ứng dụng thành status/body phù hợp. Lỗi không được xử lý có thể đi qua cơ chế error handling mặc định của container/Spring Boot. Lỗi từ filter xảy ra trước dispatcher có thể cần cơ chế xử lý riêng; không nên mặc định mọi lỗi đều vào một `@RestControllerAdvice`.

Một số đường đi phổ biến:

- Không tìm được route/handler: thường là **404 Not Found**.
- Sai kiểu path variable, malformed JSON hoặc validation thất bại: thường là **400 Bad Request**.
- Bị lớp security từ chối: có thể là **401 Unauthorized** (chưa xác thực) hoặc **403 Forbidden** (không đủ quyền), tùy cấu hình.
- Lỗi không được xử lý: thường là **500 Internal Server Error**.

Đây là **ví dụ điển hình**, không phải luật cứng cho mọi app: exception handler, proxy, security và cấu hình có thể đổi status/body. Khi response headers đã được gửi (response committed), không thể tùy ý đổi status như khi response còn chưa bắt đầu; điều này đặc biệt quan trọng với streaming.

### Bước 8 — Kết thúc pipeline và gửi phản hồi

Các callback hậu xử lý của interceptor/filter được gọi theo quy tắc của từng tầng; server ghi status, headers, body ra kết nối (có thể chunked/streaming), proxy chuyển tiếp nếu có, client đọc response và xử lý JSON/HTML/file. Theo dõi thời gian end-to-end cần tính cả độ trễ mạng và proxy, không chỉ thời gian chạy service.

## 5. Ví dụ Spring Boot MVC chạy được với Java 17+

Ví dụ dưới đây cố ý dùng dữ liệu giả để thấy rõ đường đi **HTTP → controller → service → JSON**, không yêu cầu database. Tạo project Gradle với cấu trúc:

```text
web-runtime-demo/
├── build.gradle
└── src/main/java/com/example/webruntime/WebRuntimeApplication.java
```

Nội dung `build.gradle` (Spring Boot 3.3.x, Java 17):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.7'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Nội dung `src/main/java/com/example/webruntime/WebRuntimeApplication.java`:

```java
package com.example.webruntime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> find(@PathVariable long id) {
        OrderView result = orderService.findById(id);
        return ResponseEntity.ok(result);
    }
}

@Service
class OrderService {
    public OrderView findById(long id) {
        if (id <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "id phải lớn hơn 0");
        }
        return new OrderView(id, "CONFIRMED");
    }
}

record OrderView(long id, String status) {}
```

Chạy từ thư mục `web-runtime-demo` bằng Gradle tương thích Spring Boot 3.3 và JDK 17+:

```bash
gradle bootRun
```

Nếu project có Gradle wrapper, dùng `./gradlew bootRun` trên macOS/Linux hoặc `.\gradlew.bat bootRun` trên Windows PowerShell. Khi server đã khởi động, thử gọi:

```bash
curl -s http://localhost:8080/api/orders/42
```

Body JSON dự kiến (một dòng, không phụ thuộc phần log startup):

```json
{"id":42,"status":"CONFIRMED"}
```

Trong response HTTP thành công, status là **200**, `Content-Type` thông thường là `application/json`. Giá trị `42` được chuyển từ path thành `long`; `OrderController.find` gọi `OrderService.findById`; service tạo `OrderView`; Spring MVC/Jackson chuyển record thành JSON. Controller không tự mở socket hoặc tự viết chuỗi HTTP.

Thử `/api/orders/0`: service phát sinh `ResponseStatusException` với **400 Bad Request**. Thử `/api/orders/abc`: chuyển kiểu `String → long` thất bại trong bước binding, cũng thường là **400**, và service chưa chạy. Response body lỗi phụ thuộc cấu hình Spring Boot nên không giả định một JSON lỗi cố định. Ví dụ này không thêm Spring Security, do đó không tự phát sinh bước authentication mặc định của `spring-boot-starter-security`.

## 6. Nếu dùng WebFlux thì đường đi thay đổi ở đâu?

| Khía cạnh | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Máy chủ phổ biến | Tomcat (embedded mặc định với starter web) | Reactor Netty (phổ biến với starter webflux) |
| Mô hình request | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange`, `ServerHttpRequest` / `ServerHttpResponse` |
| Lớp chặn chung | Servlet `Filter`; Spring Security filter chain nếu có | `WebFilter`; reactive security WebFilter chain nếu có |
| Bộ điều phối | `DispatcherServlet` | `DispatcherHandler` |
| Chọn và gọi handler | `HandlerMapping`, `HandlerAdapter` | `HandlerMapping`, `HandlerAdapter` dạng reactive |
| Kết quả HTTP | `HandlerMethodReturnValueHandler`, `HttpMessageConverter`, view resolver | `HandlerResultHandler`, `HttpMessageWriter`, reactive view handling |
| Luồng thực thi | Worker thread cho xử lý Servlet đồng bộ, có hỗ trợ async | Non-blocking I/O, xử lý theo reactive stream và event loop/scheduler |

WebFlux có đường đi khái quát:

```text
Client → HTTP server (thường Reactor Netty)
       → HttpWebHandlerAdapter / WebFilter
       → DispatcherHandler → mapping/adapter
       → controller hoặc functional handler
       → service trả Publisher (ví dụ Mono/Flux)
       → HandlerResultHandler / HttpMessageWriter
       → HTTP response
```

`Mono<T>` thường biểu diễn tối đa một kết quả; `Flux<T>` có thể biểu diễn nhiều phần tử. Reactor điều phối việc subscribe và phát tín hiệu dữ liệu/lỗi/hoàn tất; response được ghi khi dòng dữ liệu được xử lý. Không được đặt lời gọi blocking dài (ví dụ JDBC đồng bộ hoặc `Thread.sleep`) ngay trên Netty event-loop thread: nó cản trở nhiều request khác. Nếu bắt buộc dùng API blocking, cần tách công việc sang scheduler thích hợp hoặc dùng API/driver reactive. Cũng không nên coi WebFlux là tự động nhanh hơn MVC trong mọi workload.

Tên `@RestController` và mô hình controller → service có thể giống nhau ở cả hai stack; **thư viện HTTP được chọn và cách thực thi mới quyết định pipeline thực tế**. Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có trong ứng dụng Spring Boot, mặc định thường ưu tiên loại ứng dụng Servlet/MVC trừ khi cấu hình rõ lựa chọn khác.

## 7. Cách quan sát và khoanh vùng khi request không như mong đợi

Đi từ bên ngoài vào trong theo đúng pipeline:

1. **Không kết nối được:** kiểm tra URL, DNS, port, TLS, proxy, tình trạng server đã lắng nghe.
2. **Có phản hồi nhưng controller không chạy:** kiểm tra reverse proxy, HTTP method/path, filter/security, 404, 401/403 và lỗi binding.
3. **Controller vào nhưng kết quả sai/chậm:** theo dấu tham số đã bind, service, transaction, DB/API và thời gian I/O.
4. **Service trả đúng nhưng client nhận sai:** kiểm tra `ResponseEntity`, serializer, content negotiation, response headers, exception handler, streaming/proxy.
5. **Chỉ chậm dưới tải:** quan sát thread pool/connection pool ở MVC, blocking trên event loop ở WebFlux, pool của database, hàng đợi và timeout.

Có thể thêm request ID hoặc trace ID xuyên suốt proxy → filter → controller → service, rồi ghi log với thời gian của từng chặng. Với ứng dụng thực tế, metrics/traces (ví dụ qua Micrometer/Actuator khi được cấu hình) giúp nhận ra chặng nào chiếm thời gian; log ở controller một mình không đo toàn bộ request.

## 8. Các nhầm lẫn cần tránh

- **“Mạng gọi thẳng method trong controller”:** HTTP server phải tiếp nhận và framework phải định tuyến/binding trước.
- **“Mọi request đều đi vào service”:** filter, security, route mapping hoặc binding có thể kết thúc request từ trước.
- **“Object Java được trả trực tiếp qua HTTP”:** framework phải mã hóa thành body bytes, đồng thời xác định status và headers.
- **“Filter = Interceptor”:** Servlet Filter nằm ngoài `DispatcherServlet`; MVC Interceptor tham gia vào quá trình handler của Spring MVC.
- **“Một request luôn bằng một connection và một thread”:** keep-alive, HTTP/2, servlet async và WebFlux làm giả định này không đúng tổng quát.
- **“WebFlux luôn non-blocking dù gọi code blocking”:** tự đưa thao tác blocking vào event loop vẫn gây nghẽn.
- **“Có lỗi là `@RestControllerAdvice` chắc chắn bắt được”:** lỗi có thể xảy ra ở proxy/filter/server hoặc sau khi response đã committed.

**Ghi nhớ:** request HTTP đi qua **network → server → middleware → dispatcher/routing → controller → service → xử lý kết quả → server/network → client**. Khi cần debug, xác định request dừng ở chặng nào trước khi tìm lỗi trong nghiệp vụ.