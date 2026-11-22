# Kiểm thử URI không hợp lệ, header sai và thiếu dữ liệu trong HttpRequest (Java 11+)

> **Chủ đề:** HTTP Request. Bài này tập trung vào **kiểm thử request trước khi gửi** và **kiểm thử hợp đồng dữ liệu khi server nhận request**, dùng `java.net.http.HttpRequest` có từ Java 11. Kiến thức và các API cơ bản dưới đây vẫn áp dụng trên các JDK hiện đại. Phần kiểm thử ban đầu **không cần Internet**, không liên hệ endpoint bên ngoài và không sử dụng thư viện HTTP lỗi thời.

## 1. Mục tiêu học tập và câu hỏi cốt lõi

Khi viết mã HTTP, không phải dữ liệu sai nào cũng dẫn đến cùng một loại lỗi. Một URI chứa khoảng trắng, một header có dấu xuống dòng, một request chưa có URI, và một POST không có body là **bốn vấn đề khác nhau**. Nếu gộp chúng thành “HTTP request không hợp lệ”, test sẽ dễ kiểm sai lớp chịu trách nhiệm.

Sau bài này, bạn có thể:

1. Phân biệt lỗi **cú pháp URI** ở `URI.create(...)`, lỗi **URI không được HTTP Client hỗ trợ**, và URI **hợp lệ về kỹ thuật nhưng không được nghiệp vụ cho phép**.
2. Tạo test cho header có **tên sai**, **giá trị sai**, header `null` và danh sách header thiếu cặp tên/giá trị.
3. Hiểu khi nào `HttpRequest.Builder.build()` tự báo lỗi, khi nào ứng dụng phải tự **validate dữ liệu bắt buộc**, và khi nào lỗi chỉ phát hiện được ở **server**.
4. Phân biệt `POST(BodyPublishers.noBody())`, body rỗng, body `null`, thiếu `Content-Type` và thiếu trường nghiệp vụ.
5. Viết bài kiểm thử **không gửi mạng** cho những lỗi phát hiện ngay trong lúc tạo request.
6. Viết bài kiểm thử **tích hợp HTTP cục bộ** xác nhận response `400`, `415` và `201` theo một hợp đồng server rõ ràng.
7. Xử lý lỗi bằng thông tin chính xác, không làm rò token, không tắt TLS validation, không gửi URL do người dùng cung cấp tới đích tùy ý.

## 2. Ba tầng xác thực dữ liệu request

Đây là mô hình quan trọng nhất của bài:

~~~text
Đầu vào có thể sai
     |
     v
(1) Java URI parser
    URI.create(raw)
    - Sai cú pháp URI? -> IllegalArgumentException
     |
     v
(2) HttpRequest.Builder
    .uri(...), .header(...), .POST(...), .build()
    - Scheme không hỗ trợ, header cú pháp sai,
      chưa cấu hình URI? -> Exception ở phía client
     |
     v
(3) Hợp đồng nghiệp vụ và server
    - Thiếu title, thiếu API key, body JSON sai,
      thiếu Content-Type...?
    - Ứng dụng tự validate trước khi gửi HOẶC
      server trả HTTP 400/401/415/422... theo API
     |
     v
Chỉ gọi client.send(...) khi request đã được kiểm tra đủ
~~~

**Không tự đồng nhất các tầng:**

- `URI.create(...)` trả về một `URI` nếu chuỗi **đúng cú pháp URI**, chứ không kiểm tra URL này có hoạt động hoặc được phép truy cập hay không.
- `HttpRequest.Builder` kiểm tra một số quy tắc **cấu trúc HTTP request**. Nó **không biết** trường `name` có bắt buộc theo API của bạn hay không.
- Nếu server nhận được request hợp lệ về mặt giao thức nhưng dữ liệu nghiệp vụ thiếu, `HttpClient.send(...)` thường trả `HttpResponse<T>` có `statusCode()` thuộc nhóm 4xx. Nó **không tự ném `IllegalArgumentException` chỉ vì server trả 400**.
- Một số tình huống có thể gặp `IOException`, timeout, lỗi TLS hoặc `InterruptedException` khi **thực sự gửi** request; đó là tầng I/O, không phải lỗi xác thực đầu vào ở builder.

| Loại kiểm thử | Ví dụ | Nơi phát hiện thường gặp | Kết quả nên assert |
| --- | --- | --- | --- |
| Sai cú pháp URI | `https://example.com/a b` | `URI.create` | `IllegalArgumentException` |
| Scheme không phải HTTP(S) | `ftp://example.com/a` | `HttpRequest.newBuilder(uri)` | `IllegalArgumentException` |
| URI tương đối | `/tasks` | `HttpRequest.newBuilder(uri)` | URI không thể dùng làm HTTP request đích |
| Thiếu URI | `HttpRequest.newBuilder().build()` | `build()` | `IllegalStateException` |
| Header name sai | `"Bad Header"` | `header(...)` | `IllegalArgumentException` |
| Header value có CR/LF | `"ok\r\nInjected: yes"` | `header(...)` | `IllegalArgumentException` |
| Header value là `null` | `header("X-Trace", null)` | Kiểm tra đối số | `NullPointerException` |
| Thiếu trường `message` bắt buộc | `"   "` | Validator của ứng dụng | Lỗi nghiệp vụ đã định nghĩa, ví dụ `IllegalArgumentException` |
| POST có body rỗng | `BodyPublishers.noBody()` | **Không mặc định sai** ở builder | Request có thể được tạo; server quyết định |
| Thiếu `Content-Type` | Có body nhưng không set header | **Không mặc định sai** ở builder | Server có thể trả `415` theo hợp đồng |
| Thiếu xác thực | Không có `Authorization` | Hợp đồng auth/server | Có thể `401/403`, tùy API |
| Endpoint tồn tại nhưng đường dẫn sai | `/api/missing` | Server | Thường `404`, tùy định tuyến |

