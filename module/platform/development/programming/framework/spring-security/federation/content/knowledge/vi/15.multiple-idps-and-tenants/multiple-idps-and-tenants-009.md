# Giới hạn tính duy nhất của NameID và email giữa các IdP

**Module:** Spring Security – federation  
**Chủ đề cha:** Nhiều IdP và tenant  
**Công nghệ minh họa:** SAML 2.0 Web Browser SSO, Spring Boot 3.x, Spring Security 6.5, Java 17+.

## 1. Vì sao NameID hoặc email không tự là định danh toàn cục?

Giả sử một ứng dụng Service Provider (**SP**) kết nối với hai Identity Provider (**IdP**): một IdP của công ty và một IdP của nhà cung cấp. Mỗi IdP tự quản lý namespace định danh của người dùng mà nó xác thực. Vì thế:

| Nguồn | NameID | Email attribute | Chủ thể thực tế |
| --- | --- | --- | --- |
| IdP company | **employee-42** | alex@example.org | Nhân viên A |
| IdP partner | **employee-42** | alex@example.org | Nhà cung cấp B |
| IdP company sau khi thay nhân sự | **employee-88** | alex@example.org | Nhân viên C mới được cấp email |

Ba dòng **không phải một tài khoản** chỉ vì một số chuỗi trùng nhau. IdP company và partner có thể cùng phát NameID text giống nhau mà vẫn định danh **hai người khác nhau**. Email có thể được dùng làm alias, đổi theo tên, dùng chung hoặc tái cấp phát cho người mới.

Một SP nguy hiểm thường làm:

~~~text
SAML đã đăng nhập thành công
  -> lấy NameID hoặc email
  -> SELECT * FROM app_users WHERE email = ?
  -> đăng nhập với quyền của user tìm thấy
~~~

Nếu IdP partner phát email trùng tài khoản admin của company, SP có thể cho partner user tiếp quản local admin. Đây là **account confusion/account takeover** tại ranh giới federation. Chữ ký SAML hợp lệ chỉ chứng minh **IdP cụ thể đã phát assertion**, không chứng minh email hoặc NameID unique trên tất cả IdP.

**Nguyên tắc:** Phải định danh người dùng bằng một **federated identifier có namespace**, tối thiểu gồm **issuer đáng tin + stable subject trong scope được thỏa thuận**, bổ sung **SP scope, NameID Format/qualifiers và tenant boundary** khi liên quan. Sau đó liên kết tới **local user** đã được phê duyệt, cuối cùng mới kiểm tra **authorization**.

## 2. Ba lớp độc lập: xác thực, liên kết và phân quyền

| Lớp | Câu hỏi | Nguồn tin cậy |
| --- | --- | --- |
| **SAML Authentication** | Assertion này có thật sự do IdP đã tin cậy phát cho đúng SP và còn hiệu lực không? | Spring Security SAML provider + IdP metadata/verification certificate |
| **Federated account resolution** | Subject của đúng IdP này đã được liên kết với local user nào? | Identity-link registry/DB, chính sách provisioning và approval |
| **Authorization** | Local user này có quyền truy cập tài nguyên/hành động trong tenant hiện tại không? | DB grants, policy engine, trạng thái tài khoản/tenant |

Spring Security **Saml2Authentication** có thể báo đã authenticated nhưng local user chưa được liên kết hoặc đang bị disabled. Không tự cho một người truy cập dữ liệu nội bộ chỉ vì họ có một assertion hợp lệ của một IdP khác được SP tin cậy cho mục đích đăng nhập cơ bản.

Ví dụ logic:

~~~text
ALLOW read(document 42)
  = valid SAML authentication
  AND correct issuer + stable subject + scope
  AND exact approved account link
  AND local user enabled
  AND document belongs to authorized tenant
  AND local grant READ(document 42)
  AND no explicit deny
~~~

Đây là **deny by default** và **least privilege**: nếu thiếu link, trạng thái không rõ hoặc DB không trả được quyết định, không cấp quyền ngầm. Bản thân thuộc tính email không nằm trong biểu thức quyết định vì không phải primary authentication binding đã được phê duyệt.

## 3. Cấu trúc NameID trong SAML 2.0

Ví dụ một **mảnh XML minh họa**, chưa phải assertion có chữ ký:

~~~xml
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    NameQualifier="https://idp.company.example/saml"
    SPNameQualifier="https://portal.example.org/saml/sp">
  pairwise-company-user-847
</saml:NameID>
~~~

Phân biệt:

- **NameID value:** chuỗi bên trong phần tử, có thể opaque, email-like hoặc một mã khác. Không mặc định đây là email hoặc user ID duy nhất ngoài IdP.
- **Format:** nghĩa của giá trị, chẳng hạn persistent, transient, emailAddress, unspecified.
- **NameQualifier:** namespace/authority liên quan đến định danh theo quy tắc SAML và format; có thể không xuất hiện.
- **SPNameQualifier:** SP hoặc affiliation mà identifier được dành cho, đặc biệt có ý nghĩa đối với pairwise persistent identifiers.
- **Assertion Issuer:** IdP entityID phát assertion, được xác minh bằng trust policy của SP. Issuer và NameQualifier là **hai trường khác nhau**; không nhầm lẫn ngay cả khi chúng có cùng text.
- **SP entityID:** định danh SP mà assertion được cấp, phải khớp Audience/Recipient và cấu hình tin cậy.

