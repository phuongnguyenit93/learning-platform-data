# PublisherProbe để kiểm tra nhánh fallback được đăng ký

## 1. Vì sao chỉ kiểm tra giá trị trả về chưa đủ?

Trong một luồng **Reactive** dùng Project Reactor, logic thường chọn giữa **nguồn chính (primary)** và **nhánh dự phòng (fallback)**. Ví dụ: đọc cache; nếu không tìm thấy thì gọi nguồn dự phòng; hoặc thực thi một tác vụ, nếu không có lệnh thì gửi tín hiệu “không có việc”.

~~~text
                       primary Publisher
                               |
                     subscribe / request
                               |
                   có onNext? / onComplete?
                        /             \
                  có giá trị       hoàn tất rỗng
                      |                  |
                      v                  v
                giữ kết quả       subscribe fallback
                      |                  |
                      +--------+---------+
                               |
                        downstream
~~~

Một bài test dùng `StepVerifier` để so sánh kết quả cuối cùng rất hữu ích:

~~~java
StepVerifier.create(primary.switchIfEmpty(fallback))
        .expectNext("cached")
        .verifyComplete();
~~~

Nhưng kết quả `"cached"` **chưa luôn chứng minh nhánh fallback đã chạy**: nguồn chính cũng có thể phát ra đúng `"cached"`. Trường hợp khó hơn là **`Mono<Void>`**: nguồn chính và fallback đều chỉ hoàn tất, nên cả hai đường đi đều cho cùng tín hiệu `onComplete`, không có `onNext` để phân biệt.

`PublisherProbe` từ artifact `reactor-test` giải quyết vấn đề này. Nó bọc một `Publisher` và ghi nhận xem nhánh ấy **được subscribe, được request hay bị cancel**. Sau khi test đã thực sự subscribe luồng bằng `StepVerifier`, ta kiểm tra probe để xác nhận đường đi.

**Ý quan trọng của tên bài:** “fallback được đăng ký” nên hiểu ở mức **nhánh fallback thực sự được chọn và nhận subscription**, không phải một bean Spring được đăng ký trong `ApplicationContext`. Chỉ đặt `fallback` vào biểu thức `switchIfEmpty(...)` là *khai báo/assembly* luồng; **không đủ bằng chứng fallback đã được sử dụng**.

## 2. Ba giai đoạn phải phân biệt: assembly, subscription và signal

Reactive Streams có nguyên tắc then chốt: phần lớn publisher Reactor là **lazy/cold**. Khi viết một chuỗi operator, ta thường **xây dựng mô tả công việc** chứ chưa thực thi phần lớn hành vi.

~~~java
PublisherProbe<String> backup = PublisherProbe.of(
        Mono.just("from-backup")
);

Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(backup.mono());

// Tới đây mới là assembly: chưa có subscriber downstream.
~~~

Trong đoạn trên, `backup.mono()` tạo publisher bọc probe, nhưng **chưa có downstream subscribe**. Chỉ khi test gọi:

~~~java
StepVerifier.create(result)
        .expectNext("from-backup")
        .verifyComplete();

backup.assertWasSubscribed();
~~~

thì có sự kiện subscribe, dữ liệu và completion được kiểm tra.

Bốn loại tín hiệu thường cần tách bạch:

| Sự kiện | Có nghĩa gì? | Ví dụ |
| --- | --- | --- |
| `subscribe` | Subscriber đăng ký theo dõi Publisher; nhánh đã được đi vào | `fallback.assertWasSubscribed()` |
| `request(n)` | Subscriber đưa **demand** cho dữ liệu theo Reactive Streams | `fallback.assertWasRequested()` |
| `onNext(value)` | Có phần tử dữ liệu được phát | `StepVerifier.expectNext(...)` |
| `onComplete` / `onError` / cancellation | Kết thúc bình thường, kết thúc lỗi hoặc hủy subscription | `verifyComplete()`, `expectError...`, `assertWasCancelled()` |

**Subscribe không có nghĩa đã phát ra giá trị.** Một `Mono.empty()` được subscribe sẽ hoàn tất ngay mà không có `onNext`. Tương tự, `assertWasRequested()` chỉ khẳng định có ít nhất một yêu cầu dữ liệu, **không khẳng định publisher đã phát dữ liệu**.

### Khi nào switchIfEmpty chọn fallback?

`Mono<T>.switchIfEmpty(alternative)` và `Flux<T>.switchIfEmpty(alternative)` chuyển sang alternative khi **upstream hoàn tất mà không phát phần tử nào**.

- `Mono.just("A")`: phát một phần tử → **không** subscribe fallback.
- `Mono.empty()`: hoàn tất không phần tử → **có** subscribe fallback.
- `Mono.error(exception)`: kết thúc lỗi → **không** phải trường hợp empty; `switchIfEmpty` không xử lý lỗi này.
- `Mono.never()`: không phát, không hoàn tất, không báo lỗi → **chưa** có điều kiện chuyển sang fallback; nếu hủy test, fallback vẫn không được subscribe.

Đừng đồng nhất “chưa thấy dữ liệu trong một khoảng thời gian” với “nguồn đã hoàn tất rỗng”. Muốn fallback theo timeout hoặc error, cần operator có ngữ nghĩa tương ứng như `timeout(...)`, `onErrorResume(...)`.

## 3. API chính của reactor.test.publisher.PublisherProbe

Import chính xác:

~~~java
import reactor.test.publisher.PublisherProbe;
import reactor.test.StepVerifier;
~~~

Tập công cụ thường dùng:

| API | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `PublisherProbe.empty()` | Tạo probe không phát dữ liệu, chỉ hoàn tất | Đặc biệt hữu ích với `Mono<Void>` |
| `PublisherProbe.of(Publisher)` | Bọc Publisher thật và giữ nguyên tín hiệu của nó | Thích hợp khi fallback phải trả dữ liệu |
| `probe.mono()` | Lấy `Mono<T>` đã gắn probe | Cho `Mono.switchIfEmpty` |
| `probe.flux()` | Lấy `Flux<T>` đã gắn probe | Cho `Flux.switchIfEmpty` |
| `probe.assertWasSubscribed()` | Khẳng định đã subscribe ít nhất một lần | Dùng sau `StepVerifier.verify...` |
| `probe.assertWasNotSubscribed()` | Khẳng định nhánh không được subscribe | Quan trọng cho đường primary có dữ liệu |
| `probe.assertWasRequested()` / `assertWasNotRequested()` | Kiểm tra sự kiện demand | Không thay assertion trên `onNext` |
| `probe.assertWasCancelled()` / `assertWasNotCancelled()` | Kiểm tra cancellation | Phân biệt hoàn tất bình thường với bị hủy |

Một probe có thể tạo cả `mono()` và `flux()`, nhưng **cả hai dùng chung trạng thái quan sát của cùng probe**. Không dùng cùng probe cho nhiều ca độc lập rồi hiểu `assertWasSubscribed()` là chứng cứ chỉ cho ca cuối; lần subscribe trước có thể đã khiến trạng thái true.

### empty() khác of(...) thế nào?

~~~java
PublisherProbe<Void> completionOnly = PublisherProbe.empty();
Mono<Void> cleanup = completionOnly.mono();
~~~

Publisher này chỉ phát tín hiệu hoàn tất, cho phép test quan sát nhánh **không có giá trị**. Với fallback có giá trị:

~~~java
PublisherProbe<String> withValue = PublisherProbe.of(
        Mono.just("backup-result")
);
Mono<String> backup = withValue.mono();
~~~

Probe thứ hai **phát lại giá trị `"backup-result"` từ Publisher được bọc**, đồng thời ghi nhận subscription/request/cancel. Nó không tự sản sinh giá trị khác hay biến một nguồn lỗi thành thành công.

**PublisherProbe không khẳng định giá trị, thứ tự item hay exception.** Nó ghi nhận một số tín hiệu về việc sử dụng nhánh. Dùng `StepVerifier` cho dữ liệu/completion/error, kết hợp `PublisherProbe` cho control flow; có thể dùng Mockito `verify` để kiểm tra lời gọi collaborator ở tầng Java khi phù hợp.

## 4. Ví dụ nhanh nhất: chứng minh fallback được subscribe

Ví dụ chỉ cần Reactor và reactor-test:

~~~java
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("from-cache")
);

Mono<String> flow = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

StepVerifier.create(flow)
        .expectNext("from-cache")
        .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
fallback.assertWasNotCancelled();
~~~

Vì upstream là `Mono.empty()`, khi test subscribe, Reactor chuyển sang fallback. Test chứng minh **hai hợp đồng**: giá trị `from-cache` được phát đúng, và fallback thực sự được subscribe.

Đổi nguồn chính:

~~~java
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.just("from-cache")
);

Mono<String> flow = Mono.just("from-primary")
        .switchIfEmpty(fallback.mono());

StepVerifier.create(flow)
        .expectNext("from-primary")
        .verifyComplete();

fallback.assertWasNotSubscribed();
fallback.assertWasNotRequested();
~~~

Ở đây, kết quả từ primary được giữ nguyên và fallback không chạy. **Hai test đối xứng** giúp phát hiện bug mà một ca happy path đơn lẻ bỏ lọt.

**Quan trọng về cấp độ kiểm thử:** các đoạn trên là **body code minh họa**, không phải tệp Java độc lập có `class`/`import`. Phần 7 và 8 trình bày đầy đủ các tệp test JUnit Jupiter biên dịch được.

## 5. Bẫy đặc biệt: Mono<Void> không có giá trị để quan sát

Một `Mono<Void>` có thể biểu diễn “hoàn tất tác vụ” nhưng **không phát phần tử**. Vì thế hai nhánh đều có thể cho cùng kết quả:

~~~text
Nguồn có lệnh "refresh"
    → gateway.execute("refresh") trả Mono<Void>
    → onComplete

Nguồn không có lệnh
    → thực thi fallback Mono<Void>
    → onComplete
~~~

Dùng `StepVerifier.create(result).verifyComplete()` cho cả hai trường hợp đều PASS; **không biết đường nào đã chạy** nếu thiếu probe.

Một sai lầm hay gặp:

~~~java
// Sai với mục tiêu chỉ fallback khi NGUỒN LỆNH trống.
return commandSource
        .flatMap(gateway::execute)  // execute trả Mono<Void>.
        .switchIfEmpty(emptyFallback);
~~~

Dù `commandSource` có phát lệnh, `gateway.execute(...)` thường hoàn tất **không có onNext**, làm kết quả của `flatMap` rỗng. `switchIfEmpty` đặt **sau** đó nhìn thấy chuỗi rỗng và có thể subscribe fallback **dù lệnh đã được thực thi**.

