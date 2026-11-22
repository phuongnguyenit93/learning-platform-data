# Phạm vi SAML2 Service Provider của Spring Security và ranh giới triển khai Identity Provider

**Vấn đề trung tâm:** Khi tích hợp đăng nhập doanh nghiệp bằng SAML 2.0 vào ứng dụng Spring Boot, Spring Security giúp ứng dụng đóng vai trò **Service Provider (SP, còn gọi là Relying Party – RP)**: chuyển người dùng tới nhà cung cấp danh tính, tiếp nhận và kiểm tra kết quả SAML, sau đó tạo Authentication và phiên của ứng dụng. Spring Security **không biến ứng dụng thành một SAML 2.0 Identity Provider (IdP)** chỉ nhờ bật cấu hình SAML2 Login.

Bài học này nằm trong nền tảng Spring, tập trung vào **Spring Security Servlet/Spring Boot 3.x, Spring Security 6.x, Java 17+**. Phạm vi cần nắm vững là **phần Spring Security cung cấp sẵn**, **phần IdP chịu trách nhiệm**, và **điểm giao tiếp bắt buộc giữa hai bên**. Ví dụ dùng Spring Boot 3.3.5 để giữ cú pháp nhất quán; khi áp dụng bản mới hơn, cần đối chiếu tài liệu đúng phiên bản.

## 1. Phân vai: SP/RP, IdP/AP và trình duyệt

SAML 2.0 là bộ đặc tả liên kết danh tính trao đổi thông tin xác thực và thuộc tính người dùng bằng các thông điệp XML có ràng buộc bảo mật. Trong **SAML Web Browser SSO**, ba thành phần chính là:

- **Service Provider (SP) / Relying Party (RP):** ứng dụng cung cấp tài nguyên cho người dùng. SP không nhất thiết trực tiếp xác minh mật khẩu của người dùng; thay vào đó, nó **tin cậy có điều kiện** một IdP đã cấu hình, kiểm tra SAML Response/Assertion rồi quyết định có tạo phiên ứng dụng hay không.
- **Identity Provider (IdP) / Asserting Party (AP):** hệ thống xác thực người dùng theo chính sách danh tính của tổ chức, chẳng hạn mật khẩu, MFA, khóa tài khoản, thiết bị và quyền truy cập. Sau khi xác thực, nó phát hành SAML Assertion cho đúng SP với chữ ký, thời hạn và audience thích hợp.
- **Trình duyệt:** trung chuyển yêu cầu và phản hồi SAML qua HTTP Redirect/POST binding. Trình duyệt **không phải nguồn đáng tin** về danh tính: mọi SAML Response nhận từ browser phải được SP xác minh.

Một hệ thống có thể có **nhiều SP cùng sử dụng một IdP**. Đăng nhập một lần (SSO) có thể xảy ra vì IdP còn phiên xác thực. Điều đó **không** có nghĩa SP chia sẻ cookie phiên với IdP hoặc với nhau.

| Câu hỏi | SP – ứng dụng Spring Security | IdP – nhà cung cấp danh tính |
| --- | --- | --- |
| Ai đưa người dùng đến trang đăng nhập? | Khởi tạo yêu cầu đăng nhập và điều hướng browser đến SSO endpoint của IdP | Phục vụ giao diện đăng nhập khi cần |
| Ai xác minh mật khẩu, MFA, tài khoản? | Không làm trong luồng SAML SP thông thường | IdP và hệ thống xác thực tích hợp của nó |
| Ai tạo AuthnRequest? | SP khi dùng SP-initiated SSO | Nhận, kiểm tra và xử lý AuthnRequest |
| Ai tạo SAML Response/Assertion chứng minh xác thực? | **Nhận và kiểm tra** | **Phát hành và ký** cho SP được phép |
| Ai lưu khóa dùng để xác minh chữ ký IdP? | SP phải có trust configuration/certificate phù hợp | IdP quản lý khóa ký và công bố thông tin xác minh theo quy trình tin cậy |
| Ai tạo phiên cho ứng dụng A? | SP ứng dụng A | IdP chỉ quản lý phiên đăng nhập của IdP |
| Ai xuất bản metadata SP? | Spring Security có hỗ trợ metadata cho SP | IdP dùng metadata SP để đăng ký/kiểm tra trust |
| Ai xuất bản metadata IdP? | SP tiêu thụ metadata IdP | IdP công bố metadata Identity Provider |
| Ai cấp quyền trên các API, URL và nghiệp vụ riêng của A? | **Ứng dụng A**; có thể ánh xạ thuộc tính SAML thành quyền nội bộ | IdP cung cấp danh tính/thuộc tính theo chính sách, không thay thế authorization ở A |
| Ai thực hiện Single Logout xuyên hệ thống? | SP có thể tham gia luồng SAML SLO khi cấu hình đúng | IdP phải hỗ trợ và phối hợp SLO với các SP; không mặc nhiên đồng bộ mọi phiên |

**Cốt lõi:** Spring Security giúp ứng dụng **tiêu thụ và xác minh khẳng định danh tính**; để **phát hành** khẳng định danh tính cho ứng dụng khác thì cần một IdP thực thụ.

