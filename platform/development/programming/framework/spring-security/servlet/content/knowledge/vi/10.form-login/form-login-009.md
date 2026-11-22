# SessionAuthenticationStrategy và lưu SecurityContext sau xác thực (Spring Security Servlet)

Khi người dùng nhập đúng username/password trong ứng dụng Spring MVC, ta mới giải quyết được **một phần** của việc đăng nhập. Hệ thống còn phải quyết định xử lý **HTTP session** thế nào, hạn chế nguy cơ session fixation, có cho phép nhiều phiên đồng thời không, và quan trọng nhất: **SecurityContext chứa Authentication đã xác thực có được lưu để request sau nhận ra người dùng hay không?**

Trong Spring Security Servlet, hai trách nhiệm này có liên hệ nhưng **không phải một**:

- **`SessionAuthenticationStrategy`**: thực thi các chính sách gắn với **sự kiện xác thực thành công**, chẳng hạn đổi session ID để chống session fixation, kiểm soát số session, ghi nhận phiên hoặc làm mới trạng thái CSRF theo cấu hình.
- **`SecurityContextRepository`**: nạp và lưu **`SecurityContext`**. Với form login sử dụng session, repository cho phép một request sau dùng cùng session khôi phục `Authentication` đã được xác minh.

`SecurityContextHolder` chỉ giữ context cho quá trình xử lý hiện tại; `HttpSession` giữ state có thể vượt qua nhiều request; còn `SessionAuthenticationStrategy` chủ yếu xử lý **chính sách khi phiên đăng nhập được hình thành**. Phân biệt đúng giúp tránh lỗi “đăng nhập thành công nhưng refresh lại mất login”, tình huống đổi session ID không đúng và cấu hình stateless bị pha với form login.

Bài này tập trung vào **Spring Security Servlet / Spring MVC**, điển hình Spring Security 6.x và Java 17+. Mốc Spring Boot 3.3.5 trong ví dụ chỉ nhằm cố định một bộ dependency dễ hiểu; không có nghĩa đây là bản mới nhất hoặc còn được hỗ trợ tại thời điểm đọc.

## 1. Năm khái niệm cần nhận diện trước khi cấu hình

**Authentication.** Kết quả của việc xác minh danh tính, chứa principal và authorities. Trước khi xác thực, `UsernamePasswordAuthenticationToken` chỉ đại diện dữ liệu username/password chưa đáng tin. Sau khi `AuthenticationManager` trả về kết quả thành công, hệ thống mới có thể xem đó là Authentication đã xác thực.

**SecurityContext.** Đối tượng chứa `Authentication` cho quá trình xử lý bảo mật. Một context rỗng tồn tại không đồng nghĩa đã có người dùng đăng nhập.

**SecurityContextHolder.** API cung cấp quyền truy cập context hiện tại, thường sử dụng chiến lược dựa vào thread trong Servlet. Nó được web security filter thiết lập/dọn dẹp theo request, **không tự là nơi lưu đăng nhập cho nhiều request**.

**SecurityContextRepository.** Hợp đồng nạp và lưu context qua các ranh giới được xác định. Trong web login có session, repository phù hợp có thể dùng `HttpSessionSecurityContextRepository`; Spring Security còn có `RequestAttributeSecurityContextRepository` và `DelegatingSecurityContextRepository`.

**SessionAuthenticationStrategy.** Hợp đồng nhận kết quả xác thực thành công cùng `HttpServletRequest` và `HttpServletResponse` để thực thi chính sách session. Nó **không thay thế** `PasswordEncoder`, `AuthenticationManager` hay `SecurityContextRepository`.

Một phương thức chính của strategy:

```java
void onAuthentication(
    Authentication authentication,
    HttpServletRequest request,
    HttpServletResponse response
) throws SessionAuthenticationException;
```

Đây là chữ ký khái niệm của API; không phải file Java độc lập. Việc thực thi xảy ra sau khi có Authentication thành công từ manager, theo luồng filter được cấu hình. Strategy có thể làm phát sinh `SessionAuthenticationException`, khiến phiên đăng nhập không được chấp nhận theo chính sách dù credential đúng.

## 2. Toàn cảnh form login: chiến lược session nằm ở đâu?

Đối với `UsernamePasswordAuthenticationFilter` (kế thừa `AbstractAuthenticationProcessingFilter`), luồng xử lý điển hình là:

```text
Browser
  |
  | POST /login (username, password, CSRF token theo cấu hình)
  v
CsrfFilter và các security filter đi trước
  |
UsernamePasswordAuthenticationFilter
  |
  +-- requiresAuthentication(request)?
        |
        +-- NO  -> tiếp tục filter chain
        |
        +-- YES -> attemptAuthentication(...)
                     |
                     v
                AuthenticationManager
                     |
                AuthenticationProvider
                     |
          Authentication thành công / exception / null
                     |
                     +-- SUCCESS -------------------------+
                     |                                   |
                     |  SessionAuthenticationStrategy    |
                     |  .onAuthentication(...)          |
                     |                                   |
                     |  successfulAuthentication(...)   |
                     |    -> SecurityContextHolder      |
                     |    -> SecurityContextRepository  |
                     |       .saveContext(...)           |
                     |    -> remember-me/event           |
                     |    -> SuccessHandler/redirect     |
                     |                                   |
                     +-- EXCEPTION -> FailureHandler     |
                     +-- NULL -> chờ bước khác           |
```

