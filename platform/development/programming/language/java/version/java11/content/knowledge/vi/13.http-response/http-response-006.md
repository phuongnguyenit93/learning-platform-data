# HTTP Response: BodyHandlers.ofByteArray() và discarding() trong Java 11+

> **Phạm vi:** Hai cách xử lý thân phản hồi HTTP bằng API chuẩn `java.net.http.HttpResponse.BodyHandlers`: **`ofByteArray()`** khi cần giữ byte phản hồi, và **`discarding()`** khi chỉ cần thông tin như mã trạng thái hoặc headers. Cả hai xuất hiện trong **Java 11**, tiếp tục được hỗ trợ trên các JDK hiện đại và không phụ thuộc thư viện HTTP bên thứ ba.

## 1. Mục tiêu và bức tranh tổng thể

Sau bài này, bạn có thể:

1. Chọn chính xác `HttpResponse.BodyHandlers.ofByteArray()` hoặc `HttpResponse.BodyHandlers.discarding()` theo mục đích đọc response.
2. Hiểu ý nghĩa kiểu `HttpResponse<byte[]>` so với `HttpResponse<Void>` và giá trị của `response.body()`.
3. Biết khi nào `HttpClient.send` trả về: với hai handler này, dữ liệu response đã được xử lý xong trước khi có kết quả bình thường.
4. Phân biệt **response body rỗng**, **response body bị loại bỏ**, và **HTTP status lỗi** như `404`.
5. Thử GET đến HTTP server cục bộ, kiểm mã `200`, `404`, `204` mà không cần Internet.
6. Phân tích khác biệt về **RAM, băng thông và xử lý byte**; tránh dùng `ofByteArray()` cho nội dung rất lớn/không đáng tin.
7. Xử lý timeout, I/O, interrupt, charset, content length và resource lifecycle hợp lý.
8. Viết test có assert rõ ràng thay vì chỉ kiểm lệnh `send` không ném ngoại lệ.

Một lời gọi đồng bộ điển hình có dạng:

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());
~~~

Còn khi không muốn giữ body:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding());
~~~

Đây là **hai đoạn minh họa** trong một phương thức đã có `client`, `request` và xử lý `IOException`, `InterruptedException`; chúng không phải chương trình độc lập.

**Điểm giống nhau:** Dù dùng handler nào, bạn vẫn có `statusCode()`, `headers()`, `uri()`, `version()` và `request()` của phản hồi. Điểm khác nhau lớn nhất là **giá trị `body()` được giữ lại**.

## 2. Đọc hợp đồng API: BodyHandler, BodySubscriber và HttpResponse<T>

Trong Java 11, `HttpClient` cung cấp:

~~~java
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;
~~~

Đây là chữ ký **rút gọn để giải thích API**, không phải phương thức cần tự khai báo trong chương trình.

Khi client nhận được response status và headers, `BodyHandler<T>` quyết định `BodySubscriber<T>` sẽ tiêu thụ nội dung thân phản hồi thế nào. Sau đó `HttpResponse<T>` chứa thông tin phản hồi cùng `T` tương ứng.

Hai factory method:

~~~java
// Trả BodyHandler<byte[]>: lưu nội dung vào mảng byte.
HttpResponse.BodyHandlers.ofByteArray();

// Trả BodyHandler<Void>: tiêu thụ rồi bỏ nội dung.
HttpResponse.BodyHandlers.discarding();
~~~

- **`ofByteArray()`** tạo subscriber thu thập body thành `byte[]`. Khi `send` trả bình thường với handler này, mảng byte đã có toàn bộ body mà handler nhận được.
- **`discarding()`** tạo subscriber không giữ nội dung body và hoàn thành với kết quả kiểu `Void`. Trong việc sử dụng thông thường, `response.body()` trả **`null`**.
- **`HttpResponse<T>`** vẫn cho biết mã HTTP và headers **bất kể** handler có giữ body hay không.
- Các handler dựng sẵn này **không tự phân loại status** là 2xx, 4xx hay 5xx để thay đổi cách xử lý. Chúng chấp nhận body theo handler được chỉ định; ứng dụng kiểm `statusCode()` riêng.
- Khác với handler trả `InputStream`, hai handler trên **không trả một luồng body còn phải tự đọc** cho caller. Một lời gọi `send` sử dụng chúng hoàn tất việc tiêu thụ/loại bỏ thân phản hồi trước khi trả kết quả thành công.

### Kiểu generic quan trọng thế nào?

| Handler | Kiểu kết quả của `send` | `response.body()` | Mục đích chính |
| --- | --- | --- | --- |
| `BodyHandlers.ofByteArray()` | `HttpResponse<byte[]>` | Mảng `byte[]` chứa body | Đọc nội dung byte để xử lý |
| `BodyHandlers.discarding()` | `HttpResponse<Void>` | `null` theo hành vi subscriber bỏ body | Chỉ cần status/headers, không giữ dữ liệu |
| `BodyHandlers.ofString(charset)` | `HttpResponse<String>` | Chuỗi đã giải mã | Văn bản nhỏ và biết charset |
| `BodyHandlers.ofInputStream()` | `HttpResponse<InputStream>` | Luồng để caller đọc/đóng | Streaming và giới hạn byte |
| `BodyHandlers.ofFile(path)` | `HttpResponse<Path>` | Đường dẫn file đích | Lưu body ra đĩa |

Không thể làm:

~~~java
// Sai kiểu generic:
HttpResponse<String> r = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());
~~~

