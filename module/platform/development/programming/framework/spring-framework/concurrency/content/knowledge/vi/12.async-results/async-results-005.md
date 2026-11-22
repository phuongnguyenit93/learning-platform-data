# Dùng `completedFuture()` cho giá trị đã tính trong luồng xử lý

## Mục tiêu

Trong Spring Framework, một phương thức `@Async` trả `CompletableFuture<T>` thường kết thúc bằng:

```java
return CompletableFuture.completedFuture(result);
```

Vì sao một phương thức **bất đồng bộ** lại trả về future **đã hoàn tất**? Cần phân biệt hai đối tượng: **future tạm** mà phương thức đích tạo trong worker sau khi đã tính `result`, và **future thực tế** Spring proxy trả cho caller để theo dõi toàn bộ công việc được submit. `completedFuture()` không lập lịch chạy; chính `@Async` và executor chuyển việc khỏi caller khi được cấu hình và gọi đúng cách.

Sau khi học, bạn có thể:

1. Giải thích chính xác hợp đồng của `CompletableFuture.completedFuture(value)` trong JDK.
2. Hiểu vì sao target method `@Async` dùng completed future để chuyển giá trị đã tính cho hạ tầng Spring.
3. Phân biệt thời điểm **giá trị đã có trong worker** với thời điểm **future của caller hoàn tất**.
4. Chọn đúng giữa `completedFuture`, `failedFuture`, `supplyAsync`, `new CompletableFuture<>()`, và các toán tử composition.
5. Viết và chạy ví dụ Java 17+ với Spring Framework chứng minh future tạm đã xong trong khi proxy future còn pending.
6. Tránh các sai lầm về self-invocation, blocking, lỗi bất đồng bộ, cancellation, timeout, context và mutable state.

**Kết luận cốt lõi:** `completedFuture(value)` nói “tôi **đã có** value”; nó không nói “hãy tính value trên thread khác”. Trong phương thức `@Async`, việc lựa chọn thread nằm ở **Spring proxy/executor**, không ở static factory của `CompletableFuture`.

## 1. `completedFuture()` trong Java tạo ra gì?

Theo Java SE, `CompletableFuture.completedFuture(U value)` trả về một `CompletableFuture<U>` mới, **đã hoàn tất bình thường** với giá trị truyền vào. Đó là factory method đồng bộ, không submit task.

```java
CompletableFuture<Integer> ready =
    CompletableFuture.completedFuture(42);

System.out.println(ready.isDone()); // true
System.out.println(ready.join());   // 42
```

Ví dụ trên là snippet Java sử dụng `java.util.concurrent.CompletableFuture`, không cần Spring. Nó không mở thread mới, không dùng `ForkJoinPool.commonPool()` và không tạo một computation pending. `join()` ở đây trả về ngay vì kết quả đã sẵn.

Đặc biệt, Java đánh giá **biểu thức tham số trước lời gọi**:

```java
int answer = expensiveCalculation();
return CompletableFuture.completedFuture(answer);
```

`expensiveCalculation()` chạy **trước** khi future được tạo, trên thread đang chạy đoạn code đó. Viết:

```java
return CompletableFuture.completedFuture(expensiveCalculation());
```

không tự làm phép tính thành async: Java vẫn thực thi `expensiveCalculation()` để lấy argument trước khi gọi factory method. Nếu `expensiveCalculation()` chặn ba giây, caller của một method Java thông thường có thể bị chặn ba giây. Muốn đổi nơi chạy, cần cơ chế scheduling riêng như `@Async`, `ExecutorService.submit`, hoặc `CompletableFuture.supplyAsync`.

**Các trạng thái và đặc điểm:**

