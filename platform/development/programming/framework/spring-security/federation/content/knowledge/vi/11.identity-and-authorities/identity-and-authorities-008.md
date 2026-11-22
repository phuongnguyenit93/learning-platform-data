# Kết hợp quyền từ IdP với quyền nghiệp vụ trong cơ sở dữ liệu nội bộ

**Module:** Spring Security – federation  
**Ngữ cảnh:** Danh tính và quyền  
**Nền tảng:** SAML 2.0 Web Browser SSO, Spring Security 6.x, Spring Boot 3.x, Java 17+.

## 1. Vì sao đăng nhập SSO thành công chưa đồng nghĩa được truy cập dữ liệu?

**Identity Provider (IdP)** xác thực người dùng và có thể phát hành thuộc tính tổ chức như nhóm, phòng ban, mã nhân viên, hình thức xác thực. **Service Provider (SP)** là ứng dụng nghiệp vụ. SP biết ai sở hữu đơn hàng, hồ sơ, khoản thanh toán; ai được phê duyệt trong hạn mức; hợp đồng nào đang hoạt động; tenant nào có quyền xem dữ liệu nào.

Ví dụ: IdP đã xác minh nhân viên có nhóm **finance-readers**, nhưng DB ứng dụng chỉ cấp quyền **READ** trên đơn hàng **42**, không cấp quyền trên đơn **43**. Nếu SP chỉ kiểm tra group IdP rồi cho truy cập mọi đơn hàng, nó đã biến thông tin tổ chức thành một đặc quyền nghiệp vụ không được cấp.

Ta cần kết hợp ba lớp:

1. **Authentication:** SAMLResponse thật sự đến từ IdP đáng tin và dành cho đúng SP? Người dùng/subject là ai?
2. **Eligibility:** Thuộc tính IdP đã xác minh có đáp ứng điều kiện tham gia chức năng chung, ví dụ nhóm finance-readers?
3. **Authorization nghiệp vụ:** DB nội bộ có liên kết subject với tài khoản đang hoạt động và cho phép thao tác cụ thể trên tài nguyên cụ thể không?

Một quyết định điển hình:

~~~text
ALLOW read(order=42)
  = trustedSamlAuthentication
  AND idpGroupEligible
  AND localIdentityLinked
  AND localAccountEnabled
  AND businessPermission(order=42, action=READ)
  AND tenantBoundarySatisfied
  AND noExplicitDeny
~~~

Đây là mô hình **deny by default**: thiếu dữ liệu hoặc có điều kiện không đạt → **DENY**. Không tự dùng phép OR giữa “IdP says admin” và “DB granted” để mở quyền, trừ khi nghiệp vụ có policy đặc biệt đã được phê duyệt và kiểm chứng.

**Câu chốt:** IdP trả lời “người dùng này là ai, có đặc tính tổ chức gì?”; DB ứng dụng trả lời “người dùng này được làm gì với dữ liệu nào?”. Phải xác thực trước khi kiểm tra quyền, và phân quyền ở từng tài nguyên/hành động quan trọng.

## 2. Ranh giới nguồn dữ liệu và nguồn sự thật

| Dữ liệu | Nguồn được tin cậy | Vai trò |
| --- | --- | --- |
| Chữ ký SAML, Issuer, Audience, Destination, Recipient, thời gian | IdP metadata + Spring Security SAML provider | Xác minh assertion hợp lệ |
| NameID, subject, SAML AttributeStatement, groups | **Assertion đã được xác minh** | Cung cấp danh tính ngoài và thuộc tính tổ chức |
| Liên kết subject IdP với user nội bộ | **Account-linking DB** | Ngăn nhầm danh tính giữa IdP/tenant |
| Trạng thái tài khoản enabled/disabled | **DB ứng dụng** | Cho phép hoặc khóa ở phạm vi SP |
| Vai trò và quyền business | **Role/grant/permission DB** | Quyết định thao tác nghiệp vụ |
| Resource ownership, trạng thái tài nguyên, tenant | **DB ứng dụng/policy service** | Bảo vệ từng bản ghi |
| SecurityContext/HttpSession | Spring Security SP | Duy trì trạng thái đăng nhập; không tự đồng bộ mọi thay đổi quyền |

Điều này giải thích vì sao lưu **ROLE_USER** trong SecurityContext không có nghĩa tự động có **order:read:42**. **GrantedAuthority** mô tả những quyền Spring Security biết tại một thời điểm; nhiều quyền tài nguyên chỉ có thể quyết định qua DB ở thời điểm hành động.

### Các mô hình có thể chọn

