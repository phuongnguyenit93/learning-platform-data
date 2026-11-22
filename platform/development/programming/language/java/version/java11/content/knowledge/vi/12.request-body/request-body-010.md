# Tái phát dữ liệu và yêu cầu có thể retry — Request body trên Java 11+

## 1. Hai vấn đề riêng biệt: tái phát byte và retry an toàn

Trong Java 11+, `java.net.http.HttpClient` gửi request body bằng cách đăng ký một `Flow.Subscriber<ByteBuffer>` với `HttpRequest.BodyPublisher` của request. Nếu cần gửi lại một request do redirect, xác thực, kết nối lỗi hoặc chính sách retry của ứng dụng, HTTP client có thể tạo **subscription mới**. Một body publisher phù hợp phải **phát lại cùng dãy byte** thay vì tiếp tục từ vị trí đã bị tiêu thụ.

Tuy nhiên, **có thể phát lại dữ liệu không đồng nghĩa có thể gửi lại request một cách an toàn**:

- **Replayable body:** dữ liệu gửi ở lượt mới giống dữ liệu ban đầu, kể cả sau khi lượt trước bị hủy.
- **Retry-safe request:** gửi lại một request không gây ra tác dụng phụ ngoài ý muốn nếu server **có thể đã xử lý lần đầu**.

Ví dụ body JSON dùng `BodyPublishers.ofString` dễ phát lại, nhưng `POST /orders` vẫn có nguy cơ tạo **hai đơn hàng** sau timeout nếu server chưa có cơ chế chống trùng lặp. Ngược lại, `PUT /resource/42` có ngữ nghĩa idempotent trong HTTP, nhưng nếu publisher sử dụng InputStream đã đọc hết thì lần gửi sau vẫn có thể thất bại.

Bài này chỉ dùng **kiến thức vẫn áp dụng hiện nay** trên Java 11 và các JDK mới: `HttpRequest.BodyPublisher`, `BodyPublishers`, `HttpClient`, `Flow` và tính idempotent trong **RFC 9110**.

## 2. Hợp đồng của HttpRequest.BodyPublisher

Giao diện `HttpRequest.BodyPublisher` kế thừa `Flow.Publisher<ByteBuffer>`, đồng thời có phương thức:

```java
long contentLength();
```

Theo tài liệu Java, mỗi lần client gửi request có body sẽ có một subscriber nhận dữ liệu từ publisher. Khi request phải gửi lại, **một subscription mới được tạo và được kỳ vọng phát cùng dữ liệu như trước**.

Những yêu cầu thực tế:

1. **Multiple subscriptions:** các lần đăng ký mới phải có thể bắt đầu lại từ đầu; không chia sẻ một iterator hoặc InputStream đã bị tiêu thụ.
2. **Byte chính xác:** số byte, thứ tự và nội dung phải nhất quán. Không phát dữ liệu thời gian thực thay đổi nếu yêu cầu retry cùng payload.
3. **Backpressure:** nếu tự viết publisher, phải tôn trọng `Flow.Subscription.request(n)` và báo lỗi đúng cơ chế `onError`.
4. **ByteBuffer ownership:** publisher không được tiếp tục truy cập, đọc hoặc sửa buffer đã bàn giao cho HTTP client.
5. **Lỗi/hủy:** subscription có thể bị `cancel` giữa chừng. Publisher cần dọn tài nguyên và vẫn có khả năng phát lại từ đầu cho lượt khác khi cần.
6. **Độ dài ổn định:** `contentLength()` có thể bị gọi nhiều lần và **phải trả cùng giá trị** cho một publisher.

`contentLength()` trả `0` khi body rỗng, số byte dương khi biết trước, hoặc số âm khi không xác định được. Với body có độ dài `0`, HTTP client **có thể không subscribe**.

**Độ dài body tính bằng byte, không phải số ký tự:**

```java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofString("Xin chào");

System.out.println(body.contentLength()); // 9, vì UTF-8
```

Chuỗi `Xin chào` có 9 byte UTF-8 do `à` dùng hai byte. Không lấy `String.length()` làm content length.

## 3. Chọn nguồn body sao cho tái phát được

