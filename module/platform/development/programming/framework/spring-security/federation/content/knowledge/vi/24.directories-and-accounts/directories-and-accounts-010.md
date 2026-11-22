# Tối thiểu hóa thuộc tính chia sẻ và giới hạn lưu dữ liệu cá nhân trong thư mục, tài khoản và liên kết danh tính

> **Module:** Spring Security – federation. **Nhóm:** Thư mục và tài khoản. Tài liệu này hướng dẫn thiết kế một hệ thống đăng nhập liên kết (federation) chỉ **thu thập, truyền, sử dụng và lưu những thuộc tính danh tính thực sự cần thiết**. Áp dụng cho LDAP/Active Directory, SAML 2.0, OpenID Connect (OIDC), provisioning bằng SCIM và các ứng dụng Spring Security. Tập trung vào hợp đồng chia sẻ thuộc tính giữa IdP và Relying Party, lựa chọn định danh ít tiết lộ, authorization tối thiểu, vòng đời bản ghi cá nhân, log/cache/backup, kiểm thử và xử lý khi nguồn dữ liệu không còn phù hợp. Các tên miền, người dùng và mốc thời hạn đều giả lập; ví dụ code Java 17 thuần ở cuối bài chạy độc lập.

## 1. Vấn đề: đăng nhập cần nhận diện, không cần sao chép hồ sơ nhân sự

Một tổ chức có thư mục nhân sự trung tâm. IdP đồng bộ từ thư mục và cung cấp đăng nhập SSO cho nhiều ứng dụng:

- **Portal nội bộ:** chỉ cần biết một định danh ổn định để tạo phiên, trạng thái tài khoản và tên hiển thị.
- **Ứng dụng báo cáo:** chỉ cần biết danh tính và quyền truy cập một tập báo cáo; không cần email, số điện thoại hay địa chỉ.
- **Ứng dụng hỗ trợ:** có chức năng gửi thông báo email cho nhân viên khi họ chủ động mở yêu cầu, nên chỉ ở nghiệp vụ này cần email được phê duyệt.
- **Ứng dụng đối tác bên ngoài:** chỉ cần biết người dùng có đủ điều kiện thực hiện nghiệp vụ hay không; không cần nhận cả ngày sinh, employeeId và sơ đồ tổ chức.

Directory có thể có hàng chục thuộc tính như `cn`, `displayName`, `mail`, `telephoneNumber`, `homeAddress`, `dateOfBirth`, `manager`, `department`, `memberOf`, employee ID, cost center, salary band, dữ liệu xác minh giấy tờ. **Có sẵn trong directory không đồng nghĩa mọi Relying Party được nhận.**

Một cấu hình “lấy toàn bộ user object rồi serialise vào JWT, SAML assertion hoặc session” làm tăng khả năng rò rỉ, correlation giữa các hệ thống và gánh nặng giữ/xóa dữ liệu. Không có nguyên tắc nào nói “dữ liệu đã nằm trong mạng nội bộ thì có thể chia sẻ cho mọi service”.

### 1.1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt **identity attribute**, **authentication context**, **entitlement** và **domain profile**.
2. Áp dụng **purpose limitation, data minimization, storage limitation** ở nguồn dữ liệu, federation protocol, ứng dụng và kho lưu.
3. Lập **attribute release contract** theo từng RP/client, tenant, mục đích và thời hạn.
4. Biết OIDC `openid`, `profile`, `email` scopes và `claims` parameter có tác động gì; tránh xin dữ liệu quá rộng.
5. Chọn `(iss, sub)`, subject identifier dạng pairwise hoặc một opaque stable ID thay cho email làm khóa tài khoản.
6. Dùng SAML 2.0 `NameID` và `AttributeStatement` theo allowlist, tránh gửi nhóm/quyền/directory đầy đủ.
7. Hạn chế dữ liệu LDAP bằng `SearchControls.setReturningAttributes` và SCIM bằng `attributes`/schema `returned` policy.
8. Phân biệt dữ liệu chỉ cần **trong phiên**, dữ liệu cần **giữ để vận hành**, dữ liệu phục vụ **hồ sơ nghiệp vụ** theo căn cứ độc lập.
9. Xử lý provisioning, de-provisioning, subject deletion/correction, retention, backups, logs, analytics và incident response.
10. Chạy Java 17 demo về pairwise pseudonymous ID, allowlist per RP, từ chối attribute vượt mục đích, TTL và unlink.

## 2. Vị trí của dữ liệu cá nhân trong federation

```text
Authoritative HR / Identity directory
  employeeId, preferredName, email, phone, address, groups, roles, status
             |
             | HR-to-IdP synchronization
             v
IdP / Identity Broker
  account + authentication + policy per RP
             |
             +-- OIDC ID Token/UserInfo (allowlisted claims)
             +-- SAML Assertion (allowlisted NameID/attributes)
             +-- SCIM provisioning (approved account attributes)
             v
Relying Party A: Portal       Relying Party B: Reports
  minimal account link          minimal account link
  local roles/session            local roles/session
             |
             v
Logs / metrics / caches / database / backups
             |
             v
Retention, de-provisioning, correction and deletion workflow
```

Mỗi mũi tên là **một quyết định chia sẻ dữ liệu riêng**. Khi IdP phát đầy đủ employee profile qua signed SAML Assertion hoặc ID Token, điều đó vẫn là **truyền dữ liệu** ngay cả khi RP chỉ dùng một thuộc tính. Việc lọc DTO sau khi nhận **không xóa được lần tiết lộ đã xảy ra**.

### 2.1. Vai trò: directory, IdP, RP và người dùng

| Thành phần | Quyền/trách nhiệm chính | Rủi ro cần ngăn |
| --- | --- | --- |
| **Authoritative source** (HR/LDAP/AD) | Quản lý sự thật nguồn, chất lượng và phân loại thuộc tính | Thư mục chứa quá nhiều dữ liệu, permission đọc quá rộng |
| **IdP / federation broker** | Xác thực user, phát subject/claims/attributes theo RP | Attribute release mặc định “all”, pairwise mapping không cô lập |
| **RP — Relying Party** | Nhận minimal identity, tạo tài khoản/phiên và phân quyền | Lưu full assertion/profile vô thời hạn, dùng email làm identity key |
| **SCIM provisioning service** | Đồng bộ lifecycle/authorized population | Provision mọi employee tới mọi app, không deprovision |
| **Application domain storage** | Lưu nghiệp vụ với mục đích/thời hạn được duyệt | Dùng login attributes cho mục đích thứ hai ngoài kỳ vọng |
| **Security/privacy owners** | Duyệt policy, threat/privacy assessment và exception | Không có owner, không đo được retention/erasure |

Bài nói về **kỹ thuật thiết kế quyền truy cập và quản lý dữ liệu**, không thay đánh giá pháp lý theo nơi triển khai. Consent không phải lúc nào cũng là căn cứ thích hợp; phải xác định căn cứ xử lý, mục đích, quyền/chế độ thông báo và giới hạn thời gian theo quy định áp dụng.

## 3. Ba nguyên tắc riêng: mục đích, tối thiểu, thời gian

### 3.1. Purpose limitation — mục đích xác định

Trước khi IdP/RP lấy một thuộc tính, đặt câu hỏi:

- Chức năng hoặc quyết định nào **không thể hoạt động** nếu thiếu thuộc tính?
- Thuộc tính này được xử lý bởi bên nào, trong thời gian nào và theo thông báo/trust agreement nào?
- Có một phương án **derived value** ít tiết lộ hơn không?
- Sẽ làm gì khi chức năng ngừng cần, user đổi vai trò, app bị ngừng hoặc hợp đồng kết thúc?
- Có sử dụng lại cho analytics, marketing hoặc cross-app tracking không? Nếu có phải có **mục đích/cơ sở và policy riêng**, không suy từ việc user từng đăng nhập.

**Ví dụ:** hệ thống chỉ cần biết một người đủ 18 tuổi hay không. Nếu IdP đã xác minh tuổi và policy cho phép, hãy chuyển **`over18=true/false`** thay vì ngày sinh đầy đủ. Đây là attribute tối thiểu hơn, không phải bằng chứng tuổi hợp lệ trong mọi pháp luật/ngữ cảnh; cần assurance đáp ứng yêu cầu.

### 3.2. Data minimization — chỉ dữ liệu cần thiết

Cùng một người nhưng các RP có nhu cầu khác nhau:

| Use case | Thuộc tính tối thiểu thường đủ | Thường không cần |
| --- | --- | --- |
| Đăng nhập nội bộ | `iss`, `sub`; local account ID, trạng thái được phép | Địa chỉ, ngày sinh, điện thoại, employee number toàn cục |
| Hiển thị lời chào | Preferred/display name nếu thật sự dùng | Legal name, middle name, giới tính, ngày sinh |
| Xác thực ủy quyền báo cáo | RP-specific permission/role, hoặc policy decision | Toàn bộ `memberOf`, manager chain, HR record |
| Gửi biên nhận yêu cầu | Email đã xác minh nếu mục đích yêu cầu và được duyệt | Số điện thoại, địa chỉ nhà, email cá nhân khác |
| Kiểm tra đủ điều kiện | Boolean/claim đủ điều kiện có issuer và assurance | Ngày sinh/giấy tờ/dữ liệu đánh giá gốc |
| Bảng điều khiển số liệu tổng hợp | Số liệu đã tổng hợp phù hợp mức ẩn danh | Danh sách từng cá nhân không cần thiết |

