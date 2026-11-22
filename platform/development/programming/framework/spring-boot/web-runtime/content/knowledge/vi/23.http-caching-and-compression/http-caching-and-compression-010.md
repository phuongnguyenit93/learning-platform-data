# Kiểm tra cache hoặc nén khi phản hồi được gửi theo luồng trong Spring Boot

## 1. Mục tiêu và câu hỏi cần trả lời

Một API **trả phản hồi theo luồng (streaming response)** không nhất thiết tạo xong toàn bộ nội dung trước khi bắt đầu gửi. Server có thể ghi từng phần, ví dụ báo cáo CSV được sinh dần, chuỗi log, một nguồn dữ liệu dài hoặc **Server-Sent Events (SSE)**.

Khi bật HTTP cache hoặc nén GZIP, cần kiểm tra **đường đi thực tế từ server đến client**, không chỉ nhìn mã controller hay thấy property đã bật:

1. Phản hồi có được **cache** không? Cache phía trình duyệt/CDN/proxy có được phép lưu, tái sử dụng hay revalidate hay không?
2. Phản hồi có được **nén** không? Client đề nghị `Accept-Encoding: gzip` và server thực sự trả `Content-Encoding: gzip` cùng byte GZIP hợp lệ hay chỉ trả text không nén?
3. Nếu streaming, các phần dữ liệu có đến **dần theo thời gian** không? Hay bị giữ trong bộ đệm của application, container, proxy, cache filter hoặc compression layer cho tới gần cuối?
4. Những điều nào ảnh hưởng đến `Content-Length`, `Transfer-Encoding: chunked`, HTTP/2, `ETag` và `Vary`?
5. Làm thế nào viết một ví dụ **Spring Boot MVC Java 17+ chạy được**, thử bằng curl và kiểm thử HTTP thật để tránh kết luận từ MockMvc?

**Nguyên tắc:** streaming là **cách phát body**, caching là **chính sách lưu/tái sử dụng HTTP response**, còn compression là **mã hóa biểu diễn body trên đường truyền**. Ba vấn đề độc lập nhưng có thể tương tác qua buffering, HTTP headers và proxy.

## 2. Phân biệt streaming, caching, compression và chunked transfer

| Khái niệm | Ý nghĩa | Header/tín hiệu quan sát | Không nên hiểu nhầm |
| --- | --- | --- | --- |
| Streaming | Ứng dụng có thể phát body từng phần trước khi toàn bộ dữ liệu sẵn sàng | Thời gian các byte đến, `flush`, stream completion | Không có nghĩa mặc định “không cache” hoặc “không nén” |
| HTTP caching | Browser/proxy được phép lưu và tái sử dụng phản hồi theo chính sách | `Cache-Control`, `ETag`, `Last-Modified`, `Age`, `Vary`, `304` | `Cache-Control` không phải chức năng nén |
| HTTP compression | Nội dung truyền đi dùng content coding như gzip | Request `Accept-Encoding`, response `Content-Encoding: gzip`, byte GZIP | `Content-Type` không trở thành `application/gzip`; MIME nội dung vẫn giữ |
| Chunked transfer | HTTP/1.1 truyền body theo các chunk khi chưa biết trước tổng độ dài | `Transfer-Encoding: chunked` (nếu được sử dụng) | Chunked không phải GZIP; HTTP/2 không dùng header này |
| SSE | Stream sự kiện văn bản theo `text/event-stream`, thường kéo dài | `Content-Type: text/event-stream` và các dòng `data: ...` | Không phải JSON array cần buffer đủ mới giải mã |
| Conditional request | Client hỏi representation còn mới không | `If-None-Match`, `If-Modified-Since`, response `304` | Không phù hợp máy móc với stream thay đổi liên tục |

Một response HTTP/1.1 có thể **vừa chunked vừa gzip**:

```text
Ứng dụng viết từng phần
        |
        v
Bộ nén GZIP -> byte đã nén
        |
        v
HTTP/1.1 chunked framing -> network
        |
        v
Client giải chunked framing -> giải nén GZIP -> đọc nội dung
```

Đối với HTTP/2 và HTTP/3, dữ liệu được truyền bằng framing của protocol tương ứng, **không dùng `Transfer-Encoding: chunked`**; điều đó không có nghĩa mất khả năng stream hoặc nén.

**Không có `Content-Length` không đủ chứng minh đang stream:** response có thể được tạo sẵn rồi container vẫn gửi chunked. Ngược lại, một response stream hữu hạn có thể biết trước kích thước. Phải nhìn **thời điểm byte đến** và loại buffering trên đường đi.

## 3. Streaming trong Spring MVC và Spring WebFlux

### 3.1. Spring MVC / Servlet

Spring MVC có nhiều cách trả dữ liệu dần:

- `StreamingResponseBody`: callback viết vào `OutputStream` của response, phù hợp file export sinh dần hoặc dữ liệu tùy chỉnh. Spring xử lý dạng async; việc ghi ra servlet stream vẫn là I/O blocking trên thread dành cho tác vụ.
- `ResponseBodyEmitter`: phát nhiều object/fragment và để framework chuyển đổi sang HTTP body.
- `SseEmitter`: hỗ trợ SSE kiểu MVC, phát nhiều sự kiện `text/event-stream`.
- `Resource`, `ResponseEntity<Resource>`: thích hợp file đã tồn tại; **có thể** được đọc và truyền dần, nhưng điều đó khác với callback tạo dữ liệu liên tục.
- `ResponseEntity<StreamingResponseBody>`: vừa khai báo cache/content-type headers, vừa dùng streaming body.

Một ví dụ callback (chỉ là snippet; cần đặt trong controller và import phù hợp):

```java
StreamingResponseBody body = outputStream -> {
    outputStream.write("part A\n".getBytes(StandardCharsets.UTF_8));
    outputStream.flush();
    outputStream.write("part B\n".getBytes(StandardCharsets.UTF_8));
    outputStream.flush();
};
return ResponseEntity.ok()
    .cacheControl(CacheControl.noStore())
    .body(body);
```

`flush()` yêu cầu đẩy byte qua lớp buffering của Java/Servlet ở thời điểm đó, **không bảo đảm client đã nhận ngay**: gzip wrapper, web server, proxy, TLS và mạng còn có thể buffer hoặc gom nhiều write. Nếu ứng dụng dùng `StreamingResponseBody`, nên cấu hình executor cho xử lý MVC async phù hợp với tải, theo dõi timeout và client disconnect.

