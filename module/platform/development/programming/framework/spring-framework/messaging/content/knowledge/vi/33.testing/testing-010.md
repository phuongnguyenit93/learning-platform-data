# Dùng StepVerifier kiểm tra luồng phản ứng, lỗi và cancellation

## Mục tiêu

Trong ứng dụng Spring, các API reactive thường trả về Mono hoặc Flux. Một luồng có thể phát dữ liệu, hoàn tất bình thường, phát lỗi hoặc bị hủy trước khi kết thúc. Chỉ kiểm tra giá trị trả về cuối cùng là chưa đủ: cần xác nhận thứ tự, số lượng phần tử, tín hiệu terminal, backpressure, retry và hành vi cancellation.

Project Reactor cung cấp StepVerifier trong module reactor-test để mô phỏng một subscriber và kiểm tra các tín hiệu mà Publisher phát ra theo đúng thứ tự. Bài này tập trung vào cách dùng StepVerifier để kiểm thử luồng phản ứng, lỗi và cancellation, bao gồm các publisher được dùng trong Spring RSocket.

Sau bài này, bạn có thể:

- Tạo kịch bản kiểm thử cho Mono và Flux bằng StepVerifier.
- Kiểm tra onNext, onComplete và onError.
- Kiểm tra lỗi sau khi stream đã phát một phần dữ liệu.
- Điều khiển demand để xác nhận backpressure.
- Dùng virtual time để kiểm tra delay, interval và timeout mà không phải chờ thật.
- Dùng TestPublisher để chủ động phát tín hiệu trong test.
- Kiểm tra cancellation được truyền lên upstream.
- Áp dụng StepVerifier vào publisher lấy từ RSocketRequester và kiểm thử các trường hợp lỗi.

## 1. Vì sao cần StepVerifier?

Reactive Streams không trả dữ liệu theo cách đồng bộ thông thường. Một Publisher có thể phát nhiều phần tử theo thời gian và giao tiếp với subscriber bằng các tín hiệu:

- onSubscribe: subscriber nhận Subscription và có thể yêu cầu dữ liệu hoặc hủy.
- onNext: publisher phát một phần tử.
- onError: publisher kết thúc bằng lỗi.
- onComplete: publisher kết thúc bình thường.
- cancel: subscriber yêu cầu dừng subscription.

Với Mono, publisher phát tối đa một phần tử rồi hoàn tất hoặc phát lỗi. Mono cũng có thể hoàn tất rỗng mà không phát phần tử nào. Với Flux, publisher có thể phát zero hoặc nhiều phần tử trước khi complete hoặc error.

Một test chỉ gọi block() thường bỏ qua nhiều hành vi quan trọng:

- Không kiểm tra được nhiều phần tử có phát đúng thứ tự hay không.
- Không kiểm tra được stream kết thúc bình thường hay bằng lỗi.
- Không thể mô phỏng demand tăng dần một cách rõ ràng.
- Không thể kiểm tra cancellation và tín hiệu cleanup.
- Có thể khiến test chờ thật khi publisher chứa delay hoặc interval.

StepVerifier subscribe vào Publisher, điều khiển demand và xác nhận các tín hiệu theo kịch bản. Nó phù hợp với unit test cho service reactive, adapter, handler và các luồng xử lý dữ liệu.

### 1.1. Dependency

Với Maven và Spring Boot, thêm reactor-test ở test scope. Spring Boot dependency management thường quản lý phiên bản Reactor tương thích với stack Spring đang dùng:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án dùng Spring Boot starter test, JUnit Jupiter đã có sẵn. Nếu không, thêm dependency JUnit Jupiter tương ứng với build của dự án. Không nên tự chọn phiên bản reactor-test khác với Reactor Core đang chạy trong ứng dụng.

### 1.2. Cách một kịch bản StepVerifier hoạt động

Một kịch bản thường có ba phần:

