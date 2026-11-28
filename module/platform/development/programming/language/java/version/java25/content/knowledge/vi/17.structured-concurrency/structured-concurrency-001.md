# Phạm vi và trạng thái preview lần thứ năm của Structured Concurrency trong JDK 25

## 1. Mục tiêu và bối cảnh

Một request trong ứng dụng server thường cần gọi nhiều dịch vụ hoặc đọc nhiều nguồn dữ liệu cùng lúc. Nếu mỗi tác vụ được khởi chạy độc lập bằng thread, executor hoặc future, code phải tự quản lý thời điểm chờ, hủy tác vụ còn lại, truyền lỗi và bảo đảm không còn tác vụ chạy sau khi request cha đã kết thúc. Khi một nhánh lỗi, các nhánh khác có thể vẫn tiếp tục làm việc dù kết quả của chúng không còn được sử dụng.

**Structured Concurrency** tổ chức các tác vụ đồng thời thành một cây có quan hệ cha–con và vòng đời rõ ràng. Một tác vụ cha mở một **scope**, khởi chạy các **subtask**, đợi kết quả theo một chính sách, xử lý outcome rồi đóng scope. Scope không hoàn tất cho tới khi các thread con đã kết thúc. Cách tổ chức này giúp cancellation, lỗi và quan sát thread có cùng ranh giới với đơn vị công việc nghiệp vụ.

Trong **Java 25**, Structured Concurrency được đề xuất qua **JEP 505 – Structured Concurrency (Fifth Preview)**. API nằm trong **java.util.concurrent** dưới tên **StructuredTaskScope**. Đây là **preview API**, không phải API Java SE ổn định trong JDK 25.

Bài **Phạm vi và trạng thái preview lần thứ năm của Structured Concurrency trong JDK 25**, thuộc chương **Structured Concurrency** của lộ trình **JAVA_VERSION_JAVA25**, tập trung vào:

1. Mô hình task/subtask, scope, fork, join và close.
2. Phạm vi thay đổi của JEP 505 so với preview lần thứ tư trong JDK 24.
3. Chính sách hoàn thành và hủy tác vụ thông qua Joiner.
4. Cấu hình timeout, thread factory và tên scope.
5. Quy tắc xử lý lỗi, interruption và giới hạn của cancellation.
6. Tương tác với virtual threads và ScopedValue.
7. Cách biên dịch/chạy preview đúng JDK 25 và trạng thái API trong các JDK mới hơn.

**Lưu ý về phạm vi:** các ví dụ mã trong bài được viết đúng theo API **JDK 25, JEP 505** để người học hiểu lần preview thứ năm. Đây là ví dụ theo phiên bản, không phải khuyến nghị đưa preview API vào hệ thống production cần tương thích lâu dài. Tình trạng hiện hành của tính năng được cập nhật ở mục 4.

## 2. Structured Concurrency giải quyết vấn đề gì?

Giả sử một endpoint cần lấy thông tin hồ sơ, đơn hàng gần đây và điểm thành viên. Ba nguồn dữ liệu độc lập nên có thể được gọi đồng thời:

~~~text
HTTP request
    |
    +-- load profile
    |
    +-- load recent orders
    |
    +-- load loyalty points
    |
    +-- combine results
~~~

Nếu dùng các tác vụ không có quan hệ vòng đời, code cha phải tự ghi nhớ mọi handle, chờ từng future, hủy những future còn lại khi có lỗi và xử lý tình huống request bị timeout. Một nhánh có thể tiếp tục chạy sau khi request đã trả lỗi.

Structured Concurrency xem ba lời gọi trên là **một đơn vị công việc**:

~~~mermaid
flowchart TD
    A["Request task"] --> B["StructuredTaskScope"]
    B --> C["Subtask: profile"]
    B --> D["Subtask: orders"]
    B --> E["Subtask: loyalty"]
    C --> F["Joiner decides outcome"]
    D --> F
    E --> F
    F --> G["Return result or propagate failure"]
    G --> H["Close scope; all child threads finish"]
~~~

Mục tiêu chính:

- **Vòng đời có cấu trúc:** subtask được tạo trong scope và phải kết thúc trước khi luồng điều khiển rời scope.
- **Cancellation có quan hệ:** khi chính sách yêu cầu hủy, scope ngăn fork thêm và interrupt các subtask chưa hoàn tất.
- **Xử lý lỗi tập trung:** outcome của nhóm subtask được xử lý tại join().
- **Quan sát tốt hơn:** quan hệ cha–con giữa các tác vụ có thể được thể hiện trong thread dump.
- **Tích hợp virtual threads:** scope mặc định tạo một virtual thread cho mỗi subtask được fork.

Structured Concurrency không thay thế mọi executor, queue hoặc cơ chế xử lý message. Nó phù hợp khi một tác vụ có thể chia thành các công việc con có quan hệ vòng đời và phải hoàn tất trước khi tác vụ cha tiếp tục.

## 3. Mô hình scope: open → fork → join → process → close