**Không phải mọi bảng đều có cùng luật:** “phải có email” có thể đúng cho một ứng dụng liên lạc nhưng không đúng cho một RP chỉ xác thực đăng nhập. Một thuộc tính “tiện dùng để debug” thường không đủ để được gửi mặc định.

### 3.3. Storage limitation — không giữ quá thời gian cần thiết

Trả lời cả **lưu ở đâu** và **khi nào xóa**:

1. Dữ liệu chỉ dùng để quyết định login hoặc role lúc xác thực: có thể giữ **trong request/session ngắn hạn** hoặc không lưu ở DB.
2. Opaque account link `(issuer, subject)`: có thể cần tồn tại trong thời gian RP account hoạt động; xóa/unlink khi deprovision theo policy.
3. Email dùng gửi biên nhận: nếu app cần lịch sử liên lạc được duyệt có thể có thời hạn riêng; nếu chỉ gửi một lần, **đọc on demand rồi không lưu bản sao lâu dài**.
4. Audit bảo mật: giữ **event code/timestamp/service/opaque correlation ID** thay full claims, có retention độc lập.
5. Transaction/financial records: nếu phải lưu theo nghĩa vụ hợp pháp, tách khỏi federated login profile và có access/retention control riêng.
6. Backup/replica: cần deletion propagation, giới hạn retention và quy tắc restore không hồi sinh hồ sơ đã xóa.

**Không chọn một mốc TTL chung** cho session, account link, legal documents, audit log và analytics. Phải có **retention schedule theo loại dữ liệu và mục đích**, được privacy/security/legal owners phê duyệt.

## 4. Phân loại thuộc tính trước khi cấp cho RP

Một **data inventory** nên có: tên trường từ nguồn, ý nghĩa, sensitivity, authoritative owner, mục đích sử dụng, bên nhận, điều kiện phát hành, cách cập nhật, retention và hành động deprovision.

| Thuộc tính nguồn | Ví dụ | Rủi ro | Quyết định release |
| --- | --- | --- | --- |
| `directoryObjectId` | internal ID | Có thể link cross-RP | Không gửi toàn cục; thay pairwise/opaque RP ID |
| `uid` / `employeeNumber` | user/HR number | Dễ link, tái nhận diện | Tránh nếu chỉ cần subject |
| `mail` | corporate email | Định danh trực tiếp, có thể thay đổi | Chỉ khi cần liên lạc, không dùng làm primary login key |
| `displayName` | tên hiển thị | Dữ liệu cá nhân | Chỉ cho UI cần hiển thị |
| `givenName`, `sn` | họ/tên | Có thể không cần cả hai | Chọn display name nếu đủ |
| `telephoneNumber` | số điện thoại | Nhạy cảm theo use case | Không mặc định phát vào mọi token |
| `homePostalAddress` | địa chỉ | Nhạy cảm, rủi ro lớn | Không release khi login thông thường |
| `birthDate` | ngày sinh | Có thể nhạy cảm | Chuyển derived eligibility nếu phù hợp |
| `memberOf` / groups | hàng trăm group DNs | Lộ sơ đồ tổ chức, excessive privilege | Chuyển role/entitlement tối thiểu cho riêng RP |
| `manager` / department | cơ cấu tổ chức | Dễ suy nội bộ/cross-link | Chỉ phát nếu chức năng đòi hỏi |
| `accountEnabled` / `active` | true/false | Trạng thái quan trọng | Dùng cho login authorization khi cần |
| `salary` / health / IDs | tài chính/sức khỏe/ID | Rủi ro cao | Không chia sẻ trừ mục đích và kiểm soát riêng |
| Password hashes/private keys | secret | Cực kỳ nhạy cảm | **Tuyệt đối không đưa vào federation assertions/claims** |

**Multi-valued attributes** như `memberOf`, `emails` và `roles` là nơi dễ vô tình tiết lộ nhiều hơn dự kiến. Nếu một group list chứa 200 tên dự án và phòng ban, hãy tính một quyền cụ thể như `canViewReport=true` hoặc RP-specific role thay vì gửi toàn bộ danh sách.

### 4.1. Nhãn phân loại chỉ là điểm đầu

Không thể chỉ dựa vào “email = low sensitivity”, “department = non-sensitive”. Rủi ro thay đổi theo đối tượng nhận, tập dữ liệu kết hợp, nơi xử lý và luật áp dụng. Một opaque subject vẫn là dữ liệu có thể liên quan cá nhân nếu hệ thống giữ bảng ánh xạ ngược. **Pseudonymization không tự thành anonymization.**

### 4.2. Attribute derivation tốt hơn truyền dữ liệu gốc

```text
Directory:
  birthDate = 1995-xx-xx
        |
        v
IdP/verified attribute processor
  policy: isEligibleForService = true
        |
        v
RP:
  sees only eligible=true, issuer, subject, assurance context
  cannot recover birthDate from the assertion
```

Yêu cầu ứng dụng phải tự chọn mức assurance phù hợp (kiểm tra nguồn của kết quả, expiry và user consent/legal basis), không chấp nhận một boolean do browser tự gửi.

## 5. Hợp đồng chia sẻ thuộc tính theo từng RP

Một **attribute release policy** không nên chỉ là cấu hình “OIDC/SAML enabled”. Nó phải xác định chính xác RP, tenant, protocol, audience, mục đích, claims và retention.

Ví dụ contract mang tính thiết kế, **không phải YAML mặc định của Spring Security**:

```yaml
identity_attribute_release:
  portal:
    issuer: "https://idp.example.org"
    audience: "portal-client"
    purpose: "authentication_and_greeting"
    identifier: "pairwise_subject"
    allowed_claims:
      - "sub"
      - "active"
      - "display_name"
    denied_claims:
      - "birth_date"
      - "home_address"
      - "salary"
      - "phone"
    retention:
      session_claims: "until_session_end"
      account_link: "until_unlink_with_approved_retention"

  reports:
    issuer: "https://idp.example.org"
    audience: "reports-client"
    purpose: "report_authorization"
    identifier: "different_pairwise_subject"
    allowed_claims:
      - "sub"
      - "report_entitlement"
    retention:
      authorization_cache: "short_ttl_with_revocation"

  support:
    issuer: "https://idp.example.org"
    audience: "support-client"
    purpose: "requested_email_notification"
    allowed_claims:
      - "sub"
      - "verified_email_when_needed"
    retention:
      notification_delivery_record: "approved_short_period"
```

Giá trị mô tả policy; ứng dụng phải có code/config thực enforce. **Deny-by-default**: nếu một RP mới xuất hiện, mặc định chưa được phát group list/phone/HR attributes. Việc phát email phải có mục đích được duyệt, không chỉ vì nó dễ debug.

### 5.1. Các trường cần duyệt trong contract

1. **RP identity:** client_id/OIDC audience hoặc SAML entityID; chống attacker tự xưng là RP có quyền cao.
2. **Tenant và issuer:** không trộn directory của các tổ chức.
3. **Purpose code:** người quản trị có thể audit/kiểm soát.
4. **Allowed attributes:** tên chuẩn + aliases + transformation.
5. **Mandatory vs optional:** thiếu optional không được kéo tất cả attributes; thiếu mandatory phải fail safely.
6. **Consent/lawful basis/notice:** được privacy/legal review.
7. **Subject strategy:** pairwise, persistent hay transient ID theo nghiệp vụ.
8. **Session/retention:** dữ liệu hiện ở nơi nào sau login.
9. **Downstream sharing:** RP có được chuyển tiếp cho API/analytics không?
10. **Revocation/correction/deletion:** khi nào update, disable, unlink, purge.
11. **Monitoring/exception:** ai duyệt, ai theo dõi policy drift.
12. **Versioning:** thay contract là security/privacy change, không deploy âm thầm.

### 5.2. Chỉ gửi “đã được yêu cầu” vẫn chưa đủ nếu request quá rộng

Theo NIST SP 800-63C-4, một RP nên chỉ yêu cầu thông tin tối thiểu; IdP chỉ truyền thông tin phù hợp trust agreement/requests. Nhưng RP có thể cấu hình sai và yêu cầu `profile email phone address`. Do đó **hai phía phải kiểm soát**: RP request minimal, IdP enforce attribute allowlist, và RP hạn chế local persistence.

### 5.3. Khi nhiều RPs cùng owner

Cùng doanh nghiệp **không tự động có quyền correlation** giữa RPs. Nếu nghiệp vụ thực sự cần shared identifier, có thể thiết kế một sector/shared PPI theo hợp đồng và đánh giá privacy risk, nhưng không phát một global employee ID cho tất cả services chỉ vì chúng dùng chung AD.

## 6. Chọn định danh: email không phải khóa tài khoản bền vững

### 6.1. Khóa liên kết an toàn ở RP

Với OIDC, subject liên kết người dùng nên dựa trên **cặp `(iss, sub)`**:

```text
(issuer, subject) =
("https://idp.example.org", "opaque-sub-for-portal")
```

`sub` **chỉ có ý nghĩa trong phạm vi issuer**. Hai IdPs có thể trùng subject string nhưng là hai người khác nhau. RP nên giữ issuer/provider registration và subject trong account link; không dùng email làm primary key vì email có thể đổi, tái sử dụng, chưa xác minh hoặc dùng chung.

