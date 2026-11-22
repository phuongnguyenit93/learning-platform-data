# Clear-Site-Data và giới hạn hỗ trợ phía trình duyệt khi đăng xuất Spring Security Servlet

## 1. Tại sao logout còn cần quan tâm đến trình duyệt?

Một người dùng nhấn **Đăng xuất** trong ứng dụng web. Phía server đã vô hiệu hóa HttpSession, nhưng trong trình duyệt có thể vẫn còn cookie, cache của trang trước đó, localStorage, sessionStorage, IndexedDB, service worker hoặc trạng thái hiển thị ở một tab khác. Một cơ chế hỗ trợ dọn dữ liệu ở phía browser là HTTP response header:

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

**Clear-Site-Data chỉ là yêu cầu từ server tới user agent.** Việc nó được xử lý như thế nào phụ thuộc trình duyệt, phiên bản, directive, secure context và chính sách của thiết bị. Header này **không thay thế thao tác vô hiệu hóa session, thu hồi refresh token hoặc hủy quyền truy cập phía server**.

Bài học tập trung vào **Spring Security Servlet**, mục **Đăng xuất**. Sau khi hoàn thành, bạn có thể:

- Giải thích đúng mục đích và cú pháp của Clear-Site-Data, các directive "cache", "cookies", "storage", "executionContexts".
- Phân biệt xóa dữ liệu phía browser với hủy session/token phía server.
- Xác định giới hạn theo browser, origin, cookie Domain và các ứng dụng khác trên cùng site.
- Kết hợp POST /logout, CSRF, LogoutFilter, SecurityContextLogoutHandler, cookie clearing và LogoutSuccessHandler.
- Chạy ứng dụng **Java 17+, Spring Boot 3.3.13, Spring Security 6**, sử dụng form login/session.
- Kiểm thử bằng curl, MockMvc và trình duyệt thật, biết rõ công cụ nào chứng minh được điều gì.

Ví dụ dùng mật khẩu demo **learner / learn-pass** trên localhost, không dùng làm credentials production.

## 2. Hai nửa của logout: server-side và browser-side

~~~text
Browser                               Spring Security Servlet
   |                                          |
   | POST /logout + CSRF token + cookie       |
   |----------------------------------------->|
   |                                    CsrfFilter
   |                                          |
   |                                    LogoutFilter
   |                                          |
   |                         clear SecurityContext
   |                         invalidate HttpSession
   |                         expire JSESSIONID cookie
   |                                          |
   |                         LogoutSuccessHandler
   |                         Clear-Site-Data header
   |                         HTTP 204 No Content
   |<-----------------------------------------|
   |                                          |
   | Browser có thể thực thi các directives   |
   | nếu hỗ trợ và đủ điều kiện HTTPS         |
   |                                          |
   | GET /me với phiên cũ                     |
   |----------------------------------------->|
   |               Không còn authenticated   |
~~~

Tầng **server-side** cần bảo đảm credential cũ không còn quyền sau logout. Với form login dùng session, đó là **invalidateHttpSession(true)** và dọn Authentication trong SecurityContext. Nếu có remember-me hoặc refresh/access token, phải xử lý vòng đời chúng theo kiến trúc cụ thể; chỉ hủy HttpSession không mặc nhiên thu hồi token.

Tầng **browser-side** có thể được yêu cầu xóa các nhóm dữ liệu bằng Clear-Site-Data, cookie expiration qua Set-Cookie và logic dọn app state trong frontend. Những hành động này có giá trị riêng tư và trải nghiệm người dùng nhưng không được dùng như chứng cứ duy nhất rằng logout an toàn.

**Bất biến quan trọng:** nếu browser bỏ qua hoàn toàn Clear-Site-Data, request sử dụng một HttpSession đã hủy vẫn phải bị server từ chối. Ngược lại, nếu browser xóa một bản sao token nhưng token đó còn hiệu lực trên server, kẻ đã sao chép token vẫn có thể dùng nó.

## 3. Cú pháp của HTTP response header

Server đặt header lên **response** của logout thành công:

~~~http
HTTP/1.1 204 No Content
Clear-Site-Data: "cache", "cookies", "storage"
~~~

Các directive được đặt **trong dấu nháy kép** và phân tách bằng dấu phẩy. Không nhầm với một request header do client gửi, hay một lệnh JavaScript có thể chủ động xóa dữ liệu ở các origin bất kỳ.

Ví dụ những tập directive khác nhau:

~~~http
Clear-Site-Data: "cookies"
~~~

~~~http
Clear-Site-Data: "storage", "cache"
~~~

