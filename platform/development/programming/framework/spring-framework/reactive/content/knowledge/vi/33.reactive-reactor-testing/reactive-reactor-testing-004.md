# Kiểm tra cancel và công việc dọn dẹp trong Project Reactor

## 1. Tổng quan

Một Publisher của Reactor có thể hoàn thành, phát lỗi hoặc bị **hủy subscription**. Cancellation xuất hiện trong ứng dụng Spring WebFlux khi:

- Browser đóng trang đang nghe Server-Sent Events (SSE).
- WebSocket hoặc HTTP client ngắt kết nối.
- Toán tử take(n) nhận đủ phần tử nên hủy upstream.
- timeout(...) hủy nguồn ban đầu khi hết thời gian.
- switchMap chuyển sang inner Publisher mới và hủy inner cũ.
- Consumer gọi Disposable.dispose().
- Một service bị shutdown hoặc request context không còn cần kết quả.

**Cancel không phải onComplete hay onError.** Đây là yêu cầu từ downstream gửi lên Subscription để ngừng phát thêm dữ liệu. Sau cancel, upstream được kỳ vọng giải phóng các resource thuộc subscription nhưng cancellation là cơ chế hợp tác: nó không thể bảo đảm một remote request đã được rollback hoặc một socket đã đóng tức thì.

Kiểm thử phải trả lời ít nhất bốn câu hỏi:

1. Subscription có bị cancel theo dự kiến?
2. Cancellation đã tới đúng Publisher/inner Publisher chưa?
3. Tài nguyên thật sự được release và có được release đúng một lần không?
4. Nếu cleanup bất đồng bộ hoặc lỗi, test có quan sát được kết quả không?

Bài học dùng **StepVerifier**, **PublisherProbe**, **TestPublisher**, **doOnCancel**, **doFinally**, **Flux.using**, **Flux.usingWhen**, **Mono.usingWhen**, **doOnDiscard** và virtual time.

## 2. Reactive Streams và tín hiệu cancel

~~~text
Publisher ----onSubscribe----> Subscriber
Publisher -------onNext-----> Subscriber
Publisher -----onComplete---> Subscriber
Publisher -------onError----> Subscriber

Subscriber ----request(n)----> Subscription -> upstream
Subscriber ------cancel()----> Subscription -> upstream
~~~

Subscription.request(n) cho phép nguồn phát tối đa n phần tử theo demand. Subscription.cancel() báo upstream downstream không cần dữ liệu nữa. Trong Reactive Streams, cancel là lệnh điều khiển, **không phải terminal signal được Publisher phát xuống Subscriber**.

Phải phân biệt rõ:

| Đường kết thúc | Downstream nhận | doOnComplete | doOnError | doOnCancel | doFinally |
| --- | --- | --- | --- | --- | --- |
| Thành công | onComplete | Có | Không | Không | ON_COMPLETE |
| Lỗi | onError | Không | Có | Không | ON_ERROR |
| Cancel | Không có terminal từ Publisher | Không | Không | Có, nếu đi qua hook | CANCEL |

Các toán tử điều khiển có thể chuyển nghĩa của termination ở các vị trí: take(n) có thể **cancel upstream** nhưng **complete downstream**; timeout có thể **cancel upstream** rồi **onError downstream**. Vì vậy, cần đặt hook ở **đúng đoạn luồng đang được kiểm tra**.

### 2.1. Cancel không tự hủy side effect

Một HTTP POST có thể đã được server khác commit khi client cancel. Một database driver có thể đã gửi query trước khi nhận tín hiệu cancel. Cleanup là việc đóng/giải phóng resource, không đồng nghĩa transaction đã rollback hoàn toàn hay lệnh bên ngoài chưa thực hiện.

Nếu nghiệp vụ có side effect, cần idempotency key, transaction protocol, trạng thái xử lý và reconciliation riêng.

### 2.2. Cancel thuộc subscription cụ thể

Nguồn cold thường tạo công việc mới cho từng subscriber; hủy một subscriber không hủy người khác. Nguồn shared/hot (share, replay, Sinks.Many, refCount) có nhiều subscriber: hủy client A có thể chỉ gỡ A, trong khi source vẫn phục vụ B. Khi test, chỉ rõ đang xác nhận **per-subscriber cancel** hay **upstream physical shutdown**.

## 3. doOnCancel và doFinally

### 3.1. doOnCancel

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() ->
        System.out.println("cancel requested")
    );
~~~

doOnCancel chạy khi cancel đi qua vị trí toán tử. Callback chạy trước khi Reactor chuyển cancel tiếp về upstream tại chính vị trí đó. Nó không chạy khi onComplete hoặc onError thông thường.