### 3.2. Spring WebFlux / Reactor

WebFlux có thể trả `Flux<T>` / `Flux<ServerSentEvent<T>>`. Với `text/event-stream` hoặc NDJSON, framework mã hóa nhiều phần dữ liệu thành một stream; nếu cố serialize `Flux` thành một JSON array thông thường thì có thể phát sinh buffering theo media type/converter.

Snippet chỉ minh họa, **không phải class chạy độc lập**:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(n -> ServerSentEvent.<String>builder()
            .id(Long.toString(n))
            .data("tick-" + n)
            .build());
}
```

Cần import `Flux`, `ServerSentEvent`, `Duration` và annotation thích hợp. `Flux.interval` tạo dữ liệu theo lịch mà không dùng `Thread.sleep` để chặn Netty event loop. Stream ví dụ này là vô hạn; client có thể hủy subscription khi đóng kết nối.

**Không áp dụng trực tiếp công thức MVC `StreamingResponseBody` cho Netty WebFlux**; hai stack có I/O, threading và kiểm soát bộ đệm khác nhau. Tuy nhiên, ý nghĩa của `Cache-Control`, `Content-Encoding`, `Vary` và bài kiểm thử HTTP end-to-end về cơ bản vẫn giống nhau.

## 4. Caching khi response là stream

### 4.1. Stream có luôn bị cấm cache không?

**Không.** Một phản hồi được gửi theo stream vẫn có thể là **tài nguyên hữu hạn, ổn định**, ví dụ bản xuất CSV đã đóng băng theo phiên bản. Nếu HTTP cache policy cho phép và response hoàn chỉnh, một cache có thể lưu bản sao rồi dùng lại/kiểm tra lại khi đủ điều kiện.

Ngược lại, các luồng **live events, thông tin theo request/user, dữ liệu biến đổi liên tục** thường không nên cho shared cache giữ lại. Với chúng, chỉ cần gửi một vài byte trước cũng không biến body thành dữ liệu “công khai”.

| Loại response | Chính sách thường phù hợp | Vì sao |
| --- | --- | --- |
| SSE cá nhân, feed thời gian thực, dữ liệu nhạy cảm | `Cache-Control: no-store` | Không cho cache tuân thủ chuẩn lưu response |
| Dashboard user-specific có thể cache riêng | `private` và freshness/validator theo contract nếu thực sự cần | Không cho shared cache dùng lại giữa người dùng |
| Bản xuất file/versioned snapshot công khai | `public, max-age=...` và `ETag`/`Last-Modified` được tính đúng | Có representation ổn định, phù hợp cache |
| Tài nguyên cần revalidate mỗi lần nhưng có thể lưu | `no-cache` với validator thích hợp | `no-cache` **không đồng nghĩa không lưu** |
| Nội dung cần giữ nguyên không bị proxy biến đổi | `no-transform` có thể bổ sung | Liên quan biến đổi representation; **không thay thế** `no-store` |

Các header `no-store` và `no-cache` dễ gây nhầm:

- **`no-store`**: cache tuân thủ phải tránh lưu request/response theo directive thích hợp. Dùng cho luồng dữ liệu riêng tư hoặc mà việc lưu lại không được chấp nhận.
- **`no-cache`**: cho phép lưu nhưng không dùng đáp ứng request khác nếu chưa validate thành công với origin (hoặc quy tắc RFC tương ứng).
- **`private`**: shared cache không được lưu; private browser cache có thể lưu nếu directive khác không cấm.
- **`public`**: cho phép dùng trong shared cache trong điều kiện phù hợp; chỉ áp dụng khi chắc chắn không lộ dữ liệu theo người dùng.
- **`max-age=N`**: TTL/freshness của representation; không có nghĩa rằng body đang stream sẽ được kết thúc hay gửi nhanh hơn.

Trong Spring MVC:

```java
// Snippet: sử dụng trên ResponseEntity trong controller.
return ResponseEntity.ok()
    .cacheControl(CacheControl.noStore())
    .body(streamingBody);
