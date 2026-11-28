# Tổ chức các tác vụ con trong một phạm vi có vòng đời rõ ràng

Một request trong ứng dụng thường cần gọi nhiều dịch vụ độc lập: lấy hồ sơ người dùng, đọc đơn hàng, tải quyền truy cập hoặc truy vấn danh mục. Chạy tuần tự khiến tổng thời gian chờ tăng lên; chạy song song có thể giảm latency, nhưng cũng tạo ra một vấn đề khó thấy: khi request cha kết thúc hoặc một tác vụ thất bại, những tác vụ con còn lại có thể tiếp tục chạy, giữ tài nguyên và thực hiện side effect ngoài ý muốn.

**Structured Concurrency** tổ chức các tác vụ con thành một nhóm có quan hệ cha-con và một phạm vi vòng đời rõ ràng. Phạm vi đó quyết định nơi tạo tác vụ, cách chờ kết quả, chính sách xử lý lỗi và thời điểm các thread con phải kết thúc. Java 25 cung cấp API thử nghiệm **StructuredTaskScope** trong package **java.util.concurrent** qua **JEP 505 — Structured Concurrency (Fifth Preview)**.

Bài thuộc chương **Structured Concurrency** của module **JAVA_VERSION_JAVA25**. Nội dung dùng đúng API preview của Java 25: **StructuredTaskScope.open()**, **fork()**, **join()**, **close()**, **Subtask** và **Joiner**. Bài cũng đặt API Java 25 trong bối cảnh hiện hành: JDK 27 vẫn phát hành Structured Concurrency ở preview lần thứ bảy; JEP 543 đã tích hợp API final vào JDK 28 early-access, nhưng JDK 28 chưa GA tại thời điểm biên soạn. Vì API thay đổi giữa các preview, các ví dụ trong bài được gắn rõ với JDK 25.

> **Lưu ý về preview:** StructuredTaskScope trong Java 25 chưa phải API final. Muốn biên dịch và chạy ví dụ phải bật preview ở cả compiler và JVM. Không lấy ví dụ cũ dùng constructor hoặc các lớp ShutdownOnFailure/ShutdownOnSuccess từ những preview trước để áp dụng vào JDK 25.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích Structured Concurrency và vì sao vòng đời tác vụ con cần gắn với tác vụ cha.
2. Phân biệt concurrency có cấu trúc với việc tạo thread, ExecutorService, Future và CompletableFuture một cách rời rạc.
3. Mô tả vai trò của StructuredTaskScope, fork, join, close, Subtask và Joiner.
4. Viết chương trình Java 25 sử dụng StructuredTaskScope.open() trong try-with-resources.
5. Chọn chính sách chờ kết quả phù hợp: tất cả thành công, chờ mọi tác vụ, hoặc lấy kết quả thành công đầu tiên.
6. Hiểu cách lỗi ở một subtask có thể kích hoạt cancellation cho các subtask còn lại.
7. Viết tác vụ con có khả năng phản hồi interruption và giải phóng tài nguyên.
8. Cấu hình tên scope, ThreadFactory và timeout.
9. Hiểu virtual threads được dùng mặc định và cách ScopedValue được truyền vào các tác vụ con.
10. Nhận biết giới hạn của Structured Concurrency: không tự rollback side effect, không giới hạn tải hệ thống và không làm CPU-bound code tự nhanh hơn.
11. Phân biệt API Java 25 với những thay đổi trong JDK 26, 27 và JDK 28.
12. Đánh giá khi nào nên áp dụng Structured Concurrency trong service Java/Spring Boot.

## 2. Structured Concurrency giải quyết vấn đề gì?

Hãy xem một request lấy dữ liệu trang tổng quan. Request cần gọi ba dịch vụ độc lập:

- User service trả hồ sơ người dùng.
- Order service trả đơn hàng gần đây.
- Recommendation service trả danh sách gợi ý.

Nếu gọi tuần tự, thời gian chờ gần bằng tổng thời gian của ba lời gọi. Nếu chạy song song, thời gian chờ có thể gần với lời gọi chậm nhất. Nhưng khi chạy song song, chương trình cần quản lý các tình huống:

- Một tác vụ hoàn tất nhưng hai tác vụ khác vẫn đang chạy.
- Một tác vụ thất bại, trong khi các tác vụ còn lại không còn cần thiết.
- Request cha bị timeout hoặc bị hủy.
- Một tác vụ con bị block và không phản hồi interruption.
- Thread cha muốn trả response trong khi thread con vẫn đang sử dụng tài nguyên.

Với concurrency không có cấu trúc, lập trình viên thường phải tự lưu các Future, gọi cancel, xử lý exception và bảo đảm không bỏ quên tác vụ. Khi số nhánh tăng, quan hệ vòng đời trở nên khó theo dõi.

Structured Concurrency đưa các tác vụ liên quan vào một **scope**. Scope là nơi bắt đầu, phối hợp và kết thúc nhóm tác vụ. Tác vụ cha chỉ tiếp tục sau khi chính sách join được thỏa mãn; khi scope đóng, các thread con do scope tạo phải kết thúc trước khi luồng cha rời khỏi khối try-with-resources.

~~~mermaid
flowchart TD
    P["Request / tác vụ cha"] --> S["StructuredTaskScope"]
    S --> A["Subtask: User"]
    S --> B["Subtask: Orders"]
    S --> C["Subtask: Recommendations"]
    A --> J["join(): áp dụng chính sách hoàn tất"]
    B --> J
    C --> J
    J --> R["Tổng hợp kết quả"]
    R --> X["close(): đóng scope"]
    X --> O["Tác vụ cha tiếp tục"]
~~~

### 2.1. Một scope tương tự phạm vi của try-with-resources

Một scope có thể được hiểu như một tài nguyên đại diện cho nhóm công việc song song:

- Mở scope để bắt đầu một đơn vị công việc.
- Fork các subtask trong scope.
- Join để chờ kết quả theo một chính sách đã chọn.
- Đọc kết quả sau khi join.
- Đóng scope để bảo đảm các thread con đã kết thúc.

Mô hình này làm cho cấu trúc concurrency hiện rõ trong code. Người đọc có thể nhìn vào một khối lệnh và xác định những tác vụ nào thuộc cùng request, lỗi được xử lý ở đâu và khi nào các thread con phải kết thúc.