Với filter form login chuẩn, **session strategy thường chạy trước `successfulAuthentication(...)`**, và lời gọi lưu context diễn ra trong quá trình xử lý nhánh thành công theo repository của filter. Điều này có ý nghĩa vì đổi session ID, kiểm tra giới hạn số phiên hoặc đăng ký phiên thường phải hoàn tất trước khi người dùng được chuyển sang trang sau đăng nhập.

Các luồng xác thực khác (HTTP Basic, OAuth2, Resource Server, custom filter) có cơ chế và điểm gọi khác nhau. Không giả định mọi authentication filter đều kế thừa `AbstractAuthenticationProcessingFilter` hay tự động gọi cùng strategy. Bài đang nói về **form login trên Servlet**.

### Ba thời điểm khác nhau

| Thời điểm | Đối tượng chính | Câu hỏi được giải quyết |
|---|---|---|
| Kiểm tra credential | `AuthenticationManager` / provider | Username/password có hợp lệ không? |
| Xử lý chính sách phiên | `SessionAuthenticationStrategy` | Session hiện tại có được dùng/đổi ID/đăng ký/giới hạn không? |
| Lưu trạng thái xác thực | `SecurityContextRepository` | Context sẽ được nạp ở request tiếp theo bằng cách nào? |

**Một session ID mới không có nghĩa SecurityContext đã được lưu.** Và **`SecurityContextHolder.setContext(...)` không có nghĩa strategy đã thực hiện chống fixation**. Hai nhiệm vụ cần cùng đúng, nhưng không suy ra nhiệm vụ này tự hoàn tất nhiệm vụ kia.

## 3. Vì sao session fixation là vấn đề lớn sau đăng nhập?

**Session fixation** là tình huống kẻ tấn công cố khiến nạn nhân sử dụng một session identifier đã biết trước, rồi tận dụng việc nạn nhân đăng nhập thành công trong session đó. Nếu session ID không được thay đổi khi nâng trạng thái từ anonymous lên authenticated, identifier cũ có thể vẫn đại diện cho phiên đã đăng nhập.

Các bước tấn công ở mức khái niệm:

1. Một session identifier tồn tại trước khi nạn nhân đăng nhập.
2. Kẻ tấn công tìm cách khiến trình duyệt nạn nhân sử dụng identifier đó.
3. Nạn nhân hoàn tất đăng nhập.
4. Nếu session ID giữ nguyên trong phiên đã xác thực và kẻ tấn công biết ID, rủi ro chiếm phiên tăng lên.

**Phòng vệ quan trọng:** thay session identifier tại thời điểm xác thực thành công và áp dụng biện pháp quản lý session phù hợp. Cookie `Secure`/`HttpOnly`, TLS, cấu hình reverse proxy, SameSite, timeout và logout cũng là các lớp bảo vệ độc lập.

Spring Security Servlet cung cấp các strategy liên quan:

- **`ChangeSessionIdAuthenticationStrategy`:** dùng API Servlet để đổi session ID của session đang có, thường là lựa chọn thích hợp với Servlet container hiện đại (Servlet 3.1+) và là hành vi mặc định phổ biến của cấu hình hỗ trợ session fixation hiện nay.
- **`SessionFixationProtectionStrategy`:** hỗ trợ những cách xử lý chuyển sang session mới và chuyển/cân nhắc session attributes; đây là cơ chế hữu ích để hiểu khi duy trì ứng dụng hoặc container cũ.
- **`NullAuthenticatedSessionStrategy`:** không thực hiện thay đổi session khi onAuthentication. Không phải lựa chọn an toàn thay thế mặc định cho một website dựa vào session chỉ để tránh lỗi tích hợp.

Trong cấu hình Spring Security, những lựa chọn như `sessionFixation().changeSessionId()`, `migrateSession()`, `newSession()` và `none()` có hậu quả khác nhau. Không coi việc “không đổi session ID” là tối ưu hiệu năng. Khi cần giữ các thuộc tính HTTP session, hãy kiểm thử chính xác các thuộc tính nào tồn tại trước/sau login; thay session có thể tác động vào các đối tượng được bind và lifecycle hooks của Servlet.

### Đổi session ID không đồng nghĩa tạo credential mới

Credential vẫn do AuthenticationManager xác minh. Strategy chỉ cập nhật cách quản lý **phiên** đã được cấp. Sau khi đổi session ID, browser phải nhận và gửi lại session identifier hợp lệ ở request tiếp theo; nếu proxy, cookie path/domain hoặc client không giữ cookie, ứng dụng vẫn có thể trở lại anonymous dù xác thực thành công.

**Không log hoặc gửi session ID lên URL.** Session ID có giá trị như một credential trong khi session còn hiệu lực; đưa nó vào logs/analytics/URL có thể tạo đường rò rỉ mới.

## 4. Chọn SessionAuthenticationStrategy phù hợp

