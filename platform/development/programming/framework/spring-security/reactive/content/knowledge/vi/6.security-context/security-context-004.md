# Thiết lập ngữ cảnh bằng contextWrite và withAuthentication

> **Chủ đề:** Ngữ cảnh bảo mật trong Spring Security reactive (Spring WebFlux, Reactor, Spring Boot 3.x, Spring Security 6.x, Java 17+). Bài tập trung vào cách **đưa một `Authentication` đã được xác thực đáng tin cậy vào Reactor Context cho một reactive pipeline cụ thể**, bằng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`, và cách đọc, thử nghiệm, giới hạn phạm vi của ngữ cảnh đó.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa `ThreadLocal`, `reactor.util.context.Context`, `SecurityContext` và `Authentication`.
2. Hiểu API `ReactiveSecurityContextHolder.withAuthentication(authentication)` trả về **Reactor `Context`** chứ không trả về `Mono<Authentication>`, và `contextWrite(...)` gắn context vào subscription như thế nào.
3. Viết một pipeline đọc principal bằng `ReactiveSecurityContextHolder.getContext()`; tự cấp context cho pipeline test hoặc tác vụ nội bộ đã xác thực.
4. Dự đoán đúng tác động của vị trí `contextWrite`, các nhánh `flatMap`, `publishOn`, và nhiều subscriptions độc lập.
5. Nhận diện giới hạn bảo mật: `withAuthentication` **không kiểm tra mật khẩu/JWT, không lưu phiên và không thay thế quá trình authentication của WebFlux**.

## 2. Vì sao Spring Security reactive cần Reactor Context?

Trong ứng dụng Servlet truyền thống, một request thường có luồng xử lý gắn với worker thread; mã quen thuộc có thể gọi `SecurityContextHolder.getContext().getAuthentication()`. Cách đó chủ yếu dựa vào cơ chế lưu context theo execution thread, thường là `ThreadLocal`.

Trong WebFlux, một pipeline `Mono`/`Flux` có thể:

- Chỉ được thực thi sau khi có subscriber;
- Chuyển giữa nhiều thread bởi `publishOn` / `subscribeOn`;
- Chạy các nhánh bất đồng bộ với `flatMap`;
- Dùng lại cùng publisher cho nhiều subscriptions độc lập;
- Không có quan hệ cố định “một request = một thread”.

Nếu dựa đơn thuần vào `ThreadLocal` của luồng hiện tại, danh tính có thể bị mất hoặc đọc sai khi luồng thay đổi. Spring Security reactive dùng `ReactiveSecurityContextHolder` để lấy `SecurityContext` từ **Reactor Context thuộc subscription**.

Các khái niệm liên quan:

| Khái niệm | Vai trò |
| --- | --- |
| `Authentication` | Đại diện principal, credential (nếu còn), authorities và trạng thái xác thực của một chủ thể |
| `SecurityContext` | Đối tượng chứa `Authentication` dùng trong việc ra quyết định bảo mật |
| `reactor.util.context.Context` | Kho khóa–giá trị bất biến về mặt API, gắn với subscription và được Reactor truyền qua chuỗi operator |
| `ReactiveSecurityContextHolder` | Adapter của Spring Security để lấy hoặc đặt `Mono<SecurityContext>` trong Reactor Context |
| `contextWrite(...)` | Reactor operator làm thay đổi context **được nhìn thấy ở phía upstream** của vị trí operator khi subscription diễn ra |
| `ReactiveSecurityContextHolder.getContext()` | Trả về `Mono<SecurityContext>` theo ngữ cảnh của subscriber; có thể empty khi không có context |

**Phân biệt hai lớp tên giống nhau:** `SecurityContext` là dữ liệu bảo mật của Spring Security. `Context` là container bất biến của Reactor. Spring Security lưu một publisher `Mono<SecurityContext>` dưới key nội bộ trong Reactor Context; không phải trực tiếp đặt username dưới key tùy ý như `"user"`.

### 2.1 Từ SecurityContext tới Authentication

Đọc danh tính từ reactive context bằng API chính thức:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public class CurrentUserService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous");
    }
}
```

Đây là một **class Java đầy đủ có thể đặt trong source** (chưa gắn `@Service` hay đăng ký bean), dùng Spring Security core và Reactor. Giá trị `"anonymous"` là fallback **khi không có giá trị phù hợp trong pipeline**, không phải bản thân Spring Security luôn đặt principal dưới tên đó. Trong HTTP WebFlux, anonymous authentication có thể tồn tại khi filter bảo mật hoạt động; vì thế việc gọi `getContext()` có trả context hay không còn phụ thuộc security chain.

`filter(Authentication::isAuthenticated)` chỉ là kiểm tra trạng thái của đối tượng đã có trong context, **không chứng minh credential đã được xác thực đúng**. Một đối tượng được tạo thủ công có thể tự khai báo trạng thái; luôn phân biệt dữ liệu demo với kết quả do authentication manager/trusted provider cấp.

