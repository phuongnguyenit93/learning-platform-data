# Chuyển từ Spring Security SAML Extension cũ sang hỗ trợ SAML2 hiện hành

## 1. Mục tiêu, phạm vi và khác biệt kiến trúc

Nhiều ứng dụng Java doanh nghiệp từng dùng **Spring Security SAML Extension 1.x** để làm **SAML 2.0 Service Provider (SP)**. Các dự án này thường có dependency `spring-security-saml2-core`, cấu hình XML `securityContext.xml`, nhiều bộ lọc thủ công (`SAMLEntryPoint`, `SAMLProcessingFilter`, `MetadataGeneratorFilter`, `SAMLLogoutFilter`), một `KeyManager` giữ JKS, `MetadataManager` quản lý IdP, `ExtendedMetadata` và code ánh xạ `SAMLAuthenticationProvider`/`SAMLUserDetailsService`.

Spring Security hiện hành tích hợp chức năng **SAML2 Login trực tiếp vào Spring Security Servlet** qua module `spring-security-saml2-service-provider`, cấu hình `SecurityFilterChain`, `saml2Login()`, `RelyingPartyRegistration`, `RelyingPartyRegistrationRepository` và provider dựa trên OpenSAML. Các khả năng xuất bản metadata và SAML Single Logout (SLO) được cấu hình qua `saml2Metadata()` và `saml2Logout()` khi phiên bản/tình huống hỗ trợ.

**Mục đích nâng cấp không phải thay tên class rồi biên dịch:** phải **chuyển cả mô hình trust**, metadata, Endpoint URL, khóa ký/giải mã, request correlation, session, identity/role mapping, SLO và các kiểm tra an ninh. Một thay đổi sai `EntityID` hoặc Assertion Consumer Service (ACS) có thể khiến toàn bộ đối tác IdP từ chối login ngay cả khi Java compile thành công.

Bài thuộc nhóm **Chuyển đổi và nâng cấp** trong module **Spring Security - federation**. Nội dung tập trung vào **migrating a SAML2 Service Provider (SP)**; **không** hướng dẫn chuyển một SAML Identity Provider viết riêng bằng extension thành IdP mới trong Spring Security, vì khả năng RP/SP của module hiện hành không tương đương một IdP server đầy đủ.

**Kết quả mong đợi:**
1. Nhận diện đầy đủ thành phần cũ và contract thực với IdP.
2. Hiểu ánh xạ chức năng sang Spring Security SAML2 mới và nhận biết **không có tương đương 1:1**.
3. Thiết lập một SP mới dùng Spring Security/Boot version được hỗ trợ, nhập IdP metadata và khóa đúng vai trò.
4. Bảo tồn hoặc chuyển đổi có kiểm soát `EntityID`, ACS, SLO URLs, NameID, attributes, roles và sessions.
5. Kiểm thử security negative cases, interoperability, multi-IdP, reverse proxy và rollover.
6. Phát hành an toàn với canary, rollout, rollback và audit thay đổi trust.

**Giới hạn phiên bản:** tài liệu Spring Security **6.x** có nhiều mẫu `OpenSaml4AuthenticationProvider`; tài liệu dòng **7.x** hiện hành dùng `OpenSaml5AuthenticationProvider` và thay đổi API principal/assertion. Cần dựa vào **phiên bản Spring Security, Spring Boot, OpenSAML được resolve thật**; không trộn snippets của các dòng release.

## 2. Extension cũ khác hỗ trợ mới ở đâu?

| Khía cạnh | Spring Security SAML Extension 1.x | Spring Security SAML2 hiện hành | Việc phải làm khi chuyển |
| --- | --- | --- | --- |
| Dependency | `spring-security-saml2-core` và OpenSAML của thời extension | `spring-security-saml2-service-provider` | Thay dependency, quản lý BOM/transitives |
| Cách bật SSO | Nhiều filter và entry point thêm thủ công | `http.saml2Login(...)` trong `SecurityFilterChain` | Dọn filter chain cũ, tránh 2 stacks xử lý cùng callback |
| Start login | `SAMLEntryPoint`, `/saml/login` thường gặp | `Saml2WebSsoAuthenticationRequestFilter`; mặc định `/saml2/authenticate/{registrationId}` | Chuyển entry link và IdP picker |
| ACS | `SAMLProcessingFilter`, thường `/saml/SSO` | `Saml2WebSsoAuthenticationFilter`; mặc định `/login/saml2/sso/{registrationId}` | Đồng bộ IdP ACS, proxy và metadata |
| SP metadata | `MetadataGeneratorFilter`, `MetadataDisplayFilter`, `MetadataGenerator` | `saml2Metadata()` từ `RelyingPartyRegistration` | So output XML/EntityID/cert/ACS trước khi đổi IdP |
| IdP metadata | `MetadataManager`, `ExtendedMetadataDelegate`, file/HTTP providers | `RelyingPartyRegistrations.fromMetadataLocation`/repository | Tái tạo trust policy, refresh, expiry và signing keys |
| Extended properties | `ExtendedMetadata`, các bean thủ công | Properties/builders, protocol-specific customization | Đối chiếu từng behavior, không auto-copy XML |
| Keystore | `KeyManager`, JKS/JCEKS aliases | `Saml2X509Credential` sign/verify/decrypt | Di chuyển private key an toàn, bảo tồn key use |
| Authentication provider | `SAMLAuthenticationProvider` + `WebSSOProfileConsumer` | OpenSAML provider và converters | Giữ chữ ký/audience/recipient/timestamp/replay checks |
| User mapping | `SAMLUserDetailsService`, `SAMLCredential`, principal tùy biến | Verified authentication + attributes/authorities converter hoặc local service | Thiết kế subject/tenant/role contract |
| Logout | `SAMLLogoutFilter`, `SAMLLogoutProcessingFilter` | `saml2Logout(...)`, request/response filters | Kiểm lại RP/AP-initiated SLO và endpoint |
| Multi-IdP | Metadata aliases/discovery và context provider | Nhiều `RelyingPartyRegistration`, custom resolver/picker | Có mapping `registrationId`, issuer và tenant rõ |
| Proxy/load balancer | `SAMLContextProviderLB` và server name overrides | `{baseUrl}`, forwarded headers/base URL, metadata config | Kiểm host/scheme/path ngoài Internet đúng |
| Binding/profiles | Extension 1.x có thể hỗ trợ nhiều profile/binding đặc biệt | Modern module tập trung SAML Web Browser SSO/SLO | Lập **feature-gap list**, test các binding ngoài mặc định |

**Không có lệnh tự động chính thức kiểu “convert XML config sang RelyingPartyRegistration” để bảo đảm tương đương hoàn toàn.** Spring có tài liệu migration mô tả các **patterns**, không phải bảng tìm–thay tất cả classes.

## 3. Phân biệt extension 1.x, Spring Security 5/6 và 7

| Dòng dự án | Ghi chú |
| --- | --- |
| **Spring Security SAML Extension 1.x** | Dự án extension lịch sử; thường XML beans, `org.springframework.security.saml.*`, `OpenSAML 2.x` trong các bản cũ |
| **Spring Security 5.x** | SAML SP support đã được đưa vào Spring Security core ecosystem, ví dụ `saml2Login` và `RelyingPartyRegistration` |
| **Spring Security 6.x** | Dùng API hiện đại Servlet `SecurityFilterChain`, Jakarta EE namespaces; một số hướng dẫn dùng `OpenSaml4AuthenticationProvider` |
| **Spring Security 7.x** | Documentation dùng `OpenSaml5AuthenticationProvider`, `Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor`; một số APIs cũ bị deprecate |
| **Spring Boot 3/4** | Quản lý dependency versions và auto-config SAML2 theo dòng Boot, nên lấy BOM do Boot quản lý thay vì tự ghép thư viện |

**Cần kiểm cụ thể:** `java -version`, `mvn dependency:tree`/`gradle dependencies`, Spring Boot plugin version, Spring Security BOM, OpenSAML versions và Java Servlet imports. Chuyển từ Boot 2.x lên Boot 3/4 còn liên quan **`javax.servlet.*` → `jakarta.servlet.*`**, không phải chỉ SAML. Tránh import `javax` từ extension cũ vào Spring 6/7.

Không phải ứng dụng nào cũng nên làm “big bang” nâng cấp Boot, Java, SAML, DB và reverse proxy cùng một ngày. Tách thay đổi, chạy canary và giữ fallback an toàn khi business SLA cho phép.

## 4. Bước 0: Kiểm kê mọi hành vi cũ trước khi thay code

Một bản **inventory** nên ghi, cho từng đối tác IdP:

| Thành phần/giá trị phải thu thập | Vì sao quan trọng? |
| --- | --- |
| **SP EntityID** | IdP dùng làm audience/identifier; thay có thể phải cấu hình mới phía đối tác |
| **IdP EntityID/Issuer** | Chọn đúng nguồn được tin; nhiều partners có thể dùng usernames giống nhau |
| **SSO endpoint URL, binding** | Browser redirect/POST phải đến đúng IdP |
| **ACS URL, binding, index** | IdP POST SAMLResponse tới đích đã đăng ký |
| **SingleLogoutService URLs và binding** | RP/AP initiated logout, request/response handling |
| **Signing rules** | Response ký hay Assertion ký, AuthnRequest có phải ký không |
| **IdP verification certificates** | Dùng kiểm chữ ký; khác SP signing private key |
| **SP encryption/decryption keys** | Bật EncryptedAssertion/EncryptedAttribute/EncryptedID |
| **NameIDFormat và subject identity key** | Quy định local-account linking, không chỉ displayName/email |
| **Attribute Name/NameFormat, cardinality** | Group/role/tenant/email mapping, values có thể đa trị |
| **RequestedAuthnContext/forceAuthn/passive/scoping** | IdP policy, MFA assurance, step-up behavior |
| **SP-initiated/IdP-initiated SSO** | Correlation/InResponseTo/RelayState policy khác nhau |
| **Session timeout/cookie/SameSite** | Cross-site POST ACS có thể mất session state nếu cookie policy sai |
| **AuthnRequest repository/RelayState** | Cần giữ request correlation trong cluster |
| **Metadata refresh/expiry và trust policy** | Rotation, issuer/cert trust, startup khi IdP offline |
| **Multi-IDP discovery/entityAlias** | Login URL và tenant selection/registration resolution |
| **Artifact/ECP/SOAP/PAOS support cũ** | Có thể không có tính năng thay thế trực tiếp, cần đánh giá gap |
| **Logging/audit/error handlers** | Đừng mất authentication/authorization audit khi đổi filter |
| **Load balancer/proxy/forwarded headers** | Sinh đúng public scheme/host trong ACS/metadata |
| **Operations keys/secret management** | HSM/JKS, alias/password, key lifecycle, rotation và quyền đọc |
| **Partner contact, approval và rollback** | IdP phải cập nhật metadata/cert có kiểm soát |

**Nguồn kiểm kê** có thể là XML security context, `web.xml`, current IdP metadata/SP metadata, management UI của IdP, deployment secrets và E2E traces bằng test identities. **Không đưa production SAMLResponse, raw NameID, private key hoặc keystore password vào tài liệu inventory**; chỉ ghi fingerprints/versions và references được duyệt.

### Ví dụ cấu hình extension cũ cần nhận diện

~~~xml
<!-- Cấu trúc LỊCH SỬ, chỉ để nhận diện trong project cũ. -->
<security:http entry-point-ref="samlEntryPoint">
  <security:custom-filter before="FIRST"
                          ref="metadataGeneratorFilter"/>
  <security:custom-filter after="BASIC_AUTH_FILTER"
                          ref="samlFilter"/>
</security:http>
~~~

Các bean `samlFilter` thường gộp nhiều servlet filters, và `samlEntryPoint` khởi tạo SSO. **Không đặt các filter legacy này cùng filter chain mới** với cùng ACS để “chạy song song” trong một endpoint; kết quả có thể double parsing, cạnh tranh session state và xác thực sai flow.

## 5. Thiết kế trạng thái đích

Một ứng dụng Spring Security SAML2 RP/SP hiện đại thường gồm:

~~~mermaid
flowchart TD
    U[Browser] --> F[Spring SecurityFilterChain]
    F --> R[SSO request filter]
    R --> IDP[Trusted IdP]
    IDP --> ACS[SAML Response POST to ACS]
    ACS --> P[Saml2WebSsoAuthenticationFilter]
    P --> T[RelyingPartyRegistrationRepository]
    P --> A[OpenSAML authentication provider]
    A --> V[Signature / issuer / audience / time / recipient]
    V --> M[Verified NameID and attributes]
    M --> L[Local identity and authority mapper]
    L --> X[Spring SecurityContext / application session]
    X --> B[Business authorization and tenant policy]
~~~

Trong đó:
- `SecurityFilterChain` định nghĩa endpoint authorization và bật SAML2.
- `RelyingPartyRegistration` đại diện **một quan hệ SP–IdP**; một ứng dụng có thể có nhiều registrations.
- `RelyingPartyRegistrationRepository` tra cứu registration theo `registrationId` hoặc strategy riêng.
- `Saml2X509Credential` biểu diễn certificates/keys theo **key use** (signing, decryption, verification).
- OpenSAML provider xử lý signature/decryption/protocol validation trước khi tạo authenticated object.
- Application local mapper không tự decode raw `SAMLResponse` hoặc bỏ qua provider.

**Lưu ý:** nhiều IdPs có thể đại diện các tổ chức/tenants, nhưng “tenant” của business domain vẫn cần kiểm riêng. Không map `registrationId` tùy ý từ browser thành quyền truy cập tenant.

## 6. Dependency: bỏ extension, thêm service provider module

### Maven với Spring Boot BOM

~~~xml
<!-- Trong pom.xml đã quản lý Spring Boot/Spring Security version. -->
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

### Gradle

~~~groovy
repositories {
    mavenCentral()
    // OpenSAML artifacts có thể cần thêm repository Shibboleth.
    maven {
        url = uri("https://build.shibboleth.net/maven/releases")
    }
}

dependencies {
    implementation("org.springframework.security:spring-security-saml2-service-provider")
}
~~~

Nếu dùng Spring Boot với BOM, **đừng gắn một version SAML module khác dòng Security đã resolve**. Theo Spring Boot docs, OpenSAML có thể cần **Shibboleth Maven Releases repository**; kiểm repository thực cần theo version và tổ chức, không bật arbitrary insecure repository.

### Những dependencies cũ cần loại bỏ hoặc cô lập

~~~text
org.springframework.security.extensions:spring-security-saml2-core
org.opensaml:*                         (versions từ extension cũ)
org.apache.xml.security:*              (override không tương thích)
commons-logging / servlet javax.*      (theo dependency cụ thể)
tự viết SAMLProcessingFilter và WebSSOProfileConsumer subclasses
~~~

Các tọa độ/versions chính xác của legacy artifact phụ thuộc hệ thống. **Không xóa bừa một XML security library còn được module khác dùng**; chạy dependency tree và kiểm classpath clash trước khi loại.

Lệnh kiểm:

~~~bash
mvn dependency:tree
mvn -DskipTests=false test

# Nếu dùng Gradle:
./gradlew dependencies --configuration runtimeClasspath
./gradlew test
~~~

Nếu plugin Maven surefire hoặc Gradle build có logic khác, chọn lệnh tương ứng; ví dụ chỉ minh họa. **Không đưa keystore/secret production vào CI** để “đảm bảo test pass”.

## 7. Cấu hình Spring Boot hiện hành tối thiểu bằng IdP metadata

Spring Boot có thể tự cấu hình `RelyingPartyRegistrationRepository` từ properties:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "https://idp.example/metadata"
~~~

Giá trị là **IdP metadata URL giả**; ứng dụng thật cần IdP đã cung cấp metadata, trust đúng HTTPS và entity registration đã được IdP chấp thuận. Tên `assertingparty` là schema trong các dòng Boot hiện hành; nếu dự án dùng dòng Boot cũ có thể gặp `identityprovider` trong tài liệu lịch sử. **Đối chiếu configuration metadata của phiên bản Boot thật** trước khi copy.

Spring Security Boot auto-config có thể sinh registration và filter chain nếu dependency/properties đầy đủ, nhưng khi bạn định nghĩa `SecurityFilterChain` riêng thì phải **bật `saml2Login()` trong chain phục vụ callback**, không tự tin auto-config vẫn thêm mọi filter.

**Caveat metadata URL lúc startup:** nếu builder/runtime tải metadata từ IdP lúc khởi động và endpoint IdP offline, app có thể fail startup. Với hệ thống yêu cầu offline boot, cân nhắc metadata file/config revision được phê duyệt, retry/cache/hot reload strategy theo version; không tắt TLS verify hoặc chấp nhận metadata unsigned từ URL không tin cậy.

## 8. JavaConfig hiện hành: một quan hệ SP–IdP

