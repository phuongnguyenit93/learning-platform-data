# AuthorizationManager và cách biểu diễn quyết định cho phép hoặc từ chối (Spring Security Servlet)

## 1. Vì sao cần một mô hình ra quyết định phân quyền?

Trong ứng dụng Spring Security Servlet, **xác thực** (authentication) trả lời “request này đại diện cho ai?”, còn **phân quyền** (authorization) trả lời “danh tính đó có được thực hiện hành động này trên tài nguyên này không?”.

Ví dụ một API báo cáo có các yêu cầu:

- Người chưa đăng nhập được xem `GET /public`.
- `lan` được đọc báo cáo `r101` nhưng không được đọc báo cáo `r202` của `minh`.
- Người có vai trò `ADMIN` được xem cả hai báo cáo, nếu các quy tắc nghiệp vụ khác cho phép.
- Tài khoản bình thường không được mở `GET /finance/export`.
- Tác vụ nhạy cảm có thể yêu cầu đồng thời `ROLE_ADMIN` **và** trạng thái xác thực đầy đủ.

Nếu viết quyền rải rác bằng `if` trong từng controller, ta dễ bỏ sót một endpoint, không nhất quán giữa các API và khó kiểm thử. **`AuthorizationManager<T>`** là abstraction của Spring Security dùng để đưa ra **quyết định cho phép hay từ chối** dựa trên Authentication và đối tượng được bảo vệ.

Mục tiêu sau bài:

1. Hiểu interface `AuthorizationManager<T>`, `Supplier<Authentication>` và tham số context `T`.
2. Phân biệt quyết định **granted**, **denied** và khả năng **abstain** ở API Spring Security 6.3.x.
3. Hiểu vị trí `AuthorizationFilter`, `ExceptionTranslationFilter` và policy trong Servlet filter chain.
4. Biết cách dùng manager có sẵn và tự viết manager kiểm tra vai trò + quyền sở hữu đối tượng.
5. Phân biệt “request khớp matcher” với “request được cấp quyền”.
6. Viết kiểm thử MockMvc chứng minh các phản hồi 200, 401, 403 bằng request HTTP thật.
7. Biết các giới hạn: CSRF, chủ sở hữu resource, multi-tenant, method security, audit, hiệu năng và race condition.

**Phạm vi ví dụ:** Java 17, Spring Boot 3.3.5, Spring Security 6.3.x trên Servlet stack. Tên API và các cơ chế bổ sung có thể thay đổi ở Spring Security mới hơn; khi nâng phiên bản cần kiểm tra tài liệu chính thức tương ứng.

## 2. Hợp đồng AuthorizationManager<T>

Interface chính là `org.springframework.security.authorization.AuthorizationManager<T>`. Trong Spring Security 6.3.x, các thành phần cần nắm:

```java
// Chữ ký khái niệm; đặt trong ngữ cảnh có imports phù hợp.
// Không copy đoạn này để định nghĩa lại AuthorizationManager của thư viện.
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T object
);

void verify(
    Supplier<Authentication> authentication,
    T object
);
```

Điểm quan trọng:

- `authentication` là một **Supplier**: đối tượng có thể cung cấp `Authentication` khi manager cần dùng; không phải lúc nào cũng phải gọi nó.
- `object` là context được bảo vệ, phụ thuộc loại manager: với HTTP Servlet thường là `RequestAuthorizationContext`; ở cơ chế khác có thể là một đối tượng khác.
- `check(...)` biểu diễn kết quả ra quyết định. Với API `AuthorizationDecision` trong bài, `new AuthorizationDecision(true)` biểu diễn cho phép và `new AuthorizationDecision(false)` biểu diễn từ chối.
- Trong contract của thế hệ API này, `check(...)` **có thể trả null để abstain** (không đưa ra quyết định). **Null không phải một quyết định allow** và không được dùng như “mặc định cho phép”.
- `verify(...)` là phương thức hỗ trợ thực thi việc kiểm tra; khi kết quả là **deny** có thể ném `AccessDeniedException`. Không tự suy rằng một `null` từ manager là quyết định deny nếu chưa xét cơ chế kết hợp/enforcement.

Đây là đoạn API mang tính giải thích, không phải nguyên một class độc lập. Tại source Java thật, `Supplier` thuộc `java.util.function`, `Authentication` thuộc `org.springframework.security.core`, và `AuthorizationDecision`/`AuthorizationManager` thuộc `org.springframework.security.authorization`.

### 2.1. Ý nghĩa của generic T

`AuthorizationManager<T>` không chỉ dành cho một loại endpoint. Generic `T` cho biết **đối tượng đang được ủy quyền**:

| Loại chính sách | `T` thường gặp | Ngữ cảnh xem xét |
| --- | --- | --- |
| HTTP Servlet request | `RequestAuthorizationContext` | `HttpServletRequest`, biến đường dẫn, dữ liệu HTTP phù hợp |
| URL/filter integration ở API đời khác | Có thể dùng context/filter invocation khác | Cần kiểm tra version |
| Method security | Context lời gọi phương thức hoặc đối tượng method invocation | Method, args, kết quả, annotations theo cơ chế |
| Custom integration | Context do ứng dụng định nghĩa | Resource, action, tenant, thông tin đã xác minh |

Không thể lấy tùy tiện một `AuthorizationManager<RequestAuthorizationContext>` rồi gắn vào vị trí cần `AuthorizationManager<MethodInvocation>` mà mong compiler/framework tự chuyển context.

### 2.2. Supplier<Authentication> và phép đánh giá lười

Vì manager nhận supplier, nó có thể **chỉ lấy Authentication khi thực sự cần**:

```java
AuthorizationManager<RequestAuthorizationContext> demoPolicy =
    (authenticationSupplier, context) -> {
        // Chỉ trong manager có nhu cầu mới gọi get().
        Authentication current = authenticationSupplier.get();
        boolean allowed = current != null
            && current.isAuthenticated();

        return new AuthorizationDecision(allowed);
    };
```

Đây là **mảnh code minh họa trong class đã có imports**, không phải khuyến nghị dùng cờ `isAuthenticated()` đơn lẻ cho policy thật. Với anonymous, `AnonymousAuthenticationToken.isAuthenticated()` có thể là true; trong ví dụ chạy được bên dưới sẽ dùng `AuthenticationTrustResolver`.

**Tại sao dùng supplier?** Một số quyết định, ví dụ `permitAll` hoặc `denyAll`, không cần đọc principal. Việc truy xuất SecurityContext/Authentication không cần thiết có thể được tránh trong những code path đó. Đừng ép gọi `supplier.get()` ở mọi request chỉ vì có supplier.

## 3. AuthorizationDecision: granted, denied và abstain

### 3.1. Quyết định tường minh

Trong Spring Security 6.3.x:

```java
AuthorizationDecision allow =
    new AuthorizationDecision(true);

AuthorizationDecision deny =
    new AuthorizationDecision(false);

boolean granted = allow.isGranted(); // true
boolean denied = deny.isGranted();   // false
```