Với SAML 2.0, `NameID` và qualifier/format/IdP entityID đóng vai trò tương tự; cần hiểu NameID format thực sự đang dùng và đối chiếu đúng asserting party. Không giả định NameID = email hoặc persistent identifier theo mọi IdP.

### 6.2. Public vs pairwise subject identifiers

OIDC Core định nghĩa:

- **`public` subject:** cùng `sub` cho user tại các clients nhận public subject, có thể tạo correlation.
- **`pairwise` subject:** provider phát `sub` khác nhau theo **sector identifier** để hạn chế correlation giữa các RPs.

NIST SP 800-63C-4 cũng khuyến nghị/đưa quy định về **pairwise pseudonymous identifiers** theo Federation Assurance Level và trust context. Pairwise ID phải khó đoán, không chứa plaintext username/email/employee number; có thể được tạo bằng keyed derivation hay random mapping ở IdP.

```text
IdP user internal ID: employee-0042

Portal RP    sees sub = ppi-portal-8d...
Reports RP   sees sub = ppi-reports-2a...
Support RP   sees sub = ppi-support-f3...

All three represent one person at IdP,
but independent RPs cannot directly link by sub alone.
```

**Lưu ý:** pairwise `sub` không ngăn correlation nếu IdP đồng thời gửi **cùng email, tên và số điện thoại** cho ba RPs. Minimize accompanying attributes. Pairwise ID vẫn là **pseudonymous personal data** trong nhiều privacy contexts, không tuyên bố anonymous.

### 6.3. Thiết kế PPI không dùng hash đoán được

Sai:

```text
sub = SHA256(email)
```

Email có entropy thấp/dễ đoán, attacker có thể dictionary lookup, và cùng hash được phát cho nhiều RPs. Đúng hơn là **IdP-only keyed HMAC với secret an toàn**, sector/RP scope, issuer và immutable internal ID, hoặc random opaque mapping có kiểm soát. Key rotation/sector migration cần bảo toàn account-link strategy hoặc có migration flow đáng tin, không làm user account mất hoặc bị link sai.

### 6.4. Khi cần correlation có chủ đích

Một số business domains cần cùng identity ở Portal và Reports. Có thể:

- Dùng một **authorization broker** dịch subject giữa scopes với audit và purpose checks.
- Dùng shared sector group khi phù hợp OIDC subject rules và trust agreement.
- Dùng account-link consent/verified flow do user chủ động thực hiện.

Không chia sẻ mapping table `globalEmployeeId → mọi RP subject` cho các RP vốn không cần. Bảng ánh xạ này là **dữ liệu cá nhân và high-value correlation asset**.

## 7. OIDC: xin ít claim ngay từ đầu

### 7.1. Scope `openid` không phải “xin cả hồ sơ”

OIDC Core 1.0 xác định `openid` yêu cầu OIDC authentication. Các scope bổ sung có ý nghĩa:

| Scope | Tập claims có thể yêu cầu | Lưu ý |
| --- | --- | --- |
| `openid` | OIDC authentication với `sub` và core protocol claims trong ID Token | Không đồng nghĩa cần email/phone/address |
| `profile` | Tập profile claims như name, nickname, picture, **gender, birthdate**, locale... | **Rộng hơn nhiều người nghĩ**; đừng yêu cầu chỉ để lấy displayName nếu có cách ít hơn |
| `email` | `email`, `email_verified` | Chỉ cần nếu app thật sự gửi email/verify ownership |
| `phone` | `phone_number`, `phone_number_verified` | Không mặc định cho sign-in |
| `address` | `address` | Rủi ro riêng, hiếm khi cần cho SSO cơ bản |

Scope trong OIDC là **yêu cầu**, không bảo đảm mọi provider trả mọi giá trị. Claim `email_verified=true` có ngữ nghĩa verification của OP, nhưng không tự biến email thành immutable unique subject. `claims` request parameter có thể xin riêng claims nhưng hỗ trợ là **optional** theo OP metadata; RP phải xử lý thiếu optional claims.

### 7.2. Cấu hình Spring OAuth2 Client scope tối thiểu

Ví dụ Spring Boot config fragment cho client chỉ cần login:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: corporate
            client-id: portal-client
            scope:
              - openid
        provider:
          corporate:
            issuer-uri: https://idp.example.org
```

Đây chỉ là **fragment**: còn cần client authentication secret/configuration, TLS, redirect URIs, provider metadata và session controls. Quan trọng là **không tự thêm profile/email/phone/address**. Với một UI thật sự cần display name, trao đổi với IdP để có **release policy riêng** thay vì tự bật `profile` rộng rồi lưu toàn bộ ID Token.

Một OP vẫn có thể phát một số claims ngoài scopes do policy khác; RP còn cần kiểm soát storage/logging. Tuy nhiên **chỉ lọc ở RP không hoàn tác sự tiết lộ đã diễn ra**, nên chặn tại IdP là lớp ưu tiên.

### 7.3. Request từng claim với `claims` khi OP hỗ trợ

Ví dụ OIDC request parameter (chỉ là JSON phần `claims`, không phải một authorization URL hoàn chỉnh):

```json
{
  "userinfo": {
    "preferred_username": null
  }
}
```

Một ứng dụng chỉ cần greeting có thể xin một claim cụ thể thay cả `profile`, nếu OP có hỗ trợ `claims_parameter_supported`. Tuy nhiên `preferred_username` có thể nhận diện người dùng; hãy dùng `display_name` RP-specific hoặc derived greeting khi có thể, và không biến username thành globally shared key.

**Không tự thêm mọi PII vào ID Token:** ID Token thường được RP/client nhận trực tiếp và có thể đi qua browser/backchannel theo flow. Dùng UserInfo với TLS/Access Token được bảo vệ và release policy, nhưng **UserInfo cũng là dữ liệu cá nhân**; không trả “all” chỉ vì endpoint riêng.

### 7.4. Validate token là bắt buộc, minimization không thay security

RP vẫn phải validate issuer, audience, signature/JWK, expiration, nonce/state/PKCE theo flow và yêu cầu; `sub` sau validation mới có thể dùng làm subject. Không dùng browser-provided `sub` hay raw UserInfo từ endpoint chưa xác thực. NIST minimization không cho phép bỏ integrity/authentication controls.

## 8. Spring Security OIDC: map thuộc tính ít nhất có thể

Spring Security hỗ trợ `OidcUser`, `OidcUserService`, `OAuth2UserService` và `GrantedAuthoritiesMapper`. Chỉ vì `OidcUser.getClaims()` trả một map không có nghĩa ứng dụng nên copy nó vào bảng `users`, session, audit hoặc DTO.

### 8.1. Dùng issuer + subject làm account link

Ví dụ fragment Java trong ứng dụng Spring Security đã cấu hình OIDC:

```java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Fragment: OidcUser này đã được Spring Security xác thực.
public record FederatedAccountRef(String issuer, String subject) {}

public FederatedAccountRef accountRef(OidcUser user) {
    var token = user.getIdToken();
    return new FederatedAccountRef(
        token.getIssuer().toString(),
        token.getSubject()
    );
}
```

Không dùng `user.getEmail()` làm primary key và không lưu toàn bộ `user.getClaims()`. Với multi-tenant, thêm trusted tenant/registration ID vào khóa liên kết nếu architecture cần.

### 8.2. Sơ đồ xử lý domain riêng

```text
OidcUser (validated; có thể chứa nhiều claims)
   |
   +-- (iss, sub) -> AccountLink
   +-- approved entitlement -> local RoleMapping
   +-- optional display_name -> View DTO / short session
   |
   X-- KHÔNG serialize nguyên OidcUser/ID Token vào DB
   X-- KHÔNG log claims/JWT
   X-- KHÔNG trả token/PII sang frontend không cần thiết
```

**Lưu ý kỹ thuật:** Một custom mapper chỉ giảm dữ liệu của **domain entity/DTO**; nó không xóa những claims đã được IdP phát trong signed ID Token, và Spring Security security context có thể còn giữ `OidcUser` trong phiên. Để giảm dữ liệu ở nguồn cần IdP attribute release policy; để giảm dữ liệu tại RP cần kiểm soát cách lưu `SecurityContext`/session và serialization theo framework/version. Không chỉnh ID Token đã ký như một JSON tùy ý.

### 8.3. Quyền không phải mọi group

Spring có `GrantedAuthoritiesMapper` và delegating `OAuth2UserService` để map OIDC claims/group tới authorities. Nhưng một raw claim `groups` có thể chứa hàng trăm DNs. Nên lấy **RP-specific entitlement** từ IdP/authorization service, hoặc map server-side ra ``ROLE_REPORT_VIEWER``; không copy nguyên group map vào user profile hay browser-facing session.

Mọi rule “group -> ADMIN” phải gắn trusted issuer, đúng tenant/audience và role policy; **không tin browser JSON claims**. Fail closed khi quyền bắt buộc thiếu hoặc stale.

## 9. SAML 2.0: NameID và AttributeStatement tối thiểu

### 9.1. Ranh giới chia sẻ của SAML Assertion

SAML IdP gửi `Response/Assertion` có `Subject/NameID`, authentication context và có thể `AttributeStatement`:

```xml
<saml:AttributeStatement
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="active">
    <saml:AttributeValue>true</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="appRole">
    <saml:AttributeValue>REPORT_VIEWER</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
