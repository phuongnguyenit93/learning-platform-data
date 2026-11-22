# Phiên làm việc là gì và vì sao HTTP không tự giữ trạng thái đăng nhập

> **Module:** Spring Security – fundamentals  
> **Nhóm kiến thức:** Phiên và cookie  
> **Đề bài:** Phiên làm việc là gì và vì sao HTTP không tự giữ trạng thái đăng nhập

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác ý nghĩa **HTTP là giao thức không có trạng thái ứng dụng giữa các request** (*stateless*).
2. Mô tả cách **session**, **session ID**, **cookie**, **SecurityContext** và **Authentication** phối hợp để trình duyệt có cảm giác “đăng nhập một lần, dùng nhiều trang”.
3. Đọc được trao đổi HTTP liên quan đến `Set-Cookie` và `Cookie`, phân biệt thông tin nào nằm tại browser và thông tin nào nằm phía server.
4. Dùng `HttpSession` trên Servlet stack và hiểu khi nào Spring Security lưu hoặc khôi phục danh tính từ session.
5. Tạo ứng dụng Java 17+ với Spring Boot, form login, cookie session, endpoint được bảo vệ, logout và bài kiểm thử xác thực hai request liên tiếp.
6. Phân biệt session-based login, HTTP Basic, bearer token/JWT và các chính sách `SessionCreationPolicy`.
7. Tránh các lỗi phổ biến: nhầm cookie với session, cho rằng cookie tồn tại đồng nghĩa đã xác thực, tắt CSRF, dùng session ID trong URL, bỏ qua timeout hoặc session fixation.

## 2. HTTP “không giữ trạng thái” có nghĩa là gì?

HTTP trao đổi theo cặp **request → response**. Một request có method, target URL, headers và có thể có body; một response có status, headers và body. **Theo bản chất giao thức, request thứ hai không tự động kế thừa “ai đã đăng nhập” từ request trước.**

Ví dụ hai request độc lập:

~~~http
GET /profile HTTP/1.1
Host: example.test
~~~

~~~http
GET /profile HTTP/1.1
Host: example.test
~~~

Nếu chúng không mang credentials hay dấu hiệu nhận diện nào khác, server không có căn cứ từ chính hai request này để kết luận chúng đến từ cùng một tài khoản. Server có thể nhớ dữ liệu trong RAM hoặc database, nhưng cần **cách liên kết một request mới với dữ liệu đó**.

Điều cần phân biệt:

- **Stateless ở tầng HTTP** không có nghĩa server không được lưu dữ liệu.
- **Keep-Alive / HTTP/2 / HTTP/3** có thể tái sử dụng kết nối hoặc multiplex nhiều stream; điều này không mặc nhiên tạo ra phiên đăng nhập cho một người dùng. Kết nối mạng không phải danh tính ứng dụng.
- Hai request đến từ cùng địa chỉ IP không chứng minh cùng người dùng: NAT, proxy, Wi-Fi công cộng, mobile network và đổi IP đều làm IP không phù hợp để định danh session.
- `User-Agent`, `Referer`, địa chỉ IP hoặc một header bất kỳ do client tự gửi đều không đủ để xác thực.
- Server vẫn có thể dùng cookie, token, URL parameter hoặc cơ chế khác để *xây dựng trạng thái ứng dụng trên HTTP*. Với đăng nhập web truyền thống, cookie + server session là cách quen thuộc.

**Câu kết luận cốt lõi:** HTTP cung cấp cơ chế gửi thông điệp; còn việc “nhớ rằng request này thuộc Alice” là trách nhiệm của **cơ chế quản lý phiên/xác thực ở tầng ứng dụng**.

## 3. Session, cookie và session ID khác nhau thế nào?

Một hệ thống session-based login truyền thống thường gồm:

| Khái niệm | Vị trí chủ yếu | Chức năng |
| --- | --- | --- |
| **HTTP request** | Trên đường client → server | Gửi hành động hiện tại; mỗi request được xử lý độc lập về ngữ nghĩa HTTP |
| **HTTP response** | Server → client | Trả kết quả, có thể đặt cookie |
| **Cookie** | Browser lưu và gửi theo quy tắc domain/path/SameSite/Secure | Vật mang một giá trị như session ID qua các request |
| **Session ID** | Trong cookie của browser và khóa tra cứu phía server | Định danh opaque một session; **không phải password hay object chứa toàn bộ user** |
| **Server-side session** | RAM, session store, cache hoặc database phía server | Lưu dữ liệu liên quan phiên, ví dụ `SecurityContext`, dữ liệu tạm |
| **SecurityContext** | Trong xử lý request và có thể được persist giữa requests | Chứa `Authentication` của Spring Security |
| **Authentication** | Đối tượng Spring Security | Principal, authorities và trạng thái authentication |
| **Session timeout** | Chính sách server | Quyết định bao lâu không hoạt động thì session hết hiệu lực |

Ở cấu hình Servlet thường gặp, cookie có tên **`JSESSIONID`**. Khi dùng Spring Session hoặc cơ chế khác, tên cookie có thể là **`SESSION`** hay tên được cấu hình; đừng viết code phụ thuộc cứng vào một tên nếu hạ tầng có thể thay đổi.

Ví dụ giản lược:

~~~text
Browser:
  Cookie: JSESSIONID=s_8b7f...   <-- chỉ chứa mã định danh

Server:
  sessionStore["s_8b7f..."] = {
    SecurityContext: Authentication(principal="alice",
                                    authorities=["ROLE_USER"]),
    otherSessionData: ...
  }
~~~

Chuỗi trên là dữ liệu minh họa, **không phải định dạng nội bộ cố định** của Spring Security. Session ID thực phải được tạo ngẫu nhiên và đủ khó đoán bởi container/session infrastructure. Không tự tạo ID kiểu `userId=42`, `alice-2026` hay chuỗi tăng dần.

### Cookie không phải session

Cookie là cơ chế phía client để mang dữ liệu qua request; session là **ngữ cảnh phía server** gắn với session ID. Browser có thể có cookie không liên quan đến login (ngôn ngữ, theme, giỏ hàng), và server có thể tạo session cho người dùng chưa đăng nhập (ví dụ để lưu saved request hoặc CSRF token). Vì vậy:

**Có cookie `JSESSIONID` không đồng nghĩa đã đăng nhập.** Phải xem session tương ứng có `Authentication` hợp lệ hay không.

Ngược lại, ứng dụng có thể xác thực bằng bearer token mà không dùng session cookie; do đó **đã đăng nhập không nhất thiết phải có `JSESSIONID`**.

## 4. Từng bước: browser đăng nhập và “được nhớ” qua request sau

Giả sử người dùng mở `https://app.example.test/account`, ứng dụng dùng form login và session.

### Bước 1 — Request đầu tiên chưa có danh tính

~~~http
GET /account HTTP/1.1
Host: app.example.test
~~~

Server cần authentication, nên thường trả redirect tới trang login:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Ứng dụng có thể tạo session **ngay trước lúc login thành công**, ví dụ để lưu URL được yêu cầu hoặc CSRF token. Việc có `Set-Cookie` lúc này không chứng minh người dùng đã đăng nhập.

### Bước 2 — Người dùng nhập credentials

Browser nhận form login, gửi username, password cùng CSRF token do ứng dụng cấp:

~~~http
POST /login HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=prelogin_id

username=alice&password=example-password&_csrf=example-csrf-token
~~~

Đây là HTTP **minh họa, không dùng token/password thật**. Spring Security chuyển credentials tới authentication mechanism phù hợp (ví dụ `AuthenticationManager` và `UserDetailsService`), xác minh thành công và tạo `Authentication`.

### Bước 3 — Gắn authentication với session

Trong một cấu hình session-based, server lưu `SecurityContext` thông qua `SecurityContextRepository`; dữ liệu liên quan đến phiên được lưu/tra cứu bằng session ID.

Sau authentication, Spring Security có cơ chế **session fixation protection**, thường đổi session ID. Server gửi cookie cập nhật:

~~~http
HTTP/1.1 302 Found
Location: /account
Set-Cookie: JSESSIONID=postlogin_id; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Cookie trên là một **ví dụ triển khai HTTPS đã cấu hình an toàn**, không cam kết mọi môi trường mặc định phát ra đúng bốn thuộc tính này. Tên cookie, đường dẫn, `Secure` và `SameSite` phụ thuộc container, reverse proxy và cấu hình.

### Bước 4 — Request tiếp theo mang cùng session ID

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=postlogin_id
~~~

Browser gửi cookie theo quy tắc cookie; server:

1. Tách session ID từ request.
2. Tìm session tương ứng trong kho phiên.
3. Khôi phục `SecurityContext`/`Authentication`.
4. Kiểm tra người dùng có đủ quyền vào `/account`.
5. Trả dữ liệu hoặc lỗi phù hợp.
6. Kết thúc request, dọn security context gắn với luồng xử lý theo cơ chế framework.

Người dùng cảm thấy mình **vẫn đăng nhập**, nhưng thật ra danh tính đã được **khôi phục cho từng request**, không phải HTTP tự nhớ.

### Bước 5 — Logout hoặc hết hạn

Khi logout hợp lệ, server có thể hủy session, xóa `SecurityContext` và yêu cầu browser bỏ cookie. Khi session timeout, bản ghi server không còn hợp lệ dù browser có thể vẫn giữ cookie cũ. Request sau phải đăng nhập lại.

Sơ đồ tổng thể:

~~~text
Browser                     Spring Security                   Session Store
  | GET /private                    |                                |
  |-------------------------------->|                                |
  | 302 /login                      |                                |
  |<--------------------------------|                                |
  | GET /login + form/CSRF          |------ (optional session) ------>|
  |<--------------------------------|                                |
  | POST /login credentials+CSRF    |                                |
  |-------------------------------->| verify password                |
  |                                 | store SecurityContext -------->|
  | 302 + Set-Cookie: JSESSIONID    |                                |
  |<--------------------------------|                                |
  | GET /private + Cookie           |                                |
  |-------------------------------->| lookup session ---------------->|
  |                                 |<-------- SecurityContext -------|
  | 200 protected content           | authorize                      |
  |<--------------------------------|                                |
  | POST /logout + CSRF + Cookie    |                                |
  |-------------------------------->| invalidate session ----------->|
  | 302 login/logout success        |                                |
  |<--------------------------------|                                |
~~~

Đây là sơ đồ luồng tổng quát, không biểu diễn chính xác mọi filter/redirect/response ở từng phiên bản Spring Security.

## 5. Hiểu Set-Cookie và Cookie ở mức HTTP

### Set-Cookie: server yêu cầu browser lưu cookie

~~~http
Set-Cookie: JSESSIONID=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **`JSESSIONID=opaque-value`:** tên và giá trị. Giá trị là một **bearer credential**; ai chiếm được ID còn hiệu lực có thể có nguy cơ chiếm session.
- **`Path=/`:** phạm vi URL path được browser dùng để quyết định gửi cookie. Path không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng origin.
- **`Secure`:** browser chỉ gửi cookie qua kết nối an toàn (với một số khác biệt/ngoại lệ khi chạy trên localhost). Production nên sử dụng HTTPS end-to-end.
- **`HttpOnly`:** JavaScript từ trang không đọc được cookie bằng `document.cookie`. Nó giảm một loại rủi ro đánh cắp session bởi XSS, nhưng không khiến ứng dụng miễn nhiễm với XSS.
- **`SameSite=Lax`:** hạn chế một số tình huống gửi cookie từ site khác, hỗ trợ chống CSRF. `SameSite` không thay cho CSRF token trong mọi bối cảnh.

Các thuộc tính khác:

- **`Domain`:** nếu không đặt, cookie thường là host-only; nên tránh mở rộng sang subdomain không cần thiết.
- **`Max-Age` và `Expires`:** kiểm soát vòng đời cookie phía browser. Không phải chính sách timeout của session server.
- **`SameSite=Strict`:** hạn chế chặt hơn, nhưng có thể làm trải nghiệm điều hướng từ trang ngoài không như mong đợi.
- **`SameSite=None; Secure`:** cần cho một số trường hợp thực sự cross-site; phải đánh giá CSRF và chính sách trình duyệt.
- **Prefix `__Host-`:** có quy tắc tên/`Secure`/`Path=/`/không `Domain` hỗ trợ cookie host-only chặt hơn; muốn đổi tên session cookie phải cấu hình hạ tầng tương thích.

