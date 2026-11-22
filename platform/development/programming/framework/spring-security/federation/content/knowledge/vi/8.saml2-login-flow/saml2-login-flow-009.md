# Lưu SecurityContext và tạo phiên ứng dụng sau khi xác thực SAML2 thành công

**Module:** Spring Security – federation  
**Chủ đề cha:** Luồng đăng nhập SAML2  
**Nền tảng:** Spring Boot 3.x, Spring Security 6.x, Servlet/MVC, Java 17+.

## 1. Bức tranh tổng thể

Sau khi người dùng đăng nhập ở **Identity Provider (IdP)**, trình duyệt gửi **SAMLResponse** tới **Service Provider (SP)**. Spring Security phải xác minh SAMLResponse, thiết lập **Authentication** được tin cậy rồi giữ trạng thái xác thực để request tiếp theo không cần lặp lại toàn bộ quy trình SAML.

Có ba khái niệm liên quan nhưng hoàn toàn khác nhau:

- **SecurityContext:** đối tượng Spring Security chứa **Authentication**, bao gồm principal và authorities. Nó mô tả trạng thái bảo mật mà request hiện tại đang sử dụng.
- **SecurityContextHolder:** điểm truy cập SecurityContext ở thread đang xử lý request (mặc định dùng ThreadLocal). Nó **không phải cơ chế lưu phiên qua nhiều request**.
- **HttpSession + SecurityContextRepository:** nơi phía SP lưu SecurityContext qua các HTTP request. Browser mang cookie định danh phiên (**JSESSIONID** hoặc **SESSION** tùy cấu hình), còn dữ liệu xác thực thực tế được lưu phía ứng dụng.

Ngoài ra, IdP có một **phiên SSO riêng**. Phiên IdP và phiên ứng dụng SP không phải cùng một session; chúng có thể hết hạn hoặc bị logout vào những thời điểm khác nhau.

**Kết quả mong muốn:** Người dùng lần đầu gọi trang cần đăng nhập thì được đưa tới IdP; sau khi SAMLResponse hợp lệ, SP lưu Authentication vào SecurityContext; browser quay lại bằng cookie phiên SP và được nhận diện ở các request kế tiếp. Chỉ xác thực thành công **không tự cấp** mọi vai trò nghiệp vụ: SP còn phải phân quyền.

## 2. Các thành phần trong Spring Security

| Thành phần | Trách nhiệm |
| --- | --- |
| **Saml2WebSsoAuthenticationRequestFilter** | Tạo và gửi AuthnRequest để khởi động SAML2 browser SSO. |
| **Saml2AuthenticationRequestRepository** | Lưu AuthnRequest và thông tin correlation tới khi SAMLResponse trở lại; mặc định dùng HttpSession. |
| **Saml2WebSsoAuthenticationFilter** | Nhận SAMLResponse ở ACS endpoint và thực hiện authentication flow. |
| **AuthenticationManager / SAML provider** | Xác minh Response/Assertion bằng chính sách IdP đã đăng ký; tạo Authentication đã xác thực nếu thành công. |
| **Saml2Authentication** | Authentication đại diện cho đăng nhập SAML đã thành công; principal thường là Saml2AuthenticatedPrincipal. |
| **SecurityContext / SecurityContextHolder** | Context chứa Authentication và nơi request hiện tại đọc context. |
| **SecurityContextRepository** | Abstraction đọc/lưu context để request tiếp theo khôi phục được authentication. |
| **HttpSessionSecurityContextRepository** | Lưu context trong HttpSession của SP. |
| **RequestAttributeSecurityContextRepository** | Giữ context cho các dispatch trong cùng request, không thay thế persistence qua nhiều request. |
| **DelegatingSecurityContextRepository** | Kết hợp nhiều repository; cấu hình phổ biến có request attribute và HttpSession. |
| **SecurityContextHolderFilter** | Trong Spring Security 6, tải SecurityContext từ repository cho request, không tự lưu mọi thay đổi cuối request. |
| **SessionAuthenticationStrategy** | Áp dụng chính sách khi đăng nhập, như đổi session ID để chống session fixation. |
| **AuthenticationSuccessHandler** | Điều hướng hoặc trả response khi xác thực thành công; thường phục hồi URL người dùng đã yêu cầu. |
| **LogoutHandler** | Xóa trạng thái xác thực/phiên khi đăng xuất theo cấu hình. |

Spring Security SAML2 có sẵn các thành phần này. Ứng dụng bình thường **không cần tự giải mã SAMLResponse**, tạo một Authentication giả, hay gọi HttpSession.setAttribute bằng tên tự đặt để “ghi nhớ người dùng”.

## 3. Luồng từ HTTP request đến phiên đăng nhập

