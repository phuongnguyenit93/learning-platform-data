# Giới hạn truyền mức độ xác thực, thuộc tính và quyền qua nhiều tầng liên kết

Trong một kiến trúc **OpenID Connect (OIDC) và môi giới danh tính**, người dùng có thể xác thực ở IdP của công ty, đi qua một hoặc nhiều **identity broker** rồi đăng nhập vào ứng dụng Java/Spring Security. Trên đường đi, mỗi tầng có thể chuyển đổi SAML assertion thành OIDC ID Token, đổi issuer/subject, làm mới token, chuẩn hóa nhóm người dùng, hoặc phát hành access token cho API. Những chuyển đổi này tạo thuận tiện, nhưng cũng tạo **ranh giới tin cậy**: mức xác thực, thuộc tính hồ sơ và quyền truy cập ở hệ thống A **không mặc nhiên có cùng ý nghĩa hoặc cùng phạm vi ở hệ thống B**.

Ví dụ, IdP upstream chỉ chứng minh người dùng đăng nhập bằng mật khẩu; broker downstream lại phát ID Token có `acr=urn:enterprise:mfa` dù không thực hiện thêm yếu tố. Một ứng dụng tài chính tin vào chuỗi này để duyệt giao dịch lớn thì đã **nâng mức bảo đảm không có căn cứ**. Hoặc IdP upstream gửi `groups=["admins"]`, broker sao chép thành `roles=["ADMIN"]` và ứng dụng tự tạo `ROLE_ADMIN`; kết quả là **leo thang đặc quyền qua ánh xạ claim**.

Bài học này trả lời năm câu hỏi:

1. **Mức độ xác thực** (`acr`, `amr`, `auth_time`, SAML `AuthnContext`) có thể được bảo toàn, giảm hoặc nâng một cách hợp lệ qua broker như thế nào?
2. **Thuộc tính danh tính** (`sub`, NameID, email, nhóm, phòng ban, tenant) có thể mất nguồn gốc, thời điểm hoặc ý nghĩa ở mỗi chặng ra sao?
3. **Quyền ứng dụng/API** khác gì với nhóm IdP, OAuth scope và token được broker phát hành?
4. Làm sao xây **trust contract**, chính sách chuyển đổi, **step-up** và **deny by default** cho một chuỗi federation nhiều tầng?
5. Spring Security và Java 17 có thể thực thi/kiểm thử các ranh giới đó như thế nào mà không bỏ xác minh OIDC/SAML mặc định?

**Nguyên tắc xuyên suốt:** không tuyên bố mức bảo đảm cao hơn bằng cách đổi tên claim; không “truyền nguyên” dữ liệu không có hợp đồng ngữ nghĩa; không tự cấp quyền từ upstream group hoặc JWT hợp lệ; **mỗi hop xác minh đầu vào, phát hành đầu ra theo chính sách riêng, và RP cuối kiểm tra admission/authorization độc lập**.

## 1. Mô hình kiến trúc: liên kết nhiều hop không phải một chuỗi tin cậy tự động

~~~text
                 TRUST HOP 1                TRUST HOP 2                TRUST HOP 3
+-----------+   SAML/OIDC     +-----------+  OIDC downstream +---------+ OIDC/API +--------+
| IdP gốc   | -------------->| Broker A  |----------------->|Broker B |--------->| RP/API |
| Nhân viên |                 | RP hoặc SP|                  | OP / AS |          | Portal |
+-----------+                 +-----------+                  +---------+          +--------+
    |                             |                               |                   |
    | SAML AuthnContext           | verify signature/conditions  | verify broker A   | verify B issuer,
    | hoặc OIDC acr/amr           | map identity+assurance        | map+mint tokens   | audience, time
    | auth_time, attributes       | issue new token              | choose claims     | local account,
    |                             |                               |                   | permissions
    +-----------------------------+-------------------------------+-------------------+
       "Có chữ ký ở từng hop" KHÔNG có nghĩa nội dung và quyền giữ nguyên ngữ nghĩa.
~~~

Mỗi quan hệ có **issuer**, **audience/client**, signing keys, claim schema, mục đích sử dụng, khả năng kiểm toán và chính sách riêng.

- Khi **IdP gốc → Broker A** là SAML, Broker A là **SAML Service Provider**: phải xác minh chữ ký, issuer, audience, destination/recipient, conditions, subject confirmation, `InResponseTo` và chống replay.
- Khi **Broker A → Broker B** là OIDC, Broker A là **OpenID Provider (OP)** cho Broker B: Broker B xác minh ID Token được phát **cho đúng client_id của mình**.
- Khi **Broker B → Portal** là OIDC, Broker B có thể phát **ID Token mới** với `iss` của B, `sub` theo quy tắc B và `aud` dành cho Portal.
- Portal **không nhận trực tiếp một bằng chứng có chữ ký của IdP gốc** nếu broker không cung cấp cơ chế provenance có thể kiểm chứng riêng. Portal tin **Broker B theo hợp đồng**, không tự suy rằng B và mọi hệ thống upstream có mức bảo đảm như nhau.

**Chữ ký chứng minh người phát biểu đã ký claim, không chứng minh claim được suy ra đúng từ upstream.** Một token của broker ký hợp lệ có thể vẫn có `acr` sai về nghiệp vụ nếu mapping/policy của broker cấu hình sai. RP phải xét cả cryptographic trust **và** semantic trust.

### 1.1. Bốn loại bằng chứng không được nhập làm một

| Bằng chứng hoặc quyết định | Câu hỏi | Thành phần thường chịu trách nhiệm |
| --- | --- | --- |
| **Authentication event** | Người dùng được xác thực bằng phương thức nào, lúc nào? | IdP/OP thực sự xác thực, hoặc broker có thực hiện step-up. |
| **Identity attributes** | Email, phòng ban, mã nhân sự, nhóm lấy từ đâu, còn mới và có đáng tin không? | Nguồn dữ liệu thuộc tính (IdP, HR, SCIM, directory) và broker mapping. |
| **Application admission** | Người dùng đã được cấp phép vào ứng dụng, chưa bị khóa/disable và thuộc tenant đúng chưa? | RP/ứng dụng cục bộ. |
| **Resource authorization** | Phiên này có được `approve:payment` cho giao dịch X không? | API/resource server và business policy. |

Một claim `amr=["pwd","otp"]` **không cấp quyền** `finance:approve`. Một claim `department="Finance"` cũng không chứng minh người dùng là approver được bổ nhiệm. Một access token có `scope=read` không nhất thiết cho phép đọc tài liệu thuộc mọi tenant.

## 2. Ba trục assurance: mức xác thực, định danh và bảo vệ federation

Trong kiến trúc liên kết, **mức bảo đảm** không phải một số duy nhất có thể cộng/trừ qua các broker. Có ít nhất ba chiều:

| Chiều | Cần chứng minh gì? | Ví dụ giới hạn |
| --- | --- | --- |
| **Authentication Assurance (AAL)** | Người dùng đã xác thực với chất lượng/authenticator đáp ứng chính sách nào? | Mật khẩu đơn lẻ không được gắn nhãn MFA chỉ nhờ chuyển từ SAML sang OIDC. |
| **Identity Assurance (IAL)** | Độ tin cậy khi chứng minh và gắn danh tính với một người có thật. | MFA tốt không tự chứng minh họ tên/pháp nhân đã được kiểm tra. |
| **Federation Assurance (FAL)** | Giao dịch federation bảo vệ assertion, audience, replay/injection và trust agreement tới mức nào? | Một login có MFA không tự bảo đảm token ở mọi hop chống injection/replay đúng yêu cầu. |

Các thuật ngữ **IAL/AAL/FAL** được phân biệt trong **NIST SP 800-63**. Chúng chỉ có thể được tuyên bố khi hệ thống đáp ứng đầy đủ quy tắc và trust agreement tương ứng; **không dịch máy móc `acr="mfa"` thành “NIST AAL2” hoặc “FAL2”**.

Ví dụ:

- IdP gốc xác thực bằng một authenticator phishing-resistant có thể tạo authentication event mạnh; nhưng Broker A xác minh một SAML assertion với cấu hình audience/correlation yếu thì federation hop đó vẫn có rủi ro khác.
- Người dùng đã được identity proofing tốt ở HR, nhưng lần xác thực gần nhất chỉ bằng password; IAL cao **không tự nâng** AAL.
- Broker phát token mới sau hai giờ mà không reauthenticate người dùng; `iat` token mới **không biến `auth_time` cũ thành hiện tại**.

Khi doanh nghiệp đặt yêu cầu “thanh toán cần MFA trong vòng 5 phút”, phải định nghĩa **mức phương thức, tính mới, nguồn tin và độ tin cậy trên từng hop**. Không thể kiểm tra chỉ một trường `acr` và bỏ các điều kiện còn lại.

## 3. OIDC: ý nghĩa chính xác của acr, amr, auth_time và các yêu cầu step-up

