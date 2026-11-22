# Phát hiện lệnh chặn bằng BlockHound khi môi trường hỗ trợ

Trong Reactor, một pipeline có thể trông hoàn toàn reactive nhưng vẫn chứa lời gọi **blocking** như `Thread.sleep`, truy cập file đồng bộ, JDBC, hoặc chờ khóa. Nếu những lời gọi đó chạy trên event loop hay thread dành cho xử lý non-blocking, chúng có thể giữ thread quá lâu, làm tăng độ trễ, giảm throughput và khiến các request khác phải chờ.

**BlockHound** là công cụ instrumentation cho JVM, do dự án Reactor phát triển, giúp phát hiện một số lời gọi blocking trên các thread được đánh dấu **non-blocking only**. Khi bắt gặp một phương thức blocking được nhận diện trên thread loại này, BlockHound ném `reactor.blockhound.BlockingOperationError`. Đây là tín hiệu để sửa cách thiết kế scheduler hoặc thay API blocking bằng API reactive; không phải một cơ chế tự động chuyển code blocking thành non-blocking.

Đề bài nhấn mạnh **“khi môi trường hỗ trợ”** vì BlockHound cần khả năng Java agent/instrumentation của JVM. Một số JDK, native-image, sandbox, JVM hạn chế dynamic attach hoặc môi trường CI có thể không hỗ trợ cài agent. Trong trường hợp đó, vẫn kiểm thử pipeline bằng StepVerifier, VirtualTimeScheduler, kiểm thử timeout và benchmark; không tuyên bố BlockHound đã phát hiện blocking nếu instrumentation thực tế chưa cài được.

Bài này trình bày nguyên lý, giới hạn, cấu hình Gradle/JDK 17, bộ test Reactor có chế độ bật BlockHound có chủ đích, cách đọc lỗi, khắc phục blocking trong WebFlux và hướng xử lý môi trường không hỗ trợ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lệnh blocking, CPU-bound và non-blocking.
2. Hiểu vì sao event loop không nên chạy lời gọi chờ đồng bộ.
3. Biết BlockHound kiểm tra phương thức và thread như thế nào.
4. Phân biệt `Schedulers.parallel()`, `Schedulers.single()` và `Schedulers.boundedElastic()`.
5. Hiểu vai trò `NonBlocking` marker và `Schedulers.isInNonBlockingThread()`.
6. Cài BlockHound bằng `BlockHound.install()` tại thời điểm thích hợp.
7. Cấu hình JVM flag cần thiết cho JDK 13+ ở Gradle test.
8. Bật test BlockHound **chủ động**, không giả định mọi môi trường đều hỗ trợ.
9. Viết test dương tính kiểm tra `BlockingOperationError` bằng `StepVerifier`.
10. Viết test đối chứng cho tác vụ non-blocking và tác vụ blocking được cô lập trên boundedElastic.
11. Phân biệt lỗi `block()` do guard của Reactor với lỗi do BlockHound.
12. Tìm đúng vị trí blocking qua stack trace, không che lỗi bằng whitelist tùy tiện.
13. Dùng `markAsBlocking` hoặc `allowBlockingCallsInside` có kiểm soát.
14. Nhận biết false negative, false positive và tác động của instrumentation toàn JVM.
15. Thiết kế chiến lược CI và phương án thay thế khi không dùng được BlockHound.

## 2. Vì sao blocking gây nguy hiểm trong reactive pipeline?

Reactor sử dụng publisher, subscriber và các scheduler để thực thi công việc. Trong Spring WebFlux chạy trên Reactor Netty, một số lượng event-loop thread tương đối nhỏ quản lý rất nhiều kết nối. Mô hình này hoạt động hiệu quả khi callback chạy nhanh và không chặn thread.

Ví dụ một pipeline có vẻ đơn giản:

~~~java
Mono<String> result = Mono.just("hello")
    .map(value -> {
        Thread.sleep(500);
        return value.toUpperCase();
    });
~~~

Đoạn trên chỉ là mã minh họa, chưa biên dịch vì `Thread.sleep` cần xử lý `InterruptedException`. Nếu xử lý exception rồi chạy nó trong event loop, thread bị giữ ít nhất khoảng 500 ms. Nhiều request đồng thời sẽ phải chờ cùng worker thread.

### 2.1. Blocking và non-blocking

| Loại công việc | Ví dụ | Tác động |
| --- | --- | --- |
| Chờ blocking | `Thread.sleep`, JDBC đồng bộ, socket read đồng bộ | Thread đợi, không xử lý được task khác |
| CPU-bound | Tính toán phức tạp liên tục | Không nhất thiết blocking I/O, nhưng vẫn chiếm CPU và event loop |
| Non-blocking I/O | R2DBC, WebClient/Netty khi dùng đúng cách | Không giữ thread để chờ I/O |
| Reactive delay | `Mono.delay(Duration)` | Scheduler hẹn giờ, không gọi Thread.sleep trong callback |
| Legacy blocking được cô lập | `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` | Chuyển chờ blocking sang pool boundedElastic, nhưng không làm API trở thành non-blocking |

BlockHound chủ yếu kiểm tra **các phương thức blocking được biết hoặc đánh dấu** khi chạy trên thread non-blocking. Nó không đo tất cả độ trễ, không phát hiện tự động mọi vòng lặp CPU-bound và không thay thế profiler.

### 2.2. Event loop bị chặn

~~~text
Event-loop thread
  |
  +-- Request A: parse header       1 ms
  +-- Request B: blocking JDBC    500 ms  <-- giữ thread
  +-- Request C: handle response    ...   <-- phải chờ
  +-- Request D: handle response    ...   <-- phải chờ
~~~

Một lệnh blocking đơn lẻ có thể tạo head-of-line blocking cho các tác vụ dùng chung event loop. Khi hệ thống bận, độ trễ có thể tăng không tuyến tính.

### 2.3. Vì sao không dùng mọi nơi boundedElastic?

`boundedElastic` là giải pháp cầu nối khi chưa thể bỏ API blocking, nhưng vẫn có giới hạn số thread và queue. Nếu hàng nghìn request cùng gọi JDBC blocking, chuyển tất cả sang boundedElastic chưa chắc đủ để duy trì SLA. Cần giới hạn concurrency, timeout, pool tài nguyên và ưu tiên native reactive driver khi khả thi.

## 3. BlockHound hoạt động thế nào?

