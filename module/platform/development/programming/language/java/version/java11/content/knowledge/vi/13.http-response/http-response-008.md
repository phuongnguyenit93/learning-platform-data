# Java 11 — BodyHandler tùy biến theo status, header

**Chủ đề:** Java 11 → HTTP Response. Bài học hướng dẫn sử dụng `HttpResponse.BodyHandler<T>` để quyết định **cách nhận và xử lý response body** dựa vào HTTP status và headers *trước khi tải nội dung*, sau đó tạo `HttpResponse.BodySubscriber<T>` phù hợp. Trọng tâm là thiết kế đúng luồng dữ liệu, phân loại lỗi, kiểm soát RAM/tài nguyên và xây test HTTP cục bộ đáng tin cậy. Chỉ dùng các API chuẩn có trên JDK 11 và những thực hành vẫn còn áp dụng hiện nay; không dùng HTTP Client incubator cũ hoặc cú pháp Java mới hơn không tương thích Java 11.

**Mục tiêu học:** Người học phân biệt `BodyHandler` với `BodySubscriber` và `BodyPublisher`, dùng `ResponseInfo.statusCode()` / `headers()` / `version()`, rẽ nhánh text–binary–no-content–HTTP-error, trả một kiểu kết quả thống nhất, tránh đọc body nguy hiểm, hiểu khi nào cần streaming và kiểm thử được các lựa chọn đó.

## 1. Tại sao cần BodyHandler tùy biến?

Cách đơn giản nhất để gọi Java 11 HTTP Client là:

~~~java
HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Đây là **đoạn minh họa**: `client` là `HttpClient`, `request` là `HttpRequest`, cần import `java.net.http.HttpResponse`, `java.nio.charset.StandardCharsets` và xử lý `IOException` / `InterruptedException`.

`BodyHandlers.ofString(UTF_8)` **luôn cố đọc body thành String**, dù server trả `200 text/plain`, `404 application/json` hay `200 application/octet-stream`. Điều này có thể không phù hợp khi một endpoint có nhiều kiểu phản hồi: tải file thành công nhưng trả JSON lỗi; nhận text khi thành công nhưng trả binary cho ảnh; không muốn lưu nội dung của response ngoài dự kiến.

**Tình huống thực tế:**

- Với `2xx` và `Content-Type: text/plain`, giải mã thành text.
- Với `2xx` và `Content-Type: application/octet-stream`, nhận byte hoặc lưu file mà không chuyển qua String.
- Với `4xx/5xx`, đọc lỗi nhỏ để phân loại, nhưng không đưa body lỗi vào nhánh xử lý dữ liệu thành công.
- Với `204 No Content`, trả trạng thái “không có nội dung” mà không cố parse JSON/bytes.
- Với MIME type ngoài allowlist, **loại bỏ body an toàn** thay vì tự tải nội dung lớn hoặc giải mã sai.
- Với file tải xuống rất lớn, chỉ ghi file khi status/header hợp lệ; tránh `ofByteArray()` vì nó tích lũy toàn bộ bytes trong RAM.

`BodyHandler` giúp chọn **chiến lược xử lý body sớm**. Nó không thay thế validation, authorization, JSON parser, retry policy hay phân loại lỗi HTTP ở tầng nghiệp vụ.

## 2. Vòng đời Java 11: header trước, body sau

Luồng xử lý:

~~~text
HttpRequest → HttpClient.send()/sendAsync()
                        |
                 Nhận status + headers
                        |
          Gọi BodyHandler.apply(ResponseInfo)
                        |
                 Chọn BodySubscriber<T>
               /          |           \
           ofString     ofByteArray   replacing/stream
               \          |           /
                  Nhận body bytes
                        |
                BodySubscriber hoàn tất
                        |
                   HttpResponse<T>
         statusCode(), headers(), version(), body()
~~~

**Điều gì đến trước?** Java 11 gọi `BodyHandler.apply(info)` khi đã có thông tin status và headers nhưng **trước khi body bytes được nhận để xử lý**. Trong `apply` có thể đọc metadata, lựa chọn subscriber rồi trả về ngay. Java HTTP Client dùng subscriber để tiêu thụ nội dung theo giao thức `Flow`.

Bảng phân vai:

| Thành phần | Thuộc phía nào? | Chức năng |
| --- | --- | --- |
| `HttpRequest.BodyPublisher` | **Request** | Phát byte body gửi **lên server**. |
| `HttpResponse.BodyHandler<T>` | **Response** | Chọn cách xử lý response từ **status + headers**. |
| `HttpResponse.ResponseInfo` | **Response metadata sớm** | Cung cấp `statusCode()`, `headers()`, `version()` trước lúc xử lý body. |
| `HttpResponse.BodySubscriber<T>` | **Response** | Tiêu thụ bytes và tạo giá trị kiểu `T` cho `response.body()`. |
| `HttpResponse<T>` | **Response kết quả** | Chứa status, headers, URI, version và body kết quả; không tự suy đoán “2xx mới thành công”. |

**Không phải một cơ chế “đọc vài byte rồi quyết định”**: `ResponseInfo` chưa chứa body bytes. Nếu muốn lựa chọn sau khi xem vài byte, cần tự thiết kế subscriber/decoder streaming có buffer và state, thay vì mong `BodyHandler` phân tích được body trước khi nó đến.

## 3. Chữ ký API và ba nguồn thông tin

Java 11 định nghĩa `BodyHandler<T>` là functional interface:

~~~java
@FunctionalInterface
public interface BodyHandler<T> {
    HttpResponse.BodySubscriber<T> apply(
        HttpResponse.ResponseInfo responseInfo);
}
~~~

Đây là **chữ ký rút gọn để giải thích**, không phải mã cần tự khai báo trong dự án. Có thể cài bằng lambda:

~~~java
HttpResponse.BodyHandler<String> handler = info -> {
    if (info.statusCode() == 204) {
        return HttpResponse.BodySubscribers.replacing("");
    }
    return HttpResponse.BodySubscribers.ofString(
        StandardCharsets.UTF_8);
};
~~~

Đây là **đoạn minh họa**, cần import `HttpResponse` và `StandardCharsets`. Hai nhánh cùng trả `BodySubscriber<String>`, nên generic `BodyHandler<String>` hợp lệ. `replacing("")` bỏ bytes body (nếu có) và trả giá trị thay thế; nó không phải “dừng HTTP request trước khi tải header” hay bảo đảm không có traffic nào tới máy.

Thông tin có trong `ResponseInfo`:

| Phương thức | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `info.statusCode()` | `int` | Mã HTTP response, ví dụ 200, 204, 404, 503. |
| `info.headers()` | `HttpHeaders` | Headers của response; có `firstValue`, `allValues`, `map`. |
| `info.version()` | `HttpClient.Version` | HTTP/1.1 hoặc HTTP/2 **thực tế** của response. |

Cùng các dữ liệu trên vẫn có thể đọc từ `HttpResponse` sau khi nhận; sự khác biệt của `BodyHandler` là **ra quyết định sớm** để không phải tải mọi response theo cùng cách.

### 3.1. Đọc header không phân biệt hoa/thường

~~~java
String contentType = info.headers()
    .firstValue("Content-Type")
    .orElse("");
