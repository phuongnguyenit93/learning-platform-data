# Kiểm thử Reactor Context và ranh giới chuyển scheduler

## 1. Mục tiêu

Trong Spring WebFlux, một request có thể đi qua WebFilter, controller và service rồi chuyển sang một hoặc nhiều worker thread bằng `subscribeOn` hay `publishOn`. Nếu muốn mang theo `traceId`, correlation ID hoặc metadata gắn với **một subscription**, ta nên hiểu **Reactor Context**, không giả định biến `ThreadLocal` đi theo mọi thread.

Bài học này trả lời hai câu hỏi độc lập:

- **Dữ liệu Context:** operator nào thấy key/value nào, khi nào Context được tạo, và những subscription khác nhau có rò dữ liệu sang nhau không?
- **Ranh giới scheduler:** mã tạo source và các operator trước/sau `subscribeOn`, `publishOn` chạy trên thread nào; Context có còn đúng sau scheduler hop không?

Chúng ta sẽ dùng Java 17+, Spring Boot 3.3.5, Reactor Core, JUnit Jupiter, `StepVerifier` và `WebTestClient`. Các phiên bản được chọn để có ví dụ cụ thể, **không phải tuyên bố phiên bản mới nhất**. Một bộ test hoàn chỉnh kiểm tra Context thuần Reactor, tên thread trong scheduler riêng và HTTP header đi vào Context qua Spring WebFlux.

Khi đọc bài, cần phân biệt ba khái niệm: **thread thực thi**, **subscriber context** và **phần tử dữ liệu onNext**. Chúng tương tác nhưng không thay thế nhau.

## 2. Context là gì, khác ThreadLocal thế nào?

`reactor.util.context.Context` chứa các cặp key/value được gắn với subscription. Reactor cung cấp `ContextView` chỉ đọc cho nhiều callback. `Context` có API bất biến: `put` trả về giá trị mới thay vì sửa một map chung.

Ví dụ:

```java
Context original = Context.of("requestId", "R1");
Context changed = original.put("requestId", "R2");
// original.get("requestId") -> "R1"
// changed.get("requestId")  -> "R2"
```

Đây là snippet cần import `reactor.util.context.Context`. Lưu ý tính bất biến của **container Context** không khiến object mutable lưu bên trong nó tự trở nên bất biến hay thread-safe.

| Tiêu chí | Reactor Context | ThreadLocal |
| --- | --- | --- |
| Phạm vi chính | Subscriber / reactive subscription | Java Thread |
| Cách đọc | `Mono.deferContextual`, `ContextView` | `ThreadLocal.get()` |
| Cách ghi | `contextWrite`, trả Context mới | `ThreadLocal.set()` |
| Khi `publishOn` chuyển thread | Reactor operator vẫn có thể đọc Context tương ứng | Không tự bảo đảm giá trị đi theo |
| Rò dữ liệu thường gặp | Dùng cached emitted value hoặc quản lý inner publisher sai | Pool thread tái sử dụng khi quên remove |
| Vai trò | Metadata theo subscription | Metadata theo thread |

**Context không xuất hiện như một giá trị emitted** nếu không có operator chủ động đọc nó. Ví dụ `Mono.just("hello")` luôn phát `hello`, bất kể Context chứa gì; chỉ `deferContextual` hoặc operator tương ứng mới biến metadata thành output.

Một Context key không nên được dùng như kho lưu mật khẩu, token thô hoặc trạng thái nghiệp vụ mutable có vòng đời dài. Với tenant/authorization, nguồn dữ liệu phải đến từ một cơ chế xác thực đáng tin cậy; client tự đặt header không đủ để cấp quyền.

## 3. Hai chiều của reactive chain: subscription và signal

Chuỗi operator có hai hướng quan trọng:

```text
Assembly (đọc source code):
Mono.deferContextual(...)
    .map(...)
    .publishOn(worker)
    .map(...)
    .contextWrite(Context.of("requestId", "R1"))

Subscription xây từ downstream lên upstream:
subscriber cuối
  ↑ contextWrite bổ sung requestId
  ↑ map / publishOn / map
  ↑ deferContextual truy cập requestId

Dòng onNext/onError/onComplete đi từ source xuống:
deferContextual → map → publishOn → map → subscriber
```

`contextWrite` thay Context được downstream subscriber truyền lên **các operator phía upstream**. Đây là nguyên nhân đặt nó ở cuối chuỗi thường giúp các operator phía trên truy cập được dữ liệu.

Ví dụ đơn giản:

```java
Mono<String> p = Mono.deferContextual(
        ctx -> Mono.just("id=" + ctx.get("requestId")))
        .contextWrite(Context.of("requestId", "A"));
```

Khi subscribe, kết quả là `id=A`.

### Vị trí đặt contextWrite làm thay đổi ý nghĩa

```java
Mono<String> p = Mono.just("data")
        .contextWrite(Context.of("requestId", "A"))
        .flatMap(value -> Mono.deferContextual(
                ctx -> Mono.just(
                        ctx.getOrDefault("requestId", "missing"))));
```

Giá trị từ `flatMap` downstream là `missing` nếu subscriber cuối không cấp key này. `contextWrite` không phải lệnh “sửa biến chung để những dòng dưới nhìn thấy”.

### Hai đoạn cùng chuỗi có thể đọc hai giá trị

```java
Mono<String> p = Mono.deferContextual(
                ctx -> Mono.just(ctx.<String>get("scope")))
        .contextWrite(ctx -> ctx.put("scope", "inner"))
        .flatMap(first -> Mono.deferContextual(
                ctx -> Mono.just(
                        first + "|" + ctx.<String>get("scope"))))
        .contextWrite(ctx -> ctx.put("scope", "outer"));
```

