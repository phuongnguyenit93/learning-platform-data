# close, shutdown, shutdownNow, awaitTermination và khác biệt theo phiên bản

## Mục tiêu bài học

Trong `java.net.http.HttpClient`, một client sau khi `build()` không chỉ là cấu hình bất biến; nó còn quản lý tài nguyên phục vụ các request như **kết nối HTTP/1.1, HTTP/2**, luồng xử lý và công việc bất đồng bộ. Vì vậy cần phân biệt giữa **đã xử lý xong một request** và **đã chấm dứt vòng đời của cả client**.

Đây là điểm dễ gây nhầm khi học Java networking: **Java 17 không có** các phương thức quản lý vòng đời `HttpClient.close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)` và `isTerminated()`. **Từ Java 21**, nhóm phương thức này mới được bổ sung vào `HttpClient`, cùng khả năng dùng `try-with-resources` thông qua `AutoCloseable`. Không thể copy mã dùng `client.close()` từ tài liệu JDK 21 sang dự án biên dịch `--release 17` rồi mong nó hoạt động.

Sau bài này, bạn có thể:

- Lập bảng đúng **API có/không có** giữa Java 11–20 (đặc biệt Java 17) và Java 21+.
- Giải thích khác nhau giữa `close()` (đóng orderly và **chờ**), `shutdown()` (khởi động orderly shutdown nhưng **không chờ**), `shutdownNow()` (cố gắng dừng nhanh, không đảm bảo tức thì), `awaitTermination(Duration)` (chờ có thời hạn) và `isTerminated()` (đọc trạng thái).
- Hiểu các trạng thái **đang nhận request → đang shutdown → đã terminated**, và thời điểm request mới không còn được nhận.
- Quản lý response body dạng `String`, `InputStream`, `Stream<String>` hoặc `Publisher` để không làm graceful shutdown bị kẹt.
- Áp dụng mẫu **graceful shutdown có thời hạn**, sau đó có thể gọi `shutdownNow()` như bước giảm thiểu, nhưng không khẳng định mọi tác vụ đã dừng.
- Phân biệt dừng **HTTP client** với dừng **ExecutorService tự cấp**, đóng socket của server, hoặc hủy các `CompletableFuture`.
- Chạy **hai chương trình độc lập**: một chương trình tương thích **Java 17**, một chương trình **Java 21+** dùng đầy đủ API mới; kiểm chứng trên loopback, không cần Internet.

## 1. Hai phiên bản API: Java 17 và Java 21 khác nhau ở đâu?

`HttpClient` được chuẩn hóa trong `java.net.http` từ **Java 11**. Trong Java 17, lớp là một abstract class được tạo qua `HttpClient.newHttpClient()` hoặc `HttpClient.newBuilder().build()`, có `send` và `sendAsync`, nhưng **chưa** khai báo `AutoCloseable` hay các method lifecycle mới.

Đến **Java 21**, `HttpClient` triển khai `AutoCloseable` và bổ sung năm method liên quan:

| Method / hành vi | Java 11–20, gồm Java 17 | Java 21+ | Mục đích |
|---|---|---|---|
| `send(...)`, `sendAsync(...)` | Có | Có | Gửi request đồng bộ/bất đồng bộ |
| `HttpClient.newBuilder().build()` | Có | Có | Tạo client dùng nhiều lần |
| `close()` trên `HttpClient` | **Không** | **Có** | Orderly shutdown, chờ client terminated |
| `shutdown()` | **Không** | **Có** | Bắt đầu orderly shutdown, trả về không đợi request cũ |
| `shutdownNow()` | **Không** | **Có** | Cố khởi động immediate shutdown |
| `awaitTermination(Duration)` | **Không** | **Có** | Chờ các hoạt động còn lại hoàn tất sau shutdown |
| `isTerminated()` | **Không** | **Có** | Hỏi các hoạt động đã hoàn tất sau shutdown chưa |
| `try (HttpClient c = ...)` | **Không hợp lệ** trong Java 17 | **Hợp lệ** từ Java 21 | Tự gọi `close()` khi ra khỏi khối |

**Không** đồng nhất `HttpClient` với `ExecutorService`. Hai loại có vài method cùng tên (`shutdown`, `shutdownNow`, `awaitTermination`), nhưng chúng là hai API khác nhau, tham số cũng khác. Với `HttpClient`, `awaitTermination` nhận **`java.time.Duration`**; với `ExecutorService`, method truyền thống nhận **`long timeout, TimeUnit unit`**.

Lý do cần xác định version theo **compiler/release target**, không chỉ JVM runtime: nếu máy chạy JDK 24 nhưng dự án `javac --release 17`, bạn vẫn **không thể** biên dịch lời gọi `HttpClient.shutdown()` vì API Java 17 không khai báo nó. Ngược lại, mã được biên dịch dùng API Java 21 không nên được chạy trên JVM 17.

### Ví dụ lỗi khi nhầm phiên bản

~~~java
// Không hợp lệ với API HttpClient của Java 17:
try (HttpClient client = HttpClient.newHttpClient()) {
    client.shutdown();
    client.awaitTermination(Duration.ofSeconds(2));
}
~~~

Đây là **ví dụ cố ý không biên dịch trên JDK 17**, để minh họa sự khác biệt. Ngoài import `java.net.http.HttpClient`, `java.time.Duration`, mã còn cần môi trường compile **Java 21+** thì mới có những symbol đó. Các chương trình chạy được riêng cho Java 17 và 21 được cung cấp ở phần sau.

## 2. Vì sao một HttpClient có vòng đời?

Về API, `HttpClient` sau `build()` là **bất biến về cấu hình** (preferred version, redirect policy, proxy, TLS context...), nhưng việc gửi request cần tài nguyên **có trạng thái runtime**:

- **Connection pool / keep-alive:** client có thể giữ những kết nối còn dùng được để reuse thay vì mở lại TCP/TLS connection cho mọi request.
- **HTTP/2 multiplexing:** một TCP/TLS connection có thể phục vụ nhiều HTTP streams. Không đồng nghĩa “một response xong thì đóng socket”.
- **Công việc asynchronous:** `sendAsync` có futures, callbacks, body subscribers, network operations có thể còn đang chạy.
- **Response streaming:** người dùng có thể đã nhận `HttpResponse<InputStream>` nhưng chưa đọc hết bytes; xử lý body chưa hoàn tất.
- **WebSocket / protocol sessions:** ứng dụng có thể dùng những tài nguyên trao đổi liên tục cần quy định lifecycle riêng.

Vì vậy, **kết thúc một request không nhất thiết là kết thúc mọi hoạt động của client**. Phần implementation của HttpClient có thể tái sử dụng connection, release tài nguyên khi idle, hoặc tiếp tục xử lý background tasks. Việc liên tục tạo client ngắn hạn cho từng request thường giảm khả năng reuse, tăng kết nối và khó kiểm soát tài nguyên.

Khuyến nghị phổ biến: **tạo một client cho một nhóm cấu hình tin cậy/chính sách hợp lý rồi reuse cho nhiều request**. Nếu ứng dụng cần những policy TLS/proxy/cookie tách biệt, có thể tạo các client khác nhau và quản lý vòng đời mỗi client theo phiên bản JDK.

### “Immutable” không có nghĩa không cần shutdown

`HttpClient` không có public setters để sửa client sau build, nhưng:
- `send`/`sendAsync` vẫn tạo operations;
- connection pool và các hoạt động mạng vẫn thay đổi theo thời gian;
- body publishers/subscribers và custom executor có vòng đời khác;
- close/shutdown quyết định **không nhận request mới và kết thúc các công việc đang tiến hành**.

Đừng suy ra “client immutable thì Java tự giải phóng ngay khi response được trả về”; nhất là khi response được xử lý bằng stream mà người gọi chưa đóng.

## 3. Trạng thái vòng đời Java 21+

Sơ đồ đơn giản:

~~~text
     HttpClient.newBuilder().build()
                    │
                    ▼
        ACTIVE / nhận request mới
                    │
          shutdown() hoặc close()
                    │
                    ▼
    SHUTTING DOWN / không nhận request mới
       │            │
       │            └─ request cũ và xử lý response body
       │               được phép hoàn tất theo orderly policy
       │
       ├─ awaitTermination(Duration) → chờ / hết hạn / interrupt
       │
       ├─ shutdownNow() → cố ngắt sớm các hoạt động đang chạy
       │                  (best effort, không đảm bảo tức thì)
       │
       ▼
             TERMINATED
        isTerminated() == true
~~~

**Điểm phân biệt:** `shutdown()` **không tự chờ**, `awaitTermination(...)` **không tự khởi động shutdown**, `close()` **vừa khởi động orderly shutdown vừa chờ**, còn `shutdownNow()` là yêu cầu dừng nhanh hơn nhưng không có bảo đảm hủy sạch ngay lập tức.

`isTerminated()` theo hợp đồng Java 21 chỉ có thể trả `true` sau một lần `shutdown()` hoặc `shutdownNow()`. Một client không có request nào **chưa** được shutdown vẫn **không được xem đã terminated** chỉ vì nó đang idle.

Không có method khôi phục một client đã shutdown về trạng thái ACTIVE. Nếu muốn gửi request mới sau khi dừng, tạo một `HttpClient` khác và đặt lại policy.

### Bảng hành vi ngắn gọn

| API (Java 21+) | Có chờ khi gọi? | Request đã nộp trước đó? | Request mới? | Cam kết |
|---|---|---|---|---|
| `shutdown()` | **Không** | Được cho hoàn tất theo orderly shutdown | Không nhận nữa | Bắt đầu quá trình |
| `awaitTermination(Duration d)` | Chờ tối đa `d` khi `d > 0` | Quan sát tiến trình kết thúc | Không quyết định; cần shutdown trước | `true` đã terminated, `false` hết thời hạn |
| `shutdownNow()` | **Không đợi hoàn tất** | Có thể bị gián đoạn/hủy, nhưng không đảm bảo | Không nhận nữa | **Nỗ lực** kết thúc sớm |
| `close()` | **Có thể chờ lâu** | Cố đợi hoàn tất | Không nhận nữa | Chờ cho tới terminated theo contract |
| `isTerminated()` | Không | Không tác động | Không tác động | Đọc trạng thái, không kích hoạt shutdown |

**Cẩn thận về từ “graceful”:** graceful shutdown không cam kết các request sẽ luôn thành công, cũng không hoàn tất mọi công việc nghiệp vụ ở downstream. Nó cho phép các operations đang tiến hành hoàn thành trong điều kiện có thể. Network failure, timeout, lỗi publisher/subscriber vẫn có thể làm request thất bại.

## 4. `shutdown()`: orderly nhưng trả về ngay

Theo JDK 21:

~~~java
client.shutdown();
// Không nộp thêm request mới cho client này.
// Các request đã submit có thể vẫn đang thực thi.
~~~

Snippet trên giả định `client` là `HttpClient` của JDK 21+. `shutdown()`:
1. **Khởi động** một quy trình orderly shutdown.
2. Không chấp nhận những request mới nộp bằng `send` hoặc `sendAsync`.
3. Cho các request đã nộp trước đó tiếp tục các operations cần thiết để hoàn thành — gồm cả hoạt động đợi body được phân phối tới người tiêu thụ.
4. **Không chờ** chúng hoàn thành trước khi trả về. Nếu muốn đợi thì gọi `awaitTermination(Duration)` hoặc `close()`.

Gọi `shutdown()` lại khi client đã shutdown không tạo hiệu ứng bổ sung theo Javadoc. Nhưng “không đợi” không phải “đã close xong”: ngay sau khi gọi, `isTerminated()` có thể vẫn `false`.

### Thời điểm từ chối request mới

