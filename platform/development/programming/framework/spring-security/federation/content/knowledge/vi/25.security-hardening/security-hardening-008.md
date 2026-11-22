# Không bỏ kiểm tra chữ ký, audience, recipient hoặc thời gian để chữa lỗi cấu hình

## 1. Bài toán: login lỗi không có nghĩa validator sai

Khi triển khai **Spring Security - federation**, Service Provider (SP) nhận **SAML2 Response** từ Identity Provider (IdP), hoặc ứng dụng OIDC/JWT nhận token từ OpenID Provider/Authorization Server. Nhóm vận hành có thể gặp **signature invalid**, **audience mismatch**, **recipient/destination mismatch**, **assertion expired**, **InResponseTo mismatch** hoặc **JWT invalid audience**. Một cách “sửa nhanh” nguy hiểm là bỏ phép kiểm gây lỗi để người dùng đăng nhập được.

**Nguyên tắc: không bỏ kiểm tra chữ ký, audience, recipient, thời gian hoặc request correlation để che lỗi cấu hình.** Phải truy nguyên sai khác ở **metadata IdP/SP, certificate/verification key, EntityID, ACS URL, HTTPS/reverse proxy, token audience/client ID, NTP hoặc session repository** rồi sửa tại đúng nguồn.

Bài thuộc nhóm **Gia cố an toàn** của **Spring Security - federation**. Trọng tâm là SAML2 Web Browser SSO, đồng thời làm rõ phép kiểm tương đương trong OIDC và JWT API. Ví dụ dùng **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**. Mọi host/ID `example.org` chỉ là mô phỏng; login thật cần IdP và metadata/trust được vận hành.

### Mục tiêu

1. Giải thích chữ ký, trusted issuer, audience, recipient và thời gian là những điều kiện **độc lập**.
2. Phân biệt **SAML2 Issuer, AudienceRestriction, Destination, SubjectConfirmationData Recipient, InResponseTo, NotBefore, NotOnOrAfter**.
3. Nêu nguyên nhân thường gặp: **SP entity ID khác IdP Audience**, ACS internal khác HTTPS public, signing cert rollover, clock drift, mất AuthnRequest.
4. Biết vì sao **OIDC ID Token aud=client_id** nhưng **JWT access token aud=resource API**.
5. Dùng Spring Security/OpenSAML và NimbusJwtDecoder, **không viết validator tắt kiểm**.
6. Chạy Java 17 demo chứng minh chữ ký đúng vẫn có thể bị reject bởi audience/recipient/time.
7. Tổ chức negative tests và quy trình sửa config mà **vẫn fail closed**.

## 2. Các phép kiểm và rủi ro khi tắt

| Phép kiểm | Nó chứng minh | Nếu bỏ kiểm |
| --- | --- | --- |
| **Signature + trusted key** | Message/Assertion/Token được ký bởi key thuộc issuer đã tin, đúng dữ liệu được ký. | Giả mạo user/attributes, XML Signature Wrapping. |
| **Issuer** | Đúng IdP/OP/AS trong trust configuration. | Nhầm IdP, realm hoặc registration. |
| **Audience** | Token/Assertion phát cho đúng SP/Relying Party/API. | Token substitution từ ứng dụng A sang B. |
| **Recipient (SAML)** | Bearer Assertion được phép xuất trình tại endpoint nhận đúng. | Assertion bị đưa sang ACS/endpoint khác. |
| **Destination (SAML)** | Protocol Response được nhắm tới đúng endpoint. | Redirect Response tới endpoint không phù hợp. |
| **NotBefore/NotOnOrAfter, exp/nbf** | Trong cửa sổ thời gian cho phép. | Replay và dùng credential quá hạn/chưa có hiệu lực. |
| **InResponseTo, state, nonce** | Login response khớp request/browser flow tương ứng. | Login CSRF, request confusion, token replay. |
| **Replay + local authorization** | Không tái dùng bearer proof trái policy; user có quyền resource. | SSO replay hoặc privilege escalation. |

Chữ ký hợp lệ **không thay audience**. Audience đúng **không thay recipient**. Recipient đúng **không chứng minh Assertion chưa hết hạn**. Tất cả đúng vẫn cần local account, tenant/resource authorization, replay/ID policy và session security.

~~~text
Incoming protocol response
  |
  +-- valid signature anchored to trusted issuer key? -- NO -> REJECT
  +-- trusted issuer/registration? -------------------- NO -> REJECT
  +-- intended audience matches consumer? ------------ NO -> REJECT
  +-- valid SAML Recipient/Destination? --------------- NO -> REJECT
  +-- Conditions/SubjectConfirmation/time valid? ----- NO -> REJECT
  +-- correct request correlation/replay policy? ----- NO -> REJECT
  +-- local account/tenant/resource rights? ---------- NO -> DENY
  |
  +-- all required checks pass -> authenticated and authorized
~~~

**Fail closed** không đồng nghĩa hết người dùng được login: đó là tính chất cần có trong lúc hệ thống cấu hình sai, nhằm tránh phát Authentication có quyền cho thông điệp không hợp lệ. Không “tạm cho ROLE_USER” bằng cách đọc raw NameID/email chưa xác thực.

## 3. SAML2: phân biệt EntityID, Audience, ACS, Recipient, Destination

Ví dụ một SAML Service Provider có:

~~~text
IdP EntityID:
    https://idp.example.org/saml2

SP EntityID:
    https://sp.example.org/saml2/service-provider-metadata/corp

ACS endpoint:
    https://sp.example.org/login/saml2/sso/corp

Spring registrationId:
    corp

AuthnRequest ID:
    _REQ_42

SAML Response ID:
    _RESP_9001

SAML Assertion ID:
    _ASSERT_8001
~~~

**AudienceRestriction** của Assertion SAML thường chứa **SP EntityID**, không phải IdP EntityID, ACS hay registrationId. **SubjectConfirmationData Recipient** thường là **ACS URL** nơi bearer assertion được trình đến. **Response Destination** là thuộc tính ở protocol Response, trỏ endpoint nơi message được gửi theo SAML profile/binding. Recipient và Destination có thể bằng nhau nhưng **không phải một trường**.

**registrationId** là khóa cấu hình Spring dùng để tìm RelyingPartyRegistration. URL callback chứa `corp` không tự chứng minh issuer, không phải tenant authorization. Sau khi có registration ứng viên, provider vẫn phải kiểm trusted key/issuer/audience/recipient/time.

### Ví dụ Conditions

~~~xml
<saml:Conditions
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  NotBefore="2030-01-01T11:55:00Z"
  NotOnOrAfter="2030-01-01T12:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>https://sp.example.org/saml2/service-provider-metadata/corp</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

Đây là **XML fragment** để giải thích, không phải signed Assertion có thể login. Nếu IdP phát audience `https://sp.example.org/` nhưng SP config có EntityID dài như trên, response cần bị reject. **Sửa SP/IdP registration**, không remove AudienceRestriction validator.

SAML có thể có nhiều AudienceRestrictions và nhiều Audience trong một restriction; **OpenSAML** xử lý logic theo chuẩn, không tự viết `firstAudience.equals(...)` rồi bỏ các conditions khác.

### Ví dụ Recipient

~~~xml
<saml:SubjectConfirmation
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
    Recipient="https://sp.example.org/login/saml2/sso/corp"
    InResponseTo="_REQ_42"
    NotOnOrAfter="2030-01-01T12:05:00Z"/>
</saml:SubjectConfirmation>
~~~

Recipient gắn với **bearer subject confirmation**. Nó không phải SP EntityID. Nếu nó trỏ một ACS khác, không được thay bằng “đúng audience rồi thì đủ”.

### Ví dụ Destination của Response

~~~xml
<samlp:Response
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  ID="_RESP_9001"
  Version="2.0"
  IssueInstant="2030-01-01T12:00:00Z"
  InResponseTo="_REQ_42"
  Destination="https://sp.example.org/login/saml2/sso/corp">
  <!-- Chỉ là ví dụ thuộc tính, không phải signed Response hoàn chỉnh. -->
</samlp:Response>
~~~

Response Destination xác định endpoint được phép nhận protocol Response; bearer Recipient bảo vệ subject confirmation tại ACS. Sửa **IdP Reply URL/ACS và SP metadata**, không bỏ các phép so sánh.

## 4. Chữ ký SAML, XML Signature Wrapping và metadata trust

SAML sử dụng **XML Digital Signature**. IdP có thể ký Response, Assertion hoặc cả hai theo profile/trust contract. Không khẳng định mọi profile bắt buộc cả hai chữ ký; yêu cầu bảo mật là **dữ liệu được dùng cấp Authentication nằm trong phần chữ ký hợp lệ từ IdP được tin cậy**, và các điều kiện protocol được kiểm.

Các bước đúng:

1. Xác minh XML-DSig, Reference URI, signed IDs, transforms, canonicalization bằng **OpenSAML**, không parse/verify bằng code XML tùy tiện.
2. Dùng **IdP verification X509 credentials** từ trusted RelyingPartyRegistration/IdP metadata.
3. Kiểm issuer phù hợp **IdP EntityID** của registration đó.
4. Đọc principal/attributes **từ validated signed element**, không từ một Assertion khác do attacker chèn.
5. Chặn **XML Signature Wrapping** (signed Assertion A nhưng app lấy unsigned Assertion B), duplicate IDs và parser hazards.
6. Chỉ cho thuật toán, key strength, XML parser và certificate rotation theo security policy.
7. Không tin **KeyInfo X509Certificate do Response tự mang** trừ khi nó được kiểm neo vào trusted verification credentials.

**Base64 decode không phải signature validation.** XML parser đọc được NameID không có nghĩa IdP đã xác thực NameID ấy. Một IdP ký message cũng không tự có quyền cấp `ROLE_ADMIN`: Spring vẫn phải map local groups và tenant/resource permissions theo chính sách nội bộ.

### Khi IdP rotate signing certificate

Triệu chứng: login từ một thời điểm nhất định bắt đầu fail chữ ký; có thể chỉ lỗi trên một số nodes do cache metadata khác nhau.

**Quy trình an toàn:** xác minh IdP metadata qua kênh quản trị/tin cậy; kiểm issuer và cert mới; cập nhật RelyingPartyRegistration verification credentials; cho overlap old/new trong cửa sổ có kiểm soát; bảo đảm các SP nodes cùng trust config; chạy positive và negative signature tests. **Không** đặt `trustAll=true`, bỏ signature validator hoặc tự nhận certificate bất kỳ từ raw XML.

