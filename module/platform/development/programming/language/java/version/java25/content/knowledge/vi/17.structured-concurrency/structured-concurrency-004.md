# Phối hợp join, hủy tác vụ, ngắt luồng và thời hạn thực thi

## 1. Bối cảnh và trạng thái API

Bài thuộc chương **Structured Concurrency** của module **JAVA_VERSION_JAVA25**. Structured Concurrency giúp nhóm các tác vụ con có quan hệ với nhau thành một đơn vị công việc. Thay vì tạo thread hoặc submit task rồi tự quản lý nhiều `Future`, code mở một scope, fork các tác vụ, join theo một chính sách và đóng scope trong cùng một cấu trúc `try`-with-resources.

Trong một request tổng hợp, ứng dụng có thể cần gọi đồng thời profile service, inventory service và recommendation service. Các tác vụ này thuộc cùng một thao tác nghiệp vụ: kết quả chỉ có ý nghĩa khi request cha quyết định cách phối hợp, xử lý lỗi và kết thúc chúng. Structured Concurrency làm rõ quan hệ cha-con và vòng đời đó.

**Trạng thái phiên bản cần nhớ:**

- **JDK 25 — JEP 505, Structured Concurrency (Fifth Preview):** API `StructuredTaskScope` vẫn là preview. Cần bật preview khi biên dịch và chạy.
- **JDK 26 — JEP 525, Sixth Preview:** API tiếp tục được điều chỉnh.
- **JDK 27 — JEP 533, Seventh Preview:** tính năng vẫn là preview; API tiếp tục thay đổi so với JDK 25.

Do đó, các ví dụ mã trong bài được viết chính xác cho **JDK 25**. Khi dùng JDK 26/27, đọc Javadoc và JEP của phiên bản đích, rồi cập nhật mã theo API preview của release đó. Không coi API này là API ổn định chỉ vì nó đã xuất hiện qua nhiều vòng preview.

Trong JDK 25, cách dùng hiện hành là `StructuredTaskScope.open(...)`, `fork(...)`, `join()`, `Joiner` và `close()`. Không sao chép các ví dụ từ những vòng preview cũ có kiểu API hoặc chính sách scope đã thay đổi.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vòng đời owner → scope → subtasks → join → close.
2. Chọn chính sách join phù hợp với yêu cầu nghiệp vụ.
3. Hiểu khi nào một lỗi làm hủy các tác vụ anh em.
4. Phân biệt hủy scope với ngắt thread và kết thúc tác vụ thực tế.
5. Viết tác vụ con phản hồi interrupt đúng cách.
6. Thiết lập timeout/deadline cho cả nhóm tác vụ.
7. Xử lý `InterruptedException`, `FailedException` và `TimeoutException`.
8. Hiểu vì sao `close()` có thể chờ lâu nếu tác vụ không hợp tác.
9. Kết hợp `StructuredTaskScope` với virtual threads và `ScopedValue`.
10. Biết khi nào nên dùng structured concurrency và khi nào một background job độc lập phù hợp hơn.

## 2. Từ task rời rạc sang một cây công việc

### 2.1. Vấn đề khi tự quản lý nhiều Future

Một cách triển khai quen thuộc là submit nhiều task vào executor rồi tự chờ kết quả:

~~~java
Future<Profile> profile = executor.submit(() -> loadProfile(userId));
Future<List<Order>> orders = executor.submit(() -> loadOrders(userId));

try {
    return new Dashboard(profile.get(), orders.get());
} catch (ExecutionException e) {
    profile.cancel(true);
    orders.cancel(true);
    throw new DashboardException(e.getCause());
}
~~~

Đoạn mã trên có thể chạy, nhưng caller phải tự phối hợp nhiều chi tiết:

- Nếu một task lỗi, các task còn lại phải được hủy ở mọi nhánh xử lý.
- Phải chờ hoặc dọn các task đã submit.
- Phải xử lý timeout và interruption cho từng Future.
- Phải tránh quên cancel khi một nhánh ném exception.
- Phải bảo đảm các task không tiếp tục chạy vô chủ sau khi request kết thúc.

Structured Concurrency đưa các trách nhiệm này vào một scope có vòng đời rõ ràng. Các tác vụ con vẫn có thể chạy đồng thời, nhưng chúng thuộc về một thao tác cha và phải được xử lý trước khi scope đóng.

### 2.2. Cấu trúc một scope

~~~mermaid
flowchart TD
    R["Request / tác vụ cha"] --> O["Mở StructuredTaskScope"]
    O --> F1["fork: load profile"]
    O --> F2["fork: load orders"]
    O --> F3["fork: load recommendations"]
    F1 --> J["join theo Joiner policy"]
    F2 --> J
    F3 --> J
    J -->|Thành công theo policy| V["Đọc / tổng hợp kết quả"]
    J -->|Lỗi, timeout hoặc short-circuit| C["Hủy scope và interrupt task còn chạy"]
    V --> X["close"]
    C --> X
    X --> D["Các task con đã kết thúc"]
~~~

Một scope có các thành phần:

- **Owner thread:** thread mở scope. Chỉ owner được gọi `fork`, `join` và `close`.
- **Subtask:** tác vụ được tạo bằng `scope.fork(...)`.
- **Joiner:** chính sách quyết định `join()` chờ điều gì và trả về kết quả nào.
- **Configuration:** cấu hình `ThreadFactory`, tên scope và timeout.
- **close():** đóng scope, hủy các task chưa xong và chờ tất cả thread con kết thúc.

