# Hiện thực check hoặc authorize đúng hợp đồng phiên bản

## 1. Mục tiêu: đúng API đang chạy, đúng quyết định bảo mật

`AuthorizationManager<T>` là hợp đồng Spring Security dùng để ra quyết định **có cho phép thực hiện một hành động đối với đối tượng bảo vệ kiểu `T` hay không**. Framework có thể gọi manager ở HTTP request, method invocation hoặc các điểm tích hợp khác.

Khi tự cài đặt một `AuthorizationManager`, không thể chỉ nhớ tên hàm từ một ví dụ trên mạng. Giữa **Spring Security 6.3**, **6.4–6.5** và **7.x**, hợp đồng đã thay đổi:

- Ở 6.3, phương thức phải hiện thực là `check(...)`, trả `AuthorizationDecision`.
- Ở 6.4–6.5, `authorize(...)` được thêm và khuyến nghị sử dụng, nhưng `check(...)` vẫn là phương thức trừu tượng trong interface nên class trực tiếp implements interface vẫn cần hiện thực `check(...)`.
- Từ 7.0, `check(...)` được loại bỏ khỏi interface; `authorize(...)` là phương thức trừu tượng phải hiện thực, trả `AuthorizationResult`. Kiểu `Supplier` còn có wildcard và annotation nullable cần chú ý khi viết `@Override`.

Vì vậy, điều cần quyết định **trước khi viết code** là phiên bản `spring-security-core` thực sự nằm trên compile classpath của **module đang build**; sau đó đọc đúng Javadoc cho **chính phiên bản đó**.

Một implementation đúng phải vượt qua đồng thời hai tiêu chí:

1. **Đúng hợp đồng Java/API:** signature, generic `T`, return type và `@Override` biên dịch đúng, được interceptor gọi.
2. **Đúng hợp đồng authorization:** ALLOW chỉ khi có bằng chứng đầy đủ; DENY cho trường hợp không đủ quyền; `null`/abstain và exception phải được xử lý rõ, tránh vô tình fail-open.

Đây là bài về **hợp đồng phiên bản và cách hiện thực**, không phải cách nâng cấp toàn bộ Spring Boot hay cách thiết kế mọi chính sách ACL.

## 2. Ma trận phiên bản cần ghi nhớ

| Spring Security | Phương thức abstract của `AuthorizationManager<T>` | Phương thức còn lại | Kiểu trả về khi quyết định | Điều cần viết |
|---|---|---|---|---|
| 6.3.x | `check(Supplier<Authentication>, T)` | `verify(...)` là default | `AuthorizationDecision` hoặc `null` | `@Override check(...)` |
| 6.4.x | `check(Supplier<Authentication>, T)`, đã deprecated | `authorize(Supplier<Authentication>, T)` là default; `verify(...)` là default | `check`: `AuthorizationDecision`; `authorize`: `AuthorizationResult` | Class implements trực tiếp **vẫn phải** cung cấp `check(...)` |
| 6.5.x | `check(Supplier<Authentication>, T)`, đã deprecated | `authorize(...)` là default; `verify(...)` là default | Như 6.4 | Duy trì adapter cho bản 6.x; chuẩn bị di chuyển sang `authorize` |
| 7.0.x / 7.1.x | `authorize(Supplier<? extends Authentication>, T)` | `verify(...)` là default; không còn `check` trong interface | `AuthorizationResult` hoặc `null` | `@Override authorize(...)` với đúng signature |

Trong Javadoc 7.x, type-use nullability được biểu diễn rõ hơn, ví dụ `Supplier<? extends @Nullable Authentication>`. Dòng code không cần import riêng annotation nullable để minh họa Java generic, nhưng phần **`? extends` là thành phần của signature cần khớp** khi override. `AuthorizationDecision` vẫn implements `AuthorizationResult`, nên có thể dùng `new AuthorizationDecision(true/false)` làm kết quả cho phiên bản mới.

**Chú ý phạm vi:** các mốc trên là API của Spring Security, không phải “Spring Boot 3 tự động hỗ trợ authorize”. Boot dùng dependency management để chọn một bản Spring Security; một ứng dụng có thể override phiên bản đó. Phải nhìn dependency thực tế, không suy đoán từ tên starter.

Tài liệu tham chiếu theo phiên bản:
- [AuthorizationManager 6.3.3 Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 6.4.10 Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.10/api/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 6.5.11 Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html).
- [AuthorizationManager 7.0 Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationManager.html).

## 3. Nhìn rõ ba phương thức: check, authorize và verify

### 3.1. check: hợp đồng cũ, vẫn tồn tại ở 6.4–6.5

Ở phiên bản 6.3, hình dạng cơ bản:

~~~java
public interface AuthorizationManager<T> {
    AuthorizationDecision check(
            Supplier<Authentication> authentication,
            T object);

    default void verify(
            Supplier<Authentication> authentication,
            T object) {
        // Framework triển khai.
    }
}
~~~