Ví dụ **Spring Security project fragment** cho một SP, sử dụng Java 17+ nhưng **cần Spring Security/Boot dependencies**; không chạy bằng javac thuần:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration
        .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class Saml2SpSecurityConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration rp =
                RelyingPartyRegistrations
                    .fromMetadataLocation("https://idp.example/metadata")
                    .registrationId("corp")
                    .entityId("https://reports.example/saml2/sp/corp")
                    .assertionConsumerServiceLocation(
                        "https://reports.example/login/saml2/sso/corp")
                    .build();

        return new InMemoryRelyingPartyRegistrationRepository(rp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/health").permitAll()
                    .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

**Lưu ý lớn:**
- `https://idp.example/metadata`, `https://reports.example/...` và `corp` là giá trị **minh họa**, phải thay bằng thông số đã được IdP approve.
- `entityId(...)` và `assertionConsumerServiceLocation(...)` được **đặt rõ**. Nếu muốn giữ `EntityID`/ACS cũ thì dùng giá trị cũ đã kiểm, nhưng **ACS cũ khác default filter URL**; phải cấu hình callback resolver/filter tương ứng (phần 10). Không chỉ thay một dòng metadata.
- `RelyingPartyRegistrations.fromMetadataLocation` parse **IdP metadata**; chữ ký, issuer trust, HTTPS, expiry và rollover cần có policy vận hành.
- `saml2Metadata()` xuất SP metadata từ registration; **không thay `saml2Login()`**.
- Không bật `saml2Logout()` trong mẫu tối thiểu nếu chưa cung cấp signing keys, SLO endpoints và xác minh IdP support; phần 15 đề cập riêng.
- Nếu IdP yêu cầu AuthnRequest ký hoặc encrypt Assertion, **phải thêm SP credentials** đúng vai trò.
- Nếu app có API Basic/JWT/OIDC khác, thiết kế nhiều filter chains/request matchers để SAML chain không vô tình chặn toàn bộ hệ thống.

Mẫu tránh viết thủ công `MetadataGeneratorFilter` hoặc `SAMLProcessingFilter`. Cấu hình identity/role mapping sẽ thực hiện sau provider validation, không tạo Authentication từ XML chưa verify.

## 9. Endpoint mapping cũ–mới

Các đường dưới đây là **mẫu thường gặp**, không mặc định mọi extension app đã dùng cùng URL.

| Chức năng | Legacy URL điển hình | Spring Security SAML2 default | Yêu cầu migration |
| --- | --- | --- | --- |
| Bắt đầu SP-initiated login | `/saml/login` | `/saml2/authenticate/{registrationId}` | Đổi link/UI/entry point/IdP picker |
| ACS nhận SAMLResponse | `/saml/SSO` | `/login/saml2/sso/{registrationId}` | Đổi IdP ACS/metadata hoặc thêm custom processing URL |
| SP metadata | `/saml/metadata` | `/saml2/metadata` và `/saml2/metadata/{registrationId}` | Re-register metadata URL/EntityID |
| SP metadata alias | URL tùy extension/alias | `/saml2/service-provider-metadata/{registrationId}` | So metadata payload, không đoán |
| SLO inbound/outbound | `/saml/SingleLogout` hoặc variant | `/logout/saml2/slo` | Cấu hình logout request/response matcher và metadata |
| Local logout | App `/logout` tùy cấu hình | `POST /logout` theo Spring config | Không nhầm local logout với global SLO |

**Sai lầm hay gặp:** IdP tiếp tục gửi POST `/saml/SSO` nhưng Spring chỉ bắt `/login/saml2/sso/corp`. HTTP 404/403/redirect loop có thể xuất hiện dù signature keys đúng. Cần kiểm **effective external URL** (scheme, host, port, context path, reverse-proxy rewrite) và giá trị ACS trong metadata mà IdP **thực sự đang dùng**.

### Có nên giữ nguyên URL cũ?

Có hai lựa chọn thực tế:

**A. Đổi sang defaults mới:** đơn giản hơn và dễ bảo trì; yêu cầu IdP sửa metadata/ACS, update bookmarks/SSO links, chạy thử cùng thay đổi cấu hình đối tác.

**B. Giữ URLs cũ tạm thời:** giảm thay đổi phía IdP trong một giai đoạn, nhưng phải **khớp đồng thời**:
- `RelyingPartyRegistration.assertionConsumerServiceLocation`.
- `http.saml2Login(saml2 -> saml2.loginProcessingUrl(...))`.
- Logic xác định đúng registration nếu URL không chứa `{registrationId}`.
- Proxy routes/CSRF/Cookie/SameSite và SAML binding thực.
- IdP metadata và registered ACS chính xác.

**Không chỉ chỉnh ACS trong metadata** rồi kỳ vọng filter tự nghe URL đó. Ngược lại, không chỉ đổi filter path mà quên partner metadata đã đăng ký.

## 10. Tùy biến ACS khi cần duy trì đường dẫn legacy

Spring reference chỉ ra có thể đổi URL nơi `Saml2WebSsoAuthenticationFilter` xử lý `SAMLResponse` bằng `saml2Login().loginProcessingUrl(...)`.

Ví dụ fragment:

~~~java
@Bean
SecurityFilterChain legacyAcsCompatibility(HttpSecurity http)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml2 -> saml2
                .loginProcessingUrl("/saml/SSO"))
            .build();
}
~~~

**Chỉ là cấu hình minh họa:** khi ACS không có `{registrationId}` và có nhiều IdPs/tenants, phải đảm bảo `RelyingPartyRegistration` được resolve **đúng nguồn tin cậy** bằng `AuthenticationConverter`/resolver, correlation state hoặc issuer matching được validate. Đừng dựa vào `registrationId` do browser tự thêm rồi cho nó quyết định trust hoặc tự chọn “IdP đầu tiên”.

Phải khai báo cùng ACS external URL trong registration và trên IdP. Dùng staging test với hai IdPs để xác nhận không chọn sai signing key/audience.

### Không dùng HTTP GET để nhận SAMLResponse tùy ý

Web Browser SSO SAMLResponse thông thường đi qua **HTTP POST binding** vào ACS. Theo Spring Security 7.x migration docs, converters đang được siết cách xử lý SAML Response GET trong lộ trình phiên bản sau. **Không dùng GET response payload như một shortcut tương thích với legacy nếu chưa có chuẩn/binding chính thức**, và không disable signature/protocol checks để chấp nhận URL-based response.

**RelayState** có thể mang opaque correlation state; không dùng raw RelayState làm open redirect hay chứa sensitive token.

## 11. Metadata: từ MetadataGenerator sang saml2Metadata()

Legacy extension thường khởi tạo `MetadataGenerator`, `MetadataGeneratorFilter`, `MetadataDisplayFilter` và quản lý `entityAlias`/keystore.

Spring Security hiện hành:

~~~java
http.saml2Login(Customizer.withDefaults());
http.saml2Metadata(Customizer.withDefaults());
~~~

Theo tài liệu metadata hiện hành, endpoint thường có:

~~~text
GET /saml2/metadata
GET /saml2/metadata/{registrationId}
GET /saml2/service-provider-metadata/{registrationId}
~~~

**Quan trọng:** metadata mới có thể khác metadata cũ dù cùng tên app. Trước khi đưa IdP dùng:

- So `EntityDescriptor.entityID` **byte-for-byte/URI chính xác** với partner registration.
- So `SPSSODescriptor`, `AssertionConsumerService Location`, Binding và index/default.
- So public signing/encryption certificates và `KeyDescriptor use`.
- So `SingleLogoutService Location` và các bindings được hỗ trợ.
- So `NameIDFormat`, `AuthnRequestsSigned`, `WantAssertionsSigned` theo hợp đồng.
- So hostname/port/scheme/path qua load balancer và `{baseUrl}`.
- Kiểm IdP metadata cache: “metadata SP mới đã publish” **không đồng nghĩa IdP đã import/apply**.

**Đừng copy metadata XML cũ vào endpoint mới rồi bỏ qua `RelyingPartyRegistration`**: runtime checks/ACS/EntityID cần nhất quán với metadata đã công bố. Nếu hệ thống dùng metadata ký (signed metadata), xác định cách ký và nơi validate ở cả hai phía.

### Metadata mới không cần toàn bộ công cụ quản trị cũ

Đừng đưa `MetadataGeneratorFilter`, `MetadataManager` hoặc `ExtendedMetadata` của extension lên classpath chỉ để có endpoint `/saml/metadata`. Bản hiện hành có `saml2Metadata` và repository; nếu cần custom metadata, dùng supported resolver/customization API cho version đang dùng, không trộn filter cũ vào security chain mới.

## 12. Khóa và X.509: KeyManager không chuyển “nguyên object” sang mới

Legacy `KeyManager` có thể đọc JKS alias chứa SP private key, SP signing certificate và IdP verification material. Spring SAML2 dùng **`Saml2X509Credential`** phân loại theo mục đích:

| Mục đích | Ai sở hữu private key? | IdP/SP dùng ra sao? |
| --- | --- | --- |
| **IdP signing** | IdP | SP dùng **public cert** với `Saml2X509Credential.verification(cert)` |
| **SP AuthnRequest signing** | SP | SP dùng **private key** với `Saml2X509Credential.signing(privateKey,cert)`; IdP verify public cert |
| **SP Assertion decryption** | SP | IdP encrypt bằng public SP cert; SP `Saml2X509Credential.decryption(privateKey,cert)` |
| **TLS certificate** | Máy chủ tương ứng | Bảo vệ HTTPS; không mặc định là SAML XML signing key |
| **IdP metadata signature** | Metadata issuer/owner | Có trust policy/verification riêng; không mặc định cùng key với assertion |

Fragment JavaConfig để thêm credential của SP:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.cert.X509Certificate;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;

RelyingPartyRegistration withSpKeys(
        RelyingPartyRegistration.Builder builder,
        RSAPrivateKey signingKey,
        X509Certificate signingCert,
        RSAPrivateKey decryptionKey,
        X509Certificate encryptionCert) {

    Saml2X509Credential signing =
            Saml2X509Credential.signing(signingKey, signingCert);
    Saml2X509Credential decryption =
            Saml2X509Credential.decryption(decryptionKey, encryptionCert);

    return builder
            .signingX509Credentials(keys -> keys.add(signing))
            .decryptionX509Credentials(keys -> keys.add(decryption))
            .build();
}
~~~

**Đây là fragment trong dự án có dependencies**, không phải chương trình tự chạy. `signingKey`, `decryptionKey` và certificates đến từ secret manager/keystore loader có kiểm soát; code không load PEM trong ví dụ. Khi chuyển từ JKS:
- Kiểm alias nào phục vụ **SP signing** và alias nào dùng decrypt.
- Nếu chuyển key định dạng, kiểm **PKCS#8 private key**, algorithm, certificate chain và khớp keypair.
- Giữ private key ngoài Git/container image/log/test report.
- Không vô tình xuất **IdP private signing key** tới SP (IdP chỉ cung cấp verification public cert).
- Rà hỗ trợ thuật toán RSA/ECDSA, XML Signature/Encryption và key transport theo IdP/OpenSAML baseline.
- Có kế hoạch old/new verification/decryption key **overlap** khi rotate, không xóa key trước khi messages còn in flight.
- Nếu IdP bắt buộc ký AuthnRequest, thêm SP signing credentials trước rollout; không hạ yêu cầu ký phía IdP chỉ để “chạy”.

**Không dùng trust-all certificate verifier** hoặc bỏ kiểm XML signature khi thấy lỗi tương thích.

## 13. IdP metadata, trust anchors và rollover

Một `RelyingPartyRegistration` bao gồm thông tin **Asserting Party**: entity ID, SSO/SLO URLs, verification credentials và preferences. Tải metadata từ một URL không đủ để tạo trust boundary nếu chưa xác định **ai kiểm soát URL, certificate nào được tin, metadata có được ký/xác thực ra sao và khi nào cập nhật**.

Quy trình:
1. Đội IAM xác nhận IdP EntityID và metadata endpoint qua kênh chính thức.
2. Xác minh HTTPS/PKIX/hostname hoặc metadata signature theo policy.
3. Lưu fingerprint/trust revision vào cấu hình được duyệt.
4. Import/test vào staging rồi mới tạo production registration.
5. Khi IdP công bố signing cert mới, so old/new `KeyDescriptor` và activation time.
6. Bảo đảm các Spring nodes có cùng approved trust set hoặc versioned rollout.
7. Audit `PARTNER_CONFIG_PROPOSED → APPROVED → ACTIVATED` và rollback nếu cần.
8. Test signed assertion bằng cert cũ/mới theo overlap policy.
9. Không tự tin vào một `InMemoryRelyingPartyRegistrationRepository` tạo lúc startup nếu yêu cầu refresh động; kiểm cache/repository refresh mechanism theo version.

**Sự khác nhau với legacy:** không có nghĩa tính năng tự reload metadata từ `FilesystemMetadataProvider`/`HTTPMetadataProvider`/`CachingMetadataManager` trước đây tự xuất hiện khi bạn gọi `fromMetadataLocation`. Một repository khởi tạo từ metadata ở startup có thể giữ snapshot; nếu yêu cầu hot refresh, phải chủ động thiết kế repository/caching/periodic reload và concurrency/rollback.

## 14. Identity, NameID và ánh xạ quyền khi nâng cấp

SAML Identity có thể dựa vào `NameID` với format (persistent/transient/emailAddress), issuer, registration hoặc một attribute có hợp đồng ổn định. Legacy code thường nhận `SAMLCredential` và gọi một `SAMLUserDetailsService`. Spring SAML2 mới đưa kết quả provider vào `Authentication` và attributes/authorities.

**Không lấy email mặc định làm khóa local account** khi di chuyển: email có thể đổi/cấp lại; NameID format transient thay đổi theo login; nhiều IdPs có thể có cùng `NameID` dạng chuỗi. Nên định nghĩa **stable identity key** dựa trên trusted IdP/issuer + subject identifier đủ ổn định, cùng tenant/account-linking approval.

| Legacy behavior | Target behavior cần test |
| --- | --- |
| Đọc `SAMLCredential.getNameID()` | Đọc verified principal/subject từ SAML provider đúng version |
| `SAMLUserDetailsService.loadUserBySAML(...)` | Custom response converter/delegated account lookup hoặc post-auth local mapping |
| `SAMLCredential.getAttributeAsString(...)` | Verified attribute contract từ principal/assertion accessor, xử lý list và kiểu |
| Dùng role theo raw groups | Exact allowlist từ trusted groups → app `GrantedAuthority` |
| Tự gán `ROLE_USER` hoặc default admin | Phân biệt framework default authority với business authorization |
| Account link theo username/email | Link theo stable subject/issuer/registration và kiểm migration consistency |
| Attribute namespace/NameFormat | Test đúng tên `Attribute Name`, không tin `FriendlyName` tự do |

### SAML AttributeValue có thể đa trị

~~~xml
<saml:Attribute
  Name="urn:example:claims:groups"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AttributeValue>APP_REPORT_VIEWERS</saml:AttributeValue>
  <saml:AttributeValue>FINANCE_EMPLOYEES</saml:AttributeValue>
</saml:Attribute>
~~~

Một IdP có thể phát **0..N** `AttributeValue` và kiểu dữ liệu không phải String. **Không tự split dấu phẩy** trừ khi contract IdP nêu đó là một value delimited. Đừng lấy `getFirstAttribute("groups")` nếu cần xét toàn bộ groups. Một `Domain Admins` từ AD/IdP không tự thành app `ROLE_ADMIN`.

### Spring Security 6/7 principal khác nhau

- Ở Spring 6 nhiều ứng dụng dùng `Saml2AuthenticatedPrincipal` và `getFirstAttribute`/`getAttribute`.
- Tài liệu migration Spring 7 đánh dấu `Saml2AuthenticatedPrincipal` deprecated, chuyển thông tin assertion sang `Saml2ResponseAssertionAccessor` gắn với credential trong default flow.
- Spring 7 có `Saml2AssertionAuthentication` và response conversion API khác với legacy `SAMLCredential`.
- Không cast `Authentication.getPrincipal()` về class cũ khi đã nâng lên version mới hoặc app dùng nhiều authentication mechanisms.
- Khi customize converter, **delegate default validation/result** rồi bổ sung local user/authorities; không tự parse raw SAMLResponse mà không verify.

**Mục tiêu migration:** role/tenant/user linking giống business intent cũ nhưng an toàn hơn, không nhất thiết giống từng class Java hoặc `Authentication.toString()`.

## 15. Single Logout: không coi local logout là SLO

Extension cũ thường cấu hình `SAMLLogoutFilter` và `SAMLLogoutProcessingFilter`. Spring Security hiện hành có `saml2Logout()` và các filters dành cho `SAMLRequest`/`SAMLResponse`.

Theo tài liệu Spring:
- **RP-initiated:** User POST tới endpoint logout; SP xóa local session, phát `LogoutRequest` ký đến IdP; IdP có thể trả `LogoutResponse` để SP kiểm.
- **AP/IdP-initiated:** SP nhận `LogoutRequest` từ IdP, xác minh chữ ký/issuer/destination/subject/correlation phù hợp, invalidate session rồi trả `LogoutResponse`.
- Default SLO endpoint của Spring thường là **`/logout/saml2/slo`**.
- Bật `saml2Logout()` cần **IdP hỗ trợ SLO và có signing key/cert SP phù hợp** (theo cấu hình tài liệu). Không chỉ thêm DSL rồi coi global logout tự hoạt động.

### JavaConfig fragment tùy chọn khi đáp ứng SLO prerequisites

~~~java
// Trong bean SecurityFilterChain khi đã có registration với
// SP signing credentials và IdP SingleLogoutService metadata:
http
    .saml2Login(Customizer.withDefaults())
    .saml2Logout(Customizer.withDefaults());
