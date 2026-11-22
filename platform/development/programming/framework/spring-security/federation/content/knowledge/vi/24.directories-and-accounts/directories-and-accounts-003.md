# Tải nhóm hoặc thuộc tính nội bộ sau khi xác thực liên kết

## 1. Bài toán: IdP nhận diện người dùng, ứng dụng vẫn phải quyết định quyền

Một ứng dụng Spring Security dùng **OIDC, SAML2, CAS hoặc Kerberos** thường ủy quyền việc xác thực danh tính cho hệ thống khác. Sau khi IdP/KDC/CAS xác thực thành công, ứng dụng mới biết **người dùng bên ngoài là ai**; chưa đủ để biết người ấy có tài khoản nội bộ nào, thuộc phòng ban/nhóm/tenant nào và có quyền đọc, duyệt, xuất hay xóa dữ liệu nào.

Ví dụ:

~~~text
OIDC authenticated identity:
    issuer = https://idp.example.org/realms/corp
    sub = opaque-123

Internal identity binding:
    (OIDC, issuer, sub) -> account_id = 41

Local directory:
    account_id=41, status=ACTIVE
    tenant_id=corp, membership=ACTIVE
    groups=[FINANCE_READER, CASE_AGENT]

Approved policy:
    corp:FINANCE_READER -> APP_REPORT_READ
    corp:CASE_AGENT -> APP_CASE_WRITE

Spring authorization:
    /corp/reports requires APP_REPORT_READ
    data queries must still enforce tenant_id=corp
~~~

**Xác thực liên kết thành công không tự trao quyền toàn bộ ứng dụng.** Cần tách rõ:

1. **Federated authentication:** verify OIDC ID Token/code, SAMLResponse, CAS service ticket hoặc Kerberos service ticket.
2. **Identity binding:** liên kết danh tính đã được xác minh với **internal account ID**.
3. **Internal directory loading:** tải trạng thái tài khoản, membership, groups và attributes từ nguồn có thẩm quyền.
4. **Authority mapping:** dùng chính sách có allowlist để chuyển groups/attributes thành **GrantedAuthority** hoặc business permissions.
5. **Resource authorization:** kiểm role/tenant/owner/operation ở service/database, kể cả sau khi session đã được tạo.

Bài thuộc nhóm **Thư mục và tài khoản** của **Spring Security - federation**. Ví dụ Java dùng **Java 17+**, Spring Boot **3.3.5** và Spring Security **6.x**. Tất cả issuer/tenant/subject theo example.org là dữ liệu giả, không phải IdP thật đang hoạt động.

### Kết quả học tập

- Phân biệt external claims với internal attributes và thẩm quyền cấp quyền.
- Biết cách chọn khóa account **(protocol, trusted issuer, stable subject)**, không auto-link bằng email.
- Hiểu vai trò của **LDAP/Active Directory, local DB, SCIM/IGA, HR data**.
- Biết cách tải nhóm tại **OIDC user service**, trong SAML2 response converter, hoặc qua local UserDetailsService cho CAS/Kerberos.
- Tạo policy **group → permission** chính xác, có tenant scope, không tự map thành ROLE_ADMIN.
- Đánh giá timing, cache, stale authorities, offboarding, nested group, LDAP injection và directory outages.
- Chạy ví dụ Java 17 độc lập, cấu hình Spring OIDC + JDBC, kiểm thử cả các tình huống từ chối.

## 2. Ranh giới tin cậy: phải tải dữ liệu sau khi xác thực

~~~text
Browser
    |
    v
Spring Security protocol filter/provider
  OIDC: code exchange + ID Token validation
  SAML2: XML Signature + issuer + audience + subject confirmation
  CAS: validate service ticket with CAS server
  Kerberos: GSS context with SPN/keytab
    |
    v
Trusted external identity
  (protocol, issuer/realm, stable subject)
    |
    v
Server-side identity_links
  -> internal account_id
    |
    v
Directory / internal DB / IAM
  -> active account?
  -> tenant membership?
  -> groups, department, manager, cost center?
    |
    v
Explicit local authority policy
  -> allowed business permissions
    |
    v
Spring Authentication/GrantedAuthority
    |
    v
Service + resource + tenant authorization
    |
    v
Database WHERE tenant_id = authorizedTenant
~~~

**Không được thực hiện local authority mapping dựa trên email/header/issuer do browser tự khai trước khi framework xác thực liên kết.** Một chữ ký SAML/JWT hợp lệ chỉ chứng minh token đến từ một issuer tin cậy và thỏa các validation của giao thức; chữ ký **không tự quyết định** issuer ấy có quyền cấp ROLE_ADMIN, tenant membership hay quyền business cụ thể.

Ví dụ người dùng từ IdP Partner có signed claim **department=Finance**: ứng dụng không được mặc định cho họ đọc dữ liệu tài chính của Corp. Cần xem IdP có quyền xác thực danh tính, cấp nhóm, hoặc cấp membership cho tenant nào theo **trust contract** của tổ chức.

## 3. Những thuộc tính nào nên đọc từ nguồn nội bộ?

| Dữ liệu | Nguồn authoritative thường gặp | Ứng dụng dùng để | Rủi ro khi lấy sai |
| --- | --- | --- | --- |
| Internal account ID | Local database/IGA | Khóa user ổn định, audit, foreign keys. | Trùng email làm ghép nhầm users. |
| Account enabled/locked | IAM/local DB/HR workflow | Quyết định có cho đăng nhập hoặc access. | IdP login pass nhưng account app đã bị khóa. |
| Tenant membership | Membership DB/IGA | Quyền chọn tenant. | Cross-tenant data access. |
| Groups/roles | AD/LDAP/local groups/SCIM | Input cho chính sách quyền. | Nhóm ngoài phạm vi trở thành admin. |
| Department/cost center | HR/IGA/directory | ABAC, routing, báo cáo theo đơn vị. | Department string giả/mới chưa được phê duyệt. |
| Manager/approval chain | HR/IGA | Workflow phê duyệt. | Một manager bị hiểu là admin toàn hệ thống. |
| Display name/job title | Directory/HR | Giao diện profile. | Dùng thông tin hiển thị làm account key. |
| Permission version | IAM/authorization store | Revalidation và session/cache invalidation. | Quyền đã thu hồi vẫn dùng lâu. |
| Tenant/account risk flags | Business authorization store | Block/step-up theo policy. | API nhạy cảm không kiểm điều kiện mới. |

