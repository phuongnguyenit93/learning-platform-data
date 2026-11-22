# Giới hạn đọc lại request body và cách dùng wrapper hoặc decorator trong Spring Boot

## 1. Vấn đề: request body không mặc định là bộ đệm có thể đọc lại

HTTP request body đi tới server dưới dạng luồng byte. Trong Spring Boot, framework thường tiêu thụ luồng đó để giải mã JSON, form, multipart hoặc dữ liệu nhị phân. Sau khi một thành phần đã đọc hết, thành phần kế tiếp không thể mặc nhiên quay lại byte đầu tiên.

Ở **Spring MVC**, request body được đọc qua HttpServletRequest.getInputStream() hoặc getReader(). Khi controller có @RequestBody, HttpMessageConverter đọc stream để tạo DTO Java. Một Servlet Filter hoặc HandlerInterceptor đọc trước mà không phát lại dữ liệu có thể khiến controller nhận body rỗng, Required request body is missing, hoặc lỗi parse JSON.

Ở **Spring WebFlux**, ServerHttpRequest.getBody() trả Flux<DataBuffer>. Việc một WebFilter subscribe và tiêu thụ Flux gốc không đồng nghĩa controller có thể subscribe lại và nhận chính xác payload ban đầu. Publisher của incoming network stream không phải cache có khả năng replay bảo đảm.

Nhu cầu thực tế gồm audit, đo kích thước, kiểm tra chữ ký webhook, xác nhận định dạng, tìm lỗi hoặc xử lý middleware. Không phải nhu cầu nào cũng cần đọc body hai lần. Hãy ưu tiên:

1. Nếu chỉ cần log metadata, không đọc raw body.
2. Nếu cần quan sát bytes mà controller đang đọc, dùng cơ chế caching quan sát.
3. Nếu thật sự cần hai consumer đọc cùng raw bytes, buffer có giới hạn và phát lại qua wrapper/decorator.
4. Nếu đã parse thành DTO, truyền DTO đi tiếp thay vì parse raw bytes lần hai.
5. Nếu request là file lớn hoặc stream không giới hạn, dùng streaming hoặc lưu trữ tạm có quản lý; tránh buffer toàn bộ vào RAM.

**Nguyên tắc quan trọng:** body không tự động có quyền seek, rewind hoặc replay. Muốn đọc lại, ứng dụng phải cấp một nguồn dữ liệu mới với giới hạn kích thước và lifecycle rõ ràng.

## 2. Servlet MVC và WebFlux dùng các abstraction khác nhau

| Khía cạnh | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Incoming request | HttpServletRequest | ServerHttpRequest |
| Cách đọc body | getInputStream(), getReader() | getBody(): Flux<DataBuffer> |
| Extension point toàn cục | Servlet Filter / OncePerRequestFilter | WebFilter |
| Cách bọc | HttpServletRequestWrapper | ServerHttpRequestDecorator |
| Cách parse @RequestBody | HttpMessageConverter | HttpMessageReader/Decoder |
| Công cụ quan sát tích hợp | ContentCachingRequestWrapper | Không dùng servlet wrapper; phải dùng reactive pipeline phù hợp |
| Phát lại body | ByteArrayInputStream mới từ byte[] đã cache | Flux<DataBuffer> mới từ bytes đã cache |
| Rủi ro đặc thù | Form parser, Servlet async input, filter order | Pooled buffers, retain/release, cancellation, backpressure |

Ví dụ trong bài nhắm **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. Boot 3 dùng package jakarta.servlet; Boot 2 cũ dùng javax.servlet. Một project có spring-webflux chỉ để dùng WebClient vẫn có thể chạy MVC, nên phải kiểm tra web application type thực tế trước khi chọn code.

## 3. Phân biệt quan sát body với phát lại body

**Quan sát** nghĩa là ghi một bản sao của những byte downstream thực sự đọc. Nếu downstream chưa đọc, cache có thể rỗng. Nếu downstream đọc một phần, cache có thể chỉ chứa phần đó. Việc quan sát không buộc request stream phải quay lại đầu.

**Phát lại** nghĩa là cung cấp một nguồn body độc lập với vị trí đọc hiện tại. Với wrapper đơn giản, ta lưu toàn bộ bytes vào byte[] nhỏ rồi mỗi lần gọi getInputStream() tạo ByteArrayInputStream mới. Với WebFlux, decorator phát ra Flux mới cho subscriber tiếp theo.

