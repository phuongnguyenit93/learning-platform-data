# Kiểm chứng lỗi, hủy, tài nguyên và ngữ cảnh theo từng yêu cầu trong Project Reactor

## 1. Mục tiêu

Một request reactive có thể đi qua nhiều operator, thread và dependency. Khi request lỗi, timeout hoặc client ngắt kết nối, ứng dụng cần trả đúng kết quả, giải phóng resource và giữ đúng metadata của chính request đó.

Bài thực hành kết hợp bốn chiều:

1. **Error:** lỗi được truyền tới đúng subscriber, được phân loại/chuyển đổi có chủ đích và không bị nuốt.
2. **Cancellation:** downstream không còn cần dữ liệu thì upstream nhận cancel và resource được dọn theo contract.
3. **Resource lifecycle:** mỗi subscription mở resource riêng, giải phóng đúng nhánh complete, error hoặc cancel.
4. **Per-request Context:** request ID và tenant metadata không bị trộn giữa các request chạy đồng thời hoặc khi pipeline đổi Scheduler.

Ta dùng Reactor Context, Mono/Flux.usingWhen, StepVerifier, PublisherProbe, TestPublisher, virtual time, doFinally và một resource ledger có thể quan sát. Mục tiêu là thực hành tenant isolation và request isolation bằng kiểm thử có thể lặp lại.

Các bất biến:

- Mỗi request chỉ đọc Context của subscription đó.
- Mỗi resource đã mở được release đúng một lần.
- Complete, error, cancel chạy đúng cleanup branch.
- Lỗi nghiệp vụ không bị biến thành success ngoài ý muốn.
- take/timeout có thể cancel upstream trong khi downstream complete/error.
- ThreadLocal không phải nguồn sự thật cho request metadata trong reactive chain.

## 2. Mô hình lifecycle

~~~text
HTTP request
    |
    v
WebFilter: validate/generate requestId
    |
    v
contextWrite(requestId, tenant/principal)
    |
    v
Controller -> Service
    |
    v
usingWhen(open resource)
    |
    +---- ContextView: đọc metadata của request
    |
    +---- dependency call / async boundary
    |
    +---- complete ------> asyncComplete(resource)
    |
    +---- error ---------> asyncError(resource, error)
    |
    +---- downstream cancel -> asyncCancel(resource)
    |
    v
HTTP response / stream ends
~~~

| Tình huống | Upstream | Downstream |
| --- | --- | --- |
| Flux complete tự nhiên | ON_COMPLETE | ON_COMPLETE |
| Flux phát lỗi | ON_ERROR | ON_ERROR hoặc lỗi đã map |
| take(n) nhận đủ item | Có thể CANCEL | ON_COMPLETE |
| timeout hết hạn | CANCEL nguồn gốc | ON_ERROR(TimeoutException) |
| Client hủy stream | CANCEL nếu adapter truyền xuống | Không có terminal từ nguồn bị hủy |

Không thể chỉ nhìn HTTP status hoặc terminal signal ở controller rồi suy ra mọi operator upstream có cùng trạng thái.

## 3. Request Context thuộc về subscription

### 3.1. Khai báo key

~~~java
public final class RequestContext {
    public static final String REQUEST_ID = "app.requestId";
    public static final String TENANT_ID = "app.tenantId";

    private RequestContext() {}
}
~~~

Reactor Context là key-value bất biến gắn với Subscriber/subscription. Chọn key có namespace để tránh xung đột; không dùng một biến static mutable để giữ request ID hiện tại.

### 3.2. Ghi và đọc Context

~~~java
Mono<String> identify() {
    return Mono.deferContextual(view -> {
        String requestId = view.get(RequestContext.REQUEST_ID);
        String tenantId = view.get(RequestContext.TENANT_ID);
        return Mono.just(requestId + "|" + tenantId);
    });
}

Mono<String> result = identify()
    .contextWrite(context -> context
        .put(RequestContext.REQUEST_ID, "req-101")
        .put(RequestContext.TENANT_ID, "tenant-A")
    );
~~~

deferContextual đọc ContextView khi subscribe. Nếu key bắt buộc bị thiếu, view.get(key) ném lỗi; với key tùy chọn dùng getOrDefault/getOrEmpty.

### 3.3. Context sau async boundary

~~~java
Mono<String> identifyAfterDelay() {
    return Mono.delay(Duration.ofMillis(10))
        .then(Mono.deferContextual(view ->
            Mono.just(
                view.get(RequestContext.REQUEST_ID)
                    + "|"
                    + view.get(RequestContext.TENANT_ID)
            )
        ));
}
~~~

Mono.delay có thể chạy trên Scheduler khác. Context vẫn thuộc subscription, không phụ thuộc callback đang chạy trên thread nào.

### 3.4. Chiều nhìn của contextWrite

Data signal đi từ upstream xuống downstream, nhưng Context được cung cấp từ phía subscriber và được các operator **upstream của contextWrite** nhìn thấy.

