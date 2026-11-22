# HttpSessionSecurityContextRepository và RequestAttributeSecurityContextRepository

## 1. Vì sao Spring Security phải lưu lại SecurityContext?

Trong ứng dụng Spring Security theo mô hình Servlet, kết quả xác thực người dùng thường được biểu diễn bởi một `Authentication` nằm trong `SecurityContext`. `SecurityContextHolder` giúp code trong quá trình xử lý hiện tại truy cập ngữ cảnh này. Nhưng HTTP là giao thức gồm **nhiều request tách biệt**: một kết quả đăng nhập ở request A không tự nhiên tồn tại trong request B nếu ứng dụng không có cơ chế lưu và khôi phục.

Spring Security dùng **`SecurityContextRepository`** để định nghĩa cách lấy và lưu `SecurityContext`. Hai triển khai có phạm vi sống khác nhau là:

- **`HttpSessionSecurityContextRepository`:** lưu `SecurityContext` trong `HttpSession`, nhờ đó request tiếp theo gửi cùng session có thể dùng lại kết quả xác thực.
- **`RequestAttributeSecurityContextRepository`:** lưu `SecurityContext` thành **attribute của chính ServletRequest** để nó có thể được khôi phục trong **cùng request** qua các dispatch type như `ERROR` hoặc `FORWARD`; dữ liệu **không tồn tại sang HTTP request mới**.
- **`DelegatingSecurityContextRepository`:** kết hợp nhiều repository. Trong cấu hình mặc định được Spring Security 6 mô tả, nó dùng cả request attribute và HTTP session để phục vụ hai nhu cầu trên.

**Không được đánh đồng** một biến `SecurityContextHolder` trên thread, một request attribute và một HTTP session. Chúng là ba nơi có vòng đời khác nhau; hiểu sự khác biệt này giúp giải quyết lỗi “đăng nhập xong nhưng request sau lại thành anonymous”, “trang lỗi không nhìn thấy người dùng” và “đã tắt tạo session nhưng ứng dụng vẫn có session”.

Bài học trình bày API, vòng đời, cách cấu hình trong Spring Security 6.5.x, cơ chế explicit save, ví dụ Java 17 có thể chạy với mock Servlet request, các tình huống test và giới hạn bảo mật.

## 2. Bản đồ các thành phần liên quan

```text
 HTTP request                          Spring Security filter chain
      |                                          |
      |                                          v
      |                              SecurityContextHolderFilter
      |                              nạp SecurityContext khi cần
      |                                          |
      |                          SecurityContextRepository.loadDeferredContext
      |                                          |
      |                       +------------------+-----------------+
      |                       |                                    |
      |                       v                                    v
      |         RequestAttributeSecurityContextRepository    HttpSessionSecurityContextRepository
      |         request.setAttribute(...)                     HttpSession.getAttribute(...)
      |         tồn tại trong ServletRequest                   có thể tồn tại qua requests
      |                       |                                    |
      |                       +------------------+-----------------+
      |                                          |
      |                                          v
      |                                 SecurityContextHolder
      |                                          |
      |                               Authentication & authorities
      |                                          |
      |                                     Authorization
      |                                          |
      |                         khi có auth mới cần được lưu:
      |                                          |
      |                          SecurityContextRepository.saveContext
      |                                          |
      v                                          v
 response/redirect                     request attr +/hoặc HTTP session
```

Những trách nhiệm cần tách rời:

| Thành phần | Chức năng | Không nên hiểu thành |
| --- | --- | --- |
| `SecurityContext` | Chứa `Authentication` đang được hệ thống tin cậy. | Database user hoặc kho password. |
| `SecurityContextHolder` | Cung cấp điểm truy cập ngữ cảnh hiện hành, thường gắn với thread qua strategy. | Nơi lưu trạng thái đăng nhập bền vững giữa hai HTTP request. |
| `SecurityContextRepository` | Hợp đồng đọc/lưu ngữ cảnh từ phương tiện phù hợp. | Tự xác minh username/password. |
| `HttpSessionSecurityContextRepository` | Kết nối security context với một HTTP session. | Tự động tạo session trong mọi request hoặc tự kiểm soát mọi cookie. |
| `RequestAttributeSecurityContextRepository` | Giữ context trong request attribute để có thể đọc ở một dispatch khác của cùng request. | Một cơ chế đăng nhập duy trì giữa nhiều requests. |
| `DelegatingSecurityContextRepository` | Gửi thao tác lưu đến các delegate và tìm context qua các delegate. | Cache phân tán hoặc hợp nhất nhiều danh tính khác nhau. |
| `AuthenticationManager`/provider | Xác minh credential và trả `Authentication` đã xác thực. | Kho lưu `SecurityContext`. |
| `SecurityFilterChain` | Tổ chức filter xử lý request, authentication, authorization và response. | Đồng nghĩa với HTTP session. |

Ví dụ: `DaoAuthenticationProvider` có thể xác thực password rất đúng, nhưng **custom login controller** quên gọi `saveContext(...)` thì lần gọi HTTP kế tiếp vẫn có thể không tìm được kết quả đăng nhập. Ngược lại, một request đã có session chứa context không cần so password lại **ở mọi request** chỉ để hiển thị principal.

## 3. Hợp đồng SecurityContextRepository trong Spring Security 6

Interface `org.springframework.security.web.context.SecurityContextRepository` có các API quan trọng:

```java
DeferredSecurityContext loadDeferredContext(
        HttpServletRequest request);

void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);

boolean containsContext(HttpServletRequest request);
```

Đây là chữ ký **minh họa theo API**, không phải một interface cần tự tạo. Các kiểu `HttpServletRequest` và `HttpServletResponse` nằm trong gói `jakarta.servlet.http` ở Spring Security 6.

### `loadDeferredContext(...)`: nạp khi thực sự cần

API này trả về một `DeferredSecurityContext`; security context có thể chỉ được truy cập từ repository khi code yêu cầu `get()`. Lợi ích là tránh truy cập session hoặc tạo object không cần thiết trong những request không đọc ngữ cảnh.

```java
DeferredSecurityContext deferred =
        repository.loadDeferredContext(request);
SecurityContext context = deferred.get();
Authentication auth = context.getAuthentication();
```

Đây là đoạn trích cần repository/request hợp lệ. Khi chưa có context lưu trữ, repository tạo/trả **một context rỗng**, không phải bắt buộc trả `null`. `deferred.isGenerated()` có thể cho biết nó được tạo mới thay vì đọc được một context có sẵn.

Không nhầm `loadDeferredContext` với câu lệnh “đăng nhập”. Đọc một context không đồng nghĩa user đã được xác thực; `context.getAuthentication()` có thể `null`, hoặc authentication hiện hữu có thể đại diện anonymous, tùy filter/cấu hình.

### `saveContext(...)`: thao tác lưu có chủ đích

```java
repository.saveContext(context, request, response);
```

Với repository session, kết quả có thể được ghi vào `HttpSession`; với repository request attribute, nó được gắn vào `ServletRequest`. Nếu dùng delegating, thao tác được chuyển đến nhiều delegate theo cấu hình.