### Cookie: browser tự gửi lại trong request

~~~http
Cookie: JSESSIONID=opaque-value
~~~

Browser có thể lưu nhiều cookie cho một site. Khi request phù hợp chính sách cookie, nó gửi đúng cookies tương ứng; JavaScript **không bắt buộc** phải tự thêm header này. Vì gửi cookie thường tự động nên ứng dụng session-based cần chú ý CSRF.

**Điểm bảo mật:** HTTP header/cookie do client gửi đến đều có thể bị client tùy biến khi thử nghiệm. Server không nên tin bất kỳ giá trị cookie nào theo nghĩa “user ID này là thật” nếu chưa tra đúng session store và xác minh trạng thái tương ứng.

## 6. Vì sao HTTP không gắn sẵn phiên với IP hay TCP connection?

Một trực giác sai là “server nhìn thấy cùng kết nối nên biết cùng user”.

Thực tế:

- Browser có thể gửi nhiều request bằng nhiều kết nối; HTTP/2 cho phép multiplex, nhưng connection reuse không phải tiêu chuẩn định danh login.
- Reverse proxy có thể gom/chia connections; các user khác nhau có thể đi qua cùng proxy/IP.
- Mobile user có thể đổi mạng, IP, thiết bị hoặc mở phiên riêng tư.
- Một trình duyệt có thể dùng nhiều tài khoản ở các profile khác nhau dù chung IP.
- Các request được triển khai qua load balancer có thể rơi vào các instance server khác nhau.

Cookie session ID giải quyết vấn đề định danh request trong phạm vi policy, trong khi session store giúp khôi phục dữ liệu phía server. Không thay thế bằng IP, user agent hay thời gian request.

## 7. HttpSession của Servlet là gì?

Với Servlet API, `jakarta.servlet.http.HttpSession` biểu diễn session trên phía server. Những phương thức cần biết:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `request.getSession()` | Lấy session hiện có hoặc **tạo mới** nếu chưa có | Có thể vô ý tạo session |
| `request.getSession(false)` | Lấy session hiện có, hoặc trả `null` | Phù hợp khi chỉ cần kiểm tra, không tự tạo |
| `session.getId()` | Lấy session identifier | Không log/hiển thị trong API production |
| `session.setAttribute(key, value)` | Lưu dữ liệu trong session | Tránh PII, object lớn hoặc đối tượng không cần thiết |
| `session.getAttribute(key)` | Đọc dữ liệu session | Kiểm tra kiểu/null phù hợp |
| `session.getMaxInactiveInterval()` | Xem thời gian bất hoạt tối đa (giây) | Idle timeout, không nhất thiết absolute lifetime |
| `session.invalidate()` | Hủy session | Không thay thế toàn bộ logout flow của Spring Security |
| `request.changeSessionId()` | Thay ID session hiện hành | Cơ chế quan trọng khi chống session fixation |

Ví dụ minh họa Servlet (fragment trong controller):

~~~java
@GetMapping("/debug/session-present")
public boolean sessionPresent(HttpServletRequest request) {
    return request.getSession(false) != null;
}
~~~

Đoạn trên cần annotation/Servlet import phù hợp và **không nên mở một debug endpoint tiết lộ nội bộ ở production**. Điểm chính là dùng `getSession(false)` khi không muốn việc quan sát làm phát sinh session.

### Lưu ý session và authentication là hai thứ khác nhau

Tạo `HttpSession` bằng `request.getSession()` không tự xác thực người dùng. Một session chưa login có thể lưu giỏ hàng tạm, CSRF token hoặc saved request. Ngược lại, Spring Security không nhất thiết phải dùng `HttpSession` nếu sử dụng bearer token và cấu hình stateless.

Bên trong một request của Spring MVC, `SecurityContextHolder` giúp code lấy authentication đang hoạt động. **Nó không phải cơ chế lưu lâu dài giữa mọi request.** Với chiến lược Servlet thường gặp, context được gắn với xử lý hiện tại (thường là `ThreadLocal`); repository/session đảm nhiệm phần persistence khi cần.

## 8. Spring Security ghi nhớ người đăng nhập như thế nào?

Các thành phần chính:

**`Authentication`** là kết quả xác thực, có principal (ví dụ username), authorities (role/permission), flags. Không nên lưu password thô trong session.

**`SecurityContext`** bọc `Authentication`.

**`SecurityContextHolder`** cho code hiện tại truy cập security context. Nếu chỉ set holder trong custom code rồi kết thúc request, điều đó **không đảm bảo** phiên sau đã được lưu.

**`SecurityContextRepository`** quyết định cách đọc/lưu security context giữa các giai đoạn xử lý:

- `HttpSessionSecurityContextRepository`: liên kết context với `HttpSession`.
- `RequestAttributeSecurityContextRepository`: bảo tồn context trong phạm vi request/dispatch (ví dụ error dispatch), không phải session cross-request.
- `DelegatingSecurityContextRepository`: ủy quyền cho nhiều repository. Đây là cách ghép thường thấy với session + request attribute trên Servlet stack.
- `NullSecurityContextRepository`: không persist context; hữu ích khi chủ ý stateless.

**`SecurityContextHolderFilter`** tải context từ repository để request dùng; trong Spring Security 6+, mô hình phổ biến là **explicit save**: cơ chế login hoặc custom code cần lưu context qua repository nếu muốn các request sau đọc được. Đừng dùng thông tin từ bài viết thời Spring Security 5 và cho rằng thay `SecurityContextHolder` thì luôn tự lưu lại khi response kết thúc.

### Form login khác HTTP Basic thế nào?

- **Form login + session:** người dùng gửi credentials khi đăng nhập; sau khi thành công, server liên kết authentication với session; browser gửi session cookie cho các request tiếp theo.
- **HTTP Basic:** request gửi header `Authorization: Basic ...`. Đây là cơ chế thường xác thực lại theo mỗi request, không tự yêu cầu server lưu session để “nhớ login”. Browser có thể lưu credentials và tự gửi lại nên cảm giác giống session, nhưng cơ chế khác.
- **Bearer token:** mỗi request gửi `Authorization: Bearer ...`; server validate token theo chiến lược của hệ thống. Token có thể là JWT self-contained hoặc opaque token cần introspection. Không đồng nghĩa với servlet session.
- **Remember-me:** một cơ chế riêng có thể giúp tái xác thực qua cookie lâu dài sau khi session bình thường hết hạn; không nên nhầm với chính session ID.