`AuthorizationDecision` chứa trạng thái granted/denied; nó **không** là đối tượng biểu diễn HTTP response code hay body. Cùng một quyết định deny có thể dẫn đến 302, 401 hoặc 403 tùy cơ chế authentication/exception handling.

Ví dụ:

- `new AuthorizationDecision(true)` → policy cho phép tiếp tục nếu không có lớp kiểm tra khác chặn.
- `new AuthorizationDecision(false)` → policy từ chối; tầng enforcement xử lý exception/response thích hợp.

### 3.2. Null/abstain là gì?

Một custom manager có thể trả `null` để diễn tả **không có kết luận** theo contract cũ. Đây không phải “allow” và cũng không có nghĩa tất cả manager sẽ hiểu nó như “deny”.

```java
// CHỈ MINH HỌA contract cũ: tránh trả null tùy tiện trong policy cuối.
AuthorizationManager<RequestAuthorizationContext> undecided =
    (authenticationSupplier, context) -> null;
```

Khi kết hợp nhiều managers hoặc dùng một API khác, cách xử lý abstain phụ thuộc implementation/combinator. Vì vậy:

- Nếu một policy **chịu trách nhiệm cuối cùng** cho một resource, nên trả `AuthorizationDecision(true/false)` tường minh.
- Với dữ liệu không tồn tại hoặc context không đúng, thông thường trả deny trong manager cuối.
- Nếu có nhiều policies, thiết kế rõ thứ tự và ngữ nghĩa tổng hợp “all of/any of”, bao gồm trường hợp không policy nào ra quyết định.
- Đừng viết `return null` khi xảy ra lỗi DB vì “không biết thì cho qua”; thiếu thông tin cần được xử lý có kiểm soát, thường **fail closed**.

### 3.3. Phân biệt denied và lỗi runtime

Một quyết định deny là kết quả chính sách có chủ đích. Timeout DB, lỗi network hoặc exception không mong muốn là **lỗi thực thi**, không phải bằng chứng người dùng thiếu quyền. Hệ thống phải tránh leak dữ liệu và không fail-open, đồng thời cần log/metric/alert phù hợp.

Không bắt mọi exception rồi `return new AuthorizationDecision(true)`. Ngược lại, cũng không nên che giấu sự cố hệ thống bằng cách báo “sai mật khẩu” cho mọi 500.

### 3.4. API mới hơn

Tùy version, Spring Security có các abstraction kết quả authorization mới hơn, chẳng hạn `AuthorizationResult` và các phương thức bổ sung/thay đổi so với `AuthorizationDecision`. Mã trong bài **pin Spring Boot 3.3.5 / Spring Security 6.3.x** nên dùng `AuthorizationDecision` và `check(...)`. Khi nâng cấp, kiểm tra chữ ký/deprecation chính thức thay vì suy diễn API version mới là hoàn toàn giống API này.

## 4. AuthorizationManager nằm ở đâu trong Servlet request flow?

Một sơ đồ thông thường:

```text
HTTP request
     |
     v
DelegatingFilterProxy
     |
     v
FilterChainProxy
     |
     v
SecurityFilterChain được chọn
     |
     +-- SecurityContext handling / Authentication filters
     |        -> tạo hoặc khôi phục Authentication
     |
     +-- ExceptionTranslationFilter
     |        -> xử lý bảo mật khi có exception phù hợp
     |
     +-- AuthorizationFilter
              |
              +-- nhận Supplier<Authentication>
              +-- đưa request vào AuthorizationManager
              +-- rule matcher được chọn
              +-- decision GRANTED / DENIED
              |
              +-- GRANTED -> tiếp tục tới controller
              +-- DENIED  -> AccessDeniedException / exception handling
```

Trong các cấu hình HTTP Servlet hiện đại, `AuthorizationFilter` là điểm thực thi quyết định của `AuthorizationManager`. `ExceptionTranslationFilter` thường xử lý exception liên quan authorization/authentication, lựa chọn entry point hoặc access denied handler tương ứng.

Đây là **mô hình khái niệm**, không phải bản cam kết thứ tự mọi filter có thể thêm bởi ứng dụng. Một số request có thể bị từ chối trước AuthorizationFilter, ví dụ CSRF hoặc firewall.

### 4.1. Phân biệt PEP và PDP

Các từ kiến trúc thường gặp:

- **PEP (Policy Enforcement Point)**: nơi áp đặt quyết định — ở ví dụ HTTP, `AuthorizationFilter` có vai trò này.
- **PDP (Policy Decision Point)**: nơi tính quyết định — ở ví dụ, `AuthorizationManager` có vai trò này.
- **PIP (Policy Information Point)**: nguồn thuộc tính/dữ liệu policy cần — ví dụ repository báo cáo cho biết báo cáo nào thuộc user nào.

Không phải mọi ứng dụng phải hiện thực cả ba như một dịch vụ độc lập. Phân biệt trách nhiệm giúp tránh vừa truy vấn dữ liệu, vừa tạo HTTP response, vừa gửi email từ bên trong một matcher/policy khó test.

### 4.2. Authorization granted chưa chắc HTTP 200

Ngay cả khi `AuthorizationManager` trả granted:

- Controller có thể trả 404 nếu resource không tồn tại.
- Business validation có thể trả 400.
- Method security có thể từ chối vì chính sách sâu hơn.
- Một filter trước đó có thể đã xử lý request khác dự kiến.
- Controller có thể lỗi 500.
- CSRF filter có thể chặn POST trước khi authorization.

**Manager quyết định cho phép đi tiếp theo chính sách của nó**, chứ không phải quyết định status code cuối cùng của toàn request.

## 5. RequestMatcher chọn rule; AuthorizationManager quyết định quyền