Đây là lỗi ngữ nghĩa do **đặt operator sai vị trí**, không phải lỗi timing hay Mockito.

### Thiết kế đúng trong ví dụ

Đặt `switchIfEmpty` tại **vị trí còn giữ tín hiệu lệnh `String`**, trước khi chuyển lệnh thành `Mono<Void>`:

~~~java
Mono<String> selected = commandSource
        .switchIfEmpty(emptyFallback.then(Mono.<String>empty()));

return selected.flatMap(gateway::execute).then();
~~~

Khi primary có lệnh, `selected` phát `String`, bỏ qua fallback rồi chuyển sang `gateway.execute`. Khi primary rỗng, publisher thay thế **subscribe emptyFallback**, chờ nó hoàn tất, rồi hoàn tất rỗng mà **không gọi gateway**.

`emptyFallback.then(Mono.<String>empty())` có cùng kiểu `Mono<String>` mà `switchIfEmpty` cần nhưng vẫn giữ hành vi `Mono<Void>` của fallback. Cách này không cần giả tạo một “sentinel value” trong domain.

**Quy tắc đọc chuỗi Reactor:** `switchIfEmpty` không biết nghiệp vụ của bạn định nghĩa “có lệnh” ra sao; nó chỉ xét việc **upstream tại đúng vị trí operator có onNext hay không**. Những toán tử như `then()`, `ignoreElement()` hoặc `flatMap` sang Publisher chỉ hoàn tất có thể thay đổi trạng thái có/không onNext.

## 6. Cấu trúc dự án và dependencies chạy được

Ví dụ chính là **unit test** cho một component reactive có thể dùng trong ứng dụng Spring Boot 3.5.x, Java 17/JUnit Jupiter, Project Reactor và Mockito. Ta **không khởi động Spring context** vì mục tiêu là chứng minh đường đi Publisher, không phải bean wiring hay HTTP.

Tệp chính:

~~~text
src/main/java/com/example/reactivetest/
  CommandGateway.java
  CommandFlow.java
src/test/java/com/example/reactivetest/
  CommandFlowTest.java
  PublisherProbeBranchTest.java
~~~

Với dự án Spring Boot 3.5.x dùng Gradle Groovy DSL đã có Spring Boot plugin, repositories, Java 17 toolchain và dependency management, cấu hình liên quan là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`reactor-test` cung cấp `StepVerifier` và `PublisherProbe`. Khai báo rõ `testImplementation 'io.projectreactor:reactor-test'` để ví dụ không phụ thuộc giả định nó được kéo gián tiếp từ một starter khác. Spring Boot BOM quản lý phiên bản Reactor phù hợp, nên không tự trộn các version `reactor-core` và `reactor-test` không tương thích.

`spring-boot-starter-webflux` cung cấp `Mono`/`Flux` cùng stack Reactive; nếu đây chỉ là module Java thuần dùng Reactor, có thể khai báo `reactor-core` và `reactor-test` trực tiếp cùng JUnit/Mockito thay vì starter WebFlux. **Không cần `@SpringBootTest`** cho ví dụ unit test.

## 7. Ví dụ Java 17 đầy đủ: nhánh fallback Mono<Void>

### 7.1. Interface đại diện tác vụ thật

**Tệp `src/main/java/com/example/reactivetest/CommandGateway.java`:**

~~~java
package com.example.reactivetest;

import reactor.core.publisher.Mono;

public interface CommandGateway {
    Mono<Void> execute(String command);
}
~~~

Trong sản phẩm thật, implementation có thể ghi audit log, gửi message hoặc gọi một API bất đồng bộ. Unit test sẽ mock gateway để không gây side effect bên ngoài.

### 7.2. Luồng lựa chọn nhánh với switchIfEmpty đúng vị trí

**Tệp `src/main/java/com/example/reactivetest/CommandFlow.java`:**

~~~java
package com.example.reactivetest;

import java.util.Objects;

import reactor.core.publisher.Mono;

public final class CommandFlow {
    private final CommandGateway gateway;

