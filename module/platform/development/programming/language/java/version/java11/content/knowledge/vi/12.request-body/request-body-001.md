# BodyPublishers.noBody và yêu cầu HTTP không có nội dung (Java 11)

Kể từ **Java 11**, gói chuẩn `java.net.http` cung cấp `HttpClient`, `HttpRequest`, `HttpResponse` và các `BodyPublisher` để gửi yêu cầu HTTP. Không phải request nào cũng cần payload: một lệnh GET thường chỉ truy vấn dữ liệu; một DELETE thường xác định tài nguyên qua URI; một số endpoint POST chỉ kích hoạt một hành động và không yêu cầu body. Trong trường hợp cần tạo **request với body không có nội dung**, dùng:

```java
HttpRequest.BodyPublishers.noBody()
```

Đây là factory trả về `HttpRequest.BodyPublisher` **không phát ra byte nội dung nào**. API này được giới thiệu cùng HTTP Client chuẩn của Java 11 và vẫn sử dụng được trên JDK hiện đại.

Ví dụ ngắn:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.invalid/jobs/7/trigger"))
        .POST(HttpRequest.BodyPublishers.noBody())
        .build();
```

Đây là **đoạn mã trong phương thức**, cần imports `java.net.URI` và `java.net.http.HttpRequest`. Nó tạo một request **POST không có body**; chưa gửi request ra mạng. Chỉ gửi thật khi dùng `HttpClient.send` hoặc `sendAsync`, và server phải hỗ trợ hợp đồng endpoint tương ứng.

**Phân biệt ngay từ đầu:** không có *request body* **không** có nghĩa không có URI, headers, method hay response body; cũng không có nghĩa endpoint là chỉ đọc hay an toàn để gọi lặp. `noBody()` chỉ quyết định phần **nội dung request**.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Nắm vai trò của `HttpRequest.BodyPublisher` và `BodyPublishers.noBody()`.
2. Tạo đúng các request `GET`, `DELETE`, `POST`, `PUT` và phương thức tự khai báo như `PATCH`/`HEAD` khi **hợp đồng server cho phép không có body**.
3. Hiểu vì sao `POST(noBody())` vẫn là POST và có thể thay đổi trạng thái hệ thống.
4. Phân biệt **không cung cấp publisher**, **publisher không phát byte nào**, và **publisher của chuỗi rỗng**.
5. Kiểm tra `bodyPublisher()`, `contentLength()` và hiểu giới hạn của phép kiểm tra đó.
6. Sử dụng `HttpClient` thật, xác nhận HTTP status, phân biệt request body và response body.
7. Biết khi nào đặt `Content-Type`, authorization, timeout, kiểm soát retry, và cách test không phụ thuộc mạng bên ngoài.
8. Tránh dùng những API được bổ sung sau Java 11 khi mục tiêu bài tập là tương thích Java 11.

## 2. `BodyPublisher` nằm ở đâu trong HTTP Client?

Một luồng gọi HTTP gồm ba bước:

```text
HttpRequest.Builder
     |
     +-- URI / method / headers / timeout
     |
     +-- BodyPublisher  <-- nguồn byte của REQUEST body
             |
             v
         HttpRequest
             |
             v
       HttpClient.send / sendAsync
             |
             v
        HTTP response
             |
             +-- statusCode / headers
             |
             +-- BodyHandler  <-- cách nhận RESPONSE body