Kết quả là `inner|outer`. `contextWrite("inner")` chỉ ảnh hưởng các operator upstream của nó; `flatMap` sau vị trí đó đọc Context còn chứa `outer`.

**Đây không phải race condition.** Hai subscriber trung gian có thể quan sát Context khác nhau một cách có chủ đích vì hướng truyền Context.

## 4. Các API quan trọng và cách kiểm chứng

| API | Công dụng | Ràng buộc khi test |
| --- | --- | --- |
| `Context.of(k, v)` | Tạo Context | Giá trị đúng type |
| `Context.put(k, v)` | Trả về Context đã thêm/thay key | Original không bị thay đổi |
| `ContextView.get(k)` | Đọc key bắt buộc | Thiếu key phát exception |
| `ContextView.getOrDefault(k, fallback)` | Đọc key tùy chọn | Trả fallback khi không có |
| `Mono.deferContextual(fn)` | Đọc Context **lúc subscribe** | Khác với đọc state ngay khi assembly |
| `Flux.deferContextual(fn)` | Tương tự cho nhiều phần tử | Cẩn thận thứ tự khi flatMap |
| `contextWrite(ContextView)` | Gộp Context downstream lên upstream | Vị trí operator quan trọng |
| `contextWrite(Function<Context,Context>)` | Chỉnh Context theo giá trị downstream | Trả Context mới |
| `transformDeferredContextual(fn)` | Tạo transform có truy cập Context | Kích hoạt tại subscription |
| `StepVerifierOptions.withInitialContext` | Cấp Context ban đầu cho verifier | Test publisher mà không cần thêm contextWrite |
| `StepVerifier.expectAccessibleContext` | Assert Context hiện diện trong chuỗi | Gọi `then()` để quay về assertions onNext |
| `StepVerifier.expectNoAccessibleContext` | Assert không có Context truy cập được | Chỉ dùng khi đó là hợp đồng |

Trong trường hợp Context key bắt buộc:

```java
Mono<String> reader = Mono.deferContextual(
        ctx -> Mono.just(ctx.<String>get("requestId")));
```

Nếu subscriber không có key, `ctx.get` ném `NoSuchElementException` và Reactor chuyển nó thành **error signal** khi subscribe. Test bằng `StepVerifier.expectError` thay vì `assertThrows` bọc thao tác tạo Mono, vì source chưa chạy tại thời điểm assembly.

## 5. Chọn loại test đúng phạm vi

Đối với bài này, **không cần nạp Spring Boot context** để chứng minh `Context` hoặc scheduler hoạt động như dự kiến. Unit test Reactor thuần dùng `StepVerifier` và scheduler do test tạo là lựa chọn tốt. Nhưng để biết WebFilter đã thực sự được Spring đăng ký và HTTP header đi vào Context, cần một bài test WebFlux tích hợp.

| Mục tiêu | Cách test |
| --- | --- |
| `contextWrite` có tới operator upstream không | `StepVerifier.expectNext` |
| Context của subscription A/B độc lập | Tạo hai `StepVerifier` trên cùng cold source |
| Thiếu key có thành error signal không | `StepVerifier.expectError` |
| Context có thể được subscriber cấp sẵn không | `StepVerifierOptions.withInitialContext` |
| `subscribeOn` điều phối source thread nào | `Mono.fromSupplier` + named `Scheduler` |
| `publishOn` chuyển operator downstream không | Capture thread name trước/sau boundary |
| Reactor Context còn đúng sau scheduler hop không | `deferContextual` trước/sau hop, assert value |
| WebFlux filter có đưa request header vào Context không | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` |
| MDC/ThreadLocal có bridge qua thread khác không | Test riêng theo Micrometer context-propagation cấu hình thật |

Không dùng `Thread.sleep` thay cho kiểm tra đã nhận signal terminal; StepVerifier có thể chờ completion/error với timeout. Không dùng `withVirtualTime` để chứng minh worker thread: virtual time chủ yếu giải quyết timers, không đại diện thread-hop thật.

## 6. Ví dụ dự án Java 17+ chạy được

Cấu trúc:

```text
reactor-context-boundary/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/context/
│   ├── ContextBoundaryApplication.java
│   ├── RequestIdFilter.java
│   └── TraceController.java
└── src/test/java/com/example/context/
    ├── ContextRulesTest.java
    ├── SchedulerBoundaryTest.java
    └── TraceHttpTest.java