## 2. Spring Security SAML2 Service Provider hỗ trợ những gì?

Mô-đun **spring-security-saml2-service-provider** là tích hợp SAML2 **Relying Party** cho ứng dụng Servlet. Khi có một **RelyingPartyRegistration** hợp lệ và bật **saml2Login()**, framework cung cấp hạ tầng để:

1. **Điều hướng đăng nhập (SP-initiated):** khi người dùng truy cập tài nguyên bảo vệ mà chưa xác thực, Spring Security có thể tạo AuthnRequest cho IdP và chuyển hướng trình duyệt tới IdP.
2. **Nhận SAMLResponse ở Assertion Consumer Service (ACS):** cung cấp filter endpoint cho HTTP POST mang tham số SAMLResponse; không cần tự viết controller để giải mã XML.
3. **Xác minh phản hồi/Assertion:** dùng OpenSAML và các bộ xác minh được cấu hình để kiểm tra chữ ký, issuer/registration, điều kiện thời gian, recipient/destination, audience, correlation và các ràng buộc cần thiết.
4. **Tạo Authentication cho ứng dụng:** từ kết quả hợp lệ, Spring Security tạo Saml2Authentication và principal; SecurityContext của phiên ứng dụng có thể được duy trì bằng cơ chế Spring Security Servlet.
5. **Đọc SAML attributes:** ứng dụng có thể lấy NameID và các thuộc tính đã được IdP phát hành, sau đó tự quyết định liên kết tài khoản và ánh xạ quyền.
6. **Quản lý cấu hình nhiều đối tác:** đăng ký một hoặc nhiều IdP qua **RelyingPartyRegistrationRepository**; mỗi registration mô tả sự tin cậy giữa một SP và một asserting party.
7. **Phát metadata SP:** khi bật **saml2Metadata()**, Spring Security có thể công bố entityId, ACS và các thông tin SP liên quan để IdP cấu hình.
8. **Tham gia SAML Single Logout (SLO) khi tích hợp:** Spring Security có hỗ trợ RP-initiated và AP-initiated SLO ở phía SP, nhưng cần IdP hỗ trợ, endpoint, chữ ký/chứng chỉ và cấu hình nhất quán. Đây là phần **tùy chọn và có điều kiện**, không phải kết quả tự động của saml2Login().

### Giới hạn thực tế của phạm vi trên

- Framework **không tự cấp tài khoản** tại IdP, không quản lý mật khẩu/MFA cho IdP, và không sở hữu phiên SSO toàn tổ chức.
- Framework **không phát hành SAML Assertion thay một IdP** trong mô hình SP mặc định, không cung cấp đầy đủ IdP SSO endpoint, IdP metadata, hay quản trị federation partner theo vai trò IdP.
- Không nên suy ra rằng **mọi SAML profile/binding** đều được hỗ trợ hoàn chỉnh bằng cấu hình mặc định. Trọng tâm là **Web Browser SSO** phổ biến; trường hợp **SAML Artifact, SOAP, ECP, AttributeQuery, yêu cầu đặc thù của IdP** có thể cần thiết kế/extension riêng, hoặc dùng sản phẩm IdP/SP chuyên biệt.
- Việc ánh xạ claims thành business roles, quản lý tài khoản cục bộ, provisioning/deprovisioning, quyết định authorization và bảo vệ API nội bộ **vẫn thuộc ứng dụng**.
- OpenSAML là thư viện xử lý thông điệp/giao thức; có OpenSAML trong dependency **không đồng nghĩa** bạn đã có một SAML Identity Provider.

## 3. Luồng SAML Web Browser SSO: SP làm gì, IdP làm gì?

### Luồng SP-initiated login thường gặp

~~~text
[Browser]                     [Spring SP]                        [SAML IdP]
    |-- GET /private ---------->|                                   |
    |<-- Redirect AuthnRequest -|                                   |
    |-------------------- SAMLRequest/RelayState ------------------>|
    |<------------------- trang login/MFA nếu cần ------------------|
    |-------------------- nhập thông tin xác thực ----------------->|
    |<--------------- HTML form có SAMLResponse -------------------|
    |-- POST SAMLResponse ------>|                                   |
    |                            |-- validate Response/Assertion     |
    |                            |-- create Authentication/session   |
    |<--------- trang /private --|                                   |
~~~

1. **SP:** request chưa có Authentication nên bắt đầu đăng nhập SAML; tạo **AuthnRequest** và chuyển trình duyệt tới IdP theo HTTP binding đã cấu hình.
2. **IdP:** kiểm tra SP được tin cậy, xác thực người dùng theo chính sách nội bộ; nếu IdP đã có phiên SSO phù hợp thì có thể không yêu cầu nhập mật khẩu lại.
3. **IdP:** tạo **Response** chứa **Assertion** nhắm tới SP. Tùy cấu hình đối tác, chữ ký có thể ở Response, Assertion hoặc cả hai; sự hiện diện và vị trí của chữ ký phải được SP xác minh theo chính sách.
4. **Browser:** POST dữ liệu SAMLResponse đến **ACS của SP** (ví dụ /login/saml2/sso/corp).
5. **SP:** xác minh tài liệu SAML, ràng buộc giao thức, trust và điều kiện bảo mật; nếu hợp lệ thì tạo **Saml2Authentication**, đưa vào SecurityContext và tiếp tục request.
6. **Ứng dụng:** sau login vẫn phải kiểm tra quyền theo URL, role và quy tắc nghiệp vụ. Đăng nhập thành công không đồng nghĩa truy cập mọi tài nguyên.