Vì `ofByteArray` tạo `BodyHandler<byte[]>` chứ không tạo `BodyHandler<String>`. Type-safety giúp phát hiện nhầm kiểu ngay khi biên dịch.

## 3. Khi nào nên dùng ofByteArray()?

Dùng `ofByteArray()` khi **phải xử lý dữ liệu phản hồi** và có thể giữ toàn bộ nội dung trong bộ nhớ một cách an toàn, ví dụ:

- Tệp nhị phân **nhỏ**: ảnh thumbnail, chữ ký số, tài liệu có ngưỡng kích thước nghiêm ngặt.
- Dữ liệu cần tính checksum/hash sau khi nhận xong.
- Nội dung văn bản **nhỏ** mà muốn chủ động chọn charset để chuyển từ byte sang `String`.
- Gọi một API có response nhỏ, muốn lưu lại toàn bộ byte để phân tích giao thức riêng.
- Bài kiểm thử muốn so sánh chính xác các byte do server trả về.

Ví dụ từ một method đã có `client` và `request`:

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

int status = response.statusCode();
byte[] content = response.body();

if (status >= 200 && status < 300) {
    // Chỉ parse khi đúng hợp đồng API.
    System.out.println("Received bytes: " + content.length);
} else {
    System.err.println("HTTP status: " + status);
}
~~~

Điểm cần nhớ:

- `content.length` là **số byte**, không phải số ký tự Unicode.
- Với dữ liệu hợp lệ, `byte[]` chứa body **sau khi Java HTTP Client đã xử lý tầng HTTP cần thiết**. Không dùng mảng này làm bằng chứng rằng ta có raw wire bytes y hệt trên socket, chẳng hạn HTTP framing/chunk metadata.
- `ofByteArray` không xem xét MIME type hoặc `Content-Type` để tự chuyển thành object JSON. Muốn parse JSON, cần parser và schema phù hợp.
- `ofByteArray` **không áp đặt một giới hạn kích thước có thể cấu hình bằng tham số**. Nếu server gửi body lớn, client có thể tích lũy nhiều dữ liệu trong heap.
- `byte[]` đã nhận thuộc về caller để xử lý; không cần `close()` cho chính mảng byte. Nhưng giữ tham chiếu quá lâu vẫn khiến dữ liệu tiếp tục chiếm bộ nhớ.

**Không đọc body của nguồn không đáng tin một cách vô hạn rồi mới kiểm `body.length`.** Đến khi `send` trả về, mảng lớn có thể đã được cấp phát. Việc kiểm kích thước **sau khi đọc xong** hữu ích cho validation nhưng không phải biện pháp chặn tăng RAM kịp thời.

## 4. Khi nào nên dùng discarding()?

Dùng `discarding()` khi **thân phản hồi không cần cho quyết định tiếp theo**, ví dụ:

- Kiểm tra endpoint có phản hồi và lấy mã status.
- Lấy một header do server trả về, không cần nội dung.
- Gọi API mà chỉ cần biết thành công/thất bại qua status và không cần body.
- Response chứa thông tin không cần giữ lại trong RAM hoặc đưa vào log.
- Những request kiểu `HEAD`, khi response theo giao thức không có body.

Ví dụ:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding());

int status = response.statusCode();
String traceId = response.headers()
        .firstValue("X-Request-Id")
        .orElse("(missing)");

System.out.println("status=" + status);
System.out.println("requestId=" + traceId);
System.out.println("bodyIsNull=" + (response.body() == null));
~~~

**Đoạn mã minh họa**: cần `client`, `request`, import và xử lý exception; giá trị `X-Request-Id` phụ thuộc server.

### discarding() có làm server ngừng gửi body không?

**Không.** `discarding()` nói rằng **client không giữ body dưới dạng đối tượng kết quả**. Nó **không** biến GET thành HEAD, không làm server tự biết bạn không cần dữ liệu, và **không cam kết tiết kiệm băng thông**.

Cụ thể:

- Server có thể vẫn gửi toàn bộ body theo HTTP; phía client nhận các byte rồi bỏ đi.
- `discarding()` tiết kiệm **bộ nhớ tích lũy body** so với `ofByteArray()`, nhưng **không đồng nghĩa** chi phí mạng, thời gian hoặc CPU bằng không.
- Với request GET đến file rất lớn, discarding vẫn có thể phải nhận lượng dữ liệu mạng lớn trước khi `send` hoàn tất. Nếu không cần body, cân nhắc **HEAD** khi endpoint hỗ trợ và khi ngữ nghĩa phù hợp.
- Nếu chỉ muốn dừng hẳn việc tải một phần cụ thể, cần cơ chế hủy/cancel hoặc chiến lược request riêng; đừng coi discarding như thao tác cancel.

### Void và null khác byte[0]

- `HttpResponse<Void>` là kiểu đúng cho discarding; `body() == null` là giá trị thông thường.
- `HttpResponse<byte[]>` từ `ofByteArray()` có thể chứa mảng **độ dài 0** khi response không có body, ví dụ status 204.
- **`null` và `new byte[0]` không phải cùng ý nghĩa** trong Java. Vì thế không gọi `response.body().length` trên kết quả discarding.

## 5. Chương trình Java 11+ hoàn chỉnh: so sánh cả hai handler

Ví dụ này khởi tạo **HTTP server cục bộ** trên `127.0.0.1`, dùng cổng do hệ điều hành cấp, sau đó gửi GET qua `HttpClient`. Nó không cần DNS, Internet hoặc API bên ngoài nên có thể chạy/kiểm thử lặp lại.

