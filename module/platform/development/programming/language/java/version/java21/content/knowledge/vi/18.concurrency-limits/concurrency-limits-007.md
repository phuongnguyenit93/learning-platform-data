# Ngân sách timeout xuyên nhiều bước của một request

Một request thường đi qua nhiều bước: xác thực, đọc dữ liệu, gọi dịch vụ khác, ghi database và dựng response. Nếu mỗi bước tự đặt timeout tối đa giống nhau, tổng thời gian xử lý có thể vượt xa thời gian mà client hoặc gateway chờ đợi. Cách phù hợp là cấp cho request một **ngân sách thời gian (timeout budget)** duy nhất, biểu diễn bằng một deadline, rồi truyền deadline đó qua các bước.

Trong Java 21, có thể triển khai cách làm này bằng `System.nanoTime()`, `Duration`, các API timeout của thư viện I/O và các API chờ kết quả như `Future.get(timeout, unit)`. Virtual thread giúp tổ chức mỗi request theo luồng xử lý đồng bộ dễ đọc, nhưng không tự tạo ra timeout xuyên suốt và cũng không tự hủy mọi thao tác khi deadline hết hạn.

## 1. Vì sao cần một timeout budget chung?

Giả sử một request có ngân sách 2 giây và thực hiện tuần tự ba bước:

| Bước | Timeout riêng |
|---|---:|
| Đọc hồ sơ người dùng | 2 giây |
| Gọi dịch vụ đơn hàng | 2 giây |
| Ghi kết quả | 2 giây |

Nếu mỗi bước đều được phép dùng hết timeout riêng, tổng thời gian có thể lên tới 6 giây, chưa kể thời gian xử lý nội bộ. Client hoặc API gateway có thể đã timeout sau 2 giây, trong khi backend vẫn tiếp tục làm việc.

Một timeout budget chung giải quyết vấn đề bằng cách tính thời gian còn lại sau mỗi bước. Nếu request bắt đầu với 2 giây và bước đầu tiêu thụ 600 ms, bước tiếp theo chỉ còn tối đa khoảng 1.4 giây. Các bước sau tiếp tục dùng phần ngân sách còn lại.

Cần phân biệt:

- **Timeout của một bước:** thời gian tối đa mà một thao tác cụ thể được phép chờ.
- **Deadline của request:** thời điểm cuối cùng mà toàn bộ request cần hoàn thành.
- **Remaining budget:** khoảng thời gian còn lại từ hiện tại đến deadline.

Timeout của từng bước nên là giá trị nhỏ hơn giữa giới hạn riêng của bước và ngân sách còn lại của request.

## 2. Dùng System.nanoTime để đo thời gian đã trôi qua

Để quản lý deadline trong cùng một JVM, nên dùng `System.nanoTime()` thay vì `System.currentTimeMillis()` hoặc `Instant.now()`.

`System.nanoTime()` cung cấp đồng hồ đơn điệu (monotonic clock), phù hợp để đo khoảng thời gian. Giá trị trả về không phải thời gian lịch và không có ý nghĩa để chuyển thành ngày giờ thực tế. Điều quan trọng là hiệu số giữa hai lần đọc.

Ngược lại, đồng hồ lịch như `System.currentTimeMillis()` có thể thay đổi do đồng bộ thời gian hệ thống hoặc điều chỉnh đồng hồ. Nếu dùng nó để đo timeout, thay đổi đồng hồ có thể làm thời gian còn lại bị tính sai.

Ví dụ:

```java
long startedAt = System.nanoTime();

// Thực hiện một công việc.

long elapsedNanos = System.nanoTime() - startedAt;
```

Cách tính bằng phép trừ phù hợp với đặc tính của `nanoTime()`, kể cả khi bộ đếm nội bộ tràn số, miễn là khoảng thời gian cần đo nhỏ hơn khoảng biểu diễn hợp lệ của hiệu số. Với timeout của request, các khoảng thời gian thực tế thường nhỏ hơn rất nhiều giới hạn đó.

## 3. Biểu diễn deadline dùng chung

Có thể tạo một lớp nhỏ giữ deadline theo đơn vị nanosecond. Lớp này cung cấp thời gian còn lại và giới hạn timeout cho từng bước.

