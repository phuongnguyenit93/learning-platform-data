# Ngăn nhầm lẫn IdP, nhầm tenant và truy cập dữ liệu chéo tổ chức

## 1. Mục tiêu: nhận đúng người, đúng tổ chức, đúng tài nguyên

Một ứng dụng **Spring Security SAML2 Service Provider (SP)** có thể nhận đăng nhập từ nhiều **Identity Provider (IdP)** và phục vụ nhiều tenant (công ty, khách hàng, tổ chức). **Một SAMLResponse được ký hợp lệ không mặc nhiên cho phép người dùng truy cập dữ liệu của mọi tenant.**

Có ba loại lỗi độc lập nhưng thường xuất hiện cùng nhau:

- **IdP confusion:** ánh xạ Assertion sang sai RelyingPartyRegistration, nhầm issuer hoặc dùng signing key của IdP khác.
- **Tenant confusion:** lấy tenant từ URL, header, tên miền email hoặc claim chưa có thẩm quyền và coi đó là quyền vào tổ chức.
- **Cross-tenant data access (BOLA/IDOR):** người dùng đã đăng nhập hợp lệ nhưng service/repository/cache cho phép lấy bản ghi thuộc tổ chức khác.

Bài học này tập trung vào **Spring Security 6.x Servlet SAML 2.0 federation**, Java 17+ và ví dụ **Spring Boot 3.3.5**. Mục tiêu là bảo vệ **trust của IdP → identity binding → tenant authorization → isolation ở tầng dữ liệu**. Không viết XML Signature validator riêng hoặc tắt các kiểm tra SAML.

### Câu hỏi cần trả lời

1. SP biết một Response thuộc IdP nào mà không tin bừa issuer do browser gửi?
2. Khi IdP đã xác thực user, làm sao xác định user có membership **tenant cụ thể**?
3. Làm sao tránh nhầm khi **một IdP phục vụ nhiều tenant** hoặc nhiều IdP phát cùng email/NameID?
4. Làm sao ngăn một người ở tenant A đổi path, header hoặc document ID để lấy dữ liệu của tenant B?
5. Các đường cache, search, export, object storage, background jobs và connection pool có phải tuân tenant boundary không?
6. Cần những negative tests nào để chứng minh cách ly tổ chức ngay cả khi SAML login đã thành công?

## 2. Các định danh phải được tách biệt

| Định danh | Ví dụ | Ý nghĩa | Có chứng minh membership? |
| --- | --- | --- | --- |
| **registrationId** | corp, partner | Khóa cấu hình trong RelyingPartyRegistrationRepository. | Không. |
| **IdP entityID / Issuer** | https://idp.corp.example.org/saml | Định danh logic của IdP phát Assertion. | Không. |
| **SP entityID** | https://sp.example.org/saml2/service-provider-metadata/corp | Định danh SP, thường xuất hiện ở AudienceRestriction. | Không. |
| **ACS URL** | https://sp.example.org/login/saml2/sso/corp | Đích nhận SAMLResponse. | Không; URL không phải trust anchor. |
| **NameID** | opaque-user-7 | Định danh subject trong Assertion, có format và lifecycle riêng. | Không. |
| **stable subject** | employeeId=EMP-041 | Claim do IdP cấp và được thống nhất để liên kết account. | Không tự động; phải ràng buộc đúng issuer và account. |
| **tenantId** | corp, partner | Namespace của quyền, dữ liệu và tổ chức. | Không; client chỉ chọn mục tiêu. |
| **resource ID** | DOC-001 | Mã tài liệu/hóa đơn. | Không; ID khó đoán không thay permission. |

**registrationId không phải IdP entityID và không phải tenantId.** Có thể có registrationId **corp** trỏ đến một IdP dùng chung cho nhiều tenant hoặc hai registration cùng IdP issuer nhưng khác SP entityID/ACS. Khi ấy không được tự đồng nhất issuer với tenant.

**NameID/email không được mặc định là global account key.** Một IdP có thể sử dụng NameID transient, email có thể thay đổi hoặc tái cấp, hai IdP có thể phát cùng chuỗi subject. Một khóa account an toàn thường cần **(IdP issuer, stable subject)** rồi liên kết đến **internal account ID** thông qua bảng server-side đã được phê duyệt.

## 3. Threat model: attacker có SAML login hợp lệ

Giả sử attacker có tài khoản hợp lệ ở **Partner IdP**; họ đăng nhập vào SP, nhận HttpSession và gọi API:

~~~text
GET /orgs/partner/docs/DOC-001   -> dữ liệu Partner hợp lệ
GET /orgs/corp/docs/DOC-001      -> thay tenant ở path
X-Tenant-ID: corp                -> giả header
GET /api/docs/DOC-CORP-SECRET    -> truy cập trực tiếp ID biết được
POST /api/docs {"tenantId":"corp", "title":"..."}
~~~

Attacker không cần có private signing key của Corp IdP nếu ứng dụng sai ở **tenant authorization** hoặc **data access**.

Sơ đồ đúng:

~~~text
SAMLResponse từ browser
   |
   v
Spring Security/OpenSAML kiểm:
   - đúng registration, IdP issuer, public signing key
   - Response/Assertion signature
   - Audience, Destination, Recipient
   - Time, InResponseTo, subject confirmation, replay
   |
   v