Server mô phỏng ba nhánh:

- `/data` → `200` và thân phản hồi văn bản `Hello Java`.
- `/missing` → `404` cùng body `Not found`.
- `/empty` → `204 No Content`, không có body.

Tạo tệp **`ResponseBodyHandlersDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class ResponseBodyHandlersDemo {
    static HttpRequest request(String base, String path) {
        return HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();

                int code = "/data".equals(path)
                        ? 200
                        : "/empty".equals(path) ? 204 : 404;

                byte[] bytes = (
                        code == 200 ? "Hello Java" : "Not found"
                ).getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=UTF-8");

                if (code == 204) {
                    exchange.sendResponseHeaders(204, -1);
                } else {
                    exchange.sendResponseHeaders(code, bytes.length);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write(bytes);
                    }
                }
            } finally {
                exchange.close();
            }
        });

        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            // A. Giữ body thành byte[].
            HttpResponse<byte[]> full = client.send(
                    request(base, "/data"),
                    HttpResponse.BodyHandlers.ofByteArray());

            System.out.println(
                    "data.status=" + full.statusCode());
            System.out.println(
                    "data.bytes=" + full.body().length);
            System.out.println(
                    "data.text=" + new String(
                            full.body(), StandardCharsets.UTF_8));

            // B. Bỏ body: chỉ giữ status/headers và metadata.
            HttpResponse<Void> ignored = client.send(
                    request(base, "/data"),
                    HttpResponse.BodyHandlers.discarding());

            System.out.println(
                    "discard.status=" + ignored.statusCode());
            System.out.println(
                    "discard.bodyIsNull="
                            + (ignored.body() == null));

            // C. HTTP 404 vẫn là một response HTTP có thể đọc body.
            HttpResponse<byte[]> missing = client.send(
                    request(base, "/missing"),
                    HttpResponse.BodyHandlers.ofByteArray());

            System.out.println(
                    "missing.status=" + missing.statusCode());
            System.out.println(
                    "missing.text=" + new String(
                            missing.body(), StandardCharsets.UTF_8));

            // D. HTTP 204 không chứa body.
            HttpResponse<byte[]> empty = client.send(
                    request(base, "/empty"),
                    HttpResponse.BodyHandlers.ofByteArray());

            System.out.println(
                    "empty.status=" + empty.statusCode());
            System.out.println(
                    "empty.bytes=" + empty.body().length);
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Biên dịch và chạy

JDK đầy đủ có module `jdk.httpserver` dùng riêng để **dựng server test**. Mã phía client chỉ dùng module tiêu chuẩn `java.net.http`. Bạn có thể chạy bằng:

~~~bash
javac --add-modules jdk.httpserver ResponseBodyHandlersDemo.java
java --add-modules jdk.httpserver ResponseBodyHandlersDemo
~~~

**Stdout đã đối chiếu với chương trình chạy trên JDK:**

~~~text
data.status=200
data.bytes=10
data.text=Hello Java
discard.status=200
discard.bodyIsNull=true
missing.status=404
missing.text=Not found
empty.status=204
empty.bytes=0
~~~

### Phân tích từng kết quả

1. `"Hello Java"` có **10 ký tự ASCII và 10 byte UTF-8**, nên `full.body().length == 10`; `new String(..., UTF_8)` tạo lại đúng chuỗi.
2. Cùng endpoint `/data` được gọi lần hai bằng `discarding()`. Lần này status vẫn là **200** nhưng `body()` là **null** vì subscriber không lưu thân phản hồi.
3. `/missing` trả **404** và body `Not found`. `ofByteArray()` vẫn thu thập byte của body lỗi; `send` không tự ném exception chỉ vì 404.
4. `/empty` trả **204 No Content**; với `ofByteArray()` thì body có **0 byte**. Đây là phản hồi hoàn tất nhưng không chứa nội dung, khác với body `null` do discarding.
5. `HttpClient` được tái sử dụng cho các request; `server.stop(0)` chạy trong `finally`. Ví dụ dùng `throws Exception` để phần trình diễn gọn; trong ứng dụng thực tế nên xử lý `IOException` và `InterruptedException` theo tầng.
6. `HttpClient.Version.HTTP_1_1` chỉ nhằm khiến fixture HTTP server nhỏ tương thích/dễ dự đoán. Ứng dụng thật có thể dùng HTTP/2 khi cả client và server hỗ trợ.

**Lưu ý:** `com.sun.net.httpserver.HttpServer` nằm trong module JDK `jdk.httpserver`, phục vụ minh họa/test, không phải một phần của `java.net.http.HttpClient`. Nếu runtime đã bị cắt bỏ module này, demo không chạy cho tới khi module được cung cấp. Trong production, server HTTP thường được quản lý bằng framework/cấu hình triển khai chuyên dụng.

## 6. Status, headers và body là ba thông tin độc lập

Hai handler không quyết định request thành công theo nghiệp vụ. Người gọi phải kiểm HTTP status:

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    processBytes(response.body());
} else {
    reportFailure(response.statusCode());
}
~~~

**Đây là đoạn mã minh họa**, không chạy độc lập: `processBytes` và `reportFailure` là các helper giả định; cần khai báo `client`, `request` và xử lý exceptions.

Với `discarding()`:

~~~java
HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());

if (response.statusCode() == 204) {
    System.out.println("No Content");
} else if (response.statusCode() >= 400) {
    System.err.println("HTTP status=" + response.statusCode());
}
~~~

Bạn vẫn nhận được metadata ngay cả khi không giữ body:

| Thông tin | Cả hai handler có giữ được không? | Ghi chú |
| --- | --- | --- |
| `statusCode()` | **Có** | Phân loại 2xx, 3xx, 4xx, 5xx theo API đích |
| `headers()` | **Có** | Lấy qua `firstValue`/`allValues`, không giả định header nào cũng có |
| `uri()` | **Có** | Có thể khác request URI nếu client cho phép redirect |
| `version()` | **Có** | Phiên bản HTTP thực tế |
| `request()` | **Có** | Request tương ứng |
| Body dưới dạng `byte[]` | **Chỉ ofByteArray()** | Chỉ nên dùng khi payload đủ nhỏ |
| Không giữ body trong response | **discarding()** | Body dạng `Void`, thông thường `null` |

### 6.1. Phản hồi lỗi vẫn có thể có body

Server có thể trả:

~~~text
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error":"item_not_found"}
~~~

Đoạn trên là **mẫu minh họa phản hồi HTTP**, không phải kết quả cố định của chương trình ở mục 5.

- `ofByteArray()`: body chứa byte biểu diễn JSON lỗi; application có thể giải mã/parsing sau khi kiểm status.
- `discarding()`: vẫn thấy `404` và headers, nhưng **không còn nội dung lỗi** để hiển thị hoặc parse.
- Cả hai đều **không tự ném `IOException` chỉ vì status=404`**. Ngoại lệ `IOException` biểu thị lỗi I/O thực sự hoặc vấn đề trong quá trình xử lý phản hồi.