~~~

`HttpHeaders.firstValue(name)` không phân biệt hoa/thường ở tên header. Giá trị trả về là `Optional<String>` vì header có thể không tồn tại. Nếu server gửi nhiều giá trị, `firstValue` chỉ lấy **giá trị đầu**. Một ứng dụng có chính sách bảo mật nghiêm ngặt có thể cần phát hiện nhiều header mâu thuẫn thay vì tự chọn đầu tiên.

**Không dùng `headerValue.equals("application/json")` mà bỏ qua tham số**: header thực tế có thể là `application/json; charset=utf-8`. Để định tuyến theo *media type*, tách phần trước dấu `;`, trim và so sánh không phân biệt hoa/thường trong ngữ cảnh tên media type:

~~~java
String mime = contentType.split(";", 2)[0]
    .trim().toLowerCase(Locale.ROOT);
~~~

Đây chỉ là **cách đơn giản cho danh sách MIME cố định và header hợp lệ**; nếu cần phân tích đầy đủ tham số (chuỗi được quote, nhiều giá trị, charset, boundary), dùng parser phù hợp và kiểm tra ngữ nghĩa. Dữ liệu header đến từ server/đường trung gian **không mặc nhiên đáng tin**.

## 4. Status HTTP không phải exception Java

Các status phổ biến:

| HTTP status | Body có thể xuất hiện? | Chiến lược thường gặp |
| --- | --- | --- |
| `200 OK` | Có thể có text, JSON, binary | Dựa vào media type + hợp đồng để chọn subscriber. |
| `201 Created` | Có thể có thông tin tài nguyên mới | Kiểm tra schema/hợp đồng; không tự giả định text. |
| `202 Accepted` | Có thể có metadata công việc | Phân loại accepted, không nhầm là đã hoàn tất nghiệp vụ. |
| `204 No Content` | Không có body theo HTTP semantics | Trả giá trị trạng thái không có nội dung, không parse. |
| `206 Partial Content` | Có thể là một đoạn dữ liệu có range | Chỉ ghép/ghi khi đã kiểm tra `Content-Range`, range mong đợi và format. |
| `301/302/307/308` | Redirect, có thể có body | Theo redirect policy, không lẫn body redirect với dữ liệu đích. |
| `400/422` | Thường có thông tin validation | Đọc lỗi nhỏ theo schema, không xử lý như success. |
| `401/403` | Authentication/authorization | Xử lý quyền, tránh log credential/body nhạy cảm. |
| `404` | Không tìm thấy | Có thể đọc thông điệp lỗi, hoặc bỏ qua nếu không cần. |
| `429/500/503` | Có thể có lỗi tạm thời | Kiểm tra `Retry-After`/chính sách retry, không retry vô hạn. |

`HttpClient.send(...)` **không tự ném `IOException` chỉ vì server trả `404` hoặc `500`**. Một response HTTP lỗi vẫn là response, có status và headers để handler chọn subscriber. Ngoại lệ Java thường phản ánh lỗi kết nối, TLS, timeout, I/O hoặc lỗi trong quá trình xử lý body.

`BodyHandler` không nên im lặng biến `404` thành `200`. Bạn có thể **bỏ body**, nhưng `response.statusCode()` vẫn giữ status thật. Nếu dùng `BodySubscribers.replacing` để trả một giá trị mặc định, đừng nhầm giá trị đó với dữ liệu thành công của server.

## 5. BodySubscribers được cung cấp trên Java 11

`HttpResponse.BodySubscribers` gồm các factory chuẩn, phù hợp để return từ lambda `BodyHandler`.

| Factory | Kiểu trả về | Tác dụng và lưu ý |
| --- | --- | --- |
| `BodySubscribers.ofString(charset)` | `BodySubscriber<String>` | Decode response thành String; chọn charset có hợp đồng. |
| `BodySubscribers.ofByteArray()` | `BodySubscriber<byte[]>` | Gom body vào RAM; chỉ an toàn khi có giới hạn dung lượng. |
| `BodySubscribers.ofFile(path)` | `BodySubscriber<Path>` | Ghi bytes xuống file; phải kiểm soát path, quyền và khi nào được ghi. |
| `BodySubscribers.discarding()` | `BodySubscriber<Void>` | Tiêu thụ và bỏ body, không giữ nội dung. |
| `BodySubscribers.replacing(value)` | `BodySubscriber<T>` | Bỏ body và trả giá trị thay thế có kiểu `T`. |
| `BodySubscribers.mapping(downstream, mapper)` | `BodySubscriber<U>` | Chuyển kết quả của subscriber khác sang kiểu miền dữ liệu mong muốn. |
| `BodySubscribers.ofInputStream()` | `BodySubscriber<InputStream>` | Cho phép đọc body theo stream; caller phải đọc/đóng đúng vòng đời. |
| `BodySubscribers.ofPublisher()` | `BodySubscriber<Flow.Publisher<List<ByteBuffer>>>` | Chuyển body thành publisher, cần subscribe và xử lý backpressure/cancel đúng. |
| `BodySubscribers.fromSubscriber(...)` | Generic theo subscriber/finisher | Tích hợp subscriber tùy biến với Flow; dùng khi có yêu cầu streaming đặc biệt. |

**Điều rất quan trọng về generic:** Một `BodyHandler<T>` phải trả `BodySubscriber<T>` ở **mọi nhánh**. Không thể đơn giản:

~~~java
HttpResponse.BodyHandler<Object> wrong = info -> {
    if (info.statusCode() == 200) {
        return HttpResponse.BodySubscribers.ofString(
            StandardCharsets.UTF_8);
    }
    return HttpResponse.BodySubscribers.ofByteArray();
};
~~~

Đây là **đoạn cố tình sai kiểu Java**: `BodySubscriber<String>` và `BodySubscriber<byte[]>` không phải `BodySubscriber<Object>` do generic invariance. Đừng copy nguyên đoạn này vào chương trình. Cách đúng là **chọn một kiểu kết quả duy nhất** và bọc kết quả các subscriber bằng `BodySubscribers.mapping(...)`, hoặc sử dụng một kiểu phù hợp chung như `Path`/`String` theo hợp đồng.

## 6. Thiết kế một kiểu domain cho nhiều dạng body

Nếu endpoint có nhiều loại response, tạo một kiểu mô tả **cách diễn giải body** chứ không ép tất cả thành String. Trên Java 11, dùng class thông thường:

~~~java
final class DecodedBody {
    final String kind;
    final String content;

    DecodedBody(String kind, String content) {
        this.kind = kind;
        this.content = content;
    }
}
~~~

Đây là **định nghĩa kiểu minh họa**. Với ứng dụng thật, nên dùng enum thay vì string cho `kind`, bổ sung validation và phân biệt payload dữ liệu với thông tin chẩn đoán. Dùng `record` hoặc sealed types chỉ khi target JDK phù hợp; **không dùng record trong source cần compile Java 11**.

Những nhánh xử lý có thể cùng trả `BodySubscriber<DecodedBody>` bằng mapping:

~~~java
HttpResponse.BodySubscriber<DecodedBody> text =
    HttpResponse.BodySubscribers.mapping(
        HttpResponse.BodySubscribers.ofString(
            StandardCharsets.UTF_8),
        value -> new DecodedBody("TEXT", value));

HttpResponse.BodySubscriber<DecodedBody> binary =
    HttpResponse.BodySubscribers.mapping(
        HttpResponse.BodySubscribers.ofByteArray(),
        bytes -> new DecodedBody(
            "BINARY", java.util.Arrays.toString(bytes)));

HttpResponse.BodySubscriber<DecodedBody> ignored =
    HttpResponse.BodySubscribers.replacing(
        new DecodedBody("IGNORED", "-"));
~~~

Đây là **đoạn minh họa**, `DecodedBody` đã có; cần import `HttpResponse` và `StandardCharsets`. Các nhánh trả **cùng kiểu generic**, vì vậy có thể dùng trong một `BodyHandler<DecodedBody>`. Ở đây `Arrays.toString(bytes)` chỉ để hiển thị minh họa; ứng dụng thực sự nhận binary thường nên giữ `byte[]` hoặc lưu file, không biến thành chuỗi dạng `[1, 2, 3]`.

## 7. Chương trình Java 11 hoàn chỉnh: phân nhánh theo status và Content-Type

Ví dụ sau **chạy offline** bằng HTTP server loopback của JDK, tạo 5 endpoint có status/header khác nhau:

- `/text`: 200 + `text/plain` → decode UTF-8 thành String.
- `/binary`: 200 + `application/octet-stream` → nhận byte[] rồi biểu diễn để kiểm tra.
- `/error`: 404 + `text/plain` → giữ thông điệp lỗi, không gắn nhãn success.
- `/empty`: 204 → không đọc nội dung, trả một trạng thái cố định.
- `/ignored`: 200 + `application/json` (không nằm trong allowlist demo) → discard, không cố parse.

Mục tiêu chính là **quyết định bằng status/header trước khi body đến**. Ví dụ này chọn đọc toàn bộ body cho hai dạng nội dung nhỏ; với dữ liệu lớn, xem mục streaming.

Lưu file **`ConditionalBodyHandlerDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class ConditionalBodyHandlerDemo {
    private ConditionalBodyHandlerDemo() {
    }

    static final class DecodedBody {
        final String kind;
        final String content;

        DecodedBody(String kind, String content) {
            this.kind = kind;
            this.content = content;
        }
    }

    static HttpResponse.BodyHandler<DecodedBody> handler() {
        return info -> {
            int status = info.statusCode();
            String contentType = info.headers()
                .firstValue("Content-Type").orElse("");
            String mime = contentType.split(";", 2)[0]
                .trim().toLowerCase(Locale.ROOT);

            if (status == 204) {
                return HttpResponse.BodySubscribers.replacing(
                    new DecodedBody("NO_CONTENT", "-"));
            }
            if (status >= 400) {
                if ("text/plain".equals(mime)) {
                    return HttpResponse.BodySubscribers.mapping(
                        HttpResponse.BodySubscribers.ofString(
                            StandardCharsets.UTF_8),
                        s -> new DecodedBody("HTTP_ERROR", s));
                }
                return HttpResponse.BodySubscribers.replacing(
                    new DecodedBody("ERROR_IGNORED", "-"));
            }
            if (status >= 200 && status < 300) {
                if ("text/plain".equals(mime)) {
                    return HttpResponse.BodySubscribers.mapping(
                        HttpResponse.BodySubscribers.ofString(
                            StandardCharsets.UTF_8),
                        s -> new DecodedBody("TEXT", s));
                }
                if ("application/octet-stream".equals(mime)) {
                    return HttpResponse.BodySubscribers.mapping(
                        HttpResponse.BodySubscribers.ofByteArray(),
                        bytes -> new DecodedBody(
                            "BINARY", Arrays.toString(bytes)));
                }
            }
            return HttpResponse.BodySubscribers.replacing(
                new DecodedBody("IGNORED", "-"));
        };
    }

    private static void respond(HttpExchange exchange, int status,
            String contentType, byte[] body) throws IOException {
        try {
            exchange.getResponseHeaders().set(
                "Content-Type", contentType);
            exchange.sendResponseHeaders(status, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/text", exchange -> respond(
            exchange, 200, "text/plain; charset=utf-8",
            "Xin chào".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/binary", exchange -> respond(
            exchange, 200, "application/octet-stream",
            new byte[] {1, 2, 3}));
        server.createContext("/error", exchange -> respond(
            exchange, 404, "text/plain; charset=utf-8",
            "không tìm thấy".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/ignored", exchange -> respond(
            exchange, 200, "application/json",
            "{\"ok\":true}".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/empty", exchange -> {
            try {
                exchange.sendResponseHeaders(204, -1);
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
            String base = "http://127.0.0.1:" +
                server.getAddress().getPort();

            for (String path : List.of(
                    "/text", "/binary", "/error",
                    "/empty", "/ignored")) {
                HttpRequest request = HttpRequest.newBuilder(
                        URI.create(base + path))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

                HttpResponse<DecodedBody> response = client.send(
                    request, handler());

                System.out.println(
                    path.substring(1) +
                    " status=" + response.statusCode() +
                    " kind=" + response.body().kind +
                    " data=" + response.body().content);
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 11 với file UTF-8, trên môi trường cho phép socket loopback:

~~~bash
javac -encoding UTF-8 --add-modules jdk.httpserver ConditionalBodyHandlerDemo.java
java --add-modules jdk.httpserver ConditionalBodyHandlerDemo
~~~

**Stdout chính xác trong điều kiện chạy bình thường:**

~~~text
text status=200 kind=TEXT data=Xin chào
binary status=200 kind=BINARY data=[1, 2, 3]
error status=404 kind=HTTP_ERROR data=không tìm thấy
empty status=204 kind=NO_CONTENT data=-
ignored status=200 kind=IGNORED data=-
~~~

**Giải thích những điểm quan trọng:**

1. `HttpServer` trong module `jdk.httpserver` là **server test HTTP/1.1 cục bộ**; không yêu cầu Internet hay thư viện khác. Port 0 để OS chọn cổng đang trống; không hard-code 8080.
2. `handler()` dùng `statusCode()` **trước**, rồi kiểm tra `Content-Type`. Nếu lỗi HTTP thì không đưa body vào nhánh thành công chỉ vì header là text/plain.
3. `mime` được chuẩn hóa bằng `Locale.ROOT`, và bỏ tham số như `charset=utf-8` để so sánh đúng media type. Ví dụ có chủ đích chỉ hỗ trợ UTF-8 cho text.
4. `BodySubscribers.mapping(ofString(UTF_8), ...)` chỉ xây object `DecodedBody` sau khi subscriber gốc đọc/giải mã text.
5. `BodySubscribers.mapping(ofByteArray(), ...)` nhận binary rồi biến thành định dạng dễ nhìn để kiểm chứng; production không nên chuyển binary lớn sang String để log.
6. `BodySubscribers.replacing(...)` **tiêu thụ và bỏ** nội dung; nhánh `/ignored` không parse `application/json` chỉ vì status 200.
7. `204` không có response body theo hợp đồng HTTP, nên handler không cố parse dữ liệu.
8. `client.send(...)` trả response cả với `404`; status và content là dữ liệu riêng, không được đánh đồng `404` với exception Java.
9. `Redirect.NEVER` ngăn việc tự động chuyển URL khiến demo bất ngờ nhận response từ endpoint khác.
10. `server.stop(0)` dừng server sau test; nếu hệ điều hành cấm mở socket loopback, demo có thể ném lỗi trước khi in đủ các dòng. Đây là giới hạn môi trường, không phải một kết quả stdout khác của mã thành công.

**Giới hạn của demo:** ứng dụng thực cần validate header, giới hạn kích thước body, phân biệt schema lỗi, bảo vệ dữ liệu nhạy cảm và xử lý lỗi I/O. Demo dùng `ofString`/`ofByteArray` vì payload nhỏ. Không sử dụng logic “nếu MIME không đúng thì tự đoán JSON/CSV” cho dữ liệu không tin cậy.

## 8. Chọn nhánh theo header khác ngoài Content-Type

Ngoài `Content-Type`, có nhiều header ảnh hưởng cách xử lý, nhưng **header chỉ là metadata**, không bảo đảm body đúng định dạng.

### 8.1. `Content-Length`

~~~java
long limit = 1024L * 1024L; // Chính sách: 1 MiB.
long declared = info.headers()
    .firstValueAsLong("Content-Length")
    .orElse(-1L);
if (declared > limit) {
    return HttpResponse.BodySubscribers.replacing(
        new DecodedBody("TOO_LARGE_DECLARED", "-"));
}
~~~

Đây là **đoạn minh họa đặt trong BodyHandler<DecodedBody>`**, không phải toàn chương trình; `DecodedBody` đã được định nghĩa. Header `Content-Length` có thể thiếu (chunked HTTP/1.1 hoặc HTTP/2), có thể bị parser từ chối nếu không hợp lệ, hoặc không phản ánh kích thước giải nén. **Đây chỉ là bước kiểm tra sớm**, không phải giới hạn bảo mật tuyệt đối. Phải áp dụng giới hạn **khi thực sự nhận byte** ở subscriber hoặc lớp streaming, và giới hạn dữ liệu **sau giải nén** khi áp dụng.

