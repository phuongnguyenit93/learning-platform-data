# Bọc request/response để đọc nội dung và giới hạn bộ nhớ trong Spring MVC

> **Bối cảnh:** Spring Web MVC dùng Servlet API (`jakarta.servlet.*`) trên Java 17+, ví dụ Spring Boot 3.x / Spring Framework 6.x. Chủ đề tập trung vào **`HttpServletRequestWrapper`, `HttpServletResponseWrapper`, `ContentCachingRequestWrapper` và `ContentCachingResponseWrapper`**, việc đọc HTTP body mà không phá luồng xử lý, cũng như **kiểm soát lượng bộ nhớ được giữ để ghi log/quan sát**. Phải phân biệt rõ ba giới hạn: **kích thước cache**, **kích thước payload được chấp nhận**, và **bộ nhớ của toàn pipeline (converter, file upload, service)**.

## 1. Vì sao cần bọc request và response?

Trong Servlet stack, HTTP body được đọc/ghi dưới dạng stream. Một Filter có thể muốn đo hoặc quan sát:

- Request method, URL, status, thời gian thực thi.
- Một bản xem trước nhỏ (preview) của request body khi người dùng gọi JSON/text API.
- Một bản xem trước nhỏ của response body để chẩn đoán lỗi trong môi trường thử nghiệm.
- Số byte response được ghi, giúp phân tích dữ liệu lớn mà không giữ toàn bộ trong RAM.
- Việc từ chối upload hoặc JSON body quá lớn bằng chính sách giới hạn độc lập.

Cách làm nguy hiểm:

```java
// KHÔNG dùng khi body có thể rất lớn.
byte[] all = request.getInputStream().readAllBytes();
System.out.println(new String(all, StandardCharsets.UTF_8));
chain.doFilter(request, response);
```

Đoạn code minh họa này có hai vấn đề:

1. `readAllBytes()` có thể giữ **toàn bộ request body** trong heap. Request vài trăm MiB có thể gây áp lực GC hoặc `OutOfMemoryError`.
2. Nó **tiêu thụ request input stream trước** khi controller và `HttpMessageConverter` đọc; nếu không có cơ chế replay hoàn chỉnh, `@RequestBody` sau đó sẽ không còn body và có thể nhận lỗi.

Response cũng có vấn đề tương tự: gom body vào `ByteArrayOutputStream` không giới hạn để ghi log có thể khiến server giữ nhiều bản sao của một file hoặc một JSON response lớn.

**Mục tiêu đúng:** cho phần còn lại của ứng dụng tiếp tục đọc/ghi body bình thường, chỉ giữ tối đa một lượng byte đã định (ví dụ **1024 byte mỗi chiều/request**) để quan sát, và **đừng nhầm con số ấy là hard limit cho toàn bộ HTTP body**.

## 2. Kiến trúc Servlet wrapper

`HttpServletRequestWrapper` và `HttpServletResponseWrapper` thuộc package `jakarta.servlet.http` trong Spring Boot 3.x. Chúng thực thi Decorator pattern: chứa request/response thật, mặc định delegate các phương thức xuống đối tượng gốc và cho phép override một số method.

```text
Client HTTP request
   |
Servlet Filter
   | new RequestWrapper(originalRequest)
   | new ResponseWrapper(originalResponse)
   |
   v
chain.doFilter(requestWrapper, responseWrapper)
   |
   v
DispatcherServlet
   |
Controller @RequestBody -> HttpMessageConverter đọc wrapper.getInputStream()
   |
Controller trả DTO / String / Resource
   |
HttpMessageConverter -> wrapper.getOutputStream() / wrapper.getWriter()
   |
   v
Servlet container truyền bytes đến client
   |
Filter ghi thống kê bounded preview, status, thời gian (nếu sync)
```

Ví dụ hình dạng tối giản:

```java
class MyRequestWrapper extends HttpServletRequestWrapper {
    MyRequestWrapper(HttpServletRequest request) {
        super(request);
    }
}

class MyResponseWrapper extends HttpServletResponseWrapper {
    MyResponseWrapper(HttpServletResponse response) {
        super(response);
    }
}
```

Đây là fragment mô tả các lớp base, không phải demo hoàn chỉnh. Một wrapper chỉ delegate sẽ không tự cache được body. Muốn đọc hoặc quan sát body, phải dùng wrapper Spring có sẵn hoặc override cách đọc/ghi stream một cách đúng chuẩn Servlet.

**Không tự ý sửa byte body:** nếu wrapper thay body nhưng vẫn giữ `Content-Length`, charset, `Content-Encoding` hoặc chữ ký HMAC cũ, downstream sẽ đọc sai hoặc signature không hợp lệ. Bài này chủ yếu **quan sát**, không biến đổi nội dung.

## 3. Tại sao request body thường chỉ đọc được một lần?

`HttpServletRequest.getInputStream()` cho phép đọc HTTP entity body dưới dạng byte; `getReader()` cho phép đọc qua `Reader` với character encoding. Chúng là **hai cách truy cập thay thế nhau**, không được trộn tùy tiện trên cùng request theo hợp đồng Servlet.

Trong Spring MVC:

```java
@PostMapping(path = "/echo", consumes = MediaType.TEXT_PLAIN_VALUE)
@ResponseBody
String echo(@RequestBody String body) {
    return "echo:" + body;
}
```

Đây là method minh họa: message converter cần đọc body từ request stream để tạo `String`. Nếu Filter đã đọc hết stream, converter không thể tự tua lại như đọc file thông thường.

### 3.1. Các cách tiếp cận

| Cách | Có tiêu thụ stream trước handler? | Bộ nhớ | Dùng khi nào? |
| --- | --- | --- | --- |
| Filter đọc `readAllBytes()` trước `doFilter` | **Có** | Theo toàn body, không an toàn nếu không chặn | **Tránh** |
| `ContentCachingRequestWrapper(request, limit)` rồi downstream tự đọc | **Không** chủ động đọc trước | Cache tối đa `limit` byte được đọc | Logging/observability request đã tiêu thụ |
| Tự dựng replayable request từ một bounded byte array | **Có**, nhưng wrapper trả lại stream từ bản đã lưu | Tối đa hard cap đặt trước, thêm copy nếu không cẩn thận | Chỉ khi thật sự cần đọc trước và replay body nhỏ |
| Tee request stream, giữ prefix hữu hạn trong quá trình downstream đọc | **Không** chủ động đọc trước | Theo giới hạn preview | Đếm/ghi sample an toàn, nâng cao |
| Parse JSON/DTO trong controller/service | Framework đọc đúng một lần | Theo converter/object graph | Xử lý nghiệp vụ, không thay audit filter |

