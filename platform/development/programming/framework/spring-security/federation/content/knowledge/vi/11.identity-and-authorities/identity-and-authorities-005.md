# Chuẩn hóa tên, email và nhóm từ các IdP khác nhau

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Danh tính và quyền. Bài này xây dựng một mô hình thống nhất để chuyển dữ liệu danh tính từ nhiều OpenID Provider (OIDC), SAML Identity Provider (IdP) và các nguồn liên kết khác thành **hồ sơ người dùng nội bộ** và **quyền ứng dụng** mà không đánh đồng tên/email/nhóm ở các hệ thống độc lập.

## 1. Bài toán và nguyên tắc quan trọng nhất

Một doanh nghiệp có thể kết nối ứng dụng Spring với nhiều nhà cung cấp danh tính: IdP nhân viên, IdP đối tác, Azure/Entra ID, Keycloak, Okta hoặc một hệ thống SAML cũ. Cùng một người dùng có thể nhận các dữ liệu như:

```text
OIDC IdP A:
  iss             = https://login-a.example.org/realms/staff
  sub             = user-8f9
  name            = "Nguyễn Thị Lan"
  email           = "Lan@Example.ORG"
  email_verified  = true
  groups          = ["finance-read", "project-x"]

OIDC IdP B:
  iss             = https://accounts-b.example.net
  sub             = "person-1007"
  preferred_username = "lan.nguyen"
  given_name      = "Lan"
  family_name     = "Nguyễn"
  email           = "lan@example.org"
  email_verified  = false
  roles           = ["Accounting.View"]

SAML IdP C:
  IdP entityID    = https://sso.partner.example.edu/issuer
  NameID          = "u-7481"
  NameID Format   = persistent
  Attributes:
    displayName   = ["Nguyễn Thị Lan"]
    mail          = ["lan@example.org"]
    memberOf      = ["CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu"]
```

Các trường trên **không cho phép kết luận ba lần đăng nhập là một người duy nhất**, dù tên và email nhìn giống nhau. Mỗi IdP có quy tắc phát hành định danh, quản lý email, cập nhật nhóm và vòng đời tài khoản riêng. Nếu ứng dụng nối tài khoản theo email hoặc tin mọi nhóm có tên `admin`, kẻ tấn công có thể chiếm tài khoản hoặc nâng quyền thông qua một IdP có mức bảo đảm thấp hơn.

**Hệ thống chuẩn hóa phải tách bốn khái niệm:**

1. **Nguồn danh tính đã được xác minh:** Issuer, tenant, giao thức, chứng thư/khóa tin cậy và registration đang hoạt động.
2. **Khóa định danh bất biến trong phạm vi nguồn:** OIDC `iss + sub`; SAML NameID/định danh ổn định theo hợp đồng; không dùng email làm primary key.
3. **Thuộc tính hồ sơ hiển thị/liên lạc:** Tên, given/family name, email, trạng thái email đã xác minh, locale. Có thể đổi theo thời gian.
4. **Quyền ứng dụng nội bộ:** Permission/role mà ứng dụng quyết định sau khi **ánh xạ có kiểm soát** từ nhóm/role bên ngoài và kiểm tra quyền nghiệp vụ.

Kết quả mong muốn: một bản ghi `CanonicalIdentity` có định danh ổn định, provenance của từng trường, hồ sơ hiển thị an toàn, và **tập quyền ít nhất cần thiết**. Dữ liệu ngoài hợp đồng bị bỏ qua hoặc từ chối, không được tự động trở thành thẩm quyền.

## 2. Vì sao phải quản lý “nguồn” trước khi chuẩn hóa dữ liệu?

### 2.1. Mọi claim phải có ngữ cảnh

Với **OIDC**, ứng dụng Relying Party (RP) kiểm tra ID Token: chữ ký của OP, `iss`, `aud`, thời hạn và những kiểm tra `nonce`/flow cần thiết. Theo OIDC Core, chỉ cặp `iss + sub` có bảo đảm định danh ổn định trong phạm vi issuer; `name`, `preferred_username`, `email` không có cam kết duy nhất hoặc không tái cấp phát.

Với **SAML 2.0 Web SSO**, Service Provider (SP) kiểm tra SAMLResponse/Assertion, nguồn IdP, chữ ký, `AudienceRestriction`, `Recipient`, `Destination`, thời gian và replay. Sau khi xác minh, `Saml2AuthenticatedPrincipal` cho phép đọc NameID và các attributes đã xử lý. Tuy nhiên, **NameID không tự động là khóa vĩnh viễn**: `transient` là tạm thời; `persistent` được thiết kế ổn định theo liên kết nhưng phụ thuộc chính sách IdP; `emailAddress` không phải định danh bất biến.

Với CAS hoặc identity broker, tên principal/attributes cũng chỉ được dùng sau khi ticket hoặc bản khẳng định từ **server được tin** đã được xác minh. Khi broker chuyển đổi SAML thành OIDC, phải phân biệt **issuer thực sự của token downstream là broker** với danh tính upstream mà broker khai báo; không cho một claim `upstream_issuer` do client tự gửi quyết định tin cậy.

**Đầu vào đã qua xác thực vẫn có thể có claim không đủ tin cậy để cấp quyền.** Chữ ký hợp lệ chứng minh IdP đã phát một claim; nó không chứng minh rằng mọi claim đều có mức đảm bảo, độ mới và ý nghĩa giống nhau giữa các nhà cung cấp.

### 2.2. Định danh nguồn nên được cấu hình, không suy đoán từ input

Mỗi kết nối cần bản ghi cấu hình:

| Trường | Ví dụ | Quy tắc |
| --- | --- | --- |
| `providerKey` | `staff-a`, `partner-b` | Khóa cấu hình do hệ thống quản lý, không phải input tự chọn |
| `protocol` | `OIDC` hoặc `SAML2` | Chọn cơ chế validation đúng |
| `issuer` / IdP entityID | `https://login-a.example.org/realms/staff` | Khớp chính xác nguồn đã đăng ký |
| `registrationId` | `staff-a` | Liên kết Spring registration với chính sách IdP |
| `tenant` / realm | `staff` | Giới hạn tenant có quyền cấp thuộc tính nào |
| `subjectSource` | `sub` hoặc NameID persistent/employee ID được phê duyệt | Không dùng email/username tùy tiện |
| `displayNameClaim` | `name` hoặc SAML OID `displayName` | Chỉ dùng để hiển thị |
| `emailClaim` và tình trạng verification | `email` + `email_verified` hoặc quy trình xác minh ngoài | Không được dùng để nối tài khoản tự động |
| `groupClaim` / attribute | `groups`, `roles`, SAML `memberOf` | Đúng schema và đường dẫn đã thỏa thuận |
| `groupMappingVersion` | `v3` | Audit thay đổi chính sách quyền |

Không nhận token từ mọi issuer chỉ vì cấu trúc JWT giống nhau. Nếu dùng nhiều IdP, resolve đúng registration đã phê duyệt rồi kiểm tra bằng khóa tin cậy **của issuer tương ứng**, thay vì tin `iss`/`kid`/`jku` do token chưa xác thực tự khai và tải khóa theo URL tùy ý.