```

Đoạn XML chỉ minh họa hai attributes; production còn cần issuer, audience restriction, Recipient, signature validation và protocol metadata. **Signed/encrypted assertion vẫn có thể chia sẻ quá nhiều PII**. Mã hóa chỉ bảo vệ transport/confidentiality, không tự giảm dữ liệu mà RP được nhận.

### 9.2. Attribute release policy ở IdP

IdP nên cấu hình theo từng SP/RP `entityID`:

- SP Portal chỉ nhận NameID opaque/persistent hoặc transient đúng nhu cầu, plus display name nếu được duyệt.
- SP Reports nhận app-specific role/entitlement thay all groups.
- Không phát `mail`/`telephoneNumber`/`employeeNumber`/`homeAddress` theo default cho mọi SP.
- Với SP đối tác, dùng scoped/pairwise NameID và derived attribute nếu cần.
- SP A không được thay mặt SP B xin additional PII bằng cách sửa `AttributeConsumingService` mà không có IdP policy.
- Tên attribute và NameFormat/URI phải cố định, versioned, tránh collisions/alias đọc nhầm.

Nếu IdP gửi all groups một lần trong assertion, dù Spring chỉ đọc first element, dữ liệu đã đi đến RP. **Minimize ở nơi phát** trước rồi lọc DTO/thời hạn tại nơi nhận.

### 9.3. Spring Security đọc thuộc tính SAML2

Sau SAML Response validation thành công, principal ở Spring có thể là `Saml2AuthenticatedPrincipal`. Ví dụ:

```java
import org.springframework.security.saml2.provider.service.authentication
    .Saml2AuthenticatedPrincipal;

// Fragment trong một ứng dụng Spring MVC đã bật saml2Login.
public String labelFor(Saml2AuthenticatedPrincipal principal) {
    String displayName = principal.getFirstAttribute("displayName");
    return displayName != null ? displayName : "Đã đăng nhập";
}
```

SAML cho phép **multi-valued attributes**. `getFirstAttribute` chỉ lấy giá trị đầu; không dùng cho một claim nhiều giá trị `groups` rồi tự suy quyền. Và một app chỉ hiển thị tên không có nghĩa đã ngăn IdP gửi thêm thông tin. Config attribute release ở IdP, không dùng code controller làm privacy control duy nhất.

### 9.4. SAML NameID không nên là email khi không cần

Persistent opaque NameID giúp giữ account link dù email đổi. Transient NameID có thể phù hợp khi session ngắn và không cần persistent account, nhưng không thể dùng làm account link ổn định nếu giá trị thay đổi liên tục. Chọn NameID format theo mục đích và trust agreement, kiểm tra IdP behavior và migration.

## 10. LDAP/AD: chỉ đọc những attributes cần thiết

Rủi ro thường xuất hiện **trước** khi OIDC/SAML assertion được tạo: IdP hoặc ứng dụng truy vấn LDAP với default “get all user attributes”, rồi vô tình log/cache hoặc phát lại mọi trường.

### 10.1. LDAP RFC 4511: projection rất cụ thể

LDAP `SearchRequest.attributes` xác định những thuộc tính server trả:

- Danh sách **rỗng** hoặc `*` có thể yêu cầu **tất cả user attributes**.
- Chỉ `1.1` nghĩa là **không yêu cầu thuộc tính nào** (dùng khi chỉ cần kiểm tra entry tồn tại).
- Danh sách tên cụ thể như `uid`, `accountStatus` hoặc `entryUUID` chỉ yêu cầu các attributes đó.
- LDAP access control của server vẫn có quyền giới hạn hơn.
- Operational attributes thường cần yêu cầu rõ; tên/trường có thể khác OpenLDAP và AD.

Theo RFC 4511, **một danh sách projection rỗng không đồng nghĩa “không lấy gì”**. Đây là lỗi dễ gặp khi developer gọi API mà không truyền `returningAttributes`.

### 10.2. JNDI SearchControls chọn thuộc tính

Fragment Java dùng JNDI, giả định đã có `DirContext ctx` bảo vệ bằng LDAPS/StartTLS và bind account read-only:

```java
import javax.naming.NamingEnumeration;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

// Fragment: ctx phải được xây dựng có TLS, truststore và quyền đọc hẹp.
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(
        new String[] {"entryUUID", "accountStatus"});
controls.setCountLimit(1);
controls.setTimeLimit(2000);

// JNDI filter arguments giúp tránh nối input vào LDAP filter.
NamingEnumeration<SearchResult> results = ctx.search(
        "ou=people,dc=example,dc=org",
        "(uid={0})",
        new Object[] {uid},
        controls);
```

`entryUUID`/`accountStatus` chỉ là **schema ví dụ**; AD có thể dùng `objectGUID`, `userAccountControl` và cách tính account enabled khác. Không tự đọc tất cả AD attributes “vì chưa rõ schema” ở production; inventory và chỉ yêu cầu đúng trường.

### 10.3. Filter an toàn và directory permissions

- Tránh LDAP injection: dùng JNDI filter arguments hoặc escaping đúng schema.
- Dùng account search/bind có **quyền chỉ đọc** đúng OU/attributes cần thiết; nếu directory ACL không hỗ trợ field-level đủ tốt, đặt directory broker.
- Dùng LDAPS hoặc StartTLS với certificate validation, không plain LDAP qua đường không tin cậy.
- Không giữ connection/debug logs chứa user password, bind DN secrets hay toàn bộ SearchResult.
- Giới hạn subtree, size/time limits và pagination khi cần; không quét toàn thư mục theo cron rồi sao chép HR profile.
- Với group memberships, query quyền **trong app scope**; không dump toàn bộ `memberOf` vào session/JWT.

### 10.4. Phân biệt lookup để đăng nhập và directory synchronization

Một request login cần `active` + subject có thể chỉ cần 1–2 attributes. Một provisioning connector có thể cần thêm email/department cho một nghiệp vụ đã duyệt; đó là **pipeline và contract riêng**. Không lấy nhu cầu provisioning làm lý do mở rộng tất cả OIDC ID Tokens.

## 11. SCIM: giới hạn provisioning và response fields

SCIM (RFC 7643/7644) là giao thức quản lý vòng đời account/provisioning, khác SSO login. Một client SCIM có thể tạo/update/disable user ở RP trước khi họ đăng nhập, vì thế nguy cơ **lưu dữ liệu cá nhân lâu dài** cao hơn transient claims trong login.

### 11.1. Partial resource representations

RFC 7644 định nghĩa query parameters:

- `attributes=userName,active`: yêu cầu các trường cụ thể (ngoài fields được schema yêu cầu `returned=always`).
- `excludedAttributes=...`: loại một số fields khỏi default representation.
- Không dùng đồng thời `attributes` và `excludedAttributes` trong cùng request.
- Server tuân theo schema `returned` policy; một số attributes như SCIM `id` có `returned=always` và vẫn xuất hiện.
- `excludedAttributes` theo kiểu “trừ bớt” dễ bỏ sót field mới; **allowlist với attributes** thường dễ kiểm soát hơn.

Ví dụ SCIM query minh họa:

```http
GET /scim/v2/Users/opaque-account-id?attributes=id,active HTTP/1.1
Host: directory-api.example.org
Authorization: Bearer REDACTED_ACCESS_TOKEN
Accept: application/scim+json
```

Với một ứng dụng chỉ cần biết account có active, không yêu cầu `emails`, `phoneNumbers`, `addresses`, `manager` và toàn bộ enterprise extension. SCIM response còn phụ thuộc server schema và contract; không tự kết luận Query Projection thay thế authorization kiểm soát đọc.

### 11.2. SCIM `returned` và `mutability`

RFC 7643 mô tả schema metadata:

| `returned` | Ý nghĩa |
| --- | --- |
| `always` | Trả bất kể request projection, ví dụ resource ID |
| `default` | Trả mặc định, trừ khi request chọn subset |
| `request` | Chỉ trả trong các ngữ cảnh/request đã chỉ định |
| `never` | Không trả trong response |

`mutability=writeOnly` thường đi kèm `returned=never` đối với dữ liệu không được xuất trả. Không tự đặt password/token là SCIM attribute mặc định chỉ vì server cho phép extension.

### 11.3. De-provisioning khác xóa audit bắt buộc

Khi user rời tổ chức/không còn được phép dùng RP:

1. IdP/provisioning service gửi deactivate, delete hoặc unlink theo contract.
2. RP lập tức revoke access và active sessions/tokens theo policy.
3. Xóa hoặc tách không còn cần những profile fields đã đồng bộ.
4. Nếu có hồ sơ nghiệp vụ phải giữ vì obligation, giữ trong **restricted domain record** với retention riêng, không còn cho phép login hoặc dùng email cho mục đích khác.
5. Xóa/audit mapping subject theo quy định và xử lý backups.

NIST SP 800-63C-4 nhấn mạnh giới hạn **những subscriber accounts được provision cho RP** và việc deprovision accounts đã terminated, trừ các hạn chế của retention requirements/policy/regulations. Đừng tự provision toàn bộ 100.000 employees cho một RP chỉ có 100 users được duyệt.

## 12. Authorization: giảm group/role data mà vẫn an toàn

### 12.1. “Cho mọi group” không phải chi tiết cần thiết cho RP

Một IdP có thể biết `memberOf` chứa:

```text
CN=Project-Secret-A
CN=Project-Secret-B
CN=Finance-Staff
CN=HR-Benefits
CN=VPN-Admins
...
```

Reports RP chỉ cần biết `REPORT_VIEW`. Gửi toàn bộ 200 groups vừa lộ cơ cấu tổ chức, vừa có thể dẫn đến mapping privilege nhầm. Một giải pháp:

```text
IdP/Authorization Broker
  directory groups / HR roles
             |
             v
