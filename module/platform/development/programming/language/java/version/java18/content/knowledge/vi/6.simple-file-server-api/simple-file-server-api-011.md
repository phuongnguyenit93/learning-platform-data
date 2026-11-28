# `HttpHandlers.handleOrElse()`: phối hợp điều kiện request với file handler và handler tùy biến

> **Chương:** API SimpleFileServer  
> **Module học:** JAVA_VERSION_JAVA18 — `HttpHandlers` và `SimpleFileServer` được bổ sung từ Java 18; các API này vẫn được hỗ trợ trên JDK hiện đại.  
> **Mục tiêu:** Dùng `Predicate<Request>` để chọn một handler tùy biến khi điều kiện đúng và chuyển các request còn lại cho file handler hoặc handler dự phòng.

## 1. Bài toán: một context có thể cần nhiều cách xử lý

Một file handler của `SimpleFileServer` phục vụ nội dung tĩnh rất tiện, nhưng nó chỉ hỗ trợ hai phương thức HTTP:

- `GET`: đọc tệp hoặc xem directory listing.
- `HEAD`: lấy headers tương ứng mà không gửi response body.

Các method khác như `POST`, `PUT` hoặc `OPTIONS` nhận `405 Method Not Allowed`. Trong một ứng dụng thử nghiệm, ta có thể muốn giữ file handler cho phần lớn request, đồng thời xử lý riêng một số request bằng handler tự viết.

Ví dụ:

| Request | Cách xử lý mong muốn |
| --- | --- |
| `GET /hello.txt` | File handler trả nội dung tệp. |
| `HEAD /hello.txt` | File handler trả headers. |
| `OPTIONS /hello.txt` | Handler tùy biến trả `204` và header `Allow`. |
| `POST /hello.txt` | File handler dự phòng trả `405`. |

Nếu tự viết một `HttpHandler` lớn với nhiều nhánh `if/else`, code có thể nhanh chóng khó đọc. Từ Java 18, `HttpHandlers.handleOrElse(...)` cung cấp cách ghép một handler theo điều kiện với một handler dự phòng.

## 2. Hợp đồng của `HttpHandlers.handleOrElse()`

Chữ ký:

```java
public static HttpHandler handleOrElse(
        Predicate<Request> handlerTest,
        HttpHandler handler,
        HttpHandler fallbackHandler)
```

Phương thức trả về một `HttpHandler` mới có hành vi giống cấu trúc `if/else`:

```java
if (handlerTest.test(request)) {
    handler.handle(exchange);
} else {
    fallbackHandler.handle(exchange);
}
```

Đây là cách mô tả logic để hiểu API; ứng dụng không cần tự viết đoạn mã giả này.

| Tham số | Kiểu | Trách nhiệm |
| --- | --- | --- |
| `handlerTest` | `Predicate<Request>` | Kiểm tra metadata của request và trả `true` hoặc `false`. |
| `handler` | `HttpHandler` | Xử lý exchange khi predicate trả `true`. |
| `fallbackHandler` | `HttpHandler` | Xử lý mọi exchange còn lại khi predicate trả `false`. |
| **Kết quả** | `HttpHandler` | Handler tổng hợp, có thể đăng ký vào `HttpContext` như handler thông thường. |

Nếu bất kỳ đối số nào là `null`, factory ném `NullPointerException`.

Trong ứng dụng dùng named module, khai báo module HTTP server:

```java
module demo.http {
    requires jdk.httpserver;
}
```

**Điểm quan trọng:** fallback không có nghĩa là error handler. Fallback chỉ là nhánh được gọi khi predicate trả `false`. Nó có thể là file handler, handler trả `404`, handler trả `405`, hoặc một handler nghiệp vụ khác. Kết quả HTTP cuối cùng do handler được chọn quyết định.

## 3. Predicate nhận `Request`, không phải `HttpExchange`

`Request` là interface biểu diễn một **view bất biến của trạng thái request**. Các thông tin chính có thể dùng trong predicate:

| Phương thức | Dữ liệu |
| --- | --- |
| `getRequestMethod()` | HTTP method như `GET`, `HEAD`, `OPTIONS`. |
| `getRequestURI()` | URI của request; có thể lấy path bằng `getPath()`. |
| `getRequestHeaders()` | Headers request ở dạng chỉ đọc. |

Các key trong `Headers` không phân biệt chữ hoa/chữ thường. Nếu một header xuất hiện nhiều lần, danh sách giá trị giữ các giá trị nhận được theo thứ tự.

Predicate chỉ nhận `Request`; nó không nhận `HttpExchange` và không có API đọc request body. Khi cần đọc body, hãy để predicate chọn một handler rồi đọc body bên trong handler đó qua `exchange.getRequestBody()`.

Ví dụ predicate kiểm tra method:

```java
Predicate<Request> isGet =
        request -> request.getRequestMethod().equals("GET");
```

Kiểm tra method và path cùng lúc:

```java
Predicate<Request> isHealthGet = request ->
        request.getRequestMethod().equals("GET")
                && request.getRequestURI().getPath().equals("/health");
```

Kiểm tra header:

```java
Predicate<Request> wantsDigest = request ->
        request.getRequestHeaders().containsKey("Want-Digest");
```

Nên giữ predicate ngắn, dễ kiểm tra và chỉ đọc metadata. Không thực hiện nghiệp vụ ghi dữ liệu hoặc tiêu thụ request body trong predicate.

## 4. Ví dụ hoàn chỉnh: xử lý OPTIONS riêng, file handler làm fallback

Ví dụ này tạo một file server tùy chỉnh:

- `GET` và `HEAD` đi qua file handler.
- `OPTIONS /hello.txt` được xử lý bởi handler tùy biến.
- Các method khác như `POST` rơi vào file handler và nhận `405`.
- `OPTIONS` trên đường dẫn khác không thỏa predicate nên cũng đi qua file handler.

Chuẩn bị thư mục `public` và file `public/hello.txt`. Lưu mã thành `ConditionalFileServer.java`:

```java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandlers;
import com.sun.net.httpserver.SimpleFileServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class ConditionalFileServer {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("public").toAbsolutePath().normalize();
        if (!Files.isDirectory(root) || !Files.isReadable(root)) {
            throw new IllegalArgumentException(
                    "Thư mục public không tồn tại hoặc không đọc được: " + root);
        }

        // Handler mặc định phục vụ tệp và directory listing.
        HttpHandler fileHandler = SimpleFileServer.createFileHandler(root);

        // Handler tùy biến cho OPTIONS /hello.txt.
        Headers optionsHeaders = new Headers();
        optionsHeaders.set("Allow", "GET, HEAD, OPTIONS");
        HttpHandler optionsHandler =
                HttpHandlers.of(204, optionsHeaders, "");

        // Predicate chỉ chọn OPTIONS cho đúng resource hello.txt.
        HttpHandler combined = HttpHandlers.handleOrElse(
                request ->
                        request.getRequestMethod().equals("OPTIONS")
                                && request.getRequestURI().getPath()
                                        .equals("/hello.txt"),
                optionsHandler,
                fileHandler);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", combined);

        server.start();
        try {
            int port = server.getAddress().getPort();
            System.out.println("File server: http://127.0.0.1:" + port + "/");
            System.out.println("Nhấn Enter để dừng...");
            System.in.read();
        } finally {
            server.stop(1);
        }
    }
}
```

Biên dịch và chạy bằng JDK 18 trở lên:

```bash
javac ConditionalFileServer.java
java ConditionalFileServer
```

Thay `<port>` bằng cổng được chương trình in ra:

```bash
curl -i http://127.0.0.1:<port>/hello.txt
curl -I http://127.0.0.1:<port>/hello.txt
curl -i -X OPTIONS http://127.0.0.1:<port>/hello.txt
curl -i -X POST http://127.0.0.1:<port>/hello.txt
curl -i -X OPTIONS http://127.0.0.1:<port>/missing.txt
```

Kết quả dự kiến:

| Request | Predicate | Handler được chọn | Kết quả |
| --- | --- | --- | --- |
| `GET /hello.txt` | `false` | File handler | `200` nếu file tồn tại. |
| `HEAD /hello.txt` | `false` | File handler | Headers, không có body. |
| `OPTIONS /hello.txt` | `true` | Options handler | `204`, header `Allow: GET, HEAD, OPTIONS`. |
| `POST /hello.txt` | `false` | File handler | `405 Method Not Allowed`. |
| `OPTIONS /missing.txt` | `false` | File handler | `405 Method Not Allowed`. |

Ví dụ cho thấy `handleOrElse` không tự quyết định status code. Request `POST` nhận `405` vì fallback là file handler, và file handler chỉ hỗ trợ `GET`/`HEAD`. Nếu thay fallback bằng handler khác, kết quả sẽ thay đổi theo handler đó.

Nhấn Enter ở terminal Java để gọi `server.stop(1)`.

## 5. Dùng `HttpHandlers.of()` để tạo handler phản hồi tĩnh

`HttpHandlers` còn có factory method:

```java
public static HttpHandler of(
        int statusCode,
        Headers headers,
        String body)
```

Phương thức này tạo một handler trả về status, headers và body cố định. Body dạng `String` được mã hóa UTF-8. Nếu body rỗng, không gửi response body; độ dài được truyền là `-1`.

Ví dụ handler trả lỗi 405:

```java
Headers allowGet = new Headers();
allowGet.set("Allow", "GET");

HttpHandler notAllowed =
        HttpHandlers.of(405, allowGet, "Method Not Allowed");
```