## 3. Thiết kế hồ sơ chuẩn hóa: định danh, liên hệ và quyền là ba vùng khác nhau

Một schema nội bộ phù hợp:

```text
CanonicalIdentity
  localAccountId: UUID (do ứng dụng cấp, không lấy từ email)
  externalIdentifiers[]:
    - providerKey: "staff-a"
      issuer: "https://login-a.example.org/realms/staff"
      subject: "user-8f9"
      protocol: "OIDC"
      tenant: "staff"
      verifiedAt: ...
      linkStatus: VERIFIED
  profile:
    displayName: "Nguyễn Thị Lan"
    givenName: "Lan"
    familyName: "Nguyễn"
    emailDisplay: "Lan@example.org"
    emailVerifiedBy: "staff-a"
    emailVerificationAt: ... (nếu hệ thống cung cấp)
    locale: "vi-VN"
  entitlements:
    - REPORT_READ
    - PROJECT_X_VIEW
  audit:
    mappingVersion: "v3"
    lastIdentitySync: ...
    attributeSources: ...
```

**Chỉ `localAccountId`** dùng làm khóa nội bộ của dữ liệu nghiệp vụ. `externalIdentifiers` có unique constraint theo nguồn và định danh, chẳng hạn `(provider_key, issuer, subject, tenant/qualifiers nếu thuộc mô hình)`. Trong OIDC, cặp chuẩn giao thức là `iss + sub`; việc lưu thêm providerKey/tenant giúp ràng buộc cấu hình vận hành, chứ không được làm mất ý nghĩa của cặp này. Trong SAML, cần lưu đủ NameID Format, NameQualifier, SPNameQualifier hoặc attribute bất biến đã thỏa thuận nếu chúng ảnh hưởng tính duy nhất/ổn định.

**Một người có thể có nhiều external identifiers**, nhưng việc liên kết chúng vào một `localAccountId` phải là **quy trình liên kết tài khoản có bằng chứng và xác thực phù hợp**, không phải join hai hàng có email trùng.

Tách từng nguồn của dữ liệu theo chính sách:

- `displayName` dùng cho giao diện; hiển thị an toàn và có fallback.
- `emailDisplay` dùng cho liên hệ chỉ khi được phép; email không phải quyền truy cập.
- `roles/permissions` do **policy của ứng dụng** quyết định; không tự nhận bất kỳ claim nào có tên `roles` thành `ROLE_ADMIN`.
- `accountStatus`/`disabled` có thể đến từ HR/SCIM/directory nguồn sự thật khác, không tự suy từ việc claim bị thiếu trong một lần login.
- `userId` của IdP không phải lúc nào cũng giống `sub`; phân biệt giá trị trong API quản trị của IdP với định danh đã xuất bản cho RP.

## 4. Chuẩn hóa tên người: giữ nguyên danh tính văn hóa và không dùng tên để nhận diện

### 4.1. Các trường thường gặp

OIDC cung cấp các claim chuẩn như `name`, `given_name`, `family_name`, `middle_name`, `nickname`, `preferred_username`, `locale`. Chúng có thể vắng mặt. Không bắt buộc IdP A và IdP B cùng cấp đầy đủ; nếu ứng dụng yêu cầu tên hiển thị, cần chọn thứ tự ưu tiên theo nguồn.

Trong SAML, tên attribute thường dùng có thể là:

| Ý nghĩa | SAML Attribute Name hay gặp | Ghi chú |
| --- | --- | --- |
| Display name | `urn:oid:2.16.840.1.113730.3.1.241` hoặc `displayName` | Hai dạng là quy ước trong triển khai, **không phải mọi IdP đều phát** |
| Given name | `urn:oid:2.5.4.42` | Cần metadata/attribute contract đúng |
| Surname | `urn:oid:2.5.4.4` | Không mặc định thứ tự hiển thị cho mọi quốc gia |
| Email | `urn:oid:0.9.2342.19200300.100.1.3` hoặc `mail` | Chưa tự chứng minh email verified |
| Group membership | `memberOf`, OID/URI hoặc tên riêng do đối tác khai báo | Có thể là DN, GUID hoặc danh sách |

IdP có thể phát Attribute `Name` là URN và `FriendlyName` chỉ để người đọc. SP nên map theo **Attribute Name/NameFormat đã thỏa thuận** thay vì chỉ tin FriendlyName vì FriendlyName có thể không duy nhất hoặc thay đổi.

### 4.2. Quy tắc thực tế

1. Chỉ đọc claim danh tính sau khi SAML/OIDC validation thành công.
2. Quy định thứ tự ưu tiên theo IdP: ví dụ `name` đáng tin khi có, nếu không thì ghép `given_name` và `family_name` theo quy tắc locale/sản phẩm. Với tiếng Việt, nhiều người dùng thích hiển thị **họ – tên đệm – tên**; không cố đảo máy móc dựa trên “first/last name” tiếng Anh.
3. Chuẩn hóa Unicode **NFC** cho mục đích hiển thị/tìm kiếm nhất quán; giữ nguyên dấu tiếng Việt và khoảng trắng hợp lệ. Tránh `NFKC` toàn diện nếu nó làm thay đổi ý nghĩa ký tự không mong muốn.
4. Bỏ khoảng trắng đầu/cuối và kiểm soát độ dài/dữ liệu điều khiển trong giao diện. **Không tự xóa diacritics** như `Nguyễn` thành `Nguyen` làm hồ sơ chuẩn.
5. Không dùng `name`, `displayName`, `preferred_username` hoặc cặp họ/tên để tìm/merge account. Tên dễ trùng và có thể đổi.
6. Tránh log PII/attributes không cần thiết. Với giao diện HTML, luôn encode output/chặn injection theo framework; normalization chuỗi **không thay thế** HTML escaping.
7. Nếu thiếu tên, dùng nhãn trung tính như “Người dùng” hoặc định danh nội bộ không nhạy cảm; không tự hiển thị email hay `sub` nếu chính sách quyền riêng tư không cho phép.

**Ví dụ phân biệt:** `"Nguyễn"` có thể được biểu diễn bằng các mã Unicode khác nhau nhưng hiển thị tương tự. NFC hữu ích để so sánh cho mục đích **search/display**; vẫn không biến chuỗi tên thành khóa định danh.

### 4.3. Trạng thái đa ngôn ngữ và profile update

Claim `locale` giúp chọn quy tắc hiển thị ngày/giờ/tên, không xác thực quốc tịch hay nguồn gốc. Khi IdP thay tên, ứng dụng có thể đồng bộ vào profile tùy thẩm quyền từng nguồn, nhưng nên lưu thời điểm/nguồn và tránh ghi đè tên người dùng đã tự chọn nếu quy trình sản phẩm không muốn. Đối với tên sử dụng trên chứng từ pháp lý, cần **nguồn có thẩm quyền riêng**; tên trên token SSO không mặc nhiên là legal name đã kiểm tra giấy tờ.

## 5. Chuẩn hóa email: display khác verification khác identity

