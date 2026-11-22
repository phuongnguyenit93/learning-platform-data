# Thành phần xử lý thành công, thất bại và yêu cầu đăng nhập

Một request tới ứng dụng Spring Boot có thể được phép, được chuyển tới trang đăng nhập, nhận 401 hoặc bị từ chối với 403. Những phản hồi này không do một thành phần duy nhất quyết định. Spring Security có các điểm mở rộng với **trách nhiệm khác nhau**: AuthenticationSuccessHandler, AuthenticationFailureHandler, AuthenticationEntryPoint, AccessDeniedHandler và ExceptionTranslationFilter. Hiểu ranh giới giữa chúng giúp cấu hình đúng cho website dùng form login và REST API dùng HTTP Basic hoặc Bearer token.

Bài học tập trung vào **bản đồ thành phần và luồng xử lý** trong Spring Security Servlet/MVC hiện đại, kèm ví dụ chạy được trên Java 17 và Spring Boot 3.3.x. Một số hành vi cụ thể phụ thuộc kiểu xác thực, thứ tự SecurityFilterChain và cấu hình ứng dụng; không phải mọi request đều đi qua tất cả handler.

## 1. Phân biệt bốn kết quả thường gặp

Giả sử ứng dụng có các tài nguyên sau:

- GET /public: ai cũng được xem.
- GET /user: chỉ cần đăng nhập.
- GET /admin: phải có vai trò ADMIN.
- GET /api/me: yêu cầu HTTP Basic.
- GET /api/admin: yêu cầu HTTP Basic và vai trò ADMIN.

Một request sẽ rơi vào các tình huống sau:

| Tình huống | Điều đang diễn ra | Phản hồi điển hình |
| --- | --- | --- |
| Truy cập tài nguyên công khai | Quy tắc authorization cho phép, không cần xác thực. | 200 nếu Controller xử lý thành công. |
| Người dùng ẩn danh truy cập tài nguyên cần đăng nhập | Chưa có danh tính đã xác thực phù hợp. | Browser form login: 302 tới /login; HTTP Basic/Bearer API: thường là 401. |
| Người dùng gửi đúng tài khoản, mật khẩu ở form login | Một filter xác thực hoàn thành thành công. | Success handler quyết định redirect hoặc response sau khi login. |
| Người dùng gửi sai mật khẩu ở form login | Filter xác thực gặp AuthenticationException trong luồng login đó. | Failure handler thường redirect tới /login?error hoặc trả lỗi. |
| Người dùng đã đăng nhập nhưng thiếu quyền | Authorization từ chối hành động. | Thường là 403, xử lý qua AccessDeniedHandler trong luồng tương ứng. |
| Request POST bị chặn do CSRF | Cơ chế bảo vệ CSRF từ chối request. | Thường 403; vị trí xử lý lỗi có thể khác luồng authorization URL. |

**Điểm phân biệt quan trọng:** “đăng nhập thất bại” là một sự kiện trong **quá trình xác thực credential**, còn “cần đăng nhập để xem tài nguyên” là **yêu cầu khởi đầu xác thực** khi truy cập tài nguyên được bảo vệ. Hai tình huống có thể dùng hai handler khác nhau.

Một request GET /user ẩn danh không nhất thiết đã thử đăng nhập; đó thường là trường hợp **AuthenticationEntryPoint**. Một request POST /login với mật khẩu sai mới là trường hợp điển hình của **AuthenticationFailureHandler**.

## 2. Bản đồ các thành phần chính

| Thành phần | Vai trò | Khi thường được gọi | Ví dụ phản hồi |
| --- | --- | --- | --- |
| **AuthenticationSuccessHandler** | Quyết định bước tiếp theo sau **một lần xác thực thành công** trong luồng filter sử dụng handler này. | Form login hoặc interactive authentication filter hoàn thành xác thực. | 302 tới /user; redirect về request đã lưu; trả JSON theo thiết kế. |
| **AuthenticationFailureHandler** | Xử lý **thất bại khi thực hiện một luồng xác thực** có dùng failure handler. | POST /login với mật khẩu sai, tài khoản bị khóa, credential không hợp lệ trong form login. | 302 tới /login?error; 401 JSON trong API login tùy cấu hình. |
| **AuthenticationEntryPoint** | **Bắt đầu cơ chế xác thực** khi request cần danh tính mà chưa có xác thực phù hợp. | Ẩn danh vào trang cần login; API thiếu/sai credential khi cơ chế đó dùng entry point. | Redirect tới trang login; 401 và WWW-Authenticate. |
| **AccessDeniedHandler** | Xử lý request đã bị từ chối quyền truy cập trong luồng cần trả access denied. | Principal hợp lệ thiếu role/scope/permission; một số lỗi CSRF theo filter. | 403; trang lỗi quyền; JSON lỗi an toàn. |
| **ExceptionTranslationFilter** | Chuyển AuthenticationException/AccessDeniedException phát sinh **ở downstream** thành hành vi HTTP phù hợp. | Filter phân quyền ở sau nó báo thiếu xác thực hoặc thiếu quyền. | Gọi entry point hoặc access denied handler theo trạng thái xác thực. |
| **RequestCache** | Có thể ghi nhớ request cần xác thực để trở lại đích sau login. | Người dùng ẩn danh vào trang được bảo vệ, sau đó login thành công. | SavedRequestAwareAuthenticationSuccessHandler dùng saved request nếu phù hợp. |