Trong hệ thống nhiều thread, cần **dừng producer** tạo request và quy định thời điểm shutdown. Nếu một thread còn gọi `sendAsync()` đồng thời thread khác gọi `shutdown()`, thứ tự hai sự kiện có thể quyết định request ấy được chấp nhận hay bị từ chối. Không dựa vào việc các operations nộp sau khi shutdown sẽ “được xếp hàng đợi khi client mở lại”: không có bước mở lại.

**Không phụ thuộc vào loại exception chính xác** khi nộp request mới vào client đã shutdown: code ứng dụng nên bảo đảm không submit tiếp theo policy và xử lý failure hợp lý, thay vì viết logic giả định một thông báo exception duy nhất trên mọi implementation.

## 5. `awaitTermination(Duration)` và `isTerminated()`: quan sát kết thúc

Hợp đồng Java 21:

~~~java
client.shutdown();
boolean finished = client.awaitTermination(Duration.ofSeconds(3));

if (finished) {
    System.out.println("HTTP client terminated");
} else {
    System.out.println("Still terminating after 3s");
}
~~~

Đây là snippet Java 21+, cần import `java.time.Duration` và giả định `client` đã build. `awaitTermination` trả:
- `true` khi client terminated trong thời gian chờ;
- `false` khi hết thời hạn chờ mà chưa terminated;
- ném `InterruptedException` khi thread đang đợi bị interrupt.

**`Duration.ZERO` hoặc thời hạn âm:** method **không chờ** mà chỉ kiểm tra trạng thái ở thời điểm đó. Không dùng `awaitTermination(Duration.ZERO)` như một lệnh “đợi mãi”; nó khác hẳn một số API timeout khác.

**Giá trị timeout không phải deadline cứng cho shutdown:** `awaitTermination(Duration.ofSeconds(3))` giới hạn **lần đợi ấy**, không ép mọi network/body work tự dừng ở giây thứ ba. Sau khi nhận `false`, các tasks cũ có thể vẫn đang chạy và cần chính sách xử lý tiếp.

`isTerminated()` là cách hỏi trạng thái tức thời:

~~~java
client.shutdown();
System.out.println(client.isTerminated()); // true hoặc false tùy thời điểm.
~~~

Không viết unit test assert `isTerminated() == true` **ngay lập tức** sau `shutdown()` khi còn hoạt động async. Chỉ khẳng định chắc hơn sau khi `awaitTermination(...)` trả `true` trên implementation đúng hợp đồng.

### Interrupt đúng cách

Khi `awaitTermination` bị interrupt, ứng dụng phải quyết định dừng nhanh, báo lỗi hoặc truyền ngắt lên caller. Mẫu bảo toàn tín hiệu:

~~~java
try {
    boolean finished = client.awaitTermination(Duration.ofSeconds(3));
    if (!finished) {
        client.shutdownNow();
    }
} catch (InterruptedException ex) {
    client.shutdownNow(); // Nỗ lực kết thúc sớm, không phải guarantee.
    Thread.currentThread().interrupt();
    throw ex;
}
~~~

Snippet trên dành cho Java 21+, nằm trong method có `throws InterruptedException` hoặc được xử lý phù hợp. Sau khi catch, đặt lại cờ interrupt rồi truyền exception; không nuốt interrupt để tiếp tục đợi vô thời hạn.

## 6. `shutdownNow()`: best effort, không phải “kill everything”

`HttpClient.shutdownNow()` của Java 21 **cố gắng** khởi động immediate shutdown. Theo API, implementation *có thể cố interrupt* các operations đang chạy; hành vi của operations khi bị interrupt không được bảo đảm hoàn toàn. Không có cam kết rằng:

- Mọi socket lập tức đóng trước khi `shutdownNow()` trả về.
- Mọi `CompletableFuture` được complete hoặc complete exceptionally trong thời hạn cố định.
- Mọi `send()` bị block đều được giải phóng ngay.
- Server **chưa** nhận/thực hiện request đã gửi.
- Mọi tài nguyên bên ngoài như executor tự cấp, file/network stream của ứng dụng được dọn tự động.

Vì vậy đừng dùng `shutdownNow()` như cơ chế rollback request POST đã bắt đầu: server có thể đã tạo giao dịch trước khi client hủy. Đối với request không idempotent, cần idempotency key hoặc cơ chế xác nhận trạng thái server.

**Về subclass:** `HttpClient` là abstract class. Implementation mặc định của JDK override các method lifecycle mới theo hướng **best effort**. Theo phần *Implementation Requirements* của Java 21, nếu một subclass không override `shutdownNow()`, implementation base mặc định chỉ gọi `shutdown()`; do đó tuyệt đối không suy diễn “mọi HttpClient implementation sẽ interrupt thật”.

### Graceful trước, immediate nếu vượt deadline

Một đoạn xử lý Java 21+ thường hợp lý hơn gọi `close()` vô điều kiện:

~~~java
client.shutdown();
boolean done;
try {
    done = client.awaitTermination(Duration.ofSeconds(5));
} catch (InterruptedException ex) {
    client.shutdownNow();
    Thread.currentThread().interrupt();
    throw ex;
}

if (!done) {
    client.shutdownNow();
    // Nếu còn thời gian, có thể awaitTermination một lần nữa.
    // Không giả định lệnh trên bảo đảm dừng ngay.
}
~~~

Đây là snippet, cần `java.time.Duration` và `client` đã có. Thực tế phải ngừng nộp request mới, quản lý các futures/streams và xác định thời hạn hoàn tất riêng trước khi shutdown.

**Khi `awaitTermination` lần hai cũng trả false:** ghi nhận shutdown chưa hoàn tất; không chuyển thành câu kết luận “đã đóng hết” chỉ vì đã gọi `shutdownNow()`.

## 7. `close()`: orderly shutdown **và chờ**

Java 21 bổ sung `AutoCloseable` cho `HttpClient`. Vì vậy có thể viết:

~~~java
try (HttpClient client = HttpClient.newHttpClient()) {
    // Gửi request và tiêu thụ/đóng response bodies.
} // Tự gọi client.close().
~~~

