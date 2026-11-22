# CountDownLatch, barrier và phối hợp luồng có kiểm soát

Trong nhóm **Bất đồng bộ và lịch chạy** của module **Spring Boot - testing**, một lỗi kiểm thử rất phổ biến là “test chạy được trên máy tôi nhưng thất bại ở CI”. Nguyên nhân thường không nằm ở JUnit mà ở việc test đang dựa vào thời gian **đoán trước**, ví dụ gọi `Thread.sleep(200)` và hy vọng task `@Async`, `@Scheduled` hoặc một executor đã chạy xong. Khi scheduler chậm, thread pool đông, GC xảy ra hoặc máy CI có ít CPU, giả định ấy bị phá vỡ.

**CountDownLatch**, **CyclicBarrier** và **Phaser** là ba công cụ của `java.util.concurrent` giúp sắp xếp những thời điểm quan trọng một cách tường minh: đợi một số worker đến một checkpoint, chủ động mở cổng cho các worker đi tiếp, hoặc yêu cầu một nhóm thread gặp nhau trước khi bắt đầu pha kế tiếp. Test tốt còn kết hợp `Future/CompletableFuture`, **timeout hữu hạn**, xử lý interruption, `finally` giải phóng waiters và cleanup executor.

Mục tiêu của bài:

1. Dùng `CountDownLatch` để biết **N công việc đã tới checkpoint** và để **thả chúng sau khi test sẵn sàng**.
2. Phân biệt **start gate** với **completion signal**; hiểu `countDown()` không tự làm một thread chờ.
3. Dùng `CyclicBarrier` để tập hợp một số parties **cố định** qua nhiều pha; hiểu broken barrier, timeout và reset.
4. Biết khi nào `Phaser` với parties động thích hợp hơn.
5. Viết JUnit 5 tests tái hiện **race condition có chủ đích**, thay vì ngủ và hy vọng đụng race.
6. Kiểm tra một Spring Boot `@Async` service với executor thật và hai latch; không thử bằng self-invocation hoặc Mockito-only khi mục tiêu là kiểm tra thread boundary.
7. Kiểm tra `@Scheduled`: tách logic nghiệp vụ khỏi trigger; dùng latch làm tín hiệu khi cần smoke test scheduler thật.
8. Tránh deadlock, timeout giả, mất exception, resource leak, khẳng định ordering hoặc rollback mà test chưa chứng minh.

Ví dụ sử dụng **Java 17+, JUnit Jupiter, Spring Boot 3.5 / Spring Framework 6.2**. Phần Java SE có mã `javac/java` và **stdout chính xác**; phần Spring Boot có classes, test và Gradle dependencies để người học chạy trong project thật. Mỗi ví dụ nêu ranh giới những gì nó kiểm chứng.

## 1. Tại sao Thread.sleep không phải công cụ phối hợp?

Một test dễ vỡ:

```java
service.startAsyncWork();
Thread.sleep(200);
assertEquals(1, repository.count());
```

Đây là **anti-pattern minh họa**, không phải một file đầy đủ. Nó không có sự kiện nào bảo đảm task đã bắt đầu hoặc kết thúc trước lúc kiểm tra. Nếu máy CI scheduling chậm hơn 200 ms, test fail giả; nếu task đã xong ngay, test lãng phí 200 ms. Khi task ném exception trên background thread, test có thể vẫn xanh nếu không thu thập kết quả.

Thay vì hỏi “đã ngủ đủ lâu chưa?”, hãy hỏi một điều quan sát được:

- Worker đã **bắt đầu** chưa? Dùng `started.countDown()` và `started.await(timeout)`.
- Đã có **đủ N worker đến checkpoint** chưa? Dùng `new CountDownLatch(N)`.
- Có cần giữ worker ở checkpoint cho tới khi test thiết lập state? Dùng `release.await(timeout)` và test gọi `release.countDown()`.
- Tất cả worker cần kết thúc **mỗi pha** cùng nhau? Dùng `CyclicBarrier` hoặc `Phaser`.
- Cần biết **kết quả/exception cuối cùng**? Dùng `Future.get(timeout, unit)` hoặc `CompletableFuture.get(...)`.
- Cần chờ điều kiện bên ngoài thay đổi nhưng không kiểm soát code phát tín hiệu? Có thể dùng Awaitility với timeout/polling phù hợp, không phải `Thread.sleep` cố định.

**Không có primitive nào bảo đảm một thứ tự chạy của OS scheduler.** Chúng chỉ tạo ra các quan hệ phối hợp cụ thể. Phải đặt tín hiệu đúng chỗ, dùng số parties đúng và quan sát side effect với thread-safe state.

## 2. Mô hình ba loại đồng bộ hóa

```text
CountDownLatch: một cổng / một lần
  Worker A ---- countDown --+
  Worker B ---- countDown --+--> count == 0 --> waiter được thả
  Test thread - await ------+

CyclicBarrier: rendezvous, nhiều pha
  Worker A -> phase 1 -> await --+
  Worker B -> phase 1 -> await --+--> cả hai qua barrier
  Worker A -> phase 2 -> await --+
  Worker B -> phase 2 -> await --+--> cùng qua lần nữa

Phaser: rendezvous nhiều pha, parties có thể thay đổi
  Phase 0: A + B + C
  Phase 1: A + B      (C deregister)
  Phase 2: A + B + D  (D register)
```

| Công cụ | Mục tiêu | Tái sử dụng? | Parties |
| --- | --- | --- | --- |
| `CountDownLatch` | Đợi count về 0, gate một chiều | **Không reset** | Count cố định lúc tạo |
| `CyclicBarrier` | Các thread chờ nhau tại barrier | **Có, nhiều generation** | Số parties cố định |
| `Phaser` | Phối hợp nhiều phase | Có | Có thể register/deregister |
| `Future/CompletableFuture` | Kết quả/exception của task | Theo một task/chain | Không thay barrier group |
| `Semaphore` | Giới hạn số phép truy cập đồng thời | Có | Permits thay vì rendezvous |
| `BlockingQueue` | Truyền sự kiện/giá trị giữa thread | Có | Producer/consumer |
| `AtomicInteger/locks` | Bảo vệ state mutation | Có | Không thay chức năng gate |

**Rất quan trọng:** `CountDownLatch` và `CyclicBarrier` **không biến một thuật toán đọc-sửa-ghi không atomic thành thread-safe**. Chúng giúp tái hiện/điều khiển timing; dữ liệu chia sẻ vẫn cần CAS, lock, transaction hoặc cơ chế bảo vệ phù hợp.

## 3. CountDownLatch: semantics chính xác

`CountDownLatch` được tạo với một `count` không âm:

```java
CountDownLatch arrived = new CountDownLatch(2);
CountDownLatch release = new CountDownLatch(1);
```

API cốt lõi:

- `countDown()`: giảm count một đơn vị nếu đang lớn hơn 0; khi về 0, đánh thức thread đang `await()`. Phương thức này **không block** cho tới khi người khác hoàn tất.
- `await()`: đợi vô hạn trừ khi bị interrupt; **không nên dùng vô hạn trong integration tests**.
- `await(long timeout, TimeUnit unit)`: trả `true` nếu count về 0; trả `false` khi hết hạn. Nếu bị interrupt, ném `InterruptedException`.
- `getCount()`: snapshot để debug; không dùng như điều kiện đồng bộ chính vì có thể thay đổi ngay sau khi đọc.
- Sau khi count = 0, các lệnh `countDown()` tiếp theo không có tác dụng; `await(...)` trả ngay.
- **Không có `reset()` trên CountDownLatch.** Nếu cần một vòng mới, tạo latch mới hoặc chọn CyclicBarrier/Phaser.

### Start gate và completion gate khác nhau

```java
CountDownLatch start = new CountDownLatch(1);
CountDownLatch finished = new CountDownLatch(2);
```

Worker có thể làm:

```java
try {
    start.await();
    process();
} finally {
    finished.countDown();
}
```

Test/driver làm:

```java
start.countDown();
boolean done = finished.await(
        5, TimeUnit.SECONDS);
```

Đây là **snippet minh họa**, cần imports, method `process()` và executor. `finished.countDown()` nằm trong `finally` để không làm test chờ mãi khi `process()` ném lỗi. Tuy nhiên, **finished về 0 chỉ chứng minh worker đã qua finally**; nó không báo worker thành công. Để thấy exception, phải giữ `Future` và gọi `get(...)`.

### Hàng rào bộ nhớ (happens-before)

Tài liệu Java SE 17 nêu: các hành động trong thread trước `countDown()` *happen-before* các hành động sau một `await()` trở về thành công ở thread khác. Điều này quan trọng cho visibility.

```text
Worker:
  write shared data
  latch.countDown()
                   happens-before
Test:
  latch.await() returns successfully
  read shared data
```

Nhưng `getCount()==0` được quan sát từ một thời điểm không thay thế việc thiết kế đúng synchronization, và phép tăng counter bằng `counter++` không tự trở nên atomic chỉ vì có latch.

## 4. Pattern đáng tin: ready latch + release latch + Futures

Một cấu trúc mạnh để kiểm tra concurrency là **hai latch khác mục đích**:

```text
                  Worker A                Worker B
                  --------                --------
                  reach.countDown()       reach.countDown()
                  release.await()         release.await()
                         |                       |
                         +------- blocked -------+
                                         ^
                                         |
Test thread:  reach.await(timeout) ------+
              assert workers reached gate
              prepare/assert initial state
              release.countDown()
              futureA.get(timeout)
              futureB.get(timeout)
```

Đây là cách kiểm soát điểm bắt đầu một thao tác nhạy cảm. Khi `reach.await(...)` trả true, test biết **đủ worker đã tới điểm tín hiệu**; nó chưa chứng minh từng worker đã đứng yên vĩnh viễn. Nếu mã worker được viết đúng là `reach.countDown()` ngay trước `release.await()`, test chủ động mở release mới tạo được thời điểm bước tiếp theo bắt đầu.

**Lưu ý pool size:** nếu cần **2 workers cùng đợi ở gate**, executor phải có ít nhất **2 thread có thể thực thi**. Với `newSingleThreadExecutor()`, worker đầu block chờ release còn worker thứ hai nằm trong queue: `reach` không thể về 0. Khi test lại đợi `reach` rồi mới release, đó là deadlock thiết kế, không phải “CI chậm”.

## 5. CyclicBarrier: gặp nhau ở mỗi pha

`CyclicBarrier(parties)` đợi đúng số parties gọi `await()` ở **cùng generation**. Khi party cuối đến, barrier trip và tất cả được thả; instance có thể dùng tiếp ở generation sau.

```java
CyclicBarrier barrier = new CyclicBarrier(2);

Callable<Void> worker = () -> {
    performPhaseOne();
    barrier.await(5, TimeUnit.SECONDS);

    performPhaseTwo();
    barrier.await(5, TimeUnit.SECONDS);
    return null;
};
```

Đây là snippet minh họa; các method performPhaseOne/Two chưa định nghĩa tại đây. Trong phần runnable, hai worker thật được submit và cả hai đi qua **hai phase**.

**Điểm cốt lõi:**

- `parties=2` nghĩa **hai lượt gọi await** cần đến ở mỗi generation; nếu chỉ có một worker, nó chờ và timeout.
- `await(timeout, unit)` có thể ném `TimeoutException`, `InterruptedException` hoặc `BrokenBarrierException`.
- Khi một waiter timeout/interrupt, barrier thường chuyển sang **broken state**; các waiter khác của generation ấy nhận `BrokenBarrierException`.
- `isBroken()` cho biết trạng thái broken. `reset()` tạo generation mới nhưng có thể khiến waiter hiện tại thất bại; dùng reset **chỉ khi đã phối hợp lifecycle**, không dùng mù quáng để “chữa test”.
- Constructor cho phép optional `barrierAction` chạy một lần khi party cuối tới barrier, trước khi các parties được thả.
- `getNumberWaiting()` là snapshot để debug, **không dùng để làm assertion scheduling ổn định**.

### CyclicBarrier khác CountDownLatch thế nào?

Với CountDownLatch, một thread chỉ gọi `countDown()` và **đi tiếp**, không chờ các thread khác. Với CyclicBarrier, **chính các parties phải chờ nhau** tại `await()`. CountDownLatch dùng lại cần object mới; CyclicBarrier có thể lặp qua nhiều pha.

Nếu JUnit thread cũng phải là một trong các parties, phải tính **cả test thread** vào số parties. Ví dụ hai workers + test thread cùng gọi barrier.await() thì `parties=3`, không phải 2. Tuy nhiên, thường dễ debug hơn nếu **test dùng latch làm điều phối** và chỉ các workers tham gia CyclicBarrier.

## 6. Phaser: parties động và nhiều generation

`Phaser` tương tự CyclicBarrier nhưng số bên tham gia có thể thay đổi:

- `register()` hoặc `bulkRegister(n)`: thêm parties.
- `arrive()`: báo hoàn thành phase mà không đợi.
- `arriveAndAwaitAdvance()`: báo đến và chờ phase tiến lên.
- `arriveAndDeregister()`: báo đến rồi rút khỏi các phase tiếp theo.
- `awaitAdvanceInterruptibly(phase, timeout, unit)`: chờ phase đổi với timeout/interrupt; bản không interruptible có semantics khác.
- `forceTermination()`: đưa phaser vào trạng thái kết thúc, giúp giải phóng waiters khi cần recovery.

Một snippet:

```java
Phaser phaser = new Phaser(1); // test/driver
phaser.register();             // một worker
int current = phaser.getPhase();

// Worker đã đăng ký gọi:
// phaser.arriveAndDeregister();

// Test gọi:
int advanced = phaser.arriveAndAwaitAdvance();
```

Đây là **mô hình giải thích**, không phải một test runnable; để chạy thật cần start worker và xử lý timeout/cleanup. Nếu một party đã đăng ký nhưng không bao giờ arrive, phase không tiến. Vì vậy đối với test đơn giản có hai worker cố định, CountDownLatch hoặc CyclicBarrier thường ít phức tạp hơn.

**Phaser không phải câu trả lời mặc định cho mọi async test.** Dùng nó khi thật sự cần nhiều thế hệ với số worker thay đổi, ví dụ pipeline nhiều giai đoạn có các task register/deregister. Với nhiều task được submit vào pool nhỏ, tránh đăng ký tất cả rồi để một số task chờ tại phase trong khi phần còn lại chưa được scheduler chạy: có thể tạo starvation/deadlock.

## 7. Nguyên tắc thiết kế concurrency test không flaky

Trước khi viết test, làm rõ 4 yếu tố:

| Yếu tố | Câu hỏi phải trả lời |
| --- | --- |
| **Entry checkpoint** | Task báo đã tới bước nào? Tín hiệu có đi trước phép đọc/ghi cần kiểm soát không? |
| **Gate release** | Ai mở cổng? Có bảo đảm mở kể cả khi assert fail? |
| **Result/exception** | Test lấy từ Future, queue hay callback nào? Có timeout hữu hạn? |
| **Cleanup/lifecycle** | Ai stop executor, scheduler và dọn database/mocks? Worker còn blocked không? |

**Checklist tối thiểu:**