BlockHound dùng Byte Buddy/Java instrumentation để can thiệp vào các phương thức được xem là blocking. Khi phương thức đó được gọi, BlockHound kiểm tra thread hiện tại có thuộc nhóm non-blocking-only không. Nếu có, mặc định nó phát lỗi:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep
~~~

Tên method trong stack trace giúp tìm chỗ gọi blocking.

Có ba yếu tố cần đồng thời xảy ra:

1. **Agent đã cài thành công** và instrument được phương thức liên quan.
2. Phương thức được BlockHound nhận diện/đăng ký là blocking.
3. Lời gọi diễn ra trên **thread được đánh dấu non-blocking**.

Nếu một trong ba điều kiện không đáp ứng, BlockHound có thể không báo lỗi. Điều này không tự chứng minh code an toàn.

### 3.1. Marker NonBlocking

Reactor định nghĩa interface đánh dấu `reactor.core.scheduler.NonBlocking`. Nhiều worker thread của `Schedulers.parallel()` và `Schedulers.single()` triển khai marker này. BlockHound có tích hợp với Reactor để nhận diện những thread đó.

Có thể kiểm tra:

~~~java
boolean isNonBlocking =
    Schedulers.isInNonBlockingThread();
~~~

Giá trị phản ánh thread đang chạy tại thời điểm kiểm tra, không phải loại publisher khai báo trong biến Java.

### 3.2. Scheduler và khả năng phát hiện

| Scheduler/thread | Đặc trưng | Kết quả điển hình với Thread.sleep sau khi cài BlockHound |
| --- | --- | --- |
| `Schedulers.parallel()` | Worker non-blocking cho tác vụ ngắn/CPU | Bị phát hiện |
| `Schedulers.single()` | Worker non-blocking dùng chung | Bị phát hiện |
| Reactor Netty event loop | Network I/O non-blocking | Bị phát hiện trong điều kiện tích hợp tương thích |
| `Schedulers.boundedElastic()` | Dành cho legacy blocking có giới hạn | Không bị chặn theo chính sách non-blocking-thread mặc định |
| Main/JUnit test thread | Thường không được đánh dấu NonBlocking | Có thể không bị phát hiện |
| Custom ExecutorService | Tùy kiểu thread và predicate | Không giả định được phát hiện |
| Virtual thread | Phụ thuộc JDK/config và runtime | Cần kiểm thử tương thích riêng |

**Không viết một test `Thread.sleep(20)` trên main test thread rồi suy ra BlockHound không hoạt động khi không có lỗi.** Phải dùng `subscribeOn(Schedulers.parallel())` hoặc chuyển callback bằng `publishOn` để test đúng loại thread.

### 3.3. Cài agent trước khi chạy pipeline

Cách đơn giản:

~~~java
BlockHound.install();
~~~

Nên cài sớm khi khởi động process test/application, trước khi tạo nhiều scheduler và thực thi pipeline. Installation là tác động ở **cấp JVM**, không phải cài riêng cho một Mono. Không gọi install lại trong từng method @Test.

Theo BlockHound, các lần cài tiếp theo thường bị bỏ qua; không dựa vào việc cài lần hai để thay đổi allowlist. Nếu có nhiều module/test suite cần custom integration, thiết kế một điểm cài thống nhất.

### 3.4. Không phải kiểm tra ở compile time

BlockHound không đọc source code để cấm `Thread.sleep` ngay khi biên dịch. Nó phát hiện **lời gọi thực sự xảy ra** khi test chạy trên thread phù hợp. Đường code không được test sẽ không được quan sát.

## 4. Phiên bản, JVM flag và môi trường hỗ trợ

Ví dụ trong bài dùng:

- **Java 17** (HotSpot/OpenJDK có Java instrumentation hoạt động).
- **Reactor Core/Test 3.8.8**.
- **BlockHound 1.0.18.RELEASE**.
- **JUnit Jupiter 5.14.4**.
- **Gradle 8.x hoặc mới hơn** tương thích JDK và plugin đang dùng.

Các phiên bản này được chọn để có cặp Reactor Core/Test đồng bộ và dependency BlockHound đã phát hành. Dự án sử dụng version catalog hoặc BOM riêng phải giữ phiên bản Reactor cùng release train.

### 4.1. Yêu cầu JDK 13+

Tài liệu BlockHound hiện hướng dẫn thêm JVM flag sau trên JDK 13+:

~~~text
-XX:+AllowRedefinitionToAddDeleteMethods
~~~

Đây là workaround cho giới hạn JVM về redefinition native methods, không phải một flag tăng hiệu suất. Flag phải được cấp cho **JVM chạy test**, không chỉ cho Gradle daemon hoặc shell. Tùy JDK vendor/version, JVM có thể cảnh báo, bỏ hỗ trợ hoặc từ chối các cơ chế instrumentation khác.

Không áp dụng flag này một cách mù quáng cho mọi môi trường production. Chỉ dùng ở test JVM thực sự cần BlockHound, và xác minh startup instrumentation thành công.

### 4.2. Dynamic attach và native-image

Một số môi trường có thể từ chối Java agent attach/retransform:

- Container có quyền process attach bị giới hạn.
- JVM bật chính sách ngăn dynamic agent loading.
- Runtime native-image không có cơ chế Java instrumentation tương đương.
- JDK vendor/phiên bản không tương thích Byte Buddy agent đang dùng.
- Hệ thống an ninh hoặc test runner không cho gắn agent.
- Một số công cụ coverage/instrumentation khác xung đột.

Nếu `BlockHound.install()` ném exception, test phải báo trạng thái **không cài được**. Không được kết luận pipeline không có blocking chỉ vì không thấy `BlockingOperationError`.

### 4.3. Nguyên tắc “khi môi trường hỗ trợ”

Nên có hai lớp kiểm thử:

1. **Core Reactor tests**: chạy mọi nơi, không phụ thuộc instrumentation.
2. **BlockHound opt-in tests**: chỉ bật trên JVM/test runner đã xác nhận hỗ trợ; nếu bật mà cài thất bại thì báo test failure rõ ràng.

Không bỏ qua việc cài agent bằng `try/catch` rồi vẫn cho toàn bộ test BlockHound PASS. Điều đó tạo false sense of safety.

## 5. Cách kết hợp BlockHound với StepVerifier

`StepVerifier` kiểm tra tín hiệu của publisher: onNext, onComplete hoặc onError. Khi BlockHound ném `BlockingOperationError` trong một callback reactive, lỗi thường đi theo `onError` tới subscriber.