Đây là **mẫu Java 21+**, không biên dịch trên JDK 17.

`close()`:
1. Bắt đầu orderly shutdown nếu client chưa shutdown.
2. Chờ các hoạt động còn lại cần thiết cho những request đã submit hoàn tất, tới trạng thái terminated.
3. Không nhận thêm request mới sau khi shutdown được yêu cầu.
4. Nếu bị interrupt trong lúc chờ, `close()` **có thể** gọi `shutdownNow()` để cố dừng hoạt động rồi tiếp tục đợi; trước khi trả về, trạng thái interrupt được phục hồi theo tài liệu.
5. Nếu client đã terminated, gọi `close()` lại không có tác dụng đáng kể.

**Quan trọng:** `close()` **không có tham số timeout**, do đó **không phù hợp để áp một deadline cứng** khi code khác còn giữ response stream/subscription chưa dọn. Ngay cả khi đã yêu cầu `shutdownNow()` từ thread khác, behavior của operations không có bảo đảm sẽ kết thúc ngay.

### Ví dụ so sánh

~~~java
// Java 21+:
client.shutdown();                  // Bắt đầu đóng, không chờ.
client.awaitTermination(Duration.ofSeconds(2)); // Đợi tối đa 2 giây.
client.shutdownNow();               // Cố đóng nhanh hơn, không chờ.

// Khác với:
client.close(); // Orderly shutdown và ĐỢI tới terminated.
~~~

Các câu lệnh trên chỉ là **so sánh semantics**, không phải hướng dẫn gọi lần lượt cả bốn trên cùng một client. Trong app, chọn đúng **một chính sách lifecycle**: scoped `try-with-resources`, hoặc graceful có thời hạn/force fallback. Không dùng chuỗi lệnh vô nghĩa chỉ để “chắc đã đóng”.

## 8. Hai ví dụ Java 17 và Java 21+ đã kiểm thử

Hai chương trình sau **độc lập**, cùng tạo `HttpServer` trên loopback `127.0.0.1` với cổng động `0`, rồi dùng `HttpClient` gọi `GET /ping` nhận `PONG`. Mục tiêu là kiểm tra **API lifecycle khác nhau**, không phải minh họa production HTTP server.

- **Ví dụ A:** biên dịch với `--release 17`; cố tình **không dùng** `HttpClient.close/shutdown`.
- **Ví dụ B:** biên dịch với `--release 21`; dùng `try-with-resources`, `shutdown`, `awaitTermination`, `shutdownNow`, `isTerminated`.

Chúng đã được biên dịch và chạy bằng JDK hiện đại có `javac --release 17` / `--release 21` để kiểm tra **API compatibility**. Chạy bytecode thực tế bằng JVM đúng version tương ứng vẫn cần môi trường có đầy đủ JDK/modules. Không cần tên miền ngoài hoặc chứng chỉ TLS.

### 8.1. Ví dụ A — tương thích Java 17

Lưu trọn vẹn thành **`HttpClient17Demo.java`**:

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

public class HttpClient17Demo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ping", exchange -> {
            byte[] bytes = "PONG".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort() + "/ping");
            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET().build();
            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("Java 17 status: " + response.statusCode());
            System.out.println("Java 17 body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Lệnh biên dịch/chạy với **JDK 17**:

~~~bash
javac -encoding UTF-8 HttpClient17Demo.java
java HttpClient17Demo
~~~

Khi kiểm tra **khả năng dùng API Java 17** bằng compiler JDK mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 HttpClient17Demo.java
java HttpClient17Demo
~~~

Stdout trong thử nghiệm thành công:

~~~text
Java 17 status: 200
Java 17 body: PONG
~~~

**Giải thích:**
- `HttpClient` trong JDK 17 tạo client và dùng `send` bình thường.
- `BodyHandlers.ofString` tiêu thụ response body vào `String`; không để lại `InputStream` cho ứng dụng phải tự đọc.
- Không có `client.close()`, `client.shutdown()` hoặc `client.awaitTermination(Duration)` trong mã Java 17. Khi kết thúc process, OS thu hồi tài nguyên tiến trình; trong service chạy lâu, quản lý số lượng client và request/stream lifecycle thay vì tạo client mới vô hạn.
- `server.stop(0)` đóng **HTTP server listener của bài**, hoàn toàn không phải lời gọi lifecycle lên `HttpClient`.
- Mã demo dùng HTTP không mã hóa trên loopback để thử API; production endpoint nhạy cảm cần HTTPS/TLS và chính sách xác thực phù hợp.

### 8.2. Ví dụ B — Java 21+ và các method lifecycle

Lưu trọn vẹn thành **`HttpClientLifecycle21Demo.java`**:

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

public class HttpClientLifecycle21Demo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ping", exchange -> {
            byte[] bytes = "PONG".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort() + "/ping");
            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3)).GET().build();

            // close() tự được gọi khi ra khỏi khối.
            try (HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1).build()) {
                HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                System.out.println("close example: "
                    + response.statusCode() + " " + response.body());
            }
            System.out.println("close returned");

            HttpClient graceful = HttpClient.newHttpClient();
            graceful.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            graceful.shutdown();
            boolean finished =
                graceful.awaitTermination(Duration.ofSeconds(3));
            System.out.println("graceful terminated: " + finished
                + " / " + graceful.isTerminated());
            if (!finished) {
                graceful.shutdownNow();
            }

            HttpClient forced = HttpClient.newHttpClient();
            forced.shutdownNow();
            boolean stopped =
                forced.awaitTermination(Duration.ofSeconds(3));
            System.out.println("forced terminated: " + stopped
                + " / " + forced.isTerminated());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Dùng **JDK 21 trở lên**:

~~~bash
javac -encoding UTF-8 HttpClientLifecycle21Demo.java
java HttpClientLifecycle21Demo
~~~

Nếu compiler mới hơn nhưng muốn kiểm tra Java 21 API surface:

~~~bash
javac --release 21 -encoding UTF-8 HttpClientLifecycle21Demo.java
java HttpClientLifecycle21Demo
~~~

