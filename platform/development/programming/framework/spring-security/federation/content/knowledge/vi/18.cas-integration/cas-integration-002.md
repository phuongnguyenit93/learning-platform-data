# CasAuthenticationEntryPoint và chuyển hướng tới CAS server

## 1. Mục tiêu và bối cảnh

Trong hệ thống **Spring Security – federation**, **Central Authentication Service (CAS)** cho phép nhiều ứng dụng sử dụng một máy chủ đăng nhập tập trung. Khi một browser chưa có phiên đăng nhập tại ứng dụng Spring, ứng dụng cần đưa browser tới **CAS server /login**, kèm một **service URL** để CAS biết nơi trả người dùng về sau khi đăng nhập.

Lớp Spring Security thực hiện bước bắt đầu này là **CasAuthenticationEntryPoint**:

- Được **ExceptionTranslationFilter** gọi khi một request cần đăng nhập nhưng chưa có Authentication hợp lệ.
- Xây URL chuyển hướng đến **CAS loginUrl**, gắn tham số **service** từ **ServiceProperties**.
- Phản hồi bằng HTTP redirect, thường là **302 + Location**.
- **Không xác thực service ticket**, không tự tạo user session và không phải CAS server.
- Hoạt động cùng **CasAuthenticationFilter** nhận ticket tại callback và **CasAuthenticationProvider** dùng CAS **TicketValidator** kiểm tra ticket với server.

**Điều quan trọng:** CAS protocol với **service ticket (ST)** và **ticket-granting ticket (TGT)** là một giao thức riêng. Dù Apereo CAS server có thể cung cấp SAML2/OIDC, **CasAuthenticationEntryPoint không phải Saml2WebSsoAuthenticationFilter hoặc cấu hình saml2Login()**. Bài này hướng dẫn **CAS native protocol**, không mô tả SAML 2.0 SAMLResponse/Assertion.

Bài sử dụng **Spring Boot 3.3.5, Spring Security 6.x và Java 17** để minh họa. CAS server và URL example.org là ví dụ; muốn kiểm thử đăng nhập end-to-end phải có một **CAS server thật** đã đăng ký service, HTTPS/certificates và tài khoản phù hợp.

### Kết quả học tập

1. Mô tả các vai trò browser, CAS server, Spring SP/service và **CasAuthenticationEntryPoint**.
2. Phân biệt **loginUrl**, **ServiceProperties.service**, **filterProcessesUrl**, **serverPrefix** và URL trang người dùng yêu cầu.
3. Hiểu mối quan hệ **ExceptionTranslationFilter → AuthenticationEntryPoint → redirect → CAS login → ticket callback → ticket validation → SecurityContext**.
4. Cấu hình Java SecurityFilterChain cho **Spring Security 6.x**, không dùng XML namespace kiểu cũ một cách máy móc.
5. Tự dự đoán URL redirect, kiểm mã hóa **service**, xử lý **sendRenew**, cookie, HTTPS, reverse proxy và lỗi service không trùng.
6. Chẩn đoán vòng lặp redirect, ticket invalid, callback không đi qua filter và cấu hình sai quyền truy cập.
7. Kiểm thử không dựa vào việc login trang CAS hiển thị thành công như bằng chứng Spring đã authenticated.

## 2. CAS native protocol: Service, TGT và ST

Bốn khái niệm dễ nhầm:

| Đối tượng | Vai trò |
| --- | --- |
| **CAS server** | Xác thực người dùng tập trung, duy trì phiên SSO, phát ticket cho service được đăng ký. |
| **CAS service / client app** | Ứng dụng Spring Security cần đăng nhập CAS và phải kiểm ticket trước khi tạo local Authentication. |
| **Ticket-Granting Ticket (TGT) và TGC cookie** | CAS dùng để nhận biết browser đã có SSO session tại CAS. Chúng **không phải Spring HttpSession**. |
| **Service Ticket (ST)** | Ticket ngắn hạn, ràng buộc với **service URL**, được browser mang về service; theo CAS protocol, **một ticket chỉ dùng cho một lần validation**. |

Luồng thường thấy:

~~~text
1. Browser: GET https://app.example.org/private
                  |
                  v
2. Spring Security: chưa có Authentication
   ExceptionTranslationFilter -> CasAuthenticationEntryPoint
                  |
                  v
3. HTTP 302 Location:
   https://cas.example.org/cas/login?service=<URL-ENCODED-CALLBACK>
                  |
                  v
4. Browser -> CAS server:
   - chưa có TGC hợp lệ: CAS yêu cầu đăng nhập/MFA tùy chính sách
   - có TGC hợp lệ: CAS có thể phát ST mà không hỏi mật khẩu lại
                  |
                  v
5. CAS -> Browser -> SP callback:
   https://app.example.org/login/cas?ticket=ST-...
                  |
                  v
6. CasAuthenticationFilter lấy ticket
   -> CasAuthenticationProvider
   -> TicketValidator gọi CAS /serviceValidate bằng HTTPS
                  |
                  v
7. CAS xác nhận ticket hợp lệ, đúng service, chưa sử dụng
   -> Spring tạo Authentication, local SecurityContext/session
   -> redirect tới tài nguyên đã yêu cầu hoặc success target
~~~

**Bước 3 chỉ là khởi tạo xác thực.** Ứng dụng không được nhận user là đã đăng nhập chỉ vì browser đi qua CAS login URL, vì chưa xác minh ticket. Trong luồng trên, browser thực hiện **front-channel redirect** còn ứng dụng gửi request **back-channel** đến CAS để kiểm ticket.

### Ví dụ URL

Giả sử:

~~~text
CAS loginUrl:
  https://cas.example.org/cas/login

CAS server prefix:
  https://cas.example.org/cas

Service callback / ServiceProperties.service:
  https://app.example.org/login/cas

Resource browser ban đầu muốn xem:
  https://app.example.org/private
~~~

Khi một request chưa authenticated bị chặn, entry point có thể gửi:

~~~http
HTTP/1.1 302 Found
Location: https://cas.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas
~~~

CAS sau login có thể trả browser tới:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/login/cas?ticket=ST-EXAMPLE-ONE-TIME
~~~

**ST-EXAMPLE-ONE-TIME chỉ là ký hiệu mô tả**, không phải service ticket thật. Ticket thực chỉ được tin sau khi server Spring dùng **TicketValidator** xác minh với CAS server, gồm service URL khớp.

Một request tới **/private** và một service callback **/login/cas** là **hai URL khác nhau**. **ServiceProperties.service** thông thường trỏ tới **callback** mà CAS filter xử lý, không trỏ tới bất kỳ trang private nào user vừa yêu cầu.

## 3. CasAuthenticationEntryPoint thực sự làm gì?

Lớp **org.springframework.security.cas.web.CasAuthenticationEntryPoint** triển khai **AuthenticationEntryPoint** và **InitializingBean**. Các thành phần cốt lõi:

~~~java
CasAuthenticationEntryPoint entryPoint = new CasAuthenticationEntryPoint();
entryPoint.setLoginUrl("https://cas.example.org/cas/login");
entryPoint.setServiceProperties(serviceProperties);
entryPoint.setEncodeServiceUrlWithSessionId(false);
~~~