## 3. StructuredTaskScope trong Java 25

Trong Java 25, **StructuredTaskScope** là một sealed interface preview thuộc package **java.util.concurrent**. Scope được mở bằng các factory method tĩnh thay vì khởi tạo bằng constructor công khai.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| StructuredTaskScope.open() | Mở scope với chính sách mặc định |
| StructuredTaskScope.open(Joiner) | Mở scope với chính sách phối hợp tùy chọn |
| fork(Callable) | Chạy một tác vụ con có kết quả |
| fork(Runnable) | Chạy một tác vụ con không trả kết quả |
| join() | Chờ theo chính sách của scope và trả kết quả tổng hợp |
| close() | Đóng scope, hủy tác vụ chưa hoàn tất và chờ các thread con kết thúc |
| StructuredTaskScope.Subtask | Đại diện cho một tác vụ con |
| StructuredTaskScope.Joiner | Định nghĩa chính sách xử lý khi các subtask hoàn tất |
| StructuredTaskScope.Configuration | Cấu hình thread factory, tên scope và timeout |

Mặc định, mỗi lần gọi fork tạo một **virtual thread** để thực thi subtask. Scope có thể được cấu hình bằng một ThreadFactory khác khi có nhu cầu quan sát hoặc kiểm soát thread.

### 3.1. Vòng đời cơ bản

Một scope Java 25 có trình tự thông thường:

1. Thread hiện tại gọi open() và trở thành owner của scope.
2. Owner gọi fork() để tạo các subtask.
3. Các subtask chạy đồng thời trên thread riêng.
4. Owner gọi join() để chờ chính sách hoàn tất.
5. Owner đọc kết quả từ join() hoặc Subtask.get().
6. Khối try kết thúc và close() được gọi tự động.

~~~mermaid
sequenceDiagram
    participant O as Owner thread
    participant S as StructuredTaskScope
    participant T1 as Subtask 1
    participant T2 as Subtask 2

    O->>S: open()
    O->>S: fork(task1)
    S->>T1: start virtual thread
    O->>S: fork(task2)
    S->>T2: start virtual thread
    O->>S: join()
    T1-->>S: result / failure
    T2-->>S: result / failure
    S-->>O: join outcome
    O->>O: đọc kết quả
    O->>S: close() qua try-with-resources
    S-->>O: bảo đảm thread con đã kết thúc
~~~

## 4. Ví dụ đầu tiên: chạy song song các tác vụ độc lập

Giả sử trang tổng quan cần hồ sơ người dùng và thống kê đơn hàng. Hai lời gọi độc lập, có thể thực hiện đồng thời.

~~~java
import java.util.concurrent.StructuredTaskScope;

record UserProfile(String id, String displayName) {}
record OrderSummary(long orderCount, long totalAmount) {}
record Dashboard(UserProfile user, OrderSummary orders) {}

class DashboardService {

    Dashboard loadDashboard(String userId)
            throws InterruptedException {

        try (var scope = StructuredTaskScope.open()) {
            var userTask = scope.fork(
                    () -> fetchUserProfile(userId));

            var orderTask = scope.fork(
                    () -> fetchOrderSummary(userId));

            // Chính sách mặc định: chờ tất cả thành công,
            // nếu một subtask thất bại thì hủy các subtask còn lại.
            scope.join();

            return new Dashboard(
                    userTask.get(),
                    orderTask.get());
        }
    }

    private UserProfile fetchUserProfile(String userId) {
        // Gọi User service
        return new UserProfile(userId, "An");
    }

    private OrderSummary fetchOrderSummary(String userId) {
        // Gọi Order service
        return new OrderSummary(12, 4_500_000);
    }
}
~~~

**Diễn giải:**

- open() mở một scope với chính sách mặc định.
- Mỗi fork() tạo một subtask trên virtual thread mới.
- Hai lời gọi có thể tiến hành đồng thời.
- join() chờ các subtask theo chính sách mặc định.
- Khi join thành công, get() lấy kết quả của từng subtask.
- Khi khối try kết thúc, close() được gọi để đóng scope.

open() mặc định sử dụng chính sách chờ tất cả subtask thành công. Nếu một subtask thất bại, scope bị hủy, các subtask còn lại được interrupt và join() ném StructuredTaskScope.FailedException.

### 4.1. Vì sao phải gọi join trước khi lấy kết quả?

Trong Java 25, Subtask.get() chỉ được gọi bởi owner sau khi scope đã join và subtask đã hoàn tất thành công. Nếu gọi get() trước khi join hoặc khi subtask không ở trạng thái thành công, API sẽ từ chối thao tác.

Trình tự đúng:

~~~java
try (var scope = StructuredTaskScope.open()) {
    var first = scope.fork(() -> loadFirst());
    var second = scope.fork(() -> loadSecond());

    scope.join();

    Result a = first.get();
    Result b = second.get();
}
~~~

Không dùng Subtask.get() như một phương thức chờ tương tự Future.get(). Việc chờ và phối hợp thuộc về join(); get() chỉ đọc kết quả sau khi chính sách của scope đã hoàn tất.

## 5. Chính sách hoàn tất với Joiner

Không phải tác vụ nào cũng cần chờ tất cả subtask theo cùng một cách. Java 25 cung cấp StructuredTaskScope.Joiner để định nghĩa chính sách phối hợp.

| Joiner | Hành vi của join() | Khi phù hợp |
|---|---|---|
| awaitAllSuccessfulOrThrow() | Chờ tất cả thành công; hủy scope và ném lỗi nếu một subtask thất bại | Cần kết quả từ nhiều subtask khác kiểu |
| allSuccessfulOrThrow() | Trả stream các subtask nếu tất cả thành công; hủy scope và ném lỗi khi có thất bại | Các subtask cùng kiểu kết quả |
| anySuccessfulResultOrThrow() | Trả kết quả của subtask thành công đầu tiên; hủy phần còn lại; lỗi nếu tất cả thất bại | Gọi nhiều replica/provider và chỉ cần một kết quả |
| awaitAll() | Chờ tất cả subtask kết thúc, không tự hủy scope hoặc ném lỗi chỉ vì một subtask thất bại | Muốn thu thập và tự xử lý từng trạng thái |