### 3.1. Các claim chính

| Claim OIDC | Ý nghĩa | Giới hạn khi qua broker |
| --- | --- | --- |
| **`acr`** | Authentication Context Class Reference: tên lớp/ngữ cảnh xác thực được OP tuyên bố đã thỏa. | Tên lớp **không có thang bậc toàn cục**; cần hợp đồng ý nghĩa, mapping và bằng chứng. |
| **`amr`** | Mảng Authentication Methods References mô tả phương thức đã dùng. | Có thể mất chi tiết do mapping; `["mfa"]` không chứng minh mọi yêu cầu phishing-resistant. |
| **`auth_time`** | Thời điểm **người dùng thực sự xác thực** (Unix seconds). | Không được thay bằng thời điểm broker phát hành token nếu broker chỉ dùng lại SSO session. |
| **`iat`** | Thời điểm **phát hành token**. | Token mới có `iat` mới vẫn có thể dựa trên `auth_time` cũ. |
| **`max_age`** (request) | Giới hạn tuổi của lần xác thực được yêu cầu. | Broker phải thực thi hoặc bảo đảm upstream thực thi; RP kiểm tra `auth_time`. |
| **`acr_values`** (request) | Danh sách lớp xác thực **mong muốn**, theo thứ tự ưu tiên. | Theo OIDC Core, đây là **yêu cầu tự nguyện (voluntary)**, không bảo đảm luôn đạt. |
| **`claims` requesting essential `acr`** | Yêu cầu claim `acr` bắt buộc với giá trị được chấp nhận khi OP hỗ trợ cơ chế này. | OP phải đáp ứng theo chuẩn nếu hỗ trợ; RP vẫn phải xác minh token và đánh giá policy. |
| **`prompt=login`** | Hướng dẫn OP yêu cầu người dùng đăng nhập lại. | **Không tự chứng minh MFA**; cần biết cách OP xử lý và kiểm tra claims trả về. |
| **`nonce`, `state`** | Liên kết transaction/token với request; chống substitution/CSRF. | Không phải thông tin về strength/MFA; vẫn cần qua broker. |

OIDC Core nói `acr` là string phụ thuộc ngữ nghĩa được các bên thỏa thuận, **không bắt buộc có** trong mọi ID Token. `amr` cũng có thể không có. Một value như `urn:corp:aal-high` chỉ có ý nghĩa khi **issuer được tin** và có định nghĩa policy cụ thể; không được coi chuỗi dài hơn hoặc tên “high” là bằng chứng cao hơn.

### 3.2. Ví dụ token cùng một người nhưng hai thời điểm

Lần xác thực thực sự của người dùng diễn ra lúc 08:00 UTC, trong khi broker phát token cho Portal lúc 09:30 UTC:

~~~json
{
  "iss": "https://broker.example.org",
  "sub": "pairwise-user-81",
  "aud": "portal-web",
  "iat": 1794043800,
  "exp": 1794044100,
  "auth_time": 1794038400,
  "acr": "urn:corp:password",
  "amr": ["pwd"]
}
~~~

Đây là **payload minh họa, không phải JWT có chữ ký**; timestamp chỉ minh họa trường và không được dùng làm test token thật. Trên một giao dịch thực, `auth_time` phải phản ánh event tương ứng theo hợp đồng OIDC, không sao chép `iat` chỉ để làm token “trông mới”.

Nếu giao dịch chuyển token qua 2 broker:

~~~text
IdP      xác thực lúc 08:00 UTC với password
Broker A xác minh lúc 09:20 UTC, issue token mới lúc 09:20
Broker B nhận token lúc 09:25 UTC, issue token mới lúc 09:30
Portal   nhận ID Token B lúc 09:30

Không có bước xác thực mới:
  thời điểm chứng thực gốc = 08:00 UTC
  thời điểm phát hành downstream = 09:30 UTC
  yêu cầu "MFA trong 5 phút" => KHÔNG ĐẠT
~~~

Nếu Broker B **thực sự tổ chức step-up** bằng một authenticator mới thuộc chính sách được công nhận, B có thể có một authentication event mới và claims tương ứng, nhưng phải **ghi nhận chính xác phương thức, subject binding và mức bảo đảm** của event đó. B không được nâng mức chỉ bằng câu lệnh `claims.put("acr","mfa")`.

### 3.3. Yêu cầu step-up từ RP xuống broker

Giả sử Portal yêu cầu MFA với lớp ngữ nghĩa đã thống nhất:

~~~text
GET https://broker.example.org/authorize?
    response_type=code
    &client_id=portal-web
    &scope=openid
    &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker
    &state=<opaque-state>
    &nonce=<opaque-nonce>
    &code_challenge=<S256-challenge>
    &code_challenge_method=S256
    &acr_values=urn%3Acorp%3Amfa
    &max_age=300
~~~

Các giá trị trong `<...>` chỉ là ký hiệu cho dữ liệu giao dịch bí mật/ngẫu nhiên, không phải URL đăng nhập có thể chạy. Client phải dùng **Authorization Code + PKCE**, lưu state/nonce/verifier theo transaction, kiểm tra redirect URI và các quy tắc OIDC thông thường.

**`acr_values` một mình là yêu cầu mong muốn.** Nếu Portal muốn một `acr` cụ thể trở thành điều kiện cứng, OIDC cho phép dùng `claims` request với `id_token.acr` có `essential=true` và `values`, khi OP hỗ trợ. Tuy vậy, RP vẫn cần **kiểm tra giá trị `acr` cuối cùng**, `auth_time`, issuer, audience, signature và thời hạn; không coi việc gửi request là bằng chứng hoàn thành step-up.

Ví dụ cấu trúc `claims`:

~~~json
{
  "id_token": {
    "acr": {
      "essential": true,
      "values": ["urn:corp:mfa"]
    },
    "auth_time": {
      "essential": true
    }
  }
}
~~~

Không trộn tùy ý `acr_values` và `claims.id_token.acr` với `values` trong cùng request rồi suy đoán kết quả; OIDC Core nêu hành vi kết hợp này có trường hợp **không được đặc tả**. Thiết kế phải chọn phương thức được OP/broker hỗ trợ và test đúng cấu hình.

### 3.4. Step-up là quyết định tại thời điểm sử dụng tài nguyên

Giả sử người dùng đã đăng nhập Portal để đọc dashboard, rồi bấm “Duyệt khoản chi”. Không nhất thiết yêu cầu MFA cho mọi trang, nhưng endpoint duyệt tiền phải bảo đảm:

1. **Đã xác thực danh tính** qua issuer/audience/nonce/signature đáng tin.
2. **Assurance thực tế đáp ứng lớp bắt buộc** theo trust contract.
3. **Authentication freshness** đáp ứng giới hạn ví dụ `now - auth_time <= 300 seconds`.
4. **Được cấp quyền nghiệp vụ** như `payments:approve` với hạn mức, trạng thái user và tenant chính xác.
5. **Chống replay và CSRF** ở giao dịch duyệt; không chỉ dựa vào `acr` để tự cho phép một yêu cầu POST.

Nếu token thiếu `auth_time` hoặc broker không thể xác nhận upstream MFA, ứng dụng có thể chuyển tới flow step-up hoặc từ chối. **Không mặc định “thiếu claim tức là phương thức mạnh nhất”**. Step-up không khắc phục được thiếu quyền: user có MFA vẫn không được duyệt tiền nếu không có `payments:approve`.

## 4. SAML 2.0 ở hop upstream: RequestedAuthnContext không phải giấy chứng nhận mức đã đạt

Trong môi trường broker nhận SAML upstream, một `AuthnRequest` có thể yêu cầu lớp xác thực bằng `RequestedAuthnContext`:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-701"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.org/saml/sso"
    ForceAuthn="true">
  <saml:Issuer>urn:example:sp:broker-a</saml:Issuer>
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef>urn:example:authn:mfa</saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

Đây là XML **rút gọn để học cấu trúc**, không phải request hoàn chỉnh/được ký theo một federation thực tế. Chuỗi `urn:example:authn:mfa` là **lớp riêng theo hợp đồng**, không phải một SAML standard class tự động được mọi IdP hiểu. `ForceAuthn="true"` yêu cầu IdP xác thực lại thay vì chỉ dựa vào phiên hiện tại theo profile; **không tự tạo MFA** nếu không yêu cầu và xác minh đúng lớp. Cả class ref và ForceAuthn phải được đối chiếu hành vi IdP thực tế.

SAML Core định nghĩa `RequestedAuthnContext` với `Comparison` như `exact`, `minimum`, `maximum`, `better` (giá trị mặc định là `exact`); cách so sánh phụ thuộc **ngữ nghĩa/quan hệ** giữa các authentication classes mà các bên hiểu. Không thể đoán một lớp “tốt hơn” bằng thứ tự chuỗi URI.