### 3.2. doFinally

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .doFinally(signal ->
        System.out.println("final = " + signal)
    );
~~~

doFinally quan sát SignalType.ON_COMPLETE, SignalType.ON_ERROR hoặc SignalType.CANCEL. Đây là hook phù hợp cho metrics, logging và một số cleanup đồng bộ nhẹ.

Những lưu ý quan trọng:

- Trong completion/error, callback doFinally có thể chạy **sau** khi terminal đã tới downstream. Không assert trạng thái callback ngay sau verifyComplete mà không xét race.
- Nhiều doFinally liên tiếp có thể thực thi callback theo thứ tự ngược thứ tự khai báo.
- Không đặt blocking close lâu trong doFinally trên event-loop Netty.
- Một callback doFinally gọi releaseAsync(...).subscribe() là một subscription tách rời, không làm cleanup trở thành phần được await trong pipeline.
- doOnTerminate/doAfterTerminate không bao phủ cancel.

Với resource lifecycle phức tạp, ưu tiên using/usingWhen thay vì nhiều callback tự quản lý.

## 4. StepVerifier.thenCancel() điều khiển test

**StepVerifier** là công cụ của dependency reactor-test. Nó subscribe vào Publisher, kiểm tra tín hiệu, request và chủ động cancel trong kịch bản test.

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.<Long>never()
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertTrue(cancelled.get());
~~~

Đây là snippet cần imports của Java, Reactor, reactor-test và JUnit. thenCancel là **bước điều khiển**, không phải expectation về một onCancel signal từ Publisher. Nó thường được dùng cho nguồn never() hoặc một stream đang chờ.

### 4.1. Nhận một phần rồi cancel

~~~java
StepVerifier.create(Flux.range(1, 10))
    .expectNext(1, 2, 3)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

Sau khi nhận 1, 2, 3, verifier hủy subscription. Với source đồng bộ nhanh, không dùng ví dụ này để kết luận socket hoặc I/O đã dừng chính xác tại một thời điểm.

### 4.2. Kiểm soát demand

~~~java
StepVerifier.create(Flux.range(1, 10), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

Initial request=0 cho phép khởi tạo không demand. thenRequest(2) cấp demand đúng hai phần tử. Nếu quên thenRequest trước expectNext, test có thể chờ vô hạn.

### 4.3. Trần thời gian

verify(Duration) đặt timeout thực cho toàn kịch bản, tránh CI bị treo bởi nguồn không terminate. Không có thenCancel hoặc terminal expectation tương ứng, Flux.never() sẽ không kết thúc.

**thenCancel PASS chỉ chứng minh hành động cancel đã được thực thi.** Cần kiểm tra thêm cleanup hoặc probe để xác minh tác động mong muốn.

## 5. PublisherProbe kiểm tra upstream

**PublisherProbe** instrument một Publisher để biết nó đã được subscribe, request và cancel hay chưa.

~~~java
PublisherProbe<Long> probe =
    PublisherProbe.of(Flux.<Long>never());

StepVerifier.create(probe.flux())
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));

probe.assertWasSubscribed();
probe.assertWasRequested();
probe.assertWasCancelled();
~~~

Các assertion hữu ích gồm:

| Assertion | Ý nghĩa |
| --- | --- |
| assertWasSubscribed() | Có subscriber |
| assertWasNotSubscribed() | Không được subscribe |
| assertWasRequested() | Có request demand |
| assertWasNotRequested() | Không thấy request |
| assertWasCancelled() | Có cancel |
| assertWasNotCancelled() | Không thấy cancel |

Probe không xác nhận tài nguyên như network socket, file descriptor hoặc DB connection đã được đóng. Nó chỉ kiểm tra contract Publisher tại điểm instrument.

### 5.1. Đặt probe ở nguồn cần chứng minh

~~~java
PublisherProbe<Integer> source =
    PublisherProbe.of(Flux.range(1, 100));

Flux<Integer> firstTwo = source.flux().take(2);
~~~

Nếu muốn biết take(2) có cancel Publisher gốc hay không, probe phải bọc **source**, không chỉ bọc downstream của take. Tương tự, đặt probe quanh inner Publisher khi kiểm tra switchMap/flatMap.

### 5.2. assertWasNotCancelled không luôn mang nghĩa xấu

Nếu Mono.just("ok") hoàn tất tự nhiên, source không cần cancel. Ngược lại, trong timeout hoặc take(n), downstream có thể hoàn tất hợp lệ nhưng upstream vẫn bị cancel. Phải đánh giá theo vị trí hook và contract của operator.