Với `firstValueAsLong`, nếu header có nhưng không parse được thành `long` có thể ném `NumberFormatException`. Nếu nhiều giá trị Content-Length hoặc giá trị âm/bất nhất, phải áp dụng chính sách HTTP và không tự tin rằng một giá trị đầu là hợp lệ.

### 8.2. `Content-Encoding`

`Content-Encoding: gzip` mô tả cách mã hóa **representation** của payload. Nó khác `Content-Type`: `application/json` vẫn có thể được gửi dưới dạng bytes nén gzip. Không dựa vào `Content-Type` rồi decode ngay bytes nén bằng UTF-8. Hệ thống cần một bước giải nén đúng, kiểm tra kích thước/CRC/giới hạn tài nguyên trước khi parse theo media type. Không mặc định mọi môi trường Java 11 HTTP Client tự giải mã mọi Content-Encoding.

Không tự chấp nhận các thuật toán nén không hỗ trợ hoặc những phản hồi có tỉ lệ giải nén bất thường; đặt giới hạn CPU, thời gian và số byte để chống **decompression bomb**.

### 8.3. `Content-Disposition` khi tải file

Header `Content-Disposition: attachment; filename=...` có thể dùng cho tải file, nhưng **filename là dữ liệu từ server**, không phải đường dẫn tin cậy. Tránh nối chuỗi tên file bất kỳ trực tiếp vào đường dẫn lưu. Chuẩn hóa, loại ký tự nguy hiểm, giới hạn thư mục đích, kiểm tra symlink/race và quyền ghi.

Java 11 có `BodyHandlers.ofFileDownload(directory, options...)` khi muốn filename từ response, nhưng ứng dụng vẫn phải thực hiện kiểm soát an toàn đường dẫn theo mô hình tin cậy; không nên dùng một header bên ngoài để quyết định nơi ghi file nhạy cảm.

### 8.4. `ETag`, `Last-Modified` và status `304`

Nếu cache/conditional request trả `304 Not Modified`, đó không phải body dữ liệu mới để parse. Client có thể dùng bản cache cũ do ứng dụng đã kiểm chứng và quản lý, thay vì tự diễn giải `304` như `200`. `BodyHandler` có thể chọn bỏ body, còn logic cache và tính đúng của validator nằm ở tầng cao hơn.

### 8.5. `Retry-After` với 429/503

Header `Retry-After` có thể là số giây hoặc HTTP-date tùy định dạng. Nó ảnh hưởng **quyết định retry**, không phải lý do để đọc mọi body vào RAM. Phải tôn trọng deadline/backoff và idempotency; không retry vô hạn hoặc gửi lại request có side effect mà không có chiến lược chống lặp.

## 9. Lựa chọn streaming và ghi file khi response lớn

Việc chọn đúng subscriber có thể tránh tích lũy file lớn trong bộ nhớ:

~~~java
HttpResponse.BodyHandler<Path> downloadHandler =
    info -> {
        if (info.statusCode() == 200 &&
                info.headers().firstValue("Content-Type")
                    .orElse("").startsWith(
                        "application/octet-stream")) {
            return HttpResponse.BodySubscribers.ofFile(destination);
        }
        return HttpResponse.BodySubscribers.replacing(
            Path.of("not-downloaded"));
    };
~~~

Đây là **đoạn minh họa** với `destination` là `Path` an toàn, đã được xác định bởi ứng dụng. Dạng `startsWith` ở đây chỉ để minh họa; trong production phải so sánh media type đã parse, tránh loại MIME có tiền tố giống nhưng không hợp lệ. `Path.of("not-downloaded")` là **sentinel minh họa**, không có file thật được tạo; không được suy nó là output download thành công. Mọi nhánh đều trả `BodySubscriber<Path>`.

### 9.1. Không ghi file khi status/header không đạt

Khi trả `BodySubscribers.ofFile`, việc ghi bắt đầu sau khi subscriber được chọn; **đừng tạo file đích rồi mới kiểm tra status** nếu mục tiêu là tránh rác từ response lỗi. Với download quan trọng, nên ghi vào đường dẫn tạm thuộc thư mục được phép, verify checksum/kích thước/schema, sau đó mới di chuyển sang đích theo quy tắc overwrite/atomic move đã thiết kế.

Nếu kết nối đứt giữa chừng, file có thể đã được ghi **một phần**. `BodyHandler` không tự mang lại transactional write. Dùng `try/finally` và cleanup phù hợp ở tầng điều phối, không coi `HttpResponse<Path>` xuất hiện đồng nghĩa dữ liệu đã được xác minh cryptographic integrity.

### 9.2. Với `ofInputStream()`

~~~java
HttpResponse.BodyHandler<InputStream> streaming =
    info -> info.statusCode() == 200
        ? HttpResponse.BodySubscribers.ofInputStream()
        : HttpResponse.BodySubscribers.replacing(
            InputStream.nullInputStream());
~~~

