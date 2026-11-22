# Tạo bộ dữ liệu SAML thử nghiệm với khóa ký dành riêng cho kiểm thử

> **Chủ đề:** Spring Security – federation. **Nhóm:** Kiểm thử SAML2. Đây là bài Knowledge độc lập về thiết kế, sinh, ký, kiểm chứng và vận hành **bộ fixture SAML 2.0** với **khóa ký của IdP chỉ dùng cho môi trường test**. Tài liệu kết hợp SAML Web Browser SSO, Spring Security/OpenSAML, Java 17, OpenSSL, metadata, mock IdP, test clocks, request correlation, replay, XML Signature Wrapping và CI/CD bảo vệ bí mật.

## 1. Vấn đề cần giải quyết

Để thử nghiệm một Spring Security SAML Service Provider (SP), không đủ tạo một file XML có NameID rồi Base64-encode nó thành tham số `SAMLResponse`. Một test đáng tin phải chứng minh:
1. SAML XML được **test Identity Provider (IdP) ký thật bằng XML Digital Signature**, không bằng chuỗi giả.
2. Spring SP xác minh chữ ký bằng **public certificate test đã được tin cậy trong đúng RelyingPartyRegistration**.
3. Signed XML chứa **đúng Issuer, Audience, Recipient, Destination, Conditions, SubjectConfirmation, InResponseTo** và ID hợp lệ.
4. User/attributes được dùng phải thuộc **Assertion được chữ ký tin cậy bảo vệ**.
5. Bộ test có positive và negative cases phân biệt được cryptographic failure, signer trust failure, SAML protocol failure và local authorization failure.
6. Không dùng private key IdP production, không đưa test signing certificate vào production trust store, và không dùng tài khoản nhân viên thật làm dữ liệu mẫu.

**Nguyên tắc chính:** Phía test IdP **giữ private signing key**; phía Spring test SP **chỉ tin public signing certificate**. Private test key không được cấp cho Spring chỉ để verify assertion, và tuyệt đối không lấy production signing key sang môi trường kiểm thử.

## 2. Những khái niệm nên phân biệt

| Khái niệm | Ý nghĩa |
|---|---|
| SAML Response | Thông điệp protocol do IdP gửi đến SP ACS qua browser |
| SAML Assertion | Bằng chứng chứa Subject/NameID, Conditions, AuthnStatement, Attributes |
| Test IdP | Hệ thống giả lập/isolated Identity Provider phục vụ test |
| SP | Spring Security SAML2 Relying Party cần xác minh Response |
| ACS | Assertion Consumer Service nhận SAMLResponse |
| IdP signing private key | Bí mật bên IdP dùng tạo XMLDSig signatures |
| IdP verification certificate | Public certificate SP dùng kiểm chữ ký |
| SP signing private key | Bí mật riêng của SP để ký AuthnRequest/LogoutRequest nếu cần |
| SP decryption private key | Khóa SP giải EncryptedAssertion/EncryptedID nếu cần |
| TLS certificate | Chứng thư transport HTTPS, không tự thay XMLDSig certificate |
| RelyingPartyRegistration | Mapping SP entityID, ACS, trusted IdP issuer và signing credentials |
| IdP metadata | EntityID, SSO endpoint, public signing certificates, bindings |
| XMLDSig | Cơ chế Reference/Digest/SignedInfo/SignatureValue trên XML |
| KeyInfo | Gợi ý certificate/key trong XML, không tự trở thành trust anchor |
| SignatureMethod | Thuật toán ký, ví dụ RSA-SHA256 |
| DigestMethod | Thuật toán băm Reference, ví dụ SHA-256 |
| Reference URI | Liên kết chữ ký tới ID của Response hoặc Assertion |
| InResponseTo | Correlation với AuthnRequest SP-initiated |
| NotBefore/NotOnOrAfter | Thời hạn Assertion và bearer confirmation |
| Replay | Tái sử dụng token/assertion đã được phát |
| Fixture manifest | Hợp đồng scenario, signer, protocol fields và expected outcome |
| Test clock | Thời gian điều khiển để kiểm expiration/skew |
| Test IdP certificate rollover | Giai đoạn trust A/B rồi bỏ A để kiểm rotation |

Dùng cùng từ “certificate” cho IdP signing, SP decryption và TLS dễ gây nhầm. Mỗi cặp khóa có mục đích, owner và trust policy riêng.

## 3. Tách môi trường kiểm thử và sản xuất

Một mô hình an toàn:

~~~text
          ISOLATED TEST IDP / FIXTURE SIGNER
          ----------------------------------
          private: TEST_IDP_A.key
          public:  TEST_IDP_A.crt
          issuer:  urn:example:saml:test-idp:alpha
                          |
                          | Signed SAMLResponse
                          | browser / HTTP POST
                          v
          SPRING SERVICE PROVIDER - TEST
          ----------------------------------
          registrationId: fixture-idp
          trusted IdP cert: TEST_IDP_A.crt (public)
          expected issuer:  urn:example:saml:test-idp:alpha
          SP entityID:      urn:example:saml:test-sp:portal
          ACS:              https://portal.test.example/login/saml2/sso/fixture-idp

          PRODUCTION ENVIRONMENT (NO LINK)
          ----------------------------------
          production IdP signing private key
          production SAML verification trust
          production user accounts and sessions
~~~

**Không được:**
- Export private signing key production vào CI hoặc máy nhà phát triển.
- Dùng một keypair cho cả test và production IdP.
- Commit private test key vào Git, container image, docs hay public artifact.
- Để production SP tin test public certificate “cho tiện”.
- Để test IdP có thể gửi SAMLResponse vào production ACS với trusted credentials.
- Copy nguyên SAMLResponse production làm fixture vì có thể chứa NameID, email, group, session index và thông tin nhân sự.

**Có thể:** Commit một **public test X.509 certificate** trong test resources nếu nó không được production tin và không chứa private key. Với secret test private key, tốt nhất sinh trong temporary workspace/CI secret store, có ACL và dọn sạch sau job.

### 3.1. Self-signed certificate có phù hợp không?

Với SAML test, **có thể dùng self-signed certificate** vì SP thường tin signing certificate thông qua configured IdP metadata hoặc verification credential được quản trị chấp thuận. Tuy nhiên, **self-signed không có nghĩa trust-all**. Chữ ký toán học hợp lệ bằng public key lạ phải bị reject nếu key đó không thuộc đúng IdP registration.

