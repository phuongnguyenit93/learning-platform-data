# Không gọi get() hoặc join() ngay lập tức nếu mục tiêu là chồng lấp công việc

## 1. Vấn đề: có Future nhưng vẫn chạy tuần tự

Trong Spring Framework, phương thức được đánh dấu `@Async` có thể chạy trên `TaskExecutor` và trả về `Future<T>` hoặc `CompletableFuture<T>`. Tuy nhiên, **bất đồng bộ ở phía worker không đồng nghĩa caller đang tận dụng được tính đồng thời**. Nếu sau mỗi lần gọi bạn lập tức chờ kết quả bằng `get()` hoặc `join()`, caller sẽ dừng tại lần chờ đó và **chưa kịp gửi công việc độc lập tiếp theo**.

Ví dụ tưởng là song song:

~~~java
String inventory = inventoryService.loadAsync().join();
String price = pricingService.loadAsync().join();
return inventory + " / " + price;
~~~

Đây là **đoạn code minh họa**, giả định hai service bean thực sự trả `CompletableFuture<String>` từ các method `@Async` hợp lệ. Lệnh đầu tiên gửi yêu cầu lấy tồn kho rồi **đợi nó hoàn thành**; chỉ sau đó mới gọi tới giá. Hai hoạt động độc lập không được khởi động cùng lúc.

Thay bằng:

~~~java
CompletableFuture<String> inventory = inventoryService.loadAsync();
CompletableFuture<String> price = pricingService.loadAsync();

return inventory.thenCombine(price, (stock, amount) ->
        stock + " / " + amount);
~~~

Đoạn thứ hai giả định phương thức chứa code trả `CompletableFuture<String>`. Nó **gửi cả hai công việc trước**, rồi tạo future của kết quả kết hợp. Caller không cần chặn tại mỗi lần gửi. Trong thực tế, hai tác vụ chỉ có thể chạy chồng lấp khi executor, tài nguyên, khóa và downstream cho phép; `CompletableFuture` không tự bảo đảm nhiều worker đang chạy đồng thời.

**Quy tắc cốt lõi:** nếu các công việc độc lập, hãy **khởi động tất cả công việc cần chạy đồng thời trước**, sau đó mới **phối hợp kết quả hoặc chờ tại ranh giới thật sự cần kết quả**. Không bỏ hoàn toàn việc chờ; chỉ đặt điểm chờ đúng vị trí.

## 2. Phân biệt ba thời điểm: submit, execution và await

~~~text
Thời gian ------------------------------------------------------------>

Cách dễ vô tình tuần tự:
Caller:  submit A |====== get(A) ======| submit B |==== join(B) ====|
Worker:      [------- A -------]                  [------ B ------]

Cách cho phép chồng lấp:
Caller:  submit A -> submit B -> làm việc C -> phối hợp -> | chờ nếu cần |
Worker 1:    [------- A --------]
Worker 2:         [---------- B ---------]
Caller C:              [-- C --]
~~~

Sơ đồ trên chỉ minh họa vị trí chặn; độ dài thực tế tùy thời gian task, thread availability và scheduling. Hai thao tác submit liên tiếp **không bắt buộc** dẫn tới hai thread đang chạy cùng lúc. Chúng có thể nằm trong queue nếu pool không đủ năng lực.

### 2.1. Khi nào mỗi hành động xảy ra?

| Hành động | Điều gì xảy ra? | Caller có bị chặn chờ kết quả không? |
| --- | --- | --- |
| `worker.workAsync()` qua Spring proxy | Interceptor gửi phần thực thi tới executor rồi trả một handle kết quả | Thông thường **không chờ** thân method hoàn thành, nhưng submission vẫn có thể bị ảnh hưởng bởi saturation/rejection |
| `CompletableFuture.supplyAsync(task, executor)` | Gửi task tới executor được chỉ định | Không chờ task hoàn thành khi submit thành công |
| `future.get()` | Đợi hoàn thành, trả giá trị hoặc ném exception tương ứng | **Có** nếu chưa xong |
| `future.join()` | Đợi hoàn thành, trả giá trị hoặc ném unchecked completion exception | **Có** nếu chưa xong |
| `future.thenApply(fn)` | Đăng ký bước biến đổi sau khi future trước xong | Không bắt caller chờ, nhưng callback có thể chạy ngay trên caller khi future đã hoàn thành |
| `future.thenCompose(fn)` | Ghép một bước tiếp theo trả future khác | Không bắt caller đợi từng bước; có **phụ thuộc dữ liệu** giữa hai bước |
| `a.thenCombine(b, fn)` | Tạo future kết hợp khi **cả a và b** thành công | Không buộc caller chờ ngay |
| `CompletableFuture.allOf(...)` | Tạo future hoàn thành khi mọi future đầu vào hoàn thành | Không chặn tại lúc đăng ký |
| `get(timeout, unit)` | Chặn nhưng có giới hạn thời gian chờ | Có; có thể ném `TimeoutException` |