~~~http
Clear-Site-Data: "executionContexts"
~~~

Ba block trên là **ba lựa chọn độc lập** để giải thích cú pháp, không phải ba header bắt buộc phải được gửi đồng thời. Ví dụ chạy được trong bài dùng **"cache", "cookies", "storage"**.

### Secure context

Cơ chế Clear-Site-Data gắn với yêu cầu **HTTPS/secure context** trong các trình duyệt triển khai nó. Kết quả chạy trên **http://localhost** không đủ để xác nhận hiệu lực trên production; localhost có thể được coi là nguồn tin cậy trong một số browser, nhưng không được dùng làm bằng chứng tương thích toàn diện. Kiểm thử trên một **origin HTTPS** giống môi trường thật.

### Header có mặt khác với dữ liệu đã bị xóa

Bốn sự kiện rất khác nhau:

1. Server đã tạo response logout.
2. Response có header Clear-Site-Data đúng cú pháp.
3. Browser nhận và có khả năng thực thi directive.
4. Dữ liệu mong muốn thực sự đã bị xóa.

Curl/MockMvc chỉ xác nhận tốt bước 1 và 2. Bước 3 và 4 phải kiểm tra bằng trình duyệt thực, theo browser/version và loại dữ liệu.

## 4. Ý nghĩa của các directive

| Directive | Yêu cầu ở phía browser | Giới hạn và tác dụng phụ |
| --- | --- | --- |
| **"cache"** | Dọn các loại browser cache thuộc phạm vi site/origin theo implementation | Không purge CDN, reverse proxy, dữ liệu origin khác hay screenshot |
| **"cookies"** | Dọn cookie trong phạm vi mà directive được triển khai | Có thể ảnh hưởng cookie dùng chung domain và các app sibling; không hỗ trợ đồng nhất |
| **"storage"** | Dọn dữ liệu web storage, IndexedDB và các vùng dữ liệu client liên quan theo implementation | Có thể mất bản nháp offline; không revoke token trên server |
| **"executionContexts"** | Yêu cầu làm mới/ảnh hưởng các browsing contexts đang mở theo hỗ trợ browser | Không thể trông chờ mọi tab tự reload, mức hỗ trợ không đồng nhất |
| **"*"** | Yêu cầu xóa rộng các loại dữ liệu được cơ chế hỗ trợ | Không nên dùng mặc định; tác động tới nhiều loại dữ liệu và UX |

Danh sách directive và chi tiết xử lý có thể phát triển giữa các phiên bản browser. Những directive về prefetch/prerender hoặc client hints có thể xuất hiện trong tài liệu tùy phiên bản; trước khi sử dụng phải xác minh cả **đặc tả được nhắm tới** và **behavior trong browser được hỗ trợ**.

### 4.1. "cache" không phải Cache-Control

Clear-Site-Data "cache" yêu cầu browser dọn cache phù hợp. Nó **không** thay thế response header:

~~~http
Cache-Control: no-store
~~~

Đối với dữ liệu cá nhân nhạy cảm, **no-store** nên được áp dụng ngay từ khi phục vụ nội dung; không đợi đến logout mới cố xóa thứ đã cache. Clear-Site-Data không tự sửa các lỗi CDN cache key, proxy cache, response đã tải xuống file hoặc tab đang giữ DOM cũ.

### 4.2. "cookies" cần xem Domain và Path

Cookie không có cùng quy tắc phạm vi với localStorage. Cookie có thể mang Domain=example.com, Path=/, Secure, HttpOnly và SameSite; một số cookie được chia sẻ giữa các host cùng site.

Giả sử có:

~~~text
accounts.example.com
app.example.com
shop.example.com
~~~

Nếu những ứng dụng này dùng cookie trên domain cha, một yêu cầu dọn cookie ở phạm vi site có thể ảnh hưởng ngoài mục tiêu logout cục bộ. Không khẳng định rằng header luôn chỉ tác động cookie của **chính đường dẫn /logout**, hoặc luôn chỉ tác động một subdomain.

**Thiết kế an toàn:** kết thúc session server, gửi Set-Cookie làm hết hạn cookie cụ thể (đúng tên/Path/Domain) và chỉ dùng "cookies" rộng nếu đã đánh giá tác động tới các ứng dụng có liên quan.

### 4.3. "storage" có thể mất dữ liệu offline

Web Storage và IndexedDB thường chứa dữ liệu của **origin**; ứng dụng PWA còn có Cache Storage, service worker và hàng đợi đồng bộ. Yêu cầu dọn "storage" có thể phù hợp khi dữ liệu đó gắn với account vừa logout, nhưng cũng có thể xóa:

- Bản nháp chưa lưu lên server.
- Dữ liệu offline mà người dùng chưa đồng bộ.
- Cấu hình giao diện hoặc tiện ích không nhạy cảm.
- Cache ứng dụng phải tải lại sau lần truy cập tiếp theo.

Đừng dùng "storage" chỉ vì nghe có vẻ an toàn hơn. Hãy phân loại dữ liệu, xác định phần nào cần xóa, chính sách đồng bộ và cách xử lý cho browser **không hỗ trợ directive**.

### 4.4. "executionContexts" không bảo đảm mọi tab đổi giao diện

User mở tab A và B. Tab A logout; tab B vẫn đang hiển thị tên user cũ trong DOM. Header executionContexts có thể không được browser hỗ trợ hoặc không tác động đúng như mong đợi. Tuy vậy request API mới từ tab B với session cũ **phải bị từ chối phía server**.

Để cải thiện UI đa tab, ứng dụng có thể kết hợp BroadcastChannel, sự kiện storage, refresh khi focus hoặc subscription trạng thái account. Đây là bổ sung UX; kiểm tra quyền trên server vẫn là nền tảng.

## 5. Phạm vi origin, site, cookie và hệ thống SSO

**Origin** thường là bộ ba scheme, host và port. Những địa chỉ sau không cùng origin:

~~~text
https://app.example.com
https://app.example.com:8443
https://login.example.com
http://app.example.com
~~~

**Site** và **cookie domain** không đồng nghĩa hoàn toàn với origin. Do đó từng directive có thể có phạm vi áp dụng khác nhau. Không dùng một công thức đơn giản “Clear-Site-Data luôn xóa đúng một origin” cho tất cả dữ liệu, đặc biệt là cookie.

### Logout tại một ứng dụng không phải global SSO logout

Nếu app và Identity Provider chạy ở hai origin hoặc có session khác nhau:

1. App A hủy HttpSession cục bộ.
2. Browser có thể dọn cookie/storage tại phạm vi được hỗ trợ.
3. Identity Provider vẫn có thể duy trì **SSO session** riêng.
4. Khi quay lại app A, user có thể được SSO xác thực lại mà không nhập password.

Nếu mục tiêu là logout toàn bộ đăng nhập liên kết, cần cơ chế OIDC logout, revoke refresh tokens hoặc session coordination theo sản phẩm identity; Clear-Site-Data không phải giao thức logout liên miền.

### Dữ liệu header không thể xóa

Clear-Site-Data không thể thu hồi hay xóa:

- Token đã bị sao chép sang thiết bị, origin hoặc attacker khác.
- Session còn hiệu lực trong Redis/database nếu server chưa revoke.
- Ảnh chụp màn hình, bản in, file tải về, dữ liệu đã gửi email.
- CDN/proxy cache bên ngoài browser.
- LocalStorage/IndexedDB thuộc origin khác.
- Cache và storage của một trình duyệt khác trên cùng máy.

Không mô tả Clear-Site-Data là “xóa sạch dấu vết của người dùng”.

## 6. Giới hạn hỗ trợ phía trình duyệt

Không thể coi Clear-Site-Data là một feature **phổ quát**. Hành vi phụ thuộc browser engine, phiên bản, directive, secure context, cấu hình enterprise và chế độ WebView/private browsing.

| Môi trường | Điều cần kiểm tra thực tế | Không nên suy ra |
| --- | --- | --- |
| Chrome/Edge và Chromium-based | Cache, cookies, storage có được xử lý trên HTTPS không? | Một directive chạy nghĩa là mọi directive chạy |
| Firefox | Browser/version có hỗ trợ các directive dự kiến không? | Kết quả Chromium áp được nguyên vẹn |
| Safari macOS, Safari iOS/WebKit | Header nhận được có dẫn tới xóa storage/cookie thực không? | Hỗ trợ đầy đủ chỉ vì header hiện ở Network |
| Android System WebView, WKWebView | Data store/WebView host có xử lý header không? | Tương đương desktop browser |
| Private browsing | Tuổi thọ storage và phạm vi clear thực tế | Behavior như cửa sổ thông thường |
| Managed/enterprise browser | Chính sách quản trị có ảnh hưởng không? | User nào cũng dùng cấu hình mặc định |

Đây là **ma trận kiểm chứng**, không phải bảng hứa hẹn một phiên bản cụ thể có hỗ trợ 100%. Không nên viết logic bảo mật yêu cầu browser chắc chắn dọn thành công; luôn có đường đi server-side an toàn nếu header bị bỏ qua.

