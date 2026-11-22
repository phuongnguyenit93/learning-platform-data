# Ánh xạ nhóm SAML thành quyền nội bộ theo danh sách được cho phép

## 1. Bài toán thực hành: IdP trả nhóm, ứng dụng phải quyết định quyền

Một ứng dụng Spring Boot đóng vai trò **SAML 2.0 Service Provider (SP)** nhận SAML Response từ Identity Provider (IdP). IdP xác thực nhân viên và có thể trả các AttributeStatements, chẳng hạn nhóm nhân sự, phòng ban hoặc mã nhóm trong Active Directory/Entra ID. Ứng dụng muốn cấp quyền đọc báo cáo, phê duyệt hoặc thao tác nghiệp vụ tùy nhóm. Đây là một bài toán **authorization mapping**, không phải thao tác sao chép tên nhóm từ IdP vào vai trò Spring Security.

Ví dụ thông tin sau khi SAML Response đã được xác minh:

~~~text
SAML IdP issuer   : https://idp-a.example.org/metadata
Registration ID   : corp-a
NameID            : persistent-employee-482
Attribute Name    : urn:example:claims:group-id
Attribute values  :
  - grp:finance-readers
  - grp:finance-approvers
  - grp:external-admin
Tenant            : tenant-a
~~~

Ứng dụng chỉ cho phép hai ánh xạ đã được quản trị:

~~~text
(corp-a, tenant-a, grp:finance-readers)
       -> TENANT_A_REPORT_READ

(corp-a, tenant-a, grp:finance-approvers)
       -> TENANT_A_REPORT_APPROVE

grp:external-admin
       -> KHÔNG ÁNH XẠ
~~~

Kết quả là `TENANT_A_REPORT_READ` và `TENANT_A_REPORT_APPROVE`, **không** có `ROLE_ADMIN` hoặc `ROLE_SUPER_ADMIN`.

Bài Knowledge thuộc **Spring Security - federation → Thực hành tổng hợp** với đề bài **“Ánh xạ nhóm SAML thành quyền nội bộ theo danh sách được cho phép”**.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt **SAML Authentication**, **AttributeStatements**, **GrantedAuthority**, **role**, **permission**, **local account** và **tenant**.
2. Hiểu tại sao `groups`, `memberOf`, `roles` là **dữ liệu từ IdP**, không tự động thành quyền ứng dụng.
3. Trích đúng **mọi giá trị** trong một SAML attribute nhiều giá trị, không chỉ `getFirstAttribute()`.
4. Thiết kế **allowlist ánh xạ chính xác**, scoped theo IdP registration/issuer và tenant.
5. Dùng `SimpleGrantedAuthority` và `hasAuthority`/`hasRole` đúng tiền tố, tránh grant thừa.
6. Không cấp quyền đặc biệt từ các chuỗi `Admin`, `ROLE_ADMIN`, wildcard hoặc email chưa đủ bằng chứng.
7. Gắn verified external identity vào app-local account ổn định, kiểm `active`, membership và policy.
8. Phân biệt cấp **quyền chức năng** với quyền truy cập **resource của tenant hoặc đối tượng cụ thể**.
9. Tích hợp qua Spring SAML2 provider/response authentication converter phù hợp Spring Security 6.x/7.x.
10. Giữ nguyên chữ ký XML, Issuer, Audience, Recipient, time và request correlation khi custom authorities.
11. Thiết kế bộ unit, integration và negative tests cho nhóm trùng tên, nhóm lạ, group spoofing, revoked groups và multi-IdP.
12. Chạy chương trình **Java 17 độc lập** mô phỏng allowlist, cho stdout xác định, không cần Spring.
13. Kiểm khả năng thay đổi nhóm sau login, session stale, event provisioning và privilege revocation.
14. Có checklist bảo mật, runbook vận hành và tiêu chí QA trước release.

**Ngữ cảnh:** Java 17+, Spring Boot 3.x, Spring Security Servlet SAML2 Login; hai phiên bản tiêu biểu là Spring Security 6.x với OpenSAML provider tương ứng và 7.x với `OpenSaml5AuthenticationProvider`. Những URL `example.org`, group IDs và permission strings trong bài chỉ là ví dụ; trong hệ thật phải dùng metadata và danh mục groups do tổ chức cấp.

---

## 2. Luồng dữ liệu: chỉ ánh xạ sau SAML verification

~~~mermaid
sequenceDiagram
  participant Browser
  participant IdP
  participant SP as Spring Security SP
  participant Policy as Group Allowlist + Account Policy
  participant App as Protected Resource
  Browser->>SP: GET /reports
  SP-->>Browser: Redirect SAML AuthnRequest
  Browser->>IdP: AuthnRequest + login
  IdP-->>Browser: SAMLResponse với AttributeStatement
  Browser->>SP: POST ACS /login/saml2/sso/corp-a
  SP->>SP: Verify trust, XML signature, Issuer, Audience, time, subject
  alt SAML invalid
    SP-->>Browser: Authentication failure
  else SAML verified
    SP->>Policy: Verified issuer/subject + group values
    Policy->>Policy: Account ACTIVE, tenant membership, explicit allowlist
    Policy-->>SP: Internal GrantedAuthority subset
    SP->>SP: Create Authentication/SecurityContext
    Browser->>App: GET /tenants/tenant-a/reports/42
    App->>App: Check current account + tenant + object permission
    App-->>Browser: 200 only when authorized
  end
~~~

**Bắt buộc giữ ba ranh giới tách biệt:**

- **AuthN trust:** SAML Response/Assertion phải qua `Saml2WebSsoAuthenticationFilter`, token converter, `RelyingPartyRegistration`, OpenSAML signature/issuer/audience/time/subject validators.
- **Group-to-authority mapping:** chỉ sau khi Response hợp lệ, ánh xạ nhóm theo **danh sách cho phép do ứng dụng kiểm soát**, không theo tên nhóm chưa kiểm.
- **Resource AuthZ:** permission có thể được tạo thành GrantedAuthority nhưng **vẫn phải check** resource ownership, active tenant membership, account state và chính sách hiện hành.

Nếu XML signature không hợp lệ, **không có** bước “cứ đọc AttributeStatement để xem nhóm có hợp lệ không”. Group extraction từ một XML chưa verified là dữ liệu không tin cậy.

### Default Spring SAML authority có phải groups không?

Theo Spring Security SAML2 reference, response authentication converter mặc định tạo principal có các SAML attributes và cấp authority cơ bản như `ROLE_USER` (tùy version còn có factor marker). **Không mặc định** mọi SAML `groups` biến thành `ROLE_*`. Như vậy:
- Người dùng SSO có thể authenticated nhưng chưa được cấp quyền nghiệp vụ.
- Phải cấu hình **explicit mapping** để có `TENANT_A_REPORT_READ`, `REPORT_EXPORT` hoặc vai trò được app thiết kế.
- `isAuthenticated()` không nên đủ để truy cập endpoint nhạy cảm.
- `ROLE_USER` không có nghĩa user thuộc tenant nào hoặc được xem tài liệu nào.

## 3. SAML AttributeStatement và đặc điểm nhóm

Một Assertion có thể có các attributes như sau:

~~~xml
<saml:AttributeStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute
      Name="urn:example:claims:group-id"
      NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
      FriendlyName="groups">
    <saml:AttributeValue
        xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:type="xs:string">grp:finance-readers</saml:AttributeValue>
    <saml:AttributeValue
        xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:type="xs:string">grp:finance-approvers</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
~~~

**XML trên chỉ là cấu trúc minh họa, không phải một SAML Response có chữ ký.** Khi kiểm thử tích hợp, cần SAML Response/Assertion đã ký đúng và chứa attribute này trong nội dung được bảo vệ theo profile.

Thuộc tính `Attribute` có thể chứa:
- `Name`: tên có tính hợp đồng; có thể là URI/OID/string.
- `NameFormat`: ngữ nghĩa định dạng tên attribute, phải hiểu cùng metadata.
- `FriendlyName`: tên gợi nhớ, không nên được xem là khóa duy nhất cho policy.
- `AttributeValue`: có thể **nhiều giá trị**, có thể là string hoặc cấu trúc XML tùy IdP/OpenSAML.
- `EncryptedAttribute`: một số IdP mã hóa attribute; chỉ xử lý sau decryption hợp lệ.

### Ví dụ nhiều IdP biểu diễn nhóm khác nhau

| IdP | Attribute Name | Kiểu giá trị minh họa | Lưu ý |
| --- | --- | --- | --- |
| SAML IdP A | `urn:example:claims:group-id` | `grp:finance-readers` | Stable group ID được app allowlist |
| SAML IdP B | `memberOf` | `CN=Finance,OU=Groups,DC=b,DC=example,DC=org` | DN có dấu phẩy; không split bằng dấu phẩy |
| SAML IdP C | URI/OID từ federation contract | Directory object GUID | Phải chuẩn hóa encoding đã được thỏa thuận |
| SAML IdP D | `groups` | `Finance Readers` | Tên hiển thị mutable, dễ va chạm |
| SAML IdP E | `roles` | `ROLE_ADMIN` | Không tự lấy làm Spring authority |

**Không có một SAML attribute group name phổ quát cho mọi IdP.** Phải thống nhất IdP nào phát attribute `Name`, `NameFormat`, kiểu giá trị và semantics nào. Nếu IdP không phát groups, thực thi chính sách fail closed: không thêm quyền nghiệp vụ ngoài những quyền đã được local account service xác minh.

## 4. Dùng ID nhóm bền vững, không mặc định dùng display name

Tên hiển thị:
- Có thể đổi khi phòng ban đổi tên.
- Có thể trùng ở nhiều directory hoặc OU.
- Có thể khác hoa/thường do case normalization.
- Có thể chứa unicode, dấu cách, ký tự phân tách.
- Có thể được tái sử dụng cho một nhóm mới sau khi nhóm cũ xóa.

Vì vậy, nếu hạ tầng IdP có **immutable group object ID**, ưu tiên dùng ID đó (sau khi thỏa thuận đúng nghĩa và namespace). Nếu chỉ có DN/role names, phải:
1. Xác định **IdP issuer** và directory scope.
2. Dùng phép so sánh chính xác được quy định trong contract.
3. Ghi rõ normalization rules, tránh tự `toLowerCase()` toàn bộ.
4. Rà soát khi rename/reparent/recreate group.
5. Không lấy `FriendlyName` thay `Name` nếu hai tên có thể trùng.
6. Phân biệt string "Finance" trong IdP A với string "Finance" trong IdP B.
7. Kiểm phiên bản mapping và trách nhiệm phê duyệt thay đổi.