## 3. API trọng tâm: withAuthentication(...) và contextWrite(...)

`ReactiveSecurityContextHolder` có bốn API quan trọng cho bài này:

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getContext()` | `Mono<SecurityContext>` | Đọc context bảo mật từ Reactor Context hiện hành |
| `withAuthentication(Authentication)` | `Context` | Tạo Reactor Context mang `Mono<SecurityContext>` chứa authentication được cung cấp |
| `withSecurityContext(Mono<? extends SecurityContext>)` | `Context` | Tự cung cấp publisher SecurityContext khi cần kiểm soát cách lấy context |
| `clearContext()` | `Function<Context, Context>` | Tạo phép biến đổi loại bỏ key SecurityContext trong phạm vi Reactor Context áp dụng |

Cú pháp điển hình:

```java
Mono<String> result = currentUsername()
    .map(name -> "Hello " + name)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
```

Đây là **đoạn trích trong một method có biến `authentication` hợp lệ và method `currentUsername()`**, không phải file chạy độc lập. `withAuthentication(authentication)` tạo một `Context` chứa `Mono<SecurityContext>`; `contextWrite(...)` là operator của Reactor gắn context ấy vào subscriber khi pipeline được subscribe. Khi `currentUsername()` nằm **upstream** của `contextWrite`, nó đọc được authentication vừa gắn.

**Không nhầm thứ tự được viết ra với thời điểm thực thi:**

```text
Khai báo publisher (assembly):
  currentUsername() -> map(...) -> contextWrite(withAuthentication(auth))
                                       ^ ở cuối chuỗi mã

Khi subscribe:
  Subscriber
      |
      v
  contextWrite tạo/ghép Reactor Context
      |
      v (ngữ cảnh được nhìn thấy ở upstream)
  map(...) -> currentUsername() đọc ReactiveSecurityContextHolder.getContext()

Luồng dữ liệu onNext sau đó đi từ source về subscriber.
```

Reactor Context gắn với **Subscriber**, không phải biến toàn cục, không tự lưu qua request khác và không phải thay đổi của mutable object trong thread. `Context` bất biến về mặt API: phép `put` hoặc phép ghép tạo context mới cho phạm vi operator tương ứng.

### 3.1 Cú pháp ngắn gọn và tương đương

Khi đã có một `Authentication` **đáng tin cậy**, hai cách sau có cùng mục tiêu:

```java
// Cách 1: dùng helper trực tiếp
Mono<String> viaAuthentication = currentUsername()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

// Cách 2: tự dựng SecurityContext để cung cấp qua Mono
SecurityContext securityContext = new SecurityContextImpl(auth);
Mono<String> viaSecurityContext = currentUsername()
    .contextWrite(
        ReactiveSecurityContextHolder.withSecurityContext(
            Mono.just(securityContext)
        )
    );
```

Các dòng trên là **đoạn code minh họa cần import** `Mono`, `SecurityContext`, `SecurityContextImpl` và có sẵn `auth` / `currentUsername()`. Trong thực tế, dùng `withAuthentication` khi chỉ cần truyền một Authentication; dùng `withSecurityContext` khi đã có publisher context, chẳng hạn từ thành phần xác thực hoặc repository được kiểm soát.

**Không làm cách này:**

```java
// Sai về ý nghĩa: "auth" là dữ liệu chưa xác thực do client tự khai báo
Authentication auth = /* tạo từ username/role nhận thẳng từ HTTP request */;
return protectedBusinessOperation()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

Mẫu này là **pseudocode cố ý không biên dịch** nhằm cảnh báo. `withAuthentication` không kiểm tra chữ ký token, password, quyền hay nguồn dữ liệu. Đặt một đối tượng có authority vào context là hành động **có quyền lực bảo mật**, chỉ thực hiện sau bước kiểm chứng đáng tin cậy và khi phạm vi đó được phép dùng danh tính tương ứng.

## 4. Bài thực hành runnable bằng JUnit 5 và StepVerifier