### Kỹ thuật kiểm chứng

- Dùng **HTTPS** trên origin kiểm thử thực.
- Gắn key thử nghiệm vô hại vào localStorage, sessionStorage và nếu cần IndexedDB/Cache Storage.
- Trước logout, ghi nhận cookies, app storage và trạng thái session.
- Gửi POST /logout, kiểm tra Network response có header và có đúng dấu nháy.
- Kiểm tra từng loại storage/cookie sau logout, không suy từ một key.
- Yêu cầu lại tài nguyên bảo vệ với session cũ, xác nhận server từ chối.
- Thử hai tab; thử browser/version và thiết bị được sản phẩm công bố hỗ trợ.
- Ghi nhận **header present / client cleanup observed / server session invalid** thành ba tiêu chí độc lập.

## 7. Những phương tiện dọn trạng thái không thay thế nhau

| Cơ chế | Phía xử lý | Tác dụng chính | Giới hạn |
| --- | --- | --- | --- |
| invalidateHttpSession(true) | Server | Hủy HttpSession hiện tại | Không xóa browser cache/localStorage |
| clearAuthentication(true) | Spring Security | Xóa Authentication khỏi context theo logout handler | Không thu hồi token độc lập |
| deleteCookies("JSESSIONID") | HTTP Set-Cookie / browser | Yêu cầu hết hạn cookie cụ thể | Cần đúng Path/Domain; không xóa mọi cookie |
| Clear-Site-Data "cookies" | Browser có hỗ trợ | Dọn cookie theo phạm vi directive | Có thể ảnh hưởng cookie site rộng |
| Clear-Site-Data "storage" | Browser có hỗ trợ | Dọn client storage | Có thể mất dữ liệu offline |
| Clear-Site-Data "cache" | Browser có hỗ trợ | Dọn cache phía browser | Không purge CDN |
| Cache-Control: no-store | Browser/intermediary | Hạn chế lưu response nhạy cảm | Không phải lệnh revoke phiên |
| Token/session revocation | Backend hoặc identity provider | Không cho dùng tiếp credential đã thu hồi | Không dọn UI/storage client |
| App state reset / BroadcastChannel | Frontend | Cập nhật UI và thông báo logout đa tab | Không thay server authorization |

**Một logout tốt cần ít nhất server state an toàn**; các kỹ thuật phía client bổ sung theo yêu cầu sản phẩm.

## 8. Luồng logout Spring Security Servlet

Trong form login dùng session và CSRF mặc định:

~~~text
POST /logout
  |
  v
CsrfFilter kiểm tra CSRF token cho unsafe method
  |
  +-- sai/thiếu --> HTTP 403, logout không thành công
  |
  v
LogoutFilter
  |
  v
SecurityContextLogoutHandler
  +-- clear Authentication/context
  +-- invalidate HttpSession
  |
  v
CookieClearingLogoutHandler (nếu cấu hình)
  +-- Set-Cookie hết hạn
  |
  v
LogoutSuccessHandler
  +-- Clear-Site-Data response header
  +-- HTTP 204 No Content
~~~

Trong Spring Security, dùng DSL logout và handler chuẩn thay vì tự viết controller logout xóa vài session attribute.

Một fragment:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setHeader("Clear-Site-Data",
            "\"cache\", \"cookies\", \"storage\"");
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    })
);
~~~

Đoạn trên là **fragment trong SecurityFilterChain**, chưa phải một chương trình Java độc lập. Project hoàn chỉnh ở phần tiếp theo.

### Vì sao chỉ phát header lúc logout?

Nếu vô tình cấu hình:

~~~http
GET /me
HTTP/1.1 200
Clear-Site-Data: "cookies", "storage"
~~~

thì một browser có hỗ trợ có thể xóa cookie/storage trên mỗi lần tải profile, gây login loop và mất dữ liệu. Chỉ phát header theo **hành động xóa website data có chủ đích**, thường là logout success hoặc một luồng xóa account đã được xác thực.

### HTTP 204 là gì?

**204 No Content** báo request được xử lý thành công nhưng không có response body. Với frontend chủ động POST logout, 204 là lựa chọn rõ ràng; frontend tự điều hướng sang login/homepage. Không cố trả JSON body kèm 204. Nếu dùng 302 redirect thay thế, phải kiểm tra header vẫn nằm đúng response cần browser xử lý.

### Vì sao POST và CSRF?