API JDK 25 sử dụng StructuredTaskScope trong try-with-resources:

~~~java
try (var scope = StructuredTaskScope.open()) {
    var first = scope.fork(() -> fetchFirst());
    var second = scope.fork(() -> fetchSecond());

    scope.join();

    return combine(first.get(), second.get());
}
~~~

| Bước | API | Ý nghĩa |
| --- | --- | --- |
| Mở scope | StructuredTaskScope.open(...) | Tạo scope do thread hiện tại sở hữu. |
| Tạo subtask | scope.fork(Callable) hoặc scope.fork(Runnable) | Khởi chạy một thread mới trong scope, mặc định là virtual thread. |
| Chờ outcome | scope.join() | Đợi theo chính sách của Joiner đã chọn. |
| Đọc kết quả | subtask.get() hoặc kết quả do Joiner trả về | Chỉ đọc sau khi join() hoàn tất và subtask đã thành công. |
| Đóng scope | close() do try-with-resources gọi | Hủy scope nếu cần và đợi mọi thread con kết thúc. |

**Owner thread** là thread đã mở scope. Chỉ owner được gọi fork, join và close. Không chuyển scope sang thread khác để thread đó fork hoặc join thay owner.

Các quy tắc quan trọng:

- Phải gọi join() sau khi đã fork các subtask và trước khi scope đóng. Nếu owner fork subtask rồi đóng scope mà chưa join, close() báo lỗi sau khi đóng scope.
- Chỉ gọi join() một lần.
- Không gọi fork() sau khi đã gọi join().
- Chỉ lấy kết quả Subtask.get() sau khi join() đã hoàn tất và subtask thành công.
- Scope đóng sẽ chờ các thread con kết thúc; việc rời block không làm các thread con tự chạy độc lập bên ngoài scope.

Trong JDK 25, StructuredTaskScope là một **sealed interface** và được tạo qua static factory open(...), không tạo bằng constructor công khai.

## 4. Trạng thái preview: JDK 25 và các phiên bản tiếp theo

Structured Concurrency đã trải qua nhiều vòng thiết kế và preview. Cần phân biệt **trạng thái của API trong JDK 25** với trạng thái mới nhất của tính năng trong các bản JDK sau.

| JDK | JEP | Trạng thái | Điểm cần nhớ |
| --- | --- | --- | --- |
| JDK 19 | JEP 428 | Incubator lần đầu | API thử nghiệm trong module incubator. |
| JDK 20 | JEP 437 | Incubator lần hai | Tiếp tục phát triển trước khi đưa vào preview. |
| JDK 21 | JEP 453 | Preview lần đầu | API xuất hiện trong java.util.concurrent. |
| JDK 22 | JEP 462 | Preview lần hai | Tiếp tục lấy phản hồi. |
| JDK 23 | JEP 480 | Preview lần ba | Tiếp tục lấy phản hồi. |
| JDK 24 | JEP 499 | Preview lần bốn | Phiên bản ngay trước API JDK 25. |
| **JDK 25** | **JEP 505** | **Preview lần năm** | open(...) factory và Joiner thay đổi cấu trúc API. |
| JDK 26 | JEP 525 | Preview lần sáu | Tiếp tục điều chỉnh tên/kiểu kết quả Joiner và cấu hình. |
| JDK 27 | JEP 533 | Preview lần bảy | Bổ sung kiểu ngoại lệ cho join() và thay đổi API liên quan. |
| JDK 28 | JEP 543 | API final đã được tích hợp vào Early Access, không thay đổi chữ ký so với preview lần bảy | Không còn preview marker trong JDK 28 EA; JDK 28 chưa GA tại ngày 27/11/2026. |

### Tình trạng hiện hành tính đến ngày 27/11/2026

- **JDK 25:** Structured Concurrency vẫn là preview lần thứ năm. Phải bật preview ở cả bước biên dịch và chạy.
- **JDK 26:** tính năng vẫn ở preview lần thứ sáu.
- **JDK 27:** bản GA đã phát hành với preview lần thứ bảy; vẫn cần --enable-preview.
- **JDK 28 Early Access:** JEP 543 đã được tích hợp để hoàn thiện API sau bảy vòng preview. Tài liệu Early Access không còn đánh dấu StructuredTaskScope là preview. JDK 28 chưa phải bản GA tại thời điểm của bài.

Do đó, **JEP 505 là một mốc lịch sử/API quan trọng của Java 25**, còn Structured Concurrency vẫn là hướng phát triển hiện hành. Khi chọn JDK cho một ứng dụng, phải dùng API đúng phiên bản JDK đang chạy; không lấy mã preview Java 25 rồi mặc định nó tương thích nguyên trạng với Java 26/27.

## 5. JEP 505 đã thay đổi gì so với JDK 24?

Thay đổi lớn của preview lần thứ năm là cách tạo scope và cách chọn chính sách xử lý subtask.

