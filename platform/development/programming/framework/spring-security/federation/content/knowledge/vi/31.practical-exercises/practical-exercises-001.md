# Xây dựng Service Provider SAML2 với metadata và IdP thử nghiệm

## 1. Mục tiêu thực hành và tiêu chí nghiệm thu

Bài thuộc nhóm **Thực hành tổng hợp** trong module **Spring Security - federation**. Người học sẽ xây dựng một **SAML 2.0 Service Provider (SP)** bằng Spring Boot/Spring Security, dùng **Keycloak** làm **Identity Provider (IdP)** thử nghiệm, trao đổi metadata đúng chiều, chạy đăng nhập **SP-initiated SAML Web Browser SSO**, kiểm tra session và thực hành các tình huống thất bại an ninh. Spring giữ vai trò SP/Relying Party; Keycloak phát Authentication Assertion theo giao thức SAML 2.0 và đảm nhiệm đăng nhập user.

Kết quả cần đạt:

1. Có Keycloak realm `saml-lab`, user thử nghiệm `alice` và SAML client đã đăng ký.
2. Có Spring Boot ứng dụng Java 17 với `spring-security-saml2-service-provider`, `SecurityFilterChain.saml2Login()` và `saml2Metadata()`.
3. Spring đọc **IdP metadata** tại `http://localhost:8081/realms/saml-lab/protocol/saml/descriptor`.
4. Keycloak dùng **SP EntityID** lấy từ **SP metadata** và **ACS** đúng đường HTTP-POST.
5. Truy cập `http://localhost:8080/me` bằng browser chưa có phiên sẽ được chuyển tới IdP; login xong SAMLResponse được Spring xác minh, trở về `/me` có `authenticated=true`.
6. Biết tại sao màn hình IdP xuất hiện **chưa** chứng minh SAMLResponse đã được SP xác minh.
7. Có bảng kiểm âm tính: sai signature, issuer, audience, ACS, timestamp, request correlation, nhóm/quyền, logout và certificate rotation.
8. Có ví dụ Java 17 thuần chạy độc lập, kiểm hợp đồng EntityID/ACS và ánh xạ nhóm chỉ theo allowlist.

**Mốc phiên bản dùng trong bài:** Java 17; Maven 3.9+; Spring Boot **3.5.0** (Spring Security 6.x); Keycloak image **26.8.2**. Đây là bộ phiên bản minh họa cụ thể cho bài lab, **không phải khuyến nghị giữ release cũ cho production**. Khi triển khai thực, chọn patch release được tổ chức phê duyệt và test lại các APIs đã thay đổi. Tài liệu Spring Security 7 có nhiều API OpenSAML/principal mới hơn; không sao chép kết hợp tùy tiện với Boot 3.x.

> **Phạm vi an ninh:** các URL HTTP, tài khoản bootstrap `admin` và passwords trong bài **chỉ dùng trên localhost**, không mở ra Internet hoặc dùng làm cấu hình production. Môi trường thật phải có HTTPS, danh tính/kho bí mật được quản lý, IdP metadata trust policy, chứng thư hợp lệ, CSRF/session/replay protection và audit không chứa SAMLResponse hay private keys.

## 2. Hiểu các thành phần trước khi cài

| Thành phần | Vai trò | Thông số lab |
| --- | --- | --- |
| **Spring SP / Relying Party** | Tạo AuthnRequest, nhận SAMLResponse, xác minh và tạo SecurityContext | `http://localhost:8080` |
| **Keycloak IdP / Asserting Party** | Xác thực user, ký và phát SAMLResponse | `http://localhost:8081` |
| **SAML AuthnRequest** | SP đề nghị IdP đăng nhập người dùng | Browser HTTP-Redirect đến IdP |
| **SAMLResponse/Assertion** | IdP chuyển kết quả xác thực, Subject và attributes | Browser HTTP-POST tới ACS |
| **IdP metadata** | IdP EntityID, SSO endpoint, public signing certificate | `/realms/saml-lab/protocol/saml/descriptor` |
| **SP metadata** | SP EntityID, ACS, supported bindings, signing/encryption descriptors nếu có | `/saml2/metadata/keycloak` |
| **RelyingPartyRegistration** | Cấu hình quan hệ SP–IdP phía Spring | `registrationId=keycloak` |
| **Assertion Consumer Service (ACS)** | Endpoint Spring nhận POST SAMLResponse | `/login/saml2/sso/keycloak` |
| **SP EntityID** | Identifier mà IdP dùng làm Client ID/Audience | `http://localhost:8080/saml2/service-provider-metadata/keycloak` |
| **Spring HTTP session** | Lưu xác thực cục bộ sau khi SAML validated | Cookie/session store, không phải IdP session |

**Một URL giống EntityID chưa chắc cần được browser dùng như trang web.** EntityID là identifier. SP default EntityID có thể cùng dạng với URL endpoint phát metadata; khi đăng ký IdP phải copy đúng `EntityDescriptor.entityID` thay vì tự đặt tên `keycloak`.

### Luồng SSO kỳ vọng

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring SP :8080
    participant I as Keycloak IdP :8081
    B->>SP: GET /me (anonymous)
    SP-->>B: 302 /saml2/authenticate/keycloak
    B->>SP: GET /saml2/authenticate/keycloak
    SP-->>B: SAML AuthnRequest HTTP-Redirect
    B->>I: GET SAML SSO endpoint with SAMLRequest
    I->>I: Identify SAML Client + authenticate alice
    I-->>B: HTML form with signed SAMLResponse
    B->>SP: POST /login/saml2/sso/keycloak
    SP->>SP: Resolve registration + verify SAML signature/conditions
    SP->>SP: Establish authenticated SecurityContext/session
    SP-->>B: Redirect to saved /me
    B->>SP: GET /me using SP session cookie
    SP-->>B: JSON authenticated = true
~~~

**Không có bước nào yêu cầu Spring nhận username/password Keycloak qua một API tự viết.** Spring tin kết quả từ IdP **sau khi** kiểm chữ ký và các điều kiện SAML, không phải chỉ vì có tham số `SAMLResponse` trong HTTP POST.

## 3. Chuẩn bị môi trường

Cài JDK 17, Maven 3.9+, Docker và một trình duyệt với DevTools. Kiểm tra:

~~~bash
java -version
mvn -version
docker version
~~~

Dành trống host ports **8080** (Spring) và **8081** (Keycloak). Nếu dùng Windows PowerShell, `curl` có thể là alias của `Invoke-WebRequest`; khi cần flags của curl chuẩn hãy gọi `curl.exe` hoặc tải XML qua browser.