Trong `authorizeHttpRequests`, ví dụ:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/reports/{reportId}").access(reportAccessPolicy)
    .anyRequest().denyAll()
);
```

Có hai tầng:

1. `requestMatchers("/reports/{reportId}")` trả lời “HTTP request có thuộc route này không?”.
2. `reportAccessPolicy` trả lời “principal có quyền trên báo cáo cụ thể được yêu cầu không?”.

Không nên hiểu rằng khi route matcher true thì user đã được grant. Ngược lại, một manager cho phép cũng không tự khiến URL khác được match.

### 5.1. Thứ tự matcher đầu tiên phù hợp

`authorizeHttpRequests` thường áp dụng **request matcher đầu tiên phù hợp**. Đây là lỗi nguy hiểm:

```java
// KHÔNG đúng khi /reports/internal/** cần policy riêng:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/reports/**").permitAll()
    .requestMatchers("/reports/internal/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Matcher `/reports/**` đứng trước đã xử lý internal URL. Đặt rule cụ thể trước rule rộng, và dùng một custom AuthorizationManager nếu cần kết hợp nhiều điều kiện quyền.

Trong nhiều `SecurityFilterChain`, `securityMatcher` chọn **chain** đầu tiên phù hợp; `requestMatchers` chọn **authorization rule** trong chain đã được chọn. Đừng nhầm hai phạm vi.

### 5.2. Mặc định nên fail closed

Đối với endpoint chưa có policy rõ ràng, một cấu hình có thể dùng `.anyRequest().denyAll()` để tránh route mới vô tình công khai. Khi dùng fallback này, nhớ khai báo hợp lệ đường dẫn login, error, static asset hoặc health nếu sản phẩm cần chúng được truy cập.

Ở ví dụ API HTTP Basic bên dưới, chỉ route `/public` được công khai; còn các route nghiệp vụ được bảo vệ bằng manager riêng.

## 6. Các AuthorizationManager dựng sẵn

Spring Security cung cấp các thành phần giải quyết những trường hợp thường gặp:

| API hoặc cơ chế | Ý nghĩa tổng quát |
| --- | --- |
| `permitAll()` | Cho phép request phù hợp mà không yêu cầu xác thực |
| `denyAll()` | Từ chối request phù hợp |
| `authenticated()` | Yêu cầu authentication không phải anonymous theo trust resolver |
| `fullyAuthenticated()` | Yêu cầu authentication không phải anonymous và không phải remember-me |
| `hasRole("ADMIN")` | Yêu cầu authority theo quy ước `ROLE_ADMIN` |
| `hasAuthority("report:read")` | Yêu cầu authority đúng tên |
| `AuthorityAuthorizationManager` | Manager kiểm tra role/authority theo cấu hình |
| `AuthenticatedAuthorizationManager` | Manager kiểm tra mức tin cậy authentication |
| `AuthorizationManagers.allOf(...)` | Kết hợp các manager theo logic tương tự AND |
| `AuthorizationManagers.anyOf(...)` | Kết hợp các manager theo logic tương tự OR |

Cách kết hợp thực tế cần xét **ngữ nghĩa abstain/deny** theo version. Với policy cuối cùng nhạy cảm, việc đưa ra quyết định rõ ràng và test đủ tình huống quan trọng hơn việc chỉ đọc tên combinator.

### 6.1. Quyền và độ tin cậy là hai trục

Ví dụ `hasRole("ADMIN")` **không mặc định** yêu cầu fully authenticated. Người dùng được nhận diện qua remember-me có thể vẫn mang `ROLE_ADMIN`. Nếu tài nguyên rất nhạy cảm, có thể yêu cầu đồng thời:

```text
request thuộc /finance/export
AND AuthenticationTrustResolver.isFullyAuthenticated(current)
AND current có ROLE_ADMIN
AND các policy nghiệp vụ khác (nếu có)
```

Trong ví dụ, một custom manager biểu diễn rõ điều kiện AND này. Tuy vậy, fully authenticated **không chứng minh MFA mới thực hiện**; nếu cần step-up/recent authentication phải thiết kế chính sách bổ sung.

### 6.2. Kiểm tra authority không đủ cho resource ownership

`hasRole("READER")` cho phép user mang vai trò đọc, nhưng không tự phân biệt báo cáo của `lan` và `minh`. Object-level authorization cần một nguồn sự thật (repository/domain service) để xác nhận owner/tenant và action được phép.

Đây là tình huống phù hợp để viết `AuthorizationManager<RequestAuthorizationContext>` riêng hoặc method security tùy kiến trúc.

## 7. RequestAuthorizationContext và path variables

Với HTTP Servlet, một manager có thể dùng `RequestAuthorizationContext`:

```java
// Minh họa trong class với RequestAuthorizationContext:
HttpServletRequest request = context.getRequest();
String reportId = context.getVariables().get("reportId");
String method = request.getMethod();
```

`getVariables()` mang các biến đường dẫn mà matcher có hỗ trợ trích xuất, chẳng hạn khi dùng matcher Spring MVC phù hợp với `/reports/{reportId}`. **Không nên mặc định** một matcher bất kỳ luôn cung cấp cùng các biến.

Với ứng dụng Spring MVC và Spring Security 6.3.x, DSL:

```java
.requestMatchers("/reports/{reportId}").access(reportAccessPolicy)
```

có thể sử dụng MVC-aware matching khi điều kiện framework phù hợp, giúp đẩy biến `reportId` vào `RequestAuthorizationContext`. Ví dụ integration test sẽ trực tiếp kiểm chứng biến này thực sự được truyền trong môi trường Spring Boot cụ thể.

### 7.1. Path variable là dữ liệu không đáng tin

Ngay cả khi matcher trích `reportId` thành công, giá trị đó do client đưa vào URL. Manager phải tra ID trong repository đáng tin, không suy ra ownership từ một giá trị query/header do browser tự khai.

Sai lầm:

```java
// Không an toàn: không lấy ownership chỉ từ tham số tự khai báo của client.
boolean allow = request.getParameter("owner")
    .equals(authentication.get().getName());
```

Attacker có thể tự đổi `owner=lan`. Chính sách đúng cần đối chiếu báo cáo thực sự thuộc ai ở kho server; tránh IDOR/BOLA.

### 7.2. Không tồn tại cũng phải có quyết định rõ

Nếu path variable không có, report ID sai hoặc repository không tìm ra báo cáo, manager cuối thường nên trả **deny** hoặc triển khai cơ chế trả 404 phù hợp policy, nhưng không `return true` hay `return null` “cho qua vì thiếu dữ liệu”.

Việc trả 403 hay 404 cho tài nguyên không tồn tại còn là quyết định thiết kế API, có thể được điều chỉnh để tránh enumeration. Ví dụ đơn giản ưu tiên deny ở manager và kiểm thử 403.

## 8. Viết custom AuthorizationManager đúng trách nhiệm

Một manager tốt nên:

- Nhận Authentication/context, đọc dữ liệu **cần** cho quyết định.
- Trả kết quả allow/deny tường minh.
- Không ghi dữ liệu nghiệp vụ hoặc làm thao tác có side effect trong `check`.
- Không tin header hoặc query tự khai báo về role/owner.
- Không để lỗi DB dẫn đến `AuthorizationDecision(true)`.
- Không log password, token, session ID hay thông tin nhạy cảm của principal.
- Có test đơn vị cho quyết định và integration test cho HTTP filter chain.
- Cân nhắc hiệu năng, số lần truy vấn và cache invalidation.
- Đảm bảo đồng nhất với policy ở service và phương thức, đặc biệt khi controller còn xử lý nhiều resource.

### 8.1. Mô hình policy báo cáo

Định nghĩa:

```text
reportOwner("r101") = "lan"
reportOwner("r202") = "minh"

allow(GET /reports/{reportId}) nếu:
   authentication hợp lệ và không anonymous
   AND reportId tồn tại trong kho server
   AND (
       username == reportOwner(reportId)
       OR authority == ROLE_ADMIN
   )
```

Điều kiện admin chỉ là ví dụ nghiệp vụ. Trong hệ thống đa tenant, một admin của tenant A **không nhất thiết** được xem mọi báo cáo tenant B. Role, tenant, scope và account state phải xác định theo chính sách thật.

### 8.2. Khi nào gọi Authentication supplier?

Trong manager này phải biết username và authorities mới quyết định được, nên gọi `authenticationSupplier.get()`. Ở route `/public` sử dụng `permitAll`, framework có thể không cần resolve Authentication.

Điều quan trọng là **đúng mục đích**, không phải cố tránh supplier bằng mọi giá. Nếu context đã bị từ chối do thiếu reportId, manager có thể trả deny ngay mà không cần nạp principal.

## 9. Demo Spring Boot 3.3.5 + Java 17 hoàn chỉnh

Ví dụ chạy được gồm:

- `GET /public`: public.
- `GET /reports/{reportId}`: owner hoặc admin, dùng custom manager.
- `GET /finance/export`: chỉ admin và fully authenticated.
- Mọi URL khác: deny.
- HTTP Basic giúp dễ kiểm thử 401/403/200; ví dụ không triển khai form login hoặc remember-me cookie.

Tài khoản demo:

| Username | Password (chỉ demo) | Authorities | Báo cáo sở hữu |
| --- | --- | --- | --- |
| `lan` | `lan-demo` | `ROLE_USER` | `r101` |
| `minh` | `minh-demo` | `ROLE_USER` | `r202` |
| `admin` | `admin-demo` | `ROLE_ADMIN` | Không cần là owner trong policy mẫu |

**Chỉ sử dụng trên localhost thử nghiệm.** HTTP Basic mã hóa Base64 chứ không bảo mật password trên dây; production bắt buộc HTTPS và bí mật thật không được hardcode.

### 9.1. Cấu trúc dự án

```text
authorization-manager-demo/
  pom.xml
  src/
    main/java/example/authorization/
      AuthorizationDemoApplication.java
      SecurityConfig.java
      ReportOwnerStore.java
      ReportAccessPolicy.java
      AdminFullPolicy.java
      DemoController.java
    test/java/example/authorization/
      AuthorizationManagerIntegrationTest.java
```

### 9.2. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>authorization-manager-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

### 9.3. Main class

File `src/main/java/example/authorization/AuthorizationDemoApplication.java`:

```java
package example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
```

### 9.4. ReportOwnerStore: server-side dữ liệu quyền sở hữu

File `src/main/java/example/authorization/ReportOwnerStore.java`:

```java
package example.authorization;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class ReportOwnerStore {

    private final Map<String, String> owners = Map.of(
        "r101", "lan",
        "r202", "minh"
    );

    public String ownerOf(String reportId) {
        return owners.get(reportId);
    }
}
```

Ở đây `Map` là nguồn dữ liệu minh họa để project chạy độc lập. Trong sản phẩm thật, truy vấn kho dữ liệu có kiểm soát, phân biệt `tenantId`, trạng thái báo cáo, có thể dùng query lọc theo owner/tenant ngay tại SQL và kiểm tra thêm tại service.

### 9.5. ReportAccessPolicy: custom AuthorizationManager cho resource

File `src/main/java/example/authorization/ReportAccessPolicy.java`:

```java
package example.authorization;

import java.util.function.Supplier;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class ReportAccessPolicy
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ReportOwnerStore store;

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public ReportAccessPolicy(ReportOwnerStore store) {
        this.store = store;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authenticationSupplier,
            RequestAuthorizationContext context) {

        String reportId = context.getVariables().get("reportId");

        // Thiếu biến hoặc ID không có trong kho: deny rõ ràng.
        if (reportId == null) {
            return new AuthorizationDecision(false);
        }

        String owner = store.ownerOf(reportId);
        if (owner == null) {
            return new AuthorizationDecision(false);
        }

        Authentication current = authenticationSupplier.get();

        if (current == null || !trust.isAuthenticated(current)) {
            return new AuthorizationDecision(false);
        }

        boolean isOwner = owner.equals(current.getName());

        boolean isAdmin = current.getAuthorities().stream()
            .anyMatch(authority ->
                "ROLE_ADMIN".equals(authority.getAuthority()));

        return new AuthorizationDecision(isOwner || isAdmin);
    }
}
```

Ở đoạn này:

1. `context.getVariables().get("reportId")` sử dụng biến path từ matcher `/reports/{reportId}`. Spring MVC-aware matcher được chọn trong môi trường mẫu và integration test sẽ xác nhận behavior.
2. Thiếu reportId hoặc report không tồn tại → `false`, không `null`.
3. `AuthenticationTrustResolver` loại anonymous ngay cả khi token có flag `isAuthenticated`.
4. Dùng owner lấy từ **server-side store**, không đọc tham số `?owner=lan` do client tự gửi.
5. Admin được phép theo policy **của ví dụ này**. Một ứng dụng đa tenant cần điều kiện tenant/scope bổ sung.
6. Không tạo HTTP response trong manager; `AuthorizationFilter` và exception handling chịu trách nhiệm phản hồi.

### 9.6. AdminFullPolicy: đồng thời authority và trust level

File `src/main/java/example/authorization/AdminFullPolicy.java`:

```java
package example.authorization;

import java.util.function.Supplier;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class AdminFullPolicy
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authenticationSupplier,
            RequestAuthorizationContext context) {

        Authentication current = authenticationSupplier.get();

        boolean full = current != null
            && trust.isFullyAuthenticated(current);

        boolean isAdmin = current != null
            && current.getAuthorities().stream().anyMatch(
                a -> "ROLE_ADMIN".equals(a.getAuthority()));

        return new AuthorizationDecision(full && isAdmin);
    }
}
```

Một remembered admin có thể vẫn mang `ROLE_ADMIN`, nhưng không được xem là fully authenticated. Manager này yêu cầu **cả hai điều kiện**; nó không đánh đồng role với mức độ xác thực.

Dù vậy, nếu endpoint xuất dữ liệu cực kỳ nhạy cảm, `fullyAuthenticated` vẫn không bảo đảm MFA hoặc mới đăng nhập. Các yêu cầu đó cần policy bổ sung.

### 9.7. SecurityConfig: nối manager vào HTTP rules

File `src/main/java/example/authorization/SecurityConfig.java`:

```java
package example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("lan-demo"))
            .roles("USER")
            .build();

        UserDetails minh = User.withUsername("minh")
            .password(encoder.encode("minh-demo"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(lan, minh, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ReportAccessPolicy reportPolicy,
            AdminFullPolicy adminFullPolicy) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/reports/{reportId}")
                    .access(reportPolicy)
                .requestMatchers("/finance/export")
                    .access(adminFullPolicy)
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Bài chỉ dùng GET endpoints; giữ nguyên CSRF protection mặc định.
        return http.build();
    }
}
```

Giải thích:

- `.requestMatchers(...).access(reportPolicy)` tạo một mapping từ request matcher sang authorization manager.
- `.access(adminFullPolicy)` truyền manager cho route nhạy cảm.
- `.anyRequest().denyAll()` tránh mở bất kỳ route nào chưa được định nghĩa rõ.
- `httpBasic` cho phép mô phỏng authentication bằng header Basic; `STATELESS` và `NullSecurityContextRepository` không dùng session làm nguồn Authentication xuyên requests.
- `NullRequestCache` ngăn lưu URL cũ trong session chỉ để redirect form login.
- Không bật `formLogin` vì đây là API demo. HTTP 401 thường kèm `WWW-Authenticate: Basic`; user authenticated thiếu quyền thường nhận 403.
- Ví dụ chỉ có **GET**; việc thêm POST/PUT/DELETE cần đánh giá CSRF theo cơ chế credential của client, authorization thay đổi trạng thái và idempotency. Stateless không tự động làm CSRF vô nghĩa.

### 9.8. DemoController: không tự sao chép logic phân quyền

File `src/main/java/example/authorization/DemoController.java`:

```java
package example.authorization;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/reports/{reportId}")
    String report(@PathVariable String reportId,
                  Authentication authentication) {
        return "report:" + reportId + ":" + authentication.getName();
    }

    @GetMapping("/finance/export")
    String export(Authentication authentication) {
        return "export:" + authentication.getName();
    }
}
```

Đây là demo để phản hồi ngắn, dễ test. Trong sản phẩm thật, service lấy báo cáo nên kiểm tra resource owner/tenant ở một trust boundary phù hợp, không chỉ tin rằng mọi đường gọi service đều xuất phát từ một HTTP controller đã được bảo vệ.

## 10. Kiểm thử bằng MockMvc: đúng ai được xem báo cáo nào?

File `src/test/java/example/authorization/AuthorizationManagerIntegrationTest.java`:

```java
package example.authorization;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationManagerIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AdminFullPolicy adminFullPolicy;

    @Test
    void publicRouteWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousReportGetsBasicChallenge() throws Exception {
        MvcResult response = mvc.perform(get("/reports/r101"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge =
            response.getResponse().getHeader("WWW-Authenticate");

        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void ownerLanCanReadHerReport() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r101:lan"));
    }

    @Test
    void lanCannotReadMinhReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerMinhCanReadHisReport() throws Exception {
        mvc.perform(get("/reports/r202")
                .with(httpBasic("minh", "minh-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r202:minh"));
    }

    @Test
    void adminCanReadBothReports() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r101:admin"));

        mvc.perform(get("/reports/r202")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:r202:admin"));
    }

    @Test
    void unknownReportIdIsExplicitlyDenied() throws Exception {
        mvc.perform(get("/reports/unknown")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousFinanceExportGets401() throws Exception {
        mvc.perform(get("/finance/export"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void nonAdminFinanceExportGets403() throws Exception {
        mvc.perform(get("/finance/export")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void fullAdminCanExport() throws Exception {
        mvc.perform(get("/finance/export")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("export:admin"));
    }

    @Test
    void badBasicPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/reports/r101")
                .with(httpBasic("lan", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUrlIsDeniedToAuthenticatedUser()
            throws Exception {
        mvc.perform(get("/private-unlisted")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/reports/r101")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminFullManagerDeniesRememberMeToken() {
        Authentication remembered =
            new RememberMeAuthenticationToken(
                "demo-key",
                "admin",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
            );

        HttpServletRequest request =
            new MockHttpServletRequest("GET", "/finance/export");

        AuthorizationDecision decision = adminFullPolicy.check(
            () -> remembered,
            new RequestAuthorizationContext(request)
        );

        assertNotNull(decision);
        assertFalse(decision.isGranted());
    }
}
```

### 10.1. Tại sao test vừa HTTP vừa kiểm tra manager riêng?

- Các test `mvc.perform(...)` đi qua **Spring Security filter chain thật**. `httpBasic(...)` gửi header Basic để framework xác thực username/password, không giả lập sẵn một principal.
- Các trường hợp owner/other owner/admin kiểm tra **trích xuất path variable + quyền resource**. Nếu `context.getVariables()` không nhận biến `reportId` trên matcher thực tế, test owner sẽ thất bại, giúp phát hiện sai cấu hình.
- Các trường hợp 401 vs 403 kiểm chứng **phân biệt authentication và authorization**.
- Test `adminFullManagerDeniesRememberMeToken` gọi trực tiếp manager để chứng minh độ tin cậy của remember-me. Test này **không** kiểm thử hệ thống tạo remember-me cookie; muốn kiểm thử cookie thật phải cấu hình remember-me và login tương ứng.

### 10.2. Vì sao không dùng .with(user("lan")) để test Basic?

Spring Security Test có `.with(user(...))` để dựng Authentication thử nghiệm. Nó hữu ích khi test controller/policy mà không cần auth mechanism, nhưng **không chứng minh username/password thật được HTTP Basic filter xử lý**.

Ở đây `httpBasic("lan", "lan-demo")` cần đi qua BasicAuthenticationFilter/AuthenticationProvider và password encoder. Nhờ vậy test nhìn thấy kết quả 401 khi password sai.

### 10.3. Tại sao report không tồn tại nhận 403?

Manager trong demo trả `AuthorizationDecision(false)` nếu ID không tồn tại. Đây là một policy minh họa fail closed. Một API thật có thể chọn 404 nhằm tránh tiết lộ sự tồn tại của tài nguyên, nhưng phải chủ động thiết kế response, không tự giả định manager trả null sẽ tạo 404.

### 10.4. Vì sao postWithoutCsrfIsRejected có giá trị dù controller chỉ GET?

Test chứng minh CSRF filter có thể từ chối một POST trước khi tới handler HTTP khác. Nó **không** chứng minh API POST đã được thiết kế đầy đủ. Khi thêm endpoint ghi dữ liệu, cần test CSRF token hợp lệ, quyền thao tác và business state transitions riêng.

## 11. Chạy Maven, gọi API và đọc kết quả

Cần JDK 17+ và Maven. Trong thư mục `authorization-manager-demo`:

```bash
mvn test
mvn spring-boot:run
```

Nếu dependencies và môi trường phù hợp, **14 bài kiểm thử dự kiến pass**. Đây là dự kiến từ mã nguồn, **không phải** một lượt Maven đã được thực thi; log build và thời gian thay đổi theo máy.

Thử trên **localhost**:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/reports/r202
curl -i -u minh:minh-demo http://localhost:8080/reports/r202
curl -i -u admin:admin-demo http://localhost:8080/reports/r101
curl -i -u lan:lan-demo http://localhost:8080/finance/export
curl -i -u admin:admin-demo http://localhost:8080/finance/export
```

Các username/password ở đây là **giả lập**, chỉ dùng local qua HTTP thử nghiệm. **Không** truyền credential thật qua HTTP, không log password và cân nhắc lịch sử shell/process listing khi dùng `curl -u`.

| HTTP request | Kết quả dự kiến | Lý do |
| --- | --- | --- |
| Anonymous `GET /public` | 200 `public` | `permitAll` |
| Anonymous `GET /reports/r101` | 401, `WWW-Authenticate: Basic` | Thiếu authentication |
| Lan `GET /reports/r101` | 200 `report:r101:lan` | Lan là owner |
| Lan `GET /reports/r202` | 403 | Báo cáo của Minh |
| Minh `GET /reports/r202` | 200 `report:r202:minh` | Minh là owner |
| Admin `GET /reports/r101` | 200 `report:r101:admin` | Role admin được grant |
| Admin `GET /reports/unknown` | 403 | ID không có trong kho, policy deny |
| Lan `GET /finance/export` | 403 | Thiếu ROLE_ADMIN |
| Admin `GET /finance/export` | 200 `export:admin` | Full auth + ROLE_ADMIN |
| Lan dùng password sai | 401 | Basic authentication thất bại |
| Admin `GET /private-unlisted` | 403 | `anyRequest().denyAll()` |

**Chú ý:** 401, 403 và 200 ở bảng này phụ thuộc cấu hình HTTP Basic trong ví dụ. Khi dùng form login, anonymous request bị chặn có thể trả 302 redirect tới login thay vì 401; đó không phải khác biệt trong `AuthorizationDecision`.

## 12. Một ví dụ Java 17 độc lập: tách policy khỏi HTTP

Để hiểu bản chất quyết định allow/deny mà không cần Spring Boot, có thể chạy một chương trình Java 17 thuần. Mô hình dưới chỉ mô phỏng quyết định Boolean, **không tự tạo AuthorizationManager thật, HttpServletRequest hay SecurityContext**.

Tạo file `PolicyDecisionDemo.java`:

```java
import java.util.Map;

public class PolicyDecisionDemo {

    enum Outcome {
        GRANTED, DENIED
    }

    record User(String name, boolean admin) {}

    static final Map<String, String> OWNERS = Map.of(
        "r101", "lan",
        "r202", "minh"
    );

    static Outcome canRead(User user, String reportId) {
        String owner = OWNERS.get(reportId);

        if (user == null || owner == null) {
            return Outcome.DENIED;
        }

        boolean allowed = user.admin() || owner.equals(user.name());
        return allowed ? Outcome.GRANTED : Outcome.DENIED;
    }

    public static void main(String[] args) {
        User lan = new User("lan", false);
        User minh = new User("minh", false);
        User admin = new User("admin", true);

        System.out.println("lan r101 -> " + canRead(lan, "r101"));
        System.out.println("lan r202 -> " + canRead(lan, "r202"));
        System.out.println("minh r202 -> " + canRead(minh, "r202"));
        System.out.println("admin r101 -> " + canRead(admin, "r101"));
        System.out.println("admin missing -> " +
            canRead(admin, "missing"));
        System.out.println("anonymous r101 -> " +
            canRead(null, "r101"));
    }
}
```

Biên dịch và chạy trên JDK 17:

```bash
javac PolicyDecisionDemo.java
java PolicyDecisionDemo
```

Stdout **chính xác**:

```text
lan r101 -> GRANTED
lan r202 -> DENIED
minh r202 -> GRANTED
admin r101 -> GRANTED
admin missing -> DENIED
anonymous r101 -> DENIED
```

Chương trình chỉ tách công thức quyết định, không thực hiện HTTP Basic, CSRF, method security hay exception handling. Phần Spring Boot/MockMvc mới chứng minh manager được thực thi trong Servlet filter chain.

## 13. Kết hợp nhiều AuthorizationManager

Đôi khi một quyết định cần kiểm tra:

```text
GRANT nếu:
    hasRole("ADMIN")
    AND isFullyAuthenticated()
    AND resource thuộc đúng tenant
    AND account còn hiệu lực
```

Có hai kiểu kết hợp logic thường gặp:

- **ALL (AND):** tất cả điều kiện phải được thỏa.
- **ANY (OR):** ít nhất một nhánh hợp lệ.

Spring Security có các công cụ như `AuthorizationManagers.allOf` và `AuthorizationManagers.anyOf`. Chúng có thể giảm code boilerplate cho những manager được xây sẵn. Tuy nhiên, cần hiểu cách implementation của phiên bản đang dùng xử lý denied và abstain.

### 13.1. Một manager tự viết rõ ràng

Trong `AdminFullPolicy` ở phần 9, ta dùng:

```java
boolean full = current != null
    && trust.isFullyAuthenticated(current);

boolean isAdmin = current != null
    && current.getAuthorities().stream().anyMatch(
        a -> "ROLE_ADMIN".equals(a.getAuthority()));

return new AuthorizationDecision(full && isAdmin);
```

Nó rõ ràng, không có nhánh null/abstain. Nếu policy yêu cầu thêm tenant, có thể bổ sung điều kiện từ nguồn dữ liệu đáng tin thay vì đặt nhiều rule trùng matcher rồi mong framework tự kết hợp.

### 13.2. Tránh hiểu OR khi ghép nhiều quyền

Ví dụ `owner OR admin` có ý nghĩa khi admin được đặc cách xem báo cáo của user khác trong cùng phạm vi hợp lệ. Nhưng “owner OR hasAnyRole(USER, ADMIN)” sẽ cho **mọi USER** đọc mọi báo cáo nếu role đó hiện diện, vô tình bỏ ownership.

Kiểm thử phải có ít nhất một ca **user hợp lệ nhưng không sở hữu resource**, vì đây là lỗi mà test chỉ người anonymous không phát hiện.

### 13.3. Abstain trong tập manager

Trong mô hình kết hợp, một manager có thể không áp dụng cho object nào đó. Nếu dùng `null` để abstain theo API đời cũ, cần xác định rõ:

- ai quyết định cuối cùng khi tất cả abstain;
- manager nào áp dụng cho resource nào;
- một deny có bị OR với grant khác không;
- kiểm soát nào là điều kiện bắt buộc, không được bypass;
- trạng thái null có phát sinh do lỗi dữ liệu không.

**Không thiết kế “mọi manager abstain thì mặc nhiên grant”** ở các resource cần bảo vệ, trừ khi đây là một quyết định policy có kiểm soát và được kiểm chứng.

## 14. Quyết định deny được chuyển thành HTTP response thế nào?

### 14.1. Anonymous chưa được xác thực

Với một request `GET /reports/r101` không có Basic header:

1. Rule `/reports/{reportId}` được chọn.
2. Manager thiếu authenticated principal sẽ không cấp quyền.
3. Spring Security đánh giá cần authentication và sử dụng Basic entry point.
4. Client thường nhận **401** cùng `WWW-Authenticate: Basic ...`.

Nếu cấu hình form login thay vì Basic, cùng lý do deny có thể làm browser nhận **302 tới trang login**. Vì thế không thể đọc `AuthorizationDecision(false)` rồi kết luận response luôn là 403.

### 14.2. User đã xác thực nhưng thiếu quyền

Lan đăng nhập Basic đúng và gửi `GET /reports/r202`:

1. Authentication được tạo hợp lệ.
2. Manager lấy owner từ store: Minh.
3. Lan không phải owner cũng không có ROLE_ADMIN.
4. Decision denied.
5. HTTP thường là **403 Forbidden** trong cấu hình API.

### 14.3. HTTP status và lỗi CSRF

CSRF protection ở một request POST có thể chặn trước manager. Khi đó response 403 không chứng minh `ReportAccessPolicy` đã được gọi. Muốn xác định chính sách nào từ chối, xem security filter flow và test phù hợp.

### 14.4. Authorization event và audit

Một số cấu hình Spring Security có thể xuất bản sự kiện authorization như grant/deny qua `AuthorizationEventPublisher`. Hữu ích cho observability nếu được cấu hình đúng, nhưng:

- Không giả định framework mặc định log đầy đủ mọi quyết định.
- Không log raw credentials/cookie/session ID hoặc dữ liệu riêng tư của resource.
- Tách **security audit** với lỗi kinh doanh; thông tin owner/tenant phải được xử lý theo privacy policy.
- Đừng dùng event listener có side effects thay đổi permission trong cùng request như một phần bắt buộc của quyết định.

## 15. Hiệu năng và tính nhất quán của policy

Một custom manager có thể được gọi thường xuyên. Nếu mỗi check tải dữ liệu lớn hoặc gọi dịch vụ bên ngoài, latency tăng và có thể tạo điểm tấn công DoS.

Đề xuất:

- Tối ưu lookup chỉ lấy những cột cần: ownerId, tenantId, trạng thái, policy version.
- Có index phù hợp cho bảng quyền và ID report.
- Dùng cache cẩn thận: quyền vừa bị thu hồi không được tiếp tục cấp lâu ngoài SLA.
- Không cache decision theo URL đơn thuần mà bỏ qua principal, tenant, action và thời điểm.
- Nếu dùng quyền phân tán, quy định rõ độ trễ đồng bộ và timeout/fail-closed behavior.
- Xem race condition: quyền được kiểm tra lúc bắt đầu nhưng resource bị đổi owner trước lúc cập nhật. Với thao tác nhạy cảm, có thể cần kiểm tra trong transaction tại thời điểm commit.
- Đo p95/p99 của API và tỉ lệ deny/timeout ở môi trường thử nghiệm; không khẳng định mọi authorization manager “rất rẻ” chỉ vì code vài dòng.

### 15.1. Kiểm tra ở nhiều tầng

Request-level authorization phù hợp để chặn endpoint sớm. Nhưng service có thể được gọi từ scheduler, message consumer hoặc một controller khác. Với thao tác dữ liệu nhạy cảm, method security hoặc kiểm tra domain-level nên là lớp bảo vệ bổ sung có chủ đích.

Không đặt logic phân quyền vào UI bằng cách ẩn nút rồi tin rằng backend an toàn. Client có thể tự gửi HTTP request tới endpoint.

### 15.2. Tránh TOCTOU

TOCTOU (time-of-check to time-of-use) xảy ra khi trạng thái quyền thay đổi giữa lúc policy check và lúc thực hiện thao tác. Ví dụ:

```text
T1  request GET /reports/r101: owner được xác minh là lan
T2  report được chuyển chủ sở hữu
T3  service trả nội dung r101 theo kết quả kiểm tra cũ
```

Với một API đọc đơn giản, rủi ro có thể được giảm bằng truy vấn có ràng buộc owner/tenant ngay lúc fetch. Với cập nhật có side effects, dùng transaction, row-level policy hoặc điều kiện version/owner phù hợp. `AuthorizationManager` không tự giải quyết mọi race condition.

## 16. Những lỗi phổ biến

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Dùng `Authentication.isAuthenticated()` đơn lẻ | Anonymous token có thể bị coi là user thật | Dùng `AuthenticationTrustResolver` hoặc manager chuẩn |
| Nghĩ matcher true đồng nghĩa granted | Bỏ qua principal và authority | Tách RequestMatcher và AuthorizationManager |
| Trả `null` khi repository lỗi | Abstain có thể bị diễn giải sai trong pipeline | Trả deny/exception có kiểm soát, không fail open |
| Trả `true` nếu reportId không tồn tại | Mở đường đi sai, tăng nguy cơ lộ dữ liệu | Fail closed và test report missing |
| Lấy `owner` từ query tự khai báo | Attacker tự đổi query để mạo nhận ownership | Đọc ownership từ server-side store |
| Chỉ kiểm tra `ROLE_USER` cho báo cáo mọi user | BOLA/IDOR | Kiểm tra owner/tenant theo object |
| Nghĩ `ROLE_ADMIN` tự là full login | Remember-me admin có thể giữ authority | Kết hợp role và trust policy |
| Coi `fullyAuthenticated` là có MFA mới nhất | Giao dịch nhạy cảm chưa được step-up | Thêm recent-auth/MFA controls |
| Đặt `permitAll` wildcard trước rule bảo vệ | Route nhạy cảm được public hóa | Matcher cụ thể trước, deny fallback |
| Đặt hai rule trùng URL và mong chúng tự AND | Rule đầu tiên match được áp dụng | Viết một manager kết hợp |
| Coi `AuthorizationDecision(false)` luôn là HTTP 403 | Thực tế có thể là 401 hoặc redirect | Xem entry point, authentication và error handlers |
| Giả định AuthorizationDecision granted = 200 | Controller/service có thể chặn/khác status | Phân biệt grant với HTTP response |
| Đưa query DB nặng vào mọi matcher | Tốn tài nguyên, DoS | Đặt business lookup ở policy/service tối ưu |
| Cache quyền theo URL nhưng quên principal | Cho phép chéo user | Cache key có principal, tenant, action, policy version |
| Không test owner khác | Bỏ sót IDOR | Có matrix owner, non-owner, admin, missing |
| Dùng `with(user(...))` và tưởng đã test Basic | Bypass authentication mechanism | Gửi `httpBasic` qua MockMvc |
| Dùng stateless làm lý do tự tắt CSRF | Browser vẫn có thể tự gửi Basic credentials | Threat model CSRF riêng cho API |
| Log Authorization header/cookie | Lộ secret | Audit metadata an toàn, không log credential |
| Không tính đến multi-node consistency | Quyền thu hồi chậm | Thiết kế dữ liệu/cache/revocation rõ |
| Không bảo vệ service gọi ngoài HTTP | Đường gọi khác bypass controller policy | Thêm method/domain authorization khi cần |
| Không phân biệt AccessDenied và lỗi DB | Response/log sai, che lỗi vận hành | Phân loại exception và fail closed |
| Quên fallback cho route mới | Endpoint thiếu policy có thể bị mở | Deny by default và kiểm thử |

## 17. Debug khi kết quả authorization khác kỳ vọng

Kiểm tra theo thứ tự:

1. **Đúng SecurityFilterChain?** Kiểm tra `securityMatcher` và `@Order` nếu có nhiều chain.
2. **Rule URL nào match?** Xem thứ tự `requestMatchers` và fallback.
3. **Authentication có thật?** Xem Basic header, session, token hoặc filter authentication đang chạy.
4. **Principal hiện tại là ai?** Chú ý anonymous và remember-me, không chỉ `isAuthenticated`.
5. **T có đúng loại?** `RequestAuthorizationContext` có phải context được manager đang nhận không?
6. **Biến path có trích đúng?** `context.getVariables()` có chứa `reportId` không, có trùng matcher MVC không?
7. **Dữ liệu owner/tenant lấy từ đâu?** Query DB thực sự, không từ tham số tự khai báo.
8. **Chính sách AND/OR thế nào?** Owner OR admin có đúng yêu cầu chưa? Các điều kiện bắt buộc có bị bỏ qua?
9. **Manager trả gì?** `AuthorizationDecision(true)`, `false`, `null` hay ném exception?
10. **Filter có thực sự áp đặt decision?** AuthorizationFilter/exception translation và entry point hoạt động ra sao?
11. **401/302 hay 403?** Phân biệt thiếu authentication với user đã xác thực nhưng không có quyền.
12. **CSRF có chặn trước không?** Một POST 403 có thể không liên quan report policy.
13. **Controller/service còn policy nào nữa?** Method security, ownership ở service, validation, tenant.
14. **Có cache stale hoặc TOCTOU không?** Quyền vừa thay đổi, request khác node, dữ liệu bị chuyển owner.
15. **Nâng Spring Security version?** Kiểm tra các API, matcher, AuthorizationResult/AuthorizationDecision và exception handling theo version.

Trong môi trường phát triển có thể bật:

```properties
logging.level.org.springframework.security=DEBUG
```

Không log password, cookie, Authorization header, bearer token hoặc ID phiên thực. Tạo test nhỏ dựa trên decision matrix nhanh hơn việc chỉ nhìn log tổng quát.

## 18. Câu hỏi luyện tập có đáp án

**Câu 1.** `AuthorizationManager<RequestAuthorizationContext>` trả lời câu hỏi nào?

**Đáp án:** Nó dùng Authentication và ngữ cảnh HTTP để ra quyết định quyền đối với request phù hợp. Nó không tự thực hiện password verification, không chọn SecurityFilterChain và không trực tiếp quyết định body/status response.

**Câu 2.** `new AuthorizationDecision(false)` có luôn tạo HTTP 403 không?

**Đáp án:** Không. Anonymous API Basic có thể nhận 401, form-login anonymous có thể redirect 302. Response tùy entry point và exception handling.

**Câu 3.** `check(...)` trả `null` nghĩa là gì trong API Spring Security 6.3.x?

**Đáp án:** Abstain/không ra quyết định theo contract tương ứng, không được coi là grant mặc định. Policy cuối nhạy cảm nên quyết định rõ allow/deny.

**Câu 4.** Tại sao tham số đầu tiên là `Supplier<Authentication>`?

**Đáp án:** Cho phép truy xuất Authentication khi cần, tránh giải tham chiếu trong các rule như permitAll/denyAll không cần principal.

**Câu 5.** Một request `GET /reports/r202` có owner là Minh; Lan có ROLE_USER. Rule chỉ `hasRole("USER")` có chặn Lan không?

**Đáp án:** Không chắc; nếu chỉ kiểm tra role, Lan có thể được vào dù không sở hữu. Cần kiểm tra owner/tenant của report cụ thể.

**Câu 6.** Có thể tin query `?owner=lan` để cho Lan vào báo cáo không?

**Đáp án:** Không. Client tự cung cấp query; ownership phải lấy từ nguồn server đáng tin.

**Câu 7.** Muốn route admin đòi cả admin role và full authentication, có thể khai báo hai rule trùng URL rồi mong cả hai chạy không?

**Đáp án:** Không; rule đầu tiên match được áp dụng. Dùng một AuthorizationManager kết hợp hoặc cơ chế phối hợp có ngữ nghĩa tường minh.

**Câu 8.** `AuthorizationDecision(true)` có chứng minh HTTP sẽ trả 200 không?

**Đáp án:** Không. Nó chỉ grant theo policy hiện tại; controller/method security/các filter khác vẫn có thể từ chối hoặc trả status khác.

**Câu 9.** Test dùng `.with(user("lan"))` cho route báo cáo có chứng minh HTTP Basic password đúng không?

**Đáp án:** Không. Nó có thể dựng sẵn SecurityContext. Test Basic thật dùng `httpBasic("lan","lan-demo")` đi qua filter/provider.

**Câu 10.** Admin yêu cầu một report ID không có trong store, manager nên làm gì trong thiết kế fail-closed của demo?

**Đáp án:** Trả `AuthorizationDecision(false)`; không suy ra admin được truy cập resource chưa tồn tại. Response 403/404 ngoài thực tế cần policy API chủ động.

**Câu 11.** Tại sao test authenticated non-owner lại quan trọng?

**Đáp án:** Nó phát hiện lỗi BOLA/IDOR mà test anonymous không bắt được. Một user hợp lệ vẫn có thể cố mở tài nguyên người khác.

**Câu 12.** Nếu một policy cho phép ở T1 nhưng resource đổi owner trước khi service truy vấn ở T2 thì sao?

**Đáp án:** Có thể xảy ra TOCTOU. Cần truy vấn/transaction/authorization phù hợp tại điểm sử dụng dữ liệu, không dựa tuyệt đối vào quyết định cũ.

## 19. Checklist áp dụng trong sản phẩm

### Trước khi viết manager

- Resource được bảo vệ là gì, action nào, owner/tenant nào?
- Authentication có được tin tưởng, account có còn hiệu lực không?
- Chính sách là ALL hay ANY? Những điều kiện bắt buộc có bị một nhánh OR bypass không?
- Manager nào cung cấp decision cuối? Nếu abstain, ai xử lý?
- Input request nào là untrusted, dữ liệu server nào là nguồn quyền đáng tin?
- Có thể dùng manager chuẩn thay vì custom code không?

### Trước khi đưa lên production

- Có default deny cho route ngoài danh sách không?
- Có test anonymous, owner, non-owner, admin, unknown ID, invalid credential không?
- Có kiểm tra 401 vs 403/redirect theo entry point thực tế không?
- Có test path variables dưới contextPath/servletPath đang triển khai không?
- Có CSRF/HTTP method/rate limit và TLS đúng cho API không?
- Có kiểm tra đồng thời ở service/DB đối với thao tác nhạy cảm không?
- Có log/metrics an toàn và không lộ credentials hoặc thông tin tenant không?
- Có chính sách cập nhật/revoke quyền xuyên node, cache và transaction không?

## 20. Tóm tắt cần nhớ

- **`AuthorizationManager<T>`** là nơi tính quyết định phân quyền, nhận `Supplier<Authentication>` và ngữ cảnh `T`.
- **`AuthorizationDecision(true)`** là allow; **`false`** là deny; ở contract Spring Security 6.3.x, `null` có thể biểu diễn abstain, **không phải grant mặc định**.
- **`RequestMatcher`** xác định rule nào áp dụng; **`AuthorizationManager`** xác định principal có đủ quyền theo rule đó không.
- **`AuthorizationFilter`** thực thi quyết định trong Servlet chain; exception handling/entry point chuyển lỗi thành 401, 302 hoặc 403 tùy authentication.
- **`RequestAuthorizationContext`** có thể cung cấp HttpServletRequest và path variables từ matcher tương thích; các giá trị đường dẫn là input chưa đáng tin, phải đối chiếu server-side resource store.
- **Role/authority**, **độ tin cậy authentication** và **quyền sở hữu đối tượng** phải được kết hợp đúng. Role không tự chứng minh owner hoặc full/recent MFA.
- **Deny by default**, test user hợp lệ nhưng không phải owner, và tách policy khỏi HTTP response là những nền tảng để tránh BOLA/IDOR.
- Với Spring Boot 3/Java 17, kiểm thử đầy đủ **anonymous → 401**, **owner/admin → 200**, **non-owner → 403**, **unknown ID → deny**, cùng cơ chế HTTP Basic/CSRF để xác minh policy trong filter chain thực tế.
