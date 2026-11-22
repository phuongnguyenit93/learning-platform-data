# Chẩn đoán chữ ký không hợp lệ, không tìm thấy khóa và chứng thư đã đổi

## 1. Vấn đề cần giải quyết

Trong hệ thống Spring Security - federation, luồng SSO có thể hoạt động ổn định rồi đột nhiên lỗi khi Identity Provider (IdP) hoặc Authorization Server thay khóa ký. Những thông báo thường thấy:

- SAML Response hoặc Assertion: signature verification failed, cannot validate signature, no trusted signing credential.
- Xác thực OIDC ID Token/JWT access token: no matching JWK, unknown kid, invalid signature, unsupported algorithm.
- Một số pod login thành công, một số pod lỗi sau certificate rollover vì metadata/cache không đồng bộ.
- Endpoint lấy IdP metadata hoặc JWKS gặp HTTP 5xx, TLS error, timeout, malformed XML/JSON.
- Có người thấy chứng thư X.509 hết NotAfter rồi kết luận nhầm đó là JWT exp hoặc SAML NotOnOrAfter.
- SAML EncryptedAssertion không giải mã được hoặc IdP không chấp nhận signed AuthnRequest nhưng lỗi bị gọi chung là signature error.

Bài thuộc nhóm Quan sát và gỡ lỗi. Mục đích là chẩn đoán đúng tầng, có bằng chứng kiểm được, xử lý key/certificate rotation an toàn, không bỏ xác minh chữ ký hay tự tin certificate do message đưa tới. Phạm vi chính là Spring Security 6.x với SAML2 Service Provider, OIDC login và OAuth2 JWT Resource Server; ví dụ cấu hình dùng Spring Boot 3.3.5 và Java 17. Các hostname example.org, issuers và key identifiers là dữ liệu mô phỏng.

Sau bài học, người đọc phải phân biệt được:

1. Không tìm thấy khóa tin cậy để verify.
2. Có khóa tin cậy nhưng chữ ký không verify.
3. Có chữ ký hợp lệ nhưng issuer, audience, recipient, thời gian hoặc tenant không hợp lệ.
4. Chứng thư ký đã bị đổi hoặc đã hết thời hạn theo chính sách.
5. Không thể tải metadata/JWKS vì mạng, cache hoặc TLS.
6. SP không giải mã được Assertion vì decryption key sai.
7. IdP không verify được AuthnRequest vì SP signing key/cert sai.

Nguyên tắc bảo mật: fail closed. Không chuyển một SAMLResponse/JWT chưa được verify thành Authentication; không thêm một arbitrary public key vào trust set chỉ để login thành công.

## 2. Bản đồ các bước kiểm tra

### 2.1. Luồng SAML2 tại Service Provider

~~~text
Browser -> SP: yêu cầu tài nguyên protected
SP -> IdP: AuthnRequest (có thể được SP signing key ký)
IdP -> Browser: SAMLResponse có Response/Assertion ký theo profile
Browser -> SP: POST SAMLResponse tới ACS

Spring SAML2 authentication:
  1. Resolve RelyingPartyRegistration đúng issuer/context
  2. Deserialize và kiểm chữ ký XML được yêu cầu
  3. Chọn trusted IdP verification credentials
  4. Giải mã EncryptedAssertion nếu có bằng SP decryption credentials
  5. Kiểm Issuer, Destination, AudienceRestriction, Recipient
  6. Kiểm Conditions/SubjectConfirmationData times, InResponseTo
  7. Lấy principal từ signed/validated Assertion
  8. Áp dụng local account, groups, tenant và resource authorization
~~~

Thứ tự verify/decrypt có thể khác theo cấu trúc signed Response hay signed Assertion và Spring/OpenSAML version. Không viết custom XML parser để bỏ qua signed-element/reference rules; chỉ dùng kết quả Authentication từ provider đã xác thực đầy đủ.

### 2.2. Luồng JWT tại Relying Party/API

~~~text
JWT header: alg, kid, typ       -- dữ liệu chưa được tin cậy
JWT payload: iss, aud, exp...  -- dữ liệu chưa được tin cậy
JWT signature

Trusted issuer configured on server
  -> provider discovery / trusted jwks_uri
  -> fetch/cached JWKS public keys
  -> choose candidate by kid/kty/alg/use where appropriate
  -> verify JWS signature using trusted candidate
  -> verify iss/aud/exp/nbf, token type, nonce/state as relevant
  -> authenticated principal + app authorization
~~~

Chỉ Base64URL decode payload không có nghĩa chữ ký hợp lệ. JWT header kid là key identifier, không phải chứng minh trust. Không chấp nhận jku/x5u URL chỉ từ unverified token header để tải JWK bất kỳ.

## 3. Lỗi chọn khóa khác lỗi xác minh chữ ký

| Nhóm lỗi | Câu hỏi kiểm chứng | Một số nguyên nhân |
| --- | --- | --- |
| KEY_NOT_FOUND | Có public verification key được tin cậy phù hợp không? | Trusted metadata thiếu, JWT kid mới chưa có trong JWKS cache, nhầm issuer/registration, key type/alg không hợp. |
| SIGNATURE_INVALID | Dùng key đã chọn thì bytes được ký có verify không? | Wrong key, signed data bị sửa, SAML XML-DSig reference/canonicalization sai, JWT signature giả, kid reused với key bytes khác. |
| ISSUER_MISMATCH | Assertion/Token thực sự do issuer nào phát và registration nào được trust? | Nhầm tenant/realm, staging/prod, cross-IdP. |
| CLAIM_VALIDATION | Chữ ký pass nhưng audience/recipient/time có đúng không? | Assertion cho SP khác, API token cho resource khác, expired, wrong ACS. |
| METADATA_FETCH_FAILED | Nguồn public keys có lấy/parse được không? | DNS, network, TLS trust, 404/500, timeout, malformed XML/JSON. |
| CERT_POLICY | Certificate đã đổi/hết NotAfter/revoked theo quy định? | Rotation thiếu overlap, certificate inventory và metadata/trust policy không đồng bộ. |
| DECRYPT_FAILED | Có SP private decryption key tương ứng với ciphertext không? | IdP dùng encryption cert cũ, SP private key sai, unsupported encryption. |
| AUTHNREQUEST_SIGNING | IdP có tin public signing certificate của SP không? | IdP chưa cập nhật cert SP hoặc SP ký request với key sai. |