~~~java
Mono<String> flow = Mono.deferContextual(view ->
        Mono.just(view.get(RequestContext.REQUEST_ID))
    )
    .contextWrite(context ->
        context.put(RequestContext.REQUEST_ID, "req-102")
    );
~~~

deferContextual nằm upstream nên đọc được req-102. Đặt contextWrite sai vị trí có thể khiến operator khác không thấy key. Khi debug, vẽ chain theo vị trí operator.

## 4. ThreadLocal và MDC không phải request context

MDC và một số thư viện imperative dùng ThreadLocal. Trong WebFlux, request có thể đổi thread; một thread cũng có thể phục vụ nhiều request.

~~~text
Request A -> reactor-http-nio-1 -> parallel-2
Request B -> reactor-http-nio-1
Request C -> reactor-http-nio-1 -> boundedElastic-1
~~~

Nếu gọi MDC.put("requestId", "A") rồi không khôi phục, thread được tái sử dụng có thể mang ID cũ sang request khác.

Nguyên tắc:

- Reactor Context giữ custom request metadata trong pipeline.
- MDC chỉ là adapter cho logging tại thời điểm ghi log.
- Micrometer Context Propagation cần accessor và reset/remove đúng.
- Không tự subscribe() tác vụ riêng rồi kỳ vọng Context/cancellation/error đi cùng subscription chính.
- Không capture request object hoặc SecurityContext chứa secrets vào static field.

Một MDC scope thủ công lưu giá trị trước và restore trong finally:

~~~java
static void withMdc(String requestId, Runnable action) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", requestId);
        action.run();
    }
    finally {
        if (previous == null) {
            MDC.remove("requestId");
        }
        else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

Scope này chỉ tồn tại trong callback đồng bộ; nó không làm ThreadLocal tự truyền qua async boundary.

## 5. Kiểm chứng lỗi: propagate, map và recover

### 5.1. Lỗi là terminal signal

~~~java
Mono<String> source =
    Mono.error(new IllegalStateException("database unavailable"));

StepVerifier.create(source)
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().equals("database unavailable")
    )
    .verify();
~~~

Không chỉ kiểm tra "có lỗi". Hãy xác minh đúng kiểu exception, message hoặc error code cần cho caller.

### 5.2. onErrorMap chuyển đổi loại lỗi

~~~java
Mono<String> publicResult = source
    .onErrorMap(
        IllegalStateException.class,
        error -> new DependencyFailure(
            "CATALOG_UNAVAILABLE",
            error
        )
    );
~~~

Đổi lỗi kỹ thuật thành domain/application exception nhưng giữ cause. Không tạo exception mới rồi bỏ nguyên nhân gốc nếu cần điều tra.

### 5.3. onErrorResume phục hồi bằng Publisher khác

~~~java
Mono<String> result = source
    .onErrorResume(
        TimeoutException.class,
        error -> Mono.just("fallback")
    );
~~~

Chỉ recover loại lỗi có fallback hợp lệ. Nếu database unavailable mà trả List rỗng, caller có thể hiểu nhầm là không có dữ liệu.

### 5.4. doOnError chỉ quan sát

~~~java
Mono<String> result = source
    .doOnError(error ->
        log.error("operation failed", error)
    );
~~~

doOnError không tiêu thụ lỗi và không biến nó thành success. Nếu cần recover, dùng onErrorResume hoặc operator tương ứng.

Không swallow lỗi cleanup bằng onErrorResume(error -> Mono.empty()) nếu điều đó che giấu lỗi close connection hoặc rollback. Chỉ bỏ qua khi có chính sách, metrics và lý do rõ ràng.

## 6. Cancellation là điều khiển ngược dòng

Subscriber có thể gọi Subscription.cancel() khi không cần dữ liệu nữa: client đóng HTTP/SSE/WebSocket, take(n) đủ item, timeout hết hạn, switchMap thay inner Publisher hoặc Disposable.dispose() được gọi.

Cancel không phải onComplete/onError. Nó cũng không tự rollback remote side effect đã thực hiện.

### 6.1. doOnCancel và doFinally

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() ->
        log.info("subscription cancelled")
    )
    .doFinally(signal ->
        log.info("ended: {}", signal)
    );
~~~

doOnCancel chạy khi cancel đi qua vị trí operator. doFinally nhận ON_COMPLETE, ON_ERROR hoặc CANCEL. Với complete/error, callback doFinally có thể chạy sau terminal signal đã tới downstream; test callback async bằng latch hoặc cơ chế await.

### 6.2. take có thể complete downstream nhưng cancel upstream

~~~java
Flux<Integer> firstTwo =
    Flux.range(1, 100)
        .doFinally(signal ->
            log.info("source signal={}", signal)
        )
        .take(2)
        .doFinally(signal ->
            log.info("result signal={}", signal)
        );
~~~

take(2) phát hai giá trị rồi complete downstream; nó có thể cancel source vì không cần phần còn lại. Hai hook có thể thấy CANCEL và ON_COMPLETE tương ứng.