Authenticated Saml2AuthenticatedPrincipal
   |
   v
Server-side identity binding:
   (verified IdP entityID, stable subject) -> localAccount
   |
   v
Tenant authorization:
   IdP được phép đại diện tenant?
   User có active membership tenant?
   User có quyền operation trên object?
   |
   v
Data boundary:
   query WHERE tenant_id = authorizedTenant
   cache/search/storage/job dùng verified tenant context
~~~

**SAML authentication thành công là điều kiện cần, không phải điều kiện đủ cho quyền dữ liệu.**

## 4. Chống nhầm IdP ở bước SAML authentication

Ví dụ hai RelyingPartyRegistration:

~~~text
registrationId: corp
  IdP entityID: https://idp.corp.example.org/saml
  IdP verification certs: public signing keys của Corp IdP
  SP entityID: https://sp.example.org/saml2/service-provider-metadata/corp
  ACS: https://sp.example.org/login/saml2/sso/corp

registrationId: partner
  IdP entityID: https://idp.partner.example.org/saml
  IdP verification certs: public signing keys của Partner IdP
  SP entityID: https://sp.example.org/saml2/service-provider-metadata/partner
  ACS: https://sp.example.org/login/saml2/sso/partner
~~~

Một attacker có thể POST SAMLResponse Partner vào **/login/saml2/sso/corp**. Chữ **corp** trong URL chỉ là gợi ý định tuyến; Spring Security phải xác minh Response bằng policy/verification keys của Corp, đúng issuer, audience và ACS. Bản tin của Partner phải **bị từ chối** nếu không đáp ứng các ràng buộc.

### 4.1. AuthnRequest đã lưu và lựa chọn registration

Trong **SP-initiated login**:

~~~text
GET /saml2/authenticate/corp
  -> Spring tạo AuthnRequest ID=_r123
  -> HttpSession lưu pending AuthnRequest và registration
  -> browser sang Corp IdP
  -> browser POST SAMLResponse về ACS
  -> converter tìm request đã lưu / registrationId
  -> provider kiểm Response.InResponseTo=_r123
  -> signature + Issuer + Audience + Recipient + Destination + time...
~~~

Trong Spring Security Servlet, **HttpSessionSaml2AuthenticationRequestRepository** là repository mặc định phổ biến cho pending AuthnRequest. Nếu dùng nhiều SP node cần sticky session phù hợp hoặc shared session store để callback tìm được request; **không bỏ InResponseTo** khi bị mất session.

### 4.2. Issuer fallback không phải bằng chứng

Với ACS không chứa registrationId hoặc thiếu saved AuthnRequest, Spring Security có thể tra registration bằng **Response.Issuer**. Nhưng **Issuer từ Response chưa được kiểm chữ ký tại thời điểm lookup**, nên chỉ là **gợi ý chọn ứng viên trust configuration**.

Nếu hai registration **corp-vn** và **corp-sg** có **cùng IdP issuer** nhưng khác SP entityID/ACS/tenant, chỉ dùng issuer không thể chọn duy nhất. Cần pending request context, ACS/registrationId rõ hoặc custom resolver có policy an toàn. **Không chọn registration đầu tiên** rồi bỏ validation để cho login.

**IdP-initiated SSO** không có AuthnRequest gốc, nên cần chính sách riêng cho unsolicited response, chống login CSRF/replay và giải quyết issuer/tenant ambiguity. Nếu không cần IdP-initiated, có thể chỉ cho SP-initiated flow.

### 4.3. Những kiểm tra SAML không được hạ mức

| Kiểm tra | Lỗi có thể xảy ra nếu bỏ |
| --- | --- |
| **Trusted IdP metadata và entityID** | Tự tin certificate/SSO URL của IdP lạ. |
| **XML Signature của Response/Assertion** | Chấp nhận dữ liệu tự ký/bị sửa. |
| **Issuer khớp registration** | Nhầm Partner thành Corp. |
| **AudienceRestriction** | Nhận Assertion cấp cho SP khác. |
| **Response.Destination** | Nhận Response gửi sai endpoint. |
| **SubjectConfirmationData.Recipient** | Bearer Assertion dành cho ACS khác được chấp nhận. |
| **InResponseTo nếu SP-initiated** | Login CSRF, gắn Response sai browser/request. |
| **NotBefore/NotOnOrAfter** | Chấp nhận Assertion quá hạn. |
| **Replay/one-time policy** | Tái sử dụng Response đã tiêu thụ. |
| **SAML encryption, nếu dùng** | Không giải mã an toàn trước khi dùng dữ liệu. |

Không tin ds:KeyInfo trong bản tin để tự cấp trust cho certificate mới. Verification key phải lấy từ **registration/metadata đã chấp nhận**, không phải từ message chưa xác minh.

## 5. Chống nhầm tenant bằng policy được máy chủ quản lý

Thiết kế một registry:

| registrationId | IdP issuer được phê duyệt | Tenant IdP được quyền đại diện | Stable subject claim |
| --- | --- | --- | --- |
| corp | https://idp.corp.example.org/saml | corp | employeeId |
| partner | https://idp.partner.example.org/saml | partner | externalSubjectId |
| shared-broker | https://broker.example.org/saml | corp, partner nếu đã phê duyệt | immutableSubject |

Ngay cả **shared-broker** có quyền phát danh tính cho hai tenant cũng không tự làm mọi user broker thành member cả hai. Phải có **active tenant membership per user** và role/action của từng tenant.

