# AccessDecisionManager, AccessDecisionVoter và hướng chuyển sang AuthorizationManager

> **Phạm vi:** Spring Security – authorization, nhóm **Phiên bản và chuyển đổi**. Bài này giải thích kiến trúc quyết định quyền kiểu cũ, cách đọc đúng các phiếu bầu, và lộ trình chuyển sang `AuthorizationManager` khi nâng cấp Spring Security. Ví dụ integration test nhắm Spring Boot 3.x, Spring Security 6.x và Java 17+; các khác biệt của Spring Security 7 được chỉ rõ để tránh áp dụng nhầm API.

## 1. Vì sao cần hiểu cả hệ thống cũ lẫn mới?

Trong codebase Spring Security lâu năm có thể gặp bộ ba:

- `SecurityMetadataSource`: tìm các `ConfigAttribute` gắn với URL hoặc method cần bảo vệ, chẳng hạn `ROLE_ADMIN`.
- `AccessDecisionVoter<S>`: một policy riêng bỏ phiếu `GRANT`, `DENY` hoặc `ABSTAIN` đối với đối tượng đang truy cập.
- `AccessDecisionManager`: tổng hợp các phiếu từ nhiều voter, quyết định cho qua hoặc ném `AccessDeniedException`.

Ở kiến trúc hiện đại, `AuthorizationManager<T>` nhận `Supplier<Authentication>` và đối tượng đang được bảo vệ, sau đó đưa ra quyết định cuối cùng. Spring Security cung cấp các manager dựng sẵn và cách ghép policy, nên nhiều ứng dụng không cần tự viết voter hay decision manager nữa.

**Điểm mấu chốt:** chuyển đổi là **bảo toàn chính sách bảo mật**, không chỉ đổi tên interface. Việc chọn cách ghép rule khác có thể làm người từng bị từ chối nay được phép truy cập. Trước khi sửa code phải xác định đúng quy tắc bỏ phiếu, nhất là trường hợp các voter bất đồng hoặc không voter nào đưa ra quyết định.

### Ranh giới phiên bản

| Nhánh | Điều cần biết |
| --- | --- |
| Spring Security 5.x | API cũ còn phổ biến, nhưng `AuthorizationManager` đã trở thành hướng thay thế; `authorizeHttpRequests` xuất hiện trong lộ trình hiện đại hóa |
| Spring Security 6.x (ví dụ Spring Boot 3.x) | Ưu tiên `authorizeHttpRequests`, `@EnableMethodSecurity` và `AuthorizationManager`. Legacy Access API còn có thể có trong code cũ |
| Spring Security 6.4–6.5 | `AuthorizationManager.authorize(...)`/`AuthorizationResult` là API mới hơn; `check(...)` bị deprecated trong 6.5 nhưng vẫn là abstract method ở 6.x |
| Spring Security 7.x | Các class `AccessDecisionManager`, `AccessDecisionVoter` và Access API liên quan chuyển sang module legacy `spring-security-access`. `AuthorizationManager.authorize(...)` là điểm triển khai chính; `check(...)` không còn là API để override |

**Không trộn chữ ký `check` của 6.x với `authorize` của 7.x** trong cùng một class custom rồi kỳ vọng biên dịch trên mọi phiên bản. Ví dụ chạy hoàn chỉnh ở mục 6 dùng lambda `AuthorizationManager` và các factory có sẵn, giúp hạn chế phụ thuộc vào chữ ký cũ.

## 2. Kiến trúc AccessDecisionManager và AccessDecisionVoter

### 2.1. Luồng quyết định kiểu cũ

```text
HTTP request / method invocation
             │
             ▼
FilterSecurityInterceptor / MethodSecurityInterceptor (legacy)
             │
             ├─ SecurityMetadataSource
             │     └─ lấy ConfigAttribute tương ứng URL/method
             │
             ▼
      AccessDecisionManager.decide(authentication, object, attributes)
             │
             ├─ RoleVoter                  ──► GRANT / DENY / ABSTAIN
             ├─ AuthenticatedVoter         ──► GRANT / DENY / ABSTAIN
             └─ CustomDomainVoter         ──► GRANT / DENY / ABSTAIN
             │
             ▼
      Bộ tổng hợp phiếu (strategy)
             ├─ cho phép: tiếp tục request / gọi method
             └─ từ chối: AccessDeniedException
```