## 6. Cancel do take, timeout và switchMap

### 6.1. take(n)

~~~java
Flux<Integer> source = Flux.range(1, 10)
    .doFinally(signal ->
        System.out.println("upstream = " + signal)
    );

Flux<Integer> result = source.take(2)
    .doFinally(signal ->
        System.out.println("downstream = " + signal)
    );
~~~

take(2) chỉ nhận đủ hai phần tử; sau đó có thể gửi cancel upstream vì không cần tám phần tử còn lại và phát onComplete downstream. Hai hook có thể nhận SignalType khác nhau: upstream CANCEL, downstream ON_COMPLETE.

### 6.2. timeout

~~~java
Mono<String> source = Mono.<String>never()
    .doFinally(signal ->
        System.out.println("source = " + signal)
    );

Mono<String> result = source
    .timeout(Duration.ofSeconds(5))
    .doFinally(signal ->
        System.out.println("result = " + signal)
    );
~~~

Timeout hủy source, còn downstream nhận TimeoutException. Nếu timeout có fallback Publisher, downstream có thể hoàn tất sau fallback; test cả việc cancel source và subscribe fallback.

### 6.3. switchMap và prefetch

switchMap hủy inner Publisher cũ khi item mới tới; flatMap có thể hủy nhiều inner Publisher khi downstream cancel. Operator còn có thể chứa các item đã prefetch trong queue. Một phần các item này cần **discard cleanup**.

Không giả định số lượng item bị discard cố định dưới concurrency khác nhau. Kiểm tra invariant tài nguyên thay vì phụ thuộc timing của Scheduler.

## 7. Flux.using: resource cleanup đồng bộ

Flux.using tạo resource cho mỗi subscription, tạo Publisher sử dụng resource, rồi cleanup khi complete, error hoặc cancel.

~~~java
Flux<String> flow = Flux.using(
    () -> openResource(),
    resource -> readEvents(resource),
    resource -> closeResource(resource)
);
~~~

Các phương thức trong snippet này là API giả định của ứng dụng. Nó mô tả ownership và cách Reactor kết nối cleanup với lifecycle.

### 7.1. Ví dụ AutoCloseable

~~~java
final class TestLease implements AutoCloseable {

    private final AtomicInteger closeCount;