**SAMLRequest** và **SAMLResponse** đi qua trình duyệt, nhưng điểm xác thực mật khẩu là **IdP**; nơi tin tưởng kết quả và cấp quyền ứng dụng là **SP**. Điều này là ranh giới chức năng quan trọng nhất.

### IdP-initiated SSO khác ở đâu?

Với **IdP-initiated flow**, người dùng chọn ứng dụng từ portal IdP; IdP có thể gửi một SAMLResponse không bắt nguồn từ AuthnRequest cụ thể của SP. Spring Security có thể xử lý một số tình huống dựa trên registration/issuer, nhưng việc không có AuthnRequest tương quan tạo rủi ro khác SP-initiated: cần xác minh **destination, recipient, audience, chữ ký, thời gian, đối tác được phép, trạng thái phiên và replay** theo thiết kế. Không mặc định bật/cho phép IdP-initiated chỉ vì IdP có nút “Launch App”.

**RelayState** có thể hỗ trợ duy trì ngữ cảnh điều hướng, nhưng không được coi là URL đã tin cậy; phải phòng open redirect và kiểm soát giá trị được phép.

## 4. Những thành phần SAML và endpoint SP phải hiểu

| Thuật ngữ | Ý nghĩa thực tế |
| --- | --- |
| **SP entityId** | Định danh logic duy nhất của SP trong quan hệ trust; thường nhìn như URL, nhưng không nhất thiết là URL fetch được. IdP cần đăng ký khớp. |
| **IdP entityId (issuer)** | Định danh asserting party mà SP kỳ vọng; phải so khớp với giá trị trong thông điệp SAML. |
| **AuthnRequest** | Yêu cầu SP gửi IdP để xác thực user; thường có ID, issuer và thông tin ACS/binding. |
| **SAML Response** | Thông điệp IdP trả về SP; có thể mang một hoặc nhiều Assertion theo profile/giao thức. |
| **Assertion** | Khẳng định xác thực/thuộc tính, chứa Subject/NameID, điều kiện, audience, thời hạn và có thể AuthnStatement. |
| **NameID** | Định danh subject do IdP phát hành; có định dạng transient/persistent/email... Không mặc định coi NameID là khóa người dùng vĩnh viễn. |
| **Attributes** | Thuộc tính như email, department, group; tên/định dạng/độ tin cậy phụ thuộc IdP và thỏa thuận đối tác. |
| **ACS (Assertion Consumer Service)** | Endpoint **của SP** nhận SAMLResponse và thực hiện xác minh; không phải IdP SSO endpoint. |
| **SingleSignOnService** | Endpoint **của IdP** nhận AuthnRequest từ SP. |
| **SP metadata** | XML mô tả SP, thường có SPSSODescriptor, entityID, ACS, chứng chỉ và binding. |
| **IdP metadata** | XML mô tả IdP, thường có IDPSSODescriptor, entityID, SSO/SLO endpoints và chứng chỉ xác minh. |
| **SLO (Single Logout)** | Giao thức phối hợp logout; không tự động xảy ra chỉ nhờ việc SSO login hoạt động. |

### Các URL thường gặp của Spring Security Servlet

| URL | Vai trò | Chú ý |
| --- | --- | --- |
| **/saml2/authenticate/{registrationId}** | SP tạo AuthnRequest và bắt đầu SAML login tới đối tác tương ứng. | Ví dụ **/saml2/authenticate/corp**; đây là SP endpoint để bắt đầu login. |
| **/login/saml2/sso/{registrationId}** | ACS của SP nhận SAMLResponse (thường HTTP POST). | Ví dụ **/login/saml2/sso/corp**; phải được IdP đăng ký chính xác. |
| **/saml2/metadata/{registrationId}** | Xuất metadata của **SP** khi cấu hình **saml2Metadata()**. | Ví dụ **/saml2/metadata/corp**; chỉ dùng để trao đổi trust của SP. |
| **/saml2/metadata** | Metadata cho các registration phù hợp, tùy repository hỗ trợ. | Cần kiểm tra output thực tế trong môi trường. |
| **/saml2/service-provider-metadata/{registrationId}** | Đường metadata SP tương thích được Spring hỗ trợ. | Không phải metadata của IdP. |
| **/logout/saml2/slo** | SAML logout message endpoint của SP khi có cấu hình SLO. | Phân biệt với **POST /logout** local; cách trigger/tiếp nhận phụ thuộc cấu hình. |