Bảng là định hướng kiểm thử, không quy định mọi server phải dùng một mã status giống nhau cho cùng lỗi. **Status là quyết định của API/server**, không phải một quy tắc do `HttpRequest.Builder` áp đặt.

## 3. Kiểm thử URI không hợp lệ

### 3.1. Phân biệt URI sai cú pháp và URI không dùng được với HTTP Client

`java.net.URI` tuân theo cú pháp URI tổng quát. Ví dụ:

~~~java
URI.create("https://example.com/a%20b"); // URI hợp lệ, khoảng trắng đã mã hóa
URI.create("https://example.com/a b");   // IllegalArgumentException
~~~

Đoạn mã minh họa, cần import `java.net.URI`. Khoảng trắng thô không hợp lệ trong chuỗi URI truyền vào `URI.create`. Phần `%20` là dạng percent-encoding cho khoảng trắng trong path.

Một URI có thể **hợp lệ theo cú pháp tổng quát** nhưng không phù hợp để `HttpClient` gửi HTTP:

~~~java
URI ftp = URI.create("ftp://example.com/file");
HttpRequest.newBuilder(ftp);            // IllegalArgumentException

URI relative = URI.create("/tasks");
HttpRequest.newBuilder(relative);       // IllegalArgumentException
~~~

Các ví dụ này phù hợp với `HttpClient` đi kèm JDK 11 và các JDK hiện đại. HTTP request cần một URI đích thuộc scheme HTTP/HTTPS được implementation hỗ trợ và có host thích hợp. `ftp:` không phải HTTP, còn `/tasks` là relative URI không có scheme và authority/host phù hợp.

**Vị trí ném lỗi có ý nghĩa:**

- Với `"https://example.com/a b"`, `URI.create` đã thất bại **trước** khi tạo builder.
- Với `"ftp://example.com/file"`, `URI.create` có thể thành công, nhưng `HttpRequest.newBuilder(ftp)` **từ chối scheme**.
- Với URI thiếu hoàn toàn, `HttpRequest.newBuilder().GET().build()` thất bại vì builder **chưa được cấp URI**.

Đừng viết test cố bắt `URISyntaxException` trực tiếp từ `URI.create`. Phương thức `URI.create(String)` bao bọc lỗi cú pháp thành **`IllegalArgumentException`**. Nếu dùng constructor `new URI(String)`, ngoại lệ checked có thể là `URISyntaxException` — đó là một API khác và cần test đúng API đang gọi.

### 3.2. URI đúng cú pháp vẫn có thể sai nghiệp vụ hoặc không an toàn

Ví dụ cả hai URI đều có thể tạo được:

~~~java
URI.create("https://example.com/tasks?id=");
URI.create("http://127.0.0.1:8080/internal");
~~~

Nhưng:

- `?id=` có thể là **thiếu giá trị `id`** theo hợp đồng API.
- Một URL đến loopback hoặc địa chỉ mạng nội bộ có thể **không được phép** nếu do người dùng gửi cho một hệ thống server-side (rủi ro SSRF).
- URI không tự chứng minh server tồn tại, DNS/TLS hoạt động, user có quyền truy cập, hoặc tài nguyên đúng.
- URI có fragment `#section` không mang ý nghĩa là phần định tuyến gửi đến server trong HTTP request; đừng dùng fragment để truyền trường bắt buộc đến API.
- URI chứa query trông như đủ trường nhưng thiếu URL encoding vẫn có thể làm server hiểu khác dự định; đừng nối trực tiếp chuỗi không đáng tin vào URL.

**Cách làm:** kiểm tra URI theo chính sách ứng dụng (scheme, host, port, đường dẫn, tham số bắt buộc, allowlist khi phù hợp), rồi mới tạo request. Với URI từ người dùng, kiểm tra thêm chuyển hướng và chính sách kết nối ở tầng network; chỉ kiểm `uri.getScheme()` chưa phải biện pháp chống SSRF đầy đủ.

### 3.3. Mã hóa đúng phần URI

Không xây path/query bằng cách nối chuỗi thô tùy ý. Phần path và query có quy tắc encoding riêng. Với dữ liệu có khoảng trắng hoặc dấu `&`, `?`, `#`, cần mã hóa ở **đúng thành phần** của URI. `URLEncoder` chủ yếu sử dụng cho **HTML form/query-style encoding**, không phải một bộ mã hóa chung cho cả đường dẫn URL. Với API cụ thể, dùng URI builder phù hợp hoặc tạo `URI` từ các thành phần riêng và kiểm tra kết quả.

Ví dụ nguyên tắc: nếu muốn path `/a b`, dạng `/a%20b` có ý nghĩa khác với việc đưa chuỗi thô `/a b` vào `URI.create`.

## 4. Kiểm thử header sai

### 4.1. Header name phải có cú pháp hợp lệ

Trong HTTP, tên header là một *token* theo quy tắc giao thức. Tên chứa khoảng trắng, ký tự phân tách không được phép hoặc ký tự điều khiển có thể bị từ chối.

~~~java
HttpRequest.newBuilder()
        .header("Bad Header", "value"); // IllegalArgumentException
~~~

Phần trên **không có lệnh gửi HTTP**; builder kiểm tra ngay trong lời gọi `header`. Không cần tạo `HttpClient` hoặc mock HTTP server để phát hiện lỗi tên header này.

Tên header thông thường nên rõ ràng, ví dụ `Accept`, `Content-Type`, `X-Trace-Id` hoặc các tên chuẩn khác mà API của bạn quy định. Header HTTP **không phân biệt chữ hoa/chữ thường ở tên**; test không nên giả định `Content-Type` và `content-type` là hai header độc lập về ngữ nghĩa.

