# JUnit Jupiter: Timeout và khác biệt giữa giới hạn thời gian thông thường với preemptive timeout

## 1. Hiểu đúng mục tiêu của timeout trong kiểm thử

Một bài kiểm thử có thể đưa ra **kết quả đúng** nhưng mất quá nhiều thời gian do deadlock, polling sai, I/O bị treo hoặc thuật toán bất thường. JUnit Jupiter cung cấp các cơ chế để đặt **ngân sách thời gian** và đánh dấu test thất bại khi vượt ngân sách đó.

Có hai ý tưởng thường bị nhầm:

- **Timeout thông thường (non-preemptive):** cho đoạn code được kiểm tra chạy đến khi kết thúc, sau đó xác định có vượt giới hạn không. API điển hình: `Assertions.assertTimeout(...)`.
- **Preemptive timeout:** theo dõi thời hạn và **cố gắng kết thúc sớm việc chờ** khi hết thời gian. API điển hình: `Assertions.assertTimeoutPreemptively(...)`. Jupiter chạy callback trên **thread khác** rồi cố gắng interrupt khi quá hạn.

“Preemptive” ở đây **không đồng nghĩa cưỡng bức hủy an toàn mọi công việc**. Java `Thread.interrupt()` là cơ chế phối hợp: tác vụ có thể phản ứng và dừng, hoặc phớt lờ tín hiệu và tiếp tục chạy.

Riêng annotation `@Timeout` có cách vận hành phụ thuộc `threadMode`. Đừng mặc định coi `@Timeout` hoàn toàn giống `assertTimeout`: ở chế độ `SAME_THREAD`, Jupiter có thể **interrupt thread thực thi test** khi quá hạn, trong khi `assertTimeout` chủ động chờ callback hoàn thành rồi mới đánh giá thời gian.

**Kết quả học tập:** sau bài này, bạn có thể giải thích thời điểm fail và thread sử dụng; chọn `assertTimeout`, `assertTimeoutPreemptively` hoặc `@Timeout` đúng mục tiêu; biết các giới hạn của interrupt; tránh lỗi transaction rollback khi kết hợp Spring Boot với preemptive timeout.

## 2. So sánh bốn cơ chế quan trọng

| Cơ chế | Phạm vi áp dụng | Thread chạy nội dung | Khi vượt hạn | Nguy cơ cần nhớ |
| --- | --- | --- | --- | --- |
| `assertTimeout(duration, executable)` | Một callback hoặc đoạn code | **Cùng thread** gọi assertion | Chờ callback chạy xong rồi fail theo thời gian đã đo | Test có thể tiếp tục treo rất lâu nếu callback không kết thúc |
| `assertTimeoutPreemptively(duration, executable)` | Một callback hoặc đoạn code | **Thread khác** | Assertion fail khi hết hạn, cố gắng interrupt thread đang chạy callback | Callback có thể vẫn chạy; `ThreadLocal`/test-managed transaction không đi theo |
| `@Timeout(..., threadMode = SAME_THREAD)` | Phương thức JUnit được annotation | **Thread thực thi test hiện tại** | Bộ theo dõi thời gian cố interrupt thread sau hạn; Jupiter ghi nhận timeout | Interrupt không bảo đảm ngắt JDBC/network/logic không hợp tác |
| `@Timeout(..., threadMode = SEPARATE_THREAD)` | Phương thức JUnit được annotation | **Thread riêng** | Cố interrupt/ghi nhận timeout khi quá hạn | Rủi ro thread-bound context và side effect tương tự preemptive assertion |

Hai lựa chọn của `@Timeout` có vai trò khác `@Timeout.ThreadMode.INFERRED`: giá trị `INFERRED` là mặc định; nó lấy quyết định từ cấu hình `junit.jupiter.execution.timeout.thread.mode.default`, và nếu không được cấu hình hợp lệ thì **fallback sang `SAME_THREAD`**.

**Phân biệt việc kiểm thời hạn với benchmark:** timeout test phát hiện công việc mất thời gian không chấp nhận được trong môi trường kiểm thử; nó **không phải** cách đo hiệu năng chính xác hay thay thế profiler/microbenchmark. CPU, CI load, GC, mạng và startup làm thời gian dao động.

## 3. assertTimeout(): chạy hoàn tất rồi đánh giá

Import:

~~~java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeout;
~~~

Dùng cho một callback `Executable` không có giá trị trả về:

~~~java
assertTimeout(Duration.ofSeconds(2), () -> {
    service.performOperation();
});
~~~

Đoạn code trên là **mã minh họa**: `service` cần do dự án cung cấp. Nếu `performOperation()` chạy 2,3 giây rồi trả về bình thường, assertion **fail sau khi 2,3 giây đã trôi qua**, chứ không làm lời gọi dừng đúng giây thứ 2. Nếu phương thức bị treo vô hạn, assertion này cũng không thể tự giải thoát thread gọi nó.

Với một `ThrowingSupplier<T>`, API còn trả về giá trị từ callback:

~~~java
int result = assertTimeout(
        Duration.ofSeconds(2),
        () -> Math.multiplyExact(12, 4));

assertEquals(48, result);
~~~

`assertEquals` trong đoạn minh họa cần import từ `org.junit.jupiter.api.Assertions`. Trong trường hợp thành công, kết quả là `48`. Nếu callback ném exception ngoài dự kiến, test vẫn thất bại; timeout không tự chuyển lỗi nghiệp vụ thành kết quả thành công.

Ưu điểm quan trọng của `assertTimeout` là **giữ nguyên thread của đoạn code được kiểm tra**. Những ngữ cảnh gắn với thread — ví dụ một số `ThreadLocal`, transaction do Spring TestContext quản lý — vẫn có thể truy cập trong callback, miễn là phần mềm không tự tạo thread khác bên trong.

**Khi nên chọn:** kiểm thử service/validation/repository trong cùng test-managed transaction, kiểm một nhánh xử lý có deadline mang tính cảnh báo, hoặc cần kết quả/ngoại lệ và không muốn tạo ranh giới thread mới.

**Giới hạn:** do không hủy sớm công việc, nó không đủ làm cơ chế chống treo cứng cho lời gọi I/O có thể chặn vô hạn. Hãy thêm timeout phù hợp của chính HTTP client, JDBC statement, socket hoặc broker; tách worker/process khi cần cơ chế cô lập mạnh hơn.

## 4. assertTimeoutPreemptively(): chạy trên thread riêng và cố ngắt sớm

Import:

~~~java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;
~~~

Ví dụ kiểm một phép toán thuần:

~~~java
int result = assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> Math.multiplyExact(12, 4));

assertEquals(48, result);
~~~

Đoạn này cũng trả kết quả `48` nếu hoàn tất đúng hạn. Khác biệt lớn là **callback chạy trên worker thread khác với thread gọi assertion**. Khi callback không hoàn tất đúng thời hạn, Jupiter đánh dấu timeout và cố `interrupt()` worker thread. Vì thế bên gọi có thể nhận kết quả fail sớm hơn thời điểm callback thực sự ngừng làm việc.

Minh họa bằng giả định tác vụ chạy khoảng 500 ms và giới hạn là 100 ms:

| Mốc | `assertTimeout(100 ms)` | `assertTimeoutPreemptively(100 ms)` |
| --- | --- | --- |
| t = 0 | Bắt đầu callback ngay trên thread gọi | Giao callback cho worker thread |
| t ≈ 100 ms | Callback vẫn chạy; assertion tiếp tục đợi | Phát hiện hết hạn, cố interrupt worker và trả lỗi timeout |
| t ≈ 500 ms | Callback hoàn thành, assertion xác nhận quá hạn và fail | Worker **có thể đã dừng** hoặc **vẫn chạy** nếu không hợp tác với interrupt |

Các mốc là **mô hình khái niệm**, không phải cam kết lịch chạy chính xác đến từng mili giây. Scheduling và hệ điều hành có thể làm thời điểm thực tế lệch.

Tại sao “cố interrupt” không đồng nghĩa “đã hủy”?

- `Thread.sleep(...)`, `Object.wait(...)` và các thao tác chặn *interruptible* thường ném `InterruptedException`, cho phép callback dừng.
- Vòng lặp CPU không kiểm tra trạng thái interrupt có thể tiếp tục chạy.
- Một số I/O, native call hoặc thư viện có thể không phản ứng ngay với interrupt.
- Callback có thể bắt `InterruptedException` rồi bỏ qua, tiếp tục ghi dữ liệu hoặc phát sự kiện.
- Side effect đã thực hiện **không tự rollback** chỉ vì assertion báo timeout.