1. Tạo Publisher cần kiểm tra.
2. Dùng StepVerifier.create(publisher) để tạo subscriber kiểm thử.
3. Khai báo các tín hiệu mong đợi rồi kết thúc bằng verifyComplete(), verify(), hoặc một phương thức verify phù hợp.

Ví dụ tối thiểu:

~~~java
StepVerifier.create(Flux.just("A", "B"))
    .expectNext("A", "B")
    .verifyComplete();
~~~

StepVerifier thực sự subscribe vào publisher. Vì vậy, các thao tác lazy trong Reactor được kích hoạt khi test bắt đầu. Đừng gọi subscribe() riêng trên publisher trước khi đưa nó vào StepVerifier; việc đó tạo một subscription khác và làm sai kịch bản đang kiểm tra.

## 2. Kiểm tra giá trị và thứ tự phát

### 2.1. Kiểm tra Mono

Với một Mono phát một giá trị:

~~~java
Mono<String> source = Mono.just("RSocket");

StepVerifier.create(source)
    .expectNext("RSocket")
    .verifyComplete();
~~~

Với Mono hoàn tất rỗng:

~~~java
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();
~~~

Với Mono phát lỗi:

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid request"))
    )
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Cần phân biệt Mono.empty() với Mono.error(). Trường hợp đầu là hoàn tất bình thường không có dữ liệu; trường hợp sau là terminal error.

### 2.2. Kiểm tra nhiều phần tử của Flux

~~~java
Flux<String> source = Flux.just("connect", "request", "close");

StepVerifier.create(source)
    .expectNext("connect")
    .expectNext("request", "close")
    .verifyComplete();
~~~

expectNext kiểm tra giá trị theo thứ tự. Nếu phần tử khác giá trị mong đợi hoặc stream phát tín hiệu không đúng thứ tự, verification thất bại.

Khi cần kiểm tra điều kiện thay vì so sánh toàn bộ object:

~~~java
StepVerifier.create(Flux.just(
        new Message("m-1", "created"),
        new Message("m-2", "updated")
    ))
    .assertNext(message -> {
        assertEquals("m-1", message.id());
        assertEquals("created", message.type());
    })
    .assertNext(message -> {
        assertEquals("m-2", message.id());
        assertEquals("updated", message.type());
    })
    .verifyComplete();
~~~

Ví dụ này giả định ứng dụng có record Message(String id, String type) và đã import assertEquals từ JUnit. assertNext nhận Consumer và cho phép dùng assertion của thư viện test.

### 2.3. Kiểm tra số lượng phần tử

Nếu không cần kiểm tra từng giá trị:

~~~java
StepVerifier.create(Flux.range(1, 5))
    .expectNextCount(5)
    .verifyComplete();
~~~

expectNextCount kiểm tra publisher phát đúng số phần tử liên tiếp, nhưng không xác nhận nội dung từng phần tử. Dùng expectNext hoặc assertNext nếu giá trị có ý nghĩa nghiệp vụ.

expectNextMatches nhận Predicate và phù hợp khi chỉ cần kiểm tra một số điều kiện:

~~~java
StepVerifier.create(Mono.just("accepted"))
    .expectNextMatches(value -> value.startsWith("accept"))
    .verifyComplete();
~~~

Không dùng predicate quá rộng. Một điều kiện như value != null có thể bỏ lọt lỗi nội dung mà contract thực sự cần bảo vệ.

## 3. Kiểm tra lỗi và terminal signal

### 3.1. Kiểm tra kiểu lỗi

~~~java
Flux<String> source = Flux.error(
    new IllegalStateException("connection unavailable")
);

StepVerifier.create(source)
    .expectError(IllegalStateException.class)
    .verify();
~~~

expectError(Class) xác nhận kiểu exception. Nếu chỉ kiểm tra kiểu lỗi mà không kiểm tra message hoặc thuộc tính, test có thể bỏ lọt lỗi sai nguyên nhân.

### 3.2. Kiểm tra message hoặc điều kiện lỗi

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("quantity must be positive"))
    )
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
            && "quantity must be positive".equals(error.getMessage())
    )
    .verify();