- Future do `completedFuture(value)` tạo có `isDone() == true`, `isCompletedExceptionally() == false`.
- `get()` và `join()` có kết quả sẵn; không phải chờ một background task.
- Có thể dùng `completedFuture(null)` nếu hợp đồng cho phép giá trị `null`; đây là một **future hợp lệ** mang giá trị null, không đồng nghĩa một method trả chính tham chiếu future là `null`.
- Với value là object mutable, `completedFuture` không biến object ấy thành immutable hay thread-safe.
- `completedFuture(error)` khi `error` là một `Throwable` vẫn có thể là **thành công với giá trị Throwable**, khác với future thất bại.

Ví dụ đồng bộ trả completion handle:

```java
public CompletableFuture<String> greeting(String name) {
    String message = "Xin chào " + name;
    return CompletableFuture.completedFuture(message);
}
```

Nếu không có AOP async hoặc executor bao ngoài, cả việc tạo `message` lẫn tạo future đều xảy ra trên caller. **Kiểu trả về `CompletableFuture` không tự bảo đảm lời gọi là bất đồng bộ.**

## 2. Vì sao `@Async` sử dụng một future tạm?

Spring `@Async` hỗ trợ những phương thức có kiểu trả về `void` hoặc `Future` (bao gồm `CompletableFuture`). Với kiểu trả về có kết quả, Spring proxy submit lời gọi sang executor rồi trao cho caller một handle để chờ hoặc compose kết quả.

Xem method minh họa trong một Spring bean:

```java
@Async("reportExecutor")
public CompletableFuture<String> buildReport(String id) {
    String report = calculateReport(id); // work trong worker
    return CompletableFuture.completedFuture(report);
}
```

Đây chưa phải chương trình độc lập: cần method `calculateReport`, `@EnableAsync`, bean tên `reportExecutor` và lời gọi **qua Spring proxy**. Trong điều kiện đúng:

1. Caller gọi `buildReport("A")` trên Spring-managed proxy.
2. Async interceptor chọn `reportExecutor` và submit method invocation.
3. Caller nhận **future của proxy**, thường khi task còn chưa hoàn tất.
4. Worker chạy `calculateReport("A")` và nhận một `String report`.
5. Vì chữ ký method yêu cầu `CompletableFuture<String>`, worker trả **future tạm đã completed** bằng `completedFuture(report)`.
6. Hạ tầng async xử lý return value của target method và hoàn tất **future mà caller nhận** với `report`.

Spring `@Async` Javadoc diễn đạt rõ sự khác nhau này: future mà proxy trả là asynchronous handle thực tế, còn target method có thể dùng `CompletableFuture.completedFuture` như một handle tạm để chuyển giá trị đã tính trong execution thread.

```text
Caller thread                 Spring proxy                  Worker thread
   |                               |                              |
   +-- service.buildReport("A") -->|                              |
   |                               +--- submit to executor ------>|
   |<-- proxyFuture --------------+                              |
   |                                                      calculateReport
   |                                                            |
   |                                                    String report đã có
   |                                                            |
   |                                           completedFuture(report)
   |                                                    tempFuture = DONE
   |                                                            |
   |                               <---- target returns tempFuture
   |                               |                              |
   |<---- proxyFuture completed ---+                              |
   |
   +-- thenApply/get/join/whenComplete tùy caller
```

**Không thể suy ra** rằng proxy future sẽ luôn pending ngay sau method call: task có thể chạy cực nhanh, hoặc executor được chọn có thể thực thi trên caller. Ví dụ đầy đủ ở phần 4 chủ động dùng chốt đồng bộ để quan sát hai trạng thái mà không phụ thuộc lịch scheduler.

### Ai chịu trách nhiệm gì?

| Thành phần | Trách nhiệm | Không tự làm |
| --- | --- | --- |
| `@EnableAsync` | Đăng ký hạ tầng annotation-driven async trong Spring context. | Không tạo kết quả nghiệp vụ. |
| `@Async("reportExecutor")` | Đánh dấu method và chỉ định executor. | Không tự hoạt động qua mọi kiểu lời gọi Java trực tiếp. |
| Spring proxy/interceptor | Nhận invocation, chọn executor, submit và cung cấp completion handle cho caller. | Không bảo đảm task luôn chạy thread khác trong mọi executor configuration. |
| `Executor`/`TaskExecutor` | Phân phối/chạy task, quản lý hàng đợi và worker theo chính sách. | Không biến dữ liệu dùng chung thành thread-safe. |
| `completedFuture(result)` trong target | Đóng gói kết quả **đã tính trong worker** thành completed temporary future. | Không submit thêm task, không bắt đầu một worker mới. |
| Future trả cho caller | Cho phép chờ có timeout, quan sát lỗi, biến đổi hoặc phối hợp kết quả. | Không tự giải phóng caller nếu caller gọi `join()` ngay. |