**Nhóm không nhất thiết là một chuỗi đơn giản.** Directory có thể trả nhiều group DNs, objectGUIDs, group IDs hoặc nested groups; phải phân biệt loại trực tiếp/lồng nhau, giới hạn kích thước và tránh vòng lặp. Không mặc định memberOf trong Active Directory trả tất cả nhóm lồng nhau hoặc mọi LDAP directory có cùng schema.

## 4. Liên kết external principal với local account

### 4.1. OIDC: dùng issuer + subject đã xác minh

OIDC ID Token có **iss** và **sub**. Khi Spring Security OIDC authentication đã thành công, cặp:

~~~text
iss = https://idp.example.org/realms/corp
sub = opaque-123
~~~

được dùng lookup identity link. **sub ổn định trong phạm vi issuer**, nhưng có thể là pairwise subject theo client; issuer/sub có thể thay khi IdP migration. Phải có quy trình thay đổi hoặc link accounts đã xác minh.

**Không nên dùng email/preferred_username làm khóa duy nhất toàn cục**: email đổi, tái cấp hoặc trùng giữa IdPs; email_verified giúp khẳng định một tính chất do provider phát nhưng không tự cho phép gộp mọi account cùng email.

### 4.2. SAML2: IdP issuer + stable subject theo trust contract

~~~text
protocol = SAML2
issuer = https://saml.corp.example.org/idp
stableSubject = immutableEmployeeId
              hoặc persistent NameID đúng contract
~~~

**NameID có nhiều formats**: transient, persistent, email. Transient NameID không phù hợp làm account ID lâu dài; email format cũng không nhất thiết immutable. Sau Spring/OpenSAML signature, issuer, audience, time, recipient, correlation validation, mới đọc AttributeStatement và map identity.

**registrationId khác tenant ID**: một RelyingPartyRegistration có thể xác thực user cho nhiều tenants, hoặc một IdP dùng nhiều registrations. Không cấp membership chỉ vì ACS URL chứa tên tenant.

### 4.3. CAS và Kerberos

- **CAS native:** username đáng tin sau khi service ticket được CAS validator kiểm với đúng service. Nếu có nhiều CAS realms/servers, namespace identity theo CAS trust domain; username alice từ CAS A có thể khác alice từ CAS B.
- **Kerberos:** verified principal có realm, ví dụ **alice@EXAMPLE.ORG**; đừng cắt @REALM rồi ghép với alice@OTHER.ORG.
- **LDAP username** và federated subject không mặc nhiên trùng. Liên kết bằng internal identity registry với owner, status và audit.

### 4.4. Bảng identity_links

