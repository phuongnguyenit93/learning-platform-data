# Content-Length, truyền dữ liệu theo luồng và thời điểm hoàn tất phản hồi

> **Phạm vi:** HTTP trong ứng dụng Spring Boot web-runtime. Bài học tập trung vào cách bên nhận biết ranh giới phần thân phản hồi, cách máy chủ phát dữ liệu dần theo thời gian và khi nào một phản hồi thật sự hoàn tất. Ví dụ dùng Java 17+ và Spring MVC; phần WebFlux được tách riêng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `Content-Length` theo **byte truyền đi**, phân biệt với số ký tự, thời gian xử lý và kích thước dữ liệu trước khi nén.
2. Phân biệt response có kích thước đã biết, response truyền dần (`streaming`), HTTP/1.1 `Transfer-Encoding: chunked` và cơ chế kết thúc stream của HTTP/2.
3. Nhận diện bốn mốc khác nhau: handler trả về, header được commit, từng phần dữ liệu được flush và HTTP response hoàn tất.
4. Chọn cách trả dữ liệu trong Spring MVC hoặc WebFlux, kiểm tra qua `curl` và xử lý các lỗi thường gặp như ngắt kết nối, timeout hay response đã commit.

## 2. HTTP cần biết ranh giới thông điệp để làm gì?

Một response HTTP/1.1 thông thường có dòng trạng thái, các header, dòng trống rồi đến phần thân (nếu được phép có thân):

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Length: 5

Hello
```

Ở ví dụ này, `Content-Length: 5` nghĩa là **5 octet (5 byte)** của phần thân. Client đọc đúng 5 byte rồi biết phần thân kết thúc; kết nối TCP vẫn có thể được giữ để tái sử dụng cho request khác. Giá trị này **không** nói rằng server đã xử lý xong nghiệp vụ, client đã đọc xong dữ liệu trong ứng dụng, hay toàn bộ dữ liệu phải được gửi trong một lần `write`.

Phân biệt các khái niệm:

| Khái niệm | Ý nghĩa thực tế |
|---|---|
| `Content-Length` | Độ dài nội dung theo byte, dùng để xác định ranh giới nội dung khi áp dụng quy tắc framing tương ứng. |
| `Content-Type` | Kiểu nội dung và, nếu có, charset; không cho biết độ dài. |
| `Content-Encoding: gzip` | Nội dung được mã hóa/nén; độ dài truyền đi có thể khác dữ liệu gốc. |
| `Transfer-Encoding: chunked` | Cách **HTTP/1.1** đóng khung phần thân thành các chunk có dấu kết thúc; không phải format của JSON hay cấu trúc nghiệp vụ. |
| Streaming | Chiến lược tạo/gửi từng phần dữ liệu thay vì chờ tạo xong toàn bộ. Có thể thực hiện với độ dài biết trước hoặc chưa biết trước. |
| Response complete | Server đã hoàn tất việc tạo/gửi phản hồi theo giao thức hoặc kết thúc xử lý response; không đồng nghĩa mọi tầng nhận đã tiêu thụ xong dữ liệu. |

### Đếm byte, không đếm ký tự

Trong Java, `String.length()` đếm đơn vị UTF-16, còn HTTP `Content-Length` cần số byte thực sự được gửi. Ví dụ độc lập sau biên dịch được bằng JDK 17:

```java
// File: ByteLengthDemo.java
import java.nio.charset.StandardCharsets;

