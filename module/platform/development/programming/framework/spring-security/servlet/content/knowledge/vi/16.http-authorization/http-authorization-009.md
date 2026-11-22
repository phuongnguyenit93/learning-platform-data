# Kết hợp điều kiện phân quyền HTTP bằng AuthorizationManagers.allOf và anyOf

> **Ngữ cảnh:** Spring Security **Servlet** 6.x, Java 17+, HTTP authorization dùng `HttpSecurity.authorizeHttpRequests`. Bài tập trung vào API `AuthorizationManagers.allOf(...)` (tổ hợp **AND**) và `AuthorizationManagers.anyOf(...)` (tổ hợp **OR**), cách hoạt động của `AuthorizationManager<RequestAuthorizationContext>`, kết quả cho phép/từ chối/không có quyết định, thứ tự đánh giá và những lỗi thiết kế thường gặp. Ví dụ chạy với Spring Boot 3.3.5 và Java 17.

## 1. Vấn đề: một URL thường có nhiều yêu cầu phân quyền

Với một endpoint bảo vệ báo cáo, quy tắc nghiệp vụ không nhất thiết chỉ là “đã đăng nhập” hoặc “có một role”. Chẳng hạn:

- `GET /reports/view`: người dùng **đã xác thực** **VÀ** (**có `REPORT_READ`** **HOẶC** **có role `ADMIN`**).
- `GET /reports/export`: người dùng **có role `ADMIN`** **VÀ** **có quyền `REPORT_EXPORT`**.
- `GET /review`: người dùng **có role `ADMIN`** **HOẶC** **có role `AUDITOR`**.

Viết bằng biểu thức logic:

```text
VIEW   = AUTHENTICATED && (REPORT_READ || ROLE_ADMIN)
EXPORT = ROLE_ADMIN && REPORT_EXPORT
REVIEW = ROLE_ADMIN || ROLE_AUDITOR
```

Với Spring Security Servlet, ta có thể ghép nhiều `AuthorizationManager<RequestAuthorizationContext>` để biểu diễn chính sách này một cách có cấu trúc. `AuthorizationManagers.allOf` tương đương tư duy **mọi điều kiện bắt buộc đều phải qua**; `AuthorizationManagers.anyOf` tương đương **chỉ cần một nhánh cho phép**.

**Đây là authorization (phân quyền), không phải authentication (xác thực).** Trước đó, một authentication filter như `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter` hoặc Bearer token filter phải kiểm chứng credentials và tạo `Authentication` đáng tin cậy. AuthorizationManager chỉ đánh giá danh tính/quyền/ngữ cảnh request **đã được hệ thống biết** theo policy.

## 2. Bản đồ các API và kiểu dữ liệu

Các lớp thường dùng:

| API | Vai trò |
| --- | --- |
| `AuthorizationManager<T>` | Giao diện một bộ ra quyết định cho đối tượng cần bảo vệ kiểu `T` |
| `AuthorizationManagers.allOf(...)` | Ghép nhiều managers theo **AND** |
| `AuthorizationManagers.anyOf(...)` | Ghép nhiều managers theo **OR** |
| `AuthorityAuthorizationManager<T>` | Kiểm tra authorities hoặc roles trong `Authentication` |
| `AuthenticatedAuthorizationManager<T>` | Kiểm tra mức độ authentication như `authenticated()`, `fullyAuthenticated()` |
| `RequestAuthorizationContext` | Ngữ cảnh của request HTTP Servlet, gồm `HttpServletRequest` và variables của matcher khi có |
| `AuthorizationDecision` | Đại diện kết quả grant/deny cho những manager sử dụng API decision |
| `AuthorizationFilter` | Áp dụng `AuthorizationManager` lên request đã đi tới bước authorization |
| `ExceptionTranslationFilter` | Dẫn lỗi thiếu xác thực đến entry point (ví dụ 401/redirect) hoặc lỗi thiếu quyền đến access-denied handling (thường 403) |

Chữ ký API logic minh họa:

```java
// Mã giải thích interface, không cần khai báo lại trong ứng dụng.
AuthorizationManager<RequestAuthorizationContext> rule = ...;

AuthorizationManager<RequestAuthorizationContext> mustPassAll =
        AuthorizationManagers.allOf(firstRule, secondRule);

AuthorizationManager<RequestAuthorizationContext> mayPassAny =
        AuthorizationManagers.anyOf(firstRule, secondRule);
```

Các biến `firstRule`, `secondRule` trong fragment cần có kiểu tương thích với `AuthorizationManager<RequestAuthorizationContext>`. `AuthorizationManagers` không nhận các `boolean` tính sẵn, không tự đọc database, không cấp JWT và không tự thay thế `SecurityFilterChain`.

### Kiểu T có ý nghĩa

`AuthorizationManager<T>` là API generic. Đối với DSL `authorizeHttpRequests().requestMatchers(...).access(...)` trên Servlet, `T` thường là **`RequestAuthorizationContext`**. Không lấy trực tiếp một `AuthorizationManager<MethodInvocation>` dành cho method security hoặc một kiểu dành cho reactive WebFlux rồi ép kiểu để dùng ở HTTP Servlet.

Imports tiêu biểu:

```java
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
```

Trong ví dụ hoàn chỉnh bên dưới, các biến manager sẽ được khai báo rõ với `RequestAuthorizationContext` để compiler kiểm tra loại đối tượng cần được phân quyền.

## 3. allOf: phép AND của các điều kiện

Hãy hình dung `allOf(A,B,C)`:

```text
Request -> A?
             |
       deny -+---> DENY
             |
           grant / no-decision
             |
             v
             B?
             |
       deny -+---> DENY
             |
           grant / no-decision
             |
             v
             C?
             |
       deny -+---> DENY
             |
           grant / no-decision
             |
             v
          GRANT (nếu không manager nào phủ quyết)
```

Với các manager phổ biến trả quyết định rõ ràng true/false, phép AND hoạt động đúng như bảng chân trị:

| A | B | `allOf(A,B)` |
| --- | --- | --- |
| Cho phép | Cho phép | Cho phép |
| Cho phép | Từ chối | Từ chối |
| Từ chối | Cho phép | Từ chối |
| Từ chối | Từ chối | Từ chối |

Ví dụ người dùng muốn export báo cáo chỉ khi vừa thuộc `ROLE_ADMIN` vừa có `REPORT_EXPORT`:

```java
AuthorizationManager<RequestAuthorizationContext> exportRule =
        AuthorizationManagers.allOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasAuthority("REPORT_EXPORT")
        );
```

Ở đây **một trong hai điều kiện không đủ**. Một admin chưa được cấp quyền export sẽ bị chặn. Một user có quyền `REPORT_EXPORT` nhưng không mang `ROLE_ADMIN` cũng bị chặn.

**Không nhầm `hasRole("ADMIN")` với `hasAuthority("ADMIN")`:** `hasRole("ADMIN")` dùng prefix role thông thường `ROLE_ADMIN`, còn `hasAuthority("REPORT_EXPORT")` so chính xác chuỗi `REPORT_EXPORT`. Với `UserDetails`, nên định nghĩa authorities rõ ràng và thống nhất với các rules.

### Phần tử không đưa ra quyết định

Trong API `AuthorizationManager`, một số implementation có thể trả **không có quyết định** (`null`) từ method `check(...)`. Với tổ hợp `AuthorizationManagers.allOf` trong Spring Security 6, manager không đưa ra quyết định **không được coi tự động là phủ quyết**. Nếu không manager nào từ chối, tổ hợp có thể **grant**, kể cả khi tất cả managers đều abstain.

Do đó với policy quan trọng, **không nên viết manager trả null trên request không nhận diện được rồi tin `allOf` sẽ fail closed**. Hãy đảm bảo có một điều kiện trả deny rõ ràng nếu dữ liệu cần thiết thiếu hoặc không hợp lệ, hoặc thiết kế matcher/phạm vi áp dụng phù hợp.

Ví dụ fragment chống sai:

```java
// Fragment Java, dùng trong custom manager của ứng dụng.
AuthorizationManager<RequestAuthorizationContext> tenantCheck =
        (authentication, context) -> {
            String tenant = context.getRequest().getHeader("X-Tenant");
            if (tenant == null || tenant.isBlank()) {
                return new AuthorizationDecision(false);
            }
            // Phải kiểm tra tenant theo principal/dữ liệu server tin cậy;
            // không chỉ tin giá trị header do client tự gửi.
            return new AuthorizationDecision(
                    canAccessTenant(authentication.get(), tenant));
        };
```

Hàm `canAccessTenant(...)` là **hàm nghiệp vụ cần tự triển khai và truy cập nguồn dữ liệu tin cậy**; fragment này **không chạy độc lập**. Mục tiêu là minh họa: thiếu tenant thì trả false, **không trả null rồi vô tình để allOf grant**. Trong môi trường thực tế, cần cả quản lý exception, null authentication, tenant ID hợp lệ và ownership kiểm tra trên server.

## 4. anyOf: phép OR của các điều kiện

`anyOf(A,B,C)` trả cho phép ngay khi có **ít nhất một** điều kiện grant. Với các manager luôn có quyết định rõ ràng:

| A | B | `anyOf(A,B)` |
| --- | --- | --- |
| Cho phép | Cho phép | Cho phép |
| Cho phép | Từ chối | Cho phép |
| Từ chối | Cho phép | Cho phép |
| Từ chối | Từ chối | Từ chối |

Ví dụ `/review` dành cho admin **hoặc** auditor:

```java
AuthorizationManager<RequestAuthorizationContext> reviewRule =
        AuthorizationManagers.anyOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("AUDITOR")
        );
```

Một người chỉ có `ROLE_AUDITOR` vẫn được phép truy cập. Một người chỉ có `ROLE_USER` bị từ chối.

**Với manager abstain:** `anyOf` thường bỏ qua những kết quả `null` và chỉ grant khi tìm được nhánh cho phép. Nếu không nhánh nào grant, tổng hợp **deny**. Vì thế không nên hiểu `null` là `true`, và cũng không nên coi AND/OR trên tập các manager có thể trả null hoàn toàn tương đương biểu thức Boolean ba giá trị thông thường.

### Dùng anyOf hay hasAnyAuthority?

Khi chỉ cần một trong nhiều authority thuần túy:

```java
// Fragment ngắn gọn hơn nếu chỉ kiểm tra danh sách authorities:
AuthorityAuthorizationManager<RequestAuthorizationContext> simple =
        AuthorityAuthorizationManager.hasAnyAuthority(
                "ROLE_ADMIN", "ROLE_AUDITOR");
```

`hasAnyAuthority` thường đủ và dễ đọc. `anyOf` có lợi hơn khi bạn muốn kết hợp **các policy khác loại**, ví dụ: admin role **hoặc** chủ sở hữu tài nguyên **hoặc** user được cấp một quyền nghiệp vụ riêng.

`anyOf` không tự quyết định nhánh nào nên đứng đầu theo hiệu năng hay mức độ an toàn. Trình tự check được xác định bởi cách bạn truyền managers; hãy tránh nhánh có side effects hoặc phụ thuộc thứ tự. Cả `allOf` và `anyOf` có thể dừng sớm khi đã đủ kết luận, nên **đừng dùng chúng để thực hiện audit side effects bắt buộc chạy mọi lần**.

## 5. Lồng allOf và anyOf để biểu diễn policy thực tế

Cho endpoint xem báo cáo:

```text
VIEW = AUTHENTICATED && (REPORT_READ || ROLE_ADMIN)
```

Chúng ta có thể viết cấu trúc lồng nhau:

```java
AuthorizationManager<RequestAuthorizationContext> canRead =
        AuthorizationManagers.anyOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasAuthority("REPORT_READ"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN")
        );

AuthorizationManager<RequestAuthorizationContext> viewRule =
        AuthorizationManagers.allOf(
                AuthenticatedAuthorizationManager
                        .<RequestAuthorizationContext>authenticated(),
                canRead
        );
```