Không đồng nhất kiểm định SAML signing credential với browser TLS PKI. Certificate validity và KeyUsage/EKU/chain processing phải theo trusted IdP policy và verifier implementation; không mặc định mọi thư viện tự kiểm mọi điều kiện PKIX.

## 4. Chọn test keys và thuật toán

Một profile RSA tương thích rộng:
- Dùng RSA 3072-bit cho test IdP nếu các sản phẩm hỗ trợ; ít nhất RSA 2048-bit nếu baseline cho phép.
- Với XMLDSig, dùng SignatureMethod RSA-SHA256 hoặc mạnh hơn theo security policy.
- Với signed Reference, dùng DigestMethod SHA-256 hoặc mạnh hơn.
- Dùng canonicalization và enveloped-signature transforms theo SAML/XMLDSig profile.
- Chặn SHA-1/MD5, XSLT/external Reference và weak algorithms theo baseline.
- Có thể dùng ECDSA P-256/P-384 nếu IdP/SP tương thích, nhưng không mặc định vendor nào cũng hỗ trợ.
- Đặt thời hạn cert test phù hợp; quay vòng key khi cần.
- Định danh key trong manifest như `TEST-IDP-A`, `TEST-IDP-B` và lưu certificate fingerprint.

**Phân biệt hai thuật toán:** Chứng thư X.509 tự ký bằng SHA-256 không tự chứng minh Assertion đã có XML Signature RSA-SHA256. Generator phải thực hiện operation ký XML riêng sau khi dựng Response/Assertion.

### 4.1. Dùng hai keys để kiểm trust, không chỉ một

Key A phục vụ positive fixtures của IdP test alpha; Key B phục vụ:
- Negative case “wrong signing key”.
- Key rollover tests.
- Cross-IdP registration isolation.
- Chứng minh Spring không tin KeyInfo tự khai.

Có thể dùng cả A và B dưới **cùng issuer** trong rotation scenario, nhưng trust set phải được đổi theo phase; dùng **hai issuers khác nhau** khi kiểm IdP/tenant mix-up.

## 5. Sinh khóa ký chỉ dùng cho test bằng OpenSSL

Các lệnh ví dụ dưới đây dành cho Linux/macOS với OpenSSL 3.x và directory test có quyền hạn chế. Trên Windows có thể dùng WSL hoặc cách thiết lập ACL/PowerShell tương đương. Đường dẫn là trong workspace test, không phải production.

### 5.1. Tạo thư mục và hạn chế quyền truy cập

~~~bash
umask 077

mkdir -p build/saml-fixtures/private
mkdir -p build/saml-fixtures/public

chmod 700 build/saml-fixtures/private
~~~

Dùng `build/` làm output transient và exclude khỏi Git/artifacts. Những lệnh tạo thư mục thành công thường không có stdout; không ghi password/secret lên shell history.

### 5.2. Sinh RSA 3072-bit test signing private key

~~~bash
openssl genpkey \
  -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out build/saml-fixtures/private/idp-test-a.key.pem
~~~

File `idp-test-a.key.pem` là **private key**, không cho Spring SP truy cập chỉ để verify. Lệnh có thể in thông tin tiến trình ra stderr tùy OpenSSL version; không có stdout cố định phải assert.

### 5.3. Tạo X.509 certificate self-signed test

~~~bash
openssl req -new -x509 \
  -key build/saml-fixtures/private/idp-test-a.key.pem \
  -out build/saml-fixtures/public/idp-test-a.crt.pem \
  -sha256 \
  -days 30 \
  -subj "/CN=Isolated SAML Test IdP A" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature"
~~~

Giải thích:
- `-key` dùng private key vừa sinh để tạo chứng thư tương ứng.
- `-x509` xuất certificate, không xuất một certificate request chờ CA.
- `-sha256` là thuật toán ký chứng thư, khác XMLDSig signing algorithm.
- `-days 30` cho cryptoperiod test ví dụ, không phải quy tắc production.
- `CA:FALSE` không biến cert thành CA.
- `digitalSignature` mô tả mục đích sử dụng.
- X.509 CN không tự bằng IdP SAML entityID.
- Các extension flags phụ thuộc OpenSSL version; khi tool không hỗ trợ, sửa bằng verified configuration file thay vì bỏ kiểm TLS/SAML.

### 5.4. Kiểm fingerprint và public key matching

~~~bash
openssl x509 \
  -in build/saml-fixtures/public/idp-test-a.crt.pem \
  -noout -subject -issuer -dates -fingerprint -sha256

openssl pkey \
  -in build/saml-fixtures/private/idp-test-a.key.pem \
  -pubout \
  -out build/saml-fixtures/public/from-private.pub.pem

openssl x509 \
  -in build/saml-fixtures/public/idp-test-a.crt.pem \
  -pubkey -noout \
  -out build/saml-fixtures/public/from-cert.pub.pem

cmp \
  build/saml-fixtures/public/from-private.pub.pem \
  build/saml-fixtures/public/from-cert.pub.pem
~~~

Cả hai public-key exports cùng dạng PEM từ OpenSSL; nếu trùng byte thì `cmp` exit code 0 và thường không in output. Nếu format khác, so DER SubjectPublicKeyInfo bytes thay vì text. Fingerprint thực tế **ngẫu nhiên theo cặp khóa mới**, không viết một fingerprint giả vào test expectation.

### 5.5. Tạo test key B độc lập

~~~bash
openssl genpkey \
  -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out build/saml-fixtures/private/idp-test-b.key.pem

openssl req -new -x509 \
  -key build/saml-fixtures/private/idp-test-b.key.pem \
  -out build/saml-fixtures/public/idp-test-b.crt.pem \
  -sha256 \
  -days 30 \
  -subj "/CN=Isolated SAML Test IdP B" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature"
~~~

Key B không phải bản copy của A. Không giữ A và B ở cùng production trust list, trừ khi thử **test IdP key overlap** trong riêng môi trường test.

## 6. Cấu trúc bộ fixture và quản lý artifacts

Một layout khuyến nghị:

~~~text
saml-fixture-kit/
  README.md
  manifest.yaml
  public/
    idp-test-a.crt.pem
    idp-test-b.crt.pem
    idp-test-metadata.xml
  generated/
    signed-response-valid.xml
    signed-assertion-valid.xml
    signed-both-valid.xml
    bad-audience-but-valid-signature.xml
    expired-but-valid-signature.xml
    tampered-after-sign.xml
    signed-by-untrusted-key.xml
  private/
    idp-test-a.key.pem        (ephemeral, excluded from Git)
    idp-test-b.key.pem        (ephemeral, excluded from Git)
  ci/
    expected-results.json
    fixture-clock.txt