- **Nhóm IdP là điều kiện cần, DB là điều kiện đủ bổ sung:** dùng AND, thích hợp quản trị dữ liệu nhạy cảm.
- **Nhóm IdP ánh xạ sang role cấp chức năng:** ví dụ nhóm finance-readers ↦ ROLE_FINANCE_USER; người dùng vẫn phải có DB grant cho đơn hàng.
- **Chỉ DB quyết định quyền, IdP chỉ xác thực:** hợp lý nếu nhóm/phòng ban IdP không ổn định hoặc không nằm trong contract của tổ chức.
- **Quyền được đóng vào Authentication khi login:** thích hợp role ít thay đổi, nhưng gặp vấn đề stale permission/thu hồi; phải thiết kế refresh hoặc invalidation.
- **Policy service tập trung:** thích hợp nhiều ứng dụng và chính sách phức tạp; cần tính toán rủi ro mạng/độ trễ và fail-closed.

Không có thuật toán chung “gộp mọi role của IdP và DB rồi cho phép”. Mỗi permission cần **ngữ nghĩa, nguồn có thẩm quyền, điều kiện phủ định và phạm vi dữ liệu** được xác định trước.

## 3. Nhận SAML2 principal từ Spring Security

Ở luồng SAML Web Browser SSO, trình duyệt gửi SAMLResponse đến Assertion Consumer Service (ACS). Spring Security **Saml2WebSsoAuthenticationFilter** chuyển cho AuthenticationManager/OpenSAML provider. Chỉ sau khi kiểm tra chữ ký, Issuer, AudienceRestriction, Recipient/Destination, thời gian, SubjectConfirmation và request correlation cần thiết, Spring tạo Authentication đã xác thực.

Trong Spring Security 6.x, kết quả thông thường là **Saml2Authentication** với principal **Saml2AuthenticatedPrincipal**:

~~~java
@GetMapping("/identity")
public Map<String, Object> identity(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
    List<?> groups = principal.getAttribute("groups");

    return Map.of(
        "registrationId", principal.getRelyingPartyRegistrationId(),
        "subject", principal.getName(),
        "groups", groups == null ? List.of() : groups);
}
~~~

Đoạn trên là **fragment** cần import Java/Spring MVC/SAML; nó chỉ dùng để học, **không nên công khai trong production** vì subject và groups có thể là dữ liệu nhận dạng. Khi dùng controller đầy đủ, có thể inject Authentication hoặc @AuthenticationPrincipal sau khi đã authenticated.

- **getName()** thường biểu diễn **NameID**, không bắt buộc là email.
- **getRelyingPartyRegistrationId()** trả ID registration cục bộ như company, cần gắn với đúng issuer/metadata đáng tin.
- **getAttribute("groups")** lấy danh sách group nếu IdP dùng đúng tên attribute đó. SAML cho phép **nhiều giá trị** cho một attribute.
- **getFirstAttribute** tiện khi contract bảo đảm một giá trị; không dùng để cắt bớt danh sách quyền nhiều giá trị.
- Tên claim có thể là OID/URI hoặc format do IdP phát hành, không mặc định là groups. Cần **contract tên, NameFormat, kiểu dữ liệu, case/normalization, authority nguồn**.

**Không sử dụng giá trị groups từ HTTP query/header hoặc XML SAMLResponse chưa xác minh** để cấp ROLE_ADMIN. Dù cùng tên “admins”, một nhóm của IdP đối tác có thể không phải nhóm có quyền admin trong ứng dụng công ty.

## 4. Liên kết danh tính: issuer + subject, không phải email

Dữ liệu liên kết nên dựa trên **(IdP issuer/entityID, subject ổn định)**. Nếu dự án dùng **registrationId** như company, giá trị này phải là định danh cố định của trust relationship tới đúng IdP. Hai IdP có thể phát cùng NameID nhưng nói về hai người hoàn toàn khác nhau.

| Trust/registration | Subject | Local user |
| --- | --- | --- |
| company | employee-847 | 1001 |
| partner | employee-847 | 9007 |
| company | employee-911 | 1002 |

**Đừng tự gộp hai người đầu vì cùng subject text.** Nếu đổi IdP/tenant hoặc định dạng NameID, phải có quy trình chuyển liên kết có kiểm toán.

### Persistent NameID và transient NameID

- **Persistent NameID** được thiết kế ổn định trong một phạm vi cụ thể; có thể dùng làm khóa liên kết **nếu IdP/SP đã thống nhất contract**.
- **Transient NameID** có thể thay đổi theo lần login, không thích hợp làm khóa DB lâu dài.
- **Email** có thể thay đổi, được tái cấp phát hoặc không unique giữa các tenant; không dùng email làm bằng chứng tự động nhập một tài khoản cũ có quyền cao.
- Nếu dùng một attribute employeeId thay NameID, phải kiểm tra tính ổn định/unique và chỉ đọc sau xác minh SAML.