| Implementation | Trách nhiệm | Ghi chú thực hành |
|---|---|---|
| `ChangeSessionIdAuthenticationStrategy` | Đổi session ID sau xác thực | Thường dùng cùng Servlet session fixation protection trên container mới |
| `SessionFixationProtectionStrategy` | Thay session và xử lý migration thuộc tính theo cấu hình | Cần chú ý session-scoped beans, attribute migration và các callback |
| `ConcurrentSessionControlAuthenticationStrategy` | Kiểm tra số phiên đồng thời theo user | Có thể từ chối login mới hoặc đánh dấu phiên cũ hết hiệu lực tùy policy |
| `RegisterSessionAuthenticationStrategy` | Ghi nhận session sau xác thực vào `SessionRegistry` | Hữu ích trong thiết kế concurrent session management |
| `CompositeSessionAuthenticationStrategy` | Gọi một chuỗi strategy theo thứ tự | Trật tự rất quan trọng, không hoán đổi tùy ý |
| `CsrfAuthenticationStrategy` | Làm mới trạng thái CSRF token trong lúc xác thực | Liên quan bảo vệ CSRF, không phải cơ chế giữ Authentication lâu dài |
| `NullAuthenticatedSessionStrategy` | Không thay đổi session | Chỉ cân nhắc khi thiết kế session không cần cơ chế này và đã có phòng vệ thích hợp |

Trong một cấu hình kiểm soát concurrency, tổ hợp có thể đặt bước **kiểm tra số phiên trước**, bước **đổi/thiết lập phiên**, rồi bước **đăng ký phiên**. Điều này tránh ghi một phiên mới vào registry khi policy không chấp nhận đăng nhập. Spring Security có thể dựng strategy tổng hợp từ DSL, vì vậy **đừng tự tạo composite chỉ để thay thế mặc định** nếu các lựa chọn cấu hình đã đáp ứng yêu cầu.

### Concurrent sessions không chỉ là một con số

Với rule “mỗi user tối đa một session”, phải định nghĩa rõ:

- Login mới có được phép và làm session cũ hết hạn hay không?
- Hay login mới bị từ chối khi session cũ còn hiệu lực?
- Session sau logout, timeout hoặc server restart được hủy/giải phóng khỏi registry thế nào?
- Ở môi trường nhiều instance, registry và kho session có đồng bộ/nhất quán không?

`SessionRegistryImpl` trong memory có đặc tính khác với session registry/lưu session phân tán; không giả định hai máy chủ độc lập cùng biết toàn bộ session của một user. Thử giới hạn phiên bằng browser riêng hoặc nhiều client có cookie tách biệt; một tab mới trong **cùng browser session** thường không phải một phiên độc lập.

## 5. SecurityContext được lưu ở đâu sau khi strategy chạy?

Spring Security sử dụng `SecurityContextRepository` để nạp/lưu context. Trong hệ Spring Security 6, cấu hình servlet phổ biến dùng `DelegatingSecurityContextRepository` gồm:

```java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
```

Đây là **đoạn Java minh họa**, cần dependency và import thích hợp; không phải một ứng dụng độc lập.

Hai delegate giải quyết hai phạm vi:

- **`RequestAttributeSecurityContextRepository`:** lưu context trong `HttpServletRequest` hiện tại. Hữu ích qua các lần dispatch (ví dụ `ERROR`) thuộc cùng request nếu security chain xử lý phù hợp.
- **`HttpSessionSecurityContextRepository`:** lưu context trong HTTP session để request tiếp theo có cùng session hợp lệ có thể nạp lại.
- **`DelegatingSecurityContextRepository`:** kết hợp khả năng nạp và lưu của các delegate. Nó không phải cơ chế lưu phân tán, không tự cấp session vô thời hạn.

`SecurityContextHolder` lưu thông tin trong quá trình xử lý hiện tại rồi thường được filter dọn ở ranh giới request. Khi thấy holder trống sau response, đó **không tự chứng minh** login đã mất. Cần xét repository và request mới có nạp lại được context hay không.

### Ví dụ timeline sau form login

```text
REQUEST #1: POST /login
  - AuthenticationManager xác minh đúng username/password
  - SessionAuthenticationStrategy áp dụng fixation / concurrency policy
  - SecurityContext được tạo và gắn Authentication
  - SecurityContextRepository.saveContext(context, request, response)
  - SuccessHandler trả redirect (vd. /account)
  - Response có thể gửi Set-Cookie session ID

REQUEST #2: GET /account, client gửi cùng session cookie hợp lệ
  - SecurityContextHolderFilter / repository nạp context
  - Authorization nhận Authentication đã xác thực
  - Controller xử lý request
  - Kết thúc request: holder được dọn theo lifecycle

REQUEST #3: cùng URL nhưng không có session cookie
  - Không tìm thấy context trong session cũ
  - Ứng dụng có thể yêu cầu login lại
```

**Kết quả 302 từ POST login là chưa đủ để xác minh lưu context.** Phải thực hiện tiếp một request bảo vệ với session vừa tạo và kiểm tra Authentication thực tế.

### HTTP session không đồng nghĩa cookie chứa mật khẩu