Để thấy rõ mà không cần mở web server hoặc giả lập HTTP login, tạo một dự án Spring Boot 3.x WebFlux/Java 17+ với các dependency sau trong `build.gradle` đã cấu hình Spring Boot plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` đem vào Spring Security, `spring-boot-starter-webflux` có Reactor core và API WebFlux, `reactor-test` có `StepVerifier`. Đoạn test dưới đây **không cần `@SpringBootTest` hoặc chạy HTTP server**: nó kiểm tra trực tiếp ngữ nghĩa `contextWrite` trong một reactive pipeline thuần.

Tạo file `src/test/java/com/example/reactivesecurity/ReactiveContextExamplesTest.java`:

```java
package com.example.reactivesecurity;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextExamplesTest {

    // Một Authentication đã đánh dấu authenticated chỉ để dựng dữ liệu TEST.
    // Production phải lấy từ authentication manager/IdP hợp lệ.
    private static Authentication auth(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username,
            "unused-test-credential",
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );
    }

    private static Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous");
    }

    @Test
    void readsAuthenticationFromContextWrite() {
        Mono<String> result = username()
            .map(name -> "Hello " + name)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(result)
            .expectNext("Hello alice")
            .verifyComplete();
    }

    @Test
    void noContextMeansNoSecurityContextValue() {
        StepVerifier.create(username())
            .expectNext("anonymous")
            .verifyComplete();
    }

    @Test
    void withSecurityContextCanBeUsedInstead() {
        SecurityContext securityContext = new SecurityContextImpl(auth("bob"));

        Mono<String> result = username()
            .contextWrite(
                ReactiveSecurityContextHolder.withSecurityContext(
                    Mono.just(securityContext)
                )
            );

        StepVerifier.create(result)
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void contextWriteMustBeDownstreamOfReader() {
        // Đặt contextWrite TRƯỚC flatMap chỉ cấp context cho Mono.just upstream.
        // username() ở flatMap downstream không thấy nó.
        Mono<String> misplaced = Mono.just("start")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            )
            .flatMap(ignored -> username());

        StepVerifier.create(misplaced)
            .expectNext("anonymous")
            .verifyComplete();

        // Đúng: contextWrite ở cuối, phía downstream của reader.
        Mono<String> corrected = Mono.just("start")
            .flatMap(ignored -> username())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(corrected)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void differentSubscribersCanHaveDifferentAuthentications() {
        Mono<String> asAlice = username()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        Mono<String> asBob = username()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("bob"))
            );

        StepVerifier.create(Mono.zip(asAlice, asBob))
            .assertNext(names -> {
                assertThat(names.getT1()).isEqualTo("alice");
                assertThat(names.getT2()).isEqualTo("bob");
            })
            .verifyComplete();
    }

    @Test
    void innerContextDoesNotEscalateToFollowingOuterStage() {
        Mono<String> flow = Mono.just("start")
            .flatMap(ignored ->
                username().contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(auth("worker"))
                )
            )
            .flatMap(innerName ->
                username().map(outerName -> innerName + "/" + outerName)
            );

        StepVerifier.create(flow)
            .expectNext("worker/anonymous")
            .verifyComplete();
    }

    @Test
    void contextSurvivesReactorSchedulerChange() {
        Mono<String> flow = Mono.just("trigger")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> username())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(flow)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void clearContextCanMaskAuthenticationForOneScope() {
        Mono<String> flow = username()
            .contextWrite(ReactiveSecurityContextHolder.clearContext())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(flow)
            .expectNext("anonymous")
            .verifyComplete();
    }

    @Test
    void aNewSubscriptionDoesNotInheritAnotherSubscriptionContext() {
        Mono<String> sharedSource = username();

        StepVerifier.create(sharedSource.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            ))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(sharedSource)
            .expectNext("anonymous")
            .verifyComplete();
    }
}
```

Chạy từ thư mục dự án:

```bash
./gradlew test --tests '*ReactiveContextExamplesTest'
```

Trên Windows PowerShell, dùng `.\gradlew.bat test --tests '*ReactiveContextExamplesTest'`. Đây là **test JUnit**, không phải ứng dụng Java SE có thể chạy bằng `javac` và `java` mà thiếu Spring Security, Reactor và JUnit dependencies.

Nếu test thành công, Gradle báo test task hoàn tất. Các chuỗi như `"Hello alice"`, `"worker/anonymous"` là **giá trị StepVerifier mong đợi** chứ không phải dữ liệu đã được in ra stdout. Nội dung ở đây nêu kỳ vọng từ mã; cần chạy lệnh trong project tương ứng để xác nhận ở phiên bản dependency thực tế.

### 4.1 Giải thích từng nhóm test

- `readsAuthenticationFromContextWrite`: ở phía upstream của `contextWrite`, `getContext()` nhìn thấy `SecurityContext` chứa `Authentication` tên `alice`.
- `noContextMeansNoSecurityContextValue`: test thuần Reactor không có WebFilter mặc định, nên `getContext()` không có security key → fallback `anonymous`.
- `withSecurityContextCanBeUsedInstead`: dùng helper mức thấp hơn để đưa vào `Mono<SecurityContext>`; kết quả đọc vẫn là `bob`.
- `contextWriteMustBeDownstreamOfReader`: chỗ đặt operator quyết định **reader upstream nào** nhận context; context không “chảy” tự do đến mọi operator sau đó.
- `differentSubscribersCanHaveDifferentAuthentications`: cùng API đọc principal nhưng hai nhánh subscribe độc lập mang hai context khác nhau.
- `innerContextDoesNotEscalateToFollowingOuterStage`: context thêm bên trong `flatMap` chỉ ảnh hưởng sub-publisher đã được áp dụng; không tự thay context ở các operator kế tiếp của outer chain.
- `contextSurvivesReactorSchedulerChange`: đổi scheduler **bên trong cùng Reactor chain** vẫn giữ Reactor Context đúng scope.
- `clearContextCanMaskAuthenticationForOneScope`: xóa key trong context của đoạn upstream; đây không phải logout HTTP hoặc thu hồi token.
- `aNewSubscriptionDoesNotInheritAnotherSubscriptionContext`: một publisher có thể được subscribe lại với context khác; lần subscribe mới không tự mang context của lần trước.

### 4.2 Minh họa riêng cho hướng contextWrite

So sánh hai pipeline:

```java
// Đúng: contextWrite nằm downstream so với vị trí getContext()
Mono<String> yes = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

