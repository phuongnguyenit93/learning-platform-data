# Đóng scope và bảo đảm các tác vụ con đã kết thúc

Một StructuredTaskScope không chỉ gom các tác vụ chạy đồng thời vào cùng một nhóm. Nó còn ràng buộc vòng đời của các tác vụ con với tác vụ cha: khi scope đóng, luồng sở hữu scope phải chờ cho đến khi mọi luồng con do scope tạo ra thực sự kết thúc.

Trong JDK 26, API này thuộc JEP 525 – Structured Concurrency (Sixth Preview). Phần quan trọng của bài là phân biệt join() với close(): join() chờ kết quả theo chính sách của scope; close() hủy những tác vụ còn chạy rồi chờ chúng kết thúc hoàn toàn. Dùng try-with-resources để bảo đảm close() được gọi kể cả khi phần xử lý kết quả phát sinh exception.

## 1. Phiên bản API và trạng thái preview

Structured Concurrency trong JDK 26 vẫn là preview API. API chính nằm trong java.util.concurrent.StructuredTaskScope, với các thao tác open(), fork(), join() và close(). Mặc định, mỗi lần fork() tạo một thread mới; cấu hình mặc định sử dụng virtual thread.

Biên dịch và chạy ví dụ bằng JDK 26:

~~~powershell
javac --enable-preview --release 26 -d out src\ScopeCloseDemo.java
java --enable-preview -cp out ScopeCloseDemo
~~~

Phải bật preview ở cả compiler và runtime. Không thể dùng JDK 27 với --release 26 để chạy preview API của JDK 26; compiler và runtime phải cùng release với preview đang kiểm thử.

Tính đến ngày 27/11/2026:

| JDK | JEP | Trạng thái |
|---|---|---|
| JDK 26 | JEP 525 | Structured Concurrency – Sixth Preview |
| JDK 27 | JEP 533 | Structured Concurrency – Seventh Preview |

JDK 27 đã GA, nhưng Structured Concurrency vẫn là preview. Một số kiểu generic và exception của StructuredTaskScope đã thay đổi giữa hai release. Các ví dụ chính trong bài dùng API JDK 26; phần cuối nêu các điểm cần kiểm tra khi nâng cấp.

## 2. Vòng đời của một scope

Một scope được mở bởi một luồng gọi là owner thread. Chỉ owner được phép gọi fork(), join() và close() trên scope đó.

~~~text
Owner thread
    |
    | open()
    v
StructuredTaskScope
    |
    +---- fork(task A) ----> Subtask A
    |
    +---- fork(task B) ----> Subtask B
    |
    | join()
    |   Chờ các tác vụ hoàn tất hoặc scope bị hủy
    v
Xử lý kết quả / exception
    |
    | rời khối try
    v
close()
    |
    +---- Hủy scope nếu chưa hủy
    +---- Interrupt các tác vụ chưa kết thúc
    +---- Chờ tất cả thread con kết thúc
    |
    v
Owner tiếp tục chạy sau khối try
~~~

Cách sử dụng chuẩn:

1. Mở scope bằng StructuredTaskScope.open() trong khối try-with-resources.
2. Gọi fork() để chạy các tác vụ con.
3. Gọi join() để chờ outcome theo chính sách của scope.
4. Đọc kết quả sau khi join() hoàn tất.
5. Khi rời khối try, Java tự gọi close() và chờ các thread con kết thúc.

Mỗi scope chỉ được thao tác bởi owner thread. Không truyền scope cho tác vụ con để tác vụ con tự gọi fork(), join() hoặc close() trên scope cha. Nếu một tác vụ con cần tạo công việc đồng thời của riêng nó, tác vụ đó có thể mở một scope lồng nhau và tự quản lý scope ấy.

## 3. Phân biệt join() và close()

Hai phương thức có vai trò khác nhau:

| Phương thức | Trách nhiệm | Khi nào kết thúc |
|---|---|---|
| join() | Chờ các tác vụ hoàn tất hoặc chờ đến khi scope bị hủy; sau đó trả outcome hoặc ném exception | Có thể kết thúc khi scope đã bị hủy dù một số thread con vẫn đang xử lý việc dừng |
| close() | Hủy scope nếu cần, interrupt các tác vụ chưa hoàn tất và chờ mọi thread con kết thúc | Chỉ trả về sau khi các thread do scope tạo ra đã kết thúc |