### Bảng dữ liệu nội bộ gợi ý

~~~text
identity_binding:
  idp_entity_id
  stable_subject
  local_account_id
  status
  UNIQUE(idp_entity_id, stable_subject)

tenant_membership:
  local_account_id
  tenant_id
  status(active/revoked)
  scoped_permissions
  membership_version

tenant_resource:
  tenant_id
  resource_id
  owner_id
  payload
~~~

Sau SAML authentication, thực hiện lần lượt:

1. Xác nhận registration và IdP issuer thực đã được **trusted SAML provider** kiểm.
2. Đọc stable subject từ **Saml2AuthenticatedPrincipal.getAttributes()** theo Attribute.Name đã thỏa thuận; **đúng một giá trị**, đúng kiểu, không blank.
3. Tìm localAccount bằng **(IdP issuer, stable subject)**, không bằng email một mình.
4. Kiểm IdP này được phép đại diện **requestedTenant**.
5. Kiểm localAccount active, có membership active tại tenant và quyền trên operation/resource.
6. Chỉ sau đó tạo **authorizedTenant** cho service/repository/cache.
7. Nếu bất kỳ bước nào mâu thuẫn, **deny by default**, không dùng tenant hoặc role mặc định rộng.

### Signed tenant claim có đủ không?

Một IdP có thể phát:

~~~xml
<saml:Attribute xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                Name="tenantId">
  <saml:AttributeValue>corp</saml:AttributeValue>
</saml:Attribute>
~~~

Chữ ký chỉ chứng minh claim đến từ IdP. Nếu Partner IdP không có thẩm quyền phát membership Corp, giá trị **corp** phải bị policy chặn. Nếu IdP được ủy quyền cho nhiều tenant, còn cần xác minh **subject này có membership đúng tenant**.

Không mặc định lấy tenant từ **email domain**, **NameID**, **group=admin**, hoặc **X-Tenant-ID** do client gửi. Các nguồn đó có thể dùng làm selector/hint nếu policy quy định, không thay quyết định server.

## 6. Tenant selector và session: không để hai tab trộn tổ chức

Ứng dụng có thể có:

~~~text
/orgs/corp/docs/DOC-001
/orgs/partner/docs/DOC-001
~~~

tenantId trong URL là **đích mà caller yêu cầu**, phải được kiểm membership mỗi request. Một số rủi ro:

- Lưu **currentTenant** global trong HttpSession khiến tab A đang ở Corp vô tình bị tab B chuyển sang Partner.
- Session login IdP khác nhưng ứng dụng giữ roles/tenant cũ.
- Membership đã bị thu hồi nhưng cache quyền/session chưa hết.
- Dùng tenantId từ header/path để đặt database RLS session variable trước khi check user.
- Cho một user có role **ADMIN** ở Partner thành platform ADMIN toàn bộ ứng dụng.

Nên tách **tenant selection**, **tenant authorization** và **data operation**. Đổi tenant cần kiểm lại membership và scoped roles; session có thể giữ UI preference, nhưng không thay server-side kiểm quyền. Nếu identity thực sự đổi IdP, làm mới SecurityContext và áp dụng session fixation/cookie policy phù hợp.

### Account linking/JIT provisioning

Nếu user lần đầu đăng nhập, ứng dụng có thể tạo account (JIT), nhưng:

- IdP và tenant phải đã onboarding/allowlist.
- Không tự hợp nhất hai account chỉ vì email giống nhau.
- Không tự tạo membership ADMIN từ group lạ trong SAML.
- Phải có quy trình invitation/approval, lifecycle, deprovisioning và audit.
- Stable subject có thể được IdP tái cấp hoặc đổi; phải có migration policy.
- Cross-IdP account linking chỉ qua quy trình có thẩm quyền và được ghi nhận, không tự nối theo displayName.

## 7. Truy cập dữ liệu: chống BOLA/IDOR ở tầng service

**Anti-pattern:**

~~~sql
SELECT id, title, body
FROM documents
WHERE id = :documentId;
~~~

Query có thể an toàn SQL injection nhưng vẫn lộ tài liệu tenant khác. **Resource ID khó đoán, kể cả UUID, không thay authorization**.

**Hướng đúng:**

~~~sql
SELECT id, title, body
FROM documents
WHERE tenant_id = :authorizedTenant
  AND id = :documentId;
~~~

**authorizedTenant** phải đến từ principal đã xác thực và membership/permission server-side, không đưa thẳng path hoặc header vào query nếu chưa kiểm.

Cả write operations phải có scope:

~~~sql
UPDATE documents
SET title = :title
WHERE tenant_id = :authorizedTenant AND id = :documentId;

DELETE FROM documents
WHERE tenant_id = :authorizedTenant AND id = :documentId;
~~~

Với INSERT, gán tenant_id từ **verified tenant context**; không cho client gán tenantId của tổ chức khác một cách tùy tiện. Khi chuyển resource giữa tenants cần operation đặc quyền tách biệt, có audit.

**Controller check một lần là chưa đủ:** các đường batch, export, search, GraphQL, background và internal service cũng có thể gọi repository. Dùng service/data-access boundary bảo vệ mọi entry point. Có thể bổ sung database row-level security làm defense in depth.

### 403 hay 404?