```

`BodyPublisher` và `BodyHandler` phục vụ **hai hướng dữ liệu khác nhau**:

- `HttpRequest.BodyPublisher` tạo dữ liệu **đi ra**: bytes của request.
- `HttpResponse.BodyHandler<T>` hướng dẫn xử lý dữ liệu **đi vào**: ví dụ nhận `String`, `byte[]`, `InputStream` hoặc bỏ qua response body.
- `BodyPublishers.noBody()` thuộc **request**; `HttpResponse.BodyHandlers.discarding()` thuộc **response**. Hai lời gọi không thay thế cho nhau.

Theo API Java 11, `BodyPublisher` mở rộng `Flow.Publisher<ByteBuffer>`. Với body có dữ liệu, HTTP Client nhận các byte buffer từ publisher để gửi. `noBody()` là publisher hoàn thành ngay và **không cung cấp nội dung body**. Vì nó báo độ dài bằng 0, HTTP Client có thể không cần subscribe để lấy dữ liệu.

### Ý nghĩa của `contentLength()`

`HttpRequest.BodyPublisher.contentLength()` trả về số byte dự kiến:

| Giá trị | Ý nghĩa |
| --- | --- |
| `0` | Body có độ dài 0; có thể do `noBody()` hoặc một publisher rỗng khác. |
| Số dương | Biết trước độ dài body theo byte. |
| Số âm | Không biết trước độ dài body; HTTP Client lựa chọn cách gửi phù hợp. |

Với `HttpRequest.BodyPublishers.noBody()`, kết quả `contentLength()` là **0**.

**Không đồng nhất giá trị 0 với một header cụ thể trên dây.** Java API bảo đảm publisher không cung cấp payload; nó không hứa mọi JDK/protocol/server đều biểu diễn request theo cùng một chuỗi headers, chẳng hạn luôn có hoặc luôn không có `Content-Length: 0`. Đặc biệt, chi tiết truyền tải khác nhau giữa HTTP/1.1 và HTTP/2. Nếu giao thức tích hợp cần đúng dạng framing/header, kiểm tra bằng integration test với server tương ứng.

## 3. Dùng `noBody()` với phương thức nào?

`HttpRequest.Builder` trong Java 11 có các phương thức:

| Cách xây request | Có cần truyền `BodyPublisher`? | Ghi chú |
| --- | --- | --- |
| `builder.GET()` | **Không** | GET mặc định, thích hợp khi đọc tài nguyên; không cần ghi `noBody()`. |
| `builder.DELETE()` | **Không** | Shortcut DELETE thông thường không có request body. |
| `builder.POST(BodyPublishers.noBody())` | **Có** | POST được tạo nhưng không phát request payload. Chỉ phù hợp khi endpoint cho phép. |
| `builder.PUT(BodyPublishers.noBody())` | **Có** | PUT không có payload nếu hợp đồng endpoint cho phép; nhiều API PUT thực tế yêu cầu representation. |
| `builder.method("PATCH", BodyPublishers.noBody())` | **Có** | Có thể tạo phương thức tùy khai báo; PATCH thường yêu cầu tài liệu thay đổi, nên phải theo hợp đồng. |
| `builder.method("HEAD", BodyPublishers.noBody())` | **Có** | Cách tạo HEAD **tương thích Java 11**; response HEAD không chứa message body theo ngữ nghĩa HTTP. |
| `builder.method("DELETE", BodyPublishers.noBody())` | **Có** | Viết rõ publisher rỗng; thường đơn giản hơn khi dùng `DELETE()`. |

**Chi tiết tương thích:** phương thức tiện ích `HttpRequest.Builder.HEAD()` được bổ sung **sau Java 11**. Vì vậy, trong bài học yêu cầu Java 11, dùng `method("HEAD", BodyPublishers.noBody())`. Với GET và DELETE, `GET()`/`DELETE()` đã có từ Java 11 và không bắt bạn truyền publisher.

Một số method có thể bị hạn chế bởi implementation và một số URI/request không được server chấp nhận. Tạo được `HttpRequest` không đồng nghĩa server sẽ trả thành công.

### Ví dụ HTTP có tên thao tác nhưng không có body

Giả sử server định nghĩa:

```text
POST /jobs/7/retry

Request body: không có
Response: 202 Accepted
```

Client Java 11 có thể tạo:

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://api.example.invalid/jobs/7/retry"))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.noBody())
        .build();
```

Đây là đoạn mã minh họa, không phải endpoint có thể chạy được. **Job ID nằm trong URI**, còn việc server cho phép retry hay không phụ thuộc trạng thái job, phân quyền và hợp đồng API. Dù không có body, request có thể làm thay đổi dữ liệu hoặc chạy tác vụ.

## 4. Ví dụ 1 — chương trình đầy đủ kiểm tra request, không cần mạng

Để nhìn thấy khác biệt giữa các builder mà không gọi server thật, tạo tệp **`NoBodyRequestDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpRequest;

public class NoBodyRequestDemo {
    private static void describe(String label, HttpRequest request) {
        boolean hasPublisher = request.bodyPublisher().isPresent();
        String detail = hasPublisher
                ? "publisher=" + request.bodyPublisher()
                        .get().contentLength()
                : "publisher=absent";

        System.out.println(label + " method="
                + request.method() + " " + detail);
    }

    public static void main(String[] args) {
        URI uri = URI.create("https://example.invalid/items/7");

        HttpRequest get = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpRequest delete = HttpRequest.newBuilder(uri)
                .DELETE()
                .build();

        HttpRequest post = HttpRequest.newBuilder(uri)
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();

        HttpRequest put = HttpRequest.newBuilder(uri)
                .PUT(HttpRequest.BodyPublishers.noBody())
                .build();

        HttpRequest patch = HttpRequest.newBuilder(uri)
                .method("PATCH", HttpRequest.BodyPublishers.noBody())
                .build();

        HttpRequest head = HttpRequest.newBuilder(uri)
                .method("HEAD", HttpRequest.BodyPublishers.noBody())
                .build();

        describe("GET", get);
        describe("DELETE", delete);
        describe("POST", post);
        describe("PUT", put);
        describe("PATCH", patch);
        describe("HEAD", head);

        System.out.println("No-body length: " +
                HttpRequest.BodyPublishers.noBody().contentLength());
        System.out.println("Empty-string length: " +
                HttpRequest.BodyPublishers.ofString("").contentLength());
    }
}
```

Biên dịch bằng compiler vẫn hỗ trợ mức Java 11:

```sh
javac --release 11 -encoding UTF-8 NoBodyRequestDemo.java
java NoBodyRequestDemo
```

**Stdout với HTTP Client chuẩn của JDK:**