Mặc định, `StructuredTaskScope.open()` tạo virtual thread cho mỗi subtask. Scope không tạo một thread pool cố định; nó dùng thread factory của cấu hình, mặc định là virtual-thread factory.

### 2.3. Quy tắc cấu trúc của JDK 25

| Quy tắc | Ý nghĩa |
| --- | --- |
| Scope có một owner | Thread mở scope phải là thread gọi `fork`, `join`, `close` |
| `fork` trước `join` | Không fork thêm sau khi đã gọi join |
| `join` chỉ gọi một lần | Một scope có một điểm phối hợp kết quả |
| Đọc kết quả sau join | `Subtask.get()` chỉ dùng sau join và khi task thành công |
| Scope phải được đóng | Thường dùng `try`-with-resources |
| `close` chờ task con kết thúc | Task con không được chạy vượt khỏi vòng đời scope |

Đây là những ràng buộc có chủ đích. Chúng giúp tránh việc một tác vụ con sống lâu hơn thao tác cha hoặc kết quả được đọc khi task chưa hoàn tất.

## 3. join: chờ theo chính sách thay vì chờ tùy ý

### 3.1. Chính sách mặc định

Ví dụ JDK 25:

~~~java
import java.util.concurrent.StructuredTaskScope;

record Dashboard(Profile profile, List<Order> orders) {}

Dashboard loadDashboard(String userId) throws InterruptedException {
    try (var scope = StructuredTaskScope.open()) {
        var profile = scope.fork(() -> loadProfile(userId));
        var orders = scope.fork(() -> loadOrders(userId));

        scope.join();

        return new Dashboard(profile.get(), orders.get());
    }
}
~~~

`open()` không tham số dùng chính sách mặc định `awaitAllSuccessfulOrThrow()`:

- Chờ các task con hoàn tất thành công.
- Nếu một task con thất bại, scope bị hủy.
- Các task con chưa hoàn tất bị interrupt.
- `join()` ném `StructuredTaskScope.FailedException`, với exception của task thất bại đầu tiên làm cause.
- Nếu tất cả thành công, `join()` trả `null`; kết quả riêng được đọc từ `Subtask.get()`.

`Subtask.get()` không phải cách chờ task. Hãy gọi `join()` trước, sau đó mới đọc kết quả.

### 3.2. Các Joiner có sẵn trong JDK 25

JDK 25 cung cấp các chính sách phổ biến sau:

| Joiner | `join()` trả về | Khi một task thất bại |
| --- | --- | --- |
| `awaitAllSuccessfulOrThrow()` | `null` sau khi tất cả thành công | Hủy scope và ném lỗi |
| `allSuccessfulOrThrow()` | Stream các `Subtask` khi tất cả thành công | Hủy scope và ném lỗi |
| `anySuccessfulResultOrThrow()` | Kết quả của task đầu tiên thành công | Nếu tất cả thất bại thì ném lỗi |
| `awaitAll()` | `null` khi tất cả task kết thúc | Không tự hủy scope và không ném lỗi từ task con |

Chọn Joiner theo ý nghĩa của kết quả:

- Dùng `awaitAllSuccessfulOrThrow()` khi các task có thể trả về các kiểu khác nhau và tất cả đều bắt buộc thành công.
- Dùng `allSuccessfulOrThrow()` khi các task trả cùng kiểu và cần một stream các subtask thành công.
- Dùng `anySuccessfulResultOrThrow()` khi chỉ cần kết quả đầu tiên thành công, ví dụ truy vấn nhiều replica.
- Dùng `awaitAll()` khi muốn chờ tất cả task kết thúc rồi tự đọc trạng thái từng task, kể cả khi có task lỗi.

### 3.3. allSuccessfulOrThrow() để thu thập kết quả cùng kiểu

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

List<String> loadNames(List<String> userIds) throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow())) {

        userIds.forEach(id -> scope.fork(() -> loadName(id)));

        return scope.join()
            .map(StructuredTaskScope.Subtask::get)
            .toList();
    }
}
~~~

`join()` trả về stream các `Subtask<String>` theo thứ tự fork khi tất cả thành công. Nếu một task thất bại, Joiner hủy scope và `join()` ném `FailedException`.

Đừng giữ hoặc tái sử dụng một đối tượng Joiner cho nhiều scope. Javadoc yêu cầu tạo Joiner mới cho mỗi scope; các callback của Joiner có thể được gọi đồng thời từ nhiều thread.

### 3.4. anySuccessfulResultOrThrow() cho chiến lược lấy kết quả đầu tiên

Ví dụ ứng dụng có hai replica cung cấp cùng dữ liệu:

~~~java
import java.util.concurrent.StructuredTaskScope;

Product findFromFastestReplica(String productId)
        throws InterruptedException {

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<Product>anySuccessfulResultOrThrow())) {

        scope.fork(() -> eastReplica.find(productId));
        scope.fork(() -> westReplica.find(productId));

        return scope.join();
    }
}
~~~

Khi một replica trả kết quả thành công, Joiner kết thúc sớm, hủy scope và interrupt replica còn lại. Nếu tất cả replica đều thất bại, `join()` ném `FailedException`.

