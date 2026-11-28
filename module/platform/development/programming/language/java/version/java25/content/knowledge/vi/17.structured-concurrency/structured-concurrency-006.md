# Xử lý tài nguyên và bảo đảm tác vụ con kết thúc khi đóng phạm vi

> **Chương:** Structured Concurrency
>
> **Phiên bản:** Java 25, JEP 505 — Structured Concurrency (Fifth Preview). Bài này tập trung vào vòng đời của `StructuredTaskScope`, thứ tự `fork`/`join`/`close`, hủy tác vụ, xử lý lỗi và giải phóng tài nguyên. API vẫn là preview trong JDK 25; cần bật preview khi biên dịch và chạy.

## 1. Vì sao vòng đời tác vụ con phải gắn với phạm vi?

Một request thường tách thành nhiều công việc độc lập: đọc hồ sơ, lấy đơn hàng, tải quyền truy cập hoặc gọi một dịch vụ khác. Nếu mỗi công việc chạy trên một thread nhưng không có quan hệ vòng đời rõ ràng với request cha, có thể xảy ra:

- Request đã trả lỗi hoặc timeout nhưng tác vụ con vẫn chạy.
- Một tác vụ thất bại trong khi các tác vụ còn lại tiếp tục giữ socket, file hoặc kết nối database.
- Code đọc kết quả khi tác vụ chưa hoàn tất.
- Exception bị thất lạc trong thread khác hoặc chỉ xuất hiện ở log.
- Tác vụ con sống lâu hơn dữ liệu/context mà nó đang sử dụng.

**Structured concurrency** tổ chức các tác vụ liên quan thành một đơn vị công việc có phạm vi rõ ràng. `StructuredTaskScope` tạo một ranh giới lexical: tác vụ con được fork trong scope và scope không đóng xong cho tới khi các thread con kết thúc.

Mục tiêu của bài thực hành là đảm bảo:

1. Scope luôn được đóng, kể cả khi code cha gặp exception.
2. Tác vụ con được chờ hoặc hủy theo một chính sách kết quả rõ ràng.
3. Khi scope đóng, không còn thread con nào tiếp tục chạy phía sau.
4. Mỗi tác vụ tự giải phóng tài nguyên mà nó sở hữu.
5. Timeout và interruption được truyền tới tác vụ con theo cách có thể xử lý.

## 2. Trạng thái API trong Java 25

`StructuredTaskScope` là **preview API** trong Java 25 theo JEP 505 (lần preview thứ năm). Đây không phải API final. Cần biên dịch và chạy bằng JDK 25 với preview được bật:

~~~bash
javac --release 25 --enable-preview -d out src/main/java/example/ReportService.java
java --enable-preview -cp out example.ReportService
~~~

Nếu dùng Maven hoặc Gradle, cấu hình compiler và test/runtime task để truyền `--enable-preview`; tất cả môi trường chạy chương trình cũng phải dùng JDK 25 tương ứng. Preview bytecode của JDK 25 không phải bytecode có thể mang sang JDK khác để chạy mà không biên dịch lại.

**Phạm vi áp dụng hiện tại:** JDK 26 tiếp tục preview Structured Concurrency theo JEP 525 (lần preview thứ sáu). Vì API preview có thể thay đổi giữa các bản phát hành, ví dụ và chữ ký API trong bài này dành cho JDK 25. Ví dụ, overload `open(joiner, configFunction)` trong JDK 25 nhận `Function<Configuration, Configuration>`, trong khi JDK 26 đổi tham số cấu hình thành `UnaryOperator<Configuration>`. Khi nâng cấp JDK, phải đọc Javadoc của đúng phiên bản và biên dịch lại. Không sao chép các ví dụ cũ từ những preview ban đầu.

### Những API cũ không dùng trong Java 25