join() không phải lệnh dừng thread. Với chính sách mặc định, join() chờ tất cả tác vụ thành công hoặc dừng chờ khi một tác vụ thất bại và scope bị hủy. Với joiner kiểu lấy kết quả đầu tiên thành công, join() có thể trả về ngay khi một tác vụ thành công và các tác vụ còn lại được interrupt.

Sau khi scope bị hủy, isCancelled() có thể trả về true trước khi các thread con thực sự kết thúc. Vì vậy, không dùng isCancelled() để kết luận rằng mọi tài nguyên của tác vụ con đã được giải phóng.

close() thực hiện phần chờ cuối cùng:

- Nếu scope chưa bị hủy, close() hủy scope.
- Việc hủy ngăn các thread con mới bắt đầu và interrupt các tác vụ chưa hoàn tất.
- close() chờ mọi thread do scope tạo ra kết thúc.
- Nếu owner bị interrupt trong lúc close() đang chờ, close() vẫn tiếp tục chờ đến khi các thread con kết thúc rồi đặt lại trạng thái interrupt cho owner.

Đây là bảo đảm quan trọng của structured concurrency: luồng owner không tiếp tục ra khỏi phạm vi scope trong khi thread con của scope vẫn còn chạy.

## 4. Ví dụ thành công: join kết quả rồi đóng scope

Ví dụ sau gọi hai dịch vụ độc lập để lấy hồ sơ và số đơn hàng đang mở. Hai tác vụ chạy đồng thời; owner chờ cả hai bằng join() rồi mới đọc kết quả.

~~~java
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

public class ScopeCloseDemo {

    record Profile(String displayName) {}
    record Dashboard(Profile profile, int openOrders) {}

    static Profile fetchProfile() {
        return new Profile("Duke");
    }

    static Integer fetchOpenOrders() {
        return 3;
    }

    static Dashboard loadDashboard()
            throws InterruptedException,
                   StructuredTaskScope.FailedException {

        try (var scope = StructuredTaskScope.open()) {
            Subtask<Profile> profile =
                    scope.fork(ScopeCloseDemo::fetchProfile);

            Subtask<Integer> orders =
                    scope.fork(ScopeCloseDemo::fetchOpenOrders);

            // Chờ các tác vụ hoàn tất theo chính sách mặc định.
            scope.join();

            // Chỉ đọc kết quả sau khi đã join.
            return new Dashboard(profile.get(), orders.get());
        }
        // close() được gọi tự động trước khi loadDashboard() trả về.
    }

    public static void main(String[] args) throws Exception {
        Dashboard dashboard = loadDashboard();
        System.out.println(dashboard);
    }
}
~~~

Với StructuredTaskScope.open() trong JDK 26, chính sách mặc định là chờ tất cả tác vụ thành công hoặc hủy scope khi có tác vụ thất bại. Nếu tất cả thành công, join() hoàn tất bình thường; Subtask.get() có thể được gọi để lấy kết quả.

Khi khối try kết thúc, close() vẫn được gọi. Trong trường hợp tất cả tác vụ đã hoàn tất, không còn tác vụ nào cần interrupt hoặc chờ. Owner chỉ tiếp tục sau khi quá trình đóng scope hoàn tất.

Không gọi Subtask.get() trước join(). Kết quả của subtask chỉ được owner đọc sau khi đã join và subtask đã hoàn tất thành công. Nếu subtask thất bại hoặc scope bị hủy trước khi có kết quả, không được coi handle đó là một kết quả hợp lệ.

## 5. Khi một tác vụ lỗi, close vẫn chờ tác vụ còn lại

Với chính sách mặc định, khi một subtask thất bại, scope bị hủy và các subtask chưa hoàn tất bị interrupt. join() ném StructuredTaskScope.FailedException, trong đó cause là exception của tác vụ thất bại.

Điểm cần nhớ là join() có thể báo lỗi trước khi tác vụ còn lại hoàn tất quá trình dừng. Sau đó, try-with-resources gọi close(), và close() chờ cho đến khi thread còn lại thực sự kết thúc.

~~~java
import java.io.IOException;
import java.util.concurrent.StructuredTaskScope;

public class ScopeFailureCloseDemo {

    static String fetchProfile() {
        return "profile";
    }

    static String fetchOrders() throws IOException {
        throw new IOException("Order service unavailable");
    }