`Authentication` chứa danh tính và danh sách `GrantedAuthority`. `secureObject` có thể là request được bọc trong `FilterInvocation` hoặc method invocation tương ứng; `ConfigAttribute` biểu diễn metadata policy (role, trạng thái xác thực, expression hoặc cấu hình tùy biến). Đừng nhầm **authentication** (ai là người gọi) với **authorization** (người đó có được phép làm điều này không).

Chữ ký legacy để **đọc hiểu**, không phải chương trình độc lập:

```java
// API cũ; chỉ dùng khi bảo trì/migrate legacy code.
interface AccessDecisionManager {
    void decide(
        Authentication authentication,
        Object secureObject,
        Collection<ConfigAttribute> attributes)
        throws AccessDeniedException;

    boolean supports(ConfigAttribute attribute);
    boolean supports(Class<?> secureObjectType);
}

interface AccessDecisionVoter<S> {
    int vote(Authentication authentication,
             S secureObject,
             Collection<ConfigAttribute> attributes);

    boolean supports(ConfigAttribute attribute);
    boolean supports(Class<?> secureObjectType);
}
```

`supports(...)` giúp framework xác định voter/manager có thể xử lý loại metadata và loại đối tượng nào. `vote(...)` không được gọi đến business method hay tạo side effect; nhiệm vụ của voter là đưa ra quyết định. Mã trên là chữ ký **rút gọn minh họa** từ các interface thực tế, không khai báo lại chúng trong project.

### 2.2. Ba kết quả của một voter

| Phiếu | Ý nghĩa | Điều không được suy diễn |
| --- | --- | --- |
| `ACCESS_GRANTED` (+1) | Voter cho phép theo policy mà nó đại diện | Không đồng nghĩa toàn bộ hệ thống sẽ cho phép |
| `ACCESS_DENIED` (-1) | Voter từ chối theo policy đó | Có thể bị strategy `AffirmativeBased` bỏ qua nếu voter khác grant |
| `ACCESS_ABSTAIN` (0) | Voter không có ý kiến/không xử lý rule này | **Không đồng nghĩa** cho phép |

Voter chỉ nên abstain nếu policy không áp dụng hoặc không thể xét rule tương ứng; nếu policy áp dụng và caller không đủ quyền, kết quả thường là deny. Ví dụ `RoleVoter` abstain khi không có `ConfigAttribute` nào mang prefix role mà nó hỗ trợ; khi role attribute áp dụng nhưng user thiếu role thì deny.

Khi **tất cả voter abstain**, các implementation voting mặc định thường từ chối (`allowIfAllAbstainDecisions=false`). Bật all-abstain = allow chỉ để “hết lỗi 403” có thể mở lỗ hổng. Khi migrate, luôn xác minh chính sách fallback và các URL/method không được match.

### 2.3. Ba cách tổng hợp phiếu cũ

| Strategy | Nguyên tắc | Khi voter A GRANT, voter B DENY |
| --- | --- | --- |
| `AffirmativeBased` | **Ít nhất một GRANT** thì cho phép; deny không phủ quyết grant | **ALLOW** |
| `UnanimousBased` | **Có DENY** thì từ chối; nếu không DENY và có GRANT thì cho phép | **DENY** |
| `ConsensusBased` | So sánh số phiếu GRANT và DENY; mặc định hòa từ chối, có cấu hình xử lý hòa | **DENY khi hòa**, theo cấu hình mặc định |

Các phiếu abstain bị bỏ qua trong việc đếm grant/deny; nếu **toàn abstain**, dùng policy cấu hình cho trường hợp này, mặc định deny. Khi một codebase tùy chỉnh tie hoặc all-abstain behavior, phải đọc cấu hình thực tế và viết test tương ứng.

Ví dụ: `RoleVoter` GRANT vì user có role nhân viên; `AccountSuspendedVoter` DENY vì tài khoản đang bị khóa. Với `AffirmativeBased`, chỉ cần một GRANT, người bị khóa **vẫn có thể được phép truy cập**. Với `UnanimousBased`, DENY sẽ chặn. Đây là một ví dụ vì sao không thể thay `AffirmativeBased` bằng tổ hợp mới mà không hiểu kỳ vọng nghiệp vụ.

**Cách suy nghĩ khi migrate:**

- “Có ít nhất một policy cho phép” gần với logical OR, nhưng phải xác định rõ deny/abstain behavior.
- “Tất cả policy bắt buộc đều cho phép” gần với logical AND, nhất là một policy có tính phủ quyết như suspended/tenant isolation.
- “Đa số thắng” của `ConsensusBased` không tương đương trực tiếp với `anyOf` hoặc `allOf`; cần viết manager tổng hợp tùy biến nếu nghiệp vụ vẫn thật sự cần majority vote.
- Một deny mang tính **veto** không được đặt cùng nhánh OR với rule grant; cần ưu tiên deny hoặc tách thành điều kiện bắt buộc.