**Điều quan trọng:** `get` và `join` không phải các API sai. Chúng phù hợp khi caller **thực sự phải đồng bộ** ở cuối xử lý, trong test/CLI hoặc tại ranh giới trả kết quả. Sai lầm nằm ở việc **chờ quá sớm khi vẫn còn việc độc lập chưa được gửi**.

## 3. Vì sao chờ ngay lập tức làm mất cơ hội overlap?

Giả sử có hai cuộc gọi I/O độc lập: A thường mất khoảng 400 ms, B thường mất khoảng 600 ms; thời gian chỉ dùng để minh họa, không phải cam kết.

Cách tuần tự:

~~~java
Result a = service.fetchAsync("A").join(); // đợi A
Result b = service.fetchAsync("B").join(); // bây giờ mới gửi B
consume(a, b);
~~~

Tổng thời gian chờ có thể gần **400 + 600 ms**, chưa kể overhead. Dù `fetchAsync` thật sự chạy trên worker, caller không cho B cơ hội khởi động trong lúc A chạy.

Cách tốt hơn:

~~~java
CompletableFuture<Result> aFuture = service.fetchAsync("A");
CompletableFuture<Result> bFuture = service.fetchAsync("B");

// Caller có thể tiếp tục xử lý việc khác không phụ thuộc kết quả.
prepareResponseMetadata();

// Chỉ khi cần cả hai mới đồng bộ:
Result a = aFuture.join();
Result b = bFuture.join();
consume(a, b);
~~~

Đoạn này là ví dụ khái niệm, cần `Result`, `service`, `prepareResponseMetadata` và `consume` trong ứng dụng. Nếu executor có đủ khả năng và hai tác vụ không khóa lẫn nhau, thời gian hoàn tất có thể tiến gần `max(400, 600)` thay vì tổng, nhưng **không được coi đây là bảo đảm hiệu năng**.

Nếu không muốn caller block ở cuối, hãy để hàm orchestration **trả `CompletableFuture`**:

~~~java
public CompletableFuture<CombinedResult> getCombined() {
    var a = service.fetchAsync("A");
    var b = service.fetchAsync("B");
    return a.thenCombine(b, CombinedResult::new);
}
~~~

Đây là một method minh họa, cần các kiểu `CombinedResult`, `service`, cấu hình Spring và import. Khi người dùng downstream cũng chấp nhận Future, ta có thể **duy trì pipeline bất đồng bộ** qua nhiều lớp. Nếu một tầng cuối bắt buộc trả giá trị đồng bộ, chỉ chờ ở **tầng đó**, với timeout và xử lý lỗi.

## 4. get() và join(): giống nhau ở việc chặn, khác nhau ở cách báo lỗi

### 4.1. Future.get()

Với `java.util.concurrent.Future<T>`:

~~~java
T result = future.get();
T resultWithTimeout = future.get(3, TimeUnit.SECONDS);
~~~

Hai dòng là những cách dùng **thay thế**, không đặt cùng phạm vi vì trùng tên biến. `get()` có thể chặn không giới hạn; `get(timeout, unit)` giới hạn thời gian chờ. Các exception checked thường gặp gồm:

- `InterruptedException`: thread đang chờ bị interrupt; nếu bắt để làm cleanup, thông thường phục hồi interrupt flag phù hợp.
- `ExecutionException`: task hoàn thành lỗi, có thể kiểm tra `getCause()`.
- `TimeoutException`: thời gian chờ đã vượt giới hạn.
- `CancellationException`: Future đã bị hủy (unchecked).

`get(timeout)` ném `TimeoutException` **không đồng nghĩa task đã dừng**; công việc có thể vẫn chạy và tiếp tục tác động lên hệ thống. Cần xử lý timeout của caller, cancellation, trạng thái job và downstream theo nghiệp vụ.

### 4.2. CompletableFuture.join()

`CompletableFuture<T>.join()` cũng chặn nếu future chưa hoàn tất, nhưng không buộc caller khai báo/bắt checked `InterruptedException` hay `ExecutionException`:

~~~java
String value = future.join();
~~~

Nếu Future thất bại, `join()` thường ném `CompletionException` (unchecked) bao bọc nguyên nhân; nếu bị hủy có thể ném `CancellationException`. `join()` **không có tham số timeout trực tiếp**. Với `CompletableFuture` cần timeout, có thể dùng `get(timeout, unit)`, hoặc xem xét `orTimeout`/`completeOnTimeout` theo hợp đồng của API.

**Đừng kết luận `join()` là “non-blocking” chỉ vì không khai báo checked exception.** `get()` và `join()` đều có thể chặn luồng tại điểm gọi.

### 4.3. Nếu future đã hoàn thành thì sao?

Khi future đã kết thúc, `get()` và `join()` có thể trả ngay hoặc ném lỗi ngay; chúng không nhất thiết tạo độ trễ. Lời khuyên "đừng chờ ngay" chủ yếu nhằm tránh việc caller bị giữ khi **chưa khởi động đủ các tác vụ có thể độc lập** hoặc đang ở thread không nên chặn.