Tên và kiểu trả về trong bảng là API Java 25. Một số tên và kiểu kết quả đã thay đổi trong các JDK sau.

### 5.1. Mặc định: tất cả phải thành công

Khi dùng:

~~~java
try (var scope = StructuredTaskScope.open()) {
    var user = scope.fork(() -> fetchUser());
    var orders = scope.fork(() -> fetchOrders());

    scope.join();

    return new Dashboard(user.get(), orders.get());
}
~~~

join() trả về null khi tất cả subtask thành công. Nếu một subtask thất bại, join() ném StructuredTaskScope.FailedException; exception của subtask thất bại được đặt làm cause.

### 5.2. Chờ tất cả kết quả cùng kiểu

Khi nhiều subtask trả về cùng một kiểu, có thể dùng allSuccessfulOrThrow():

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

List<String> searchAll(List<String> indexes, String query)
        throws InterruptedException {

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner
                    .<String>allSuccessfulOrThrow())) {

        indexes.forEach(index ->
                scope.fork(() -> search(index, query)));

        return scope.join()
                .map(StructuredTaskScope.Subtask::get)
                .toList();
    }
}
~~~

Trong Java 25, join() của allSuccessfulOrThrow() trả về một stream các Subtask. Kết quả của từng subtask được lấy bằng Subtask.get().

Nếu một subtask thất bại, scope bị hủy và join() ném FailedException. Joiner này phù hợp khi tất cả kết quả đều cần thiết và cùng kiểu dữ liệu.

### 5.3. Lấy kết quả thành công đầu tiên

Một trường hợp khác là truy vấn nhiều replica hoặc nhiều nhà cung cấp dữ liệu. Chỉ cần một kết quả thành công là đủ:

~~~java
import java.util.concurrent.StructuredTaskScope;

String fetchFromAnyProvider(String key)
        throws InterruptedException {

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner
                    .<String>anySuccessfulResultOrThrow())) {

        scope.fork(() -> providerA.read(key));
        scope.fork(() -> providerB.read(key));
        scope.fork(() -> providerC.read(key));

        return scope.join();
    }
}
~~~

anySuccessfulResultOrThrow() trả kết quả từ subtask đầu tiên hoàn tất thành công. Khi đã có kết quả, Joiner hủy scope và interrupt các subtask còn lại. Nếu tất cả subtask đều thất bại, join() ném FailedException.

Không dùng chính sách này nếu mọi kết quả đều phải được tổng hợp hoặc các tác vụ có side effect bắt buộc phải hoàn tất.

### 5.4. Chờ tất cả nhưng tự xử lý lỗi

awaitAll() chờ tất cả subtask kết thúc mà không tự hủy scope khi một subtask thất bại. Owner có thể kiểm tra từng trạng thái sau khi join:

~~~java
try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAll())) {

    var profile = scope.fork(() -> fetchProfile());
    var orders = scope.fork(() -> fetchOrders());
    var recommendations = scope.fork(() -> fetchRecommendations());

    scope.join();

    if (profile.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
        useProfile(profile.get());
    }

    if (orders.state() == StructuredTaskScope.Subtask.State.FAILED) {
        logFailure(orders.exception());
    }

    if (recommendations.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
        useRecommendations(recommendations.get());
    }
}
~~~

Chính sách này hữu ích khi từng kết quả có thể thành công hoặc thất bại độc lập và ứng dụng muốn áp dụng fallback riêng. Hãy kiểm tra Subtask.state() trước khi gọi get() hoặc exception().

### 5.5. Tự thiết kế Joiner

Java 25 cho phép triển khai StructuredTaskScope.Joiner<T,R> khi các chính sách có sẵn không đáp ứng yêu cầu.

Các callback chính:

- onFork(Subtask) được gọi khi owner fork một subtask.
- onComplete(Subtask) được gọi khi subtask hoàn tất thành công hoặc thất bại.
- result() tạo kết quả cuối cùng hoặc ném exception cho join().

onFork và onComplete trả về boolean; trả true yêu cầu scope hủy các subtask còn lại. Các callback hoàn tất có thể được nhiều thread gọi đồng thời, vì vậy implementation của Joiner phải thread-safe.

Tạo một Joiner mới cho từng scope. Không chia sẻ một instance Joiner mutable giữa nhiều scope và không đặt business logic phức tạp vào Joiner; hãy để Joiner tập trung vào chính sách phối hợp, còn owner xử lý nghiệp vụ sau khi join.

## 6. Cách lỗi và cancellation lan truyền

Một mục tiêu quan trọng của Structured Concurrency là xử lý lỗi trong một nhóm tác vụ như một đơn vị công việc.

Với chính sách awaitAllSuccessfulOrThrow() hoặc mặc định:

1. Một subtask ném exception.
2. Joiner nhận biết subtask thất bại.
3. Scope bị hủy.
4. Các thread đang chạy subtask khác được interrupt.
5. join() thức dậy và ném StructuredTaskScope.FailedException.
6. Owner xử lý cause và đóng scope.

~~~mermaid
sequenceDiagram
    participant O as Owner
    participant S as Scope
    participant A as Subtask A
    participant B as Subtask B

    O->>S: fork A và B
    S->>A: chạy A
    S->>B: chạy B
    A-->>S: thất bại
    S->>B: interrupt B
    S-->>O: join() ném FailedException
    O->>S: close()
    B-->>S: kết thúc sau khi xử lý interrupt
    S-->>O: close() hoàn tất
~~~

### 6.1. Cancellation không phải cưỡng chế dừng thread

Cancellation trong Structured Concurrency chủ yếu dựa vào interruption. JVM không cưỡng chế dừng một thread đang chạy tùy ý. Subtask cần hợp tác với cơ chế interrupt:

- Các API blocking interruptible phải được dùng đúng cách.
- Nếu bắt InterruptedException, thường nên truyền exception ra ngoài hoặc khôi phục interrupt status khi không thể truyền.
- Vòng lặp tính toán dài nên kiểm tra Thread.currentThread().isInterrupted().
- Tài nguyên mở như stream, socket hoặc file phải được đóng bằng try-with-resources.
- Không bỏ qua interruption chỉ để hoàn thành công việc khi parent đã hủy.