~~~

Đây là bố cục mục tiêu, các filenames `generated/*.xml` chỉ có sau khi generator/IdP ký SAML thực. Không được coi tên file “signed” là bằng chứng có chữ ký hợp lệ; mọi fixture cần được **đọc qua verifier**.

### 6.1. Data synthetic, không dùng account thật

Ví dụ thống nhất:

~~~text
Test IdP A issuer: urn:example:saml:test-idp:alpha
Test IdP B issuer: urn:example:saml:test-idp:beta
Test SP entityID:  urn:example:saml:test-sp:portal
Test ACS URL:     https://portal.test.example/login/saml2/sso/fixture-idp
Test SSO URL:     https://idp.test.example/sso
NameID:           synthetic-user-001@test.invalid
Local test user:  test-user-1001
Local test tenant: tenant-alpha
Mapped role:      ROLE_REPORT_VIEW
Unapproved group: UntrustedAdmin
~~~

Không dùng employeeNumber, real SIDs, email thật, production tenant ID hoặc signed assertions từ user thật. Một NameID giả cũng cần **stable identity-link policy** trong local test database để test role mapping.

### 6.2. Manifest ghi nguồn khóa và expected outcome

~~~yaml
suite: isolated-saml2-fixtures
version: 1
profile: web-browser-sso
testIdp:
  entityId: "urn:example:saml:test-idp:alpha"
  keyRef: "test-secret-store:idp-a-private"
  verificationCertificate: "public/idp-test-a.crt.pem"
  signatureAlgorithm: "rsa-sha256"
  digestAlgorithm: "sha256"
testSp:
  entityId: "urn:example:saml:test-sp:portal"
  acs: "https://portal.test.example/login/saml2/sso/fixture-idp"
  registrationId: "fixture-idp"
clock:
  unitTestStrategy: fixed
  fixedInstant: "2026-06-01T12:00:00Z"
cases:
  - id: positive-response-signed
    signer: TEST_IDP_A
    signaturePlacement: RESPONSE
    subject: synthetic-user-001@test.invalid
    expected: AUTHENTICATED
  - id: positive-assertion-signed
    signer: TEST_IDP_A
    signaturePlacement: ASSERTION
    expected: AUTHENTICATED
  - id: bad-audience-signed
    signer: TEST_IDP_A
    audience: urn:example:saml:test-sp:other
    expected: REJECT_AUDIENCE
  - id: tampered-after-sign
    signer: TEST_IDP_A
    mutateAfterSigning: true
    expected: REJECT_SIGNATURE
  - id: wrong-signing-key
    signer: TEST_IDP_B
    expected: REJECT_UNTRUSTED_SIGNER
~~~

**Đây là hợp đồng đầu vào cho fixture generator của dự án**, không phải Spring Security YAML autoconfiguration. `keyRef` chỉ nên trỏ secret store/test volume; không nhét literal private key trong manifest. Error labels là kỳ vọng tầng test; HTTP failure handler có thể redirect hoặc trả HTTP status khác.

## 7. Public metadata của test IdP

IdP metadata cần chứa:
- `EntityDescriptor.entityID` đúng test issuer.
- `IDPSSODescriptor` với supported SAML 2.0 protocol.
- `SingleSignOnService` URL/Binding đúng môi trường test.
- `KeyDescriptor use="signing"` với **public X.509 certificate** tương ứng A.
- Nếu test rotation, KeyDescriptor cho A/B theo policy.

SAML metadata skeleton minh họa:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="urn:example:saml:test-idp:alpha">

  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data/>
      </ds:KeyInfo>
    </md:KeyDescriptor>

    <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.test.example/sso"/>

  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Đây là **sketch chưa hoàn chỉnh**: tag `X509Data` đang rỗng nên **không thể dùng làm trust metadata thực**. Test IdP/metadata generator phải đưa Base64 DER của public cert vào `ds:X509Certificate`, đảm bảo XML schema và metadata trust. **Private key tuyệt đối không nằm trong metadata**.

### 7.1. PEM certificate khác KeyInfo

Một PEM certificate chỉ chứa public material. Metadata SAML `ds:X509Certificate` dùng Base64 DER certificate, không chèn dòng định dạng PEM vào XML. `ds:KeyInfo` trong incoming SAMLResponse **không tự cấp quyền trust certificate lạ**; SP phải so với approved verification credentials của registration.

### 7.2. Key rollover metadata

Kịch bản cùng một test IdP:
1. SP đang tin A.
2. Test IdP xuất thêm cert B, SP trust A+B.
3. IdP bắt đầu ký bằng B.
4. Verify B pass trong overlap; verify A pass khi chưa retire.
5. SP bỏ A theo change control.
6. Signature A bị reject.

Nếu test **khác IdP/tenant**, không gắn B vào registration alpha chỉ vì issuer beta có chữ ký mathematically valid.

## 8. Spring Boot test configuration: SP chỉ cài public cert

Ví dụ dưới đây là **file application-saml-test.yml** chỉ kích hoạt trong profile test. Property names cần đối chiếu Spring Boot version được dùng, vì naming thay đổi giữa releases.

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          fixture-idp:
            entity-id: "urn:example:saml:test-sp:portal"
            assertingparty:
              entity-id: "urn:example:saml:test-idp:alpha"
              singlesignon:
                url: "https://idp.test.example/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-test-a.crt.pem"
~~~

Trong Spring Boot/Spring Security:
- `fixture-idp` là registration ID.
- Top-level `entity-id` là SP entityID.
- `assertingparty.entity-id` là trusted test IdP entityID.
- `verification.credentials[].certificate-location` trỏ **public certificate test IdP**, không phải PEM private key.
- `singlesignon.url` là endpoint IdP nhận AuthnRequest; phải có test IdP thật/test double support protocol.
- SP ACS mặc định thường là `/login/saml2/sso/{registrationId}`; kiểm thực tế của deployment.
- Test profile **không được merge** các trust credentials này vào production.
- Nếu test SP phải ký AuthnRequest, cấu hình **SP signing key riêng** trong section signing, không sao chép IdP private key.

### 8.1. Spring SecurityFilterChain

Tệp `SamlSecurityConfig.java` trong Spring Boot project:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Mã trên là **Spring configuration class**, không phải Java standalone. Nó cố ý sử dụng default SAML provider/validators thay vì tự Base64-decode và tạo Authentication. Cần dependencies, registration, metadata, test IdP và ACS thật. Đối với HTTP-POST SAMLResponse, Spring Security thực thi filter/CSRF policy riêng; đừng vô hiệu hóa CSRF trên toàn bộ ứng dụng.

