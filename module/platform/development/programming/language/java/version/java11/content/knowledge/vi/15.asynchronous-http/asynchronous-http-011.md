# Retry theo tính lặp an toàn và khả năng phát lại body (Java 11)

Một request HTTP bất đồng bộ có thể thất bại vì mất kết nối, timeout, server quá tải hoặc bị giới hạn tốc độ. Khi đó, câu hỏi **không chỉ là “có nên gọi lại không?”** mà gồm ba điều kiện độc lập:

1. **Thao tác có thể lặp lại an toàn về mặt ngữ nghĩa không?** Gửi lại có tạo thêm đơn hàng, giao dịch, email hay side effect ngoài ý muốn?
2. **Request body có thể phát lại đúng dữ liệu như lần đầu không?** `BodyPublisher` có cung cấp lại cùng dãy byte cho mỗi lần gửi?
3. **Lỗi hiện tại có đáng retry, và ngân sách còn cho phép không?** Status/exception, số lần thử, backoff, `Retry-After` và thời hạn tổng thể phải phù hợp.

Trong **Java 11**, `java.net.http.HttpClient.sendAsync(...)` trả về `CompletableFuture<HttpResponse<T>>`. Java cung cấp các công cụ xây chuỗi bất đồng bộ, nhưng **không tự định nghĩa retry policy nghiệp vụ** cho endpoint của bạn. Bài học này trình bày cách ra quyết định về retry và dùng `HttpRequest.BodyPublisher` có thể phát lại, tránh gửi trùng tác vụ hoặc vô tình gửi body rỗng sau lần thất bại đầu.

Các API chính (`HttpClient`, `HttpRequest`, `BodyPublishers`, `CompletableFuture`, `Flow`) vẫn còn áp dụng trên các JDK được hỗ trợ hiện nay. Ví dụ biên dịch ở mức **`--release 11`**; không cần vận hành một runtime Java 11 đã hết thời gian hỗ trợ cập nhật chỉ để thực hành.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **safe**, **idempotent** và **replayable body** — ba khái niệm không đồng nghĩa.
2. Nêu chính sách retry cho GET/HEAD, PUT/DELETE và POST/PATCH theo RFC 9110 và hợp đồng endpoint.
3. Dùng `HttpRequest.BodyPublishers.ofString`, `ofByteArray` và `ofInputStream(Supplier<InputStream>)` đúng với yêu cầu phát lại.
4. Hiểu mỗi lần HTTP Client phải gửi lại request body có thể tạo **một `Flow.Subscription` mới**, và dữ liệu phải tương đương lần đầu.
5. Xử lý `CompletableFuture` hoàn tất bình thường với HTTP `429`/`503` khác với hoàn tất lỗi vì `IOException`.
6. Viết retry bất đồng bộ có số lần tối đa và trì hoãn, không dùng `Thread.sleep` chặn thread callback.
7. Thiết kế idempotency key cho tác vụ POST có side effect **chỉ khi server hỗ trợ hợp đồng đó**.
8. Giải thích retry sau timeout không bảo đảm request ban đầu chưa được áp dụng.
9. Biết đặt backoff/jitter, `Retry-After`, deadline, giới hạn body, điều kiện hủy và quan sát số lần thử.
10. Kiểm thử logic retry với fake transport và kiểm thử tính replayable của publisher độc lập mạng.

## 2. Ba điều kiện phải cùng đúng trước khi retry

```text
              Một attempt đã lỗi / nhận status có thể retry
                                |
                                v
                   [1] Retry có phù hợp lỗi?
                         /             \
                        NO              YES
                        |                |
                  Không retry            v
                             [2] Operation lặp an toàn?
                                   /        \
                                  NO         YES
                                  |           |
                            Không retry       v
                                    [3] Body phát lại được?
                                            /       \
                                           NO        YES
                                           |          |
                                     Không retry      v
                                            [4] Còn retry budget?
                                                 /     \
                                                NO      YES
                                                |        |
                                          Kết thúc    Delay có giới hạn
                                                        |
                                                        v
                                              Gửi attempt tiếp theo
```

**Điều kiện “body có thể replay” không thay thế idempotency.** Một body `byte[]` có thể được gửi lại chính xác, nhưng nếu POST đó tạo đơn hàng mới mỗi lần, retry vẫn nguy hiểm. Ngược lại, một PUT theo ngữ nghĩa idempotent có thể không retry được nếu body lần đầu lấy từ một stream chỉ đọc được một lượt.

Khi một điều kiện thiếu, ứng dụng nên trả lỗi hoặc trạng thái **chưa xác định** thay vì tự đoán thành công/thất bại. Với operation có side effect, có thể cần truy vấn trạng thái phía server bằng operation ID/correlation ID.

## 3. Safe và idempotent theo HTTP: phân biệt thật rõ

Theo **RFC 9110**, một method được coi là **safe** khi ý nghĩa được yêu cầu là chỉ đọc, không chủ đích thay đổi trạng thái server. **Idempotent** nghĩa là nhiều request **giống nhau** tạo ra **hiệu ứng có chủ đích** tương đương một request. Một method có thể idempotent nhưng **không safe**.

| Method | Safe theo ngữ nghĩa HTTP? | Idempotent theo ngữ nghĩa HTTP? | Hướng retry |
| --- | --- | --- | --- |
| `GET` | Có | Có | Thường là ứng viên retry tốt; vẫn kiểm tra endpoint, cache, quota và status |
| `HEAD` | Có | Có | Tương tự GET, không có response body theo ngữ nghĩa HEAD |
| `OPTIONS` | Có | Có | Có thể retry khi API/giao thức cho phép |
| `TRACE` | Có theo đặc tả | Có | Thường bị vô hiệu hóa do rủi ro bảo mật; không khuyến khích bật chỉ để thử retry |
| `PUT` | Không | Có | Retry có thể hợp lệ **nếu representation gửi lại giống nhau** và hợp đồng endpoint tuân thủ ngữ nghĩa PUT |
| `DELETE` | Không | Có | Tác động mong muốn idempotent; response lần 2 có thể khác lần 1 (`204` rồi `404`) |
| `POST` | Không mặc định | Không mặc định | Chỉ retry khi **server định nghĩa** idempotency/reconciliation rõ ràng |
| `PATCH` | Không mặc định | Không mặc định | Có thể xây PATCH idempotent, nhưng không tự suy ra từ tên method |

### “Idempotent” không có nghĩa mọi response giống hệt

Ví dụ xóa tài nguyên:

```text
DELETE /items/7   -> lần 1: 204 No Content
DELETE /items/7   -> lần 2: 404 Not Found (tùy API)
```

Trạng thái cuối của tài nguyên đều là **không còn item 7**, nhưng status hai lần có thể khác nhau. Server vẫn có thể ghi log cho từng request hoặc tạo audit event. Tính idempotent đề cập tới **tác động được yêu cầu**, không phải bảo đảm mọi quan sát, header, counter hay response đều giống hệt.

### “Safe” không có nghĩa không có side effect vật lý nào

Một GET có thể ghi log truy cập, metric hoặc cập nhật cache. Tuy nhiên, nó **không được thiết kế** để tạo đơn hàng hoặc trừ tiền theo ngữ nghĩa GET. Nếu hệ thống cũ dùng `GET /charge` để thu tiền, **đừng áp mặc định retry GET**; hợp đồng endpoint đó đã không tuân thủ ngữ nghĩa safe chuẩn.