~~~

Có thể dùng expectErrorMessage nếu chỉ cần so sánh message, hoặc expectErrorSatisfies khi cần nhiều assertion:

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid payload"))
    )
    .expectErrorSatisfies(error -> {
        assertInstanceOf(IllegalArgumentException.class, error);
        assertEquals("invalid payload", error.getMessage());
    })
    .verify();
~~~

Các assertion ở trên là API của JUnit Jupiter. Chọn đúng phương thức theo phiên bản JUnit mà dự án đang dùng.

### 3.3. Stream phát một phần dữ liệu rồi mới lỗi

Đây là trường hợp rất quan trọng trong messaging. Một Flux có thể phát một số kết quả trước khi phát onError:

~~~java
Flux<String> source = Flux.concat(
    Flux.just("item-1:accepted", "item-2:accepted"),
    Flux.error(new IllegalStateException("downstream unavailable"))
);

StepVerifier.create(source)
    .expectNext("item-1:accepted")
    .expectNext("item-2:accepted")
    .expectErrorMessage("downstream unavailable")
    .verify();
~~~

Test xác nhận hai phần tử đã phát trước lỗi. Với RSocket, client có thể đã nhận một số payload trước khi stream kết thúc bằng ERROR. Ứng dụng cần quyết định cách giữ kết quả đã nhận, tra cứu trạng thái còn lại và retry an toàn.

Không biến mọi lỗi thành complete trong production chỉ để test dễ pass. Nếu service có chủ ý chuyển lỗi nghiệp vụ thành một phần tử kết quả, hãy kiểm tra chính xác DTO và trạng thái đó.

### 3.4. Phân biệt lỗi nghiệp vụ và lỗi reactive

Có hai cách biểu diễn phổ biến:

- **Business outcome:** một payload bình thường có status REJECTED, NOT_FOUND hoặc VALIDATION_FAILED. Publisher vẫn có thể complete bình thường.
- **Technical failure:** publisher phát onError, ví dụ lỗi kết nối, timeout hoặc lỗi hệ thống không thể xử lý trong contract hiện tại.

Ví dụ business rejection:

~~~java
Mono<OrderResult> source = Mono.just(
    new OrderResult("order-1", "REJECTED", "LIMIT_EXCEEDED")
);

StepVerifier.create(source)
    .assertNext(result -> {
        assertEquals("REJECTED", result.status());
        assertEquals("LIMIT_EXCEEDED", result.code());
    })
    .verifyComplete();
~~~

Ví dụ giả định có record OrderResult(String orderId, String status, String code). Test cần kiểm tra cả status và code để tránh nhầm một response từ chối hợp lệ thành technical error.

## 4. Điều khiển demand và kiểm tra backpressure

Reactive Streams dùng demand để subscriber thông báo số phần tử mà nó sẵn sàng nhận. Subscriber không nên bị buộc phải xử lý vô hạn phần tử ngay lập tức.

StepVerifier.create có thể nhận initial request. Giá trị 0 giúp test publisher trước khi subscriber yêu cầu dữ liệu:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

Luồng kiểm tra:

1. Subscriber bắt đầu với demand bằng 0.
2. Test yêu cầu một phần tử.
3. Publisher phát 1.
4. Test yêu cầu thêm hai phần tử.
5. Publisher phát 2 và 3.
6. Publisher complete.

Điều này giúp kiểm tra các operator hoặc publisher tự triển khai có tôn trọng demand hay không.

### 4.1. Khi nào cần kiểm tra backpressure?

Nên kiểm tra demand khi:

- Viết custom Publisher hoặc adapter.
- Xử lý stream lớn từ database, message broker hoặc remote service.
- Dùng buffer, window, limitRate hoặc operator có khả năng giữ nhiều phần tử.
- Muốn bảo đảm consumer chậm không bị đẩy dữ liệu vượt khả năng xử lý.
- Tích hợp một luồng dữ liệu có tốc độ cao qua RSocket Channel hoặc Request-Stream.