| Nhu cầu | Cách phù hợp |
|---|---|
| Log số byte downstream đã tiêu thụ | ContentCachingRequestWrapper sau Filter chain |
| Log kích thước thực và kiểm tra quá ngưỡng | Giới hạn body ở proxy/server và bounded read phù hợp |
| Filter xác minh raw JSON, controller vẫn dùng @RequestBody | Bounded replay wrapper |
| WebFlux WebFilter xem raw JSON, controller vẫn parse | Bounded aggregate + ServerHttpRequestDecorator |
| Controller đã có DTO rồi muốn kiểm tra nghiệp vụ | Dùng DTO, validation và service, không đọc lại stream |
| Multipart upload hàng GB | Streaming, disk/object storage và quotas; không replay bằng byte[] |

Tránh áp dụng cùng một cách cho mọi endpoint. Việc giữ bản sao toàn bộ payload từ hàng nghìn request đồng thời có thể tạo memory pressure và tăng độ trễ đáng kể.

## 4. ContentCachingRequestWrapper: cache những byte đã đọc, không tự replay

Spring Framework cung cấp:

~~~java
org.springframework.web.util.ContentCachingRequestWrapper
~~~

Theo Javadoc 6.2, lớp này cache nội dung **khi** InputStream/Reader được đọc. Nó không chủ động đọc body trong constructor. getContentAsByteArray() trả các byte đã được cache đến thời điểm gọi, tối đa cache limit.

Một số hệ quả:

- Trước khi controller đọc @RequestBody, getContentAsByteArray() thường rỗng.
- Nếu controller không đọc body, cache có thể rỗng dù client đã gửi dữ liệu.
- Nếu controller chỉ đọc một phần, cache cũng có thể là dữ liệu chưa đầy đủ.
- contentCacheLimit không tự từ chối request lớn hơn hạn mức; nó là giới hạn giữ nội dung trong cache.
- Hook handleContentOverflow(int) có thể được override nếu muốn xử lý overflow riêng, nhưng hành vi mặc định không phải tự động HTTP 413.
- Lớp này không bảo đảm getInputStream() lần hai phát lại toàn bộ bytes cho controller khác.

Ví dụ Filter chỉ **quan sát số byte** sau khi MVC xử lý:

~~~java
package example.mvc;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;

@Component
public class ObservedBodyFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(ObservedBodyFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        ContentCachingRequestWrapper wrapped =
                new ContentCachingRequestWrapper(request, 4096);

        try {
            chain.doFilter(wrapped, response);
        } finally {
            log.debug("Cached body bytes: {}",
                    wrapped.getContentAsByteArray().length);
        }
    }
}
~~~

Filter ở trên không tự đọc body trước controller. Khi controller đọc, wrapper giữ bản sao tối đa 4096 bytes. Giá trị log có thể nhỏ hơn tổng payload thật vì cache limit hoặc vì downstream chỉ đọc một phần; nó không phải số đo tuyệt đối của payload length.

**Lưu ý:** Đừng đăng ký ObservedBodyFilter và Filter replay đầy đủ ở phần tiếp theo đồng thời trên cùng endpoint khi chưa kiểm soát thứ tự và tác dụng của các wrapper lồng nhau. Hai ví dụ nhằm giải quyết **hai nhu cầu khác nhau**.

## 5. Vì sao một lượt đọc sớm khiến @RequestBody lỗi?

Ví dụ Filter sai:

~~~java
byte[] bytes = request.getInputStream().readAllBytes();
log.debug("Read {} bytes", bytes.length);
chain.doFilter(request, response);
~~~

Filter đã đọc stream gốc tới EOF; sau đó HttpMessageConverter của MVC không còn dữ liệu để parse. Nếu controller yêu cầu @RequestBody, Spring có thể báo request body missing hoặc lỗi parse.

Thay bằng ContentCachingRequestWrapper chưa đủ nếu Filter vẫn đọc trước và kỳ vọng tự có dữ liệu để controller đọc lại:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request);
byte[] bytes = wrapped.getInputStream().readAllBytes();
chain.doFilter(wrapped, response);
~~~

Ở đây wrapped.getInputStream() cũng tiêu thụ input gốc trong lúc cache, và ContentCachingRequestWrapper không hứa rằng các lần getInputStream tiếp theo bắt đầu lại từ đầu. Muốn middleware đọc trước rồi controller đọc lại, cần một wrapper **replayable** thật sự hoặc chuyển phần xử lý đến sau khi framework parse.

Nếu mục tiêu là validation JSON, @Valid cùng DTO hoặc RequestBodyAdvice thường thích hợp hơn việc cắt vào luồng raw bytes.

## 6. Custom Servlet wrapper phát lại body cho xử lý đồng bộ

Với các JSON endpoint nhỏ, có thể đọc body gốc **một lần có giới hạn** ở Filter, sau đó truyền xuống chain một HttpServletRequestWrapper tạo stream mới từ bytes đã lưu.

Ví dụ dưới đây chỉ dành cho **synchronous Servlet reads**; nó không thực hiện hợp đồng non-blocking ServletInputStream.setReadListener. Điều này được ghi rõ để không giả vờ hỗ trợ async I/O.