**Nguồn sự thật sau xác thực** là `AuthnStatement/AuthnContext` và các thông tin đã qua xác minh của assertion, không phải các tham số mà broker từng gửi trong AuthnRequest.

### 4.1. Những gì phải kiểm tra trước khi dịch SAML → OIDC

| Yếu tố SAML upstream | Broker cần xác minh/diễn giải | Đầu ra OIDC downstream |
| --- | --- | --- |
| `Issuer`, chữ ký và trust credential | Đúng IdP đã đăng ký cho giao dịch, signature trên đúng nội dung. | Broker mới có cơ sở ký ID Token của mình. |
| `AudienceRestriction` | Assertion dành cho **broker SP**, không phải Portal downstream. | Broker phát **aud mới là client_id Portal**. |
| `Destination`, bearer `Recipient`, `InResponseTo` | Khớp ACS và giao dịch SSO, chống assertion injection. | Không copy nguyên các giá trị này vào downstream token. |
| `Subject/NameID` | Subject theo format/qualifier và issuer; mapping tin cậy. | `sub` do broker cấp, có thể pairwise; không mặc định bằng NameID. |
| `AuthnStatement/AuthnContextClassRef` | Mức đã đạt theo contract riêng với IdP. | Map sang `acr` **nếu mapping được phê duyệt**. |
| `AuthnStatement@AuthnInstant` | Thời điểm xác thực được IdP công bố. | `auth_time` chỉ nếu phù hợp hợp đồng và nguồn được tin. |
| Authentication methods/profile khác | Không phải SAML nào cũng phát `amr` OIDC tương đương. | Không tự chế thêm `amr=["mfa"]` khi không đủ chứng cứ. |
| `Conditions/NotOnOrAfter` | Giới hạn dùng assertion SAML upstream. | Không sao chép thời hạn đó như tuổi phiên/token downstream. |

**Dịch giao thức không được tẩy dấu tính chất của upstream.** Nếu Broker A không có hợp đồng rằng `AuthnContextClassRef=X` mang nghĩa MFA chống phishing, Broker A chỉ được ghi nhận “upstream asserted class X”; không tự đổi X thành một lớp cao hơn do tên na ná. Nếu upstream không cung cấp context có thể kiểm tra, assurance downstream phải ở mức **unknown/baseline** theo policy hoặc yêu cầu step-up.

## 5. Mô hình “claim provenance”: thuộc tính đến từ đâu, lúc nào, với ý nghĩa gì?

Một hệ thống liên kết không chỉ chuyển tên trường. Mỗi claim nghiệp vụ có ít nhất **nguồn**, **ngữ nghĩa**, **đối tượng**, **phạm vi**, **thời điểm cập nhật** và **cách đã xác minh**.

Ví dụ cùng giá trị `department="Finance"` có thể đến từ:

- HR master data do nhân sự cập nhật, kiểm chứng và đồng bộ sang broker.
- `groups` của IdP được suy ra thành phòng ban qua mapping.
- `preferred_username` hoặc profile do người dùng tự chỉnh.
- Header `X-Department` do một proxy chưa được bảo vệ truyền qua.
- Cache 7 ngày trước của hệ thống bị ngưng đồng bộ.

Những nguồn này **không tương đương** cho việc cấp quyền phê duyệt tài chính.

### 5.1. Bảng kiểm chất lượng thuộc tính

| Thuộc tính | Nguồn đáng tin theo mục đích | Giới hạn cần ghi nhận |
| --- | --- | --- |
| `sub` / subject | Issuer cụ thể, xác minh chữ ký/token và liên kết account. | **Chỉ duy nhất trong namespace issuer**, có thể pairwise giữa clients. |
| `email` | OP/IdP cung cấp, có thể kèm `email_verified`. | Có thể thay đổi/tái sử dụng, không phải khóa tài khoản hay bằng chứng quyền. |
| `name`, `preferred_username` | Directory/profile cho hiển thị. | Không dùng làm identity binding/permission. |
| `employee_id` | HR hoặc nguồn có hợp đồng tính duy nhất, trạng thái. | Có thể nhạy cảm, có thể thay đổi theo tổ chức/tenant. |
| `department` | HR/SCIM/directory có provenance và thời gian cập nhật. | Không mặc nhiên là entitlement. |
| `groups` | Danh mục nhóm đã kiểm duyệt theo issuer/tenant. | Tên nhóm có thể trùng, thiếu hoặc stale; không tự đổi thành roles. |
| `tenant_id` | Mapping từ nguồn quản trị và danh tính đã liên kết. | Không tin query param/RelayState quyết định tenant. |
| `role`, `entitlement` | Quản trị/phê duyệt ứng dụng hoặc contract delegation rõ. | Phải có phạm vi app/resource và thời hạn hiệu lực. |
| `acr` / `amr` | Authentication event đã được bên có trách nhiệm xác minh. | Không suy ra từ email, group hay token signing algorithm. |
| `auth_time` | Event xác thực được OP/broker chứng thực theo contract. | Không thay bằng `iat` để giả tăng freshness. |

Nếu broker ghép claims từ nhiều nguồn, cần **ưu tiên nguồn và xung đột** được định nghĩa: ví dụ trạng thái tài khoản DISABLED của app thắng nhóm `active-users` do IdP gửi trễ. **Không lấy giá trị “có vẻ mạnh nhất”** từ nhiều claims rồi bỏ nguồn gốc, vì attacker có thể kiểm soát nguồn có độ tin cậy thấp hơn.

### 5.2. Envelope nội bộ có provenance, không phải JWT chuẩn

Một mô hình kiến trúc cho broker (đây là **schema minh họa**, không phải một claim OIDC chuẩn):

~~~json
{
  "effective_subject": "broker-user-42",
  "source_authentication": {
    "upstream_issuer": "urn:example:idp:employees",
    "upstream_subject_ref": "idp-subject-key-77",
    "upstream_protocol": "SAML2",
    "validated_at": "2026-11-07T03:00:00Z",
    "auth_time": "2026-11-07T02:58:00Z",
    "source_context": "urn:example:authn:password",
    "mapped_assurance": "urn:corp:password",
    "mapping_policy_version": "assurance-v7"
  },
  "attributes": {
    "department": {
      "value": "Finance",
      "source": "HR_DIRECTORY",
      "updated_at": "2026-11-06T08:00:00Z"
    }
  },
  "local_account_status": "ACTIVE"
}
~~~

Broker lưu envelope này **trong kho tin cậy/được kiểm soát** để quyết định claims downstream và audit. Không cần, cũng **không nên**, phát toàn bộ provenance hay source subject nhạy cảm vào ID Token cho mọi RP. Nếu doanh nghiệp cần RP kiểm tra provenance độc lập, phải thiết kế một **claim contract có chữ ký, audience, consent/minimization, key management và chuẩn hóa ngữ nghĩa**; không tưởng tượng rằng custom JSON tự đáng tin khi nằm trong token.

**Mỗi lần broker phát token** phải xác định dữ liệu nào được phép qua ranh giới. Thuộc tính stale, unknown hoặc không có quyền chia sẻ được **lược bỏ hoặc chuyển thành trạng thái “không xác định”**, không tự suy ra default có quyền.

## 6. Chuyển subject giữa nhiều broker: không nối tài khoản chỉ bằng email

Một subject ở SAML IdP có thể là `NameID` dạng persistent với qualifier; Broker A cấp `sub` của mình; Broker B lại cấp một `sub` pairwise cho Portal.

~~~text
SAML IdP        issuer = urn:example:idp:employees
                NameID = permanent-77 (scoped by IdP/SP)

Broker A OIDC   issuer = https://broker-a.example.org
                sub    = a-user-123

Broker B OIDC   issuer = https://broker-b.example.org
                sub    = pairwise-for-portal-9