Ví dụ một tác vụ CPU-bound có thể kiểm tra interruption:

~~~java
long calculate(long limit) throws InterruptedException {
    long total = 0;

    for (long i = 0; i < limit; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Task cancelled");
        }
        total += expensiveStep(i);
    }

    return total;
}
~~~

Nếu subtask gọi một API không phản hồi interruption, scope có thể phải chờ rất lâu khi đóng. Tài liệu Java 25 nêu rõ close() luôn chờ các thread thực thi subtask kết thúc, kể cả khi scope đã bị hủy.

### 6.2. Không nuốt interruption

Mẫu xử lý sau rất nguy hiểm:

~~~java
try {
    callRemoteService();
} catch (InterruptedException e) {
    // Bỏ qua và tiếp tục làm việc
}
~~~

Khi parent đã hủy scope, việc bỏ qua interrupt khiến subtask tiếp tục tiêu thụ tài nguyên và làm chậm close().

Nếu method hiện tại không thể khai báo InterruptedException, có thể khôi phục trạng thái interrupt rồi chuyển lỗi sang exception phù hợp:

~~~java
try {
    callRemoteService();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", e);
}
~~~

Chọn cách xử lý theo contract của API và tầng gọi; không biến interruption thành một lỗi nghiệp vụ bình thường rồi tiếp tục chạy.

### 6.3. Cancellation không rollback side effect

Giả sử subtask đã gửi yêu cầu thanh toán và sau đó scope bị hủy. Interruption không thể tự động hoàn tác giao dịch đã được hệ thống thanh toán chấp nhận.

Structured Concurrency quản lý vòng đời thread và phối hợp kết quả; nó không cung cấp transaction semantics cho hệ thống phân tán. Với các operation có side effect, cần thiết kế idempotency key, timeout, trạng thái giao dịch và quy trình reconciliation riêng.

## 7. Quyền sở hữu scope và các quy tắc cấu trúc

Java 25 áp dụng các quy tắc để bảo đảm scope được dùng đúng cấu trúc:

- Chỉ owner thread đã mở scope mới được gọi fork, join và close.
- Không gọi fork sau khi đã gọi join.
- Trong Java 25, join() chỉ được gọi một lần trên scope.
- Sau khi fork subtask, owner phải gọi join() trước khi scope đóng bình thường.
- Subtask.get() chỉ được gọi sau join khi subtask thành công.
- Subtask.exception() chỉ được gọi sau join khi subtask thất bại.
- Các scope lồng nhau phải được đóng theo thứ tự ngược với thứ tự mở.

Nếu owner rời khối try sau khi đã fork mà chưa join, scope bị hủy và close() chờ các thread con kết thúc; sau đó API báo lỗi sử dụng sai cấu trúc. Không dựa vào close() để thay thế join().

### 7.1. Scope lồng nhau

Một subtask có thể mở scope riêng để fork các subtask nhỏ hơn. Khi đó hình thành cây công việc:

~~~mermaid
flowchart TD
    R["Request"] --> A["Scope: Dashboard"]
    A --> B["Subtask: Profile"]
    A --> C["Subtask: Orders"]
    B --> D["Scope: Profile details"]
    D --> E["Subtask: Account"]
    D --> F["Subtask: Preferences"]
~~~

Mỗi scope chịu trách nhiệm vòng đời của các subtask trực tiếp do nó tạo. Khi scope cha đóng, các scope con cần được đóng theo đúng cấu trúc; nếu không, API có thể phát hiện StructureViolationException.

Không truyền một scope cho nhiều component để chúng tùy ý fork hoặc đóng. Hãy giữ quyền sở hữu ở method điều phối và truyền kết quả hoặc interface nghiệp vụ cho các tầng khác.

## 8. Cấu hình scope: tên, thread factory và timeout

Mặc định của Java 25:

- Scope không có tên.
- Thread factory tạo virtual thread không tên cho từng subtask.
- Không có timeout.
- Các scoped-value bindings hiện tại được capture khi scope được mở và kế thừa bởi các thread con.

Có thể thay đổi cấu hình qua overload open(Joiner, Function<Configuration, Configuration>).

### 8.1. Đặt tên scope để quan sát

Tên scope giúp nhận diện một nhóm công việc khi kiểm tra thread dump hoặc công cụ quản trị:

~~~java
try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow(),
        config -> config.withName("dashboard-request"))) {

    scope.fork(() -> fetchProfile());
    scope.fork(() -> fetchOrders());

    scope.join();
}
~~~

Tên nên mô tả operation hoặc nhóm tác vụ, tránh chứa user ID, token hay dữ liệu nhạy cảm.

### 8.2. Đặt timeout cho scope

Java 25 cho phép cấu hình timeout bằng Duration:

~~~java
import java.time.Duration;
import java.util.concurrent.StructuredTaskScope;

try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow(),
        config -> config
                .withName("dashboard-request")
                .withTimeout(Duration.ofSeconds(2)))) {

    var profile = scope.fork(() -> fetchProfile());
    var orders = scope.fork(() -> fetchOrders());

    scope.join();

    return new Dashboard(profile.get(), orders.get());

} catch (StructuredTaskScope.TimeoutException e) {
    return Dashboard.unavailable();
}
~~~

Đặt đoạn này trong một method khai báo `throws InterruptedException`; ví dụ lược bỏ phần khai báo method để tập trung vào cấu hình scope và timeout.

Timeout bắt đầu tính từ lúc scope được mở, không phải từ lúc owner gọi join(). Vì vậy, mở scope sát với thời điểm fork các tác vụ; tránh tạo scope quá sớm rồi thực hiện nhiều công việc không liên quan trước khi fork.

Khi timeout hết hạn, scope bị hủy và các thread đang chạy subtask được interrupt. join() ném StructuredTaskScope.TimeoutException. close() vẫn chờ các thread con kết thúc, nên timeout không có nghĩa method chắc chắn trả về ngay lập tức nếu subtask không phản hồi interrupt.

### 8.3. Tùy chỉnh ThreadFactory

Scope mặc định tạo virtual threads. Có thể truyền ThreadFactory để đặt tên thread hoặc cấu hình handler:

~~~java
var factory = Thread.ofVirtual()
        .name("dashboard-task-", 0)
        .factory();

try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow(),
        config -> config
                .withName("dashboard")
                .withThreadFactory(factory))) {

    scope.fork(() -> fetchProfile());
    scope.fork(() -> fetchOrders());
    scope.join();
}
~~~

ThreadFactory tạo thread cho các subtask được fork. Nó không biến scope thành một executor pool có hàng đợi hoặc giới hạn concurrency. Nếu cần giới hạn số lời gọi tới một dependency, hãy dùng cơ chế bulkhead/semaphore hoặc giới hạn fan-out riêng.

## 9. Structured Concurrency và virtual threads

Structured Concurrency và virtual threads bổ sung cho nhau nhưng giải quyết hai vấn đề khác nhau:

- **Virtual threads** giúp tạo nhiều thread nhẹ hơn cho các tác vụ thường xuyên block.
- **Structured Concurrency** tổ chức quan hệ cha-con, vòng đời, cancellation và kết quả của các tác vụ.

Java 25 mặc định dùng virtual thread cho mỗi subtask được fork. Điều này phù hợp với các lời gọi I/O blocking như HTTP, JDBC driver hỗ trợ phù hợp hoặc đọc file.

### 9.1. Virtual threads không tự tăng tốc CPU-bound work

Nếu một subtask thực hiện tính toán nặng, nó vẫn cần CPU. Virtual thread không tạo thêm năng lực xử lý CPU. Tạo hàng nghìn subtask CPU-bound có thể làm tăng context switching, queueing và cạnh tranh tài nguyên.

Với CPU-bound work:

- Chọn số tác vụ song song dựa trên CPU quota và số core khả dụng.
- Dùng thuật toán chia việc và cơ chế bounded parallelism phù hợp.
- Đo throughput, CPU saturation và latency.
- Không tạo số subtask không giới hạn chỉ vì virtual threads nhẹ.

### 9.2. Virtual threads không thay thế connection pool hoặc rate limit

Một service có thể tạo hàng nghìn virtual threads, nhưng database chỉ cho phép một số lượng connection hữu hạn. Nếu mọi subtask đồng thời lấy connection, queueing và timeout có thể tăng mạnh.

Structured Concurrency không tự giới hạn số request tới database, API provider hoặc message broker. Cần kết hợp connection pool có giới hạn, semaphore/bulkhead, rate limit, admission control, timeout phù hợp và retry có giới hạn.

## 10. Truyền context bằng ScopedValue

StructuredTaskScope được tích hợp với ScopedValue. Khi scope được mở, các scoped-value bindings hiện tại được capture và kế thừa vào các thread chạy subtask. Điều này hữu ích cho context bất biến như request ID, tenant context, user principal đã xác thực, correlation metadata hoặc locale.

Ví dụ minh họa:

~~~java
static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

Dashboard handleRequest(String requestId) throws InterruptedException {
    return ScopedValue.where(REQUEST_ID, requestId).call(() -> {
        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(() -> {
                log("profile task, request=" + REQUEST_ID.get());
                return fetchProfile();
            });

            var orders = scope.fork(() -> {
                log("orders task, request=" + REQUEST_ID.get());
                return fetchOrders();
            });

            scope.join();
            return new Dashboard(profile.get(), orders.get());
        }
    });
}
~~~

Đây là ví dụ về ý tưởng truyền context; trong ứng dụng thực tế cần thiết kế exception boundary phù hợp với API gọi bên ngoài.

### 10.1. Vì sao cần mở scope bên trong binding?

Scope capture scoped-value bindings tại thời điểm scope được mở. Nếu scope được tạo trước khi bind request context, các thread con không tự động nhận binding được thiết lập sau đó.

Đặt StructuredTaskScope.open() bên trong phạm vi ScopedValue.where(...).run(...) giúp các subtask kế thừa context mong muốn. Scope lồng nhau cũng kế thừa các bindings tại thời điểm mỗi scope được mở.

Không dùng ScopedValue để truyền mutable shared state hoặc bí mật không cần thiết. Binding được kế thừa giúp truyền context; nó không thay thế kiểm soát quyền truy cập, mã hóa hay xác thực.

## 11. So sánh với ExecutorService, Future và CompletableFuture

Các API concurrency hiện có vẫn hữu ích; Structured Concurrency bổ sung một mô hình tổ chức vòng đời.

| Tiêu chí | ExecutorService/Future | CompletableFuture | StructuredTaskScope |
|---|---|---|---|
| Tạo tác vụ | Submit vào executor | Tạo stage và callback async | Fork subtask trong scope |
| Quan hệ cha-con | Không được cưỡng chế bằng cấu trúc lexical | Có thể compose nhưng quan hệ vòng đời không tự nhiên theo scope | Scope biểu diễn rõ nhóm tác vụ con |
| Chờ kết quả | get() hoặc join() trên từng future | join()/composition trên stage | Một lần scope.join() theo Joiner |
| Xử lý lỗi | Caller tự tổng hợp/cancel | Dùng exceptional stages/handlers | Joiner định nghĩa chính sách hoàn tất và cancellation |
| Cancellation | Thường phải gọi cancel từng future | Propagation phụ thuộc graph và API | Scope hủy các subtask còn chạy theo policy |
| Kết thúc phạm vi | Executor có lifecycle riêng | Graph stage có thể tiếp tục | close() chờ thread con kết thúc |
| Mặc định tạo thread | Phụ thuộc executor | Phụ thuộc executor/async facility | Virtual thread cho mỗi subtask |

Structured Concurrency phù hợp khi một operation cha chia thành các tác vụ con liên quan và cần kết quả trước khi tiếp tục. ExecutorService vẫn phù hợp với worker pool sống lâu, hàng đợi công việc, consumer nền và tác vụ được submit độc lập khỏi request hiện tại.

### 11.1. Không thay mọi CompletableFuture bằng StructuredTaskScope

Một pipeline CompletableFuture có thể mô tả nhiều stage phụ thuộc nhau, callback và composition bất đồng bộ. StructuredTaskScope phù hợp hơn khi cần một nhóm task có vòng đời gắn với operation cha và một điểm phối hợp rõ ràng.