~~~

Để giữ endpoint `/SLOService.saml2` cũ, tài liệu cho customization:

~~~java
http.saml2Logout(saml2 -> saml2
    .logoutRequest(request -> request
        .logoutUrl("/SLOService.saml2"))
    .logoutResponse(response -> response
        .logoutUrl("/SLOService.saml2"))
);
~~~

Cũng phải cập nhật `singleLogoutServiceLocation` trong registration và partner metadata. **Chỉ viết filter matcher không đủ**.

### Local vs SLO và session semantics

| Sự kiện | Có thể kết luận |
| --- | --- |
| `POST /logout` xử lý local cleanup | Local session đã được xóa theo implementation |
| SP đã gửi `LogoutRequest` | Đã khởi tạo SLO, chưa xác nhận IdP đã xóa session |
| SP nhận signed/valid `LogoutResponse` | Đã xác nhận response theo scope/protocol |
| SP nhận IdP-initiated `LogoutRequest` hợp lệ | Có thể invalidate matching local session theo policy |
| Browser đóng tab | Không có bằng chứng server-side logout |
| Session expired | Không phải người dùng chủ động logout |

Trong migration phải test **RP-initiated và IdP-initiated**, session index/NameID matching, RelayState, InResponseTo, CSRF/cookie và response status. Không phát event `GLOBAL_LOGOUT_COMPLETED` khi chỉ thấy HTTP 200 hoặc redirect.

## 16. SP-initiated so với IdP-initiated SSO

Legacy app có thể hỗ trợ cả:
- **SP-initiated**: Spring phát AuthnRequest, lưu request/RelayState, IdP trả `InResponseTo` khớp.
- **IdP-initiated (unsolicited)**: IdP gửi SAMLResponse tới ACS khi SP chưa tạo AuthnRequest; correlation không có như luồng SP-initiated.

**Không mở mặc định unsolicited SSO chỉ để tương thích** nếu business không cần. Khi phải chấp nhận, cần policy cụ thể về issuer, recipient, audience, signature, freshness, replay, local user linking và login CSRF/session confusion. Một app khác nhau có thể yêu cầu disable IdP-initiated SSO hoàn toàn.

Thử cases:
- Người dùng bắt đầu từ portal IdP cũ; có còn đường IdP-initiated không?
- IdP gửi `RelayState` là opaque state hay một URL; có open redirect không?
- IdP gửi Response tới ACS mới trong staging và production; destination được validate đúng?
- Authentication Request repository trong session có lưu/đọc được khi callback đến pod khác?
- `InResponseTo`/request-ID được kiểm đầy đủ ở SP-initiated case?
- Replay cache chia sẻ nhiều nodes hay chỉ local JVM?
- Nếu có nhiều IdP, nguồn validation cert nào được chọn cho unsolicited response?

**Một migration thành công không được đánh đổi bằng cách tắt signature, issuer hoặc audience checks.**

## 17. Các profile/bindings extension có thể chưa tương đương

Tài liệu extension 1.x lịch sử liệt kê các profile như:
- Web Browser SSO (SP-/IdP-initiated).
- Single Logout.
- HTTP-POST, HTTP-Redirect, Artifact, SOAP, PAOS/ECP và các dạng Enhanced Client/Proxy trong phạm vi extension.
- Discovery/IdP selection, metadata interoperability, một số PKIX trust và holder-of-key cases.

SAML2 module hiện hành được Spring mô tả chủ yếu là **SAML Web Browser SSO Service Provider** và SLO. **Không tự suy mọi binding/profile của extension 1.x được hỗ trợ giống hệt**. Lập bảng:

| Feature cũ | Hướng xử lý |
| --- | --- |
| HTTP-Redirect AuthnRequest + HTTP-POST SAMLResponse | Khả năng phổ biến, test mặc định |
| POST AuthnRequest nếu IdP yêu cầu | Kiểm `Saml2AuthenticationRequestResolver`/OpenSAML factory customization |
| Artifact binding | Xác minh hỗ trợ cụ thể; nếu chưa có, thiết kế alternative/gateway |
| SOAP/ECP/PAOS | Có thể cần SAML gateway hoặc library khác theo feature gap |
| Holder-of-key profiles | Không mặc định thay thế bằng bearer web SSO |
| Custom discovery service | Triển khai trang picker/registration resolution rõ |
| Metadata reload không restart | Custom/caching repository và trust change process |
| Custom policy “sign Response hoặc all Assertions” | Dùng provider validators theo version, kiểm negative cases |
| Custom request-scoping/RequestedAuthnContext | Cấu hình customization chặt, test với IdP |
| Custom logout/session index | Tái hiện đúng SLO contract bằng supported APIs |

Nếu có profile cũ **bắt buộc cho đối tác**, việc triển khai “Spring Security 7 + saml2Login()” có thể **chưa đủ**. Không silently disable chức năng, không hạ profile; cân nhắc dedicated SAML gateway/IdP broker hoặc trì hoãn riêng phần đó kèm risk acceptance và kế hoạch thay thế.

## 18. Reverse proxy, context path và forwarded headers

Legacy `SAMLContextProviderLB` thường dùng để thông báo public server name/port/context path khi ứng dụng chạy sau Nginx/ingress. Trong Spring hiện hành, nhiều URL dùng `{baseUrl}` và `RelyingPartyRegistration`, chịu ảnh hưởng request/proxy metadata.

Ví dụ:

~~~text
External URL: https://portal.example/sso
Ingress -> internal http://app:8080

Expected public ACS:
  https://portal.example/login/saml2/sso/corp

Wrong inferred ACS if forwarded headers missing:
  http://app:8080/login/saml2/sso/corp
~~~

Nếu IdP gửi Destination tới public URL nhưng Spring validate theo internal URL, login fail. Các bước:
1. Xác định canonical external public URL cho SP.
2. Kiểm trusted proxy headers `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host`/`X-Forwarded-Port`/prefix.
3. Cấu hình Boot `server.forward-headers-strategy` phù hợp môi trường **hoặc** ForwardedHeaderFilter/server native, tránh hai lớp xử lý trùng.
4. **Chỉ tin forwarded headers do trusted ingress set/sanitize**; không chấp nhận header do client ngoài Internet giả mạo để tạo malicious ACS URLs.
5. Có thể dùng explicit `entityId`/ACS URL để ổn định nếu kiến trúc yêu cầu, nhưng filter matcher/IdP metadata phải cùng contract.
6. Test HTTPS và path prefix trên production-like ingress, không chỉ localhost.

**Không khắc phục Destination mismatch bằng cách bỏ DestinationValidator.** Điều đó giảm khả năng phát hiện SAMLResponse dành cho endpoint khác.

## 19. CSRF, session cookie và AuthnRequest correlation

Spring Security dùng HTTP session/repository để lưu authorization request state trong nhiều cấu hình. Với SAML Web Browser SSO, IdP trả **cross-site HTTP POST** tới ACS; browser cookie policies (SameSite/third-party cookie restrictions) có thể làm mất session cookie và request correlation.

- `SameSite=Lax` thường hỗ trợ top-level cross-site **GET**, nhưng không mặc định gửi cookie trong cross-site POST.
- `SameSite=None; Secure` có thể cần cho một số SAML POST ACS/session designs, đồng thời phải đánh giá CSRF risk.
- Spring `HttpSessionSaml2AuthenticationRequestRepository`/request repository cần phù hợp load balancing/session store.
- Nếu callback đến pod khác, Spring Session/Redis hoặc sticky session có thể được dùng theo rủi ro/triển khai; phải bảo đảm TTL và request correlation.
- Đừng disable CSRF toàn ứng dụng chỉ để ACS POST qua được. Spring SAML filters có cơ chế phù hợp; nếu dùng custom URL cần cấu hình exemption tối thiểu có lý do và test.
- Kiểm `RelayState` và `InResponseTo`, chống unsolicited/replay/login CSRF.
- Sau login thay đổi session ID/fixation policy và không giữ raw SAMLResponse/tickets lâu hơn cần.
- Test Safari/Firefox/Chrome với cookie policies hiện hành; không khẳng định Chrome cấm third-party cookie cho tất cả người dùng.

**Không coi “chữ ký SAML hợp lệ” là đủ nếu request/session correlation bị bypass**. Migration có thể làm login flow yếu hơn khi cố phục hồi tính tương thích.

## 20. Authorization: giữ quyền nghiệp vụ, không giữ security smell cũ

Legacy `SAMLUserDetailsService` có thể tạo application `UserDetails` và authorities dựa trên `SAMLCredential`. Trong Spring Security SAML2, authority default từ framework không tự là quyền business.