**Đoạn này chỉ minh họa khởi tạo**, cần biến serviceProperties và cấu hình SecurityFilterChain. Ví dụ đầy đủ ở phần sau.

| Thuộc tính/API | Tác dụng |
| --- | --- |
| **setLoginUrl(String)** | URL **CAS server /login** để browser được redirect tới. |
| **setServiceProperties(ServiceProperties)** | Cung cấp thông tin service của ứng dụng, nhất là **service callback URL** và renew policy. |
| **commence(request, response, exception)** | Được ExceptionTranslationFilter gọi để bắt đầu login; tạo CAS redirect response. |
| **createServiceUrl(...)** | Xây service URL có liên quan request, mặc định dựa vào CAS client utility và ServiceProperties. |
| **createRedirectUrl(serviceUrl)** | Tạo login redirect URL có tham số service, theo CAS client. |
| **preCommence(...)** | Extension hook nếu cần tiền xử lý trước redirect; không nên tự sửa trust/điểm đến tùy tiện. |
| **setRedirectStrategy(...)** | Chọn chiến lược redirect khi cần custom behavior, không tự thay ticket validation. |
| **setEncodeServiceUrlWithSessionId(false)** | Tránh đưa servlet session ID vào URL service khi không cần; giữ session ID trong cookie an toàn. |

**Không nhầm phương thức commence với authenticate:** nó không đọc form password của CAS, không gọi /serviceValidate, không parse ticket và không cấp GrantedAuthority.

### ExceptionTranslationFilter gọi khi nào?

Với request được đánh dấu **authenticated()** trong SecurityFilterChain:

1. Request qua các filters; không có Authentication hợp lệ.
2. **AuthorizationFilter** thấy tài nguyên yêu cầu xác thực và từ chối.
3. **ExceptionTranslationFilter** nhận AccessDeniedException/AuthenticationException phù hợp; với user anonymous/unauthenticated, nó gọi entry point.
4. Request có thể được **RequestCache** lưu để trả về sau login.
5. CasAuthenticationEntryPoint gửi redirect tới CAS.

**User đã authenticated nhưng thiếu quyền** cần được trả **403 Forbidden** bởi authorization policy, không mặc nhiên bị redirect CAS vô hạn. Nếu mọi 403 lại thành redirect, kiểm lại access-denied handling và thứ tự filter.

### Tách ba URL quan trọng

- **loginUrl:** CAS server nhận browser, ví dụ **https://cas.example.org/cas/login**.
- **service URL:** URL public của ứng dụng Spring **nhận ST**, ví dụ **https://app.example.org/login/cas**.
- **filterProcessesUrl:** path tại Spring mà CasAuthenticationFilter lắng nghe, mặc định **/login/cas**. Nó là **path**, không phải URL CAS server.

**Cas20ServiceTicketValidator** lại nhận **CAS server prefix**, thường là **https://cas.example.org/cas**, để tạo endpoint **/serviceValidate**. Không dùng loginUrl có hậu tố /login làm serverPrefix rồi tạo **/login/serviceValidate** sai.

## 4. ServiceProperties và điều kiện khớp service

**org.springframework.security.cas.ServiceProperties** chứa những cấu hình có ý nghĩa với CAS service.

~~~java
ServiceProperties properties = new ServiceProperties();
properties.setService("https://app.example.org/login/cas");
properties.setSendRenew(false);
~~~

Giá trị **service** phải khớp service mà CAS server phát ticket cho, và URL callback phải thuộc phạm vi **CasAuthenticationFilter** xử lý. CAS protocol yêu cầu ticket chỉ hợp lệ cho **service identifier được chỉ định khi phát hành**.

### Quy tắc URL nhất quán

| Chỗ xuất hiện service | Giá trị đúng về mặt logic |
| --- | --- |
| Redirect từ SP đến **CAS /login?service=...** | URL HTTPS callback public, đã URL-encode. |
| CAS redirect browser về callback | Callback URL ấy, thêm **ticket** query parameter. |
| CAS filter đang giám sát | **/login/cas** ở context path ứng dụng phù hợp. |
| Ticket validation ở CAS | **service URL tương ứng ticket** (không lẫn URL tài nguyên ban đầu). |
| CAS server service registry | Chấp thuận service URL/hostname/path chính xác theo policy. |

Ví dụ **service=https://app.example.org/login/cas** và CAS callback tới **http://localhost:8080/login/cas** không đương nhiên bằng nhau. Sự khác biệt scheme **http/https**, host, port, path, context path hoặc encoding có thể gây **INVALID_SERVICE** hoặc ticket validation fail.

**Không dùng service URL được lấy thẳng từ query parameter/Host header chưa tin cậy.** CAS server nên có **registered services allowlist** chặt, HTTPS, không wildcard mở. SP nên giữ public service URL được operator cấu hình cố định hoặc chỉ dựng từ forwarded headers do reverse proxy đáng tin cung cấp.

### sendRenew: true khác false

- **sendRenew(false):** CAS có thể dùng SSO session sẵn có (TGC/TGT) và phát ST mà không yêu cầu nhập password lại.
- **sendRenew(true):** thêm yêu cầu **renew** vào CAS login và ticket validation để đòi ticket phát từ việc người dùng xác thực trực tiếp, theo CAS protocol.
- **renew không phải mặc định là MFA**; quy tắc MFA/step-up phụ thuộc CAS server và chính sách tổ chức.
- **renew không có nghĩa** tắt TGC, xóa SP session hoặc cho phép proxy tickets.
- **gateway=true** là chế độ thử SSO không tương tác, khác renew; kết hợp gateway và renew không có ngữ nghĩa được CAS protocol bảo đảm. CasAuthenticationEntryPoint thông thường không phải gateway redirect filter.

Chỉ bật renew nếu nghiệp vụ đòi tái xác thực và CAS server được cấu hình tương ứng; cần kiểm hành vi ticket validator khi renew=true.

## 5. Filter và provider: vì sao entry point chưa đủ?

Ba lớp thường đi cùng:

| Thành phần | Input | Output/việc làm |
| --- | --- | --- |
| **CasAuthenticationEntryPoint** | Request chưa authenticated cần quyền. | **HTTP redirect** tới CAS /login với service. |
| **CasAuthenticationFilter** | Browser quay về **/login/cas?ticket=ST-...**. | Tạo authentication request token rồi gọi AuthenticationManager. |
| **CasAuthenticationProvider** | CAS ticket authentication token. | Nhờ TicketValidator kiểm ST với CAS; nạp UserDetails/authorities, tạo CasAuthenticationToken. |
| **TicketValidator** (Apereo CAS Java Client) | ST + service URL + CAS server prefix. | Gọi CAS /serviceValidate hoặc profile tương ứng; parse thành công/thất bại. |
| **SecurityContext** và local HttpSession | Authentication đã được provider xác nhận. | Duy trì login ở ứng dụng Spring cho request tiếp theo. |

Nếu cấu hình **chỉ CasAuthenticationEntryPoint**, browser có thể đến CAS login, trở về callback, rồi lại bị redirect login liên tục vì **chưa có filter/provider xử lý ticket**.