Không phải mọi unit test cần điều khiển demand bằng 0. Với publisher chuẩn như Flux.just hoặc Flux.range, kiểm tra cơ bản thường đủ. Tập trung kiểm tra backpressure ở những nơi ứng dụng có logic buffering, concurrency hoặc custom subscription.

### 4.2. Kiểm tra không có tín hiệu trong một khoảng thời gian

expectNoEvent kiểm tra publisher không phát tín hiệu trong khoảng thời gian chỉ định:

~~~java
StepVerifier.withVirtualTime(() -> Flux.interval(Duration.ofSeconds(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(500))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenCancel()
    .verify();
~~~

expectSubscription giúp xác nhận subscription trước khi kiểm tra khoảng không có event. Nếu dùng virtual time, test tiến thời gian giả lập mà không phải sleep thật.

## 5. Kiểm tra cancellation

Cancellation xảy ra khi subscriber không còn cần dữ liệu. Ví dụ người dùng rời màn hình, request hết deadline, client đóng stream hoặc một operator như take giới hạn số phần tử.

Cancellation không giống complete:

- Complete là publisher kết thúc bình thường.
- Error là publisher kết thúc do lỗi.
- Cancel là subscriber yêu cầu dừng subscription.

### 5.1. Kiểm tra cancellation được truyền lên upstream

Có thể dùng doFinally để quan sát tín hiệu kết thúc:

~~~java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Long> source = Flux.<Long>never()
    .doFinally(finalSignal::set);

StepVerifier.create(source)
    .thenCancel()
    .verify(Duration.ofSeconds(5));

assertEquals(SignalType.CANCEL, finalSignal.get());
~~~

doFinally nhận SignalType khi publisher hoàn tất, lỗi hoặc bị cancel. Test xác nhận subscriber đã hủy và callback cleanup được thực thi với tín hiệu CANCEL.

Nếu test một luồng hữu hạn và dùng expectNext rồi verifyComplete, tín hiệu cuối cùng sẽ là ON_COMPLETE chứ không phải CANCEL.

### 5.2. Kiểm tra cleanup

Ví dụ service cần giải phóng tài nguyên khi stream bị hủy:

~~~java
AtomicBoolean cleanedUp = new AtomicBoolean();

Flux<String> source = Flux.<String>never()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            cleanedUp.set(true);
        }
    });

StepVerifier.create(source)
    .thenCancel()
    .verify();

assertTrue(cleanedUp.get());
~~~

Trong ứng dụng thực tế, cleanup có thể đóng file, giải phóng lease, dừng polling hoặc hủy tác vụ upstream. Cleanup nên idempotent để nhiều đường kết thúc không giải phóng cùng tài nguyên theo cách gây lỗi.

Không đặt side effect nghiệp vụ không thể đảo ngược vào callback cancellation với giả định callback đó luôn chạy trước khi server commit. Cancellation là tín hiệu điều khiển stream; nó không phải transaction rollback.

### 5.3. Cancellation trong RSocket

Với Request-Stream hoặc Channel, cancellation của subscriber thường được truyền thành tín hiệu CANCEL trên stream RSocket. Responder có thể dùng tín hiệu này để ngừng công việc còn lại nếu implementation hỗ trợ cancellation.

Tuy nhiên, cancellation không chứng minh server chưa xử lý dữ liệu. Một side effect đã commit trước khi CANCEL đến vẫn tồn tại. Vì vậy:

- Không xóa trạng thái nghiệp vụ chỉ vì client hủy stream.
- Lưu kết quả đã commit trước khi phát acknowledgement.
- Dùng operation ID để client truy vấn lại sau khi reconnect.
- Thiết kế idempotency cho thao tác có thể được gửi lại.
- Kiểm tra cancellation bằng integration test với transport thật nếu hành vi truyền CANCEL là yêu cầu quan trọng.

