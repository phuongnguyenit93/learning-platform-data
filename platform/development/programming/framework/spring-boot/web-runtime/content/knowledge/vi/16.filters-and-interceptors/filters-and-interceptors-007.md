# ContentCachingRequestWrapper, ContentCachingResponseWrapper và giới hạn sử dụng trong Spring Boot

Khi viết servlet filter, người học thường muốn **đọc body của HTTP request và response** để audit, đo kích thước, tạo dấu vết khi debug hoặc tính checksum. Servlet API không cho phép mọi middleware đọc body bao nhiêu lần cũng được: request input stream thường được tiêu thụ theo luồng; response output stream là nơi server ghi dữ liệu trả về. Spring Framework cung cấp hai wrapper hữu ích:

- **ContentCachingRequestWrapper**: giữ bản sao những byte request **thực sự đã được downstream đọc**. Sau đó có thể lấy bản sao bằng getContentAsByteArray() hoặc getContentAsString().
- **ContentCachingResponseWrapper**: tạm giữ những byte mà downstream ghi vào response wrapper, cho phép đọc bản sao, rồi **phải gọi copyBodyToResponse()** để chuyển nội dung sang response gốc.

Hai lớp nằm trong package **org.springframework.web.util** và thuộc **Servlet stack**, dùng với **jakarta.servlet.http.HttpServletRequest/HttpServletResponse** trong Spring Boot 3.x. Chúng **không phải** công cụ tương đương cho một server chạy hoàn toàn trên Spring WebFlux + Reactor Netty.

Bài trình bày cơ chế thực tế, giới hạn quan trọng, ví dụ Spring Boot 3.5.x + Java 17+ có thể chạy bằng Maven, kiểm thử MockMvc và các trường hợp không nên sử dụng bộ nhớ đệm body này.

## 1. Bảng so sánh nhanh

| Câu hỏi | ContentCachingRequestWrapper | ContentCachingResponseWrapper |
|---|---|---|
| Bọc đối tượng nào? | HttpServletRequest | HttpServletResponse |
| Khi nào cache được tạo? | Khi downstream đọc input stream/reader hoặc luồng đọc tham số phù hợp | Khi downstream ghi output stream/writer của wrapper |
| Có tự đọc body ngay lúc khởi tạo? | **Không** | Không; chỉ chặn dữ liệu được ghi qua wrapper |
| Đọc cache bằng cách nào? | getContentAsByteArray(), getContentAsString() | getContentAsByteArray(), getContentInputStream(), getContentSize() |
| Có giới hạn cache theo constructor? | Có overload nhận contentCacheLimit | Không có overload hạn mức tương ứng trong API Spring Framework 6.2 |
| Nếu chưa ai đọc/ghi thì sao? | Cache có thể rỗng | Cache chưa có dữ liệu |
| Có cần copy body trở lại không? | **Không** | **Có**, gọi copyBodyToResponse() đúng thời điểm |
| Có biến request thành replayable body không? | **Không**; chỉ có bản sao đã tiêu thụ | Không liên quan input request |
| Điểm nguy hiểm nhất | Đọc quá sớm, hiểu sai cache limit, log dữ liệu nhạy cảm | Quên copy, buffer response lớn, streaming/async, error dispatch |
| Dùng ở đâu? | Servlet filter/Servlet MVC HTTP request | Servlet filter/Servlet MVC HTTP response |

**Ghi nhớ ngắn:** Request wrapper **quan sát phần đã đọc**; response wrapper **giữ phần đã ghi và cần chuyển tiếp**. Chúng không có cùng lifecycle và không thể dùng hoán đổi.

## 2. Servlet filter, DispatcherServlet và thời điểm quan sát body

Trong Spring Boot với spring-boot-starter-web:

~~~text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty/Undertow tùy cấu hình)
    |
    v
Servlet Filter chain
    |
    +-- ContentCachingRequestWrapper(request)
    +-- ContentCachingResponseWrapper(response)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping / Controller
    |       |
    |       +-- @RequestBody được đọc bởi HttpMessageConverter
    |       +-- Response DTO được serialize qua HttpMessageConverter
    |
    v
Filter tiếp tục sau chain.doFilter(...)
    |
    +-- requestWrapper.getContentAsByteArray()
    +-- responseWrapper.getContentAsByteArray()
    +-- responseWrapper.copyBodyToResponse()
    |
    v
Client nhận body response
~~~

Từ góc nhìn của filter:

- Code **trước** filterChain.doFilter(...) chạy trước khi controller và converter xử lý body.
- Code **sau** filterChain.doFilter(...) chạy khi phần downstream đồng bộ đã xong.
- Request cache được lấp đầy **trong lúc** controller/converter tiêu thụ request body.
- Response cache được lấp đầy **trong lúc** controller/converter ghi response body vào wrapper.
- Filter phải hoàn tất việc copy response body về response gốc đúng lifecycle.

Sơ đồ này dành cho **xử lý đồng bộ**. Nếu request khởi động Servlet async hoặc streaming, lệnh chain.doFilter() có thể trở về **trước khi response hoàn tất**. Khi đó không được dùng mẫu sync một cách mù quáng.

## 3. ContentCachingRequestWrapper: chỉ cache phần đã tiêu thụ

API Spring Framework 6.2:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 1024);

byte[] cachedBytes = wrapped.getContentAsByteArray();
String cachedText = wrapped.getContentAsString();
~~~

Đoạn code trên chỉ minh họa API; yêu cầu biến request kiểu HttpServletRequest và import org.springframework.web.util.ContentCachingRequestWrapper.

**Quan trọng:** ngay sau constructor, cachedBytes có thể là mảng rỗng dù HTTP request mang body thật. Wrapper **không chủ động đọc input stream**. Nó chỉ ghi nhận byte khi một bên phía sau gọi getInputStream()/getReader() và thực sự đọc dữ liệu.

Ví dụ:

~~~text
POST /api/demo/echo
Content-Type: text/plain