~~~text
Browser                      Spring Security SP                   SAML IdP
   |                                |                                 |
   | GET /profile                   |                                 |
   |------------------------------->| chưa có Authentication          |
   |<-------------------------------| redirect bắt đầu login          |
   | GET /saml2/authenticate/company|                                 |
   |------------------------------->| tạo AuthnRequest                |
   |                                | lưu request correlation         |
   |<-------------------------------| chuyển browser sang IdP ------->|
   |                                |                                 | login
   | POST /login/saml2/sso/company  |<-------------------------------|
   |------------------------------->| SAMLResponse + RelayState       |
   |                                | verify Response/Assertion       |
   |                                | Authentication thành công       |
   |                                | SessionAuthenticationStrategy   |
   |                                | SecurityContextHolder.set       |
   |                                | Repository.saveContext         |
   |<-------------------------------| redirect + session cookie      |
   |                                |                                 |
   | GET /profile + cookie          |                                 |
   |------------------------------->| Repository.loadContext         |
   |                                | Authorization kiểm tra quyền    |
   |<-------------------------------| 200 (nếu có quyền)             |
~~~

Sơ đồ là **trình tự khái niệm**, lược bớt một số filter. Đăng nhập có thể kết thúc bằng chuyển hướng về trang yêu cầu trước đó hoặc trang mặc định theo success handler.

### 3.1. Trước khi có SAMLResponse

Khi browser chưa authenticated truy cập trang bảo vệ, **SecurityFilterChain** xác định request. **ExceptionTranslationFilter** cùng **AuthenticationEntryPoint** khởi động SAML login. Endpoint phổ biến **/saml2/authenticate/{registrationId}** tạo AuthnRequest và chuyển browser tới IdP.

**HttpSession có thể đã tồn tại trước khi đăng nhập**, để chứa **AuthnRequest** được lưu bởi **HttpSessionSaml2AuthenticationRequestRepository**, CSRF token hoặc SavedRequest (URL muốn truy cập trước SSO). Có HttpSession **không đồng nghĩa** có Authentication của người dùng.

Bằng việc giữ AuthnRequest phía SP, hệ thống có thể đối chiếu **InResponseTo** và các thông tin liên quan khi IdP phản hồi. Không lấy RelayState hoặc request ID từ client rồi mặc định tin chúng mà thiếu ràng buộc phiên và chống replay.

### 3.2. IdP trả SAMLResponse

Trình duyệt POST tới **Assertion Consumer Service (ACS)**, thường là **/login/saml2/sso/{registrationId}**. **Saml2WebSsoAuthenticationFilter** lấy dữ liệu response, xác định registration, gọi AuthenticationManager. Provider SAML2/OpenSAML kiểm tra:

1. Chữ ký Response/Assertion bằng certificate của IdP đã được tin.
2. Issuer khớp IdP thuộc RelyingPartyRegistration đã đăng ký.
3. AudienceRestriction hướng tới đúng SP entityID.
4. Recipient/Destination hướng tới ACS hợp lệ.
5. Conditions, NotBefore, NotOnOrAfter và clock skew theo chính sách.
6. InResponseTo/request correlation với AuthnRequest trong SP-initiated flow, cùng bảo vệ replay.
7. Các yêu cầu về NameID, SubjectConfirmation và decryption nếu có.

**Chỉ khi vượt qua validation** mới được tạo Authentication đáng tin. Không dùng một XML parser hay việc decode Base64 làm chứng cứ đăng nhập.

### 3.3. Khi Authentication thành công

Trong luồng tiêu chuẩn:

- **SessionAuthenticationStrategy** xử lý sự kiện đăng nhập mới, bao gồm chống session fixation.
- Spring Security thiết lập một **SecurityContext** chứa Authentication, thông thường là **Saml2Authentication** với Saml2AuthenticatedPrincipal.
- Spring lưu context qua **SecurityContextRepository** thích hợp để request khác khôi phục được.
- **AuthenticationSuccessHandler** phản hồi; mặc định thường là chuyển người dùng về SavedRequest hoặc trang fallback.
- Browser giữ cookie session của SP, sau đó gửi lại trong các request đến SP.

**Lưu ý:** Nói “tạo phiên sau xác thực” có thể gây nhầm rằng HttpSession chỉ được khởi tạo lúc callback. Trên thực tế, session trước login có thể đã tồn tại; Spring thường **đổi session ID khi xác thực thành công**, và từ thời điểm đó phiên chứa SecurityContext của người dùng đã xác thực.

### 3.4. Request tiếp theo

Ở GET /profile sau login, Servlet container hoặc Spring Session tìm HttpSession bằng cookie. **SecurityContextHolderFilter** đọc context từ repository; **SecurityContextHolder** giúp AuthorizationFilter/controller truy cập Authentication trong request. Mã ứng dụng có thể inject **Authentication** hoặc **@AuthenticationPrincipal**.