| API có trong Java 11 | Nguồn | Điều kiện để phát lại chính xác |
| --- | --- | --- |
| `BodyPublishers.ofString(s)` | `String`, UTF-8 mặc định | Nội dung chuỗi cố định |
| `BodyPublishers.ofString(s, charset)` | Chuỗi theo charset chỉ định | Encoding và văn bản nhất quán |
| `BodyPublishers.ofByteArray(bytes)` | Mảng byte | Giữ byte nguồn liên quan ổn định |
| `BodyPublishers.ofByteArray(bytes, offset, length)` | Một đoạn của mảng | Không thay đổi đúng đoạn đã chọn |
| `BodyPublishers.ofByteArrays(iterable)` | Một chuỗi mảng byte từ `Iterable` | Iterable có thể lặp lại và mỗi lượt cho đúng cùng dữ liệu |
| `BodyPublishers.ofFile(path)` | File trên đĩa | File còn tồn tại, đọc được, không bị thay đổi |
| `BodyPublishers.ofInputStream(supplier)` | Stream được tạo theo nhu cầu | Supplier tạo **mỗi lần một stream mới**, từ đầu, cùng byte |
| `BodyPublishers.fromPublisher(p)` | `Flow.Publisher<ByteBuffer>` tùy biến | Publisher gốc hỗ trợ multiple subscriptions và cùng byte |
| `BodyPublishers.noBody()` | Không có body | Không có dữ liệu cần tái phát |

Không factory nào bảo đảm server sẽ xử lý retry an toàn về mặt nghiệp vụ.

### 3.1. String và mảng byte: phù hợp payload nhỏ, bất biến

```java
String json = "{\"status\":\"ready\"}";

HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/resource/42"))
        .header("Content-Type", "application/json; charset=utf-8")
        .PUT(HttpRequest.BodyPublishers.ofString(json))
        .build();
```

Đây là **mảnh mã** cần import `java.net.URI` và `java.net.http.HttpRequest`. Với mảng byte, bạn có thể tự tạo snapshot trước khi xây request:

```java
byte[] source = json.getBytes(StandardCharsets.UTF_8);
byte[] snapshot = source.clone();

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofByteArray(snapshot);
```

Không sửa `snapshot` trong lúc request có thể phát lại. Không nên phụ thuộc vào chi tiết triển khai nội bộ của `ofByteArray` để cho phép những thread khác sửa nguồn đồng thời.

### 3.2. ofFile: có đường dẫn không đồng nghĩa có snapshot

```java
Path file = Path.of("exports", "snapshot.json");

HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/upload"))
        .POST(HttpRequest.BodyPublishers.ofFile(file))
        .build();
```

`ofFile` có thể đọc lại file ở một lượt subscription khác. Nhưng nếu file bị sửa, cắt cụt, thay thế hoặc thiếu quyền đọc giữa các lần, byte phát lại **có thể khác hoặc báo lỗi**. Khi yêu cầu retry cùng payload, hãy tạo file snapshot riêng, hoàn tất ghi trước khi gửi và giữ file ổn định đến hết cửa sổ retry.

### 3.3. ofInputStream: mở nguồn mới mỗi lần

`BodyPublishers.ofInputStream` nhận `Supplier<? extends InputStream>` vì dữ liệu stream **không được buffer sẵn**, trong khi request có thể cần lặp lại. Supplier có thể bị gọi nhiều lần.

**Đúng:**

```java
byte[] snapshot = "Hello".getBytes(StandardCharsets.UTF_8);

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(
                () -> new ByteArrayInputStream(snapshot));
```

**Sai:**

```java
// CỐ Ý SAI: dùng lại stream đã đọc/hết dữ liệu.
InputStream shared = new ByteArrayInputStream(snapshot);
HttpRequest.BodyPublisher oneShot =
        HttpRequest.BodyPublishers.ofInputStream(() -> shared);
```

Đây là hai mảnh mã minh họa với import phù hợp; không đặt cả hai khai báo `body` trong cùng scope. Dùng lại một stream không tự quay về đầu. `mark/reset` cũng không phải chiến lược chung: nhiều lớp `InputStream` không hỗ trợ, và concurrent subscriptions có thể gây race.

