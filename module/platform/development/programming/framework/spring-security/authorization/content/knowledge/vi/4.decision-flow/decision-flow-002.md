# SecurityContext và cách lấy Authentication tại thời điểm kiểm tra

> **Module:** Spring Security – authorization  
> **Nhóm:** Luồng quyết định  
> **Phạm vi:** Cách Spring Security nắm giữ danh tính đang có hiệu lực, cách các cơ chế phân quyền lấy `Authentication` khi cần ra quyết định, và các ranh giới luồng xử lý dễ khiến việc đọc danh tính sai.

## 1. Tình huống mở đầu: “người dùng hiện tại” là ai?

Một API `GET /api/invoices/101` được gọi bởi Lan. Hệ thống xác thực token/session và biết Lan có quyền `invoice:read`. Khi quyết định có trả hóa đơn số 101 hay không, code cần xác định:

1. **Ai đang gọi yêu cầu này?** Danh tính đã được Spring Security xác thực là gì?
2. **Người gọi có những quyền nào tại thời điểm kiểm tra?** Có authority `invoice:read`, `ROLE_ACCOUNTANT` hoặc `SCOPE_invoices.read` không?
3. **Hóa đơn 101 có nằm trong phạm vi của người gọi không?** Cùng tenant, đúng owner, hoặc được chia sẻ hợp lệ?
4. **Việc kiểm tra đang chạy ở đâu?** Trong servlet request thread, trong method được interceptor bảo vệ, hay trong một tác vụ bất đồng bộ?

Trong Spring Security, **`SecurityContext` chứa `Authentication`**, còn **`SecurityContextHolder` cho phép truy xuất `SecurityContext` đang gắn với ngữ cảnh thực thi**. Ở ứng dụng Servlet thông thường, `SecurityContextHolder` dùng `ThreadLocal`. Vì thế, “lấy user hiện tại” có nghĩa là **lấy authentication đang có hiệu lực trong ngữ cảnh thực thi hiện tại**, chứ không phải đọc một biến global dùng chung cho cả ứng dụng.

Bài học này đi theo luồng ra quyết định thực tế để làm rõ: khi nào context được nạp, khi nào authentication được đọc, những API lấy authentication thích hợp, vì sao có lúc trả `null`/anonymous, và vì sao truyền công việc sang thread khác cần xử lý riêng.

## 2. Phân biệt bốn thành phần liên quan

| Thành phần | Vai trò trong luồng | Cần nhớ |
|---|---|---|
| `SecurityContextHolder` | Điểm truy cập tới context theo chiến lược lưu trữ đang cấu hình | Không phải một “user singleton”; mặc định dựa trên thread hiện tại ở Servlet |
| `SecurityContext` | Chứa `Authentication` đang có hiệu lực | Có thể tồn tại nhưng `getAuthentication()` là `null` |
| `Authentication` | Đại diện cho chủ thể hoặc yêu cầu xác thực; có principal, authorities, details, trạng thái authenticated | Loại đối tượng phụ thuộc cơ chế xác thực: username/password, JWT, OAuth, anonymous… |
| `GrantedAuthority` | Quyền gắn với `Authentication` để policy có thể so khớp | Ví dụ `ROLE_USER`, `invoice:read`, `SCOPE_invoices.read` |

Quan hệ thường gặp:

~~~text
SecurityContextHolder
         |
         v
   SecurityContext
         |
         v
     Authentication
      /     |      \
principal credentials authorities
                    |
                    +--> ROLE_ACCOUNTANT
                    +--> invoice:read
                    +--> SCOPE_invoices.read
~~~

**`SecurityContext` không tự xác thực thông tin.** Nó là nơi giữ kết quả xác thực/đại diện chủ thể theo cơ chế của hệ thống. Authentication phải được tạo ra từ một cơ chế đáng tin, chẳng hạn authentication filter + `AuthenticationManager` hoặc một JWT đã được Resource Server xác minh. Không tin chuỗi `userId`, `role` hoặc `authorities` do client tự gửi rồi tự gắn nó vào context để vượt kiểm soát quyền.

### Một `Authentication` chứa gì?

Các phương thức quan trọng của interface:

- `getName()`: tên đại diện chủ thể theo implementation đang dùng.
- `getPrincipal()`: đối tượng principal; có thể là `UserDetails`, `Jwt`, String hoặc kiểu khác.
- `getAuthorities()`: tập các `GrantedAuthority` đã được cấp.
- `isAuthenticated()`: cờ trạng thái của authentication token; **không tự bảo đảm chủ thể là một người dùng đã đăng nhập theo nghĩa nghiệp vụ** vì anonymous authentication cũng có thể được đánh dấu authenticated.
- `getDetails()`: chi tiết bổ sung do implementation cung cấp; không nên mặc định có tenant/permission ở đây.
- `getCredentials()`: dữ liệu chứng thực; thường được xóa sau xác thực, không log hay trả ra API.

Đừng ép kiểu principal thành `UserDetails` trong mọi luồng. Ứng dụng JWT Resource Server thường có principal kiểu `Jwt` trong `JwtAuthenticationToken`; một ứng dụng form login có thể dùng `UserDetails`; anonymous authentication có principal khác nữa. Hãy xây dựng abstraction danh tính theo cơ chế thật của ứng dụng.

## 3. Vòng đời một request Servlet: context đến từ đâu?

Một dòng chảy điển hình với Spring Security Servlet:

~~~text
HTTP request
     |
     v