### CasAuthenticationFilter mặc định

Ở Spring Security 6.3, **CasAuthenticationFilter** mặc định xử lý **/login/cas**. Trong cấu hình Java có thể đặt rõ:

~~~java
CasAuthenticationFilter filter = new CasAuthenticationFilter();
filter.setFilterProcessesUrl("/login/cas");
filter.setServiceProperties(serviceProperties);
filter.setAuthenticationManager(authenticationManager);
~~~

Đây là đoạn giải thích cần variables có thật; xem phần 8 để có project đầy đủ. Phải gắn filter vào **SecurityFilterChain** đúng vị trí (ví dụ trước UsernamePasswordAuthenticationFilter).

### CasAuthenticationProvider

Provider cần:

- **ServiceProperties** cùng service của entry point/filter.
- Một **TicketValidator**, ví dụ **org.apereo.cas.client.validation.Cas20ServiceTicketValidator** từ Apereo Java CAS Client.
- **UserDetailsService** hoặc **AuthenticationUserDetailsService** lấy account/authorities ở phía ứng dụng.
- **key** cho provider, là một **identifier nội bộ** dùng nhận diện token, không phải private signing key.
- Chính sách account active, membership, roles/authorization sau CAS authentication.

Ví dụ CAS server đã xác thực **alice** nhưng ứng dụng chỉ cho user **bob**: nếu UserDetailsService không có alice hoặc user bị disable, ứng dụng có thể vẫn từ chối. **CAS login success không tự cấp mọi local role.**

### CAS 2.0/3.0 endpoint

- **/login**: CAS nhận browser và phát service ticket.
- **/serviceValidate**: CAS server kiểm ST, thường trả XML.
- **/p3/serviceValidate**: CAS protocol 3.0 có thể trả thêm attributes theo profile.
- **/proxyValidate**: được dùng nếu cần xử lý proxy tickets và proxy trust; không mở mặc định nếu không cần.
- **/logout**: CAS logout endpoint, khác với logout session ứng dụng Spring.

**Spring Security CAS integration là CAS native protocol, không dùng saml2Login() để thay CasAuthenticationFilter.** CAS server có thể hỗ trợ SAML2 riêng, nhưng đó là một integration khác.

## 6. Java 17 độc lập: tự tạo redirect URL để hiểu mã hóa

Chương trình **CasRedirectUrlDemo.java** dùng JDK 17, **không cần CAS server hoặc Spring**. Nó chứng minh cách thêm query parameter service khi xây URL ví dụ. Đây là **mô phỏng URL**, không thay thế CasAuthenticationEntryPoint hoặc kiểm ticket; trong production để Spring CAS Client xây redirect.

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class CasRedirectUrlDemo {
    private static String create(String loginUrl, String service, boolean renew) {
        if (loginUrl.contains("?")) {
            throw new IllegalArgumentException("Demo requires plain login URL");
        }
        String encodedService = URLEncoder.encode(
                service, StandardCharsets.UTF_8);
        return loginUrl + "?service=" + encodedService
                + (renew ? "&renew=true" : "");
    }

    public static void main(String[] args) {
        String loginUrl = "https://cas.example.org/cas/login";
        String service = "https://app.example.org/login/cas";

        System.out.println("default=" + create(loginUrl, service, false));
        System.out.println("renew=" + create(loginUrl, service, true));
        System.out.println("callback=" + service);
    }
}
~~~

Chạy:

~~~bash
javac CasRedirectUrlDemo.java
java CasRedirectUrlDemo
~~~

**stdout chính xác:**

~~~text
default=https://cas.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas
renew=https://cas.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&renew=true
callback=https://app.example.org/login/cas
~~~

Giải thích:

- **service** được encode thành **https%3A%2F%2Fapp.example.org%2Flogin%2Fcas** khi là giá trị query param.
- Sau khi CAS parse query, service logic vẫn là **https://app.example.org/login/cas**.
- **renew=true** chỉ là parameter gửi CAS, chưa chứng minh CAS thực sự bắt user đăng nhập lại; cần test CAS server và TicketValidator.
- Ví dụ không xử lý login URL có query string từ trước, dấu fragment, proxy headers hoặc URL cấu hình không hợp lệ. Sử dụng component của Spring/CAS cho production.
- Không gọi trực tiếp redirect URL với **service do browser cung cấp** vì có thể dẫn đến open redirect hoặc cấp ticket cho service không được phê duyệt.

## 7. Cấu hình môi trường: có những URL nào?

Mục tiêu project:

~~~text
Spring SP public URL:
  https://app.example.org

Spring CAS callback:
  https://app.example.org/login/cas

CAS base/serverPrefix:
  https://cas.example.org/cas

CAS loginUrl:
  https://cas.example.org/cas/login

CAS validation endpoint:
  https://cas.example.org/cas/serviceValidate
~~~

**Service callback và base URL phải được CAS admin đăng ký.** Nếu app chạy nội bộ tại **http://sp-a:8080** sau reverse proxy HTTPS, CAS vẫn phải redirect tới **https://app.example.org/login/cas**, không phải internal host. CAS app phải có DNS và TLS trust đúng; browser phải đến được loginUrl, còn Spring backend phải kết nối được đến serverPrefix trên HTTPS.

Kiểm:

1. DNS/TLS của **cas.example.org** dùng từ browser và từ Spring backend (backend gọi /serviceValidate).
2. **app.example.org** có HTTPS public, proxy map **/login/cas** đúng path tới Spring.
3. CAS registered service allowlist có exact callback URL đúng scheme/host/path.
4. **ServiceProperties.service** giống callback được công bố.
5. **CasAuthenticationFilter** xử lý đúng **/login/cas**, không bị filter/security chain khác chặn.
6. CAS client có quyền nạp local user/roles sau successful ticket validation.
7. Cookie SP có **Secure/HttpOnly/SameSite** phù hợp, request cache/session hoạt động.
8. Không tự dùng **ticket** trong query làm Authentication mà không validate back-channel.

## 8. Ví dụ Spring Boot 3.3.5 / Spring Security 6.x hoàn chỉnh

Đây là ứng dụng Spring MVC minh họa luồng CAS native. **User alice** được định nghĩa cục bộ chỉ để kiểm luồng và cấp ROLE_USER; **CAS server phải có tài khoản alice** để chạy hết flow. Các cấu hình CAS URL là example.org, nên chưa có server thật thì bạn chỉ quan sát được redirect, không thể hoàn tất ticket validation.

### 8.1. pom.xml

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>spring-cas-entry-point-demo</artifactId>
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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-cas</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

**spring-security-cas** là mô-đun tích hợp CAS native của Spring Security; không dùng **spring-security-saml2-service-provider** để triển khai lớp CasAuthenticationEntryPoint. Dependencies của CAS Java Client (đặc biệt **cas-client-core**) thường được lấy qua module CAS; khi nâng version cần kiểm **mvn dependency:tree** và bảo đảm tương thích Spring Security/Spring Boot/Jakarta Servlet của toàn dependency graph. Không tự thêm version client mới nhất nếu làm xung đột với thư viện Spring đang dùng.