Tuyệt đối không dùng `assertTimeoutPreemptively` như một cơ chế quản lý giao dịch, hủy HTTP request hoặc đảm bảo cleanup. Nếu chủ đích là chống hang của một tài nguyên bên ngoài, đặt thêm timeout và hủy ở chính client/driver/protocol, đồng thời kiểm tác vụ sau khi bị hủy có an toàn không.

## 5. @Timeout: áp dụng cho phương thức, có chế độ thread rõ ràng

`@Timeout` là annotation của **JUnit Jupiter**, khác `@Test(timeout = ...)` kiểu JUnit 4.

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class TimeoutAnnotationExamples {

    @Test
    @Timeout(value = 2, unit = TimeUnit.SECONDS,
             threadMode = Timeout.ThreadMode.SAME_THREAD)
    void sameThreadDeadline() {
        int result = Math.addExact(20, 22);
        org.junit.jupiter.api.Assertions.assertEquals(42, result);
    }

    @Test
    @Timeout(value = 2, unit = TimeUnit.SECONDS,
             threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
    void separateThreadDeadline() {
        int result = Math.addExact(20, 22);
        org.junit.jupiter.api.Assertions.assertEquals(42, result);
    }
}
~~~

Đây là **ví dụ Java/JUnit độc lập về annotation**, chỉ thao tác với dữ liệu thuần nên cả hai test đều PASS. Cách viết tường minh `threadMode` giúp người đọc thấy ranh giới thread thay vì phụ thuộc cấu hình mặc định.

**Ý nghĩa:**

- `@Timeout(2)` mặc định lấy `unit = TimeUnit.SECONDS`, vì vậy tương đương giới hạn 2 giây.
- `SAME_THREAD` thực thi phương thức test trong thread của test; khi quá hạn, JUnit dùng một thread giám sát để **interrupt thread đang chạy test**. Đây không phải hành vi “chờ đến khi method tự kết thúc” giống hệt `assertTimeout`.
- `SEPARATE_THREAD` thực thi method trong thread riêng và cố interrupt khi hết hạn; có cùng nhóm rủi ro về `ThreadLocal`, test transaction và side effect với `assertTimeoutPreemptively`.
- `INFERRED` là mặc định, sử dụng cấu hình `junit.jupiter.execution.timeout.thread.mode.default`; nếu thiếu/không hợp lệ thì chọn `SAME_THREAD`.

### @Timeout trên lớp và các trường hợp đặc biệt

Có thể gắn `@Timeout` trên lớp để đặt giới hạn mặc định cho các **test/test template/test factory methods** trong lớp, kể cả lớp `@Nested`, trừ khi được annotation riêng ghi đè. **Annotation cấp lớp không tự áp dụng cho lifecycle methods** như `@BeforeEach` và `@AfterEach`. Có thể gắn `@Timeout` trực tiếp lên một lifecycle method khi muốn giới hạn chính phương thức đó, tùy version Jupiter hỗ trợ.

Với `@ParameterizedTest` hoặc `@RepeatedTest`, mỗi invocation được kiểm giới hạn riêng. Với `@TestFactory`, `@Timeout` gắn trên factory chỉ đo thời gian **tạo ra dynamic tests**, không đo toàn bộ thời gian thực thi các `DynamicTest` được tạo; cần `assertTimeout(...)` hoặc `assertTimeoutPreemptively(...)` trong từng dynamic test nếu muốn giới hạn phần thực thi.

Không đặt deadline quá thấp cho test có khởi động container/context hoặc phụ thuộc CI; tốc độ thực tế không chỉ phụ thuộc logic Java trong phương thức test.

## 6. Ví dụ hoàn chỉnh Java 17+: nhìn thấy sự khác biệt giữa hai thread

File `src/test/java/example/TimeoutStrategiesTest.java` dưới đây gồm năm bài kiểm thử độc lập. Ví dụ yêu cầu dự án Java 17+ có JUnit Jupiter 5.x tương thích (thường có qua `spring-boot-starter-test` trong Spring Boot). Không cần Spring context, DB, HTTP server hoặc Docker.

~~~java
package example;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTimeout;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

@DisplayName("So sánh timeout của JUnit Jupiter")
class TimeoutStrategiesTest {

    private Thread testThread;

    @BeforeEach
    void rememberTestThread() {
        testThread = Thread.currentThread();
    }

    @Test
    @DisplayName("assertTimeout chạy cùng thread đang gọi")
    void nonPreemptiveUsesCallingThread() {
        Thread callbackThread = assertTimeout(
                Duration.ofSeconds(5),
                Thread::currentThread);

        assertSame(testThread, callbackThread);
    }

    @Test
    @DisplayName("assertTimeout trả được kết quả từ supplier")
    void normalTimeoutReturnsValue() {
        int total = assertTimeout(
                Duration.ofSeconds(5),
                () -> Math.addExact(1_200, 800));

        assertEquals(2_000, total);
    }

    @Test
    @DisplayName("assertTimeoutPreemptively dùng thread khác")
    void preemptiveUsesAnotherThread() {
        Thread callbackThread = assertTimeoutPreemptively(
                Duration.ofSeconds(5),
                Thread::currentThread);

        assertNotSame(testThread, callbackThread);
    }

    @Test
    @DisplayName("ThreadLocal của caller không tự truyền sang worker")
    void preemptiveDoesNotInheritThreadLocal() {
        ThreadLocal<String> trace = new ThreadLocal<>();
        trace.set("trace-42");

        try {
            String sameThreadValue = assertTimeout(
                    Duration.ofSeconds(5),
                    trace::get);

            String workerThreadValue = assertTimeoutPreemptively(
                    Duration.ofSeconds(5),
                    trace::get);

            assertEquals("trace-42", sameThreadValue);
            assertNull(workerThreadValue);
        } finally {
            trace.remove();
        }
    }

    @Test
    @Timeout(value = 5, unit = TimeUnit.SECONDS,
             threadMode = Timeout.ThreadMode.SAME_THREAD)
    @DisplayName("@Timeout SAME_THREAD giữ thread của test")
    void annotationSameThread() {
        assertSame(testThread, Thread.currentThread());
        assertEquals(6, Math.multiplyExact(2, 3));
    }
}
~~~

**Phân tích kỹ bài test:**

1. `rememberTestThread()` chạy trước mỗi method, ghi nhận thread hiện tại. Theo lifecycle mặc định, instance test không dùng chung giữa các method.
2. `nonPreemptiveUsesCallingThread()` nhận lại chính đối tượng `Thread` qua `assertTimeout`. `assertSame` kiểm **cùng identity**, không chỉ cùng tên thread.
3. `normalTimeoutReturnsValue()` cho thấy callback kiểu supplier trả `2000`; Jupiter kiểm thời lượng và trả giá trị khi thành công.
4. `preemptiveUsesAnotherThread()` gọi `Thread.currentThread()` bên trong callback. Kết quả là một thread khác với thread chạy bài test.
5. `preemptiveDoesNotInheritThreadLocal()` tạo một `ThreadLocal` thông thường (không phải `InheritableThreadLocal`). Callback đồng thread đọc được `trace-42`, còn callback trên worker mới đọc `null`. Đây là mô hình thu nhỏ của rủi ro mất ngữ cảnh thread.
6. `annotationSameThread()` minh họa chọn `@Timeout(... SAME_THREAD)` tường minh trong test có setup và assertion.

**Kỳ vọng chạy:** cả **5 bài kiểm thử PASS** trong môi trường JUnit Jupiter 5.x phù hợp; chúng không in stdout. Ngưỡng 5 giây đủ rộng cho thao tác đơn giản, giảm nguy cơ fail do jitter trong CI. Chúng **không đo tốc độ thuật toán** và không mô phỏng một tác vụ bị treo để tránh tạo test cố ý thất bại trong suite.

### Chạy với Gradle

Trong một dự án Spring Boot đang có Gradle plugin và dependency management, cấu hình `build.gradle` thường gồm (đây là **đoạn cấu hình**, không phải file build hoàn chỉnh):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy từ root của module/build phù hợp:

~~~bash
./gradlew test --tests example.TimeoutStrategiesTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.TimeoutStrategiesTest
~~~

Khi cấu hình hợp lệ, Gradle/JUnit Platform phát hiện cả năm phương thức, test task thành công và Gradle báo `BUILD SUCCESSFUL` nếu các tác vụ liên quan cũng thành công. Không có stdout chính xác cố định do IDE/Gradle log format thay đổi theo môi trường.

Trong dự án thực tế, class nghiệp vụ được kiểm phải là **production implementation** từ `src/main/java`. Ví dụ trên cố ý kiểm đúng semantics timeout/thread của JUnit nên không chứa bean Spring.

## 7. Rủi ro rất quan trọng trong Spring Boot: mất test-managed transaction

Spring TestContext hỗ trợ kiểm thử `@Transactional`: trước khi gọi test, framework có thể mở **test-managed transaction** rồi rollback khi test kết thúc. Trạng thái transaction được gắn với **thread hiện tại** qua `ThreadLocal` (ví dụ context trong transaction synchronization).

Sơ đồ đơn giản:

~~~text
Test thread (Spring đã bind transaction T1)
  |
  +-- assertTimeout(...) --------> service/repository dùng T1
  |                                |__ test kết thúc -> rollback T1
  |
  +-- assertTimeoutPreemptively(...)
          |
          +-- Worker thread ------> KHÔNG có ThreadLocal của T1
                                      |__ service/repository có thể
                                          mở transaction khác và COMMIT
Test thread rollback T1 không rollback được những ghi chép đã commit ở worker.
~~~

Do vậy, một bài test **có thể PASS hoặc FAIL vì timeout nhưng vẫn để lại dữ liệu trong DB** nếu gọi code ghi dữ liệu qua worker thread. Điều này đặc biệt nguy hiểm khi test suite dùng chung database kiểm thử: bài sau có thể thấy dữ liệu rò rỉ từ bài trước.

### Cách dùng sai (minh họa, không phải một file Java độc lập)

~~~java
// Trong một Spring test class có @Transactional và OrderRepository được inject:
@Test
void unsafePreemptiveWrite() {
    assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
        repository.save(new Order("ORD-100"));
    });
}
~~~