## 5. Ba mẫu điều phối đúng

### Mẫu A — gửi trước, đợi sau (fork-then-join)

~~~java
CompletableFuture<Customer> customer = customerClient.getAsync(id);
CompletableFuture<Orders> orders = orderClient.listAsync(id);

// Công việc không phụ thuộc customer/orders.
AuditMetadata metadata = buildMetadata();

Customer c = customer.join();
Orders o = orders.join();
return assemble(c, o, metadata);
~~~

Đoạn minh họa này **chủ động có điểm join** ở cuối, sau khi đã khởi động cả hai công việc. Nó phù hợp khi hàm phải trả giá trị đồng bộ và thread caller **được phép chờ**. Nếu caller là request thread, cần xem timeout, tải và cách hệ thống web xử lý bất đồng bộ.

### Mẫu B — kết hợp kết quả mà không chặn caller

~~~java
public CompletableFuture<Overview> getOverview(String id) {
    var customer = customerClient.getAsync(id);
    var orders = orderClient.listAsync(id);
    return customer.thenCombine(orders, Overview::new);
}
~~~

Mảnh code minh họa cần các kiểu và bean đã khai báo. `thenCombine` chạy khi **cả hai** hoàn thành thành công, không cần caller gọi `join`. Nó là cách diễn tả “khi đủ hai kết quả, hãy làm bước tiếp”.

**Lưu ý về thread thực thi callback:** `thenCombine` không có hậu tố `Async` thường thực thi callback ở thread hoàn thành một stage hoặc ở thread đang đăng ký nếu các stage đã xong. Nếu bước ghép kết quả làm CPU nặng hoặc I/O blocking, cân nhắc `thenCombineAsync(fn, chosenExecutor)`, đồng thời tránh gây bão hòa chính pool cần để chạy các task còn lại.

### Mẫu C — nhiều future với allOf()

~~~java
List<CompletableFuture<String>> futures = List.of(
        service.runAsync("A"),
        service.runAsync("B"),
        service.runAsync("C"));

CompletableFuture<List<String>> results =
        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture<?>[0]))
                .thenApply(ignored ->
                        futures.stream()
                                .map(CompletableFuture::join)
                                .toList());
~~~

Mảnh minh họa cần `List`, `service` và import phù hợp. Ở đây:

1. Ba method được gọi trước, tạo ba Future.
2. `allOf` tạo Future kết thúc khi **tất cả** các Future đầu vào kết thúc.
3. `thenApply` chỉ chạy bình thường sau khi `allOf` hoàn thành thành công; lúc đó các `join()` để lấy giá trị **không còn phải chờ task**.
4. Nếu bất kỳ Future nào hoàn thành lỗi, `allOf` thường hoàn thành lỗi và callback `thenApply` không chạy. Phải xử lý lỗi ở pipeline nếu cần partial results.

`allOf()` **không tự tạo `List<T>` kết quả**; nó trả về `CompletableFuture<Void>`. Bước lấy kết quả cần thực hiện riêng. Đừng gắn `join` trong vòng lặp **đang tạo danh sách Future** theo kiểu “submit một việc rồi đợi ngay”, vì như vậy lại biến quá trình thành tuần tự.

## 6. Phân biệt công việc độc lập và công việc phụ thuộc

Không phải mọi `join` sớm đều vô lý. Nếu B **cần kết quả A làm đầu vào**, không thể khởi động B thực sự trước khi có A:

~~~java
// A hoàn tất rồi mới biết khóa để lấy B.
CompletableFuture<Account> account = accountService.findAsync(userId);

CompletableFuture<Profile> profile =
        account.thenCompose(a -> profileService.loadAsync(a.profileId()));
~~~

Mảnh code minh họa này dùng `thenCompose` vì callback trả về một Future khác. `thenApply` trong trường hợp này sẽ tạo `CompletableFuture<CompletableFuture<Profile>>` thay vì tự flatten kết quả. **`thenCompose` không tạo parallelism giữa A và B**, vì B thực sự phụ thuộc vào A; nhưng nó giúp orchestration không block thread trong lúc chờ.

Trong một workflow có ba tác vụ A, B, C:

- A và B **độc lập**: có thể submit cả hai ngay.
- C **phụ thuộc kết quả A+B**: dùng `thenCombine` hoặc `allOf` để kích hoạt C sau khi có đủ dữ liệu.
- D **không liên quan**: có thể được submit trước hoặc trong lúc A/B đang chạy.

Tư duy này xây một **đồ thị phụ thuộc (dependency graph)** thay vì chờ từng dòng code một cách máy móc.

~~~text
A ─────────┐
           ├──> C (cần A và B) ───> kết quả
B ─────────┘
D ─────────────────────────────────> công việc độc lập
~~~

Chỉ những cạnh **phụ thuộc thật sự** mới buộc phải chờ; phần độc lập mới có cơ hội chồng lấp.

## 7. Demo độc lập Spring: quan sát cả hai task bắt đầu trước khi caller chờ kết quả