public class ByteLengthDemo {
    public static void main(String[] args) {
        String text = "A😊";
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        System.out.println(text.length());
        System.out.println(payload.length);
    }
}
```

Chạy bằng `javac ByteLengthDemo.java` và `java ByteLengthDemo`, stdout chính xác là:

```text
3
5
```

`A` chiếm 1 byte UTF-8; emoji chiếm 4 byte UTF-8 nhưng 2 code unit UTF-16. Nếu payload thực tế là mảng `payload`, giá trị độ dài hợp lệ là `5`, không phải `3`. Với JSON, ảnh, file hoặc UTF-8 nhiều dấu tiếng Việt, luôn tính theo **byte sau khi tuần tự hóa và mã hóa thực tế**.

## 3. Ba cơ chế xác định điểm cuối của response

### Trường hợp A — Độ dài được biết trước

Khi phản hồi có phần thân hợp lệ, không dùng `Transfer-Encoding`, và server biết chính xác byte count, server có thể gửi `Content-Length: N`. Client xác định điểm cuối khi nhận đủ N byte. Chẳng hạn tệp tĩnh hoặc mảng `byte[]` đã tạo sẵn thường phù hợp.

Điều này **không cấm streaming**: server vẫn có thể ghi 100 lần vào socket, miễn tổng số byte thuộc response đúng N. Ngược lại, việc có sẵn N byte không có nghĩa mỗi byte phải được chuyển đến client ngay lập tức; hệ điều hành, TLS, proxy và client đều có thể đệm.

### Trường hợp B — Chưa biết độ dài: HTTP/1.1 chunked

Với response HTTP/1.1 có phần thân dài chưa biết trước, server thường dùng `Transfer-Encoding: chunked`. Mỗi chunk chứa kích thước hệ thập lục phân, dữ liệu và CRLF; **chunk cuối kích thước 0** đánh dấu phần thân kết thúc. Ví dụ minh họa theo dòng (thực tế các dòng kết thúc bằng CRLF):

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked
Content-Type: text/plain

5
Hello
6
 World
0

```

Các byte nội dung ghép lại là `Hello World` (11 byte); `5`, `6`, `0` và CRLF là framing, không phải nội dung ứng dụng. Server có thể chia chunk theo kích thước khác tùy bộ đệm và runtime, nên **một lần `write` không nhất thiết tương ứng đúng một HTTP chunk**. `curl` thông thường giải mã chunked trước khi hiển thị body.

**Không tự đặt cả `Content-Length` và `Transfer-Encoding` trong cùng message.** Theo HTTP, sender không được gửi đồng thời hai header này. Các framing không nhất quán có thể gây đọc thiếu/dư dữ liệu và tạo lỗ hổng khi proxy với server hiểu khác nhau.

### Trường hợp C — HTTP/2, HTTP/3 và cách kết thúc stream

HTTP/2 truyền nội dung trong các DATA frame, và cờ `END_STREAM` báo stream đã kết thúc (hoặc HEADERS kết thúc stream khi không có body). **HTTP/2 không dùng `Transfer-Encoding: chunked`**; các header phụ thuộc kết nối như `Transfer-Encoding` bị cấm. HTTP/3 cũng dùng framing riêng của giao thức thay cho HTTP/1.1 chunked.

`Content-Length` **vẫn có thể xuất hiện trong HTTP/2** nếu biết chính xác độ dài. Khi có, số byte nội dung phải khớp lượng DATA thực tế theo quy tắc protocol. Không thấy `Transfer-Encoding: chunked` ở HTTP/2 là bình thường, không có nghĩa response không được streaming.

Trong HTTP/1.0 hoặc một số tình huống tương thích cũ, response không có độ dài có thể dùng **đóng kết nối** để phân định kết thúc. Cách này khó phân biệt hoàn tất bình thường với đứt kết nối giữa chừng; ưu tiên framing có ranh giới rõ ràng khi có thể.

### Những response không mang phần thân

Response cho `HEAD`, các status `1xx`, `204 No Content` và `304 Not Modified` **không có response body** theo HTTP semantics. `Content-Length` bị cấm trong response `1xx` hoặc `204`; với `HEAD` và `304` có điều kiện, nếu gửi header này thì phải là độ dài sẽ có trong response GET tương ứng, **không phải số byte body đã gửi** (thực tế bằng 0). Response `2xx` cho `CONNECT` chuyển sang tunnel, có quy tắc framing khác.

Đối với **request body** (ví dụ POST upload), `Content-Length` cũng là số byte mà server kỳ vọng đọc nếu không có transfer coding. Việc server nhận đủ request body và thời điểm server hoàn tất response là hai mốc độc lập.

## 4. Streaming: “trả dần” khác “gửi chunked”

Streaming nghĩa là ứng dụng tạo hoặc chuyển tiếp dữ liệu theo từng phần: tải file lớn, nhật ký tiến độ, SSE, NDJSON hoặc kết quả từ hệ thống upstream. Mục đích thường là giảm bộ nhớ giữ toàn bộ payload và giảm thời gian đến byte đầu tiên.