Thứ tự logic ở ví dụ này:

1. Người dùng phải có authentication được framework coi là đã xác thực.
2. Người dùng có `REPORT_READ` **hoặc** có `ROLE_ADMIN`.
3. Nếu bất kỳ điều kiện bắt buộc nào từ chối, `allOf` từ chối.
4. Nếu người dùng chỉ có `ROLE_GUEST`, `authenticated()` đúng nhưng `canRead` sai → tổng vẫn deny.
5. Nếu anonymous không có role/authority hợp lệ, authorization không đạt; với HTTP Basic, client thường nhận 401 challenge thay vì 403.

Một trường hợp dễ mắc: viết `anyOf(authenticated(), hasRole("ADMIN"))` sẽ cho phép **mọi user đã đăng nhập** đi qua nhánh đầu, vô hiệu hóa ràng buộc admin của nhánh thứ hai. Đó là lỗi thiết kế **OR quá rộng**. Khi phải “đăng nhập và có quyền”, sử dụng `allOf` hoặc một rule role/authority đủ chặt.

### Sơ đồ policy lồng nhau

```text
                    allOf
                   /     \
        authenticated    anyOf
                         /    \
                  REPORT_READ  ROLE_ADMIN

Kết quả:
- anonymous                       -> DENY
- authenticated, ROLE_GUEST        -> DENY
- authenticated, REPORT_READ       -> GRANT
- authenticated, ROLE_ADMIN        -> GRANT
- authenticated, cả hai           -> GRANT
```

Lồng điều kiện giúp thể hiện chính sách công khai thay vì giấu nó trong một lambda dài. Tuy nhiên, nếu quy tắc gắn với **ownership tài nguyên** hoặc permission động từ database, vẫn cần custom `AuthorizationManager` hoặc service kiểm tra quyền trên server; không biến tất cả logic nghiệp vụ thành phép kiểm tra role tĩnh.

## 6. Từ AuthorizationManager đến HTTP 200, 401, 403

Luồng Servlet tiêu biểu:

```text
HTTP request
    |
    v
FilterChainProxy -> SecurityFilterChain
    |
    v
Authentication filters
(Basic/form/Bearer... tùy chain)
    |
    v
SecurityContextHolder / Authentication hiện tại
    |
    v
AuthorizationFilter
    |
    v
AuthorizationManager<RequestAuthorizationContext>
    |
    +--- allOf / anyOf / nested managers
             |
         +---+----+
         |        |
       GRANT     DENY
         |        |
         v        v
   Controller    AccessDeniedException
                  |
                  v
           ExceptionTranslationFilter
                  |
             +----+-----------+
             |                |
         anonymous?       authenticated?
             |                |
             v                v
       Authentication     AccessDeniedHandler
         EntryPoint        thường 403
         thường 401
         hoặc form 302
```

Với **HTTP Basic** như ví dụ runnable ở mục 9:

| Tình huống | Kết quả thường thấy | Giải thích |
| --- | --- | --- |
| Không có Basic credentials, endpoint bảo vệ | **401** + `WWW-Authenticate` | Chưa có identity phù hợp |
| Sai username/password | **401** | Authentication thất bại trước authorization |
| Credentials đúng nhưng không đạt `allOf`/`anyOf` | **403** | Xác thực đúng nhưng policy deny |
| Credentials đúng và tổ hợp grant | **200** (nếu controller trả 200) | Controller được phép chạy |
| Endpoint `permitAll()` không có Basic credentials | **200** | Không yêu cầu login |

Ở web form login, đường anonymous bị deny có thể dẫn đến **302 redirect** tới trang login. `AuthorizationManagers.allOf/anyOf` **không tự tạo HTTP status**; response là kết quả của filter chain, entry point và access-denied handling.

### Authentication khác Authorization

`Authentication` cung cấp `principal`, `authorities` và trạng thái đã xác thực. Provider xác minh password/token. Manager phân quyền **đọc** thông tin đó, không cho phép client tự chọn role qua URL/header rồi gắn vào `Authentication`.

Các `GrantedAuthority` như `ROLE_ADMIN` hay `REPORT_EXPORT` phải đến từ nguồn tin cậy: user store, identity provider hoặc cơ chế mapping claims đã được xác thực. Đừng cho phép request body gửi `roles:["ROLE_ADMIN"]` rồi dùng trực tiếp để ra quyết định.

## 7. Các vấn đề khi tổ hợp nhiều điều kiện

### 7.1. Nhánh chấp nhận quá rộng

Sai về ý định nghiệp vụ:

```java
// Nguy hiểm nếu /admin phải yêu cầu ROLE_ADMIN:
AuthorizationManager<RequestAuthorizationContext> tooBroad =
        AuthorizationManagers.anyOf(
                AuthenticatedAuthorizationManager
                        .<RequestAuthorizationContext>authenticated(),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN")
        );
```

Bởi vì `anyOf` là OR, một user bình thường đã đăng nhập sẽ vượt qua nhánh `authenticated()`. Nếu yêu cầu là “đã đăng nhập **và** admin”, dùng `allOf` hoặc trực tiếp `hasRole("ADMIN")`.

### 7.2. Nhánh bất khả thi

```java
// Chỉ cho phép người dùng có CẢ HAI role.
// Nếu dữ liệu nghiệp vụ thiết kế role loại trừ nhau,
// điều kiện này sẽ không bao giờ grant.
AuthorizationManager<RequestAuthorizationContext> impossible =
        AuthorizationManagers.allOf(
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("GUEST"),
                AuthorityAuthorizationManager
                        .<RequestAuthorizationContext>hasRole("ADMIN")
        );
```

Chú ý: một user về kỹ thuật **có thể có nhiều role**; vì vậy “bất khả thi” chỉ đúng khi hệ thống dữ liệu quy định hai role loại trừ nhau. Đừng lấy ví dụ này để kết luận Spring Security mặc định chỉ có một role cho mỗi user.