Ví dụ này được thiết kế để **kiểm tra hành vi**, không phán đoán bằng tốc độ. Dùng **Java 17+, Spring Framework 6.1.14 và Gradle 8.5+**, không cần Spring Boot, HTTP server hay database.

Có hai method call `@Async` chạy trên một `ThreadPoolTaskExecutor` có **hai worker**. Cả hai worker báo tín hiệu qua `CountDownLatch` khi đã bắt đầu, rồi cùng chờ một latch khác. Caller khởi động **cả hai** trước, thực hiện một phép tính độc lập, quan sát hai worker đã vào method và mới cho chúng hoàn tất.

### 7.1. Cấu trúc project

~~~text
overlap-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/OverlapDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'overlap-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.OverlapDemo'
}
~~~

**src/main/java/demo/OverlapDemo.java**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class OverlapDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JobWorker worker = context.getBean(JobWorker.class);

            CountDownLatch bothStarted = new CountDownLatch(2);
            CountDownLatch release = new CountDownLatch(1);

            // Gửi cả hai task trước khi lấy bất kỳ kết quả nào.
            CompletableFuture<String> a =
                    worker.workAsync("A", bothStarted, release);
            CompletableFuture<String> b =
                    worker.workAsync("B", bothStarted, release);

            // Tạo future phối hợp, không block caller ở đây.
            CompletableFuture<String> combined =
                    a.thenCombine(b, (left, right) ->
                            left + "+" + right);

            try {
                // Caller tiếp tục xử lý phần độc lập.
                int callerComputation = 20 + 22;
                System.out.println("caller work: " +
                        (callerComputation == 42));

                // Chờ TÍN HIỆU test: cả hai worker đã vào method.
                if (!bothStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Two tasks did not start in time");
                }
                System.out.println("both tasks started: " +
                        (bothStarted.getCount() == 0));

                // Workers chưa thể hoàn tất vì đang chờ release.
                System.out.println("both futures pending: " +
                        (!a.isDone() && !b.isDone()));

                release.countDown();

                // Điểm đồng bộ cuối cùng: giờ mới cần kết quả.
                System.out.println("combined result: " +
                        combined.get(5, TimeUnit.SECONDS));
                System.out.println("both futures completed: " +
                        (a.isDone() && b.isDone()));
            } finally {
                // Tránh kẹt worker nếu test/quan sát thất bại.
                release.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("workerExecutor")
        public ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("overlap-worker-");
            return pool;
        }

        @Bean
        public JobWorker jobWorker() {
            return new JobWorker();
        }
    }

    public static class JobWorker {
        @Async("workerExecutor")
        public CompletableFuture<String> workAsync(
                String name,
                CountDownLatch started,
                CountDownLatch release) {

            started.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    return CompletableFuture.failedFuture(
                            new IllegalStateException(
                                    "Release latch timed out"));
                }
                return CompletableFuture.completedFuture(
                        name + "-done");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }
        }
    }
}
~~~

**Chạy** trong thư mục `overlap-demo`:

~~~bash
gradle run
~~~

Nếu có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

**Các dòng stdout do chương trình tự in**, khi hai worker khởi động và hoàn tất bình thường trong ngưỡng thời gian năm giây:

~~~text
caller work: true
both tasks started: true
both futures pending: true
combined result: A-done+B-done
both futures completed: true
~~~

Có thể xuất hiện log Spring hoặc Gradle ngoài năm dòng này. Demo **không khẳng định latency** hoặc hậu tố tên thread cụ thể. Nếu môi trường thiếu tài nguyên và worker không bắt đầu trong timeout, chương trình ném exception thay vì xem đó là kết quả thành công.

### 7.2. Vì sao demo xác minh được overlap?

1. `Config` bật `@EnableAsync`; `JobWorker` được container tạo và method `workAsync` gọi từ code bên ngoài bean qua Spring proxy.
2. `workerExecutor` có hai worker và nhận hai task A/B.
3. Mỗi worker giảm `bothStarted` rồi chờ `release`. Việc `bothStarted` về 0 **chỉ có thể xảy ra khi cả hai method đã bắt đầu chạy**, không chỉ nằm trong queue.
4. Khi caller đọc `both futures pending`, chưa worker nào được thả, nên hai CompletableFuture vẫn chưa kết thúc.
5. Caller thả latch, hai worker hoàn thành. Future `combined` tự hoàn thành khi cả A và B có kết quả; caller chỉ gọi `get(timeout)` tại ranh giới cần in kết quả.
6. Nếu đổi code thành `worker.workAsync("A", ...).get()` **trước khi** submit B, caller sẽ chờ A trong lúc A đợi `release`; không bao giờ đến được bước submit B theo trình tự như ví dụ. Trường hợp thử nghiệm này minh họa rõ việc chờ quá sớm đã phá cơ hội overlap.

`CountDownLatch` ở đây phục vụ **kiểm thử có kiểm soát**, không phải yêu cầu phải có latch trong mọi chương trình `@Async`. Trong production, công việc thực thường chờ I/O, xử lý CPU hoặc phối hợp với hệ thống ngoài; `CompletableFuture`/Future thể hiện trạng thái hoàn thành.

