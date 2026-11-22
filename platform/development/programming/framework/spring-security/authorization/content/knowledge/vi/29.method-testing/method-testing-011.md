# Kiểm thử method security Reactive và Reactor Context

> Bài thực hành Spring Security cho **phân quyền ở tầng phương thức** của ứng dụng reactive. Công cụ: Java 17+, Spring Security 6.5/7.x, Spring Test/JUnit Jupiter, Reactor `Mono`/`Flux` và `StepVerifier`. Trọng tâm là **cách Authentication được lấy từ Reactor Context**; ví dụ kiểm thử trực tiếp Spring service, chưa cần mở HTTP server.

## 1. Mục tiêu và những điểm khác với kiểm thử đồng bộ

Một phương thức có thể được bảo vệ bằng:

~~~java
@PreAuthorize("hasAuthority('report:read')")
public Mono<String> viewReport() { /* ... */ }
~~~

Bộ kiểm thử có giá trị phải chứng minh:

1. **Không có người dùng đăng nhập:** publisher báo lỗi truy cập.
2. **Có người dùng nhưng sai quyền:** publisher vẫn báo lỗi.
3. **Có đúng authority:** publisher trả về đúng dữ liệu rồi hoàn tất.
4. **Context không bị mất khi đổi scheduler:** service vẫn đọc đúng username qua `ReactiveSecurityContextHolder`.
5. **Mỗi subscriber có Context riêng:** dùng lại cùng publisher không làm lẫn danh tính giữa hai subscription.

Với `Mono`/`Flux`, lỗi bảo mật thường phát ra như tín hiệu **`onError` khi subscribe**, nên phải kiểm tra bằng `StepVerifier`; gọi hàm rồi chỉ `assertDoesNotThrow(...)` gần như không chứng minh được quyền truy cập. Khác với một API HTTP, test phương thức kiểm tra `AccessDeniedException`, không kiểm tra status `401`/`403`.

## 2. Cơ chế Reactor Context và reactive method security

Trong ứng dụng Servlet đồng bộ, `SecurityContextHolder` thường gắn context vào `ThreadLocal`. Ứng dụng WebFlux/Reactor có thể chuyển thread do `publishOn` hoặc `subscribeOn`, vì vậy reactive method security sử dụng **Reactor Context**, gắn với *subscription*, không gắn cố định với thread.

Các thành phần cần hiểu:

- `ReactiveSecurityContextHolder.getContext()` trả về `Mono<SecurityContext>` lấy từ Reactor Context hiện hành.
- `ReactiveSecurityContextHolder.withAuthentication(auth)` tạo `reactor.util.context.Context` mang `Authentication` để gắn vào publisher bằng `contextWrite(...)`.
- `@EnableReactiveMethodSecurity` bật các interceptor bảo vệ `@PreAuthorize`/`@PostAuthorize` trên Spring bean.
- `@WithMockUser` tạo test authentication; `WithSecurityContextTestExecutionListener` và `ReactorContextTestExecutionListener` hỗ trợ đưa thông tin đó vào reactive test.
- `StepVerifier.create(publisher)` thực sự **subscribe** và quan sát `onNext`, `onError`, `onComplete`.

~~~text
Test  ->  publisher.contextWrite(withAuthentication(auth))
                      |
                      | subscribe: Context đi ngược lên upstream
                      v
          @PreAuthorize / reactive interceptor
             |                      |
          Thiếu quyền             Có quyền
             |                      |
      onError(AccessDenied)     Service đọc
                                ReactiveSecurityContextHolder
                                     |
                              onNext -> onComplete
~~~

`contextWrite` cần nằm trong **cùng chuỗi** với thao tác bảo vệ và đặt ở vị trí phù hợp để Context được truyền lên upstream. Context vẫn được truyền qua các operator Reactor tiêu chuẩn khi đổi scheduler, nhưng không tự động chảy sang `new Thread`, `CompletableFuture` riêng hoặc một lệnh `subscribe()` tách rời.

**Lưu ý AOP:** phương thức reactive được bảo vệ nên trả một `Publisher` (`Mono`/`Flux`). Gọi bean qua Spring container/proxy; tự `new` service hoặc self-invocation `this.securedMethod()` có thể bỏ qua interceptor. Bật `@EnableReactiveMethodSecurity`, không thay bằng `@EnableMethodSecurity` của Servlet.

## 3. Cài dependency và cấu hình

