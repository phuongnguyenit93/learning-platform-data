# Builder khả biến và request bất biến trong Java 11+

**Chủ đề cha: HTTP Request.** API `java.net.http` được chuẩn hóa trong Java 11 và vẫn được dùng trong Java hiện đại. Khi tạo HTTP request, Java phân biệt rõ **`HttpRequest.Builder` có thể thay đổi** (*mutable*) với **`HttpRequest` đã được xây dựng có cấu hình bất biến** (*immutable*). Phân biệt đúng hai giai đoạn giúp tránh rò rỉ header, ghi đè cấu hình của request trước, và lỗi khi nhiều luồng cùng xây request.

Bài học đi từ cơ chế, các ví dụ Java 11+ chạy được, `header` so với `setHeader`, `Builder.copy()`, body publisher, tái sử dụng request, an toàn đồng thời, lỗi biên dịch/runtime và bộ kiểm thử hồi quy. Chúng ta tập trung vào hành vi của **request**; `HttpClient` là đối tượng gửi và có vòng đời độc lập.

## 1. Mô hình vòng đời của HTTP request

```text
HttpRequest.newBuilder(uri)
          |
          v
HttpRequest.Builder (mutable)
  - uri(...), GET(), POST(...), PUT(...)
  - header(...), setHeader(...), timeout(...)
          |
       build()
          |
          v
HttpRequest A (immutable)
          |
          +-- client.send(A, ...)
          +-- client.sendAsync(A, ...)
          |
          v
Builder vẫn còn và có thể chỉnh tiếp
          |
       build()
          |
          v
HttpRequest B (immutable, đối tượng mới)
```

Tại giai đoạn builder, các lời gọi cấu hình thay đổi **trạng thái của chính builder** và trả lại builder đó để có thể viết chuỗi lời gọi. Tại giai đoạn request, đối tượng đã build không có setter để đổi URI, method, headers, timeout hoặc body publisher.

Javadoc của `HttpRequest.Builder` quy định:

- Các setter chỉnh **builder hiện tại**; chúng không âm thầm trả về một request mới.
- `build()` trả về **một đối tượng `HttpRequest` mới ở mỗi lần gọi**.
- Request đã build **bất biến về cấu hình** và **có thể được gửi nhiều lần**.
- Các setter trên builder **không được đồng bộ hóa**. Không dùng cùng builder từ nhiều thread mà không có đồng bộ bên ngoài.

Có thể xem `HttpRequest` là một bản chốt cấu hình tại thời điểm `build()`. Đây là cách hiểu hữu ích cho việc đọc code. Nó **không** có nghĩa Java sao chép sâu mọi đối tượng mà builder có thể tham chiếu, đặc biệt là một `BodyPublisher` tùy chỉnh có trạng thái.

## 2. Những thành phần nào có thể cấu hình trên Builder?

Với Java 11, một builder có thể nhận:

| Cấu hình | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Địa chỉ yêu cầu | `uri(URI)` | Đích HTTP/HTTPS hợp lệ |
| Phương thức HTTP | `GET()`, `POST(BodyPublisher)`, `PUT(BodyPublisher)`, `DELETE()`, `method(...)` | Cách request tương tác với tài nguyên |
| Header | `header(name,value)`, `headers(...)`, `setHeader(name,value)` | Metadata của request |
| Timeout của request | `timeout(Duration)` | Thời hạn cho request cụ thể |
| Phiên bản HTTP ưu tiên | `version(HttpClient.Version)` | HTTP/1.1 hoặc HTTP/2 ưu tiên, không bảo đảm giao thức thực tế |
| Expect: 100-continue | `expectContinue(boolean)` | Tùy chọn bắt tay trước khi gửi body trong trường hợp phù hợp |

Có hai điểm cần chú ý:

1. `HttpRequest.newBuilder()` không có URI ban đầu: gọi `build()` khi chưa đặt URI sẽ ném `IllegalStateException`. `HttpRequest.newBuilder(URI)` cho phép cung cấp URI ngay từ đầu.
2. Khi không cấu hình method khác, method mặc định của builder là **GET**. Viết `GET()` tường minh cũng hợp lệ và làm rõ ý định.

Các tên header hoặc giá trị không hợp lệ có thể gây `IllegalArgumentException`. Một số header (ví dụ thông tin do HTTP client tự quản lý) còn bị hạn chế đặt trực tiếp. Không giả định có thể tự đặt tùy ý `Content-Length` hoặc các header bị JDK giới hạn.