Portal binding  (https://broker-b.example.org, pairwise-for-portal-9)
                -> local user-42
~~~

`sub` OIDC **không duy nhất toàn cầu**. Cặp **`iss` + `sub`** xác định subject trong quan hệ tin cậy đó. Nếu cùng email xuất hiện ở Broker A và B, không có nghĩa hai tài khoản phải hợp nhất. Nếu pairwise subject của Broker B thay đổi vì client/sector identifier thay đổi, Portal cần quy trình re-link đã được quản trị; không fallback sang `email` hoặc `preferred_username`.

**Nguy cơ confused deputy:** broker nhận assertion dành cho client A nhưng lại phát token cho client B vì route theo query hoặc `login_hint` không ràng buộc transaction. Phải pin client/registration/issuer/audience, bảo vệ `state`/`nonce`, kiểm tra `InResponseTo` khi upstream là SAML, không cho dữ liệu tự khai quyết định trust anchor.

## 7. Giới hạn truyền quyền: group, role, OAuth scope và API permission là bốn thứ khác nhau

| Dữ liệu | Ngữ nghĩa | Không được tự suy thành |
| --- | --- | --- |
| IdP `groups` | Thành viên một hoặc nhiều nhóm **trong IdP/tenant**. | `ROLE_ADMIN` trên mọi ứng dụng. |
| Broker `roles` | Vai trò do broker công bố theo chính sách/realm/client. | Quyền trên mọi tài nguyên nghiệp vụ ở RP. |
| OAuth `scope` | Quyền mà AS cấp cho **một access token** theo client, user, audience, consent, policy. | Bằng chứng user có vai trò nhân sự, hoặc API khác sẽ chấp nhận. |
| App `GrantedAuthority` | Authority mà Spring Security đưa vào `Authentication` của ứng dụng. | Quyền vượt tenant, ownership và tài nguyên cụ thể. |
| `permissions`/entitlements của ứng dụng | Quyền được phê duyệt cho **app/resource/action/tenant**. | Assurance/MFA, identity proofing hoặc quyền ở ứng dụng khác. |
| OAuth token-exchange `act` | Mô tả actor/delegation trong ngữ cảnh token exchange (nếu được dùng). | Thay thế xác thực subject hoặc tự động giao quyền rộng hơn. |

Một group `finance-admin` tại IdP-X không nhất thiết giống `finance-admin` tại IdP-Y. Nếu broker xóa namespace rồi ánh xạ cả hai thành `ROLE_FINANCE_ADMIN`, một tenant có thể vô tình đạt quyền tenant khác.

### 7.1. Mẫu ánh xạ quyền có kiểm soát

Ví dụ **bản đồ entitlement nghiệp vụ**:

~~~text
(trustedIssuer = IdP-X,
 tenant = tenant-A,
 groupId = 6f4a-...,
 approvedMapping = v12)
     -> đề xuất role app:finance-viewer

LocalAppPolicy:
  localAccount.status == ACTIVE
  localAccount.tenant == tenant-A
  localAccount.entitlements contains payments:approve
  transaction.amount <= approvedLimit
  effectiveAssurance >= requiredAssurance
  authenticationAge <= requiredAge
  => ALLOW approval

Nếu một điều kiện fail => DENY hoặc STEP-UP theo policy.
~~~

Group upstream chỉ là **tín hiệu** có thể hỗ trợ cấp role nếu hợp đồng cho phép; quyết định cuối có thể do admin/SCIM/HR và policy của ứng dụng. Với role nguy hiểm (quản trị người dùng, duyệt thanh toán), thường nên có **phê duyệt cục bộ/entitlement rõ** và quy trình thu hồi.

**Deny luôn có ưu tiên**: tài khoản cục bộ `LOCKED`, `DISABLED`, bị thu hồi license, không thuộc tenant hoặc permission bị revoke thì **không được mở lại** chỉ vì upstream token vẫn có group cũ.

### 7.2. Tránh nhầm audience giữa ID Token và Access Token

Giả sử Broker B phát ID Token cho Portal:

~~~json
{
  "iss": "https://broker-b.example.org",
  "sub": "pairwise-for-portal-9",
  "aud": "portal-web",
  "acr": "urn:corp:password",
  "auth_time": 1794038400
}
~~~

Còn Reports API yêu cầu access token:

~~~json
{
  "iss": "https://broker-b.example.org",
  "sub": "pairwise-for-api-9",
  "aud": "reports-api",
  "scope": "reports:read",
  "exp": 1794044100
}
~~~

Đây là **payload mô phỏng**, không phải JWT hợp lệ hay một bảo đảm mọi OP sẽ cấp `sub` khác nhau cho ID Token/access token. Nó minh họa **audience của mỗi token** và chính sách API. **Không truyền ID Token của Portal cho API**; resource server phải kiểm tra chữ ký, issuer, expiration, **audience**, scope/permission và tenant. Không copy access token upstream dành cho Broker A sang API downstream chỉ vì cả hai cùng được mã hóa JWT.

### 7.3. Delegation và OAuth Token Exchange

Khi Backend A gọi Backend B **thay mặt người dùng**, đó là **ủy quyền/delegation**, không chỉ OIDC login. **RFC 8693 OAuth 2.0 Token Exchange** mô tả việc một client yêu cầu security token khác, có thể dùng `subject_token`, `actor_token`, `audience`/`resource` và `scope` theo khả năng của AS. Các claim `act` và `may_act` có thể mô tả vai trò actor/ủy quyền trong các profile thích hợp.

Ví dụ:

~~~text
User -> Portal (OIDC Login)
Portal -> Authorization Server (token exchange, nếu được hỗ trợ)
      subject_token = token được AS tin
      requested audience = reports-api
      requested scope = reports:read
AS -> Portal: access token dành reports-api
Portal -> Reports API: Bearer access token
Reports API: check iss, aud, exp, scopes, tenant, resource
~~~

Việc token exchange thành công **không đồng nghĩa AS cho phép mọi scope**; chỉ những quyền được chính sách, chủ thể, client và consent cho phép mới được cấp. `act` thể hiện actor trong hệ thống hỗ trợ nó, **không phải bằng chứng step-up MFA**. Không trao quyền rộng hơn chỉ vì token mới do broker ký; nguyên tắc **least privilege và audience restriction** phải được áp dụng ở từng API.

## 8. Nguyên tắc bảo toàn/ngăn leo thang qua mỗi hop

### 8.1. Bất biến số 1: một hop không tự tăng assurance

Nếu hop upstream được chứng minh chỉ đáp ứng lớp `PASSWORD`, một bước **chuyển đổi token đơn thuần** không được phát `MFA` chỉ vì tên role/thuộc tính yêu cầu. Muốn tuyên bố mức mới cao hơn phải có **sự kiện xác thực bổ sung thực sự** và policy xác định nó đáp ứng điều kiện.

**Không có phép `max(acr_A, acr_B)` chung cho mọi issuer.** Nếu mapping không được cấu hình, kết quả phải là **UNKNOWN** hoặc mức baseline theo hợp đồng, không đoán `LOW < MEDIUM < HIGH` dựa vào chuỗi.

### 8.2. Bất biến số 2: freshness không tự mới khi re-issue token

Broker A và B có thể đổi `iat` mỗi lần phát token, nhưng khi không xác thực lại, **event `auth_time` không đổi về mặt bản chất**. Nếu có step-up hợp lệ và broker công bố auth_time mới, cần ghi rõ event mới đó và bằng chứng tại issuer/OP nào. Đừng vô tình dùng thời điểm phát refresh token làm thời điểm MFA.

### 8.3. Bất biến số 3: thuộc tính có provenance và mục đích sử dụng

Nếu downstream cần `department` cho giao diện, nguồn profile có thể đủ; nếu cần để duyệt thanh toán, phải dùng HR/entitlement source đáng tin, độ mới và quyền sở hữu. **Một chữ ký của broker trên claim đã copy không làm nguồn dữ liệu đầu tiên tự đáng tin**.

### 8.4. Bất biến số 4: quyền có namespace, scope và deny precedence

Role `admin` của Partner IdP không tự là `app:admin`; scope `read` của service A không cho service B; tenant A không có quyền tenant B. Quyền downstream phải được **cho phép tường minh** bởi mapping và local policy, không tự union tất cả nhóm/role từ các tầng.

### 8.5. Bất biến số 5: mỗi hop phát token cho đúng audience và kiểm tra giao dịch

Khi Broker A nhận SAML assertion dành **cho Broker A**, Portal không được dùng assertion đó trực tiếp. Khi Broker B phát ID Token, Portal phải xác minh `iss`, `aud`, signature/JWKS, expiration, nonce và state/transaction tương quan. Một token upstream dù hợp lệ vẫn **không có audience downstream**.

### 8.6. Bất biến số 6: chính sách phải biết trường hợp UNKNOWN

Không nên có fallback `missing acr -> treat as MFA`, `missing groups -> admin`, `userInfo unavailable -> assume active` hoặc `broker timeout -> accept last elevated token`. Các lỗi nguồn dữ liệu, claim không được định nghĩa, mapping không tồn tại hoặc stale vượt SLA cần dẫn đến **step-up, deny hoặc pending**, tùy yêu cầu nghiệp vụ; không fail-open.

## 9. Trust contract cho từng cặp IdP–Broker và Broker–RP

Một văn bản hợp đồng kỹ thuật tối thiểu nên bao gồm:

| Nhóm hợp đồng | Cần chỉ rõ |
| --- | --- |
| Định danh đối tác | Issuer/entityID chuẩn, client_id/audience, signing keys, metadata, allowed algorithms, rotation. |
| Authentication assurance | Danh sách SAML AuthnContext/ OIDC acr có ý nghĩa, mapping được duyệt, phương thức/amr, khi nào step-up. |
| Authentication freshness | `auth_time` được xác định như thế nào; SSO/reauth, clock skew, TTL, `max_age` và fail conditions. |
| Identity binding | `iss+sub`, SAML NameID + qualifiers, pairwise subject, xử lý đổi issuer/migration. |
| Claim provenance | Nguồn HR/directory/self-service, cách xác minh, độ mới, phiên bản schema, null/unknown. |
| Claim release/privacy | RP được nhận những claim nào, dùng làm gì, retention/consent và mã hóa nếu cần. |
| Authorization mapping | Group IDs/tenant namespace, local entitlements, deny precedence, ai phê duyệt quyền. |
| Session lifecycle | Thời hạn OP session/RP session, revocation, logout propagation, account disabled behavior. |
| Error/fallback | IdP unreachable, missing acr, stale attribute, invalid signature, mapping unknown → deny/step-up. |
| Vận hành và kiểm toán | Correlation IDs, policy version, audit/provenance, phát hiện sai lệch claim và key rotation. |

**Lưu ý:** ký token không thay **trust agreement**. Một ứng dụng có thể tin rằng Broker B đã kiểm tra upstream bằng chứng theo một hợp đồng; nếu không có hợp đồng/provenance, RP chỉ nên sử dụng chính những claim được B cam kết và **không tuyên bố đã kiểm chứng trực tiếp phương thức upstream**.

### 9.1. Bảng mapping assurance theo issuer

Ví dụ **policy nội bộ**:

| Verified upstream issuer | Claimed upstream context | Effective class theo hợp đồng | Cho phép khi |
| --- | --- | --- | --- |
| `urn:example:idp:employee` | `urn:example:authn:password` | `PASSWORD` | Signature và SAML conditions hợp lệ; mapping phiên bản đã duyệt. |
| `urn:example:idp:employee` | `urn:example:authn:mfa` | `MFA` | IdP thực thi 2 yếu tố đúng contract và có audit. |
| `https://partner.example.org` | `urn:partner:otp` | `UNKNOWN` | Chưa có hợp đồng chứng minh tương đương MFA của ứng dụng. |
| `https://partner.example.org` | `urn:partner:phish-resistant` | `UNKNOWN` | Tên có vẻ cao nhưng không tự là bằng chứng. |
| Bất kỳ issuer khác | Bất kỳ `acr` | `UNKNOWN` | Không có trust relationship; từ chối claim bảo đảm cao. |
| Broker thực hiện step-up | Phương thức được chính broker xác minh | Mức do broker policy cho phép | Có event mới, time/subject binding, audit, đúng tiêu chuẩn. |

Không thể ép một phép so sánh `MFA` và `PHISHING_RESISTANT` bằng thứ tự chữ cái. Với yêu cầu phishing-resistant, phải **xác minh đúng loại authenticator và ngữ cảnh**, không chỉ có hai factors.

## 10. Chính sách Java 17 tự chạy: xác thực hợp lệ không đồng nghĩa assurance/quyền đủ

Chương trình sau mô phỏng **kết quả đã được các giao thức OIDC/SAML xác minh trước đó**, sau đó áp dụng mapping assurance **đúng issuer và giá trị context đã được đăng ký** và quyền tài nguyên cục bộ. Nó không tự parse/verify JWT, chữ ký XML hay cung cấp IdP; không thể dùng như một authentication provider thật.

Tệp **`FederationBoundaryPolicyDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Set;

public final class FederationBoundaryPolicyDemo {

    enum Assurance { UNKNOWN, PASSWORD, MFA }

    record Evidence(String trustedSourceIssuer,
                    String sourceContext,
                    Instant authenticationTime) {}

    record Account(boolean active,
                   String tenant,
                   Set<String> approvedPermissions) {}

    private static Assurance effectiveAssurance(Evidence evidence) {
        if (!evidence.trustedSourceIssuer().equals(
                "urn:example:idp:employee")) {
            return Assurance.UNKNOWN;
        }
        return switch (evidence.sourceContext()) {
            case "urn:example:authn:password" -> Assurance.PASSWORD;
            case "urn:example:authn:mfa" -> Assurance.MFA;
            default -> Assurance.UNKNOWN;
        };
    }

    static String decide(Evidence evidence,
                         Account account,
                         String requestedTenant,
                         String permission,
                         Assurance required,
                         Instant now,
                         Duration maxAuthenticationAge) {

        if (!account.active()) {
            return "ACCOUNT_BLOCKED";
        }
        if (!account.tenant().equals(requestedTenant)) {
            return "TENANT_DENIED";
        }
        if (!account.approvedPermissions().contains(permission)) {
            return "PERMISSION_DENIED";
        }

        Assurance level = effectiveAssurance(evidence);
        if (level == Assurance.UNKNOWN) {
            return "ASSURANCE_UNVERIFIED";
        }
        if (level.ordinal() < required.ordinal()) {
            return "STEP_UP_REQUIRED";
        }

        if (evidence.authenticationTime() == null
                || evidence.authenticationTime().isAfter(now)
                || Duration.between(evidence.authenticationTime(), now)
                           .compareTo(maxAuthenticationAge) > 0) {
            return "REAUTH_REQUIRED";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Duration freshness = Duration.ofMinutes(5);

        Evidence mfaFresh = new Evidence(
                "urn:example:idp:employee",
                "urn:example:authn:mfa", now.minusSeconds(60));
        Evidence password = new Evidence(
                "urn:example:idp:employee",
                "urn:example:authn:password", now.minusSeconds(60));
        Evidence mfaStale = new Evidence(
                "urn:example:idp:employee",
                "urn:example:authn:mfa", now.minusSeconds(600));
        Evidence unknownIssuer = new Evidence(
                "urn:example:idp:partner",
                "urn:example:authn:mfa", now.minusSeconds(60));

        Account approved = new Account(true, "tenant-A",
                Set.of("payments:approve"));
        Account blocked = new Account(false, "tenant-A",
                Set.of("payments:approve"));
        Account noPermission = new Account(true, "tenant-A",
                Set.of("reports:read"));

        System.out.println(decide(mfaFresh, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(password, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaStale, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaFresh, blocked, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaFresh, noPermission, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(unknownIssuer, approved, "tenant-A",
                "payments:approve", Assurance.MFA, now, freshness));
        System.out.println(decide(mfaFresh, approved, "tenant-B",
                "payments:approve", Assurance.MFA, now, freshness));
    }
}
~~~

Chạy bằng Java 17:

~~~bash
javac FederationBoundaryPolicyDemo.java
java FederationBoundaryPolicyDemo
~~~

**Stdout chính xác:**

~~~text
ALLOW
STEP_UP_REQUIRED
REAUTH_REQUIRED
ACCOUNT_BLOCKED
PERMISSION_DENIED
ASSURANCE_UNVERIFIED
TENANT_DENIED
~~~

Giải thích:

1. MFA theo hợp đồng, mới 60 giây, tài khoản ACTIVE, có đúng permission và tenant → `ALLOW`.
2. Chỉ có password dù token ký hợp lệ → `STEP_UP_REQUIRED`.
3. MFA cũ 600 giây trong khi giới hạn 300 giây → `REAUTH_REQUIRED`.
4. Account bị khóa: local deny thắng mọi authentication claim.
5. Có MFA nhưng thiếu `payments:approve`: không cấp quyền nghiệp vụ.
6. Issuer khác dù claim text trùng lớp MFA: mapping **không đáng tin**, nên không suy ra MFA.
7. Quyền thuộc tenant A không cho phép duyệt giao dịch của tenant B.

**Giới hạn của demo:** `Assurance` enum chỉ có thang thứ tự **do ví dụ tự định nghĩa và contract chấp nhận**, **không phải thang bậc chuẩn toàn cầu cho mọi `acr`**. Trong hệ thống thật, `Evidence` phải được dựng từ **assertion/token đã được framework xác minh và provenance đã được broker kiểm soát**, không lấy trực tiếp từ request JSON/header. Cũng cần clock skew nhỏ có kiểm soát, chính sách reauthentication cho level mới, disabled account và hạn mức giao dịch, cùng resource ownership; demo không thay thế SAML/OIDC validation.

### 10.1. Các trường hợp code cố tình không cho phép

- Không xem `unknownIssuer` là MFA vì context chứa chữ `mfa`.
- Không so `acr` bằng `String.compareTo` hoặc regex `contains("high")`.
- Không dùng ngày `iat` phát token làm `authenticationTime`.
- Không đọc `groups` chưa được duyệt để tạo `approvedPermissions`.
- Không bỏ kiểm tra tenant hoặc local account disabled chỉ vì người dùng đã qua MFA.
- Không ghi `new Authentication(..., ROLE_ADMIN)` trực tiếp từ claim tự khai.

## 11. Tích hợp Spring Security OAuth2/OIDC: giữ framework validation, thêm policy đúng vị trí

Trong một ứng dụng **Spring Boot Servlet**, `oauth2Login()` giúp thực hiện Authorization Code/OIDC login và xử lý validation của ID Token theo registration/issuer. Ví dụ cấu hình `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          broker:
            issuer-uri: https://broker.example.org
~~~

Đây là cấu hình minh họa. OP thực phải có discovery/JWKS, client registration và redirect URI thật. Không đưa client secret vào code repo. Nếu ứng dụng yêu cầu PKCE S256, kiểm tra và bật theo `ClientRegistration.ClientSettings.requireProofKey` hoặc cấu hình phiên bản tương ứng; không mặc nhiên confidential client đã bật PKCE ở mọi bản Spring Security.

Tệp `src/main/java/example/portal/SecurityConfig.java`:

~~~java
package example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasAuthority("app:admin")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Mã này là một **phần của dự án Spring Boot có dependency `spring-boot-starter-oauth2-client`**, không phải class chạy với Java SE thuần. Cấu hình trên **chưa kiểm tra assurance/provenance/entitlement nghiệp vụ**; `oauth2Login` xác thực OIDC token chứ không tự áp dụng “MFA trong 5 phút để duyệt tiền”.

### 11.1. Điểm mở rộng sau OIDC authentication

Spring Security hỗ trợ:

- `oauth2Login(...userInfoEndpoint(...oidcUserService(...)))` với `OAuth2UserService<OidcUserRequest, OidcUser>`.
- `OidcUserService` mặc định có thể được ủy quyền để tải `OidcUser`, sau đó ứng dụng tra local identity/account status, chuyển đổi authorities theo policy.
- `GrantedAuthoritiesMapper` cho phép ánh xạ authorities khi hoàn tất login, nhưng không nên biến tất cả scopes hoặc IdP groups thành app roles.
- `@EnableMethodSecurity` và `@PreAuthorize`/authorization service giúp kiểm tra quyền cho từng phương thức/tài nguyên.

**Thứ tự cần giữ:** framework xác minh **ID Token signature, issuer, audience, expiry, nonce và giao dịch authorization** → admission bằng `iss+sub` và trạng thái local account → ánh xạ **approved authorities** → cấp session → authorization và **freshness/step-up** tại endpoint nhạy cảm.

Mẫu pseudocode **không phải Spring API cụ thể để copy vào project**:

~~~text
verifiedUser = springOidcUserService.loadUser(oidcUserRequest)
issuer  = verifiedUser.idToken.iss
subject = verifiedUser.idToken.sub
account = localIdentityBindingRepository.lookup(issuer, subject)

if account is missing, LOCKED or DISABLED:
    throw AuthenticationFailure

approvedAuthorities = accountEntitlements.forAppAndTenant()
effectiveAssurance = localContract.evaluateVerifiedBrokerClaims(
    issuer, acr, amr, auth_time, policyVersion)

authentication = principalWithApprovedAuthorities(
    verifiedUser, localAccountId, effectiveAssurance)

On sensitive endpoint:
    require account ACTIVE
    require permission and tenant/resource ownership
    require assurance policy and max authentication age
    else request step-up or deny
~~~

Nếu có custom `OidcUserService`, vẫn phải **ủy quyền cho implementation mặc định** và không bỏ logic xác thực ID Token, `UserInfo.sub` matching, state/nonce hoặc token validation. Nếu cần thực thi assurance ngay tại login, điểm kiểm tra phải nằm trước khi session authenticated được công bố; nếu chỉ cần step-up cho tác vụ nhạy cảm, kiểm tra lại tại resource/service boundary và **đảm bảo token/session sau step-up thực sự được cập nhật**.

### 11.2. Ví dụ method security và giới hạn của nó

~~~java
package example.portal;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    @PreAuthorize("hasAuthority('payments:approve')")
    public String approvePayment() {
        return "Accepted for further policy checks";
    }
}
~~~