**Chọn handler theo nhu cầu chẩn đoán:** nếu hệ thống cần body lỗi từ API, dùng một handler giữ body **với cap thích hợp**, hoặc tự chọn subscriber dựa trên status. Đừng gọi `discarding` rồi cố parse body từ `response.body()` sau đó.

### 6.2. 204 và 304: không có body theo ngữ nghĩa giao thức

Một response `204 No Content` không có body. `304 Not Modified` cũng là status không có response content theo HTTP semantics. Với `ofByteArray` trên response bình thường không chứa body, mảng byte rỗng là kết quả phù hợp. Trong demo, `204` cho `empty.body().length == 0`.

**Không đánh đồng** response trống với failure: `204` có thể là kết quả thành công. Ngược lại, một `200` có body rỗng có thể hợp lệ hoặc bất thường tùy hợp đồng endpoint.

### 6.3. HEAD khác với GET + discarding

`HEAD` yêu cầu server chỉ trả metadata/headers như một GET tương ứng mà **không** có nội dung response. `GET` với `BodyHandlers.discarding()` vẫn là GET, server có thể truyền body bình thường và client bỏ đi.

Nếu chỉ cần `Content-Length`, `ETag`, `Last-Modified` hoặc kiểm tra metadata mà endpoint hỗ trợ HEAD đúng cách, có thể dùng:

~~~java
HttpRequest head = HttpRequest.newBuilder(
        URI.create("https://example.com/resource"))
        .method("HEAD", HttpRequest.BodyPublishers.noBody())
        .build();

HttpResponse<Void> response = client.send(
        head, HttpResponse.BodyHandlers.discarding());
~~~

Đây là **mã minh họa**, cần import và client đã tạo. Một số endpoint không hỗ trợ HEAD, và headers như `Content-Length` có thể thiếu hoặc không đại diện đúng payload sau biến đổi; đừng dùng header như một bảo đảm duy nhất về kích thước nhận được.

## 7. Byte, charset và phân biệt dữ liệu văn bản với nhị phân

`ofByteArray()` trả byte thô của **HTTP response body được nhận**, không tự giải mã văn bản. Nếu server trả UTF-8:

~~~java
byte[] bytes = response.body();
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa. Phải chọn charset theo hợp đồng server hoặc header `Content-Type` đã xác thực; `ofByteArray()` không tự áp dụng `Content-Type: charset=...`.

### 7.1. Không phải một ký tự bằng một byte

Với chuỗi `"Chào"`, Java `String.length()` là **4 đơn vị UTF-16**, nhưng encoding UTF-8 dùng **5 byte**, vì `à` được mã hóa thành hai byte. Vì thế:

~~~java
byte[] data = "Chào".getBytes(StandardCharsets.UTF_8);
System.out.println(data.length); // 5
~~~

Đây là đoạn minh họa trong một method có import `StandardCharsets`. Khi muốn đếm kích thước body, dùng `byte[].length` chứ không dùng `String.length()`. Dữ liệu emoji hoặc ký tự ngoài BMP còn có sự khác biệt giữa UTF-16 code unit, Unicode code point và số byte.

### 7.2. Byte của ảnh/file không nên chuyển sang String tùy ý

Với body là PNG, PDF, ZIP hoặc định dạng binary khác:

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());
byte[] binary = response.body();

// Sử dụng binary để kiểm magic bytes / checksum / ghi file,
// không gọi new String(binary, UTF_8) một cách tùy ý.
~~~

Đoạn trên chưa là chương trình độc lập và giả định payload đã được kiểm kích thước.

Chuyển binary sang String bằng charset bất kỳ rồi mã hóa lại có thể **thay đổi byte**, khiến checksum sai hoặc file hỏng. Nếu cần lưu file lớn, cân nhắc `BodyHandlers.ofFile(path)` thay vì giữ `byte[]`.