Với browser form login, session cookie được gửi tự động. Một URL GET thực hiện logout có thể bị người khác nhúng, prefetch hoặc kích hoạt không chủ đích. Khi CSRF bật, logout nên được thực hiện bằng **POST kèm CSRF token hợp lệ**. Trong cấu hình mặc định, GET /logout có thể dẫn đến trang xác nhận; không nhầm GET với hành động hủy session.

## 9. Dự án Java 17+ runnable: Spring Boot form logout

Chọn **form login/session** thay vì HTTP Basic để dễ kiểm chứng: HTTP Basic client có thể tiếp tục gửi username/password hợp lệ ở mỗi request sau logout, khiến server xác thực lại ngay cả khi đã hủy session.

Dự án có GET **/public**, GET **/csrf**, GET **/me**, trang đăng nhập mặc định **/login** và POST **/logout**. Login thành công tạo session; logout invalidates session và trả header.

### 9.1. Cây thư mục

~~~text
clear-site-data-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/clearsite/
    │   ├── ClearSiteDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/clearsite/
        └── ClearSiteLogoutTest.java
~~~

### 9.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>clear-site-data-demo</artifactId>
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

Đây là **toàn bộ pom.xml** với một block build hợp lệ, không cần ghép thêm XML. Spring Boot parent quản lý các phiên bản Spring Security tương thích trong nhánh được dùng.

### 9.3. ClearSiteDemoApplication.java

~~~java
package com.example.clearsite;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ClearSiteDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClearSiteDemoApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java

~~~java
package com.example.clearsite;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learn-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public", "/csrf").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request, response, authentication) -> {
                    response.setHeader(
                        "Clear-Site-Data",
                        "\"cache\", \"cookies\", \"storage\"");
                    response.setStatus(
                        HttpServletResponse.SC_NO_CONTENT);
                })
            );

        return http.build();
    }
}
~~~

Giải thích:

1. **UserDetailsService + BCryptPasswordEncoder** cung cấp một account test với password đã hash. Không lưu raw password trong UserDetails.
2. **formLogin** bật cơ chế xác thực qua username/password và trang login mặc định.
3. **/public** và **/csrf** công khai; **/me** yêu cầu authentication.
4. CSRF **không bị tắt**. POST /login và POST /logout phải có token.
5. **invalidateHttpSession(true)** là bước server-side cốt lõi.
6. **clearAuthentication(true)** dọn Authentication theo logout handlers.
7. **deleteCookies("JSESSIONID")** gửi yêu cầu xóa cookie session bằng Set-Cookie phù hợp với cấu hình hiện tại; cần xác minh Path/Domain nếu dùng reverse proxy hoặc custom cookie.
8. **LogoutSuccessHandler** chỉ phát Clear-Site-Data sau xử lý logout, trả status **204** và không có body.
9. Mật khẩu mẫu chỉ dành cho localhost. Không dùng hardcoded credentials trong production.

**Không thêm Clear-Site-Data vào một security header writer áp cho mọi response.** Bộ lọc của Spring Security sẽ chạy nhiều URL; nếu header bị gửi thường xuyên, trình duyệt có thể liên tục mất session/data.

### 9.5. DemoController.java