// Sai về kỳ vọng: getContext() ở flatMap downstream của contextWrite
Mono<String> no = Mono.just("x")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
    .flatMap(x -> ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName()))
    .defaultIfEmpty("no-context");
```

Đây là **đoạn trích cần biến `auth` và import hợp lệ**. `yes` sẽ phát username khi `auth` đáng tin cậy và không null; `no` thường phát `"no-context"` nếu không có SecurityContext nào do subscriber bên ngoài cung cấp. Trong môi trường HTTP có security filter hoặc subscriber được bọc context khác, kết quả có thể khác; vị trí đúng luôn được xác định bằng **context thực tế và phạm vi subscriber**, không bằng mô hình “biến toàn cục”.

## 5. Vì sao contextWrite hoạt động từ dưới lên?

Reactor Context **không phải signal data** chạy xuôi qua mọi `map`/`flatMap`. Nó gắn với subscriber, được truyền trong quá trình subscription từ phía downstream đến các operator upstream. Do đó:

```text
Assembly order (trên xuống trong mã):

  Mono.deferContextual(read)
    .map(transform)
    .contextWrite(addContext)

Subscription starts:
  subscriber
    -> contextWrite(addContext) tạo Context mới
    -> upstream map(transform)
    -> upstream deferContextual(read) thấy Context mới

Data/onNext:
  read -> transform -> subscriber
```

`contextWrite(ContextView)` ghép các entry của `ContextView` với context downstream, tạo context nhìn thấy ở upstream. `contextWrite(Function<Context,Context>)` nhận context downstream và trả lại context cho phía upstream, ví dụ `ctx -> ctx.put("requestId", "r-001")`.

Một ví dụ Reactor Context tổng quát:

```java
Mono<String> trace = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("requestId", "missing")))
    .contextWrite(ctx -> ctx.put("requestId", "r-001"));
```

Đoạn này nên phát `"r-001"`. Nhưng **`ctx.put("requestId", "...")` không tạo Spring SecurityContext**; `ReactiveSecurityContextHolder.getContext()` tìm key/kiểu dữ liệu nội bộ của Spring Security. Dùng `withAuthentication` hoặc `withSecurityContext` thay vì đoán key hay đặt một field `"user"` rồi kỳ vọng Spring Security sử dụng.

Khi nhiều operator `contextWrite` thay đổi cùng một key, reader ở upstream sẽ thấy entry từ context gần nó nhất theo thứ tự áp dụng. Một `contextWrite` trong inner publisher thường chỉ cấp context cho **inner publisher đó**, không viết ngược thành “trạng thái của outer pipeline”.

## 6. Khi nào nên dùng withAuthentication thủ công?

### 6.1 Kiểm thử unit, service và reactive method security

Đây là tình huống rõ ràng nhất: bạn cần chạy một service reactive hoặc method có kiểm tra quyền **trong test** với một danh tính test xác định.

```java
Authentication testUser = UsernamePasswordAuthenticationToken.authenticated(
    "alice",
    "not-used",
    List.of(new SimpleGrantedAuthority("ROLE_READER"))
);

Mono<String> result = service.findCurrentUserData()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(testUser));

StepVerifier.create(result)
    .expectNext("expected-data-for-alice")
    .verifyComplete();
