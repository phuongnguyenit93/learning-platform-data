# Giới hạn thời gian xác minh và dọn scheduler sau test

Trong nhóm kiến thức **Luồng Reactive** của Spring Boot, test `Mono`/`Flux` cần bảo vệ **hai hợp đồng khác nhau**: (1) kết quả và tín hiệu của publisher phải được xác minh trong một khoảng chờ hữu hạn; (2) scheduler, subscription và các tài nguyên do test tạo phải được **dọn đúng quyền sở hữu**, tránh rò thread hoặc làm hỏng những test khác.

Nếu dùng `StepVerifier.verify()` không có thời hạn, một pipeline mắc kẹt có thể khiến test chờ vô hạn. Ngược lại, nếu cứ gọi `Schedulers.shutdownNow()` sau từng test, bạn có thể đóng nhầm các scheduler Reactor dùng chung trong cùng JVM. Kết quả thường là bộ test chạy riêng thì xanh, chạy cả suite hoặc chạy song song thì lỗi thất thường.

**Ba công cụ khác nhau không nên đánh đồng:**

- **`StepVerifier.verify(Duration)`:** giới hạn *thời gian thực* mà verifier chờ kịch bản hoàn thành; hết hạn → assertion của test thất bại.
- **Operator `.timeout(Duration)`:** là một phần của pipeline nghiệp vụ; quá hạn có thể tạo `onError(TimeoutException)` hoặc fallback theo cấu hình.
- **`StepVerifier.withVirtualTime(...)` / `VirtualTimeScheduler`:** mô phỏng thời gian mà scheduler nhìn thấy; giúp kiểm tra timer/delay/backoff dài mà không phải ngủ thật.

Bài học trình bày cách chọn timeout, quản lý `Scheduler.dispose()` và `VirtualTimeScheduler.reset()`, tránh chạm vào scheduler dùng chung, và cung cấp mã **Java 17+, JUnit Jupiter + reactor-test** có thể chạy trong project Spring Boot với dependencies phù hợp.

## 1. Các tín hiệu cần kiểm tra trong một luồng Reactive

Reactive Streams diễn ra khi subscriber đăng ký nhận dữ liệu:

```text
Test subscriber                     Publisher
      |                                 |
      |---------- subscribe ---------->|
      |<--------- onSubscribe ----------|
      |----------- request(n) --------->|
      |<------------ onNext(A) ---------|
      |<------------ onNext(B) ---------|
      |<--- onComplete() HOẶC onError() -|
      |
      +-- Có thể cancel subscription trước terminal event
```

Trong một publisher tuân thủ đặc tả, `onComplete` và `onError` là **hai cách kết thúc loại trừ nhau**. `Mono<T>` phát tối đa một `onNext`; `Flux<T>` có thể phát 0, 1, nhiều hoặc vô hạn phần tử. Một số publisher như `Mono.never()` và `Flux.never()` không tự phát terminal signal.

Ví dụ các kịch bản StepVerifier:

```java
StepVerifier.create(Mono.just("ok"))
        .expectNext("ok")
        .verifyComplete();

StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .verifyComplete();

StepVerifier.create(Mono.empty())
        .verifyComplete();
```

Đây là những snippet nằm trong test method có imports Reactor phù hợp. Các case đồng bộ hoàn tất ngay. Nhưng khi nguồn là HTTP, DB, timer, event stream hoặc một chuỗi đợi demand, cần thêm **verification deadline** nếu nguy cơ kẹt là có thật.

Một test chỉ xây kịch bản `StepVerifier.create(...).expectNext(...)` mà **không gọi** `verify()`/`verifyComplete()` thì chưa thực hiện xác minh. Mục tiêu không phải đặt một đồng hồ cho đẹp mà là thực sự subscribe, quan sát các `onNext` và nhận terminal signal đúng.

## 2. So sánh các timeout và phạm vi tác động

| Cơ chế | Đối tượng bị giới hạn | Khi hết hạn | Có thay đổi publisher nghiệp vụ? |
| --- | --- | --- | --- |
| `verify(Duration.ofSeconds(3))` | Một lượt xác minh StepVerifier | Thất bại bằng `AssertionError` | **Không** |
| `StepVerifier.setDefaultTimeout(...)` | Các verifier tạo **sau** khi đặt policy global | Áp dụng default ở các `verify()` mới | Không, nhưng đổi global test configuration |
| `Mono.timeout(Duration)` | Thời gian chờ tín hiệu của pipeline | `onError(TimeoutException)` nếu không có fallback | **Có** |
| `withVirtualTime(...)` | Clock của scheduler tương thích | Test có thể advance thời gian ảo | Ảnh hưởng thời gian quan sát của operator trong test |
| JUnit Jupiter `@Timeout` | Toàn bộ test method/lifecycle theo runner | JUnit báo test quá hạn | Không tự sửa tín hiệu Reactor |
| Build/CI timeout | Task test hoặc toàn build | Hệ thống chạy test dừng quá hạn | Không phải một assertion Reactor |

**Đơn vị đo rất quan trọng:** `StepVerifier.verify(Duration.ofSeconds(3))` vẫn kiểm soát **ba giây thực**, kể cả khi bên trong verifier đang advance ba ngày ảo. `thenAwait(Duration.ofDays(3))` dưới `withVirtualTime` có thể xong gần như tức thì nếu các operator dùng virtual scheduler.