### 4.2. Giá trị header chứa xuống dòng hoặc ký tự điều khiển

Ví dụ độc hại hoặc lỗi ghép chuỗi:

~~~java
HttpRequest.newBuilder()
        .header("X-Trace", "ok\r\nInjected: yes");
~~~

`\r\n` là CRLF. Trên JDK chuẩn, mẫu này gây `IllegalArgumentException` do header value không hợp lệ; nó không được phép âm thầm tạo một header mới bằng cách chèn xuống dòng. Đây là một trong những lớp phòng vệ chống **HTTP header injection**.

Tuy nhiên, việc client từ chối CRLF **không thay thế** việc kiểm dữ liệu nghiệp vụ: một chuỗi không có CRLF vẫn có thể không được phép theo định dạng `X-Trace-Id` mà hệ thống yêu cầu (chẳng hạn tối đa 64 ký tự hoặc chỉ gồm chữ/số/gạch nối).

### 4.3. Header `null` và thiếu cặp tên/giá trị

~~~java
HttpRequest.newBuilder().header("X-Trace", null);
// NullPointerException

HttpRequest.newBuilder().headers("Accept", "application/json", "X-Trace");
// IllegalArgumentException: số đối số lẻ
~~~

`headers(String... headers)` nhận luân phiên **tên, giá trị, tên, giá trị...**. Test nên dùng dữ liệu đầu vào chính xác và xác nhận loại ngoại lệ, không assert toàn bộ chuỗi message do JDK tạo ra vì message có thể thay đổi.

Phân biệt các lỗi:

- `null` là **thiếu đối tượng**, thường dẫn đến `NullPointerException` ở API.
- `""` có thể là **giá trị rỗng hợp lệ về mặt giao thức** với một số header, nhưng vẫn có thể bị nghiệp vụ cấm.
- Tên header rỗng hoặc chứa ký tự không hợp lệ là lỗi **cú pháp**, thường `IllegalArgumentException`.
- Các header được JDK tự quản lý, ví dụ `Content-Length`, có thể bị **hạn chế bởi implementation**. Không viết test portable đòi được tự set các header này hoặc đòi đúng một thông điệp lỗi trên mọi bản JDK.

### 4.4. `header`, `setHeader` và nhiều giá trị

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/items"))
        .header("X-Tag", "one")
        .header("X-Tag", "two")
        .setHeader("Accept", "application/json")
        .GET()
        .build();
~~~

Đây là **đoạn minh họa**, cần import `HttpRequest` và `URI`. `header` thêm một giá trị; `setHeader` đặt lại danh sách giá trị của header tương ứng. Nếu API cấm lặp `X-Tag` hoặc đòi một giá trị duy nhất, việc đó phải được kiểm tra theo **hợp đồng API**, không được mặc nhiên cho rằng builder sẽ từ chối mọi header trùng.

### 4.5. Header sai về nghiệp vụ khác với header sai về cú pháp

Ví dụ `Authorization`, `Content-Type` hoặc `Accept`:

- Header `Authorization` bị thiếu **không** khiến builder tự tạo lỗi. Endpoint được bảo vệ có thể trả `401` hoặc `403`.
- Header `Content-Type` bị thiếu với POST body là chuyện server/contract quyết định; builder không tự biết endpoint chỉ nhận JSON.
- Header `Accept` hợp lệ về cú pháp nhưng đề nghị media type server không cung cấp có thể dẫn tới `406`; không phải `IllegalArgumentException` ở builder.
- Nếu dùng `BodyPublishers.ofString(...)`, hãy đặt `Content-Type` rõ khi cần. Publisher chỉ cung cấp byte cho body; không tự bảo đảm header mô tả đúng kiểu dữ liệu.

Test nên tách **cú pháp header** (unit test không cần mạng) và **yêu cầu header của API** (contract/integration test).

## 5. “Thiếu dữ liệu” có thể nghĩa là những gì?

Một request thiếu dữ liệu không luôn tương đương request không có body. Xác định rõ **loại dữ liệu thiếu**, **ai bắt buộc nó**, và **kết quả kỳ vọng**.

| Trường hợp | Java HTTP builder có từ chối? | Nên kiểm tra ở đâu? |
| --- | --- | --- |
| Chưa đặt URI rồi gọi `build()` | **Có:** `IllegalStateException` | Unit test builder |
| Gọi `POST(null)` | Tham số `BodyPublisher` không hợp lệ; có thể `NullPointerException` | Unit test API/null contract |
| Gọi `POST(BodyPublishers.noBody())` | **Không mặc định sai** | Contract API/server, nếu body bắt buộc |
| Gọi `POST(BodyPublishers.ofString(""))` | Body dài 0 byte, không mặc định sai | Contract API/server |
| POST JSON không có trường `name` | Builder không parse JSON | Validator, schema hoặc server |
| Trường `message` là `null` hoặc chỉ chứa khoảng trắng | Builder không biết quy tắc nghiệp vụ | Validator ứng dụng |
| Thiếu `Content-Type` | Builder thường vẫn build được | API/server, có thể 415 |
| Thiếu `Authorization` | Builder thường vẫn build được | Auth layer, có thể 401/403 |
| Thiếu query param bắt buộc | URI vẫn có thể hợp lệ | Validator/HTTP endpoint |
| Thiếu endpoint/host hợp lệ | Tùy cách tạo URI: parser/builder có thể từ chối | URI parsing và policy validation |

### 5.1. Phân biệt noBody và body rỗng