### 6.1. Tệp ReplayableRequest.java

Tệp src/main/java/example/mvc/ReplayableRequest.java:

~~~java
package example.mvc;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

public final class ReplayableRequest extends HttpServletRequestWrapper {

    private final byte[] body;

    public ReplayableRequest(HttpServletRequest original, byte[] bytes) {
        super(original);
        this.body = bytes.clone();
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream input = new ByteArrayInputStream(body);

        return new ServletInputStream() {
            @Override
            public int read() throws IOException {
                return input.read();
            }

            @Override
            public boolean isFinished() {
                return input.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException(
                        "Synchronous reads only");
            }
        };
    }

    @Override
    public BufferedReader getReader() throws IOException {
        String encoding = getCharacterEncoding();
        Charset charset = encoding == null
                ? StandardCharsets.UTF_8
                : Charset.forName(encoding);
        return new BufferedReader(
                new InputStreamReader(getInputStream(), charset));
    }
}
~~~

Các điểm quan trọng:

- Constructor sao chép byte[] để tránh thay đổi ngoài ý muốn.
- getInputStream() tạo ByteArrayInputStream mới bắt đầu từ byte thứ 0 trên **mỗi lần gọi**.
- getReader() cũng tạo reader mới, dùng encoding được request công bố, fallback UTF-8.
- isFinished thể hiện stream đã đọc tới EOF; isReady trả true vì dữ liệu nằm trong RAM.
- setReadListener được cố ý báo unsupported. Nếu ứng dụng dùng non-blocking Servlet request input hoặc Servlet async API, phải thay bằng implementation đáp ứng đầy đủ ReadListener callbacks hoặc giải pháp khác.
- Wrapper không override getParameter(), getParts(), getParameterMap(). Vì vậy không dùng mù quáng cho application/x-www-form-urlencoded hay multipart/form-data, nơi container có parser riêng.

Không nên coi wrapper này là một Servlet framework hoàn chỉnh: nó là ví dụ thiết kế giới hạn để đọc lại JSON nhỏ ở request xử lý đồng bộ.

## 7. Servlet Filter đọc có giới hạn và trả HTTP 413

Tệp src/main/java/example/mvc/ReplayBodyFilter.java:

~~~java
package example.mvc;

import java.io.IOException;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ReplayBodyFilter extends OncePerRequestFilter {

    private static final int MAX_BYTES = 64 * 1024;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String contentType = request.getContentType();
        boolean target = "POST".equalsIgnoreCase(request.getMethod())
                && "/api/echo".equals(request.getServletPath())
                && contentType != null
                && contentType.toLowerCase(Locale.ROOT)
                        .startsWith("application/json");

        if (!target) {
            chain.doFilter(request, response);
            return;
        }

        // Đọc tối đa MAX_BYTES + 1 để nhận ra body vượt giới hạn.
        byte[] bytes = request.getInputStream()
                .readNBytes(MAX_BYTES + 1);

        if (bytes.length > MAX_BYTES) {
            response.sendError(413, "Request body too large");
            return;
        }

        chain.doFilter(new ReplayableRequest(request, bytes), response);
    }
}
~~~

**Vì sao phải đọc MAX_BYTES + 1?** Nếu chỉ đọc đúng 64 KiB, không thể biết stream có byte thứ 65.537 hay không. Đọc tối đa một byte quá ngưỡng đủ để từ chối mà không cần tải toàn bộ request lớn vào RAM.

Không chỉ dựa vào Content-Length để giới hạn vì header có thể không có hoặc request dùng chunked transfer. Để bảo vệ trước slow upload, vẫn cần server/proxy read timeout và các hạn mức khác.

Filter cố ý chỉ chọn POST /api/echo với application/json. Nếu dự án có context path hoặc custom servlet mapping, phải kiểm chứng getServletPath() trong môi trường đó. Với Content-Type phức tạp, dùng MediaType parser và error handling phù hợp; startsWith chỉ là điều kiện đơn giản cho endpoint ví dụ.

Filter này tạo một bản sao cho request đã được chấp nhận. Nếu muốn áp dụng toàn API, cần tính toán memory budget, concurrency, giới hạn body và cơ chế bảo vệ trước DOS; không đổi target thành true cho mọi request mà không đánh giá chi phí.

## 8. Controller chứng minh JSON đã được đọc và vẫn có thể đọc lại

Tệp src/main/java/example/mvc/BodyEchoController.java:

~~~java
package example.mvc;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BodyEchoController {

    public record Payload(String message) {}

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> echo(
            @RequestBody Payload payload,
            HttpServletRequest request) throws IOException {

        // MVC đã đọc JSON để tạo Payload trước khi vào method.
        byte[] replayed = request.getInputStream().readAllBytes();

        String message = payload.message() == null
                ? ""
                : payload.message();

        return Map.of(
                "message", message,
                "replayedBytes", replayed.length
        );
    }
}
~~~