**Lưu ý quan trọng từ Spring Security 6:** `SecurityContextHolderFilter` *chỉ nạp*, không tự động lưu mọi thay đổi vào repository ở cuối request. Code **tự xác thực** người dùng và muốn họ còn đăng nhập ở request tiếp theo cần thực hiện **explicit save** bằng repository thích hợp. Các filter đăng nhập chuẩn đã được thiết kế để xử lý việc này theo cấu hình của chúng; không vì thế mà custom controller được phép bỏ qua.

### `containsContext(...)` là một phép hỏi về lưu trữ

`containsContext(request)` cho biết repository hiện có một context cho request hay không. Nó **không tự chứng minh** credential mới được xác thực, account chưa bị khóa, session chưa hết hạn, hay user có quyền đối với mọi tài nguyên. Muốn ra quyết định authorization phải dùng ngữ cảnh và policy phù hợp.

### API cũ `loadContext(HttpRequestResponseHolder)`

Nhiều blog và project Spring Security 5 sử dụng:

```java
SecurityContext context =
        repository.loadContext(new HttpRequestResponseHolder(
                request, response));
```

Đây là **API cũ/deprecated** trong Spring Security 6.5.11. Với code mới, ưu tiên `loadDeferredContext(HttpServletRequest)` và `saveContext(...)`. Những wrapper response của đường cũ liên quan cách lưu ngầm khi response commit, nên không nên sao chép máy móc vào cấu hình explicit-save mới.

## 4. HttpSessionSecurityContextRepository: tồn tại giữa các request

`HttpSessionSecurityContextRepository` lưu security context trong một `HttpSession`. Khóa attribute mặc định là hằng:

```java
HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY
```

Giá trị khóa thường được biết đến là `"SPRING_SECURITY_CONTEXT"`. Một phiên Servlet khác với một HTTP request: nhiều request từ cùng browser có thể dùng lại session thông qua session ID/cookie, nếu container và ứng dụng có cấu hình phù hợp.

### 4.1. Khi đọc từ session

Quá trình thông dụng:

1. HTTP request tới ứng dụng, có thể mang cookie định danh session cũ.
2. Servlet container giải quyết cookie đó thành `HttpSession` hợp lệ, nếu có.
3. Repository đọc attribute chứa `SecurityContext` từ session.
4. Nếu attribute không tồn tại hoặc không phải SecurityContext hợp lệ, tạo context rỗng.
5. Context sẵn có có thể được gắn vào `SecurityContextHolder` bởi security filter cho request hiện hành.

**Đọc không bắt buộc tạo session.** Với cấu hình mặc định, repository dùng `getSession(false)` khi đọc; một guest request chưa có session không vì riêng thao tác này mà tạo session mới. Cần phân biệt việc **repository không tạo session khi đọc** với việc các thành phần khác như CSRF token repository, request cache, view layer hoặc application code **có thể** tạo session.

### 4.2. Khi lưu vào session

Trong Spring Security 6.5, `saveContext(...)` có các tối ưu/điều kiện để tránh tạo session không cần:

- Context rỗng không cần tạo session mới chỉ để lưu “chưa đăng nhập”.
- Anonymous authentication không nên được dùng để tạo một session chỉ vì nó xuất hiện trong holder.
- Với context đã xác thực và khác ngữ cảnh rỗng, repository có thể tạo session **nếu cấu hình cho phép**.
- Khi session đã tồn tại, repository có thể ghi context vào attribute của session đó.
- `setAllowSessionCreation(false)` ngăn **repository này tạo session mới**, nhưng **không** ngăn nó ghi vào một session đã tồn tại do thành phần khác tạo.

Nói cách khác, `HttpSessionSecurityContextRepository` là cơ chế lưu context **vào session khi có lý do**, không phải mệnh lệnh tạo session trên mọi request. Việc một session có được tạo cuối cùng còn phụ thuộc nhiều thành phần của filter chain và ứng dụng.

### 4.3. Các setter quan trọng

```java
HttpSessionSecurityContextRepository repo =
        new HttpSessionSecurityContextRepository();

repo.setAllowSessionCreation(false);
repo.setDisableUrlRewriting(true);
repo.setSpringSecurityContextKey(
        HttpSessionSecurityContextRepository
                .SPRING_SECURITY_CONTEXT_KEY);
```

Đoạn code có thể dùng trong một class đã import các kiểu cần thiết. Ý nghĩa:

| Setter | Ý nghĩa và giới hạn |
| --- | --- |
| `setAllowSessionCreation(false)` | Repository không tạo session mới chỉ để lưu; **vẫn có thể dùng session đã tồn tại**. |
| `setDisableUrlRewriting(true)` | Tránh thêm session ID vào URL khi response wrapper dùng cơ chế URL rewriting. |
| `setSpringSecurityContextKey(...)` | Đổi tên attribute chứa security context; chỉ làm khi mọi chỗ đọc/ghi thống nhất. |
| `setTrustResolver(...)` | Tùy biến cách nhận diện anonymous/remember-me cho quyết định lưu; không chỉnh nếu chưa có test bảo mật đầy đủ. |
| `setSecurityContextHolderStrategy(...)` | Đồng bộ với strategy `SecurityContextHolder` nếu ứng dụng dùng chiến lược context riêng. |

**Không dùng `setAllowSessionCreation(false)` như cách thay thế hoàn toàn cho `SessionCreationPolicy.STATELESS`.** Cờ này chỉ ảnh hưởng một repository; stateless authentication còn phụ thuộc policy filter chain, request cache, CSRF, authentication filter và các thành phần web khác.

### 4.4. Session không phải toàn bộ danh tính hay quyền vĩnh viễn

Một security context lưu trong session chứa một **ảnh chụp Authentication/authorities** ở thời điểm xác thực. Nếu admin thu hồi role trong DB, session cũ **không tự cập nhật** role chỉ vì request tiếp theo đọc lại context. Cần chính sách refresh/revalidation, invalidate sessions hoặc authorization dựa trên trạng thái mới nhất khi rủi ro yêu cầu.

Ở môi trường nhiều instance, `HttpSession` cần cơ chế session affinity hoặc shared session store phù hợp, ví dụ cấu hình Spring Session/Redis với serialization an toàn; `HttpSessionSecurityContextRepository` **không tự tạo một cơ sở dữ liệu session phân tán**. Không lưu JPA entity/proxy lười tải, credential raw hoặc graph dữ liệu nhạy cảm tùy tiện vào principal chỉ vì session có thể serialize.

## 5. RequestAttributeSecurityContextRepository: giới hạn trong một ServletRequest

`RequestAttributeSecurityContextRepository` lưu context qua `ServletRequest.setAttribute(...)`, thông qua một attribute name do repository quản lý. Nó có thể dựng bằng constructor mặc định hoặc một tên attribute tùy chỉnh:

```java
RequestAttributeSecurityContextRepository repo =
        new RequestAttributeSecurityContextRepository();

// Hoặc tên attribute chuyên biệt do ứng dụng kiểm soát:
RequestAttributeSecurityContextRepository named =
        new RequestAttributeSecurityContextRepository(
                "my.application.securityContext");
```