**Không được** chỉ đọc phần text NameID rồi bỏ hết Format/qualifiers nếu contract định danh phụ thuộc vào các thuộc tính đó. Nhưng cũng không được dùng một giá trị Qualifier chưa xác minh để tự tạo trust; đầu tiên phải xác minh toàn bộ SAML Response/Assertion.

## 4. Bốn NameID Format thường gặp

| Format | Ngữ nghĩa | Có thích hợp làm khóa liên kết lâu dài? |
| --- | --- | --- |
| **persistent** | Identifier opaque ổn định theo quan hệ IdP–SP hoặc SP affiliation; thường pairwise | **Có thể**, nếu xác nhận uniqueness/lifecycle/qualifiers |
| **transient** | Identifier tạm, có thể thay đổi qua phiên | **Không**, nếu không có stable subject thay thế |
| **emailAddress** | Giá trị có định dạng địa chỉ email | **Không chỉ dựa vào format**; email không bảo đảm immutable hoặc global unique |
| **unspecified** | Ý nghĩa do các bên triển khai quy định | Chỉ khi có **contract rõ** về tính ổn định, scope và non-reassignment |

Một số format khác gồm WindowsDomainQualifiedName, X509SubjectName, Kerberos và entity. Chúng mang namespace/semantics riêng; không mặc định phù hợp làm human-account primary key.

### 4.1. Persistent không có nghĩa chung trên mọi SP

SAML cho phép IdP cấp **persistent pairwise identifiers** khác nhau cho cùng người tại những SP khác nhau. Ví dụ:

~~~text
IdP company / SP portal  / người A -> pairwise-p1
IdP company / SP reports / người A -> pairwise-r7

IdP partner / SP portal  / người B -> pairwise-p1
~~~

Không thể suy ra người A ở portal và reports giống nhau bằng cách so sánh value; cũng không thể suy ra người A và B tại portal là một chỉ vì pairwise-p1 trùng giữa hai IdP. Phạm vi **Issuer + SP/affiliation** là cốt yếu.

### 4.2. Transient không được ép thành tài khoản dài hạn

Nếu IdP phát NameID transient, user có thể nhận một value mới khi đăng nhập lại. Lưu transient vào bảng unique account link tạo nhiều tài khoản trùng người hoặc khiến người dùng “mất dữ liệu” sau mỗi login.

Giải pháp là yêu cầu IdP phát **stable subject attribute** có contract (ví dụ ID nội bộ never-reassigned) hoặc dùng quy trình linking an toàn. Không tự ghép dựa trên email để “chữa” transient ID.

### 4.3. EmailAddress không phải chứng thư ownership vĩnh viễn

SAML NameID Format emailAddress thể hiện dạng identifier, **không phải** bằng chứng rằng email đã được kiểm tra quyền sở hữu, không đổi và không tái cấp phát. Nếu IdP có thuộc tính emailVerified riêng, điều đó vẫn phải được xem trong **trust contract** và không tự chứng minh mọi tài khoản khác đang dùng email là cùng người.

### 4.4. Unspecified cần contract rõ

Một IdP có thể phát userPrincipalName, employeeNumber hoặc một chuỗi tên người dùng theo Format unspecified. SP chỉ dùng làm khóa nếu IdP và SP đã thống nhất bằng tài liệu **namespace, uniqueness, lifetime, reassignment, multi-tenant semantics và behavior khi migration**. Không suy diễn từ UI rằng value nhìn “có vẻ ID” là bất biến.

## 5. Các lý do email không an toàn để tự nối tài khoản giữa các IdP

### 5.1. Email giống nhau nhưng khác người

IdP partner có thể phát email của một địa chỉ liên hệ chung hoặc cùng text email của công ty. IdP partner có thẩm quyền xác thực người dùng của họ; họ không có thẩm quyền gán một người vào local admin account do IdP công ty quản lý.

### 5.2. Email thay đổi hoặc bị tái cấp phát

Một địa chỉ có thể đổi do kết hôn, đổi tên, chuyển domain, thay phòng ban; có thể là alias hoặc mailbox chung; có thể bị thu hồi rồi gán cho nhân viên khác. Nếu local account được tìm chỉ theo email, quyền của người cũ có thể rơi vào người mới.

### 5.3. Email chưa chắc verified hoặc authoritative

Tùy IdP, email có thể do admin nhập, người dùng tự khai hoặc đồng bộ từ nguồn khác. Không lấy dữ liệu đã có chữ ký SAML làm chứng minh email đã được verified nếu IdP không cam kết điều đó.

### 5.4. Chuẩn hóa email tùy tiện có thể làm trùng user

- Domain thường so khớp không phân biệt hoa thường theo DNS, cần xử lý IDN/punycode phù hợp.
- Local-part có thể có quy tắc xử lý khác nhau ở các mail provider; không tự lowercase mọi địa chỉ khi dùng làm identity key.
- Không tự xóa dấu chấm, dấu cộng, `+tag` hoặc alias vì quy tắc một nhà cung cấp không áp dụng mọi domain.
- Không dùng so sánh `LIKE`, substring hoặc “tên trước dấu @” để xác nhận cùng user.
- Unicode và IDN/homograph có thể làm dữ liệu nhìn giống nhưng khác byte/identity.