## 3. Điều kiện để ví dụ Spring hoạt động đúng

Không phải cứ thêm `@Async` vào mã nguồn là method chạy nền. Cần kiểm tra:

- **Bean do Spring quản lý:** object phải đến từ `ApplicationContext`, không phải instance tự tạo bằng `new`.
- **Async đã bật:** cần `@EnableAsync` hoặc cấu hình hạ tầng tương đương trong đúng application context.
- **Lời gọi qua proxy:** ở proxy mode mặc định, `this.asyncMethod()` trong cùng target là **self-invocation**, bỏ qua proxy và không được interceptor submit như lời gọi bên ngoài.
- **Method có thể intercept:** class-based proxy không override được method `final` hoặc `private`; class `final` không thể subclass. Nếu JDK proxy, caller cần gọi method được expose qua interface phù hợp.
- **Chữ ký hợp lệ:** `@Async` hỗ trợ `void`, `Future` và `CompletableFuture`, không thay tùy ý bằng `String` rồi kỳ vọng interceptor sẽ biến thành future.
- **Executor được chọn có thật:** `@Async("lessonExecutor")` cần bean tên tương ứng. Direct executor kiểu `Runnable::run` hoặc policy `CallerRunsPolicy` khi quá tải có thể chạy task trên caller, dù proxy vẫn có tác dụng.
- **Caller không chặn một cách vô tình:** gọi `get()` hoặc `join()` ngay sẽ chờ kết quả; `@Async` không bảo đảm HTTP request thread tự được giải phóng.

Khi thiếu `@EnableAsync` trong ứng dụng tự cấu hình như ví dụ, `@Async` có thể không được xử lý; `return completedFuture(value)` lúc đó chỉ là dòng Java thông thường. Vì vậy cần phân biệt **completion API** với **scheduling configuration** khi chẩn đoán.

## 4. Thực hành Java 17: factory không tạo task nền

Ví dụ sau kiểm chứng hành vi của `completedFuture` với JDK thuần. Thí nghiệm hai Future target/proxy của Spring đã có trong bài chuyên về async bridge; ở đây chỉ tập trung vào **thời điểm tính giá trị và việc submit**.

Lưu thành `CompletedFutureSemanticsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletedFutureSemanticsDemo {
    static int compute(AtomicInteger calls) {
        calls.incrementAndGet();
        return 21 * 2;
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        // compute chạy trên caller trước khi factory nhận đối số.
        int result = compute(calls);
        CompletableFuture<Integer> ready =
                CompletableFuture.completedFuture(result);
        System.out.println("computedBeforeFactory=" + calls.get());
        System.out.println("readyDone=" + ready.isDone());
        System.out.println("readyValue=" + ready.join());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch release = new CountDownLatch(1);
        try {
            CompletableFuture<Integer> scheduled =
                    CompletableFuture.supplyAsync(() -> {
                        try {
                            release.await();
                            return 42;
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    }, pool);
            // Chốt chưa mở, nên task không thể hoàn tất.
            System.out.println("scheduledPending=" + !scheduled.isDone());
            release.countDown();
            System.out.println("scheduledValue=" + scheduled.join());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac --release 17 CompletedFutureSemanticsDemo.java
java CompletedFutureSemanticsDemo
```

Kết quả:

```text
computedBeforeFactory=1
readyDone=true
readyValue=42
scheduledPending=true
scheduledValue=42
```

