# Quản lý vòng đời `java.net.http.HttpClient` theo JDK và ứng dụng hiện hành

## 1. Vì sao vòng đời HTTP client quan trọng?

`java.net.http.HttpClient` là HTTP client chính thức trong module `java.net.http` từ Java 11. Một client có thể gửi nhiều yêu cầu đồng bộ (`send`) và bất đồng bộ (`sendAsync`); sau khi xây dựng, cấu hình của client là bất biến. Client có thể quản lý những tài nguyên như kết nối, bộ đệm và công việc I/O nền. Vì vậy việc tạo client, tái sử dụng, đóng response body và dừng ứng dụng cần được thiết kế theo **phiên bản JDK đang chạy** và **phạm vi sở hữu tài nguyên**.

Câu hỏi thực tế không chỉ là “có nên gọi `close()` không?” mà gồm:

- Client được chia sẻ trên toàn ứng dụng hay tạo theo mỗi tác vụ?
- JDK mục tiêu là 11/17 hay 21 trở lên?
- Có request và stream response chưa xử lý xong không?
- Executor do ai tạo, ai chịu trách nhiệm dừng?
- Ứng dụng đang shutdown hay chỉ kết thúc một request?
- Framework đang quản lý bean/service hay code Java thuần tự quản lý?

**Nguyên tắc xuyên suốt:** tái sử dụng client ổn định khi cùng cấu hình, quản lý vòng đời theo phạm vi ứng dụng/service, xử lý response body đúng cách, và chỉ dùng những phương thức shutdown thực sự có trên JDK mục tiêu. Kiến thức trong bài còn áp dụng trên JDK hiện đại; phần khác biệt giữa JDK được ghi rõ, không áp dụng nhầm API mới vào Java 11.

## 2. Khác biệt theo phiên bản JDK: điểm quyết định

| JDK mục tiêu | `HttpClient` có `AutoCloseable`? | Có `close()`/`shutdown()`/`awaitTermination()`? | Chiến lược |
| --- | --- | --- | --- |
| **Java 11** | Không | Không | Tạo và tái sử dụng client theo vòng đời service/app; đóng/tiêu thụ body stream; tự quản lý executor do ứng dụng tạo; không gọi phương thức shutdown chưa tồn tại |
| **Java 17** | Không | Không | Cùng nhóm hợp đồng API với Java 11; không suy ra Java 17 có `HttpClient.close()` |
| **Java 21** | Có | Có | Có thể dùng `try-with-resources` cho client có phạm vi ngắn, hoặc `close`/`shutdown` khi app kết thúc; lưu ý thao tác đóng chờ request/body đang hoạt động |
| **Java 25 và các JDK mới có API tương ứng** | Có | Có | Quản lý lifecycle rõ ràng; chọn graceful shutdown, bounded wait và cancellation theo yêu cầu hệ thống |

Theo tài liệu Java SE 21, các phương thức `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)` và `isTerminated()` được thêm từ **Java 21**; `HttpClient` từ phiên bản đó triển khai `AutoCloseable`. Trên Java 11 và 17, những phương thức đó **không thuộc API**, nên mã như sau **không biên dịch được với `--release 11`**:

```java
// Chỉ dành cho JDK 21+, KHÔNG dùng khi biên dịch --release 11.
try (HttpClient client = HttpClient.newHttpClient()) {
    // ...
}
```

Nếu đang bảo trì hệ thống chạy Java 11, **không gợi ý “chỉ cần `client.close()`”**. Nếu nâng cấp lên JDK 21+, xem xét thay đổi vòng đời thật sự theo Javadoc hiện hành, thay vì suy đoán rằng các JDK có hành vi giống nhau.

## 3. Client không đồng nghĩa với một request

`HttpClient` và `HttpRequest` có vai trò khác nhau:

- **`HttpClient`**: chứa cấu hình dùng chung (HTTP version ưu tiên, chính sách redirect, proxy, SSL, authenticator, executor, connect timeout); có thể gửi nhiều request. Cấu hình được chốt sau khi `build()`.
- **`HttpRequest`**: mô tả một yêu cầu cụ thể: URL, method, headers, request timeout, request body. Đối tượng request được tạo bằng builder rồi có thể được gửi qua client.
- **`HttpResponse<T>`**: thể hiện kết quả cho một yêu cầu. Loại `BodyHandler<T>` quyết định response body được đưa vào `String`, tệp, `InputStream`, luồng dòng hay dạng publisher.
- **`CompletableFuture<HttpResponse<T>>`**: biểu diễn kết quả bất đồng bộ, không phải một client thứ hai. Khi workflow kết thúc vẫn phải xử lý các tài nguyên của response.

