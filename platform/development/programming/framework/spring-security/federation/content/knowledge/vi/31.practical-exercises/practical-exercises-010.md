# Kết nối ứng dụng OIDC với hệ thống môi giới dùng IdP SAML phía sau

**Module:** Spring Security – federation  
**Nhóm:** Thực hành tổng hợp  
**Mục tiêu:** Dựng luồng đăng nhập end-to-end **Spring Boot OIDC client → identity broker → SAML Identity Provider**, thấy rõ hai ranh giới trust, ánh xạ tài khoản, quản lý phiên và kiểm thử trường hợp thất bại.  
**Công nghệ:** Java 17, Spring Boot 3.5.x/Spring Security 6.x, Keycloak 26.x làm môi giới danh tính, Keycloak realm thứ hai làm SAML IdP giả lập. Các địa chỉ `localhost` chỉ dùng cho lab; không mở `start-dev`, HTTP hoặc tài khoản quản trị demo trên production.

## 1. Kết quả học tập phải đạt

Sau bài thực hành, bạn cần tự kiểm tra được:

1. Một **ứng dụng Java chỉ cấu hình OIDC** nhưng người dùng cuối đăng nhập ở một **SAML IdP** nằm phía sau broker.
2. Broker đóng vai trò **SAML Service Provider (SP)** khi làm việc với IdP, đồng thời là **OpenID Provider (OP)** khi cấp OIDC token cho Spring Boot.
3. SAML Response được broker kiểm tra chữ ký/Issuer/Audience/Recipient/thời gian; OIDC ID Token được Spring Security kiểm tra **issuer của broker**, chữ ký/JWKS, audience, expiry/nonce theo flow.
4. Thấy **NameID/attributes của SAML** không tự trở thành cùng một giá trị với **OIDC `sub`**, và `sub` không tự cấp quyền nghiệp vụ.
5. Thấy được Authorization Code flow, callback và tài nguyên bảo vệ mà **không** log token, SAMLResponse, cookie hoặc private key.
6. Phân biệt lỗi ở IdP, broker, OIDC client, account linking và local authorization.
7. Có một lab repeatable, test positive và negative, biết tháo cấu hình lab và thay đổi gì trước khi triển khai thật.

**Điểm mấu chốt:** SAML và OIDC **không cần chạy cùng lúc trong Spring app**. Broker dịch **kết quả xác thực đã được kiểm chứng**, không phải đổi chuỗi SAMLResponse thành JWT bằng cách encode thủ công.

## 2. Sơ đồ kiến trúc và các ranh giới

~~~text
Browser                   Spring Boot:8081
   |  GET /api/me                 |
   +----------------------------> | Chưa đăng nhập
   |                               |
   | 302 tới /oauth2/authorization/broker
   |                               |
   |------------------------------>| OIDC Authorization Code + state/nonce/PKCE
   |                               |
   | 302 tới Keycloak broker realm :8080
   v                               v
+---------------------------------------------------+
| Identity broker realm: broker-oidc                |
| Vai trò downstream: OIDC OpenID Provider          |
| - nhận yêu cầu /protocol/openid-connect/auth      |
| - quản lý session và linked identities            |
| - sau upstream login phát authorization code      |
+---------------------------------------------------+
   |
   | SAML AuthnRequest (binding theo cấu hình)
   v
+---------------------------------------------------+
| SAML IdP realm: corp-saml                         |
| - xác thực user                                    |
| - tạo SAMLResponse / signed Assertion             |
+---------------------------------------------------+
   |
   | Browser POST SAMLResponse → broker SAML ACS
   v
+---------------------------------------------------+
| Broker SAML SP                                    |
| - verify IdP signing key/Issuer/Audience/ACS/time |
| - map upstream subject → broker user              |
+---------------------------------------------------+
   |
   | Browser redirect OIDC authorization code
   v
Spring Boot OIDC callback:
   /login/oauth2/code/broker
   |
   | Spring client đổi code qua backchannel token endpoint
   v
Broker OIDC ID Token: iss=broker, aud=client, sub=broker user
   |
   v
Spring Security OidcUser + local authorization
   |
   v
GET /api/me → 200; GET /api/admin → deny nếu chưa có role
~~~

### Ba vai trò cần nhớ

| Thành phần | Vai trò giao thức | Nó phải tin ai? |
| --- | --- | --- |
| **corp-saml** | **SAML IdP** | SAML SP metadata/ACS/EntityID của broker được đăng ký |
| **broker-oidc** khi nói với IdP | **SAML SP** | IdP EntityID và **signing certificate** được onboarding |
| **broker-oidc** khi nói với Spring | **OIDC OP** | OIDC client registration, redirect URI, client authentication |
| **Spring Boot app** | **OIDC Relying Party** / OAuth2 Client | Issuer/JWKS của **broker**, ID Token hợp lệ cho đúng client |
| **Database nghiệp vụ** | Quyết định quyền | Local account, tenant, roles từ nguồn được phê duyệt |

Một SAML Assertion có chữ ký hợp lệ chỉ được broker xử lý **sau khi verify đúng signed element**; một OIDC ID Token có chữ ký hợp lệ mới là thông tin để ứng dụng xác định người dùng broker; quyền /admin, owner/resource vẫn do ứng dụng quyết định.

### Hai cặp URL thường bị nhầm

**Upstream SAML:**

- IdP EntityID: giá trị EntityID thực từ SAML IdP metadata.
- IdP SSO URL: nơi broker gửi AuthnRequest.
- Broker SAML SP EntityID: identifier trong broker SP metadata.
- Broker SAML ACS: nơi IdP trả **SAMLResponse**, **không** phải Spring app.

**Downstream OIDC:**

- Broker issuer: giá trị `issuer` từ OIDC Discovery JSON.
- Broker authorization/token/JWKS endpoints: do Discovery khai báo.
- OIDC client ID: client của Spring app đăng ký tại broker.
- Spring redirect URI: nơi broker trả **authorization code**, **không** phải SAMLResponse.

**Không gửi SAMLResponse vào `/login/oauth2/code/broker`; không gửi OIDC code tới broker SAML ACS.**

## 3. Chuẩn bị lab cục bộ

Lab dùng **một Keycloak server có hai realm**, để tái hiện hai giao thức mà không cần tài khoản IdP doanh nghiệp:

- Realm **corp-saml**: mô phỏng SAML IdP của công ty.
- Realm **broker-oidc**: nhận SAML upstream, phát OIDC downstream.
- Spring Boot Java 17 app chạy trên máy host ở port **8081**.
- Keycloak trên port **8080**, cả browser và Spring host cùng truy cập `http://localhost:8080`.

**Chú ý về trust:** Hai realm trên cùng một process chỉ là **mô phỏng chức năng/protocol**, chưa mô phỏng sự phân tách mạng, vận hành, CA và khả năng tấn công của IdP độc lập. Production phải dùng endpoints/tên miền HTTPS riêng với certificate, key rotation, availability và network policies.

### Yêu cầu