```

### 6.1. settings.gradle

```groovy
rootProject.name = 'reactor-context-boundary'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-webflux` chọn reactive web stack. Không thêm `spring-boot-starter-web` vào project mẫu, vì khi cả MVC và WebFlux cùng xuất hiện trên classpath, Boot thường ưu tiên Servlet MVC nếu không chọn web-application-type một cách tường minh. `reactor-test` chứa `StepVerifier`; Reactor Core được quản lý qua BOM của Spring Boot.

Các lệnh `./gradlew` chỉ dùng được nếu dự án có **Gradle Wrapper**. Nếu chưa có wrapper, dùng `gradle` với bản Gradle tương thích. Java 17+ là mức tối thiểu của ứng dụng mẫu.

### 6.3. Spring Boot application

Tạo `src/main/java/com/example/context/ContextBoundaryApplication.java`:

```java
package com.example.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextBoundaryApplication.class, args);
    }
}
```

## 7. Spring WebFlux filter lưu request ID trong Reactor Context

`src/main/java/com/example/context/RequestIdFilter.java`:

```java
package com.example.context;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestIdFilter implements WebFilter {

    public static final String TRACE_ID = "traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String incoming = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Request-Id");

        String resolved = (incoming == null || incoming.isBlank())
                ? "none"
                : incoming;

        return chain.filter(exchange)
                .contextWrite(ctx -> ctx.put(TRACE_ID, resolved));
    }
}
```

Filter không tạo biến static hay ThreadLocal để ghi `traceId`. Nó lấy header cho request hiện tại, rồi dùng `contextWrite` để cung cấp Context cho subscription của phần handler chain.

### Vì sao viết chain.filter(exchange).contextWrite(...)?

`WebFilterChain.filter(...)` trả một `Mono<Void>` biểu diễn phần còn lại của WebFlux processing. Khi subscribe vào Mono đó, `contextWrite` đặt key cho phía upstream trong chain: các operator/context-aware component ở handler có thể đọc nó.

Nếu đặt `contextWrite` trên một Mono **không liên quan** rồi lại trả `chain.filter(exchange)` khác, Context tạo ra ở Mono không được subscribe sẽ không có tác dụng. Đây là lỗi wiring phổ biến: Context gắn với **subscription**, không phải thao tác mutable toàn cục.

Nếu app dùng authentication, đừng lấy tenant/role trực tiếp từ header do client điều khiển rồi đưa vào Context làm căn cứ phân quyền. Header `X-Request-Id` trong ví dụ chỉ mang **correlation metadata**, và giá trị `none` là fallback học tập.

## 8. Controller đọc Context sau scheduler hop

`src/main/java/com/example/context/TraceController.java`:

```java
package com.example.context;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class TraceController {

    @GetMapping(
            value = "/trace",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> trace() {
        return Mono.just("ready")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> Mono.deferContextual(ctx ->
                        Mono.just("trace=" + ctx.getOrDefault(
                                RequestIdFilter.TRACE_ID, "none"))));
    }
}
```

Ở đây `publishOn(Schedulers.parallel())` là một hop có chủ đích để học. `deferContextual` nằm trong `flatMap` downstream của hop, nên endpoint đọc Context **sau khi signal đã chuyển sang scheduler**. Test HTTP ở mục 11 kiểm tra response đúng; test scheduler ở mục 10 kiểm tra tên thread rõ ràng.

Không thêm `publishOn` vào mọi endpoint production: chuyển thread có chi phí và có thể làm mất locality. Nếu đang dùng driver reactive thật, nhiều thao tác không cần scheduling thủ công. Dùng `Schedulers.parallel` cho CPU non-blocking khi phù hợp, và `Schedulers.boundedElastic` cho một số blocking calls đã được cô lập.

## 9. Bộ test ContextRulesTest: 7 tình huống độc lập

Tạo `src/test/java/com/example/context/ContextRulesTest.java`:

```java
package com.example.context;