### 5.1. Trường OIDC và giới hạn ý nghĩa

OIDC định nghĩa `email` và `email_verified`. `email_verified = true` nghĩa là OP đã thực hiện bước xác nhận kiểm soát email theo chính sách của nó tại thời điểm xác minh. Đây **không phải bảo đảm vĩnh viễn** người dùng đang sở hữu hộp thư hoặc email được cấp riêng cho người đó; cũng không phải quyền để gán vào account nội bộ có cùng email.

Nếu `email_verified` vắng mặt hoặc `false`, coi trạng thái **chưa được xác minh** trong luồng dựa trên OIDC, không tự chuyển thành true từ việc người dùng đã login. Với SAML, một attribute `mail` không có cờ verification chuẩn tương đương cho mọi IdP; chỉ gắn verified nếu có **hợp đồng tin cậy/bằng chứng riêng** xác nhận IdP chịu trách nhiệm kiểm chứng.

**Ba trạng thái nên tách:**

| Trạng thái | Ý nghĩa | Được làm gì? |
| --- | --- | --- |
| `emailPresent` | IdP đưa một chuỗi trông như email | Có thể hiển thị nếu hợp lệ và phù hợp chính sách |
| `emailVerified` | Nguồn có thẩm quyền xác minh quyền kiểm soát theo contract | Có thể dùng cho thông báo/khôi phục phù hợp chính sách; không tự link account |
| `emailPrimaryForContact` | Người dùng/tổ chức đã chọn địa chỉ liên hệ chính | Là lựa chọn sản phẩm, độc lập với khóa định danh `iss + sub` |

**Không đồng nhất** email là claim đăng nhập, email là địa chỉ gửi thông báo, email là username và email là principal ID. Một mailbox có thể là shared alias; một user có thể đổi tên miền công ty; email cũ có thể tái cấp phát cho người khác.

### 5.2. Cách chuẩn hóa an toàn

- `strip` khoảng trắng đầu/cuối do dữ liệu cấu hình; không sửa tùy tiện phần bên trong địa chỉ.
- Có thể **lowercase phần domain** sau dấu `@` bằng quy tắc phù hợp và xử lý tên miền IDN/Punycode khi hệ thống hỗ trợ; phần local-part theo tiêu chuẩn email có thể có khác biệt chữ hoa/chữ thường. Không ép lowercase toàn địa chỉ như một quy luật nhận dạng phổ quát.
- Không tự loại dấu chấm hoặc chuỗi `+tag` ở local-part. Những biến đổi kiểu “Gmail bỏ dấu chấm/plus” là chính sách riêng của một provider và có thể gây gộp sai đối với domain khác.
- Dùng parser/validator email phù hợp sản phẩm (có tính đến Unicode/EAI và chính sách gửi mail), chứ không dùng regex đơn giản để quyết định tài khoản nào được liên kết.
- Kiểm tra địa chỉ email và độ dài theo chính sách, chống control characters/header injection trước khi gửi mail; sanitize log.
- Lưu cả giá trị do nguồn cung cấp và giá trị chuẩn hóa cho **mục tiêu tìm kiếm/liên hệ**, kèm source, timestamp, verification. Không dùng canonical email làm unique key người dùng toàn hệ thống.
- Dữ liệu email vẫn là PII; tránh đưa vào URL, cookie, access token dư thừa hoặc log.

**Ví dụ:**

```text
Giá trị nhận:      "  Lan@Example.ORG  "
Email hiển thị:    "Lan@example.org"
Đã xác minh?       Chỉ nếu nguồn có bằng chứng tương ứng.

Giá trị khác:      "lan@example.org"
Không tự kết luận: "Lan@..." và "lan@..." là cùng một account.
Không tự kết luận: "lan+finance@example.org" cùng "lan@example.org".
```

### 5.3. Account linking: điều kiện phải nghiêm ngặt hơn email matching

Trường hợp tài khoản nội bộ `localAccountId=123` đã liên kết với OIDC A, người dùng đăng nhập bằng SAML B có `mail` trùng email hiện tại. Ứng dụng **không được tự nối** SAML B với account 123 chỉ dựa vào email; cần quy trình:

1. Người dùng có **phiên đã xác thực mạnh** với account nội bộ hoặc một external identifier đã liên kết.
2. Người dùng chủ động yêu cầu thêm nguồn B.
3. Thực hiện federation login với B, xác minh chính xác B issuer/certificate/NameID hoặc immutable identifier.
4. Đánh giá rủi ro/step-up, xác nhận user đã kiểm soát account hiện tại và định danh mới; với account quản trị có thể yêu cầu phê duyệt bổ sung.
5. Chặn nếu external identifier B đã được liên kết với account khác; không “chiếm chuyển” tự động.
6. Ghi audit sự kiện link/unlink (nguồn, subject key đã băm/giới hạn hiển thị, thời gian, actor, xác thực), thông báo chủ tài khoản theo chính sách.
7. Thực thi unique constraint và transaction để tránh hai request đồng thời nối sai.

Đây là khuyến nghị quan trọng trong NIST federation account linking: thao tác nối danh tính cần được bảo vệ bằng phiên xác thực, không chỉ email trùng.

## 6. Chuẩn hóa nhóm/role: tên giống nhau không chứng minh quyền giống nhau

### 6.1. Thực tế các nguồn phát nhóm

| Nguồn | Claim/attribute phổ biến | Hình dạng | Cảnh báo |
| --- | --- | --- | --- |
| OIDC IdP A | `groups` | `["finance-read","operations"]` | `groups` không phải claim chuẩn bắt buộc OIDC Core; có thể chỉ có trong UserInfo |
| OIDC IdP B | `roles`, `realm_access.roles` | list string hoặc object lồng nhau | Schema riêng của vendor, phải khai báo đường dẫn chính xác |
| SAML IdP C | `memberOf`, `groups`, `Role` hoặc OID/URI | list DN, GUID, string | Có thể gửi AttributeValue nhiều giá trị, độ dài/encoding khác nhau |
| Broker | `upstream_groups` hoặc `app_roles` | mapped claim do broker phát | Chỉ được tin trong phạm vi quyền broker được ủy quyền |
| SCIM/HR directory | group membership ngoài login | membership hoặc entitlement cập nhật nền | Cần đánh giá độ mới, authoritative source và revocation |

Một nhóm tên `Admins` từ IdP đối tác **không đồng nghĩa** `ROLE_ADMIN` trong ứng dụng nội bộ. Ngay cả cùng một IdP, `Admins` của tenant A có thể khác tenant B. Cần xét đủ **issuer + tenant + group identifier** và chính sách gán vào permission nội bộ.

### 6.2. Chính sách ánh xạ allowlist theo nguồn

Ví dụ xây hợp đồng:

| Provider đã kiểm tra | External group ID chính xác | Permission nội bộ | Phạm vi |
| --- | --- | --- | --- |
| `staff-a` (issuer staff) | `finance-read` | `REPORT_READ` | Chỉ báo cáo của nhân viên |
| `staff-a` | `approvers-v2` | `REPORT_APPROVE` | Cần giới hạn bản ghi/đơn vị |
| `partner-b` (issuer đối tác) | `CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu` | `REPORT_READ` | Chỉ dữ liệu được chia sẻ với đối tác |
| `partner-b` | `CN=Admins,OU=Apps,...` | **Không map** | Không tự cấp quyền admin nội bộ |
| Issuer khác/claim lạ | `admin` hoặc mọi chuỗi khác | **Không map** | Fail closed |