**TLS certificate, IdP SAML signing certificate, SP decryption certificate, SP AuthnRequest signing key** có vai trò khác nhau. Đừng sửa lỗi SAML signing bằng cách thay nhầm web TLS cert.

## 5. Audience mismatch thường do EntityID của SP không đồng bộ

Các nguyên nhân điển hình:

- IdP Audience = `https://sp.example.org/app`, nhưng Spring SP EntityID = `https://sp.example.org/saml2/service-provider-metadata/corp`.
- Chuyển HTTP → HTTPS, tên domain hoặc reverse proxy khiến SP metadata thay.
- Copy IdP app registration từ staging sang production, dùng chung entity ID sai.
- Đổi IdP realm, registrationId hoặc tenant nhưng lưu audience cũ.
- Multiple IdPs/SPs: Response có audience của `partner` nhưng callback tới `corp`.

**Hướng sửa:**

1. Xuất **SP metadata** từ cấu hình đang chạy; lấy `EntityDescriptor entityID`.
2. Đối chiếu AudienceRestriction do **trusted IdP** thực phát trong môi trường sandbox/log đã redact.
3. Cấu hình IdP Audience chính xác như **SP entityID** đã thống nhất.
4. Nếu cần stable EntityID, đặt explicit entityId và cùng giá trị trong IdP app registration.
5. Giữ audience validation; tuyệt đối không chấp nhận wildcard mọi SPs.

Cùng một IdP có thể phát tokens cho nhiều SPs; đây chính là lý do audience binding không được tắt.

## 6. Recipient/Destination mismatch thường do HTTPS reverse proxy

Một mô hình:

~~~text
Public browser / IdP POST:
  https://sp.example.org/login/saml2/sso/corp

TLS ingress:
  https://sp.example.org

Request tới Spring pod:
  http://spring-pod:8080/login/saml2/sso/corp

Nếu app nghĩ ACS là:
  http://spring-pod:8080/login/saml2/sso/corp

Nhưng IdP phát Recipient:
  https://sp.example.org/login/saml2/sso/corp
~~~

Validation đúng sẽ reject vì **recipient/destination được xác định theo external endpoint và trust contract**, không phải đường backend tự đoán.

**Sửa:**

- Xác minh exact public scheme/host/port/path/registrationId/ACS.
- Kiểm IdP Reply URL/ACS và SP metadata `AssertionConsumerService Location`.
- Đặt public canonical ACS trong RelyingPartyRegistration.
- Cấu hình forwarded headers ở trusted reverse proxy; Spring Boot có thể dùng **server.forward-headers-strategy: framework**.
- Proxy phải xóa/ghi đè `Forwarded`/`X-Forwarded-*` từ public clients để chống host-header poisoning.
- Nếu có nhiều context paths/tenants, quản lý đúng ACS binding và session/correlation.
- Tái tạo signed Response mới từ IdP sau khi sửa; **không sửa raw XML trên đường đi**.

**Không tắt Recipient/Destination**. Điều đó biến sai lệch cấu hình thành nguy cơ đưa bearer assertions đến endpoint khác.

## 7. Thời gian SAML: hai vùng hợp lệ phải được kiểm

| Trường | Ý nghĩa |
| --- | --- |
| **Conditions.NotBefore** | Assertion chưa dùng được trước thời điểm này (trừ bounded skew policy). |
| **Conditions.NotOnOrAfter** | Assertion không còn hợp lệ từ thời điểm này trở đi. |
| **SubjectConfirmationData.NotBefore** | Giới hạn sớm đối với bearer confirmation nếu có. |
| **SubjectConfirmationData.NotOnOrAfter** | Giới hạn cuối riêng của bearer confirmation. |
| **Response/Assertion IssueInstant** | Thời điểm phát hành; có thể được kiểm thêm theo freshness/profile. |
| **AuthnStatement.AuthnInstant** | Thời điểm IdP xác thực user, không nhất thiết là lúc Response được phát. |
| **SessionNotOnOrAfter** | Thời hạn phiên IdP được chỉ báo, không tự là thời hạn HttpSession Spring. |

Ví dụ **now=2030-01-01T12:00:00Z**, `NotBefore=11:55Z`, `NotOnOrAfter=12:05Z` thì trong window. **Tại đúng 12:05:00Z**, Assertion đã hết hạn: **NotOnOrAfter là exclusive bound**. Không viết custom check `now <= notOnOrAfter`.

Thời gian phải đồng bộ **UTC/NTP/Windows Time** trên IdP, SP, Kubernetes nodes và VMs. Một bounded clock skew nhỏ có thể hợp lý, tùy Spring/OpenSAML version/profile. **Không tăng skew lên nhiều giờ hay vô hạn**: tăng cửa sổ replay và che lỗi đồng hồ.

Nếu login chậm vì IdP yêu cầu MFA, đo latency và thỏa thuận token lifetime phù hợp với IdP admin. Không xóa NotBefore/NotOnOrAfter chỉ vì user thao tác chậm. Nếu timestamp bị encode sai timezone hoặc milliseconds-vs-seconds ở JWT, sửa phía phát hành/serialization.

## 8. InResponseTo, nonce, state và replay

### SP-initiated SAML