**Đối với opaque NameID, tuyệt đối không tùy tiện lowercase, trim hoặc bỏ dấu**. Value mang ngữ nghĩa theo IdP; thay đổi có thể đồng nhất nhầm hai subject khác nhau. Nếu cần chuẩn hóa, chuẩn hóa theo **contract và dữ liệu đã xác minh**, rồi lưu cả raw/canonical với audit.

## 6. Khóa federated có namespace: mức tối thiểu và mở rộng

### 6.1. Khóa nền tảng

Trong điều kiện IdP cung cấp stable subject có namespace rõ:

~~~text
FederatedIdentifier = (trustedIssuerEntityId, stableSubject)
~~~

Mô hình NIST SP 800-63C nhấn mạnh các IdP quản lý subject IDs độc lập và **các subject identifiers có thể trùng giữa IdP**, nên relying party không được xử lý subject mà thiếu issuer context.

Trong SAML persistent pairwise, scope SP có thể ảnh hưởng value. Trong ứng dụng đa tenant, identity link và authorization còn cần tenant boundary.

### 6.2. Khóa phòng thủ sâu

Một cấu trúc logic tham khảo:

~~~text
(tenantId,
 verifiedIssuerEntityId,
 spEntityIdOrAffiliation,
 nameIdFormat,
 nameQualifier,
 spNameQualifier,
 nameIdValue)
      -> localUserId
~~~

Tại sao có từng phần:

- **tenantId:** để không lẫn quyền giữa hai tổ chức/đối tác.
- **verifiedIssuerEntityId:** để company và partner không trùng namespace.
- **spEntityIdOrAffiliation:** để lưu đúng pairwise identity scope.
- **nameIdFormat:** để không coi một transient value giống một persistent value là cùng subject.
- **nameQualifier / spNameQualifier:** để bảo toàn thông tin namespace theo SAML/IdP contract.
- **nameIdValue:** nội dung identifier, giữ đúng semantics từ nguồn được xác minh.

Đây là mô hình khái niệm, không phải câu khẳng định một SP phải luôn lưu đúng bảy cột. Nếu IdP dùng stable employee ID attribute khác NameID, thay thông tin subject bằng một namespace/issuer/scoping tương đương và phải chứng minh thuộc tính ấy được đảm bảo unique/immutable trong phạm vi đã duyệt.

### 6.3. RegistrationId của Spring không phải Issuer

**registrationId** như company/partner là định danh **cục bộ của SP** cho một RelyingPartyRegistration. Nó cho Spring chọn metadata, certificates và endpoints, nhưng không nhất thiết là IdP issuer bất biến:

- Registration có thể bị đổi tên khi deploy.
- Một registration có thể được reconfigure tới issuer khác.
- Nhiều registrations có thể trỏ cùng issuer nhưng khác SP entityID/tenant.
- registrationId không tự chứa NameID Format hoặc qualifiers.

Chỉ sử dụng registrationId như **trusted lookup key** tới issuer/SP scope/tenant **được cấu hình server-side**; nếu cần lưu vào identity link, quản lý migration khi đổi tên. Không cho browser chỉ định issuer hoặc tenant tùy ý rồi coi đó là danh tính đã xác minh.

## 7. Hai assertion minh họa: cùng NameID text, hai người

Mảnh XML A (không có chữ ký, chỉ giải thích):

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Issuer>https://idp.company.example/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      SPNameQualifier="https://portal.example.org/saml/sp">
      same-opaque-id
    </saml:NameID>
  </saml:Subject>
</saml:Assertion>
~~~

Mảnh XML B:

~~~xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Issuer>https://idp.partner.example/saml</saml:Issuer>
  <saml:Subject>
    <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      SPNameQualifier="https://portal.example.org/saml/sp">
      same-opaque-id
    </saml:NameID>
  </saml:Subject>
</saml:Assertion>
~~~

**Kết quả:** khác issuer → khác federated key, dù NameID text giống nhau. Hai XML mẫu không phải tokens có thể đăng nhập. Với XML thật, Spring Security phải kiểm chứng signature, issuer, audience, recipient, time và SAML request correlation trước khi identity resolver sử dụng principal.

## 8. Sơ đồ account resolution an toàn

~~~text
Browser
  |
  | SAMLResponse
  v
Spring Security Saml2WebSsoAuthenticationFilter
  |
  | signature, trusted Issuer, Audience, Recipient, time, InResponseTo
  v
Saml2Authentication / Saml2AuthenticatedPrincipal
  |
  | trusted registration -> issuer, SP scope, tenant
  | stable subject + Format/qualifiers theo contract
  v
FederatedIdentityResolver
  |
  | exact lookup theo composite key
  v
FederatedIdentityLink DB
  +-- 0 link: deny / pending onboarding
  +-- 1 link: local account (nếu enabled)
  +-- conflict: deny và audit, cần admin review
  |
  v
Business authorization (tenant, role, resource grants)
  |
  v
Cho phép hoặc từ chối request
~~~

**Không lấy email làm fallback** khi exact link không tồn tại. Nếu muốn liên kết hai federated identities với một local account, phải có flow riêng có authentication, explicit consent/approval, audit và uniqueness constraints.

## 9. Schema PostgreSQL nhiều IdP/tenant

Schema tham khảo sau giữ identity key có issuer/tenant/SP scope/Format/qualifiers, tránh primary key bằng email:

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    display_email VARCHAR(320)
);