**Không có timeout mặc định hữu hạn:** Reactor Test ghi nhận `StepVerifier.verify()` mặc định có thể chờ không giới hạn. Đặc biệt khi dùng `StepVerifier.create(publisher, 0)` nhưng quên `thenRequest(n)`, kịch bản đòi `onNext` có thể không bao giờ tiến triển.

## 3. Dùng verify(Duration) để bảo vệ từng test

Thay vì dựa vào một global timeout dễ tác động test khác, ưu tiên đặt budget ngay tại verification:

```java
StepVerifier.create(Flux.just(10, 20, 30))
        .expectNext(10, 20, 30)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

`expectComplete()` khai báo terminal signal; `verify(Duration)` thực hiện subscribe, kiểm tra các tín hiệu và trả về thời lượng thực của verification. Phần này tương đương việc đặt terminal expectation rồi verify, nhưng cho biết rõ giới hạn chờ.

**Cần phân biệt các API:**

- `verifyComplete()`: shortcut khai báo completion và thực hiện verify, dùng default timeout nếu đã cấu hình. Không nên coi nó là một timeout hữu hạn khi chưa set default.
- `expectComplete().verify(Duration)`: điều khiển timeout **trên từng test**, thường là lựa chọn dễ bảo trì.
- `expectError(IllegalArgumentException.class).verify(Duration)`: đòi publisher kết thúc bằng error trong budget; không kỳ vọng complete sau error.
- `thenCancel().verify(Duration)`: chủ động hủy stream chưa có terminal signal; test xác minh kịch bản cancellation.
- `verify(Duration.ZERO)`: theo API Reactor, `Duration.ZERO` nghĩa là **chờ không giới hạn**, không phải deadline bằng 0 ms.

Giới hạn 3 giây ở ví dụ trên **không phải SLA nghiệp vụ**. Đó là safety net để CI tránh treo trong trường hợp nguồn không hoàn tất do bug. Các deadline nghiệp vụ phải được xác định bằng yêu cầu ứng dụng và test riêng.

### Bắt được một verification timeout cố ý

```java
@Test
void neverCompletingPublisherHitsVerificationGuard() {
    assertThrows(AssertionError.class,
            () -> StepVerifier.create(Mono.never())
                    .expectComplete()
                    .verify(Duration.ofMillis(150)));
}
```

Đoạn này cần imports `org.junit.jupiter.api.Test` và static `assertThrows`. **JUnit test pass vì một assertion failure từ StepVerifier là kết quả được mong đợi trong case minh họa**. Nếu bỏ ngưỡng thời gian và gọi `verify()`, `Mono.never()` có thể giữ thread chờ mãi.

Không cần kiểm tra đúng từng chữ trong thông báo `AssertionError`: nội dung message có thể thay đổi giữa các bản Reactor; thứ cần chứng minh là verifier có giới hạn chờ và báo thất bại đúng loại.

## 4. Ngưỡng global của StepVerifier: dùng được nhưng phải dọn

Reactor Test hỗ trợ:

```java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
// Những StepVerifier được tạo SAU lời gọi này dùng default mới.

