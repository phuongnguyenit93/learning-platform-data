# Redirect URI sau reverse proxy và cấu hình URL công khai trong Spring Security OAuth2 Client

## 1. Vấn đề: ứng dụng nhìn thấy URL nội bộ, người dùng truy cập URL công khai

Trong **Spring Security Servlet** với **OAuth2 Client / OAuth2 Login**, ứng dụng thường chạy bên trong mạng riêng nhưng trình duyệt truy cập qua reverse proxy, load balancer hoặc API gateway:

~~~text
Trình duyệt người dùng
  https://app.example.com
          |
          | HTTPS 443
          v
Reverse proxy / load balancer (TLS termination)
          |
          | HTTP nội bộ
          v
Spring Boot trên http://service:8080
~~~

Khi đăng nhập bằng **OAuth2 Authorization Code** (thường kết hợp OpenID Connect), Spring Security chuyển hướng trình duyệt đến nhà cung cấp danh tính (IdP). Trong URL chuyển hướng này có tham số **redirect_uri**: địa chỉ mà IdP sẽ đưa trình duyệt trở lại sau khi người dùng đăng nhập.

**Yêu cầu then chốt:** IdP cần nhận đúng callback **công khai**, ví dụ:

~~~text
https://app.example.com/login/oauth2/code/company
~~~

Nếu Spring Security lại suy ra:

~~~text
http://service:8080/login/oauth2/code/company
~~~

thì IdP có thể báo **redirect_uri_mismatch**, **invalid_redirect_uri**, **invalid_request** hoặc lỗi tương đương. Ngay cả khi IdP chấp nhận, trình duyệt có thể không truy cập được hostname nội bộ. Vấn đề gốc thường nằm ở **scheme, host, port hoặc path/prefix** mà ứng dụng nhận từ reverse proxy.

Bài này tập trung vào **đăng nhập qua trình duyệt với authorization_code** trong Servlet stack. OAuth2 Client chỉ sử dụng **client_credentials** để gọi API server-to-server không thực hiện browser login/callback như ví dụ này.

Sau bài học, bạn sẽ hiểu: (1) Spring Security dựng redirect URI thế nào, (2) header **Forwarded / X-Forwarded-*** dùng để khôi phục URL công khai ra sao, (3) cấu hình **server.forward-headers-strategy** và **redirect-uri**, (4) các trường hợp gateway thêm hoặc loại bỏ path prefix, (5) cách kiểm thử luồng đăng nhập và gỡ lỗi an toàn.

## 2. Phân biệt authorization request URL và callback URL

Hai endpoint thường bị nhầm:

| Endpoint | Ai gọi và vào lúc nào? | Vai trò |
| --- | --- | --- |
| **/oauth2/authorization/company** | Trình duyệt truy cập ứng dụng để **bắt đầu đăng nhập** | Spring Security tạo Authorization Request rồi trả 302 chuyển đến IdP |
| **/login/oauth2/code/company** | IdP chuyển hướng trình duyệt **trở lại** sau đăng nhập | Spring Security nhận **code** và **state**, kiểm tra tương quan rồi thực hiện bước đổi code lấy token |
| **Authorization Endpoint của IdP** | Trình duyệt được chuyển hướng tới IdP | IdP xác thực người dùng và xác nhận yêu cầu OAuth2 |
| **Token Endpoint của IdP** | Backend ứng dụng gọi IdP | Đổi authorization code lấy token, theo chính sách OAuth2/OIDC của IdP |

Tên **company** là **registrationId** trong cấu hình OAuth2 Client. Đây không phải hostname IdP và không nhất thiết là tên provider mặc định.

Luồng đầy đủ:

~~~text
(1) GET https://app.example.com/oauth2/authorization/company
    |
    v
(2) Spring Security tạo authorization request, lưu state trong session
    |
    v
(3) HTTP 302 Location: https://idp.example.net/authorize?
          client_id=...
          &response_type=code
          &scope=...
          &state=...
          &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
    |
    v
(4) Người dùng đăng nhập tại IdP
    |
    v
(5) GET https://app.example.com/login/oauth2/code/company?code=...&state=...
    |
    v
(6) Proxy đưa request trở về Spring Security
    |
    v
(7) Spring Security kiểm tra state, đổi code lấy token và thiết lập authentication
~~~