Đây là **đoạn minh họa**, cần import `java.io.InputStream` và `HttpResponse`. `InputStream.nullInputStream()` được giới thiệu trong Java 11. Với `ofInputStream()`, `HttpResponse` có thể được trả về **trước khi toàn bộ body bytes đến**; **caller phải đọc và đóng** `response.body()` bằng `try-with-resources`. Nếu không đọc/đóng stream, có thể giữ tài nguyên network và ảnh hưởng connection reuse.

Đọc streaming:

~~~java
try (InputStream in = response.body()) {
    byte[] chunk = new byte[8192];
    int count;
    long total = 0;
    while ((count = in.read(chunk)) != -1) {
        total += count;
        if (total > MAX_ALLOWED_BYTES) {
            throw new IOException("Response too large");
        }
        consume(chunk, 0, count);
    }
}
~~~

Đây là **đoạn minh họa**, `response` có kiểu `HttpResponse<InputStream>`, `MAX_ALLOWED_BYTES` và `consume` do ứng dụng khai báo. Khi input quá lớn, dừng đọc và đóng stream; không gọi `readAllBytes()` đối với payload chưa kiểm soát. Với output cần atomicity, đưa dữ liệu vào staging/transaction thay vì commit từng chunk rồi không thể rollback.

### 9.3. `BodyHandlers.buffering` không phải giới hạn kích thước

Java 11 có `BodyHandlers.buffering(handler, bufferSize)` để gom dữ liệu thành các nhóm có kích thước mục tiêu trước khi chuyển cho downstream subscriber. Nó **không** giới hạn tổng số byte response. Không dùng bufferSize=8192 rồi khẳng định download tối đa 8192 byte; `ofByteArray()` phía sau vẫn có thể tích lũy cả response cực lớn.

## 10. Mỗi nhánh phải có một kiểu kết quả nhất quán

Một số thiết kế phù hợp:

**Phương án A — dùng một kiểu domain duy nhất:** `BodyHandler<DecodedBody>`; mọi nhánh dùng `mapping` hoặc `replacing` để tạo `DecodedBody`. Đây là cách demo đã dùng.

**Phương án B — mọi nhánh tạo `String`:** status thành công đọc text, lỗi trả text lỗi hoặc một nhãn thay thế, body binary bị bỏ. Hợp lý nếu hợp đồng đầu ra luôn là text; không phù hợp nếu cần giữ byte nhị phân.

**Phương án C — mọi nhánh trả `Path`:** với endpoint download, response thành công lưu file, status lỗi trả trạng thái riêng. Nếu dùng `Path` giả như sentinel, phải kết hợp thêm status và không để caller tưởng đường dẫn đó là file tải thành công.

**Phương án D — chỉ dùng `BodyHandler<Void>`:** tất cả response body bị bỏ hoặc chuyển qua sink bên ngoài. Hợp cho endpoint chỉ cần status, nhưng không thích hợp khi ứng dụng cần phân tích JSON lỗi hoặc file trả về.

Nếu kết quả thật sự gồm nhiều dạng dữ liệu, ưu tiên một kiểu trả về rõ ràng:

~~~java
final class ApiPayload {
    enum Kind { TEXT, BINARY, EMPTY, ERROR, REJECTED }

    final Kind kind;
    final String text;
    final byte[] bytes;

    private ApiPayload(Kind kind, String text, byte[] bytes) {
        this.kind = kind;
        this.text = text;
        this.bytes = bytes == null ? null : bytes.clone();
    }

    static ApiPayload text(String s) {
        return new ApiPayload(Kind.TEXT, s, null);
    }

    static ApiPayload bytes(byte[] data) {
        return new ApiPayload(Kind.BINARY, null, data);
    }

    static ApiPayload empty() {
        return new ApiPayload(Kind.EMPTY, null, null);
    }
}
~~~

Đây là **định nghĩa class minh họa**, chưa có constructor/factory cho mọi `Kind`; trong dự án thật hoàn thiện bất biến, accessors phòng thủ và error handling. Có thể dùng `BodySubscribers.mapping(ofByteArray(), ApiPayload::bytes)` để giữ bytes mà không chuyển thành chuỗi. Nếu trả mảng ra từ getter, cân nhắc copy phòng thủ; đừng vô tình cho code ngoài sửa dữ liệu đã được xác thực.

Điểm chính là **generic T của BodyHandler thể hiện hợp đồng trả về**, không phải loại byte mà HTTP transport đang truyền.

## 11. Charset, JSON và vấn đề giải mã

### 11.1. `ofString()` và `ofString(charset)`

`BodyHandlers.ofString()` có thể chọn charset từ `Content-Type` theo quy tắc Java 11; khi header không chỉ định charset hỗ trợ, API dùng fallback UTF-8. `BodyHandlers.ofString(StandardCharsets.UTF_8)` hoặc `BodySubscribers.ofString(UTF_8)` dùng UTF-8 **tường minh**, bất kể server khai báo charset khác.

Với API JSON hiện đại, quy định codec/encoding theo **hợp đồng endpoint**, thường là UTF-8. Nếu server gửi charset không khớp mà bạn cố decode, có thể ra text sai. Một BodyHandler chỉ dựa vào tên MIME không thể tự sửa dữ liệu encoding hỏng; phải validate theo schema, byte encoding và nội dung.

### 11.2. Java SE 11 không có thư viện JSON parser tích hợp

`application/json` không có nghĩa có thể gọi `new JSONObject(response.body())` bằng Java SE 11 chuẩn mà không thêm dependency. Khi xử lý JSON thật, dùng thư viện parser được duy trì (chẳng hạn Jackson bản phù hợp với Java target) và kiểm soát size/depth/schema. `BodySubscribers.mapping(ofString(UTF_8), parser::parse)` có thể dùng về mặt cấu trúc, nhưng **nó vẫn tích lũy toàn bộ body String trước khi parse**; chỉ phù hợp khi có giới hạn kích thước.

### 11.3. Không tự đoán nội dung dựa vào vài byte khi header không đúng

Khi `Content-Type` thiếu/mâu thuẫn, giải pháp an toàn tùy hợp đồng có thể là **từ chối**, bỏ body hoặc lưu vào vùng kiểm định riêng. Sniffing dựa trên byte đầu có thể tạo rủi ro type confusion; không nên “cứ đọc như text xem được không” đối với dữ liệu từ nguồn không tin cậy.

## 12. Kiểm thử phân nhánh mà không phụ thuộc Internet

Chương trình hoàn chỉnh ở mục 7 đã là một integration fixture tại loopback. Test cần khẳng định **đúng cả status lẫn kiểu body**, vì chỉ test text success không chứng minh nhánh lỗi hoạt động.

Bảng test quan trọng:

| Tình huống | Status/Headers | Kết quả mong đợi |
| --- | --- | --- |
| Text thành công | 200 + `text/plain; charset=utf-8` | `DecodedBody.kind=TEXT`, nội dung UTF-8 đúng. |
| Binary thành công | 200 + `application/octet-stream` | `kind=BINARY`, bytes không bị decode như String. |
| Lỗi text | 404 + `text/plain` | `kind=HTTP_ERROR`, HTTP status vẫn 404. |
| Không có body | 204 | `kind=NO_CONTENT`, không parse nội dung. |
| MIME ngoài allowlist | 200 + `application/json` trong demo | `kind=IGNORED`, không trả nội dung JSON trong body. |
| Header thiếu | 200 + không có `Content-Type` | Chính sách rõ ràng, demo chọn IGNORED. |
| Status 5xx | 503 + `text/plain` | Nhánh HTTP_ERROR nếu được phép đọc lỗi. |
| Body rất lớn | 200 + media type hợp lệ | Giới hạn RAM/streaming, không chỉ tin Content-Length. |
| Disconnect giữa chừng | Headers đến nhưng body fail | Request xử lý lỗi I/O/partial file, không báo thành công. |
| Redirect | 302 rồi 200 khi policy follow | Nhánh phản hồi cuối theo response đã chọn, cần test policy. |

### 12.1. Unit test logic chọn subscriber với ResponseInfo giả

JDK 11 cho phép dựng `HttpHeaders.of(...)` để hỗ trợ test. Có thể tạo `ResponseInfo` giả để test *việc lựa chọn*, không cần socket:

~~~java
HttpResponse.ResponseInfo info = new HttpResponse.ResponseInfo() {
    public int statusCode() {
        return 204;
    }

    public java.net.http.HttpHeaders headers() {
        return java.net.http.HttpHeaders.of(
            java.util.Map.of(), (name, value) -> true);
    }

    public HttpClient.Version version() {
        return HttpClient.Version.HTTP_1_1;
    }
};

HttpResponse.BodySubscriber<ConditionalBodyHandlerDemo.DecodedBody> sub =
    ConditionalBodyHandlerDemo.handler().apply(info);
~~~

Đây là **đoạn minh họa**, cần import `HttpResponse` và `HttpClient`. Bạn có thể assert `sub` khác null; muốn kiểm tra object body mà subscriber tạo ra, phải đưa subscriber qua một Flow subscription hợp lệ và đợi completion, **không** đơn giản gọi `getBody().toCompletableFuture().join()` khi subscriber chưa được hoàn tất — dễ treo test.

Với logic phức tạp, tách riêng hàm phân loại status/MIME thành **pure function** và unit test trả về enum, còn integration test kiểm chứng subscriber thực nhận body và trả đúng kiểu.

### 12.2. Ví dụ JUnit Jupiter 5.x với HTTP fixture

Lớp sau cần JUnit Jupiter bản tương thích Java 11, module `jdk.httpserver` và Maven/Gradle test runner. Nó kiểm tra nhánh HTTP error của `ConditionalBodyHandlerDemo.handler()` bằng server cục bộ. Lưu `ConditionalBodyHandlerDemoTest.java` cùng package với demo:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ConditionalBodyHandlerDemoTest {
    @Test
    void errorStatusUsesErrorSubscriber() throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/missing", exchange -> {
            try {
                byte[] body = "not found".getBytes(
                    StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(404, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:" +
                server.getAddress().getPort() + "/missing");
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5)).GET().build();

            HttpResponse<ConditionalBodyHandlerDemo.DecodedBody> r =
                client.send(request,
                    ConditionalBodyHandlerDemo.handler());

            assertEquals(404, r.statusCode());
            assertEquals("HTTP_ERROR", r.body().kind);
            assertEquals("not found", r.body().content);
        } finally {
            server.stop(0);
        }
    }
}
~~~

Không cần Internet. **Đây là class test hoàn chỉnh khi nằm trong dự án đã khai báo JUnit Jupiter**, không tự compile bằng JDK 11 thuần nếu thiếu dependency. Trong bài Knowledge, không giả định test đã chạy trên CI; khi triển khai cần dùng test task của build tool và bảo đảm fixture dọn tài nguyên dù test fail.

## 13. Backpressure, concurrency và BodySubscriber tùy biến

`BodySubscriber<T>` triển khai `Flow.Subscriber<List<ByteBuffer>>` và công bố `CompletionStage<T> getBody()`. Mỗi lần `onNext` có thể mang nhiều `ByteBuffer`; không được giả định mỗi buffer là một HTTP/1.1 chunk hay HTTP/2 frame tương ứng.

Khi chọn subscriber chuẩn như `ofByteArray`, `ofString`, `ofFile`, JDK quản lý flow theo contract. Khi **tự viết** một `BodySubscriber`:

1. Xử lý `onSubscribe`, giữ `Flow.Subscription` và gọi `request(n)` theo nhu cầu; **không phát/lấy dữ liệu vượt demand**.
2. Từng `onNext(List<ByteBuffer>)` phải xử lý đúng `remaining()` của các buffer, không lấy `capacity()` làm số byte hợp lệ.
3. Tôn trọng `onError` và `onComplete`, hoàn tất `getBody()` theo đúng trạng thái.
4. Khi cancel, hủy subscription và đóng/hoàn trả tài nguyên; không phụ thuộc vào một thread callback cố định.
5. Không giả định body hoàn thành trước khi `HttpResponse` xuất hiện nếu subscriber trả về stream/publisher, trái với các handler tích lũy toàn bộ body.
6. Kiểm soát kích thước, thời gian và hành vi xử lý bất đồng bộ; mapping blocking CPU nặng hoặc I/O ngoài trong callback có thể ảnh hưởng throughput.
7. Không chia sẻ state mutable giữa các request nếu một `BodyHandler` object được dùng lại cho nhiều lần send.

**Ưu tiên tổ hợp các factory `BodySubscribers` trước khi tự viết Flow subscriber**. Custom subscriber đúng nghĩa hữu ích khi cần streaming parser, bounded accumulator hoặc xử lý trực tiếp vào sink có backpressure, nhưng đó là trách nhiệm khó hơn chọn một nhánh dựa vào header.

### 13.1. `BodySubscribers.mapping` hoạt động khi nào?

~~~java
HttpResponse.BodySubscriber<Integer> sizeSubscriber =
    HttpResponse.BodySubscribers.mapping(
        HttpResponse.BodySubscribers.ofByteArray(),
        bytes -> bytes.length);
~~~

Đây là **đoạn minh họa**. Kết quả body là số byte sau khi subscriber gốc đã tích lũy **toàn bộ** body. Nó không tiết kiệm RAM chỉ vì kiểu trả về cuối là `Integer`. Với file lớn cần đếm byte, dùng streaming subscriber có giới hạn thay vì `mapping(ofByteArray())`.

### 13.2. Không chặn mã lâu trong `BodyHandler.apply`

`apply(info)` phải chọn subscriber nhanh và trả về. Không thực hiện truy vấn DB, đọc file lớn, gọi HTTP khác hoặc đợi `CompletableFuture.join()` trong lambda handler theo cách có thể làm tắc thread của HTTP Client. Nếu cần cấu hình ngoài, chuẩn bị trước trong một service có thread-safe state và thời gian chờ có giới hạn.

## 14. Những rủi ro bảo mật và vận hành

**1. Header không đáng tin tuyệt đối.** `Content-Type` do server/proxy gửi, có thể sai hoặc cố tình đánh lừa. Chỉ cho phép MIME kỳ vọng, kiểm tra magic bytes/schema/checksum khi tải tệp nhạy cảm, và không thực thi dữ liệu nhận được.