Spring Security FilterChainProxy
     |
     +--> SecurityContextHolderFilter / cơ chế load context
     |    - lấy SecurityContext từ SecurityContextRepository nếu phù hợp
     |    - chuẩn bị SecurityContextHolder cho request
     |
     +--> Authentication filters
     |    - session/form login, HTTP Basic, Bearer JWT, ...
     |    - xác minh credentials/token theo cấu hình
     |    - đặt Authentication được tin cậy vào context
     |
     +--> AuthorizationFilter
     |    - chọn rule cho request
     |    - lấy Authentication KHI rule cần đến
     |    - gọi AuthorizationManager để quyết định
     |
     +--> DispatcherServlet / Controller
     |    |
     |    +--> Service method được method security chặn nếu cấu hình
     |    +--> Truy cập dữ liệu và policy theo đối tượng
     |
     v
Response
     |
     v
Kết thúc xử lý: context của thread phải được dọn theo lifecycle
~~~

**Đây là sơ đồ khái niệm**, không phải thứ tự tất cả các filter trong mọi cấu hình. Có thể có anonymous filter, exception translation, CSRF, session management, request cache hoặc các filter tùy chỉnh. Spring Security sắp xếp và điều phối chúng theo filter chain hiệu lực.

Ở Spring Security 6.x, `SecurityContextHolderFilter` thường làm nhiệm vụ load context; `SecurityContextPersistenceFilter` thuộc cơ chế lịch sử và không nên được cấu hình chạy đồng thời. Với session-based authentication, repository có thể phục hồi context từ session. Với JWT Bearer Resource Server stateless, token thường được xác minh và tạo authentication cho từng request; không nên mặc định suy rằng login/token sẽ tự lưu vào HTTP session.

**Điểm thời gian quan trọng:** request có thể bắt đầu mà chưa phải mọi bước xác thực đều hoàn tất. Việc tự ý đọc `SecurityContextHolder` trong một filter chạy **trước** authentication filter có thể nhận context trống hoặc chưa có principal mong đợi; đặt việc kiểm tra quyền ở đúng điểm sau xác thực hoặc sử dụng authorization infrastructure do Spring Security quản lý.

## 4. Cách đọc `Authentication` trong code Servlet

### 4.1. Cách thấp nhất: `SecurityContextHolder.getContext()`

Trong một service hoặc một component đang thực thi ở thread được Spring Security bảo vệ:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();

if (authentication != null) {
    String username = authentication.getName();
    // authorities nằm trong authentication.getAuthorities()
}
~~~

Đoạn này là **snippet trong ứng dụng Spring Security**, không phải chương trình Java chạy độc lập. `getContext()` thường cung cấp một context (có thể trống); **`getAuthentication()` mới là giá trị cần kiểm tra `null`**. Không gọi thẳng `getAuthentication().getName()` nếu code có thể chạy trước khi đăng nhập, ở public endpoint, trong worker thread hoặc ngoài request.

Trường hợp chỉ cần danh tính đã xác thực, nên yêu cầu route/service đủ bảo vệ rồi đọc ở nơi sử dụng, không lưu authentication vào trường `static` hay biến instance của singleton service.

### 4.2. Lấy các quyền từ Authentication

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

Set<String> authorities = authentication == null
        ? Set.of()
        : authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(java.util.Objects::nonNull)
                .collect(Collectors.toUnmodifiableSet());
~~~

Đoạn trên minh họa cách thu thập **chuỗi authority**, không phải cách tự quyết định mọi quyền. Nếu muốn kiểm tra `ROLE_ADMIN`, `invoice:read` hoặc `SCOPE_invoices.read`, nhất thiết phải biết nguồn ánh xạ đã cấp authority nào và chính sách áp dụng. Khi có role hierarchy hoặc custom authorization logic, chỉ kiểm tra `Set.contains(...)` tự viết có thể khác kết quả của AuthorizationManager được cấu hình.

**Không trả danh sách authority ra public API mặc định.** Chỉ bộc lộ thông tin danh tính/quyền khi chức năng thật sự cần và dữ liệu được giới hạn phù hợp.

### 4.3. Dùng interface của framework để tránh đọc holder trực tiếp ở controller

Trong Spring MVC, các lựa chọn thường dùng:

| Cách lấy | Nội dung nhận được | Phù hợp khi |
|---|---|---|
| `SecurityContextHolder.getContext().getAuthentication()` | `Authentication` hiện hành | Service/utility đồng bộ nằm trong Servlet security context |
| `@CurrentSecurityContext(expression = "authentication") Authentication auth` | Chính `Authentication` | Controller cần danh tính kèm authorities |
| `@AuthenticationPrincipal Object principal` | `Authentication.getPrincipal()` | Chỉ cần principal và biết kiểu của nó |
| `Principal principal` | Principal của request (thường lấy được `getName()`) | Chỉ cần tên danh tính, tránh phụ thuộc implementation |
| `HttpServletRequest.getUserPrincipal()` | Principal của Servlet request | Tích hợp API Servlet |
| `@PreAuthorize` với biểu thức `authentication`, `principal` | Authentication/principal khi method được kiểm tra | Đặt policy tại method boundary |

Một controller minh họa có thể viết:

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class IdentityController {

    @GetMapping("/me")
    public Map<String, String> me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication,
            @AuthenticationPrincipal Object principal,
            Principal servletPrincipal) {

        // Endpoint này phải được bảo vệ bởi rule authenticated.
        return Map.of(
                "authenticationName", authentication.getName(),
                "principalType", principal.getClass().getSimpleName(),
                "servletName", servletPrincipal.getName()
        );
    }
}
~~~

