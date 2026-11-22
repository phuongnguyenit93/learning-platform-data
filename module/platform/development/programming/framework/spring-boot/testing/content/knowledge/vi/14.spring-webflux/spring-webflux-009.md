# Kiểm tra Reactor Context được truyền trong chuỗi xử lý Spring WebFlux

## 1. Mục tiêu: xác minh metadata đi đúng qua một reactive chain

Trong Spring WebFlux, HTTP request có thể đi qua **WebFilter → Controller → Service → Mono/Flux** và được thực thi trên nhiều thread khác nhau. Một đoạn mã dùng ThreadLocal để lưu requestId rồi đọc ở service không nhất thiết hoạt động sau khi publishOn hoặc một phép xử lý bất đồng bộ làm thay đổi thread.

**Reactor Context** cung cấp cơ chế truyền metadata theo **subscription**, không theo Java Thread. Thay vì thêm requestId vào mọi chữ ký phương thức, lớp đầu vào có thể đặt một key trong Context; các Reactor operators phía upstream có thể đọc key đó khi pipeline được subscribe. Điều thiết yếu không phải chỉ biết cách gọi API, mà là **viết test chứng minh Context thực sự đi đến consumer, không bị mất hay trộn giữa các request**.

Sau bài học, bạn có thể:
- Giải thích sự khác biệt giữa **Reactor Context**, ThreadLocal, ServerWebExchange attributes và HTTP headers.
- Phân biệt **Context** (immutable key-value) với **ContextView** (read-only).
- Đọc và ghi metadata bằng **Mono.deferContextual**, **Flux.deferContextual**, **contextWrite**, **getOrDefault**, **getOrEmpty**.
- Hiểu chiều propagation từ downstream subscriber lên upstream và vì sao vị trí contextWrite quan trọng.
- Kiểm tra Context bằng **StepVerifier**, **StepVerifierOptions.withInitialContext** và **expectAccessibleContext**.
- Kiểm thử các trường hợp đúng, thiếu key, ghi đè, publishOn, flatMap và hai subscriptions không nhiễm dữ liệu.
- Dùng Spring WebFlux **WebFilter** đưa X-Request-Id vào Reactor Context, rồi dùng WebTestClient xác minh response body và header.
- Nhận diện các boundary làm mất Context: subscribe thủ công, ThreadLocal không có bridge, CompletableFuture riêng và HTTP call sang dịch vụ khác.

Ví dụ chạy trên **Java 17, Spring Boot 3.3.5, Reactor 3.6.x, Gradle, JUnit Jupiter và reactor-test**. Project dùng WebFlux và embedded reactive server, không dùng Spring MVC.

## 2. Mental model: Context gắn với Subscriber

| Cơ chế | Gắn với đối tượng nào? | Khi dùng | Giới hạn |
|---|---|---|---|
| Java ThreadLocal | Một Java Thread | Imperative code trên thread ổn định | Không tự đi theo reactive thread hopping |
| HTTP request header | Một HTTP message | Truyền correlation ID qua network | Header do client gửi không tự đáng tin |
| ServerWebExchange attributes | Exchange của request WebFlux | Chia sẻ dữ liệu giữa components nắm exchange | Không tự xuất hiện trong bất kỳ reactive chain nào |
| Reactor Context | **Subscriber/subscription** | Truyền metadata dọc Reactor pipeline | Chỉ nơi có ContextView và đúng chain mới đọc được |
| ContextView | Read-only view của Context | Đọc ở source/inner publisher | Không thể sửa trực tiếp |
| SecurityContext reactive | Cơ chế Spring Security dựa trên reactive Context | Authentication/authorization | Phải được security infrastructure thiết lập, không tự tin header |

**Reactor Context không phải global map.** Cùng một Mono có thể được subscribe hai lần với Context khác nhau; mỗi subscription nhìn thấy metadata thuộc về nó. Các lệnh put/delete tạo Context mới, nên **Context bất biến về cấu trúc**, nhưng một object mutable như HashMap đặt làm value vẫn có thể bị thay đổi và gây race.

Context có key và value không null. Key có thể là một String constant hoặc một object/Class key. Với bài mẫu, dùng String constant để code dễ hiểu; với library lớn, nên tránh key collision giữa các thư viện.

**Context không thay thế business data.** Tên người dùng, số lượng sản phẩm, đơn hàng vẫn thuộc dữ liệu nghiệp vụ của Mono/Flux hoặc method parameters. Context hợp với request correlation ID, trace metadata, locale hoặc các yếu tố mang tính cross-cutting. Không biến nó thành kho chứa payload khổng lồ, cache mutable hoặc một kênh ẩn đưa dữ liệu bảo mật chưa xác thực qua mọi lớp.

## 3. Cơ chế ghi từ dưới lên: contextWrite chỉ ảnh hưởng upstream

Trong Reactor, data signal đi từ source tới subscriber; còn **Context** đi ngược từ subscriber tới các operators upstream khi hình thành subscription:

~~~text
Source / Mono.deferContextual(ctx -> ...)
               ^
               | Context đi lên
               |
           flatMap / map
               ^
               |
     contextWrite(ctx -> ctx.put(KEY, "r-1"))
               ^
               |
        StepVerifier / subscribe()