```text
GET method=GET publisher=absent
DELETE method=DELETE publisher=absent
POST method=POST publisher=0
PUT method=PUT publisher=0
PATCH method=PATCH publisher=0
HEAD method=HEAD publisher=0
No-body length: 0
Empty-string length: 0
```

Giải thích từng dòng:

1. `GET()` và `DELETE()` đặt method nhưng không yêu cầu bạn khai báo `BodyPublisher`, nên `bodyPublisher()` của request trên có thể trả `Optional.empty()`; chương trình in `publisher=absent`.
2. `POST(noBody())`, `PUT(noBody())` và `method(..., noBody())` thiết lập **một publisher cụ thể**, và publisher ấy có `contentLength() == 0`.
3. `noBody()` và `ofString("")` đều báo body dài **0 byte**. Giá trị 0 **không đủ** để kết luận chúng tạo ra các header HTTP khác nhau khi thực sự gửi request.
4. Đoạn demo **chỉ xây request, không thực hiện I/O**. Tên miền `example.invalid` cố ý không trỏ tới một API cần liên lạc, giúp bài có đầu ra cố định.

### `bodyPublisher()` là `Optional`

`HttpRequest.bodyPublisher()` có kiểu:

```java
Optional<HttpRequest.BodyPublisher>
```

Nó cho biết request có **publisher được đặt** hay không. Đây không phải cách kiểm tra server đã nhận body, HTTP client đã gửi request, hoặc một header `Content-Length` nào đã xuất hiện trên mạng. Cần tách ba câu hỏi:

- **Builder đã được gắn publisher chưa?** Kiểm tra `bodyPublisher().isPresent()`.
- **Publisher dự định phát bao nhiêu byte?** Kiểm tra `contentLength()` nếu có.
- **Server đã thực nhận request gì?** Cần tích hợp với server thử nghiệm, trace HTTP hoặc kiểm tra log phù hợp.

Đừng gọi `request.bodyPublisher().get()` khi `Optional` có thể rỗng, vì sẽ gây `NoSuchElementException`. Ví dụ phía trên kiểm tra `isPresent()` trước.

## 5. `noBody()`, `ofString("")` và `null` khác nhau thế nào?

| Biểu thức | Ý định của người viết | Độ dài publisher | Khuyến nghị |
| --- | --- | ---: | --- |
| `BodyPublishers.noBody()` | **Không có nội dung request** | 0 | Ưu tiên khi endpoint thực sự không nhận body |
| `BodyPublishers.ofString("")` | Có một **representation dạng chuỗi rỗng** | 0 | Dùng khi hợp đồng nói gửi payload chuỗi rỗng |
| `BodyPublishers.ofByteArray(new byte[0])` | Có representation nhị phân độ dài 0 | 0 | Dùng nếu semantics của payload nhị phân rỗng là điều cần biểu đạt |
| `BodyPublishers.ofString("{}")` | JSON object rỗng dưới dạng chuỗi | 2 byte UTF-8 | **Không** tương đương không có body; `{}` là dữ liệu hợp lệ |
| `BodyPublishers.ofString("null")` | Văn bản chứa từ `null` | 4 byte UTF-8 | Cũng **không** tương đương body trống |
| `POST(null)` | Không tạo được publisher hợp lệ | Không áp dụng | Không dùng; tham số publisher yêu cầu non-null |

**Chú ý giới hạn ngữ nghĩa:** ở mức HTTP message, một representation dài 0 byte và việc không phát byte payload có thể trông giống nhau trong nhiều tình huống. Sự khác biệt ở đây trước hết là **chủ ý và hợp đồng API**. Không giả định mọi server có thể phân biệt các trường hợp chỉ dựa vào phương thức Java đã tạo request. Hãy kiểm thử với hệ thống thật nếu hợp đồng cần phân biệt “body không tồn tại” và “body rỗng”.

### Vì sao không dùng `"{}"` thay cho `noBody()`?

Một API nhận `POST /tasks/7/run` với **không body** có thể từ chối request mang `{}` vì endpoint không định nghĩa một schema JSON. Ngược lại, endpoint khác lại yêu cầu JSON object hợp lệ, có thể là `{}`. Chọn publisher theo **hợp đồng endpoint**, không theo cảm giác “POST thì luôn có JSON” hoặc “POST không cần dữ liệu thì gửi `{}` cho chắc”.

Khi dùng `noBody()` mà không gửi representation, thường **không cần đặt `Content-Type: application/json`**, vì không có body JSON để mô tả. Header `Accept: application/json` vẫn có thể cần nếu bạn muốn **response** dạng JSON. Một số API có yêu cầu header đặc biệt dù body rỗng; hãy tuân theo tài liệu của chính API đó.

## 6. Ví dụ 2 — gửi HTTP POST không body đến server nội bộ

Để quan sát request thật mà không phụ thuộc dịch vụ bên ngoài, chương trình bên dưới mở một HTTP/1.1 server **chỉ trên loopback `127.0.0.1`**, nhận một request, rồi trả `204 No Content`. Server dùng API socket tiêu chuẩn Java SE; đoạn mã này là **test tối giản**, không phải HTTP server đầy đủ cho production.