- JDK 17, Maven, Docker hoặc Podman, trình duyệt có thể truy cập localhost.
- Port 8080/8081 đang trống.
- Quyền khởi động container và tạo hai realm/key client trong **lab riêng**.
- Tài khoản **chỉ dùng cho lab**, không dùng user thật, SAML metadata hoặc secrets production.
- Nếu muốn dùng lệnh JSON inspection: cài `curl` và `jq` tùy chọn.

### Khởi động Keycloak

Với Docker trên máy local:

~~~bash
docker run --rm --name kc-broker-lab \
  -p 127.0.0.1:8080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=lab-admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=lab-only-change-this \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev --hostname=http://localhost:8080
~~~

**Giải thích:**

- `start-dev` dùng defaults cho phát triển, **không** được mang nguyên vào production.
- Chỉ bind vào **127.0.0.1**, không expose 0.0.0.0.
- Admin credentials ví dụ chỉ để vào Admin Console trong lab; đừng dùng giá trị đó cho server thật.
- `--rm` làm mất dữ liệu container sau khi dừng; nếu cần làm lab nhiều lượt, cấu hình persistent volume/DB riêng theo Keycloak docs.
- Chạy Spring app trên **host**. Nếu chạy app ở container khác, `localhost` của app trỏ về container đó, không phải broker; cần DNS/hostname và routing nhất quán, đồng thời issuer URL phải truy cập được cả browser lẫn Spring.

Truy cập Keycloak Admin Console tại `http://localhost:8080/admin/`, đăng nhập **lab-admin**.

Keycloak phiên bản 26.x có thể đổi vị trí một số nút cấu hình; các tên chính cần xác định là **Realms, Identity providers, Clients, Client authentication, Standard flow, Credentials, SAML Metadata/Endpoints, First broker login**.

## 4. Thiết lập realm corp-saml làm IdP

### Bước 4.1. Tạo realm

Trong Keycloak Admin Console, chọn **Create realm**, đặt tên **corp-saml**. Realm này sẽ làm **SAML Identity Provider**.

Sau khi tạo, các endpoint dự kiến cho host lab là:

~~~text
IdP metadata/descriptor:
http://localhost:8080/realms/corp-saml/protocol/saml/descriptor

IdP SSO endpoint:
http://localhost:8080/realms/corp-saml/protocol/saml

IdP realm base / entity ID thường gặp:
http://localhost:8080/realms/corp-saml
~~~

**Phải đọc `EntityDescriptor entityID`, SingleSignOnService Binding/Location và X509Certificate từ metadata thực**, không tin một URI đã đoán chỉ vì URL trông hợp lý. Keycloak có thể thay hostname/context-path trong deployment có reverse proxy.

### Bước 4.2. Tạo test user

Trong **corp-saml → Users → Add user**:

- Username: `alice.lab`
- Email: `alice@lab.invalid` (chỉ là dữ liệu giả)
- Enabled: ON
- Credentials: đặt một mật khẩu test và tắt “Temporary” nếu muốn đăng nhập không bị yêu cầu đổi mật khẩu.
- Không gán ROLE_ADMIN, không bật production MFA/secrets.
- Có thể tạo `bob.lab` để negative test identity linking.

**Không tạo tài khoản broker tương ứng bằng tay ngay** nếu muốn thấy first broker login flow. Production lại có thể yêu cầu **pre-provisioned users/approved account linking**; xem mục 10.

### Bước 4.3. Chưa tạo SAML client quá sớm

Một SAML IdP cần biết **broker SP EntityID và ACS**. Ta sẽ tạo trước identity-provider entry ở broker, lấy **SP Descriptor** chính thức, sau đó import nó vào corp-saml. Làm như vậy giảm sai tên EntityID/ACS so với gõ tay.

## 5. Thiết lập broker-oidc làm SAML SP upstream

### Bước 5.1. Tạo realm broker-oidc

Tạo realm mới tên **broker-oidc**. Realm này có hai chức năng:

1. **Identity provider connection SAML v2.0** tới corp-saml.
2. **OIDC OP** phục vụ Spring Boot client.

Một realm Keycloak có thể làm broker và phát OIDC tokens cho nhiều clients. Trong lab hai realm tồn tại trên cùng Keycloak instance nhưng có session/keys/config riêng theo realm.

### Bước 5.2. Khai báo SAML identity provider

Tại realm **broker-oidc → Identity providers → Add provider → SAML v2.0**, dùng:

| Trường | Giá trị lab / chính sách |
| --- | --- |
| Alias | `corp-saml-upstream` |
| Enabled | ON |
| Service Provider Entity ID | Giữ giá trị do broker tạo hoặc đặt một URI rõ ràng, rồi **sử dụng đúng SP descriptor** |
| Identity Provider Entity ID | Đọc từ metadata corp-saml, **không để rỗng** |
| Single Sign-On Service URL | Từ IdP metadata, ví dụ `http://localhost:8080/realms/corp-saml/protocol/saml` |
| NameID Policy Format | Persistent nếu upstream hỗ trợ, hoặc stable attribute được phê duyệt |
| Principal Type | Subject NameID hoặc Attribute đã xác minh, có độ ổn định phù hợp |
| Want Assertions Signed | ON **khi** IdP được cấu hình ký Assertion |
| Validate Signature | ON; không chấp nhận Assertion/Response không ký theo trust policy |
| Signing certificate | Public verification cert của **corp-saml**, import từ metadata tin cậy |
| Trust Email | OFF cho lab an toàn/đặc biệt khi chưa có policy email verification |
| Store Tokens | OFF trừ khi use case cần và đã bảo vệ lưu trữ |
| First Login Flow | Mặc định để quan sát behavior trong lab; production phải review chống account takeover |

**Hai thiết lập không được bỏ trống trong production:** `Identity Provider Entity ID` và **cơ chế xác minh chữ ký bằng signing key tin cậy**. Keycloak docs nêu rõ nếu Identity Provider Entity ID trống thì việc kiểm Issuer có thể không diễn ra.

**Want Assertions Signed** phải khớp cách IdP thực sự ký. Khi bật, hãy cấu hình SAML client phía IdP **sign assertions** và import đúng cert, rồi test. Nếu IdP chỉ ký Response theo contract khác, phải chọn profile/trust policy tương thích, **không tắt toàn bộ Validate Signature cho dễ chạy**.

### Bước 5.3. Lấy broker SP metadata và ACS

Sau khi lưu identity-provider alias, mở phần **Endpoints → SAML 2.0 Service Provider Metadata** của connection (theo UI phiên bản).

URL descriptor theo Keycloak:

~~~text
http://localhost:8080/realms/broker-oidc/broker/corp-saml-upstream/endpoint/descriptor
~~~

SAML ACS được metadata công bố tương ứng với:

~~~text
http://localhost:8080/realms/broker-oidc/broker/corp-saml-upstream/endpoint
~~~