Trong Spring Security 6, **entityId mặc định** của RP thường được xây từ mẫu **{baseUrl}/saml2/service-provider-metadata/{registrationId}**; **ACS mặc định** thường là **{baseUrl}/login/saml2/sso/{registrationId}**. Tham số **{baseUrl}** phản ánh URL ứng dụng mà client nhìn thấy (scheme, host, port). Nếu chạy sau reverse proxy, cần đảm bảo URL công khai đúng; không đăng ký nhầm localhost hoặc HTTP nội bộ làm ACS production.

Các endpoint trên là của **ứng dụng SP**. Chúng **không** biến ứng dụng thành IdP có trang đăng nhập danh tính, IdP metadata hoặc dịch vụ cấp Assertion cho bên thứ ba.

## 5. Kiến trúc Spring Security phía Service Provider

Trong ứng dụng Servlet, SecurityFilterChain tích hợp các thành phần theo luồng:

- **Saml2WebSsoAuthenticationRequestFilter** khởi tạo và mã hóa AuthnRequest trước khi redirect đến IdP.
- **Saml2WebSsoAuthenticationFilter** nhận SAMLResponse tại ACS, tạo yêu cầu xác thực tới AuthenticationManager.
- **OpenSAML authentication provider** xác minh thông điệp/assertion theo phiên bản Spring Security/OpenSAML trong dự án; tên implementation cụ thể có thể thay đổi giữa các phiên bản, nên không buộc code ứng dụng trực tiếp vào implementation nếu không cần tùy biến.
- **Saml2Authentication** cung cấp Authentication đã xác thực; **Saml2AuthenticatedPrincipal** cung cấp tên và thuộc tính người dùng trong Spring Security 6.x.
- **RelyingPartyRegistration** chứa cả thông tin SP (entityId, ACS, signing/decryption credential) và thông tin IdP (issuer, SSO/SLO endpoints, verification certificate, policy gửi AuthnRequest). **RelyingPartyRegistrationRepository** tìm registration theo ID.
- **SecurityContext** đại diện trạng thái đăng nhập trong ứng dụng. Với web session thông thường, ứng dụng lưu/khôi phục Authentication qua cơ chế phiên Servlet. Phiên IdP độc lập ở phía IdP.

Điểm quan trọng: **RelyingPartyRegistrationRepository không phải kho người dùng IdP**. Nó lưu **định nghĩa đối tác và trust**, không xác thực username/password, không lưu tài khoản/MFA, không phát hành SAML Assertion.

## 6. Ví dụ Spring Boot 3.3.5, Java 17: triển khai một SP

Ví dụ dưới đây tạo **ứng dụng SP thực sự** có thể khởi chạy với Java 17/Maven sau khi được kết nối tới **IdP thật**. Nó **không bao gồm IdP**. Cần được IdP cung cấp metadata endpoint qua HTTPS (hoặc file metadata đáng tin cậy), và phải đăng ký SP/ACS/entityId ở IdP trước khi login hoạt động.

### 6.1. Dependency và Maven repository

OpenSAML có các artifact cần tải từ kho Shibboleth; thêm repository khi dự án dùng **spring-security-saml2-service-provider**. Dùng Spring Boot BOM/parent để quản lý phiên bản các Spring dependencies.

**pom.xml**

~~~xml
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
    <artifactId>saml-sp-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>

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

### 6.2. Khai báo registration tới IdP

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}

server:
  port: 8080
~~~

**corp** là **registrationId nội bộ của SP**, không phải tên tài khoản. Giá trị **SAML_IDP_METADATA_URI** phải trỏ tới metadata SAML IdP thật, chẳng hạn **https://idp.example.org/saml/metadata** (địa chỉ ở đây chỉ minh họa). Spring Boot sẽ tạo **RelyingPartyRegistrationRepository** từ cấu hình; metadata cung cấp issuer, IdP SSO URL và các chứng chỉ kiểm tra chữ ký. Không tự tin tưởng một metadata URL lạ hoặc không được quản trị.

Thứ tự triển khai có thể cần phối hợp với IdP admin: chuẩn bị entityId/ACS công khai của SP, đăng ký ở IdP, cập nhật metadata IdP và khởi động SP. Nếu IdP yêu cầu **signed AuthnRequest**, **assertion encryption** hoặc thuật toán/binding cụ thể, cần bổ sung credential và registration tương ứng; bản ví dụ tối giản chưa chủ động tạo khóa ký/decrypt của SP.

### 6.3. Application, filter chain và controller

**src/main/java/com/example/samlsp/SamlSpDemoApplication.java**

~~~java
package com.example.samlsp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSpDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samlsp/SecurityConfig.java**

~~~java
package com.example.samlsp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**src/main/java/com/example/samlsp/DemoController.java**

~~~java
package com.example.samlsp;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SAML SP public";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID: " + principal.getName();
    }
}
~~~

**Ý nghĩa:** URI **/** không yêu cầu đăng nhập, **/me** yêu cầu xác thực SAML; **saml2Login()** bật phía SP nhận Assertion và đăng nhập, còn **saml2Metadata()** công bố metadata SP. Chưa hề viết mã nhận mật khẩu hay ký Assertion cho các bên khác – vì hai tác vụ đó thuộc IdP.