### Đừng split group DN theo dấu phẩy

Ví dụ:

~~~text
CN=Finance,OU=Groups,DC=corp,DC=example,DC=org
~~~

Đây là **một** DN, không phải năm groups. Nếu viết `value.split(",")`, app có thể tạo các "group" giả như `CN=Finance` và `OU=Groups`, dẫn đến hiểu sai quyền. Nếu IdP trả multiple `AttributeValue`, mỗi phần tử mới là một group value theo contract. Nếu IdP trả serialized list string, parser phải theo **đúng định dạng đã được ký kết**, không tự đoán delimiter.

### Kiểm group values có kiểu hợp lệ

Spring `Saml2AuthenticatedPrincipal#getAttribute(name)`/`Saml2ResponseAssertionAccessor#getAttribute(name)` có thể trả `List<A>` và `getAttributes()` là `Map<String, List<Object>>`. Khi mapping:
- Dùng **toàn bộ list**.
- Chỉ map các giá trị thuộc kiểu mà policy cho phép, thường string IDs.
- Với XML cấu trúc lạ hoặc giá trị không hợp lệ, không gọi `toString()` rồi coi là role.
- Hạn chế số lượng/kích thước attribute values để chống DoS nếu IdP compromised.
- Lọc duplicate bằng `Set`, nhưng không tạo quyền mới ngoài allowlist.
- Không mặc định mọi attribute `groups` đều có giá trị.

## 5. Allowlist là một bảng quyết định, không phải "prefix group"

Một allowlist nên có khóa ánh xạ rõ ràng:

~~~text
(relying-party registration / IdP issuer,
 app tenant,
 exact SAML attribute Name / NameFormat contract,
 exact external group identifier)
     -> approved internal authority set
~~~

Ví dụ:

| Registration | Tenant | Attribute Name | External Group ID | Authority |
| --- | --- | --- | --- | --- |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:finance-readers` | `TENANT_A_REPORT_READ` |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:finance-approvers` | `TENANT_A_REPORT_APPROVE` |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:auditors` | `TENANT_A_AUDIT_READ` |
| `partner-b` | `tenant-b` | `urn:example:claims:group-id` | `grp:finance-readers` | `TENANT_B_REPORT_READ` |
| `partner-b` | `tenant-a` | `urn:example:claims:group-id` | `grp:finance-readers` | **No mapping** |
| `corp-a` | `tenant-a` | `urn:example:claims:group-id` | `grp:external-admin` | **No mapping** |

Một group ID trùng ở hai IdP **không** khiến roles giống nhau. Những values chưa được nhập vào bảng là **unknown** và cho ra empty authority addition.

### Các chính sách cần ghi rõ

1. **Deny by default** đối với mọi group không có trong allowlist.
2. Không hỗ trợ wildcard `*`, contains-match, regex tùy tiện hoặc `startsWith("admin")`.
3. Không cho IdP tự gửi tên nội bộ `ROLE_ADMIN` để bỏ qua bảng.
4. **Không auto-provision mapping** khi thấy group mới.
5. Không infer privileged authority từ email domain/department/display name.
6. Global/system admin phải có approval riêng; tốt nhất không ánh xạ trực tiếp từ external groups nếu không có governance.
7. Nếu tenant/user bị disable, không grant dù group match.
8. Mapping change phải versioned, reviewed, audited và rollout có kiểm thử.
9. Mỗi authority phải có mô tả mục đích và phạm vi tenant/object.
10. Không union vô điều kiện tất cả roles từ nhiều IdPs vào một account.

## 6. `GrantedAuthority`, `ROLE_`, `hasRole` và `hasAuthority`

Spring Security dùng `GrantedAuthority` để thể hiện quyền trong `Authentication`.

Ví dụ:

~~~java
new SimpleGrantedAuthority("TENANT_A_REPORT_READ")
~~~

Với permission dạng custom authority:

~~~java
@PreAuthorize("hasAuthority('TENANT_A_REPORT_READ')")
public Report readTenantAReport(...) { ... }
~~~

Khi dùng role style:

~~~java
new SimpleGrantedAuthority("ROLE_REPORT_VIEWER")
~~~

và:

~~~java
@PreAuthorize("hasRole('REPORT_VIEWER')")
public Report readReport(...) { ... }
~~~

`hasRole("REPORT_VIEWER")` thường so với authority `ROLE_REPORT_VIEWER` dựa trên role prefix mặc định. Nếu bạn gọi `hasAuthority("REPORT_VIEWER")`, đó là so khớp **exact string** không tự thêm prefix. Custom default role prefix có thể được cấu hình; phải kiểm Spring Security version/config.

### Một số lỗi nhỏ có hậu quả lớn

| Mapping thành | Guard dùng | Kết quả |
| --- | --- | --- |
| `ROLE_REPORT_VIEWER` | `hasRole('REPORT_VIEWER')` | Phù hợp convention mặc định |
| `TENANT_A_REPORT_READ` | `hasAuthority('TENANT_A_REPORT_READ')` | Exact permission |
| `ROLE_REPORT_VIEWER` | `hasAuthority('REPORT_VIEWER')` | Thường fail vì khác string |
| `ROLE_ADMIN` do IdP tự gửi | `hasRole('ADMIN')` | **Nguy cơ leo thang quyền** |
| `TENANT_A_REPORT_READ` | Chỉ `isAuthenticated()` | Permission không được kiểm |
| `TENANT_A_REPORT_READ` | `hasAuthority('TENANT_B_REPORT_READ')` | Không hợp tenant |
| `ROLE_USER` mặc định | `hasRole('ADMIN')` | Không đủ |
| `ROLE_USER` mặc định | `isAuthenticated()` | Có thể cho vào route nếu thiết kế guard quá rộng |

**`ROLE_USER` mặc định không nên được dùng làm bằng chứng có quyền đọc mọi dữ liệu nội bộ.**

## 7. Trách nhiệm bảo mật trước khi ánh xạ

Một mapper **không có nhiệm vụ xác minh chữ ký XML**. Nó phải chỉ được gọi **sau** OpenSAML provider xác minh:
1. Response/Assertion Signature với certificate IdP được SP tin cậy.
2. Response/Assertion Issuer và đúng relying party registration.
3. Destination, AudienceRestriction, Recipient.
4. NotBefore/NotOnOrAfter và bearer subject confirmation.
5. Request correlation/InResponseTo theo SP-initiated flow.
6. SAML Status và assertions hợp lệ.
7. Decryption cho encrypted assertions/attributes nếu IdP sử dụng.
8. XML structure và signature reference scope.
9. Các additional validations/replay policy mà ứng dụng yêu cầu.

Nếu mapper dùng direct `Base64.getDecoder().decode(request.getParameter("SAMLResponse"))` rồi trích `groups` thì **chưa có trust boundary**. Một người có thể tự tạo XML chứa `Admin` và thử cấp quyền.

### Tin cậy theo nguồn, không chỉ theo giá trị

Một group value `"grp:finance-approvers"` có thể được IdP A phát hợp lệ, IdP B cũng có group string tương tự. App chỉ nên cho IdP B cấp quyền đối với những authority mà chính IdP B được ủy quyền theo **approved policy**. Bản thân group string không chứa bằng chứng ai có quyền cấp nó.

## 8. Danh mục quyền nội bộ có phiên bản và quản trị

Ví dụ policy:

~~~yaml
# Ví dụ dữ liệu ứng dụng; không phải Spring Boot property tự hiểu.
saml-group-authority-policy:
  version: "2026-11-07"
  registrations:
    corp-a:
      expected-issuer: "https://idp-a.example.org/metadata"
      attribute-name: "urn:example:claims:group-id"
      tenants:
        tenant-a:
          "grp:finance-readers":
            - TENANT_A_REPORT_READ
          "grp:finance-approvers":
            - TENANT_A_REPORT_APPROVE
          "grp:auditors":
            - TENANT_A_AUDIT_READ
    partner-b:
      expected-issuer: "https://idp-b.example.org/metadata"
      attribute-name: "urn:example:claims:group-id"
      tenants:
        tenant-b:
          "grp:finance-readers":
            - TENANT_B_REPORT_READ
~~~

**Đây là schema tự định nghĩa của ứng dụng**, không có auto-binding mapper mặc định nào trong Spring Security chỉ nhờ khai YAML này. Dev phải tạo `@ConfigurationProperties`/policy service, validate config và kiểm against approved list.

### Ràng buộc config khi khởi động

- Reject duplicate mapping keys có conflict.
- Reject unknown internal authority strings, nếu policy danh mục quyền cố định.
- Reject unauthorized mapping từ external group tới `ROLE_SUPER_ADMIN`.
- Reject blank issuer, blank group ID, unsafe wildcard.
- Không silently merge hai registrations có cùng group ID vào một namespace.
- Kiểm `expected-issuer` khớp trusted SAML metadata/configuration.
- Với production, chỉ ops/security policy admin được sửa.
- Config qua version control + PR review + CI tests; không chấp nhận config from untrusted IdP claims.
- Không ghi mapping vào session như dữ liệu không thể thay đổi mãi mãi.

### Có nên đặt allowlist ở database?

Có thể, khi doanh nghiệp có nhiều tenants và policy cần thay thường xuyên:
- Bảng `external_group_authority_map` với `registration_id`, `issuer`, `tenant_id`, `attribute_name`, `external_group_id`, `internal_authority`, `approved_at`, `approved_by`, `version`, `active`.
- Unique key composite tránh collision.
- Admin UI phải có RBAC và dual control cho privileged changes.
- Áp transaction/rollback, audit immutable.
- Cache policy có TTL/version và invalidation.
- Từ chối nếu policy registry unavailable theo mức an ninh yêu cầu; không fallback “grant everyone”.

Cơ sở dữ liệu allowlist **không** làm IdP group claim đáng tin hơn nếu chữ ký/issuer chưa được xác minh.

## 9. Cần local account binding chứ không chỉ `NameID`

SAML `NameID` có thể:
- Là persistent identifier theo quan hệ IdP–SP;
- Là transient identifier ngắn hạn;
- Là email-style identifier có thể đổi/tái cấp;
- Là unspecified string với semantics của IdP.

Một enterprise app nên map external identity đã verified sang `appAccountId` bất biến. Nên scope theo:
- IdP issuer/entityID/registration trust context;
- NameID format và qualifiers nếu profile dùng;
- Subject value hoặc stable directory ID theo hợp đồng;
- Tenant/account linking governance.

Không dùng email/username/NameID text **không scoped** làm primary account key. Kiểm account **ACTIVE**, membership/role hiện hành và status của tenant **trước khi cấp quyền**.

### Một IdP phục vụ nhiều tenants

IdP xác thực user A không đồng nghĩa user A thuộc mọi tenants có cùng IdP. Ví dụ:
- `corp-a` là IdP của cả tenant-a và tenant-c.
- User có nhóm `grp:finance-readers` nhưng chỉ có membership tenant-a.
- Bảng group mapping cho tenant-c có thể cũng có group tương tự.

**Phải kiểm local membership tenant-c**, không lấy tên IdP thay membership. Mọi tài nguyên phải check tenantId/ACL riêng.

## 10. Group attribute nhiều giá trị: không dùng giá trị đầu tiên

Spring Security 6.x có thể cung cấp:

~~~java
Saml2AuthenticatedPrincipal principal = ...;
List<String> groups =
        principal.getAttribute("urn:example:claims:group-id");
~~~

Đây là **snippet Spring API**, không phải Java standalone. `getAttribute` có thể trả null, cần xử lý. `getFirstAttribute()` trả một giá trị, **không thích hợp** nếu IdP có thể trả nhiều groups.

Spring Security 7.x đưa `Saml2AssertionAuthentication` cùng `Saml2ResponseAssertionAccessor`, và `Saml2AuthenticatedPrincipal` đã được deprecated trong nhánh này; với implementation mới, ưu tiên lấy attributes từ accessor:

~~~java
if (authentication instanceof Saml2AssertionAuthentication saml) {
    Saml2ResponseAssertionAccessor verifiedAssertion =
            saml.getCredentials();
    List<Object> groups = verifiedAssertion
            .getAttributes()
            .getOrDefault(
                "urn:example:claims:group-id",
                List.of());
    // Apply application-approved allowlist only.
}
~~~

Cần các imports và Spring 7.x dependencies tương ứng; đây **không phải test tự chạy bằng javac**. Tránh gọi đoạn này trước khi `AuthenticationManager` đã xác thực SAML. Nếu dùng compatibility layer phải giữ đúng SLO credential/accessor behavior.

### Kiểm kiểu dữ liệu

Trong `Map<String,List<Object>>`, từng phần tử có thể là kiểu khác string. Ví dụ:

~~~java
for (Object rawValue : groups) {
    if (!(rawValue instanceof String groupId)) {
        // Reject/ignore unsupported group value by policy.
        continue;
    }
    // Lookup exact allowlist by issuer/registration/tenant/groupId.
}
~~~

Không:
- `rawValue.toString()` trên object tùy ý rồi cấp quyền;
- Split comma nếu IdP trả DN;
- Auto-trim/lowercase nếu IdP contract không quy định;
- Kết nối mỗi external group thành `ROLE_` + group string;
- Lấy `<Attribute FriendlyName="roles">` mà không kiểm `Attribute Name`;
- Coi `groups=null` là “mọi nhóm”.

## 11. Thiết kế service ánh xạ: đầu vào và đầu ra

Một API business thuần không cần phụ thuộc trực tiếp OpenSAML:

~~~java
Set<String> resolveAuthorities(
        VerifiedSamlIdentity identity,
        ActiveAccount account,
        String requestedTenantId,
        Map<String, List<Object>> verifiedAttributes);
~~~

**Các types `VerifiedSamlIdentity` và `ActiveAccount` là ứng dụng tự định nghĩa**, không phải Spring classes. Input `VerifiedSamlIdentity` chỉ nên được tạo từ provider/callback đã xác minh, không từ body hoặc header tự gửi của người dùng.

Service cần:

1. Lookup exact external identity → local account, từ chối unknown/disabled.
2. Xác nhận `requestedTenantId` là tenant user có active membership.
3. Xác minh IdP/registration được tenant tin theo approved policy.
4. Chỉ đọc tên Attribute đã được phê duyệt cho registration.
5. Chuyển từng group value thành một exact lookup key có issuer/tenant scope.
6. Union chỉ **những internal authorities được allowlist**.
7. Không tạo system admin authority từ unknown/extra groups.
8. Deduplicate results, output immutable set.
9. Có audit event về số lượng accepted/rejected groups, policy version; không log raw sensitive group membership nếu không cần.
10. Hỗ trợ revoke/refresh chính sách khi user bị chuyển group hoặc xóa tài khoản.

### Tại sao không chỉ `map.get(groupId)`?

Vì IdP A và IdP B có thể đều có `Finance` hoặc `Admins`. Một bare `Map<String,String>` không phân biệt:
- Trust domain/issuer;
- Tenant;
- Attribute semantics;
- Group identifier origin;
- Environment (prod vs test);
- Approval history;
- Authority scope.

Giảm namespace xuống một string là nguyên nhân phổ biến của **confused deputy** và cross-tenant privilege escalation.

## 12. Spring Security 7.x: dùng response authentication converter

Theo tài liệu Spring Security, `OpenSaml5AuthenticationProvider#setResponseAuthenticationConverter` là customization point cho `Authentication` sau khi response/assertion được xác thực. `ResponseAuthenticationConverter` mặc định có thể dùng làm delegate để giữ việc trích principal, credentials và attributes theo framework.