Ở đây `repository` và `Order` là các thành phần giả định của ứng dụng; đoạn này chỉ minh họa **anti-pattern**. Nếu repository dùng transaction độc lập ở worker, lệnh ghi có thể được commit dù transaction của test thread bị rollback. Đừng lấy kết quả rollback của test thread làm bằng chứng dữ liệu ở worker đã được dọn.

### Cách thích hợp hơn cho test transaction (minh họa)

~~~java
// Trong cùng Spring test class @Transactional:
@Test
void usesTestManagedTransaction() {
    assertTimeout(Duration.ofSeconds(5), () -> {
        repository.save(new Order("ORD-100"));
        assertEquals(1, repository.count());
    });
}
~~~

`assertTimeout` chạy callback trong thread của test, giúp code được quản lý bởi Spring tham gia đúng test-managed transaction **nếu** propagation và các điều kiện transaction của ứng dụng tương thích. Sau đó Spring có thể rollback transaction theo hợp đồng kiểm thử thông thường.

Chú ý: `assertTimeout` không cưỡng bức dừng query đang treo. Nếu tích hợp có nguy cơ chờ I/O lâu, cần thêm giới hạn ở cấp JDBC statement, connection/driver, HTTP client hoặc server. Với giới hạn cả phương thức, `@Timeout(threadMode = SAME_THREAD)` thường an toàn hơn về thread-bound context so với `SEPARATE_THREAD`, nhưng **interrupt vẫn không bảo đảm hủy ngay mọi thao tác I/O**.