Trong thực tế, URL ở bước (3) thường chứa thêm tham số tùy provider, ví dụ **nonce**, **code_challenge** khi dùng PKCE; không dùng sơ đồ này để kết luận danh sách tham số luôn giống nhau. Bước (5) dùng **GET query response** trong cấu hình thông thường; một provider sử dụng response mode khác cần xem lại cách cookie/session hoạt động.

**redirect_uri phải khớp cấu hình đã đăng ký tại IdP.** Cách so khớp của IdP có thể rất nghiêm ngặt, phân biệt **http/https**, hostname, port, path, chữ hoa/thường và dấu slash cuối. Không tự thêm query parameter động hay thay đổi callback tùy tiện.

## 3. Spring Security tạo redirect_uri từ baseUrl

Đối với registration dùng Authorization Code, Spring Security hỗ trợ các biến mẫu như:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Trong đó:

- **{baseUrl}**: URL cơ sở nhìn từ request mà Spring Security đã xử lý, gồm scheme, host, port (nếu cần) và context path công khai thích hợp.
- **{registrationId}**: tên registration, ví dụ **company**.
- **/login/oauth2/code/{registrationId}**: callback mặc định do OAuth2 Login authentication filter xử lý khi ứng dụng sử dụng cấu hình chuẩn.

Ví dụ ba trường hợp:

| Trình duyệt truy cập | Backend nội bộ | redirect_uri đúng |
| --- | --- | --- |
| https://app.example.com | http://service:8080 | **https://app.example.com/login/oauth2/code/company** |
| https://app.example.com:8443 | http://service:8080 | **https://app.example.com:8443/login/oauth2/code/company** |
| https://app.example.com/portal | http://service:8080 và proxy strip **/portal** | **https://app.example.com/portal/login/oauth2/code/company** |

Nếu backend tự thấy **http://service:8080** vì thiếu thông tin proxy tin cậy, **{baseUrl}** có thể sai. Ngược lại, khi gateway khai báo sai prefix, callback có thể bị thiếu **/portal** hoặc lặp thành **/portal/portal**.

Cách khắc phục nên ưu tiên **sửa mô hình URL công khai và header được tin cậy**. Có thể đặt redirect-uri tuyệt đối cho từng môi trường khi cần ổn định hostname, nhưng điều đó không thay thế việc đảm bảo reverse proxy chuyển tiếp callback thật tới đúng ứng dụng.

### Hai nhóm cấu hình liên quan nhưng khác chức năng

- **spring.security.oauth2.client.registration.company.redirect-uri** quyết định giá trị **redirect_uri** được đưa vào Authorization Request và dùng trong luồng OAuth2 Client.
- **server.forward-headers-strategy** quyết định việc ứng dụng Spring Boot xử lý các header forwarded mà proxy cung cấp. Nó có thể ảnh hưởng scheme/host/port/context path mà các thành phần web đọc được.

Bật forwarded headers không tự thay đổi giá trị đăng ký ở IdP. Sửa redirect-uri trong application.yml cũng không tự sửa gateway, cookie hoặc session.

## 4. Ví dụ Spring Boot 3.x, Spring Security 6.x, Java 17+

Đặt ví dụ trong một ứng dụng Spring Boot đã có Gradle wrapper. Trong file **build.gradle**, thêm các dependency nếu chưa có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Cấu hình **src/main/resources/application.yml**:

~~~yaml
server:
  forward-headers-strategy: framework

spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OAUTH_CLIENT_ID}
            client-secret: ${OAUTH_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Ý nghĩa:

1. **registration.company** tạo client registration mang ID **company**, nên URL bắt đầu đăng nhập là **/oauth2/authorization/company**, callback mặc định là **/login/oauth2/code/company**.
2. **provider.company-oidc.issuer-uri** cho phép Spring tra metadata OIDC của issuer, như authorization endpoint, token endpoint và JWK Set. Issuer phải là giá trị thật do IdP công bố và được backend truy cập được. Ví dụ này cần IdP OIDC hỗ trợ discovery, không phải mọi server OAuth2 đều có OIDC discovery.
3. **OAUTH_CLIENT_ID**, **OAUTH_CLIENT_SECRET** là biến môi trường hoặc secret của deployment. Không ghi client secret thật vào Git, README, log hoặc URL chuyển hướng.
4. **redirect-uri** dùng mẫu **{baseUrl}**, nên scheme/host/port và prefix của request sau xử lý proxy quyết định callback được tạo ra.
5. **forward-headers-strategy: framework** yêu cầu Spring Boot trên Servlet dùng cơ chế xử lý forwarded headers ở tầng framework (thường qua **ForwardedHeaderFilter**). Cấu hình này chỉ an toàn khi các header forwarded đã được proxy tin cậy kiểm soát.

Tệp **src/main/java/com/example/loginproxy/LoginProxyApplication.java**:

~~~java
package com.example.loginproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginProxyApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}