hello

T0: Filter tạo ContentCachingRequestWrapper
    cache = [] (0 bytes)

T1: Filter gọi filterChain.doFilter(wrapper, response)
    @RequestBody String đọc 5 bytes từ ServletInputStream
    cache = "hello" (5 bytes)

T2: Filter tiếp tục sau chain.doFilter
    getContentAsByteArray() = 5 bytes
~~~

Nếu endpoint không đọc request body (chẳng hạn GET /ping), cache request có thể vẫn bằng 0. Điều này là **hành vi đúng**, không phải wrapper bị hỏng.

### 3.1. Đọc cache trước chain không có tác dụng

Sai kỳ vọng:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 1024);

log.info("body={}", wrapped.getContentAsString());
filterChain.doFilter(wrapped, response);
~~~

Dòng log có thể in chuỗi rỗng, vì không ai đọc body trước đó. Để ghi nhận những byte đã được controller xử lý, hãy **đọc cached content sau khi downstream hoàn tất**.

### 3.2. Đừng cố đọc InputStream trong filter trước controller

Một số code cố "làm đầy cache" bằng:

~~~java
byte[] bytes = wrapped.getInputStream().readAllBytes();
filterChain.doFilter(wrapped, response);
~~~

Đây là **anti-pattern**. Việc đọc InputStream có thể tiêu thụ body của request, khiến @RequestBody phía sau nhận EOF hoặc body thiếu. ContentCachingRequestWrapper giữ bản sao đã đọc, nhưng **không tự quay ngược InputStream để controller đọc lại từ đầu**.

Nếu requirement thật sự là đọc body nhiều lần, cần một thiết kế riêng có giới hạn kích thước và wrapper replay input thích hợp. Không nên coi ContentCachingRequestWrapper là "re-readable request wrapper" hoàn chỉnh.

### 3.3. getContentAsByteArray và getContentAsString

- getContentAsByteArray(): trả byte[] chứa phần nội dung đã được cache.
- getContentAsString(): giải mã phần cache theo charset được cấu hình của wrapper, có từ Spring Framework 6.1.
- Byte length không đồng nghĩa số ký tự Unicode: một ký tự tiếng Việt có thể chiếm nhiều byte UTF-8.
- Nếu body là JSON, muốn hiểu cấu trúc hãy deserialize bằng công cụ JSON phù hợp sau khi kiểm soát privacy; không dùng substring tùy tiện với mọi body.
- Nếu Content-Type là multipart, octet-stream hoặc file upload, không chuyển thẳng byte[] thành String và log.

Trong một middleware đo dung lượng, chỉ cần **cache.length**. Không nên log nội dung body mặc định.

## 4. contentCacheLimit bảo vệ điều gì — và không bảo vệ điều gì?

Constructor:

~~~java
new ContentCachingRequestWrapper(request, 1024);
~~~

yêu cầu wrapper chỉ giữ **tối đa 1.024 byte bản sao của request body**. Nó **không**:

- từ chối HTTP request dài hơn 1.024 byte;
- làm controller chỉ đọc được 1.024 byte;
- cắt phần payload được chuyển đến business handler;
- bảo đảm toàn bộ body đã được cache;
- thay thế các giới hạn upload, JSON parser, proxy hoặc servlet container;
- tạo bảo đảm an toàn tuyệt đối về tổng bộ nhớ mà application dùng.

Nếu client gửi **2.048 ký tự ASCII** và controller đọc toàn bộ, controller vẫn có thể nhận đủ 2.048 ký tự, trong khi wrapper chỉ cache 1.024 byte đầu tiên.

~~~text
Request body trên wire:           2048 bytes ASCII
Giới hạn copy của request cache: 1024 bytes
Controller @RequestBody đọc:      2048 bytes
getContentAsByteArray():         1024 bytes
Kết luận: chỉ bị giới hạn bản SAO để quan sát
~~~

### 4.1. handleContentOverflow

Spring Framework cung cấp hook:

~~~java
protected void handleContentOverflow(int contentCacheLimit)
~~~

Hàm mặc định không thực hiện hành động nào. Khi lượng dữ liệu đọc vượt giới hạn, subclass **có thể** override hook để đưa ra phản ứng riêng.

Nhưng không tự suy luận rằng override hook để ném exception là cơ chế giới hạn upload production an toàn cho mọi luồng: cần hiểu khi nào body được đọc, cách container xử lý request, cách exception được map và trường hợp streaming/multipart. Để áp hạn mức request thật, hãy cấu hình/kiểm soát tại gateway, container, codec, endpoint hoặc service phù hợp.

### 4.2. Cache đạt đúng limit chưa chắc bị overflow

Nếu cache.length == 1024, có hai khả năng: body được đọc **đúng 1.024 byte**, hoặc body **lớn hơn** nhưng bản cache bị giới hạn. Không được tự gắn nhãn "TRUNCATED" chỉ dựa vào cache.length == limit. Nếu cần cờ overflow chính xác, thiết kế hook/metrics theo đặc tả và kiểm thử khi body vượt ngưỡng.

## 5. ContentCachingResponseWrapper: bản sao response cần được phát lại

Khác request wrapper, response wrapper chặn dữ liệu **được downstream ghi ra**:

~~~java
ContentCachingResponseWrapper wrapped =
        new ContentCachingResponseWrapper(response);

filterChain.doFilter(request, wrapped);

byte[] cachedResponse = wrapped.getContentAsByteArray();
wrapped.copyBodyToResponse();
~~~

Đoạn trên là **mẫu cho luồng sync thành công**. Production cần bảo đảm copy trong finally và xử lý async/errors riêng.

Khi controller gọi writer/output stream của wrapper, bytes được lưu lại trong wrapper thay vì được chuyển ngay đến underlying HttpServletResponse. Sau khi cần đo, ghi log đã được che dữ liệu hoặc tạo hash, phải gọi:

~~~java
wrapped.copyBodyToResponse();
~~~

