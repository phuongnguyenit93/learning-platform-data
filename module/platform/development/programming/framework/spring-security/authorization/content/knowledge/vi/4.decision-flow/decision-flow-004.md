# Supplier<Authentication> và việc lấy danh tính theo nhu cầu

## 1. Vấn đề: vì sao quyết định phân quyền lại nhận một Supplier?

Khi một yêu cầu HTTP đến ứng dụng Spring Security, hệ thống cần quyết định: **cho phép hay từ chối**. Không phải quyết định nào cũng cần biết người gửi là ai. Ví dụ, đường dẫn trạng thái công khai có thể được cho phép đối với mọi người, còn một URL chưa được đăng ký có thể bị từ chối với mọi người. Ở hai trường hợp đó, việc lấy danh tính chỉ để rồi không sử dụng là không cần thiết.

Đối với các quy tắc phụ thuộc quyền, hệ thống mới cần đọc `Authentication` hiện tại để kiểm tra danh tính, trạng thái xác thực và `GrantedAuthority`. Đó là lý do API `AuthorizationManager` trong Spring Security nhận một **`Supplier<Authentication>`** thay vì bắt mọi quy tắc phải nhận ngay một đối tượng `Authentication` đã được lấy sẵn.

Một `Supplier<T>` là giao diện hàm chuẩn của Java, có phương thức `T get()`. Nó đại diện cho một thao tác *có thể thực hiện khi cần*. Đối với `Supplier<Authentication>`, mục đích là trì hoãn việc truy xuất đối tượng xác thực cho tới khi quy tắc thật sự cần dùng.

```text
HTTP request
    |
    v
Security Filter Chain
    |
    v
AuthorizationFilter
    | tạo Supplier<Authentication>
    | chưa nhất thiết lấy Authentication
    v
AuthorizationManager
    |
    +-- permitAll / denyAll
    |       |
    |       +-- quyết định bằng rule, không cần gọi supplier.get()
    |
    +-- authenticated / hasAuthority / rule theo người dùng
            |
            +-- cần thông tin danh tính, gọi supplier.get()
                     |
                     v
                SecurityContext
                     |
                     v
                Authentication
                     |
                     v
              quyết định quyền (grant / deny)
```

**Mấu chốt:** “lấy danh tính theo nhu cầu” ở đây là **trì hoãn đọc `Authentication` từ ngữ cảnh bảo mật**, không có nghĩa mỗi lần gọi `get()` sẽ tự động đăng nhập người dùng, truy vấn IdP/LDAP hay làm mới token. Những thao tác xác thực hoặc tải quyền thuộc cơ chế khác.

## 2. Nhắc lại những thành phần trong luồng quyết định

| Thành phần | Vai trò |
| --- | --- |
| `Authentication` | Biểu diễn chủ thể và kết quả xác thực; chứa `principal`, `authorities`, thông tin bổ sung |
| `GrantedAuthority` | Quyền/role/scope có thể được quy tắc sử dụng, ví dụ `document:read` |
| `SecurityContext` | Chứa `Authentication` của luồng thực thi hiện tại |
| `SecurityContextHolder` | Cách ứng dụng truy cập `SecurityContext` (mặc định thường dựa trên `ThreadLocal` ở Servlet) |
| `Supplier<Authentication>` | Cung cấp `Authentication` khi `get()` được gọi |
| `AuthorizationManager<T>` | Quyết định cho phép/từ chối trên đối tượng được bảo vệ `T` |
| `AuthorizationFilter` | Đưa yêu cầu Servlet qua kiểm tra phân quyền trước khi tiếp tục xử lý |
| `RequestAuthorizationContext` | Ngữ cảnh request được dùng khi phân quyền HTTP |
| `SecurityFilterChain` | Chuỗi bộ lọc nơi xác thực, bảo vệ request và phân quyền phối hợp |

Một điểm dễ nhầm: `Authentication` không phải bản ghi hồ sơ người dùng đầy đủ trong database; nó là đối tượng biểu diễn danh tính và các authority mà cơ chế xác thực đã tạo ra. Việc `authentication.getName()` trả tên người dùng **không có nghĩa** mọi điều kiện truy cập tài liệu đã được kiểm tra.

### 2.1. Quy trình xác thực và phân quyền khác nhau

**Xác thực** giải mã/xác minh bearer token, kiểm tra thông tin đăng nhập, khôi phục phiên hoặc thiết lập principal tùy kiến trúc. **Phân quyền** đọc kết quả xác thực và đánh giá chính sách. Supplier trong `AuthorizationManager` là phương tiện truy cập kết quả ấy, không phải cách thay thế bước xác thực.

Ví dụ, với JWT resource server, bộ lọc xác thực bearer token có thể cần giải mã và xác minh JWT trước khi `AuthorizationFilter` chạy. Việc rule `permitAll()` không gọi supplier **không tự bảo đảm** mọi bộ lọc trước đó đều bỏ qua token hoặc không làm công việc khác.