### 6.3. timeout cancel nguồn gốc rồi phát lỗi

~~~java
Mono<String> result = remoteCall()
    .timeout(Duration.ofSeconds(2));
~~~

Khi timeout, remoteCall upstream thường nhận CANCEL, còn downstream nhận TimeoutException. Nếu có fallback, downstream có thể tiếp tục và hoàn tất bằng kết quả fallback.

## 7. Resource lifecycle với usingWhen

Khi resource cần giải phóng bất đồng bộ, dùng usingWhen thay vì gọi closeReactive().subscribe() trong doFinally.

~~~java
Mono.usingWhen(
    resourceSupplier,
    resource -> useResource(resource),
    resource -> cleanupOnComplete(resource),
    (resource, error) -> cleanupOnError(resource, error),
    resource -> cleanupOnCancel(resource)
);
~~~

| Nhánh resource closure | Callback cleanup |
| --- | --- |
| Complete | cleanupOnComplete |
| Error | cleanupOnError |
| Downstream cancel | cleanupOnCancel |

Flux.usingWhen có cấu trúc tương tự. Mono.usingWhen phù hợp với một kết quả; Flux.usingWhen phù hợp với stream nhiều phần tử.

### 7.1. Resource supplier theo subscription

~~~java
Mono.usingWhen(
    Mono.fromSupplier(connectionFactory::openLease),
    lease -> executeQuery(lease),
    Lease::closeAsync,
    (lease, error) -> lease.rollbackAsync(),
    Lease::closeAsync
);
~~~

Mỗi subscription nhận một lease. Không mở connection một lần ở assembly rồi để nhiều request cùng sử dụng và cùng đóng.

### 7.2. Không fire-and-forget cleanup

Sai:

~~~java
.doFinally(signal ->
    lease.closeReactive().subscribe()
)
~~~

Subscription cleanup này tách khỏi pipeline gốc. Lỗi cleanup không được compose; cancellation có thể kết thúc trong khi tác vụ release vẫn chạy.

Để usingWhen nhận cleanup Publisher và điều phối theo nhánh lifecycle. Nếu nhiều đường logic có thể yêu cầu release, bảo vệ trạng thái bằng AtomicBoolean, nhưng vẫn cần một owner rõ ràng.

### 7.3. Resource release khác business rollback

Đóng connection không nhất thiết có nghĩa transaction đã rollback đúng cách. Với R2DBC, dùng TransactionalOperator/R2dbcTransactionManager hoặc API transaction có contract rõ ràng. Test commit, rollback và close khi nghiệp vụ cần bảo đảm các bước đó.

## 8. Resource ledger và bất biến

Trong bài thực hành, ResourceLedger đếm:

- opened: số lease đã mở.
- completed: số lease release qua nhánh complete.
- failed: số lease release qua nhánh error.
- cancelled: số lease release qua nhánh cancel.
- active: số lease chưa được release.

Bất biến sau khi test kết thúc:

~~~text
opened = completed + failed + cancelled + active
~~~

Khi không còn request nào active, active phải bằng 0. Nếu mỗi lease chỉ được release một lần, tổng ba outcome bằng số lease đã đóng.

Đây là công cụ test/diagnostic. Production có thể dùng Micrometer metrics tương ứng, nhưng không gắn request ID có cardinality cao làm metric tag.

## 9. Ví dụ tích hợp: RequestScopedFlow

Ứng dụng demo tạo resource theo subscription và đọc Context trong async boundary.

Ba luồng:

- complete(): mở lease, đợi async hop, đọc request context, trả kết quả và cleanup complete.
- fail(): mở lease, đọc context rồi phát DomainFailure, cleanup error.
- stream(): mở lease và phát tick vô hạn; khi downstream take(2) hoặc client cancel, cleanup cancel.

Context có requestId và tenantId để kiểm tra tenant isolation.

### 9.1. Cấu trúc dự án

~~~text
reactor-request-verification/
├── pom.xml
└── src/
    ├── main/java/com/example/verification/
    │   └── RequestScopeDemo.java
    └── test/java/com/example/verification/
        └── RequestScopeTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-request-verification</artifactId>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ chạy với **Java 17+** và **Reactor 3.8.8**. Maven compiler release được đặt là 17.

### 9.3. RequestScopeDemo.java

~~~java
package com.example.verification;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.context.ContextView;

public final class RequestScopeDemo {

    public static final String REQUEST_ID = "app.requestId";
    public static final String TENANT_ID = "app.tenantId";

    private final ResourceLedger ledger =
        new ResourceLedger();

    public Mono<String> identifyAfterAsyncHop() {
        return Mono.delay(Duration.ofMillis(5))
            .then(Mono.deferContextual(context ->
                Mono.just(render(context))
            ));
    }

    public Mono<String> complete() {
        return Mono.usingWhen(
            Mono.fromSupplier(ledger::open),
            lease -> identifyAfterAsyncHop(),
            ledger::complete,
            ledger::failed,
            ledger::cancelled
        );
    }