CREATE TABLE federated_identities (
    tenant_id VARCHAR(100) NOT NULL,
    issuer_entity_id VARCHAR(500) NOT NULL,
    sp_scope VARCHAR(500) NOT NULL,
    name_id_format VARCHAR(250) NOT NULL,
    name_qualifier VARCHAR(500) NOT NULL DEFAULT '',
    sp_name_qualifier VARCHAR(500) NOT NULL DEFAULT '',
    name_id_value VARCHAR(700) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (
        tenant_id, issuer_entity_id, sp_scope,
        name_id_format, name_qualifier,
        sp_name_qualifier, name_id_value
    )
);

CREATE TABLE document_permissions (
    tenant_id VARCHAR(100) NOT NULL,
    app_user_id BIGINT NOT NULL REFERENCES app_users(id),
    document_id BIGINT NOT NULL,
    can_read BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, app_user_id, document_id)
);
~~~

**Giới hạn schema minh họa:**

- `name_qualifier=''` đại diện cho qualifier **vắng mặt** theo contract đã chuẩn hóa; nếu IdP phân biệt absent với present-empty, cần cột hiện diện riêng hoặc canonical encoding không nhập nhằng.
- Foreign key app_user_id không tự chứng minh cùng tenant; ứng dụng thật nên thêm **composite foreign key** hoặc constraint/triggers để identity link không trỏ sang app_user tenant khác. Query ví dụ kiểm tra tenant tường minh.
- Document phải được ràng buộc tới tenant trong bảng dữ liệu thật; permission chỉ là một phần, không thay object-level tenant query.
- Quyền ghi bảng link phải chỉ dành cho flow account linking/provisioning được quản trị, có audit và transaction.
- Có thể thêm createdBy, approvedBy, revokedAt, nguồn cấp và migration history; không sửa/quên dấu vết khi đổi issuer.

### Seed dữ liệu cố ý trùng tên

~~~sql
INSERT INTO app_users (id, tenant_id, enabled, display_email)
VALUES
    (1001, 'company', TRUE, 'alex@example.org'),
    (2001, 'partner', TRUE, 'alex@example.org');

INSERT INTO federated_identities (
    tenant_id, issuer_entity_id, sp_scope,
    name_id_format, name_qualifier, sp_name_qualifier,
    name_id_value, registration_id, app_user_id
) VALUES
    ('company',
     'https://idp.company.example/saml',
     'https://portal.example.org/saml/sp',
     'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
     '',
     'https://portal.example.org/saml/sp',
     'same-opaque-id', 'company', 1001),
    ('partner',
     'https://idp.partner.example/saml',
     'https://portal.example.org/saml/sp',
     'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
     '',
     'https://portal.example.org/saml/sp',
     'same-opaque-id', 'partner', 2001);

INSERT INTO document_permissions (
    tenant_id, app_user_id, document_id, can_read
) VALUES
    ('company', 1001, 42, TRUE),
    ('partner', 2001, 42, FALSE);
~~~

Hai user có **email và NameID text trùng**, nhưng không trùng federated identity key. Company user có grant document 42, partner user không có. Không có lý do để partner kế thừa document permission của company.

## 10. Java 17 chạy độc lập: chứng minh khóa khác nhau

Ví dụ sau là chương trình **Java 17+ thực sự biên dịch/chạy được**, không phụ thuộc Spring hoặc IdP. Nó mô phỏng danh tính đã được một hệ thống xác thực đáng tin cung cấp; **không phải SAML signature validator**.

**Tệp: FederatedKeyDemo.java**

~~~java
import java.util.Map;

public final class FederatedKeyDemo {

    record Key(
        String tenant,
        String issuer,
        String spScope,
        String format,
        String nameIdValue) { }

