# Phát hiện lời gọi chặn bằng BlockHound trong môi trường phù hợp

Một ứng dụng reactive có thể dùng `Mono` và `Flux` ở mọi tầng nhưng vẫn vô tình chặn thread trong lúc chờ I/O. Một lời gọi JDBC đồng bộ trên Reactor Netty event loop, `Thread.sleep()` trong `Schedulers.parallel()` hoặc `Future.get()` trong callback đều có thể làm pipeline mất khả năng phục vụ các công việc khác. Những lỗi này đôi khi không xuất hiện trong unit test thông thường vì test chạy trên thread không bị đánh dấu là non-blocking.

BlockHound giúp phát hiện một nhóm lời gọi blocking khi chúng chạy trên thread được xem là non-blocking. Khi phát hiện, nó ném `BlockingOperationError` tại thời điểm lời gọi xảy ra. Kết hợp BlockHound với kiểm thử Reactor giúp nhóm phát triển tìm lỗi sớm, xác định chính xác vị trí chặn và kiểm tra rằng API blocking đã được cô lập trên scheduler phù hợp.

Bài học thuộc chương **Kiểm thử** của module `REACTIVE_PROGRAMMING`, tập trung vào các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung hướng dẫn cài đặt BlockHound trong môi trường phù hợp, đọc lỗi, viết kiểm thử có chủ đích và hiểu giới hạn của công cụ.

## 1. Blocking nguy hiểm ở đâu trong pipeline reactive?

Reactive Streams cho phép subscriber yêu cầu dữ liệu theo demand và nhận tín hiệu bất đồng bộ. Reactor thường dùng nhiều scheduler để chạy các giai đoạn khác nhau. Một số thread được thiết kế để xử lý nhanh và không chặn, đặc biệt là worker của `Schedulers.parallel()`, `Schedulers.single()` và event loop của Reactor Netty.

Nếu một callback giữ thread non-blocking trong lúc đợi I/O hoặc một điều kiện khác, thread đó không thể xử lý những tín hiệu đang chờ. Với event loop, nhiều kết nối có thể dùng chung một thread nên một lời gọi blocking có thể làm tăng độ trễ của nhiều request.

Ví dụ không an toàn:

```java
Mono<Profile> profile = Mono.fromCallable(() -> {
    // Ví dụ giả định DAO dùng JDBC đồng bộ.
    return jdbcProfileDao.findById(42L);
}).subscribeOn(Schedulers.parallel());
```

`fromCallable` trì hoãn việc gọi DAO đến lúc subscribe, nhưng `subscribeOn(parallel())` lại đưa thao tác blocking lên scheduler dành cho công việc CPU-bound không blocking. Trì hoãn lời gọi không đồng nghĩa với việc lời gọi đã an toàn.

Một số lời gọi blocking phổ biến:

- `Thread.sleep(...)`, `Object.wait(...)` và các thao tác chờ tương tự.
- `Future.get()`, `CompletableFuture.join()` hoặc `CountDownLatch.await()`.
- JDBC, JPA đồng bộ và một số client HTTP đồng bộ.
- Đọc file/socket bằng API đồng bộ như `InputStream.read()`.
- Chờ khóa hoặc semaphore khi có tranh chấp.
- Gọi `block()`, `blockFirst()` hoặc `blockLast()` trong một thread non-blocking.

Không phải tất cả các phương thức này đều được BlockHound phát hiện trong mọi phiên bản và môi trường. Công cụ chỉ kiểm tra những điểm blocking đã được instrument hoặc tích hợp; phần giới hạn này cần được tính đến khi đọc kết quả.

## 2. BlockHound phát hiện blocking như thế nào?

BlockHound sử dụng Java instrumentation để kiểm tra một số phương thức có khả năng blocking. Nó kết hợp với các integration để biết thread nào cần được bảo vệ. Reactor cung cấp integration đánh dấu các thread non-blocking của scheduler; khi một phương thức đã được nhận diện là blocking được gọi trên thread đó, BlockHound ném `BlockingOperationError`.