## 8. Áp dụng vào service và controller Spring

### 8.1. Tầng service trả future thay vì chờ bên trong

Không nên viết một method đồng bộ chứa hai `join` sớm rồi trả giá trị:

~~~java
public DashboardData loadDashboard() {
    var account = accountService.getAsync().join();
    var orders = orderService.listAsync().join();
    return new DashboardData(account, orders);
}
~~~

Thay vào đó, nếu API có thể bất đồng bộ:

~~~java
public CompletableFuture<DashboardData> loadDashboardAsync() {
    var account = accountService.getAsync();
    var orders = orderService.listAsync();
    return account.thenCombine(orders, DashboardData::new);
}
~~~

Hai method trên là **mảnh code minh họa**, cần các dependency/service/kiểu dữ liệu tương ứng. Tầng gọi quyết định khi nào cần await. Khi áp dụng `@Async` cho method của service, phải nhớ **self-invocation** trong proxy mode mặc định không kích hoạt interception; nên inject một Spring-managed worker bean và gọi qua proxy.

### 8.2. Trong Spring MVC

Controller có thể trả `CompletableFuture` hoặc kiểu kết quả bất đồng bộ mà MVC hỗ trợ, để Spring quản lý ranh giới async request. Cần chọn cơ chế tương thích với kiểu trả về, timeout và cấu hình MVC.

Đoạn minh họa (cần spring-webmvc, import và các bean phù hợp):

~~~java
@RestController
class DashboardController {
    private final DashboardService service;

    DashboardController(DashboardService service) {
        this.service = service;
    }

    @GetMapping("/dashboard")
    public CompletableFuture<DashboardData> dashboard() {
        return service.loadDashboardAsync();
    }
}
~~~

Điểm chính là không lấy `service.loadDashboardAsync().join()` ngay trong controller nếu mục tiêu là **giải phóng request thread**. Tuy nhiên, kiểu trả về Future **không tạo ra khả năng thực thi vô hạn**; vẫn cần timeout, giới hạn số async requests, queue/rejection policy và kết nối downstream.

Một request HTTP cuối cùng vẫn cần kết quả để phản hồi. **Không block tại controller** khác với **không bao giờ phải đợi kết quả**: MVC có thể quản lý việc đợi/dispatch thông qua cơ chế asynchronous request processing của nó. Không dùng Future tùy tiện để che một operation blocking bên trong mà không đánh giá resource.

### 8.3. Trong scheduled job hoặc message consumer

Một tác vụ theo lịch có thể submit các tác vụ độc lập và phối hợp kết quả bằng Future, nhưng cần xem vòng đời callback: nếu scheduler callback chờ `join()` lâu, nó có thể giữ thread scheduler, làm các lần kích hoạt khác bị trì hoãn. Nếu callback submit rồi trả về ngay, các lần lịch tiếp theo có thể **chồng lấp công việc nền**; cần cơ chế deduplication hoặc giới hạn số job đang chạy nếu nghiệp vụ không cho phép.

Với message listener, đừng chỉ submit async rồi **acknowledge message ngay** nếu hệ thống yêu cầu xử lý thành công trước ack. Chỗ nào chờ hoặc gửi ack phụ thuộc delivery contract. `@Async` và Future trong bộ nhớ không bảo đảm khôi phục task sau process crash.

## 9. Xử lý lỗi, timeout và cancellation mà không phá tính bất đồng bộ

### 9.1. Xử lý lỗi trong chuỗi Future

~~~java
CompletableFuture<String> safe = worker.workAsync()
        .exceptionally(error -> {
            logFailure(error);
            return "fallback";
        });
~~~

Đây là mảnh minh họa, cần bean `worker`, method `logFailure` và kiểu trả phù hợp. `exceptionally` tạo một stage dùng giá trị thay thế khi stage trước hoàn thành lỗi; **không tự retry** công việc bị lỗi và cũng không bảo đảm rollback side effect.

Để chỉ quan sát lỗi mà vẫn giữ trạng thái exceptional:

~~~java
CompletableFuture<String> observed = worker.workAsync()
        .whenComplete((value, error) -> {
            if (error != null) {
                logFailure(error);
            }
        });
~~~

Callback trong `whenComplete` không tự biến failure thành success. Với các stage ghép, cần xác định rõ việc một nhánh fail thì bỏ cả tác vụ, dùng fallback hay cho kết quả một phần.

### 9.2. Dùng timeout đúng mục đích

~~~java
CompletableFuture<String> task = worker.workAsync();
String value = task.get(3, TimeUnit.SECONDS);
~~~

Ví dụ này **chủ động chờ** tối đa ba giây tại ranh giới cần kết quả. `get(timeout)` timeout **không tự dừng task**. Nếu caller phải trả HTTP trong ngưỡng thời gian, hãy quyết định xử lý task còn chạy, cancellation, retry và idempotency.

Với `CompletableFuture`:

~~~java
CompletableFuture<String> timed = worker.workAsync()
        .orTimeout(3, TimeUnit.SECONDS);
~~~

`orTimeout` có thể **hoàn thành exceptional chính CompletableFuture nhận được** sau timeout; nó không bắt buộc hủy computation thực đang chạy dưới executor. `completeOnTimeout` thay bằng một giá trị mặc định nếu chưa xong. Không dùng timeout như biện pháp thay cho admission control hoặc task cancellation.

### 9.3. Đừng bỏ quên các Future

Tránh tình huống “fire-and-forget vô chủ”:

~~~java
worker.sendAsync(data); // không lưu handle, không xử lý lỗi/ack
~~~

Mảnh minh họa trên **không mặc định sai**, nhưng với tác vụ có giá trị nghiệp vụ, caller nên có cách ghi trạng thái, theo dõi failure hoặc retry. Với `@Async void`, exception từ worker không thể tự ném đồng bộ lại caller; có thể cấu hình `AsyncUncaughtExceptionHandler`, log và metrics. Nếu thao tác phải survive restart, dùng job store, outbox hoặc broker bền vững chứ không chỉ lưu Future trong heap.

## 10. Overlap phụ thuộc tài nguyên, không chỉ phụ thuộc cách gọi

Không gọi `join` ngay **chỉ tạo cơ hội** chạy đồng thời. Còn có các giới hạn:

| Giới hạn | Ảnh hưởng |
| --- | --- |
| Executor chỉ có một worker | A và B thường được chạy lần lượt dù submit cùng lúc |
| Pool queue đầy | Task bị từ chối; handler như DiscardPolicy có thể bỏ task âm thầm |
| Pool dùng CallerRunsPolicy | Khi bão hòa, caller có thể chạy task ngay, làm lời gọi submit bị chặn |
| Hai task tranh cùng một khóa | Chỉ một task vào critical section một lúc |
| DataSource pool có một connection | Hai worker có thể chờ cùng tài nguyên, throughput không tăng |
| Downstream giới hạn rate/connections | Gửi song song có thể tăng lỗi 429/503 hoặc timeouts |
| Workload CPU-bound trên ít core | Tăng worker quá mức có thể tăng context switching và chậm hơn |
| Task gắn transaction/ThreadLocal | Chuyển sang worker có thể mất context cần thiết nếu không truyền đúng |

**Cấu hình executor cần có mục đích.** Với `ThreadPoolTaskExecutor`, corePoolSize, maxPoolSize, queueCapacity và rejection handler tương tác với nhau. Một queue lớn có thể giữ nhiều request nhưng tăng độ trễ và bộ nhớ. Một pool quá ít worker sẽ không giúp A/B chạy chồng lấp dù orchestrator đã submit cả hai.

Thêm thread không biến blocking I/O thành non-blocking và không tự làm class singleton an toàn luồng. Những property `spring.task.execution.*` của Spring Boot chỉ áp dụng theo quy tắc auto-configuration tương ứng; ứng dụng Spring Framework thuần trong demo không đọc các property Boot này.

### 10.1. Nguy cơ thread starvation deadlock khi chờ Future bên trong pool

Ví dụ giả định executor chỉ có **một worker** và một queue có chỗ:

~~~java
executor.execute(() -> {
    Future<String> child = executor.submit(() -> "child result");
    String result = child.get(); // worker duy nhất đang chờ child
    use(result);
});
~~~

Đoạn này chỉ nhằm minh họa (cần bao ngoài xử lý checked exception, executor và `use`). Parent task chiếm worker và đợi child. Nhưng child nằm trong queue, cần worker đó để chạy: **thread starvation deadlock**. Có timeout thì parent có thể thoát khỏi việc đợi; nó không làm thiết kế chờ này trở thành tối ưu.

Để giảm nguy cơ, biểu diễn pipeline bằng continuation, không block worker khi đang đợi một task khác chạy trên chính pool hạn chế. Nếu các bước phụ thuộc hoàn toàn theo trình tự, đôi khi **gọi trực tiếp trên một worker** lại đơn giản hơn submit con rồi đợi. Cần tính pool, queue và dependency graph cùng nhau.

## 11. Transaction, context và singleton khi chồng lấp công việc

Trong Spring, `@Transactional` của caller thường gắn với **thread hiện tại**. Khi `@Async` dùng worker khác, transaction context **không tự động được truyền**. Hai query async chạy đồng thời cũng có thể cần hai database connections/transaction độc lập. Một yêu cầu vừa ghi dữ liệu trong transaction chưa commit, rồi submit worker truy vấn ngay, có thể gặp dữ liệu chưa nhìn thấy.

Không giữ một transaction dài trên request thread chỉ để chờ nhiều Future nếu không có lý do rõ ràng. Với thao tác phải xảy ra sau commit, cân nhắc after-commit event hoặc transactional outbox tùy yêu cầu nhất quán và durability.