Các ví dụ từ những phiên bản preview trước có thể dùng constructor hoặc lớp chính sách như `new StructuredTaskScope.ShutdownOnFailure()` và `new StructuredTaskScope.ShutdownOnSuccess<>()`, cùng `throwIfFailed()`. Mô hình đó không còn là API Java 25 trong JEP 505. Java 25 dùng các factory `StructuredTaskScope.open(...)` và `StructuredTaskScope.Joiner`.

## 3. Vòng đời chuẩn của một scope

`StructuredTaskScope` được thiết kế để dùng với `try`-with-resources:

~~~text
Mở scope
   |
   v
Fork các subtask
   |
   v
Join một lần để nhận outcome
   |
   v
Đọc kết quả sau join
   |
   v
Đóng scope tự động
   |
   v
Hủy phần việc còn lại (nếu có), chờ mọi thread con kết thúc
~~~

Một scope có **owner thread** là thread gọi `StructuredTaskScope.open()`. Chỉ owner mới được gọi `fork`, `join` và `close`. Các quy tắc chính:

- Có thể gọi `fork` nhiều lần trước khi `join`.
- Không gọi `fork` sau khi đã `join`.
- `join` chỉ được gọi một lần.
- Sau `join`, owner mới được đọc kết quả qua `Subtask.get()` hoặc `Subtask.exception()`.
- `close` được gọi tự động khi ra khỏi `try`-with-resources.
- Nếu đã fork subtask mà thoát block trước khi thử `join`, `close` vẫn đóng scope, hủy/chờ tác vụ con rồi ném `IllegalStateException`.

`open()` mặc định tạo virtual thread không tên cho mỗi subtask, dùng chính sách chờ tất cả subtask thành công hoặc dừng khi một subtask thất bại. Scope mặc định không có timeout.

## 4. Ví dụ cơ bản: lấy dữ liệu song song và đóng scope đúng cách

Giả sử một trang dashboard cần hồ sơ người dùng, đơn hàng gần đây và cảnh báo. Ba lời gọi độc lập có thể chạy song song:

~~~java
import java.util.concurrent.StructuredTaskScope;

record Dashboard(
        UserProfile profile,
        OrderSummary orders,
        AlertSummary alerts) {}

final class DashboardService {

    private final UserService userService;
    private final OrderService orderService;
    private final AlertService alertService;

    DashboardService(
            UserService userService,
            OrderService orderService,
            AlertService alertService) {
        this.userService = userService;
        this.orderService = orderService;
        this.alertService = alertService;
    }

    Dashboard load(String userId) throws InterruptedException {
        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(() -> userService.fetch(userId));
            var orders = scope.fork(() -> orderService.fetchRecent(userId));
            var alerts = scope.fork(() -> alertService.fetch(userId));

            // Chờ theo policy mặc định: tất cả thành công hoặc một tác vụ lỗi.
            scope.join();

            // Chỉ đọc Subtask sau khi join hoàn tất.
            return new Dashboard(
                    profile.get(),
                    orders.get(),
                    alerts.get());
        }
    }
}
~~~

Nếu cả ba thành công, `join()` hoàn tất bình thường và owner đọc kết quả. Nếu một subtask thất bại, chính sách mặc định hủy scope, interrupt các subtask chưa xong và `join()` ném `StructuredTaskScope.FailedException`.

Khi method trả về, `try`-with-resources gọi `close()`. Vì vậy, thread thực thi các subtask không thể tiếp tục chạy sau khi scope đóng xong.

## 5. close() thực sự làm gì?

`close()` không chỉ đánh dấu scope là đã đóng. Theo hợp đồng Java 25, nó:

1. Hủy scope nếu scope chưa bị hủy.
2. Ngăn không cho fork thêm subtask.
3. Interrupt các thread đang chạy subtask chưa hoàn tất.
4. Chờ tất cả thread con kết thúc.
5. Chỉ sau đó mới cho owner tiếp tục ra khỏi phạm vi.

Điều này tạo bảo đảm quan trọng: **không có subtask nào thuộc scope còn chạy sau khi `close()` hoàn tất**.

### Nếu owner bị interrupt trong lúc close?