Stdout đã đo được trên JDK hiện đại (không có pending stream/tasks khi shutdown):

~~~text
close example: 200 PONG
close returned
graceful terminated: true / true
forced terminated: true / true
~~~

**Vì sao đoạn code cố tình có ba client?**
1. **Client trong `try-with-resources`:** gửi GET, hoàn tất response body bằng `ofString`, rồi `close()` được gọi khi ra scope. Dòng `close returned` chỉ xuất hiện khi việc đóng đã trả về.
2. **Client graceful:** hoàn tất request trước, gọi `shutdown()`, `awaitTermination(3s)`, in kết quả `finished` và `isTerminated()`. Trong bài test không có work pending nên cả hai là `true`.
3. **Client forced:** chưa submit request nào, gọi `shutdownNow()` rồi chờ. Trong bài test nó kết thúc thành công; **điều này không chứng minh** shutdownNow luôn làm ngừng các in-flight requests trong 3 giây.

**Không coi hai dòng `true / true` là output đảm bảo cho server bận hoặc custom publisher treo.** Tại các máy hoặc thời điểm khác, `awaitTermination` có thể trả `false`; bộ code nêu rõ cần chính sách xử lý khi timeout. Đây là ví dụ dễ tái lập khi không có pending work, không phải stress test cancellation.

### Không trộn code Java 21 vào Java 17

Dù hai ví dụ dùng chung lớp `HttpClient`, chương trình `HttpClientLifecycle21Demo` dựa vào các method **Since: 21**. Nếu project đặt `maven.compiler.release=17` hoặc Gradle toolchain Java 17, compiler phải báo lỗi nếu bạn copy `shutdown()`/`close()` vào code cũ. Cách sửa là **quản lý lifecycle tương thích JDK17** hoặc **nâng version project có kiểm soát**, chứ không dùng reflection để gọi bừa một phương thức có thể không tồn tại.

## 9. Vì sao `close()` hoặc orderly shutdown có thể bị kẹt ở response body?

Đây là cảnh báo đặc biệt quan trọng trong **Implementation Note on closing the HttpClient** của Javadoc Java 21.

Các `BodyHandlers` trả về các loại body có hợp đồng tiêu thụ khác nhau:

| Response BodyHandler | Body được trả | Khi nào việc đọc body thật sự xong? | Điều cần làm |
|---|---|---|---|
| `BodyHandlers.ofString()` | `String` | Thông thường `HttpResponse` chỉ hoàn tất khi bytes đã được gom/giải mã | Không có stream mở mà caller phải đóng |
| `BodyHandlers.ofByteArray()` | `byte[]` | Bytes được gom vào mảng trước khi body hoàn tất | Giới hạn dữ liệu để tránh memory bloat |
| `BodyHandlers.discarding()` | `Void` | Nội dung response được discard theo handler | Hữu ích khi thực sự không cần body |
| `BodyHandlers.ofInputStream()` | `InputStream` | Body có thể còn đang chờ đọc **sau khi `send` trả response** | Đọc tới EOF hoặc `close()` stream |
| `BodyHandlers.ofLines()` | `Stream<String>` | Stream có thể chưa tiêu thụ hết | Tiêu thụ/`close()` stream |
| `BodyHandlers.ofPublisher()` | Reactive publisher | Còn phụ thuộc subscriber, request demand và cancel | Subscriber phải tiêu thụ/cancel đúng quy tắc |
| Custom `BodySubscriber` | Tùy loại body | Có thể đang đợi downstream request/cancel | Xử lý subscription và cleanup |

Nếu ứng dụng gọi `client.close()` khi một `HttpResponse<InputStream>` đang mở nhưng **không được đọc và không được đóng**, client có thể phải chờ các operations không thể hoàn tất. Tương tự, một subscriber không gửi demand hoặc không cancel có thể **đình trệ orderly shutdown**.

### Đọc stream đúng cách

Với Java 21+ hoặc Java 17, tiêu thụ body `ofInputStream` nên dùng try-with-resources:

~~~java
HttpResponse<InputStream> response = client.send(
    request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream in = response.body()) {
    in.transferTo(OutputStream.nullOutputStream());
} // Stream được đóng trước khi shutdown client.
~~~

Đây là **snippet** cần import `java.io.InputStream`, `java.io.OutputStream` và `java.net.http.HttpResponse`; `client` và `request` đã được tạo. `transferTo` ở đây chỉ minh họa tiêu thụ hết; trong production cần **giới hạn số byte**, timeout và xử lý nội dung/streaming đúng cách, tránh đọc dữ liệu không tin cậy không giới hạn.

**Nếu không cần body:** chọn `BodyHandlers.discarding()`. Nếu stream cần xử lý từng chunk, chủ động `close()` trong `finally` khi không thể đọc hết. Đóng sớm có thể khiến underlying HTTP/1.1 connection không được reuse, nhưng vẫn tốt hơn bỏ rơi stream.

**Với `ofLines()`:** đóng stream khi không còn dùng; không để pipeline lazy giữ resource sau khi đã nhận `HttpResponse`.

**Với `ofPublisher()`:** tuân thủ giao thức `Flow.Subscription.request(n)`, `cancel()` và completion/error handling. Chỉ nhận publisher rồi bỏ đó có thể giữ operations đang pending. Tránh subscriber chặn vô hạn hoặc không bao giờ request data.

### Không nhầm future completed với mọi bytes đã được xử lý

Một `sendAsync(request, BodyHandlers.ofInputStream())` có thể hoàn tất future với `HttpResponse<InputStream>` **trước khi toàn bộ response bytes được người gọi đọc**. `future.join()` chỉ cho biết `HttpResponse` theo BodyHandler đã sẵn sàng, không tự drain hay đóng stream.

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

HttpResponse<InputStream> response = future.join();
try (InputStream in = response.body()) {
    // Tiêu thụ/giới hạn dữ liệu hoặc đóng stream khi không dùng.
}
~~~