### 8.2. Maven dependencies

Fragment nằm trong Spring Boot POM đã có parent/BOM:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Không tự đoán version OpenSAML, Santuario và Spring từ một snippet; phải dùng bộ dependency tương thích. Một số releases cần Shibboleth Maven repository. `spring-security-test` hỗ trợ MockMvc/business authorization tests nhưng **không tự thay thế việc verify signed SAMLResponse thật**.

## 9. Một unsigned SAML XML scaffold để kiểm negative case

Ví dụ sau chỉ minh họa cấu trúc fields cần fixture generator xây dựng. Nó **không có XML Signature**, vì vậy khi đưa vào SP yêu cầu trusted signature thì **phải bị reject**, dù các trường còn lại có vẻ hợp lệ.

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_r1"
    Version="2.0"
    IssueInstant="2026-06-01T12:00:00Z"
    Destination="https://portal.test.example/login/saml2/sso/fixture-idp"
    InResponseTo="_request_001">

  <saml:Issuer>urn:example:saml:test-idp:alpha</saml:Issuer>

  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="_a1" Version="2.0"
      IssueInstant="2026-06-01T12:00:00Z">

    <saml:Issuer>urn:example:saml:test-idp:alpha</saml:Issuer>

    <saml:Subject>
      <saml:NameID
          Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">synthetic-user-001</saml:NameID>

      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://portal.test.example/login/saml2/sso/fixture-idp"
            InResponseTo="_request_001"
            NotOnOrAfter="2026-06-01T12:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-06-01T11:59:00Z"
        NotOnOrAfter="2026-06-01T12:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>urn:example:saml:test-sp:portal</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
        AuthnInstant="2026-06-01T11:59:55Z">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>

  </saml:Assertion>
</samlp:Response>
~~~

**Các điểm chú ý:**
- Response và Assertion phải có IDs duy nhất.
- `Issuer` phải là test IdP thực sự đáng tin.
- `Destination` và `SubjectConfirmationData.Recipient` phải đúng ACS.
- `AudienceRestriction` phải khớp SP entityID.
- `InResponseTo` phải khớp **AuthnRequest đang pending**, không phải constant tùy ý trong E2E.
- `NotOnOrAfter` hết hạn nên assertion static này không thể dùng làm positive fixture sau tháng 6/2026 trên real clock.
- NameID synthetic phải map tới local test account.
- **Thiếu Signature** → expected reject. Muốn positive case, generator phải ký bằng XMLDSig, không paste một SignatureValue giả.

## 10. Sinh SAML signature thật bằng test IdP hoặc OpenSAML

SAML XML Signature không phải JCA ký trực tiếp toàn chuỗi XML. Cần:
- Tạo SAML `Response` và `Assertion` objects theo schema/profile.
- Đặt issuer, subject, audience, recipient, times, correlation, attributes.
- Gắn `ds:Signature` ở Response hoặc Assertion phù hợp.
- Đặt approved SignatureMethod, DigestMethod, canonicalization và transforms.
- Reference tới đúng ID của signed Response/Assertion.
- Dùng **test IdP private key** để tạo chữ ký.
- Marshall XML và thực hiện signer theo API OpenSAML hỗ trợ.
- Không sửa signed XML nodes sau khi ký.
- Gửi SAMLResponse bằng HTTP-POST binding Base64 tới ACS.
- Spring SP dùng test public cert để verify XMLDSig.

**Không tạo signature bằng cách chèn raw Base64 bytes vào XML** hoặc dùng `SHA256withRSA` trên một string XML chưa canonicalize. Thư viện OpenSAML/SAML test IdP nên chịu trách nhiệm XMLDSig vì giữa các versions có sự khác nhau về APIs marshaling, algorithms và object models.

### 10.1. Response-signed, Assertion-signed và both-signed

| Fixture | Signature placement | Expected |
|---|---|---|
| valid-response-signed | Reference tới Response.ID | Accept khi assertion nằm trong verified Response subtree |
| valid-assertion-signed | Reference tới Assertion.ID | Accept khi consumed assertion được ký |
| valid-both-signed | Cả Response và Assertion | Accept nếu signatures và rules đều đúng |
| unsigned | Không có chữ ký tin cậy | Reject |
| wrong-key | Được ký bằng test key B, SP chỉ trust A | Reject untrusted signer |
| tampered | Sửa content được ký sau signing | Reject signature |
| multiple-assertions | Signed A1 nhưng app muốn dùng unsigned A2 | Reject XSW hoặc schema/policy |

Spring Security/OpenSAML thường yêu cầu Response hoặc toàn bộ Assertions được signed đúng policy; không tự vô hiệu hóa checks để làm “fixture chạy”.

### 10.2. Signature References và ID

- XMLDSig `Reference URI="#_r1"` ký Response ID `_r1`.
- `Reference URI="#_a1"` ký Assertion ID `_a1`.
- IDs phải duy nhất, không duplicate ID resolution.
- Không external URI/file references hoặc transforms ngoài allowlist.
- Không tự chấp nhận KeyInfo certificate như trust anchor.
- Không read raw XML bằng `getElementsByTagName("NameID")` sau khi verify một node khác.
- Consumed NameID/Attributes phải đến từ **exact validated protected assertion**.

## 11. Ba kiểu negative fixtures cần tách biệt

### 11.1. Negative mật mã: sửa sau khi ký

Tạo SAMLResponse hợp lệ, ký bằng key A, **sau đó** thay một byte thuộc signed content (ví dụ NameID). Không ký lại. Kỳ vọng XMLDSig digest/signature verification FAIL. Đây không phải test Audience validation.

### 11.2. Negative trust: signer khác approved key

Tạo SAMLResponse với mọi fields hợp lệ, nhưng ký bằng private key B. Khi SP chỉ trust certificate A, chữ ký toán học dưới public key B có thể đúng, nhưng **signer không được IdP registration cho phép** → reject.

Đừng giải quyết bằng cách đọc certificate B từ `ds:KeyInfo` rồi coi là trusted. Đây là kiểm soát cốt lõi.

### 11.3. Negative protocol: ký đúng fields bị sai

Để test Audience:
1. Tạo Assertion có Audience sai.
2. Giữ Issuer, Recipient, Destination, time, request correlation hợp lệ khác.
3. Ký **Assertion sai Audience** bằng test private key A.
4. Spring verify chữ ký PASS nhưng AudienceRestriction validation FAIL.