onNext/onComplete đi từ Source xuống Subscriber
Context đi từ Subscriber lên phía Source
~~~

Ví dụ đọc đúng:

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
    .contextWrite(Context.of("requestId", "R-7"));

StepVerifier.create(source)
    .expectNext("R-7")
    .verifyComplete();
~~~

Đây là đoạn minh họa **bên trong một class test** đã import Mono, Context và StepVerifier. Vì contextWrite nằm **downstream** so với deferContextual, nguồn đọc được key khi subscribe.

Ví dụ dễ nhầm:

~~~java
Mono<String> source = Mono.just("value")
    .contextWrite(Context.of("requestId", "R-7"))
    .flatMap(value -> Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("requestId", "missing"))));

StepVerifier.create(source)
    .expectNext("missing")
    .verifyComplete();
~~~

Nguyên nhân: contextWrite trên chỉ tác động đến **Mono.just phía upstream của nó**. Toán tử flatMap ở downstream không có key ấy. Đây không phải bằng chứng rằng flatMap làm mất Context; mà là **contextWrite được đặt sai vị trí so với operator cần đọc**.

Sửa vị trí:

~~~java
Mono<String> source = Mono.just("value")
    .flatMap(value -> Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId") + ":" + value)))
    .contextWrite(Context.of("requestId", "R-7"));

StepVerifier.create(source)
    .expectNext("R-7:value")
    .verifyComplete();
~~~

### 3.1. Ghi đè cùng một key

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")))
    .contextWrite(Context.of("requestId", "near"))
    .contextWrite(Context.of("requestId", "far"));

StepVerifier.create(source)
    .expectNext("near")
    .verifyComplete();
~~~

Khi subscription đi ngược chuỗi, Context ở phía cuối đặt "far" trước. Sau đó contextWrite gần source hơn ghi đè "near"; reader nhìn thấy "near". Không thể đơn giản lấy “dòng cuối cùng trong source Java thắng” làm quy tắc.

### 3.2. Context là cấu trúc bất biến

~~~java
Context before = Context.of("requestId", "A");
Context after = before.put("requestId", "B");

// before vẫn giữ A; after chứa B.
~~~

Nếu viết contextWrite nhận một Function, nên **trả** Context mới:

~~~java
.contextWrite(ctx -> ctx.put("requestId", "B"))
~~~

Đừng gọi ctx.put rồi bỏ qua kết quả. Cũng không nên thay toàn bộ Context bằng Context.of(...) trong một Function khi không cần, bởi code/framework khác có thể đã đưa những key có ý nghĩa vào Context ban đầu.

## 4. Đọc dữ liệu đúng thời điểm: deferContextual và ContextView

**Mono.deferContextual** chỉ gọi factory khi có subscription, đúng lúc Context đã hiện diện. Điều này khác với việc lấy giá trị ThreadLocal hoặc biến global lúc đang lắp ghép reactive chain.

~~~java
Mono<String> readId = Mono.deferContextual(ctx -> {
    String id = ctx.getOrDefault("requestId", "not-set");
    return Mono.just(id);
});
~~~

Các cách truy cập:

| API | Nếu key không có | Phù hợp |
|---|---|---|
| ctx.get(key) | Ném NoSuchElementException | Key thực sự bắt buộc |
| ctx.getOrDefault(key, fallback) | Trả fallback | Correlation metadata tùy chọn |
| ctx.getOrEmpty(key) | Optional.empty() | Xử lý hai nhánh có/không rõ ràng |
| ctx.hasKey(key) | false | Kiểm tra sự hiện diện |
| ctx.stream() | Duyệt entries | Debug có chọn lọc, không log mọi dữ liệu |

Với get, hãy để **StepVerifier.expectError(NoSuchElementException.class)** chứng minh trường hợp key bắt buộc bị thiếu. Với getOrDefault, cần test riêng để tránh nhầm “code đã dùng Context” với “code chỉ luôn trả fallback”.

**transformDeferredContextual** là lựa chọn khi bạn cần đọc ContextView ở giữa chuỗi:

~~~java
Mono<String> result = Mono.just("Hello")
    .transformDeferredContextual((publisher, ctx) ->
            publisher.map(value -> value + " [" +
                    ctx.getOrDefault("requestId", "none") + "]"))
    .contextWrite(Context.of("requestId", "abc"));

StepVerifier.create(result)
    .expectNext("Hello [abc]")
    .verifyComplete();
~~~

Cách này giúp thêm metadata vào các item mà không luôn phải tạo source từ deferContextual. Tuy vậy khi logic phức tạp, hãy đặt một service method riêng đọc Context để test trực tiếp.

### 4.1. Vì sao tránh Mono.just(ThreadLocal.get())?

~~~java
// Anti-pattern minh họa, không phải chương trình đầy đủ:
String capturedId = REQUEST_ID_THREAD_LOCAL.get();
return Mono.just(capturedId)
        .publishOn(Schedulers.parallel());
~~~

Biến capturedId được đọc **trước subscription** và dựa trên thread lúc method được gọi. Nó không theo subscriber và không thể biểu diễn đúng hai subscriptions khác nhau của cùng một Mono. Nếu cần tích hợp logging MDC/ThreadLocal trong một ứng dụng reactive, dùng bridge/context-propagation phù hợp, không coi ThreadLocal là nguồn thay thế cho ContextView.

## 5. Ví dụ ứng dụng: requestId từ WebFilter đến service

Ta sẽ tạo API HTTP:

~~~http
GET /api/greetings?name=Lan HTTP/1.1
X-Request-Id: req-42
~~~

Khi thành công, response có header X-Request-Id=req-42 và JSON:

~~~json
{
  "message": "Hello, Lan",
  "requestId": "req-42"
}
~~~

Quy tắc của ví dụ:
- Nếu request header có 1–64 ký tự chỉ gồm A-Z, a-z, 0-9, dấu gạch dưới hoặc dấu gạch nối, nhận ID đó.
- Nếu thiếu header hoặc header sai format, tự sinh UUID.
- GreetingService đọc Context bằng Mono.deferContextual. Khi không có Context trong **unit test**, service trả fallback "not-set".
- Context chỉ phục vụ **correlation**, không dùng X-Request-Id làm credential, authorization hoặc tenant identity.
- Mỗi request dùng local variable requestId của filter; không lưu trong field mutable của singleton.

### 5.1. Các file

~~~text
settings.gradle
build.gradle
src/main/java/demo/context/ContextDemoApplication.java
src/main/java/demo/context/RequestContext.java
src/main/java/demo/context/GreetingResponse.java
src/main/java/demo/context/GreetingService.java
src/main/java/demo/context/GreetingController.java
src/main/java/demo/context/RequestIdWebFilter.java
src/test/java/demo/context/GreetingServiceContextTest.java
src/test/java/demo/context/GreetingWebFluxHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'webflux-context-test'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích:** spring-boot-starter-webflux cung cấp Spring WebFlux, Reactor và embedded Netty theo mặc định. StepVerifier nằm trong artifact **reactor-test**, nên khai báo testImplementation tường minh. Spring Boot BOM/dependency-management quản lý phiên bản Reactor tương thích; đừng tự ghép các phiên bản reactor-core và reactor-test không đồng bộ.

Ở dự án có thêm **spring-boot-starter-web**, Spring Boot thông thường ưu tiên MVC nếu có cả hai stack; cần xem cấu hình **spring.main.web-application-type** khi buộc chạy reactive. Bộ ví dụ chỉ dùng WebFlux.

### 5.2. Application chính và key

**src/main/java/demo/context/ContextDemoApplication.java**

~~~java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/context/RequestContext.java**

~~~java
package demo.context;

public final class RequestContext {

    public static final String REQUEST_ID = "requestId";

    private RequestContext() {
    }
}
~~~

**src/main/java/demo/context/GreetingResponse.java**

~~~java
package demo.context;

public record GreetingResponse(String message, String requestId) {
}
~~~

Việc dùng constant tránh lỗi gõ key không đồng nhất giữa filter, service và unit test. Trong một thư viện lớn, có thể chọn một key object/class riêng để tránh đụng tên với thư viện khác. Response record bất biến theo các String fields.

### 5.3. WebFilter ghi Context cho mỗi request

**src/main/java/demo/context/RequestIdWebFilter.java**

~~~java
package demo.context;

import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestIdWebFilter implements WebFilter {

    private static final String HEADER = "X-Request-Id";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String incoming =
                exchange.getRequest().getHeaders().getFirst(HEADER);

        String requestId =
                incoming != null &&
                incoming.matches("[A-Za-z0-9_-]{1,64}")
                        ? incoming
                        : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set(HEADER, requestId);

        return chain.filter(exchange)
                .contextWrite(context -> context.put(
                        RequestContext.REQUEST_ID, requestId));
    }
}
~~~