**Khuyến nghị cho nhiều request có cùng chính sách:** dùng một client chia sẻ có vòng đời đủ dài (hoặc một nhóm nhỏ client ứng với các cấu hình độc lập), thay vì tạo một client mới sau mỗi lời gọi HTTP. Javadoc nhấn mạnh client hỗ trợ chia sẻ tài nguyên giữa các request. Tạo client liên tục có thể làm giảm cơ hội tái sử dụng kết nối và tăng chi phí tài nguyên; tác động cụ thể tùy cấu hình, tải và JDK, cần đo trong môi trường thực tế.

Client có thể dùng đồng thời từ nhiều luồng cho các request; không nên coi nó là “đối tượng chỉ dùng một lần”. Không thay đổi `HttpClient` đã build bằng cách gọi builder lần nữa: muốn cấu hình khác thì tạo client khác, có chính sách sở hữu riêng.

## 4. Chọn phạm vi sở hữu trong ứng dụng

### 4.1. Service hoặc ứng dụng dài hạn

Phù hợp cho REST backend, worker và chương trình có nhiều lần gọi ra ngoài.

```java
import java.net.http.HttpClient;
import java.time.Duration;

public final class SharedHttpClient {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private SharedHttpClient() {}

    public static HttpClient get() {
        return CLIENT;
    }
}
```

Đây là **một lớp Java 11 hợp lệ**, nhưng không có `main`. Khi cấu hình gắn chặt với ứng dụng, dùng một instance chia sẻ như trên là phương án đơn giản. Với dependency injection (DI), thường nên tạo một bean/service `HttpClient` duy nhất và đưa vào các component cần sử dụng, thay vì dùng biến tĩnh toàn cục nếu ứng dụng cần test hoặc thay đổi cấu hình.

Không tạo một client riêng trong mỗi phương thức nghiệp vụ chỉ vì muốn gửi một request. Cũng không phải mọi hệ thống đều chỉ được phép có *một* client: có thể cần các client khác nhau cho TLS, proxy, authenticator hoặc timeout/configuration độc lập.

### 4.2. CLI ngắn hạn hoặc tác vụ có giới hạn

Trên **JDK 21+**, một client sở hữu độc quyền trong một khối công việc có thể được đóng bằng `try-with-resources`. Trên **JDK 11**, `HttpClient` không hỗ trợ cách này; chương trình CLI thường kết thúc cùng tiến trình JVM, nhưng vẫn cần chờ tác vụ của mình hoàn tất và đóng các body stream/file/executor mà ứng dụng quản lý.

Điều quan trọng: **không lấy “tiến trình sẽ tự kết thúc” làm giải pháp cho server chạy lâu**. Đối với server, phải có chính sách hoàn thành/cancel request và sở hữu các tài nguyên khác.

### 4.3. Framework và ứng dụng quản lý bean

Với framework DI, ưu tiên giữ cấu hình tập trung, tạo client khi module/service được khởi tạo và quản lý giải phóng tài nguyên khi container shutdown theo khả năng của JDK:

- Java 11/17: không khai báo một callback gọi `HttpClient.close`; callback của ứng dụng có thể ngừng nhận việc mới, đợi request, đóng tài nguyên response và xử lý executor **do ứng dụng sở hữu**.
- Java 21+: chỉ callback đóng client khi bean **thực sự là chủ sở hữu**. Nếu client được framework hoặc module khác sở hữu, không gọi đóng từ một consumer bất kỳ.
- Một service được dựng để dùng lâu không nên đóng client mỗi khi một request nghiệp vụ hoàn thành; làm thế sẽ ảnh hưởng các request đang dùng chung client.
- Trong test, nếu cần tạo client riêng và thay đổi TLS/ủy quyền/timeout theo từng test, quản lý sở hữu và teardown riêng để tránh chồng chéo với client dùng chung production.

Không dùng nguyên một kiểu lifecycle cho cả `java.net.http.HttpClient` của JDK và các HTTP client của thư viện thứ ba; chúng có API đóng và mô hình sở hữu khác nhau.