Session cookie thường mang **session identifier**, không chứa raw password hoặc toàn bộ SecurityContext mặc định. Context được giữ phía server trong session repository. Nếu có giải pháp lưu session riêng, cần kiểm tra cách serialization, persistence, session expiration và chính sách cluster thay vì dựa vào nhận định chung rằng “cookie đã an toàn”.

## 6. Điểm chuyển quan trọng ở Spring Security 6: explicit save

Ở nhiều cấu hình Spring Security 6, `SecurityContextHolderFilter` chịu trách nhiệm nạp hoặc cung cấp cách nạp context vào holder, rồi dọn khi request kết thúc. **Filter này không tự động lưu mọi thay đổi trong holder vào repository** như cách mà ví dụ cũ với `SecurityContextPersistenceFilter` có thể khiến người đọc kỳ vọng.

Với một custom login flow, đoạn sau **chưa đủ** để bảo đảm trạng thái đăng nhập ở request tiếp theo:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
```

Trong đó `authenticated` phải là kết quả đã được manager/provider xác minh. Đoạn code là **mảnh bên trong handler có biến hợp lệ**, không tự xác thực credential hay đăng ký filter.

Nếu custom flow cần lưu state, phải bảo đảm một lời gọi phù hợp với repository:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Tuy nhiên đây **không phải toàn bộ flow đăng nhập**: còn có session strategy, session fixation protection, remember-me, failure handling, CSRF, response và nhiều trách nhiệm tùy thiết kế. Nếu dùng `UsernamePasswordAuthenticationFilter` của Spring Security, **để chính filter/framework xử lý** phần chuẩn đó thay vì tự lặp lại lời gọi `saveContext` trong controller hoặc success handler.

**Đặc biệt:** `SessionAuthenticationStrategy.onAuthentication(...)` không phải API lưu SecurityContext. Có thể strategy đã thay session ID thành công nhưng custom code quên save context; browser nhận session mới song vẫn không có Authentication ở request sau. Ngược lại, ghi context vào session mà bỏ session fixation policy cũng tạo rủi ro riêng.

### Lưu trước khi response được commit

Khi tạo HTTP session và cần gửi cookie cho client, `saveContext` phải xảy ra trước khi response commit hoặc redirect khi flow yêu cầu. Sau khi response đã được gửi, server có thể không thêm được Set-Cookie hoặc thay đổi metadata đúng cách. Vì vậy thay đổi thứ tự “redirect trước, save sau” trong custom filter là nguồn lỗi khó quan sát.

## 7. Form login có cần tự cấu hình bean SessionAuthenticationStrategy không?

**Thông thường không.** DSL `formLogin(...)` kết hợp `sessionManagement(...)`, security context repository và các bộ lọc chuẩn đã được Spring Security điều phối. Tự tạo `SessionAuthenticationStrategy` bean chưa chắc khiến mọi authentication filter tự dùng bean đó; các filter được cấu hình bằng DSL có thể nhận strategy từ các shared objects/Configurer tương ứng.

Nếu yêu cầu chỉ là bật session fixation protection, điều chỉnh hạn mức concurrency hoặc xác định policy, **bắt đầu bằng DSL**. Chỉ triển khai strategy tùy biến khi có nghiệp vụ cụ thể và test đầy đủ đường đi HTTP.

Ví dụ cấu hình bean Java trong một project Spring Boot 3.x **Servlet**:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .defaultSuccessUrl("/account", true)
            .permitAll())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId()))
        .build();
}
```

Đây là **mảnh method** có các import từ Spring Security; bản project runnable nằm ở mục 9. Với Servlet hỗ trợ đổi session ID, cấu hình trên biểu đạt tường minh kỳ vọng chống session fixation. Không thêm `sessionFixation().none()` để làm các test “dễ pass”.

### SessionCreationPolicy khác SessionAuthenticationStrategy

| Policy | Mục đích | Ngữ nghĩa thực tế |
|---|---|---|
| `ALWAYS` | Spring Security chủ động dùng/tạo session | Phù hợp ứng dụng chủ ý dùng session |
| `IF_REQUIRED` | Chỉ tạo session khi thành phần cần | Phổ biến cho website form login |
| `NEVER` | Security không chủ động tạo session mới nhưng có thể dùng session đang có | Không phải chế độ stateless tuyệt đối |
| `STATELESS` | Không tạo session và không dùng session để nạp SecurityContext | Thường phù hợp bearer-token API, không phù hợp nếu muốn duy trì form login bằng session |

`SessionCreationPolicy` nói về **cách Spring Security dùng session**, không phải thuật toán đổi session ID. Nó cũng không cấm mọi servlet component khác tạo session, và không tự tắt CSRF. Trong form login mặc định, nếu cấu hình `STATELESS` nhưng lại mong sau 302 browser vẫn đăng nhập nhờ HttpSession, đó là mâu thuẫn thiết kế.

Có thể dùng nhiều `SecurityFilterChain`: một chain web stateful form login và một chain API stateless. Khi đó phải kiểm tra matcher/order để tránh URL đăng nhập rơi vào chain sai.

## 8. Những lưu ý về session fixation và session attributes

Tại thời điểm login thành công, trình duyệt có thể đang có session chứa dữ liệu phục vụ việc trước khi đăng nhập: CSRF token, request cache, flash attributes, giỏ hàng ẩn danh, tùy chọn ngôn ngữ... Thay session cần cân nhắc các dữ liệu nào nên giữ.