Những thành phần này **không thay thế** bộ máy xác thực hoặc bộ máy phân quyền. Một số thành phần liên quan khác:

- **AuthenticationManager / AuthenticationProvider**: kiểm tra credential và tạo Authentication được xác thực khi thành công, hoặc báo AuthenticationException phù hợp.
- **Authentication (principal + authorities)**: đại diện danh tính và các quyền đã được xác định bởi cơ chế đáng tin.
- **SecurityContextHolder / SecurityContextRepository**: cách truy cập và lưu/khôi phục SecurityContext theo cơ chế và chiến lược được cấu hình.
- **UsernamePasswordAuthenticationFilter**: nhận form login POST theo đường mặc định /login, gọi cơ chế xác thực, rồi dùng success/failure handler.
- **BasicAuthenticationFilter**: xử lý HTTP Basic; luồng thất bại của nó thường dùng AuthenticationEntryPoint, không có nghĩa sẽ chạy form-login failure handler.
- **AuthorizationFilter**: áp dụng chính sách truy cập được cấu hình; nếu bị từ chối có thể phát sinh AccessDeniedException.
- **CsrfFilter**: kiểm tra token cho request áp dụng CSRF policy, thường trước khi Controller chạy.
- **SecurityFilterChain / FilterChainProxy**: tổ chức chuỗi filter phù hợp cho request. Nếu có nhiều chain, chain đầu tiên khớp sẽ quyết định tập filter/chính sách của request.

Tên component cho biết vai trò phổ biến, nhưng hành vi runtime phải được kiểm tra ở cấu hình và đường gọi thật. Ví dụ, **AuthenticationSuccessHandler không phải callback chạy sau mọi request HTTP có Authentication hợp lệ**.

## 3. Sơ đồ quyết định từ request tới response

Đây là sơ đồ khái niệm cho một ứng dụng vừa có web form login vừa có API. Nó chỉ vẽ các nhánh chính; trong thực tế nhiều filter có thể chặn sớm hoặc có entry point riêng.

~~~mermaid
flowchart TD
    R["HTTP request"] --> C["SecurityFilterChain phù hợp"]
    C --> L{"Request đang thực hiện login?"}
    L -- "Có" --> A["Filter gọi AuthenticationManager"]
    A --> AS{"Credential hợp lệ?"}
    AS -- "Có" --> SH["AuthenticationSuccessHandler"]
    AS -- "Không" --> FH["AuthenticationFailureHandler"]
    L -- "Không" --> P["Xây dựng / khôi phục SecurityContext khi phù hợp"]
    P --> Z["Authorization check"]
    Z --> AU{"Cho phép?"}
    AU -- "Có" --> CT["Controller / Service"]
    AU -- "Không" --> EX["AccessDeniedException hoặc xử lý từ chối"]
    EX --> TYPE{"Principal đã đủ mức xác thực?"}
    TYPE -- "Chưa / anonymous" --> EP["AuthenticationEntryPoint"]
    TYPE -- "Đã xác thực" --> DH["AccessDeniedHandler"]
~~~

Trong nhánh authorization điển hình, **ExceptionTranslationFilter** chịu trách nhiệm chuyển ngoại lệ từ downstream thành quyết định gọi AuthenticationEntryPoint hay AccessDeniedHandler. Một số authentication filter tự bắt lỗi và trực tiếp gọi entry point/failure handler. Không có bảo đảm rằng mọi ngoại lệ 401/403 đều đi qua một điểm duy nhất.

### 3.1. Luồng A: truy cập trang bảo vệ khi chưa đăng nhập

~~~text
GET /user (anonymous)
    -> SecurityFilterChain dành cho web
    -> Authorization thấy cần authenticated()
    -> ExceptionTranslationFilter nhận ngoại lệ downstream
    -> AuthenticationEntryPoint cho form login
    -> HTTP 302 Location: /login
    -> Browser GET /login
    -> Trang đăng nhập được hiển thị
~~~

**Chưa có thao tác gửi mật khẩu** nên thông thường chưa gọi AuthenticationFailureHandler. Trong cơ chế form login có RequestCache, ứng dụng còn có thể lưu request ban đầu để sau khi login trở lại tài nguyên đích; phụ thuộc handler và session policy.

### 3.2. Luồng B: gửi form login thành công

~~~text
POST /login (username/password + CSRF token hợp lệ)
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager / AuthenticationProvider
    -> Xác thực thành công
    -> Tạo/ghi SecurityContext theo cơ chế cấu hình
    -> AuthenticationSuccessHandler
    -> Ví dụ HTTP 302 Location: /user
~~~

Ở đây success handler nhận kết quả Authentication thành công. Nó quyết định điều hướng hoặc response của **thao tác login**, không tự cấp role và không tự kiểm quyền đối tượng nghiệp vụ.

### 3.3. Luồng C: gửi form login thất bại

~~~text
POST /login (mật khẩu sai, request hợp lệ)
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager / AuthenticationProvider
    -> AuthenticationException
    -> AuthenticationFailureHandler
    -> Ví dụ HTTP 302 Location: /login?error
~~~

Thất bại do sai credential được xử lý bởi failure handler **trong filter đăng nhập đó**. Nếu request POST /login bị CsrfFilter từ chối **trước khi bộ xác thực chạy**, kết quả có thể là 403 chứ không phải redirect với thông báo sai mật khẩu.