**Điều kiện chạy:** đây là một class Spring MVC trong dự án có Spring Web và Spring Security; endpoint `/api/me` phải được bảo vệ để chỉ người dùng đã xác thực mới gọi tới. Nó không tự biên dịch chỉ bằng JDK 17. Phần `principalType` minh họa rằng principal **không mặc định** là `UserDetails`. Khi dùng public endpoint, phải thiết kế trường hợp authentication/principal null, và không dùng output này để công khai chi tiết quyền/claims nhạy cảm.

Lưu ý ở một số cấu hình, Servlet `Principal` và Security `Authentication` có thể liên hệ nhưng không nhất thiết là cùng kiểu; annotation `@CurrentSecurityContext` là cách tường minh khi muốn **toàn bộ Authentication**. Nếu chỉ cần ID nghiệp vụ, nên dùng một service chuyển đổi principal đã xác thực thành định danh domain đáng tin.

## 5. “Tại thời điểm kiểm tra” trong `authorizeHttpRequests` là lúc nào?

Từ Spring Security 6, cấu hình `authorizeHttpRequests` sử dụng `AuthorizationFilter` và `AuthorizationManager`. Một khác biệt quan trọng là **lấy authentication theo nhu cầu**:

~~~text
AuthorizationFilter
    |
    +--> tạo Supplier<Authentication>
    |
    +--> tìm rule phù hợp với request
    |
    +--> gọi AuthorizationManager
              |
              +--> permitAll / denyAll
              |       thường không cần gọi supplier.get()
              |
              +--> authenticated / hasRole / hasAuthority /
                    policy tùy chỉnh
                      |
                      +--> khi cần, gọi supplier.get()
                               |
                               v
                      Authentication trong context hiện hành
~~~

Vì vậy, câu “Spring Security lấy authentication **tại thời điểm kiểm tra**” có ý nghĩa cụ thể: rule cần danh tính có thể truy xuất `Authentication` từ `SecurityContextHolder` khi đánh giá, thay vì tải principal từ session hoặc token một cách vô điều kiện cho mọi URL.

Ví dụ cấu hình **có ý nghĩa về thời điểm lookup**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("invoice:read")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Trong cách cấu hình này:

- `permitAll()` có thể cho phép request mà authorization **không cần đọc Authentication**; điều này không có nghĩa mọi authentication filter đều bị bỏ qua.
- `hasAuthority("invoice:read")` cần quyền hiệu lực từ `Authentication`.
- `hasRole("ADMIN")` với quy ước mặc định thường yêu cầu authority `ROLE_ADMIN`.
- `denyAll()` từ chối vô điều kiện nên không cần lookup Authentication.
- `httpBasic()` minh họa cơ chế xác thực; ứng dụng thật cần cấu hình người dùng/credential, HTTPS, các endpoint được cho phép và kiểm soát CSRF/session tùy kiến trúc.

**Một lỗi tư duy thường gặp:** thấy `permitAll` “không load Authentication” rồi kết luận “context trong controller chắc chắn trống” hoặc “authentication filter không chạy”. Đây là hai khâu khác nhau. Rule có thể không **yêu cầu** lookup, trong khi các filter khác có thể xác thực request; hành vi phụ thuộc cấu hình chain và request thực tế.

## 6. Custom `AuthorizationManager`: nhận supplier và chỉ đọc khi cần

Nếu logic phân quyền phụ thuộc cả request và đối tượng, `authorizeHttpRequests` cho phép truyền một `AuthorizationManager<RequestAuthorizationContext>`. Ví dụ minh họa tích hợp policy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class InvoiceHttpAuthorizationConfig {

    @Bean
    SecurityFilterChain invoiceSecurity(
            HttpSecurity http,
            InvoiceAccessPolicy invoiceAccessPolicy) throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.GET, "/api/invoices/{invoiceId}")
                    .access((authenticationSupplier, context) -> {
                        String invoiceId =
                                context.getVariables().get("invoiceId");

                        boolean permitted = invoiceAccessPolicy.canRead(
                                authenticationSupplier.get(), invoiceId);

                        return new AuthorizationDecision(permitted);
                    })
                .anyRequest().authenticated()
        );

        return http.build();
    }
}
~~~

**Đây là đoạn cấu hình phụ thuộc ứng dụng**, cần interface/bean `InvoiceAccessPolicy` do hệ thống cài đặt; chưa bao gồm authentication mechanism và những rule cần thiết khác. Chính sách `canRead(authentication, invoiceId)` phải lấy invoice từ nguồn server, xác minh permission, tenant và ownership; biết `invoiceId` không tự tạo quyền. Đừng nhận tenant từ query/header do người gọi tự khai làm căn cứ duy nhất.

Ở đây, `authenticationSupplier.get()` được gọi **khi policy cần đánh giá chủ thể**. Không nên gọi supplier trong lúc khởi tạo cấu hình và lưu `Authentication` vào một bean singleton: bean có thể sống hàng tháng, còn principal thay đổi theo từng request.

Khi policy cần nhiều thông tin, truyền `Authentication` vào policy làm dependency tường minh, dễ kiểm thử hơn việc mỗi tầng đều gọi `SecurityContextHolder`. Đồng thời cần chọn vị trí thích hợp: kiểm tra quyền theo từng bản ghi ở service thường tránh được tình trạng một luồng khác gọi service nhưng bỏ qua HTTP rule.

## 7. Method security: lấy Authentication khi method được gọi