~~~java
// POST với publisher công bố 0 byte
HttpRequest emptyPost = HttpRequest.newBuilder(
        URI.create("https://example.com/tasks"))
        .POST(HttpRequest.BodyPublishers.noBody())
        .build();

// POST với một chuỗi rỗng được publisher mã hóa
HttpRequest emptyTextPost = HttpRequest.newBuilder(
        URI.create("https://example.com/tasks"))
        .POST(HttpRequest.BodyPublishers.ofString(""))
        .build();
~~~

Cả hai request **có thể được tạo** bằng API Java 11. Với `BodyPublishers.noBody()`, `contentLength()` trả **0**; với `ofString("")` cũng là 0 byte. Nhưng ý nghĩa nghiệp vụ khác nhau tùy endpoint. Một API yêu cầu `message` không rỗng phải **tự kiểm tra** quy tắc đó, thường trước khi gửi.

Đừng nhầm:

- **Không đặt BodyPublisher**: thường xảy ra ở GET, khi `bodyPublisher()` là `Optional.empty()`.
- **Đặt BodyPublisher không tạo byte**: `POST(noBody())` có publisher với content length 0.
- **Trường JSON `null`**: có thể là chuỗi payload chứa ký tự `null` hoặc field có giá trị JSON null; đây không phải một `null` Java cho đối số `BodyPublisher`.

### 5.2. Thiếu dữ liệu cần validator riêng

Ví dụ hàm tạo POST dạng text yêu cầu `content` có giá trị không chỉ là khoảng trắng:

~~~java
static HttpRequest createMessage(URI destination, String content) {
    if (content == null || content.isBlank()) {
        throw new IllegalArgumentException("content must not be blank");
    }

    return HttpRequest.newBuilder(destination)
            .header("Content-Type", "text/plain; charset=UTF-8")
            .POST(HttpRequest.BodyPublishers.ofString(
                    content, StandardCharsets.UTF_8))
            .build();
}
~~~

Đây là **method minh họa**, cần đặt trong class và import `URI`, `HttpRequest`, `StandardCharsets`. `String.isBlank()` tồn tại từ Java 11. Hợp đồng `content` không rỗng là **quy tắc do ứng dụng đặt ra**, không phải yêu cầu bắt buộc của HTTP POST.

Với JSON cần schema cụ thể, đừng tự dựng JSON bằng cách nối chuỗi của người dùng; dùng JSON serializer và validator phù hợp. Bài này minh họa `text/plain` để tránh phụ thuộc thư viện JSON ngoài Java SE.

## 6. Chương trình hoàn chỉnh: kiểm thử URI/header/thiếu dữ liệu mà không gọi mạng

Tạo tệp **`RequestChecksDemo.java`** với toàn bộ mã sau. Mỗi test dùng `reject` để khẳng định đúng **loại exception**; nếu không ném lỗi hoặc ném sai loại, chương trình báo `AssertionError` thay vì in “PASS” giả.

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

public class RequestChecksDemo {
    private static void reject(
            String label,
            Class<? extends RuntimeException> wanted,
            Runnable action) {

        try {
            action.run();
            throw new AssertionError("Expected failure: " + label);
        } catch (RuntimeException ex) {
            if (!wanted.isInstance(ex)) {
                throw new AssertionError(
                        "Wrong error for " + label, ex);
            }
            System.out.println(
                    label + "=" + ex.getClass().getSimpleName());
        }
    }

    private static HttpRequest createMessage(
            URI destination, String content) {

        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException(
                    "content must not be blank");
        }

        return HttpRequest.newBuilder(destination)
                .header("Content-Type",
                        "text/plain; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        content, StandardCharsets.UTF_8))
                .build();
    }