`compute()` được gọi trước factory nên bộ đếm đã bằng 1, còn `ready` completed ngay. `supplyAsync` submit supplier lên worker, nhưng latch giữ phép tính chưa xong để lần kiểm tra `scheduledPending` ổn định; sau khi mở chốt mới nhận được 42. Trong method Spring `@Async`, proxy đã làm nhiệm vụ submit; target chỉ cần tính kết quả trên worker rồi trả `completedFuture(result)`.

## 5. Dùng `completedFuture` đúng trong Spring service thực tế

Giả sử một service truy vấn repository đồng bộ:

```java
@Service
public class UserService {
    private final UserRepository repository;

    public UserService(UserRepository repository) {
        this.repository = repository;
    }

    @Async("ioExecutor")
    public CompletableFuture<UserDto> findUser(long id) {
        User user = repository.loadRequired(id);
        UserDto dto = new UserDto(user.id(), user.name());
        return CompletableFuture.completedFuture(dto);
    }
}
```

Đây là **mẫu cấu trúc không độc lập**; các kiểu `UserRepository`, `User` và `UserDto` phải được định nghĩa, có các annotation/import tương ứng và bean `ioExecutor` phải tồn tại.

Lời gọi `service.findUser(id)` từ bean khác đi **qua Spring proxy** sẽ gửi toàn bộ phần đọc repository và dựng DTO lên `ioExecutor`. Khi đến `completedFuture(dto)`, phần việc đồng bộ trong worker đã xong. Future này chỉ đóng gói kết quả đã có cho Spring.

Nếu không có `@Async` hoặc gọi trực tiếp target qua self-invocation, `repository.loadRequired(id)` diễn ra trên caller, có thể chặn caller lâu; completed future phía sau không cứu được thời gian đã mất.

### Khi nào nên dùng?

- Target method `@Async` tính được kết quả đồng bộ trong worker và cần trả đúng chữ ký `CompletableFuture<T>`.
- Nhánh cache hit hoặc dữ liệu tĩnh đã có sẵn muốn tuân thủ API Future thống nhất.
- Test stub trả ngay một giá trị có sẵn, không cần scheduler.
- Một adapter muốn cung cấp stage đã hoàn tất mà không tạo thêm worker.

### Khi nào không phù hợp?

- Muốn bắt đầu tính toán ở pool khác: sử dụng `ExecutorService.submit`, Spring `@Async` hoặc `CompletableFuture.supplyAsync(..., executor)`.
- Muốn biểu diễn công việc sẽ hoàn tất khi callback/sự kiện đến: tạo future chưa hoàn tất và gọi `complete` hoặc `completeExceptionally` đúng thời điểm.
- Muốn chuyển tải một Future đang pending thành giá trị: nên compose thay vì `join` một Future khác trong worker rồi bọc kết quả.
- Muốn báo lỗi đã biết: dùng `failedFuture(error)` chứ không coi `completedFuture(error)` là completion thất bại.

## 6. So sánh các API trong một bảng

| API | Kết quả ngay sau lời gọi | Lập lịch task mới? | Mục đích |
| --- | --- | --- | --- |
| `CompletableFuture.completedFuture(value)` | Future đã completed thành công | **Không** | Đưa giá trị đã tính vào completion API. |
| `CompletableFuture.failedFuture(error)` | Future đã completed exceptionally | **Không** | Đưa lỗi đã biết vào completion API. |
| `new CompletableFuture<T>()` | Future chưa completed | **Không** | Callback bên ngoài hoàn tất sau. |
| `CompletableFuture.supplyAsync(supplier)` | Future có thể còn pending hoặc đã xong rất nhanh | **Có** qua default executor | Chạy phép tính bất đồng bộ mà không chỉ định pool. |
| `CompletableFuture.supplyAsync(supplier, executor)` | Tương tự, theo chính sách executor cung cấp | **Có** qua executor được chọn | Chủ động chọn pool. |
| `CompletableFuture.runAsync(runnable, executor)` | Future kiểu `Void` | **Có** | Công việc không có giá trị trả về. |
| `future.thenApply(transform)` | Stage phụ thuộc kết quả future trước | Không bắt buộc tạo worker mới | Biến đổi kết quả. |
| `future.thenApplyAsync(transform, executor)` | Stage phụ thuộc thực thi qua executor | **Có** | Cần chọn thread/pool cho bước biến đổi. |
| `future.thenCompose(function)` | Stage dẹt từ hàm trả future khác | Không tự yêu cầu pool mới | Nối chuỗi các phép tính bất đồng bộ. |

