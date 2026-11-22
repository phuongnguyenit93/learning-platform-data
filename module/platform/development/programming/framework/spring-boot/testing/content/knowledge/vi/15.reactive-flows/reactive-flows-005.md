# Tạo publisher đúng thời điểm khi dùng StepVerifier.withVirtualTime

Trong **Spring Boot và Project Reactor**, nhiều pipeline dùng **Mono.delay**, **Flux.interval**, **delayElements**, **timeout**, **retryWhen** hoặc những operator cần Scheduler. Nếu kiểm thử bằng đồng hồ thật, một phép thử “chờ một ngày” hiển nhiên không thực tế. **StepVerifier.withVirtualTime** của reactor-test thay cách quản lý thời gian của các Scheduler được Reactor hỗ trợ bằng **VirtualTimeScheduler**, cho phép test tua nhanh đồng hồ mà không thực sự đợi nhiều giờ.

Tuy nhiên, virtual time chỉ có ý nghĩa khi **pipeline được tạo đúng thời điểm**. Điều quan trọng nhất là **cung cấp Supplier<Publisher<T>> tạo publisher sau khi virtual scheduler đã được kích hoạt**. Nếu tạo sẵn một Mono/Flux có operator theo thời gian rồi truyền nó qua lambda chỉ để thỏa cú pháp, operator có thể đã nắm giữ Scheduler thật từ trước: test chờ, treo hoặc chạy theo thời gian thực dù ta gọi thenAwait.

Bài này giải thích **assembly – subscription – scheduling – verification**, cách viết đúng và sai, ví dụ chạy được với **Java 17, Spring Boot 3.4.5, Reactor Test và JUnit Jupiter**, giới hạn của virtual time và phương pháp kiểm tra lỗi một cách có hệ thống.

## 1. Vì sao Supplier quan trọng hơn cú pháp lambda?

Hãy nhìn hai cách viết có vẻ tương đương.

**Sai về ý định dùng virtual time (đừng đưa vào suite kiểm thử):**

~~~java
Mono<Long> alreadyBuilt = Mono.delay(Duration.ofHours(12));

StepVerifier.withVirtualTime(() -> alreadyBuilt)
    .expectSubscription()
    .thenAwait(Duration.ofHours(12))
    .expectNext(0L)
    .verifyComplete();
~~~

Biến **alreadyBuilt** đã được tạo **trước** khi StepVerifier kích hoạt virtual scheduler. Một số operator thời gian lấy Scheduler ngay khi **assembly**, ví dụ qua Schedulers.parallel(). Supplier ở đây không tạo pipeline mới, nó chỉ trả lại object cũ. Kết quả có thể phụ thuộc Scheduler thật hoặc không tiến hành đúng theo clock ảo. Đừng cố “sửa” bằng Thread.sleep hoặc tăng timeout test lên nhiều giờ.

**Đúng: khởi tạo timed operator bên trong Supplier**

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(12)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(12))
    .expectNext(0L)
    .verifyComplete();
~~~

Khi StepVerifier chuẩn bị kiểm thử, nó thiết lập VirtualTimeScheduler rồi mới gọi **Supplier** để lấy Publisher. Do đó **Mono.delay** và Scheduler mặc định mà nó dùng được xác định trong phạm vi virtual-time setup. Sau **thenAwait(12 giờ ảo)**, Mono phát **0L** và complete mà không cần chờ 12 giờ ngoài đời.

**Mẹo nhớ:** publisher nên được **tạo trong lambda**, không phải **chỉ được trả từ lambda**.

### Reactor tài liệu hóa điều gì?

Reactor Test API nhận **Supplier<? extends Publisher<? extends T>>** thay vì một Publisher có sẵn vì các time-based operators cần được khởi tạo sau khi virtual clock được kích hoạt. Tài liệu nhấn mạnh tránh dựng Flux trước rồi để Supplier trả biến đã có. Tham khảo chính thức ở cuối bài, đặc biệt phần *Manipulating Time* và Javadoc StepVerifier.

Điều này không phải quy tắc đặt tên biến hay việc lambda có dấu ngoặc nào; đây là **thứ tự thời điểm thực thi code tạo operator**.

## 2. Bốn thời điểm cần phân biệt: assembly, subscription, schedule, emit

| Thời điểm | Điều xảy ra | Rủi ro khi dùng virtual time |
| --- | --- | --- |
| **Assembly** | Code gọi Mono.delay, Flux.interval, timeout, retryWhen, publishOn… để tạo pipeline | Timed operator có thể chụp Scheduler mặc định hoặc scheduler được truyền tường minh ngay lúc này |
| **Subscription** | StepVerifier subscribe, Reactor tạo Subscription và kích hoạt logic subscription | Một số operator/defer mới tạo work, đăng ký timer hoặc lên lịch khi subscribe |
| **Scheduling** | Operator đưa tác vụ vào Scheduler với thời điểm chạy | Nếu scheduler là real/custom scheduler, thenAwait trên VirtualTimeScheduler không tua nhanh được |
| **Emission** | onNext, onError, onComplete được gửi đến subscriber | StepVerifier phải advance virtual clock đúng bước, có demand phù hợp để quan sát tín hiệu |

**Publisher có tính lazy** không có nghĩa mọi thứ bên trong nó đều được lựa chọn lazy. Trong Reactor, phần lớn xử lý dữ liệu đợi đến lúc subscribe, nhưng việc **tạo operator** có thể quyết định scheduler/clock hoặc giữ reference ngoài từ trước. Vì vậy “Reactor là lazy” **không** biện minh cho việc dựng sẵn mọi pipeline trước withVirtualTime.