**2. Không dựa riêng vào Content-Length.** Khi header thiếu/sai hoặc response nén, cần giới hạn **bytes thực nhận** và **bytes sau giải nén**. Một file nhỏ trên wire có thể thành hàng GB sau giải nén.

**3. Không ghi đè file khi không kiểm soát.** Dùng đường dẫn nằm trong thư mục được phép, filename an toàn, giới hạn quyền, file tạm, verify và move theo policy. Phải dọn partial file khi network fail hoặc mapping lỗi.

**4. Không biến HTTP error thành success.** `BodySubscribers.replacing("ok")` trên 500 sẽ cho body “ok” nhưng HTTP status vẫn 500; nếu caller chỉ xem body có thể xử lý sai. Đóng gói status/error rõ ràng hoặc check `statusCode()` sau send.

**5. Không log raw response body.** Body có thể chứa token, PII, HTML/script hoặc binary. Log loại MIME, status, request ID, byte count an toàn và error category; giới hạn cardinality của nhãn metrics.

**6. Không tin rằng status 2xx = payload hợp lệ.** Dữ liệu vẫn có thể lỗi JSON, charset, thiếu trường, sai checksum hoặc schema version. BodyHandler chỉ chọn kiểu tiêu thụ; validation vẫn bắt buộc.

**7. Không retry mù quáng.** Request POST có thể đã tạo side effect trước khi client bị timeout; một subscriber bị lỗi giữa chừng không chứng minh server chưa nhận request. Phải có idempotency/retry policy.

**8. Không dùng `ofInputStream()` mà quên đóng.** Body streaming có thể giữ kết nối và tài nguyên nếu client không đọc/đóng; áp dụng `try-with-resources`.

**9. Không dựa vào một phiên bản HTTP.** Java 11 client có thể dùng HTTP/1.1 hoặc HTTP/2; `ResponseInfo.version()` cho actual protocol. Logic xử lý status/body cần đúng ở cả hai vì việc chia frame/packet không phải ranh giới dữ liệu ứng dụng.

**10. Không giả định JSON parser có sẵn trong Java SE.** Dùng thư viện được duy trì khi thật sự parse và validate JSON; chọn version thư viện tương thích JDK 11 và cập nhật bản vá.

## 15. Phân loại lỗi, timeout và async

HTTP error response và lỗi kết nối là hai nhóm khác nhau:

~~~java
try {
    HttpResponse<DecodedBody> response =
        client.send(request, handler());

    if (response.statusCode() >= 400) {
        handleHttpFailure(response.statusCode(), response.body());
    } else {
        handleSuccess(response.body());
    }
} catch (java.net.http.HttpConnectTimeoutException e) {
    reportConnectionTimeout(e);
} catch (java.net.http.HttpTimeoutException e) {
    reportRequestTimeout(e);
} catch (IOException e) {
    reportIoFailure(e);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    reportInterrupted(e);
}
~~~

Đây là **đoạn minh họa**, `DecodedBody`/`handler` như demo; `client`/`request` và các hàm `handle...`/`report...` do ứng dụng định nghĩa. `HttpConnectTimeoutException` là subclass của `HttpTimeoutException` nên đặt catch cụ thể trước. Nếu `BodySubscriber` gặp lỗi decoding, ghi file hoặc mapping, CompletableFuture hay `send` có thể kết thúc lỗi; không tự phát minh một status HTTP khi **không có HttpResponse hoàn chỉnh**.

Với `sendAsync`:

~~~java
CompletableFuture<HttpResponse<DecodedBody>> future =
    client.sendAsync(request, handler());

future.thenAccept(response -> {
    System.out.println("HTTP " + response.statusCode() +
        ", kind=" + response.body().kind);
}).exceptionally(error -> {
    reportAsyncFailure(error);
    return null;
});
~~~

Đây là **đoạn minh họa**, cần import `java.util.concurrent.CompletableFuture` và khai báo `reportAsyncFailure`. Async không đổi semantics của `BodyHandler`: lựa chọn vẫn dựa vào status/headers; chỉ khác cách nhận hoàn tất và exception. Luồng nghiệp vụ phải giữ/chờ future ở nơi phù hợp với vòng đời ứng dụng, xử lý cancellation/timeout và không để tác vụ thất bại âm thầm.

### 15.1. Redirect và nhiều response

Nếu `HttpClient.Redirect.NORMAL`/`ALWAYS` được bật, client có thể nhận response trung gian trước khi có response cuối. `HttpResponse.previousResponse()` có thể cho biết chuỗi trước đó, nhưng body trung gian trong đối tượng previous response không phải payload để ứng dụng parse như response cuối. Khi áp dụng policy dựa trên status/header, cần xác định **response cuối hay từng hop** bạn thực sự muốn xử lý. Không tin rằng redirect tới host khác vẫn có cùng Content-Type hoặc quyền truy cập.

## 16. Lỗi thường gặp và cách khắc phục

| Cách viết sai | Hậu quả | Giải pháp |
| --- | --- | --- |
| `BodyHandlers.ofString()` cho mọi response | Binary bị diễn giải như text, dữ liệu lớn tốn RAM. | Chọn subscriber bằng status và MIME. |
| Chỉ kiểm tra status **sau** khi đã `ofFile` | Response lỗi có thể bị ghi ra file đích. | Dùng custom BodyHandler kiểm tra status trước khi chọn `ofFile`. |
| Gọi `info.body()` trong `apply` | `ResponseInfo` **không có body()**. | Dùng `info.statusCode()`/`headers()`, body do subscriber nhận về sau. |
| Trả `BodySubscriber<String>` và `BodySubscriber<byte[]>` từ `BodyHandler<Object>` | Lỗi generic invariance. | Dùng `mapping` để mọi nhánh trả cùng `T`. |
| Dùng `BodySubscribers.replacing` rồi nghĩ đã chặn mọi bytes trên mạng | Subscriber bỏ body, nhưng giao thức có thể vẫn nhận/tiêu thụ bytes. | Hiểu đúng discard, giới hạn ở nhiều tầng nếu cần. |
| Tin Content-Length mà không kiểm tổng byte thực nhận | Có thể OOM hoặc nhận payload vượt limit. | Bounded streaming và kiểm tra sau giải nén. |
| Dùng `startsWith("application/json")` tùy tiện | Có thể nhận MIME không mong muốn có cùng tiền tố. | Parse media type rồi so sánh chính xác. |
| Dùng `ofString(UTF_8)` với dữ liệu gzip | Nhận ký tự rác/decoding sai. | Kiểm tra `Content-Encoding` và giải nén đúng. |
| Ghi file từ `Content-Disposition` không kiểm tra filename | Path traversal/ghi đè nguy hiểm. | Giới hạn thư mục và sanitize filename, verify/atomic move. |
| Tưởng `200 OK` đồng nghĩa JSON hợp lệ | Schema/charset/format vẫn có thể sai. | Validate sau khi subscriber nhận body. |
| Dùng `BodyHandlers.buffering(..., 8192)` làm giới hạn 8 KiB | Đây là kích thước buffer giữa tầng, không chặn tổng tải. | Dùng bounded subscriber/stream. |
| Quên đóng `response.body()` kiểu InputStream | Rò rỉ tài nguyên/kết nối không tái sử dụng đúng. | `try-with-resources`. |
| Tự parse text lỗi không giới hạn từ server | Error response cũng có thể rất lớn. | Hạn mức lỗi, streaming hoặc bỏ body. |
| Bắt mọi exception rồi trả một response giả 200 | Che lỗi network/TLS/IO. | Phân biệt HTTP status thật và exception. |
| Dùng nhiều request chung một mutable handler state | Race, ghi dữ liệu sang request khác. | Handler stateless hoặc per-request state được đồng bộ. |
| Dùng record/sealed/virtual-thread API trong ví dụ Java 11 | Không biên dịch được với source target 11. | Dùng class Java 11 và API chuẩn có từ JDK 11. |