### 7.3. Nhầm ROLE_ prefix

`hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` với prefix mặc định. `hasAuthority("ADMIN")` kiểm tra đúng chuỗi `ADMIN`. Không tùy tiện thêm `ROLE_` vào `hasRole` rồi kỳ vọng hoạt động như `hasAuthority`. Nếu ứng dụng đã tùy chỉnh role prefix, phải đọc policy thực tế và test authority mapping.

### 7.4. Trả null khi đáng ra phải deny

Nếu custom manager không thể xác định quyền do tenant ID thiếu, database không trả dữ liệu hoặc request không hợp lệ, **không nên mặc định trả null** rồi trông chờ AND deny. Với allOf, một điều kiện abstain có thể bị bỏ qua. Tùy tình huống, trả `new AuthorizationDecision(false)` hoặc để exception xử lý theo chính sách lỗi rõ ràng.

Ví dụ code minh họa fail closed:

```java
AuthorizationManager<RequestAuthorizationContext> featureCheck =
        (authentication, context) -> {
            boolean featureEnabled = false; // Ví dụ policy bị đóng
            return new AuthorizationDecision(featureEnabled);
        };
```

Đây là fragment đơn giản minh họa kết quả false rõ ràng, không phải một hệ thống feature flags. Nếu phải dùng remote policy service, cần phân biệt **policy deny** với **sự cố dịch vụ** trong audit/monitoring.

### 7.5. Side effects và thứ tự gọi

Một manager có thể không được gọi nếu:

- `allOf`: manager trước đã deny.
- `anyOf`: manager trước đã grant.

Vì vậy không gắn hành động bắt buộc như “luôn ghi audit log” vào chỉ manager cuối. Audit nên được thực hiện bằng cơ chế đảm bảo coverage cho các trường hợp allow/deny theo thiết kế, thay vì hy vọng mọi nhánh manager đều được đánh giá.

### 7.6. Phân quyền không phải kiểm tra object ownership

`hasRole("USER")` + `REPORT_READ` có thể đủ cho tài liệu công khai của nhóm, nhưng không tự biết người dùng có được xem **report ID cụ thể** hay không. Với quy tắc “owner hoặc admin”, manager custom phải dựa trên **Authentication đáng tin** và **server-side resource ownership**; client chỉ cung cấp mã report, không cung cấp kết luận “tôi là owner”.

Phần API HTTP có thể dùng `RequestAuthorizationContext.getRequest()` hoặc `getVariables()` (khi request matcher điền variables) để lấy thông tin request; service phân quyền phải tra cứu quyền thật. Tránh dùng `X-Role` hoặc `X-Admin: true` do client gửi làm bằng chứng.

## 8. Lập chính sách dễ đọc và dễ test

Không phải luôn cần cả `allOf` lẫn `anyOf`. Nên chọn mức biểu đạt đơn giản nhất:

- Một authority: `hasAuthority("REPORT_READ")`.
- Một role: `hasRole("ADMIN")`.
- Một trong nhiều authority: `hasAnyAuthority("REPORT_READ", "REPORT_EXPORT")`.
- **AND giữa hai loại ràng buộc:** `allOf(hasRole("ADMIN"), hasAuthority("REPORT_EXPORT"))`.
- **OR giữa hai policy không đồng nhất:** `anyOf(hasRole("ADMIN"), customOwnerRule)`.
- **Lồng nhiều cấp:** `allOf(authenticated(), anyOf(hasAuthority("REPORT_READ"), hasRole("ADMIN")))`.

Tách managers thành biến có tên mang ý nghĩa nghiệp vụ giúp người review không đọc nhầm:

```java
AuthorizationManager<RequestAuthorizationContext> reportReadAccess = ...;
AuthorizationManager<RequestAuthorizationContext> exportAccess = ...;
AuthorizationManager<RequestAuthorizationContext> reviewAccess = ...;
```

Đây là **fragment mô tả đặt tên**, không phải source runnable; dấu ba chấm cần thay bằng manager thật. Ví dụ hoàn chỉnh ngay sau đây không dùng placeholder.

### Lưu ý khi có nhiều SecurityFilterChain

`SecurityFilterChain` được chọn bởi `securityMatcher`, và **chỉ chain khớp đầu tiên** áp dụng cho request. `requestMatchers` bên trong `authorizeHttpRequests` chọn rule cho URL/method trong chain đã được chọn.

Nếu bạn đặt API chain sau một web fallback chain nhận mọi URL, những `allOf`/`anyOf` của API có thể **không bao giờ được gọi**. Trước khi debug logic AND/OR, hãy xác minh request đã đi vào đúng chain.

## 9. Project chạy được: Java 17 + Spring Boot 3.3.5 + HTTP Basic

Ta tạo một ứng dụng Spring MVC Servlet đơn giản gồm:

| Method/URL | Chính sách | Response khi được phép |
| --- | --- | --- |
| `GET /public` | `permitAll()` | `public:ok` |
| `GET /reports/view` | `authenticated() AND (REPORT_READ OR ROLE_ADMIN)` | `report:view:<username>` |
| `GET /reports/export` | `ROLE_ADMIN AND REPORT_EXPORT` | `report:export:<username>` |
| `GET /review` | `ROLE_ADMIN OR ROLE_AUDITOR` | `review:<username>` |

Ta dùng HTTP Basic với `SessionCreationPolicy.STATELESS` để dễ thử bằng `curl`. Việc dùng Basic **chỉ phục vụ ví dụ**: logic `AuthorizationManager` vẫn dùng được với form login và Bearer token khi authentication mechanism phù hợp. Production luôn dùng HTTPS và cơ chế bảo vệ credentials theo yêu cầu hệ thống.

Tài khoản demo (tất cả có password `demo123` **chỉ dùng local**):