Ở tầng method, `@PreAuthorize`/`@PostAuthorize` cho phép diễn tả điều kiện phân quyền tại biên gọi method. Bật hỗ trợ bằng `@EnableMethodSecurity`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Trong một Spring-managed service, ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceDto readInvoice(long invoiceId) {
    // Đọc tài nguyên sau khi qua kiểm tra quyền hành động.
    return invoiceService.read(invoiceId);
}
~~~

Biểu thức `hasAuthority('invoice:read')` được đánh giá khi method invocation đi qua method security interceptor; nó sử dụng authentication tương ứng với **lần gọi hiện tại**. Một invocation sau, với một authentication khác, phải được đánh giá lại. Tránh lưu kết quả “user A là admin” vào trạng thái bean dùng chung rồi tái sử dụng cho user B.

Ngoài các helper như `hasAuthority`, biểu thức security còn có:

- `authentication`: instance `Authentication` gắn với invocation.
- `principal`: đối tượng `Authentication.getPrincipal()`.
- `#invoiceId`: tham số method nếu tên có thể được Spring Security nhận diện.
- `@somePolicy.check(...)`: gọi policy bean do ứng dụng định nghĩa.

Ví dụ kết hợp quyền chức năng và đối tượng:

~~~java
@PreAuthorize(
        "hasAuthority('invoice:read') " +
        "and @invoicePolicy.canRead(authentication, #invoiceId)")
public InvoiceDto readInvoice(long invoiceId) {
    return invoiceService.read(invoiceId);
}
~~~

**Điều kiện:** phải có bean `invoicePolicy`, method policy phù hợp và tên tham số `invoiceId` được Spring Security nhận diện (chẳng hạn biên dịch với `-parameters` hoặc khai báo tên tường minh). Đoạn này chỉ minh họa một method, không phải class biên dịch độc lập.

Phân biệt:

- **Kiểm tra authority:** chủ thể có quyền đọc hóa đơn về mặt hành động không?
- **Kiểm tra đối tượng:** hóa đơn cụ thể có thuộc tenant/owner hoặc nhóm được chia sẻ không?

Cả hai cần đúng. Nếu method được gọi trực tiếp từ method khác trong cùng instance và dự án dùng proxy-based method security, annotation có thể không được thực thi do **self-invocation**. Đây là lỗi kiến trúc dẫn đến quyết định quyền không chạy, không phải lỗi `SecurityContextHolder`.

### 7.1. `@PreAuthorize` không phải lúc nào cũng là lần kiểm tra duy nhất

Một request có thể phải qua HTTP authorization, sau đó method security, rồi các policy nghiệp vụ ở service/repository. Nhiều chốt bảo vệ cùng ra quyết định ở **thời điểm khác nhau** trong cùng request. Đừng suy ra “đã qua rule HTTP thì mọi object đều được phép”.

Với `@PostAuthorize`, quyết định có thể được kiểm tra sau khi method hoàn thành và có kết quả trả về; tuy nhiên điều đó không thay thế việc bảo vệ side effect trước khi thực hiện. Tránh dùng kiểm tra sau để bảo vệ thao tác thay đổi dữ liệu nguy hiểm mà đáng ra phải chặn từ trước.

## 8. Context có thể trống hoặc là anonymous: kiểm tra ra sao?

Ở public endpoint hoặc code chạy ngoài servlet filter chain, tình huống này có thể xảy ra:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

// authentication có thể null.
~~~

Nếu cơ chế anonymous authentication được bật, Spring Security có thể gắn `AnonymousAuthenticationToken` vào context. Vì vậy:

~~~java
authentication != null && authentication.isAuthenticated()
~~~

**không phải cách luôn đúng để xác định “người dùng đã đăng nhập”**. `AnonymousAuthenticationToken` cũng có thể trả `isAuthenticated() == true`. Đây là trạng thái authentication token của framework, không phải cam kết rằng một người dùng có danh tính thật đã đăng nhập.

Trong một service chỉ chấp nhận user đã xác thực, có thể dùng lớp helper rõ ràng:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class CurrentActor {

    private CurrentActor() {
    }

    public static Authentication requireUser() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException(
                    "An authenticated user is required");
        }
        return authentication;
    }
}
~~~

Đây là class Java trong **dự án đã có Spring Security**, không phải Java core độc lập. Nó minh họa xử lý `null` và anonymous. Trong hệ thống phức tạp hơn, có thể sử dụng `AuthenticationTrustResolver` để phân biệt anonymous/remember-me và những policy yêu cầu *fully authenticated*. Với policy ở HTTP hoặc method security, ưu tiên dùng rule `authenticated()`/`isAuthenticated()` của framework đúng ngữ nghĩa anonymous thay vì viết lại toàn bộ logic.

Một số trường hợp khác cần phân biệt:

| Tình huống | Authentication trong holder có thể là | Điều nên kiểm tra |
|---|---|---|
| Request được bảo vệ, login thành công | Authentication thật của user/client | Principal/authorities, policy domain |
| Public request chưa đăng nhập | `null` hoặc anonymous | Không giả định `getName()` đại diện user đã login |
| Bearer token không hợp lệ | Thường bị authentication filter từ chối trước controller | Không xử lý như user hợp lệ |
| Thread mới không được truyền context | Context trống, authentication `null` | Dùng propagation hoặc truyền danh tính đã xác minh |
| Unit test không dựng security context | Thường trống | Dựng mock authentication/test security phù hợp |
| Sau logout/clearContext | Authentication trước đó không còn là “current” | Không dùng tham chiếu cũ cho quyền mới |