```java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeoutException;

public final class Deadline {
    private final long deadlineNanos;

    private Deadline(long deadlineNanos) {
        this.deadlineNanos = deadlineNanos;
    }

    public static Deadline after(Duration budget) {
        Objects.requireNonNull(budget, "budget");

        long nanos = budget.toNanos();
        if (nanos <= 0) {
            throw new IllegalArgumentException(
                    "Budget phải lớn hơn 0");
        }

        return new Deadline(System.nanoTime() + nanos);
    }

    public Duration remaining() throws TimeoutException {
        long nanos = deadlineNanos - System.nanoTime();

        if (nanos <= 0) {
            throw new TimeoutException("Request deadline đã hết");
        }

        return Duration.ofNanos(nanos);
    }

    public Duration cap(Duration stepLimit)
            throws TimeoutException {
        Objects.requireNonNull(stepLimit, "stepLimit");

        if (stepLimit.isZero() || stepLimit.isNegative()) {
            throw new IllegalArgumentException(
                    "Step limit phải lớn hơn 0");
        }

        Duration left = remaining();
        return left.compareTo(stepLimit) < 0
                ? left
                : stepLimit;
    }
}
```

Cách sử dụng:

```java
Deadline deadline = Deadline.after(Duration.ofSeconds(2));

Duration profileTimeout =
        deadline.cap(Duration.ofMillis(700));

Duration orderTimeout =
        deadline.cap(Duration.ofSeconds(1));
```

Phương thức `remaining()` trả về ngân sách còn lại. Phương thức `cap(stepLimit)` chọn giới hạn nhỏ hơn giữa timeout riêng của bước và thời gian còn lại của request.

Lớp ví dụ giả định budget là một khoảng thời gian thực tế, dương và đủ nhỏ để chuyển sang nanosecond bằng `Duration.toNanos()`. Với cấu hình timeout do người dùng hoặc hệ thống khác cung cấp, cần kiểm tra giới hạn đầu vào và xử lý `ArithmeticException` nếu duration quá lớn để biểu diễn bằng long nanosecond.

## 4. Truyền deadline qua các bước tuần tự

Không nên truyền lại timeout ban đầu cho mỗi phương thức. Hãy truyền cùng một deadline hoặc remaining budget để mỗi bước biết request còn bao nhiêu thời gian.

Ví dụ mô hình xử lý:

```java
Response handleRequest(String userId) throws Exception {
    Deadline deadline = Deadline.after(Duration.ofSeconds(2));

    User user = userService.load(
            userId,
            deadline.cap(Duration.ofMillis(600))
    );

    Order order = orderService.loadLatest(
            user.id(),
            deadline.cap(Duration.ofMillis(900))
    );

    deadline.remaining(); // Kiểm tra request vẫn còn thời gian.

    return Response.from(user, order);
}
```

Mỗi service nhận timeout riêng đã được giới hạn theo ngân sách request. Nếu bước đọc user mất 500 ms, bước lấy order không còn được dùng 900 ms đầy đủ nếu deadline chỉ còn ít hơn khoảng đó.

Trong thiết kế lớn hơn, nên truyền đối tượng deadline xuyên qua các lớp nội bộ thay vì truyền một giá trị timeout ban đầu. Như vậy, mọi bước đều tính remaining budget tại thời điểm thực thi và không vô tình khởi động lại đồng hồ.

Không nên tạo một deadline mới trong mỗi service nếu đó vẫn là cùng một request. Làm như vậy sẽ reset ngân sách và phá vỡ giới hạn thời gian tổng thể.

## 5. Áp dụng deadline cho HTTP Client

Java 21 cung cấp `java.net.http.HttpClient`. Có thể đặt timeout cho một request bằng `HttpRequest.Builder.timeout(Duration)`. Khi gửi request, hãy lấy remaining budget ngay trước khi tạo request.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.TimeoutException;

class RemoteProfileClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(500))
            .build();

    String fetch(URI uri, Deadline deadline)
            throws Exception {
        Duration timeout =
                deadline.cap(Duration.ofMillis(800));

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(timeout)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        return response.body();
    }
}
```

Trong ví dụ:

- `connectTimeout` giới hạn thời gian thiết lập kết nối theo cấu hình của HttpClient.
- `HttpRequest.timeout` đặt giới hạn cho request cụ thể.
- `deadline.cap(...)` đảm bảo timeout của request không vượt quá ngân sách còn lại hoặc giới hạn riêng của bước.

Timeout kết nối và timeout request có phạm vi khác nhau. Không nên coi `connectTimeout` là timeout tổng của toàn bộ request. Khi cần deadline xuyên suốt, hãy đặt timeout cho từng request theo remaining budget; đồng thời cấu hình timeout kết nối phù hợp với chính sách của client.

Khi timeout xảy ra, API có thể ném `HttpTimeoutException`, là một loại `IOException`. Ứng dụng cần phân biệt lỗi timeout với lỗi kết nối hoặc lỗi xử lý response để quyết định retry hay trả lỗi cho caller.

## 6. Áp dụng deadline khi chờ Future

Một tác vụ có thể chạy qua `ExecutorService` và trả về `Future`. Phương thức `Future.get(timeout, unit)` giới hạn thời gian chờ kết quả. Cần truyền remaining budget thay vì timeout ban đầu.

```java
import java.util.concurrent.*;