Tạo tệp **`LocalNoBodyRoundTrip.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LocalNoBodyRoundTrip {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (ServerSocket listener =
                     new ServerSocket(0, 1, loopback)) {

            ExecutorService executor =
                    Executors.newSingleThreadExecutor();

            try {
                Future<String> requestLine = executor.submit(() -> {
                    try (Socket socket = listener.accept()) {
                        socket.setSoTimeout(3000);
                        BufferedReader reader = new BufferedReader(
                                new InputStreamReader(
                                        socket.getInputStream(),
                                        StandardCharsets.US_ASCII));

                        String firstLine = reader.readLine();
                        if (firstLine == null) {
                            throw new IllegalStateException(
                                    "Missing request line");
                        }

                        String line;
                        while ((line = reader.readLine()) != null
                                && !line.isEmpty()) {
                            // Consume HTTP request headers.
                        }

                        byte[] reply = (
                                "HTTP/1.1 204 No Content\r\n" +
                                "Content-Length: 0\r\n" +
                                "Connection: close\r\n" +
                                "\r\n")
                                .getBytes(StandardCharsets.US_ASCII);
                        socket.getOutputStream().write(reply);
                        socket.getOutputStream().flush();
                        return firstLine;
                    }
                });

                URI uri = URI.create(
                        "http://127.0.0.1:"
                                + listener.getLocalPort()
                                + "/tasks/7/run");

                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(3))
                        .POST(HttpRequest.BodyPublishers.noBody())
                        .build();

                HttpClient client = HttpClient.newBuilder()
                        .version(HttpClient.Version.HTTP_1_1)
                        .connectTimeout(Duration.ofSeconds(2))
                        .build();

                HttpResponse<Void> response = client.send(
                        request, HttpResponse.BodyHandlers.discarding());

                System.out.println("Method: " + request.method());
                System.out.println("Request-body bytes: " +
                        request.bodyPublisher().get().contentLength());
                System.out.println("Server saw: " +
                        requestLine.get(3, TimeUnit.SECONDS));
                System.out.println("Response status: " +
                        response.statusCode());

            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy:

```sh
javac --release 11 -encoding UTF-8 LocalNoBodyRoundTrip.java
java LocalNoBodyRoundTrip
```

**Stdout thành công khi hệ điều hành cho phép loopback HTTP:**

```text
Method: POST
Request-body bytes: 0
Server saw: POST /tasks/7/run HTTP/1.1
Response status: 204
```

Phân tích:

1. `ServerSocket(0, 1, loopback)` chọn cổng trống do OS cấp phát và chỉ lắng nghe tại địa chỉ loopback, không cần biết trước một cổng cụ thể.
2. Luồng server đọc **request line và các HTTP headers** tới dòng trống; vì đây là `POST(noBody())` nên không có body bytes để xử lý.
3. `HttpClient.Version.HTTP_1_1` được chọn để server đơn giản có thể quan sát request line chuẩn HTTP/1.1. Các phiên bản HTTP khác có framing riêng, không phù hợp với parser test rất tối giản này.
4. `request.bodyPublisher().get().contentLength()` trả 0 vì đã gắn `noBody()` cụ thể.
5. Server gửi status `204` cùng response body rỗng; client đọc bằng `BodyHandlers.discarding()` nên kiểu kết quả là `HttpResponse<Void>`.
6. Request vẫn là **POST**; server nhận đường dẫn `/tasks/7/run` và có thể áp nghiệp vụ riêng.

Chương trình không cần Internet, DNS ngoài mạng hoặc tài khoản API. Tuy vậy, các chính sách bảo mật của OS/container có thể chặn việc mở cổng loopback; khi đó chương trình có thể báo lỗi I/O thay vì in bốn dòng. Ví dụ chủ yếu minh họa ranh giới **request body** và **response body**; parser socket ở đây không xử lý chunking, TLS, nhiều request hoặc mọi trường hợp protocol, nên không sử dụng nó làm server sản xuất.

### Có thể gửi request nhưng không quan tâm response body

Trong chương trình trên:

```java
HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());
```

Điều này có nghĩa: **vẫn nhận response HTTP và status**, nhưng không giữ response body dưới dạng `String` hoặc byte array.

Nếu API trả lỗi với body chứa mã lỗi cần parse, không nên mù quáng dùng `discarding()` cho mọi status. Hãy chọn `BodyHandler` phù hợp, kiểm tra `statusCode()` và giới hạn lượng body nhận được. `noBody()` ở chiều request **không buộc** chiều response phải trống.

## 7. HTTP method và hợp đồng nghiệp vụ vẫn quan trọng

Một request không có body vẫn có **HTTP method**, **URI**, **query parameters**, **headers** và **tác dụng**. Ví dụ:

```text
GET    /items/7                 -> xem item
DELETE /items/7                 -> xóa item (nếu được phép)
POST   /jobs/7/retry            -> yêu cầu thử lại job
POST   /payments/7/capture      -> tác vụ tài chính, có side effect
HEAD   /items/7                 -> lấy metadata theo HTTP
```

Đây chỉ là **ví dụ định tuyến**, không phải chuẩn chung của mọi hệ thống.

- **GET** về mặt ngữ nghĩa HTTP là phương thức truy xuất dữ liệu. Dùng `builder.GET()` trừ khi hợp đồng có yêu cầu đặc biệt. Không dùng GET để kích hoạt side effect tùy tiện.
- **DELETE** xác định tài nguyên cần xóa qua URI; `builder.DELETE()` thuận tiện khi không có request payload. Việc DELETE có thực sự idempotent ở mức hệ thống cần được hiểu theo hợp đồng và hành vi server.
- **POST** có thể không body nhưng vẫn gọi một operation có side effect, vì vậy không tự động retry nếu chưa có cơ chế idempotency phù hợp.
- **PUT** thường gửi representation mới của tài nguyên. Dùng `PUT(noBody())` chỉ khi endpoint thực sự định nghĩa yêu cầu rỗng; có nhiều API sẽ từ chối bằng `400`, `411`, `415` hoặc `422` tùy hợp đồng.
- **PATCH** thông thường mang tài liệu cập nhật. `method("PATCH", noBody())` là cú pháp builder hợp lệ, nhưng chỉ có ý nghĩa nếu API thực sự cho phép patch không body.
- **HEAD** được định nghĩa để lấy metadata của tài nguyên mà response không có content body. Java 11 có thể gọi `method("HEAD", noBody())`; đừng nhầm với API `Builder.HEAD()` của JDK được bổ sung sau này.

**Điểm cốt lõi:** `BodyPublishers.noBody()` chỉ nói **không gửi request content**. Việc request có ý nghĩa nghiệp vụ hay bị từ chối là quyết định của server và hợp đồng tích hợp.

### Status cần được kiểm tra riêng

`HttpClient.send(...)` không tự ném `IOException` khi server trả status `400` hoặc `503`. Nó có thể trả một `HttpResponse<T>` chứa status đó. Ví dụ đoạn code trong phương thức:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

if (response.statusCode() == 204) {
    // Operation thành công, response không có content body.
} else if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    // Thành công theo hợp đồng, xử lý response nếu cần.
} else {
    // Diễn giải lỗi theo tài liệu API, không coi là IOException.
}
```