    static void load() throws InterruptedException {
        try (var scope = StructuredTaskScope.open()) {
            scope.fork(ScopeFailureCloseDemo::fetchProfile);
            scope.fork(ScopeFailureCloseDemo::fetchOrders);

            scope.join();
        } catch (StructuredTaskScope.FailedException failure) {
            Throwable cause = failure.getCause();
            System.err.println("Subtask failed: " + cause);
        }
        // Khi đến catch, close() của scope đã chạy xong.
    }

    public static void main(String[] args) throws Exception {
        load();
    }
}
~~~

Trong ví dụ, fetchOrders() ném IOException. Joiner mặc định hủy scope khi phát hiện lỗi và join() ném FailedException. Khi rời khối try, close() interrupt tác vụ chưa hoàn tất và chờ thread đó kết thúc trước khi chương trình vào catch.

Không bắt FailedException bên trong khối try rồi tiếp tục sử dụng kết quả của các subtask đã bị hủy. Hãy xử lý outcome sau khi scope đóng, hoặc chỉ đọc kết quả những subtask đã hoàn tất thành công sau join() theo chính sách đã chọn.

## 6. Hủy một tác vụ không có nghĩa thread đã kết thúc

Hủy scope gửi tín hiệu interrupt đến thread đang chạy subtask. Java không cưỡng bức dừng thread ngay lập tức. Tác vụ con phải hợp tác với cơ chế interrupt và kết thúc sớm khi nhận yêu cầu hủy.

Một tác vụ thực hiện vòng lặp CPU dài nên kiểm tra trạng thái interrupt định kỳ:

~~~java
static long calculate() throws InterruptedException {
    long result = 0;

    for (int i = 0; i < 1_000_000_000; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Subtask cancelled");
        }

        result += i;
    }

    return result;
}
~~~

Với API blocking có thể ném InterruptedException, hãy kết thúc tác vụ khi nhận interruption. Nếu cần chuyển exception lên tầng gọi, hãy để exception được truyền tiếp. Nếu bắt exception nhưng không thể truyền tiếp, khôi phục trạng thái interrupt bằng Thread.currentThread().interrupt() rồi thoát khỏi tác vụ.

~~~java
static String readRemoteData() throws InterruptedException {
    try {
        return interruptibleRemoteRead();
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw exception;
    }
}
~~~

Không viết mã bỏ qua interruption:

~~~java
// Không nên: tác vụ tiếp tục chạy sau khi scope yêu cầu hủy.
try {
    blockingOperation();
} catch (InterruptedException ignored) {
    // Tiếp tục xử lý như chưa có yêu cầu hủy.
}
~~~

Nếu subtask bỏ qua interrupt, mắc kẹt trong thao tác không thể interrupt hoặc chờ một tài nguyên không bao giờ được giải phóng, close() có thể chờ vô thời hạn. StructuredTaskScope bảo đảm owner không rời scope khi thread con còn chạy; nó không cung cấp cơ chế cưỡng bức kết thúc thread.

Vì vậy, các tác vụ con cần:

- Sử dụng thao tác blocking có khả năng phản hồi interruption khi phù hợp.
- Kiểm tra interrupt trong vòng lặp tính toán dài.
- Đóng file, stream, socket và tài nguyên riêng trong finally hoặc try-with-resources.
- Không nuốt InterruptedException rồi tiếp tục công việc.
- Đặt timeout cho I/O hoặc phụ thuộc bên ngoài khi API hỗ trợ.

## 7. Khi owner bị interrupt trong lúc join

join() ném InterruptedException nếu owner bị interrupt trước hoặc trong lúc chờ. Khi exception này được ném, trạng thái interrupt của owner bị xóa theo quy tắc của Java.

Nếu join() nằm trong khối try-with-resources, luồng điều khiển rời khối và close() vẫn được gọi. close() hủy scope nếu chưa bị hủy, interrupt các tác vụ chưa kết thúc và chờ chúng dừng. Nếu owner lại bị interrupt trong lúc close() chờ, close() tiếp tục đợi và đặt lại trạng thái interrupt trước khi trả về.

Ví dụ xử lý interruption ở tầng gọi:

~~~java
static void runConcurrentWork() {
    try (var scope = StructuredTaskScope.open()) {
        scope.fork(() -> performTaskA());
        scope.fork(() -> performTaskB());

        scope.join();

    } catch (InterruptedException exception) {
        // close() đã được gọi trước khi vào catch.
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
                "Tác vụ đồng thời bị interrupt", exception);

    } catch (StructuredTaskScope.FailedException exception) {
        throw new IllegalStateException(
                "Một tác vụ con thất bại", exception.getCause());
    }
}
~~~