Đây là mảnh code thuộc dự án Spring, cần bật `@EnableMethodSecurity`; **chỉ `hasAuthority` chưa đủ** để duyệt giao dịch tài chính. Service/controller còn phải kiểm tra **đúng tài khoản, tenant, hạn mức, đối tượng, mức assurance và auth_time thực tế**, đồng thời chống thao tác lặp lại, session logout/revocation và các ràng buộc nghiệp vụ. Ví dụ trả chuỗi `Accepted for further policy checks` nhằm nói rõ không thực hiện một lệnh chuyển tiền thật.

Nếu các claims được lấy từ ID Token qua broker, ứng dụng phải có **trust contract** với broker về cách tính assurance. **Spring Security không tự suy ra NIST AAL/FAL của IdP gốc** từ một ID Token do broker ký.

## 12. API Resource Server: chính sách phải theo token audience, không theo role UI

Trong ứng dụng nhiều tầng, một RP có thể gọi API khác bằng access token. API cần thực thi chính sách riêng:

~~~text
Portal (OIDC RP)
  user authenticated by Broker
  local account admitted
      |
      | access token for reports-api only
      v
Reports API (OAuth Resource Server)
  1. verify token issuer/signature/expiration
  2. verify audience == reports-api
  3. verify approved scope/entitlements
  4. verify tenant/owner/resource
  5. if action sensitive: verify assurance/freshness via trusted contract
  6. deny otherwise