Không cần gọi IdP hoặc đưa SAMLResponse vào mỗi HTTP request. Khi request hoàn tất, holder của thread được dọn, còn context lưu trong session/repository được giữ đến khi hết hạn hoặc logout.

## 4. Cách SecurityContext được lưu trong Spring Security 6

### 4.1. SecurityContextHolder chỉ chứa trạng thái request

Ví dụ đọc context bên trong một controller/service đã ở security filter chain:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    String name = authentication.getName();
}
~~~

Đây là **snippet**, không phải class Java độc lập. Cần import **org.springframework.security.core.Authentication** và **org.springframework.security.core.context.SecurityContextHolder**.

Request sau có thể chạy ở thread khác hoặc application instance khác. Vì vậy không lưu SecurityContext trong biến **static** hay tự ghép với thread ID. Repository mới là nguồn persistence.

### 4.2. Repository nào giữ context?

Cấu hình Spring Security 6 thường sử dụng **DelegatingSecurityContextRepository** gồm:

- **RequestAttributeSecurityContextRepository:** lưu theo request attribute để các dispatch trong cùng HTTP request nhìn thấy context.
- **HttpSessionSecurityContextRepository:** lưu context vào HttpSession, cho phép các request mới khôi phục Authentication.

Chuỗi thực tế:

~~~text
Authentication đã được xác minh
        |
SecurityContextHolder (request)
        |
SecurityContextRepository.saveContext(context, request, response)
        |
        +--> RequestAttributeSecurityContextRepository
        |
        +--> HttpSessionSecurityContextRepository
                         |
                         v
                      HttpSession
                         |
             cookie phiên mang session ID
                         |
                      Request sau
                         |
SecurityContextRepository.loadDeferredContext / loadContext
                         |
SecurityContextHolder + Authorization
~~~

Tên phương thức load phụ thuộc API/phiên bản triển khai; ý chính là **load từ repository ở request mới**. Cookie không chứa toàn bộ SecurityContext.

### 4.3. Spring 5 và Spring 6 khác nhau ở explicit save

Trong Spring Security 5 mặc định truyền thống, **SecurityContextPersistenceFilter** có thể tự lưu những thay đổi context trước khi request/response kết thúc.

Trong Spring Security 6, cấu hình mặc định sử dụng **SecurityContextHolderFilter** với cơ chế **requireExplicitSave**: filter tải context nhưng **không tự ghi mọi thay đổi vào repository**. Vì vậy, custom code muốn duy trì Authentication qua request phải gọi **SecurityContextRepository.saveContext(...)** một cách rõ ràng.

**Đây không phải lý do tự gọi saveContext sau mỗi SAML login.** Khi dùng **saml2Login()** và authentication filters chuẩn, Spring Security đã xử lý việc ghi context trong thành công flow. Chỉ cần manual save nếu chính ứng dụng **tự viết một flow thay thế/tùy chỉnh** thay đổi Authentication.

## 5. Ví dụ Spring Boot 3 và Java 17+: SAML2 login có phiên SP

Mẫu này là mã cho một dự án Spring Boot/Maven với Java 17+ và Spring Security 6.x. Bạn cần một **IdP thật**, metadata XML đáng tin và đăng ký SP entityID/ACS tại IdP trước khi thử đăng nhập. Tên miền example.org chỉ dùng minh họa.

### 5.1. Maven dependencies

Trong phần **dependencies** của pom.xml dùng Spring Boot parent/BOM tương thích:

~~~xml
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
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

Spring SAML2 service provider sử dụng OpenSAML; hãy theo dependency management của Spring Boot, tránh ép các bản OpenSAML xung đột.

### 5.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    metadata-location: classpath:metadata/company-idp.xml

server:
  servlet:
    session:
      timeout: 30m
~~~

Đặt metadata IdP thật, đã được phê duyệt, trong **src/main/resources/metadata/company-idp.xml**. **timeout: 30m** thường là **idle timeout** của HttpSession tại SP, không phải thời hạn SAML Assertion hay thời hạn session tại IdP. Nếu IdP yêu cầu AuthnRequest ký hoặc assertion mã hóa, bổ sung credentials của SP theo chính sách IdP.

### 5.3. Lớp main

**src/main/java/com/example/saml/SamlSessionApplication.java**

~~~java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSessionApplication.class, args);
    }
}
~~~

### 5.4. SecurityFilterChain, đăng ký IdP và session policy

**src/main/java/com/example/saml/SamlSecurityConfig.java**

~~~java
package com.example.saml;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties(
            @Value("${app.saml.metadata-location}") String metadataLocation) {

        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(metadataLocation)
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp/company")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(company);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId()))
            .logout(logout -> logout
                .logoutSuccessUrl("/"));

        return http.build();
    }
}
~~~