Từ client:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'
~~~

Dự kiến HTTP 200, JSON body tương đương:

~~~json
{"message":"hello","replayedBytes":19}
~~~

Số 19 là số byte của đúng chuỗi JSON ASCII trong ví dụ, không phải giới hạn chung hoặc độ dài Unicode. Thứ tự các key trong JSON response có thể thay đổi.

Controller đọc body lần hai chỉ để chứng minh wrapper. Trong business code, nếu đã có Payload thì nên dùng Payload thay vì đọc raw bytes thêm lần nữa.

### 8.1. Cấu trúc Maven project

Project Spring Boot 3.5/Java 17+ với starter-web và starter-test:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đoạn trên thuộc pom.xml có parent/BOM Spring Boot. Class ứng dụng:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

Đặt các Java files dưới src/main/java/example/mvc/; thư mục src/test/java/example/mvc/ dành cho test. Ví dụ không phải chương trình javac độc lập vì phụ thuộc Spring Boot và Servlet API.

### 8.2. MockMvc test cho replay và giới hạn

Tệp src/test/java/example/mvc/ReplayBodyFilterTest.java:

~~~java
package example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ReplayBodyFilterTest {

    @Autowired
    MockMvc mvc;

    @Test
    void converterAndControllerBothReceiveBytes() throws Exception {
        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("hello"))
                .andExpect(jsonPath("$.replayedBytes").value(19));
    }

    @Test
    void rejectsBodyBeyondLimit() throws Exception {
        String large = "{\"message\":\""
                + "x".repeat(64 * 1024)
                + "\"}";

        mvc.perform(post("/api/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(large))
                .andExpect(status().is(413));
    }
}
~~~

Chạy ./mvnw test hoặc trên Windows .\mvnw.cmd test. Test thứ nhất khẳng định @RequestBody có JSON và lần getInputStream sau trả đủ 19 bytes. Test thứ hai xác nhận payload vượt 64 KiB bị Filter từ chối.

Nếu bạn bật Spring Security, MockMvc có thể nhận 401/403 trước khi tới controller; cần cấu hình chính sách và test identity đúng thay vì kết luận replay wrapper sai.

## 9. Những giới hạn của replay wrapper trên Servlet

### Form URL-encoded

application/x-www-form-urlencoded có cơ chế parser đặc biệt ở Servlet container. Khi một Filter đọc InputStream trước, việc gọi getParameter()/getParameterMap() có thể bị ảnh hưởng. ReplayableRequest chỉ hỗ trợ stream và reader, không tái tạo form parameter map.

Nếu cần hỗ trợ form, hãy dùng những API sau parse hoặc xây wrapper thực hiện đầy đủ parameter semantics, charset và thời điểm đọc; đừng áp dụng nguyên wrapper JSON.

### Multipart upload

Multipart body chứa nhiều part, headers và file. Buffer toàn bộ request có thể gây OutOfMemoryError hoặc tiêu thụ heap lớn khi nhiều upload đồng thời. Nên để multipart resolver/Part API xử lý, thiết lập max file/request size và dùng disk/object storage theo nhu cầu. Không log nội dung file chỉ để debug.

### Async Servlet API

Với Servlet 3.1 non-blocking I/O, setReadListener cần thực hiện hợp đồng callback bất đồng bộ. ReplayableRequest ở trên ném UnsupportedOperationException, nên **chỉ dùng với synchronous reads**. Khi có Callable, DeferredResult, WebAsyncTask hoặc async dispatch, còn phải đánh giá vòng đời Filter, wrapper và callback.

### InputStream và Reader

Servlet API có quy tắc riêng cho việc dùng getInputStream và getReader. Wrapper ví dụ cố ý cung cấp một nguồn mới cho cả hai, nhưng không phải giải pháp universal cho mọi container/framework behavior. Tốt nhất chọn một cách đọc raw bytes, giữ nguyên encoding, không trộn bừa parser form, multipart và stream.

### Thứ tự Filter

Nếu Filter khác đã tiêu thụ body trước khi ReplayBodyFilter chạy, wrapper không thể khôi phục bytes đã mất. Phải kiểm tra thứ tự Servlet filters, Spring Security và các middleware liên quan. Thay đổi thứ tự cần đi kèm integration tests; không lạm dụng order cực cao mà không biết tác động bảo mật.

## 10. WebFlux: vì sao subscribe hai lần vào body gốc không đáng tin cậy?

Trong WebFlux:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

Đó là publisher đại diện cho incoming request bytes, không phải List<DataBuffer> đã lưu. Nếu WebFilter đọc bằng subscribe() hoặc DataBufferUtils.join(...), body đã được tiêu thụ theo pipeline. Controller không tự động nhận lại cùng dữ liệu khi gọi @RequestBody.

Đoạn sai về mặt thiết kế:

~~~java
exchange.getRequest().getBody().subscribe(buffer -> {
    // Đọc bytes ở đây...
});
return chain.filter(exchange);
~~~

subscribe() thủ công tách việc đọc khỏi lifecycle của chain, làm khó xử lý backpressure, error, cancellation và ownership của DataBuffer. Hãy **trả một Mono kết hợp đúng việc đọc, tạo decorator và gọi chain.filter**, không tạo subscription bên lề.

WebFlux dùng ServerHttpRequestDecorator để override getBody() và cấp publisher mới:

~~~java
ServerHttpRequestDecorator replay =
        new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public Flux<DataBuffer> getBody() {
                // Trả Flux mới theo hợp đồng replay của ứng dụng.
                return ...;
            }
        };