## 3. AuthorizationManager: quyết định quyền theo API mới

### 3.1. Cơ chế tổng quát

```text
HTTP request
   │
   ▼
SecurityFilterChain
   │
   ▼
AuthorizationFilter (authorizeHttpRequests)
   │
   ▼
RequestMatcherDelegatingAuthorizationManager
   │
   ├─ match request nào?
   └─ áp AuthorizationManager<RequestAuthorizationContext>
        ├─ authentication: Supplier<Authentication> (lấy khi cần)
        ├─ context: request + path variables nếu được matcher cung cấp
        └─ result: allow / deny / abstain
             │
             ├─ deny  → AccessDeniedException → HTTP response xử lý bởi security
             └─ allow → tiếp tục chain → Controller / Service
```

Ở method layer, `@EnableMethodSecurity` dùng các interceptor như `AuthorizationManagerBeforeMethodInterceptor` và `AuthorizationManagerAfterMethodInterceptor` để đánh giá trước/sau method. `@PreAuthorize`, `@PostAuthorize`, `@Secured` và JSR-250 được phục vụ bởi các manager/chốt chặn phù hợp.

`AuthorizationManager<T>` là một abstraction có kiểu cho đối tượng được bảo vệ (ví dụ `RequestAuthorizationContext` hoặc `MethodInvocation`), giúp policy kiểm tra actor và resource/argument. `Supplier<Authentication>` cho phép trì hoãn lấy Authentication đến khi thực sự cần, hữu ích cho `permitAll`/`denyAll` và các rule không phụ thuộc user.

### 3.2. Kiểu kết quả và abstain

Trong nhánh 6.4+ và 7.x, API mới có dạng khái niệm:

```java
// Trích ý tưởng API hiện đại, không phải file Java độc lập.
AuthorizationResult authorize(
    Supplier<Authentication> authentication,
    T secureObject);
```

`new AuthorizationDecision(true)` nghĩa là allow, `new AuthorizationDecision(false)` là deny; `null` có thể biểu diễn “abstain” với implementation cho phép. `AuthorizationManager.verify(...)` dùng kết quả để ném `AccessDeniedException` khi có quyết định deny. **Không tự giả định abstain = deny hoặc abstain = allow trong mọi cơ chế ghép**. Ví dụ overload `AuthorizationManagers.allOf/anyOf` có quy tắc khi tất cả abstain hoặc danh sách rỗng; hãy chọn fallback rõ ràng và test trường hợp không policy nào match.

Nếu dùng `@PreAuthorize`/`@PostAuthorize`, Spring Security thường đã tạo manager phù hợp; chỉ cần custom manager khi policy thực sự phức tạp, cần dữ liệu domain hoặc tích hợp hệ thống quyền bên ngoài.

### 3.3. Mapping cũ sang mới

| Legacy | Cách dùng hiện đại | Cần giữ ngữ nghĩa gì? |
| --- | --- | --- |
| `FilterSecurityInterceptor` + `authorizeRequests(...)` | `AuthorizationFilter` + `authorizeHttpRequests(...)` | Thứ tự matcher, fallback, dispatcher, mã trạng thái |
| `SecurityMetadataSource` / `ConfigAttribute` | `RequestMatcher`/config DSL, manager nhận context | Scope URL/method, path variable, resource ownership |
| `AccessDecisionVoter` | Một `AuthorizationManager<T>` cho từng policy | Grant/deny/abstain, veto và dữ liệu đầu vào |
| `AffirmativeBased` | `AuthorizationManagers.anyOf(...)` hoặc policy OR rõ ràng | Một grant có override deny hay không; all-abstain fallback |
| `UnanimousBased` | `AuthorizationManagers.allOf(...)` hoặc policy AND rõ ràng | Một deny có veto hay không; all-abstain fallback |
| `ConsensusBased` | Policy tổng hợp tùy biến có kiểm thử | Hòa, đa số, đếm abstain |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Annotation nào thật sự bật và proxy behavior |
| `MethodSecurityInterceptor` | Before/after method authorization interceptors | Thời điểm check trước/sau, side effect, self-invocation |
| Custom expression voter | `WebExpressionAuthorizationManager` hoặc manager type-safe | Semantics SpEL, tên bean, role prefix, principal/resource context |