### 6.4. Chạy thử và kết quả có thể dự đoán

Thiết lập biến môi trường **SAML_IDP_METADATA_URI** thành URL metadata IdP hợp lệ, có thể truy cập từ server; sau đó trong thư mục chứa **pom.xml** chạy:

~~~bash
mvn spring-boot:run
~~~

- **GET http://localhost:8080/** trả đúng nội dung văn bản: **SAML SP public**.
- **GET http://localhost:8080/saml2/metadata/corp** trả **SP metadata XML** khi registration đã sẵn sàng và endpoint được cho phép; đây là metadata của SP, không phải của IdP. Trong một số cấu hình, có thể cần cho phép public GET metadata qua authorization rules hoặc cấu hình truy cập riêng.
- **GET http://localhost:8080/saml2/authenticate/corp** bắt đầu luồng SP-initiated SSO hướng tới IdP. Nó không tự hiển thị màn hình đăng nhập IdP trong ứng dụng Spring.
- **GET http://localhost:8080/me** khi chưa có phiên kích hoạt yêu cầu đăng nhập; khi IdP trả Assertion hợp lệ, endpoint trả chuỗi dạng **NameID: <giá trị do IdP phát hành>**. Không thể tuyên bố một giá trị NameID cố định vì phụ thuộc tài khoản, NameID format và chính sách IdP.

Để demo hoàn tất login, **entityId SP và ACS phải được IdP đăng ký**, trust certificate hợp lệ và địa chỉ callback chính xác. Nếu cấu hình metadata IdP chỉ là URL giả, khởi động/đăng nhập sẽ thất bại; đó là hệ quả đúng vì ứng dụng này **chỉ là SP**.

**Production:** cấu hình URL HTTPS công khai ở proxy/server, đồng bộ metadata/tên miền và đăng ký ACS chính xác. Không sử dụng endpoint HTTP localhost như cấu hình production; không viết secret/private key vào file commit.

## 7. Metadata, chứng chỉ và việc thiết lập tin cậy

SAML federation không đơn giản là nhập “URL login” của IdP. Hai bên cần **hợp đồng tin cậy** gồm các dữ kiện khớp nhau.

### SP cung cấp cho IdP

- **SP entityId** – định danh logic của ứng dụng, chính xác tới ký tự, thường ổn định qua nâng cấp.
- **ACS URL và binding** – nơi IdP gửi Response, ví dụ HTTPS POST tới /login/saml2/sso/corp.
- **Chứng chỉ SP** – nếu IdP yêu cầu SP ký AuthnRequest hoặc mã hóa Assertion cho SP; khóa riêng nằm ở SP và phải được bảo vệ.
- **Thông tin SLO** – nếu hai bên tích hợp logout federation.
- **Metadata SP** – tài liệu XML có SPSSODescriptor; được xuất qua **saml2Metadata()** và dùng cho onboarding.

### IdP cung cấp cho SP

- **IdP entityId** và **SSO endpoint/binding** chính xác.
- **X.509 public certificate** (hoặc metadata đáng tin cậy chứa certificate) để SP xác minh chữ ký SAML.
- **Quy tắc ký:** IdP ký Response, Assertion hay cả hai; thuật toán và trust policy thống nhất.
- **Quy tắc Subject/NameID/Attribute**: định danh nào ổn định, email có được dùng làm khóa liên kết tài khoản hay không, tên thuộc tính vai trò/group.
- **Logout endpoint/certificate**, nếu IdP hỗ trợ SLO.
- **Chính sách MFA, session và certificate rollover**, được quản lý ở IdP.

**Không được đảo chiều:** certificate do IdP công bố để **SP xác minh** không biến SP thành IdP; certificate dùng để **SP ký AuthnRequest** không làm SP có quyền ký Assertion như IdP. Hai cặp khóa phục vụ hai vai trò khác nhau.

**Metadata là tài liệu cấu hình tin cậy, không phải cứ có URL là an toàn.** Với metadata động, phải tin tưởng nguồn và transport, có quy trình xác minh chữ ký metadata nếu yêu cầu, giới hạn quyền cập nhật và hỗ trợ rotation. Nếu chứng chỉ IdP đổi nhưng SP vẫn dùng trust cũ, login có thể thất bại; không “sửa” bằng cách tắt signature validation.

## 8. Các điều kiện bảo mật cần được SP kiểm tra

SAMLResponse đi qua trình duyệt nên có thể bị sửa, phát lại, thay thế hoặc gửi vào sai endpoint. Phần xử lý SAML của Spring Security/OpenSAML hỗ trợ validation theo cấu hình; đội triển khai vẫn phải hiểu và kiểm thử điều kiện bảo mật quan trọng:

1. **Chữ ký và trust:** chỉ chấp nhận chữ ký theo thuật toán/policy đã cho phép, dùng đúng certificate tin cậy của IdP đã đăng ký. Không tự bỏ qua chữ ký hay chỉ parse Base64/XML rồi lấy email.
2. **Issuer/registration:** Identity Provider phát hành phải thuộc đối tác dự kiến, không chấp nhận issuer tùy ý. Nếu hỗ trợ nhiều IdP, phải xác định đúng registration từ request/correlation/issuer theo logic an toàn.
3. **AudienceRestriction:** Assertion phải nhắm tới entityId của **SP hiện tại**. Assertion cấp cho SP B không được dùng đăng nhập SP A.
4. **Destination và Recipient:** thông điệp/SubjectConfirmationData phải nhắm đúng ACS hợp lệ của SP, nhất là sau reverse proxy.
5. **InResponseTo và yêu cầu ban đầu:** với SP-initiated login, Response cần tương ứng AuthnRequest đã phát hành khi profile/policy yêu cầu. Cần lưu và bảo vệ trạng thái yêu cầu để không nhận phản hồi ngoại lai.
6. **Điều kiện thời gian:** kiểm tra NotBefore/NotOnOrAfter, SubjectConfirmationData, response/statement time theo đặc tả. Đồng bộ đồng hồ qua NTP; chỉ dùng clock skew nhỏ, có lý do.
7. **Replay protection:** không chấp nhận lặp lại cùng Assertion/Response khi profile yêu cầu chống phát lại. Trong hệ thống đa instance, lưu trạng thái chống replay/correlation phải phù hợp kiến trúc.
8. **XML wrapping/XXE/processing:** dùng bộ xử lý SAML được duy trì và cấu hình bảo mật; không tự viết parser/validator thô trên DOM để “đơn giản hóa”.
9. **Phiên và CSRF:** sau khi xác thực hợp lệ, session cookie cần Secure/HttpOnly/SameSite phù hợp và bảo vệ fixation. Bảo vệ CSRF cho các thao tác nghiệp vụ; không tắt bảo vệ toàn hệ thống chỉ để nhận SAML POST.
10. **Privacy:** SAML Assertion/attributes có thể chứa thông tin cá nhân. Không log SAMLResponse, khóa riêng, cookie hoặc toàn bộ XML chưa được làm sạch trong production.

Với IdP-initiated flow không có InResponseTo để liên kết với request khởi tạo, **đừng tự bỏ qua các điều kiện kiểm tra còn lại**. Cần một quyết định kiến trúc và kiểm thử bảo mật riêng nếu tổ chức yêu cầu mô hình này.

## 9. Identity Provider thực thụ phải triển khai những chức năng gì?

Nếu đề bài sản phẩm là **“Xây hệ thống Spring phát hành SAML đăng nhập cho nhiều ứng dụng doanh nghiệp”**, đó là thiết kế **Identity Provider**, khác căn bản với cấu hình Service Provider bên trên.

Một IdP thường cần:

1. **Định danh/tài khoản:** kho người dùng hoặc kết nối LDAP/AD, quy tắc định danh, xác thực, khóa tài khoản, quản lý credentials, thay đổi mật khẩu, recovery và lifecycle tài khoản.
2. **Chính sách xác thực:** MFA, risk-based authentication, phát hiện bất thường, phiên SSO của IdP, idle/absolute timeout, chính sách phiên đa thiết bị, reauthentication.
3. **SAML protocol server:** nhận và xác minh AuthnRequest từ SP, biết SP nào được tin tưởng, hỗ trợ binding được công bố, phát hành đúng SAML Response/Assertion theo đối tác.
4. **Ký và khóa:** quản lý private key IdP, chứng chỉ công khai, key rollover, thuật toán ký, bảo vệ HSM/KMS nếu cần, kiểm soát provenance/trust metadata.
5. **Đảm bảo điều kiện Assertion:** issuer, Subject/NameID, AudienceRestriction, Destination/Recipient, thời hạn, AuthnStatement, SessionIndex, response-to-request correlation và chống replay.
6. **SAML IdP metadata:** phát IDPSSODescriptor, SingleSignOnService, SingleLogoutService (nếu hỗ trợ), KeyDescriptor với signing certificate; cập nhật metadata cho SP theo quy trình đã thỏa thuận.
7. **Quản lý liên kết nhiều SP:** onboarding, phê duyệt ACS/EntityID, attribute release policy, mapping NameID, tenancy, consent/quyền riêng tư và audit.
8. **SLO/truy vết phiên:** quản lý SessionIndex, yêu cầu/đáp ứng logout, xử lý failure/partial logout và thông báo đến các SP khác theo hợp đồng hỗ trợ.
9. **Vận hành, giám sát, compliance:** HA, logging an toàn, key rotation, giám sát certificate expiry, audit authentication, response signing và kiểm thử tương thích các SP.

**Không có cấu hình saml2Login() nào tự tạo ra bộ tính năng này.** Spring MVC, Spring Security, OpenSAML hay Spring Boot có thể là thành phần kỹ thuật dùng để **xây riêng một IdP**, nhưng lúc đó cần tự thiết kế và kiểm thử giao thức, khóa, bảo mật, nghiệp vụ và vận hành; đó là một dự án phát triển Identity Provider thực thụ, không còn là tác vụ bật SAML2 Service Provider.