| Trước JDK 25 | API JDK 25 – JEP 505 |
| --- | --- |
| Tạo scope bằng constructor. | Tạo scope qua StructuredTaskScope.open(...). |
| Chọn chính sách qua các lớp con như ShutdownOnFailure và ShutdownOnSuccess. | Chọn chính sách qua StructuredTaskScope.Joiner. |
| Kết quả và lỗi được truy vấn qua các API riêng của lớp con. | join() trả outcome do Joiner tạo hoặc ném FailedException nếu Joiner báo lỗi. |
| Timeout gắn với thao tác join theo API cũ. | Timeout được cấu hình ở scope khi gọi open(...). |
| Cấu hình được truyền qua constructor. | Dùng function cấu hình áp dụng lên Configuration mặc định. |

Mục đích của thay đổi là tách **cơ chế quản lý scope** khỏi **chính sách tổng hợp kết quả**. StructuredTaskScope quản lý vòng đời và thực thi subtask; Joiner quyết định khi nào scope đạt outcome và kết quả của join() có kiểu gì.

### Không dùng mẫu API từ các preview cũ

Khi viết code theo JDK 25, không sao chép ví dụ cũ sử dụng constructor hoặc các lớp con ShutdownOnFailure/ShutdownOnSuccess, API throwIfFailed(), hay joinUntil() theo thiết kế preview cũ. Những dạng này thuộc các phiên bản preview trước và không phải cách dùng JEP 505 trong JDK 25. Dùng open(...), Joiner, join() và cấu hình timeout theo scope.

## 6. Chính sách mặc định của open()

StructuredTaskScope.open() mở scope với chính sách mặc định:

- Chờ tất cả subtask hoàn thành thành công.
- Nếu một subtask thất bại, scope bị hủy và các subtask chưa hoàn tất bị interrupt.
- join() trả null nếu tất cả thành công.
- Nếu một subtask thất bại, join() ném StructuredTaskScope.FailedException; exception gốc là cause.

Ví dụ:

~~~java
import java.util.concurrent.StructuredTaskScope;

public class CustomerDashboardService {

    record Dashboard(String profile, String orders) {}

    static Dashboard loadDashboard(String customerId)
            throws InterruptedException {

        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(() -> loadProfile(customerId));
            var orders = scope.fork(() -> loadRecentOrders(customerId));

            // Chờ cả hai nhánh thành công; lỗi ở một nhánh sẽ hủy nhánh còn lại.
            scope.join();

            return new Dashboard(profile.get(), orders.get());
        } catch (StructuredTaskScope.FailedException e) {
            throw new IllegalStateException(
                    "Không thể tải đầy đủ dữ liệu dashboard", e.getCause());
        }
    }

    static String loadProfile(String customerId) throws InterruptedException {
        return "profile:" + customerId;
    }

    static String loadRecentOrders(String customerId) throws InterruptedException {
        return "orders:" + customerId;
    }
}
~~~

Hai lời gọi độc lập chạy đồng thời. Thread owner chỉ kết hợp dữ liệu sau khi join() hoàn tất. Nếu một nhánh lỗi, nhánh còn lại được yêu cầu dừng bằng interrupt.

FailedException là exception của scope, còn exception gốc nằm trong getCause(). Có thể phân loại cause để ánh xạ sang lỗi nghiệp vụ phù hợp, nhưng không nên bỏ mất nguyên nhân gốc khi ghi log hoặc chuyển lỗi lên tầng trên.

## 7. Joiner: chọn chính sách hoàn thành cho nhóm subtask

StructuredTaskScope.Joiner<T,R> là thành phần xác định outcome của join(). JDK 25 cung cấp các Joiner thường dùng:

| Joiner JDK 25 | Khi nào join() hoàn tất? | Kết quả |
| --- | --- | --- |
| allSuccessfulOrThrow() | Tất cả thành công; hủy scope nếu có một nhánh thất bại. | Stream<Subtask<T>> theo thứ tự fork. |
| anySuccessfulResultOrThrow() | Khi có một subtask thành công; hủy các nhánh còn lại. | Kết quả của subtask thành công đầu tiên. |
| awaitAllSuccessfulOrThrow() | Tất cả thành công; hủy scope nếu có một nhánh thất bại. | null. |
| awaitAll() | Tất cả subtask kết thúc, kể cả khi có lỗi. | null; không tự hủy scope chỉ vì một subtask lỗi. |

### 7.1. allSuccessfulOrThrow()

Dùng khi tất cả nhánh phải thành công và trả về cùng một kiểu dữ liệu:

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

static List<String> searchAll(List<String> terms)
        throws InterruptedException {

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow())) {

        for (String term : terms) {
            scope.fork(() -> searchIndex(term));
        }

        return scope.join()
                .map(StructuredTaskScope.Subtask::get)
                .toList();
    }
}

static String searchIndex(String term) {
    return "result:" + term;
}
~~~

Kết quả của join() là stream các Subtask thành công theo thứ tự chúng được fork. Có thể lấy kết quả bằng Subtask.get() sau khi join. Nếu một nhánh thất bại, Joiner hủy scope và join() ném FailedException.

