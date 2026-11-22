# ReactiveSecurityContextHolder và Reactor Context

Hãy hình dung một ứng dụng Spring WebFlux xử lý hàng nghìn request đồng thời. Mai gọi `GET /me`, An gọi `GET /me` gần như cùng lúc. Cả hai request có thể được xử lý trên **một nhóm nhỏ các event-loop thread**, và một request có thể chuyển sang thread khác khi pipeline dùng `publishOn` hoặc được nối với một lời gọi bất đồng bộ. Dù vậy, ứng dụng vẫn phải biết **đúng người gọi của từng chuỗi xử lý** để không trả hồ sơ Mai cho An.

Trong lập trình Servlet đồng bộ, chúng ta thường gặp `SecurityContextHolder.getContext()`: Spring Security mặc định gắn `SecurityContext` với thread hiện tại. Trong lập trình **reactive**, không thể dùng giả định “một thread tương ứng với một request” làm cơ sở bảo mật. Spring Security cung cấp **`ReactiveSecurityContextHolder`**, được xây dựng trên **Reactor Context** để định danh đi cùng ngữ cảnh của **subscriber/subscription**, thay vì phụ thuộc cố định vào một Java thread.

Bài này giải thích: Reactor Context là gì, `ReactiveSecurityContextHolder` lấy và đưa `SecurityContext` vào luồng `Mono`/`Flux` ra sao, `contextWrite` hoạt động theo chiều nào, WebFlux Security tự gắn context thế nào, việc lưu session dùng repository gì, vì sao các tác vụ ngoài Reactor có thể mất context, và cách viết code/test Java 17+ có thể chạy.

**Phạm vi:** Spring Security **WebFlux/reactive stack**, với Project Reactor. Không nhầm `ReactiveSecurityContextHolder` với `SecurityContextHolder` cho Servlet, và không dùng `SecurityContextRepository` của `jakarta.servlet` để xử lý WebFlux. Các ví dụ phân biệt rõ mã runnable và fragment trong ứng dụng.

## 1. Tách bốn đối tượng trước khi đọc Reactor Context

| Đối tượng | Nhiệm vụ chính | Điểm cần nhớ |
| --- | --- | --- |
| `Authentication` | Đại diện chủ thể đã hoặc đang được xác thực, cùng authorities | Có thể là username/password, JWT, OAuth2/OIDC hoặc custom principal |
| `SecurityContext` | Chứa `Authentication` đang được áp dụng | Có thể chứa `Authentication` đã xác thực hoặc chưa có người dùng |
| `SecurityContextHolder` | Truy cập context theo chiến lược **imperative**, mặc định ThreadLocal trong Servlet | Không dùng như nguồn sự thật mặc định trong Reactor pipeline |
| `ReactiveSecurityContextHolder` | Đọc/đưa `Mono<SecurityContext>` vào **Reactor Context** | Sử dụng `getContext()`, `withAuthentication(...)`, `withSecurityContext(...)` và `clearContext()` |

Giả sử controller WebFlux viết:

~~~java
// Mảnh code đặt trong reactive service/controller.
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

Giá trị trả về là **`Mono<String>`**, không phải username lấy đồng bộ tại thời điểm gọi phương thức. Khi subscriber đăng ký pipeline, `ReactiveSecurityContextHolder` mới truy xuất ngữ cảnh của subscription tương ứng.

Nếu không có `SecurityContext` trong Reactor Context, `getContext()` thường hoàn thành **rỗng** (`Mono.empty()`), không tự tạo một tài khoản đáng tin hoặc trả username “anonymous”. Muốn xử lý thiếu context, hãy dùng `switchIfEmpty`/`defaultIfEmpty` một cách có chủ đích.

~~~java
// Mảnh code trong ứng dụng reactive.
Mono<String> nameOrGuest() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(java.util.Objects::nonNull)
        .map(Authentication::getName)
        .defaultIfEmpty("guest");
}
~~~

Chuỗi `guest` chỉ là **giá trị hiển thị fallback**, không được coi là một `Authentication` hợp lệ hay quyền truy cập dữ liệu.

## 2. Tại sao ThreadLocal không đủ trong WebFlux?

Một cách dùng phổ biến ở Servlet:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Cách này phù hợp trong những flow imperative đã có context được gắn cho thread bởi Security filters. Nhưng với Reactor:

~~~text
HTTP request của Mai
    |
    v
event-loop-thread-1
    | map(), flatMap()
    v
publishOn(parallel scheduler)
    |
    v
worker-thread-3
    | gọi service khác
    v
HTTP response của Mai

HTTP request của An
    |
    v
event-loop-thread-1 (có thể là thread vừa xử lý Mai)
    |
    v
HTTP response của An
~~~

**Thread có thể được dùng lại cho nhiều request, và một subscription có thể đổi thread.** Nếu code cố lấy user bằng `SecurityContextHolder` ở bất kỳ điểm nào của pipeline, dữ liệu có thể là `null`, không được thiết lập, hoặc khác với giả định của lập trình viên. Nguy hiểm hơn, nếu tự đặt `ThreadLocal` mà không dọn đúng, có nguy cơ lẫn danh tính giữa tác vụ.

Không phải `publishOn` luôn làm mất security context. **Reactor Context được thiết kế để đi theo subscription qua các operator Reactor**, kể cả khi lịch chạy thay đổi. Thứ thường bị mất là **giả định dựa trên thread** hoặc context bị bỏ khi code tách khỏi publisher đã quản lý.

### Hai trục khác nhau

~~~text
ThreadLocal:
  "Tôi đang chạy trên Thread số mấy?"
  -> Dữ liệu liên kết với chính Thread đó.

Reactor Context:
  "Tôi đang là một Subscriber trong subscription nào?"
  -> Dữ liệu liên kết với chuỗi reactive và đi qua ContextView.
~~~

Reactor Context **không phải** bộ nhớ toàn cục của ứng dụng và không phải nơi lưu account lâu dài. Nó giống **ngăn metadata gắn với subscription**, dùng cho những thông tin xuyên suốt chuỗi xử lý như security context, trace/correlation ID hoặc locale nếu được quản lý đúng.

## 3. Reactor Context là gì?

Reactor `Context` là một cấu trúc dữ liệu dạng key-value **immutable** theo API: khi thêm/xóa key, bạn nhận một context mới thay vì sửa trực tiếp đối tượng cũ. `ContextView` cung cấp giao diện **chỉ đọc** để truy vấn các key đã có.

Ví dụ độc lập về Reactor (fragment cần `reactor-core`):

~~~java
Mono<String> pipeline =
    Mono.deferContextual(view ->
        Mono.just("trace=" + view.getOrDefault("traceId", "none"))
    )
    .contextWrite(ctx -> ctx.put("traceId", "req-101"));
~~~

Khi được subscribe, pipeline có thể phát:

~~~text
trace=req-101
~~~

Ở đây:

- `Mono.deferContextual(view -> ...)` đọc `ContextView` của subscription **khi có subscriber**, không phải khi assembly code được gọi.
- `contextWrite(...)` tạo context dành cho các operator ở **phía upstream** trong đoạn chain mà nó được áp dụng.
- Key `traceId` chỉ là ví dụ application metadata, không thay thế `SecurityContext`.
- Hai subscription có thể mang hai giá trị `traceId` khác nhau dù dùng cùng một `Mono` object.

### Context đi từ subscriber lên upstream

Một sơ đồ dễ nhớ:

~~~text
          UPSTREAM                        DOWNSTREAM
       +--------------+              +-----------------+
       | deferContextual| -> map() -> | contextWrite(...) | -> subscribe()
       +--------------+              +-----------------+
                  ^                              |
                  +----- Context từ subscriber --+
~~~

**Tín hiệu dữ liệu** (`onNext`, `onComplete`, `onError`) thường đi từ upstream về downstream. **Reactor Context** được truyền khi subscribe theo hướng **từ downstream về upstream**. Vì vậy:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("color", "none"))
    )
    .contextWrite(ctx -> ctx.put("color", "blue"));
~~~

`deferContextual` có thể đọc `blue`. Nhưng nếu `contextWrite` nằm **upstream** của một `flatMap` xuất hiện ở downstream, các publisher được tạo bên trong `flatMap` downstream không mặc định chịu tác động của context viết chỉ cho upstream trước đó.

**Lưu ý về scope:** `contextWrite` không phải lệnh thay đổi một biến global. Nó áp dụng cho đoạn publisher nhất định trong subscription. Muốn một nhánh nghiệp vụ có security context, đặt `contextWrite` ở **ranh giới phía downstream** bao phủ chính nhánh cần chạy. Không copy một `Context` của người dùng vào singleton dùng chung.

### Context immutable nhưng giá trị đặt vào có thể mutable

`Context` không cho sửa key/value ngay trong object cũ, nhưng value như `SecurityContext` hoặc `Authentication` có thể là một object Java có mutable fields. **Không tạo một `SecurityContext` toàn cục rồi chia sẻ cho nhiều người dùng** chỉ vì Reactor Context là immutable. Bảo vệ ownership từng subscription vẫn là trách nhiệm của ứng dụng.

## 4. API chính của ReactiveSecurityContextHolder

Class:

~~~java
org.springframework.security.core.context.ReactiveSecurityContextHolder
~~~

Bốn phương thức quan trọng theo Spring Security hiện đại:

~~~java
// API mô tả chữ ký thực tế, bỏ imports để tập trung vào ý nghĩa.
static Mono<SecurityContext> getContext();

static reactor.util.context.Context withAuthentication(
        Authentication authentication);

static reactor.util.context.Context withSecurityContext(
        Mono<? extends SecurityContext> securityContext);

static java.util.function.Function<
    reactor.util.context.Context,
    reactor.util.context.Context> clearContext();
~~~

### 4.1. getContext(): đọc theo subscription, không đọc ThreadLocal

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
~~~

`getContext()` trả `Mono<SecurityContext>`, nên bạn có thể phối hợp với `flatMap`, `switchIfEmpty`, `filter`, `zipWhen` hoặc policy reactive. Không cần `block()` để lấy tên trong một WebFlux controller: cứ trả `Mono<String>` và để framework subscribe đúng chỗ.

`Mono` có thể hoàn thành rỗng: **không nên tự ném `NullPointerException`** vì code giả định context luôn tồn tại. Nếu endpoint yêu cầu login, phần authorization của Spring Security nên chặn anonymous **trước** khi controller được gọi. Nếu là endpoint công khai, xử lý trường hợp không có context theo policy.

### 4.2. withAuthentication(authentication): thiết lập context cho một chain

~~~java
Authentication identity = UsernamePasswordAuthenticationToken.authenticated(
    "mai", null,
    java.util.List.of(new SimpleGrantedAuthority("ROLE_USER"))
);

Mono<String> who = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> answer = who.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(identity)
);
~~~

Ở đây `identity` là object đã được đánh dấu authenticated để **minh họa/test**, không phải kết quả hợp lệ được tạo từ dữ liệu người dùng tự khai. Trong ứng dụng thật, `Authentication` phải do cơ chế **đã xác minh password/token/SSO** tạo ra. `withAuthentication` chỉ **đặt danh tính có sẵn vào ngữ cảnh**, nó không xác minh credentials.

Phương thức này trả một `reactor.util.context.Context` để hợp nhất qua `contextWrite(...)`. **Nó không làm việc như `SecurityContextHolder.setContext` ghi một biến global**, và cũng không tự lưu session ở HTTP response.

### 4.3. withSecurityContext(Mono<SecurityContext>): truyền context qua publisher

Một cách dùng khác:

~~~java
SecurityContext securityContext = new SecurityContextImpl();
securityContext.setAuthentication(identity);

Mono<String> answer = who.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(
        Mono.just(securityContext)
    )
);
~~~

Khác với `withAuthentication`, cách này cho phép cung cấp **một `Mono<SecurityContext>`**. Nó có ích trong các trường hợp context được tải từ nguồn reactive hoặc được tạo bởi một bước xử lý không đồng bộ đã được xác minh. Không dùng `Mono.just` với context `null`; Reactor không hỗ trợ phát `null` như tín hiệu dữ liệu hợp lệ.

Không nên tự tạo một `Mono<SecurityContext>` từ header username hoặc claim chưa được kiểm chứng rồi đưa vào `withSecurityContext`: đó là **đánh dấu một danh tính không có bằng chứng là đáng tin**.

### 4.4. clearContext(): bỏ key security khỏi context của một đoạn pipeline

~~~java
Mono<String> anonymousView =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous")
        .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

`clearContext()` trả **hàm biến đổi Reactor Context**, có thể truyền cho `contextWrite`. Nó làm mất key của `ReactiveSecurityContextHolder` đối với **đoạn upstream đang được áp dụng**; không xóa session ở server, không revoke JWT và không logout tất cả thiết bị.

**Quan trọng về thứ tự:** với `chain.contextWrite(clearContext()).contextWrite(withAuthentication(mai))`, context ở phía upstream của `clearContext` không còn identity, dù downstream đặt Mai. Vì các `contextWrite` cùng tham gia quá trình subscribe từ phía downstream, vị trí đặt quyết định scope.

## 5. Ví dụ chạy độc lập Java 17+: hai người dùng, hai subscription, một lần đổi thread

Trước khi tích hợp WebFlux HTTP, hãy quan sát Reactor Context qua một chương trình **không cần web server**. Điều này làm tách biệt chính xác phần lõi: Spring Security Core cung cấp `ReactiveSecurityContextHolder`, Project Reactor cung cấp `Mono`, `contextWrite` và scheduler.

### 5.1. Tạo project Gradle