    TestLease(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    @Override
    public void close() {
        closeCount.incrementAndGet();
    }
}
~~~

~~~java
AtomicInteger closed = new AtomicInteger();

Flux<Integer> stream = Flux.using(
    () -> new TestLease(closed),
    lease -> Flux.<Integer>never(),
    TestLease::close
);

StepVerifier.create(stream)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertEquals(1, closed.get());
~~~

Resource được đóng đúng một lần trong kịch bản này. Đừng mở resource trước khi tạo Flux rồi vô tình để nhiều subscriber cùng đóng một connection.

### 7.2. Eager và non-eager

Flux.using có overload cho boolean eager. Khi eager=true, trong nhánh complete/error, cleanup thực hiện trước khi phát terminal xuống downstream; lỗi cleanup có thể ảnh hưởng terminal. Với non-eager, cleanup sau terminal, lỗi cleanup có thể bị drop. Cancel không gửi downstream terminal nên cần test bằng counter/latch.

## 8. Flux.usingWhen và Mono.usingWhen: cleanup bất đồng bộ

Dùng **usingWhen** khi release trả Publisher, ví dụ R2DBC connection.close(), rollback hoặc một async lease manager.

~~~java
Flux.usingWhen(
    resourceSupplier,
    resource -> useResource(resource),
    resource -> asyncComplete(resource),
    (resource, error) -> asyncError(resource, error),
    resource -> asyncCancel(resource)
);
~~~

| Nhánh useResource | Cleanup |
| --- | --- |
| Complete | asyncComplete |
| Error | asyncError |
| Cancel | asyncCancel |

Không gọi cleanupPublisher.subscribe() rồi trả Mono.empty() nếu cần usingWhen điều phối hoàn tất/lỗi cleanup. Trả trực tiếp Publisher cleanup.

### 8.1. Kiểm tra asyncCancel

~~~java
AtomicInteger cancelled = new AtomicInteger();
CountDownLatch latch = new CountDownLatch(1);

Flux<Integer> flow = Flux.usingWhen(
    Mono.just("lease-1"),
    lease -> Flux.<Integer>never(),
    lease -> Mono.empty(),
    (lease, error) -> Mono.empty(),
    lease -> Mono.fromRunnable(() -> {
        cancelled.incrementAndGet();
        latch.countDown();
    })
);

StepVerifier.create(flow)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertTrue(latch.await(2, TimeUnit.SECONDS));
assertEquals(1, cancelled.get());
~~~

Snippet cần test method throws InterruptedException. CountDownLatch giúp đợi cleanup có thể chạy trên Scheduler khác. Cancel có thể xảy ra trước khi asyncCancel Publisher hoàn tất; một verify cancel đơn thuần không nhất thiết chờ mọi cleanup độc lập.

### 8.2. Test đủ ba nhánh

- Khi source complete, asyncComplete phải chạy đúng một lần.
- Khi source error, asyncError nhận đúng Throwable.
- Khi downstream cancel, asyncCancel chạy.
- Khi cleanup tự phát lỗi, test outcome theo semantics của Flux/Mono.usingWhen.

Với Mono.usingWhen, một giá trị thành công có thể được giữ lại cho tới khi cleanup thành công; nếu cleanup lỗi, giá trị có thể bị discard và downstream nhận onError. Không nuốt lỗi release vô điều kiện, nhất là với transaction hoặc connection pool.

## 9. Discarded elements khác dropped signals

**Discarded** là phần tử bị một operator bỏ trong luồng hợp lệ, ví dụ filter loại một item hoặc queue prefetch bị clear khi cancel. **Dropped** là tín hiệu không thể tiếp tục được truyền theo contract, ví dụ nguồn sai phát onNext sau terminal. Hai khái niệm có hook và cách kiểm tra khác nhau.

### 9.1. doOnDiscard

~~~java
Flux<Buffer> accepted = source
    .filter(Buffer::isWanted)
    .doOnDiscard(Buffer.class, Buffer::release);
~~~

Đây là snippet minh họa, cần Buffer và source cụ thể của ứng dụng.

Hook doOnDiscard áp dụng với các operator hỗ trợ **Discard Support** trong Javadoc và được đặt downstream so với các operator cần dọn. Callback release cần idempotent, đặc biệt với DataBuffer/ByteBuf reference-counted.

Không dùng Hooks.onNextDropped để thay cho doOnDiscard của filter hoặc queue.

### 9.2. verifyThenAssertThat

~~~java
StepVerifier.create(
        Flux.just(1, 2, 3, 4)
            .filter(n -> n % 2 == 0)
    )
    .expectNext(2, 4)
    .expectComplete()
    .verifyThenAssertThat()
    .hasDiscardedExactly(1, 3);
~~~

StepVerifier Assertions có các method hasDiscardedExactly, hasDiscardedElements, hasNotDiscardedElements, hasDroppedExactly và hasDroppedElements. Chọn đúng loại dữ liệu muốn kiểm tra.

## 10. TestPublisher và virtual time

### 10.1. Điều khiển nguồn bằng TestPublisher

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .expectSubscription()
    .then(() -> source.next("one"))
    .expectNext("one")
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

TestPublisher giúp emit item từ test đúng thời điểm, thay vì ngủ chờ timer và hy vọng test đến đúng pha.

### 10.2. Timeout năm phút không cần đợi năm phút thật

~~~java
PublisherProbe<String> probe =
    PublisherProbe.of(Mono.<String>never());

StepVerifier.withVirtualTime(() ->
        probe.mono().timeout(Duration.ofMinutes(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(5))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));

probe.assertWasCancelled();
~~~

Tạo operator dùng Scheduler bên **trong lambda** withVirtualTime. thenAwait tiến clock ảo; verify(Duration) giữ một trần real-time. Virtual time không mô phỏng thread sleep, socket I/O hoặc scheduler bên ngoài đã được tạo riêng.

## 11. Dự án Maven Java 17 chạy được

Bộ test dưới đây dùng **reactor-core 3.8.8**, **reactor-test 3.8.8** và **JUnit Jupiter 5.12.2**. Reactor 3.8.8 là release ổn định vào tháng 10/2026. Không cần Spring Boot runtime vì mục tiêu là kiểm thử trực tiếp các operator mà Spring WebFlux sử dụng.

Cấu trúc:

~~~text
reactor-cancel-cleanup-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── com/example/reactortests/
                └── CancellationAndCleanupTest.java
~~~

### 11.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-cancel-cleanup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.2. CancellationAndCleanupTest.java

~~~java
package com.example.reactortests;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.junit.jupiter.api.Assertions.*;

class CancellationAndCleanupTest {

    static final class TestLease implements AutoCloseable {
        private final AtomicInteger closes;

        TestLease(AtomicInteger closes) {
            this.closes = closes;
        }