Ví dụ:

~~~java
Mono<String> timeBound = Mono.delay(Duration.ofMinutes(30))
    .map(ignored -> "ready");
~~~

Dù giá trị **ready** chỉ được phát khi subscribe, nguồn thời gian **Mono.delay(...)** đã được tạo ở assembly time. Nếu tạo trong constructor singleton Spring, khi JUnit chạy test thì nó có thể đã giữ Scheduler được lựa chọn trước đó.

### Một cách dùng đúng với service object tạo trước

**Được phép tạo service object trước**, nếu method service **tạo publisher mới mỗi lần được gọi**:

~~~java
TimedStreamService service = new TimedStreamService();

StepVerifier.withVirtualTime(
        () -> service.delayed("ready", Duration.ofHours(6)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(6))
    .expectNext("ready")
    .verifyComplete();
~~~

Supplier chạy method service sau virtual setup; method lại tạo Mono.delay mới trong mỗi lần gọi. Tuy nhiên nếu **service.delayed(...)** chỉ trả về một field Mono đã tạo sẵn trong constructor, lambda sẽ không giúp gì. Phải xem implementation, không chỉ signature.

## 3. StepVerifier.withVirtualTime chạy như thế nào?

**StepVerifier.create(publisher)** dùng publisher đã có và quan sát nó theo thời gian thực; có ích cho logic đồng bộ hoặc time-based test rất ngắn. **StepVerifier.withVirtualTime(supplier)** thiết lập virtual scheduler quanh lần verify để điều khiển các scheduler mặc định mà operator sử dụng.

Các phương thức quan trọng:

- **expectSubscription()**: xác nhận sự kiện subscribe. Nên đặt trước expectNoEvent.
- **expectNoEvent(Duration)**: cho thời gian trôi, đồng thời **FAIL nếu có bất cứ event nào** trong khoảng đó; kể cả **subscription** cũng được xem là event.
- **thenAwait(Duration)**: cho thời gian trôi mà **không khẳng định không có event** trong khoảng đó. Trong virtual mode, nó **advance clock ảo**.
- **expectNext(value)**: xác nhận onNext có đúng giá trị.
- **expectNextCount(n)**: kiểm tra số onNext khi không quan tâm nội dung cụ thể.
- **expectComplete()** và **verifyComplete()**: kiểm tra completion.
- **expectError(...)** và **verifyError(...)**: kiểm tra lỗi.
- **thenCancel()**: dừng kiểm thử với stream không bao giờ kết thúc.
- **verify(Duration.ofSeconds(5))**: giới hạn **thời gian thực** mà test được phép dùng để verify; không phải thời gian ảo do pipeline cần.
- **withVirtualTime(supplier, initialRequest)**: có thể điều khiển demand đầu, nhưng phải thenRequest đúng lúc trước khi timer phát, nếu không một số source như Flux.interval có thể báo overflow vì thiếu request.

**Không đặt expectNoEvent làm bước đầu tiên**:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectNoEvent(Duration.ofHours(1))  // Sai: subscription la event.
    .thenAwait(Duration.ofHours(23))
    .expectNext(0L)
    .verifyComplete();
~~~

**Sửa bằng expectSubscription():**

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofHours(23))
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
~~~

Ví dụ thứ hai có assertion mạnh: **không phát quá sớm** trong 23 giờ ảo, rồi có giá trị đúng sau thêm một giờ ảo. Nếu chỉ dùng thenAwait(1 ngày), test không trực tiếp bảo vệ yêu cầu “không được phát sớm”.

### StepVerifier có thật sự chạy nhanh hơn không?

Thời gian ảo có thể tua từ 0 tới nhiều giờ chỉ với vài bước scheduling nội bộ. Tuy nhiên công việc CPU thật, I/O, khóa thread, JDBC, network hoặc Thread.sleep **không bị VirtualTimeScheduler tự làm nhanh hơn**. Vì vậy một test virtual time vẫn có thể chậm/hang nếu pipeline phụ thuộc công việc không dùng virtual scheduler.

Đừng assert rằng verify() phải mất đúng 0 ms. Tốc độ thật phụ thuộc build, JVM, GC và CI; hãy assert **emission order/time contract** chứ không assert microseconds của runner.

## 4. Những operator thường cần tạo trong Supplier

| Operator / thao tác | Tác dụng | Kịch bản với virtual clock |
| --- | --- | --- |
| **Mono.delay(duration)** | Sau khoảng chờ mới phát 0L | Kiểm tra chờ một giờ/ngày |
| **Flux.interval(period)** | Phát 0L, 1L… theo chu kỳ, đợt đầu sau period | Kiểm tra heartbeat hoặc polling |
| **delayElements(duration)** | Trì hoãn từng onNext | Kiểm tra khoảng cách dữ liệu đến |
| **timeout(duration)** | Ném TimeoutException nếu nguồn không phát kịp | Test fallback/timeout logic |
| **retryWhen(Retry.fixedDelay(...))** | Retry sau khoảng backoff cố định | Kiểm tra số lần retry và kết quả thành công |
| **retryWhen(Retry.backoff(...))** | Backoff tăng dần, có thể kèm jitter | Cần kiểm soát jitter và điều kiện scheduling |
| **delaySubscription(duration)** | Chậm bắt đầu subscription | Cần không phát/subscribe trước deadline |
| **publishOn(Schedulers.parallel())** | Đổi Scheduler cho xử lý sau điểm đổi | Scheduler cần được chọn trong virtual scope, nếu muốn dùng clock ảo |
| **subscribeOn(scheduler)** | Lên lịch subscribe trên scheduler cụ thể | Nếu scheduler được tạo từ trước, virtual time có thể không kiểm soát được |