Cây thư mục sẽ xây:

~~~text
saml-sp-lab/
  pom.xml
  src/main/java/com/example/samllab/
    SamlSpLabApplication.java
    SecurityConfig.java
    LabController.java
  src/main/resources/
    application.yml
~~~

Không đặt keystore/password/real tokens vào source code hoặc spreadsheet. Bản đầu tiên không cần SP signing/decryption private keys vì IdP lab được cấu hình **không yêu cầu ký AuthnRequest và không encrypt Assertion**. **IdP vẫn phải ký SAMLResponse hoặc Assertion** để Spring kiểm.

## 4. Bước 1 — Chạy Keycloak IdP trên localhost

Theo hướng dẫn Docker chính thức của Keycloak, image có thể chạy ở chế độ phát triển:

~~~bash
docker run --rm --name saml-idp-lab -p 127.0.0.1:8081:8080 -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin quay.io/keycloak/keycloak:26.8.2 start-dev
~~~

Giải thích: cổng container 8080 được publish thành **localhost:8081** trên host, không chiếm port Spring 8080; `127.0.0.1` giúp không public admin console ra mạng khác. `start-dev`, mật khẩu dễ nhớ và `--rm` **chỉ phù hợp lab**; container sẽ mất dữ liệu nếu xóa không có volume. Đừng dùng cấu hình này cho Internet hoặc môi trường doanh nghiệp.

Mở: `http://localhost:8081/admin`. Đăng nhập bằng `admin`/`admin`. Khi Keycloak sẵn sàng:
1. **Manage realms → Create realm**.
2. Đặt tên `saml-lab`, tạo realm và chọn nó trong current realm.
3. Không dùng realm `master` để chứa user/demo app; `master` phục vụ quản trị Keycloak.

### Tạo user Alice

Trong realm `saml-lab`:
- **Users → Create new user**; username `alice`, Enabled ON.
- Save, vào tab **Credentials → Set password**.
- Đặt một password chỉ dùng cho lab; đặt **Temporary OFF** để không buộc đổi ở login đầu.
- Nếu admin UI khác giữa các bản 26.x, tìm field tương đương; không thay đổi yêu cầu bảo mật.

### Xem IdP metadata

Mở trực tiếp:

~~~text
http://localhost:8081/realms/saml-lab/protocol/saml/descriptor
~~~

Hoặc:

~~~bash
curl -fsS "http://localhost:8081/realms/saml-lab/protocol/saml/descriptor"
~~~

Kỳ vọng XML metadata chứa `EntityDescriptor`, `IDPSSODescriptor`, `SingleSignOnService` và thường `KeyDescriptor` chứa public signing certificate. **Không đặt chính URI này vào ô Keycloak Client ID**: đây là **đầu vào cho Spring**, còn Keycloak Client ID phải bằng SP EntityID xuất ra từ Spring. Nếu 404, kiểm realm name, port, Docker log; nếu chưa được XML metadata thì **chưa chạy Spring với metadata-uri**.

## 5. Bước 2 — Tạo Maven project Spring Boot

### `pom.xml` hoàn chỉnh

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
    <version>3.5.0</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>saml-sp-lab</artifactId>
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
      <artifactId>spring-security-saml2-service-provider</artifactId>
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

  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <name>Shibboleth Maven Releases</name>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots>
        <enabled>false</enabled>
      </snapshots>
    </repository>
  </repositories>

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

**Vì sao cần các dependency:**
- `spring-boot-starter-web`: Servlet web server và REST controller.
- `spring-boot-starter-security`: SecurityFilterChain, Authentication/Authorization.
- `spring-security-saml2-service-provider`: SAML RP/SP integration với OpenSAML.
- Test dependencies: phục vụ unit/MockMvc regression tests sau.
- Shibboleth HTTPS Maven Releases repository: Spring Security docs hướng dẫn repository này vì một số OpenSAML artifacts có nguồn phát hành riêng. **Không bật insecure repository hoặc trust-all TLS**.
- Spring Boot parent quản lý các phiên bản tương thích. Tránh pin OpenSAML/Spring Security transitive version không tương thích.

Nếu build lỗi do repository, thử kiểm HTTPS, proxy Maven/corporate certificate trust, network và dependency tree; **không** tự cài extension cũ `spring-security-saml2-core` để “cứu” dependency mới.

### `SamlSpLabApplication.java`

~~~java
package com.example.samllab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSpLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSpLabApplication.class, args);
    }
}
~~~

Java `@SpringBootApplication` tạo context và auto-configuration; application.yml ở đúng resources path sẽ xác định HTTP port.

## 6. Bước 3 — Dùng IdP metadata tạo RelyingPartyRegistration

### `src/main/resources/application.yml`

~~~yaml
server:
  port: 8080

spring:
  security:
    saml2:
      relyingparty:
        registration:
          keycloak:
            assertingparty:
              metadata-uri: "http://localhost:8081/realms/saml-lab/protocol/saml/descriptor"
~~~

**Đọc cấu hình:**
- `registration.keycloak` là **registrationId** nội bộ, có trên các URL `/saml2/authenticate/keycloak` và `/login/saml2/sso/keycloak`.
- `assertingparty.metadata-uri` trỏ tới **IdP metadata XML**. Nó **không** phải OIDC `.well-known/openid-configuration`, không phải URL `/admin` và không phải SP metadata.
- Spring Boot có thể tự tạo `RelyingPartyRegistrationRepository` từ properties. Metadata cung cấp IdP EntityID, SSO location, supported bindings và public verification certs.
- Nếu Keycloak chưa chạy hoặc realm chưa tồn tại, build Java có thể thành công nhưng **application startup không tải được metadata**.
- Không coi một nguồn HTTP bên ngoài localhost là đáng tin. Production dùng HTTPS/PKIX và metadata issuer/certificate review.
- Cấu hình này là **lab tối thiểu** cho unsigned AuthnRequest nhưng signed SAML Response/Assertion. Không có SP private signing/decryption key nên chưa support những IdP policies yêu cầu chúng.

Đổi tên registration `keycloak` sẽ đổi default login/ACS/metadata URLs. Hãy update **cả Keycloak SAML client, IdP registered ACS và mọi test links** nếu đổi tên.

## 7. Bước 4 — Bật SAML2 filter chain và xuất SP metadata

### `SecurityConfig.java`