~~~sql
CREATE TABLE app_accounts (
    account_id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE identity_links (
    protocol VARCHAR(16) NOT NULL,
    issuer VARCHAR(255) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    account_id BIGINT NOT NULL REFERENCES app_accounts(account_id),
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (protocol, issuer, subject_id)
);
~~~

Đây là **server-controlled link**, không phải dữ liệu do user tự POST. Cùng subject ở hai issuers là hai identities khác nhau. Nhiều external identities có thể liên kết một internal account, nhưng chỉ khi qua một quy trình **verified account linking** được phê duyệt, không dựa vào email/displayName.

Nếu identity link không tồn tại, inactive hoặc mâu thuẫn, hệ thống nên **deny by default** hoặc đưa user vào onboarding flow không có quyền nhạy cảm; không tự cấp ROLE_ADMIN vì issuer “đáng tin”.

## 5. Nguồn nhóm và thuộc tính nội bộ

### Local DB

Thích hợp khi nhóm/quyền là khái niệm nghiệp vụ như **FINANCE_READER, CASE_AGENT, REPORT_APPROVER** hoặc membership tenant. Database cung cấp constraints, audit, transactions, permissions và version cho revoke. Cần đồng bộ lifecycle với IdP/HR/IGA.

### LDAP / Active Directory

Thích hợp khi công ty quản lý groups trong directory. Có thể dùng:

- **objectGUID/entryUUID** hoặc immutable directory object ID để gắn với account.
- **memberOf**, group member query, hoặc directory-specific mechanism cho nested groups.
- **employeeID, department, manager, cost center, account flags** theo schema.
- Mapping **directory group DN/object ID** sang local permission policy.

Kết nối LDAP bằng **LDAPS/StartTLS với TLS certificate/hostname validation**, account **read-only least privilege**, search base hạn chế, timeout, paging và size limits. Tránh string-concatenated LDAP filters từ user input; dùng **LdapTemplate**/query builder có escaping đúng schema.

**LDAP lookup sau federated authentication không bắt user LDAP bind lại bằng password.** App đã xác thực qua IdP; directory client dùng service credential/read access riêng. LDAP group query và LDAP password-based authentication là hai khâu khác nhau.

### SCIM, IGA, HR

**SCIM** có thể đồng bộ users/groups, disable status và provisioning events vào local database; **IGA/HR** là nguồn cho organization/department/manager. Phương án này giúp login nhanh hơn việc truy vấn nhiều systems đồng bộ tại mọi request, nhưng phải có idempotency, event integrity, reconciliation, lag monitoring và revoke SLA.

Không coi một signed **groups** claim từ IdP là quyền mặc định trừ khi **authority delegation contract** của tổ chức cho phép IdP cấp nhóm đó, và mapping vẫn có tenant/role allowlist.

## 6. Group không phải GrantedAuthority và không phải OAuth2 SCOPE

Ví dụ chính sách server-side:

| Tenant | Internal group | GrantedAuthority |
| --- | --- | --- |
| corp | FINANCE_READER | APP_REPORT_READ |
| corp | CASE_AGENT | APP_CASE_WRITE |
| corp | SUPPORT_VIEWER | APP_TICKET_READ |
| partner | FINANCE_READER | APP_PARTNER_REPORT_READ |

**GrantedAuthority** trong Spring Security là chuỗi authority được Authentication mang theo; **@PreAuthorize("hasAuthority('APP_REPORT_READ')")** kiểm đúng chuỗi đó. **hasRole("ADMIN")** mặc định kiểm **ROLE_ADMIN**. **SCOPE_read** thường đại diện OAuth2 access token scope, không tự tương đương business permission đọc báo cáo.

Mẫu nguy hiểm:

~~~java
// KHÔNG sử dụng: user-controlled/unapproved external group
new SimpleGrantedAuthority("ROLE_" + externalGroup);
~~~

Mẫu đúng là **chỉ lấy các quyền local đã nằm trong allowlist** sau khi kiểm issuer/sub/account/membership:

~~~java
// Mảnh minh họa; roleCode đến từ policy nội bộ được phê duyệt.
if (APPROVED_PERMISSIONS.contains(roleCode)) {
    new SimpleGrantedAuthority(roleCode);
}
~~~

Trong ứng dụng nhiều tenant, không có quyền report toàn cầu chỉ vì user có quyền ở tenant Corp. Cần kiểm membership **tenant được yêu cầu**, operation và resource tenant. **URL/header/body tenantId chỉ là selector**, không tự cấp quyền.

## 7. Chọn thời điểm tải nhóm: login, request hay provisioning

| Thời điểm | Lợi ích | Hạn chế |
| --- | --- | --- |
| **Ngay sau federated login** | Có authorities ngay khi lập Authentication. | Login chậm hơn; session có thể stale sau revoke. |
| **Tại request/service authorization** | Phản ánh thay đổi gần thời gian thực. | Tốn DB/LDAP, cần cache/timeouts. |
| **SCIM/IGA background sync** | Login nhanh, data được quản trị. | Đồng bộ bất đồng bộ có thể trễ. |
| **Kết hợp login preload + recheck cho sensitive operations** | Cân bằng UX và freshness. | Cần permission version/session revocation policy. |

Với payroll, administration, export hoặc cross-tenant data, nên **recheck local account/role/tenant** tại resource access, hoặc dùng permission version và session/cache invalidation. **Không mặc định authorities tạo lúc login sẽ luôn cập nhật khi nhóm đổi ở directory.**

## 8. Java 17 thuần: mô phỏng xác thực liên kết và tải nhóm

**FederatedDirectoryDemo.java** chạy bằng JDK 17, **không cần OIDC/SAML2/LDAP/KDC**. Đối tượng VerifiedIdentity dưới đây là **mô hình đã được framework xác minh**, không được tạo từ JSON/header do browser gửi trong hệ thống thật.

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

public class FederatedDirectoryDemo {
    static final String CORP =
            "https://idp.example.org/realms/corp";
    static final String OTHER =
            "https://idp.other.example.org/realms/other";

    record VerifiedIdentity(String issuer, String sub,
                            boolean verified) {}
    record Account(long id, boolean enabled) {}
    record Membership(long id, String tenant,
                      boolean active, List<String> groups) {}
    record IdentityKey(String issuer, String sub) {}

    static final Map<IdentityKey, Account> LINKS = Map.of(
        new IdentityKey(CORP, "opaque-123"), new Account(41, true),
        new IdentityKey(CORP, "disabled-9"), new Account(99, false),
        new IdentityKey(CORP, "revoked-2"), new Account(42, true),
        new IdentityKey(CORP, "unknown-group"), new Account(43, true),
        new IdentityKey(CORP, "no-groups"), new Account(44, true)
    );
    static final List<Membership> MEMBERS = List.of(
        new Membership(41, "corp", true,
            List.of("FINANCE_READER", "CASE_AGENT")),
        new Membership(42, "corp", false, List.of("FINANCE_READER")),
        new Membership(43, "corp", true, List.of("UNKNOWN_GROUP")),
        new Membership(44, "corp", true, List.of())
    );
    static final Map<String, String> APPROVED = Map.of(
        "FINANCE_READER", "APP_REPORT_READ",
        "CASE_AGENT", "APP_CASE_WRITE"
    );

    static String decide(VerifiedIdentity id, String tenant) {
        if (id == null || !id.verified()) {
            return "DENY UNVERIFIED_IDENTITY";
        }
        Account account = LINKS.get(new IdentityKey(id.issuer(), id.sub()));
        if (account == null) {
            return "DENY NO_LINK";
        }
        if (!account.enabled()) {
            return "DENY ACCOUNT_DISABLED";
        }

        Membership membership = MEMBERS.stream()
            .filter(m -> m.id() == account.id())
            .filter(m -> m.tenant().equals(tenant))
            .findFirst().orElse(null);
        if (membership == null) {
            return "DENY NO_MEMBERSHIP";
        }
        if (!membership.active()) {
            return "DENY INACTIVE_MEMBERSHIP";
        }

        TreeSet<String> permissions = new TreeSet<>();
        for (String group : membership.groups()) {
            String code = APPROVED.get(group);
            if (code == null) {
                return "DENY UNMAPPED_GROUP";
            }
            permissions.add(code);
        }
        return "ALLOW account=" + account.id()
             + " permissions=" + permissions;
    }

    static void show(String label, VerifiedIdentity id, String tenant) {
        System.out.println(label + ": " + decide(id, tenant));
    }

    public static void main(String[] args) {
        show("valid", new VerifiedIdentity(
            CORP, "opaque-123", true), "corp");
        show("wrong tenant", new VerifiedIdentity(
            CORP, "opaque-123", true), "partner");
        show("same sub other issuer", new VerifiedIdentity(
            OTHER, "opaque-123", true), "corp");
        show("unverified", new VerifiedIdentity(
            CORP, "opaque-123", false), "corp");
        show("disabled", new VerifiedIdentity(
            CORP, "disabled-9", true), "corp");
        show("revoked", new VerifiedIdentity(
            CORP, "revoked-2", true), "corp");
        show("unmapped", new VerifiedIdentity(
            CORP, "unknown-group", true), "corp");
        show("empty groups", new VerifiedIdentity(
            CORP, "no-groups", true), "corp");
        show("missing", null, "corp");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FederatedDirectoryDemo.java
java FederatedDirectoryDemo
~~~

**stdout chính xác:**

~~~text
valid: ALLOW account=41 permissions=[APP_CASE_WRITE, APP_REPORT_READ]
wrong tenant: DENY NO_MEMBERSHIP
same sub other issuer: DENY NO_LINK
unverified: DENY UNVERIFIED_IDENTITY
disabled: DENY ACCOUNT_DISABLED
revoked: DENY INACTIVE_MEMBERSHIP
unmapped: DENY UNMAPPED_GROUP
empty groups: ALLOW account=44 permissions=[]
missing: DENY UNVERIFIED_IDENTITY
~~~

- **valid:** hai local groups được map và TreeSet sắp xếp **APP_CASE_WRITE** trước **APP_REPORT_READ**.
- **wrong tenant:** user không có membership Partner dù account là Corp.
- **same sub other issuer:** sub giống nhau nhưng IdP khác không được auto-link.
- **unverified:** không dùng identity chưa được protocol provider xác thực.
- **disabled/revoked:** vẫn có identity link nhưng local account/membership không hợp lệ.
- **unmapped:** nhóm nội bộ chưa có hợp đồng quyền; fail-closed.
- **empty groups:** có thể vào ứng dụng nhưng không được cấp business permissions; API yêu cầu APP_REPORT_READ phải trả 403.

**Chương trình này không kiểm OIDC ID Token/SAML signature, không nối LDAP/SQL và không tạo HTTP session.** Chỉ dùng để học bước **local authorization sau trusted authentication**.

## 9. Ví dụ Spring Boot 3.3.5: OIDC UserService tải nhóm JDBC

Mẫu Servlet Spring MVC dưới đây có **OIDC federation + local JDBC directory**. H2 chỉ dùng để học. Để chạy login thật cần OIDC Provider sandbox và client registration hợp lệ, với issuer/sub thực đã được phê duyệt liên kết tới local account.

### 9.1. pom.xml

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
    <artifactId>federated-directory-example</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build><plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins></build>
</project>
~~~

**Đừng dùng thư viện OIDC để tự verify SAMLResponse hay dùng claim groups từ bearer token không đúng issuer.** Spring oauth2Login() thực hiện OIDC authorization code flow; business mapping chạy sau khi framework xác minh ID Token.

### 9.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

spring:
  datasource:
    url: "jdbc:h2:mem:directorydb;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
  security:
    oauth2:
      client:
        registration:
          intranet:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: "${OIDC_ISSUER_URI}"
~~~

Biến môi trường issuer phải trỏ tới **OIDC Provider thật** có discovery metadata. Client cần đăng ký redirect URI, ví dụ **http://localhost:8080/login/oauth2/code/intranet** trong sandbox được kiểm soát hoặc HTTPS public callback thực tế. Không đặt secret trong source code/log.

### 9.3. schema.sql

**src/main/resources/schema.sql**

~~~sql
CREATE TABLE app_accounts (
    account_id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE identity_links (
    protocol VARCHAR(16) NOT NULL,
    issuer VARCHAR(255) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    account_id BIGINT NOT NULL REFERENCES app_accounts(account_id),
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (protocol, issuer, subject_id)
);

CREATE TABLE tenant_memberships (
    account_id BIGINT NOT NULL REFERENCES app_accounts(account_id),
    tenant_id VARCHAR(32) NOT NULL,
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (account_id, tenant_id)
);

CREATE TABLE directory_groups (
    tenant_id VARCHAR(32) NOT NULL,
    group_code VARCHAR(64) NOT NULL,
    authority_code VARCHAR(64) NOT NULL,
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (tenant_id, group_code)
);

CREATE TABLE assigned_groups (
    account_id BIGINT NOT NULL,
    tenant_id VARCHAR(32) NOT NULL,
    group_code VARCHAR(64) NOT NULL,
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (account_id, tenant_id, group_code),
    FOREIGN KEY (account_id, tenant_id)
        REFERENCES tenant_memberships(account_id, tenant_id),
    FOREIGN KEY (tenant_id, group_code)
        REFERENCES directory_groups(tenant_id, group_code)
);
~~~

Các ràng buộc PK/FK chống lẫn identity links và gán group vào tenant không có membership; database production còn cần indexes, migrations, transaction/revocation và audit.

### 9.4. data.sql

**src/main/resources/data.sql**

~~~sql
INSERT INTO app_accounts VALUES (41, 'Alice', TRUE);

-- PLACEHOLDER: issuer/sub phải được thay bằng verified IdP identity.
INSERT INTO identity_links
(protocol, issuer, subject_id, account_id, enabled)
VALUES
('OIDC', 'https://idp.example.org/realms/corp',
 'opaque-123', 41, TRUE);

INSERT INTO tenant_memberships VALUES (41, 'corp', TRUE);

INSERT INTO directory_groups VALUES
('corp', 'FINANCE_READER', 'APP_REPORT_READ', TRUE),
('corp', 'CASE_AGENT', 'APP_CASE_WRITE', TRUE);

INSERT INTO assigned_groups VALUES
(41, 'corp', 'FINANCE_READER', TRUE),
(41, 'corp', 'CASE_AGENT', TRUE);
~~~

Trong production không để demo SQL tự chạy. Provisioning/identity linking do IAM/DB workflow có quyền thực hiện; không auto-insert account từ email chưa được xác minh.

### 9.5. Main

**src/main/java/com/example/directory/FederatedDirectoryApplication.java**

~~~java
package com.example.directory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederatedDirectoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederatedDirectoryApplication.class, args);
    }
}
~~~

### 9.6. LocalAuthorityService.java

**src/main/java/com/example/directory/LocalAuthorityService.java**

~~~java
package com.example.directory;

import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LocalAuthorityService {
    // Demo chỉ dành cho tenant corp. Multi-tenant cần scope mỗi request.
    private static final String TENANT = "corp";
    private static final Set<String> ALLOWED = Set.of(
        "APP_REPORT_READ", "APP_CASE_WRITE"
    );
    private final JdbcTemplate jdbc;

    public LocalAuthorityService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record LocalProfile(long accountId, String displayName,
                               Set<String> permissions) {}

    @Transactional(readOnly = true)
    public LocalProfile load(String issuer, String subject) {
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw denied("missing_verified_identity");
        }

        List<LocalProfile> accounts = jdbc.query(
            """
            SELECT a.account_id, a.display_name
              FROM app_accounts a
              JOIN identity_links l ON l.account_id = a.account_id
              JOIN tenant_memberships m ON m.account_id = a.account_id
             WHERE l.protocol = 'OIDC'
               AND l.issuer = ? AND l.subject_id = ?
               AND a.enabled = TRUE AND l.enabled = TRUE
               AND m.tenant_id = ? AND m.enabled = TRUE
            """,
            (rs, index) -> new LocalProfile(
                rs.getLong("account_id"),
                rs.getString("display_name"),
                Set.of()),
            issuer, subject, TENANT
        );
        if (accounts.size() != 1) {
            throw denied("no_active_local_identity");
        }

        LocalProfile account = accounts.get(0);
        List<String> codes = jdbc.queryForList(
            """
            SELECT DISTINCT g.authority_code
              FROM assigned_groups ag
              JOIN directory_groups g
                ON ag.tenant_id = g.tenant_id
               AND ag.group_code = g.group_code
             WHERE ag.account_id = ?
               AND ag.tenant_id = ?
               AND ag.enabled = TRUE
               AND g.enabled = TRUE
            """,
            String.class, account.accountId(), TENANT
        );

        TreeSet<String> verified = new TreeSet<>();
        for (String code : codes) {
            if (!ALLOWED.contains(code)) {
                throw denied("unapproved_permission_code");
            }
            verified.add(code);
        }
        return new LocalProfile(account.accountId(),
            account.displayName(), Set.copyOf(verified));
    }

    private OAuth2AuthenticationException denied(String code) {
        return new OAuth2AuthenticationException(new OAuth2Error(code));
    }
}
~~~