Đây là snippet dùng Java 17+ và cần import `java.util.concurrent.CompletableFuture`, `java.io.InputStream`, `java.net.http.HttpResponse`; các biến khác đã được tạo. Trong hệ thống thật cần xử lý `CompletionException` và deadline trước khi chờ `join` vì `join()` không có timeout riêng.

## 10. `sendAsync`, cancellation và tác vụ chưa hoàn tất

`sendAsync(...)` trả về `CompletableFuture<HttpResponse<T>>`. Nếu không còn cần kết quả, ứng dụng có thể yêu cầu hủy:

~~~java
CompletableFuture<HttpResponse<String>> pending =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

boolean requested = pending.cancel(true);
~~~

Đây là snippet dùng Java 17+, không phải chương trình độc lập. Tài liệu JDK nói `cancel(true)` trên future có thể cố hủy HTTP exchange để sớm release resources, nhưng:
- Không đảm bảo thời điểm cancellation tác dụng thực sự.
- Với HTTP/1.1, có thể đóng kết nối đột ngột.
- Với HTTP/2, có thể reset stream hoặc đôi lúc đóng connection.
- Request có thể đã tới server và đã có tác dụng nghiệp vụ.
- `cancel` không thay thế cleanup stream đã trả về trước đó.

**Tính đúng đắn nghiệp vụ:** một `POST /payments` bị cancel không có nghĩa server chưa trừ tiền. Khi retry, cần idempotency key và cơ chế đối soát/trạng thái server. Cách tắt client là chính sách tài nguyên, không phải distributed transaction rollback.

### Hủy futures trước hay sau shutdown?

Trong hệ thống, thường:
1. Ngừng tạo request mới.
2. Đợi một khoảng thời gian cho in-flight operations hoàn tất theo policy.
3. Hủy những futures không cần nữa theo deadline ứng dụng; đóng/cancel body streams/subscriptions.
4. Với Java 21+, gọi `shutdown()` và `awaitTermination`; nếu không hoàn tất, cân nhắc `shutdownNow()`.
5. Ghi nhận các operations còn đang pending và bảo vệ quá trình dừng ứng dụng.

Không có thứ tự “một kích cỡ vừa tất cả”. Có service cần ưu tiên hoàn tất giao dịch, có service cần thoát nhanh. Quan trọng là không gọi `shutdownNow()` rồi báo “mọi request đã bị rollback”.

## 11. Custom ExecutorService không phải HttpClient lifecycle

Một `HttpClient` có thể được build với custom executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);

HttpClient client = HttpClient.newBuilder()
    .executor(executor)
    .build();
~~~

Đây là snippet dùng Java 17+ với import `java.util.concurrent.*` và `java.net.http.HttpClient`.

**Hai đối tượng sở hữu tài nguyên khác nhau:**
- `client.shutdown()` (chỉ từ Java 21) điều khiển **HttpClient operations**.
- `executor.shutdown()` là API của **ExecutorService** và điều khiển **nhận task vào executor**, không phải API đóng HTTP client.
- Việc HttpClient có ngừng sau các requests không tự bảo đảm mọi task ứng dụng chạy trong executor tự cấp đã hoàn tất và executor của ứng dụng được shutdown.
- Trong Java 17, vẫn có thể `executor.shutdown()`, nhưng **không** suy diễn điều đó tương đương `HttpClient.close()` của Java 21.

Thứ tự lifecycle hợp lý khi ứng dụng sở hữu executor:
1. Dừng các producers gửi requests.
2. Đảm bảo streams/futures cần được hoàn tất hoặc hủy theo chính sách.
3. **Java 21+**: shutdown client và đợi (có thời hạn) nếu cần.
4. Sau khi các công việc HTTP còn cần executor đã được xử lý, shutdown **executor ứng dụng sở hữu** riêng và đợi theo API `ExecutorService.awaitTermination(long, TimeUnit)`.
5. Nếu bất kỳ bước nào không kết thúc, báo/đo lường trạng thái, xử lý interrupt theo policy; không mặc định đã đóng sạch.

Nếu shutdown custom executor quá sớm trong khi `sendAsync` còn phụ thuộc vào nó, những tác vụ HTTP còn lại có thể bị từ chối hoặc đình trệ, khiến client khó terminate. Đây là lý do cần tách rõ owner của client và owner của executor.

### Đừng nhầm with server lifecycle

`com.sun.net.httpserver.HttpServer.stop(int delay)` là API dừng **HTTP server**, không phải `HttpClient.shutdown()`. Một chương trình demo có thể vừa chạy server, vừa chạy client; khi dừng phải quản lý hai nhóm tài nguyên riêng. Trong ứng dụng production còn có database pools, thread pools khác và message consumers, tất cả có shutdown policy riêng.

## 12. Chọn shutdown policy theo tình huống

| Tình huống | Lựa chọn thông thường |
|---|---|
| Tool ngắn, Java 21+, đã đọc hết bodies | `try (HttpClient c = ...)` để `close()` tự chạy |
| Service dài hạn, nhiều request | Tạo/reuse client theo cấu hình; dừng khi service shutdown |
| Service cần graceful shutdown tối đa vài giây, Java 21+ | `shutdown()` rồi `awaitTermination(Duration)`; nếu timeout, cân nhắc `shutdownNow()` và theo dõi |
| Đang streaming response lâu dài | Chủ động đóng/cancel streams/subscriptions, không để `close()` chờ không giới hạn |
| App dùng Java 17 | Không gọi API Java 21; reuse client, đặt timeout, cancel futures, đóng body streams, quản lý custom executor và process lifecycle |
| Cần hủy task CPU của application | Quản lý `ExecutorService` riêng, không xem `HttpClient.shutdownNow()` là phương thức hủy tác vụ CPU |
| POST đã gửi nhưng future bị cancel | Không tự retry vô điều kiện; xác minh trạng thái nghiệp vụ/idempotency |
| Dùng custom subclass của `HttpClient` | Đọc contract/override lifecycle; default base methods có semantics tối thiểu |
| Chỉ muốn biết client đã dừng hay chưa | Java 21+: `isTerminated()`; không phải câu lệnh khởi động shutdown |
| Muốn thăm dò không chờ | Java 21+: `awaitTermination(Duration.ZERO)`, nên gọi sau shutdown |