Hãy chọn API dựa trên mô hình công việc, không dựa vào việc API nào mới hơn.

## 12. Ví dụ thực tế: fan-out trong service Spring Boot

Một endpoint tổng hợp dữ liệu có thể gọi nhiều dependency song song:

~~~java
@Service
class CustomerOverviewService {

    private final ProfileClient profileClient;
    private final OrderClient orderClient;
    private final RewardClient rewardClient;

    CustomerOverviewService(
            ProfileClient profileClient,
            OrderClient orderClient,
            RewardClient rewardClient) {
        this.profileClient = profileClient;
        this.orderClient = orderClient;
        this.rewardClient = rewardClient;
    }

    CustomerOverview load(String customerId)
            throws InterruptedException {

        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(
                    () -> profileClient.getProfile(customerId));

            var orders = scope.fork(
                    () -> orderClient.getRecentOrders(customerId));

            var rewards = scope.fork(
                    () -> rewardClient.getBalance(customerId));

            scope.join();

            return new CustomerOverview(
                    profile.get(),
                    orders.get(),
                    rewards.get());
        }
    }
}
~~~

Đây là ví dụ minh họa việc điều phối. Khi tích hợp vào Spring Boot, cần kiểm tra:

- Spring bean được gọi từ các virtual threads có hỗ trợ cách truy cập hiện tại hay không.
- Transaction context có được thiết kế phù hợp với thread mới không.
- Security/request context có được truyền qua ScopedValue hoặc cơ chế context propagation tương ứng không.
- HTTP client, JDBC driver và dependency có phản hồi interruption hay không.
- Timeout của scope có phù hợp với timeout của từng dependency và timeout của HTTP request không.
- Connection pool và downstream service có đủ capacity cho fan-out đồng thời không.

Không giả định một transaction được mở trên thread cha sẽ tự động trở thành transaction chung cho mọi subtask. Mỗi subtask có thể chạy trên thread khác và cần transaction boundary rõ ràng theo framework.

## 13. Chọn chính sách theo bài toán nghiệp vụ

| Bài toán | Joiner gợi ý trong Java 25 | Lý do |
|---|---|---|
| Lấy hồ sơ và đơn hàng; thiếu một phần thì request thất bại | awaitAllSuccessfulOrThrow() hoặc open() | Cần mọi kết quả |
| Lấy dữ liệu từ ba replica, chỉ cần một kết quả hợp lệ | anySuccessfulResultOrThrow() | Có thể trả về sớm khi một replica thành công |
| Chạy nhiều phép tính cùng kiểu và tổng hợp tất cả | allSuccessfulOrThrow() | join() trả stream các subtask |
| Thu thập mọi kết quả để áp dụng fallback riêng | awaitAll() | Owner tự kiểm tra trạng thái từng subtask |
| Chạy các tác vụ cùng thuộc một request có deadline | Joiner phù hợp + Configuration.withTimeout() | Scope có thời hạn và cancellation |

Một Joiner nên phản ánh yêu cầu thực tế của operation. Nếu nghiệp vụ cần tất cả kết quả, không dùng policy first-success chỉ để giảm latency. Nếu chỉ cần một replica thành công, không chờ tất cả replica hoàn tất.

## 14. Những giới hạn cần hiểu trước khi áp dụng

Structured Concurrency giúp quản lý vòng đời và lỗi, nhưng không giải quyết mọi vấn đề concurrency.

### 14.1. Không bảo đảm các tác vụ hoàn tất cùng lúc

Các subtask chạy song song, nhưng scheduling phụ thuộc JVM và hệ điều hành. join() chờ theo policy; nó không làm các tác vụ có cùng thời gian thực thi.

### 14.2. Không tự giới hạn số lượng subtask

Một vòng lặp gọi fork() hàng trăm nghìn lần có thể tạo áp lực lên bộ nhớ, downstream và scheduler. Hãy giới hạn fan-out hoặc chia batch.

### 14.3. Không tự khôi phục side effect

Nếu subtask đã ghi database hoặc gửi message, cancellation không rollback các thay đổi đó. Dùng transaction, idempotency và compensation theo yêu cầu nghiệp vụ.

### 14.4. Không bảo đảm task luôn dừng nhanh

Scope close chờ thread con kết thúc. Subtask không hợp tác với interruption có thể làm request cha bị giữ lại lâu hơn timeout dự kiến.

### 14.5. Không thay thế message queue và background worker

Tác vụ cần sống lâu hơn request, được retry độc lập, lưu bền hoặc chạy theo lịch nên được quản lý bằng job queue, scheduler hoặc worker service. Không đặt tác vụ nền không giới hạn trong scope của HTTP request.

### 14.6. Không biến CPU-bound work thành non-blocking

Virtual thread không làm phép tính CPU nặng chạy nhanh hơn. Hãy dùng concurrency có giới hạn và đo trên workload thật.

## 15. Quan sát và debug scope

Một lợi ích của Structured Concurrency là cấu trúc cha-con của thread dễ quan sát hơn.

### 15.1. Đặt tên scope

Dùng Configuration.withName() để đặt tên cho scope. Tên ngắn và có ý nghĩa giúp phân biệt nhóm công việc khi xem thread dump hoặc dữ liệu quản trị.

### 15.2. Dùng jcmd để xem thread dump

JDK cung cấp các lệnh chẩn đoán thread dump qua jcmd. Thread dump có thể hiển thị cấu trúc liên quan tới scope và các virtual threads đang thực thi subtask.

Khi điều tra một request bị treo, hãy xem:

- Owner thread đang ở đâu, có đang chờ trong join() không?
- Những subtask nào còn chạy?
- Thread con đang chờ socket, monitor hay database?
- Có subtask nào không phản hồi interruption?
- Scope có tên để truy vết theo operation không?

### 15.3. Đừng log toàn bộ context nhạy cảm

Tên scope, thread name và custom log fields có thể xuất hiện trong log/diagnostic output. Tránh đưa access token, session cookie, email hoặc dữ liệu cá nhân vào tên scope và thread name.

## 16. Trạng thái API và khác biệt giữa các JDK

Structured Concurrency đã trải qua nhiều vòng preview. Đây là lý do các ví dụ cũ có thể không biên dịch trên JDK 25 hoặc mới hơn.

