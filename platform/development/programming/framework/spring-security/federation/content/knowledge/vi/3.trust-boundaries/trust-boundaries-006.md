# Định danh người dùng ổn định trong phạm vi từng nhà cung cấp

## 1. Mục tiêu và bối cảnh

Trong **Spring Security – federation**, ứng dụng có thể nhận kết quả đăng nhập từ nhiều nhà cung cấp danh tính (Identity Provider, viết tắt **IdP**). Câu hỏi thiết kế quan trọng là: **lần đăng nhập hôm nay và lần đăng nhập tháng sau có thực sự thuộc cùng một người dùng không?** Nếu hai người từ hai IdP cùng có tên `alex` hoặc cùng một giá trị ID ngắn `123`, làm sao tránh gộp nhầm tài khoản?

Bài học thuộc nhóm **ranh giới tin cậy**: ứng dụng chỉ được đồng nhất danh tính khi bằng chứng xác thực đến từ nhà cung cấp đã tin cậy và định danh có **phạm vi rõ ràng**.

Nguyên tắc cốt lõi của OpenID Connect (OIDC):

> Định danh liên kết ổn định mà Relying Party có thể dựa vào là **cặp `(iss, sub)` của ID token hợp lệ**, trong phạm vi và chính sách cấp subject của nhà phát hành.

- **`iss` (issuer):** danh tính logic của nhà phát hành, ví dụ `https://login.example.test/realms/staff`. Một host có thể có nhiều issuer khác nhau do đường dẫn/realm/tenant.
- **`sub` (subject):** định danh của người dùng do issuer cấp. Theo OIDC, nó duy nhất trong issuer, không được cấp lại cho người dùng khác; chuỗi này có phân biệt chữ hoa/chữ thường.
- **Local user ID:** khóa tài khoản do hệ thống nghiệp vụ sở hữu, ví dụ `user_9001`. Nó không đồng nghĩa với `sub` và có thể có nhiều danh tính ngoài liên kết tới.
- **Email, username, display name:** thuộc tính hồ sơ có thể thay đổi hoặc trùng, không phải khóa liên kết ổn định theo bảo đảm của OIDC.

Đối với OIDC, cần nhớ ba tầng: **IdP xác thực và cấp định danh**, **Spring Security kiểm tra kết quả xác thực và cung cấp principal tin cậy**, **ứng dụng liên kết principal với tài khoản nội bộ**. Spring Security không tự bảo đảm mọi IdP có cùng cách đặt mã người dùng.

## 2. Vì sao định danh phải có phạm vi nhà cung cấp?

Xét hai lần đăng nhập sau:

| Lần đăng nhập | Issuer | Subject | Email |
| --- | --- | --- | --- |
| Alice qua IdP của công ty A | `https://idp-a.example.test` | `123` | `alice@a.example.test` |
| Bob qua IdP của công ty B | `https://idp-b.example.test` | `123` | `bob@b.example.test` |

Hai giá trị `sub=123` **không chứng minh** hai bản ghi là một người. Chúng được tạo trong hai không gian định danh khác nhau. Khóa chính xác là:

```text
(https://idp-a.example.test, 123) -> local_user_Alice
(https://idp-b.example.test, 123) -> local_user_Bob
```

Nếu cơ sở dữ liệu chỉ lưu `sub`, lần đăng nhập của Bob có thể bị ánh xạ sang tài khoản Alice. Đó là lỗi **account collision/account takeover** tại ranh giới federation. Tránh lỗi này bằng khóa ghép `issuer + subject`, kết hợp kiểm tra nguồn phát hành trước khi lookup.

Cùng một nhà cung cấp thương mại cũng có thể có nhiều **issuer logic**:

```text
https://sso.example.test/realms/sales   + subject=123
https://sso.example.test/realms/hr      + subject=123
```

Hai danh tính vẫn khác nhau. Không thay `iss` bằng hostname, tên hãng, `registrationId`, `realm` tự suy đoán hoặc domain email. OIDC quy định giá trị issuer phải khớp đúng metadata và token; **đường dẫn là một phần của issuer**. Không tự xóa path, đổi chữ hoa/thường, chuẩn hóa URL tùy tiện hoặc gộp hai issuer khác nhau thành một.

## 3. Điều gì được xem là “ổn định”?

Một khóa để liên kết tài khoản cần những tính chất sau:

1. **Cùng chủ thể theo thời gian:** lần đăng nhập sau vẫn tìm được liên kết cũ dù tên/email thay đổi.
2. **Không tái cấp cho người khác:** nếu chủ thể bị xóa, định danh cũ không chuyển sang người mới.
3. **Có phạm vi uniqueness rõ ràng:** một giá trị `sub` chỉ duy nhất theo **issuer**; không mặc nhiên duy nhất toàn Internet.
4. **Đến từ nguồn được xác minh:** không tin `iss`/`sub` nằm trong JSON/header/query parameter do client tự gửi.
5. **Thỏa thuận về vòng đời:** khi IdP đổi tenant, đổi issuer, chuyển hệ thống hoặc thay chính sách `sub`, ứng dụng cần quy trình migration được kiểm soát.

Theo OIDC Core, `sub` là định danh nội bộ **duy nhất và không được cấp lại trong issuer**. Tuy nhiên, “ổn định” không có nghĩa một con người sẽ nhận **một `sub` chung tại mọi ứng dụng**: OIDC hỗ trợ **pairwise subject identifier** khác nhau theo sector/client. Điều đó bảo vệ quyền riêng tư, và không vi phạm nguyên tắc uniqueness trong issuer.

Ngoài ra, một hệ thống thực tế có thể chuyển từ issuer A sang issuer B hoặc tái cấu trúc dữ liệu bất chấp hợp đồng ban đầu. Ứng dụng không suy ra danh tính mới từ địa chỉ email cũ; cần **liên kết/migration có kiểm chứng**.

## 4. Các loại claim: khóa danh tính và dữ liệu hồ sơ

| Giá trị | Ý nghĩa | Dùng làm khóa nối tài khoản? |
| --- | --- | --- |
| `iss` + `sub` đã xác minh | Danh tính do một OIDC issuer xác lập cho Relying Party | **Có**, theo chính sách issuer/subject đã cam kết |
| Chỉ `sub` | Subject không có không gian nhà phát hành | **Không** trong hệ thống đa IdP |
| `email` | Địa chỉ liên lạc | **Không**: có thể đổi, xóa, tái cấp, trùng/ngụy tạo |
| `email_verified` | Tín hiệu IdP đã kiểm chứng email theo cơ chế của họ | **Không**: không chứng minh chủ tài khoản nội bộ cũ là người hiện tại |
| `preferred_username`, `name` | Tên đăng nhập/hiển thị | **Không**: có thể đổi/trùng, phạm vi khác nhau |
| `groups`, `roles`, `scope` | Nhóm, vai trò, phạm vi quyền | **Không**: phục vụ phân quyền, không phải định danh |
| `aud` | Đối tượng token được cấp cho | Không là user ID; dùng để kiểm tra token dành cho ứng dụng/API |
| `jti` | ID của token JWT nếu có | **Không**: xác định token, không xác định người dùng xuyên các token |
| `sid` | ID phiên khi được phát hành | **Không**: định danh phiên, có thể thay đổi |

Ví dụ người dùng đổi email:

```json
{
  "iss": "https://login.example.test/realms/staff",
  "sub": "7b1f93",
  "email": "mai.old@example.test"
}
```

Sau khi đổi tên miền:

```json
{
  "iss": "https://login.example.test/realms/staff",
  "sub": "7b1f93",
  "email": "mai.new@example.test"
}
```

Hai minh họa là **payload claim rút gọn để giải thích**, không phải JWT hoàn chỉnh hay bằng chứng đã ký. Nếu **ID token đã được OIDC client kiểm tra hợp lệ** và cùng cặp `(iss, sub)`, ứng dụng có thể tìm cùng liên kết nội bộ dù email thay đổi. Không dùng hai đoạn JSON chưa xác thực để tự kết luận rằng người gọi là người cũ.

## 5. Public subject và pairwise subject của OIDC

OIDC hỗ trợ hai kiểu subject:

- **Public subject:** issuer có thể cấp cùng một `sub` cho cùng người dùng qua các client phù hợp. Client không nên suy ra subject của nhà cung cấp khác cũng giống vậy.
- **Pairwise subject:** issuer tạo `sub` khác nhau cho từng **sector identifier** để các ứng dụng khác phạm vi không dễ theo dõi chéo cùng một người. Cùng một người, cùng issuer nhưng ở sector khác có thể có hai subject khác nhau.

Ví dụ minh họa:

| Đăng nhập | Issuer | Sector | Subject |
| --- | --- | --- | --- |
| Nhân viên Mai vào portal A | `https://idp.example.test` | `portal-a.example.test` | `pair-A-8f2` |
| Mai vào portal B | `https://idp.example.test` | `portal-b.example.test` | `pair-B-5d1` |

Không thể tự xác nhận `pair-A-8f2` và `pair-B-5d1` thuộc cùng một con người chỉ vì email giống. Với pairwise subject, sector được tính theo quy định OIDC, thường liên quan host của redirect URI hoặc `sector_identifier_uri`; sự thay đổi cấu hình sector có thể ảnh hưởng đến subject mà client nhận.