để chuyển nội dung sang response thật. Nếu quên, HTTP client có thể nhận **body rỗng** hoặc không đầy đủ, dù controller đã tạo response đúng.

### 5.1. flushBuffer không thay copyBodyToResponse

Javadoc của ContentCachingResponseWrapper lưu ý **flushBuffer() không tự flush nội dung xuống client hoặc commit response gốc** khi body vẫn nằm trong wrapper. Muốn copy toàn bộ cached body, gọi copyBodyToResponse().

Không viết:

~~~java
wrapped.flushBuffer();  // KHÔNG thay thế copyBodyToResponse()
~~~

và cho rằng client chắc chắn đã nhận đủ response.

### 5.2. Không gọi copyBodyToResponse quá sớm

Nếu copy body khi controller hoặc một filter downstream **vẫn còn ghi tiếp**, ứng dụng có thể gặp dữ liệu thiếu, sai Content-Length, duplicate hoặc stream hỏng. Hãy xác định rõ thời điểm response đồng bộ đã hoàn tất. Mẫu finally sync ở phần demo chỉ hợp lệ vì các endpoint được giới hạn trong phạm vi đồng bộ, có body nhỏ.

### 5.3. Response wrapper không có contentCacheLimit tương ứng

Trong Spring Framework 6.2, ContentCachingResponseWrapper được tạo từ HttpServletResponse và **không có constructor public với contentCacheLimit tương ứng request wrapper**.

Điều này quan trọng vì:

- response nhiều MB có thể bị buffer trong bộ nhớ;
- việc gọi getContentAsByteArray còn tạo byte[] để inspect;
- nhiều concurrent requests khiến memory usage nhân lên;
- response streaming có thể bị chặn lại thay vì đến client từng phần;
- cache có thể tác động độ trễ/TTFB và áp lực GC.

Đừng tự cho rằng response cache bị giới hạn chỉ vì request cache được đặt 1 KiB. Nếu muốn đo dung lượng response lớn, cân nhắc một wrapper **đếm byte** không giữ nguyên body hoặc dùng metrics ở lớp khác.

## 6. Hai API không đồng nghĩa với replay body

Một số bài hướng dẫn dùng từ "caching" rồi suy ra:

~~~text
Read request lần 1 -> request wrapper -> read request lần 2 (SAI)
Write response -> caching response -> tự gửi client ngay   (SAI)
~~~

Thực tế:

- Request wrapper là **observer** của các lần đọc body đi qua nó; truy vấn cache là truy cập **bản sao đã tiêu thụ**, không rewind được nguồn.
- Response wrapper là **buffer** của dữ liệu write đi qua nó; khi kết thúc, cần copy dữ liệu sang response thật.
- Cả hai hoạt động trong Servlet I/O model, không thay thế reactive backpressure.
- Cả hai có thể bị ảnh hưởng bởi lớp filter khác bọc tiếp request/response, thứ tự execution và response đã commit.

Một wrapper replayable có thể phải tự lưu bản sao body đầy đủ, định nghĩa lại getInputStream và getReader cho một luồng có thể lặp, cung cấp đúng ServletInputStream.isReady/isFinished/setReadListener, xử lý charset, body size, multipart và async. Đây là một yêu cầu khác, không phải chức năng mặc định của ContentCachingRequestWrapper.

## 7. Khi nào nên và không nên dùng?

**Phù hợp khi:**

- Ứng dụng Spring MVC/Servlet đồng bộ, body nhỏ và kiểm soát được.
- Muốn quan sát **độ dài** request/response đã xử lý hoặc lưu checksum đã được cân nhắc.
- Có danh sách endpoint cụ thể được phép inspect, ví dụ JSON nội bộ không chứa PII.
- Muốn làm bằng chứng trong test rằng controller đã đọc request body và response trả bytes đúng.
- Có chính sách giới hạn/che dữ liệu trước khi log hoặc gửi telemetry.

**Không nên dùng trực tiếp kiểu sync buffering cho:**

- Spring WebFlux reactive server chạy trên Reactor Netty.
- Server-Sent Events (SSE) với text/event-stream.
- StreamingResponseBody, ResponseBodyEmitter và những phản hồi được ghi bất đồng bộ.
- File download lớn, video streaming, chunked transfer kéo dài.
- Multipart upload lớn hoặc nội dung nhị phân cần băng thông cao.
- API có dữ liệu nhạy cảm mà mục tiêu chỉ để log thô body.
- Response có nhiều filter phức tạp như compression, ETag, cache, signing, hoặc đã commit một phần.
- Các ứng dụng áp lực memory/latency cao nếu chưa profiling.

**Lưu ý:** đây là hướng dẫn chọn công cụ, không phải khẳng định mọi trường hợp async đều luôn không thể dùng bất kỳ caching wrapper nào. Có thể xây lifecycle/async-aware filter đúng, nhưng nó cần thiết kế và kiểm thử riêng; không được copy filter đồng bộ rồi mở rộng phạm vi một cách mù quáng.

## 8. Dự án mẫu Java 17+ Spring Boot 3.5.x

Dự án minh họa các giới hạn theo cách có thể kiểm chứng:

1. **POST /api/demo/echo** nhận text/plain, trả ECHO: + body; filter đo request bytes đã được controller đọc và response bytes được tạo.
2. **GET /api/demo/ping** không có request body, nên request cache là 0 byte.
3. **POST /api/demo/length** nhận chuỗi dài hơn request cache limit; controller vẫn trả đúng số ký tự trong khi request cache chỉ giữ tối đa 1.024 byte.
4. Filter **chỉ áp dụng cho /api/demo/**; các endpoint khác không bị buffer body.
5. Audit record **chỉ lưu metadata**, không lưu body hoặc exception message.
6. Response body vẫn tới client nhờ copyBodyToResponse() trong finally.

Dự án chỉ hỗ trợ **endpoint xử lý đồng bộ, body nhỏ** trong phạm vi demo. Không áp dụng filter này cho async/SSE/stream/file download ở production nếu chưa có logic riêng.

Cấu trúc:

~~~text
body-cache-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/cache/
    │   │   ├── BodyCacheApplication.java
    │   │   ├── EchoController.java
    │   │   ├── AuditRecord.java
    │   │   ├── AuditRecorder.java
    │   │   └── ContentCachingAuditFilter.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/cache/
            └── ContentCachingAuditTest.java
~~~

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>body-cache-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>body-cache-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không thêm spring-boot-starter-webflux. Spring Boot 3.5.x dùng package **jakarta.servlet**, không dùng javax.servlet trong source demo.

### 8.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: body-cache-demo
~~~

Demo không chứa dữ liệu đăng nhập hoặc file upload. Đặt request cache limit trong class filter để test ngắn gọn; trong ứng dụng thật nên đưa giới hạn quan sát vào config riêng, có đơn vị rõ ràng và kiểm soát môi trường.

### 8.3. BodyCacheApplication.java

~~~java
package com.example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(BodyCacheApplication.class, args);
    }
}
~~~

### 8.4. EchoController.java

~~~java
package com.example.cache;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class EchoController {

    @GetMapping(path = "/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String echo(@RequestBody String input) {
        return "ECHO:" + input;
    }

    @PostMapping(path = "/length",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Integer> length(
            @RequestBody String input) {
        return Map.of("characters", input.length());
    }
}
~~~

Các method đồng bộ, không dùng Callable, DeferredResult, StreamingResponseBody hoặc reactive publisher. Echo trả chuỗi qua Spring MVC StringHttpMessageConverter, còn length trả JSON bằng converter tương ứng.

Ở endpoint length, String.length() đếm **UTF-16 code units**, không phải số Unicode code points hoặc byte. Test dùng ký tự ASCII nên giá trị length cũng bằng số byte payload. Với tiếng Việt/emoji, số ký tự do người dùng cảm nhận có thể khác.

### 8.5. AuditRecord.java

~~~java
package com.example.cache;

public record AuditRecord(
        String method,
        String path,
        int requestBytesCached,
        int responseBytesCached,
        int status) {
}
~~~

Đây là một record metadata cho demo. Nó **không chứa raw request/response body**. Trong production, path có thể chứa ID nhạy cảm hoặc query parameters; vẫn cần chính sách tối thiểu hóa dữ liệu trước khi log/export.

### 8.6. AuditRecorder.java

~~~java
package com.example.cache;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.stereotype.Component;

@Component
public class AuditRecorder {

    private final Queue<AuditRecord> records =
            new ConcurrentLinkedQueue<>();

    public void record(AuditRecord event) {
        records.add(event);
    }

    public List<AuditRecord> snapshot() {
        return List.copyOf(records);
    }

    public void clear() {
        records.clear();
    }
}
~~~

AuditRecorder chỉ phục vụ **quan sát trong test**. Nó giữ sự kiện trong bộ nhớ không giới hạn; **không phải một hệ thống audit production**. Khi dùng thật, chọn metrics, tracing hoặc async structured logging với retention, sampling, backpressure, privacy, access control và chính sách giới hạn rõ ràng.

### 8.7. ContentCachingAuditFilter.java

~~~java
package com.example.cache;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;

@Component
public class ContentCachingAuditFilter
        extends OncePerRequestFilter {

    private static final int REQUEST_CACHE_BYTES = 1024;

    private final AuditRecorder recorder;

    public ContentCachingAuditFilter(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI()
                .substring(request.getContextPath().length());

        return !path.startsWith("/api/demo/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        ContentCachingRequestWrapper wrappedRequest =
                new ContentCachingRequestWrapper(
                        request, REQUEST_CACHE_BYTES);

        ContentCachingResponseWrapper wrappedResponse =
                new ContentCachingResponseWrapper(response);

        try {
            chain.doFilter(wrappedRequest, wrappedResponse);
        } finally {
            try {
                recorder.record(new AuditRecord(
                        request.getMethod(),
                        request.getRequestURI(),
                        wrappedRequest.getContentAsByteArray().length,
                        wrappedResponse.getContentSize(),
                        wrappedResponse.getStatus()));
            } finally {
                wrappedResponse.copyBodyToResponse();
            }
        }
    }
}
~~~

**Vì sao đoạn code này đúng cho demo đồng bộ?**

- shouldNotFilter giới hạn phạm vi bằng path, tránh tự động buffer toàn bộ ứng dụng.
- REQUEST_CACHE_BYTES=1024 giới hạn **bản sao request**, không tác động request thật.
- Filter không gọi getInputStream/readAllBytes trước controller.
- Thông tin request cache được đọc **sau** filter chain, khi @RequestBody đã được Spring MVC giải mã.
- Response bytes được đo bằng getContentSize; không cần tạo thêm một byte[] response.
- finally ngoài bảo đảm nỗ lực copy body sau khi filter chain kết thúc; finally trong bảo đảm vẫn copy ngay cả khi bước recorder gặp lỗi.
- copyBodyToResponse() là bước không thể bỏ để bảo đảm client nhận body.

**Giới hạn cực kỳ quan trọng:** đoạn filter **chỉ đúng cho xử lý Servlet đồng bộ đã kiểm soát**. Nó không theo dõi async lifecycle, chưa hỗ trợ error redispatch phức tạp, streaming, body rất lớn hoặc nhiều response wrappers cạnh tranh nhau. Dùng @Component ở đây để Spring Boot đăng ký filter đơn giản; nếu cần xác định order, dispatcher types và URL patterns trong production, ưu tiên FilterRegistrationBean hoặc cấu hình tương đương có chủ đích. Không tự thêm nhiều cơ chế đăng ký cho cùng filter khiến nó chạy hai lần.

### 8.8. Chạy ứng dụng

Từ thư mục body-cache-demo:

~~~bash
mvn test
mvn spring-boot:run
~~~

Sau khi server chạy cổng 8080:

~~~bash
curl -i \
  http://localhost:8080/api/demo/ping

curl -i \
  -X POST http://localhost:8080/api/demo/echo \
  -H "Content-Type: text/plain; charset=UTF-8" \
  -H "Accept: text/plain" \
  --data-binary "hello"

curl -i \
  -X POST http://localhost:8080/api/demo/length \
  -H "Content-Type: text/plain; charset=UTF-8" \
  -H "Accept: application/json" \
  --data-binary "abc"
~~~

Kết quả body của echo chính xác với input ASCII trong ví dụ:

~~~text
ECHO:hello
~~~

Kết quả JSON của length (thứ tự key không quan trọng):

~~~json
{"characters":3}
~~~

Không có endpoint công khai để đọc AuditRecorder; nó chỉ được dùng qua injection trong integration tests. Đây là cách tránh đưa dữ liệu audit nội bộ ra HTTP.

## 9. MockMvc tests: kiểm chứng hai wrapper và cache limit

**src/test/java/com/example/cache/ContentCachingAuditTest.java**

~~~java
package com.example.cache;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContentCachingAuditTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AuditRecorder recorder;

    @BeforeEach
    void resetEvents() {
        recorder.clear();
    }

    @Test
    void echoStillReachesClientAndBodiesAreObserved()
            throws Exception {

        mvc.perform(post("/api/demo/echo")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.TEXT_PLAIN)
                    .content("hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("ECHO:hello"));

        List<AuditRecord> events = recorder.snapshot();
        assertThat(events).hasSize(1);

        AuditRecord event = events.get(0);
        assertThat(event.requestBytesCached()).isEqualTo(5);
        assertThat(event.responseBytesCached()).isEqualTo(
                "ECHO:hello".getBytes(StandardCharsets.UTF_8).length);
        assertThat(event.status()).isEqualTo(200);
    }

    @Test
    void getWithoutBodyHasEmptyRequestCache() throws Exception {
        mvc.perform(get("/api/demo/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));

        List<AuditRecord> events = recorder.snapshot();
        assertThat(events).hasSize(1);
        assertThat(events.get(0).requestBytesCached()).isZero();
        assertThat(events.get(0).responseBytesCached())
                .isGreaterThan(0);
    }

    @Test
    void cacheLimitDoesNotLimitControllerInput()
            throws Exception {

        String input = "x".repeat(2048);

        mvc.perform(post("/api/demo/length")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(input))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.characters").value(2048));

        List<AuditRecord> events = recorder.snapshot();
        assertThat(events).hasSize(1);
        assertThat(events.get(0).requestBytesCached())
                .isEqualTo(1024);
    }

    @Test
    void unrelatedRouteIsNotWrapped() throws Exception {
        mvc.perform(get("/not-a-demo-route"))
                .andExpect(status().isNotFound());

        assertThat(recorder.snapshot()).isEmpty();
    }
}
~~~

**Ý nghĩa của từng test:**

- Test echo chứng minh response body vẫn tới client, tức copyBodyToResponse không bị quên.
- Test ping chứng minh request không có body có cache 0 byte, dù controller trả "pong".
- Test input 2048 chứng minh controller đọc đủ payload, trong khi cached request bytes giới hạn ở 1024.
- Test unrelated route chứng minh filter không được áp dụng cho mọi request.

Không assert độ dài byte response JSON khi chưa kiểm soát encoding/content type, vì serialization có thể làm output khác dự đoán. Dùng text/plain ASCII và UTF-8 để kiểm tra byte length một cách rõ ràng.

Chạy:

~~~bash
mvn test
~~~

Nếu test pass, Maven trả exit code 0. Ví dụ chưa chạy build trong tài liệu này; log và timings phụ thuộc máy và bộ dependency.

## 10. Vì sao cùng request mà filter có thể không thấy body?

Những nguyên nhân phổ biến:

1. Controller không hề đọc body: wrapper vẫn đúng, cache rỗng.
2. Filter đã bị skip bởi shouldNotFilter hoặc URL mapping khác.
3. Một filter **chạy trước** đã đọc body trên request gốc trước khi request được bọc.
4. Request body được đọc sau khi filter sync đã kết thúc do async processing.
5. Data được nhận từ form parameters hoặc multipart parser qua code path khác; cache có thể không đại diện mọi bytes wire-level.
6. Request bị security/gateway chặn sớm và body chưa hề được tiêu thụ.
7. Một lớp wrapper khác đang sử dụng request gốc hoặc thay đổi luồng body.
8. Exception xảy ra trước thời điểm đọc body.
9. Content cache đạt giới hạn nên chỉ thấy prefix, không phải toàn bộ body.

**Đừng sửa bằng cách đọc hết ServletInputStream trong filter**; cách đó có thể làm mất body của controller. Hãy xác nhận code path/downstream nào tiêu thụ input, thứ tự filter và dạng xử lý sync/async.

## 11. Servlet request parameters, form URL encoding và multipart

Request không chỉ gồm raw JSON hoặc text. Với form-urlencoded:

~~~http
POST /form HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&mode=basic
~~~

Một servlet container có thể parse form parameters khi getParameterMap/getParameter* được gọi. ContentCachingRequestWrapper có hỗ trợ ghi nhận dữ liệu tham số form trong những tình huống nhất định. Tuy nhiên, **không nên giả định cache luôn bằng đúng raw HTTP body byte-for-byte** của form submission; cơ chế parameter encoding/decoding và tình huống parse trước đó có thể ảnh hưởng.

Với multipart/form-data, file upload và metadata có thể được servlet container hoặc multipart resolver xử lý theo lifecycle riêng. Request cache giới hạn không phải công cụ đo hay lưu nguyên vẹn nội dung file. Không log multipart content hoặc upload bytes. Nếu chỉ cần kích thước upload, dùng thông tin multipart/metrics phù hợp ở lớp đã hiểu semantics của upload.

### 11.1. Charset và binary body

getContentAsString() dựa vào charset được cấu hình trên request. Nếu client gửi byte sequence không phù hợp charset hoặc sử dụng binary protocol, một bản giải mã String không thể đảm bảo tương đương payload gốc. Nếu cần digest/hash bytes, chỉ xử lý byte[] đã giới hạn và có chính sách bảo mật; đừng coi nó luôn là một chuỗi UTF-8.

Một JSON object còn có thể chứa password, token, số thẻ, hồ sơ sức khỏe hoặc dữ liệu cá nhân. Regex để xóa chuỗi nhạy cảm **không đủ tin cậy** để đảm bảo không lộ dữ liệu. Ưu tiên allowlist những field không nhạy cảm hoặc ghi metadata kích thước, status, request ID.

## 12. Async servlet request: khi chain.doFilter trả về sớm

Spring MVC hỗ trợ Callable, DeferredResult, WebAsyncTask, ResponseBodyEmitter và những cơ chế Servlet async khác. Trong trường hợp này:

~~~text
T0 Filter tạo request/response wrappers
T1 filterChain.doFilter(...)
T2 Controller bắt đầu xử lý async và trả control
T3 Filter finally chạy
T4 Async worker thực sự hoàn thành body response (muộn hơn)
~~~

Nếu gọi copyBodyToResponse tại **T3**, response có thể chưa có body cuối cùng. Nếu chỉ đọc request cache lúc T3, request body cũng có thể chưa được tiêu thụ hết trong một số thiết kế.

OncePerRequestFilter có các hook shouldNotFilterAsyncDispatch() và shouldNotFilterErrorDispatch(). Mặc định việc bỏ qua/đi qua một số dispatch có thể ảnh hưởng phạm vi wrapper, nhưng **chỉ override hook không tự giải quyết vòng đời cache và copy**.

Muốn hỗ trợ async đúng cần:

- Đảm bảo wrapper sống qua những giai đoạn async cần thiết.
- Xem lại listener/completion/error/timeout của Servlet async.
- Tránh copy quá sớm hoặc copy lặp.
- Hiểu filter chain có thể chạy lại trên ASYNC dispatch.
- Kiểm soát response đã committed và những bytes đã ghi.
- Viết test với DeferredResult, Callable, timeout và lỗi giữa chừng.

Bài mẫu **cố ý không hỗ trợ Servlet async** để không đưa ra một giải pháp tưởng như phổ quát nhưng sai lifecycle.

## 13. Streaming, SSE và response lớn: không buffer cả luồng

Hãy tưởng tượng endpoint:

~~~java
@GetMapping(path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    return new SseEmitter();
}
~~~

Đây là đoạn minh họa Spring MVC, không nằm trong demo runnable. SSE cần gửi dữ liệu theo thời gian; nếu bọc bằng response cache và chỉ copy sau khi kết thúc, client có thể không nhận event kịp thời, hoặc response giữ lâu làm bộ nhớ tăng.

Những trường hợp tương tự:

- StreamingResponseBody ghi từng chunk vào OutputStream.
- Video/file download lớn.
- Server giữ kết nối dài, long polling.
- Proxy compression/gzip xử lý response qua một wrapper khác.
- HTTP range requests với status 206 Partial Content.
- Response attachment chứa dữ liệu nhị phân.

**Một response wrapper không có cache size cap nên không phù hợp để giữ toàn bộ body lớn trong memory.** Nếu cần đo "đã gửi bao nhiêu bytes", hãy dùng counting stream/metrics đúng layer thay vì copy toàn bộ response.

Ngay cả endpoint đồng bộ nhưng trả 100 MB cũng không nên bị cache nếu mục tiêu chỉ là ghi request method + response status.

## 14. Quản lý exception, error dispatch và finally

Sử dụng finally cho việc copy trong filter sync là rất quan trọng, nhưng chưa đủ cho mọi trường hợp lỗi.

Nếu downstream ném exception trước khi tạo response, Servlet container hoặc Spring Boot có thể thực hiện error dispatch/response rendering ở lifecycle khác. Một response wrapper đã cache một phần body có thể chứa dữ liệu chưa hoàn chỉnh. Trong trường hợp này, mù quáng copy bytes có thể khiến error body bị sai hoặc ghi nội dung dở dang.

**Do đó:**

1. Trong demo chỉ dùng những controller sync thành công.
2. Với error handling production, xác định error response được dựng ở cùng dispatch hay dispatch khác.
3. Không coi shouldNotFilterErrorDispatch() là thứ duy nhất cần thay.
4. Tránh copy response body nếu response gốc đã committed/đang bị error dispatch theo cơ chế khác, trừ khi logic đã được thiết kế rõ.
5. Test các trường hợp @ExceptionHandler, @ControllerAdvice, sendError, exception ném trực tiếp và timeout.
6. Không nuốt exception bằng catch(Exception) rồi trả 200 để giữ response body.

Response cache không phải transactional buffer. Nếu một nửa body đã viết và controller lỗi, không bảo đảm có thể rollback trạng thái network an toàn.

## 15. Thứ tự filter và tác động tới Spring Security, compression, ETag

Trong Servlet stack, nhiều filter có thể chạy trước/sau nhau:

~~~text
Filter A -> Filter B -> DispatcherServlet -> Filter B -> Filter A
~~~

Nếu một filter ghi nén gzip, một filter tính ETag và một filter cache response, **thứ tự ảnh hưởng nội dung nào được nhìn thấy**: bytes JSON gốc hay bytes đã nén, headers Content-Encoding/Content-Length đã được thiết lập hay chưa, response đã commit hay chưa.

### 15.1. ShallowEtagHeaderFilter

Spring Framework có ShallowEtagHeaderFilter sử dụng response content caching để tính shallow ETag từ bytes response. Nếu ứng dụng đã dùng filter này, thêm một response caching wrapper riêng có thể tạo nhiều tầng buffer không cần thiết và làm sai cách copy khi code tự quản lý thiếu cẩn thận.

Nếu mục tiêu chỉ là hỗ trợ conditional GET hoặc ETag, xem công cụ sẵn có thay vì viết một body-caching filter chung.

### 15.2. Spring Security

Security filter chain có thể từ chối request trước khi controller đọc body. Nếu filter audit nằm sau security thì không thấy request bị chặn; nếu nằm trước security có thể log request mà không được phép lưu dữ liệu nhạy cảm.

Không đọc/chuyển body trong filter chỉ để phục vụ authentication khi đã có Spring Security và cơ chế credentials chuẩn. Không log Authorization header, cookie, CSRF token, password hoặc raw body. Authorization và caching body là hai trách nhiệm khác nhau.

### 15.3. FilterRegistrationBean và ordering

Với use case production, có thể chủ động đăng ký Servlet Filter qua FilterRegistrationBean để xác định URL patterns và order. Nhưng không đăng ký cùng một filter qua cả @Component và FilterRegistrationBean theo kiểu khiến nó chạy lặp.

Chỉ thêm @Order hoặc đặt số order khi có lý do đã kiểm thử; thứ tự filter ảnh hưởng request body đã bị ai tiêu thụ, response body đã được encode/nén chưa, cũng như filter nào nhìn thấy exception.

## 16. Phân biệt với HandlerInterceptor

Servlet **HandlerInterceptor** chạy quanh các handler của Spring MVC. Nó rất phù hợp để quan sát:

- handler method/route;
- request start/end timing;
- status và handler metadata;
- thông tin không phụ thuộc raw body.

Nhưng interceptor không thay Servlet request/response bằng wrapper theo cách filter làm. Nếu cần quan sát byte-level body, filter thường là vị trí thích hợp hơn, với điều kiện hiểu lifecycle.

Các callback preHandle, postHandle, afterCompletion không bảo đảm có một response body buffer để đọc; postHandle còn không được gọi theo cách người mới kỳ vọng với @ResponseBody hoặc async processing.

Nếu use case chỉ là "đo latency mỗi route", cân nhắc Micrometer/observations hoặc HandlerInterceptor thay vì buffer response body.

## 17. Phân biệt Servlet wrapper với Spring WebFlux

Cặp ContentCachingRequestWrapper/ContentCachingResponseWrapper dùng:

~~~java
jakarta.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletResponse
~~~

Trong ứng dụng WebFlux reactive server:

~~~java
org.springframework.http.server.reactive.ServerHttpRequest
org.springframework.http.server.reactive.ServerHttpResponse
org.springframework.web.server.ServerWebExchange
~~~

Đó là **những abstraction khác nhau**. WebFlux không có ServletInputStream/ServletOutputStream như API chính. Không ép dùng ContentCachingRequestWrapper bên trong WebFilter của Reactor Netty.

Nếu bắt buộc quan sát body trong WebFlux, cần thiết kế decorator tương ứng (ServerHttpRequestDecorator/ServerHttpResponseDecorator) và hiểu DataBuffer, reference counting, reactive streams, backpressure, cancellation, codec. Thiết kế đó phải giới hạn memory và không phá subscription; không copy thẳng mã Servlet filter sang WebFilter.

**Chú ý Spring Boot khi có hai starter:** nếu project có cả spring-boot-starter-web và spring-boot-starter-webflux, Boot thường ưu tiên MVC/Servlet trừ khi cấu hình application type. Vì vậy, việc có WebClient hoặc WebFlux dependency không có nghĩa server đang chạy reactive.

## 18. Các lựa chọn thay thế an toàn hơn

| Mục tiêu thật | Phương án nên cân nhắc |
|---|---|
| Đo số request/status/latency | Micrometer HTTP server observations |
| Audit hành động nghiệp vụ | Event tại application service với các field được phép |
| Trace request qua các service | Distributed tracing, trace ID, correlation ID |
| Log method, URI, header chọn lọc | CommonsRequestLoggingFilter hoặc filter nhỏ, tránh body |
| Log prefix request body rất nhỏ, đã lọc dữ liệu | AbstractRequestLoggingFilter/CommonsRequestLoggingFilter với max payload thích hợp; phải kiểm tra privacy |
| Tính ETag cho response phù hợp | ShallowEtagHeaderFilter hoặc cơ chế caching HTTP được framework hỗ trợ |
| Đếm response bytes lớn | Counting output stream/metrics ở layer phù hợp, không giữ raw body |
| Validate JSON schema | DTO + Jakarta Validation + business checks |
| Chặn upload/body quá lớn | Servlet container, gateway, endpoint/server limits; không chỉ request cache limit |
| Đọc request body nhiều lần | Replay wrapper chuyên dụng có giới hạn, giữ đúng Servlet semantics |
| Observability cho WebFlux | WebFilter/reactive observations, không dùng Servlet wrappers |

Đừng chọn body caching chỉ vì nó dễ demo. Chọn giải pháp ít quyền truy cập dữ liệu và ít tác động latency nhất đáp ứng được yêu cầu vận hành.

## 19. Checklist vận hành và bảo mật

Trước khi triển khai một filter đụng request/response body, cần trả lời:

- [ ] Ứng dụng chạy Spring MVC/Servlet, không phải WebFlux reactive server?
- [ ] Có thực sự cần body, hay chỉ cần request ID/method/status/latency?
- [ ] Đã giới hạn chính xác URL/method/content-type nào được bọc chưa?
- [ ] Request cache limit đã được đặt bằng byte, không nhầm với max request size?
- [ ] Có hiểu getContentAsByteArray() có thể rỗng hoặc chỉ chứa prefix không?
- [ ] Không đọc getInputStream() trước controller chỉ để làm đầy cache?
- [ ] Response wrapper có được copyBodyToResponse() đúng lifecycle không?
- [ ] Có test body response đến client nguyên vẹn sau filter không?
- [ ] Đã loại async, streaming, SSE, file upload/download lớn chưa?
- [ ] Có xem error dispatch, timeout, sendError và response committed chưa?
- [ ] Có kiểm tra compression, ETag, cache, gateway và Spring Security filter ordering?
- [ ] Không log raw credentials, Authorization, cookie, token, PII, financial/health data?
- [ ] Có định nghĩa retention, masking, access control, sampling và không tăng memory vô hạn?
- [ ] Có test payload lớn hơn request cache limit để xác nhận controller vẫn đọc đủ?
- [ ] Có test concurrency/load để đo response buffer memory và latency?
- [ ] Không đăng ký filter hai lần qua @Component và FilterRegistrationBean?
- [ ] Có chiến lược riêng cho multipart/form-urlencoded và charset?
- [ ] Có test HEAD, 204 No Content và các response không có body nếu phạm vi bao gồm chúng?

## 20. Những lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Request cache luôn rỗng | Đọc cache trước chain hoặc controller không đọc body | Đọc sau downstream, kiểm tra đường đi thực |
| Controller @RequestBody nhận rỗng | Filter đã đọc InputStream trước controller | Không đọc sớm; cân nhắc replay wrapper riêng nếu cần |
| Cache chỉ có 1024 bytes dù payload 2048 | contentCacheLimit chỉ giới hạn bản sao | Đừng gọi đó là truncation của request thật |
| Client nhận response body rỗng | Quên copyBodyToResponse | Copy ở lifecycle sync đúng, kể cả finally |
| Gọi flushBuffer nhưng client vẫn không có body | Response wrapper flushBuffer không chuyển cached body | Gọi copyBodyToResponse |
| Memory tăng khi download lớn | Response wrapper buffer toàn bộ output | Không bọc file lớn; dùng metrics/counting |
| SSE không đến từng event | Body bị giữ trong wrapper | Bỏ response buffering hoặc thiết kế streaming-aware |
| 2048 ký tự Unicode khác số bytes cache | UTF-8/charset nhiều byte | Phân biệt bytes, code units và code points |
| JSON log chứa password/token | Log raw request/response body | Tắt raw body, allowlist metadata, privacy review |
| Lỗi khi có async/DeferredResult | chain.doFilter trả về trước khi async hoàn tất | Thiết kế lifecycle async riêng, không dùng filter sync mẫu |
| 500/error response lạ sau filter | Error dispatch, response committed hoặc copy sai thời điểm | Test exception handling và dispatch |
| Content-Length không khớp | Multiple wrappers, copy quá sớm, compression | Xem thứ tự filter, copy và headers |
| Một số endpoint không được audit | shouldNotFilter/URL pattern, security chặn trước | Xác định scope và filter order |
| WebFlux code không compile với wrapper | Import Servlet wrapper vào reactive server | Dùng reactive request/response decorator khác |
| Multipart cache không đúng raw wire body | Container parser/form semantics | Quan sát multipart ở layer đúng |
| AuditRecorder phình bộ nhớ | Demo lưu Queue không giới hạn | Dùng bounded metrics/logging infrastructure |
| Lỗi log làm response bị ảnh hưởng | Log/metrics ném exception trong filter | Cách ly audit failures, ưu tiên bảo toàn HTTP response |

## 21. Mẫu tư duy debug theo thời gian

Khi gặp bug do caching wrapper, hãy ghi lại các mốc:

~~~text
T0 Bắt đầu request: URL/method/content type?
T1 Filter có thật sự chạy không? Đứng trước/sau filter nào?
T2 Ai đang giữ request wrapper? Có ai đã đọc InputStream?
T3 Có @RequestBody hay converter nào đọc body không?
T4 Controller trả sync, async, stream hay exception?
T5 Response writer đã viết bao nhiêu bytes vào wrapper?
T6 filterChain.doFilter() đã kết thúc sync thật chưa?
T7 Đã gọi copyBodyToResponse() chưa? Response committed chưa?
T8 Client nhận status/headers/body thực tế ra sao?
~~~

Một số kỹ thuật hiệu quả:

- Dùng MockMvc kiểm tra sync filter và controller.
- Dùng integration test với embedded server khi cần quan sát network, compression, chunked/async semantics.
- Dùng payload ASCII có length cố định để phân biệt số byte và số ký tự.
- Đặt assertion riêng cho response body, không chỉ HTTP 200.
- Không dựa vào log để kết luận request đã được đọc hết.
- Thử body dài hơn cache limit để chứng minh giới hạn cache không giới hạn input.
- Test riêng raw text, JSON, form, multipart khi phạm vi thực sự hỗ trợ.
- Dùng profiling/metrics để đánh giá memory của response caching.

## 22. Kết luận

**ContentCachingRequestWrapper** giữ một **bản sao có giới hạn** của những byte request đã được downstream đọc. Nó **không tự tiêu thụ body** và **không cho phép controller đọc lại request tùy ý**. contentCacheLimit là giới hạn của phần cache, không phải giới hạn upload/request thực tế.

**ContentCachingResponseWrapper** giữ những byte downstream đã ghi vào wrapper. Để client nhận đúng response, **phải gọi copyBodyToResponse()** tại thời điểm phù hợp. Nó không có giới hạn cache constructor tương ứng và có thể gây tăng memory/latency nếu áp dụng cho response lớn hoặc stream.

Trong Spring Boot MVC/Servlet, có thể dùng chúng cho **những endpoint đồng bộ, body nhỏ, đã kiểm soát dữ liệu**. Không đưa filter đồng bộ vào async/SSE/streaming chỉ bằng cách thêm vài hook; cần thiết kế khác. Để logging/metrics sản xuất, ưu tiên dữ liệu tối thiểu, hạn mức rõ, không lưu body nhạy cảm và kiểm thử lifecycle thực.

## Tài liệu chính thức

- [Spring Framework 6.2 — ContentCachingRequestWrapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html)
- [Spring Framework 6.2 — ContentCachingResponseWrapper API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/ContentCachingResponseWrapper.html)
- [Spring Framework 6.2 — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