    public static void main(String[] args) {
        reject("bad-uri-syntax", IllegalArgumentException.class,
                () -> URI.create("https://example.com/a b"));

        reject("unsupported-scheme", IllegalArgumentException.class,
                () -> HttpRequest.newBuilder(
                        URI.create("ftp://example.com/a"))
                        .GET().build());

        reject("relative-uri", IllegalArgumentException.class,
                () -> HttpRequest.newBuilder(
                        URI.create("/tasks"))
                        .GET().build());

        reject("bad-header-name", IllegalArgumentException.class,
                () -> HttpRequest.newBuilder()
                        .header("Bad Header", "x"));

        reject("bad-header-value", IllegalArgumentException.class,
                () -> HttpRequest.newBuilder()
                        .header("X-Trace", "ok\r\nInjected: yes"));

        reject("null-header-value", NullPointerException.class,
                () -> HttpRequest.newBuilder()
                        .header("X-Trace", null));

        reject("missing-uri", IllegalStateException.class,
                () -> HttpRequest.newBuilder().GET().build());

        reject("missing-business-data", IllegalArgumentException.class,
                () -> createMessage(
                        URI.create("https://example.com/tasks"), "  "));

        HttpRequest valid = createMessage(
                URI.create("https://example.com/tasks"), "Hello");
        System.out.println("valid-method=" + valid.method());
        System.out.println("valid-body-length="
                + valid.bodyPublisher()
                        .orElseThrow()
                        .contentLength());

        HttpRequest emptyPost = HttpRequest.newBuilder(
                URI.create("https://example.com/tasks"))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
        System.out.println("empty-post-length="
                + emptyPost.bodyPublisher()
                        .orElseThrow()
                        .contentLength());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RequestChecksDemo.java
java RequestChecksDemo
~~~

Có thể dùng `javac --release 11 RequestChecksDemo.java` với bản `javac` hiện đại còn hỗ trợ release 11 để kiểm tra giới hạn cú pháp/API Java 11.

**Stdout đã chạy đối chiếu:**

~~~text
bad-uri-syntax=IllegalArgumentException
unsupported-scheme=IllegalArgumentException
relative-uri=IllegalArgumentException
bad-header-name=IllegalArgumentException
bad-header-value=IllegalArgumentException
null-header-value=NullPointerException
missing-uri=IllegalStateException
missing-business-data=IllegalArgumentException
valid-method=POST
valid-body-length=5
empty-post-length=0
~~~

### Giải thích kết quả theo thứ tự

1. `URI.create("https://example.com/a b")` gặp **khoảng trắng thô** trong URI và thất bại ở parser.
2. `ftp://example.com/a` là URI có cú pháp hợp lệ tổng quát, nhưng `HttpRequest` không chấp nhận scheme `ftp`.
3. `/tasks` là URI tương đối, không đủ thông tin làm đích HTTP.
4. `Bad Header` không phải tên header dạng token hợp lệ.
5. Giá trị `"ok\r\nInjected: yes"` chứa CRLF nên bị từ chối.
6. `null` không phải chuỗi header value hợp lệ.
7. `build()` không có URI gây `IllegalStateException`, đúng hợp đồng Javadoc Java 11.
8. Chuỗi chỉ có khoảng trắng bị **validator do ứng dụng tự định nghĩa** từ chối; không cần tạo request hay gửi mạng.
9. Request tốt dùng POST; từ `"Hello"` mã hóa UTF-8 thành **5 byte**, nên `BodyPublisher.contentLength()` là 5.
10. `noBody()` không phải lỗi builder; độ dài body công bố là **0 byte**.

Mọi ca kiểm tra trên chỉ tạo đối tượng và thực hiện validation. **Không có lời gọi `HttpClient.send`, không cần truy cập `example.com` và không tạo yêu cầu HTTP ra Internet.** Đây là đặc trưng của unit test cấu trúc request.

**Lưu ý tính portable:** Chúng ta assert **loại ngoại lệ và hành vi API** cho các trường hợp nêu rõ, không assert toàn bộ `exception.getMessage()` vì nội dung thông báo có thể khác theo phiên bản/bản phân phối JDK. Đừng áp dụng cùng kết quả cố định này cho mọi header bị implementation hạn chế.

## 7. Kiểm thử tích hợp: request build được nhưng server từ chối dữ liệu

Một kiểm thử chỉ gọi builder không thể chứng minh server chấp nhận dữ liệu theo hợp đồng nghiệp vụ. Ví dụ:

- `POST` body `"hello"` nhưng **không có `Content-Type`** — builder có thể tạo request thành công.
- `POST` có `Content-Type: text/plain` nhưng **body rỗng** — builder có thể tạo request thành công.
- `POST` có **header đúng và body không rỗng** — server có thể tạo tài nguyên.

Để kiểm các nhánh này một cách lặp lại, dựng **HTTP server trên loopback** trong một chương trình Java độc lập. Không cần Internet. Mã test server chủ động định nghĩa: thiếu `Content-Type` → 415; body rỗng → 400; hợp lệ → 201. Đây là **hợp đồng của server thử nghiệm**, không có nghĩa mọi API thật phải dùng chính xác các mã này.

Tạo tệp **`HttpRequestContractDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpRequestContractDemo {
    public static void main(String[] args) throws Exception {
        // Server cục bộ, cổng 0 để hệ điều hành chọn cổng trống.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/messages", exchange -> {
            try {
                String type = exchange.getRequestHeaders()
                        .getFirst("Content-Type");

                // Fixture này chỉ nhận chuỗi cực ngắn do test tự tạo.
                byte[] bytes;
                try (InputStream input = exchange.getRequestBody()) {
                    bytes = input.readAllBytes();
                }

                int status = type == null
                        ? 415
                        : bytes.length == 0 ? 400 : 201;
                String answer = status == 415
                        ? "missing-type"
                        : status == 400 ? "missing-body" : "created";

                byte[] reply = answer.getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(status, reply.length);

                try (var output = exchange.getResponseBody()) {
                    output.write(reply);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();

        try {
            URI endpoint = URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/messages");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            // Có body, thiếu Content-Type.
            HttpRequest noType = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers
                            .ofString("hello"))
                    .build();

            // Có Content-Type, body rỗng.
            HttpRequest empty = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type",
                            "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .build();

            // Đúng Content-Type và có nội dung.
            HttpRequest valid = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type",
                            "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers
                            .ofString("hello"))
                    .build();

            for (HttpRequest request :
                    new HttpRequest[] {noType, empty, valid}) {
                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

                System.out.println(
                        response.statusCode() + ":"
                        + response.body());
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy trên **JDK đầy đủ có module `jdk.httpserver`**:

~~~bash
javac --add-modules jdk.httpserver HttpRequestContractDemo.java
java --add-modules jdk.httpserver HttpRequestContractDemo
~~~

**Stdout đã đối chiếu với fixture:**

~~~text
415:missing-type
400:missing-body
201:created
~~~

### Vì sao bài test này khác bài test ở mục 6?

- Trong cả ba nhánh, `HttpRequest.Builder.build()` **thành công**. Lỗi chỉ được phát hiện ở **hợp đồng server** khi thực sự gửi.
- `HttpClient.send(...)` **không ném exception** chỉ vì HTTP status là 415 hoặc 400. Nó trả `HttpResponse<String>` và ứng dụng đọc `statusCode()`.
- `HttpServer` trong `com.sun.net.httpserver` là API thử nghiệm có trong module JDK `jdk.httpserver`; không phải API của `java.net.http`. Việc dùng server cục bộ giúp test ổn định mà không phụ thuộc dịch vụ công cộng.
- `InputStream.readAllBytes()` bên phía **fixture** chỉ an toàn ở đây vì test tự sinh ra các body cố định rất ngắn. **Không sao chép cách đọc không giới hạn này vào server xử lý upload thực**: phải đặt giới hạn kích thước trước và trong lúc đọc body.
- `server.stop(0)` chạy trong `finally` để giải phóng server sau kiểm thử. Trong ứng dụng lớn, fixture thường được gói vào setup/teardown của bộ test tự động.
- Các HTTP status 400/415/201 ở đây là **giả định đã viết thành code của test server**. Với API thật, status có thể là `422` hoặc thông điệp khác; đọc hợp đồng endpoint thay vì phỏng đoán.

**Tại sao không dùng Internet ngay?** Unit test và integration test nội bộ cần nhanh, có kết quả tái lập, không phụ thuộc DNS, TLS, rate-limit, cấu hình proxy hoặc trạng thái nhà cung cấp. Test E2E với hệ thống thật vẫn hữu ích nhưng phải là lớp kiểm thử riêng có điều kiện môi trường rõ ràng.

## 8. Thiết kế test matrix có hệ thống

Một bộ test chất lượng nên có cả **happy path**, **negative path** và **boundary case**. Không chỉ thử một URI sai và một header sai.

### Nhóm A — URI

| Test case | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| URL HTTP/HTTPS hợp lệ | `https://example.com/tasks` | Request được build; chưa khẳng định server tồn tại |
| Sai URI syntax | `https://example.com/a b` | `URI.create` từ chối |
| Percent encoding không hoàn chỉnh | Ví dụ `https://example.com/%ZZ` | Parser từ chối cú pháp |
| Scheme không được hỗ trợ | `ftp://example.com/x` | Builder từ chối |
| Relative URI | `/tasks` | Builder không chấp nhận làm đích HTTP |
| Thiếu URI | `newBuilder().build()` | `IllegalStateException` |
| URI hợp lệ nhưng thiếu `id` | `https://example.com/tasks?id=` | Validator hoặc API tự từ chối theo hợp đồng |
| Host bị cấm theo chính sách | Loopback/private address do user nhập | App/network policy từ chối, không chỉ dựa vào parser |

### Nhóm B — Header

| Test case | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Header name thông thường | `X-Trace-Id: abc123` | Builder chấp nhận |
| Tên có khoảng trắng | `Bad Header` | `IllegalArgumentException` |
| Tên có ký tự điều khiển | Tên chứa `\n` | Builder từ chối |
| Giá trị CRLF | `"x\r\nAnother: y"` | Builder từ chối |
| Header value null | `null` | `NullPointerException` |
| `headers(...)` thiếu một value | 3 tham số thay vì cặp | `IllegalArgumentException` |
| Header lặp lại | `header("X-Tag","a")` hai lần | Kiểm danh sách giá trị theo hợp đồng |
| Header chỉ cho phép một giá trị | Hai `Authorization` hoặc header nghiệp vụ tương tự | Validator/contract, không suy diễn builder tự cấm |
| `Content-Length` do ứng dụng tự set | Giá trị bất kỳ | Implementation có thể hạn chế; kiểm theo Javadoc, không ép portable |

### Nhóm C — Thiếu dữ liệu

| Test case | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Content là `null` | `createMessage(uri, null)` | Validator từ chối |
| Content là `""` hoặc `"  "` | Text field bắt buộc | Validator từ chối |
| Content hợp lệ | `"Hello"` | Build POST, BodyPublisher dài 5 byte |
| POST body rỗng | `noBody()` | Builder chấp nhận; server có thể báo 400 |
| Thiếu `Content-Type` | POST có body | Builder chấp nhận; server có thể báo 415 |
| Thiếu auth | Không có header/token | Server/auth layer báo theo API |
| JSON thiếu field | `{}`, `{"name":null}` | Schema validator hoặc server quyết định |
| Thiếu query param | URL không có `id` | Validator/endpoint tùy hợp đồng |
| Dữ liệu có vẻ hợp lệ nhưng quá lớn | Body hoặc field quá cap | Validator/server giới hạn kích thước |

Các test phủ định nên khẳng định **đúng tầng lỗi**. Không viết test “gọi builder với JSON thiếu name phải có `IllegalArgumentException`” nếu ứng dụng chưa hề có validator riêng cho `name`.

## 9. Viết unit test chuẩn trong dự án dùng JUnit 5

Các demo ở mục 6–7 chạy độc lập trên Java 11 mà không cần dependency. Trong một dự án thực tế đã dùng **JUnit Jupiter (JUnit 5)**, cùng ý tưởng có thể tổ chức thành test method độc lập:

~~~java
// Đoạn minh họa cho test class JUnit Jupiter; không chạy độc lập
// nếu chưa có dependency org.junit.jupiter và import tương ứng.
@Test
void rejectsInvalidHeaderName() {
    assertThrows(IllegalArgumentException.class,
            () -> HttpRequest.newBuilder()
                    .header("Bad Header", "value"));
}

@Test
void acceptsExplicitlyEmptyPostAtBuilderLevel() {
    HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://example.com/tasks"))
            .POST(HttpRequest.BodyPublishers.noBody())
            .build();

    assertEquals("POST", request.method());
    assertEquals(0L, request.bodyPublisher()
            .orElseThrow().contentLength());
}
~~~

Cần import `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.Assertions.assertThrows` và `assertEquals` cùng `URI`, `HttpRequest`; phần test file phải có class bao ngoài. **Không** biến ví dụ này thành “mã Java SE chạy được ngay” khi chưa cấu hình JUnit.

Cách tổ chức hợp lý:

- Mỗi loại đầu vào sai có **test name** mô tả hành vi, không chỉ `testError1`.
- Dùng `assertThrows` và chỉ kiểm chính xác **loại exception** khi API đảm bảo; nếu muốn kiểm message do validator riêng tạo thì có thể assert message của **chính ứng dụng**.
- Cho URI sai hoặc header syntax sai, **không cần HTTP server**; test thuần tạo object sẽ nhanh và ổn định.
- Với các quy tắc của API server, dựng **server giả có phản hồi xác định** để kiểm status và body lỗi.
- Dùng test parameterized cho nhiều URI/name sai nếu số case tăng. Tránh lặp test thủ công khó bảo trì.
- Đừng tự động dùng `assertThrows(Exception.class, ...)` cho mọi lỗi: như vậy mất khả năng phát hiện việc lỗi chuyển từ validation sang network hoặc ngược lại.

## 10. Test đúng ranh giới bất đồng bộ và gửi request

Bài này là **kiểm thử xây dựng `HttpRequest`**; phần lớn lỗi cấu trúc xảy ra **trước** `HttpClient.send` hoặc `sendAsync`.

- Nếu lỗi ở `URI.create` hoặc `header`, phương thức có thể ném exception **ngay khi builder được gọi**. Không tạo fake `CompletableFuture` để chờ lỗi vốn đã đồng bộ.
- Nếu lỗi do server trả `400/415/422`, cả `send` lẫn `sendAsync` nhận được **HTTP response** (nếu mạng hoạt động bình thường); application phải kiểm `statusCode()`.
- Nếu lỗi là timeout, DNS, kết nối hoặc TLS, đó là lỗi **I/O**, thường `IOException` với `send` hoặc completion bất thường của future với `sendAsync`. Test các lỗi này riêng để tránh làm test hợp đồng URI/header bị phụ thuộc thời gian.
- Nếu request có publisher đọc từ file/stream, quá trình build có thể thành công nhưng lỗi tạo/đọc body phát sinh **khi gửi**; đừng coi `build()` thành công nghĩa là chắc chắn có dữ liệu đầu ra.
- Nếu client/server sử dụng redirect, auth/proxy hoặc bộ lọc, request thực tế có thể khác dự kiến; test tích hợp phải kiểm chính sách cụ thể.

**Quy tắc kiểm thử:** trước tiên phân loại lỗi nào có thể thấy bằng **request object**, lỗi nào chỉ có thể thấy sau **server response**, và lỗi nào chỉ biểu hiện ở **I/O**. Sau đó chọn phạm vi test tương ứng.

## 11. Thông báo lỗi và xử lý input an toàn

Một hàm xây request cho nghiệp vụ nên từ chối dữ liệu thiếu **càng sớm càng tốt**, tại nơi biết đầy đủ hợp đồng:

~~~java
static String requireNonBlank(String value, String fieldName) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(
                fieldName + " must not be blank");
    }
    return value;
}
~~~