### 3.4. Luồng D: đã đăng nhập nhưng thiếu vai trò

~~~text
GET /admin (principal USER)
    -> Authentication đã hợp lệ
    -> Authorization yêu cầu ROLE_ADMIN
    -> Bị từ chối
    -> AccessDeniedHandler ở luồng phù hợp
    -> HTTP 403 Forbidden
~~~

Đây không phải mật khẩu sai và cũng không có lý do để thử đăng nhập lại khi user đã xác thực đủ mức nhưng thiếu role. Trong một số chính sách dành cho tài nguyên riêng tư, ứng dụng có thể che sự tồn tại bằng 404; điều quan trọng là không trả dữ liệu hay thực hiện side effect trái phép.

### 3.5. Luồng E: API dùng HTTP Basic

~~~text
GET /api/me, không có Authorization
    -> Authorization yêu cầu authenticated()
    -> Basic AuthenticationEntryPoint
    -> HTTP 401 + WWW-Authenticate: Basic ...

GET /api/me, Authorization: Basic hợp lệ
    -> BasicAuthenticationFilter xác thực
    -> Authorization cho phép
    -> Controller trả HTTP 200
~~~

Một lần xác thực Basic thành công **không đồng nghĩa** form-login AuthenticationSuccessHandler sẽ chạy. BasicAuthenticationFilter hoạt động theo cơ chế riêng và có thể xác thực trên mỗi request chưa có Authentication phù hợp trong context. Token Bearer với OAuth2 Resource Server cũng có entry point và handler lỗi riêng; không xem nó như form login.

## 4. AuthenticationSuccessHandler: khi xác thực thành công

Interface **AuthenticationSuccessHandler** định nghĩa cách ứng dụng phản hồi sau khi một authentication filter hoàn tất đăng nhập thành công. Với form login, các lựa chọn phổ biến:

- **SimpleUrlAuthenticationSuccessHandler**: redirect tới một URL mặc định hoặc đích do cấu hình cho phép.
- **SavedRequestAwareAuthenticationSuccessHandler**: ưu tiên redirect tới request đã lưu trong RequestCache nếu có, sau đó dùng target mặc định.
- **Handler tùy biến**: trả JSON hoặc điều hướng theo logic được thiết kế, nhưng phải giữ tính an toàn và tránh đưa secret vào response/log.

Ví dụ mảnh cấu hình dành cho web form login:

~~~java
.formLogin(form -> form
    .successHandler(new SimpleUrlAuthenticationSuccessHandler("/user"))
)
~~~

Đây là **mảnh code trong HttpSecurity configuration**, không phải chương trình Java độc lập. Nó điều hướng tới /user sau một lần form login thành công. Nếu sử dụng handler này, request ban đầu không tự động được ưu tiên giống SavedRequestAwareAuthenticationSuccessHandler; đây là quyết định UX cần chọn có chủ đích.

**Success handler không chứng minh được quyền vào /admin.** Sau redirect, request GET /admin hoặc /user vẫn được kiểm tra bởi authorization policy mới. Nếu người dùng thiếu role, GET /admin vẫn phải bị từ chối.

### 4.1. Về saved request và redirect

Khi khách truy cập /checkout trước khi login, RequestCache có thể ghi nhớ một request để dùng làm điểm quay lại. SavedRequestAwareAuthenticationSuccessHandler có thể redirect sau login tới URL đã lưu.

Cần lưu ý:

- Không lấy tham số returnUrl/next từ client rồi redirect tùy ý; phải giới hạn đích tin cậy để tránh open redirect.
- Không mặc nhiên “phát lại” một request POST cũ kèm body và side effect. RequestCache thường phục vụ điều hướng về tài nguyên; phương thức, dữ liệu và CSRF của thao tác thay đổi trạng thái cần thiết kế riêng.
- Với REST API stateless, RequestCache và login redirect có thể không phù hợp; nên dùng response API rõ ràng thay vì HTML redirect.
- Session fixation và security context persistence là các quan tâm riêng; success handler không tự thay thế cơ chế bảo vệ phiên của Spring Security.

## 5. AuthenticationFailureHandler: khi xác thực thất bại

**AuthenticationFailureHandler** xử lý thất bại của một authentication flow có sử dụng handler này, thường là POST /login trong form login.

Ví dụ:

~~~java
.formLogin(form -> form
    .failureHandler(
        new SimpleUrlAuthenticationFailureHandler("/login?error")
    )
)
~~~

Khi mật khẩu sai, failure handler redirect tới URL được cấu hình. Nó có thể nhận AuthenticationException mô tả lý do kỹ thuật, nhưng response công khai cần hạn chế tiết lộ thông tin.

Các ngoại lệ liên quan có thể gồm BadCredentialsException, DisabledException, LockedException hoặc CredentialsExpiredException tùy AuthenticationProvider và trạng thái account. **Không nên phản hồi thông báo giúp kẻ tấn công phân biệt rõ “user có tồn tại hay không”** nếu không có yêu cầu nghiệp vụ và biện pháp bảo vệ thích hợp. Có thể log nguyên nhân nội bộ theo chính sách, đồng thời trả thông điệp tổng quát cho người dùng.

### 5.1. Không phải lỗi nào cũng gọi FailureHandler

Những trường hợp sau cần phân biệt:

| Tình huống | Thành phần thường xử lý |
| --- | --- |
| Sai mật khẩu khi gửi POST /login đúng luồng form authentication | AuthenticationFailureHandler. |
| Chưa đăng nhập nhưng truy cập GET /admin | AuthenticationEntryPoint. |
| Gửi HTTP Basic credential sai tới GET /api/me | BasicAuthenticationFilter thường gọi AuthenticationEntryPoint. |
| Bearer token thiếu/hết hạn trong Resource Server | Bearer entry point hoặc cơ chế lỗi xác thực tương ứng. |
| Đã đăng nhập nhưng thiếu quyền | AccessDeniedHandler. |
| POST /login thiếu CSRF token | CsrfFilter có thể trả 403 trước khi login authentication filter chạy. |
| Controller/service phát sinh exception nghiệp vụ | Exception handler của ứng dụng; không tự động là AuthenticationFailureHandler. |

Nếu custom failure handler viết response JSON, thường cần đặt status phù hợp (ví dụ 401 khi credential sai trong API login), Content-Type chính xác, giới hạn thông tin lỗi, không đưa password/token vào body. Với website, redirect tới trang login có thông báo tổng quát là lựa chọn phổ biến.

## 6. AuthenticationEntryPoint: khi request cần xác thực

**AuthenticationEntryPoint** là điểm bắt đầu “authentication challenge” khi request chưa có xác thực phù hợp để truy cập tài nguyên được bảo vệ hoặc một cơ chế xác thực cần báo lỗi credential.

Các implementation điển hình:

| Implementation | Mục đích | Hành vi điển hình |
| --- | --- | --- |
| **LoginUrlAuthenticationEntryPoint** | Ứng dụng web dùng form login. | Redirect 302 tới /login. |
| **BasicAuthenticationEntryPoint** | HTTP Basic. | 401 kèm WWW-Authenticate: Basic realm=... |
| **BearerTokenAuthenticationEntryPoint** | OAuth2 Resource Server dùng Bearer token. | 401 và challenge Bearer theo ngữ cảnh. |
| **HttpStatusEntryPoint** | Chỉ cần trả status đã chọn. | Ví dụ 401 mà không render trang đăng nhập. |

Đây là các lựa chọn cho **cơ chế xác thực khác nhau**, không phải danh sách có thể cắm vào một cách tùy tiện. Ví dụ client HTTP Basic cần challenge thích hợp; thay bằng status 401 trống có thể làm thay đổi trải nghiệm/client negotiation.

Ví dụ khái niệm:

~~~text
Client GET /api/me không Authorization
           |
           v
Authorization yêu cầu user
           |
           v
AuthenticationEntryPoint cho HTTP Basic
           |
           v
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

**401** thông thường liên quan thiếu hoặc không có credential hợp lệ. Nếu API sử dụng Bearer token, nội dung challenge/error header phải tương thích cơ chế Bearer đã chọn. **302** là phản hồi điều hướng thường dùng cho browser form login. Không nên cấu hình một entry point redirect HTML login cho mọi REST client nếu chúng mong JSON hoặc 401.

### 6.1. AuthenticationEntryPoint khác FailureHandler ở đâu?

- **Entry point**: “Tài nguyên này cần một cơ chế xác thực; hãy bắt đầu/challenge” — ví dụ GET /admin khi ẩn danh.
- **Failure handler**: “Một lần thử đăng nhập theo luồng đang chạy đã thất bại” — ví dụ POST /login với password sai.

Một số filter như HTTP Basic gọi entry point trực tiếp khi credential sai; vì vậy phân biệt không phải bằng status code (cả hai có thể dẫn tới 401) mà bằng **vị trí và sự kiện trong luồng**.

## 7. AccessDeniedHandler: đã xác thực nhưng thiếu quyền

Khi một request bị authorization từ chối sau khi xác thực, AccessDeniedHandler thường quyết định response:

- HTTP 403 cho một API REST; JSON ngắn gọn nếu hợp đồng API yêu cầu.
- Trang “không có quyền” cho ứng dụng web.
- Ghi audit/sự kiện denied phù hợp nhưng không làm lộ dữ liệu.
- Có thể chọn 404 để tránh tiết lộ sự tồn tại của tài nguyên theo chính sách đã thống nhất.

Ví dụ mảnh cấu hình:

~~~java
.exceptionHandling(exceptions -> exceptions
    .accessDeniedHandler((request, response, denied) ->
        response.sendError(403)
    )
)
~~~

Mảnh này phù hợp trong SecurityFilterChain cho luồng cần trả 403, nhưng không đồng nghĩa mọi lỗi 403 đều đi qua handler đó. Ví dụ CsrfFilter có thể xử lý từ chối qua AccessDeniedHandler riêng của chính nó theo cấu hình filter. Proxy hoặc Controller cũng có thể tự trả 403.

**Authorization theo route khác authorization theo object.** GET /api/orders/42 có thể qua điều kiện authenticated() nhưng vẫn phải kiểm tra order.ownerId có khớp principal/tenant hiện tại không. Service phải ngăn trả dữ liệu và side effects nếu thiếu quyền. Việc trả 403 sau khi đã ghi DB trái phép không phải bảo vệ đúng.

## 8. ExceptionTranslationFilter: cầu nối từ exception sang HTTP

ExceptionTranslationFilter không có trách nhiệm đăng nhập hay xác thực mật khẩu. Nó **bắt một số AuthenticationException hoặc AccessDeniedException từ các filter ở phía sau trong chain** và chuyển sang hành động phản hồi tương ứng:

1. Nếu có **AuthenticationException**, khởi động authentication thông qua AuthenticationEntryPoint.
2. Nếu có **AccessDeniedException** và principal đang là anonymous hoặc ở mức xác thực chưa đủ trong logic tương ứng, khởi động AuthenticationEntryPoint.
3. Nếu có **AccessDeniedException** với principal đã xác thực đủ mức, gọi AccessDeniedHandler.

Đây là quyết định tại thời điểm xử lý exception. Spring Security sử dụng thông tin Authentication và trust resolver để phân biệt người dùng anonymous hoặc remember-me khi phù hợp. Đừng tự cài đặt kiểu “chỉ cần SecurityContext có một object bất kỳ là user đã đăng nhập đầy đủ”.

Luồng khái quát:

~~~mermaid
flowchart TD
    E["ExceptionTranslationFilter nhận exception downstream"] --> T{"Loại exception"}
    T -- "AuthenticationException" --> P["AuthenticationEntryPoint"]
    T -- "AccessDeniedException" --> S{"Anonymous / insufficient authentication?"}
    S -- "Có" --> P
    S -- "Không" --> D["AccessDeniedHandler"]
    P --> R1["401 challenge hoặc 302 login tùy cơ chế"]
    D --> R2["403 hoặc response denied được cấu hình"]
~~~

**Giới hạn quan trọng:** một filter nằm **trước** ExceptionTranslationFilter có thể tự xử lý exception. BasicAuthenticationFilter hoặc UsernamePasswordAuthenticationFilter có logic riêng khi authentication không thành công. Do đó không gắn nhận định “mọi 401/403 đều do ExceptionTranslationFilter” vào mọi hệ thống.

## 9. Ví dụ đầy đủ: web form login và API HTTP Basic trong Spring Boot

Ví dụ này giúp quan sát cả **success/failure handler**, **entry point** và **access denied handler** mà không nhầm hành vi giữa website và API. Hai SecurityFilterChain dùng matcher khác nhau:

- Chain API khớp /api/** và dùng HTTP Basic.
- Chain web mặc định cho các request còn lại và dùng form login.

Ví dụ chạy trong môi trường localhost bằng JDK 17+, Maven 3.9+ và Spring Boot 3.3.6 (phiên bản minh họa thuộc dòng 3.3.x). Tài khoản/mật khẩu chỉ để học; HTTP Basic dùng Base64, không mã hóa nội dung credential và phải dùng HTTPS trên mạng thực tế.

### 9.1. Cấu trúc thư mục

~~~text
security-handlers-demo/
  pom.xml
  src/main/java/com/example/handlers/SecurityHandlersApplication.java
  src/main/java/com/example/handlers/DemoController.java
  src/main/java/com/example/handlers/SecurityConfig.java
  src/test/java/com/example/handlers/SecurityHandlersTests.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-handlers-demo</artifactId>
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
~~~

### 9.3. SecurityHandlersApplication.java

~~~java
package com.example.handlers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityHandlersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityHandlersApplication.class, args);
    }
}
~~~

### 9.4. DemoController.java

~~~java
package com.example.handlers;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/user")
    public String user(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "web-admin";
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "api-admin";
    }
}
~~~

### 9.5. SecurityConfig.java

~~~java
package com.example.handlers;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(ex -> ex.accessDeniedHandler(
                (request, response, denied) ->
                    response.sendError(HttpServletResponse.SC_FORBIDDEN)
            ));

        // Mặc định CSRF còn bật; ví dụ chỉ gọi các endpoint GET.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/user").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler(
                    new SimpleUrlAuthenticationSuccessHandler("/user")
                )
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/login?error")
                )
                .permitAll()
            );

        // Dùng trang login mặc định do Spring Security tạo.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-admin"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Đọc cấu hình:**

1. **@Order(1) + securityMatcher("/api/**")** áp dụng HTTP Basic cho API; policy của API không tự dùng form login handler.
2. **@Order(2)** là chain web không có securityMatcher hẹp, dùng làm fallback cho các đường còn lại.
3. **API Basic** trả challenge khi cần đăng nhập; người dùng reader hợp lệ vẫn bị 403 ở /api/admin.
4. **Web form login** dùng success handler để redirect tới /user sau login, failure handler tới /login?error nếu username/password sai.
5. **Trang /login** được hỗ trợ bởi cấu hình formLogin mặc định với permitAll. Khi browser gửi form, cần CSRF token do trang login tạo; yêu cầu thủ công thiếu token có thể bị 403 trước khi tới failure handler.
6. **AccessDeniedHandler tùy biến của API** dùng sendError(403), chỉ thay cách phản hồi denied theo chain đó. Web chain dùng xử lý access denied mặc định.
7. **AuthenticationEntryPoint** của mỗi cơ chế được cấu hình thông qua formLogin/httpBasic. Không phải tự viết EntryPoint chỉ để quan sát hành vi mặc định.
8. **Không tắt CSRF cho toàn ứng dụng**. Demo chỉ có GET nghiệp vụ; nếu thêm POST/PUT/DELETE cần thiết kế và kiểm thử CSRF phù hợp với loại credential và client.
9. **Role ADMIN** được Spring Security kiểm tra tương ứng authority ROLE_ADMIN khi dùng hasRole("ADMIN").
10. Mật khẩu demo được đưa vào InMemoryUserDetailsManager qua PasswordEncoder; ứng dụng thật phải dùng kho danh tính và vòng đời secret phù hợp.

### 9.6. Chạy và quan sát bằng curl

Từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác chạy (PowerShell dùng curl.exe; Linux/macOS có thể thay bằng curl):

~~~powershell
curl.exe -i http://localhost:8080/
curl.exe -i http://localhost:8080/user
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u reader:demo http://localhost:8080/api/me
curl.exe -i -u reader:demo http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

**Kết quả HTTP dự kiến:**

| Request | Status | Điểm quan sát |
| --- | --- | --- |
| GET / | 200 | Body home, route web công khai. |
| GET /user ẩn danh | 302 | Header Location tới /login do form-login entry point. |
| GET /api/public | 200 | Body api-public. |
| GET /api/me ẩn danh | 401 | HTTP Basic authentication challenge. |
| GET /api/me với reader/demo | 200 | Body api:reader. |
| GET /api/admin với reader/demo | 403 | User có danh tính nhưng thiếu ROLE_ADMIN. |
| GET /api/admin với admin/demo-admin | 200 | Body api-admin. |

Header chi tiết như Date, Cache-Control, Set-Cookie, Location có thể thay đổi theo Servlet container và phiên bản. Đọc **status và nguyên nhân** thay vì phụ thuộc byte-for-byte vào mọi header.

Để quan sát **AuthenticationSuccessHandler / AuthenticationFailureHandler** của form login, mở http://localhost:8080/user trên browser. Bạn sẽ được chuyển tới /login. Gửi **reader / demo** qua form: trình duyệt chuyển tới /user và thấy **web:reader**. Thử mật khẩu sai: browser được đưa về **/login?error** theo failure handler. Sau khi đăng nhập bằng reader, mở /admin sẽ bị **403**. Khi thử với tài khoản admin/demo-admin, /admin sẽ trả body web-admin.