Đây là **mô tả rút gọn** của interface để học hợp đồng, không phải source code đầy đủ của thư viện. `check` nhận `Supplier<Authentication>` và một đối tượng bảo vệ kiểu `T`. Kết quả có thể là `AuthorizationDecision(true)`, `AuthorizationDecision(false)` hoặc `null` để từ chối ra quyết định (*abstain*).

Ở 6.4/6.5, `check` được đánh dấu deprecated, nhưng vẫn là phần bắt buộc của interface cho class implements trực tiếp. Từ “deprecated” có nghĩa nên chuyển hướng thiết kế trong tương lai, **không có nghĩa class cũ tự biến thành implementation chỉ cần `authorize`**.

### 3.2. authorize: hợp đồng mới

Từ 6.4 có thêm `authorize(...)` trả `AuthorizationResult`; ở 6.4–6.5 đó là default method. Từ 7.0, đây là **phương thức trừu tượng**, còn `check` bị loại khỏi interface.

Hình dạng ngắn gọn của API 7.x:

~~~java
public interface AuthorizationManager<T> {
    AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            T object);

    default void verify(
            Supplier<? extends Authentication> authentication,
            T object) {
        // Framework triển khai.
    }
}
~~~

Đây cũng là mô hình rút gọn để đọc; Javadoc thật có annotation nullable trên kiểu liên quan. Bởi `AuthorizationDecision implements AuthorizationResult`, code sau là hợp lệ khi signature phiên bản mới đã đúng:

~~~java
return new AuthorizationDecision(granted);
~~~

Một implementation return type `AuthorizationResult` cho phép framework và các implementation khác cung cấp thêm metadata quyết định về sau mà không buộc client chỉ dùng một class cụ thể.

### 3.3. verify: method tiện ích, không phải điểm override chính

`verify(supplier, object)` là default method. Nó dùng kết quả manager để thực thi kiểm tra, **ném `AccessDeniedException` nếu nhận một quyết định từ chối (negative)**. Khi manager trả `null`, đó là *abstain*, không phải kết quả DENY tự động; **không được giả định `verify(...)` sẽ ném exception trong trường hợp null**.

Đừng tự gọi `verify` rồi bỏ qua những thành phần khác nếu chưa hiểu ý nghĩa abstain và cách manager được kết hợp. Nếu use case đòi phải có quyết định dương tính, nên viết manager luôn trả ALLOW/DENY rõ ràng thay vì `null`.

## 4. Ví dụ đúng cho Spring Security 6.3

Giả sử cần một manager nhận `T = String`, trong đó object là tên authority bắt buộc, ví dụ `"document:read"`. Manager phải từ chối khi không có authentication hợp lệ, authority rỗng hoặc principal anonymous.

Tệp `RequiredAuthorityManager.java` (một class tích hợp Spring Security 6.3; project phải có dependency Spring Security):

~~~java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;

public final class RequiredAuthorityManager
        implements AuthorizationManager<String> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            String requiredAuthority) {

        if (requiredAuthority == null || requiredAuthority.isBlank()) {
            return new AuthorizationDecision(false);
        }

        Authentication current = authentication.get();
        if (current == null
                || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        boolean granted = current.getAuthorities().stream()
                .anyMatch(authority ->
                        requiredAuthority.equals(authority.getAuthority()));

        return new AuthorizationDecision(granted);
    }
}
~~~

**Vì sao code đúng hợp đồng 6.3?**

- Dùng chính `check(Supplier<Authentication>, String)` với `@Override`.
- `AuthorizationDecision` là kiểu trả về của interface.
- Kiểu tham số thứ hai khớp với `AuthorizationManager<String>`.
- Không trả null cho trường hợp thiếu dữ liệu; trả kết quả từ chối tường minh.
- Không sử dụng `hasRole` ngầm: so sánh authority **chính xác**, ví dụ `document:read` khác `ROLE_document:read`.

Đây là ví dụ **kiểm tra quyền chức năng**, không phải quyền của một tài liệu cụ thể. Muốn kiểm tra tenant/owner/ACL phải dùng context và chính sách tài nguyên phù hợp, thay vì chỉ so sánh authority.

**Không** sao chép một snippet 7.x dùng `@Override authorize(...)` vào source compile bằng 6.3: interface 6.3 không có method đó, dẫn đến lỗi `@Override` và thiếu `check` trừu tượng.

## 5. Spring Security 6.4–6.5: “authorize được khuyên dùng” không có nghĩa bỏ check

Ở 6.4–6.5, Javadoc thể hiện đồng thời:

~~~text
@Deprecated AuthorizationDecision check(Supplier<Authentication>, T) // abstract
default AuthorizationResult authorize(Supplier<Authentication>, T)
default void verify(Supplier<Authentication>, T)
~~~

Vì `check` vẫn abstract, một class viết **chỉ**:

~~~java
@Override
public AuthorizationResult authorize(
        Supplier<Authentication> authentication,
        String requiredAuthority) {
    return new AuthorizationDecision(true);
}
~~~

**không phải implementation đầy đủ** của `AuthorizationManager<String>` ở 6.4/6.5; compiler vẫn yêu cầu `check(...)`. Đoạn code trên còn cấp quyền vô điều kiện; nó chỉ dùng để chỉ ra lỗi signature, **không được đưa vào production**.