**Phân tích cấu hình:**

- **RelyingPartyRegistrations.fromMetadataLocation()** đọc metadata IdP để khởi tạo cấu hình SAML2 của nhà phát hành tin cậy. **RelyingPartyRegistrationRepository** cung cấp registration cho filter login.
- **/login/saml2/sso/company** là ACS của SP, phải trùng vị trí IdP gửi response; SP entityID và ACS cần đăng ký đúng bên IdP.
- **saml2Login()** tích hợp authentication filters, provider, context và success/failure processing.
- **SessionCreationPolicy.IF_REQUIRED** cho phép tạo/duy trì HttpSession khi SAML browser flow cần, thay vì dùng stateless.
- **sessionFixation().changeSessionId()** đổi session ID khi login để chống session fixation. Đây là chiến lược mặc định trên Servlet 3.1+; viết tường minh để dễ hiểu.
- **logoutSuccessUrl("/")** điều hướng sau local logout, không tự cấu hình SAML Single Logout với IdP.
- Không tự khai báo SecurityContextRepository: phần browser SSO được Spring Security cấu hình persistence theo cơ chế mặc định phù hợp.
- **Không tắt CSRF toàn ứng dụng.** SAML2 login tiêu chuẩn có xử lý riêng cho ACS; nếu tùy biến loginProcessingUrl hoặc chuỗi filter, cần bảo đảm matcher ACS và CSRF được cấu hình đúng.

**Chú ý:** Nếu chạy ở **http://localhost:8080**, callback ví dụ đang cấu hình **https://portal.example.org/** sẽ không đi về localhost. Dùng môi trường kiểm thử có URL/ACS đã đăng ký hoặc đổi chính xác SP entityID/ACS đồng thời ở SP và IdP, tuyệt đối không bỏ validation Recipient/Destination để lách lỗi URL.

### 5.5. Controller xem trạng thái phiên sau login

**src/main/java/com/example/saml/SessionController.java**

~~~java
package com.example.saml;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/")
    public String home() {
        return "SAML SP session ready";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(
            Authentication authentication,
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal,
            HttpServletRequest request) {

        HttpSession existing = request.getSession(false);

        return Map.of(
            "authenticated", String.valueOf(authentication.isAuthenticated()),
            "name", principal.getName(),
            "registrationId", principal.getRelyingPartyRegistrationId(),
            "sessionPresent", String.valueOf(existing != null)
        );
    }
}
~~~

**Tại sao getSession(false)?** Nó không tự tạo HttpSession. Nếu dùng request.getSession() mặc định trong một phép kiểm tra session, code có thể tạo phiên mới, khiến bạn kết luận sai rằng “session đã tồn tại và đăng nhập thành công”.

Trong ứng dụng chỉ dùng SAML2 login, principal ở /me sau xác thực thành công thường là **Saml2AuthenticatedPrincipal**. Nếu tích hợp thêm form login, OAuth2 hoặc Bearer, controller phải xử lý kiểu principal tương ứng, không ép mọi Authentication thành SAML.

**Không đưa session ID, raw SAMLResponse, cookie, NameID nhạy cảm hoặc SAML attributes dư thừa vào response/log trong production.** Response mẫu chỉ nhằm giúp học kiểm tra luồng.

### 5.6. Chạy và thử nghiệm

Trong project Maven Spring Boot hợp lệ:

~~~bash
mvn spring-boot:run
~~~

Sau khi khởi động thành công, request public:

~~~bash
curl -i http://localhost:8080/
~~~

Response body từ controller:

~~~text
SAML SP session ready
~~~

Để kiểm chứng SAML2 thật, dùng browser truy cập **URL SP đã đăng ký**, mở **/me**, hoàn thành login tại IdP và để IdP gửi SAMLResponse tới ACS. Quan sát:

1. Trước khi có Authentication, browser được hướng tới quy trình SAML login.
2. Sau login, /me trả **authenticated=true**, **sessionPresent=true**, cùng subject và registrationId thực tế.
3. Refresh /me nhiều lần khi phiên chưa hết hạn: không cần gửi lại SAMLResponse trên mỗi request.
4. Mở browser khác/xóa cookie SP: SP không có Authentication cũ; nếu IdP còn SSO session, lần đăng nhập lại có thể diễn ra nhanh.
5. Sau local logout hợp lệ, SP phải bỏ phiên; truy cập trang bảo vệ lại sẽ cần một vòng đăng nhập SAML mới ở SP.

JSON chính xác tùy IdP/user và chính sách của hệ thống. Nếu metadata IdP/ACS chưa đúng hoặc IdP chưa đăng ký SP, login không hoàn tất; không thể dựa vào ví dụ giả để kết luận session persistence đã chạy.