| Username | Authorities | Ý nghĩa |
| --- | --- | --- |
| `reader` | `ROLE_USER`, `REPORT_READ` | Được xem báo cáo, không export/review |
| `auditor` | `ROLE_AUDITOR` | Được review, không tự có `REPORT_READ` |
| `admin` | `ROLE_ADMIN`, `REPORT_EXPORT` | Được view/export/review |
| `adminNoExport` | `ROLE_ADMIN` | Được view/review, **không** được export |
| `guest` | `ROLE_GUEST` | Đã login nhưng không đạt các rule protected |

### 9.1. Cấu trúc dự án

```text
authorization-composition/
├── pom.xml
└── src/main/java/example/authorization/
    ├── AuthorizationApplication.java
    ├── SecurityConfig.java
    └── ReportController.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>authorization-composition</artifactId>
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

### 9.3. AuthorizationApplication.java

```java
package example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java: kết hợp AND/OR

```java
package example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.AuthenticatedAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_USER", "REPORT_READ")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_AUDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN", "REPORT_EXPORT")
                .build();

        UserDetails adminNoExport = User.withUsername("adminNoExport")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_ADMIN")
                .build();

        UserDetails guest = User.withUsername("guest")
                .password(encoder.encode("demo123"))
                .authorities("ROLE_GUEST")
                .build();

        return new InMemoryUserDetailsManager(
                reader, auditor, admin, adminNoExport, guest);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {

        // /reports/view = authenticated AND
        //                 (REPORT_READ OR ROLE_ADMIN)
        AuthorizationManager<RequestAuthorizationContext> readOrAdmin =
                AuthorizationManagers.anyOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasAuthority(
                                        "REPORT_READ"),
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN")
                );

        AuthorizationManager<RequestAuthorizationContext> viewRule =
                AuthorizationManagers.allOf(
                        AuthenticatedAuthorizationManager
                                .<RequestAuthorizationContext>authenticated(),
                        readOrAdmin
                );

        // /reports/export = ROLE_ADMIN AND REPORT_EXPORT
        AuthorizationManager<RequestAuthorizationContext> exportRule =
                AuthorizationManagers.allOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN"),
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasAuthority(
                                        "REPORT_EXPORT")
                );

        // /review = ROLE_ADMIN OR ROLE_AUDITOR
        AuthorizationManager<RequestAuthorizationContext> reviewRule =
                AuthorizationManagers.anyOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN"),
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("AUDITOR")
                );

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/reports/view")
                    .access(viewRule)
                .requestMatchers(HttpMethod.GET, "/reports/export")
                    .access(exportRule)
                .requestMatchers(HttpMethod.GET, "/review")
                    .access(reviewRule)
                .anyRequest().denyAll()
        );

        // Bật Basic để tập trung test authorization bằng curl.
        http.httpBasic(Customizer.withDefaults());

        // Không dùng HTTP session cho identity giữa các request API demo.
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Không bật form login cho demo API; CSRF mặc định được giữ.
        http.formLogin(form -> form.disable());
        return http.build();
    }
}
```

Phân tích cách ghép:

1. **`readOrAdmin`** là `anyOf`: người có `REPORT_READ` **hoặc** `ROLE_ADMIN` vượt qua bước này.
2. **`viewRule`** là `allOf`: phải có authentication hợp lệ **và** vượt qua `readOrAdmin`.
3. **`exportRule`** là `allOf`: admin chưa có `REPORT_EXPORT` vẫn bị từ chối.
4. **`reviewRule`** là `anyOf`: auditor được review dù không có `REPORT_READ`.
5. `.access(viewRule)` gắn `AuthorizationManager<RequestAuthorizationContext>` vào rule HTTP Servlet tương ứng.
6. `anyRequest().denyAll()` khiến URL hoặc method không có rule không bị mở ngoài ý muốn.
7. `httpBasic()` + `STATELESS` giúp mỗi request được xác thực riêng. Cơ chế role/authority không phụ thuộc HTTP Basic, nhưng ví dụ không cần HTML login/session để test.
8. CSRF **không bị tắt**: các endpoint bài demo chỉ GET. Nếu thêm POST/PUT/PATCH/DELETE, thiết kế CSRF theo client/threat model, không disable bảo vệ toàn cục chỉ vì muốn test.
9. `hasRole` dùng role prefix mặc định; dữ liệu user khai báo bằng `.authorities("ROLE_ADMIN", ...)` chính xác, tránh nhầm `.roles()` với `.authorities()`.
10. Demo hard-code password chỉ để học local. Production dùng user store/IdP, password hashing và HTTPS; không để password thật trong source hoặc shell history.

### 9.5. ReportController.java

```java
package example.authorization;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/public")
    public String publicPage() {
        return "public:ok";
    }

    @GetMapping("/reports/view")
    public String view(Authentication auth) {
        return "report:view:" + auth.getName();
    }

    @GetMapping("/reports/export")
    public String export(Authentication auth) {
        return "report:export:" + auth.getName();
    }

    @GetMapping("/review")
    public String review(Authentication auth) {
        return "review:" + auth.getName();
    }
}
```

Những controller methods này không tự quyết định quyền. `AuthorizationFilter` áp dụng `AuthorizationManagers.allOf/anyOf` **trước khi request đến controller**. Controller chỉ thấy request đã được phép và `Authentication` tương ứng.

### 9.6. Chạy ứng dụng

Tại thư mục có `pom.xml`, cần JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Mặc định Spring Boot mở server tại `http://localhost:8080`. Các lệnh `curl` dưới đây **chỉ dùng local**; môi trường thật bắt buộc HTTPS để không lộ HTTP Basic credentials.

## 10. Bài kiểm thử HTTP cho AND/OR

### 10.1. Anonymous vào public endpoint

```bash
curl -s http://localhost:8080/public
```

Body dự kiến:

```text
public:ok
```

Vì `permitAll()`, endpoint công khai không yêu cầu user có authority nào.