@RestController
class ExampleController {
    @GetMapping("/")
    String home() {
        return "Visit /oauth2/authorization/company to sign in";
    }

    @GetMapping("/account")
    String account(@AuthenticationPrincipal OidcUser user) {
        return "subject=" + user.getIdToken().getSubject();
    }
}
~~~

**Cách thử thực tế:** Cấu hình IdP OIDC hợp lệ, cung cấp ba biến môi trường và chạy ứng dụng qua reverse proxy HTTPS. Trên IdP, khai báo callback chính xác:

~~~text
https://app.example.com/login/oauth2/code/company
~~~

Truy cập **https://app.example.com/oauth2/authorization/company**. Spring Security sẽ tạo request chứa tham số **redirect_uri** trỏ về địa chỉ trên, nếu forwarded headers đã được xử lý đúng. Sau đăng nhập, **GET /account** trả **subject=...** với subject trong ID token của người dùng; giá trị cụ thể phụ thuộc tài khoản/IdP nên không dự đoán trước.

**Ranh giới ví dụ:** Chưa có real IdP/credential thì không thể chạy trọn luồng đăng nhập chỉ từ mã demo. Dependency và Java source có thể biên dịch trong một dự án Boot 3.x đã cấu hình đúng; cần môi trường OIDC và URL công khai để kiểm chứng callback. Không dùng token hoặc secret minh họa để đăng nhập production.

## 5. Reverse proxy phải truyền đúng URL công khai

Vì HTTPS thường kết thúc ở proxy, backend nhìn thấy socket HTTP nội bộ. Proxy cần gửi thông tin **công khai** bằng header đã được chuẩn hóa tại vùng tin cậy:

| Header | Giá trị với ví dụ | Tác dụng |
| --- | --- | --- |
| **X-Forwarded-Proto** | https | Scheme công khai |
| **X-Forwarded-Host** | app.example.com | Host công khai |
| **X-Forwarded-Port** | 443 | Port công khai |
| **X-Forwarded-Prefix** | /portal, khi có prefix thực | Path prefix bên ngoài có thể đã bị proxy strip |
| **Forwarded** | proto=https;host=app.example.com | Chuẩn header thay thế theo RFC; chọn cách nhất quán |
| **X-Forwarded-For** | địa chỉ IP gốc được proxy tin cậy quản lý | Liên quan client IP và logging; không quyết định callback hostname |

**Chỉ proxy tin cậy được phép đặt các giá trị này.** Nếu client Internet tự gửi **Forwarded: host=evil.example** rồi ứng dụng tin tưởng nó, attacker có thể ảnh hưởng URL tạo bởi ứng dụng và gây lỗi hoặc rủi ro redirect/host poisoning. Tại ranh giới Internet, proxy phải **loại bỏ hoặc ghi đè** header forwarded do client đưa vào, chỉ tạo lại từ hostname/protocol đã được phép. Giới hạn truy cập trực tiếp vào cổng backend; không dựa vào việc người dùng “sẽ không đoán được” port nội bộ.

### Trích đoạn cấu hình proxy cho deployment không có path prefix

Trong một khối **server** HTTPS có **server_name app.example.com** và chứng chỉ TLS được cấu hình riêng, ví dụ location Nginx sau thể hiện thông tin cần chuyển tiếp:

~~~nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host app.example.com;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.com;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;
}
~~~

Đây là **trích đoạn** bên trong cấu hình Nginx, không phải toàn bộ tệp triển khai/TLS. **X-Forwarded-For $remote_addr** mô tả proxy ở ranh giới trực tiếp; nếu có nhiều proxy tin cậy, cách xây dựng và chấp nhận chuỗi IP cần thiết kế riêng. Không lấy nguyên các header do client tự gửi để xây URL công khai.