    public CommandFlow(CommandGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    public Mono<Void> processOrFallback(
            Mono<String> commandSource,
            Mono<Void> emptyFallback
    ) {
        Objects.requireNonNull(commandSource, "commandSource");
        Objects.requireNonNull(emptyFallback, "emptyFallback");

        Mono<String> selected = commandSource.switchIfEmpty(
                emptyFallback.then(Mono.<String>empty())
        );

        return selected.flatMap(gateway::execute).then();
    }
}
~~~

Hợp đồng của phương thức:

- Nguồn chính phát một lệnh: gọi `gateway.execute(command)` và đợi Publisher trả về kết thúc; **không dùng fallback**.
- Nguồn chính hoàn tất rỗng: subscribe và hoàn tất `emptyFallback`; **không gọi gateway**.
- Nguồn chính báo lỗi: truyền lỗi xuống downstream; **không tự dùng fallback**.
- Gateway báo lỗi: truyền lỗi xuống downstream; **không tự dùng fallback**.
- Luồng trả về `Mono<Void>`, vì caller chỉ cần biết hoàn tất hay lỗi, không cần một kết quả kiểu String.

`Objects.requireNonNull` kiểm tra tham số object khi gọi method, không tự subscribe hoặc chặn/block luồng. Các hoạt động với source/gateway/fallback do Reactor điều phối khi downstream subscribe.

### 7.3. Bộ test JUnit Jupiter và MockitoExtension

**Tệp `src/test/java/com/example/reactivetest/CommandFlowTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CommandFlowTest {

    @Mock
    CommandGateway gateway;

    CommandFlow flow;

    @BeforeEach
    void setUp() {
        flow = new CommandFlow(gateway);
    }

    @Test
    void emptyPrimary_subscribesFallbackAndDoesNotRunGateway() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        Mono<Void> result = flow.processOrFallback(
                Mono.empty(),
                fallback.mono()
        );

        StepVerifier.create(result)
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
        verifyNoInteractions(gateway);
    }

    @Test
    void nonEmptyPrimary_executesGatewayWithoutFallback() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();
        PublisherProbe<Void> executePublisher = PublisherProbe.of(
                Mono.empty()
        );

        when(gateway.execute("refresh"))
                .thenReturn(executePublisher.mono());

        Mono<Void> result = flow.processOrFallback(
                Mono.just("refresh"),
                fallback.mono()
        );

        StepVerifier.create(result)
                .verifyComplete();

        verify(gateway).execute("refresh");

        executePublisher.assertWasSubscribed();
        executePublisher.assertWasRequested();
        executePublisher.assertWasNotCancelled();

        fallback.assertWasNotSubscribed();
        fallback.assertWasNotRequested();
    }

    @Test
    void sourceError_doesNotTriggerEmptyFallback() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        Mono<Void> result = flow.processOrFallback(
                Mono.error(new IllegalStateException("source unavailable")),
                fallback.mono()
        );

        StepVerifier.create(result)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "source unavailable".equals(
                                        error.getMessage()
                                ))
                .verify();

        fallback.assertWasNotSubscribed();
        verifyNoInteractions(gateway);
    }

    @Test
    void gatewayError_propagatesWithoutUsingFallback() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        when(gateway.execute("refresh"))
                .thenReturn(Mono.error(
                        new IllegalArgumentException("bad command")
                ));

        Mono<Void> result = flow.processOrFallback(
                Mono.just("refresh"),
                fallback.mono()
        );

        StepVerifier.create(result)
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                                && "bad command".equals(error.getMessage()))
                .verify();

        verify(gateway).execute("refresh");
        fallback.assertWasNotSubscribed();
    }

    @Test
    void neverCompletingPrimary_doesNotSelectFallbackBeforeCancel() {
        PublisherProbe<Void> fallback = PublisherProbe.empty();

        Mono<Void> result = flow.processOrFallback(
                Mono.never(),
                fallback.mono()
        );

        StepVerifier.create(result)
                .thenCancel()
                .verify();

        fallback.assertWasNotSubscribed();
        verifyNoInteractions(gateway);
    }
}
~~~

**Giải thích các assertion:**

| Ca | Kết quả `StepVerifier` | Kết quả probe | Collaborator |
| --- | --- | --- | --- |
| Primary rỗng | `verifyComplete()` | Fallback subscribed + requested, không cancel | Gateway không được gọi |
| Primary có `"refresh"` | `verifyComplete()` | Fallback không subscribed; publisher của gateway subscribed | Gateway gọi đúng lệnh |
| Primary báo lỗi | `expectErrorMatches(...)` | Fallback không subscribed | Gateway không được gọi |
| Gateway báo lỗi | `expectErrorMatches(...)` | Fallback không subscribed | Gateway đã được gọi |
| Primary không bao giờ complete | Test chủ động `thenCancel()` | Fallback không subscribed | Gateway không được gọi |

Trong ca có lệnh, test dùng **hai probe khác nhau**. `verify(gateway).execute("refresh")` xác nhận method mock được gọi, còn `executePublisher.assertWasSubscribed()` xác nhận **Mono do gateway trả về được downstream thực sự subscribe**. Đây là hai sự kiện khác nhau, đặc biệt quan trọng với API reactive: gọi một method trả `Mono` chưa đồng nghĩa side effect nằm bên trong Publisher đã chạy.

`verifyComplete()` không in output và không trả dữ liệu (luồng là `Mono<Void>`); probe là bằng chứng điều hướng giữa hai nhánh. Mỗi test tạo probe mới để không bị trạng thái subscription từ ca trước.

## 8. Ví dụ đầy đủ cho fallback có dữ liệu và Flux

`PublisherProbe.empty()` hữu ích cho nhánh chỉ hoàn tất; nếu fallback phải **phát dữ liệu**, dùng `PublisherProbe.of(...)` để giữ nguyên tín hiệu của Publisher được bọc.

**Tệp `src/test/java/com/example/reactivetest/PublisherProbeBranchTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class PublisherProbeBranchTest {

    @Test
    void emptyMono_subscribesValueFallback() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("cached")
        );