Danh sách không có nghĩa mọi operator này chắc chắn capture scheduler ở **cùng** một phương thức và version. Quy tắc đáng tin hơn là **để toàn bộ assembly của timed chain xảy ra trong Supplier**, rồi kiểm tra scheduler mà operator thực tế dùng.

Các Scheduler được tạo riêng như **Schedulers.newSingle("real")**, **Schedulers.fromExecutor(...)** hoặc executor của thư viện khác **không tự được thay bằng VirtualTimeScheduler** chỉ vì bạn dùng withVirtualTime. Nếu operator truyền tường minh một custom scheduler không nằm dưới cơ chế được Reactor virtualize, thenAwait không tua clock của scheduler ấy.

## 5. Ví dụ phản chứng dễ mắc: tạo publisher trong fixture

Trong một test class hoặc Spring bean, người viết thường dựng publisher ở field:

~~~java
class FragileExample {
    // Được khởi tạo khi test object được tạo, trước withVirtualTime.
    private final Flux<Long> ticks =
            Flux.interval(Duration.ofMinutes(30));

    void verifyTicks() {
        StepVerifier.withVirtualTime(() -> ticks)
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(30))
            .expectNext(0L)
            .verifyComplete();
    }
}
~~~

**Đây là phản ví dụ, không nên chạy như test chuẩn.** Vấn đề là **ticks** đã chứa timed operator tạo ngoài phạm vi virtual-time setup. Không nên chữa bằng cách thay expectNoEvent thành thenAwait hoặc tăng timeout chờ.

**Cách sửa thứ nhất — factory method tạo Publisher mới:**

~~~java
class BetterExample {
    Flux<Long> ticks() {
        return Flux.interval(Duration.ofMinutes(30));
    }

    void verifyTicks() {
        StepVerifier.withVirtualTime(this::ticks)
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(30))
            .expectNext(0L)
            .thenCancel()
            .verify();
    }
}
~~~

**Cách sửa thứ hai — tạo trực tiếp trong lambda:**

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMinutes(30)).take(3))
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(30))
    .expectNext(0L)
    .thenAwait(Duration.ofMinutes(30))
    .expectNext(1L)
    .thenAwait(Duration.ofMinutes(30))
    .expectNext(2L)
    .verifyComplete();
~~~

Trong cách thứ nhất, Flux.interval là **vô hạn**, nên dùng thenCancel() sau khi xác nhận giá trị cần thiết. Ở cách thứ hai, take(3) giúp stream hoàn tất sau giá trị 2L.

### Mono.defer có giải quyết được không?

**Mono.defer** hoặc **Flux.defer** dời thời điểm gọi factory tới **subscription**:

~~~java
Mono<Long> safelyDeferred =
        Mono.defer(() -> Mono.delay(Duration.ofHours(5)));
~~~

Bản thân đối tượng Mono.defer có thể tạo trước, nhưng **Mono.delay được dựng khi subscribe**, nên có cơ hội chọn virtual scheduler đang active. Tuy nhiên:

- Nếu lambda bên trong chỉ trả một Publisher tạo sẵn, defer **không sửa** việc operator đã capture Scheduler trước đó.
- Nếu dùng scheduler custom đã tạo trước hoặc một HTTP client dựa vào clock thật, defer **không virtualize** công việc ấy.
- Với **StepVerifier.withVirtualTime**, cách dễ đọc nhất vẫn là **Supplier tạo đầy đủ pipeline cần test**, không dựa vào mẹo defer để che việc assembly sớm.
- Khi API/service cần luôn trả một publisher được xây sẵn, defer là một lựa chọn hợp lý **sau khi** hiểu nó tạo những operator nào lúc subscription.

Đừng nhầm **lazy assembly trong Supplier** và **lazy subscription trong Mono.defer**. Cả hai liên quan thời điểm tạo, nhưng ở những lớp API khác nhau.

## 6. Ví dụ chạy được: Java 17 + Spring Boot 3.4.5 + Reactor Test

Dự án nhỏ không yêu cầu web server, database hoặc Testcontainers. Nó dùng Reactor Core cho luồng nghiệp vụ, Reactor Test cho StepVerifier và JUnit Jupiter cho test. Spring Boot cung cấp dependency management và một Spring bean để minh họa tình huống test service trong context.

**Hợp đồng của TimedStreamService:**

1. **delayed(value, wait)** phát value sau khoảng wait dương.
2. **ticks(period, count)** phát các số từ 0L đến count-1 theo chu kỳ period dương rồi complete; count phải lớn hơn 0.
3. **timeoutFallback(timeout)** nguồn never() phải trả "fallback" khi hết timeout.
4. **retryTwice(operation, wait)** thực thi lại một operation tối đa hai lần sau mỗi khoảng wait cố định; khi lần thứ ba thành công thì phát "ok".

Hợp đồng này cho test dễ xác minh thứ tự onNext và thời điểm. Không trộn logic bên ngoài như HTTP client hoặc sleep để tránh độ trễ ngẫu nhiên.

### 6.1. Cây tệp