**Diễn giải:**

1. WebFilter đọc HTTP header; nếu giá trị không phù hợp quy tắc minh họa, tạo UUID (mỗi request khác nhau).
2. Nó gắn cùng ID vào HTTP response header.
3. **chain.filter(exchange)** biểu diễn reactive chain phía controller và service. **contextWrite** được áp vào Mono<Void> ở downstream, do đó toàn bộ phần upstream của chain có thể đọc key.
4. Filter không gọi **subscribe()**. Chính WebFlux framework sẽ subscribe để xử lý response; manual subscribe() dễ tạo subscription không có Context hoặc tách khỏi response lifecycle.
5. requestId là local variable của lần gọi filter, không phải mutable static field hay field singleton. Hai request không ghi đè trạng thái của nhau.

Trong hệ thống có nhiều filters, thứ tự thực hiện và response commit có thể ảnh hưởng việc đặt header; nếu cần bảo đảm cả các đường lỗi đặc biệt, kiểm tra thêm filter ordering hoặc beforeCommit. Bài mẫu chỉ cần flow đơn giản này.

### 5.4. Service đọc Context tại subscription

**src/main/java/demo/context/GreetingService.java**

~~~java
package demo.context;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    public Mono<GreetingResponse> greet(String name) {
        return Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    RequestContext.REQUEST_ID, "not-set");

            return Mono.just(new GreetingResponse(
                    "Hello, " + name, requestId));
        });
    }
}
~~~