Chú ý:

1. **JdbcTemplate** dùng placeholders/bound parameters cho issuer và subject; không string-concatenate SQL theo user input.
2. Local account, identity link và membership đều phải active; không lấy group từ email/remote claim.
3. **tenant=corp được cố định bằng server config** trong ví dụ; nếu hệ thống nhiều tenant, phải kiểm requested tenant và membership mỗi operation.
4. Group authorities được lấy từ bảng local và kiểm allowlist; nếu có mã lạ, ví dụ **ROLE_SUPER_ADMIN**, method **denied()** fail-closed.
5. Tập group có thể rỗng: login vẫn hợp lệ nhưng không được làm operations cần **APP_REPORT_READ**.
6. Nếu DB outage, không fallback sang admin; phải có failure/limited-mode policy rõ.
7. Khi session đã có authorities mà nhóm bị thay đổi, quyền trong Authentication có thể stale; cần session revoke/permission version hoặc live check.

### 9.7. SecurityConfig.java

**src/main/java/com/example/directory/SecurityConfig.java**

~~~java
package com.example.directory;

import java.util.LinkedHashSet;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, LocalAuthorityService local)
            throws Exception {

        OidcUserService delegate = new OidcUserService();

        OAuth2UserService<OidcUserRequest, OidcUser> enriched =
                request -> {
            // Tại đây Spring OAuth2/OIDC login đã xác minh ID Token.
            OidcUser principal = delegate.loadUser(request);
            String issuer =
                    principal.getIdToken().getClaimAsString("iss");
            String subject = principal.getSubject();

            LocalAuthorityService.LocalProfile profile =
                    local.load(issuer, subject);

            LinkedHashSet<GrantedAuthority> authorities =
                    new LinkedHashSet<>();

            // Giữ dấu hiệu authenticated OIDC, không lấy remote
            // group claim để tự cấp ROLE_ADMIN.
            for (GrantedAuthority authority :
                    principal.getAuthorities()) {
                if (authority instanceof OidcUserAuthority) {
                    authorities.add(authority);
                }
            }

            for (String code : profile.permissions()) {
                authorities.add(new SimpleGrantedAuthority(code));
            }

            return new DefaultOidcUser(authorities,
                principal.getIdToken(), principal.getUserInfo(), "sub");
        };

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(enriched)));

        return http.build();
    }
}
~~~