~~~text
settings.gradle
build.gradle
src/main/java/com/example/virtualtime/VirtualTimeApplication.java
src/main/java/com/example/virtualtime/TimedStreamService.java
src/test/java/com/example/virtualtime/TimedStreamServiceTest.java
src/test/java/com/example/virtualtime/TimedStreamSpringContextTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'reactor-virtual-time-learning'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'io.projectreactor:reactor-core'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Giữ Reactor Core và reactor-test theo BOM của Spring Boot để hạn chế lệch version. **reactor-test** chỉ cần trong test classpath, không phải implementation dependency của production service. Reactor virtual time có thể dùng mà không cần khởi động Spring context; vì vậy các unit tests dưới đây không có @SpringBootTest trừ bài test wiring riêng.

**src/main/java/com/example/virtualtime/VirtualTimeApplication.java**

~~~java
package com.example.virtualtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VirtualTimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(VirtualTimeApplication.class, args);
    }
}
~~~

**src/main/java/com/example/virtualtime/TimedStreamService.java**

~~~java
package com.example.virtualtime;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class TimedStreamService {
    public Mono<String> delayed(String value, Duration wait) {
        positive(wait);
        Objects.requireNonNull(value, "value");
        return Mono.delay(wait).map(ignored -> value);
    }

    public Flux<Long> ticks(Duration period, int count) {
        positive(period);
        if (count <= 0) {
            throw new IllegalArgumentException("count must be positive");
        }
        return Flux.interval(period).take(count);
    }

    public Mono<String> timeoutFallback(Duration timeout) {
        positive(timeout);
        return Mono.<String>never()
                .timeout(timeout)
                .onErrorResume(TimeoutException.class,
                        ignored -> Mono.just("fallback"));
    }

    public Mono<String> retryTwice(
            Supplier<Mono<String>> operation, Duration wait) {
        Objects.requireNonNull(operation, "operation");
        positive(wait);
        return Mono.defer(operation)
                .retryWhen(Retry.fixedDelay(2, wait));
    }

    private static void positive(Duration value) {
        Objects.requireNonNull(value, "duration");
        if (value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(
                    "duration must be positive");
        }
    }
}
~~~

**Tại sao implementation có thể test bằng virtual time?** Mỗi lần gọi delayed, ticks, timeoutFallback hoặc retryTwice, method tạo một **Publisher mới** với operator thời gian tương ứng. Test **gọi method trong Supplier của withVirtualTime**, để các operator ấy được dựng sau khi Reactor virtual scheduler được thiết lập.

**Cần phân biệt:** kiểm tra value, duration và count ở thân Java chạy ngay lúc **assembly**, còn các tín hiệu Mono/Flux phát ở **subscription**. Một service muốn chuẩn hóa lỗi input thành onError signal thay vì throw lúc assembly có thể dùng Mono.defer/Mono.error theo contract riêng; ví dụ chọn throw trực tiếp vì mục tiêu là clock.

### 6.2. Unit test đầy đủ, không khởi động Spring context

**src/test/java/com/example/virtualtime/TimedStreamServiceTest.java**