Ví dụ **Spring Security 7.x integration pattern** với policy service do ứng dụng triển khai:

~~~java
package com.example.security;

import java.util.Collection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.*;
import org.springframework.security.saml2.provider.service.authentication
        .OpenSaml5AuthenticationProvider.ResponseAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlGroupSecurityConfig {

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            VerifiedGroupAuthorityPolicy policy) throws Exception {

        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        ResponseAuthenticationConverter defaults =
                new ResponseAuthenticationConverter();

        provider.setResponseAuthenticationConverter(responseToken -> {
            Saml2Authentication original = defaults.convert(responseToken);

            if (!(original instanceof Saml2AssertionAuthentication saml)) {
                throw new BadCredentialsException(
                        "Unsupported SAML authentication representation");
            }

            Collection<? extends GrantedAuthority> allowlisted =
                    policy.requireActiveAccountAndMap(
                            saml.getRelyingPartyRegistrationId(),
                            saml.getName(),
                            saml.getCredentials().getAttributes());

            return saml.toBuilder()
                    .authorities(existing -> {
                        existing.removeIf(authority ->
                                authority.getAuthority().startsWith(
                                        "TENANT_"));
                        existing.addAll(allowlisted);
                    })
                    .build();
        });

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health").permitAll()
                .anyRequest().authenticated());

        http.saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
~~~

**Rất quan trọng về đoạn code:**
- Đây là Spring configuration **có phụ thuộc project và service ứng dụng**, không biên dịch standalone. `VerifiedGroupAuthorityPolicy` phải được tự triển khai: resolve verified registration/issuer, link subject với active local account, kiểm tenant membership, chỉ cấp authorities allowlist, từ chối `unknown/disabled`. `saml.getName()` không tự là local account key bền vững, nên production phải map theo identity namespace đúng format/qualifiers.
- Đoạn này minh họa **7.x** (`Saml2AssertionAuthentication`, `toBuilder`, `authorities(Consumer)`); 6.x có APIs khác. Đối chiếu đúng phiên bản source/Javadoc trong project, đặc biệt khi nâng từ 6.x.
- `toBuilder()` trên `Saml2AssertionAuthentication` giúp giữ representation/accessor được framework dùng, có lợi cho SLO. **Không tùy tiện thay bằng `new Saml2Authentication` làm mất thông tin SAML assertion** nếu bản hiện hành cần accessor để xử lý logout.
- Trong ví dụ này, `existing.removeIf` loại mọi custom authority bắt đầu `TENANT_` (nếu có trước đó) rồi chỉ thêm allowlisted; chính sách production có thể chọn giữ/loại những authorities trusted khác theo convention của mình. **Không nên chỉ lọc theo prefix** nếu code trước đó có thể đã thêm quyền nguy hiểm từ nguồn không được tin: phải bảo đảm `defaults` và các converter khác không tự inject elevated roles; có thể bắt đầu từ một tập baseline allowlisted cụ thể.
- Default `ROLE_USER` hoặc SAML factor authority không tự cấp quyền business. Mỗi route nhạy cảm cần `hasAuthority`/policy service.
- Không dùng custom response converter để bỏ signature, issuer, recipient, audience hoặc condition validators: converter ở **sau** verification.
- Config cần `RelyingPartyRegistrationRepository`, IdP metadata/verification credentials đúng, dependency `spring-security-saml2-service-provider` và OpenSAML tương thích.
- Nếu app có nhiều `AuthenticationProvider` hoặc SSO methods, bảo đảm `AuthenticationManager` không vô tình loại provider dùng cho phương thức khác; thiết kế `ProviderManager` theo kiến trúc ứng dụng.

### Làm rõ kiểu `authorities(...)` trong Spring Security 7

Builder `AbstractAuthenticationToken.AbstractAuthenticationBuilder` dùng:

~~~java
.authorities(existingAuthorities -> {
    existingAuthorities.addAll(approvedAuthorities);
})
~~~

`authorities` nhận **Consumer của collection**, không phải mọi bản đều có overload nhận trực tiếp `Collection`. `Saml2AssertionAuthentication` có builder riêng; code `saml.toBuilder().authorities(...).build()` bảo tồn representation Spring 7.x khi API tương ứng được hỗ trợ.

### Alternative: local UserDetails/account authority lookup

Một hệ thống muốn toàn quyền do backend quản lý có thể:
1. Dùng default SAML response converter cho validated principal/attributes.
2. Lookup `accountId` bằng verified external identity.
3. Load local active account, tenant memberships, grants từ DB.
4. **Chỉ** dùng SAML groups để kích hoạt một số preapproved mappings, không cho chúng override revocations.
5. Tạo authentication authorities từ trusted local grants + authorized mapping.
6. Revalidate permissions ở resource boundary.