### 2.2. `SecurityContextHolder` và ngữ cảnh hiện tại

Trong ứng dụng Servlet điển hình, Spring Security lưu ngữ cảnh cho luồng đang xử lý request, thường qua chiến lược dựa trên `ThreadLocal`. Khi rule cần `Authentication`, cơ chế cung cấp có thể đọc từ `SecurityContextHolder`. Tùy cách thiết lập `SecurityContextRepository` và bộ lọc, việc tải ngữ cảnh từ nơi lưu trữ cũng có thể được trì hoãn.

Đừng suy ra rằng đây là một cache toàn cục hay đối tượng sống mãi qua mọi request. Mỗi request phải đi qua chuỗi bảo mật phù hợp, và việc truyền ngữ cảnh sang luồng bất đồng bộ phải được thực hiện có chủ đích.

## 3. `Supplier<T>` trong Java: cơ chế trì hoãn rất đơn giản

### 3.1. Eager và lazy khác nhau thế nào?

Lấy dữ liệu sớm:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

// Đã yêu cầu đọc Authentication trước khi biết rule có cần.
boolean allowed = publicEndpoint || hasPermission(authentication);
```

Truy xuất theo nhu cầu (mã minh họa ý tưởng):

```java
Supplier<Authentication> authentication =
    () -> SecurityContextHolder.getContext().getAuthentication();

// Có thể quyết định cho phép ngay mà không gọi get().
boolean allowed = publicEndpoint
    || hasPermission(authentication.get());
```

Trong biểu thức thứ hai, Java dùng **short-circuit evaluation** của `||`: nếu `publicEndpoint` là `true`, vế phải không chạy và `authentication.get()` không được gọi. Đây là minh họa cơ chế Java, **không phải toàn bộ mã nội bộ của Spring Security**.

Một `Supplier` chỉ mô tả thao tác. **Tạo supplier không đồng nghĩa thực hiện thao tác**. Nhưng nếu tác giả rule tự gọi `get()` ở đầu hàm trước khi kiểm tra đường công khai, thì lại đánh mất lợi ích trì hoãn.

### 3.2. Lazy không đồng nghĩa memoization

Xét một supplier:

```java
Supplier<String> supplier = () -> expensiveLookup();
```

Mỗi lần gọi `supplier.get()` **có thể** thực hiện lại `expensiveLookup()`. Giao diện `Supplier` không hứa chỉ tính một lần, không tự cache kết quả và không bảo đảm kết quả bất biến. Tùy implementation, nó có thể trả một đối tượng đã nằm trong context hoặc truy cập một cơ chế tải trì hoãn khác.

Trong Spring Security, khi gọi `get()` nhiều lần, không nên tự kết luận số lần truy vấn database, số lần đọc session hay số lần kiểm tra token tương ứng một-một. Những chi tiết đó phụ thuộc các bộ lọc, `SecurityContextHolderStrategy`, `SecurityContextRepository` và implementation của supplier.

### 3.3. Trì hoãn việc đọc, không trì hoãn trách nhiệm kiểm tra

Nếu rule cần kiểm tra authority thì phải lấy `Authentication` đáng tin và so sánh quyền. Trì hoãn để tiết kiệm thao tác không được biến thành “không đọc được nên cho qua”:

```text
Nếu rule không phụ thuộc danh tính:
    quyết định theo chính sách tĩnh (permit / deny)

Nếu rule phụ thuộc danh tính:
    lấy Authentication từ nguồn bảo mật đáng tin
    nếu thiếu/không hợp lệ -> không tự cho phép
    nếu có -> đánh giá đầy đủ chính sách