Khi kết hợp với file handler:

```java
Predicate<Request> isGet =
        request -> request.getRequestMethod().equals("GET");

HttpHandler getOrNotAllowed = HttpHandlers.handleOrElse(
        isGet,
        fileHandler,
        notAllowed);
```

Ở đây chỉ request `GET` được chuyển tới file handler; `HEAD` cũng bị predicate từ chối và nhận 405 từ fallback. Đây là khác biệt so với file handler gốc vốn hỗ trợ cả `GET` và `HEAD`. Nếu muốn giữ cả hai method:

```java
Predicate<Request> isReadMethod = request -> {
    String method = request.getRequestMethod();
    return method.equals("GET") || method.equals("HEAD");
};
```

`HttpHandlers.of` đọc và loại bỏ request body trước khi gửi response. Điều này phù hợp với handler phản hồi tĩnh, nhưng nếu cần xử lý dữ liệu body, hãy viết handler tùy biến để đọc và xác thực body trước.

Factory `of` ném `IllegalArgumentException` nếu status code không phải số nguyên dương có ba chữ số theo hợp đồng API; ném `NullPointerException` nếu headers hoặc body là null.

## 6. Kết hợp nhiều điều kiện bằng Predicate

Vì `handlerTest` là `Predicate<Request>`, có thể dùng các phép kết hợp chuẩn của `Predicate`:

- `and(other)`: cả hai điều kiện phải đúng.
- `or(other)`: ít nhất một điều kiện đúng.
- `negate()`: đảo kết quả điều kiện.

Ví dụ chọn request GET có header `Want-Digest`:

```java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpHandlers;
import com.sun.net.httpserver.Request;
import java.util.function.Predicate;

Predicate<Request> isGet =
        request -> request.getRequestMethod().equals("GET");

Predicate<Request> wantsDigest =
        request -> request.getRequestHeaders().containsKey("Want-Digest");

Predicate<Request> isGetWithDigest = isGet.and(wantsDigest);
```

Sau đó dùng predicate tổng hợp:

```java
Headers digestHeaders = new Headers();
digestHeaders.set("Content-Type", "text/plain; charset=utf-8");
HttpHandler digestHandler =
        HttpHandlers.of(200, digestHeaders, "Digest response");
HttpHandler fallback = fileHandler;

HttpHandler combined = HttpHandlers.handleOrElse(
        isGetWithDigest,
        digestHandler,
        fallback);
```

Chỉ request thỏa đồng thời hai điều kiện mới vào `digestHandler`. GET không có header, POST có header hoặc request khác đều đi vào fallback.

### Ghép lồng nhiều handler

Javadoc minh họa cách lồng nhiều `handleOrElse`:

```java
HttpHandler h1 = fileHandler;
HttpHandler getHandler =
        HttpHandlers.of(200, new Headers(), "GET response");

HttpHandler h2 = HttpHandlers.handleOrElse(
        isGet,
        getHandler,
        h1);

HttpHandler h3 = HttpHandlers.handleOrElse(
        wantsDigest.and(isGet),
        digestHandler,
        h2);
```

Thứ tự thực thi:

1. `h3` kiểm tra `wantsDigest.and(isGet)`; nếu đúng, gọi `digestHandler`.
2. Nếu sai, `h3` chuyển sang `h2`.
3. `h2` kiểm tra `isGet`; nếu đúng, gọi `getHandler`.
4. Nếu sai, `h2` chuyển sang `h1`, tức file handler.

Do đó, request GET có `Want-Digest` được ưu tiên cho digest handler; GET không có header đi vào get handler; các method còn lại được file handler xử lý. Đây là cách xây dựng chuỗi điều kiện mà không cần viết một handler khổng lồ với nhiều nhánh lồng nhau.

## 7. Phân biệt HttpContext routing với handleOrElse

Hai cơ chế này hoạt động ở hai tầng khác nhau:

| Cơ chế | Câu hỏi được giải quyết | Đầu vào |
| --- | --- | --- |
| `HttpServer` / `HttpContext` | Request thuộc context/route nào? | URI path của request. |
| `HttpHandlers.handleOrElse` | Trong handler của context đã chọn, gọi handler nào? | Predicate nhận `Request` metadata. |

Luồng xử lý:

```text
HTTP request
     |
     v
HttpServer chọn HttpContext theo URI path
     |
     v
Filter chain của context
     |
     v
Composite HttpHandler từ handleOrElse
     |
     +---- predicate true ----> handler
     |
     +---- predicate false ---> fallbackHandler
     |
     v
HTTP response
```

Nếu request không khớp context nào, handler tổng hợp không được gọi. Vì vậy, `fallbackHandler` không phải route fallback toàn server và cũng không tự bắt mọi lỗi 404. Nó chỉ là nhánh `else` bên trong một HttpHandler đã được gọi.

