# @EnableMethodSecurity và các nhóm annotation được kích hoạt — Spring Security Servlet

Trong ứng dụng Spring Security, việc người dùng vượt qua lớp bảo vệ URL **không có nghĩa họ được phép thực hiện mọi nghiệp vụ mà controller gọi**. Một controller `GET /api/docs/42` có thể yêu cầu “đã đăng nhập”, nhưng service đọc tài liệu còn phải kiểm tra quyền của người dùng đối với chính tài liệu đó. Spring Security hỗ trợ đặt quyết định phân quyền ở **ranh giới phương thức** thông qua các annotation như `@PreAuthorize`, `@PostAuthorize`, `@Secured` và `@RolesAllowed`.

Để các annotation đó thực sự có tác dụng, ứng dụng phải bật **method security** bằng `@EnableMethodSecurity` và chọn đúng các **nhóm annotation** cần sử dụng. Đây là một chỗ dễ cấu hình thiếu: với Spring Security 6.x, nhóm **pre/post annotations được bật mặc định** khi dùng `@EnableMethodSecurity`, trong khi nhóm **@Secured** và **JSR-250** cần **opt-in** qua hai cờ riêng. Viết `@Secured("ROLE_ADMIN")` lên một service mà không bật nhóm tương ứng có thể tạo cảm giác an toàn giả vì annotation không được method-security advisor của nhóm đó thực thi.

Bài này thuộc phần **Bảo vệ phương thức** trong module **Spring Security – servlet**, sử dụng Java 17+, Spring Security 6.x và ví dụ Spring Boot 3.3.5. Trọng tâm là **annotation nào được kích hoạt, mỗi nhóm làm gì, điều kiện AOP proxy để interception xảy ra, và cách kiểm chứng bằng test thực tế**.

## 1. Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Giải thích sự khác nhau giữa **HTTP request authorization** và **method authorization**.
2. Biết chính xác trạng thái mặc định của `prePostEnabled`, `securedEnabled` và `jsr250Enabled` trong `@EnableMethodSecurity`.
3. Sử dụng các annotation thuộc ba nhóm: `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter`; `@Secured`; `@RolesAllowed`/`@PermitAll`/`@DenyAll`.
4. Phân biệt **role** với **authority**; hiểu `ROLE_` prefix, SpEL, `Authentication`, tham số phương thức và `returnObject`.
5. Biết tại sao `@PostAuthorize` không nên dùng để bảo vệ một thao tác đã gây side effect.
6. Mô tả được giới hạn **proxy-based AOP**: self-invocation, private/final methods, method calls không đi qua proxy, bean không được Spring quản lý.
7. Kích hoạt nhóm annotation bằng `@EnableMethodSecurity(prePostEnabled = true, securedEnabled = true, jsr250Enabled = true)` và viết kiểm thử **đủ cả allow và deny**.
8. Phát hiện lỗi thiếu annotation group, phân quyền ở sai tầng, biến cấu hình method security thành HTTP bypass hoặc dùng test mocking che mất AOP.

## 2. Method security giải quyết vấn đề gì?

Hãy nhìn một chuỗi gọi nghiệp vụ:

~~~text
GET /api/docs/42
       |
       v
Spring Security Servlet FilterChain
  -> authentication: principal/authorities?
  -> HTTP authorization: endpoint cần authenticated?
       |
       v
Spring MVC Controller
       |
       v
DocumentService.findById("42")
       |
       +-- Method security kiểm tra:
       |     User này có quyền đọc tài liệu 42 không?
       |
       +-- Được phép -> phương thức chạy / trả dữ liệu
       +-- Bị từ chối -> AccessDeniedException
~~~

HTTP authorization thường phù hợp với điều kiện trên **URL + method + role/scope chung**. Nhưng quyền ở tầng service còn phụ thuộc **tham số hoặc dữ liệu trả về**, ví dụ: “chỉ xem bản ghi thuộc tenant hiện tại”, “chỉ cập nhật hóa đơn do mình sở hữu”, hoặc “chỉ admin được gọi nghiệp vụ này dù nhiều controllers cùng sử dụng”.

Ví dụ hai cấp kiểm tra:

~~~java
// HTTP: chỉ yêu cầu đã đăng nhập cho namespace.
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())

// Method: yêu cầu đúng chủ thể hoặc quản trị viên.
// Đặt trên phương thức service Spring bean:
@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
public String profileOf(String username) {
    return "Profile of " + username;
}
~~~

Đoạn trên gồm **hai mảnh code** thuộc hai lớp cấu hình khác nhau, không phải một class độc lập. Nếu reader muốn truy cập profile của admin, HTTP authorization có thể cho đi qua vì reader đã đăng nhập, nhưng **service proxy từ chối** trước khi chạy method.

**Method security không thay thế authentication.** Annotation cần một `Authentication` được hình thành từ nguồn đáng tin (session/form login, HTTP Basic, JWT decoder, v.v.). Nếu custom filter tự gán `ROLE_ADMIN` từ một header chưa được xác minh, method security có thể đánh giá trên authorities giả và cấp quyền sai.

## 3. Bật @EnableMethodSecurity: những cờ cần thuộc

### 3.1. Cấu hình tối thiểu

Trong một Spring configuration class:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Khi Spring Security method security được bật như trên, nhóm **pre/post annotations** được hỗ trợ mặc định. Nhưng **không** tự động có nghĩa `@Secured` và JSR-250 đều được bật.

### 3.2. Ma trận các nhóm annotation

| Nhóm | Annotation chính | Cờ @EnableMethodSecurity | Mặc định khi chỉ viết @EnableMethodSecurity |
| --- | --- | --- | --- |
| Pre/Post annotations | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` | `prePostEnabled` | **true — bật** |
| Secured annotations | `@Secured` | `securedEnabled` | **false — tắt** |
| JSR-250 annotations | `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `jsr250Enabled` | **false — tắt** |

Bật cả ba nhóm một cách tường minh:

~~~java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
~~~

Không nên mặc định bật mọi nhóm rồi rải annotation trùng lặp lên cùng một method. **Chọn một convention chính cho codebase**, và bật nhóm bổ sung khi thực sự cần tương thích dự án/ thư viện đang dùng. Khi nhiều annotation authorization đồng thời áp lên cùng một lời gọi, các advisors có thể đều tác động; không coi một `@PermitAll` là “override mọi @PreAuthorize khác”.

### 3.3. Những biến thể cấu hình đáng nhớ

**Chỉ dùng pre/post (thường là lựa chọn mặc định):**

~~~java
@EnableMethodSecurity
~~~

**Dùng pre/post và @Secured:**

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

**Dùng pre/post và JSR-250:**

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

**Chỉ dùng @Secured, không bật pre/post:**

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true
)
~~~

**Chỉ dùng JSR-250:**

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    jsr250Enabled = true
)
~~~

Những dòng trên là **các lựa chọn độc lập**, không dán nhiều `@EnableMethodSecurity` vào một ứng dụng rồi hi vọng kết hợp ngầm. Hãy đặt một cấu hình nhất quán và kiểm thử từng annotation thực tế dùng.

### 3.4. Nếu annotation không thuộc nhóm đã bật?

Nếu ứng dụng chỉ dùng `@EnableMethodSecurity` mặc định mà developer thêm:

~~~java
@Secured("ROLE_ADMIN")
public void deleteAllReports() { ... }
~~~

thì advisor xử lý `@Secured` **không được đăng ký theo cấu hình mặc định**. Spring Security method security không tự chuyển annotation này thành `@PreAuthorize`. Nếu HTTP layer chỉ đòi `authenticated()`, request có thể vượt quyền vì service-level check mong đợi **không chạy**.