### Provisioning lúc đăng nhập lần đầu

Khi không tìm thấy local account link, các lựa chọn an toàn là **deny cho tới khi được phê duyệt**, tạo tài khoản **pending không quyền**, hoặc JIT provisioning quyền cơ bản theo policy đã duyệt. Tuyệt đối không tự tạo local ADMIN vì IdP gửi một chuỗi nhóm gần giống tên role quản trị.

## 5. Mapping nhóm từ IdP sang quyền ứng dụng

Một allowlist giúp giảm nguy cơ role injection:

| IdP có thẩm quyền | Attribute/value chính xác | Ý nghĩa có thể map | Điều không tự động được cấp |
| --- | --- | --- | --- |
| company | groups = finance-readers | Được vào màn hình đọc nghiệp vụ tài chính | Không được READ mọi invoice/order |
| company | groups = purchasing | Có thể dùng luồng mua hàng | Không tự được APPROVE hoặc DELETE |
| partner | groups = external-vendor | Chức năng nhà cung cấp đã giới hạn | Không được vào dữ liệu nhân viên |
| company | groups = unknown-group | Không map role | Không tự sinh ROLE_UNKNOWN/ADMIN |

Mapping cần kiểm tra **issuer + attribute name + value**, không chỉ so sánh value. Nếu application muốn dùng **hasRole("FINANCE")**, Spring Security thông thường kiểm tra authority **ROLE_FINANCE**. **hasAuthority("order:read")** so sánh chuỗi chính xác, nhưng quyền **trên orderId cụ thể** vẫn cần DB lookup.

Không làm:

~~~java
// Không an toàn nếu group chưa được allowlist/định nghĩa quyền:
new SimpleGrantedAuthority("ROLE_" + rawGroupFromClient);
~~~

Đây là mảnh code minh họa điều phải tránh, **không phải khuyến nghị triển khai**. Thậm chí với group đã xác minh, ứng dụng vẫn phải kiểm soát việc nhóm nào có thể thành quyền gì và ghi nhận thay đổi mapping.

### Quyền trong Authentication có thể bị cũ

Spring Security có thể lưu GrantedAuthority sau login trong **SecurityContext/HttpSession**. Nếu DB hoặc IdP thu hồi quyền trong khi người dùng vẫn còn phiên, authorities đã chụp lúc login có thể không đổi. Vì vậy:

- Role phục vụ hiển thị menu ít nhạy cảm có thể snapshot ngắn hạn.
- **Object-level permission** nên đọc DB ngay trước hành động hoặc có cache giới hạn TTL/invalidation.
- Thay đổi group tại IdP **không chắc** xuất hiện trong phiên SAML đã thiết lập; cần chính sách re-authentication/forced session invalidation hoặc refresh theo giao thức và yêu cầu nghiệp vụ.
- Khi local account disabled, nên chặn request mới qua DB policy dù SecurityContext vẫn có Authentication hợp lệ.

## 6. Lưu quyền nghiệp vụ trong DB

Ví dụ dùng **PostgreSQL**, single-tenant để tập trung vào nguyên tắc. Dự án nhiều tenant phải đưa tenant_id vào cả bảng liên kết, quyền và truy vấn bản ghi.

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE federated_identities (
    registration_id VARCHAR(80) NOT NULL,
    subject_id VARCHAR(300) NOT NULL,
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    PRIMARY KEY (registration_id, subject_id)
);

CREATE TABLE order_permissions (
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    order_id BIGINT NOT NULL,
    permission VARCHAR(32) NOT NULL,
    permitted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (app_user_id, order_id, permission)
);
~~~

Ví dụ dữ liệu:

~~~sql
INSERT INTO app_users (id, enabled)
VALUES (1001, TRUE);

INSERT INTO federated_identities
    (registration_id, subject_id, app_user_id)
VALUES ('company', 'employee-847', 1001);

INSERT INTO order_permissions
    (app_user_id, order_id, permission, permitted)
VALUES
    (1001, 42, 'READ', TRUE),
    (1001, 43, 'READ', FALSE);
~~~

Nếu subject **employee-847** từ IdP company có group finance-readers và app_users.enabled=true, quyền đọc order 42 có thể được cấp; order 43 bị từ chối. Nếu app_users.enabled=false, cả hai phải bị từ chối.