**Đối chiếu descriptor trước khi đăng ký:** Trường `entityID` trong EntityDescriptor phải trùng SP EntityID broker khai; AssertionConsumerService Location/Binding phải trùng cấu hình IdP. SP metadata là đầu vào đăng ký với upstream IdP; **đây không phải OIDC Discovery hoặc Spring redirect URI**.

Trên host, bạn có thể xem metadata lab:

~~~bash
curl -fsS \
  http://localhost:8080/realms/broker-oidc/broker/corp-saml-upstream/endpoint/descriptor
~~~

Không lưu output metadata nội bộ lên paste công khai. Với production, chỉ tải metadata từ nguồn được allowlist và xác minh provenance/trust; HTTPS và key rotation phải theo chính sách.

## 6. Đăng ký broker SP thành SAML client của corp-saml

Quay lại realm **corp-saml → Clients → Create client**.

- Chọn **Client type: SAML**.
- **Import SP descriptor** từ URL hoặc file metadata của broker (tùy UI/import workflow).
- Kiểm **Client ID/EntityID** bằng `EntityDescriptor entityID`, không điền bằng OIDC client ID.
- Kiểm **Master SAML Processing URL** hoặc ACS POST URL theo metadata, chính là broker SAML ACS.
- Chọn đúng POST/Redirect bindings theo hai phía. Với SAML Response thường dùng HTTP-POST.
- Trong SAML signing settings, bật **sign assertions** (và/hoặc sign documents) theo policy mà broker mong đợi; với lab này mục tiêu là **signed Assertion** để Want Assertions Signed + Validate Signature ở broker có ý nghĩa.
- Kiểm signature algorithm modern, tránh các SHA-1 algorithms đã bị loại/không khuyến nghị.
- Không bật encryption nếu chưa cấu hình broker decryption credentials và chưa test, nhưng production có thể yêu cầu EncryptedAssertion.
- Chỉ allow broker SP đã đăng ký; IdP không được gửi Assertion đến arbitrary ACS từ request.

**Quan trọng khi debug:** Nếu broker báo `invalid signature`, thường do key/cert không khớp, IdP SAML client chưa ký đúng Assertion, hoặc profile chỉ ký Response. Đừng giải quyết bằng cách tắt signature checking. Đối chiếu signing cert và signed elements với **SAML metadata**.

### Bật IdP signing key cho broker

Trong broker connection SAML v2.0:

1. Truy cập metadata URL của **corp-saml**.
2. Lấy **IdP signing public certificate** đúng role `signing`.
3. Import cert hoặc bật metadata key refresh theo tính năng version và **trust policy**.
4. Verify SP stores trusted key của IdP; KeyInfo trong SAMLResponse chỉ là thông tin do sender đưa, **không tự là trust anchor**.
5. Nếu rotate IdP signing key, lên kế hoạch overlap/new-key approval; không tự tin mọi cert bất kỳ trong XML.

**Expected:** AuthnRequest từ broker tới corp-saml, signed Response/Assertion từ corp-saml quay lại **broker ACS**, không đi thẳng Spring.

## 7. Tạo downstream OIDC client cho Spring Boot

Ở realm **broker-oidc → Clients → Create client**:

| Cấu hình | Giá trị |
| --- | --- |
| Client type | OpenID Connect |
| Client ID | `spring-oidc-lab` |
| Client authentication | **ON** cho server-side confidential client |
| Standard Flow | **ON** (Authorization Code) |
| Direct Access Grants | OFF |
| Implicit Flow | OFF |
| Service Account Roles | OFF nếu không dùng M2M |
| Valid redirect URIs | `http://localhost:8081/login/oauth2/code/broker` |
| Root/Home URL | `http://localhost:8081` (nếu yêu cầu) |
| Web origins | Không cần `*` cho server-side MVC login |
| PKCE method | S256 khi Spring client gửi S256 code_challenge |
| Client secret | Lấy từ **Credentials**, chỉ cấp cho Spring host bằng environment/secret store |

Với ví dụ Java bên dưới, ta **chủ động thêm PKCE S256** qua DefaultOAuth2AuthorizationRequestResolver, nên có thể đặt Keycloak client yêu cầu S256. Không bật thêm một custom redirect URI mà chưa sửa đồng thời OIDC client registration và Spring callback filter.

### URLs cần kiểm tra

~~~text
Broker issuer:
http://localhost:8080/realms/broker-oidc

OIDC Discovery:
http://localhost:8080/realms/broker-oidc/.well-known/openid-configuration

Authorization endpoint thường là:
http://localhost:8080/realms/broker-oidc/protocol/openid-connect/auth

Token endpoint thường là:
http://localhost:8080/realms/broker-oidc/protocol/openid-connect/token

JWKS endpoint thường là:
http://localhost:8080/realms/broker-oidc/protocol/openid-connect/certs

Spring login initiation:
http://localhost:8081/oauth2/authorization/broker

Spring callback:
http://localhost:8081/login/oauth2/code/broker
~~~

**Luôn đọc Discovery JSON** thay vì giả định mọi Keycloak installation sử dụng cùng hostname/context path:

~~~bash
curl -fsS \
  http://localhost:8080/realms/broker-oidc/.well-known/openid-configuration
~~~

Có `jq`:

~~~bash
curl -fsS \
  http://localhost:8080/realms/broker-oidc/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'
~~~

**Bất biến:** Spring `issuer-uri` phải khớp chính xác `issuer` mà broker công bố và claim `iss` của ID Token. `aud` phải chứa **spring-oidc-lab**, không phải SAML SP EntityID.

### Broker đưa người dùng đến SAML IdP

Tại trang login của broker, user có thể bấm nút IdP alias `corp-saml-upstream`; hoặc admin có thể cấu hình **Default Identity Provider** trong authentication flow/broker settings. Một số Keycloak flows hỗ trợ `kc_idp_hint` để yêu cầu provider; đó là **routing hint** chứ không phải bằng chứng đã xác thực.

**Trong lab chọn thủ công nút SAML IdP** để quan sát từng hop. Không để browser query/header tự quyết định IdP trust/JWKS/issuer của Spring; issuer phải được cấu hình server-side.

## 8. Tạo Spring Boot 3.5 / Java 17 project chạy được

Dự án nhỏ dùng **Spring MVC** và **Spring Security OAuth2 Client**; không cần thêm dependency SAML2 Service Provider ở Spring vì broker đã xử lý SAML.

~~~text
saml-behind-broker-lab/
  pom.xml
  src/main/resources/application.yml
  src/main/java/com/example/brokerlab/
    BrokerLabApplication.java
    SecurityConfig.java
    DemoController.java
~~~

### 8.1. pom.xml

~~~xml
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
    <artifactId>saml-behind-broker-lab</artifactId>
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
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
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

**Version:** Chọn Spring Boot 3.5.7 tương thích Java 17 và Spring Security 6.x cho lab. Trong thực tế, dùng BOM patch **được tổ chức hỗ trợ và đã cập nhật bản vá bảo mật**, không lấy mã lab làm khuyến nghị cố định phiên bản mãi về sau.

### 8.2. application.yml