**Ngoại lệ cần hiểu:** đây là cảnh báo về *test-managed transactions*. Các transaction do application tạo có thể có propagation khác, và nhiều code chủ động chạy bất đồng bộ cũng sẽ tách khỏi thread test. Không kết luận “mọi call trên worker đều commit” trong mọi cấu hình; kết luận đúng là **không được tin rằng rollback của test thread bao phủ worker thread**.

## 8. Vì sao ThreadLocal, context và side effect dễ gây lỗi?

Các framework có thể gắn dữ liệu vào thread: transaction synchronization, một số security context, MDC/correlation ID, dữ liệu request, locale hoặc tracing. Context của một thread **không tự động** xuất hiện ở thread khác. Một số thư viện có cơ chế propagation riêng, nhưng bạn không nên giả định nó hoạt động chỉ vì tên API là “timeout”.

Tác động cụ thể:

- Trong unit test thuần Java, callback preemptive đọc `ThreadLocal` có thể trả `null` dù thread gọi đã thiết lập giá trị.
- Trong Spring integration test, một repository/service được gọi từ worker có thể không thấy transaction đã bind của test.
- Tracing/logging context có thể mất correlation ID khiến báo cáo khó theo dõi.
- Security context và request context có thể hoạt động khác nếu không được propagation tường minh.
- Async task được callback tạo ra có thể sống lâu hơn assertion và phát side effect sau khi test đã chuyển trạng thái.