Không có “find/replace” an toàn cho toàn bộ các cặp trên. Ví dụ `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` kiểm tra chính xác chuỗi `ADMIN`; đổi sai có thể gây false deny hoặc false allow.

## 4. Chuyển đổi theo từng lớp, có kiểm soát

### Bước 1 – Chụp chính sách đang chạy

Liệt kê tất cả chỗ dùng `AccessDecisionManager`, `AccessDecisionVoter`, `SecurityMetadataSource`, `FilterSecurityInterceptor`, `MethodSecurityInterceptor`, `@EnableGlobalMethodSecurity` và `authorizeRequests`. Ghi lại URL pattern/method, HTTP method, thứ tự matcher, roles, scope, owner/tenant, các trạng thái nghiệp vụ, và cấu hình tie/all-abstain/veto. Đừng mặc định mỗi voter chỉ phụ thuộc roles.

Với policy “khóa tài khoản”, “đang bị đình chỉ”, “tenant khác”, “chỉ sửa resource mình sở hữu”, hãy xác định xem **deny có phải phủ quyết tuyệt đối** hay không. Mọi trường hợp nhạy cảm cần test trước khi chuyển.

### Bước 2 – Chuyển HTTP rules

Ví dụ **legacy**, chỉ để nhận diện (đoạn minh họa, không xây dựng ứng dụng độc lập):

```java
http.authorizeRequests()
    .antMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

Ví dụ mới trên Spring Security 6.x (đặt trong `@Bean SecurityFilterChain`):

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/reports/**").hasAuthority("report:read")
    .anyRequest().denyAll()
);
```

Ở nhánh mới, không dựa vào `antMatchers` cũ. Dùng `requestMatchers(...)` đúng context web (Servlet), phân biệt `securityMatcher` – chọn chain – với `requestMatchers` – chọn rule trong chain. Quy tắc trong `authorizeHttpRequests` được xét **theo thứ tự khai báo**, nên đặt matcher cụ thể trước matcher rộng. Chọn fallback `denyAll` nếu muốn “chỉ mở những route đã liệt kê”; nếu ứng dụng trước đây dùng `authenticated` cho route còn lại, đổi sang `denyAll` là **thay đổi policy có chủ đích** cần test và review.

Đừng tự suy ra HTTP 401/403 chỉ từ biểu thức Java: anonymous có thể được chuyển tới login/401 theo entry point, người đã xác thực nhưng thiếu quyền thường bị 403; kiểm tra filter chain và application setup bằng `MockMvc`.

### Bước 3 – Chuyển method security

```java
// Legacy:
@EnableGlobalMethodSecurity(prePostEnabled = true)

// Hiện đại:
@EnableMethodSecurity
```

`@EnableMethodSecurity` bật pre/post annotations theo default; nếu code dùng `@Secured` hoặc JSR-250 (`@RolesAllowed`), cần bật cờ tương ứng (`securedEnabled = true`, `jsr250Enabled = true`) và kiểm tra behavioral parity. Spring Boot starter security **không tự động bật** method security chỉ nhờ có dependency.

Ví dụ policy method dựa vào quyền và resource (đoạn minh họa, cần có bean `documentPolicy` thật):

```java
@PreAuthorize("hasAuthority('document:write') "
    + "and @documentPolicy.canEdit(authentication, #p0)")
public void editDocument(long documentId, String newTitle) {
    // Ghi DB sau khi đã qua quyền; service thực còn cần
    // kiểm soát tenant và concurrency ở repository/SQL.
}
```

Dùng `#p0` để tránh phụ thuộc việc Java compiler giữ tên tham số. Đảm bảo lời gọi **đi qua Spring-managed proxy**; `this.editDocument(...)` trong cùng bean có thể bỏ qua advice. Với write, `@PostAuthorize` diễn ra sau method body nên không dùng thay cho chốt chặn trước mutation.

### Bước 4 – Thay voter bằng manager cho policy tương đương

Một custom `AccessDecisionVoter` kiểm tra “user bị suspended” thường có thể thay bằng `AuthorizationManager<RequestAuthorizationContext>`. Với policy mới, không cần tái tạo `ConfigAttribute` chỉ để trả về ba hằng số cũ. Dùng type-safe context, đưa kết quả vào `AuthorizationDecision`.

Ví dụ dùng lambda để giữ tương thích Spring Security 6.x (SAM `check`) và 7.x (SAM `authorize`) trong các nhánh tương ứng, miễn dependency framework và chữ ký generic do compiler chọn đúng:

```java
// Đặt trong @Configuration; đoạn này minh họa custom bean.
@Bean
AuthorizationManager<RequestAuthorizationContext> activeAccount() {
    return (authentication, context) -> {
        Authentication user = authentication.get();
        boolean active = user != null
            && user.isAuthenticated()
            && !"suspended".equals(user.getName());
        return new AuthorizationDecision(active);
    };
}
```

Đây là **demo rule cố định**, không phải giải pháp kiểm tra trạng thái tài khoản sản phẩm thật. Ở production, dùng nguồn dữ liệu tin cậy (user/account repository hoặc policy service), cân nhắc cache/revocation, timeout, error policy và tránh bỏ qua user disabled/tenant restriction. `authentication.get()` chỉ gọi khi cần; nếu không cần danh tính, không bắt supplier lấy sớm.

Nếu có cả policy “phải có `report:read`” **và** “tài khoản không bị đình chỉ”, chúng là các điều kiện **AND**. Nếu dùng `anyOf`, một grant từ quyền đọc có thể cho qua bất chấp policy suspended deny – lặp lại lỗi `AffirmativeBased`. Dùng `allOf` hoặc một policy có deny veto rõ ràng, kèm test account đã suspended nhưng có role/scope hợp lệ.

### Bước 5 – Có thể dùng adapter tạm thời, nhưng cần kết thúc migration

Trong giai đoạn có nhiều voter/domain policy chưa thể chuyển cùng lúc, adapter `AuthorizationManager` có thể gọi `AccessDecisionManager.decide(...)` và ánh xạ kết quả:

```java
// Pseudocode migration: cần metadata source phù hợp loại object.
try {
    oldManager.decide(authentication, secureObject, attributes);
    return new AuthorizationDecision(true);
} catch (AccessDeniedException denied) {
    return new AuthorizationDecision(false);
}
```

Adapter cho **một voter** phải ánh xạ đủ ba giá trị: `ACCESS_GRANTED → true`, `ACCESS_DENIED → false`, `ACCESS_ABSTAIN → null`. Không map abstain sang true và cũng không ép mọi exception thành “deny”; chỉ convert `AccessDeniedException` theo thiết kế, các lỗi hệ thống khác cần nổi lên hoặc xử lý bằng chính sách fail-closed rõ ràng.

Adapter cần lưu ý đối tượng đầu vào: manager request thường nhận `RequestAuthorizationContext`, trong khi voter cũ có thể đòi `FilterInvocation`/`ConfigAttribute`. Không ép kiểu hoặc tự tạo metadata sai ngữ cảnh. Hãy kiểm tra runtime type và dùng test để chứng minh parity. Sau khi policy mới đã được kiểm chứng, gỡ adapter và dependency legacy.

### Bước 6 – Nhánh Spring Security 7

Nếu nâng cấp lên Spring Security 7 mà vẫn cần chạy tạm legacy Access API, thêm dependency **chỉ khi còn code dùng nó**:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-access'
}
```

Spring Security 7 chuyển `AccessDecisionManager`, `AccessDecisionVoter` và Access API liên quan vào module này. Dùng dependency management/BOM đúng phiên bản framework; không lấy jar 6.x để lấp class thiếu của 7.x. Đây là **bước tương thích tạm thời**, không phải kiến trúc mới nên sao chép. Khi tạo custom class `AuthorizationManager` ở 7.x, override `authorize(...)` theo API hiện hành; ở 6.x, kiểm tra giao diện `check(...)` của phiên bản đang chạy. Lambda/factory có thể giảm khác biệt ở source code.

## 5. Tình huống quan trọng: chốt chặn suspended phải có quyền phủ quyết

Giả sử hệ thống yêu cầu:

- Người dùng phải có authority chính xác `report:read` để đọc báo cáo.
- Tài khoản `suspended` phải bị từ chối **kể cả khi token còn mang authority cũ**.
- Route quản trị yêu cầu `ROLE_ADMIN`.
- Mọi route chưa đăng ký bị deny.

Legacy có voter A trả `GRANT` vì `report:read` và voter B trả `DENY` vì suspended. Nếu strategy đang là `AffirmativeBased` thì quyết định có thể **ALLOW**, mặc dù nghiệp vụ muốn DENY. Khi migrate, phải chọn policy vừa thể hiện điều kiện **đúng** vừa có test chứng minh actor bị suspended không thể truy cập.

Biểu thức logic mong muốn:

```text
allowReports(actor) =
    actor.isAuthenticated
    AND actor.hasAuthority("report:read")
    AND NOT actor.isSuspended