Một cách viết cho source 6.4/6.5 là giữ implementation `check(...)` đúng như mục 4. Default `authorize(...)` của Spring Security phiên bản đó có khả năng đi qua implementation hiện có. Nếu muốn tự hiện thực `authorize(...)` để tập trung logic quyết định ở API mới, vẫn phải bổ sung adapter `check(...)`:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class DenyMissingAuthorityManager
        implements AuthorizationManager<String> {

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            String requiredAuthority) {

        Authentication current = authentication.get();
        boolean granted = requiredAuthority != null
                && !requiredAuthority.isBlank()
                && current != null
                && current.isAuthenticated()
                && current.getAuthorities().stream()
                        .anyMatch(a -> requiredAuthority.equals(a.getAuthority()));
        return new AuthorizationDecision(granted);
    }

    @Override
    @Deprecated
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            String requiredAuthority) {

        AuthorizationResult result =
                authorize(authentication, requiredAuthority);
        return new AuthorizationDecision(
                result != null && result.isGranted());
    }
}
~~~

Đây là **mã tích hợp 6.4/6.5**, phụ thuộc thư viện Spring Security, không phải chương trình Java độc lập. Về bảo mật, class này trả DENY với kết quả `authorize` null. Trong code thực tế nên trích logic policy ra một phương thức riêng dùng chung để tránh recursion hoặc kiểm tra nhiều lần; adapter phải chỉ chuyển **một chiều**. Ví dụ `authorize → check` và `check → authorize` đồng thời sẽ gọi vòng vô hạn.

Lưu ý: đoạn minh họa 6.4/6.5 dùng `isAuthenticated()`, nhưng `AnonymousAuthenticationToken` có thể có cờ authenticated; nếu endpoint riêng tư, cần dùng đúng cơ chế đánh giá anonymous/remember-me như mục 4 và policy ứng dụng. Không được coi đây là permission theo từng record.

**Khi nào chọn cách nào?**

- Module chỉ chạy 6.3: implement `check`.
- Module cố định 6.4/6.5: vẫn implement `check`; có thể expose thêm `authorize` khi logic yêu cầu và có test.
- Module chuyển hẳn sang 7: bỏ adapter `check`, implement `authorize` với signature 7.
- Nếu có một codebase phải build trên hai major version, không dựa vào giả định source class override cả hai được; tách implementation theo source set/build profile hoặc sử dụng một adapter nội bộ được build/test riêng cho từng version. Không ép một artifact đã compile chống lại ABI khác khi chưa chứng minh tính tương thích.

## 6. Ví dụ đúng cho Spring Security 7.x

Tại Spring Security 7, Javadoc chỉ còn `authorize(...)` và `verify(...)`. Khi tự triển khai trực tiếp interface, cần chú ý kiểu wildcard của supplier:

~~~java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;

public final class RequiredAuthorityManager
        implements AuthorizationManager<String> {

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            String requiredAuthority) {

        if (requiredAuthority == null || requiredAuthority.isBlank()) {
            return new AuthorizationDecision(false);
        }

        Authentication current = authentication.get();
        if (current == null
                || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        boolean granted = current.getAuthorities().stream()
                .anyMatch(authority ->
                        requiredAuthority.equals(authority.getAuthority()));

        return new AuthorizationDecision(granted);
    }
}
~~~

**Điểm khác biệt so với 6.3:**

- Method là `authorize`, không phải `check`.
- Return type được khai báo `AuthorizationResult`.
- Supplier khai báo `Supplier<? extends Authentication>`, khớp wildcard từ hợp đồng 7.x (Javadoc còn thể hiện nullable type-use).
- Không cần implement `check`, và không gắn `@Override` lên method đó vì interface 7 không còn định nghĩa.
- `AuthorizationDecision` vẫn là kết quả cụ thể hợp lệ vì nó implements `AuthorizationResult`.

Một lỗi khó hiểu thường gặp khi nâng cấp 7.x: giữ signature `authorize(Supplier<Authentication>, T)` của 6.4/6.5, thêm `@Override` rồi gặp thông báo **name clash / neither overrides** vì generic wildcard khác dù cùng erasure JVM. Đừng bỏ `@Override` để “chạy cho xong”; sửa signature theo Javadoc compile classpath.

Ngoài ra, ví dụ trên chủ ý deny khi thiếu authority hoặc thiếu authentication. Không để `null` thay thế DENY, vì caller có thể diễn giải null là abstain.

## 7. Tại sao nhiều lambda vẫn tương thích, còn class override thì vỡ?

Một functional interface có thể được implement qua lambda. Do lambda không ghi rõ tên phương thức `check` hay `authorize`, cùng mã nguồn hình dạng:

~~~java
AuthorizationManager<String> denyMissing =
        (authentication, requiredAuthority) -> {
            Authentication current = authentication.get();
            boolean granted = current != null
                    && requiredAuthority != null
                    && current.getAuthorities().stream()
                           .anyMatch(a -> requiredAuthority.equals(a.getAuthority()));
            return new AuthorizationDecision(granted);
        };