### Tại sao `close()` không thay thế deadline có thời hạn?

Hãy xét:

~~~text
T0  client.send(..., ofInputStream()) trả HttpResponse<InputStream>
T1  ứng dụng chưa đọc hoặc đóng InputStream
T2  thread khác gọi client.close()
T3  close() đợi hoạt động còn lại
T4  stream không được consume/cancel → close có thể chờ rất lâu
~~~

Trong kiến trúc cần stop nhanh, không nên để đường shutdown **phụ thuộc vô hạn** vào một stream mà application không quản lý. Đặt thời hạn cho request, resource cleanup rõ, timeout/grace period; dùng `shutdown/awaitTermination/shutdownNow` để quan sát và ứng xử khi vượt hạn, đồng thời hiểu giới hạn của best-effort cancellation.

## 13. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| Gọi `HttpClient.close()` trên JDK 17 | Method chưa có trong API 17 | Java 17 code phải dùng lifecycle tương thích; nâng JDK nếu cần |
| Nghĩ `HttpClient` luôn `AutoCloseable` từ Java 11 | Chỉ có từ Java 21 | Ghi rõ min Java version khi viết ví dụ |
| Nghĩ `shutdown()` đợi mọi request xong | Method trả về ngay sau khởi động shutdown | Dùng `awaitTermination` hoặc `close` nếu cần đợi |
| Nghĩ `awaitTermination` tự gọi shutdown | Chỉ chờ/kiểm tra trạng thái | Gọi `shutdown` trước |
| Nghĩ `awaitTermination(Duration.ZERO)` chờ vô hạn | Duration không dương là kiểm tra tức thời | Dùng Duration dương cho chờ |
| Nghĩ `shutdownNow()` bảo đảm mọi request ngừng ngay | API chỉ best effort | Theo dõi state, timeout, cancel và cleanup |
| Nghĩ `close()` luôn trả về nhanh | Nó có thể đợi chưa hoàn tất body work | Drain/đóng response streams, dùng policy có deadline |
| Nghĩ `isTerminated()==false` khi idle là lỗi | Chưa shutdown thì không thể true | Phân biệt idle và terminated |
| Dùng `BodyHandlers.ofInputStream` nhưng bỏ mặc body | Giữ pending response delivery | Consume/close stream |
| Dùng `ofPublisher` mà subscriber không request/cancel | Reactive backpressure làm stream treo | Điều khiển subscription và cancel |
| Chỉ gọi `future.cancel(true)` rồi khẳng định server không xử lý POST | Hủy không rollback server state | Idempotency/đối soát |
| Dừng executor tự cấp trước khi HTTP work xong | Async tasks có thể bị từ chối/khó terminate | Quy định thứ tự shutdown theo ownership |
| Shutdown HttpServer rồi xem client đã đóng | Hai object khác nhau | Dọn từng tài nguyên |
| Tạo client mới cho mỗi request | Mất khả năng connection pooling/reuse | Reuse client có cùng policy |
| `try-with-resources` trên Java 21 mà quên streaming body | `close` có thể chờ không mong muốn | Đảm bảo body lifecycle trước khi ra scope |
| Xem kết quả demo forced terminated=true là cam kết | Demo không có pending tasks | Test overload/cancellation riêng |
| Biên dịch với JDK 24 rồi tưởng code dùng được trên Java 17 | Cần `--release 17` để khóa API | Kiểm tra version target của dự án |
| Dùng `ExecutorService.awaitTermination(3, SECONDS)` cho HttpClient | Method signature khác | Dùng `HttpClient.awaitTermination(Duration)` trên Java 21+ |

## 14. Kiểm thử những tình huống quan trọng

Không chỉ chạy một chương trình luôn thành công; để kiểm chứng policy shutdown hãy thiết kế các bài test có **điều kiện dừng rõ**:

1. **Không có pending requests:** tạo client Java 21+, gọi `shutdown()` rồi `awaitTermination(positive duration)`; kết quả thường kết thúc nhanh.
2. **Một request đã nộp và hoàn tất:** gọi `send` với `BodyHandlers.ofString`, sau đó `shutdown`; `awaitTermination` có thể trả true nhanh, như demo.
3. **Request async đang chạy:** server loopback có `CountDownLatch` kiểm soát lúc trả body; `shutdown` không block, `awaitTermination(short duration)` có thể trả false. Thả latch rồi chờ lại và xác minh true theo thời gian hợp lý.
4. **Cancel async future:** gọi `cancel(true)` khi server đã nhận request, kiểm tra client và server logs; không assert request chưa được xử lý.
5. **Unconsumed InputStream:** nhận `HttpResponse<InputStream>` rồi không đọc; kiểm tra graceful shutdown với thời hạn riêng, sau đó đóng stream và chờ lại. Dùng deadline toàn test để tránh treo CI.
6. **Thử ofPublisher không có demand:** xác nhận consumer phải request/cancel; không biến `close()` vô hạn thành test treo.
7. **Custom executor:** nộp requests với executor do ứng dụng sở hữu; dừng client rồi dừng executor theo đúng thứ tự; theo dõi active tasks.
8. **Java 17 compile gate:** biên dịch `HttpClient17Demo.java` với `--release 17` thành công; thử gọi `client.close()` trong source 17 phải bị compiler từ chối.
9. **Java 21 compile gate:** biên dịch `HttpClientLifecycle21Demo.java` với `--release 21`; chạy trên JVM 21+.
10. **Client đã shutdown:** thử submit request mới sau shutdown, xác nhận không được chấp nhận; không phụ thuộc vào message exception cụ thể.
11. **Interrupt thread đang await:** interrupt waiter, xử lý `InterruptedException` đúng policy và bảo toàn interrupt flag.
12. **HTTP/1.1 vs HTTP/2:** kiểm tra behavior cancellation có thể ảnh hưởng socket/stream khác nhau; không hard-code assertion kiểu “luôn đóng đúng một connection”.