Bảng liên kết có khóa chính **(registration_id, subject_id)**. Không dùng LIKE(email) hoặc truy vấn tùy tiện “tên trùng thì liên kết”. Việc thêm/sửa account link và grant phải qua luồng quản trị có phê duyệt, audit và điều kiện phức tạp hơn nếu hệ thống cần.

**Lưu ý multi-tenant:** orderId=42 có thể tồn tại ở nhiều tenant. Khi bổ sung tenant_id, phải giữ ràng buộc tới tenant của local user và resource; câu query có tenant filter và FK/unique constraints phù hợp. Không lấy tenantId từ header client rồi tin ngay.

## 7. Ví dụ Spring Boot 3, Java 17+: kiểm tra IdP group AND DB permission

Ứng dụng mẫu dùng **SAML2 browser login** và **method security**. Khi truy cập **GET /orders/42**, Spring Security tạo Saml2Authentication sau SSO, rồi **OrderPolicy** kiểm tra group IdP, account link, enabled và grant trên orderId.

**Các điều kiện để chạy tích hợp thật:** dự án Maven Spring Boot 3.x với Java 17+, metadata IdP đã được duyệt, SP có đúng entityID/ACS, PostgreSQL đã tạo bảng/dữ liệu, cấu hình datasource và biến môi trường. Domain example.org chỉ minh họa, không tự cung cấp dịch vụ SSO.

### 7.1. Maven dependencies

Trong phần dependencies của pom.xml dùng Spring Boot parent/BOM thích hợp:

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
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

Không ép phiên bản OpenSAML khác với tập phiên bản Spring Security tương thích. JDBC là lựa chọn đơn giản cho bài; có thể dùng JPA/PermissionEvaluator/AuthorizationManager trong hệ thống thật.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    metadata-location: classpath:metadata/company-idp.xml

spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

server:
  servlet:
    session:
      timeout: 30m
~~~

Đặt metadata XML IdP thật ở **src/main/resources/metadata/company-idp.xml**; cấu hình tài khoản DB có quyền cần thiết, SQL parameterized, TLS/secret manager theo môi trường. Schema được migration/DBA cài đặt, không coi việc chạy Boot tự tạo các bảng này.

### 7.3. Main class

**src/main/java/com/example/federation/FederationApplication.java**

~~~java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }
}
~~~

### 7.4. Cấu hình SAML2 và method security

**src/main/java/com/example/federation/SecurityConfig.java**