| JDK | JEP | Trạng thái | Điểm cần biết |
|---|---|---|---|
| 19–20 | JEP 428/437 | Incubator | API ban đầu ở module incubator |
| 21 | JEP 453 | Preview lần 1 | API trong java.util.concurrent |
| 22 | JEP 462 | Preview lần 2 | Tiếp tục hoàn thiện |
| 23 | JEP 480 | Preview lần 3 | Giữ hướng API |
| 24 | JEP 499 | Preview lần 4 | Trước lần thay đổi lớn ở JDK 25 |
| 25 | JEP 505 | Preview lần 5 | open() factory, Joiner, Subtask; ví dụ trong bài dùng phiên bản này |
| 26 | JEP 525 | Preview lần 6 | Tiếp tục thay đổi policy, timeout và kiểu kết quả |
| 27 | JEP 533 | Preview lần 7 | Tiếp tục thay đổi kiểu exception và API Joiner |
| 28 | JEP 543 | Final được tích hợp vào JDK 28 early-access | API final giữ hình dạng từ JDK 27; JDK 28 chưa GA tại thời điểm biên soạn |

### 16.1. Tránh ví dụ từ preview cũ

Các ví dụ cũ có thể sử dụng constructor trực tiếp của StructuredTaskScope, các lớp ShutdownOnFailure hoặc ShutdownOnSuccess, hoặc Future làm kiểu kết quả của fork. Đây không phải hình dạng API Java 25 được dùng trong bài.

Với JDK 25, hãy dùng static factory open(), Joiner và StructuredTaskScope.Subtask.

### 16.2. Không sao chép nguyên ví dụ Java 25 sang JDK 26/27/28

Các phiên bản sau tiếp tục thay đổi tên Joiner, kiểu kết quả và cách biểu diễn exception. Ví dụ Java 25 có thể cần chỉnh sửa khi chuyển sang JDK 26/27 hoặc API final của JDK 28.

Đối với JDK 28 early-access, JEP 543 đã tích hợp Structured Concurrency thành API final. Tuy nhiên, khi viết mã mới cho một toolchain cụ thể, hãy dùng đúng Javadoc của chính JDK đó và kiểm tra signature của StructuredTaskScope, Joiner, Subtask và exception của join().

## 17. Biên dịch và chạy Structured Concurrency trên Java 25

Vì JEP 505 là preview, cần bật preview ở cả compile time và runtime.

Biên dịch:

~~~bash
javac --release 25 --enable-preview -d out DashboardService.java
~~~

Chạy:

~~~bash
java --enable-preview -cp out com.example.DashboardApplication
~~~

Với Maven hoặc Gradle, cấu hình compiler release 25 và bật preview cho cả compiler/test/runtime tasks. Không chỉ bật preview ở compiler rồi chạy ứng dụng mà thiếu JVM option tương ứng.

### 17.1. Preview gắn với phiên bản JDK

Preview API được thiết kế để thử nghiệm và nhận phản hồi. Một class file được biên dịch với preview của JDK 25 không thể được coi là artifact preview dùng chung cho mọi JDK khác. Hãy biên dịch và chạy bằng đúng release tương ứng khi kiểm thử preview.

### 17.2. Khi nâng cấp

Khi chuyển từ Java 25 lên Java 27 hoặc Java 28:

1. Đọc JEP và Javadoc của release đích.
2. So sánh API StructuredTaskScope, Joiner, Subtask và exception.
3. Bỏ các preview flag chỉ khi release đích cung cấp API final.
4. Cập nhật xử lý lỗi và timeout theo API đích.
5. Biên dịch lại toàn bộ module và chạy test cancellation/timeout/failure.
6. Kiểm tra thư viện hoặc framework có dùng API preview này hay không.

Không xóa --enable-preview chỉ vì JEP đã được final hóa trên nhánh phát triển; chỉ bỏ flag khi JDK GA hoặc build đích mà dự án thực sự dùng cung cấp API final.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| StructuredTaskScope không được nhận diện | Thiếu preview flag hoặc đang dùng JDK không đúng release | Dùng JDK 25 và bật preview ở compiler/runtime |
| Ví dụ ShutdownOnFailure không biên dịch | Code thuộc API preview cũ | Chuyển sang open() và Joiner của JDK 25 |
| Subtask.get() ném lỗi trạng thái | Gọi trước join hoặc subtask không thành công | Join trước, kiểm tra trạng thái rồi mới get |
| join() ném FailedException | Một subtask thất bại theo policy fail-fast | Xem cause và kiểm tra tác vụ con |
| Scope đóng rất lâu | Subtask không phản hồi interruption hoặc đang ở blocking call không interruptible | Kiểm tra API blocking, timeout và cleanup |
| Thread con tiếp tục chạy sau khi request cha bị hủy | Subtask nuốt interrupt hoặc side effect đã được gửi ra ngoài | Tôn trọng interrupt, timeout downstream và idempotency |
| Request timeout nhưng close() chưa trả về | Scope vẫn phải chờ thread con kết thúc | Sửa tác vụ con để dừng hợp tác |
| Một subtask làm hỏng tất cả kết quả | Đang dùng Joiner fail-fast trong khi nghiệp vụ cần partial result | Chọn awaitAll() và xử lý trạng thái riêng |
| Tạo quá nhiều virtual threads | Fan-out không giới hạn | Giới hạn số subtask, dùng bulkhead/semaphore |
| CPU tăng khi chạy song song | Tác vụ CPU-bound hoặc concurrency quá lớn | Giới hạn mức song song và benchmark |
| Không thấy context trong subtask | Scope được mở ngoài phạm vi ScopedValue binding | Mở scope bên trong binding |
| WrongThreadException hoặc lỗi cấu trúc | Thread khác owner gọi fork/join/close hoặc đóng scope sai thứ tự | Giữ quyền sở hữu scope tại owner và đóng theo thứ tự lồng nhau |
| Code chạy trên JDK 25 nhưng không chạy trên JDK 27/28 | API preview thay đổi giữa các release | Dùng Javadoc của JDK đích và cập nhật Joiner/exception |

## 19. Bài tập thực hành

**Bài 1 — Fan-out request:** viết method lấy hồ sơ người dùng và đơn hàng bằng hai subtask. Dùng open(), fork(), join() và Subtask.get().