```text
Reactor pipeline
       |
       v
Thread đang thực thi callback
       |
       v
Thread có được xem là non-blocking?
       |
       +---- Không ----> lời gọi tiếp tục theo hành vi bình thường
       |
       +---- Có
              |
              v
       Gọi phương thức đã được instrument?
              |
              +---- Không ----> BlockHound có thể không phát hiện
              |
              +---- Có
                     |
                     v
             BlockingOperationError
```

Điểm quan trọng là BlockHound kiểm tra theo thread thực thi tại thời điểm gọi. Cùng một API có thể bị báo lỗi khi chạy trên `parallel`, nhưng được chấp nhận khi chạy trên `boundedElastic`, vì scheduler này được thiết kế để chứa các tác vụ blocking có giới hạn.

BlockHound không biến API blocking thành API non-blocking và cũng không tự chuyển công việc sang scheduler khác. Nó là công cụ phát hiện và kiểm thử. Ứng dụng vẫn phải thiết kế ranh giới scheduler đúng cách.

## 3. Thêm BlockHound vào môi trường kiểm thử

BlockHound thường được thêm vào test runtime để kiểm tra các đường đi reactive trong unit test hoặc integration test. Hãy chọn phiên bản tương thích với JDK, Reactor và hệ thống build của dự án.

### Gradle

```kotlin
dependencies {
    testImplementation("io.projectreactor.tools:blockhound:<compatible-version>")
}
```

Thay `<compatible-version>` bằng phiên bản BlockHound đã được dự án xác nhận. Không dùng một phiên bản tùy ý nếu dự án đang khóa phiên bản Reactor hoặc JDK cụ thể.

### Maven

```xml
<dependency>
    <groupId>io.projectreactor.tools</groupId>
    <artifactId>blockhound</artifactId>
    <version>${blockhound.version}</version>
    <scope>test</scope>
</dependency>
```

Khai báo `blockhound.version` trong properties hoặc dependency management của dự án. Phạm vi `test` giữ công cụ trong test runtime; nếu muốn kiểm tra một môi trường chạy khác, cần cấu hình dependency và agent theo đúng mục tiêu triển khai.

BlockHound dựa vào instrumentation của JVM. Một số JDK, cấu hình CI, container hoặc chính sách bảo mật có thể hạn chế dynamic attach hoặc class retransformation. Nếu `BlockHound.install()` thất bại khi khởi tạo, hãy kiểm tra thông báo của JVM và hướng dẫn tương thích của phiên bản BlockHound đang dùng; đừng bỏ qua lỗi cài đặt rồi kết luận rằng test đã bảo vệ được blocking.

## 4. Cài đặt BlockHound một lần trước khi chạy test

BlockHound nên được cài đặt sớm trong test process, trước khi các test khởi tạo scheduler hoặc chạy pipeline cần kiểm tra. Vì instrumentation là trạng thái dùng chung của JVM, không nên gọi `install()` tùy tiện trong từng test method.

Ví dụ với JUnit 5:

```java
import org.junit.jupiter.api.BeforeAll;
import reactor.blockhound.BlockHound;

abstract class BlockHoundTestSupport {
    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }
}
```

Các test cần kiểm tra blocking có thể kế thừa lớp hỗ trợ này. Với một test suite lớn, có thể cài đặt ở bootstrap chung hoặc extension được dự án quản lý để tránh cài lặp và bảo đảm thứ tự khởi tạo nhất quán.

Reactor integration được BlockHound nạp thông qua cơ chế integration của nó khi các thư viện tương ứng có mặt trên classpath. Khi test không phát hiện blocking như mong đợi, hãy xác minh integration Reactor được nạp và thread đang chạy thực sự được đánh dấu non-blocking.

## 5. Viết test cố ý tạo blocking trên scheduler non-blocking