## 6. Manual saveContext: khi custom flow thay đổi Authentication

Đây là phần thường gây lỗi khi nâng Spring Security 5 lên 6. Một custom filter/controller có thể làm:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
~~~

Đoạn này **chỉ đặt context cho request hiện tại**. Trong mặc định Spring Security 6, nếu muốn context tiếp tục tồn tại, phải thêm:

~~~java
securityContextRepository.saveContext(context, request, response);
~~~

Mã trên là **snippet**, các biến phải được truyền từ một flow xác thực đã tin cậy. **verifiedAuthentication** phải là kết quả AuthenticationManager/validator đã xác minh SAML đầy đủ, không được tạo từ input browser rồi tự gán authenticated=true.

Ví dụ class hỗ trợ (dành riêng cho custom flow đã xác minh, **không cần dùng với saml2Login() chuẩn**):

~~~java
package com.example.saml;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.SecurityContextRepository;

public final class VerifiedSessionWriter {

    private final SecurityContextRepository repository;

    public VerifiedSessionWriter(SecurityContextRepository repository) {
        this.repository = repository;
    }

    public void persist(
            Authentication verified,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (verified == null || !verified.isAuthenticated()) {
            throw new IllegalArgumentException(
                "Authentication must already be verified");
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);
        repository.saveContext(context, request, response);
    }
}
~~~

Class này có thể biên dịch khi nằm trong dự án có Spring Security và Jakarta Servlet dependencies; nó **không phải** SAML response validator. Đối tượng repository phải chính là repository tương thích với filter chain khôi phục context trên request kế tiếp. Nếu dùng một repository để save và một repository khác để load, session sẽ “mất” dù không có lỗi biên dịch.

Lưu context **trước khi response commit**, vì Set-Cookie/redirect có thể không sửa được nếu response đã hoàn tất. Với custom flow, cũng cần tự áp dụng session-fixation policy, correlation, xử lý CSRF và failure; dùng **saml2Login()** chuẩn thường là lựa chọn an toàn hơn.

## 7. Phiên trước và sau login: session fixation

**Session fixation** là tình huống kẻ tấn công cố khiến nạn nhân đăng nhập trên một session ID mà kẻ tấn công đã biết trước đó.

Một chuỗi đúng:

~~~text
Anonymous browser -> HttpSession ID = S1
                |
          AuthnRequest lưu trong S1
                |
          SAMLResponse hợp lệ
                |
         SessionAuthenticationStrategy
                |
       HttpServletRequest.changeSessionId()
                |
          Authenticated session ID = S2
                |
       SecurityContext được persist
~~~

Trên Servlet 3.1+, **changeSessionId** là chiến lược mặc định khi có cơ chế session fixation protection phù hợp. Nó thay ID và giữ các session attributes cần thiết. Các lựa chọn khác là **newSession** hoặc **migrateSession**; không dùng **none** nếu không có cơ chế bảo vệ thay thế đã kiểm chứng.

**Cách kiểm tra:** nếu session đã có trước login, xem ID trước/sau ở DevTools trong môi trường kiểm thử; ID nên thay theo cấu hình. Không tiết lộ session ID trong log, issue tracker hoặc screenshot.

## 8. Cookie phiên và SAML HTTP-POST callback

Cookie phía SP phải được browser gửi trên request sau khi login. Những thiết lập cần xem xét:

- **Secure:** chỉ chuyển cookie qua HTTPS.
- **HttpOnly:** JavaScript trên trang không đọc được cookie.
- **Domain/Path:** đúng hostname/path của ứng dụng sau reverse proxy.
- **SameSite:** ảnh hưởng đặc biệt đến POST SAMLResponse từ IdP sang ACS.

Nhiều IdP dùng **cross-site HTTP POST** để browser gửi SAMLResponse. Nếu cookie session của SP mang **SameSite=Lax** hoặc **Strict**, browser có thể không gửi cookie trên POST xuyên site. SP mất HttpSession chứa AuthnRequest, dẫn đến lỗi request correlation hoặc login loop.

Nếu flow thực tế cần cookie ở cross-site POST, có thể phải cấu hình **SameSite=None; Secure** trên HTTPS. Ví dụ production:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: none
      timeout: 30m
~~~

**Không áp cấu hình này máy móc cho HTTP localhost**; Secure cookie yêu cầu HTTPS ở môi trường thực và có khác biệt giữa browser/localhost. Hãy kiểm tra request ACS thật trong DevTools, chính sách cookie của Servlet/Spring Session và reverse proxy.