~~~java
package com.example.clearsite;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/csrf")
    public Map<String, String> csrf(
            @RequestAttribute("_csrf") CsrfToken token) {
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
~~~

GET /csrf cho phép client cùng session lấy token cần thiết để POST login/logout. Khi đưa vào hệ thống thật, cần kiểm soát **same-origin/CORS** để website không tin cậy không đọc token, và nên thiết kế endpoint theo kiến trúc frontend được sử dụng. Không đưa session ID, raw password hoặc hash vào response.

## 10. Thử với curl: kiểm chứng server, không giả làm browser

Khởi động:

~~~bash
mvn spring-boot:run
~~~

Mặc định localhost:8080 khi cổng còn trống. Những lệnh tiếp theo dành cho bash với **curl và jq**; trên Windows có thể dùng curl.exe và ConvertFrom-Json. Chỉ dùng credential demo.

### 10.1. Nhận CSRF token và session cookie

~~~bash
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')
~~~

Lệnh tạo/giữ cookie jar **cookies.txt** trong thư mục hiện tại. Không đưa cookie file chứa session thật vào Git, ticket hoặc log.

### 10.2. Đăng nhập bằng form POST

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=learn-pass" \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/login
~~~

Kỳ vọng **302 redirect** sau login đúng với formLogin mặc định (đích redirect phụ thuộc saved request và cấu hình). Curl không tự follow redirect nếu không dùng -L.

### 10.3. Kiểm tra session đã login

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
~~~

Kỳ vọng **200** và username learner; /me không cần thêm password vì dùng HttpSession đã tạo sau login.

### 10.4. Lấy token mới, vì login có thể thay CSRF token

~~~bash
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')
~~~

### 10.5. Logout thành công

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/logout
~~~

Các dòng quan trọng trong response:

~~~http
HTTP/1.1 204
Clear-Site-Data: "cache", "cookies", "storage"
~~~

Server có thể gửi thêm Set-Cookie hết hạn và các security headers. Đừng phụ thuộc thứ tự header hoặc một cookie attribute cụ thể ngoài những gì đã cấu hình/test.

**Curl không xử lý Clear-Site-Data như browser.** Việc curl hiển thị header chỉ chứng minh server đã gửi nó; curl không tự xóa IndexedDB, localStorage hoặc browser cache.

### 10.6. Dùng lại phiên sau logout

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
~~~

Kỳ vọng phiên cũ không được xác thực; với formLogin mặc định, anonymous request thường được **redirect đến /login**. Đừng khẳng định API phải trả 401 trong mọi cấu hình vì entry point của formLogin khác HTTP Basic.

### 10.7. POST logout thiếu CSRF

~~~bash
curl -i --request POST http://localhost:8080/logout
~~~

Kỳ vọng **403** nếu CSRF protection được giữ và không có token hợp lệ. LogoutSuccessHandler không chạy, do đó response không được phát Clear-Site-Data từ handler của bài.

## 11. Kiểm thử MockMvc: header chính xác và session bị hủy

Tạo **src/test/java/com/example/clearsite/ClearSiteLogoutTest.java**:

~~~java
package com.example.clearsite;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ClearSiteLogoutTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResponseDoesNotClearData() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"))
            .andExpect(header().doesNotExist("Clear-Site-Data"));
    }

    @Test
    void csrfTokenCanBeRetrieved() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isString());
    }

    @Test
    void logoutWithoutCsrfDoesNotRunSuccessHandler()
            throws Exception {

        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist("Clear-Site-Data"));
    }

    @Test
    void validLogoutClearsServerSessionAndAddsHeader()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "learn-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().isNoContent())
            .andExpect(header().string(
                "Clear-Site-Data",
                "\"cache\", \"cookies\", \"storage\""));

        assertTrue(session.isInvalid());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Các test chứng minh:

- GET thông thường **không** bị gắn nhầm Clear-Site-Data.
- Endpoint /csrf trả thông tin token.
- POST /logout thiếu CSRF bị **403**, không đi tới success handler.
- Đăng nhập form thành công tạo HttpSession, GET /me dùng session đó trả 200.
- POST /logout hợp lệ trả 204 + đúng header và **MockHttpSession bị invalid**.

**Giới hạn của MockMvc:** nó không thực thi browser engine, không kiểm tra xóa localStorage/IndexedDB và không thể thay thế test Safari/Firefox/WebView thật. Đừng báo “browser data đã xóa” chỉ vì assertions của MockMvc pass.

## 12. Thực hành kiểm thử browser thật trên HTTPS

Trên origin HTTPS test, chuẩn bị dữ liệu vô hại trong DevTools Console:

~~~javascript
localStorage.setItem("clear-test", "local-before");
sessionStorage.setItem("clear-test", "session-before");
~~~

Nếu có thể, chuẩn bị thêm cookie test riêng và một IndexedDB database thử nghiệm. Không đưa mật khẩu/token/PII thật vào các giá trị mẫu.

Thứ tự kiểm tra:

1. Mở **Network** và **Application/Storage** trong Developer Tools.
2. Đăng nhập để tạo session, quan sát JSESSIONID hiện có.
3. Trong tab A, POST /logout hợp lệ.
4. Xác nhận response thật qua HTTPS có **Clear-Site-Data: "cache", "cookies", "storage"**.
5. Kiểm tra các key thử nghiệm ở localStorage và sessionStorage, IndexedDB, Cache Storage, cookies, service worker registration.
6. Mở hoặc giữ tab B trước logout; xác minh tab B có thể vẫn hiển thị UI cũ nhưng request bảo vệ mới **bị server từ chối**.
7. Thử trên Chrome/Edge, Firefox, Safari và WebView thực được sản phẩm hỗ trợ.
8. Ghi kết quả riêng cho **header present**, **browser cleanup observed**, **server session invalid**, và phiên bản hệ điều hành/browser.
9. Nếu dữ liệu không xóa ở browser cụ thể, đừng cố sửa bằng cách bỏ session invalidation; cần client fallback phù hợp.
10. Thử tác động lên cookie của ứng dụng sibling cùng domain trước khi bật "cookies" rộng ở production.