### Lựa chọn kiến trúc khi tổ chức cần IdP

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Spring app cần cho nhân viên đăng nhập bằng tài khoản doanh nghiệp | Dùng **Spring Security SAML2 SP** để liên kết tới IdP đã có. |
| Một tổ chức cần cổng SSO cho nhiều ứng dụng SAML | Dùng **IdP sản phẩm chuyên dụng** (ví dụ Keycloak với SAML, Shibboleth IdP hoặc Microsoft Entra ID theo khả năng triển khai), quản lý SP, xác thực và metadata từ hệ thống đó. |
| Cần liên kết nhiều nguồn danh tính, chuyển đổi giữa SAML và OIDC | Cân nhắc **identity broker/gateway** hỗ trợ cả hai giao thức; ứng dụng Spring có thể là SP SAML hoặc OIDC client phía ngoài. |
| Muốn tự phát hành Assertion từ dịch vụ Spring | Phải xác định đây là **xây IdP riêng** với phạm vi, threat model, giao thức, key lifecycle, HA và kiểm thử bảo mật đầy đủ; không dùng cấu hình SP làm IdP giả. |
| Đã có Spring Authorization Server và muốn thêm SAML IdP | Spring Authorization Server chủ yếu hỗ trợ **OAuth2/OIDC Authorization Server**; **không tự động trở thành SAML2 IdP** nhờ bật SAML login hay OAuth2/OIDC server. Cần thành phần thực sự hỗ trợ vai trò SAML IdP. |

**Phân biệt đăng nhập và cung cấp danh tính:** một ứng dụng Spring có thể đồng thời **đăng nhập vào IdP bên ngoài** và **phát token OAuth2/OIDC** nếu xây thêm authorization server. Điều đó vẫn không mặc nhiên biến nó thành IdP phát hành SAML Assertion theo SAML 2.0.

## 10. Session và Single Logout: ranh giới trách nhiệm

Sau login thành công có thể tồn tại ít nhất hai phiên:

- **Phiên IdP:** dùng để IdP nhận ra người dùng ở lần truy cập SSO tiếp theo, có timeout, MFA và logout policy riêng.
- **Phiên local của SP:** Spring ứng dụng quản lý SecurityContext/session cookie, timeout và phân quyền riêng.

Khi **SP session hết hạn** mà IdP session còn sống, SP có thể bắt đầu SAML flow mới; IdP có thể xác thực không cần hỏi mật khẩu. Khi **IdP session hết hạn** mà SP session còn sống, ứng dụng có thể vẫn phục vụ request tới lúc local session hết hạn hoặc nhận sự kiện logout/thu hồi từ cơ chế khác.

**Local logout** (thường qua POST /logout với CSRF hợp lệ) chỉ xóa phiên cục bộ theo cấu hình. Để logout liên kết, Spring Security có **saml2Logout()** ở phía SP, nhưng yêu cầu IdP hỗ trợ **SingleLogoutService**, cấu hình ký/xác minh logout message, endpoint và sự tương quan session/NameID. Trong bối cảnh phù hợp, RP-initiated logout có thể gửi LogoutRequest; AP-initiated logout có thể gửi LogoutRequest đến SP để SP phản hồi sau khi hủy local session.

Ví dụ cấu hình minh họa **bổ sung vào SecurityConfig hiện có** khi IdP thực sự đã hỗ trợ SLO:

~~~java
// Minh họa bổ sung trong chuỗi cấu hình HttpSecurity hiện có.
// Cần thêm SLO endpoint và signing credentials vào registration.
http.saml2Logout(Customizer.withDefaults());
~~~

Đoạn này **không phải chương trình chạy độc lập**, không tự kích hoạt logout toàn hệ thống chỉ nhờ thêm một dòng. Cần cấu hình signing certificate/private key, SLO location, IdP trust, và kiểm thử RP-/AP-initiated SLO. Không đảm bảo logout tức thời ở mọi thiết bị và mọi SP nếu đối tác không hỗ trợ.

## 11. Kịch bản thực hành và checklist nghiệm thu

Một bài kiểm chứng đúng phạm vi SP nên có **IdP thử nghiệm thật** hoặc môi trường sandbox, một SP Spring và metadata/keys đã được cấp bởi IdP. Không tạo SAMLResponse thủ công chỉ để “đánh lừa” validation.

**Luồng kiểm chứng chức năng:**