```

Một custom manager cũng phải định nghĩa rõ kết quả khi không có quyết định. Trong Spring Security 6.3, `AuthorizationManager.check(...)` có thể trả `null` để biểu thị không đưa ra quyết định (*abstain*). Không nên dùng `null` để diễn đạt một lệnh từ chối nghiệp vụ quan trọng; trả `new AuthorizationDecision(false)` khi thực sự cần từ chối.

## 4. Java 17: ví dụ chạy độc lập để quan sát `get()`

Đoạn sau không phụ thuộc Spring Security. Nó dùng `Supplier<Identity>` để mô phỏng cơ chế “chỉ lấy danh tính khi rule cần”. Kết quả in ra số lần `get()` thực sự được gọi, giúp phân biệt **trì hoãn** và **cache**.

Lưu file `DeferredAuthenticationDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class DeferredAuthenticationDemo {

    enum Rule {
        PUBLIC,
        DENY,
        READ_DOCUMENT
    }

    record Identity(String name, Set<String> authorities) {}

    static boolean allowed(
            Supplier<Identity> identitySupplier,
            Rule rule
    ) {
        if (rule == Rule.PUBLIC) {
            return true; // Không gọi supplier.get()
        }
        if (rule == Rule.DENY) {
            return false; // Không gọi supplier.get()
        }

        // Chỉ rule này cần danh tính.
        Identity identity = identitySupplier.get();
        return identity != null
            && identity.authorities() != null
            && identity.authorities().contains("document:read");
    }

    public static void main(String[] args) {
        AtomicInteger lookups = new AtomicInteger();

        Supplier<Identity> currentIdentity = () -> {
            lookups.incrementAndGet();
            return new Identity(
                "An",
                Set.of("document:read")
            );
        };

        System.out.println(
            "public: " + allowed(currentIdentity, Rule.PUBLIC)
        );
        System.out.println(
            "deny: " + allowed(currentIdentity, Rule.DENY)
        );
        System.out.println(
            "lookups after constants: " + lookups.get()
        );

        System.out.println(
            "read document: "
                + allowed(currentIdentity, Rule.READ_DOCUMENT)
        );
        System.out.println(
            "lookups after first read: " + lookups.get()
        );

        System.out.println(
            "read again: "
                + allowed(currentIdentity, Rule.READ_DOCUMENT)
        );
        System.out.println(
            "lookups after second read: " + lookups.get()
        );

        Supplier<Identity> noPermission =
            () -> new Identity("Binh", Set.of());

        System.out.println(
            "missing permission: "
                + allowed(noPermission, Rule.READ_DOCUMENT)
        );
        System.out.println(
            "missing principal: "
                + allowed(() -> null, Rule.READ_DOCUMENT)
        );
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac DeferredAuthenticationDemo.java
java DeferredAuthenticationDemo
```

Kết quả chuẩn:

```text
public: true
deny: false
lookups after constants: 0
read document: true
lookups after first read: 1
read again: true
lookups after second read: 2
missing permission: false
missing principal: false
```

Phân tích:

1. Cả rule công khai và rule từ chối đều quyết định mà không cần danh tính: bộ đếm vẫn là `0`.
2. Lần đầu xem tài liệu phải đọc danh tính: bộ đếm thành `1`.
3. Gọi cùng supplier lần nữa vẫn thực hiện thân lambda: bộ đếm thành `2`; `Supplier` **không tự memoize**.
4. Không có permission hoặc không có principal thì không được đọc tài liệu.
5. Kết quả `false` ở ví dụ thuần Java là quy tắc do ta viết, **không diễn giải đầy đủ** ngoại lệ và xử lý anonymous của Spring Security.

Mọi `Identity` trong chương trình là dữ liệu giả phục vụ học. Trong ứng dụng thật, không nhận một `Supplier` từ HTTP request hoặc tin đối tượng `Identity` do client tự cung cấp; `Authentication` phải đến từ cơ chế xác thực đáng tin.

## 5. Luồng thật của Spring Security khi phân quyền HTTP

Phần này mô tả luồng Servlet dùng `authorizeHttpRequests` và `AuthorizationFilter` của Spring Security 6.x.

### 5.1. Bốn chặng của một quyết định

**Chặng 1 — Các bộ lọc xác thực chuẩn bị bối cảnh.** Tùy cơ chế (session, form login, bearer token...), Spring Security xử lý dữ kiện cần thiết để tạo/khôi phục `SecurityContext`. Không phải mọi request đều có user đăng nhập: có thể là anonymous, một request không được xác thực, hoặc ngữ cảnh chưa được tải tại thời điểm bắt đầu.

**Chặng 2 — `AuthorizationFilter` tạo supplier.** Bộ lọc này tạo một `Supplier<Authentication>` lấy danh tính hiện tại từ ngữ cảnh bảo mật và đưa supplier cùng request vào bộ `AuthorizationManager`. Vì supplier mới chỉ là khả năng lấy dữ liệu, bước này tự nó không bắt buộc phải truy xuất principal.

**Chặng 3 — `AuthorizationManager` chọn và đánh giá quy tắc.** Ví dụ, manager phân tuyến khớp các `requestMatchers(...)` để chọn rule phù hợp. Rule `permitAll()` hoặc `denyAll()` có thể trả quyết định ngay; các rule `authenticated()`, `hasAuthority(...)` hoặc kiểm tra theo principal cần lấy `Authentication`.

**Chặng 4 — Tiếp tục hoặc chặn.** Nếu được phép, chuỗi xử lý tiếp tục tới ứng dụng; nếu không, luồng bị chặn và các bộ lọc xử lý lỗi bảo mật phù hợp. Trong cấu hình API thường thấy, thiếu xác thực có thể dẫn tới 401, còn thiếu quyền có thể dẫn tới 403. Mã cụ thể còn tùy `AuthenticationEntryPoint`, `AccessDeniedHandler` và loại client.

### 5.2. Vì sao `permitAll()` và `denyAll()` thường không cần đọc danh tính?

Giả sử:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/internal/retired").denyAll()
    .requestMatchers("/api/reports/**")
        .hasAuthority("report:read")
    .anyRequest().denyAll()
);
```

- `GET /public/help`: chính sách quyết định cho mọi chủ thể được truy cập; quy tắc `permitAll` không cần lấy `Authentication`.
- `GET /internal/retired`: từ chối với mọi chủ thể; quy tắc `denyAll` không cần lấy `Authentication`.
- `GET /api/reports/7`: cần kiểm tra quyền `report:read` nên manager phải truy cập `Authentication`.
- Request chưa được quy tắc nào cho phép: quy tắc cuối `denyAll` từ chối; không phải tự tạo “quyền mặc định” cho người đã đăng nhập.

Điều này giúp giảm công việc đọc thông tin xác thực không cần thiết ở các điểm quyết định hằng số. **Không nên hiểu thành công bố “truy cập công khai không hề xử lý session/JWT”**: chuỗi lọc có thể đã thực hiện các thao tác khác trước khi đến bộ lọc phân quyền. Hiệu quả thực tế tùy cấu hình và luồng request.

### 5.3. Khi nào supplier được gọi?

| Rule hoặc tình huống | Có cần `Authentication` để ra quyết định? | Điều cần nhớ |
| --- | --- | --- |
| `permitAll()` | Không | Quyết định cho phép tĩnh |
| `denyAll()` | Không | Quyết định từ chối tĩnh |
| `hasAuthority("report:read")` | Có | Cần danh sách `GrantedAuthority` hiện hành |
| `hasRole("ADMIN")` | Có | Thường kiểm tra `ROLE_ADMIN` |
| `authenticated()` | Có | Cần phân biệt người thực sự xác thực với anonymous |
| Custom manager phụ thuộc user/tenant | Có | Gọi `get()` và kiểm tra ngữ cảnh, scope, đối tượng |
| Custom manager chỉ xét feature flag tĩnh | Có thể không | Không tự gọi `get()` nếu kết quả thật sự không phụ thuộc user |

Bảng nói về **nhu cầu của chính rule**, không là cam kết rằng supplier chỉ được gọi đúng một lần. Một custom manager có thể gọi nhiều lần, và các thành phần bảo mật khác có thể đã truy cập ngữ cảnh từ trước.

### 5.4. Anonymous authentication và biểu thức `isAuthenticated()`

Trong các cấu hình có `AnonymousAuthenticationFilter`, người chưa đăng nhập có thể được biểu diễn bởi `AnonymousAuthenticationToken`. Đối tượng này có thể báo `isAuthenticated() == true` theo hợp đồng đối tượng token, nhưng Spring Security vẫn nhận biết nó là **anonymous** khi dùng các bộ quản lý/biểu thức `authenticated()` tương ứng.

Vì vậy, với rule bảo vệ cần xác thực thật, **không tự thay** `authenticated()` bằng điều kiện `authentication != null && authentication.isAuthenticated()` rồi suy luận rằng đã chặn anonymous. Dùng chính sách xác thực của Spring Security hoặc `AuthenticationTrustResolver` thích hợp.

### 5.5. Thiếu `Authentication` không đồng nghĩa được truy cập

Nếu bộ lọc/manager cần `Authentication` mà context không chứa đối tượng hợp lệ, có thể xảy ra ngoại lệ liên quan đến thiếu thông tin xác thực và được bộ lọc khác xử lý. Chi tiết phụ thuộc chiến lược context và cấu hình authentication. Không nên viết custom manager thành:

```java
// SAI: thiếu context lại cho qua.
Authentication a = authentication.get();
if (a == null) {
    return new AuthorizationDecision(true);
}
```

Thay vào đó, chặn quyền hoặc để luồng lỗi xác thực chuẩn của Spring xử lý. Nếu sử dụng mã kiểm tra độc lập, `new AuthorizationDecision(false)` diễn đạt rõ quyết định từ chối.

## 6. Dùng `Supplier<Authentication>` trong một AuthorizationManager tùy chỉnh

### 6.1. Chọn đúng API của phiên bản đang dùng

Spring Security đã phát triển API theo phiên bản:

- Với **Spring Security 6.3**, `AuthorizationManager<T>` có phương thức chính `check(Supplier<Authentication>, T)` trả về `AuthorizationDecision` (hoặc `null` khi không đưa ra quyết định).
- Từ **Spring Security 6.4**, phương thức `authorize(...)`/kiểu kết quả mới được bổ sung, và API `check(...)` được đánh dấu deprecated ở các phiên bản sau. Khi nâng phiên bản, cần xem đúng JavaDoc và chữ ký đang sử dụng.
- Các ví dụ tiếp theo cố ý dùng **`check(...)` theo Spring Security 6.3**, phù hợp các dự án Spring Boot 3.3/Security 6.3. Không trộn chữ ký của Security 7 với code của 6.3.

Tài liệu chính thức: [AuthorizationManager 6.3.3 API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html) và [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

### 6.2. Một rule kiểm tra authority

Đoạn này là **mã tích hợp Spring Security 6.3 trong ứng dụng Servlet**, không phải file Java chạy độc lập:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class DocumentAuthorizationConfig {

    @Bean
    AuthorizationManager<RequestAuthorizationContext> documentReader() {
        return (authenticationSupplier, requestContext) -> {
            // Lấy Authentication vì quy tắc này cần authority.
            Authentication current = authenticationSupplier.get();

            boolean mayRead = current != null
                && current.getAuthorities().stream()
                    .anyMatch(authority ->
                        "document:read".equals(authority.getAuthority()));

            return new AuthorizationDecision(mayRead);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .access(documentReader())
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Điều đang diễn ra:

1. `requestMatchers(...)` chọn rule theo request; mã `documentReader()` được gọi khi xây cấu hình để lấy bean manager, còn việc **thực thi quyết định** trong lambda chỉ diễn ra khi request tương ứng đi qua phân quyền.
2. Vì `documentReader` cần authority, nó gọi `authenticationSupplier.get()`. Đây là điểm lấy `Authentication` theo nhu cầu.
3. Quy tắc so chuỗi `document:read` với `GrantedAuthority.getAuthority()`; nếu không có thì từ chối.
4. `.access(...)` gắn manager tùy chỉnh vào đường dẫn. `permitAll/denyAll` ở các tuyến khác không chạy logic đọc danh tính trong manager này.
5. Ví dụ không cấu hình xác thực: ở ứng dụng thật phải có cơ chế tạo `Authentication` phù hợp, chẳng hạn session login hoặc OAuth2 Resource Server.

Trong thực tế, nếu chỉ muốn kiểm tra đúng một authority, cách ngắn và được ưu tiên hơn là `.hasAuthority("document:read")`. Viết custom manager khi cần logic đặc biệt như ràng buộc theo request, chính sách nghiệp vụ hoặc dịch vụ quyền. **Đừng tự viết lại mọi tính năng xác thực/anonymous của framework.**

### 6.3. Rule custom trì hoãn theo điều kiện

Một manager có thể quyết định theo thông tin tĩnh trước và chỉ gọi supplier nếu cần. Ví dụ đoạn lambda minh họa (không phải lớp đầy đủ):

```java
AuthorizationManager<RequestAuthorizationContext> manager =
    (authentication, context) -> {
        String path = context.getRequest().getRequestURI();

        if ("/public/ping".equals(path)) {
            // Không gọi authentication.get() ở nhánh này.
            return new AuthorizationDecision(true);
        }

        if ("/admin/disabled".equals(path)) {
            return new AuthorizationDecision(false);
        }

        Authentication principal = authentication.get();
        boolean allowed = principal != null
            && principal.getAuthorities().stream()
                .anyMatch(a -> "document:read".equals(a.getAuthority()));

        return new AuthorizationDecision(allowed);
    };
```

Ở triển khai thật, ưu tiên dùng `requestMatchers` để chọn chính sách cho các tuyến khác nhau; tránh viết kiểm tra URL tự phát dễ sai vì context path, route variables, proxy, encoded URL, ký tự phân tách và phương thức HTTP. Mục đích đoạn mã là thấy rõ **vị trí đặt `get()`**.

Lưu ý về **kiểm tra quyền tài nguyên**: có `document:read` chưa đủ cho mọi tài liệu. Để xem `/api/documents/123`, service/repository còn phải xác minh tenant, chủ sở hữu, chia sẻ và trạng thái của tài liệu 123.

### 6.4. Vì sao supplier không phải giải pháp thay thế method security?

Request authorization quyết định việc đi qua tầng HTTP. Một hàm dịch vụ có thể được gọi từ job, message consumer hoặc một controller khác. Khi thao tác có ý nghĩa nghiệp vụ, vẫn cần kiểm tra tại điểm vào dịch vụ hoặc chính sách dữ liệu thích hợp. Supplier cung cấp danh tính để quyết định; nó **không đảm bảo** mọi nơi gọi chức năng đều đi qua cùng một manager.

Có thể dùng `@PreAuthorize("hasAuthority('document:read')")` và chính sách theo đối tượng tại service khi phù hợp. Nếu dùng method security qua Spring AOP proxy, phải hiểu self-invocation có thể bỏ qua proxy. Không lấy việc một URL đã được bảo vệ làm bảo đảm duy nhất cho quyền trên đối tượng.

## 7. Ranh giới tin cậy: supplier không tạo ra danh tính mới

Đây là phần quan trọng để tránh các suy luận sai khi tối ưu luồng quyết định.

### 7.1. Nguồn đáng tin là SecurityContext của request

Một bộ lọc xác thực đã được cấu hình đúng chịu trách nhiệm đưa `Authentication` đáng tin vào ngữ cảnh. Supplier trong authorization dùng kết quả này. Không viết:

```java
// SAI: người gọi tự gửi userId rồi tự tạo authority.
Supplier<Authentication> authentication =
    () -> new UsernamePasswordAuthenticationToken(
        request.getHeader("X-User"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
```

Đoạn trên **cố tình minh họa lỗi bảo mật**, không được dùng trong ứng dụng. Header `X-User` do client kiểm soát không chứng minh ai đang đăng nhập. Khi cần nhiều nguồn danh tính, phải xác thực qua chuỗi filter/provider đáng tin, không tự biến dữ liệu request thành principal có quyền.

### 7.2. Supplier không làm mới role/JWT khi gọi `get()`

Ví dụ một JWT chứa authority `report:approve` đã được xác minh và đưa vào `SecurityContext`. Nếu người dùng bị thu hồi quyền ở hệ thống IdP, gọi `authentication.get()` không tự động gọi IdP để kiểm tra lại nhóm mới. Quyền có hiệu lực đến đâu còn phụ thuộc thời hạn token, cơ chế thu hồi, tra cứu quyền động hoặc cách thiết kế session/cache.

Nếu ứng dụng yêu cầu thu hồi quyền gần thời gian thực, cần cơ chế rõ như token ngắn hạn, tra cứu policy theo request với cache và invalidation, hoặc revoke session/token theo kiến trúc; **không coi Supplier là một cơ chế revocation**.

### 7.3. Supplier không mặc nhiên an toàn qua thread

Trong Servlet, `SecurityContextHolder` mặc định sử dụng chiến lược gắn với luồng xử lý. Lưu supplier vào một field singleton hoặc đưa nó sang một executor rồi gọi `get()` có thể truy cập context khác hoặc không còn context sau request.

Khi chạy `@Async`, `CompletableFuture`, scheduled task hoặc message consumer, cần thiết kế rõ danh tính thực thi. Nếu cần mang security context có chủ đích, cân nhắc các công cụ truyền ngữ cảnh do Spring Security hỗ trợ (như `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` cho tác vụ tương ứng); đồng thời xác nhận thời điểm và phạm vi quyền. Không tự động sao chép session, credentials hay quyền của người gọi vào tác vụ nền tồn tại lâu dài.

### 7.4. Không chia sẻ supplier giữa các request

Một supplier được tạo để truy cập danh tính trong một request phải sống cùng phạm vi quyết định phù hợp. Đừng giữ trong biến `static`, singleton field hoặc cache toàn cục. Nếu supplier phụ thuộc thread-local, kết quả có thể thay đổi theo ngữ cảnh luồng, tạo lỗi nhận nhầm user hoặc vô tình cho phép sai.

Nếu cần cache quyết định quyền nghiệp vụ, hãy xác định khóa cache theo user/tenant/action/resource/phiên bản chính sách, thời hạn và cơ chế vô hiệu hóa. **Supplier không phải cache** và không giải quyết được vấn đề quyền bị lỗi thời.

## 8. Kiểm thử cơ chế trì hoãn và quyết định truy cập

Một bài kiểm thử tốt nên phân biệt ba điều: **rule có được chọn đúng không**, **rule có cần đọc Authentication không**, và **quyết định cuối có đúng quyền nghiệp vụ không**.

### 8.1. Ma trận kiểm thử

| Ca | Rule | Kỳ vọng quyết định | Kỳ vọng gọi `get()` |
| --- | --- | --- | --- |
| Endpoint public | `permitAll` | Cho phép | Quy tắc này không cần gọi |
| Endpoint luôn khóa | `denyAll` | Từ chối | Quy tắc này không cần gọi |
| API có đủ `document:read` | `hasAuthority` | Cho phép | Cần Authentication |
| API thiếu authority | `hasAuthority` | Từ chối | Cần Authentication |
| Chưa được xác thực | `authenticated` | Không cho vào API bảo vệ | Cần đánh giá trạng thái xác thực |
| Custom manager chỉ xét cấu hình tĩnh | Custom | Theo chính sách | Có thể bằng 0 |
| Custom manager xét tenant/owner | Custom | Theo chính sách thực tế | Cần principal và dữ liệu đối tượng |
| Manager gọi `get()` hai lần | Custom | Theo logic manager | Có thể là 2; không tự cache |
| Tác vụ nền không có context đúng | Custom dùng current context | Không tự cho phép | Phụ thuộc thiết kế context propagation |

**Lưu ý:** số lần gọi supplier trong một test mô phỏng chỉ chứng minh logic của manager đó. Đừng dùng counter ở một điểm để kết luận số lượt đọc DB/session/token trong toàn bộ pipeline.

### 8.2. Unit test cho manager của Spring Security 6.3

Đoạn dưới là **phần thân minh họa của một test JUnit**; giả sử đã có bean `AuthorizationManager<RequestAuthorizationContext> documentReader`, biến `HttpServletRequest request`, import các kiểu Spring Security và JUnit cần thiết:

```java
AtomicInteger calls = new AtomicInteger();

Authentication reader =
    new UsernamePasswordAuthenticationToken(
        "an",
        null,
        List.of(new SimpleGrantedAuthority("document:read"))
    );

Supplier<Authentication> supplier = () -> {
    calls.incrementAndGet();
    return reader;
};

RequestAuthorizationContext context =
    new RequestAuthorizationContext(request);

AuthorizationDecision result =
    documentReader.check(supplier, context);

assertNotNull(result);
assertTrue(result.isGranted());
assertEquals(1, calls.get());
```

Đoạn code cho thấy cách xác nhận manager có gọi `get()` khi cần authority; nó **không phải chương trình Java độc lập**. Test tương ứng với người thiếu quyền nên có `AuthorizationDecision(false)`. Với một rule công khai, tạo supplier ném `AssertionError` khi bị gọi sẽ giúp kiểm tra không truy cập danh tính ngoài ý muốn:

```java
Supplier<Authentication> unexpectedLookup = () -> {
    throw new AssertionError("Authentication should stay deferred");
};

// Gọi manager thực sự đại diện cho permitAll theo cấu hình test.
// Nếu nó gọi unexpectedLookup.get(), test phải thất bại.
```

Cần nhớ: trong Spring Security 6.4 trở lên, API có thể sử dụng `authorize(...)` với kiểu kết quả mới. Không sao chép nguyên chữ ký của phiên bản khác rồi suy đoán lỗi do supplier.

### 8.3. Kiểm thử tích hợp với `MockMvc`

Trong ứng dụng Spring MVC có `spring-security-test`, kiểm tra tuyến công khai, tuyến có quyền, thiếu quyền và chưa đăng nhập bằng `MockMvc`. Đối với POST/PATCH/DELETE, nếu CSRF bật, test nên kèm token CSRF hợp lệ khi muốn kiểm tra chính sách phân quyền; nếu không, mã 403 có thể chỉ do CSRF.

Một số test helper như `user(...)` hoặc `jwt(...)` thiết lập principal giả lập, không chứng minh mật khẩu, chữ ký JWT, audience hoặc issuer đã được xác thực trong môi trường thật. Cần thêm kiểm thử xác thực riêng khi điều đó là yêu cầu.

### 8.4. Kiểm tra hiệu năng theo đúng bằng chứng

Để đánh giá lợi ích trì hoãn, có thể đo:

- Số request vào tuyến công khai/tuyến luôn bị khóa.
- Số lần truy cập ngữ cảnh, số lần tải session khi cấu hình cho phép đo.
- Thời gian xử lý phân quyền và tỷ lệ cache hit, nếu có.
- Chi phí xác thực bearer token, truy vấn database và các bộ lọc trước đó.

Nếu đo tổng request và thấy không cải thiện, đừng kết luận `Supplier` vô dụng: phần lớn chi phí có thể nằm ở bộ lọc khác hoặc nghiệp vụ. Ngược lại, không tuyên bố “permitAll không chạm database” nếu chưa đo trong kiến trúc cụ thể.

## 9. Lỗi phổ biến khi dùng `Supplier<Authentication>`

| Lỗi | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| Gọi `get()` ngay đầu mọi manager | Mất lợi ích trì hoãn ở nhánh tĩnh | Chọn rule trước, chỉ đọc khi cần |
| Giả định `Supplier` là cache | `get()` nhiều lần có thể thực hiện thao tác nhiều lần | Hiểu implementation; nếu cần cache, thiết kế rõ phạm vi |
| Nghĩ `get()` sẽ xác thực lại JWT | Quyền cũ có thể còn hiệu lực | Tách xác thực token, refresh và revocation |
| Nghĩ `permitAll` bỏ qua toàn bộ filter chain | Token/session hoặc bộ lọc khác vẫn có thể chạy | Phân biệt rule authorization với toàn pipeline |
| Tự kiểm tra `auth.isAuthenticated()` là đủ | Anonymous token có thể được coi là authenticated theo cờ nội bộ | Dùng quy tắc `authenticated()` và trust resolver |
| Thiếu auth thì `allow = true` | Mở API bảo vệ | Mặc định từ chối hoặc để framework xử lý lỗi |
| Dùng `null` để diễn đạt từ chối | Có thể biểu thị abstain, gây hiểu sai điều kiện | Trả `AuthorizationDecision(false)` khi cần deny |
| Lấy role từ header client và gói vào supplier | Người dùng có thể tự cấp quyền | Chỉ lấy principal/authority từ nguồn xác thực đáng tin |
| Giữ supplier trong singleton/async job | Context luồng bị sai hoặc hết hạn | Giữ đúng request scope, truyền context có kiểm soát |
| Chỉ bảo vệ URL, bỏ quyền đối tượng | IDOR/BOLA: đổi ID truy cập dữ liệu người khác | Bảo vệ ở service/repository và theo tenant |
| Trộn API `check` 6.3 và `authorize` 6.4+ | Mã không khớp phiên bản, lỗi khi nâng cấp | Tra JavaDoc đúng phiên bản |
| Suy ra số lần đọc DB từ số lần `get()` | Đánh giá hiệu năng sai | Đo theo tầng context repository và authentication |

## 10. Quy trình áp dụng trong dự án

1. **Xác nhận phiên bản Spring Security** đang sử dụng để chọn đúng chữ ký `AuthorizationManager`. Với Spring Boot 3.3 / Security 6.3, dùng `check(...)` trong ví dụ custom manager.
2. **Vẽ đường đi của request** qua chuỗi bảo mật: authentication filter, context, `AuthorizationFilter`, manager, handler/controller và service.
3. **Định nghĩa chính sách URL**: endpoint công khai, endpoint luôn chặn, endpoint cần authority. Dùng `anyRequest().denyAll()` để đóng trường hợp chưa xét.
4. **Chỉ viết custom manager khi cần** và dùng supplier đúng mục đích: rule tĩnh không đọc, rule theo danh tính gọi `get()` khi đánh giá.
5. **Xác minh dữ liệu nhận từ Authentication**: principal, authority, cơ chế ánh xạ role/scope; không suy ra tenant/owner từ request chưa kiểm chứng.
6. **Bảo vệ nghiệp vụ và dữ liệu** ở service/repository, bao gồm truy cập cùng tài nguyên qua kênh khác HTTP.
7. **Kiểm thử** tuyến công khai/từ chối/đủ quyền/thiếu quyền/anonymous, kiểm tra count trong unit test và test dữ liệu không bị lộ.
8. **Kiểm tra hành vi async và thu hồi quyền** nếu hệ thống dùng queue, background job, token dài hạn hoặc session cache.
9. **Đo hiệu năng thực tế** khi tối ưu là mục tiêu; không mặc định rằng mọi supplier đều tiết kiệm cùng một lượng tài nguyên.
10. **Rà soát khi nâng cấp**: JavaDoc và test phải đi cùng phiên bản Spring Security trong dự án.

## 11. Câu hỏi tự kiểm tra

1. **Vì sao `AuthorizationManager` nhận `Supplier<Authentication>`?** Để chỉ lấy danh tính khi cần quyết định dựa trên principal/authority, tránh truy xuất không cần ở rule tĩnh.
2. **Tạo supplier có tự lấy Authentication không?** Không; thân supplier được thực hiện khi `get()` được gọi.
3. **`permitAll()` có bảo đảm không bộ lọc nào truy cập session/JWT không?** Không. Chỉ có thể khẳng định rule cho phép tĩnh không cần đọc Authentication để ra quyết định.
4. **Gọi `get()` hai lần có tự trả cùng kết quả cached không?** Không có bảo đảm từ giao diện `Supplier`; implementation quyết định.
5. **`get()` có kiểm tra lại nhóm ở IdP sau khi user bị thu hồi quyền không?** Không tự động; cần cơ chế xác thực/làm mới/thu hồi riêng.
6. **Vì sao `isAuthenticated()` đơn lẻ dễ sai với anonymous?** Vì token anonymous có thể được đánh dấu authenticated về mặt đối tượng; quy tắc `authenticated()` có cách phân biệt phù hợp.
7. **Có `document:read` thì đọc được tài liệu của tenant khác không?** Không; phải kiểm tra chính sách theo tài nguyên.
8. **Supplier đặt trong singleton rồi dùng ở thread khác có an toàn không?** Không thể giả định; context mặc định gắn với luồng và phạm vi request, cần truyền context có chủ đích.
9. **Spring Security 6.3 gọi phương thức chính nào của `AuthorizationManager`?** `check(Supplier<Authentication>, T)`; các phiên bản về sau có `authorize(...)`.
10. **Nếu custom manager không thể xác minh danh tính nhưng thao tác nhạy cảm thì sao?** Không tự cho phép; từ chối an toàn hoặc để cơ chế lỗi xác thực chuẩn xử lý.

**Ghi nhớ:** `Supplier<Authentication>` là một **điểm truy xuất danh tính trì hoãn trong luồng quyết định**. Nó giúp rule tĩnh không phải truy cập danh tính và cho rule phụ thuộc quyền lấy `Authentication` đúng lúc. Nó **không thay thế xác thực**, **không tự cache**, **không tự thu hồi quyền**, và **không thay thế kiểm tra tenant/đối tượng ở tầng nghiệp vụ**.