import java.time.Duration;
import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContextRulesTest {

    private static final String TRACE_ID = "traceId";

    @Test
    void contextWriteMakesValueVisibleToUpstream() {
        Mono<String> source = Mono.deferContextual(
                ctx -> Mono.just("trace=" +
                        ctx.<String>get(TRACE_ID)))
                .contextWrite(Context.of(TRACE_ID, "r-100"));

        StepVerifier.create(source)
                .expectNext("trace=r-100")
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void separateSubscriptionsUseSeparateContext() {
        Mono<String> reader = Mono.deferContextual(
                ctx -> Mono.just(
                        ctx.getOrDefault(TRACE_ID, "missing")));

        StepVerifier.create(reader.contextWrite(
                        Context.of(TRACE_ID, "request-A")))
                .expectNext("request-A")
                .verifyComplete();

        StepVerifier.create(reader.contextWrite(
                        Context.of(TRACE_ID, "request-B")))
                .expectNext("request-B")
                .verifyComplete();

        StepVerifier.create(reader)
                .expectNext("missing")
                .verifyComplete();
    }

    @Test
    void contextWriteDoesNotPropagateDownstream() {
        Mono<String> source = Mono.just("data")
                .contextWrite(Context.of(TRACE_ID, "upstream-only"))
                .flatMap(value -> Mono.deferContextual(ctx ->
                        Mono.just(
                                ctx.getOrDefault(TRACE_ID, "missing"))));

        StepVerifier.create(source)
                .expectNext("missing")
                .verifyComplete();
    }

    @Test
    void nestedAndOuterContextMayDiffer() {
        Mono<String> source = Mono.deferContextual(
                        ctx -> Mono.just(ctx.<String>get("scope")))
                .contextWrite(ctx -> ctx.put("scope", "inner"))
                .flatMap(first -> Mono.deferContextual(
                        ctx -> Mono.just(
                                first + "|" + ctx.<String>get("scope"))))
                .contextWrite(ctx -> ctx.put("scope", "outer"));

        StepVerifier.create(source)
                .expectNext("inner|outer")
                .verifyComplete();
    }

    @Test
    void verifierSuppliesInitialContext() {
        Mono<String> source = Mono.deferContextual(
                ctx -> Mono.just("tenant=" +
                        ctx.<String>get("tenantId")));

        StepVerifier.create(
                        source,
                        StepVerifierOptions.create().withInitialContext(
                                Context.of("tenantId", "tenant-A")))
                .expectAccessibleContext()
                .contains("tenantId", "tenant-A")
                .then()
                .expectNext("tenant=tenant-A")
                .verifyComplete();
    }

    @Test
    void missingRequiredKeyProducesErrorSignal() {
        Mono<String> source = Mono.deferContextual(
                ctx -> Mono.just(ctx.<String>get(TRACE_ID)));

        StepVerifier.create(source)
                .expectError(NoSuchElementException.class)
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void putReturnsNewContextInsteadOfMutatingSource() {
        Context original = Context.of(TRACE_ID, "before");
        Context changed = original.put(TRACE_ID, "after");

        assertEquals("before", original.get(TRACE_ID));
        assertEquals("after", changed.get(TRACE_ID));
    }
}
```

### Giải thích từng phép thử

**contextWriteMakesValueVisibleToUpstream** kiểm tra Context được ghi ở downstream của `deferContextual` và phát giá trị đúng. Không có real HTTP thread nào cần tham gia.

**separateSubscriptionsUseSeparateContext** tái sử dụng cùng cold `Mono` nhưng tạo ba subscription. Subscriber A nhận `request-A`, subscriber B nhận `request-B`, subscriber không có key nhận `missing`. Nếu ai đó dùng static field để ghi ID theo request, test tương tự có thể phơi bày rò rỉ state.

**contextWriteDoesNotPropagateDownstream** bảo vệ quy tắc hướng truyền Context. Một `contextWrite` không tự ảnh hưởng `flatMap` nằm downstream trong cùng chain.

**nestedAndOuterContextMayDiffer** xác minh hai đoạn trong chain có Context khác nhau một cách hợp lệ, không nhầm là một mutable map dùng chung.

**verifierSuppliesInitialContext** dùng `StepVerifierOptions.withInitialContext` để mô phỏng Context đến từ subscriber. `expectAccessibleContext().contains(...).then()` kiểm tra Context có thể truy cập, rồi tiếp tục kiểm tra phần tử emitted. Cả hai assertions đều có giá trị: Context hiện diện chưa chắc business code đã dùng đúng key.

**missingRequiredKeyProducesErrorSignal** chứng minh thiếu `traceId` bắt buộc dẫn tới `onError` tại subscription. Vì `Mono.deferContextual` lazy, không dùng `assertThrows` quanh lệnh **tạo** Mono.

**putReturnsNewContextInsteadOfMutatingSource** kiểm tra nguyên tắc immutable Context. Đây là JUnit test đơn giản, không cần subscriber.

**Kết quả kỳ vọng:** 7 test method. Các method chưa được thực thi trong phiên này; cần chạy Gradle thực tế để xác nhận.

## 10. Bộ test SchedulerBoundaryTest: ranh giới thread và Context

Tạo `src/test/java/com/example/context/SchedulerBoundaryTest.java`:

```java
package com.example.context;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchedulerBoundaryTest {

    @Test
    void subscribeOnMovesSourceEvaluation() {
        Scheduler worker = Schedulers.newSingle("source-boundary");
        AtomicReference<String> sourceThread = new AtomicReference<>();
        AtomicReference<String> mapThread = new AtomicReference<>();

        try {
            Mono<Integer> p = Mono.fromSupplier(() -> {
                        sourceThread.set(
                                Thread.currentThread().getName());
                        return 5;
                    })
                    .map(value -> {
                        mapThread.set(
                                Thread.currentThread().getName());
                        return value * 2;
                    })
                    .subscribeOn(worker);

            StepVerifier.create(p)
                    .expectNext(10)
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertNotNull(sourceThread.get());
            assertTrue(sourceThread.get()
                    .startsWith("source-boundary-"));
            assertEquals(sourceThread.get(), mapThread.get());
        } finally {
            worker.dispose();
        }
    }

    @Test
    void publishOnMovesDownstreamButNotPreviousSource() {
        Scheduler worker = Schedulers.newSingle("downstream-boundary");
        AtomicReference<String> before = new AtomicReference<>();
        AtomicReference<String> after = new AtomicReference<>();
        String testThread = Thread.currentThread().getName();

        try {
            Mono<Integer> p = Mono.just(7)
                    .doOnNext(value -> before.set(
                            Thread.currentThread().getName()))
                    .publishOn(worker)
                    .map(value -> {
                        after.set(Thread.currentThread().getName());
                        return value + 1;
                    });

            StepVerifier.create(p)
                    .expectNext(8)
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertEquals(testThread, before.get());
            assertNotNull(after.get());
            assertTrue(after.get().startsWith(
                    "downstream-boundary-"));
        } finally {
            worker.dispose();
        }
    }

    @Test
    void contextSurvivesSubscribeOnAndPublishOn() {
        Scheduler source = Schedulers.newSingle("ctx-source");
        Scheduler downstream = Schedulers.newSingle("ctx-after");
        AtomicReference<String> onSource = new AtomicReference<>();
        AtomicReference<String> onDownstream = new AtomicReference<>();

        try {
            Mono<String> p = Mono.deferContextual(ctx -> {
                        onSource.set(Thread.currentThread().getName());
                        return Mono.just(ctx.<String>get("traceId"));
                    })
                    .subscribeOn(source)
                    .publishOn(downstream)
                    .flatMap(id -> Mono.deferContextual(ctx -> {
                        onDownstream.set(
                                Thread.currentThread().getName());
                        return Mono.just(id + "|" +
                                ctx.<String>get("traceId"));
                    }))
                    .contextWrite(Context.of("traceId", "req-900"));

            StepVerifier.create(p)
                    .expectNext("req-900|req-900")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertNotNull(onSource.get());
            assertNotNull(onDownstream.get());
            assertTrue(onSource.get().startsWith("ctx-source-"));
            assertTrue(onDownstream.get().startsWith("ctx-after-"));
        } finally {
            source.dispose();
            downstream.dispose();
        }
    }

    @Test
    void eachPublishOnCreatesAnotherBoundary() {
        Scheduler first = Schedulers.newSingle("stage-one");
        Scheduler second = Schedulers.newSingle("stage-two");
        AtomicReference<String> stageOne = new AtomicReference<>();
        AtomicReference<String> stageTwo = new AtomicReference<>();

        try {
            Mono<String> p = Mono.just("ok")
                    .publishOn(first)
                    .map(text -> {
                        stageOne.set(Thread.currentThread().getName());
                        return text;
                    })
                    .publishOn(second)
                    .map(text -> {
                        stageTwo.set(Thread.currentThread().getName());
                        return text.toUpperCase();
                    });

            StepVerifier.create(p)
                    .expectNext("OK")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));

            assertNotNull(stageOne.get());
            assertNotNull(stageTwo.get());
            assertTrue(stageOne.get().startsWith("stage-one-"));
            assertTrue(stageTwo.get().startsWith("stage-two-"));
        } finally {
            first.dispose();
            second.dispose();
        }
    }
}
```

**Kết quả kỳ vọng:** 4 test methods.

### subscribeOn là boundary của source/subscription

Trong test đầu, `Mono.fromSupplier` chạy khi subscribe. `subscribeOn(worker)` dời subscription/source sang scheduler có thread tên bắt đầu bằng `source-boundary-`. `map` nằm ngay sau source cũng chạy trên worker đó khi chưa có operator đổi scheduler khác.

Không nói rằng `subscribeOn` chỉ ảnh hưởng đúng một dòng source: nó điều khiển subscription và có thể kéo theo callback downstream chạy trên cùng thread nếu chưa có `publishOn`.

### publishOn là boundary của signal downstream

Test thứ hai dùng `Mono.just(7)` phát đồng bộ trên thread JUnit trong tình huống cụ thể này. `doOnNext` phía trước `publishOn` capture thread JUnit, còn `map` sau `publishOn(worker)` capture worker mới. Kiểm tra cả trước lẫn sau mới chứng minh boundary đúng vị trí.

Không đặt `publishOn` ở cuối rồi mong `map` phía trên tự chạy ở thread mới: nó tác động tới downstream **sau** boundary.

### Context không bị ràng buộc với thread name

Test thứ ba vừa kiểm tra Context `req-900` được đọc ở hai đoạn, vừa xác nhận hai đoạn chạy trên thread có prefix khác nhau. Khi Context vẫn đúng qua cả `subscribeOn` và `publishOn`, ta có bằng chứng về **Reactor Context propagation trên chain đó**. Không được suy rộng thành mọi `ThreadLocal` sẽ có cùng dữ liệu.

### Cách assert thread bền vững

`Schedulers.newSingle("prefix")` cung cấp tên scheduler riêng cho test. Chỉ assert tên thread `startsWith("prefix-")` thay vì so sánh exact `"parallel-1"` hoặc số thread toàn JVM. Thread name của global pool có thể thay đổi theo môi trường, phiên bản hoặc suite song song.

`AtomicReference` được dùng để capture thông tin giữa các callback chạy trên thread khác nhau; sau khi StepVerifier thấy terminal signal, test mới đọc các reference. Scheduler tạo riêng cần `dispose()` trong `finally` để tránh rò worker threads.

### Vì sao không dùng Thread.sleep?

Một test kiểu:

```java
publisher.subscribe(value -> observed.set(value));
Thread.sleep(100);
assertEquals("ok", observed.get());
```

là **snippet phản ví dụ** với các biến chưa định nghĩa. Đợi một khoảng thời gian cố định không bảo đảm publisher đã hoàn thành; CI chậm dễ gây flaky. Dùng `StepVerifier` để đăng ký subscription, kiểm tra onNext/onError/onComplete và `verify(Duration.ofSeconds(5))` để có timeout rõ ràng.

## 11. Integration test: HTTP header đi qua WebFilter vào Reactor Context

Tạo `src/test/java/com/example/context/TraceHttpTest.java`:

```java
package com.example.context;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TraceHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void requestHeaderIsVisibleAfterSchedulerHop() {
        client.get()
                .uri("/trace")
                .header("X-Request-Id", "trace-123")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=trace-123");
    }

    @Test
    void twoRequestsHaveIndependentContext() {
        client.get()
                .uri("/trace")
                .header("X-Request-Id", "request-A")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=request-A");

        client.get()
                .uri("/trace")
                .header("X-Request-Id", "request-B")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=request-B");

        client.get()
                .uri("/trace")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("trace=none");
    }
}
```

**Kết quả kỳ vọng:** 2 test methods.

Lớp này mở embedded WebFlux HTTP server trên port do OS chọn, không hardcode port. `WebTestClient` gửi request thật, filter được Spring component scan đăng ký, controller đọc Context **sau `publishOn`**. Đây là test ranh giới từ **HTTP header → WebFilter → Reactor Context → controller**.

`WebTestClient` cũng có thể chạy ở mock binding mode khi dùng `@WebFluxTest`. Trong ví dụ chọn `RANDOM_PORT` vì muốn chứng minh đường request qua server thật. Unit test thuần Reactor ở mục 9–10 nhanh hơn và nên dùng cho phần lớn quy tắc Context/scheduler; HTTP test dành cho wiring thực.

### Chống rò dữ liệu giữa request

Test thứ hai gửi A, B và request không có header; một bean singleton sai thiết kế lưu requestId trong field có thể làm test phát hiện state rò giữa request. Nhưng test tuần tự không chứng minh được mọi race điều kiện tải cao. Khi sản phẩm cần độ tin cậy dưới concurrency, bổ sung integration test gửi đồng thời nhiều request có ID khác nhau, assert ID đúng cho từng response.

Context có phạm vi subscription, nhưng nếu code đưa ID vào **một giá trị emitted bị cache toàn cục**, dữ liệu vẫn có thể rò qua cache. Vì thế test context isolation cần bổ sung các case hot/shared publisher nếu ứng dụng thực dùng `cache()`, `share()` hoặc replay.

## 12. Chạy test và đọc báo cáo đúng cách

| Lớp | Số method | Vai trò |
| --- | ---: | --- |
| `ContextRulesTest` | 7 | Hướng propagation, immutable Context, initial Context, isolation và error |
| `SchedulerBoundaryTest` | 4 | `subscribeOn`/`publishOn`, tên thread và giữ Context qua hop |
| `TraceHttpTest` | 2 | WebFlux HTTP filter và Context từ request header |

Tổng cộng **13 phương thức `@Test`** trong mã mẫu.

Dùng lệnh:

```bash
./gradlew test --tests "com.example.context.ContextRulesTest"
./gradlew test --tests "com.example.context.SchedulerBoundaryTest"
./gradlew test --tests "com.example.context.TraceHttpTest"
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có Wrapper và Gradle tương thích đã được cài, dùng `gradle test`. Kết quả kỳ vọng là PASS nhưng **chỉ báo cáo chạy thực tế mới xác nhận**. Test không in stdout nghiệp vụ cố định. Xem Gradle HTML report tại `build/reports/tests/test/index.html` hoặc XML ở `build/test-results/test`.