### 5.1. Pipeline vi phạm

~~~java
Mono<String> wrong = Mono.fromCallable(() -> {
    Thread.sleep(30);
    return "done";
})
.subscribeOn(Schedulers.parallel());
~~~

Snippet trên có `Thread.sleep` nên compiler cần xử lý InterruptedException nếu dùng làm chương trình thực tế. Mã đầy đủ ở phần 10 sẽ có helper xử lý exception.

Với BlockHound đã cài thành công, thao tác sleep trên worker của parallel scheduler thường dẫn tới `BlockingOperationError`. Test nên xác minh loại lỗi, không chỉ gọi `expectError()` vì một NullPointerException hoặc lỗi codec cũng có thể khiến expectError pass.

### 5.2. Test nhắm đúng lỗi

~~~java
StepVerifier.create(wrong)
    .expectErrorSatisfies(error -> {
        assertTrue(isBlockingOperationError(error));
    })
    .verify(Duration.ofSeconds(5));
~~~

`isBlockingOperationError` là helper của test để duyệt cause chain. Nó giúp tránh phụ thuộc việc một operator bọc lỗi hay không. Phải kiểm tra nguyên nhân là BlockHound, không chấp nhận bất kỳ exception nào.

### 5.3. Test đối chứng

Có hai đối chứng hữu ích:

- Logic non-blocking trên parallel phải hoàn tất.
- Logic blocking được cô lập trên boundedElastic có thể hoàn tất mà BlockHound không báo lỗi trên non-blocking thread.

Điều này chứng minh công cụ đang phân biệt môi trường thực thi; không chứng minh boundedElastic có throughput vô hạn hoặc legacy code đủ an toàn để dùng dưới tải lớn.

## 6. subscribeOn và publishOn quyết định vị trí blocking

Một lỗi phổ biến là chuyển scheduler ở vị trí sai.

### 6.1. subscribeOn chuyển công việc nguồn