- User không có quyền vào requested tenant: thường **403 Forbidden**.
- User có quyền tenant nhưng documentId không tồn tại trong tenant đó: **404 Not Found**, không tiết lộ “tài liệu này thật ra ở tenant khác”.
- Tùy chính sách có thể trả 404 để che existence; nhất quán response body, counts, logs và timing để hạn chế side channel.

## 8. Java 17 thuần: mô phỏng trust, tenant, document

Ví dụ **TenantBoundaryDemo.java** chạy không cần Spring/IdP/DB. Đối tượng **VerifiedLogin** giả định đã qua SAML signature/issuer/audience validation trước khi được tạo. **Tuyệt đối không dựng VerifiedLogin từ header hay XML chưa xác thực trong production.**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;

public class TenantBoundaryDemo {
    record VerifiedLogin(String registration, String issuer, String subject) {}
    record Registration(String issuer, Set<String> tenants) {}
    record Identity(String issuer, String subject) {}
    record Document(String tenant, String id, String title) {}

    static final Map<String, Registration> REG = Map.of(
        "corp", new Registration("https://idp.corp.example.org/saml", Set.of("corp")),
        "partner", new Registration("https://idp.partner.example.org/saml", Set.of("partner"))
    );

    static final Map<Identity, Set<String>> MEMBERS = Map.of(
        new Identity("https://idp.corp.example.org/saml", "EMP-041"), Set.of("corp"),
        new Identity("https://idp.partner.example.org/saml", "P-007"), Set.of("partner")
    );

    static final List<Document> DOCUMENTS = List.of(
        new Document("corp", "DOC-001", "Corp report"),
        new Document("partner", "DOC-001", "Partner report"),
        new Document("partner", "DOC-002", "Partner confidential")
    );

    static String read(VerifiedLogin login, String tenant, String id) {
        Registration policy = REG.get(login.registration());
        if (policy == null || !policy.issuer().equals(login.issuer())) {
            throw new SecurityException("IDP_MISMATCH");
        }
        if (!policy.tenants().contains(tenant)) {
            throw new SecurityException("TENANT_DENIED");
        }
        Identity key = new Identity(login.issuer(), login.subject());
        if (!MEMBERS.getOrDefault(key, Set.of()).contains(tenant)) {
            throw new SecurityException("NO_MEMBERSHIP");
        }
        return DOCUMENTS.stream()
            .filter(d -> d.tenant().equals(tenant))
            .filter(d -> d.id().equals(id))
            .findFirst()
            .orElseThrow(() -> new SecurityException("DOCUMENT_NOT_FOUND"))
            .title();
    }

    static void show(String label, Supplier<String> operation) {
        try {
            System.out.println(label + ": " + operation.get());
        }
        catch (SecurityException ex) {
            System.out.println(label + ": DENY " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        VerifiedLogin corp = new VerifiedLogin(
            "corp", "https://idp.corp.example.org/saml", "EMP-041");
        VerifiedLogin partner = new VerifiedLogin(
            "partner", "https://idp.partner.example.org/saml", "P-007");
        VerifiedLogin wrong = new VerifiedLogin(
            "corp", "https://idp.partner.example.org/saml", "EMP-041");

        show("corp/corp", () -> read(corp, "corp", "DOC-001"));
        show("corp/partner", () -> read(corp, "partner", "DOC-001"));
        show("partner/partner", () -> read(partner, "partner", "DOC-001"));
        show("wrong issuer", () -> read(wrong, "corp", "DOC-001"));
        show("corp probes partner id", () -> read(corp, "corp", "DOC-002"));
    }
}
~~~

Biên dịch và chạy JDK 17+:

~~~bash
javac TenantBoundaryDemo.java
java TenantBoundaryDemo
~~~

**stdout chính xác:**

~~~text
corp/corp: Corp report
corp/partner: DENY TENANT_DENIED
partner/partner: Partner report
wrong issuer: DENY IDP_MISMATCH
corp probes partner id: DENY DOCUMENT_NOT_FOUND
~~~

Cần chú ý:

1. Corp và Partner đều có **DOC-001**, nhưng lookup theo **tenant+id** trả đúng tài liệu mỗi tổ chức.
2. User Corp đổi tenant=partner bị chặn dù đã đăng nhập.
3. Registration corp không được gán issuer Partner.
4. Corp biết ID riêng của Partner không thể tra cứu qua tenant Corp.
5. Membership là server-side; IdP đã ký không tự cấp membership.
6. Đây là demo authorization, **không thay Spring Security/OpenSAML**, không tự xử lý SAML Response.

## 9. Spring Boot 3.3.5: SP hai IdP và tenant-scoped API

Mẫu này mô tả hai registration **corp/partner**, dùng **IdP metadata thật** và bản ghi membership/tài liệu trong memory chỉ để học. Khi triển khai thực phải thay bằng hệ thống identity/membership và repository đã bảo vệ, mọi tài liệu thuộc tenant cụ thể.

### 9.1. Maven — pom.xml

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
    <artifactId>saml-tenant-isolation</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
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

Maven XML có một xmlns:xsi và cặp namespace/XSD đúng trong xsi:schemaLocation. Các dependencies thuộc họ Boot 3.3/Security 6.x, JDK 17; cần IdP sandbox thật để hoàn tất SSO.

### 9.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "${CORP_IDP_METADATA_URI}"
          partner:
            assertingparty:
              metadata-uri: "${PARTNER_IDP_METADATA_URI}"

server:
  port: 8080
~~~

Hai metadata-uri là URL IdP **đã được tổ chức phê duyệt**. Corp IdP dự kiến có entityID **https://idp.corp.example.org/saml** và Partner IdP dự kiến có entityID **https://idp.partner.example.org/saml**. Nếu issuer thực tế khác, phải chỉnh registry policy qua onboarding, không tự suy issuer từ hostname/email. SP entityID/ACS phải đăng ký tại cả hai IdP.

### 9.3. Main class

**src/main/java/com/example/samltenant/SamlTenantApplication.java**

~~~java
package com.example.samltenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlTenantApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlTenantApplication.class, args);
    }
}
~~~