String loadWithDeadline(
        ExecutorService executor,
        Deadline deadline) throws Exception {

    Future<String> future = executor.submit(
            () -> callRemoteService()
    );

    try {
        long remaining = deadline.remaining().toNanos();
        return future.get(remaining, TimeUnit.NANOSECONDS);
    } catch (TimeoutException ex) {
        future.cancel(true);
        throw ex;
    }
}
```

Khi deadline hết hạn, `get` ném `TimeoutException`; gọi `cancel(true)` yêu cầu task đang chạy dừng bằng cách gửi interrupt. Đây là yêu cầu hủy, không phải bảo đảm rằng công việc đã dừng ngay lập tức.

Task phải hợp tác với interruption. Nếu code bỏ qua interrupt hoặc đang gọi thư viện không hỗ trợ hủy đúng cách, công việc có thể tiếp tục chạy sau khi caller đã timeout. Với HTTP, database hoặc driver, cần hiểu chính sách timeout/cancel riêng của thư viện đang dùng.

Virtual thread không thay đổi nguyên tắc này. Nó giúp việc chờ blocking có chi phí thấp hơn, nhưng timeout và hủy vẫn phải được truyền xuống đúng API thực hiện I/O.

## 7. Ngân sách khi gọi nhiều dịch vụ song song

Khi request gọi nhiều dịch vụ song song, tất cả nhánh vẫn phải chia sẻ cùng deadline. Không cấp lại toàn bộ timeout ban đầu cho từng nhánh.

Ví dụ một request có 1.5 giây để gọi song song dịch vụ hồ sơ và dịch vụ quyền truy cập. Hai thao tác bắt đầu gần như cùng lúc, vì vậy tổng thời gian chờ thường gần với nhánh hoàn thành chậm hơn, không phải tổng thời gian của hai nhánh. Tuy nhiên, cả hai vẫn phải dừng hoặc trả kết quả theo cùng deadline.

```java
import java.util.concurrent.*;

record CombinedData(String profile, String permissions) {}