Mỗi browser/version phải có kết quả thực nghiệm; không điền sẵn rằng Safari/WebKit hay Firefox hỗ trợ đầy đủ chỉ vì Chromium đã làm được.

## 13. Các tình huống thực tế dễ hiểu nhầm

### 13.1. Sau logout vẫn thấy trang user khi bấm Back

Browser có thể hiển thị trạng thái DOM hoặc ảnh trang cũ trong lịch sử/bfcache. Điều đó **chưa chứng minh** server vẫn cho phép đọc dữ liệu mới. Thiết lập Cache-Control/no-store cho dữ liệu nhạy cảm và thiết kế app refresh/validate session khi trang hoạt động lại.

### 13.2. Client tiếp tục gửi HTTP Basic

HTTP Basic có thể gửi lại raw username/password ở request sau, khiến server xác thực lại. Clear-Site-Data không vô hiệu mật khẩu của người dùng hoặc tự thu hồi Basic credentials. Demo dùng form/session để tránh nhầm lẫn này.

### 13.3. SSO login trở lại ngay

IdP có session ở domain khác; app local logout không thu hồi nó. Cần chính sách SSO logout hoặc giao thức logout identity tương ứng.

### 13.4. Xóa cookie phá trạng thái ứng dụng khác

Một cookie được scope cho example.com có thể được nhiều app cùng sử dụng. Trước khi phát "cookies" hãy xác minh phạm vi và chấp nhận/giảm thiểu tác dụng phụ, không đặt header theo cảm tính.

### 13.5. Storage clearing phá dữ liệu PWA offline

Nếu app chưa đồng bộ IndexedDB, dọn "storage" có thể làm mất dữ liệu. Định nghĩa UX/cảnh báo/dong bộ trước logout và có chính sách phân loại storage.

### 13.6. CDN vẫn trả PII

Header Clear-Site-Data không tự purge cache CDN. Sửa Cache-Control, cache key và cấu hình CDN; đảm bảo server kiểm tra quyền cho tài nguyên nhạy cảm.

### 13.7. iOS WebView không xóa dữ liệu

WebView có thể dùng storage riêng hoặc hỗ trợ header khác desktop browser. Cần test trên bản WebView và app host thực, hoặc sử dụng API nền tảng để quản lý data store khi kiến trúc yêu cầu.

### 13.8. Header xuất hiện ở mọi response

Do cấu hình global header writer thay vì logout handler. Khi browser hỗ trợ, mỗi request có thể tự xóa cookie/storage. Chuyển phát header vào riêng logout success flow.

## 14. Chẩn đoán khi Clear-Site-Data không như mong đợi

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/cách xử lý |
| --- | --- | --- |
| Curl thấy header nhưng storage vẫn còn | Curl không phải browser | Test HTTPS browser thật |
| Header có mặt nhưng browser không clear | Browser/version/secure context | Compatibility matrix, HTTPS |
| Chrome và Safari khác nhau | Engine và directive support khác | Test từng version |
| Logout trả 403 | CSRF thiếu hoặc sai | POST token hợp lệ cùng session |
| Logout trả redirect không như mong muốn | Handler default/chain khác | Kiểm tra LogoutSuccessHandler |
| Session bị hủy nhưng lại tự login | SSO/Basic/remember-me còn hiệu lực | Xác định nguồn credentials |
| Cookie không biến mất | Path/Domain xóa không khớp | Inspect Set-Cookie và session |
| Nhiều app bị logout | Cookie shared domain bị dọn | Rà soát site/cookie scope |
| Mất bản nháp offline | "storage" xóa cả app data | Thiết kế đồng bộ trước logout |
| Một tab vẫn hiển thị user cũ | DOM/bfcache/UI state | Broadcast + refresh + server enforcement |
| CDN vẫn cache dữ liệu nhạy cảm | Header chỉ yêu cầu browser | Cache-Control, CDN config |
| Token cũ vẫn dùng được | Không có revoke/expiry phía server | Revocation/token rotation |
| Header được gửi cả khi GET /public | Áp dụng global sai | Chỉ phát khi logout thành công |

Quy trình debug: xác nhận POST /logout đã tới đúng chain; CSRF hợp lệ; LogoutFilter đã hủy session; response có header; proxy không strip; browser ở HTTPS; storage thực tế có bị dọn; các API sau logout có còn cho phép truy cập bằng phiên cũ không.

## 15. Bài tập và đáp án

**Bài A.** Server chỉ gửi Clear-Site-Data "cookies" mà không hủy HttpSession. Có chắc logout an toàn?