~~~yaml
server:
  port: 8081
  forward-headers-strategy: none
  servlet:
    session:
      cookie:
        http-only: true

spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: spring-oidc-lab
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          broker:
            issuer-uri: http://localhost:8080/realms/broker-oidc

logging:
  level:
    root: INFO
    org.springframework.security: WARN
    org.opensaml: WARN
~~~

- Client ID phải khớp Keycloak **broker-oidc OIDC client**, không phải SAML SP EntityID.
- Secret cung cấp bằng environment `OIDC_CLIENT_SECRET`, không lưu trong Git.
- `openid` khiến Spring dùng **OIDC authentication** và OidcUserService.
- `provider.broker.issuer-uri` dẫn tới **broker** (không phải SAML IdP).
- `redirect-uri` dùng template mặc định, callback thực ở port **8081**.
- `forward-headers-strategy: none` chỉ thích hợp cho host lab trực tiếp; production sau reverse proxy cần trusted forwarded-header handling và public HTTPS URL.
- Trong HTTP-only lab, cookie Secure có thể chưa được bật; production bắt buộc HTTPS và cookie Secure/SameSite/CSRF policy phù hợp.

### 8.3. Main class

**src/main/java/com/example/brokerlab/BrokerLabApplication.java**

~~~java
package com.example.brokerlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrokerLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrokerLabApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig: OIDC login và PKCE S256

**src/main/java/com/example/brokerlab/SecurityConfig.java**

~~~java
package com.example.brokerlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(oauth -> oauth
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

**Giải thích chính xác:**

1. `DefaultOAuth2AuthorizationRequestResolver` xử lý `/oauth2/authorization/broker`.
2. `withPkce()` thêm `code_challenge`/`code_challenge_method` và giữ verifier trong OAuth2AuthorizationRequest để dùng khi exchange code.
3. `oauth2Login()` cấu hình Authorization Code authentication; `state`/OIDC `nonce`/token validation do Spring Security flow xử lý theo implementation.
4. Không có `.saml2Login()` ở Spring; SAML ACS nằm trong **broker**.
5. Không bật `csrf.disable()` hoặc dùng permitAll cho `/api/**`.
6. `/api/admin` yêu cầu role ADMIN; lab không tự gán role này từ SAML/Keycloak group, nên đăng nhập thành công vẫn bị deny đối với admin.
7. Spring Security sẽ thiết lập HttpSession/SecurityContext sau login; mã này không tự tạo Authentication từ OIDC query `code`.

**Không có client secret hardcode.** Những thành phần này phụ thuộc Maven dependencies và broker đang chạy; chúng là các file của **một dự án tích hợp đầy đủ tối thiểu**, không phải Java thuần chạy với `javac` đơn lẻ.

### 8.5. DemoController: kiểm chứng OIDC principal mà không dump token

**src/main/java/com/example/brokerlab/DemoController.java**

~~~java
package com.example.brokerlab;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private static final String BROKER_ISSUER =
        "http://localhost:8080/realms/broker-oidc";

    @GetMapping("/")
    public String home() {
        return "Lab OIDC -> Broker -> SAML IdP";
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser oidcUser) {
        return Map.of(
            "authenticated", true,
            "oidcIssuerIsBroker",
                BROKER_ISSUER.equals(
                    oidcUser.getIdToken().getIssuer().toString()),
            "oidcSubjectPresent",
                !oidcUser.getSubject().isBlank(),
            "samlHandledAtBroker", true);
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("result", "admin-only");
    }
}
~~~

`/api/me` **không in raw ID Token, access token, SAMLResponse, email hoặc NameID**. `samlHandledAtBroker=true` chỉ là thông tin **kiến trúc lab**, không phải bằng chứng kỹ thuật về upstream SAML ở request cụ thể: để chứng minh upstream path phải xem event/trace **phía broker và IdP**. Khi ứng dụng có nhiều IdP ngoài SAML, không dùng field demo này để ra quyết định quyền.

**Lưu ý:** Spring Security đã validate ID Token trước khi tạo OidcUser; phép so sánh issuer trong controller để minh họa, không thay validation có sẵn. Không tự decode JWT từ request parameter rồi tạo principal.

### 8.6. Khởi chạy Spring app

Trên máy host, đặt secret lấy từ broker OIDC client **Credentials**; không ghi secret vào logs/history chia sẻ. Ví dụ trong shell test (tùy hệ điều hành):

~~~bash
export OIDC_CLIENT_SECRET="the-lab-client-secret-from-keycloak"
mvn spring-boot:run
~~~

Trên PowerShell:

~~~powershell
$env:OIDC_CLIENT_SECRET = "the-lab-client-secret-from-keycloak"
mvn spring-boot:run
~~~

**Dòng secret là nhãn hướng dẫn phải thay bằng giá trị lab**, không phải credential thật đã được phát trong bài. Nên dùng secret store hoặc file cấu hình môi trường không commit trong workflow nghiêm túc.

Mở bằng trình duyệt:

~~~text
http://localhost:8081/
http://localhost:8081/api/me
http://localhost:8081/oauth2/authorization/broker
~~~

Khi truy cập `/api/me` chưa đăng nhập, Spring Security chuyển browser qua OIDC login với broker. Tại Keycloak broker chọn `corp-saml-upstream`, hoàn tất login bằng `alice.lab` ở realm corp-saml, nếu cần qua first-broker-login screen. Sau callback, `/api/me` phải nhận kết quả tương tự:

~~~json
{
  "authenticated": true,
  "oidcIssuerIsBroker": true,
  "oidcSubjectPresent": true,
  "samlHandledAtBroker": true
}
~~~

**Đây là expected output khi toàn bộ lab được cấu hình đúng**, chưa phải bằng chứng live E2E đã được chạy trong tài liệu. Trạng thái thực cần xác nhận bằng browser/network và test logs đã sanitize.

Thử `/api/admin`: mặc dù OIDC login thành công, nếu không có ROLE_ADMIN do app cấp thì phải **403/deny theo policy**, không được auto-accept chỉ vì SAML user hoặc broker OIDC client có group/role.

## 9. Kiểm tra luồng qua từng hop

### Hop A – Spring app khởi tạo OIDC

Khi chưa có HttpSession authenticated:

~~~text
GET /api/me
  -> 302 /oauth2/authorization/broker
  -> 302 http://localhost:8080/realms/broker-oidc/
          protocol/openid-connect/auth?client_id=...
                                   &response_type=code
                                   &scope=openid...
                                   &state=...
                                   &code_challenge=...
                                   &code_challenge_method=S256
~~~

**Không log nguyên URL có `state`, `code`, cookie hoặc token.** Chỉ kiểm trong browser devtools của môi trường test, sau đó xóa HAR nếu chứa credential.

### Hop B – Broker chuyển sang SAML IdP

Khi chọn `corp-saml-upstream`:

~~~text
Browser -> broker SAML IdP connection
Broker  -> SAML AuthnRequest gửi tới IdP SSO endpoint
Browser -> corp-saml login
IdP     -> signed SAMLResponse (HTTP POST)
Browser -> broker ACS /broker/corp-saml-upstream/endpoint
~~~