**SameSite=None không phải miễn trừ CSRF:** các POST/PUT/DELETE nghiệp vụ dùng session cookie vẫn cần CSRF protection. Chỉ callback ACS đã được Spring SAML2 xử lý và kiểm tra theo profile SAML mới có ngoại lệ phù hợp. Không tắt CSRF toàn web để chữa một lỗi callback.

## 9. Timeout và phiên IdP khác phiên SP

| Thành phần | Ai quản lý? | Có tự hủy SecurityContext trong SP không? |
| --- | --- | --- |
| **SP HttpSession idle timeout** | SP / Servlet / Spring Session | Có, nếu session hết hiệu lực, Authentication cũ không khôi phục được |
| **Absolute timeout nội bộ** | Chính sách SP nếu tự áp dụng | Có thể chủ động bắt reauthentication, không tự có chỉ vì idle timeout |
| **IdP SSO session timeout** | IdP | Không tự động hủy HttpSession SP nếu không có cơ chế liên kết |
| **SAML Assertion Conditions.NotOnOrAfter** | IdP/Assertion validator | Điều kiện chấp nhận assertion khi login; không mặc định là hạn HttpSession |
| **AuthnStatement.SessionNotOnOrAfter** | IdP khi cung cấp | Có thể được dùng trong chính sách session SP nếu triển khai rõ ràng |
| **SAML Single Logout** | SP + IdP cùng tham gia | Có thể phối hợp chấm dứt session nếu hai bên cấu hình SLO đúng |

Một SAML assertion hợp lệ trong 5 phút có thể tạo phiên SP với idle timeout 30 phút. Đó không tự động là lỗi: **assertion lifetime** và **application session lifetime** phục vụ mục tiêu khác nhau. Với nghiệp vụ nhạy cảm, có thể yêu cầu absolute lifetime, step-up hoặc IdP reauthentication.

Nếu session SP hết hạn nhưng IdP còn phiên SSO, browser có thể trải qua một vòng SAML login mới gần như không cần nhập lại mật khẩu; SP vẫn phải kiểm chứng SAMLResponse mới.

## 10. Logout local và SAML Single Logout

Trong cấu hình thông thường, **POST /logout** với CSRF token hợp lệ kích hoạt các logout handlers của Spring Security, thường:

- invalidate HttpSession của SP;
- xóa Authentication trong SecurityContextHolder;
- xóa context khỏi repository theo cơ chế được cấu hình;
- điều hướng đến logout success URL.

**GET /logout** thường hiển thị trang xác nhận khi CSRF bật. Không gọi GET rồi kỳ vọng chắc chắn đã logout.

**Local logout không có nghĩa IdP đã logout.** Khi người dùng truy cập lại SP, IdP có thể còn SSO session và cấp SAMLResponse mới. Muốn logout liên kết, cấu hình **saml2Logout()** cùng SingleLogoutService, signing credentials, endpoint, chính sách xác minh request/response và hỗ trợ từ IdP. Spring Security có flow RP-initiated và AP-initiated SAML Single Logout; đây là chủ đề khác với chỉ xóa HttpSession cục bộ.

## 11. Chạy nhiều node: chia sẻ AuthnRequest và SecurityContext

Trong một ứng dụng chỉ có một node, HttpSession thường nằm trong bộ nhớ servlet container. Khi load balancer chuyển các request sang nhiều node:

- AuthnRequest lưu ở node A, nhưng SAMLResponse POST về node B: B không tìm thấy request gốc để đối chiếu InResponseTo.
- SAMLResponse được xác minh ở node A và SecurityContext lưu trong session A, nhưng /me vào node B: B không biết session đã xác thực.
- Sticky session có thể hỗ trợ nhưng không giải quyết triệt để vấn đề node bị thay thế hoặc failover.

Có thể dùng **Spring Session** với Redis/DB làm session store chung, để **HttpSession** được đọc từ các node. Với Spring Boot, dependency Redis theo BOM:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Ví dụ địa chỉ Redis đã được phê duyệt:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example.org
      port: 6379
server:
  servlet:
    session:
      timeout: 30m
~~~

Spring Session tích hợp qua Servlet Filter để thay HttpSession bằng implementation dùng store chung; cookie có thể mang tên **SESSION**. Spring Security vẫn dùng SecurityContextRepository để lưu context vào session logic đó.

Khi triển khai cần kiểm tra object/session serialization, cùng cấu hình registration/metadata ở các node, cookie domain/path, Redis TLS/ACL, expiration, monitoring và chính sách bảo vệ dữ liệu. **Không đưa session store public ra Internet.**

**Hai loại repository cần phân biệt:** **HttpSessionSaml2AuthenticationRequestRepository** lưu AuthnRequest trong phiên trước ACS; **HttpSessionSecurityContextRepository** lưu SecurityContext sau authentication. Hệ thống nhiều node cần cả hai trạng thái này khả dụng trên node xử lý.