Tương tự cho Recipient, Destination, InResponseTo, expired/future Conditions, SubjectConfirmation, Response Status và wrong issuer. **Nếu sửa Audience sau signing, lỗi đầu tiên sẽ là signature**, không chứng minh audience validator hoạt động.

## 12. Key rotation fixtures

Dùng A/B ở các giai đoạn:

| Phase | Trust set phía test SP | Key ký Response | Kỳ vọng |
|---|---|---|---|
| Baseline | A | A | Accept |
| Baseline | A | B | Reject |
| Overlap | A, B | A | Accept |
| Overlap | A, B | B | Accept |
| Retired A | B | B | Accept |
| Retired A | B | A | Reject |
| Cross IdP | Alpha trust A | Issuer beta, signer B | Reject |
| Untrusted KeyInfo | A | Signer B, KeyInfo B | Reject |

Key rotation không đồng nghĩa IdP issuer phải đổi. Với **cùng IdP rotating signing keys**, A/B đều thuộc issuer alpha trong khoảng thời gian phê duyệt. Với **cross-IdP scenario**, issuer alpha/beta khác nhau và trust phải tách theo registration.

## 13. Java 17 chạy độc lập: kiểm chữ ký với đúng test key

Mã JDK 17 dưới đây tạo hai RSA keypairs ngẫu nhiên trong bộ nhớ, ký một byte message bằng key A, verify với public A, kiểm tamper và wrong key B. **Đây là JCA demo về key separation, không phải SAML XMLDSig signer**, vì nó không thực hiện XML Reference/canonicalization.