Đoạn này cần các biến `client` và `request`, imports `HttpResponse` và `StandardCharsets`, cũng như xử lý `IOException`/`InterruptedException` của `send`; **không phải chương trình độc lập**. Trạng thái `202 Accepted` có thể cho biết server mới tiếp nhận tác vụ, **chưa hoàn thành**; không tự đồng nhất mọi 2xx với kết quả cuối cùng.

## 8. Những header nào vẫn cần khi không có body?

Không có payload không đồng nghĩa bỏ mọi header. Tùy API, có thể cần:

| Header | Có thể cần khi `noBody()`? | Mục đích |
| --- | --- | --- |
| `Authorization` | **Có**, nếu endpoint yêu cầu | Chứng minh quyền gửi thao tác |
| `Accept` | **Có** | Mong muốn định dạng của **response** |
| `If-Match` | **Có** | Điều kiện precondition, hỗ trợ tránh thao tác trên phiên bản tài nguyên cũ |
| `Idempotency-Key` | **Có** nếu API hỗ trợ | Giúp server nhận diện các lần gọi lặp của một tác vụ có side effect |
| `X-Request-ID` hoặc trace ID | **Có** nếu chính sách yêu cầu | Theo dõi request xuyên hệ thống |
| `Content-Type` | Thường **không cần** khi không có representation | Mô tả kiểu media của **request body** nếu có |
| `Content-Length` | Do HTTP Client quản lý theo protocol | Không nên tự gán để “ép” body rỗng; nhiều headers bị hạn chế đặt thủ công |

Không đưa access token vào URL query nếu có thể tránh, bởi URL có thể xuất hiện trong logs, lịch sử và hệ thống giám sát. Không log toàn bộ headers có secrets. Đặt quyền truy cập và TLS theo chính sách của ứng dụng.

### `Content-Length: 0` không phải hợp đồng duy nhất

`BodyPublisher.contentLength() == 0` là thông tin bên Java. Nó **không bảo đảm** rằng raw HTTP trên dây phải luôn hiển thị chính xác một dòng `Content-Length: 0`; có thể khác theo method, protocol và implementation. Trên HTTP/2, request không được biểu diễn như một chuỗi dòng HTTP/1.1 tương đương.

Nếu server hoặc proxy có hành vi đặc biệt khi header `Content-Length` **vắng mặt** so với bằng 0, hãy viết một **integration/contract test** đo request ở phía server; không suy đoán từ `HttpRequest.bodyPublisher()`.

## 9. So sánh thêm các `BodyPublishers` đang sử dụng