## 5. Chương trình Java 11 hoàn chỉnh: tái sử dụng client, không gọi API shutdown mới

Chương trình dưới đây minh họa lifecycle **không cần mạng**: tạo client một lần, dùng lại trong các lần xây dựng request và in thông tin cấu hình. Lưu mã vào **`HttpClientLifecycle11Demo.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

public class HttpClientLifecycle11Demo {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    static HttpClient sharedClient() {
        return CLIENT;
    }

    static HttpRequest buildRequest(String url) {
        return HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    public static void main(String[] args) {
        HttpClient first = sharedClient();
        HttpClient second = sharedClient();
        HttpRequest request = buildRequest(
                "https://example.com/api");

        System.out.println("Same client: " + (first == second));
        System.out.println("HTTP version: " + first.version());
        System.out.println("Redirects: " + first.followRedirects());
        System.out.println("Connect timeout seconds: "
                + first.connectTimeout().orElseThrow().getSeconds());
        System.out.println("Request timeout seconds: "
                + request.timeout().orElseThrow().getSeconds());
        System.out.println("Request method: " + request.method());
    }
}
```

Biên dịch bằng JDK 11 (hoặc JDK mới hơn có hỗ trợ biên dịch mục tiêu 11):

```bash
javac --release 11 -encoding UTF-8 HttpClientLifecycle11Demo.java
java HttpClientLifecycle11Demo
```

**Kết quả xác định:**

```text
Same client: true
HTTP version: HTTP_1_1
Redirects: NEVER
Connect timeout seconds: 3
Request timeout seconds: 5
Request method: GET
```

Đây là chương trình chạy hoàn chỉnh và **không gửi HTTP request**, nên không cần Internet, server ngoài hay dữ liệu thực nghiệm. Trong một ứng dụng thật, `sharedClient()` được dùng để gửi nhiều `HttpRequest` khác nhau thông qua `send` hoặc `sendAsync`.

**Điểm quan trọng:** mã `--release 11` không gọi `close`, `shutdown` hay `awaitTermination` trên client, vì những API này không có trên Java 11. Việc không có các phương thức đó không đồng nghĩa có thể bỏ qua tài nguyên response hoặc executor do chính ứng dụng tạo.

## 6. Vòng đời response body thường quan trọng không kém vòng đời client

Mặc dù nhiều dạng `BodyHandler` trả về body đã thu thập hoàn chỉnh, có dạng trả về tài nguyên cần được tiêu thụ hoặc đóng:

| `BodyHandler` | Giá trị body | Điều cần quản lý |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | Toàn bộ nội dung body được thu thập vào bộ nhớ; cần giới hạn kích thước response theo yêu cầu |
| `BodyHandlers.ofByteArray()` | `byte[]` | Toàn bộ byte được giữ trong heap; cân nhắc với response lớn |
| `BodyHandlers.ofFile(path)` | `Path` | Response được ghi ra tệp; xử lý kết quả/tệp theo vòng đời dữ liệu |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Đọc đến EOF hoặc đóng stream**; không bỏ quên stream mở |
| `BodyHandlers.ofLines()` | `Stream<String>` | Đóng stream bằng `try-with-resources`; terminal operation cần chạy theo hợp đồng |
| `BodyHandlers.ofPublisher()` | `Publisher<List<ByteBuffer>>` | Đăng ký subscriber và yêu cầu dữ liệu/cancel khi không tiếp tục; quản lý backpressure |

Javadoc của các JDK hiện đại lưu ý việc không đọc hết, đóng hoặc hủy các stream/subscription có thể **cản trở graceful shutdown**. Bản chất rủi ro tài nguyên cũng cần chú ý trên JDK 11.

### 6.1. Ví dụ xử lý `InputStream` đúng

**Trích đoạn Java 11, cần khai báo URL hợp lệ và xử lý `IOException`/`InterruptedException` trong một phương thức:**

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/data")).GET().build();

HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    while (body.read(buffer) != -1) {
        // Xử lý từng khối; không tự động giữ toàn bộ body.
    }
}
```

Cần các import: `java.net.URI`, `java.net.http.HttpRequest`, `java.net.http.HttpResponse` và `java.io.InputStream`; `client` là `HttpClient` do caller hoặc DI cung cấp. Đoạn này **không phải chương trình đầy đủ**, không chạy nếu chưa cấu hình endpoint. Khi không thể đọc hết, vẫn cần **đóng body stream** để ứng dụng không giữ tài nguyên không cần thiết. Việc đóng có thể ảnh hưởng khả năng tái sử dụng kết nối tùy giao thức và hiện trạng trao đổi; không hứa chắc chắn một kết nối luôn được tái sử dụng.

Nếu lấy body là `Stream<String>` từ `ofLines()`, dùng `try (Stream<String> lines = response.body()) { ... }` theo cùng nguyên tắc. Với `ofPublisher()`, phải thiết kế subscription đúng, không coi “đã nhận `HttpResponse`” là đã hoàn tất việc tiêu thụ nội dung.

### 6.2. Không quên timeout, backpressure và giới hạn body

Một client sử dụng lâu có thể tích lũy request chờ nếu không quản lý tải:

- `connectTimeout` trên client giới hạn giai đoạn thiết lập kết nối (theo hợp đồng API); không phải timeout bao trùm mọi xử lý request.
- `HttpRequest.Builder.timeout(Duration)` giới hạn thời gian thực hiện request theo hợp đồng API; nên định nghĩa deadline cấp nghiệp vụ và kiểm tra hành vi của body streaming.
- `BodyHandlers.ofString` hoặc `ofByteArray` giữ nội dung trong bộ nhớ: không phù hợp nếu payload lớn/không giới hạn. Dùng streaming hoặc ghi file, và thực thi ràng buộc kích thước phía ứng dụng.
- Cần giới hạn concurrency/in-flight requests theo khả năng downstream; dùng semaphore, queue có giới hạn hoặc cơ chế quản trị tương đương. Tái sử dụng client **không** đồng nghĩa client tự biết giới hạn nghiệp vụ của hệ thống.

## 7. Executor: phân biệt quyền sở hữu và việc shutdown

`HttpClient.Builder.executor(Executor)` cho phép cung cấp executor riêng. Đó là một **tài nguyên khác** với chính `HttpClient`.

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
HttpClient client = HttpClient.newBuilder()
        .executor(executor)
        .build();
```

Đây là **trích đoạn Java 11**, cần import `java.util.concurrent.ExecutorService`, `java.util.concurrent.Executors` và `java.net.http.HttpClient`. Nó không đóng tài nguyên và không phải toàn bộ chương trình.

Nếu ứng dụng **tạo và sở hữu** executor này, ứng dụng cần lên kế hoạch `executor.shutdown()` và chờ kết thúc theo vòng đời thực tế. **Không shutdown executor ngay sau khi gửi `sendAsync`** nếu các tác vụ liên quan vẫn cần nó. Cũng không shutdown một executor mà nhiều module khác đang chia sẻ trừ khi bạn là owner được xác định.

Trên Java 11/17, `HttpClient` không có `close()`, nhưng `ExecutorService` vẫn có `shutdown()` và `awaitTermination(...)`. Đừng nhầm `executor.shutdown()` là API đóng toàn bộ HTTP client hoặc toàn bộ connection pool. Trường hợp client dùng executor mặc định và `client.executor()` trả `Optional.empty()`, bạn không có một executor sở hữu để shutdown qua API đó.

Mô hình dừng hợp lý với executor do ứng dụng sở hữu:

1. Ngừng chấp nhận tác vụ HTTP mới.
2. Chờ hoặc hủy các tác vụ `sendAsync` theo deadline phù hợp, và xử lý/đóng response body đang giữ.
3. Khi công việc phụ thuộc executor đã kết thúc, shutdown **executor do ứng dụng sở hữu** và chờ có giới hạn.
4. Nếu vẫn còn tác vụ không hoàn tất, thực hiện chính sách lỗi/hủy và ghi log phù hợp; `shutdownNow()` trên `ExecutorService` là nỗ lực dừng, không bảo đảm mọi tác vụ sẽ chấm dứt.
5. Đảm bảo hệ thống logging, metrics, callback và những module khác không tiếp tục gửi request qua client sau mốc dừng.

Không dựa vào các thread mặc định là daemon hay non-daemon để định nghĩa chính sách shutdown, vì chi tiết triển khai và môi trường có thể thay đổi.