Các `ThreadLocal` như MDC, SecurityContext, request attributes cũng không tự lan truyền qua thread pool; dùng cơ chế capture/restore hoặc `TaskDecorator` thích hợp khi cần. Đừng nhúng dữ liệu người dùng nhạy cảm vào tên thread để theo dõi tác vụ; nên sử dụng structured log/tracing.

Một `@Service` Spring mặc định singleton có thể bị nhiều worker gọi đồng thời. Tránh đặt request-specific mutable fields trên bean; truyền immutable DTO/record hoặc snapshot và sử dụng cơ chế đồng bộ thích hợp cho shared mutable state. Thay đổi cách phối hợp Future không tự loại bỏ data races.

## 12. Kiểm tra hiệu quả và viết test ổn định

### 12.1. Đo điều đúng

Đừng chỉ so thời gian một lần chạy, vì JVM warmup, cache, scheduling, network và latency downstream làm số đo dao động. Hãy quan sát:

- **Task submit time** và số task đã gửi.
- **Thời điểm worker bắt đầu/kết thúc** để xác nhận thời gian xử lý thực sự chồng lấp.
- **Queue wait time**, active threads, queue depth và rejection.
- **Caller blocked time** ở `get()`, `join()` hoặc điểm chờ khác.
- **Thời gian đáp ứng end-to-end** và chi phí cho hệ thống ngoài.

Hai Future được tạo gần nhau không chắc worker đã chạy đồng thời. Demo ở mục 7 dùng `CountDownLatch` để xác minh **cả hai method đã vào worker trước khi được thả** — bằng chứng mạnh hơn phép đo thời gian ngẫu nhiên.

### 12.2. Test các trường hợp bất thường

1. Một trong hai tác vụ ném lỗi: future kết hợp có thể hoàn thành lỗi, cần assert cause đúng.
2. Một nhánh rất chậm: áp dụng timeout và quyết định nhánh khác sẽ tiếp tục hay bị hủy.
3. Executor chỉ có một worker: không nên assert song song thực tế nếu không có capacity.
4. Executor từ chối task: phải có failure signal hoặc cơ chế thay thế theo contract.
5. Caller bị interrupt khi đang `get()`: xử lý interrupt phù hợp và không đánh đồng với task fail.
6. Một task phụ thuộc vào task khác: dùng `thenCompose`, không cố chạy nhánh phụ thuộc trước dữ liệu đầu vào.
7. Độ tải cao: xác nhận giới hạn concurrency, response timeout và số tác vụ dồn hàng đợi.
8. Có job trạng thái lâu dài: kiểm tra job store, restart/retry và idempotency.

### 12.3. Kiểm tra @Async thực sự chạy qua Spring

Nếu gọi method được `@Async` đánh dấu mà code chạy đồng bộ, xem lại:

- `@EnableAsync` có được bật trong đúng ApplicationContext chưa?
- Worker có được Spring quản lý và caller có inject proxy từ container không?
- Có đang tự gọi `this.asyncMethod()` trong cùng bean không?
- Method có thể được Spring proxy intercept không (thực tế hay dùng public, non-final)?
- `@Async("executorName")` trỏ đến đúng bean executor không?
- Caller có đang `join()` ngay nên **trông** như toàn bộ chuỗi đồng bộ dù method đã async không?

Phải phân biệt **annotation không hoạt động** với **annotation hoạt động nhưng điểm chờ đặt quá sớm**; cách sửa hoàn toàn khác nhau.

## 13. Anti-pattern và cách sửa nhanh

| Anti-pattern | Hệ quả | Thay bằng |
| --- | --- | --- |
| `aAsync().join(); bAsync().join();` khi A/B độc lập | Không khởi động B trước khi xong A | Tạo Future A và B trước, chờ hoặc combine sau |
| `future.get()` ngay trong HTTP controller | Giữ request thread chờ | Trả Future/kiểu async MVC thích hợp, cấu hình timeout |
| `stream.map(item -> async(item).join())` | Có thể submit rồi chờ từng item, thành gần tuần tự | `map(async)` ra danh sách Future, `allOf` sau |
| `CompletableFuture.supplyAsync(task)` không chỉ định pool | Thường dùng ForkJoin commonPool, không lấy pool Spring tự định nghĩa | `supplyAsync(task, explicitExecutor)` hoặc Spring-managed `@Async` |
| `allOf(...)` nhưng quên lấy từng kết quả | Chỉ có CompletableFuture<Void> | `thenApply` lấy kết quả sau khi allOf hoàn tất |
| `join()` trong worker rồi submit child lên cùng single-thread pool | Dễ starvation/deadlock | Dùng continuation hoặc cấu hình lại dependency và pool |
| Tạo hàng nghìn Future rồi allOf một lần không giới hạn | Quá tải pool, DB, network hoặc bộ nhớ | Bounded concurrency, pagination, rate limit |
| Không quan sát Future sau dispatch | Lỗi nền không ai xử lý | Error handler, status, metrics, tracing |
| `get(timeout)` rồi nghĩ task đã dừng | Task vẫn có thể chạy sau timeout | Quy định cancel/timeout ở tầng công việc và downstream |
| Xem CompletableFuture là bảo đảm task sẽ survive restart | Future chỉ sống trong process | Durable queue, outbox hoặc job store |