        @Override
        public void close() {
            closes.incrementAndGet();
        }
    }

    static final class Payload {
        final int id;
        final AtomicBoolean released = new AtomicBoolean();

        Payload(int id) {
            this.id = id;
        }

        void release() {
            released.set(true);
        }
    }

    @Test
    void cancellationReachesUpstream() {
        PublisherProbe<Long> upstream =
            PublisherProbe.of(Flux.<Long>never());

        AtomicBoolean onCancel = new AtomicBoolean();
        AtomicReference<SignalType> finalSignal =
            new AtomicReference<>();

        Flux<Long> flow = upstream.flux()
            .doOnCancel(() -> onCancel.set(true))
            .doFinally(finalSignal::set);

        StepVerifier.create(flow)
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        upstream.assertWasSubscribed();
        upstream.assertWasRequested();
        upstream.assertWasCancelled();
        assertTrue(onCancel.get());
        assertEquals(SignalType.CANCEL, finalSignal.get());
    }

    @Test
    void doFinallyTracksCompletionAndError()
            throws InterruptedException {
        CountDownLatch completeLatch = new CountDownLatch(1);
        CountDownLatch errorLatch = new CountDownLatch(1);
        AtomicReference<SignalType> completed =
            new AtomicReference<>();
        AtomicReference<SignalType> errored =
            new AtomicReference<>();

        StepVerifier.create(
                Flux.just(1, 2).doFinally(signal -> {
                    completed.set(signal);
                    completeLatch.countDown();
                })
            )
            .expectNext(1, 2)
            .verifyComplete();

        StepVerifier.create(
                Flux.<Integer>error(
                    new IllegalStateException("boom")
                )
                .doFinally(signal -> {
                    errored.set(signal);
                    errorLatch.countDown();
                })
            )
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "boom".equals(error.getMessage())
            )
            .verify();

        assertTrue(
            completeLatch.await(2, TimeUnit.SECONDS)
        );
        assertTrue(
            errorLatch.await(2, TimeUnit.SECONDS)
        );
        assertEquals(
            SignalType.ON_COMPLETE,
            completed.get()
        );
        assertEquals(
            SignalType.ON_ERROR,
            errored.get()
        );
    }

    @Test
    void usingClosesResourceOnCancel() {
        AtomicInteger closed = new AtomicInteger();

        Flux<Integer> flow = Flux.using(
            () -> new TestLease(closed),
            lease -> Flux.<Integer>never(),
            TestLease::close
        );

        StepVerifier.create(flow)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(1, closed.get());
    }

    @Test
    void usingWhenInvokesAsyncCancel()
            throws InterruptedException {
        AtomicInteger completes = new AtomicInteger();
        AtomicInteger errors = new AtomicInteger();
        AtomicInteger cancels = new AtomicInteger();
        CountDownLatch done = new CountDownLatch(1);

        Flux<Integer> flow = Flux.usingWhen(
            Mono.just("lease-A"),
            lease -> Flux.<Integer>never(),
            lease -> Mono.fromRunnable(
                completes::incrementAndGet
            ),
            (lease, error) -> Mono.fromRunnable(
                errors::incrementAndGet
            ),
            lease -> Mono.fromRunnable(() -> {
                cancels.incrementAndGet();
                done.countDown();
            })
        );

        StepVerifier.create(flow)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(done.await(2, TimeUnit.SECONDS));
        assertEquals(0, completes.get());
        assertEquals(0, errors.get());
        assertEquals(1, cancels.get());
    }

    @Test
    void usingWhenCompletesAfterCleanup() {
        AtomicInteger closed = new AtomicInteger();

        Flux<Integer> flow = Flux.usingWhen(
            Mono.just(new TestLease(closed)),
            lease -> Flux.just(10, 20),
            lease -> Mono.fromRunnable(lease::close),
            (lease, error) -> Mono.fromRunnable(
                lease::close
            ),
            lease -> Mono.fromRunnable(lease::close)
        );

        StepVerifier.create(flow)
            .expectNext(10, 20)
            .verifyComplete();

        assertEquals(1, closed.get());
    }