| Tình huống | Độ dài biết trước? | Cách làm điển hình |
|---|---|---|
| `byte[]` nhỏ đã tạo hoàn chỉnh | Có | Trả một response bình thường; có thể đặt `Content-Length` theo `byte[].length`. |
| File lớn, biết kích thước và không đổi trong lúc đọc | Có | Ghi file theo từng block; có thể giữ `Content-Length` chính xác. |
| Kết quả tạo dần, chưa biết số phần | Không | Streaming; HTTP/1.1 thường dùng chunked; HTTP/2 dùng các DATA frame. |
| SSE tiến độ hoặc sự kiện liên tục | Thường không | `text/event-stream`, phát/flush sự kiện và hoàn tất khi nguồn kết thúc; stream vô hạn không có completion bình thường. |
| Dữ liệu JSON dạng `application/json` thông thường | Tùy | Framework có thể gom/đệm; không được suy ra từng item đến ngay chỉ vì trả `Flux`. Chọn media type dành cho stream nếu cần phát liên tục. |

Ba tầng cần phân biệt: **(1)** ứng dụng gọi `write` hoặc phát một item, **(2)** runtime flush/đẩy byte tới tầng giao thức, **(3)** client thực sự thấy và xử lý dữ liệu. Buffering ở response wrapper, servlet container, reverse proxy, HTTP/TLS, kernel và thư viện client có thể khiến các tầng xảy ra lệch thời điểm. `flush()` yêu cầu đẩy dữ liệu đã đệm xuống tầng dưới; nó **không chứng minh dữ liệu đã tới màn hình hoặc được client xử lý**. Các proxy như Nginx có thể tiếp tục đệm dù ứng dụng đã flush.

**Streaming không đồng nghĩa chunked.** Chunked là một kỹ thuật đóng khung của HTTP/1.1, trong khi streaming là cách phát dữ liệu qua thời gian và có thể dùng với cả HTTP/2, HTTP/3 hoặc response có `Content-Length` chính xác.

## 5. Timeline: khi nào response thật sự hoàn tất?

```text
T0  Request tới container
    |
T1  Handler quyết định status, headers, response body hoặc publisher
    |
T2  Response committed: status/header đã được đưa vào luồng xuất
    |   (thường ở lần flush đầu, khi buffer đầy hoặc khi container commit)
T3  Write + flush phần 1 --- Write + flush phần 2 --- ... phần cuối
    |
T4  Kết thúc theo giao thức:
    |   đủ N byte (Content-Length), chunk 0, hoặc END_STREAM
T5  Client nhận/giải mã/đọc xong; có thể muộn hơn T4
```

- **Handler return (T1):** phương thức controller đã trả `ResponseEntity`, `StreamingResponseBody`, `Mono` hoặc `Flux`. Với response bất đồng bộ, công việc tạo body có thể mới bắt đầu. `return` của controller **không phải** tín hiệu “đã gửi xong”.
- **Commit (T2):** status và header đã được chốt để gửi; với Servlet có thể kiểm tra `HttpServletResponse.isCommitted()`. Sau commit, thông thường không thể đổi từ `200` thành `500` hoặc gửi một JSON error mới bằng cách reset response.
- **Flush (T3):** đẩy dữ liệu đã ghi qua các buffer có thể flush; response vẫn mở và các byte tiếp theo vẫn có thể đến. Flush không tự động kết thúc response.
- **Completion phía server (T4):** framework/container đã kết thúc response thành công theo giao thức, hoặc đường xử lý async đã được hoàn tất. Nếu stream bị lỗi, có thể kết thúc bất thường trước khi thông điệp hoàn chỉnh.
- **Hoàn tất phía client (T5):** client xử lý và tiêu thụ xong nội dung là mốc khác. Server không thể suy ra điều đó chỉ từ `write`/`flush` trả về hay callback completion của framework.