**Đáp án:** Không. Cookie có thể không bị xóa ở một browser, hoặc session/token đã bị sao chép. Server phải invalidate/revoke credential còn hiệu lực.

**Bài B.** Vì sao một response HTTP có header Clear-Site-Data chưa đủ chứng minh localStorage bị xóa?

**Đáp án:** Browser có thể không hỗ trợ directive, bỏ qua trong môi trường không secure hoặc có behavior khác. Phải test storage thực tế.

**Bài C.** App A và B dùng cookie Domain=example.com. Logout A gửi "cookies" có rủi ro gì?

**Đáp án:** Xóa cookie rộng có thể làm B mất phiên hoặc tùy chọn, ảnh hưởng SSO/UX. Phải xem cookie scope.

**Bài D.** Dùng Clear-Site-Data "cache" có thay thế Cache-Control: no-store trên response PII không?

**Đáp án:** Không. No-store phải bảo vệ response nhạy cảm ngay khi được phục vụ; Clear-Site-Data là bước bổ sung ở browser khi logout.

**Bài E.** POST /logout thiếu CSRF nhận 403. Vì sao không có header Clear-Site-Data từ success handler?

**Đáp án:** CsrfFilter từ chối trước LogoutFilter/LogoutSuccessHandler.

**Bài F.** MockMvc xác nhận header đúng và MockHttpSession invalid. Có thể kết luận Safari đã xóa IndexedDB không?

**Đáp án:** Không. MockMvc không thực thi browser. Kiểm tra trên Safari/WebKit thật.

**Bài G.** Sau logout, client vẫn gửi Authorization Basic với mật khẩu đúng. Vì sao /me có thể trả 200?

**Đáp án:** Server xác thực lại raw credentials trên request mới. Logout session không vô hiệu mật khẩu Basic.

**Bài H.** Tab B còn hiển thị username cũ. Phải kiểm tra gì đầu tiên để kết luận nguy cơ bảo mật?

**Đáp án:** Gửi request được bảo vệ bằng phiên/token cũ, xem server có từ chối không. DOM cũ có thể do cache/memory, cần UX dọn thêm.

**Bài I.** Vì sao không nên đặt Clear-Site-Data "storage" trên mọi request?

**Đáp án:** Browser hỗ trợ có thể liên tục xóa trạng thái ứng dụng, gây mất dữ liệu và vòng lặp đăng nhập.

## 16. Checklist triển khai

- [ ] Hiểu Clear-Site-Data là **yêu cầu phía browser**, không phải revoke token/session trên server.
- [ ] Đã hủy HttpSession và Authentication; xử lý token/remember-me/SSO nếu có.
- [ ] Cookie hết hạn gửi đúng Domain/Path và được browser thực thi.
- [ ] Chỉ phát Clear-Site-Data trên logout success hoặc sự kiện được thiết kế để dọn site data.
- [ ] Dấu nháy kép quanh từng directive đúng: "cache", "cookies", "storage".
- [ ] Đã cân nhắc dùng từng directive, không mặc định wildcard "*".
- [ ] Có HTTPS production và đã test secure context.
- [ ] Đã kiểm tra browser/OS/version thực tế, không hứa hỗ trợ giống nhau cho Safari, Firefox và Chromium.
- [ ] Có test MockMvc cho header logout, server session invalid, CSRF denial và response bình thường không có header.
- [ ] Có test browser thật cho Cookies, localStorage, sessionStorage, IndexedDB, Cache Storage.
- [ ] Đã rà soát cookie chung của nhiều app/subdomain trước khi dùng "cookies".
- [ ] Đã rà soát PWA/offline drafts và dữ liệu cần giữ trước khi dùng "storage".
- [ ] Có Cache-Control/no-store cho response riêng tư và policy CDN riêng.
- [ ] Có xử lý tab khác/Back navigation phù hợp mà vẫn enforce session invalidation phía server.
- [ ] Không log passwords, session cookies, token hoặc thông tin PII khi debug logout.

**Kết luận:** Trong Spring Security Servlet, **Clear-Site-Data** là lớp bổ sung hữu ích cho logout nhưng **hỗ trợ phía browser có giới hạn và không đồng nhất**. Hãy phát nó trên **response logout thành công** cùng với invalidateHttpSession, clearAuthentication và cookie clearing; thu hồi token/SSO session theo giao thức riêng nếu cần. Chỉ coi logout là thành công về bảo mật khi **server từ chối sử dụng lại credential đã hủy**, còn việc browser dọn cache/cookies/storage phải được kiểm chứng trên môi trường HTTPS và các browser mục tiêu.