Khi gửi login thủ công bằng curl, phải xử lý cookie jar và CSRF token thật của trang login; nếu bỏ qua bước này, kết quả 403 do CSRF **không phải** bằng chứng failure handler sai.

## 10. Viết kiểm thử xác nhận đúng handler theo tình huống

Spring Security Test hỗ trợ MockMvc để kiểm tra các phản hồi khác nhau. File test bên dưới đi cùng dự án ví dụ ở trên, dùng dependencies test đã khai báo trong pom.xml.

**SecurityHandlersTests.java**:

~~~java
package com.example.handlers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHandlersTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousWebUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/user"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void anonymousApiClientGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicUserCanReadOwnApiIdentity() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void basicUserCannotCallAdminApi() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("reader", "demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void successfulFormLoginRedirectsToUser() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "demo"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user"));
    }

    @Test
    void failedFormLoginRedirectsToErrorPage() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void loginWithoutCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "reader")
                .param("password", "demo"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test chứng minh:

- Ẩn danh đi vào web được chuyển hướng tới login; API lại trả 401.
- Basic user đúng được xác thực, role USER vẫn không vào được admin API.
- Login thành công đi qua success handler; login sai password đi qua failure handler.
- Login request thiếu CSRF token bị chặn, cho thấy **lỗi trước authentication filter** không nhất thiết dùng failure handler.

**Lưu ý về redirect URL trong MockMvc:** kiểm thử ở trên kỳ vọng redirect tuyệt đối dạng http://localhost/login theo hành vi LoginUrlAuthenticationEntryPoint trong cấu hình mặc định. Nếu cấu hình proxy/servlet context path hoặc thay đổi cách xây Location, nên dùng assert phù hợp với URL mà ứng dụng xác định; không cố định giả định ở mọi môi trường.

Một test 403 còn cần kiểm **không có side effect trái phép** nếu endpoint thực hiện ghi DB, chuyển tiền hoặc publish message. Handler trả status đúng không đủ để chứng minh logic phân quyền không bị bỏ qua.

## 11. Khi API cần JSON thay vì redirect

Website dùng form login thường hợp lý khi trả redirect tới trang đăng nhập. REST API được gọi bằng fetch, curl hoặc backend service thường cần status 401/403 và JSON ngắn gọn để client xử lý có kiểm soát.

Một AuthenticationEntryPoint tùy biến có thể trả JSON 401 theo hợp đồng API:

~~~java
.exceptionHandling(ex -> ex.authenticationEntryPoint(
    (request, response, authenticationException) -> {
        response.setStatus(401);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"unauthenticated\"}");
    }
))
~~~

Mảnh code này là **minh họa trong SecurityFilterChain riêng dành cho API**; không áp trực tiếp vào demo HTTP Basic ở mục 9 nếu muốn giữ WWW-Authenticate challenge. Với Basic/Bearer, entry point chuẩn xử lý challenge và protocol-specific headers thường phù hợp hơn; việc ghi JSON cần được thiết kế sao cho vẫn giữ ngữ nghĩa xác thực đúng.

Tương tự, một AccessDeniedHandler tùy biến có thể trả JSON 403:

~~~java
.exceptionHandling(ex -> ex.accessDeniedHandler(
    (request, response, denied) -> {
        response.setStatus(403);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"forbidden\"}");
    }
))
~~~