Nếu một test scheduler fail, cần biết đó là lỗi giá trị emitted, thread prefix, timeout hay lifecycle; đừng sửa expected thread theo môi trường ngẫu nhiên. Nếu HTTP test fail, kiểm tra web application type (WebFlux hay MVC), filter bean, header, port và exception trong server log.

## 13. Context và MDC/ThreadLocal: đừng gộp làm một

Trong ứng dụng Spring MVC truyền thống, người ta thường dùng `MDC.put("traceId", value)` rồi log trên request thread. Với WebFlux, operator có thể chạy trên event-loop và sau đó hop sang worker thread.

`ThreadLocal` gắn với thread, không tự đọc từ Reactor Context. Nếu filter đặt MDC trước khi publisher thực thi, sau `publishOn` một worker có thể thấy `null` hoặc state không mong muốn. Các scheduler dùng lại thread giữa nhiều request nên quên cleanup ThreadLocal còn có thể làm lộ ID cũ.

Reactor Core hỗ trợ tích hợp với Micrometer `io.micrometer:context-propagation` (từ Reactor 3.5+). Với adapter `ThreadLocalAccessor` và chế độ propagation phù hợp, một số ThreadLocal có thể được restore từ Context ở những đoạn hỗ trợ; tự động mode có thể được bật bằng `Hooks.enableAutomaticContextPropagation()` tùy phiên bản và cấu hình.