1. **SP metadata:** gọi /saml2/metadata/corp và xác minh entityId, ACS HTTPS, binding, chứng chỉ SP nếu dùng. IdP admin phải đăng ký đúng các giá trị.
2. **SP-initiated SSO:** mở /me không có local session; thấy redirect tới IdP; xác thực ở IdP; IdP POST SAMLResponse về ACS; SP tạo Authentication; /me hiển thị NameID từ IdP.
3. **SSO giữa hai SP:** đăng nhập SP A rồi mở SP B cùng IdP; B vẫn tạo flow riêng, IdP có thể không yêu cầu mật khẩu nếu phiên IdP còn hiệu lực.
4. **Sai trust:** thử IdP metadata với issuer/certificate không khớp trong môi trường test, kiểm tra SP từ chối login và không tạo Authentication.
5. **Sai ACS/audience:** thử cấu hình Destination/Recipient/AudienceRestriction không khớp giữa hai bên; xác nhận thất bại thay vì cho login.
6. **Clock skew:** giả lập đồng hồ sai hoặc Assertion quá hạn trong sandbox; kiểm tra thông báo lỗi có thể chẩn đoán và không tắt validation để “fix”.
7. **Certificate rollover:** tập dượt nhận metadata có chứng chỉ mới theo quy trình, bảo đảm không có khoảng trống trust và không phải vô hiệu signature check.
8. **Logout:** phân biệt local logout với SAML SLO; xác minh phiên SP và IdP biến mất đến mức nào, và các SP khác có nhận logout hay không.
9. **Reverse proxy:** kiểm tra thực tế entityId/ACS sử dụng hostname HTTPS công khai, không lộ HTTP localhost hay port nội bộ.
10. **Authorization:** sau khi SAML xác thực, user không có role phù hợp vẫn bị chặn ở endpoint nghiệp vụ nhạy cảm.

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể / hướng kiểm tra |
| --- | --- |
| Không tải được metadata IdP khi start | Metadata URI sai, IdP chưa hoạt động, TLS/trust/network lỗi, cấu hình trust không tương thích. |
| IdP báo unknown SP hoặc invalid audience | SP entityId khác giá trị đã đăng ký tại IdP. |
| IdP báo ACS/Reply URL mismatch | ACS của Spring khác URL đã cho phép tại IdP; proxy làm sai scheme/host/port. |
| POST callback thất bại do signature verification | Certificate IdP cũ/sai, chữ ký thiếu theo chính sách, trust không khớp hoặc message bị biến đổi. |
| Authentication thất bại do thời gian | NTP/clock skew, NotBefore/NotOnOrAfter, SubjectConfirmationData quá hạn. |
| Login xong không có quyền truy cập | Authentication SAML thành công nhưng role/authority nghiệp vụ chưa ánh xạ; kiểm tra authorization phía SP. |
| Người dùng logout SP nhưng quay lại được ngay | IdP session còn hoạt động; SP local logout không đồng nghĩa IdP logout. |
| Muốn xuất IdP metadata từ /saml2/metadata | Sai vai trò: endpoint đó xuất **SP metadata**, không phải **IDPSSODescriptor**. |
| Đã thêm spring-security-saml2-service-provider nhưng không có trang quản trị user | Đúng theo thiết kế: dependency này không xây IdP/identity store. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một ứng dụng bật saml2Login() và có /saml2/metadata/corp. Nó đã là SAML IdP chưa?  
**Đáp án:** Chưa. Ứng dụng là **SP**; metadata được xuất là **SP metadata**, còn IdP phải nhận AuthnRequest, xác thực user và phát hành signed Assertion.

**Câu 2.** Ai sở hữu endpoint /login/saml2/sso/corp và ai sở hữu SingleSignOnService trong IdP metadata?  
**Đáp án:** ACS **/login/saml2/sso/corp thuộc SP Spring**; SingleSignOnService thuộc **IdP**, nhận AuthnRequest từ SP.

**Câu 3.** Vì sao đăng nhập SAML thành công không bảo đảm quyền truy cập /admin của SP?  
**Đáp án:** Assertion chứng minh danh tính/thuộc tính theo trust. **Authorization** tới /admin vẫn do SP quyết định; phải ánh xạ roles/authorities và áp dụng chính sách nội bộ.

**Câu 4.** Có thể đổi khóa xác minh chữ ký IdP bằng cách tắt signature validation khi gặp lỗi không?  
**Đáp án:** Không. Cần kiểm tra IdP metadata, certificate, rotation, issuer và policy; bỏ xác minh sẽ phá ranh giới tin cậy.

**Câu 5.** Nếu sản phẩm cần login portal, MFA, SAML Assertions cho 20 SP, nên giao nhiệm vụ cho module nào?  
**Đáp án:** Đây là yêu cầu **Identity Provider**. Chọn IdP/broker chuyên dụng hoặc dự án IdP riêng đầy đủ; module **spring-security-saml2-service-provider** chỉ xử lý vai trò SP.

## 13. Tài liệu tham khảo chính thức

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): mô hình SP, AuthnRequest, ACS, RelyingPartyRegistration và luồng login.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): xác minh và tùy biến xử lý Assertion/Authentication.
- [Spring Security – SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): xuất SP metadata.
- [Spring Security – SAML 2.0 Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP-/AP-initiated SLO và các điều kiện cấu hình.
- [Spring Boot – SAML 2.0](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html#web.security.saml2): tích hợp SP và Shibboleth repository. Khi triển khai Boot 3.3.5, tra tài liệu 3.3.x tương ứng để kiểm tra khác biệt phiên bản.

**Ghi nhớ cuối:** Spring Security giải quyết bài toán **ứng dụng Spring tin cậy một IdP để đăng nhập như SAML2 SP**. Nhiệm vụ **xác thực tập trung, quản trị danh tính và phát hành SAML Assertion với vai trò IdP** cần hệ thống/giải pháp khác và hợp đồng trust rõ ràng với mọi SP.