`isDone()` không chứng minh một bước đã thực thi trên worker khác. Task qua `supplyAsync` có thể hoàn tất trước khi caller kiểm tra, hoặc executor tùy chỉnh có thể thực thi trực tiếp trên caller. Phải nhìn cơ chế scheduling, không chỉ trạng thái future.

### Đối chiếu với `supplyAsync`

```java
ExecutorService pool = Executors.newSingleThreadExecutor();
try {
    int number = 7;
    CompletableFuture<Integer> immediate =
        CompletableFuture.completedFuture(number * 2);
    CompletableFuture<Integer> scheduled =
        CompletableFuture.supplyAsync(() -> number * 2, pool);

    System.out.println("immediate=" + immediate.join());
    System.out.println("scheduled=" + scheduled.join());
} finally {
    pool.shutdown();
}
```

Đây là snippet đặt trong method, cần import `ExecutorService`, `Executors`, `CompletableFuture`. Khi chạy thành công, output là:

```text
immediate=14
scheduled=14
```

Output giống nhau nhưng khác ranh giới thực thi: biểu thức `number * 2` của `immediate` được đánh giá trên caller ngay lập tức; biểu thức bên trong supplier của `scheduled` được gửi qua `pool`.

### Tránh “double scheduling” không có chủ đích

```java
@Async("ioExecutor")
public CompletableFuture<String> load(String id) {
    return CompletableFuture.supplyAsync(() -> blockingLookup(id));
}
```

Đây là snippet cần bean/executor và `blockingLookup`, không độc lập. Ở đây `@Async` đã đưa phương thức `load` lên executor được chọn, rồi `supplyAsync` **không truyền executor** lại gửi một task sang default executor của JDK (thường `ForkJoinPool.commonPool()`). Điều này có thể gây hai tầng scheduling, khó quản lý thread/context/metrics và thêm blocking khi Spring cần kết quả của stage con.

Nếu `blockingLookup` là công việc đồng bộ muốn thực hiện trên worker `ioExecutor`, idiom thường đơn giản hơn:

```java
@Async("ioExecutor")
public CompletableFuture<String> load(String id) {
    String value = blockingLookup(id);
    return CompletableFuture.completedFuture(value);
}
```

Nếu logic thật sự đã hoàn tất bất đồng bộ ở một hệ thống khác, có thể có lý do để compose một stage từ API đó; cần quyết định rõ ownership và executor, không tự động chọn `supplyAsync` chỉ vì có `CompletableFuture`.

## 7. Xử lý ngoại lệ ở target và caller

### Target ném lỗi trước khi tạo completed future

```java
@Async("ioExecutor")
public CompletableFuture<UserDto> findUser(long id) {
    User user = repository.loadRequired(id);
    return CompletableFuture.completedFuture(
        new UserDto(user.id(), user.name())
    );
}
```

Đây là snippet dùng các kiểu domain ở phần trước. Nếu repository ném `RuntimeException`, dòng `completedFuture` sẽ không chạy. Khi invocation đi qua Spring async proxy, hạ tầng phản ánh lỗi từ worker sang completion handle của caller.

Caller có thể dùng `get()` (thường nhận `ExecutionException` với `cause`), `join()` (thường `CompletionException`) hoặc callback `whenComplete`/`handle`.

### Lỗi đã được xác định trong code