    @Test
    void timeoutCancelsOriginalPublisher() {
        PublisherProbe<String> original =
            PublisherProbe.of(Mono.<String>never());

        StepVerifier.withVirtualTime(() ->
                original.mono()
                    .timeout(Duration.ofMinutes(5))
            )
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(5))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));

        original.assertWasSubscribed();
        original.assertWasCancelled();
    }

    @Test
    void doOnDiscardReleasesFilteredResources() {
        Payload first = new Payload(1);
        Payload second = new Payload(2);
        Payload third = new Payload(3);

        Flux<Integer> flow = Flux.just(
                first, second, third
            )
            .filter(payload -> payload.id % 2 == 0)
            .doOnDiscard(
                Payload.class,
                Payload::release
            )
            .map(payload -> payload.id);

        StepVerifier.create(flow)
            .expectNext(2)
            .verifyComplete();

        assertTrue(first.released.get());
        assertFalse(second.released.get());
        assertTrue(third.released.get());
    }

    @Test
    void stepVerifierCanAssertDiscardedItems() {
        StepVerifier.create(
                Flux.just(1, 2, 3, 4)
                    .filter(n -> n % 2 == 0)
            )
            .expectNext(2, 4)
            .expectComplete()
            .verifyThenAssertThat()
            .hasDiscardedExactly(1, 3);
    }
}
~~~

### 11.3. Diễn giải tám test

- **cancellationReachesUpstream**: StepVerifier cancel, PublisherProbe xác nhận source nhận cancel, hook doOnCancel/doFinally nhận biết cancellation.
- **doFinallyTracksCompletionAndError**: kiểm tra hai nhánh terminal và chờ callback bằng latch.
- **usingClosesResourceOnCancel**: resource AutoCloseable được đóng một lần khi downstream cancel.
- **usingWhenInvokesAsyncCancel**: chỉ callback asyncCancel được gọi; asyncComplete/asyncError không chạy.
- **usingWhenCompletesAfterCleanup**: release Publisher hoàn tất trước downstream onComplete.
- **timeoutCancelsOriginalPublisher**: dùng virtual time, timeout 5 phút trên clock ảo, upstream nhận cancel.
- **doOnDiscardReleasesFilteredResources**: hai item bị filter được giải phóng; item giao cho subscriber không bị release.
- **stepVerifierCanAssertDiscardedItems**: kiểm tra chính xác danh sách item discard.

### 11.4. Chạy test

~~~bash
java -version
mvn -version
mvn clean test
~~~

Kỳ vọng: Maven thực thi tám JUnit tests và tất cả PASS khi dependency và môi trường được cấu hình đúng. Format log Maven có thể khác nhau giữa các hệ; dùng số lượng failures/errors và build status để xác minh thay vì dựa vào stdout cố định.

## 12. Test cleanup đúng một lần

Một resource phải có owner rõ ràng. Nếu doFinally và usingWhen đều release một connection, có thể dẫn đến double close. Tốt nhất dùng **một cơ chế chính** quản lý resource.

Nếu nhiều đường điều khiển phải cùng yêu cầu release, có thể bảo vệ:

~~~java
AtomicBoolean released = new AtomicBoolean();

Runnable releaseOnce = () -> {
    if (released.compareAndSet(false, true)) {
        closeResource();
    }
};
~~~

Đây là snippet cần closeResource của ứng dụng. So sánh compareAndSet giúp callback idempotent, nhưng không giải quyết việc release bất đồng bộ thất bại; vẫn cần theo dõi kết quả.

Test thêm:

- Hai subscription riêng → hai resource riêng được mở/đóng.
- Complete → đóng một lần.
- Error → đóng một lần.
- Cancel → đóng một lần.
- Cleanup phát lỗi → lỗi được quan sát theo contract.
- Cancel trùng/lifecycle race → không double close.

## 13. Spring WebFlux: từ unit test tới HTTP integration

### 13.1. SSE

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Long>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(n -> ServerSentEvent.builder(n).build())
        .doFinally(signal ->
            logger.info("SSE ended: {}", signal)
        );
}
~~~

Đây là snippet minh họa cần controller, logger, imports. Khi HTTP client đóng stream, server adapter có thể cancel Publisher; cần test bằng WebTestClient lấy response body Flux, cancel sau một số event và chờ latch phía server.

Network disconnect có thể xuất hiện thành CANCEL hoặc ERROR tùy adapter và vị trí operator; test integration theo contract thực tế thay vì mặc định mọi disconnect luôn cho một SignalType giống nhau.

### 13.2. WebSocket

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> output = eventSource
        .map(session::textMessage);

    Mono<Void> outbound = session.send(output);
    Mono<Void> inbound = session.receive().then();

    return Mono.firstWithSignal(inbound, outbound)
        .doFinally(signal ->
            logger.info("WS {} finished: {}",
                session.getId(), signal)
        );
}
~~~

Đây là snippet yêu cầu WebSocketHandler, eventSource và logger. Đừng subscribe riêng vào timer/broker mà không đưa Disposable vào lifecycle. Khi client disconnect, đảm bảo dọn registry, timer và broker subscription.