### 10.2. Anonymous vào endpoint cần phân quyền

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/reports/view
```

Kết quả dự kiến:

```text
401
```

Đường anonymous không có Basic credentials sẽ bị policy deny và Basic authentication entry point phát challenge. Đây là trường hợp thiếu authentication, không phải người đã xác thực nhưng thiếu `REPORT_READ`.

### 10.3. Reader được xem báo cáo nhờ REPORT_READ

```bash
curl -s --user reader:demo123 \
  http://localhost:8080/reports/view
```

Body dự kiến:

```text
report:view:reader
```

`authenticated()` grant, `hasAuthority("REPORT_READ")` grant → `anyOf` grant → `allOf` grant.

### 10.4. Admin được xem báo cáo dù không có REPORT_READ

```bash
curl -s --user admin:demo123 \
  http://localhost:8080/reports/view
```

Body dự kiến:

```text
report:view:admin
```

Admin không được khai báo `REPORT_READ` nhưng có `ROLE_ADMIN`; nhánh OR thứ hai trong `anyOf` grant, nên tổng vẫn grant.

### 10.5. Auditor chỉ có ROLE_AUDITOR không được tự xem báo cáo

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user auditor:demo123 http://localhost:8080/reports/view
```

Kỳ vọng:

```text
403
```

`auditor` đã xác thực nhưng **cả** `REPORT_READ` và `ROLE_ADMIN` đều không có. Tổ hợp OR deny, dẫn tới AND deny. Đây là authorization failure, không phải password error.

### 10.6. Auditor được review theo nhánh OR

```bash
curl -s --user auditor:demo123 \
  http://localhost:8080/review
```

Body dự kiến:

```text
review:auditor
```

`anyOf(ROLE_ADMIN,ROLE_AUDITOR)` thành công nhờ nhánh auditor.

### 10.7. Reader không có role để review

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user reader:demo123 http://localhost:8080/review
```

Kỳ vọng:

```text
403
```

`reader` có `REPORT_READ` nhưng không thuộc nhóm admin/auditor; quyền đọc báo cáo không tự động biến thành quyền review.

### 10.8. Admin đủ hai điều kiện mới export được

```bash
curl -s --user admin:demo123 \
  http://localhost:8080/reports/export
```

Body:

```text
report:export:admin
```

Cả `ROLE_ADMIN` và `REPORT_EXPORT` cùng đúng nên `allOf` grant.

### 10.9. Admin thiếu REPORT_EXPORT bị từ chối

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user adminNoExport:demo123 \
  http://localhost:8080/reports/export
```

Kỳ vọng:

```text
403
```

Trường hợp này chứng minh `allOf` không đồng nghĩa “chỉ cần role ADMIN”. Một điều kiện thiếu làm toàn bộ policy deny.