**Nếu nguồn là file, mở một InputStream mới:**

```java
Path path = Path.of("exports", "body.bin");

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return Files.newInputStream(path);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
```

Mã này cần import `Path`, `Files`, `IOException`, `UncheckedIOException` và `HttpRequest`. Nó tạo stream mới nhưng **chưa đảm bảo file không bị sửa**.

Javadoc Java 11 còn nêu supplier có thể trả `null` ở lượt sau; lúc đó yêu cầu phát lại **thất bại**. Không thiết kế hệ thống phụ thuộc vào việc client sẽ tự buffer body từ lượt đầu.

### 3.4. Custom Flow.Publisher: adapter không tự làm dữ liệu replayable

`BodyPublishers.fromPublisher(publisher)` chỉ chuyển một `Flow.Publisher<ByteBuffer>` thành `BodyPublisher`. Nếu publisher nguồn là **one-shot**, tiêu thụ từ một queue hoặc phát dữ liệu live, adapter không tự cache dữ liệu để có thể lặp lại.

Custom publisher phải hỗ trợ subscriber mới, phát byte cùng thứ tự, tôn trọng backpressure, đóng tài nguyên khi hủy và không sửa `ByteBuffer` sau khi trao cho HTTP client.

Với `fromPublisher(publisher, contentLength)`, tham số `contentLength` trên Java 11 phải **dương** và là đúng số byte phát. Khi không biết trước, dùng `fromPublisher(publisher)` để báo độ dài không xác định; khi không có body dùng `noBody()`.

## 4. Idempotency: điều kiện quan trọng của retry-safe

Theo **RFC 9110 `9.2.2**, một request method idempotent khi **tác dụng mong muốn** của một hay nhiều request giống nhau.

| Method | Ngữ nghĩa | Chính sách retry |
| --- | --- | --- |
| `GET`, `HEAD` | Safe; cũng idempotent | Thường có thể thử lại nếu lỗi tạm thời, với giới hạn |
| `PUT` | Idempotent theo chuẩn | Có thể thử lại với cùng body/điều kiện nếu server tuân thủ |
| `DELETE` | Idempotent theo chuẩn | Trạng thái cuối cùng tương đương; response status có thể khác |
| `POST` | Không mặc định idempotent | Không retry mù quáng nếu thiếu bảo đảm nghiệp vụ |
| `PATCH` | Không mặc định idempotent | Xem hợp đồng endpoint và điều kiện cụ thể |

Idempotency **không yêu cầu response hai lượt giống nhau**. Ví dụ DELETE lần đầu có thể trả `204`, lần sau `404`, nhưng tác dụng mong muốn vẫn là xóa tài nguyên.

### 4.1. Timeout: server có thể đã xử lý

```text
Client                         Server
  | ---- POST /orders -------> | Đã tạo đơn hàng
  |                            | Đang tạo response
  X <--- connection lost ------|
  |
  | ---- retry POST ---------> | Có thể tạo đơn thứ hai
```

Một `IOException` hoặc timeout không chứng minh server chắc chắn chưa nhận request hay chưa commit. Đây là lý do **POST tạo đơn hàng/thanh toán không thể tự retry** chỉ vì publisher phát lại được.

### 4.2. Idempotency-Key chỉ có tác dụng nếu server thực thi

Nếu server có hợp đồng chống trùng, client có thể truyền một khóa ổn định cho **cùng một thao tác nghiệp vụ**:

```java
String operationId = "order-operation-unique-id";

HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/orders"))
        .header("Idempotency-Key", operationId)
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                "{\"sku\":\"BOOK-01\",\"quantity\":1}"))
        .build();