**Quy tắc vận hành:** đánh dấu “được retry” bằng **policy đã được xem xét cho từng operation**, không chỉ dùng `method.equals("GET")` hoặc `method.equals("PUT")` làm điều kiện duy nhất.

## 4. Request đã đến server chưa? Vì sao timeout là tình huống khó?

Khi client gửi POST thanh toán và nhận lỗi I/O:

```text
Client                        Server
  |  POST /payments              |
  |----------------------------->|
  |                         Ghi giao dịch
  |                          Commit thành công
  |                               |
  |               response bị mất X
  |<----------------------------- X
  |
  +-- Client nhìn thấy timeout / IOException
```

Client **không biết** server chưa nhận request, đang xử lý hay đã xử lý xong. Retry vô điều kiện có thể tạo giao dịch thứ hai.

Ngược lại, lỗi xảy ra ngay khi client chưa tạo được kết nối có thể làm người viết nghĩ “chắc chắn server chưa thực thi”, nhưng việc phân loại tin cậy tình huống này thường phụ thuộc client, proxy, kết nối tái sử dụng và tầng transport. Đừng khẳng định từ một `IOException` chung rằng side effect chưa xảy ra.

Vì vậy, với POST có tác dụng ngoài hệ thống:

- Ưu tiên **idempotency key do server hiểu và thực thi**, nếu API có hỗ trợ.
- Dùng **operation ID** ổn định, xác minh trạng thái qua endpoint riêng khi cần.
- Nếu không có cơ chế an toàn, trả trạng thái **UNKNOWN/INDETERMINATE** để xử lý đối soát, thay vì tự retry hay tự báo thất bại.
- Đừng dùng cancellation của future làm bằng chứng giao dịch đã được hủy ở phía server.

## 5. Khả năng phát lại request body: hợp đồng Java 11

`HttpRequest.BodyPublisher` của Java 11 mở rộng:

```java
Flow.Publisher<ByteBuffer>
```

Một lần gửi request có body tạo một subscriber để HTTP Client nhận các byte từ publisher. **Nếu request cần được gửi lại**, một **subscription mới** được tạo và **được kỳ vọng phát lại cùng dữ liệu như trước**.

Đây là yếu tố trọng tâm của bài. Một `HttpRequest` bất biến **có thể** được tái sử dụng, nhưng publisher gắn trong nó phải thực sự hỗ trợ subscription mới tương đương. Tạo lại `HttpRequest` cũng **không tự chữa** một publisher tự viết chỉ đọc nguồn một lần.

### Bảng đánh giá các `BodyPublishers`

| Body publisher | Khả năng phát lại | Điều kiện/cạm bẫy |
| --- | --- | --- |
| `BodyPublishers.noBody()` | Không có byte body cần phát lại | **Không** biến method có side effect thành idempotent |
| `BodyPublishers.ofString(text, UTF_8)` | Thông thường dễ phát lại | Giữ nguyên payload và charset; snapshot dữ liệu trước khi gửi |
| `BodyPublishers.ofByteArray(bytes)` | Có thể phát lại theo publisher chuẩn | Không sửa nội dung mảng gốc đồng thời với gửi/retry |
| `BodyPublishers.ofFile(path)` | Dựa trên nội dung file khi gửi | File phải tồn tại, được đọc được và **không thay đổi giữa các attempt** |
| **`BodyPublishers.ofInputStream(supplier)`** | Được thiết kế cho việc có thể gửi lại | `Supplier` phải trả **stream mới, mở được, cùng bytes** trên mỗi lần cần đọc |
| `BodyPublishers.ofByteArrays(iterable)` | Phụ thuộc dữ liệu/`Iterable` | Không dùng iterable một lượt hoặc dữ liệu bị biến đổi nếu muốn replay |
| `BodyPublishers.fromPublisher(flowPublisher)` | Phụ thuộc publisher bên dưới | Nguồn hot/one-shot có thể **không thể subscribe lại** hoặc phát dữ liệu khác |
| BodyPublisher tự viết | Phải tự bảo đảm contract | Mỗi subscription phát cùng byte, đúng độ dài, đúng backpressure và vòng đời |

**Phân biệt request với response:** request body có `Flow.Publisher<ByteBuffer>`; còn response streaming qua `BodyHandlers.ofPublisher()` trả `Flow.Publisher<List<ByteBuffer>>`. Hai kiểu phục vụ hai chiều khác nhau; không tráo chúng khi thiết kế retry.

### Buffer đã được publish: quyền sở hữu

Theo Java 11, các `ByteBuffer` mà request-body publisher phát ra phải được cấp phát bởi publisher và **không tiếp tục được truy cập/sửa đổi sau khi đã publish cho HTTP Client**. Một subscription gửi lại phải tạo sequence mới tương đương và quản lý dữ liệu độc lập đúng cách. Không tái sử dụng một `ByteBuffer` đã bị di chuyển position để gửi lại rồi kỳ vọng nó tự quay về đầu.

### `contentLength()` không chứng minh replayable

`BodyPublisher.contentLength()` có thể trả:

- `0`: không có byte body;
- số dương: số byte đã biết;
- số âm: chưa biết trước.

Độ dài **không** cho biết nội dung có thể phát lại hay không. Publisher có `contentLength() == 100` nhưng đọc nguồn một lượt vẫn có thể **không gửi được attempt thứ hai**.

API yêu cầu `contentLength()` trả **cùng một giá trị cố định qua các lần gọi**. Nếu khai báo một số byte cụ thể, publisher phải phát đúng số byte đó. Không thay đổi content length theo số attempt.

## 6. `ofInputStream(Supplier<InputStream>)`: mở stream mới cho mỗi lần cần đọc

`BodyPublishers.ofInputStream` nhận **supplier**, chứ không nhận trực tiếp một `InputStream`. Java 11 thiết kế như vậy vì stream thông thường **bị tiêu thụ khi đọc**:

```java
byte[] payload = "payload-7".getBytes(StandardCharsets.UTF_8);

HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofInputStream(
                () -> new ByteArrayInputStream(payload));
```

Đây là **snippet đặt trong một phương thức**, cần imports `ByteArrayInputStream`, `StandardCharsets` và `HttpRequest`. Mỗi lần supplier được gọi sẽ trả một `InputStream` **mới**, bắt đầu từ byte đầu. Mảng `payload` phải được xem là snapshot bất biến trong suốt quá trình gửi và retry.

**Cách dễ sai:**

```java
InputStream oneShot = openSomeStream();
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofInputStream(() -> oneShot);
```

Đây là **phản ví dụ minh họa trong một phương thức** có `InputStream` và một hàm do người viết cung cấp. Supplier luôn trả **cùng instance đã bị đọc**, do đó lần gửi lại có thể gặp EOF hoặc stream đã đóng. Không dùng `mark/reset` như giải pháp chung cho mọi stream; nhiều stream không hỗ trợ hoặc chỉ hỗ trợ trong giới hạn nhất định.

### Khi supplier không mở được stream