Lệnh **proxy_set_header Forwarded "";** khiến ví dụ tránh giữ một giá trị **Forwarded** do client tự cung cấp, trong khi Nginx đặt rõ họ **X-Forwarded-***. Ứng dụng chỉ nên tin các header này khi cổng nội bộ bị giới hạn và tuyến proxy thực sự đáp ứng các quy tắc ở trên.

Có thể sử dụng chuẩn **Forwarded** thay cho nhóm **X-Forwarded-*** nếu hạ tầng hỗ trợ, nhưng cần kiểm tra thứ tự ưu tiên và việc ghi đè, tránh hai bộ header mô tả hai hostname khác nhau.

### framework và native

Trong Spring Boot, **server.forward-headers-strategy** thường có các lựa chọn:

- **none**: không xử lý forwarded headers ở phía Spring Boot.
- **native**: để container xử lý theo khả năng/cấu hình của nó.
- **framework**: dùng cơ chế của framework để đọc forwarded headers.

Bài này dùng **framework** để minh họa trực tiếp trên Spring MVC. Nếu chọn **native** (ví dụ thông qua cấu hình Tomcat RemoteIpValve), phải xác minh từng loại header và trusted proxy phù hợp; không tự giả định nó xử lý prefix giống **ForwardedHeaderFilter**. Tránh bật nhiều lớp xử lý cùng header mà không biết bên nào là nguồn chính.

## 6. Khi ứng dụng có public path prefix

Đây là trường hợp thường khó chẩn đoán nhất. Giả sử trình duyệt truy cập:

~~~text
https://app.example.com/portal/oauth2/authorization/company
~~~

Nhưng reverse proxy **strip /portal** rồi chuyển đến backend:

~~~text
http://service:8080/oauth2/authorization/company
~~~

Backend xử lý security endpoint ở path **/oauth2/authorization/company**. Tuy nhiên, IdP phải trả về callback **có prefix công khai**:

~~~text
https://app.example.com/portal/login/oauth2/code/company
~~~

Trong mô hình strip prefix, một reverse proxy được tin cậy có thể gửi:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
~~~

và ứng dụng xử lý với **forward-headers-strategy: framework**. Hãy kiểm tra **Location** được tạo ra ở request thực tế; tính chính xác của prefix phụ thuộc cấu hình proxy, servlet mapping, context path và version. Không nên đoán rằng thêm một header là đủ để toàn bộ request/callback hoạt động.

Nếu ứng dụng đã chạy **server.servlet.context-path: /portal** và proxy chuyển nguyên prefix, **không** đồng thời ép thêm cùng prefix vào **X-Forwarded-Prefix**, trừ khi đã chứng minh đường dẫn không bị nhân đôi. Có hai kiến trúc thường gặp:

| Kiến trúc | Proxy chuyển vào backend | Giải pháp URL |
| --- | --- | --- |
| App thực sự có context path **/portal** | Giữ **/portal** trên request | Context path là một phần URL cơ sở; không thêm prefix lần hai |
| App ở context root **/**, proxy strip **/portal** | Chuyển **/oauth2/...** vào backend | Proxy khai báo prefix công khai đúng cách; backend tái dựng URL ngoài |

Phải thử **cả hai chiều**:
1. Browser gọi đúng public authorization URL.
2. Authorization Request đưa **redirect_uri** đúng tới IdP.
3. IdP gọi lại **public callback** có prefix.
4. Proxy map callback đến endpoint **/login/oauth2/code/company** bên trong backend.
5. Session cookie vẫn được gửi đúng path và host sau vòng đi-về.

Nếu proxy làm mất prefix ở lúc tạo authorization request hoặc ở lúc forward callback, có thể xuất hiện **redirect_uri_mismatch**, 404 hoặc **authorization_request_not_found**. Đây là ba lỗi với nguyên nhân khác nhau, không nên xử lý bằng cách tắt bảo mật.

## 7. Cấu hình redirect-uri tuyệt đối: khi nào thích hợp?

Nếu ứng dụng chỉ có **một public hostname cố định trong mỗi môi trường**, có thể chọn URL tường minh thay cho **{baseUrl}**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "https://app.example.com/login/oauth2/code/company"
~~~