~~~java
Mono<String> result = Mono.fromCallable(
        () -> legacyBlockingCall()
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` đặt việc subscribe/source execution lên scheduler được chọn. Đây là mẫu quen thuộc để cô lập một API blocking hiện có.

Nếu thay `boundedElastic` bằng `parallel`, BlockHound có thể báo lỗi khi source gọi Thread.sleep hoặc I/O blocking.

### 6.2. publishOn ảnh hưởng operator phía sau

~~~java
Mono<String> result = Mono.just("hello")
    .publishOn(Schedulers.parallel())
    .map(value -> legacyBlockingCall());
~~~

Với vị trí trên, `map` chạy sau publishOn trên worker của parallel scheduler, nên thao tác blocking bị phát hiện.

Trong trường hợp khác:

~~~java
Mono<String> result = Mono.fromCallable(
        () -> legacyBlockingCall()
    )
    .publishOn(Schedulers.parallel());
~~~

`publishOn` nằm **sau** source nên không làm callable phía trước chạy trên parallel. Đừng dùng trường hợp này để chứng minh BlockHound hỏng khi nó không báo lỗi.

### 6.3. Ghép hai scheduler trong một flow

~~~java
Mono<String> flow = Mono.fromCallable(
        () -> legacyBlockingCall()
    )
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(String::trim);
~~~

Source blocking chạy trên boundedElastic. Sau `publishOn`, bước biến đổi nhẹ chạy trên parallel. Khi bảo trì code, nhớ rằng thêm một lời gọi blocking **sau** publishOn có thể tái tạo vi phạm.

## 7. BlockHound khác cơ chế cấm block() có sẵn của Reactor

Reactor có kiểm tra riêng với các API chờ đồng bộ như:

~~~java
Mono.just("value").block();
~~~

Khi `block()` chạy trên một Reactor thread được đánh dấu NonBlocking (ví dụ parallel), Reactor có thể ném:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread ...
~~~

Lỗi này có thể xuất hiện **ngay cả khi chưa cài BlockHound**.

Ngược lại, `BlockingOperationError: Blocking call! java.lang.Thread.sleep` là tín hiệu của BlockHound instrumentation. Vì thế không dùng `Mono.block()` như bài test duy nhất để xác minh BlockHound đã cài thành công.

### 7.1. StepVerifier.verify() có blocking không?

`StepVerifier.verify()` chờ kết quả test và có thể block **JUnit test thread**, thường không phải event loop. Đây là cách kiểm thử bình thường. Không gọi StepVerifier.verify() bên trong map/flatMap hoặc callback chạy trên Reactor non-blocking thread.

### 7.2. withVirtualTime có phát hiện Thread.sleep không?

`StepVerifier.withVirtualTime` điều khiển thời gian của các scheduler ảo cho operator như delay, interval, timeout. Nó **không làm Thread.sleep biến thành non-blocking**, cũng không thay thế BlockHound. Dùng virtual time cho logic dựa vào thời gian và dùng BlockHound để quan sát vi phạm blocking khi agent hoạt động.

## 8. Tình huống thường gặp trong Spring WebFlux

### 8.1. JDBC đồng bộ trong controller

Một handler kiểu sau nguy hiểm nếu chạy trực tiếp trên event loop:

~~~java
@GetMapping("/customers/{id}")
Mono<Customer> get(@PathVariable String id) {
    Customer customer = jdbcRepository.findById(id);
    return Mono.just(customer);
}
~~~

Đây là đoạn minh họa, giả định `jdbcRepository` và `Customer` của ứng dụng đã tồn tại. Lời gọi JDBC được thực thi **trước khi** method trả Mono; wrapping kết quả trong Mono.just không làm JDBC non-blocking.

### 8.2. Cô lập legacy JDBC nếu chưa thể thay

~~~java
@GetMapping("/customers/{id}")
Mono<Customer> get(@PathVariable String id) {
    return Mono.fromCallable(
        () -> jdbcRepository.findById(id)
    )
    .subscribeOn(Schedulers.boundedElastic());
}
~~~

Cách này dời việc blocking sang boundedElastic. Vẫn cần giới hạn concurrency, JDBC pool, timeout, cancellation semantics và kiểm soát overload. Bản sửa dài hạn có thể là dùng R2DBC, reactive HTTP client hoặc adapter bất đồng bộ thật sự, nếu đáp ứng yêu cầu nghiệp vụ.

### 8.3. Thread.sleep để “đợi một chút”

Không dùng:

~~~java
Mono.just("x")
    .map(value -> {
        sleepForOneSecond();
        return value;
    });
~~~

Nếu muốn delay không chặn thread:

~~~java
Mono<String> delayed = Mono.just("x")
    .delayElement(Duration.ofSeconds(1));
~~~

Hoặc:

~~~java
Mono<String> delayed =
    Mono.delay(Duration.ofSeconds(1))
        .thenReturn("x");
~~~

`delayElement` và `Mono.delay` dùng scheduler hẹn giờ thay vì chặn thread bằng Thread.sleep.

### 8.4. File I/O và HTTP client đồng bộ

`Files.readAllBytes`, `InputStream.read`, legacy Apache HttpClient đồng bộ hoặc các SDK bên thứ ba có thể block. Đừng giả định mọi method I/O đều được BlockHound instrument; việc có hoặc không có lỗi còn tùy phương thức, JVM và tích hợp của library.

Với API chỉ có dạng đồng bộ, có thể cô lập:

~~~java
Mono<byte[]> content = Mono.fromCallable(
        () -> Files.readAllBytes(path)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là snippet tích hợp, giả định biến `path` là `java.nio.file.Path`. Với file lớn, `readAllBytes` còn có rủi ro dùng nhiều heap; ưu tiên streaming, giới hạn kích thước hoặc cơ chế I/O phù hợp.

### 8.5. Logging và SDK bên thứ ba

Một logging appender đồng bộ, driver, DNS resolver hoặc SDK không tương thích có thể block trong callback tưởng như nhẹ. Khi BlockHound báo lỗi, xem cả stack trace của thư viện. Không vội thêm allowlist cho toàn bộ package.

## 9. Tạo test tùy chọn: chạy bình thường và bật BlockHound có chủ đích

Ví dụ dùng một dự án **Reactor thuần Java 17**. Không cần Spring Boot server; đây là bài học về kiểm thử Reactor và scheduler, nên bộ test tập trung trực tiếp vào publisher.

Cấu trúc:

~~~text
reactor-blockhound-lab/
├── build.gradle
└── src/
    ├── main/java/demo/BlockingExamples.java
    └── test/java/demo/
        ├── ReactorSchedulerTest.java
        └── BlockHoundOptionalTest.java
~~~

### 9.1. build.gradle

~~~groovy
plugins {
    id 'java'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'

    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.14.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.14.4'

    testImplementation 'io.projectreactor.tools:blockhound:1.0.18.RELEASE'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    String optIn = providers.gradleProperty('blockhound')
        .orElse('false')
        .get()

    systemProperty 'test.blockhound', optIn

    if (optIn == 'true') {
        jvmArgs '-XX:+AllowRedefinitionToAddDeleteMethods'
        maxParallelForks = 1
    }
}
~~~

Giải thích:

- Dependency BlockHound chỉ nằm trong test classpath, không mặc nhiên đưa agent vào runtime production.
- `test.blockhound` có giá trị `false` khi chạy test thông thường.
- Chỉ khi chạy `-Pblockhound=true`, JUnit mới kích hoạt test dùng instrumentation.
- Flag JDK 13+ được cấp cho **test JVM** trong nhánh opt-in.
- `maxParallelForks = 1` tránh nhiều test JVM cùng khởi động không cần thiết cho ví dụ; mỗi JVM vẫn có trạng thái instrumentation riêng.
- Các test lõi vẫn chạy khi BlockHound bị tắt.

Không yêu cầu môi trường không hỗ trợ phải tự động bỏ qua một lỗi cài agent đã xảy ra. **Nếu bật opt-in mà BlockHound.install() thất bại, Gradle test nên thất bại rõ ràng.**

### 9.2. BlockingExamples.java

~~~java
package demo;

import java.util.Locale;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class BlockingExamples {

    private BlockingExamples() {
    }

    public static String legacyWait(String input) {
        try {
            Thread.sleep(25);
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Legacy operation interrupted", ex
            );
        }

        return input.toUpperCase(Locale.ROOT);
    }

    public static Mono<String> wrongOnParallel(String value) {
        return Mono.fromCallable(
                () -> legacyWait(value)
            )
            .subscribeOn(Schedulers.parallel());
    }

    public static Mono<String> isolatedOnBoundedElastic(String value) {
        return Mono.fromCallable(
                () -> legacyWait(value)
            )
            .subscribeOn(Schedulers.boundedElastic());
    }

    public static Mono<String> nonBlockingTransform(String value) {
        return Mono.just(value)
            .publishOn(Schedulers.parallel())
            .map(s -> s.toUpperCase(Locale.ROOT));
    }

    public static Mono<String> wrongAfterPublishOn(String value) {
        return Mono.just(value)
            .publishOn(Schedulers.parallel())
            .map(BlockingExamples::legacyWait);
    }

    public static Mono<Boolean> onParallelNonBlockingThread() {
        return Mono.fromSupplier(
                Schedulers::isInNonBlockingThread
            )
            .subscribeOn(Schedulers.parallel());
    }

    public static Mono<Boolean> onBoundedElasticNonBlockingThread() {
        return Mono.fromSupplier(
                Schedulers::isInNonBlockingThread
            )
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Ở đây:

- `legacyWait` mô phỏng API đồng bộ; xử lý InterruptedException đúng cách.
- `wrongOnParallel` đưa blocking operation lên parallel worker: BlockHound phải phát hiện khi agent hoạt động.
- `isolatedOnBoundedElastic` chạy cùng operation trên scheduler dành cho legacy blocking.
- `nonBlockingTransform` chỉ uppercase String, không có chờ đồng bộ.
- `wrongAfterPublishOn` giúp kiểm tra vị trí operator nằm sau publishOn.
- Hai method cuối kiểm tra thread classification của Reactor.

### 9.3. ReactorSchedulerTest.java — luôn chạy

~~~java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

final class ReactorSchedulerTest {

    @Test
    void nonBlockingTransformCompletes() {
        StepVerifier.create(
            BlockingExamples.nonBlockingTransform("alpha")
        )
        .expectNext("ALPHA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void boundedElasticCanRunLegacyBlockingCall() {
        StepVerifier.create(
            BlockingExamples.isolatedOnBoundedElastic("beta")
        )
        .expectNext("BETA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void parallelWorkersAreMarkedNonBlocking() {
        StepVerifier.create(
            BlockingExamples.onParallelNonBlockingThread()
        )
        .expectNext(true)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void boundedElasticWorkersAreNotMarkedNonBlocking() {
        StepVerifier.create(
            BlockingExamples.onBoundedElasticNonBlockingThread()
        )
        .expectNext(false)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

Bốn test này không gọi BlockHound.install(). Chúng kiểm tra scheduler classification và giá trị output cơ bản, vì thế vẫn chạy khi agent instrumentation không khả dụng.

### 9.4. BlockHoundOptionalTest.java — chỉ chạy khi bật opt-in

~~~java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@EnabledIfSystemProperty(
    named = "test.blockhound",
    matches = "true"
)
final class BlockHoundOptionalTest {

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }

    private static boolean containsBlockHoundError(
            Throwable error) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {

            if (current instanceof BlockingOperationError) {
                return true;
            }
        }

        return false;
    }

    @Test
    void detectsSleepOnParallelScheduler() {
        StepVerifier.create(
            BlockingExamples.wrongOnParallel("alpha")
        )
        .expectErrorSatisfies(error ->
            assertTrue(
                containsBlockHoundError(error),
                () -> "Unexpected error: " + error
            )
        )
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void detectsSleepAfterPublishOn() {
        StepVerifier.create(
            BlockingExamples.wrongAfterPublishOn("beta")
        )
        .expectErrorSatisfies(error ->
            assertTrue(
                containsBlockHoundError(error),
                () -> "Unexpected error: " + error
            )
        )
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void legacyBlockingOnBoundedElasticStillCompletes() {
        StepVerifier.create(
            BlockingExamples.isolatedOnBoundedElastic("gamma")
        )
        .expectNext("GAMMA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }

    @Test
    void pureTransformOnParallelCompletes() {
        StepVerifier.create(
            BlockingExamples.nonBlockingTransform("delta")
        )
        .expectNext("DELTA")
        .expectComplete()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

**Vì sao dùng `@EnabledIfSystemProperty`?**

JUnit chỉ chạy lớp test khi `test.blockhound=true`. Khi chưa bật, các test của lớp này hiển thị **skipped**, không phải passed. Đây là trạng thái đúng với môi trường không chạy instrumentation. Nếu đã bật nhưng `BlockHound.install()` thất bại, @BeforeAll làm test fail và báo nguyên nhân thay vì nuốt lỗi.

**Vì sao không dùng `expectError()`?** Vì cần chứng minh lỗi đến từ BlockHound, không phải từ logic ứng dụng hoặc lỗi dependency. Helper duyệt cause chain giúp test rõ mục đích hơn.

### 9.5. Chạy test bình thường

Nếu dự án có Gradle wrapper:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Nếu không có wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng:** `ReactorSchedulerTest` chạy và pass; `BlockHoundOptionalTest` bị skip do chưa bật. Điều này **không có nghĩa** BlockHound đã xác nhận toàn bộ code không blocking.

### 9.6. Bật BlockHound trên môi trường được hỗ trợ

Với Gradle wrapper:

~~~bash
./gradlew test -Pblockhound=true --rerun-tasks
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test -Pblockhound=true --rerun-tasks
~~~

Với Gradle cài sẵn:

~~~bash
gradle test -Pblockhound=true --rerun-tasks
~~~

Khi JVM 17/agent tương thích:

- Gradle truyền `-XX:+AllowRedefinitionToAddDeleteMethods` tới test JVM.
- JUnit bật `BlockHoundOptionalTest`.
- @BeforeAll cài BlockHound một lần.
- Hai test `detectsSleep...` nhận lỗi `BlockingOperationError` và **test PASS vì đã kỳ vọng chính xác lỗi đó**.
- Hai test đối chứng hoàn tất bình thường.
- Test class thông thường cũng tiếp tục chạy.

Nếu agent không cài được, test phải FAIL với lỗi cài agent. Khi đó chỉ dùng `-Pblockhound=true` trên runner có hỗ trợ; runner khác tiếp tục chạy baseline tests không dùng agent.

### 9.7. Không dùng sleep thật cho test thời gian chung

`Thread.sleep(25)` trong ví dụ chỉ làm **mẫu vi phạm blocking** có thể quan sát bằng BlockHound. Nó không phải phương án tốt để kiểm thử timer/operator theo thời gian. Với nghiệp vụ có delay/timeout, nên dùng StepVerifier.withVirtualTime và scheduler ảo thích hợp thay vì sleep nhiều giây làm test chậm.

## 10. Phân tích stack trace của BlockingOperationError

Ví dụ lỗi khi BlockHound phát hiện:

~~~text
reactor.blockhound.BlockingOperationError:
Blocking call! java.lang.Thread.sleep
    at java.base/java.lang.Thread.sleep(...)
    at demo.BlockingExamples.legacyWait(BlockingExamples.java:...)
    at demo.BlockingExamples.lambda$wrongOnParallel$0(...)
    at reactor.core.publisher.MonoCallable.call(...)
    ...
~~~

Số dòng và frame cụ thể phụ thuộc Java/compiler/Reactor version. Đọc từ trên xuống:

1. `BlockingOperationError` cho biết detector đã kích hoạt.
2. `java.lang.Thread.sleep` là blocking method bị chặn.
3. `demo.BlockingExamples.legacyWait` là điểm bắt đầu trong code ứng dụng.
4. Reactor stack frames cho biết callback/operator gọi đến helper đó.

Khi báo lỗi ở thư viện bên thứ ba, tìm call site đầu tiên thuộc code ứng dụng để xác định đường gọi. Không nên chỉ xóa dòng top frame hoặc thêm whitelist ngay mà chưa hiểu vì sao code chạy trên non-blocking thread.

### 10.1. Phân biệt root cause và wrapper

Một số operator có thể wrap exception. Khi đó StepVerifier có thể thấy một Throwable với `BlockingOperationError` nằm trong `getCause()`. Helper `containsBlockHoundError` ở ví dụ test hỗ trợ trường hợp này.

Tránh viết matcher chỉ dựa vào một chuỗi message có thể đổi theo version. Ưu tiên type `BlockingOperationError` và thông tin call site từ stack trace.

## 11. Tùy biến BlockHound và tránh lạm dụng allowlist

BlockHound có builder API để bổ sung blocking methods, điều chỉnh vùng cho phép blocking, hoặc tích hợp framework.

### 11.1. Mark method ứng dụng là blocking

Giả sử một thư viện nội bộ có method:

~~~java
public String load(String key) {
    // Trong thực tế gọi I/O đồng bộ
    return "value";
}
~~~

Đây là đoạn minh họa, không phải class chạy độc lập. Nếu biết chắc method này là blocking nhưng BlockHound chưa nhận diện, có thể đánh dấu bằng JVM descriptor:

~~~java
BlockHound.install(builder ->
    builder.markAsBlocking(
        "com.example.LegacyStore",
        "load",
        "(Ljava/lang/String;)Ljava/lang/String;"
    )
);
~~~

Descriptor `(Ljava/lang/String;)Ljava/lang/String;` nghĩa là method nhận một String và trả String. Phải đúng tên class và method signature. Nếu signature sai, detector có thể không instrument được method mong muốn.

### 11.2. Cấu hình allowBlockingCallsInside

Một số thư viện có đoạn bootstrap được đánh giá là chấp nhận chờ đồng bộ trong ngữ cảnh đặc biệt. Khi có bằng chứng rõ, BlockHound hỗ trợ:

~~~java
BlockHound.install(builder ->
    builder.allowBlockingCallsInside(
        "com.example.SafeBootstrap",
        "initialize"
    )
);
~~~

Đây là cấu hình ngoại lệ **có rủi ro**: nó bỏ qua kiểm tra blocking khi lời gọi nằm trong vùng đã cho phép. Không biến phương thức thành non-blocking và không bảo đảm an toàn nếu nó bị gọi từ event loop thực tế.

### 11.3. Dùng tích hợp mặc định của Reactor

`BlockHound.install()` tải các `BlockHoundIntegration` có sẵn qua ServiceLoader, trong đó có tích hợp Reactor phù hợp phiên bản. Khi viết tùy biến, ưu tiên overload `BlockHound.install(integrations...)` để giữ các tích hợp mặc định.

Cẩn thận với `BlockHound.builder().install()`: tạo builder trực tiếp không mặc nhiên tự tải tích hợp SPI như `BlockHound.install()`; có thể mất rule xác định Reactor NonBlocking threads nếu không cấu hình đầy đủ.

### 11.4. Whitelist có giới hạn

Nếu thật sự cần ngoại lệ:

- Nêu lý do vì sao blocking tại vị trí đó là chấp nhận được.
- Giới hạn vào một method cụ thể, không whitelist toàn bộ namespace.
- Thêm test chứng minh các vị trí khác vẫn bị bắt lỗi.
- Đặt issue/tiêu chí gỡ ngoại lệ khi thay API blocking.
- Không dùng allowlist để che một lỗi mới phát sinh trong controller production.

### 11.5. Install một lần và global side effect

BlockHound instrumentation có phạm vi process/JVM. Một test cấu hình allowlist có thể ảnh hưởng test khác trong cùng fork. Vì vậy:

1. Có một điểm cài agent trước tất cả BlockHound tests.
2. Tránh tạo nhiều test class tự gọi install với cấu hình khác nhau.
3. Không cho test suite điều chỉnh global rule trong lúc các test khác đang chạy song song.
4. Khi cần so sánh chính sách khác nhau, tách thành JVM/test task riêng.

## 12. Những gì BlockHound phát hiện và không phát hiện

| Tình huống | Kết quả điển hình | Giải thích |
| --- | --- | --- |
| Thread.sleep trên parallel sau install | BlockingOperationError | Method được instrument và thread NonBlocking |
| Thread.sleep trên boundedElastic | Không bị BlockHound chặn | Scheduler dành cho blocking bridge |
| Thread.sleep trên JUnit main thread | Thường không bị chặn | Thread không đánh dấu NonBlocking |
| Mono.block trên parallel | Có thể IllegalStateException của Reactor | Không nhất thiết nhờ BlockHound |
| Loop tính toán CPU 100% | Có thể không báo | Không phải lời gọi blocking được instrument |
| Native/SDK I/O chưa được đăng ký | Có thể không báo | BlockHound không nhận diện mọi blocking API |
| Code path không chạy khi test | Không báo | Detector là runtime |
| Cài agent thất bại | Không có bảo đảm phát hiện | Instrumentation chưa hoạt động |
| Virtual thread/custom scheduler | Phụ thuộc thread marker/configuration | Cần xác minh môi trường |
| Tác vụ thực thi tốt trên boundedElastic | Test có thể pass | Không bảo đảm tài nguyên dưới tải |

### 12.1. False negative

Một test không báo lỗi có thể do:
- Pipeline không chạy nhánh blocking.
- Thread không được đánh dấu NonBlocking.
- BlockHound chưa cài hoặc cài lỗi.
- Blocking method chưa được BlockHound nhận diện.
- Custom scheduler không tích hợp thread predicate.
- Instrumentation không hoạt động trên JDK/runtime đó.

Để kiểm tra detector, hãy giữ một test kiểm soát **cố ý gọi Thread.sleep trên parallel** và xác nhận BlockHound phát `BlockingOperationError` khi bật.

### 12.2. False positive hoặc lỗi thực nhưng không nguy hiểm trong ngữ cảnh

Một số thao tác khởi tạo framework/logging có thể bị đánh dấu blocking trong khi diễn ra ở pha mà nhóm phát triển đã đánh giá chấp nhận được. Hãy xem execution context và thứ tự khởi động trước khi cho ngoại lệ.

Đặc biệt, thay đổi classloader/instrumentation do bytecode agent khác có thể tạo lỗi lạ. Đừng coi mọi lỗi liên quan instrumentation là một vi phạm business code.

### 12.3. Không dùng BlockHound làm chứng chỉ performance

BlockHound có thể phát hiện một loại antipattern, nhưng không cho biết:
- p95/p99 latency production.
- Mức CPU saturation.
- Số connection đang giữ.
- Tốc độ xử lý thực tế của database.
- Memory/queue growth khi backpressure.
- Lỗi timeout hoặc deadlock trong mọi tình huống.

Vẫn cần metrics, profiling, load test, thread dump và tracing.

## 13. Khi môi trường không hỗ trợ BlockHound

Nếu BlockHound không hoạt động trong một JVM nhất định, **không cần bỏ cả chiến lược kiểm thử Reactor**.

### 13.1. Chạy baseline StepVerifier

Dùng StepVerifier để kiểm tra:
- onNext/onComplete/onError.
- Thứ tự item.
- Error recovery, retry và cancellation.
- Timeout và backpressure theo demand.
- Tài nguyên được cleanup khi subscribe/cancel.

Các test đó có thể chạy trên JVM không hỗ trợ agent.

### 13.2. Test concurrency và responsiveness

Dùng kiểm thử tích hợp WebFlux để xem một request chậm có kéo latency request độc lập tăng lên không, nhưng cần môi trường và warm-up ổn định để tránh kết luận sai từ timing ngẫu nhiên.

Có thể đo `Schedulers.isInNonBlockingThread()` tại call site cần quan sát để nhận biết blocking code có nguy cơ chạy trên event loop. Đây là chỉ báo thread classification, không phải detector tự động cho mọi blocking method.

### 13.3. Static analysis và code review

Tìm các pattern rủi ro trong reactive callbacks:
- `Thread.sleep`.
- `Future.get`/`CountDownLatch.await`.
- `InputStream.read`/`Files.readAllBytes`.
- JDBC/JPA synchronous repository.
- `block()`, `blockFirst()`, `blockLast()`.
- `toIterable()` và các phép chuyển thành synchronous consumer.
- Network client SDK đồng bộ.
- Lock/condition có khả năng chờ lâu.

Phân tích tĩnh có thể bỏ sót blocking thông qua thư viện hoặc callback gián tiếp, nhưng bổ sung giá trị khi agent không chạy được.

### 13.4. Load test và thread dump

Theo dõi event-loop utilization, p95/p99 latency, blocked/waiting thread states và stack trace. Nếu các event-loop thread thường xuyên nằm trong JDBC/Thread.sleep/file read, đây là dấu hiệu cần sửa ngay cả khi không có BlockHound.

### 13.5. Cách báo cáo test trung thực

| Điều kiện | Báo cáo đúng |
| --- | --- |
| Test BlockHound đã bật, agent cài được, positive probe phát đúng lỗi | BlockHound detection verified |
| Test BlockHound không bật | SKIPPED / not executed |
| Agent không hỗ trợ, test không bật | Not available on runner |
| Agent đã bật nhưng cài thất bại | FAILED / setup failure |
| Không phát hiện lỗi trong những case đã chạy | No detected violation in tested paths only |

Không ghi “BlockHound PASS” cho runner chỉ chạy baseline Reactor tests.

## 14. Tích hợp vào CI có chủ đích

Một chiến lược CI thực tế:

~~~text
Build/CI
  |
  +--> Unit + StepVerifier baseline (mọi runner)
  |
  +--> Supported JVM job (opt-in)
  |       |
  |       +--> Java 17 + JVM native-method flag
  |       +--> -Pblockhound=true
  |       +--> instrumentation setup
  |       +--> positive detection probe
  |       +--> regression tests
  |
  +--> API integration tests
  |
  +--> Performance/latency and resource metrics
~~~

### 14.1. Chọn một runner được kiểm chứng

Bắt đầu với Java 17 HotSpot/OpenJDK trên runner có attach instrumentation hoạt động. Kiểm tra version của Byte Buddy/BlockHound nếu nâng JDK. Đừng chuyển tất cả CI job lên JDK mới rồi mặc định dynamic agent vẫn hoạt động.

### 14.2. Opt-in và fail-fast

- Runner chưa được xác nhận hỗ trợ: chạy `gradle test`, BlockHound class được skip minh bạch.
- Runner đã xác nhận hỗ trợ: chạy `gradle test -Pblockhound=true`.
- Khi cài agent thất bại trên runner đã opt-in: fail job và kiểm tra JVM flags/runtime; không swallow exception.
- Sau khi nâng JDK hoặc BlockHound version: chạy positive probe trước khi tin kết quả kiểm thử.

### 14.3. Không biến skip thành “thành công” về chất lượng

CI dashboard nên hiển thị ít nhất số test executed/skipped và tên job có agent. Test được đánh dấu skipped không cung cấp bằng chứng đã phát hiện blocking. Khi yêu cầu BlockHound là một quality gate bắt buộc, cấu hình job riêng trên runner tương thích và coi lỗi cài agent là blocker.

### 14.4. Tách test có tính toàn JVM

BlockHound instrumentation không có uninstall thông dụng giữa các test. Nếu chạy nhiều test chung fork, cẩn thận với global Schedulers hooks, parallel JUnit execution và mocking agents. Có thể tách một Gradle test task/JVM riêng nếu bộ test lớn yêu cầu isolation.

## 15. Troubleshooting

### 15.1. BlockHound báo thiếu JVM flag

Triệu chứng:

~~~text
It looks like you're running on JDK 13+.
You need to add '-XX:+AllowRedefinitionToAddDeleteMethods' JVM flag.
~~~

Khắc phục: đặt flag ở `tasks.named('test', Test) { jvmArgs ... }` hoặc cấu hình Surefire/Failsafe test JVM tương ứng. Chạy lại opt-in test. Không chỉ đặt biến môi trường rồi giả định mọi fork nhận được flag.

### 15.2. Không thể self-attach/agent load

Triệu chứng có thể là `IllegalStateException`, lỗi Byte Buddy attach, agent loading restrictions hoặc một JVM exception trước khi test body chạy.

Kiểm tra JDK vendor, container security policy, JVM dynamic attach setting, phiên bản Byte Buddy/BlockHound và công cụ coverage khác. Nếu JVM hiện tại không hỗ trợ, chạy BlockHound trên runner tương thích và tiếp tục baseline tests trên runner đó.

### 15.3. Có BlockHound nhưng test không báo lỗi

Kiểm tra:
1. `BlockHound.install()` đã thực thi thành công chưa?
2. Lớp test có bị `@EnabledIfSystemProperty` skip không?
3. Request/publisher đã được subscribe chưa?
4. Blocking call có chạy trên Schedulers.parallel/single hoặc event loop không?
5. Có vô tình đặt source trên boundedElastic hoặc JUnit thread không?
6. Method có thuộc bộ phương thức được instrument không?
7. Có allowlist hoặc integration khác đã bỏ qua lời gọi không?

Test kiểm soát `Thread.sleep` trên parallel là cách kiểm tra nền tảng tốt hơn việc suy đoán từ một pipeline phức tạp.

### 15.4. Lỗi Reactor block() không phải BlockingOperationError

Nếu exception là `IllegalStateException` với thông điệp `block() ... not supported in thread`, đó có thể là guard của Reactor. Dù nguyên nhân cũng là blocking không đúng scheduler, đừng trình bày nó như bằng chứng BlockHound đã cài thành công.

### 15.5. Lỗi chỉ xuất hiện sau khi thêm BlockHound

Xem stack trace và tìm nơi gọi I/O chặn. Nếu trong code của bạn, sửa bằng reactive API hoặc cô lập boundedElastic. Nếu trong framework bootstrap/logging, xác minh lifecycle và version compatibility rồi mới cân nhắc allowlist hẹp. Không tắt toàn bộ detector chỉ vì một lỗi mới.

### 15.6. JVM warning về dynamic agent

JDK mới có thể cảnh báo dynamic loading sẽ bị hạn chế. Không suy ra test đã fail chỉ từ warning; xem setup có thành công và positive probe có phát `BlockingOperationError` hay không. Với chính sách JVM không cho agent, không cố bypass quy định môi trường; chọn runner khác cho test agent.

### 15.7. Kiểm thử ngẫu nhiên fail vì scheduler timing

Để test ổn định:
- Không kỳ vọng số millisecond chính xác.
- Dùng StepVerifier timeout đủ thoáng (ví dụ 5 giây).
- Không phụ thuộc thứ tự giữa các scheduler worker không có contract.
- Tránh dùng Thread.sleep để “đợi scheduler khởi động”.
- Không gọi hàng nghìn blocking task trong unit test.
- Để test kiểm tra hành vi thay vì hiệu suất.

## 16. Bài tập thực hành

### Bài 1: Phát hiện lỗi sau publishOn

Chạy `BlockHoundOptionalTest.detectsSleepAfterPublishOn` với `-Pblockhound=true` trên JVM hỗ trợ. Giải thích vì sao `map` gọi `legacyWait` chạy trên parallel worker.

**Đáp án:** `publishOn(Schedulers.parallel())` chuyển execution context cho các operator phía sau nó. Do đó `legacyWait` chạy trên non-blocking thread, và Thread.sleep bị BlockHound chặn.

### Bài 2: Sửa nguồn blocking

Thay:

~~~java
Mono.fromCallable(() -> BlockingExamples.legacyWait("abc"))
    .subscribeOn(Schedulers.parallel());
~~~

Bằng:

~~~java
Mono.fromCallable(() -> BlockingExamples.legacyWait("abc"))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Giải thích đây chỉ là cô lập blocking trên scheduler phù hợp, không biến Thread.sleep thành non-blocking. Nếu nhu cầu là delay, thay bằng `Mono.delay`/`delayElement`.

### Bài 3: Thêm kiểm thử non-blocking

Tạo Mono uppercase không gọi API blocking, chạy trên parallel và assert completion. Đây là đối chứng cho positive detection probe.

### Bài 4: Giả lập môi trường không hỗ trợ

Chạy `gradle test` không có `-Pblockhound=true`. Quan sát test class BlockHound được skip. Bảo đảm báo cáo QA không viết “BlockHound detected no blocking” chỉ vì lớp test bị bỏ qua.

### Bài 5: Thêm quy tắc cho legacy method

Với method `com.example.LegacyStore.load(String)`, cân nhắc markAsBlocking bằng descriptor chính xác; tạo test dương tính trên parallel và test đối chứng trên boundedElastic. Không cho phép ngoại lệ rộng nếu chưa đánh giá tác động.

## 17. Checklist review code và CI

1. **Environment:** test JVM có hỗ trợ Java instrumentation và Byte Buddy agent không?
2. **Flag:** JDK 13+ đã cấp `-XX:+AllowRedefinitionToAddDeleteMethods` cho test JVM chưa?
3. **Version:** Reactor Core/Test và BlockHound phiên bản tương thích chưa?
4. **Install:** `BlockHound.install()` chạy một lần đủ sớm chưa?
5. **Marker:** positive probe có chạy trên non-blocking thread chưa?
6. **Detection:** test kiểm tra `BlockingOperationError` thay vì bất kỳ exception nào chưa?
7. **Negative control:** logic non-blocking trên parallel hoàn tất chưa?
8. **Legacy control:** blocking bridge trên boundedElastic hoạt động và được giới hạn chưa?
9. **Scheduler placement:** `subscribeOn`/`publishOn` đặt đúng chỗ chưa?
10. **API:** có thể thay blocking API bằng reactive API thật sự không?
11. **Scope:** có code path quan trọng nào chưa được chạy trong tests không?
12. **Exceptions:** có whitelist quá rộng che blocking thật không?
13. **Global state:** test class có cố gắng install/đổi rule nhiều lần trong cùng JVM không?
14. **CI opt-in:** runner không hỗ trợ được báo SKIPPED, còn runner đã bật nhưng fail được báo FAILED không?
15. **Monitoring:** đã có metric, profiling, latency/load test bổ sung chưa?
16. **Prod:** không mang agent hay JVM flag test vào production khi chưa đánh giá overhead và tương thích.

**Kết luận:** BlockHound là một công cụ bổ sung cho kiểm thử Reactor, hữu ích để phát hiện blocking methods trên các thread non-blocking như `Schedulers.parallel()` và event loop khi agent cài được. Cần cài đúng JVM, kiểm tra bằng positive probe và assert `BlockingOperationError`. Khi JDK hoặc môi trường không hỗ trợ instrumentation, không nên giả báo PASS; hãy bỏ qua lớp test opt-in một cách minh bạch và tiếp tục baseline StepVerifier, code review, profiling và kiểm thử tích hợp. Việc sửa lỗi nên ưu tiên non-blocking API; nếu bắt buộc phải dùng legacy blocking code, cô lập trên boundedElastic cùng các giới hạn tài nguyên phù hợp.

## Tài liệu tham khảo

- BlockHound — GitHub README, installation, integrations, JDK 13+ flag: https://github.com/reactor/BlockHound
- BlockHound — Quick Start: https://github.com/reactor/BlockHound/blob/master/docs/quick_start.md
- BlockHound — Customization: https://github.com/reactor/BlockHound/blob/master/docs/customization.md
- BlockHound — Releases (1.0.18.RELEASE, October 2026): https://github.com/reactor/BlockHound/releases
- Reactor Core 3.8 — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Reactor Core 3.8 — NonBlocking and Schedulers API: https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html
- Reactor Test — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor BlockHound Builder — API reference: https://projectreactor.io/docs/BlockHound/snapshot/api/reactor/blockhound/BlockHound.Builder.html