return chain.filter(exchange.mutate()
        .request(replay)
        .build());
~~~

Đây là ý tưởng minh họa; code đầy đủ ở phần tiếp theo có bound 64 KiB, DataBuffer release và lỗi HTTP 413.

## 11. WebFlux WebFilter: bounded join và ServerHttpRequestDecorator

### 11.1. Thiết kế

Trình tự:

1. Chỉ áp dụng POST /api/echo với application/json.
2. Đọc request.getBody() qua DataBufferUtils.join(..., 64 KiB).
3. Nếu vượt ngưỡng, DataBufferLimitException được đổi thành ResponseStatusException(413).
4. Sao chép joined DataBuffer thành byte[] rồi release buffer gốc trong finally.
5. Tạo ServerHttpRequestDecorator, mỗi subscriber nhận một DataBuffer mới từ bytes.
6. Gọi chain.filter(exchange đã thay request) trong cùng reactive pipeline.

Sao chép sang byte[] đơn giản hóa quản lý reference count so với giữ nguyên pooled DataBuffer qua nhiều subscribers. Tuy nhiên, nó tốn thêm allocation và chỉ dùng khi request đủ nhỏ.

### 11.2. Tệp ReplayBodyWebFilter.java

Tệp src/main/java/example/flux/ReplayBodyWebFilter.java:

~~~java
package example.flux;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ReplayBodyWebFilter implements WebFilter {

    private static final int MAX_BYTES = 64 * 1024;

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        ServerHttpRequest request = exchange.getRequest();
        MediaType contentType = request.getHeaders().getContentType();

        boolean target = request.getMethod() == HttpMethod.POST
                && request.getPath().pathWithinApplication()
                        .value().equals("/api/echo")
                && contentType != null
                && MediaType.APPLICATION_JSON
                        .isCompatibleWith(contentType);

        if (!target) {
            return chain.filter(exchange);
        }

        Mono<byte[]> cached = DataBufferUtils.join(
                        request.getBody(), MAX_BYTES)
                .map(buffer -> {
                    try {
                        byte[] bytes =
                                new byte[buffer.readableByteCount()];
                        buffer.read(bytes);
                        return bytes;
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .defaultIfEmpty(new byte[0])
                .onErrorMap(
                        DataBufferLimitException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "Request body too large", ex));

        return cached.flatMap(bytes -> {
            ServerHttpRequestDecorator replay =
                    new ServerHttpRequestDecorator(request) {
                @Override
                public Flux<DataBuffer> getBody() {
                    return Flux.defer(() -> Flux.just(
                            exchange.getResponse()
                                    .bufferFactory()
                                    .wrap(bytes.clone())));
                }
            };

            return chain.filter(exchange.mutate()
                    .request(replay)
                    .build());
        });
    }
}
~~~

Giải thích:

- join(Publisher, maxByteCount) kiểm soát tổng byte đã aggregate. Nếu bị lỗi/cancel, các buffers đã được join giữ sẽ được giải phóng theo contract của DataBufferUtils.
- map sao chép bytes và release joined buffer, tránh giữ pooled input lâu hơn cần.
- defaultIfEmpty xử lý trường hợp request không phát DataBuffer nào.
- onErrorMap nằm trong pipeline đọc body, trước flatMap downstream, giúp chuyển riêng lỗi buffer limit thành HTTP 413.
- Flux.defer cung cấp DataBuffer mới khi có subscription; bytes.clone() ngăn các subscription phụ thuộc vào cùng một mảng mutable.
- Downstream codecs chịu trách nhiệm tiêu thụ/release DataBuffer mới theo luồng HTTP.
- Không gọi block(), subscribe() thủ công hay lưu raw bytes vào static/global cache.
- Filter vẫn làm giảm khả năng streaming vì nó phải đệm trọn JSON request nhỏ trước khi gọi controller; không áp dụng cho upload hay stream vô hạn.

Với Netty, thao tác trực tiếp trên DataBuffer bắt buộc phải xét lifecycle. Một DataBuffer đã release không được phát lại bằng Flux.just(buffer) cho subscriber khác. Nếu sử dụng retain(), phải release theo đúng ownership. Việc copy bounded byte[] giúp giảm rủi ro reuse buffer cũ.

## 12. Ví dụ WebFlux controller và WebTestClient

Tạo một **project Spring Boot 3.5.x riêng** với Java 17+, spring-boot-starter-webflux và spring-boot-starter-test. Không đưa ReplayableRequest của Servlet project vào reactive-only application.

Tệp src/main/java/example/flux/FluxApplication.java:

~~~java
package example.flux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxApplication.class, args);
    }
}
~~~