Tương tự, viết `@RolesAllowed("ADMIN")` mà quên `jsr250Enabled=true` không tạo ra JSR-250 enforcement như mong muốn. **Đây là lý do tests negative-case bắt buộc**: cho user đã xác thực nhưng thiếu quyền gọi đúng phương thức và yêu cầu kết quả là 403/AccessDeniedException.

## 4. Nhóm pre/post: mạnh nhất về biểu thức và dữ liệu

Nhóm này sử dụng biểu thức **Spring Expression Language (SpEL)** và các giá trị có sẵn như `authentication`, `principal`, `hasRole(...)`, `hasAuthority(...)`, tham số phương thức, `returnObject` hoặc `filterObject` tùy annotation.

### 4.1. @PreAuthorize — kiểm tra trước khi chạy method

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void rebuildIndex() {
    // Chỉ thực thi khi có ROLE_ADMIN.
}
~~~

Dùng để bảo vệ hành động **có side effect**: tạo, sửa, xóa, thay đổi trạng thái, gửi email, thanh toán. Khi rule từ chối, phương thức nghiệp vụ không được phép thực thi qua proxy.

Với tham số:

~~~java
@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
public String readProfile(String username) {
    return "profile:" + username;
}
~~~

`#p0` tham chiếu tham số đầu tiên của method và không phụ thuộc compiler có giữ metadata tên tham số hay không. Nếu muốn dùng `#username`, cần chắc chắn tên tham số có thể được Spring Security khám phá (ví dụ compiler option `-parameters` hoặc annotation hỗ trợ). Đừng để một expression chạy được trong IDE nhưng bị deny/ lỗi trên build production vì thiếu parameter names.

**Lưu ý:** Kiểm tra `username == authentication.name` chỉ là ví dụ minh họa identity. Khi dữ liệu thuộc nhiều tenant hoặc tài nguyên có người sở hữu trong DB, quyền phải dựa vào business authorization thật; không tin owner id do client tự khai.

### 4.2. @PostAuthorize — kiểm tra sau khi có returnObject

~~~java
@PostAuthorize(
    "returnObject.owner == authentication.name or hasRole('ADMIN')")
public Document findDocument(String id) {
    return repository.findById(id).orElseThrow();
}
~~~

Đây là **mảnh code minh họa**: `Document` có getter `getOwner()` và `repository` là đối tượng repository thực. Sau khi method trả kết quả, method-security advisor kiểm tra `returnObject` rồi mới cho lời gọi nhận kết quả.

Ưu điểm: có thể kiểm tra quyền dựa trên **thông tin chỉ biết sau khi load object**. Nhược điểm: **method đã chạy rồi**. Nếu method ghi DB, gửi email hoặc gọi API bên ngoài trước khi `@PostAuthorize` từ chối, các side effects có thể đã xảy ra hoặc không được rollback như bạn kỳ vọng. Vì vậy:

- Ưu tiên `@PreAuthorize` hoặc kiểm tra policy **trước** mutation.
- Dùng `@PostAuthorize` cho những read-only operations mà output cần được xét ownership.
- Không xem post-check là bức tường ngăn thực thi một thao tác nhạy cảm.
- Khi method có transaction, ghi rõ thứ tự AOP advisors và transaction boundaries nếu dựa vào rollback.

### 4.3. @PreFilter — lọc input collection trước khi method chạy

~~~java
@PreFilter("filterObject == authentication.name or hasRole('ADMIN')")
public List<String> keepAllowedUsers(List<String> usernames) {
    return List.copyOf(usernames);
}
~~~

Khi proxy nhận danh sách tên user, `@PreFilter` đánh giá từng phần tử trước khi gọi body. Trong ví dụ, user thường chỉ giữ lại tên của mình; admin có thể giữ toàn bộ. Thường dùng với `Collection`/array/map/stream theo khả năng của phiên bản và kiểu dữ liệu; khi có nhiều tham số dạng collection, dùng `filterTarget` để chỉ đích tường minh.

Không coi lọc input là cách thay thế authorization theo đối tượng ở tầng persistence: người gọi có thể bypass logic nếu có đường khác tới database, còn việc sửa collection có thể gây vấn đề với immutable input. Trong ví dụ chạy ở dưới, controller tạo một `ArrayList` mutable để bộ lọc xử lý an toàn.

### 4.4. @PostFilter — lọc collection đầu ra

~~~java
@PostFilter(
    "filterObject.owner == authentication.name or hasRole('ADMIN')")
public List<Document> listDocuments() {
    return new ArrayList<>(repository.findAll());
}
~~~

Đây là mảnh code. Sau khi có một collection kết quả, Spring Security xét từng phần tử thông qua `filterObject`. Người dùng thường chỉ thấy các document được phép; admin có thể thấy tất cả.

**Không thay thế truy vấn có điều kiện bằng @PostFilter nếu dữ liệu lớn hoặc nhạy cảm.** Service có thể đã load hàng nghìn records trước khi lọc; chi phí DB/CPU/memory và rủi ro dữ liệu đi qua logs/cache/side effects vẫn tồn tại. Với sản phẩm thật, ưu tiên query có điều kiện tenant/owner ngay trong DB, và thêm method security như lớp bảo vệ theo chính sách.

### 4.5. Pre/post: khi nào dùng annotation nào?

| Tình huống | Annotation phù hợp để cân nhắc | Điều cần xác minh |
| --- | --- | --- |
| Chỉ admin được xóa dữ liệu | `@PreAuthorize("hasRole('ADMIN')")` | Check trước side effect |
| User xem profile của mình | `@PreAuthorize("#p0 == authentication.name")` | Tham số tin cậy và policy owner |
| Đọc object rồi kiểm tra owner thực | `@PostAuthorize` | Read-only, dữ liệu đã load |
| Loại input không thuộc user | `@PreFilter` | Collection mutable, filterTarget, không leak qua đường khác |
| Danh sách records trả về chỉ phần được phép | `@PostFilter` | Performance, query filtering, paging |
| Cần kiểm tra scope exact từ JWT/OAuth2 | `@PreAuthorize("hasAuthority('SCOPE_docs.read')")` | JWT authority converter mapping |

## 5. Nhóm @Secured: role/authority tĩnh, dễ đọc

Annotation `@Secured` thuộc namespace Spring Security và **không được bật mặc định** với `@EnableMethodSecurity`. Muốn dùng:

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

Ví dụ:

~~~java
@Secured("ROLE_ADMIN")
public String administratorReport() {
    return "only-admin";
}
~~~

`@Secured` dùng danh sách quyền/authority, **không hỗ trợ SpEL tùy ý** như `@PreAuthorize`. Nếu muốn so sánh tham số với Authentication, chính sách tenant, owner hoặc gọi policy bean, `@PreAuthorize` thường phù hợp hơn.

Ví dụ có nhiều authority cho phép:

~~~java
@Secured({"ROLE_ADMIN", "ROLE_AUDITOR"})
public String auditReport() {
    return "audit";
}
~~~

Các giá trị là role authorities theo convention. **Không nhầm** cách ghi giữa `@Secured("ROLE_ADMIN")` và `@PreAuthorize("hasRole('ADMIN')")`. Với role prefix mặc định:

- `@Secured("ROLE_ADMIN")` kiểm tra authority có giá trị `ROLE_ADMIN`.
- `hasRole('ADMIN')` mặc định tra `ROLE_ADMIN`.
- `hasAuthority('ROLE_ADMIN')` kiểm tra đúng chuỗi `ROLE_ADMIN`.
- `hasAuthority('SCOPE_docs.read')` kiểm tra chính xác OAuth2 scope authority convention nếu converter đã cấp authority đó.