| Factory | Nội dung gửi đi | Tình huống phù hợp |
| --- | --- | --- |
| **`noBody()`** | Không phát request content | Request không yêu cầu body |
| `ofString("hello")` | UTF-8 bytes của chuỗi | Text/JSON body nhỏ |
| `ofString(json, StandardCharsets.UTF_8)` | Bytes theo charset cụ thể | Tránh phụ thuộc charset mặc định |
| `ofByteArray(bytes)` | Bytes trong mảng | Payload nhị phân có sẵn |
| `ofFile(path)` | Dữ liệu từ file | Gửi file khi API cho phép, cần quản lý file/quyền truy cập |
| `ofInputStream(supplier)` | Dữ liệu đọc từ stream | Body lớn/streaming, xử lý khả năng gửi lại |
| `fromPublisher(flowPublisher)` | Nguồn dữ liệu reactive | Tích hợp pipeline `Flow.Publisher` theo hợp đồng |

Tất cả các factory trong bảng là API thuộc `HttpRequest.BodyPublishers` có thể sử dụng ở Java 11. Lựa chọn tùy **dữ liệu cần gửi** và **hợp đồng server**. `noBody()` không phải “cách rút gọn” để thay mọi publisher có dữ liệu.

**Khi nào cần `ofString("")`?** Khi endpoint yêu cầu **representation là chuỗi rỗng**. Nếu endpoint chỉ nói “không có request body”, `noBody()` rõ ý định hơn. Nếu endpoint yêu cầu một object JSON rỗng, phải gửi `{}` với media type phù hợp, không thay bằng `noBody()`.

**Khi nào không nên dùng publisher rỗng?** Khi endpoint POST/PUT/PATCH cần metadata bắt buộc trong JSON, multipart hoặc bytes nhị phân. Nếu gửi noBody, server có thể từ chối hoặc thực thi hành vi khác với dự kiến.

## 10. Dùng `noBody()` trong service và adapter

Trong ứng dụng nhiều lớp, ranh giới phổ biến là:

```text
Application service
     |
     v
Business gateway ("retryJob")
     |
     v
HTTP adapter (path, method, auth, status)
     |
     v
HttpClient + HttpRequest.BodyPublishers.noBody()
     |
     v
External API
```

Bài toán nghiệp vụ có thể gọi:

```java
retryJobGateway.retry(jobId);
```

Đây là **dòng mã minh họa**, không phải chương trình độc lập. Tầng domain không cần biết thao tác bên dưới dùng `POST(noBody())` hay API giao tiếp khác.

Ví dụ một HTTP adapter nhỏ:

```java
public final class RetryJobHttpGateway {
    private final HttpClient client;
    private final URI baseUri;

    public RetryJobHttpGateway(HttpClient client, URI baseUri) {
        this.client = client;
        this.baseUri = baseUri;
    }

    public boolean retry(long jobId)
            throws IOException, InterruptedException {
        if (jobId <= 0) {
            throw new IllegalArgumentException("Invalid jobId");
        }

        URI target = baseUri.resolve("jobs/" + jobId + "/retry");
        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        return response.statusCode() == 202;
    }
}
```

Đây là **một class minh họa**, chưa bao gồm imports (cần `IOException`, `URI`, `HttpClient`, `HttpRequest`, `HttpResponse`, `Duration`) hoặc ứng dụng có `main`; cũng cần policy xử lý các HTTP status khác. `boolean` trong ví dụ chỉ có nghĩa “server trả `202`”, **không khẳng định job đã chạy xong**.

Tầng HTTP adapter là nơi quyết định endpoint nào dùng noBody, endpoint nào gửi JSON, và cách diễn giải status. Không cài đặt các chi tiết transport này trong entity hoặc business rule.

## 11. Bất đồng bộ với `sendAsync`

Cùng một `HttpRequest` không body có thể gửi bất đồng bộ:

```java
CompletableFuture<HttpResponse<Void>> result =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.discarding());
```

Đây là đoạn mã trong một phương thức, cần imports `CompletableFuture` và `HttpResponse`. Trong Java 11, `sendAsync` trả `CompletableFuture<HttpResponse<T>>`; body publisher ở phía request vẫn là `noBody()`.

Khi kiểm tra kết quả:

```java
result.thenApply(HttpResponse::statusCode)
      .thenAccept(code -> {
          if (code == 202) {
              System.out.println("Accepted");
          } else {
              System.out.println("HTTP status: " + code);
          }
      });
```

Đây cũng là **đoạn minh họa**, chưa có bước giữ chương trình đợi future hoàn thành và chưa xử lý các trạng thái exceptionally. Trong ứng dụng thật phải xử lý lỗi bất đồng bộ bằng `handle`, `whenComplete` hoặc cơ chế phù hợp; không chỉ nhìn dòng `thenAccept` mà cho rằng mọi request luôn hoàn thành thành công.

**Phân biệt lỗi:**