## 3. Thay đổi Builder sau build không làm request cũ đổi theo

Đây là cơ chế quan trọng nhất của bài. Ví dụ sau **không gửi request ra Internet**: chỉ xây dựng đối tượng rồi đọc lại thuộc tính từ chúng.

### Ví dụ chạy được: `RequestSnapshotDemo.java`

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class RequestSnapshotDemo {
    public static void main(String[] args) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create("https://example.org/one"))
                .timeout(Duration.ofSeconds(2))
                .header("X-Trace", "alpha")
                .GET();

        HttpRequest first = builder.build();

        builder.uri(URI.create("https://example.org/two"))
                .timeout(Duration.ofSeconds(9))
                .setHeader("X-Trace", "beta")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "payload", StandardCharsets.UTF_8));

        HttpRequest second = builder.build();

        System.out.println("first URI: " + first.uri());
        System.out.println("first method: " + first.method());
        System.out.println("first timeout: "
                + first.timeout().orElseThrow().toSeconds());
        System.out.println("first trace: "
                + first.headers().firstValue("X-Trace").orElseThrow());
        System.out.println("first has body: "
                + first.bodyPublisher().isPresent());

        System.out.println("second URI: " + second.uri());
        System.out.println("second method: " + second.method());
        System.out.println("second timeout: "
                + second.timeout().orElseThrow().toSeconds());
        System.out.println("second trace: "
                + second.headers().firstValue("X-Trace").orElseThrow());
        System.out.println("second has body: "
                + second.bodyPublisher().isPresent());
        System.out.println("same request: " + (first == second));
    }
}
```

Biên dịch/chạy bằng JDK 11 trở lên:

```bash
javac --release 11 -encoding UTF-8 RequestSnapshotDemo.java
java RequestSnapshotDemo
```

Stdout:

```text
first URI: https://example.org/one
first method: GET
first timeout: 2
first trace: alpha
first has body: false
second URI: https://example.org/two
second method: POST
second timeout: 9
second trace: beta
second has body: true
same request: false
```

**Giải thích:** `first` chốt URI `/one`, GET, timeout 2 giây và `X-Trace: alpha`. Việc sửa builder để tạo `second` không tác động đến `first`. Mỗi `build()` tạo đối tượng riêng, nhưng cả hai vẫn có thể được chuyển đến một `HttpClient` để gửi.

Bài này dùng `.headers().firstValue(...)` để quan sát header đã chốt và `.bodyPublisher().isPresent()` để biết request có body publisher không. `first` không có body publisher, còn `second` chứa body publisher cho POST; không cần gửi ra mạng để kiểm tra các thuộc tính đó.

## 4. `header` khác `setHeader` như thế nào?

Hai API giống tên nhưng khác ý nghĩa:

- `builder.header("X-Mode", "one")` **bổ sung một giá trị** vào tập giá trị của header đó.
- Gọi `header("X-Mode", "two")` tiếp tục **thêm** giá trị thứ hai dưới cùng tên.
- `builder.setHeader("X-Mode", "three")` **thay thế mọi giá trị đã đặt trước đó** cho tên header đó.
- Tên HTTP header được xử lý theo quy tắc **không phân biệt chữ hoa/chữ thường**; không dùng sự khác biệt viết hoa để tạo hai header độc lập.

### Ví dụ chạy được: `HeaderMutationDemo.java`

```java
import java.net.URI;
import java.net.http.HttpRequest;

public class HeaderMutationDemo {
    public static void main(String[] args) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create("https://example.org/data"))
                .header("X-Mode", "one")
                .header("X-Mode", "two");

        HttpRequest multiple = builder.build();

        builder.setHeader("X-Mode", "three");
        HttpRequest replaced = builder.build();

        System.out.println("multiple: "
                + multiple.headers().allValues("X-Mode"));
        System.out.println("replaced: "
                + replaced.headers().allValues("X-Mode"));
        System.out.println("original unchanged: "
                + multiple.headers().allValues("X-Mode"));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 HeaderMutationDemo.java