### 9.4. SecurityFilterChain

**src/main/java/com/example/samltenant/SecurityConfig.java**

~~~java
package com.example.samltenant;

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
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**anyRequest().authenticated()** chỉ buộc user đã đăng nhập; các API dưới vẫn cần **tenant authorization**. Nếu thiết kế dùng @PreAuthorize ở service thì phải bật **@EnableMethodSecurity**; Spring Security không tự kích hoạt method security chỉ vì thêm starter.

### 9.5. TenantAccessService

**src/main/java/com/example/samltenant/TenantAccessService.java**

~~~java
package com.example.samltenant;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class TenantAccessService {
    record Policy(String expectedIssuer, String subjectClaim,
                  Set<String> allowedTenants) {}
    record Identity(String issuer, String stableSubject) {}

    private final RelyingPartyRegistrationRepository registrations;

    // Hợp đồng IdP -> tenant được tổ chức phê duyệt.
    private final Map<String, Policy> policies = Map.of(
        "corp", new Policy(
            "https://idp.corp.example.org/saml", "employeeId", Set.of("corp")),
        "partner", new Policy(
            "https://idp.partner.example.org/saml",
            "externalSubjectId", Set.of("partner"))
    );

    // Bảng membership giả lập; production cần DB với status/roles/expiry.
    private final Map<Identity, Set<String>> memberships = Map.of(
        new Identity("https://idp.corp.example.org/saml", "EMP-041"),
        Set.of("corp"),
        new Identity("https://idp.partner.example.org/saml", "P-007"),
        Set.of("partner")
    );

    public TenantAccessService(RelyingPartyRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String authorize(Authentication auth, String tenantId) {
        if (auth == null || !auth.isAuthenticated()
                || !(auth.getPrincipal() instanceof Saml2AuthenticatedPrincipal p)) {
            throw new AccessDeniedException("SAML login required");
        }

        String registrationId = p.getRelyingPartyRegistrationId();
        Policy policy = policies.get(registrationId);
        if (policy == null || !policy.allowedTenants().contains(tenantId)) {
            throw new AccessDeniedException("Tenant not allowed");
        }

        RelyingPartyRegistration registration =
                registrations.findByRegistrationId(registrationId);

        if (registration == null || !policy.expectedIssuer().equals(
                registration.getAssertingPartyDetails().getEntityId())) {
            throw new AccessDeniedException("Unapproved IdP");
        }

        List<Object> values = p.getAttributes().get(policy.subjectClaim());
        if (values == null || values.size() != 1
                || !(values.get(0) instanceof String stableSubject)
                || stableSubject.isBlank()) {
            throw new AccessDeniedException("Invalid stable subject");
        }

        Identity identity = new Identity(policy.expectedIssuer(), stableSubject);
        if (!memberships.getOrDefault(identity, Set.of()).contains(tenantId)) {
            throw new AccessDeniedException("No tenant membership");
        }

        return tenantId;
    }
}
~~~

**Đánh giá bảo mật:**

- **getRelyingPartyRegistrationId()** trên principal đã được Spring SAML provider xác thực, không phải một query parameter do user tự chọn.
- **getAssertingPartyDetails().getEntityId()** xác nhận registration được cấu hình đúng IdP entityID của policy server; chính OpenSAML provider vẫn phải xác minh Response.Issuer và signature thực.
- Stable subject claim là đúng một String không blank. Không dùng email/NameID mặc định khi thiếu claim; không lấy phần tử đầu nếu đa trị.
- Quyền tenant được quyết định từ **registration allowlist + membership nội bộ**, không chỉ signed claim.
- Production cần thêm account active, tenant status, role/action và permission version; demo không đồng nghĩa mọi user của Corp IdP được quyền corp.
- Với một IdP được phép đại diện nhiều tenant, thay Set allowedTenants theo contract nhưng vẫn kiểm **membership từng user**.

### 9.6. DocumentService với tenant-scoped lookup

**src/main/java/com/example/samltenant/DocumentService.java**

~~~java
package com.example.samltenant;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    public record DocumentView(String id, String title) {}
    record Key(String tenantId, String documentId) {}

    private final TenantAccessService access;

    private final Map<Key, DocumentView> documents = Map.of(
        new Key("corp", "DOC-001"),
        new DocumentView("DOC-001", "Corp report"),
        new Key("partner", "DOC-001"),
        new DocumentView("DOC-001", "Partner report"),
        new Key("partner", "DOC-002"),
        new DocumentView("DOC-002", "Partner confidential")
    );

    public DocumentService(TenantAccessService access) {
        this.access = access;
    }

    public DocumentView read(Authentication auth,
                             String tenantId, String documentId) {
        String authorizedTenant = access.authorize(auth, tenantId);
        DocumentView document = documents.get(
                new Key(authorizedTenant, documentId));
        if (document == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
        }
        return document;
    }
}
~~~