### 10.10. Guest đã đăng nhập vẫn bị chặn

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  --user guest:demo123 http://localhost:8080/reports/view
```

Kỳ vọng:

```text
403
```

`guest` đã xác thực, nhưng không có một trong hai điều kiện xem báo cáo. Nếu nhầm sang `anyOf(authenticated(), ...)`, guest sẽ được truy cập — một regression bảo mật nghiêm trọng.

### Bảng kết quả cần đối chiếu

| User và endpoint | `authenticated` | Role/authority phù hợp | Kết quả dự kiến |
| --- | --- | --- | --- |
| anonymous `GET /public` | Không | Không cần | 200 |
| anonymous `GET /reports/view` | Không | Không | 401 |
| reader `GET /reports/view` | Có | `REPORT_READ` | 200 |
| admin `GET /reports/view` | Có | `ROLE_ADMIN` | 200 |
| auditor `GET /reports/view` | Có | Không đủ | 403 |
| auditor `GET /review` | Có | `ROLE_AUDITOR` | 200 |
| reader `GET /review` | Có | Không đủ | 403 |
| admin `GET /reports/export` | Có | Cả role và permission | 200 |
| adminNoExport `GET /reports/export` | Có | Thiếu export permission | 403 |
| guest `GET /reports/view` | Có | Không đủ | 403 |

**Lưu ý thử nghiệm:** đây là **kết quả dự kiến từ cấu hình mẫu**, không phải transcript thực thi trên môi trường của người học. Test end-to-end khi tích hợp các authentication providers, proxy, filter chain hoặc method security khác.

## 11. Kiểm thử bằng Spring Security Test và MockMvc

Các lệnh `curl` là integration smoke tests. Khi phát triển code dài hạn, nên tạo **test tự động** kiểm tra các nhánh AND/OR và ranh giới role/permission.

Thêm dependency test vào `pom.xml` nếu muốn mở rộng project:

```xml
<!-- Thêm vào phần dependencies khi muốn viết tests -->
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
```

Ví dụ **fragment JUnit 5/MockMvc** khi đã thêm dependencies trên:

```java
package example.authorization;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readerCanViewButCannotExport() throws Exception {
        mvc.perform(get("/reports/view")
                .with(user("reader").authorities(
                        new org.springframework.security.core.authority
                                .SimpleGrantedAuthority("REPORT_READ"))))
                .andExpect(status().isOk());

        mvc.perform(get("/reports/export")
                .with(user("reader").authorities(
                        new org.springframework.security.core.authority
                                .SimpleGrantedAuthority("REPORT_READ"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminWithoutExportAuthorityCannotExport() throws Exception {
        mvc.perform(get("/reports/export")
                .with(user("adminNoExport").roles("ADMIN")))
                .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReview() throws Exception {
        mvc.perform(get("/review").with(user("auditor").roles("AUDITOR")))
                .andExpect(status().isOk());
    }
}
```

Các test trên minh họa **cách inject Authentication vào security context của MockMvc**; chúng **không kiểm thử mật khẩu HTTP Basic** hay user store thật. Để kiểm tra end-to-end authentication, cần test với HTTP Basic credentials qua `httpBasic(...)` của `spring-security-test` hoặc client thực, còn để test authorization tập trung, `user(...)` giúp phân lập rõ điều kiện grant/deny.

Trong code test, nếu một username không có trong `UserDetailsService` nhưng MockMvc được gắn `user(...)`, rule authorization vẫn có thể đánh giá dựa trên Authentication mock; đó là **đặc điểm của test setup**, không phải một user đã login thực sự qua provider.

## 12. Kết hợp custom AuthorizationManager khi role tĩnh chưa đủ

Một số nghiệp vụ cần kiểm tra **quyền sở hữu** hoặc **trạng thái của tài nguyên**:

```text
CAN_EDIT = authenticated() AND
           (ROLE_ADMIN OR (IS_OWNER AND DOCUMENT_NOT_ARCHIVED))
```

Ở đây `IS_OWNER` và `DOCUMENT_NOT_ARCHIVED` phải được xác định theo dữ liệu server, thường bởi service/repository, không từ một flag client tự gửi lên.

Một thiết kế có thể dùng:

```java
// Fragment: ownershipRule và documentStateRule phải là các
// AuthorizationManager<RequestAuthorizationContext> do app triển khai.
AuthorizationManager<RequestAuthorizationContext> ownerCanEdit =
        AuthorizationManagers.allOf(
                ownershipRule,
                documentStateRule
        );

AuthorizationManager<RequestAuthorizationContext> editRule =
        AuthorizationManagers.allOf(
                AuthenticatedAuthorizationManager
                        .<RequestAuthorizationContext>authenticated(),
                AuthorizationManagers.anyOf(
                        AuthorityAuthorizationManager
                                .<RequestAuthorizationContext>hasRole("ADMIN"),
                        ownerCanEdit
                )
        );
```

**Fragment không độc lập** vì `ownershipRule` và `documentStateRule` là phần nghiệp vụ. Việc lồng `allOf` và `anyOf` không thay thế kiểm tra resource ownership trên server. Nếu path có `/documents/{id}`, custom manager có thể lấy ID từ request và gọi repository trong tầng tin cậy để biết owner/archived; không tin `X-Owner: true`.

### Tránh TOCTOU khi kiểm tra quyền và thực thi hành động

Quyền sở hữu/ trạng thái tài nguyên có thể thay đổi giữa lúc authorization filter kiểm tra và controller cập nhật database. Với thao tác ghi nhạy cảm, ngoài HTTP authorization, service/domain layer có thể cần kiểm tra lại trong transaction, optimistic locking hoặc điều kiện update có bảo đảm nhất quán. **Một allow decision trước controller không loại bỏ mọi race condition**.

## 13. Bảo mật, hiệu năng và khả năng bảo trì

### Fail closed và exception

Đối với quy tắc bắt buộc, trả deny rõ ràng khi dữ liệu không đủ. Nếu authorization service bị lỗi, cần phân biệt **sự cố hạ tầng** với policy deny, nhưng đừng vô tình trả `grant` để “giữ hệ thống hoạt động”. Nếu custom manager ném exception, response có thể là lỗi server hoặc được xử lý theo filter/exception handling tùy thiết kế; không mặc định mọi exception trở thành 403.

### Đánh giá ngắn mạch

`allOf` thường dừng khi gặp deny; `anyOf` thường dừng khi gặp grant. Điều đó giúp tránh chạy nhánh không cần thiết nhưng cũng làm **thứ tự managers có ảnh hưởng đến lượng xử lý**. Đừng dựa vào tất cả nhánh được gọi để thực hiện audit, charging hoặc cập nhật business state. `AuthorizationManager` nên **đọc dữ liệu và quyết định**, không tạo side effects.

### Tối ưu kiểm tra quyền

Nếu nhiều nhánh cùng cần gọi repository hoặc remote policy service, hãy cân nhắc cache trong phạm vi request, tránh N+1 calls, và chỉ tải tài nguyên cần kiểm tra. Không cache quyền vượt qua thay đổi account status/role/tenant membership mà thiếu chính sách invalidation.

### Ghi log an toàn

Nên ghi lại rule ID, resource ID đã được xử lý an toàn, kết quả grant/deny và correlation ID. Không ghi raw password, access token, session cookie hoặc toàn bộ Authentication chứa credentials. Audit denial/allow phải bao quát cả nhánh short-circuit.

### Testing và code review

Cần test đủ:

- **Positive:** mỗi nhánh OR cho phép đúng người cần được phép.
- **Negative:** thiếu bất kỳ điều kiện nào trong AND phải bị từ chối.
- **Anonymous:** unauthenticated phải không vô tình grant do `anyOf(authenticated(),...)`.
- **Role prefix:** `ROLE_ADMIN` khác `ADMIN`, `hasRole` khác `hasAuthority`.
- **Abstain/null:** custom manager trả null có thể khiến `allOf` cho phép ngoài dự kiến.
- **Method/URL:** các method HTTP khác ngoài GET không được tự mở nếu không có rule.
- **Ownership:** không tin dữ liệu do client khai, kiểm tra đúng tài nguyên cụ thể.
- **Multiple chains:** request phải vào đúng `SecurityFilterChain`.

## 14. Bảng debug nhanh

| Triệu chứng | Nguyên nhân có thể | Cách tìm lỗi |
| --- | --- | --- |
| Người dùng có role ADMIN nhưng bị 403 ở export | `allOf` còn yêu cầu `REPORT_EXPORT` | Xem chính xác authorities của Authentication và cả hai nhánh |
| Mọi user đăng nhập đều xem được admin endpoint | Dùng `anyOf(authenticated(), hasRole("ADMIN"))` | Đổi cấu trúc thành `allOf` hoặc rule role thích hợp |
| Auditor bị 403 ở review | `ROLE_AUDITOR` không có trong authorities hoặc sai prefix | So `hasRole("AUDITOR")` với `ROLE_AUDITOR` thực tế |
| Anonymous nhận 401 thay vì 403 | Entry point HTTP Basic được kích hoạt vì thiếu authentication | Đây là hành vi bình thường cho anonymous |
| User login thành công nhưng 403 | Authentication đúng, authorization deny | Đừng sửa password encoder; kiểm tra policy |
| `allOf` grant khi custom manager không quyết định | Manager trả null, không trả false | Trả deny rõ khi thiếu dữ liệu hoặc cấu trúc policy sai |
| Một nhánh manager không chạy | AND đã deny hoặc OR đã grant ở nhánh trước | Không dựa vào nhánh đó cho side effects/audit |
| API trả 302 login thay vì 401 | Web chain/form entry point nhận request API | Kiểm tra `securityMatcher`, `@Order`, entry point |
| `access(...)` không compile do generic type | Manager có kiểu không khớp `RequestAuthorizationContext` | Kiểm tra generic `AuthorizationManager<RequestAuthorizationContext>` |
| Quy tắc tài nguyên cụ thể bị bypass | Chỉ kiểm tra role, chưa kiểm tra ownership thực tế | Bổ sung custom manager/service thuộc server |
| GET bị chặn 403 không rõ lý do | `anyRequest().denyAll`, URL/method không khớp hoặc thiếu authority | Xem rule order, path, HTTP method |
| Đổi role nhưng quyền chưa cập nhật | Cache/session context có authorities cũ | Thiết kế refresh/re-auth/invalidation phù hợp |

Quy trình xác minh từng bước:

1. Xác minh **request vào đúng filter chain**.
2. Xác minh **Authentication được tạo từ credentials hợp lệ**, không lấy authority từ client.
3. Xác minh authorities thực tế và prefix `ROLE_`.
4. Xác minh `allOf` hay `anyOf` đúng với yêu cầu **AND/OR**.
5. Với custom manager, xác minh trường hợp **null/abstain** và exception.
6. Xác minh rule match đúng URL/method; `requestMatchers` xét theo thứ tự khai báo.
7. Test HTTP status 200/401/403 và body tại controller.
8. Test sau thay đổi role, resource owner hoặc trạng thái tài nguyên.

Ở development, có thể thêm:

```properties
logging.level.org.springframework.security=DEBUG
```

Không bật raw credentials logging trong production hoặc đưa quyền nhạy cảm/PII vào log không kiểm soát.

## 15. Tự kiểm tra

1. **`allOf` là AND hay OR?** AND: không manager nào được phủ quyết; với managers Boolean rõ ràng, tất cả phải grant.
2. **`anyOf` là AND hay OR?** OR: chỉ cần một manager grant.
3. **`anyOf(authenticated(), hasRole("ADMIN"))` có bảo vệ admin endpoint không?** Không: user bình thường đăng nhập cũng thỏa nhánh đầu.
4. **Admin có role nhưng không có REPORT_EXPORT có được export nếu dùng allOf không?** Không.
5. **Auditor không có REPORT_READ nhưng có ROLE_AUDITOR có được review không?** Có, theo `anyOf(ADMIN,AUDITOR)` của ví dụ.
6. **Authenticated user không đủ quyền nhận HTTP gì với Basic?** Thường 403.
7. **Anonymous tới endpoint bảo vệ nhận gì với Basic?** Thường 401 + challenge.
8. **`hasRole("ADMIN")` và `hasAuthority("ADMIN")` giống nhau không?** Không, prefix role mặc định khác.
9. **Nếu custom manager `check(...)` trả null, `allOf` chắc chắn deny không?** Không, đó là bẫy fail-open cần tránh.
10. **Có nên thực hiện side effects trong mọi manager?** Không, vì combinators có thể dừng đánh giá sớm.
11. **`RequestAuthorizationContext` dùng cho HTTP Servlet hay method security?** HTTP Servlet, còn method security dùng kiểu ngữ cảnh khác.
12. **Cần kiểm tra ownership tài nguyên ở đâu?** Với dữ liệu server đáng tin, có thể trong custom manager và đặc biệt service/domain layer nếu thao tác nhạy cảm.

## 16. Checklist áp dụng vào hệ thống thật

- [ ] Viết quy tắc nghiệp vụ dưới dạng AND/OR rõ ràng trước khi code.
- [ ] Dùng `AuthorizationManagers.allOf` cho các điều kiện **đều bắt buộc**.
- [ ] Dùng `AuthorizationManagers.anyOf` cho các nhánh **thay thế hợp lệ**.
- [ ] Tránh nhánh OR quá rộng như `authenticated()` khi thực chất cần role/permission.
- [ ] Khai báo manager đúng kiểu `AuthorizationManager<RequestAuthorizationContext>` cho Servlet HTTP.
- [ ] Dùng `hasRole`, `hasAuthority` và role prefix thống nhất với nguồn authorities tin cậy.
- [ ] Với custom manager, xác định rõ behavior grant/deny/null và xử lý lỗi hạ tầng an toàn.
- [ ] Không dùng combinator để làm side effects cần chạy chắc chắn; test short-circuit.
- [ ] Xác minh security chain, method/path matchers và fallback `denyAll()`.
- [ ] Kiểm tra quyền sở hữu tài nguyên và ranh giới tenant trên server khi role tĩnh chưa đủ.
- [ ] Test các tổ hợp user/role/authority dương và âm, đặc biệt trường hợp thiếu một nhánh của AND.
- [ ] Test anonymous vs authenticated để phân biệt 401/403.
- [ ] Cấu hình HTTPS, session/token lifecycle và audit theo kiến trúc; authorization rule không thay thế các lớp đó.

**Kết luận:** `AuthorizationManagers.allOf` và `AuthorizationManagers.anyOf` cho phép mô tả **chính sách phân quyền HTTP có cấu trúc, kiểm thử được** trên Spring Security Servlet. `allOf` dùng khi **mọi yêu cầu đều phải đạt**; `anyOf` dùng khi **một trong nhiều nhánh hợp lệ là đủ**. Cần đặc biệt cảnh giác với **OR quá rộng**, sai `ROLE_` prefix, manager custom **abstain/null** và assumption rằng mọi nhánh luôn chạy. Khi quyền phụ thuộc tài nguyên/tenant, việc tổ hợp managers phải đi cùng kiểm tra dữ liệu server đáng tin cậy.