**OidcUserRequest** là kiểu trong **org.springframework.security.oauth2.client.oidc.userinfo**; **OidcUserAuthority** và **DefaultOidcUser** nằm trong **org.springframework.security.oauth2.core.oidc.user**. **OAuth2Error** và **OAuth2AuthenticationException** thuộc **org.springframework.security.oauth2.core**, không phải namespace org.springframework.oauth2.

**Điểm an toàn:**

- OIDC code exchange/ID Token signature/issuer/audience/nonce được Spring xử lý trước khi gọi OidcUserService.
- **delegate.loadUser** giữ behavior framework với UserInfo/ID Token; enriched chỉ thực hiện local group lookup.
- Không lấy **email** hoặc **preferred_username** làm local account key.
- Chỉ giữ **OidcUserAuthority** của verified user, tránh nhầm **SCOPE_** với business authorities. Nếu app cần các scopes để gọi Resource API, thiết kế cách giữ chúng riêng có policy.
- **DefaultOidcUser** giữ ID Token/UserInfo, thêm permissions từ local DB, không tự tạo một token đã xác thực từ browser input.
- **@EnableMethodSecurity** là bắt buộc để @PreAuthorize hoạt động. Spring Boot security starter không tự bật method security.
- Local authorities nạp lúc login có thể stale, cần revalidation/session revoke cho dữ liệu nhạy cảm.

### 9.8. ReportsController.java

**src/main/java/com/example/directory/ReportsController.java**

~~~java
package com.example.directory;

import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {
    private final LocalAuthorityService directory;

    public ReportsController(LocalAuthorityService directory) {
        this.directory = directory;
    }

    @GetMapping("/")
    public String home() {
        return "Federated directory ready";
    }

    @GetMapping("/corp/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser user) {
        var profile = directory.load(
            user.getIdToken().getClaimAsString("iss"),
            user.getSubject());
        return Map.of(
            "accountId", profile.accountId(),
            "displayName", profile.displayName(),
            "permissions", profile.permissions());
    }

    @PreAuthorize("hasAuthority('APP_REPORT_READ')")
    @GetMapping("/corp/reports")
    public String reports() {
        return "Corp report allowed";
    }
}
~~~

Vì **/corp/me** gọi lại local directory nên nó có thể phản ánh account/membership hiện tại, nhưng **/corp/reports** dùng authorities có trong Authentication tại thời điểm login. Nếu yêu cầu revoke gần tức thì cho report, phải **kiểm lại permission version/active membership tại service**, không chỉ tin @PreAuthorize trên session lâu dài. Với data thật, repository vẫn phải filter **tenant_id=corp** và resource owner theo policy.

### 9.9. Chạy và kỳ vọng

~~~bash
mvn spring-boot:run
~~~