### 7.3. Cấp phát bộ nhớ khi giải mã

Sau khi `ofByteArray()` trả về, `new String(bytes, charset)` thường tạo một biểu diễn chuỗi bổ sung. Trong thời điểm cả mảng byte lẫn chuỗi cùng tồn tại, bộ nhớ sử dụng cao hơn chỉ riêng kích thước file. Đây là lý do không mặc định dùng `ofByteArray` rồi `new String` cho mọi response JSON/text, nhất là khi kết quả có thể lớn.

Nếu chỉ cần text nhỏ và charset rõ, `BodyHandlers.ofString(StandardCharsets.UTF_8)` cho `HttpResponse<String>` trực tiếp.

## 8. Giới hạn bộ nhớ: yếu tố quyết định khi chọn handler

**`ofByteArray` giữ toàn bộ body trong heap.** Với response 50 MiB, bạn có thể có mảng `byte[]` xấp xỉ 50 MiB, chưa kể buffer trung gian, vùng nhớ của Java HTTP Client, chuỗi tạo thêm, parser, các request khác và chi phí JVM.

Bảng so sánh chi phí:

| Yếu tố | `ofByteArray()` | `discarding()` |
| --- | --- | --- |
| Lưu toàn bộ body trong kết quả | Có | Không |
| Lấy được nội dung để parse/kiểm tra | Có | Không |
| Cần bộ nhớ tỉ lệ kích thước body | Có, có thể rất lớn | Không cần tích lũy body vào kết quả |
| Có thể vẫn nhận nhiều byte qua mạng | Có | **Có** |
| Giữ status và headers | Có | Có |
| Phù hợp response lớn không cần body | Không | Thường phù hợp nếu vẫn chấp nhận chi phí truyền body |
| Phù hợp response lớn *cần* xử lý | Không nên | Không vì bỏ dữ liệu; cân nhắc streaming/file |

### 8.1. Content-Length không phải cơ chế giới hạn đủ mạnh

Một phép kiểm header:

~~~java
long claimed = response.headers()
        .firstValueAsLong("Content-Length")
        .orElse(-1L);
~~~

chỉ đọc **con số do server công bố**, nếu có. Giá trị này có thể thiếu hoặc khác dữ liệu thực tế do encoding/đường truyền/bất nhất của nguồn. Kiểm `Content-Length` có thể hữu ích để từ chối sớm nhưng **không thay thế việc giới hạn số byte thực nhận trong quá trình xử lý**.

Quan trọng hơn: với `ofByteArray()`, đến lúc bạn có `HttpResponse<byte[]> response` thì body **đã được tích lũy trong RAM**. Kiểm `response.body().length > maxBytes` ở thời điểm đó **quá muộn để ngăn cấp phát**.

### 8.2. Nếu response lớn và vẫn cần xử lý

Thay vì mặc định dùng `ofByteArray`:

- `BodyHandlers.ofInputStream()` cho phép tự đọc theo chunk, đếm byte và đóng stream khi vượt cap. Đọc streaming **có thể chặn** khi dữ liệu chưa đến và phải dùng `try-with-resources`.
- `BodyHandlers.ofFile(Path)` ghi body ra file thay vì tạo một mảng lớn trong heap; ứng dụng vẫn cần kiểm đĩa trống, định dạng, quyền ghi, kích thước và cleanup.
- Một `BodyHandler/BodySubscriber` tùy chỉnh có thể áp chính sách ngay khi xử lý body, nhưng cần hiểu rõ `Flow.Subscription`, backpressure và cancellation.
- Giới hạn request đồng thời, timeout và kích thước sau giải nén/parse; chỉ cap file/byte chưa đủ bảo vệ CPU và bộ nhớ của parser.

Minh họa cách nhận stream (trong method có `client`, `request` và xử lý ngoại lệ):

~~~java
HttpResponse<java.io.InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (java.io.InputStream stream = response.body()) {
    byte[] buffer = new byte[8192];
    long total = 0;
    long maxBytes = 1024L * 1024L;

    while (true) {
        long remaining = maxBytes - total;
        int wanted = (int) Math.min(buffer.length,
                remaining > 0 ? remaining : 1L);
        int n = stream.read(buffer, 0, wanted);

        if (n == -1) {
            break;
        }
        if (n == 0) {
            throw new java.io.IOException("Stream made no progress");
        }
        if (n > remaining) {
            throw new java.io.IOException("Response body too large");
        }

        total += n;
        // Xử lý buffer[0..n), không tích lũy toàn bộ body.
    }
}
~~~

**Đây là đoạn minh họa, không phải chương trình độc lập**. Nó dùng bộ đệm cố định và thử thêm 1 byte khi đã đạt cap để phát hiện response dài hơn cap. Trong ứng dụng thực, cần chính sách thời gian/hủy, cleanup dữ liệu đã ghi và giới hạn các tầng parser. Đoạn `stream.read(...)` có thể chặn; cấu hình timeout/deadline phải phù hợp loại BodyHandler và môi trường.

### 8.3. Khi nhiều request cùng chạy

Nếu đồng thời có 20 response, mỗi response cần tích lũy 10 MiB, chỉ các mảng kết quả đã khoảng **200 MiB**, chưa tính buffer trung gian, parser và ứng dụng. Vì vậy giới hạn theo request cần đi cùng:

- Ngưỡng body tối đa tin cậy;
- Số lượng request đồng thời;
- Timeout và hủy tác vụ;
- Xử lý theo luồng khi dữ liệu lớn;
- Metrics về peak heap, số request lỗi và kích thước body.