**Khác biệt cốt lõi:** request attribute không phải cookie, không phải session attribute và không có tác dụng kéo dài login sang request HTTP tiếp theo. Mỗi request mới có tập attributes riêng; browser gửi cookie session cũ **không** làm một request attribute ở request trước xuất hiện trở lại.

### 5.1. Tại sao cần repository này khi đã có SecurityContextHolder?

Trong ứng dụng Servlet, một request có thể đi qua nhiều **dispatch type**, ví dụ:

- `REQUEST`: tiếp nhận request ban đầu.
- `FORWARD`: forward tới resource/view khác.
- `ERROR`: container thực hiện error dispatch khi xử lý lỗi.
- Một số tình huống `ASYNC`: xử lý bất đồng bộ theo vòng đời Servlet.

Ở một số container, `SecurityContextHolder` có thể đã được clear trước khi bắt đầu một lần `ERROR` dispatch. Nếu chỉ dựa vào ThreadLocal hiện tại, error page không biết user nào vừa gặp lỗi, nên không thể hiển thị hoặc dùng principal như dự kiến.

**RequestAttributeSecurityContextRepository** cho phép đặt ngữ cảnh vào request attribute; khi cùng ServletRequest được dispatch lại và filter chain phù hợp đọc repository, context có thể được khôi phục.

```text
REQUEST /documents/42
   |
   +--> authentication/filter xây SecurityContext cho "lan"
   |
   +--> requestRepo.saveContext(context, request, response)
   |
   +--> controller ném exception
   |
   +--> SecurityContextHolder của dispatch trước được clear
   |
   +--> ERROR dispatch /error  (cùng ServletRequest/attributes)
             |
             +--> requestRepo.loadDeferredContext(request)
             |
             +--> có thể lấy context của "lan" để xử lý error view
```

**Không có bảo đảm** rằng mọi Servlet container, cấu hình filter dispatcher types và security policy sẽ chạy đúng y như sơ đồ ở mọi ứng dụng. Repository tạo cơ chế lưu trữ trong request, nhưng ứng dụng vẫn cần đăng ký filter cho dispatcher phù hợp và quyết định quyền truy cập trang lỗi/forward.

### 5.2. Phạm vi và kỳ vọng đúng

| Tình huống | RequestAttributeSecurityContextRepository |
| --- | --- |
| Cùng request, code khác đọc lại context đã lưu | Có, nếu cùng request attribute còn tồn tại. |
| `ERROR` dispatch của cùng ServletRequest | Có thể khôi phục context khi filter/dispatch được cấu hình phù hợp. |
| `FORWARD` trong cùng request | Có thể khôi phục qua repository nếu cần. |
| Request tiếp theo từ cùng browser | **Không**: request attribute mới không có context cũ. |
| Request tiếp theo có cùng HTTP session | **Không tự dùng session**. |
| Ứng dụng restart | Không: request đã kết thúc, attribute cũng không còn. |
| Stateless API | Có thể hữu ích cho dispatch nội bộ nhưng không là persistence giữa requests. |

Đừng cố sửa lỗi “login request sau bị anonymous” bằng cách thay repository session bằng **chỉ request attribute**. Đó là giải pháp ngược mục tiêu: kho request attribute cố ý **không** duy trì trạng thái qua request mới.

### 5.3. Không tự gán attribute key bằng một string đoán mò

Request attribute được repository quản lý. Thay vì tự gọi:

```java
request.setAttribute("SPRING_SECURITY_CONTEXT", context);
```

hãy gọi:

```java
requestAttributeRepository.saveContext(context, request, response);
```

Chuỗi `"SPRING_SECURITY_CONTEXT"` thường là **key trong HttpSessionSecurityContextRepository**; không được mặc định nó cũng là default request attribute name. Dùng API đúng để tránh lệch tên và điều kiện lưu giữa các phiên bản.

## 6. So sánh trực tiếp hai repository

| Đặc tính | HttpSessionSecurityContextRepository | RequestAttributeSecurityContextRepository |
| --- | --- | --- |
| Nơi lưu | `HttpSession` attribute | `ServletRequest` attribute |
| Tồn tại qua HTTP request mới | **Có**, nếu cùng session hợp lệ và context đã lưu | **Không** |
| Hỗ trợ ERROR/FORWARD dispatch cùng request | Có thể tùy việc session được tạo/sẵn có và filter config; không phải mục tiêu chính | **Mục tiêu thiết kế chính** |
| Cần session cookie | Muốn duy trì giữa requests thì thường cần session ID/cookie hợp lệ | Không |
| Có thể tạo HttpSession | Có, khi save context cần lưu và allowSessionCreation=true | Không chỉ vì lưu request attribute |
| Tồn tại khi response đã commit | Session cần xử lý thời điểm save/cookie/response đúng | Request attribute không dựa vào cookie/response commit cho mục tiêu cùng request |
| Tính bền sau server restart | Phụ thuộc session infrastructure | Không |
| Thường dùng | Login dựa vào server-side session | Giữ context qua dispatch nội bộ, kể cả trang lỗi |
| Rủi ro nhầm lẫn | Session fixation, stale authorities, session replication, serialization | Tưởng là cơ chế login dài hạn, quên filter cho ERROR dispatch |

**Không có lựa chọn nào tự động “mạnh hơn” về bảo mật cho mọi hệ thống.** Sử dụng repository nào phụ thuộc mô hình authentication (session-backed hay per-request), tính sẵn sàng và yêu cầu xử lý servlet dispatch.

## 7. DelegatingSecurityContextRepository: kết hợp hai phạm vi

Tài liệu Spring Security 6 mô tả default repository là một **`DelegatingSecurityContextRepository`** với hai thành phần:

```java
SecurityContextRepository repo =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
```

Khi gọi `saveContext`, repository tổng chuyển thao tác lưu tới các delegate. Khi đọc, nó tìm context từ các delegate theo thứ tự cấu hình và dùng context có sẵn phù hợp. Với thứ tự trên:

1. Cùng request vừa tạo authentication: request attribute giữ ngữ cảnh thuận tiện cho dispatcher.
2. Request HTTP kế tiếp từ cùng session: request attribute mới rỗng, session repo có thể cung cấp context đã lưu ở request đăng nhập.
3. Nếu một delegate không có context, không đồng nghĩa toàn bộ yêu cầu không có context: repository khác vẫn có thể trả kết quả.

Một sơ đồ hai request:

```text
POST /login (request A)
   |
   +-- saveContext(authenticated "lan")
   |          |
   |          +--> request A attribute = context("lan")
   |          +--> HttpSession S1       = context("lan")
   |
   +-- response Set-Cookie: JSESSIONID=... (do Servlet container nếu cần)

GET /private (request B, cùng session S1)
   |
   +-- request B attribute: chưa có
   +-- HttpSession S1:       có context("lan")
   |
   +-- DelegatingSecurityContextRepository nạp context("lan")
```

**Quan trọng:** khả năng gửi/nhận session cookie phụ thuộc container, security config, session management và HTTP response. Chỉ nhìn thao tác lưu repository chưa thể khẳng định browser nhất định đã nhận cookie hoặc session fixation protection đã chạy.