Cách này hữu ích cho:

- Đọc từ các replica tương đương.
- Gọi nhiều nguồn dự phòng có cùng contract.
- Chọn kết quả hợp lệ đầu tiên khi không cần kết quả của các nguồn còn lại.

Không dùng nó nếu mỗi task tạo ra một phần dữ liệu bắt buộc phải tổng hợp. Việc hủy các task còn lại là hành vi đúng của chính sách “first successful result”.

### 3.5. awaitAll() khi cần xử lý từng trạng thái

`awaitAll()` đợi mọi task kết thúc nhưng không tự hủy scope khi có task thất bại. Sau join, owner có thể xem `Subtask.state()` và `Subtask.exception()`:

~~~java
try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.<String>awaitAll())) {

    var first = scope.fork(() -> fetchPrimary());
    var second = scope.fork(() -> fetchSecondary());

    scope.join();

    if (first.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
        use(first.get());
    } else if (first.state() == StructuredTaskScope.Subtask.State.FAILED) {
        logFailure(first.exception());
    }

    if (second.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
        use(second.get());
    } else if (second.state() == StructuredTaskScope.Subtask.State.FAILED) {
        logFailure(second.exception());
    }
}
~~~

Các trạng thái cần hiểu:

- `SUCCESS`: task hoàn tất bình thường; có thể gọi `get()` sau join.
- `FAILED`: task kết thúc bằng exception; có thể đọc `exception()` sau join.
- `UNAVAILABLE`: task chưa có kết quả khả dụng, ví dụ scope đã bị hủy trước khi task hoàn tất.

Dùng `awaitAll()` khi lỗi từng task là dữ liệu cần phân loại, hoặc khi các task chủ yếu tạo side effect đã được kiểm soát. Nếu nghiệp vụ yêu cầu mọi kết quả thành công, dùng Joiner có chính sách fail-fast rõ ràng.

## 4. Hủy tác vụ: scope cancellation và các tình huống kích hoạt

### 4.1. Hủy scope có nghĩa gì?

Khi scope bị hủy:

1. Scope ngăn việc bắt đầu thêm task con.
2. JVM gửi interrupt tới các thread đang chạy task chưa hoàn tất.
3. `join()` được đánh thức để trả kết quả hoặc ném exception theo Joiner.
4. `close()` vẫn đợi mọi thread con kết thúc.

Hủy scope không phải lệnh buộc thread dừng ngay lập tức. Java không cưỡng bức dừng một thread đang chạy mã ứng dụng. Tác vụ con phải nhận biết interrupt và tự kết thúc.

### 4.2. Các tình huống hủy thường gặp

| Nguyên nhân | Điều gì xảy ra |
| --- | --- |
| Một subtask thất bại với `awaitAllSuccessfulOrThrow()` mặc định | Scope hủy các subtask còn lại và `join()` ném `FailedException` |
| Một subtask thành công với `anySuccessfulResultOrThrow()` | Scope hủy các subtask chưa hoàn tất và `join()` trả kết quả thành công đầu tiên |
| Timeout của scope hết hạn | Scope bị hủy, task còn chạy nhận interrupt và `join()` ném `TimeoutException` |
| Owner rời block `try` trước khi join | `close()` hủy scope, interrupt task chưa xong và chờ chúng kết thúc |
| Owner gọi `close()` | Scope hủy task chưa xong rồi chờ mọi thread con kết thúc |

Không có một lời gọi `shutdown()` độc lập trong API JDK 25 để thay thế vòng đời trên. Chính sách Joiner, timeout và `close()` điều khiển việc hủy.

### 4.3. Kiểm tra scope đã bị hủy chưa

`scope.isCancelled()` cho biết scope đã bị hủy hoặc đang trong quá trình hủy:

~~~java
while (hasMoreWork()) {
    if (scope.isCancelled()) {
        break;
    }

    submitNextSubtask();
}
~~~

Cách kiểm tra này hữu ích khi owner có giai đoạn fork dài. Nếu một task đã khiến scope bị hủy hoặc timeout xảy ra, owner có thể ngừng tạo thêm việc.

`isCancelled()` không chứng minh tất cả task con đã kết thúc. Quá trình gửi interrupt và kết thúc task có thể vẫn đang diễn ra. `close()` mới là điểm đợi cho đến khi các thread con hoàn tất.

## 5. Interrupt: tác vụ con phải hợp tác với việc hủy

### 5.1. Interrupt là tín hiệu, không phải nút kill

Interrupt là cơ chế yêu cầu thread dừng hoặc thay đổi hoạt động hiện tại. Cách phản hồi tùy thuộc vào code và API đang gọi:

- `Thread.sleep`, `BlockingQueue.take` và nhiều thao tác blocking có thể ném `InterruptedException`.
- Vòng lặp CPU-bound cần chủ động kiểm tra interrupt.
- API I/O hoặc thư viện bên ngoài có thể không phản hồi interrupt ngay.
- Một tác vụ đang gọi remote service cần timeout ở HTTP/RPC client, vì interrupt của thread không đảm bảo remote server dừng xử lý.

Nếu task bỏ qua interrupt hoặc chặn vô thời hạn trong API không interruptible, scope có thể không đóng được trong thời gian mong muốn.

### 5.2. Viết vòng lặp CPU-bound có kiểm tra interrupt

