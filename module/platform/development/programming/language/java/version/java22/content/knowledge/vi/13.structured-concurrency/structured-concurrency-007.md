# Timeout, thời hạn xử lý và đóng scope khi tác vụ con chưa kết thúc

## 1. Mục tiêu và mốc API sử dụng

Khi một yêu cầu chia thành nhiều tác vụ con, timeout phải được hiểu cùng với vòng đời của các tác vụ đó. Một yêu cầu đã hết thời gian hữu ích vẫn có thể cần chờ tác vụ con phản hồi hủy và giải phóng tài nguyên.

Bài này thuộc chương **Đồng thời có cấu trúc** trong module Java 22, tập trung vào những nguyên lý tiếp tục áp dụng trong Java hiện đại. **Các ví dụ dùng đúng API JDK 27; `StructuredTaskScope` vẫn là preview trong phiên bản này.** Cần bật preview ở cả bước biên dịch và chạy. Xem [API StructuredTaskScope của JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Mục tiêu của bài:

- Phân biệt timeout tương đối, deadline và thời gian đóng scope.
- Đặt ngân sách chung cho các tác vụ con.
- Xử lý đúng timeout, lỗi tác vụ và việc owner thread bị interrupt.
- Giải thích vì sao hết timeout chưa đồng nghĩa phương thức đã trả về.
- Thiết kế tác vụ có thể hủy và truyền ngân sách còn lại qua các tầng xử lý.

Các ví dụ không sử dụng API preview cũ của Java 22. Khi chạy bài thực hành, chọn JDK 27 cho cả `javac` và `java`; không giả định mã dùng preview của một phiên bản sẽ dùng nguyên trạng trên phiên bản khác.

## 2. Ba khái niệm cần tách biệt

| Khái niệm | Câu hỏi nó trả lời | Biểu diễn thường dùng |
| --- | --- | --- |
| Timeout tương đối | Từ lúc bắt đầu, được dành bao lâu? | `Duration.ofMillis(250)` |
| Deadline | Kết quả cần sẵn sàng trước thời điểm nào? | `Instant` |
| Hoàn tất đóng scope | Khi nào mọi luồng tác vụ con trong scope đã kết thúc? | `close()` hoàn tất |

Giả sử một màn hình cần đồng thời lấy hồ sơ người dùng và tồn kho. Nếu tồn kho trả về sau năm giây trong khi màn hình chỉ còn ngân sách 250 ms, kết quả đó đã quá muộn để đáp ứng yêu cầu ban đầu.

Tuy vậy, ngừng cần kết quả và kết thúc tác vụ là hai mốc khác nhau. Tác vụ có thể đang:

- Chờ một thao tác I/O phản hồi.
- Đang xử lý một khối dữ liệu dài.
- Thoát khỏi vòng lặp sau khi nhận tín hiệu hủy.
- Chạy `finally` để giải phóng tài nguyên.

Bạn cần tính cả phần việc này khi thiết kế độ trễ của yêu cầu.

### Timeout của scope bắt đầu từ lúc nào?

Trong API đang dùng, timeout được cấu hình bằng `Configuration.withTimeout(Duration)` và bắt đầu khi scope được mở, không phải khi gọi `join()`. Vì thế, thời gian chuẩn bị và fork bên trong scope cũng tiêu thụ ngân sách. Khi hết hạn trước hoặc trong lúc chờ, scope bị hủy. Xem [cấu hình và mở scope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#open(java.util.function.UnaryOperator)).

Ví dụ dự kiến:

```text
0 ms                  90 ms                            250 ms
| mở scope            | gọi join                       | hết timeout
|------ chuẩn bị -----|---------- tiếp tục chờ ----------|
```

Tại mốc 90 ms, ngân sách còn khoảng 160 ms, không phải một khoảng 250 ms mới.

Để đối chiếu, `Future.get(timeout, unit)` giới hạn thời gian của lần chờ đó; bản thân việc chờ hết hạn không phải lời gọi hủy tác vụ. Xem [Future.get có timeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html#get(long,java.util.concurrent.TimeUnit)).

## 3. Ví dụ hoàn chỉnh: đặt timeout cho hai tác vụ

Lưu chương trình sau thành `TimeoutScopeDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class TimeoutScopeDemo {
    record Dashboard(String profile, int stock) {}

    static Dashboard loadDashboard(Duration timeout)
            throws InterruptedException, ExecutionException {
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("Timeout phải dương");
        }

        try (var scope = StructuredTaskScope.<Object>open(
                config -> config
                        .withName("dashboard")
                        .withTimeout(timeout))) {

            var profile = scope.fork(TimeoutScopeDemo::readProfile);
            var stock = scope.fork(TimeoutScopeDemo::readStock);

            scope.join();

            return new Dashboard(profile.get(), stock.get());
        }
    }

    private static String readProfile() throws InterruptedException {
        Thread.sleep(Duration.ofMillis(70));
        return "user-42";
    }

    private static int readStock() throws InterruptedException {
        try {
            Thread.sleep(Duration.ofSeconds(2));
            return 8;
        } finally {
            System.out.println("stock: đã đi qua finally");
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        long started = System.nanoTime();

        try {
            var result = loadDashboard(Duration.ofMillis(250));
            System.out.println(result);
        } catch (ExecutionException exception) {
            if (exception.getCause()
                    instanceof StructuredTaskScope.CancelledByTimeoutException) {
                System.out.println("Hết thời gian xử lý; scope đã đóng.");
            } else {
                throw exception;
            }
        } finally {
            long elapsedMillis =
                    (System.nanoTime() - started) / 1_000_000;
            System.out.println("Thời gian quan sát: "
                    + elapsedMillis + " ms");
        }
    }
}
```

Trong thư mục chứa tệp, dùng JDK 27:

```powershell
javac --enable-preview --release 27 -encoding UTF-8 TimeoutScopeDemo.java
if ($LASTEXITCODE -ne 0) {
    throw 'Bien dich that bai.'
}
java --enable-preview TimeoutScopeDemo
```

Cờ biên dịch và chạy được mô tả trong tài liệu [javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) và [java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

### Đọc ví dụ theo luồng điều khiển

1. `loadDashboard` mở một scope có ngân sách 250 ms.
2. Hai tác vụ được fork; một tác vụ mô phỏng đọc hồ sơ nhanh, tác vụ kia mô phỏng đọc tồn kho chậm.
3. Owner gọi `join()` để lấy kết quả của chính sách phối hợp.
4. Khi timeout xảy ra, tác vụ tồn kho đang ngủ có thể nhận interrupt và đi qua `finally`.
5. `loadDashboard` chỉ thoát hẳn sau bước đóng scope tự động.
6. `main` xử lý ngoại lệ rồi ghi nhận tổng thời gian quan sát.

Với chính sách mặc định của `open(configOperator)` trong JDK 27, lỗi tác vụ hoặc timeout được báo qua `ExecutionException`. Marker cho trường hợp scope bị hủy do timeout là `StructuredTaskScope.CancelledByTimeoutException` trong `getCause()`. Xem [định nghĩa marker timeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.CancelledByTimeoutException.html).

Đầu ra của một lượt chạy có thể có dạng:

```text
stock: đã đi qua finally
Hết thời gian xử lý; scope đã đóng.
Thời gian quan sát: <một giá trị đo được> ms
```

Không đặt điều kiện rằng số đo phải đúng 250 ms. Việc lập lịch, nhận interrupt, chạy cleanup và ghi log đều ảnh hưởng đến số đo. Trên một hệ thống quá bận, ngay cả thời điểm tác vụ con bắt đầu cũng có thể khác dự kiến.

## 4. Vì sao join báo timeout nhưng close vẫn chờ?

Vòng đời cần hiểu là:

```text
Mở scope
    -> Fork tác vụ
    -> Chờ kết quả phối hợp
    -> Hết ngân sách: yêu cầu hủy các tác vụ chưa xong
    -> join báo outcome
    -> close chờ các luồng tác vụ kết thúc
    -> Phương thức chứa scope mới có thể thoát hẳn
```

`close()` hủy scope nếu cần, rồi chờ tất cả luồng tác vụ trong scope kết thúc. Nếu owner bị interrupt trong lúc đóng, nó vẫn tiếp tục chờ và hoàn tất với trạng thái interrupt được đặt. Xem [hợp đồng close của JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html#close()).

Đó là lý do chương trình không để các tác vụ con còn chạy vượt ra ngoài thời gian sống của scope. Đổi lại, một tác vụ không phản hồi hủy có thể kéo dài thời gian thoát scope.

`close()` không thay thế `join()`. Sau khi đã fork tác vụ, owner cần thử gọi `join()` để lấy outcome. Nếu bỏ qua bước này, `close()` vẫn đợi đóng rồi báo `IllegalStateException`; khi đang có một ngoại lệ khác truyền ra, lỗi đóng có thể xuất hiện trong danh sách suppressed. Các thao tác fork, join và close phải do owner thực hiện.

### Vị trí catch quyết định bạn đang quan sát mốc nào

```java
try (var scope = StructuredTaskScope.<Object>open(
        config -> config.withTimeout(Duration.ofMillis(250)))) {
    scope.fork(TimeoutScopeDemo::readStock);

    try {
        scope.join();
    } catch (ExecutionException exception) {
        // Đã có outcome từ join, nhưng scope vẫn đang mở.
        System.out.println("join đã báo lỗi");
        throw exception;
    }
} catch (ExecutionException exception) {
    // Bước close tự động đã chạy trước khi đến đây.
    System.out.println("đã ra khỏi scope");
    throw exception;
}
```

Đoạn này minh họa vị trí đặt `catch` trong một phương thức có khai báo các ngoại lệ tương ứng; nó không thay thế toàn bộ chương trình ở phần 3.

Với `try`-with-resources, các `catch` gắn với câu lệnh nằm ngoài bước đóng tài nguyên tự động. Nếu cần phân tích ngoại lệ phát sinh thêm khi đóng, xem cả `getSuppressed()` thay vì chỉ ghi chuỗi thông báo. Quy tắc này được mô tả trong [JLS 14.20.3](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.20.3).

Một lệnh `return` bên trong khối `try` cũng phải đi qua bước đóng tài nguyên trước khi kết quả được chuyển cho bên gọi. Vì vậy, trả fallback từ trong scope không tạo ra đường thoát tức thì nếu tác vụ con vẫn chưa kết thúc.

### Quan sát cleanup chậm

Để thực hành, thay `readStock` trong chương trình bằng phương thức dưới đây:

```java
private static int readStock() throws InterruptedException {
    try {
        Thread.sleep(Duration.ofSeconds(2));
        return 8;
    } finally {
        System.out.println("stock: bắt đầu cleanup mô phỏng");
        Thread.sleep(Duration.ofMillis(400));
        System.out.println("stock: cleanup mô phỏng hoàn tất");
    }
}
```

Lần `sleep` đầu có thể bị interrupt khi scope hết timeout. `InterruptedException` từ thao tác đó xóa trạng thái interrupt; trong lượt chạy chỉ có lần hủy này, phần mô phỏng cleanup vẫn có thể ngủ thêm khoảng 400 ms. Xem [cơ chế interrupt của Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html#interrupt()).

Nếu tác vụ đã bắt đầu đúng như dự kiến, tổng thời gian quan sát thường gồm cả thời gian đến timeout và thời gian cleanup. Một interrupt khác hoặc điều kiện lập lịch khác có thể làm diễn biến thay đổi.

Đây là mô phỏng để quan sát thời gian đóng scope. Trong mã ứng dụng, cleanup cần làm phần việc giải phóng tài nguyên cần thiết và kết thúc sớm; tránh thêm công việc chậm không phục vụ việc đóng tài nguyên.

## 5. Chuyển deadline thành ngân sách còn lại

Timeout tương đối phù hợp ở một tầng xử lý. Khi yêu cầu đi qua nhiều tầng, deadline giúp diễn đạt cùng một mốc kết thúc mong muốn.

Giả sử tổng ngân sách yêu cầu là 800 ms:

```text
Nhận yêu cầu        Xác thực xong       Gọi các dịch vụ
0 ms                120 ms              còn khoảng 680 ms
|----- 120 ms ------|---------------------------> deadline 800 ms
```

Nếu mỗi tầng đều tạo timeout 800 ms mới, tổng thời gian được cho phép sẽ tăng ngoài dự định. Tầng sau cần dùng phần ngân sách còn lại.

Thêm hai import sau vào ví dụ ở phần 3:

```java
import java.time.Instant;
import java.util.concurrent.TimeoutException;
```

Sau đó thêm phương thức vào `TimeoutScopeDemo`:

```java
static Dashboard loadBefore(Instant deadline)
        throws InterruptedException, ExecutionException, TimeoutException {
    Duration remaining = Duration.between(Instant.now(), deadline);

    if (remaining.isZero() || remaining.isNegative()) {
        throw new TimeoutException(
                "Yêu cầu đã hết hạn trước khi mở scope");
    }

    return loadDashboard(remaining);
}
```

Cách chuyển `Instant` thành `Duration` để cấu hình scope được nêu trong [Configuration.withTimeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html#withTimeout(java.time.Duration)).

Ở đây có hai nguồn báo quá hạn khác nhau:

| Thời điểm phát hiện | Cách báo trong ví dụ |
| --- | --- |
| Deadline đã qua trước khi mở scope | Mã ứng dụng chủ động ném `java.util.concurrent.TimeoutException` |
| Scope đang thực thi thì hết ngân sách | `join()` theo chính sách mặc định ném `ExecutionException` có cause là `CancelledByTimeoutException` |

Ngoại lệ `TimeoutException` trong `loadBefore` do chính mã ứng dụng tạo ra. Nó không phải ngoại lệ timeout trực tiếp mà `join()` của ví dụ JDK 27 đang ném.

Hãy tính thời gian còn lại sát lúc bắt đầu công việc cần giới hạn. Nếu có thêm một giai đoạn chờ dài giữa việc tính `remaining` và mở scope, giá trị đó đã không còn phản ánh đúng ngân sách còn lại.

## 6. Dùng đồng hồ đơn điệu cho ngân sách trong cùng JVM

`Instant` thuận tiện khi trao đổi một mốc thời gian. Với việc đo khoảng thời gian đã trôi qua bên trong cùng JVM, `System.nanoTime()` phù hợp hơn đồng hồ lịch. Giá trị tuyệt đối của nó không có ý nghĩa như một thời điểm UTC và không được truyền sang JVM khác để so sánh. Xem [System.nanoTime](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html#nanoTime()).

Một lớp ngân sách nhỏ có thể được thêm dưới dạng lớp lồng trong `TimeoutScopeDemo`:

```java
static final class RequestBudget {
    private final long startedNanos;
    private final long totalNanos;

    RequestBudget(Duration total) {
        if (total.isZero() || total.isNegative()) {
            throw new IllegalArgumentException("Ngân sách phải dương");
        }

        totalNanos = total.toNanos();
        startedNanos = System.nanoTime();
    }

    Duration remaining() throws java.util.concurrent.TimeoutException {
        long elapsed = System.nanoTime() - startedNanos;

        if (elapsed >= totalNanos) {
            throw new java.util.concurrent.TimeoutException(
                    "Không còn ngân sách xử lý");
        }

        return Duration.ofNanos(totalNanos - elapsed);
    }
}
```

Lớp này phục vụ ngân sách yêu cầu ngắn, chẳng hạn vài trăm mili giây hoặc vài giây. Mỗi lần cần bắt đầu một giai đoạn, gọi lại `remaining()` thay vì lưu và dùng lại một `Duration` đã tính từ lâu.

Ví dụ trong một phương thức xử lý có khai báo các ngoại lệ tương ứng:

```java
var budget = new RequestBudget(Duration.ofMillis(800));

// Những giai đoạn thực hiện sau thời điểm này cùng tiêu thụ ngân sách.
Dashboard dashboard = loadDashboard(budget.remaining());
```

Nếu còn một tầng gọi dịch vụ khác, truyền cùng đối tượng `budget` cho tầng đó để nó tự lấy thời gian còn lại lúc sắp bắt đầu thao tác. Nếu giới hạn riêng của dịch vụ là 200 ms và ngân sách yêu cầu còn 130 ms, chỉ cấp tối đa 130 ms cho lần gọi.

Hai nguyên tắc thiết kế:

- Đối với cùng một yêu cầu, các tầng dùng chung một ngân sách gốc.
- Ngân sách của một thao tác không vượt phần thời gian còn lại của yêu cầu.

Đây vẫn là cơ chế quản lý ngân sách mang tính phối hợp. Giữa phép đo và lúc bắt đầu thao tác luôn có một khoảng chuyển tiếp; nó không tạo ra bảo đảm thời gian thực cứng.

## 7. Tác vụ con phải phản hồi việc hủy

Scope có thể phát tín hiệu interrupt, nhưng mã tác vụ quyết định nó có thoát sớm hay không.

Với tác vụ đang gọi một phương thức interruptible như `Thread.sleep`, hãy cho `InterruptedException` truyền ra khi không có lý do xử lý tại chỗ. Các phương thức `readProfile` và `readStock` ở ví dụ đã chọn cách này.

Với đoạn tính toán kéo dài, có thể đặt điểm kiểm tra giữa các đơn vị công việc:

```java
static long sumValues(int[] values) throws InterruptedException {
    long sum = 0;

    for (int value : values) {
        if (Thread.interrupted()) {
            throw new InterruptedException("Dừng phép tính theo yêu cầu hủy");
        }

        sum += value;
    }

    return sum;
}
```

Trong mẫu này, `Thread.interrupted()` vừa kiểm tra vừa xóa cờ để phương thức báo việc gián đoạn bằng `InterruptedException`. Nếu chỉ cần quan sát trạng thái mà không xóa cờ, dùng `Thread.currentThread().isInterrupted()`. Xem [Thread.interrupted](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html#interrupted()).

Tránh bắt `InterruptedException` rồi tiếp tục một thao tác dài như chưa có yêu cầu hủy. Nếu biên API không thể khai báo ngoại lệ này, cần kết thúc công việc theo hợp đồng của biên đó và khôi phục trạng thái interrupt khi thích hợp.

### Phần việc của owner cũng phải ngắn

Timeout không phải một cơ chế cưỡng bức ngắt toàn bộ mã Java của owner. Nếu owner thực hiện một bước tính toán dài giữa các lần fork và `join()`, bước đó vẫn có thể làm yêu cầu chậm.

Trong vòng lặp tạo nhiều tác vụ, có thể kiểm tra `scope.isCancelled()` để tránh chuẩn bị thêm công việc sau khi scope đã bị hủy. Kiểm tra này chỉ cho biết trạng thái hủy; nó không chứng minh các luồng con đã kết thúc.

Hãy giữ giai đoạn fork ngắn và luôn đi đến điểm phối hợp kết quả theo cấu trúc dự kiến. Với scope lồng nhau, mỗi tầng cần đóng scope do mình mở trước khi tầng bên ngoài kết thúc.

### Khi việc đóng scope kéo dài

Có ba nhóm nguyên nhân cần phân biệt:

| Nhóm nguyên nhân | Hướng thiết kế |
| --- | --- |
| Tác vụ không kiểm tra hủy trong đoạn tính toán dài | Chia công việc thành phần đủ nhỏ và đặt điểm kiểm tra |
| Thư viện đang chờ thao tác không phản hồi interrupt | Dùng timeout/cơ chế hủy mà chính thư viện hỗ trợ |
| Cleanup làm quá nhiều việc hoặc chờ không giới hạn | Thu hẹp cleanup và kiểm soát các thao tác chờ bên trong |

Dành riêng một phần ngân sách dự kiến cho cleanup có thể giúp đạt mục tiêu độ trễ. Tuy nhiên, `withTimeout` không đặt một giới hạn riêng cho `close()`. Nếu cần ranh giới cưỡng bức cho công việc không thể hủy hợp tác, phải thiết kế ranh giới thực thi khác, chẳng hạn tiến trình được quản lý riêng.

## 8. Phối hợp timeout của scope với timeout I/O

Một ngân sách cho toàn bộ nhóm tác vụ và timeout của thao tác I/O giải quyết hai lớp vấn đề liên quan. Ví dụ, khi tác vụ con gửi HTTP request, có thể đặt timeout riêng cho request dựa trên ngân sách còn lại.

Thêm các import:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.TimeoutException;
```

Phương thức sau có thể đặt trong `TimeoutScopeDemo` cùng lớp `RequestBudget`:

```java
static String fetchText(
        HttpClient client,
        URI uri,
        RequestBudget budget)
        throws IOException, InterruptedException, TimeoutException {

    Duration remaining = budget.remaining();
    Duration perCallLimit = Duration.ofMillis(200);

    Duration requestTimeout =
            remaining.compareTo(perCallLimit) < 0
                    ? remaining
                    : perCallLimit;

    var request = HttpRequest.newBuilder(uri)
            .timeout(requestTimeout)
            .GET()
            .build();

    var response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString());

    return response.body();
}
```

Bên gọi cung cấp `HttpClient` và URI phù hợp. Phương thức này minh họa cách giới hạn thời gian, chưa đặt chính sách xử lý HTTP status cho nghiệp vụ cụ thể.

`HttpRequest.Builder.timeout` có hợp đồng timeout riêng và có thể dẫn đến `HttpTimeoutException`. Xem [timeout của HTTP request](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration)).

Nếu `fetchText` được fork trong scope mặc định:

- Lỗi HTTP timeout xảy ra trước có thể làm tác vụ thất bại; cause của `ExecutionException` sẽ phản ánh lỗi tác vụ.
- Timeout chung của scope được báo bằng marker `CancelledByTimeoutException` như phần 3.
- Việc owner bị interrupt khi chờ là một đường điều khiển riêng.

Không gom cả ba thành một nhãn “request chậm”. Việc phân biệt giúp xác định đúng tầng đang tiêu thụ ngân sách.

Với HTTP, hủy phía client cũng không bảo đảm hệ thống ở xa chưa xử lý yêu cầu. Hợp đồng `HttpClient.send` nêu rõ việc thử hủy trao đổi khi bị interrupt có thể diễn ra sau khi request đã được gửi. Vì vậy, nếu một thao tác làm thay đổi dữ liệu cần thử lại, thiết kế nghiệp vụ phải tính đến khả năng lần trước đã có hiệu lực. Xem [HttpClient.send](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html#send(java.net.http.HttpRequest,java.net.http.HttpResponse.BodyHandler)).

## 9. Phân loại outcome và quyết định xử lý

Bảng sau áp dụng cho scope được mở bằng `open(configOperator)` như ví dụ, dùng chính sách mặc định của JDK 27:

| Tình huống | Dấu hiệu ở điểm phối hợp | Hướng xử lý |
| --- | --- | --- |
| Tất cả tác vụ cần thiết thành công | `join()` hoàn tất bình thường | Đọc kết quả rồi tạo phản hồi |
| Một tác vụ thất bại | `ExecutionException` mang lỗi tác vụ trong cause | Phân loại lỗi nghiệp vụ hoặc lỗi phụ thuộc |
| Scope bị hủy bởi timeout | `ExecutionException` có cause là `CancelledByTimeoutException` | Áp dụng chính sách quá hạn của yêu cầu |
| Owner bị interrupt trước hoặc trong lúc chờ | `InterruptedException` | Cho phép yêu cầu hủy truyền ra, thực hiện cleanup |
| Cleanup còn chạy | Chưa ra khỏi bước đóng scope | Chờ đóng và quan sát nguyên nhân dừng chậm |

Nếu thay bằng một `Joiner` riêng, hãy đọc hợp đồng outcome của joiner đó. JDK 27 cho phép policy và kiểu ngoại lệ khác nhau; một joiner riêng còn có thể tạo kết quả cho trường hợp timeout. Xem [StructuredTaskScope.Joiner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html).

Chính sách fallback cũng cần được quyết định rõ: dữ liệu nào bắt buộc, dữ liệu nào có thể dùng bản cache, và kết quả quá hạn còn giá trị hay không. Đặt quyết định đó ở tầng hiểu yêu cầu nghiệp vụ. Dù đã chọn fallback, bước đóng scope vẫn cần hoàn tất.

Khi timeout và một lỗi phụ thuộc xảy ra gần nhau, hãy xử lý outcome thực tế quan sát được. Không dùng thứ tự các dòng log từ nhiều luồng làm bằng chứng duy nhất cho nguyên nhân.

## 10. Quan sát và thực hành

Để phân biệt thời gian chờ kết quả với thời gian thu hồi công việc, có thể ghi nhận ba mốc:

```text
scope_opened      join_outcome                 scope_closed
     |-----------------|----------------------------|
       pha thực thi        pha đóng và thoát scope
```

Trong ví dụ có `catch` ngay quanh `join()`, mốc `join_outcome` được ghi ở catch bên trong; mốc `scope_closed` được ghi sau câu lệnh `try`-with-resources hoặc ở catch bên ngoài. Dùng `System.nanoTime()` cho chênh lệch trong cùng JVM.

Khi đọc log, cần biết scope thuộc yêu cầu nào, outcome là gì, tác vụ nào đang dừng và thời gian đóng kéo dài bao lâu. Tên `dashboard` trong ví dụ giúp nhận diện phạm vi công việc; mã ứng dụng thực tế có thể gắn thêm định danh yêu cầu trong hệ thống quan sát.

Thử các kịch bản sau với chương trình ở phần 3:

| Thay đổi | Điều cần quan sát |
| --- | --- |
| Giảm thời gian ngủ của cả hai tác vụ xuống dưới ngân sách | Kết quả `Dashboard` được tạo sau `join` thành công |
| Giữ một tác vụ chậm và cleanup ngắn | Marker timeout và thời điểm thoát scope |
| Dùng bản `readStock` có cleanup mô phỏng 400 ms | Khoảng cách giữa `join_outcome` và `scope_closed` |
| Làm một tác vụ ném lỗi trước timeout | Cause là lỗi tác vụ thay vì marker timeout chung |
| Truyền deadline đã qua vào `loadBefore` | Mã ứng dụng từ chối trước khi mở scope |
| Tiêu thụ một phần `RequestBudget` rồi gọi dịch vụ | Ngân sách được cấp là phần còn lại |

Khi viết kiểm thử cho những kịch bản đồng thời, nên dùng cơ chế đồng bộ như latch để điều khiển lúc tác vụ bắt đầu và lúc cleanup được phép kết thúc. Tránh kiểm thử chỉ dựa vào việc tổng thời gian phải bằng chính xác một con số mili giây.

Trước khi áp dụng mẫu vào một yêu cầu thực tế, hãy xác định được: ngân sách bắt đầu ở đâu, ai truyền thời gian còn lại, tác vụ phản hồi interrupt bằng cách nào, và tài nguyên nào cần được đóng trước khi scope có thể kết thúc.