```java
@Async("validationExecutor")
public CompletableFuture<String> validate(String input) {
    if (input == null || input.isBlank()) {
        return CompletableFuture.failedFuture(
            new IllegalArgumentException("Input is blank")
        );
    }
    return CompletableFuture.completedFuture(input.trim());
}
```

Snippet này giả định bean `validationExecutor`, các import và Spring async context. `failedFuture` tạo completed future **exceptionally**, còn `completedFuture` tạo completed future **successfully**. Chữ “completed” chỉ nói về trạng thái kết thúc; phải phân biệt thành công với thất bại.

Nếu khai báo `@Async void`, caller không có future để nhận exception từ worker; cần `AsyncUncaughtExceptionHandler` hoặc logging/metrics có chủ đích. Với nghiệp vụ quan trọng phải theo dõi kết quả, nên có một return type Future hoặc job status.

### Caller quan sát lỗi

```java
CompletableFuture<String> answer = validationService.validate(input);
answer.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Failed: " + error.getMessage());
    } else {
        System.out.println("Valid: " + value);
    }
});
```

Đây là đoạn minh họa có `validationService` và `input`. `whenComplete` là phép **quan sát**, không nhất thiết chữa lỗi. Nếu muốn trả fallback, cân nhắc `exceptionally`/`handle` và chính sách nghiệp vụ. Không bỏ quên future trong lúc task có thể lỗi.

## 8. Composition sau khi nhận kết quả

Caller thường không cần lập tức `get()`/`join()`; có thể ghép các stage:

```java
CompletableFuture<String> display =
    workService.compute("A", 7)
        .thenApply(value -> "Result: " + value.value());
```

Snippet dùng `WorkService` của ví dụ chính nhưng không độc lập. `thenApply` có thể được thực thi bởi thread hoàn tất stage hoặc thread đăng ký callback khi future đã completed. Nó **không bảo đảm** tạo một worker khác.

Nếu muốn chọn rõ executor cho bước tiếp theo:

```java
CompletableFuture<String> display =
    workService.compute("A", 7)
        .thenApplyAsync(value -> "Result: " + value.value(), cpuExecutor);
```

Ở đây cần một `Executor cpuExecutor`. Không mặc định rằng `thenApplyAsync(...)` không truyền executor sẽ dùng `lessonExecutor` của Spring; overload không có executor thường dùng default executor của JDK.

Với hàm trả `CompletionStage<U>`:

```java
CompletableFuture<String> chained =
    workService.compute("A", 7)
        .thenCompose(value -> anotherService.lookup(value.value()));
```

Snippet giả định `anotherService.lookup(...)` trả `CompletionStage<String>` hoặc `CompletableFuture<String>`. `thenCompose` tránh tạo future lồng. Tránh `join()` Future khác trong worker chỉ để `return completedFuture(...)`: nếu future kia cần chính worker bị chặn để chạy tiếp, pool nhỏ có thể nghẽn hoặc deadlock.

## 9. Thread context, dữ liệu mutable và side effects

**Thread context:** `@Async` là ranh giới giữa caller thread và worker. `ThreadLocal`, MDC, request attributes, security context, và transaction gắn với caller không mặc nhiên truyền sang worker. `completedFuture` không thay đổi quy tắc này. Khi cần context, truyền có kiểm soát bằng `TaskDecorator` hoặc cơ chế tương ứng, phải dọn/khôi phục trong `finally` do worker được tái sử dụng. Nếu task async cần transaction, xác định transaction tại worker theo cấu hình Spring phù hợp.

**Object được trả:** Một `CompletableFuture<List<Order>>` completed không tự biến `List<Order>` thành immutable. Nếu nhiều thread còn sửa object, nguy cơ race vẫn có. Ưu tiên DTO bất biến, defensive copy hoặc ownership rõ:

```java
List<String> snapshot = List.copyOf(items);
return CompletableFuture.completedFuture(snapshot);
```

Snippet này cần import `List` và biến `items`. `List.copyOf` ngăn sửa cấu trúc thông qua danh sách kết quả, nhưng không bảo đảm bất biến sâu của các phần tử mutable; việc copy từ nguồn đang sửa đồng thời cần đồng bộ thích hợp.