1. Tạo latch/condition **trước** khi submit tasks.
2. Submit đủ workers và đảm bảo pool có đủ threads.
3. Worker `countDown()` đúng tại checkpoint; không báo sớm hơn điều cần chứng minh.
4. Test gọi `await(timeout)`, **assert true**; không dùng `await()` vô hạn trong CI.
5. Test mở gate trong `finally`, không chỉ ở happy path.
6. Test `get(timeout)` **từng Future** để exception không bị bỏ quên.
7. `shutdownNow()`/`shutdown()` + termination policy; không để blocked threads sống sau test.
8. Nếu worker bị interrupt, khôi phục flag bằng `Thread.currentThread().interrupt()` và kết thúc có kiểm soát.
9. Dùng state thread-safe như `AtomicInteger`, `ConcurrentHashMap` hoặc synchronized/lock theo hợp đồng.
10. Không assert thứ tự thread names hoặc timestamp mà JVM/OS không cam kết.
11. Chạy test nhiều lần/CI để phát hiện timing dependence, nhưng không dùng “pass 100 lần” để tuyên bố thuật toán chắc chắn đúng.
12. Ghi rõ rằng synchronization trong test **không sửa được** bug tồn tại khi chạy production.

## 8. Project Java 17 và Spring Boot 3.5 hoàn chỉnh

Cấu trúc source:

```text
src/
├── main/java/example/concurrency/
│   ├── CoordinationApplication.java
│   ├── GateCoordinator.java
│   ├── GateDemo.java
│   ├── AsyncPoolConfig.java
│   ├── ControlledAsyncService.java
│   ├── ScheduledProbe.java
│   └── ScheduledHeartbeat.java
└── test/java/example/concurrency/
    ├── GateCoordinatorTest.java
    ├── RaceConditionTest.java
    ├── ControlledAsyncServiceTest.java
    └── ScheduledHeartbeatTest.java
```

Phần **Java SE** gồm `GateCoordinator.java` và `GateDemo.java` — có thể compile riêng chỉ bằng JDK 17. Phần **Spring Boot** gồm application, async executor, service, scheduled probe và các integration tests.

### Gradle dependencies

Trong project Spring Boot **3.5.x** đã có Gradle plugin/repositories/dependency management và Java toolchain 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đoạn trên là **phần bổ sung của `build.gradle`**, không phải toàn bộ build script độc lập. Test unit dùng JUnit Jupiter trong `spring-boot-starter-test`; Spring scheduling, `@Async` và `ThreadPoolTaskExecutor` đến từ Spring Context trên application classpath. Không cần Docker/database cho bộ test này.

**Cẩn thận các phiên bản:** mã dùng Java 17 records, switch không cần preview, JUnit Jupiter và Spring Boot 3.5. Với Java 21 virtual threads, executor/scheduler policy có thể thay đổi nhưng semantics latch/barrier của Java vẫn cần bảo vệ như cũ.

## 9. Java SE source: GateCoordinator.java

Tạo `src/main/java/example/concurrency/GateCoordinator.java`:

```java
package example.concurrency;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class GateCoordinator {
    private GateCoordinator() {
    }

    public static String latchPair() throws Exception {
        ExecutorService pool =
                Executors.newFixedThreadPool(2);
        CountDownLatch bothReady =
                new CountDownLatch(2);
        CountDownLatch release =
                new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                bothReady.countDown();

                if (!release.await(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker A timed out");
                }
                return "A";
            });

            Future<String> second = pool.submit(() -> {
                bothReady.countDown();

                if (!release.await(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker B timed out");
                }
                return "B";
            });

            if (!bothReady.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "workers did not reach gate");
            }

            release.countDown();

            return first.get(5, TimeUnit.SECONDS)
                    + second.get(5, TimeUnit.SECONDS);
        } finally {
            // Nếu test/await ném lỗi, vẫn mở cổng.
            release.countDown();
            pool.shutdownNow();
        }
    }

    public static int barrierPhases()
            throws Exception {
        ExecutorService pool =
                Executors.newFixedThreadPool(2);
        AtomicInteger completedPhases =
                new AtomicInteger();

        CyclicBarrier barrier =
                new CyclicBarrier(
                        2, completedPhases::incrementAndGet);

        Callable<Void> work = () -> {
            barrier.await(5, TimeUnit.SECONDS);
            barrier.await(5, TimeUnit.SECONDS);
            return null;
        };

        try {
            Future<Void> first = pool.submit(work);
            Future<Void> second = pool.submit(work);

            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);

            return completedPhases.get();
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Điểm kiểm tra tính runnable:**

- Đúng **2 worker threads** cho `bothReady=2`, nên hai tasks có thể đến gate.
- Mỗi worker gọi `bothReady.countDown()` trước khi `release.await(...)`.
- Test/driver đợi cả hai tới rồi chủ động `release.countDown()`.
- Hai `Future.get(timeout)` trả đúng **giá trị hoặc exception của từng task**; không chỉ đợi latch.
- `finally` bảo đảm release và gọi `shutdownNow()`; trong một service thật nên có lifecycle/termination policy phù hợp.
- `CyclicBarrier(2, action)` trip **hai lần**, action tăng `completedPhases` mỗi generation.
- Không in trực tiếp từ worker, vì thứ tự worker output không xác định; method trả giá trị, `GateDemo` in từ main thread sau khi các Futures hoàn tất.

**Giới hạn timeout:** 5 giây là guard chống treo ví dụ, không phải SLO cho mọi môi trường. Test cực chậm có thể báo timeout; khi đó kiểm tra CPU/pool size/deadlock trước khi tăng số lên vô hạn.

## 10. Java SE source: GateDemo.java và stdout chính xác

Tạo `src/main/java/example/concurrency/GateDemo.java`:

```java
package example.concurrency;