Spring docs có ví dụ response converter phối hợp `UserDetailsService`. Với Spring 7.x có `Saml2AssertionAuthentication` và accessor hỗ trợ giữ SAML information; khi chuyển principal sang local user object cần test SLO và principal conversion. Không coi `UserDetailsService#loadUserByUsername(NameID)` là an toàn nếu NameID không scoped theo IdP.

## 13. Spring Security 6.x: cần đọc API đúng version

Trong Spring Security 6.x:
- Có các implementations `OpenSaml4AuthenticationProvider` hoặc `OpenSaml5AuthenticationProvider` tùy version/dependencies.
- Authentication có thể là `Saml2Authentication` với `Saml2AuthenticatedPrincipal`.
- Thường có thể custom `setResponseAuthenticationConverter` với converter theo provider đang dùng.
- Các nested types như `ResponseToken`, `ResponseAuthenticationConverter` và constructors khác nhau; **không giả định cú pháp 7.x biên dịch nguyên xi trên 6.x**.
- `Saml2AuthenticatedPrincipal#getAttribute(name)` trả nhiều values; `getFirstAttribute` chỉ trả một.
- `new Saml2Authentication(principal, original.getSaml2Response(), verifiedAllowlistedAuthorities)` là một pattern của các bản cũ khi principal type/constructor phù hợp, nhưng cần bảo đảm response verification đã hoàn tất.

Một mảnh **ý tưởng 6.x**, không phải class độc lập:

~~~java
Saml2Authentication validated = defaultConverter.convert(responseToken);
Saml2AuthenticatedPrincipal principal =
        (Saml2AuthenticatedPrincipal) validated.getPrincipal();

List<Object> rawGroups =
        principal.getAttributes().getOrDefault(
                "urn:example:claims:group-id", List.of());

// mapExactAllowlist() phải được app viết và lấy issuer/tenant
// từ trusted relying-party/account context, không từ request.
// Collection<GrantedAuthority> grants = ...

// Ở version hỗ trợ constructor này:
// return new Saml2Authentication(
//         principal, validated.getSaml2Response(), grants);
~~~

Với 7.x, `Saml2AuthenticatedPrincipal` deprecated. Khi migration nên ưu tiên `Saml2ResponseAssertionAccessor` và `Saml2AssertionAuthentication` theo tài liệu chính thức để giữ thông tin cần thiết cho Single Logout.

**Không nhầm `Saml2AuthenticationToken`** (incoming unverified request) với `Saml2Authentication`/`Saml2AssertionAuthentication` (kết quả verified). Mapping group authority ở giai đoạn token chưa verified là sai trust boundary.

## 14. Java 17 standalone: allowlist theo issuer và tenant

Ví dụ này chỉ dùng **Java Standard Library**, không phụ thuộc Spring/OpenSAML. Nó mô phỏng phần logic nhóm → authority **sau khi SAML đã được xác minh**.

Bối cảnh:
- IdP A và IdP B cùng có subject string `shared-001` nhưng là hai external identities khác nhau.
- IdP A có group finance readers + finance approvers + một group “super-admin” chưa được cấp phép.
- IdP B có group value giống IdP A nhưng chỉ được map authority của tenant B.
- User A không được lấy quyền tenant B.
- Unknown group/unknown issuer/missing group/disabled account không cấp quyền.