**Policy tiêu biểu:**
- Verified IdP + immutable subject → local user link, không dùng email như primary key vô điều kiện.
- Attribute `groups` có 0..N values; chỉ map **approved group IDs** sang `ROLE_REPORT_VIEWER`/`ROLE_REPORT_EDITOR`.
- `tenant` bắt buộc: đúng **một** giá trị và kiểm local tenant membership.
- Thiếu group → authenticated nhưng **không** có app-specific role; endpoint protected trả deny.
- `Domain Admins` của AD không tự thành `ROLE_ADMIN` của portal.
- Local account disabled → deny dù SAML Assertion hợp lệ.
- User từ IdP A và IdP B cùng username/email → không tự account-link.

Ví dụ contract:

~~~text
idpEntityId: https://idp.example/entity
subject: persistent-opaque-user-id
tenant: reports
groups: [APP_REPORT_VIEWERS, OTHER_GROUP]

local user key:
  (trusted_idp_entity_id, stable_subject)
  -> local_user_041

approved mapping:
  APP_REPORT_VIEWERS -> ROLE_REPORT_VIEWER
  OTHER_GROUP        -> no application role
~~~

**Không log raw Assertion XML, NameID, email và group list** trong quá trình migration. Dùng synthetic identities, sanitized error codes và internal correlation ID.

## 21. Java 17 độc lập: kiểm hợp đồng migration trước khi đổi IdP

Chương trình sau dùng **chỉ Java 17** để kiểm xem một bản cấu hình đích có giữ những thông số thiết yếu của SP cũ không: `EntityID`, ACS, issuer, chính sách ký AuthnRequest, NameID format, group attribute. Nó còn minh họa role mapping theo allowlist.

**Đây là contract-check demo**, **không** parse/verify SAMLResponse, không thực hiện XML Signature/Encryption, không kết nối IdP. Production vẫn cần Spring Security/OpenSAML provider và signed E2E fixtures.