Tài liệu Java 11 cho phép supplier trả `null` trong một lần gọi tiếp theo, khi đó request **thất bại**. Nếu không thể mở file hoặc nguồn, cũng có thể phát sinh lỗi khi tạo/đọc stream. Không được âm thầm thay payload bằng mảng rỗng rồi gửi request khác với tác vụ ban đầu.

### Với file hoặc nguồn dữ liệu thay đổi theo thời gian

Nếu supplier mỗi lần mở lại một tệp và tệp bị sửa giữa hai attempt, hai request có thể mang **nội dung khác nhau** dù cùng URI/method/idempotency key. Để chắc chắn replay chính xác:

1. Snapshot payload thành `byte[]` khi nhỏ và hợp lý về bộ nhớ.
2. Với payload lớn, spool ra file tạm có quản lý vòng đời, checksum và quyền truy cập.
3. Không sửa nội dung snapshot cho tới khi operation hoàn tất/được hủy.
4. Nếu server dùng idempotency key, các attempt cùng key phải biểu diễn **cùng một operation và cùng payload logic**.
5. Kiểm tra file không bị xóa/đổi quyền giữa các attempt; xử lý lỗi phát lại một cách riêng biệt.

## 7. Ví dụ hoàn chỉnh 1: retry bất đồng bộ có điều kiện

Chương trình **`AsyncRetryDemo.java`** sau gồm:

- Interface `AsyncSender` để tách HTTP transport khỏi retry policy.
- Adapter `JdkHttpSender` dùng `HttpClient.sendAsync` của Java 11.
- `FakeSender` trả các response/status/lỗi I/O theo kịch bản cố định, **không truy cập mạng**.
- `RetryEngine` chỉ retry khi **policy của operation cho phép**, body có thể replay, lỗi/status nằm trong tập được phép và chưa vượt `maxAttempts`.
- Delay giữa các attempt bằng `CompletableFuture.delayedExecutor` (**có sẵn trong Java 11**), không `Thread.sleep` trong callback.

Ví dụ **không tự suy luận rằng chỉ cần có header `Idempotency-Key` là server chắc chắn idempotent**. Cờ `allowedByContract` phải được đặt **sau khi đã biết hợp đồng endpoint**; giả lập ở `main` chủ động đặt true/false để kiểm chứng.

Tạo tệp **`AsyncRetryDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class AsyncRetryDemo {
    static final class Plan {
        final String label, method, idempotencyKey;
        final boolean allowedByContract, replayableBody;
        final Supplier<HttpRequest.BodyPublisher> bodyFactory;

        Plan(String label, String method, String idempotencyKey,
             boolean allowedByContract, boolean replayableBody,
             Supplier<HttpRequest.BodyPublisher> bodyFactory) {
            this.label = label;
            this.method = method;
            this.idempotencyKey = idempotencyKey;
            this.allowedByContract = allowedByContract;
            this.replayableBody = replayableBody;
            this.bodyFactory = bodyFactory;
        }

        HttpRequest newRequest() {
            HttpRequest.Builder builder = HttpRequest.newBuilder(
                    URI.create("https://api.example.invalid/" + label))
                    .timeout(Duration.ofSeconds(2));
            if (idempotencyKey != null) {
                builder.header("Idempotency-Key", idempotencyKey);
            }
            if ("GET".equals(method)) {
                return builder.GET().build();
            }
            return builder.method(method, bodyFactory.get()).build();
        }

        boolean safeToRetry() {
            return allowedByContract && replayableBody;
        }
    }

    static final class Reply {
        final int status;
        Reply(int status) { this.status = status; }
    }

    interface AsyncSender {
        CompletableFuture<Reply> send(Plan plan);
    }

    static final class JdkHttpSender implements AsyncSender {
        private final HttpClient client;
        JdkHttpSender(HttpClient client) { this.client = client; }

        @Override
        public CompletableFuture<Reply> send(Plan plan) {
            return client.sendAsync(plan.newRequest(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                    .thenApply(response -> new Reply(
                            response.statusCode()));
        }
    }

    static final class FakeSender implements AsyncSender {
        private final ConcurrentHashMap<String, AtomicInteger> attempts =
                new ConcurrentHashMap<>();

        int count(String label) {
            AtomicInteger count = attempts.get(label);
            return count == null ? 0 : count.get();
        }

        @Override
        public CompletableFuture<Reply> send(Plan plan) {
            plan.newRequest(); // A new request for each attempt.
            int n = attempts.computeIfAbsent(
                    plan.label, ignored -> new AtomicInteger())
                    .incrementAndGet();

            if ("get".equals(plan.label)) {
                return CompletableFuture.completedFuture(
                        new Reply(n < 3 ? 503 : 200));
            }
            if ("postKey".equals(plan.label)) {
                return CompletableFuture.completedFuture(
                        new Reply(n == 1 ? 503 : 200));
            }
            if ("network".equals(plan.label) && n == 1) {
                return CompletableFuture.failedFuture(
                        new IOException("Simulated connection reset"));
            }
            if ("network".equals(plan.label)) {
                return CompletableFuture.completedFuture(new Reply(200));
            }
            return CompletableFuture.completedFuture(new Reply(503));
        }
    }

    static final class RetryEngine {
        private final AsyncSender sender;
        private final int maxAttempts;

        RetryEngine(AsyncSender sender, int maxAttempts) {
            this.sender = sender;
            this.maxAttempts = maxAttempts;
        }

        CompletableFuture<Reply> execute(Plan plan) {
            return attempt(plan, 1);
        }

        private CompletableFuture<Reply> attempt(Plan plan, int number) {
            CompletableFuture<Reply> current;
            try {
                current = sender.send(plan);
            } catch (RuntimeException failure) {
                current = CompletableFuture.failedFuture(failure);
            }

            return current.handle((response, failure) -> {
                boolean retry = false;
                if (failure != null) {
                    Throwable cause = unwrap(failure);
                    retry = cause instanceof IOException;
                    if (!retry || !plan.safeToRetry()
                            || number >= maxAttempts) {
                        return CompletableFuture.<Reply>failedFuture(cause);
                    }
                } else {
                    retry = response.status == 429
                            || response.status == 502
                            || response.status == 503
                            || response.status == 504;
                    if (!retry || !plan.safeToRetry()
                            || number >= maxAttempts) {
                        return CompletableFuture.completedFuture(response);
                    }
                }

                long delayMillis = 10L * number;
                return CompletableFuture.runAsync(
                        () -> {},
                        CompletableFuture.delayedExecutor(
                                delayMillis, TimeUnit.MILLISECONDS))
                        .thenCompose(ignored -> attempt(plan, number + 1));
            }).thenCompose(next -> next);
        }

        private static Throwable unwrap(Throwable failure) {
            while (failure instanceof CompletionException
                    && failure.getCause() != null) {
                failure = failure.getCause();
            }
            return failure;
        }
    }

    private static Plan get(String label) {
        return new Plan(label, "GET", null, true, true,
                HttpRequest.BodyPublishers::noBody);
    }

    private static Plan post(String label, String key,
                             boolean contract, boolean replayable) {
        return new Plan(label, "POST", key, contract, replayable,
                () -> HttpRequest.BodyPublishers.ofString(
                        "{\"job\":7}", StandardCharsets.UTF_8));
    }

    private static void show(
            String caption, Plan plan,
            RetryEngine retry, FakeSender fake) {
        Reply response = retry.execute(plan).join();
        System.out.println(caption + ": status=" + response.status
                + ", attempts=" + fake.count(plan.label));
    }

    public static void main(String[] args) {
        FakeSender fake = new FakeSender();
        RetryEngine retry = new RetryEngine(fake, 3);

        show("GET", get("get"), retry, fake);
        show("POST without contract",
                post("postNoKey", null, false, true), retry, fake);
        show("POST with documented key",
                post("postKey", "stable-operation-7", true, true),
                retry, fake);
        show("GET with I/O failure",
                get("network"), retry, fake);
        show("Non-replayable body",
                post("oneShot", "stable-operation-8", true, false),
                retry, fake);
    }
}
```