Tạo file **`SamlGroupAllowlistDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

public final class SamlGroupAllowlistDemo {

    private static final String GROUP_ATTRIBUTE =
            "urn:example:claims:group-id";

    record IdentityKey(String issuer, String subject) {}

    record MappingKey(
            String issuer, String tenantId, String groupId) {}

    record Account(
            String accountId, boolean enabled,
            Set<String> activeTenants) {}

    record VerifiedSaml(
            String issuer,
            String subject,
            Map<String, List<String>> attributes) {}

    private static final String ISSUER_A =
            "https://idp-a.example.org/metadata";
    private static final String ISSUER_B =
            "https://idp-b.example.org/metadata";

    // In a real app, these values are application-managed policy.
    private static final Map<MappingKey, Set<String>> ALLOWLIST =
            Map.of(
                new MappingKey(ISSUER_A, "tenant-a",
                        "grp:finance-readers"),
                Set.of("TENANT_A_REPORT_READ"),

                new MappingKey(ISSUER_A, "tenant-a",
                        "grp:finance-approvers"),
                Set.of("TENANT_A_REPORT_APPROVE"),

                new MappingKey(ISSUER_B, "tenant-b",
                        "grp:finance-readers"),
                Set.of("TENANT_B_REPORT_READ")
            );

    // Demonstration only: account binding by scoped identity.
    private static final Map<IdentityKey, Account> ACCOUNTS =
            Map.of(
                new IdentityKey(ISSUER_A, "shared-001"),
                new Account("acct-a", true, Set.of("tenant-a")),

                new IdentityKey(ISSUER_B, "shared-001"),
                new Account("acct-b", true, Set.of("tenant-b")),

                new IdentityKey(ISSUER_A, "disabled-002"),
                new Account("acct-disabled", false,
                        Set.of("tenant-a"))
            );

    static SortedSet<String> authoritiesFor(
            VerifiedSaml verified,
            String requestedTenant) {

        // The caller must have verified this identity with
        // real SAML cryptography. This demo does not do that.
        Account account = ACCOUNTS.get(
                new IdentityKey(
                        verified.issuer(), verified.subject()));

        TreeSet<String> granted = new TreeSet<>();
        if (account == null || !account.enabled()
                || !account.activeTenants()
                        .contains(requestedTenant)) {
            return granted;
        }

        List<String> externalGroups =
                verified.attributes().getOrDefault(
                        GROUP_ATTRIBUTE, List.of());

        // Exact allowlist: unknown groups grant no authority.
        for (String externalGroup : externalGroups) {
            if (externalGroup == null || externalGroup.length() > 256) {
                continue;
            }
            Set<String> approved = ALLOWLIST.get(
                    new MappingKey(verified.issuer(),
                            requestedTenant, externalGroup));
            if (approved != null) {
                granted.addAll(approved);
            }
        }
        return granted;
    }

    public static void main(String[] args) {
        VerifiedSaml alice = new VerifiedSaml(
                ISSUER_A,
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers",
                        "grp:finance-approvers",
                        "grp:external-superadmin")));

        VerifiedSaml bob = new VerifiedSaml(
                ISSUER_B,
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers")));

        VerifiedSaml unknownGroup = new VerifiedSaml(
                ISSUER_A,
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of("ROLE_SUPER_ADMIN")));

        VerifiedSaml noGroups = new VerifiedSaml(
                ISSUER_A, "shared-001", Map.of());

        VerifiedSaml unknownIssuer = new VerifiedSaml(
                "https://idp-rogue.example.org/metadata",
                "shared-001",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers")));

        VerifiedSaml disabled = new VerifiedSaml(
                ISSUER_A, "disabled-002",
                Map.of(GROUP_ATTRIBUTE, List.of(
                        "grp:finance-readers")));

        System.out.println("A allowed: "
                + authoritiesFor(alice, "tenant-a"));
        System.out.println("B allowed: "
                + authoritiesFor(bob, "tenant-b"));
        System.out.println("A into B: "
                + authoritiesFor(alice, "tenant-b"));
        System.out.println("B into A: "
                + authoritiesFor(bob, "tenant-a"));
        System.out.println("Unknown group: "
                + authoritiesFor(unknownGroup, "tenant-a"));
        System.out.println("Missing groups: "
                + authoritiesFor(noGroups, "tenant-a"));
        System.out.println("Unknown issuer: "
                + authoritiesFor(unknownIssuer, "tenant-a"));
        System.out.println("Disabled account: "
                + authoritiesFor(disabled, "tenant-a"));
    }
}
~~~

Chạy trên Java 17+:

~~~bash
javac SamlGroupAllowlistDemo.java
java SamlGroupAllowlistDemo
~~~

**Stdout chính xác:**

~~~text
A allowed: [TENANT_A_REPORT_APPROVE, TENANT_A_REPORT_READ]
B allowed: [TENANT_B_REPORT_READ]
A into B: []
B into A: []
Unknown group: []
Missing groups: []
Unknown issuer: []
Disabled account: []
~~~

### Tại sao kết quả như vậy?

- A có hai nhóm được approve → hai authorities, sắp xếp lexicographic bởi `TreeSet`.
- `grp:external-superadmin` không nằm trong allowlist → không thành admin.
- B có group ID string giống A nhưng issuer khác → B chỉ nhận `TENANT_B_REPORT_READ`.
- A yêu cầu tenant B/B yêu cầu A → bị chặn vì không có local active membership.
- Chuỗi `ROLE_SUPER_ADMIN` do IdP khai không có allowlist → không cấp quyền.
- Missing attribute → no permission.
- Unknown issuer + subject text giống A → không map account.
- Disabled account → không cấp quyền.

### Những giới hạn của demo

1. `VerifiedSaml` là một **giả định đã verified**; mã này **không parse XML, không verify signature, không làm IdP trust validation**.
2. Map account/group policy hardcode cho học tập; production dùng DB/config quản trị với transaction, cache invalidation và audit.
3. Code chỉ demo tenant-level permissions, chưa có object-level ACL.
4. `Account.activeTenants` là snapshot, không có session/token revocation.
5. Mọi input demo đều là Java objects, không phải raw HTTP requests; đừng expose hàm để client tự gửi `issuer`.
6. Trả mutable `TreeSet` trong ví dụ đơn giản; trong code production có thể dùng `Collections.unmodifiableSortedSet` hoặc `Set.copyOf` để tránh caller đổi kết quả.
7. Dù authority được cấp, endpoint vẫn phải kiểm account hiện hành, resource owner và tenant scope.

## 15. Từ demo chuyển sang `SimpleGrantedAuthority`

Trong Spring Security, chuyển internal strings đã được allowlist sang `GrantedAuthority`:

~~~java
import java.util.Set;
import java.util.Collection;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

Collection<? extends GrantedAuthority> convertApproved(
        Set<String> internalAuthorities) {
    return internalAuthorities.stream()
            .map(SimpleGrantedAuthority::new)
            .toList();
}
~~~

Snippet phải nằm trong một class phù hợp, không có standalone `main`. Điều **quan trọng nhất** không phải `.map(SimpleGrantedAuthority::new)` mà là `internalAuthorities` đã được tạo từ exact allowlist **sau verified SAML trust + local membership**.

### Không bao giờ làm thế này

~~~java
// Anti-pattern: group string từ IdP trở thành ROLE_...
for (String externalGroup : groupsFromSaml) {
    authorities.add(
            new SimpleGrantedAuthority("ROLE_" + externalGroup));
}
~~~

Nếu IdP phát `ADMIN`, `SUPERUSER` hay string bất ngờ, code có thể tạo quyền mới không được phê duyệt. Đặc biệt nguy hiểm nếu app có route `hasRole('ADMIN')`.

### Không dùng `contains("admin")`

~~~java
// Anti-pattern: logic cấp quyền dựa substring
if (group.toLowerCase().contains("admin")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

Các chuỗi `not-an-admin`, `external-admin`, `helpdesk-admin`, `admin-readonly` không có cùng semantics. Quyền phải đến từ **khóa group ID exact và policy approved**, không từ heuristic trên tên.

## 16. Kiểm `hasAuthority` tại endpoint và object ACL tại service

Nếu app có quyền đọc tài liệu theo tenant, một guard thô:

~~~java
@PreAuthorize("hasAuthority('TENANT_A_REPORT_READ')")
public Report getReport(String id) { ... }
~~~

chỉ chứng minh user có một authority; nó chưa chứng minh báo cáo `id` thực sự thuộc tenant A hoặc thuộc scope user có thể đọc.

Thiết kế an toàn hơn:

~~~java
@PreAuthorize("@reportAccess.canRead(authentication, #tenantId, #reportId)")
public Report read(String tenantId, String reportId) {
    return reportRepository
            .findByTenantIdAndId(tenantId, reportId)
            .orElseThrow();
}
~~~

Đây là **snippet trong Spring application**, trong đó:
- `reportAccess` là app bean được implement; method phải kiểm `Authentication`, account ACTIVE, tenant membership, hiện hành authorization policy và object ACL.
- `reportRepository` phải query bằng `tenantId` và `reportId` thay vì find by ID global rồi lọc ở frontend.
- Cần bật `@EnableMethodSecurity`.
- HTTP 403 hoặc 404 tùy privacy contract, nhưng không được trả dữ liệu sai tenant.
- Không cho người dùng sửa path `tenantId` rồi dựa vào authority của tenant cũ.
- Cần kiểm API, GraphQL, batch export, file download, search index và background job, không chỉ controller.

### Khi hệ thống có hàng nghìn tenants

Không nhất thiết tạo `TENANT_X_*` authority cho mọi tenant trong session. Có thể giữ permission dạng `REPORT_READ`, nhưng **mọi lần quyết định trên object** phải lấy trusted current tenant context và check active membership. Tài liệu dùng tenant-qualified strings chỉ để minh họa scoping; production có thể triển khai policy engine/ABAC/relationship-based authorization thay vì tạo vô hạn `GrantedAuthority` strings.

## 17. Account disabled hoặc không có membership

Không nên chỉ kiểm:
- Group `grp:finance-readers` có mặt;
- IdP cryptographically trusted.

Còn phải:
- App-local account mapping active;
- Không bị suspended/deleted/locked/offboarded;
- Tenant active, membership active;
- Đối tượng tài nguyên đúng tenant;
- Permission chưa bị revoke tại local policy version hiện hành;
- Local security status có thể override IdP group claim;
- Một employee thuộc group nhưng bị chặn bởi legal hold/separation of duties;
- Không auto-create privileged local account chỉ vì group admin.

Khi `unknown subject` hoặc `missing group`, policy có thể:
- Cho login với baseline `ROLE_USER` nhưng **không cấp business permissions**;
- Hoặc reject login/onboarding khi app yêu cầu pre-provisioning.

Dù chọn cách nào, **không mặc định fallback quyền đọc mọi thứ**.

## 18. Vai trò nghiệp vụ và segregation of duties

Trong hệ thống tài chính, `REPORT_READ` và `REPORT_APPROVE` có thể phải tách:
- Người phê duyệt không phê duyệt bản ghi do mình tạo.
- `PAYMENT_CREATE` và `PAYMENT_APPROVE` không được cùng account nếu policy cấm.
- `USER_MANAGE` và `AUDIT_DELETE` phải theo approval khác.
- Admin tenant không tự là platform super admin.
- External directory groups chỉ thể hiện membership, không thay workflow-specific approval.

Một group allowlist có thể cấp một **candidate permission**, nhưng ABAC/resource-level checks vẫn quyết định cuối cùng. Ví dụ một tài khoản có `TENANT_A_REPORT_APPROVE` vẫn không được approve chính report do mình tạo.

### System admin là boundary riêng

Khuyến nghị:
- Không có entry `externalGroup=Admins → ROLE_SUPER_ADMIN` trong generic SAML mapping.
- Global admin do internal IAM/PAM/local approval cấp với MFA/step-up.
- Nếu nghiệp vụ bắt buộc delegate global admin qua IdP, dùng issuer/group ID cụ thể, dual control, time-bound grant, approval/audit riêng.
- Không cấp quyền dựa vào chuỗi role do external partner IdP tự đặt.
- Negative tests phải chứng minh unknown `ROLE_ADMIN`/`SuperAdmins` không đổi privileges.

## 19. Khi groups không có, quá nhiều hoặc có giá trị lạ

Các trường hợp không bình thường:
- Attribute `groups` vắng;
- Attribute có list rỗng;
- Attribute chứa `null`, binary/XML object thay vì string;
- List có duplicate group IDs;
- Case mismatch (`grp:Finance-Readers` vs `grp:finance-readers`);
- DisplayName/renamed group thay ID cũ;
- Có 10.000 group values (group overage);
- Attribute Name có cùng FriendlyName nhưng khác NameFormat;
- Signed response chứa nhiều assertions, mapper chỉ đọc subset đã verified;
- SAML AttributeValue có nested XML không được xử lý theo contract.

**Quy tắc:**
- Không thấy approved group → không grant quyền tương ứng.
- Không tự động tạo roles từ unknown values.
- Với input type sai, fail closed và phân loại lỗi theo policy; không `toString()` arbitrary.
- Duplicate values không cộng thêm privileges.
- Có giới hạn kích thước/count và fail/deny phù hợp khi vượt resource policy.
- Với group overage/claims truncation, không coi “không nhận nhóm admin” là lý do gọi API directory bất kỳ rồi tin kết quả; nếu cần bổ sung group lookup, dùng service credentials, IdP contract, response binding, authorization và audit riêng.
- Không tự cấp quyền rộng để “hỗ trợ người dùng khi IdP thiếu group”.

### Group overage không phải wildcard

Một số enterprise IdPs giới hạn số groups đính kèm token/assertion. Hệ thống có thể trả một cơ chế tham chiếu hoặc group overage indicator theo product. Đây không phải một chuẩn chung cho mọi SAML IdP. Khi thiếu groups, **fail closed theo quyền**, log structured indicator và dùng integration được hỗ trợ nếu được phê duyệt.

## 20. IdP A và IdP B có group cùng tên

Ví dụ:
- IdP A (`corp-a`) có group `Finance`.
- IdP B (`partner-b`) cũng có group `Finance`.

Không thể suy hai groups có cùng quyền.

| Issuer | Group | Tenant | Permission |
| --- | --- | --- | --- |
| IdP A | `Finance` | tenant-a | `TENANT_A_REPORT_READ` nếu policy |
| IdP B | `Finance` | tenant-b | `TENANT_B_REPORT_READ` nếu policy |
| IdP B | `Finance` | tenant-a | Không grant |
| Unknown IdP | `Finance` | tenant-a | Authentication failure/no account |
| IdP A | `SuperAdmins` | tenant-a | Không grant nếu không approved |
| IdP A | `Finance` | tenant-a khi account disabled | Không grant |

Lỗi phổ biến: một `Map<String,String>` toàn cục `Finance → ROLE_FINANCE_ADMIN`. Như vậy IdP đối tác có thể cấp quyền nội bộ chỉ bằng group text giống nhau. **Allowlist phải scope issuer/trust + tenant**, còn role usage phải scope object access.

## 21. `NameID` trùng, email trùng và identity binding

Hai IdPs khác nhau có thể phát:
- Cùng NameID `"alex"`;
- Cùng email `"alex@example.org"`;
- Cùng group `"grp:finance-readers"`.

Điều đó không chứng minh cùng account. Khi ánh xạ:
1. Resolve SAML RelyingPartyRegistration đã được verify.
2. Lấy subject identifier theo IdP contract.
3. Tạo external identity key scoped issuer/NameID qualifiers/format.
4. Lookup appAccountId bất biến.
5. Check local account active.
6. Check active tenant membership.
7. Lookup group allowlist với IdP/tenant/attribute/group ID.
8. Cấp authority cụ thể, không tự merge accounts.
9. Khi cần link identities, yêu cầu verified proof + audit.
10. Khi email được tái sử dụng sau offboarding, không khôi phục grants cũ theo email.

**External group mapping không được dùng làm một dạng account linking ngầm.** Group membership và subject identity có nghĩa khác nhau.

## 22. Quyền cập nhật khi group thay đổi

SAML login thường cấp authority vào session tại lúc đăng nhập. IdP có thể thay membership **sau đó**, nhưng app-local session vẫn giữ `Authentication` cũ.

Ví dụ:
- 09:00 login, group `grp:finance-approvers` cấp `REPORT_APPROVE`.
- 09:10 quản trị viên gỡ user khỏi group.
- 09:11 browser vẫn mang session Spring đã được cấp authority trước đó.
- 09:15 user thử phê duyệt một giao dịch.

Nếu app chỉ tin authority snapshot tại 09:00, revoke có thể chậm tới khi session hết hạn hoặc reauthentication. Yêu cầu kỹ thuật:
- Xác định **revocation SLA**.
- Có local account/permission gate hiện hành khi thao tác nhạy cảm.
- Invalidate/expire sessions khi IdP group change được provision bằng SCIM/LDAP/event hoặc admin action.
- Lưu policyVersion/securityEpoch vào session và so với DB.
- Giảm session lifetime/force reauthentication cho quyền cao.
- Khi mapping policy thay đổi, invalidate/refresh affected sessions.
- Nếu SAML Single Logout được dùng, **không mặc định SLO là bảo đảm mọi local session/API token bị revoke** nếu hệ chưa triển khai.
- Với nhiều nodes, revoke state phải shared/consistent.

### Không giữ role cũ trong cache

- Cache key nên có accountId, tenantId, policyVersion hoặc securityEpoch khi phù hợp.
- Không lưu `ROLE_ADMIN` vào global cache chỉ theo email/username.
- Không dùng long-lived `@Cacheable` group mappings mà không có invalidation.
- Retry/event out-of-order không được tự khôi phục old grant.
- Audit quyết định quyền theo source/policy version hiện hành.

## 23. SCIM, LDAP hoặc HR provisioning bổ sung cho SAML

Nhiều tổ chức đồng bộ group memberships qua SCIM hoặc LDAP. Khi đó:
- SAML assertion xác thực user ở login.
- SCIM/LDAP/HR cung cấp dữ liệu entitlement hoặc account state theo chính sách.
- App vẫn cần **provenance**: source nào được phép cấp group/tenant permission.
- SCIM `externalId` được scoped theo provisioning client; không dùng toàn hệ mà thiếu source.
- Group displayName có thể đổi và không luôn là stable ID.
- Group removal/revocation event cần idempotency và ordering.
- Nếu SAML và SCIM bất đồng, chọn **source of truth** theo security policy, không union quyền vô điều kiện.
- Không cho một IdP đối tác tự provision permission system-wide bằng group assignment.
- Khi identity bị disabled, local policy phải deny dù SAML assertion có chữ ký hợp lệ.

### Có nên query LDAP mỗi request?

Tùy latency, availability và SLA. Có các lựa chọn:
1. Chỉ login-time group snapshot + short session lifetime.
2. Session snapshot kết hợp periodic refresh.
3. Local materialized membership từ SCIM/events và current gate tại mỗi hành động quan trọng.
4. Live directory/entitlement lookup có cache bảo vệ và fallback deny cho privileged action.

Không có một cách phổ quát. Chọn theo target revocation latency, availability, regulatory needs và threat model.

## 24. Audit: giải thích vì sao được cấp hoặc bị từ chối

Một audit record có thể nêu:
- `traceId` opaque;
- `registrationId` approved alias;
- `accountId` nội bộ;
- `tenantId`;
- `policyVersion`;
- `matchedMappingCount`;
- `grantedAuthorityNames` nếu classification cho phép;
- `decision`;
- `source` type `verified-saml`/`local-grant`;
- `reasonCode` như `NO_ALLOWLIST_MATCH`, `ACCOUNT_DISABLED`, `TENANT_NOT_MEMBER`.

Ví dụ event đã được tối giản:

~~~json
{
  "event": "saml_authority_mapping",
  "traceId": "opaque-trace-123",
  "registrationAlias": "corp-a",
  "accountRef": "acct-a",
  "tenantRef": "tenant-a",
  "policyVersion": "v12",
  "matchedMappingCount": 2,
  "unknownGroupCount": 1,
  "result": "MAPPED"
}
~~~

**Đây là schema app tự thiết kế**, không phải event mặc định của Spring. Không log raw SAML Response, XML, attributes chứa thông tin nhạy cảm, private keys, session IDs hoặc tokens. Group IDs cũng có thể bộc lộ cơ cấu nhân sự; nếu không cần log trực tiếp thì chỉ log count/categorical reason.

### Các metrics hữu ích

- `saml_group_mapping_success_total{registration,tenant}`
- `saml_group_mapping_unknown_groups_total{registration}`
- `saml_group_mapping_rejected_total{reason}`
- `saml_group_policy_version{cluster}`
- `saml_active_account_denials_total`
- `saml_tenant_permission_denied_total`
- `saml_privileged_grants_total`
- `saml_group_mapping_latency_seconds`

Tránh labels theo raw userName/NameID/email/group IDs có cardinality cao; dùng controlled enumeration alias.

## 25. Kiểm unit mapping bằng cases có collisions

Unit test logic mapper **không cần** thật SAML XML, nhưng test phải nói đúng phạm vi.

Các cases cơ bản:

| ID | Verified input | Expected |
| --- | --- | --- |
| U01 | IdP A, tenant A, group reader | `TENANT_A_REPORT_READ` |
| U02 | IdP A, tenant A, group approver | `TENANT_A_REPORT_APPROVE` |
| U03 | IdP A, nhiều groups reader+approver | Cả hai, không duplicate |
| U04 | IdP A, group unknown | No authority addition |
| U05 | IdP A, group `ROLE_ADMIN` | No admin |
| U06 | IdP A, group `Admin` | No admin |
| U07 | IdP B, group text giống A | Chỉ mapping B |
| U08 | IdP B với tenant A | No authority |
| U09 | User A không còn tenant membership | No authority |
| U10 | User disabled | No authority |
| U11 | Missing groups attribute | No authority |
| U12 | Empty attribute list | No authority |
| U13 | Duplicate group value | Không duplicate quyền |
| U14 | Attribute value kiểu unsupported | Reject/ignore theo policy |
| U15 | NameFormat/FriendlyName khác contract | Không map nhầm |
| U16 | Whitespace/case variant | Không tự match nếu contract exact |
| U17 | Long/oversized group ID | Không xử lý quá giới hạn |
| U18 | Local group policy registry unavailable | Fail closed theo chính sách |
| U19 | Identity unknown/NameID trùng IdP khác | Không lấy account A |
| U20 | Mapping config bị đổi version | Session/permissions refresh đúng |

**U01–U20 kiểm thuật toán mapping**, không chứng minh XML signature/issuer/audience verification. Đừng gọi test chỉ dùng mock attributes là “SAML verifier test”.

## 26. Tích hợp SAML thực: không mock provider khi test trust boundary

Một integration test đúng nên:
1. Có Spring SecurityFilterChain thật và SAML ACS filter.
2. Có trusted test IdP signing certificate riêng cho từng registration.
3. Test IdP tạo **SAMLResponse/Assertion ký hợp lệ**, có group AttributeStatements theo contract.
4. Dùng đúng SP entity ID, ACS Recipient/Destination, AudienceRestriction và time.
5. Giữ InResponseTo/RelayState khi kiểm SP-initiated SSO.
6. Cho response qua `AuthenticationManager`/OpenSAML provider thật.
7. Sau verify, assert exact authorities được cấp theo allowlist.
8. Request protected route kiểm `hasAuthority` và object ACL.
9. Negative signed fixture wrong group/issuer/tenant không cấp quyền.
10. Không chỉ xem HTTP 302 như dấu hiệu login thành công.

### Integration matrix

| ID | Tình huống | Cần assert |
| --- | --- | --- |
| I01 | A signed response, reader group approved | Login OK, only READ |
| I02 | A signed response, reader+approver | Login OK, READ+APPROVE |
| I03 | A signed response, unknown admin group | No ADMIN |
| I04 | A signed response, no groups | Authenticated theo policy, no business permission |
| I05 | B signed response, group ID giống A | Only B mapping |
| I06 | B signed response POST ACS A | Authentication fail (trust/issuer) |
| I07 | Unsigned/modified SAML Response with admin group | Authentication fail |
| I08 | Wrong audience but valid signature | Authentication fail |
| I09 | Wrong recipient/time but valid signature | Authentication fail |
| I10 | Valid SAML A but disabled local account | Reject/no business permission |
| I11 | Valid SAML A but tenant membership removed | Deny tenant resource |
| I12 | Valid SAML A with multi-value attribute | Exact allowlisted union |
| I13 | Two assertions, malicious extra group in unverified assertion | No unverified authority |
| I14 | EncryptedAttribute containing groups | Decrypt/validate then map |
| I15 | IdP group removed, session old | Revoke/deny within SLA |
| I16 | Two tenants same IdP, same group text | No cross-tenant grants |
| I17 | Multiple nodes with policy version drift | Detect/fail safe |
| I18 | Known group with changed displayName | Correct ID-based mapping |
| I19 | Attribute Name/FriendlyName collision | Only approved attribute Name |
| I20 | Global super admin attempted via group name | Deny by policy |

### Negative semantic tests phải giữ chữ ký đúng

Đây là điểm thường bị bỏ sót:
- Nếu thay group XML **sau khi ký**, chữ ký sẽ hỏng.
- Test sẽ fail ở Signature Validator, **không chứng minh** allowlist hoạt động.
- Để kiểm unknown group, hãy tạo fixture chứa unknown group rồi **ký bằng trusted test IdP key**; các fields khác đúng.
- Positive controls phải login thành công cùng IdP và local account.
- Với wrong issuer/recipient/audience, ký fixture phù hợp để cô lập đúng rule.

Không tắt signature verification để cho test group mapping pass. Mapper là thành phần downstream của cryptographic verification.

## 27. MockMvc/@WithMockUser phù hợp kiểm AuthZ, không phù hợp SAML trust

Ví dụ trong Spring Boot project:

~~~java
@Test
@WithMockUser(
        username = "acct-a",
        authorities = "TENANT_A_REPORT_READ")
void userCanReadTenantAReport() throws Exception {
    mvc.perform(get("/tenants/tenant-a/reports/report-1"))
            .andExpect(status().isOk());
}
~~~

Điều kiện: project có endpoint, test data, authorization rules và Spring Security Test. Đây **không phải class standalone**. `@WithMockUser` đặt user/authority giả trong SecurityContext; **nó không đi qua XML Signature, IdP trust hoặc group attribute converter**.

Một test negative hợp lệ:

~~~java
@Test
@WithMockUser(
        username = "acct-a",
        authorities = "TENANT_A_REPORT_READ")
void cannotReadTenantBReport() throws Exception {
    mvc.perform(get("/tenants/tenant-b/reports/report-2"))
            .andExpect(status().isForbidden());
}
~~~

Có thể trả 404 theo resource hiding policy; assertions điều chỉnh theo contract. Nhưng test phải đảm bảo report-2 **thực sự tồn tại trong tenant B**, user A đã authenticated và không có B membership; nếu resource không tồn tại thì 404 không chứng minh tenant ACL.

### Phân tách hai loại bằng chứng

- Unit/MockMvc: “Nếu user có `TENANT_A_REPORT_READ`, backend có chặn tenant B không?”
- Signed SAML provider/integration: “IdP A có group reader đã verified thì mapper chỉ cấp `TENANT_A_REPORT_READ` không?”
- Browser E2E: “Metadata/ACS/cookies/RelayState/IdP hoạt động và actual session chứa đúng authority không?”

Không trộn ba kết luận vào một test dùng fake principal.

## 28. Quyền phê duyệt và object-level access

Giả sử `TENANT_A_REPORT_APPROVE` có trong authorities. Vẫn cần:
- Kiểm report thuộc tenant A.
- Kiểm report đang ở trạng thái chờ duyệt.
- Người duyệt không chính là người tạo nếu separation-of-duties yêu cầu.
- Kiểm hạn mức/ownership/workflow stage.
- Check account active và role hiện hành nếu revocation SLA ngắn.
- Không duyệt report đã bị hủy chỉ vì role còn hiệu lực trong session.
- Audit action, tenant, object ID, source policy và thời gian.
- Không dùng client request param `approved=true` để bỏ policy.

**Authorities là input cho authorization, không phải kết luận cuối cùng trên mọi tài nguyên.**

## 29. Kiểm thử đồng thời và cạnh tranh cấu hình

Các tình huống ít thấy nhưng có tác động:
1. Hai logins cùng subject xảy ra trong lúc group policy được cập nhật.
2. Một node dùng policy version v12, node khác v13.
3. SCIM remove event và login callback xảy ra cùng lúc.
4. Account bị disable sau khi assertion đã verify nhưng trước khi session commit.
5. A ở một tab, B ở tab khác trong cùng browser session, principal/tenant context bị thay.
6. Group mapping được rollback sau incident nhưng old sessions còn role v13.
7. Group IDs được tái sử dụng sau directory recreation.
8. Redis cache cũ được phục hồi sau outage.
9. Local membership revoked nhưng scheduled export job vẫn chạy.
10. Group attribute list quá dài làm mapper tốn tài nguyên.

### Biện pháp

- Policy version immutable per decision hoặc atomic config reload.
- Rollout/health kiểm all nodes cùng policy version.
- Account security epoch + permission cache invalidation.
- Revalidate sensitive actions ở business boundary.
- Stable group ID và directory namespace.
- Deny unknown state/config conflict theo threat model.
- Audit mapping decisions phục vụ root cause.
- Resource query luôn dùng trusted tenant context.
- Test concurrency và eventually consistent revocation với SLA rõ.
- Không trộn anonymous/default permissions với elevated mapped authorities.

## 30. Chọn nơi thực thi mapping: converter hay downstream policy?

| Vị trí | Ưu điểm | Rủi ro/cần kiểm |
| --- | --- | --- |
| SAML ResponseAuthenticationConverter | Authorities có ngay sau login | Phải giữ provider defaults, SLO accessor và account checks |
| AuthenticationSuccessHandler | Có session/HTTP context | Nếu thay SecurityContext sai dễ mất persisted auth |
| Local account/user-details service | Kết hợp SCIM/DB/grants hiện hành | Cần map issuer+subject chính xác; latency/cache |
| Custom authorization service tại request | Quyền cập nhật nhanh, object ACL mạnh | Cần tối ưu performance và availability |
| Policy engine bên ngoài | Tách policy & audit | Fail-closed, latency, trust boundary, tenant scope |
| JWT minting nội bộ sau SAML | Thuận tiện giữa microservices | Authority stale đến expiry/revocation; token audience |
| Gateway mapping | Có thể centralize | Không được bỏ resource-level checks; trusted identity propagation |

**Không đặt toàn bộ bảo vệ ở frontend/UI**. Kể cả mapper đưa đúng authority, API/resource service phải tự xác minh permission và tenant/object ownership. Một gateway được trusted vẫn không thay object-level ACL trong backend.

### Nếu mint local JWT sau SAML

- Chỉ mint JWT sau verified SAML login + allowlist mapping + active account.
- Claims `sub` nên là stable app account ID, không email/NameID unscoped.
- `iss` là app issuer và `aud` đúng microservice.
- `scope/roles/tenant` do app policy phát, không copy raw SAML groups vào quyền.
- JWT có TTL/refresh/revoke policy theo privileged action SLA.
- Backend Resource Server verify signature, issuer, audience, expiry, account/tenant state.
- Nếu user rời group, những JWT cũ có thể tồn tại tới hạn nếu không có revocation gate.

## 31. Bảo vệ mapping policy trước thao tác của IdP đối tác

Trong multi-IdP B2B:
- Một IdP đối tác có thể tự cấp người dùng vào group bất kỳ trong **directory của họ**.
- Đó là quyền quản trị bên họ, không đồng nghĩa quyền cấp admin tenant A của bạn.
- Mapping phải xác định **IdP/tenant nào được delegate quyền gì**.
- Với tenant-local self-service, tenant admin có thể sửa mapping của tenant mình nhưng không sửa global/system roles.
- Mọi change tới privileged mapping phải được local security review/approval.
- Không cho auto-discovered group “Admins” trở thành app admin theo heuristic.
- Có quotas, rate limits và audit khi IdP liên tục gửi group values chưa biết.
- Nếu external group mất khỏi metadata hoặc directory, không auto-retain quyền cũ vô thời hạn.
- Explicit deny rule hoặc absence of allowlist nên áp dụng trước granting defaults.

**Trường hợp IdP bị chiếm quyền điều hành:** một signed SAML Response có thể mang group do attacker control **và vẫn có chữ ký hợp lệ**. Chữ ký xác nhận IdP đã phát attribute; **allowlist** giới hạn phạm vi quyền mà IdP được ủy quyền cấp. Tuy nhiên nếu một group được allowlist có quyền cao thì IdP compromise vẫn có thể cấp group ấy; cần PAM/approval/dual control cho những quyền quan trọng.

## 32. Checklist QA trước release

- [ ] `RelyingPartyRegistration` trỏ tới đúng IdP issuer, ACS, SP entity ID và trusted verification credentials.
- [ ] SAML signature, issuer, audience, recipient, conditions, InResponseTo validation còn nguyên.
- [ ] EncryptedAttributes (nếu dùng) được decrypt/verify trước khi map.
- [ ] Attribute Name, NameFormat, kiểu value và data contract được IdP xác nhận.
- [ ] Dùng **List values**, không chỉ `getFirstAttribute()` với group đa trị.
- [ ] Group identifiers stable, không dựa displayName/email khi có ID đáng tin.
- [ ] Allowlist khóa theo IdP registration/issuer, tenant, attribute và external group ID.
- [ ] Không tự tạo authority theo tên nhóm hoặc prefix từ IdP.
- [ ] `ROLE_ADMIN`/`SUPER_ADMIN` không do unknown group tự cấp.
- [ ] Quy tắc `hasAuthority`/`hasRole` và `ROLE_` prefix nhất quán.
- [ ] `ROLE_USER` mặc định không mở endpoint nhạy cảm.
- [ ] Unknown/empty/malformed group không cấp permission ngoài allowlist.
- [ ] Duplicate group values không duplicate authorities.
- [ ] Group overage/unsupported value type có fail-closed policy.
- [ ] External identity link theo issuer/subject/qualifiers, không email đơn lẻ.
- [ ] Local app account ACTIVE và tenant membership được kiểm trước grant.
- [ ] Object-level resource ACL được kiểm tại service/repository.
- [ ] Mapping policy có owner, change review, version, audit và rollback.
- [ ] Permission cache/session invalidation đáp ứng revocation SLA.
- [ ] Custom converter giữ `Saml2AssertionAuthentication` accessor/SLO behavior theo Spring 7 nếu áp dụng.
- [ ] Migration 6.x→7.x đã cập nhật deprecations và APIs.
- [ ] Unit tests có same group ID hai IdPs, unknown admin group, missing attributes, disabled account.
- [ ] Provider/integration tests dùng **signed** fixtures; invalid groups phải vẫn có valid signature.
- [ ] MockMvc @WithMockUser tests không được báo thành SAML verifier tests.
- [ ] Tài nguyên tenant B tồn tại và B session hợp lệ trong negative cross-tenant tests.
- [ ] Multi-node policy version và group removal/session staleness được kiểm.
- [ ] Logging/metrics không chứa raw SAML Response, credentials hoặc PII.
- [ ] System admin grants có governance riêng, không tự map qua group name.
- [ ] Tests bao gồm allow/no allow, content parity, groups đa trị và request-time AuthZ.
- [ ] Browser SSO E2E có IdP thực/staging, đúng metadata/ACS/cookies.
- [ ] Có runbook khi IdP rename groups, đổi Attribute Name hoặc signing certificate.

## 33. Câu hỏi ôn tập và đáp án

**Câu 1.** Nhóm SAML `"ROLE_ADMIN"` có nên trở thành `ROLE_ADMIN` tự động không?

**Đáp án:** không. Phải có allowlist exact do ứng dụng quản lý và đánh giá scope/privileged grants.

**Câu 2.** Chữ ký SAML đúng có chứng minh group `"Admins"` được phép làm global admin không?

**Đáp án:** không. Chữ ký xác nhận IdP phát group, nhưng ứng dụng quyết định quyền ủy quyền.

**Câu 3.** Vì sao không lấy `getFirstAttribute("groups")` khi nhóm có nhiều giá trị?

**Đáp án:** chỉ lấy một group, bỏ những giá trị khác; cần đọc `getAttribute()`/attributes list và map toàn bộ theo contract.

**Câu 4.** Group name `"Finance"` của hai IdPs có đồng nghĩa không?

**Đáp án:** không. Phải scope issuer/registration/tenant và group ID.

**Câu 5.** `hasAuthority("TENANT_A_REPORT_READ")` và `hasRole("TENANT_A_REPORT_READ")` giống nhau không?

**Đáp án:** không mặc định. `hasRole` thường thêm `ROLE_`, còn `hasAuthority` so exact.

**Câu 6.** Missing `groups` attribute có nên cấp `ROLE_REPORT_VIEWER` cho tiện không?

**Đáp án:** không, nếu policy không có rule cấp độc lập. Missing groups → không grant permission tương ứng.

**Câu 7.** Một đối tác tự phát `"SuperAdmins"` có được vào system admin API không?

**Đáp án:** không; allowlist và local security governance phải bảo vệ global/system roles.

**Câu 8.** SAML group DN có dấu phẩy, có nên split comma không?

**Đáp án:** không. DN là một value; multiple AttributeValues được xử lý theo list.

**Câu 9.** Unknown group cần làm login fail hay chỉ bỏ qua?

**Đáp án:** tùy chính sách. Nhưng phải fail closed **ở quyền**, không tự grant. Nếu group attribute là điều kiện bắt buộc để onboarding, có thể reject authentication.

**Câu 10.** Một user không còn thuộc tenant A nhưng vẫn có group reader A, có đọc A report không?

**Đáp án:** không. Local active membership và object ACL cần được kiểm.

**Câu 11.** `Saml2AuthenticatedPrincipal` có được dùng trong Spring Security 7.x không?

**Đáp án:** có thể còn để tương thích nhưng đã deprecated; 7.x khuyến nghị `Saml2ResponseAssertionAccessor`/`Saml2AssertionAuthentication`.

**Câu 12.** Vì sao không tạo `Saml2Authentication` mới tùy ý trên Spring 7.x?

**Đáp án:** có thể làm mất assertion accessor/registration information phục vụ SLO hoặc framework behavior; ưu tiên giữ kiểu được default converter tạo, ví dụ `toBuilder`.

**Câu 13.** Response converter được gọi trước hay sau OpenSAML verification?

**Đáp án:** trong flow provider mặc định, response authentication conversion diễn ra sau các bước response/assertion verification/validation; không thay bằng custom bypass.

**Câu 14.** Một SAML Response sửa group sau signing rồi bị từ chối chứng minh allowlist không?

**Đáp án:** không chắc. Có thể chỉ signature fail; test unknown group phải có valid signature.

**Câu 15.** Có thể dùng email làm account key chính cho mapping không?

**Đáp án:** không nên. Email mutable và có thể trùng/reuse; dùng external identity scoped issuer và stable appAccountId.

**Câu 16.** `ROLE_USER` default có đủ đọc tất cả reports không?

**Đáp án:** không. Route business phải check explicit permission và tenant/resource.

**Câu 17.** Group `"admin"` và `"Admin"` có nên được coi giống nhau không?

**Đáp án:** chỉ nếu normalization contract được xác định rõ và policy được phê duyệt; không tự lowercase vì có thể gây collision.

**Câu 18.** Hai values trùng nhau có tạo hai permissions giống nhau không?

**Đáp án:** không; dùng `Set` deduplicate, không grant vượt allowlist.

**Câu 19.** Admin tenant A có được xem tenant B vì cùng group ID không?

**Đáp án:** không. Tenant membership, group mapping và object ACL scoped riêng.

**Câu 20.** Ngay sau khi admin gỡ group từ IdP, session SAML cũ chắc chắn mất quyền chưa?

**Đáp án:** không. Cần revocation strategy, session expiry/re-authentication, policy refresh hoặc local account gate đáp ứng SLA.

**Câu 21.** `@WithMockUser` có chứng minh signed SAML group attribute được verify không?

**Đáp án:** không. Nó nạp SecurityContext giả; cần provider integration với signed fixtures.

**Câu 22.** `ROLE_REPORT_VIEWER` có thể được cấp từ SAML chưa verify không?

**Đáp án:** không. Không đọc raw client-supplied XML rồi tự cấp quyền.

**Câu 23.** Vì sao nên có audit `policyVersion`?

**Đáp án:** giúp giải thích authority grant tại thời điểm login và điều tra khi mapping thay đổi hoặc node drift.

**Câu 24.** Nếu IdP bị chiếm quyền, allowlist có hoàn toàn vô hiệu hóa mọi tấn công không?

**Đáp án:** không. Nó giới hạn quyền được delegate cho IdP nhưng các nhóm approved vẫn có thể bị lạm dụng; dùng governance/MFA/PAM cho quyền cao.

**Câu 25.** Tại sao route có `hasAuthority` vẫn cần resource ACL?

**Đáp án:** authority chỉ là permission khái quát; quyền trên một object phụ thuộc tenant, owner, workflow và policy hiện hành.

**Câu 26.** Vì sao không chỉ viết một Map `<String,String>` toàn cục?

**Đáp án:** nó không phân biệt IdP issuer/registration, tenant hoặc attribute contract, làm trùng group text gây cấp quyền chéo.

**Câu 27.** Khi IdP đổi `FriendlyName`, mapping có nên tự động đổi tên attribute key không?

**Đáp án:** không; dùng `Attribute Name` đã thống nhất, kiểm NameFormat và thay đổi có migration/versioning.

**Câu 28.** Khi app tạm không truy cập policy database, có được grant mọi quyền đã thấy trong assertion không?

**Đáp án:** không. Fail closed theo policy và retry/incident runbook, không bypass allowlist.

**Câu 29.** Có cần kiểm signing cert/metadata của IdP khi bài toán chỉ nói về groups không?

**Đáp án:** có, vì groups chỉ có ý nghĩa tin cậy sau SAML validation đúng asserting party.

**Câu 30.** Kết quả demo `Unknown group: []` chứng minh Spring SAML2 an toàn chưa?

**Đáp án:** chưa. Nó chỉ chứng minh thuật toán thuần Java với giả định input verified, không thay signed integration tests.

## 34. Runbook khi user đăng nhập được nhưng không có quyền

**Bước 1 — Xác định AuthN vs AuthZ.** SAML login có thành công và tạo Authentication không? Nếu chữ ký/issuer/audience/time fail thì không phải lỗi group mapping.

**Bước 2 — Kiểm correct registration.** Người dùng đến từ đúng IdP/tenant chưa? Metadata và certificate có tương ứng không?

**Bước 3 — Kiểm attribute contract.** Đúng `Attribute Name`, `NameFormat`, kiểu list values? Có encrypted attributes hoặc group overage không? Chỉ kiểm trên dữ liệu redacted.

**Bước 4 — Kiểm identity binding.** NameID/issuer được map tới đúng appAccountId? Account ACTIVE? Tenant membership active?

**Bước 5 — Kiểm allowlist.** Exact group IDs có trong mapping hiện hành? Policy version nào, approval nào? Có rename/recreate group không?

**Bước 6 — Kiểm security context.** Authorities thực tế sau login có thuộc allowed set không? `hasRole`/`hasAuthority` có dùng đúng prefix?

**Bước 7 — Kiểm resource ACL.** User có access đúng tenant/report/action không? Object có tồn tại và phù hợp policy không?

**Bước 8 — Kiểm cache/session.** Người dùng vừa được thêm/gỡ group? Session có snapshot cũ? Cache policy có invalidation đúng không?

**Bước 9 — Kiểm consistency.** Các pods/regions có cùng policy version và IdP trust config không?

**Bước 10 — Sửa nguyên nhân.** Sửa policy/IdP attribute contract qua change control; không tạm grant `ROLE_ADMIN` hoặc bật wildcard mapping chỉ để user vào được.

**Bước 11 — Regression.** Chạy positive, unknown-group negative, privileged-group negative, cross-IdP/cross-tenant signed fixtures và object ACL tests.

**Bước 12 — Theo dõi.** Kiểm auth success, mapping unknown-group count, denials và privilege changes mà không lộ PII/raw SAML.

## 35. Tổng kết

**Ánh xạ nhóm SAML thành quyền nội bộ an toàn là một bài toán ủy quyền có giới hạn tin cậy**:

1. **Chỉ dùng attributes của SAML Response đã được provider xác minh.** SAML Signature chứng minh nguồn và tính toàn vẹn trong phạm vi trust cấu hình; không tự cấp quyền.
2. **Dùng allowlist exact, có namespace IdP/registration, tenant và attribute contract.** Không map chuỗi nhóm theo prefix, wildcard, contains hoặc tên hiển thị tùy ý.
3. **Cấp đúng `GrantedAuthority` đã được phê duyệt.** `hasAuthority` so exact, `hasRole` dùng convention `ROLE_`.
4. **Kiểm local account ACTIVE, tenant membership và resource ACL.** Một group được phép không tự cấp quyền toàn tenant hay system admin.
5. **Xử lý tất cả group values, unknown/duplicate/missing và typed attributes.** Unknown group không được phát sinh authority.
6. **Giữ Spring Security provider verification và cấu trúc SAML accessor/SLO khi custom converter.** Đối chiếu APIs Spring 6.x/7.x.
7. **Test cả AuthN và AuthZ bằng signed fixtures và local ACL cases.** Mock principal hữu ích nhưng không phải bằng chứng SAML signature.
8. **Có governance, audit, revoke và cache/session refresh.** Group đã bị gỡ không nên tồn tại quyền vô thời hạn trong session.

Một bài thực hành đạt yêu cầu phải chứng minh rằng IdP A cấp được **chỉ** những quyền được delegate, IdP B có cùng group string không thể chiếm quyền A, và tài khoản không có membership/đã disabled không thể vượt ACL dù sở hữu signed SAML assertion hợp lệ.

### Tài liệu chính thức và bảo mật tham khảo

1. Spring Security — Authenticating SAML Responses; `OpenSaml5AuthenticationProvider`, response authentication converter, principal, authorities: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
2. Spring Security — SAML2 Login Overview, verification flow và default authorities: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
3. Spring Security — SAML2 Migration 7, `Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor`: https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
4. Spring Security — `Saml2AuthenticatedPrincipal` API, multi-value attributes/deprecation: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
5. Spring Security — `Saml2AssertionAuthentication` API và builder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AssertionAuthentication.html
6. Spring Security — `Saml2ResponseAssertionAccessor` API, `getAttributes()`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/saml2/provider/service/authentication/Saml2ResponseAssertionAccessor.html
7. Spring Security — Method Security và `@PreAuthorize`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
8. Spring Security — Authorization architecture, GrantedAuthority/roles: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
9. OASIS — SAML 2.0 Core, AttributeStatement/Attributes/NameID: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
10. OASIS — SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
11. OWASP — Authorization Cheat Sheet, least privilege/deny-by-default/check every request: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
12. OWASP — Insecure Direct Object Reference Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
13. OWASP — Multi-Tenant Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html