Một test có chủ đích có thể gọi `Thread.sleep()` trên `Schedulers.parallel()` để xác minh BlockHound phát hiện vi phạm:

```java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingDetectionTest extends BlockHoundTestSupport {

    @Test
    void detectsSleepOnParallelScheduler() {
        Mono<Void> pipeline = Mono.fromRunnable(() -> {
            try {
                Thread.sleep(10);
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(error);
            }
        }).subscribeOn(Schedulers.parallel());

        StepVerifier.create(pipeline)
            .expectError(BlockingOperationError.class)
            .verify(Duration.ofSeconds(2));
    }
}
```

Trong ví dụ, `subscribeOn(parallel())` đưa callable lên worker non-blocking. Khi `Thread.sleep` được gọi, BlockHound phát hiện và ném `BlockingOperationError`. `StepVerifier` xác minh lỗi mong đợi và đặt timeout để test không treo vô hạn nếu môi trường kiểm thử bị cấu hình sai.

Đây là test âm có chủ đích: pipeline được tạo ra để vi phạm quy tắc và test thành công khi công cụ phát hiện đúng. Không đưa đoạn blocking này vào code production.

### Vì sao không chỉ kiểm tra thread name?

Tên thread như `parallel-1` hoặc `reactor-http-nio-2` hữu ích khi chẩn đoán, nhưng tên có thể thay đổi theo phiên bản và cấu hình. BlockHound dựa vào trạng thái non-blocking và phương thức được instrument thay vì dựa đơn thuần vào chuỗi tên thread. Test nên xác minh hành vi phát hiện, không khóa cứng vào tên thread nội bộ.

## 6. Kiểm tra cách sửa: đưa API blocking lên `boundedElastic`

Khi phải tích hợp một thư viện đồng bộ, hãy trì hoãn lời gọi và thực thi nó trên scheduler dành cho blocking:

```java
Mono<LegacyProfile> findProfile(long id) {
    return Mono.fromCallable(() -> legacyDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`fromCallable` trì hoãn việc gọi DAO đến subscription. `subscribeOn(boundedElastic())` chuyển quá trình thực thi callable sang scheduler có giới hạn được thiết kế để chứa tác vụ blocking. Các bước reactive tiếp theo có thể kết hợp publisher này bằng `flatMap` mà không gọi `block()`.

Có thể viết test kiểm tra pipeline hoàn tất trên môi trường có BlockHound:

```java
@Test
void blockingAdapterRunsOnBoundedElastic() {
    Mono<String> pipeline = Mono.fromCallable(() -> {
        try {
            Thread.sleep(5);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(error);
        }
        return "loaded";
    }).subscribeOn(Schedulers.boundedElastic());

    StepVerifier.create(pipeline)
        .expectNext("loaded")
        .verifyComplete();
}
```

BlockHound không báo lỗi trong ví dụ này vì `boundedElastic` cho phép tác vụ blocking. Điều đó không có nghĩa có thể chạy số lượng blocking task vô hạn. `boundedElastic` vẫn có giới hạn worker và hàng đợi; hãy kiểm soát concurrency, timeout và thời gian thực thi.

Nếu có driver reactive phù hợp, ưu tiên API non-blocking xuyên suốt. `boundedElastic` là ranh giới tích hợp cho thư viện legacy hoặc thao tác đồng bộ chưa thể thay thế.

## 7. `publishOn` sau lời gọi blocking không sửa được nguồn

Một lỗi thường gặp là gọi blocking trước rồi mới chuyển scheduler bằng `publishOn`:

```java
Mono<LegacyProfile> unsafe = Mono.fromCallable(
        () -> legacyDao.findById(42L)
    )
    .publishOn(Schedulers.boundedElastic());