java HeaderMutationDemo
```

```text
multiple: [one, two]
replaced: [three]
original unchanged: [one, two]
```

Khi xử lý token xác thực hoặc request ID cần **một giá trị**, nên dùng `setHeader` để thay thế cấu hình cũ trên builder; thận trọng với việc nối nhiều giá trị không chủ ý bằng `header`. Đừng đặt thông tin bí mật trong header trên một builder dùng chung qua nhiều người dùng rồi đổi qua lại giữa các request: điều đó dễ làm lộ trạng thái và có rủi ro chạy đồng thời.

Bất biến của request có nghĩa tập header của `HttpRequest` đã build không bị đổi bởi việc sửa builder về sau. Nó **không** có nghĩa những header hiện diện trên request luôn phù hợp về an toàn hoặc nghiệp vụ; phải chọn thông tin chính xác trước khi build.

## 5. `Builder.copy()`: tách nhánh cấu hình ngay trong Java 11

`HttpRequest.Builder.copy()` **đã có trong Java 11**. Phương thức này tạo một builder mới dựa trên trạng thái hiện tại, sau đó mỗi builder có thể được thay đổi độc lập. Khi nhiều request có phần cấu hình chung như Accept, User-Agent và timeout, copy giúp tái sử dụng cấu hình **trước khi build** mà không làm các nhánh sửa lẫn nhau.

### Ví dụ chạy được: `CopyBuilderDemo.java`

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

public class CopyBuilderDemo {
    public static void main(String[] args) {
        HttpRequest.Builder base = HttpRequest.newBuilder(
                URI.create("https://example.org/items"))
                .header("Accept", "application/json")
                .setHeader("X-Mode", "base")
                .timeout(Duration.ofSeconds(5))
                .GET();

        HttpRequest.Builder child = base.copy();
        child.uri(URI.create("https://example.org/items/42"))
                .setHeader("X-Mode", "detail");

        HttpRequest baseRequest = base.build();
        HttpRequest childRequest = child.build();

        System.out.println("base URI: " + baseRequest.uri());
        System.out.println("child URI: " + childRequest.uri());
        System.out.println("base mode: " + baseRequest.headers()
                .firstValue("X-Mode").orElseThrow());
        System.out.println("child mode: " + childRequest.headers()
                .firstValue("X-Mode").orElseThrow());
        System.out.println("child Accept: " + childRequest.headers()
                .firstValue("Accept").orElseThrow());
        System.out.println("same builder: " + (base == child));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 CopyBuilderDemo.java
java CopyBuilderDemo
```

```text
base URI: https://example.org/items
child URI: https://example.org/items/42
base mode: base
child mode: detail
child Accept: application/json
same builder: false
```

`copy()` có ích khi làm nhiều request có **cấu hình nền** giống nhau rồi thay đổi từng trường. Tuy nhiên, đừng dùng chung cùng một builder mutable từ nhiều thread để gọi `copy()` trong khi thread khác đang cập nhật nó; cách đó vẫn có cạnh tranh dữ liệu. Tốt nhất mỗi luồng sở hữu builder riêng hoặc việc copy/sửa được điều phối rõ ràng.

**Phân biệt API theo phiên bản:** `HttpRequest.newBuilder(existingRequest, headerFilter)` (khởi tạo builder từ một `HttpRequest` đã build) là API được thêm sau Java 11, từ Java 16. Nó hữu ích trên JDK mới nhưng **không biên dịch với `--release 11`**. Nếu cần source tương thích Java 11, sử dụng `Builder.copy()` **trước khi bỏ builder gốc**, hoặc xây request mới từ các thông tin cần thiết. Không giả định có thể gọi `first.toBuilder()`: `HttpRequest` không có instance method như vậy.

## 6. Bất biến không có nghĩa cùng một request phải gửi đúng một lần

Theo hợp đồng Java 11, một `HttpRequest` đã build có thể được truyền cho `HttpClient.send(...)` hay `sendAsync(...)` **nhiều lần**. Có ba tình huống khác nhau cần phân biệt:

1. **Request object:** cùng một cấu hình URI/method/headers/timeout/body publisher được dùng lại; không cần build lại để gửi lại một GET.
2. **HTTP exchange:** mỗi lần gửi có kết quả `HttpResponse` riêng. Status, headers và body response có thể khác nhau vì trạng thái server thay đổi.
3. **Tác động nghiệp vụ:** gửi lại POST tạo đơn hàng, thanh toán hoặc upload có thể **lặp tác động**. Việc request bất biến không tự làm thao tác HTTP trở thành *idempotent*.