### 7.2. anySuccessfulResultOrThrow()

Dùng khi có nhiều nguồn dự phòng và chỉ cần kết quả thành công đầu tiên:

~~~java
import java.util.concurrent.StructuredTaskScope;

static String fetchFromAnyReplica()
        throws InterruptedException {

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>anySuccessfulResultOrThrow())) {

        scope.fork(() -> fetchPrimary());
        scope.fork(() -> fetchReplicaA());
        scope.fork(() -> fetchReplicaB());

        // Trả kết quả của nhánh đầu tiên thành công.
        // Các nhánh còn lại được hủy khi không còn cần thiết.
        return scope.join();
    }
}

static String fetchPrimary() { return "primary"; }
static String fetchReplicaA() { return "replica-a"; }
static String fetchReplicaB() { return "replica-b"; }
~~~

Nếu tất cả nhánh đều thất bại, join() ném FailedException. Chính sách này phù hợp với các nguồn dự phòng độc lập; không dùng nó khi kết quả phải được tổng hợp từ tất cả nguồn.

### 7.3. awaitAllSuccessfulOrThrow()

Dùng khi các subtask trả về kiểu khác nhau và owner cần đọc từng handle sau khi join:

~~~java
try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow())) {

    var profile = scope.fork(() -> loadProfile(customerId));
    var balance = scope.fork(() -> loadBalance(customerId));
    var permissions = scope.fork(() -> loadPermissions(customerId));

    scope.join();

    return new CustomerView(
            profile.get(),
            balance.get(),
            permissions.get());
}
~~~

Joiner chờ tất cả nhánh thành công và trả null. Nếu có nhánh thất bại, scope bị hủy và join() ném FailedException.

### 7.4. awaitAll()

awaitAll() chờ mọi subtask kết thúc nhưng không tự hủy scope khi một subtask lỗi. Joiner trả null; nếu cần kiểm tra kết quả riêng lẻ, dùng Subtask.state() và Subtask.exception() sau khi join.

Chính sách này phù hợp khi các nhánh có side effect độc lập và ứng dụng muốn thu thập trạng thái tất cả nhánh. Cần xử lý lỗi từng nhánh rõ ràng vì việc một nhánh thất bại không tự làm join() thất bại theo chính sách này.

## 8. Tự định nghĩa Joiner khi chính sách mặc định chưa đủ

Joiner cho phép triển khai chính sách hoàn thành riêng. Trong JDK 25, các callback chính gồm:

- onFork(Subtask) được gọi khi một subtask được fork.
- onComplete(Subtask) được gọi khi subtask hoàn thành thành công hoặc thất bại.
- result() tạo kết quả cuối hoặc ném exception cho join().

onFork và onComplete có thể trả true để yêu cầu hủy scope. Đặc biệt, onComplete có thể được gọi đồng thời bởi nhiều thread; implementation Joiner phải thread-safe.

Ví dụ rút gọn: thu thập các Subtask thành công trong callback, sau đó đọc kết quả ở result() khi joiner được gọi bởi owner:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.StructuredTaskScope;

final class CollectSuccessful<T>
        implements StructuredTaskScope.Joiner<T, List<T>> {

    private final Queue<StructuredTaskScope.Subtask<? extends T>> completed =
            new ConcurrentLinkedQueue<>();

    @Override
    public boolean onComplete(
            StructuredTaskScope.Subtask<? extends T> subtask) {
        if (subtask.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
            completed.add(subtask);
        }
        return false;
    }

    @Override
    public List<T> result() {
        List<T> values = new ArrayList<>();
        for (var subtask : completed) {
            values.add(subtask.get());
        }
        return List.copyOf(values);
    }
}
~~~

Sử dụng:

~~~java
try (var scope = StructuredTaskScope.open(new CollectSuccessful<String>())) {
    scope.fork(() -> queryA());
    scope.fork(() -> queryB());
    scope.fork(() -> queryC());

    return scope.join();
}
~~~

Trong ví dụ, callback onComplete chỉ lưu handle vào concurrent queue. result() được gọi khi owner đang thực hiện join và đọc kết quả sau khi các subtask đã hoàn tất. Không gọi Subtask.get() từ callback onComplete đang chạy trên thread con; API quy định owner chỉ đọc kết quả sau khi join.

Đây là ví dụ về cơ chế Joiner, không phải nơi để đặt toàn bộ nghiệp vụ. Joiner nên tập trung vào chính sách hoàn thành, thu thập kết quả và quyết định cancellation; xử lý nghiệp vụ nên nằm ở code gọi join().

## 9. Cấu hình timeout, thread factory và tên scope

JDK 25 cung cấp StructuredTaskScope.Configuration. Khi gọi open(Joiner, configFunction), function nhận cấu hình mặc định và trả về cấu hình mới. Có thể thiết lập:

- **ThreadFactory:** tạo thread thực thi subtask; mặc định là virtual thread không có tên.
- **Timeout:** giới hạn thời gian của toàn scope; timeout bắt đầu khi scope được mở.
- **Name:** tên scope phục vụ giám sát và quản lý.