### Vì sao request repo thường đứng trước session repo?

Request attribute được ưu tiên cho **ngữ cảnh thuộc dispatch hiện tại**, sau đó session repo bổ sung khả năng vượt qua HTTP request. Nếu code đã lưu ngữ cảnh mới trong request (ví dụ authentication thay đổi ở request hiện tại), việc ưu tiên request giúp các dispatch tiếp theo không vô tình rơi lại một trạng thái session cũ. Tuy nhiên kết quả cụ thể vẫn phải dựa vào contract và kiểm thử implementation, nhất là nếu ứng dụng tùy biến nhiều delegate.

### Cấu hình SecurityFilterChain

Đoạn sau là **trích đoạn trong class `@Configuration`**, giả sử đã có dependency Spring Security Servlet:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    SecurityContextRepository repository =
            new DelegatingSecurityContextRepository(
                    new RequestAttributeSecurityContextRepository(),
                    new HttpSessionSecurityContextRepository());

    http
        .securityContext(security -> security
            .securityContextRepository(repository)
            .requireExplicitSave(true))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

Cần import các loại `Bean`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và repository tương ứng. Đoạn này **chưa chạy độc lập**: còn cần `@SpringBootApplication`, nguồn user/AuthenticationManager, controller và security policy phù hợp. Spring Security 6 đã có cấu hình repository kết hợp mặc định; tự khai báo như trên chủ yếu hữu ích khi bạn cần thay đổi, minh họa hoặc kiểm soát chính xác một filter chain.

**Không áp dụng y nguyên `anyRequest().authenticated()` cho các endpoint `/error`, health, static assets hoặc API public mà chưa đánh giá các dispatcher type và quyền truy cập mong muốn.** Cấu hình sản phẩm cần phân biệt các đường truy cập và loại dispatch.

## 8. Java 17 runnable demo: request attribute, session và delegating

Ví dụ sau sử dụng **Spring Security Web 6.5.11**, **Spring Framework 6.2.12 test mocks**, Java 17+ và Gradle. Chương trình console gọi trực tiếp các repository bằng `MockHttpServletRequest`/`MockHttpServletResponse`, nên **không cần web server, DB hoặc controller**. Nó chứng minh chính xác phạm vi lưu trữ của từng repository.

Demo **không xác thực mật khẩu**. `Authentication` được tạo sẵn với `UsernamePasswordAuthenticationToken.authenticated(...)` chỉ để tập trung vào repository API. Trong ứng dụng thật, chỉ provider/AuthenticationManager đáng tin cậy mới được quyết định một identity đã xác thực; **không lấy username từ HTTP request rồi gọi factory authenticated để tự đăng nhập**.

### 8.1. Cấu trúc dự án

```text
security-context-repository-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── RepositoryScopeDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'security-context-repository-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.RepositoryScopeDemo'
}
```

Spring Security Web tự khai báo các dependency transitive phù hợp cho core/context; `spring-test` cung cấp Servlet mocks. Các version ở đây là một **tổ hợp minh họa đã chọn** để đọc API cụ thể; trong Spring Boot project thực nên để dependency management/BOM của Boot cấp tập phiên bản tương thích, không tự khóa từng thư viện theo bài demo.

### 8.2. File `src/main/java/demo/RepositoryScopeDemo.java`

```java
package demo;

import jakarta.servlet.http.HttpSession;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

public final class RepositoryScopeDemo {

    private static SecurityContext userContext(String username) {
        // CHỈ dùng trong demo: không tự tạo authenticated token
        // từ dữ liệu HTTP chưa được AuthenticationManager kiểm chứng.
        Authentication authenticated =
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        null,
                        AuthorityUtils.createAuthorityList("ROLE_READER"));

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        return context;
    }

    private static String username(SecurityContext context) {
        return context.getAuthentication() == null
                ? "(none)"
                : context.getAuthentication().getName();
    }

    public static void main(String[] args) {

        // A. Request attribute: chỉ giữ context trên cùng request object.
        RequestAttributeSecurityContextRepository requestRepo =
                new RequestAttributeSecurityContextRepository();

        MockHttpServletRequest requestA = new MockHttpServletRequest();
        MockHttpServletResponse responseA = new MockHttpServletResponse();

        System.out.println("request.before="
                + requestRepo.containsContext(requestA));

        requestRepo.saveContext(userContext("lan"), requestA, responseA);
        SecurityContextHolder.clearContext();

        System.out.println("request.saved="
                + requestRepo.containsContext(requestA));
        System.out.println("request.sameRequestUser="
                + username(requestRepo.loadDeferredContext(requestA).get()));
        System.out.println("request.createdSession="
                + (requestA.getSession(false) != null));

        MockHttpServletRequest requestB = new MockHttpServletRequest();
        System.out.println("request.nextRequestHasContext="
                + requestRepo.containsContext(requestB));

        // B. HttpSession: không tự tạo session khi chỉ load.
        HttpSessionSecurityContextRepository sessionRepo =
                new HttpSessionSecurityContextRepository();

        MockHttpServletRequest readOnly = new MockHttpServletRequest();
        sessionRepo.loadDeferredContext(readOnly).get();

        System.out.println("session.loadCreatedSession="
                + (readOnly.getSession(false) != null));

        MockHttpServletRequest loginRequest = new MockHttpServletRequest();
        MockHttpServletResponse loginResponse =
                new MockHttpServletResponse();

        sessionRepo.saveContext(userContext("lan"),
                loginRequest, loginResponse);

        HttpSession session = loginRequest.getSession(false);
        System.out.println("session.createdAfterSave=" + (session != null));

        MockHttpServletRequest nextRequest = new MockHttpServletRequest();
        nextRequest.setSession(session);

        System.out.println("session.nextRequestUser="
                + username(sessionRepo.loadDeferredContext(nextRequest).get()));

        // C. Không cho repository tạo session; request không có session
        // sẽ không thể giữ Authentication bằng HttpSession repo.
        HttpSessionSecurityContextRepository noCreate =
                new HttpSessionSecurityContextRepository();
        noCreate.setAllowSessionCreation(false);

        MockHttpServletRequest noSessionRequest =
                new MockHttpServletRequest();
        noCreate.saveContext(userContext("lan"), noSessionRequest,
                new MockHttpServletResponse());

        System.out.println("session.noCreateFlagHonored="
                + (noSessionRequest.getSession(false) == null));

        // D. Delegating repository: lưu request attr và session.
        SecurityContextRepository both =
                new DelegatingSecurityContextRepository(
                        new RequestAttributeSecurityContextRepository(),
                        new HttpSessionSecurityContextRepository());

        MockHttpServletRequest current = new MockHttpServletRequest();
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        both.saveContext(userContext("mai"), current, response);

        System.out.println("both.currentRequestHasContext="
                + both.containsContext(current));

        MockHttpServletRequest later = new MockHttpServletRequest();
        later.setSession(current.getSession(false));

        System.out.println("both.nextRequestUser="
                + username(both.loadDeferredContext(later).get()));

        MockHttpServletRequest unrelated = new MockHttpServletRequest();
        System.out.println("both.unrelatedRequestHasContext="
                + both.containsContext(unrelated));

        // E. Null repo: hoàn toàn không lưu SecurityContext.
        SecurityContextRepository none = new NullSecurityContextRepository();
        MockHttpServletRequest noStore = new MockHttpServletRequest();
        none.saveContext(userContext("lan"), noStore,
                new MockHttpServletResponse());
        System.out.println("null.repoHasContext="
                + none.containsContext(noStore));

        SecurityContextHolder.clearContext();
    }
}
```