```

Không bật cache response tùy ý cho **stream vô hạn**, vì cache hoàn chỉnh có thể không bao giờ được tạo ra; một số proxy/caching layer còn cố buffer toàn bộ response khiến browser không thấy dữ liệu dần.

### 4.2. ETag và Last-Modified: cần representation ổn định

`ETag` là validator giúp client gửi `If-None-Match`; với GET/HEAD có thể nhận `304 Not Modified` và **không có body** nếu representation chưa đổi. `Last-Modified` / `If-Modified-Since` cũng là cơ chế conditional request.

Đối với bản snapshot **đã version hóa** có thể biết ETag từ metadata trước khi ghi body, có thể xử lý conditional request **trước** khi khởi tạo công việc stream tốn kém. Nhưng với luồng thay đổi theo thời gian hoặc dữ liệu mỗi request khác nhau:

- Không gán một `ETag` cố định giả cho mọi nội dung dù byte khác nhau.
- Không bật logic buffer toàn bộ stream chỉ để tính checksum nếu mục tiêu là phát dữ liệu dần và giảm memory.
- Không kỳ vọng một request streaming live trả `304` chỉ vì một thời điểm trước đó không có event mới.
- Với content coding gzip/identity, representation có byte khác nhau; **strong ETag** phải tôn trọng tính chất byte-for-byte từng representation. Nếu validator mô tả cùng nội dung ngữ nghĩa qua nhiều encoding, cân nhắc **weak ETag** theo HTTP semantics và nhu cầu ứng dụng.
- Không bật `ETag` nếu chưa có định nghĩa version phù hợp và cách xử lý conditional requests đúng.

Spring MVC có `ResponseEntity.eTag(...)` và `WebRequest.checkNotModified(...)` cho các tài nguyên hữu hạn. Dùng validator mạnh/yếu theo đúng hợp đồng HTTP, kể cả `Vary` khi có nhiều variants.

### 4.3. Cẩn thận với `ShallowEtagHeaderFilter`

`ShallowEtagHeaderFilter` tạo ETag từ **body đã được sinh ra**, nhờ `ContentCachingResponseWrapper`. Điều đó thường đòi hỏi **cache/buffer toàn bộ response trước khi trả**, tiết kiệm băng thông ở các lần revalidation nhưng không tiết kiệm CPU sinh body và có thể **phá streaming theo thời gian thực**.

Nếu một ứng dụng đã đăng ký filter này:

- Kiểm tra nó có đang bao phủ `/stream/**`, `/events` hoặc các API trả file lớn không.
- Với luồng không cần ETag, **loại trừ đường dẫn** khỏi filter, hoặc gọi `ShallowEtagHeaderFilter.disableContentCaching(request)` **trước khi ghi response** theo API Spring.
- Không tự bọc mọi streaming response bằng `ContentCachingResponseWrapper` để log hay tính checksum; wrapper có thể giữ body trong memory và làm `flush()` không đẩy ngay xuống client.
- Nếu dùng async, xem xét filter dispatch type (`ASYNC`) và lifecycle; cách đăng ký sai có thể làm response bất thường.
- Nếu body đã commit, nhiều header/status không thể sửa lại. Xác định policy/cache validators **trước khi bắt đầu phát byte**.

## 5. Nén HTTP khi stream

### 5.1. Thỏa thuận Content-Encoding

Client có thể yêu cầu:

```http
GET /demo/stream HTTP/1.1
Host: localhost:8080
Accept-Encoding: gzip
```

Nếu server đủ điều kiện nén và chọn gzip, response có dạng:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8
Content-Encoding: gzip
Vary: Accept-Encoding
Cache-Control: no-store
Transfer-Encoding: chunked
```

Đây là **minh họa HTTP/1.1**, không phải header bảo đảm luôn có: `Transfer-Encoding: chunked` phụ thuộc version/container/length và có thể bị proxy thay đổi; có header khác không được liệt kê. **Body sau các header này là byte GZIP**, không phải các dòng text có thể đọc trực tiếp. Sau khi client giải mã content coding, người dùng mới thấy nội dung text.

**Phân biệt:**

- `Accept-Encoding` là khả năng/ưu tiên của client; **không tự chứng minh** server đã nén.
- `Content-Encoding: gzip` và signature/cấu trúc GZIP hợp lệ là bằng chứng về **nội dung đã nén trên đường truyền**.
- `Content-Type: text/plain` vẫn mô tả media type **sau khi giải mã** content coding; không đổi thành `application/gzip` chỉ vì nén.
- `Vary: Accept-Encoding` báo cache rằng phiên bản nén và không nén phải được phân biệt khi tái sử dụng.
- `Content-Length` nếu có trên **response gzip** phải là số byte của representation đã nén, **không** phải số byte text trước nén.
- Không tự set `Content-Length` bằng độ dài string Java hoặc byte trước nén khi container sẽ chuyển đổi thành gzip.
- Với HTTP/2/3, có thể có `Content-Encoding: gzip` nhưng **không có** chunked transfer coding.

### 5.2. Cấu hình Spring Boot

Ví dụ với **Spring Boot 3.x tương thích, Java 17+, embedded Tomcat (mặc định của spring-boot-starter-web)**:

```properties
server.port=8080

# Bật nén HTTP của embedded web server.
server.compression.enabled=true

# Chỉ cho phép nén các kiểu dữ liệu phù hợp trong demo.
server.compression.mime-types=text/plain,application/json

# Hạ ngưỡng để dễ kiểm chứng trong môi trường local.
server.compression.min-response-size=1B

# Dùng cấu hình timeout phù hợp cho MVC async.
spring.mvc.async.request-timeout=30s
```

Spring Boot có các property trên để cấu hình nén, nhưng **quyết định nén thực tế thuộc connector/container và điều kiện request-response**. Cần kiểm tra version cụ thể của Boot, Tomcat/Jetty/Undertow/Netty, HTTP protocol, MIME, trạng thái response, `Accept-Encoding`, kích thước và proxy.

Theo tài liệu Spring Boot 3.5, mặc định `server.compression.enabled=false`; danh sách MIME mặc định gồm nhiều kiểu text/JSON/XML và ngưỡng size mặc định là `2KB`. Với streaming **không biết trước Content-Length**, điều kiện size và thời điểm nén phụ thuộc implementation; **không suy luận chỉ từ `min-response-size`** rằng mọi luồng nhỏ đều được nén.

Trong demo, cấu hình `mime-types` **không chứa `text/event-stream`**. Điều này có chủ đích: SSE cần nhận sự kiện sớm và streaming compression có thể thêm buffering/độ trễ; không cố gắng nén SSE chỉ để giảm vài byte. Với hệ thống thực, proxy/CDN cũng phải không ép nén/đệm SSE trái với mục tiêu độ trễ.

### 5.3. GZIP và buffering

Nén theo luồng **vẫn có thể** tạo byte đầu ra dần; tuy nhiên bộ nén có buffer, gom các phần trước khi phát, hoặc tốn CPU. `flush()` ở Spring/Servlet không đồng nghĩa gzip byte lập tức tới client. GZIP encoder có thể phát sync flush khác nhau tùy cấu hình; reverse proxy có thể buffer tiếp.

Vì vậy hãy đo:

1. **TTFB** — thời điểm byte đầu tiên tới client.
2. **Time between chunks/events** — khoảng cách thực giữa các phần dữ liệu quan sát được.
3. **Total download time** và throughput.
4. **Số byte truyền**: bản gzip có thật sự giảm kích thước không? Với dữ liệu rất nhỏ, header gzip có thể làm tổng byte **lớn hơn**.
5. **CPU/bộ nhớ** phía server, response buffer, số client đồng thời và thời gian connection tồn tại.

Đừng chọn “có gzip” hay “không gzip” theo cảm giác: với bản log hoặc JSON lớn và rất dễ nén, gzip có thể giúp; với SSE có độ trễ thấp hoặc dữ liệu đã nén (ZIP, JPEG, PNG), việc nén thêm ít có lợi, thậm chí gây hại.

## 6. Ví dụ ứng dụng Spring Boot MVC chạy được

Ví dụ chứa **ba endpoint**:

- `GET /demo/stream`: text hữu hạn nhưng phát nhiều lần theo luồng; **`Cache-Control: no-store`**, cho phép kiểm tra GZIP.
- `GET /demo/events`: SSE hữu hạn, hai event, **no-store**; không nằm trong danh sách MIME nén của demo.
- `GET /demo/snapshot`: nội dung **ổn định, có phiên bản**, cache công khai ngắn hạn và weak ETag để minh họa revalidation, đối chiếu với live streaming.

Sử dụng **Spring Boot 3.5.x, Java 17+**, dependency `spring-boot-starter-web` và `spring-boot-starter-test`. Embedded server mặc định là Tomcat. Tạo project bằng Spring Initializr, dùng Maven wrapper. Nếu dùng Spring Boot 4.x, hãy đối chiếu package test/auto-configuration và starter của phiên bản ấy thay vì giả định mọi import đều giữ nguyên.

### 6.1. Cấu trúc file

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ StreamCacheApplication.java
│  │  └─ StreamController.java
│  └─ resources/application.properties
└─ test/java/com/example/demo/
   └─ StreamHttpIntegrationTest.java
```

### 6.2. File cấu hình

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.compression.enabled=true
server.compression.mime-types=text/plain,application/json
server.compression.min-response-size=1B
spring.mvc.async.request-timeout=30s
```

### 6.3. Main class

**`src/main/java/com/example/demo/StreamCacheApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamCacheApplication.class, args);
    }
}
```

### 6.4. Controller

**`src/main/java/com/example/demo/StreamController.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/demo")
public class StreamController {

    @GetMapping(value = "/stream", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<StreamingResponseBody> stream() {
        StreamingResponseBody body = output -> {
            for (int index = 1; index <= 4; index++) {
                String chunk = "part=" + index
                    + ";payload=" + "JAVA".repeat(1000) + "\n";

                output.write(chunk.getBytes(StandardCharsets.UTF_8));
                output.flush();

                if (index < 4) {
                    pause();
                }
            }
        };

        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(
                "text/plain;charset=UTF-8"))
            .cacheControl(CacheControl.noStore())
            .header(HttpHeaders.VARY, HttpHeaders.ACCEPT_ENCODING)
            .body(body);
    }

    @GetMapping(value = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> events() {
        StreamingResponseBody body = output -> {
            for (int index = 1; index <= 2; index++) {
                String event = "event: tick\n"
                    + "id: " + index + "\n"
                    + "data: hello-" + index + "\n\n";
                output.write(event.getBytes(StandardCharsets.UTF_8));
                output.flush();

                if (index < 2) {
                    pause();
                }
            }
        };

        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .cacheControl(CacheControl.noStore())
            .body(body);
    }

    @GetMapping(value = "/snapshot",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> snapshot() {
        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .cacheControl(
                CacheControl.maxAge(60, TimeUnit.SECONDS).cachePublic()
            )
            .eTag("W/\"snapshot-v1\"")
            .header(HttpHeaders.VARY, HttpHeaders.ACCEPT_ENCODING)
            .body("snapshot=v1\n");
    }

    private static void pause() throws IOException {
        try {
            Thread.sleep(150);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IOException("Streaming interrupted", ex);
        }
    }
}
```

**Giải thích chính xác:**

1. `StreamingResponseBody` tạo body khi quá trình ghi bắt đầu trên MVC async worker, không xây một chuỗi 16KB trong controller rồi mới trả một lần.
2. `output.flush()` thử đẩy các phần dữ liệu ở bốn thời điểm; `pause()` làm khoảng cách giữa các lần viết dễ quan sát hơn. **`Thread.sleep` chỉ dùng cho demo**, không phải cách tạo streaming production.
3. `stream()` đặt `no-store` **trước khi gửi byte**, hợp với nội dung tạo theo yêu cầu mà không muốn browser/proxy lưu lại. Nó không đặt `Content-Length` do không biết độ dài biểu diễn sau nén.
4. `Vary: Accept-Encoding` giúp caches phân biệt các encoding variant nếu cache policy thay đổi sau này. Với `no-store`, Vary không thay thế no-store.
5. `events()` tạo text SSE hợp lệ: mỗi event có `event:`, `id:`, `data:` và **một dòng trống kết thúc event**. Đây là SSE hữu hạn để demo; SSE production có thể chạy lâu hơn, cần heartbeat, backpressure và reconnect.
6. `snapshot()` cố ý **không** dùng streaming: nó biểu diễn một tài nguyên đã version hóa và cache ngắn hạn, ETag yếu `W/"snapshot-v1"` nhằm tránh tuyên bố byte-identical giữa các content encodings. Spring MVC có hỗ trợ conditional request với `ResponseEntity` ETag; không tự dựng 304 cho streaming live.
7. Các endpoint chạy trên **HTTP** local cho dễ thử. Production cần HTTPS, authentication/authorization nếu nội dung riêng, timeout hợp lý và cân nhắc rủi ro nén dữ liệu bí mật.

**Chú ý về executor:** tài liệu Spring Framework khuyến nghị cấu hình một `TaskExecutor` thích hợp cho xử lý async streaming trong MVC thay vì dựa vào executor phát triển mặc định khi chạy tải lớn. Ví dụ nhỏ này chưa tinh chỉnh pool để giữ code tập trung. Với nhiều client stream lâu, đo số thread đang dùng và đặt giới hạn concurrency, timeout, queue, graceful shutdown cùng handling cho client disconnect.

## 7. Thử thủ công bằng curl: quan sát header và byte thật

Chạy ứng dụng:

```bash
java -version
./mvnw spring-boot:run
```

Trên Windows dùng `mvnw.cmd spring-boot:run`; khi PowerShell có alias cho `curl` hãy dùng `curl.exe`. Ví dụ sau dùng cú pháp Bash/Unix.

### 7.1. Baseline không nén

Yêu cầu identity coding:

```bash
curl --http1.1 -sS -D identity-headers.txt \
  -H 'Accept-Encoding: identity' \
  -o identity.txt \
  http://localhost:8080/demo/stream
```

Kiểm tra `identity-headers.txt`:

- Kỳ vọng `HTTP/1.1 200`.
- Có `Content-Type: text/plain;charset=UTF-8` (cách viết dấu cách/casing có thể khác).
- Có `Cache-Control: no-store`.
- **Thông thường không có** `Content-Encoding: gzip` khi yêu cầu `identity`.
- `Vary: Accept-Encoding`.
- Có thể thấy `Transfer-Encoding: chunked` nếu Tomcat phát body không biết length theo HTTP/1.1; **đừng kiểm thử bất biến bắt buộc header này phải có**.

File `identity.txt` chứa bốn đoạn:

```text
part=1;payload=JAVAJAVAJAVA...
part=2;payload=JAVAJAVAJAVA...
part=3;payload=JAVAJAVAJAVA...
part=4;payload=JAVAJAVAJAVA...
```

Các dấu `...` chỉ viết gọn để minh họa; **file thật có chuỗi `"JAVA"` lặp 1000 lần mỗi đoạn** (không chứa ký hiệu `...`). Trong ứng dụng demo, không có timestamp hay UUID nên byte nội dung nhất quán giữa các request; điều đó giúp so sánh gzip với identity.

### 7.2. Yêu cầu GZIP và kiểm tra payload

```bash
curl --http1.1 -sS -D gzip-headers.txt \
  -H 'Accept-Encoding: gzip' \
  -o response.gz \
  http://localhost:8080/demo/stream
```

**Đừng thêm `--compressed` ở lệnh này**: tùy công cụ, `--compressed` có thể tự giải nén trước khi ghi `-o`, khiến bạn tưởng file đã nén nhưng thực tế nó chứa text.

Kiểm tra `gzip-headers.txt` có `Content-Encoding: gzip`. Sau đó giải nén body raw:

```bash
gzip -dc response.gz > decoded.txt
cmp identity.txt decoded.txt
wc -c identity.txt response.gz
```

Kỳ vọng `cmp` không in gì và exit code bằng **0** nếu hai file trùng byte. Với chuỗi `JAVA` lặp lại nhiều, `response.gz` thường nhỏ hơn `identity.txt`; đây là kết quả phụ thuộc thực thi GZIP chứ không có con số cố định.

Có thể kiểm tra hai byte đầu GZIP thông qua công cụ hex (thường là `1f 8b`), nhưng **đừng chỉ dựa vào magic bytes**: giải nén thành công và so sánh dữ liệu vẫn có giá trị hơn.

Nếu phản hồi không có `Content-Encoding: gzip`, **đừng đổi kết luận thành “Spring không hỗ trợ streaming gzip”**. Kiểm tra lại `server.compression.enabled`, MIME thực, size/length, HTTP request headers, container đang dùng, các filter và proxy. Việc stream response được nén hay không có thể khác theo connector và version.

### 7.3. `curl --compressed` và bẫy tự giải nén

```bash
curl --http1.1 --compressed -sS \
  -D auto-headers.txt \
  -o auto-decoded.txt \
  http://localhost:8080/demo/stream
```

`--compressed` yêu cầu một content coding mà curl hỗ trợ và **giải nén tự động** cho dữ liệu nhận về. Vì vậy, file `auto-decoded.txt` có thể là **text đã giải nén** dù header server vẫn báo `Content-Encoding: gzip`. Nếu dùng file output để kết luận “không hề nén”, bạn sẽ nhầm.

Để kiểm chứng chính xác, phối hợp **response headers trên wire, dữ liệu raw**, giải nén và so sánh với bản identity.

### 7.4. Quan sát dữ liệu đến dần, không phải chỉ status 200

Để quan sát stream text không nén:

```bash
curl --http1.1 --no-buffer \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/demo/stream
```

`--no-buffer` (viết tắt `-N`) tắt buffering đầu ra của **curl**, nhưng không vô hiệu hóa buffer của container, GZIP hoặc reverse proxy. Nếu ứng dụng viết và flush theo khoảng 150 ms, bạn có thể thấy các phần xuất hiện từng đợt; khả năng quan sát còn phụ thuộc terminal/network.

Ghi thời gian tổng và TTFB bằng curl:

```bash
curl --http1.1 -sS -o /dev/null \
  -w 'ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/demo/stream
```

`time_starttransfer` đo thời gian đến byte đầu tiên theo cơ chế curl, **không cho biết khoảng cách giữa mọi phần**. Muốn đo chunk latency thật, cần client đọc streaming và timestamp lúc nhận từng đoạn, hoặc công cụ theo dõi network. Flush các write trong Java không bảo đảm mỗi write trở thành một network chunk hoặc lần đọc riêng ở client.

### 7.5. SSE: tránh nén và buffering khi yêu cầu độ trễ thấp

```bash
curl --http1.1 -N -i \
  -H 'Accept: text/event-stream' \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/demo/events
```

Kỳ vọng trong cấu hình demo:

- `Content-Type: text/event-stream`.
- `Cache-Control: no-store`.
- **Không có** `Content-Encoding: gzip` vì danh sách MIME nén **không** bao gồm `text/event-stream`.
- Body là hai event `tick` phân tách bởi dòng trống, không phải JSON array.
- Dữ liệu có thể đến theo hai lần viết cách nhau khoảng 150 ms ở app, nhưng proxy hoặc network có thể gom lại.

Nếu deploy qua Nginx hoặc proxy có buffering, bạn cần kiểm tra proxy buffering/cache/compression theo location cụ thể. Ví dụ **`X-Accel-Buffering: no`** là header được một số cấu hình Nginx hiểu để kiểm soát buffering; nó **không phải một cơ chế chuẩn được mọi proxy tôn trọng**. Với SSE, thiết kế heartbeat, cache bypass, idle timeout và proxy streaming settings theo hạ tầng thật.

### 7.6. Revalidation ở endpoint snapshot

Đầu tiên nhận ETag:

```bash
curl -i \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/demo/snapshot
```

Response có thể có:

```http
HTTP/1.1 200 OK
Cache-Control: max-age=60, public
ETag: W/"snapshot-v1"
Content-Type: text/plain
Vary: Accept-Encoding
```

Header ordering/casing thực tế thay đổi. Sau đó gửi `If-None-Match`:

```bash
curl -i \
  -H 'Accept-Encoding: identity' \
  -H 'If-None-Match: W/"snapshot-v1"' \
  http://localhost:8080/demo/snapshot
```

Với Spring MVC và controller mẫu, mong đợi **304 Not Modified**, **không có response body**. So sánh `/demo/stream`: endpoint đó không gắn ETag vì không có chính sách lưu/tái sử dụng, dù output demo có thể trông ổn định.

**Đừng dùng request trên để “chứng minh CDN cache hoạt động”**: curl mặc định không giữ HTTP cache như trình duyệt; nó chỉ cho thấy origin hỗ trợ conditional request. Để chứng minh cache ở browser/CDN/proxy, phải thử **qua đúng tầng cache** và quan sát hành vi/metrics của cache ấy.

## 8. Kiểm thử tích hợp qua HTTP thật, không chỉ dùng MockMvc

### Vì sao cần test end-to-end?

`MockMvc` hữu ích để kiểm tra controller, headers mà Spring đặt và async dispatch, nhưng **không chạy HTTP connector thật của embedded Tomcat/Jetty**, không chứng minh HTTP compression thực sự được áp dụng, chunked framing hay buffer network. Với compression và streaming, cần ít nhất một **integration test mở cổng thực** hoặc chạy curl qua môi trường tương ứng.

Tạo file:

**`src/test/java/com/example/demo/StreamHttpIntegrationTest.java`**

```java
package com.example.demo;

import java.io.ByteArrayInputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamHttpIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    private HttpResponse<byte[]> get(String path, String acceptEncoding)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri(path))
            .header("Accept-Encoding", acceptEncoding)
            .GET()
            .build();

        return client.send(request, HttpResponse.BodyHandlers.ofByteArray());
    }

    @Test
    void streamedResponseDeclaresNoStore() throws Exception {
        HttpResponse<byte[]> response = get(
            "/demo/stream", "identity"
        );

        assertEquals(200, response.statusCode());
        assertTrue(
            response.headers().firstValue("Cache-Control")
                .orElse("").contains("no-store")
        );
        assertTrue(
            response.headers().firstValue("Vary")
                .orElse("").contains("Accept-Encoding")
        );
        String body = new String(
            response.body(), StandardCharsets.UTF_8
        );
        assertTrue(body.contains("part=1;payload="));
        assertTrue(body.contains("part=4;payload="));
        assertTrue(body.endsWith("\n"));
    }

    @Test
    void gzipIsAppliedToStreamOverRealHttp() throws Exception {
        HttpResponse<byte[]> response = get(
            "/demo/stream", "gzip"
        );

        assertEquals(200, response.statusCode());
        assertEquals(
            "gzip",
            response.headers().firstValue("Content-Encoding")
                .orElse("")
        );

        // JDK HttpClient trả byte body nhận được; giải gzip chủ động.
        String decoded;
        try (GZIPInputStream gzip = new GZIPInputStream(
                new ByteArrayInputStream(response.body()))) {
            decoded = new String(
                gzip.readAllBytes(), StandardCharsets.UTF_8
            );
        }

        assertTrue(decoded.contains("part=1;payload="));
        assertTrue(decoded.contains("part=4;payload="));
        assertTrue(decoded.endsWith("\n"));
    }

    @Test
    void eventStreamIsNotCompressedInThisConfiguration()
            throws Exception {
        HttpResponse<byte[]> response = get(
            "/demo/events", "gzip"
        );

        assertEquals(200, response.statusCode());
        assertTrue(
            response.headers().firstValue("Content-Type")
                .orElse("").startsWith("text/event-stream")
        );
        assertTrue(
            response.headers().firstValue("Cache-Control")
                .orElse("").contains("no-store")
        );
        assertTrue(
            response.headers().firstValue("Content-Encoding").isEmpty()
        );

        String body = new String(
            response.body(), StandardCharsets.UTF_8
        );
        assertTrue(body.contains("data: hello-1\n\n"));
        assertTrue(body.contains("data: hello-2\n\n"));
    }

    @Test
    void snapshotSupportsConditionalGet() throws Exception {
        HttpResponse<byte[]> initial = get(
            "/demo/snapshot", "identity"
        );
        assertEquals(200, initial.statusCode());

        String etag = initial.headers().firstValue("ETag")
            .orElseThrow();

        HttpRequest conditional = HttpRequest.newBuilder(
                uri("/demo/snapshot"))
            .header("Accept-Encoding", "identity")
            .header("If-None-Match", etag)
            .GET()
            .build();

        HttpResponse<byte[]> response = client.send(
            conditional, HttpResponse.BodyHandlers.ofByteArray()
        );
        assertEquals(304, response.statusCode());
        assertEquals(0, response.body().length);
    }
}
```

**Lưu ý về imports:** `@Autowired` và `Environment` không được sử dụng trong class test trên nên có thể xóa hai import ấy cho sạch code; chúng không làm Java biên dịch sai, nhưng không cần trong project thật.

Chạy test khi **không có ứng dụng khác chiếm cổng cố định**, vì `@SpringBootTest(RANDOM_PORT)` khởi tạo một embedded server riêng trên port ngẫu nhiên:

```bash
./mvnw test
```

Bốn bài test được **kỳ vọng pass khi dùng Spring Boot 3.5.x + embedded Tomcat và cấu hình compression đúng như ví dụ**. Đó là kết quả thiết kế, **không phải tuyên bố đã chạy test trong repository thực tế**. Nếu test gzip không pass:

- Trước hết kiểm tra `Content-Encoding` và loại server hiện tại.
- Kiểm tra project có dùng Tomcat mặc định hay đã đổi sang Jetty/Undertow.
- Kiểm tra `application.properties` thực sự được load và profile/biến môi trường không ghi đè.
- Kiểm tra `Content-Type` của endpoint có khớp `server.compression.mime-types`.
- Kiểm tra client có gửi `Accept-Encoding: gzip`, có reverse proxy và không có filter tự nén/giải nén.
- Không “sửa” test bằng cách bỏ assert GZIP chỉ để nó xanh; test đang nhắm vào feature bạn muốn xác minh.

**Phạm vi test:** test `HttpClient.send(...ofByteArray())` đợi **toàn bộ** body rồi mới kiểm tra. Nó chứng minh gzip header và byte giải nén đúng, **không tự chứng minh chunk đến dần**. Để đo arrival latency, thêm một test/client `BodyHandlers.ofInputStream()` đọc stream theo thời gian hoặc dùng network tracing trực tiếp. Các phép kiểm cache phía CDN/proxy cũng phải chạy ở tầng cache thực.

## 9. Những lưu ý khiến test “đúng trên local, sai trên production”

### 9.1. Reverse proxy, CDN và response buffering

Đường đi phổ biến:

```text
Spring Boot MVC (flush)
       |
       v
Embedded Tomcat / gzip
       |
       v
Nginx / API gateway / CDN (có thể buffer, nén lại, cache)
       |
       v
TLS / network
       |
       v
Browser / curl / EventSource
```

Một proxy có thể nhận nhiều phần rồi mới gửi, dù application flush đúng. CDN có thể nén gzip/brotli, tự thêm `Vary` hoặc thực hiện cache theo cấu hình riêng. Vì vậy cần test cả **direct-to-app** và **qua URL production-like**, đồng thời so sánh headers, TTFB và khoảng cách event.

Một số proxy có tính năng buffer response mặc định; với SSE phải tắt buffering ở location phù hợp và bảo đảm idle timeout lớn hơn khoảng nghỉ giữa heartbeat/events. Không đổi global proxy config chỉ vì một endpoint: cần cân nhắc tài nguyên, bảo mật và các dịch vụ khác.

### 9.2. Không có `Content-Length` và xử lý lỗi sau khi đã gửi một phần

Nếu stream chưa biết tổng byte hoặc body sẽ được nén, **không tự set `Content-Length`** từ số ký tự hoặc kích thước chưa nén. HTTP/1.1 có thể dùng chunked; HTTP/2 có frame riêng. Khi server đã commit headers/body, một exception phát sinh giữa stream thường không thể đổi status 200 sang 500 một cách đáng tin. Client có thể thấy kết nối bị ngắt hoặc stream kết thúc bất thường.

Hệ thống production nên có:

- Log/metric cho **bắt đầu – hoàn tất – lỗi – client disconnect** của stream.
- Format có dấu hiệu hoàn tất hoặc event kết thúc nếu nghiệp vụ cần biết stream đầy đủ.
- Timeout, backpressure, giới hạn concurrent streams, resource cleanup và cancellation.
- Không rò rỉ stack trace/file path/secret vào data event khi lỗi.
- Đối với xuất file sinh dần, cân nhắc tạo file hoàn chỉnh trước nếu cần integrity hash, kiểm thử và download resume chính xác.

### 9.3. GZIP và rò rỉ thông tin theo kích thước

Nếu response nén chứa **bí mật** (CSRF token, session credential, thông tin nhạy cảm) được trộn với phần text mà kẻ tấn công điều khiển và có thể quan sát độ dài body, nén có thể góp phần vào **compression side-channel** (liên quan các lớp tấn công như BREACH). Không bật gzip tùy tiện cho mọi response nhạy cảm chỉ vì giảm băng thông.

Giảm thiểu theo threat model: tránh trộn secret vào output có thể được điều khiển, giảm khả năng quan sát và kiểm soát CORS/CSRF, cân nhắc tắt compression ở endpoint có rủi ro; TLS **không tự loại bỏ** suy luận dựa trên kích thước compressed response.

### 9.4. Shared cache làm lộ dữ liệu người dùng

`Cache-Control: public` trên response personalized hoặc xuất dữ liệu theo `Authorization`/cookie là rủi ro nếu proxy/cache key không tách user. `Vary: Accept-Encoding` chỉ phân biệt gzip vs identity; **không** thay thế việc phân quyền/đánh dấu `private`/`no-store`.

Một stream trả dữ liệu theo tenant/user nên mặc định được xem là nhạy cảm, trừ khi có quy tắc rõ cho public representation. Đừng chỉ quan sát “lần đầu chưa cache” rồi kết luận cache an toàn; phải kiểm tra tương tác giữa các user, các request khác nhau và cả URL/query/header tạo cache key.

### 9.5. Test chunk boundary có thể sai vì cách client nhận byte

Một lời gọi `write()` không tương ứng 1:1 với:

- một chunk ở HTTP/1.1,
- một HTTP/2 DATA frame,
- một TCP packet,
- một lần callback network của client.

Các tầng có thể phân mảnh hoặc hợp nhất dữ liệu. Nếu cần parsing stream theo sự kiện, sử dụng **định dạng có delimiter/framing rõ ràng** như SSE (dòng trống giữa events) hoặc NDJSON (mỗi JSON object một dòng), không dựa vào kích thước buffer hay ranh giới của `read()`.

### 9.6. “Server compression đã bật” không có nghĩa response nào cũng gzip

Kiểm tra cả điều kiện:

1. Client có `Accept-Encoding` chấp nhận coding ấy không?
2. `Content-Type` có thuộc danh sách MIME được nén không?
3. Response có vượt ngưỡng và đáp ứng các điều kiện của container không?
4. Có status/range/content coding trước đó hoặc tình huống không phù hợp để nén không?
5. Proxy/CDN có giải nén, nén lại hoặc thay header không?
6. Client đã tự động giải nén response trước khi đưa body tới test chưa?

Đừng kết luận từ **kích thước file output sau auto-decompression**. Hãy đối chiếu wire headers, raw encoded bytes và kết quả giải nén.

## 10. Checklist kiểm thử cache và compression cho streaming

| Câu hỏi | Cách kiểm tra | Kết quả cần đạt |
| --- | --- | --- |
| Response là streaming thật hay chỉ trả body sau khi hoàn tất? | `curl -N`; client đọc và timestamp byte, xem proxy buffering | Có byte/event đến dần theo SLA của ứng dụng |
| Header cache có đúng policy? | `curl -D headers.txt`, kiểm tra `Cache-Control` | Live/private stream -> thường `no-store` |
| Cache có giữ/trả lại nhầm một stream? | Test qua browser/CDN/proxy và metrics/cache status | Không lưu/tái sử dụng nội dung không được phép |
| GZIP có áp dụng khi yêu cầu? | `Accept-Encoding:gzip` + `Content-Encoding:gzip`, raw `.gz` | Byte thực giải nén hợp lệ, khớp bản identity |
| Không nén khi không yêu cầu? | `Accept-Encoding: identity` | Không có gzip content coding, body đọc được |
| `Vary` đã phân biệt variants? | Kiểm tra `Vary: Accept-Encoding` nếu applicable | Cache không trộn bản gzip/identity |
| SSE có giữ độ trễ thấp? | `curl -N`, proxy config và event timestamps | Không bị nén/buffer ngoài ý muốn |
| `Content-Length` có đúng? | So sánh raw byte, kiểm tra status/coding | Không set length sai, đặc biệt sau nén |
| HTTP/1.1 chunked có bị nhầm GZIP không? | Kiểm tra `Transfer-Encoding` và `Content-Encoding` | Hiểu đúng hai lớp khác nhau |
| Snapshot cache được không? | Request `If-None-Match` theo ETag | 304 không body nếu tài nguyên chưa đổi |
| Bật ShallowEtag filter ảnh hưởng stream? | Kiểm tra wrapper/filter và response latency/memory | Không buffer toàn stream chỉ để tính ETag |
| Test có chạy qua HTTP connector? | `@SpringBootTest(RANDOM_PORT)` hoặc curl tới Tomcat thật | Kiểm chứng nén/transfer trên wire |
| Lỗi giữa stream và client disconnect? | Test cắt kết nối, timeout, fault injection | Không leak resource, có log/metrics chính xác |
| Đầu vào/secret có gây side-channel hay cache leak? | Review sensitive endpoints và compression/cache policy | Không nén/cache sai thông tin nhạy cảm |

## 11. Những hiểu lầm cần tránh

**“Dùng `StreamingResponseBody` là response không thể cache.”** Sai. HTTP cacheability phụ thuộc policy, loại representation và khả năng cache giữ bản phản hồi hoàn chỉnh, không phụ thuộc riêng kiểu Java.

**“`no-cache` nghĩa là không được lưu.”** Sai. `no-store` mới hướng tới việc không lưu; `no-cache` hướng tới revalidation trước khi reuse.

**“Bật `server.compression.enabled=true` thì mọi response đều gzip.”** Sai. MIME, size, `Accept-Encoding`, container và proxy quyết định; cần đo response thực.

**“Có `Transfer-Encoding: chunked` tức đã nén.”** Sai. Chunked là framing của HTTP/1.1, không phải gzip.

**“Không thấy `Transfer-Encoding: chunked` nên không stream.”** Sai. HTTP/2/3 không dùng chunked, và HTTP/1.1 còn có các cách xác định body framing khác.

**“`curl --compressed` ghi file đã gzip.”** Sai trong nhiều trường hợp: curl **tự giải nén**, nên `-o` nhận nội dung đã giải mã.

**“Gọi `flush()` là browser nhìn thấy event ngay.”** Sai. GZIP, proxy buffering, TLS và network có thể trì hoãn hoặc gom write.

**“Tính ETag cho stream bằng filter là miễn phí.”** Sai. `ShallowEtagHeaderFilter` tạo giá trị từ toàn bộ body và có thể buffer, làm mất đặc tính phát từng phần.

**“ETag của gzip và identity luôn dùng chung strong tag.”** Không an toàn về ngữ nghĩa validator mạnh. Representation bytes khác nhau có thể cần strong ETag khác nhau; weak ETag có ý nghĩa so sánh ngữ nghĩa rộng hơn, theo contract HTTP.

**“Kiểm thử MockMvc đã xác nhận có nén trên wire.”** Sai. MockMvc không đi qua Tomcat HTTP connector thật; dùng integration test hoặc curl.

**“Chỉ cần thấy `Cache-Control: no-store` là CDN chắc chắn không cache.”** Đây là directive chuẩn, nhưng vẫn phải kiểm tra cấu hình cache/proxy cụ thể, đặc biệt khi có rule override hoặc lỗi triển khai.

## 12. Câu hỏi tự kiểm tra

1. **Response streaming có mặc định `Cache-Control: no-store` không?** Không. Thiết lập rõ theo loại dữ liệu và chính sách.
2. **Một stream CSV đã hoàn tất, có version ổn định, có thể cache không?** Có thể, nếu policy và validator thích hợp, cache nhận được toàn bộ representation và không có dữ liệu riêng tư không được phép lưu.
3. **SSE nên bị nén mọi lúc để tiết kiệm băng thông không?** Không. SSE cần xét latency và buffering, thường không nén khi ưu tiên phát event sớm.
4. **Client gửi `Accept-Encoding: gzip`, nhưng response không có `Content-Encoding`, đó là lỗi chắc chắn không?** Không. Server có thể chọn identity khi điều kiện nén không phù hợp hoặc không được cấu hình.
5. **`Content-Length` phải là số byte trước gzip hay sau gzip?** Nếu có header trên response gzip, phải phản ánh byte của content coding thực sự được gửi theo HTTP semantics, không phải độ dài text gốc.
6. **Dùng `curl --compressed` mà output vẫn đọc được text có nghĩa server không nén?** Không; curl có thể đã giải nén.
7. **`ShallowEtagHeaderFilter` có thể làm client nhận chậm hơn không?** Có. Nó có thể buffer toàn response trước khi truyền, trái mục tiêu streaming.
8. **Một lần `output.write` là một HTTP chunk?** Không. Có nhiều tầng buffer/framing, không có bảo đảm 1:1.
9. **Muốn xác nhận 304 phải hỏi endpoint nào trong demo?** `/demo/snapshot` với `If-None-Match`. Stream live `/demo/stream` dùng `no-store` và không có ETag.
10. **Có nên cache shared response phụ thuộc cookie/user chỉ vì đã đặt `Vary: Accept-Encoding`?** Không. `Vary` cho content coding không đảm bảo cô lập user; cần policy authorization và private/no-store phù hợp.

## 13. Tài liệu chính thức để đối chiếu

- Spring Boot 3.5, *Common Application Properties*: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/ (xem `server.compression.*` và `spring.mvc.async.request-timeout`).
- Spring Framework, *Asynchronous Requests (Spring MVC)*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html (xem `StreamingResponseBody`, `SseEmitter` và async executor).
- Spring Framework, *HTTP Caching (MVC)*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html (xem `CacheControl`, `ETag`, `Last-Modified` và `304`).
- Spring Framework, *HTTP Caching (WebFlux)*: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html.
- Spring Framework, `ShallowEtagHeaderFilter` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html (xem `disableContentCaching`).
- RFC 9110, *HTTP Semantics*: https://www.rfc-editor.org/rfc/rfc9110 (xem Content-Encoding, Accept-Encoding, Vary, ETag và framing).
- RFC 9111, *HTTP Caching*: https://www.rfc-editor.org/rfc/rfc9111 (xem ý nghĩa `no-store`, `no-cache`, `private`, `public`).
- MDN, *Content-Encoding*: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Encoding.
- MDN, *Server-sent events*: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events.

**Kết luận:** để kiểm tra caching hoặc compression khi Spring Boot gửi body theo stream, phải phân biệt **chính sách cache**, **nội dung đã nén trên wire**, và **thời điểm byte/event thực sự đến client**. Dùng `Cache-Control` theo tính chất dữ liệu, `Vary` khi có variants, cấu hình `server.compression.*` có kiểm chứng, loại trừ buffering ETag filter với stream live, và kiểm thử bằng HTTP connector thật. Đối chiếu direct-to-app với reverse proxy/CDN trước khi kết luận sản phẩm đã streaming, nén và cache đúng.