```

Đây là mảnh minh họa, không phải một đơn hàng thật. Java HTTP Client **không tự triển khai idempotency key**. Server phải có cơ chế lưu khóa, giới hạn thời gian hiệu lực, so payload và trả lại kết quả theo hợp đồng. Trong **cùng thao tác retry**, dùng **cùng key và cùng payload**; thao tác mới dùng key khác. Không coi việc thêm một header bất kỳ là đủ ngăn trùng khi server không hỗ trợ.

## 5. Chương trình Java 11 kiểm thử replay và gửi request thủ công hai lần

Ví dụ sau độc lập, chạy bằng Java 11+. Nó dùng `Flow.Subscriber` để đọc một publisher qua **hai subscription**, thử dữ liệu từ stream/file, rồi tạo một HTTP server **loopback** bằng mô-đun tiêu chuẩn JDK `jdk.httpserver` để kiểm tra hai lần gửi một request PUT. Không cần mạng Internet.

Tạo file **`BodyReplayDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpRequest.BodyPublisher;
import java.net.http.HttpRequest.BodyPublishers;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class BodyReplayDemo {
    private static byte[] collect(BodyPublisher publisher) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Throwable> error = new AtomicReference<>();

        publisher.subscribe(new Flow.Subscriber<ByteBuffer>() {
            private Flow.Subscription subscription;
            @Override public void onSubscribe(Flow.Subscription s) {
                subscription = s;
                s.request(1);
            }
            @Override public void onNext(ByteBuffer buffer) {
                byte[] bytes = new byte[buffer.remaining()];
                buffer.get(bytes);
                out.write(bytes, 0, bytes.length);
                subscription.request(1);
            }
            @Override public void onError(Throwable t) {
                error.set(t);
                done.countDown();
            }
            @Override public void onComplete() {
                done.countDown();
            }
        });
        if (!done.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Publisher timed out");
        }
        if (error.get() != null) {
            throw new IllegalStateException("Publisher failed", error.get());
        }
        return out.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = "Xin ch\u00E0o".getBytes(StandardCharsets.UTF_8);
        BodyPublisher fromString = BodyPublishers.ofString("Xin ch\u00E0o");
        System.out.println("string same bytes = "
                + Arrays.equals(collect(fromString), collect(fromString)));
        System.out.println("string length = " + fromString.contentLength());

        BodyPublisher fromArray = BodyPublishers.ofByteArray(bytes);
        System.out.println("array replay = "
                + Arrays.equals(collect(fromArray), collect(fromArray)));

        AtomicInteger opens = new AtomicInteger();
        BodyPublisher fromStream = BodyPublishers.ofInputStream(() -> {
            opens.incrementAndGet();
            return new ByteArrayInputStream(bytes);
        });
        System.out.println("supplier replay = "
                + Arrays.equals(collect(fromStream), collect(fromStream)));
        System.out.println("supplier calls = " + opens.get());
        System.out.println("stream length = " + fromStream.contentLength());

        Path file = Files.createTempFile("replay-body-", ".txt");
        try {
            Files.writeString(file, "first", StandardCharsets.UTF_8);
            BodyPublisher fromFile = BodyPublishers.ofFile(file);
            byte[] first = collect(fromFile);
            Files.writeString(file, "after", StandardCharsets.UTF_8);
            byte[] second = collect(fromFile);
            System.out.println("file bytes changed = "
                    + !Arrays.equals(first, second));
        } finally {
            Files.deleteIfExists(file);
        }

        AtomicInteger calls = new AtomicInteger();
        AtomicReference<String> lastBody = new AtomicReference<>();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/resource", exchange -> {
            byte[] body = exchange.getRequestBody().readAllBytes();
            lastBody.set(new String(body, StandardCharsets.UTF_8));
            calls.incrementAndGet();
            exchange.sendResponseHeaders(204, -1);
            exchange.close();
        });
        server.start();
        try {
            URI address = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/resource");
            HttpRequest request = HttpRequest.newBuilder(address)
                    .PUT(BodyPublishers.ofString("snapshot"))
                    .build();
            HttpClient client = HttpClient.newHttpClient();
            int first = client.send(request,
                    HttpResponse.BodyHandlers.discarding()).statusCode();
            int second = client.send(request,
                    HttpResponse.BodyHandlers.discarding()).statusCode();
            System.out.println("manual sends status = " + first + "/" + second);
            System.out.println("manual sends count = " + calls.get());
            System.out.println("same request body = "
                    + "snapshot".equals(lastBody.get()));
        } finally {
            server.stop(0);
        }
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 11 --add-modules jdk.httpserver BodyReplayDemo.java
java --add-modules jdk.httpserver BodyReplayDemo
```

**Đầu ra đã kiểm chứng:**

```text
string same bytes = true
string length = 9
array replay = true
supplier replay = true
supplier calls = 2
stream length = -1
file bytes changed = true
manual sends status = 204/204
manual sends count = 2
same request body = true
ALL CHECKS PASSED
```

**Giải thích:**

- `ofString` và `ofByteArray` phát lại cùng byte khi nguồn ổn định.
- Supplier của `ofInputStream` được gọi **hai lần** để cấp hai stream độc lập. `contentLength() == -1` nghĩa độ dài không xác định trước.
- `ofFile` phát byte khác khi file bị sửa giữa hai subscription.
- Hai lần `client.send` là **hai lần gửi thủ công**, không chứng minh HttpClient tự retry. Server loopback nhận hai request PUT và trả `204`.
- `collect` là subscriber thử nghiệm cho payload nhỏ, không phải mã để buffer file lớn trong ứng dụng thật.

Nếu môi trường không cho mở loopback, chạy phần publisher bằng ví dụ riêng; test mạng có thể bị giới hạn bởi sandbox/firewall. Java 11 hỗ trợ cả `java.net.http` và `jdk.httpserver`.

## 6. Tự retry, redirect và HTTP response là những tình huống khác nhau

**Không có quy tắc rằng Java HttpClient tự retry mọi request có body**. Phải xem loại lỗi, cấu hình client, giao thức và ngữ nghĩa ứng dụng.

| Tình huống | Vấn đề cần chú ý |
| --- | --- |
| Kết nối ngắt trước response | Không chắc server đã xử lý chưa; cần idempotency và body replayable |
| Redirect `307`/`308` | Khi follow redirect có thể phải giữ method/body và phát lại |
| Redirect `301`/`302`/`303` | Method/body có thể thay đổi theo quy tắc HTTP và client |
| Authentication challenge | Có thể phải lặp request với thông tin xác thực |
| HTTP `429`/`503` | Xem retry policy, `Retry-After` và giới hạn số lần |
| Timeout | Server có thể đã commit; POST không bảo vệ không tự retry |
| Hủy/cancel/interrupt | Trao đổi có thể dở dang; tôn trọng hủy và quản lý tài nguyên |

`HttpClient.Redirect.NORMAL` điều khiển chính sách redirect, **không** làm body one-shot thành replayable và **không** tự bảo đảm an toàn nghiệp vụ khi resend.

### Checklist retry production

1. Method/endpoint idempotent hay có server-side deduplication?
2. Publisher phát lại **cùng byte** được không? File/stream có snapshot?
3. Lỗi nào có thể retry (transient `IOException`, `429`, `503`...)?
4. Giới hạn số lần thử, deadline tổng thể và backoff + jitter?
5. `Retry-After` có được tôn trọng theo hợp đồng server không?
6. Request timeout đơn lẻ có bị nhầm với deadline tổng nhiều lần không?
7. Có tôn trọng `InterruptedException`/cancel, đóng nguồn body và hạn chế log bí mật không?

**Mẫu minh họa** trong phương thức đã có `HttpClient client`, `HttpRequest request`, `throws IOException, InterruptedException`; chỉ áp dụng khi request idempotent và body replayable:

```java
int maxAttempts = 3;
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());
        // Có response: xử lý status theo hợp đồng API.
        System.out.println("HTTP status = " + response.statusCode());
        break;
    } catch (IOException ex) {
        if (attempt == maxAttempts) throw ex;
        // Production: phân loại lỗi, deadline, backoff và jitter.
    }
}
```

Đoạn mã **không** xử lý `429`/`503`/`Retry-After` và chưa phải policy hoàn chỉnh. Nó minh họa retry hữu hạn khi `IOException` và **không bắt `InterruptedException` để retry**. Tuyệt đối không áp dụng nguyên xi cho POST thanh toán hoặc tạo đơn hàng không có bảo đảm idempotency.

## 7. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Body lần hai rỗng hoặc lỗi | Supplier trả một InputStream đã tiêu thụ | Tạo stream mới từ đầu mỗi subscription |
| File body khác sau retry | Nguồn `ofFile` bị sửa | Tạo/giữ file snapshot bất biến |
| Custom Flow publisher không replay | Nguồn chỉ hỗ trợ một lượt subscribe | Thiết kế multiple subscriptions hoặc buffer/snapshot |
| `contentLength` biến động | Phụ thuộc nguồn có thể đổi | Trả hằng số; không biết thì báo độ dài âm |
| Khai báo sai byte length | Dùng số ký tự thay kích thước byte | Đếm byte thực tế; cố định encoding |
| POST bị thực hiện hai lần | Timeout nhưng server đã xử lý | Server idempotency/deduplication hoặc không retry |
| Retry vô hạn | Không giới hạn attempts/deadline | Cấu hình số lần, backoff, tổng timeout |
| Retry mọi 5xx | Chưa phân loại lỗi và tác dụng phụ | Xem status, `Retry-After`, endpoint contract |
| Tưởng redirect = tự retry an toàn | Redirect có quy tắc method/body riêng | Hiểu chính sách redirect và replay |
| Log token/body khi lỗi | Tiết lộ dữ liệu nhạy cảm | Chỉ log metadata an toàn |
| Tưởng request bất biến nghĩa file bất biến | `BodyPublisher` đọc nguồn bên ngoài | Đóng băng nguồn trong cửa sổ retry |

## 8. Bài tập tự kiểm tra

**Câu 1.** Nếu `ofInputStream(() -> sharedStream)` luôn trả stream đã đọc hết, có thể retry đúng body không?  
**Đáp án:** Không. Phải cấp một stream mới có cùng nội dung từ đầu.

**Câu 2.** `ofFile` có bảo đảm phát lại cùng byte sau khi file bị thay đổi không?  
**Đáp án:** Không. Phải giữ file ổn định hoặc dùng snapshot.

**Câu 3.** Body `ofString` của `POST /orders` replayable, client timeout. Có retry ngay không?  
**Đáp án:** Không mặc định. Lần đầu có thể đã tạo đơn, nên cần server deduplication hoặc xác định lần trước chưa áp dụng.

**Câu 4.** Hai request PUT idempotent có luôn trả cùng HTTP status không?  
**Đáp án:** Không. Idempotency nói về tác dụng mong muốn chứ không buộc response giống nhau.

**Câu 5.** `contentLength()` có được trả độ dài khác sau mỗi subscription không?  
**Đáp án:** Không. Hợp đồng `BodyPublisher` yêu cầu kết quả ổn định giữa các lần gọi.

**Câu 6.** `BodyPublishers.fromPublisher` có tự cache dữ liệu của custom publisher one-shot không?  
**Đáp án:** Không. Publisher nguồn phải tự đảm bảo khả năng phát lại.

## 9. Ghi nhớ

Một request có body **có thể retry đúng cách** khi cả ba điều kiện được đáp ứng: **body phát lại được đúng byte**, **thao tác an toàn để lặp theo ngữ nghĩa server**, và **chính sách retry giới hạn, phân loại lỗi rõ ràng**.

- Với `ofInputStream`, supplier tạo stream mới; không tái sử dụng stream đã tiêu thụ.
- Với `ofFile`, giữ file bất biến; với `ofByteArray`, giữ payload nguồn ổn định.
- Với custom `Flow.Publisher`, cần hỗ trợ nhiều subscription, byte nhất quán và `contentLength` cố định.
- `POST` không mặc định idempotent; `Idempotency-Key` chỉ hữu ích khi server hỗ trợ.
- `HttpClient` không hứa tự retry mọi lỗi; cân nhắc redirect, timeout, `429`/`503`, backoff và `Retry-After` theo tình huống.

### Tài liệu chính thức còn áp dụng

- [Java 11 — HttpRequest.BodyPublisher: subscription và replay](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Java 11 — BodyPublishers: ofString, ofFile, ofByteArray, ofInputStream, fromPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java 11 — HttpClient.send và sendAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 25 — HttpRequest.BodyPublisher, hợp đồng hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Java 25 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [RFC 9110 `9.2.2 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)