Lookup theo **tenantId+documentId**, không tìm toàn bộ dataset rồi mới lọc. Nếu thay Map bằng database, repository phải có predicate **WHERE tenant_id=:authorizedTenant AND document_id=:id**, và các đường list/search/export/write cũng đi qua boundary tương đương.

### 9.7. TenantController

**src/main/java/com/example/samltenant/TenantController.java**

~~~java
package com.example.samltenant;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TenantController {
    private final DocumentService documents;

    public TenantController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/")
    public String home() {
        return "SAML tenant isolation ready";
    }

    @GetMapping("/orgs/{tenantId}/docs/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable String tenantId,
            @PathVariable String documentId,
            Authentication authentication) {
        return documents.read(authentication, tenantId, documentId);
    }
}
~~~

Controller nhận tenantId từ path **chỉ để biết caller yêu cầu tenant nào**. Service kiểm quyền rồi mới lookup. Các API khác cũng phải dùng cùng boundary, không chỉ một controller GET.

### 9.8. Chạy và xác nhận

Cấu hình IdP metadata và SP entityID/ACS thật, IdP release đúng employeeId/externalSubjectId, chạy:

~~~bash
mvn spring-boot:run
~~~

- **GET http://localhost:8080/** trả **SAML tenant isolation ready**.
- **GET /saml2/authenticate/corp** bắt đầu SSO với Corp; **/saml2/authenticate/partner** với Partner.
- **GET /saml2/metadata/corp** và **/saml2/metadata/partner** xuất SPSSODescriptor theo registration.
- Với Corp login hợp lệ employeeId=EMP-041, **GET /orgs/corp/docs/DOC-001** trả JSON tương ứng **Corp report**.
- Corp login gọi **/orgs/partner/docs/DOC-001** bị **403**.
- Partner login externalSubjectId=P-007 gọi **/orgs/partner/docs/DOC-001** thấy **Partner report**.
- Corp gọi **/orgs/corp/docs/DOC-002** bị **404** vì document chỉ tồn tại trong Partner.
- Sai SAML signature/issuer/audience bị chặn **trước** khi DocumentService chạy; thiếu membership/stable subject bị chặn tại **TenantAccessService**.

**Không thể chứng minh SSO end-to-end với IdP giả**. Cần IdP sandbox thực tế, certificates tin cậy, ACS HTTPS public phù hợp và SAMLResponse ký đúng. Các record in-memory chỉ là dữ liệu mẫu, không dùng làm authorization store production.

## 10. PostgreSQL RLS làm phòng vệ chiều sâu

Shared database có thể có schema:

~~~sql
CREATE TABLE documents (
    tenant_id VARCHAR(100) NOT NULL,
    document_id VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (tenant_id, document_id)
);
~~~

Nếu dùng PostgreSQL, có thể thêm RLS:

~~~sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy ON documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
~~~

**Không coi đây là migration hoàn chỉnh**: cần kiểm role DB, grants, transaction boundary và connection pool. Quy tắc:

1. Chỉ đặt **app.tenant_id** từ tenant đã được server xác minh.
2. Dùng **SET LOCAL** trong transaction thay vì SET session-level có thể rò tenant khi connection pool tái sử dụng.
3. App database role không nên là superuser/BYPASSRLS; chủ bảng có thể bypass nếu không FORCE RLS, cần test thực tế.
4. Test đọc/ghi/xóa/list/count ở tất cả tenant-owned tables.
5. DB RLS không bao phủ Redis, object storage, search hoặc queue.
6. Job cross-tenant cần service principal/phạm vi quyền riêng, không dùng user role bình thường.

Nếu không dùng RLS, ít nhất phải đảm bảo mọi query có tenant scope và authorization boundary tập trung. Chọn database-per-tenant/schema-per-tenant/shared-table theo SLA, compliance và vận hành; mỗi lựa chọn vẫn cần quyền đúng tenant.

## 11. Cache, file, search và background processing

### Cache

**Sai:** cache key **document:DOC-001** có thể trả Corp report cho Partner vì ID trùng.

**Đúng hướng:**

~~~text
tenant:corp:document:DOC-001
tenant:partner:document:DOC-001
~~~

Nếu kết quả còn phụ thuộc user/permission, cache key hoặc policy cache phải tính cả những yếu tố ấy. **Kiểm authorization trước khi đọc dữ liệu cache nhạy cảm.** Membership revocation cần invalidate/TTL phù hợp.

### Object storage

~~~text
tenants/corp/docs/DOC-001.pdf
tenants/partner/docs/DOC-001.pdf
~~~

Prefix tenant không thay quyền. Trước khi phát signed download URL hoặc đọc/ghi file, kiểm user có quyền **đúng object và operation**. Chống path/key tampering, giới hạn TTL, method và chính sách bucket/IAM. Tenant admin không được dùng tài khoản storage rộng quyền của platform.

### Search / analytics

Search index, vector DB, report và warehouse phải **filter tenant ngay trong truy vấn**. Không trả toàn bộ results rồi lọc UI, vì snippet, ranking, facets, total count hoặc cached search có thể lộ dữ liệu trước khi lọc.