- Mã `400`, `401`, `404`, `409`, `429`, `503` là **HTTP status**, cần diễn giải theo endpoint.
- Lỗi DNS, kết nối, TLS, timeout hoặc đọc response có thể khiến `send` ném `IOException` hoặc khiến future của `sendAsync` hoàn tất exceptionally.
- `send` có thể ném `InterruptedException`; nếu bắt rồi bọc thành loại lỗi khác, thường nên gọi `Thread.currentThread().interrupt()` trước khi propagate.
- `noBody()` không giúp tránh lỗi kết nối, phân quyền, timeout, hoặc dữ liệu response không hợp lệ.

## 12. Retry, idempotency và hệ quả nghiệp vụ

Một request `POST(noBody())` có thể kích hoạt một tác vụ có side effect như retry job, thanh toán, gửi email hoặc thay đổi trạng thái. Vì vậy **không có body không có nghĩa thao tác vô hại**.

Giả sử client POST để kích hoạt hành động, nhưng kết nối đứt trước khi nhận response. Có ít nhất hai khả năng: server chưa xử lý, hoặc server đã xử lý nhưng response bị mất. Gửi lại tự động có thể **thực hiện hai lần**.

Một thiết kế vững cần xác định:

1. Endpoint có idempotent không? Cùng một request lặp lại có tạo thêm side effect không?
2. API có hỗ trợ `Idempotency-Key`, version precondition, request ID hoặc truy vấn trạng thái kết quả không?
3. Những HTTP status/lỗi mạng nào được phép retry? Có `Retry-After` khi bị `429` hoặc `503` không?
4. Giới hạn **số lần thử, tổng deadline** và số request đồng thời như thế nào?
5. Nếu server đã nhận yêu cầu nhưng chưa hoàn tất (`202`), application sẽ kiểm tra trạng thái ở đâu?

Đặt retry tại adapter/gateway hoặc tầng orchestration có hiểu operation; **không** retry mù mọi `POST(noBody())`. `DELETE()` cũng có thể liên quan side effect, đặc biệt khi hệ thống bên ngoài không bảo đảm triển khai đúng ngữ nghĩa HTTP.

## 13. Kiểm thử hành vi request không body

Một bộ test tốt chia ra hai lớp:

### Test nhanh, không mạng

Dùng `NoBodyRequestDemo` hoặc unit test tương đương để kiểm tra:

- `request.method()` bằng method mong muốn.
- `request.uri()` khớp endpoint.
- Các headers do adapter đặt có đúng không.
- Với `POST(noBody())`, `bodyPublisher()` có mặt và `contentLength() == 0`.
- Application xử lý `202`, `204`, `4xx`/`5xx` theo hợp đồng.

Những test này không chứng minh request đã tới server hoặc header trên dây đúng như mong đợi.

### Integration test với HTTP server thử nghiệm

Dùng local server như `LocalNoBodyRoundTrip` hoặc mock HTTP server được dự án hỗ trợ để kiểm tra:

- HTTP method và URI thực nhận.
- Request không có content bytes.
- Auth và headers được xử lý như kỳ vọng.
- Response status, timeout và lỗi kết nối.
- HTTP/1.1/HTTP/2 nếu hệ thống yêu cầu cả hai.
- Thao tác có side effect có cơ chế chống xử lý trùng khi retry.

Đối với API production, ưu tiên local integration/contract tests có dữ liệu thử nghiệm và môi trường kiểm soát; đừng để mỗi unit test phụ thuộc dịch vụ thật hoặc token nhạy cảm.

## 14. Lỗi thường gặp và cách xử lý

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gọi `POST()` không tham số như `GET()` | `POST` của Java 11 yêu cầu một `BodyPublisher` | Dùng `POST(BodyPublishers.noBody())` |
| Truyền `null` để biểu diễn không body | Publisher phải là đối tượng hợp lệ | Dùng `BodyPublishers.noBody()` |
| Dùng `ofString("{}")` cho mọi POST rỗng | `{}` vẫn là JSON payload | Chọn theo hợp đồng API |
| Cho rằng `noBody()` tự đặt đúng mọi header | API chỉ đảm bảo publisher không phát content | Đặt headers cần thiết; kiểm tra wire bằng integration test |
| Coi `noBody()` và `BodyHandlers.discarding()` là một | Một cái thuộc request, cái kia thuộc response | Phân biệt chiều gửi và nhận |
| Gọi `request.bodyPublisher().get()` trên GET | `Optional` có thể rỗng | Kiểm tra `isPresent()` hoặc `map/orElse` |
| Sử dụng `Builder.HEAD()` rồi biên dịch `--release 11` | `HEAD()` được bổ sung sau Java 11 | Dùng `method("HEAD", noBody())` |
| Tưởng `POST(noBody())` là thao tác chỉ đọc | Method vẫn có side effect theo hợp đồng | Đánh giá idempotency, quyền và retry |
| Bỏ qua status vì response không body | Lỗi `401`, `409`, `503` vẫn có thể xảy ra | Kiểm tra `response.statusCode()` |
| Mặc định Content-Length luôn có đúng một dạng header | Wire formatting do client/protocol quyết định | Dùng test phía server nếu hợp đồng cần |
| Dùng `Content-Type: application/json` khi không có payload | Có thể gây hiểu sai representation | Chỉ đặt khi hợp đồng yêu cầu |
| Không đặt timeout | Request có thể chờ quá lâu | Đặt timeout, deadline và chính sách hủy phù hợp |
| Log URL/token khi gửi POST noBody | URL/headers vẫn có thể nhạy cảm | Redact hoặc không log secrets |
| Tưởng publisher độ dài 0 ngăn được trả body lớn | Response được xử lý bằng BodyHandler riêng | Giới hạn body của response nếu đầu vào không tin cậy |
| Test bằng inspect request rồi khẳng định server đã nhận | Chưa có network I/O | Kiểm tra thêm bằng local integration test |