StepVerifier.resetDefaultTimeout();
// Trở về default "không giới hạn" cho các verifier tạo sau.
```

Đây là thiết lập **static/global trong JVM**, không scoped theo JUnit test method. Cần lưu ý:

1. Chính sách mới chỉ áp dụng cho verifier được tạo sau lần thay đổi; **không tự viết lại cấu hình của verifier đã tạo trước đó**.
2. Nó có thể ảnh hưởng các test ở class khác nếu chạy cùng JVM.
3. `resetDefaultTimeout()` trả về mặc định **không giới hạn**, không hứa khôi phục một timeout tùy chỉnh mà suite khác đã đặt.
4. Test song song có thể race: test A set 3 giây, test B tạo verifier, test A reset trước khi B tạo/verifies tiếp.
5. Một `@AfterEach` dùng reset có thể dọn thay đổi của test hiện tại, nhưng **không biến global mutable state thành an toàn trong parallel suite**.

Ví dụ class **chỉ dành cho suite chạy tuần tự và đang chủ động sở hữu chính sách default**:

```java
package example.testing.time;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class GlobalVerifierBudgetTest {
    @BeforeEach
    void setBudget() {
        StepVerifier.setDefaultTimeout(Duration.ofSeconds(3));
    }

    @AfterEach
    void resetBudget() {
        StepVerifier.resetDefaultTimeout();
    }

    @Test
    void shortcutUsesConfiguredGlobalBudget() {
        StepVerifier.create(Flux.just("A", "B"))
                .expectNext("A", "B")
                .verifyComplete();
    }
}
```

Class này là file JUnit độc lập trong dự án đã có Reactor/JUnit dependencies. Nó được đưa vào bài để hiểu API và trách nhiệm restore state, **không phải** lời khuyên dùng global timeout cho mọi test. Trong suite lớn, hãy ưu tiên `expectComplete().verify(Duration.ofSeconds(...))` cục bộ.

## 5. Scheduler là tài nguyên có quyền sở hữu

`Scheduler` của Reactor dùng để điều phối tác vụ, chẳng hạn các operator `publishOn`, `subscribeOn`, `delayElements`, `Mono.delay` hoặc `Flux.interval`. Cần phân biệt scheduler nào là **owned resource** của test, scheduler nào là **shared/global**.

| Tài nguyên | Quyền sở hữu | Cleanup nên làm |
| --- | --- | --- |
| `Schedulers.newSingle("test-owned")` | Test tạo | `scheduler.dispose()` trong `@AfterEach` hoặc `finally` |
| `Schedulers.newParallel("test-owned", 2)` | Test tạo | Dispose khi không còn task cần dùng |
| `Schedulers.newBoundedElastic(...)` do test tạo | Test tạo | Dispose hoặc graceful lifecycle phù hợp |
| `Scheduler.Worker` do test tự tạo bằng `createWorker()` | Test tạo | `worker.dispose()` |
| `Schedulers.parallel()` | Scheduler shared/cached của Reactor | **Không dispose bừa bãi** |
| `Schedulers.boundedElastic()` | Scheduler shared/cached của Reactor | Không shutdown từ một test bất kỳ |
| `VirtualTimeScheduler.create()` | Test tạo | `virtual.dispose()`; nếu đã cài global thì cần restore factory |
| `publisher.subscribe(...)` thủ công | Subscriber/test sở hữu `Disposable` | `subscription.dispose()` khi kết thúc |
| Spring WebFlux/Netty server/context | Spring/Netty lifecycle | Đóng qua lifecycle của context/server phù hợp |

Nếu không dọn một `Schedulers.newSingle(...)` do test tạo, thread có thể còn sống và khiến build không thoát hoặc gây rò tài nguyên. Ngược lại, nếu một test `dispose()` scheduler lấy từ `Schedulers.parallel()`, các test khác có thể bị `RejectedExecutionException` hoặc không thực thi được task đúng lúc.

**Nguyên tắc:** ai tạo object/tài nguyên thì chịu trách nhiệm giải phóng; với tài nguyên mượn từ framework, sử dụng lifecycle của framework thay vì tùy tiện dọn trong fixture riêng.

## 6. Ví dụ Spring Boot/Reactor Java 17+: một service kiểm soát scheduler

Bộ ví dụ dưới đây tập trung hoàn toàn vào **publisher signals và scheduler cleanup**. Không cần mở ApplicationContext để kiểm tra một class Reactor thuần.

Cấu trúc project:

```text
src/
├── main/java/example/testing/time/
│   ├── DelayService.java
│   └── ExecutorCleanupDemo.java
└── test/java/example/testing/time/
    ├── DelayServiceTest.java
    ├── VirtualTimeScenarioTest.java
    └── GlobalVerifierBudgetTest.java
```

### 6.1. File production DelayService.java

Tạo `src/main/java/example/testing/time/DelayService.java`:

```java
package example.testing.time;

import java.time.Duration;
import java.util.Objects;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

public final class DelayService {
    private final Scheduler scheduler;

    public DelayService(Scheduler scheduler) {
        this.scheduler = Objects.requireNonNull(
                scheduler, "scheduler");
    }

    public Flux<Integer> numbers() {
        return Flux.range(1, 3)
                .map(number -> number * 10)
                .publishOn(scheduler);
    }

    public Mono<String> after(Duration delay) {
        if (delay == null || delay.isNegative()) {
            return Mono.error(new IllegalArgumentException(
                    "delay must be >= 0"));
        }

        return Mono.delay(delay, scheduler)
                .map(tick -> "ready");
    }