**Thiết kế đúng:** xem mỗi cặp `(iss, sub)` là một **external identity** riêng. Nếu doanh nghiệp muốn dùng chung một tài khoản nội bộ giữa portal A/B, việc nối hai danh tính phải theo cơ chế liên kết đã được IdP và ứng dụng chấp thuận (ví dụ cùng session chứng minh hai tài khoản, luồng broker có hợp đồng rõ, hoặc migration được xác thực). Không cố tự tính lại `sub` pairwise, không dùng email như khóa để phá vỡ bảo vệ riêng tư này.

Nếu nhiều redirect URI/client cần giữ danh tính pairwise nhất quán, đội vận hành IdP cần thiết kế sector identifier **trước khi chạy production**, kiểm thử việc thay URL/đổi client và có phương án duy trì ánh xạ cũ.

## 6. Ranh giới tin cậy: “ai nói người dùng này là ai?”

Điểm quan trọng không chỉ là nội dung claim, mà còn là **ai phát hành claim và ứng dụng kiểm tra nó ra sao**.

```text
Người dùng / Browser
   │ chuyển hướng đăng nhập
   ▼
IdP tin cậy (issuer đã đăng ký)
   │ xác thực người dùng, cấp authorization code / ID token
   ▼
Spring Security OIDC Client
   │ kiểm tra luồng và ID token theo cấu hình
   │ lấy iss, sub từ principal tin cậy
   ▼
External Identity Resolver
   │ lookup (iss, sub) trong bảng liên kết
   ▼
Local User + Membership + Quyền nghiệp vụ
```

Ứng dụng chỉ nhận **danh tính đã xác thực** sau khi xử lý chuẩn OIDC: kiểm tra signature/khóa tin cậy, `iss`, `aud` (client ID), thời hạn, và các ràng buộc `state`/`nonce` khi áp dụng. Spring Security thực hiện các bước của OIDC client theo cấu hình; các validation tùy chỉnh phải **bổ sung** yêu cầu bảo mật chứ không làm mất bước xác thực mặc định.

Không lấy `iss` từ một query parameter `?issuer=...`, không lấy `sub` từ HTTP header do client tự kiểm soát, không giải mã JWT rồi coi payload là tin cậy. Chủ thể chưa được xác minh chỉ là **dữ liệu không tin cậy**.

Trong hệ thống đa IdP, mỗi issuer phải nằm trong tập cấu hình được phép. Ngay cả khi hai IdP dùng chung tên nhà cung cấp hoặc cùng domain email, token của IdP A **không có quyền** nhận là IdP B.

**Đừng trộn vai trò token:** OIDC **ID token** dùng để chứng minh đăng nhập cho đúng OIDC client; một API bearer nên xác minh **access token dành cho chính API**. Luồng `client_credentials` có thể đại diện **ứng dụng** chứ không có người dùng cuối; đừng tự lấy `sub` từ mọi access token và ánh xạ thành tài khoản nhân viên.

## 7. Chọn khóa lưu trữ và thiết kế dữ liệu

Nên dùng hai lớp: khóa nội bộ bất biến và bảng liên kết danh tính bên ngoài.

```text
local_user
  id = user-9001       (do ứng dụng cấp)
  status = ACTIVE

external_identity
  issuer = https://idp-a.example.test
  subject = abcd-001
  user_id = user-9001

external_identity
  issuer = https://idp-b.example.test
  subject = pp-981
  user_id = user-9001  (chỉ sau liên kết được xác minh)
```

Điểm chính: **một local user có thể có nhiều external identity**, và mỗi cặp issuer/subject chỉ được gắn với **tối đa một** local user đang có hiệu lực. Không ép external subject trở thành primary key của toàn bộ dữ liệu nghiệp vụ. Bảng quan hệ dùng local user ID nên giữ nguyên khi IdP thay đổi.

Ví dụ schema PostgreSQL (minh họa cho ứng dụng do bạn kiểm soát):

```sql
CREATE TABLE local_user (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE external_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id BIGINT NOT NULL REFERENCES local_user(id),
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT external_identity_iss_sub_unique
        UNIQUE (issuer, subject),
    CONSTRAINT external_identity_nonempty
        CHECK (length(issuer) > 0 AND length(subject) > 0)
);

CREATE INDEX external_identity_local_user_idx
    ON external_identity(local_user_id);
```

Thiết kế bổ sung trong production:

- Giữ `issuer` **đúng giá trị đã được xác minh**; vì OIDC issuer và subject phân biệt chữ hoa/thường, tránh `LOWER(issuer)`, `LOWER(subject)` hoặc đối chiếu không phân biệt case.
- Định nghĩa chính sách khi vô hiệu hóa external identity, khóa user và thu hồi session; không xóa hàng loạt quan hệ/đơn hàng chỉ vì tài khoản IdP thay đổi.
- Với hệ thống nhiều tổ chức, dùng bảng `membership(local_user_id, tenant_id, ...)` để thể hiện quyền. **Tenant nghiệp vụ không thay thế issuer**. Khi một issuer chứa nhiều tenant logic, cần hiểu cách provider cấp `sub` và giới hạn account theo hợp đồng, không gộp tenant bằng suy luận.
- Tạo liên kết/đổi liên kết trong **transaction** và dựa vào unique constraint để ngăn race condition: hai request JIT provisioning đồng thời không được tạo hai người dùng cho một `(iss,sub)`.
- Hạn chế quyền đọc bảng mapping và audit các thao tác link/unlink. `iss`+`sub` có thể trở thành dữ liệu nhận diện cá nhân trong hệ thống và cần bảo vệ tương ứng.

**Quy tắc upsert:** nếu `(iss,sub)` đã tồn tại, tìm local user tương ứng và kiểm tra `status`; nếu chưa tồn tại, chỉ tạo user mới khi chính sách cho phép JIT provisioning hoặc khởi động **quy trình liên kết xác thực**. Tuyệt đối không tự nối với một local user có email trùng.

## 8. Spring Security lấy định danh OIDC ở đâu?

Với Spring Security OAuth 2.0 Login và scope `openid`, principal thường là `OidcUser`. Nó chứa **ID token** cùng các claim liên quan. `OidcUser` cung cấp `getIdToken()`, `getIssuer()`, `getSubject()`.

Một cấu hình OIDC Client tối thiểu (chỉ minh họa; để vận hành cần đăng ký client và redirect URI ở IdP):

Tệp `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: staff
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope: [openid, profile, email]
        provider:
          staff:
            issuer-uri: https://login.example.test/realms/staff
```

Thư viện cần thiết cho ví dụ Servlet: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`; cấu hình redirect URI trên IdP phải khớp redirect endpoint ứng dụng, thường `{baseUrl}/login/oauth2/code/{registrationId}`. Bảo vệ secret bằng biến môi trường/secret manager; HTTPS là yêu cầu môi trường thực.

Một lớp nhận principal từ Spring Security **sau khi đăng nhập OIDC thành công**:

Tệp `VerifiedIdentity.java` trong package ứng dụng, ví dụ `com.example.federation`:

```java
package com.example.federation;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component
public class VerifiedIdentity {

    public IdentityKey from(OidcUser principal) {
        // Chỉ gọi khi principal đến từ luồng OIDC đã xác thực.
        String issuer = principal.getIdToken().getIssuer().toString();
        String subject = principal.getIdToken().getSubject();
        return new IdentityKey(issuer, subject);
    }