Tệp src/main/java/example/flux/FluxEchoController.java:

~~~java
package example.flux;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class FluxEchoController {

    public record Payload(String message) {}

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<Payload> body) {
        return body.map(payload ->
                Map.of("message", payload.message() == null
                        ? "" : payload.message()));
    }
}
~~~

Controller chỉ đọc một lần sau khi WebFilter đã cache body. Nó không cần biết gì về DataBuffer vì HttpMessageReader giải mã JSON từ decorator.

Tệp src/test/java/example/flux/ReplayBodyWebFilterTest.java:

~~~java
package example.flux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReplayBodyWebFilterTest {

    @Autowired
    WebTestClient client;

    @Test
    void bodyStillReachesController() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"message\":\"hello\"}")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void largeBodyIsRejected() {
        String big = "{\"message\":\""
                + "x".repeat(64 * 1024)
                + "\"}";

        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(big)
                .exchange()
                .expectStatus().isEqualTo(413);
    }
}
~~~

Chạy ./mvnw test hoặc .\mvnw.cmd test. WebTestClient có thể dùng với full reactive context và embedded server. Nếu project có Spring Security, phải cấu hình identity/policy phù hợp để không nhầm 401/403 với lỗi body decorator.

Khi test WebFlux riêng, bảo đảm không thêm spring-boot-starter-web ngoài ý muốn: nếu có cả hai starter, Boot thường chọn MVC thay vì WebFlux.

## 13. DataBuffer ownership, memory limit và backpressure

Đây là các lỗi rủi ro cao khi viết WebFlux filter:

1. DataBuffer từ Reactor Netty có thể được pool và reference-counted; cần release khi tự consume xong.
2. DataBufferUtils.join có thể tạo composite buffer; đọc xong phải release buffer kết quả, cả trong exception path.
3. Khi buffer bị discard do cancel, filter hoặc flatMap, có thể cần doOnDiscard(DataBuffer.class, DataBufferUtils::release) theo hướng dẫn Spring.
4. Nếu giữ pooled DataBuffer sau callback, phải retain trước và release sau đúng số lần.
5. Không tái sử dụng DataBuffer đã được framework release.
6. Không tự subscribe vào request body ngoài chain; để Reactor điều phối subscription và cancellation.
7. Đừng giữ nhiều bản copy của payload trong logs, cache, request attributes và queue không có giới hạn.

Phản mẫu:

~~~java
DataBuffer cachedBuffer = ...;
// Có thể bị release sau subscriber đầu tiên:
Flux<DataBuffer> replay = Flux.just(cachedBuffer);
~~~

Nếu subscriber đầu tiên consume/release cachedBuffer, subscriber tiếp theo có thể gặp reference count error. Khi dùng bounded byte[] và wrap một buffer mới mỗi subscription, dữ liệu không còn phụ thuộc vào pooled buffer đã release; nhưng chi phí RAM và allocation vẫn cần đánh giá.

### Codec limit không thay thế custom filter limit

Trong Spring Boot WebFlux, có thể cấu hình codecs, ví dụ:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 256KB
~~~

Codec limit áp dụng cho hoạt động buffer/aggregate của codec theo semantics tương ứng. Nó **không tự đặt hạn mức cho mọi custom WebFilter đang dùng DataBufferUtils.join** nếu Filter không truyền maxByteCount.

Trong ví dụ WebFilter, MAX_BYTES = 64 KiB hoạt động độc lập. Payload lớn hơn ngưỡng này nhận 413 dù HTTP codec có hạn mức lớn hơn.

Đặt thêm giới hạn ở reverse proxy/API gateway, server, multipart parser, JSON codec và application layer khi phù hợp. Không chỉ tăng vô hạn maxInMemorySize để làm biến mất DataBufferLimitException.

## 14. RequestBodyAdvice, logging và cách tránh đọc lại bytes