~~~java
long calculateReport(List<Record> records) throws InterruptedException {
    long total = 0;

    for (Record record : records) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Report calculation cancelled");
        }

        total += calculateContribution(record);
    }

    return total;
}
~~~

Dùng `isInterrupted()` để kiểm tra mà không xóa interrupt status. `Thread.interrupted()` là phương thức static kiểm tra thread hiện tại và xóa status; không gọi nó tùy tiện nếu code chưa có kế hoạch xử lý tín hiệu.

Một vòng lặp lớn có thể kiểm tra theo batch để giảm chi phí kiểm tra, nhưng cần chọn khoảng batch sao cho tác vụ phản hồi đủ nhanh.

### 5.3. Không nuốt InterruptedException

Ví dụ sai:

~~~java
try {
    Thread.sleep(10_000);
} catch (InterruptedException ignored) {
    // Tiếp tục xử lý như chưa có gì xảy ra.
}
~~~

Khi `InterruptedException` được ném, interrupt status thường đã bị xóa. Nếu bỏ qua exception, task không còn phản hồi đúng yêu cầu hủy.

Nếu có thể truyền exception ra khỏi `Callable`, hãy để task kết thúc:

~~~java
Callable<Result> task = () -> {
    return blockingOperation(); // Có thể ném InterruptedException
};
~~~

Nếu buộc phải chuyển sang một API không khai báo checked exception, khôi phục interrupt status rồi kết thúc bằng một exception phù hợp:

~~~java
try {
    return blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new CancellationException("Task interrupted");
}
~~~

Không bắt `InterruptedException` rồi tiếp tục công việc bình thường. Nếu cần cleanup, dùng `finally` để đóng resource và sau đó cho interruption truyền ra ngoài.

### 5.4. Dùng timeout cho I/O bên ngoài

Một scope timeout không thể tự bảo đảm mọi socket, JDBC driver hoặc SDK bên ngoài dừng ngay khi thread bị interrupt.

Ví dụ với HTTP client, hãy cấu hình cả timeout của request:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofMillis(700))
    .GET()
    .build();

HttpResponse<String> response =
    httpClient.send(request, HttpResponse.BodyHandlers.ofString());
~~~

Timeout ở HTTP request giới hạn thời gian chờ của thao tác mạng theo cấu hình client. Scope timeout quản lý vòng đời nhóm task. Hai lớp này bổ sung cho nhau.

Với JDBC, kiểm tra query timeout/cancel behavior của driver. Với RPC, đặt deadline ở client và truyền remaining budget xuống service. Không dựa duy nhất vào interrupt nếu thư viện không cam kết phản hồi nó.

## 6. Deadline và timeout cho cả nhóm task

### 6.1. Cấu hình timeout trong JDK 25

JDK 25 cho phép mở scope với Joiner và một hàm cấu hình. `withTimeout(Duration)` đặt thời hạn cho scope:

~~~java
import java.time.Duration;
import java.util.concurrent.StructuredTaskScope;

Dashboard loadDashboard(String userId) throws InterruptedException {
    var joiner =
        StructuredTaskScope.Joiner.<Object>awaitAllSuccessfulOrThrow();

    try (var scope = StructuredTaskScope.open(
            joiner,
            config -> config.withTimeout(Duration.ofMillis(800)))) {

        var profile = scope.fork(() -> loadProfile(userId));
        var balance = scope.fork(() -> loadBalance(userId));

        scope.join();

        return new Dashboard(profile.get(), balance.get());
    }
}
~~~

Trong ví dụ, `Object` là kiểu kết quả chung cho Joiner để hai task có thể trả về kiểu khác nhau. Mỗi biến `profile` và `balance` vẫn giữ kiểu `Subtask<Profile>` hoặc `Subtask<Balance>` tương ứng.

Khi timeout hết hạn trước khi scope join xong:

- Scope bị hủy.
- Các task con chưa hoàn tất nhận interrupt.
- `join()` ném `StructuredTaskScope.TimeoutException`.
- Khi thoát block, `close()` chờ các task con thực sự kết thúc.

### 6.2. Timeout bắt đầu khi mở scope

Timeout của `StructuredTaskScope` bắt đầu tính từ lúc gọi `open(...)`, không phải chỉ từ lúc bắt đầu `join()`.

Vì vậy ngân sách thời gian bao gồm:

- Thời gian tạo scope.
- Giai đoạn fork các subtask.
- Thời gian chờ trong join.

Nếu code thực hiện nhiều công việc trước khi gọi `join()`, phần đó vẫn tiêu thụ deadline. Đây là lý do không nên mở scope quá sớm rồi thực hiện một giai đoạn chuẩn bị dài trước khi fork.

### 6.3. Xử lý timeout và lỗi

~~~java
Dashboard loadDashboard(String userId) throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<Object>awaitAllSuccessfulOrThrow(),
            config -> config.withTimeout(Duration.ofMillis(800)))) {

        var profile = scope.fork(() -> loadProfile(userId));
        var balance = scope.fork(() -> loadBalance(userId));

        scope.join();
        return new Dashboard(profile.get(), balance.get());

    } catch (StructuredTaskScope.TimeoutException e) {
        throw new DashboardTimeoutException("Dashboard deadline exceeded", e);
    } catch (StructuredTaskScope.FailedException e) {
        throw new DashboardException("A dashboard subtask failed", e.getCause());
    }
}
~~~