**Không bật global hook trong một test tùy tiện rồi quên hủy/reset.** Hook có thể ảnh hưởng các subscriptions mới trong cả JVM/suite. Nếu ứng dụng dùng Boot Observability/Tracing, cần test riêng theo stack Micrometer/SLF4J/OpenTelemetry thật, vì test Reactor Context đơn thuần **không chứng minh MDC đã được bridge**.

Một test MDC có giá trị nên kiểm tra hai request với hai ID và một request không ID, qua scheduler hop, quan sát log context trên worker, rồi bảo đảm cleanup sau completion/error/cancellation. Không dựa vào việc request đầu chạy cùng thread với request sau.

## 14. flatMap, inner publishers và ranh giới Context

`flatMap` tạo inner subscription. Các Reactor-native operators hỗ trợ Context, nhưng một phép `contextWrite` **bên trong inner chain không sửa Context của outer chain**.

Ví dụ:

```java
Mono<String> p = Mono.just("order-1")
        .flatMap(id -> Mono.deferContextual(
                ctx -> Mono.just(id + ":" +
                        ctx.<String>get("scope")))
                .contextWrite(Context.of("scope", "inner")))
        .flatMap(first -> Mono.deferContextual(
                ctx -> Mono.just(first + ":" +
                        ctx.getOrDefault("scope", "missing"))));
```

Kết quả `order-1:inner:missing` khi subscriber ngoài không cấp key này. Giá trị `inner` được gắn cho inner publisher, không “bắn ra ngoài” để thay Context của `flatMap` tiếp theo.

Với `Flux.flatMap` chạy nhiều inner publishers đồng thời, thứ tự emitted values có thể không cố định. Nếu test không có ràng buộc thứ tự, assert tập kết quả/đếm phần tử thay vì `expectNext(a,b,c)`. Nếu contract cần giữ thứ tự, cân nhắc `concatMap` hoặc `flatMapSequential` và kiểm tra latency/order theo đúng semantics.

### Tạo subscription bằng subscribe() bên trong callback

Anti-pattern:

```java
Mono.just("start")
    .doOnNext(value -> anotherPublisher.subscribe())
    .contextWrite(Context.of("traceId", "r-1"));
```

`anotherPublisher` là biến minh họa đã có ở scope khác. Lời gọi `subscribe()` tạo subscription mới, không tự có Context như outer subscriber; errors/cancellation của inner bị tách khỏi pipeline chính.

Hướng đúng thường là **compose**:

```java
Mono.just("start")
    .flatMap(value -> anotherPublisher)
    .contextWrite(Context.of("traceId", "r-1"));
```

Với kiểu Mono tương ứng, `flatMap` nối lifecycle/error và Context theo reactive chain thay vì thả một subscription tự quản lý. Đừng dùng `subscribe()` trong service chỉ để “bắt publisher chạy”.

## 15. Ranh giới ngoài Reactor

`CompletableFuture.supplyAsync`, executor tùy biến, callback Java thuần hoặc một thư viện tự tạo thread không tự biết Reactor Context. Khi bridge từ `Mono` ra API ngoài rồi quay về, phải quyết định metadata được mang theo bằng:

- Tham số explicit (`requestId` truyền vào adapter) khi dễ và an toàn.
- Một context snapshot/adapter có đăng ký theo SPI phù hợp.
- Thiết kế API mà outer Reactor operator đọc Context và truyền dữ liệu vào lời gọi ngoài.