Nếu owner bị interrupt trong khi `close()` đang chờ thread con, `close()` vẫn tiếp tục chờ cho tới khi tất cả thread con kết thúc. Sau khi hoàn tất, trạng thái interrupt của owner được đặt lại. Cơ chế này ưu tiên không để thread con vượt khỏi vòng đời của scope.

### Close không thể ép một tác vụ dừng tức thì

`interrupt` là tín hiệu yêu cầu tác vụ hợp tác dừng. Nếu subtask:

- Nuốt `InterruptedException` rồi tiếp tục vòng lặp.
- Chặn trong API không phản hồi interruption.
- Chờ native call hoặc thao tác I/O không có timeout.
- Chạy vòng lặp CPU vô hạn mà không kiểm tra interrupt.

thì `close()` có thể phải chờ rất lâu, thậm chí không kết thúc. Vì vậy, trách nhiệm của code subtask là phản hồi interruption và giải phóng tài nguyên.

## 6. Viết subtask có thể hủy an toàn

Không được coi interrupt là exception cần bỏ qua. Với một tác vụ dài, kiểm tra interruption tại các điểm hợp lý:

~~~java
static SearchResult search(Index index, Query query)
        throws InterruptedException {
    var results = new ArrayList<Document>();

    for (var partition : index.partitions()) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Search cancelled");
        }

        results.addAll(index.search(partition, query));
    }

    return new SearchResult(results);
}
~~~

Nếu API đang gọi ném `InterruptedException`, thường nên để exception truyền lên để subtask kết thúc. Nếu bắt exception để cleanup trước, phải khôi phục trạng thái interrupt hoặc ném lại:

~~~java
try {
    return blockingOperation();
} catch (InterruptedException e) {
    cleanupLocalState();
    Thread.currentThread().interrupt();
    throw e;
}
~~~

Không dùng `Thread.interrupted()` để kiểm tra một cách vô thức trong nhiều tầng: phương thức này đọc và xóa trạng thái interrupt. Nếu chỉ cần kiểm tra, `isInterrupted()` giữ nguyên trạng thái.

Với tác vụ CPU-bound, đặt điểm kiểm tra interruption trong vòng lặp hoặc giữa các batch. Với network/database client, cấu hình connect/read/query timeout và dùng API có thể hủy nếu thư viện hỗ trợ.

## 7. Giải phóng tài nguyên ngay trong subtask

Scope quản lý vòng đời thread, không tự đóng mọi tài nguyên mà thread sử dụng. Mỗi subtask phải đóng tài nguyên nó sở hữu bằng `try`-with-resources:

~~~java
static ParsedDocument parse(Path path) throws IOException {
    try (var input = Files.newInputStream(path);
         var reader = new BufferedReader(
                 new InputStreamReader(input, StandardCharsets.UTF_8))) {
        return parseDocument(reader);
    }
}

static ParsedDocument parseInSubtask(Path path) throws IOException {
    // Tài nguyên được đóng cả khi parse thành công hoặc bị lỗi.
    return parse(path);
}
~~~

Nếu scope bị hủy trong lúc đọc, hãy dùng API I/O phù hợp và đặt timeout/điều kiện hủy. `try`-with-resources trong subtask vẫn chạy khi stack unwind do exception, nhờ đó đóng stream, statement hoặc response body mà subtask đang sở hữu.

### Quy tắc sở hữu tài nguyên

| Tài nguyên | Nơi nên sở hữu và đóng |
| --- | --- |
| File stream mở riêng cho một subtask | Chính subtask đó, trong `try`-with-resources. |
| HTTP response/body của một request con | Subtask gọi HTTP client, đóng body sau khi đọc. |
| JDBC connection/statement/result set riêng | Subtask hoặc transaction boundary sở hữu chúng. |
| Tài nguyên dùng chung giữa nhiều subtask | Một owner rõ ràng; đồng bộ truy cập và chỉ đóng sau khi scope đã join/close. |
| Tài nguyên cấp request cha | Request cha đóng sau khi scope kết thúc. |