- `changeSessionId()` thường cho phép giữ session hiện có và các attributes nhưng xoay ID; đây là lựa chọn thích hợp ở môi trường Servlet hiện đại.
- `migrateSession()` hoặc `newSession()` có thể có chính sách tạo session mới/chuyển attributes khác nhau. Đọc đúng tài liệu version và kiểm thử các lifecycle callbacks với session-scoped components.
- Không tự copy tất cả attributes nhạy cảm từ anonymous sang authenticated session nếu không hiểu trust boundary. Một attribute do request ẩn danh tạo có thể ảnh hưởng kết quả ứng dụng sau đăng nhập.
- Đảm bảo reverse proxy, cookie domain/path, HTTPS và session tracking thống nhất để client nhận ID mới; khi cookie không quay lại, kết quả biểu hiện như session bị mất.

Đừng kết luận session fixation protection đã chạy chỉ từ việc thấy có `JSESSIONID`. Cần so sánh session identifier **trước và sau** bước xác thực trong một môi trường test được kiểm soát, hoặc dùng integration test phù hợp. Tránh ghi ID thực vào log/report; đối chiếu trong test bằng assertion là đủ.

## 9. Ví dụ thực hành Spring Boot MVC: session và SecurityContext tồn tại sau redirect

Ví dụ dùng **Java 17+, Maven, Spring Boot 3.3.5** và Spring Security do Boot quản lý. Đây là mốc để tái tạo bài học, không phải cam kết về vòng đời hỗ trợ; sản phẩm thật phải chọn phiên bản hiện hành phù hợp.

Mục tiêu kiểm thử:

1. Truy cập `/account` chưa đăng nhập dẫn tới trang login.
2. Login hợp lệ bằng POST kèm CSRF token, success handler redirect tới `/account`.
3. Request **sau redirect** dùng session đã lưu có thể đọc principal.
4. Request mới không mang session tương ứng vẫn chưa đăng nhập.
5. Login sai mật khẩu không biến thành đăng nhập thành công.
6. POST login thiếu CSRF token bị chặn trước bước xác minh credential.

### 9.1. Cấu trúc project

```text
session-login-demo/
├── pom.xml
└── src/
    ├── main/java/example/sessionlogin/
    │   ├── SessionLoginApplication.java
    │   ├── WebSecurityConfig.java
    │   └── AccountController.java
    └── test/java/example/sessionlogin/
        └── SessionLoginTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>session-login-demo</artifactId>
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

Đừng khai báo phiên bản Spring Security độc lập cho từng module: Spring Boot parent căn các dependencies cùng một hệ.

### 9.3. Spring Boot entry point

Tạo `src/main/java/example/sessionlogin/SessionLoginApplication.java`:

```java
package example.sessionlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLoginApplication.class, args);
    }
}
```

### 9.4. Security configuration

Tạo `src/main/java/example/sessionlogin/WebSecurityConfig.java`:

```java
package example.sessionlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/account", true)
                .failureUrl("/login?error")
                .permitAll())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()))
            .build();
    }
}
```

Giải thích:

- `UserDetailsService` và `PasswordEncoder` tạo một tài khoản **demo-only**. Không dùng credential này trong môi trường thật.
- `formLogin(...)` kích hoạt cơ chế nhận POST login của Spring Security; không cần tự thêm `@PostMapping("/login")`.
- `sessionFixation(...changeSessionId())` thể hiện rõ chiến lược xoay session ID khi login.
- `defaultSuccessUrl("/account", true)` đặt redirect cố định để kiểm thử; nếu không có flag `true`, saved request có thể ảnh hưởng URL cuối cùng.
- Không tắt `csrf`. Form POST cần CSRF token hợp lệ theo thiết kế của website dùng session/cookie.
- Không khai báo custom `SecurityContextRepository` khi không cần thiết; để cấu hình tích hợp chuẩn đảm nhiệm quá trình lưu context.

### 9.5. Controller

Tạo `src/main/java/example/sessionlogin/AccountController.java`:

```java
package example.sessionlogin;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "PUBLIC_OK";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
```

Controller không cần tự đọc `HttpSession` và cũng không có logic đặt user vào SecurityContext; security filter đã xử lý xác thực/authorization. Nếu user đã login mà muốn truy cập dữ liệu nhạy cảm, thêm phân quyền theo vai trò và ownership phù hợp.

### 9.6. Integration test với MockMvc

Tạo `src/test/java/example/sessionlogin/SessionLoginTest.java`:

```java
package example.sessionlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymousAccess() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void protectedEndpointWithoutLoginRedirectsToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login")));
    }

    @Test
    void authenticatedSessionWorksOnFollowingRequest() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, student"));

        // Một request mới KHÔNG dùng session đã lưu không có principal cũ.
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void wrongPasswordDoesNotLogUserIn() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void loginPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "demo-only-password"))
            .andExpect(status().isForbidden());
    }
}
```

Các test gửi request qua **Spring Security servlet filter chain** nhờ `@SpringBootTest` và `@AutoConfigureMockMvc`. Test thứ ba không dừng ở response redirect mà kiểm tra **request tiếp theo với cùng MockHttpSession**. Đây là bằng chứng thực hành rằng trạng thái authentication đã được lưu và nạp giữa hai request trong cấu hình minh họa.

Test này **chưa đo riêng việc session ID có thay đổi không**, vì điều đó cần mô phỏng một session có sẵn trước login và quan sát ID theo implementation/Servlet environment. Cấu hình strategy đã được khai báo nhưng kiểm thử security fixation ở mức production nên có integration test bổ sung với session cũ, cookie và real container phù hợp.

### 9.7. Chạy demo

Trong thư mục chứa `pom.xml`, với JDK 17+, Maven và dependency repositories/cache:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Nếu source được đặt đúng vị trí và dependency resolve thành công, kỳ vọng **5 JUnit test pass**. Kết quả Maven tổng thể phụ thuộc máy, nên không có transcript cố định; đây là kết quả dự kiến chứ không phải tuyên bố đã chạy lệnh. Khi chạy server ở cổng 8080 mặc định, truy cập `http://localhost:8080/login`, đăng nhập bằng tài khoản fixture rồi mở `/account`. Chuỗi body chính xác của controller với principal đã xác thực là:

```text
Hello, student
```

Trang login mặc định, header, cookie và mã redirect HTTP có thể khác nhau theo cấu hình/dependency và reverse proxy. Đừng triển khai fixture username/password đó lên môi trường công khai.

## 10. Giới hạn số session đồng thời: một trường hợp khác của SessionAuthenticationStrategy

Nếu yêu cầu nghiệp vụ là tối đa một phiên cho một tài khoản, có thể dùng cấu hình DSL của Spring Security tương ứng, ví dụ (mảnh trong `SecurityFilterChain`, không phải file Java độc lập):

```java
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true))
```

Ý nghĩa thường gặp: khi đã có một session được theo dõi cho user, một login mới vượt giới hạn có thể bị từ chối thay vì tự đẩy session cũ ra. Nếu chọn policy khác, phiên cũ có thể được đánh dấu expired và bị xử lý khi có request tiếp theo.

**Cần kiểm tra thực tế:** session registry, các cơ chế đăng ký/hủy session, servlet session lifecycle listener và môi trường multi-node. Không coi `maximumSessions(1)` là cơ chế “khóa tài khoản trên toàn thế giới”: nếu registry chỉ chạy cục bộ trên một server, nhiều instance có thể không chia sẻ số phiên. Cấu hình có thể cần thêm dependency/hạ tầng để hoạt động đúng khi phân tán; đọc tài liệu của bản Security đang triển khai.

Concurrency control là **một loại hậu kiểm sau xác thực**; nó vẫn không thay thế repository lưu context. User được xác thực theo provider nhưng bị session strategy từ chối có thể được xử lý như một lần đăng nhập thất bại do chính sách phiên. Phân biệt với kết quả password sai để ghi log và hướng dẫn hỗ trợ phù hợp, không lộ chi tiết session cho bên không có quyền.

## 11. Stateless API và session-based form login không dùng chung mọi giả định

Một website có form login thường dựa vào cookie/session để trình duyệt gửi các request sau đó. Ngược lại, một resource server xác thực bearer token thường kiểm tra token **mỗi request** và không cần lưu authentication vào HttpSession.

Ví dụ mảnh cấu hình **cho API stateless riêng**, không phải điều chỉnh trực tiếp vào form-login demo ở mục 9:

```java
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .oauth2ResourceServer(oauth -> oauth
        .jwt(Customizer.withDefaults()));
```

Đoạn minh họa đòi dependency Resource Server và cấu hình issuer/JWK tin cậy, audience/claims và authorization rules phù hợp. Không phải ai gửi một chuỗi JWT cũng đáng tin. Với API kiểu này, việc cố lưu bearer authentication trong HTTP session có thể trái mục tiêu stateless.

Khi kết hợp nhiều chains:

- Web chain xử lý `/login`, `/account` và dùng session.
- API chain xử lý `/api/**`, nhận bearer token và stateless.
- Matcher và `@Order` cần xác định rõ; phải có fallback chain khi muốn bảo vệ các URL ngoài API.
- CSRF được thiết kế theo **cách client gửi credential**, không tự vô hiệu chỉ vì một chain gắn nhãn API.

**SessionAuthenticationStrategy không có nghĩa mọi hệ thống bắt buộc dùng session.** Chiến lược xác thực phù hợp phải dựa trên giao thức và mức state cần duy trì.

## 12. Khi tự viết luồng đăng nhập: những trách nhiệm không được bỏ quên

Một custom authentication endpoint có thể tự gọi `AuthenticationManager.authenticate(...)`, nhưng làm vậy không tự động kích hoạt mọi hook của `UsernamePasswordAuthenticationFilter`.

Mô hình tối thiểu về mặt thứ tự:

```text
1. Đọc credential an toàn, kiểm tra CSRF/trust boundary.
2. AuthenticationManager.authenticate(untrustedCredential)
3. Nếu thành công: SessionAuthenticationStrategy.onAuthentication(...)
4. Tạo SecurityContext mới, đặt Authentication đã xác minh
5. SecurityContextHolder.setContext(context)
6. SecurityContextRepository.saveContext(context, request, response)
7. Remember-me/event/response handler theo giao thức đã chọn
8. Redirect/commit response và dọn holder đúng lifecycle
```