Nếu code đang kiểm **cố ý** chạy bất đồng bộ, cần dùng các cơ chế phối hợp phù hợp với công nghệ đó: `Future`/`CompletableFuture` có timeout, cancellation có xử lý interrupt, timeouts của HTTP/DB client, test fixture cô lập và cleanup có thể xác minh. Đừng dùng `assertTimeoutPreemptively` để che vấn đề hủy tác vụ; preemptive assertion chỉ cung cấp một tín hiệu test.

## 9. Ba kịch bản lựa chọn đúng trong Spring Boot

### Kịch bản A: Unit test logic thuần Java

Ví dụ một service tính toán tổng tiền từ dữ liệu đã có trong RAM. Chọn `assertTimeout(Duration.ofSeconds(...), () -> service.calculate(...))` để kiểm một ngân sách rộng và assert kết quả, vì đây là lời gọi đơn giản cùng thread. Nếu logic thuần CPU có nguy cơ vòng lặp vô hạn và bạn thực sự cần fail sớm, `assertTimeoutPreemptively` có thể hữu ích, **nhưng chỉ khi bạn quản lý được khả năng thread chạy mãi sau timeout**. Với vòng lặp không hợp tác interrupt, test runner có thể vẫn giữ tài nguyên.

### Kịch bản B: Repository integration test với @Transactional

Chọn `assertTimeout` trong callback hoặc `@Timeout(..., SAME_THREAD)` ở test method, và cấu hình statement/driver timeout phù hợp. Kiểm rollback bằng các test tích hợp riêng khi đó là rủi ro quan trọng. Tránh `assertTimeoutPreemptively` hoặc `@Timeout(..., SEPARATE_THREAD)` cho code tham gia test-managed transaction.

### Kịch bản C: HTTP call hoặc Kafka/Redis có khả năng treo

Đừng chỉ dùng một timeout ở Jupiter để kiểm soát hạ tầng. Hãy cấu hình **connect timeout / read timeout / request timeout / transaction timeout** đúng giao thức và client, dùng test container hoặc stub server khi cần kiểm integration behavior, rồi đặt `@Timeout` trên method như **lưới bảo vệ cuối cùng** cho suite. Một timeout ở test framework không thay cho giới hạn network, và cũng không chứng minh hệ thống đã rollback/cancel request.

## 10. Cấu hình timeout mặc định và khi debug

JUnit Jupiter cho phép đặt default timeout trong file `src/test/resources/junit-platform.properties`. Ví dụ dưới đây dành cho dự án dùng Jupiter version hỗ trợ các configuration parameters này:

~~~properties
# Ngưỡng mặc định 5 giây cho các test methods dùng @Test.
junit.jupiter.execution.timeout.test.method.default = 5 s

# Giữ thread cho @Timeout INFERRED nếu có context gắn với thread.
junit.jupiter.execution.timeout.thread.mode.default = same_thread

# Tạm tắt timeout khi debugger (JDWP) đang được nhận diện.
junit.jupiter.execution.timeout.mode = disabled_on_debug
~~~

Giải thích:

- `junit.jupiter.execution.timeout.test.method.default` là giới hạn mặc định của `@Test` methods không có annotation timeout cụ thể phù hợp. Có nhiều mức khác như `...testable.method.default`, `...lifecycle.method.default` và `...default`; cấu hình cụ thể ưu tiên hơn cấu hình tổng quát.
- `junit.jupiter.execution.timeout.thread.mode.default` chỉ quyết định chế độ khi annotation dùng `INFERRED`. Không thay đổi bản chất của `assertTimeoutPreemptively`: nó **luôn chạy callback trên thread riêng**.
- `disabled_on_debug` hữu ích vì đặt breakpoint có thể khiến test vượt giới hạn dù logic vẫn đúng. Đây là cơ chế xác định debug từ thông số JVM; không phải “mọi công cụ IDE” đều được phát hiện như nhau.
- Có thể dùng `enabled` hoặc `disabled` cho `junit.jupiter.execution.timeout.mode` khi phù hợp chính sách dự án; CI nên có giới hạn phù hợp để phát hiện test treo.

**Đừng chỉnh toàn suite chỉ để chữa một test thất bại liên tục.** Kiểm nguyên nhân (DB lock, HTTP timeout, máy CI, fixture dùng chung), sau đó chọn ngưỡng hợp lý cho đúng nhóm test.