Điểm quan trọng: **khả năng xem lại những byte đã đi qua** và **khả năng cho downstream đọc lại cùng body** là hai tính năng hoàn toàn khác nhau.

## 4. ContentCachingRequestWrapper: cache chỉ những gì đã được đọc

Spring cung cấp:

```java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 1024);
chain.doFilter(wrapped, response);
byte[] preview = wrapped.getContentAsByteArray();
```

Đây là fragment trong Filter, không phải chương trình độc lập. Converter/controller đọc body qua `wrapped`; khi đó wrapper sao lưu **tối đa 1024 byte** đã được tiêu thụ. Nếu handler **không đọc body**, cache có thể **rỗng**. `getContentAsByteArray()` trả nội dung **đã được đọc tới thời điểm gọi**, không tự đọc toàn request.

Theo Javadoc Spring Framework 6.2, constructor nhận `contentCacheLimit` để giới hạn cache; với các nhánh bản vá mới của Spring 6.2, constructor không truyền limit còn bị deprecate để khuyến khích đặt ngưỡng cụ thể. **Luôn dùng constructor có limit dương** cho logging.

### 4.1. Giới hạn cache KHÔNG phải giới hạn tải lên

Giả sử HTTP body dài **10 MiB**, còn limit là **1024 byte**. Sau khi `@RequestBody` đọc đủ, converter vẫn có thể nhận và deserialize toàn 10 MiB; `ContentCachingRequestWrapper` chỉ lưu tối đa 1024 byte trong **cache của wrapper**.

| Đại lượng | Trong ví dụ |
| --- | --- |
| HTTP request body thực | 10 MiB |
| `contentCacheLimit` | 1024 byte |
| `getContentAsByteArray().length` sau khi downstream đọc | Tối đa 1024 byte |
| Số byte converter được phép đọc | **Không bị chặn** bởi cấu hình cache này |
| Giới hạn heap của JSON tree/DTO | **Không được bảo đảm** bởi cấu hình cache |

Default của `handleContentOverflow(int limit)` ở wrapper là không làm gì. Nó **không mặc định trả 413 Payload Too Large** khi vượt cache limit. Có thể override hook, nhưng exception xảy ra trong lúc đọc stream và cần xử lý an toàn về filter/response commitment; không nên cho rằng override một hook là chính sách giới hạn upload đầy đủ.

### 4.2. Có phải ContentCachingRequestWrapper cho phép đọc body lần thứ hai?

Không. Nó cung cấp API đọc **bản sao cache** sau khi body được tiêu thụ, chứ không mặc định “rewind” toàn input stream cho `@RequestBody` đọc lại một lần nữa. Đặc biệt khi body lớn hơn `contentCacheLimit`, cache còn **không chứa toàn body**.

Nếu thật sự cần request được đọc lại:

1. Chọn một **hard cap hữu hạn** cho toàn body.
2. Đọc tối đa `cap + 1` byte (không dùng `readAllBytes()`) trước khi quyết định nhận/từ chối.
3. Từ chối với **413 Content Too Large** nếu vượt giới hạn, bao gồm trường hợp client không gửi `Content-Length`.
4. Với body hợp lệ, dựng custom `HttpServletRequestWrapper` trả `ServletInputStream` mới từ mảng đã lưu; xử lý cả `getReader()`, encoding, `isFinished`/`isReady`/`setReadListener` đúng Servlet API.
5. Với nonblocking/async/multipart, phải xét các yêu cầu tương thích bổ sung; tốt nhất dùng cơ chế chuyên dụng của container hoặc codec.

Cách đọc trước/replay luôn phải cân nhắc memory amplification do nhiều request đồng thời. Nếu chỉ cần logging, **không replay**; dùng cache-on-read có limit là đơn giản hơn.

## 5. ContentCachingResponseWrapper: dễ dùng nhưng có thể giữ toàn bộ response

Spring có `ContentCachingResponseWrapper`:

```java
ContentCachingResponseWrapper wrapped =
        new ContentCachingResponseWrapper(response);
try {
    chain.doFilter(request, wrapped);
    byte[] body = wrapped.getContentAsByteArray();
    // Chỉ dùng khi chắc response nhỏ hoặc đã có kiểm soát.
} finally {
    wrapped.copyBodyToResponse();
}
```

Đây là ví dụ **pattern sync được giản lược**, không nên copy vào production không giới hạn kích thước, async/error dispatch hoặc các luồng đã committed. Điểm cực kỳ quan trọng:

- `ContentCachingResponseWrapper` giữ những byte response được ghi qua nó trong buffer nội bộ.
- `getContentAsByteArray()` trả bản sao của **nội dung response được cache**.
- Phải gọi `copyBodyToResponse()` trong mô hình sử dụng sync thông thường để **chuyển nội dung cache sang response gốc**. Quên lệnh này có thể khiến client nhận body rỗng/bị thiếu.
- `flushBuffer()` trên wrapper **không đồng nghĩa** đẩy body qua response gốc trước khi copy; cần hiểu behavior của wrapper.
- API thông dụng của lớp này **không có constructor `(response, maxBytes)`** để giới hạn toàn cache như request wrapper.

Ví dụ response 100 MiB từ `@ResponseBody` có thể khiến wrapper giữ cỡ 100 MiB (chưa kể serializer/DTO/array copy), trước khi copy sang client. Nếu 100 requests như vậy chạy đồng thời, chỉ phần cache lý thuyết đã lên tới **~10 GiB**, không tính overhead. **Tránh bọc toàn bộ response bằng ContentCachingResponseWrapper nếu endpoint có body lớn hoặc không dự đoán được.**