### Background jobs và queue

Job mang **tenant scope đã được producer xác minh** hoặc tham chiếu authorized job record. Consumer xác thực nguồn, re-authorize khi membership/role đã thay đổi, scope query và output. Dedup/retry/dead-letter và file export phải tenant-aware. Không tin một trường tenantId do caller tự nhét vào message.

### Admin/support/audit

Tenant-admin chỉ có quyền trong tenant được phê duyệt; platform-admin là vai trò riêng cần audit. Log verified tenant, internal actor ID, action và deny reason; không log raw SAMLResponse, cookie, signing key, NameID/email nhạy cảm.

## 12. Ma trận kiểm thử dương tính và âm tính

**Quan trọng:** để kiểm tenant isolation, dùng **SAMLResponse thật, hợp lệ, có chữ ký từ IdP sandbox**, sau đó cố thay URL/tenant/resource. Nếu sửa XML sau ký, signature fail quá sớm và test chưa chứng minh app authorization.

| # | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Corp login hợp lệ đọc tài liệu Corp | 200 nếu account/membership/ACL đạt. |
| 2 | Partner login hợp lệ đọc tài liệu Partner | 200 theo policy. |
| 3 | Partner Response được ký hợp lệ nhưng POST ACS corp | Từ chối vì registration/issuer/trust mismatch. |
| 4 | Assertion tự ký bằng cert attacker từ ds:KeyInfo | Từ chối unknown verification key. |
| 5 | AudienceRestriction là SP khác | Từ chối. |
| 6 | Destination/Recipient không trùng ACS | Từ chối. |
| 7 | InResponseTo sai hoặc missing trong SP-initiated | Từ chối correlation. |
| 8 | Replay Response đã sử dụng | Từ chối replay/one-time policy. |
| 9 | Shared IdP issuer map hai registrations, thiếu request context | Không chọn tùy tiện, fail closed. |
| 10 | Unsolicited response từ IdP chưa đăng ký | Từ chối. |
| 11 | Partner login thành công, đổi /orgs/partner thành /orgs/corp | 403, không lộ dữ liệu. |
| 12 | Partner thêm X-Tenant-ID: corp | Không thay tenant authorization. |
| 13 | POST JSON có tenantId của tổ chức khác | Từ chối hoặc server gán verified tenant theo contract. |
| 14 | Corp biết ID tài liệu chỉ có ở Partner | 404 trong Corp scope. |
| 15 | Corp/Partner có cùng DOC-001 | Trả nội dung riêng từng tenant. |
| 16 | IdP phát signed tenantId=corp nhưng registry không cho phép | Deny, không tin quyền tenant ngoài hợp đồng. |
| 17 | Stable subject claim thiếu/đa trị/sai kiểu | Không link account bằng fallback. |
| 18 | Hai IdP có cùng email/NameID | Không hợp nhất account tự động. |
| 19 | User có SAML login hợp lệ nhưng membership bị revoke | Deny theo current membership/revalidation. |
| 20 | Tenant-admin Partner gọi API platform hoặc Corp admin | 403, role có scope. |
| 21 | List API scope nhưng totalCount query global | Test phát hiện leakage. |
| 22 | Cache dùng documentId không tenant prefix | Test phát hiện cross-tenant collision. |
| 23 | Signed URL tới file tenant khác | Không phát URL hoặc không cho download. |
| 24 | Search index trả facet/snippet tenant khác | Fail test, cần tenant filter tại search engine. |
| 25 | Job export mang forged tenantId | Consumer từ chối nếu thiếu verified authorization. |
| 26 | Hai browser tabs đổi tenant liên tục | Mỗi request re-authorize, không dùng stale currentTenant. |
| 27 | Login lại bằng IdP khác trong cùng browser | Không giữ role/tenant identity cũ. |
| 28 | DB connection tái dùng sau request tenant khác | RLS/SET LOCAL không leak. |
| 29 | Internal service truy cập tài liệu không qua controller | Vẫn qua tenant-aware authorization boundary. |
| 30 | Platform admin được phép multi-tenant | Quyền riêng, least privilege và audit rõ. |

**Negative test thành công** khi hệ thống từ chối hoạt động không có quyền mà không hạ validation SAML hoặc tạo quyền mặc định.

## 13. Những lỗi thường gặp

| Triệu chứng | Khả năng | Hướng sửa |
| --- | --- | --- |
| **RelyingPartyRegistration not found** | registrationId hoặc ACS path không có trong repository. | Kiểm onboarding, route, metadata, không tự thêm IdP lạ. |
| **Issuer mismatch** | Response đến từ IdP khác registration. | Kiểm issuer/key, không nới policy. |
| **Invalid signature** | Metadata/key rotation sai hoặc Response bị sửa. | Cập nhật trust đúng quy trình, không bỏ verify. |
| **SAML login được nhưng tenant API trả 403** | Local membership/claim/tenant policy không đạt. | Phân biệt SAML auth success với business authorization. |
| **Hai user khác IdP thành một local account** | Key binding chỉ email/NameID. | Namespace theo IdP+stable subject. |
| **Đổi tenantId trên URL vẫn đọc được tài liệu** | Service chỉ kiểm authenticated. | Kiểm membership và query WHERE tenant_id. |
| **Export/Search rò kết quả khác tenant** | Đường data không dùng common enforcement. | Sửa service/DB/search scope. |
| **Cache lẫn Corp và Partner DOC-001** | Key thiếu tenant hoặc authorization. | Tách key, authorize trước read. |
| **RLS lẫn tenant sau connection reuse** | SET session-level chưa reset. | SET LOCAL trong transaction, test pooled connections. |
| **IdP-initiated nhầm tenant** | Issuer chung không có ngữ cảnh chọn. | Policy rõ, routing bổ sung hoặc deny unsolicited. |
| **Tenant admin trở thành platform-admin** | Role mapping không scope. | Tách tenant roles/platform roles và audit. |