Đoạn code giữ lại trạng thái interrupt sau khi xử lý exception ở tầng ứng dụng. Nếu phương thức hiện tại có thể khai báo throws InterruptedException, thường nên truyền exception lên thay vì chuyển thành unchecked exception. Quyết định phụ thuộc hợp đồng của API đang viết.

Không dùng Thread.interrupted() để kiểm tra trạng thái nếu không muốn xóa cờ interrupt. Trong tác vụ cần kiểm tra định kỳ mà vẫn giữ trạng thái, dùng Thread.currentThread().isInterrupted().

## 8. Đóng scope khi chưa gọi join

Sau khi đã gọi fork(), owner phải gọi join() để lấy outcome trước khi đóng scope. Nếu owner rời khối try mà chưa từng gọi join(), close() vẫn hủy scope và chờ các thread con kết thúc, sau đó ném IllegalStateException.

Ví dụ sai:

~~~java
try (var scope = StructuredTaskScope.open()) {
    scope.fork(() -> performTask());

    // Sai: rời scope sau fork mà không gọi join().
}
~~~

Không dựa vào việc task có thể đã hoàn tất rất nhanh để bỏ join(). Quy tắc này là một phần của hợp đồng API: owner cần thực hiện bước lấy outcome sau khi fork. Nếu phần xử lý trước join phát sinh exception, try-with-resources vẫn đóng scope; exception từ close() do thiếu join có thể được ghi nhận là suppressed exception nếu đã có exception chính từ phần thân try.

Các quy tắc vòng đời cần tuân thủ:

| Quy tắc | Ý nghĩa |
|---|---|
| fork() trước join() | Không fork thêm sau khi owner đã join |
| join() sau khi fork | Cần gọi để lấy outcome của các subtask |
| close() bởi owner | Thread khác không được đóng scope thay owner |
| Đóng theo thứ tự lồng nhau | Scope trong phải đóng trước scope ngoài |
| try-with-resources | Đảm bảo close được gọi khi block kết thúc bình thường hoặc do exception |

Nếu scope được lồng trong một scope khác, hãy dùng try-with-resources ở đúng cấp. Scope trong phải đóng trước scope ngoài. Đóng scope ngoài khi scope lồng bên trong vẫn còn mở có thể gây StructureViolationException sau khi cấu trúc được đóng.

## 9. Dùng timeout nhưng vẫn phải chờ thread con kết thúc

JDK 26 cho phép cấu hình timeout khi mở scope. Timeout bắt đầu tính từ lúc scope được mở. Nếu hết hạn trước hoặc trong lúc join(), scope bị hủy và các tác vụ chưa hoàn tất bị interrupt.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

static List<String> fetchBoth() throws Exception {
    Duration timeout = Duration.ofSeconds(3);

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow(),
            config -> config.withTimeout(timeout))) {

        scope.fork(() -> fetchFromPrimary());
        scope.fork(() -> fetchFromReplica());

        return scope.join();
    }
}
~~~

Với joiner allSuccessfulOrThrow(), join() trả danh sách kết quả khi tất cả subtask thành công. Nếu có lỗi hoặc timeout theo chính sách joiner, join() ném exception tương ứng. Khi khối try kết thúc, close() vẫn chờ các thread bị interrupt kết thúc.

Timeout không phải lệnh kill thread tại đúng thời điểm hết hạn. Nó kích hoạt hủy scope và gửi interrupt. Nếu tác vụ không phản hồi interruption, close() vẫn phải đợi và có thể kéo dài vượt quá timeout cấu hình. Muốn giới hạn thời gian kết thúc thực tế, các thao tác I/O và vòng lặp bên trong tác vụ cũng phải có cơ chế timeout hoặc cancellation phù hợp.

## 10. Kiểm thử rằng close thật sự chờ tác vụ con

Có thể kiểm chứng bằng một joiner trả về khi có tác vụ đầu tiên thành công. Tác vụ còn lại bị hủy nhưng cần một khoảng thời gian để chạy finally và kết thúc. Sau khi khối try đóng scope, owner xác nhận phần cleanup đã chạy.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.atomic.AtomicBoolean;

public class ScopeCloseWaitCheck {