`FailedException` đại diện cho outcome lỗi của Joiner. `TimeoutException` biểu thị deadline scope đã hết. `InterruptedException` biểu thị owner thread bị interrupt khi chờ join; ví dụ để exception truyền lên caller để caller quyết định hủy request.

Lưu ý thứ tự thực thi: khi một exception rời khỏi block `try`, Java gọi `close()` trước khi vào `catch`. Nếu một subtask không phản hồi interrupt, `close()` có thể tiếp tục chờ, vì thế `catch TimeoutException` không có nghĩa caller luôn nhận exception ngay tại thời điểm timeout.

### 6.4. Dùng deadline chung cho các lời gọi lồng nhau

Một request có thể gọi nhiều tầng dịch vụ. Nếu mỗi tầng tự đặt timeout mới mà không trừ thời gian đã dùng, tổng thời gian thực thi có thể vượt deadline của request.

Có thể tạo deadline tuyệt đối ở tầng cha và truyền ngân sách còn lại xuống các thao tác con:

~~~java
Instant deadline = Instant.now().plus(Duration.ofSeconds(2));

Duration remaining = Duration.between(Instant.now(), deadline);
if (remaining.isNegative() || remaining.isZero()) {
    throw new TimeoutException("Request deadline exceeded");
}
~~~

Đoạn trên minh họa cách tính remaining budget; khi đưa vào hệ thống, dùng clock phù hợp và kiểm tra deadline trước khi mở scope. Sau đó cấu hình timeout scope bằng thời gian còn lại và truyền cùng ngân sách cho HTTP/RPC/database client.

Không cộng lại toàn bộ timeout ban đầu ở mỗi tầng. Nếu request có ngân sách 2 giây, mỗi sub-operation phải dùng phần còn lại của ngân sách đó.

## 7. close(): bảo đảm task con không sống vượt scope

### 7.1. close luôn hủy task chưa hoàn tất rồi chờ

`StructuredTaskScope.close()` thực hiện hai việc theo thứ tự:

1. Hủy scope nếu chưa hủy, gửi interrupt tới các task con chưa hoàn tất.
2. Chờ tất cả thread con kết thúc.

Vì thế `close()` có thể chờ lâu nếu một task:

- Bỏ qua interrupt trong vòng lặp.
- Chặn ở API không interruptible.
- Chờ remote call không có timeout.
- Giữ lock trong khi không có đường thoát.
- Chạy cleanup không kết thúc.

Đây là hành vi có chủ đích: scope không cho phép task con tiếp tục chạy vô chủ sau khi block cha đã đóng.

### 7.2. Vì sao timeout không phải hard deadline cho toàn bộ process?

Giả sử timeout scope là 500 ms nhưng một task đang chờ thư viện native không phản hồi interrupt. Sau khi scope timeout:

- `join()` nhận `TimeoutException`.
- Scope gửi interrupt.
- `close()` đợi task kết thúc.
- Nếu task vẫn mắc kẹt, owner vẫn bị giữ trong `close()`.

Do đó timeout của scope là cơ chế kích hoạt cancellation theo deadline, không phải cơ chế cưỡng bức giết thread. Muốn thời gian kết thúc có giới hạn thực tế, cần bảo đảm các thao tác con có timeout/cancellation phù hợp.

### 7.3. Owner bị interrupt khi join

`join()` khai báo `throws InterruptedException`. Nếu owner bị interrupt trong lúc chờ:

- `join()` ném `InterruptedException`.
- `try`-with-resources vẫn gọi `close()`.
- `close()` hủy các task còn lại và đợi chúng kết thúc.
- Nếu owner bị interrupt trong khi `close()` đang chờ, `close()` vẫn tiếp tục đợi task kết thúc rồi khôi phục interrupt status trước khi hoàn tất.

Ví dụ một boundary có thể truyền interruption ra ngoài:

~~~java
Dashboard handle(String userId) throws InterruptedException {
    try (var scope = StructuredTaskScope.open()) {
        var profile = scope.fork(() -> loadProfile(userId));
        var orders = scope.fork(() -> loadOrders(userId));

        scope.join();
        return new Dashboard(profile.get(), orders.get());
    }
}
~~~

Nếu tầng gọi bắt `InterruptedException` và không truyền tiếp, tầng đó cần khôi phục interrupt status:

~~~java
try {
    return handle(userId);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new RequestCancelledException(e);
}
~~~

Không chuyển interruption thành một kết quả thành công giả. Nó là tín hiệu điều khiển luồng thực thi.

## 8. Kết hợp StructuredTaskScope với ScopedValue

JDK 25 cho phép các subtask kế thừa binding `ScopedValue` được capture khi mở scope.

~~~java
private static final ScopedValue<String> REQUEST_ID =
    ScopedValue.newInstance();

Dashboard handle(String requestId, String userId)
        throws InterruptedException {

    return ScopedValue.where(REQUEST_ID, requestId).call(() -> {
        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(() -> {
                audit("load-profile", REQUEST_ID.get());
                return loadProfile(userId);
            });

            var orders = scope.fork(() -> {
                audit("load-orders", REQUEST_ID.get());
                return loadOrders(userId);
            });

            scope.join();
            return new Dashboard(profile.get(), orders.get());
        }
    });
}
~~~