allowAdmin(actor) =
    actor.hasAuthority("ROLE_ADMIN")

fallback = denyAll
```

Nếu tài khoản bị khóa được xác định bởi DB/cache thay cho username, chỉ thay **nguồn trạng thái tin cậy**; không đổi ý nghĩa AND/veto.

## 6. Ví dụ tích hợp đầy đủ: Spring Security 6.x / Spring Boot 3.x

Ví dụ chạy kiểm thử `SecurityFilterChain` thực bằng `MockMvc`, với custom `AuthorizationManager` viết dưới dạng lambda và `AuthorizationManagers.allOf`. Dùng Java 17+, JUnit 5 và Spring Security Test. Không cần các lớp `AccessDecisionManager` cũ.

### 6.1. Dependency cho module Gradle đã có Spring Boot plugin/BOM

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu runtime đã có các starter, chỉ bổ sung phần còn thiếu; không khai báo trùng. Với Spring Boot 3.x, tránh tự pin phiên bản Security khác BOM. Test sau chỉ dùng GET nên CSRF protection không phải nguyên nhân gây deny; trong API thực, các thao tác đổi trạng thái còn cần xử lý CSRF khi dùng cookie/session.

Tạo **một file** `src/test/java/example/security/AuthorizationMigrationTest.java`:

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthorizationMigrationTest.App.class)
@AutoConfigureMockMvc
class AuthorizationMigrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({SecurityConfig.class, ApiController.class})
    static class App {}

    @Configuration
    @EnableWebSecurity
    static class SecurityConfig {

        @Bean
        AuthorizationManager<RequestAuthorizationContext> activeAccount() {
            // Demo rule: "suspended" đại diện account bị khóa.
            // Lambda giúp code test không override check()/authorize()
            // khác nhau giữa các nhánh Security.
            AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

            return (authentication, context) -> {
                Authentication actor = authentication.get();
                boolean active = actor != null
                    && actor.isAuthenticated()
                    && !trustResolver.isAnonymous(actor)
                    && !"suspended".equals(actor.getName());

                return new AuthorizationDecision(active);
            };
        }

        @Bean
        SecurityFilterChain apiSecurity(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> activeAccount
        ) throws Exception {

            AuthorizationManager<RequestAuthorizationContext> canReadReport =
                AuthorizationManagers.allOf(
                    activeAccount,
                    AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasAuthority("report:read")
                );

            http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .access(canReadReport)
                .requestMatchers(HttpMethod.GET, "/api/admin/status")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            );
            http.httpBasic(Customizer.withDefaults());

            return http.build();
        }
    }

    @RestController
    static class ApiController {
        @GetMapping("/api/reports/{id}")
        String report(@PathVariable long id) {
            return "report:" + id;
        }

        @GetMapping("/api/admin/status")
        String adminStatus() {
            return "admin:ok";
        }
    }

    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void scopeAndActiveAccountCanRead() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isOk())
            .andExpect(content().string("report:42"));
    }

    @Test
    @WithMockUser(username = "suspended", authorities = "report:read")
    void suspendedAccountIsDeniedEvenWithScope() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void activeButMissingScopeIsDenied() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminRoleCanCallAdminRoute() throws Exception {
        mvc.perform(get("/api/admin/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin:ok"));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminRoleDoesNotImplyReportScope() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void unmatchedRouteIsDeniedByFallback() throws Exception {
        mvc.perform(get("/api/unlisted"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy từ module Gradle tương ứng:

```bash
./gradlew test --tests "example.security.AuthorizationMigrationTest"
```

Trên Windows dùng `gradlew.bat`; với multi-project có thể cần task `:module-path:test`. **Kỳ vọng: 6 test PASS** khi dùng dependencies và cấu hình Spring Boot 3.x nêu trên. JUnit assertions xác minh HTTP status/response; đây không phải chương trình `main` có stdout cố định.

### 6.2. Đọc kết quả test để hiểu policy

| Test | Authentication | Kỳ vọng | Ý nghĩa |
| --- | --- | --- | --- |
| `scopeAndActiveAccountCanRead` | Alice, `report:read` | 200 + `report:42` | Đủ authority và không suspended |
| `suspendedAccountIsDeniedEvenWithScope` | Suspended, `report:read` | 403 | **Deny veto** vẫn thắng grant từ scope |
| `activeButMissingScopeIsDenied` | Bob, `ROLE_USER` | 403 | Active không tự tạo scope `report:read` |
| `adminRoleCanCallAdminRoute` | Admin, `ROLE_ADMIN` | 200 + `admin:ok` | `hasRole("ADMIN")` kiểm tra role prefix |
| `adminRoleDoesNotImplyReportScope` | Admin, `ROLE_ADMIN` | 403 | Role và authority riêng biệt nếu không cấu hình hierarchy |
| `unmatchedRouteIsDeniedByFallback` | Alice, `report:read` | 403 | `anyRequest().denyAll()` khóa endpoint chưa khai báo |

Lưu ý `@WithMockUser` dựng Authentication giả cho test, **không kiểm tra login/JWT/session và revocation thật**. Demo dùng username `"suspended"` là dấu hiệu trạng thái cố định để test composition; code production cần policy truy xuất account-status đáng tin cậy và xử lý lỗi repository rõ ràng.

### 6.3. Vì sao không dùng `anyOf`?

Nếu viết sai:

```java
AuthorizationManager<RequestAuthorizationContext> unsafe =
    AuthorizationManagers.anyOf(
        activeAccount,
        AuthorityAuthorizationManager
            .<RequestAuthorizationContext>hasAuthority("report:read")
    );