### 5.1. `copyBodyToResponse()` không phải bảo đảm an toàn bộ nhớ

Nó giải quyết việc **phát body ra client** sau khi đã cache, chứ không làm quá trình cache trở thành streaming bounded-memory. Cách dùng này phù hợp với những trường hợp có chủ đích cần toàn response để tính ETag hoặc kiểm thử body nhỏ. Ví dụ `ShallowEtagHeaderFilter` sử dụng kỹ thuật buffering để tính ETag; điều đó có trade-off memory/latency.

### 5.2. Vì sao response streaming cần cách khác?

Một endpoint `Resource`/file lớn, `StreamingResponseBody`, SSE, chunked transfer hoặc async rendering có thể cần đẩy bytes liên tục. Giữ toàn body trong heap vừa không phù hợp mục tiêu streaming, vừa có thể làm sai latency hoặc quên flush/copy.

Muốn **chỉ quan sát một prefix nhỏ của response**, nên dùng **tee wrapper**: byte nào được ghi thì vừa chuyển tiếp ngay tới Servlet output stream gốc, vừa sao lưu **tối đa N byte đầu**, và đếm tổng số byte đã đi qua wrapper.

## 6. Bounded preview: tách việc quan sát khỏi body size

Một implementation hợp lý cho logging:

```text
Controller writes byte[] / JSON / String
             |
             v
Response tee ServletOutputStream
     |
     +-----> output stream gốc -> client (ghi toàn bộ)
     |
     +-----> preview buffer (tối đa 1024 byte)
     |
     +-----> counter (số byte đi qua)
```

Với response **100 KiB**, preview 1024 byte:

- Client vẫn nhận **đầy đủ 100 KiB**.
- Tee wrapper chỉ giữ **tối đa 1024 byte**.
- Counter ghi nhận số byte đi qua wrapper; không cần tạo `byte[100KiB]` để làm log.
- Nếu controller đã sinh một `String` 100 KiB hoặc một DTO rất lớn, bộ nhớ **của controller/serializer** vẫn phải được quản lý riêng. Bounded tee chỉ giới hạn **bộ nhớ phụ của wrapper**.

### 6.1. Một lưu ý quan trọng về `getWriter()`

Servlet response có hai cách ghi:

- `getOutputStream()` cho binary và converter output.
- `getWriter()` cho character text theo encoding.

Một wrapper phải xử lý **cả hai**. Với cùng response, ứng dụng không được gọi lẫn `getWriter()` và `getOutputStream()` như hai output mode độc lập; chúng loại trừ nhau theo hợp đồng Servlet. Nếu override một method và bỏ qua method kia, bạn có thể log được binary nhưng bỏ sót response HTML/text, hoặc ngược lại.

### 6.2. Giữ nguyên trạng thái `isReady()` và write listener

`ServletOutputStream` có `isReady()` và `setWriteListener(...)` cho nonblocking I/O. Nếu custom wrapper chỉ implement `write(int)` rồi trả `isReady()=true` bất kể stream gốc, code async có thể ghi vào stream chưa sẵn sàng hoặc phá contract. Delegate các API readiness/listener xuống stream gốc. Điều này **không tự biến wrapper thành async-aware hoàn chỉnh**: vòng đời async vẫn phải được thiết kế/kiểm thử riêng.

### 6.3. Dữ liệu nào nên giữ lại?

Mặc định tốt nhất là **không ghi raw body**. Ngay cả 1024 byte đầu cũng có thể chứa password, email, bearer token, thông tin y tế hoặc bí mật. Thường chỉ nên log metadata:

```text
method=POST path=/api/echo status=200
request_cached_bytes=5
response_observed_bytes=10
response_preview_bytes=10
duration_ms=...
```

Nếu thực sự cần body sample khi debug có kiểm soát: allowlist endpoint/media type, redaction trước khi phát ra log, ẩn fields nhạy cảm, tránh multipart/binary, giới hạn retention và phân quyền truy cập log. Hex/Base64 **không phải** che giấu dữ liệu; chỉ đổi cách biểu diễn.

## 7. Ví dụ chạy được: request cache giới hạn + response tee giới hạn

Ví dụ sau là **Spring Boot 3.x + Spring Web, Java 17+**, đồng bộ (synchronous request handlers). Mỗi request chỉ giữ **tối đa 1024 byte bản sao phía request** và **1024 byte bản sao phía response** ở lớp quan sát. Response được forward **trực tiếp** xuống container thay vì gom toàn bộ trước khi gửi. Không cần database, security hay AOP.

Đây là minh họa cho **giới hạn bộ nhớ của observability wrapper**, **không phải hard limit HTTP payload**, và **không tối ưu cho async/SSE**. Các endpoint demo cố tình dùng body nhỏ hoặc String lớn để quan sát khác biệt.

### 7.1. Tạo project