## 11. Timeout có thể tạo flakiness nếu chọn sai ngưỡng

Một test có thể đôi khi PASS, đôi khi FAIL khi ngưỡng quá sát thời gian chạy thông thường.

Ví dụ không nên dùng ngưỡng 10 ms cho test cần khởi động Spring context, giao tiếp DB container hoặc dùng network. Trên máy local rảnh rỗi nó có thể PASS, nhưng trên CI tải nặng sẽ FAIL. Ngay cả test thuần Java đôi khi chịu pause do GC hoặc hệ điều hành.

Giải pháp theo bản chất lỗi:

1. **Đo và hiểu đường chạy**: test đang chờ file, DB, network, lock hay tính toán?
2. **Phân biệt setup và execution**: dùng `@Timeout` cho đúng phạm vi; cấu hình lifecycle riêng nếu setup bị treo.
3. **Chọn deadline có biên an toàn** dựa trên CI thực tế thay vì tối ưu đến từng milli giây.
4. **Dùng đồng hồ giả và điều kiện chờ** khi kiểm logic thời gian: inject `Clock` cho nghiệp vụ theo ngày giờ, dùng condition-based wait thay cho `Thread.sleep` cứng.
5. **Khi kiểm chính hành vi timeout của client**, dùng stub server hoặc fake đồng hồ được kiểm soát để xác minh exception/cancellation, không phụ thuộc độ chính xác của scheduler tới từng mili giây.
6. **Không dùng `assertTimeoutPreemptively` che lỗi thiết kế**: thêm deadline đúng chỗ (SQL query, retry policy, HTTP client) để kiểm tính an toàn ngoài test.

Nếu một hệ thống cần đo latency ở p95/p99 hay microbenchmark, dùng đo đạc chuyên dụng và môi trường kiểm soát; `assertTimeout` dành cho correctness guard, không thể đại diện kết quả production.

## 12. Lỗi thường gặp và cách tránh

**1. Nhầm `assertTimeout` với cơ chế hủy tác vụ.** Nó chờ callback kết thúc rồi fail; tác vụ treo khiến test treo. Giới hạn thời gian của HTTP/DB cần đặt ở lớp client tương ứng.

**2. Nghĩ `assertTimeoutPreemptively` giết được thread.** Nó chỉ cố interrupt; tác vụ bỏ qua interrupt có thể tiếp tục chạy sau khi assertion đã fail. Tránh callback có side effect khó hoàn tác.

**3. Dùng preemptive trong Spring `@Transactional` test.** Callback ở worker không thừa hưởng test-managed transaction của thread gốc; ghi dữ liệu có thể commit ngoài rollback dự kiến. Ưu tiên cùng thread.

**4. Coi `@Timeout(SAME_THREAD)` giống hệt `assertTimeout`.** Cả hai giữ thread, nhưng annotation có cơ chế **interrupt khi quá hạn**, còn non-preemptive assertion kiểm sau khi callback hoàn thành.

**5. Bỏ trống thread mode rồi phỏng đoán.** `@Timeout` mặc định `INFERRED` và đọc cấu hình Jupiter. Chọn `SAME_THREAD` tường minh khi điều đó quan trọng cho Spring transaction.

**6. Lấy `@Timeout(100)` làm 100 ms.** Đơn vị mặc định của annotation là **giây**, không phải milli giây. Viết `unit = TimeUnit.MILLISECONDS` khi muốn 100 ms.

**7. Dùng `@Test(timeout = 1000)` của JUnit 4 trong Jupiter.** `org.junit.jupiter.api.Test` không có thuộc tính timeout. Dùng `@Timeout`, `assertTimeout` hoặc `assertTimeoutPreemptively`.

**8. Tưởng timeout của `@TestFactory` bao phủ mọi `DynamicTest`.** Nó chỉ áp dụng cho factory method. Giới hạn phần thực thi phải đặt ở từng dynamic test.

**9. Bắt `InterruptedException` rồi bỏ qua.** Thread có thể tiếp tục sau deadline, gây leak hoặc ghi dữ liệu ngoài ý muốn. Khi thật sự cần dừng có phối hợp, xử lý interruption đúng hợp đồng và cleanup.