Một rule `@Secured("ADMIN")` không tự tương đương `@Secured("ROLE_ADMIN")` trong mọi cấu hình; hãy dùng convention thống nhất.

## 6. Nhóm JSR-250: @RolesAllowed, @PermitAll, @DenyAll

Với Java 17/Spring Boot 3, dùng package **`jakarta.annotation.security`**, không dùng code cũ `javax.annotation.security` từ Java EE theo thói quen. Các annotation chính:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
~~~

Bật:

~~~java
@EnableMethodSecurity(jsr250Enabled = true)
~~~

### 6.1. @RolesAllowed

~~~java
@RolesAllowed("MANAGER")
public String approveReport() {
    return "approved";
}
~~~

Với role prefix thông thường, `@RolesAllowed("MANAGER")` yêu cầu authority `ROLE_MANAGER`. Nó không phải expression SpEL cho một tham số động. Nếu tổ chức đổi role-prefix policy, hãy kiểm tra hành vi cụ thể thay vì tự ghép chuỗi theo giả định.

### 6.2. @PermitAll

~~~java
@PermitAll
public String publicCatalog() {
    return "public";
}
~~~

Cho phép method invocation qua JSR-250 advisor, bao gồm trường hợp anonymous nếu không có lớp khác chặn. Tuy nhiên:

**`@PermitAll` không bypass HTTP authentication/authorization và không tắt CSRF, filter chain hoặc các policy khác.** Nếu HTTP rule của endpoint là `hasRole("ADMIN")`, user anonymous vẫn bị chặn trước khi controller gọi method dù service có `@PermitAll`. Nếu class/method đồng thời có các annotation method security khác, không coi `@PermitAll` là override mọi advisor.

### 6.3. @DenyAll

~~~java
@DenyAll
public void dangerousOperation() {
    throw new IllegalStateException("Must never be reached");
}
~~~

Khi JSR-250 advisor được kích hoạt, mọi lời gọi **đi qua proxy** đến method này phải bị từ chối theo chính sách JSR-250, kể cả user đã có role cao. Đây là cơ chế hữu ích khi muốn cố ý đóng một method hoặc migration chưa an toàn.

Nếu `jsr250Enabled=false`, annotation này không phải một hàng rào bảo vệ mặc định. Do đó test admin bị từ chối `@DenyAll` là cách chứng minh group JSR-250 đã thật sự hoạt động.

### 6.4. So sánh ngắn

| Annotation | Từ package | Cờ kích hoạt | Kiểu kiểm tra |
| --- | --- | --- | --- |
| `@PreAuthorize("hasRole('ADMIN')")` | Spring Security | prePostEnabled | SpEL, trước method |
| `@PostAuthorize("returnObject.owner == ...")` | Spring Security | prePostEnabled | SpEL, sau method |
| `@PreFilter / @PostFilter` | Spring Security | prePostEnabled | Filter input/output |
| `@Secured("ROLE_ADMIN")` | Spring Security | securedEnabled | Authority/role tĩnh |
| `@RolesAllowed("ADMIN")` | Jakarta JSR-250 | jsr250Enabled | Role tĩnh, thường ROLE_ prefix |
| `@PermitAll` | Jakarta JSR-250 | jsr250Enabled | Cho phép theo JSR advisor |
| `@DenyAll` | Jakarta JSR-250 | jsr250Enabled | Từ chối theo JSR advisor |

## 7. Method-security interceptors và AOP proxy

Đây là phần quan trọng nhất để không rơi vào tình huống “đã bật annotation nhưng method vẫn chạy”.

### 7.1. @EnableMethodSecurity kích hoạt hạ tầng gì?

Spring Security 6 dùng cách tiếp cận **AuthorizationManager** để thực hiện method security. Hạ tầng cấu hình thêm các method-security advisors/interceptors vào các Spring beans phù hợp. Nhờ đó một lời gọi qua proxy có thể được đánh giá:

~~~text
Controller bean (Spring quản lý)
      |
      v
ProtectedService proxy
      |
      +--- Before-method authorization (ví dụ @PreAuthorize)
      |       | allowed?
      |       +--- No  -> AccessDeniedException
      |       +--- Yes -> chạy target method
      |
      +--- After-method authorization (@PostAuthorize)
      |       | allowed for returnObject?
      |       +--- No  -> AccessDeniedException
      |       +--- Yes -> trả kết quả
      |
      +--- Filter input/output nếu được gắn @PreFilter/@PostFilter
~~~

Đây là luồng khái niệm, không trình bày exact order của mọi advisor khi có transaction, caching, async hoặc annotation khác. Điều cần nhớ: **phương thức được bảo vệ khi lời gọi thật sự đi qua security proxy/advice**.

### 7.2. Self-invocation có thể bỏ qua kiểm tra

Ví dụ **sai về kỳ vọng**:

~~~java
@Service
public class PaymentService {

    public void batch() {
        // Gọi nội bộ cùng this, có thể không đi qua proxy.
        refund(); 
    }

    @PreAuthorize("hasRole('FINANCE')")
    public void refund() {
        // Thao tác tài chính nhạy cảm.
    }
}
~~~

Với proxy-based mode mặc định, lời gọi `refund()` từ `batch()` trên cùng instance **không đi qua method security proxy**, nên annotation trên `refund()` có thể không được thực thi. Điều này không chứng minh `@PreAuthorize` bị hỏng; **đường gọi đã đi vòng qua proxy**.

Cách thiết kế an toàn thường là:

- Chuyển method bảo vệ vào **Spring bean khác**, để caller inject bean đó và gọi qua proxy.
- Hoặc kiểm tra authorization ở entry point trước khi business action chạy, không phụ thuộc vào một call nội bộ được kỳ vọng có AOP interception.
- Không dùng self-injection/proxy exposure như giải pháp mặc định khi có thể thiết kế lại boundary rõ.
- Nếu thật sự cần AspectJ mode, phải triển khai weaving và kiểm tra deployment tương ứng, không chỉ đổi một flag.

### 7.3. Các method không được proxy intercept

Cần cẩn trọng với:

- `private` method: không phải boundary AOP proxy bình thường.
- `final` method/class trong proxy dựa trên subclass: không thể override để intercept.
- Bean được tạo bằng `new` ngoài Spring container: không có Spring AOP proxy.
- Gọi method trong constructor hoặc khi bean chưa được khởi tạo đầy đủ: có thể diễn ra trước proxy boundary.
- Cấu hình proxy interface vs class, method visibility, compile-time Kotlin `final`, hoặc lời gọi nội bộ cùng target instance.
- Async threads, scheduled jobs, message consumers: phải có `SecurityContext`/identity propagation đúng, không mặc định lấy HTTP request context tồn tại.

Do đó nên đặt method annotations ở **public service methods trong Spring-managed beans**, được gọi từ các bean khác qua dependency injection, kèm integration tests chứng minh advisor thực thi.

### 7.4. Proxy mode và AspectJ mode

`@EnableMethodSecurity` hỗ trợ cấu hình kiểu advice, điển hình:

~~~java
@EnableMethodSecurity(
    mode = AdviceMode.PROXY,
    proxyTargetClass = false
)
~~~

Đây là mảnh code minh họa, cần import `org.springframework.context.annotation.AdviceMode` và annotation tương ứng. Với mode proxy, Spring có thể dùng interface-based proxy hoặc class-based proxy theo cấu hình/hạ tầng thực. `proxyTargetClass = true` thường yêu cầu proxy kiểu class nhưng vẫn phải chú ý final methods/classes và self-invocation.