Đối với timing tests, tránh `Thread.sleep` để “đoán” request đang chạy; dùng các điểm đồng bộ như `CountDownLatch` và giới hạn thời gian test. `shutdownNow()` chỉ là yêu cầu nỗ lực, do đó không assert mọi OS/network/thread đều dừng trong vài mili giây.

## 15. Bài tập tự kiểm tra

1. Dự án đặt `--release 17`. Dòng `try (HttpClient client = HttpClient.newHttpClient())` có biên dịch được không? Vì sao?
2. Từ Java version nào `HttpClient` hỗ trợ `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)` và `isTerminated()`?
3. Sau `client.shutdown()`, những request đã submit có tự động bị hủy ngay không? Lệnh này có đợi response body kết thúc không?
4. Muốn chờ tối đa 5 giây sau graceful shutdown, gọi method nào? Nếu trả false thì điều đó có nghĩa gì?
5. `client.awaitTermination(Duration.ZERO)` chờ mãi hay chỉ kiểm tra tức thời?
6. Tại sao `isTerminated()` của một client không có request nhưng chưa gọi shutdown vẫn không true?
7. Nêu sự khác biệt căn bản giữa `close()` và `shutdownNow()` về việc chờ và mục tiêu dừng.
8. Response lấy từ `BodyHandlers.ofInputStream()` đã được trả về `HttpResponse`. Vì sao `client.close()` vẫn có thể chờ?
9. Khi dùng `ofLines()` và `ofPublisher()`, người dùng có những trách nhiệm cleanup/demand gì?
10. Nếu `sendAsync` bị `cancel(true)`, có thể kết luận POST đã không được server thực hiện không?
11. Nếu một `HttpClient` dùng `ExecutorService` do ứng dụng tạo, lệnh `client.shutdown()` có tự shutdown mọi thread pool của ứng dụng không?
12. Khi `awaitTermination` bị interrupt, nên xử lý thế nào để không mất tín hiệu interrupt?
13. Trong ví dụ Java 21, tại sao `forced terminated: true / true` không chứng minh mọi active request có thể bị dừng trong 3 giây?
14. `HttpClient.close()` có timeout parameter không? Nếu muốn deadline shutdown có quan sát được thì nên dùng tổ hợp method nào?
15. Phân biệt `HttpClient.awaitTermination(Duration)` và `ExecutorService.awaitTermination(long, TimeUnit)`.
16. Tại sao có thể build một `HttpClient` và dùng lại qua nhiều request thay vì xây mới mỗi lần?
17. Nếu ứng dụng còn giữ `InputStream` được trả từ một response, khi shutdown app nên làm gì với stream trước khi đóng client?
18. Vì sao Java 17 không có `close()` không đồng nghĩa rằng có thể bỏ qua timeout và resource cleanup?

**Gợi ý đáp án:**
(1) Không, Java 17 `HttpClient` chưa triển khai `AutoCloseable`; (2) Java 21; (3) không, orderly cho request trước đó hoàn tất và `shutdown` không chờ; (4) `awaitTermination(Duration.ofSeconds(5))`, false là chưa terminated trước timeout; (5) kiểm tra tức thời; (6) cần shutdown trước; (7) `close` orderly + chờ, `shutdownNow` nỗ lực dừng nhanh không đợi; (8) body chưa tiêu thụ/đóng vẫn cần network work; (9) đóng stream hoặc yêu cầu/cancel subscription đúng contract; (10) không; (11) không, phải quản lý executor riêng; (12) xử lý và khôi phục interrupt/propagate; (13) demo không có pending work; (14) không, dùng `shutdown + awaitTermination + shutdownNow` theo policy; (15) khác API và chữ ký; (16) reuse connection/resource; (17) đọc hết/close/cancel; (18) Java 17 vẫn cần quản lý streams, futures, timeout và vòng đời ứng dụng.

## 16. Ghi nhớ

- **JDK version là ranh giới cứng:** Java 17 chưa có HttpClient lifecycle methods; **Java 21+** mới có `close/shutdown/shutdownNow/awaitTermination/isTerminated` và `AutoCloseable`.
- **`shutdown()`** khởi động orderly shutdown và trả ngay; **`awaitTermination(Duration)`** đợi có thời hạn; **`isTerminated()`** chỉ quan sát trạng thái; **`close()`** orderly và đợi đến terminated; **`shutdownNow()`** cố dừng nhanh nhưng không bảo đảm tác vụ đã xong.
- **Body lifecycle quyết định shutdown có tiến triển hay không:** stream/publisher không được đọc/đóng/cancel có thể giữ request pending, làm `close()` chờ.
- **Quản lý theo owner:** HTTP client, executor tự cấp, HTTP server và request futures khác nhau; phải có thứ tự dọn riêng.
- **Đừng xem cancel như rollback:** request có thể đã tới server. Retry các thao tác gây tác dụng phụ phải tuân thủ idempotency/đối soát.
- **Dùng hai ví dụ đúng phiên bản:** Java 17 không gọi API 21; Java 21 có thể dùng `try-with-resources` và graceful shutdown có thời hạn.
- **Kiểm tra bằng thực nghiệm có deadline:** quá tải, interrupt, body streaming và slow downstream cần test riêng; output các bài đơn giản không đại diện tất cả tình huống.

### Tài liệu tham khảo

- [Oracle Java SE 17 — HttpClient (không có lifecycle APIs từ 21)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 21 — HttpClient (close/shutdown/shutdownNow/awaitTermination/isTerminated)](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 21 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 21 — ExecutorService (phân biệt shutdown APIs)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Inside Java — AutoCloseable HttpClient, tài liệu kỹ thuật về API bổ sung từ JDK 21](https://inside.java/2023/12/10/sip092/)