Ví dụ timeout 2 giây:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

static List<String> fetchWithTimeout() throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow(),
            config -> config.withTimeout(Duration.ofSeconds(2)))) {

        scope.fork(() -> fetchPrimary());
        scope.fork(() -> fetchSecondary());

        return scope.join()
                .map(StructuredTaskScope.Subtask::get)
                .toList();
    } catch (StructuredTaskScope.TimeoutException e) {
        throw new IllegalStateException("Các subtask vượt quá deadline", e);
    }
}
~~~

Khi timeout hết hạn trước hoặc trong lúc join() chờ, scope bị hủy; các subtask chưa hoàn tất bị interrupt và join() ném StructuredTaskScope.TimeoutException trong API JDK 25. close() vẫn đợi các thread con kết thúc.

Timeout của scope là một deadline chung cho nhóm tác vụ, không phải timeout riêng cho từng fork. Nếu từng dịch vụ bên ngoài có timeout riêng, hãy cấu hình timeout của HTTP/database client tương ứng để cancellation có thể kết thúc nhanh.

### Đặt tên virtual thread cho mục đích quan sát

~~~java
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.StructuredTaskScope;

ThreadFactory factory = Thread.ofVirtual()
        .name("customer-load-", 0)
        .factory();

try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow(),
        config -> config.withThreadFactory(factory))) {

    scope.fork(() -> loadProfile(customerId));
    scope.fork(() -> loadOrders(customerId));
    scope.join();
}
~~~

Đặt tên có ích khi đọc thread dump hoặc log chẩn đoán. Không cần tạo thread factory riêng nếu tên thread không có giá trị cho hệ thống; mặc định của scope đã tạo virtual thread.

## 10. Cancellation và khả năng phản hồi interrupt

Khi Joiner hủy scope, JVM gửi interrupt tới thread đang chạy các subtask chưa hoàn tất. **Interrupt là tín hiệu yêu cầu dừng**, không phải lệnh cưỡng bức kết thúc thread ngay lập tức.

Subtask nên:

- Gọi API có khả năng phản hồi interruption khi chờ.
- Không nuốt InterruptedException.
- Nếu bắt exception để cleanup, hoàn tất cleanup rồi ném lại hoặc khôi phục interrupt status theo hợp đồng của method.
- Đóng resource trong try-with-resources.
- Dùng timeout của client cho I/O có thể không phản hồi interrupt.

Ví dụ task chờ có thể bị hủy:

~~~java
static String slowLookup() throws InterruptedException {
    Thread.sleep(10_000);
    return "completed";
}
~~~

Khi thread bị interrupt, Thread.sleep ném InterruptedException và subtask kết thúc nếu exception được truyền ra ngoài.

Ví dụ cần tránh:

~~~java
static String badLookup() {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException ignored) {
        // Bỏ qua interrupt khiến scope khó kết thúc đúng hạn.
    }
    return "completed";
}
~~~

Nếu subtask bỏ qua interrupt hoặc bị kẹt trong API không thể interrupt, close() có thể phải chờ rất lâu, thậm chí vô thời hạn. Structured Concurrency không thể cưỡng bức dừng một thread đang không phản hồi.

## 11. Xử lý interruption ở thread owner

join() có thể ném InterruptedException nếu owner bị interrupt trong lúc chờ. Khi đó scope sẽ được đóng và các subtask được hủy. Nếu bắt exception tại tầng trên, cần bảo toàn chính sách interruption của ứng dụng.

Ví dụ khi không thể khai báo throws InterruptedException:

~~~java
static Dashboard loadSafely(String customerId) {
    try {
        return loadDashboard(customerId);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
                "Request bị interrupt khi chờ các subtask", e);
    }
}
~~~

Không chuyển InterruptedException thành lỗi nghiệp vụ thông thường rồi tiếp tục xử lý như chưa có cancellation. Interruption thường biểu thị owner hoặc tầng quản lý đang yêu cầu dừng công việc.

## 12. Tích hợp ScopedValue trong cây subtask

Java 25 có **ScopedValue** là API chính thức. Khi scope được mở trong một phạm vi ScopedValue đang được bind, các thread được tạo để chạy subtask kế thừa binding tại thời điểm mở scope.

Ví dụ:

~~~java
import java.util.concurrent.StructuredTaskScope;

final class RequestContextService {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    static Dashboard load(String requestId) throws Exception {
        return ScopedValue.where(REQUEST_ID, requestId).call(() -> {
            try (var scope = StructuredTaskScope.open()) {
                var profile = scope.fork(
                        () -> profileRepository.load(REQUEST_ID.get()));
                var orders = scope.fork(
                        () -> orderRepository.load(REQUEST_ID.get()));

                scope.join();
                return new Dashboard(profile.get(), orders.get());
            }
        });
    }
}
~~~