AspectJ weaving là phương án khác khi kiến trúc đòi interception vượt giới hạn proxy. **Nó yêu cầu cấu hình weaving, dependencies và test riêng**; không chỉ sửa `mode = AdviceMode.ASPECTJ` rồi cho rằng mọi internal call đã được bảo vệ.

### 7.5. Đừng đặt security rule trên một method không có caller thực

Một annotation viết trên một interface hoặc class không được Bean Factory đưa vào proxy path có thể không được áp dụng như bạn kỳ vọng. Trong codebase lớn, hãy rà soát kiến trúc invocation: request/controller → injected service proxy → method annotated. Test method trực tiếp trên object tạo bằng `new` không chứng minh method security có hiệu lực.

## 8. HTTP security và method security là hai lớp cộng tác

Một ứng dụng vừa có:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
~~~

vừa có:

~~~java
@Secured("ROLE_ADMIN")
public String administratorOperation() {
    return "admin-only";
}
~~~

Cần vượt **cả hai lớp** nếu chúng áp dụng:

- Không có authentication: HTTP layer thường trả 401 với HTTP Basic hoặc redirect tới login với form login.
- Có user thường: HTTP layer chấp nhận `authenticated()`, service `@Secured` từ chối vì thiếu ROLE_ADMIN → thường 403.
- Có admin: HTTP layer chấp nhận, service rule có thể chấp nhận → controller trả response.

Chính sách HTTP như `permitAll()` không vô hiệu hóa method-security advisor, nhưng cũng ngược lại: một method `@PermitAll` không mở route đang bị HTTP `denyAll()` hoặc `hasRole(...)` chặn.

### 8.1. Tránh nhầm @EnableMethodSecurity với @EnableWebSecurity

- `@EnableWebSecurity` liên quan cấu hình web/security filter chain.
- `@EnableMethodSecurity` kích hoạt hạ tầng bảo vệ lời gọi method.
- Trong Spring Boot sử dụng starter security, bạn có thể cấu hình `SecurityFilterChain` dưới dạng bean và riêng `@EnableMethodSecurity` mà không nhất thiết phải tự thêm `@EnableWebSecurity` như các ví dụ cấu hình thuần Spring cũ.

**Không giả định Spring Boot Starter Security tự kích hoạt đầy đủ method security** chỉ vì một `SecurityFilterChain` đã hoạt động. Hãy kiểm tra annotation và tests của từng group.

### 8.2. Khi nào trả 401 và khi nào 403?

| Tình huống | Kết quả HTTP phổ biến | Diễn giải |
| --- | --- | --- |
| Anonymous gọi route cần authenticated | 401 với HTTP Basic trong ví dụ | Thiếu authentication |
| User hợp lệ gọi method cần role khác | 403 | Method authorization deny |
| JWT/opaque bearer không hợp lệ | 401 trong resource server điển hình | Authentication thất bại |
| User đúng role và method cho phép | 200/201/... | Qua được cả HTTP và method |
| User gọi @DenyAll qua proxy | 403 khi đã authenticated | Bị JSR-250 policy deny |
| POST thiếu CSRF token trong cookie-based app | Có thể 403 trước khi vào method | Không suy diễn thiếu role |

Cụ thể status phụ thuộc `AuthenticationEntryPoint`, `AccessDeniedHandler`, controller advice và filters. Trong test, kiểm tra trạng thái theo **cấu hình project**; không khẳng định 401/403 là contract của mọi application.

## 9. Ví dụ chạy được: Spring Boot 3.3.5 + Java 17 bật đủ ba nhóm

Ví dụ này cố ý bật:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Tập endpoint minh họa:

- `GET /api/public`: service có `@PermitAll`, HTTP route cũng `permitAll`.
- `GET /api/me/{name}`: `@PreAuthorize` cho chính chủ hoặc admin.
- `GET /api/admin/pre`: `@PreAuthorize("hasRole('ADMIN')")`.
- `GET /api/admin/secured`: `@Secured("ROLE_ADMIN")`.
- `GET /api/manager/jsr`: `@RolesAllowed("MANAGER")`.
- `GET /api/denied`: `@DenyAll` chặn cả admin.
- `GET /api/docs/{id}`: `@PostAuthorize` so ownership của object đã load.
- `GET /api/docs`: `@PostFilter` loại document không thuộc user (trừ admin).
- `GET /api/names?name=reader&name=admin`: `@PreFilter` lọc input list trước khi service chạy.

### 9.1. Cấu trúc file

~~~text
method-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/example/methodsecurity/
    │       ├── MethodSecurityApplication.java
    │       ├── SecurityConfiguration.java
    │       ├── Document.java
    │       ├── ProtectedOperations.java
    │       └── DemoController.java
    └── test/java/example/methodsecurity/
        └── MethodSecurityTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'method-security-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'jakarta.annotation:jakarta.annotation-api'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management chọn các phiên bản Spring Security/Jakarta tương thích. Không trộn `javax.annotation.security` (Java EE cũ) với Spring Boot 3/Jakarta theo thói quen.

### 9.2. Main class

Tệp `src/main/java/example/methodsecurity/MethodSecurityApplication.java`:

~~~java
package example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfiguration: bật cả ba annotation groups

Tệp `src/main/java/example/methodsecurity/SecurityConfiguration.java`:

~~~java
package example.methodsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            // Các endpoint demo chỉ dùng GET, không cần tắt CSRF.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        UserDetails manager = User.withUsername("manager")
            .password(encoder.encode("manager-pass"))
            .roles("MANAGER")
            .build();

        return new InMemoryUserDetailsManager(reader, admin, manager);
    }
}
~~~

Với `roles("ADMIN")`, Spring Security tạo authority `ROLE_ADMIN` theo convention. `roles("MANAGER")` tương ứng `ROLE_MANAGER`. HTTP Basic là để test authentication đơn giản trong local lab, không phải lời khuyên dùng Basic cho mọi hệ thống. Production cần HTTPS và user store/identity provider phù hợp.

**Tại sao HTTP chỉ yêu cầu `authenticated()` cho `/api/**`?** Mục tiêu demo là chứng minh **method security vẫn từ chối một user đã xác thực nhưng thiếu quyền**. Nếu HTTP đã yêu cầu ROLE_ADMIN cho endpoint admin, bạn không thể dùng kết quả HTTP 403 để chắc chắn annotation `@Secured` đã chạy.

### 9.4. Model Document

Tệp `src/main/java/example/methodsecurity/Document.java`:

~~~java
package example.methodsecurity;

public class Document {

    private final String id;
    private final String owner;
    private final String title;