Tệp `TestSigningKeysDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;

public class TestSigningKeysDemo {

    static boolean verify(
            byte[] message,
            byte[] signedBytes,
            PublicKey trustedKey) throws Exception {

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedKey);
        verifier.update(message);
        return verifier.verify(signedBytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair testIdpA = generator.generateKeyPair();
        KeyPair testIdpB = generator.generateKeyPair();

        byte[] data =
                "synthetic-test-response".getBytes(StandardCharsets.UTF_8);
        byte[] changed =
                "modified-test-response".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(testIdpA.getPrivate());
        signer.update(data);
        byte[] signed = signer.sign();

        System.out.println("valid-a=" +
                verify(data, signed, testIdpA.getPublic()));

        System.out.println("tampered=" +
                verify(changed, signed, testIdpA.getPublic()));

        System.out.println("wrong-b=" +
                verify(data, signed, testIdpB.getPublic()));

        System.out.println("real-saml-xmldsig=false");
    }
}
~~~

Chạy:

~~~bash
javac TestSigningKeysDemo.java
java TestSigningKeysDemo
~~~

**Stdout chính xác:**

~~~text
valid-a=true
tampered=false
wrong-b=false
real-saml-xmldsig=false
~~~

**Lưu ý:**
- Private key A/B ngẫu nhiên, không in ra log.
- Bài tập dùng RSA 2048 để chạy nhanh trong JDK demo, còn lệnh OpenSSL ở trên tạo RSA 3072 cho full test keys.
- `valid-a` đúng vì public A tương ứng private A.
- `tampered` và `wrong-b` đều false.
- Đây là ký trực tiếp một byte string. Real SAML yêu cầu XMLDSig Signature/Digest/Reference/Transforms và IdP trust verification; tuyệt đối không dùng class này làm SAML authentication provider.

## 14. Java 17 chạy độc lập: kiểm SAML fixture policy theo clock cố định

Bài demo tiếp theo **giả định** signature và IdP trust đã được framework verify. Nó mô phỏng Audience, Recipient, InResponseTo, Conditions và replay để thấy cách thiết kế các negative fixtures độc lập.

Tệp `SamlFixtureRulesDemo.java`:

~~~java
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public class SamlFixtureRulesDemo {

    static final String ISSUER = "urn:example:saml:test-idp:alpha";
    static final String AUDIENCE = "urn:example:saml:test-sp:portal";
    static final String ACS =
            "https://portal.test.example/login/saml2/sso/fixture-idp";
    static final String REQUEST = "_request_001";

    record Fixture(
            String assertionId,
            String issuer,
            String audience,
            String recipient,
            String inResponseTo,
            Instant notBefore,
            Instant notOnOrAfter,
            String subject) {
    }

    static String validate(
            Fixture f, Instant now, Set<String> seen) {

        if (!ISSUER.equals(f.issuer())) {
            return "REJECT_ISSUER";
        }
        if (!AUDIENCE.equals(f.audience())) {
            return "REJECT_AUDIENCE";
        }
        if (!ACS.equals(f.recipient())) {
            return "REJECT_RECIPIENT";
        }
        if (!REQUEST.equals(f.inResponseTo())) {
            return "REJECT_CORRELATION";
        }
        if (now.isBefore(f.notBefore())
                || !now.isBefore(f.notOnOrAfter())) {
            return "REJECT_TIME";
        }
        if (!seen.add(f.assertionId())) {
            return "REJECT_REPLAY";
        }
        return "ACCEPT:" + f.subject();
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-06-01T12:00:00Z");
        Instant start = Instant.parse("2026-06-01T11:59:00Z");
        Instant end = Instant.parse("2026-06-01T12:05:00Z");

        Fixture good = new Fixture(
                "_a1", ISSUER, AUDIENCE, ACS,
                REQUEST, start, end, "synthetic-user-001");

        Set<String> seen = new HashSet<>();
        System.out.println("good=" + validate(good, now, seen));
        System.out.println("replay=" + validate(good, now, seen));

        Fixture wrongAudience = new Fixture(
                "_a2", ISSUER, "urn:example:other-sp", ACS,
                REQUEST, start, end, "synthetic-user-001");
        System.out.println("audience=" +
                validate(wrongAudience, now, new HashSet<>()));

        Fixture wrongRecipient = new Fixture(
                "_a3", ISSUER, AUDIENCE, "https://other.test.example/acs",
                REQUEST, start, end, "synthetic-user-001");
        System.out.println("recipient=" +
                validate(wrongRecipient, now, new HashSet<>()));

        Fixture expired = new Fixture(
                "_a4", ISSUER, AUDIENCE, ACS,
                REQUEST, start, now, "synthetic-user-001");
        System.out.println("expired=" +
                validate(expired, now, new HashSet<>()));

        Fixture wrongRequest = new Fixture(
                "_a5", ISSUER, AUDIENCE, ACS,
                "_wrong_request", start, end, "synthetic-user-001");
        System.out.println("correlation=" +
                validate(wrongRequest, now, new HashSet<>()));
    }
}
~~~

Chạy:

~~~bash
javac SamlFixtureRulesDemo.java
java SamlFixtureRulesDemo
~~~

**Stdout chính xác:**

~~~text
good=ACCEPT:synthetic-user-001
replay=REJECT_REPLAY
audience=REJECT_AUDIENCE
recipient=REJECT_RECIPIENT
expired=REJECT_TIME
correlation=REJECT_CORRELATION
~~~

**Giới hạn:**
- `validate` không kiểm XML signature, issuer trust, Destination/Status, SubjectConfirmationData đầy đủ, encrypted Assertions hay schema.
- `HashSet` chỉ mô phỏng replay trong một JVM, không phải distributed production replay cache.
- Fixed clock thuộc bài tập, không tự thay đổi Spring/OpenSAML clock trừ khi API/validator có hook cụ thể.
- Kết quả `ACCEPT` trong class chỉ là “pass các kiểm tra mô phỏng”, **không** có nghĩa Spring Security đã tạo session.

## 15. Test clock, freshness và request correlation

**Với unit tests**, có thể cố định:
~~~text
now = 2026-06-01T12:00:00Z
NotBefore = 2026-06-01T11:59:00Z
NotOnOrAfter = 2026-06-01T12:05:00Z
~~~

Nhưng dữ liệu static này **đã hết hạn trên real clock sau tháng 6/2026**. Đừng tắt SAML time validation hoặc kéo clock skew quá lớn chỉ để static fixture “pass”. Dùng:
- Injectable clock khi component cụ thể hỗ trợ.
- Timestamps mới sinh lúc E2E test chạy từ UTC clock.
- Unique Response.ID và Assertion.ID cho mỗi positive transaction.
- SubjectConfirmationData.NotOnOrAfter theo thời hạn bearer phù hợp.
- Actual AuthnRequest.ID được SP sinh và lưu trong session.

### 15.1. InResponseTo không được hardcode trong full HTTP E2E

SP-initiated SSO:
1. Browser yêu cầu route protected.
2. SP sinh AuthnRequest với ID mới.
3. Test IdP nhận request, lấy đúng ID sau khi validate routing/signature khi cần.
4. Response.InResponseTo và SubjectConfirmationData.InResponseTo tham chiếu ID đó.
5. SP kiểm correlation.

Nếu fixture luôn gửi `_request_001` trong khi SP đang chờ `_request_999`, lỗi correlation là đúng. Đừng “sửa” bằng disable InResponseTo.

**IdP-initiated SSO** có thể không có InResponseTo theo profile riêng; chỉ test khi deployment bật unsolicited flow có policy riêng. Không coi đó là positive SP-initiated fixture.

### 15.2. Replay case phải phân biệt với correlation

Dùng cùng signed assertion ID/Response bytes hai lần và kiểm rejection theo replay policy. Nhưng một số lần submit thứ hai đã fail vì AuthnRequest state bị tiêu thụ, không nhất thiết chứng minh replay cache hoạt động. Test replay đúng cần cô lập đường kiểm:
- Provider/session correlation.
- Assertion ID replay store.
- TTL và multi-node consistency.

Không mặc định một sản phẩm tự chặn mọi biến thể replay nếu chưa cấu hình/hợp đồng kiểm thử.

## 16. Bộ test matrix theo đúng ranh giới

| Case | Dữ liệu hoặc thay đổi | Expected |
|---|---|---|
| P01 | Response ký bằng key A, claims/conditions hợp lệ | Authentication success |
| P02 | Assertion ký bằng key A, Response context hợp lệ | Authentication success |
| P03 | Cả Response và Assertion được ký đúng | Authentication success |
| P04 | Overlap key rotation A+B, ký bằng B | Accept nếu B trong trusted credentials |
| P05 | IdP A valid, local active user thuộc tenant | Approved authorities only |
| N01 | Response và Assertion đều unsigned | Reject signature requirement |
| N02 | Đổi NameID sau signing | Reject digest/signature |
| N03 | Đổi Audience sau signing | Reject digest/signature |
| N04 | Wrong Audience rồi ký **sau khi thay** | Reject Audience |
| N05 | Wrong Recipient rồi ký đúng | Reject Recipient |
| N06 | Wrong Destination rồi ký đúng | Reject Destination |
| N07 | Wrong InResponseTo rồi ký đúng | Reject correlation |
| N08 | NotBefore ở tương lai, ký đúng | Reject time |
| N09 | NotOnOrAfter đã hết hạn, ký đúng | Reject time |
| N10 | SubjectConfirmationData expired, ký đúng | Reject bearer confirmation |
| N11 | Status không Success, ký đúng | Reject protocol |
| N12 | Issuer khác registered IdP, ký đúng | Reject issuer |
| N13 | Key B ký, SP chỉ trust A | Reject untrusted signer |
| N14 | KeyInfo chứa attacker key, SP trust A | Reject untrusted signer |
| N15 | Duplicate Response/Assertion IDs | Reject ambiguous ID |
| N16 | Signed A1 và unsigned A2, app dùng A2 | Reject XSW |
| N17 | Reference URI ký node không được dùng | Reject signed target |
| N18 | External XML entity / DTD | Reject parser |
| N19 | Huge XML / deep nesting | Reject limits |
| N20 | Replay same assertion ID | Reject replay according to policy |
| N21 | IdP-initiated khi disabled | Reject unsolicited |
| N22 | Issuer A nhưng registration thuộc B | Reject multi-IdP mix-up |
| N23 | Valid SAML nhưng local account disabled | Deny business access |
| N24 | Valid SAML nhóm UntrustedAdmin | Không tự cấp ROLE_ADMIN |
| N25 | EncryptedAssertion wrong SP key | Reject decryption |
| N26 | SHA-1/MD5 outside policy | Reject algorithm |
| N27 | Key A retired, response vẫn ký bằng A | Reject |
| N28 | RelayState external URL không approved | Không open redirect |
| N29 | Same NameID ở IdP B nhưng không linked | Không merge account |
| N30 | SAML Response signed đúng nhưng SP EntityID khác | Reject cross-SP replay |

**Kỹ thuật quan trọng:** Với N04–N12, phải tạo field sai **trước khi ký**, để signature verification vẫn PASS và protocol validator thực sự bị thử. Với N02–N03, cố ý sửa **sau khi ký** để thử digest/signature. Với N13–N14, signature mathematically valid bằng B nhưng SP không trust signer. Ba nhóm không được nhập làm một.

### 16.1. XSW và signed-object/consumed-object matching

XML Signature Wrapping có thể xảy ra khi verifier xác minh Assertion A nhưng app đọc NameID/Attributes từ Assertion B chưa ký. Test cần kiểm:
- Reference URI trỏ đúng expected Response/Assertion.
- XML ID duy nhất, không duplicate.
- Strict XML structure/namespace.
- Application không dùng `getElementsByTagName` hoặc global XPath trên raw XML để chọn security claims.
- Chỉ dùng `Saml2AuthenticatedPrincipal` đã được OpenSAML/Spring xác minh.
- Không trộn NameID và AttributeStatement giữa các Assertions.

Một signed Response thực sự bao phủ assertion subtree sẽ fail digest nếu bạn sửa nội dung subtree đó. XSW exploits dựa vào **selection/scope/parser ambiguity**, không phải phép màu vượt qua RSA.

## 17. Kiểm thử trên Spring Security/OpenSAML thật

Phải phân biệt ba tầng:

**Unit tests**
- Java 17 JCA key separation.
- Fixture manifest, role mapping, fake-clock policy.
- Synthetic identity/tenant lookup.
- Không chứng minh real XMLDSig validity.

**Provider-level integration tests**
- Test generator tạo XML SAML Response/Assertion thực sự signed.
- Spring `OpenSaml5AuthenticationProvider` (hoặc provider tương ứng phiên bản) verify bằng trusted RelyingPartyRegistration.
- Assert đúng principal/attributes sau validation.
- Test key trust, Audience, Recipient, Conditions, Assertion signature coverage.

**HTTP end-to-end tests**
- Browser/test client kích hoạt `/saml2/authenticate/{registrationId}` hoặc GET protected resource.
- Spring sinh AuthnRequest.
- Test IdP nhận request và phát signed SAMLResponse qua HTTP POST.
- Browser POST `SAMLResponse` Base64 tới `/login/saml2/sso/{registrationId}`.
- Spring xử lý ACS, cookies, state, InResponseTo.
- Kiểm authenticated session hoặc rejection.
- Test logout/expiration/replay theo policy.

**Không đủ:** Chỉ mock một Spring `Authentication` trong MockMvc rồi nói “SAML signed response đã được kiểm thử”. MockMvc rất hữu ích cho business authorization, nhưng không thay XMLDSig/OpenSAML integration tests.

### 17.1. HTTP status không phải assertion cuối cùng

SAML Web SSO có thể trả 302 redirect về trang login/success và thay đổi theo failure handler. Test nên khẳng định:
- Có/không có `SecurityContext.Authentication`.
- `Authentication.getPrincipal()` là validated `Saml2AuthenticatedPrincipal`.
- Subject/NameID đúng synthetic user expected.
- Role/authority chỉ theo policy.
- Local session không được tạo khi input invalid.
- Error category rõ trong test logs, không chứa raw secrets.

Đừng chỉ assert HTTP status 200/302.

## 18. CI/CD an toàn cho fixture generation

Pipeline:

~~~text
Checkout test code
      |
      v
Scan secrets + verify test-only environment
      |
      v
Generate ephemeral IdP test signing key/cert
      |
      v
Start isolated test IdP + Spring SP with test public cert
      |
      v
Generate fresh XMLDSig signed positive fixtures
      |
      v
Generate signed protocol-negative fixtures
      |
      v
Generate wrong-key and tamper-after-sign fixtures
      |
      v
Run OpenSAML provider tests + HTTP ACS E2E
      |
      v
Write sanitized JUnit reports
      |
      v
Delete ephemeral keys, tokens, SAML dumps and sessions
~~~

### 18.1. Không rò secret qua CI

- Test private signing keys chỉ ở ephemeral secret volume/CI secret store.
- Không bật shell debug `set -x` khi thao tác secret.
- Không ghi PEM private key vào build logs.
- Không commit private key, không đưa vào Docker layer/public artifact.
- Public cert test có thể versioned khi đã cố định profile và scope.
- Restrict external forks/priviliged CI jobs khỏi test secret manager.
- Không mount production secrets vào namespace test.
- Không publish raw SAMLResponse mang PII hoặc access tokens.
- Dọn keyfiles sau job, nhưng nhớ file deletion không xóa các bản sao đã upload/snapshot.
- Secret scanning và deployment guard chặn test cert hiện diện trong production trust config.

### 18.2. Production guard là yêu cầu độc lập

Trước rollout production:
1. Không có issuer `urn:example:saml:test-idp:alpha` trong production registration.
2. Không có public test certificate fingerprint trong production trust list.
3. Không kích hoạt `application-saml-test.yml`.
4. Không có code fallback `acceptAnySamlSignature` hoặc disabled validators.
5. IdP metadata production được approved qua kênh tin cậy.
6. SP signing/decryption secrets production chỉ xuất hiện đúng nơi cần.

Nếu guard fail, block deploy. Không tự mở rộng trust để cho SAML test login hoạt động trên prod.

## 19. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| XML nhìn đúng nhưng login fail | Chưa có XMLDSig | Dùng real OpenSAML/test IdP signer |
| SignatureValue fail | Signed content bị sửa / wrong transforms | Kiểm Reference, digest, canonicalization |
| Signer B verify bằng B nhưng Spring reject | SP chỉ trust A | Đúng negative trust |
| Wrong Audience test fail signature trước | Sửa Audience sau khi ký | Tạo sai trước, sign sau |
| Signed Response pass nhưng Assertion-signed fail | Sai profile/Reference/conditions | Kiểm signing mode và verifier |
| Static positive fixture đã expired | NotOnOrAfter trong quá khứ | Fresh timestamps hoặc inject clock |
| InResponseTo không match | Không lấy actual AuthnRequest ID | Test full SP-initiated choreography |
| Destination/Recipient mismatch | ACS URL hoặc reverse proxy sai | Kiểm HTTPS scheme/host/port/path |
| Unknown registrationId | URL routing/config profile sai | Kiểm test RelyingPartyRegistration |
| Test IdP metadata cert khác signer | Cert/key pair mismatch | So OpenSSL public keys/fingerprint |
| Key rollover B không pass | B chưa được thêm vào trust | Kiểm phase và approved certs |
| A vẫn pass sau retirement | Trust A chưa được remove | Fail rotation test |
| Duplicate ID pass và lấy wrong subject | XML Signature Wrapping | Hardening parser/Reference checks |
| Test group Admin tạo ROLE_ADMIN | Role mapping ngoài allowlist | Kiểm trusted attributes/policy |
| One pod fail | Cert clock/cache khác | Đồng bộ nodes và replay store |
| XML có XXE mà parser vẫn xử lý | Secure parser config thiếu | Chặn DTD/external entities |
| Test cert vô tình nằm trong prod | Deployment guard thiếu | Block release, kiểm incident scope |
| Cert hết hạn | Test cert lifecycle | Reissue cert, không tắt security checks |
| Test logout xong lại SSO ngay | IdP session vẫn có | Phân biệt local session với IdP SSO |

**Debug lần lượt:** keypair → cert fingerprint → manifest/test profile → XMLDSig signature/Reference → IdP issuer trust → SAML conditions/correlation → session/replay → local account/role.

## 20. Checklist chất lượng bộ dữ liệu

- [ ] Test IdP private signing key **khác** production key và không xuất hiện ở SP.
- [ ] Test private key bảo vệ trong secret store/ephemeral CI volume.
- [ ] Public certificate test được pin vào đúng relying-party registration.
- [ ] Metadata issuer, SSO endpoint, ACS/SP entityID nhất quán.
- [ ] Positive Response-signed và Assertion-signed đều dùng **XMLDSig thật**.
- [ ] NameID/Attributes chỉ từ assertion được chữ ký tin cậy bảo vệ.
- [ ] Có negative tamper-after-sign → signature reject.
- [ ] Có negative wrong-signing-key → untrusted signer reject.
- [ ] Có negative Audience/Recipient/InResponseTo sai **nhưng signature đúng**.
- [ ] Có negative NotBefore/NotOnOrAfter và SubjectConfirmation expiration.
- [ ] Có XSW/duplicate ID, unsupported multiple Assertions tests.
- [ ] Có replay, unsolicited flow, multi-IdP và tenant tests.
- [ ] Có rotation overlap A+B và retirement A.
- [ ] Có local disabled user và group-to-role allowlist tests.
- [ ] Không dùng PII, email hoặc tokens production trong fixtures.
- [ ] Test clock/IDs/correlation được quản lý tường minh.
- [ ] Full HTTP ACS integration chạy với test IdP signer thật.
- [ ] Không disable Spring default SAML validators trong tests.
- [ ] CI secret scanning và artifact cleanup hoạt động.
- [ ] Prod deployment guard từ chối test issuer/cert.
- [ ] Tài liệu fixture mô tả purpose, signer, expected failure reason và lifecycle.

## 21. Câu hỏi ôn tập

1. **Vì sao phải có test IdP signing key riêng?** Không cho CI có năng lực ký thay IdP production.
2. **SP dùng private key của test IdP để verify không?** Không, SP dùng public certificate.
3. **Test SP signing private key dùng làm gì?** Ký AuthnRequest/LogoutRequest khi cần, tách với IdP key.
4. **SP decryption private key có phải IdP verification certificate không?** Không.
5. **Self-signed test certificate có thể dùng không?** Có, nếu trust được pin/approved theo test registration.
6. **Có certificate là đã ký XML chưa?** Chưa, cần XMLDSig.
7. **JCA SHA256withRSA trên UTF-8 string có tạo SAML XML signature không?** Không, cần Reference/Digest/C14N/transforms.
8. **Để test wrong Audience, sửa trước hay sau signing?** Trước rồi ký lại.
9. **Để test signature tampering, sửa trước hay sau signing?** Sau, không ký lại.
10. **Wrong key B với issuer A test gì?** Certificate trust đúng registration.
11. **KeyInfo tự quyết định key đáng tin không?** Không.
12. **Static positive XML có dùng mãi được không?** Không nếu hết thời gian/correlation/replay.
13. **InResponseTo cần giá trị nào?** Exact pending AuthnRequest ID.
14. **Response-signed có thể bảo vệ Assertion không ký riêng không?** Có nếu Assertion nằm trong signed Response scope và profile hợp lệ.
15. **XSW xảy ra khi nào?** Chữ ký verify object A nhưng app đọc claims từ object B.
16. **MockMvc principal đã mock có test XMLDSig không?** Không.
17. **Test certificate A có nên cài production trust không?** Không.
18. **Key rotation test cần những trạng thái nào?** A-only, A+B overlap, B-only.
19. **Local account disabled nhưng SAML valid?** App vẫn phải deny business access.
20. **Tại sao không chỉ assert HTTP 200?** SSO redirect/failure handlers có thể trả 302; cần kiểm SecurityContext/principal.
21. **Dùng subject thật cho test có lợi gì?** Không nên; tạo synthetic identities.
22. **Không có signature nhưng Audience đúng có login không?** Không.
23. **Tại sao phải test replay?** Chữ ký có thể còn hợp lệ trên assertion cũ, nhưng việc dùng lại phải bị chặn theo policy.
24. **Cốt lõi để đạt QA?** Khóa riêng biệt, XMLDSig thật, trust đúng, protocol checks, expected negatives và CI isolation.

## 22. Nguồn tham khảo chính thức

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — Relying Party Registration and Credentials: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- Spring Boot — SAML 2.0 Relying Party Properties: https://docs.spring.io/spring-boot/reference/security/saml2.html
- Spring Security — Servlet Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Security — MockMvc Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- OWASP — SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- OWASP — XML External Entity Prevention: https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html
- W3C — XML Signature Syntax and Processing 1.1: https://www.w3.org/TR/xmldsig-core1/
- W3C — XML Signature Best Practices: https://www.w3.org/TR/xmldsig-bestpractices/
- OASIS — SAML 2.0 Core: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS — SAML 2.0 Profiles, Web Browser SSO: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS — SAML 2.0 Metadata: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OpenSSL — genpkey: https://docs.openssl.org/3.0/man1/openssl-genpkey/
- OpenSSL — req and self-signed certificates: https://docs.openssl.org/3.0/man1/openssl-req/
- OpenSSL — x509 inspection: https://docs.openssl.org/3.0/man1/openssl-x509/

**Tổng kết:** Một bộ SAML2 fixtures đáng tin phải dùng **IdP test private key được cô lập**, public verification certificate chỉ gắn với **test RelyingPartyRegistration**, đúng IdP metadata, synthetic users, XMLDSig signatures thật, fresh IDs/timestamps/correlation, expected security outcomes rõ ràng và CI không rò secrets. Tách ba lớp lỗi: **tamper-after-sign → signature failure**, **wrong signer → trust failure**, **invalid SAML field nhưng ký đúng → protocol validation failure**. Cuối cùng, chỉ tạo Spring Security Authentication từ assertion đã được **trusted signature** bảo vệ và qua đầy đủ audience/recipient/conditions/correlation/replay checks, sau đó kiểm local account/tenant/role độc lập.