## 15. Bài tập thực hành

**Bài 1 — Phân biệt các request.** Chạy `NoBodyRequestDemo.java`. Giải thích vì sao `GET()`/`DELETE()` không cần truyền publisher, còn `POST()` và `PUT()` bắt buộc có publisher. Giải thích tại sao `POST(noBody())` và `POST(ofString(""))` đều có body length bằng 0 nhưng diễn đạt ý định khác nhau.

**Bài 2 — Đúng method, đúng hợp đồng.** Giả sử endpoint yêu cầu `POST /tasks/15/start` với **không có body**, trả `202 Accepted`. Viết `HttpRequest` dùng `POST(noBody())`, đặt timeout và header `Accept` cần thiết. Nêu vì sao không cần gửi `{}` nếu API không yêu cầu JSON.

**Bài 3 — HEAD trên Java 11.** Viết request HEAD tương thích `--release 11` và dùng `BodyHandlers.discarding()` cho response. Giải thích vì sao không dùng `HttpRequest.Builder.HEAD()` trong bài Java 11.

**Bài 4 — Loopback thực tế.** Chạy `LocalNoBodyRoundTrip.java`. Đọc request line và status `204`; thử đổi method từ `POST` sang `PUT`. Kết quả server demo có thể vẫn `204` vì server đơn giản không kiểm tra phương thức, nhưng trong production server phải kiểm tra method và policy.

**Bài 5 — Response riêng biệt.** Một endpoint nhận `POST(noBody())` nhưng trả JSON `{"jobId":"7","status":"queued"}`. Hãy chọn `BodyHandlers.ofString(UTF_8)` để nhận body, kiểm tra status trước khi parse JSON. Giải thích vì sao `noBody()` không ngăn response có nội dung.

**Bài 6 — Retry an toàn.** Giả sử `POST(noBody())` kích hoạt gửi một email; client timeout sau khi server đã xử lý. Đề xuất idempotency key hoặc cơ chế kiểm tra trạng thái trước khi retry. Trình bày lý do body rỗng không làm operation tự động idempotent.

### Checklist hoàn thành

- [ ] Biết `BodyPublishers.noBody()` thuộc API `java.net.http` của Java 11 và trả `BodyPublisher` không phát request content.
- [ ] Tạo được `POST(noBody())`, `PUT(noBody())`, `method("PATCH", noBody())` khi hợp đồng cho phép.
- [ ] Biết `GET()` và `DELETE()` không cần truyền publisher; `HEAD` trong Java 11 viết qua `method("HEAD", noBody())`.
- [ ] Phân biệt request `BodyPublisher` với response `BodyHandler`.
- [ ] Đọc đúng `bodyPublisher()` là `Optional` và `contentLength() == 0` của `noBody()`.
- [ ] Không suy ra chính xác headers trên dây chỉ từ `contentLength()`.
- [ ] Phân biệt không body, chuỗi rỗng và JSON `{}`.
- [ ] Kiểm tra status, timeout, retry, idempotency và bảo mật khi gửi request.
- [ ] Biên dịch các ví dụ với compiler hỗ trợ `--release 11` trên một JDK đang được cập nhật.

## 16. Tài liệu tham khảo chính thức

1. [Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html) — `noBody()`, `ofString`, `ofByteArray`, `ofFile`, `fromPublisher`.
2. [Java SE 11 — HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html) — `contentLength()`, `Flow.Publisher<ByteBuffer>` và ngữ nghĩa body rỗng.
3. [Java SE 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html) — `GET`, `DELETE`, `POST`, `PUT` và `method`.
4. [Java SE 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html) — `method()`, `uri()`, `bodyPublisher()` và timeout.
5. [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html) — `send`, `sendAsync`, kết nối và cấu hình.
6. [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — `discarding()`, `ofString` và xử lý response.
7. [Java SE 25 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html) — API tiếp tục có trong dòng JDK LTS hiện hành.

**Nguyên tắc áp dụng:** khi hợp đồng HTTP yêu cầu **không có request body**, `HttpRequest.BodyPublishers.noBody()` là lựa chọn rõ nghĩa cho các builder yêu cầu publisher. Nó **không quyết định method, headers, HTTP status hoặc response body**; toàn bộ tác động và tính hợp lệ của request vẫn phụ thuộc URI, method, quyền truy cập và hợp đồng server.