~~~java
package com.example.virtualtime;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TimedStreamServiceTest {
    private final TimedStreamService service = new TimedStreamService();

    @Test
    void createsMonoAfterVirtualClockActivation() {
        StepVerifier.withVirtualTime(() ->
                        service.delayed("ready", Duration.ofDays(1)))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(23))
                .thenAwait(Duration.ofHours(1))
                .expectNext("ready")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void emitsThreeTicksAtExpectedVirtualInstants() {
        StepVerifier.withVirtualTime(() ->
                        service.ticks(Duration.ofMinutes(30), 3))
                .expectSubscription()
                .thenAwait(Duration.ofMinutes(30))
                .expectNext(0L)
                .thenAwait(Duration.ofMinutes(30))
                .expectNext(1L)
                .thenAwait(Duration.ofMinutes(30))
                .expectNext(2L)
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void timesOutAndUsesFallbackAfterFiveMinutes() {
        StepVerifier.withVirtualTime(() ->
                        service.timeoutFallback(Duration.ofMinutes(5)))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(4))
                .thenAwait(Duration.ofMinutes(1))
                .expectNext("fallback")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void retriesTwiceWithoutWaitingTwentyRealMinutes() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                        service.retryTwice(() -> {
                            int current = attempts.incrementAndGet();
                            if (current < 3) {
                                return Mono.error(
                                        new IllegalStateException("busy"));
                            }
                            return Mono.just("ok");
                        }, Duration.ofMinutes(10)))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(10))
                .thenAwait(Duration.ofMinutes(10))
                .expectNext("ok")
                .expectComplete()
                .verify(Duration.ofSeconds(5));

        assertEquals(3, attempts.get());
    }

    @Test
    void verifiesAStreamThatIsNotFinite() {
        StepVerifier.withVirtualTime(() ->
                        reactor.core.publisher.Flux.interval(
                                Duration.ofHours(1)))
                .expectSubscription()
                .thenAwait(Duration.ofHours(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

**Giải thích từng test:**

- **createsMonoAfterVirtualClockActivation**: service method được gọi **bên trong Supplier**. Trong 23 giờ ảo không có onNext/onComplete, sau thêm một giờ có ready và complete.
- **emitsThreeTicksAtExpectedVirtualInstants**: Flux.interval ban đầu đợi một period trước emission đầu; vì vậy kỳ vọng 0L ở phút 30, 1L ở phút 60, 2L ở phút 90. **take(3)** khiến stream tự complete.
- **timesOutAndUsesFallbackAfterFiveMinutes**: Mono.never không phát tín hiệu; timeout operator dùng virtual clock để sinh TimeoutException, onErrorResume chuyển thành fallback tại mốc năm phút ảo.
- **retriesTwiceWithoutWaitingTwentyRealMinutes**: Mono.defer(operation) bảo đảm Supplier operation được gọi lại **mỗi lần subscription/retry**. AtomicInteger chứng minh đúng ba lượt, Retry.fixedDelay(2, 10 phút) tạo hai lần chờ, tổng 20 phút ảo.
- **verifiesAStreamThatIsNotFinite**: Flux.interval không kết thúc, nên sau hai giá trị test **thenCancel** thay vì chờ completion không thể xuất hiện.

**verify(Duration.ofSeconds(5))** là **giới hạn thời gian thực** của mỗi phép verify để một lỗi scheduling không khiến test treo mãi. Nó không yêu cầu các publisher mất đúng năm giây; thời gian ảo đã được advance bên trong StepVerifier. Tùy tài nguyên máy/CI, có thể chọn timeout thực tế khác mà không thay đổi Duration nghiệp vụ.

### 6.3. Spring context test: bean có sẵn nhưng Publisher tạo muộn

**src/test/java/com/example/virtualtime/TimedStreamSpringContextTest.java**

~~~java
package com.example.virtualtime;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import reactor.test.StepVerifier;

@SpringBootTest
class TimedStreamSpringContextTest {
    @Autowired
    private TimedStreamService service;

    @Test
    void springBeanCreatesPipelineInsideSupplier() {
        StepVerifier.withVirtualTime(() ->
                        service.delayed("spring-ready", Duration.ofHours(8)))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(7))
                .thenAwait(Duration.ofHours(1))
                .expectNext("spring-ready")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

Spring đã tạo **service bean** trước khi test chạy, nhưng **publisher chỉ được tạo khi method delayed được gọi trong Supplier**. Đây là sự khác biệt giữa **bean lifecycle** và **pipeline assembly**. Vì test chỉ xác nhận Reactor operator, dùng unit test thuần Java vẫn là lựa chọn nhanh; @SpringBootTest chỉ cần khi muốn bảo vệ Spring wiring.

### 6.4. Cách chạy và kỳ vọng

Dùng Gradle Wrapper phù hợp với Java 17 và Boot 3.4.x. Trên Linux/macOS:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.virtualtime.TimedStreamServiceTest
./gradlew test --tests com.example.virtualtime.TimedStreamSpringContextTest
~~~

Trên Windows: thay **./gradlew** bằng **gradlew.bat** với cùng tham số. Các phép kiểm được thiết kế để **PASS** nếu tệp/dependency đúng như mẫu. Đây là kỳ vọng từ code, **không phải stdout của một bản build đã chạy thực tế**.

Bạn không cần để máy thật chờ 1 ngày, 90 phút hay 20 phút. Reactor Test tiến clock ảo trong lúc xác minh. Nhưng việc tải Gradle dependency, khởi động Spring context và chạy JUnit vẫn tiêu tốn thời gian thực.

## 7. Trường hợp Spring bean giữ publisher trong field: lỗi khó phát hiện

Giả sử một Spring service được thiết kế như sau:

~~~java
@Service
class ScheduledMessageService {
    private final Mono<String> cachedPipeline =
            Mono.delay(Duration.ofHours(24))
                .map(ignored -> "sent");

    Mono<String> deliver() {
        return cachedPipeline;
    }
}
~~~

**Đây là phản ví dụ**, không thuộc project runnable của phần 6. Bean được Spring dựng trong startup, trước khi test gọi withVirtualTime. **cachedPipeline** có thể đã chọn scheduler thật lúc assembly. Viết:

~~~java
StepVerifier.withVirtualTime(service::deliver)
    .expectSubscription()
    .thenAwait(Duration.ofHours(24))
    .expectNext("sent")
    .verifyComplete();
~~~

vẫn sai về mặt timing vì method deliver không tạo operator mới. Supplier chỉ trả **cùng một cachedPipeline**.

**Sửa theo factory method:**

~~~java
@Service
class ScheduledMessageService {
    Mono<String> deliver() {
        return Mono.delay(Duration.ofHours(24))
                .map(ignored -> "sent");
    }
}
~~~

Khi test gọi service::deliver trong withVirtualTime, timed operator được tạo sau setup. Một service được autowire trước đó **không phải** vấn đề nếu nó **không dựng sẵn timed operator** ở field hoặc constructor.

**Nếu buộc giữ một Publisher field:** cân nhắc **Mono.defer(() -> Mono.delay(...))** để tạo timed operator tại subscription, hoặc thiết kế Scheduler/Clock injection rõ ràng. Tuy nhiên, phải review toàn bộ chain; nếu một operator khác đã chụp scheduler ngoài scope thì chưa giải quyết xong.

## 8. Giới hạn của VirtualTimeScheduler: không phải đồng hồ của cả JVM

**VirtualTimeScheduler** chủ yếu kiểm soát các task được lên lịch lên nó. Reactor Test sử dụng cơ chế hook/factory để những Scheduler Reactor mặc định dùng trong timed operators được thay bằng virtual scheduler trong phạm vi kiểm thử. Nhưng nó **không sửa đồng hồ hệ điều hành**, không làm Thread.sleep, Socket.timeout, JDBC driver, random external I/O hoặc java.time.Instant.now() chạy nhanh hơn.

Ví dụ:

~~~java
Mono<String> notVirtualized = Mono.fromSupplier(
        () -> java.time.Instant.now().toString());
~~~

Mono này lấy thời gian wall-clock khi subscribe; thenAwait không khiến Instant.now tự tăng một ngày so với thời gian hệ điều hành. Nếu nghiệp vụ phụ thuộc ngày/giờ, nên **inject java.time.Clock** rồi dùng Clock.fixed hoặc Clock.offset trong unit test. Reactor virtual time và domain Clock là **hai loại đồng hồ khác nhau**.

### Scheduler custom tạo trước không được thay thế tự động

~~~java
Scheduler realScheduler = Schedulers.newSingle("dedicated-real");

try {
    Mono<Long> timer = Mono.delay(
            Duration.ofHours(3), realScheduler);

    // Đừng tin rằng thenAwait(3h) sẽ điều khiển timer này.
} finally {
    realScheduler.dispose();
}
~~~

Đoạn này là **minh họa**, cần import reactor.core.scheduler.Scheduler và Schedulers; nó không thuộc dự án runnable. Scheduler do newSingle tự tạo là tài nguyên cần dispose. Nếu một operator dùng dedicated scheduler hoặc executor không thuộc Reactor factory được virtualize, Supplier tạo pipeline muộn vẫn không bảo đảm thời gian ảo.

Muốn kiểm thử dependency sử dụng custom scheduler, có thể thiết kế **Scheduler injection** và cung cấp VirtualTimeScheduler trong test, hoặc kiểm thử với real scheduler có timeout ngắn và expectation phù hợp. Chọn chiến lược dựa trên contract, không gắn nhãn “virtual time” cho một tác vụ không có liên hệ với virtual clock.

### Thứ tự schedule trong flatMap và operator lồng

Có pipeline chỉ tạo timer **sau khi một onNext khác xuất hiện**, ví dụ delay nằm trong flatMap. Nếu bạn gọi thenAwait trước khi timer con được lập lịch, virtual clock có thể nhảy quá một mốc mà timer con mới bắt đầu đếm từ **thời điểm đã bị nhảy tới**, dẫn đến kết quả không xuất hiện như kỳ vọng. Javadoc StepVerifier cũng cảnh báo về những nguồn lập lịch trên scheduler khác và delay được tạo **bên trong data path**.

Hãy sắp xếp assertion và advance clock theo từng giai đoạn: xác nhận upstream emission, sau đó mới advance thời gian cho timer được tạo bởi emission ấy. Nếu logic có nhiều scheduler/concurrency nhánh, đôi khi dùng một test riêng kiểm tra scheduling với VirtualTimeScheduler tường minh sẽ rõ ràng hơn.

## 9. Flux.interval, backpressure và stream vô hạn

**Flux.interval(period)** theo mặc định phát giá trị đầu **0L sau khoảng period đầu**, không phát 0L ngay t=0. Khi dùng virtual time:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMinutes(15)).take(2))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(14))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext(0L)
    .thenAwait(Duration.ofMinutes(15))
    .expectNext(1L)
    .verifyComplete();
~~~

Đây là trích đoạn đặt trong một JUnit test có import Flux, Duration, StepVerifier. Nó bảo vệ cả **không phát sớm** và **đúng chu kỳ**.

Nếu kiểm tra một interval vô hạn mà yêu cầu **verifyComplete**, test không bao giờ nhận onComplete (trừ khi có take, timeout hoặc operator kết thúc khác). Dùng **take(n)** nếu nghiệp vụ giới hạn phần tử, hoặc **thenCancel()** nếu muốn xác nhận một đoạn rồi hủy subscription.

Với StepVerifier.withVirtualTime(supplier, 0), lượng request ban đầu bằng 0. Một source như Flux.interval có thể báo lỗi backpressure nếu tới mốc emission mà chưa có demand. Hãy **thenRequest(n)** trước khi advance virtual time, hoặc giữ default request nếu test không nhằm khảo sát backpressure. Đừng diễn giải overflow khi test cố tình không request như lỗi timer.

## 10. Retry, jitter và sai số thời gian

**Retry.fixedDelay(2, Duration.ofMinutes(10))** retry tối đa hai lần, mỗi lần chờ 10 phút. Khi operation thành công ở lần subscribe thứ ba, StepVerifier có thể tua clock tổng cộng 20 phút để nhận "ok". Đây là hành vi của test example ở phần 6.

**Retry.backoff(...)** có đặc tính backoff tăng dần và có thể thêm **jitter ngẫu nhiên**. Với test cần assert mốc chính xác, dùng fixedDelay hoặc cấu hình jitter có chủ ý theo API version hiện tại (ví dụ .jitter(0d)) và kiểm tra quy tắc backoff. Tránh assert một số giây cố định nếu production code đang cố tình có jitter.

Không nên tạo và **subscribe operation** trước withVirtualTime chỉ để tạo dữ liệu cho test, vì lần subscribe đó đã có thể chạy retry/timer thật. Nếu số lần retry quan trọng, dùng AtomicInteger đếm số lần Supplier operation được gọi hoặc fake có ghi nhận; nhớ phân biệt **số lần subscribe** với **số lần tạo object Mono**.

## 11. Virtual time và test song song, tài nguyên dùng chung

Reactor virtual time liên quan cơ chế thay thế Scheduler dùng chung của Reactor trong khoảng kiểm thử. Vì vậy hai test cùng thao tác scheduler factory ở những thread khác nhau, hoặc một test chạy job real-time đúng lúc test khác bật virtual time, có thể làm kết quả phụ thuộc scheduling/CI.

Hướng xử lý thực tế:

- Tránh để virtual-time tests chạy parallel với nhau hoặc với tests đang dựa vào cùng Reactor Schedulers mặc định, trừ khi bạn có chiến lược isolation được kiểm chứng.
- Không tự gọi Schedulers.resetFactory(), resetFactoryWithSnapshot(...) hoặc VirtualTimeScheduler.getOrSet() giữa lúc một verify khác đang chạy để “chữa” test.
- Đừng giữ VirtualTimeScheduler/Flux/Mono chứa timed operator trong static mutable field chia sẻ xuyên suite.
- Ưu tiên mỗi test tự tạo publisher trong Supplier và để StepVerifier quản lý lifecycle virtual scheduler; nếu thao tác thủ công với scheduler global, cần cleanup rõ và không xung đột với thread khác.
- Khi test dùng Spring context cache, nhớ **bean singleton được tái sử dụng**, nên publisher cache bên trong bean có thể được assembly sớm ngay từ khi context khởi tạo; đừng nhầm test instance PER_METHOD mới với pipeline đã được tái tạo.
- Nếu test dùng parallel threads, controlled real-time scheduler hoặc không đồng bộ toàn bộ suite, cần quản lý chính sách test concurrency ở build/JUnit chứ không chỉ đổi thứ tự test.

Bản thân StepVerifier không bảo đảm **mọi** code reactive trong JVM đang dùng cùng virtual clock. Nó chỉ điều khiển những operator thực sự schedule lên scheduler được hook.

## 12. Tránh deadlock hoặc test chờ vĩnh viễn

Một số cách viết khiến clock không tiến hoặc không có tín hiệu:

**A. Đợi onNext trước khi advance time.**

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1)))
    .expectNext(0L) // Chờ giá trị cần 1 giờ ảo, nhưng chưa tua clock.
    .verifyComplete();
