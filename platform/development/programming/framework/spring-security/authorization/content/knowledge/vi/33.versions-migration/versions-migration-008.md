# WebExpressionAuthorizationManager khi chuyển cấu hình SpEL cũ

## 1. Bối cảnh và mục tiêu

Khi nâng cấp ứng dụng Spring Security Servlet từ cách cấu hình `authorizeRequests`/`antMatchers`/`access(String)` sang `authorizeHttpRequests`, một khó khăn là bảo toàn các quy tắc **Spring Expression Language (SpEL)** đã dùng để quyết định quyền trên HTTP request. Ví dụ cũ có thể là `hasRole('ADMIN') and hasAuthority('report:read')`, so sánh tên đăng nhập với biến trong URL hoặc gọi một Spring bean để ra quyết định. API hiện đại sử dụng **`AuthorizationManager`**; không còn giả định rằng DSL `.access(...)` tiếp nhận trực tiếp chuỗi SpEL.

`WebExpressionAuthorizationManager` chính là adapter để **đánh giá biểu thức web SpEL cũ trong hợp đồng `AuthorizationManager<RequestAuthorizationContext>`**. Nó giúp chuyển đổi theo từng rule, giữ hành vi đang cần trong lúc xây dựng chính sách dễ kiểm thử hơn. Tuy nhiên, thay API không bảo đảm tự động giữ nguyên ý nghĩa role, path matching, bean resolver, permission evaluator, thứ tự rule hay quyền đối với từng bản ghi.

Sau bài học, bạn cần:

1. Nhận ra đường đi legacy và đường đi mới của một quyết định authorization Servlet.
2. Chuyển một rule `access("...")` sang `access(new WebExpressionAuthorizationManager("..."))` **đúng phiên bản**.
3. Biết khi nào dùng builder trong Spring Security 7+, khi nào cần cấu hình expression handler hoặc thay SpEL bằng `AuthorizationManager` cụ thể.
4. Kiểm thử tương đương **cho phép/từ chối** trước–sau nâng cấp, gồm HTTP method, path, authorities, bean, dispatch, CSRF và tài nguyên ngoài phạm vi.
5. Giữ nguyên nguyên tắc **deny by default**, không chuyển mọi rule phức tạp thành `authenticated()` để cấu hình chạy được.

Phạm vi của bài là **Spring Security Servlet / HttpSecurity**, không phải WebFlux (WebFlux có các loại `AuthorizationContext` và filter khác) hay `@PreAuthorize` ở method security. Ví dụ Spring dưới đây là những **đoạn tích hợp**, cần dependency/configuration/controller của dự án; chương trình Java thuần ở mục 11 là mẫu kiểm tra ma trận ý nghĩa, không chạy engine SpEL thật.

## 2. Từ FilterSecurityInterceptor sang AuthorizationFilter

Đường legacy thường gắn URL rules với `FilterSecurityInterceptor` và hệ thống metadata source, `ConfigAttribute`, `AccessDecisionManager`, voter hoặc biểu thức. Đường mới sử dụng `AuthorizationFilter` và `AuthorizationManager<RequestAuthorizationContext>` để quyết định dựa trên request:

~~~text
Cấu hình legacy (Spring Security 5.x và các nhánh tương thích)
  authorizeRequests()
    .antMatchers("/reports/**")
    .access("hasRole('ADMIN') and hasAuthority('report:read')")
       |
       v
  FilterSecurityInterceptor + cấu hình expression/voter

Cấu hình mới (Spring Security 6.x/7.x, Servlet)
  authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**")
    .access(new WebExpressionAuthorizationManager(
        "hasRole('ADMIN') and hasAuthority('report:read')")))
       |
       v
  AuthorizationFilter
       |
       v
  RequestMatcherDelegatingAuthorizationManager
       |
       v
  WebExpressionAuthorizationManager
       |
       v
  SpEL trên RequestAuthorizationContext -> GRANTED/DENIED
~~~

Các điểm cần giữ đúng:

- **`requestMatchers` chọn rule nào**, còn **`AuthorizationManager` quyết định cho phép hay từ chối** đối với request đã khớp. Một matcher sai có thể khiến biểu thức đúng không bao giờ chạy.
- `AuthorizationFilter` truyền một **`Supplier<Authentication>`** và thông tin request đến manager. Việc lấy authentication có thể được hoãn đối với `permitAll`/`denyAll`.
- Trong DSL `authorizeHttpRequests`, **rule đầu tiên khớp request được dùng**. Rule `/**` hoặc `anyRequest()` đặt quá sớm có thể che mất rule chặt chẽ phía sau.
- `WebExpressionAuthorizationManager` không cấp authority mới. Nó **kiểm tra** các authority hiện diện trong `Authentication` mà cơ chế đăng nhập/JWT đã tạo.
- Chuyển đổi ở request layer không thay thế authorization ở service/repository: ai có thể vào endpoint không mặc nhiên có quyền trên tất cả `documentId` hoặc tenant.

## 3. Bản đồ API theo phiên bản: tránh trộn ví dụ 6.x với 7.x