Biên dịch và chạy bằng một JDK được cập nhật, có compiler hỗ trợ Java 11:

```sh
javac --release 11 -encoding UTF-8 AsyncRetryDemo.java
java AsyncRetryDemo
```

**Stdout chính xác:**

```text
GET: status=200, attempts=3
POST without contract: status=503, attempts=1
POST with documented key: status=200, attempts=2
GET with I/O failure: status=200, attempts=2
Non-replayable body: status=503, attempts=1
```

### Phân tích từng dòng

1. **GET:** fake trả `503` ở hai lượt đầu và `200` ở lượt ba. Vì `allowedByContract=true` và body được đánh dấu replayable, policy gửi tối đa ba lượt.
2. **POST không có hợp đồng idempotency:** dù fake trả `503`, body có thể phát lại và còn retry budget, `allowedByContract=false` nên **chỉ gửi một lần**.
3. **POST có key và hợp đồng:** ví dụ giả định API đã tài liệu hóa key `stable-operation-7` có nghĩa idempotent. Fake trả `503` rồi `200`, do đó có **hai** attempt. Nếu server thật không công nhận key, **không được** đặt cờ true.
4. **GET bị lỗi I/O:** `CompletableFuture.failedFuture(IOException)` cho lần đầu, sau đó fake trả `200`. Retry engine chỉ coi `IOException` trong ví dụ là một loại transient error có thể xem xét.
5. **Body không phát lại được:** dù policy nghiệp vụ cho phép, `replayableBody=false` làm retry bị chặn. Chỉ một lần gửi, kết quả `503` được giữ nguyên.

### Phân biệt những lớp trong demo

**`Plan`** là chính sách của **một operation**: method, payload factory, replayability và khả năng retry theo contract. Method một mình không đủ. `Plan.newRequest()` tạo request mới cho mỗi attempt; điều này giúp cắm publisher mới khi cần, nhưng **không tự chứng minh** một supplier tùy ý sẽ phát cùng bytes.

**`JdkHttpSender`** là adapter HTTP thật: `sendAsync`, `BodyHandlers.ofString(UTF_8)`, lấy status. Nó **không tự retry**. Trong `main`, adapter thật không được dùng để gửi Internet; fake bảo đảm đầu ra cố định.

**`RetryEngine`** làm công việc điều phối: chạy attempt, phân biệt exceptional completion và HTTP status, chỉ retry 4 status mẫu (`429`, `502`, `503`, `504`), kiểm tra an toàn và số lượt tối đa. Dùng `handle(...)` rồi `thenCompose(...)` để chuyển `CompletableFuture<CompletableFuture<Reply>>` thành `CompletableFuture<Reply>`.

**`CompletableFuture.delayedExecutor(...)`** trì hoãn attempt tiếp theo mà không gọi `Thread.sleep` trực tiếp trong callback. Delay 10/20 ms chỉ để bài chạy nhanh; **không** phải backoff phù hợp cho dịch vụ thật. Production cần jitter, `Retry-After`, thời hạn tổng thể và kiểm soát tài nguyên.

### Phạm vi cố ý đơn giản hóa của demo

- Code giả lập response status chứ không parse response body/error DTO. Thực tế cần policy riêng cho `200/202/204` và trạng thái nghiệp vụ.
- `FakeSender` dựng request để xác nhận mỗi attempt có request mới nhưng **không subscribe request-body publisher**. Vì vậy nó kiểm tra logic retry, **không tự chứng minh replay byte trên wire**. Ví dụ 2 kiểm tra publisher riêng.
- `replayableBody` và `allowedByContract` là metadata **đã được xác minh** trong ví dụ, không phải giá trị Java tự suy ra.
- Retry mọi `IOException` của một operation được phép chỉ là **chính sách giản lược để minh họa**. Trong production, một lỗi đọc request body, lỗi chứng chỉ TLS, lỗi DNS do cấu hình sai hoặc lỗi payload có thể cần chặn retry ngay; không gộp mọi I/O vào “transient”.
- `maxAttempts=3` có nghĩa **tổng ba lần gửi**, không phải ba lần retry sau lượt đầu.
- Sau khi hết lượt thử với status `503`, ví dụ **trả về response `503`**; gateway thực tế cần chuyển status này thành lỗi/kết quả phù hợp, không báo business success.
- Demo không thiết lập một **deadline xuyên suốt nhiều attempt**, không áp `Retry-After` và không lan truyền cancellation của caller xuống các attempt. Những phần này là bắt buộc phải thiết kế riêng cho client production.

## 8. Ví dụ hoàn chỉnh 2: kiểm tra body publisher có thể phát lại

Để kiểm chứng rằng `ofInputStream` dùng supplier mở stream mới, tạo chương trình **`ReplayBodyDemo.java`**. Ví dụ này **không gửi HTTP**; thay vào đó, nó đăng ký hai subscriber **lần lượt** lên cùng publisher và thu lại bytes như một HTTP Client sẽ làm với các subscription khác nhau.

Tạo tệp **`ReplayBodyDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.net.http.HttpRequest;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ReplayBodyDemo {
    private static String collect(
            HttpRequest.BodyPublisher publisher) throws Exception {
        CompletableFuture<String> finished = new CompletableFuture<>();
        ByteArrayOutputStream result = new ByteArrayOutputStream();

        publisher.subscribe(new Flow.Subscriber<ByteBuffer>() {
            private Flow.Subscription subscription;

            @Override
            public void onSubscribe(Flow.Subscription subscription) {
                this.subscription = subscription;
                subscription.request(1);
            }

            @Override
            public void onNext(ByteBuffer original) {
                ByteBuffer view = original.duplicate();
                byte[] bytes = new byte[view.remaining()];
                view.get(bytes);
                result.write(bytes, 0, bytes.length);
                subscription.request(1);
            }

            @Override
            public void onError(Throwable failure) {
                finished.completeExceptionally(failure);
            }

            @Override
            public void onComplete() {
                finished.complete(new String(
                        result.toByteArray(), StandardCharsets.UTF_8));
            }
        });
        return finished.get(3, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger opens = new AtomicInteger();
        byte[] snapshot = "payload-7".getBytes(
                StandardCharsets.UTF_8);

        HttpRequest.BodyPublisher publisher =
                HttpRequest.BodyPublishers.ofInputStream(() -> {
                    opens.incrementAndGet();
                    return new ByteArrayInputStream(snapshot);
                });

        System.out.println("First: " + collect(publisher));
        System.out.println("Second: " + collect(publisher));
        System.out.println("Stream openings: " + opens.get());
        System.out.println("Unknown length: " +
                (publisher.contentLength() < 0));
    }
}
```

Chạy:

```sh
javac --release 11 -encoding UTF-8 ReplayBodyDemo.java
java ReplayBodyDemo
```

**Stdout chính xác:**

```text
First: payload-7
Second: payload-7
Stream openings: 2
Unknown length: true
```

### Vì sao kết quả quan trọng?

- Cùng một publisher nhận **hai subscription độc lập**, cả hai cùng thu được `payload-7`.
- `Supplier<InputStream>` mở **hai `ByteArrayInputStream` mới**; `opens` trở thành 2.
- `ofInputStream` dùng nguồn chưa biết trước độ dài nên `contentLength() < 0`. Giá trị âm **không có nghĩa đã xảy ra lỗi**; nó chỉ nói không khai báo độ dài trước.
- Subscriber nhận các `ByteBuffer` không có kích thước cố định; ví dụ ghép đủ bytes rồi mới giải mã UTF-8.
- `ByteBuffer.duplicate()` giữ con trỏ đọc của original độc lập, nhưng **không** sao chép nội dung. Mảng `byte[]` do code tạo mới mới là dữ liệu được sở hữu riêng.
- Test cố ý chỉ kiểm tra một chuỗi ngắn; với payload lớn không được gom toàn bộ vào RAM mà thiếu giới hạn.

**Cảnh báo:** khả năng subscribe lại một publisher riêng lẻ **không chứng minh** retry POST là an toàn về mặt nghiệp vụ. Hai điều kiện là độc lập. Hơn nữa, thử subscription trên publisher thủ công không thay thế integration test HTTP thật về header, framing, proxy, TLS và xử lý lỗi giữa lúc đang upload.

## 9. Body từ `Flow.Publisher` tự tạo: lỗi thường gặp

Ví dụ:

```java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(myPublisher);
```

Đây là **snippet trong một phương thức** với `myPublisher` là `Flow.Publisher<ByteBuffer>`.

Một publisher tùy ý có thể:

- Là **cold/replayable publisher**: subscription mới tạo lại cùng bytes, từ đầu.
- Là **hot publisher**: dữ liệu vẫn chảy theo thời gian và subscriber sau có thể nhận phần khác.
- Chỉ cho phép **một subscription**: lần hai thất bại.
- Đọc stream/file đã bị tiêu thụ: subscription thứ hai chỉ nhận đuôi/EOF.
- Phát các `ByteBuffer` đã bị thay đổi position hoặc dùng lại sau khi publish.

**Không có phép kiểm tra tự động đơn giản nào từ `contentLength()` để biết publisher có replayable không.** Hãy thiết kế contract riêng, test hai subscription hoặc tạo **body supplier** xây một publisher mới mỗi attempt từ snapshot ổn định.

Với một `ByteBuffer`, `duplicate()` chỉ tạo view có position/limit độc lập, vẫn chia sẻ backing storage. Nếu publisher tự viết cần phát lại bytes, nên giữ một snapshot `byte[]` ổn định hoặc tái mở một file bất biến, rồi tạo buffer riêng cho mỗi subscription theo hợp đồng `Flow`. Đừng reuse buffer đã phát để gửi lại khi HTTP Client có thể còn đang tiêu thụ nó.

## 10. Idempotency key cho POST: điều gì phải được bảo đảm?

Một số API hỗ trợ header như:

```text
Idempotency-Key: 27f44739-8c1c-4a3b-9837-16a7a1c08426
```

Tên và cú pháp cụ thể **phải theo tài liệu đối tác**. Một key có thể được hệ thống server dùng để nhận diện cùng một tác vụ, tránh thực thi trùng khi client gửi lại vì timeout hoặc lỗi tạm thời.

### Các điều kiện cần có

1. **Server có hợp đồng hỗ trợ key**: chỉ tự gửi header mang tên `Idempotency-Key` không tạo ra tính idempotent nếu server bỏ qua nó.
2. **Một key duy nhất cho một operation logic**: một lần thanh toán mới phải dùng key mới, không dùng lại key của giao dịch khác.
3. **Giữ nguyên key khi retry cùng operation**: tuyệt đối không sinh một key mới cho từng attempt nếu muốn server nhận ra đó là cùng request logic.
4. **Giữ nguyên payload hoặc cùng ngữ nghĩa được server cho phép**: không cùng key mà khác số tiền, địa chỉ hoặc đối tượng.
5. **Hiểu TTL/lưu giữ key ở server**: nhiều API chỉ nhớ key trong một khoảng thời gian; retry sau khi hết hạn có thể không được deduplicate.
6. **Có cách truy vấn kết quả khi status không chắc chắn**: một lỗi I/O có thể xảy ra sau khi server đã áp dụng tác vụ.

Ví dụ minh họa tạo request Java 11 trong một phương thức có `URI uri` và `String stableKey`:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .header("Idempotency-Key", stableKey)
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                "{\"amount\":1200}", StandardCharsets.UTF_8))
        .build();