public class GateDemo {
    public static void main(String[] args)
            throws Exception {
        System.out.println(
                "latch result="
                        + GateCoordinator.latchPair());
        System.out.println(
                "barrier phases="
                        + GateCoordinator.barrierPhases());
    }
}
```

Từ project root, dùng JDK 17+:

```bash
javac -d out src/main/java/example/concurrency/GateCoordinator.java src/main/java/example/concurrency/GateDemo.java
java -cp out example.concurrency.GateDemo
```

Stdout **chính xác khi hai thao tác hoàn thành trong timeout**:

```text
latch result=AB
barrier phases=2
```

Giải thích: Futures A và B có thể chạy theo thứ tự nào cũng được, nhưng main ghép `first.get() + second.get()` nên thứ tự giá trị luôn `AB`. Barrier action được chạy mỗi khi **cả hai** parties đến barrier; vì mỗi worker đi qua hai generation, counter bằng **2**. Nếu một worker timeout/interrupted, chương trình ném exception và không có stdout thành công như trên; đó là lỗi rõ ràng chứ không phải output nhiễu.

**Đây là Java SE demo thực sự**, không mở Spring context, không khởi động một scheduler thật, không phụ thuộc database/broker. Integration tests kế tiếp kiểm chứng phần Spring `@Async` và `@Scheduled` riêng.

## 11. JUnit unit tests cho CountDownLatch và CyclicBarrier

Tạo `src/test/java/example/concurrency/GateCoordinatorTest.java`:

```java
package example.concurrency;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GateCoordinatorTest {

    @Test
    void gateReleasesBothWorkers() throws Exception {
        assertEquals("AB", GateCoordinator.latchPair());
    }

    @Test
    void barrierCanBeReusedAcrossTwoPhases()
            throws Exception {
        assertEquals(2, GateCoordinator.barrierPhases());
    }

    @Test
    void latchIsOneShotAndCannotBecomePositiveAgain()
            throws Exception {
        CountDownLatch latch = new CountDownLatch(1);

        latch.countDown();
        latch.countDown();

        assertEquals(0L, latch.getCount());
        assertTrue(latch.await(0, TimeUnit.MILLISECONDS));
    }

    @Test
    void barrierTimeoutBreaksCurrentGeneration()
            throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);

        assertThrows(
                TimeoutException.class,
                () -> barrier.await(
                        1, TimeUnit.MILLISECONDS));

        assertTrue(barrier.isBroken());

        assertThrows(
                BrokenBarrierException.class,
                () -> barrier.await(
                        1, TimeUnit.MILLISECONDS));

        barrier.reset();
        assertFalse(barrier.isBroken());
    }
}
```

**Bốn JUnit methods**:

1. `gateReleasesBothWorkers` kiểm tra hai workers hoàn tất sau cổng.
2. `barrierCanBeReusedAcrossTwoPhases` kiểm tra cùng barrier được trip hai lần.
3. `latchIsOneShot...` chứng minh count không giảm âm và await trả true khi count đã bằng 0.
4. `barrierTimeoutBreaksCurrentGeneration` cố ý tạo barrier với 2 parties nhưng chỉ có **một caller**, nên nó timeout; barrier broken làm await kế tiếp ném `BrokenBarrierException`, `reset()` đưa về trạng thái chưa broken.

**Không cần Spring hay Docker.** Test dùng timeout để chặn treo, ngoại trừ test thứ tư **cố ý kiểm tra timeout** khi không có party còn lại. Nó không phụ thuộc độ trễ của một background task.

**Đừng lạm dụng `reset()` trong production**: reset trong lúc parties khác đang chờ có thể khiến chúng thất bại. Ở đây không có thread khác, nên test reset an toàn.

## 12. Tái hiện race có chủ đích thay vì trông đợi timing

Concurrency tests thường muốn bắt **lost update**, double booking hoặc oversell. Nếu dùng hai futures chạy cùng lúc mà không khóa điểm đọc/ghi, race có thể xuất hiện 1/1000 lần hoặc không xuất hiện. Muốn có test chính xác, ta dùng hai latch để **ép cả hai workers đọc cùng một snapshot trước khi cùng ghi**.

Giả sử kho còn đúng 1 sản phẩm. Cách viết lỗi:

```java
int observed = remaining.get();
if (observed > 0) {
    remaining.set(observed - 1);
    return true;
}
return false;
```

Đây là **đoạn thuật toán sai** để minh họa. `AtomicInteger.get()` và `set()` riêng rẽ là thread-safe tại từng lệnh, nhưng **tổ hợp get–check–set không atomic**. Hai threads có thể cùng đọc 1, cùng trả true, dù chỉ có một item.

### RaceConditionTest.java — hai tests có kiểm soát

Tạo `src/test/java/example/concurrency/RaceConditionTest.java`:

```java
package example.concurrency;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RaceConditionTest {

    @Test
    void gatesReproduceLostUpdateDeterministically()
            throws Exception {
        AtomicInteger stock = new AtomicInteger(1);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        Callable<Boolean> unsafe = () -> {
            int snapshot = stock.get();
            bothRead.countDown();

            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "release gate timed out");
            }

            if (snapshot <= 0) {
                return false;
            }

            stock.set(snapshot - 1); // Cố ý sai.
            return true;
        };

        try {
            Future<Boolean> one = pool.submit(unsafe);
            Future<Boolean> two = pool.submit(unsafe);

            assertTrue(
                    bothRead.await(5, TimeUnit.SECONDS));

            release.countDown();

            assertTrue(one.get(5, TimeUnit.SECONDS));
            assertTrue(two.get(5, TimeUnit.SECONDS));

            // Cả hai báo bán được, dù kho chỉ có 1.
            assertEquals(0, stock.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    private static boolean reserveSafely(
            AtomicInteger stock) {
        for (;;) {
            int current = stock.get();

            if (current <= 0) {
                return false;
            }

            if (stock.compareAndSet(
                    current, current - 1)) {
                return true;
            }
        }
    }

    @Test
    void compareAndSetPreventsDoubleReservation()
            throws Exception {
        AtomicInteger stock = new AtomicInteger(1);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        Callable<Boolean> safe = () -> {
            ready.countDown();

            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "release gate timed out");
            }

            return reserveSafely(stock);
        };

        try {
            Future<Boolean> one = pool.submit(safe);
            Future<Boolean> two = pool.submit(safe);

            assertTrue(
                    ready.await(5, TimeUnit.SECONDS));
            release.countDown();

            int successes =
                    (one.get(5, TimeUnit.SECONDS) ? 1 : 0)
                    + (two.get(5, TimeUnit.SECONDS)
                            ? 1 : 0);

            assertEquals(1, successes);
            assertEquals(0, stock.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

**Hai tests này có cùng môi trường 2 threads nhưng hai kết luận khác nhau:**

- Test đầu **chủ động chứng minh lỗi**: trước khi release, cả hai đã chụp snapshot=1. Sau release, cả hai đều trả true; đây là tình huống oversell. Test pass nghĩa là **reproducer của bug hoạt động**, không có nghĩa code unsafe là đúng.
- Test thứ hai dùng vòng CAS `compareAndSet(expected, update)`; chỉ một worker có thể chuyển stock từ 1 xuống 0. Worker còn lại thấy 0 hoặc CAS fail rồi retry và trả false. Test pass nghĩa là invariant “chỉ một reservation thành công” được giữ trong kịch bản này.

**Điều test không chứng minh:** algorithm CAS là giải pháp cho mọi hệ thống tồn kho phân tán. Với nhiều process/instances, cần DB atomic update, optimistic/pessimistic locking hoặc distributed consistency strategy phù hợp. Latch trong JUnit không thay thế transaction isolation của production database.

## 13. Spring Boot: bật @Async và @Scheduled có chủ đích

Tạo `src/main/java/example/concurrency/CoordinationApplication.java`:

```java
package example.concurrency;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableAsync
@EnableScheduling
public class CoordinationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CoordinationApplication.class, args);
    }
}
```

- `@EnableAsync` bật Spring interception cho các methods có `@Async`.
- `@EnableScheduling` cho phép Spring phát hiện các methods `@Scheduled` của beans được tạo.
- Điều này **không có nghĩa một method bất kỳ chạy trên background thread**: phải gọi đúng Spring proxy cho `@Async`; scheduled method thì được Spring scheduler invoke theo trigger.
- Trong test, scheduler bean của ví dụ chỉ được tạo khi bật property `lesson.scheduler.enabled=true`, tránh background timing làm các test khác bị ảnh hưởng.

**Self-invocation pitfall:** nếu một bean gọi `this.asyncMethod()` bên trong chính nó, lời gọi thường **không qua proxy** ở mode mặc định, nên `@Async` có thể không được áp dụng. Ví dụ dưới tách test khỏi service và assert thread name/receipts để phát hiện setup sai.

## 14. Cấu hình executor riêng, đủ workers

Tạo `src/main/java/example/concurrency/AsyncPoolConfig.java`:

```java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncPoolConfig {

    @Bean(name = "lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor pool =
                new ThreadPoolTaskExecutor();

        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("lesson-worker-");
        pool.initialize();

        return pool;
    }
}
```

Có **2 worker threads**, nên hai tác vụ `@Async("lessonExecutor")` có thể cùng đến gate. `ThreadPoolTaskExecutor` do Spring quản lý nên pool được đóng khi `ApplicationContext` kết thúc.

**Vì sao khai báo queueCapacity?** Một thread pool có thể queue task thứ ba thay vì tạo thêm thread. Khi test yêu cầu N workers đồng thời blocked ở một latch, phải đảm bảo **corePoolSize >= N** hoặc có worker capacity phù hợp. `maxPoolSize=10` không tự đảm bảo 10 workers sẽ chạy khi queue lớn; trong `ThreadPoolTaskExecutor` việc queue tasks ảnh hưởng thời điểm pool grow.

**Không nên sử dụng common ForkJoinPool vô điều kiện** cho một test cần biết chính xác số worker. Khai báo executor riêng khiến test dễ hiểu và giảm ảnh hưởng từ task khác trong process.

## 15. ControlledAsyncService: checkpoint trong @Async method

Tạo `src/main/java/example/concurrency/ControlledAsyncService.java`:

```java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ControlledAsyncService {

    public record Receipt(
            String jobId, String threadName) {
    }

    @Async("lessonExecutor")
    public CompletableFuture<Receipt> awaitRelease(
            String jobId,
            CountDownLatch reached,
            CountDownLatch release,
            long waitMillis) {

        reached.countDown();

        try {
            if (!release.await(
                    waitMillis,
                    TimeUnit.MILLISECONDS)) {
                throw new IllegalStateException(
                        "worker release timed out");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "worker interrupted", error);
        }

        return CompletableFuture.completedFuture(
                new Receipt(
                        jobId,
                        Thread.currentThread().getName()));
    }
}
```

**Đây là test seam minh họa**, không phải lời khuyên để truyền `CountDownLatch` trong API business production. Mục tiêu của class là kiểm tra Spring `@Async` thực sự chạy qua executor, gate hoạt động và timeout báo exception quan sát được.

Các điểm dễ nhầm:

- Method `awaitRelease(...)` có `@Async("lessonExecutor")` nên caller nhận `CompletableFuture<Receipt>` của Spring async invocation.
- Bên trong method đích, trả `CompletableFuture.completedFuture(...)` là hợp lệ với Spring `@Async` — proxy quản lý asynchronous result bên ngoài.
- `reached.countDown()` đánh dấu worker đã vào method **trước khi chờ release**.
- `release.await(waitMillis, MILLISECONDS)` có timeout hữu hạn; nếu false, ném `IllegalStateException`.
- Nếu bị interrupt, giữ interrupted status rồi kết thúc có exception. Không swallow interruption.
- Thread name bắt đầu bằng `lesson-worker-` khi thực sự được executor của ví dụ chạy.
- Một future complete exceptionally vẫn có thể được observer lấy qua `future.get(...)`; exception thường được bọc bằng `ExecutionException`.
- Nếu method `@Async` trả `void` thì caller không thể lấy failure qua Future; khi mục tiêu test là lỗi async, dùng Future/CompletableFuture hoặc callback error channel có kiểm soát.

## 16. ControlledAsyncServiceTest: JUnit integration có executor thật

Tạo `src/test/java/example/concurrency/ControlledAsyncServiceTest.java`:

```java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
class ControlledAsyncServiceTest {

    @Autowired
    private ControlledAsyncService service;

    @Test
    void bothWorkersWaitUntilTestOpensGate()
            throws Exception {
        CountDownLatch reached =
                new CountDownLatch(2);
        CountDownLatch release =
                new CountDownLatch(1);

        CompletableFuture<ControlledAsyncService.Receipt>
                first = service.awaitRelease(
                        "first", reached, release, 10_000);

        CompletableFuture<ControlledAsyncService.Receipt>
                second = service.awaitRelease(
                        "second", reached, release, 10_000);

        try {
            assertTrue(
                    reached.await(5, TimeUnit.SECONDS));

            assertFalse(first.isDone());
            assertFalse(second.isDone());
        } finally {
            release.countDown();
        }

        ControlledAsyncService.Receipt firstReceipt =
                first.get(5, TimeUnit.SECONDS);
        ControlledAsyncService.Receipt secondReceipt =
                second.get(5, TimeUnit.SECONDS);

        assertEquals("first", firstReceipt.jobId());
        assertEquals("second", secondReceipt.jobId());

        assertTrue(firstReceipt.threadName()
                .startsWith("lesson-worker-"));
        assertTrue(secondReceipt.threadName()
                .startsWith("lesson-worker-"));
    }

    @Test
    void gateTimeoutCompletesFutureExceptionally()
            throws Exception {
        CountDownLatch reached =
                new CountDownLatch(1);
        CountDownLatch release =
                new CountDownLatch(1);

        CompletableFuture<ControlledAsyncService.Receipt>
                future = service.awaitRelease(
                        "timeout", reached, release, 30);

        try {
            assertTrue(
                    reached.await(5, TimeUnit.SECONDS));

            ExecutionException failure = assertThrows(
                    ExecutionException.class,
                    () -> future.get(5, TimeUnit.SECONDS));

            assertInstanceOf(
                    IllegalStateException.class,
                    failure.getCause());
        } finally {
            release.countDown();
        }
    }
}
```

**Hai JUnit integration methods** thực sự tạo Spring context và gọi `@Async` bean qua proxy:

1. **Two workers gate:** khi `reached.await(...)` true, cả hai worker đã đi vào method và chờ release. Test quan sát Futures chưa xong, rồi mở release trong `finally`, sau đó lấy receipt và assert thread name đúng executor.
2. **Timeout observable:** worker được cho timeout ngắn 30 ms và không nhận release cho tới khi failure Future được quan sát. Test assert `ExecutionException` với cause `IllegalStateException`, nên không có lỗi background nào “bị log rồi mất”.

**Không dùng `Thread.sleep`**, không assert milliseconds chính xác, không phụ thuộc order first/second hoàn tất. Giới hạn test này là kiểm tra **gating and executor boundary**, không chứng minh logic business của ứng dụng khác.

**Lưu ý timeout kép:** `await(30, MILLISECONDS)` là timeout **của worker gate**, còn `future.get(5, SECONDS)` là timeout **của test chờ kết quả**. Nếu `get(...)` timeout, đó là lỗi khác với IllegalStateException từ worker. Không gộp hai tình huống thành một assertion chung.

## 17. @Scheduled: tách logic khỏi trigger, đừng ngủ chờ cron

Với scheduled job, nên tách hai trách nhiệm:

- **Logic nghiệp vụ**: method service được kiểm tra bằng unit test/JDBC integration test trực tiếp.
- **Trigger/scheduler wiring**: Spring có gọi method theo `@Scheduled` không? Nếu thật sự cần kiểm chứng, dùng một **tín hiệu có timeout** thay vì sleep.

Trong dự án mẫu, ta tạo một probe thread-safe: test “arm” latch và job báo khi tick. Probe **không lưu danh sách tick vô hạn** và không phụ thuộc tick có xảy ra trước khi test bắt đầu hay không.

### ScheduledProbe.java

Tạo `src/main/java/example/concurrency/ScheduledProbe.java`:

```java
package example.concurrency;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public class ScheduledProbe {
    private final AtomicReference<CountDownLatch> armed =
            new AtomicReference<>();

    public void arm(CountDownLatch latch) {
        armed.set(latch);
    }

    public void seenTick() {
        CountDownLatch latch =
                armed.getAndSet(null);

        if (latch != null) {
            latch.countDown();
        }
    }

    public void clear(CountDownLatch latch) {
        armed.compareAndSet(latch, null);
    }
}
```

`AtomicReference` là cần thiết vì scheduler thread ghi/đọc khác test thread. `getAndSet(null)` lấy latch đã arm một lần; nếu tick khác xảy ra trước khi test lại arm, nó không làm giảm latch cũ. Đây là tín hiệu **at most one tick cho một lần arm**; không phải metric đếm toàn bộ job executions.

### ScheduledHeartbeat.java

Tạo `src/main/java/example/concurrency/ScheduledHeartbeat.java`:

```java
package example.concurrency;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        name = "lesson.scheduler.enabled",
        havingValue = "true")
public class ScheduledHeartbeat {
    private final ScheduledProbe probe;

    public ScheduledHeartbeat(ScheduledProbe probe) {
        this.probe = probe;
    }

    @Scheduled(
        fixedDelayString =
                "${lesson.scheduler.delay-ms:1000}")
    public void tick() {
        probe.seenTick();
    }
}
```

`@Scheduled` method là **no-arg, void** và được Spring scheduler gọi. `fixedDelay` đo khoảng thời gian **sau khi lần thực thi trước kết thúc** tới lần kế tiếp, trong khi `fixedRate` nhắm thời điểm bắt đầu với chu kỳ cố định. Cả hai không bảo đảm các callback luôn đúng milisecond dưới GC/load, và sự chồng lắp phụ thuộc cấu hình scheduler, task duration và triggers.

**Quan trọng:** component này chỉ có khi `lesson.scheduler.enabled=true`. Trong các tests chỉ kiểm tra `@Async`, bean scheduler absent, tránh task chạy nền không liên quan. Với cron expressions, timezone/DST cũng cần test theo zone/clock policy; latch chỉ chứng minh một tick được phát, không chứng minh toàn bộ lịch cron chính xác.

## 18. ScheduledHeartbeatTest: smoke test scheduler thật

Tạo `src/test/java/example/concurrency/ScheduledHeartbeatTest.java`:

```java
package example.concurrency;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE,
        properties = {
                "lesson.scheduler.enabled=true",
                "lesson.scheduler.delay-ms=50"
        })
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ScheduledHeartbeatTest {

    @Autowired
    private ScheduledProbe probe;

    @Test
    void scheduleInvokesJobWithoutThreadSleep()
            throws Exception {
        CountDownLatch nextTick =
                new CountDownLatch(1);

        probe.arm(nextTick);

        try {
            assertTrue(
                    nextTick.await(5, TimeUnit.SECONDS));
        } finally {
            probe.clear(nextTick);
        }
    }
}
```

**Một JUnit integration method** chứng minh Spring scheduler **đã gọi ít nhất một lần** sau khi test arm latch. Nó không khẳng định chu kỳ chính xác là 50 ms, không assert tick count theo một khoảng wall-clock và không phụ thuộc việc tick xảy ra *trước* lúc test bắt đầu. Nếu job đã chạy trước khi latch arm, test đợi tick kế tiếp.

`@DirtiesContext(AFTER_CLASS)` giúp đóng context và scheduler sau class test này, tránh task có chu kỳ ngắn tiếp tục chạy khi các tests khác dùng Spring context cache. Đây là một **smoke test trigger thực** có timeout tối đa 5 giây. Nó vẫn là test phụ thuộc scheduler thật, nên kết quả có thể bị ảnh hưởng khi CI quá tải; đó là một lý do không dùng loại integration test này cho **mọi** câu lệnh business job.

### Test logic scheduled job độc lập

Trong code production phức tạp, `ScheduledHeartbeat.tick()` nên gọi một service có logic thực. JUnit unit test có thể tạo bean target với mock service và gọi `tick()` trực tiếp để verify delegation; đó là **unit test logic**, không chứng minh cron/fixedDelay trigger hoạt động. Trong ví dụ, probe là test seam và không phải nơi chứa business transaction.

**Đừng dùng `@Scheduled` như một timer chính xác** cho giao dịch tài chính/trả phí/cắt đơn hàng: cần deadline/clock semantics, idempotency, distributed lock hoặc job queue theo SLA.

## 19. Transaction trên thread: latch không truyền transaction Spring

Một nhận thức đặc biệt quan trọng trong **Spring Boot - testing**: Spring test-managed transaction của `@Transactional` JUnit test với JDBC thường được **gắn vào thread hiện tại**.

```text
JUnit test thread                 @Async worker thread
----------------                 --------------------
BEGIN test-managed tx
  |
  +-- submit @Async ------>       work begins
  |                                new thread
  |                                not joined test tx
  |                                own @Transactional
  |                                  if service proxy configured
  |
ROLLBACK test tx                 worker commits separately
```

`CountDownLatch` và `CyclicBarrier` có thể phối hợp **thời điểm** thao tác, nhưng **không chuyển JDBC connection/transaction state sang thread khác**. Nếu worker gọi một `@Transactional` service bean qua Spring proxy, service có thể mở transaction riêng và commit; rollback của JUnit thread không rollback committed row ấy.

**Điều này ảnh hưởng cleanup:** với @Async/HTTP thật, không nên cho `@AfterEach` trong một test-managed transaction xóa dữ liệu committed rồi nghĩ cleanup bền vững. DELETE có thể bị rollback. Cần dedicated test database, key riêng, kết thúc test transaction và cleanup độc lập nếu workflow ghi DB thực.

**Trong bộ runnable của bài này không có DB.** Các tests kiểm tra thread coordination và scheduler. Phần transaction ở mục này là **giới hạn cần ghi nhớ**, không được diễn giải thành bài đã kiểm chứng DB rollback.

Reactive transaction cũng khác: Spring reactive infrastructure thường mang context qua Reactor Context, không phải JDBC ThreadLocal thông thường. Không áp nguyên xi nhận xét về test-managed JDBC transaction cho mọi reactive pipeline.

## 20. Timeout, interruption và xử lý lỗi đúng

### CountDownLatch timeout trả boolean

```java
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError(
            "workers never reached checkpoint");
}
```

Nếu bạn chỉ gọi `ready.await(5, SECONDS);` mà **không kiểm tra giá trị trả về**, test có thể tiếp tục như thể gate mở dù thực ra timeout.

### CyclicBarrier timeout ném exception

```java
try {
    barrier.await(5, TimeUnit.SECONDS);
} catch (TimeoutException error) {
    // generation này broken; điều phối shutdown
}
```

Đây là snippet, cần imports và barrier đã khai báo. Không tiếp tục chạy logic phụ thuộc một barrier đã broken. Nếu dùng `reset()`, phải bảo đảm những parties khác không còn đang chờ generation cũ hoặc đã được thông báo lỗi.

### Interruption không phải “lỗi có thể bỏ qua”

Worker trong Java thường xử lý:

```java
try {
    release.await(5, TimeUnit.SECONDS);
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là snippet của một method `void`/lambda tương ứng. Restore interrupt flag hoặc propagate checked exception theo contract. **Đừng catch rồi bỏ qua**, vì shutdown/cancellation có thể không hoạt động và test treo khi teardown.

### Future.get mang exception về test

- `Future.get(timeout)` có thể ném `TimeoutException`, `ExecutionException`, `InterruptedException`.
- `ExecutionException.getCause()` giúp test nhìn thấy lỗi gốc ở worker.
- `future.cancel(true)` yêu cầu interrupt nếu có thể nhưng **không bảo đảm task đã chấm dứt ngay**; task có thể bỏ qua interruption.
- `CompletableFuture.join()` không có timeout trong overload đơn giản và thường bọc exception bằng `CompletionException`; trong tests cần bounded wait thường chọn `get(timeout)`.
- `CompletableFuture.allOf(...)` hợp nhiều tasks, nhưng nếu cần lỗi của từng task/ID, vẫn phải kiểm tra từng Future/cause.

### Teardown khi assertion fail

```java
try {
    assertTrue(ready.await(5, TimeUnit.SECONDS));
    // kiểm tra state, chuẩn bị cho worker đi tiếp
} finally {
    release.countDown();
    pool.shutdownNow();
}
```

Nếu thiếu `finally`, một assertion fail có thể để worker bị kẹt ở `await()` khiến cả test process không thoát. Khi cleanup production-quality, có thể thêm `awaitTermination(timeout)`, diagnostics thread dump và resource lifecycle rõ. Không gọi một phép chờ vô hạn trong cleanup để “chữa” lỗi timeout.

## 21. Executor starvation và số parties bị đếm sai

Một deadlock kinh điển:

```java
ExecutorService oneThread =
        Executors.newSingleThreadExecutor();
CountDownLatch reached = new CountDownLatch(2);
CountDownLatch release = new CountDownLatch(1);

// Submit 2 tasks; task đầu chờ release.
// Task thứ hai nằm trong queue.
// Test đợi reached về 0 rồi mới release.
```

Đây là **anti-pattern cấu trúc**, không phải test runnable đầy đủ. Nó không thể hoàn thành vì một thread đang bị chặn còn task thứ hai chưa chạy. Giải pháp:

- Tăng worker capacity đủ để các parties đang block có thể chạy, hoặc
- Sắp xếp flow để không giữ toàn bộ pool blocked khi còn những tasks bắt buộc phải chạy, hoặc
- Dùng điều phối khác phù hợp với asynchronous/nonblocking design.

Các lỗi party count:

- `new CountDownLatch(3)` nhưng chỉ có hai lần `countDown()` thực sự → test timeout.
- Worker gọi `countDown()` **hai lần** trong một nhánh nhưng thiếu ở nhánh khác → latch không đại diện đúng “N worker”.
- `CyclicBarrier(3)` nhưng chỉ có 2 workers gọi `await()` → timeout/broken.
- Test thread là một party nhưng không bao giờ `await()`.
- Worker A chờ barrier ở phase 1, worker B đi barrier phase 2 do code branches khác → generation mismatch.
- `Phaser.register()` nhưng quên `arrive()/deregister()` khi task fail → phase kẹt.
- Task chạy `@Async` nhưng do self-invocation thực ra đồng bộ → test thậm chí có thể block ngay trong lời gọi trước khi submit task kế tiếp.

**Đừng sửa bằng cách tăng timeout từ 5 giây lên 5 phút** khi có party count/pool starvation bug. Hãy vẽ đồ thị ai đợi ai.

## 22. Happens-before không đồng nghĩa atomicity hoặc ordering tùy ý

Các primitive concurrency cung cấp memory visibility theo Java Memory Model, nhưng không làm mọi operation atomically correct.

Ví dụ race ở mục 12:

```text
Worker A                    Worker B
--------                    --------
read stock = 1              read stock = 1
    |                            |
bothRead.countDown()        bothRead.countDown()
    |                            |
wait release                wait release
    |                            |
write stock=0               write stock=0
return true                 return true
```

Latch bảo đảm cả hai đã đọc snapshot trước lúc test release; nhưng không có cơ chế ràng buộc **chỉ một worker được quyền quyết định “sold”**. Vì vậy hai workers đều thành công logic dù stock còn 0.

Sửa bằng `AtomicInteger.compareAndSet` cho một process, hoặc transaction/constraint phù hợp khi hệ thống có nhiều JVM. Điều test kiểm soát là **interleaving để tái hiện bug**, không sửa logic nghiệp vụ.

Cũng không nên assert `Thread.currentThread().getName()` sẽ theo một thứ tự tăng, vì names là metadata. Trong Spring async integration test ta chỉ assert **prefix** đủ chứng minh executor được chọn, không phụ thuộc exact thread suffix.

### Visibility khi CountDownLatch đã về 0

Theo JMM, hành động trước `countDown()` happen-before hành động sau `await()` trở về thành công trong thread khác. Nhưng nếu worker còn thay đổi shared state **sau countDown** thì test vẫn có thể đọc state trong lúc worker đang sửa. Muốn assert final state, đợi **Future completion**, một done latch ở `finally`, hoặc synchronization thể hiện đúng điểm hoàn tất.

## 23. @Scheduled và lịch chạy ngoài phạm vi latch

`CountDownLatch` giúp test biết **job đã chạy ít nhất một lần**, không giúp kiểm chứng mọi tính chất của scheduler:

- **fixedRate:** nhắm khoảng giữa start times, có thể chậm khi tasks dài hoặc scheduler quá tải.
- **fixedDelay:** đợi khoảng sau khi execution trước kết thúc.
- **cron:** phụ thuộc zone, DST và clock; tính đúng đắn của cron expression nên được kiểm tra bằng logic phân tích lịch/Clock có kiểm soát khi cần.
- **scheduler pool:** một scheduler thread có thể serialize tasks; nhiều workers/schedulers có thể chạy song song nếu cấu hình.
- **distributed deployment:** nhiều ứng dụng cùng bật scheduled job có thể thực thi cùng lúc; `@Scheduled` không mặc định là distributed lock.
- **transaction:** scheduled job chạy trên scheduler thread, không kế thừa test-managed JDBC transaction.
- **lỗi runtime:** exception từ scheduled task có thể được log và những lần trigger sau có thể tiếp tục tùy scheduler/error handler; test phải quan sát failure theo policy.
- **graceful shutdown:** background task đang chạy phải có termination/ownership policy rõ.

Đừng dùng unit test gọi `job.tick()` rồi nói “cron đã chạy đúng”. Và đừng dùng real scheduled test với `Thread.sleep(1000)` rồi assert tick count chính xác khi cron/delay chịu ảnh hưởng load. Với hợp đồng lịch phức tạp, ưu tiên inject `Clock`, kiểm tra schedule calculation thuần Java hoặc dùng scheduler test utilities theo framework version.

## 24. Tách mức test: unit, integration và end-to-end

| Mức | Cách kiểm thử | Chứng minh được | Không chứng minh |
| --- | --- | --- | --- |
| Java SE unit | `GateCoordinatorTest` | Latch/barrier logic và visibility hợp đồng trong JVM | Spring proxy/scheduler |
| Race reproduction | `RaceConditionTest` | Interleaving lỗi và CAS trong một JVM | Database concurrency cross-process |
| Spring async integration | `ControlledAsyncServiceTest` | `@Async` qua executor, threads/gates/Future lỗi | Real DB/HTTP/socket |
| Spring schedule integration | `ScheduledHeartbeatTest` | Spring trigger gọi ít nhất một tick | Đúng mọi cron/DST/SLO |
| Database integration | SQL + transaction + concurrency barriers | Lock/constraint/isolation engine | Các side effects bên ngoài DB |
| Full E2E | App + broker/HTTP/DB | Kết quả workflow theo setup thật | Tất cả production failure windows |

**Không phải tất cả concurrency tests đều phải khởi động Spring context.** Khi thuật toán chỉ phụ thuộc Java `AtomicInteger` hoặc `CyclicBarrier`, JUnit thuần nhanh và dễ chẩn đoán hơn. Chỉ mở Spring khi cần test scheduling/async proxy/bean lifecycle thật.

**Không dùng `@MockBean`/`@MockitoBean` chỉ để làm test nhanh mà quên boundary**: nếu mock executor hoặc service, test có thể không còn thực sự chạy thread khác. Mock là tốt cho business logic, nhưng không chứng minh thread switching.

## 25. Chạy các test

Từ project root có Gradle wrapper:

```bash
./gradlew test --tests example.concurrency.GateCoordinatorTest
./gradlew test --tests example.concurrency.RaceConditionTest
./gradlew test --tests example.concurrency.ControlledAsyncServiceTest
./gradlew test --tests example.concurrency.ScheduledHeartbeatTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.concurrency.GateCoordinatorTest"
.\gradlew.bat test --tests "example.concurrency.RaceConditionTest"
.\gradlew.bat test --tests "example.concurrency.ControlledAsyncServiceTest"
.\gradlew.bat test --tests "example.concurrency.ScheduledHeartbeatTest"
```

**Số lượng methods:**

| Test class | Methods | Cần Spring? |
| --- | ---: | --- |
| `GateCoordinatorTest` | 4 | Không |
| `RaceConditionTest` | 2 | Không |
| `ControlledAsyncServiceTest` | 2 | Có, để kiểm tra @Async proxy |
| `ScheduledHeartbeatTest` | 1 | Có, để kiểm tra scheduler |
| **Tổng** | **9** | |

Đây là **kết quả kỳ vọng khi project và runtime được thiết lập đúng**, không phải tuyên bố đã thực thi JUnit trong môi trường người học. Console Gradle/JUnit thay đổi theo phiên bản/runner/logging nên không có một stdout chung chính xác. Chỉ demo Java SE ở mục 10 có stdout xác định sau khi hai thao tác hoàn tất trong thời hạn.

Nếu chạy full suite, lưu ý Spring TestContext cache và @DirtiesContext của scheduled test. Nếu có database/shared static state trong project thật, mỗi test cần dữ liệu riêng và cleanup, không dựa vào thứ tự methods.

## 26. Chẩn đoán lỗi theo triệu chứng

**A. `await(timeout)` trả false.** Worker chưa đủ số `countDown()`; kiểm tra count, submit tasks, branch exception, pool capacity và checkpoint placement.

**B. `Future.get(...)` ném TimeoutException.** Task chưa hoàn tất trong hạn. Kiểm tra nó đang blocked gate, barrier, I/O hoặc queue; đừng nghĩ Future timeout tự cancel task.

**C. `ExecutionException`.** Worker đã ném lỗi; inspect `getCause()` trước khi đổi timeout.

**D. `BrokenBarrierException`.** Một party bị interrupt/timeout/reset, barrier generation bị broken; log parties/generation và điều phối shutdown.

**E. `CyclicBarrier` không bao giờ trip.** Số parties sai hoặc executor không đủ workers; test thread có thể đã được tính nhầm.

**F. `Phaser` không advance.** Party đã register nhưng chưa arrive/deregister, hoặc termination/phase management sai.

**G. @Async method chạy trên main/JUnit thread.** `@EnableAsync` chưa bật, thiếu executor bean hoặc self-invocation qua `this.method()`, target không đi qua Spring proxy.

**H. @Scheduled test xanh khi gọi method trực tiếp nhưng trigger không chạy.** Chưa có `@EnableScheduling`, bean bị `@ConditionalOnProperty` loại, cron/zone sai hoặc scheduler chưa sẵn sàng.

**I. Test pass riêng, fail khi chạy cả suite.** Shared static state, context cache, async tasks còn chạy, pool starvation, parallel JUnit hoặc cleanup không đúng.

**J. Thread leak/JVM không thoát sau fail.** Worker kẹt ở `await()` và test không release trong `finally`; executor chưa shutdown.

**K. Test assert số ticket/reservations sai.** Check-then-set không atomic, dùng CAS/locks/transactions thay vì thêm latch.

**L. Test có @Transactional nhưng async DB row vẫn tồn tại.** Worker không join test transaction thread; cleanup ở transaction độc lập và xác minh after-commit state.

## 27. Các lỗi phổ biến cần tránh

**1. `Thread.sleep` để chờ async.** Thời gian cố định không đồng bộ với hoàn thành thực.

**2. Gọi `await(timeout)` rồi bỏ qua boolean.** Test có thể tiếp tục dù timeout.

**3. Dùng `await()` vô hạn trong CI.** Deadlock làm job treo.

**4. Quên `release.countDown()` trong `finally`.** Assertion fail để lại worker chờ mãi.

**5. Đếm số parties sai.** `CountDownLatch(3)` nhưng chỉ 2 signals; `CyclicBarrier(3)` nhưng chỉ 2 await callers.

**6. Executor nhỏ hơn số blocked workers cần đến gate.** Tasks bị queue, test đợi không thể hoàn thành.

**7. Đếm latch là bằng chứng task thành công.** Worker có thể countDown rồi ném lỗi; phải lấy Future.

**8. Dùng một CountDownLatch qua nhiều rounds và mong tự reset.** CountDownLatch one-shot; dùng object mới/CyclicBarrier/Phaser.

**9. Dùng reset() của CyclicBarrier khi waiters còn sống mà không phối hợp.** Có thể phá generation đang chờ.

**10. Dùng getNumberWaiting/getCount snapshot để quyết định state.** Có race; dùng await/response sync.

**11. Chỉ dùng AtomicInteger.get + set cho read-modify-write.** Hai lệnh đơn lẻ atomic không làm tổ hợp thành atomic.

**12. Claim race đã được fix chỉ vì test hai threads pass vài lần.** Cần invariant, đúng synchronization và test interleavings phù hợp.

**13. Catch InterruptedException rồi bỏ qua.** Phá cancellation/shutdown, tăng khả năng thread leak.

**14. Future timeout nhưng không cleanup/cancel.** Task có thể tiếp tục thay đổi state sau khi test fail.

**15. @Async self-invocation.** Annotation không được proxy intercept; method chạy đồng bộ.

**16. Void @Async bị lỗi nhưng test không quan sát.** Dùng CompletableFuture/callback hoặc error handler.

**17. Mock toàn bộ service/executor khi muốn test thread switching.** Mock không chứng minh executor thực.

**18. Kiểm tra @Scheduled bằng sleep rồi assert count chính xác.** Wall-clock timing không ổn định.

**19. Đặt timeout quá nhỏ so với CI capacity, hoặc tăng timeout quá lớn để che deadlock.** Chọn budget hợp lý và chẩn đoán graph chờ.

**20. Dùng latch để tin async JDBC transaction join test transaction.** Đồng bộ thời gian không chuyển transaction qua thread.

**21. Không cleanup scheduled context/test executor.** Background tasks có thể tồn tại sau method và phá tests khác.

**22. Assert thứ tự stdout từ worker threads.** Scheduler không cam kết thứ tự; in kết quả từ coordinator hoặc so sánh set/map.

**23. Dùng `@Timeout` preemptive thread mode mà không xét transaction bound thread.** Với Spring TestContext JDBC, callback chạy thread khác có thể nằm ngoài transaction test.

**24. Dùng latch mà không đặt memory/side-effect checkpoint đúng vị trí.** Test có thể nhận tín hiệu quá sớm và đọc state chưa hoàn thành.

## 28. Checklist QA cuối cùng

**Ý nghĩa primitive:**

- Đã chọn latch one-shot hay barrier nhiều phase đúng bài toán?
- Nếu dùng Phaser, parties có register/deregister chính xác không?
- CountDownLatch có count đúng số signals không? Barrier có đúng số await callers không?
- Có phân biệt `countDown()` không block với `CyclicBarrier.await()` block?

**Test orchestration:**

- Hai latches ready/release có được tạo trước khi submit tasks?
- Worker signal checkpoint trước khi block đúng chỗ?
- Executor đủ workers để mọi party có thể đến barrier?
- Mọi await/get đều có timeout hữu hạn, ngoại trừ chỗ có owner cleanup được chứng minh?
- Có assert boolean await return, inspect Future exceptions?
- Có `release.countDown()` trong finally và shutdown executor?
- Có restore interruption đúng cách?

**Đúng đắn concurrency:**

- Shared state có atomic/lock/transaction protection thực không?
- Test cố ý tái hiện race bằng interleaving kiểm soát, không chỉ chạy 100 lần may rủi?
- Assertions có tránh phụ thuộc scheduling order/timing/tên thread cụ thể?
- Có phân biệt test pass là reproducer bug hay verification fix?
- Có chờ **completion signal** khi cần final state chứ không chỉ started signal?

**Spring Boot:**

- `@EnableAsync`, `@Async("lessonExecutor")` và bean proxy hoạt động?
- `@EnableScheduling` và property bật schedule đúng scope?
- @Scheduled test kiểm tra trigger thật bằng latch, không dùng Thread.sleep?
- Các background tasks có cleanup và context lifecycle rõ?
- @Transactional test có bảo đảm side effects @Async nằm trong đúng transaction không, hay cần DB cleanup độc lập?

**Kết luận:** CountDownLatch, CyclicBarrier và Phaser cho test một cách **phối hợp thread có thể giải thích và lặp lại**. `CountDownLatch` phù hợp gate/counter một lần; `CyclicBarrier` phù hợp nhiều rounds với số parties cố định; `Phaser` phù hợp parties thay đổi qua các phase. Phối hợp tốt không dừng ở `await()`: cần **timeout, Future exception, finally release, executor cleanup, isolation và atomic state**. Khi kiểm tra Spring `@Async` và `@Scheduled`, hãy quan sát hành vi của executor/scheduler thật nhưng không dựa vào sleep hoặc suy diễn transaction đã được chuyển sang worker thread.

## 29. Tài liệu tham khảo

- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot latch, timed await và happens-before.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): parties, generations, barrier action, broken state và reset.
- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): register/deregister parties, phases, termination, timed wait.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future, shutdown, awaitTermination.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): asynchronous result, errors và completion.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `TaskExecutor`, `@EnableAsync`, `@Async`, `@Scheduled`, proxy và scheduler.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configuration và executor customization.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): thread-bound test transaction và preemptive timeouts.