        Mono<String> result = Mono.<String>empty()
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("cached")
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void nonEmptyMono_doesNotSubscribeValueFallback() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Mono.just("cached")
        );

        Mono<String> result = Mono.just("live")
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
                .expectNext("live")
                .verifyComplete();

        fallback.assertWasNotSubscribed();
        fallback.assertWasNotRequested();
    }

    @Test
    void emptyFlux_subscribesMultiValueFallback() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Flux.just("backup-A", "backup-B")
        );

        Flux<String> result = Flux.<String>empty()
                .switchIfEmpty(fallback.flux());

        StepVerifier.create(result)
                .expectNext("backup-A", "backup-B")
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }

    @Test
    void cancellingFallbackIsObservable() {
        PublisherProbe<String> fallback = PublisherProbe.of(
                Flux.<String>never()
        );

        Flux<String> result = Flux.<String>empty()
                .switchIfEmpty(fallback.flux());

        StepVerifier.create(result)
                .thenCancel()
                .verify();

        fallback.assertWasSubscribed();
        fallback.assertWasCancelled();
    }

    @Test
    void errorFallbackUsesOnErrorResumeInsteadOfSwitchIfEmpty() {
        PublisherProbe<String> recovery = PublisherProbe.of(
                Mono.just("offline-cache")
        );

        Mono<String> result = Mono.<String>error(
                new IllegalStateException("remote unavailable")
        ).onErrorResume(error -> recovery.mono());

        StepVerifier.create(result)
                .expectNext("offline-cache")
                .verifyComplete();

        recovery.assertWasSubscribed();
        recovery.assertWasRequested();
    }
}
~~~

Trong cả năm ca, **`StepVerifier`** khẳng định dữ liệu, completion hoặc thao tác cancellation; **`PublisherProbe`** khẳng định nhánh nào được subscribe và signal nào xảy ra trong nhánh đó. Với `Flux`, dùng `probe.flux()` chứ không `probe.mono()` nếu cần truyền nhiều phần tử.

### Một chú ý về cancellation

Trong ca `Flux.never()`, fallback **được subscribe** nhưng không phát tín hiệu dữ liệu/completion. `StepVerifier.thenCancel()` hủy subscription, do đó `assertWasCancelled()` là kỳ vọng đúng.

**Không đặt `assertWasNotCancelled()` vào mọi test theo thói quen.** Một nhánh có thể được subscribe, request và sau đó bị cancel hợp lệ bởi `take(1)`, timeout, hoặc subscriber hủy. Hãy kiểm tra cancellation theo đúng vòng đời được thiết kế.

### Một chú ý về việc probe không xác định nguồn giá trị

Nếu kết quả là `"cached"`, `StepVerifier.expectNext("cached")` chỉ biết giá trị. `fallback.assertWasSubscribed()` mới xác nhận fallback đã tham gia. Ngược lại, `assertWasSubscribed()` không chứng minh giá trị là `"cached"`. Hai bộ assertion bổ sung cho nhau chứ không thay thế.

## 9. Bằng chứng đúng: kiểm tra cả đường fallback và đường primary

Một bộ test chỉ có ca primary rỗng là chưa đủ. Nếu ai đó sửa code thành “luôn gọi fallback”, ca fallback vẫn PASS. Cần ít nhất hai hướng đối lập:

~~~text
Given primary = empty
When  StepVerifier subscribe pipeline
Then  fallback được subscribe/request; output đúng

Given primary = just(value)
When  StepVerifier subscribe pipeline
Then  fallback không được subscribe; output từ primary
~~~

Với thao tác có side effect, cần thêm:

~~~text
Given primary = empty
Then  gateway không được gọi

Given primary = just(command)
Then  gateway được gọi với command
  And publisher trả từ gateway được subscribe
  And fallback không được subscribe
~~~

**Phương pháp kiểm thử điều khiển luồng:**

- Assert **tín hiệu downstream** (value/completion/error) để xác nhận hợp đồng mà caller quan sát.
- Assert **subscription của fallback** để chứng minh branch được sử dụng.
- Assert **subscription của publisher thực thi** nếu muốn chứng minh tác vụ reactive thực sự chạy, không chỉ method Java được gọi.
- Dùng Mockito `verify` cho giao tiếp bên ngoài Publisher khi cần.
- Không ghi test dựa trên số log, thứ tự không được bảo đảm hoặc biến `static` chia sẻ giữa test.

Một mock trả `Mono.empty()` không có onNext; nếu chỉ dùng `verify(mock).method(...)`, test không chứng minh luồng đã subscribe Mono ấy. Bọc Mono trả về bằng `PublisherProbe.of(...)` khi đó là mục tiêu.

## 10. onErrorResume không phải switchIfEmpty

Trong Reactor:

| Điều kiện | `switchIfEmpty(fallback)` | `onErrorResume(error -> fallback)` |
| --- | --- | --- |
| Upstream phát dữ liệu và complete | Không dùng fallback | Không dùng fallback |
| Upstream complete **không phát gì** | **Subscribe fallback** | Không dùng fallback |
| Upstream phát `onError` | Lỗi truyền đi (trừ operator khác) | **Có thể subscribe recovery** |
| Upstream `never()` | Không tự trigger | Không tự trigger |

Nếu nghiệp vụ nói “cache miss thì gọi nguồn dự phòng”, `switchIfEmpty` thích hợp khi cache miss biểu diễn bằng `Mono.empty()`. Nếu nghiệp vụ nói “remote lỗi thì dùng cache”, `onErrorResume` có thể phù hợp nhưng cần giới hạn loại lỗi được phép fallback.

Ví dụ chỉ dùng fallback khi lỗi thuộc một loại:

~~~java
Mono<String> recovered = primary.onErrorResume(
        java.io.IOException.class,
        error -> fallbackProbe.mono()
);
~~~

Đây là **đoạn minh họa** cần `primary` kiểu `Mono<String>`, `fallbackProbe` kiểu `PublisherProbe<String>` và import phù hợp. Operator này dùng fallback khi upstream phát `IOException`; các lỗi khác tiếp tục truyền đi theo ngữ nghĩa của `onErrorResume`.