## 14. Quy trình refactor từ code chờ sớm sang phối hợp đúng

**Bước 1.** Vẽ đồ thị phụ thuộc: task nào độc lập, task nào cần kết quả task trước? Không ép song song các thao tác có thứ tự bắt buộc.

**Bước 2.** Kiểm tra async infrastructure: `@EnableAsync`, worker managed bean, lời gọi qua proxy, executor và queue capacity. Nếu `@Async` không hoạt động, sửa điều đó trước khi tối ưu `join`.

**Bước 3.** Thay code khởi động rồi chờ ngay bằng **khởi động toàn bộ nhánh độc lập trước**:

~~~java
var a = workerA.calculateAsync();
var b = workerB.calculateAsync();
~~~

Đây là đoạn minh họa, giả định cả hai trả `CompletableFuture` và được gọi đúng từ Spring-managed bean.

**Bước 4.** Nếu caller phải trả kết quả đồng bộ, đợi ở ranh giới muộn nhất hợp lý; nếu có thể trả async, **trả pipeline Future**:

~~~java
return a.thenCombine(b, Aggregate::new);
~~~

**Bước 5.** Chọn timeout, cách handle exception, cancellation và retry. Đặc biệt không lờ lỗi trên worker.

**Bước 6.** Đặt giới hạn concurrency theo CPU, connection pool, downstream rate limit và mục tiêu độ trễ; không dùng async để biến quá tải thành hàng đợi vô hạn.

**Bước 7.** Kiểm thử bằng latch hoặc instrumentation để xác nhận worker thực sự chồng lấp và kết quả cuối đúng. Đo thêm request latency, queue wait và error/rejection.

## 15. Câu hỏi tự kiểm tra

1. **Vì sao gọi `get()` ngay sau `@Async` có thể làm hai công việc A/B độc lập chạy tuần tự?** Vì caller chờ A hoàn tất trước khi có cơ hội gửi B.
2. **`join()` có non-blocking hơn `get()` không?** Không. Cả hai có thể block; khác nhau chủ yếu ở cơ chế exception/API.
3. **Đổi từ `get` sang `join` có tự tạo overlap không?** Không; phải thay vị trí chờ và thực sự submit các nhánh độc lập.
4. **Gửi hai Future trước rồi `join` ở cuối có hợp lệ không?** Có, khi caller được phép đồng bộ ở điểm đó và timeout/error được cân nhắc.
5. **Tại sao `thenCombine` phù hợp với hai tác vụ độc lập?** Nó tạo kết quả khi cả hai hoàn tất mà không bắt caller chờ tại lúc đăng ký.
6. **Khi B phụ thuộc dữ liệu do A trả về, API nào phù hợp?** `thenCompose`, vì callback trả Future và sự phụ thuộc là thật.
7. **`allOf` có trả thẳng danh sách giá trị không?** Không; nó trả `CompletableFuture<Void>`, cần bước tập hợp kết quả.
8. **Có hai Future thì chắc chắn dùng hai worker cùng lúc không?** Không. Phụ thuộc executor, queue, khóa và downstream.
9. **Future `get(timeout)` ném TimeoutException thì task đã dừng chưa?** Chưa chắc; timeout chờ không tự hủy computation.
10. **Vì sao chờ Future trong một worker single-thread pool có thể deadlock?** Nếu worker đang đợi một child task cũng cần chính worker đó để chạy.
11. **Trong Spring MVC, vì sao trả `CompletableFuture` thường hữu ích hơn `join` trong controller?** Nó cho phép framework quản lý async request thay vì giữ request thread chờ đồng bộ, khi cơ chế tương thích.
12. **Tách `@Async` sang executor có tự truyền transaction và ThreadLocal không?** Không; cần thiết kế context/transaction riêng.
13. **Làm sao chứng minh overlap thay vì chỉ xem thời gian?** Khống chế đồng bộ bằng latch hoặc đo chính xác interval của hai worker; demo mục 7 xác minh cả hai đã bắt đầu trước khi thả.
14. **Có nên tránh `join` ở mọi nơi không?** Không. Nó cần thiết trong một số ranh giới đồng bộ; điều cần tránh là **chờ quá sớm** và **chờ trong thread nhạy cảm khi có lựa chọn tốt hơn**.

**Ghi nhớ:** `@Async` giúp **gửi công việc**, còn `CompletableFuture` giúp **phối hợp kết quả**. Muốn các công việc độc lập có cơ hội chạy chồng lấp, hãy **gửi chúng trước**, **không gọi `get()`/`join()` ngay sau mỗi lần gửi**, và chỉ đợi ở nơi thực sự cần kết quả. Đồng thời kiểm soát executor, lỗi, timeout và tài nguyên — async không tự bảo đảm hiệu năng hay độ bền công việc.

### Tài liệu chính thức

- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Async Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.1 — @Async API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