    public Mono<String> fail() {
        return Mono.usingWhen(
            Mono.fromSupplier(ledger::open),
            lease -> Mono.delay(Duration.ofMillis(5))
                .then(Mono.deferContextual(context ->
                    Mono.<String>error(
                        new DomainFailure(
                            "DOWNSTREAM_FAILURE",
                            "Simulated dependency failure"
                        )
                    )
                )),
            ledger::complete,
            ledger::failed,
            ledger::cancelled
        );
    }

    public Flux<String> stream() {
        return Flux.usingWhen(
            Mono.fromSupplier(ledger::open),
            lease -> Flux.deferContextual(context ->
                Flux.interval(Duration.ofMillis(10))
                    .map(tick -> render(context) + "|" + tick)
            ),
            ledger::complete,
            ledger::failed,
            ledger::cancelled
        );
    }

    private static String render(ContextView context) {
        String requestId = context.get(REQUEST_ID);
        String tenantId = context.get(TENANT_ID);
        return requestId + "|" + tenantId;
    }

    public ResourceLedger.Snapshot snapshot() {
        return ledger.snapshot();
    }

    static final class Lease {
        private final AtomicBoolean released =
            new AtomicBoolean();
    }

    static final class ResourceLedger {

        private final AtomicInteger opened = new AtomicInteger();
        private final AtomicInteger completed = new AtomicInteger();
        private final AtomicInteger failed = new AtomicInteger();
        private final AtomicInteger cancelled = new AtomicInteger();
        private final AtomicInteger active = new AtomicInteger();

        Lease open() {
            opened.incrementAndGet();
            active.incrementAndGet();
            return new Lease();
        }

        Mono<Void> complete(Lease lease) {
            return release(lease, completed);
        }

        Mono<Void> failed(Lease lease, Throwable error) {
            return release(lease, failed);
        }

        Mono<Void> cancelled(Lease lease) {
            return release(lease, cancelled);
        }

        private Mono<Void> release(
            Lease lease,
            AtomicInteger outcome
        ) {
            return Mono.fromRunnable(() -> {
                if (lease.released.compareAndSet(false, true)) {
                    outcome.incrementAndGet();
                    active.decrementAndGet();
                }
            });
        }

        Snapshot snapshot() {
            return new Snapshot(
                opened.get(),
                completed.get(),
                failed.get(),
                cancelled.get(),
                active.get()
            );
        }

        record Snapshot(
            int opened,
            int completed,
            int failed,
            int cancelled,
            int active
        ) {}
    }

    public static final class DomainFailure
            extends RuntimeException {

        private final String code;

        DomainFailure(String code, String message) {
            super(message);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        RequestScopeDemo demo = new RequestScopeDemo();

        String identified = demo.identifyAfterAsyncHop()
            .contextWrite(context -> context
                .put(REQUEST_ID, "req-001")
                .put(TENANT_ID, "tenant-A")
            )
            .block();

        System.out.println("identify=" + identified);

        String completed = demo.complete()
            .contextWrite(context -> context
                .put(REQUEST_ID, "req-002")
                .put(TENANT_ID, "tenant-A")
            )
            .block();

        System.out.println("complete=" + completed);

        try {
            demo.fail()
                .contextWrite(context -> context
                    .put(REQUEST_ID, "req-003")
                    .put(TENANT_ID, "tenant-B")
                )
                .block();
        }
        catch (DomainFailure error) {
            System.out.println("error=" + error.code());
        }

        var values = demo.stream()
            .take(2)
            .contextWrite(context -> context
                .put(REQUEST_ID, "req-004")
                .put(TENANT_ID, "tenant-B")
            )
            .collectList()
            .block();

        System.out.println("stream=" + values);
        System.out.println("ledger=" + demo.snapshot());
    }
}
~~~

### 9.4. Giải thích service

- identifyAfterAsyncHop() đợi async boundary rồi đọc ContextView, không lấy ID từ ThreadLocal.
- complete() dùng Mono.usingWhen và cleanup complete.
- fail() tạo DomainFailure sau async hop; usingWhen chạy nhánh failed.
- stream() dùng Flux.usingWhen với nguồn interval vô hạn.
- take(2) hoàn tất kết quả hai item nhưng cancel stream upstream; usingWhen gọi nhánh cancelled.
- ResourceLedger bảo vệ release bằng AtomicBoolean để mỗi lease chỉ tăng đúng một outcome counter.
- snapshot() cho phép test kiểm tra active đã trở về 0.

Trong ứng dụng thực tế, lease có thể là connection, cursor, file handle hoặc subscription broker. Cleanup method trả Publisher thực hiện commit/rollback/close phù hợp.

### 9.5. RequestScopeTest.java

~~~java
package com.example.verification;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.*;

class RequestScopeTest {

    private static final String REQUEST_ID =
        RequestScopeDemo.REQUEST_ID;
    private static final String TENANT_ID =
        RequestScopeDemo.TENANT_ID;