    public static void main(String[] args) throws Exception {
        CountDownLatch slowStarted = new CountDownLatch(1);
        AtomicBoolean slowExited = new AtomicBoolean();

        try (var scope = StructuredTaskScope.open(
                StructuredTaskScope.Joiner.<String>anySuccessfulOrThrow())) {

            scope.fork(() -> {
                slowStarted.await();
                return "fast";
            });

            scope.fork(() -> {
                slowStarted.countDown();

                try {
                    // Chờ vô hạn cho đến khi scope interrupt tác vụ này.
                    new CountDownLatch(1).await();
                    return "slow";
                } finally {
                    slowExited.set(true);
                }
            });

            String result = scope.join();

            if (!"fast".equals(result)) {
                throw new AssertionError("Unexpected result: " + result);
            }

            // join() có thể trả về sau khi tác vụ chậm bị interrupt,
            // nhưng trước khi thread đó hoàn tất cleanup.
        }

        // Dòng này chỉ chạy sau khi close() đã chờ thread con kết thúc.
        if (!slowExited.get()) {
            throw new AssertionError("Subtask cleanup did not finish");
        }

        System.out.println("PASS: close waited for child termination");
    }
}
~~~

slowStarted bảo đảm tác vụ chậm đã bắt đầu trước khi tác vụ nhanh trả về. Khi anySuccessfulOrThrow() nhận kết quả thành công, scope hủy tác vụ còn lại. Tác vụ chậm nhận interruption, thoát khỏi await() và chạy finally.

join() có thể trả về trước khi thread chậm kết thúc. close() trong try-with-resources chờ thread đó kết thúc. Vì vậy, sau khi chương trình ra khỏi khối try, slowExited phải là true.

Phép thử này xác nhận điều kiện hoàn tất của close() bằng trạng thái cleanup của tác vụ. Không kiểm tra tên thread, monitor, stack trace hoặc các field nội bộ của JDK; đó không phải hợp đồng công khai của StructuredTaskScope.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| close() ném IllegalStateException | Owner đã fork nhưng không gọi join() | Gọi join() sau giai đoạn fork để lấy outcome |
| Owner vẫn chờ sau khi scope bị hủy | Tác vụ con chưa kết thúc hoặc bỏ qua interrupt | Sửa tác vụ để phản hồi interrupt và giải phóng tài nguyên |
| join() trả về nhưng một thread con vẫn đang cleanup | Joiner đã hủy scope và trả outcome trước khi thread bị interrupt kết thúc | Để try-with-resources gọi close(); không rời phạm vi tài nguyên trước close |
| Subtask.get() ném IllegalStateException | Đọc kết quả trước join hoặc subtask không thành công | Chỉ đọc sau join và xác nhận subtask hoàn tất thành công theo chính sách |
| fork() bị lỗi sau join | Đang cố thêm tác vụ sau giai đoạn join | Fork toàn bộ công việc cần thiết trước join |
| close() chờ rất lâu sau timeout | Timeout chỉ gửi cancellation; tác vụ không phản hồi interruption | Đặt timeout cho I/O, kiểm tra interrupt và đóng tài nguyên trong finally |
| join() ném InterruptedException | Owner bị interrupt trong lúc chờ | Để try-with-resources đóng scope; truyền hoặc khôi phục trạng thái interrupt ở tầng gọi |
| WrongThreadException | Thread khác owner gọi fork, join hoặc close | Chỉ owner quản lý vòng đời scope |
| StructureViolationException | Đóng scope sai thứ tự với scope lồng hoặc scoped value binding | Đóng scope theo cấu trúc lồng nhau và đúng thứ tự |

## 12. Khác biệt khi nâng cấp lên JDK 27

JDK 27 tiếp tục Structured Concurrency ở JEP 533 – Seventh Preview. Quy tắc cốt lõi của close() vẫn là hủy scope nếu cần, interrupt các subtask chưa hoàn tất và chờ tất cả thread con kết thúc. Quy tắc owner phải gọi join() sau khi fork cũng vẫn được giữ.

Tuy nhiên, API và kiểu exception của join() đã thay đổi:

| Nội dung | JDK 26 – JEP 525 | JDK 27 – JEP 533 |
|---|---|---|
| Trạng thái | Sixth Preview | Seventh Preview |
| Kiểu scope | StructuredTaskScope<T, R> | StructuredTaskScope<T, R, R_X extends Throwable> |
| Default failure | StructuredTaskScope.FailedException | ExecutionException |
| Cause của lỗi subtask | Exception của subtask thất bại | Exception của subtask thất bại |
| Timeout | StructuredTaskScope.TimeoutException theo Joiner | CancelledByTimeoutException làm cause của outcome timeout |
| Mở scope với timeout | open(joiner, configOperator) | Có thêm open(configOperator) cho chính sách mặc định |
| Đóng scope | Cancel, interrupt tác vụ chưa xong, chờ mọi thread kết thúc | Giữ nguyên bảo đảm đóng và chờ |

Không chép nguyên phần xử lý exception của JDK 26 sang JDK 27. Khi nâng cấp, hãy dùng JDK 27 compiler/runtime, bật preview của JDK 27 và kiểm tra kiểu exception mới trong StructuredTaskScope cùng Joiner tương ứng.

Các ví dụ cũ từ những preview trước có thể dùng các lớp chính sách riêng như ShutdownOnFailure hoặc ShutdownOnSuccess. API JDK 26 dùng Joiner để biểu diễn chính sách. Hãy theo Javadoc của đúng release thay vì trộn các ví dụ từ nhiều preview.

## 13. Bài thực hành

Thực hiện trên JDK 26 với preview và ghi lại kết quả:

1. Mở một scope, fork hai tác vụ trả về hai kiểu dữ liệu khác nhau, gọi join() và lấy kết quả bằng Subtask.get().
2. Đặt một tác vụ ném exception. Xác nhận joiner mặc định hủy scope, join() ném FailedException và cause là exception gốc.
3. Tạo một tác vụ còn lại chờ thao tác interruptible. Xác nhận close() gửi interrupt và chờ tác vụ chạy xong finally.
4. Dùng Joiner.anySuccessfulOrThrow() để một tác vụ thành công sớm. Quan sát join() trả kết quả trước khi tác vụ bị hủy hoàn tất cleanup; xác nhận sau khối try thì cleanup đã xong.
5. Thử rời khối try sau fork() nhưng không gọi join(). Xác nhận close() vẫn dừng và chờ tác vụ, sau đó báo IllegalStateException.
6. Interrupt owner trong lúc join(). Kiểm tra close() vẫn chờ các thread con kết thúc và xử lý trạng thái interrupt ở tầng gọi.
7. Cấu hình timeout bằng withTimeout(). Xác nhận timeout kích hoạt hủy scope, nhưng close() vẫn chờ tác vụ con phản hồi interruption.
8. Tạo một scope lồng bên trong tác vụ con. Đảm bảo scope trong đóng trước khi tác vụ con kết thúc và scope ngoài đóng sau.
9. Chạy lại các phép thử trên JDK 27 với JEP 533, cập nhật phần xử lý ExecutionException và kiểu exception timeout.

**Tiêu chí hoàn thành:** giải thích được sự khác nhau giữa join() và close(); biết vì sao close() là ranh giới bảo đảm thread con đã kết thúc; dùng try-with-resources và gọi join đúng thứ tự; xử lý failure, timeout và interruption; viết subtask hợp tác với cancellation; kiểm thử được cleanup trước khi owner tiếp tục; nhận diện khác biệt API giữa JDK 26 và JDK 27.

## 14. Tài liệu tham khảo chính thức

- [JEP 525: Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525) — trạng thái và mục tiêu của Structured Concurrency trong JDK 26.
- [Java 26 StructuredTaskScope API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) — open(), fork(), join(), close(), cancellation, timeout và quy tắc owner thread.
- [Java 26 Structured Concurrency Guide](https://docs.oracle.com/en/java/javase/26/core/structured-concurrency.html) — trình tự mở scope, fork, join và close.
- [Java 26 Preview API List](https://docs.oracle.com/en/java/javase/26/docs/api/preview-list.html) — xác nhận StructuredTaskScope và các kiểu liên quan là preview API.
- [JEP 533: Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533) — thay đổi trong JDK 27.
- [Java 27 StructuredTaskScope API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) — API, exception và bảo đảm close của JDK 27.
- [Java 27 Structured Concurrency Guide](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html) — cách dùng API trong JDK 27.

Javadoc của đúng JDK là nguồn chuẩn để xác định exception, quy tắc đóng scope và bảo đảm về thread. Structured Concurrency vẫn là preview trong JDK 26 và JDK 27; cần kiểm tra lại API trước mỗi lần nâng cấp.