**Không dùng `switchIfEmpty` để bắt exception.** Tương tự, không dùng `onErrorResume` để xử lý `Mono.empty()` vì empty không phải error. Test cần kiểm tra riêng cả empty và error khi API có cả hai trường hợp.

### Cẩn thận với defaultIfEmpty

`defaultIfEmpty(value)` thay chuỗi rỗng bằng **một giá trị tĩnh**; không có `Publisher` thay thế để gắn `PublisherProbe` trực tiếp. Nếu muốn kiểm tra một luồng fallback thực sự, dùng `switchIfEmpty(fallbackPublisher)`.

Với `Mono<Void>`, không có giá trị `Void` hợp lệ để phát làm default theo cách thông thường, nên `PublisherProbe.empty()` + `switchIfEmpty` hoặc thiết kế lại nơi đặt operator thường phù hợp hơn.

## 11. Lazy fallback: đăng ký Publisher chưa đồng nghĩa thực thi factory

Một khác biệt tinh tế:

~~~java
Mono<String> result = primary.switchIfEmpty(
        expensiveFallbackFactory()
);
~~~

Ở đây **lời gọi Java** `expensiveFallbackFactory()` xảy ra lúc xây dựng chuỗi, vì argument được Java đánh giá trước khi gọi `switchIfEmpty`. Nếu factory chỉ trả về cold `Mono` và không làm side effect, thường không sao. Nhưng nếu factory **đọc file, ghi log, gọi API đồng bộ hoặc thay đổi state ngay trong thân method**, công việc đó có thể xảy ra **ngay cả khi primary có giá trị và fallback không bao giờ được subscribe**.

Muốn trì hoãn **chính việc gọi factory** tới lúc fallback được chọn:

~~~java
Mono<String> result = primary.switchIfEmpty(
        Mono.defer(() -> expensiveFallbackFactory())
);
~~~

`Mono.defer` nhận Supplier tạo publisher **khi có subscription** vào nhánh của nó, không phải tại lúc lắp đặt operator. Nếu không có fallback subscription, factory không được gọi.

Có thể bọc để kiểm tra đường đi:

~~~java
PublisherProbe<String> fallback = PublisherProbe.of(
        Mono.defer(() -> expensiveFallbackFactory())
);

Mono<String> result = primary.switchIfEmpty(fallback.mono());
~~~

`fallback.assertWasNotSubscribed()` chứng minh Publisher bọc không bị subscribe. **Nó không tự chứng minh một factory tùy ý không bị gọi từ một vị trí khác**, ví dụ lời gọi nằm ngoài `Mono.defer`. Nếu kiểm tra số lần factory thật sự được gọi là yêu cầu quan trọng, dùng Mockito `verify(..., never())` hoặc counter được cô lập bên cạnh probe.

### Mono.defer có giải quyết mọi vấn đề timing không?

Không. Nó giúp **lazy assembly** cho nguồn do factory tạo; logic trong publisher vẫn phải nonblocking, có exception handling đúng, và test phải subscribe thì mới quan sát được. Tránh gọi `block()` trong Reactor event loop và đừng xây dựng hot publisher gây side effect ngay khi tạo rồi cho rằng `Mono.defer` ở phía ngoài có thể đảo ngược mọi hành vi đã xảy ra.

## 12. Backpressure, request và cancel: ba câu hỏi khác nhau

`PublisherProbe` làm rõ ba sự kiện:

- **Subscribed:** nhánh được đi vào. `assertWasSubscribed()`.
- **Requested:** subscriber đã gửi demand dương tới probe. `assertWasRequested()`. Không chứng minh item nào đã được phát.
- **Cancelled:** subscriber/chuỗi downstream đã hủy subscription trước khi completion/error bình thường. `assertWasCancelled()`.

`StepVerifier.create(publisher)` theo cấu hình thường dùng sẽ tự tạo subscription và demand phù hợp với các kỳ vọng. Với những test muốn kiểm soát demand, có thể chỉ định `initialRequest`:

~~~java
PublisherProbe<String> backup = PublisherProbe.of(
        Mono.just("ready")
);

StepVerifier.create(
        Mono.<String>empty().switchIfEmpty(backup.mono()),
        0
)
        .thenRequest(1)
        .expectNext("ready")
        .verifyComplete();

backup.assertWasSubscribed();
backup.assertWasRequested();
~~~

Đây là đoạn body code minh họa; `StepVerifier.create(..., 0)` khởi đầu với demand 0, rồi `thenRequest(1)` cho phép một phần tử đi qua. Với chuỗi phức tạp có prefetch/request từ operator, **không suy luận exact request count từ `assertWasRequested()`**, vì method này chỉ xác nhận “đã có request”. Khi cần kiểm tra request count/backpressure chính xác, phải dùng công cụ và contract phù hợp hơn.

**Không tái sử dụng probe giữa nhiều subscribe** nếu muốn assert riêng từng lần; API probe có thể ghi nhận trạng thái tích lũy. Với một test có retry/repeat, xác định xem bạn cần “ít nhất một lần” hay **số subscription cụ thể**. Các assert `WasSubscribed` đơn giản không tự bảo đảm đúng một lần.

## 13. PublisherProbe, TestPublisher, StepVerifier và Mockito khác nhau