    @Test
    void contextSurvivesAsyncBoundary() {
        RequestScopeDemo demo = new RequestScopeDemo();

        StepVerifier.create(
                demo.identifyAfterAsyncHop()
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-A")
                        .put(TENANT_ID, "tenant-A")
                    )
            )
            .expectNext("req-A|tenant-A")
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void concurrentRequestsKeepIndependentContexts() {
        RequestScopeDemo demo = new RequestScopeDemo();

        Mono<List<String>> results =
            Flux.range(1, 40)
                .flatMap(index ->
                    demo.identifyAfterAsyncHop()
                        .contextWrite(context -> context
                            .put(REQUEST_ID, "req-" + index)
                            .put(TENANT_ID, "tenant-" + index)
                        ),
                    8
                )
                .collectList();

        StepVerifier.create(results)
            .assertNext(values -> {
                assertEquals(40, values.size());
                for (int index = 1; index <= 40; index++) {
                    assertTrue(values.contains(
                        "req-" + index + "|tenant-" + index
                    ));
                }
            })
            .expectComplete()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void completePathReleasesResource() {
        RequestScopeDemo demo = new RequestScopeDemo();
        var before = demo.snapshot();

        StepVerifier.create(
                demo.complete()
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-complete")
                        .put(TENANT_ID, "tenant-A")
                    )
            )
            .expectNext("req-complete|tenant-A")
            .expectComplete()
            .verify(Duration.ofSeconds(2));

        var after = demo.snapshot();

        assertEquals(before.opened() + 1, after.opened());
        assertEquals(before.completed() + 1, after.completed());
        assertEquals(before.failed(), after.failed());
        assertEquals(before.cancelled(), after.cancelled());
        assertEquals(before.active(), after.active());
    }

    @Test
    void errorPathPreservesFailureAndReleasesResource() {
        RequestScopeDemo demo = new RequestScopeDemo();
        var before = demo.snapshot();

        StepVerifier.create(
                demo.fail()
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-error")
                        .put(TENANT_ID, "tenant-B")
                    )
            )
            .expectErrorSatisfies(error -> {
                assertInstanceOf(
                    RequestScopeDemo.DomainFailure.class,
                    error
                );
                var failure =
                    (RequestScopeDemo.DomainFailure) error;
                assertEquals("DOWNSTREAM_FAILURE", failure.code());
            })
            .verify(Duration.ofSeconds(2));

        var after = demo.snapshot();

        assertEquals(before.opened() + 1, after.opened());
        assertEquals(before.failed() + 1, after.failed());
        assertEquals(before.active(), after.active());
    }

    @Test
    void takeCompletesDownstreamAndCancelsResourceScope() {
        RequestScopeDemo demo = new RequestScopeDemo();
        var before = demo.snapshot();

        StepVerifier.create(
                demo.stream()
                    .take(2)
                    .contextWrite(context -> context
                        .put(REQUEST_ID, "req-cancel")
                        .put(TENANT_ID, "tenant-C")
                    )
            )
            .expectNext(
                "req-cancel|tenant-C|0",
                "req-cancel|tenant-C|1"
            )
            .expectComplete()
            .verify(Duration.ofSeconds(2));

        var after = demo.snapshot();

        assertEquals(before.opened() + 1, after.opened());
        assertEquals(before.cancelled() + 1, after.cancelled());
        assertEquals(before.active(), after.active());
    }

    @Test
    void timeoutCancelsTheOriginalPublisher() {
        PublisherProbe<String> remote =
            PublisherProbe.of(Mono.<String>never());

        StepVerifier.withVirtualTime(() ->
                remote.mono().timeout(Duration.ofSeconds(30))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(30))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));

        remote.assertWasSubscribed();
        remote.assertWasCancelled();
    }

    @Test
    void takeCancelsThePublisherItNoLongerNeeds() {
        PublisherProbe<Integer> source =
            PublisherProbe.of(Flux.range(1, 100));

        StepVerifier.create(source.flux().take(2))
            .expectNext(1, 2)
            .expectComplete()
            .verify(Duration.ofSeconds(2));

        source.assertWasSubscribed();
        source.assertWasCancelled();
    }

    @Test
    void testPublisherCanDriveAnErrorDeterministically() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux())
            .then(() -> source.next("accepted"))
            .expectNext("accepted")
            .then(() -> source.error(
                new IllegalArgumentException("bad event")
            ))
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                    && "bad event".equals(error.getMessage())
            )
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void missingRequiredContextFailsClearly() {
        RequestScopeDemo demo = new RequestScopeDemo();

        StepVerifier.create(demo.identifyAfterAsyncHop())
            .expectError()
            .verify(Duration.ofSeconds(2));
    }
}
~~~

### 9.6. Những điều test chứng minh