**Side effects:** Hoàn tất future của một method không tự chứng minh một message đã được consumer xử lý, email đã tới mailbox, hay database transaction của hệ thống khác đã commit. Phải xác định rõ `result` nói về giai đoạn nghiệp vụ nào; khi cần tính bền vững, dùng acknowledgement/job status/transaction phù hợp.

## 10. Timeout và cancellation không được nhầm với completedFuture

```java
Result value = service.compute("A", 7)
    .get(500, TimeUnit.MILLISECONDS);
```

Snippet này dùng service của ví dụ. `get(timeout)` giới hạn **lần caller chờ kết quả**. Nếu timeout, worker có thể vẫn chạy; caller timeout không tự tạo `completedFuture` hay tự dừng task.

`CompletableFuture.orTimeout(...)` có thể khiến future kết thúc ngoại lệ nếu còn pending sau thời hạn; `completeOnTimeout(...)` có thể hoàn tất bằng fallback. Các API này thay đổi trạng thái completion của future được gọi chứ không bảo đảm ngắt worker. Với future do Spring proxy trả về, cancellation và interrupt có ngữ nghĩa phụ thuộc loại future/hạ tầng; không suy ra `cancel(true)` chắc chắn dừng I/O hoặc rollback side effect.

Trong HTTP request, nếu controller gọi `join()` ngay, chính controller thread vẫn chờ. Muốn HTTP async đúng nghĩa phải dùng hợp đồng của Spring MVC/WebFlux phù hợp, độc lập với việc target method có `@Async`.

Đặt timeout thật ở HTTP client, JDBC, connection pool và deadline nghiệp vụ; hạn chế queue/worker để không giữ tài nguyên vô hạn. Nếu task cần tiếp tục sau client disconnect hoặc restart, phải có job status và hàng đợi/lưu trữ bền vững; `completedFuture` không giải quyết độ bền.

## 11. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`completedFuture` tạo task chạy nền.” | Nó tạo future đã completed, không submit task. |
| “Trả future completed trong `@Async` nghĩa là toàn bộ lời gọi đồng bộ.” | Target method có thể đang chạy trên worker; proxy future của caller theo dõi toàn bộ invocation. |
| “Future trong target và future caller chắc chắn là cùng object.” | Trong proxy mode Spring, caller thường nhận một handle riêng. |
| “`isDone() == true` chứng minh đã chạy trên thread khác.” | Một future đồng bộ tạo bằng `completedFuture` cũng `isDone() == true`. |
| “Đánh giá tham số `completedFuture(slowQuery())` ở background.” | `slowQuery()` chạy trước lời gọi factory, trên thread hiện tại. |
| “`this.asyncMethod()` cũng đi qua async proxy.” | Self-invocation ở proxy mode bỏ qua advisor. |
| “Nên lồng `supplyAsync` trong mọi `@Async`.” | Có thể thêm một tầng scheduling sang default JDK executor không cần thiết. |
| “`completedFuture(exception)` thể hiện task thất bại.” | Có thể là future thành công với giá trị exception; dùng `failedFuture`. |
| “`get(timeout)` sẽ hủy tác vụ nếu caller hết hạn.” | Timeout chỉ giới hạn chờ của caller, không tự cancel worker. |
| “Future completed thì payload tự bất biến và an toàn luồng.” | Completion không bảo vệ mutable object được share. |
| “Future returned nghĩa là HTTP thread không block.” | Controller gọi `join`/`get` vẫn chặn; cần thiết kế HTTP async thích hợp. |

## 12. Checklist rà soát một `return completedFuture(result)`