### 8.3. Chạy và stdout dự kiến

Với JDK 17+ và Gradle/Gradle Wrapper hỗ trợ Java 17, từ thư mục dự án:

```bash
gradle run --quiet
```

Các dòng do **chương trình** in ra, không tính log của Gradle và thư viện:

```text
request.before=false
request.saved=true
request.sameRequestUser=lan
request.createdSession=false
request.nextRequestHasContext=false
session.loadCreatedSession=false
session.createdAfterSave=true
session.nextRequestUser=lan
session.noCreateFlagHonored=true
both.currentRequestHasContext=true
both.nextRequestUser=mai
both.unrelatedRequestHasContext=false
null.repoHasContext=false
```

### 8.4. Giải thích các nhóm đầu ra

**Nhóm request:** `saveContext(...)` ghi context vào request A. Đọc lại cùng request vẫn thấy `lan` dù `SecurityContextHolder.clearContext()` đã được gọi; đó là khác biệt giữa context trong ThreadLocal và context lưu trong request attribute. Request B là object mới, không có attribute từ A, nên `containsContext` trả false. Việc lưu request attribute **không tạo HttpSession**.

**Nhóm session:** `loadDeferredContext(...).get()` trên request chưa có session không tự tạo session. Sau `saveContext` với authenticated `lan`, session được tạo theo `allowSessionCreation=true`. Khi request khác sử dụng cùng `HttpSession`, repository đọc lại context đó và có principal `lan`. Một trình duyệt thật sẽ cần mang session ID hợp lệ qua request, còn demo chuyển thẳng `HttpSession` giữa hai mock request để mô phỏng việc container giải quyết cookie.

**Nhóm no-create:** `setAllowSessionCreation(false)` ngăn repository tạo session mới. Nó **không** nói rằng mọi thành phần Servlet khác bị cấm tạo session, và nếu có một session tồn tại sẵn thì repo vẫn có thể dùng nó.

**Nhóm delegating:** một lần `saveContext` ghi vào request attribute và session. Request tiếp theo dùng lại session vẫn có `mai`, trong khi một request hoàn toàn không liên quan không có context. Đây là lý do hai repository thường được đặt cùng nhau.

**Nhóm null:** `NullSecurityContextRepository` bỏ qua việc lưu; thường phù hợp cho một số luồng xác thực stateless, nhưng không tự quyết định toàn bộ `SessionCreationPolicy` hoặc hành vi của mọi filter khác.

**Giới hạn:** demo chỉ gọi repository trực tiếp, không kiểm tra đăng nhập bằng password, phiên HTTP thực, redirect response, session fixation defense, `ERROR` dispatch của container, CSRF hoặc authorization. Để kiểm thử toàn bộ filter chain, hãy dùng integration test và cấu hình HTTP thật (mục 12).

## 9. SecurityContextHolderFilter và “explicit save” trong Spring Security 6

Đây là phần quan trọng nhất khi tự xây login.

### 9.1. Trước đây và hiện nay

Trong nhiều cấu hình Spring Security 5, `SecurityContextPersistenceFilter` đọc context lúc bắt đầu request và thực hiện ghi lưu khi cần lúc request/response hoàn tất. Cơ chế này khá phức tạp vì filter phải phát hiện thay đổi và lưu trước khi HTTP response commit.

Trong Spring Security 6, cấu hình mặc định dựa trên **`SecurityContextHolderFilter`**, filter chịu trách nhiệm **nạp**, còn code phát sinh authentication mới phải **lưu context rõ ràng** khi mong muốn persistence.

```text
SecurityContextHolderFilter
  |
  +--> repository.loadDeferredContext(request)
  +--> cung cấp context cho SecurityContextHolder
  |
  +--> filter/controller code
  |      |
  |      +--> AuthenticationManager.authenticate(...)
  |      +--> tạo SecurityContext mới
  |      +--> SecurityContextHolder.setContext(context)
  |      +--> repository.saveContext(context, request, response)  <-- QUAN TRỌNG
  |
  +--> khi request/dispatch kết thúc, holder được dọn theo vòng đời filter
```

**`SecurityContextHolder.setContext(context)` không tự đảm bảo lưu vào session cho request sau.** Đây là nguyên nhân phổ biến của lỗi custom login “POST /login OK, GET /me lại anonymous”.

### 9.2. Mẫu custom login đúng ranh giới

Phần sau là **trích đoạn service/controller**, không phải một controller đầy đủ có CSRF/session-strategy/rate-limiting. Nó minh họa chính xác thứ tự **authenticate → context mới → set → save**.

```java
public void finishLogin(
        String username,
        String rawPassword,
        HttpServletRequest request,
        HttpServletResponse response) {

    Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    username, rawPassword);

    Authentication verified =
            authenticationManager.authenticate(input);

    SecurityContext context = SecurityContextHolder.createEmptyContext();
    context.setAuthentication(verified);

    SecurityContextHolder.setContext(context);
    securityContextRepository.saveContext(context, request, response);
}
```

Giả định `authenticationManager` và `securityContextRepository` đã được inject từ cấu hình tin cậy. Chỉ gọi mã này **sau** khi xác thực thành công; không tự tạo token authenticated từ username do client gửi.

**Cảnh báo production:** tự viết login endpoint còn cần áp dụng `SessionAuthenticationStrategy` (chẳng hạn chống session fixation), CSRF khi có session/cookie, failure handling, bảo vệ credential trong request/log, giới hạn đăng nhập và response phù hợp. Thường nên dùng các authentication filter chuẩn hoặc triển khai một cơ chế custom được kiểm thử đầy đủ thay vì sao chép riêng bốn dòng set/save.

### 9.3. Vì sao phải save trước khi response commit?

Sau khi response đã commit, ứng dụng có thể không còn cơ hội gửi cookie chứa session ID mới hoặc đổi header cần thiết. Nếu code tạo context mới nhưng chỉ cố lưu sau `sendRedirect(...)` hoặc sau khi body đã flush, request tiếp theo có thể đến **trước khi session được ghi hợp lệ** hoặc cookie không được gửi.

Mẫu nguy hiểm:

```java
// Không nên để save quá muộn:
response.sendRedirect("/home");
securityContextRepository.saveContext(context, request, response);
```

Mẫu mục tiêu:

```java
securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/home");
```

Hai đoạn là minh họa về thứ tự, không phải hoàn chỉnh cho transaction, session fixation hay exception handling. Khi dùng filter chuẩn, nên để filter quản lý việc save/redirect theo cơ chế được hỗ trợ.

### 9.4. Đừng chạy cả hai context filters