## 8. Java 21+: đóng client có chủ đích

**Phần này chỉ dành cho JDK 21 trở lên. Không biên dịch bằng `javac --release 11`.**

Từ Java 21, `HttpClient` triển khai `AutoCloseable` và có các phương thức:

| Phương thức | Ngữ nghĩa |
| --- | --- |
| `close()` | Bắt đầu graceful shutdown, không nhận request mới và **đợi** các operation của request trước đó hoàn tất/terminated |
| `shutdown()` | Bắt đầu graceful shutdown **không chờ**; request mới không được chấp nhận |
| `awaitTermination(Duration)` | Chờ có giới hạn sau yêu cầu dừng; trả `true` nếu đã terminated, `false` nếu hết thời gian |
| `shutdownNow()` | Cố gắng dừng ngay; không cam kết chấm dứt ngay hay mọi tác vụ đều được thông báo |
| `isTerminated()` | Cho biết đã hoàn tất toàn bộ operation sau khi shutdown |

Các phương thức shutdown **không thay thế** việc tiêu thụ/đóng response body. Theo Javadoc Java 21+, một body `InputStream`/`Stream<String>` chưa đọc hết hoặc chưa đóng, hay publisher/subscriber bị đình trệ, có thể khiến graceful shutdown chờ lâu hoặc không thể hoàn tất.

### 8.1. Client có phạm vi ngắn và owner rõ ràng

Ví dụ **JDK 21+**, không có request được gửi:

```java
import java.net.http.HttpClient;

public class ShortLivedClient21Demo {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newHttpClient()) {
            System.out.println("Client created");
        }
        System.out.println("Client closed");
    }
}
```

Biên dịch/chạy trên JDK 21+:

```bash
javac --release 21 ShortLivedClient21Demo.java
java ShortLivedClient21Demo
```

Đầu ra:

```text
Client created
Client closed
```

Chỉ dùng mẫu này khi client **thuộc sở hữu của khối lệnh**; không dùng `try-with-resources` để đóng một client singleton/bean dùng chung ngay giữa đời ứng dụng.

### 8.2. Đợi có giới hạn trước khi buộc dừng

Khi ứng dụng có thời hạn shutdown, thường **không muốn block vô thời hạn** chỉ bằng `close()`. Có thể chủ động dừng theo tiến trình:

```java
// Trích đoạn JDK 21+, cần java.time.Duration và HttpClient.
client.shutdown();
if (!client.awaitTermination(Duration.ofSeconds(5))) {
    client.shutdownNow();
    if (!client.awaitTermination(Duration.ofSeconds(2))) {
        System.err.println("HTTP client still not terminated");
    }
}
```

Đây là **trích đoạn**, không phải chương trình độc lập. Phương thức `awaitTermination` có thể ném `InterruptedException`, nên cần xử lý ngắt trong lifecycle hook (thường khôi phục cờ interrupt nếu bắt và không ném tiếp). `shutdownNow` là **best effort**, không phải bảo đảm tuyệt đối sẽ kết thúc mọi request tức thì.

`close()` có thể đợi các operation đang chạy; nếu bị ngắt, tài liệu API Java 21 mô tả việc nó có thể thử dừng nhanh rồi vẫn tiếp tục đợi. Vì thế, chọn cơ chế shutdown dựa trên yêu cầu vận hành, không tùy tiện dùng blocking `close()` trên event loop hoặc thread có deadline ngắn.

## 9. Request bất đồng bộ, cancellation và graceful shutdown

`sendAsync` trả về `CompletableFuture<HttpResponse<T>>`. Vòng đời một request bất đồng bộ bao gồm: khởi tạo → I/O → xử lý response body → tác vụ downstream → thành công/thất bại/cancel. **Đừng nhầm hoàn tất một `CompletableFuture` mà bạn tự bọc bên ngoài với việc mọi tài nguyên network đã được giải phóng ngay lập tức.**

Một cách quản lý phù hợp:

- Theo dõi số request đang xử lý (in-flight), timeout, failure và tỷ lệ cancel.
- Chặn nhận yêu cầu mới khi bắt đầu shutdown.
- Chờ các request trước đó theo deadline, sau đó hủy những request không còn cần thiết.
- Trên JDK mới, dùng shutdown của client sau khi đã xử lý luồng response/cancellation; trên JDK 11, không có phương thức đóng client tương tự.
- Với request thất bại, đừng retry vô hạn; cân nhắc idempotency và exponential backoff. Hành động retry nên được dừng trong giai đoạn shutdown.