    public Document(String id, String owner, String title) {
        this.id = id;
        this.owner = owner;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Getter `getOwner()` cho phép SpEL dùng biểu thức `returnObject.owner` hoặc `filterObject.owner`. Không tin một `owner` đến từ request body mà không có persistence/business verification; demo tạo objects từ code server.

### 9.5. ProtectedOperations: đủ ba nhóm

Tệp `src/main/java/example/methodsecurity/ProtectedOperations.java`:

~~~java
package example.methodsecurity;

import java.util.ArrayList;
import java.util.List;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProtectedOperations {

    @PermitAll
    public String publicMessage() {
        return "public-ok";
    }

    @PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
    public String profileOf(String name) {
        return "profile:" + name;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String adminPre() {
        return "pre-admin-ok";
    }

    @Secured("ROLE_ADMIN")
    public String adminSecured() {
        return "secured-admin-ok";
    }

    @RolesAllowed("MANAGER")
    public String managerJsr() {
        return "jsr-manager-ok";
    }

    @DenyAll
    public String neverAllowed() {
        return "must-not-return";
    }

    @PostAuthorize(
        "returnObject.owner == authentication.name or hasRole('ADMIN')")
    public Document readDocument(String id) {
        return allDocuments().stream()
            .filter(doc -> doc.getId().equals(id))
            .findFirst()
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PostFilter(
        "filterObject.owner == authentication.name or hasRole('ADMIN')")
    public List<Document> visibleDocuments() {
        // Mutable list để PostFilter có thể lọc an toàn.
        return new ArrayList<>(allDocuments());
    }

    @PreFilter(
        "filterObject == authentication.name or hasRole('ADMIN')")
    public List<String> allowedNames(List<String> names) {
        // Input được method-security advice lọc trước body.
        return List.copyOf(names);
    }

    private List<Document> allDocuments() {
        return List.of(
            new Document("doc-r", "reader", "Reader document"),
            new Document("doc-a", "admin", "Admin document")
        );
    }
}
~~~

**Đọc kỹ vị trí của các method:** Mỗi protected method là `public`, thuộc `@Service` Spring bean và được controller gọi qua **injected proxy**. Private helper `allDocuments()` chỉ tạo dữ liệu; nó không mang annotation authorization nên lời gọi nội bộ ở đây không tạo bypass.

Trong production, thực tế document phải đến từ repository và việc xem/đổi cần kiểm tra tenant/ownership từ dữ liệu server; code trên chỉ minh họa cách các advisors hoạt động.

### 9.6. Controller gọi vào service proxy

Tệp `src/main/java/example/methodsecurity/DemoController.java`:

~~~java
package example.methodsecurity;

import java.util.ArrayList;
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ProtectedOperations protectedOperations;

    public DemoController(ProtectedOperations protectedOperations) {
        this.protectedOperations = protectedOperations;
    }

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return protectedOperations.publicMessage();
    }

    @GetMapping("/api/me/{name}")
    public String profile(@PathVariable String name) {
        return protectedOperations.profileOf(name);
    }

    @GetMapping("/api/admin/pre")
    public String adminPre() {
        return protectedOperations.adminPre();
    }

    @GetMapping("/api/admin/secured")
    public String adminSecured() {
        return protectedOperations.adminSecured();
    }

    @GetMapping("/api/manager/jsr")
    public String manager() {
        return protectedOperations.managerJsr();
    }

    @GetMapping("/api/denied")
    public String denied() {
        return protectedOperations.neverAllowed();
    }

    @GetMapping("/api/docs/{id}")
    public Document doc(@PathVariable String id) {
        return protectedOperations.readDocument(id);
    }

    @GetMapping("/api/docs")
    public List<Document> docs() {
        return protectedOperations.visibleDocuments();
    }

    @GetMapping("/api/names")
    public List<String> names(@RequestParam("name") List<String> names) {
        return protectedOperations.allowedNames(
            new ArrayList<>(names));
    }
}
~~~

Vì controller inject service từ Spring container, lời gọi từ controller tới `ProtectedOperations` đi qua proxy nếu method-security infrastructure đã được kích hoạt. Cấu trúc này **cố ý tránh self-invocation**. Tất cả endpoints là GET, không thực hiện mutation để không làm lệch trọng tâm vào CSRF.

### 9.7. Test đầy đủ allow/deny trên từng nhóm annotation

Tệp `src/test/java/example/methodsecurity/MethodSecurityTests.java`:

~~~java
package example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void permitAllMethodAllowsAnonymousWhenHttpAlsoPermits()
            throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public-ok"));
    }