Với request có body, bất biến còn **không tự bảo đảm body được phát lại thành công**: `BodyPublisher` có thể lấy dữ liệu từ file, stream, supplier hoặc nguồn tự định nghĩa. Một `BodyPublisher` phụ thuộc vào nguồn chỉ đọc một lần có thể không tái sử dụng được nếu không có cách cung cấp nguồn mới.

- `BodyPublishers.ofString(...)` là lựa chọn rõ ràng cho nội dung chuỗi đã có. Lựa chọn charset (ví dụ UTF-8) theo hợp đồng API.
- `BodyPublishers.ofInputStream(supplier)` dựa trên `Supplier<InputStream>`; khi cần gửi lại, supplier phải có khả năng tạo **InputStream mới** có dữ liệu mong muốn cho mỗi lần đăng ký.
- Request bất biến **không** bảo đảm nội dung của tài nguyên bên ngoài không đổi: ví dụ file bị sửa sau khi xây request nhưng trước lúc dữ liệu được đọc.
- Với POST/PUT có tác dụng phụ, chính sách retry phải xét tính idempotent và điều khoản của server.

Vì vậy câu “một request có thể gửi nhiều lần” là **khả năng của API**, không phải chỉ dẫn gửi lại tùy ý ở mọi hoàn cảnh.

## 7. Chạy cùng một request đã chốt và request mới sau khi sửa builder

Ví dụ đầy đủ dưới đây dùng một HTTP server loopback trên `127.0.0.1`, không phụ thuộc truy cập Internet. Chúng ta build request `/one`, đổi builder sang `/two` rồi gửi lần lượt request đầu, request sau và **request đầu thêm lần nữa**. Server phản hồi phương thức, đường dẫn và header của mỗi lần nhận.

`com.sun.net.httpserver.HttpServer` thuộc module JDK `jdk.httpserver`, chỉ dùng làm fixture kiểm thử.

### `RequestReuseLocalDemo.java`

```java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class RequestReuseLocalDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/", exchange -> {
            String reply = exchange.getRequestMethod() + " "
                    + exchange.getRequestURI().getPath() + " "
                    + exchange.getRequestHeaders().getFirst("X-Mode");
            byte[] bytes = reply.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        try {
            String origin = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpRequest.Builder builder = HttpRequest.newBuilder(
                    URI.create(origin + "/one"))
                    .setHeader("X-Mode", "first")
                    .GET();

            HttpRequest first = builder.build();

            builder.uri(URI.create(origin + "/two"))
                    .setHeader("X-Mode", "second");
            HttpRequest second = builder.build();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            HttpResponse.BodyHandler<String> handler =
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8);

            System.out.println(client.send(first, handler).body());
            System.out.println(client.send(second, handler).body());
            System.out.println(client.send(first, handler).body());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch và chạy (Java 11+):

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 RequestReuseLocalDemo.java
java --add-modules jdk.httpserver RequestReuseLocalDemo
```

Stdout khi server loopback nhận và xử lý đủ ba request:

```text
GET /one first
GET /two second
GET /one first
```

Lần gửi thứ ba vẫn có đường dẫn `/one` và header `first`, vì `first` đã được build **trước** khi builder đổi sang `/two`. Kết quả cũng chứng minh một request GET bất biến có thể gửi lại nhiều lần trong ví dụ này.

Giới hạn của ví dụ: nó kiểm tra nội dung response, không đếm số socket TCP. Từ ba lời gọi `send` không suy ra cả ba request đã dùng chung đúng một kết nối vật lý. Mục tiêu ở đây là **builder/request**, không phải đánh giá connection pooling.

## 8. An toàn đồng thời: Builder không thread-safe, request đã build có thể chia sẻ

Theo Javadoc, setter của `HttpRequest.Builder` không synchronized. Nếu hai thread cùng sửa một builder, kết quả phụ thuộc thứ tự thao tác không được bảo đảm. Ví dụ dễ gây lỗi logic:

```java
// Minh họa chống chỉ định; không dùng chung builder mutable theo cách này.
// Thread A: sharedBuilder.uri(uriA).setHeader("X-User", "A");
// Thread B: sharedBuilder.uri(uriB).setHeader("X-User", "B");
// Thread A: HttpRequest requestA = sharedBuilder.build();
```

Cấu hình `requestA` có thể không còn tương ứng với URI/header mà thread A dự định, vì thread B cũng sửa trạng thái builder. Ví dụ này chỉ minh họa ý tưởng; không có bảo đảm về một interleaving cụ thể.