Đây là **method minh họa**, có thể đặt trong class service/utility. Nó không kiểm format phức tạp như email, JSON schema, UUID hoặc giới hạn độ dài; từng loại dữ liệu cần validator riêng.

Quy tắc thực dụng:

1. Đừng để exception message vô tình chứa **API key, Authorization header, password, token hoặc toàn bộ body có dữ liệu cá nhân**.
2. Khi log URI, cân nhắc redaction các query param nhạy cảm và loại bỏ credentials ở URI.
3. Với lỗi URI do user nhập, trả thông báo dạng “URL không hợp lệ” hoặc “host không được phép” thích hợp; không phơi chi tiết hệ thống nội bộ.
4. Validate scheme/host/port/redirect cho URL không đáng tin, nhất là trong ứng dụng server-side. **URI hợp lệ về cú pháp chưa đủ chống SSRF**.
5. Giới hạn độ dài header, field, query, body, số lượng phần tử và thời gian xử lý theo chính sách của ứng dụng/server.
6. Tên header do chương trình tạo nên lấy từ hằng số/tập cho phép, thay vì ghép trực tiếp từ dữ liệu người dùng.
7. Không tự set header JDK quản lý như `Content-Length` chỉ để “sửa lỗi”; dùng đúng `BodyPublisher` để hệ thống tính độ dài thích hợp.
8. Với POST tạo tài nguyên, tránh retry mù khi gặp timeout vì server có thể đã xử lý một phần hoặc toàn bộ request; dùng idempotency theo hợp đồng API nếu cần.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sai ở đâu? | Hướng đúng |
| --- | --- | --- |
| “`URI.create` thành công thì HTTP endpoint hợp lệ.” | Chỉ kiểm cú pháp URI, không kiểm server/permission | Test policy và endpoint riêng |
| “URI tương đối `/x` dùng trực tiếp được với Java HttpClient.” | Không phải URI HTTP đích hoàn chỉnh | Tạo URI tuyệt đối HTTP/HTTPS hợp lệ |
| “Header có khoảng trắng trong tên vẫn được.” | Tên header phải là token đúng giao thức | Dùng tên hợp lệ, test negative |
| “JDK chấp nhận xuống dòng trong value.” | CR/LF có thể tạo header injection | Header builder từ chối value sai |
| “Header value null và value rỗng là như nhau.” | `null` là thiếu object; `""` có nghĩa riêng | Test null riêng; validator quyết định rỗng |
| “`headers(...)` có thể truyền số chuỗi lẻ.” | API nhận các cặp name/value | Truyền cặp đúng thứ tự |
| “Không có Content-Type thì `build()` phải ném.” | Builder không biết hợp đồng endpoint | Set header khi cần; test server trả status |
| “POST không có body luôn bị Java từ chối.” | `BodyPublishers.noBody()` hợp lệ | Phân biệt protocol và business rule |
| “String rỗng có nghĩa là bodyPublisher null.” | `ofString("")` vẫn là publisher tạo 0 byte | Test content length/contract riêng |
| “JSON thiếu field thì `HttpRequest` tự phát hiện.” | Builder không parse JSON | Validate DTO/schema hoặc server |
| “HTTP 400/415 sẽ ném `IllegalArgumentException`.” | HTTP response không phải lỗi builder | Kiểm `HttpResponse.statusCode()` |
| “Exception message của JDK bất biến.” | Có thể đổi giữa version/implementation | Assert loại lỗi và trạng thái có ý nghĩa |
| “`build()` thành công nghĩa là gửi chắc chắn thành công.” | Chưa kiểm mạng/TLS/server và body publisher | Test gửi riêng, xử lý I/O và response |
| “Test cần gọi API Internet để có tính thực tế.” | Test trở nên chậm và không ổn định | Unit test không mạng, integration test loopback |
| “Dữ liệu đầu vào sai thì nên catch mọi Exception và bỏ qua.” | Che giấu lỗi logic và che phạm vi lỗi | Tách validation, HTTP status, I/O rõ ràng |