```

thì một người bị suspended **vẫn có `report:read`** có thể được phép vì nhánh scope cho phép (OR), dù nhánh activeAccount từ chối. `allOf` trong ví dụ chính diễn đạt đúng **cần cả hai điều kiện**. Đây là thay đổi logic quan trọng hơn việc thay tên class.

Ví dụ dùng `allOf`/`anyOf` không giải quyết tự động policy **tenant/owner**: muốn kiểm tra tài nguyên cụ thể phải kiểm tra ID/resource từ context và trusted principal, hoặc kiểm tra trong service/repository. Không dựa vào request header `X-Tenant` không được xác thực. Ngoài ra, các phiên bản Spring Security có thể có hành vi all-abstain khác với policy mong muốn; test riêng trường hợp không delegate nào ra quyết định và dùng fallback rõ ràng.

## 7. Kiểm thử migration đầy đủ ngoài ví dụ HTTP

| Rủi ro | Regression test bắt buộc |
| --- | --- |
| `AffirmativeBased` cũ cho qua dù có DENY | Trường hợp một voter grant, một voter deny; đối chiếu policy **đúng** được phê duyệt |
| `ConsensusBased` có xử lý hòa tùy biến | Số lượng grant/deny/abstain và tie, cả trường hợp không voter nào áp dụng |
| Thiếu metadata làm mọi voter abstain | URL/method không có rule phải đi vào fallback an toàn |
| Thứ tự matcher đổi | Matcher hẹp được xét trước; URL không match và dispatcher types được test |
| Role prefix/hierarchy khác | `ROLE_ADMIN`, `ADMIN`, `hasRole`, `hasAuthority` không bị hoán đổi ngữ nghĩa |
| Resource thuộc tenant khác | Deny dù có scope đúng chức năng; không tác động dữ liệu ngoài tenant |
| Method security mới chưa bật | Qua proxy: `@PreAuthorize` deny trước thân method; ca self-invocation được nhận diện |
| Giao dịch/side effect bị thay đổi | Kiểm tra DB state và outbound effects, không chỉ 403 |
| Account bị khóa/revoked | Deny dù bearer/session còn chứa authority cũ |
| Các nhánh Security khác nhau | Build/test trên version thực, vì chữ ký `check`/`authorize` có khác biệt |

Phân biệt **test policy thuần** (gọi manager trực tiếp, so sánh `isGranted()`) với **integration test** (đi qua filter chain/service proxy). Cả hai có giá trị: unit test dễ bao phủ nhiều tổ hợp phiếu; integration test chứng minh matcher và advisor thực sự được kích hoạt. Với HTTP, kiểm tra cả anonymous/fully authenticated khi hợp đồng yêu cầu; với service, verify exception tại boundary được chuyển thành HTTP response như mong muốn.

**Không nên bật legacy và modern interceptor cho cùng URL/method mà không hiểu ordering**, vì có thể bị check hai lần, thay đổi semantics hoặc khiến chẩn đoán khó khăn. Migration từng lớp với bằng chứng coverage rõ ràng sẽ ít rủi ro hơn.

## 8. Những lỗi hay gặp khi nâng cấp

### “Đổi `authorizeRequests` thành `authorizeHttpRequests` là xong”

API mới dùng `AuthorizationFilter` và `AuthorizationManager`, nhưng còn matcher, fallback, dispatcher, custom policy, method annotations, exception handling. Nếu chuỗi quyết định cũ có custom voter, chỉ đổi DSL không đảm bảo logic được mang sang.

### “Một voter deny thì chắc chắn bị từ chối”

Sai với `AffirmativeBased` nếu có voter khác grant. Nếu deny cần quyền phủ quyết, dùng AND/veto logic rõ ràng và test tổ hợp grant+deny. Đừng dịch mọi danh sách voter thành OR.

### “Abstain có nghĩa là cho phép”

`ACCESS_ABSTAIN` nghĩa là voter không quyết định. `null` ở `AuthorizationManager` cũng có thể biểu diễn abstain; quyết định cuối do wrapper/composition/fallback. Không cho phép mặc định khi không có rule khớp.

### “Dùng `hasRole('ADMIN')` tương đương `hasAuthority('ADMIN')`”

Mặc định `hasRole("ADMIN")` tìm `ROLE_ADMIN`; `hasAuthority("ADMIN")` tìm chính xác `ADMIN`. Khi nâng cấp, kiểm tra GrantedAuthority và prefix/hierarchy.

### “Spring Boot có spring-boot-starter-security là method security tự bật”

Không đúng. Cần `@EnableMethodSecurity` để áp các method annotations trong cấu hình thông thường. Test phải gọi bean Spring proxy; không dùng `new Service()` để chứng minh advice.

### “Security 7 bỏ AccessDecisionManager nên cứ thêm spring-security-access rồi dùng tiếp mã cũ mãi”

Module legacy chỉ hỗ trợ quá trình chuyển tiếp. Với code mới, viết `AuthorizationManager`/policy service; gỡ dependency khi không còn class cũ. Nếu code build lỗi khi lên 7, kiểm tra cả artifact/module **và** API signature.

### “Kiểm tra 403 là đủ”

403 có thể đến từ nhiều nơi: matcher, method security, exception handler. Khi policy gắn với mutation, test thêm DB/queue/email side effects, scope owner/tenant, và transaction boundary; không suy rằng exception tự hoàn tác các tác động đã phát.

## 9. Checklist nghiệm thu migration

- [ ] Có inventory các voter/decision manager/config attributes cũ và các route/method bị ảnh hưởng.
- [ ] Có bảng truth table cho allow/deny/abstain, tie, all-abstain và chính sách veto.
- [ ] Chọn manager built-in hoặc custom phù hợp; `anyOf`/`allOf` phản ánh **policy nghiệp vụ được chấp thuận**.
- [ ] `authorizeHttpRequests` khớp HTTP method/path, đúng thứ tự, có fallback rõ ràng; không nhầm `securityMatcher`.
- [ ] `@EnableMethodSecurity` và flags của `@Secured`/JSR-250 được cấu hình khi cần; test qua proxy.
- [ ] Quyền object/tenant và trạng thái account không mất trong quá trình thay voter.
- [ ] Có regression tests cho grant+deny, all-abstain, role prefix, suspended, unknown route, anonymous, side effects.
- [ ] Tài liệu và dependency đồng bộ đúng Spring Security 6.x hay 7.x; `spring-security-access` chỉ tồn tại khi còn legacy usage.
- [ ] Test trực tiếp trên version dự kiến deploy; gỡ adapter, voter và config cũ sau khi parity và quyền mong muốn đã được xác minh.

**Kết luận:** `AccessDecisionManager` tổng hợp kết quả từ nhiều `AccessDecisionVoter` theo một strategy; `AuthorizationManager` giúp viết quyết định quyền trực tiếp và ghép policy rõ ràng. Điều cần giữ vững khi chuyển đổi là **ai được phép thực thi hành động nào trên resource nào**, kể cả trường hợp các điều kiện bất đồng hoặc không có điều kiện nào áp dụng.

## Tài liệu chính thức để đối chiếu phiên bản

- [Spring Security 7 – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, adapters và legacy voting model.
- [Spring Security 7 – Authorization Migration](https://docs.spring.io/spring-security/reference/migration/servlet/authorization.html): module `spring-security-access` và hướng nâng cấp.
- [Spring Security 7 – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `AuthorizationFilter`, thứ tự matcher và DSL.
- [Spring Security 7 – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, trước/sau method interceptor.
- [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): tài liệu giúp đọc code đang dùng 6.x.
- [Spring Security 6.5 – AuthorizationManager Java API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `check`/`authorize` ở 6.x.