    public Mono<String> neverCompletes() {
        return Mono.never();
    }
}
```

Class này nhận scheduler qua constructor. `numbers()` phát lần lượt 10, 20, 30 rồi complete. `after(delay)` kiểm tra delay trước; null hoặc âm tạo `Mono.error(IllegalArgumentException)`, còn delay hợp lệ dùng `Mono.delay(delay, scheduler)` để phát tick và biến thành `"ready"`. `neverCompletes()` dùng để chứng minh trường hợp verifier có thể bị treo nếu thiếu deadline.

Điểm thiết kế quan trọng là `DelayService` **không tự đóng scheduler**: caller/service composition quyết định ai sở hữu. Trong test, ta tạo scheduler riêng rồi dispose ở fixture. Trong ứng dụng Spring Boot, nếu scheduler được đăng ký làm bean, lifecycle của bean/context cần được thiết kế tương ứng; đừng vừa để Spring quản lý vừa dọn nó bừa bãi từ một test đang dùng chung context.

### 6.2. File test DelayServiceTest.java

Tạo `src/test/java/example/testing/time/DelayServiceTest.java`:

```java
package example.testing.time;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DelayServiceTest {
    private Scheduler ownedScheduler;
    private DelayService service;

    @BeforeEach
    void setUp() {
        ownedScheduler = Schedulers.newSingle("lesson-owned");
        service = new DelayService(ownedScheduler);
    }

    @AfterEach
    void tearDown() {
        if (ownedScheduler != null) {
            ownedScheduler.dispose();
        }
    }

    @Test
    void valuesCompleteWithinVerificationBudget() {
        StepVerifier.create(service.numbers())
                .expectNext(10, 20, 30)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void negativeDelayIsReactiveError() {
        StepVerifier.create(
                        service.after(Duration.ofSeconds(-1)))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "delay must be >= 0"
                                .equals(error.getMessage()))
                .verify(Duration.ofSeconds(3));
    }

    @Test
    void stalledMonoFailsBoundedVerification() {
        assertThrows(AssertionError.class,
                () -> StepVerifier.create(
                                service.neverCompletes())
                        .expectComplete()
                        .verify(Duration.ofMillis(150)));
    }

    @Test
    void cancellationIsObservedByPublisher() {
        AtomicInteger cancels = new AtomicInteger();

        Flux<Integer> endless = Flux.<Integer>never()
                .doOnCancel(cancels::incrementAndGet);

        StepVerifier.create(endless)
                .expectSubscription()
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertEquals(1, cancels.get());
    }

    @Test
    void explicitVirtualSchedulerNeedsNoRealTwoHourWait() {
        VirtualTimeScheduler virtual =
                VirtualTimeScheduler.create();

        try {
            DelayService virtualService =
                    new DelayService(virtual);

            StepVerifier.create(
                            virtualService.after(
                                    Duration.ofHours(2)))
                    .expectSubscription()
                    .then(() -> virtual.advanceTimeBy(
                            Duration.ofHours(2)))
                    .expectNext("ready")
                    .expectComplete()
                    .verify(Duration.ofSeconds(3));
        } finally {
            virtual.dispose();
        }
    }
}
```

Bộ test này có **5 method `@Test`**:

- `valuesCompleteWithinVerificationBudget`: kiểm tra ba dữ liệu đúng thứ tự rồi complete trong deadline 3 giây.
- `negativeDelayIsReactiveError`: kiểm tra **onError**, không dùng `assertThrows` quanh `service.after(...)` vì method trả `Mono.error(...)`.
- `stalledMonoFailsBoundedVerification`: kiểm tra verifier tự báo thất bại sau timeout, bằng một `assertThrows(AssertionError.class, ...)` có chủ đích.
- `cancellationIsObservedByPublisher`: kiểm tra `thenCancel()` kích hoạt callback `doOnCancel`; không nhầm cancel với complete.
- `explicitVirtualSchedulerNeedsNoRealTwoHourWait`: scheduler ảo tạo riêng, được inject vào service; test advance hai giờ ảo mà không `Thread.sleep`, rồi đóng scheduler bằng `finally`.

**Lưu ý về teardown:** `@AfterEach` giúp dispose `ownedScheduler` cả khi assertion fail. Scheduler ảo bên trong test riêng được dispose ở `finally`. Không gọi `Schedulers.shutdownNow()` vì đó là hành động global vượt phạm vi tài nguyên của class này.

### 6.3. File test VirtualTimeScenarioTest.java

`StepVerifier.withVirtualTime(...)` cho phép thay clock của những operator dùng factory scheduler phù hợp. Tạo `src/test/java/example/testing/time/VirtualTimeScenarioTest.java`:

```java
package example.testing.time;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

class VirtualTimeScenarioTest {

    @AfterEach
    void restoreVirtualSchedulerFactory() {
        VirtualTimeScheduler.reset();
    }