~~~

có thể compile sau khi **rebuild với mỗi phiên bản** vì compiler tự gắn lambda với phương thức abstract tương ứng. Điều này không có nghĩa binary đã compile từ version cũ tự bảo đảm tương thích ở runtime mới; cần build và test thực tế.

Đây là mẫu lambda minh họa trong một project có các import:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
~~~

Với code production, thêm kiểm tra anonymous, scope tenant, object permission; lambda đơn giản ở đây chỉ nhằm minh họa cú pháp functional interface. Khi policy phức tạp, class có tên và test rõ dễ quản lý hơn.

**Lưu ý quan trọng:** `AuthorizationManager<String>` được tạo trong ví dụ không tự động trở thành rule của Spring Security. Cần **gắn manager vào interceptor/DSL** tại đúng pointcut hoặc request rule; chỉ khai báo một bean `AuthorizationManager` không bảo đảm mọi request/method đều gọi nó.

## 8. Kiểu đối tượng T và vị trí tích hợp phải khớp

`T` trong `AuthorizationManager<T>` không phải lúc nào cũng là tài nguyên domain. Nó là **secure object context mà interceptor truyền vào**.

| Ngữ cảnh | Ví dụ kiểu `T` | Dữ liệu cần dùng |
|---|---|---|
| HTTP servlet request | `RequestAuthorizationContext` | `HttpServletRequest`, path variables và dữ liệu context |
| Method security trước lời gọi | `MethodInvocation` | Method signature và arguments |
| Method security sau lời gọi | `MethodInvocationResult` (tùy phiên bản/cơ chế) | Invocation cùng giá trị trả về |
| Hợp đồng policy tự viết | `DocumentAccessRequest` hoặc `String` | Resource ID, tenant, authority đã xác minh |
| Message authorization | Kiểu message context tương ứng của integration | Message, headers và actor tin cậy |

Manager generic cho `String` ở mục 4–7 là ví dụ dạy interface, **không thể đưa thẳng** vào `authorizeHttpRequests().access(...)` vốn đòi manager cho context HTTP thích hợp.

### 8.1. Ví dụ gắn manager vào HTTP (ý tưởng áp dụng chung)

Nếu request cần authority `report:read`, Spring Security đã có built-in `hasAuthority(...)`; custom manager chỉ cần khi có thêm policy đặc biệt.

Mã tích hợp Servlet minh họa một manager kết quả deny rõ ràng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.core.Authentication;

@Configuration
class ReportSecurityConfig {