~~~java
package com.example.samllab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/",
                    "/error",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**")
                .permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .logout(logout -> logout.logoutSuccessUrl("/"))
            .build();
    }
}
~~~

**Từng dòng có mục đích:**
- `/` public để kiểm web server hoạt động.
- `/saml2/metadata` và các variants permitAll để đối tác lấy **SP metadata** không cần session; đừng đưa thông tin riêng tư vào metadata.
- `/me` cần authenticated `SecurityContext`, nên kích hoạt Web Browser SSO nếu browser chưa đăng nhập.
- `saml2Login(...)` gắn filters và OpenSAML authentication provider; **không tự viết code parse Base64 XML trong controller**.
- `saml2Metadata(...)` bật metadata endpoint dựa trên registration.
- `logout(...)` là **local logout**, không phải SAML SLO toàn cục.
- `anyRequest().denyAll()` hạn chế các endpoints lạ; dự án thật cần rule chi tiết theo business authorization.

**Không disable CSRF toàn bộ ứng dụng.** SAML POST ACS thuộc framework authentication flow; state-changing business actions vẫn phải có CSRF protection hoặc cơ chế tương ứng. Nếu tự đổi ACS/filter matcher, hãy kiểm CSRF và state correlation riêng, không áp một exemption rộng cho mọi URL.

### `LabController.java`

~~~java
package com.example.samllab;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {

    @GetMapping("/")
    public String home() {
        return "SAML2 SP lab running. Open /me to start login.";
    }

    @GetMapping("/me")
    public Map<String, Object> currentUser(
            Authentication authentication) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("authenticated", authentication.isAuthenticated());
        result.put("authenticationType",
                authentication.getClass().getSimpleName());
        result.put("principalAvailable",
                authentication.getName() != null
                        && !authentication.getName().isBlank());
        return result;
    }
}
~~~

Trong lab, `/me` trả về trạng thái, **không lộ SAMLResponse, token, NameID hay email**. Trường `authenticationType` có thể đổi theo phiên bản Spring Security; không xây test phụ thuộc exact type name. Trong production cần loại bỏ/hạn chế debug endpoint này hoặc thay bằng API dữ liệu đã được phê duyệt.

## 8. Bước 5 — Khởi động Spring và kiểm metadata

Từ root thư mục `saml-sp-lab`:

~~~bash
mvn clean verify
mvn spring-boot:run
~~~

**Keycloak phải chạy sẵn** để Spring đọc IdP metadata. Nếu cần kiểm network qua terminal:

~~~bash
curl -fsS "http://localhost:8081/realms/saml-lab/protocol/saml/descriptor"
~~~

Mở URL:

~~~text
http://localhost:8080/
~~~

HTTP response body mong đợi:

~~~text
SAML2 SP lab running. Open /me to start login.
~~~

Đây chỉ chứng minh web server/controller chạy; `/` public, **chưa chứng minh SAML2 login**.

### Lấy SP metadata

~~~bash
curl -fsS "http://localhost:8080/saml2/metadata/keycloak"
~~~

Hoặc mở bằng browser. XML thật thường chứa `EntityDescriptor`, `SPSSODescriptor` và `AssertionConsumerService`. Với defaults của registration trong lab, hai giá trị cần xem:

~~~text
SP EntityID:
  http://localhost:8080/saml2/service-provider-metadata/keycloak

SP ACS HTTP-POST:
  http://localhost:8080/login/saml2/sso/keycloak
~~~

**Không hardcode kết luận nếu metadata runtime khác**: lấy trực tiếp `EntityDescriptor/@entityID` và `AssertionConsumerService/@Location` từ XML. Khi có custom entityId, reverse proxy, context path hoặc Spring version khác, giá trị có thể thay.

SP metadata endpoint cũng có các variants trong Spring Security:
- `/saml2/metadata`;
- `/saml2/metadata/{registrationId}`;
- `/saml2/service-provider-metadata/{registrationId}`.

**`/saml2/authenticate/keycloak` KHÔNG phải endpoint metadata.** Nó là endpoint tạo AuthnRequest, thường trả redirect sang IdP.

### So sánh hai metadata

| Field | Nguồn | Dùng để cấu hình nơi nào? |
| --- | --- | --- |
| IdP `EntityDescriptor.entityID` | Keycloak IdP metadata | Spring trusting/asserting-party issuer |
| IdP `SingleSignOnService.Location` | Keycloak IdP metadata | Spring AuthnRequest destination |
| IdP `KeyDescriptor use=signing` | Keycloak IdP metadata | Spring verify signature IdP |
| SP `EntityDescriptor.entityID` | Spring SP metadata | Keycloak SAML Client ID |
| SP `AssertionConsumerService.Location` | Spring SP metadata | Keycloak Master SAML Processing URL |
| SP `AssertionConsumerService.Binding` | Spring SP metadata | Keycloak response binding |
| SP `KeyDescriptor use=signing/encryption` | SP metadata nếu đã cấu hình keys | Keycloak verify request/encrypt Assertion |

**Không gửi SP decryption private key cho IdP.** IdP chỉ cần public encryption certificate của SP khi yêu cầu encryption.

## 9. Bước 6 — Đăng ký SAML client trên Keycloak

Sau khi kiểm metadata SP:

1. Trong Keycloak chọn realm `saml-lab`, vào **Clients → Create client**.
2. Chọn **Client type = SAML**, **không** chọn OpenID Connect.
3. **Client ID:** copy **SP EntityID** trong metadata Spring. Giá trị dự kiến của lab là:

   `http://localhost:8080/saml2/service-provider-metadata/keycloak`

4. **Master SAML Processing URL:** điền đúng **ACS**:

   `http://localhost:8080/login/saml2/sso/keycloak`

5. **Valid Redirect URIs:** thêm đúng URI ACS được phê duyệt. Không dùng wildcard `*` hoặc một domain ngoài ý muốn.
6. **Name ID Format:** chọn format IdP hỗ trợ cho user demo; nếu chọn persistent cần xác định cơ chế identity stability của Keycloak. Không suy từ tên field là NameID không thể đổi.
7. Trong nhóm **SAML capabilities**, yêu cầu IdP **ký SAML Response hoặc Assertion** bằng key phù hợp; Keycloak thường có tùy chọn **Sign Documents** và **Sign Assertions**. Không tắt cả hai.
8. Vì SP lab chưa có signing credential, **Client Signature Required = Off** để Keycloak cho phép AuthnRequest chưa ký. Đây là lựa chọn riêng cho **lab**. Khi chính sách thật yêu cầu AuthnRequest signed, phải thêm SP signing private key/cert.
9. **Không bật Encryption** cho Assertion ở bước đầu nếu chưa có SP decryption key/certificate.
10. Save và mở lại client để xác minh URI/capabilities được lưu đúng.