### Nếu viết custom login thì sao?

Trong Spring Security 6+, khi tự xác thực bên ngoài các authentication filters đã tích hợp, bạn thường phải:

1. Xác thực credentials bằng `AuthenticationManager` hoặc service đáng tin.
2. Tạo `SecurityContext` có `Authentication`.
3. Đặt context trong holder phù hợp.
4. **Gọi `SecurityContextRepository.saveContext(context, request, response)`** nếu muốn persist giữa requests.
5. Xử lý session fixation, CSRF, logout, exception, credential handling.

Không bỏ bước lưu rồi kết luận session tự hoạt động. Ví dụ thực hành bên dưới **dùng form login có sẵn**, tránh tự triển khai login filter và các cơ chế bảo mật dễ sai.

## 9. Bốn SessionCreationPolicy và hiểu đúng “stateless”

Spring Security Servlet cung cấp `SessionCreationPolicy`:

| Policy | Ý nghĩa theo Spring Security | Trường hợp thường dùng |
| --- | --- | --- |
| `ALWAYS` | Luôn tạo `HttpSession` | Chỉ khi ứng dụng thực sự cần session chủ động |
| `IF_REQUIRED` | Tạo session khi cần | Form login truyền thống; thường là lựa chọn mặc định |
| `NEVER` | Spring Security không chủ động tạo session, nhưng có thể dùng session đã có | Khi session do phần khác tạo |
| `STATELESS` | Spring Security không tạo session và không dùng session để lấy `SecurityContext` | API bearer token/Basic được thiết kế stateless |

Code cấu hình (fragment bên trong `SecurityFilterChain`):

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
);
~~~

Với `STATELESS`, Spring Security sẽ không dùng `HttpSession` làm nơi lấy security context; **đừng hiểu thành một lời hứa rằng toàn bộ ứng dụng, MVC view hay thư viện khác không bao giờ gọi `getSession()`**.

Cũng đừng nghĩ chuyển từ `IF_REQUIRED` sang `STATELESS` sẽ tự tạo login bằng JWT. Chúng là **các cơ chế khác nhau**: cần cấu hình authentication filter, token issuer/validator, refresh/revocation và chính sách frontend riêng.

Trong ứng dụng có nhiều `SecurityFilterChain`, mỗi chain có matcher và chính sách tương ứng; cần test request đi vào đúng chain và policy thật sự có hiệu lực.

## 10. Demo đầy đủ: Java 17 + Spring Boot + session-based form login

Demo xây ứng dụng Spring MVC có:

- `/` và `/api/public` không yêu cầu login;
- `/api/me` cần authenticated user;
- trang `/login` được Spring Security tạo sẵn;
- form login lưu authentication trong session;
- `/logout` xử lý hủy session qua cơ chế mặc định;
- test login hai request, request không gửi cookie và CSRF.

**Môi trường:** Java 17+, Maven 3.9+, Spring Boot **3.5.7** (dòng Spring Security 6.5 tương ứng). Dùng HTTPS ở production; HTTP `localhost:8080` ở đây chỉ dành cho học tập.

Cấu trúc:

~~~text
session-demo/
  pom.xml
  src/main/java/com/example/sessiondemo/
    SessionDemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/sessiondemo/
    SessionFlowTests.java
~~~

### File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>session-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

### File SessionDemoApplication.java

~~~java
package com.example.sessiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
~~~

### File SecurityConfig.java

~~~java
package com.example.sessiondemo;

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

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/api/public", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout.logoutSuccessUrl("/?logout"))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("example456"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

**Giải thích:**

- `formLogin(Customizer.withDefaults())` kích hoạt trang/form login mặc định do Spring Security quản lý; không cần tự viết `POST /login`.
- `SessionCreationPolicy.IF_REQUIRED` cho phép tạo session để duy trì login khi cần.
- `csrf(Customizer.withDefaults())` giữ cơ chế CSRF mặc định cho phương thức thay đổi trạng thái như POST. **Không tắt CSRF chỉ để curl POST login thành công**.
- `logoutSuccessUrl("/?logout")` đưa người dùng về trang public khi logout. Với CSRF bật, logout nên gửi **POST /logout** với token hợp lệ; GET logout thường hiển thị trang xác nhận, không tương đương hoàn tất logout trong mọi cấu hình.
- Mật khẩu demo được hash bằng BCrypt khi ứng dụng khởi động. `demo123`/`example456` chỉ dùng localhost, tuyệt đối không hardcode credentials thật trong production.
- `/error` được permit để không che lỗi ứng dụng bằng một redirect login không cần thiết; production cần xét lại error response policy.
- Demo không có API thay đổi dữ liệu, nhưng vẫn bật CSRF để thực hành login/logout đúng.

### File DemoController.java

~~~java
package com.example.sessiondemo;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Welcome - open /api/me after signing in";
    }

    @GetMapping("/api/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(
            Authentication authentication,
            HttpServletRequest request
    ) {
        HttpSession session = request.getSession(false);

        return Map.of(
            "username", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "sessionPresent", session != null
        );
    }
}
~~~

`/api/me` được bảo vệ bởi `anyRequest().authenticated()`. Trong route thành công, method nhận `Authentication` của request hiện tại. `request.getSession(false)` **không tạo session mới**; nó chỉ minh họa cách xem session có tồn tại không. Không đưa session ID vào body hoặc log.

### File application.properties

~~~properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

`server.servlet.session.timeout=20m` cấu hình timeout nhàn rỗi ở phía server, không có nghĩa mọi cookie nhất định mất sau đúng 20 phút tính từ login. Dấu `http-only` giúp browser không phơi giá trị cookie cho `document.cookie`.

**Production qua HTTPS:** bật `Secure` cho session cookie (ví dụ cấu hình phù hợp với reverse proxy/TLS termination), đánh giá `Domain`/`Path`, HSTS và toàn bộ đường truyền. Trên demo chỉ chạy HTTP localhost nên **không ép `server.servlet.session.cookie.secure=true`** khiến cookie không được gửi trong một số trình duyệt/môi trường thử nghiệm; môi trường production phải đảm bảo HTTPS.