## 8. Những lỗi thiết kế thường gặp

| Cách làm sai | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Nghĩ predicate nhận `HttpExchange` | API khai báo `Predicate<Request>`; predicate chỉ nhận view metadata. | Dùng `getRequestMethod()`, `getRequestURI()`, `getRequestHeaders()`. |
| Nghĩ fallback tự trả 404 | Fallback là một HttpHandler tùy ý, không phải cơ chế lỗi mặc định. | Chọn rõ file handler hoặc handler trả status cần thiết. |
| Dùng predicate chỉ kiểm tra method nhưng muốn route theo path | Mọi request trong context thỏa method đều vào nhánh true. | Kiểm tra cả `getRequestURI().getPath()` khi cần. |
| Dùng file handler làm fallback nhưng mong POST được lưu tệp | File handler chỉ hỗ trợ GET/HEAD. | Viết handler POST/PUT riêng với validation và quyền ghi. |
| Quên method HEAD khi tạo predicate GET-only | HEAD bị chuyển sang fallback dù file handler gốc hỗ trợ HEAD. | Kiểm tra cả GET và HEAD nếu muốn giữ hành vi đọc tệp. |
| Đọc request body trong predicate | Request không cung cấp API đọc body. | Chuyển việc đọc body vào HttpHandler được chọn. |
| Truyền null vào một trong ba tham số | Factory không chấp nhận đối số null. | Tạo predicate, handler và fallback hợp lệ. |
| Lồng quá nhiều điều kiện khó đọc | Thứ tự nhánh trở nên khó theo dõi. | Tách predicate có tên, viết handler riêng và kiểm thử từng nhánh. |

## 9. Nguyên tắc sử dụng trong ứng dụng thực tế

1. **Đặt predicate theo yêu cầu nghiệp vụ cụ thể:** kết hợp method, path và header khi cần, không chỉ kiểm tra một thuộc tính nếu route cần nhiều điều kiện.
2. **Giữ predicate nhẹ:** chỉ đọc metadata bất biến; không đọc body, ghi file hoặc thực hiện side effect.
3. **Chọn fallback có chủ đích:** file handler phù hợp cho tài nguyên tĩnh; handler 405 phù hợp khi chỉ cho phép một số method; handler tùy biến phù hợp khi cần API riêng.
4. **Nhớ rằng context được chọn trước:** đăng ký route/context đúng ở tầng HttpServer, sau đó mới composition handler.
5. **Giữ GET và HEAD đúng ý định:** nếu thay file handler bằng predicate GET-only, HEAD sẽ không còn đi vào file handler.
6. **Không nhầm dispatch với authorization:** predicate chọn handler không tự xác thực người dùng hoặc cấp quyền truy cập tài nguyên.
7. **Kiểm thử cả hai nhánh:** test predicate true, false, method không hỗ trợ, path không khớp và header thiếu/thừa.

## 10. Câu hỏi tự kiểm tra

1. `HttpHandlers.handleOrElse` trả về kiểu gì?
2. Ba tham số của `handleOrElse` có vai trò gì?
3. Khi predicate trả false, handler nào được gọi?
4. Vì sao fallback handler không đồng nghĩa với error handler?
5. `Request` cung cấp những metadata nào cho predicate?
6. Vì sao predicate không thể đọc request body?
7. Nếu fallback là `SimpleFileServer.createFileHandler(root)`, POST nhận kết quả gì?
8. Vì sao predicate chỉ kiểm tra GET sẽ làm HEAD không vào file handler?
9. Khác biệt giữa context routing và handleOrElse là gì?
10. Khi nào nên dùng `HttpHandlers.of` thay vì viết HttpHandler thủ công?

**Bài thực hành:** chạy `ConditionalFileServer`, gửi GET, HEAD, OPTIONS, POST đến `/hello.txt` và OPTIONS đến `/missing.txt`. Quan sát predicate đúng/sai và handler được gọi. Tiếp theo thay predicate thành GET-or-HEAD và fallback thành `HttpHandlers.of(405, ...)`; xác nhận HEAD vẫn vào file handler. Cuối cùng tạo predicate kết hợp method và header `Want-Digest`, lồng hai `handleOrElse` để quan sát thứ tự ưu tiên.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `HttpHandlers`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandlers.html): chữ ký, điều kiện true/false, nested composition, `of` và ngoại lệ.
- [Oracle JDK 27 — `Request`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/Request.html): request state bất biến, method, URI, headers và `with`.
- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): file handler, GET/HEAD và cách kết hợp handler khác.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): context selection và gắn handler.
- [Oracle JDK 18 — `HttpHandlers`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandlers.html): API được giới thiệu từ Java 18.