~~~text
reactive-context-core-demo/
  build.gradle
  src/main/java/ReactiveContextDemo.java
  src/test/java/ReactiveContextDemoTest.java
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    // BOM chỉ để quản lý phiên bản tương thích; đây không phải ứng dụng Boot.
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.security:spring-security-core'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'ReactiveContextDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dự án dùng **BOM của Spring Boot** để có bộ phiên bản dependency thống nhất; không cần plugin Spring Boot vì chỉ chạy `public static void main` bằng Gradle application plugin. Yêu cầu JDK 17+, Gradle hỗ trợ Java 17 và kết nối Maven Central khi tải dependency lần đầu.

### 5.2. Java đầy đủ, biên dịch/chạy được

Tạo `src/main/java/ReactiveContextDemo.java`:

~~~java
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ReactiveContextDemo {

    private static Authentication user(String name) {
        // Chỉ dành cho DEMO: trong production phải xác minh bằng chứng
        // trước khi tự tạo một Authentication đã authenticated.
        return UsernamePasswordAuthenticationToken.authenticated(
            name, null, List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous");
    }

    public static void main(String[] args) {
        Authentication mai = user("mai");
        Authentication an = user("an");

        // Cùng một publisher; ba subscriptions nhìn thấy
        // ba ngữ cảnh độc lập, theo contextWrite của mỗi subscription.
        Mono<String> lookup = currentName();

        System.out.println("without=" + lookup.block());

        System.out.println("with-mai=" + lookup
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(mai))
            .block());

        System.out.println("with-an=" + lookup
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(an))
            .block());

        System.out.println("cleared=" + lookup
            .contextWrite(ReactiveSecurityContextHolder.clearContext())
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(mai))
            .block());

        // Việc đọc context xảy ra SAU publishOn ở flatMap.
        Mono<String> switched = Mono.just("start")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName))
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(mai));

        System.out.println("after-thread-switch=" + switched.block());

        SecurityContext saved = new SecurityContextImpl();
        saved.setAuthentication(an);
        System.out.println("with-security-context=" + lookup
            .contextWrite(ReactiveSecurityContextHolder
                .withSecurityContext(Mono.just(saved)))
            .block());
    }
}
~~~

Từ thư mục project:

~~~bash
java -version
gradle --version
gradle run --quiet
~~~

Đầu ra dự kiến do chính các `println` tạo ra:

~~~text
without=anonymous
with-mai=mai
with-an=an
cleared=anonymous
after-thread-switch=mai
with-security-context=an
~~~

Đầu ra là **kết quả theo logic các API trong ví dụ**, không dựa vào tên thread, tốc độ scheduler hoặc thời điểm hệ thống. Chương trình dùng `block()` chỉ vì **đây là lệnh CLI đang ở ranh giới `main`**; bên trong WebFlux request handler không nên `block()` như vậy.

Giải thích từng dòng:

1. `without=anonymous`: subscription không chứa key security; `getContext()` không phát `SecurityContext`, nên `defaultIfEmpty` hoạt động.
2. `with-mai=mai`: subscription đầu có `Authentication` của Mai do `withAuthentication` cung cấp.
3. `with-an=an`: dùng **cùng publisher `lookup`** nhưng subscription khác mang An. Không có biến ThreadLocal global nào bị “đổi người dùng”.
4. `cleared=anonymous`: trong scope upstream, `clearContext` được áp dụng sau khi `withAuthentication(mai)` ở downstream đưa dữ liệu vào.
5. `after-thread-switch=mai`: đoạn `flatMap` chạy sau `publishOn` vẫn đọc được Reactor Context phù hợp; một bước đổi scheduler trong Reactor không đồng nghĩa mất context.
6. `with-security-context=an`: `withSecurityContext(Mono.just(saved))` cung cấp context đã chứa `Authentication` của An.

**Ranh giới bảo mật:** hàm `user(name)` trong ví dụ chủ động tạo token `authenticated` từ literal để dạy Reactor Context. Nó **không phải hàm login**; không được nhận username do client gửi rồi dùng logic này để đánh dấu authenticated trong production.

### 5.3. Test subscriptions và không có context

Tạo `src/test/java/ReactiveContextDemoTest.java`:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextDemoTest {

    private static Authentication identity(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name, null, List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @Test
    void samePublisherCanSeeSeparateIdentities() {
        Mono<String> lookup = currentName();

        StepVerifier.create(lookup.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(identity("mai"))))
            .expectNext("mai")
            .verifyComplete();

        StepVerifier.create(lookup.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(identity("an"))))
            .expectNext("an")
            .verifyComplete();
    }

    @Test
    void noContextProducesEmptyPublisher() {
        StepVerifier.create(currentName())
            .verifyComplete();
    }

    @Test
    void clearContextRemovesUpstreamSecurityIdentity() {
        StepVerifier.create(currentName()
                .contextWrite(ReactiveSecurityContextHolder.clearContext())
                .contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(identity("mai"))))
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Kết quả mong đợi: **3 tests pass** nếu JDK/Gradle/dependencies được thiết lập đúng. Test `noContextProducesEmptyPublisher` khẳng định absence có thể biểu diễn bằng publisher không có phần tử. Test `samePublisherCanSeeSeparateIdentities` chứng minh **không có rò danh tính từ một subscription sang subscription khác** khi context được cấp riêng.

Cả ba test dùng `Authentication` được tạo để **mô phỏng identity đáng tin trong unit test**, không chứng minh provider đã xác thực password. Với hệ thống production cần test cả authentication manager, WebFlux security filter chain và authorization.

## 6. Spring WebFlux tự gắn Reactive SecurityContext thế nào?

Trong ứng dụng WebFlux có Spring Security, không cần viết `contextWrite(withAuthentication(...))` ở từng controller. Security web filters được cấu hình để **tải hoặc tạo Authentication đã xác minh và đưa nó vào Reactor Context** theo request.

Sơ đồ:

~~~text
HTTP request / WebFlux ServerWebExchange
                |
                v
           SecurityWebFilterChain
                |
                +--> context repository nếu có
                |       ReactorContextWebFilter
                |       -> cung cấp SecurityContext cho Reactor Context
                |
                +--> AuthenticationWebFilter hoặc filter theo cơ chế
                |       -> ReactiveAuthenticationManager kiểm tra credentials
                |       -> tạo Authentication đáng tin
                |
                +--> AuthorizationWebFilter
                |       -> truy cập Authentication trong reactive context
                |
                v
          Router/Controller/Service
                |
                +--> ReactiveSecurityContextHolder.getContext()
                |
                v
          Mono/Flux response và subscriber
~~~

Đây là sơ đồ **khái niệm**, không mô tả chính xác thứ tự/filter class của mọi cơ chế JWT, Basic, OAuth2 và mọi phiên bản. Quan trọng là web security và reactive method security cùng sử dụng **Reactor Context phù hợp**.

Hai lớp rất đáng nhớ:

- `ReactorContextWebFilter` sử dụng `ServerSecurityContextRepository` để tạo nguồn `SecurityContext` cho `ReactiveSecurityContextHolder`.
- `AuthenticationWebFilter` được dùng trong nhiều luồng reactive authentication; tùy cấu hình, nó chuyển request sang `Authentication`, gọi `ReactiveAuthenticationManager`, rồi xử lý success/failure và context.

Các cơ chế đặc thù như JWT Resource Server có thể sử dụng những thành phần và chính sách lưu khác. Đừng mặc định mọi login dùng một shared web session hoặc bất kỳ `Authentication` nào cũng được tạo bởi `AuthenticationWebFilter` duy nhất.

### Khác Servlet ở những class nào?

| Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityContextHolder` (thread strategy) | `ReactiveSecurityContextHolder` (Reactor Context) |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `SecurityContextRepository` | `ServerSecurityContextRepository` |
| `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` |
| `NullSecurityContextRepository` | `NoOpServerSecurityContextRepository` |
| `jakarta.servlet.http.HttpServletRequest` | `ServerWebExchange` |

Tên giống nhau nhưng **không hoán đổi interface**. `SecurityContextRepository` của Servlet có `saveContext(..., HttpServletRequest, HttpServletResponse)` và `loadDeferredContext(HttpServletRequest)`; phía WebFlux có `ServerSecurityContextRepository.save(exchange, context): Mono<Void>` và `load(exchange): Mono<SecurityContext>`.

## 7. WebFlux repository lưu phiên khác với Reactor Context hiện tại

Đây là sự phân biệt rất quan trọng:

- **Reactor Context:** gắn identity với **subscription** trong quá trình xử lý request hoặc operation.
- **`ServerSecurityContextRepository`:** quyết định identity đã xác thực có thể được **lưu/tải giữa các request** hay không, tùy implementation.
- **`WebSession`:** một nguồn lưu server-side có thể liên kết nhiều HTTP requests thông qua session cookie.
- **Bearer token:** có thể được xác minh **trên từng request** mà không cần session persistence.

Interface reactive:

~~~java
// Chữ ký tóm tắt từ API WebFlux, không phải class độc lập.
Mono<SecurityContext> load(ServerWebExchange exchange);

Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
~~~

Đây là API của `org.springframework.security.web.server.context.ServerSecurityContextRepository`; không dùng `jakarta.servlet`.

Một số implementations:

| Class | Hành vi | Khi nào hữu ích |
| --- | --- | --- |
| `WebSessionServerSecurityContextRepository` | Lưu/đọc SecurityContext trong WebFlux `WebSession` | Flow login có session và cookie |
| `NoOpServerSecurityContextRepository` | Không lưu context qua requests | API stateless thường xác thực bearer mỗi request |
| Custom repository | Nạp/lưu context qua nguồn do ứng dụng kiểm soát | Trường hợp đặc thù, cần kiểm thử bảo mật và lifecycle |

Đối với những filter đã được Spring Security cung cấp, cấu hình authentication thành công sẽ quyết định context được đưa vào Reactor Context và repository nào được sử dụng. Nếu tự viết một flow, cần xem **cả hai**: context của request hiện tại và cách persist khi muốn request tương lai tiếp tục login.

**Đừng suy luận:** vì `getContext()` trả Authentication trong request A nên request B chắc chắn vẫn authenticated. Reactor Context không phải cơ chế persistence xuyên HTTP requests.

### Lỗi thường gặp khi tự gọi reactive save

Một fragment sai:

~~~java
// SAI: Mono<Void> là publisher lazy; không được subscribe nên có thể
// không có thao tác lưu nào xảy ra.
serverSecurityContextRepository.save(exchange, context);
return Mono.just("ok");
~~~

Cách đúng là **compose** công việc lưu vào pipeline được trả về:

~~~java
// Fragment bên trong reactive authentication flow đã xác minh identity.
return serverSecurityContextRepository.save(exchange, context)
    .thenReturn("ok");
~~~

Đây không phải implementation login production đầy đủ: bạn còn cần CSRF, cookie/session strategy, credential handling, logout, failure handling, policy và xác minh account. Nhưng nó cho thấy nguyên tắc quan trọng của reactive: **một Mono chưa được subscribe/compose sẽ không tự thực hiện side effect**.

Không dùng `.subscribe()` thủ công bên trong controller chỉ để kích hoạt save; thao tác tách khỏi pipeline có thể mất context, bỏ qua lỗi và tạo race với response. Hãy trả `Mono` đã `then`/ `flatMap` kết hợp và để WebFlux subscribe.

## 8. Ví dụ WebFlux chạy được: API đọc identity trong Reactor Context

Ví dụ ứng dụng HTTP hoàn chỉnh dưới đây dùng **Spring Boot 4.1.2**, WebFlux, Spring Security reactive và HTTP Basic để có thể gọi bằng `curl`. Mục tiêu là chứng minh:

- `GET /public` cho phép anonymous.
- `GET /me` cần xác thực; controller đọc username qua `ReactiveSecurityContextHolder.getContext()`.
- User `mai` có `ROLE_USER` và không thể truy cập `/admin`.
- User `admin` có `ROLE_ADMIN` và được phép truy cập `/admin`.
- Dữ liệu identity nằm trong reactive context do filter chain chuẩn tạo ra, không tự dùng `ThreadLocal`.

**HTTP Basic trong bài chỉ để minh họa local**; production cần HTTPS, throttling, credential lifecycle, logs được redact và thiết kế xác thực phù hợp.

### 8.1. Cấu trúc

~~~text
webflux-security-context-lab/
  pom.xml
  src/main/java/com/example/reactive/
    ReactiveSecurityApplication.java
    SecurityConfiguration.java
    IdentityController.java
~~~

### 8.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-security-context-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chỉ sử dụng `spring-boot-starter-webflux`, **không** thêm `spring-boot-starter-webmvc`: khi cùng chứa MVC và WebFlux, Spring Boot có thể ưu tiên mô hình Servlet thay vì WebFlux nếu không chỉ định rõ application type. Giữ đúng một reactive web stack giúp tránh sự pha trộn `SecurityContextHolder` và `ReactiveSecurityContextHolder` ngoài ý muốn.

### 8.3. Main class

Tạo `src/main/java/com/example/reactive/ReactiveSecurityApplication.java`:

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

### 8.4. SecurityWebFilterChain + ReactiveUserDetailsService

Tạo `src/main/java/com/example/reactive/SecurityConfiguration.java`:

~~~java
package com.example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails mai = User.withUsername("mai")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(mai, admin);
    }

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

`MapReactiveUserDetailsService` là một implementation **reactive** của `ReactiveUserDetailsService`. Nó giữ dữ liệu trong memory chỉ để demo, không đại diện kho người dùng production. `BCryptPasswordEncoder` được sử dụng để kiểm tra password hash, không lưu plaintext trong `UserDetails`.

`SecurityWebFilterChain` và `ServerHttpSecurity` là các kiểu reactive, khác với `SecurityFilterChain`/`HttpSecurity` của Servlet. `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`. Không cần tự tạo `Authentication` từ chuỗi do client gửi, vì filter/provider chuẩn xử lý xác thực.

### 8.5. Controller đọc security context của subscription

Tạo `src/main/java/com/example/reactive/IdentityController.java`:

~~~java
package com.example.reactive;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "hello-" + name);
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-area");
    }
}
~~~

`me()` không gọi `block()`, `subscribe()` hoặc `SecurityContextHolder.getContext()`. Nó trả một `Mono<String>`, để **framework subscribe theo request hiện tại**. Khi Basic credentials hợp lệ, filter security đặt context vào reactive chain nên `getContext()` có Authentication đã xác minh.

Nếu bạn muốn một endpoint công khai hiển thị tên khách, phải thiết kế fallback rõ ràng; ví dụ `defaultIfEmpty("guest")`. Nhưng trong `/me`, rule `anyExchange().authenticated()` đã yêu cầu caller được xác thực nên code không cần cấp quyền cho anonymous.

### 8.6. Chạy bằng Maven và thử HTTP

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Trên terminal khác:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/admin
curl -i -u admin:demo-password http://localhost:8080/admin
~~~

Kết quả theo chính sách demo:

| Request | Status kỳ vọng | Body khi thành công |
| --- | --- | --- |
| Anonymous `GET /public` | `200` | `public` |
| Anonymous `GET /me` | `401` theo Basic entry point | Thông báo/challenge tùy cấu hình |
| Mai `GET /me` | `200` | `hello-mai` |
| Mai `GET /admin` | `403` | Không được xem nội dung admin |
| Admin `GET /admin` | `200` | `admin-area` |

Đây là **kết quả được dự đoán từ SecurityWebFilterChain và code**; mã chưa được thực thi trong bài hướng dẫn. Nếu app có nhiều chain, thêm form login, reverse proxy hoặc entry point riêng, response status/body có thể khác.

Mật khẩu demo xuất hiện trong `curl` vì đây là môi trường local. **Không đưa credentials thật vào command line hoặc shell history**, không dùng HTTP không có TLS trên Internet. Trong production cần HTTPS và cấu hình logging để không ghi `Authorization` header.

## 9. @EnableReactiveMethodSecurity và quyền trong service

WebFlux authorization không chỉ dành cho URL. Với Spring Security reactive, bạn có thể bật **method security**:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Cần import `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`; đây là **fragment**, không phải project thứ ba hoàn chỉnh. Những method được bảo vệ thường cần trả về `Publisher` như `Mono` hoặc `Flux` để enforcement tích hợp đúng Reactor Context. Tùy phiên bản/cấu hình, Kotlin coroutine có hỗ trợ riêng.

Ví dụ service:

~~~java
// Fragment bên trong @Service bean được Spring proxy.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminSummary() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> "admin-summary-for-" + auth.getName());
}
~~~

Để `@PreAuthorize` có tác dụng, phải bật method security và **gọi qua Spring proxy** (không tự `new` service hoặc self-invoke một method bị chặn rồi mong AOP luôn áp dụng). Dù phương thức có role `ADMIN`, vẫn cần kiểm tra **quyền với bản ghi/tenant cụ thể** nếu xử lý dữ liệu nhạy cảm.

Spring Security reactive method authorization dựa vào Reactor Context, nên tự tạo một `ThreadLocal` `SecurityContextHolder` ở controller không thay thế việc có identity đúng trong subscriber.

### Khi nào nên dùng Authentication parameter thay vì ReactiveSecurityContextHolder?

Trong WebFlux, Spring có thể resolve một `Principal` hoặc `Mono<Principal>` cho handler phù hợp. Nhưng ở **tầng service**, không nên phụ thuộc trực tiếp vào WebFlux `ServerWebExchange` chỉ để tìm người gọi; `ReactiveSecurityContextHolder.getContext()` là điểm tích hợp reactive thuận tiện.

Với business logic lớn, có thể tạo `CurrentActorResolver` trả `Mono<CurrentActor>`, lấy `accountId` đã xác minh rồi truy vấn account hiện tại. Điều này giúp tách security principal khỏi domain account và dễ kiểm thử.

## 10. Khi có Flux dài hoặc streaming, context tồn tại theo subscription

Một WebFlux endpoint có thể trả `Flux<Event>` kéo dài lâu (Server-Sent Events) hoặc service subscribe nhiều nguồn dữ liệu. Reactor Context gắn với **subscription**, không biến mất đơn giản vì thread bị thay đổi. Tuy nhiên có những điểm thiết kế cần lưu ý:

- Một `Flux` có thể được **subscribe nhiều lần**. Mỗi lần subscribe cần context được cấp đúng.
- Nếu publisher được **share/hot** giữa nhiều người dùng, dữ liệu phát từ nguồn dùng chung phải được lọc/phân quyền theo **subscription/request của từng người**, không biến một `SecurityContext` của subscriber đầu thành biến toàn cục.
- Với stream dài, role hoặc trạng thái tài khoản có thể đổi trong lúc stream đang chạy. Cần cân nhắc **độ trễ thu hồi quyền** và cách đóng stream khi account bị khóa.
- Không `cache()` kết quả chứa dữ liệu người dùng A vào singleton rồi tái dùng cho B nếu cache key/policy không an toàn.
- Một operator `publishOn` trong Reactor không mặc định làm mất context, nhưng việc **thoát khỏi pipeline** sang callback của thư viện không tích hợp Reactor có thể làm mất scope.

Ví dụ cảnh báo:

~~~java
// SAI: tự subscribe trong controller, tách khỏi quản lý request.
public Mono<String> handler() {
    service.findData()
        .subscribe(value -> sendSomewhere(value)); // detached side effect
    return Mono.just("accepted");
}
~~~

Hàm `sendSomewhere` chưa được định nghĩa, nên đây chỉ là **fragment cảnh báo**. Vấn đề là lỗi, cancellation, backpressure và context của luồng phụ không còn được biểu diễn trong publisher mà WebFlux quản lý.

Nên **compose**:

~~~java
// Fragment: service và sender trả về Mono phù hợp.
public Mono<String> handler() {
    return service.findData()
        .flatMap(value -> sender.send(value).thenReturn("accepted"));
}
~~~

Khi các thành phần vẫn nằm trong một pipeline reactive đúng, context, lỗi và cancellation có cơ hội được quản lý nhất quán hơn. Không mặc định bất kỳ phương thức trả `Mono` nào cũng bảo mật đúng: vẫn cần kiểm tra quyền trước khi đọc hoặc phát dữ liệu.

## 11. Các ranh giới thường làm mất context

### 11.1. CompletableFuture và raw Executor

Một task `CompletableFuture.supplyAsync(...)` hoặc `ExecutorService.submit(...)` **không tự nhận Reactor Context** chỉ vì được gọi bên trong `flatMap`. Nếu code ở thread đó gọi `SecurityContextHolder.getContext()`, nó có thể thấy rỗng; cũng không thể mặc nhiên gọi `ReactiveSecurityContextHolder.getContext()` nếu task không được subscribe trong một Reactor chain có context.

Nếu cần chuyển metadata qua ranh giới này, hãy truyền một **CurrentActor/subject ID đã được xác minh** như tham số có chủ đích hoặc dùng cơ chế context propagation phù hợp của Reactor/Micrometer/Spring Security phiên bản đang dùng. Không truyền raw password, bearer token hoặc toàn bộ `Authentication` đến job lâu dài trừ khi có kiến trúc bảo mật riêng.

### 11.2. ThreadLocal MDC và logging

MDC của logging thường dựa trên ThreadLocal. `contextWrite(ctx -> ctx.put("traceId", ...))` không tự đảm bảo MDC sẽ giữ đúng giá trị trên mọi scheduler nếu không có bridge được cấu hình. Tương tự, việc bật một integration truyền tracing context **không tự có nghĩa security context cũng được truyền theo cách bạn kỳ vọng**.

**Không đưa password, access token hoặc toàn bộ JWT claims vào MDC/trace** để “debug ngữ cảnh”. Chỉ ghi thông tin tối thiểu, đã được phép như correlation ID và account ID đã xử lý theo chính sách.

### 11.3. block() trên event loop

Trong ví dụ CLI, `block()` dùng để đợi kết quả và in stdout. Trong WebFlux, gọi `block()` hoặc `blockOptional()` trong request handler có thể chặn event loop và thậm chí ném exception trên non-blocking thread tùy scheduler. Đừng xử lý bằng cách chuyển mọi code sang `boundedElastic` một cách mù quáng.

Nếu phụ thuộc thư viện blocking (JDBC, file I/O cũ), cô lập phần blocking với scheduler phù hợp và kiểm tra concurrency/latency; còn service reactive nên trả `Mono`/`Flux` để pipeline tiếp tục quản lý context.

### 11.4. Dùng Reactor Context như một nơi lưu phiên vĩnh viễn

Không. Sau HTTP request, subscription kết thúc. Request kế tiếp cần authentication mới hoặc repository/session/token để nạp lại danh tính. `ReactiveSecurityContextHolder.withAuthentication(mai)` không phát session cookie và không thực hiện JWT revocation.

### 11.5. Tự tạo Authentication đã authenticated từ input client

Ví dụ nguy hiểm:

~~~java
// SAI: username từ query param/chưa xác minh mà đã đánh dấu tin cậy.
Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest,
    null,
    java.util.List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
return securedAction.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(auth)
);
~~~

Đây là **privilege escalation trực tiếp** nếu áp dụng vào request thực. `withAuthentication` chỉ đặt object vào Reactor Context; nó không xác minh password, chữ ký JWT hay quyền của account. Trong production, identity phải đến từ filter/provider/manager đã xác thực và chính sách gán quyền từ nguồn đáng tin.

## 12. So sánh thay đổi context: set global, withAuthentication và clearContext

| Hành động | Servlet imperative | Reactor reactive |
| --- | --- | --- |
| Đọc identity | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Đặt identity cho phần xử lý | `SecurityContextHolder.setContext(ctx)` | `publisher.contextWrite(withAuthentication(auth))` |
| Xóa local association | `SecurityContextHolder.clearContext()` | `publisher.contextWrite(clearContext())` với scope phù hợp |
| Lưu qua request | `SecurityContextRepository` với servlet request/response | `ServerSecurityContextRepository` với `ServerWebExchange` |
| Nguồn dữ liệu người dùng mật khẩu | `UserDetailsService` | `ReactiveUserDetailsService` |
| Filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |

**Điểm không tương đương hoàn toàn:** `ReactiveSecurityContextHolder.clearContext()` chỉ trả một hàm sửa context cho nhánh reactive. Nó không giống thao tác ngay lập tức trên ThreadLocal hiện tại. Chỉ khi `contextWrite` nằm đúng chỗ, upstream subscribe mới nhìn thấy context bị loại bỏ.

### Context cũ và context mới lồng nhau

Giả sử một outer request có identity Mai. Trong một unit test, ta muốn thực thi một nhánh thử nghiệm dưới identity An:

~~~java
Mono<String> check = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> asAn = check.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(testAn)
);
~~~

Đây là **mảnh code test**, `testAn` là `Authentication` tạo từ fixture tin cậy, không phải user input. Kết quả của `asAn` được đọc dưới An **ở phần upstream cụ thể**, nhưng không biến mọi pipeline của cả request thành An. Việc ghi đè context trong code production có thể gây lỗi **confused deputy**: một module thực hiện hành động dưới quyền khác với danh tính thực của người gọi.

Tốt hơn hết, không override security context để “giải quyết lỗi không tìm thấy user”. Hãy sửa cách kết nối publisher với security chain hoặc truyền một actor được kiểm soát trong tác vụ thực sự được ủy quyền.

## 13. Xác thực và phân quyền: context đúng chưa đủ

Một context có `Authentication.isAuthenticated()==true` không có nghĩa user được xem bất kỳ bản ghi nào. Hai lớp:

~~~text
Authentication:
   Có token/password được xác minh?
   Danh tính thuộc tài khoản nào?
   Đã qua MFA/chính sách yêu cầu chưa?
             |
             v
Reactor Context chứa Authentication đã xác minh
             |
             v
Authorization:
   Có quyền với action?
   Có thuộc tenant?
   Tài nguyên có thuộc chủ thể/chia sẻ hợp lệ?
   Account còn enabled, token/session chưa bị thu hồi?
             |
             v
Chỉ thực hiện thao tác được phép
~~~

Với multi-tenant, một user có `ROLE_ADMIN` ở công ty A không tự được phép đọc dữ liệu công ty B. `ReactiveSecurityContextHolder.getContext()` giúp biết **chủ thể hiện tại**; service/authorization manager vẫn phải tra membership, owner, tenant và policy đúng cho tài nguyên.

Một service fragment:

~~~java
// Fragment trong reactive service, repository/policy là thành phần ứng dụng.
public Mono<DocumentView> findDocument(String documentId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> documentRepository.findById(documentId)
            .flatMap(document ->
                authorizationPolicy.canRead(auth, document)
                    .filter(Boolean::booleanValue)
                    .switchIfEmpty(Mono.error(
                        new AccessDeniedException("Forbidden")))
                    .thenReturn(mapper.toView(document))
            )
        );
}
~~~

Đây là **mảnh kiến trúc**, không phải class độc lập; cần định nghĩa `DocumentView`, `authorizationPolicy`, mapper, repository và null/error policy. Hãy đảm bảo không phát `DocumentView` trước khi policy trả cho phép; nếu dữ liệu nhạy cảm, query nên được giới hạn ngay từ DB theo tenant/owner.

Không tự cấp quyền nếu `getContext()` hoàn thành rỗng. Trong API yêu cầu xác thực, security chain phải từ chối; trong service cần xử lý thiếu context đúng policy (thường là deny, không phải lấy “người dùng mặc định”).

## 14. Kiểm thử đúng reactive context

Có ba tầng quan trọng:

### Tầng A — Unit test Reactor Context

Sử dụng `StepVerifier` và `contextWrite(withAuthentication(...))` để assert publisher đọc đúng principal, phân biệt subscriptions và không rò dữ liệu. Demo phần 5 có ba test hoàn chỉnh.

### Tầng B — WebFlux filter chain

Dùng `WebTestClient` hoặc integration test HTTP để xác nhận:

- Anonymous vào `/me` bị từ chối.
- User hợp lệ đọc `/me` thấy đúng username.
- User Mai truy cập `/admin` bị chặn dù Basic credentials chính xác.
- Admin truy cập `/admin` thành công.
- Hai request đồng thời dùng credentials khác nhau không thấy danh tính lẫn nhau.

Không dùng test chỉ có `@WithMockUser` để chứng minh password đã được xác minh: annotation test tạo sẵn security context, có thể bỏ qua `ReactiveAuthenticationManager` hoặc `ReactiveUserDetailsService`.

### Tầng C — Ranh giới ngoài Reactor và repository

Kiểm tra hành vi sau `publishOn`, `subscribeOn`, `flatMap`, WebClient, callback của thư viện ngoài, executor, lưu session và token-based requests. Test phải mô phỏng đúng vị trí context được đặt và nơi code đọc nó.

Một ma trận:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Publisher không có security context | `getContext()` empty; service xử lý theo policy |
| `withAuthentication(mai)` trên một subscription | Đọc được Mai ở upstream phù hợp |
| Một publisher được subscribe với Mai rồi An | Mỗi subscription thấy đúng danh tính |
| `clearContext()` áp đúng scope | Upstream không còn security context |
| `publishOn` trong cùng Reactor chain | Context phù hợp vẫn đi tới code đọc ở nhánh tiếp |
| Tự mở `CompletableFuture`/executor | Không tự giả định có Reactor Context bên trong |
| `block()` ở `main` CLI | Có thể dùng để chờ kết quả |
| `block()` trong WebFlux event loop | Không nên; có thể chặn hoặc lỗi |
| WebFlux HTTP Basic hợp lệ | `ReactiveSecurityContextHolder` thấy Authentication đã xác minh |
| Sai password hoặc token không hợp lệ | Không tạo context có quyền đáng tin |
| Role USER gọi endpoint ADMIN | Bị từ chối theo authorization |
| Session WebFlux đã bị invalidate | Không khôi phục quyền từ session cũ |
| Token JWT hết hạn | Không được chấp nhận bởi decoder/validator |
| Role bị thu hồi sau khi token/session được cấp | Policy phải xác định độ trễ cập nhật và cơ chế revocation |
| Hot Flux được chia sẻ | Không lộ data A cho B do cache/source dùng chung |
| Exception giữa pipeline | Không được đánh dấu success hoặc vô tình trả dữ liệu đã phát trước khi authorization |

Một điểm có giá trị trong test: **đừng assert thread name** để chứng minh identity đúng. Thread scheduling là chi tiết thực thi; điều cần assert là Authentication/username/authorities ở từng subscription.

## 15. Những sai lầm phổ biến

1. **“ReactiveSecurityContextHolder cũng là ThreadLocal.”** Không. Nó đọc context gắn với Reactor subscription.
2. **“WebFlux vẫn một request một thread như Servlet.”** Không thể dùng giả định đó; pipeline có thể chia sẻ/đổi thread.
3. **“Đọc `SecurityContextHolder.getContext()` trong `flatMap` chắc chắn đúng user.”** Không mặc định; dùng reactive API.
4. **“`ReactiveSecurityContextHolder.getContext()` trả thẳng `SecurityContext`.”** Nó trả `Mono<SecurityContext>`.
5. **“Không có context sẽ tự có `ROLE_USER` hoặc authenticated=true.”** Không; absence phải xử lý an toàn.
6. **“`contextWrite` sửa một map toàn cục.”** Không; context theo subscription, áp dụng theo scope.
7. **“`contextWrite` truyền dữ liệu theo chiều `onNext`.”** Không; context được propagate từ subscriber lên upstream.
8. **“Đặt `contextWrite` ở đâu cũng có tác dụng trên mọi operator.”** Không; vị trí trong chain quan trọng.
9. **“`withAuthentication(username)` sẽ tự kiểm tra mật khẩu.”** Nó nhận `Authentication` đã có; không xác minh credentials.
10. **“Có Authentication trong Reactor Context là có HTTP session.”** Không; đây là hai vòng đời khác nhau.
11. **“`ServerSecurityContextRepository` là cùng interface với `SecurityContextRepository` Servlet.”** Không; khác phương thức và stack.
12. **“`NoOpServerSecurityContextRepository` tự xác minh JWT.”** Không; cần filter/decoder.
13. **“Gọi `save(exchange, context)` mà không subscribe là đủ.”** Không; phải compose publisher.
14. **“Tự `.subscribe()` trong controller giúp chạy nhanh hơn.”** Dễ mất error/cancellation/context và tạo tác vụ tách khỏi request.
15. **“`publishOn` luôn làm mất Reactor Context.”** Không; Reactor operators truyền context đúng cách trong cùng subscription.
16. **“`CompletableFuture.supplyAsync` mặc định nhận mọi key Reactor Context.”** Không; cần bridge hoặc truyền dữ liệu có kiểm soát.
17. **“`block()` trong WebFlux là cách dễ nhất lấy username.”** Tránh; trả Mono/Flux.
18. **“Reactor Context immutable nên có thể chia sẻ một SecurityContext mutable cho mọi user.”** Không; value có thể mutable và chứa identity riêng.
19. **“`clearContext()` tương đương logout ở mọi thiết bị.”** Không; chỉ xóa key trong scope của publisher.
20. **“Có ROLE_ADMIN nghĩa được xem mọi tenant.”** Không; cần object/tenant-level authorization.
21. **“`@EnableReactiveMethodSecurity` bảo vệ mọi method không có Publisher tùy ý.”** Hợp đồng method security reactive cần sử dụng kiểu trả về/đường gọi tương thích và Spring proxy.
22. **“HTTP Basic request A đã đăng nhập thì request B không cần credentials.”** Không mặc định; Basic thường xác thực theo header ở mỗi request.
23. **“Gắn token do client khai vào withSecurityContext là hợp lệ.”** Không; token phải qua xác minh chữ ký/issuer/audience/expiry.
24. **“Một publisher cache data A và trả cho B miễn là có security context.”** Không; cache có thể rò dữ liệu nếu key/scope sai.
25. **“Test @WithMockUser chứng minh provider thật hoạt động.”** Không; test giả lập danh tính, không chứng minh xác thực password/token.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `ReactiveSecurityContextHolder.getContext()` trả kiểu gì?

*Trả lời:* `Mono<SecurityContext>` được lấy từ Reactor Context theo subscription.

**Câu 2.** Vì sao `SecurityContextHolder.getContext()` không phải cách mặc định đáng tin trong WebFlux reactive pipeline?

*Trả lời:* `SecurityContextHolder` mặc định gắn context với thread, trong khi reactive subscription có thể chuyển/chia sẻ thread. Reactor Context gắn theo subscriber thích hợp hơn.

**Câu 3.** `withAuthentication(auth)` có xác minh password không?

*Trả lời:* Không. Nó chỉ tạo context chứa `Authentication` đã có, để `contextWrite` cung cấp vào một chain. Authentication phải đến từ nguồn được xác minh.

**Câu 4.** `contextWrite` ảnh hưởng operator upstream hay downstream?

*Trả lời:* Nó cung cấp context cho **upstream** khi subscription được tạo từ downstream.

**Câu 5.** Tại sao cùng một `Mono<String>` có thể trả username Mai rồi An ở hai lần subscribe?

*Trả lời:* Vì mỗi subscription được cấp một Reactor Context riêng; `withAuthentication` được áp theo chain/subscription chứ không sửa global user.

**Câu 6.** `publishOn(Schedulers.parallel())` có tự xóa Reactor Context không?

*Trả lời:* Không trong một Reactor chain hoạt động đúng; context được truyền qua các operator. Nhưng chuyển sang raw executor/callback tách khỏi pipeline lại là ranh giới khác.

**Câu 7.** `clearContext()` có revoke access token ở client không?

*Trả lời:* Không. Nó là hàm xóa key security khỏi scope của Reactor Context; JWT/token lifetime và revocation cần cơ chế riêng.

**Câu 8.** WebFlux dùng repository nào thay cho `HttpSessionSecurityContextRepository` của Servlet?

*Trả lời:* `WebSessionServerSecurityContextRepository` là implementation lưu context vào `WebSession` của WebFlux; giao diện là `ServerSecurityContextRepository`.

**Câu 9.** Nếu gọi `repository.save(exchange,context)` rồi bỏ `Mono<Void>`, context đã được lưu chưa?

*Trả lời:* Không thể coi là đã lưu; Mono thường lazy và cần được compose/subscribed bởi flow phù hợp.

**Câu 10.** Vì sao một WebFlux controller nên trả `Mono<String>` thay vì gọi `getContext().block()`?

*Trả lời:* Trả publisher giúp framework quản lý subscriber context, non-blocking execution, lỗi và cancellation. Block trong event loop có thể gây trì hoãn hoặc exception.

**Câu 11.** Context có `ROLE_ADMIN` tại request hiện tại có chứng minh admin được đọc dữ liệu mọi tenant không?

*Trả lời:* Không; cần quyền theo tenant, owner/resource, trạng thái và các policy khác.

**Câu 12.** Khi làm unit test bằng `withAuthentication`, có cần dùng một password thật không?

*Trả lời:* Không. Tạo Authentication fixture trong test để kiểm tra propagation; muốn test xác thực thật phải đi qua filter/provider/manager.

## 17. Checklist triển khai WebFlux production

- [ ] Ứng dụng thực sự sử dụng Spring WebFlux và `SecurityWebFilterChain`, không vô tình trộn servlet security config.
- [ ] Code trong `Mono`/`Flux` dùng `ReactiveSecurityContextHolder.getContext()` nếu cần principal/authorities hiện tại.
- [ ] Không dựa vào `SecurityContextHolder` ThreadLocal hoặc `Thread.currentThread()` để xác định user.
- [ ] Hiểu rằng Reactor Context đi từ subscriber lên upstream; đặt `contextWrite` đúng scope, không làm auth override ngoài ý muốn.
- [ ] Authentication đến từ filter/provider/manager đã xác minh, không tự tin vào username/role trong request.
- [ ] Tránh `block()` hoặc `subscribe()` nội bộ trong WebFlux handler/service.
- [ ] Không giữ singleton/global `SecurityContext` mutable có thể dùng chung giữa nhiều người dùng.
- [ ] Ranh giới `CompletableFuture`, executor, callback, WebClient, queue và long-lived Flux có chính sách truyền identity rõ.
- [ ] Nếu dùng WebSession, chọn `ServerSecurityContextRepository`, timeout, cookie, logout và session fixation phù hợp.
- [ ] Nếu dùng bearer token stateless, mỗi request được verify token; không nhầm Reactor Context với nơi lưu access token bền vững.
- [ ] Các phép `Mono<Void>` save/side effect được compose đúng vào returned publisher; không fire-and-forget.
- [ ] Method security reactive bật đúng và các secured methods được gọi qua Spring proxy.
- [ ] Authorization kiểm tra role/permission cùng owner/tenant/resource-level policy.
- [ ] Quyền bị thu hồi/tài khoản bị khóa có SLA và chiến lược invalidation/re-evaluation phù hợp.
- [ ] Logs/metrics/tracing không chứa raw password, OTP, bearer tokens hoặc toàn bộ security context.
- [ ] Test cùng publisher với nhiều context khác nhau, context vắng mặt, `clearContext`, `publishOn` và HTTP thật.
- [ ] Test các endpoint `/public`, `/me`, `/admin` qua security filter chain, không chỉ `@WithMockUser`.
- [ ] Không cache/hot-share dữ liệu riêng của một user cho các subscribers khác nếu không có kiểm soát quyền.
- [ ] Có theo dõi lỗi mất context nhưng không in thông tin nhạy cảm để debug.
- [ ] Cập nhật Spring Security, Reactor, Spring Boot và test dependencies theo BOM/patch phù hợp.

### Tổng kết

**`SecurityContextHolder` chủ yếu giải quyết ngữ cảnh theo thread ở imperative/Servlet; `ReactiveSecurityContextHolder` giải quyết ngữ cảnh theo subscription ở Spring WebFlux/Reactor.** `getContext()` trả `Mono<SecurityContext>`, còn `withAuthentication`, `withSecurityContext` và `clearContext` được dùng cùng `contextWrite` để quản lý scope ngữ cảnh.

Ở WebFlux, security filters thường cấp Reactor Context cho từng request, còn `ServerSecurityContextRepository` quyết định có lưu context qua request khác hay không. Việc giữ đúng danh tính sau `publishOn` không cho phép bỏ kiểm tra password/JWT, owner/tenant authorization hoặc lifecycle session/token.

Một nguyên tắc thiết kế đáng nhớ: **đừng hỏi “thread này thuộc về ai?”; hãy hỏi “subscription/request đã được xác minh này đang mang security context nào, và subject đó có quyền gì với tài nguyên đang xử lý?”**

### Tài liệu tham khảo chính thức

- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html)
- [Spring Security — ReactorContextWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html)
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html)
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