- **GET /** trả **Federated directory ready** nếu app và OIDC client configuration khởi tạo được.
- Anonymous **GET /corp/me** được chuyển sang OIDC login.
- OIDC issuer và subject phải **khớp chính xác identity_links**; với sample issuer/sub chỉ là dữ liệu giả, admin phải liên kết với IdP sandbox thật.
- Nếu link active, local account active, membership corp active và groups hợp lệ, **GET /corp/me** trả JSON có **accountId=41, displayName=Alice** cùng hai APP_ permissions.
- **GET /corp/reports** được phép khi Authentication có **APP_REPORT_READ**, trả **Corp report allowed**.
- Issuer/sub không khớp, account disabled, membership revoked hoặc DB có unapproved authority code → login bị từ chối theo policy, không auto-grant.
- User có account/membership hợp lệ nhưng không có group FINANCE_READER → có thể login, nhưng **GET /corp/reports trả 403**.

**Không có OIDC Provider thật, verified issuer/sub, redirect URI và secrets hợp lệ thì không thể kiểm thử end-to-end login.** Việc compile demo Java17 độc lập không chứng minh token verification thật.

## 10. SAML2: tải local groups sau validated Response

Trong **Spring Security 6.3.x**, **OpenSaml4AuthenticationProvider** có thể cấu hình **setResponseAuthenticationConverter** để mở rộng kết quả đã được SAML2 provider xử lý. Không lẫn với **OpenSaml5AuthenticationProvider** ở version khác.

~~~text
Saml2WebSsoAuthenticationFilter
 -> Saml2AuthenticationTokenConverter (RelyingPartyRegistration)
 -> OpenSaml4AuthenticationProvider (SAML signature/conditions)
 -> validated Saml2Authentication and Saml2AuthenticatedPrincipal
 -> local issuer/stable subject -> account/tenant/groups
 -> mapped authorities -> service authorization
~~~

**Mảnh minh họa API, KHÔNG độc lập runnable vì thiếu provider bean/imports và business helper:**

~~~java
OpenSaml4AuthenticationProvider provider =
        new OpenSaml4AuthenticationProvider();

var delegate = OpenSaml4AuthenticationProvider
        .createDefaultResponseAuthenticationConverter();

provider.setResponseAuthenticationConverter(responseToken -> {
    Saml2Authentication saml = delegate.convert(responseToken);
    Saml2AuthenticatedPrincipal p =
            (Saml2AuthenticatedPrincipal) saml.getPrincipal();

    // resolve trusted RelyingPartyRegistration từ p,
    // suy ra IdP entityID được cấu hình và stable subject
    // đã được IdP release/ứng dụng phê duyệt.
    Collection<GrantedAuthority> mapped =
            loadLocalAuthoritiesAfterValidatedSaml(p);

    return new Saml2Authentication(p,
            saml.getSaml2Response(), mapped);
});
~~~

**loadLocalAuthoritiesAfterValidatedSaml** là helper business giả định; cần định nghĩa trong ứng dụng. Điểm extension này không được dùng để bỏ signature/time/audience/recipient validation. **NameID** có thể transient/email, không tự ổn định; dùng persistent NameID/immutable attribute theo trust contract và namespace theo IdP entityID.

Khi một IdP phục vụ nhiều tenants, verified IdP issuer **không thay membership**. A request user đã SAML authenticated vẫn phải kiểm local account, group/tenant và tài nguyên.

## 11. CAS và Kerberos: khác protocol nhưng cùng local directory layer

**CAS native flow:**

~~~text
CAS login -> CAS service ticket
 -> CasAuthenticationFilter -> CasAuthenticationProvider
 -> TicketValidator kiểm ST với CAS server
 -> local UserDetailsService / Directory
 -> groups/attributes/authorities + business authorization
~~~

**Kerberos/SPNEGO flow:**

~~~text
Browser Authorization: Negotiate
 -> SpnegoAuthenticationProcessingFilter
 -> KerberosServiceAuthenticationProvider
 -> SunJaasKerberosTicketValidator / GSS keytab
 -> verified principal user@REALM
 -> local UserDetailsService / Directory
 -> groups/attributes/authorities + business authorization
~~~

Không tin username, email hay X-User do request tự gửi; chỉ dùng principal **sau** CAS ticket hoặc Kerberos GSS verification. Nếu có nhiều CAS servers/realms, namespace local identity theo trust domain. Việc LDAP query groups không có nghĩa ứng dụng phải thực hiện lại password-based LDAP authentication.

## 12. LDAP/AD lookup: filter injection, nested membership và scale

Một directory có thể sử dụng:

~~~text
AD service user identity: objectGUID=...
LDAP entry DN: uid=alice,ou=people,dc=corp,dc=example,dc=org
Group DN: cn=FinanceReader,ou=groups,dc=corp,dc=example,dc=org
Group references: member / memberOf tùy schema
~~~

Các nguyên tắc:

1. **Lookup từ verified local account/immutable directory ID**, không từ email/username do browser tự chọn.
2. Dùng Spring LDAP **LdapTemplate** hoặc LDAP client có escape filter/parameter binding; không concat **(uid= + input + )** thủ công.
3. **LDAPS/StartTLS**, truststore/hostname validation; không tắt TLS verification.
4. Service account directory chỉ được đọc OU/attributes cần, không có Domain Admin privileges.
5. Paging, size limits, query timeouts, connect/read deadlines và circuit breaker để tránh login treo lâu.
6. Nested groups cần kiểm direct vs transitive semantics, giới hạn depth/cycle và tránh queries không giới hạn.
7. Group DN/objectGUID thường đáng tin hơn chỉ so common name; cùng CN giữa domains khác nhau chưa cùng authority.
8. Referrals/forest trust phải được allowlist; không auto-follow đến directory attacker.
9. Không đưa toàn bộ group list vào cookie/JWT/session nếu không cần; map thành permissions tối thiểu.
10. Group list và HR attributes có thể là dữ liệu nhạy cảm, cần access control, retention và audit.

**Nguồn directory bị lỗi không phải tín hiệu để cấp quyền mặc định.** Với báo cáo tài chính hay admin, fail closed; nếu doanh nghiệp cần limited offline mode, policy phải nêu rõ data/action nào được dùng, TTL và rủi ro.

## 13. Session/caching và thu hồi quyền

Một user login lúc 09:00, OIDC user service tải groups và gắn **APP_REPORT_READ** trong Authentication. Lúc 09:05 admin thu hồi FINANCE_READER. Nếu ứng dụng chỉ kiểm session authorities, user có thể tiếp tục đọc báo cáo tới khi phiên hết hạn.

Để kiểm soát **revocation window**, cân nhắc:

- **Permission version** trong directory/IGA và so version mỗi request hoặc tại sensitive operation.
- **SessionRegistry / Spring Session** để invalidate sessions sau account disable/group revoke trên mọi nodes.
- **Short-lived caches** với TTL theo risk; không giữ roles vô hạn.
- **Event-driven invalidation** từ SCIM/IGA/HR/AD connector có audit/retry.
- **Live permission/membership check** trong service/AuthorizationManager cho payroll/admin/cross-tenant.
- **Revalidate resource tenant**, không chỉ authority từ login.
- **Cache key** namespace theo account ID, tenant, policy version, không theo email.
- **Outage policy** rõ: không chuyển unavailable directory thành admin access.

Ví dụ cache key:

~~~text
authz:v5:account:41:tenant:corp:policy:27
~~~

**Đừng hứa quyền được thu hồi ngay chỉ vì JWT hoặc SAML Assertion có thời hạn ngắn.** Local session/authorization cache có vòng đời riêng và có thể tồn tại sau khi token login đã hết hiệu lực.

## 14. Multi-tenant và boundary ở tầng dữ liệu

**Anti-pattern:**

~~~sql
SELECT document_id, body FROM documents
WHERE document_id = :requestedDocument;
~~~

Nếu document ID của tenant khác bị đoán/biết, user đã authenticated có thể xem nhầm dữ liệu.

**Đúng hướng:**

~~~sql
SELECT document_id, body FROM documents
WHERE tenant_id = :authorizedTenant
  AND document_id = :requestedDocument;
~~~

**authorizedTenant** phải là tenant được server xác minh từ active membership, không nhận thẳng path/query/header khi chưa kiểm. Với INSERT/UPDATE/DELETE cũng phải có tenant predicate hoặc gán tenant từ verified context. Database RLS có thể bổ sung defense-in-depth nhưng không thay membership logic, và không bao phủ cache/search/blob/queue.

Một group **FINANCE_READER** ở tenant Partner không tự cấp quyền **FINANCE_READER** tại Corp. Nếu cho phép người dùng chọn tenant, phải kiểm membership và quyền theo tenant mỗi request; mẫu Spring phần 9 có **fixed tenant corp** để tránh suy diễn rằng một APP_REPORT_READ toàn cục an toàn trong mọi hệ thống đa tenant.

## 15. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| OIDC login thành công nhưng local directory trả no link | issuer/sub chưa được provision/link đúng. | Kiểm verified identity và onboarding, không dùng email fallback. |
| SAML login xong account đổi mỗi phiên | NameID transient được dùng làm stable key. | Chọn persistent NameID/immutable attribute đúng IdP contract. |
| Email giống nhưng accounts bị gộp | Identity link không namespace issuer. | PK(protocol,issuer,subject), quy trình verified linking. |
| IdP group Admin thành ROLE_ADMIN | Mapping tự động không có allowlist. | Server-controlled policy theo tenant/role. |
| User từ tenant A đọc dữ liệu B | Chỉ check authenticated() hoặc global role. | Local membership + data-layer tenant predicate. |
| Thêm group LDAP nhưng quyền không đổi | Session/authz cache chưa refresh. | Permission version/revoke/reauthorization. |
| LDAP query chậm/hết hạn | Nested groups, referral, search base quá rộng. | Timeouts, paging, bound depth, indexes. |
| LDAP group lookup lộ quyền | Filter injection từ user input. | Escaping/parameterized query, server-side account lookup. |
| User disabled vẫn truy cập | Session cũ/permissions cache còn. | Recheck status và revoke sessions. |
| OIDC SCOPE_read đọc được report | OAuth2 scope bị nhầm business role. | APP_REPORT_READ chỉ từ internal permission policy. |
| Trong DB có unapproved authority | Mapping drift, group policy bị sửa. | Reject code lạ, audit/approval. |
| GET protected trả 403 sau login | Local roles không đủ. | Phân biệt federated authentication success với business authz. |
| Directory down, user tự thành admin | Fail-open fallback. | Fail closed hoặc limited mode đã được phê duyệt. |
| Spring @PreAuthorize không chạy | Chưa bật @EnableMethodSecurity. | Bật method security, regression test. |
| Tất cả orgs dùng group có cùng tên | Thiếu tenant namespace. | Scope groups và permissions theo tenant ID. |

## 16. Ma trận kiểm thử tích hợp

Tách kiểm **federated validation**, **identity linking**, **directory membership**, **authority mapping** và **resource authorization**.

| # | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| 1 | OIDC issuer/sub đúng, account + membership active | Tải local groups/permissions. |
| 2 | ID Token signature/issuer/audience/nonce sai | Spring OIDC reject trước local lookup. |
| 3 | Cùng sub nhưng IdP issuer khác | NO_LINK; không ghép account. |
| 4 | Hai IdPs phát cùng email | Không tự link. |
| 5 | Identity link disabled | Deny login. |
| 6 | Local account disabled | Deny. |
| 7 | Membership tenant revoked | Deny tenant. |
| 8 | Corp user gọi Partner tenant | Deny khi thiếu membership Partner. |
| 9 | FINANCE_READER Corp group | APP_REPORT_READ Corp theo policy. |
| 10 | FINANCE_READER Partner group | Không tự cấp Corp permission. |
| 11 | Remote IdP claim ROLE_ADMIN chưa được ủy quyền | Không cấp ROLE_ADMIN. |
| 12 | Local unknown group | Deny hoặc ignore theo contract; không auto-elevate. |
| 13 | Group list empty | Login có thể pass, privileged endpoint 403. |
| 14 | Group vừa revoke trong active session | Revalidation/session version chặn theo SLA. |
| 15 | Directory DB outage | Không default-admin. |
| 16 | LDAP filter có ký tự đặc biệt | Không có LDAP injection. |
| 17 | AD nested group có cycle/depth quá lớn | Có giới hạn, không DoS. |
| 18 | LDAP referral trỏ ngoài trust | Không tự follow và cấp group. |
| 19 | IdP đổi issuer/sub khi migration | Verified account relinking. |
| 20 | SAML NameID transient thay theo phiên | Không dùng làm permanent identity key. |
| 21 | CAS servers khác nhau cùng username | Không gộp identity. |
| 22 | Kerberos realms khác nhau cùng username | Không gộp identity. |
| 23 | Local group đa trị | Dedup, normalize có policy, không chỉ lấy đầu. |
| 24 | User biết document ID thuộc Partner | Data-layer tenant filter chặn. |
| 25 | JIT provisioning chưa được phê duyệt | Không tạo membership admin. |
| 26 | HR department đổi | ABAC cập nhật theo revalidation policy. |
| 27 | email_verified=true nhưng subject khác | Không link dựa email. |
| 28 | Session tồn tại node khác sau revoke | Shared session invalidation đúng. |
| 29 | Authority_code trong DB không có allowlist | Fail-closed. |
| 30 | Userinfo có attributes quá lớn/sai kiểu | Schema/size validation, không bypass. |
| 31 | User thiếu APP_REPORT_READ | @PreAuthorize trả 403. |
| 32 | @EnableMethodSecurity bị bỏ | Regression test phát hiện enforcement mất. |
| 33 | OAuth2 SCOPE_read nhưng không APP_REPORT_READ | Report 403. |
| 34 | IdP session vẫn còn sau local logout | Re-login vẫn kiểm account/permissions mới. |
| 35 | Audit account linking và role change | Có policy/actor/tenant, không lộ tokens. |

**Không chỉ test một ID Token có chữ ký sai**: lỗi signature chặn trước khi group mapping, nên chưa chứng minh local directory ACL hoạt động. Hãy dùng SSO hợp lệ từ sandbox rồi thử sai tenant, sai group, disabled account và stale session.

## 17. Checklist production

**Danh tính và account**

- [ ] External identity được framework xác minh trước khi group lookup.
- [ ] Identity key có protocol+issuer/realm+stable subject; không auto-match email.
- [ ] Account linking/JIT provisioning có approval và audit.
- [ ] Active status và tenant membership được kiểm server-side.
- [ ] SAML persistent NameID/immutable attribute và OIDC sub lifecycle có contract.

**Directory và roles**

- [ ] Directory authoritative source rõ cho từng thuộc tính/group.
- [ ] LDAP/AD dùng TLS, read-only credentials, escaping, paging/timeouts/depth limits.
- [ ] SCIM/IGA synchronization có SLA, retry, reconciliation.
- [ ] Group→permission mapping có allowlist, tenant scope, least privilege.
- [ ] Không map mọi remote groups thành Spring ROLE_ADMIN.
- [ ] Không nhầm OAuth2 scopes với business permissions.

**Spring và authorization**

- [ ] OIDC oidcUserService delegate trước khi lấy local groups.
- [ ] SAML2 response converter tùy version, không bỏ validation provider.
- [ ] CAS/Kerberos chỉ đọc local account sau ticket/GSS validation.
- [ ] @EnableMethodSecurity và @PreAuthorize có tests.
- [ ] Sensitive permissions revalidated theo SLA; session revocation/cache invalidation.
- [ ] Data-layer tenant predicates, cross-tenant tests và audit.
- [ ] Directory outage fail closed hoặc limited policy được phê duyệt.

## 18. Câu hỏi ôn tập

**1. IdP xác thực thành công có cho user tất cả quyền app không?**  
Không. IdP xác nhận identity; local account, groups, tenant membership và resource policy mới quyết định quyền.

**2. Vì sao nên dùng issuer+sub của OIDC thay email?**  
Vì email có thể thay đổi/tái cấp/trùng nhiều IdPs; subject được hiểu trong phạm vi issuer.

**3. SAML2 NameID có luôn ổn định không?**  
Không. Transient NameID không phù hợp linking dài hạn; phải có persistent NameID hoặc immutable attribute theo contract.

**4. LDAP group Admin có tự thành ROLE_ADMIN không?**  
Không. Cần chính sách ánh xạ minh bạch, least privilege và tenant scope.

**5. Khi nào OIDC user service lấy local group?**  
Sau khi Spring OIDC validation tạo verified principal; không lấy dữ liệu tự khai trước authentication.

**6. User có role lúc login rồi bị revoke, vì sao session vẫn có role?**  
Authorities đã được lưu trong Authentication. Cần permission version, session revoke hoặc live authorization.

**7. OIDC access-token SCOPE_read có cho đọc báo cáo APP_REPORT_READ không?**  
Không nếu không có policy ánh xạ rõ; chúng là hai dạng quyền khác.

**8. LDAP group lookup sau SSO có cần password user để bind lần nữa không?**  
Không. App dùng directory service client read-only; authentication đã xảy ra với IdP.

**9. Đã kiểm APP_REPORT_READ, vì sao vẫn cần tenant_id trong query?**  
Authority không tự xác minh resource ownership hoặc tenant. Query phải scope đúng tài nguyên.

**10. Nếu directory bị lỗi, có nên gán ROLE_USER hoặc ADMIN mặc định?**  
Không. Fail closed hoặc limited mode được phê duyệt, không auto-elevate khi dependency outage.

## 19. Tài liệu chính thống

1. [Spring Security 6.x — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): mapping user authorities, delegation-based OIDC user service.
2. [Spring Security 6.3 — OidcUserService Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): OIDC user loading customization.
3. [Spring Security 6.3 — DefaultOidcUser Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html): ID Token/UserInfo và authorities.
4. [Spring Security 6.3 — OpenSaml4AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): SAML response converter.
5. [Spring Security — SAML2 Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): validated Response/principal mapping (chú ý version 7.x).
6. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): @EnableMethodSecurity và @PreAuthorize.
7. [Spring LDAP — Reference](https://docs.spring.io/spring-ldap/reference/): LdapTemplate, search và directory integration.
8. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer, subject, UserInfo và ID Token verification.
9. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID, issuer và AttributeStatement.
10. [RFC 7643 — SCIM Schema](https://www.rfc-editor.org/rfc/rfc7643), [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): user/group provisioning.
11. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, authorization mỗi request.
12. [OWASP — Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): tenant scoping và data isolation.

**Kết luận:** Sau khi xác thực liên kết, ứng dụng phải **map danh tính đã xác minh (issuer+stable subject) sang local account**, nạp groups/attributes từ **nguồn có thẩm quyền**, dùng **local allowlist** chuyển thành business permissions, rồi kiểm **tenant/resource** khi thực hiện API. Không auto-link bằng email, không auto-role từ group IdP, không giữ quyền đã thu hồi vô thời hạn trong session.