Keycloak version có thể bố trí các field ở tab khác nhau; đối chiếu chức năng **Client ID/ACS/redirect/signature requirements** thay vì cố tìm y hệt UI từ một hình cũ.

### Vì sao Client ID không phải chuỗi `keycloak`?

`registrationId=keycloak` chỉ phân biệt cấu hình nội bộ **trong Spring**. Trong `samlp:AuthnRequest`, `saml:Issuer` thường là **SP EntityID**; Keycloak dựa vào issuer/client ID để biết client nào đang yêu cầu SSO. Nếu điền Client ID là `keycloak` nhưng SP phát issuer là URL metadata, Keycloak có thể báo **client not found/invalid client**.

### Nếu Keycloak hỗ trợ import SP metadata

Có thể nhập trực tiếp URL `/saml2/metadata/keycloak` hoặc XML đã tải. **Vẫn phải đối chiếu** SP EntityID, ACS, bindings, signing requirements và redirect allowlist sau import. Không mặc định chức năng import hoàn tất trust policy hoặc chính sách ký.

## 10. Bước 7 — Đăng nhập Web Browser SSO

Mở cửa sổ riêng tư hoặc browser profile chưa có Spring session:

~~~text
http://localhost:8080/me
~~~

Hành trình thành công:
1. Spring thấy resource cần authenticated → bắt đầu SAML2 login.
2. Spring phát `AuthnRequest` và browser đi tới Keycloak.
3. Keycloak xác định SAML client theo Issuer, yêu cầu user `alice` nhập password nếu chưa có IdP session.
4. Sau khi user xác thực, Keycloak sinh **signed SAMLResponse/Assertion**.
5. Browser thực hiện **HTTP POST** chứa `SAMLResponse` tới `/login/saml2/sso/keycloak`.
6. Spring `Saml2WebSsoAuthenticationFilter` và OpenSAML provider xác minh signature, issuer, audience, Destination/Recipient, Conditions, SubjectConfirmationData, request correlation và các ràng buộc áp dụng.
7. Spring tạo authenticated `Authentication`, lưu `SecurityContext`/session.
8. Browser được redirect về `/me` và nhận JSON với `authenticated: true`.

Ví dụ JSON **minh họa**, class/type name có thể đổi:

~~~json
{
  "authenticated": true,
  "authenticationType": "Saml2Authentication",
  "principalAvailable": true
}
~~~

Đừng suy một trạng thái ở bước 3 là hoàn thành: Keycloak hiển thị login page chỉ chứng minh SP AuthnRequest khởi tạo được; **chưa chứng minh SAMLResponse đã được Spring verify**.

### Các điểm kiểm chứng độc lập

| Quan sát | Kết luận có thể rút ra |
| --- | --- |
| Trang root `/` trả 200 | Spring Boot hoạt động |
| Browser được chuyển đến IdP | AuthnRequest start cơ bản |
| User login thành công phía Keycloak | IdP xác thực user |
| Network có POST `/login/saml2/sso/keycloak` | Response đến ACS |
| Spring lập session và `/me` authenticated=true | SP đã xử lý SAML hợp lệ trong config đã triển khai |
| Tài nguyên yêu cầu business role bị deny với user thiếu entitlement | Authorization app hoạt động |
| Invalid signature/issuer/audience bị reject | Negative security checks còn hiệu lực |

**Không thu thập raw SAMLResponse vào public bug tracker.** Trong môi trường thử nghiệm, chỉ dùng test identities, và HAR/logs có thể chứa session cookie/AttributeValue nên phải bảo vệ.

## 11. Metadata XML: đọc đúng dù XML có nhiều namespace

IdP metadata skeleton:

~~~xml
<!-- Minh họa giản lược, KHÔNG phải metadata có thể import thật. -->
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="http://localhost:8081/realms/saml-lab">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- public certificate of Keycloak -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="http://localhost:8081/realms/saml-lab/protocol/saml"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

SP metadata skeleton:

~~~xml
<!-- Minh họa giản lược; giá trị thật lấy từ SP metadata endpoint. -->
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="http://localhost:8080/saml2/service-provider-metadata/keycloak">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="http://localhost:8080/login/saml2/sso/keycloak"
      index="0"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

**Hai XML trên là sơ đồ có lược bỏ phần tử bắt buộc của metadata hoàn chỉnh**, tuyệt đối không dùng chúng thay XML từ IdP/SP trong quá trình import. Trong thực tế XML namespace prefix, thứ tự elements, certificate descriptors, ACS index và signing flags có thể khác.

Lấy field từ namespace-aware XML parser hoặc xem metadata thật. Đặc biệt:
- `EntityDescriptor.entityID` không phải tự động là URL login.
- `SPSSODescriptor` định nghĩa SP; `IDPSSODescriptor` định nghĩa IdP.
- `KeyDescriptor use=signing` thường chứa public key để bên đối tác verify SAML message.
- `KeyDescriptor use=encryption` thường chứa public key dùng encrypt cho recipient.
- `AssertionConsumerService.Binding` phải tương thích với binding mà IdP phát response.
- `SingleLogoutService` chỉ liên quan khi cấu hình SLO.

## 12. Spring Security xử lý SAMLResponse như thế nào?

Ở runtime, hai endpoint có vai trò khác:

~~~text
/saml2/authenticate/{registrationId}
  -> Saml2WebSsoAuthenticationRequestFilter
  -> construct AuthnRequest and redirect to IdP

/login/saml2/sso/{registrationId}
  -> Saml2WebSsoAuthenticationFilter
  -> Saml2AuthenticationToken (untrusted before verification)
  -> AuthenticationManager / OpenSAML provider
  -> verify signature, issuer, audience, time, recipient, correlation
  -> Saml2Authentication and SecurityContext
~~~

Provider có thể còn decrypt `EncryptedAssertion`/`EncryptedAttribute`/`EncryptedID` khi cấu hình SP decryption credentials. **Không cần và không được tự viết servlet controller `POST /login/saml2/sso/keycloak` để decode XML rồi gán `ROLE_USER` từ raw Request**.

### Spring Security version