Policy: can user view Reports?
             |
             v
RP-specific claim: reportAccess=VIEW
             |
             v
Reports app uses allowlisted authorization mapping
```

**Security caveat:** Role/entitlement phải được tạo từ nguồn trusted và cập nhật khi group changes. Giảm thuộc tính không có nghĩa RP được tin bất kỳ boolean client gửi. Kiểm tra `iss`, `aud`, signature, expiry, tenant và freshness.

### 12.2. Tính lại khi cần thay vì cache vô hạn

Entitlement thay đổi thường xuyên có thể cần policy decision service hoặc short TTL cache; nếu RP giữ `isAdmin=true` trong session 30 ngày, user bị thu hồi quyền có thể còn access. Thiết kế `authorization_ttl`, invalidate khi deprovision/role change và re-evaluate những thao tác nhạy cảm. Đây là **freshness và revocation**, không phải cớ để lưu toàn bộ directory group list.

### 12.3. Chia tách Authentication và Authorization

`Authenticated` nghĩa là IdP đã xác minh user; `Authorized` nghĩa app quyết định cho chức năng cụ thể. Một `sub` hợp lệ không tự có quyền `ADMIN`. Minimal identity claims có thể kết hợp local resource-based policies để tránh phát quá nhiều attributes.

## 13. Tối thiểu hóa sau khi nhận: request, session, DB, API

### 13.1. Tránh “copy all claims” trong entity

Anti-pattern:

```java
// SAI: đưa mọi claim của OIDC principal vào database.
// userEntity.setProfileJson(serialize(oidcUser.getClaims()));
// logging.info("claims={}", oidcUser.getClaims());
```

Nguy cơ: birthday/address/groups hiện diện lâu dài, searchable, replicated, backup; khi IdP thay release policy, bản sao cũ vẫn nằm DB.

Phương án tốt hơn:

```text
AccountLink {
  rpAccountId          (random internal ID)
  trustedIssuerId
  scopedSubject        (RP-specific)
  status
  createdAt/lastLoginAt
}

Optional UserPreference {
  rpAccountId
  displayName         (only if needed by UI)
  updatedAt/retentionPolicyId
}