## 6. TestPublisher: chủ động điều khiển tín hiệu

TestPublisher thuộc reactor-test. Nó cho phép test tự quyết định khi nào phát onNext, onError hoặc onComplete. Điều này hữu ích khi cần kiểm tra service phản ứng ra sao trước các tín hiệu đến theo từng bước.

Ví dụ:

~~~java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux())
    .then(() -> {
        publisher.next("A", "B");
    })
    .expectNext("A", "B")
    .then(() -> {
        publisher.complete();
    })
    .verifyComplete();
~~~

TestPublisher giúp tạo nguồn dữ liệu điều khiển được mà không cần Thread.sleep. Test đăng ký trước, sau đó phát dữ liệu và hoàn tất đúng lúc kịch bản yêu cầu.

### 6.1. Kiểm tra upstream phát lỗi

~~~java
TestPublisher<String> publisher = TestPublisher.create();

StepVerifier.create(publisher.flux())
    .then(() -> {
        publisher.error(new IllegalStateException("source failed"));
    })
    .expectErrorMessage("source failed")
    .verify();
~~~

Có thể dùng TestPublisher để kiểm tra service ánh xạ lỗi upstream thành response hoặc lỗi nghiệp vụ theo contract.

### 6.2. Khi nào dùng TestPublisher?

Dùng TestPublisher khi cần:

- Phát dữ liệu theo từng bước.
- Mô phỏng lỗi xảy ra sau một số phần tử.
- Kiểm tra operator xử lý tín hiệu đến trễ.
- Điều khiển luồng đầu vào của service.
- Tránh dùng sleep hoặc phụ thuộc timing của thread.

TestPublisher chỉ là công cụ kiểm thử, không dùng làm nguồn dữ liệu production. Với test cần kiểm tra chính xác request/cancel của Publisher, có thể dùng các assertion mà TestPublisher cung cấp; nếu cần xác minh hành vi transport RSocket, phải có integration test riêng.

## 7. Virtual time: kiểm tra timer mà không chờ thật

Các publisher như Mono.delay, Flux.interval, timeout và retry backoff có thể làm test chậm nếu phải chờ thời gian thực. StepVerifier.withVirtualTime cho phép tiến đồng hồ giả lập.

### 7.1. Kiểm tra Flux.interval

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Publisher phải được tạo bên trong Supplier truyền cho withVirtualTime. Nếu tạo Flux.interval trước đó, publisher có thể đã giữ scheduler thật và không dùng virtual scheduler của StepVerifier.

### 7.2. Kiểm tra timeout

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
            .timeout(Duration.ofSeconds(2))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectError(TimeoutException.class)
    .verify();
~~~

Publisher dự kiến phát dữ liệu sau năm giây nhưng timeout được đặt hai giây. Test tiến thời gian đến deadline và xác nhận TimeoutException.

Cần import java.util.concurrent.TimeoutException. Virtual time chỉ kiểm soát scheduler được tích hợp với virtual scheduler; không tự động thay thế mọi clock, thread hoặc API blocking bên ngoài Reactor.

### 7.3. Kiểm tra retry backoff

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>error(new IllegalStateException("temporary"))
            .retryWhen(
                Retry.fixedDelay(2, Duration.ofSeconds(1))
            )
            .onErrorReturn("fallback")
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext("fallback")
    .verifyComplete();
~~~

Retry.fixedDelay(2, ...) thực hiện tối đa hai lần retry sau lần subscribe ban đầu. Khi cả ba lần đều lỗi, onErrorReturn chuyển lỗi cuối cùng thành giá trị fallback. Test không phải đợi hai giây thật.

Nếu test dùng Retry.backoff có jitter, thời điểm chính xác có thể khó dự đoán. Có thể cấu hình jitter phù hợp hoặc chỉ kiểm tra trong một khoảng thời gian ảo đủ rộng.

## 8. Một lớp test hoàn chỉnh