Broker kiểm:

- SAML IdP EntityID/Issuer đúng như cấu hình.
- XMLDSig signature/digest và IdP verification certificate trusted.
- Audience = broker SP EntityID, Destination/Recipient = broker SAML ACS.
- Time Conditions, SubjectConfirmation, InResponseTo và unique/replay IDs theo profile.
- XML parser safety (không XXE, không dùng unsigned sibling Assertion).
- Stable NameID/selected principal attribute trước khi map broker account.

### Hop C – Broker phát OIDC cho Spring

Khi upstream SAML verified, Keycloak áp first/post-broker-login flow, tạo hoặc link broker user, rồi tiếp tục **OIDC Authorization Code**.

Spring nhận callback:

~~~text
GET http://localhost:8081/login/oauth2/code/broker
     ?code=<one-time-opaque-code>&state=<bound-state>

Spring -> broker token endpoint (backchannel, client_secret_basic)
Broker -> ID Token/Access Token response
Spring -> validate broker ID Token, create OidcUser
Spring -> save SecurityContext/HttpSession
Browser -> /api/me returns authenticated JSON
~~~

**ID Token chính phải có:**

| Claim | Expected | Kiểm soát |
| --- | --- | --- |
| `iss` | `http://localhost:8080/realms/broker-oidc` | Spring issuer validation |
| `sub` | Broker-local stable subject | Không nhất thiết bằng SAML NameID |
| `aud` | Có `spring-oidc-lab` | Đúng OIDC client |
| `exp`, `iat` | Thời gian hợp lệ | Token lifetime |
| `nonce` | Phù hợp request khi sử dụng | OIDC login correlation |
| `azp` nếu áp dụng | Client đã được phép | Kiểm theo OIDC semantics |
| `email`, `name` | Optional | Không dùng làm global account ID |
| `groups`/`roles` | Optional broker mapping | Không auto-mint quyền ứng dụng |

**Không gửi ID Token tới backend API như access token** chỉ vì nó là JWT. Nếu ứng dụng có resource server endpoints yêu cầu Bearer, dùng access token đúng `aud/scope/issuer` và xác minh riêng.

## 10. First broker login, liên kết tài khoản và phân quyền

Khi SAML IdP trả NameID, broker cần ánh xạ người dùng upstream vào một tài khoản trong broker realm. **Default first broker login flow** có thể tự tạo tài khoản nếu chưa có. Với lab fresh realms, đó có thể là điều mong đợi để thấy luồng hoạt động.

**Production không thể coi auto-link theo email là an toàn mặc định.** Cần xác định:

1. SAML NameID thuộc format nào: persistent hay transient? Nếu transient, không dùng làm persistent lookup key.
2. Broker key để tìm external user là gì? Phải là stable upstream `(source IdP alias, verified issuer, immutable subject)`.
3. Mối quan hệ broker user ↔ upstream user có được chứng minh/approved không? Nếu email trùng mà identities khác issuer, cần reauthentication/approval chứ không auto-merge.
4. Spring app có local business user ID và tenant không? Nên map `(broker iss, broker sub, tenant)` → `local user_id` đã phê duyệt.
5. Những quyền nào đến từ local DB? Không tự map `groups=admins` hoặc SAML Attribute là ROLE_ADMIN nếu không qua allowlist/policy.
6. Khi disable user ở IdP hoặc local DB, session broker/app có bị revoke ngay không hay chỉ theo TTL?
7. Thay đổi alias IdP, SAML NameID format hoặc OIDC client/sector có thể đổi `sub`/link; kiểm ảnh hưởng trước deploy.

### Ví dụ bảng mapping (minh họa)

~~~sql
CREATE TABLE local_user (
  id BIGINT PRIMARY KEY,
  tenant_id VARCHAR(80) NOT NULL,
  enabled BOOLEAN NOT NULL
);

CREATE TABLE external_identity_link (
  id BIGINT PRIMARY KEY,
  local_user_id BIGINT NOT NULL REFERENCES local_user(id),
  issuer VARCHAR(500) NOT NULL,
  subject VARCHAR(500) NOT NULL,
  tenant_id VARCHAR(80) NOT NULL,
  approved BOOLEAN NOT NULL,
  UNIQUE (issuer, subject, tenant_id)
);
~~~

**Trong ứng dụng thật**, lookup chỉ sau khi Spring đã xác minh OIDC ID Token. Bảo đảm ràng buộc tenant nhất quán, transactions, unique constraints, account linking audit/approval và không auto-create admin khi mapping trống.

Một `email_verified=true` do broker phát có thể chỉ phản ánh policy trust email upstream, **không** chứng minh cùng một người dùng giữa các issuers. Kiểm `Trust Email` và first login flow của Keycloak trước migration.

### Role mapping và local authorization

Với lab, `oauth2Login` tạo Authentication OIDC; app chưa có bước map DB roles nên `/api/admin` phải bị deny. Để cấp quyền thật:

- Trên `OidcUserService` hoặc custom authentication success handling, lấy `oidcUser.getIdToken().getIssuer()` và `oidcUser.getSubject()` **đã validated**.
- Lookup user link/tenant, enabled/locked và allowed roles trong database.
- Chuyển kết quả policy thành GrantedAuthorities, có deny-by-default và nguồn dữ liệu được phê duyệt.
- Không lấy username/email không được xác minh hoặc header X-Role của browser làm quyền.
- Không tạo local user ID mới cho mỗi login khi SAML NameID/broker sub thay đổi.
- Nếu cần MFA, kiểm `acr`/`amr`/`auth_time` do broker map đúng semantics, không tự suy rằng SAML IdP đã thực hiện step-up.

**OIDC `sub` của broker không được phép coi là SAML NameID.** Broker là issuer mới có chính sách subject riêng, có thể có nhiều linked external identities trên cùng broker account.

## 11. Java 17 độc lập: mô phỏng hai lớp trust và identity linking

Để phân biệt “SAML đã được broker kiểm” với “OIDC đã được Spring kiểm”, ta dựng mô hình **không có network hay XML/JWT**. Hai booleans verify đại diện cho kết quả thực của các thư viện; **đây không phải crypto validator**.

**Tệp: BrokerTrustChainDemo.java**

~~~java
import java.util.Map;

public final class BrokerTrustChainDemo {

    private static final String SAML_ISSUER =
        "http://localhost:8080/realms/corp-saml";
    private static final String BROKER_ISSUER =
        "http://localhost:8080/realms/broker-oidc";
    private static final String OIDC_CLIENT = "spring-oidc-lab";

    record SamlEvidence(
        String issuer, boolean verifiedSignature,
        boolean validRecipient, String upstreamSubject) { }

    record OidcEvidence(
        String issuer, String audience, boolean verifiedSignature,
        boolean validNonce, String brokerSubject) { }

    private static final Map<String, String> APPROVED =
        Map.of("broker-sub-42", "LOCAL-USER-42");