**Phân biệt timeout:**

1. `HttpRequest.timeout` là cấu hình request HTTP.
2. `CompletableFuture.orTimeout` tạo deadline ở tầng completion của future; không nên tự động suy ra nó đã dừng mọi tác vụ I/O nền theo đúng thời điểm.
3. `CompletableFuture.cancel(...)` yêu cầu hủy future; tùy JDK và implementation có thể tác động đến exchange, nhưng không đảm bảo server chưa xử lý request hoặc tài nguyên đã biến mất ngay.

Cần xử lý `IOException`, `InterruptedException` (với `send`), và lỗi completion bất đồng bộ; khi nhận interrupt trong code đồng bộ mà không ném tiếp, thường khôi phục `Thread.currentThread().interrupt()`.

## 10. Ví dụ kiến trúc vòng đời theo loại ứng dụng

| Loại ứng dụng | Chủ sở hữu client | Khi tạo | Khi dừng | Điểm cần đặc biệt chú ý |
| --- | --- | --- | --- | --- |
| Backend HTTP server | DI container hoặc outbound HTTP service | Khi khởi động bean/service | Khi ngừng service/container | Nhiều request dùng chung; giới hạn concurrency; body stream không để rò rỉ |
| Batch worker dài hạn | Worker controller | Trước nhiều tác vụ | Khi worker shutdown hoặc đổi cấu hình | Hạn chế tạo client/tác vụ; quản lý in-flight và retries |
| Desktop app | Application network layer | Khi network layer khởi tạo | Khi đóng app/module tương ứng | Không block UI thread trong thời gian chờ shutdown |
| CLI nhỏ | `main`/scoped owner | Trong một lần chạy | Sau các request thuộc CLI | JDK 11 không `close()` client; JDK 21+ có `try-with-resources` |
| Test integration | Test fixture hoặc test container | Trước một nhóm test | Sau test group | Không đóng client chia sẻ bởi test khác; dọn tài nguyên response |

**Chú ý với thay đổi cấu hình:** vì `HttpClient` bất biến, thay đổi proxy/authenticator/TLS policy có thể cần tạo client mới. Thiết kế chuyển giao: tạo client mới, ngừng tạo request trên client cũ, cho request cũ kết thúc/cancel, sau đó giải phóng theo API của JDK. Không hoán đổi client đang dùng mà làm mất kiểm soát future/stream đang mở.

## 11. Dấu hiệu vận hành và checklist

Quan sát những số liệu sau trong môi trường thực tế:

- Số HTTP request đang xử lý; phân bố latency p95/p99; timeout/cancel/failure; tỷ lệ retry.
- Số body stream/response chưa tiêu thụ xong, các task bất đồng bộ treo và thời gian shutdown thực.
- Tài nguyên executor do ứng dụng sở hữu: active threads, queued tasks, rejection, thời gian đóng.
- Kết nối đang mở/được giữ theo khả năng quan sát của runtime; không suy đoán pool được đóng chỉ vì object request ra khỏi scope.
- Kích thước response, đặc biệt khi dùng `ofString`/`ofByteArray`, để tránh rủi ro heap không kiểm soát.

Trước khi triển khai, kiểm tra:

1. **JDK thật**: ứng dụng compile và chạy trên phiên bản nào? Có gọi API `close/shutdown` chỉ có từ 21 trong mã phải chạy trên 11/17 không?
2. **Ownership**: ai tạo client và ai chịu trách nhiệm ngừng sử dụng/đóng? Consumer có đang đóng client dùng chung sai thời điểm không?
3. **Scope**: client có được tái sử dụng trong nhiều request cùng cấu hình không?
4. **Body**: mọi `InputStream`, `Stream<String>` hoặc publisher đều được tiêu thụ/đóng/cancel đúng cách chưa?
5. **Executor**: do ai tạo? Có ai shutdown trước khi tác vụ HTTP hoàn tất không?
6. **Deadline**: timeout connect/request/operation và thời hạn graceful shutdown đã được định nghĩa rõ chưa?
7. **Concurrency**: có giới hạn số request đồng thời và chiến lược backpressure không?
8. **Khả năng test**: có test nhiều request song song, cancellation, response stream chưa đọc hết, shutdown khi đang tải và đổi cấu hình không?
9. **Observability**: có số liệu để phát hiện resource leak và shutdown treo không?
10. **Vận hành**: có xử lý lỗi, log và interrupt rõ ràng thay vì bắt rồi bỏ qua không?