SP tạo **AuthnRequest ID**, lưu ở request repository/session; IdP trả `Response.InResponseTo` và/hoặc `SubjectConfirmationData.InResponseTo` theo profile. SP phải tương quan đúng request ID và session khởi tạo.

Nếu **InResponseTo mismatch** vì LB chuyển node, cookie SameSite/Secure sai, browser mở nhiều tabs hoặc session lost, hãy sửa request repository/cookie/shared session/ACS. **Không disable correlation** trên mọi request chỉ vì muốn login pass.

### IdP-initiated SAML

Unsolicited SAML Response có thể không có AuthnRequest để correlate. Nếu sản phẩm yêu cầu, dùng chính sách IdP-initiated **tường minh** với IdP allowlist, đúng registration, signature/issuer/audience/recipient/time và replay protections đầy đủ. Không biến tất cả SP-initiated requests thành “allow unsolicited”.

### Signed message vẫn có thể bị replay

Chữ ký xác nhận origin/integrity, **không chứng minh message chưa từng được gửi**. Cần kiểm assertion/response IDs, replay cache/one-time semantics, time window và request correlation theo profile. Kéo dài Assertion lifetime quá mức làm tăng cơ hội replay.

### OAuth2/OIDC

**state** ràng buộc authorization callback với browser session/CSRF; **nonce** ràng buộc ID Token với authentication request khi được dùng. Chúng khác SAML InResponseTo nhưng cùng bảo vệ khỏi response confusion/replay. Không tắt state/nonce khi gặp lỗi cookie/callback; sửa redirect URL/session và provider registration.

## 9. OIDC ID Token khác JWT Access Token

Trong OIDC:

- **ID Token `iss`** phải trùng trusted OpenID Provider issuer.
- **`aud` của ID Token** phải chứa **client_id** của Relying Party. Khi nhiều audiences, kiểm additional audiences và `azp` theo OIDC Core.
- **JWS signature** phải được kiểm bằng keys/algorithms từ trusted OP metadata/JWKS.
- **`exp`** không được quá hạn; `iat` và `auth_time` có thể phục vụ freshness policy; `nbf` nếu có phải được tôn trọng.
- **nonce** nếu client đã gửi thì phải được kiểm.
- **state** phải khớp OAuth2 request; redirect URI và PKCE phải tuân thủ flow/client policy.

Trong OAuth2 Resource Server, `aud` của **JWT access token** thường là **resource API identifier**, không mặc nhiên bằng OIDC client_id.

~~~text
ID Token for browser application:
  iss = https://login.example.org/realms/corp
  aud = web-client-123
  sub = alice-opaque

Access Token for reports API:
  iss = https://login.example.org/realms/corp
  aud = api://reports
  scope = reports.read
~~~

API không được nhận ID Token của web client chỉ vì `sub` và signature đúng. **Xin access token dành cho API**; không bỏ audience validator ở API.

**Decode Base64URL payload không phải verify JWT**. Không tin `alg=none`, `kid` không phải trust anchor, không lấy JWK từ URL do JWT header tự chỉ như `jku`/`x5u` chưa được trust. Khi IdP rotate JWKS, refresh key set từ trusted issuer metadata, không tắt signature.

## 10. Java 17 độc lập: chữ ký đúng vẫn phải bị từ chối khi audience sai

**FederationValidationDemo.java** dùng RSA-SHA256 thật để ký một **message mô phỏng**, sau đó kiểm issuer, audience, recipient, request ID và thời gian. Chỉ cần JDK 17.

**Giới hạn bắt buộc:** đây **không phải SAML XML-DSig hoặc JWT/JWS verifier**. `canonicalForDemo()` ghép fields bằng dấu `|` không bảo vệ khỏi XML canonicalization/string ambiguity; khóa sinh ngẫu nhiên trong demo không phải trusted IdP key. Trong production dùng OpenSAML/Spring Security/NimbusJwtDecoder.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;

public class FederationValidationDemo {
    record Envelope(String issuer, String audience, String recipient,
                    String inResponseTo, Instant notBefore,
                    Instant notOnOrAfter, String subject) {
        String canonicalForDemo() {
            return String.join("|", issuer, audience, recipient,
                inResponseTo, notBefore.toString(),
                notOnOrAfter.toString(), subject);
        }
    }

    record Policy(String issuer, String audience,
                  String recipient, String requestId) {}