Tài liệu Spring Security 6 khuyến nghị một ứng dụng chỉ dùng **một trong hai** `SecurityContextHolderFilter` hoặc `SecurityContextPersistenceFilter`, không dùng đồng thời. Tắt/bật `requireExplicitSave` để “vá nhanh” mà không hiểu flow có thể gây save dư, khó đoán thời điểm session được cập nhật và tăng rủi ro khi response commit.

## 10. SessionCreationPolicy không đồng nghĩa một repository

Trong `HttpSecurity.sessionManagement(...)`, các chính sách thường gặp:

| Policy | Ý nghĩa chính | Điều cần lưu ý |
| --- | --- | --- |
| `ALWAYS` | Spring Security chủ động tạo session. | Không nên dùng chỉ vì muốn giữ context nếu mặc định đã đủ. |
| `IF_REQUIRED` | Chỉ tạo session khi cần. | Thường phù hợp login session-backed. |
| `NEVER` | Spring Security không tạo session mới nhưng có thể dùng session đã có. | Không đồng nghĩa hoàn toàn stateless; thành phần khác vẫn có thể tạo session. |
| `STATELESS` | Spring Security không tạo hoặc dùng HttpSession để lấy SecurityContext cho mục tiêu xác thực stateless. | Các filter/integration khác vẫn phải được kiểm tra, và request attribute có thể có vai trò trong dispatch. |

**Phân biệt kỹ:**

- `setAllowSessionCreation(false)` là thuộc tính của **một HttpSessionSecurityContextRepository instance**.
- `SessionCreationPolicy.STATELESS` là **một lựa chọn của security configuration** tác động tới cơ chế session management và các repository/filter có liên quan.
- `NullSecurityContextRepository` là implementation **không lưu**; dùng nó một mình không khiến các controller hoặc các thư viện khác bị cấm tạo session.
- `RequestAttributeSecurityContextRepository` có thể vẫn giúp lưu context trong một dispatch hiện hành ngay cả khi **không** muốn persistence sang request tiếp theo.

**Không xây API token/JWT giả stateless nhưng lại vô tình đặt authentication vào HttpSession** vì một filter custom sử dụng session repository. Ngược lại, **không chuyển toàn bộ ứng dụng form login sang Null repo** rồi ngạc nhiên vì login không duy trì ở request mới.

### Cấu hình minh họa cho API stateless

```java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
```

Đây là **đoạn minh họa**, không phải template production đầy đủ: cần xác định loại API, CSRF, authentication mechanism, CORS, các path và error handlers. HTTP Basic gửi credentials trên mỗi request nên không tự đòi một session; với bearer token/JWT, cách xác thực và filter khác. Việc không thấy session trong một test không chứng minh mọi endpoint trong sản phẩm tuyệt đối không tạo session.

## 11. ERROR/FORWARD dispatch: lợi ích thực tế và điều cần cấu hình

Một số lỗi chỉ xuất hiện khi controller ném exception hoặc container forward request tới trang lỗi:

```text
GET /invoice/42
  |
  +-- security filter nạp context user "lan"
  +-- controller throw exception
  +-- holder có thể được clear khi dispatch trước kết thúc
  +-- container dispatch /error trong cùng ServletRequest
  +-- page cần current principal
```

Nếu chỉ dựa vào ThreadLocal, context đã clear có thể khiến error page hiển thị anonymous. `RequestAttributeSecurityContextRepository` lưu security context ngay trên request; khi filter ở dispatcher tiếp theo nạp từ repository, nó có thể khôi phục ngữ cảnh.

Tuy nhiên cần phân biệt:

1. **Lưu ngữ cảnh:** `RequestAttributeSecurityContextRepository.saveContext(...)` đã được gọi khi cần. Nếu chưa lưu attribute, không có gì để phục hồi.
2. **Chạy filter:** `springSecurityFilterChain` cần được đăng ký cho các dispatcher types mong muốn. Một số cấu hình Boot/Servlet container khác nhau về mặc định; phải kiểm tra thật.
3. **Authorization cho trang lỗi:** `/error` và dispatcher type `ERROR` có thể chịu quy tắc authorization riêng; nếu rule quá chặt, request lỗi có thể bị chặn lần hai.
4. **Ngữ cảnh nào được hiển thị:** error page chỉ nên xem các thông tin principal được phép lộ, không dump `Authentication` hoặc session ra client.
5. **ServletRequest có thật sự là cùng request:** request attribute không tồn tại qua một HTTP request mới, kể cả cùng URL hoặc cùng cookie.

Một chính sách minh họa có thể cho phép xử lý error dispatch:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    .anyRequest().authenticated())
```

Đoạn này là **trích đoạn DSL**, cần import `jakarta.servlet.DispatcherType` và nối vào cấu hình HTTP thật. **`permitAll` cho ERROR dispatch không đồng nghĩa bạn có thể bỏ kiểm soát dữ liệu**: trang lỗi phải bảo vệ nội dung nhạy cảm và chỉ hiển thị dữ liệu theo chính sách đã xác định.

### Async và ThreadLocal là vấn đề khác

`SecurityContextHolder` theo default strategy dùng ThreadLocal; một tác vụ `@Async` hoặc thread do ứng dụng tự mở **không tự nhận context giống thread web ban đầu**. `RequestAttributeSecurityContextRepository` giữ context trên request object nhưng không tự truyền ThreadLocal sang mọi thread. Nếu cần context trong async task, dùng cơ chế propagation phù hợp như `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` hoặc integration hỗ trợ của Spring Security; bảo đảm không giữ context của request cũ ngoài phạm vi cho phép.

## 12. Kiểm thử hai vòng đời một cách tách biệt

### 12.1. Unit/integration test ở cấp repository

Các test trực tiếp dùng `MockHttpServletRequest` nên kiểm chứng:

| Trường hợp | Repository | Kỳ vọng |
| --- | --- | --- |
| Chưa save | RequestAttribute | `containsContext(request) == false`. |
| Đã save trên request A | RequestAttribute | Nạp trên A thấy principal đã lưu. |
| Request B là object mới | RequestAttribute | Không thấy context của A. |
| Đọc từ request chưa có session | HttpSession | Không tự tạo session chỉ vì load context. |
| Save authenticated context | HttpSession | Có thể tạo session khi `allowSessionCreation=true`. |
| Request B dùng cùng session | HttpSession | Đọc lại authentication đã lưu. |
| Không có session + allowSessionCreation=false | HttpSession | Repository không tạo session mới. |
| Đã có session + allowSessionCreation=false | HttpSession | Vẫn có thể lưu vào session hiện tại. |
| Save vào delegating | Request + Session | Cả hai delegate nhận context theo thiết kế. |
| Request mới có session nhưng không có attribute | Delegating | Lấy context từ session delegate. |
| Request mới không có session | Delegating | Không tự có authentication cũ. |
| Save vào Null repository | Null | Không có persistence của context. |

### 12.2. Kiểm thử Servlet dispatch thật

Mocked direct call **không đủ** để khẳng định ứng dụng vận hành giống nhau trên mọi container. Khi cần kiểm tra `ERROR`/`FORWARD`:

- Dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` hoặc integration setup thật có filter chain.
- Tạo endpoint giả lập lỗi sau authentication.
- Xác nhận request attribute được lưu trong cùng request trước khi error dispatch, theo cơ chế đăng nhập/filter đã chọn.
- Kiểm tra controller/error handler nhìn thấy principal đúng khi dispatcher type là `ERROR`.
- Kiểm tra rule authorization cho error page và không lộ thông tin nhạy cảm.
- So sánh hành vi khi repository là request-only, session-only và delegating.
- Thử user chưa đăng nhập: trang lỗi công khai theo policy, không có principal giả.
- Nếu nhiều filter chains, xác minh repository đúng chain đang xử lý URL.