```

`publishOn` chuyển các tín hiệu downstream sau vị trí đặt operator. Nó không chuyển ngược việc thực thi callable nguồn. Nếu subscription bắt đầu trên event loop, lời gọi DAO có thể chạy trên event loop trước khi tín hiệu được chuyển sang `boundedElastic`.

Đặt `subscribeOn` ở nguồn:

```java
Mono<LegacyProfile> safe = Mono.fromCallable(
        () -> legacyDao.findById(42L)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

Nếu pipeline có nhiều giai đoạn, có thể dùng `publishOn` để chuyển phần biến đổi downstream, còn `subscribeOn` để định vị việc subscribe nguồn. Hãy chọn vị trí dựa trên nơi thao tác thực sự được thực thi.

## 8. Phát hiện blocking trong WebFlux và event loop

Trong ứng dụng WebFlux dùng Reactor Netty, event loop phục vụ nhiều kết nối. Một handler không nên gọi JDBC, `Thread.sleep()` hoặc client HTTP đồng bộ trực tiếp.

Ví dụ handler không an toàn:

```java
@GetMapping("/profiles/{id}")
Mono<Profile> find(@PathVariable long id) {
    Profile profile = jdbcDao.findById(id);
    return Mono.just(profile);
}
```

Lời gọi JDBC xảy ra ngay trong phương thức controller, trước khi `Mono.just` được trả về. Nếu controller chạy trên event loop, thread đó bị chặn. BlockHound có thể phát hiện các phương thức blocking đã được instrument khi chúng chạy trên thread Reactor Netty non-blocking.

Adapter blocking an toàn hơn:

```java
@GetMapping("/profiles/{id}")
Mono<Profile> find(@PathVariable long id) {
    return Mono.fromCallable(() -> jdbcDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Nếu repository hỗ trợ R2DBC, hãy dùng repository reactive trực tiếp:

```java
@GetMapping("/profiles/{id}")
Mono<Profile> find(@PathVariable long id) {
    return reactiveProfileRepository.findById(id);
}
```

BlockHound có thể giúp phát hiện lỗi trong integration test chạy qua WebFlux, nhưng test phải thực sự thực thi handler trên event loop. Một unit test gọi trực tiếp phương thức controller từ thread JUnit không tái tạo đầy đủ môi trường thực thi của server.

## 9. Đọc và diễn giải `BlockingOperationError`

Khi BlockHound phát hiện blocking, stack trace thường cho biết:

- Phương thức blocking bị phát hiện, ví dụ `Thread.sleep` hoặc một phương thức I/O đã instrument.
- Thread hiện tại đang thực thi.
- Chuỗi operator/callback dẫn đến lời gọi đó.
- Các frame của thư viện ứng dụng hoặc thư viện bên thứ ba gọi phương thức blocking.

Khi đọc stack trace, hãy tìm frame đầu tiên thuộc code ứng dụng sau phương thức blocking. Frame đó thường chỉ ra adapter, mapper, callback hoặc service đã gọi API không phù hợp.

Ví dụ cách điều tra:

1. Xác định thread đang bị báo lỗi có phải `parallel`, `single` hoặc event loop không.
2. Tìm lời gọi ứng dụng gần nhất dẫn đến phương thức blocking.
3. Xác định API đó là JDBC, file I/O, lock, future hay một lời gọi chờ khác.
4. Kiểm tra operator và scheduler trước vị trí lỗi.
5. Nếu là API legacy, chuyển lời gọi vào `fromCallable`/`fromRunnable` và `subscribeOn(boundedElastic())`.
6. Nếu có API reactive tương ứng, thay thế adapter blocking.
7. Chạy lại test để xác minh lỗi đã biến mất và kiểm tra kết quả nghiệp vụ vẫn đúng.

Không nên chỉ bắt `BlockingOperationError` rồi bỏ qua. Làm như vậy khiến test xanh nhưng lỗi chặn vẫn tồn tại.

## 10. Phân biệt lỗi blocking với lỗi scheduler và lỗi thời gian

Không phải mọi test chậm hoặc pipeline không hoàn tất đều do blocking. Một pipeline có thể chờ nguồn không phát dữ liệu, bị starvation, deadlock do khóa, hoặc đơn giản là đang thực hiện công việc CPU quá nặng.

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
|---|---|---|
| `BlockingOperationError` | Phương thức blocking được gọi trên thread non-blocking. | Đọc stack trace và xác định call site. |
| Pipeline treo nhưng không có BlockHound error | Nguồn chưa phát, scheduler starvation, API không được instrument hoặc deadlock. | Thread dump, log, metric và trạng thái subscription. |
| CPU cao, không có thread chờ I/O | Công việc CPU-bound kéo dài hoặc vòng lặp không kết thúc. | Profiler và thread dump. |
| Event loop phản hồi chậm | Blocking hoặc callback CPU-bound lâu trên event loop. | Theo dõi event-loop latency và thread dump. |
| Queue tăng, worker bận | Concurrency vượt capacity hoặc tác vụ downstream chậm. | Scheduler metrics, queue size và throughput. |

BlockHound phát hiện một lớp vấn đề. Nó không thay thế profiler, thread dump, metric scheduler, timeout hoặc kiểm thử hiệu năng.

## 11. Giới hạn và false positive của BlockHound

BlockHound hữu ích nhưng không phải bộ phân tích tĩnh toàn diện. Cần hiểu phạm vi của nó để không diễn giải sai kết quả.

### Không phát hiện mọi dạng blocking

BlockHound chỉ phát hiện những phương thức đã được instrument hoặc được integration nhận diện. Một thư viện có thể chặn bên trong native code, dùng API chưa được instrument hoặc tự triển khai vòng chờ mà công cụ không nhận ra. Không có lỗi BlockHound không chứng minh toàn bộ pipeline là non-blocking.

### Chỉ báo lỗi trên thread được bảo vệ

Một lời gọi blocking chạy trên thread JUnit, thread tùy chỉnh không được đánh dấu hoặc `boundedElastic` có thể không bị báo lỗi. Nếu test chạy code trên thread khác với môi trường production, kết quả có thể bỏ sót vấn đề.

### Blocking được cho phép trên `boundedElastic`

`boundedElastic` là nơi dành cho tác vụ blocking có giới hạn. BlockHound thường không báo lỗi khi các thao tác đó chạy ở đây. Nhưng nếu quá nhiều tác vụ được gửi vào, worker hoặc queue vẫn có thể bão hòa. Cần kiểm soát capacity và đo thời gian chờ.

### CPU-bound lâu không nhất thiết là blocking

Một vòng lặp tính toán kéo dài có thể chiếm worker non-blocking nhưng không gọi phương thức blocking đã instrument. BlockHound có thể không phát hiện. Hãy dùng profiler và giới hạn thời gian/concurrency cho công việc CPU nặng.

### Có thể có false positive hoặc thư viện cần cấu hình riêng

Một số thư viện có phương thức bị nhận diện là blocking dù ứng dụng dùng chúng trong một ngữ cảnh được kiểm soát. Trước khi cho phép, hãy xác minh hợp đồng thư viện và thread thực thi. Nếu thực sự cần ngoại lệ, cấu hình allow-list thật hẹp và ghi rõ lý do.

## 12. Allow-list có kiểm soát cho một phương thức đã được đánh giá

BlockHound cho phép khai báo một số lời gọi được phép bằng `allowBlockingCallsInside`. Chỉ dùng khi đã xác minh phương thức đó không gây rủi ro trong thread đang chạy hoặc thư viện có lý do kỹ thuật đặc biệt.

```java
BlockHound.builder()
    .allowBlockingCallsInside(
        "com.example.NativeBridge",
        "readAlreadyAvailableValue"
    )
    .install();
```

Ví dụ minh họa cách khai báo theo tên class và method. Không nên allow toàn bộ package, toàn bộ thư viện hoặc các phương thức chung như `read`, `wait` hay `sleep`. Allow-list quá rộng có thể che giấu lỗi blocking thật trong những đường đi khác.

Nếu một thư viện cần thực hiện I/O blocking, giải pháp ưu tiên vẫn là đặt nó trên `boundedElastic` hoặc thay bằng API non-blocking. Allow-list không phải cách chuyển scheduler và cũng không làm lời gọi trở nên bất đồng bộ.

## 13. Kết hợp BlockHound với `StepVerifier`

`StepVerifier` kiểm tra tín hiệu của publisher: giá trị, hoàn tất, lỗi và cancellation. BlockHound bổ sung kiểm tra rằng một số phương thức blocking không được gọi trên thread non-blocking trong lúc pipeline chạy.

Ví dụ kết hợp:

```java
@Test
void reactivePipelineDoesNotBlock() {
    Mono<String> pipeline = Mono.fromCallable(() -> "profile")
        .subscribeOn(Schedulers.parallel())
        .map(String::toUpperCase);

    StepVerifier.create(pipeline)
        .expectNext("PROFILE")
        .verifyComplete();
}
```

Nếu một operator trong chuỗi vô tình gọi phương thức blocking đã được instrument trên worker `parallel`, BlockHound sẽ làm publisher phát lỗi và test thất bại. Test vẫn kiểm tra kết quả đầu ra như bình thường.

Nên có cả test dương và test âm:

- Test dương: pipeline hợp lệ chạy xong, phát đúng kết quả và không có blocking error.
- Test âm: một đoạn code cố ý blocking trên non-blocking scheduler bị BlockHound phát hiện.
- Test adapter: API blocking được cô lập trên `boundedElastic` và pipeline hoàn tất.
- Integration test: request WebFlux đi qua event loop mà không gọi API blocking trực tiếp.

Test âm xác minh công cụ hoạt động; test dương xác minh code ứng dụng tuân thủ quy tắc. Không thay thế toàn bộ suite bằng một test `Thread.sleep` đơn lẻ.

## 14. Kiểm tra cancellation và tài nguyên khi test phát hiện blocking

BlockHound không quản lý resource lifecycle. Khi một test thất bại hoặc timeout, ứng dụng vẫn cần hủy subscription và giải phóng tài nguyên. Với nguồn tạo từ `using` hoặc `usingWhen`, hãy kiểm tra cleanup khi lỗi hoặc cancel.

```java
AtomicBoolean closed = new AtomicBoolean();

Mono<String> pipeline = Mono.using(
    () -> new AutoCloseable() {
        @Override
        public void close() {
            closed.set(true);
        }
    },
    resource -> Mono.fromCallable(() -> {
        // Công việc reactive của ví dụ.
        return "done";
    }),
    resource -> {
        try {
            resource.close();
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
);

StepVerifier.create(pipeline)
    .expectNext("done")
    .verifyComplete();

assertTrue(closed.get());
```

Ví dụ dùng cleanup đồng bộ để minh họa ownership. Với resource có thao tác close bất đồng bộ, dùng `usingWhen` để Reactor phối hợp publisher cleanup. Nếu một blocking call không hỗ trợ interrupt, cancellation có thể không dừng lời gọi ngay; hãy cấu hình timeout tại client hoặc driver.

## 15. Quy trình đưa BlockHound vào CI

BlockHound có thể chạy trong unit test hoặc integration test của CI. Một quy trình thực tế:

1. Chọn JDK và phiên bản BlockHound tương thích với dự án.
2. Cài đặt BlockHound một lần trong test process trước khi pipeline cần kiểm tra chạy.
3. Chạy các test service, adapter và WebFlux handler trên scheduler giống môi trường production.
4. Khi gặp `BlockingOperationError`, lưu stack trace và xác định call site thuộc ứng dụng hay thư viện.
5. Sửa bằng API reactive hoặc cô lập API blocking trên `boundedElastic`.
6. Chỉ thêm allow-list khi đã đánh giá và ghi rõ lý do.
7. Chạy lại test dương, test âm và integration test liên quan.
8. Theo dõi thay đổi JDK, Reactor, driver và dependency vì chúng có thể thay đổi hành vi instrumentation.

Không nên làm CI xanh bằng cách vô hiệu hóa BlockHound trên toàn suite khi gặp lỗi. Nếu một môi trường không hỗ trợ attach/instrumentation, hãy ghi nhận rõ test đó không chạy được và thiết lập một môi trường tương thích để thực hiện kiểm tra.

## 16. Tình huống thực tế: tìm lỗi JDBC chạy trên event loop

Một endpoint WebFlux tải hồ sơ khách hàng bằng một DAO cũ dùng JDBC. Trong môi trường local, endpoint hoạt động nhưng khi tải cao, độ trễ của nhiều request tăng. Một integration test cài BlockHound và gửi request đến endpoint.

Code ban đầu:

```java
@GetMapping("/customers/{id}")
Mono<Customer> getCustomer(@PathVariable long id) {
    return Mono.just(jdbcCustomerDao.findById(id));
}
```

Lời gọi `findById` được thực thi ngay khi controller được gọi. Nếu nó chạy trên event loop, BlockHound có thể phát hiện phương thức I/O blocking của driver hoặc lời gọi blocking liên quan. Stack trace chỉ đến DAO và call site của controller.

Sửa bằng adapter:

```java
Mono<Customer> findCustomer(long id) {
    return Mono.fromCallable(() -> jdbcCustomerDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}

@GetMapping("/customers/{id}")
Mono<Customer> getCustomer(@PathVariable long id) {
    return findCustomer(id);
}
```

Sau khi sửa, integration test phải xác minh request vẫn trả đúng customer và BlockHound không báo blocking trên event loop. Tiếp đó, theo dõi số worker `boundedElastic` đang hoạt động, thời gian chờ và connection pool. Nếu lưu lượng lớn, cần cân nhắc chuyển DAO sang R2DBC thay vì chỉ tăng số worker.

## 17. Checklist sử dụng BlockHound đúng cách

- Thêm BlockHound vào đúng test runtime và chọn phiên bản tương thích JDK/Reactor.
- Cài đặt một lần, sớm trong test process.
- Xác minh Reactor integration được nạp và thread được bảo vệ đúng.
- Dùng test âm để xác nhận một lời gọi blocking bị phát hiện trên scheduler non-blocking.
- Dùng test dương để xác nhận pipeline hợp lệ không phát `BlockingOperationError`.
- Dùng `subscribeOn(boundedElastic())` cho adapter API blocking; không trông chờ `publishOn` đặt sau nguồn sửa được lời gọi.
- Ưu tiên driver/client reactive khi có thể.
- Không nhầm việc BlockHound cho phép `boundedElastic` với việc scheduler có capacity vô hạn.
- Hiểu công cụ không phát hiện mọi API blocking, CPU-bound lâu hoặc mọi deadlock.
- Dùng allow-list hẹp, có lý do và được review; không vô hiệu hóa kiểm tra rộng.
- Kết hợp `StepVerifier`, integration test, thread dump và metric để chẩn đoán.
- Kiểm tra cancellation và cleanup khi pipeline lỗi hoặc bị hủy.

BlockHound bổ sung một lớp bảo vệ hữu ích cho kiểm thử reactive bằng cách phát hiện một số lời gọi blocking trên thread non-blocking. Công cụ giúp tìm call site sớm, nhưng không thay thế thiết kế scheduler, driver non-blocking, kiểm soát concurrency hay quan sát vận hành. Khi cài đặt đúng môi trường, kết hợp test âm/dương và sửa ranh giới blocking rõ ràng, nhóm phát triển có thể giữ event loop và scheduler CPU-bound hoạt động đúng mục đích.