```

Đây là **đoạn minh họa trong test**: `service.findCurrentUserData()` và dữ liệu kỳ vọng phụ thuộc service thật. Với `@EnableReactiveMethodSecurity` / `@PreAuthorize`, SecurityContext cần xuất hiện trong Reactor Context lúc publisher được subscribe và phương thức cần dùng signature reactive được Spring Security hỗ trợ.

Đối với test HTTP WebFlux (controller, router, filter chain), ưu tiên các test helper của `spring-security-test` như `SecurityMockServerConfigurers.mockUser(...)`, `mockAuthentication(...)`, `mockJwt(...)` hoặc `@WithMockUser` theo loại bài test và runtime. Chúng thiết lập authentication ở lớp test phù hợp, giúp tránh bypass web filter ngoài ý muốn.

### 6.2 Tác vụ nội bộ sau bước authentication đáng tin cậy

Có khi một thành phần phản ứng cần chạy pipeline với `Authentication` do **`ReactiveAuthenticationManager` vừa xác thực**:

```java
public Mono<String> authenticateThenDoWork(
        ReactiveAuthenticationManager manager,
        Authentication presented,
        Mono<String> protectedWork) {

    return manager.authenticate(presented)
        .switchIfEmpty(Mono.error(
            new BadCredentialsException("Authentication did not succeed")))
        .flatMap(authenticated ->
            protectedWork.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authenticated)
            )
        );
}
```

Đây là **một method minh họa đặt trong class Java**; cần import `ReactiveAuthenticationManager` từ `org.springframework.security.authentication`, `BadCredentialsException` từ cùng package, `Authentication` và `Mono`. `presented` ở trạng thái trước xác thực chỉ được đưa vào `manager.authenticate`; **chỉ kết quả `authenticated` do manager chấp nhận** mới được đưa vào Reactor Context. Trong triển khai thực, chọn manager phù hợp với cơ chế credential và xử lý authentication error theo chính sách.

Nếu muốn tránh vô tình chia sẻ một publisher nóng giữa các chủ thể, có thể thay tham số `Mono<String> protectedWork` bằng `Supplier<Mono<String>> workFactory` và gọi `workFactory.get()` bên trong `flatMap`. Bản ngắn trên đúng về ngữ nghĩa contextWrite đối với publisher lạnh được tạo cho tác vụ.

**Giới hạn bảo mật:** Đừng nhận `Authentication` với authorities/roles từ body hoặc header tùy ý rồi gọi `withAuthentication`, dù flag `isAuthenticated()` là `true`. Cờ trạng thái là thuộc tính của đối tượng; bước kiểm chứng nguồn credential vẫn là trách nhiệm của authentication provider/manager. Chỉ cấp ngữ cảnh cho đúng tác vụ và đúng chủ thể; tránh “run as admin” nếu không có cơ chế ủy quyền/kiểm soát đã thiết kế.

### 6.3 Trong WebFlux HTTP request thông thường: framework làm việc này

Một request WebFlux có `SecurityWebFilterChain` và authentication phù hợp thường đã có security context được đưa vào reactive chain bởi thành phần của Spring Security (ví dụ `ReactorContextWebFilter` và các authentication filters). Business service **chỉ cần đọc**:

```java
public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Đây là một **method trong Spring service**, không cần tự gắn `withAuthentication` cho mỗi request. Thao tác tự tạo một Authentication “tin tưởng” ngay trong controller để khớp role là một cách **vượt bước xác thực**, không phải cách triển khai Spring Security đúng.

`contextWrite(withAuthentication(...))` đặc biệt hữu ích khi thử nghiệm hoặc cần cấp context cho **một phần reactive computation đã xác thực**. Nó không tự làm cho một HTTP request có credential hợp lệ, không thay thế authentication filter, không tự gửi credential sang downstream HTTP service và không tự lưu phiên cho request tiếp theo.

## 7. Ví dụ WebFlux đọc context mà Spring Security tạo từ HTTP Basic

Để phân biệt **context do framework cấp** với context gắn thủ công trong unit test, đây là một ứng dụng HTTP nhỏ dùng xác thực Basic (chỉ phục vụ học tập). Giữ nguyên `build.gradle` mục 4 và tạo các file dưới package `com.example.reactivesecurity`.

### 7.1 Application: ReactiveContextApplication.java

`src/main/java/com/example/reactivesecurity/ReactiveContextApplication.java`:

```java
package com.example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
```

### 7.2 SecurityConfig.java

`src/main/java/com/example/reactivesecurity/SecurityConfig.java`:

```java
package com.example.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(reader);
    }
}
```

Code demo tạo user `reader` cùng mật khẩu mã hóa từ giá trị minh họa. Không đưa tài khoản test cố định vào production, không dùng Basic auth trên HTTP không mã hóa ngoài môi trường local. Với POST/PUT/DELETE, Spring Security có thể yêu cầu CSRF token theo cấu hình; GET không cần CSRF token cho ví dụ này.

### 7.3 WhoAmIController.java

`src/main/java/com/example/reactivesecurity/WhoAmIController.java`:

```java
package com.example.reactivesecurity;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No authenticated principal")));
    }
}
```

Controller **không gọi `withAuthentication`**: `SecurityWebFilterChain` đã xử lý Basic credential, kiểm tra user và cung cấp Authentication hợp lệ cho request pipeline. `whoami()` chỉ đọc principal từ Reactor Context.

Chạy ứng dụng:

```bash
./gradlew bootRun
```

Ở terminal khác, trong môi trường **localhost chỉ phục vụ thử nghiệm**, gọi:

```bash
curl -i http://localhost:8080/whoami
curl -i -u reader http://localhost:8080/whoami
```

Lệnh thứ hai yêu cầu nhập password tương tác: `reader-demo-password`. Kỳ vọng lần đầu trả **401 Unauthorized** vì thiếu credential, lần thứ hai trả **200 OK** với body:

```text
reader
```

Response thực tế còn chứa HTTP headers do server/security cung cấp; khối trên chỉ mô tả **body kỳ vọng**. Nếu ứng dụng dùng profile/port khác, cần điều chỉnh URL. Lỗi 401 khi credential sai là hành vi xác thực; không nên “sửa” bằng cách tạo thủ công Authentication trong controller.

### 7.4 Test HTTP dùng Spring Security thay cho withAuthentication thủ công

Khi muốn kiểm tra **HTTP filter chain**, thêm `testImplementation 'org.springframework.security:spring-security-test'` và dùng `WebTestClient` / test security configurer theo bài toán, hoặc dùng header Basic như sau để kiểm tra filter thật:

`src/test/java/com/example/reactivesecurity/WhoAmIHttpTest.java`:

```java
package com.example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class WhoAmIHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousRequestIsUnauthorized() {
        client.get()
            .uri("/whoami")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedRequestReadsPrincipalFromReactorContext() {
        client.get()
            .uri("/whoami")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("reader");
    }
}
```

Test này cần chạy với Spring Boot WebFlux server thật và `SecurityConfig` được scan. Không yêu cầu `withAuthentication` trong Controller. Ngược lại, khi chỉ test một service/publisher, `StepVerifier` với `contextWrite(withAuthentication(testAuth))` giúp cô lập logic reactive mà không khởi chạy server. Đây là **hai lớp kiểm thử bổ sung** nhau.

## 8. Phạm vi, propagation, concurrency và lỗi khó thấy

### 8.1 Reactor Context được truyền qua Reactor operators, không phải mọi async API

Ví dụ này có thể vẫn đọc được user:

```java
Mono<String> onAnotherScheduler = Mono.just("start")
    .publishOn(Schedulers.parallel())
    .flatMap(ignored -> username())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(auth)
    );
```

Đoạn trên dùng `username()` và `auth` từ môi trường đã có. `publishOn` đổi scheduler nhưng chuỗi vẫn thuộc Reactor subscription; Reactor Context vẫn khả dụng. Kết luận “đổi thread là luôn mất context” **không đúng với Reactor operators được ghép đúng chuỗi**.

Ngược lại, nếu tách việc sang `new Thread(...)`, `CompletableFuture.supplyAsync(...)`, callback của SDK ngoại vi, hoặc gọi `subscribe()` thủ công tạo một subscription khác, không thể mặc nhiên giả định context sẽ truyền qua đó. Một số thư viện/cấu hình có cơ chế **context propagation bridge**, nhưng phải biết rõ đang dùng cơ chế nào và kiểm thử nó; không dựa vào một `ThreadLocal` tình cờ có giá trị.

Không gọi `block()` để lấy authentication trên WebFlux event-loop. Ngoài làm tắc thread, đó còn có thể tạo subscription mới với context không như bạn kỳ vọng. Thay vì:

```java
// Sai trong reactive request pipeline:
String name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block();
```

Hãy **giữ luồng reactive**:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .flatMap(this::loadDataForUser);
```

Hai khối là **method snippets**, không chạy độc lập; `loadDataForUser(String)` phải trả về `Mono<...>` phù hợp. Thông điệp chính là chuyển username vào downstream operator, không phá luồng bằng `block()`.

### 8.2 Mỗi subscription có context riêng, nhưng objects trong context cần an toàn

`Context` chỉ là cấu trúc dữ liệu bất biến về mặt thao tác `put`/`delete`. Nó **không tự biến mọi object bên trong thành immutable**. `SecurityContextImpl`/`Authentication` có trạng thái có thể thay đổi; tránh chia sẻ một mutable SecurityContext rồi gọi `setAuthentication(...)` giữa nhiều request hoặc nhiều người dùng.

Test tạo context riêng cho từng subscription là cách minh họa an toàn. Không đặt `Authentication` đang sử dụng vào `static`, singleton bean mutable, Reactor context global giả lập hoặc cache không phân tách chủ thể. Một `Mono` được tạo sẵn không tự đồng nghĩa mang Authentication của subscription gần nhất.

### 8.3 Vị trí trong flatMap quyết định phạm vi

Khi chạy:

```java
Mono<String> result = Mono.just("go")
    .flatMap(ignored ->
        username().contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(workerAuth)
        )
    )
    .flatMap(inner ->
        username().map(outer -> inner + "/" + outer)
    );
```

Khi outer subscriber không có authentication khác, kết quả dự đoán là `"worker/anonymous"`. Inner `username()` nhận `workerAuth`, còn `username()` trong `flatMap` phía sau không tự nhận context của inner publisher. Để toàn bộ vùng upstream của outer chain dùng cùng danh tính, đặt `contextWrite(withAuthentication(...))` **ở cuối outer chain** với phạm vi được cấp phép.

**Không “khắc phục” bằng cách gán Authentication vào biến static/thread-local**. Điều đó có thể tạo lỗi rò rỉ danh tính hoặc quyền giữa các request.

### 8.4 Hai subscription đồng thời không làm context thành dữ liệu toàn cục

Ví dụ hai nhánh:

```java
Mono<String> fromAlice = username()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(aliceAuth)
    );