~~~

Trong Spring Security Resource Server, cấu hình `oauth2ResourceServer(jwt)` xử lý JWT theo decoder/validator; cần **cấu hình audience validation** tương ứng token contract, không chỉ kiểm tra `iss`/signature rồi cho mọi API dùng chung token. Scope được Spring có thể ánh xạ thành authority dạng `SCOPE_...`, nhưng **scope không đương nhiên thay quyền nghiệp vụ/ownership**.

Khi resource server chỉ nhận token opaque, có thể dùng introspection theo AS đáng tin; không tự giả định tất cả access tokens đều là JWT. Nếu dùng token exchange, các yêu cầu mới phải bị **giới hạn theo subject, actor, client, audience, scope, tenant và chính sách**. Không chuyển tiếp ID Token như bearer token cho API.

## 13. Giới hạn quyền và claim khi có hai hay nhiều broker

Một chuỗi nhiều broker làm tăng khả năng:

- **Tăng sai assurance** vì một hop dịch `acr=X` thành `Y` mạnh hơn.
- **Mất provenance** vì broker sau chỉ thấy claim đã được broker trước ký.
- **Mất độ mới** vì `iat` mới nhưng `auth_time` cũ hoặc không được chuyển.
- **Mất tính duy nhất định danh** vì `sub` pairwise đổi, email được tái sử dụng.
- **Mở rộng quyền** vì mapping `group` → `role` → `scope` → `authority` tự động.
- **Mất scope** vì tenant A/B không được pin ở giao dịch hoặc cache.
- **Token confusion** vì ID Token/upstream access token đi tới API downstream sai audience.
- **Mất trạng thái revoke** vì group/SCIM/account status ở upstream đổi nhưng token downstream vẫn còn hạn.
- **Không thống nhất logout** vì OP/Broker/IdP/RP session sống độc lập.
- **Lộ dữ liệu** vì mỗi hop phát quá nhiều PII, groups, phương thức xác thực vào JWT/log.

Có thể hình dung **hợp đồng rủi ro theo từng hop**:

~~~text
IdP --> Broker A --> Broker B --> Portal --> API

Hop A:
  validate upstream issuer+signature+context
  map identity and attributes with provenance
  decide allowable assurance/claims

Hop B:
  validate Broker A issuer+audience+signature
  apply B-specific contract (cannot invent lost evidence)
  mint own token for Portal audience
  preserve trustworthy freshness or mark UNKNOWN

Portal:
  validate Broker B ID Token
  map iss+sub -> local account
  deny if locked/unprovisioned
  map only approved authorities

API:
  validate access token for its own audience
  enforce tenant/resource+scope+permission
  require step-up evidence for sensitive operations
~~~

**Broker sau không thể “khôi phục” bằng chứng đã mất chỉ bằng đổi chuỗi claim.** Nếu Broker A không truyền `auth_time` đáng tin mà Broker B cần yêu cầu freshness, B nên yêu cầu xác thực mới/thông tin từ nguồn được tin, hoặc báo không đáp ứng. Đừng âm thầm tự đặt `auth_time=now`.

### 13.1. Rủi ro stale attributes và deprovisioning

Người dùng rời công ty lúc 10:00, HR/SCIM cập nhật DISABLED, nhưng Broker A cache group “active” đến 11:00; Broker B phát access token dài hạn đến 17:00. Ngay cả khi ID Token hợp lệ theo signature, **quyền không còn phù hợp**.

Biện pháp:
1. Xác định **nguồn authority của trạng thái account** (HR/SCIM, local entitlement service).
2. Event-driven invalidation cùng TTL cache theo SLA thu hồi.
3. Resource server kiểm tra status/permission hiện hành cho thao tác nhạy cảm.
4. Session/JWT revocation, token introspection hoặc `securityVersion` theo hệ thống.
5. Khi upstream outage, không bật cache vô hạn để cho mọi quyền cũ còn hiệu lực.