| Công cụ | Trả lời câu hỏi | Không tự làm được |
| --- | --- | --- |
| `StepVerifier` | Luồng phát giá trị, hoàn tất/lỗi, timing/cancel như kỳ vọng? | Không cho biết một fallback có tín hiệu giống primary đã được dùng nếu không có probe |
| `PublisherProbe` | Publisher/nhánh đã được subscribe, request, cancel? | Không xác minh chi tiết giá trị, thứ tự hoặc thông điệp lỗi |
| `TestPublisher` | Điều khiển phát `next`/`complete`/`error` từ upstream trong test | Không thay thế toàn bộ assertion về kết quả downstream |
| Mockito `@Mock`/`verify` | Method Java của collaborator được gọi với tham số nào? | Không bảo đảm Publisher mà method trả về được subscribe |
| `@WebFluxTest` + `WebTestClient` | HTTP route/filter/serialization của WebFlux hoạt động ra sao? | Không tự kiểm tra nhánh fallback nội bộ nếu response giống nhau |

### Vì sao không luôn dùng TestPublisher?

`TestPublisher` thích hợp khi test cần **tự chủ động phát tín hiệu** theo một lịch có kiểm soát. `PublisherProbe` là lựa chọn đơn giản hơn khi chỉ cần biết **một publisher dự phòng có được sử dụng hay không** và Publisher thật có thể là `Mono.empty()`, `Mono.just(...)` hoặc `Flux.just(...)`.

Dù `TestPublisher` có liên quan đến giao diện probe trong API Reactor, phần lớn test control-flow nên dùng factory `PublisherProbe.empty()` / `PublisherProbe.of(...)` theo hướng dẫn Reactor, thay vì quản lý hàng loạt tín hiệu thủ công không cần thiết.

### Vì sao không chỉ dùng AtomicBoolean?

Một `AtomicBoolean` trong `doOnSubscribe` hoặc `doOnNext` cũng có thể ghi nhận một số sự kiện, nhưng nếu phải kiểm tra subscribe/request/cancel qua nhiều test, nó tạo boilerplate và dễ bỏ sót trường hợp. `PublisherProbe` được thiết kế trực tiếp cho công việc đó. Ngược lại, nếu mục tiêu là chứng minh **business side effect đã commit**, một subscription assertion không đủ; cần assertion mức nghiệp vụ hoặc integration test phù hợp.

## 14. Khi đưa kỹ thuật vào Spring Boot / Spring WebFlux

Ví dụ chính dùng **JUnit Jupiter + MockitoExtension**, không phải `@SpringBootTest`. Đây là lựa chọn đúng nếu bạn đang kiểm tra phương thức Java trả `Mono`/`Flux` và một số nhánh operator. Framework WebFlux không phải được nạp lên thành server để test một `switchIfEmpty`.

Khi phương thức nằm trong Spring service:

~~~java
@Service
public class QuoteLookupService {
    private final QuoteRepository repository;
    private final QuoteFallbackClient fallbackClient;

    public Mono<Quote> find(String id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.defer(
                        () -> fallbackClient.load(id)
                ));
    }
}
~~~

Đây là **skeleton minh họa**, không phải tệp độc lập; nó cần field/constructor, các interface, model và import phù hợp. Trong unit test, bạn có thể dùng Mockito mock `QuoteRepository` và `QuoteFallbackClient`, sau đó dùng `PublisherProbe.of(Mono.just(...))` làm Publisher mà client trả về. Nếu muốn kiểm tra **factory method được gọi hay không**, thêm Mockito `verify(fallbackClient).load(id)`/`verify(..., never())`.

Một WebFlux HTTP slice `@WebFluxTest` thường kiểm tra controller/request/response bằng `WebTestClient`, mock những service ngoài slice. Nó không phải nơi tốt nhất để chứng minh mọi nhánh bên trong service **đã bị mock đi**. Nếu test cần chứng minh service thật cùng Spring wiring, cân nhắc `@SpringBootTest`/`@Import` phù hợp; vẫn có thể áp dụng `PublisherProbe` trên Publisher trả từ mock repository/client.

**Không dùng `block()` chỉ để tạo điều kiện assert** trong một test reactive. `StepVerifier` tự subscribe và quản lý expectation phù hợp; khi đã dùng `WebTestClient`, client test cũng kích hoạt subscription cho luồng HTTP theo framework.