    static byte[] sign(Envelope value, PrivateKey key)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(value.canonicalForDemo()
            .getBytes(StandardCharsets.UTF_8));
        return signer.sign();
    }

    static boolean verify(Envelope value, byte[] proof, PublicKey key)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(value.canonicalForDemo()
            .getBytes(StandardCharsets.UTF_8));
        return verifier.verify(proof);
    }

    static String check(Envelope value, byte[] proof, PublicKey key,
                        Policy p, Instant now)
            throws GeneralSecurityException {
        if (!verify(value, proof, key)) {
            return "REJECT SIGNATURE";
        }
        if (!p.issuer().equals(value.issuer())) {
            return "REJECT ISSUER";
        }
        if (!p.audience().equals(value.audience())) {
            return "REJECT AUDIENCE";
        }
        if (!p.recipient().equals(value.recipient())) {
            return "REJECT RECIPIENT";
        }
        if (!p.requestId().equals(value.inResponseTo())) {
            return "REJECT IN_RESPONSE_TO";
        }
        if (now.isBefore(value.notBefore())) {
            return "REJECT NOT_YET_VALID";
        }
        if (!now.isBefore(value.notOnOrAfter())) {
            return "REJECT EXPIRED";
        }
        return "ACCEPT";
    }

    static void show(String label, Envelope value, byte[] sig,
                     PublicKey key, Policy p, Instant now)
            throws GeneralSecurityException {
        System.out.println(label + ": "
            + check(value, sig, key, p, now));
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        Policy policy = new Policy(
            "https://idp.example.org/saml",
            "https://sp.example.org/metadata/corp",
            "https://sp.example.org/login/saml2/sso/corp",
            "_REQ_42");

        Instant now = Instant.parse("2030-01-01T12:00:00Z");
        Instant start = Instant.parse("2030-01-01T11:55:00Z");
        Instant end = Instant.parse("2030-01-01T12:05:00Z");

        Envelope good = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, end, "alice");
        byte[] goodProof = sign(good, pair.getPrivate());
        show("valid", good, goodProof, pair.getPublic(), policy, now);

        Envelope tampered = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, end, "mallory");
        show("tampered", tampered, goodProof,
            pair.getPublic(), policy, now);

        Envelope wrongIssuer = new Envelope("https://other.example.org",
            policy.audience(), policy.recipient(), policy.requestId(),
            start, end, "alice");
        show("wrong issuer", wrongIssuer,
            sign(wrongIssuer, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope wrongAudience = new Envelope(policy.issuer(),
            "https://other.example.org/metadata", policy.recipient(),
            policy.requestId(), start, end, "alice");
        show("wrong audience", wrongAudience,
            sign(wrongAudience, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope wrongRecipient = new Envelope(policy.issuer(),
            policy.audience(), "https://other.example.org/acs",
            policy.requestId(), start, end, "alice");
        show("wrong recipient", wrongRecipient,
            sign(wrongRecipient, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope wrongRequest = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), "_REQ_WRONG",
            start, end, "alice");
        show("wrong request", wrongRequest,
            sign(wrongRequest, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope future = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            Instant.parse("2030-01-01T12:01:00Z"), end, "alice");
        show("future", future, sign(future, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope expired = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, Instant.parse("2030-01-01T11:59:00Z"), "alice");
        show("expired", expired, sign(expired, pair.getPrivate()),
            pair.getPublic(), policy, now);

        Envelope boundary = new Envelope(policy.issuer(),
            policy.audience(), policy.recipient(), policy.requestId(),
            start, now, "alice");
        show("boundary", boundary,
            sign(boundary, pair.getPrivate()),
            pair.getPublic(), policy, now);

        show("no signature", good, new byte[0],
            pair.getPublic(), policy, now);
    }
}
~~~

Chạy:

~~~bash
javac FederationValidationDemo.java
java FederationValidationDemo
~~~

**stdout chính xác** (keypair mỗi lần khác nhau nhưng kết quả kiểm luôn giống):

~~~text
valid: ACCEPT
tampered: REJECT SIGNATURE
wrong issuer: REJECT ISSUER
wrong audience: REJECT AUDIENCE
wrong recipient: REJECT RECIPIENT
wrong request: REJECT IN_RESPONSE_TO
future: REJECT NOT_YET_VALID
expired: REJECT EXPIRED
boundary: REJECT EXPIRED
no signature: REJECT SIGNATURE
~~~

Đặc biệt: **wrong issuer/audience/recipient/request** đều được **ký lại hợp lệ bằng private key thử nghiệm**, chứng minh rằng chữ ký đúng vẫn không thể thay các policy checks. **NotOnOrAfter là exclusive**, nên `boundary` reject.

Không sử dụng đoạn demo này để verify real XML/JWT: nó chưa có signed-element/reference/canonicalization checks, trust anchoring, multiple AudienceRestrictions, replay cache, token type hay XML parser protections.

## 11. Spring Boot 3.3.5: cấu hình SAML2 SP có EntityID và ACS public

Mẫu sử dụng trusted IdP metadata, explicit public SP entity ID và ACS, cùng **Spring Security SAML2 provider mặc định**, không override validator. Cần IdP sandbox thật và trusted metadata mới chạy SAML end-to-end.

### pom.xml

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
  <artifactId>secure-saml-sp</artifactId>
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
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

### application.yml

~~~yaml
server:
  port: 8080
  # Chỉ khi proxy trusted quản lý Forwarded/X-Forwarded-*.
  forward-headers-strategy: framework

app:
  saml:
    idp-metadata: "${CORP_IDP_METADATA_URI}"
~~~

**CORP_IDP_METADATA_URI** phải là nguồn IdP metadata được phê duyệt, không phải URL do browser chọn. Có thể là file được quản trị hoặc trusted HTTPS endpoint, với kiểm integrity, cache refresh và key rollover.

### Main class

**src/main/java/com/example/samlguard/SamlGuardApplication.java**

~~~java
package com.example.samlguard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlGuardApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlGuardApplication.class, args);
    }
}
~~~

### SecurityConfig.java

**src/main/java/com/example/samlguard/SecurityConfig.java**

~~~java
package com.example.samlguard;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    RelyingPartyRegistrationRepository registrations(
            @Value("${app.saml.idp-metadata}") String metadata) {

        RelyingPartyRegistration corp =
            RelyingPartyRegistrations
                .fromMetadataLocation(metadata)
                .registrationId("corp")
                .entityId(
                    "https://sp.example.org/saml2/service-provider-metadata/corp")
                .assertionConsumerServiceLocation(
                    "https://sp.example.org/login/saml2/sso/corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Giải thích:**

- `RelyingPartyRegistrations.fromMetadataLocation()` lấy IdP EntityID, SSO endpoint và verification credentials từ trusted metadata.
- `.entityId(...)` xác định **SP audience** sẽ được IdP sử dụng.
- `.assertionConsumerServiceLocation(...)` cố định **public HTTPS ACS** cho Recipient/Destination.
- `.registrationId("corp")` là khóa cấu hình, không tự là tenant/issuer trust.
- `.saml2Login()` giữ Spring Security/OpenSAML signature/issuer/audience/recipient/time/correlation validations.
- `.saml2Metadata()` công bố metadata SP để IdP admin đối chiếu; không dùng nội dung metadata chưa được bảo vệ làm trust self-service.
- Nếu IdP đòi signed AuthnRequest hoặc encrypt Assertions, phải cấu hình SP signing/decryption credentials đúng policy, không tắt yêu cầu.
- Nếu có nhiều IdPs hoặc nhiều ACS paths, cần lựa chọn registration có kiểm soát, tuyệt đối không nhận issuer từ raw XML làm proof.
- `forward-headers-strategy` chỉ hợp lệ với trusted ingress đã strip public forwarded headers.

### Controller

**src/main/java/com/example/samlguard/HomeController.java**

~~~java
package com.example.samlguard;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HomeController {
    @GetMapping("/")
    public String home() {
        return "SAML2 SP ready";
    }

    @GetMapping("/private")
    public String privatePage(Authentication auth) {
        return "Authenticated: " + auth.getName();
    }
}
~~~

Chạy:

~~~bash
mvn spring-boot:run
~~~

Với IdP sandbox/trusted metadata/HTTPS callback đúng: GET / là public; GET /private kích hoạt SAML2 login; Spring validate signed SAMLResponse/Assertion, issuer, audience, recipient/time trước khi tạo Authentication. **Không có IdP/key/ACS thật thì không thể kết luận end-to-end login pass.**

**Lưu ý version:** Spring Security 6.3.x dùng OpenSAML4 provider; tài liệu Spring Security 7.x có OpenSAML5 APIs. Đừng paste custom validators từ version khác. Ví dụ cố ý **không override** response/assertion validators.

## 12. JWT Resource Server: giữ default issuer/time, THÊM audience

Resource API cần nhận **access token** phát cho đúng API. Với Spring Security 6.x, Resource Server có trusted issuer/JWKS validation và timestamps; để bắt buộc `aud=api://reports`, thêm validator **bằng cách ghép với defaults**.

Đây là cấu hình cho **một ứng dụng API riêng**, không phải code trong cùng SAML SP ở phần 11.

**Dependency fragments trong pom.xml API:**

~~~xml
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
  <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

**application.yml API:**

~~~yaml
app:
  jwt:
    issuer: "${TRUSTED_JWT_ISSUER}"
    audience: "api://reports"
~~~

**src/main/java/com/example/api/ApiSecurityConfig.java**

~~~java
package com.example.api;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.jwt.issuer}") String issuer,
            @Value("${app.jwt.audience}") String expectedAudience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "JWT audience does not include this API", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return decoder;
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Không dùng** `decoder.setJwtValidator(audienceValidator)` một mình: có thể ghi đè default issuer/exp/nbf validators. **DelegatingOAuth2TokenValidator** kết hợp kiểm audience với **JwtValidators.createDefaultWithIssuer**, giữ defaults. `NimbusJwtDecoder` xác minh JWS signature với keys từ trusted issuer metadata/JWKS; user-supplied JWT header không chọn trust anchor.

Nếu contract yêu cầu token profile/type cụ thể (ví dụ **RFC 9068**), bổ sung type/profile validation; ID Token của website không được tự dùng làm API access token chỉ vì signature hợp lệ.

### OIDC client registration là một cấu hình khác

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope:
              - openid
              - profile
        provider:
          corp:
            issuer-uri: "${OIDC_ISSUER_URI}"
~~~

Ở đây ID Token audience phải chứa **OIDC_CLIENT_ID**. Nếu không khớp, sửa OP app/client registration thay vì bỏ OIDC aud validation. Còn API audience là `api://reports`, không mặc nhiên giống client_id.

## 13. Bảng xử lý lỗi theo đúng lớp

| Hiện tượng | Nghi ngờ | Hành động đúng |
| --- | --- | --- |
| Signature invalid sau IdP rollout | Signing cert/key rotate hoặc stale metadata. | Refresh trusted verification credentials, kiểm IdP EntityID, rollout all nodes. |
| Audience invalid trên production | SP EntityID sai hoặc dùng metadata staging. | Đối chiếu SP metadata với IdP Audience đúng môi trường. |
| Recipient mismatch sau ingress migration | HTTPS public URL khác internal host/path. | Cấu hình canonical ACS và trusted forwarded headers. |
| Destination mismatch | IdP Reply URL khác ACS thực tế. | Sửa IdP app registration/binding, không bỏ Destination. |
| InResponseTo mismatch | AuthnRequest state mất do session/LB/cookie. | Fix request repository, SameSite, Secure, shared session. |
| NotBefore quá tương lai | Clock skew, IdP timestamp sai. | Đồng bộ NTP/UTC và bounded skew policy. |
| NotOnOrAfter đã hết | Callback chậm, TTL IdP ngắn, clock drift. | Đo flow và chỉnh IdP TTL hợp lý, giữ validator. |
| Unknown JWT kid | JWKS rollover, wrong issuer, cache stale. | Refresh trusted JWKS, kiểm issuer và key provenance. |
| JWT invalid audience | ID Token/web token được gửi vào API. | Xin access token đúng resource, giữ API audience. |
| OIDC issuer sai | Realm/issuer-uri sai. | Sửa client/provider metadata. |
| User có token valid nhưng thiếu quyền | Local RBAC/tenant membership. | Trả 403/deny, không thay audience để cấp role. |

**Đừng “thử bỏ từng validator xem có vào được không” trên hệ thống thật.** Dùng logs đã redact, trusted metadata và sandbox signed fixtures. Nếu muốn kiểm audience validator độc lập, phải tạo **token/Assertion được ký hợp lệ nhưng audience sai**; sửa XML sau ký sẽ bị signature validator chặn trước.

## 14. Ma trận negative tests bắt buộc

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | SAML signed Response/Assertion, issuer/audience/ACS/time hợp lệ | Pass authentication nếu local account được cho phép. |
| 2 | Thay principal sau ký | Signature invalid → reject. |
| 3 | XML có signed Assertion A và unsigned Assertion B giả | Không lấy B làm principal; reject wrapping. |
| 4 | XML KeyInfo chứa attacker cert | Không trust certificate ngoài metadata. |
| 5 | IdP rotate key nhưng SP chưa update trusted metadata | Fail closed, không skip signature. |
| 6 | Issuer của IdP khác registration | Reject. |
| 7 | Đúng issuer string nhưng key ký không trusted | Reject. |
| 8 | Signed AudienceRestriction trỏ SP khác | Reject. |
| 9 | Nhiều AudienceRestriction không thỏa | Reject theo SAML Conditions semantics. |
| 10 | Assertion staging đưa vào SP production | Reject audience/recipient. |
| 11 | Bearer Recipient sai ACS | Reject. |
| 12 | Response Destination sai ACS | Reject. |
| 13 | ACS đổi scheme HTTPS→HTTP | Reject đến khi sửa metadata/proxy. |
| 14 | Reverse proxy dùng sai host/port/path | Reject; sửa external canonical ACS. |
| 15 | InResponseTo khác saved request ID | Reject. |
| 16 | SP AuthnRequest session repository mất | Fail closed; sửa storage/HA. |
| 17 | Browser mở nhiều login tabs | Request IDs không bị nhầm. |
| 18 | IdP-initiated Response tại app không cho phép unsolicited | Reject. |
| 19 | IdP-initiated được cấp phép | Vẫn kiểm signature, aud, recipient, time, replay. |
| 20 | Conditions NotBefore future | Reject, trừ bounded skew hợp lệ. |
| 21 | Conditions NotOnOrAfter bằng now | Expired (exclusive). |
| 22 | SubjectConfirmationData expired nhưng Conditions còn | Reject. |
| 23 | Conditions expired nhưng SubjectConfirmation còn | Reject. |
| 24 | IdP/SP lệch giờ 15 phút | Không nới skew vô hạn; fix NTP. |
| 25 | Replay signed assertion/response ID | Reject theo replay policy. |
| 26 | OIDC ID Token signature invalid | Reject. |
| 27 | OIDC ID Token iss sai | Reject. |
| 28 | OIDC aud thiếu client_id RP | Reject. |
| 29 | OIDC aud có nhiều audiences, azp không thỏa | Reject. |
| 30 | OIDC nonce/state mismatch | Reject correlation. |
| 31 | OIDC ID Token exp đã qua | Reject. |
| 32 | OIDC auth_time không fresh khi yêu cầu max_age | Re-auth theo policy. |
| 33 | API nhận ID Token của browser app | Reject type/audience. |
| 34 | JWT access token aud sai nhưng chữ ký đúng | Reject. |
| 35 | JWT access token iss sai nhưng aud đúng | Reject. |
| 36 | JWT alg=none/invalid signature | Reject. |
| 37 | JWT jku chỉ tới attacker host | Không trust key URL tự khai. |
| 38 | Key rotate tại trusted issuer | Refresh JWKS có kiểm soát, vẫn verify. |
| 39 | JWT nbf future/exp expired | Reject. |
| 40 | Token valid nhưng user disabled | Local authorization deny. |
| 41 | Token valid nhưng tenant membership thiếu | 403, không cross-tenant. |
| 42 | Proxy nhận X-Forwarded-Host của public client | Test fail; strip/overwrite. |
| 43 | Custom audience validator bỏ issuer/time defaults | Test fail; không deploy. |
| 44 | Same SAML Assertion đến wrong registration | Reject trust/audience/recipient mismatch. |
| 45 | Logs chứa raw SAMLResponse/JWT/keys | Security QA fail; redact. |

## 15. Checklist xử lý và phát hành

**SAML2 trust**

- [ ] IdP EntityID, signing certificate/KeyDescriptor và trusted metadata chính xác.
- [ ] Không trust arbitrary KeyInfo từ message; không bỏ XML signature.
- [ ] SP EntityID khớp AudienceRestriction do IdP phát.
- [ ] ACS public HTTPS khớp Recipient và Destination.
- [ ] Conditions và SubjectConfirmationData time đều được kiểm.
- [ ] InResponseTo và replay protection đúng profile.
- [ ] IdP-initiated SSO nếu có được allowlist và ràng buộc riêng.
- [ ] Metadata/cert rotation có plan, overlap, rollback.

**OIDC/JWT**

- [ ] ID Token signature/issuer/aud(client_id)/exp/state/nonce được kiểm.
- [ ] API access token signature/issuer/aud(resource)/exp/nbf/type theo contract.
- [ ] JWKS chỉ đến từ trusted issuer; không accept alg none hoặc token header URL.
- [ ] Thêm custom validators bằng composition, không ghi đè defaults.

**Vận hành/authorization**

- [ ] SP/IdP/API time đồng bộ UTC/NTP; clock tolerance nhỏ có approval.
- [ ] Reverse proxy tin Forwarded headers chỉ từ trusted ingress.
- [ ] Tests signed wrong audience/recipient/time và replay đều reject.
- [ ] Log an toàn theo trace ID/reason code; không xuất raw tokens/PII/keys.
- [ ] Local account, roles, tenant và resource-level authorization hoạt động.
- [ ] Nếu positive login lỗi, sửa cấu hình; không xóa negative test expectations.

## 16. Câu hỏi ôn tập

**1. Chữ ký SAML hợp lệ có đủ để đăng nhập vào SP bất kỳ không?**  
Không. Audience, Recipient/Destination, Conditions, issuer, request correlation và local authorization vẫn phải đúng.

**2. Audience khác Recipient thế nào?**  
Audience thường là SP EntityID; Recipient là ACS endpoint nơi bearer Assertion được trình đến.

**3. Destination có thay Recipient được không?**  
Không. Destination thuộc Response; Recipient thuộc SubjectConfirmationData. Cả hai có semantics riêng dù thường cùng ACS.

**4. Vì sao không tắt Recipient khi Spring chạy sau HTTPS ingress?**  
Vì lỗi thường là canonical public ACS/proxy headers sai; sửa IdP/SP metadata và forwarding trust boundary.

**5. Tại đúng NotOnOrAfter, Assertion còn hợp lệ không?**  
Không. Thời điểm cuối là exclusive; cần từ chối nếu đã đạt giới hạn.

**6. Chứng thư nằm trong KeyInfo có đáng tin tự động không?**  
Không. Phải neo vào trusted IdP verification credentials.

**7. InResponseTo mismatch do LB thì sửa gì?**  
Sửa AuthnRequest repository, session cookie và HA; không bỏ correlation.

**8. OIDC ID Token audience phải là gì?**  
Phải chứa client_id của RP, với kiểm additional audiences/azp theo OIDC Core. API access token có audience khác.

**9. Vì sao test sửa Audience trên XML sau khi ký chưa kiểm riêng audience?**  
Vì signature sẽ invalid trước. Cần signed fixture mới có audience sai nhưng chữ ký hợp lệ.

**10. Làm sao thêm audience validator cho Spring JWT mà vẫn giữ issuer/exp/nbf?**  
Ghép `JwtValidators.createDefaultWithIssuer` cùng audience validator bằng `DelegatingOAuth2TokenValidator`.

**11. Có nên đặt skew = 24h khi IdP lệch đồng hồ?**  
Không. Đồng bộ NTP/UTC và dùng bounded tolerance nhỏ theo policy.

**12. Nếu protocol validation pass có tự cấp ROLE_ADMIN không?**  
Không. Cần local user/group, tenant/resource checks và least privilege.

## 17. Tài liệu chính thống

1. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AudienceRestriction, SubjectConfirmationData, Recipient, Conditions và NotOnOrAfter.
2. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO bearer profile.
3. [Spring Security 6.3 OpenSaml4AuthenticationProvider](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): provider trust/validation.
4. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, entityID, ACS, metadata.
5. [Spring Security Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response/assertion validation; kiểm API version.
6. [Spring Boot 3.3 Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): SAML2 SP configuration.
7. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token iss/aud/exp/nonce/azp.
8. [RFC 7519 JWT](https://www.rfc-editor.org/rfc/rfc7519): exp, nbf, iat, iss, aud.
9. [RFC 7515 JWS](https://www.rfc-editor.org/rfc/rfc7515): signature/algorithm.
10. [RFC 9068 OAuth2 JWT Access Token](https://www.rfc-editor.org/rfc/rfc9068): access token type/audience.
11. [Spring Security OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JwtDecoder và validation composition.
12. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): XML Signature Wrapping/trust/replay.
13. [OWASP JWT Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): signature validation và key trust.
14. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default và least privilege.

**Kết luận:** Federation an toàn cần **signature của trusted issuer, đúng audience, đúng recipient/destination, đúng thời gian, request correlation/replay checks và local authorization**. Khi login lỗi, giải quyết **metadata, keys, EntityID, ACS URL, reverse proxy, token client/resource ID, NTP hoặc session**, tuyệt đối không tắt bộ kiểm tra để che lỗi cấu hình.