~~~

Đây là **phản ví dụ**. ExpectNext đang chờ sự kiện sẽ chỉ xuất hiện khi clock chạy qua một giờ. Sửa bằng **expectSubscription().thenAwait(Duration.ofHours(1))** trước khi expectNext.

**B. Tạo interval trong flatMap sau khi đồng hồ đã advance quá xa.** Timer con có thể lên lịch khi virtual time đã ở mốc mới, khiến thời điểm tính khác dự kiến. Cần hiểu thứ tự onNext → inner subscription → scheduler registration.

**C. Trộn Thread.sleep/blocking call vào Reactor event-loop/virtual scheduler.** VirtualTimeScheduler không thực thi sleep nhanh, và nếu blocking làm nghẽn thread đang cần thực thi verify thì test có thể deadlock. Không dùng block() bên trong một operator đang đợi chính clock mà test cần advance.

**D. Tạo publisher trước withVirtualTime.** Đây là lỗi chính của bài: scheduler có thể đã được captured theo real time. Cần xây lại publisher trong Supplier, không chỉ tăng thời gian test.

**E. Quên terminal expectation.** Flux.interval vô hạn sẽ không complete. Dùng thenCancel hoặc take. Nếu một test cố verifyComplete vô hạn, lỗi nằm ở hợp đồng hoàn tất chứ không nhất thiết ở Reactor virtual-time infrastructure.