**Bài 2 — Failure propagation:** làm một subtask ném exception. Quan sát FailedException, cause và việc subtask còn lại nhận interruption.

**Bài 3 — Interruption cooperation:** viết một tác vụ vòng lặp dài, thêm kiểm tra interrupt. Hủy scope và xác nhận thread con kết thúc.

**Bài 4 — First successful result:** mô phỏng ba replica. Dùng Joiner.anySuccessfulResultOrThrow() và kiểm tra các subtask còn lại bị hủy sau khi có kết quả đầu tiên.

**Bài 5 — All results:** chạy một tập tác vụ cùng kiểu với allSuccessfulOrThrow(). Lấy stream các Subtask và chuyển thành danh sách kết quả.

**Bài 6 — Partial results:** dùng awaitAll() để chờ tất cả tác vụ rồi kiểm tra trạng thái từng subtask. Thiết kế fallback khi một dependency thất bại.

**Bài 7 — Timeout:** cấu hình scope timeout hai giây. Tạo một subtask chậm, quan sát cancellation và cách xử lý StructuredTaskScope.TimeoutException.

**Bài 8 — ScopedValue:** bind request ID trước khi mở scope. Đọc request ID từ hai subtask và xác nhận context được kế thừa.

**Bài 9 — Scope lồng nhau:** tạo một subtask mở scope con để gọi hai dependency khác. Quan sát cấu trúc cha-con trong thread dump.

**Bài 10 — Giới hạn fan-out:** tạo workload gọi nhiều dependency. Thêm semaphore/bulkhead để giới hạn concurrency và đo throughput/latency.

**Bài 11 — So sánh API:** viết cùng một bài toán bằng ExecutorService và StructuredTaskScope. So sánh cancellation, error propagation và vị trí quản lý vòng đời.

**Bài 12 — Nâng cấp JDK:** so sánh JDK 25 preview với JDK 27 preview hoặc JDK 28 early-access. Ghi lại các khác biệt API và cập nhật code theo Javadoc tương ứng.

## 20. Checklist hoàn thành

- [ ] Giải thích Structured Concurrency là gì và vấn đề vòng đời nó giải quyết.
- [ ] Biết Java 25 dùng JEP 505, preview lần thứ năm.
- [ ] Dùng đúng StructuredTaskScope.open() thay cho constructor/API cũ.
- [ ] Dùng fork() để tạo subtask và join() để phối hợp.
- [ ] Đọc kết quả bằng Subtask.get() sau khi join thành công.
- [ ] Hiểu chính sách mặc định và các Joiner có sẵn.
- [ ] Biết khi nào dùng awaitAllSuccessfulOrThrow, allSuccessfulOrThrow, anySuccessfulResultOrThrow và awaitAll.
- [ ] Hiểu FailedException, timeout và cancellation trong Java 25.
- [ ] Biết chỉ owner thread được fork/join/close.
- [ ] Dùng try-with-resources để đóng scope.
- [ ] Viết subtask phản hồi interruption và giải phóng tài nguyên.
- [ ] Hiểu close chờ thread con kết thúc và cancellation không phải cưỡng chế dừng.
- [ ] Không xem cancellation là rollback transaction hoặc side effect.
- [ ] Biết virtual threads là mặc định nhưng không tự giới hạn concurrency.
- [ ] Cấu hình tên scope, ThreadFactory và timeout khi cần.
- [ ] Hiểu ScopedValue bindings được kế thừa vào các subtask.
- [ ] Biết bật preview ở cả compile time và runtime của JDK 25.
- [ ] Nhận biết API khác nhau giữa JDK 25, 26, 27 và JDK 28.
- [ ] Có chiến lược kiểm thử failure, timeout, interruption và nâng cấp.

## Tài liệu tham khảo chính thức

- [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): thiết kế và trạng thái preview trong JDK 25.
- [Java SE 25 — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): API open, fork, join, close, ownership và exception.
- [Java SE 25 — StructuredTaskScope.Joiner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): các policy có sẵn và cách triển khai Joiner.
- [Java SE 25 — StructuredTaskScope.Configuration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html): cấu hình ThreadFactory, tên scope và timeout.
- [Java SE 25 — ScopedValue.Carrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html): bind scoped values bằng run() hoặc call() và cách exception được truyền ra caller.
- [Oracle Java 25 — Structured Concurrency](https://docs.oracle.com/en/java/javase/25/core/structured-concurrency.html): hướng dẫn sử dụng scope, Joiner và các ví dụ.
- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): context propagation và tích hợp với virtual threads/structured concurrency.
- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): các điều chỉnh trong JDK 26.
- [Oracle JDK 27 Release Notes — Structured Concurrency (Seventh Preview)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): trạng thái preview trong JDK 27.
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533): thay đổi API ở JDK 27.
- [JEP 543 — Structured Concurrency](https://openjdk.org/jeps/543): API final được tích hợp vào JDK 28.
- [OpenJDK review — Implement JEP 543](https://mail-archive.com/core-libs-dev%40openjdk.org/msg75715.html): xác nhận bỏ preview annotations và cập nhật @since cho JDK 28.

## Kết luận

**Structured Concurrency biến một nhóm tác vụ song song thành một đơn vị công việc có vòng đời và chính sách hoàn tất rõ ràng.** Trong Java 25, StructuredTaskScope cung cấp open, fork, join, close, Subtask và Joiner; mặc định, các subtask chạy trên virtual threads, lỗi có thể kích hoạt cancellation và scope không đóng trước khi các thread con kết thúc.

Khi áp dụng, hãy chọn Joiner đúng yêu cầu nghiệp vụ, viết subtask hợp tác với interruption, đặt timeout phù hợp và giới hạn fan-out theo năng lực của dependency. Nhớ rằng Structured Concurrency quản lý vòng đời thread, không tự rollback side effect hay giới hạn tài nguyên bên ngoài. API Java 25 vẫn là preview; JDK 27 tiếp tục preview lần thứ bảy, còn JEP 543 đã được tích hợp final vào JDK 28 early-access. **Dùng đúng API theo JDK mục tiêu và kiểm thử cancellation, lỗi, timeout trước khi đưa vào vận hành.**