    public record IdentityKey(String issuer, String subject) {}
}
```

Lớp trên là **mảnh tích hợp trong Spring Boot có dependencies**, không phải chương trình JDK chạy độc lập. Nó minh họa cách lấy hai claim từ **ID token**, rồi chuyển cho service lookup mapping. Ví dụ không tự truy vấn DB, không triển khai account linking và không thay cho việc cấu hình `SecurityFilterChain` với `oauth2Login()` hoặc cấu hình phù hợp do Spring Boot cung cấp.

**Tại sao không chỉ lấy `principal.getName()`?** Tên principal là biểu diễn cho giao diện framework và có thể thay bằng `user-name-attribute`/cấu hình tùy chỉnh. Dù mặc định OIDC thường hiển thị subject, không nên dùng nó một mình làm khóa liên kết, vì cần cả issuer. Tương tự, tên registration `staff` là nhãn cấu hình local, không phải issuer trong token.

Khi dùng SAML, principal không phải `OidcUser`: phải đọc SAML NameID có chính sách persistence và ngữ cảnh IdP/SP tương ứng. Khi dùng OAuth 2.0 Resource Server, request API thường có `JwtAuthenticationToken` hoặc principal tương đương; **không ép tất cả về một kiểu OIDC login principal**. Hợp đồng định danh của API phải được kiểm tra riêng theo token/issuer và grant type.

## 9. Ví dụ Java 17 độc lập: ba ca đồng nhất và phân biệt

Chương trình sau mô phỏng lookup sau khi đã xác thực token. Không có token thật, chữ ký, IdP hoặc Spring Security trong chương trình; mục đích là kiểm tra **quy tắc khóa**.

Tệp `ProviderScopedIdentityDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class ProviderScopedIdentityDemo {

    record IdentityKey(String issuer, String subject) {
        IdentityKey {
            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new IllegalArgumentException("Missing identity key");
            }
        }
    }

    public static void main(String[] args) {
        Map<IdentityKey, String> localUsers = new HashMap<>();

        IdentityKey companyA = new IdentityKey(
            "https://idp-a.example.test", "123"
        );
        IdentityKey companyB = new IdentityKey(
            "https://idp-b.example.test", "123"
        );

        localUsers.put(companyA, "user-A");
        localUsers.put(companyB, "user-B");

        // Cùng subject, khác issuer -> hai tài khoản riêng.
        System.out.println("A=" + localUsers.get(companyA));
        System.out.println("B=" + localUsers.get(companyB));
        System.out.println("sameExternalIdentity="
            + companyA.equals(companyB));

        // Cùng issuer+subject, email đổi -> vẫn lookup cùng tài khoản.
        String oldEmail = "mai.old@example.test";
        String newEmail = "mai.new@example.test";
        System.out.println("emailChanged="
            + !oldEmail.equals(newEmail));
        System.out.println("sameLocalUserAfterEmailChange="
            + "user-A".equals(localUsers.get(companyA)));

        // Subject pairwise khác -> không tự nối dựa vào email.
        IdentityKey otherSector = new IdentityKey(
            "https://idp-a.example.test", "pairwise-999"
        );
        System.out.println("otherSectorMapped="
            + localUsers.containsKey(otherSector));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac ProviderScopedIdentityDemo.java
java ProviderScopedIdentityDemo
```

Stdout chính xác:

```text
A=user-A
B=user-B
sameExternalIdentity=false
emailChanged=true
sameLocalUserAfterEmailChange=true
otherSectorMapped=false
```

Giải thích:

- `record` sinh `equals()`/`hashCode()` từ cả **issuer lẫn subject**, nên hai công ty cùng phát subject `123` vẫn tạo hai khóa khác nhau.
- Email không tham gia `IdentityKey`, nên thay email không làm mất ánh xạ khi cặp issuer/subject vẫn giữ nguyên.
- Pairwise subject mới chưa có mapping trả `false`. Hệ thống thật phải thực hiện linking có bằng chứng, không tự coi hai subject là cùng người.
- Không dùng `Map` trong RAM làm kho tài khoản production; persistence, unique constraint, transaction và audit là nhiệm vụ của service + database.

## 10. SAML 2.0: cùng tư tưởng, cách mang định danh khác

Trong federation bằng **SAML 2.0**, ứng dụng đóng vai Service Provider (SP), nhận assertion từ IdP. Định danh thường mang trong `<NameID>`; nhưng **không phải mọi NameID đều ổn định**.

| SAML NameID format | Đặc điểm | Khả năng dùng làm liên kết dài hạn |
| --- | --- | --- |
| `persistent` | Định danh opaque, lâu dài, thường theo quan hệ IdP–SP | Phù hợp khi đã xác nhận hợp đồng ổn định và qualifiers |
| `transient` | Định danh ngắn hạn, không dùng nhận diện dài hạn | Không |
| `emailAddress` | Dùng địa chỉ email như tên định danh | Rủi ro thay đổi/tái cấp; không mặc nhiên ổn định |
| `unspecified` | Không có cam kết chung về định dạng/persistence | Cần quy định rõ với IdP trước khi lưu |

Với SAML persistent NameID, ngoài chuỗi value cần xét **IdP entityID, NameQualifier/SPNameQualifier (nếu có), NameID Format** và hợp đồng với từng SP. Không chỉ lấy phần text của NameID rồi đem so sánh toàn hệ thống. Persistent NameID có thể **khác nhau giữa hai SP dù người dùng thực tế là một**. Đây là tình huống tương tự pairwise subject của OIDC.

Spring Security `saml2Login()` thực hiện xử lý chứng thực SAML theo cấu hình, nhưng **chính sách chọn ID dùng làm liên kết tài khoản** vẫn là quyết định tích hợp của ứng dụng/IdP. Khi IdP không bảo đảm persistent NameID, cần yêu cầu một thuộc tính bất biến khác có phạm vi và hợp đồng đáng tin, hoặc thiết kế một quy trình linking an toàn.

## 11. SCIM, LDAP và mã nhân viên không tự thay thế khóa OIDC

Tổ chức có thể dùng LDAP/Active Directory, hệ thống nhân sự (HR) hoặc **SCIM** để cấp phát tài khoản. Đây là các nguồn/luồng bổ sung, không tự biến mọi mã thành định danh federation đáng tin.

- **SCIM `id`** do SCIM service provider phát hành; ổn định và không tái cấp **trong không gian của SCIM service provider**.
- **SCIM `externalId`** do provisioning client cung cấp; có phạm vi provisioning domain, là thông tin mapping của luồng provisioning, không phải `sub` OIDC mặc định.
- **Mã nhân viên/LDAP DN/username** có thể được chuyển hệ thống, thay đổi tổ chức, đổi tên, tái sử dụng hoặc có scope riêng; không tự giả định bất biến.
- Khi onboarding qua SCIM rồi đăng nhập qua OIDC, phải định nghĩa mapping chính thức: SCIM resource nào ứng với `(iss,sub)` nào, bằng phép nối được xác thực ở provisioning/login, không chỉ trùng email.

Mẫu an toàn: SCIM tạo local user và ghi **liên kết đã được quản trị kiểm chứng**; OIDC login tra `(iss,sub)` để mở đúng tài khoản đó. Nếu mapping chưa có, áp dụng trạng thái pending hoặc kiểm tra người dùng thay vì đoán.

## 12. Liên kết nhiều IdP với cùng một người dùng

Có hai thao tác khác nhau:

1. **Nhận dạng external identity đã biết:** token hợp lệ với `(iss,sub)` đã có trong bảng ⇒ tìm local user.
2. **Gắn external identity mới với local user hiện hữu:** đây là **hành động nhạy cảm** có thể chuyển quyền truy cập dữ liệu, phải được ủy quyền và xác minh riêng.

Ví dụ người dùng đã có tài khoản qua IdP A muốn gắn IdP B:

```text
1. Đăng nhập tài khoản nội bộ qua IdP A, phiên hiện tại đủ mạnh.
2. Người dùng yêu cầu "Liên kết IdP B".
3. Ứng dụng khởi tạo luồng đăng nhập riêng tới B, chống CSRF/state.
4. Spring Security nhận kết quả B đã xác thực.
5. Kiểm tra khóa (iss_B, sub_B) chưa thuộc local user khác.
6. Thực hiện linking trong transaction + audit.
7. Chỉ từ lần sau mới cho B truy cập vào local user đã liên kết.
```

Có thể yêu cầu MFA/step-up, xác nhận quản trị hoặc quy trình tổ chức tùy mức rủi ro. Nếu B đã gắn với user khác, **từ chối xung đột và mở quy trình giải quyết**, không âm thầm chuyển liên kết. Nếu chỉ thấy cùng `email` hoặc `email_verified=true`, không được tự động merge.

Quy trình unlink cũng phải kiểm soát: tránh xóa phương thức đăng nhập cuối cùng khiến người dùng bị khóa, đồng thời xử lý session/token/quyền sau unlink.

## 13. Đổi issuer, di chuyển IdP và sáp nhập tổ chức

Các tình huống gây đứt liên kết:

- Thay URL/realm/tenant làm `iss` thay đổi.
- Đổi IdP A sang B: `sub` mới thuộc không gian định danh khác.
- Đổi public subject sang pairwise (hoặc đổi sector ID/redirect domain) làm `sub` mới.
- Chuyển tenant/khôi phục dữ liệu ở nhà cung cấp dẫn đến định danh được xuất/nhập khác nhau.
- Nối hai tổ chức có username/email trùng.

Không “sửa tự động” bằng cách tìm user có email giống. Một quy trình migration an toàn:

1. Lập danh sách **issuer cũ/mới** và kiểu subject; kiểm tra IdP có cung cấp bảng ánh xạ chính thức hay không.
2. Chọn nguồn chứng minh liên kết: export có chữ ký/bằng chứng quản trị được kiểm soát, xác thực hai tài khoản hoặc cơ chế hợp nhất từ IdP.
3. Tạo mapping `old (iss,sub) -> local_user` và `new (iss,sub) -> same local_user` bằng transaction, kiểm tra uniqueness và xung đột.
4. Chạy thử trên tập nhỏ có kiểm toán; xử lý conflict bằng review, không tự merge hàng loạt.
5. Giữ history và khả năng rollback quyền liên kết; không làm mất owner ID của dữ liệu nghiệp vụ.
6. Chỉ ngừng issuer cũ khi có chính sách cutoff, xử lý session/token đã cấp và đường đăng nhập dự phòng.

Dùng `issuer` làm namespace của danh tính nghĩa là **thay issuer là sự kiện thay khóa liên kết**. Không chỉ đổi một giá trị cấu hình `issuer-uri` rồi kỳ vọng mọi user được nhận dạng như cũ.

Nếu ứng dụng tin một **identity broker** (ví dụ IdP trung gian A xác thực tiếp ở IdP B), ứng dụng nhận danh tính do **A phát hành**; chính A chịu trách nhiệm mapping người dùng B sang subject của A. Không lưu `sub` của B từ claim không có hợp đồng rồi bỏ qua `iss` của token mà ứng dụng thực sự tin cậy.

## 14. Quan hệ giữa nhận dạng và phân quyền

Khóa `(iss,sub)` giải quyết câu hỏi **“là tài khoản nào?”**, không trả lời **“được làm gì?”**.

Sau khi có local user, ứng dụng phải xem xét:

- Trạng thái tài khoản: ACTIVE, SUSPENDED, DEPROVISIONED.
- Tenant/organization membership hiện hành.
- Vai trò, quyền cụ thể trên tài nguyên và điều kiện nghiệp vụ.
- Bảo đảm không đọc nhầm dữ liệu tenant khác chỉ vì cùng `sub` hoặc cùng nhóm.
- Policy khi đổi IdP: quyền cũ có được giữ hay phải phê duyệt lại?

Một IdP có thể phát `groups=["finance"]`, nhưng ứng dụng vẫn phải quyết định nhóm đó được ánh xạ thành authority/role nào và có quyền trên bản ghi nào. Danh tính bền vững là **điều kiện nền** cho phân quyền chính xác, không phải giấy phép truy cập mọi dữ liệu.

## 15. Ma trận kiểm thử quan trọng

| Ca kiểm thử | Đầu vào | Kết quả đúng |
| --- | --- | --- |
| Đăng nhập lại cùng người | Cùng `iss`, cùng `sub`, email giữ nguyên | Nhận đúng local user cũ |
| Email đổi | Cùng `iss`, cùng `sub`, email mới | Nhận đúng local user cũ; cập nhật email theo chính sách |
| Username đổi | Cùng `iss`, cùng `sub`, username mới | Nhận đúng local user cũ |
| Hai IdP trùng subject | `iss_A`, `iss_B`, cùng `sub=123` | Hai external identities khác nhau |
| Issuer khác path | `/realms/a` và `/realms/b` trên cùng host | Không tự gộp |
| Token giả/issuer lạ | Payload có `sub` trùng user đang tồn tại | Từ chối trước lookup nếu token không hợp lệ/không tin issuer |
| ID token sai audience | Issuer và subject đúng nhưng token cấp cho client khác | OIDC client phải từ chối |
| Subject pairwise mới | Cùng IdP, `sub` khác do sector | Không tự gộp, cần linking |
| Nhiều lần link song song | Cùng external identity vào hai tài khoản | Unique constraint bảo đảm không gắn đôi |
| Email đã tái cấp | Người mới có email trùng người cũ nhưng khác `sub` | Không cấp quyền tài khoản cũ |
| IdP A đổi sang B | `iss` và có thể `sub` đều đổi | Không tự match; dùng migration xác minh |
| Người dùng bị khóa nội bộ | Token vẫn hợp lệ, `(iss,sub)` đã biết | Ứng dụng từ chối theo trạng thái local user |
| API client credentials | Token đại diện ứng dụng, không có end-user | Không ánh xạ bừa thành local user |
| SAML transient NameID | NameID đổi theo phiên | Không dùng làm khóa user vĩnh viễn |
| SCIM externalId trùng từ provisioning domain khác | Cùng text `externalId` | Phân biệt theo domain và chính sách mapping |

Khi tích hợp, nên có test end-to-end chạy với **hai issuer khác nhau**; chỉ mock một issuer dễ bỏ sót collision. Có test ngắt quãng trong migration/linking để phát hiện race condition và kiểm tra log audit trước/sau.

## 16. Lỗi thường gặp và cách tránh

1. **Khóa bảng chỉ bằng `sub`:** hai IdP có thể phát cùng subject ⇒ thêm `issuer` vào khóa/unique constraint.
2. **Tự nối user bằng email:** email đổi hoặc tái cấp; `email_verified` cũng không bảo đảm đồng nhất với tài khoản nội bộ trước đó ⇒ xác thực liên kết riêng.
3. **Tin `preferred_username`, `name`, `registrationId` là ID vĩnh viễn:** đây không phải cặp issuer/subject ⇒ lấy claim định danh từ ID token đã xác minh.
4. **Lấy `iss`/ `sub` từ token chưa kiểm tra chữ ký hoặc từ HTTP header:** dữ liệu do client tự khai ⇒ chỉ xử lý sau thành công của bộ xác thực tin cậy.
5. **Chuẩn hóa subject bằng lowercase/trim:** subject là chuỗi phân biệt chữ hoa/thường; thay đổi có thể tạo collision ⇒ giữ chính xác giá trị đã được cấp.
6. **Bỏ path hoặc tenant khỏi issuer:** nhiều realm có issuer khác nhau ⇒ lưu đầy đủ issuer được xác minh.
7. **Xem một người luôn có một subject chung mọi client:** pairwise subject khác theo sector ⇒ thiết kế account linking theo hợp đồng.
8. **Dùng `jti` hoặc session ID làm user ID:** token và session đổi qua vòng đời ⇒ dùng issuer/subject.
9. **Dùng subject của ID token để thay thế bước phân quyền dữ liệu:** nhận dạng đúng vẫn không chứng minh quyền trên invoice/project ⇒ kiểm tra business authorization.
10. **Gộp tài khoản khi đổi IdP bằng script match email:** có thể làm lộ dữ liệu người khác ⇒ migration cần bằng chứng, kiểm toán, kiểm tra trùng/xung đột.
11. **Không ràng buộc DB uniqueness/transaction:** JIT provisioning đồng thời dễ tạo trùng user ⇒ unique constraint trên `(iss,sub)` và xử lý conflict.
12. **Dùng bất kỳ access token như bằng chứng người dùng:** token cho API/client khác hoặc client credentials có thể không đại diện end-user ⇒ kiểm tra token type, audience, grant và contract.

## 17. Checklist quyết định khi triển khai

Trước khi cho một IdP liên kết đến ứng dụng, xác nhận:

- [ ] Issuer OIDC chính xác là gì? Có phân biệt realm/tenant/path không? Metadata/issuer được cấu hình như thế nào?
- [ ] Subject có phải public hay pairwise? Scope của pairwise/sector identifier là gì? Điều gì xảy ra khi đổi redirect URI hoặc client?
- [ ] `iss` và `sub` được lấy từ token/principal đã kiểm tra signature, audience, issuer, thời hạn và điều kiện luồng chưa?
- [ ] Bảng mapping có unique constraint `(issuer, subject)`; local user ID có độc lập với IdP không?
- [ ] Có cấm auto-link dựa trên email trùng, kể cả `email_verified=true`, và có quy trình link/unlink an toàn không?
- [ ] Hành vi khi subject/issuer thay đổi, người dùng bị khóa, mất quyền tenant hoặc đổi IdP đã được định nghĩa và kiểm thử chưa?
- [ ] Nếu dùng SAML/SCIM, thuộc tính nào có cam kết ổn định và **phạm vi nguồn phát hành** của thuộc tính đó là gì?
- [ ] Các dịch vụ nghiệp vụ còn kiểm tra trạng thái tài khoản, membership và quyền trên tài nguyên sau khi đã nhận dạng user không?

### Câu hỏi tự kiểm tra

**1. Cùng `sub=42`, một token từ `iss=A`, một từ `iss=B`. Có phải cùng người dùng?** Không; không thể kết luận như vậy. Đó là hai external identities khác nhau cho đến khi liên kết được xác minh.

**2. `email_verified=true` có đủ để tìm tài khoản theo email rồi gán quyền không?** Không; tín hiệu kiểm chứng email không thay thế bằng chứng rằng người đăng nhập hiện tại là chủ của local user cũ.

**3. Vì sao cùng IdP mà hai ứng dụng nhận hai `sub` khác nhau?** Có thể IdP dùng OIDC pairwise subject theo sector khác nhau. Cần hợp đồng/luồng liên kết nếu muốn một local user chung.

**4. Một user đổi email nhưng `iss` và `sub` giữ nguyên thì sao?** Vẫn lookup đúng mapping hiện tại; cập nhật thuộc tính email theo chính sách quản trị.

**5. Khi đổi issuer của IdP, có nên tự động đổi key mọi user bằng email không?** Không. Tạo mapping old/new có xác minh, xử lý conflict và audit.

**6. Spring Security tự quyết định subject nào thuộc cùng tài khoản nghiệp vụ không?** Không. Spring Security xử lý xác thực giao thức và tạo principal; ứng dụng quản lý bảng liên kết và quyết định truy cập.

## Tài liệu chuẩn để đối chiếu

- OpenID Connect Core 1.0, mục **2, 5.7 Claim Stability and Uniqueness, 8 Subject Identifier Types**: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security, OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security, Advanced OAuth 2.0 Login / OIDC User Service: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security, `OidcUser` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- OASIS SAML 2.0 Core, mục **2.2 Name Identifiers, 8.3.7 Persistent Identifier**: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- IETF RFC 7643 (SCIM Core Schema), mục `id`, `externalId`: https://datatracker.ietf.org/doc/html/rfc7643

**Ghi nhớ:** một subject chỉ có ý nghĩa trong không gian nhà phát hành và chính sách subject của nhà phát hành đó. Trong OIDC, **`(iss,sub)` đã được xác minh** là khóa liên kết bền vững; **local user** là danh tính do ứng dụng quản lý; mọi việc gộp, chuyển hoặc cấp quyền giữa các danh tính phải có bằng chứng và chính sách rõ ràng.