Nếu IdP có GUID/immutable group ID, dùng ID ổn định hơn display name hoặc distinguished name có thể đổi khi nhóm chuyển OU. Khi IdP chỉ cung cấp DN/string, document quy tắc rename và version mapping; không dùng `toLowerCase`, `contains("admin")` hoặc split string tùy tiện. Quản trị quyền cần phê duyệt bởi chủ ứng dụng, **không phải chỉ người quản trị IdP đối tác**.

### 6.3. Nguyên tắc least privilege và defense in depth

- **Default deny:** nhóm thiếu, malformed, không thuộc allowlist → không cấp quyền nghiệp vụ mới. Xác thực thành công không mặc nhiên cấp `REPORT_READ` hay `ROLE_ADMIN`.
- **Tách quyền theo hành động:** ưu tiên permission như `REPORT_READ`, `REPORT_APPROVE`, `USER_MANAGE` hơn ánh xạ thẳng mọi string thành một role quá rộng.
- **Phân quyền trên tài nguyên:** có `REPORT_READ` vẫn phải kiểm tra user/tenant được đọc **báo cáo cụ thể** nào.
- **Nguồn authoritative cho quyền cao:** vai trò nhạy cảm có thể yêu cầu quyết định nội bộ hoặc hai nguồn/step-up, không chỉ một external group.
- **Freshness:** membership trong ID Token/SAML Assertion là ảnh chụp tại thời điểm phát; khi người dùng bị xóa nhóm ở IdP, session Spring đang mở có thể giữ authorities cũ. Cần session timeout, re-authentication, revocation, back-channel provisioning/deprovisioning hoặc đánh giá quyền tại mỗi request nhạy cảm tùy chính sách.
- **MFA không thay entitlement:** claim `amr`/`acr` biểu thị ngữ cảnh xác thực (nếu được tin), không chứng minh quyền nghiệp vụ.
- **Không trust claim từ browser:** không lấy `X-Groups`, localStorage hoặc form body làm cơ sở quyền nếu backend chưa kiểm chứng qua kênh có thẩm quyền.

**Phân biệt role và scope:** Với OIDC login, `SCOPE_profile` hay `SCOPE_email` là phạm vi OAuth client yêu cầu, **không phải nhóm nhân viên**. `ROLE_ADMIN` của ứng dụng phải được cấp qua mapping hoặc local policy đã phê duyệt; không suy ra từ scope.

## 7. Pipeline chuẩn hóa nên xây trong ứng dụng

```text
      OIDC ID Token/UserInfo        SAML Response/Assertion
         (OP A, OP B)                 (IdP C)
                |                        |
                v                        v
          Validation OIDC           Validation SAML
          iss/aud/signature         issuer/signature/
          exp/nonce/claims          audience/recipient/time
                |                        |
                +-----------+------------+
                            |
                            v
                  Trusted Source Context
                   issuer, registrationId,
                   tenant, protocol, subject
                            |
                            v
                    Attribute Extractor
                name/email/verification/groups
                            |
                            v
                    Normalization Layer
                  unicode/profile/email forms
                            |
                            v
                   Source-specific Mapper
                  exact group IDs => permissions
                            |
                            v
                     Account Resolver
              stable external key => localAccountId
                      (link only by policy)
                            |
                            v
                   Authorization Layer
              permission + tenant + object rights
                            |
                            v
                     Application Data
```

**Kiến trúc quan trọng:** Xác thực **trước**, chuẩn hóa **sau**. Bộ mapping không được nhận thẳng raw JWT/unchecked XML từ HTTP request. Nó nên nhận dữ liệu đã được Spring Security xác minh, cộng với registration/issuer context đáng tin cậy. Ngoài ra cần giới hạn **độ dài và số lượng** các claim/attributes để tránh DoS và bảo vệ tính nhất quán.

### 7.1. Canonical model

Trong code/business logic, có thể chia:

```text
VerifiedExternalIdentity:
  sourceKey             // được resolve từ cấu hình đáng tin
  subject               // OIDC sub, hoặc SAML persistent identifier
  claims                // subset đã được kiểm chứng
  authenticationTime
  assuranceContext      // khi IdP và hợp đồng cho phép diễn giải

CanonicalProfile:
  displayName
  emailForDisplay
  emailVerificationState
  locale

CanonicalEntitlements:
  applicationPermissions
  tenantScope
  policyVersion
  evaluatedAt
```

Nếu claim thuộc tính quan trọng không có, không đoán từ username/chuỗi NameID; có thể hiển thị fallback, **không cấp quyền tương ứng**. Nếu dữ liệu đến từ nhiều nguồn cùng được liên kết với một local account, cần **chính sách ưu tiên theo từng field**, chẳng hạn email công việc lấy từ HR directory còn displayName do người dùng chọn; không dùng “lần login gần nhất thắng tất cả” khi một đối tác ít tin cậy có thể ghi đè thuộc tính nhạy cảm.

### 7.2. Đồng bộ chủ động và đồng bộ khi đăng nhập

- **Just-in-Time (JIT) provisioning:** tạo hồ sơ khi lần đầu login thành công; dễ triển khai nhưng phát hiện deprovision trễ. Unique constraint bắt buộc.
- **SCIM/directory sync:** cập nhật, khóa hoặc thu hồi entitlement qua kênh quản lý ngoài SSO; cần kiểm tra quyền nguồn và xử lý out-of-order events.
- **Login-time refresh:** lấy profile/groups từ claims mỗi lần login; quyền có thể lạc hậu trong session tới lần login tiếp theo.
- **Just-in-time authorization:** với tác vụ nhạy cảm, kiểm tra quyền từ authoritative store ở mỗi request hoặc định kỳ; thêm kiểm tra tenant/object.

Chọn mô hình theo rủi ro. Đừng tự gọi một API bên ngoài cho mọi request mà không timeout/cache/error policy; khi nguồn group mất kết nối phải có hành vi fail-closed phù hợp. Quan trọng hơn, **quyết định phân quyền phải có thời hạn và phiên bản policy**.

## 8. Ví dụ Java 17+ độc lập: canonical hóa dữ liệu và nhóm

Ví dụ sau chỉ sử dụng thư viện chuẩn Java 17, không cần Spring. Nó mô phỏng bước **sau khi IdP đã được xác minh**. `sourceKey` được lấy từ bảng cấu hình đã phê duyệt, không phải chuỗi do người dùng tự khai báo.

File `FederatedNormalizationDemo.java`:

```java
import java.net.IDN;
import java.text.Normalizer;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class FederatedNormalizationDemo {

    record ExternalKey(String sourceKey, String subject) { }

    record VerifiedIdentity(
            String sourceKey,
            String subject,
            String displayName,
            String email,
            boolean emailVerified,
            List<String> groups) { }

    record CanonicalIdentity(
            ExternalKey key,
            String displayName,
            String emailDisplay,
            boolean emailVerified,
            Set<String> permissions) { }

    private static final Map<String, Map<String, String>> GROUP_MAPPING =
        Map.of(
            "staff-a",
            Map.of(
                "finance-read", "REPORT_READ",
                "approvers-v2", "REPORT_APPROVE"),
            "partner-b",
            Map.of(
                "CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu",
                "REPORT_READ"));

    private static String normalizeDisplayName(String value) {
        if (value == null || value.isBlank()) {
            return "Người dùng";
        }
        return Normalizer.normalize(value.strip(), Normalizer.Form.NFC);
    }

    // Chỉ để hiển thị trong lab; KHÔNG phải trình phân tích RFC email.
    private static String normalizeDisplayEmail(String value) {
        if (value == null || value.isBlank()) {
            return "";
        }
        String trimmed = value.strip();
        int at = trimmed.lastIndexOf('@');
        if (at < 1 || at >= trimmed.length() - 1) {
            return "";
        }
        String local = trimmed.substring(0, at);
        String domain = trimmed.substring(at + 1);
        try {
            return local + "@" +
                IDN.toASCII(domain).toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException invalidDomain) {
            return "";
        }
    }

    static CanonicalIdentity normalize(VerifiedIdentity identity) {
        if (identity == null
                || !GROUP_MAPPING.containsKey(identity.sourceKey())
                || identity.subject() == null
                || identity.subject().isBlank()) {
            throw new IllegalArgumentException(
                "Unknown source or missing immutable subject");
        }

        Map<String, String> allowed =
            GROUP_MAPPING.get(identity.sourceKey());
        Set<String> permissions = new TreeSet<>();

        // Không tin nhóm ngoài allowlist, không cấp quyền mặc định.
        for (String rawGroup : identity.groups()) {
            String mapped = allowed.get(rawGroup);
            if (mapped != null) {
                permissions.add(mapped);
            }
        }

        return new CanonicalIdentity(
            new ExternalKey(identity.sourceKey(), identity.subject()),
            normalizeDisplayName(identity.displayName()),
            normalizeDisplayEmail(identity.email()),
            identity.emailVerified(),
            Set.copyOf(permissions));
    }

    public static void main(String[] args) {
        VerifiedIdentity a = new VerifiedIdentity(
            "staff-a", "user-8f9", "  Nguyễn Thị Lan  ",
            "Lan@Example.ORG", true,
            List.of("finance-read", "ops-admin"));

        VerifiedIdentity b = new VerifiedIdentity(
            "partner-b", "person-1007", "Nguyễn Thị Lan",
            "lan@example.org", false,
            List.of("CN=Readers,OU=Apps,DC=partner,DC=example,DC=edu",
                    "CN=Admins,OU=Apps,DC=partner,DC=example,DC=edu"));

        CanonicalIdentity first = normalize(a);
        CanonicalIdentity second = normalize(b);

        System.out.println("firstKey=" +
            first.key().sourceKey() + ":" + first.key().subject());
        System.out.println("firstName=" + first.displayName());
        System.out.println("firstEmail=" + first.emailDisplay());
        System.out.println("firstVerified=" + first.emailVerified());
        System.out.println("firstCanRead=" +
            first.permissions().contains("REPORT_READ"));
        System.out.println("firstIsAdmin=" +
            first.permissions().contains("ADMIN"));
        System.out.println("samePersonByKey=" +
            first.key().equals(second.key()));
        System.out.println("secondCanRead=" +
            second.permissions().contains("REPORT_READ"));
        System.out.println("secondIsAdmin=" +
            second.permissions().contains("ADMIN"));
        System.out.println("secondEmailVerified=" +
            second.emailVerified());
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac --release 17 FederatedNormalizationDemo.java
java FederatedNormalizationDemo
```

Stdout xác định:

```text
firstKey=staff-a:user-8f9
firstName=Nguyễn Thị Lan
firstEmail=Lan@example.org
firstVerified=true
firstCanRead=true
firstIsAdmin=false
samePersonByKey=false
secondCanRead=true
secondIsAdmin=false
secondEmailVerified=false
```

**Giải thích kết quả:** Hai tài khoản có displayName và email gần giống nhưng `ExternalKey` khác; không auto-link. IdP B có nhóm chứa chuỗi `Admins` nhưng không có mapping, nên không nhận permission ADMIN. `emailVerified` của B vẫn false dù email giống A.

**Giới hạn và điều kiện dùng thực tế:**

- `sourceKey` trong ví dụ là đại diện cho issuer/registration đã được backend xác minh; production phải lưu actual issuer + subject + tenant/qualifiers như thiết kế ở mục 3.
- `normalizeDisplayEmail` là minh họa cho domain casing và IDN, **không phải email parser đầy đủ RFC 5322/EAI**. Không dùng nó để khẳng định email hợp lệ, gửi mail hoặc link account nếu chưa qua validator và chính sách verification thật.
- Dùng `Set.copyOf` chỉ bảo toàn nội dung không trùng, **không cam kết thứ tự**. Ví dụ không in trực tiếp set để tránh kỳ vọng thứ tự stdout khác JVM. Có thể dùng `TreeSet` để trình bày quyền theo thứ tự khi cần báo cáo.
- Trong hệ thống thật cần giới hạn độ dài, loại claim lạ, kiểm soát các ký tự điều khiển trong dữ liệu hiển thị, normalize ký tự cho search riêng và escape ở HTML. Không dùng `Normalizer.Form.NFC` làm cơ chế xác thực.
- Không phải tất cả SAML NameID đều ổn định. `subject` trong ví dụ chỉ được truyền sau khi nguồn cung cấp đã được xác minh **và** đã xác nhận tính ổn định bằng contract.
- Mỗi phiên bản mapping có owner/phê duyệt; cập nhật mapping không được làm các phiên cũ tự giữ quyền cao vô thời hạn.
- Nếu input `groups` null hoặc trùng schema, production phải validate shape và áp quy tắc fail-closed; ví dụ giả định dữ liệu đã trích xuất thành list an toàn.

## 9. Tích hợp Spring Security: OIDC authorities và SAML attributes

### 9.1. OIDC: `GrantedAuthoritiesMapper` cho nguồn tin cậy

Trong Spring Security Servlet OAuth2/OIDC Login, `OidcUserAuthority` chứa ID Token và UserInfo đã được framework xử lý; có thể sử dụng `GrantedAuthoritiesMapper` để chuyển claim nhóm thành authorities nội bộ. Chỉ tạo authorities khi issuer nằm trong danh sách đã cấu hình và claim có cấu trúc phù hợp.

Ví dụ một Spring Boot 3+/Spring Security 6+ app, Java 17+; file `src/main/java/com/example/federation/OidcRoleConfig.java`:

```java
package com.example.federation;

import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Configuration
public class OidcRoleConfig {

    private static final String STAFF_ISSUER =
        "https://login-a.example.org/realms/staff";

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return input -> {
            Set<GrantedAuthority> result = new HashSet<>();

            for (GrantedAuthority authority : input) {
                if (!(authority instanceof OidcUserAuthority oidc)) {
                    continue;
                }
                String issuer = oidc.getIdToken().getIssuer().toString();

                if (!STAFF_ISSUER.equals(issuer)) {
                    continue;
                }

                // groups là claim riêng của IdP đã thỏa thuận.
                Object raw = oidc.getIdToken().getClaims().get("groups");
                if (!(raw instanceof java.util.List<?> groups)) {
                    continue;
                }

                for (Object group : groups) {
                    if ("finance-read".equals(group)) {
                        result.add(new SimpleGrantedAuthority(
                            "APP_REPORT_READ"));
                    } else if ("approvers-v2".equals(group)) {
                        result.add(new SimpleGrantedAuthority(
                            "APP_REPORT_APPROVE"));
                    }
                }
            }
            return result;
        };
    }
}
```

**Điều kiện tích hợp:** Class là một Spring Bean trong project có `spring-boot-starter-security` và `spring-boot-starter-oauth2-client` (hoặc dependency tương đương). Đăng ký bean mapper và bật `http.oauth2Login(...)` trong filter chain; Spring Security cung cấp đường cấu hình mapper qua `oauth2Login().userInfoEndpoint().userAuthoritiesMapper(...)` hoặc bean được hệ thống sử dụng đúng theo version. Class trên **không tự chạy bằng `javac` không có Spring dependencies**.

Lời giải thích:

- `STAFF_ISSUER` là issuer test được cấu hình; trong production nên lấy từ source registry đã review, không từ input client. Dù claim `iss` đã được framework kiểm tra, việc ràng buộc issuer trong **policy mapping** giúp chỉ issuer nhân viên được gán quyền nhân viên.
- Mapping exact-string chỉ chấp nhận hai group ID `finance-read` và `approvers-v2`; các role lạ, `admin` hoặc nhóm của IdP khác không được dùng.
- Tên authority `APP_REPORT_READ` khác `ROLE_ADMIN` và `SCOPE_profile`; ứng dụng có thể dùng `hasAuthority("APP_REPORT_READ")` cho route hoặc method. Không tự cấp quyền từ OAuth scopes.
- Một IdP có thể đặt `groups` trong **UserInfo** thay vì ID Token, hoặc không cấp `groups` theo scope mặc định. Khi đó phải điều chỉnh extractor theo hợp đồng nguồn, kiểm tra tính nhất quán `sub` và policy UserInfo; không “fallback” sang claim bất kỳ hoặc header do client gửi.
- Code mapper ở trên **trả về chỉ các authority nghiệp vụ đã được map**. Nếu ứng dụng khác còn cần những authorities kỹ thuật phục vụ flow, cần thiết kế lại whitelist rõ ràng và kiểm thử filter/authorization của phiên bản Spring đang dùng; không sao chép bừa `input` vì nó có thể mang `SCOPE_*` không phải role.
- `email_verified` và `name` không tham gia cấp quyền. Mapping quyền cao cần kiểm tra rủi ro/độ mới, không chỉ một claim string.

Ví dụ cấu hình route sử dụng authority mới:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .requestMatchers("/reports/**")
                    .hasAuthority("APP_REPORT_READ")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Đây là file Java riêng `WebSecurityConfig.java` trong package `com.example.federation`, cùng package/import/package declaration tương ứng. Không dùng snippet import này nối ngay dưới file `OidcRoleConfig.java` đang có class, vì Java không cho phép đặt `import` sau class. Trong project hoàn chỉnh, đặt `package com.example.federation;` ở đầu `WebSecurityConfig.java`.

**Quan trọng:** `hasAuthority` chỉ kiểm tra permission ở cấp URL; service xử lý báo cáo phải kiểm tra tenant/owner/đơn vị và từng bản ghi. `REPORT_READ` từ đối tác chỉ được áp dụng cho tập dữ liệu đối tác được phép đọc, không tự động cho quyền trên tất cả dữ liệu công ty.

### 9.2. SAML: đọc attributes đã xác minh qua `Saml2AuthenticatedPrincipal`

Trong Spring Security SAML2, khi `SAMLResponse` được xác minh thành công, `Authentication#getPrincipal` thường là `Saml2AuthenticatedPrincipal`, có `getAttributes()` trả map tên attribute → danh sách giá trị. Tên NameID được dùng làm principal name theo cơ chế mặc định, nhưng **không đủ để quyết định account linking** nếu IdP không có stable NameID.

Ví dụ Java thuộc Spring Boot, **đọc dữ liệu không tự cấp quyền**:

```java
package com.example.federation;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SamlProfileController {

    @GetMapping("/saml-profile")
    public Map<String, Object> profile(Authentication authentication) {
        if (!(authentication.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return Map.of("authenticatedBySaml", false);
        }

        String registrationId =
            principal.getRelyingPartyRegistrationId();

        // Tên thuộc tính phải lấy từ contract của IdP tương ứng.
        List<Object> names = principal.getAttributes()
            .getOrDefault(
                "urn:oid:2.16.840.1.113730.3.1.241",
                List.of());

        return Map.of(
            "authenticatedBySaml", true,
            "registration", registrationId,
            "hasDisplayName", !names.isEmpty());
    }
}
```

**Bảo mật ví dụ:** Code không trả raw assertions/NameID/email hay danh sách nhóm ra response. Endpoint `/saml-profile` vẫn phải được bảo vệ bởi `saml2Login`/`authenticated` trong security chain. Đừng coi controller này là kiểm chứng SAML; kiểm chứng chữ ký/issuer/audience/recipient xảy ra **trước**, tại Spring Security/OpenSAML. Nếu có nhiều filter chain, đảm bảo route không bypass validation.

Để **cấp authorities từ SAML attributes**, tích hợp mapping vào quá trình tạo `Saml2Authentication`/authentication provider theo phiên bản Spring Security đang dùng (ví dụ các extension points về conversion của `OpenSaml5AuthenticationProvider`), hoặc xử lý kiểm tra permission bằng một authorization service sau khi xác thực với dữ liệu đã kiểm chứng. Cần audit và áp mapping theo `registrationId` + IdP entityID + tenant; **đừng chỉ cho principal.getAttributes().get("memberOf") chứa Admins rồi tự tạo ROLE_ADMIN**. Nếu sử dụng Spring Security 7, API extension point có thể khác các dự án 6.x; luôn theo reference của đúng version.

### 9.3. Một mô hình chung cho cả SAML và OIDC

Tách extractor thành hai adapter:

```text
OidcVerifiedClaimsAdapter
    input: OidcUser + verified ClientRegistration/Issuer
    output: VerifiedExternalIdentity

SamlVerifiedAttributesAdapter
    input: Saml2AuthenticatedPrincipal + verified registration
    output: VerifiedExternalIdentity

NormalizationService
    input: VerifiedExternalIdentity
    output: CanonicalProfile + ExternalKey

EntitlementMapper
    input: ExternalKey/source + allowlisted group IDs
    output: application permissions

AccountLinkService
    input: verified ExternalKey + proven local account session
    output: linked identifier (only after policy approval)
```