1. **Giá trị đã tính ở đâu?** Mọi phép tính/I/O xảy ra **trước** `completedFuture` và có thể blocking.
2. **Có proxy không?** `@EnableAsync` được bật ở đúng context, bean do Spring quản lý và lời gọi qua proxy?
3. **Đúng executor không?** Qualifier `@Async("...")`, thread-name prefix, hàng đợi/rejection và giới hạn pool đã rõ?
4. **Có hai loại future không?** Future tạm ở target với future proxy caller không nên bị đồng nhất về identity và lifecycle.
5. **Có exception không?** Thất bại từ `throw`, `failedFuture` và lỗi submit phải được quan sát, không coi là success.
6. **Có double scheduling không?** `supplyAsync` trong method `@Async` có đưa task sang một executor khác ngoài ý muốn?
7. **Có blocking để compose không?** Tránh `join()` trên future phụ thuộc cùng pool nhỏ.
8. **Payload mutable không?** Kiểm tra thread safety, ownership, snapshot/DTO trước khi expose.
9. **Có context và transaction không?** Worker có nhận đúng context và dọn sạch sau khi dùng?
10. **Timeout/cancel và late result?** Caller trả fallback có thể khiến task cũ tiếp tục cập nhật data; cần idempotency và giới hạn side effect.

## 13. Câu hỏi tự kiểm tra

**1. `CompletableFuture.completedFuture(7)` có dùng một thread mới không?**

Không. Nó tạo future đã completed ngay, không cần executor.

**2. Vì sao target method `@Async` trả completed future mà caller vẫn có thể nhận pending future?**

Vì target tính value bên trong worker rồi trả future tạm; caller nhận future do Spring proxy tạo để theo dõi **toàn bộ invocation**, gồm cả thời gian chờ chạy và tính toán.

**3. Nếu chỉ có `return completedFuture(slowQuery())` mà không có scheduling, `slowQuery` chạy ở đâu?**

Chạy trên caller thread trước khi factory được gọi, có thể block caller.

**4. Ví dụ demo cho `temporaryFutureDone=true` nhưng `proxyFutureDoneBeforeReturn=false` nhờ đâu?**

Nhờ worker đã tạo future tạm và mở latch `temporaryReady`, nhưng vẫn bị giữ ở `allowReturn` trước khi target method return. Proxy future chưa được hoàn tất.

**5. Dùng `supplyAsync` bên trong `@Async("lessonExecutor")` có nhất thiết tốt hơn không?**

Không. Có thể tạo thêm một task trên common pool hoặc executor khác, gây khó quản lý scheduling và context; nếu đã tính đồng bộ trong worker thì `completedFuture(result)` thường phù hợp hơn.

**6. Khi muốn biểu diễn lỗi đã xác định, dùng `completedFuture(error)` hay `failedFuture(error)`?**

Dùng `failedFuture(error)` để completion exceptional. `completedFuture(error)` có thể coi object lỗi là giá trị thành công.

**7. Nếu caller gọi `proxyFuture.get()` ngay, caller có tiếp tục xử lý việc khác không?**

Không trong lúc đợi; chính thread caller bị block cho đến khi future hoàn tất hoặc chờ bị ngắt.

**8. Một future completed với `List<Order>` có tự trở thành deep immutable không?**

Không. Future không thay đổi tính mutable của object, cần chính sách dữ liệu và đồng bộ riêng.

### Ghi nhớ

`CompletableFuture.completedFuture(value)` chỉ nói rằng **value đã sẵn có và future được hoàn tất thành công**. Trong một method Spring `@Async` được gọi qua proxy, **việc bất đồng bộ nằm ở đường proxy/executor**; target có thể dùng completed future tạm như một cách chuẩn để chuyển giá trị đã tính trong worker tới caller. Luôn tách bạch *chỗ tính giá trị*, *đường submit*, *future thực tế của caller*, *ngoại lệ* và *vòng đời của tác vụ*.

### Tài liệu tham khảo chính thức

- [Spring Framework — `@Async` Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/Async.html): hợp đồng future của proxy và future tạm của target.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@EnableAsync`, executor, `@Async` và return type.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `completedFuture`, `failedFuture`, `supplyAsync`, composition, timeout và cancellation.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): kết quả, chờ và hủy.