```

Đây là **snippet**, cần imports `HttpRequest`, `Duration`, `StandardCharsets`. Để gửi thật, phải có hợp đồng server cho operation này. Ở request mới/retry của **cùng operation**, dùng **cùng `stableKey` và cùng body**, không đổi số tiền. Nếu API không hỗ trợ idempotency, không được suy ra an toàn chỉ vì header có mặt.

### Có cần gửi lại `POST` sau response `409`?

**Không mặc định.** Một số server dùng `409` để báo request với key đang được xử lý hoặc conflict; server khác dùng `409` cho lỗi version. Hãy đọc tài liệu endpoint và error schema. Đừng thêm `409` vào danh sách retry tự động chỉ vì đó là status 4xx có vẻ “tạm thời”.

## 11. Phân loại lỗi và status cho một retry policy

| Kết quả attempt | Mặc định hợp lý | Khi nào có thể retry? |
| --- | --- | --- |
| `200/201` | Thành công ở mức HTTP; kiểm tra body/nghiệp vụ | Thường không retry; status nghiệp vụ có hợp đồng riêng |
| `202 Accepted` | Chưa chắc job hoàn tất | Thường **poll status** thay vì gửi lại operation có side effect |
| `204 No Content` | Hoàn thành HTTP không có body | Không parse body thành JSON; thường không retry |
| `400 Bad Request` | Request lỗi | Sửa dữ liệu, không retry y nguyên |
| `401/403` | Xác thực/quyền | Không retry mù; xử lý credentials/quyền |
| `404 Not Found` | Không tìm thấy | Theo endpoint; không mặc định retry |
| `408 Request Timeout` | Server báo timeout request | Có thể cân nhắc với operation idempotent và body replayable |
| `409 Conflict` | Trạng thái xung đột | Theo hợp đồng; không mặc định retry |
| `422 Unprocessable Content` | Request không hợp lệ về ngữ nghĩa | Sửa request thay vì retry |
| `429 Too Many Requests` | Bị rate limit | Có thể retry có giới hạn, **tôn trọng `Retry-After`** |
| `500/502/503/504` | Lỗi phía server/gateway | Có thể retry chọn lọc nếu an toàn, không khuếch đại sự cố |
| `IOException` trong `sendAsync` | Vấn đề I/O | Cần xác minh transient hay permanent; chỉ retry nếu operation an toàn |
| `HttpTimeoutException` | Request hết hạn | Không suy ra server chưa áp dụng; xét idempotency và deadline |
| `ConnectException` | Không thiết lập được kết nối | Có thể transient, nhưng cũng có thể sai địa chỉ/cấu hình |
| `SSLHandshakeException` | TLS không hoàn tất | Thường phải sửa cấu hình/chứng chỉ, tránh retry hàng loạt |
| `CancellationException` | Caller/ứng dụng hủy | Thường **không retry** sau yêu cầu hủy |
| `IllegalArgumentException` khi dựng request | Lỗi lập trình/cấu hình | Không retry cùng input |
| `CompletionException` | Wrapper khi future hoàn tất lỗi | Xem `getCause()`, không coi wrapper là nguyên nhân gốc |

**Không retry theo class exception một cách mù quáng.** Ví dụ `IOException` khi đọc tệp body đã bị xóa sẽ không khắc phục nhờ đợi 100 ms; `SSLHandshakeException` do chứng chỉ không hợp lệ cần sửa cấu hình. Code demo dùng policy rút gọn để dễ theo dõi, nhưng production phải có **taxonomy rõ ràng**.

### Không nhầm lỗi HTTP với exceptional completion

`sendAsync(...)` trả `CompletableFuture<HttpResponse<T>>`:

- HTTP `503` được nhận đầy đủ → future có thể hoàn thành **bình thường** với `HttpResponse` có `statusCode() == 503`.
- Lỗi kết nối/đọc body → future có thể hoàn thành **exceptionally**, không có `HttpResponse` hợp lệ.
- Thao tác giải mã/map ở `thenApply(...)` ném lỗi → future phía sau cũng hoàn thành exceptionally, nhưng đây **không nhất thiết là lỗi transport**.

Đọc status trong nhánh có response, đọc cause trong nhánh lỗi; đừng chỉ dựa vào `exceptionally(...)` để xử lý `429`/`503`.

## 12. Backoff, jitter, `Retry-After` và ngân sách thời gian

Retry không nên bắn hàng loạt ngay sau một `503`. Nếu hàng nghìn client gửi lại đồng thời, server đang quá tải có thể bị quá tải hơn.

### Exponential backoff có trần và jitter

Một chính sách mẫu (chỉ là ví dụ, không phải giá trị chung):

```text
Attempt 1: gửi ngay
Sau lỗi 1: chờ trong khoảng 0..200 ms
Sau lỗi 2: chờ trong khoảng 0..400 ms
Sau lỗi 3: chờ trong khoảng 0..800 ms
...
Không vượt maxBackoff, maxAttempts và overallDeadline
```

Jitter làm các client ít bị đồng bộ vào cùng một thời điểm retry. Có thể dùng `ThreadLocalRandom` hoặc một nguồn ngẫu nhiên phù hợp để tính delay trong miền đã kiểm soát; không cần crypto RNG cho backoff thông thường.

**Tối thiểu phải có:**

- `maxAttempts`: tổng số lượt gửi, ví dụ tối đa 3.
- `maxBackoff`: không đợi vô hạn một lượt.
- **Overall deadline**: tổng thời gian các attempt + delays phải nằm trong ngân sách của use case.
- **Concurrency limit**: không cho mọi request lỗi tạo vô số future/delayed tasks.
- **Cancellation policy**: ngừng lập lịch thêm nếu caller không còn cần kết quả.
- **Metrics**: số attempt, lỗi cuối, operation, delay, outcome; không ghi secret.

### `Retry-After` có hai dạng

RFC 9110 cho phép:

```http
Retry-After: 120
```

nghĩa là gợi ý đợi **120 giây**, hoặc:

```http
Retry-After: Fri, 31 Dec 1999 23:59:59 GMT
```

là một **HTTP-date** chỉ thời điểm tiếp tục. Các ví dụ định dạng trên minh họa chuẩn cú pháp, **không liên hệ thời gian hiện tại**.

Nếu dùng `429`/`503`, hãy đọc `response.headers().firstValue("Retry-After")` và phân tích **cả số giây lẫn HTTP-date**, có giới hạn/điều kiện lỗi. Không chỉ parse integer rồi coi mọi giá trị khác là `0`. Nếu thời gian server yêu cầu lớn hơn **overall deadline**, thông thường nên ngừng retry và trả trạng thái phù hợp thay vì giữ request lâu vô hạn.

Header có thể vắng mặt, sai cú pháp hoặc bị sửa trên đường truyền; luôn có fallback policy và chặn giá trị quá lớn/tràn số. Không vượt qua policy của server bằng cách retry sớm hơn chỉ vì local delay đang nhỏ.

### Tránh `Thread.sleep` trong callback

`CompletableFuture.delayedExecutor(delay, TimeUnit.MILLISECONDS)` có trong Java 11 và giúp lên lịch tác vụ sau delay mà không giữ một thread chỉ để ngủ. Với công việc production, có thể dùng `ScheduledExecutorService` được quản lý để có quyền shutdown, metrics và giới hạn số delayed tasks.

Đừng gọi `Thread.sleep(2000)` trong `thenApply` hoặc `whenComplete` trên thread HTTP Client. Việc block callback có thể làm giảm thông lượng và tạo hiệu ứng dây chuyền khi nhiều request lỗi.

## 13. Deadline và hủy: phân biệt timeout của attempt với timeout tổng

Có ít nhất ba giới hạn thời gian khác nhau:

1. **`HttpClient.Builder.connectTimeout(Duration)`**: giới hạn thời gian thiết lập kết nối mới theo hợp đồng API.
2. **`HttpRequest.Builder.timeout(Duration)`**: timeout của một request/attempt.
3. **Overall deadline của use case**: gồm mọi attempt, backoff, chờ queue và xử lý kết quả.

Nếu mỗi attempt được đặt 5 giây và cho 3 attempt, tổng thời gian có thể **lớn hơn 15 giây** khi cộng thêm backoff, scheduling và các công việc khác. Vì thế, đặt request timeout không thay thế overall deadline.

### `CompletableFuture.orTimeout` có giải quyết tất cả không?

`orTimeout(t, unit)` có từ Java 9 và dùng được ở Java 11; nó có thể làm future hoàn tất exceptionally khi quá hạn. Nhưng **timeout/cancellation của future không đồng nghĩa server chưa nhận hoặc chưa xử lý request**. Trong một chuỗi retry, cần truyền tín hiệu dừng sang scheduler và attempt đang chạy khi có thể, tránh một attempt cũ vẫn tiếp tục gửi dữ liệu sau khi caller đã bỏ cuộc.

Không tự retry từ nhánh `TimeoutException` nếu operation không idempotent. Kể cả POST với key, cần kiểm tra thời hạn và hợp đồng server trước khi gửi lại.

### Khi ứng dụng dừng giữa lúc body đang được gửi

Nếu request body là stream lớn, cần dọn nguồn:

- HTTP Client có thể hủy subscription khi request dừng, nhưng code cấp nguồn phải tuân theo `Flow.Subscription.cancel()` và vòng đời file/stream.
- Với `ofInputStream`, bảo đảm các stream mở ra được đóng đúng cách khi subscriber/HTTP Client ngừng tiêu thụ.
- Nếu tự viết publisher, phải hỗ trợ cancellation, lỗi nguồn, backpressure và không sử dụng lại các buffer đã chuyển giao.
- Nếu user cancel từ giao diện, dừng **lên lịch các attempt tiếp theo**. Đừng coi việc future hoàn thành exceptionally là “hệ thống server đã hoàn tác”.

## 14. Dùng cùng một `HttpRequest` hay tạo request mới?

Có hai cách hợp lệ:

**Cách A — tái sử dụng request bất biến** nếu `BodyPublisher` hỗ trợ subscribe lại chính xác:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .POST(HttpRequest.BodyPublishers.ofString(
                payload, StandardCharsets.UTF_8))
        .build();

// Có thể gọi sendAsync với request này cho các attempt theo policy,
// miễn publisher có thể phát lại và operation retry an toàn.
```