    @Test
    void protectedRouteNeedsAuthentication() throws Exception {
        mockMvc.perform(get("/api/admin/secured"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preAuthorizeAllowsSelf() throws Exception {
        mockMvc.perform(get("/api/me/reader")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:reader"));
    }

    @Test
    void preAuthorizeDeniesAnotherUser() throws Exception {
        mockMvc.perform(get("/api/me/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void preAuthorizeAllowsAdminOverride() throws Exception {
        mockMvc.perform(get("/api/me/reader")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void preAuthorizeAdminRuleDeniesReader() throws Exception {
        mockMvc.perform(get("/api/admin/pre")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securedAnnotationDeniesReader() throws Exception {
        mockMvc.perform(get("/api/admin/secured")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securedAnnotationAllowsAdmin() throws Exception {
        mockMvc.perform(get("/api/admin/secured")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("secured-admin-ok"));
    }

    @Test
    void jsr250RolesAllowedAllowsManager() throws Exception {
        mockMvc.perform(get("/api/manager/jsr")
                .with(httpBasic("manager", "manager-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("jsr-manager-ok"));
    }

    @Test
    void jsr250RolesAllowedDeniesOtherRole() throws Exception {
        mockMvc.perform(get("/api/manager/jsr")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void denyAllRejectsEvenAdmin() throws Exception {
        mockMvc.perform(get("/api/denied")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postAuthorizeAllowsOwner() throws Exception {
        mockMvc.perform(get("/api/docs/doc-r")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("reader"));
    }

    @Test
    void postAuthorizeDeniesNonOwnerAfterRead() throws Exception {
        mockMvc.perform(get("/api/docs/doc-a")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postAuthorizeAllowsAdmin() throws Exception {
        mockMvc.perform(get("/api/docs/doc-r")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void postFilterRemovesOtherUsersDocuments() throws Exception {
        mockMvc.perform(get("/api/docs")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].owner").value("reader"));
    }

    @Test
    void postFilterAllowsAdminToSeeAllDocuments() throws Exception {
        mockMvc.perform(get("/api/docs")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)));
    }

    @Test
    void preFilterRemovesUnauthorizedNames() throws Exception {
        mockMvc.perform(get("/api/names")
                .param("name", "reader", "admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0]").value("reader"));
    }

    @Test
    void preFilterAllowsAdminToKeepAllNames() throws Exception {
        mockMvc.perform(get("/api/names")
                .param("name", "reader", "admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)));
    }
}
~~~

**Vì sao đây là test của các nhóm annotation chứ không chỉ HTTP layer?** HTTP policy chỉ đòi `authenticated()` cho tất cả endpoints protected trong `/api/**`. User reader **đã authenticated** nhưng bị 403 ở `@Secured`, `@RolesAllowed`, `@PreAuthorize` và `@PostAuthorize`. Admin bị từ chối ở `@DenyAll`. Như vậy các negative tests bắt được lỗi thiếu advisor tốt hơn việc chỉ test anonymous bị HTTP 401.

Một số nhóm chỉ có hiệu lực khi đủ điều kiện: `@PermitAll` cần JSR-250 enabled và HTTP cũng phải permit anonymous; `@PreFilter` yêu cầu input collection tương thích; `@PostFilter` trả list mutable để có thể lọc. Các tests chỉ mô tả hiệu năng/chức năng của demo; không thay thế review transaction/security policy sản phẩm.

### 9.8. Chạy ví dụ

Với Java 17 và Gradle tương thích:

~~~bash
gradle test
gradle bootRun
~~~

Nếu dự án có Gradle Wrapper, dùng:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows: `gradlew.bat test` và `gradlew.bat bootRun`. Không dùng `javac`/`java` đơn lẻ để chạy project Spring Boot khi thiếu classpath của dependencies. Các lệnh trên là hướng dẫn chạy, **không khẳng định Gradle đã chạy trong môi trường tạo bài viết**.

Ví dụ HTTP request khi ứng dụng lắng nghe localhost:8080:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/admin/secured
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin/secured
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/secured
curl -i -u manager:manager-pass \
  http://localhost:8080/api/manager/jsr
curl -i -u reader:reader-pass \
  http://localhost:8080/api/docs/doc-r
curl -i -u reader:reader-pass \
  http://localhost:8080/api/docs/doc-a
~~~

Trong demo, kỳ vọng: public 200; anonymous vào admin/secured thường 401; reader vào admin/secured 403; admin vào admin/secured 200; manager vào manager/jsr 200; reader đọc doc-r 200 nhưng doc-a 403.

**Chỉ dùng credentials mẫu cho localhost.** Trong production không để password trong shell history, không chạy HTTP Basic qua mạng không mã hóa, dùng HTTPS và identity provider phù hợp.

## 10. Bảng kết quả theo từng nhóm annotation

| Request / Principal | HTTP check | Method annotation | Kết quả điển hình |
| --- | --- | --- | --- |
| GET /api/public, anonymous | permitAll | `@PermitAll` | 200 |
| GET /api/admin/secured, anonymous | authenticated | Chưa tới method | 401 |
| GET /api/admin/secured, reader | authenticated | `@Secured("ROLE_ADMIN")` | 403 |
| GET /api/admin/secured, admin | authenticated | `@Secured("ROLE_ADMIN")` | 200 |
| GET /api/manager/jsr, manager | authenticated | `@RolesAllowed("MANAGER")` | 200 |
| GET /api/manager/jsr, reader | authenticated | `@RolesAllowed("MANAGER")` | 403 |
| GET /api/denied, admin | authenticated | `@DenyAll` | 403 |
| GET /api/me/reader, reader | authenticated | `@PreAuthorize` | 200 |
| GET /api/me/admin, reader | authenticated | `@PreAuthorize` | 403 |
| GET /api/docs/doc-r, reader | authenticated | `@PostAuthorize` | 200 |
| GET /api/docs/doc-a, reader | authenticated | `@PostAuthorize` | 403 |
| GET /api/docs, reader | authenticated | `@PostFilter` | 200, chỉ 1 document |
| GET /api/names, reader | authenticated | `@PreFilter` | 200, chỉ tên reader |

Bảng gắn với configuration và dữ liệu demo. Khi thay `AuthenticationEntryPoint`, form login, JWT resource server hoặc controller error handling, **HTTP status cụ thể có thể khác** nhưng điều cần được kiểm chứng vẫn là quyền có/không được cấp chính xác.

## 11. Điều gì xảy ra khi tắt từng nhóm?

Đây là cách tự phát hiện các annotation bị cấu hình “treo”.

### 11.1. Không bật @Secured

~~~java
@EnableMethodSecurity
~~~

Khi chỉ dùng dòng này, `@PreAuthorize`/`@PostAuthorize` vẫn được bật, nhưng `@Secured` không được bật mặc định. Nếu HTTP route chỉ yêu cầu authenticated và không có lớp bảo vệ khác, reader có thể đi qua một method chỉ gắn `@Secured("ROLE_ADMIN")`. **Đây là tình trạng nguy hiểm** vì source code khiến reviewer tưởng method đã protected.

### 11.2. Không bật JSR-250

~~~java
@EnableMethodSecurity(securedEnabled = true)
~~~

`@RolesAllowed`, `@PermitAll` và `@DenyAll` vẫn chưa được bật nếu thiếu `jsr250Enabled=true`. Đặc biệt, một method `@DenyAll` có thể không bị method-security advisor JSR-250 chặn như tưởng tượng.

### 11.3. Tắt prePostEnabled

~~~java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Khi đó không kỳ vọng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` chạy. Nếu codebase vẫn sử dụng các annotation đó, việc tắt nhóm **làm thay đổi security behavior** và phải được kiểm chứng bằng tests negative-cases.

### 11.4. Vì sao không nên thử cấu hình tắt nhóm ngay trên production?

Tắt annotation group có thể âm thầm mở quyền. Muốn học cơ chế, hãy dùng test fixture hoặc nhánh cấu hình sandbox riêng. Trong production, mọi thay đổi `@EnableMethodSecurity` flags phải được coi là **security policy migration**, có inventory annotation và tests chứng minh không tạo bypass.

## 12. So sánh @PreAuthorize với @Secured và @RolesAllowed

### 12.1. Cùng mục tiêu role-based

Ba cách gần tương đương về mục tiêu khi role-prefix mặc định là `ROLE_`:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void adminA() {}

@Secured("ROLE_ADMIN")
public void adminB() {}

@RolesAllowed("ADMIN")
public void adminC() {}
~~~

**Nhưng không tương đương về cơ chế kích hoạt:**

- `adminA` yêu cầu prePostEnabled.
- `adminB` yêu cầu securedEnabled.
- `adminC` yêu cầu jsr250Enabled.

Và chúng không hứa hoàn toàn đồng nhất nếu custom role hierarchy, role prefix, expression handler hoặc authorization manager khác được cấu hình. Với hệ thống lớn, hãy chọn convention chính, rồi kiểm thử authorities/role mapping thật.

### 12.2. Khi cần điều kiện động

Chỉ một role tĩnh thường không đủ:

~~~java
@PreAuthorize(
    "#p0 == authentication.name and hasAuthority('SCOPE_profile.write')")
public void updateProfile(String username, String value) {
    // ...
}
~~~

Đây là mảnh code minh họa, method body phải thực hiện business update với dữ liệu server-verified. `@PreAuthorize` cho phép phối hợp tham số, authorities, biểu thức boolean và gọi policy bean; `@Secured`/`@RolesAllowed` không cho cùng mức biểu đạt như SpEL.

Trong service thật, ownership thường cần DB query: có thể viết một bean `accessPolicy.canEdit(authentication, documentId)` và dùng expression tham chiếu bean, nhưng đừng viết policy cho phép dựa chỉ vào ownerId do client truyền. Hãy để policy bean dùng nguồn dữ liệu đáng tin và tránh side effects trong authorization.

### 12.3. Chọn ít annotation hơn thường dễ review hơn

Một codebase dùng cả `@Secured`, `@RolesAllowed` và `@PreAuthorize` trên cùng logic dễ tạo lệch policy khi refactor. Nếu không bị ràng buộc tương thích, chọn `@PreAuthorize` làm convention chính là lựa chọn phổ biến vì hỗ trợ biểu thức và được bật mặc định khi method security được bật. Những nhóm khác vẫn hữu ích khi tương thích legacy code, Jakarta annotations hoặc yêu cầu tổ chức.

## 13. Kích hoạt method security trong dự án đang có

### 13.1. Kiểm tra inventory annotations

Trước khi thay config, thống kê codebase thực sự dùng annotation nào:

- `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`.
- `@Secured`.
- `@RolesAllowed`, `@PermitAll`, `@DenyAll` từ `jakarta.annotation.security`.
- Custom meta-annotations hoặc custom AuthorizationManager/advisors.
- Rules nằm trên interface, class, method và khả năng interface/class proxy nhận được annotation.

Nếu nhóm nào đang dùng mà chưa được bật, đừng chỉ sửa config trong khi bỏ qua test access-denied.

### 13.2. Từ @EnableGlobalMethodSecurity sang @EnableMethodSecurity

Trong codebase Spring Security cũ có thể gặp:

~~~java
@EnableGlobalMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Đây là annotation **legacy**, không phải hướng cấu hình ưu tiên của Spring Security 6. Với nền tảng mới, dùng:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
~~~

Tuy tên flags tương tự, hạ tầng và extension points đã đổi theo hướng AuthorizationManager. Nếu code cũ custom `GlobalMethodSecurityConfiguration`, expression handler, permission evaluator hoặc metadata sources, **không đảm bảo chỉ đổi tên annotation là xong**. Hãy kiểm tra migration guide phù hợp phiên bản và chạy integration tests cho từng method policy.

### 13.3. Đừng bật method security bằng cách tạo object security thủ công

Không cần tự new `MethodSecurityInterceptor`, `AuthorizationManagerBeforeMethodInterceptor` hoặc custom AOP proxy cho use case bình thường. `@EnableMethodSecurity` đăng ký hạ tầng tương ứng. Chỉ mở rộng bằng custom advisors/managers khi có nhu cầu rõ và tests chứng minh thứ tự áp dụng.

### 13.4. Bật method security không làm mọi method tự động bị chặn

Nếu chỉ cấu hình `@EnableMethodSecurity`, framework **không tự yêu cầu admin cho mọi method**. Method không có annotation/advice áp dụng có thể vẫn được gọi, tùy HTTP rules và security layers khác. Vì vậy cần đặt method-level annotations ở đúng service boundaries và có default-deny/authorization chính sách ở web/domain layers.

## 14. Các lỗi phổ biến khi triển khai

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| @PreAuthorize không tác động | Chưa bật method security, method không qua proxy | Kiểm tra @EnableMethodSecurity, Spring bean và call graph |
| @Secured cho user thường đi qua | securedEnabled mặc định false | Bật securedEnabled và thêm negative test |
| @RolesAllowed không kiểm soát quyền | jsr250Enabled mặc định false hoặc package sai | Bật jsr250Enabled, dùng Jakarta import trong Boot 3 |
| @PermitAll nhưng HTTP vẫn 401 | HTTP filter chain yêu cầu authentication | Điều chỉnh HTTP policy có chủ đích, không bỏ toàn chain |
| @DenyAll không chặn admin | JSR-250 chưa bật hoặc call bypass proxy | Test enabled flag và proxy invocation |
| @PreAuthorize "#username" không tìm thấy biến | Parameter name metadata thiếu | Dùng #p0/#a0 hoặc -parameters rõ |
| @PreAuthorize deny user có role ADMIN | ROLE_ prefix hoặc authorities mapping sai | Kiểm tra Authentication.getAuthorities() an toàn |
| @PostAuthorize bị deny nhưng DB đã thay đổi | Method chạy trước post-check | Dùng pre-check trước side effects |
| @PostFilter làm request chậm | Load cả collection rồi mới lọc | Query theo owner/tenant ở DB, paging và policy layer |
| @PreFilter lỗi với immutable input | Advisor cần lọc collection | Dùng collection mutable phù hợp, test filterTarget |
| Gọi method annotated từ cùng class vẫn chạy | Self-invocation không qua proxy | Tách bean / bảo vệ entry point |
| Unit test new ProtectedService() bỏ qua annotation | Object ngoài Spring container | Integration test gọi injected Spring bean/proxy |
| Private/final method không bị intercept | Giới hạn proxy/AOP | Chuyển vào public proxied boundary; review Kotlin/final |
| Admin được phép qua URL nhưng service 403 | Method rule chặt hơn web rule | Đây có thể là hành vi đúng; xác minh cả hai lớp |
| Test @WithMockUser pass nhưng JWT thực vẫn lỗi | Test giả Authentication, bỏ qua decoder/authn | Thêm end-to-end auth tests |
| POST trả 403 trước khi gọi service | CSRF filter chặn | Tách CSRF test với method-security test |
| Custom annotation không hoạt động | Meta annotation/advisor chưa được nhận | Kiểm tra Spring Security version, target và proxy |
| Nhiều advisors cùng áp | Các annotation kết hợp gây conditions ngoài dự kiến | Dùng convention rõ và test kết hợp |
| Refactor method gọi nội bộ | Proxy boundary thay đổi | Regression tests từ controller/external bean |

### 14.1. Đừng tự dùng Authentication.getName() rồi cho rằng method security đã bật

Việc service tự đọc `SecurityContextHolder.getContext().getAuthentication()` và kiểm tra tên user **không giống** method-security advice được kích hoạt. Nó có thể là một business authorization check hợp lệ nếu làm cẩn thận, nhưng không chứng minh `@PreAuthorize` hoạt động. Muốn xác nhận advisor, cần negative tests cho annotation **trên Spring-managed service**.

### 14.2. Đừng dựa hoàn toàn vào @WithMockUser

`@WithMockUser` hữu ích để test service method authorization với một simulated Authentication; tuy nhiên nó **không xác minh form login, password encoder, JWT signature, opaque introspection hoặc HTTP filters**. Trong bài lab, MockMvc dùng `httpBasic()` để đi qua authentication và method-security chain; trong production thêm kiểm thử cho cơ chế xác thực thực tế.

### 14.3. Phân biệt annotation không thực thi và annotation bị deny

Nếu user nhận 403:

- Đã vào method security chưa?
- Annotation nào đang chặn? SpEL expression có đúng không?
- Authorities của user là gì?
- Method có chạy body chưa (phân biệt pre vs post)?
- HTTP layer hoặc CSRF có chặn trước không?

Nếu user **được phép** trái mong muốn:

- Annotation group có thực sự enabled không?
- Lời gọi có đi qua proxy không?
- Bean có được Spring quản lý không?
- Có self-invocation, final method, custom proxy or call trực tiếp qua constructor không?
- Method-level annotations có bị bypass bởi đường code khác không?
- Authentication/authority có bị cấp quyền quá rộng trước đó không?

**Một kết quả 200 không chứng minh method security được kích hoạt**, vì có thể service hoàn toàn không bị advisor chặn. Kết quả **403 trên user đã xác thực nhưng thiếu đúng quyền** mới là test phân biệt quan trọng.

## 15. Chiến lược kiểm thử ở nhiều tầng

### 15.1. Unit test policy

Khi business policy phức tạp, tách một component kiểm tra quyền với nguồn dữ liệu đáng tin để unit test logic: owner, tenant, scopes, account status. Test này chưa chứng minh annotation hay proxy đã áp dụng; nó chỉ chứng minh logic được gọi đúng khi có input.

### 15.2. Spring method-security integration test

Autowire **service bean thật từ Spring context**, gắn `@WithMockUser` cho các trường hợp allow/deny, và dùng `assertThrows(AccessDeniedException.class, ...)` cho negative cases. Cách này giúp chứng minh advisor intercept được calls từ test qua injected bean. Không tạo service bằng `new`.

Mảnh code minh họa:

~~~java
@Test
@WithMockUser(username = "reader", roles = "USER")
void readerCannotCallAdminService() {
    assertThrows(AccessDeniedException.class,
        () -> protectedOperations.adminSecured());
}
~~~

Cần import JUnit `assertThrows`, `AccessDeniedException` và `WithMockUser` cùng Spring test context; đây là **mảnh test**, không phải full test class. Không dùng `@WithMockUser(roles="ADMIN")` làm bằng chứng HTTP Basic/password được xác thực thật.

### 15.3. MockMvc controller-to-service integration

Như ví dụ mục 9, request đi qua HTTP Basic → controller → service proxy. Đây là lớp tốt để phát hiện:

- HTTP route quá rộng.
- Annotation group bị tắt.
- Service call graph không đi qua proxy.
- Role prefix/authority mismatch.
- Pre/post filter behavior.
- Trang hoặc endpoint public vẫn bị HTTP chặn.

### 15.4. End-to-end test với nguồn auth thực

Nếu production dùng form login/session, hãy test CSRF, session, remember-me/re-auth phù hợp. Nếu dùng JWT, test cả chữ ký, issuer, audience, expiration, authorities converter. Nếu dùng opaque access token, test introspection/invalid token/server failures. Method security **không thay thế** validation của credential đầu vào.

### 15.5. Negative-test matrix nên có

| Nhóm | Positive | Negative quan trọng |
| --- | --- | --- |
| @PreAuthorize | Đúng owner hoặc role | Đã authenticated nhưng sai owner/role |
| @PostAuthorize | Object của mình | Object thuộc người khác |
| @PreFilter | Danh sách được lọc đúng | Không lọc lọt phần tử người khác |
| @PostFilter | Danh sách chỉ phần được phép | Không trả list chưa lọc cho user |
| @Secured | ROLE_ADMIN | ROLE_USER nhận 403 |
| @RolesAllowed | ROLE_MANAGER | ROLE_USER/ROLE_ADMIN khác role nhận 403 |
| @PermitAll | Anonymous và HTTP permit | HTTP deny vẫn phải có quyền từ chối |
| @DenyAll | Không có positive | Admin vẫn bị từ chối |
| Proxy boundary | Controller gọi service bean | Self-call/new object không được dùng làm security guarantee |

## 16. Bài tập tự kiểm tra

1. Vì sao ứng dụng đã có SecurityFilterChain chưa chắc đã kích hoạt `@PreAuthorize` trên service?
2. Chỉ dùng `@EnableMethodSecurity`, annotation groups nào được bật mặc định và nhóm nào còn tắt?
3. Viết cấu hình bật cả `@Secured` và JSR-250 mà vẫn giữ pre/post annotations.
4. Trong Spring Boot 3, import đúng package nào cho `@RolesAllowed` và `@PermitAll`? Vì sao code `javax.annotation.security` cũ cần được review?
5. Một service chỉ gắn `@Secured("ROLE_ADMIN")`, nhưng config chỉ có `@EnableMethodSecurity`. Tình huống bypass nào có thể xảy ra?
6. `@PreAuthorize("hasRole('ADMIN')")` khác `@Secured("ROLE_ADMIN")` về syntax, ability to use SpEL và flag kích hoạt thế nào?
7. `@RolesAllowed("MANAGER")` thường tương ứng `ROLE_MANAGER` hay `ROLE_ADMIN`?
8. Tại sao một `@PermitAll` service không mở được HTTP endpoint nếu URL policy yêu cầu `hasRole('ADMIN')`?
9. Vì sao `@DenyAll` đáng được kiểm thử bằng user admin đã được xác thực thay vì chỉ anonymous?
10. Với một method `updateInvoice()` có side effect, dùng `@PostAuthorize` thay `@PreAuthorize` có nguy cơ gì?
11. `@PostFilter` trên 100.000 records có thể gây vấn đề gì về performance và data minimization?
12. Vì sao `@PreFilter` cần chú ý mutable input, `filterTarget` và loại collection?
13. Nếu expression dùng `#username` nhưng build thiếu `-parameters`, có thể gặp lỗi gì? Cách dùng `#p0` khác thế nào?
14. Khi method annotated được gọi từ một method khác **cùng class**, proxy mode mặc định có tự intercept không?
15. Tại sao `new ProtectedOperations()` trong unit test không chứng minh method security?
16. Mô tả ưu/nhược điểm giữa JDK dynamic proxy và class-based proxy đối với method interception.
17. Nếu một `final` method chứa `@PreAuthorize`, điều gì phải xem xét trước khi coi nó được bảo vệ bởi proxy?
18. Dùng MockMvc test chứng minh reader đã authenticated nhưng bị deny ở `@Secured` và `@RolesAllowed`.
19. Nếu thay `jsr250Enabled=true` thành false mà app vẫn compile, loại test nào sẽ phát hiện mất bảo vệ?
20. Với JWT scope `docs.read` được convert thành `SCOPE_docs.read`, dùng expression nào để kiểm tra đúng authority?
21. Tại sao hai annotations authorization khác nhóm trên cùng method không nhất thiết có semantics “annotation sau override annotation trước”?
22. Có nên chỉ gắn method security ở controller mà bỏ qua service được gọi từ scheduled job, messaging consumer hoặc nội bộ khác không?
23. Một `@PostAuthorize` từ chối quyền sau khi `@Transactional` service đã update DB; bạn cần kiểm chứng điều gì về thứ tự advisor và rollback?
24. Nếu bật `@EnableMethodSecurity` trong quá trình migrate khỏi `@EnableGlobalMethodSecurity`, những extension points và tests nào cần review?
25. Lập bảng kiểm tra cho service bảo vệ tài liệu theo owner/tenant: HTTP route, method annotation, persisted ownership, auth converter và tests negative.

## 17. Checklist trước production

- [ ] `@EnableMethodSecurity` được khai đúng trong Spring configuration.
- [ ] `prePostEnabled`, `securedEnabled`, `jsr250Enabled` phản ánh đúng annotations codebase đang dùng.
- [ ] Các JSR-250 annotations từ `jakarta.annotation.security` trong Spring Boot 3.
- [ ] Có tests đã authenticated nhưng sai role/scope/owner bị chặn (không chỉ anonymous 401).
- [ ] Mỗi method sensitive có boundary Spring-managed bean và lời gọi qua proxy.
- [ ] Đã rà soát self-invocation, private/final methods và bean tạo ngoài Spring.
- [ ] Business actions có side effects được kiểm tra **trước** khi chạy, không chỉ @PostAuthorize.
- [ ] Owner/tenant/resource authorization dựa trên dữ liệu đáng tin, không tin request params.
- [ ] @PostFilter không được dùng thay query filtering cho datasets lớn/nhạy cảm.
- [ ] @PreFilter xử lý collection/mutable input an toàn và có tests.
- [ ] Role prefix/authorities mapping rõ ràng giữa HTTP auth và method authorization.
- [ ] HTTP filter chain vẫn chặn đúng anonymous, CSRF và invalid credentials.
- [ ] @PermitAll trên method không được coi là bypass HTTP security.
- [ ] Các annotations ở interfaces/classes/overrides/meta-annotations đã được test qua proxy.
- [ ] Đã xem xét interactions với @Transactional, @Async, @Cacheable và exception handling.
- [ ] Nếu dùng nhiều nhóm annotation, không có rules chồng lấn tạo policy khó đoán.
- [ ] Có migration/rollback tests khi đổi Spring Security version và legacy method security config.
- [ ] Không ghi Authentication/credentials/token nhạy cảm vào logs khi debug.
- [ ] Security policy changes có code review và regression tests.
- [ ] Có test chặn nhầm quyền ở service được gọi từ job, message listener hoặc non-HTTP entry points.

## 18. Kết luận

`@EnableMethodSecurity` không phải một công tắc “bật hết mọi annotation”. Trong Spring Security 6.x, nó **bật nhóm pre/post theo mặc định**; `@Secured` yêu cầu `securedEnabled=true`, còn `@RolesAllowed`/`@PermitAll`/`@DenyAll` yêu cầu `jsr250Enabled=true`. Đó là ba nhóm riêng cần được kích hoạt có chủ đích và xác minh bằng tests.

Dù annotation group đã bật, **quy tắc chỉ bảo vệ những lời gọi được method-security advice thực sự intercept**, thường qua Spring AOP proxy. Vì vậy đừng chỉ kiểm tra source code có `@PreAuthorize` hay không; hãy kiểm tra đường gọi controller → service bean/proxy, kết quả 403 cho user thiếu quyền và behavior với self-invocation/side effects.

Công thức triển khai đáng nhớ: **bật đúng nhóm → gắn rule ở business boundary → tạo Authentication từ nguồn tin cậy → kiểm thử negative cases qua proxy → giữ HTTP authorization và method authorization như hai lớp phối hợp**. Khi làm đủ, method security trở thành lớp bảo vệ nghiệp vụ thực sự, thay vì một tập annotation chỉ có vẻ an toàn.