Trích đoạn trên **chỉ thay thế giá trị redirect-uri** trong cấu hình đầy đủ ở mục 4; giữ các thuộc tính client/provider khác. Cách này giúp authorization request không phụ thuộc host/scheme forwarded để chọn callback, nhưng browser vẫn phải quay về đúng endpoint được proxy đưa tới backend và session vẫn phải hợp lệ.

Với nhiều môi trường **localhost/staging/production**, IdP thường cần khai báo redirect URI tương ứng, hoặc dùng client registration/secret riêng. Tránh wildcard callback và tránh tự cho phép host tùy ý; chọn public URI một cách kiểm soát theo cấu hình deployment, ví dụ profile hoặc biến môi trường do hệ thống cấp.

Không đặt **redirect_uri** cố định chỉ vì không hiểu request forwarding: email xác nhận đăng nhập, form action, absolute link, cookie hoặc các redirect khác vẫn có thể mắc lỗi khi ứng dụng không biết public URL chính xác.

### Không thay đổi callback path một chiều

Nếu tự chọn callback khác với **/login/oauth2/code/{registrationId}**, phải cấu hình **OAuth2LoginAuthenticationFilter** tương ứng (ví dụ **oauth2Login().redirectionEndpoint().baseUri(...)**) và security chain phải nhận endpoint đó. Chỉ đổi **registration.redirect-uri** sẽ khiến IdP gọi về một path mà filter OAuth2 Login mặc định không xử lý; kết quả thường là 404 hoặc chuyển hướng đăng nhập ngoài ý muốn.

Đối với phần lớn ứng dụng, giữ callback mặc định giúp giảm số nơi phải cấu hình.

## 8. Kiểm thử: quan sát redirect_uri trước khi đăng nhập

### A. Kiểm tra HTTP qua public host

Trong staging hoặc môi trường test có DNS/TLS hợp lệ và IdP đã đăng ký client, chạy:

~~~bash
curl -i 'https://app.example.com/oauth2/authorization/company'
~~~

Kỳ vọng phản hồi **302** có header **Location** trỏ tới authorization endpoint của IdP. Trong URL Location, giải mã tham số **redirect_uri** và so sánh với callback đã đăng ký:

~~~text
redirect_uri=https://app.example.com/login/oauth2/code/company
~~~

Nhiều tham số trong **Location** được percent-encode; không cần toàn bộ URL Location giống hệt giữa hai lần chạy, vì **state**, **nonce** và dữ liệu ngẫu nhiên có thể thay đổi. Không đăng lại nguyên chuỗi Location có chứa state ra kênh công khai.

Nếu nhận **302 tới /login** thay vì IdP, kiểm tra registration ID, SecurityFilterChain được chọn và OAuth2 login setup. Nếu nhận **500** hoặc lỗi startup, kiểm tra IdP discovery, environment variables và cấu hình issuer. Nếu Location trỏ **http://service:8080**, tập trung vào **forwarded header trust** và việc Spring Boot có xử lý forwarded headers hay không.

Sau đó hoàn tất đăng nhập bằng trình duyệt và xem Network:

- Authorization Request gửi đi chứa redirect_uri đúng.
- Callback thực tế tới URL public đúng và có **code/state** theo flow tương ứng.
- Trình duyệt gửi session cookie mà ứng dụng cần để liên kết **state**.
- Proxy route callback tới đúng backend.
- Ứng dụng tạo authentication thành công và không tạo vòng lặp redirect.

### B. Unit test cho cơ chế tái dựng URL từ forwarded headers

Bài test nhỏ sau kiểm tra hành vi **ForwardedHeaderFilter** riêng biệt. Nó **không** thay cho bài test OAuth2 end-to-end và **chỉ dùng header giả lập có nguồn đáng tin**.

Tệp **src/test/java/com/example/loginproxy/ForwardedUrlTest.java**:

~~~java
package com.example.loginproxy;

import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.ForwardedHeaderFilter;