## 13. Checklist cho một pull request có HttpRequest

- [ ] Mọi request đều có URI đích hợp lệ; test URI syntax, scheme và URI thiếu.
- [ ] URI do người dùng nhập được kiểm policy an toàn, không chỉ parse thành công.
- [ ] Header name/value đã tuân thủ cú pháp, tránh ký tự điều khiển và dữ liệu null.
- [ ] Không giả định có thể set mọi header do JDK quản lý.
- [ ] Các trường nghiệp vụ bắt buộc được xác thực độc lập với `HttpRequest.Builder`.
- [ ] Có test riêng cho body rỗng, `BodyPublishers.noBody()` và body hợp lệ.
- [ ] `Content-Type` và `Accept` được khai báo theo hợp đồng API khi cần.
- [ ] Unit test cho builder **không gọi mạng**; integration test server có fixture xác định.
- [ ] Test HTTP error kiểm `statusCode()` và thông điệp phản hồi, không mong builder ném exception.
- [ ] Test không phụ thuộc toàn bộ exception message, external DNS, timeout ngẫu nhiên hoặc thứ tự request bất định.
- [ ] Mã chạy bằng Java 11+ và không dùng tính năng HTTP Request chỉ mới xuất hiện trên các JDK mới.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Chuỗi URI `"https://example.com/a b"` bị từ chối ở đâu?