Đừng giả định `Mono.fromFuture` khiến code bên trong `CompletableFuture` tự đọc được Reactor Context. Nó chỉ đưa tín hiệu hoàn thành của Future trở lại reactive stream; callback Future đã chạy theo semantics của executor riêng.

### Cached và hot publishers

`Mono.deferContextual` giúp mỗi subscription đọc Context ở thời điểm subscribe. Nhưng nếu tạo:

```java
Mono<String> shared =
        Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("traceId")))
            .cache();
```

publisher `shared` có thể cache giá trị emitted từ subscription đầu. Subscriber thứ hai có Context khác vẫn có thể nhận giá trị cached của subscriber đầu. Đây là rò dữ liệu qua **cache output**, không có nghĩa immutable Reactor Context biến thành map chung. Không cache publisher phụ thuộc dữ liệu per-request dưới dạng singleton toàn cục.

## 16. Virtual time, timeout và thread boundaries

`StepVerifier.withVirtualTime` thích hợp cho `delayElements`, `timeout`, `retryWhen` có backoff. Virtual time thay việc chờ thực bằng kiểm soát clock của scheduler trong một số operator khi publisher được tạo đúng thời điểm.

Ví dụ minh họa:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(2)))
    .expectSubscription()
    .expectNoEvent(Duration.ofHours(2))
    .expectNext(0L)
    .verifyComplete();