Những lỗi này có thể có thông báo giống nhau ở framework hoặc IdP. Error text không đủ để tự kết luận root cause. Cần kiểm issuer, expected registration, keyset version, signed element, thuật toán và timestamp của rollout.

### 3.1. Hai tình huống dễ nhầm

- Key mới đã được IdP sử dụng nhưng SP chưa nạp certificate mới: có thể thấy no verification credential, no matching key hoặc signature invalid tùy provider.
- JWKS có kid trùng JWT header nhưng public key thực là khóa cũ: key selector tìm ra candidate, signature vẫn fail; không phải cứ kid match là token trusted.

### 3.2. Những việc không được làm

- Không bật trustAll hoặc skipSignatureValidation.
- Không dùng KeyInfo certificate từ SAMLResponse làm trust anchor mới.
- Không fetch JWKS từ JWT jku/x5u của attacker.
- Không thêm tất cả issuers vào cùng trust store rồi chọn bất kỳ key verify được.
- Không tắt exp/nbf/audience/issuer khi cần tìm lỗi signature.
- Không nhận raw NameID/email/sub làm user trước khi framework xác minh.

## 4. SAML2: phân biệt certificate và private keys

| Chủ sở hữu | Loại khóa | Mục đích |
| --- | --- | --- |
| IdP | Signing private key | Ký Response/Assertion được gửi tới SP. |
| IdP | Signing public certificate | SP dùng để verify signature; nằm trong trusted asserting-party metadata/credentials. |
| SP | Signing private key | Ký AuthnRequest nếu IdP yêu cầu. |
| SP | Signing public certificate | IdP dùng để verify AuthnRequest. |
| SP | Decryption private key | SP giải mã EncryptedAssertion/EncryptedAttribute. |
| SP | Encryption public certificate | IdP dùng để encrypt Assertion cho SP. |
| TLS server | HTTPS certificate/private key | Bảo vệ transport/hostname, không thay SAML verification key. |

Ví dụ IdP metadata (chỉ là XML fragment; certificate bytes trong đây là ký hiệu minh họa, không phải cert thực):

~~~xml
<md:EntityDescriptor
  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
  xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
  entityID="https://idp.example.org/saml">
  <md:IDPSSODescriptor
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_PUBLIC_CERTIFICATE_ONLY</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Metadata thật có thể có nhiều KeyDescriptor, có hoặc không có use cụ thể. Provider/OpenSAML xử lý theo profile. Không lấy nhầm KeyDescriptor use=encryption để verify chữ ký. Không mặc định certificate đầu tiên trong XML là khóa active.

### 4.1. Trust phải được neo ở IdP đúng

RelyingPartyRegistration liên kết SP metadata với asserting-party metadata: IdP EntityID, SingleSignOnService, public verification credentials, SP EntityID/ACS và các credentials của SP. Nếu app có corp, partner, staging, production, mỗi registration phải có trust/policy riêng. Dùng certificate của partner để tin Response corp là lỗi cross-tenant.

KeyInfo trong XML Signature có thể mô tả candidate, nhưng thông tin đó do người gửi cung cấp; verification phải dựa trên trusted IdP credentials. Một XML Signature hợp lệ với một arbitrary certificate không đủ chứng minh message đến từ IdP.

### 4.2. Response ký hay Assertion ký?

Theo federation profile, IdP có thể ký Response, Assertion hoặc cả hai. Phải bảo đảm phần dữ liệu được dùng cấp principal thực sự nằm trong signed/validated elements. Không verify một signed Assertion A rồi đọc unsigned Assertion B: đó là bề mặt XML Signature Wrapping.

Việc xác minh XML-DSig liên quan SignedInfo, Reference URI, canonicalization, transforms và element IDs, không chỉ so một Base64 signature với XML string tự dựng. Dùng Spring Security/OpenSAML, không tự verify SAML bằng vài dòng java.security.Signature.

### 4.3. Signing certificate NotAfter không phải Token expiry

Một X.509 certificate có NotBefore/NotAfter. Chữ ký RSA/ECDSA có thể vẫn đúng về mặt toán học khi certificate đã quá NotAfter; việc có từ chối hay không còn phụ thuộc trust configuration, PKIX/certificate validity policy, profile và provider. Không mặc định Spring SAML luôn tự kiểm CA chain/NotAfter của mọi certificate trong metadata.

SAML Assertion còn có Conditions.NotOnOrAfter và SubjectConfirmationData.NotOnOrAfter; JWT có exp/nbf. Đây là các thời hạn của credential/message, độc lập với X509 certificate dates. Không chữa certificate rollover bằng cách bỏ assertion time check.

### 4.4. Signing, encryption và TLS không được tráo

- SP decrypt fail: điều tra SP private decryption key và public encryption certificate đã cấu hình bên IdP.
- IdP reject SP AuthnRequest signature: điều tra SP signing private key và SP public certificate mà IdP đang tin.
- SP reject incoming Response signature: điều tra IdP signing public certificate/trusted metadata.
- Metadata HTTPS TLS fail: điều tra TLS CA chain, hostname và network; không tự coi lỗi là XML signature fail.

## 5. Chẩn đoán certificate public bằng OpenSSL/keytool

Trong môi trường vận hành được cấp quyền, tải metadata qua trusted IdP URL (hostname chỉ là ví dụ):