Đầu ra 401/403 tùy vị trí và security entry point/handler: yêu cầu chưa xác thực thường là `401`; yêu cầu đã xác thực nhưng thiếu quyền thường là `403`. Ứng dụng có thể có chiến lược 404 ở mức tài nguyên để tránh tiết lộ sự tồn tại, nhưng không được rò rỉ nội dung tài nguyên.

## 9. Tại sao mặc định là `ThreadLocal` và hậu quả của nó?

Trên **Servlet stack**, `SecurityContextHolder` mặc định dùng `MODE_THREADLOCAL`. Có thể hình dung:

~~~text
Request A -> Thread T1 -> SecurityContext [Lan]
Request B -> Thread T2 -> SecurityContext [Bình]

SecurityContextHolder.getContext() trên T1 -> context của Lan
SecurityContextHolder.getContext() trên T2 -> context của Bình
~~~

Điều này không có nghĩa một thread mãi mãi thuộc về một user. Servlet container dùng **thread pool**: thread T1 có thể phục vụ request của Lan lúc này và Bình ở request sau. Spring Security filter chain đảm bảo lifecycle context được làm sạch theo cơ chế quản lý của nó, tránh chuyển danh tính từ request trước sang request sau.

Ba sai lầm nghiêm trọng:

1. **Lưu authentication vào trường instance của singleton `@Service`:** trường này được mọi request dùng chung, có thể chứa user sai.
2. **Tự tạo/cài context trong thread nhưng quên clear:** thread được tái sử dụng có thể mang danh tính cũ.
3. **Truy cập holder từ thread mới rồi tin có cùng người gọi:** `ThreadLocal` không tự xuyên qua thread boundary.

`SecurityContextHolder` có thể dùng strategy khác như `MODE_INHERITABLETHREADLOCAL` hoặc `MODE_GLOBAL`, nhưng việc thay chiến lược không phải giải pháp mặc định cho server. Đặc biệt `InheritableThreadLocal` với thread pool có thể truyền context sai thời điểm tạo thread và tạo nguy cơ dùng danh tính cũ. Với ứng dụng web thông thường, giữ mặc định và sử dụng cơ chế propagation được Spring Security hỗ trợ khi thực sự cần.

## 10. Tác vụ bất đồng bộ: khi đọc holder sẽ đọc ngữ cảnh nào?

Xét một API gọi `@Async`, `CompletableFuture`, `ExecutorService` hoặc tạo thread mới:

~~~text
Servlet thread: Authentication = Lan
              |
              +--> submit công việc
                       |
                       v
                  Worker thread
                  Authentication = ?
~~~

Mặc định với `MODE_THREADLOCAL`, worker thread **không tự kế thừa** context của servlet thread. Nó có thể không có authentication. Nếu một worker tái sử dụng context cũ do code tự đặt và không dọn, đó là lỗi bảo mật còn nghiêm trọng hơn.