| Chủ đề | Kiểu cũ | Hướng 6.x | Hướng 7.x |
| --- | --- | --- | --- |
| URL DSL | `authorizeRequests` | `authorizeHttpRequests` | `authorizeHttpRequests`; API cũ đã bị loại bỏ |
| Matcher | `antMatchers`/`mvcMatchers` theo cấu hình cũ | `requestMatchers` với overload/matcher phù hợp | `requestMatchers`, lưu ý matcher/servlet path của phiên bản hiện tại |
| Cú pháp biểu thức URL | `.access("hasRole('ADMIN')")` | `.access(new WebExpressionAuthorizationManager("hasRole('ADMIN')"))` | Dùng constructor tương tự hoặc builder `withDefaults().expression(...)` |
| Nhiều biểu thức chung handler | Legacy expression handler | `new WebExpressionAuthorizationManager(...)` và nếu cần `setExpressionHandler(...)` | `WebExpressionAuthorizationManager.withDefaults()` hoặc `withExpressionHandler(...)`; setter cũ bị deprecate |
| Điều kiện đơn giản | Chuỗi SpEL như `hasRole('ADMIN')` | `.hasRole("ADMIN")`, `.hasAuthority("...")` | Tương tự, ưu tiên API type-safe |
| Bean policy phức tạp | `@webPolicy.check(authentication, request)` trong SpEL | `.access((authentication, context) -> new AuthorizationDecision(...))` hoặc handler có bean resolver | Ưu tiên manager trực tiếp; builder bean hỗ trợ tham chiếu bean trong biểu thức |

**Mốc API:** `WebExpressionAuthorizationManager` có từ Spring Security 5.8. `WebExpressionAuthorizationManager.Builder` và các factory `withDefaults()`/`withExpressionHandler(...)` được bổ sung ở **7.0**, nên **không copy builder vào code đang dùng Spring Security 6.3/6.4/6.5**. Trong 6.5 có `setExpressionHandler(...)`; ở 7.0 setter này bị đánh dấu deprecated để ưu tiên builder. Spring Security 7 cũng thay đổi một số API khác của `AuthorizationManager`, ví dụ bỏ `check` để dùng `authorize`: khi implement manager thủ công, biên dịch theo đúng version.

Dựa trên **dependency graph thực**, không suy phiên bản Spring Security chỉ từ ví dụ trên mạng hay số phiên bản Spring Boot. Dùng BOM/plugin quản lý dependency và kiểm xung đột transitive trước khi chuyển.

## 4. Chuyển một biểu thức SpEL cũ sang `WebExpressionAuthorizationManager`

Giả sử hệ thống cũ có trang báo cáo chỉ cho người vừa là `ROLE_ADMIN` vừa có authority `report:read`.

### Trước: kiểu `authorizeRequests` (ví dụ legacy, không áp dụng nguyên xi cho 7.x)

~~~java
// Mảnh cấu hình legacy Spring Security 5.x
http.authorizeRequests()
    .antMatchers("/reports/**")
        .access("hasRole('ADMIN') and hasAuthority('report:read')")
    .anyRequest().authenticated();
~~~

Đây là mảnh lịch sử để so sánh ý nghĩa. `and` yêu cầu cả **hai** điều kiện. Cùng chuỗi với `or` sẽ cho phép actor chỉ có một quyền, nên thay dấu nối là thay đổi chính sách.

### Sau: Java config cho Spring Security 6.x và 7.x

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.expression.WebExpressionAuthorizationManager;