## 15. Gỡ lỗi một ca fallback có kết quả sai

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `assertWasNotSubscribed` FAIL dù primary có dữ liệu | `switchIfEmpty` đặt sau `then()` hoặc chuyển thành `Mono<Void>` | Chuyển `switchIfEmpty` đến vị trí upstream vẫn phát giá trị cần xét |
| `assertWasSubscribed` FAIL khi primary rỗng | Không có downstream subscription, hoặc pipeline không dùng probe đã truyền | Gọi `StepVerifier.verify...` trên đúng kết quả rồi đối chiếu wiring |
| Test PASS với `verifyComplete` nhưng fallback không dùng | Cả hai nhánh đều hoàn tất rỗng | Thêm `PublisherProbe` |
| `assertWasRequested` FAIL | Subscriber không cấp demand hoặc bị hủy sớm | Kiểm tra `initialRequest`/`thenRequest`, operator và cancellation |
| `assertWasNotCancelled` FAIL | Có `take`, timeout, `thenCancel` hoặc downstream hủy | Test cancellation theo contract, không mặc định completion |
| Fallback chạy ngay cả khi không cần | Factory có side effect eager tại assembly | Bọc factory trong `Mono.defer` |
| Fallback không chạy với `Mono.error` | `switchIfEmpty` không xử lý error | Sử dụng `onErrorResume` khi hợp đồng yêu cầu recovery |
| Gateway method đã được gọi nhưng side effect chưa xảy ra | Publisher trả về chưa được subscribe | Dùng probe bọc publisher trả về và xác nhận subscription |
| Test treo vì `Mono.never()` | Test đợi completion mà luồng không hoàn tất | Dùng `thenCancel` hoặc timeout test có chủ đích |
| Test thứ hai có probe “đã subscribed” dù chưa đi qua | Dùng lại probe giữa hai lần subscribe/test | Tạo probe mới cho từng test hoặc quản lý state có chủ đích |
| `PublisherProbe.empty()` không phát value mong đợi | Factory empty chỉ complete | Dùng `PublisherProbe.of(Mono.just(value))` |
| Test chỉ chạy trong IDE, fail khi chạy suite | Dùng state dùng chung, phụ thuộc test order, mock không reset | Cô lập mọi probe, stubbing và dữ liệu theo test |

### Hướng debug theo ba lớp

1. **Dữ liệu upstream:** nguồn có thực sự phát `onNext`, hoàn tất rỗng hay báo `onError`?
2. **Vị trí operator:** có `then`/`ignoreElement`/`flatMap(... Mono<Void>)` trước `switchIfEmpty` làm mất phần tử không?
3. **Quan sát đường đi:** StepVerifier đã subscribe đúng publisher chưa? Probe được gắn đúng fallback chưa? Assert subscription/request/cancel có khớp hợp đồng không?

Bước cuối cùng, nếu cần, dùng `StepVerifier` kết hợp `doOnSubscribe`/`doOnEach`/`log()` có chọn lọc để gỡ lỗi; tránh để log thay thế assertion ổn định.

## 16. Checklist thực hành

Một test fallback bằng `PublisherProbe` đáng tin cậy nên có:

- [ ] Xác định đúng **lý do fallback**: empty, error hay timeout; chọn operator tương ứng.
- [ ] Tìm đúng **vị trí đặt `switchIfEmpty`** trước khi mất tín hiệu dữ liệu có ý nghĩa.
- [ ] Chọn `PublisherProbe.empty()` nếu cần quan sát nhánh chỉ complete; `PublisherProbe.of(...)` nếu fallback phát dữ liệu.
- [ ] Đặt `probe.mono()`/`probe.flux()` trong nhánh fallback thực tế, không ở một Publisher bị bỏ qua.
- [ ] Dùng `StepVerifier` để subscribe và kiểm tra output/completion/error.
- [ ] Sau khi verify, dùng `assertWasSubscribed()` hoặc `assertWasNotSubscribed()` đúng kịch bản.
- [ ] Kiểm tra `assertWasRequested()`/cancellation khi chúng là phần của hợp đồng.
- [ ] Có cả ca **primary rỗng → fallback được dùng** và **primary có dữ liệu → fallback không được dùng**.
- [ ] Có ca error nếu hệ thống phải phân biệt empty với error.
- [ ] Nếu code trả `Mono<Void>`, kiểm tra operator có làm mất `onNext` trước `switchIfEmpty` không.
- [ ] Không chỉ `verify(mock).method()` khi cần chứng minh Publisher trả về thực sự được subscribe.
- [ ] Không dùng chung probe giữa các test độc lập hoặc phụ thuộc thứ tự test.
- [ ] Dùng `Mono.defer` nếu cần lazy factory và tránh side effect tại assembly.
- [ ] Không tạo Spring context khi chỉ cần test control-flow Java/Reactor thuần.

### Chạy các test

Từ thư mục có Gradle Wrapper (Linux/macOS):

~~~bash
./gradlew test --tests "com.example.reactivetest.CommandFlowTest"
./gradlew test --tests "com.example.reactivetest.PublisherProbeBranchTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.reactivetest.CommandFlowTest"
.\gradlew.bat test --tests "com.example.reactivetest.PublisherProbeBranchTest"
~~~

Các test trên không chứa `System.out.println`, vì vậy **không có stdout cố định do code tự in**. Gradle/JUnit có thể hiển thị số test PASS/FAIL và thông báo task theo cấu hình; khi mọi dependency hợp lệ, những assertion nêu trong bài là kỳ vọng cho bộ test. Đây là mã phụ thuộc Reactor, reactor-test, JUnit Jupiter và Mockito nên không thể chạy chỉ bằng `javac Test.java` không cung cấp classpath các thư viện đó.

**Ghi nhớ:** `PublisherProbe` giúp chứng minh một nhánh fallback có **thực sự được subscribe** khi luồng chạy, ngay cả khi cả hai nhánh đều trả `Mono<Void>` và kết quả đều chỉ là `onComplete`. Dùng nó **cùng StepVerifier**; kiểm tra cả nhánh được chọn lẫn nhánh không được chọn, và luôn đặt `switchIfEmpty` ở vị trí vẫn phản ánh “upstream rỗng” theo đúng nghiệp vụ.

### Tài liệu tham khảo

- [Project Reactor — Testing, Checking the Execution Path with PublisherProbe](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Reactor Test — PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html)
- [Reactor Core — Reactive Programming and switchIfEmpty](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)