### 8.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

app:
  cas:
    login-url: "https://cas.example.org/cas/login"
    server-prefix: "https://cas.example.org/cas"
    service-url: "https://app.example.org/login/cas"
    send-renew: false
~~~

Ba URL không được đổi lẫn:

- **login-url** dùng cho browser redirect.
- **server-prefix** dùng cho TicketValidator xây URL kiểm ST.
- **service-url** dùng trong query service khi redirect login và **service** khi validate ticket.

Trong hệ thống thật, lấy giá trị từ cấu hình quản trị/secret store/environment thay vì giả định hostname cố định; URL public **https://app.example.org** phải map tới app đang chạy. Example.org không có CAS server production.

### 8.3. Application main

**src/main/java/com/example/casdemo/CasDemoApplication.java**

~~~java
package com.example.casdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasDemoApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig: entry point, filter, provider và chain

**src/main/java/com/example/casdemo/SecurityConfig.java**

~~~java
package com.example.casdemo;

import java.util.List;
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String serviceUrl,
            @Value("${app.cas.send-renew:false}") boolean sendRenew) {
        ServiceProperties properties = new ServiceProperties();
        properties.setService(serviceUrl);
        properties.setSendRenew(sendRenew);
        return properties;
    }

    @Bean
    CasAuthenticationEntryPoint casAuthenticationEntryPoint(
            ServiceProperties serviceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {
        CasAuthenticationEntryPoint entryPoint =
                new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(loginUrl);
        entryPoint.setServiceProperties(serviceProperties);
        entryPoint.setEncodeServiceUrlWithSessionId(false);
        return entryPoint;
    }

    @Bean
    UserDetailsService localUsers() {
        // Chỉ để kiểm thử: CAS quyết định authentication.
        // Spring app giữ chính sách account/authorities riêng.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}not-used-by-cas")
                .authorities("ROLE_USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties serviceProperties,
            UserDetailsService localUsers,
            @Value("${app.cas.server-prefix}") String casPrefix) {
        CasAuthenticationProvider provider = new CasAuthenticationProvider();
        provider.setServiceProperties(serviceProperties);
        provider.setTicketValidator(
                new Cas20ServiceTicketValidator(casPrefix));
        provider.setUserDetailsService(localUsers);
        provider.setKey("demo-cas-provider-id");
        return provider;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    CasAuthenticationFilter casAuthenticationFilter(
            CasAuthenticationProvider provider,
            ServiceProperties serviceProperties,
            SecurityContextRepository securityContextRepository) {
        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setFilterProcessesUrl("/login/cas");
        filter.setServiceProperties(serviceProperties);
        filter.setAuthenticationManager(
                new ProviderManager(List.of(provider)));
        // Custom CAS filters must explicitly persist authentication in Spring Security 6.
        filter.setSecurityContextRepository(securityContextRepository);
        // Rotate an existing session ID after successful CAS authentication.
        filter.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());
        return filter;
    }

    @Bean
    FilterRegistrationBean<CasAuthenticationFilter> disableServletRegistration(
            CasAuthenticationFilter filter) {
        // Filter là bean nên Boot có thể auto-register thành Servlet filter.
        // Vô hiệu đăng ký độc lập; chỉ dùng nó bên trong SecurityFilterChain.
        FilterRegistrationBean<CasAuthenticationFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(filter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CasAuthenticationEntryPoint entryPoint,
            CasAuthenticationFilter casFilter,
            SecurityContextRepository securityContextRepository) throws Exception {
        http
            .securityContext(context -> context
                .securityContextRepository(securityContextRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .addFilterBefore(
                casFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Giải thích vì sao các bean này cần thiết:**

1. **ServiceProperties:** cùng service callback HTTPS, sendRenew policy và ticket validation.
2. **CasAuthenticationEntryPoint:** được ExceptionTranslationFilter dùng khi cần CAS login; tạo Location đến CAS loginUrl.
3. **CasAuthenticationFilter:** xử lý ticket trên path **/login/cas**, gọi AuthenticationManager.
4. **ProviderManager(CasAuthenticationProvider):** gửi authentication request token từ filter đến đúng CAS provider, giúp kiểm ST.
5. **Cas20ServiceTicketValidator:** kiểm CAS service ticket qua CAS serverPrefix, trên HTTPS với TLS trust hợp lệ.
6. **UserDetailsService:** cung cấp local authorities; không đồng nghĩa CAS server có các accounts ấy. Ví dụ chỉ alice được resolve; production dùng database/identity mapping thực tế.
7. **FilterRegistrationBean disabled:** CasAuthenticationFilter đã được đưa vào Spring Security chain, nên phải tránh Boot tự đăng ký nó như servlet filter độc lập **lần thứ hai**.
8. **SecurityFilterChain.exceptionHandling:** nối entry point vào ExceptionTranslationFilter. Nếu thiếu, có thể gặp trang login mặc định của Spring hoặc HTTP 401/403 không theo mong muốn.
9. **addFilterBefore:** đảm bảo CAS filter tham gia đúng chain và bắt callback **/login/cas**. Không chỉ đăng ký filter bean rồi kỳ vọng Spring Security tự dùng nó.
10. **Không gọi formLogin() hoặc saml2Login()** cho ví dụ này; có thể tích hợp đa cơ chế nhưng phải đặt request matchers/entry points theo từng phạm vi thay vì trộn toàn cục.

11. **SecurityContextRepository:** Spring Security 6 yêu cầu custom `AbstractAuthenticationProcessingFilter` tự cấu hình repository nếu muốn giữ kết quả xác thực qua request. Bean `DelegatingSecurityContextRepository` phối hợp `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`. `CasAuthenticationFilter` và `SecurityFilterChain` dùng cùng bean để callback CAS lưu `Authentication` vào HTTP session và request `/private` sau đó đọc lại được.
12. **Session fixation:** `ChangeSessionIdAuthenticationStrategy` được gắn vào custom CAS filter. Nếu đã có session trước khi xác thực thành công, servlet container đổi session ID và giữ dữ liệu session, ngăn session fixation.

**Lưu ý production:** phương án UserDetailsService in-memory và role ROLE_USER chỉ minh họa cho alice, không thay local account provisioning/authorization, không dùng mật khẩu {noop} cho ứng dụng có form-login. Giá trị **provider.setKey** là chuỗi nhận diện provider, không phải encryption key; đặt identifier duy nhất và ổn định theo thiết kế.

### 8.5. Controller

**src/main/java/com/example/casdemo/ExampleController.java**

~~~java
package com.example.casdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ExampleController {

    @GetMapping("/")
    public String home() {
        return "CAS entry point demo ready";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "CAS authenticated: " + authentication.getName();
    }
}
~~~

Khi chưa đăng nhập, **GET /private** bị security filter chặn trước controller. Sau khi CAS cấp ticket hợp lệ và provider tìm được user alice, endpoint có thể trả **CAS authenticated: alice**. Nếu CAS trả user không có trong local user service, bước hoàn tất authentication có thể fail; ví dụ chủ động không tự cấp ROLE_USER cho mọi tên từ CAS.

### 8.6. Regression test: callback CAS phải giữ đăng nhập ở request tiếp theo

Bổ sung `spring-boot-starter-test` (test scope) trong `pom.xml`. Test này **mock CAS provider** để cô lập cơ chế lưu session; nó không thay thế integration test xác minh Service Ticket với CAS server thật.

**src/test/java/com/example/casdemo/CasSessionPersistenceTest.java**

~~~java
package com.example.casdemo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.authentication.CasServiceTicketAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CasSessionPersistenceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    CasAuthenticationProvider casProvider;

    @BeforeEach
    void stubCasProviderWithoutNetwork() {
        when(casProvider.supports(CasServiceTicketAuthenticationToken.class))
                .thenReturn(true);
        when(casProvider.authenticate(any(Authentication.class)))
                .thenReturn(new UsernamePasswordAuthenticationToken(
                        "alice", null, AuthorityUtils.createAuthorityList("ROLE_USER")));
    }

    @Test
    void authenticationSurvivesTheRequestAfterCasCallback() throws Exception {
        MvcResult callback = mvc.perform(
                get("/login/cas").param("ticket", "ST-LOCAL-TEST"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) callback.getRequest().getSession(false);
        assertNotNull(session, "CAS callback must establish a local session");

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("CAS authenticated: alice"));
    }
}
~~~

Chạy `mvn -Dtest=CasSessionPersistenceTest test`. Trước khi cấu hình repository, callback có thể thành công nhưng request `/private` tiếp theo mất đăng nhập và chuyển hướng lại tới CAS. Với repository chung, test khẳng định `Authentication` tồn tại trong session ở request kế tiếp. Kiểm thử thêm việc thay session ID khi có session cũ, timeout/logout và xác minh ticket thật trong môi trường tích hợp.

### 8.7. Khởi động

Ở thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

**Kỳ vọng có thể kiểm ngay từ ứng dụng chưa có CAS server thật:**

- **GET http://localhost:8080/** trả chính xác **CAS entry point demo ready**.
- **GET http://localhost:8080/private** khi anonymous sẽ bị chuyển hướng đến **https://cas.example.org/cas/login?service=...**, theo service-url cấu hình.
- Địa chỉ CAS example.org không phải server thật; browser không thể hoàn tất login tại đó.
- Vì callback đặt **https://app.example.org/login/cas**, hệ thống thật cần HTTPS ingress trỏ về app đang chạy và CAS server đăng ký đúng URL ấy. Một process local chỉ có HTTP **localhost:8080** không đủ cho end-to-end.

**Khi có CAS sandbox hợp lệ:**

1. Mở **https://app.example.org/private**.
2. Quan sát HTTP 302 từ SP sang **/cas/login?service=...**.
3. Đăng nhập CAS bằng tài khoản test **alice**.
4. CAS redirect browser về **https://app.example.org/login/cas?ticket=ST-...**.
5. Spring CasAuthenticationFilter nhận ST, provider gọi **/cas/serviceValidate** bằng HTTPS với cùng service.
6. CAS server trả validation success; Spring đọc alice, localUsers có alice, tạo Authentication.
7. Browser quay lại **/private** (nhờ request cache/success handler mặc định nếu cấu hình phù hợp) và nhận **CAS authenticated: alice**.
8. Request tiếp theo sử dụng local session SecurityContext cho tới khi session hết hạn/logout.

**Đừng coi response 302 bước 2 là QA PASS của authentication**. Chỉ sau bước 6–7 mới chứng minh được CAS server ticket validation và local account mapping.

## 9. Kiểm tra redirect bằng browser và HTTP tools

### Network trace tối thiểu

Dùng browser DevTools → Network:

~~~text
GET /private
  302 Location=https://cas.example.org/cas/login?service=...

GET CAS /cas/login?service=...
  CAS hiển thị login hoặc phát ticket qua SSO cookie

GET /login/cas?ticket=ST-...
  Spring CAS filter xử lý callback

GET /private
  200 khi session CAS validation + local authorization hợp lệ
~~~

Nếu kiểm bằng **curl -I**:

~~~bash
curl -I https://app.example.org/private
~~~

có thể thấy **302** tới CAS login. Nhưng **HEAD** request không nhất thiết giống GET trong mọi app/filter chain; dùng **curl -i -s -D - -o /dev/null** hoặc browser GET để quan sát thực tế. Đừng dùng **curl -L** và khẳng định login thành công chỉ từ chuỗi redirects khi chưa có CAS session.

Không đưa ticket ST thật vào terminal history/ticket public: ST là credential ngắn hạn. Browser DevTools/network logs có thể hiển thị ticket; loại bỏ hoặc che khi chia sẻ.

### Điều cần kiểm trong Location

- Scheme và host của loginUrl đúng CAS server đã phê duyệt.
- **service** khi URL-decode đúng **https://app.example.org/login/cas**.
- Không xuất hiện internal host **http://sp-a:8080** hoặc service của tenant khác.
- Không có session identifier trong URL.
- Nếu sendRenew=true, có **renew** theo protocol và validator cùng chính sách.
- CAS registered service chính xác, không để wildcard tùy tiện.
- Sau callback, request vào CasAuthenticationFilter chứ không bị redirect sang CAS một lần nữa mà không validate ticket.

## 10. Reverse proxy, context path và cookie

### Reverse proxy và external URL

~~~text
Browser HTTPS https://app.example.org/private
         |
         v
Load balancer / ingress (TLS termination)
         |
         v
Spring backend HTTP http://sp-a:8080/private
~~~

**ServiceProperties.service phải là public callback HTTPS**, không phải http://sp-a:8080/login/cas. Nếu app có context path **/portal**, callback có thể là **https://app.example.org/portal/login/cas** còn filterProcessesUrl tương ứng servlet path **/login/cas**. Phải kiểm cấu hình thật của Servlet context và reverse proxy path rewriting.

Nếu SP dựng URL động từ request, chỉ tin forwarded headers do **proxy hợp lệ ghi/ghi đè**. Không dùng nguyên vẹn **X-Forwarded-Host** do Internet có thể tự gửi. Với service URL cấu hình tĩnh, forward header vẫn ảnh hưởng redirects/saved requests nếu web layer xây external links.

### CAS cookie và SP cookie là khác nhau

| Cookie/session | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| **CAS TGC/TGT session** | CAS domain, ví dụ cas.example.org. | Chứng minh browser có phiên CAS SSO để CAS cân nhắc phát ST. |
| **SP HttpSession/JSESSIONID/SESSION** | Application domain, ví dụ app.example.org. | SecurityContext của Spring service sau khi ticket được kiểm. |
| **LB affinity cookie** | Reverse proxy/load balancer. | Giữ browser được route đến một backend, không tạo Authentication. |

Với hai node SP, nếu session chỉ nằm local mà callback/requests sau đi node khác, có thể mất SecurityContext và lặp CAS login. Cần sticky sessions phù hợp hoặc **Spring Session Redis/JDBC**, test cookie/domain/TTL và failover. **CAS server có TGC hợp lệ không có nghĩa SP tự có local Authentication**; SP vẫn phải xử lý ST cho mỗi service/session cần thiết.

### Cookie bảo mật

- SP cookie nên **Secure, HttpOnly**, SameSite phù hợp với flow và host.
- CAS callback mặc định qua **GET** front-channel redirect với ticket. Cookie SameSite=Lax thường phù hợp top-level cross-site GET, nhưng phải thử browser/policy thực; không sao chép máy móc cấu hình SameSite của SAML POST.
- Không viết session ID vào **service URL** hoặc URL query nếu không có yêu cầu/phân tích bảo mật đặc biệt.
- Khi authentication thành công, Spring nên áp dụng session fixation protection/cookie rotation theo security config.
- TLS ở browser↔CAS, browser↔SP và SP backend↔CAS validator phải được bảo vệ theo trust policy.

### Logout không mặc định là SLO

**POST /logout** của Spring thường chỉ vô hiệu hóa SP local session. Người dùng có thể được CAS cấp ST mới ngay vì CAS TGC vẫn còn. Đăng xuất CAS trung tâm cần thiết kế **CAS Single Logout (SLO)**, CAS logout endpoint và filter/notification handling thích hợp. Không hứa rằng gọi SP logout sẽ tự kết thúc mọi phiên CAS/ứng dụng khác.

## 11. Lỗi redirect thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm/sửa |
| --- | --- | --- |
| **/private trả 401 hoặc trang login form** | ExceptionTranslationFilter chưa dùng CasAuthenticationEntryPoint hoặc chain khác match trước. | Kiểm SecurityFilterChain matcher và exceptionHandling authenticationEntryPoint. |
| **Browser tới CAS nhưng CAS báo unrecognized service** | Service URL chưa đăng ký hoặc khác scheme/host/path. | So đúng service URL sau decode với CAS registered service. |
| **CAS login được rồi quay lại /login/cas và lại redirect CAS** | CasAuthenticationFilter chưa được gắn vào security chain, callback không match hoặc ticket validation fail. | Kiểm filterProcessesUrl, thứ tự filter, provider và logs theo reason code. |
| **INVALID_SERVICE khi kiểm ST** | Service ở /login và /serviceValidate không khớp chính xác. | Dùng chung ServiceProperties, public callback ổn định, không tự thêm ticket vào service. |
| **INVALID_TICKET** | ST hết hạn, đã dùng hoặc khác service, proxy ticket bị đưa vào ST validator. | Login lại tạo ST mới, không replay, dùng đúng CAS validation endpoint. |
| **TLS handshake fail khi validate ticket** | Spring backend không tin CAS HTTPS certificate, hostname sai hoặc proxy/TLS. | Sửa truststore/CA/hostname, không tắt certificate verification. |
| **CAS liên tục yêu cầu nhập mật khẩu** | sendRenew=true hoặc TGC không được giữ. | Kiểm renew policy, CAS SSO cookie/browser và user settings. |
| **CAS đăng nhập được nhưng Spring trả user not found** | Local UserDetailsService không chứa CAS username. | Cấu hình account mapping/provisioning đã được phê duyệt; không tự cấp quyền mặc định rộng. |
| **/private 403 sau CAS login** | Authenticated user thiếu required authority. | Kiểm local roles/authorization, không redirect login để bỏ qua role policy. |
| **Callback 404** | Sai context path hoặc reverse proxy không route /login/cas. | Kiểm external URL, ingress rules, filterProcessesUrl. |
| **Location redirect tới http://internal:8080** | service URL/proxy host cấu hình sai hoặc trusted forwarded headers thiếu. | Đặt public HTTPS service, cấu hình proxy đúng. |
| **Ticket xuất hiện trong log và analytics** | Query string bị log nguyên vẹn. | Redact ticket từ access logs/tracing/referrer và redirects. |
| **Spring CAS filter chạy hai lần** | Đăng ký filter bean và servlet filter tự động, lại add vào SecurityFilterChain. | Dùng FilterRegistrationBean disabled như mẫu. |
| **Không redirect sau khi login về trang trước** | RequestCache hoặc success handler thay đổi, session mất. | Kiểm saved request, local HttpSession, SameSite/affinity và success handler. |
| **CAS login ST hợp lệ nhưng sai tenant** | Chỉ kiểm CAS username rồi map tất cả vào một organization. | Account mapping + tenant membership sau CAS validation; không tin URL/header. |
| **ST bị validate lại và fail** | CAS ST là one-time token. | Không retry cùng ST; bắt đầu flow login mới. |

Phân biệt **redirect fail** (chưa tới CAS), **CAS login fail**, **ticket-validation fail**, **local user/role fail** và **session fail**. Những nhóm lỗi này có cách sửa khác nhau.

## 12. Những quyết định bảo mật quan trọng

### CAS server phải whitelist service URL

CAS protocol khuyến nghị server chỉ redirect/issue ticket cho **registered authorized services**. Nếu CAS cho phép service tùy ý, kẻ tấn công có thể tận dụng để thực hiện open redirect hoặc phishing/ticket misuse. SP cần gửi service URL ổn định; CAS server registry kiểm host/scheme/path và chính sách service.

### Không coi ST trong query là bằng chứng duy nhất

- ST phải được kiểm **server-to-server** qua HTTPS với CAS server tin cậy.
- Kết quả validation phải ràng buộc với **service** được phát ticket.
- ST phải ngắn hạn, chỉ dùng một lần; sau login tránh lưu raw ST.
- Không log ticket thật vào app logs, analytics, error traces hoặc URL chia sẻ.
- Không viết endpoint **/login/cas** tự động cho bất cứ ai có query **ticket** mà bỏ CasAuthenticationProvider.

### CAS identity và local authority

CAS server xác thực danh tính theo protocol, còn SP quyết định tài khoản có được truy cập app không. Tên người dùng trùng nhau ở hai CAS servers không tự cùng account. Trong hệ thống đa tổ chức, identity binding nên kèm **trusted CAS server/service domain** và stable subject, tenant membership và role per organization. Không lấy request header **X-User** làm username thay cho TicketValidator.

### Renew không phải chống mọi attack

renew có thể yêu cầu xác thực trực tiếp lại; nó không thay TLS, ticket one-time, CSRF, session management hoặc authorization. Bật renew có thể gây trải nghiệm đăng nhập lại thường xuyên; phải thống nhất policy theo chức năng rủi ro.

### Không dùng http/localhost ở production

CAS server login, CAS service callback và ticket validation nên sử dụng **HTTPS công khai có hostname đáng tin**. Local HTTP chỉ phục vụ demo với sandbox được kiểm soát; không mở service registry chấp nhận mọi HTTP host vào production để “làm cho ticket validation pass”.

### Không nhầm OAuth2, SAML2 và CAS

| Giao thức | Redirect/Callback thường gặp | Token/artifact trả về |
| --- | --- | --- |
| **CAS native** | /cas/login?service=..., /login/cas | **Service Ticket**, kiểm bằng CAS /serviceValidate. |
| **SAML2 Web Browser SSO** | IdP SSO endpoint, SP ACS | **SAMLResponse/Assertion**, kiểm XML signature/profiles. |
| **OAuth2/OIDC authorization code** | Authorization endpoint, redirect_uri | **authorization code**, đổi token tại token endpoint; OIDC thêm ID Token. |

Apereo CAS server hỗ trợ nhiều giao thức, nhưng **CasAuthenticationEntryPoint** thuộc CAS native integration. Khi làm bài này phải dùng **spring-security-cas**, không mô tả saml2Login() là cùng một filter.

## 13. Kiểm thử positive và negative

Nên có **CAS sandbox** phát ticket hợp lệ, service registry cố định và một user test, kèm unit tests không cần server cho entry point URL. **Không công bố ST thật trong báo cáo**.

| # | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| 1 | Anonymous GET /private | 302 tới CAS loginUrl với service encoded đúng. |
| 2 | Authenticated GET /private | Không redirect CAS; cho qua authorization. |
| 3 | Anonymous GET / | 200 public, không gọi CAS. |
| 4 | CAS đã có TGC, sendRenew=false | CAS có thể phát ST không hỏi password theo policy. |
| 5 | sendRenew=true, CAS user có SSO session | CAS đòi đăng nhập trực tiếp lại theo renew policy. |
| 6 | CAS loginUrl nhầm server prefix, thiếu /login | Browser tới endpoint sai; kiểm Location. |
| 7 | service URL sai host/path so với registered service | CAS từ chối service hoặc ticket validation fail. |
| 8 | App ở reverse proxy HTTPS nhưng service là http://internal | Không được chấp nhận; sửa external URL. |
| 9 | Callback đúng /login/cas?ticket=ST hợp lệ | Filter/provider validate, tạo Authentication. |
| 10 | Callback không match filterProcessesUrl | Không có Authentication; bị 404/redirect/401 theo chain. |
| 11 | Có entry point nhưng thiếu CasAuthenticationFilter | Login loop, không xử lý ST. |
| 12 | Có filter nhưng thiếu CasAuthenticationProvider | AuthenticationManager không xử lý ST; fail. |
| 13 | CAS server /serviceValidate unreachable | Login fail có kiểm soát; không bỏ validator. |
| 14 | CAS HTTPS hostname/certificate sai | TLS validation fail; không tắt verify. |
| 15 | ST bị validate lần thứ hai | CAS trả invalid ticket; không replay. |
| 16 | ST được phát cho service A nhưng validate với service B | CAS từ chối service mismatch. |
| 17 | CAS user alice hợp lệ, local account alice enabled | Có thể hoàn tất login và ROLE_USER. |
| 18 | CAS user khác chưa có local account | Login business mapping fail, không tự cấp admin. |
| 19 | User authenticated thiếu quyền admin | 403, không redirect lại CAS vô hạn. |
| 20 | Truy cập /private sau login ở node khác với local sessions | Có thể mất SecurityContext; dùng sticky/shared store tùy SLA. |
| 21 | Hai apps có cùng CAS TGC nhưng khác SP sessions | Mỗi app cần local ST validation/session riêng. |
| 22 | CAS logout chỉ kết thúc CAS session | SP session không nhất thiết tự mất nếu chưa có CAS SLO. |
| 23 | SP logout nhưng CAS TGC còn | Browser có thể được CAS SSO lại; test logout policy. |
| 24 | User gửi service callback URL do client tự chọn | Không để tạo trusted redirect/service không nằm trong registry. |
| 25 | Spring filter được Boot auto-register cộng với addFilterBefore | Test phát hiện xử lý trùng; tắt servlet registration độc lập. |
| 26 | Browser gửi ticket giả, không do CAS cấp | Validator từ chối, không tạo Authentication. |
| 27 | CAS admin tắt service registration | CAS /login từ chối hoặc /serviceValidate thất bại theo policy. |
| 28 | Saved request bị mất nhưng CAS login thành công | Có thể về success target mặc định, không chứng minh ST fail. |
| 29 | CAS credential đã xác thực nhưng tenant/role không hợp lệ | SP deny business access, không nâng quyền. |
| 30 | CAS và SP dùng đường proxy sai port/HTTPS | Invalid service/redirect mismatch; sửa URL topology. |

**Negative test đạt** khi ứng dụng từ chối chính xác điều không hợp lệ, chứ không phải khi tắt ticket validation để login được bằng mọi giá.

### Kiểm tra nhanh ở trình duyệt

1. Mở **/private** khi chưa có SP session.
2. Đọc **HTTP response status** và **Location** của redirect đầu tiên.
3. URL-decode **service**; so với ServiceProperties.service và CAS service registry.
4. Hoàn tất login trên CAS sandbox, xem browser quay về đúng **/login/cas?ticket=...**.
5. Xác minh backend có gọi **/serviceValidate** thành công.
6. Xem HTTP redirect sau ticket validation tới trang yêu cầu và thử một request authenticated nữa.
7. Logout SP rồi truy cập lại, phân biệt TGC CAS và SP local session.
8. Thử ST cũ một lần nữa, service khác, renew policy và lỗi network/TLS.

## 14. Những lỗi phổ biến cần tránh

1. **Nghĩ CasAuthenticationEntryPoint đã xác thực user.** Nó chỉ redirect.
2. **Đặt loginUrl bằng service URL hoặc ngược lại.** Một URL thuộc CAS server, một URL thuộc SP.
3. **Đặt ServiceProperties.service bằng /private** thay vì callback mà CAS filter giám sát.
4. **Dùng CasAuthenticationFilter nhưng quên setAuthenticationManager/CasAuthenticationProvider.**
5. **Quên addFilterBefore filter vào SecurityFilterChain.**
6. **Bật filter bean hai lần** do servlet auto registration của Boot.
7. **Đặt server-prefix bằng .../cas/login** rồi validator tạo path sai.
8. **Cho CAS registered services wildcard quá rộng** làm giảm kiểm soát redirect/ticket.
9. **Tắt certificate validation** để tránh lỗi TLS giữa SP và CAS.
10. **Tin ticket từ query mà không gọi CAS validation**.
11. **Tái sử dụng một ST nhiều lần** trong khi protocol chỉ cho phép một lần validation.
12. **Log ticket đầy đủ trong access logs**, gây rò credential ngắn hạn.
13. **Nhầm CAS native với SAML2/OIDC** khi cấu hình filters.
14. **Bỏ quyền app vì CAS đã authenticated**, không kiểm role/tenant.
15. **Gắn tất cả CAS users vào ROLE_ADMIN** bằng một UserDetailsService mặc định rộng.
16. **Coi SP logout là CAS Single Logout** trong khi TGC CAS còn.
17. **Coi sendRenew=true là đã bật MFA cho mọi hệ thống**, không kiểm CAS policy.
18. **Dựng service URL từ Host/X-Forwarded-Host chưa tin cậy**.
19. **Không phân biệt URL public HTTPS với backend localhost HTTP**.
20. **Mất session do load balancer rồi cho rằng ticket validation hỏng**, không kiểm cookie/shared session.

## 15. Checklist triển khai production

**Thiết lập protocol và routing:**

- [ ] Xác định đúng **CAS native protocol**; server đang cung cấp /login và /serviceValidate tương ứng.
- [ ] **loginUrl=https://CAS_HOST/cas/login** và **serverPrefix=https://CAS_HOST/cas** nhất quán.
- [ ] **ServiceProperties.service** là HTTPS callback public, được CAS server registry cho phép.
- [ ] **filterProcessesUrl** match callback, tính cả context path và proxy rewrite.
- [ ] ExceptionTranslationFilter thực sự chọn **CasAuthenticationEntryPoint** cho tài nguyên CAS-protected.
- [ ] CasAuthenticationFilter và CasAuthenticationProvider hoạt động cùng TicketValidator, UserDetailsService.
- [ ] Chỉ đăng ký CAS filter một lần trong security chain, không có servlet auto registration trùng.
- [ ] Saved request/redirect sau login được kiểm với HTTPS và session thật.

**An ninh:**

- [ ] CAS login + ticket validation dùng HTTPS, truststore và hostname verification đúng.
- [ ] CAS service registry allowlist chặt; không cho service do client tự tạo.
- [ ] ST được kiểm server-to-server, một lần, gắn service; không log/referrer leak.
- [ ] Session SP cookie Secure/HttpOnly/SameSite phù hợp và session fixation protection hoạt động.
- [ ] Đặt **sendRenew** đúng business requirement; kiểm renew không được hiểu nhầm thành MFA.
- [ ] Phân quyền local UserDetails/tenant sau CAS validation, không tự cấp quyền mọi CAS user.
- [ ] Có logout/SLO policy riêng cho CAS TGC và SP local session.

**Vận hành và QA:**

- [ ] Có CAS sandbox và user test, không dùng domain example.org làm dữ liệu production.
- [ ] Kiểm cả redirect location, validation response và authenticated resource, không chỉ 302.
- [ ] Test invalid ticket, used ticket, wrong service, TLS failure, missing role và user disabled.
- [ ] Test reverse proxy, load balancer multi-node/session persistence và session timeout.
- [ ] Log request trace/HTTP status/reason code có che ticket/PII/secrets.
- [ ] Theo dõi CAS server/version, CAS client và Spring Security 6.x compatibility trước khi upgrade.

## 16. Câu hỏi ôn tập

**Câu 1.** CasAuthenticationEntryPoint có tạo CasAuthenticationToken khi redirect không?  
**Đáp án:** **Không.** Nó chỉ bắt đầu CAS login bằng HTTP redirect. Filter và provider xử lý ST sau callback.

**Câu 2.** Vì sao service=https://app.example.org/login/cas không giống loginUrl=https://cas.example.org/cas/login?  
**Đáp án:** loginUrl thuộc CAS server nhận browser; service là URL callback của SP nhận ST, và phải được CAS registry/validator khớp.

**Câu 3.** Người dùng login CAS thành công, browser có ticket, nhưng Spring vẫn lặp CAS login. Nên kiểm gì?  
**Đáp án:** CasAuthenticationFilter có xử lý /login/cas không, provider/validator có hoạt động không, service URL khớp không và SecurityContext/session có được lưu không.

**Câu 4.** sendRenew=true có đồng nghĩa chắc chắn CAS đã thực hiện MFA?  
**Đáp án:** **Không.** Renew yêu cầu xác thực trực tiếp, MFA là chính sách của CAS server cần kiểm riêng.

**Câu 5.** CAS đã có TGC nên browser được SSO. Vì sao Spring vẫn phải validate ST?  
**Đáp án:** CAS TGC quản lý SSO tại CAS; SP chỉ tin ST được CAS phát đúng service và xác minh server-to-server, rồi mới lập local Authentication.

**Câu 6.** CAS trả ST cho app.example.org nhưng Spring validate với localhost:8080. Điều gì xảy ra?  
**Đáp án:** Thường ticket validation thất bại do service mismatch; cần dùng public HTTPS service URL nhất quán.

**Câu 7.** Vì sao tắt servlet auto-registration của CasAuthenticationFilter bean trong ví dụ?  
**Đáp án:** Vì filter đã được đăng ký bằng addFilterBefore bên trong SecurityFilterChain; auto registration bên ngoài có thể khiến chạy hai lần/sai thứ tự.

**Câu 8.** CAS login có thể dùng saml2Login() thay CasAuthenticationEntryPoint không?  
**Đáp án:** Không cho CAS native ST flow. saml2Login() dùng SAML2 Response/Assertion; nếu CAS server đóng vai trò SAML2 IdP là một cấu hình SAML2 riêng.

**Câu 9.** CAS user có username alice nhưng local account alice bị khóa. Có thể cho login app vì CAS xác thực thành công?  
**Đáp án:** Không theo policy app; provider/user details cần thực thi account status và authorization local.

**Câu 10.** SP logout có luôn kết thúc CAS TGC và đăng xuất các ứng dụng khác không?  
**Đáp án:** Không; muốn logout tập trung cần CAS Single Logout/SLO được cấu hình riêng.

## 17. Tài liệu chính thức và nguồn học tiếp

1. [Spring Security 6.x – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): toàn bộ interaction sequence, ServiceProperties, CasAuthenticationEntryPoint, CasAuthenticationFilter và CasAuthenticationProvider.
2. [Spring Security 6.3.5 Javadoc – CasAuthenticationProvider](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): provider, serviceProperties, ticketValidator, userDetailsService và provider key.
3. [Spring Security 6.3.0-RC1 Javadoc – CasAuthenticationFilter](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): path mặc định /login/cas, service ticket handling và setServiceProperties.
4. [Spring Security 6.5 Javadoc – CAS web package](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/cas/web/package-summary.html): CAS entry point/filter và các gateway classes.
5. [Spring Security 6.5 Javadoc – ServiceProperties](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/ServiceProperties.html): service, sendRenew và các tham số liên quan.
6. [Apereo CAS – CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): /login?service=..., ticket one-time và /serviceValidate; tài liệu nhánh development cần đối chiếu CAS server version đang triển khai.
7. [Apereo CAS – CAS Protocol](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html): phân biệt CAS TGT/TGC/ST, CAS 2.0 và CAS 3.0.
8. [Apereo Java CAS Client](https://github.com/apereo/java-cas-client): thư viện TicketValidator, CAS protocol filter và dependency cas-client-core.
9. [Spring Security – Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): quan hệ ExceptionTranslationFilter, AuthenticationEntryPoint và AuthenticationManager.
10. [Spring Security – CAS module](https://docs.spring.io/spring-security/reference/modules.html): mô-đun spring-security-cas và dependencies.

**Tóm tắt:** **CasAuthenticationEntryPoint chỉ quyết định chuyển browser tới CAS login server**, sử dụng **loginUrl** và **ServiceProperties.service**. **CasAuthenticationFilter** nhận **ST** ở callback **/login/cas**, **CasAuthenticationProvider/TicketValidator** kiểm ST đúng service với CAS server rồi mới tạo local Authentication. Bảo vệ **HTTPS, CAS registered services, URL nhất quán, session, account mapping và authorization** là yêu cầu thiết yếu của một luồng đăng nhập CAS an toàn.