class ForwardedUrlTest {
    @Test
    void reconstructsPublicSchemeHostAndPort() throws Exception {
        MockHttpServletRequest request =
                new MockHttpServletRequest(
                        "GET", "/oauth2/authorization/company");
        request.setScheme("http");
        request.setServerName("service.internal");
        request.setServerPort(8080);

        request.addHeader("X-Forwarded-Proto", "https");
        request.addHeader("X-Forwarded-Host", "app.example.com");
        request.addHeader("X-Forwarded-Port", "443");

        MockHttpServletResponse response = new MockHttpServletResponse();

        new ForwardedHeaderFilter().doFilter(request, response, (req, res) -> {
            HttpServletRequest actual = (HttpServletRequest) req;
            assertEquals("https", actual.getScheme());
            assertEquals("app.example.com", actual.getServerName());
            assertEquals(443, actual.getServerPort());
            assertEquals(
                    "https://app.example.com/oauth2/authorization/company",
                    actual.getRequestURL().toString());
        });
    }
}
~~~

Chạy trong dự án Boot có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.loginproxy.ForwardedUrlTest
~~~

Trên Windows dùng **gradlew.bat test --tests com.example.loginproxy.ForwardedUrlTest**. Test kỳ vọng hoàn thành không có assertion failure. Nó chứng minh URL mà Servlet request bộc lộ sau filter, nhưng **chưa chứng minh** IdP được đăng ký đúng, session tồn tại hoặc proxy chuyển callback về chính xác. Để kiểm chứng những yếu tố đó, dùng bài test HTTP/browser ở phần A.

### C. Ma trận kiểm thử tối thiểu

| Tình huống | Điều cần xác minh |
| --- | --- |
| Browser vào https://app.example.com/oauth2/authorization/company | 302 đến IdP; redirect_uri là **https** và hostname public |
| Proxy truyền backend HTTP :8080 | redirect_uri **không** chứa hostname/port nội bộ |
| External path prefix **/portal** | redirect_uri có **/portal** đúng một lần; callback được route về app |
| Staging host và production host | Mỗi môi trường tạo callback đã đăng ký ở IdP |
| Callback sau đăng nhập | **state**, session cookie và callback path tương quan thành công |
| Gửi request vào backend trực tiếp | Backend không bị public truy cập tùy tiện; header forwarded giả mạo không thể thay đổi security URL được dùng bởi người ngoài |
| Callback sai path/port | Không tạo vòng lặp login; log chỉ rõ lỗi mapping hoặc mismatch |

## 9. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra / khắc phục |
| --- | --- | --- |
| **redirect_uri_mismatch** ở IdP | Redirect URI gửi lên khác whitelist đã đăng ký | Giải mã tham số redirect_uri trong Location, đối chiếu scheme/host/port/path/trailing slash |
| redirect_uri chứa **http://service:8080** | Backend không dùng thông tin public forwarded, hoặc proxy không truyền đúng | Kiểm tra **server.forward-headers-strategy**, trusted proxy, X-Forwarded-Proto/Host/Port |
| **http** thay vì **https** | TLS kết thúc ở proxy nhưng backend chỉ nhìn HTTP | Cấu hình forwarding scheme đúng, không bật trust header từ Internet |
| Thiếu hoặc nhân đôi **/portal** | Proxy strip/preserve prefix không thống nhất với context path và X-Forwarded-Prefix | Xem request ngoài/vào trong, kiểm tra callback trong IdP và mapping trên gateway |
| Callback tới **404** | Callback chưa được gateway chuyển đúng, hoặc security filter không xử lý URI đã tùy chỉnh | Giữ mặc định **/login/oauth2/code/{registrationId}** hoặc cấu hình redirectionEndpoint tương ứng |
| **authorization_request_not_found** / **invalid_state** | Session đã mất, cookie không trở lại, nhiều replica không chia sẻ session, state bị thay đổi | Kiểm tra cookie host/path/SameSite/Secure, timeout, session store, reverse proxy và flow nhiều replica |
| Callback lặp về **/login** | Security chain sai, authentication không được khôi phục, callback không được filter OAuth2 login xử lý | Kiểm tra FilterChainProxy và log Spring Security, tránh thay callback path một phía |
| Chạy localhost đúng nhưng staging sai | Host/port/prefix hoặc IdP registration khác | Kiểm tra public hostname và redirect URI cụ thể của từng môi trường |
| Chỉnh redirect-uri cố định nhưng vẫn lỗi | Proxy không route callback, cookie/session sai hoặc IdP vẫn dùng whitelist cũ | Kiểm tra toàn bộ vòng authorize → callback → token exchange |
| Browser liên tục mất session | Cookie bị chặn do Secure/SameSite, domain/path sai hoặc load balancing | Kiểm tra Set-Cookie và Cookie trong Network, không log giá trị session/token |