### 13.3. WebClient

~~~java
Mono<OrderResponse> operation = webClient.post()
    .uri("/orders")
    .bodyValue(command)
    .retrieve()
    .bodyToMono(OrderResponse.class);
~~~

Downstream cancel có thể ngừng quan tâm response và làm connector hủy I/O, **nhưng không bảo đảm server đã ngừng xử lý POST**. Hãy dùng Idempotency-Key và đối soát trạng thái khi cần exactly/effectively-once.

### 13.4. R2DBC

Nếu dùng Reactive DB, ưu tiên TransactionalOperator/R2dbcTransactionManager hoặc usingWhen để commit/rollback/close theo đúng lifecycle. Không gọi connection.close().subscribe() trong doFinally rồi coi cleanup đã được chờ.

## 14. Hot Publisher, đa subscriber và resource sharing

~~~java
Flux<Long> shared = Flux.interval(Duration.ofSeconds(1))
    .share();
~~~

Khi client A và B cùng subscribe, việc A cancel có thể chỉ gỡ A. Upstream tiếp tục phục vụ B cho tới khi chính sách share/refCount quyết định hủy.

Nên test:

1. A và B cùng nhận dữ liệu.
2. Hủy A.
3. B vẫn nhận được.
4. Hủy B.
5. Upstream được giải phóng nếu đó là policy của toán tử.
6. Cache/replay không giữ dữ liệu vô hạn.

Một PublisherProbe trên A không tự chứng minh broker connection dùng chung đã đóng.

## 15. Chống flaky test

### 15.1. Không dùng Thread.sleep

Sai:

~~~java
StepVerifier.create(source)
    .thenCancel()
    .verify();

Thread.sleep(100);
assertTrue(closed.get());
~~~

Máy CI chậm có thể cần hơn 100ms; test ngẫu nhiên PASS/FAIL. Dùng CountDownLatch, PublisherProbe hoặc một Publisher completion của cleanup.

### 15.2. Không verify vô hạn

Flux.never() không tự complete. Thêm thenCancel hoặc expectTimeout, và verify(Duration) để có trần thời gian.

Có thể đặt StepVerifier.setDefaultTimeout(Duration.ofSeconds(3)) ở scope test suite, nhưng setting toàn cục có thể tác động test khác; timeout riêng từng test dễ kiểm soát hơn.

### 15.3. Tạo time operator trong withVirtualTime supplier

~~~java
Mono<String> never = Mono.never();

StepVerifier.withVirtualTime(() ->
        never.timeout(Duration.ofMinutes(10))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(10))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));
~~~

Không giữ Scheduler vật lý trong một operator đã được tạo trước khi virtual clock được thiết lập.

### 15.4. Không kiểm tra doFinally quá sớm

doFinally của complete/error có thể chạy sau downstream terminal, nên dùng latch/await. Không dùng AtomicReference global dùng chung cho nhiều subscription đang chạy đồng thời; nên đo state per subscription.

### 15.5. Không nhầm discard và dropped

Một item bị filter thường là discard hợp lệ; không phải dropped signal. Dùng local doOnDiscard để cleanup và đúng StepVerifier assertions. Với prefetch/scheduler concurrency, ưu tiên invariants resource release thay vì số lượng item discard cứng.

## 16. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Test treo với Flux.never | Không có thenCancel/verify timeout | Thêm thenCancel và verify(Duration) |
| thenCancel PASS nhưng resource leak | Không instrument cleanup | Dùng using/usingWhen + counter/latch |
| doOnTerminate không chạy khi cancel | Không bao phủ cancel | Dùng doFinally/doOnCancel |
| take(2) upstream CANCEL, downstream COMPLETE | Operator chủ động ngừng nguồn | Test hai vị trí riêng |
| Timeout downstream ERROR, upstream CANCEL | Timeout chuyển tín hiệu | PublisherProbe nguồn + expectError |
| Virtual time vẫn đợi thời gian thật | Timer/Scheduler tạo ngoài lambda | Xây time operator trong supplier |
| doOnDiscard không gọi | Operator không hỗ trợ hoặc hook sai vị trí | Đọc Discard Support |
| DataBuffer leak | Bỏ buffered item chưa release | doOnDiscard và ownership rõ ràng |
| usingWhen cleanup bị mất | Cleanup được subscribe riêng | Return Publisher cleanup |
| Cleanup chạy hai lần | Có hai owner | Chỉ một owner, release idempotent |
| Cleanup async test flaky | Assertion quá sớm | Dùng CountDownLatch |
| Một user cancel làm dừng room | Shared source lifecycle không đúng | Kiểm tra share/refCount |
| HTTP cancel mà remote vẫn có side effect | Cancel không rollback | Idempotency/reconciliation |
| Test chỉ dùng AtomicBoolean | Không chứng minh upstream hoặc socket đã đóng | PublisherProbe + integration test |