~~~java
package com.example.federation;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties(
            @Value("${app.saml.metadata-location}") String location) {
        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(location)
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp/company")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(company);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**@EnableMethodSecurity** bật xử lý **@PreAuthorize**; chỉ viết annotation trên method nhưng không bật method security thì không đủ. **saml2Login()** giữ flow xác minh SAML chuẩn và session SP, không cần tự parse SAMLResponse để đọc groups.

SP entityID và ACS là ví dụ, phải khớp IdP thực. Nếu thử ở http://localhost:8080 mà ACS đăng ký là https://portal.example.org thì callback sẽ không về local; sửa chính xác môi trường và thông tin hai phía, không tắt Recipient/Audience validation.

### 7.5. OrderPolicy.java: kết hợp IdP group và SQL grant

**src/main/java/com/example/federation/OrderPolicy.java**

~~~java
package com.example.federation;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component("orderPolicy")
public class OrderPolicy {

    private final JdbcTemplate jdbc;

    public OrderPolicy(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public boolean canRead(Authentication authentication, long orderId) {
        if (!(authentication instanceof Saml2Authentication saml)) {
            return false;
        }
        if (!authentication.isAuthenticated()) {
            return false;
        }
        if (!(saml.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }
        if (!"company".equals(principal.getRelyingPartyRegistrationId())) {
            return false;
        }

        List<?> groups = principal.getAttribute("groups");
        if (groups == null || !groups.contains("finance-readers")) {
            return false;
        }

        String subject = principal.getName();
        if (subject == null || subject.isBlank()) {
            return false;
        }

        String sql = """
            SELECT COUNT(*)
              FROM app_users u
              JOIN federated_identities fi
                ON fi.app_user_id = u.id
              JOIN order_permissions op
                ON op.app_user_id = u.id
             WHERE fi.registration_id = ?
               AND fi.subject_id = ?
               AND u.enabled = TRUE
               AND op.order_id = ?
               AND op.permission = 'READ'
               AND op.permitted = TRUE
            """;

        Long count = jdbc.queryForObject(
            sql,
            Long.class,
            principal.getRelyingPartyRegistrationId(),
            subject,
            orderId);

        return count != null && count > 0;
    }
}
~~~

**Giải thích:**

1. Chỉ nhận Saml2Authentication đã được Spring Security thiết lập; trường hợp anonymous/loại auth khác → **DENY**.
2. Kiểm tra registrationId company, phải được cấu hình cố định tới IdP tin cậy.
3. Chỉ chấp nhận attribute groups có giá trị **finance-readers** đúng contract. Nếu group thiếu → DENY; không tự fallback cho phép.
4. Dùng subject đã được xác minh để tra **federated_identities**, không tra theo email giống nhau.
5. Kết hợp local account **enabled** và bản ghi grant có **permission=READ**, **permitted=TRUE** cho orderId cụ thể.
6. Dùng **bind parameters** tránh SQL injection. Query **COUNT(*)** cho kết quả 0 nếu grant/link không tồn tại.
7. Khi DB không sẵn sàng, JdbcTemplate ném exception; không chuyển thành **ALLOW**. Ứng dụng có thể trả 503/5xx đã được xử lý, không lộ SQL hoặc thông tin nhạy cảm.

**Bảo vệ chống TOCTOU:** Nếu check quyền lúc đầu nhưng tài nguyên/tenant/grant thay đổi trước khi đọc/sửa dữ liệu, có thể xảy ra race. Với thao tác ghi nhạy cảm, nên thực hiện **authorization filter trong câu lệnh đọc/sửa** hoặc dùng transaction/locking phù hợp, không tự tin rằng check ở controller là đủ.

### 7.6. OrderController.java: @PreAuthorize bảo vệ resource

**src/main/java/com/example/federation/OrderController.java**

~~~java
package com.example.federation;

import java.util.Map;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/")
    public String home() {
        return "Federated authorization demo";
    }

    @GetMapping("/orders/{orderId}")
    @PreAuthorize("@orderPolicy.canRead(authentication, #orderId)")
    public Map<String, Object> getOrder(
            @P("orderId") @PathVariable("orderId") long orderId) {

        return Map.of(
            "orderId", orderId,
            "authorization", "passed");
    }
}
~~~

**@P("orderId")** giúp Spring Security biết tên tham số trong SpEL **#orderId** mà không phụ thuộc cách compiler giữ tên parameter. **authentication** là Authentication của người dùng hiện tại mà method-security expression cung cấp.

**Controller chỉ trả payload minh họa**, không trả đơn hàng thật. Production phải lấy order dưới điều kiện tenant/permission đáng tin cậy (ở service layer/DB query). Method security nên áp dụng tại **business service** nếu nhiều luồng REST, scheduler hoặc message handler có thể gọi cùng nghiệp vụ; không chỉ dựa vào controller.

### 7.7. Chạy và hành vi kỳ vọng

Sau khi cấu hình metadata IdP, SP registration, PostgreSQL và biến môi trường, chạy ở thư mục project Maven:

~~~bash
mvn spring-boot:run
~~~

Endpoint public:

~~~bash
curl -i http://localhost:8080/
~~~

Response body:

~~~text
Federated authorization demo
~~~

Khi browser đã đăng nhập SAML thật:

| Điều kiện | GET /orders/42 | GET /orders/43 |
| --- | --- | --- |
| IdP group finance-readers; user 1001 enabled; DB grant theo SQL mẫu | **200** | **403** |
| IdP group không có finance-readers | **403** | **403** |
| app_users.enabled = FALSE | **403** | **403** |
| Không có account link | **403** | **403** |
| Không có SAML Authentication hợp lệ | Bắt đầu luồng đăng nhập | Bắt đầu luồng đăng nhập |
| DB tạm mất kết nối | **Không được trả 200** | **Không được trả 200** |

Đây là kết quả logic từ cấu hình/SQL, không khẳng định đã chạy end-to-end trên IdP thật. Nếu IdP không cấp attribute **groups** hoặc group value khác, policy sẽ từ chối; đó là fail-closed, không phải lý do bỏ kiểm tra nhóm.

## 8. Ví dụ Java 17 độc lập, có stdout để kiểm tra

Chương trình bên dưới chỉ mô phỏng **quyết định logic**. Nó không tự xác minh SAML, không truy vấn DB và không nên dùng Set trong memory để thay thế database authorization thật.

**Tệp: CombinedAccessPolicy.java**

~~~java
import java.util.Set;

public final class CombinedAccessPolicy {

    record Evidence(
        boolean verified,
        String registration,
        String subject,
        Set<String> groups) { }

    record LocalAccount(
        String linkedSubject,
        boolean enabled,
        Set<Long> allowedOrderIds) { }

    static boolean canRead(Evidence evidence,
                           LocalAccount local,
                           long orderId) {
        return evidence != null
            && evidence.verified()
            && "company".equals(evidence.registration())
            && evidence.groups().contains("finance-readers")
            && local != null
            && local.enabled()
            && evidence.subject().equals(local.linkedSubject())
            && local.allowedOrderIds().contains(orderId);
    }

    public static void main(String[] args) {
        Evidence valid = new Evidence(
            true, "company", "employee-847",
            Set.of("finance-readers"));
        LocalAccount account = new LocalAccount(
            "employee-847", true, Set.of(42L));
        Evidence noGroup = new Evidence(
            true, "company", "employee-847", Set.of("staff"));

        System.out.println(
            "allow=" + canRead(valid, account, 42L));
        System.out.println(
            "missingGroup=" + canRead(noGroup, account, 42L));
        System.out.println(
            "noLocalGrant=" + canRead(valid, account, 43L));
        System.out.println(
            "disabledLocalUser=" + canRead(valid,
                new LocalAccount("employee-847", false, Set.of(42L)),
                42L));
        System.out.println(
            "wrongLink=" + canRead(valid,
                new LocalAccount("another-subject", true, Set.of(42L)),
                42L));
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac CombinedAccessPolicy.java
java CombinedAccessPolicy
~~~

**Stdout chính xác:**

~~~text
allow=true
missingGroup=false
noLocalGrant=false
disabledLocalUser=false
wrongLink=false
~~~

Các tên và dữ liệu đều giả định. **Evidence.verified** trong demo chỉ là boolean cố định để minh họa; production phải sử dụng Authentication sau khi SAML provider xác minh signature/issuer/audience/recipient/time, không nhận giá trị verified do client tự cung cấp.

## 9. Đồng bộ quyền và vấn đề “stale permissions”

Sau SAML2 login, SP thường lưu Authentication vào SecurityContext/HttpSession. Group từ IdP là snapshot tại thời điểm nhận assertion. Local role nếu được nạp vào authorities ở thời điểm login cũng có thể bị cũ.

| Chiến lược | Độ mới quyền | Đánh đổi |
| --- | --- | --- |
| Nạp toàn bộ role khi SAML login | Snapshot | Ít DB query, nhưng revoke không hiện ra ngay |
| Kiểm tra DB ở mỗi thao tác nhạy cảm | Gần thời gian thực | Có latency/query, cần index và availability |
| Cache quyền với TTL ngắn | Bị giới hạn bởi TTL | Có stale window, cần invalidation đúng |
| Policy service tập trung | Theo source of truth và cache | Cần HA, timeout, fail-closed, giám sát |

**Thu hồi ở DB:** Khi grant bị xóa hoặc app_users.enabled=false, per-request DB policy ngăn request tiếp theo. **Thu hồi ở IdP:** Khi nhóm bị xóa ở IdP, principal đã lưu trong SP session có thể vẫn còn group cũ. Per-request DB check **không tự làm mới IdP attributes**; phải có chính sách re-authentication, session invalidation, IdP logout/invalidation hoặc cơ chế refresh an toàn được thiết kế riêng.

Với những hệ thống cần ngăn thao tác tiền bạc hoặc dữ liệu nhạy cảm, có thể buộc **fresh authentication/step-up** trước hành động, kết hợp policy nội bộ và mức độ xác thực mà IdP cung cấp.

## 10. Role mapping qua response authentication converter

Đối với Spring Security 6.x, có thể thay đổi cách SAML assertion đã xác minh được chuyển thành Authentication/GrantedAuthority thông qua extension tương ứng của **OpenSamlXAuthenticationProvider**; trong các phiên bản hỗ trợ OpenSAML 5 là **OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter**.

Cách mở rộng về mặt kiến trúc:

~~~text
SAML Response từ browser
   |
OpenSAML AuthenticationProvider kiểm tra trust + signature + conditions
   |
Response authentication converter trên dữ liệu đã xác minh
   |
Lookup (IdP issuer, subject) -> local account
   |
Map IdP groups qua allowlist, đọc DB role nếu cần
   |
Tạo Saml2Authentication với authorities đã duyệt
   |
SecurityContext / HttpSession
~~~

**Không cần dùng converter chỉ để kiểm tra orderId.** Ví dụ OrderPolicy ở mục 7 giữ nguyên provider SAML chuẩn và kiểm tra quyền lúc truy cập. Nếu tùy biến converter phải giữ nguyên validation chuẩn, xử lý lỗi DB fail closed và làm rõ cơ chế cập nhật authorities stale. **DaoAuthenticationProvider không phải công cụ nạp role cho SAML2**; provider đó dành cho xác thực username/password.

Nếu muốn hiển thị một nút theo role mà không gây nhiều query, có thể tạo một **display entitlement** lúc login, nhưng backend vẫn phải kiểm tra grant thực sự trước khi trả hoặc sửa tài nguyên. Ẩn nút trên UI không phải authorization.

## 11. Quyền trên đối tượng, tenant và trạng thái dữ liệu

Một hệ thống thực tế thường có thêm:

- **Resource ownership:** Đơn hàng thuộc user/team/đơn vị nào?
- **Tenant scope:** User có nằm trong tenant của order?
- **Workflow state:** Chỉ cho sửa DRAFT, không cho sửa APPROVED/CLOSED.
- **Amount limits:** Người phê duyệt chỉ được duyệt dưới ngưỡng.
- **Separation of duties:** Người tạo không được là người duyệt cùng giao dịch.
- **Grant expiration:** Quyền dự án chỉ đến một ngày xác định.
- **Explicit deny:** Tài khoản tạm khóa hoặc tài nguyên bị legal hold.

Ví dụ:

~~~text
approveInvoice(user, invoice)
 = validSaml(user)
 AND userInApprovedIdpGroup
 AND localUserEnabled(user)
 AND invoice.tenantId == user.tenantId
 AND hasLocalPermission(user, invoice, APPROVE)
 AND invoice.status == PENDING
 AND invoice.amount <= user.approvalLimit
 AND invoice.createdBy != user.id
 AND noHold(invoice)
~~~

Các điều kiện chứa dữ liệu DB cần kiểm tra trong giao dịch phù hợp, nhất là lúc **sửa trạng thái**. Không chỉ kiểm tra role trên URL; hãy đưa policy sát với điểm thực thi nghiệp vụ.

## 12. Xử lý lỗi và chính sách fail closed

- **SAMLResponse không hợp lệ:** không tạo Authentication đáng tin; không truy cập DB grant để “chữa” authentication thất bại.
- **Không có local account:** deny hoặc tạo pending không quyền, theo onboarding policy.
- **Unknown IdP group:** không map role cao, deny nếu group là điều kiện bắt buộc.
- **Account disabled:** deny bất kể IdP session vẫn hoạt động.
- **DB không truy cập được:** không mặc định cho phép bằng last-known role; trả lỗi an toàn với monitoring, không làm lộ SQL/PII.
- **Không tìm thấy resource:** tránh tiết lộ thông tin phân biệt resource tồn tại ở tenant khác; chọn 404/403 theo policy nhất quán.
- **Cấu hình IdP không ổn định:** không tự chuyển sang tin issuer khác vì một request mang dữ liệu trông hợp lệ.
- **Transaction race:** sau check nhưng trước UPDATE có thể thay grant/trạng thái; dùng conditional SQL/transaction phù hợp.

**Không lưu toàn bộ SAMLResponse hoặc danh sách chi tiết mọi tài nguyên được phép vào cookie/client.** Session cookie chỉ là định danh phiên; business grant vẫn do nguồn dữ liệu có quyền quản trị xác nhận.

## 13. Kiểm thử kết hợp và bài tập

### Ma trận kiểm thử âm

1. **Wrong issuer:** SAMLResponse ký bởi IdP partner nhưng account grant thuộc company → từ chối.
2. **Signature/recipient/audience sai:** không đi tới bước xét local grant.
3. **Đúng group nhưng thiếu DB grant:** orderId bị từ chối.
4. **Đúng DB grant nhưng thiếu group bắt buộc:** từ chối.
5. **Local user disabled:** từ chối dù IdP còn xác thực.
6. **Subject thay đổi hoặc transient NameID:** không tự join sang tài khoản có quyền.
7. **Email giống người khác:** không tự gộp account link.
8. **IdP group tên ROLE_ADMIN chưa nằm trong mapping:** không cấp admin.
9. **DB grant revoked khi session còn sống:** request tiếp theo bị từ chối với per-request lookup.
10. **IdP group revoked khi session còn sống:** kiểm thử chính sách refresh/session invalidation, không giả định tự cập nhật.
11. **DB outage:** không có request nào được cấp quyền nhờ fallback allow.
12. **Cross-tenant resource ID:** chỉ có tenant scope đúng mới được phép.
13. **Tham số orderId bị sửa:** kiểm tra object-level trên mỗi request, tránh IDOR/BOLA.
14. **Gọi business service từ scheduler/message consumer:** policy không bị bypass bởi đường vào khác.
15. **Grant thay ngay trong giao dịch ghi:** bảo đảm condition/locking ngăn TOCTOU.
16. **Unknown/missing groups:** deny thay vì có role mặc định quá rộng.
17. **Local role thay đổi giữa hai tab/browser session:** policy phải phản ánh revoke theo SLA.
18. **Audit:** ghi actor/action/resource/decision có kiểm soát, không log SAMLResponse hoặc cookie.

### Câu hỏi tự kiểm tra

**Câu 1:** IdP nói user thuộc finance-readers, nhưng DB không có quyền order 99. Có cho xem không?  
**Trả lời:** Không. Nhóm IdP chỉ là điều kiện chức năng; local DB không có grant thì mặc định từ chối.

**Câu 2:** DB có grant READ order 42 cho subject employee-847 thuộc company, nhưng người gửi là employee-847 của partner. Có cho xem không?  
**Trả lời:** Không. Khóa liên kết phải xét IdP/issuer hoặc registration đã được phê duyệt **cùng subject**.

**Câu 3:** DB thu hồi quyền ngay khi session SP còn sống. Chọn cách gì để request sau bị chặn?  
**Trả lời:** Kiểm tra DB tại request/hành động, hoặc cache có invalidation và mức stale được quy định; không chỉ lưu quyền lúc login.

**Câu 4:** IdP gỡ group khi SP đã lưu principal có group cũ; truy vấn DB mỗi request có bảo đảm biết group đã gỡ không?  
**Trả lời:** Không. Attribute IdP trong principal có thể stale; cần chính sách re-authentication hoặc invalidation phù hợp.

**Câu 5:** Có thể biến mọi SAML group thành ROLE_* theo cách nối chuỗi không?  
**Trả lời:** Không. Chỉ map các group/issuer đã được phê duyệt theo allowlist, và quyền tài nguyên phải được kiểm tra riêng.

**Câu 6:** Một @PreAuthorize trên controller có đủ bảo vệ nghiệp vụ ở mọi kênh không?  
**Trả lời:** Không nếu service còn được gọi bởi những đường khác. Policy nên được thực thi ở service layer/DB boundary phù hợp.

## 14. Checklist production

- [ ] SAMLResponse đã được Spring SAML provider xác minh đầy đủ: signature, Issuer, AudienceRestriction, Recipient, time và correlation.
- [ ] Có contract về group attribute, NameFormat, issuer và subject ổn định của IdP.
- [ ] Account linking gắn với **issuer/registration đã được duyệt + subject**, không mặc định email.
- [ ] Local account enabled/disabled, role và resource grants nằm trong source of truth có audit.
- [ ] Các group IdP được map bằng allowlist; unknown/missing group không sinh quyền.
- [ ] Áp dụng **deny by default, least privilege** và AND các điều kiện cần.
- [ ] Quyền object-level được quyết định theo **action + resource + tenant**, không chỉ role.
- [ ] Có **@EnableMethodSecurity** khi dùng @PreAuthorize; business service được bảo vệ cả khi có nhiều kênh gọi.
- [ ] JDBC query dùng bind parameters, index/constraints và timeout phù hợp; không lộ lỗi SQL.
- [ ] DB outage không dẫn tới fallback allow.
- [ ] Có policy cho revoke, đổi group và session stale ở cả IdP lẫn DB.
- [ ] Với multi-tenant, mọi link/grant/resource query đều có tenant scope.
- [ ] Với thao tác ghi/duyệt, chống TOCTOU qua transaction hoặc conditional update.
- [ ] Test missing group, missing grant, wrong issuer, wrong subject, disabled, revocation, DB outage, cross-tenant và role injection.
- [ ] Audit vừa đủ để truy nguyên nguồn grant, không log SAMLResponse/cookie/PII nhạy cảm.

**Kết luận:** Trong SAML2 federation, IdP là nguồn sự thật cho **danh tính và các thuộc tính tổ chức được xác minh**; ứng dụng nội bộ là nguồn sự thật cho **đặc quyền nghiệp vụ trên từng tài nguyên**. Spring Security cung cấp Saml2AuthenticatedPrincipal và method security để kết hợp hai nguồn theo chính sách rõ ràng. Người dùng được đăng nhập thành công chỉ là **điểm bắt đầu** của quá trình phân quyền.

## 15. Tài liệu tham khảo

- [Spring Security 6.5 – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): SAML2 Authentication, Saml2AuthenticatedPrincipal và dữ liệu attributes.
- [Spring Security 6.5 – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): response converter, phối hợp UserDetailsService và quyền tùy biến.
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): @EnableMethodSecurity, @PreAuthorize, parameter annotation @P và bean policy.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): GrantedAuthority và AuthorizationManager.
- [Spring Framework – JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcTemplate và bind parameters.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, check permissions on every request.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID, AttributeStatement, assertion conditions.