Khi phát response có `Content-Length: 1000`, client kỳ vọng đủ **1000 byte**: nếu kết nối đóng sau 700 byte thì thông điệp thiếu dữ liệu, không phải hoàn tất thành công. Với HTTP/1.1 chunked, **chunk 0** là dấu kết thúc hợp lệ; nếu chỉ đóng socket trước chunk 0 thì body không hoàn chỉnh. Với HTTP/2, cần kết thúc stream hợp lệ; reset stream giữa chừng không phải thành công.

## 6. Thí nghiệm Spring MVC: một endpoint cố định, một endpoint streaming

Tạo một ứng dụng Spring Boot dùng `spring-boot-starter-web` (Spring MVC, Java 17+). Trong dự án Spring Boot đã có dependency này, đặt **nguyên tệp** sau tại `src/main/java/example/http/FramingApplication.java`:

```java
package example.http;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class FramingApplication {

    public static void main(String[] args) {
        SpringApplication.run(FramingApplication.class, args);
    }

    @RestController
    static class HttpController {
        private static final MediaType TEXT_UTF8 =
                new MediaType("text", "plain", StandardCharsets.UTF_8);

        @GetMapping("/http/fixed")
        ResponseEntity<byte[]> fixed() {
            byte[] body = "Xin chào từ Spring Boot!\n"
                    .getBytes(StandardCharsets.UTF_8);
            return ResponseEntity.ok()
                    .contentType(TEXT_UTF8)
                    .contentLength(body.length)
                    .body(body);
        }

        @GetMapping("/http/stream")
        ResponseEntity<StreamingResponseBody> stream() {
            StreamingResponseBody writer = output -> {
                for (int i = 1; i <= 3; i++) {
                    byte[] part = ("Phần " + i + "\n")
                            .getBytes(StandardCharsets.UTF_8);
                    output.write(part);
                    output.flush();

                    try {
                        Thread.sleep(500);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IOException("Luồng ghi bị gián đoạn", e);
                    }
                }
            };

            return ResponseEntity.ok()
                    .contentType(TEXT_UTF8)
                    .body(writer);
        }
    }
}
```

**Vì sao code đúng với mục tiêu?**

- `/http/fixed` tính byte UTF-8 trước khi set `contentLength(body.length)`. Nó có response body với kích thước xác định.
- `/http/stream` trả về `StreamingResponseBody`: callback ghi trực tiếp vào `OutputStream` trong cơ chế xử lý async của Spring MVC; controller có thể kết thúc lời gọi trước khi toàn bộ body hoàn tất.
- Vòng lặp phát ba phần và flush mỗi phần. `Thread.sleep(500)` chỉ để quan sát; **không dùng sleep để đồng bộ nghiệp vụ trong production**. `IOException` phát sinh khi có vấn đề ghi được chuyển cho runtime; không tự trả một body lỗi mới sau khi response đã commit.
- Endpoint streaming **không tự đặt `Content-Length`** vì ví dụ nhằm minh họa kết thúc do runtime/giao thức. Với embedded Tomcat chạy HTTP/1.1 và không có tầng trung gian thay đổi, thường sẽ thấy `Transfer-Encoding: chunked`. Đây là kết quả triển khai có thể thay đổi theo giao thức và cấu hình.

Chạy ứng dụng bằng lệnh của dự án (`./gradlew bootRun` trên hệ Unix hoặc `gradlew.bat bootRun` trên Windows). Ở terminal khác:

```bash
curl -i --http1.1 http://localhost:8080/http/fixed
curl -i -N --http1.1 http://localhost:8080/http/stream
```

`-i` hiển thị header; `-N` tắt buffer ở đầu ra của `curl` để dễ thấy ba phần xuất hiện dần. Body dự kiến của request stream (mỗi dòng cách nhau xấp xỉ 0,5 giây trong điều kiện thử nghiệm cục bộ):

```text
Phần 1
Phần 2
Phần 3
```

Dùng `curl -v -N --http1.1 ...` để quan sát thông tin giao thức. Nếu muốn xem bytes framing chunked mà `curl` thường giải mã, dùng `curl --raw -i -N --http1.1 http://localhost:8080/http/stream`; ranh giới và kích thước chunk **không được cố định** theo ba lần ghi ứng dụng. Khi thí nghiệm, tạm tắt nén và đi trực tiếp vào embedded server để thấy kết quả dễ đối chiếu.