Nếu yêu cầu là validate object đã giải mã, Spring MVC có RequestBodyAdvice và Bean Validation. Dùng @Valid cùng DTO hoặc service validation thường phù hợp hơn đọc raw JSON ở Filter và parse lại trong controller.

HandlerInterceptor có thể truy cập thông tin về handler và request metadata, nhưng đọc trực tiếp request.getInputStream() từ preHandle vẫn sẽ tiêu thụ stream. Với WebFlux, có thể dùng WebFilter và exchange attributes để chia sẻ metadata đã xử lý, không nhất thiết tạo thêm subscription.

Nếu audit chỉ cần ghi kích thước request, content type và status, hãy thu thập sau khi controller/codec đọc body hoặc ở tầng HTTP server/proxy, không copy raw payload vào log.

Đối với **webhook signature** cần HMAC trên raw body, không serialize DTO trở lại JSON trước khi xác minh: whitespace, escaping và thứ tự field có thể thay đổi và làm HMAC sai. Khi cần xác minh chữ ký, đọc raw bytes có giới hạn tại một vị trí có chủ đích, dùng so sánh constant-time cho chữ ký rồi replay nếu downstream cần parse cùng dữ liệu. Không log secret key, signature và payload nhạy cảm.

## 15. Multipart, form, Unicode và những giới hạn quan trọng

**Form URL-encoded:** Servlet container có thể parse parameters từ request body. Nếu Filter đọc InputStream trước khi getParameter được gọi, parameter map có thể bị ảnh hưởng. Wrapper ví dụ không tái tạo getParameter()/getParts() nên không được dùng rộng cho form/multipart.

**Multipart:** MultipartFile và Part API đã có lifecycle và storage semantics. Tạo một byte[] khổng lồ từ toàn bộ multipart chỉ để log là không phù hợp. Dùng streaming, file size limits, disk quotas và object storage.

**Unicode:** UTF-8 dùng số byte không nhất thiết bằng Java String.length(). Với tiếng Việt, emoji hoặc encoding khác, max request size phải dựa trên bytes, không phải số ký tự. getReader cần tôn trọng charset; JSON hiện đại thường dùng UTF-8.

**Content-Length:** Có thể vắng mặt hoặc không phản ánh lượng bytes thực sự đang đọc trong mọi ngữ cảnh proxy/encoding. Khi enforce size, giới hạn bằng bộ đếm bytes thực tế, không chỉ tin request.getContentLengthLong().

**Non-blocking Servlet async:** ReplayableRequest ở ví dụ không hỗ trợ setReadListener. Một implementation dùng cho non-blocking input phải có callback contract đầy đủ; không chỉ trả isReady=true rồi coi là tương thích với mọi framework.

**Client disconnect/cancellation:** WebFlux pipeline có thể cancel. DataBuffer đã tích lũy phải được release; không giữ body lâu trong một global cache nếu request đã hủy. Trong Servlet, xử lý lỗi đọc và timeout cũng cần giải phóng tài nguyên.

## 16. Lỗi thường gặp và cách tìm đúng nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| @RequestBody báo missing sau khi thêm Filter | Filter đọc body trước controller | Bỏ đọc trước, hoặc bounded replay wrapper |
| getContentAsByteArray() rỗng trong Filter | Downstream chưa đọc body | Quan sát sau khi chain đọc, không dùng như read-ahead |
| Cache chỉ có một phần body | Cache limit hoặc downstream đọc một phần | Không coi cache length là payload length tuyệt đối |
| ContentCachingRequestWrapper nhưng lần đọc thứ hai rỗng | Wrapper không hứa replay stream | Dùng wrapper tự tạo getInputStream mới |
| application/x-www-form-urlencoded không có parameters | Filter đọc body trước form parser | Dùng form API phù hợp, không áp dụng JSON wrapper |
| Multipart upload gây OutOfMemoryError | Buffer cả file trong heap | Streaming, disk/object storage và quotas |
| JSON tiếng Việt bị lỗi ký tự | Giải mã bytes sai charset | Dùng UTF-8 hoặc charset đúng |
| WebFlux controller body rỗng | WebFilter subscribe body gốc trước | Bounded aggregation + request decorator |
| Netty báo memory leak | Không release DataBuffer sau consume | Kiểm tra join, release và cancellation |
| WebFlux Invalid reference count | Tái dùng pooled buffer đã release | Tạo DataBuffer mới hoặc quản lý retain/release |
| DataBufferLimitException | Codec/join vượt ngưỡng | Đặt giới hạn chủ đích, xử lý 413 và đánh giá memory |
| Payload lớn vẫn được nhận | Chỉ đặt ContentCaching cacheLimit | Enforce actual byte limit, proxy/server |
| Servlet async InputStream callback lỗi | Wrapper blocking-only | Dùng implementation đúng Servlet async contract |
| Filter được áp dụng quá rộng | Cache mọi path, gồm upload | Restrict media type/method/endpoint |
| Controller đúng nhưng filter sai thứ tự | Filter trước đã consume body | Kiểm tra Filter registration/order và Spring Security |
| Hệ thống chậm khi tải cao | Mỗi request copy body vào RAM | Giới hạn size, concurrency, GC và lựa chọn streaming |