| Test | Chứng cứ |
| --- | --- |
| contextSurvivesAsyncBoundary | ContextView vẫn đọc được sau delay |
| concurrentRequestsKeepIndependentContexts | 40 subscription không trộn requestId/tenantId |
| completePathReleasesResource | asyncComplete tăng, active không tăng |
| errorPathPreservesFailureAndReleasesResource | DomainFailure được giữ và nhánh failed chạy |
| takeCompletesDownstreamAndCancelsResourceScope | downstream complete, cleanup cancel được gọi |
| timeoutCancelsTheOriginalPublisher | TimeoutException ở downstream, PublisherProbe thấy upstream cancel |
| takeCancelsThePublisherItNoLongerNeeds | take(2) không để source tiếp tục |
| testPublisherCanDriveAnErrorDeterministically | TestPublisher phát item rồi lỗi theo kịch bản |
| missingRequiredContextFailsClearly | Thiếu Context bắt buộc thì lỗi rõ ràng |

### 9.7. Chạy chương trình

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=com.example.verification.RequestScopeDemo
~~~

Output kỳ vọng:

~~~text
identify=req-001|tenant-A
complete=req-002|tenant-A
error=DOWNSTREAM_FAILURE
stream=[req-004|tenant-B|0, req-004|tenant-B|1]
ledger=Snapshot[opened=3, completed=1, failed=1, cancelled=1, active=0]
~~~

Chạy test:

~~~bash
mvn clean test
~~~

Kỳ vọng: 9 JUnit tests PASS. Đây là output kỳ vọng từ code đã trình bày; cần chạy Maven trong môi trường dự án để xác nhận thực tế.

## 10. Đưa request context vào Spring WebFlux

WebFilter là ranh giới phù hợp để validate/generate request ID rồi đưa nó vào Reactor Context.

~~~java
@Component
public class RequestContextWebFilter implements WebFilter {

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        return Mono.defer(() -> {
            String incoming = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Request-ID");

            String requestId =
                incoming != null
                    && SAFE_ID.matcher(incoming).matches()
                    ? incoming
                    : UUID.randomUUID().toString();

            exchange.getResponse().getHeaders().set(
                "X-Request-ID",
                requestId
            );

            return chain.filter(exchange)
                .contextWrite(context ->
                    context.put(
                        RequestScopeDemo.REQUEST_ID,
                        requestId
                    )
                );
        });
    }
}
~~~

Imports cần có: Pattern, UUID, Component, ServerWebExchange, WebFilter, WebFilterChain và Mono. Đây là adapter Spring WebFlux minh họa; dự án Reactor thuần ở phần trước không phụ thuộc Spring.

### 10.1. Tenant phải đến từ nguồn tin cậy

Không lấy tenant ID từ header tùy ý của client rồi dùng làm ranh giới bảo mật. Trong production, tenant cần được suy ra từ authenticated principal/claim hoặc gateway tin cậy, rồi ghi vào Context bằng contextWrite.

### 10.2. Response header và controller

Trả X-Request-ID giúp người gọi cung cấp mã khi báo lỗi. Nếu browser cần đọc custom response header qua CORS, phải expose header theo chính sách CORS. Không đưa stack trace, secrets hoặc thông tin nội bộ vào response.

Controller phải return Publisher:

~~~java
@GetMapping("/orders")
public Flux<OrderDto> orders() {
    return service.findOrders();
}
~~~

Không gọi subscribe() hoặc block() bên trong controller. WebFlux adapter sở hữu subscription và có thể truyền cancellation khi HTTP client disconnect.

## 11. Error handling tại HTTP boundary

Một lớp @RestControllerAdvice có thể map domain error thành status và body ổn định:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DomainFailure.class)
    public ResponseEntity<ApiError> handle(
        DomainFailure error
    ) {
        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ApiError(
                error.code(),
                "The operation could not be completed"
            ));
    }

    public record ApiError(
        String code,
        String message
    ) {}
}
~~~

Đây là snippet Spring MVC/WebFlux compatible theo annotation API; cần imports và DomainFailure của ứng dụng.

Không trả error.getMessage() tùy tiện nếu nó có thể chứa hostname, SQL, token hoặc dữ liệu nội bộ. Ghi log chi tiết ở server với request ID; trả error code an toàn cho client.

## 12. Tích hợp WebClient và dependency

Khi gọi downstream, request context được đọc tại subscription và chuyển thành header theo contract.

~~~java
ExchangeFilterFunction requestIdFilter =
    (request, next) ->
        Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                RequestScopeDemo.REQUEST_ID,
                "missing"
            );

            ClientRequest outgoing =
                ClientRequest.from(request)
                    .headers(headers ->
                        headers.set("X-Request-ID", requestId)
                    )
                    .build();

            return next.exchange(outgoing);
        });
~~~

Đây là client-side WebClient filter. Trong production, thiếu request ID phải được xử lý rõ ràng; không dùng chuỗi "missing" chung cho mọi request. Nếu dùng Micrometer Tracing, để tracing framework truyền traceparent; custom X-Request-ID cần contract riêng.