CombinedData loadBoth(
        ExecutorService executor,
        Deadline deadline) throws Exception {

    Future<String> profile = executor.submit(
            () -> loadProfile(deadline)
    );
    Future<String> permissions = executor.submit(
            () -> loadPermissions(deadline)
    );

    try {
        String p = profile.get(
                deadline.remaining().toNanos(),
                TimeUnit.NANOSECONDS
        );

        String a = permissions.get(
                deadline.remaining().toNanos(),
                TimeUnit.NANOSECONDS
        );

        return new CombinedData(p, a);
    } catch (ExecutionException | TimeoutException ex) {
        profile.cancel(true);
        permissions.cancel(true);
        throw ex;
    } catch (InterruptedException ex) {
        profile.cancel(true);
        permissions.cancel(true);
        throw ex;
    }
}
```

Trong ví dụ, mỗi lần chờ Future đều tính lại remaining budget. Nếu nhánh profile đã dùng gần hết thời gian, nhánh permissions chỉ còn phần ngân sách thực tế còn lại.

Với xử lý song song, nên cân nhắc chờ các kết quả theo deadline chung và hủy các nhánh còn lại khi request không thể hoàn thành. Nếu cần xử lý nhiều task theo nhóm và quản lý vòng đời theo cấu trúc, có thể xem xét các API concurrency phù hợp với phiên bản JDK triển khai; không nên dùng preview API Java 21 làm hợp đồng mặc định cho ứng dụng ổn định.

## 8. Retry và backoff cũng tiêu thụ ngân sách

Retry không được khởi động lại timeout tổng. Mỗi lần thử và thời gian backoff đều tiêu thụ ngân sách của request.

Ví dụ request có deadline 3 giây:

| Hoạt động | Thời gian đã dùng | Ngân sách còn lại |
|---|---:|---:|
| Bắt đầu | 0 ms | 3000 ms |
| Lần gọi đầu | 700 ms | 2300 ms |
| Backoff | 200 ms | 2100 ms |
| Lần gọi thứ hai | 900 ms | 1200 ms |
| Backoff tiếp | 300 ms | 900 ms |

Trước mỗi lần retry, phải kiểm tra remaining budget. Nếu thời gian còn lại không đủ cho một lần thử có ý nghĩa, nên dừng và trả lỗi thay vì bắt đầu thêm một request chắc chắn vượt deadline.

Ví dụ:

```java
String callWithRetry(Deadline deadline) throws Exception {
    int attempts = 0;

    while (attempts < 3) {
        deadline.remaining(); // Dừng ngay nếu request đã hết ngân sách.

        try {
            return callRemote(
                    deadline.cap(Duration.ofMillis(700))
            );
        } catch (TransientException ex) {
            attempts++;

            if (attempts >= 3) {
                throw ex;
            }

            Duration backoff = Duration.ofMillis(150);
            if (deadline.remaining().compareTo(backoff) <= 0) {
                throw new TimeoutException(
                        "Không còn đủ ngân sách để retry");
            }

            Thread.sleep(backoff);
        }
    }

    throw new IllegalStateException("Không thể tới đây");
}
```

Ví dụ trên minh họa nguyên tắc. Trong code thực tế, cần phân biệt lỗi tạm thời có thể retry với lỗi không thể retry; đồng thời backoff nên bị giới hạn bởi remaining budget. Nếu dùng `Thread.sleep`, phải xử lý `InterruptedException` và giữ nguyên trạng thái interrupt nếu không thể truyền exception lên caller.

## 9. Chuyển deadline qua ranh giới service

Trong cùng một JVM, có thể truyền trực tiếp đối tượng deadline dựa trên `System.nanoTime()`. Không được gửi giá trị `deadlineNanos` sang một process hoặc máy khác rồi so sánh với `System.nanoTime()` tại đó.

Lý do: origin của `System.nanoTime()` không phải mốc thời gian chung giữa các process hoặc host. Giá trị tuyệt đối của nó chỉ có ý nghĩa trong JVM hiện tại để tính hiệu số.

Khi gọi service khác qua HTTP hoặc messaging, có thể truyền:

- **Remaining timeout:** khoảng thời gian còn lại tại thời điểm gửi, dưới dạng đơn vị rõ ràng như milliseconds.
- **Absolute wall-clock deadline:** mốc UTC, ví dụ một timestamp, nếu các hệ thống có chính sách đồng bộ clock và xử lý clock skew.

Remaining timeout thường dễ áp dụng trong một request chain: mỗi service nhận thời gian còn lại và tiếp tục trừ phần thời gian tiêu thụ tại service đó. Tuy nhiên, thời gian truyền mạng cũng tiêu thụ ngân sách; caller nên gửi giá trị đã tính tại thời điểm gần gửi nhất và service nhận không nên reset về timeout mặc định ban đầu.

Không gửi giá trị nanosecond thô từ `System.nanoTime()` qua mạng. Không có bảo đảm hai JVM có cùng origin hoặc cùng thang đo tuyệt đối cho giá trị đó.

## 10. Timeout không đồng nghĩa với hủy công việc

Khi caller hết thời gian chờ, điều đó không có nghĩa mọi hoạt động phía dưới tự động dừng. Một timeout có thể chỉ khiến caller ngừng chờ kết quả; task hoặc thao tác I/O vẫn tiếp tục nếu API không hỗ trợ cancellation hoặc code không phản hồi interrupt.

Cần phân biệt:

| Hành động | Ý nghĩa |
|---|---|
| Đặt timeout | Giới hạn thời gian chờ của một API |
| Caller timeout | Caller không chờ kết quả thêm và nhận lỗi timeout |
| Cancel Future | Gửi yêu cầu hủy task; có thể gửi interrupt |
| Dừng I/O | Phụ thuộc API, driver, socket và khả năng cancellation |
| Deadline propagation | Cho các bước phía dưới biết thời gian còn lại |

Để tránh công việc mồ côi sau khi request đã timeout:

- Truyền remaining budget xuống tầng HTTP/database.
- Dùng API có timeout/cancel phù hợp.
- Kiểm tra interruption trong các vòng lặp hoặc tác vụ dài.
- Hủy các task song song còn lại khi request thất bại.
- Đóng tài nguyên bằng try-with-resources.
- Không retry nếu deadline đã hết.

## 11. Chọn timeout cho từng tầng

Một hệ thống có thể có nhiều timeout khác nhau. Chúng nên được cấu hình theo quan hệ cha-con, trong đó timeout của thao tác con không vượt quá ngân sách còn lại của request.

| Tầng | Ví dụ timeout | Vai trò |
|---|---|---|
| Client/API gateway | Tổng thời gian chờ request | Giới hạn trải nghiệm đầu cuối |
| Server request handler | Request deadline | Ngân sách chung trong ứng dụng |
| HTTP connect | Thời gian thiết lập kết nối | Giới hạn bước mở kết nối |
| HTTP request | Thời gian chờ response | Giới hạn lần gọi service |
| Database query | Query timeout của statement/driver | Giới hạn truy vấn |
| Future/task | Thời gian chờ kết quả | Giới hạn caller chờ task |
| Retry/backoff | Phần ngân sách còn lại | Tránh retry vượt deadline |

Không nên đặt timeout của backend dài hơn timeout của gateway một cách vô tình. Nếu gateway timeout sau 2 giây nhưng backend vẫn làm việc 10 giây, hệ thống có thể tiếp tục tiêu thụ thread, connection và tài nguyên cho request mà caller đã bỏ cuộc.

Đồng thời, không nên đặt tất cả timeout giống hệt nhau mà không xét overhead. Cần dành một phần ngân sách cho serialize response, ghi log cần thiết, cleanup và truyền response về caller.

## 12. Các lỗi thường gặp

| Lỗi thiết kế | Hậu quả | Cách xử lý |
|---|---|---|
| Mỗi bước dùng lại timeout ban đầu | Tổng thời gian request có thể vượt giới hạn | Truyền một deadline chung |
| Dùng `currentTimeMillis()` để đo elapsed time | Clock adjustment có thể làm sai phép đo | Dùng `System.nanoTime()` trong cùng JVM |
| Tạo deadline mới ở mỗi service nội bộ | Ngân sách bị reset sau mỗi bước | Truyền cùng deadline hoặc remaining budget |
| Gọi Future.get với timeout ban đầu ở mỗi lần chờ | Tổng thời gian chờ có thể vượt deadline | Tính remaining trước mỗi lần get |
| Retry không tính backoff | Retry tiếp tục sau khi request đã hết thời gian | Trừ thời gian backoff vào ngân sách |
| Cho rằng TimeoutException tự dừng task | Task có thể tiếp tục chạy nền | Hủy task và bảo đảm code/API phản hồi cancellation |
| Truyền nanoTime qua network | Các host không có chung origin monotonic clock | Truyền remaining duration hoặc deadline UTC có kiểm soát |
| Cấu hình connect timeout nhưng bỏ request timeout | Kết nối thành công nhưng chờ response quá lâu | Cấu hình cả timeout theo đúng phạm vi |
| Dùng timeout quá nhỏ mà không xét độ phân giải API | Một số API chỉ nhận đơn vị giây hoặc có semantics riêng | Kiểm tra độ phân giải và hành vi của driver/API |

## 13. Quy trình áp dụng trong Java 21

Khi thiết kế request có nhiều bước, hãy thực hiện theo trình tự:

1. Xác định ngân sách đầu cuối dựa trên timeout của caller hoặc SLA.
2. Tạo một deadline ngay khi bắt đầu xử lý request bằng `System.nanoTime()`.
3. Truyền deadline qua các bước nội bộ, không tạo lại timeout đầy đủ.
4. Trước mỗi I/O hoặc lần chờ, lấy remaining budget và áp dụng giới hạn riêng của bước.
5. Tính cả thời gian retry, backoff và xử lý song song vào ngân sách chung.
6. Khi deadline hết, dừng nhận thêm công việc, hủy task còn lại khi có thể và trả lỗi timeout phù hợp.
7. Đảm bảo các API I/O và driver có timeout riêng; không giả định timeout của caller tự dừng mọi thao tác.
8. Ghi nhận timeout theo từng tầng để xác định bước nào thường xuyên tiêu thụ hết ngân sách.

Ngân sách timeout xuyên request giúp các tầng trong ứng dụng cùng tuân theo một giới hạn thời gian đầu cuối. Trong Java 21, kết hợp deadline đơn điệu, `Duration`, timeout của HTTP/Future và cơ chế cancellation phù hợp giúp request có hành vi dễ dự đoán hơn. Virtual thread làm mô hình thread-per-request thuận tiện, nhưng chính sách deadline, giới hạn tài nguyên và hủy tác vụ vẫn cần được thiết kế rõ ràng.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime())
- [Oracle Java SE 21 API — Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)
- [Oracle Java SE 21 API — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration))
- [Oracle Java SE 21 API — Future.get](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html#get(long,java.util.concurrent.TimeUnit))
- [Oracle Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