SAML logout và OIDC logout **không tự bảo đảm mọi API token bị thu hồi**, đặc biệt với JWT stateless. Authentication assurance cũng phải được làm mới độc lập với thời hạn token/session.

## 14. Thiết kế data minimization: không chuyển mọi thuộc tính qua mọi hop

Trong federation, dữ liệu hồ sơ có thể tiết lộ nhiều hơn mục đích đăng nhập: số nhân viên, phòng ban, địa chỉ, giới tính, phương thức MFA, danh sách nhóm nội bộ. Không nên đưa tất cả vào ID Token downstream hoặc gửi tới tất cả ứng dụng chỉ vì broker truy cập được.

Một chính sách tốt:

| RP / API | Dữ liệu tối thiểu cần thiết | Không nên phát |
| --- | --- | --- |
| Portal dashboard | Opaque `sub`, tên hiển thị nếu được đồng ý, auth status. | Toàn bộ HR record, private groups, SAML assertion XML. |
| Ứng dụng chấm công | Stable subject binding, entitlement chấm công, trường được phê duyệt. | Groups quản trị hệ thống khác, access token API khác. |
| Ứng dụng tài chính | Account binding, tenant, policy-approved finance entitlement; assurance theo contract. | Số tài khoản cá nhân, dữ liệu nhân sự không liên quan. |
| Reports API | Access token đúng audience, scope/permission, tenant/ref và claim được chấp thuận. | ID Token Portal, upstream SAML assertion, refresh token. |
| Audit bảo mật | Correlation ID, issuer/ref đã kiểm tra, policy version, quyết định và timestamp. | Raw assertion/ID Token/NameID/email nếu không bắt buộc. |

OIDC `scope` và `claims` có thể yêu cầu thuộc tính nhưng release vẫn phải theo chính sách OP/broker; **việc RP yêu cầu claim không đồng nghĩa nó được đảm bảo phát ra**. Broker nên phát ít nhất có thể, cân nhắc `pairwise sub`, data retention, consent/lawful purpose và mã hóa khi cần.

**Khác biệt quan trọng:** “thuộc tính không được chuyển qua” không phải là “thuộc tính có giá trị false”. Nếu downstream cần department nhưng broker không phát, phải xử lý **UNKNOWN** và dùng nguồn khác được tin; không mặc định membership/role “đúng” hoặc “sai” khi chưa có hợp đồng.

## 15. Vận hành: logging, metrics và điều tra sai lệch assurance

Gợi ý những trường để lưu **trong log được bảo vệ**:

~~~text
event=FEDERATED_ASSURANCE_POLICY_EVALUATION
time_utc=2026-11-07T03:00:00Z
transaction_ref=txn-7a31
downstream_issuer=https://broker-b.example.org
upstream_source_ref=idp-contract-employee
mapping_policy_version=assurance-v7
requested_class=urn:corp:mfa
effective_class=urn:corp:password
authentication_age_seconds=420
decision=STEP_UP_REQUIRED
local_entitlement_policy_version=finance-v12
~~~

Đây là định dạng minh họa, không phải metric Spring Security có sẵn. Tránh đưa thông tin mật/PII và token thô vào log: `id_token`, `access_token`, refresh token, assertion XML, cookie, private key, email hay danh sách nhóm nội bộ. Dùng hashed refs và phân quyền đọc audit.

Metrics nên theo dõi: rate `assurance_missing`, `assurance_mismatch`, `freshness_reauth`, `step_up_success/failure`, `claim_mapping_unknown`, `issuer_audience_reject`, `entitlement_denied`, `broker_upstream_timeout`, `token_exchange_reject`. Quan sát ở từng hop để biết lỗi do upstream không phát claim, mapping sai, broker không chuyển, hay RP áp dụng policy mới.

### 15.1. Khi lỗi xảy ra ở broker, ứng dụng xử lý sao?

| Tình huống | Hành vi an toàn |
| --- | --- |
| Broker thiếu `acr` nhưng endpoint chỉ cần login baseline. | Cho login ở mức đủ cho baseline **nếu policy cho phép**, không gán MFA. |
| Broker thiếu `acr` ở thao tác yêu cầu MFA. | Step-up hoặc deny; không mặc định đã đạt. |
| `auth_time` không có khi cần max_age. | Step-up/re-auth hoặc deny; không dùng `iat` làm thay thế. |
| Upstream group trống hoặc source stale. | Không tự cấp role; dùng approved local entitlement và chính sách error. |
| Issuer/audience/signature không hợp lệ. | Từ chối xác thực, không chạy JIT provisioning. |
| Mapping context chưa có hợp đồng. | `UNKNOWN`, không nâng class theo tên tương tự. |
| IdP upstream không hỗ trợ mức được yêu cầu. | Thông báo không đáp ứng, chọn IdP khác được phép hoặc từ chối, không tự thêm claim. |
| Nguồn local account status không sẵn sàng. | Fail closed với thao tác yêu cầu quyền; báo lỗi vận hành thân thiện. |
| Claim UserInfo `sub` khác ID Token `sub`. | Từ chối dữ liệu UserInfo; điều tra token/OP. |
| Broker mất session SSO nhưng RP vẫn có session. | Thực thi local session/step-up policy; không suy ra IdP đã logout mọi nơi. |

## 16. Test matrix: chứng minh không nâng assurance, không tràn quyền

| Test case | Expected result |
| --- | --- |
| Upstream SAML class `password`, broker chỉ đổi sang OIDC. | Downstream không được nhận `MFA` nếu không có event mới. |
| Upstream đã MFA nhưng broker không có mapping chứng minh. | Effective assurance `UNKNOWN`/policy level thấp, không tự nâng. |
| Upstream MFA nhưng `auth_time` 30 phút trước; payment yêu cầu 5 phút. | Step-up/re-auth, không dựa vào `iat` token mới. |
| Broker tự phát token mới và đặt `iat=now`, không reauthenticate. | Freshness vẫn gắn authentication event cũ. |
| `acr_values` yêu cầu MFA nhưng response thiếu `acr`. | RP kiểm tra policy; không coi yêu cầu đã được đáp ứng. |
| `claims.id_token.acr` essential MFA nhưng OP không thể đáp ứng. | Authentication flow thất bại theo hợp đồng; RP không hạ cấp im lặng. |
| `amr=["pwd","otp"]` nhưng partner chưa cam kết semantics. | Không suy luận tự động phishing-resistant/AAL mức cụ thể. |
| SAML `ForceAuthn=true` nhưng `AuthnContext` vẫn yếu. | Không gán MFA; từ chối/step-up theo thực tế response. |
| Upstream issuer lạ có context text giống issuer tin cậy. | Từ chối mapping hoặc đánh dấu UNKNOWN. |
| ID Token upstream `aud=broker-a` gửi vào Portal. | Portal từ chối, không bỏ audience check. |
| Broker B ID Token sai `iss`, `aud`, signature hoặc nonce. | Portal từ chối trước account/role mapping. |
| Email giống nhau tại hai IdP, `iss+sub` khác. | Không tự merge account. |
| Email được tái sử dụng sau khi user cũ bị disable. | Không hồi sinh quyền cũ từ email. |
| Group tên `admin` từ IdP partner không được allowlist. | Không tạo `ROLE_ADMIN`. |
| Group hợp lệ tenant A nhưng yêu cầu tài nguyên tenant B. | Từ chối cross-tenant. |
| Local account LOCKED nhưng OIDC `acr=MFA` hợp lệ. | Từ chối admission; không tự mở khóa. |
| Token có `scope=reports:read` nhưng API `aud` khác. | Resource server từ chối. |
| Scope hợp lệ nhưng user không sở hữu report. | Backend authorization từ chối tài nguyên. |
| Broker phát token với `act` nhưng subject không có quyền yêu cầu. | Token exchange/resource operation từ chối. |
| Attribute HR stale vượt policy TTL. | Không dùng attribute làm căn cứ cấp quyền cao. |
| Downstream không nhận `department`. | `UNKNOWN`, không mặc định entitlement. |
| UserInfo `sub` khác ID Token `sub`. | Từ chối kết quả UserInfo. |
| Broker refresh token sau một giờ. | Không tự làm mới `auth_time` hoặc quyền bị revoke. |
| Broker A mất kết nối upstream trong step-up. | Fail closed, không tạo claim MFA giả. |
| Đổi policy mapping `assurance-v7` sang v8. | Audit/version rõ; test hồi quy cho đúng đối tác và lớp. |
| Logout/disable tài khoản local trong khi RP session còn sống. | Revocation/status checks chặn thao tác vượt SLA. |
| Cùng một giao dịch có callback trùng/replay. | Từ chối giao dịch lặp theo state/nonce/replay policy. |