Như vậy, tên, email và nhóm ở hai giao thức được chuẩn hóa về **cấu trúc dữ liệu chung**, nhưng **không ép bằng chứng và độ tin cậy giống nhau**. Ví dụ OIDC `email_verified` có semantics được tiêu chuẩn hóa; SAML `mail` cần contract khác. OIDC `sub` ổn định theo issuer; SAML `NameID` có nhiều format với độ ổn định khác nhau.

## 10. Chính sách xung đột khi một account có nhiều IdP

Giả sử sau một quy trình account linking có bằng chứng, account nội bộ có hai nguồn:

| Field | Nguồn A | Nguồn B | Quy tắc được duyệt |
| --- | --- | --- | --- |
| Display name | `Nguyễn Thị Lan` | `Lan Nguyễn` | Giữ tên do user chọn hoặc nguồn HR theo contract |
| Email | `lan@corp.example` verified | `lan@partner.example` unverified | Chỉ email có chính sách liên hệ/verification phù hợp mới làm primary |
| Group | `finance-read` | `CN=Admins,...` | A có thể cấp REPORT_READ; B không cấp ADMIN |
| Office/Department | HR directory | claim OIDC tự cấu hình | Nguồn HR authoritative cho dữ liệu tổ chức nếu policy quy định |
| Account disabled | HR/SCIM | SSO session còn tồn tại | Không chấp nhận việc login cũ làm bật lại account đã disabled |
| Tenant access | Internal ABAC | Partner IdP tenant claim | Kiểm tra tenant trên tài nguyên; không giao quyền tenant chỉ bằng email |

**Thiết kế field-level precedence:** không phải cứ claim “mới nhất” là được phép ghi đè; sự mới/tin cậy/cấp quyền của từng nguồn phải được xác định theo field. Các thay đổi ảnh hưởng phân quyền phải có audit và quyền sửa policy riêng. Đừng dùng một API `PATCH /profile` nhận `groups` rồi ghi thẳng vào entitlements.

Khi user mất liên kết với nguồn IdP A, quyết định có khóa toàn bộ local account hay chỉ xóa external identifier A phụ thuộc chính sách bảo mật và nghĩa vụ dữ liệu. Cần thông báo, xóa/revoke session theo rủi ro; không tự gán sang một tài khoản khác có cùng email.

## 11. Những trường hợp khó và cách giải quyết

### 11.1. Email bị đổi hoặc tái cấp phát

IdP A đổi email từ `lan@corp.example` sang `lan.nguyen@corp.example` nhưng `iss + sub` giữ nguyên. **Đây vẫn là cùng external identity**. Cập nhật email hiển thị/liên hệ theo chính sách, không tạo user mới, không chuyển quyền dựa trên email.

Nếu nhân viên nghỉ và email cũ được tái cấp phát cho người khác, user mới có `sub` khác. Nếu hệ thống liên kết bằng email, user mới có thể thừa hưởng dữ liệu/nghiệp vụ người cũ. Unique constraint theo external identifier là lớp phòng vệ quan trọng.

### 11.2. Group rename hoặc chuyển OU

IdP SAML gửi `CN=Readers,OU=Finance,...` rồi di chuyển sang `CN=Readers,OU=Apps,...`. Nếu mapping dựa vào DN nguyên văn, quyền có thể mất; đừng xử lý bằng `contains("Readers")`. Ưu tiên group object ID ổn định hoặc quy trình cập nhật mapping có version, kiểm thử trước chuyển đổi.

### 11.3. Cùng group name nhưng hai tenant khác nhau

Tenant nhân viên có `admin`, tenant đối tác cũng có `admin`. Nếu code chỉ kiểm tra `group.equalsIgnoreCase("admin")`, có thể nâng quyền đối tác. Luôn dùng `sourceKey/issuer + tenant + exactGroupId` và allowlist. Ngay cả trong tenant đã tin, role `admin` phải được ánh xạ vào **quyền cụ thể** mà ứng dụng cho phép.

### 11.4. Claim nhiều giá trị và sai kiểu

SAML `AttributeValue` có thể là danh sách; OIDC custom `groups` có thể là array hoặc string theo IdP; nested `realm_access.roles` là JSON object vendor-specific. Không ép mọi thứ thành CSV bằng `toString()` rồi split comma vì giá trị DN chứa dấu phẩy hợp lệ. Kiểm tra kiểu, số lượng, độ dài, null, duplicate và từ chối format không theo hợp đồng. Khi thiếu group, quyền mới là tập rỗng; không dùng vai trò cuối cùng của phiên trước như mặc định vĩnh viễn.

### 11.5. Nhóm quá nhiều hoặc token vượt kích thước

Một số IdP không phát toàn bộ nhóm trong ID Token mà đưa `groups overage`/pointer tới API khác; broker có thể cắt nhóm; SAML assertion lớn làm HTTP POST quá size limit. **Đừng hiểu “claim thiếu” là user có quyền cũ**. Nếu phải gọi Graph/Directory API, dùng service access có quyền tối thiểu, request timeout, validate response theo nguồn và bảo vệ cache/thời hạn; không lấy group names từ URL do client cung cấp.

### 11.6. Unicode và email homograph

Tên có dấu, ký tự kết hợp, direction markers và Unicode lookalikes có thể gây nhầm trên giao diện. NFC là một công cụ thống nhất encoding, **không chống được mọi homograph**. Khi hiển thị kết quả tìm kiếm account, có thể hiển thị thêm thông tin ít nhạy cảm đã được phép để người dùng xác nhận, chứ không link dựa vào tên. Email quốc tế hóa cần thư viện/SMTP hỗ trợ phù hợp; không tự loại ký tự Unicode rồi coi là cùng địa chỉ.

### 11.7. SAML transient NameID và OIDC pairwise `sub`

SAML `transient` có thể đổi qua phiên, không phù hợp làm external ID dài hạn. Nếu IdP chỉ cung cấp NameID transient, yêu cầu **attribute định danh bất biến** đã thỏa thuận và xác minh thuộc tính đó được phát bởi nguồn tin cậy trước khi tạo local account. Với OIDC, `sub` có thể là **pairwise** theo sector identifier/RP, không bằng `sub` của cùng người tại app khác. Không tổng hợp account xuyên RP dựa trên email hoặc cố so sánh `sub` của hai issuer.

## 12. Test matrix chuẩn hóa và phân quyền

Mọi fixture cần đại diện dữ liệu **sau bước xác thực OIDC/SAML hợp lệ**, trừ các case cố tình kiểm tra validation nguồn. Không nên sửa raw ID Token/SAMLAssertion đã ký rồi coi lỗi chữ ký là bằng chứng mapping hoạt động đúng.