## 12. Những lỗi hay gặp và cách sửa

| Sai lầm | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Gọi `client.close()` trong Java 11 hoặc 17 | Lỗi biên dịch vì không có API | Không gọi; quản lý vòng đời ứng dụng và tài nguyên thực sự sở hữu |
| Cứ mỗi request tạo `newHttpClient()` | Tăng chi phí khởi tạo và giảm khả năng chia sẻ kết nối | Tái sử dụng client theo service/config |
| Đóng client singleton sau một request ở JDK 21+ | Các request khác trên client dùng chung không được nhận/hoàn tất | Chỉ owner đóng tại teardown |
| Bỏ quên `response.body()` kiểu stream | Có thể giữ kết nối hoặc làm graceful shutdown treo | Đọc đến hết/đóng/cancel đúng giao thức |
| Dùng `ofString()` cho body không giới hạn | Có thể tăng đỉnh heap | Dùng streaming/giới hạn byte |
| Shutdown executor ngay sau `sendAsync()` | Tác vụ async phụ thuộc executor có thể bị ảnh hưởng | Dừng nhận việc, chờ hoàn tất rồi shutdown executor owner |
| Nghĩ `executor.shutdown()` tương đương `client.close()` | Không quản lý hết các tài nguyên của client | Phân biệt executor và HTTP client |
| Dùng `close()` khi cần deadline cứng | Có thể chờ lâu vì task/body bị đình trệ | Xem `shutdown` + `awaitTermination` + `shutdownNow` (JDK 21+) |
| Nghĩ `shutdownNow` bảo đảm dừng ngay | Có thể còn task/connection chưa dừng | Ghi log, xử lý kết quả best effort |
| Dựa vào `future.orTimeout` để khẳng định HTTP exchange đã hủy | Có thể vẫn còn I/O/trạng thái nền | Thiết kế cancellation + cleanup độc lập |
| Không test khi shutdown có request còn chạy | Đóng app treo/mất yêu cầu | Test tải đồng thời, body stream và deadline |
| Thay cấu hình runtime nhưng tái sử dụng client cũ | Cấu hình cũ vẫn tồn tại trên instance | Tạo client mới và chuyển giao ownership có kiểm soát |

## 13. Bài luyện tập

**Bài 1.** Ứng dụng Java 11 tạo một `HttpClient` cho mỗi lần gọi API, rồi định chuyển sang `try (HttpClient c = ...)` để “giải phóng kết nối”. Có đúng không?

**Đáp án:** Không. `HttpClient` Java 11 không `AutoCloseable`; `try-with-resources` dành cho client từ JDK 21+. Trên Java 11, nên tái sử dụng client theo service và đóng những tài nguyên response/executor do ứng dụng thực sự sở hữu.

**Bài 2.** Một `HttpClient` JDK 21+ đang được nhiều module sử dụng. Một module kết thúc request và gọi `close()`. Vấn đề gì?

**Đáp án:** `close()` bắt đầu shutdown client và không chấp nhận request mới; module khác có thể bị ảnh hưởng. Owner của client mới quyết định thời điểm đóng.

**Bài 3.** Gọi `send` với `BodyHandlers.ofInputStream()`, nhận `HttpResponse<InputStream>` rồi bỏ qua stream. Hậu quả?

**Đáp án:** Có thể giữ tài nguyên/kết nối và gây khó khăn cho việc hoàn tất request hoặc graceful shutdown. Phải đọc hết hoặc đóng stream theo chính sách ứng dụng.

**Bài 4.** Vì sao `connectTimeout(Duration.ofSeconds(3))` không nên được hiểu là “mọi HTTP request sẽ kết thúc trong 3 giây”?

**Đáp án:** Nó áp dụng cho giai đoạn thiết lập kết nối, không phải deadline của mọi tác vụ HTTP và xử lý response. Có thể thiết lập `HttpRequest.timeout` và kiểm soát deadline nghiệp vụ.