**Đáp án:** `URI.create` không chấp nhận khoảng trắng thô; bạn sẽ nhận `IllegalArgumentException` trước khi dùng HTTP builder. Cần mã hóa thành phần path đúng cách.

**Câu 2.** `URI.create("ftp://example.com/file")` có thể tạo được, vậy `HttpRequest.newBuilder(uri)` có gửi request HTTP không?

**Đáp án:** Không. URI tổng quát có thể có `ftp`, nhưng HTTP Client chỉ nhận scheme HTTP/HTTPS phù hợp; builder từ chối scheme không hỗ trợ bằng `IllegalArgumentException`.

**Câu 3.** Header name `"Bad Header"` sai, có cần khởi động HTTP server để kiểm không?

**Đáp án:** Không. `header(...)` sẽ từ chối ngay; một unit test thuần là đủ.

**Câu 4.** `POST(BodyPublishers.noBody())` có bị Java 11 tự từ chối không?

**Đáp án:** Không. Nó mô tả POST không gửi byte body. Nếu endpoint bắt buộc body, validator phía ứng dụng hoặc server phải áp đặt quy tắc đó.

**Câu 5.** Không có `Content-Type` nhưng POST có body, exception mặc định là gì?

**Đáp án:** Không có exception bắt buộc ở builder chỉ vì thiếu header này. Server có thể báo `415`, `400` hoặc hành vi khác tùy hợp đồng; test server phải nêu rõ kỳ vọng.

**Câu 6.** Tại sao `HttpClient.send` trả response `400` không đồng nghĩa test builder sai?

**Đáp án:** Vì request có thể đã đúng về cú pháp, nhưng server từ chối dữ liệu. Đây là **kết quả HTTP**; client đọc `statusCode()` và xử lý nghiệp vụ.

**Câu 7.** Khi test lỗi, nên assert chuỗi `"invalid header..."` nguyên văn do JDK tạo ra không?

**Đáp án:** Thường không. Assert **loại exception** và điều kiện hợp đồng; chuỗi thông báo cụ thể của JDK không phải giao diện ổn định cho ứng dụng.

## Tài liệu tham khảo chính thức và còn áp dụng

- [`HttpRequest.Builder` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `uri`, `header`, `headers`, `setHeader`, `POST`, `build` và ngoại lệ được tài liệu hóa.
- [`HttpRequest` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): `newBuilder`, `bodyPublisher()` và request immutable.
- [`HttpRequest.BodyPublishers` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `noBody()`, `ofString(...)` và `contentLength()`.
- [`URI` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/URI.html): cú pháp và cách tạo/parse URI.
- [`HttpClient` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `send` và xử lý kết quả HTTP.
- [`HttpServer` — JDK 11](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): test fixture server loopback trong module JDK `jdk.httpserver`.
- [`HttpRequest.Builder` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): kiểm tra các API cốt lõi vẫn còn được hỗ trợ; bài không sử dụng những tính năng mới chỉ có ở JDK 26.

**Ghi nhớ:** Một test tốt phải xác định **ai có trách nhiệm phát hiện dữ liệu sai**. `URI` xử lý cú pháp, `HttpRequest.Builder` xử lý cấu trúc request, validator xử lý quy tắc nghiệp vụ, server trả status theo hợp đồng, và `HttpClient` xử lý giao tiếp mạng. Tách đúng các tầng sẽ giúp test Java 11+ chính xác, nhanh, ổn định và dễ bảo trì.