Đây cũng là **mảnh code minh họa**, không được chèn đồng thời vào một chain có cấu hình exceptionHandling khác mà không hợp nhất cấu hình. Phản hồi production nên có cơ chế mã hóa JSON và headers nhất quán; tránh đưa trực tiếp thông tin từ ngoại lệ hoặc input không tin cậy vào body.

Trong Spring Boot, xử lý exception ở **@ControllerAdvice** phù hợp cho lỗi phát sinh trong Controller/Service, nhưng các request bị chặn bởi security filter trước Controller **không nhất thiết** đi tới ControllerAdvice. Để tùy chỉnh 401/403 của security filter, dùng entry point/denied handler đúng vị trí.

## 12. Phân biệt luồng session, Basic, Bearer và remember-me

### 12.1. Form login + session

- Thường có trang /login, cookie phiên và redirect.
- Sau một form login thành công, Spring Security có thể cập nhật session/security context theo cấu hình.
- AuthenticationSuccessHandler dùng để điều hướng sau login.
- AuthenticationFailureHandler dùng khi thử login thất bại.
- RequestCache có thể lưu URL cần truy cập trước đăng nhập.
- CSRF protection đặc biệt quan trọng ở form POST và request thay đổi trạng thái có cookie/session.

### 12.2. HTTP Basic

- Mỗi request có thể mang Authorization: Basic ...; credential phải được kiểm tra qua provider và password encoder phù hợp.
- Thường dùng 401 + WWW-Authenticate để challenge; sai credential thường được xử lý bởi Basic filter/entry point.
- Không mặc nhiên gọi form login success/failure handlers.
- Basic chỉ Base64 credential, cần HTTPS trên mạng thực tế.
- Không nên cho rằng HTTP Basic đồng nghĩa an toàn trước CSRF; trình duyệt có thể tự gửi credential đã lưu tùy bối cảnh. Quyết định CSRF phải theo cách client thực sự xác thực và gửi request.

### 12.3. Bearer token / Resource Server

- Client gửi Authorization: Bearer ...; Resource Server xác minh token qua cấu hình tin cậy, gồm chữ ký hoặc introspection và các điều kiện cần thiết.
- Khi thiếu token hoặc token không hợp lệ, entry point của Bearer thường trả 401 với challenge phù hợp.
- Khi đã xác thực nhưng thiếu scope/quyền, handler cho access denied thường trả 403 và có thể dùng header Bearer tương ứng.
- OAuth2 login interactive khác với Resource Server chỉ xác thực Bearer trên API; không gộp mọi cơ chế dưới “formLogin handlers”.

### 12.4. Remember-me và mức xác thực

Một số ứng dụng web có remember-me authentication. Tùy chính sách, Spring Security có thể xem mức xác thực này **chưa đủ cho thao tác đặc biệt nhạy cảm**, nên chuyển lại quy trình login đầy đủ. Khi debug yêu cầu đăng nhập lại, đừng chỉ nhìn Authentication không null; cần xem trust level và chính sách cụ thể.

## 13. Những sai lầm thường gặp