## 14. Checklist production

**Federation:**

- [ ] Chỉ nhận IdP entityID và metadata/certificates đã được phê duyệt.
- [ ] Mọi Response/Assertion được kiểm signature, issuer, audience, destination, recipient, time, InResponseTo và replay.
- [ ] Issuer lookup mơ hồ không chọn ngẫu nhiên; IdP-initiated có policy riêng.
- [ ] SP entityID/ACS public HTTPS đúng từng registration.
- [ ] Stable subject claim có tên/kiểu/cardinality/lifecycle rõ.

**Authorization và data isolation:**

- [ ] Server quản lý allowlist registration/IdP → tenants.
- [ ] Account linking theo issuer+stable subject, membership active, role scoped.
- [ ] Tenant path/header/body chỉ là selector, không tự cấp quyền.
- [ ] Service/repository cưỡng chế authorizedTenant cho SELECT/INSERT/UPDATE/DELETE/list/search/export.
- [ ] DB RLS hoặc kiểm soát defense-in-depth khác được đánh giá.
- [ ] Cache, blob, queue, search, support tools và audit có tenant scope.
- [ ] Tenant-admin không có platform role tự động.
- [ ] Membership/session/permission cache có TTL và revocation policy.

**Kiểm thử/vận hành:**

- [ ] Test hai IdP, hai tenant và tài liệu cùng ID.
- [ ] Test thay tenant sau khi SAML login hợp lệ, không chỉ test signed XML sai.
- [ ] Test account collision, multi-tab, session switch, node failover, Redis/cache và IdP rotation.
- [ ] Có quy trình tenant onboarding/offboarding, revoke, migration và access review.
- [ ] Monitor cross-tenant denies mà không lộ raw Assertion/PII/secrets.

## 15. Tự kiểm tra

**1. SAMLResponse Partner ký đúng, vì sao vẫn không được đọc tài liệu Corp?**  
Vì signature xác thực nguồn IdP Partner, không chứng minh IdP ấy có quyền cấp membership Corp, user có quyền Corp hoặc tài liệu thuộc tenant được phép.

**2. registrationId=corp trên ACS URL có đủ chứng minh Response do Corp IdP phát?**  
Không. URL là routing, provider phải kiểm đúng issuer/key/audience/profile.

**3. Hai registrations có cùng IdP Issuer, không có pending AuthnRequest. Có thể chọn registration đầu tiên?**  
Không. Cần ngữ cảnh định tuyến được kiểm soát hoặc fail closed.

**4. Hai IdP có cùng employeeId. Có thể dùng employeeId làm account key toàn cầu?**  
Không, cần namespace issuer/stable subject và policy linking.

**5. Đã filter tenant ở UI, repository.findById không scope có an toàn không?**  
Không. Mọi đường đọc/ghi phải enforcement ở service/data layer.

**6. Có RLS và connection pool, tại sao cần SET LOCAL?**  
Để tenant context không sống sang transaction/request khác trên kết nối tái sử dụng.

**7. Vì sao cache key tenant-prefixed chưa đủ bảo vệ?**  
Cần kiểm quyền trước cache read; result còn có thể phụ thuộc quyền user và membership phiên.

**8. Stable subject bị thiếu nhưng IdP login hợp lệ, có nên tạo guest account chung?**  
Không nếu stable subject bắt buộc để liên kết account; phải fail closed và sửa IdP attribute release.

## 16. Tài liệu tham khảo

1. [Spring Security 6.5 — SAML Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): RelyingPartyRegistration, ACS, Response và issuer resolution.
2. [Spring Security 6.3 Javadoc — Saml2AuthenticatedPrincipal](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): getRelyingPartyRegistrationId và attribute APIs.
3. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): principal mapping và response validation.
4. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): @EnableMethodSecurity và @PreAuthorize khi enforce service-level.
5. [Spring Boot 3.3 — Security/SAML](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): multiple relying party registrations.
6. [OWASP — Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): tenant identity, membership, data isolation, cache/search/storage/queue.
7. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và kiểm quyền mọi request.
8. [OWASP — Insecure Direct Object Reference](https://community.owasp.org/attacks/insecure_direct_object_reference): resource ownership kiểm ở server.
9. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Issuer, AudienceRestriction, Conditions và signature.
10. [OASIS — SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO và request correlation.

**Kết luận:** Muốn tránh nhầm lẫn IdP, tenant và dữ liệu chéo tổ chức, phải **kiểm SAML với đúng IdP trust**, **liên kết identity và kiểm membership/role theo tenant**, rồi **scope mọi tài nguyên theo verified tenant ở tầng service/data**. Một SAMLResponse hợp lệ không bao giờ thay thế authorization.