Từ [Spring Initializr](https://start.spring.io/), chọn Maven, Java 17+, Spring Boot 3.x và dependency **Spring Web**. Phần dependency tương ứng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Đây là fragment của `pom.xml`; project Initializr cung cấp parent/BOM, Spring Boot plugin và metadata. Đặt **tất cả source** trong một file `src/main/java/com/example/demo/DemoApplication.java`. File chỉ có một public top-level class; những lớp còn lại package-private là hợp lệ trong Java 17.

### 7.2. Mã Java đầy đủ

```java
package com.example.demo;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletOutputStream;
import jakarta.servlet.WriteListener;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpServletResponseWrapper;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Component
class BoundedBodyObservationFilter extends OncePerRequestFilter {

    private static final int PREVIEW_LIMIT = 1024;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI()
                .substring(request.getContextPath().length());
        return !path.startsWith("/api/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Chỉ cache phần request body mà downstream thật sự đọc.
        ContentCachingRequestWrapper req =
                new ContentCachingRequestWrapper(request, PREVIEW_LIMIT);

        // Không dùng ContentCachingResponseWrapper vì nó có thể
        // giữ toàn bộ response body trong RAM.
        BoundedResponseWrapper resp =
                new BoundedResponseWrapper(response, PREVIEW_LIMIT);

        long start = System.nanoTime();
        try {
            chain.doFilter(req, resp);
        } finally {
            // Demo chỉ công bố kết quả hoàn chỉnh cho sync request.
            if (!req.isAsyncStarted()) {
                resp.flushObservedWriter();
                long elapsedNanos = System.nanoTime() - start;

                // Không log raw request/response body.
                System.out.println(
                        "OBS " + req.getMethod() + " "
                        + req.getRequestURI()
                        + " status=" + resp.getStatus()
                        + " reqPreviewBytes="
                        + req.getContentAsByteArray().length
                        + " respPreviewBytes=" + resp.previewSize()
                        + " respObservedBytes=" + resp.observedBytes()
                        + " elapsedMs=" + elapsedNanos / 1_000_000L);
            } else {
                // Với async: dữ liệu có thể tiếp tục được ghi về sau.
                // Demo không tuyên bố số byte ở đây là tổng cuối.
                System.out.println("OBS async: completion not observed");
            }
        }
    }
}

class BoundedResponseWrapper extends HttpServletResponseWrapper {

    private final int limit;
    private final ByteArrayOutputStream preview;
    private long observed;

    private ServletOutputStream output;
    private PrintWriter writer;
    private boolean outputMode;
    private boolean writerMode;

    BoundedResponseWrapper(HttpServletResponse response, int limit) {
        super(response);
        if (limit < 1) {
            throw new IllegalArgumentException("limit must be positive");
        }
        this.limit = limit;
        this.preview = new ByteArrayOutputStream(limit);
    }

    private void remember(int oneByte) {
        observed++;
        if (preview.size() < limit) {
            preview.write(oneByte);
        }
    }

    private void remember(byte[] bytes, int off, int len) {
        observed += len;
        int canKeep = Math.min(limit - preview.size(), len);
        if (canKeep > 0) {
            preview.write(bytes, off, canKeep);
        }
    }

    // Một stream được chia sẻ cho output binary và writer text.
    private ServletOutputStream outputDelegate() throws IOException {
        if (output == null) {
            ServletOutputStream target = super.getOutputStream();

            output = new ServletOutputStream() {

                @Override
                public boolean isReady() {
                    return target.isReady();
                }

                @Override
                public void setWriteListener(WriteListener listener) {
                    target.setWriteListener(listener);
                }

                @Override
                public void write(int b) throws IOException {
                    target.write(b);
                    remember(b);
                }

                @Override
                public void write(byte[] b, int off, int len)
                        throws IOException {

                    target.write(b, off, len);
                    remember(b, off, len);
                }

                @Override
                public void flush() throws IOException {
                    target.flush();
                }

                @Override
                public void close() throws IOException {
                    target.close();
                }
            };
        }
        return output;
    }

    @Override
    public ServletOutputStream getOutputStream() throws IOException {
        if (writerMode) {
            throw new IllegalStateException(
                    "getWriter() already selected");
        }
        outputMode = true;
        return outputDelegate();
    }

    @Override
    public PrintWriter getWriter() throws IOException {
        if (outputMode) {
            throw new IllegalStateException(
                    "getOutputStream() already selected");
        }
        writerMode = true;

        if (writer == null) {
            String encoding = getCharacterEncoding();
            Charset charset = encoding == null
                    ? StandardCharsets.ISO_8859_1
                    : Charset.forName(encoding);

            writer = new PrintWriter(
                    new OutputStreamWriter(outputDelegate(), charset));
        }
        return writer;
    }

    // Không đóng output stream; chỉ flush writer của demo sync.
    void flushObservedWriter() {
        if (writer != null) {
            writer.flush();
        }
    }

    int previewSize() {
        return preview.size();
    }

    long observedBytes() {
        return observed;
    }
}

@RestController
class DemoController {

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> echo(@RequestBody String body) {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/plain;charset=UTF-8"))
                .body("echo:" + body);
    }

    @GetMapping(
            path = "/api/large",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String large() {
        // Đây là demo String 10_000 byte ASCII.
        // Không dùng cách tạo String lớn này cho file streaming.
        return "x".repeat(10_000);
    }

    @GetMapping("/api/writer")
    public void writer(HttpServletResponse response)
            throws IOException {

        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("hello writer");
    }
}
```

**QA mã nguồn theo thiết kế:**

- `ContentCachingRequestWrapper(request, 1024)` đặt **cache request tối đa 1024 byte**; wrapper không tự đọc trước body.
- `BoundedResponseWrapper` chỉ giữ **prefix tối đa 1024 byte**, đồng thời có `observed` để đếm số byte được ghi qua wrapper. `ByteArrayOutputStream(limit)` có dung lượng tối đa theo logic `remember(...)`, không tăng theo kích thước response.
- `outputDelegate()` delegate `write(...)` xuống stream gốc **trước** khi ghi vào preview. Response không chờ lưu đủ toàn bộ body vào một array.
- `getWriter()` dùng cùng delegate output và encoding đã xác định; `getOutputStream()` / `getWriter()` loại trừ nhau.
- `writer.flush()` ở finally trong **đường xử lý sync demo** đảm bảo body do writer chuẩn bị được chuyển xuống stream gốc. Với app thực tế phải tuân thủ lifecycle flush/commit/reset, async callbacks, error dispatch và wrapper nesting đầy đủ.
- `setWriteListener`/`isReady` delegate xuống stream gốc, nhưng code **chưa được thiết kế để quan sát async stream hoàn chỉnh**; khi request chuyển async, filter log rõ rằng completion chưa được quan sát.
- Response do `sendError()`/`sendRedirect()` hoặc servlet container tự sinh có thể **đi vòng qua những write() được wrapper quan sát**; counter không phải số byte “trên dây” sau HTTP compression/chunking/TLS.
- `@RequestBody String` vẫn có thể cấp phát bộ nhớ theo kích thước body trong MVC converter. **Giới hạn 1024 byte ở Filter không hạn chế kích thước `String` này.**
- Ví dụ chỉ in metadata, không in raw payload. Trong production tránh log đường dẫn chứa PII/token; với query string và headers phải có redaction.

### 7.3. Chạy ứng dụng

Tại thư mục gốc Spring Initializr:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
```

Spring Boot mặc định dùng `http://localhost:8080` nếu không đổi `server.port`/context path.

### 7.4. HTTP test: request text nhỏ

```bash
curl -i -X POST 'http://localhost:8080/api/echo' \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
```

Response quan trọng:

```http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

echo:hello
```

Console có dòng tương tự:

```text
OBS POST /api/echo status=200 reqPreviewBytes=5 respPreviewBytes=10 respObservedBytes=10 elapsedMs=...
```

Giải thích:
- Input `hello` chứa 5 byte ASCII.
- Output `echo:hello` chứa 10 byte ASCII.
- Limit preview 1024 không bị chạm, nên số byte cache/observed bằng kích thước thực của demo này.
- `elapsedMs` phụ thuộc máy/server/GC, không có con số cố định.

### 7.5. HTTP test: response lớn hơn giới hạn preview

```bash
curl -sS -o large.txt http://localhost:8080/api/large
wc -c large.txt
```

Với Unix có `wc`, stdout:

```text
10000 large.txt
```

Console có dòng dạng:

```text
OBS GET /api/large status=200 reqPreviewBytes=0 respPreviewBytes=1024 respObservedBytes=10000 elapsedMs=...
```

Đây là khác biệt mấu chốt: client nhận đủ **10.000 byte**, nhưng wrapper chỉ lưu **1024 byte đầu** trong buffer quan sát. `reqPreviewBytes=0` vì endpoint GET không đọc request body. Nếu OS/tool hiển thị metadata khác, chỉ giá trị số byte của file cần kiểm tra.

### 7.6. HTTP test: ghi qua getWriter()

```bash
curl -i http://localhost:8080/api/writer
```

Body:

```text
hello writer
```

Bản ghi server dạng:

```text
OBS GET /api/writer status=200 reqPreviewBytes=0 respPreviewBytes=12 respObservedBytes=12 elapsedMs=...
```

Chuỗi `hello writer` dài **12 byte ASCII**. Test này giúp phát hiện wrapper chỉ override `getOutputStream()` mà bỏ quên `getWriter()`.

### 7.7. Lệnh cURL trên Windows PowerShell

Bash dùng ký tự `\` để xuống dòng; PowerShell không dùng cùng cú pháp. Hãy chạy một dòng bằng `curl.exe`:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/echo" -H "Content-Type: text/plain" --data-binary "hello"
```

Để kiểm tra file lớn trên Windows, có thể dùng PowerShell:

```powershell
curl.exe -sS -o large.txt http://localhost:8080/api/large
(Get-Item large.txt).Length
```

Giá trị hiển thị là `10000`.

## 8. Giới hạn bộ nhớ quan sát ≠ giới hạn kích thước HTTP request

Có ít nhất bốn lớp tài nguyên có thể tăng theo dữ liệu người dùng:

```text
Client payload
   |
Reverse proxy / ingress (body size / timeout / rate limits)
   |
Servlet container (multipart/form limits, buffers, connection policy)
   |
Filters (bounded preview vs full caching)
   |
MVC converters (JSON object graph, String @RequestBody, byte[] payload)
   |
Controller / service (lists, files, temp objects, database transactions)
```

**Ví dụ:** filter giữ tối đa 1024 byte, nhưng controller nhận `@RequestBody byte[]` với body 200 MiB. Converter vẫn có thể tạo một byte array ~200 MiB, chưa kể copy/overhead. Vì vậy hard payload policy phải được thực thi **trước hoặc trong quá trình tiêu thụ body**, không chỉ trong logging filter.

### 8.1. Content-Length chỉ là kiểm tra nhanh, không đủ

```java
long length = request.getContentLengthLong();
if (length > MAX_ALLOWED_BYTES) {
    response.sendError(413, "Content Too Large");
    return;
}
```

Đây là snippet kiểm tra sớm trong một Filter, **không phải cơ chế hard cap hoàn chỉnh**:
- `Content-Length` có thể không xuất hiện hoặc là `-1`, đặc biệt với chunked encoding.
- Body thực tế sau transfer decoding/compression có thể phức tạp hơn con số header.
- Proxy/container có thể có các quy tắc riêng trước filter.

Để áp **hard cap** cho generic JSON/binary request, phải đếm **byte thực sự được đọc từ input stream** bằng một bounded/counting decorator hoặc chính sách proxy/container tương đương. Khi vượt giới hạn, ngừng đọc và trả 413 ở thời điểm còn có thể ghi response; kiểm soát exception propagation, HTTP connection và trạng thái response đã committed. Test cả requests có/không có `Content-Length`, upload chậm, chunked và concurrent requests. Nếu tự implement ServletInputStream decorator, phải bảo toàn non-blocking semantics.

### 8.2. Ví dụ pattern bounded read trước khi tạo replay buffer

Trong môi trường **đồng bộ** và có hard cap nhỏ, nếu thực sự phải đọc trước rồi replay, tránh:

```java
// Không dùng với dữ liệu không bị giới hạn!
byte[] body = request.getInputStream().readAllBytes();
```

Dùng pattern đọc có giới hạn:

```java
// Pseudocode minh họa quyết định, KHÔNG phải filter đầy đủ.
int limitBytes = 1024 * 1024;
byte[] data = request.getInputStream()
        .readNBytes(limitBytes + 1);

if (data.length > limitBytes) {
    // Trả 413 trước khi cho xử lý tiếp.
    // Không gọi chain.doFilter với stream đã bị tiêu thụ.
} else {
    // Chỉ bọc request bằng replayable wrapper thực sự nếu cần.
    // Wrapper phải triển khai đầy đủ getInputStream/getReader.
}
```

`readNBytes(limit+1)` giữ lượng dữ liệu hữu hạn, giúp phát hiện body vượt giới hạn mà không nạp toàn bộ. Nhưng nó **đã tiêu thụ stream**, nên phải có replay wrapper đúng để downstream đọc các byte hợp lệ. Với body dài hơn limit, có thể cần chính sách đóng/tiếp tục tiêu thụ kết nối của container; không tự giả định mỗi request sau trên cùng connection luôn hoạt động bình thường sau khi từ chối giữa chừng.

### 8.3. Cấu hình upload multipart và HTTP form

Spring Boot 3.x hỗ trợ các property khác nhau cho các đường đọc body:

```properties
# Multipart (file upload); ví dụ chính sách của ứng dụng:
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
spring.servlet.multipart.file-size-threshold=0B

# Giới hạn form POST do embedded Tomcat xử lý:
server.tomcat.max-http-form-post-size=2MB
```

Ý nghĩa:
- `max-file-size` giới hạn một file trong multipart request.
- `max-request-size` giới hạn tổng multipart request.
- `file-size-threshold=0B` nghĩa là cấu hình multipart có thể spill file contents xuống disk theo cơ chế Servlet multipart; điều này **không** loại trừ disk exhaustion hoặc cần kiểm soát temp files/cleanup.
- `server.tomcat.max-http-form-post-size` liên quan form POST do Tomcat parse, **không** là một universal hard limit cho mọi `application/json`/binary request.

Các property này khác nhau theo Servlet container (Tomcat/Jetty/Undertow), bản Spring Boot và framework parser. Kiểm tra [Spring Boot Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) và thực hiện integration test cho loại payload thật của ứng dụng.

### 8.4. Upload lớn: stream thay vì giữ byte[]

Với `MultipartFile`, tránh:

```java
byte[] all = file.getBytes(); // có thể tạo mảng lớn trong RAM
```

Nếu thiết kế cần lưu file, dùng `file.getInputStream()` và copy **theo buffer nhỏ** vào storage được kiểm soát, hoặc `file.transferTo(...)` khi phù hợp. Vẫn cần:
- hard file/request size limits;
- quota về disk, số lượng uploads, số parts và thời gian xử lý;
- MIME sniffing/định dạng hợp lệ, không tin tuyệt đối tên file/Content-Type từ client;
- scanning/sandbox thích hợp nếu xử lý nội dung không tin cậy;
- permission checks, path traversal protection và cleanup temporary files.

`MultipartFile` có thể đã được Servlet multipart resolver/container xử lý trước khi controller chạy; đặt một filter sau parser không tự khiến quá trình đó trở thành bounded-memory. Kiểm tra filter order và multipart infrastructure nếu muốn đo phần nào của body.

## 9. So sánh ContentCaching wrappers và tee wrappers

| Tình huống | ContentCachingRequestWrapper | ContentCachingResponseWrapper | Bounded tee wrapper |
| --- | --- | --- | --- |
| Quan sát request body mà handler tự đọc | Rất phù hợp với cache limit dương | Không liên quan | Custom request tee cũng được |
| Cho phép đọc lại request cho converter | **Không tự động** | Không liên quan | Chỉ khi làm replay wrapper riêng |
| Lưu toàn bộ response để tính hash/ETag | Không | Có, với trade-off memory | Không nếu chỉ giữ prefix |
| Quan sát response rất lớn | Không liên quan | Nguy cơ cache toàn bộ | **Ưu tiên bounded tee**, hoặc bỏ body logging |
| Giới hạn request body được phép tải | Không, chỉ giới hạn cache | Không | Preview tee cũng **không**; cần counting hard limit |
| Có thể thay đổi body khi đã đọc? | Không dễ dàng, cần replay/custom | Có thể can thiệp full buffer khi còn sync, nhưng phức tạp | Không chủ đích thay đổi body |
| Phải copy body trở lại response? | Không có `copyBodyToResponse()` | **Có** với pattern wrapper buffering | Không, tee chuyển tiếp ngay |
| Async/SSE/nonblocking | Cần hiểu dispatch/stream lifecycle | Dễ ảnh hưởng streaming | Phải thiết kế async-aware chuyên biệt |

**Không có wrapper chung “đọc lại mọi body, không tốn RAM, vừa streaming, vừa chỉnh nội dung, vừa auto 413”**. Mỗi yêu cầu là một trade-off riêng; xây wrapper ít quyền nhất và đơn giản nhất đáp ứng nhu cầu.

## 10. Đọc body để log có thể gây lỗi nội dung và lỗi bảo mật

### 10.1. Không decode binary thành text tùy ý

Một `application/octet-stream`, ảnh JPEG, zip, PDF hoặc response compressed không thể mặc định đọc thành `new String(bytes, UTF_8)` rồi mong được text có ý nghĩa. Byte prefix còn có thể cắt giữa ký tự UTF-8 multi-byte, khiến preview string có ký tự thay thế `�`.

Để chẩn đoán:
- Ưu tiên log byte count, media type, status và đường dẫn đã làm sạch.
- Chỉ render text preview nếu media type thuộc allowlist và charset đã xác minh.
- Với JSON, cần schema-based redaction; regex loại field nhạy cảm trên substring JSON **không đáng tin** khi chuỗi bị cắt giữa field/escape.
- Hex hoặc Base64 chỉ chuyển encoding; **không** tự che dữ liệu nhạy cảm.

### 10.2. Authorization và dữ liệu nhạy cảm

Filter có thể chạy trước khi authentication hoàn tất, nên log raw request headers/body có thể chứa cookie, bearer token, password, API keys và dữ liệu nhạy cảm. Với lỗi 401/403, càng cần chính sách redaction. Không lưu body cho endpoint login/payment/health records chỉ vì debug dễ hơn.

Nếu dùng Spring Security:
- Xem thứ tự filter và `SecurityFilterChain`.
- Tránh log principal/header raw khi chưa biết nguồn tin cậy.
- Dùng correlation ID không chứa bí mật thay vì dump payload.
- Kiểm tra log retention, encryption at rest, access control và môi trường bật sample.

### 10.3. Nén, transform và bytes-on-wire

Response wrapper đếm những byte được ghi qua chính wrapper. Nếu một filter/container phía ngoài nén gzip/Brotli, HTTP chunked encoding, TLS encryption hoặc proxy transform, số byte trên mạng có thể **khác**. Không dùng counter của tee wrapper làm số byte wire-level chính xác nếu chưa biết vị trí trong filter chain và transfer encoding.

Ngoài ra, `HEAD`/`304 Not Modified` không có response body theo semantics HTTP. Một wrapper ghi header/body theo cách không đúng có thể phá các điều kiện này. Với HTTP caching/ETag/streaming, cân nhắc dùng các khả năng sẵn có của framework.

## 11. Async, error dispatch và response lifecycle

### 11.1. OncePerRequestFilter không bảo đảm một lần cho toàn vòng đời async

`OncePerRequestFilter` hỗ trợ lọc trong dispatch của Servlet request, có hook như:
- `shouldNotFilter(HttpServletRequest)`.
- `shouldNotFilterAsyncDispatch()`.
- `shouldNotFilterErrorDispatch()`.

Với `Callable`, `DeferredResult`, `StreamingResponseBody` hoặc SSE, request có thể chuyển sang async và response tiếp tục được ghi **sau khi `chain.doFilter()` đầu tiên trả về**. Bởi vậy đoạn:

```java
chain.doFilter(requestWrapper, responseWrapper);
log(responseWrapper.getContentAsByteArray());
```

có thể thấy **body chưa hoàn chỉnh** hoặc xung đột async lifecycle. Demo ở mục 7 chủ động chỉ công bố log cuối cho synchronous handlers.

Nếu cần production support async:
1. Đăng ký wrapper/filters với dispatcher types phù hợp.
2. Xem xét `AsyncListener` (`onComplete`, `onError`, `onTimeout`, `onStartAsync`), hoặc tầng tracing tương ứng, để đo completion thật.
3. Không flush/close Servlet stream sai thread/thời điểm.
4. Giữ preview bounded và thread-safety nếu callback đồng thời.
5. Test async, lỗi, cancel, timeout và nested wrappers.
6. Không dùng ThreadLocal/MDC qua async thread mà thiếu propagation/cleanup.

### 11.2. Error dispatch và sendError

Exception xảy ra trong Filter **trước DispatcherServlet** không mặc định được `@RestControllerAdvice` bắt. Servlet container có thể mở ERROR dispatch tới error controller; filter có thể chạy lại nếu đăng ký `DispatcherType.ERROR`. `sendError(...)`/`sendRedirect(...)` do container xử lý cũng không nhất thiết đi qua `ServletOutputStream.write(...)` của wrapper.

Do đó preview/count là **quan sát trong phạm vi wrapper**, không phải toàn bộ raw HTTP response sinh bởi container, error pages và network stack.

### 11.3. Flush, committed status và Content-Length

Nếu response đã committed, không được tùy tiện reset body hay thay status/header. Với wrapper ghi trực tiếp xuống container (tee), bạn không thể quay lại sửa bytes đã gửi. Nếu muốn chỉnh JSON output, dùng `ResponseBodyAdvice` hoặc custom `HttpMessageConverter` trong phạm vi kiểm soát; nếu muốn rewrite HTML/file body toàn phần, phải chấp nhận buffering có giới hạn hoặc streaming transformation phức tạp.

Không tự set `Content-Length` bằng số **ký tự** Java của một String: HTTP length tính bằng **byte** theo encoding. Với response text UTF-8 có tiếng Việt, `String.length()` thường khác số bytes thực.

## 12. Tài nguyên và bộ nhớ trong server thật

Giả sử mỗi request giữ preview 1 KiB mỗi chiều (chưa tính wrapper object/metadata):
- 1 request: tối đa **2 KiB dữ liệu xem trước**.
- 1.000 requests đồng thời đang sống: tối đa khoảng **2 MiB nội dung preview**.
- Nếu giữ toàn response 10 MiB/request trong `ContentCachingResponseWrapper`, 1.000 requests có thể cần khoảng **10 GiB** chỉ cho cached body, chưa tính copies, serializer, object graph, container buffer và JVM overhead.

Đây là phép tính **dung lượng dữ liệu thô**, không phải đo heap chính xác. `ByteArrayOutputStream` có initial capacity, overhead, array allocation; `getContentAsByteArray()` có thể tạo copy; logging formatter/queue có thể giữ thêm dữ liệu. Với high concurrency, giảm preview, sampling và các buffer khác sẽ giúp hơn chỉ tối ưu một class.

Các giới hạn cần tính chung:
- **Request concurrency:** thread pool, queue và kết nối mở.
- **Request body:** proxy/container/codec/parser hard cap và thời gian đọc.
- **Output generation:** tránh xây một String/byte[] quá lớn; sử dụng streaming/resource khi thích hợp.
- **Uploads:** multipart thresholds, disk quota, cleanup và antivirus scanning.
- **Logs:** batch/async appender queue, message truncation, sampling và retention.
- **Heap:** giữ đủ dư địa cho GC, converter object graph, caches, HTTP session và service data.

## 13. Những lỗi thường gặp

| Triệu chứng | Lý do | Cách sửa |
| --- | --- | --- |
| `@RequestBody` rỗng sau Filter logging | Filter đọc stream trước | Chỉ cache-on-read hoặc replay wrapper có hard cap |
| Request cache rỗng dù body có gửi | Downstream không tiêu thụ body hoặc wrapper tạo sai vị trí | Cache phản ánh **bytes đã đọc**, không đọc trước |
| Request quá lớn vẫn được controller nhận | `contentCacheLimit` chỉ giới hạn cache | Enforce hard body size ở ingress/container/counting layer |
| Response client trống khi dùng caching wrapper | Quên `copyBodyToResponse()` | Copy body trong đúng sync lifecycle hoặc chọn tee |
| Response lớn gây OOM | `ContentCachingResponseWrapper` giữ toàn body | Bounded tee/không log body, streaming output |
| Ghi được binary nhưng không bắt text | Wrapper chỉ override `getOutputStream()` | Hỗ trợ cả `getWriter()` và đúng charset |
| Servlet báo không thể gọi `getWriter/getOutputStream` | Chuyển qua lại hai mode | Tôn trọng mode exclusivity |
| UTF-8 preview có ký tự lỗi | Cắt byte giữa code point | Dùng metadata hoặc decode phần đủ ký tự có kiểm tra |
| PostHandle không đọc được response body | Body có thể đã gửi bởi converter | Dùng response wrapper ở Filter hoặc `ResponseBodyAdvice` |
| Response bị sai Content-Length | Ghi thêm/bớt bytes sau khi set length | Để container/converter quản lý, hoặc tính lại theo byte chính xác |
| Async response log thiếu cuối | Filter return trước async completion | AsyncListener/appropriate async-aware design |
| Body log làm lộ token/password | Không whitelist/redact | Metadata-only, allowlist, bảo vệ log |
| Log 1 MiB/request gây tăng heap | Preview limit quá rộng, concurrency cao | Giới hạn vài KiB, sampling |
| Filter chạy hai lần | Double registration/ERROR dispatch | Kiểm tra mappings/order và OncePerRequestFilter |
| 413 không xảy ra khi chunked | Chỉ tin Content-Length | Count actual bytes, enforce proxy/container |
| Log bytes không khớp Content-Length | Compression/transfer coding/partial content | Hiểu vị trí wrapper và wire encoding |

## 14. Checklist review cho request/response wrapping

1. Mục tiêu là **quan sát**, **thay đổi body**, hay **enforce payload limit**? Có tách thành các trách nhiệm riêng chưa?
2. Có giữ **tối đa N byte** cho mỗi request/response không, hay đang `readAllBytes()` / buffer toàn response?
3. Có bỏ quên `getReader()` hoặc `getWriter()` không?
4. Nếu dùng `ContentCachingRequestWrapper`, đã hiểu cache chỉ có bytes được downstream đọc và **không cho replay toàn body** chưa?
5. Nếu dùng `ContentCachingResponseWrapper`, đã đảm bảo `copyBodyToResponse()` và kiểm soát full buffering chưa?
6. Nếu dùng custom tee, đã delegate mọi write/flush/ready/listener operation quan trọng và xử lý writer encoding đúng chưa?
7. Với async/error dispatch, wrapper có lifecycle riêng và có test timeout/error/complete không?
8. Có data redaction, audit access, sampling, sampling limits, retention và log queue limits chưa?
9. Hard body limit có dựa vào **actual bytes** và xử lý khi thiếu Content-Length không?
10. Multipart uploads/file streaming có cách xử lý riêng không?
11. Memory model đã tính đồng thời converter body, object graph, temp files, copies và concurrent requests chưa?
12. Các test đã kiểm chứng client nhận **đầy đủ body** dù chỉ cache một preview ngắn chưa?

## 15. Tự kiểm tra

**Câu 1.** `ContentCachingRequestWrapper(req, 1024)` có tự trả HTTP 413 nếu request body 5 MiB?

**Đáp án:** Không. Limit này giới hạn **cache** chứ không chặn downstream đọc body. Cần hard body limit độc lập.

**Câu 2.** Vì sao không gọi `request.getInputStream().readAllBytes()` trong Filter để log rồi tiếp tục `chain.doFilter`?

**Đáp án:** Nó vừa có nguy cơ gom toàn body trong heap, vừa tiêu thụ stream mà `@RequestBody` cần. Nếu phải đọc trước thì cần hard cap và replay wrapper thực sự; nếu chỉ quan sát thì dùng cache-on-read/tee.

**Câu 3.** Với `ContentCachingResponseWrapper`, tại sao phải gọi `copyBodyToResponse()`?

**Đáp án:** Nó giữ response body trong buffer; cần copy các bytes đã cache xuống response gốc trong sync lifecycle thông thường để client nhận được nội dung.

**Câu 4.** Nếu ứng dụng trả file 50 MiB và chỉ muốn đếm bytes + lưu 1 KiB đầu, có nên dùng ContentCachingResponseWrapper không?

**Đáp án:** Không lý tưởng; nó có thể giữ toàn file trong RAM. Dùng bounded tee hoặc không ghi body, và chọn streaming/resource phù hợp.

**Câu 5.** Request gửi `Transfer-Encoding: chunked`, không có Content-Length. Kiểm tra `getContentLengthLong()` có tạo hard limit không?

**Đáp án:** Không. Phải có chính sách ở proxy/container hoặc đếm bytes thực đọc, kể cả trường hợp không có length header.

**Câu 6.** Vì sao body preview có thể khiến log lộ bí mật dù chỉ dài 1024 byte?

**Đáp án:** Password, token, email hoặc thông tin riêng tư có thể xuất hiện ngay đầu body. Mặc định chỉ log metadata; body sample cần allowlist/redaction/retention/access control.

**Câu 7.** Khi response async còn ghi sau lúc `chain.doFilter()` return, log byte count trong Filter có đầy đủ không?

**Đáp án:** Không bảo đảm. Cần async-aware lifecycle và callback completion để chốt metrics.

## 16. Tài liệu chính thức

- [Spring Framework 6.2 — ContentCachingRequestWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html): giới hạn cache, chỉ cache bytes đã đọc và `handleContentOverflow`.
- [Spring Framework 6.2 — ContentCachingResponseWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/ContentCachingResponseWrapper.html): cache response body, `getContentAsByteArray()`, `copyBodyToResponse()`.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): Filter, OncePerRequestFilter, async/error dispatch.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.servlet.multipart.*`, Tomcat form limits và các giới hạn container.
- [Spring Boot 3.5 — MultipartProperties Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html): file/request size và threshold.
- [Jakarta Servlet API — HttpServletRequestWrapper](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequestwrapper): delegate/override request behavior.
- [Jakarta Servlet API — HttpServletResponseWrapper](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletresponsewrapper): delegate/override response behavior.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): cách body đi từ Servlet input stream thành controller argument và từ return value ra output stream.

**Kết luận:** để quan sát request, `ContentCachingRequestWrapper` có limit dương là lựa chọn tốt nếu chỉ cần các bytes mà downstream đã đọc. Để quan sát response lớn, tránh dùng `ContentCachingResponseWrapper` như một logger mặc định vì có thể buffer toàn body; dùng **bounded streaming tee** hoặc chỉ log metadata. Bất kỳ preview limit nào cũng **không thay thế hard HTTP payload limit**, memory policy của converter/service, kiểm soát uploads, async lifecycle hoặc bảo mật log.