Khi `StructuredTaskScope` được mở, JVM capture các binding `ScopedValue` hiện tại. Những task được fork trong scope kế thừa các binding đó.

Các quy tắc quan trọng:

- Binding được capture khi mở scope.
- Binding tại thời điểm fork phải khớp binding đã capture khi mở scope.
- Task con có thể rebind trong phạm vi riêng; khi scope rebind kết thúc, binding trước đó được khôi phục.
- Value được chia sẻ giữa các thread phải immutable hoặc mọi truy cập mutable phải được đồng bộ.
- Khi scope đóng, owner chờ task con kết thúc, nên binding của owner không bị khôi phục quá sớm trong khi task con vẫn đang dùng nó.

Cơ chế này phù hợp cho request ID, tenant metadata hoặc correlation context bất biến. Không đưa object mutable không an toàn vào `ScopedValue` rồi cho nhiều task con sửa đồng thời.

## 9. Cấu hình thread và quan sát scope

### 9.1. Đặt tên virtual thread

Mặc định, scope tạo unnamed virtual thread. Có thể cung cấp `ThreadFactory` nếu cần tên dễ quan sát:

~~~java
ThreadFactory factory = Thread.ofVirtual()
    .name("order-task-", 0)
    .factory();

var joiner =
    StructuredTaskScope.Joiner.<Object>awaitAllSuccessfulOrThrow();

try (var scope = StructuredTaskScope.open(
        joiner,
        config -> config.withThreadFactory(factory)
                        .withName("order-request"))) {

    var inventory = scope.fork(() -> reserveInventory(orderId));
    var payment = scope.fork(() -> authorizePayment(orderId));

    scope.join();
    return new CheckoutResult(inventory.get(), payment.get());
}
~~~

Tên scope và tên thread giúp người vận hành nhận diện nhóm tác vụ trong thread dump hoặc công cụ quan sát. Chỉ thêm thông tin định danh cần thiết; tránh đặt tên chứa token hoặc dữ liệu cá nhân.

### 9.2. Dùng thread dump để điều tra

Khi ứng dụng đang chạy, có thể kiểm tra JVM bằng:

~~~bash
jcmd -l
jcmd <pid> Thread.print
~~~

Thread dump giúp xem virtual thread, stack trace và mối quan hệ tác vụ trong runtime. Kết hợp tên scope/thread với request ID trong log hoặc JFR để điều tra:

- Task nào đang chờ I/O?
- Task nào chưa kết thúc sau cancellation?
- Owner đang ở `join()` hay `close()`?
- Có một task con bị mắc trong API blocking không interruptible?

Thread dump là ảnh chụp tại một thời điểm. Nếu nghi ngờ task treo, lấy nhiều dump cách nhau một khoảng ngắn và so sánh stack.

## 10. Structured Concurrency và các lựa chọn concurrency khác

| Nhu cầu | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Nhóm task con thuộc một request và phải kết thúc trước khi trả response | `StructuredTaskScope` | Vòng đời, lỗi và cancellation được phối hợp theo scope |
| Chỉ cần thực hiện một tác vụ nền tồn tại sau request | Executor hoặc message broker | Task có vòng đời độc lập với request |
| Pipeline bất đồng bộ có nhiều stage và composition | `CompletableFuture` hoặc framework reactive | Biểu diễn stage/dependency và composition |
| Nhiều tác vụ blocking có quan hệ cha-con | Structured Concurrency + virtual threads | Một virtual thread cho mỗi subtask, quản lý theo scope |
| Xử lý dữ liệu song song theo batch/collection | Stream parallel hoặc ForkJoinPool tùy workload | Mô hình phù hợp với phép biến đổi dữ liệu |
| Tác vụ lâu dài như scheduler, consumer hoặc daemon | Executor/service lifecycle riêng | Không nên buộc vào scope ngắn hạn của request |

Structured Concurrency không thay thế mọi API concurrency. Nó phù hợp khi nhóm task có cùng vòng đời và kết quả cần được phối hợp trước khi task cha tiếp tục.

Đặc biệt, không dùng scope request để chạy một công việc nền cần tồn tại sau khi response đã trả. Với background job, hãy gửi message hoặc tạo task có lifecycle do một component/service quản lý.

## 11. Biên dịch và chạy ví dụ trên JDK 25

Structured Concurrency trong JDK 25 là preview API. Cần bật preview ở cả compile và runtime.

Ví dụ với source `DashboardDemo.java`:

~~~bash
javac --release 25 --enable-preview -d out DashboardDemo.java
java --enable-preview -cp out DashboardDemo
~~~

Nếu dùng Maven hoặc Gradle, cấu hình `--enable-preview` cho cả compiler và JVM chạy test/application. Chỉ bật preview cho module hoặc source set thực sự dùng API này nếu dự án có thể tách phạm vi.

Kiểm tra runtime:

~~~bash
java -version
javac -version
~~~

Dùng đúng JDK 25 để compile và run code của JEP 505. Preview API được gắn với release cụ thể; class file hoặc source dùng preview của một release không thể coi là tương thích tự động với release tiếp theo.

### 11.1. Các ví dụ cũ cần tránh

Các vòng preview trước đã thay đổi API nhiều lần. Không lấy mã từ một bài viết cũ rồi cho rằng nó compile trên JDK 25.