    @Test
    void twoTicksAcrossTwoVirtualHours() {
        StepVerifier.withVirtualTime(
                        () -> Flux.interval(
                                Duration.ofHours(1))
                                .take(2))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .expectComplete()
                .verify(Duration.ofSeconds(3));
    }
}
```

Kịch bản này minh họa ba nguyên tắc:

1. **Tạo Publisher bên trong supplier:** `() -> Flux.interval(...)`, không xây `Flux.interval(...)` trước khi virtual scheduler được thiết lập.
2. **Có subscription trước expectNoEvent:** StepVerifier coi subscription là một event, nên cần `expectSubscription()` trước khoảng không có event.
3. **Tiến giờ ảo nhưng giới hạn thời gian thật:** `expectNoEvent(1h)` tiến đến tick đầu, `thenAwait(1h)` tiến đến tick thứ hai; `verify(3s)` vẫn giúp tránh kẹt nếu ví dụ bị sửa sai.

`VirtualTimeScheduler.reset()` là cleanup an toàn trong **bộ test đã chủ ý quản lý global virtual-scheduler factory**. Vì global scheduler factory có ảnh hưởng trên cả JVM, **không chạy đồng thời** với test khác cũng thao tác factory hoặc dùng shared Reactor scheduler mà không có cơ chế phối hợp. Nếu không muốn mutation global, dùng local `VirtualTimeScheduler.create()` và inject trực tiếp như test trước.

### 6.4. Gradle dependencies và lệnh chạy

Trong project Spring Boot đã cài plugin, repositories và dependency management tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là phần cấu hình **bổ sung**, không phải toàn bộ `build.gradle` độc lập. Starter WebFlux cung cấp Reactor Core, còn `reactor-test` là dependency test cho StepVerifier/VirtualTimeScheduler. Không cần `@SpringBootTest` chỉ để chạy hai class unit test này.

Từ root project có Gradle wrapper:

```bash
./gradlew test --tests example.testing.time.DelayServiceTest
./gradlew test --tests example.testing.time.VirtualTimeScenarioTest
./gradlew test --tests example.testing.time.GlobalVerifierBudgetTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.time.DelayServiceTest"
.\gradlew.bat test --tests "example.testing.time.VirtualTimeScenarioTest"
.\gradlew.bat test --tests "example.testing.time.GlobalVerifierBudgetTest"
```

**Kỳ vọng khi dependencies/cấu hình đúng:** `DelayServiceTest` có 5 test methods pass, `VirtualTimeScenarioTest` có một case pass, `GlobalVerifierBudgetTest` có một case pass. Không đưa giả định stdout cố định của JUnit/Gradle vì runner và logging khác nhau. Với suite có parallel execution, cần cách ly những test thay global scheduler/timeout hoặc chạy riêng như các lệnh trên.

## 7. Ví dụ Java 17 thuần về quyền sở hữu executor

Các ví dụ Reactor cần classpath của `reactor-core`/`reactor-test`, không thể lấy riêng file rồi `javac` trần mà thiếu dependencies. Để minh họa nguyên tắc **tạo tài nguyên → dọn đúng tài nguyên**, ta có thêm chương trình độc lập chỉ dùng Java SE.

Tạo `src/main/java/example/testing/time/ExecutorCleanupDemo.java`:

```java
package example.testing.time;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class ExecutorCleanupDemo {
    public static void main(String[] args)
            throws Exception {
        ScheduledExecutorService executor =
                Executors.newSingleThreadScheduledExecutor();

        try {
            String result = executor.schedule(
                    () -> "ready", 0, TimeUnit.MILLISECONDS)
                    .get(2, TimeUnit.SECONDS);

            System.out.println(result);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(
                    2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        System.out.println(
                "shutdown=" + executor.isShutdown());
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -d out src/main/java/example/testing/time/ExecutorCleanupDemo.java
java -cp out example.testing.time.ExecutorCleanupDemo
```

Stdout chính xác trong điều kiện chạy bình thường:

```text
ready
shutdown=true
```

Chương trình này minh họa pattern `try/finally`, deadline khi đợi một kết quả và shutdown executor **do chính chương trình tạo**. Nó không dùng Reactor và **không thay thế** kiểm thử `Scheduler.dispose()`. `executor.isShutdown()` chỉ chứng minh đã gọi shutdown, không khẳng định mọi task đã kết thúc; muốn có bảo đảm terminated, cần kiểm tra `awaitTermination(...)` và xử lý lifecycle theo mục tiêu.

## 8. VirtualTimeScheduler: local dispose khác reset global factory

Có hai cách điều khiển thời gian ảo trong Reactor Test.

**Cách A — scheduler cục bộ, ít tác dụng phụ:**

```java
VirtualTimeScheduler virtual =
        VirtualTimeScheduler.create();

try {
    StepVerifier.create(
                    Mono.delay(
                            Duration.ofHours(2), virtual))
            .expectSubscription()
            .then(() -> virtual.advanceTimeBy(
                    Duration.ofHours(2)))
            .expectNext(0L)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
} finally {
    virtual.dispose();
}
```

Ở đây scheduler ảo được truyền trực tiếp cho operator và **không cần thay `Schedulers.Factory` toàn JVM**. Dispose chính instance được tạo là phù hợp.

**Cách B — cài scheduler ảo trên factory dùng chung:**

```java
VirtualTimeScheduler virtual =
        VirtualTimeScheduler.create();
VirtualTimeScheduler.set(virtual);

try {
    StepVerifier.create(
                    Mono.delay(Duration.ofHours(2)))
            .expectSubscription()
            .then(() -> virtual.advanceTimeBy(
                    Duration.ofHours(2)))
            .expectNext(0L)
            .expectComplete()
            .verify(Duration.ofSeconds(3));
} finally {
    VirtualTimeScheduler.reset();
    virtual.dispose();
}
```

Đây là snippet minh họa **chỉ dùng khi test kiểm soát độc quyền global factories**, không phải hướng triển khai mặc định trong suite chạy song song. `VirtualTimeScheduler.set(virtual)` cài virtual scheduler vào các factory thích hợp, `reset()` khôi phục factory trước đó, còn `virtual.dispose()` đóng object do test tạo. **Reset factory và dispose object là hai việc khác nhau.**

`VirtualTimeScheduler.getOrSet()` có thể trả một scheduler global đã được kích hoạt bởi thành phần khác. **Không mặc định dispose một scheduler mà test không chắc mình sở hữu**; nếu đang dùng global, thiết kế setup/teardown tuần tự và kiểm soát ownership rõ ràng.

## 9. Vì sao Schedulers.shutdownNow() không nên nằm trong @AfterEach?

API Reactor:

```java
Schedulers.shutdownNow();
```

sẽ clear cached schedulers và gọi dispose lên chúng, mang tính **toàn cục**. Nó không chỉ dọn một scheduler bạn tạo bằng `Schedulers.newSingle(...)`.

Đây là một anti-pattern:

```java
@AfterEach
void tearDown() {
    Schedulers.shutdownNow();
}
```

Nếu test A đóng cached schedulers trong khi test B đang chạy `publishOn(Schedulers.parallel())` hay `subscribeOn(Schedulers.boundedElastic())`, test B có thể nhận lỗi bị từ chối task hoặc behavior không ổn định. Những test Spring Boot đang sử dụng scheduler shared cũng có thể bị ảnh hưởng.

**Khi nào mới cân nhắc `Schedulers.shutdownNow()`?** Chỉ ở teardown của một môi trường thực sự cô lập và đã bảo đảm **không còn bất kỳ luồng nào sử dụng shared schedulers**, ví dụ phase kết thúc suite có ownership rõ. Đừng dùng nó như lời khuyên chung cho từng method test.

`Schedulers.resetFactory()` cũng là API toàn cục phục vụ thay thế scheduler factory; nó không phải một lệnh “dọn scheduler riêng”. Nếu test chỉ dùng `Schedulers.newSingle(...)` thì cleanup đúng là `dispose()` của instance đó. Nếu test tự tạo `Scheduler.Worker`, dọn worker bằng `worker.dispose()` nữa.

### Ví dụ ownership khi tạo Worker

```java
Scheduler scheduler = Schedulers.newSingle("worker-owned");
Scheduler.Worker worker = scheduler.createWorker();

try {
    worker.schedule(() -> System.out.println("work"));
} finally {
    worker.dispose();
    scheduler.dispose();
}
```

Đây là **đoạn minh họa resource cleanup**, không phải một test xác minh task đã hoàn tất. Task có thể chưa chạy trước khi `finally` dispose; muốn kiểm tra execution phải dùng synchronization/hợp đồng publisher có thể chờ hữu hạn, tránh dựa vào `System.out.println`.

## 10. Khi nào dùng .timeout(Duration) trong pipeline?

Operator `timeout(Duration)` thay đổi **hành vi publisher**, không chỉ việc chờ của JUnit. Ví dụ một `Mono.never()` được bọc timeout có thể phát `java.util.concurrent.TimeoutException` sau thời gian chờ.

```java
@Test
void operatorTimeoutProducesReactiveError() {
    StepVerifier.withVirtualTime(
                    () -> Mono.<String>never()
                            .timeout(Duration.ofMinutes(5)))
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(5))
            .expectError(
                    java.util.concurrent.TimeoutException.class)
            .verify(Duration.ofSeconds(3));
}
```

Đây là một method test minh họa, cần imports `@Test`, `Duration`, `Mono`, `StepVerifier`. **Hai tầng timeout cùng tồn tại**:

- `.timeout(5 phút)`: sau 5 phút **ảo**, pipeline phát `onError(TimeoutException)`.
- `verify(3 giây)`: toàn bộ verification có tối đa 3 giây **thực** để nhận đúng error event.

Nếu pipeline có thêm `onErrorResume(TimeoutException.class, error -> Mono.just("cached"))`, subscriber sẽ thấy giá trị `"cached"` và complete; test phù hợp phải kỳ vọng fallback thay vì `expectError(...)`.

**Không thêm `.timeout(...)` vào pipeline test chỉ để ép một kịch bản production không có timeout kết thúc nhanh.** Điều đó thay đổi behavior của đối tượng đang kiểm tra. Khi chỉ muốn chống treo, dùng `verify(Duration)`.

## 11. Subscription, worker và graceful shutdown

`StepVerifier` tự quản lý subscription trong kịch bản verification, bao gồm case `thenCancel()`. Nhưng khi test tự gọi `subscribe(...)`, nó thường nhận `reactor.core.Disposable` và cần dừng subscription khi không còn dùng:

```java
Scheduler owned = Schedulers.newSingle("stream-owner");
Disposable subscription =
        Flux.interval(Duration.ofSeconds(1), owned)
                .subscribe(value -> System.out.println(value));

try {
    // Các hành động test có điểm dừng rõ ràng.
} finally {
    subscription.dispose();
    owned.dispose();
}
```

Đây là snippet lifecycle, **không phải test hoàn chỉnh** có assertions. Nó cần imports `Duration`, `Flux`, `Disposable`, `Scheduler` và `Schedulers`. Thứ tự cleanup hợp lý là **dừng nguồn/subscription trước khi đóng scheduler**. Đừng để `Flux.interval` hay một hot stream còn sống sau khi test đã xong.

Với scheduler riêng cần shutdown nhẹ nhàng, một số implementations hỗ trợ `scheduler.disposeGracefully()` trả `Mono<Void>`. Vì đó là Mono, cần subscribe và có deadline phù hợp nếu bạn muốn thật sự chờ kết quả; không chỉ gọi method rồi bỏ kết quả. Nếu shutdown graceful không hoàn tất, có thể cần force dispose theo hợp đồng resource, không chờ không giới hạn.

**Đừng nhầm scheduler dispose với cleanup mọi tài nguyên**: DB cursor, HTTP response body, socket, message consumer, Spring ApplicationContext, Reactor Netty connection pool đều có lifecycle riêng. Với Spring Boot integration test, hãy để context/adapter đóng phần mà chúng sở hữu; không nghĩ `Schedulers.shutdownNow()` đóng tất cả I/O.

## 12. JUnit @Timeout và giới hạn ở mức runner

JUnit Jupiter hỗ trợ timeout cho test method:

```java
@Timeout(value = 5, unit = TimeUnit.SECONDS)
@Test
void runnerHasSafetyNet() {
    StepVerifier.create(Flux.just(1, 2))
            .expectNext(1, 2)
            .verifyComplete();
}
```

Đoạn method cần imports `org.junit.jupiter.api.Timeout`, `Test`, `java.util.concurrent.TimeUnit`. `@Timeout` đặt một giới hạn ở cấp runner; nó **không phải một assertion về onNext/onComplete** và không thể thay kiểm tra reactive signals bằng StepVerifier.

Khi JUnit dùng chế độ timeout **preemptive** hoặc cơ chế ngắt/chạy ở thread khác, cần cẩn thận với Spring Test transaction, SecurityContext hoặc các `ThreadLocal` bindings. Một request chạy trên thread khác có thể không tham gia transaction mà test runner đang quản lý; việc test bị timeout cũng không bảo đảm thread/resource bên ngoài tự dọn hoàn toàn.

**Bốn budget nên được phân biệt:**

```text
1. Business timeout    : .timeout(Duration) trong pipeline
2. Verification budget : StepVerifier.verify(Duration)
3. Method timeout      : JUnit @Timeout
4. CI/build timeout    : Runner chặn cả task/suite
```

Không có quy tắc cứng “mọi test phải timeout 1 giây”. Chọn ngân sách dựa trên rủi ro kẹt, tải CI, loại scheduler và yêu cầu nghiệp vụ. Timer dài có thể dùng virtual time, trong khi HTTP/database integration cần budget rộng hơn và cleanup đáng tin.

## 13. Chạy song song: global scheduler có thể làm test flakiness

Các API này tác động lên **toàn JVM hoặc phạm vi factory/cache dùng chung**:

- `StepVerifier.setDefaultTimeout(...)` và `resetDefaultTimeout()`.
- `VirtualTimeScheduler.set(...)` / `getOrSet()` / `reset()`.
- `Schedulers.setFactory(...)` / `resetFactory()` / `shutdownNow()`.
- Các global hooks của Reactor nếu đã được đăng ký.

Ví dụ một race:

```text
Test A: VirtualTimeScheduler.set(virtualA)
             |
Test B: Flux.delayElements(...) bắt đầu dùng factory global
             |
Test A: VirtualTimeScheduler.reset()
             |
Test B: pipeline timing không còn như dự kiến
```

**Cách thiết kế chống race:**

1. Prefer inject `Scheduler` vào service, dùng `Schedulers.newSingle(...)` hoặc `VirtualTimeScheduler.create()` riêng cho từng test.
2. Prefer `verify(Duration)` cục bộ hơn `setDefaultTimeout` global.
3. Nếu phải thay global, chạy nhóm test ấy tuần tự hoặc dùng synchronization hợp lệ mà **toàn bộ test tác động cùng resource đều tuân thủ**.
4. `@AfterEach`/`finally` chỉ restore những thay đổi mà test **thực sự sở hữu**; không reset tùy tiện factory khác.
5. Không gọi `Schedulers.shutdownNow()` để chữa một test bị treo trong lúc cả suite vẫn chạy.
6. Với Spring Boot đang giữ ApplicationContext dùng chung, tránh can thiệp global schedulers từ unit test trong cùng process không kiểm soát.

JUnit `@ResourceLock` có thể giúp serialize **những test cùng dùng một lock key**, nhưng không thể bảo vệ khỏi code/test khác không tuân thủ key. Khi có thể, cách an toàn hơn vẫn là thiết kế tránh mutation global.

## 14. Chẩn đoán khi test treo hoặc báo lỗi sau test

**Tình huống A — verification không bao giờ kết thúc:** kiểm tra nguồn có `Mono.never`/`Flux.never` không, có terminal expectation không, đang thiếu `thenRequest(n)` không. Nếu là stream vô hạn, dùng `thenCancel()` hoặc giới hạn có chủ đích thay vì `verifyComplete()`.

**Tình huống B — verify(Duration) timeout quá nhanh:** không tự tăng lên một giờ. Kiểm tra công việc có bị blocking, scheduler bị dispose, I/O ngoài đang treo, hoặc virtual clock chưa advance. Cân nhắc fake dependency, virtual time và budget theo tải CI.

**Tình huống C — CI lỗi `RejectedExecutionException` sau một test khác:** xem có `scheduler.dispose()` nhầm lên shared `Schedulers.parallel()/boundedElastic()` hoặc `Schedulers.shutdownNow()` tại `@AfterEach` hay không.

**Tình huống D — sau virtual time test, các test khác thấy timer sai:** kiểm tra global factory có được restore không, publisher có được tạo trong supplier đúng không, và suite có parallel execution không.

**Tình huống E — build xanh nhưng process không thoát:** tìm thread từ `newSingle/newParallel` hoặc executor tự tạo chưa dispose, subscription `interval` đang sống, network/container không được đóng. Dùng thread dump/lifecycle diagnostics để xác định owner, không shutdown toàn JVM theo cảm tính.

**Tình huống F — thấy `TimeoutException` nhưng tưởng StepVerifier timeout:** phân biệt `TimeoutException` phát trong `onError` do operator `.timeout` với `AssertionError` do `verify(Duration)` không hoàn thành. Hai thứ có nguyên nhân và assertion khác nhau.

## 15. Lỗi phổ biến và cách tránh

**1. Gọi `verify()` trên `Mono.never()`.** Không có timeout hay terminal event, test có thể chờ vô hạn; dùng `verify(Duration)` trong bài test minh họa ngưỡng hoặc `thenCancel()` khi muốn test hủy.

**2. Hiểu `verify(Duration.ZERO)` là hết hạn tức thì.** Sai: ZERO trong API này biểu thị unlimited wait.

**3. Chỉ viết expectation rồi quên verify.** Kịch bản chưa được thực thi; test không có bằng chứng.

**4. Dùng `expectNextCount(n)` mà không quan tâm completion.** Nếu cần đúng n phần tử và kết thúc, phải assert terminal signal phù hợp.

**5. Coi timeout verifier là timeout nghiệp vụ.** Khi verifier hết hạn, test thất bại; publisher không tự biến thành `TimeoutException`.

**6. Cài `.timeout(...)` chỉ để làm test nhanh.** Điều đó thay đổi production behavior được kiểm tra.

**7. Đặt `StepVerifier.setDefaultTimeout` rồi quên reset.** Test khác có thể bị ảnh hưởng, nhất là chạy song song.

**8. Reset global default thành unlimited trong suite vốn có custom policy.** `resetDefaultTimeout()` không tự phục hồi custom timeout trước đó; phải quản lý chính sách ở phạm vi sở hữu.

**9. Dùng `Thread.sleep` để chờ vài giờ.** Test chậm và flaky; dùng virtual time với supplier lazy/virtual scheduler phù hợp.

**10. Tạo Publisher trước `withVirtualTime`.** Scheduler có thể đã được chọn trước khi factory chuyển sang virtual.

**11. Dùng `expectNoEvent` trước `expectSubscription`.** Subscription cũng là event; thứ tự kỳ vọng có thể sai.

**12. Quên advance clock khi đang đợi một timer.** Với virtual time, task chưa đến hạn không phát dữ liệu; dùng `thenAwait` hoặc `expectNoEvent`.

**13. Không dọn scheduler mới tạo.** Có thể để lại worker/thread và gây build không thoát.

**14. Dispose scheduler shared.** Có thể phá test khác đang dùng Reactor global schedulers.

**15. Gọi `Schedulers.shutdownNow()` mỗi `@AfterEach`.** Phạm vi quá rộng; chỉ dành cho teardown đã kiểm soát toàn suite.

**16. Gọi `VirtualTimeScheduler.reset()` mà chưa hiểu ownership/global factory.** Reset là phục hồi factory, không tự đóng mọi Scheduler độc lập.

**17. Không dispose subscription tạo thủ công.** Một Flux interval/hot source có thể tiếp tục phát sau khi test kết thúc.

**18. Cho rằng @Timeout bảo đảm cleanup mọi thread/I/O.** Runner timeout không thay thế lifecycle của scheduler, subscription, HTTP/DB resources.

## 16. Checklist trước khi báo QA PASS

**Kỳ vọng tín hiệu:**

- Publisher trả Mono/Flux hữu hạn hay có thể không complete?
- Test đang yêu cầu `onComplete`, `onError` hay cancellation?
- Đã gọi `verify()`/`verify(Duration)` thật sự chưa?
- Test có thể kẹt do thiếu demand/terminal? Budget đã hữu hạn chưa?
- Có phân biệt `AssertionError` của verifier và `TimeoutException` của publisher?

**Thời gian:**

- Test dùng real clock hay virtual clock? Vì sao?
- Với `withVirtualTime`, publisher được tạo trong supplier chưa?
- Đã advance virtual time đủ và đúng thứ tự chưa?
- Timeout có quá sát điều kiện CI hay là một deadline nghiệp vụ hợp lý?

**Cleanup:**

- Test tạo scheduler nào và đã `dispose()` đúng instance chưa?
- Test có tạo `Scheduler.Worker` hoặc gọi `subscribe()` thủ công? Có dọn chúng không?
- Có tránh dispose scheduler trả từ `Schedulers.parallel()/boundedElastic()` không?
- Có vô tình gọi `Schedulers.shutdownNow()` mỗi test không?
- Nếu thay global default timeout/factory, có reset đúng state mình sở hữu không?
- Test global có bị chạy song song với test khác đang dùng scheduler factory không?
- Các resource của Spring Boot/Netty/DB có lifecycle riêng được tôn trọng không?

**Kết luận:** một test Reactor đáng tin cần **verification budget rõ ràng** và **scheduler cleanup theo ownership**. `expectComplete().verify(Duration)` giúp chống treo cục bộ; `withVirtualTime`/`VirtualTimeScheduler` kiểm tra timer mà không ngủ thật; `@AfterEach`/`finally` đóng scheduler riêng, còn scheduler shared và global factories phải được khôi phục có kiểm soát. Không dùng `Schedulers.shutdownNow()` như một “dọn rác” mặc định cho từng test.

## 17. Tài liệu tham khảo

- [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `verify(Duration)`, default timeout và virtual time.
- [Project Reactor — VirtualTimeScheduler API](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html): `create`, `set`, `advanceTimeBy`, `reset`.
- [Project Reactor — Scheduler API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Scheduler.html): `dispose` và `disposeGracefully`.
- [Project Reactor — Schedulers API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html): global scheduler factory và `shutdownNow`.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier/virtual time.
- [JUnit Jupiter — Timeouts](https://junit.org/junit5/docs/current/user-guide/#writing-tests-declarative-timeouts): `@Timeout`.