**Cách B — cung cấp factory tạo request/publisher mới mỗi attempt**, giống `Plan.newRequest()` trong demo:

```java
Supplier<HttpRequest> newRequest = () ->
        HttpRequest.newBuilder(uri)
                .POST(HttpRequest.BodyPublishers.ofString(
                        payload, StandardCharsets.UTF_8))
                .build();
```

Cả hai đoạn là **snippet đặt trong phương thức** đã có `URI uri`, `String payload` và imports cần thiết. Chúng không tự định nghĩa retry policy. Với body stream, request factory thường giúp làm rõ cách mở **đầu vào mới**. Nhưng nếu factory chỉ trả về cùng một `Flow.Publisher` one-shot, vấn đề vẫn còn.

**Các giá trị phải ổn định xuyên suốt retry cùng operation:** URI/operation đích (trừ khi redirect được kiểm soát), method, payload logic, idempotency key, content type, authentication policy và phiên bản dữ liệu cần ghi. Một POST retry có cùng key nhưng body khác là lỗi contract nghiêm trọng.

## 15. Quan hệ giữa retry ở ứng dụng và retry nội bộ của HTTP Client

Java HTTP Client có thể thực hiện một số xử lý transport nội bộ, ví dụ thử lại kết nối tùy implementation/protocol. Tuy nhiên, không dựa vào một số lần thử lại cố định hoặc tưởng rằng client hiểu **idempotency của nghiệp vụ**. Các chi tiết nội bộ có thể khác theo JDK, phiên bản HTTP và cấu hình.

Ứng dụng phải tự quy định:

- Những operation được retry, với điều kiện nào.
- Những status/exception có ý nghĩa tạm thời.
- Body phát lại có đảm bảo cùng bytes.
- Backoff, `Retry-After` và budget.
- Phân loại response thành kết quả nghiệp vụ và tránh double-processing.

Vì có thể tồn tại retries trong các tầng khác nhau (client, proxy, service mesh, load balancer, ứng dụng), hãy xác định **retry ownership** và tổng ngân sách hệ thống. Nhiều tầng cùng retry có thể nhân số request thực tế theo cấp số nhân.

**Thực hành:** không tự kết luận rằng ba lần gọi `sendAsync` của ứng dụng bằng chính xác ba lần cố gắng truyền trên mạng trong mọi môi trường; metrics client và server cần được đối chiếu.

## 16. Kiểm thử retry và khả năng replay

| Tình huống | Kết quả mong đợi |
| --- | --- |
| GET, fake trả `503, 503, 200` | Tối đa 3 attempt, nhận `200` |
| GET, fake trả `200` ngay | 1 attempt, không retry |
| GET, fake trả `401` | 1 attempt, không retry |
| POST không có hợp đồng idempotency, fake trả `503` | 1 attempt, giữ lỗi |
| POST có hợp đồng key, body replayable, `503` rồi `200` | 2 attempt, giữ nguyên key và payload |
| POST có key nhưng body one-shot, `503` | Không retry vì không phát lại được |
| PUT cùng URI, body khác giữa hai lần | **Test thất bại**; retry payload không tương đương |
| `ofInputStream` mở stream mới mỗi lần subscribe | Hai bản bytes giống hệt, opens = 2 |
| Supplier trả cùng stream đã bị đọc | Phát hiện lần thứ hai thiếu/sai dữ liệu |
| `fromPublisher` dùng source hot | Phải đánh dấu không replayable hoặc snapshot trước |
| Future exceptionally với `IOException` transient | Chỉ retry operation đủ điều kiện |
| Future exceptionally do TLS/cấu hình | Không retry mù |
| `429` với `Retry-After` | Dùng delay phù hợp và deadline |
| `503` liên tục đến hết maxAttempts | Trả lỗi/status cuối, không bắn tiếp |
| Caller cancel trong backoff | Không gửi attempt tiếp theo |
| Timeout sau POST đã được server xử lý | Không tạo tác vụ trùng; dùng key/đối soát |
| `202 Accepted` với job ID | Theo dõi status; không POST lại tùy tiện |

**Tách hai nhóm test:**

- **Unit test policy**: dùng fake `AsyncSender` như `AsyncRetryDemo`. Kiểm tra số lượt, status, xử lý lỗi, policy và budget; không cần mạng.
- **Replay/transport integration test**: dùng `ReplayBodyDemo`, local HTTP server hoặc mock server để xác minh nội dung body từng attempt, headers, cancel và cách HTTP Client xử lý lỗi. Fake chỉ dựng `HttpRequest` **không đủ** chứng minh stream thực tế đã phát đúng bytes.

Với production, còn cần **contract test** để chứng minh server thực sự hỗ trợ idempotency key, giữ key trong thời gian mong đợi và trả cùng kết quả/cách tra cứu khi có request trùng.

## 17. Lỗi thường gặp

**Lỗi 1 — Retry mọi `IOException`.** Một số lỗi I/O là permanent hoặc liên quan body không thể phát lại; phải phân loại đúng và kiểm tra operation.

**Lỗi 2 — Cho rằng method idempotent thì body không quan trọng.** Một PUT có stream one-shot không bảo đảm gửi cùng representation lần sau.

**Lỗi 3 — Cho rằng body replayable nghĩa là POST an toàn.** Replayability chỉ giải quyết **dữ liệu được phát lại**, không giải quyết side effect trùng.

**Lỗi 4 — Chỉ thêm header `Idempotency-Key` rồi bật retry.** Nếu server bỏ qua header hoặc key đã hết TTL, không có bảo đảm deduplication.

**Lỗi 5 — Tạo idempotency key mới cho mỗi attempt.** Server hiểu đó là những operation khác nhau; phải giữ key trong cùng một transaction logic.

**Lỗi 6 — Supplier trả cùng `InputStream`.** Lần hai gặp EOF hoặc dữ liệu còn lại thay vì gửi từ đầu. Supplier phải mở stream mới.

**Lỗi 7 — File/payload thay đổi giữa hai lần.** Cùng key mà khác bytes có thể gây conflict hoặc tạo hành vi không nhất quán. Cần snapshot.

**Lỗi 8 — Dùng `BodyPublisher.contentLength()` để kiểm tra replayable.** `contentLength()` là metadata số byte, không phản ánh khả năng subscribe nhiều lần.

**Lỗi 9 — Chỉ xử lý `exceptionally(...)`, bỏ qua HTTP `429`/`503`.** Những status này vẫn có thể nằm trong `HttpResponse` của future thành công ở tầng transport.

**Lỗi 10 — Retry `200` chỉ vì business status chưa đạt.** Cần phân biệt `PENDING` với lỗi transient; có thể phải poll status, không phát lại operation.