1. **Dùng AuthenticationFailureHandler để bắt 401 từ mọi endpoint.** Failure handler dành cho luồng xác thực cụ thể như form login. Request bảo vệ khi ẩn danh thường được xử lý qua AuthenticationEntryPoint.
2. **Cho rằng AuthenticationSuccessHandler chạy sau mỗi GET có token đúng.** Nó chạy ở những luồng authentication filter được thiết kế để gọi handler, không phải bộ đếm tất cả request đã xác thực.
3. **Nhầm 403 với mật khẩu sai.** Sai credential có thể trả 401 hoặc redirect /login?error; thiếu role hay CSRF có thể trả 403.
4. **Trả 200 JSON báo lỗi login.** HTTP status nên phản ánh đúng kết quả; success/failure handler quyết định response phù hợp client.
5. **Đổi BasicAuthenticationEntryPoint thành trang HTML login cho API backend.** Client có thể nhận 302/HTML không mong đợi; phân tách SecurityFilterChain và entry point theo loại client.
6. **Tự viết handler rồi quên SecurityContext/session.** Redirect sau login không thay thế cơ chế lưu/khôi phục SecurityContext, bảo vệ session fixation hoặc kiểm thử đăng nhập tiếp theo.
7. **Để AuthenticationEntryPoint redirect tới URL do client tùy ý cung cấp.** Có thể gây open redirect; cần allowlist/validate đích khi hỗ trợ returnUrl.
8. **Không phân biệt lỗi security filter với ControllerAdvice.** @ControllerAdvice không tự nhận mọi lỗi từ filter chain.
9. **Tắt CSRF để form login POST bằng curl dễ hơn.** Thiếu CSRF token là tình huống phải hiểu đúng; đừng tắt cơ chế phòng vệ chỉ để khớp test.
10. **Bảo vệ URL nhưng bỏ quyền đối tượng.** User được vào /api/orders/** vẫn không có nghĩa được đọc/sửa mọi đơn; Service phải kiểm tra owner/tenant.
11. **Xem ExceptionTranslationFilter như nơi xử lý mọi AuthenticationException.** Authentication filter ở trước có thể tự gọi failure handler hoặc entry point; vị trí trong chain quan trọng.
12. **Cấu hình nhiều SecurityFilterChain thiếu fallback hoặc sai thứ tự.** Một request có thể khớp chain khác mong đợi; kiểm tra securityMatcher, thứ tự và endpoint quản trị.
13. **Đưa exception message vào response/log không kiểm soát.** Tránh lộ username tồn tại, password, token, stack trace hoặc thông tin policy nhạy cảm.
14. **Chỉ assert status mà không kiểm side effects.** Trường hợp bị từ chối phải không ghi dữ liệu hoặc phát sự kiện trái phép.

## 14. Phương pháp debug một response 302, 401 hoặc 403

Bắt đầu từ request cụ thể và đi theo các câu hỏi:

**1. Request đang vào SecurityFilterChain nào?** Xác định method, path, HTTP host, gateway rewrite và securityMatcher có khớp chain mình mong muốn hay không.

**2. Có đang login hay truy cập resource?** POST /login với credential khác GET /admin ẩn danh. Đặt câu hỏi liệu failure handler hay entry point phải chịu trách nhiệm.

**3. Credential đã được xử lý chưa?** HTTP Basic/Bearer có Authorization đúng scheme không? Form login có CSRF token, username/password params và session cần thiết không?

**4. Authentication hiện có là gì?** Principal có được xác thực, có role/scope tương ứng không? Không tin dữ liệu do client tự cung cấp như X-Role.

**5. Exception xuất hiện ở filter nào?** Sai credential trong UsernamePasswordAuthenticationFilter, thiếu token CSRF, hay AccessDeniedException do authorization? Chúng có đường xử lý khác nhau.

**6. HTTP response đúng cho client chưa?** Browser có thể cần 302 tới /login; service API cần 401 challenge; user đã xác thực mà thiếu role thường 403. Kiểm tra WWW-Authenticate, Location, Content-Type và body.

**7. Có redirect hoặc saved request bất ngờ không?** Một response 200 cuối cùng có thể là HTML trang login sau redirect 302, không phải resource ban đầu.

**8. Có lỗi bảo mật nghiệp vụ không?** Dù handler đã trả status đúng, xác minh không có DB update, audit sai, phát message hoặc rò dữ liệu khi bị từ chối.

Có thể bật logging có kiểm soát cho quá trình thử nghiệm tại môi trường local, nhưng phải tránh log credential, token, session cookie hoặc thông tin cá nhân. Không nên để mức debug nhạy cảm trên production chỉ để tìm nhanh một nhánh filter.

## 15. Bài tập tự đánh giá

1. Khách chưa login gọi GET /user. Thành phần nào thường bắt đầu login, và vì sao **AuthenticationFailureHandler** chưa phù hợp? **Gợi ý:** chưa có thử nhập sai mật khẩu; cần AuthenticationEntryPoint.
2. Khách POST /login với password sai nhưng có CSRF token hợp lệ. Handler nào thường xử lý? **Gợi ý:** AuthenticationFailureHandler.
3. User hợp lệ vào GET /admin nhưng thiếu ROLE_ADMIN. Handler nào thường xử lý 403? **Gợi ý:** AccessDeniedHandler sau authorization từ chối.
4. API HTTP Basic trả 401 cho request không Authorization. Có bắt buộc gọi AuthenticationFailureHandler hay không? **Gợi ý:** không; Basic entry point/challenge.
5. POST /login bị 403 trước khi kiểm mật khẩu. Hãy nêu một nguyên nhân và vị trí có thể chặn. **Gợi ý:** CsrfFilter.
6. Sau form login thành công, ứng dụng muốn quay về URL trước khi login. Component nào hỗ trợ, và cần lưu ý điều gì? **Gợi ý:** RequestCache và SavedRequestAwareAuthenticationSuccessHandler; kiểm soát redirect.
7. Một handler trả 403 nhưng Service đã ghi DB từ trước. Điều đó có an toàn không? **Gợi ý:** không; phải ngăn side effect trước khi bị từ chối.
8. Vì sao một SecurityFilterChain dùng form login cho web và một chain dùng Basic/Bearer cho API dễ hiểu hơn khi hai loại client có kỳ vọng response khác nhau? **Gợi ý:** entry point và request matcher tách biệt.

### Checklist ghi nhớ

- **SuccessHandler:** sau login thành công trong luồng hỗ trợ handler.
- **FailureHandler:** sau thất bại của một lần thử login cụ thể.
- **EntryPoint:** khởi đầu/challenge xác thực khi cần, hoặc trong một số filter khi credential không hợp lệ.
- **AccessDeniedHandler:** xử lý access denied đối với principal phù hợp, thường trả 403.
- **ExceptionTranslationFilter:** dịch một số exception downstream thành hành vi HTTP bằng entry point/denied handler.
- **SecurityFilterChain:** quyết định tập filter và chính sách áp dụng cho request; cần biết chain nào thực sự match.

## Kết luận

Trong Spring Security, **đăng nhập thành công**, **đăng nhập thất bại**, **chưa đăng nhập nhưng cần truy cập tài nguyên**, và **đã đăng nhập nhưng thiếu quyền** là bốn tình huống khác nhau. AuthenticationSuccessHandler, AuthenticationFailureHandler, AuthenticationEntryPoint và AccessDeniedHandler phản hồi ở các thời điểm khác nhau; ExceptionTranslationFilter giúp dịch ngoại lệ xác thực/phân quyền downstream thành hành vi HTTP. Khi hiểu rõ các luồng đó, có thể thiết kế web form login và REST API phản hồi đúng cho từng loại client, cấu hình handler ở đúng SecurityFilterChain và kiểm thử chính xác cả status lẫn side effects.