**F. Không giới hạn thời gian thực khi verify.** Dù virtual time giúp tua nhanh, một bug có thể khiến test chờ mãi. .expectComplete().verify(Duration.ofSeconds(5)) tạo giới hạn thực tế và trả lỗi sớm; con số có thể điều chỉnh theo CI.

## 13. Dấu hiệu và cách chẩn đoán nhanh

| Triệu chứng | Kiểm tra trước | Cách sửa |
| --- | --- | --- |
| thenAwait(1 ngày) mà test vẫn chờ thật | Publisher/Mono.delay có được tạo trước Supplier? | Tạo time-based operator trong lambda |
| Supplier chỉ viết () -> cachedMono | cachedMono được assembly ở bean field/constructor? | Dùng method factory hoặc Mono.defer đúng cách |
| Test không bao giờ có onNext | Đã advance time trước expectNext? | thenAwait/expectNoEvent đúng thứ tự |
| expectNoEvent bước đầu thất bại | Subscription cũng là event | Đặt expectSubscription trước |
| Flux.interval kỳ vọng 0L ngay khi subscribe | Interval đầu tiên chỉ phát sau period | Advance một period trước expectNext(0L) |
| Stream vô hạn không complete | Không có take hoặc terminal condition | thenCancel hoặc thêm take(n) |
| Test thấy giá trị wall-clock không đổi | Dùng Instant.now/System.currentTimeMillis | Inject Clock riêng, không nhầm với VirtualTimeScheduler |
| Test có custom Scheduler real | Operator dùng Schedulers.newSingle/executor ngoài hook | Scheduler injection hoặc real-time test |
| Retry timing không ổn định | Retry.backoff có jitter | fixedDelay hoặc thiết lập jitter theo contract |
| Virtual test fail khi chạy suite | Tests khác can thiệp global Scheduler factory hoặc shared bean pipeline | Isolate test concurrency và publisher assembly |
| Timeout ở verify(Duration) | Không có signal, thiếu request hoặc chưa schedule | Soát demand, assembly time, clock advancement |
| Test xanh nhưng thực tế HTTP timeout sai | Virtual time chỉ kiểm tra Reactor operator | Bổ sung integration HTTP/server timeout test |
| Expect giá trị sai dù timer đúng | Side effect thực thi ở assembly ngoài Supplier | Dời cả chain/side effect cần test vào đúng scope |