Lưu ý khi đưa Spring MVC streaming vào production: I/O ghi trong Servlet stack thường là **blocking** và `StreamingResponseBody` được chạy qua async executor. Cần cấu hình `AsyncTaskExecutor` phù hợp, timeout, giới hạn số luồng và kiểm tra tải/chậm client; không đặt vô hạn công việc blocking vào executor mặc định.

## 7. Spring WebFlux: completion của nguồn dữ liệu

Trong **một ứng dụng Spring Boot WebFlux riêng** sử dụng `spring-boot-starter-webflux` (không ghép ví dụ này vào dự án MVC phía trên để tránh thay đổi runtime dự kiến), controller sau phát ba sự kiện SSE. Giả sử ứng dụng đã có lớp `@SpringBootApplication` tại package cha `example.http`.

```java
// File: src/main/java/example/http/EventController.java
package example.http;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventController {
    @GetMapping(path = "/http/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
                .take(3)
                .map(index -> ServerSentEvent.<String>builder(
                                "Phần " + (index + 1))
                        .event("progress")
                        .build());
    }
}
```

Chạy `curl -N -i http://localhost:8080/http/events`. Dữ liệu trên wire có dạng SSE, ví dụ `event:progress` và `data:Phần 1`, sau đó một dòng trống, rồi tới sự kiện tiếp theo. Khi `.take(3)` phát đủ ba item, `Flux` phát **onComplete**; framework ghi kết thúc response khi phần dữ liệu còn đệm đã được xử lý. Nếu client hủy kết nối sớm, subscription có thể nhận **cancel**, không phải completion thành công. Một `Flux` không kết thúc (ví dụ nguồn sự kiện dài hạn) sẽ giữ response mở cho đến khi bị hủy, lỗi hoặc đóng có chủ đích.

Với WebFlux, `Mono` thường biểu diễn tối đa một kết quả; `Flux` biểu diễn nhiều kết quả; codec và media type quyết định cách tuần tự hóa/flush. Trả `Flux<T>` với `application/json` **không cam kết** từng phần xuất hiện ngay; dùng `text/event-stream` hay NDJSON khi yêu cầu của API là truyền từng item tới client. Backpressure giúp điều phối tốc độ phát trong pipeline reactive, nhưng không tự loại bỏ việc proxy/client buffer.

## 8. Commit, completion và lỗi trong từng mô hình

### Servlet/Spring MVC

- Với Servlet, `response.flushBuffer()` buộc flush buffer và commit response; `response.isCommitted()` cho biết header/status đã được commit hay chưa. Gọi `flushBuffer()` **không** có nghĩa Servlet đã kết thúc phần thân.
- Với phản hồi đồng bộ thông thường, việc xử lý return value và ghi body do Spring/container thực hiện. Với `StreamingResponseBody`, việc controller return và việc callback ghi xong xảy ra tại các thời điểm khác nhau.
- `ResponseBodyEmitter` / `SseEmitter` hỗ trợ `send(...)` nhiều lần rồi gọi `complete()` hoặc `completeWithError(...)`; có các callback `onCompletion`, `onTimeout`, `onError` để quản lý tài nguyên và quan sát vòng đời. Callback completion là vòng đời xử lý server, không chứng minh client hiển thị thành công.
- Servlet async ở tầng thấp có `AsyncContext.complete()` và `AsyncListener.onComplete/onError/onTimeout`; application phải tránh bỏ quên việc complete, khiến response giữ mở cho tới timeout. Với Spring MVC, ưu tiên API async của framework thay vì tự thao tác `AsyncContext` khi không cần.
- Trong quá trình streaming, client ngắt kết nối thường được phát hiện ở **lần ghi tiếp theo** qua `IOException`; Servlet không bảo đảm thông báo ngay khi client rời đi. Với SSE dài hạn, cân nhắc heartbeat và cleanup tài nguyên.

### WebFlux/Reactor