Các subtask có thể đọc cùng REQUEST_ID mà không cần truyền tham số qua mọi tầng gọi. Scope ghi nhận binding khi được mở; các binding tại thời điểm fork phải tương ứng với binding đã được capture khi mở scope. Cơ chế này giúp tránh việc scope con giữ một binding đã bị hoàn nguyên ở thread cha trong khi subtask vẫn đang chạy.

Giá trị chia sẻ giữa các thread nên là immutable object; nếu object mutable thì mọi truy cập phải được đồng bộ phù hợp. ScopedValue không tự biến một object mutable thành thread-safe.

## 13. Structured Concurrency và virtual threads

Structured Concurrency và virtual threads là hai cơ chế liên quan nhưng có mục tiêu khác nhau:

| Cơ chế | Vai trò |
| --- | --- |
| **Virtual threads (JEP 444)** | Cho phép tạo nhiều thread nhẹ, thuận tiện cho tác vụ blocking I/O. |
| **Structured Concurrency (JEP 505)** | Quản lý quan hệ, vòng đời, cancellation và kết quả của nhóm tác vụ con. |

Trong JDK 25, StructuredTaskScope mặc định dùng thread factory tạo virtual thread cho mỗi subtask. Có thể thay factory nếu cần cách tạo thread khác.

Structured Concurrency không làm một tác vụ CPU-bound tự chạy nhanh hơn số core vật lý. Với tính toán CPU nặng, cần giới hạn mức song song phù hợp với CPU và workload. Virtual thread hữu ích nhất khi nhiều tác vụ chờ I/O độc lập; scope giúp quản lý vòng đời nhóm tác vụ đó.

## 14. Structured Concurrency khác ExecutorService và CompletableFuture ở đâu?

Các API này có thể cùng xuất hiện trong một ứng dụng, nhưng biểu đạt những hợp đồng khác nhau:

| Tiêu chí | StructuredTaskScope (preview trong JDK 25) | ExecutorService | CompletableFuture |
| --- | --- | --- | --- |
| Quan hệ vòng đời cha–con | Có, qua scope lồng nhau. | Ứng dụng tự quản lý. | Phụ thuộc chuỗi stage được tạo. |
| Chờ nhóm tác vụ | join() theo Joiner. | invokeAll, Future.get hoặc cơ chế khác. | allOf, anyOf và composition. |
| Cancellation khi lỗi | Joiner có thể hủy các subtask còn lại. | Cần tự quản lý Future/cancel. | Cancellation propagation cần thiết kế rõ. |
| Quan sát quan hệ thread | Có cấu trúc scope trong thread dump. | Thường thấy executor/thread pool. | Không tự biểu diễn đầy đủ quan hệ thread như scope. |
| Trạng thái API JDK 25 | Preview, cần bật preview. | API ổn định. | API ổn định. |

Nếu hệ thống phải chạy trên JDK 25 mà không thể chấp nhận preview API, tiếp tục dùng API ổn định như ExecutorService hoặc CompletableFuture theo hợp đồng hiện tại. Nếu ứng dụng chấp nhận preview để thử nghiệm, Structured Concurrency cung cấp mô hình vòng đời nhóm tác vụ rõ ràng hơn.

## 15. Quan sát cấu trúc scope và thread dump

Một lợi ích của Structured Concurrency là quan hệ cha–con có thể được quan sát qua thread dump. Khi điều tra một request chậm, thread dump dạng JSON có thể giúp nhận diện scope và các thread thực thi subtask.

Trong môi trường kiểm thử, dùng jcmd để tạo thread dump:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Thay <pid> bằng PID của JVM. Đọc kết quả để quan sát virtual thread và quan hệ cấu trúc được runtime ghi nhận. Thread dump là ảnh chụp tại một thời điểm; để điều tra latency đầy đủ, kết hợp thêm JFR, log và metric của request.

Không nên đặt tên thread hoặc scope chứa token, dữ liệu khách hàng hay thông tin bí mật. Tên scope/thread có thể xuất hiện trong công cụ chẩn đoán và log.

## 16. Biên dịch và chạy preview đúng JDK 25

Vì StructuredTaskScope và các kiểu liên quan là preview API trong Java 25, cần dùng JDK 25 ở cả bước biên dịch và chạy.

~~~bash
# Xác nhận đúng JDK
java --version
javac --version

# Biên dịch mã dùng preview API Java 25
javac --enable-preview --release 25 StructuredExample.java

# Chạy bằng JDK 25 và bật preview
java --enable-preview StructuredExample
~~~

Trong Maven/Gradle, cấu hình compiler và test/runtime JVM phải bật preview cho đúng release 25. Chỉ bật cờ ở compiler mà không bật ở runtime vẫn có thể dẫn tới lỗi khi chạy class file preview.

**Preview gắn với phiên bản phát hành.** Class file được biên dịch bằng preview API Java 25 không phải artifact có thể mang nguyên sang JDK 26 hoặc JDK 27. Khi nâng JDK, phải biên dịch lại bằng API preview của release đích và đọc tài liệu release tương ứng. Không dùng --release 25 để biến preview API thành API ổn định.