| Hướng dẫn cũ thường gặp | Cách làm trong JDK 25 |
| --- | --- |
| Dùng lớp policy cũ như `ShutdownOnFailure` hoặc `ShutdownOnSuccess` | Dùng `StructuredTaskScope.Joiner` và các factory method tương ứng |
| Gọi API shutdown theo phiên bản preview trước | Chọn Joiner, cấu hình timeout, để `close()` quản lý lifecycle |
| Dùng constructor/API scope cũ | Mở scope bằng `StructuredTaskScope.open(...)` |
| Dùng ví dụ preview không ghi release | Kiểm tra JEP và Javadoc của đúng JDK trước khi copy |

Mục đích là học API JDK 25 đúng phiên bản. Các API preview có thể thay đổi; không dùng mã từ JDK 21–24 mà chưa đối chiếu.

## 12. Các lỗi thiết kế và cách khắc phục

| Lỗi | Hậu quả | Cách thiết kế lại |
| --- | --- | --- |
| Quên gọi `join()` sau khi fork | `close()` báo lỗi cấu trúc sau khi đóng scope | Join theo policy trước khi rời block |
| Gọi `fork()` sau `join()` | Vi phạm lifecycle | Hoàn thành giai đoạn fork trước điểm join |
| Gọi scope từ thread khác owner | `WrongThreadException` | Chỉ owner điều khiển scope |
| Gọi `Subtask.get()` trước join | Kết quả chưa sẵn sàng | Join rồi mới đọc |
| Bắt và bỏ qua `InterruptedException` | Task tiếp tục chạy sau cancellation | Truyền exception hoặc khôi phục interrupt |
| Task không phản hồi interrupt | `close()` chờ rất lâu | Kiểm tra interrupt và đặt I/O timeout |
| Dùng `awaitAll()` nhưng không đọc trạng thái | Lỗi task bị bỏ qua | Kiểm tra `state()` và `exception()` |
| Dùng `anySuccessfulResultOrThrow()` khi cần mọi kết quả | Task còn lại bị hủy sau kết quả đầu tiên | Dùng Joiner chờ tất cả thành công |
| Đặt timeout quá lớn ở mỗi tầng | Tổng deadline vượt ngân sách request | Truyền remaining deadline xuống các tầng |
| Dùng scope cho background job | Request phải chờ công việc không thuộc response | Chuyển sang message queue hoặc lifecycle riêng |
| Dùng mutable context chung giữa task con | Race condition | Dùng immutable value hoặc synchronization |

## 13. Quy trình điều tra cancellation bị chậm

Khi request timeout nhưng thread vẫn tồn tại, hãy lần lượt kiểm tra:

1. **Xác định owner:** owner đang ở `join()`, `close()` hay code ngoài scope?
2. **Xem trạng thái scope:** `isCancelled()` có trả `true` không?
3. **Lấy thread dump:** task con đang ở socket read, database call, lock wait hay vòng lặp CPU?
4. **Kiểm tra interrupt handling:** task có kiểm tra interrupt hoặc truyền `InterruptedException` không?
5. **Kiểm tra timeout downstream:** HTTP/RPC/database client có timeout riêng không?
6. **Kiểm tra cleanup:** `finally` có bị block khi đóng resource không?
7. **Tái hiện có kiểm soát:** giảm workload, dùng timeout ngắn và ghi lại thời gian từ lúc cancellation tới lúc `close()` hoàn tất.

Không kết luận scope bị lỗi chỉ vì `close()` mất thời gian. Hãy xác định task nào không kết thúc và API nào đang giữ task đó.

## 14. Checklist triển khai

### Thiết kế

- [ ] Các task con thuộc cùng một thao tác nghiệp vụ.
- [ ] Owner là thread điều khiển toàn bộ scope.
- [ ] Joiner phản ánh đúng yêu cầu kết quả.
- [ ] Xác định rõ lỗi nào phải hủy các task anh em.
- [ ] Xác định deadline của request và remaining budget.

### Triển khai

- [ ] Mở scope bằng `try`-with-resources.
- [ ] Fork xong trước khi gọi join.
- [ ] Chỉ gọi join một lần.
- [ ] Chỉ đọc `Subtask.get()` sau khi join và task thành công.
- [ ] Xử lý `FailedException`, `TimeoutException`, `InterruptedException`.
- [ ] Task con phản hồi interrupt.
- [ ] I/O client có timeout riêng.
- [ ] Không dùng scope cho background task sống lâu hơn request.

### Vận hành

- [ ] Bật preview đúng JDK 25 ở compile và runtime.
- [ ] Ghi JDK version/build và JVM options.
- [ ] Đặt tên scope/thread nếu cần quan sát.
- [ ] Có thread dump khi điều tra cancellation chậm.
- [ ] Đo thời gian `join()` và `close()` trong workload đại diện.
- [ ] Kiểm tra lại API khi nâng lên JDK 26/27.

## 15. Bài thực hành tổng hợp

**Tình huống:** endpoint checkout cần kiểm tra tồn kho, tính phí giao hàng và xác thực thanh toán song song. Response chỉ được trả khi cả ba kết quả thành công. Nếu một tác vụ thất bại hoặc vượt deadline 1,5 giây, các tác vụ còn lại cần được hủy.

### Phần A — Tạo scope và join