~~~bash
curl --fail --show-error --silent --max-time 15 https://idp.example.org/saml/metadata -o idp-metadata.xml
~~~

HTTP 200 + HTTPS không tự đủ để chứng minh metadata an toàn; nguồn IdP phải được quản trị, và metadata signature nếu có phải được verify bằng metadata trust anchor đã provision độc lập. Tuyệt đối không lấy metadata URL do browser hoặc unverified Assertion tự cung cấp.

Trích X509Certificate public từ metadata bằng XML-aware parser, wrap đúng PEM BEGIN/END, lưu thành idp-signing.pem. Không cần private key. Kiểm:

~~~bash
openssl x509 -in idp-signing.pem -noout -subject -issuer -serial -dates -fingerprint -sha256
openssl x509 -in idp-signing.pem -noout -text
openssl x509 -in idp-signing.pem -checkend 604800 -noout
keytool -printcert -file idp-signing.pem -v
~~~

Lệnh checkend 604800 có exit code nonzero nếu certificate đang hoặc sẽ hết hạn trong 7 ngày, không có stdout chung áp dụng cho mọi cert. Fingerprint SHA-256 chứng minh hai certificate files có cùng bytes hay khác bytes, không tự là trust proof. Hai certificate khác nhau có thể chứa cùng public key. Khi điều tra rotation, so cả cert fingerprint và key material/public key ID đã được IdP phê duyệt.

Cần đối chiếu ba nguồn:

1. Trusted IdP metadata bản hiện hành: EntityID, signing certificates, fingerprint, version/time.
2. Cấu hình SP đang chạy trên từng node: registration, IdP EntityID, loaded verification credentials và metadata age.
3. Signed SAML fixture trong sandbox: Issuer, SignedInfo/alg, signed element, signature result.

Không dump raw SAMLResponse/attributes/token/cookies vào logs hoặc issue tracker. Nếu phải chẩn đoán XML, dùng synthetic fixtures, quyền truy cập hạn chế và redaction.

## 6. OIDC/JWT: kid, JWKS và trusted issuer

Một JWS JWT có header alg/kid, payload iss/aud/exp, signature. Các trường header/payload đều chưa đáng tin trước khi verify.

- issuer xác định trusted OpenID Provider/Authorization Server.
- jwks_uri nằm trong provider discovery hoặc được cấu hình server-side từ nguồn tin cậy.
- JWKS có public JWKs, thường có kid, kty, alg, use/key_ops, đôi khi x5c/x5t.
- kid không bắt buộc và không global-unique. It is a key selector, not a trust anchor.
- kty/alg/use/key_ops phải tương thích với token/allowlist của ứng dụng.
- verify signature xong vẫn phải kiểm iss, aud, exp, nbf; OIDC login cần state/nonce theo flow.
- ID Token audience là client_id của RP; API access token audience là resource identifier, không mặc định bằng client_id.

### 6.1. Kiểm issuer và JWKS public endpoint

Từ trusted issuer discovery lấy jwks_uri thực tế. Các URLs minh họa dưới đây phụ thuộc từng provider; không hardcode path tùy tiện:

~~~bash
curl --fail --show-error --silent --max-time 15 https://idp.example.org/realms/corp/.well-known/openid-configuration -o discovery.json
curl --fail --show-error --silent --max-time 15 https://idp.example.org/realms/corp/protocol/openid-connect/certs -o jwks.json
jq -r '.keys[] | [.kid // "-", .kty // "-", .alg // "-", .use // "-"] | @tsv' jwks.json
~~~

Phải lấy endpoint JWKS từ trường jwks_uri thuộc discovery document của issuer được tin cậy, thay vì đoán từ example URL. Không trust URL jku/x5u của JWT header. Không dùng curl -k để qua lỗi TLS. JWKS là public keys, không được chứa private key parameters; nếu bị lộ thành phần private là security incident.

### 6.2. Phân loại lỗi JWK

| Lỗi | Giả thuyết | Cách sửa |
| --- | --- | --- |
| Unknown kid | Issuer mới rotate, key chưa publish hoặc consumer cache cũ. | Kiểm trusted JWKS hiện hành, cache TTL/refresh và rollout. |
| kid match nhưng signature fail | kid bị reuse với key khác, bytes đã bị sửa hoặc sai signer. | So public key/fingerprint, issuer, token signer và alg. |
| No compatible key | kty/alg/use/key_ops không phù hợp, key unsupported. | Kiểm key metadata và algorithm policy. |
| JWKS 404/500/timeout | Discovery path sai, outage, DNS/network. | Sửa provider endpoints/retries/cache theo policy. |
| HTTPS JWKS cert invalid | CA/hostname chain sai hoặc cert TLS hết hạn. | Sửa TLS trust, không disable HTTPS verification. |
| Invalid issuer | Token của realm/tenant khác. | Chọn đúng trusted issuer, không gộp trust pools. |
| Invalid audience | API nhận ID Token/web token hoặc token của API khác. | Cấp access token đúng API; giữ aud validator. |
| Expired/not yet valid | exp/nbf hoặc clock time sai. | NTP, renewal, bounded clock skew; không bỏ timestamps. |

Spring Security Resource Server và Nimbus hỗ trợ cập nhật JWK Set khi nhà phát hành đổi keys, nhưng chiến lược cache/refetch khi unknown kid phụ thuộc phiên bản, cấu hình custom cache, network timeouts và key endpoint. Không khẳng định mọi pod luôn refresh ngay lập tức.

## 7. Kế hoạch rotation có overlap và cách rollback

Ví dụ planned signing key rotation:

~~~text
T-7 ngày:
  IdP/AS publish public new signing key/cert bên cạnh old
  (đúng issuer, metadata/JWKS được trust).
  SP/API consumers refresh keyset và verify fingerprint/version.

T-1 ngày:
  Sandbox signed fixtures dùng old và new đều pass khi claims hợp lệ.
  Negative fixtures wrong key, tampered, wrong issuer đều reject.
  Xác nhận từng node/region/tenant đã nạp new key.