Không trả về từ subtask một stream, cursor hoặc response body vẫn phụ thuộc vào tài nguyên đã đóng trong subtask. Nếu owner cần dữ liệu sau `join`, subtask nên trả về giá trị đã materialize hoặc một đối tượng có ownership được định nghĩa rõ.

## 8. Hủy nhanh khi một subtask thất bại

`StructuredTaskScope.open()` dùng chính sách mặc định `Joiner.awaitAllSuccessfulOrThrow()`. Nếu một subtask thất bại, joiner hủy scope và `join()` ném `FailedException` với exception từ subtask thất bại làm cause.

~~~java
try (var scope = StructuredTaskScope.open()) {
    var customer = scope.fork(() -> customerService.find(customerId));
    var account = scope.fork(() -> accountService.load(customerId));
    var risk = scope.fork(() -> riskService.evaluate(customerId));

    scope.join();

    return new CustomerView(
            customer.get(),
            account.get(),
            risk.get());
} catch (StructuredTaskScope.FailedException e) {
    Throwable cause = e.getCause();
    throw new CustomerLoadException("Cannot load customer view", cause);
}
~~~

Nếu `riskService.evaluate` thất bại, các subtask còn đang chạy sẽ nhận interrupt. Khi `close()` hoàn tất, tất cả thread con đã kết thúc. Exception vẫn được truyền về owner để xử lý ở boundary phù hợp.

Không bắt mọi exception trong subtask rồi trả `null` chỉ để tránh `FailedException`. Chỉ chuyển lỗi thành fallback khi fallback là một phần hợp đồng nghiệp vụ, ví dụ phần gợi ý có thể thiếu mà dashboard vẫn hợp lệ.

## 9. Chọn chính sách hoàn tất bằng Joiner

Java 25 dùng `StructuredTaskScope.Joiner` để định nghĩa khi nào scope hoàn tất và `join()` trả về gì:

| Joiner | Khi nào `join()` hoàn tất | Kết quả |
| --- | --- | --- |
| `awaitAllSuccessfulOrThrow()` | Tất cả thành công hoặc có một subtask lỗi | `null`; lỗi đầu tiên làm hủy scope và được ném qua `FailedException`. |
| `allSuccessfulOrThrow()` | Tất cả thành công hoặc có một subtask lỗi | Stream các `Subtask` thành công theo thứ tự fork; lỗi làm hủy scope. |
| `anySuccessfulResultOrThrow()` | Có một subtask thành công đầu tiên hoặc tất cả đều lỗi | Giá trị của subtask thành công đầu tiên; nếu tất cả lỗi thì ném `FailedException`. |
| `awaitAll()` | Tất cả subtask kết thúc | Không tự hủy scope và không ném lỗi subtask; owner có thể kiểm tra từng `Subtask`. |

Ví dụ cần kết quả đầu tiên thành công:

~~~java
Product findFromReplicas(String productId)
        throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<Product>anySuccessfulResultOrThrow())) {

        scope.fork(() -> replicaA.find(productId));
        scope.fork(() -> replicaB.find(productId));
        scope.fork(() -> replicaC.find(productId));

        // Khi một replica trả kết quả thành công, các tác vụ còn lại bị hủy.
        return scope.join();
    }
}
~~~

Chỉ dùng `anySuccessfulResultOrThrow()` khi các kết quả có cùng kiểu và một kết quả thành công là đủ. Với các tác vụ có kiểu trả về khác nhau, dùng `awaitAllSuccessfulOrThrow()` rồi đọc từng `Subtask.get()` sau join.

### Khi cần thu thập tất cả outcome kể cả lỗi

`awaitAll()` đợi mọi subtask kết thúc nhưng không tự hủy khi có lỗi. Sau join, owner có thể xem `Subtask.state()` và `Subtask.exception()` để quyết định cách tổng hợp:

~~~java
try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.<Result>awaitAll())) {
    var first = scope.fork(this::readFirst);
    var second = scope.fork(this::readSecond);

    scope.join();

    if (first.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
        consume(first.get());
    } else {
        logFailure(first.exception());
    }

    if (second.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
        consume(second.get());
    } else {
        logFailure(second.exception());
    }
}
~~~

Không gọi `get()` trên subtask thất bại hoặc chưa hoàn tất. `get()` và `exception()` chỉ được owner gọi sau khi `join()` đã hoàn tất và state tương ứng hợp lệ.

## 10. Đặt timeout cho cả scope

Java 25 cho phép đặt timeout khi mở scope bằng `Configuration.withTimeout(Duration)`. Timeout bắt đầu tính từ lúc scope được mở, không phải từ thời điểm gọi `join()`.

~~~java
Dashboard loadWithDeadline(String userId)
        throws InterruptedException {
    var joiner = StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow();
    var timeout = Duration.ofMillis(800);

    try (var scope = StructuredTaskScope.open(
            joiner,
            configuration -> configuration.withTimeout(timeout))) {

        var profile = scope.fork(() -> userService.fetch(userId));
        var orders = scope.fork(() -> orderService.fetchRecent(userId));
        var alerts = scope.fork(() -> alertService.fetch(userId));

        scope.join();

        return new Dashboard(profile.get(), orders.get(), alerts.get());
    } catch (StructuredTaskScope.TimeoutException e) {
        throw new DashboardTimeoutException("Dashboard deadline exceeded", e);
    }
}
~~~

Khi timeout hết trước hoặc trong lúc `join()` chờ, scope bị hủy, thread con chưa xong nhận interrupt và `join()` ném `StructuredTaskScope.TimeoutException`.

### Timeout của scope không thay thế timeout của I/O

Timeout scope là deadline cho đơn vị công việc. Nó không bảo đảm mọi API bên trong tự động dừng ngay lập tức. Hãy kết hợp:

- Timeout của HTTP connect/read/request.
- Query timeout hoặc cancellation API của database driver.
- Interruption check trong vòng lặp CPU-bound.
- Cleanup trong `finally` hoặc `try`-with-resources.

Nếu một native call hoặc thư viện không phản hồi interrupt, scope vẫn phải chờ thread đó kết thúc trong `close()`. Đừng đặt timeout ngắn rồi giả định tài nguyên đã được giải phóng ngay tại thời điểm timeout.

## 11. Xử lý interruption của owner

`join()` ném `InterruptedException` nếu owner bị interrupt trong lúc chờ. Khi đó, scope vẫn được đóng do `try`-with-resources; `close()` hủy các subtask còn lại và chờ chúng kết thúc.

~~~java
Result runTasks() throws InterruptedException {
    try (var scope = StructuredTaskScope.open()) {
        var a = scope.fork(this::taskA);
        var b = scope.fork(this::taskB);

        scope.join();
        return new Result(a.get(), b.get());
    }
}
~~~

Nếu tầng gọi muốn chuyển interruption thành trạng thái hủy của request, có thể để `InterruptedException` truyền lên hoặc xử lý tại boundary:

~~~java
try {
    return service.runTasks();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new RequestCancelledException(e);
}
~~~

Chỉ khôi phục interrupt status khi tầng hiện tại đã bắt và không tiếp tục truyền `InterruptedException`. Không biến interruption thành kết quả thành công giả.

## 12. Scope lồng nhau và thứ tự đóng

Một subtask có thể mở scope con để chia tiếp công việc. Cấu trúc này tạo cây tác vụ:

~~~text
Request scope
├── Load profile
└── Load recommendations
    ├── Query catalog
    └── Query ranking
~~~

Mỗi scope con phải được đóng trước khi subtask cha hoàn tất. `try`-with-resources tạo thứ tự đóng ngược với thứ tự mở:

~~~java
Recommendation loadRecommendations(String userId)
        throws InterruptedException {
    try (var child = StructuredTaskScope.open()) {
        var catalog = child.fork(() -> catalogService.find(userId));
        var ranking = child.fork(() -> rankingService.rank(userId));

        child.join();
        return new Recommendation(catalog.get(), ranking.get());
    }
}
~~~