| Ca thử | Input/điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Tên Unicode dạng kết hợp | Hai chuỗi có cách biểu diễn khác nhau nhưng cùng tên | Display NFC nhất quán; external key không đổi |
| Tên thiếu | `name` vắng mặt, có `given_name`/`family_name` hoặc không có | Fallback an toàn; không tạo/merge user theo tên |
| Email domain uppercase | `Lan@Example.ORG` | Domain có thể chuẩn hóa để hiển thị; local-part giữ nguyên |
| Email local-part khác case | `Lan@example.org` vs `lan@example.org` | Không dùng biến đổi case để tự link identity |
| Email `+tag` hoặc dấu chấm | `lan+test@example.org` | Không tự bỏ tag/dot |
| Email verified false/missing | OIDC `email_verified` vắng mặt hoặc false | Không gắn verified, không auto-link |
| Email giống nhau từ hai issuer | OIDC A `sub=u1`; OIDC B `sub=u2` | Hai ExternalKey khác nhau; không auto-link |
| Email đổi nhưng `iss+sub` giữ | `sub=u1`, email mới | Cùng external key; cập nhật profile theo chính sách |
| IdP unknown hoặc issuer mismatch | Token/response không đúng nguồn tin cậy | Từ chối ở authentication, không chạy mapping |
| SAML NameID transient | NameID thay mỗi session | Không dùng làm persistent local key nếu chưa có nguồn ổn định khác |
| Claim nhóm thiếu | Không có `groups` | Không cấp quyền nghiệp vụ mới |
| Claim nhóm sai kiểu | `groups` là string bất thường thay vì array | Fail closed hoặc lỗi mapping được kiểm soát |
| Nhóm cùng tên từ hai issuer | `admin` ở internal và partner | Chỉ mapping nơi có policy được duyệt |
| Nhóm unknown/typo | `finance-read-2027` chưa trong allowlist | Không cấp `REPORT_READ`, cảnh báo nếu cần |
| Group rename | DN/ID khác contract | Mất quyền theo fail closed, yêu cầu cập nhật mapping có review |
| Quyền cao | IdP đối tác gửi `Admins` | Không thành `ROLE_ADMIN` nếu không được phê duyệt |
| Token scope được cấp | `SCOPE_email` / `SCOPE_profile` | Không suy ra entitlement báo cáo/quản trị |
| User bị xóa nhóm sau login | Session cũ còn authority | Policy revocation/session re-evaluation phải giới hạn rủi ro |
| Nhiều group values | List có duplicate và case khác nhau | Dedupe có chủ đích, exact match theo policy; không nới lỏng |
| Đa tenant | User A có `REPORT_READ` ở tenant A | Không đọc tenant B nếu ownership/ABAC không cho phép |
| Account linking đồng thời | Hai request nối cùng external ID vào hai local account | Unique constraint/transaction chặn double-link |
| UserInfo khác `sub` ID Token | Trả dữ liệu chủ thể khác | Từ chối theo OIDC; không dùng data sai chủ thể |
| SAML attribute không được IdP ký/thẩm quyền | XML bị sửa hoặc nguồn chưa được trust | Authentication thất bại; không cấp quyền |

**Kiểm thử quyền phải gồm cả route và object-level**. Ví dụ một user có `APP_REPORT_READ` vẫn bị `403` hoặc denied cho báo cáo tenant khác; một user không có permission dù login thành công không truy cập được route quản trị.

### 12.1. Test audit về nguồn dữ liệu

Với một đăng nhập, log tối thiểu trong hệ thống có phân quyền:

```text
authEventId
protocol: OIDC | SAML2
providerKey / verified issuer / registrationId
subject: định danh giả danh hóa hoặc tham chiếu nội bộ
accountId: local ID
mappingVersion
acceptedPermissionCodes
rejectedGroupCount
emailVerificationState
timestamp UTC
decision: GRANTED / DENIED
```

Không log raw ID Token/Access Token, SAMLResponse, NameID đầy đủ nếu không cần, cookie, email thật và danh sách nhóm nhạy cảm. `rejectedGroupCount` hữu ích để phát hiện mapping drift mà không công khai tất cả thông tin. Log phải phục vụ điều tra theo chính sách lưu giữ và truy cập.

## 13. Checklist triển khai thực tế

- [ ] Mỗi IdP có `providerKey`, issuer/entityID, tenant, registration, certificate/key, schema claim và owner rõ ràng.
- [ ] OIDC ID Token `iss/aud/sub`/chữ ký/thời hạn đã được xác minh; SAML assertion chữ ký/issuer/audience/recipient/time/replay đã được kiểm tra.
- [ ] Khóa external identity không dùng name/email; dùng `iss + sub` cho OIDC và định danh SAML ổn định theo contract.
- [ ] Tên hiển thị giữ Unicode/locale hợp lý, không bị dùng làm khóa liên kết, đã escape khi xuất HTML.
- [ ] Email có trạng thái nguồn/verification; domain canonicalization chỉ để display/search; không áp Gmail dot/plus rules phổ quát.
- [ ] Không auto-link account theo email trùng; account linking cần phiên xác thực, chủ thể đồng ý/step-up theo rủi ro và audit.
- [ ] Group/role claim được parse đúng schema và kiểu, giới hạn size; nguồn ngoài allowlist không thể cấp quyền.
- [ ] Mapping phân tách issuer/tenant/group ID và version policy, quyền cao được quản trị nội bộ phê duyệt.
- [ ] Không tự coi OAuth scopes, `name`, `email` hoặc `preferred_username` là authority.
- [ ] Quyền ứng dụng và dữ liệu đa tenant có enforcement ở route/method và service/object layer.
- [ ] Có cơ chế cập nhật và thu hồi khi group membership thay đổi; không giữ đặc quyền cũ vô hạn trong session.
- [ ] Test với Unicode, email đổi/tái cấp phát, nhiều issuer trùng email, group rename, group unknown, session cũ và tenant khác.
- [ ] Log đủ audit nhưng không lộ token, private attributes, session secrets hoặc raw assertion.

**Kết luận:** Chuẩn hóa không có nghĩa “gộp các IdP thành một namespace”. Phương án đúng là **giữ định danh theo nguồn**, chuẩn hóa riêng dữ liệu profile có tính thay đổi, lưu **provenance** của email, và chỉ ánh xạ **nhóm đã được phê duyệt theo issuer/tenant** thành quyền của ứng dụng. Spring Security giúp kiểm chứng OIDC/SAML và cung cấp authorities/principal, nhưng ứng dụng vẫn chịu trách nhiệm **account linking, permission mapping và phân quyền tài nguyên cuối cùng**.

## 14. Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Standard Claims và Claim Stability](https://openid.net/specs/openid-connect-core-1_0.html): `iss/sub`, `name`, `email`, `email_verified`, `preferred_username` và tính duy nhất.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `GrantedAuthoritiesMapper`, `OidcUserAuthority`, `OidcUserService` và xử lý UserInfo.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `Saml2AuthenticatedPrincipal`, attributes, xác minh assertion và `Saml2Authentication`.
- [Spring Security — SAML2 Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): cấu hình response authentication, cấp `GrantedAuthority` theo version.
- [NIST SP 800-63C-4 — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): federated identifiers, account linking và xử lý danh tính tại relying party.
- [OASIS SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID formats, Attributes và assertion conditions.
- [Java 17 `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization NFC/NFKC.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/): canonical/compatibility normalization và giới hạn sử dụng.