Bài Boot 3.5/Security 6.x có APIs/Authentication types khác dòng Spring Security 7 hiện hành. Spring 7 docs dùng `OpenSaml5AuthenticationProvider` và `Saml2ResponseAssertionAccessor`; nhiều code Spring 6 dùng `Saml2AuthenticatedPrincipal`. Khi nâng phiên bản hãy kiểm actual dependency, public APIs và integration tests; ví dụ `SecurityConfig` ở trên không dựa vào principal implementation.

### Issuer và trust

IdP ký SAMLResponse bằng **private signing key của IdP**; SP verify bằng **IdP public certificate** đã phê duyệt. Nếu IdP tự rotate cert, application cần metadata/trust refresh policy, không tự chấp nhận mọi certificate. Một signed SAML Assertion với issuer đúng vẫn phải qua **AudienceRestriction, Recipient, NotBefore/NotOnOrAfter, InResponseTo và replay safeguards**.

## 13. Phân biệt login và quyền nghiệp vụ

`/me` dùng `authenticated()` để kiểm SAML login, **không yêu cầu business role**. Với hệ thống thật:
- Link user theo trusted IdP issuer + stable subject identifier (và tenant namespace nếu cần), không chỉ email.
- IdP attributes là dữ liệu có cấu trúc; một `Attribute` có thể mang **0..N `AttributeValue`**.
- `groups` nhiều giá trị cần được duyệt toàn bộ; không chỉ `getFirstAttribute("groups")`.
- Chỉ map nhóm đã approve như `APP_REPORT_VIEWERS` → `ROLE_REPORT_VIEWER`.
- Nhóm `Domain Admins` trong AD không tự cấp `ROLE_ADMIN` của ứng dụng.
- Thiếu `tenant` bắt buộc nên deny; thiếu email tùy chọn không nhất thiết làm auth fail.
- Local user disabled phải deny dù Assertion ký đúng.
- Một SAML authenticated session không có nghĩa user được phép xem mọi resource trong API.

### Bài tập role sau bước smoke test

1. Tạo Keycloak group `APP_REPORT_VIEWERS` và gán cho `alice`.
2. Cấu hình SAML client group mapper phát Attribute Name do hai phía thống nhất, ví dụ `urn:example:claims:groups`.
3. Verify XML assertion **trong môi trường lab an toàn** hoặc kiểm verified attribute accessor sau Spring provider.
4. Map các giá trị trong list sang app authority theo exact allowlist.
5. Tạo endpoint `/reports` có `hasAuthority("ROLE_REPORT_VIEWER")`.
6. Dùng một user không có group để test 403; dùng user có group để test 200.
7. Thử thêm `Domain Admins` rồi xác nhận **không có ROLE_ADMIN**.
8. Không đưa group list thô/NameID/PII vào logs hoặc external analytics.

## 14. Java 17 độc lập: kiểm hợp đồng EntityID, ACS và role mapping

Một chương trình Java 17 thuần có thể giúp phát hiện sự nhầm lẫn giữa `registrationId`, `SP EntityID` và `ACS` trước khi gửi metadata cho Keycloak. **Chương trình dưới đây không parse SAML XML, không verify signature, không làm IdP hoặc SP**. Nó chỉ minh họa các chuỗi trong hợp đồng federation và mapping nhóm an toàn. Spring/OpenSAML vẫn phải xử lý tất cả xác minh mật mã/giao thức trong hệ thống thật.