Khi subtask `loadRecommendations` kết thúc, scope con đã đóng. Scope cha chỉ thấy một kết quả của subtask; nó không cần quản lý trực tiếp các thread cháu. Không để scope con thoát khỏi lexical lifetime của subtask cha.

## 13. Chia sẻ ScopedValue với tác vụ con

Khi `StructuredTaskScope` được mở, nó chụp các binding `ScopedValue` đang có trên owner thread. Các subtask được fork trong scope kế thừa binding đó. Đây là cách phù hợp để chia sẻ request context bất biến mà không phải truyền thủ công qua mọi tham số.

~~~java
static final ScopedValue<RequestContext> REQUEST =
        ScopedValue.newInstance();

Response handle(RequestContext context) throws InterruptedException {
    return ScopedValue.where(REQUEST, context).call(() -> {
        try (var scope = StructuredTaskScope.open()) {
            var a = scope.fork(() -> serviceA.load(REQUEST.get()));
            var b = scope.fork(() -> serviceB.load(REQUEST.get()));
            scope.join();
            return new Response(a.get(), b.get());
        }
    });
}
~~~

Các binding tại thời điểm `open()` được chụp cho scope. Khi fork, binding hiện hành phải khớp với binding đã chụp; nếu không, API có thể ném `StructureViolationException`. Quy tắc này ngăn tác vụ con kế thừa một binding sẽ bị tháo trước khi tác vụ con hoàn tất.

Giá trị được chia sẻ giữa nhiều thread nên là immutable hoặc phải có đồng bộ thích hợp. `ScopedValue` không làm một object mutable trở nên thread-safe.

## 14. Những lỗi quản lý vòng đời thường gặp

| Cách làm sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mở scope nhưng không dùng `try`-with-resources | Scope có thể không được đóng trên mọi nhánh exception | Dùng lexical scope và tự động gọi `close()`. |
| Fork rồi thoát block mà không gọi `join()` | Scope bị đóng/hủy, sau đó `close()` ném `IllegalStateException` | Gọi `join()` một lần sau giai đoạn fork. |
| Gọi `Subtask.get()` trước `join()` | Kết quả chưa sẵn sàng và API từ chối truy cập | Chờ `join()` rồi mới đọc. |
| Gọi `fork()` sau `join()` | Vi phạm lifecycle của scope | Hoàn tất toàn bộ fork trước join. |
| Gọi `join()` từ thread khác | Vi phạm owner-thread rule | Chỉ owner mở scope mới fork/join/close. |
| Nuốt `InterruptedException` trong subtask | `close()` có thể chờ rất lâu | Dọn tài nguyên, giữ interrupt hoặc ném lại để kết thúc. |
| Dùng API I/O không có timeout | Task có thể không phản hồi interrupt | Đặt timeout/cancellation ở client hoặc driver. |
| Chia sẻ stream/cursor mà không có owner | Có thể đóng quá sớm hoặc rò rỉ tài nguyên | Xác định một owner; đóng tại đúng boundary. |
| Coi timeout là lệnh kill thread | Thread có thể vẫn đang chạy | Thiết kế cooperative cancellation và cleanup. |
| Dùng constructor `ShutdownOnFailure` từ preview cũ | Không khớp API Java 25 | Dùng `open(Joiner...)` của JEP 505. |

## 15. Bài tập thực hành

### Bài A — Đảm bảo scope luôn đóng

Tạo hai subtask đọc dữ liệu từ hai nguồn. Cho một subtask ném exception có chủ đích.

**Điều kiện đạt:** `join()` báo lỗi, subtask còn lại nhận interruption, tài nguyên của nó được đóng và method cha không trả về trước khi thread con kết thúc.

### Bài B — Chứng minh close chờ tác vụ con