T0:
  IdP/AS chuyển sang ký bằng new private key.
  Monitor SIGNATURE_INVALID và KEY_NOT_FOUND.
  Consumers tiếp tục trust old trong approved overlap window.

T + approved overlap:
  Chỉ khi old tokens/assertions đã hết hạn và caches ổn định,
  retire old verification key theo lịch đã duyệt.

Emergency compromise:
  Old signing private key bị lộ => revoke trust khẩn,
  không giữ overlap chỉ để tránh lỗi đăng nhập.
~~~

Phân biệt certificate replacement dùng lại cùng public key với đổi keypair thực. Rotation khi một số consumers thiếu new key có thể gây intermittent login failure. Không vội xoay keys thêm lần nữa khi root cause là metadata snapshot cũ.

### Static SAML RelyingPartyRegistration

Với InMemoryRelyingPartyRegistrationRepository dựng từ RelyingPartyRegistrations.fromMetadataLocation lúc startup, repository có thể chứa snapshot signing certificates tại thời điểm ấy. IdP metadata URL đã thay không bảo đảm ứng dụng tự refresh trong mỗi request. Cần rebuild/refresh/redeployment có kiểm soát theo version và kiểm từng instance. Trước khi IdP bật new signing key, tất cả active SP nodes cần trust new public key.

### JWKS cache ở API

Nếu API cached old keyset và new JWT xuất hiện, unknown kid là dấu hiệu quan trọng. Kiểm issuer trong token, jwks_uri trusted, actual public JWKS, cache age, keyset version, alg policy và refetch result theo từng node. Không tải key từ arbitrary URL hoặc temporarily skip signature.

### Trình tự phản hồi sự cố khẩn

Nếu private key bị compromise: thông báo security owner, revoke/trust update theo incident process, phát keys mới, invalidate affected sessions/tokens theo khả năng hệ thống, đánh giá replay và thời gian lộ, triển khai lại và kiểm negative tests. Đây là trường hợp security ưu tiên hơn availability; không nới overlap vô hạn.

## 8. Dùng Spring Security 6.x: giữ validator mặc định

### 8.1. Mẫu SAML2 SP tối thiểu Spring Boot 3.3.5

Maven pom.xml của ứng dụng thử nghiệm:

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
  <artifactId>signature-lab</artifactId>
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

Metadata location cần lấy từ nguồn IdP được phê duyệt. Tùy version OpenSAML và Maven mirror, cần bảo đảm dependency artifacts từ repository đáng tin. Không đổi về phiên bản lỗi thời chỉ vì thiếu dependency.

application.yml:

~~~yaml
server:
  port: 8080
  # Chỉ dùng sau trusted reverse proxy đã strip user-supplied forwarded headers.
  forward-headers-strategy: framework

lab:
  saml:
    idp-metadata-uri: "https://idp.example.org/saml/metadata"
~~~

Main class trong src/main/java/com/example/signaturelab/SignatureLabApplication.java:

~~~java
package com.example.signaturelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SignatureLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SignatureLabApplication.class, args);
    }
}
~~~

SecurityConfig.java:

~~~java
package com.example.signaturelab;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    private static final Logger LOG =
        LoggerFactory.getLogger(SecurityConfig.class);

    @Bean
    RelyingPartyRegistrationRepository relyingParties(Environment env) {
        String trustedMetadata = env.getRequiredProperty(
            "lab.saml.idp-metadata-uri");

        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation(trustedMetadata)
            .registrationId("corp")
            .entityId(
                "https://sp.example.org/saml2/service-provider-metadata/corp")
            .assertionConsumerServiceLocation(
                "https://sp.example.org/login/saml2/sso/corp")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login-error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml.failureHandler(
                (request, response, error) -> {
                    // Log loại lỗi; không log raw XML hay user attributes.
                    LOG.warn("saml_login_denied causeType={}",
                        error.getClass().getSimpleName());
                    response.sendRedirect("/login-error");
                }))
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

LabController.java:

~~~java
package com.example.signaturelab;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {
    @GetMapping("/")
    public String home() {
        return "SAML2 validation lab";
    }

    @GetMapping("/login-error")
    public String loginError() {
        return "SSO authentication failed";
    }

    @GetMapping("/private")
    public String privatePage(Authentication auth) {
        return "Authenticated: " + auth.getName();
    }
}
~~~

SecurityFilterChain giữ Spring/OpenSAML signature/protocol validation. Failure handler chỉ ghi loại exception và trả trang lỗi chung, không lấy NameID từ XML lỗi rồi tạo principal. Production nên phân loại reason code nội bộ bằng mapping có kiểm soát và trace ID an toàn.

Không thể chạy SAML end-to-end với example.org; cần IdP sandbox thật, trusted metadata, correct EntityID/ACS và signed fixtures. Trong Spring Security 6.3 sử dụng họ OpenSaml4AuthenticationProvider; tài liệu Spring mới có thể dùng OpenSaml5AuthenticationProvider nên không sao chép customizer sai version.

### 8.2. Resource Server JWT: compose issuer/time/audience

Ứng dụng API dùng spring-boot-starter-oauth2-resource-server có thể cấu hình Boot YAML:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.org/realms/corp"
          jwk-set-uri: "https://idp.example.org/realms/corp/protocol/openid-connect/certs"
          audiences: "api://inventory"
~~~

Các URL trong ví dụ không live; lấy jwks_uri chính xác từ trusted issuer discovery. Giữ cả issuer và audience vì signature hợp lệ cho token của một resource khác không đủ. Với JWKS location pinned trong config, có thể tránh startup discovery ở một số cấu hình, nhưng không được bỏ iss validation.

Nếu cần custom JWT decoder, cấu hình một dự án Resource Server riêng:

~~~java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    JwtDecoder decoder(Environment env) {
        String issuer = env.getRequiredProperty("security.jwt.issuer");
        String jwks = env.getRequiredProperty("security.jwt.jwks");
        String audience = env.getRequiredProperty("security.jwt.audience");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Wrong audience", null));

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

Với Java bean trên, thêm cấu hình YAML server-side:

~~~yaml
security:
  jwt:
    issuer: "https://idp.example.org/realms/corp"
    jwks: "https://idp.example.org/realms/corp/protocol/openid-connect/certs"
    audience: "api://inventory"
~~~

- Chỉ cho phép RS256 ở ví dụ; dùng allowlist algorithm do issuer và security policy thống nhất, không tin alg bất kỳ từ token.
- DelegatingOAuth2TokenValidator bảo toàn JwtValidators.createDefaultWithIssuer, gồm issuer và timestamps, đồng thời thêm audience.
- Không dùng decoder.setJwtValidator(audienceValidator) một mình vì sẽ thay default validators.
- Không chấp nhận header jku/x5u từ token như trusted key endpoint.
- JWKS cache/auto-refresh phụ thuộc Nimbus, Spring version và cache config; unknown kid phải fail closed nếu chưa có trusted compatible key.
- API access token khác OIDC ID Token: aud của ID Token là client_id, không tự là API resource identifier.

## 9. Java 17 độc lập: minh họa key rotation và nguyên nhân fail

Chương trình KeyRotationDiagnostics.java dùng RSA SHA256 thật trên bytes của mô hình claim để cho thấy key mới chưa được trust sẽ gây KEY_NOT_FOUND; keyId đã biết nhưng signature sai vẫn bị reject; issuer/audience/time là các phép kiểm độc lập.

Giới hạn bắt buộc: đây KHÔNG phải SAML XML-DSig verifier, JOSE/JWS/JWT verifier hoặc X509 PKIX validator. Chuỗi ghép dấu | chỉ dùng dạy học, không phải canonicalization an toàn. KeyId v1/v2 là nhãn mô phỏng kid của JWKS; không khẳng định SAML Response luôn có kid. Production phải dùng OpenSAML, Spring/NimbusJwtDecoder và trusted metadata/issuer.

KeyRotationDiagnostics.java:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;
import java.util.Map;

public class KeyRotationDiagnostics {
    record Claim(String issuer, String audience, String subject,
                 Instant expiresAt, String keyId) {
        String forDemoOnly() {
            return String.join("|",
                issuer, audience, subject, expiresAt.toString(), keyId);
        }
    }

    record Evidence(Claim claim, byte[] signature) {}

    static Evidence issue(Claim c, PrivateKey key)
            throws GeneralSecurityException {
        Signature sig = Signature.getInstance("SHA256withRSA");
        sig.initSign(key);
        sig.update(c.forDemoOnly().getBytes(StandardCharsets.UTF_8));
        return new Evidence(c, sig.sign());
    }

    static String validate(Evidence e, Map<String, PublicKey> trust,
                           String issuer, String audience, Instant now)
            throws GeneralSecurityException {
        Claim c = e.claim();
        PublicKey key = trust.get(c.keyId());
        if (key == null) return "REJECT KEY_NOT_FOUND";

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(c.forDemoOnly().getBytes(StandardCharsets.UTF_8));
        if (!verifier.verify(e.signature())) {
            return "REJECT SIGNATURE_INVALID";
        }
        if (!issuer.equals(c.issuer())) return "REJECT ISSUER";
        if (!audience.equals(c.audience())) return "REJECT AUDIENCE";
        if (!now.isBefore(c.expiresAt())) return "REJECT EXPIRED";
        return "ACCEPT";
    }

    static void show(String label, Evidence e,
                     Map<String, PublicKey> trusted,
                     String issuer, String audience, Instant now)
            throws GeneralSecurityException {
        System.out.println(label + ": " +
            validate(e, trusted, issuer, audience, now));
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair old = generator.generateKeyPair();
        KeyPair fresh = generator.generateKeyPair();

        String issuer = "https://idp.example.org/realms/corp";
        String audience = "api://inventory";
        Instant now = Instant.parse("2030-01-01T12:00:00Z");
        Instant later = Instant.parse("2030-01-01T12:05:00Z");
        Instant earlier = Instant.parse("2030-01-01T11:59:00Z");

        Claim v1 = new Claim(issuer, audience, "alice", later, "v1");
        Claim v2 = new Claim(issuer, audience, "alice", later, "v2");
        Evidence oldToken = issue(v1, old.getPrivate());
        Evidence newToken = issue(v2, fresh.getPrivate());

        Map<String, PublicKey> oldOnly =
            Map.of("v1", old.getPublic());
        Map<String, PublicKey> overlap = Map.of(
            "v1", old.getPublic(), "v2", fresh.getPublic());
        Map<String, PublicKey> newOnly =
            Map.of("v2", fresh.getPublic());

        show("old before rotation", oldToken, oldOnly,
            issuer, audience, now);
        show("new before publish", newToken, oldOnly,
            issuer, audience, now);
        show("new during overlap", newToken, overlap,
            issuer, audience, now);
        show("old during overlap", oldToken, overlap,
            issuer, audience, now);
        show("old after retire", oldToken, newOnly,
            issuer, audience, now);

        Claim tampered = new Claim(
            issuer, audience, "mallory", later, "v1");
        show("tampered", new Evidence(tampered, oldToken.signature()),
            overlap, issuer, audience, now);

        Claim wrongIssuer = new Claim(
            "https://other.example.org", audience,
            "alice", later, "v2");
        show("wrong issuer", issue(wrongIssuer, fresh.getPrivate()),
            overlap, issuer, audience, now);

        Claim wrongAudience = new Claim(
            issuer, "api://other", "alice", later, "v2");
        show("wrong audience", issue(wrongAudience, fresh.getPrivate()),
            overlap, issuer, audience, now);

        Claim expired = new Claim(
            issuer, audience, "alice", earlier, "v2");
        show("expired", issue(expired, fresh.getPrivate()),
            overlap, issuer, audience, now);

        // keyId v2 nhưng dùng private key old để ký: signature sai.
        show("wrong key with known kid", issue(v2, old.getPrivate()),
            overlap, issuer, audience, now);
    }
}
~~~

Chạy trên Java 17:

~~~bash
javac KeyRotationDiagnostics.java
java KeyRotationDiagnostics
~~~

Stdout chính xác, dù cặp RSA key được sinh ngẫu nhiên:

~~~text
old before rotation: ACCEPT
new before publish: REJECT KEY_NOT_FOUND
new during overlap: ACCEPT
old during overlap: ACCEPT
old after retire: REJECT KEY_NOT_FOUND
tampered: REJECT SIGNATURE_INVALID
wrong issuer: REJECT ISSUER
wrong audience: REJECT AUDIENCE
expired: REJECT EXPIRED
wrong key with known kid: REJECT SIGNATURE_INVALID
~~~

Ý nghĩa:

- new before publish: key v2 chưa có trong trust pool, không thể verify.
- new during overlap và old during overlap: hai public keys được tin trong approved rotation window.
- old after retire: key cũ đã bỏ, token dùng key cũ bị reject.
- tampered: nội dung subject đổi nhưng signature old không đổi nên invalid.
- wrong issuer/audience: được ký bằng key trusted, nhưng claim validation vẫn reject.
- expired: chữ ký đúng nhưng token hết hạn; không nhầm với certificate NotAfter.
- wrong key with known kid: key selector tìm được v2 nhưng signature được tạo bởi v1 nên invalid.

Không dùng chương trình này để tạo Authentication. Mọi real SAML/JWT cần signed-element coverage, canonicalization/alg policy, trusted issuer/JWKS, replay/correlation và authorization của framework.

## 10. Observability không làm lộ bearer credentials

Nên log event sau khi provider trả kết quả thay vì dump unverified XML/token:

~~~text
event=sso.authentication.denied
trace_id=trace-7f20
protocol=SAML2
registration_alias=corp
stage=SIGNATURE_VERIFICATION
reason=KEY_NOT_FOUND
trusted_keyset_version=rot-2026-11-a
node=sp-prod-b
result=DENY
~~~

Reason codes như KEY_NOT_FOUND, SIGNATURE_INVALID, ISSUER_MISMATCH, DECRYPT_FAILED, CERT_VALIDITY_POLICY là taxonomy do đội vận hành định nghĩa, không phải API enum mặc định của Spring. Chỉ map exception/cause sau khi đã phân tích và sanitize. Không log nguyên error.getMessage khi có nguy cơ chứa dữ liệu.

Không ghi raw SAMLResponse, XML assertions, JWT/ID Token/access token, Authorization header, cookies, private keys, full user/group attributes hoặc JWT content trước verify. Full fingerprint và issuer endpoint nội bộ cũng có thể cần hạn chế quyền truy cập theo security policy.

Metrics và alerts hữu ích:

| Tín hiệu | Label cardinality thấp | Ý nghĩa |
| --- | --- | --- |
| sso_auth_attempts_total | protocol, registration_alias, result | Success/error ratio. |
| sso_auth_failures_total | protocol, stage, reason | Signature/key errors sau rotation. |
| idp_metadata_age_seconds | idp_alias, node | Node có stale metadata? |
| idp_metadata_refresh_success | idp_alias, node | Fetch/parse/trust pass? |
| jwks_refresh_failures_total | issuer_alias, env | Key endpoint/network vấn đề. |
| jwks_keyset_age_seconds | issuer_alias, node | Cache freshness theo pod. |
| signing_cert_days_remaining | idp_alias, cert_slot | Planned expiry alert. |
| sso_rotation_state | idp_alias, phase | Publish, activate, overlap, retire. |

Không dùng arbitrary kid, user email, subject, trace ID hay raw URL làm Prometheus labels vì cardinality và privacy. Chi tiết per-request nằm trong sanitized audit logs.

Alert khi (1) SIGNATURE_INVALID/KEY_NOT_FOUND tăng đồng loạt; (2) chỉ một node fail; (3) metadata/JWKS không refresh; (4) signing cert sắp NotAfter; (5) actual key fingerprint khác approved change; (6) synthetic login fail sau T0.

## 11. Runbook 12 bước khắc phục sự cố

1. Ghi UTC onset, protocol, IdP alias, registration, affected endpoints, deployment version và trace IDs đã sanitize.
2. Xác định phạm vi: toàn hệ thống hay một region/node/tenant? Chỉ SAML login hay JWT API?
3. Phân loại stage: metadata fetch, key selection, signature verify, decryption, issuer/audience/time, local authorization.
4. Đọc expected trusted issuer/registration và keyset version từ app đang chạy; không nhìn unverified token để quyết định trust.
5. Lấy IdP metadata/JWKS từ approved origin và kiểm HTTPS/trust/integrity. So fingerprints/kid/alg với change record.
6. Đối chiếu thời điểm IdP publish new key và lúc nó bắt đầu ký bằng new private key.
7. Kiểm SP static RelyingPartyRegistration snapshot hoặc JWT JWKS cache/TTL/refetch trên từng node.
8. Phân biệt encryption failure, signed AuthnRequest rejected by IdP, cert NotAfter và signed assertion time expiry.
9. Sửa đúng config: import approved new verification public key, refresh metadata/rebuild repository/reload cache, giữ old trong approved overlap.
10. Test new-signed hợp lệ pass, tampered/wrong issuer/wrong audience/retired key/expired vẫn reject.
11. Rollout từng node/region, theo dõi failure metrics, xác minh không còn intermittent fail và có rollback plan.
12. Chốt RCA: owner, certificate fingerprints, keyset versions, change ticket, postmortem, rotation calendar, runbook update.

Chủ sở hữu: IdP/AS admin quản lý signer và publish keys; SP/API team quản lý registration/decoder/cache; Platform chịu trách nhiệm DNS/TLS/network/rollout; Security/IAM phê duyệt trust anchor/compromise response; QA/SRE quản lý synthetic tests/metrics.

## 12. Ma trận test chữ ký, khóa và rotation

Để test audience độc lập, phải tạo message/token được ký hợp lệ nhưng audience sai. Nếu chỉ sửa XML/JSON sau ký, signature invalid trước và chưa chứng minh audience validator hoạt động.

| # | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| 1 | SAML signed từ trusted IdP, claims hợp lệ | Login pass sau local authorization. |
| 2 | SAML ký bằng attacker private key | Reject signature/trust. |
| 3 | SAML KeyInfo chứa attacker X509 cert | Không tự trust. |
| 4 | SAML NameID bị sửa sau ký | Reject signature. |
| 5 | XML Signature Wrapping signed Alice + unsigned Mallory | Không cấp Mallory principal. |
| 6 | Signed Response hợp lệ nhưng Assertion khác không trong coverage | Reject untrusted data. |
| 7 | IdP dùng old key, SP trust old | Pass trong old valid period. |
| 8 | IdP ký new nhưng SP chỉ trust old | Fail closed. |
| 9 | SP trust old+new, IdP ký new | Pass. |
| 10 | SP trust old+new, old fixture chưa hết hạn | Pass trong overlap. |
| 11 | Old key đã retire | Reject old-signed messages. |
| 12 | Wrong IdP EntityID/registration | Reject issuer/trust. |
| 13 | SAML audience/recipient sai, chữ ký đúng | Reject protocol claims. |
| 14 | X509 signing cert hết NotAfter, signature math verify | Đánh giá cert policy riêng, không nhầm lỗi. |
| 15 | SAML assertion NotOnOrAfter expired | Reject time. |
| 16 | Metadata endpoint HTTPS CA invalid | Fail nếu không có trusted valid snapshot theo policy. |
| 17 | Static registration chưa cập nhật cert mới | Fail, cần reload/rebuild. |
| 18 | Node A trust new, B chỉ old | Phát hiện node inconsistency. |
| 19 | IdP từ chối SP signed AuthnRequest | Kiểm SP signing credentials. |
| 20 | EncryptedAssertion decrypt failed | Kiểm SP decryption keys. |
| 21 | IdP encryption certificate bị dùng nhầm signing verifier | Reject/config QA fail. |
| 22 | Metadata bị sửa từ untrusted origin | Không nạp public keys. |
| 23 | JWT RS256 đúng issuer/audience/key | API pass. |
| 24 | JWT kid mới, cache chỉ old | KEY_NOT_FOUND, refresh trusted JWKS. |
| 25 | JWT JWKS overlap old+new | New và old còn hạn đều pass. |
| 26 | JWT kid đúng nhưng signed bởi wrong private key | SIGNATURE_INVALID. |
| 27 | JWT kid reused nhưng key bytes khác | Reject, điều tra issuer rotation. |
| 28 | JWT alg=none | Reject. |
| 29 | JWT jku/x5u trỏ attacker | Không tải arbitrary key URL. |
| 30 | JWK use=enc nhưng token cần sig | Reject incompatible key. |
| 31 | JWT issuer sai, chữ ký có thể đúng | Reject issuer. |
| 32 | API nhận ID Token của web client | Reject audience/token type. |
| 33 | exp expired hoặc nbf future | Reject time. |
| 34 | JWKS endpoint 404/timeout | Fail closed nếu không có trusted key hợp lệ. |
| 35 | JWKS HTTPS certificate expired | Không tắt TLS validation. |
| 36 | Custom cache không refresh unknown kid | Chẩn đoán stale keyset, sửa cache. |
| 37 | Signing private key compromise | Emergency revoke, không giữ overlap. |
| 38 | Token verified nhưng user disabled | Local authorization deny. |
| 39 | Cross-tenant wrong issuer/registration | Reject. |
| 40 | Debug log chứa raw SAMLResponse/JWT/private key | Security QA fail. |
| 41 | Certificate inventory alert trước hạn | Lập planned rotation change. |
| 42 | Rollback old signer trong approved window | Chỉ accept old trusted key khi policy cho phép. |
| 43 | JWT kid cùng nhưng kty/alg không tương thích | Reject/no candidate. |
| 44 | SAML signature valid nhưng user thiếu role | 403/local deny. |
| 45 | Metadata 200 nhưng malformed/wrong issuer | Reject metadata. |

Kết quả tốt nhất: positive new-signed fixture pass sau rotation nhưng tampered, wrong issuer/audience, old retired key, expired và untrusted key vẫn bị từ chối. Không xóa negative tests để làm CI xanh.

## 13. Anti-pattern phổ biến và cách thay

| Anti-pattern | Thay bằng |
| --- | --- |
| Tin mọi certificate khi IdP rotate | Import approved IdP public verification keys từ trusted metadata, có overlap. |
| Tự nhận KeyInfo từ Response như trust anchor | Anchored verification credentials theo registration. |
| Có JWT kid đúng thì cho login | Vẫn verify trusted JWK, algorithm, signature và claims. |
| Fetch JWKS từ jku của user token | Server-configured trusted issuer discovery/JWKS URI. |
| Bỏ signature khi no matching key | Fail closed và sửa publish/refresh/reload. |
| Nhầm X509 NotAfter với JWT exp | Điều tra cert policy và token lifetime riêng. |
| Decrypt fail thì xoay IdP signing cert | Kiểm SP decryption key và IdP encryption cert. |
| IdP reject AuthnRequest thì đổi IdP response signer | Kiểm SP signing key và IdP SP trust. |
| Trust mọi alg do JWT header yêu cầu | Dùng allowlist alg phù hợp trusted issuer. |
| Bỏ old key ngay trong planned rotation | Overlap có giới hạn theo TTL và policy. |
| Giữ old verification key vô hạn | Retirement deadline, metrics, rotation controls. |
| Log nguyên SAML XML/JWT trong prod | Sanitized reason codes/trace IDs, limited lab debug. |

## 14. Checklist nghiệm thu

### SAML2

- [ ] IdP EntityID và RelyingPartyRegistration đúng môi trường/tenant.
- [ ] Dùng đúng IdP verification public key; không nhầm SP signing/decryption hoặc HTTPS TLS cert.
- [ ] Metadata trusted/integrity, key fingerprints và certificate dates được inventory.
- [ ] Spring/OpenSAML kiểm signature/coverage, chống XML Signature Wrapping.
- [ ] Issuer, audience, recipient/destination, NotBefore/NotOnOrAfter và InResponseTo còn hiệu lực.
- [ ] Static metadata snapshots có refresh/redeploy plan, node parity đúng.
- [ ] Planned old+new overlap hoặc compromised-key revoke policy rõ ràng.

### OIDC/JWT

- [ ] Trusted issuer/JWKS URI được pin/config server-side.
- [ ] kid/kty/alg/use/key_ops kiểm theo policy, không tin arbitrary header URL.
- [ ] JwtDecoder kiểm signature, issuer, exp/nbf và audience API.
- [ ] ID Token dùng aud client_id; API access token dùng resource aud.
- [ ] Cache refresh và unknown kid behavior được test theo actual version.
- [ ] Key rotation tests bao phủ publisher/consumer timing.

### Quan sát và xử lý sự cố

- [ ] Metric cho errors theo protocol/registration/stage/reason có cardinality thấp.
- [ ] Alert JWKS/metadata fetch errors, keyset age, signing cert NotAfter.
- [ ] Logs không lộ raw token, keys, cookies, user full attributes.
- [ ] Có golden signed fixtures old/new và negative tests cho tampering/unknown key.
- [ ] Key fingerprints được xác nhận qua approved change record.
- [ ] Incident chỉ đóng khi fail-closed signature verification vẫn hoạt động.

## 15. Câu hỏi ôn tập

1. Signature invalid và key not found khác nhau ra sao? Key not found nghĩa là chưa có trusted candidate, còn signature invalid nghĩa là candidate được dùng nhưng không verify.
2. Có được tin X509Certificate nằm trong SAML KeyInfo không? Không, phải anchored vào trusted IdP verification credentials.
3. TLS certificate và SAML signing certificate có thay nhau được không? Không, chúng bảo vệ transport và signed message ở các tầng khác nhau.
4. X509 certificate đã hết NotAfter có chắc signature bytes sẽ verify sai không? Không, mathematical signature và certificate validity/trust policy là hai phép kiểm khác nhau.
5. Vì sao phải publish new public key trước khi ký bằng new private key? Consumers cần nạp new key trước khi gặp new-signed traffic.
6. Khi nào nên retire old key ngay, không giữ overlap? Khi key compromise hoặc emergency security policy yêu cầu.
7. JWT kid có phải trust anchor không? Không; nó là untrusted selector, phải verify bằng key từ trusted issuer.
8. Tại sao chỉ cấu hình jwk-set-uri mà không kiểm issuer có thể nguy hiểm? Không có ràng buộc iss chính xác của API trust contract.
9. SAML encrypted assertion lỗi decrypt cần kiểm khóa nào? SP private decryption key và IdP SP encryption public cert.
10. IdP không verify signed AuthnRequest thì kiểm khóa nào? SP signing private key/cert đã đăng ký ở IdP.
11. InMemoryRelyingPartyRegistrationRepository có tự nạp lại signing cert sau mỗi request? Không nên giả định; snapshot thường cần rebuild/reload.
12. Sao lỗi chỉ xuất hiện ở một pod sau rotation? Có thể metadata/JWKS cache/config khác phiên bản.
13. Có chữ ký đúng rồi có thể bỏ audience/time không? Không, trust, audience và time là các ràng buộc độc lập.
14. Nên log raw JWT/SAMLResponse cho dễ debug không? Không; dùng sanitized reason, trace ID và môi trường sandbox có kiểm soát.

## 16. Tài liệu chính thống

1. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, IdP verification credentials và SAML login.
2. [Spring Security Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): signature/decryption/claims validation; so API version vì docs mới dùng OpenSAML5.
3. [Spring Security SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): asserting-party metadata, trust và metadata signatures.
4. [Spring Security 6.3 OpenSaml4AuthenticationProvider API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): provider family phù hợp Spring Security 6.3.
5. [Spring Security OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): issuer/JWKS/rotation/default validators.
6. [Spring Boot 3.3 Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): SAML/Boot security integration.
7. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Assertion/conditions/signature semantics.
8. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): KeyDescriptor, EntityDescriptor.
9. [W3C XML Signature 1.1](https://www.w3.org/TR/xmldsig-core1/): Reference/canonicalization/KeyInfo.
10. [RFC 7517 JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWKS/kid/kty/use.
11. [RFC 7515 JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS alg/signature.
12. [RFC 7519 JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): iss/aud/exp/nbf.
13. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation.
14. [RFC 8414 OAuth2 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer metadata/JWKS discovery.
15. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature wrapping and trust.
16. [OWASP JWT Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): secure JWT verification.
17. [OpenSSL x509 manual](https://docs.openssl.org/3.0/man1/openssl-x509/): fingerprint/dates/checkend.

Kết luận: Khi gặp invalid signature, key not found hoặc signing certificate changed, đi từ protocol và đúng trusted issuer/registration đến metadata/JWKS, kiểm public key/fingerprint và cache state, phân biệt signature, cert policy và token validity. Sửa đúng cấu hình và planned rotation; không bao giờ bỏ signature verification hoặc tự tin khóa do unverified message cung cấp.