Tạo file **`SamlSpMetadataContractDemo.java`**:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SamlSpMetadataContractDemo {

    record SpContract(
            String registrationId,
            URI entityId,
            URI acs,
            URI idpMetadata) {}

    static boolean sameContract(
            SpContract expected, SpContract actual) {
        return expected.equals(actual);
    }

    static boolean validAcs(URI registered, URI candidate) {
        return registered.getScheme().equals(candidate.getScheme())
                && registered.getHost().equalsIgnoreCase(
                        candidate.getHost())
                && registered.getPort() == candidate.getPort()
                && registered.getRawPath().equals(
                        candidate.getRawPath())
                && candidate.getRawQuery() == null
                && candidate.getRawFragment() == null;
    }

    static Set<String> appRoles(List<String> groups) {
        Set<String> result = new TreeSet<>();
        for (String group : groups) {
            if ("APP_REPORT_VIEWERS".equals(group)) {
                result.add("ROLE_REPORT_VIEWER");
            }
            if ("APP_REPORT_EDITORS".equals(group)) {
                result.add("ROLE_REPORT_EDITOR");
            }
        }
        return result;
    }

    public static void main(String[] args) {
        SpContract expected = new SpContract(
                "keycloak",
                URI.create("http://localhost:8080"
                        + "/saml2/service-provider-metadata/keycloak"),
                URI.create("http://localhost:8080"
                        + "/login/saml2/sso/keycloak"),
                URI.create("http://localhost:8081"
                        + "/realms/saml-lab/protocol/saml/descriptor"));

        SpContract actual = new SpContract(
                expected.registrationId(),
                expected.entityId(),
                expected.acs(),
                expected.idpMetadata());

        SpContract wrongAcs = new SpContract(
                "keycloak", expected.entityId(),
                URI.create("http://localhost:8080"
                        + "/login/saml2/sso/other"),
                expected.idpMetadata());

        System.out.println("SP contract matches: "
                + sameContract(expected, actual));

        System.out.println("Wrong ACS detected: "
                + !sameContract(expected, wrongAcs));

        System.out.println("Registered ACS allowed: "
                + validAcs(expected.acs(), actual.acs()));

        System.out.println("Unregistered redirect rejected: "
                + !validAcs(expected.acs(),
                  URI.create("http://evil.example/login/saml2/sso/keycloak")));

        System.out.println("ACS with query rejected: "
                + !validAcs(expected.acs(),
                  URI.create(expected.acs() + "?ticket=FAKE")));

        System.out.println("Registration ID: "
                + expected.registrationId());

        System.out.println("Approved roles: "
                + appRoles(List.of(
                  "Domain Admins", "APP_REPORT_VIEWERS")));

        System.out.println("External admin becomes app admin: "
                + appRoles(List.of("Domain Admins"))
                  .contains("ROLE_ADMIN"));

        System.out.println("No app groups grants no role: "
                + appRoles(List.of("OTHER_TEAM")).isEmpty());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac SamlSpMetadataContractDemo.java
java SamlSpMetadataContractDemo
~~~

**Stdout chính xác:**

~~~text
SP contract matches: true
Wrong ACS detected: true
Registered ACS allowed: true
Unregistered redirect rejected: true
ACS with query rejected: true
Registration ID: keycloak
Approved roles: [ROLE_REPORT_VIEWER]
External admin becomes app admin: false
No app groups grants no role: true
~~~

**Giải thích:**
- `sameContract` dùng record equality để so bốn field; một ACS khác là thay đổi hợp đồng, không nên áp dụng khi IdP chưa sửa registered URI.
- `validAcs` minh họa exact scheme/host/port/path và không có query/fragment; **không thay Spring/OpenSAML Destination/Recipient validator**.
- `appRoles` dùng allowlist, không biến một nhóm hạ tầng thành ứng dụng admin.
- Kết quả không chứng minh chứng thư, XML Signature, SAML Conditions, replay, InResponseTo hoặc request correlation thực sự PASS.
- Trong production phải lấy trusted metadata/certificates, không cho user nhập URI tự do để thành trust authority.

## 15. Mở rộng 1 — Bật signed AuthnRequest

Mẫu đầu tiên chọn **Keycloak Client Signature Required = Off** vì Spring SP chưa có private signing key. Trong ứng dụng thật cần chính sách thống nhất:

1. Sinh một cặp private key + X.509 certificate **của SP** cho lab, dùng thuật toán đáp ứng crypto baseline.
2. Lưu private signing key ở secret store/file có ACL tối thiểu; không commit vào Git.
3. Đưa SP **public signing certificate** vào metadata/Keycloak SAML client.
4. Cấu hình Spring `Saml2X509Credential.signing(...)` hoặc Boot signing credentials.
5. Bật Keycloak **Client Signature Required**.
6. Kiểm Spring thực sự ký AuthnRequest đúng binding và Keycloak chấp nhận.
7. Kiểm altered request/unknown certificate bị IdP reject.

Fragment YAML (đặt **dưới `registration.keycloak`**, không phải một file YAML hoàn chỉnh):

~~~yaml
signing:
  credentials:
    - private-key-location: "file:/run/secrets/saml/sp-signing.key"
      certificate-location: "file:/etc/saml/sp-signing.crt"
~~~

Địa chỉ file chỉ minh họa; cần cung cấp keypair thật **trong môi trường lab bảo vệ phù hợp**. Nếu IdP yêu cầu signing nhưng SP chưa hỗ trợ, **không khắc phục bằng cách tắt kiểm chữ ký SAMLResponse ở SP**. Hai chiều signature khác nhau: SP ký request cho IdP, IdP ký response/assertion cho SP.

## 16. Mở rộng 2 — EncryptedAssertion và SP decryption key

Để thử encryption:
1. SP sinh hoặc nhận **private decryption key + certificate** hợp lệ.
2. SP công bố **public encryption certificate** trong metadata cho Keycloak.
3. Keycloak encrypt Assertion bằng SP public certificate; browser chuyển **EncryptedAssertion** tới SP.
4. Spring decrypt bằng **SP private key** trước/sau signature checks theo đúng Spring/OpenSAML provider workflow.
5. SP tiếp tục kiểm issuer, audience, recipient, signature, Conditions, subject confirmation và replay.
6. Test sai key/decryption failure phải **FAIL CLOSED**; không chuyển sang đọc plaintext không xác minh.

Boot YAML fragment đặt dưới `registration.keycloak`:

~~~yaml
decryption:
  credentials:
    - private-key-location: "file:/run/secrets/saml/sp-decrypt.key"
      certificate-location: "file:/etc/saml/sp-decrypt.crt"
~~~

**Phân biệt:** `EncryptedAssertion` mã hóa cả Assertion, `EncryptedAttribute` mã hóa một Attribute và `EncryptedID` mã hóa identifier. XML Signature bảo vệ integrity/authenticity còn XML Encryption bảo vệ confidentiality; **mã hóa không thay chữ ký**. Dùng lab keys và regenerate signed/encrypted fixtures, không sửa raw signed XML để tạo test khác.

## 17. Mở rộng 3 — Local logout và SAML Single Logout

Trong lab ban đầu, `POST /logout` thực hiện **local session logout** theo Spring Security. Browser có thể được redirect đến `/`; **IdP SSO session của Keycloak có thể vẫn sống**, nên lần vào `/me` tiếp theo có thể được đăng nhập lại mà không phải nhập password. Đây không phải bằng chứng local logout thất bại.

**SAML Single Logout (SLO)** riêng cần:
- IdP metadata có `SingleLogoutService` và binding được hỗ trợ.
- SP có signing credential khi IdP/protocol yêu cầu ký LogoutRequest/LogoutResponse.
- Đã thống nhất RP-initiated và IdP-initiated logout endpoints, ví dụ `/logout/saml2/slo` theo Spring.
- Bật `saml2Logout(Customizer.withDefaults())` **sau khi** prerequisites hoàn chỉnh.
- Test LogoutRequest/LogoutResponse signature/issuer/destination/correlation và session index/nameID matching.
- Audit `LOGOUT_REQUESTED`, `LOGOUT_LOCAL_COMPLETED`, `LOGOUT_SLO_DISPATCHED`, `LOGOUT_SLO_CONFIRMED` riêng theo phạm vi có chứng cứ.

**Không gắn nhãn global logout thành công khi chỉ thấy HTTP 302 hoặc một session Spring đã bị hủy.** Nếu IdP SSO session còn sống, lần truy cập mới có thể khởi tạo SSO như thường.

## 18. Mở rộng 4 — Reverse proxy HTTPS và session cookie

Trong production, public URL có thể là `https://portal.example.com` nhưng ứng dụng nội bộ ở `http://spring:8080`. Nếu metadata SP tự suy từ host nội bộ, IdP gửi `Destination`/`Recipient` khác expected ACS, khiến login fail.

Cần:
- Chọn canonical public SP EntityID và ACS; đưa vào `RelyingPartyRegistration`/metadata và IdP registration đồng thời.
- Dùng trusted `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host`/`X-Forwarded-Port` hoặc Boot `server.forward-headers-strategy` phù hợp.
- **Không trust forwarded headers do Internet client tự cung cấp**; ingress phải sanitize.
- Dùng HTTPS + PKIX/hostname verification, HSTS theo policy, cookie `Secure`/`HttpOnly`/`SameSite` phù hợp.
- Với cross-site SAML HTTP-POST ACS, `SameSite=Lax` có thể làm cookie session không được gửi; một số kiến trúc cần `SameSite=None; Secure` và CSRF/correlation controls.
- Tổ chức multi-pod cần session/request repository hoạt động giữa nodes hoặc routing consistent; kiểm `InResponseTo`/`RelayState`.
- Không đặt session ID hoặc raw SAMLResponse vào URL, log, client storage.

**Điều thú vị:** localhost:8080 và localhost:8081 là **khác origin nhưng có thể cùng site** vì port không tạo khác site theo browser site semantics. Vì vậy thành công trên localhost **không chứng minh** cookie behavior sẽ đúng giữa hai production domains khác site. Phải test end-to-end trên HTTPS domains đại diện môi trường thật.

## 19. Lỗi thường gặp và cách xác định nhanh

| Dấu hiệu | Nguyên nhân có thể | Kiểm/sửa |
| --- | --- | --- |
| App không khởi động | IdP metadata URI 404/connection refused | Khởi động realm/Keycloak trước Spring |
| Maven không tìm OpenSAML | Thiếu Shibboleth Releases/HTTPS proxy | Sửa build repository, không trust-all |
| SP metadata trả 404 | Chưa bật `saml2Metadata` hoặc sai registrationId | Kiểm SecurityFilterChain/repository |
| Keycloak “client not found” | Client ID không bằng SP AuthnRequest Issuer/EntityID | Copy SP metadata entityID chính xác |
| Invalid redirect URI | ACS chưa đăng ký | Đăng ký exact ACS |
| Keycloak đòi signed request | Client Signature Required ON nhưng SP chưa signing | Bổ sung SP key/cert hoặc đổi policy riêng lab |
| IdP login thành công nhưng browser 404 tại SP | Master SAML Processing URL sai | So ACS từ SP metadata |
| Signature validation failed | IdP signing disabled/sai public cert/trust | Ký IdP response/assertion và kiểm metadata |
| SAML issuer mismatch | IdP metadata/Issuer khác registration | Dùng đúng realm EntityID và signing keys |
| Audience mismatch | SP EntityID không trùng IdP Client ID/Audience | Sửa approved partner contract |
| Destination/Recipient mismatch | Wrong ACS, reverse proxy scheme/host | Chỉnh public ACS và proxy |
| InResponseTo mismatch | Mất AuthnRequest state/cookie/cluster | Kiểm session repository, RelayState |
| Assertion expired/not yet valid | IdP/SP clock skew, login quá chậm | Đồng bộ NTP, tolerance nhỏ có căn cứ |
| Cannot decrypt | IdP encrypt nhưng SP thiếu/sai private key | Cấu hình decryption credential |
| Login loop | Cookie SameSite/session missing/IdP config | Kiểm DevTools Network và cookies |
| Authenticated nhưng API 403 | Thiếu local group/tenant authorization | Thêm mapping đúng và test deny |
| Login chỉ pass trên một pod | Metadata/keyset/session store drift | Kiểm configs, replication và sticky routing |
| Metadata cert mới nhưng Spring chưa dùng | Registration snapshot/cache stale | Refresh/rollback theo trust change policy |
| SP logs đầy SAML XML | Debug body capture | Tắt thu thập raw SAMLResponse, xử lý dữ liệu lộ |

**Runbook theo thứ tự:** network/metadata → SP EntityID/client → ACS/redirect → IdP signing cert → SAML provider validation → Spring session/cookie → local business authorization. Đừng nới signature/audience/replay checks để vượt lỗi cấu hình.

### Kiểm DevTools an toàn

Dùng test user trên lab:
1. Xem `GET /me` chuyển tới login start.
2. Xem `SAMLRequest` redirect tới đúng realm trên port 8081.
3. Xem Keycloak có thể authenticate `alice`.
4. Xem browser POST tới `/login/saml2/sso/keycloak`.
5. Xem ACS response redirect về `/me`.
6. Xem session cookie và `authenticated=true`.

Không copy raw `SAMLResponse`, session cookie hoặc HAR đầy đủ vào tài liệu công khai. SAMLResponse có thể mang PII/AttributeValue; `no-store` và redacted logs quan trọng ngay cả trong môi trường thử nghiệm.

## 20. Ma trận kiểm thử tích hợp và an ninh

| ID | Ca kiểm thử | Kết quả cần có |
| --- | --- | --- |
| L01 | Realm/user/keycloak SAML client tồn tại | IdP metadata có thể đọc |
| L02 | Spring đọc IdP metadata | Boot khởi động, repository tạo registration |
| L03 | `GET /` anonymous | HTTP 200 body của lab |
| L04 | `GET /saml2/metadata/keycloak` | XML SP metadata có EntityID/ACS |
| L05 | Client ID bằng SP EntityID | AuthnRequest tới đúng client |
| L06 | Registered ACS đúng | SAMLResponse POST tới Spring |
| L07 | Signed SAMLResponse/Assertion đúng key | Provider authenticate |
| L08 | User `alice` đúng password | `/me` authenticated=true |
| L09 | Sai password | Không tạo session authenticated |
| L10 | User chưa có Spring session | Bắt đầu SP-initiated SSO |
| L11 | Client ID sai | IdP từ chối/không tìm thấy client |
| L12 | ACS không nằm redirect allowlist | IdP từ chối theo chính sách |
| L13 | Unsigned SAML Assertion và Response | Spring reject |
| L14 | Signature unknown cert | Spring reject |
| L15 | Audience là SP khác | Spring reject |
| L16 | Recipient hoặc Destination khác ACS | Spring reject |
| L17 | InResponseTo không khớp request | Reject trong SP-initiated flow |
| L18 | NotBefore tương lai | Reject ngoài approved skew |
| L19 | NotOnOrAfter hết hạn | Reject ngoài approved skew |
| L20 | Replay cùng Response/Assertion ID | Reject theo replay/correlation controls |
| L21 | XML Signature Wrapping/XXE | Parser/provider reject |
| L22 | EncryptedAssertion đúng SP key | Decrypt và verify đầy đủ |
| L23 | EncryptedAssertion sai SP key | Reject, không fallback |
| L24 | Optional email missing | Identity/authorization policy xử lý đúng |
| L25 | Required tenant missing | Deny business access |
| L26 | Group AttributeValue đa trị | Map exact allowlist, không chỉ first |
| L27 | User có nhóm Domain Admins | Không tự cấp app ROLE_ADMIN |
| L28 | User local disabled | Deny theo local account policy |
| L29 | Local POST logout | Session local bị invalidated |
| L30 | IdP session còn sau local logout | Login có thể lại im lặng, được giải thích đúng |
| L31 | SLO khi bật, RP initiated | Signed request/response và correlation |
| L32 | SLO invalid IdP initiated | Không xóa session tùy tiện |
| L33 | Third-party cookie/cross-site POST | Request correlation và CSRF vẫn đúng |
| L34 | Callback tới pod khác | Session/repository state consistent |
| L35 | IdP signing key rollover | Approved certificate rotation |
| L36 | SP decryption key rollover | Old/new key overlap theo policy |
| L37 | Metadata refresh khi IdP offline | Có fail/retry/cache policy rõ |
| L38 | Reverse proxy HTTPS | Public EntityID/ACS khớp metadata |
| L39 | Spoofed Forwarded headers | Không tạo malicious external ACS |
| L40 | Logs/APM/HAR | Không chứa raw SAMLResponse/keys/PII |
| L41 | SAML login có nhưng thiếu app group | Business endpoint bị từ chối |
| L42 | Hai IdPs có cùng email | Không account-link nhầm |
| L43 | Spring Security upgrade | API/build/protocol regressions được test |
| L44 | Unsupported binding/profile | Được nhận diện, không âm thầm hạ yêu cầu |
| L45 | Backup/restore IdP+SP config | EntityID/ACS/cert revisions được phục hồi |

**Không đánh dấu tất cả test PASS chỉ vì bài viết có ma trận.** Smoke test L01–L10 có thể chạy thủ công theo lab; nhiều test âm tính cần **signed fixtures được sinh bởi test IdP**. Sửa bytes XML sau khi đã ký thường chỉ làm signature fail, **không** chứng minh validator riêng cho audience/expiration hoạt động.

## 21. Kiểm thử bằng công cụ nào, tránh hiểu nhầm

**Browser E2E + Keycloak:** kiểm full redirects/POST, login/session/cookie. Cần thiết để xác nhận IdP thực và ACS.

**Spring MockMvc/unit tests:** kiểm `/me` yêu cầu authenticated, rule `denyAll` và local role mapping. Không chứng minh IdP signature trust/metadata exchange nếu chỉ mock Authentication.

**OpenSAML signed fixtures:** dùng IdP test hoặc OpenSAML test signer tạo Assertion/Response có chữ ký hợp lệ bằng **lab keys**; thay issuer/audience/time **trước khi ký** rồi đi qua provider Spring thật. Không dùng production private keys.

**Metadata comparisons:** đọc XML namespace-aware, đối chiếu EntityID/ACS, signing keys, binding, SLO. Không so XML byte-for-byte khi order/namespaces không ảnh hưởng semantics; **so URI identifiers chính xác**.

**Security scanning:** kiểm dependency vulnerabilities và Keycloak/Spring patch versions, no secrets in Git/CI, HTTP request-body logging disabled.

## 22. Checklist nghiệm thu và bàn giao

- [ ] Docker Keycloak chỉ bind localhost, realm `saml-lab` có user `alice`.
- [ ] IdP metadata descriptor trả XML; Spring đọc được qua `metadata-uri`.
- [ ] Dự án Maven Java 17 có `spring-security-saml2-service-provider`, Spring Security/Boot BOM tương thích.
- [ ] `SecurityFilterChain` bật `saml2Login`, `saml2Metadata`.
- [ ] Public root/metadata accessible, protected `/me` cần SAML login.
- [ ] SP metadata trả `EntityDescriptor`, ACS và đúng SP EntityID.
- [ ] Keycloak SAML Client ID **bằng đúng SP EntityID**, không phải registrationId.
- [ ] Master SAML Processing URL/Valid Redirect URIs **đúng ACS**.
- [ ] Keycloak ký SAMLResponse hoặc Assertion; Spring verify bằng IdP trust cert.
- [ ] SP unsigned AuthnRequest chỉ được chấp nhận khi policy lab cho phép.
- [ ] Browser redirect AuthnRequest/POST SAMLResponse end-to-end thành công.
- [ ] Spring `/me` trả `authenticated=true` sau login.
- [ ] App vẫn deny unsigned/bad issuer/bad audience/expired/replayed responses.
- [ ] Local login user linking và role/tenant policy không cấp quyền quá mức.
- [ ] Không log raw SAML XML/NameID/tokens/keys.
- [ ] Session cookie và cross-site POST được kiểm trong production-like browsers.
- [ ] HTTPS, forwarded headers, actual public EntityID/ACS được test sau ingress.
- [ ] Có certificates/metadata refresh/rotation và approval policy.
- [ ] Local logout khác SLO; không tự khẳng định IdP sessions đều bị hủy.
- [ ] Có negative E2E tests, audit, rollback và quyền đối tác khi triển khai thật.

## 23. Nguồn chính thức

1. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): AuthnRequest/Response flow, filters, RelyingPartyRegistration và OpenSAML.
2. [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `saml2Metadata` và các endpoints SP metadata.
3. [Spring Security — Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request resolver, signing và AuthnRequest repository.
4. [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): validation, decryption, principal/authorities.
5. [Spring Security — SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP initiated logout, signing và SLO endpoints.
6. [Spring Boot 3.5 — Spring Security / SAML2](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): Boot properties, OpenSAML Maven repository và auto-config.
7. [Keycloak — Getting Started on Docker](https://www.keycloak.org/getting-started/getting-started-docker): khởi động image, realm, user.
8. [Keycloak — Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/): SAML clients, Client ID, Master SAML Processing URL, Redirect URIs, signing settings.
9. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): assertion, Conditions và protocol.
10. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO/SLO profiles.
11. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityID, KeyDescriptor, ACS, SingleSignOnService.
12. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature, issuer, audience, replay và XML security.
13. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie, session rotation, local logout.
14. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh log credentials và PII.
15. [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc/security integration.

**Kết luận:** SP SAML2 hoàn chỉnh không chỉ là ứng dụng hiển thị màn hình Keycloak. Phải có **IdP metadata nhập đúng vào Spring**, **SP metadata phát đúng EntityID và ACS**, **SAML client Keycloak dùng đúng EntityID/ACS và ký response**, browser đi hết **AuthnRequest → IdP authentication → SAMLResponse POST → OpenSAML signature/issuer/audience/recipient/time/correlation validation → Spring authenticated session**. Khi smoke test thành công, tiếp tục negative tests, nhóm/quyền nghiệp vụ, HTTPS/session/cookie/proxy, SLO và certificate rotation trước khi coi hệ thống sẵn sàng production.