Một phần logic Java **minh họa trong custom component có biến đã được inject**:

```java
Authentication result =
    authenticationManager.authenticate(unauthenticatedRequest);

sessionAuthenticationStrategy.onAuthentication(result, request, response);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
// Sau đó mới tạo redirect hoặc response phù hợp.
```

Đây **không phải class chạy độc lập**: `unauthenticatedRequest` phải là Authentication token chưa được tin cậy; `request`/`response` là Servlet objects; manager, strategy và repository phải đến từ một security configuration nhất quán. Đoạn ngắn này chưa xử lý exception, CSRF, remember-me, event, timeout, response hoặc cạnh tranh phiên; không đem nguyên xi vào production.

Ưu tiên dùng flow authentication có sẵn khi có thể. Khi tự can thiệp, đặc biệt kiểm thử:

- `SessionAuthenticationException` từ strategy có được chuyển thành phản hồi thất bại đúng không?
- Context có được lưu **trước redirect** và nạp lại ở request kế tiếp?
- Cookie/session ID có xoay đúng khi nâng quyền từ anonymous lên authenticated?
- Authentication bị thu hồi/logout có được xóa khỏi session/repository và client hay không?
- Có xảy ra double invocation strategy hoặc double save do vừa chạy custom code vừa dùng filter chuẩn không?

Không thực hiện `sessionAuthenticationStrategy.onAuthentication(...)` lại trong success handler của form login mặc định chỉ vì bạn muốn “chắc chắn có session”. Thao tác trùng có thể làm thay session ID nhiều lần hoặc ghi nhận concurrency sai.

## 13. Logout, session timeout và cập nhật quyền

**Lưu SecurityContext sau login không đồng nghĩa quyền tồn tại vô thời hạn.** Một session có thể hết hạn, bị hủy, bị thay đổi ID, bị từ chối do concurrency policy hoặc trở nên không phù hợp khi quyền người dùng thay đổi.

Trong luồng logout của Spring Security, framework có thể:

- Xóa `Authentication` khỏi `SecurityContextHolder` và repository theo cấu hình.
- Invalidate HTTP session, xóa cookie chỉ khi cấu hình và phản hồi thực tế hỗ trợ.
- Thực thi remember-me logout handler hoặc cơ chế logout phía identity provider khi được thiết kế.

Chỉ gọi `SecurityContextHolder.clearContext()` trong một thread không nhất thiết xóa context đã lưu trong session. Ngược lại, chỉ xóa cookie phía browser không luôn làm server session vô hiệu; quản lý cả hai phía tùy policy.

Nếu user bị thu hồi quyền, dữ liệu Authentication đã lưu trong session có thể chứa authorities cũ. Cần chính sách reauthentication, refresh context hoặc session invalidation dựa trên yêu cầu nghiệp vụ. Repository không tự đồng bộ authorities với mọi thay đổi trong kho người dùng.

## 14. Lỗi thường gặp: chẩn đoán theo symptom

| Triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
|---|---|---|
| Login POST trả 302 thành công nhưng GET kế tiếp tới /account bị redirect login | Quên `SecurityContextRepository.saveContext` trong custom flow, client không giữ session cookie, hoặc repository sai | Kiểm tra save/load, Set-Cookie/Cookie, thời điểm response commit và security chain |
| Login đúng password nhưng bị từ chối do session policy | `SessionAuthenticationStrategy` ném exception (concurrency/session) | Phân biệt kết quả manager với kết quả hậu kiểm session, rà soát SessionRegistry |
| Session ID không thay khi đăng nhập | Session fixation policy chưa kích hoạt, filter dùng strategy khác hoặc login không đi qua chain dự kiến | Xác định filter/strategy được gọi; test session trước/sau login |
| Session ID đã thay nhưng vẫn mất login | Strategy đã chạy nhưng repository chưa lưu context, session không đến browser, hoặc base path/domain cookie sai | Kiểm tra riêng thao tác save và request mới có cùng session |
| Đã đặt context trong holder nhưng refresh mất user | `SecurityContextHolderFilter` không tự save context của custom flow | Gọi save đúng repository khi cần và dùng filter authentication chuẩn nếu có |
| Đăng nhập từ một browser khiến browser khác bị logout | Concurrency policy giới hạn phiên đang có | Kiểm tra `maximumSessions`/`maxSessionsPreventsLogin` và registry |
| Limit một session nhưng nhiều node vẫn cho login mới | Registry/session store không chia sẻ giữa instances | Kiểm tra Spring Session, cluster session registry, logout/expiration propagation |
| POST login thiếu CSRF token trả 403 trước khi xác thực | `CsrfFilter` chặn request | Giữ CSRF phù hợp, đừng tắt global để che lỗi |
| Sau logout vẫn được xác thực | Context trong session chưa bị xóa, remember-me hoặc SSO đã login lại | Kiểm tra logout handlers, session invalidation, cookie và IdP |
| API stateless bất ngờ có session | Request cache, MVC layer, custom code hoặc web chain/stateful config khác | Xác định thành phần tạo session; kiểm tra đúng chain và SessionCreationPolicy |
| Session hiển thị thông tin quyền đã cũ | Context chứa authorities cũ, thiếu chính sách cập nhật/revoke | Đặt chiến lược invalidation/reauthentication phù hợp |
| Test dùng `@WithMockUser` pass nhưng login production lỗi | Mock user bỏ qua password manager, strategy và repository thật | Bổ sung MockMvc test POST /login và request sau bằng session |