RoleAssignment {
  rpAccountId
  appRole
  expiresAt / policyVersion
}
```

Nếu không cần hiển thị tên giữa các sessions, có thể chỉ lưu account link và tra short-lived display name từ approved source lúc render. **Không dùng account email làm foreign key cho toàn bộ business tables** vì đổi email làm sai identity link.

### 13.2. Session có thể chứa nhiều dữ liệu hơn bạn tưởng

Spring Security có thể giữ `OidcUser`/`Saml2Authentication` trong `SecurityContext`. Nếu framework serializes toàn bộ principal vào Spring Session Redis, full claims có thể đã nằm trong **session store**, dù JPA entity đã tối giản.

Cần kiểm tra:

- Serialized principal có những claims nào?
- Token/ID Token/Authentication stored ở đâu, TTL bao lâu?
- Java session persistence/Redis backups có encryption/ACL?
- Session invalidation/logout có thực sự xóa dữ liệu?
- Custom principal có được tạo sau **trusted authentication** với required context/authorities và không phá Spring semantics?
- Có diagnostics/heap dump hay exceptions giữ raw claims không?

**Không tự sửa `DefaultOidcUser` để loại claim khỏi signed ID Token**; ID Token đã ký phải được kiểm chứng nguyên vẹn. Ưu tiên IdP không phát PII không cần; ở RP giới hạn authorization/domain projection và retention.

### 13.3. API downstream không được nhận nguyên principal

Một backend chỉ cần `userId` và `canSubmit=true` không nên được chuyển nguyên `OidcUser`, SAML Assertion XML hoặc access token có scopes/claims rộng. Thiết kế **audience-restricted downstream token** hoặc service-side authorization decision, giảm propagation và accidental logging. Không đưa thẳng principal map vào JSON response cho frontend.

## 14. Chính sách lưu dữ liệu theo vòng đời

Một retention matrix minh họa (mốc chỉ để bàn luận, **không phải yêu cầu pháp lý hoặc cấu hình mặc định**):

| Loại dữ liệu | Nơi giữ | Điểm xóa/refresh | Lưu ý |
| --- | --- | --- | --- |
| OIDC/SAML raw authentication response | Bộ nhớ khi validate, framework session nếu cần | Theo protocol/session lifecycle; tránh DB persistence | Không log raw token/assertion |
| Display name dùng rendering | Request/short session | Logout/TTL | Có thể tra lại khi cần |
| `(iss, sub)` account link | RP account table | Unlink/deprovision/account termination | Bảo vệ linkage/pseudonymous data |
| RP-specific entitlement | Session/short authorization cache | TTL hoặc revocation event | Fail closed khi stale |
| Email để gửi notification | On-demand hoặc business record tối thiểu | Theo mục đích delivery/approved retention | Không copy sang analytics |
| Transaction data có nghĩa vụ retention | Domain database tách identity | Theo legal/business retention plan | Không xóa trái nghĩa vụ; restrict |
| Security audit | Audit store | Retention theo policy/legitimate requirement | Opaque event IDs, no raw claims |
| Search/analytics index | Derived/minimized dataset | Reindex/purge đồng bộ khi source xóa | De-identification không mặc định anonymous |
| Backups | Encrypted backup vault | Rotation/expiry + restore controls | Phải tránh “data resurrection” sau restore |

### 14.1. TTL ≠ xóa thật ở mọi nơi

Cài Redis `EX 3600` chỉ khiến cache key hết hạn ở Redis; nó không xóa audit, stream logs, replicas, DB backups, dead-letter queues, trace captures, CSV exports hoặc browser storage.

Để giới hạn giữ dữ liệu, cần **data lineage inventory** và mỗi storage sink có **deletion/retention policy**. Nếu có luật yêu cầu giữ một phần record, phải **tách record giữ lại** và chặn reuse ngoài mục đích.

### 14.2. Cập nhật/correction

Nếu display name/email ở directory đổi:

- RP không nên dùng stale cached email như identity key.
- Nếu cần cập nhật, nhận event/SCIM PATCH hoặc re-fetch approved source.
- Mapping subject ổn định không đổi chỉ vì email đổi.
- Nếu user yêu cầu correction/deletion, có quy trình propagate tới các bản sao RP thích hợp.
- Cần audit hoạt động correction mà **không giữ nội dung cũ quá mức cần thiết**.

### 14.3. Account disabled, deprovisioned và terminated

- `Disabled`: không cho login/access; có thể giữ một số records được phép.
- `Deprovisioned`: RP không còn được gắn identity/provisioning population, cần remove access/links theo trust agreement.
- `Terminated`: account xóa/đóng theo policy; xử lý remaining records và retention restrictions.
- `Legal hold`: chỉ giữ dữ liệu thật sự bắt buộc và hạn chế truy cập, không giữ full HR profile vì dễ.

Không trộn các trạng thái này thành một flag `deleted` mà không định nghĩa impact với sessions/tokens và data retention.

## 15. Logs, metrics, APM và support có thể là nguồn lộ lớn nhất

Theo OWASP Logging Cheat Sheet, không nên ghi trực tiếp access tokens, session IDs, passwords, secrets, sensitive personal information và dữ liệu vượt classification của logging system.

### 15.1. Không log token hoặc user object

Sai:

```text
DEBUG OIDC response = <all ID Token claims>
INFO newUser: email + phone + homeAddress + birthDate
TRACE LDAP SearchResult: <all attributes>
AUDIT authentication: raw SAML Assertion XML
METRIC login_total{email="user@example.org"}
```

Đúng hơn:

```json
{
  "event": "federation_login_success",
  "rp": "reports",
  "idp": "corporate",
  "policy_version": "attr-release-v3",
  "disclosure_fields": ["sub", "report_entitlement"],
  "correlation_id": "request-opaque-id",
  "result": "success"
}
```

Đây là JSON telemetry **minh họa**: không log `sub` raw, NameID, email, LDAP DN, employee ID, groups, token hoặc full request. `disclosure_fields` liệt kê **tên các field** đã được phê duyệt, không lưu values. Mỗi tổ chức phải kiểm tra liệu các IDs và field names tự chúng có làm lộ thông tin nhạy cảm hay không.

### 15.2. Những tầng cần redaction

- Spring MVC/GraphQL request logs và security events.
- OAuth2 callback logs chứa `code`, `id_token` hoặc `access_token`.
- Reverse proxy/Ingress `request_uri`, response bodies nếu tracing.
- LDAP client debug, SAML XML/Assertion, OIDC UserInfo bodies.
- Redis/DB query logs, ORM `toString()`.
- Message bus payloads, dead-letter queues, support exports.
- APM/Distributed tracing, crash dumps, heap dumps.
- Client-side browser analytics, HTTP response payloads, local/session storage.
- KMS secret metadata và correlation tables.

**Hash không luôn đủ:** hash email không có keyed secret có thể bị dictionary attack. Nếu cần link logs trong thời gian hữu hạn, dùng **rotating keyed pseudonymous event identifiers** và TTL phù hợp, đánh giá khả năng correlation. Không đưa `sub` pairwise sang analytics như “ẩn danh tuyệt đối”.

## 16. Trust, bảo mật, quyền cá nhân và căn cứ xử lý

### 16.1. Identity minimization không thay authentication verification

OIDC ID Token vẫn phải verify signature/issuer/audience/expiry/nonce; SAML Assertion vẫn phải verify trusted signing cert, issuer, audience/recipient/InResponseTo/replay/time. LDAP cần TLS, bind ACL và safe filters. **Không bỏ các verification fields cốt lõi** chỉ để giảm số claim; các trường protocol security không đồng nhất với tùy chọn profile PII.

### 16.2. Derived attributes cần nguồn đáng tin

Nếu app được gửi `eligible=true` thay ngày sinh, cần trust IdP đã tính eligibility đúng quy định và mức assurance cần thiết. Không cho browser hay untrusted RP tự điền flag này. Tương tự `role=viewer` phải đến từ authorization policy đáng tin, không từ username claim.

### 16.3. Quyền cá nhân và exception

Một chương trình privacy governance thực tế cần:

1. **Notice/transparency:** mô tả app nào nhận dữ liệu nào và vì sao.
2. **Access/correction:** cách truy vấn, sửa thuộc tính nguồn và propagate.
3. **Erasure/deprovision:** xóa account links, attributes, caches nếu không còn cần.
4. **Consent/withdrawal nếu áp dụng:** revoke attribute release và xử lý downstream retention phù hợp.
5. **Retention exceptions:** statutory records, security audit, legal hold có owner/expiry và access controls.
6. **Breach incident response:** xác định IdP/RPs đã nhận field nào, hạn chế rò rỉ và thông báo theo yêu cầu áp dụng.
7. **Third-party processors:** hợp đồng, transfer/boundary, retention và access protections.
8. **Periodic reviews:** attribute release policies, group claim sprawl, unused fields, deprovision errors.

Không coi “đã bật encryption” là đã đáp ứng yêu cầu **data minimization**. Encryption giới hạn người đọc trái phép, không hạn chế RP được phép nhận quá nhiều dữ liệu.

## 17. Java 17 độc lập: release allowlist, pairwise ID và TTL

Chương trình không cần Spring, IdP, LDAP hoặc database. Nó minh họa:

- **Directory nguồn** chứa nhiều attributes.
- **Mỗi RP** có allowlist riêng; một yêu cầu email từ RP Reports bị từ chối.
- IdP phát **subject pseudonymous khác nhau theo RP**, được tính bằng HMAC key giả lập.
- Không xuất phone/birthDate sang Portal/Reports.
- Một kho minh họa chỉ giữ **email** của RP Support trong thời hạn có giới hạn, không giữ full claim map.
- Bản ghi quá TTL không còn truy cập được và được purge.
- Một RP khác không thể tra bản ghi Support; unlink xóa bản sao.

**Giới hạn quan trọng:** đây là mô hình policy ở mức Java, không phát OIDC ID Token hoặc SAML Assertion, không xác minh tokens, không có TLS, SQL, consent, KMS, key rotation/backup hay pháp lý. HMAC key được hardcode **chỉ để demo có kết quả xác định**, tuyệt đối không dùng production; khóa thực phải ở secret manager/HSM và có migration/recovery plan. Pseudonymous `sub` vẫn có thể là dữ liệu cá nhân.

Lưu file `MinimalAttributeReleaseDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MinimalAttributeReleaseDemo {

    private static final String ISSUER = "https://idp.example.org";
    private static final byte[] DEMO_HMAC_KEY =
        "demo-only-not-a-production-secret".getBytes(
            StandardCharsets.UTF_8);

    record Policy(Set<String> allowed) {}
    record Saved(Map<String, String> data, Instant expiresAt) {}

    static final class AttributeBroker {
        private final Map<String, Policy> policies = Map.of(
            "portal", new Policy(Set.of("active", "displayName")),
            "reports", new Policy(Set.of("active")),
            "support", new Policy(Set.of("email"))
        );

        private String pairwiseSubject(String rp, String internalId)
                throws GeneralSecurityException {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                DEMO_HMAC_KEY, "HmacSHA256"));
            String input = ISSUER + "|" + rp + "|" + internalId;
            byte[] digest = mac.doFinal(
                input.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest).substring(0, 24);
        }

        Map<String, String> release(
                String rp, Set<String> requested,
                Map<String, String> directory)
                throws GeneralSecurityException {
            Policy policy = policies.get(rp);
            if (policy == null ||
                    !policy.allowed().containsAll(requested)) {
                throw new SecurityException(
                    "Attribute request not approved for RP");
            }

            String internalId = directory.get("internalId");
            if (internalId == null || internalId.isBlank()) {
                throw new SecurityException(
                    "Missing trusted internal subject");
            }

            Map<String, String> out = new LinkedHashMap<>();
            out.put("iss", ISSUER);
            out.put("sub", pairwiseSubject(rp, internalId));
            for (String field : requested) {
                String value = directory.get(field);
                if (value != null) {
                    out.put(field, value);
                }
            }
            return Map.copyOf(out);
        }
    }

    static final class MinimalRetentionStore {
        private final Map<String, Saved> data = new HashMap<>();

        private String key(String rp, String sub) {
            return rp + "|" + sub;
        }

        void saveSupportEmail(Map<String, String> claims,
                              Instant now, Duration ttl) {
            if (ttl.isNegative() || ttl.isZero() ||
                    !claims.containsKey("email") ||
                    !claims.containsKey("sub")) {
                throw new IllegalArgumentException(
                    "Email and positive TTL required");
            }
            data.put(key("support", claims.get("sub")),
                new Saved(Map.of("email", claims.get("email")),
                          now.plus(ttl)));
        }

        boolean exists(String rp, String sub, Instant now) {
            Saved record = data.get(key(rp, sub));
            return record != null &&
                    now.isBefore(record.expiresAt());
        }

        boolean onlyEmailStored() {
            return data.values().stream().allMatch(
                v -> v.data().keySet().equals(Set.of("email")));
        }

        int purge(Instant now) {
            int before = data.size();
            data.entrySet().removeIf(
                e -> !now.isBefore(e.getValue().expiresAt()));
            return before - data.size();
        }

        void unlink(String rp, String sub) {
            data.remove(key(rp, sub));
        }
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        Map<String, String> directory = Map.of(
            "internalId", "employee-0042",
            "active", "true",
            "displayName", "Lan",
            "email", "lan@example.org",
            "phone", "+84-000000",
            "birthDate", "1990-01-01",
            "homeAddress", "hidden-address",
            "salaryBand", "confidential"
        );

        AttributeBroker broker = new AttributeBroker();

        Map<String, String> portal = broker.release(
            "portal", Set.of("active", "displayName"),
            directory);
        Map<String, String> reports = broker.release(
            "reports", Set.of("active"), directory);
        Map<String, String> support = broker.release(
            "support", Set.of("email"), directory);

        System.out.println("Portal fields: " +
                new TreeSet<>(portal.keySet()));
        System.out.println("Reports fields: " +
                new TreeSet<>(reports.keySet()));
        System.out.println("Different RP subjects: " +
                !portal.get("sub").equals(reports.get("sub")));
        System.out.println("Stable Portal subject: " +
                portal.get("sub").equals(
                    broker.release("portal",
                        Set.of("active"), directory).get("sub")));

        boolean blocked = false;
        try {
            broker.release("reports", Set.of("email"), directory);
        } catch (SecurityException expected) {
            blocked = true;
        }
        System.out.println("Reports email request rejected: " +
                blocked);
        System.out.println("Portal phone disclosed: " +
                portal.containsKey("phone"));
        System.out.println("No birthDate released: " +
                !portal.containsKey("birthDate") &&
                !reports.containsKey("birthDate"));

        Instant now = Instant.parse("2026-11-07T00:00:00Z");
        MinimalRetentionStore store = new MinimalRetentionStore();
        store.saveSupportEmail(support, now, Duration.ofDays(2));

        System.out.println("Support stored only email: " +
                store.onlyEmailStored());
        System.out.println("Other RP cannot read support data: " +
                !store.exists("reports", support.get("sub"),
                    now.plus(Duration.ofHours(1))));
        System.out.println("Available within TTL: " +
                store.exists("support", support.get("sub"),
                    now.plus(Duration.ofDays(1))));
        System.out.println("Expired at cutoff: " +
                !store.exists("support", support.get("sub"),
                    now.plus(Duration.ofDays(2))));
        System.out.println("Purge removed: " +
                store.purge(now.plus(Duration.ofDays(2))));

        store.saveSupportEmail(support, now, Duration.ofDays(2));
        store.unlink("support", support.get("sub"));
        System.out.println("Unlink removed record: " +
                !store.exists("support", support.get("sub"),
                    now.plus(Duration.ofHours(1))));
    }
}
```

Chạy:

```bash
javac MinimalAttributeReleaseDemo.java
java MinimalAttributeReleaseDemo
```

Stdout **chính xác**:

```text
Portal fields: [active, displayName, iss, sub]
Reports fields: [active, iss, sub]
Different RP subjects: true
Stable Portal subject: true
Reports email request rejected: true
Portal phone disclosed: false
No birthDate released: true
Support stored only email: true
Other RP cannot read support data: true
Available within TTL: true
Expired at cutoff: true
Purge removed: 1
Unlink removed record: true
```

### 17.1. Vì sao kết quả như vậy?

- Portal được phép nhận `active` và `displayName`, ngoài `iss/sub` là các protocol identity fields mô phỏng.
- Reports chỉ được `active` và `iss/sub`; email request vượt allowlist nên broker **throw SecurityException**, không im lặng phát dữ liệu.
- Cùng internalId nhưng RP khác tạo HMAC input khác → pairwise subjects khác; cùng RP+internalId cho subject ổn định.
- Phone và birthDate không ở RP output mặc dù directory nguồn có.
- Store chỉ ghi `email` của Support, không ghi original claims, source employee ID hay birthDate.
- TTL kiểm tra bằng `now.isBefore(expiresAt)`; **đúng thời điểm cutoff là hết hạn**.
- Purge xóa bản ghi đã expired; unlink xóa record dù thời gian giữ chưa hết.
- `Other RP cannot read` minh họa namespace isolation; mã demo không có real authentication/authorization và không chứng minh dữ liệu trong DB được bảo vệ bằng ACL.

### 17.2. Các giới hạn cần bổ sung trước production

1. HMAC key phải từ KMS/secret manager, không hardcode; version/rotation có thể làm subject thay đổi nếu không có stable mapping/compatibility plan.
2. Một RP thực có thể có nhiều tenants; `issuer, tenant, client registration/sector` phải là trusted values, không nhận từ query user tùy ý.
3. Không có OIDC token issuance/verification hay SAML assertion signing/validating.
4. Chương trình không xác minh căn cứ xử lý/consent và notice; chỉ minh họa purpose policy.
5. Không có encrypted database/Redis, real TTL jobs, transactions, multi-node consistency hay backups.
6. `Map` chứa source PII trong memory để demo; production cần control memory dumps/serialization.
7. Store cho `support` không có actual caller authentication, chỉ namespace key; production phải kiểm tra RP identity/server authorization.
8. Keyed pseudonymization **không đồng nghĩa ẩn danh**; vẫn có correlation/re-identification nếu release kèm name/email.
9. Không xử lý alias, user merge/split, account recovery, account linking và data-subject requests.
10. Ngoài storage layer, phải loại PII khỏi logs/APM/search indices/backups theo policy.

## 18. Kiểm thử: phải chứng minh điều gì không được tiết lộ?

### 18.1. Positive tests

| Kiểm thử | Kết quả cần thấy |
| --- | --- |
| Portal RP chỉ xin `openid` | ID Token chỉ có protocol/identity fields do policy cho phép; không email/phone không cần |
| Portal xin display name được duyệt | Chỉ preferred name được phát theo hợp đồng, không full profile mặc định |
| Reports nhận role riêng | Chỉ role/report entitlement, không full group DNs |
| LDAP projection chỉ định 2 attributes | Search response không chứa các fields còn lại |
| SCIM `attributes=id,active` | Không có email/phone/addresses nếu schema/policy không bắt buộc |
| OIDC `(iss, sub)` stable | Cùng subject được nhận biết đúng trên nhiều sessions cùng RP |
| Pairwise khác RP | Portal sub khác Reports sub cho cùng user |
| Short-lived authorization cache | Thay đổi quyền/deprovision được áp trước TTL đã duyệt |
| Retention job | Record expired không còn được dùng và bị purge |
| Local logout/session destroy | Temporary profile/tokens không còn accessible |

### 18.2. Negative tests về privacy và security

| Tình huống | Kỳ vọng |
| --- | --- |
| Reports xin `email` dù chưa duyệt | **Deny** release, báo audit field name/reason |
| Một client mới không có contract | Không phát optional profile attributes |
| RP cố ép `scope=profile email phone address` | IdP release policy không mở rộng trái contract |
| `claims` request OP không hỗ trợ | App xử lý thiếu optional claim, không fallback xin toàn bộ profile |
| SAML SP gửi AttributeConsumingService yêu cầu nhiều fields | IdP không phát ngoài allowlist |
| SAML Assertion signed chứa birthDate ngoài policy | Privacy QA **FAIL** dù signature valid |
| LDAP search returningAttributes rỗng | Test phát hiện có thể trả tất cả user attributes |
| LDAP injection vào filter | Không truy cập được người/attribute ngoài mục đích |
| SCIM query `excludedAttributes` bỏ sót field mới | Release regression test fail; dùng allowlist |
| SCIM provision tất cả employees cho RP nhỏ | Population policy fail; giới hạn authorized accounts |
| RP dùng email làm primary key | Identity model QA FAIL nếu email đổi/recycled |
| IdP A và IdP B có cùng `sub` text | RP dùng `(iss, sub)`, không merge hai users |
| Pairwise `sub` nhưng phát cùng email ở nhiều RPs | Privacy correlation test chỉ ra nguy cơ |
| HMAC không có key dùng SHA256(email) | Privacy QA FAIL đối với stable pairwise ID |
| User bị deprovision | Revoke access, unlink identity, purge profile theo policy |
| User sửa email | Không đứt account link, stale copy được xử lý |
| Retention TTL hết | Không còn đọc dữ liệu, cleanup running |
| Backup restore hồ sơ đã xóa | Replay deletion tombstones/policy; không hồi sinh account |
| Raw JWT/SAML/LDAP entry trong debug log | Security QA FAIL |
| Personal data trong metric labels | Privacy QA FAIL |
| JWT userInfo claim được trả trong API response ngoài mục đích | Reject/strip trước release |
| Session serialized toàn OIDC claims vào Redis | Privacy QA nếu ngoài policy; sửa IdP release/session storage |
| Cross-tenant PPI mapping | Không thể lấy subject/data tenant khác |
| Authorization role stale | Fail closed/revalidate theo criticality |
| Legal hold record | Chỉ giữ phần cần thiết, restricted purpose, explicit expiry/review |
| Consent bị rút khi cần | Dừng release/xử lý theo policy và quyền áp dụng |

### 18.3. Kiểm thử cả IdP và RP

**Chỉ nhìn dữ liệu đã vào database RP là chưa đủ.** Phải inspect:

- SAML Assertion payload đã giải mã ở test environment.
- OIDC ID Token và UserInfo actual claims trên login test.
- LDAP/SCIM responses server thực trả.
- Spring Security principal/session serialization.
- Downstream REST DTOs.
- Log pipeline/APM/search index/backup snapshots.

Một test “portal DB chỉ có displayName” không bắt được việc signed ID Token vẫn mang birthDate qua mạng hoặc Redis session serialization giữ full JWT.

### 18.4. Data-flow regression test

Mỗi lần IdP nâng cấp schema hoặc thêm một claim, contract test nên chạy **deny-by-default**: field mới không tự xuất hiện ở RPs. Mỗi lần app thêm mục đích mới (gửi email, export báo cáo), cần cập nhật approval và retention. Không mở `profile` vĩnh viễn vì từng có một lần release cần thiết.

## 19. Runbook áp dụng trong dự án

### Bước 1 — Vẽ luồng dữ liệu

Liệt kê directory → IdP → protocol response → RP SecurityContext → DB/cache/log/API/backend. Với mỗi mũi tên ghi issuer, RP/tenant, mục đích và nơi dữ liệu đến.

### Bước 2 — Lập inventory và phân loại

Liệt kê tất cả LDAP attributes, OIDC claims, SAML AttributeStatements, SCIM fields hiện được dùng. Chia: protocol/security required, authorization, UX, business-domain, sensitive/never release. Đặc biệt rà soát multi-valued `groups`.

### Bước 3 — Duyệt contract per RP

Tạo allowlist và những trường **bị cấm**. Xác định issuer/sector ID, scopes, consent/trust agreement, TTL và deprovision triggers. Có owner và policy version để audit.

### Bước 4 — Chặn tại nguồn

Giảm LDAP SearchRequest projection; trong IdP chỉnh attribute mapper/release rules; trong OIDC hạn chế scopes/claims; trong SAML hạn chế released attributes; trong SCIM giới hạn population/fields. Không dùng RP-only filtering làm giải pháp duy nhất.

### Bước 5 — Hạn chế RP persistence

Map subject sang random local account ID; tách fields chỉ cần session với dữ liệu giữ lại. Cấu hình Spring Session, caches và JSON serialization. Không đưa raw principals/claims tới frontend, logs hay downstream APIs.

### Bước 6 — Retention, correction và deprovisioning

Thiết kế expiry/access checks, purge jobs, delete/unlink events, backup restore controls, legal holds/restrictions. Kiểm tra user role change và account disable có revoke sessions/tokens phù hợp.

### Bước 7 — Privacy/security integration tests

Test positive requests tối thiểu và negative attribute escalation; so ID Token/SAML/SCIM actual payload; test pairwise IDs, cross-tenant, logs, TTL, deletion và restore.

### Bước 8 — Theo dõi drift

Một số metrics phù hợp: số attribute-policy violations theo RP, số inactive accounts chưa deprovision, số cache entries quá TTL, tỷ lệ request userInfo không cần thiết, số claims trong issued assertions theo allowlist. **Không** đưa raw emails/sub/NameIDs vào metric labels.

## 20. Những lỗi thiết kế phổ biến

| Anti-pattern | Vì sao có vấn đề | Phương án tốt hơn |
| --- | --- | --- |
| Xin OIDC `profile email phone address` cho mọi app | Mở rộng tiết lộ không cần thiết | `openid` + approved claims tùy RP |
| JWT/ID Token chứa mọi HR field | Dữ liệu đến nhiều hệ thống, lưu/backup khó kiểm soát | IdP release minimal claims |
| Dùng email làm ID | Email có thể đổi, reused, dễ link | `(issuer, subject)` opaque/pairwise |
| SHA256(email) làm pairwise `sub` | Dễ đoán, correlation giữa RPs | Keyed/IdP-managed PPI per sector |
| Toàn bộ `memberOf` vào token | Lộ group structure/roles | RP-specific derived entitlement |
| Dùng SAML signing thay attribute policy | Signature chỉ bảo vệ integrity/authenticity | Release allowlist trước khi sign |
| Gọi LDAP search mặc định không projection | Có thể trả toàn bộ user attrs | `setReturningAttributes` cụ thể |
| SCIM `excludedAttributes` làm kiểm soát chính | Có thể bỏ sót field mới | Allowlist query/schema + population policy |
| Đồng bộ mọi nhân viên tới mọi RP | Nhân bản dữ liệu và account không cần | Authorized account population, JIT provisioning |
| Spring Security session chứa full profile vô hạn | Redis/backup kéo dài PII | IdP minimization + session lifecycle control |
| Log `oidcUser.getClaims()` | Dữ liệu cá nhân/secret rò trong logs | Event code, approved metadata only |
| Hash email rồi coi anonymous | Dễ link/dictionary và có mapping | Treat pseudonym as protected personal data |
| Xóa JPA record nhưng không xóa backups | Restore có thể hồi sinh dữ liệu | Backup retention/tombstones |
| Tắt app account nhưng giữ token active | Access chưa bị revoke | Token/session revocation theo policy |
| Dùng một retention TTL cho mọi data | Không phản ánh mục đích/obligation | Retention schedule theo từng loại |
| Consent là lý do để thu mọi thứ | Consent có phạm vi, lawful basis riêng | Purpose-specific necessity and transparency |

## 21. Checklist production

- [ ] Mỗi RP/client có owner, purpose, issuer, tenant và allowlist attributes.
- [ ] Thư mục LDAP được tìm với returningAttributes cụ thể, bind ACL tối thiểu.
- [ ] OIDC scopes/claims không mặc định xin profile/email/phone/address nếu không cần.
- [ ] IdP release policy enforce per RP, không chỉ lọc DTO ở RP.
- [ ] SAML NameID/AttributeStatement đúng mục đích, không group dump.
- [ ] SCIM giới hạn provisioning population và attributes/returned policy.
- [ ] Subject key ở RP là trusted issuer + scoped subject, không dùng email.
- [ ] Pairwise PPI không lộ plaintext PII, không dựa SHA256(email) không có secret.
- [ ] Multi-tenant và cross-RP mapping không có leakage.
- [ ] Derived authorization/eligibility từ nguồn tin cậy, có policy freshness.
- [ ] Không lưu raw ID Token, SAML Assertion, LDAP SearchResult trong account database.
- [ ] Spring Session/Redis serialization đã được review để không giữ profile quá mức.
- [ ] Domain records chứa PII có purpose, retention owner, expiry/review.
- [ ] Token/session deprovision, logout và role-change revocation được kiểm thử.
- [ ] Purge jobs xử lý caches, DB, logs, search indices, exports và backups theo policy.
- [ ] User correction/erasure/unlink/withdrawal có workflow rõ.
- [ ] Data retained vì legal hold được tách, restricted và reviewed.
- [ ] Không log raw NameID/sub/email/access token/JWT/attributes/passwords.
- [ ] QA có negative tests claim escalation, SCIM leakage, LDAP projection và cross-tenant.
- [ ] Contract versioning và monitoring phát hiện field mới ngoài allowlist.
- [ ] Các quyền và thời hạn được privacy/security/legal owners phê duyệt theo nơi áp dụng.

## 22. Câu hỏi ôn tập

**1. Chỉ vì directory có `mail` thì mọi ứng dụng được nhận email không?**  
Không. Mỗi RP cần một mục đích và attribute release contract riêng; đăng nhập thường chỉ cần stable subject.

**2. Tối thiểu hóa dữ liệu có nghĩa chỉ lọc JSON DTO trong controller không?**  
Không. Nếu IdP đã phát claim, dữ liệu đã được chia sẻ. Phải giảm ở nơi phát, và hạn chế lưu/ghi log tại nơi nhận.

**3. Vì sao OIDC `profile` có thể là lựa chọn quá rộng?**  
Vì nó yêu cầu tập nhiều standard profile claims, có thể gồm birthdate/gender/picture, không chỉ display name.

**4. RP nên dùng email hay `(iss, sub)` để link account?**  
`(issuer, subject)` từ token đã verify; email có thể đổi hoặc reused.

**5. Pairwise subject có ngăn mọi khả năng nhận diện giữa các apps không?**  
Không. Nếu cùng email/tên/phone đi kèm, RPs vẫn có thể correlation. PPI cũng thường là pseudonymous personal data.

**6. Tại sao SHA256(email) không đủ để tạo PPI?**  
Email dễ đoán và hash không có key dễ brute-force, còn giá trị chung cho RPs tạo correlation. Dùng IdP-managed, keyed sector-specific derivation hoặc random mapping.

**7. LDAP `attributes=[]` có nghĩa không trả field nào?**  
Không. Theo RFC 4511, danh sách trống yêu cầu all user attributes; chỉ `1.1` biểu thị no attributes.

**8. SCIM `attributes=id,active` có loại được `id` khi không yêu cầu?**  
Không, vì schema `returned=always` (như `id`) vẫn cần được trả; còn `active` là explicitly requested.

**9. Tại sao gửi all groups không nên là default?**  
Vì lộ cấu trúc tổ chức và quyền không liên quan; có thể phát RP-specific entitlement hoặc policy decision thay thế.

**10. Nếu chỉ cần user trên 18 tuổi, RP có cần ngày sinh?**  
Thường không. Có thể dùng verified derived `over18` nếu assurance và policy phù hợp.

**11. User rời công ty, chỉ disable OIDC login đã đủ để xóa dữ liệu chưa?**  
Chưa. RP có thể giữ SCIM-provisioned account, caches, records, tokens và backups; cần deprovision/retention workflow.

**12. TTL Redis một giờ có bảo đảm dữ liệu cá nhân đã xóa hết?**  
Không. Còn logs, backups, replicas, DB, analytics và exports khác.

**13. SAML Assertion đã signed có tự bảo đảm data minimization không?**  
Không. Chữ ký chứng minh integrity/authenticity; nó không giảm nội dung được phép đọc.

**14. Tại sao Spring Security OidcUser có thể ảnh hưởng privacy ngay cả khi JPA chỉ lưu `sub`?**  
Vì SecurityContext/session serialization có thể giữ token/profile claims; cần review framework storage và IdP release.

**15. Khi email đổi, account link cần làm gì?**  
Giữ link theo immutable trusted subject nếu phù hợp, cập nhật email theo purpose và không dùng email làm foreign key.

**16. Consent có đồng nghĩa được lưu dữ liệu vô thời hạn?**  
Không. Cần mục đích, scope, nghĩa vụ và thời hạn áp dụng; xử lý withdrawal/deletion theo policy/lawful basis.

## 23. Nguồn tài liệu và tiêu chuẩn

- [NIST SP 800-63C-4 (2025) — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): data minimization, pairwise identifiers, derived attributes, provisioning/deprovisioning và privacy safeguards.
- [NIST CSRC — SP 800-63C-4 Final](https://csrc.nist.gov/pubs/sp/800/63/c/4/final): bản xuất bản chính thức tháng 7/2025.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, `sub`, claims, `profile/email/phone/address` scopes, `claims` parameter và pairwise subject/sector identifier.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, mapping authorities, claims processing.
- [Spring Security — SAML2 Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2AuthenticatedPrincipal`, `getAttribute`/`getFirstAttribute`.
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511): `SearchRequest.attributes`, `1.1`, `*` và attribute selection semantics.
- [RFC 7643 — SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643): attribute characteristics `returned`/`mutability`/`required`.
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): `attributes`/`excludedAttributes` parameters và partial resource representation.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh log tokens, session IDs và sensitive personal data.
- [OWASP — User Privacy Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html): privacy by design, minimizing data disclosure.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): bảo vệ dữ liệu được phép lưu, quản lý khóa và lưu trữ.

**Ghi nhớ:** Hệ thống federation tốt **không chuyển toàn bộ hồ sơ directory cho tất cả ứng dụng**. RP chỉ xin attribute phục vụ mục đích được duyệt; IdP **allowlist** ở nguồn; subject được namespace bởi issuer và ưu tiên pairwise/opaque khi giảm correlation; LDAP/SCIM chỉ trả fields cần thiết; Spring Security chỉ map dữ liệu tối thiểu cho account/roles/session; dữ liệu được lưu có TTL/retention/điều kiện xóa riêng, và logs/backups cũng phải nằm trong vòng đời đó. **Signed/encrypted token không tự bảo đảm privacy**, còn pseudonymous ID không mặc định anonymous.