**Không dùng riêng `@WithMockUser` để kết luận login persistence giữa requests hoạt động.** Mock user thường thiết lập security context cho test mà không thực sự gọi authentication manager, tạo session cookie hay lưu repository. Nó có ích cho authorization test nhưng không chứng minh đường login thực và persistence.

### 12.3. Test với session thật

Đối với ứng dụng session-backed có form login:

1. Request đầu chưa đăng nhập truy cập trang bảo vệ; bị chuyển/đưa tới login theo policy.
2. Client gửi password hợp lệ và CSRF token phù hợp.
3. Framework xử lý authentication, session fixation protection và lưu context trước redirect.
4. Request tiếp theo gửi cookie session mới; đọc được principal và authorities.
5. Request không có cookie hoặc đã logout nhận unauthenticated/anonymous behavior.
6. Sau session expiry/invalidate, context cũ không còn được phục hồi.
7. Nếu scale nhiều node, thử session store/replication và serialization.
8. Nếu admin khóa account, kiểm tra chiến lược invalidation hoặc revalidation, không mặc nhiên cho rằng session tự phản ánh DB.

**Chú ý:** assert HTTP 302/401/403 cụ thể phụ thuộc cơ chế form login/Basic và exception handling; đừng chỉ test các repository rồi tự suy ra status HTTP.

## 13. Phối hợp logout, session fixation và cookie

`HttpSessionSecurityContextRepository` **không phải bộ phận duy nhất** đảm nhiệm các khía cạnh này. Khi dùng session-backed authentication, cấu hình tổng thể phải có:

- **Session fixation protection:** sau login thành công, container/framework thường đổi session ID theo chiến lược phù hợp. Custom login không được bỏ qua `SessionAuthenticationStrategy` chỉ vì đã gọi `saveContext`.
- **Cookie bảo mật:** `HttpOnly`, `Secure` khi dùng HTTPS, `SameSite` phù hợp, cookie scope và TTL theo yêu cầu; cấu hình ở servlet container/proxy/session store.
- **CSRF defense:** form login và các request thay đổi trạng thái dựa trên cookie/session cần chống CSRF; `SecurityContextRepository` không thay thế CSRF protection.
- **Logout:** làm mất hiệu lực hoặc cập nhật đúng session và context theo cấu hình; không chỉ xóa `SecurityContextHolder` trong thread rồi coi session cũ đã bị thu hồi.
- **Thời gian sống session:** invalidation, inactivity timeout và chính sách kiểm soát đăng nhập đồng thời nếu cần.
- **URL session ID:** hạn chế `;jsessionid` trong URL để giảm rủi ro lộ ID qua log, referrer và lịch sử duyệt; dùng cấu hình servlet và `setDisableUrlRewriting` khi phù hợp.

### Vì sao clear ThreadLocal chưa đủ logout?

Một controller chỉ gọi:

```java
SecurityContextHolder.clearContext();
```

sẽ xóa context hiện hành của thread. **Nếu `HttpSession` vẫn chứa security context đã xác thực**, request sau cùng session vẫn có thể nạp lại. Cơ chế logout chuẩn của Spring Security phải xử lý việc xóa/invalidate session, context, remember-me và các cookie liên quan theo policy.

Với delegating repository, logout/custom clear còn cần đánh giá việc request attribute đã lưu ở dispatch hiện tại. Không được lưu một context cũ sau khi đã logout rồi mong nó không được khôi phục. Tốt nhất là để logout handlers được framework hỗ trợ thực hiện cleanup, sau đó test cả **cùng request** và **request kế tiếp**.

## 14. Các bẫy cấu hình thường gặp

1. **“`SecurityContextHolder` là storage giữa các request.”** Sai: ThreadLocal/strategy gắn với ngữ cảnh hiện hành; persistence cần repository.
2. **“`RequestAttributeSecurityContextRepository` giữ login đến hôm sau.”** Sai: chỉ trong cùng ServletRequest.
3. **“`HttpSessionSecurityContextRepository` tạo session ngay khi load.”** Mặc định không cần tạo session chỉ để đọc.
4. **“`setAllowSessionCreation(false)` khiến ứng dụng hoàn toàn stateless.”** Sai: repository vẫn dùng session sẵn có; các thành phần khác có thể tạo session.
5. **“Lưu vào request attribute tự lưu sang session.”** Không, trừ khi bạn dùng delegating hoặc chủ động lưu vào session repo.
6. **“Lưu vào session chắc chắn khôi phục được ở ERROR dispatch mọi trường hợp.”** Không phải mọi container/filter setup đều giữ holder; request repo là phần bổ sung cho dispatch.
7. **“Spring Security 6 tự lưu bất kỳ thay đổi nào vào holder.”** Với `SecurityContextHolderFilter`, phải explicit save nếu cần persistence; filter đăng nhập chuẩn có cơ chế riêng.
8. **“`containsContext=true` nghĩa user hiện tại luôn còn quyền.”** Không; có thể là snapshot cũ, cần policy revalidation.
9. **“Đã xác thực trong custom controller thì không cần `saveContext`.”** Sai nếu muốn session-backed login sang request kế.
10. **“Đổi `setSpringSecurityContextKey` không cần phối hợp.”** Nếu nơi đọc dùng key cũ, session sẽ trông như chưa có context.
11. **“Dùng `NullSecurityContextRepository` luôn đồng nghĩa cookie không tồn tại.”** Không: ứng dụng/container khác có thể tạo cookie/session.
12. **“Stateful login cứ copy ví dụ authenticated token.”** Không: token tin cậy phải đến từ AuthenticationManager/provider, không từ raw username client.
13. **“Request attribute tồn tại trong tác vụ background chạy ngày mai.”** Không, và ThreadLocal security context không tự truyền vào mọi worker thread.
14. **“Session context là entity Hibernate sống.”** Principal có thể được serialize và không có transaction; tránh giữ ORM proxy/lazy association.
15. **“Thay roles trong DB là session tự đổi.”** Không; cần refresh hoặc revoke.
16. **“Quên thay session ID sau login không sao vì repository đã save.”** Session fixation defense là trách nhiệm riêng và rất quan trọng.
17. **“Save sau redirect đã commit cũng luôn thành công.”** Không; session cookie/header có thể không gửi được nữa.
18. **“Đăng ký hai context filters cùng lúc an toàn hơn.”** Spring Security 6 khuyến nghị chỉ dùng một trong HolderFilter/PersistenceFilter.
19. **“Có delegating tức là nhiều phiên đăng nhập được merge quyền.”** Delegating chọn nơi lưu/đọc context, không hợp nhất authorities của các identities.
20. **“Dùng request repo thay session repo sẽ tăng bảo mật mặc định.”** Nó thay đổi semantics; yêu cầu session-backed sẽ mất.
21. **“Chỉ test `@WithMockUser` là đủ xác minh persistence.”** Không thử request cookie/repository real login.
22. **“Cookie session thuộc trách nhiệm SecurityContextRepository toàn bộ.”** Việc sinh/giải mã cookie ID chủ yếu do Servlet container/session infrastructure.
23. **“Session backend phân tán được tạo tự động bởi repository.”** Không; cần hạ tầng và cấu hình hỗ trợ.
24. **“Trạng thái anonymous phải lưu xuống session cho mọi guest.”** Repository session mặc định có tối ưu tránh lưu context rỗng/anonymous không cần thiết.
25. **“Nếu trang /error bị từ chối thì hãy tắt toàn bộ authorization.”** Cần phân quyền dispatcher/error page hợp lý, không mở dữ liệu khác.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Hai repository này khác nhau nhất ở phạm vi lưu như thế nào?