    public static void main(String[] args) {
        String format =
            "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
        String sp = "https://portal.example.org/saml/sp";

        Key company = new Key(
            "company", "https://idp.company.example/saml",
            sp, format, "same-opaque-id");
        Key partner = new Key(
            "partner", "https://idp.partner.example/saml",
            sp, format, "same-opaque-id");
        Key transientKey = new Key(
            "company", "https://idp.company.example/saml",
            sp,
            "urn:oasis:names:tc:SAML:2.0:nameid-format:transient",
            "same-opaque-id");

        Map<Key, Long> links = Map.of(
            company, 1001L,
            partner, 2001L);

        String emailA = "alex@example.org";
        String emailB = "alex@example.org";

        System.out.println(
            "sameNameId=" + company.nameIdValue()
                .equals(partner.nameIdValue()));
        System.out.println(
            "sameEmail=" + emailA.equals(emailB));
        System.out.println(
            "sameFederatedKey=" + company.equals(partner));
        System.out.println("companyUser=" + links.get(company));
        System.out.println("partnerUser=" + links.get(partner));
        System.out.println(
            "transientLinked=" + links.containsKey(transientKey));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FederatedKeyDemo.java
java FederatedKeyDemo
~~~

**Stdout chính xác:**

~~~text
sameNameId=true
sameEmail=true
sameFederatedKey=false
companyUser=1001
partnerUser=2001
transientLinked=false
~~~

Java `record` so sánh các trường của key theo giá trị; tên/email trùng không đủ khi issuer/tenant khác nhau. `transientKey` khác Format nên không tự khớp link persistent. Chương trình rút gọn chưa mô hình hóa qualifiers/uniqueness constraints/transaction; production cần đầy đủ namespace theo contract và SAML validation trước lookup.

## 11. Spring Security 6.5: đọc principal đúng cách

Sau khi Spring Security xác minh SAMLResponse, `Saml2Authentication` có principal thường là `Saml2AuthenticatedPrincipal`. Trong Spring Security **6.5**:

~~~java
if (authentication instanceof Saml2Authentication saml
        && saml.getPrincipal() instanceof
            Saml2AuthenticatedPrincipal principal) {

    String registrationId =
        principal.getRelyingPartyRegistrationId();
    String nameId = principal.getName();

    // Chỉ lookup theo registration -> verified issuer/SP scope
    // và một stable subject được contract bảo đảm.
}
~~~

Đây là snippet trong một method Java, không phải class độc lập; cần imports Authentication, Saml2Authentication, Saml2AuthenticatedPrincipal từ Spring Security.

**API có giới hạn quan trọng:** `principal.getName()` không tự mang toàn bộ NameID Format, NameQualifier và SPNameQualifier trong một String. `getRelyingPartyRegistrationId()` trả khóa registration cục bộ, không phải trực tiếp Issuer từ SAML.

Vì vậy, **registrationId + principal.getName()** chỉ là **identity lookup tiện lợi dưới một contract chặt**, không tự là composite SAML identity đã được kiểm tra đủ. Với production cần adapter/policy sau khi xác minh assertion để kiểm tra NameID Format/qualifiers hoặc dùng stable subject attribute khác được IdP phát đúng contract.

**Chú ý phiên bản:** Các API của principal trong Spring Security **7.x** có deprecation/định hướng thay thế; code này chủ đích theo **6.5**, cần xem tài liệu đúng phiên bản khi nâng cấp.

## 12. Spring Boot 3 + Java 17: hai registrations, một chính sách local grant

Ví dụ kết hợp **SAML2 authentication** với một **DB authorization policy** để không chỉ dựa vào email. Cần project Maven Spring Boot 3.x tương thích Spring Security 6.x, hai IdP thật với metadata và SP registrations, PostgreSQL đã tạo bảng/mẫu seed, và Java 17+.

**Giới hạn bảo mật của ví dụ:** Policy bên dưới giả định hai IdP đã được quản trị xác nhận **chỉ phát persistent NameID** theo **SPNameQualifier=SP scope** và **NameQualifier absent** như seed dữ liệu. Đoạn code không parse SAML XML để tự xác minh Format/qualifiers; điều đó cần được thực thi bằng **SAML identity adapter/validation contract** trước khi áp dụng vào production. Không dùng đoạn mã để liên kết user nếu IdP đang phát transient, unspecified hoặc emailAddress NameID ngoài contract.

### 12.1. Dependencies

Trong phần dependencies của pom.xml dùng Spring Boot parent/BOM tương thích:

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

Không trộn OpenSAML version ngoài dải Spring Security/Boot quản lý.

### 12.2. application.yml

**src/main/resources/application.yml**

~~~yaml
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

DB credentials lấy từ secret manager/biến môi trường. Ứng dụng phải có migration schema/seed phù hợp; YAML không tự tạo bảng federated identities.

### 12.3. Main class

**src/main/java/com/example/fed/FederationApplication.java**

~~~java
package com.example.fed;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }
}
~~~

### 12.4. SecurityConfig: định nghĩa hai trust relationships

**src/main/java/com/example/fed/SamlSecurityConfig.java**

~~~java
package com.example.fed;

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
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(
                    "classpath:metadata/company-idp.xml")
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        RelyingPartyRegistration partner =
            RelyingPartyRegistrations
                .fromMetadataLocation(
                    "classpath:metadata/partner-idp.xml")
                .registrationId("partner")
                .entityId("https://portal.example.org/saml/sp")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/partner")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(
            company, partner);
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

- Cả company và partner có metadata/verification credentials **riêng**. Một assertion ký bởi partner không thể được chấp nhận như company nếu issuer/registration validation đúng.
- SP entityID có thể giống nhau nếu cùng một SP logic, nhưng persistent NameID pairwise có thể phụ thuộc entityID/affiliation theo contract.
- Metadata ở classpath phải là tài liệu IdP thật; các tên miền example.org chỉ minh họa và không tự cung cấp SSO.
- **@EnableMethodSecurity** cho phép xử lý @PreAuthorize ở controller/service.
- Với nhiều IdP, có thể cần cho user chọn login tại **/saml2/authenticate/company** hoặc partner; chọn registration phải bị ràng buộc vào metadata/trust server-side.
- Nếu app có các endpoint khác chứa dữ liệu nhạy cảm, phải áp identity link/tenant authorization ở cả những endpoint ấy; ví dụ chỉ bảo vệ resource cụ thể.

### 12.5. DocumentPolicy: tra composite key thay vì email

**src/main/java/com/example/fed/DocumentPolicy.java**

~~~java
package com.example.fed;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component("documentPolicy")
public class DocumentPolicy {

    private record Source(
        String tenant, String issuer, String spScope) { }

    private static final Map<String, Source> SOURCES =
        Map.of(
            "company", new Source(
                "company", "https://idp.company.example/saml",
                "https://portal.example.org/saml/sp"),
            "partner", new Source(
                "partner", "https://idp.partner.example/saml",
                "https://portal.example.org/saml/sp"));

    private final JdbcTemplate jdbc;