Khi debug, hãy tìm **consumer đầu tiên** của body. Nếu Consumer A đã đọc trước khi wrapper được tạo thì wrapper đặt sau đó không thể khôi phục bytes nguyên thủy. Khi Security Filter hoặc middleware nào đó đã động tới body, thứ tự thực thi là yếu tố quan trọng.

## 17. Bảo mật và ngân sách bộ nhớ

Body có thể chứa password, token, OTP, email, dữ liệu tài chính, thông tin cá nhân hoặc file. Replay tạo thêm bản sao dữ liệu này trong heap.

Các nguyên tắc:

- Không log toàn bộ body theo mặc định trong production.
- Không giữ raw body trong static fields, session hoặc cache chung không có lifecycle.
- Whitelist/mask fields trước khi log; ưu tiên metadata request và số byte đã xử lý.
- Chỉ buffer những media type và endpoint cần thiết.
- Enforce giới hạn **byte** và request concurrency. Với nhiều request song song, tổng RAM có thể tăng theo kích thước body nhân số request và số bản sao.
- Tránh lưu raw body lâu hơn vòng đời request; không phụ thuộc GC để đáp ứng chính sách lưu giữ dữ liệu nhạy cảm.
- Không dùng cùng giải pháp cho file upload lớn hoặc streaming vô hạn.
- Kiểm thử 413, invalid JSON, body rỗng, timeout, client cancel, multipart excluded và security policy.
- Kiểm tra logging/tracing để tránh vô tình đưa raw body vào trace attributes.

Ví dụ: 1.000 request đồng thời, mỗi request giữ 64 KiB body, chỉ một bản sao đã cần khoảng 62,5 MiB trước khi tính overhead, decoder buffers, copy thêm và GC. Vì vậy, một cap nhỏ cho mỗi request vẫn không đồng nghĩa vô hại ở tải cao.

## 18. Quy trình áp dụng thực tế

1. **Xác định web stack:** Spring MVC hay WebFlux, đúng package và kiểu ApplicationContext.
2. **Nêu nhu cầu:** log, HMAC, validation, parser dùng một lần, hay bắt buộc replay raw bytes?
3. **Chọn đúng extension point:** Servlet Filter, RequestBodyAdvice hoặc WebFilter/ServerHttpRequestDecorator.
4. **Scope rõ:** đường dẫn, method, content type; tránh bắt multipart hoặc stream vô hạn.
5. **Đặt giới hạn byte:** trường hợp thiếu Content-Length, request chậm và body > limit.
6. **Giữ nguyên bytes:** đặc biệt nếu HMAC phụ thuộc payload nguyên thủy.
7. **Đảm bảo lifecycle:** Servlet synchronous/async và Netty DataBuffer retain/release.
8. **Kiểm thử cả hai consumers:** controller nhận DTO đúng sau khi Filter đã đọc, không chỉ test Filter độc lập.
9. **Kiểm thử lỗi:** 400/413, JSON malformed, empty body, cancel, concurrency, Unicode.
10. **Giám sát:** request latency, memory allocations, GC, 413 rate và buffer leak metrics/logs.

Nếu chỉ cần audit metadata hoặc logic trên DTO, bỏ hẳn replay layer thường là kiến trúc đơn giản hơn, nhanh hơn và ít rủi ro hơn.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 – ContentCachingRequestWrapper](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html): cơ chế cache những bytes đã được đọc, cache limit và overflow hook.
- [Spring Framework 6.2 – DataBufferUtils](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): join, maxByteCount, retain/release, error/cancellation.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled buffer lifecycle, doOnDiscard và release.
- [Spring Framework – WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): codec memory limits và streaming.
- [Spring Framework 6.2 – ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): getBody và mutate/decorator.
- [Spring Boot 3.5 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html).
- [Spring Boot 3.5 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html).

**Kết luận:** Request body là một stream, không tự động cho phép đọc lại. Trong MVC, ContentCachingRequestWrapper chỉ phù hợp để quan sát phần đã đọc; phát lại thật sự cần bounded HttpServletRequestWrapper cung cấp stream mới. Trong WebFlux, cần xử lý Flux<DataBuffer> trong một reactive pipeline có quản lý release/cancellation và cung cấp body mới qua ServerHttpRequestDecorator. Hãy ưu tiên parse một lần, chỉ buffer khi thực sự cần, giới hạn byte và kiểm thử cả error, async và resource lifecycle.