- `onComplete` kết thúc bình thường của publisher; `onError` kết thúc bất thường; `cancel` là tín hiệu tiêu thụ bị hủy (có thể do client disconnect). Những sự kiện này liên quan pipeline nguồn; byte vẫn có thể đang trên đường truyền hoặc trong buffer dưới.
- Việc `ServerHttpResponse` hoàn tất ghi và đóng stream theo giao thức là thước đo phía server. Nó không có bằng chứng rằng ứng dụng client đã parse, hiển thị hoặc lưu xong nội dung.
- Nếu lỗi xảy ra **trước commit**, framework thường còn khả năng chọn status/header lỗi. Nếu **sau commit**, không thể tin rằng `@ExceptionHandler` sẽ chuyển toàn bộ response đã phát thành JSON lỗi; kết nối/stream có thể đóng bất thường. Thiết kế định dạng streaming có khả năng thể hiện event lỗi nghiệp vụ trước khi chủ động kết thúc, nếu giao thức ứng dụng cho phép.

### Mốc hoàn tất phụ thuộc lớp nào?

| Mốc quan sát | Điều có thể kết luận | Điều không thể kết luận |
|---|---|---|
| Controller đã return | Handler đã chuyển kết quả/callback/publisher cho framework | Body đã gửi xong |
| `isCommitted() == true` | Header/status không còn sửa tự do | Client đã nhận đủ body |
| `flush()` không báo lỗi | Lời gọi ghi/flush ở tầng hiện tại đã trả về | Từng byte đã qua proxy và được client đọc |
| MVC `complete()`, WebFlux publisher `onComplete` | Nguồn/đường xử lý ứng dụng đã kết thúc bình thường | Không thể có lỗi I/O phía dưới hay client đã tiêu thụ xong |
| Client nhận đủ `Content-Length`, chunk cuối hoặc `END_STREAM` | Message body hoàn chỉnh theo giao thức ở client | Logic nghiệp vụ client đã thực hiện xong |

## 9. Quan sát, kiểm thử và xử lý sự cố

1. **Kiểm tra byte và header của payload cố định:** so sánh `Content-Length` với số byte thực tế sau serialization và `Content-Encoding`. Với Java, dùng `byte[].length`, không dùng `String.length()`.
2. **Quan sát truyền dần:** dùng `curl -N -v --http1.1`, xem thời điểm nhận dữ liệu, không chỉ nhìn lúc lệnh kết thúc. Với proxy, thử gọi trực tiếp embedded server rồi qua proxy để tìm tầng đệm.
3. **Kiểm tra từng giao thức:** so sánh HTTP/1.1 với HTTP/2 nếu server/proxy đã bật HTTP/2. Đừng đòi `Transfer-Encoding: chunked` trong HTTP/2; tìm mốc kết thúc stream và quan sát tốc độ dữ liệu.
4. **Thử client ngắt ngang:** dừng `curl` khi đang stream, quan sát `IOException` / cancel / callback cleanup, số kết nối mở và tài nguyên đang giữ.
5. **Thử timeout và lỗi sau khi flush:** quan sát response đã commit có thể bị cắt giữa chừng, chứ không nhất thiết quay về HTTP 500 kèm body hoàn chỉnh. Với stream dài hạn, đặt timeout phù hợp và có chiến lược retry, resume hoặc thông báo lỗi ở tầng ứng dụng.
6. **Kiểm tra qua mạng thật:** unit test controller hoặc `MockMvc` hữu ích cho nội dung và mapping nhưng không thay thế integration test qua cổng HTTP thực để kiểm tra chunking, flush, proxy, compression và disconnect.