Tạo file **`SamlExtensionMigrationDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SamlExtensionMigrationDemo {

    record SpContract(
            String spEntityId,
            String acsUrl,
            String idpEntityId,
            boolean signedAuthnRequestRequired,
            String nameIdFormat,
            String groupsAttribute) { }

    static Set<String> appRoles(List<String> incomingGroups) {
        Set<String> roles = new TreeSet<>();
        for (String group : incomingGroups) {
            if ("APP_REPORT_VIEWERS".equals(group)) {
                roles.add("ROLE_REPORT_VIEWER");
            }
            if ("APP_REPORT_EDITORS".equals(group)) {
                roles.add("ROLE_REPORT_EDITOR");
            }
        }
        return roles;
    }

    static boolean sameTrustContract(
            SpContract oldConfig,
            SpContract newConfig) {
        return oldConfig.spEntityId().equals(newConfig.spEntityId())
                && oldConfig.acsUrl().equals(newConfig.acsUrl())
                && oldConfig.idpEntityId().equals(newConfig.idpEntityId())
                && oldConfig.signedAuthnRequestRequired()
                     == newConfig.signedAuthnRequestRequired()
                && oldConfig.nameIdFormat().equals(newConfig.nameIdFormat())
                && oldConfig.groupsAttribute()
                     .equals(newConfig.groupsAttribute());
    }

    public static void main(String[] args) {
        String issuer = "https://idp.example/entity";
        String entity = "https://reports.example/legacy-sp";
        String acs = "https://reports.example/saml/SSO";
        String format =
                "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
        String groups = "urn:example:claims:groups";

        SpContract legacy = new SpContract(
                entity, acs, issuer, true, format, groups);
        SpContract preserved = new SpContract(
                entity, acs, issuer, true, format, groups);
        SpContract changed = new SpContract(
                "https://reports.example/new-sp",
                "https://reports.example/login/saml2/sso/corp",
                issuer, false, format, groups);

        System.out.println("Preserved contract compatible: "
                + sameTrustContract(legacy, preserved));

        System.out.println("Changed defaults compatible: "
                + sameTrustContract(legacy, changed));

        System.out.println("SP EntityID preserved: "
                + legacy.spEntityId().equals(
                    preserved.spEntityId()));

        System.out.println("ACS preserved: "
                + legacy.acsUrl().equals(
                    preserved.acsUrl()));

        System.out.println("IdP issuer preserved: "
                + legacy.idpEntityId().equals(
                    preserved.idpEntityId()));

        System.out.println("Request signing policy preserved: "
                + (legacy.signedAuthnRequestRequired()
                   == preserved.signedAuthnRequestRequired()));

        System.out.println("Approved roles: "
                + appRoles(List.of(
                    "Domain Admins", "APP_REPORT_VIEWERS")));

        System.out.println("Unapproved admin becomes ROLE_ADMIN: "
                + appRoles(List.of("Domain Admins"))
                    .contains("ROLE_ADMIN"));

        System.out.println("Missing approved group grants role: "
                + !appRoles(List.of("OtherGroup")).isEmpty());

        System.out.println("New ACS needs partner update: "
                + !legacy.acsUrl().equals(changed.acsUrl()));
    }
}
~~~

Biên dịch và chạy **JDK 17+**:

~~~bash
javac SamlExtensionMigrationDemo.java
java SamlExtensionMigrationDemo
~~~

**Stdout chính xác:**

~~~text
Preserved contract compatible: true
Changed defaults compatible: false
SP EntityID preserved: true
ACS preserved: true
IdP issuer preserved: true
Request signing policy preserved: true
Approved roles: [ROLE_REPORT_VIEWER]
Unapproved admin becomes ROLE_ADMIN: false
Missing approved group grants role: false
New ACS needs partner update: true
~~~

**Giải thích:**
- `preserved` giữ các trường contract trong ví dụ nên kiểm bằng chuỗi nhận `true`.
- `changed` đổi EntityID, ACS và tắt required signing nên **không tương thích** với contract cũ nếu IdP chưa được update.
- `NameIDFormat` và group attribute URI được giữ, tránh thay đổi local identity mapping ngầm.
- `Domain Admins` không được cấp app `ROLE_ADMIN`.
- Khi không có approved group thì không được cấp quyền ứng dụng.
- Đổi ACS cần thay partner registration hoặc triển khai endpoint compatibility có kiểm chứng.

**Cảnh báo:** `sameTrustContract` chỉ so **6 trường minh họa** và không kiểm certificates, signature, encryption, replay, metadata, SLO, cookie, tenant, profile/binding support hay actual signed assertions. Trong một migration thật, **contract bảng phần 4 rộng hơn nhiều**, cần E2E security testing. Không dùng hàm này làm SAML authorization/validation logic.

## 22. Kế hoạch chuyển đổi theo giai đoạn

### Giai đoạn 0 — Discovery và baseline

- Chốt inventory IdP/SP metadata, EntityID, ACS, SLO, certs, algorithms, subjects/attributes/groups/tenants.
- Chụp **test-only** baseline behavior từ ứng dụng cũ: SP-initiated/IdP-initiated login, logout, role mapping, error behavior, multi-IdP và proxy.
- Ghi dependency versions, vulnerability baseline, backend services, DNS, firewall và IdP ownership.
- Đánh dấu bắt buộc vs optional features, đặc biệt Artifact/ECP/SOAP và metadata dynamic reload.

### Giai đoạn 1 — Dựng SAML2 SP mới ở môi trường cách ly

- Dùng Spring Boot/Security version được tổ chức hỗ trợ, JVM/Jakarta libraries tương thích.
- Thêm `spring-security-saml2-service-provider` và `saml2Login`, bỏ legacy extension/filter classes khỏi target app.
- Cấu hình một `RelyingPartyRegistration` với IdP test metadata và trusted verification certificate.
- Tạo SP EntityID/ACS riêng cho staging nếu tránh va chạm production IdP registration.
- Chỉ cho test identities/approved accounts vào staging, không dùng production keys.
- Kiểm HTTP response headers, no-store, TLS, CSRF và default deny routes.

### Giai đoạn 2 — Kết nối IdP, xác thực và mapping

- Cung cấp SP metadata mới cho IdP staging; verify EntityID/ACS/signature requirements.
- Test AuthnRequest HTTP-Redirect, response HTTP-POST, request correlation, conditions và response audience.
- Nếu IdP ký AuthnRequest hoặc encrypt Assertion, thêm signing/decryption `Saml2X509Credential`.
- Đọc verified NameID/attributes qua provider, map local user/authorities/tenant đúng contract.
- Test user missing optional fields, wrong tenant, disabled account, duplicate emails/multi-IdP.

### Giai đoạn 3 — SLO và các advanced requirements

- Chỉ bật `saml2Logout()` khi IdP/SP keys, endpoints và binding đã kiểm.
- Test RP-initiated và AP-initiated, invalid signature, stale session, request replay và missing correlation.
- Kiểm artifact/ECP/discovery/RequestedAuthnContext/metadata reload: feature gap phải có kết luận riêng.
- Kiểm rotation IdP signing certificate và SP decryption key.

### Giai đoạn 4 — Production-like staging

- Đi qua **cùng ingress/CDN/WAF/LB, HTTPS scheme và context path** như production.
- Test multi-pod session/shared request repository/cache, SameSite cookie và browser flows.
- Chạy regression trên Java/Spring dependency versions thật.
- Kiểm audit, SIEM, telemetry không chứa raw SAMLResponse/NameID/keys.
- Load test IdP metadata retrieval/startup behavior, key rollover và disaster recovery.

### Giai đoạn 5 — Canary và rollout

- Phối hợp IAM/IdP admin đổi metadata/ACS/cert theo change window được phê duyệt.
- Có thể dùng **SP registration riêng** (EntityID/ACS khác) cho canary nếu IdP hỗ trợ; không tự cho hai SP cùng EntityID nhận arbitrary responses.
- Định tuyến một nhóm test users/partner traffic sang SP mới bằng cấu hình đã kiểm, giữ session isolation.
- So tỷ lệ login success/failure, SAML validation reason, role mapping và logout outcome.
- Không chia một ACS URL giữa hai stacks bằng round-robin khi request correlation/store không tương thích.
- Khi đạt acceptance criteria và monitoring ổn định mới mở dần traffic.

### Giai đoạn 6 — Cutover, rollback và dọn legacy

- Thay partner metadata/redirect/ACS/SLO sang bản đã phê duyệt và xác nhận IdP effective state.
- Gỡ `spring-security-saml2-core`, XML beans/filter cũ và OpenSAML transitive overrides khỏi new app.
- Thu hồi/rotate credentials cũ theo policy khi hết overlap, không xóa quá sớm.
- Cập nhật runbooks, dashboards, dependency governance và secure cookie settings.
- Rollback phải đưa lại **cả SP deployment + IdP metadata/ACS/cert trust + session assumptions**; không chỉ redeploy JAR cũ rồi kỳ vọng IdP tự trở về.
- Audit old/new revision/actor/approver, đã deploy node nào và rollback reason.

## 23. Chiến lược “song song” đúng: không tạo hai chủ thể xác thực cho một callback

Các kiến trúc có thể chọn:

| Chiến lược | Điểm mạnh | Rủi ro/cần kiểm |
| --- | --- | --- |
| **Migrate in-place theo change window** | Ít IdP registrations, đơn giản operational | Downtime/rollback phụ thuộc partner update |
| **Parallel staging với SP EntityID mới** | Test độc lập, tránh ảnh hưởng prod | IdP phải hỗ trợ app registration khác và users test |
| **Canary với separate ACS/EntityID** | Chuyển dần traffic rõ ràng | Chọn IdP registrations đúng, session isolation |
| **SAML gateway/broker giữ external contract** | Có thể giảm số IdP changes cho nhiều apps | Tạo thêm trust boundary/ops/latency; phải audit broker |
| **Dual-stack cùng app, ACS khác nhau** | Có thể hỗ trợ chuyển từng route | Filter order, shared session, keys/correlation phức tạp; không khuyến nghị khi chưa kiểm kỹ |

**Không gửi cùng một signed SAMLResponse tới hai SP để thử shadow verification**: Assertion thường có Audience/Recipient/One-time replay conditions; một Response đã dành cho SP A không tự hợp lệ cho SP B. Với dual-run cần IdP phát responses đúng riêng từng registration, không “clone packet” để test.

## 24. Ma trận kiểm thử bảo mật và tương thích

| ID | Kịch bản | Tiêu chí PASS |
| --- | --- | --- |
| M01 | SP-initiated login với IdP staging | Redirect/AuthnRequest/POST ACS/authenticated đúng |
| M02 | EntityID cũ được bảo tồn | IdP Audience match, không unexpected entity switch |
| M03 | ACS default mới nhưng IdP vẫn dùng URL cũ | Phát hiện mismatch, không silent fallback |
| M04 | Custom legacy ACS được bật | Filter/registration/IdP/proxy đều cùng URL |
| M05 | IdP-initiated SSO | Chỉ accept nếu policy approved, validate replay/issuer |
| M06 | InResponseTo sai | Reject SP-initiated response |
| M07 | Signed Assertion bằng cert được trust | Accept nếu mọi condition khác đúng |
| M08 | Assertion ký bằng unknown cert | Reject, không trust-all |
| M09 | Response không ký, Assertion không ký | Reject |
| M10 | Assertion expired/NotBefore future | Reject theo clock skew nhỏ được phê duyệt |
| M11 | Audience, Recipient hoặc Destination sai | Reject, không disable validators |
| M12 | SAMLResponse replay cùng Assertion ID | Reject theo replay/correlation policy |
| M13 | EncryptedAssertion đúng SP decrypt key | Decrypt + verify rồi authenticate |
| M14 | EncryptedAssertion sai SP key | Reject, không fallback plaintext |
| M15 | EncryptedAttribute/EncryptedID | Decrypt đúng thứ tự sau checks liên quan |
| M16 | Signed AuthnRequest required nhưng SP không ký | Fail rõ, thêm signing credential |
| M17 | IdP signing rollover A→B | Old/new trust overlap đúng window |
| M18 | SP decryption key rollover A→B | Các pods dùng cùng allowed keysets |
| M19 | Missing optional displayName/email | Không throw NPE hoặc account-link sai |
| M20 | Missing required tenant | Deny authorization/login theo contract |
| M21 | Groups multi-value | Xét đúng list, allowlist chính xác |
| M22 | AD Domain Admins nhưng không có app group | Không cấp ROLE_ADMIN |
| M23 | Hai IdPs có cùng email/username | Không gộp nhầm user/tenant |
| M24 | IdP metadata unavailable at startup | Fail/recover theo explicit design, không silent trust bypass |
| M25 | IdP metadata signed/PKIX invalid | Reject theo trust policy |
| M26 | Proxy Forwarded spoofing | Không tạo ACS/EntityID từ untrusted headers |
| M27 | Browser cross-site POST và SameSite | Request correlation ổn định, không CSRF downgrade |
| M28 | Callback đến pod khác | Request repository/session shared đúng |
| M29 | Login thất bại rồi retry | No stale AuthnRequest/RelayState confusion |
| M30 | RP-initiated SLO | Signed LogoutRequest, valid response/correlation |
| M31 | AP-initiated SLO invalid signature | Reject, không logout tùy tiện |
| M32 | Local logout only | Không báo global SLO completed |
| M33 | Custom legacy SLO URL | Match filter, registration, metadata/IdP |
| M34 | XML Signature Wrapping/XXE/oversized XML | Provider/parser reject theo security policy |
| M35 | Artifact/ECP/PAOS use case cũ | Gap được test/giải quyết, không silently drop |
| M36 | Browser history/ingress logs | Không raw SAMLResponse/keys/PII trong logs |
| M37 | Role mapping ở Spring 6/7 | Compatibility với principal accessor được kiểm |
| M38 | Đổi SAML config revision giữa rollout | Detect per-node drift/audit |
| M39 | Test switchback/rollback | IdP+SP metadata/trust khôi phục có chứng cứ |
| M40 | OIDC/API dùng chung app | SecurityFilterChains không bắt nhầm routes |
| M41 | Endpoint metadata mới | EntityID, ACS, key descriptors công bố đúng |
| M42 | Test auth thất bại vì cert vs thiếu quyền | Logs phân biệt protocol failure và local authorization |
| M43 | CAS/OIDC coexistence (nếu có) | Chọn correct authentication manager, tránh filter conflicts |
| M44 | Negative HTTP GET SAMLResponse | Không bypass intended HTTP POST binding/security checks |
| M45 | Session/logout sau nâng cấp | Không giữ session legacy tùy tiện hoặc tạo fixation |

**Yêu cầu fixture:** Để thử time/audience/signature, phải tạo một **signed SAMLResponse hợp lệ** từ IdP test hoặc OpenSAML signer lab rồi sửa điều kiện trước khi ký; sửa XML sau khi ký chỉ làm signature invalid, không kiểm được validator khác. Không đưa production signing keys/credentials vào CI.

## 25. Những lỗi phổ biến khi chuyển và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| 404 tại `/saml/SSO` | Legacy ACS còn trên IdP, new filter chỉ nghe default URL | Đổi IdP ACS hoặc custom filter + registration |
| `AudienceRestriction` mismatch | SP EntityID mặc định mới khác cũ | Thống nhất EntityID/IdP registration |
| `Destination` mismatch | Reverse proxy HTTPS/host/path sai | Fix trusted forwarded headers/public ACS |
| `Signature validation failed` | Wrong IdP verification cert, metadata rollover | Kiểm trusted signing cert, không disable signature |
| `Could not decrypt` | Thiếu/sai SP private decryption credential | Add đúng keypair và encryption cert |
| `No matching AuthnRequest` | Session lost, RelayState/ACS mismatch, load balancing | Kiểm request repository/cookie/session |
| CSRF 403 trên ACS | Custom matcher/CSRF/cross-site POST cookie issue | Test filter chain và exception scope đúng |
| 302 login loop | RegistrationId, saved request, cookies/IdP metadata issue | Trace flow theo stage, không log raw response |
| Login succeeded nhưng user anonymous in controller | Filter chain order/SecurityContext/session policy sai | Đảm bảo saml2Login đúng chain |
| Principal cast exception | `Saml2AuthenticatedPrincipal`/7 accessor mismatch | Refactor theo actual resolved API |
| Groups chỉ nhận một giá trị | `getFirstAttribute` dùng sai | Use list + cardinality/allowlist |
| User cũ bị tạo local account mới | NameID format/EntityID link key thay đổi | Explicit account migration/link audit |
| SLO chỉ xóa local session | Chưa bật/config SLO và signing key | Bổ sung SLO test theo profile |
| IdP-initiated login fail | Unsolicited response không được trust/handled | Decide policy, không bỏ replay/audience |
| Một pod hoạt động, pod khác fail | Inconsistent keys/registration/session store | Align deployment snapshots and secrets |
| Metadata refresh không xảy ra | Repo chỉ đọc metadata lúc startup | Xây refresh strategy/version audit |
| Boot startup fail vì IdP offline | Metadata URI unavailable | Approved static metadata/caching/retries |
| Java `ClassNotFoundException` | Extension/OpenSAML javax/jakarta conflict | Fix BOM/transitive dependency tree |
| Legacy Artifact/ECP không chạy | Feature parity chưa được xác minh | Gateway/alternative/profile migration |
| SAMLResponse xuất hiện trong log | Debug filter/ingress body capture | Redact/stop capture; incident response nếu thật |
| Private key bị lộ trong test artifacts | Vận hành secrets không chuẩn | Revoke/rotate, purge và secure key storage |

**Đừng giảm kiểm chữ ký, audience, recipient, thời gian và replay chỉ để vượt một lỗi migration.** Một migration chỉ thực sự hoàn tất khi **trạng thái an ninh tối thiểu không kém hệ thống cũ** và các behavior nghiệp vụ được IdP/ứng dụng xác nhận.

## 26. Tiêu chí nghiệm thu trước khi cutover

**Giao thức & trust:**
- SP metadata mới được IdP phê duyệt và import đúng.
- EntityID/ACS/binding đúng, AuthnRequest signing requirement, verification/decryption keys đúng.
- Signature/issuer/audience/recipient/NotBefore/NotOnOrAfter/InResponseTo/replay tests PASS.
- Trusted certificate rotation và metadata refresh strategy có ownership.

**Identity & quyền:**
- Stable identity link đúng cho từng IdP/tenant; không account collision.
- Local user disabled/revoked bị từ chối theo policy.
- Missing/empty/multi-valued SAML attributes được xử lý đúng.
- Không tự cấp role admin từ raw IdP groups; authorization negative tests PASS.

**Vận hành & SLO:**
- Login và logout có telemetry/audit không rò credentials.
- SLO đã kiểm với IdP nếu là yêu cầu; local vs remote completion được phân biệt.
- Cluster/session/cookie/reverse-proxy/SameSite tested trên browser thực.
- Có rollback thực thi được, bao gồm IdP metadata/registered ACS/key and app deployment.
- Dependency tree không còn extension/OpenSAML collision, đã chạy security scanning.
- Feature-gap inventory đã có disposition cho Artifact/ECP/SOAP và custom behavior.
- Change management partner có approval/change ticket, canary, monitoring và post-cutover review.

Không chấp nhận dấu **“migration done”** chỉ vì màn hình login IdP xuất hiện; điều đó chứng minh tối đa **AuthnRequest start**, chưa chứng minh Response được verify, đúng local user, đúng quyền và logout an toàn.

## 27. Checklist công việc theo thứ tự dễ áp dụng

1. Xác định app là **SP**; nếu dự án tự làm IdP hoặc ECP/Artifact thì xử lý feature gap riêng.
2. Đọc legacy XML/metadata/keystore config, chụp hợp đồng external SAML chính xác.
3. Khóa dependency versions Java, Spring Boot/Security, OpenSAML theo supported BOM.
4. Gỡ extension và filter cũ **khỏi target runtime**, không cùng lúc nghe cùng ACS.
5. Thêm `spring-security-saml2-service-provider`; cấu hình `SecurityFilterChain.saml2Login`.
6. Tạo `RelyingPartyRegistration` theo approved IdP metadata và entity IDs.
7. Sinh/kiểm SP metadata bằng `saml2Metadata`; compare EntityID, ACS, certs, binding với legacy.
8. Cung cấp SP signing/decryption credentials khi IdP policy cần, quản lý secrets.
9. Quyết định giữ hay đổi URLs; cập nhật **filter + registration + IdP + proxy** nhất quán.
10. Tái hiện request correlation, state, session timeout, cookie SameSite và proxy URLs.
11. Chuyển user details/role mapping sang verified attributes, strict tenant/identity policy.
12. Test SP-initiated login, IdP-initiated khi được duyệt, SLO RP/AP khi được hỗ trợ.
13. Kiểm các profile/binding ngoài browser SSO cũ; không bỏ ngầm feature quan trọng.
14. Thực hiện negative tests signature, audience, recipient, replay, time, decryption và spoofed headers.
15. Test multi-node, metadata refresh/key rotation, WAF/APM/log redaction.
16. Canary với IdP test users/approved partner changes, đo errors theo reason/registration/node.
17. Cutover production với approval, audit config revisions và kế hoạch rollback IdP+SP.
18. Retire legacy dependency và credentials cũ sau overlap an toàn, cập nhật runbooks.

## 28. Tài liệu chính thức tham khảo

1. [Spring Security SAML Extension 1.x — Reference Documentation](https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/): `SAMLEntryPoint`, `SAMLProcessingFilter`, `MetadataGeneratorFilter`, `MetadataManager`, `KeyManager`, SLO, supported profiles và bindings của extension.
2. [Spring Security Wiki — SAML 2.0 Migration Guide (Extension → Spring Security 5.7)](https://github.com/spring-projects/spring-security/wiki/SAML-2.0-Migration-Guide): hướng dẫn patterns migration, lịch sử và những khác biệt cốt lõi.
3. [Spring Security — SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/): Spring RP/SP module hiện hành.
4. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `SecurityFilterChain`, `Saml2WebSsoAuthenticationRequestFilter`, `Saml2WebSsoAuthenticationFilter`, `RelyingPartyRegistration`.
5. [Spring Security — Producing SAML AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `/saml2/authenticate/{registrationId}`, signing, request repository và customization.
6. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): ACS, OpenSAML provider, validators, decryption, NameID và authority mapping.
7. [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `saml2Metadata`, endpoints và response resolver.
8. [Spring Security — SAML Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP SLO, signing credentials và default endpoint.
9. [Spring Security — SAML2 Migrations (Spring 7)](https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html): `Saml2ResponseAssertionAccessor`, `Saml2AssertionAuthentication`, logout behavior và GET response handling changes.
10. [Spring Boot — SAML 2.0](https://docs.spring.io/spring-boot/reference/security/saml2.html): `spring.security.saml2.relyingparty.registration`, credential properties và build repository.
11. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Assertions, Issuer, Conditions, SubjectConfirmation, attributes.
12. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Browser SSO/SLO obligations.
13. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityID, KeyDescriptor, AssertionConsumerService và SLO metadata.
14. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature validation, replay, XML signature wrapping và trust.
15. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): HTTP session, cookies, logout.
16. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu nhạy cảm trong audit/logs.
17. [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): kiểm filter chains, authentication và authorization.

**Ghi nhớ:** Spring Security SAML Extension 1.x và Spring Security SAML2 hiện hành chia sẻ **giao thức SAML 2.0**, nhưng **không chia sẻ mô hình cấu hình và APIs**. Hãy bắt đầu bằng inventory **trust contract (EntityID, ACS, issuer, certificates, conditions, subject, roles, SLO)**, xây `RelyingPartyRegistration`/`saml2Login`, xuất metadata chuẩn và thử với IdP trước khi cutover. Đặc biệt phải kiểm đồng thời **endpoint + metadata + filter mapping**, **signing/decryption keys**, **authentication vs authorization**, **SLO vs local logout** và **binding/profile gaps**; chỉ đánh dấu thành công khi positive và negative E2E tests cùng rollback đã được chứng minh.