### Cookie, state và nhiều replica

Trong cấu hình Spring Security OAuth2 Login phổ biến, authorization request (chứa **state**) được giữ qua **HTTP session**, nhờ repository mặc định **HttpSessionOAuth2AuthorizationRequestRepository**. Khi trình duyệt quay về callback, hệ thống cần tìm lại authorization request tương ứng.

Nếu public host thay đổi trong lúc đăng nhập, session cookie không được gửi theo đúng domain/path, proxy đưa callback sang replica không chia sẻ session, hoặc session hết hạn, luồng có thể lỗi ngay cả khi redirect_uri hoàn toàn đúng.

Với mô hình nhiều replica, dùng cơ chế session phù hợp như shared session store hoặc giải pháp routing được kiểm soát; không bỏ kiểm tra **state** để xử lý lỗi. Với OIDC thông thường dùng top-level GET callback, **SameSite=Lax** thường phù hợp, nhưng cookie policy phải được thử trên trình duyệt thực; flow sử dụng **form_post** và cookie cross-site có yêu cầu khác. Trong production cần đảm bảo session cookie được bảo vệ trên HTTPS, có thuộc tính **Secure** khi phù hợp và đường dẫn cookie đúng với public prefix.

### An toàn khi tin proxy headers

Cấu hình **forward-headers-strategy: framework** không tự xác thực proxy. Nó chỉ bảo ứng dụng sử dụng các header có mặt. Để tránh spoofing:

1. Giới hạn mạng để người dùng bên ngoài không thể kết nối thẳng tới backend.
2. Tại public ingress, xóa hoặc ghi đè **Forwarded** và **X-Forwarded-*** do client đưa vào.
3. Chỉ chấp nhận public hostname/port đã cấu hình, không ghép trực tiếp Host do client tùy chọn.
4. Với nhiều proxy, xác định hop nào được phép đặt header và bảo đảm các hop tiếp theo bảo toàn giá trị đã xác thực.
5. Giữ TLS hợp lệ trên public host, không gửi code/token/client-secret vào log hoặc thông báo lỗi chi tiết cho người dùng.
6. Bảo đảm IdP chỉ chấp nhận redirect URI chính xác đã đăng ký, không dùng wildcard rộng hoặc open redirect.

## 10. Checklist trước khi đưa OAuth2 Client qua reverse proxy lên production

1. **Công khai URL:** Xác định duy nhất scheme, host, port, external prefix mà người dùng truy cập.
2. **Registration ở IdP:** Callback trùng chính xác giá trị ứng dụng tạo ra (không lẫn URL bắt đầu đăng nhập).
3. **Client registration:** Đúng registrationId, issuer metadata, client ID/secret, scope và redirect-uri template.
4. **Proxy:** Route cả **/oauth2/authorization/{registrationId}** và **/login/oauth2/code/{registrationId}**; xử lý prefix nhất quán.
5. **Forwarded headers:** Được tạo bởi proxy tin cậy, không phản ánh header client không kiểm soát; cấu hình Spring Boot **framework** hoặc container **native** đã kiểm chứng.
6. **Security chain:** OAuth2 Login và callback được xử lý trong đúng chain; không chặn callback bằng matcher sai, redirect loops hoặc filter khác.
7. **Cookie/session:** HTTPS, SameSite/Secure/Path phù hợp; session còn tồn tại đến callback, nhiều replica có thiết kế lưu session.
8. **Thử nghiệm:** Kiểm tra 302 Location và **redirect_uri đã giải mã**, hoàn tất login thực, xác nhận không xuất hiện hostname nội bộ hoặc prefix sai.
9. **Đổi môi trường:** Staging/production có registration, domain và callback tương ứng; không hardcode callback của môi trường khác.
10. **Vận hành:** Ghi nhận status, endpoint, correlation ID và loại lỗi đủ để chẩn đoán, nhưng không lộ authorization code, state, access token, ID token hoặc client secret.

**Một cấu hình thành công phải nhất quán cả ba nơi:** URL công khai của trình duyệt, redirect URI đã đăng ký ở IdP, và URL mà Spring Security tính từ request sau proxy. Nếu ba giá trị này khớp và session/callback route vẫn được giữ, luồng OAuth2 Client qua reverse proxy hoạt động mà không cần nới lỏng quy tắc bảo mật.