    @Bean
    SecurityFilterChain reportFilterChain(HttpSecurity http)
            throws Exception {

        AuthorizationManager<RequestAuthorizationContext> reportPolicy =
                (authentication, context) -> {
                    Authentication current = authentication.get();
                    boolean granted = current != null
                            && current.isAuthenticated()
                            && current.getAuthorities().stream()
                                    .anyMatch(a ->
                                            a.getAuthority().equals("report:read"));
                    return new AuthorizationDecision(granted);
                };

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/reports/**").access(reportPolicy)
                .anyRequest().denyAll());

        return http.build();
    }
}
~~~

Đây là ví dụ **cấu hình HTTP**, không phải chương trình `javac` độc lập; cần Spring Security, Boot hoặc ứng dụng cấu hình filter, bean và HTTP runtime. Rule chỉ minh họa đường tích hợp, không thay cho kiểm tra tenant/row-level authorization. Với ứng dụng thật cần xem xét các SecurityFilterChain khác, actuator, assets, CORS, CSRF, session, anonymous, authentication entry point và thứ tự matcher.

Để đơn giản và chính xác với một authority đơn thuần, thường nên viết:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").hasAuthority("report:read")
    .anyRequest().denyAll());
~~~

**Đừng dùng `permitAll` hoặc `anyRequest().authenticated()` thay thế một rule quyền cụ thể** khi endpoint đòi authority đặc biệt.

### 8.2. Method invocation cần interceptor được gắn đúng

Một manager cho method security có thể khai báo `AuthorizationManager<MethodInvocation>`. Tuy nhiên, làm thành bean đơn thuần chưa đảm bảo intercept method. Muốn chặn phương thức, phải đăng ký pointcut/interceptor, dùng API cấu hình tương ứng của phiên bản hoặc dùng annotation `@PreAuthorize` trên service. Một cách gọn thường là chuyển policy vào bean:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public DocumentView findDocument(long id) {
    return queryService.findDocument(id);
}
~~~

`documentPolicy` là bean ứng dụng có contract boolean rõ; logic trong bean này cần kiểm tra cả tenant/resource. Code là **ví dụ tích hợp** để minh họa rằng có lúc không cần tự viết `AuthorizationManager`; method security phải bật và lời gọi phải qua Spring proxy.

Nếu thực sự viết custom manager cho method interception, phải phân biệt **before invocation** và **after invocation**; kiểu context khác nhau và hậu kiểm sau lệnh ghi có thể đến sau side effect.

## 9. Quyết định ALLOW / DENY / ABSTAIN: tránh nhầm null thành deny

Spring Security cho phép implementation trả `null` để biểu thị **không có quyết định** (*abstain*). Đây không phải `AuthorizationDecision(false)`.

| Giá trị từ manager | `isGranted()` | Ý nghĩa logic | Kết quả `verify` thông thường |
|---|---|---|---|
| `new AuthorizationDecision(true)` | `true` | ALLOW | Không ném vì không có quyết định âm |
| `new AuthorizationDecision(false)` | `false` | DENY | Ném `AccessDeniedException` |
| `null` | Không có đối tượng để gọi | ABSTAIN | Không tự động ném như DENY |
| Exception trong policy | Không có quyết định bình thường | Lỗi đánh giá / phụ thuộc | Xử lý exception theo stack, không coi đó là ALLOW |

**Khi chỉ có một manager bảo vệ một thao tác nhạy cảm, nên trả true/false tường minh**. Không trả null chỉ vì thiếu principal, token không có tenant hoặc dịch vụ ACL timeout.

Ví dụ:

~~~java
AuthorizationDecision decision =
        new AuthorizationDecision(permissionVerified && resourceVisible);
~~~

Hai boolean ở đây **phải** được tính từ nguồn tin cậy, đã xử lý null/exception và đúng scope. Nếu permission service lỗi, chọn cơ chế fail closed và báo lỗi thích hợp; không cho qua vì “chưa quyết định được”.

### Vì sao abstain nguy hiểm khi kết hợp?

Một số composition có semantics đặc biệt. Chẳng hạn `AuthorizationManagers.allOf(...)` với các manager abstain có thể coi abstain là không chặn, và biến thể mặc định có thể grant nếu mọi manager abstain. Không nên suy luận “allOf + null = deny”.

Từ Spring Security 6.3 có overload cho default khi tất cả abstain:

~~~java
AuthorizationManager<RequestAuthorizationContext> policy =
        AuthorizationManagers.allOf(
                new AuthorizationDecision(false),
                primaryManager,
                secondaryManager);
~~~

Đoạn này là **mã tích hợp minh họa**; `primaryManager`/`secondaryManager` phải cùng generic context và đã tồn tại. Overload dùng `AuthorizationDecision(false)` giúp định nghĩa **all-abstain → DENY**, nhưng không làm policy đúng nếu nhánh manager khác cấp quyền quá rộng. Cần test semantics từng manager và thứ tự fallback.

Với các rule bắt buộc trên tài nguyên (tenant/owner), phần kiểm tra đó nên **trả DENY** khi không xác minh được, tránh trả null rồi nhường cho một rule khác cấp quyền ngoài ý muốn.

## 10. Supplier<Authentication>: lazy, nhưng không phải tự tạo trust

`Supplier<Authentication>` được truyền vào manager để cho phép trì hoãn lấy authentication cho đến khi thật sự cần. Một public endpoint dùng `permitAll` có thể không cần tra context. Trong custom manager:

1. Kiểm tra điều kiện không cần authentication trước (ví dụ tên authority bắt buộc có tồn tại).
2. Chỉ gọi `authentication.get()` khi phải quyết định theo người dùng.
3. Cân nhắc giữ kết quả trong một biến địa phương; không gọi supplier nhiều lần hoặc giữ supplier để dùng bất đồng bộ về sau.
4. Với HTTP context, đừng xem path/query/header do client gửi là danh tính đã xác minh.
5. Không nghĩ `Authentication.isAuthenticated()` đơn lẻ luôn loại bỏ anonymous; có thể dùng cơ chế AuthenticationTrustResolver hoặc built-in manager hỗ trợ anonymous/remember-me chính xác.

Ví dụ logic Java thường dùng:

~~~java
Authentication principal = authentication.get();
if (principal == null) {
    return new AuthorizationDecision(false);
}
~~~

Đây chỉ là mẫu, không thể đủ một mình: một số Authentication anonymous có thể có `principal != null`. Phải xác định policy về anonymous và scope.

**Không giữ kết quả trong cache toàn cục** nếu quyết định phụ thuộc user/tenant/request. Cache quyết định nếu có phải key theo actor, authority, resource, policy version và cơ chế thu hồi thích hợp.

## 11. Những lỗi biên dịch thường gặp và cách đọc nguyên nhân

| Lỗi compiler / triệu chứng | Nguyên nhân có thể | Cách kiểm chứng/sửa |
|---|---|---|
| “Class is not abstract and does not override abstract method check(...)” | Source 6.4/6.5 nhưng chỉ implement `authorize` | Kiểm tra Javadoc đang compile, implement `check` bắt buộc hoặc nâng cấp đồng bộ sang 7 |
| “Method does not override method from its superclass” tại `authorize` | Compile 6.3, interface chưa có `authorize` | Dùng `check` đúng signature ở 6.3 |
| “Method does not override …” tại `check` | Compile 7, `check` đã bị loại | Chuyển sang `authorize` |
| “Name clash: same erasure, yet neither overrides” | 7.x dùng `Supplier<Authentication>` thay cho wildcard theo API | Đối chiếu generic Javadoc 7.x, dùng `Supplier<? extends Authentication>` |
| “Incompatible types: AuthorizationResult cannot be converted to AuthorizationDecision” | Dùng kết quả `authorize` mới nhưng biến khai báo kiểu cũ | Dùng `AuthorizationResult` và `isGranted()`; không ép kiểu nếu không kiểm soát implementation |
| Warning deprecated check | Spring Security 6.4/6.5 | Không bỏ method abstract chỉ để xóa warning; lập kế hoạch migration có kiểm chứng |
| Implementation compile, nhưng rule không chạy | Chưa gắn manager vào HTTP DSL/interceptor; Spring proxy bị bypass | Kiểm tra cấu hình thật, gọi qua bean Spring và test integration |
| “Cannot resolve symbol AuthorizationResult” | Compile classpath quá cũ hoặc dependency không đồng bộ | Xem lại version artifact chính xác, tránh copy code mới vào code cũ |
| Runtime `NoSuchMethodError` / `AbstractMethodError` | Bytecode/thư viện Spring Security không đồng nhất với version compile, hoặc extension chưa tương thích | In dependency tree runtime, build lại extension theo version mục tiêu, không chắp vá method bằng reflection |

**Tránh workaround nguy hiểm:** không bỏ `@Override` để che lỗi, không thêm method overload không được interceptor gọi, không catch tất cả exception rồi trả `new AuthorizationDecision(true)`. Compiler đang chỉ ra **điểm bất đồng hợp đồng**, cần giải quyết ở dependency và chữ ký.

## 12. Xác định đúng dependency thực tế trước khi sửa

Khi build bằng Gradle, lệnh gợi ý (chạy trong đúng multi-project module, thay cấu hình theo module cụ thể):

~~~bash
./gradlew :your-module:dependencyInsight --dependency spring-security-core --configuration compileClasspath
./gradlew :your-module:dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Đây là **lệnh mẫu**, không phải stdout. Đường dẫn `:your-module` chỉ là ký hiệu minh họa, phải thay bằng module thực tế. Trên Windows có thể dùng `gradlew.bat`. So sánh version `spring-security-core`, `spring-security-config`, `spring-security-web` và test dependencies; tránh tình trạng phiên bản nằm ở các major/minor không tương thích.

Ngoài ra có thể dùng IDE “Go to declaration” trên `AuthorizationManager` để kiểm tra thực tế interface trong compile classpath. Sau đó mở Javadoc **đúng phiên bản**, kiểm tra:

- Phương thức abstract hiện hành là `check` hay `authorize`?
- Kiểu `Supplier` là `Supplier<Authentication>` hay `Supplier<? extends Authentication>`?
- Return type là `AuthorizationDecision` hay `AuthorizationResult`?
- Có default method gì? Có annotation `@Nullable` không?
- Cách `verify` xử lý negative/null; semantics composition nếu dùng `allOf/anyOf`.
- Test chạy bản framework nào? Có thư viện extension compile theo version cũ không?

Khi dùng Spring Boot BOM, tránh tự đặt phiên bản từng spring-security artifact khác nhau nếu không có lý do được kiểm chứng. Nếu nâng major version, đọc migration guide và sửa toàn bộ chỗ tương tác interface một cách có kiểm soát.

## 13. Nâng cấp từ check sang authorize an toàn

Một lộ trình migrate có thể kiểm toán:

1. **Đóng băng hợp đồng hiện tại.** Ghi version compile/runtime, mọi implementation `AuthorizationManager<T>`, mọi nơi gọi `check/authorize/verify` và các manager composition.
2. **Tách logic quyết định khỏi adapter phiên bản.** Viết policy thuần Java hoặc service domain nhận actor/resource tin cậy và trả kết quả rõ `ALLOW/DENY`.
3. **Giữ adapter 6.x đúng.** Trên 6.4/6.5, `check` vẫn là abstract; nếu viết `authorize` cũng vẫn có adapter `check` hợp lệ. Tránh vòng gọi hai chiều.
4. **Khi chuyển sang 7, đổi signature.** Implement `authorize(Supplier<? extends Authentication>, T)`, return `AuthorizationResult`; bỏ các `@Override check` không còn trong interface.
5. **Review semantics null.** Bảo đảm null/abstain không bị diễn giải như DENY ở nơi này nhưng như ALLOW ở nơi khác; đặt default deny khi compose manager nếu policy yêu cầu.
6. **Build từng target version.** Với thư viện dùng chung, test riêng bytecode của từng major; không suy luận chỉ từ IDE compile một bản.
7. **Integration test thực tế.** HTTP/method interceptor phải gọi implementation mới; test DENY, ALLOW, null, anonymous, thiếu tenant, lỗi dependency, proxy bypass, behavior của `verify` và middleware handling.
8. **Quan sát sau nâng cấp.** Theo dõi denied/abstained/error metrics, latency và các đường yêu cầu được phép; không log token hoặc dữ liệu ACL nhạy cảm.

Nếu codebase chỉ hỗ trợ một version, không cần thêm compatibility layer phức tạp. Dùng đúng API version đang chạy và xóa adapter lỗi thời khi đã chuyển hoàn toàn sang 7.

## 14. Demo Java 17 độc lập: phân biệt DENY với ABSTAIN

Để nắm semantics mà không cần runtime Spring, hãy mô phỏng việc manager có thể trả một trong ba trạng thái. Đây là **chương trình Java thuần**, không mô phỏng tự động toàn bộ `AuthorizationManager.verify` của Spring.

Tạo tệp `DecisionDemo.java`:

~~~java
public class DecisionDemo {
    enum Decision { ALLOW, DENY, ABSTAIN }

    static Decision decide(String actor, String authority, boolean dataReady) {
        if (actor == null || authority == null) {
            return Decision.DENY;
        }
        if (!dataReady) {
            return Decision.ABSTAIN;
        }
        return actor.equals("an") && authority.equals("document:read")
                ? Decision.ALLOW
                : Decision.DENY;
    }

    static boolean failClosed(Decision result) {
        return result == Decision.ALLOW;
    }

    public static void main(String[] args) {
        Decision allowed = decide("an", "document:read", true);
        Decision denied = decide("binh", "document:read", true);
        Decision unknown = decide("an", "document:read", false);

        System.out.println("allowed=" + allowed
                + ", permit=" + failClosed(allowed));
        System.out.println("denied=" + denied
                + ", permit=" + failClosed(denied));
        System.out.println("unknown=" + unknown
                + ", permit=" + failClosed(unknown));
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
javac DecisionDemo.java
java DecisionDemo
~~~

Stdout:

~~~text
allowed=ALLOW, permit=true
denied=DENY, permit=false
unknown=ABSTAIN, permit=false
~~~

Trong demo, adapter `failClosed` chỉ permit với ALLOW. **Trong Spring thật, `null` từ một manager là abstain và có semantics do caller/composition quyết định**, nên không được dùng đoạn mô phỏng để khẳng định `verify` luôn tự deny khi null. Nếu thuộc tính quyền bắt buộc không sẵn sàng, tốt hơn là manager hoàn chỉnh trả `AuthorizationDecision(false)` hoặc ném lỗi kỹ thuật có kiểm soát, không trả null cho đường bắt buộc được bảo vệ.

## 15. Unit test và integration test cần thiết

### 15.1. Unit test contract cho từng version

Với **6.3**:

~~~java
AuthorizationDecision decision =
        manager.check(() -> authenticatedUser, "document:read");

assertThat(decision).isNotNull();
assertThat(decision.isGranted()).isTrue();
~~~

Với **6.4–6.5** có thể kiểm tra cả `check` và `authorize`:

~~~java
AuthorizationDecision legacy =
        manager.check(() -> authenticatedUser, "document:read");
AuthorizationResult modern =
        manager.authorize(() -> authenticatedUser, "document:read");

assertThat(legacy.isGranted()).isEqualTo(modern.isGranted());
~~~

Với **7.x**:

~~~java
AuthorizationResult result =
        manager.authorize(() -> authenticatedUser, "document:read");

assertThat(result).isNotNull();
assertThat(result.isGranted()).isTrue();
~~~

Ba đoạn là **snippet test minh họa**, phụ thuộc fixture `manager`/`authenticatedUser`, JUnit và assertion library; không phải class Java 17 standalone. Với denied/absent authentication, mong đợi explicit negative decision. Nếu cố tình hỗ trợ abstain, thêm test caller/composition theo nghĩa thực của abstain.

### 15.2. Test verify, null và composition

Cần chứng minh:

- `verify` với negative decision ném `AccessDeniedException`.
- `verify` với positive decision không ném.
- `verify` với manager abstain không được mặc định coi là DENY nếu framework không thực hiện điều đó.
- `AuthorizationManagers.allOf` khi tất cả thành phần abstain: kiểm tra đúng default đã chọn; cân nhắc overload all-abstain DENY.
- `AuthorizationManagers.anyOf` khi có manager grant, deny hoặc abstain: kiểm tra rule tổng thực tế, tránh một manager grant quá rộng.
- Null authentication, anonymous token và remember-me theo security policy phải không cấp quyền ngoài ý muốn.

Ví dụ test tóm tắt (pseudo-fixture trên Spring Security, không phải class độc lập):

~~~java
assertThatThrownBy(
        () -> manager.verify(() -> userWithoutAuthority, "document:read"))
        .isInstanceOf(AccessDeniedException.class);
~~~

### 15.3. Test interceptor thật, không chỉ gọi manager trực tiếp

Một unit test gọi `manager.check(...)` hoặc `authorize(...)` có thể PASS dù manager **chưa được đăng ký** với Spring Security. Vì thế cần thêm test integration:

1. HTTP request match đúng rule custom `.access(manager)` hay không, theo thứ tự matcher.
2. SecurityFilterChain nào đang xử lý request? Nhiều chain có thể dẫn tới rule khác.
3. Method security có được bật và interceptor được gắn vào đúng method không?
4. Lời gọi đi qua Spring-managed proxy, không phải `this.method()` self-invocation?
5. Object context thực tế đúng generic `T` hay không?
6. Khi không có rule match, có fallback `denyAll()` hoặc policy phù hợp không?
7. Với user đúng role nhưng sai tenant/owner, phải bị chặn ngay cả khi manager kiểm tra authority chung trả granted.
8. Khi permission backend timeout hoặc trả dữ liệu thiếu, không được cho phép thao tác do null/exception.
9. Với các đường non-HTTP (message, scheduler), có adapter/policy đúng chứ không dựa vào rule HTTP?
10. Sau khi upgrade version, chạy thử nghiệm trên runtime thực tế để phát hiện `AbstractMethodError`, `NoSuchMethodError`, generic bridge hoặc artifact lẫn version.

## 16. Các lỗi security đặc trưng khi triển khai sai contract

**Lỗi A — Thay null bằng `true` để tránh “block nhầm”.** Đây là fail-open. Cần làm rõ tại sao manager abstain và chỉ grant khi chính sách thực sự cho phép.

**Lỗi B — Return negative nhưng logic caller bỏ qua kết quả.** Ví dụ gọi `manager.authorize(...)` chỉ để log rồi vẫn tiếp tục update. Phải để interceptor xử lý kết quả hoặc kiểm tra rõ và chặn khi không granted.

**Lỗi C — `verify` được dùng như bắt buộc deny trong mọi trường hợp null.** Default verify chỉ xử lý negative decision; abstain có thể trôi qua. Nếu cần deny khi chưa quyết định, trả negative tường minh hoặc compose có all-abstain default deny.

**Lỗi D — Implement class đúng API nhưng không gắn vào pointcut/filter chain.** Manager không có tác dụng với request/method nếu không được framework gọi.

**Lỗi E — Truyền sai kiểu `T`.** Manager cho `String` không tự thể hiện được quyền trên `RequestAuthorizationContext` hoặc `MethodInvocation`; ép kiểu không giải quyết khác biệt ngữ nghĩa.

**Lỗi F — Tin `authentication.get() != null` là đủ.** Anonymous token vẫn có thể tồn tại, role có thể thiếu, claim tenant phải xác minh.

**Lỗi G — Quên chính sách resource.** Authority `document:read` chưa đủ cho một document của tenant khác.

**Lỗi H — Bắt ngoại lệ policy rồi cấp quyền.** Một sự cố permission backend trở thành đường bypass; xử lý fail closed và báo lỗi.

**Lỗi I — Đổi method signature theo ví dụ mới nhưng không nâng toàn bộ dependencies.** Compile, runtime có thể dùng API khác; đọc dependencyInsight và test ABI.

**Lỗi J — Dùng `@Override check` ở 7.x hoặc `@Override authorize` ở 6.3.** Cần chọn một hợp đồng đúng với version, không xóa annotation để che mismatch.

## 17. Checklist trước khi merge

- [ ] Đã xác định chính xác version `spring-security-core` compile/runtime của module.
- [ ] Có liên kết Javadoc đúng version và chữ ký abstract method tương ứng.
- [ ] `@Override` thực sự override, không có bridge/name clash do `Supplier` generic.
- [ ] Return type đúng, dùng `AuthorizationDecision`/`AuthorizationResult` theo contract.
- [ ] ALLOW/DENY/ABSTAIN được định nghĩa rõ; không đồng nhất null với false hoặc true.
- [ ] Khi quyền bắt buộc, dữ liệu thiếu/anonymous/permission backend lỗi không cấp quyền.
- [ ] `verify` và manager composition có test cho quyết định positive, negative, abstain.
- [ ] Kiểu `T` khớp secure context do HTTP/method/message interceptor truyền vào.
- [ ] Manager đã được gắn vào đúng SecurityFilterChain, interceptor hoặc policy use case.
- [ ] Authority, tenant và quyền tài nguyên được kiểm tra theo scope đáng tin.
- [ ] Có unit test policy và integration test interceptor/route thực, kể cả các đường non-HTTP quan trọng.
- [ ] Build sạch trên target version, không có Spring Security artifact bị lệch version và không có lỗi runtime linkage.

**Quy tắc cuối:** Đúng tên phương thức mới chỉ giúp code compile. Một `AuthorizationManager` đúng phải ra quyết định đáng tin, xử lý abstain có chủ đích và được Spring Security gọi tại đúng ranh giới. Đối với 6.3 hãy hiện thực `check`; đối với 6.4–6.5 nhớ `check` vẫn abstract dù đã deprecated; đối với 7.x hãy hiện thực `authorize` với signature và return type mới.

## Tài liệu tham khảo theo phiên bản

- [Spring Security 6.3.3 API – AuthorizationManager](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.4.10 API – AuthorizationManager](https://docs.spring.io/spring-security/site/docs/6.4.10/api/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.5 API – AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7.0 API – AuthorizationManager](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7.0 What's New – check removed](https://docs.spring.io/spring-security/reference/7.0-SNAPSHOT/whats-new.html)
- [Spring Security Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