**Bài 5.** Khi ứng dụng Java 21+ phải dừng trong thời gian hữu hạn nhưng vẫn có request đang chạy, chọn hướng nào?

**Đáp án:** Ngừng nhận request mới, cố gắng hoàn tất/cancel body đang xử lý, gọi `shutdown()`, `awaitTermination(Duration)`, và nếu vượt hạn có thể gọi `shutdownNow()` best effort. Không khẳng định mọi task sẽ dừng chắc chắn.

## 14. Tóm tắt và tài liệu chính thức

- **Java 11/17:** `HttpClient` có thể tái sử dụng cho nhiều request; **không có API `close/shutdown`**. Cần quản lý client theo service/app, xử lý response body và executor tự tạo.
- **Java 21+:** `HttpClient` có `AutoCloseable`, `close`, `shutdown`, `shutdownNow`, `awaitTermination`, `isTerminated`. Chỉ đóng client tại ranh giới ownership phù hợp, sau khi có kế hoạch cho request/body đang hoạt động.
- **Mọi JDK:** vòng đời client khác vòng đời request/response; timeout/cancel/backpressure và resource management vẫn là trách nhiệm thiết kế của ứng dụng.
- **Không dựa vào suy đoán về pool/thread**, không bắt `OutOfMemoryError` hay dùng shutdown cưỡng bức làm quy trình xử lý bình thường.
- **Kiểm tra runtime mục tiêu và đặc tả API**, không sao chép nguyên mẫu từ JDK khác phiên bản.

Tài liệu Oracle còn giá trị tham khảo:

- [`HttpClient` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html) — tạo client, chia sẻ tài nguyên, sync/async, builder.
- [`HttpClient` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — vòng đời API trước JDK 21.
- [`HttpClient` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html) — `AutoCloseable` và các phương thức `close/shutdown` được thêm từ 21, lưu ý stream đang mở.
- [`HttpClient` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html) — đối chiếu API còn được hỗ trợ trên JDK hiện đại.
- [`HttpResponse.BodyHandlers` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — cách nhận nội dung response.
 client trên JDK 21+ có nghĩa service đó được quyền shutdown pool không?

**Đáp án:** Không. Pool được quản lý bởi owner của pool và chỉ dừng khi không còn thành phần/tác vụ dùng chung.

**Câu 6.** `future.cancel(true)` một POST đồng nghĩa server chưa ghi dữ liệu?

**Đáp án:** Không. Cancellation chỉ là best effort; cần idempotency và xác nhận trạng thái nghiệp vụ.

**Câu 7.** `client.isTerminated()` trả false khi client JDK 21 còn idle và chưa shutdown. Có phải request treo không?

**Đáp án:** Không. Trạng thái terminated phản ánh kết thúc sau khi đã yêu cầu shutdown, không phải trạng thái nhàn rỗi thông thường.

## 16. Tóm tắt và tài liệu chính thức

- **JDK 11/17:** tái sử dụng một client theo owner/config; theo dõi request, future, body và executor; **không có API đóng HttpClient công khai**.
- **JDK 21+:** `HttpClient` implement `AutoCloseable`, có `close()` và `shutdown/awaitTermination/shutdownNow`; vẫn đóng **theo lifecycle của owner**, không phải theo từng request.
- **Mọi JDK:** response streaming chưa tiêu thụ/đóng có thể giữ request mở. Executor do ứng dụng sở hữu có lifecycle riêng.
- Không coi GC, timeout, hủy future hay `shutdownNow` là cam kết tài nguyên sẽ hoàn toàn được giải phóng ngay.
- Cần xây dựng chính sách stop/timeout/concurrency và quan sát phù hợp với ứng dụng, không sao chép code từ JDK mới sang target Java 11.

Tài liệu API chính thức, còn phù hợp:

- [`HttpClient` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): API Java 11, cấu hình client và `send`/`sendAsync`.
- [`HttpClient.Builder` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): executor, connection timeout, cấu hình TLS/proxy.
- [`HttpClient` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): đối chiếu JDK 17 chưa có close.
- [`HttpClient` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): `AutoCloseable` và API shutdown mới từ 21.
- [`HttpClient` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): lifecycle, connection pool và response body streaming trên JDK hiện đại.
- [`HttpResponse.BodyHandlers` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): cách nhận response dạng string, stream và publisher.