**Đáp án:** `HttpSessionSecurityContextRepository` dùng `HttpSession` và có thể khôi phục qua các HTTP requests chia sẻ session. `RequestAttributeSecurityContextRepository` lưu vào attribute của một ServletRequest, hữu ích giữa các dispatch trong request đó nhưng không tồn tại qua request mới.

**Câu 2.** Vì sao request repo hữu ích cho `ERROR` dispatch?

**Đáp án:** Servlet container có thể thực hiện error dispatch khi `SecurityContextHolder` đã bị clear từ dispatch trước; request attribute vẫn có thể tồn tại trên cùng ServletRequest, cho filter/repository đọc lại context.

**Câu 3.** `SecurityContextHolderFilter` có tự lưu context sau khi custom controller gọi `setContext` không?

**Đáp án:** Không. Với explicit save, custom authentication mechanism cần gọi `SecurityContextRepository.saveContext(context, request, response)` nếu muốn persistence giữa requests.

**Câu 4.** Một guest request đọc `HttpSessionSecurityContextRepository.loadDeferredContext(...).get()`. Có chắc session mới được tạo?

**Đáp án:** Không. Repository có thể trả context rỗng mà không tạo session khi chỉ đọc.

**Câu 5.** `setAllowSessionCreation(false)` có khiến repository ngừng đọc/ghi session đã tồn tại không?

**Đáp án:** Không. Nó ngăn repository này tạo session mới; session đã có vẫn có thể được sử dụng.

**Câu 6.** Dùng riêng request repo cho form login session-backed thì điều gì xảy ra ở request kế?

**Đáp án:** Attribute của request đăng nhập không tồn tại trên request mới; authentication không tự được khôi phục. Cần repository session hoặc một cơ chế persistence khác phù hợp.

**Câu 7.** Tại sao thường dùng DelegatingSecurityContextRepository?

**Đáp án:** Nó kết hợp request attribute cho cùng ServletRequest/dispatch và HttpSession để giữ login qua request mới, đáp ứng hai nhu cầu khác nhau.

**Câu 8.** Sau logout, chỉ gọi `SecurityContextHolder.clearContext()` có đủ không?

**Đáp án:** Không nếu session còn chứa authentication; request mới có thể nạp lại context. Phải xử lý session/repository/logout handlers theo chính sách.

**Câu 9.** Nếu admin thu hồi `ROLE_ADMIN` trong DB, user còn session có bị mất quyền ngay không?

**Đáp án:** Không được giả định. Session thường chứa Authentication snapshot; cần chiến lược revalidation, invalidation hoặc authorization dựa dữ liệu hiện tại.

**Câu 10.** Một custom controller đã gọi `saveContext` nhưng vẫn không đăng nhập được ở request kế. Cần kiểm tra gì?

**Đáp án:** Repository được dùng có thật sự là session/delegating không; save có trước response commit không; session đã tạo hợp lệ chưa; cookie/session ID có được gửi và quay lại không; filter chain có dùng cùng repository/key không; session fixation/CSRF/session store có xử lý đúng không.

**Câu 11.** Trong API stateless, `NullSecurityContextRepository` có nghĩa gì?

**Đáp án:** Bản thân repository không lưu context. Nó không tự cấm toàn ứng dụng tạo session hoặc bảo đảm mọi filter đều không dùng session.

**Câu 12.** Vì sao không dùng trực tiếp `UsernamePasswordAuthenticationToken.authenticated(...)` với username từ body login để tạo context?

**Đáp án:** Đó là một token được đánh dấu đã xác thực nhưng chưa hề chứng minh credential. Dữ liệu client phải được kiểm chứng qua AuthenticationManager/provider; trong demo factory đó chỉ mô phỏng một authentication đã đáng tin để khảo sát repository.

**Câu 13.** `loadContext(HttpRequestResponseHolder)` và `loadDeferredContext(request)` khác nhau thế nào trong API 6.5?

**Đáp án:** `loadContext` là API cũ/deprecated gắn với request/response wrapper cho cơ chế lưu ngầm, còn `loadDeferredContext` là giao diện ưu tiên để nạp context khi cần theo mô hình hiện đại.

**Câu 14.** Thay `SessionCreationPolicy.IF_REQUIRED` bằng `STATELESS` có bảo đảm một API vẫn giữ login session như trước không?

**Đáp án:** Không. Stateless thay đổi mục tiêu sử dụng session để lưu authentication; muốn login bằng session phải chọn policy/repository tương ứng và test.

## 16. Tài liệu chính thức

- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository`, `NullSecurityContextRepository` và sơ đồ filter/save.
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): explicit save, custom authentication, session management và `SecurityContextHolderFilter`.
- [Spring Security 6.5.11 — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html): session key, điều kiện tạo session và các setters.
- [Spring Security 6.5.11 — RequestAttributeSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/RequestAttributeSecurityContextRepository.html): request-scoped persistence qua dispatch, constructor và `loadDeferredContext`.
- [Spring Security 6.5.11 — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html): repository kết hợp, save/contains/deferred load.
- [Spring Security 6.5.11 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): hợp đồng đọc/lưu context.
- [Spring Framework 6.2 — MockHttpServletRequest API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/mock/web/MockHttpServletRequest.html): mock Servlet request và `setSession(HttpSession)` dùng trong ví dụ.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): quan hệ giữa `AuthenticationManager`, provider và `SecurityContextHolder`.

**Kết luận:** `HttpSessionSecurityContextRepository` giữ `SecurityContext` **qua nhiều HTTP requests chia sẻ session**; `RequestAttributeSecurityContextRepository` giữ ngữ cảnh **trong một ServletRequest, kể cả các dispatch nội bộ**. `DelegatingSecurityContextRepository` kết hợp hai phạm vi và là mặc định phổ biến trong Spring Security 6. Khi tự tạo authentication, luôn tách rõ **xác minh credential → tạo context → lưu đúng repository**, hiểu explicit save và thời điểm response commit, rồi kiểm thử cả request hiện tại, request kế tiếp và `ERROR` dispatch thực tế.