1. Tạo `StructuredTaskScope` bằng `open()`.
2. Fork ba task có kiểu kết quả khác nhau.
3. Gọi `join()` đúng một lần.
4. Đọc ba kết quả sau khi join.
5. Tổng hợp `CheckoutResult`.

**Đạt** khi cả ba task chạy đồng thời và owner chỉ đọc kết quả sau join.

### Phần B — Xử lý lỗi

1. Cho một task ném `IOException`.
2. Quan sát `FailedException` từ join.
3. Ghi nhận cause của lỗi.
4. Xác minh các task anh em nhận interrupt.
5. Kiểm tra `close()` đợi các task còn lại kết thúc.

**Đạt** khi phân biệt được lỗi gốc và các task bị hủy do lỗi đó.

### Phần C — Thêm deadline

1. Mở scope với `awaitAllSuccessfulOrThrow()`.
2. Cấu hình `withTimeout(Duration.ofMillis(1500))`.
3. Cho một task chậm hơn deadline.
4. Bắt `TimeoutException`.
5. Kiểm tra thời gian thực tế cho tới khi `close()` hoàn tất.
6. Đặt timeout riêng cho HTTP/RPC/database call.

**Đạt** khi giải thích được vì sao scope timeout có thể xảy ra trước khi caller thoát khỏi `close()`.

### Phần D — Kiểm thử interrupt

1. Viết một task CPU-bound kiểm tra `isInterrupted()`.
2. Viết một task blocking bằng API có thể interrupt.
3. Kích hoạt cancellation do lỗi hoặc timeout.
4. Xác nhận cả hai task kết thúc và cleanup được chạy.
5. Viết một ví dụ task bỏ qua interrupt để quan sát `close()` bị chờ.

**Đạt** khi không dùng cơ chế cưỡng bức dừng thread và hiểu cancellation là hợp tác.

### Phần E — Quan sát và context

1. Đặt tên scope là `checkout`.
2. Đặt tên virtual thread bằng `ThreadFactory`.
3. Bind request ID bằng `ScopedValue` trước khi mở scope.
4. Đọc request ID trong các task con.
5. Lấy thread dump và xác định các task đang chạy.

**Đạt** khi các task con nhận đúng context và có thể được nhận diện trong thread dump.

## 16. Câu hỏi tự đánh giá

1. Structured Concurrency nhóm các task theo nguyên tắc nào?
2. Vì sao `StructuredTaskScope` phải được dùng trong `try`-with-resources?
3. Thread nào là owner của một scope?
4. Vì sao `fork()` không được gọi sau `join()`?
5. `StructuredTaskScope.open()` dùng Joiner mặc định nào trong JDK 25?
6. Khi một task thất bại, điều gì xảy ra với các task anh em theo chính sách mặc định?
7. `allSuccessfulOrThrow()` khác `awaitAllSuccessfulOrThrow()` ở kiểu kết quả như thế nào?
8. Khi nào nên dùng `anySuccessfulResultOrThrow()`?
9. `awaitAll()` có tự hủy scope khi task thất bại không?
10. Vì sao `Subtask.get()` chỉ được gọi sau join?
11. Scope cancellation có cưỡng bức dừng thread con không?
12. Tác vụ con cần làm gì để phản hồi interrupt?
13. Vì sao không nên nuốt `InterruptedException`?
14. Khác biệt giữa `Thread.isInterrupted()` và `Thread.interrupted()` là gì?
15. Timeout của scope bắt đầu tính từ thời điểm nào?
16. `TimeoutException` có đảm bảo caller thoát ngay khỏi `close()` không?
17. Vì sao HTTP/RPC/database client cần timeout riêng?
18. `close()` làm gì với các task chưa hoàn tất?
19. `StructuredTaskScope` kế thừa `ScopedValue` binding như thế nào?
20. JEP 505 là preview lần thứ mấy trong JDK 25?
21. Vì sao code dùng Structured Concurrency trên JDK 25 cần bật preview ở cả compile và runtime?
22. JDK 26 và JDK 27 tiếp tục thay đổi trạng thái API này như thế nào?
23. Khi nào một background job nên được quản lý bởi executor hoặc message broker thay vì request scope?
24. Những thông tin nào cần thu thập khi điều tra `close()` chậm?

## 17. Tài liệu tham khảo

- [OpenJDK JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): thiết kế và thay đổi API cho JDK 25.
- [Java SE 25 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): `open`, `fork`, `join`, `close`, timeout, cancellation và kế thừa ScopedValue.
- [Java SE 25 API — StructuredTaskScope.Joiner](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): các chính sách `allSuccessfulOrThrow`, `anySuccessfulResultOrThrow`, `awaitAllSuccessfulOrThrow` và `awaitAll`.
- [Java SE 25 API — StructuredTaskScope.Configuration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html): cấu hình thread factory, tên scope và timeout.
- [Oracle Java 25 Core Libraries — Structured Concurrency](https://docs.oracle.com/en/java/javase/25/core/structured-concurrency.html): quy trình dùng scope, joiner, exception handling và quan sát thread.
- [Oracle JDK 25 — Preview Language and VM Features](https://docs.oracle.com/en/java/javase/25/language/preview-language-and-vm-features.html): bật preview khi compile và chạy.
- [JDK 26 — Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): JEP 525, Structured Concurrency Sixth Preview.
- [JDK 27 — Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): JEP 533, Structured Concurrency Seventh Preview.