```

Cần import `Mono`, `StepVerifier`, `Duration`. Test này không ngủ hai giờ thật. Tuy nhiên, virtual-time scheduler **không phải công cụ chứng minh callback chạy trên thread worker thực**, vì nó có mô hình scheduling đặc biệt. Muốn kiểm tra `subscribeOn`/`publishOn` đúng boundary, dùng `Schedulers.newSingle` riêng như mục 10.

`verifyComplete()` không tự đặt một timeout phù hợp cho mọi môi trường. Với test có chuyển scheduler, dùng `expectComplete().verify(Duration.ofSeconds(5))` hoặc budget CI phù hợp để phát hiện publisher treo thay vì chờ vô hạn.

## 17. Blocking I/O trong chuỗi Reactive

Không phải cứ trả `Mono` là mọi code bên trong tự non-blocking. Ví dụ một controller gọi JDBC đồng bộ trước khi trả `Mono.just(...)` đã chặn request thread. `Schedulers.parallel()` có ít worker, phù hợp CPU non-blocking, **không nên chứa thao tác blocking I/O lâu**.

Đối với dependency blocking tạm thời còn phải giữ, một pattern thường được dùng:

```java
Mono.fromCallable(() -> legacyRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là snippet minh họa với `legacyRepository` và `id` do ứng dụng định nghĩa, không thuộc project runnable. `boundedElastic` cách ly một số blocking calls khỏi event-loop với khả năng giới hạn tài nguyên; nó **không tự biến I/O thành non-blocking**.

Nếu adapter blocking cần request ID, hãy đọc Reactor Context bên trong publisher và truyền ID thành đối số explicit cho adapter, hoặc dùng context-propagation được cấu hình. Không kỳ vọng ThreadLocal ở request event-loop tự có trên boundedElastic thread.

## 18. Các lỗi thường gặp

| Lỗi hoặc biểu hiện | Nguyên nhân | Kiểm thử/khắc phục |
| --- | --- | --- |
| `NoSuchElementException` từ `ContextView.get` | Thiếu key | Đặt `contextWrite` downstream đúng chỗ, hoặc dùng fallback có chủ đích |
| Source thấy Context nhưng một downstream operator không thấy | `contextWrite` chỉ ảnh hưởng upstream | Kiểm tra vị trí và Context của operator |
| `flatMap` thứ hai không thấy key từ inner thứ nhất | Inner Context không lan ra outer Context | Đặt Context ở outer chain hoặc truyền dữ liệu explicit |
| `ThreadLocal`/MDC null sau hop | Không có propagation adapter | Reactor Context hoặc bridge Micrometer đúng phiên bản |
| Verify chạy trước completion | Subscribe async không được đợi | StepVerifier + timeout, không sleep |
| Test dựa vào tên `parallel-1` bị flaky | Shared thread pool bị dùng bởi suite khác | Scheduler test-owned với prefix riêng |
| Test treo | Publisher không terminal, retry không giới hạn | Timeout, kiểm tra signal lifecycle |
| Request A nhận ID của B | Static/singleton mutable state hoặc cached output | Test nhiều request Context khác nhau |
| `Context.put` tưởng sửa original | API immutable | Dùng Context mới được trả về |
| `subscribeOn` tưởng chỉ chạy source một dòng | Subscription scheduling ảnh hưởng nhiều operator | Capture thread tại source và map |
| `publishOn` tưởng ảnh hưởng operator phía trên | Nó điều phối downstream signal | Capture thread trước và sau boundary |
| Context đúng nhưng log trace sai | Reactor Context và MDC là hai hệ khác | Test adapter/logging riêng |
| StepVerifier dùng virtual time rồi kiểm tra tên thread | Virtual time cho timers | Named scheduler thật cho hop test |
| Callback CompletableFuture mất ID | Ngoài Reactor, thiếu bridge | Explicit args hoặc context snapshot |
| `cache()` dùng chung Mono per-request | Cached onNext value lộ request đầu | Không share cached value có metadata per-request |
| Test scheduler tạo nhiều thread không dọn | Không dispose Scheduler mới | `try/finally` với `dispose()` |
| Full HTTP test quá chậm | Dùng Spring context cho logic thuần Reactor | Tách unit test và integration test |
| Test chỉ assert HTTP status | Không biết Context có đúng không | Assert response body và nhiều request IDs |

## 19. Checklist thực hành

Trước khi merge test:

1. Đã định nghĩa chính xác Context key/value và phạm vi một subscription chưa?
2. Code đọc Context bằng `deferContextual` ở thời điểm subscribe, hay chốt dữ liệu tại assembly?
3. `contextWrite` có nằm downstream của operator cần đọc không?
4. Đã test key vắng mặt và fallback/error khi cần chưa?
5. Hai subscriptions trên cùng một cold publisher có nhận hai Context khác nhau không?
6. `StepVerifierOptions.withInitialContext` có được dùng khi mục tiêu là context do subscriber cấp không?
7. `expectAccessibleContext` có `then()` và assertions tiếp theo trên emitted values không?
8. `subscribeOn` test capture đúng source thread chưa?
9. `publishOn` test capture cả operator trước và sau hop chưa?
10. Nếu có hai `publishOn`, đã kiểm tra callback sau mỗi boundary chưa?
11. Context có giữ đúng qua từng hop không, độc lập với tên thread?
12. Test dùng named scheduler riêng, không assert số thứ tự của shared worker threads?
13. Test chờ terminal signal và có timeout hợp lý?
14. Scheduler mới tạo đã `dispose()` trong `finally`?
15. Có phân biệt Reactor Context với MDC/ThreadLocal và test bridge khi cần?
16. Không gọi `subscribe()` tự phát bên trong doOnNext/map?
17. Không dùng singleton cached publisher cho output phụ thuộc request?
18. Khi cần kiểm tra HTTP wiring, đã có `WebTestClient` chạy đúng WebFlux runtime?
19. Hai request khác ID và request thiếu ID có response khác nhau đúng kỳ vọng?
20. Có bảo đảm request header từ client không được tin làm thông tin phân quyền?
21. Code production có tránh blocking event-loop và dùng scheduler phù hợp?
22. Có chạy Gradle trong môi trường mục tiêu và kiểm tra PASS/FAIL thực tế, không chỉ đếm `@Test` từ source?

## 20. Bài tập củng cố

1. Đổi vị trí `contextWrite` trong `contextWriteMakesValueVisibleToUpstream` và dự đoán nơi `get` ném exception.
2. Thử thay `get("traceId")` thành `getOrDefault("traceId","missing")`, so sánh signal error với fallback.
3. Thêm subscription thứ tư có key `request-C` vào `separateSubscriptionsUseSeparateContext`.
4. Xóa `withInitialContext` trong `verifierSuppliesInitialContext` và giải thích thứ tự assertion sẽ fail.
5. Trong `subscribeOnMovesSourceEvaluation`, bỏ `subscribeOn` và kiểm tra source thread thực.
6. Trong `publishOnMovesDownstreamButNotPreviousSource`, dời `publishOn` xuống cuối chain; xác định callback nào còn ở thread JUnit.
7. Thêm `publishOn` thứ hai vào pipeline có Context rồi kiểm tra cả Context value và thread prefix.
8. Tạo một `Mono.deferContextual(...).cache()` dùng chung, subscribe bằng hai Context khác nhau; phân biệt output cache với Context của subscriber.
9. Thử tự gọi `subscribe()` trong một callback rồi so sánh cách làm bằng `flatMap`.
10. Chạy HTTP test với hai request ID khác nhau; nếu rò dữ liệu, kiểm tra static/field/cache trước khi nghi Context.
11. Khi đang dùng Micrometer context-propagation trong app thật, thêm test riêng cho MDC sau scheduler hop.
12. Viết test xử lý một `Mono.error(...)` dưới Context có trace ID; kiểm tra error signal và logging metadata không bị lộ ra response.
13. Thử một blocking adapter ở sandbox với `boundedElastic` và xác minh code không chạy trên event-loop; đừng dùng sleep trên production.
14. Dùng `StepVerifier.withVirtualTime` kiểm tra retry delay; giải thích tại sao test đó khác với thread-boundary test.

## 21. Tài liệu tham khảo

- [Project Reactor 3.6 — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.6.17/reference/#context): `Context`, `ContextView`, `contextWrite`, `deferContextual`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/3.6.17/reference/#schedulers): `subscribeOn`, `publishOn`, `Schedulers`.
- [Project Reactor — Testing a Context](https://projectreactor.io/docs/core/3.6.17/reference/#_testing_the_context): `StepVerifierOptions.withInitialContext`, `expectAccessibleContext`.
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/3.6.17/reference/#context-propagation-support): Micrometer SPI, ThreadLocal bridging.
- [Spring Framework — WebFlux WebFilter](https://docs.spring.io/spring-framework/reference/web/webflux-webhandler-api.html): WebHandler/WebFilter chain.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): test WebFlux có hoặc không có live HTTP server.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test WebFlux và RANDOM_PORT.

## 22. Tổng kết

**Reactor Context đi cùng subscription, không đi cùng một Java Thread.** `contextWrite` biến đổi Context cho upstream; `deferContextual` đọc Context tại thời điểm subscribe; `StepVerifierOptions.withInitialContext` cho phép test mô phỏng subscriber cấp Context. Nên kiểm tra cả hai mặt: giá trị Context nhìn thấy và isolation giữa những subscriptions khác nhau.

`subscribeOn` điều phối subscription/source, còn `publishOn` chuyển signal handling downstream tới Scheduler được chọn. Qua Reactor-native operator chain, Context có thể vẫn đúng sau scheduler hop, nhưng `ThreadLocal` và MDC cần giải pháp propagation riêng. Bộ kiểm thử dùng StepVerifier, test-owned scheduler và WebTestClient giúp xác nhận **metadata đúng, execution boundary đúng và Spring WebFlux filter wiring đúng** mà không dựa vào Thread.sleep hay tên thread ngẫu nhiên.