Mono<String> fromBob = username()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bobAuth)
    );

Mono.zip(fromAlice, fromBob);
```

Chúng có thể chạy đồng thời nhưng mỗi nhánh được gắn context của chính publisher/subscription đó. `aliceAuth` không ghi đè `bobAuth` như khi dùng một biến toàn cục. Hãy chú ý không chia sẻ mutable state từ những đối tượng được đặt **bên trong** Context.

### 8.5 clearContext không phải logout

`ReactiveSecurityContextHolder.clearContext()` trả về một hàm biến đổi Reactor Context, dùng với:

```java
Mono<String> scoped = username()
    .contextWrite(ReactiveSecurityContextHolder.clearContext());
```

Nó **loại bỏ security key khỏi context upstream của publisher này**. Nó không tự xóa cookie, invalidates `WebSession`, thu hồi access token, xóa server-side OAuth2 authorized client, hoặc đảm bảo HTTP request kế tiếp không còn đăng nhập. Logout thực tế phải dùng cơ chế Spring Security logout/session/token tương ứng.

## 9. Ngữ cảnh đã thiết lập ảnh hưởng đến authorization thế nào?

Trong reactive method security, các interceptor như `@PreAuthorize` cần đọc authenticated principal/authorities từ ngữ cảnh reactive. Khi một service trả về publisher và được Spring Security proxy theo cách hỗ trợ, việc subscribe với context của user phù hợp cho phép policy đánh giá quyền.

Tuy nhiên, **đặt context không tự tạo authorization policy**. Ví dụ bạn cấp `Authentication` có `ROLE_READER`, nhưng nếu method/API không kiểm tra role hoặc quyền đối tượng, method vẫn có thể trả dữ liệu không nên truy cập. Cần cấu hình `@EnableReactiveMethodSecurity` và method annotations/rule logic đúng; với HTTP, cấu hình `SecurityWebFilterChain` và `authorizeExchange`.

Ngoài ra, `isAuthenticated()` / authority chỉ đại diện những thuộc tính **được bên xác thực cấp đáng tin cậy**. Không suy ra “đã đăng nhập” chỉ vì đối tượng trong test hoặc code nội bộ có cờ authenticated.

Khi gọi một HTTP downstream service bằng `WebClient`, Reactor Context của caller không tự trở thành header `Authorization` ở HTTP request mới. Cần OAuth2 Client/authorized client, token relay được cho phép, mTLS hoặc cơ chế định danh dịch vụ đúng. Không chuyển nguyên user token sang một dịch vụ khác nếu audience/scope không cho phép.

## 10. Bảng lỗi thường gặp và cách sửa

| Sai lầm | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Gọi `SecurityContextHolder.getContext()` theo Servlet trong reactive code | Tên user sai/mất khi chuyển scheduler | Dùng `ReactiveSecurityContextHolder.getContext()` trong Reactor chain |
| Đặt `contextWrite` trên source trước một reader downstream | Reader thấy empty hoặc context cũ | Đặt `contextWrite` downstream của những operator cần đọc |
| Đưa chuỗi `"alice"` vào `Context` rồi gọi `getContext()` | `getContext()` empty | Dùng `withAuthentication` / `withSecurityContext` |
| Tạo `Authentication` với role từ HTTP request chưa xác thực | Bypass authentication/privilege escalation | Dùng SecurityWebFilterChain, ReactiveAuthenticationManager, JWT verification, IdP đáng tin cậy |
| Gọi `block()` / tự `subscribe()` trong handler | Mất context hoặc chặn event-loop | Kết hợp `map` / `flatMap` và trả lại `Mono/Flux` |
| Kỳ vọng contextWrite inner `flatMap` sửa context của outer pipeline | Bước sau thấy principal khác/không có | Chọn scope `contextWrite` trên outer publisher khi cần |
| Kỳ vọng contextWrite sống qua request mới | User mới hoặc background job không có context | Cấp lại context trong subscription hợp lệ; với HTTP để Spring Security quản lý |
| Nhầm `clearContext()` với logout | Session/token vẫn hoạt động | Dùng logout/session invalidation/token revocation phù hợp |
| Có `withAuthentication` là đã đủ phân quyền | Method không được kiểm tra role/ownership | Bật/configure authorization, kiểm tra quyền tại resource/service |
| Gửi SecurityContext sang `WebClient` rồi mong downstream nhận user | Downstream trả 401/403 | Chủ động cấu hình credential/token relay được phép và xác minh audience/scope |
| Tự tạo context dùng chung chứa mutable Authentication | Rò rỉ dữ liệu giữa tasks/users | Giữ phạm vi subscription, dùng objects phù hợp và không mutate shared context |
| Test service với contextWrite rồi suy ra HTTP endpoint an toàn | Unit test qua nhưng HTTP auth sai | Test riêng SecurityWebFilterChain bằng WebTestClient |

## 11. Bài tự kiểm tra và câu trả lời

**Câu 1.** Vì sao `contextWrite(withAuthentication(auth))` thường đặt ở **cuối** pipeline dùng để đọc principal?

Vì subscriber khởi đầu từ downstream và Reactor Context được nhìn thấy bởi **upstream** operators. Đặt ở cuối giúp các operator upstream như `ReactiveSecurityContextHolder.getContext()` có thể đọc `SecurityContext` được cấp.

**Câu 2.** `withAuthentication(new UsernamePasswordAuthenticationToken(...))` có tự xác thực password không?

Không. Helper chỉ **gói một Authentication được cung cấp** vào context. Cần dùng đúng authentication manager/provider để xác thực. Chỉ sử dụng authentication tạo thủ công trong test hoặc trường hợp nội bộ đã được kiểm chứng và ủy quyền chặt chẽ.

**Câu 3.** Dùng `publishOn(Schedulers.parallel())` rồi đọc username, context có mất không?

Thông thường **không** nếu vẫn trong cùng chuỗi Reactor được subscribe đúng cách và contextWrite bao phủ reader. `Context` được truyền theo subscriber, không dựa vào việc giữ nguyên thread.

**Câu 4.** Nếu trong một `flatMap` nội bộ dùng `withAuthentication(workerAuth)`, bước `flatMap` phía sau trong outer chain có tự thấy workerAuth không?

Không. Context mới chỉ cấp cho phần sub-publisher đã gọi `contextWrite`, không tự viết ngược vào context của outer sequence.

**Câu 5.** `ReactiveSecurityContextHolder.getContext()` trả về `SecurityContext` trực tiếp hay một `Mono<SecurityContext>`?

Trả về **`Mono<SecurityContext>`**. Cần xử lý reactive bằng `map` / `flatMap`; publisher có thể empty nếu không có security key trong Reactor Context.

**Câu 6.** Có thể dùng `clearContext()` để đăng xuất người dùng WebFlux không?

Không. Nó chỉ xóa context key trong phạm vi publisher đã cấp phép; logout phải xử lý session/cookie/token theo mô hình xác thực.

**Câu 7.** Nếu test `StepVerifier` của service dùng withAuthentication thành công, đã chứng minh Spring Security HTTP filter bảo vệ endpoint chưa?

Chưa. Test publisher chứng minh propagation và logic trong phạm vi test. Cần test HTTP thật để chứng minh request authentication, authorization, CSRF/route policy.

**Câu 8.** Thao tác `ctx.put("username", "alice")` có đủ để `ReactiveSecurityContextHolder.getContext()` thấy Alice không?

Không. `ReactiveSecurityContextHolder` dùng cấu trúc/key nội bộ chứa `Mono<SecurityContext>`, không tự hiểu các key tùy ý.

## 12. Checklist triển khai

- [ ] Đã có `Authentication` **được xác thực bởi thành phần đáng tin cậy** trước khi cấp context bằng `withAuthentication`.
- [ ] Publisher cần đọc Authentication nằm **upstream** của vị trí `contextWrite` áp dụng.
- [ ] `ReactiveSecurityContextHolder.getContext()` được xử lý bằng `Mono`, có xử lý tình huống không có context nếu bài toán cho phép.
- [ ] Phạm vi `flatMap`, inner publisher, subscribe lần mới, parallel branch và scheduler được hiểu/được kiểm thử.
- [ ] Không gọi `block()` trong WebFlux event-loop, không tách subscriptions ngoài ý muốn, không dùng mutable global Authentication.
- [ ] Không coi `withAuthentication` là bước kiểm chứng credential, cấp quyền, lưu session hay logout.
- [ ] Trong HTTP request thông thường, để Spring Security WebFlux tạo/khôi phục context và tự xử lý filter chain.
- [ ] Test unit bằng `StepVerifier`, test HTTP bằng `WebTestClient` khi cần chứng minh bảo mật endpoint.
- [ ] Nếu có method security, đã cấu hình và thử nghiệm quyền trên publisher thực tế.
- [ ] Với WebClient gọi downstream, xử lý credential/ủy quyền riêng theo cơ chế bảo mật hợp lệ.

**Ghi nhớ cốt lõi:** `ReactiveSecurityContextHolder.withAuthentication(auth)` tạo **Reactor Context mang Spring SecurityContext**; `contextWrite(...)` cấp context ấy cho **các operator upstream trong subscription được áp dụng**. Đây là kỹ thuật kiểm soát **sự hiện diện của SecurityContext trong reactive pipeline**, không phải phương thức thay thế xác thực và phân quyền của ứng dụng.

### Tài liệu chính thức

- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Reactor Core — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Reactor Core — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