    public DocumentPolicy(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public boolean canRead(
            Authentication authentication, long documentId) {
        if (!(authentication instanceof Saml2Authentication saml)
                || !saml.isAuthenticated()) {
            return false;
        }
        if (!(saml.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }

        String registrationId =
            principal.getRelyingPartyRegistrationId();
        Source source = SOURCES.get(registrationId);
        String nameId = principal.getName();

        if (source == null || nameId == null || nameId.isBlank()) {
            return false;
        }

        String sql = """
            SELECT COUNT(*)
              FROM federated_identities fi
              JOIN app_users u
                ON u.id = fi.app_user_id
               AND u.tenant_id = fi.tenant_id
              JOIN document_permissions dp
                ON dp.app_user_id = fi.app_user_id
               AND dp.tenant_id = fi.tenant_id
             WHERE fi.tenant_id = ?
               AND fi.issuer_entity_id = ?
               AND fi.sp_scope = ?
               AND fi.registration_id = ?
               AND fi.name_id_format = ?
               AND fi.name_qualifier = ''
               AND fi.sp_name_qualifier = ?
               AND fi.name_id_value = ?
               AND u.enabled = TRUE
               AND dp.document_id = ?
               AND dp.can_read = TRUE
            """;

        Long count = jdbc.queryForObject(
            sql, Long.class,
            source.tenant(),
            source.issuer(),
            source.spScope(),
            registrationId,
            "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
            source.spScope(),
            nameId,
            documentId);

        return count != null && count == 1;
    }
}
~~~

**Cần hiểu giới hạn an ninh của code:**

1. **SOURCES** lấy issuer/tenant/SP scope từ trusted registration server-side, không lấy tenant từ query/header hay email.
2. **SAML AuthenticationProvider** phải đã xác minh assertion trước khi principal được dùng.
3. Query cố ý dùng exact issuer, tenant, SP scope, Format và qualifiers theo contract, nhưng **principal.getName() không tự chứng minh XML NameID Format/qualifiers đúng**. Cần một adapter/validator đáng tin kiểm tra NameID XML fields hoặc dùng stable subject khác theo contract, nếu không có nguy cơ **format confusion** khi raw value trùng.
4. **JOIN** user và permission buộc cùng tenant; quyền document thực tế còn cần object-level tenant query, không chỉ permission row.
5. **Prepared parameter binding** của JdbcTemplate chống SQL injection, không nối NameID vào SQL.
6. Khi DB lỗi, method không được fallback allow; hãy trả lỗi an toàn và giám sát thay vì cho user vào.
7. Truy vấn **count==1** là phòng thủ chống dữ liệu mơ hồ; unique constraints và account linking flow phải giữ mỗi external identity có một local owner.
8. Với thao tác ghi nhạy cảm, tránh **TOCTOU** bằng kiểm tra grant/tài nguyên trong transaction hoặc conditional UPDATE được tenant-scoped.

### 12.6. Controller bảo vệ tài nguyên

**src/main/java/com/example/fed/DocumentController.java**

~~~java
package com.example.fed;

import java.util.Map;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    @GetMapping("/")
    public String home() {
        return "Federated identity example";
    }

    @GetMapping("/documents/{documentId}")
    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #documentId)")
    public Map<String, Object> readDocument(
            @P("documentId")
            @PathVariable("documentId") long documentId) {

        return Map.of(
            "documentId", documentId,
            "authorization", "passed");
    }
}
~~~

Controller trả dữ liệu giả sau khi policy cho phép, không truy xuất document thật. Trong hệ thống thực, **business service/DB query** phải kiểm tra tenant và grant cùng việc lấy dữ liệu, không chỉ dựa vào một controller hoặc ẩn nút trên UI.

### 12.7. Chạy và kiểm thử tích hợp

Trong dự án Maven đầy đủ với Java 17+, PostgreSQL, schema, IdP metadata và SP registration thật:

~~~bash
mvn spring-boot:run
~~~

Nếu ứng dụng khởi động được, endpoint công khai:

~~~bash
curl -i http://localhost:8080/
~~~

Body từ controller:

~~~text
Federated identity example
~~~

Sau khi login SAML thật, dựa trên seed data và identity contract:

| Authenticated identity | Local user | DB quyền READ document 42 | Kỳ vọng |
| --- | --- | --- | --- |
| company + same-opaque-id | 1001 | TRUE | **200** |
| partner + same-opaque-id | 2001 | FALSE | **403** |
| company + unknown NameID | Không link | Không | **403** |
| company + linked user disabled | 1001 bị khóa | TRUE | **403** |
| Issuer không được phê duyệt | Không qua SAML validation | Bất kỳ | Không được truy cập |
| DB lỗi | Chưa có quyết định đáng tin | Không rõ | Không trả **200** |

Đây là **hành vi dự kiến**, không tuyên bố đã thử với IdP thật. Nếu IdP phát NameID transient/unspecified, phải test policy/adapter Format; code minh họa một mình **không phải bằng chứng format đã được xác minh**.

## 13. Khi muốn liên kết hai IdP vào cùng một local account

Một local user có thể hợp pháp sử dụng IdP company và liên doanh. Tuy nhiên **email trùng không phải giấy phép tự động gộp**. Một quy trình account linking an toàn gồm:

1. User đăng nhập vào **local account hiện hữu** qua một federated identity đã được tin.
2. Xác nhận phiên hiện hành có độ mới đủ (fresh authentication); với quyền cao, dùng reauthentication hoặc step-up phù hợp.
3. User **chủ động khởi tạo linking** IdP thứ hai đã được phép; SP ghi state/correlation có CSRF protection và thời hạn.
4. Browser xác thực tại IdP thứ hai; SP kiểm tra signature, issuer, audience, recipient, time, InResponseTo theo SAML profile.
5. Xây external identity key **đầy đủ** từ issuer + stable subject + scope/format/qualifiers đã được xác minh.
6. Kiểm tra external key **chưa liên kết với local account khác**. Nếu đã có, không overwrite theo yêu cầu từ browser.
7. User xác nhận hoặc admin phê duyệt khi policy yêu cầu; chống user enumeration và không lộ tài khoản của người khác.
8. Ghi link **atomic transaction** theo unique constraint, audit actor, tenant, issuer, approval, timestamp.
9. Không nâng role nội bộ tự động vì có thêm IdP; authorization policy vẫn là nguồn quyết định quyền.
10. Có cơ chế unlink/recovery, không cho người dùng tùy tiện xóa mọi phương thức đăng nhập hoặc di chuyển tài khoản admin sang IdP không được phê duyệt.

NIST federation guidance coi account linking là hành động cần **authenticated session**, không đơn thuần là so sánh email. Có thể sử dụng email để đưa ra tín hiệu **gợi ý liên hệ** trong UX, nhưng không để nó quyết định account ownership.

## 14. JIT provisioning và nguy cơ account takeover

Một chính sách sai:

~~~text
if (emailExistsInLocalDatabase(samlEmail)) {
    signInAsExistingLocalAccount();
} else {
    createLocalAccount();
}
~~~

IdP khác có thể đưa cùng email nhưng không đại diện đúng người được cấp quyền trong local DB. Chữ ký assertion vẫn hợp lệ cho IdP ấy, nên tấn công xảy ra ở **account resolution**, không ở signature validation.

**Chính sách thay thế:**

- Có **exact federated identity link** → xác định local user đã được phê duyệt.
- Chưa có link → tạo **pending account/no-rights** hoặc yêu cầu provisioning admin/HR system; không auto-match email.
- Email trùng tài khoản có quyền → không tự liên kết; chuyển sang linking flow xác minh cả hai bên.
- Link mơ hồ/conflict → deny và báo audit.
- Có thể dùng SCIM/HR provisioning để tạo link từ nguồn quản trị đáng tin, nhưng phải xác định key/lifecycle.
- Local account disabled → không được cấp quyền dù IdP login thành công.

## 15. Migration: issuer, SP scope, tenant và email thay đổi

### IdP đổi issuer/entityID

Khi công ty chuyển IdP, issuer có thể đổi từ một entityID cũ sang mới. **Không tự map subject cũ sang issuer mới chỉ vì NameID/email trùng**. Cần metadata trust mới, nguồn mapping có thẩm quyền, migration script có phê duyệt, audit, giai đoạn chạy song song và kiểm thử user lifecycle trước khi tắt IdP cũ.

### SP đổi entityID

Nếu dùng **persistent pairwise NameID**, đổi SP entityID có thể khiến IdP phát một identifier khác cho cùng người. Phải lập kế hoạch transition/alias mapping, không dùng email làm cầu nối duy nhất. NameQualifier/SPNameQualifier cũng cần được kiểm tra.

### Email đổi hoặc được cấp lại

Nếu giữ federated identifier ổn định, đổi email **không làm đổi local user**; chỉ cập nhật thuộc tính liên lạc. Nếu email cũ được gán cho người khác, external link của người cũ không được tự chuyển sang người mới.

### Tách/nhập tenant

Một subject được cấp quyền ở tenant A không tự mang quyền sang B. Tenant migration và authorization migration là hai quyết định khác nhau, cần làm rõ quyền, dữ liệu, audit và người phê duyệt.

### Đổi NameID Format hoặc transient ID

Nếu IdP bất ngờ đổi persistent thành transient/unspecified, **không nhận value mới như một stable identity đã linked**. Dừng hoặc đưa vào quy trình migration có xác minh, xử lý phiên hiện có và truyền thông vận hành.

## 16. Kiểm thử âm cho multi-IdP account linking

Dùng test IdP phát assertion **được ký hợp lệ** cho từng tình huống. Chỉ tự sửa XML đã ký rồi thấy signature failure chưa chứng minh account-linking policy đã bảo vệ đúng.

| Tình huống | Kết quả đúng |
| --- | --- |
| Hai IdP phát cùng NameID value | Hai federated identities khác nhau |
| Hai IdP phát cùng email | Không auto-link local users |
| IdP partner phát email của company admin | Không truy cập được company admin |
| Cùng IdP, NameID persistent theo hai SP scopes | Không tự coi identifier cùng key |
| NameID transient được gửi để tạo long-term link | Deny hoặc yêu cầu stable subject contract |
| NameID emailAddress trùng account cũ | Không tự tạo link |
| Format đổi nhưng value giữ nguyên | Kiểm tra policy, không silent merge |
| NameQualifier hoặc SPNameQualifier đổi | Không bỏ khác biệt namespace nếu contract có ý nghĩa |
| IdP issuer đổi | Migration phải được phê duyệt |
| RegistrationId đổi tên | Cần mapping/migration server-side có audit |
| Email đổi nhưng persistent NameID giữ nguyên | Giữ đúng local link, cập nhật display email riêng |
| Email tái cấp cho nhân viên mới | Không kế thừa local grants |
| Cùng subject text ở hai tenant | Không xuyên tenant boundary |
| Request có tenantId/issuer trong query | Không cho client chọn namespace identity |
| Local link không có | Deny/pending, không fallback email |
| External key liên kết tới local account khác | Conflict/deny, không overwrite |
| Local account disabled | Không business access |
| SAML issuer/signature/audience sai | Bị từ chối trước account resolution |
| Opaque NameID khác chữ hoa/thường | Không normalize bừa |
| Email có dấu chấm hoặc +alias | Không áp provider-specific normalization chung |
| Document cùng ID nhưng tenant khác | Deny vì tenant/resource scope |
| DB lỗi lúc tra identity link | Fail closed, không fallback allow |
| Hai linking requests đồng thời cho cùng external key | Unique/transaction ngăn liên kết đôi |
| IdP group bị thu hồi khi SP session còn sống | Áp revoke/refresh/session policy theo SLA |

### Câu hỏi ôn tập

**1. Cùng NameID text ở company và partner có nghĩa cùng người không?**  
Không. Issuer và scope là một phần của federated identifier.

**2. Format=emailAddress có chứng minh email đã được verified và không tái cấp không?**  
Không. Format mô tả kiểu identifier; provenance, verification, lifecycle cần contract riêng.

**3. Vì sao persistent NameID của một người có thể khác giữa hai SP?**  
Vì nó có thể được IdP cấp theo pairwise SP/affiliation scope để bảo vệ quyền riêng tư.

**4. Chỉ có principal.getName() đã đủ làm composite key không?**  
Không. Cần ràng buộc verified issuer, SP/tenant scope và NameID semantics; code phải kiểm tra format/qualifiers theo contract.

**5. Nếu email người dùng đổi nhưng persistent NameID giữ, có cần tạo local user mới không?**  
Không, nếu đã có exact federated link và identity lifecycle không bị thay đổi.

**6. Nếu muốn cùng user truy cập qua hai IdP, có nên auto-link bằng email không?**  
Không. Cần authenticated session, xác thực IdP mới, approval/confirmation, unique constraint và audit.

## 17. Checklist production

- [ ] SAMLResponse được xác minh đầy đủ bằng trusted metadata/certificate: signature, issuer, audience, recipient, time, InResponseTo.
- [ ] IdP contract xác định **NameID Format, qualifiers, stable subject, uniqueness scope và non-reassignment**.
- [ ] Không dùng **email** hoặc một NameID raw làm primary key toàn cục.
- [ ] Federated key có **verified issuer + subject** và SP/tenant scope khi cần.
- [ ] Không tự lowercase/trim opaque NameID, hoặc chuẩn hóa email theo quy tắc một provider khác.
- [ ] RelyingPartyRegistration/registrationId được ánh xạ server-side tới issuer/SP/tenant đáng tin.
- [ ] Không auto-link account chỉ vì email trùng; JIT onboarding mặc định pending/no-rights.
- [ ] Account linking yêu cầu authenticated session và kiểm chứng IdP mới, approval/audit theo policy.
- [ ] Một federated key chỉ có một local owner theo constraint/transaction; conflict được từ chối.
- [ ] Local roles, tenant và resource grants được kiểm tra sau khi xác định đúng user.
- [ ] Khi issuer, SP entityID, NameID Format hoặc tenant đổi, có migration plan được phê duyệt.
- [ ] Tài khoản bị disable hoặc role bị revoked phải bị chặn theo yêu cầu thời gian thu hồi.
- [ ] Mọi business endpoint/service có account-linking và object-level authorization; không dựa vào UI-only check.
- [ ] SQL dùng bind parameters, giới hạn quyền DB, audit và fail-closed khi DB outage.
- [ ] Test collision NameID/email, wrong issuer/tenant, transient/format confusion, qualifier, account linking races, revoke.
- [ ] Không ghi SAMLResponse, NameID/PII không cần thiết, cookie/session ID, private keys vào log.
- [ ] Khi nâng Spring Security 6 lên 7, xem lại principal API và verified identity adapter theo tài liệu phiên bản.

**Kết luận:** NameID định danh subject **trong namespace và scope của bên phát hành SAML**; email là thuộc tính có thể thay đổi, tái cấp hoặc do nhiều nguồn cùng phát. Không trường nào tự bảo đảm **global uniqueness giữa các IdP**. Để tránh gộp nhầm tài khoản và chiếm quyền, dùng **trusted issuer + stable subject + SP/tenant scope thích hợp**, exact account linking có kiểm chứng, rồi phân quyền nghiệp vụ độc lập.

## 18. Tài liệu tham khảo

- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID, Format, NameQualifier/SPNameQualifier và các NameID formats.
- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): persistent/transient NameID và pairwise identifiers theo SP.
- [NIST SP 800-63C-4 – Federation](https://pages.nist.gov/800-63-4/sp800-63c/Federation/): issuer + subject identity, account linking, privacy.
- [Spring Security 6.5 – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): RelyingPartyRegistration và SAML authentication.
- [Spring Security 6.5 – Saml2AuthenticatedPrincipal API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html): getName, getRelyingPartyRegistrationId, getAttribute.
- [Spring Security 6.5 – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html): SAML Response validators/attribute conversion.
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): @EnableMethodSecurity, @PreAuthorize.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và resource-level permissions.