## 12. Tùy chỉnh AuthenticationSuccessHandler không làm mất session

Một số ứng dụng muốn redirect về /dashboard hoặc ghi audit sau SAML2 login. Không cần tự ghi lại SecurityContext nếu chỉ thay điều hướng.

Ví dụ dùng SavedRequestAwareAuthenticationSuccessHandler để giữ URL gốc:

~~~java
.saml2Login(saml -> {
    SavedRequestAwareAuthenticationSuccessHandler delegate =
        new SavedRequestAwareAuthenticationSuccessHandler();
    delegate.setDefaultTargetUrl("/me");

    saml.successHandler((request, response, authentication) -> {
        // Chỉ ghi audit thông tin tối thiểu, không ghi SAMLResponse/cookie.
        delegate.onAuthenticationSuccess(request, response, authentication);
    });
})
~~~

Đây là **fragment trong SecurityFilterChain**, cần import **org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler**. Nó thay lời gọi **saml2Login(Customizer.withDefaults())** trong ví dụ, không đặt cả hai cạnh nhau. Nếu có SavedRequest, delegate thường ưu tiên URL đã yêu cầu; **/me** là fallback.

Success handler phải xử lý response đúng, không ghi raw SAMLResponse vào session. Trong flow tùy biến, response commit quá sớm trước khi context đã được lưu sẽ khiến cookie/redirect bị sai. Với flow Spring chuẩn, việc xác thực/lưu context do filter xử lý trước khi success handler hoàn tất.

## 13. Lỗi thường gặp và cách tìm đúng tầng

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| Login SAML thành công nhưng refresh trang lại bị login | Cookie không gửi, SecurityContextRepository chưa lưu/khôi phục, session expired | Set-Cookie, cookie ở request kế tiếp, repository và session timeout |
| ACS báo thiếu AuthnRequest gốc | Cookie SameSite bị chặn, chuyển node, session mất trước callback | Network POST ACS, HttpSessionSaml2AuthenticationRequestRepository, load balancer |
| Chỉ custom setContext nhưng không còn ở request sau | Spring 6 explicit save chưa được thực hiện | saveContext vào repository đúng; đừng dùng manual flow khi không cần |
| 401/redirect sau login dù Authentication valid ở callback | Không có persistence qua request hoặc chain sai | SecurityContextHolderFilter, repository, cookie, matcher |
| Session ID không thay sau đăng nhập khi đã có session trước đó | Chống session fixation bị vô hiệu, custom flow bỏ SessionAuthenticationStrategy | Cấu hình changeSessionId và filter authentication |
| Refresh sang node B mất phiên | HttpSession local tại node A | Spring Session hoặc routing/session sharing phù hợp |
| User authenticated nhưng /admin trả 403 | Thiếu authorities/roles | Role mapping và authorization policy, không sửa SAML validation |
| Logout rồi lại đăng nhập gần như tức thì | IdP SSO session vẫn còn | Phân biệt logout local và SAML SLO |
| Session cookie Secure không gửi khi test HTTP | Cấu hình cookie production trong dev không HTTPS | HTTPS test domain/cấu hình dev phù hợp |
| SAML POST từ IdP mất cookie | SameSite=Lax/Strict trên cross-site POST | Kiểm tra browser/ACS và SameSite=None; Secure khi cần |
| Lỗi deserialize session ở Redis sau deploy | Object/session serializer không tương thích | Kiểm tra codec, phiên bản, dữ liệu nhạy cảm |
| Các role đổi nhưng phiên vẫn cho quyền cũ | Authorities lưu trong SecurityContext chưa được làm mới | Re-evaluate quyền/thu hồi session khi policy thay đổi |

**Thứ tự debug hữu ích:** kiểm tra **SAMLResponse validation → success event → session fixation → saveContext → Set-Cookie → cookie request sau → load context → authorization**. Nếu user authenticated nhưng thiếu role, đó là lỗi phân quyền, không phải lỗi lưu phiên.

Chỉ bật DEBUG trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Không log SAMLResponse, cookie, session ID, private keys hoặc attributes nhận dạng nhạy cảm. Dùng correlation ID và thông báo đã làm sạch để quan sát flow.

## 14. Tình huống thực hành

### A. Có HttpSession trước login thì đã xác thực?

**Không.** HttpSession có thể chỉ giữ AuthnRequest hoặc SavedRequest. Chỉ Authentication đã được xác minh trong SecurityContext mới là cơ sở xác thực.

### B. Spring 6 custom controller đặt Authentication vào SecurityContextHolder rồi redirect, request sau lại anonymous?

**Vì holder không tự lưu qua request.** Custom flow phải dùng SecurityContextRepository.saveContext(context, request, response) vào repository đúng, kèm xác minh credential và session strategy. SAML2 login chuẩn thường đã giải quyết phần đó.