**Lỗi 11 — Retry `POST` sau timeout với suy đoán server chưa nhận.** Server có thể đã commit; cần key/đối soát.

**Lỗi 12 — `Thread.sleep` trong callback của `sendAsync`.** Làm block thread thực hiện callback; dùng scheduler/delayed executor.

**Lỗi 13 — Exponential backoff không giới hạn hoặc không có jitter.** Có thể chờ quá lâu hoặc tạo retry storm; cần cap và deadline.

**Lỗi 14 — Không đọc `Retry-After` hoặc chỉ hỗ trợ số giây.** RFC cũng cho phép HTTP-date; cần parser và giới hạn.

**Lỗi 15 — Chỉ giới hạn từng attempt, không giới hạn toàn bộ workflow.** Tổng thời gian và tài nguyên có thể vượt SLA.

**Lỗi 16 — Future bị hủy nhưng scheduler vẫn gửi tiếp.** Cần truyền trạng thái cancellation đến lịch retry và transport.

**Lỗi 17 — Ghi log request body/token qua mọi attempt.** Có thể tăng rủi ro lộ dữ liệu nhạy cảm; log metadata đã redaction.

**Lỗi 18 — Đặt retry ở nhiều tầng mà không thống nhất.** Client + proxy + gateway + service đều retry có thể khuếch đại tải.

## 18. Bài tập thực hành

### Bài 1 — Xác định tính an toàn

Với các operation sau, hãy chọn **retry được / không retry mặc định / chỉ retry khi contract cụ thể bảo đảm**:

1. GET lấy trạng thái đơn hàng.
2. DELETE xóa một resource.
3. PUT đặt lại một representation cố định.
4. POST tạo thanh toán, không có idempotency key.
5. POST tạo thanh toán, server có hỗ trợ idempotency key hợp lệ và request body có thể phát lại.
6. PATCH tăng số lượng tồn kho bằng một phép cộng tương đối.

Giải thích riêng **method semantics**, **body replayability** và **server-side deduplication**.

### Bài 2 — Đọc stdout của retry policy

Chạy `AsyncRetryDemo.java` và xác nhận các số lượt `3, 1, 2, 2, 1`. Giải thích từng trường hợp: tại sao GET đầu cần ba lượt, POST không contract chỉ một lượt, và POST one-shot vẫn không retry dù có idempotency key.

### Bài 3 — Khả năng replay của stream

Chạy `ReplayBodyDemo.java` và sửa supplier thành một biến `ByteArrayInputStream` duy nhất được trả lại nhiều lần. Quan sát/giải thích vì sao hai subscription không còn đảm bảo cùng payload. Khôi phục supplier tạo stream mới; so sánh bytes của hai lần chứ không chỉ độ dài.

### Bài 4 — Thêm một trạng thái không được retry

Cho fake trả `401` trong lần đầu của GET. Kiểm tra policy không retry và trả `401`. Giải thích vì sao một token hết hạn cần giải quyết cơ chế authentication/refresh có kiểm soát thay vì retry nguyên request liên tục.

### Bài 5 — `Retry-After` và ngân sách

Thiết kế policy cho `429 Retry-After: 120` khi overall deadline còn 3 giây. Nên **không chờ 120 giây** trong use case có SLA 3 giây; trả lỗi/đề nghị thử lại sau theo contract và có thể đưa thời gian đến một hệ thống hàng đợi riêng.

### Bài 6 — Tính số attempts ở nhiều tầng

Nếu ứng dụng thử 3 lần, proxy thử tối đa 2 lần cho mỗi request và backend client cũng thử 2 lần cho mỗi kết nối, tình huống xấu nhất có thể tới **12 lần cố gắng**. Giải thích vì sao phải tập trung retry ownership, giới hạn tổng số lần và đo metrics ở từng tầng.

### Bài 7 — Chuẩn bị triển khai production

Viết checklist cho một client POST có body JSON lớn:

- Operation có idempotency key được server hỗ trợ không?
- Body có thể snapshot hoặc mở stream mới với **cùng bytes** không?
- Retryable status/error nào được phép?
- Có overall deadline, per-attempt timeout, backoff/jitter và `Retry-After` không?
- Có bảo vệ RAM/đĩa, đóng stream, cancellation và metrics không?
- Nếu timeout sau khi server đã xử lý, truy vấn kết quả bằng operation ID như thế nào?

### Checklist hoàn thành

- [ ] Phân biệt safe, idempotent và body replayability.
- [ ] Hiểu GET/HEAD an toàn theo HTTP, PUT/DELETE idempotent nhưng có side effect, POST/PATCH không mặc định idempotent.
- [ ] Biết `HttpClient.sendAsync` dùng `CompletableFuture` và HTTP 503 có thể là response thành công về I/O.
- [ ] Hiểu `BodyPublisher` có thể phải được subscribe lại khi request gửi lại, và dữ liệu phải tương đương.
- [ ] Biết `ofInputStream` cần supplier mở stream mới; `ofFile` cần file ổn định; custom publisher cần hỗ trợ replay.
- [ ] Không dùng `contentLength` làm bằng chứng khả năng replay.
- [ ] Dùng idempotency key **đúng hợp đồng server**, ổn định cho một operation, không đổi body.
- [ ] Có retry budget, backoff/jitter, `Retry-After`, deadline và cancellation policy.
- [ ] Chạy và kiểm tra output hai ví dụ Java 11.
- [ ] Không retry mù side effect sau lỗi mạng hoặc timeout.

## 19. Tài liệu tham khảo đang áp dụng

1. [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html) — `sendAsync`, kiểu future và xử lý exception.
2. [Java SE 11 — HttpRequest.BodyPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html) — hợp đồng `Flow.Publisher<ByteBuffer>`, subscription mới khi gửi lại, độ dài và vòng đời buffer.
3. [Java SE 11 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html) — `ofString`, `ofByteArray`, `ofFile`, `ofInputStream(Supplier)` và `fromPublisher`.
4. [Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — `handle`, `thenCompose`, `failedFuture`, `delayedExecutor` và `orTimeout`.
5. [Java SE 11 — Flow.Subscription](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.Subscription.html) — `request`, `cancel` và backpressure.
6. [RFC 9110 — HTTP Semantics, Section 9.2](https://www.rfc-editor.org/rfc/rfc9110#section-9.2) — safe/idempotent methods và lưu ý về tự động retry.
7. [RFC 9110 — Retry-After](https://www.rfc-editor.org/rfc/rfc9110#section-10.2.3) — delay-seconds và HTTP-date.
8. [Java SE 25 — HttpClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html) — đối chiếu sự tồn tại của API HTTP Client trên JDK LTS hiện đại.

**Ghi nhớ:** retry HTTP bất đồng bộ chỉ an toàn khi **operation được phép lặp**, **request body phát lại đúng dữ liệu**, và **lỗi/status thực sự phù hợp để retry trong ngân sách thời gian/tài nguyên**. Java 11 hỗ trợ `sendAsync`, `CompletableFuture` và các `BodyPublisher` cần thiết, nhưng tính idempotent của POST, việc tránh giao dịch trùng và chính sách retry cuối cùng vẫn phải được **xác nhận bằng hợp đồng ứng dụng/server**, không suy đoán từ tên method hay exception.