**10. Đặt deadline sát thời gian thường thấy.** Phát sinh flaky trên CI. Chọn khoảng rộng có ý nghĩa hoặc xây test bằng thời gian ảo và synchronization deterministic.

**11. Nghĩ timeout nghĩa là rollback.** Timeout chỉ cho biết thời gian vượt ngưỡng; việc rollback, compensation, idempotency và cleanup thuộc về giao dịch/nghiệp vụ.

**12. Thiếu dấu hiệu thread trong chẩn đoán.** Nếu thấy lỗi transaction, context hoặc security chỉ xuất hiện khi đổi sang preemptive, kiểm xem callback chạy thread nào và ngữ cảnh nào được bind/propagate.

## 13. Quy trình chọn timeout khi viết bài test mới

Bắt đầu bằng câu hỏi “điều gì xảy ra nếu code vượt thời gian dự kiến?”:

1. **Chỉ cần báo rằng logic chậm?** Dùng `assertTimeout` (cùng thread, hoàn thành rồi đánh giá).
2. **Cần giới hạn toàn method?** Dùng `@Timeout`; với Spring context nhạy thread, chọn `SAME_THREAD` rõ ràng.
3. **Cần người gọi không đợi callback quá hạn?** Chỉ dùng `assertTimeoutPreemptively`/`SEPARATE_THREAD` khi callback an toàn với thread mới và interruption, không dựa vào thread-bound transaction, và side effect/cleanup được kiểm soát.
4. **Có thể chặn vô hạn trong I/O?** Bổ sung timeout của driver/protocol và cơ chế hủy phù hợp; test framework là lớp cảnh báo bổ sung.
5. **Cần xác nhận sau timeout không còn side effect?** Test cancellation, cleanup và trạng thái bền vững bằng integration test phù hợp; timeout assertion không tự cung cấp bằng chứng đó.
6. **Môi trường CI có dao động?** Đặt ngưỡng đủ rộng và quan sát thực tế; không khẳng định hiệu năng production từ test ngắn.

### Bảng tự kiểm trước khi commit

- [ ] Biết rõ timeout dùng `assertTimeout`, `assertTimeoutPreemptively` hay `@Timeout`.
- [ ] Biết đoạn code chạy **trên thread nào** và có cần context gắn thread không.
- [ ] Hiểu “vượt hạn” dẫn đến *kiểm sau hoàn tất* hay *cố interrupt*.
- [ ] Với Spring `@Transactional` test, tránh preemptive thread làm mất rollback.
- [ ] Không giả định `interrupt()` sẽ hủy mọi tác vụ và undo mọi side effect.
- [ ] Có timeout thực tế ở HTTP/DB/broker khi I/O có thể chặn.
- [ ] Ngưỡng timeout phù hợp CI; test không chỉ PASS nhờ may mắn scheduling.
- [ ] Có assertions về nghiệp vụ/trạng thái; timeout không phải assertion duy nhất nếu cần kiểm correctness.
- [ ] Tên test/`@DisplayName` mô tả mục đích, không chỉ viết “timeout test”.
- [ ] Có chiến lược cleanup/cancellation nếu test chạy bất đồng bộ hoặc có side effect ngoài tiến trình.

**Ghi nhớ:** `assertTimeout` giữ callback trong **cùng thread** và **chờ xong mới đánh giá**; `assertTimeoutPreemptively` đưa callback sang **thread khác** và **cố interrupt khi hết hạn**; `@Timeout` có thread mode riêng, trong đó `SAME_THREAD` vẫn có cơ chế interrupt. Trong Spring Boot, lựa chọn thread quyết định liệu transaction/context kiểm thử có còn áp dụng hay không.

### Tài liệu tham khảo chính thức

- [JUnit 5 User Guide – Assertions: Timeout](https://docs.junit.org/5.12.0/user-guide/#writing-tests-assertions): `assertTimeout`, `assertTimeoutPreemptively` và dạng trả kết quả.
- [JUnit 5 User Guide – Declarative Timeouts](https://docs.junit.org/5.12.0/user-guide/#writing-tests-declarative-timeouts): `@Timeout`, `ThreadMode` và cấu hình timeout.
- [JUnit Jupiter API – Assertions](https://junit.org/junit5/docs/5.12.0/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html): hợp đồng và lưu ý của hai assertion.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): cảnh báo preemptive timeout và `ThreadLocal` transaction trong Spring TestContext.
- [Gradle User Manual – Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): chạy JUnit Platform và báo cáo test.