Spring Security cung cấp các wrapper như:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextExecutor`
- Các integration executor/task executor hỗ trợ `SecurityContext`

Những wrapper này thiết lập context thích hợp trong thời gian chạy delegate và dọn context sau đó. Tùy wrapper/constructor, context có thể được cố định từ lúc cấu hình hoặc được lấy theo thời điểm submit, vì vậy phải hiểu chính xác phiên bản và cách khởi tạo. **Không tái sử dụng một `SecurityContext` chứa danh tính user A làm context cố định cho toàn bộ executor xử lý của user B.**

Ví dụ dạng khái niệm trong một ứng dụng đã quản lý executor:

~~~java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

// delegateExecutor là executor do ứng dụng quản lý.
Executor securityAwareExecutor =
        new DelegatingSecurityContextExecutor(delegateExecutor);

securityAwareExecutor.execute(() -> {
    // Tác vụ có thể truy xuất context đã được wrapper truyền.
    // Tránh giữ Authentication ở static/global state.
});
~~~

Đây là **snippet tích hợp**, không phải chương trình độc lập; phải có `delegateExecutor` và lifecycle shutdown phù hợp. Việc quyết định có nên **truyền danh tính** sang công việc nền hay không là quyết định nghiệp vụ: một job gửi email vào ngày hôm sau thường nên dùng service identity/authorization rõ ràng hoặc dữ liệu audit đã xác minh, thay vì giữ toàn bộ authentication của request trước đó.

**Quy tắc:** nếu tác vụ chỉ cần ID chủ thể cho audit, hãy chuyển một ID đã xác minh dưới dạng dữ liệu công việc. Nếu tác vụ cần thực thi *với quyền của người dùng* tại thời điểm chạy, thiết kế policy, độ tươi của quyền và cơ chế propagation/ủy quyền riêng thay vì ngầm dựa vào `ThreadLocal`.

## 11. Vòng đời, thay đổi quyền và tính “hiện tại” của Authentication

Từ “hiện tại” có hai nghĩa cần phân biệt:

1. **Hiện tại trong ngữ cảnh xử lý**: authentication mà security infrastructure đang cung cấp cho invocation/request đang diễn ra.
2. **Hiện tại theo dữ liệu quyền mới nhất trong database/IdP**: role/permission có thể vừa được quản trị viên thay đổi.

Hai điều này **không luôn đồng nhất**. Ví dụ:

~~~text
10:00 — Lan đăng nhập; Authentication chứa invoice:approve.
10:05 — Admin thu hồi quyền invoice:approve trong database.
10:06 — Session cũ hoặc JWT chưa hết hạn vẫn mang authority cũ.
10:07 — Rule đọc authority từ Authentication hiện hành.
~~~

Nếu hệ thống không có cơ chế làm mới quyền hoặc thu hồi phù hợp, rule ở 10:07 có thể vẫn nhìn thấy authority cũ. Điều đó **không có nghĩa SecurityContextHolder đọc sai thread**; nó đang đọc chính xác thông tin authentication đang có hiệu lực, nhưng thông tin đó chưa được làm mới theo nguồn quyền nghiệp vụ.

Khi yêu cầu thu hồi quyền nhanh, cần cân nhắc:

- Kiểm tra permission nhạy cảm từ nguồn cập nhật hoặc cache có chính sách vô hiệu hóa.
- Rút ngắn vòng đời access token theo mức chấp nhận của sản phẩm.
- Thiết kế revocation/session invalidation hoặc token introspection khi cần.
- Không tin claims lâu sống đối với các quyết định có rủi ro cao mà đòi dữ liệu quyền mới.
- Kiểm tra tenant, owner và trạng thái tài nguyên tại thời điểm thực hiện thao tác, không dựa mãi trên dữ liệu request trước.

Không đánh đồng **lấy authentication lúc đánh giá** với **tải mới role từ database ở mọi lần đánh giá**. Bộ máy authorization thường đọc authorities đã được đưa vào `Authentication`; việc làm mới quyền là một trách nhiệm kiến trúc riêng.

## 12. `SecurityContextRepository` và việc lưu context qua các request

Ở Servlet, cần phân biệt:

- **Holder:** context đang có hiệu lực trong luồng xử lý hiện tại.
- **Repository:** nơi lưu/khôi phục context giữa các request nếu ứng dụng dùng persistence.
- **Session-based authentication:** có thể dùng repository lưu context trong HTTP session.
- **Stateless Bearer JWT:** thường xác minh token và xây dựng authentication cho mỗi request, không cần giữ session server cho user.

Với Spring Security 6.x, khi một **custom authentication mechanism** tự xác thực thành công và muốn lưu context sang request sau, thường cần làm rõ bước lưu vào `SecurityContextRepository` (thay vì chỉ gọi `SecurityContextHolder.setContext`):

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;

// authentication là kết quả đã được xác minh.
// request và response là các đối tượng HTTP Servlet hiện tại.
// securityContextRepository do ứng dụng cấu hình/cung cấp.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
~~~

Đây là **snippet minh họa bên trong custom authentication flow**, không phải thứ mọi controller cần tự làm. Một login filter do Spring Security quản lý có thể xử lý lưu context theo cơ chế của nó. Ngược lại, stateless Resource Server thường **không cần** gọi `saveContext` cho mỗi JWT.

Tại sao nên dùng `createEmptyContext()` khi tự tạo context? Spring Security khuyến nghị tạo một context mới trước khi `setAuthentication`, giảm nguy cơ race condition do cùng context bị tham chiếu/chia sẻ ở nhiều nơi. Không dùng việc set context thủ công làm đường tắt để giả mạo danh tính.

Dọn context bằng `SecurityContextHolder.clearContext()` khi code **tự quản lý** vòng đời (ví dụ đoạn test tùy chỉnh với thread); với request thông thường, Spring Security filter chain chịu trách nhiệm cleanup.

## 13. Servlet và WebFlux: không lấy Authentication cùng một cách

Bài học hiện tại lấy **Servlet stack** làm tuyến chính. Với ứng dụng **Spring WebFlux/reactive**, ngữ cảnh bảo mật thường dựa trên **Reactor Context**, không thể tùy tiện trông chờ `ThreadLocal` từ `SecurityContextHolder` truyền đúng qua reactive operator và thay đổi thread.

Spring Security reactive cung cấp `ReactiveSecurityContextHolder`. Ví dụ trong một component reactive:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
~~~

Đoạn này là **method trong dự án WebFlux có Spring Security reactive**, không phải chương trình Java độc lập; khi không có security context, publisher có thể rỗng, nên caller cần thiết kế xử lý `switchIfEmpty`/authorization phù hợp. Không chuyển method sang code Servlet rồi mong nó thay thế `SecurityContextHolder.getContext()`.

Trong WebFlux controller có thể inject principal/reactive authentication qua các cơ chế được hỗ trợ, hoặc dùng reactive method security khi đã được kích hoạt phù hợp. Cách truyền context qua chuỗi Reactor là điểm cần bảo toàn; **gọi `block()` hoặc tạo thread tùy ý** để “đọc auth cho dễ” thường là một hướng triển khai sai.

## 14. Ví dụ Java 17 độc lập: minh họa thời điểm đọc và ranh giới thread

Để thấy rõ **đọc ngay tại thời điểm quyết định** khác với **giữ snapshot cũ** như thế nào, ví dụ sau dùng `ThreadLocal` của Java thuần. **Đây chỉ là mô phỏng cách lưu context theo thread**, không phải implementation của Spring Security; Java core không tự xác thực user/token.

Lưu tệp `ContextTimingDemo.java`:

~~~java
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public class ContextTimingDemo {

    record Actor(String name, Set<String> authorities) {
    }

    private static final ThreadLocal<Actor> CURRENT =
            new ThreadLocal<>();

    static String currentName() {
        Actor actor = CURRENT.get();
        return actor == null ? "<none>" : actor.name();
    }

    static boolean canApprove() {
        Actor actor = CURRENT.get();
        return actor != null
                && actor.authorities().contains("invoice:approve");
    }

    public static void main(String[] args)
            throws InterruptedException {

        CURRENT.set(new Actor("lan", Set.of("invoice:read")));
        Actor savedOldActor = CURRENT.get();

        System.out.println("lan can approve: " + canApprove());

        CURRENT.set(new Actor(
                "minh", Set.of("invoice:read", "invoice:approve")));

        System.out.println("minh can approve: " + canApprove());

        AtomicReference<String> workerName =
                new AtomicReference<>();

        Thread worker = new Thread(() ->
                workerName.set(currentName()));
        worker.start();
        worker.join();

        System.out.println(
                "worker thread actor: " + workerName.get());
        System.out.println(
                "saved old actor: " + savedOldActor.name());

        CURRENT.remove();

        System.out.println(
                "after clear actor: " + currentName());
        System.out.println(
                "after clear can approve: " + canApprove());
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac ContextTimingDemo.java
java ContextTimingDemo
~~~

Kết quả chính xác:

~~~text
lan can approve: false
minh can approve: true
worker thread actor: <none>
saved old actor: lan
after clear actor: <none>
after clear can approve: false
~~~

**Diễn giải kết quả:**

1. Context thread chính đang là Lan, chưa có `invoice:approve` → từ chối.
2. Sau khi đổi context sang Minh, gọi `canApprove()` **ở thời điểm mới** thấy `invoice:approve` → cho phép.
3. Thread mới có một `ThreadLocal` riêng, nên không tự nhìn thấy actor của thread chính.
4. Biến `savedOldActor` vẫn giữ Lan dù actor hiện tại đã đổi thành Minh → snapshot cũ **không đại diện cho current actor**.
5. `CURRENT.remove()` dọn context trong thread chính, tránh dùng giá trị cũ trong lần xử lý sau.

Ví dụ **không nói rằng một ứng dụng production nên đổi identity giữa chừng**. Nó cho thấy vì sao phải dùng đúng infrastructure gắn context theo request, vì sao không lưu authentication để tái sử dụng và vì sao chuyển thread đòi cơ chế rõ ràng.

## 15. Kiểm thử: xác minh ai được nhìn thấy vào lúc policy chạy

Một bộ test tốt phải bao gồm **ít nhất hai người dùng khác nhau** và cả trường hợp không xác thực. Ví dụ endpoint `GET /api/invoices/{id}` có rule permission đọc và policy theo owner/tenant:

| Bối cảnh | Khi policy lấy Authentication | Kết quả mong đợi |
|---|---|---|
| Lan có `invoice:read`, đọc hóa đơn của Lan | Principal là Lan | Cho phép |
| Bình có `invoice:read`, đọc hóa đơn của Lan | Principal là Bình | Từ chối theo object policy |
| Lan không có `invoice:read` | Principal là Lan, thiếu authority | Từ chối |
| Không gửi login/token | Không có authentication thật hoặc có anonymous | Từ chối theo cấu hình |
| JWT có scope đọc nhưng thiếu permission nghiệp vụ | Có scope; không tự có permission nội bộ | Phụ thuộc policy, không được tự suy luận |
| Task worker không propagate context | Worker có thể không có authentication | Không ngầm thực hiện với quyền của caller |
| Context thread được clear ở cuối request | Lần xử lý sau không mang danh tính cũ | Không lộ chéo user |
| Role vừa bị thu hồi nhưng token/session chưa refresh | Authentication có thể vẫn chứa quyền cũ | Phải đáp ứng chính sách freshness/revocation |

Trong test Spring Security MVC, `@WithMockUser` hoặc request post-processor `user(...)` giúp mô phỏng authentication. Tuy nhiên mock user **không chứng minh** JWT validation, session persistence hoặc mapping roles/claims thực tế đã đúng. Phải test riêng các chặng đó nếu chúng liên quan tới yêu cầu bảo mật.

Ví dụ đoạn test trong dự án có Spring Security Test và một endpoint `GET /api/me` được bảo vệ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

// mvc là MockMvc đã áp dụng Spring Security test setup.
mvc.perform(get("/api/me").with(user("lan")
                .authorities(new SimpleGrantedAuthority("invoice:read"))))
        .andExpect(status().isOk());
~~~

Các import `import static` xuống dòng ở snippet này chỉ minh họa **các package lớp test**; khi đưa vào source Java thật hãy viết mỗi import trên **một dòng Java hợp lệ**. Vì phụ thuộc `mvc`, endpoint và test dependencies, đây là snippet, không phải ví dụ JDK độc lập. Mục tiêu test: rule được đánh giá với Authentication của **request đó**, không phải một giá trị cố định từ test trước.

Có thể dùng test method security để xác minh policy nhìn đúng `authentication.name` và authorities của từng lần gọi. Để kiểm tra thread leak, chạy hai task liên tiếp với identity khác nhau trên cùng executor và xác minh task thứ hai không nhận actor thứ nhất sau cleanup.

## 16. Lỗi thường gặp khi lấy Authentication

| Lỗi | Tác động | Cách sửa |
|---|---|---|
| Gọi `getAuthentication().getName()` ở public request | `NullPointerException` hoặc nhầm anonymous | Bảo vệ endpoint hoặc xử lý `null`/anonymous |
| Dùng `isAuthenticated()` như bằng chứng chắc chắn user thật | Anonymous token có thể báo `true` | Dùng framework trust semantics/kiểm tra anonymous đúng cách |
| Lưu `Authentication` vào singleton field | Rò danh tính giữa các request/thread | Đọc/tạo parameter theo invocation; không giữ global state |
| Đọc `SecurityContextHolder` trước auth filter | Context chưa có user xác thực | Chuyển check đến sau auth hoặc dùng authorization infrastructure |
| Giữ reference authentication của request cũ | Quyền lỗi thời hoặc nhầm user | Lấy ở thời điểm kiểm tra, quản lý cập nhật quyền |
| Dùng `ThreadLocal` trong `@Async` rồi mong thấy caller | Worker thread context khác | Propagation có kiểm soát hoặc truyền ID đáng tin |
| Tự `setContext` nhưng không `clearContext` ở thread tùy chỉnh | Thread pool có thể giữ danh tính cũ | `try/finally` và cleanup chính xác |
| Chỉ `setContext` trong custom login rồi tin request sau còn | Không lưu vào repository theo cơ chế cần thiết | Dùng `SecurityContextRepository.saveContext` khi session persistence cần |
| Ép principal thành `UserDetails` trong ứng dụng JWT | `ClassCastException` | Dựa trên loại authentication thực và adapter identity |
| Chỉ check `hasRole` mà không check owner/tenant | Lộ dữ liệu dù authority đúng | Policy object-level và giới hạn query |
| Thấy `permitAll` rồi giả định holder luôn trống | Hiểu sai delayed lookup | Phân biệt rule lookup với authentication filters |
| Cố dùng Servlet holder trong reactive pipeline | Sai context khi đổi thread | Dùng `ReactiveSecurityContextHolder`/Reactor Context |
| Log token, password hoặc toàn bộ principal | Rò credential/PII | Log ở mức cần thiết, mask thông tin nhạy cảm |

## 17. Checklist khi viết một đoạn kiểm tra quyền mới

1. **Chủ thể đến từ đâu?** Session, username/password, JWT hay cơ chế khác?
2. **Tại thời điểm nào?** Đang trong filter, controller, method interceptor, service hay task background?
3. **Ngữ cảnh luồng nào?** Servlet thread, task executor hay Reactor Context?
4. **Đối tượng đọc là gì?** `Authentication` toàn phần, `principal`, hay chỉ tên/ID đã xác minh?
5. **Có thể null/anonymous không?** Nếu có, chính sách xử lý là gì?
6. **Authority nào cần?** `ROLE_*`, permission nghiệp vụ hay `SCOPE_*` đã được map?
7. **Có cần policy theo tài nguyên không?** Tenant, owner, quan hệ chia sẻ, trạng thái?
8. **Có dùng lại context giữa lần gọi không?** Không giữ user ở singleton hay cache global.
9. **Quyền có cần mới nhất không?** Cần cơ chế refresh/revocation đối với role mới thu hồi?
10. **Kiểm thử đã bao phủ người dùng khác chưa?** Test allow/deny, anonymous, async, cross-tenant, expired token khi có liên quan.

### Câu hỏi tự đánh giá

**Câu 1.** `SecurityContextHolder.getContext()` trả về một đối tượng context, vậy `getAuthentication()` có chắc không `null` không?  
**Không**. Context có thể rỗng trước xác thực, ngoài request hoặc trong worker thread.

**Câu 2.** Vì sao `authentication.isAuthenticated()` có thể không đủ để nhận biết người dùng đăng nhập?  
Vì `AnonymousAuthenticationToken` có thể được đánh dấu authenticated; nên dùng semantics anonymous/authenticated do Spring Security cung cấp.

**Câu 3.** `AuthorizationFilter` có luôn buộc đọc Authentication trong mọi request không?  
**Không**. Các rule như `permitAll` và `denyAll` không nhất thiết gọi `Supplier<Authentication>.get()`.

**Câu 4.** `@PreAuthorize("hasAuthority('invoice:read')")` có tự quyết định người gọi được đọc hóa đơn của người khác không?  
**Không**. Nó mới kiểm tra authority; quyền trên từng hóa đơn phải có policy tài nguyên.

**Câu 5.** Vì sao `SecurityContextHolder` trong `@Async` có thể không chứa user của servlet request?  
Vì mặc định context gắn với `ThreadLocal` và worker là thread khác; cần cơ chế propagation rõ ràng khi nghiệp vụ yêu cầu.

**Câu 6.** Có thể chỉ `SecurityContextHolder.setContext(context)` để giữ login sang request tiếp theo không?  
**Không nên mặc định như vậy**. Cần xét `SecurityContextRepository` và cơ chế lưu context của authentication flow, đặc biệt custom login trong Spring Security 6.

**Câu 7.** Đọc Authentication ở 10:07 có bảo đảm role phản ánh thay đổi database lúc 10:05 không?  
**Không**. Authentication hiện hành có thể mang authorities cũ từ session/JWT; cần cơ chế freshness/revocation khi policy yêu cầu.

**Câu 8.** Cách đọc Authentication phù hợp với Spring WebFlux reactive là gì?  
Sử dụng `ReactiveSecurityContextHolder`/Reactor Context hoặc các cơ chế injection reactive được hỗ trợ, không dựa tùy tiện vào Servlet `ThreadLocal`.

## 18. Tài liệu chính thức để tra cứu

- Spring Security – Servlet Authentication Architecture (SecurityContextHolder, SecurityContext, Authentication): https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Authorize HTTP Requests (AuthorizationFilter, Supplier Authentication): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security (expression authentication/principal): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – Anonymous Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security – Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security – Concurrency Support: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security – Spring MVC Integration: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