### Chạy

Trong thư mục `session-demo`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Nếu có Maven Wrapper từ Spring Initializr:

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

Trên Windows PowerShell dùng `.\mvnw.cmd test` và `.\mvnw.cmd spring-boot:run`.

Mở **`http://localhost:8080/api/me`** bằng browser chưa đăng nhập. Trình duyệt sẽ được chuyển đến trang login. Đăng nhập:

~~~text
username: alice
password: demo123
~~~

Sau đó mở lại `http://localhost:8080/api/me`. Body JSON kỳ vọng (thứ tự key không được đảm bảo):

~~~json
{
  "username": "alice",
  "authenticated": true,
  "sessionPresent": true
}
~~~

Đây là **kết quả mong đợi từ cấu hình demo**, không phải kết quả đã được thực thi trong tài liệu. Trên Spring MVC, kiểu trả về `Map` được Jackson chuyển thành JSON; thứ tự khóa có thể khác.

Mở tab mới trong **cùng browser profile** và gọi `/api/me`: browser thường gửi lại cùng session cookie nên user vẫn là `alice`. Dùng cửa sổ private/incognito khác hoặc xóa cookie để thử request không mang session ID: server không tự nhận ra người dùng và thường redirect tới `/login`.

### Quan sát bằng Developer Tools

1. Mở DevTools → **Network** → xem request `/login`, `/api/me`.
2. Trong response, tìm `Set-Cookie` và các thuộc tính thực tế. Cookie có thể được cấp trước login thành công vì CSRF/saved request; không gán mọi `Set-Cookie` là “đã login”.
3. Sau login, kiểm tra browser có gửi header `Cookie` chứa session ID cho `/api/me`.
4. Xem session ID có đổi khi authentication thành công hay không (session fixation protection).
5. Thử browser profile khác: request không có cookie hiện hành phải được xử lý như chưa login.
6. Logout qua form/màn hình bảo mật rồi thử gọi lại endpoint. Browser có thể vẫn giữ cookie cũ, nhưng session đã bị hủy sẽ không xác thực được.

**Bảo mật khi chụp ảnh/network log:** Không đưa session ID, CSRF token thật, password hoặc authorization token lên chat, tài liệu công khai hay hệ thống báo lỗi. Session ID là credential cần giữ bí mật.

## 11. Kiểm thử chương trình: session được dùng lại ở request thứ hai

Thêm file `src/test/java/com/example/sessiondemo/SessionFlowTests.java`:

~~~java
package com.example.sessiondemo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFlowTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void unauthenticatedRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginSessionAuthenticatesNextRequest() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession rawSession = result.getRequest().getSession(false);
        assertNotNull(rawSession);

        MockHttpSession session = (MockHttpSession) rawSession;

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.authenticated").value(true))
            .andExpect(jsonPath("$.sessionPresent").value(true));
    }

    @Test
    void loginDoesNotAuthenticateAnUnrelatedRequest() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection());

        // Không truyền session/cookie từ request login trước.
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

Lệnh:

~~~bash
mvn test
~~~

**Ý nghĩa hai test trung tâm:**

- `loginSessionAuthenticatesNextRequest`: request POST login thành công, lấy session từ request đó rồi **truyền cùng session** sang request GET mới; GET trả tài khoản Alice.
- `loginDoesNotAuthenticateAnUnrelatedRequest`: sau khi có một request login, một request khác **không mang session đã đăng nhập** vẫn bị chuyển đến login.
- `logoutWithoutCsrfIsRejected`: chứng minh bật CSRF khác với chỉ yêu cầu login.

`MockMvc` mô phỏng request phía server, không phải browser thật. Việc truyền `MockHttpSession` giữa các request trong test tương đương với việc browser gửi session cookie để server tra cùng session; bản thân MockMvc test không chứng minh browser thực tế đang phát `Set-Cookie` như thế nào. Muốn kiểm tra cookie attributes và proxy/HTTPS, cần test HTTP thực với browser hoặc client.

**QA code:** Đây là ứng dụng mẫu có đủ tệp và dependency để người học chạy với Java 17+ và Maven. Bài chỉ nêu hành vi dự kiến từ code; không tuyên bố đã build/run hoặc đã thấy dòng `BUILD SUCCESS` khi chưa thực thi.

## 12. Một mô phỏng Java thuần để phân biệt request và session

Nếu chưa cài Spring, chương trình Java 17 sau mô phỏng logic session bằng một `Map`. Đây **không phải HTTP server và không tạo session ID an toàn**, chỉ là mô hình nhỏ để quan sát vì sao request cần một mã liên kết.