## 17. Bài tập thực hành có tiêu chí kiểm tra

**Bài 1 — đọc đường đi:** Xác định thứ tự gọi `HttpClient.send`, `BodyHandler.apply`, `BodySubscriber.onNext`, `getBody`, `HttpResponse.body`. Giải thích vì sao không thể dựa vào body bytes trong `ResponseInfo`.

**Bài 2 — rẽ nhánh MIME:** Bổ sung `text/csv; charset=utf-8` vào demo; chọn subscriber text và viết test cho input có dấu tiếng Việt, nhưng chỉ khi endpoint thật sự cam kết CSV UTF-8.

**Bài 3 — status 503:** Cho `/error` trả 503 và text “service unavailable”. Dự đoán `kind`, status và stdout. Kết quả mong đợi: vẫn `HTTP_ERROR`, status 503; không ném IOException chỉ vì status đó.

**Bài 4 — binary:** Thay mảng `{1,2,3}` bằng `{0, (byte)255, 10}`. Dự đoán `Arrays.toString` thể hiện byte signed là `[0, -1, 10]`; giải thích vì sao không nên chuyển binary thành String UTF-8 để xử lý file.

**Bài 5 — thiếu Content-Type:** Tạo endpoint 200 không gửi header Content-Type; demo sẽ trả `IGNORED`. Nếu sản phẩm yêu cầu response thiếu MIME phải báo lỗi, đề xuất cấu trúc `DecodedBody` rõ nhánh `UNSUPPORTED_MEDIA`.

**Bài 6 — giới hạn 1 MiB:** Đọc `Content-Length` để bỏ ngay body có header quá lớn, sau đó triển khai **giới hạn byte thực nhận** bằng subscriber/stream có kiểm soát. Chứng minh header thiếu hoặc sai không làm vượt giới hạn.

**Bài 7 — tải file:** Chọn `BodySubscribers.ofFile(tempPath)` chỉ cho response 200 đúng media type. Sau khi tải xong, verify file rồi chuyển vào thư mục đích. Viết test status 404 không tạo file đích và test ngắt mạng không để file partial ngoài ý muốn.

**Bài 8 — generic:** Vì sao `BodyHandler<Object>` không thể trực tiếp trả `BodySubscriber<String>`? Chứng minh bằng compile error, sau đó dùng `BodySubscribers.mapping` để tạo kiểu `ApiPayload` nhất quán.

**Bài 9 — concurrency:** Hai request đồng thời dùng cùng một handler chứa mutable `StringBuilder` chung. Mô tả race và chuyển sang kiểu immutable/per-response. Viết test chạy song song kiểm tra không trộn dữ liệu.

**Bài 10 — JSON thật:** Chọn một thư viện JSON parser được duy trì, cấu hình dependency cho Java 11, đặt giới hạn chiều sâu/dung lượng JSON, triển khai nhánh `application/json` chỉ cho status hợp lệ và kiểm tra lỗi schema.

**Bài 11 — redirect:** Server A trả 302 sang B có `application/octet-stream`. Nếu app cần chỉ tải từ domain A, cần policy nào trước khi theo redirect? Vì sao handler kiểm MIME ở response cuối không giải quyết toàn bộ SSRF/redirect security?

**Bài 12 — async:** Gửi cùng demo bằng `sendAsync`, xác nhận output logic theo từng request (không giả định thứ tự completion của nhiều request song song) và phân biệt lỗi future với HTTP 404 hợp lệ.

## 18. Checklist thiết kế dùng trong dự án

Trước khi deploy một custom `BodyHandler`:

1. **Hợp đồng response:** endpoint có các status nào, mỗi status được phép có body định dạng gì?
2. **Policy sớm:** với status và headers hiện có, chọn subscriber nào, có cần bỏ dữ liệu ngoài allowlist không?
3. **Kiểu trả về:** mọi nhánh có cùng `BodySubscriber<T>` và kết quả domain không mơ hồ không?
4. **Header parsing:** Content-Type có được chuẩn hóa chính xác, Content-Encoding và charset có được xử lý riêng không?
5. **Dung lượng:** có giới hạn bytes thực nhận, decoded bytes, thời gian và CPU chứ không chỉ tin Content-Length không?
6. **Filesystem:** download có dùng path an toàn, file tạm, cleanup và cơ chế verify trước khi publish không?
7. **Flow:** nếu dùng stream/subscriber riêng, đã kiểm soát backpressure, cancellation, lifecycle và thread-safety chưa?
8. **Lỗi:** HTTP 4xx/5xx có được phân biệt với IOException/TLS/timeout không? Stack trace/cause được giữ đúng không?
9. **Redirect/proxy:** có xác định hop/URL nào trả response và có chính sách host/scheme allowlist không?
10. **Testing:** có test local cho 200 text, 200 binary, 204, 404, MIME lạ, header thiếu, body quá lớn và ngắt kết nối không?
11. **Observability:** ghi status, MIME đã giới hạn, payload size, duration, error category; không log token/raw body?
12. **Tương thích:** source/bytecode/dependency thực sự chạy được trên JDK 11; không dùng API legacy hoặc phiên bản Java ngoài mục tiêu?

## 19. Tài liệu chính thức và tổng kết

- [Java SE 11 — HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): lambda `apply(ResponseInfo)`, lựa chọn subscriber trước khi body đến.
- [Java SE 11 — HttpResponse.ResponseInfo](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.ResponseInfo.html): status, headers và actual HTTP version.
- [Java SE 11 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): `ofString`, `ofByteArray`, `ofFile`, `mapping`, `replacing`, `discarding`, streaming.
- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): các factory xử lý response có sẵn.
- [Java SE 11 — HttpHeaders](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpHeaders.html): `firstValue`, `allValues` và các quy tắc về tên header.
- [JEP 321 — HTTP Client API](https://openjdk.org/jeps/321): Java HTTP Client chuẩn từ Java 11.

**Ghi nhớ:** `BodyHandler` **chọn cách nhận body theo status và header trước khi body được xử lý**; `BodySubscriber` thực sự **tiêu thụ byte và tạo kết quả kiểu T**. Phân nhánh theo status trước, xác minh MIME/charset/encoding, giữ cùng kiểu generic ở mọi nhánh, bỏ dữ liệu không cần thiết, giới hạn tài nguyên cho response lớn và kiểm thử bằng HTTP server cục bộ. `BodyHandler` giúp đọc đúng dữ liệu chứ không tự thay thế validation, an toàn filesystem hoặc chính sách retry.