Tạo một subtask dùng `try`-with-resources để mở tài nguyên test. Khi subtask nhận interrupt, ghi nhận cleanup trong `finally` rồi kết thúc.

**Điều kiện đạt:** xác minh cleanup hoàn tất trước khi code sau `try`-with-resources của scope chạy.

### Bài C — Timeout và I/O cancellation

Đặt `withTimeout(Duration.ofMillis(...))`, gọi một HTTP endpoint test có độ trễ dài hơn deadline.

**Điều kiện đạt:** scope ném `TimeoutException`, client request được hủy hoặc timeout theo cấu hình của HTTP client, response body được đóng và không còn tác vụ con chạy nền.

### Bài D — So sánh Joiner

Chạy cùng bộ tác vụ với `awaitAllSuccessfulOrThrow()`, `anySuccessfulResultOrThrow()` và `awaitAll()`.

**Điều kiện đạt:** mô tả chính xác khi nào scope hủy sibling, kiểu kết quả `join()` và cách owner đọc trạng thái subtask.

### Bài E — Scope lồng nhau

Tạo request scope có một subtask mở child scope với hai tác vụ cháu.

**Điều kiện đạt:** child scope kết thúc trước khi subtask cha hoàn tất; không còn thread cháu chạy sau khi request scope đóng.

## 16. Checklist trước khi đưa vào ứng dụng

- [ ] Dùng đúng JDK 25 và bật preview khi compile lẫn runtime.
- [ ] Mở scope bằng `StructuredTaskScope.open(...)` trong `try`-with-resources.
- [ ] Chỉ owner thread gọi `fork`, `join`, `close`.
- [ ] Hoàn tất giai đoạn fork trước khi gọi `join()` đúng một lần.
- [ ] Chỉ đọc `Subtask.get()` hoặc `exception()` sau khi join.
- [ ] Chọn `Joiner` theo chính sách nghiệp vụ: tất cả thành công, bất kỳ thành công hay đợi tất cả.
- [ ] Đặt timeout của scope và timeout I/O phù hợp cùng deadline request.
- [ ] Mỗi subtask đóng stream, response, statement và tài nguyên riêng của nó.
- [ ] Subtask phản hồi interruption và không nuốt `InterruptedException`.
- [ ] Không giả định `close()` có thể ép dừng một native call hoặc API không interruptible.
- [ ] Scope con đóng trước khi subtask cha hoàn tất.
- [ ] Giá trị `ScopedValue` chia sẻ là immutable hoặc có đồng bộ.
- [ ] Đọc Javadoc và biên dịch lại khi nâng cấp JDK vì Structured Concurrency vẫn là preview.

## 17. Tài liệu tham khảo

1. [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): trạng thái và thiết kế API trong JDK 25.
2. [Java SE 25 — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): `open`, `fork`, `join`, `close`, owner thread, cancellation và timeout.
3. [Java SE 25 — StructuredTaskScope.Joiner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): các chính sách hoàn tất và cách tổng hợp outcome.
4. [Java SE 25 — StructuredTaskScope.Configuration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html): timeout, thread factory và tên scope.
5. [Oracle Java 25 — Structured Concurrency](https://docs.oracle.com/en/java/javase/25/core/structured-concurrency.html): quy trình mở scope, fork, join, xử lý kết quả và đóng scope.
6. [Oracle Java 25 — javac command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): tùy chọn `--enable-preview` kết hợp `--release`.
7. [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): thay đổi preview tiếp theo trong JDK 26, nhắc lại rằng API vẫn có thể thay đổi.

**Ghi nhớ:** `join()` xác định outcome; `close()` bảo đảm vòng đời. Khi scope đóng, các tác vụ chưa xong bị interrupt và owner chờ chúng kết thúc. Bảo đảm đó chỉ hữu ích nếu mỗi subtask phản hồi interruption và tự đóng tài nguyên của nó. Dùng `try`-with-resources, timeout có chủ đích và ownership rõ ràng để không để thread hoặc tài nguyên vượt khỏi request đã tạo ra chúng.