**Cách tổ chức được khuyến nghị:**

- Một `HttpClient` đã tạo có thể được chia sẻ để gửi nhiều request.
- Mỗi lời gọi hoặc luồng tạo **một `HttpRequest.Builder` riêng** cho request của mình.
- Sau `build()`, `HttpRequest` có cấu hình bất biến và có thể được truyền giữa các luồng nếu body publisher và logic nghiệp vụ phù hợp.
- Nếu muốn cấu hình chung, tạo hàm sinh builder/request, hoặc copy builder ở một bước khởi tạo có kiểm soát. Tránh dùng một builder mutable làm biến toàn cục có thể bị ghi bởi mọi thread.

### Mẫu tạo request độc lập theo từng lời gọi

Tệp **`RequestFactory.java`** (lớp hỗ trợ, không có `main`):

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;
import java.util.Objects;

public final class RequestFactory {
    private final URI origin;

    public RequestFactory(URI origin) {
        this.origin = Objects.requireNonNull(origin);
    }

    public HttpRequest getItem(String id, String token) {
        Objects.requireNonNull(id);
        Objects.requireNonNull(token);

        return HttpRequest.newBuilder(
                    origin.resolve("/items/" + id))
                .timeout(Duration.ofSeconds(10))
                .setHeader("Accept", "application/json")
                .setHeader("Authorization", "Bearer " + token)
                .GET()
                .build();
    }
}
```

```bash
javac --release 11 -encoding UTF-8 RequestFactory.java
```

Ví dụ minh họa này dùng biến `id` theo một đoạn URI được tin cậy; với dữ liệu không tin cậy cần **mã hóa thành phần path** phù hợp để tránh tạo sai URI. `token` được đưa vào request riêng theo từng lời gọi. Nếu hệ thống xử lý thông tin xác thực nhạy cảm, không in toàn bộ request/header ra log.

`RequestFactory` giữ một URI nền bất biến và tạo builder mới khi gọi `getItem`. Nó không chứa builder mutable dùng chung. Khi request trả về, không có setter nào cho phép luồng khác sửa `Authorization` hay `timeout` của chính request đó.

## 9. Trạng thái do request quản lý và trạng thái do client quản lý

Đừng gộp tất cả cấu hình vào một chỗ:

| Đối tượng | Cấu hình/đầu vào | Phạm vi |
| --- | --- | --- |
| `HttpRequest.Builder` | URI, method, headers, timeout, body publisher | Bản nháp của một request |
| `HttpRequest` | Các thuộc tính đã build và có thể đọc qua getter | Một cấu hình request bất biến |
| `HttpClient.Builder` | Redirect policy, proxy, SSL context, connect timeout, executor và lựa chọn chung | Bản nháp của client |
| `HttpClient` | Client đã build, có thể gửi nhiều request | Cấu hình client, quản lý kết nối/tác vụ |
| `HttpResponse<T>` | Status, headers, body, HTTP version thực tế | Kết quả của một lần gửi |

Ví dụ, **timeout kết nối** cấu hình trên `HttpClient.Builder.connectTimeout(...)` khác với **timeout request** trên `HttpRequest.Builder.timeout(...)`. Đừng tạo nhiều client chỉ để đặt timeout khác nhau cho từng request: thường có thể giữ client và tạo request mới với timeout phù hợp.

Với HTTP version, `HttpRequest.Builder.version(...)` đặt phiên bản **ưu tiên** cho request; server/client có thể thương lượng phiên bản khác. Kiểm tra `HttpResponse.version()` để biết phiên bản thực tế.

Việc `HttpRequest` bất biến không làm `HttpClient` tự động sửa mọi lỗi network, retry, backpressure, cookie/session hoặc xác thực. Những mối quan tâm đó cần chính sách riêng ở tầng gọi.

## 10. Các lỗi đầu vào và hành vi dễ nhầm

Khi thao tác với builder, các trường hợp sau có ý nghĩa học tập thực tế:

1. **Thiếu URI:** `HttpRequest.newBuilder().build()` ném `IllegalStateException` vì không thể tạo request hợp lệ nếu thiếu URI.
2. **Timeout không dương:** `timeout(Duration.ZERO)` hoặc thời lượng âm ném `IllegalArgumentException`.
3. **URI có scheme không được hỗ trợ:** ví dụ `file:///tmp/data` không phải một URI HTTP request hợp lệ cho builder này; setter có thể ném `IllegalArgumentException`.
4. **Tên/giá trị header sai:** header rỗng hoặc chứa ký tự điều khiển không hợp lệ có thể bị từ chối. Một số tên header bị JDK hạn chế; đừng cố thiết lập `Content-Length` bằng tay khi BodyPublisher quản lý độ dài.
5. **Không phân biệt `header`/`setHeader`:** thêm nhiều giá trị khi mong muốn một giá trị có thể gây lỗi request hoặc tạo hành vi không mong đợi.
6. **Sửa builder sau `build()` rồi tưởng request cũ thay đổi:** request cũ giữ nguyên trạng thái đã chốt.
7. **Cùng builder trên nhiều thread:** builder không có hợp đồng thread-safe.
8. **Gửi lại POST và nghĩ an toàn:** một request có thể gửi nhiều lần ở mức API, nhưng nghiệp vụ có thể tạo dữ liệu trùng hoặc side effect.
9. **Coi body publisher là bản sao sâu bất biến:** request chốt tham chiếu/cấu hình publisher, nhưng dữ liệu ngoài hoặc publisher tự viết có thể thay đổi.
10. **Không tiêu thụ body response:** một số BodyHandler trả về stream hay publisher cần được đọc/đóng/hủy đúng cách để giải phóng tài nguyên kết nối.