### C. IdP Assertion chỉ hợp lệ 5 phút nhưng /me vẫn authenticated 20 phút sau?

**Có thể đúng theo chính sách SP.** NotOnOrAfter giới hạn assertion tại thời điểm xác minh, không mặc định là HttpSession expiration. Thiết kế idle/absolute session timeout và reauthentication theo yêu cầu nghiệp vụ.

### D. IdP SSO session vẫn còn sau khi POST /logout tại SP?

**Bình thường khi chỉ local logout.** SP session đã xóa; IdP vẫn có thể tạo SAMLResponse mới. Cần SLO thực sự nếu muốn phối hợp logout liên kết.

### E. ACS vào node B nhưng AuthnRequest trên node A?

**Có thể fail correlation.** Chia sẻ HttpSession hoặc repository request correlation tin cậy giữa các node, đồng thời giữ ràng buộc chống replay và request/session.

### F. Chỉ cần SAML2 login, có nên dùng SessionCreationPolicy.STATELESS để giảm RAM?

**Không nên áp máy móc.** STATELESS thường vô hiệu việc dùng HttpSession cho SecurityContext; browser SAML2 thông thường cần session/cơ chế persistence và request correlation. Nếu muốn stateless phải thiết kế một kiến trúc khác với cùng mức bảo mật.

### G. Cookie SameSite=Lax khiến POST SAMLResponse không mang session ID?

**Kiểm tra cross-site POST trong DevTools.** Có thể phải dùng SameSite=None; Secure trên HTTPS hoặc request repository thay thế được thiết kế chặt chẽ, song vẫn phải bảo vệ CSRF ở endpoint nghiệp vụ.

### H. SAMLResponse xác minh thành công, /admin trả 403?

**Authentication persistence có thể vẫn đúng.** Cần role/permission mapping phù hợp. Authentication và authorization là hai bước riêng.

## 15. Checklist triển khai và QA

- [ ] SAMLResponse đi qua **Saml2WebSsoAuthenticationFilter** và provider tin cậy; signature, issuer, audience, recipient, time và correlation được kiểm tra.
- [ ] SecurityFilterChain bật **saml2Login()**, ACS URL khớp IdP và registrationId.
- [ ] SP duy trì SecurityContext bằng SecurityContextRepository/HttpSession qua các request.
- [ ] Hiểu **SecurityContextHolder** chỉ là request context; custom flow cần explicit **saveContext** trên Spring Security 6.
- [ ] Browser SAML2 chain dùng session policy phù hợp; không bật STATELESS không có thiết kế thay thế.
- [ ] Chống session fixation bằng **changeSessionId** hoặc chiến lược tương đương.
- [ ] Cookie dùng **Secure**, **HttpOnly**, Domain/Path đúng; kiểm thử **SameSite** với ACS POST.
- [ ] Chỉ exempt CSRF cho endpoint SAML cần thiết; vẫn bảo vệ thao tác thay đổi trạng thái của ứng dụng.
- [ ] Có idle timeout, cân nhắc absolute lifetime, quyền có thể bị thu hồi và thời điểm cần reauthentication.
- [ ] Phân biệt SAML Assertion lifetime, IdP SSO session, SP HttpSession, local logout và SAML SLO.
- [ ] Nhiều node chia sẻ đúng AuthnRequest và SecurityContext; kiểm tra serialization và bảo mật session store.
- [ ] Tránh ghi dữ liệu SAMLResponse, token/cookie/session ID và dữ liệu nhạy cảm vào log.
- [ ] Kiểm thử login, reload, mở browser mới, session expiration, logout, thiếu role, cookie bị chặn, callback tới node khác, failover.

**Ghi nhớ:** **SAMLResponse đã xác minh → Authentication → SecurityContext → SecurityContextRepository → HttpSession → cookie session → SecurityContext khôi phục ở request sau.** Đăng nhập SAML2 không tự làm mọi trang được phép truy cập; role và chính sách phân quyền vẫn phải được đánh giá tại SP.

## 16. Tài liệu tham khảo chính thức

- [Spring Security 6.5 – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): xử lý AuthnRequest/Response và Authentication.
- [Spring Security 6.5 – SAML2 Authentication Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html): HttpSessionSaml2AuthenticationRequestRepository và request correlation.
- [Spring Security 6.5 – Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SecurityContextRepository, requireExplicitSave, SessionCreationPolicy, session fixation và timeout.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): authentication filter, SecurityContextHolder, success handler.
- [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): local logout và SecurityContextLogoutHandler.
- [Spring Security 6.5 – SAML Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html): RP/AP-initiated SLO.
- [Spring Session – Spring Boot Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): lưu HttpSession chia sẻ.