Ví dụ dưới đây gom các kỹ thuật cơ bản vào một JUnit 5 test class. Các test này dùng Reactor Core và reactor-test; chúng không cần khởi động Spring Context.

~~~java
package com.example.messaging;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
import reactor.util.retry.Retry;

class ReactivePublisherTest {

    @Test
    void emitsValuesInOrder() {
        StepVerifier.create(Flux.just("A", "B", "C"))
            .expectNext("A", "B", "C")
            .verifyComplete();
    }

    @Test
    void verifiesErrorAfterPartialData() {
        Flux<String> source = Flux.concat(
            Flux.just("first", "second"),
            Flux.error(
                new IllegalStateException("source unavailable")
            )
        );

        StepVerifier.create(source)
            .expectNext("first", "second")
            .expectErrorMessage("source unavailable")
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void requestsItemsIncrementally() {
        StepVerifier.create(Flux.range(1, 3), 0)
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void cancellationReachesUpstream() {
        AtomicReference<SignalType> finalSignal =
            new AtomicReference<>();

        Flux<Long> source = Flux.<Long>never()
            .doFinally(finalSignal::set);

        StepVerifier.create(source)
            .thenCancel()
            .verify(Duration.ofSeconds(5));

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }

    @Test
    void retriesTransientFailure() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> source = Mono.defer(() -> {
            if (attempts.incrementAndGet() < 3) {
                return Mono.error(
                    new IllegalStateException("temporary")
                );
            }
            return Mono.just("ok");
        }).retryWhen(Retry.max(2));

        StepVerifier.create(source)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void verifiesTimeoutWithVirtualTime() {
        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(5))
                    .timeout(Duration.ofSeconds(2))
            )
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void controlsSignalsWithTestPublisher() {
        TestPublisher<String> publisher = TestPublisher.create();

        StepVerifier.create(publisher.flux())
            .then(() -> {
                publisher.next("A", "B");
            })
            .expectNext("A", "B")
            .then(() -> {
                publisher.complete();
            })
            .verifyComplete();
    }
}
~~~

Các import static và class trong ví dụ thuộc JUnit Jupiter, Reactor Core và Reactor Test. Spring Boot starter test thường đã cung cấp JUnit Jupiter; reactor-test phải được thêm ở test scope.

Chạy test bằng Maven Wrapper:

~~~bash
./mvnw test
~~~

Trên Windows PowerShell, dùng:

~~~powershell
.\mvnw.cmd test
~~~

Nếu test class nằm trong module Maven con, chạy lệnh ở thư mục module đó hoặc chỉ định module từ root theo cấu trúc multi-module của dự án. Maven Surefire sẽ thực thi các test class theo cấu hình dự án.

## 9. Kiểm tra publisher từ Spring RSocket

StepVerifier không chỉ dùng với Flux.just hoặc Mono.error. Nó có thể kiểm tra publisher trả về từ RSocketRequester.

Ví dụ Request-Response:

~~~java
Mono<OrderAccepted> response = requester
    .route("orders.submit")
    .data(command)
    .retrieveMono(OrderAccepted.class);

StepVerifier.create(response)
    .assertNext(order -> {
        assertEquals("ACCEPTED", order.status());
    })
    .verifyComplete();
~~~

Test này cần một RSocket server đang chạy hoặc một test fixture đã cấu hình transport và route tương ứng. Việc StepVerifier subscribe sẽ kích hoạt request; không cần gọi block() trước.

Ví dụ Request-Stream và cancellation:

~~~java
Flux<Notification> notifications = requester
    .route("notifications")
    .retrieveFlux(Notification.class);

StepVerifier.create(notifications)
    .expectNextMatches(notification ->
        notification.id() != null
    )
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Đoạn test giả định route notifications phát ít nhất một Notification và record có accessor id(). Test kết thúc bằng cancel sau phần tử đầu tiên. Nếu route không bảo đảm phát phần tử trong thời gian test, hãy dùng fixture điều khiển được hoặc thiết kế test timeout rõ ràng.

### 9.1. Kiểm tra lỗi từ responder

Một handler có thể trả Mono.error hoặc Flux.error. Integration test nên xác nhận lỗi mà requester quan sát được theo mapping thực tế của Spring RSocket:

~~~java
StepVerifier.create(
        requester
            .route("orders.submit")
            .data(invalidCommand)
            .retrieveMono(OrderAccepted.class)
    )
    .expectError()
    .verify(Duration.ofSeconds(5));
~~~

Không nên khẳng định exception class ở client luôn giống exception class bên server. RSocket có thể chuyển lỗi ứng dụng thành error frame và Spring/RSocket Java ánh xạ nó thành kiểu lỗi phía client. Contract test nên kiểm tra mã lỗi hoặc semantics được công bố, không phụ thuộc vào class nội bộ của server nếu class đó không phải API công khai.

### 9.2. Kiểm tra SETUP và connection lifecycle

StepVerifier kiểm tra Publisher được tạo từ requester; nó không thay thế test cho handshake hoặc cấu hình transport. Với yêu cầu về SETUP, authentication, metadata, keepalive, reconnect và resume, cần integration test sử dụng transport thật hoặc test fixture RSocket phù hợp.

Có thể kiểm tra riêng:

- Client gửi setup metadata đúng.
- Server chấp nhận hoặc từ chối kết nối theo authentication policy.
- Route hoạt động sau khi SETUP hoàn tất.
- Kết nối bị đóng và requester phản ứng đúng.
- Request stream bị cancel khi subscriber hủy.
- Reconnect hoặc resume tuân theo cấu hình được công bố.

Không gộp mọi trường hợp này vào một unit test StepVerifier duy nhất. Unit test nên tập trung vào semantics của Publisher; integration test xác nhận hành vi giữa các thành phần và transport.

## 10. Best practices khi viết StepVerifier test

### 10.1. Luôn xác nhận terminal signal

Nếu test chỉ có expectNext mà không xác nhận complete hoặc error, nó có thể không phát hiện publisher phát thêm phần tử hoặc không kết thúc. Hãy kết thúc kịch bản bằng verifyComplete(), expectError... rồi verify(), hoặc thenCancel() khi chủ ý hủy.

### 10.2. Dùng timeout cho test có khả năng chờ

Các phương thức verify có thể chờ cho đến khi publisher phát terminal signal. Với test phụ thuộc mạng, scheduler hoặc nguồn bên ngoài, dùng verify(Duration.ofSeconds(...)) để tránh test treo vô hạn.

Không thêm timeout tùy tiện quá ngắn khiến test flaky trên CI. Chọn giới hạn đủ cho môi trường test và dùng virtual time nếu có thể.

### 10.3. Không dùng Thread.sleep

Thread.sleep khiến test chậm và phụ thuộc timing. Với timer của Reactor, ưu tiên withVirtualTime, thenAwait và expectNoEvent. Với nguồn tín hiệu chủ động, dùng TestPublisher.

### 10.4. Không dùng block để kiểm tra publisher

block() chỉ lấy một kết quả đồng bộ và có thể che giấu cancellation, ordering hoặc terminal behavior. StepVerifier thể hiện rõ chuỗi tín hiệu cần kiểm tra.

### 10.5. Kiểm tra cả dữ liệu lẫn lỗi

Một service có thể trả đúng dữ liệu ở happy path nhưng xử lý sai error path. Nên có test riêng cho:

- Giá trị hợp lệ.
- Publisher hoàn tất rỗng.
- Lỗi validation hoặc business rejection.
- Lỗi kỹ thuật.
- Lỗi sau khi đã phát một phần dữ liệu.
- Timeout.
- Retry và exhaustion.
- Cancellation.

Không cần tạo test riêng cho mọi operator. Tập trung vào contract và những nhánh có tác động tới nghiệp vụ.

### 10.6. Test không nên phụ thuộc thứ tự khi contract không bảo đảm thứ tự

Nếu implementation dùng flatMap và không bảo đảm ordering, đừng viết test giả định thứ tự đầu vào. Kiểm tra theo ID hoặc tập hợp kết quả nếu contract chỉ cam kết các phần tử cuối cùng, không cam kết thứ tự.

Ngược lại, nếu contract yêu cầu ordering, test phải xác nhận thứ tự rõ ràng để ngăn thay đổi implementation làm sai hành vi.

### 10.7. Tách unit test và integration test

Unit test kiểm tra publisher và operator trong một service. Integration test kiểm tra serialization, route mapping, metadata, transport và error mapping. Một test dùng Flux.just không chứng minh kết nối RSocket thực tế hoạt động.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Quên gọi verify | Kịch bản chưa thực sự chạy và assertion không được xác nhận. | Kết thúc mỗi scenario bằng phương thức verify phù hợp. |
| Chỉ expectNext, không kiểm tra terminal signal | Bỏ lọt phần tử dư hoặc stream không hoàn tất. | Dùng verifyComplete hoặc expectError rồi verify. |
| Dùng block trong test reactive | Bỏ qua demand và cancellation. | Dùng StepVerifier. |
| Dùng Thread.sleep để chờ timer | Test chậm và dễ flaky. | Dùng virtual time. |
| Tạo timer trước withVirtualTime | Publisher có thể giữ scheduler thật. | Tạo publisher trong Supplier của withVirtualTime. |
| Không cấp demand trong test backpressure | Không kiểm tra được luồng phát theo demand. | Khởi tạo với initial request 0 rồi dùng thenRequest. |
| Nhầm cancel với complete | Test kết luận sai vòng đời publisher. | Dùng thenCancel và kiểm tra SignalType.CANCEL. |
| Coi cancellation là rollback nghiệp vụ | Side effect đã commit có thể bị mất dấu. | Lưu trạng thái bền vững và dùng idempotency. |
| Assert exception class nội bộ qua RSocket | Test phụ thuộc vào mapping không được contract bảo đảm. | Kiểm tra error code hoặc semantics công khai. |
| Unit test được coi là integration test | Không phát hiện lỗi transport, codec hoặc route. | Bổ sung test RSocket với server/transport thật. |
| Dùng TestPublisher trong production | Trộn công cụ test với logic ứng dụng. | Chỉ dùng TestPublisher trong test source. |

## 12. Checklist cho một reactive test tốt

- [ ] Test subscribe vào đúng Publisher cần kiểm tra.
- [ ] Có assertion cho giá trị và thứ tự khi contract yêu cầu.
- [ ] Xác nhận complete hoặc error rõ ràng.
- [ ] Kiểm tra empty Mono nếu đó là kết quả hợp lệ.
- [ ] Có test lỗi sau khi stream đã phát dữ liệu nếu luồng có thể xảy ra.
- [ ] Điều khiển demand nếu backpressure là yêu cầu quan trọng.
- [ ] Kiểm tra cancellation và cleanup nếu resource được giữ trong stream.
- [ ] Dùng virtual time cho timer, timeout hoặc retry backoff.
- [ ] Dùng TestPublisher khi cần điều khiển tín hiệu upstream.
- [ ] Dùng verify(Duration) cho test có thể chờ.
- [ ] Không giả định cancel đồng nghĩa server rollback.
- [ ] Có integration test riêng cho RSocket transport, route và codec khi cần.

## Tài liệu tham khảo

- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, TestPublisher và virtual time.
- [Reactor Test Javadoc — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): API tạo scenario, assertion và verification.
- [Reactor Test Javadoc — TestPublisher](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): publisher điều khiển được dành cho test.
- [Project Reactor Reference — Core Features](https://projectreactor.io/docs/core/release/reference/coreFeatures.html): Mono, Flux, demand và cancellation.
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, route mapping và annotated responders.
- [RSocket Protocol](https://rsocket.io/about/protocol/): request frames, stream lifecycle, CANCEL và ERROR.