`discarding()` bỏ chi phí lưu toàn bộ body vào mảng kết quả nhưng vẫn có chi phí mạng, buffer I/O và tài nguyên kết nối. Đừng xem nó là công cụ chống mọi dạng quá tải.

## 9. Timeout, ngoại lệ và cách xử lý đúng

Cả hai handler được dùng với `HttpClient.send(...)` hoặc `sendAsync(...)`. Việc chọn handler **không thay thế** chính sách timeout và lỗi.

Một cách tạo client và request:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/resource"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

Đây là **mã minh họa**, không có kết quả cố định nếu kết nối dịch vụ thật.

- `connectTimeout` liên quan thời gian tạo **kết nối mới**, không phải deadline duy nhất của toàn bộ request.
- `HttpRequest.timeout` giới hạn thời gian nhận phản hồi theo hợp đồng request; ứng dụng vẫn phải cân nhắc body handler dạng streaming và timeout tầng mạng.
- `send` khai báo `IOException` và `InterruptedException`. `HttpTimeoutException` là một dạng `IOException`.
- Khi `send` nhận `404` hay `500` như một HTTP response hợp lệ, nó **không tự ném IOException chỉ vì status**.
- Nếu đã bắt `InterruptedException` mà không truyền tiếp, thông thường cần khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` rồi dừng tác vụ.

Ví dụ xử lý ở tầng ứng dụng:

~~~java
try {
    HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding());

    if (response.statusCode() >= 200
            && response.statusCode() < 300) {
        System.out.println("HTTP success");
    } else {
        System.err.println("HTTP status=" + response.statusCode());
    }
} catch (java.net.http.HttpTimeoutException ex) {
    System.err.println("Request timed out");
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    System.err.println("Request interrupted");
} catch (java.io.IOException ex) {
    System.err.println("Network or I/O error");
}
~~~

**Mã minh họa**: đặt trong method có biến `client` và `request`. Nó không cần đọc body, nhưng vẫn xử lý status. Trật tự catch đúng vì `HttpTimeoutException` là lớp con của `IOException`.

### Ngoại lệ không phụ thuộc handler mà chỉ phụ thuộc thành công request

| Trường hợp | Có thể xảy ra | Cách hiểu |
| --- | --- | --- |
| HTTP 200/204 | `send` trả response | Kiểm điều kiện nghiệp vụ; body có thể rỗng |
| HTTP 404/500 | `send` trả response | Không tự coi là lỗi I/O; đọc `statusCode()` |
| DNS/TCP/TLS thất bại | `IOException`/lớp con | Không có HTTP response hoàn chỉnh để xử lý |
| Request timeout | `HttpTimeoutException`/lớp con | Deadline hết; không bảo đảm server chưa xử lý |
| Thread bị interrupt | `InterruptedException` | Xử lý hủy hoặc truyền lên |
| Body handler/stream xử lý lỗi | Có thể kết thúc bất thường | Giữ nguyên nguyên nhân, dọn tài nguyên liên quan |

**Chú ý:** Timeout sau khi gửi POST không chứng minh server chưa xử lý nội dung. Không retry mù request thay đổi dữ liệu nếu chưa có idempotency policy.

## 10. So sánh với những handler khác của Java 11

Mặc dù bài này tập trung vào hai handler, việc nắm ranh giới giúp chọn đúng:

| Handler | `HttpResponse<T>` | Khi dùng |
| --- | --- | --- |
| `ofByteArray()` | `HttpResponse<byte[]>` | Cần byte, kích thước nhỏ và đã được giới hạn |
| `discarding()` | `HttpResponse<Void>` | Chỉ cần status/headers, không quan tâm body |
| `ofString()` / `ofString(charset)` | `HttpResponse<String>` | Text nhỏ, charset xác định; có thể xử lý `Content-Type` |
| `ofFile(path)` | `HttpResponse<Path>` | Tải body ra file, tránh mảng lớn trong heap |
| `ofInputStream()` | `HttpResponse<InputStream>` | Streaming, byte limit, caller đọc và đóng |
| `ofLines()` | `HttpResponse<Stream<String>>` | Xử lý chuỗi theo dòng; quản lý stream |
| `replacing(U value)` | `HttpResponse<U>` | Bỏ body và thay bằng một giá trị caller chọn |

Đặc biệt, `discarding()` **không có tham số** và trả body `Void`. Nếu cần bỏ body nhưng muốn response chứa một giá trị hằng, `replacing(value)` là handler khác đã có từ Java 11. Không giả định `replacing` có thể biến body thành dữ liệu thật; nó **chỉ thay giá trị kết quả sau khi loại bỏ byte**.

### Chọn handler sau khi nhận status?

`HttpResponse.BodyHandler<T>` là functional interface: khi được gọi, nó nhìn thấy `HttpResponse.ResponseInfo` chứa status và headers **trước khi body được nhận**. Điều này cho phép application tự chọn `BodySubscriber` dựa trên HTTP status.

Ví dụ sau giữ byte với status 2xx, còn với các status khác **bỏ body và trả mảng rỗng**:

~~~java
HttpResponse.BodyHandler<byte[]> handler = info -> {
    int status = info.statusCode();

    if (status >= 200 && status < 300) {
        return HttpResponse.BodySubscribers.ofByteArray();
    }
    return HttpResponse.BodySubscribers.replacing(new byte[0]);
};

HttpResponse<byte[]> response = client.send(request, handler);
~~~

**Đoạn minh họa** nằm trong method có `client` và `request`, cần xử lý exceptions. Quan trọng: đây không phải cơ chế giới hạn RAM cho body **2xx**, vì nhánh thành công vẫn tích lũy toàn bộ dữ liệu; và body rỗng ở nhánh lỗi **không có nghĩa** server không gửi nội dung lỗi. Ứng dụng phải kiểm status trước khi diễn giải mảng kết quả.

Nếu chỉ cần status/headers ở tất cả trường hợp, `discarding()` đơn giản và rõ ý hơn nhiều so với custom handler.

## 11. Kiểm thử đúng kết quả của từng handler

Dù demo ở mục 5 đã chạy được, trong một test suite thực tế nên **assert** hành vi chứ không chỉ nhìn console.

### Ma trận test trọng tâm

| Tình huống | Handler | Kỳ vọng |
| --- | --- | --- |
| HTTP 200, body `Hello Java` | `ofByteArray` | `statusCode()==200`, `body().length==10`, decode UTF-8 đúng |
| HTTP 200, cùng body | `discarding` | `statusCode()==200`, `body()==null` |
| HTTP 404, body `Not found` | `ofByteArray` | `statusCode()==404`, vẫn có byte của body lỗi |
| HTTP 404, body `Not found` | `discarding` | `statusCode()==404`, `body()==null` |
| HTTP 204, không body | `ofByteArray` | `statusCode()==204`, `body().length==0` |
| HTTP 204, không body | `discarding` | `statusCode()==204`, `body()==null` |
| Body là UTF-8 có dấu | `ofByteArray` | So sánh byte hoặc decode bằng cùng charset; không dùng số ký tự làm kích thước |
| Body nhị phân | `ofByteArray` | So sánh byte nguyên bản, không decode tùy tiện |
| Header bất kỳ được server trả | Cả hai | `headers()` vẫn đọc được |
| Server trả 500 | Cả hai | Response HTTP vẫn có status; không mặc định có IOException |
| Server đóng kết nối bất thường | Cả hai | Có thể có lỗi I/O |
| Body rất lớn | `ofByteArray` | Không dùng trong test stress vô hạn; kiểm phương án streaming/cap thay thế |

### Cách viết assertion không phụ thuộc Internet

Với server loopback có dữ liệu cố định như demo:

~~~java
// Minh họa các assertion bên trong test method.
if (full.statusCode() != 200 || full.body().length != 10) {
    throw new AssertionError("Wrong byte[] response");
}

if (ignored.statusCode() != 200 || ignored.body() != null) {
    throw new AssertionError("Wrong discarding response");
}

if (empty.statusCode() != 204 || empty.body().length != 0) {
    throw new AssertionError("Wrong empty response");
}
~~~

Đây là **đoạn mã minh họa** với các biến `full`, `ignored`, `empty` được tạo trong demo; nó không phải một chương trình riêng. Trong JUnit, có thể dùng `assertEquals`, `assertArrayEquals`, `assertNull` và `assertTrue`; nhớ khai báo dependency/test runner chứ không giả định JUnit là thành phần Java SE.

Ưu tiên test dùng dữ liệu cố định trong tiến trình thay vì gọi endpoint công khai: kết quả ổn định, không phụ thuộc DNS, TLS hay rate limit. Test E2E với server thật nên là một lớp riêng.

## 12. Các lỗi phổ biến và cách tránh

| Nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “`ofByteArray()` trả `String`.” | Sai kiểu generic / giải mã sai | Nó trả `byte[]`; decode riêng nếu là text |
| “`discarding()` trả mảng byte rỗng.” | Có thể gọi `.length` trên `null` | Dùng `HttpResponse<Void>`; `body() == null` |
| “`discarding()` tiết kiệm cả băng thông.” | Server vẫn có thể gửi body lớn | Nếu không cần body, cân nhắc HEAD hoặc thay hợp đồng API |
| “`ofByteArray()` chỉ đọc tối đa Content-Length.” | Dễ chấp nhận dữ liệu khổng lồ trong RAM | Có cap khi streaming; không tin tuyệt đối header |
| “`ofByteArray()` tự parse JSON theo Content-Type.” | Không có object JSON như kỳ vọng | Parse theo schema sau khi nhận byte, với giới hạn |
| “HTTP 404 làm `send` luôn ném IOException.” | Không đọc được response lỗi | Kiểm `statusCode()` và body theo nhu cầu |
| “HTTP 204 phải có body null với mọi handler.” | Nhầm empty byte array với null | `ofByteArray` có `byte[0]`, `discarding` có `null` |
| “Cần gọi `close()` trên `byte[]`.” | Hiểu sai resource lifecycle | Mảng không có `close`; quản lý reference và bộ nhớ |
| “Chỉ cần đổi sang discarding là request không chặn.” | `send` vẫn là đồng bộ và tiêu thụ body | Dùng `sendAsync` nếu cần API bất đồng bộ |
| “Dùng `new String(bytes)` luôn đúng.” | Dựa vào charset mặc định, dễ sai nội dung | Chỉ rõ `StandardCharsets.UTF_8` hoặc charset theo contract |
| “Client trả response thì nghiệp vụ đã thành công.” | Có thể nhận 4xx/5xx | Phân loại HTTP status trước khi xử lý |
| “File lớn cứ đọc thành `byte[]` rồi ghi xuống đĩa.” | Dùng RAM không cần thiết | Dùng `ofFile` hoặc xử lý theo stream |
| “`HEAD` và `GET + discarding` giống nhau.” | Nhầm số byte và semantics HTTP | Dùng đúng phương thức HTTP theo API |
| “`Content-Length` là kích thước luôn đúng.” | Bị sai khi thiếu/header không đáng tin | Đếm byte thực tế và đặt giới hạn |
| “Body của 404 lúc nào cũng trống.” | Bỏ lỡ thông báo lỗi hữu ích | Dựa hợp đồng server và chọn handler giữ body nếu cần |

## 13. Checklist khi code review HTTP Response

- [ ] Chọn handler dựa trên việc **có cần body hay không**, không chỉ theo thói quen.
- [ ] `HttpResponse<T>` có kiểu generic đúng: `byte[]` hoặc `Void`.
- [ ] Không dùng `body()` của discarding như thể đó là mảng/chuỗi.
- [ ] HTTP status và header được xử lý độc lập với body; đặc biệt với 204/404/500.
- [ ] Nếu giữ byte, kích thước body được giới hạn **trước/trong lúc nhận**, không chỉ sau `send`.
- [ ] Với text, charset được xác định rõ; với binary, không decode tùy ý.
- [ ] Không giả định discarding giảm băng thông hoặc thay GET bằng HEAD.
- [ ] Với response lớn cần đọc, dùng `ofInputStream` hoặc `ofFile` theo vòng đời tài nguyên.
- [ ] Có timeout, kiểm I/O, xử lý `InterruptedException` và quản lý concurrency.
- [ ] HTTP client được tái sử dụng theo cấu hình; test không cần Internet khi có thể dùng loopback.
- [ ] Mã tương thích mức Java 11 yêu cầu; không dùng API mới chỉ có trên JDK khác mà không ghi rõ.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Hai lời gọi sau cho kiểu kết quả gì?

~~~java
client.send(request, HttpResponse.BodyHandlers.ofByteArray());
client.send(request, HttpResponse.BodyHandlers.discarding());
~~~

**Đáp án:** Lời gọi đầu trả `HttpResponse<byte[]>`, lời gọi sau trả `HttpResponse<Void>`. Cả hai vẫn cho phép truy cập `statusCode()` và `headers()`.

**Câu 2.** Server gửi HTTP 200 và 8 MiB body. Dùng `discarding()` có chắc chỉ dùng 0 byte mạng không?

**Không.** Server vẫn có thể gửi toàn bộ body. Discarding loại bỏ dữ liệu thay vì giữ mảng byte kết quả; nó không phải phương thức giảm bandwidth.

**Câu 3.** Server trả HTTP 404 với JSON lỗi. `ofByteArray()` có ném exception ngay vì status không thuộc 2xx?

**Không.** Nếu việc truyền/nhận không lỗi, `send` trả `HttpResponse<byte[]>` và status là 404. Bạn có thể đọc byte lỗi, còn application quyết định có parse hay không.

**Câu 4.** Body của `HttpResponse<Void>` tạo bởi `discarding()` có thể được đọc bằng `new String(response.body())` không?

**Không.** Body là `Void` và thông thường là `null`; nội dung đã bị bỏ, không thể khôi phục từ response.

**Câu 5.** `ofByteArray()` trên response `204 No Content` trả mảng có chiều dài bao nhiêu trong demo?

**0 byte.** Response không chứa thân dữ liệu; điều này khác với việc body bị bỏ bởi discarding.

**Câu 6.** Muốn lấy metadata từ server mà không yêu cầu body, có thể cân nhắc điều gì ngoài discarding?

**Dùng HEAD** khi server hỗ trợ. Nó có ngữ nghĩa HTTP khác GET+discarding và có thể tránh việc truyền body, nhưng phải kiểm hỗ trợ endpoint.

**Câu 7.** Vì sao kiểm `response.body().length <= max` sau `send(...ofByteArray())` không đủ bảo vệ RAM?

**Vì** body đã được tích lũy thành mảng trước khi `send` trả về. Để tránh cấp phát quá lớn, phải kiểm giới hạn trong quá trình nhận với streaming/custom subscriber.

## Tài liệu chính thức — kiến thức còn áp dụng

- [Java SE 11: `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — `ofByteArray()`, `discarding()` và hành vi của các handler dựng sẵn.
- [Java SE 11: `HttpResponse`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html) — `statusCode`, `headers`, `body`, `uri`, `version`.
- [Java SE 11: `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html) — `send`, `sendAsync`, ngoại lệ và cách cấu hình client.
- [Java SE 11: `HttpResponse.BodyHandler`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html) — lựa chọn subscriber sau khi có status/headers.
- [Java SE 11: `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html) — `ofByteArray`, `discarding` và `replacing`.
- [Java SE 26: `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — các handler cốt lõi vẫn được hỗ trợ trên JDK hiện đại.
- [JDK 11: `HttpServer`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html) — HTTP server cục bộ dùng trong chương trình ví dụ.

**Ghi nhớ:** `ofByteArray()` = **giữ toàn bộ byte body trong `HttpResponse<byte[]>`**, phù hợp khi cần nội dung **đủ nhỏ**. `discarding()` = **tiêu thụ rồi bỏ body với `HttpResponse<Void>`**, phù hợp khi chỉ cần status/headers. Cả hai **không tự coi 4xx/5xx là lỗi I/O**, và discarding **không tự cắt dữ liệu truyền qua mạng**. Các nguyên tắc này đúng từ Java 11 và vẫn áp dụng trên JDK hiện đại.