    static String authenticate(SamlEvidence upstream,
            OidcEvidence downstream) {

        if (!SAML_ISSUER.equals(upstream.issuer())
                || !upstream.verifiedSignature()
                || !upstream.validRecipient()
                || !"saml-user-42".equals(upstream.upstreamSubject())) {
            return "DENY_UPSTREAM_SAML";
        }

        if (!BROKER_ISSUER.equals(downstream.issuer())
                || !OIDC_CLIENT.equals(downstream.audience())
                || !downstream.verifiedSignature()
                || !downstream.validNonce()) {
            return "DENY_DOWNSTREAM_OIDC";
        }

        return APPROVED.getOrDefault(downstream.brokerSubject(),
            "DENY_UNLINKED_USER");
    }

    public static void main(String[] args) {

        SamlEvidence validSaml = new SamlEvidence(
            SAML_ISSUER, true, true, "saml-user-42");
        OidcEvidence validOidc = new OidcEvidence(
            BROKER_ISSUER, OIDC_CLIENT, true,
            true, "broker-sub-42");

        System.out.println("baseline=" +
            authenticate(validSaml, validOidc));

        System.out.println("badSamlSignature=" +
            authenticate(new SamlEvidence(
                SAML_ISSUER, false, true, "saml-user-42"),
                validOidc));

        System.out.println("wrongSamlIssuer=" +
            authenticate(new SamlEvidence(
                "https://other-idp.invalid", true, true, "saml-user-42"),
                validOidc));

        System.out.println("wrongBrokerIssuer=" +
            authenticate(validSaml, new OidcEvidence(
                "https://other-broker.invalid", OIDC_CLIENT,
                true, true, "broker-sub-42")));

        System.out.println("wrongOidcAudience=" +
            authenticate(validSaml, new OidcEvidence(
                BROKER_ISSUER, "other-client",
                true, true, "broker-sub-42")));

        System.out.println("badNonce=" +
            authenticate(validSaml, new OidcEvidence(
                BROKER_ISSUER, OIDC_CLIENT,
                true, false, "broker-sub-42")));

        System.out.println("unknownUser=" +
            authenticate(validSaml, new OidcEvidence(
                BROKER_ISSUER, OIDC_CLIENT,
                true, true, "unlinked-broker-sub")));
    }
}
~~~

Chạy bằng JDK 17 thuần:

~~~bash
javac BrokerTrustChainDemo.java
java BrokerTrustChainDemo
~~~

**Stdout xác định theo code:**

~~~text
baseline=LOCAL-USER-42
badSamlSignature=DENY_UPSTREAM_SAML
wrongSamlIssuer=DENY_UPSTREAM_SAML
wrongBrokerIssuer=DENY_DOWNSTREAM_OIDC
wrongOidcAudience=DENY_DOWNSTREAM_OIDC
badNonce=DENY_DOWNSTREAM_OIDC
unknownUser=DENY_UNLINKED_USER
~~~

**Giới hạn thiết yếu:** `verifiedSignature` và `validNonce` **chỉ là mock evidence**; trong ứng dụng thật chúng phải là kết quả từ **SAML validator của broker** và **OIDC authentication pipeline của Spring Security**, tuyệt đối không phải query/header/body boolean do client gửi. Chương trình không kiểm XMLDSig, JWKS/JWT signature, TLS, audience/recipient thời gian hoặc replay; hãy chạy E2E tests riêng trên cả IdP, broker và app.

## 12. Bộ kiểm thử tích hợp từ browser đến IdP và Spring

### Positive control bắt buộc

1. Đăng xuất khỏi các sessions cũ, dùng browser profile sạch.
2. Mở `/api/me` trong Spring app; chưa login phải redirect tới broker.
3. Chọn `corp-saml-upstream`; browser đến corp-saml.
4. Login `alice.lab`; IdP ký Assertion/Response theo contract và POST về **broker ACS**.
5. Broker xác minh SAML; first broker login liên kết/tạo một user lab.
6. Broker phát authorization code về **Spring OIDC callback**.
7. Spring đổi code và validate ID Token broker.
8. `/api/me` trả authenticated=true, oidcIssuerIsBroker=true, oidcSubjectPresent=true.
9. `/api/admin` vẫn bị deny vì không có ROLE_ADMIN từ local policy.
10. Quan sát event/trace **đã sanitize** của broker cho biết source `corp-saml-upstream`; không dùng JSON field `samlHandledAtBroker=true` của controller làm bằng chứng.

### Negative test matrix

| # | Test | Lớp phải chặn | Kỳ vọng |
| --- | --- | --- | --- |
| 1 | Không đăng nhập, gọi /api/me | Spring auth entry point | Redirect/login, không có private data |
| 2 | IdP SAML ký đúng | Broker SAML validator | Positive SAML validation |
| 3 | Response có chữ ký sai | Broker | Reject trước khi tạo broker identity |
| 4 | SAML issuer sai nhưng chữ ký hợp lệ | Broker | Reject issuer |
| 5 | SAML signing key B chưa trusted | Broker | Reject key B, kể cả có KeyInfo B |
| 6 | SAML Audience khác broker SP EntityID | Broker | Reject |
| 7 | SAML Destination/Recipient khác broker ACS | Broker | Reject |
| 8 | Assertion hết hạn/NotBefore tương lai | Broker | Reject |
| 9 | InResponseTo không khớp request | Broker | Reject theo SP-initiated contract |
| 10 | Replay Response ID đã dùng | Broker | Reject replay |
| 11 | XML Signature Wrapping/duplicate IDs | Broker | Không dùng unsigned Assertion |
| 12 | Metadata SAML signing key đổi không được phê duyệt | Broker | Không tự trust key mới |
| 13 | Broker user link chưa được phê duyệt | Broker/app policy | Review hoặc deny |
| 14 | Email trùng với account khác | Broker first login flow | Không auto-link mù |
| 15 | SAML NameID transient thay đổi mỗi login | Broker link policy | Không tạo account takeover/duplicate trái policy |
| 16 | Broker OP ID Token signing key B chưa trusted | Spring OIDC | Reject invalid/untrusted signature |
| 17 | ID Token issuer khác broker | Spring OIDC | Reject |
| 18 | ID Token audience khác spring-oidc-lab | Spring OIDC | Reject |
| 19 | ID Token expired/nbf invalid | Spring OIDC | Reject |
| 20 | OIDC nonce/state mismatch | Spring OIDC | Reject callback, no authentication |
| 21 | Authorization code replay | Broker token endpoint | Reject code đã dùng |
| 22 | PKCE verifier sai | Broker token endpoint | Reject |
| 23 | Client secret sai | Broker token endpoint | Reject |
| 24 | Redirect URI chưa đăng ký | Broker authorization endpoint | Reject |
| 25 | X-Forwarded-Host giả làm đổi redirect | Trusted edge/Spring | Không open redirect/callback poisoning |
| 26 | Gửi SAMLResponse vào Spring OIDC callback | Spring/OIDC | Không tự parse SAML |
| 27 | Gửi OIDC code vào SAML broker ACS | Broker/SAML | Không nhận như SAMLResponse |
| 28 | Authenticated OIDC user gọi /api/admin | Spring authorization | Deny nếu không có role app |
| 29 | Local user disabled | Local policy | Deny dù broker ID Token valid |
| 30 | Cross-tenant object ID | App resource policy | Deny |
| 31 | IdP SAML không đáp ứng AuthnContext/MFA | Broker/step-up | Reject/reauth theo chính sách |
| 32 | Logout chỉ ở Spring app | Session layer | Local session kết thúc, không hứa upstream SLO |
| 33 | Broker logout nhưng IdP session còn | Broker/IdP | Re-login UX theo contract |
| 34 | Broker/IdP outage | Spring/broker | Fail closed, không chấp nhận fake headers |
| 35 | Thay SAML IdP signing cert theo rotation | Broker trust | Overlap theo policy, không fail-open |
| 36 | SAMLResponse/Authorization Code/ID Token trong logs | Logging pipeline | Không lộ secrets/PII |
| 37 | Replay session cũ sau account disabled | App/session policy | Deny theo revocation SLA |
| 38 | Browser third-party cookies blocked | Session/SSO UX | Không login loop; debug cookie policy |
| 39 | Different OIDC client/sector/sub | Broker/app linking | Không map dựa email tự động |
| 40 | Broker identity đổi nhưng local user_id vẫn đúng | Local DB mapping | Giữ role/ownership khi approved |