## 17. Checklist

1. Resource thuộc subscription nào?
2. Có cleanup ở complete, error và cancel?
3. StepVerifier.thenCancel test được hủy đúng lúc?
4. PublisherProbe kiểm tra đúng upstream/inner Publisher?
5. doFinally nhận SignalType nào ở từng đoạn?
6. using đóng resource đúng một lần?
7. usingWhen xử lý asyncComplete, asyncError, asyncCancel?
8. Lỗi cleanup có được quan sát?
9. Callback async có latch hoặc cơ chế await?
10. Discarded item đã được release?
11. doOnDiscard có đặt đúng chỗ và callback idempotent?
12. Source hot/shared có bảo toàn subscriber còn lại?
13. Virtual time test không phụ thuộc wall-clock?
14. Test có timeout tránh CI treo?
15. Có integration test cho SSE, WebSocket, database hoặc network khi cần?
16. Có metrics cancel, active resources, cleanup failure?
17. Đã phân biệt cancel với remote rollback?

## 18. Bài tập thực hành

**Bài 1:** Dùng Flux.never và thenCancel, assert doOnCancel.

**Bài 2:** Dùng StepVerifier initialRequest=0, thenRequest(3), expectNextCount(3), thenCancel.

**Bài 3:** PublisherProbe.assertWasCancelled và assertWasRequested.

**Bài 4:** So sánh doFinally(ON_COMPLETE), doFinally(ON_ERROR) và doFinally(CANCEL).

**Bài 5:** Test take(2) trên Flux.range(1, 10), quan sát upstream/downstream SignalType.

**Bài 6:** Dùng withVirtualTime test timeout 30 phút và kiểm tra upstream cancellation.

**Bài 7:** Flux.using với AutoCloseable: test complete, error, cancel release đúng một lần.

**Bài 8:** Flux.usingWhen: ba callback asyncComplete/asyncError/asyncCancel với counters riêng.

**Bài 9:** Tạo lỗi asyncComplete, kiểm tra kết quả downstream và lỗi cleanup.

**Bài 10:** Dùng doOnDiscard để release các object bị filter loại bỏ.

**Bài 11:** verifyThenAssertThat.hasDiscardedExactly và so sánh với hasDroppedElements.

**Bài 12:** Dùng TestPublisher.emit/next để điều khiển thời điểm phát, sau đó thenCancel.

**Bài 13:** Tạo switchMap với hai inner PublisherProbe, xác nhận inner cũ bị cancel.

**Bài 14:** Test hai subscriber trên share/refCount, xác nhận một cancel không dừng người còn lại.

**Bài 15:** Spring WebFlux SSE integration: hủy body stream và chờ resource cleanup bằng latch.

## 19. Ghi nhớ

**Cancel là tín hiệu từ downstream lên upstream**, khác với onComplete/onError. StepVerifier.thenCancel() chủ động hủy subscription, còn PublisherProbe chứng minh Publisher cụ thể đã subscribe/request/cancel.

**doOnCancel** chỉ phản ứng với cancel; **doFinally** quan sát ON_COMPLETE, ON_ERROR hoặc CANCEL. Với resource đồng bộ, dùng **Flux.using**; với resource cần cleanup Publisher, dùng **Flux.usingWhen / Mono.usingWhen**, đặc biệt nhánh asyncCancel.

**doOnDiscard** dọn phần tử bị filter/prefetch queue bỏ, không đồng nghĩa dropped signal. Dùng StepVerifier.verifyThenAssertThat, latch, counter và integration test khi cần.

Không khẳng định resource đã đóng hoặc remote transaction đã rollback chỉ vì thenCancel PASS. Kiểm tra đúng ranh giới, subscription, owner và kết quả cleanup.

## 20. Tài liệu tham khảo

- Reactor Core Reference — Testing: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Core Reference — Resource Cleanup: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Reactor Test API — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test API — StepVerifier.Assertions: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html
- Reactor Test API — PublisherProbe: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html
- Reactor Test API — TestPublisher: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html
- Reactor Core API — Flux: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core API — Mono: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core API — SignalType: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/SignalType.html
- Project Reactor Release Docs 3.8.8: https://projectreactor.io/docs
- Spring Framework Reference — WebFlux WebSocket: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Reactive Streams Specification: https://www.reactive-streams.org/