Tạo file `TinySessionSimulation.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class TinySessionSimulation {
    private static final Map<String, String> SESSIONS = new HashMap<>();

    private static String handle(String sessionId) {
        if (sessionId == null) {
            return "anonymous";
        }
        return SESSIONS.getOrDefault(sessionId, "anonymous");
    }

    public static void main(String[] args) {
        System.out.println(handle(null));

        // Mô phỏng server tạo session cho Alice khi đăng nhập.
        String demoId = "demo-only-not-random";
        SESSIONS.put(demoId, "alice");

        System.out.println(handle(demoId));
        System.out.println(handle(null));

        // Mô phỏng logout: session ID cũ không còn map tới Alice.
        SESSIONS.remove(demoId);
        System.out.println(handle(demoId));
    }
}
~~~

Chạy:

~~~bash
javac TinySessionSimulation.java
java TinySessionSimulation
~~~

Stdout chính xác:

~~~text
anonymous
alice
anonymous
anonymous
~~~

Giải thích:

- Dòng đầu: request không có session ID ⇒ anonymous.
- Dòng thứ hai: request có ID được map tới Alice ⇒ khôi phục tên Alice.
- Dòng thứ ba: request mới không có ID ⇒ vẫn anonymous dù session của Alice đang tồn tại.
- Dòng thứ tư: ID cũ đã bị xóa khỏi map ⇒ anonymous.

Trong sản phẩm thật, không tự viết session store kiểu `HashMap` toàn cục không đồng bộ, và không dùng ID đoán được như `demo-only-not-random`. Dùng session handling đã được kiểm định của Servlet container/Spring Security/Spring Session.

## 13. Cookie hết hạn và session hết hạn không phải cùng một đồng hồ

Có ít nhất ba thời điểm khác nhau:

1. **Browser cookie lifetime:** session cookie không có `Max-Age`/`Expires` thường được coi là cookie phiên của trình duyệt, nhưng một số browser có tính năng *restore session* khiến cookie tồn tại lâu hơn bạn tưởng.
2. **Server session idle timeout:** ví dụ 20 phút không có request được tính là hoạt động; khi hết hạn, server invalidates/removes session. Thời gian idle do container/session store quản lý và được làm mới theo cơ chế riêng.
3. **Absolute login lifetime/security policy:** hệ thống có thể buộc đăng nhập lại sau một mốc tổng thể, kể cả user vẫn hoạt động; đây là chính sách cần thiết kế thêm, không tự có chỉ vì đặt idle timeout.

Ví dụ minh họa:

~~~text
10:00 login -> session valid
10:08 /api/me -> session được sử dụng
10:15 /api/me -> vẫn hợp lệ
10:36 request tiếp -> có thể đã timeout nếu idle timeout=20m,
                       vì từ 10:15 đến 10:36 là 21 phút
~~~

Ví dụ chỉ để hiểu ý tưởng, không phải cam kết thời điểm quét/xóa chính xác của mỗi container hay hạ tầng session.

Khi browser xóa cookie, server session có thể vẫn tồn tại đến timeout nếu chưa được invalidate. Khi server invalidates session, browser vẫn có thể gửi cookie cũ nhưng nó không còn được coi là session đã đăng nhập. **Logout phía server** và **xóa cookie phía browser** nên được xử lý phù hợp với nhau, không chỉ làm một thao tác.

## 14. Session fixation: tại sao cần thay session ID sau login?

Giả sử kẻ tấn công biết/ép nạn nhân dùng một session ID **trước khi nạn nhân đăng nhập**. Nếu ID không thay khi login, kẻ tấn công có thể dùng ID đó để truy cập phiên đã được xác thực sau đó. Đây là **session fixation**.

Để giảm nguy cơ, Spring Security hỗ trợ session fixation protection; ở Servlet hiện đại, chiến lược `changeSessionId` thường là mặc định. Điều đó giúp:

- Session trước và sau login không dùng mã định danh cũ như credential có thể tiếp tục bị tái sử dụng.
- Browser được cấp cookie mới sau khi authentication thành công.
- Người dùng không cần tự thao tác gì ngoài login.

Không nên tự disable session fixation protection. Tránh cấu hình đưa session ID vào query string như `/page;jsessionid=...` hoặc `?sessionId=...`, vì URL có thể bị lộ qua browser history, Referer, logs hoặc link chia sẻ. Cookie truyền qua HTTPS là cách thông dụng hơn.

**Session hijacking khác session fixation:** hijacking xảy ra khi session ID hiện tại bị đánh cắp/chiếm dụng. Fixation cố gắng buộc user dùng ID do attacker biết trước. Chống fixation không thay thế HTTPS, XSS mitigation và bảo vệ cookie.

## 15. CSRF: mặt trái của cookie tự được gửi

Vì browser tự đính kèm cookie khi request phù hợp, website khác có thể khiến browser của user gửi một request đến ứng dụng đang đăng nhập. Nếu đó là thao tác có side effect (chuyển tiền, xóa dữ liệu, đổi địa chỉ), server có nguy cơ làm theo **chỉ vì thấy session cookie hợp lệ**.

Đó là lý do CSRF protection quan trọng với session/cookie authentication.

Spring Security mặc định bảo vệ các HTTP method không an toàn như POST/PUT/PATCH/DELETE bằng CSRF token; token cần được gửi theo cách một site khác không tùy tiện tạo hợp lệ. Form login mặc định có hidden input `_csrf`. Một request POST không mang token đúng có thể bị trả **403** dù user đã đăng nhập.

Ví dụ form (minh họa, token do Spring Security cấp):

~~~html
<form method="post" action="/transfer">
  <input name="destination" value="account-2">
  <input type="hidden" name="_csrf" value="issued-csrf-token">
  <button type="submit">Transfer</button>
</form>
~~~

Đây **không phải implementation đủ của chuyển tiền**, chỉ minh họa vị trí token trong request. Với JSON SPA, cách gửi token có thể qua header như `X-CSRF-TOKEN`/`X-XSRF-TOKEN` theo cấu hình repository/handler. Spring Security 6 có deferred token và BREACH protection; đừng đơn giản sao chép lời khuyên cũ kiểu “đọc một cookie bất kỳ và gửi lại là luôn đủ”.

**SameSite giúp giảm rủi ro, nhưng không thay CSRF token trong mọi tình huống.** Cần xét cả same-site subdomains, top-level navigations, legacy browser và chính sách riêng của ứng dụng. HTTP `GET` phải là read-only theo ngữ nghĩa; không thực hiện mutation qua GET rồi hy vọng SameSite sẽ bảo vệ.

## 16. So sánh session-based và stateless token authentication

| Tiêu chí | Session-based (cookie session ID) | Bearer token / JWT API |
| --- | --- | --- |
| Dữ liệu mỗi request | Browser gửi session cookie | Client gửi token (thường trong `Authorization`) |
| Bằng chứng xác thực | Server tra session/context hợp lệ | Server validate bearer token hoặc introspect opaque token |
| Trạng thái server cho login | Thường có session store | Có thể không có server session, nhưng vẫn có revoke/cache/store khác |
| Logout tức thì | Có thể invalidate session phía server | Tùy token lifetime, revocation/refresh-token design |
| Rủi ro | Session hijacking, fixation, CSRF khi cookie tự gửi | Token theft/replay, refresh-token security; CSRF phụ thuộc cách lưu/gửi token |
| Trải nghiệm browser | Cookie tự gửi theo chính sách | Client thường phải chủ động gắn bearer header |
| Scale | Cần session store chia sẻ hoặc routing phù hợp | Có thể giảm session state, nhưng không miễn phí về security/operations |

**JWT không tự an toàn hơn session.** JWT có thể bị đánh cắp, có thời hạn, cần verify signature/issuer/audience và có bài toán revoke/refresh. Nếu lưu JWT trong cookie tự gửi thì vẫn cần đánh giá CSRF. Nếu lưu token trong localStorage, không có HttpOnly và phải đối mặt với rủi ro XSS đánh cắp token. Lựa chọn phụ thuộc threat model và kiến trúc.

Trong hệ thống dùng OAuth2/OIDC, việc đăng nhập tới identity provider và trạng thái session của ứng dụng cũng có thể là hai khái niệm khác nhau. Không trộn session của browser tại app với access token dùng gọi resource server hoặc session tại identity provider.

## 17. Những sai lầm thường gặp

| Nhận định hoặc cấu hình sai | Vấn đề thực sự | Cách hiểu/sửa |
| --- | --- | --- |
| “HTTP giữ login sau POST /login” | HTTP không tự gắn danh tính qua request | Session/cookie hoặc token được mang lại |
| “Cookie là server session” | Cookie nằm ở client, session state thường ở server | Phân biệt identifier và server-side record |
| “Có JSESSIONID nghĩa là login rồi” | Session có thể tồn tại trước authentication | Kiểm tra `Authentication` và policy |
| “Cùng IP ⇒ cùng tài khoản” | IP không phải identity | Dùng credentials/session/token hợp lệ |
| “HTTP/2 giữ TCP connection nên giữ login” | Connection reuse không phải app auth state | Tách transport và identity |
| “Đọc session thì cứ getSession()” | Có thể vô ý tạo session | Dùng `getSession(false)` khi chỉ đọc |
| “SecurityContextHolder tồn tại mãi” | Context theo xử lý request/thread, không phải persistence store | Dùng `SecurityContextRepository` phù hợp |
| “Custom login setContext là đủ” | Explicit-save flow có thể không persist | `saveContext(...)` và session strategy thích hợp |
| “Basic Auth không có JSESSIONID thì đã lỗi” | Basic gửi credentials từng request | Phân biệt cơ chế authentication |
| “STATELESS khiến cả app không tạo session” | Policy chủ yếu điều khiển Spring Security context/session | Kiểm tra cả MVC/container/library |
| “Cookie sống 30 ngày nên server session sống 30 ngày” | Cookie TTL khác server idle timeout | Thiết kế từng timeout riêng |
| “Xóa cookie là logout server ngay” | Server session có thể còn tồn tại | Invalidate session, clear context và cookie phù hợp |
| “Disable CSRF cho form login dễ test hơn” | Mở nguy cơ CSRF | Dùng CSRF token đúng cách |
| “SameSite thay hoàn toàn CSRF” | Coverage không đủ trong mọi mô hình | Defense in depth + CSRF token |
| “HttpOnly loại bỏ mọi XSS” | JS vẫn có thể thực hiện hành động trong trang nạn nhân | Chống XSS, CSP, output encoding, authz |
| “Secure cookie gửi được qua mọi HTTP” | Secure được thiết kế cho HTTPS; localhost có khác biệt | HTTPS ở production, test deployment thực |
| “Session ID trong URL tiện share” | ID có thể rò qua history/logs/referrer | Cookie secure, không URL rewriting |
| “Load balancer nào cũng thấy session” | In-memory session có thể chỉ tồn tại trên 1 instance | Spring Session/store chung hoặc strategy có chủ đích |
| “Đặt role trong cookie và tin giá trị” | Client sửa được giá trị | Chỉ tin state được ký/xác minh hoặc store server-side |
| “JWT là phiên làm việc giống JSESSIONID” | Token có semantics khác server session | Thiết kế persistence/revocation riêng |

## 18. Dùng session trong hệ thống nhiều server

Ở một ứng dụng chạy một instance Servlet server, session có thể nằm trong bộ nhớ JVM. Nhưng khi triển khai:

~~~text
Browser -- Cookie: JSESSIONID=abc
    |
Load Balancer
    +--> Instance A --> local session store có abc
    |
    +--> Instance B --> local session store không có abc
~~~

Nếu request 1 tới A, request 2 tới B mà session không được chia sẻ, user có thể gặp lỗi hoặc bị coi là chưa đăng nhập. Các hướng xử lý:

- **Shared session store**: dùng Spring Session (Redis/JDBC hay backend phù hợp) để nhiều instances đọc cùng một session; cần TTL và security cho store.
- **Sticky sessions**: load balancer định tuyến cố định theo client; đơn giản hơn trong một số môi trường nhưng kém bền vững khi instance chết hoặc scale, cần đánh giá.
- **Stateless authentication**: nếu phù hợp mô hình API, dùng bearer token được validate trên mỗi request; vẫn phải bảo vệ token và giải quyết revoke.

Không lưu object session quá lớn hoặc dữ liệu không thể serialize nếu backend session yêu cầu serialization. Hạn chế thông tin nhạy cảm, tránh lưu toàn bộ entity graph, password hoặc token dài hạn không cần thiết. Session có thể được tạo/cập nhật với tần suất cao nên tính chi phí network, TTL, cache và concurrency.

## 19. Quy trình kiểm tra sự cố “đăng nhập xong lại bị văng ra”

Theo thứ tự, kiểm tra:

1. **Request sau login có gửi Cookie không?** Dùng DevTools Network, xem domain/path/SameSite/Secure, redirect qua subdomain và browser privacy restrictions.
2. **Session ID có thay khi login không?** Có thể là bảo vệ session fixation; nếu đổi đúng cách thì browser phải cập nhật.
3. **Session server còn không?** Xem timeout, restart, invalidation, eviction, session store availability và clock/time skew liên quan.
4. **Có nhiều app instances không?** Test sticky routing hoặc shared store, nhưng không log session ID thô.
5. **Có đang dùng `STATELESS` hoặc `NullSecurityContextRepository` không?** Nếu mong session-based login mà cấu hình stateless, request sau có thể không khôi phục authentication.
6. **Custom login có lưu `SecurityContext` chưa?** Với Spring Security 6+ phải lưu đúng repository khi persistence là mong muốn.
7. **Có vô tình thay session ID/cookie ở reverse proxy không?** Xem HTTPS termination, forwarded headers, cookie rewrite, path mapping.
8. **POST bị 403 sau login?** Phân biệt thiếu quyền với thiếu/expired CSRF token; GET vẫn hoạt động là một gợi ý đáng kiểm tra.
9. **Mở browser profile khác có còn login?** Nếu không, đó có thể là hành vi đúng vì cookie không được chia sẻ.
10. **Logout có invalidate server session không?** Kiểm tra behavior của handler/CSRF và session store thay vì chỉ nhìn giao diện.

Không đưa password/session ID đầy đủ vào logs hoặc báo cáo lỗi. Nếu cần correlation, dùng request ID và token/session hash đã được thiết kế an toàn, không dùng chính session credential.

## 20. Bài tập thực hành

**Bài 1 – Hai request.** Một trình duyệt gọi `GET /private` hai lần, không có cookie hay header xác thực. HTTP có buộc server biết đó là cùng user không? Giải thích vì sao IP hoặc HTTP/2 connection không đủ.

**Bài 2 – Phân biệt giá trị.** Trong `Set-Cookie: JSESSIONID=abc; HttpOnly; Secure`, đâu là identifier và đâu là dữ liệu session chứa username/authorities? Vì sao không được sửa `abc` thành `username=admin` và tin rằng có quyền admin?

**Bài 3 – Quan sát trước login.** Bạn thấy `JSESSIONID` xuất hiện ngay khi mở `GET /login` chưa đăng nhập. Đây có chắc là bug không? Nêu ít nhất hai lý do framework có thể tạo session trước authentication.

**Bài 4 – Browser mới.** Sau khi Alice login ở cửa sổ thường, một cửa sổ private mở `/api/me` và bị redirect về `/login`. Giải thích dựa trên cookie jar.

**Bài 5 – Timeout.** Cookie vẫn tồn tại sau khi server session đã timeout. Request tiếp theo phải được xử lý thế nào để không xác thực nhầm người dùng? Vì sao cookie TTL và session idle timeout phải cấu hình/kiểm thử riêng?

**Bài 6 – Session hijacking.** Nếu attacker đánh cắp một session ID đang hợp lệ, những cơ chế nào giúp giảm nguy cơ? Phân biệt session fixation, CSRF, XSS và cookie Secure/HttpOnly/SameSite.

**Bài 7 – API stateless.** Cấu hình `SessionCreationPolicy.STATELESS` rồi vẫn thấy application tạo một `HttpSession` do code của bạn gọi `getSession()`. Điều này có mâu thuẫn hoàn toàn với ý nghĩa policy không? Sửa thiết kế thế nào nếu không cần server session?

**Bài 8 – Custom login.** Trong Spring Security 6, custom controller đã xác thực thành công và chỉ gọi `SecurityContextHolder.setContext(...)`. Sau redirect sang request mới lại bị coi là anonymous. Cần kiểm tra component nào?

**Bài 9 – CSRF.** Vì sao một request POST có cookie login hợp lệ vẫn có thể bị 403? Có nên tắt CSRF khi ứng dụng dùng session cookie không?

**Bài 10 – Thực nghiệm.** Chạy demo, đăng nhập Alice, đọc `/api/me`, mở profile riêng, logout. Ghi lại request nào có `Set-Cookie`, request nào có `Cookie`, và nêu vì sao “browser tự gửi cookie” làm trải nghiệm đăng nhập liền mạch.

### Đáp án gợi ý

1. Không. Request không tự kế thừa authentication; IP/connection không phải identity đáng tin.
2. `abc` là session ID phía client; server tra session store và kiểm tra `Authentication`.
3. Có thể để lưu saved request hoặc CSRF token trước login.
4. Browser profile khác không có session cookie tương ứng.
5. Phải coi session ID cũ không còn hợp lệ, yêu cầu xác thực lại; cookie và session có lifecycle khác.
6. HTTPS, cookie flags, rotation khi login, CSRF protection, chống XSS, timeout, logout invalidate, hạn chế scope và phát hiện bất thường.
7. Không nhất thiết mâu thuẫn: policy không đảm bảo mọi library/application code không tạo session; bỏ nơi tạo session không cần thiết và dùng bearer mechanism nếu chủ ý stateless.
8. Kiểm tra `SecurityContextRepository.saveContext(...)` và session/authentication flow, không chỉ holder.
9. Vì CSRF token thiếu/sai hoặc đã timeout; với cookie-based browser login nên giữ CSRF và gửi token hợp lệ.
10. Quan sát sẽ cho thấy session ID được mang theo request; server khôi phục authentication từ server-side state, không phải HTTP tự nhớ.

## 21. Tổng kết

**Phiên làm việc (session)** là cách ứng dụng duy trì ngữ cảnh logic giữa nhiều HTTP requests. HTTP vốn không tự lưu trạng thái đăng nhập, nên browser và server phải phối hợp theo một giao thức bổ sung: server tạo/lưu session, browser giữ session ID (thường qua cookie), và mỗi request sau gửi ID để server tra/khôi phục `SecurityContext`.

Những ý cần nhớ nhất:

1. **HTTP stateless ≠ ứng dụng không thể có state.** State cần cơ chế liên kết rõ ràng như cookie/session hoặc token.
2. **Cookie ≠ session ≠ authentication.** Cookie mang ID; session phía server có thể chứa context; `Authentication` mới là danh tính/quyền được Spring Security xử lý.
3. **Session cookie là credential.** Bảo vệ bằng HTTPS, `Secure`, `HttpOnly`, `SameSite` phù hợp, chống XSS/CSRF, rotation và logout.
4. **Spring Security không “nhớ” chỉ nhờ holder.** Persistence phụ thuộc `SecurityContextRepository` và authentication flow; custom login cần explicit save khi cần.
5. **Một login session có thể được dùng ở nhiều requests, nhưng mỗi request đều phải được kiểm tra lại.** Cookie bị thiếu, hết hạn, bị hủy hoặc policy từ chối thì request không được coi là authenticated.
6. **Không nhầm session timeout, cookie lifetime và token expiration.** Đó là những chính sách riêng cần thiết kế/test.

### Tài liệu chính thức

- [Spring Security – Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security – Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security – Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security – CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot 3.5 – Servlet Session/Cookie Properties](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [MDN – Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN – Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