**Kiểm thử thật** phải dùng IdP/OP test, thông điệp SAML/JWT được ký hợp lệ và cấu hình trust riêng. Unit test mapping Java phía trên chỉ chứng minh logic ra quyết định, **không** chứng minh chữ ký, audience, nonce, `InResponseTo` hoặc quy trình step-up được kiểm tra đầy đủ. Cần integration test qua tất cả broker hops, web session, API/resource server và nhiều node.

## 17. Những hiểu lầm nguy hiểm

1. **“Broker có thể đổi `acr=low` thành `acr=high` để phù hợp Portal.”** Không nếu không có bằng chứng event/contract đáp ứng lớp cao hơn.
2. **“`acr_values` đã gửi là có MFA.”** Không; RP phải kiểm tra `acr` đã nhận và semantics.
3. **“ID Token có `amr=mfa` tức là chắc chắn đạt NIST AAL2.”** Không; cần hợp đồng và đúng điều kiện tiêu chuẩn.
4. **“Chữ ký broker chứng minh upstream IdP thực sự có MFA.”** Chữ ký chứng minh broker phát claim, còn upstream provenance cần contract/đảm bảo vận hành.
5. **“Token được phát lúc 09:30 thì user cũng xác thực lúc 09:30.”** Sai; `iat` không phải `auth_time`.
6. **“`ForceAuthn` SAML tự khiến MFA.”** Sai; nó yêu cầu xác thực lại, lớp thực tế vẫn cần kiểm tra.
7. **“Tên nhóm `admin` ở mọi IdP có cùng quyền.”** Sai; phải namespace/mapping theo issuer/tenant/app.
8. **“Email có `email_verified=true` là khóa định danh an toàn toàn hệ thống.”** Sai; binding theo issuer + subject và migration có kiểm soát.
9. **“Nếu một claim bị thiếu, có thể lấy từ token lần trước vô hạn.”** Sai; stale cache/entitlement có SLA và fail policy.
10. **“OAuth scope có thể truyền nguyên sang mọi API.”** Sai; mỗi token/audience/resource server có chính sách khác.
11. **“ID Token cũng là JWT nên đưa vào API làm bearer được.”** Sai; ID Token dành RP, không thay access token.
12. **“Broker forward upstream ID Token cho Portal là đủ.”** Sai; `iss/aud` của upstream không dành Portal.
13. **“Role từ IdP có thể vượt khóa local account.”** Sai; local deny phải thắng.
14. **“MFA thành công đồng nghĩa có quyền duyệt tiền.”** Sai; quyền resource/tenant/limit độc lập.
15. **“Spring `oauth2Login` tự hiểu mọi mapping `acr` của mọi broker.”** Sai; framework xác thực OIDC, policy assurance là hợp đồng nghiệp vụ riêng.
16. **“Nhiều hop ký số liên tiếp thì chất lượng claim tự tăng.”** Sai; transformation cần provenance/semantic contract, không có tính cộng dồn assurance.
17. **“SAML NameID, broker subject và OIDC `sub` luôn giống nhau.”** Sai; mỗi issuer có namespace và pairwise mappings.
18. **“Refresh token mới đồng nghĩa đã step-up xác thực.”** Sai; refresh không tự tạo authentication event mới.
19. **“Khi broker lỗi có thể bỏ check để giữ uptime.”** Sai với điều kiện an toàn bắt buộc; cần fail closed có chủ đích.
20. **“Logout tại RP thu hồi mọi API token và upstream sessions.”** Sai; các vòng đời phiên/token khác nhau.

## 18. Checklist đưa vào production

1. Có danh sách từng **trust hop**, issuer, audience/client, khóa ký, metadata và policy của mỗi hop không?
2. Có tài liệu mapping **SAML AuthnContext ↔ OIDC acr/amr** theo **từng issuer** và ngữ nghĩa được phê duyệt không?
3. Có ghi nhận đúng **authentication event time** và giữ freshness qua token re-issuance không?
4. Khi RP yêu cầu mức cao, có dùng `acr_values`/essential claims phù hợp, `max_age` và **kiểm tra claim cuối** không?
5. Có cơ chế **step-up thực** khi upstream yếu, không tự gắn label MFA không?
6. Có phân biệt IAL, AAL, FAL và tránh tự nhận mức chuẩn chỉ từ tên `acr` không?
7. Có provenance và freshness cho attribute cần phân quyền, ưu tiên HR/SCIM/nguồn được phê duyệt không?
8. Có dùng **issuer+subject** để nối identity; không tự merge email, NameID sai namespace hoặc pairwise sub không?
9. Claim release có data minimization, consent/mục đích sử dụng, TTL/retention và kiểm soát PII không?
10. Có mapping role/group theo issuer/tenant/client cùng deny precedence và local entitlement service không?
11. Có kiểm tra local account `LOCKED/DISABLED`, tenant và resource authorization sau OIDC login không?
12. API có xác minh đúng access token audience/scope, không chấp nhận ID Token Portal không?
13. Nếu dùng token exchange, có kiểm soát subject/actor/scope/audience và không tăng quyền khi cấp token mới không?
14. Có cơ chế session/token revocation và làm mới quyền khi nguồn HR/SCIM thay đổi không?
15. Có test chính sách khi claim thiếu, stale, sai issuer, mapping chưa duyệt, broker failover/timeout không?
16. Có audit policy version, requested/effective assurance và lý do deny mà không log assertion/token/PII nhạy cảm không?
17. Có integration test full chain SAML → broker A → broker B → OIDC Portal → API không?
18. Có chủ sở hữu rõ cho mỗi định nghĩa claim và quy trình thay đổi contract an toàn không?

## 19. Câu hỏi tự kiểm

1. **Vì sao một broker có thể ký ID Token hợp lệ nhưng mức MFA vẫn sai?** — Chữ ký chỉ xác nhận broker phát token; semantic claim phải dựa trên bằng chứng upstream và policy đã được phê duyệt.
2. **`acr` và `amr` khác gì?** — `acr` nêu lớp/ngữ cảnh đã đạt; `amr` liệt kê phương thức, không tự xác định lớp chuẩn.
3. **`iat` và `auth_time` khác gì?** — Một bên là thời điểm phát token, một bên là thời điểm người dùng xác thực.
4. **Gửi `acr_values=urn:corp:mfa` có bảo đảm OP dùng MFA không?** — Không; yêu cầu đó là voluntary, RP phải kiểm tra kết quả.
5. **Khi `auth_time` thiếu mà cần “5 phút”, nên làm gì?** — Step-up/re-auth hoặc deny; không dùng `iat` làm thay thế.
6. **SAML `ForceAuthn=true` có đồng nghĩa người dùng đã qua MFA không?** — Không; chỉ yêu cầu xác thực lại theo profile, phải xem context thực tế.
7. **Vì sao Group `admin` upstream không đủ thành `ROLE_ADMIN` downstream?** — Khác namespace/app/tenant và cần explicit approved mapping/local entitlement.
8. **Token mới của Broker B có thể chấp nhận trực tiếp chữ ký Broker A không?** — Portal phải xác minh token **do B phát cho đúng audience**; không mặc định tin token upstream A.
9. **Khi `sub` khác giữa Portal và ứng dụng khác, có nhất thiết lỗi?** — Không; có thể là pairwise subject.
10. **MFA có thay local permission `payments:approve` không?** — Không; authentication assurance và authorization là hai điều kiện độc lập.
11. **Dùng access token của Portal để gọi Reports API cần gì?** — Token dành đúng API audience/scope, được API xác minh và resource policy cho phép.
12. **Khi broker không biết nguồn của thuộc tính `department`, có thể cấp quyền theo phòng ban không?** — Không nếu quyền đòi nguồn xác minh; xử lý UNKNOWN/deny theo policy.
13. **NIST FAL có đồng nghĩa AAL không?** — Không; FAL bảo vệ giao dịch federation, AAL nói về xác thực.
14. **Có thể cộng mức bảo đảm của hai token qua hai hop không?** — Không; cần hợp đồng riêng, chứng cứ event và mapping hợp lệ.
15. **Vì sao cần `policyVersion` trong audit?** — Để biết phiên/claim được đánh giá theo định nghĩa nào, hỗ trợ kiểm soát thay đổi và điều tra sự cố.

## Tài liệu tham khảo

- [OpenID Connect Core 1.0 — ID Token claims, acr/amr/auth_time, max_age, acr_values và essential acr](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0 — issuer, endpoints, signing keys](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OASIS SAML 2.0 Core — RequestedAuthnContext, AuthnContext, AuthnStatement và NameID](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML 2.0 Profiles — Web Browser SSO requirements](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [NIST SP 800-63-4 / SP 800-63C — Digital Identity Federation and Assertions, FAL](https://pages.nist.gov/800-63-4/sp800-63c.html)
- [RFC 8693 — OAuth 2.0 Token Exchange, actor/delegation](https://www.rfc-editor.org/rfc/rfc8693.html)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
- [Spring Security — OAuth2/OIDC Login Advanced Configuration, OidcUserService và GrantedAuthoritiesMapper](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