@Configuration
class WebAuthorizationConfig {
    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/reports/**").access(
                new WebExpressionAuthorizationManager(
                    "hasRole('ADMIN') and hasAuthority('report:read')")
            )
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Điểm cần hiểu:

- `requestMatchers("/reports/**")` chọn URL phù hợp. Nếu rule cũ còn ràng buộc `HttpMethod.GET`, cần chỉ rõ HTTP method trong matcher mới; đừng mở rule cho POST/DELETE.
- `.access(...)` ở đây nhận `AuthorizationManager<RequestAuthorizationContext>`, không nhận chuỗi cũ. `new WebExpressionAuthorizationManager(expression)` parse và đánh giá biểu thức web.
- `hasRole('ADMIN')` thường kiểm `ROLE_ADMIN` theo tiền tố mặc định; `hasAuthority('report:read')` kiểm đúng chuỗi. Converter JWT/role hierarchy có thể ảnh hưởng authority thực tế; phải test cả nguồn authentication.
- `.anyRequest().denyAll()` là lựa chọn fail-closed cho ví dụ. Nếu hợp đồng cũ là các URL khác chỉ cần authentication, ghi lại khác biệt trước khi quyết định dùng `authenticated()`. **Migrate tương đương trước; hardening chủ động sau và kiểm thử riêng.**
- Code snippet trên chỉ thiết lập authorization; web app thực tế cần thêm lựa chọn form login/OAuth2 resource server, CSRF, CORS, session management, entry point và controller. Cấm dùng snippet này làm “toàn bộ config production” mà không xét cách authentication hiện có.

### Biểu thức đơn giản nên chuyển thành DSL type-safe

Không cần giữ SpEL nếu điều kiện đơn giản:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/docs/**").hasAuthority("SCOPE_documents.read")
    .requestMatchers("/public/**").permitAll()
    .anyRequest().denyAll()
);
~~~

Bên cạnh việc giảm lỗi viết sai chuỗi SpEL, API DSL làm rõ cấu trúc quyền. Với rule yêu cầu **nhiều quyền đồng thời**, chọn manager kết hợp (nếu version hỗ trợ) hoặc policy riêng thay vì đổi `and` thành `hasAnyAuthority`/`hasAnyRole` (các API “any” mang nghĩa OR). Đặc biệt, không dùng `authenticated()` thay `hasRole('ADMIN')` chỉ để tránh cấu hình converter.

## 5. Spring Security 7+: builder giúp quản lý nhiều biểu thức

Bắt đầu từ 7.0, có thể tạo các manager qua builder:

~~~java
// Spring Security 7.0+; lớp Builder không có ở 6.x.
WebExpressionAuthorizationManager.Builder expressions =
    WebExpressionAuthorizationManager.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/ops/**").access(
        expressions.expression("hasRole('OPS') and isFullyAuthenticated()")
    )
    .requestMatchers("/users/{name}").access(
        expressions.expression("#name == authentication.name")
    )
    .anyRequest().denyAll()
);
~~~

`withDefaults()` tạo builder dùng expression handler web mặc định; `expression(String)` tạo manager cho từng biểu thức. Việc sử dụng builder **không** biến biểu thức sai thành đúng, không tự ràng buộc role/tenant và không làm rule cũ an toàn hơn. Lợi ích chủ yếu là gom điểm cấu hình handler và làm đường migration thuận tiện.

Nếu expression cần tham chiếu Spring bean qua `@policyBean`, hướng dẫn 7.x khuyên **publish builder thành Spring bean** để Spring cung cấp bean resolution:

~~~java
// Spring Security 7.0+: mảnh cấu hình; cần bean reportPolicy.
@Bean
WebExpressionAuthorizationManager.Builder webExpressions() {
    return WebExpressionAuthorizationManager.withDefaults();
}

@Bean
SecurityFilterChain web(HttpSecurity http,
        WebExpressionAuthorizationManager.Builder expressions)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/reports/**").access(
            expressions.expression(
                "hasAuthority('report:read') and "
                + "@reportPolicy.canView(authentication, request)"
            )
        )
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

`reportPolicy.canView(Authentication, HttpServletRequest)` trong ví dụ là **hợp đồng của bean ứng dụng**, phải hiện thực an toàn và trả boolean. Đảm bảo bean tên `reportPolicy` thực sự có trong context, resolver được nối đúng và không dựa vào query/header chưa tin cậy làm bằng chứng quyền. Không copy hai method `web(...)`/`webSecurityFilterChain(...)` của các ví dụ vào cùng app như hai `SecurityFilterChain` vô tình cùng áp một phạm vi; mỗi snippet là một **phương án độc lập**.

Với Spring Security 6.5, nếu thật sự phải giữ bean reference trong SpEL, có thể cấu hình `DefaultHttpSecurityExpressionHandler` đúng kiểu `RequestAuthorizationContext` và gắn với manager:

~~~java
// Mảnh code Spring Security 6.5; cần ApplicationContext context.
DefaultHttpSecurityExpressionHandler handler =
    new DefaultHttpSecurityExpressionHandler();
handler.setBeanResolver(new BeanFactoryResolver(context));

WebExpressionAuthorizationManager manager =
    new WebExpressionAuthorizationManager(
        "@reportPolicy.canView(authentication, request)");
manager.setExpressionHandler(handler);
~~~

Các import tương ứng là `org.springframework.security.web.access.expression.DefaultHttpSecurityExpressionHandler`, `org.springframework.context.expression.BeanFactoryResolver` và `org.springframework.security.web.access.expression.WebExpressionAuthorizationManager`. Đây là giải pháp migration có chủ đích; setter `setExpressionHandler` bị deprecated ở 7.x, nên với 7.0+ dùng `withExpressionHandler(handler)` hoặc builder bean. Chỉ cấu hình handler sau khi đã xác định những tùy chỉnh cũ thực sự cần giữ.

**Điểm dễ sai:** `DefaultWebSecurityExpressionHandler` của hệ legacy làm việc với `FilterInvocation`; `DefaultHttpSecurityExpressionHandler` dành cho `RequestAuthorizationContext` của manager mới. Không ép kiểu hoặc bê nguyên cấu hình handler cũ sang manager mới khi generic context khác nhau. Tách lại role hierarchy, permission evaluator, bean resolver, trust resolver và các custom root methods theo API đúng phiên bản rồi kiểm thử.

## 6. Khi nào nên bỏ SpEL và viết `AuthorizationManager`?

Spring Security khuyến nghị ưu tiên manager hoặc API type-safe khi có thể. Một expression gọi bean như:

~~~java
// Legacy: một biểu thức trộn role với business policy
.access("hasRole('REVIEWER') and @reportPolicy.canView(authentication, request)")
~~~

có thể chuyển thành manager cụ thể, có dependency injection và unit test rõ:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authentication.*;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Mảnh Java Spring Security, cần interface ReportPolicy thật.
final class ReportAccessManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ReportPolicy policy;

    ReportAccessManager(ReportPolicy policy) {
        this.policy = policy;
    }

    // Phiên bản dùng lambda ở mục dưới tương thích cách gọi .access(...) 6.x/7.x.
    // Với class implements trực tiếp, signature check/authorize cần điều chỉnh theo version.
    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {
        Authentication actor = authentication.get();
        boolean reviewer = actor.getAuthorities().stream()
            .anyMatch(a -> "ROLE_REVIEWER".equals(a.getAuthority()));
        return new AuthorizationDecision(
            reviewer && policy.canView(actor, context.getRequest()));
    }
}
~~~

**Quan trọng về version:** ví dụ `check(...)` ở trên dùng contract 6.x (ở 7.x, `AuthorizationManager#check` đã bị loại khỏi API; implement `authorize(...)` với kiểu `AuthorizationResult` phù hợp). Để tránh lẫn 6.x/7.x khi đang migrate, có thể dùng **lambda** trong DSL cho manager nhỏ, là dạng thích hợp cho cả hai thế hệ:

~~~java
// ReportPolicy là bean đã inject; boolean canView(Authentication, HttpServletRequest)
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").access((authentication, context) -> {
        var actor = authentication.get();
        boolean reviewer = actor.getAuthorities().stream()
            .anyMatch(a -> "ROLE_REVIEWER".equals(a.getAuthority()));
        return new AuthorizationDecision(
            reviewer && reportPolicy.canView(actor, context.getRequest()));
    })
    .anyRequest().denyAll()
);
~~~

Lambda trên không phụ thuộc tên phương thức abstract khi biên dịch với đúng version của Spring Security; khi xây dựng manager lớp riêng, **không** sao chép ví dụ `check(...)` 6.x sang 7.x. Việc gọi `policy.canView` phải thực sự kiểm scope dữ liệu. Không chỉ làm `return new AuthorizationDecision(true)` để cho cấu hình chạy qua.

Ưu tiên class manager riêng khi cần quyết định nhiều bước, I/O tới policy service, validation input, caching, audit và kết hợp điều kiện AND/OR. Với logic duy nhất như `hasRole('ADMIN')`, DSL `hasRole` đơn giản hơn.

### Vì sao không giữ mãi SpEL?

- Tránh sai tên bean/biến runtime, ít lỗi đổi method signature hay bean resolver.
- Có điểm tập trung cho policy domain, typed input/output và unit test.
- Kiểm được rõ cách lấy principal từ `Supplier<Authentication>` và quyền trên đối tượng.
- Dễ review permission matrix khi migrate nhiều route.
- Hạn chế nguy cơ cấu hình một biểu thức động từ dữ liệu người dùng (không bao giờ đưa SpEL do client điều khiển vào `WebExpressionAuthorizationManager`).

Giữ SpEL cho giai đoạn chuyển đổi hoặc khi nó làm chính sách rõ ràng và đã được test; quyết định giữ hay viết lại căn cứ vào độ phức tạp, không dựa vào sở thích cú pháp.

## 7. Bảo toàn đúng ngữ nghĩa của biểu thức web

### 7.1. `hasRole`, `hasAuthority` và nguồn quyền

- `hasRole('ADMIN')` theo mặc định tìm `ROLE_ADMIN`; không dùng `hasRole('ROLE_ADMIN')` để “chữa” sai prefix.
- `hasAuthority('SCOPE_reports.read')` tìm **đúng chuỗi** authority. OAuth scope của JWT thường được ánh xạ thành `SCOPE_...` nếu cấu hình chuẩn của resource server còn giữ.
- `hasAnyRole('ADMIN','EDITOR')` là OR; `hasRole('ADMIN') and hasRole('EDITOR')` là AND. `hasAllAuthorities` nếu có ở DSL mới cũng cần kiểm version/chức năng cụ thể.
- Role hierarchy có thể khiến `ROLE_ADMIN` bao hàm `ROLE_EDITOR`, nhưng tùy chỉnh hierarchy cũ không mặc nhiên được đưa sang mọi expression handler mới. So sánh decision trước–sau bằng user có role kế thừa.
- JWT hợp lệ chưa đủ: `GrantedAuthority` còn phụ thuộc converter. Test cả token chỉ có scope và token có role; đừng gán authorities thẳng trong mọi test rồi bỏ qua converter thật.

### 7.2. `authentication`, `principal` và trạng thái xác thực

`authentication` là `Authentication` do Spring Security cung cấp trong evaluation context; `principal` là principal của nó. Các helper như `isAuthenticated()`, `isAnonymous()`, `isRememberMe()`, `isFullyAuthenticated()` có thể mang ý nghĩa khác nhau. `isFullyAuthenticated()` loại trừ remember-me/anonymous theo trust resolver; đổi thành `authenticated()` một cách máy móc có thể cho phép request mà policy cũ chặn.

Kiểm các nhóm: anonymous, form login, remember-me, bearer token, token không đủ scope, user bị khóa và `Authentication` được tạo bởi custom provider. Trong application dùng JWT stateless, remember-me có thể không liên quan, nhưng vẫn nên ghi rõ contract của route cũ trước khi bỏ điều kiện.

### 7.3. Biến trong URL

Với một matcher hỗ trợ trích xuất biến đường dẫn, biểu thức có thể so tên:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/profiles/{name}").access(
        new WebExpressionAuthorizationManager(
            "#name == authentication.name"))
    .anyRequest().denyAll()
);
~~~

`#name` trong biểu thức là **URI template variable** do matcher đưa vào context, **không phải** query parameter `?name=...` và cũng không phải magic argument của controller. Test với `/profiles/alice`, `/profiles/bob`, encoded path và case sensitivity theo matcher đang dùng. Nếu chuyển từ `antMatchers` sang `requestMatchers`/`PathPatternRequestMatcher` mà cách trích biến thay đổi, biểu thức có thể luôn false hoặc dùng biến khác.

Lưu ý so sánh `authentication.name` với path chỉ phù hợp khi path thực sự đại diện cho username đã chuẩn hóa. Với ID tài nguyên như `/documents/101`, **đừng** thay policy sở hữu bằng so chuỗi; cần tra cứu người sở hữu/tenant/ACL ở service.

### 7.4. Request metadata và bean policy

Một expression legacy có thể dùng `request.method`, `request.remoteAddr`, `hasIpAddress(...)` hay `@webPolicy.check(authentication, request)`. Khi migrate phải xem lại:

- `request` ở web expression là `HttpServletRequest` của request được bảo vệ, không phải DTO, method argument hay principal.
- Nếu sau proxy/load balancer, `remoteAddr` hoặc `X-Forwarded-For` cần cấu hình tin cậy chính xác; **không** dùng header do client tự khai làm quyền quản trị.
- Tham chiếu `@bean` chỉ hoạt động khi expression handler được gắn bean resolver. Nếu chuyển sang builder hoặc manager trực tiếp, phải khẳng định bean thực sự được gọi.
- `hasPermission(...)` cần `PermissionEvaluator` có contract đúng. Khi chuyển từ `DefaultWebSecurityExpressionHandler` sang `DefaultHttpSecurityExpressionHandler`, phải nối lại evaluator và test quyền trên đối tượng.
- Không đưa `@PreAuthorize("#documentId...")` của method security vào URL expression với kỳ vọng tự có method parameter `#documentId`; đó là hai evaluation context khác nhau.

### 7.5. Biểu thức boolean và deny-by-default

Chuỗi `hasRole('ADMIN') and hasAuthority('report:read')` cho phép **chỉ khi cả hai đúng**. Đặc biệt chú ý ngoặc khi kết hợp `and`/`or`:

~~~text
(hasRole('ADMIN') or hasRole('AUDITOR')) and hasAuthority('report:read')
~~~

không tương đương với

~~~text
hasRole('ADMIN') or (hasRole('AUDITOR') and hasAuthority('report:read'))
~~~

Biểu thức thứ hai cho phép ADMIN bỏ qua `report:read`. Việc đổi ưu tiên toán tử hoặc bỏ ngoặc trong migration là thay đổi bảo mật. Tương tự, `permitAll or ...` luôn true, và `denyAll and ...` luôn false. Không dùng `permitAll` làm “fallback” cho expression parse lỗi.

## 8. Matcher, filter chain và dispatch có thể đổi kết quả dù SpEL giữ nguyên

Bảo toàn text của expression là **chưa đủ**. Decision thực tế là kết quả của nhiều tầng:

~~~text
HTTP request
  ├─ SecurityFilterChain nào match request?
  ├─ Matcher/rule đầu tiên trong authorizeHttpRequests?
  ├─ Authentication được tạo bởi cơ chế nào?
  ├─ Manager/expression kiểm authorities nào?
  ├─ Dispatcher type REQUEST/FORWARD/ERROR/ASYNC?
  └─ Service/object policy có kiểm tài nguyên thật?
~~~

### Thứ tự matcher

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/public/**").permitAll()
    .requestMatchers("/admin/**").access(
        new WebExpressionAuthorizationManager(
            "hasRole('ADMIN') and isFullyAuthenticated()"))
    .anyRequest().denyAll()
);
~~~

Rule cụ thể phải đặt trước rule rộng hơn. Nếu `/admin/**` đứng trước `/admin/public/**` thì rule public sẽ không được chọn. Khi có nhiều `SecurityFilterChain` với `securityMatcher(...)` và `@Order`, phải kiểm cả **chain selection** trước khi xét rule bên trong.

### HTTP method và servlet path

Nếu legacy chỉ bảo vệ `GET /reports/**` bằng expression, đừng vô tình áp rule tương tự cho POST/DELETE, hoặc ngược lại mở quyền ghi vì dùng matcher thiếu method. Với nhiều servlet hoặc servlet mapping khác, cần matcher có servlet path rõ ràng theo phiên bản; không coi `antMatchers`, `mvcMatchers`, regex và `PathPatternRequestMatcher` là luôn tương đương. Spring Security 7 có hướng dẫn dùng `PathPatternRequestMatcher` trong nhiều trường hợp; kiểm matcher tương thích controller, context path, trailing slash, URL encoding, case và dispatcher.

### Dispatch và static resources

`AuthorizationFilter` kiểm authorization trên các dispatch phù hợp, bao gồm có thể cả `FORWARD`/`ERROR`; một view rendering hoặc error handler có thể gặp 403 sau migrate. Nếu đặc tả cho phép, cấu hình rõ dispatcher types:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD, DispatcherType.ERROR).permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Đây là **lựa chọn theo yêu cầu ứng dụng**: không tự permit mọi dispatch khi endpoint lỗi có thể sinh dữ liệu nhạy cảm. Thường ưu tiên `permitAll` cho static resources hơn `web.ignoring()` vì ignoring bỏ cả security filter chain và các security headers.

### CSRF, 401/403 và authentication

Khi một integration test POST nhận 403, nguyên nhân có thể là CSRF token thiếu, **chưa đến expression**. Khi GET nhận 401, có thể chưa xác thực, cũng không chứng minh expression sai. Phân biệt 401/403 theo entry point, bearer token authentication và policy; test qua request method + credentials hợp lệ + CSRF phù hợp. Đừng tắt CSRF toàn ứng dụng chỉ vì migration test 403.

## 9. Các lỗi chuyển đổi điển hình và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm và sửa |
| --- | --- | --- |
| `.access("...")` không compile | DSL mới nhận `AuthorizationManager` | Dùng `new WebExpressionAuthorizationManager("...")` hoặc manager type-safe |
| `withDefaults()` không tìm thấy | Đang dùng Spring Security 6.x | Dùng constructor của 6.x; chỉ dùng builder trên 7.0+ |
| `setExpressionHandler(...)` deprecated | Đang ở 7.x | Chuyển sang builder `withExpressionHandler` hoặc `withDefaults` khi phù hợp |
| Expression gọi `@bean` lỗi | Bean resolver chưa có/bean tên sai | Kiểm handler và Spring bean context; ưu tiên gọi bean trực tiếp qua manager |
| Không dùng được handler cũ | `FilterInvocation` khác `RequestAuthorizationContext` | Dùng `DefaultHttpSecurityExpressionHandler` cho WebExpressionAuthorizationManager |
| Người có `ROLE_ADMIN` bị 403 | Converter, hierarchy hoặc prefix khác | Xem `Authentication.getAuthorities()` và role hierarchy thực tế |
| User không đủ quyền lại được qua | Đổi `and` thành `or`, matcher rộng hoặc fallback `authenticated()` | Test negative với từng quyền thiếu; so thứ tự matcher |
| `#name` không resolve | Matcher không trích URI template variable | Sử dụng matcher phù hợp và test đường dẫn thực |
| Controller test pass nhưng truy cập chéo tenant | Chỉ kiểm URL-level authority | Thêm policy/service/query ràng buộc tài nguyên |
| 403 khi render error/view | Authorization chạy trên dispatch khác | Kiểm dispatcher types, không tự mở rộng tùy tiện |
| Cùng URL có lúc 200, lúc 403 | Nhiều filter chains/role hierarchy/dispatch khác | Ghi lại chain được chọn, matcher đầu tiên và principal |
| Test chỉ cho admin pass | Thiếu case denial, anonymous hoặc method khác | Ma trận test gồm allow/deny và side effects |

Một cấu hình migrate an toàn không chỉ “khởi động được”. Cần chứng minh mỗi route nhận **cùng tập request được phép** theo hợp đồng, hoặc có thay đổi security policy đã được review rõ.

## 10. Ma trận test trước–sau cho rule có nhiều điều kiện

Giả sử rule gốc:

~~~text
GET /reports/**:
    hasRole('ADMIN') and hasAuthority('report:read')
Other routes:
    denyAll
~~~

Tạo tối thiểu các actor:

| Actor/authority | `ROLE_ADMIN` | `report:read` | GET `/reports/2026` | Lý do |
| --- | --- | --- | --- | --- |
| Alice | Có | Có | ALLOW | Đúng cả hai quyền |
| Bob | Có | Không | DENY | Admin không tự thay `report:read` |
| Carol | Không | Có | DENY | Chỉ có permission không đủ role |
| Dave | Không | Không | DENY | Thiếu cả hai |
| Anonymous | Không | Không | DENY/401 theo API | Không có authentication được chấp nhận |
| Alice nhưng `/admin/**` | Có | Có | DENY | Không match `/reports/**` |
| Alice nhưng POST cùng path | Có | Có | Phụ thuộc matcher có ràng buộc method | Phải ghi rõ hợp đồng cũ và mới |

Với chính sách GET-only, thêm matcher `.requestMatchers(HttpMethod.GET, "/reports/**")`. Test `POST` bị từ chối theo `anyRequest().denyAll()`. Nếu policy cũ áp dụng mọi HTTP method, đừng đổi sang GET-only mà không có quyết định nghiệp vụ.

Đối với một expression có bean `@reportPolicy.canRead(authentication, request)`, ngoài các tổ hợp role/authority còn cần case **cùng role nhưng tài liệu thuộc tenant khác**, quyền của user bị thu hồi, resource không tồn tại, internal policy service lỗi và matcher nhận URI encoded. Negative case phải assert response **và** không có side effect.

## 11. Java 17 độc lập: tự kiểm ma trận bảo toàn AND/OR

Đoạn này minh họa việc khóa expected decisions trước khi đổi rule. Nó **không thực thi Spring Security, SpEL hay HTTP matcher thật**, nên chỉ là bài tập về ý nghĩa boolean. Việc bảo toàn cấu hình thực phải được xác minh bằng `MockMvc` ở mục tiếp theo.

Lưu thành `PolicyMatrixDemo.java`, chạy:

~~~bash
javac PolicyMatrixDemo.java
java PolicyMatrixDemo
~~~

Code Java 17+:

~~~java
import java.util.List;
import java.util.Set;

public class PolicyMatrixDemo {
    record Actor(String name, Set<String> authorities) {}

    static boolean hasRole(Actor actor, String role) {
        return actor != null &&
            actor.authorities().contains("ROLE_" + role);
    }

    static boolean hasAuthority(Actor actor, String authority) {
        return actor != null &&
            actor.authorities().contains(authority);
    }

    static boolean legacyAnd(Actor actor) {
        return hasRole(actor, "ADMIN")
            && hasAuthority(actor, "report:read");
    }

    static boolean migratedAnd(Actor actor) {
        boolean admin = hasRole(actor, "ADMIN");
        boolean canRead = hasAuthority(actor, "report:read");
        return admin && canRead;
    }

    static boolean accidentalOr(Actor actor) {
        return hasRole(actor, "ADMIN")
            || hasAuthority(actor, "report:read");
    }

    public static void main(String[] args) {
        List<Actor> actors = List.of(
            new Actor("Alice", Set.of("ROLE_ADMIN", "report:read")),
            new Actor("Bob", Set.of("ROLE_ADMIN")),
            new Actor("Carol", Set.of("report:read")),
            new Actor("Dave", Set.of())
        );

        int agreements = 0;
        for (Actor actor : actors) {
            boolean expected = legacyAnd(actor);
            boolean actual = migratedAnd(actor);
            if (expected != actual) {
                throw new AssertionError("Mismatch for " + actor.name());
            }
            agreements++;
        }

        System.out.println("matched=" + agreements);
        System.out.println("Alice=" + migratedAnd(actors.get(0)));
        System.out.println("Bob=" + migratedAnd(actors.get(1)));
        System.out.println("Carol=" + migratedAnd(actors.get(2)));
        System.out.println("Dave=" + migratedAnd(actors.get(3)));
        System.out.println("OR-regression-Bob=" + accidentalOr(actors.get(1)));
    }
}
~~~

Stdout chính xác:

~~~text
matched=4
Alice=true
Bob=false
Carol=false
Dave=false
OR-regression-Bob=true
~~~

`OR-regression-Bob=true` cho thấy một thay đổi tưởng nhỏ từ AND sang OR sẽ cho Bob vào dù thiếu `report:read`. Ma trận này là cách tư duy cần áp dụng với security test thực: trước khi rewrite, lưu expected decisions, sau đó xác nhận mỗi case vẫn đúng. Không coi chương trình này là bằng chứng Spring Security thực tế đã bảo toàn expression.

## 12. Spring Security integration test: kiểm đường dây thật

### 12.1. MockMvc phải kiểm DSL + filter chain + expression

Ví dụ **khung test Spring Boot + Spring Security Test**, giả định app có `GET /reports/2026` trả 200, bean `SecurityFilterChain` áp rule mục 4, và `MockMvc` đã nối security filters:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MigratedExpressionAuthorizationTest {
    @Autowired MockMvc mvc;

    @Test
    void adminWithReadAuthorityCanAccess() throws Exception {
        mvc.perform(get("/reports/2026")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ROLE_ADMIN"),
                    new SimpleGrantedAuthority("report:read"))))
            .andExpect(status().isOk());
    }

    @Test
    void adminWithoutReadAuthorityIsDenied() throws Exception {
        mvc.perform(get("/reports/2026")
                .with(user("bob").authorities(
                    new SimpleGrantedAuthority("ROLE_ADMIN"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithoutAdminRoleIsDenied() throws Exception {
        mvc.perform(get("/reports/2026")
                .with(user("carol").authorities(
                    new SimpleGrantedAuthority("report:read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Các static imports cần có: `MockMvcRequestBuilders.get`; `SecurityMockMvcRequestPostProcessors.user`; `MockMvcResultMatchers.status`; `@Test` của JUnit Jupiter; `@SpringBootTest` và `@AutoConfigureMockMvc` của Spring Boot Test; `SimpleGrantedAuthority` của Spring Security. Đây không phải class Java độc lập vì còn controller và Spring context thật.

Đừng cấu hình `@WithMockUser(roles={"ADMIN"}, authorities={"report:read"})` theo thói quen: `roles` và `authorities` không nên được trộn như cách này; hãy dùng `user(...).authorities(...)` để chủ động khai báo **tất cả** authority mong đợi. Test trạng thái HTTP thật phải có route/controller hợp lệ, nếu không `404` do route không tồn tại có thể bị hiểu nhầm là authorization denial.

### 12.2. Thêm test cho path variables và bean

Nếu rule dùng `#name == authentication.name`, test:

- Alice GET `/profiles/alice` → cho phép.
- Alice GET `/profiles/bob` → từ chối.
- Alice GET `/profiles/%61lice` → kết quả theo matcher/encoding của ứng dụng, không tự suy từ chuỗi raw.
- Thêm negative case khi context không có variable mong đợi.

Nếu rule dùng `@reportPolicy.canView(...)`, dùng policy bean thật hoặc test double có ghi nhận invocation (không mock luôn kết quả allow). Xác nhận bean được gọi, resource ID và tenant truyền đúng, policy deny khi owner khác, và lỗi policy không biến thành `permitAll`.

### 12.3. Kiểm authentication thật và security context

MockMvc `user(...)` là test request với `Authentication` giả; nó kiểm authorization logic sau khi principal đã có, **không** xác minh JWT signature, issuer, audience, claim mapping hoặc login filter thực. Nếu ứng dụng dùng OAuth2 resource server, thêm test với decoder/token phù hợp để chứng minh authority thực tế. Nếu thêm CSRF rule hoặc POST/PATCH/DELETE, cấp CSRF token hợp lệ khi mục tiêu là kiểm authorization, và có test CSRF riêng.

### 12.4. Kiểm biến thể framework ảnh hưởng semantics

- Một bộ test ứng với version cũ, một bộ sau migrate, cùng case matrix và expected decisions.
- Các matcher overlap `/reports/**` với `/reports/public/**`, nhiều filter chains và error/forward dispatch.
- Role hierarchy, custom prefix, principal type, anonymous, remember-me, JWT scopes, bean policy và evaluator nếu đang dùng.
- Case “cả hai điều kiện đúng”, “chỉ một đúng”, “không điều kiện nào đúng”, unknown path, wrong HTTP method và query/tenant manipulation.
- Với data access, kiểm cả repository state và response; quyết định URL-level đúng không có nghĩa ownership check đúng.

## 13. Checklist migration theo thứ tự an toàn

1. **Inventory** tất cả biểu thức từ `authorizeRequests`, `access(String)`, XML `intercept-url` và custom handlers. Ghi matcher, HTTP method, servlet path, filter chain, expression, policy bean, role hierarchy và expected allow/deny.
2. **Khóa baseline** bằng test ma trận cho những route nhạy cảm trước khi đổi API. Ghi cả error dispatch, anonymous, exception mapping và dữ liệu ngoài tenant.
3. **Chuyển DSL** sang `authorizeHttpRequests` và `requestMatchers` phù hợp version; giữ chính xác thứ tự rule, method restriction và fail-closed default.
4. **Giữ SpEL có chủ đích** bằng `new WebExpressionAuthorizationManager(expression)` ở 6.x/7.x. Không dùng `withDefaults()`/`Builder` trong 6.x. Với 7.x có thể dùng builder nếu lợi ích thực.
5. **Tái nối custom expression handler** theo API mới: role hierarchy, permission evaluator, bean resolver, trust resolver, path-variable support. Đừng bê nguyên handler dành cho `FilterInvocation`.
6. **Đơn giản hóa sau khi test pass**: thay `hasRole`/`hasAuthority` thuần bằng type-safe DSL; chuyển business bean policy phức tạp sang manager riêng. Mỗi lần thay đổi lại chạy equivalence tests.
7. **Chạy kiểm thử HTTP thật** với authentication, CSRF, request matchers, dispatch và object-level authorization; kiểm deny không có side effects.
8. **Review thay đổi chính sách** nếu muốn siết quyền, đổi default `authenticated` sang `denyAll`, đổi matcher hoặc bỏ role hierarchy. Đó là thay đổi có chủ đích, phải có acceptance criteria mới, không nhập chung vào “migration không đổi hành vi”.
9. **Triển khai có quan sát**: theo dõi tỷ lệ 401/403 theo route và role một cách an toàn, audit authorization decisions, không log access token/PII. Có cơ chế rollback config theo quy trình triển khai của hệ thống.

### Checklist QA nhanh trước khi kết luận

- [ ] `SecurityFilterChain` mới chọn đúng request; matcher đầu tiên có ý nghĩa tương đương.
- [ ] Mỗi rule SpEL cũ đã được chuyển đúng sang `WebExpressionAuthorizationManager` hoặc manager rõ ràng; không tự đổi `and`/`or`.
- [ ] Cấu hình đúng version: constructor trên 6.x/7.x, builder 7.0+, không dùng deprecated setter ngoài lý do rõ.
- [ ] `hasRole`/`hasAuthority`, prefix, role hierarchy và JWT converter khớp Authentication thực tế.
- [ ] Bean references, custom PermissionEvaluator và URI variables được nối đúng.
- [ ] Method/servlet path/dispatcher type đúng; static resources và error handler hoạt động có kiểm soát.
- [ ] Anonymous, nhớ đăng nhập, scopes thiếu, role thiếu, wrong method và unknown URL đều bị xử lý đúng hợp đồng.
- [ ] CSRF/401/403 không che kết quả kiểm expression.
- [ ] Request quyền trên object ngoài tenant/owner bị từ chối dù user có authority URL-level.
- [ ] Không có SpEL expression đến từ chuỗi do client cung cấp; lỗi parse/missing bean không mở quyền.
- [ ] Trước–sau cùng một ma trận test cho kết quả tương đương hoặc có thay đổi đã được review.

**Kết luận:** `WebExpressionAuthorizationManager` là cầu nối đáng tin cậy để **đánh giá SpEL web cũ trong hệ `AuthorizationManager` mới**, nhưng chất lượng migration nằm ở quyết định truy cập thực tế. Dùng constructor cho nhánh 6.x, cân nhắc builder cho nhánh 7.0+, giữ đúng quyền/matcher/bean context, rồi thay các biểu thức phức tạp bằng manager type-safe khi đã có test chứng minh hành vi.

### Tài liệu chính thức

- [Spring Security 6.5 — Authorize HttpServletRequests, Migrating Expressions](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): DSL mới, expression migration cho 6.x.
- [Spring Security 6.5 — WebExpressionAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/expression/WebExpressionAuthorizationManager.html): constructor, `setExpressionHandler`, `check`.
- [Spring Security 7.0 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html): manager, matching, builder và bean policy.
- [Spring Security 7.0 — WebExpressionAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/access/expression/WebExpressionAuthorizationManager.html): `withDefaults`/`withExpressionHandler`, deprecated setter, API 7.
- [Spring Security 7 — What’s New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): thay đổi AuthorizationManager, loại bỏ API legacy.
- [Spring Security — Testing Authorization](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authorization.html): dùng MockMvc kiểm đúng quyền request.