### API Java 25 không đồng nhất với API JDK 26/27

| Mốc | Thay đổi đáng chú ý sau JDK 25 |
| --- | --- |
| **JDK 26 – JEP 525** | allSuccessfulOrThrow() trả danh sách kết quả; anySuccessfulResultOrThrow() đổi tên thành anySuccessfulOrThrow(); Joiner bổ sung callback timeout; cấu hình open chuyển sang UnaryOperator. |
| **JDK 27 – JEP 533** | StructuredTaskScope có thêm tham số kiểu ngoại lệ R_X; join() mặc định dùng ExecutionException; có overload open(UnaryOperator); Joiner và timeout tiếp tục được điều chỉnh. |
| **JDK 28 EA – JEP 543** | API final được tích hợp, không còn preview marker; JDK 28 chưa GA tại ngày 27/11/2026. |

Không lấy tên Joiner, kiểu kết quả hoặc exception của JDK 26/27 ghép vào source code JDK 25. Hãy dùng tài liệu API đúng release và biên dịch lại trong CI.

## 17. Giới hạn và lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| StructuredTaskScope is a preview API | Chưa bật preview khi biên dịch. | Dùng javac --enable-preview --release 25. |
| Runtime từ chối class file preview | Chưa bật preview hoặc chạy bằng JDK khác release đã biên dịch. | Chạy bằng JDK 25 với java --enable-preview. |
| Không tìm thấy ShutdownOnFailure | Đang dùng ví dụ API trước JEP 505. | Chuyển sang StructuredTaskScope.open(...) và Joiner. |
| Không tìm thấy anySuccessfulOrThrow() | Đã lấy tên API từ JDK 26/27. | Trong JDK 25 dùng anySuccessfulResultOrThrow(). |
| Subtask.get() ném lỗi trạng thái | Gọi trước join, subtask chưa thành công hoặc scope đã bị hủy. | Gọi sau join và kiểm tra chính sách/outcome. |
| Scope đóng nhưng request vẫn chờ | Subtask không phản hồi interrupt hoặc đang block trong API không interruptible. | Dùng timeout ở client, đóng resource và thiết kế cancellation cooperative. |
| join() ném FailedException | Joiner tạo outcome lỗi khi subtask thất bại. | Kiểm tra getCause() và xử lý exception gốc. |
| join() ném TimeoutException | Timeout cấu hình cho scope đã hết hạn. | Xem deadline, thời gian từng dependency và cancellation. |
| fork() hoặc join() báo sai owner thread | Thread khác owner đang gọi thao tác quản lý scope. | Chỉ owner được fork, join và close. |
| Không thể fork sau join | Scope đã chuyển sang giai đoạn chờ/kết quả. | Hoàn tất danh sách fork trước khi gọi join. |
| Scope close chờ vô hạn | Subtask bỏ qua interrupt hoặc I/O không có timeout. | Làm subtask phản hồi interrupt và đặt timeout cho I/O. |
| ScopedValue không được kế thừa như mong đợi | Scope được mở ngoài binding mong muốn hoặc binding thay đổi giữa open và fork. | Bind context trước khi open; giữ binding nhất quán trong vòng đời scope. |

### Checklist trước khi dùng trong ứng dụng

1. Xác nhận JDK release và preview status.
2. Xác định các subtask thực sự độc lập và có thể chạy đồng thời.
3. Chọn Joiner phù hợp với chính sách kết quả.
4. Đặt timeout cho scope và cho từng dependency I/O nếu cần.
5. Đảm bảo subtask phản hồi interruption.
6. Chỉ owner thread gọi fork/join/close.
7. Đọc kết quả subtask sau join.
8. Dùng dữ liệu context immutable khi chia sẻ qua ScopedValue.
9. Đánh giá khả năng thay đổi API trước khi đưa preview vào đường chạy quan trọng.

## 18. Bài tập thực hành

### Bài A — Chạy hai subtask có kiểu kết quả khác nhau

Viết một service lấy hồ sơ và đơn hàng đồng thời bằng StructuredTaskScope.open(). Gọi join() rồi ghép hai kết quả.

**Đạt:** hiểu thứ tự open/fork/join/get/close và xử lý FailedException.

### Bài B — So sánh hai chính sách Joiner

Chạy ba tác vụ cùng kiểu dữ liệu với allSuccessfulOrThrow(); sau đó thay bằng anySuccessfulResultOrThrow(). Cho một tác vụ hoàn thành nhanh và hai tác vụ chậm.

**Đạt:** giải thích được khi nào scope chờ tất cả, khi nào scope hủy các nhánh còn lại.

### Bài C — Kiểm tra cancellation

Tạo một subtask ném exception và một subtask đang Thread.sleep. Quan sát nhánh còn lại nhận interrupt và scope đóng sau khi thread kết thúc.

**Đạt:** giải thích vì sao interruption là tín hiệu cooperative và vì sao task không phản hồi interrupt có thể làm close chờ lâu.