**Lưu ý phiên bản API:** `HttpRequest.Builder.copy()` có trong Java 11; một số tiện ích mới được thêm về sau, chẳng hạn `HttpRequest.newBuilder(request, headerFilter)` từ Java 16 và `HttpRequest.Builder.HEAD()` trên Java 21+. Nếu bài tập phải dùng `javac --release 11`, hãy dùng API thực sự có trong Java 11. Các tiện ích mới không thay đổi quy tắc mutable builder/immutable request.

## 11. Bộ test hồi quy không cần network

Ví dụ dưới đây xác minh trực tiếp bất biến của request, sự độc lập của `copy()`, việc xây hai đối tượng khác nhau và các trường hợp lỗi quan trọng. Nó tự ném `AssertionError` khi một kiểm tra không khớp; không dùng câu lệnh `assert` vốn có thể bị JVM vô hiệu hóa nếu thiếu `-ea`.

### `RequestBuilderRegression.java`

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class RequestBuilderRegression {
    private static int checks = 0;

    private static void check(String label, boolean actual) {
        checks++;
        if (!actual) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create("https://example.org/v1"))
                .setHeader("X-State", "first")
                .timeout(Duration.ofSeconds(2))
                .GET();

        HttpRequest first = builder.build();
        HttpRequest firstAgain = builder.build();

        check("build creates new object", first != firstAgain);
        check("first URI", first.uri().toString().endsWith("/v1"));
        check("first method", first.method().equals("GET"));
        check("first timeout", first.timeout().orElseThrow()
                .equals(Duration.ofSeconds(2)));
        check("first header", first.headers()
                .firstValue("X-State").orElseThrow().equals("first"));
        check("first has no body", first.bodyPublisher().isEmpty());

        builder.uri(URI.create("https://example.org/v2"))
                .setHeader("X-State", "second")
                .timeout(Duration.ofSeconds(7))
                .POST(HttpRequest.BodyPublishers.ofString(
                        "payload", StandardCharsets.UTF_8));

        HttpRequest second = builder.build();
        check("second URI", second.uri().toString().endsWith("/v2"));
        check("second method", second.method().equals("POST"));
        check("second timeout", second.timeout().orElseThrow()
                .equals(Duration.ofSeconds(7)));
        check("second header", second.headers()
                .firstValue("X-State").orElseThrow().equals("second"));
        check("second has body", second.bodyPublisher().isPresent());

        HttpRequest.Builder copy = builder.copy();
        copy.setHeader("X-State", "third");
        HttpRequest third = copy.build();

        check("copy changed independently", third.headers()
                .firstValue("X-State").orElseThrow().equals("third"));
        check("original builder intact", builder.build().headers()
                .firstValue("X-State").orElseThrow().equals("second"));
        check("first still intact", first.headers()
                .firstValue("X-State").orElseThrow().equals("first"));

        boolean missingUriRejected = false;
        try {
            HttpRequest.newBuilder().build();
        } catch (IllegalStateException expected) {
            missingUriRejected = true;
        }
        check("missing URI rejected", missingUriRejected);

        boolean badTimeoutRejected = false;
        try {
            HttpRequest.newBuilder().timeout(Duration.ZERO);
        } catch (IllegalArgumentException expected) {
            badTimeoutRejected = true;
        }
        check("zero timeout rejected", badTimeoutRejected);

        System.out.println("PASS: " + checks + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 RequestBuilderRegression.java
java RequestBuilderRegression
```

```text
PASS: 16 checks
```

**Đếm test:** 6 cho request đầu, 5 cho request thứ hai, 3 cho khả năng sửa builder copy độc lập, 2 cho lỗi đầu vào = **16**. Các phép kiểm tra đọc thông tin từ `HttpRequest` mà không gửi network request. Nếu có lỗi, `AssertionError` kèm tên case được đưa ra.

Trong dự án sử dụng JUnit, bạn có thể chuyển các trường hợp thành unit test theo framework dự án đang dùng. Với phần gửi HTTP, bổ sung integration test dùng server do test kiểm soát, tránh dựa vào Internet hoặc thứ tự hoàn thành ngẫu nhiên của các request async.

## 12. Mẫu sử dụng đề xuất

Một mẫu có tính dự đoán tốt trong ứng dụng:

```java
// Tạo và lưu HttpClient ở phạm vi phù hợp với dịch vụ.
HttpClient client = HttpClient.newHttpClient();

// Với mỗi operation, xây request riêng rồi chốt cấu hình:
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .setHeader("Accept", "application/json")
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Đây là đoạn minh họa bên trong phương thức đã có `uri`, các import và xử lý `IOException`/`InterruptedException`. `HttpClient` là đối tượng có thể tái sử dụng theo chính sách chung; `HttpRequest.Builder` được tạo mới trong lần gọi; `HttpRequest` là cấu hình đã chốt.

Nếu cần nhiều request cùng template, cân nhắc viết một factory hoặc dùng `Builder.copy()` ở giai đoạn kiểm soát. Với nội dung thay đổi theo người dùng, luôn đặt header, URI và body riêng cho từng request, tránh giữ một builder mutable toàn cục. Một request GET không body có thể gửi nhiều lần; một POST có body cần đánh giá khả năng phát lại nguồn và idempotency của nghiệp vụ.

## 13. Tự luyện và đáp án

**A.** `builder.build()` lần đầu rồi gọi `builder.setHeader("X-Mode","new")`. Header của request đầu đã bị đổi chưa?

**B.** Hai lần `builder.build()` mà không sửa builder có trả về cùng một reference `HttpRequest` không?

**C.** `builder.header("X-Tag","a").header("X-Tag","b")` khác với `builder.setHeader("X-Tag","b")` như thế nào?

**D.** Có thể cho hai thread cùng chỉnh một `HttpRequest.Builder` rồi gọi `build()` mà không đồng bộ không?

**E.** Nếu `HttpRequest` là bất biến, có thể gửi lại POST tạo đơn hàng vô hạn lần mà không lo xử lý trùng không?

**F.** Trên JDK 11, `Builder.copy()` có sẵn không? `HttpRequest.newBuilder(existingRequest, filter)` có sẵn không?

**Đáp án:**

1. **A:** Chưa. Request cũ đã chốt cấu hình, chỉ builder bị thay đổi.
2. **B:** Không. Theo hợp đồng, mỗi `build()` trả đối tượng `HttpRequest` mới.
3. **C:** `header` thêm giá trị; `setHeader` thay thế các giá trị đã có cho cùng tên.
4. **D:** Không nên. Builder không thread-safe; tạo builder riêng cho mỗi luồng hoặc có đồng bộ thích hợp.
5. **E:** Không. Bất biến của request không tự đảm bảo idempotency hay khả năng phát lại mọi BodyPublisher.
6. **F:** `copy()` có trong Java 11. Overload tạo builder từ một `HttpRequest` kèm header filter được bổ sung sau đó, từ Java 16.

## Nguồn tài liệu chính thức

- [Java SE 11 — HttpRequest.Builder: setter, build(), copy(), header(), setHeader()](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
- [Java SE 11 — HttpRequest: request đã build và BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Java SE 11 — HttpClient: send(), sendAsync()](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 11 — HttpHeaders: firstValue(), allValues()](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [Java SE 16 — HttpRequest.newBuilder(request, headerFilter)](https://docs.oracle.com/en/java/javase/16/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Java SE 21 — HttpRequest.Builder: các API vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