Một cách debug hữu ích là in **cấu trúc pipeline** lúc tạo và xem **scheduler xuất hiện ở đâu** (field, constructor, static initializer, inside flatMap, custom scheduler). Chú ý đừng biến log thời gian thực thành assertion bắt buộc: log scheduling có thể khác theo môi trường.

## 14. Chiến lược lựa chọn loại test

**Unit test với StepVerifier.withVirtualTime** phù hợp cho deadline, delay, timeout, retry, interval, heartbeat và một số chính sách thời gian. Mục tiêu là xác định chính xác **tín hiệu onNext/onError/onComplete** khi virtual clock tiến.

**Spring context test** cần thiết khi wiring/configuration quyết định pipeline được tạo/subscribe theo cách nào. Nếu service được inject và có timed publisher field, test context có thể phơi bày lỗi assembly sớm mà unit test tạo service mới chưa phản ánh.

**HTTP/WebFlux integration test** cần khi hợp đồng bao gồm status/body, serialization, filter, route, backpressure kết nối, streaming, server timeout và client disconnect. Một StepVerifier unit test xanh **không** chứng minh những lớp đó.

**Test scheduler/Clock injection** phù hợp khi application dùng custom Scheduler hoặc domain wall-clock. Chỉ dùng virtual time nếu từng operator thực sự dựa vào scheduler được nó điều khiển; không áp dụng gượng ép cho external timers và I/O.

### Tự kiểm tra

**1.** Mono.delay được tạo ở field trước test, vớiVirtualTime nhận () -> field. Có bảo đảm chạy virtual clock không? **Không**: timed operator có thể đã capture scheduler thật.

**2.** Bean Spring đã khởi tạo trước test, nhưng method delayed() luôn tạo Mono.delay mới, test dùng () -> service.delayed(...). Có đúng không? **Đúng**, vì pipeline được assembly trong supplier.

**3.** expectNoEvent là bước đầu tiên và thất bại ngay. Vì sao? **Subscription cũng là event**; phải expectSubscription trước.

**4.** thenAwait(10 phút) trên Flux.interval(10 phút) có thể cho giá trị đầu gì? **0L**, nếu timer được schedule đúng và đã có demand.

**5.** Mono.defer(() -> Mono.delay(...)) tạo trước withVirtualTime có thể hữu ích không? **Có**, vì timed Mono được assembly khi subscribe; nhưng defer không chữa scheduler custom/captured ngoài lambda.

**6.** withVirtualTime làm Instant.now tiến 24 giờ ảo không? **Không**. Inject java.time.Clock nếu cần test wall-clock domain.

**7.** Một stream interval vô hạn có thể verifyComplete không? **Không**, trừ khi pipeline thêm operator kết thúc như take; cần thenCancel.

**8.** Một Retry.backoff với jitter có phù hợp assert đúng số millisecond cố định không? **Không**, trừ khi cố ý vô hiệu/kiểm soát jitter.

**9.** Test verify(Duration.ofSeconds(5)) bị timeout, có nghĩa nghiệp vụ đã hết hạn 5 giây ảo không? **Không**. Đây là giới hạn wall-clock của test runner.

### Checklist trước khi chốt QA

- Các operator theo thời gian **được tạo bên trong Supplier** của withVirtualTime?
- Service có cache publisher ở field/constructor/static initializer trước virtual setup không?
- Publisher có dùng Scheduler mặc định Reactor hay custom scheduler/Executor không được virtualize?
- StepVerifier đã expectSubscription trước expectNoEvent chưa?
- Những mốc thenAwait có đủ để timer được schedule, chạy và phát onNext?
- Có xử lý đúng số lần retry, delaySubscription, timeout và jitter theo contract?
- Flux vô hạn đã được giới hạn bằng take(n) hoặc thenCancel?
- Backpressure/demand có được request trước khi interval phát khi dùng initialRequest=0?
- Test có giới hạn verify wall-clock để không treo CI?
- Có Thread.sleep, block, I/O, Instant.now hoặc custom Clock nằm ngoài cơ chế virtual scheduler?
- Có test chạy parallel dùng shared Reactor Scheduler factory hoặc cached Spring bean không?
- Có phân biệt kết luận về Reactor signal với kết luận về HTTP/container/DB thật không?

**Kết luận:** Muốn StepVerifier.withVirtualTime thực sự điều khiển delay/interval/timeout/retry, **đừng tạo timed publisher trước rồi trả lại qua Supplier**. Hãy **tạo toàn bộ pipeline cần kiểm tra bên trong lambda Supplier**, sau đó dùng expectSubscription, expectNoEvent, thenAwait và terminal expectation để xác nhận tín hiệu. VirtualTimeScheduler tăng tốc **lịch Reactor**, không phải wall-clock, mọi thread, custom scheduler hay external I/O. Giữ pipeline lazy đúng thời điểm và giới hạn rõ bằng chứng của bài test sẽ giúp phát hiện lỗi thời gian nhanh mà không tạo flaky suite.

## Tài liệu chính thức

- Project Reactor — Testing, Manipulating Time: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test — StepVerifier Javadoc và vớiVirtualTime Supplier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test — VirtualTimeScheduler Javadoc: https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html
- Spring Boot 3.4 — Testing: https://docs.spring.io/spring-boot/3.4/reference/testing/index.html