Cancellation của WebClient cố gắng dừng I/O không còn cần thiết nhưng không chứng minh remote service chưa commit side effect. Với thao tác tạo đơn hàng/thanh toán, dùng idempotency key và reconciliation.

## 13. Kiểm chứng cancellation và resource trong test

### 13.1. StepVerifier

StepVerifier có thể:

- expectSubscription() xác nhận subscribe.
- thenRequest(n) điều khiển demand.
- expectNext/expectError/expectComplete xác minh tín hiệu.
- thenCancel() chủ động hủy.
- verify(Duration) đặt trần thời gian thực.
- withVirtualTime() kiểm tra timeout/delay mà không chờ thời gian thật.

Không dùng verify() vô hạn với Flux.never().

### 13.2. PublisherProbe

PublisherProbe xác minh source cụ thể được subscribe, request hoặc cancel. Đặt probe quanh đúng ranh giới cần chứng minh, đặc biệt khi take/timeout/switchMap hủy upstream hoặc inner Publisher.

### 13.3. TestPublisher

TestPublisher cho phép test phát next/error/complete ở thời điểm chủ động. Nó phù hợp để tạo lỗi dependency hoặc signal sequence mà không cần sleep.

### 13.4. Cleanup async phải được chờ

Nếu cleanup chạy trên Scheduler khác, verify cancellation không nhất thiết đợi tác vụ fire-and-forget bên ngoài. Dùng CountDownLatch, CompletableFuture hoặc Publisher cleanup được compose bằng usingWhen. Tránh Thread.sleep vì timing phụ thuộc máy CI.

### 13.5. Kiểm tra mỗi resource đúng một lần

Đếm open/complete/error/cancel và active. Sau test, kiểm tra:

~~~text
active = 0
opened = completed + failed + cancelled
~~~

Nếu hệ thống cho phép lease tồn tại lâu hơn request, cần mô hình lifecycle riêng và assertion theo trạng thái mong đợi thay vì ép active luôn bằng 0 ngay lập tức.

## 14. Retry, timeout và request context

Retry resubscribe lên upstream. Nếu request ID đại diện một logical request, giữ ID ổn định qua các attempt; nếu cần phân biệt attempt, thêm attempt number riêng.

~~~java
Mono.deferContextual(context ->
    remoteCall()
        .retryWhen(retryPolicy)
        .doOnError(error ->
            log.error(
                "requestId={} failed after retries",
                context.get(RequestScopeDemo.REQUEST_ID),
                error
            )
        )
);
~~~

Đây là snippet cần remoteCall và retryPolicy. Timeout có thể cancel nguồn gốc. Retry sau timeout tạo attempt mới; mỗi attempt cần deadline và budget rõ ràng. Không retry lỗi validation, authentication hoặc business rejection một cách mù quáng.

Context của một subscription không nên bị thay bằng một ID mới mỗi retry trừ khi semantics hệ thống yêu cầu ID per attempt.

## 15. Context loss ở ranh giới ngoài Reactor

Reactor Context không tự truyền qua mọi cơ chế Java:

- new Thread(...).
- CompletableFuture.supplyAsync(...).
- ExecutorService không instrument.
- Callback từ thư viện legacy.
- Message broker listener chạy độc lập.
- Một subscribe() riêng tạo subscription mới.

Với tác vụ ngoài Reactor, truyền request ID tường minh hoặc dùng Micrometer Context Propagation/ContextSnapshot và executor decorator phù hợp.

Nếu job được xử lý sau nhiều phút hoặc trên process khác, gửi metadata có cấu trúc trong message header rồi tạo Context mới ở consumer. Không gửi nguyên request object hoặc security credentials chỉ để giữ correlation.

## 16. Lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Request A log ra ID của B | Dùng ThreadLocal global và không restore | Reactor Context per subscription |
| ContextView thiếu key | contextWrite đặt sai vị trí hoặc không có key | Kiểm tra chain và fail fast |
| Resource leak khi client disconnect | Chỉ cleanup complete/error | usingWhen asyncCancel |
| Cleanup chạy hai lần | Nhiều owner cùng đóng resource | Một owner, release idempotent |
| Lỗi bị biến thành success | onErrorResume trả empty/giá trị giả | Recover đúng loại lỗi và giữ semantics |
| Lỗi cleanup bị mất | subscribe riêng hoặc swallow error | Compose cleanup Publisher |
| take(2) không thấy complete | Test mong upstream terminal thay vì downstream | Đo đúng phía operator |
| Timeout test chờ lâu | Dùng clock thật | StepVerifier.withVirtualTime |
| Test flaky | Thread.sleep và race | Latch, probe, verify timeout |
| Remote vẫn thực hiện POST sau cancel | Server đã nhận side effect | Idempotency/reconciliation |
| Một request ghi đè Context request khác | Static mutable map/ThreadLocal | contextWrite per subscription |
| active resource không về 0 | Thiếu release branch hoặc release lỗi | Ledger, metrics, heap/thread dump |
| MDC không được dọn | Không có finally/reset accessor | Scope restore/remove |
| Tenant data rò giữa người dùng | Tin tenant header từ client | Lấy tenant từ authenticated identity |
| Log quá nhiều stack trace | Mọi tầng đều doOnError log full exception | Chọn một boundary log chi tiết |