**Chấm QA đúng:** “HTTP 302/403” một mình không chứng minh signature hoặc issuer được kiểm. Tạo **valid positive baseline** trước; với wrong SAML issuer, tài liệu phải được **ký lại bằng trusted key** để cô lập issuer validation. Với untrusted key, tài liệu phải ký hợp lệ bằng key khác nhưng trustset broker vẫn chỉ chứa key được duyệt. Với OIDC tương tự, expired/wrong audience tests không được tình cờ fail do invalid state.

### E2E và MockMvc không tương đương

- **MockMvc** có thể giả OidcUser để kiểm business authorization trong app, nhưng không đi qua Keycloak/SAML IdP, không kiểm SAML signature, OIDC JWKS hay browser cookies thực.
- **Browser-based E2E** với test IdP, broker và HTTPS-like environment mới kiểm end-to-end protocol routing, form POST, callback/cookie/session.
- **Network tests** riêng cần kiểm TLS, DNS, proxy Host/Proto, egress/IdP metadata URL and callback whitelist.
- **Môi trường lab** có thể dùng HTTP localhost, nhưng production buộc HTTPS, trusted proxies, rotation/availability controls.

## 13. Session và logout qua ba tầng

Sau login có thể tồn tại:

~~~text
Session A: Spring HttpSession/SecurityContext
Session B: Keycloak broker OP browser session
Session C: corp-saml IdP browser session
~~~

`session.invalidate()` ở Spring chỉ đảm bảo kết thúc **A**. Broker RP-initiated logout có thể kết thúc **B** nếu cấu hình đúng, nhưng **C** không tự bị xóa trong mọi tình huống. Broker có thể hỗ trợ SAML Single Logout upstream theo policy, nhưng không được hứa SLO 100% nếu IdP không triển khai/không tương thích bindings.

**Kiểm thử:**

1. Login, thấy /api/me authenticated.
2. POST logout theo Spring Security CSRF policy → app session A bị invalidate.
3. Login lại: broker B hoặc IdP C còn active có thể làm SSO xảy ra nhanh không cần nhập password.
4. Nếu muốn logout broker, dùng **OidcClientInitiatedLogoutSuccessHandler** cùng ClientRegistrationRepository và OP end_session_endpoint của broker, cấu hình trusted post_logout_redirect_uri.
5. Kiểm logout propagation/SCIM session revocation riêng nếu production yêu cầu “sign out everywhere”.
6. Thiết lập session idle/absolute timeout, token TTL, disabled-user revocation và step-up MFA theo chính sách.
7. Không gửi session cookie, logout token hoặc ID Token hint vào logs.

**OIDC ID Token khác access token:** ID Token phục vụ authentication tại Spring client; API có bearer flow cần resource server và token audience/scope đúng. Không dùng OIDC login thành authorization cho mọi object.

## 14. Gỡ lỗi theo nơi phát sinh

| Triệu chứng | Điểm kiểm và nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Spring startup fail khi load issuer | OIDC Discovery URL không truy cập được, issuer mismatch | Kiểm `.well-known/openid-configuration`, DNS/port |
| Browser bị loop về broker login | Sai redirect URI, HttpSession, cookie/domain/SameSite | So sánh registered URI/callback, state/session |
| Broker không có nút corp-saml-upstream | IdP chưa Enabled/Hide on Login Page/default flow | Kiểm identity provider alias/config |
| Broker báo `invalid requester` | SP EntityID/ACS sai ở corp-saml client | Import descriptor từ broker, so khớp entityID |
| IdP chưa ký Assertion | Want Assertions Signed và Sign Assertions không khớp | Cấu hình ký đúng node, kiểm cert |
| Broker từ chối SAML signature | Sai IdP cert/key rotation/algorithm/canonicalization | Import trusted signing cert, test signed fixture |
| Broker từ chối Issuer | Identity Provider Entity ID sai/trống | Set đúng entityID từ metadata, không bỏ kiểm |
| Broker báo Audience/Recipient mismatch | IdP SAML client ACS khác descriptor | Đối chiếu SP descriptor/binding/URL |
| Broker không link user | NameID transient, attribute mismatch, first login flow | Stable ID, approved linking |
| “Account already exists” sau SAML login | Email/username collision trong broker | Explicit proof/link approval, không bật Trust Email tùy tiện |
| Broker OIDC code callback sai | Client redirect URI/registrationId sai | Exact /login/oauth2/code/broker |
| Token exchange invalid_client | Client secret/client authentication method khác | Đồng bộ secret/basic/credentials |
| PKCE error | Client yêu cầu S256 nhưng request thiếu challenge/verifier | Kiểm withPkce và S256 setting |
| Spring ID Token issuer invalid | Chỉ vào corp-saml IdP thay vì broker | issuer-uri phải là **broker** |
| Spring audience invalid | OIDC client ID không đúng | `spring-oidc-lab` trong aud |
| Spring `/api/me` 200, `/api/admin` 403 | OIDC login thành công nhưng chưa có business role | **Đúng lab**, kiểm local policy |
| Đăng xuất rồi vẫn SSO | Broker/IdP session chưa bị logout | Thiết kế layered logout |
| Docker localhost không kết nối | App/container nhìn localhost khác nhau | Đúng host/DNS + canonical issuer |
| Logs chứa XML/token | DEBUG/custom request logger dump credentials | Audit redaction, disable raw logs |

### Quan sát không lộ secrets

Nên log:

~~~text
event=SSO_AUTH_STARTED  client=broker        route=/api/me
event=BROKER_SAML_ACCEPTED provider=corp-saml-upstream
event=OIDC_LOGIN_SUCCESS issuerAlias=broker-oidc
event=AUTHZ_DENIED       route=/api/admin   reason=ROLE_MISSING
~~~

Đây là **ví dụ event format để tự instrument**, không phải output mặc định của Keycloak hoặc Spring. Không log raw SAMLResponse, NameID, KeyInfo, authorization code, ID Token, client secret, Cookie/JSESSIONID hoặc RelayState.

Khi cần deep debug, dùng synthetic users và logger hẹp trên lab, có thời gian tắt; không bật OpenSAML TRACE/kho XML dumps cho production.

## 15. Production hardening so với lab

| Hạng mục | Trong lab | Khi triển khai thật |
| --- | --- | --- |
| Transport | HTTP localhost | HTTPS/TLS, trusted proxy chain, origin allowlist |
| Keycloak | `start-dev`, một instance/two realms | HA, persistent DB, backup/restore, hardening |
| Credentials | lab admin, client secret env | Secrets manager/rotation, admin MFA |
| SAML certificates | IdP test signer | Trusted metadata onboarding, key rotation, cert expiry |
| SAML XML processing | Broker built-in | Patch OpenSAML/Keycloak, XXE/signature wrapping tests |
| OIDC client | Confidential app, Code+PKCE | Strict redirect URIs, issuer/JWKS/aud/nonce/token TTL |
| Browser sessions | Local cookies | Secure/HttpOnly/SameSite/CSRF, session fixation protection |
| Identity link | First broker login creates lab user | Preapproved issuer+subject mapping, account takeover prevention |
| Role policy | Admin denied mặc định | DB/tenant/object authorization, least privilege |
| Audit | Manual browser tests | Central safe events, anomaly detection, retention |
| Logout | Local proof of session | RP-Initiated/Front/Back-channel/Upstream SLO contract |
| Resilience | One local Keycloak server | DR, availability, fail closed, circuit breaker |
| Monitoring | Browser, stdout | Trace IDs, metrics theo hop, no raw credentials |
| API tokens | Không dùng trong demo | Resource server access tokens with correct issuer/audience |

**Không được hạ mức trust để “cho demo chạy”:** nếu signing check fail, sửa metadata/cert/client settings thay vì tắt Validate Signature hoặc chấp nhận SAMLResponse unsigned. Nếu ID Token không validate, không chuyển sang đọc JWT claims bằng Base64 rồi tự xây Authentication.

## 16. Checklist hoàn thành bài thực hành

- [ ] Keycloak 26.x lab chạy trên localhost và Admin Console truy cập được.
- [ ] Có realm corp-saml và test user chỉ dùng cho lab.
- [ ] Có realm broker-oidc với SAML IdP alias corp-saml-upstream.
- [ ] Đã lấy **broker SP descriptor** và đăng ký thành SAML client trong corp-saml.
- [ ] IdP SAML EntityID/SSO URL và broker SP EntityID/ACS trùng metadata thực.
- [ ] Broker có **Identity Provider Entity ID không trống**, Validate Signature và trusted IdP signing certificate.
- [ ] IdP SAML client ký Assertion đúng profile (hoặc có signing policy được phê duyệt, không unsigned).
- [ ] Broker First Broker Login không auto-link existing user theo email không được kiểm chứng.
- [ ] OIDC client spring-oidc-lab ở broker cho phép Authorization Code, confidential auth, registered redirect URI.
- [ ] Spring `issuer-uri` trỏ **broker-oidc**, không trỏ corp-saml.
- [ ] Spring OIDC client ID/secret/redirect URI khớp broker registration, PKCE S256 hoạt động.
- [ ] Spring Security có `oauth2Login`, không tự parse SAMLResponse hoặc bỏ state/nonce validation.
- [ ] Browser đi qua SAML IdP rồi trở về broker ACS, sau đó về Spring OIDC callback.
- [ ] `/api/me` xác nhận OIDC issuer là broker và subject có mặt.
- [ ] `/api/admin` không được cấp quyền chỉ vì OIDC login thành công.
- [ ] Local account linking bằng approved broker `(iss, sub)` và tenant được hoạch định.
- [ ] Negative tests SAML signature/issuer/audience/time và OIDC issuer/audience/state/PKCE được thực hiện.
- [ ] Đã phân biệt MockMvc authorization tests với real browser E2E federation tests.
- [ ] Logout tại app/broker/IdP có contract cụ thể và không hứa đồng bộ ngoài khả năng hỗ trợ.
- [ ] Logs/proxy/APM không lưu raw tokens, SAMLResponse, NameID, cookies hoặc client secret.
- [ ] Không mang `start-dev`, localhost HTTP, lab admin credentials hoặc unreviewed first-login policy lên production.
- [ ] Khi kết thúc, dừng container và xoá lab secrets/files theo quy trình, không ảnh hưởng hệ thống thật.

**Kết luận:** Trong kiến trúc này, **SAML kết thúc ở broker**, còn Spring **chỉ nói OIDC với broker**. Thành công được chứng minh không phải bằng việc trình duyệt hiển thị trang đã login đơn thuần, mà bằng một chuỗi kiểm tra: upstream SAML signature/issuer/audience hợp lệ → broker tạo/nhận diện user đã link đúng → OIDC Authorization Code/PKCE và ID Token hợp lệ với broker issuer/client audience → Spring tạo Authentication → application authorization vẫn chặn quyền không được cấp. Hai giao thức, hai cặp trust và ba tầng session là những điểm phải kiểm thử độc lập.

## 17. Tài liệu tham khảo chính thức

- [Keycloak Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): container, KC_BOOTSTRAP_ADMIN_USERNAME/PASSWORD và start-dev.
- [Keycloak Server Administration – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/): SAML Identity Provider, broker alias, first login flow, token mapping và bảo mật account linking.
- [Keycloak SAML SP Metadata/Descriptor](https://www.keycloak.org/docs/latest/server_admin/#_identity_broker_saml): browser SAML broker endpoint và SAML SP descriptor.
- [Spring Security – OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): client registration, issuer-uri, redirect URI và OAuth2 Login.
- [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): authorization endpoint customization, OidcUserService, role mapping.
- [Spring Security – OAuth2AuthorizationRequestCustomizers.withPkce](https://docs.spring.io/spring-security/site/docs/6.4.12/api/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html): PKCE S256 customizer.
- [Spring Boot – OAuth2 Client Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): ClientRegistration properties và security auto-configuration.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token issuer, subject, audience, nonce.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, authorization/token/JWKS endpoint metadata.
- [OASIS SAML 2.0 Specifications](https://docs.oasis-open.org/security/saml/v2.0/): AuthnRequest, Response/Assertion, XMLDSig, NameID, bindings.
- [RFC 7636 – Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): code_challenge/code_verifier và S256.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect, PKCE, token/security considerations.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature, trust, audience, replay và wrapping.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): issuer/JWKS, state, redirect and code flow safety.