### Bài D — Cấu hình timeout

Mở scope với timeout 1 giây. Một subtask mất 200 ms, một subtask mất 5 giây. Ghi nhận exception và thời gian đóng scope.

**Đạt:** phân biệt timeout của scope với timeout của HTTP/database client.

### Bài E — Truyền request context

Bind request ID bằng ScopedValue trước khi mở scope. Fork hai subtask đọc request ID trong service/repository.

**Đạt:** giải thích binding được capture lúc mở scope và yêu cầu object chia sẻ phải immutable hoặc được đồng bộ.

### Bài F — Quan sát thread dump

Đặt tên virtual thread bằng ThreadFactory, chạy các subtask trong thời gian đủ dài rồi tạo thread dump JSON bằng jcmd.

**Đạt:** nhận diện được owner, subtask và quan hệ scope trong dữ liệu quan sát.

### Bài G — So sánh API theo release

Biên dịch ví dụ JDK 25 với --enable-preview --release 25. Đọc API docs JDK 26, 27 và JDK 28 Early Access để liệt kê thay đổi của Joiner, exception và preview status.

**Đạt:** không dùng source code JDK 25 preview như thể là API ổn định hoặc tương thích nguyên trạng với release mới hơn.

## 19. Câu hỏi tự kiểm tra

1. Structured Concurrency tổ chức quan hệ giữa task và subtask như thế nào?
2. Vì sao StructuredTaskScope được dùng trong try-with-resources?
3. Thread nào là owner và những thao tác nào chỉ owner được gọi?
4. fork() khác việc gọi một method tuần tự ở điểm nào?
5. join() mặc định xử lý khi một subtask thất bại ra sao?
6. Joiner quyết định điều gì và có những chính sách dựng sẵn nào trong JDK 25?
7. anySuccessfulResultOrThrow() phù hợp với tình huống nào?
8. Vì sao Subtask.get() chỉ được gọi sau khi join thành công?
9. Timeout của scope khác timeout của HTTP client ở điểm nào?
10. Vì sao close() vẫn có thể chờ lâu sau khi scope đã bị hủy?
11. ScopedValue được kế thừa vào subtask trong điều kiện nào?
12. Vì sao code preview Java 25 cần bật preview ở cả compiler và runtime?
13. JEP 505 thay đổi gì so với API preview lần thứ tư?
14. Trạng thái của Structured Concurrency trong JDK 27 và JDK 28 Early Access tại ngày 27/11/2026 là gì?

## 20. Tài liệu tham khảo chính thức

- [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): mục tiêu và thay đổi API trong JDK 25.
- [StructuredTaskScope — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): open, fork, join, timeout, cancellation và ScopedValue inheritance.
- [StructuredTaskScope.Joiner — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): chính sách hoàn thành dựng sẵn và Joiner tùy chỉnh.
- [Structured Concurrency — Java 25 Core Libraries Guide](https://docs.oracle.com/en/java/javase/25/core/structured-concurrency.html): khái niệm, quy trình dùng scope, Joiner và cấu hình.
- [Preview Features — Java SE 25](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html): cách biên dịch/chạy preview và giới hạn tương thích giữa các release.
- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): thay đổi trong JDK 26.
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533): thay đổi trong JDK 27.
- [JDK 27 StructuredTaskScope API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): API preview của JDK 27 và kiểu ngoại lệ R_X.
- [JEP 543 — Structured Concurrency](https://openjdk.org/jeps/543): hoàn thiện API sau bảy vòng preview trong JDK 28.
- [JDK 28 Early Access StructuredTaskScope API](https://download.java.net/java/early_access/jdk28/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): tài liệu API final trong JDK 28 EA, chưa phải bản GA.
- [OpenJDK review — Implement JEP 543](https://www.mail-archive.com/core-libs-dev%40openjdk.org/msg75715.html): thay đổi tích hợp để bỏ preview marker và cập nhật @since cho JDK 28.

**Ghi chú tính hiện hành:** Structured Concurrency là hướng API hiện hành của Java và đã được hoàn thiện trong mã nguồn JDK 28 Early Access theo JEP 543. Tuy nhiên, JDK 25 vẫn chỉ cung cấp preview lần thứ năm (JEP 505); JDK 27 GA vẫn là preview lần thứ bảy. Hãy dùng mã và cờ compiler/runtime đúng phiên bản JDK, không lấy API từ các vòng preview cũ hoặc trộn signature của JDK 26/27 vào source JDK 25.

**Kết quả cần nộp:** một chương trình Java 25 dùng StructuredTaskScope.open(), nhiều subtask, một Joiner phù hợp, xử lý lỗi/cancellation, cấu hình timeout, kết quả chạy với preview flags và bảng đối chiếu trạng thái JDK 25/26/27/28. Kết quả cần thể hiện bạn hiểu phạm vi của preview lần thứ năm và biết đánh giá mức độ ổn định của API trước khi sử dụng trong ứng dụng.