## 17. Checklist review một request reactive

1. Request ID được validate hoặc sinh tại boundary?
2. Tenant/principal lấy từ nguồn tin cậy?
3. Metadata được đưa vào Reactor Context bằng contextWrite?
4. Operator cần đọc Context có nằm đúng phía contextWrite?
5. Có ContextView đọc tại subscription thay vì static ThreadLocal?
6. Request A/B chạy đồng thời vẫn tách biệt?
7. Error được propagate/map đúng domain?
8. Recovery có thể che một lỗi thật không?
9. Timeout có cancel upstream?
10. Client disconnect có cancel stream?
11. Resource được tạo theo subscription?
12. usingWhen có đủ complete/error/cancel cleanup?
13. Cleanup async được compose và có thể quan sát lỗi?
14. Release có idempotent khi contract cần?
15. Active resource sau test có về trạng thái mong đợi?
16. Retry giữ đúng logical request ID?
17. WebClient truyền request ID/trace context theo contract?
18. Không có subscribe()/block() ẩn trong controller/service?
19. MDC scope có restore/remove?
20. Test có timeout hữu hạn và không dùng Thread.sleep?
21. Có integration test cho adapter/driver thật khi cần?
22. Có metrics cho active resource, failure, timeout và cancellation?

## 18. Bài tập thực hành

**Bài 1 — Context:** truyền requestId và tenantId bằng contextWrite; đọc bằng deferContextual sau Mono.delay.

**Bài 2 — Isolation:** chạy 100 subscription đồng thời với ID khác nhau; xác minh không có cặp requestId/tenantId bị trộn.

**Bài 3 — Missing context:** bỏ một key bắt buộc và xác minh lỗi rõ ràng thay vì fallback chung.

**Bài 4 — Error mapping:** chuyển DependencyException thành DomainFailure, giữ cause và error code.

**Bài 5 — Error recovery:** chỉ fallback TimeoutException; xác minh validation error vẫn được propagate.

**Bài 6 — Resource complete:** mở lease bằng usingWhen, complete và xác minh active trở về giá trị ban đầu.

**Bài 7 — Resource error:** phát lỗi từ resource closure và xác minh asyncError chạy một lần.

**Bài 8 — Resource cancel:** dùng Flux.interval + take(2), xác minh downstream complete nhưng asyncCancel chạy.

**Bài 9 — Timeout:** dùng virtual time để tạo TimeoutException và PublisherProbe xác minh upstream bị cancel.

**Bài 10 — TestPublisher:** chủ động phát item rồi error; xác minh thứ tự signal.

**Bài 11 — MDC:** mở scope, ném exception, xác minh ThreadLocal được restore.

**Bài 12 — WebFilter:** validate X-Request-ID, tạo UUID khi thiếu/sai và phản ánh trong response header.

**Bài 13 — WebClient:** chuyển request ID sang downstream header; kiểm tra bằng mock server.

**Bài 14 — Retry:** giữ cùng request ID qua ba attempt và thêm attempt number riêng.

**Bài 15 — Integration:** client hủy SSE giữa chừng, kiểm tra server cleanup và active resource.

**Bài 16 — Security:** lấy tenant từ authenticated principal, không tin X-Tenant-ID do client gửi.

## 19. Ghi nhớ

Một request reactive cần được kiểm chứng theo bốn chiều: **lỗi, cancellation, resource lifecycle và Context isolation**.

Reactor Context giữ metadata theo subscription, vì vậy request A và B có thể chạy trên cùng thread mà vẫn có ID riêng. StepVerifier và PublisherProbe xác minh tín hiệu và upstream cancellation. usingWhen kết nối cleanup với ba nhánh complete, error và cancel. Resource ledger hoặc metrics giúp chứng minh lease đã được release đúng một lần.

Đừng dùng MDC/ThreadLocal làm nguồn sự thật cho request trong WebFlux, không tự subscribe tác vụ phụ, không swallow cleanup error và không coi client cancel là rollback remote side effect. Test đồng thời, test lỗi, test timeout và test cancellation phải kiểm tra cả kết quả downstream lẫn trạng thái tài nguyên.

## 20. Tài liệu tham khảo

- Project Reactor Reference — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor Reference — Cleanup and Discard: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Project Reactor Reference — Testing: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Core API — Flux.usingWhen: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core API — Mono.usingWhen: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Test API — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test API — PublisherProbe: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html
- Reactor Test API — TestPublisher: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html
- Spring Framework Reference — WebFlux WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux-webfilter.html
- Spring Framework Reference — WebClient Filters: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
- Spring Framework Reference — Reactive Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Micrometer Context Propagation — Purpose and Usage: https://docs.micrometer.io/context-propagation/reference/
- Reactive Streams Specification: https://www.reactive-streams.org/