Đừng phán đoán chỉ từ HTTP status. Một request bị `403` có thể do CSRF hoặc phân quyền; `302` có thể là success redirect hoặc redirect tới login; `401` có thể do authentication entry point. Xác định filter/handler và session hiện tại trước khi sửa code.

## 15. Checklist kiểm thử khi triển khai form login có session

- [ ] Dự án sử dụng **Servlet** và đúng `SecurityFilterChain` cho POST login; không lẫn cấu hình reactive.
- [ ] `AuthenticationManager` xác thực credential trước khi thực hiện bất kỳ thao tác session đăng nhập thành công nào.
- [ ] Session fixation protection dùng chiến lược phù hợp Servlet container; có kiểm thử session ID trước/sau login khi cần.
- [ ] Nếu giới hạn concurrency, xác định rõ khi nào từ chối login mới hoặc cho phép login mới và hết hạn phiên cũ.
- [ ] Context đã được đặt vào holder **và lưu qua repository** khi flow cần duy trì xác thực qua request khác.
- [ ] Context repository mà login filter dùng nhất quán với repository được dùng khi nạp ở các request tiếp theo.
- [ ] Cookie có `Secure`/`HttpOnly`/`SameSite` và cấu hình domain/path phù hợp với HTTPS, reverse proxy và luồng đăng nhập.
- [ ] POST login được CSRF protection bảo vệ phù hợp mô hình browser/session.
- [ ] Sau success redirect, test một request dùng session hợp lệ có principal; request mới không có session không tự kế thừa authentication.
- [ ] Sau logout, session expiry, credential reset hoặc thay đổi quyền, kiểm tra đúng chính sách thu hồi.
- [ ] Không dựa vào `@WithMockUser` làm bằng chứng PasswordEncoder, SessionAuthenticationStrategy hoặc ContextRepository đã chạy.
- [ ] Không log raw password, session ID, CSRF token hay token khác vào log/test artifact.
- [ ] Với nhiều instance, kiểm tra session store/registry, routing, failover và trạng thái concurrency.

### Câu hỏi tự kiểm tra

**1.** `AuthenticationManager` trả kết quả thành công. Có thể redirect ngay và coi login hoàn tất không?  
**Đáp án:** Chưa đủ cho session-based form login. Cần chính sách phiên thông qua strategy, thiết lập/lưu context đúng repository, rồi mới xử lý response.

**2.** Strategy đã đổi session ID, nhưng request tiếp theo không biết user. Điều đó có mâu thuẫn không?  
**Đáp án:** Không. Đổi session ID và lưu SecurityContext là hai thao tác riêng; phải kiểm tra repository, cookie và thời điểm save.

**3.** Trong Spring Security 6, chỉ gọi `SecurityContextHolder.setContext(context)` trong custom controller đã đủ chưa?  
**Đáp án:** Không nếu muốn giữ đăng nhập qua nhiều request. Explicit-save thường cần `SecurityContextRepository.saveContext(...)` khi custom flow không được filter chuẩn tự thực hiện.

**4.** `SessionCreationPolicy.STATELESS` có phù hợp với một website mong sau form login browser gửi lại session cookie để duy trì user không?  
**Đáp án:** Thường không; đó là mâu thuẫn giữa cơ chế stateless và kỳ vọng session-based login.

**5.** `maximumSessions(1)` có chắc giới hạn toàn bộ user trên mọi máy chủ nếu ứng dụng chạy nhiều instance không?  
**Đáp án:** Không thể kết luận nếu chưa kiểm tra session store/registry và cơ chế đồng bộ trong cluster.

**6.** Có thể dùng `@WithMockUser` để chứng minh SessionAuthenticationStrategy đã chống fixation không?  
**Đáp án:** Không. Annotation này dựng mock security context, không thực hiện trọn flow POST login. Cần integration test có session thực/mô phỏng qua filter và so sánh session ID.

**7.** Vì sao với form login nên giữ CSRF protection?  
**Đáp án:** Trình duyệt có thể tự gửi cookie/session; POST login và các thao tác thay đổi trạng thái phải được bảo vệ theo ranh giới credential, độc lập với việc password đúng hay strategy đã chạy.

**Kết luận:** `SessionAuthenticationStrategy` giải quyết **chính sách HTTP session sau khi AuthenticationManager xác minh thành công**; `SecurityContextRepository` giải quyết **việc giữ và khôi phục SecurityContext giữa các request**. Trong form login Servlet, hai phần được filter chuẩn điều phối đúng thứ tự. Khi tùy biến, phải kiểm chứng cả **session fixation/concurrency** lẫn **explicit save, cookie và request sau redirect**, không chỉ nhìn một phản hồi login thành công.