Một số triệu chứng điển hình:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Client đợi toàn bộ phản hồi mới thấy dữ liệu | Buffering ở converter, proxy, compression hoặc client; media type không phù hợp streaming | Chọn API/media type streaming, kiểm tra flush từng tầng, thử `curl -N` và kiểm tra cấu hình proxy |
| Client báo incomplete/connection reset | `Content-Length` sai, thiếu chunk kết thúc, stream reset hoặc mất kết nối | Đối chiếu byte count/framing; log lỗi I/O, timeout và disconnect |
| API trả 200 dù phát dữ liệu bị lỗi về sau | Header đã commit trước khi lỗi xảy ra | Phân biệt lỗi trước/sau commit; nếu cần, gửi event báo lỗi theo định dạng stream và xử lý retry phía client |
| Mất nhiều bộ nhớ khi gửi file lớn | Tạo toàn bộ `byte[]`/JSON trong RAM | Dùng `Resource`, stream theo block hoặc pipeline phù hợp; giới hạn số stream đồng thời |
| Kết nối SSE lâu ngày hết tài nguyên | Không cleanup subscription, không timeout/heartbeat, client ngắt mà chưa phát hiện | Theo dõi completion/cancel/error, đóng upstream, quản lý heartbeat và giới hạn kết nối |
| Header `Content-Length` không khớp khi bật gzip | Đếm byte trước nén nhưng truyền body sau nén | Để runtime quản lý framing khi nén hoặc chỉ đặt length khi biết chính xác bytes sau mã hóa |

## 10. Quy tắc thiết kế cần nhớ

- **Biết chính xác độ dài byte cuối cùng:** dùng `Content-Length` đúng giá trị nếu phù hợp; với Spring Boot thường để framework/container tự xử lý nếu không cần kiểm soát thủ công.
- **Không biết độ dài:** không bịa hoặc “ước lượng” `Content-Length`. Server chọn framing hợp lệ theo phiên bản HTTP; có thể stream không cần lưu toàn bộ payload vào bộ nhớ.
- **Muốn client thấy từng tiến độ:** dùng định dạng phát dần phù hợp (SSE, NDJSON hoặc nhị phân chia block), flush có kiểm soát, kiểm tra các tầng đệm, xử lý đóng sớm.
- **Muốn đảm bảo dữ liệu được client xử lý:** cần cơ chế xác nhận ở **tầng ứng dụng** (ack, checkpoint, offset, idempotency...), vì server-side completion và TCP ACK không đồng nghĩa ứng dụng client đã hoàn thành công việc.
- **Sau commit:** đừng kỳ vọng đổi status hoặc thay thế body đã gửi; thiết kế logging, lỗi và giao thức streaming ngay từ đầu.

## 11. Tự kiểm tra

**Câu 1.** Java `String.length()` bằng 12 thì `Content-Length` có bắt buộc là 12 không?  
**Đáp:** Không. Phải đo bytes của nội dung thực sự được gửi, sau khi chọn charset/serialization/encoding.

**Câu 2.** Có `Transfer-Encoding: chunked` nghĩa là dữ liệu đã tới trình duyệt ngay sau mỗi `write()` không?  
**Đáp:** Không. Đó là framing HTTP/1.1; runtime, mạng, proxy và client còn có thể đệm. Một `write()` không nhất thiết bằng một chunk.

**Câu 3.** Một controller đã `return StreamingResponseBody` có nghĩa response hoàn tất chưa?  
**Đáp:** Chưa. Callback còn phải ghi và kết thúc; framework/container sau đó mới khép response theo giao thức.

**Câu 4.** HTTP/2 response đang streaming mà không có `Transfer-Encoding: chunked` có sai không?  
**Đáp:** Không. HTTP/2 dùng DATA frame và `END_STREAM`; chunked của HTTP/1.1 không được sử dụng.

**Câu 5.** `onComplete` trên server có bảo đảm client đã ghi dữ liệu vào cơ sở dữ liệu của nó không?  
**Đáp:** Không. Nếu cần bảo đảm này, client phải xác nhận riêng theo giao thức ứng dụng.

## Tài liệu chuẩn để đào sâu

- [RFC 9110 §8.6 — Content-Length](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6): ý nghĩa và các trường hợp đặc biệt.
- [RFC 9112 §6–7 — HTTP/1.1 framing và chunked](https://www.rfc-editor.org/rfc/rfc9112.html#section-6): cách xác định độ dài message body và chunk kết thúc.
- [RFC 9113 §8 — HTTP/2 messages](https://www.rfc-editor.org/rfc/rfc9113.html#section-8): DATA, END_STREAM và header bị cấm trong HTTP/2.
- [Spring Framework — Asynchronous Requests (MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `StreamingResponseBody`, `ResponseBodyEmitter`, SSE, executor và disconnect.
- [Spring Framework — Reactive Core (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): xử lý I/O non-blocking, codec và Reactive Streams.