Cần nhấn mạnh: deferContextual không “lấy Context của method Java gọi greet”; nó đọc **ContextView của subscriber** khi publisher được subscribe. Nếu method được gọi lúc lắp chain, trước subscription, vẫn không sao. Nếu source được subscribe khác nhau hai lần, mỗi subscription có thể nhận requestId khác.

**src/main/java/demo/context/GreetingController.java**

~~~java
package demo.context;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/api/greetings")
    public Mono<GreetingResponse> greet(
            @RequestParam("name") String name) {
        return service.greet(name);
    }
}
~~~

Controller không nhận trực tiếp X-Request-Id và không truyền nó qua các method signatures. WebFlux subscribe response Publisher và đi qua Context do filter cung cấp. Tham số name là required; nếu thiếu, Spring WebFlux thông thường trả HTTP 400 do request binding.

## 6. Bộ unit test StepVerifier: chứng minh propagation và phạm vi

**src/test/java/demo/context/GreetingServiceContextTest.java**

~~~java
package demo.context;

import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class GreetingServiceContextTest {

    private final GreetingService service = new GreetingService();

    @Test
    void readsIdProvidedByContext() {
        Mono<GreetingResponse> pipeline = service.greet("Lan")
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "unit-42"));

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Lan", "unit-42"))
                .verifyComplete();
    }

    @Test
    void fallbackIsExplicitWhenContextIsAbsent() {
        StepVerifier.create(service.greet("An"))
                .expectNext(new GreetingResponse(
                        "Hello, An", "not-set"))
                .verifyComplete();
    }

    @Test
    void survivesPublishOnAndNestedFlatMap() {
        Mono<GreetingResponse> pipeline = Mono.just("Mai")
                .publishOn(Schedulers.parallel())
                .flatMap(service::greet)
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "async-1"));

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Mai", "async-1"))
                .verifyComplete();
    }

    @Test
    void sameMonoCanHaveDifferentSubscriberContexts() {
        Mono<GreetingResponse> source = service.greet("Vy");

        StepVerifier.create(source.contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "request-A")))
                .expectNext(new GreetingResponse(
                        "Hello, Vy", "request-A"))
                .verifyComplete();

        StepVerifier.create(source.contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "request-B")))
                .expectNext(new GreetingResponse(
                        "Hello, Vy", "request-B"))
                .verifyComplete();
    }

    @Test
    void contextWriteTooFarUpstreamDoesNotReachReader() {
        Mono<GreetingResponse> pipeline = Mono.just("Lan")
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "too-high"))
                .flatMap(service::greet);

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Lan", "not-set"))
                .verifyComplete();
    }

    @Test
    void nearerContextWriteOverridesSameKey() {
        Mono<GreetingResponse> pipeline = service.greet("Lan")
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "near"))
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "far"));

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Lan", "near"))
                .verifyComplete();
    }

    @Test
    void stepVerifierInitialContextCanBeInspected() {
        Mono<String> readId = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get(
                        RequestContext.REQUEST_ID)));

        StepVerifierOptions options =
                StepVerifierOptions.create().withInitialContext(
                        Context.of(RequestContext.REQUEST_ID, "seed-7"));

        StepVerifier.create(readId, options)
                .expectAccessibleContext()
                .contains(RequestContext.REQUEST_ID, "seed-7")
                .then()
                .expectNext("seed-7")
                .verifyComplete();
    }

    @Test
    void missingMandatoryKeyIsErrorSignal() {
        Mono<String> strictReader = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("mandatoryKey")));

        StepVerifier.create(strictReader)
                .expectError(NoSuchElementException.class)
                .verify();
    }
}
~~~

Tám phương thức @Test có mục tiêu khác nhau:

| Test | Chứng minh điều gì? |
|---|---|
| readsIdProvidedByContext | contextWrite đưa ID tới deferContextual của service |
| fallbackIsExplicitWhenContextIsAbsent | Không có Context thì trả "not-set", không giả vờ ID tồn tại |
| survivesPublishOnAndNestedFlatMap | Context theo subscription qua scheduler hop và inner publisher |
| sameMonoCanHaveDifferentSubscriberContexts | Không rò ID A/B giữa hai subscriptions |
| contextWriteTooFarUpstreamDoesNotReachReader | Vị trí operator sai trả fallback, test tái hiện lỗi |
| nearerContextWriteOverridesSameKey | Cùng key, giá trị "near" được đọc |
| stepVerifierInitialContextCanBeInspected | StepVerifierOptions cung cấp Context; expectAccessibleContext kiểm tra key |
| missingMandatoryKeyIsErrorSignal | get key bắt buộc không có gây NoSuchElementException |

**Đừng assert tên thread trong các test này.** Scheduler được phép thay đổi cách đặt tên/thực thi thread. Điều cần chứng minh là **giá trị ID đúng**, bất kể thời điểm, thread và tốc độ CI. Không cần Thread.sleep để Context đi tới service; StepVerifier subscribe/verify chịu trách nhiệm hoàn thành Publisher.

### 6.1. get, getOrDefault, getOrEmpty: bắt lỗi đúng cách

Đọc key bắt buộc:

~~~java
Mono<String> strict = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")));

StepVerifier.create(strict)
    .expectError(NoSuchElementException.class)
    .verify();
~~~

Đọc key tùy chọn:

~~~java
Mono<String> optional = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>getOrEmpty("tenant")
                .orElse("public")));

StepVerifier.create(optional.contextWrite(
        Context.of("tenant", "acme")))
    .expectNext("acme")
    .verifyComplete();
~~~

Đây là snippets cho test đã import Mono, Context, StepVerifier, NoSuchElementException. **getOrDefault** chỉ nên dùng với metadata được phép thiếu; nếu userId/authorization bắt buộc thì fallback có thể che bug an ninh.

### 6.2. Khi cần kiểm chứng nhiều phần tử Flux

~~~java
Flux<String> items = Flux.just("a", "b", "c")
    .flatMap(item -> Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId") + ":" + item)))
    .contextWrite(Context.of("requestId", "batch-1"));

StepVerifier.create(items.collectList())
    .assertNext(values -> {
        org.junit.jupiter.api.Assertions.assertEquals(
                3, values.size());
        org.junit.jupiter.api.Assertions.assertTrue(
                values.containsAll(java.util.List.of(
                        "batch-1:a", "batch-1:b", "batch-1:c")));
    })
    .verifyComplete();
~~~

Snippet này dùng Flux, Mono, Context, StepVerifier, List trong test. Dùng **collectList + containsAll** vì flatMap có thể interleave nếu các inner publishers bất đồng bộ. Nếu thứ tự business có ý nghĩa, nên dùng concatMap hoặc assert sequence với hợp đồng ordering rõ. **expectNextCount(3)** đơn thuần không chứng minh các phần tử thật sự mang requestId.

## 7. Integration test WebTestClient: từ HTTP header đến JSON response

Unit test service chưa chứng minh filter được Spring WebFlux đăng ký. Ta cần kiểm thử **HTTP → WebFilter → Controller → Service → response**, dùng @SpringBootTest(RANDOM_PORT) với embedded reactive server thật.

**src/test/java/demo/context/GreetingWebFluxHttpTest.java**

~~~java
package demo.context;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingWebFluxHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void headerIsPropagatedToReactiveService() {
        client.get()
                .uri("/api/greetings?name=Lan")
                .header("X-Request-Id", "http-42")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Request-Id", "http-42")
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Lan")
                .jsonPath("$.requestId").isEqualTo("http-42");
    }

    @Test
    void missingHeaderGeneratesIdVisibleInBothPlaces() {
        EntityExchangeResult<GreetingResponse> result =
                client.get()
                        .uri("/api/greetings?name=Mai")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(GreetingResponse.class)
                        .returnResult();

        String id =
                result.getResponseHeaders().getFirst("X-Request-Id");

        assertNotNull(id);
        assertTrue(!id.isBlank());
        assertNotNull(result.getResponseBody());
        assertEquals(id, result.getResponseBody().requestId());
        assertEquals(
                "Hello, Mai", result.getResponseBody().message());
    }

    @Test
    void twoRequestsDoNotShareAnId() {
        client.get()
                .uri("/api/greetings?name=An")
                .header("X-Request-Id", "req-A")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-A");

        client.get()
                .uri("/api/greetings?name=An")
                .header("X-Request-Id", "req-B")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-B");
    }

    @Test
    void missingNameReturns400() {
        client.get()
                .uri("/api/greetings")
                .header("X-Request-Id", "bad-input")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

**Ý nghĩa bốn tests:**
1. Header X-Request-Id được filter đưa vào Reactor Context và service đọc thành body; response header lặp lại ID.
2. Khi không có header, filter tạo ID. Test so **hai output thuộc cùng request** thay vì assert một UUID ngẫu nhiên cố định.
3. Hai request tách biệt cho kết quả "req-A" và "req-B", không dùng field static requestId gây rò.
4. HTTP request thiếu name trả 400 từ binding, không phải fallback service có thể xử lý.

Với Spring Boot 3.3 và spring-webflux trên classpath, @SpringBootTest(RANDOM_PORT) cho phép autowire **WebTestClient** trỏ đến server đang chạy, hỗ trợ relative URI. Đây là **HTTP integration test**, không phải lời gọi service trực tiếp. TestRestTemplate cũng là lựa chọn khác ở mức HTTP, nhưng WebTestClient phù hợp hơn với WebFlux fluent assertions.

**Nếu dùng @WebFluxTest:** Test slice chỉ tải thành phần WebFlux theo phạm vi; nó không nhất thiết có đầy đủ service và filter do bạn tự viết. Khi muốn tập trung vào controller, cần đưa dependencies vào qua @Import hoặc mock của Spring Boot 3.3. Khi muốn chứng minh nguyên chuỗi application/filter đã được wiring, dùng @SpringBootTest như mẫu.

## 8. Cách chạy và tự xác nhận

Chạy trong project có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Các file source/build được cung cấp trong bài. Nếu chưa có Gradle Wrapper scripts, dùng Gradle tương thích để tạo wrapper hoặc chạy gradle test; **./gradlew** không tự tồn tại chỉ vì đã tạo build.gradle.

**Bộ ví dụ hoàn chỉnh có 12 phương thức JUnit Jupiter @Test:**
- GreetingServiceContextTest: **8 unit tests**.
- GreetingWebFluxHttpTest: **4 HTTP integration tests**.

Các snippet trong phần lý thuyết là ví dụ đặt trong method/test phù hợp, **không** thuộc bộ 12 method. Nếu tự thêm chúng thành @Test độc lập, báo cáo có nhiều case hơn.

Báo cáo mặc định ở **build/reports/tests/test/index.html**. Với source và dependencies đã cho, các test được thiết kế để PASS. Không khẳng định một stdout nguyên văn cố định; kết quả runtime/log server, port ngẫu nhiên và scheduler có thể khác theo môi trường.

Chạy riêng phần Reactor Context unit test:

~~~bash
./gradlew test --tests demo.context.GreetingServiceContextTest
~~~

Chạy riêng WebFlux HTTP integration:

~~~bash
./gradlew test --tests demo.context.GreetingWebFluxHttpTest
~~~

**Khi lỗi:** Nếu unit test đúng nhưng HTTP test sai, kiểm tra @Component của filter, package scan, Spring WebFlux startup, filter ordering và việc có ai gọi subscribe() bên trong. Nếu HTTP 200 nhưng requestId không khớp, kiểm tra đặc biệt vị trí contextWrite và key name ở service.

## 9. Context qua publishOn, subscribeOn và flatMap

**Reactor-native operators** giữ khái niệm subscriber/context dù có scheduler hop. Ví dụ:

~~~java
Mono<String> pipeline = Mono.just("item")
    .publishOn(Schedulers.boundedElastic())
    .flatMap(item -> Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId") + ":" + item)))
    .contextWrite(Context.of("requestId", "async-3"));

StepVerifier.create(pipeline)
    .expectNext("async-3:item")
    .verifyComplete();
~~~

Snippet này nằm trong test có imports. Context không phụ thuộc vào việc publisher chạy đúng một thread. **publishOn** chuyển scheduler cho các signal downstream; **subscribeOn** ảnh hưởng nơi thực hiện subscription/source theo semantics riêng. Cả hai đều không phải lệnh “xóa Context” trong chain Reactor bình thường.

Tuy nhiên, nếu bên trong flatMap bạn tạo CompletableFuture hoặc một subscription thủ công không được nối đúng vào reactive chain, context propagation qua boundary ấy **không tự được bảo đảm**. Cần truyền tham số hoặc dùng propagation bridge phù hợp.

### 9.1. Không viết subscribe thủ công trong service

~~~java
// Sai về kiến trúc request reactive:
Mono.deferContextual(ctx ->
        Mono.fromRunnable(() -> writeAudit(ctx.get("requestId"))))
    .subscribe();

return greetingService.greet("Lan");
~~~

Đây là snippet minh họa giả định có method writeAudit, không phải mã chạy độc lập. **subscribe()** ở đây tạo subscription khác, thường không kế thừa Context của request gốc như bạn mong muốn; cũng không còn gắn lifecycle lỗi/completion với HTTP response.

**Sửa theo hướng compose:**

~~~java
return Mono.deferContextual(ctx ->
        Mono.fromRunnable(() -> writeAudit(ctx.get("requestId"))))
    .then(greetingService.greet("Lan"));
~~~

Đoạn này dùng trong method trả Publisher; phần logic audit cần exception handling phù hợp với nghiệp vụ. Cách viết then nối các publishers trong một reactive chain được framework subscribe tại boundary. Không biến side effect thành fire-and-forget ngoài quản lý chỉ để tránh chờ một bước reactive.

### 9.2. Context và ThreadLocal/MDC cần bridge riêng

Một request có thể chuyển thread; do đó MDC trên thread A không tự hiện diện ở thread B. Với Reactor và Micrometer Context Propagation, có các cơ chế hỗ trợ bridging Reactor Context và ThreadLocal khi đăng ký accessor/hook thích hợp. Ví dụ **Hooks.enableAutomaticContextPropagation()** thuộc Reactor đời mới có thể kích hoạt propagation mode nhưng vẫn phụ thuộc các integration/dependencies và cách thiết lập ContextRegistry.

**Phân biệt rõ:**
- Test StepVerifier đọc ContextView **không chứng minh** MDC đúng.
- Bật một hook toàn JVM **có thể ảnh hưởng test khác**, cần quản lý setup/cleanup và concurrency.
- Không phải mọi ThreadLocal chưa đăng ký đều tự động được mang theo.
- Spring Boot observation/tracing có thể tự cấu hình một phần bridge theo phiên bản; xác nhận bằng test cụ thể thay vì giả định.

Bộ ví dụ của bài **không cần ThreadLocal** để hoạt động; đó là lựa chọn có chủ đích nhằm chỉ kiểm tra Reactor Context.

## 10. Phạm vi propagation và các boundary thực tế

| Boundary | Reactor Context tự đi theo? | Ghi chú |
|---|---|---|
| map/flatMap trong cùng chain Reactor | Có khi đặt contextWrite đúng vị trí | Inner publisher được compose, không tự subscribe tách rời |
| publishOn/subscribeOn của Reactor | Có trong reactive chain | Không phụ thuộc tên thread |
| Cùng Mono được subscribe hai lần | Mỗi lần có Context riêng | Không phải một global context dùng chung |
| WebFilter → Controller → Service trong WebFlux | Có nếu chain được compose/subscribe chuẩn | Cần test filter wiring |
| Manual subscribe() tạo subscription khác | **Không bảo đảm** kế thừa request Context | Tránh fire-and-forget trong service/filter |
| CompletableFuture/Executor tự tạo | Không mặc định | Truyền metadata hoặc bridge |
| WebClient gọi HTTP service ngoài | **Không tự biến thành HTTP header** | Thêm exchange filter/tracing phù hợp |
| Message queue/broker | Không tự truyền sang consumer khác | Metadata phải đưa vào message headers/payload |
| ThreadLocal/MDC trên thread khác | Không mặc định | Micrometer Context Propagation/hook |
| Spring Security reactive | Có cơ chế riêng trên Reactor Context | Dùng ReactiveSecurityContextHolder/API chính thức |

Nếu dùng Reactor Context cho **correlation ID xuyên microservices**, cần **đọc Context** ở outbound WebClient filter, **ghi X-Request-Id** vào HTTP request ngoài, và ở server đích nhận header rồi đặt nó vào Context mới. Reactor Context bên trong JVM A không tự được gửi trên dây mạng.

Nếu dùng **reactive transaction**, Spring dùng Reactor Context cho một phần transaction state. Đừng tự tạo một key tên "transaction" và coi đó là transaction thật: phải sử dụng ReactiveTransactionManager/TransactionalOperator hoặc cấu hình Spring reactive transaction chính thức, rồi integration test DB/R2DBC khi quan trọng.

## 11. Lỗi phổ biến và cách phát hiện

| Lỗi | Triệu chứng | Phương án |
|---|---|---|
| contextWrite nằm trước flatMap đọc Context | Reader thấy fallback | Chuyển contextWrite xuống cuối chain |
| get key bắt buộc khi Context không có | NoSuchElementException | Xác định key mandatory, test expectError hoặc fallback có chủ đích |
| Dùng key string sai chính tả | Context coi như thiếu key | Dùng constant hoặc typed key |
| Đọc từ ThreadLocal trong WebFlux | Null hoặc ID request khác khi đổi thread | Dùng deferContextual hoặc bridge |
| Tạo Mono.just từ dữ liệu đọc sớm | Giá trị bị capture trước subscription | Đọc trong deferContextual |
| Chỉ assert status 200 của WebTestClient | Không biết ID đã propagate đúng chưa | Assert response JSON và header cùng request ID |
| Dùng expectNextCount với Flux nhưng không kiểm values | Test pass dù IDs sai | Assert từng item hoặc collectList contents |
| Dùng manual subscribe trong service | Inner job không cùng Context/lifecycle | Compose publishers và return chain |
| Context chứa mutable HashMap | Race/leak dù Context immutable | Lưu value objects immutable |
| Dùng request header làm quyền truy cập | Có thể giả mạo identity | Dùng security principal xác thực |
| Context mất khi ra khỏi Reactor | API imperative/future không có bridge | Truyền tham số/propagation bridge |
| Test pass riêng nhưng fail suite parallel | Shared static state/global hook, fixture chung | Cô lập state, không dựa test order |
| WebFilter không được scan trong test slice | Unit pass, HTTP thiếu ID | @Import filter hoặc test full context |
| Xem MDC thay vì ContextView để kết luận propagation | Không thấy ID dù Context đúng | Test riêng từng tầng logging/Context |

Quy trình điều tra nên bắt đầu từ **đường subscriber**:
1. Xác định nơi ghi key vào Context và operator đọc.
2. Đặt contextWrite đủ downstream để upstream reader thấy nó.
3. Kiểm tra key/value type, dùng ContextView.getOrDefault cho optional key.
4. Viết StepVerifier với Context cụ thể, assert đúng output.
5. Kiểm tra scheduler/flatMap và nhiều subscriptions.
6. Nếu unit pass nhưng HTTP fail, kiểm tra WebFilter, ComponentScan, WebTestClient và server response.
7. Nếu vượt sang HTTP client khác, message broker, ThreadLocal hoặc future, xem propagation bridge tại boundary.
8. Chạy riêng và toàn suite, tránh mutable global state.

## 12. Context, bảo mật và dữ liệu nhiều tenant

Reactor Context là cơ chế tiện lợi để chứa metadata nhưng **không phải một kho quyền hạn**. Nếu cần userId, tenantId, security principal, hãy xác định nguồn dữ liệu đã được xác thực và cách authorization dùng dữ liệu ấy.

- **X-Request-Id** chỉ dành cho correlation, không dùng để chứng thực người gửi.
- Với Spring Security reactive, dùng **ReactiveSecurityContextHolder** để đọc security context do framework thiết lập; nó dùng reactive propagation thay vì giả định security principal luôn ở ThreadLocal.
- Không cho phép client tự ghi X-Tenant-Id rồi dùng nó để chọn DB/tenant mà chưa xác thực quyền.
- Không log toàn bộ Context vì thư viện/framework có thể đặt thông tin nhạy cảm vào đó.
- Đừng đưa password, access token thô hoặc PII vào Context nếu không thực sự cần.
- Một Context bất biến chứa một value mutable vẫn có thể tạo data race; nên ưu tiên record/immutable object.
- Với multi-tenant, thêm unit/integration tests chứng minh request A không đọc tenant của B; chạy cùng suite và trong môi trường concurrent khi cần.

Trong ví dụ hiện tại, requestId được kiểm tra regex và trả qua response, chỉ là **metadata quan sát**, không ảnh hưởng business authorization. Quy tắc này giúp tách bài học về Context propagation khỏi security design phức tạp.

## 13. Một số tình huống nâng cao

### 13.1. Retry/repeat và resubscription

Retry hoặc repeat có thể tạo **resubscription** tới upstream. Khi cấu trúc contextWrite vẫn thuộc chain, metadata downstream có thể được cung cấp lại cho nguồn. Nhưng nếu bạn dùng mutable counter/request object trong Context hoặc tạo side-effect ở lúc subscribe, retry có thể khiến hành vi khác dự kiến. Viết test cho policy retry riêng; đừng suy đoán mọi lần retry dùng cùng một nguồn dữ liệu mutable.

### 13.2. Hot publisher, cache và share

Một hot Flux hoặc Mono đã được cache/share có subscription semantics khác một cold Mono đơn giản. Context được gắn với Subscriber, vì vậy không thể suy luận một cached value luôn phản ánh Context của mọi subscriber sau đó. Nếu output phụ thuộc requestId thì **đừng cache một GreetingResponse đã chứa requestId** rồi dùng lại cho các request khác. Test ít nhất hai subscriptions khác nhau và xác nhận output không rò.

### 13.3. transformDeferredContextual

Khi một chuỗi cần đọc Context cùng item nhưng không muốn truyền nó vào chữ ký service, transformDeferredContextual có thể thực hiện biến đổi tại subscription. Chú ý vị trí contextWrite vẫn áp dụng: reader chỉ thấy Context đặt ở phía downstream. Test output thay vì chỉ kiểm tra Context hiện diện.

### 13.4. Khi chỉ cần truyền tham số thông thường

Nếu requestId chỉ được sử dụng trong một method đơn và không có cross-cutting concerns, đôi khi truyền tham số **greet(name, requestId)** trực tiếp dễ đọc và dễ test hơn. Reactor Context phù hợp với metadata phải được nhiều tầng xử lý mà không làm bẩn chữ ký hàm; đừng đưa mọi dữ liệu nghiệp vụ vào một Context không typed chỉ vì có API sẵn.

## 14. Bài tập

**Bài 1.** Tạo một Flux gồm ba sản phẩm; mỗi phần tử phải mang requestId "batch-7". Dùng Flux.flatMap + Mono.deferContextual, rồi StepVerifier.collectList/assertNext xác minh cả ba ID, không chỉ số lượng item.

**Bài 2.** Đặt contextWrite phía trước flatMap và chứng minh reader nhận fallback. Di chuyển xuống cuối chain rồi xác minh reader nhận đúng value. Giải thích bằng hướng propagation.

**Bài 3.** Đổi service thành ctx.get(KEY) để key bắt buộc. Viết test thiếu Context dự kiến NoSuchElementException và test có Context dự kiến trả kết quả. Quyết định HTTP boundary nên xử lý lỗi cấu hình đó ra sao.

**Bài 4.** Thêm một WebFilter khác có khả năng ghi đè cùng key. Dùng @Order và StepVerifier/HTTP test xác định ai thắng; sau đó thiết kế lại để chỉ một lớp có trách nhiệm tạo requestId.

**Bài 5.** Tạo một WebClient ExchangeFilterFunction đọc Reactor Context và set header X-Request-Id trong outbound HTTP request. Kiểm tra bằng mock HTTP server, rồi chứng minh rằng Context không tự truyền qua network nếu bạn không triển khai bước này.

**Bài 6.** Dùng hai requests WebFlux khác nhau, trong đó request A đã xác thực tenant A và B đã xác thực tenant B; chứng minh không rò identity giữa requests và không tin các headers tùy ý của client.

**Bài 7.** Tích hợp Micrometer Context Propagation để đưa correlation ID vào MDC khi thread hopping. Viết **hai loại assertion riêng**: ContextView có key; MDC tại đúng callback/thread có key. Làm sạch global hooks sau test.

## 15. Tài liệu tham khảo và ghi nhớ

- [Project Reactor 3.6 — Reference Guide](https://projectreactor.io/docs/core/3.6.7/reference/index.html) — Context của Subscriber, contextWrite và deferContextual.
- [Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) — operator placement và cách ghi/đọc.
- [Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — StepVerifier, StepVerifierOptions và context expectations.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — WebFlux tests và WebTestClient.
- [Spring Framework — WebFlux Web Handler API](https://docs.spring.io/spring-framework/reference/web/webflux-web-handler-api.html) — WebFilter và reactive request handling.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html) — security context trong reactive stack.

**Ghi nhớ:** Reactor Context truyền theo **subscription**, không phải theo thread. **contextWrite** đặt ở phía downstream của reader; **Mono.deferContextual** đọc ở subscription. Dùng **StepVerifier** với Context cụ thể, test cả key thiếu, operator placement, scheduler hop và hai subscriptions độc lập. Với WebFlux, đặt request metadata trong **WebFilter** và xác minh toàn bộ **HTTP → WebFilter → Controller → Service → response** bằng **WebTestClient**.