Trong Spring Boot Maven project (phiên bản thư viện để Boot BOM quản lý), bảo đảm có:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`spring-security-test` cung cấp `@WithMockUser` và test listeners; `reactor-test` cung cấp `StepVerifier`. Tạo `src/main/java/com/example/security/MethodSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfig {
}
~~~

Ở Spring Security hiện đại, mặc định `useAuthorizationManager = true`; có thể ghi tường minh `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`. Cấu hình tối giản này chỉ bật method security, phù hợp test service không cần khởi tạo HTTP security filter chain.

## 4. Service có kiểm quyền và đổi scheduler

Tạo `src/main/java/com/example/security/ReportService.java`:

~~~java
package com.example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> viewReport() {
        return Mono.just("report")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> ReactiveSecurityContextHolder.getContext()
                        .map(SecurityContext::getAuthentication)
                        .map(Authentication::getName)
                        .map(name -> "report for " + name));
    }
}
~~~

`hasAuthority('report:read')` so khớp **đúng giá trị authority**; `hasRole('ADMIN')` thường tìm authority `ROLE_ADMIN`. `publishOn` tạo ranh giới scheduler có chủ ý: danh tính phải được lấy từ **Reactor Context** trong lúc thực thi, không đọc một `ThreadLocal` được giả định tồn tại. Đầu ra được chọn là chuỗi cố định theo user, giúp kiểm tra chính xác mà không phụ thuộc DB hoặc API bên ngoài.

## 5. Năm test có thể chạy bằng JUnit Jupiter

Tạo `src/test/java/com/example/security/ReportServiceMethodSecurityTest.java`:

~~~java
package com.example.security;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = {
        MethodSecurityConfig.class,
        ReportService.class
})
class ReportServiceMethodSecurityTest {

    @Autowired
    ReportService service; // Spring bean đã được bọc bởi security interceptor

    @Test
    void unauthenticatedIsDenied() {
        StepVerifier.create(service.viewReport())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:write")
    void wrongAuthorityIsDenied() {
        StepVerifier.create(service.viewReport())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void correctAuthorityCanReadAndSeeUser() {
        StepVerifier.create(service.viewReport())
                .expectNext("report for an")
                .verifyComplete();
    }

    @Test
    void manuallyWrittenContextIsVisibleToService() {
        Mono<String> result = service.viewReport()
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                        authenticatedReader("bao")));

        StepVerifier.create(result)
                .expectNext("report for bao")
                .verifyComplete();
    }

    @Test
    void subscribersHaveIndependentContext() {
        Mono<String> shared = service.viewReport();

        Mono<String> first = shared.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authenticatedReader("an")));

        Mono<String> second = shared.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authenticatedReader("binh")));

        Mono<String> combined = Mono.zip(first, second)
                .map(pair -> pair.getT1() + " | " + pair.getT2());

        StepVerifier.create(combined)
                .expectNext("report for an | report for binh")
                .verifyComplete();
    }

    private static Authentication authenticatedReader(String name) {
        return new UsernamePasswordAuthenticationToken(
                name, "unused",
                List.of(new SimpleGrantedAuthority("report:read"))
        );
    }
}
~~~

Chạy từ gốc dự án bằng Maven Wrapper:

~~~bash
./mvnw -Dtest=ReportServiceMethodSecurityTest test
~~~

Hoặc Windows PowerShell:

~~~powershell
.\mvnw.cmd -Dtest=ReportServiceMethodSecurityTest test
~~~

**Kỳ vọng:** cả năm test PASS nếu dependency/cấu hình đúng. Các test không in `System.out`, vì thế không đưa ra stdout cố định; Maven sẽ hiển thị kết quả test/build theo plugin và phiên bản đang dùng. Tất cả file Java trên có `package`, `import` và class riêng, chạy trong project Spring Boot đã khai báo dependencies phía trên.

| Test | Context/authority | Tín hiệu phải nhận |
| --- | --- | --- |
| `unauthenticatedIsDenied` | Không có authentication | `onError(AccessDeniedException)` |
| `wrongAuthorityIsDenied` | `an`, chỉ có `report:write` | `onError(AccessDeniedException)` |
| `correctAuthorityCanReadAndSeeUser` | `an`, có `report:read` | `onNext("report for an")` + `onComplete` |
| `manuallyWrittenContextIsVisibleToService` | `bao`, authority đưa vào bằng `contextWrite` | `onNext("report for bao")` + `onComplete` |
| `subscribersHaveIndependentContext` | Hai subscriber lần lượt là `an` và `binh` | Cặp kết quả đúng user, không trộn Context |

Ca cuối reuse cùng `Mono` từ bean được proxy rồi subscribe hai lần với hai `Authentication` khác nhau; đây là phép thử trực tiếp rằng Reactor Context là dữ liệu theo subscriber. Ca `correctAuthority...` còn chứng minh username vẫn đọc đúng sau `publishOn`.

## 6. @WithMockUser, ReactorContextTestExecutionListener và quyền

Khi test chạy với `@SpringJUnitConfig`/SpringExtension và `spring-security-test`:

1. `WithSecurityContextTestExecutionListener` tạo `SecurityContext` thử nghiệm từ `@WithMockUser`, `@WithAnonymousUser` hoặc custom `@WithSecurityContext`.
2. `ReactorContextTestExecutionListener` tích hợp test context với `ReactiveSecurityContextHolder` cho các publisher reactive và dọn trạng thái khi test kết thúc.

Nếu dùng `@TestExecutionListeners` tùy biến làm mất listener mặc định, các test gắn `@WithMockUser` có thể không được Reactor nhận diện. Khi cần override listener, bảo toàn `WithSecurityContextTestExecutionListener` **và** `ReactorContextTestExecutionListener` hoặc dùng chế độ merge phù hợp.

Phân biệt rõ **role** và **authority**:

~~~java
@WithMockUser(username = "admin", roles = "ADMIN")
// authority được tạo: ROLE_ADMIN
// tương ứng @PreAuthorize("hasRole('ADMIN')")

@WithMockUser(username = "an", authorities = "report:read")
// authority được tạo: report:read
// tương ứng @PreAuthorize("hasAuthority('report:read')")
~~~

`@WithMockUser` không kiểm tra mật khẩu, tài khoản DB, token hay principal thật. Với domain cần custom principal, có thể dùng `@WithSecurityContext` + factory; `@WithUserDetails` chỉ phù hợp khi có `UserDetailsService` đáp ứng, không tự động tải user bằng mọi `ReactiveUserDetailsService`. `@WithAnonymousUser` tạo ngữ cảnh anonymous cho test; nên phân biệt anonymous với hoàn toàn thiếu `Authentication`.

## 7. Kiểm tra Context thủ công và các lỗi propagation

Không cần `@WithMockUser` khi muốn chủ động gắn user cho từng subscription:

~~~java
Authentication auth = new UsernamePasswordAuthenticationToken(
        "chi", "unused",
        List.of(new SimpleGrantedAuthority("report:read")));

Mono<String> pipeline = service.viewReport()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(pipeline)
        .expectNext("report for chi")
        .verifyComplete();
~~~

Đặt `contextWrite` trên **chính publisher mà StepVerifier subscribe**. Sai lầm điển hình:

~~~java
// Sai: subscription riêng này không cung cấp Context cho test tiếp theo.
service.viewReport()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
        .subscribe();

// Subscriber mới không tự thừa hưởng Authentication từ subscribe trước.
StepVerifier.create(service.viewReport())
        .expectNext("report for chi")
        .verifyComplete();
~~~

Một lần `subscribe()` rời rạc tách thành pipeline khác; `Context` không phải biến toàn cục. Để xác minh Reactor Context đang tồn tại bên trong chain, có thể tạm thêm `ReactiveSecurityContextHolder.getContext().map(SecurityContext::getAuthentication)` vào pipeline trong test; nhưng không để lộ mật khẩu/token vào log.

Các vấn đề khác:

- `StepVerifier.expectError(...)` đúng cho authorization bị từ chối: đừng kỳ vọng `assertThrows` trên lời gọi tạo `Mono` trước subscribe.
- Không bắt và nuốt `AccessDeniedException` qua `onErrorResume` trong chính test policy; nếu phải test fallback, test riêng sau khi xác nhận chặn truy cập.
- `SecurityContextHolder.getContext()` kiểu đồng bộ trong operator reactive có thể thấy giá trị rỗng hoặc sai thread; dùng `ReactiveSecurityContextHolder`.
- Cẩn thận với `block()` hoặc code đồng bộ xen giữa pipeline; `StepVerifier` diễn đạt contract reactive rõ hơn.
- Quyền truy cập khi `@PostAuthorize`/`@PostFilter` phụ thuộc kết quả publisher; kiểm tra rằng dữ liệu không bị phát cho subscriber không có quyền.

## 8. Khi nào cần WebTestClient?

Bộ test ở trên xác minh **service method security** mà không cần HTTP server. Nếu cần kiểm tra thêm WebFlux filter chain và status HTTP, dùng `WebTestClient` bind vào application context đã áp dụng Spring Security test support:

~~~java
// Snippet trong một WebTestClient test đã có endpoint /reports.
// Cấu hình client bằng .apply(springSecurity()) khi bindToApplicationContext.
// import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

webTestClient
        .mutateWith(mockUser()
                .authorities(new SimpleGrantedAuthority("report:read")))
        .get().uri("/reports")
        .exchange()
        .expectStatus().isOk();
~~~

Đoạn trên giả định có biến `webTestClient`, endpoint `/reports` và filter chain nên **chỉ là snippet minh họa**, chưa phải chương trình Java độc lập. Với HTTP test, kết quả `401`/`403` phụ thuộc entry point và cấu hình phân quyền; với method test, kiểm chứng exception/tín hiệu publisher. Nếu test gọi server thật qua network, annotation `@WithMockUser` trong thread test không tự gửi authentication tới server: cần HTTP Basic/Bearer token thật hoặc cơ chế auth trên request.

## 9. Bảng chẩn đoán khi test thất bại

| Hiện tượng | Điều cần kiểm tra | Cách khắc phục |
| --- | --- | --- |
| Ai cũng truy cập được | Chưa bật `@EnableReactiveMethodSecurity`; gọi service ngoài proxy; self-invocation | Tạo bean bằng Spring, test qua `@Autowired` |
| `@WithMockUser` nhưng vẫn bị từ chối | Thiếu Reactor test listener; sai role/authority | Kiểm tra test listeners và `hasRole`/`hasAuthority` |
| Test lỗi ngay khi không có user | Chưa phân biệt trả `Mono` với subscribe | `StepVerifier.expectError(...)` khi subscribe |
| Đổi thread thì sai người dùng | Đọc `ThreadLocal`, dùng `subscribe()` tách pipeline | Dùng `ReactiveSecurityContextHolder` trong cùng Reactor chain |
| Test PASS dù không xuất dữ liệu | Chỉ `verifyComplete()` mà không assert `onNext` | `expectNext(...)` rồi `verifyComplete()` |
| Hai user bị lẫn | Chia sẻ biến authentication mutable hoặc dùng state toàn cục | Dùng `contextWrite` riêng trên mỗi publisher/subscription |
| Role `ADMIN` vẫn bị chặn | `hasRole('ADMIN')` khác `hasAuthority('ADMIN')` | Kiểm tra prefix `ROLE_` và authority thực |
| Method test PASS, API HTTP vẫn lỗi | Chưa test web filter, mapping, token, hoặc security chain | Bổ sung WebTestClient/HTTP integration test |

Đối với các quy tắc theo tài nguyên (ví dụ chỉ xem báo cáo của chính mình), nên thêm test cùng role nhưng **khác owner**; test trong bài này tập trung vào cơ chế Reactor Context và authority. Với `Flux` nhiều item, hãy assert chính xác tập giá trị/điều kiện hoàn tất; với flux vô hạn, dùng `thenCancel()` theo ý định kiểm thử.

## 10. Checklist tự kiểm

- [ ] Method security được bật và method nằm trên Spring bean được AOP quản lý.
- [ ] Method trả `Mono`/`Flux` phù hợp; không bỏ qua subscription.
- [ ] Có `spring-security-test`, `reactor-test`, JUnit Jupiter/Spring Test.
- [ ] Test cả anonymous, thiếu quyền, đúng quyền và đọc đúng principal.
- [ ] Có test truyền auth bằng `contextWrite(withAuthentication(...))`.
- [ ] Đã xác minh hai subscriber có Context độc lập và Context theo operator khi đổi scheduler.
- [ ] Nếu dùng `@WithMockUser`, Reactor test listener còn hoạt động.
- [ ] Đã tách test service method khỏi test HTTP/WebFlux filter chain.

## Tài liệu tham khảo chính thức

- [Testing Method Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/test/method.html)
- [EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Testing Method Security và các test listeners](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Project Reactor — Adding a Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

**Bài tự luyện:** thêm một method `@PreAuthorize("hasRole('ADMIN')")` trả `Mono<String>` và dùng `@WithMockUser(roles = "USER")`/`@WithMockUser(roles = "ADMIN")` để xác minh hai nhánh bị chặn/được phép.