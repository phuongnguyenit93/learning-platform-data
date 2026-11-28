# Kiểm thử chứng chỉ hết hạn, không tin cậy và thiếu khóa phù hợp

Trong tích hợp SOAP doanh nghiệp, một request có thể đúng **WSDL**, đúng **XSD**, marshal thành JAXB payload hợp lệ và đi đến đúng URL nhưng vẫn bị từ chối vì **chứng chỉ hết hạn, không thuộc tập tin cậy hoặc phía thực hiện thao tác mật mã không sở hữu khóa riêng phù hợp**. Ba trường hợp này nhìn giống nhau ở bề mặt — “lỗi certificate/security” — nhưng khác căn nguyên, tầng xử lý và phương pháp kiểm thử.

Ví dụ, SOAP client gọi `https://partner.example.org/soap/orders`. Nếu chứng chỉ HTTPS của server hết hạn, **TLS handshake** có thể thất bại trước khi gửi SOAP. Nếu kết nối HTTPS thành công nhưng SOAP request được ký bởi một chứng chỉ đối tác không được tin cậy, **Apache WSS4J** trên Spring Web Services (Spring-WS) có thể từ chối request bằng security fault. Nếu client được cấu hình ký request bằng alias không có private key, quá trình **securement outbound** có thể lỗi ngay tại client, trước HTTP POST. Một log chung `SOAP call failed` không đủ phân biệt các trường hợp đó.

Bài thuộc chương **Chứng chỉ và khóa** của module **SPRING_WEB_SERVICES**: phát triển dịch vụ SOAP **contract-first** với XSD/WSDL, JAXB/OXM, endpoint và client; tích hợp SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Trọng tâm ở đây là xây dựng **bộ kiểm thử âm (negative tests)** đáng tin cậy cho các trường hợp **expired / untrusted / missing or mismatched key**, thay vì tắt xác minh TLS hoặc nới lỏng WS-Security để request “chạy được”.

## 1. Kết quả học tập và phạm vi

Sau bài này, bạn cần:

1. Phân biệt **chứng chỉ X.509**, **public key**, **private key**, **certificate chain**, **truststore** và **keystore**.
2. Xác định lỗi thuộc **TLS/mTLS**, **WS-Security Signature**, **WS-Security Encryption** hay **quản lý key material**, không đổ chung cho SOAP/JAXB.
3. Chuẩn bị các fixture chứng chỉ **hợp lệ, hết hạn, chưa có hiệu lực, không đáng tin và sai mục đích sử dụng**.
4. Kiểm thử **thiếu private key, alias sai, password sai, key/certificate không khớp và recipient key không phù hợp**.
5. Xác minh **failure ở đúng tầng**, **không gọi nghiệp vụ**, **không rò bí mật**, không nhầm SOAP Fault với lỗi TLS/HTTP.
6. Kiểm thử **cả hai hướng client ↔ server**, bao gồm chứng chỉ TLS, mTLS và WS-Security dùng cho chữ ký/mã hóa.
7. Thiết kế test CI có kết quả ổn định, không sửa đồng hồ máy build, không dùng production keys và không cho phép trust-all.

### Tiêu chí “test đạt”

Một **negative test đạt** khi cấu hình cố ý sai bị **từ chối theo đúng security policy** và có bằng chứng kiểm chứng:

- Kết nối/message dừng ở tầng được mong đợi.
- Không có tác dụng phụ nghiệp vụ; với request cố gắng sửa trạng thái, verify service/repository **không được gọi hoặc transaction không commit**.
- Không có fallback từ HTTPS sang HTTP, từ mTLS sang unauthenticated, từ signed SOAP sang unsigned SOAP.
- Không sử dụng certificate verification bypass, `TrustAllStrategy` hoặc `NoopHostnameVerifier`.
- Client nhận được loại lỗi phù hợp: **SSL/TLS error**, **WS-Security SOAP Fault** hoặc **local signing/decryption error**.
- Logs/metrics có thể phân loại lỗi mà **không lộ private key, mật khẩu, UsernameToken, SOAP Body nhạy cảm**.

**Quan trọng:** “test âm thành công” nghĩa là **hành vi từ chối được kiểm chứng**, không phải request HTTP trả thành công.

## 2. Bốn vai trò của chứng chỉ và khóa

Trong một hệ thống Spring-WS, cùng một từ “chứng chỉ” có thể nói tới bốn vai trò khác nhau:

| Vai trò | Material ở bên gửi/nhận | Dùng cho | Nếu lỗi |
| --- | --- | --- | --- |
| **TLS server identity** | HTTPS server có private key + certificate chain; client có trust anchors | Client xác minh máy chủ và kênh HTTPS | TLS handshake/hostname validation lỗi |
| **mTLS client identity** | SOAP client có private key + certificate chain; server có trust anchors | Server xác minh client ở tầng kết nối | TLS handshake/client-auth lỗi |
| **WS-Security signer** | Bên ký có private key; bên verify có public certificate/trust chain | Ký SOAP Body/Headers và kiểm tra chữ ký | Local sign error hoặc WSS4J signature validation fault |
| **WS-Security encryption recipient** | Bên gửi mã hóa bằng public key recipient; bên nhận giải mã bằng private key tương ứng | Bí mật nội dung SOAP | Không tạo được encryption hoặc decrypt/validation fault |

~~~mermaid
flowchart LR
    C["SOAP client"] -->|"HTTPS / TLS server certificate"| T["Spring-WS SOAP server"]
    C -->|"mTLS client certificate (nếu cần)"| T
    C -->|"SOAP Header ds:Signature<br/>ký bằng private key client"| V["WSS4J trên server<br/>verify bằng trust Crypto"]
    V --> T
    T -->|"SOAP encrypted response<br/>mã hóa bằng public key client"| D["WSS4J trên client<br/>private key giải mã"]
~~~

### 2.1. Public key, private key và chứng chỉ

- **Private key** là bí mật, dùng cho thao tác ký hoặc giải mã phù hợp thuật toán. Không gửi cho đối tác và không commit vào Git.
- **Public key** được gắn với danh tính/thuộc tính trong **X.509 certificate** và có thể dùng xác minh chữ ký hoặc mã hóa cho chủ sở hữu private key tương ứng.
- **Certificate chain** dẫn từ leaf certificate qua intermediate CA đến **trust anchor**. Trust anchor phải được phía xác minh chấp nhận theo chính sách, không phải cứ certificate tự khai báo issuer là tin.
- **Truststore** là tập chứng chỉ/anchors dùng xác minh **đối tác**; thông thường **không cần private key**.
- **Keystore/identity store** của signer, server TLS hoặc mTLS client phải có **PrivateKeyEntry** và certificate chain phù hợp; chỉ chứa chứng chỉ công khai là chưa đủ cho thao tác cần private key.

Một certificate có thể dùng nhiều mục đích nếu policy cho phép, nhưng không nên tự giả định certificate TLS được dùng luôn để ký WS-Security. Các policy, key usages, rotation schedules và trust scopes có thể khác nhau.

### 2.2. Không phải lỗi nào cũng tạo SOAP Fault

~~~mermaid
flowchart TD
    A["WebServiceTemplate gọi SOAP"] --> B{"TLS handshake đạt?"}
    B -->|Không| C["SSLHandshakeException / transport error<br/>chưa có SOAP request được xử lý"]
    B -->|Có| D{"Client tạo được Signature/Encrypt?"}
    D -->|Không| E["WSS4J outbound securement error<br/>có thể chưa gửi HTTP POST"]
    D -->|Có| F["SOAP POST đến server"]
    F --> G{"Server WSS4J validation đạt?"}
    G -->|Không| H["Security SOAP Fault hoặc lỗi protocol<br/>không chạy domain"]
    G -->|Có| I["XSD/JAXB + authorization"]
    I --> J["Domain endpoint + response/Fault"]
~~~

Đây là **sơ đồ phân loại lỗi**, không phải thứ tự Java callbacks chính xác của mọi implementation. Khi client securement thực hiện trước transport, local signing error xảy ra trước POST. Ở server, endpoint mapping/XML parser có thể diễn ra trước security interceptor; bắt buộc thiết kế sao cho mọi tác dụng phụ **chỉ xảy ra sau security validation**.

## 3. Phân biệt các loại lỗi trước khi chọn fixture

| Kịch bản | Điều bị sai | Dấu hiệu thường gặp | Lỗi cần mong đợi |
| --- | --- | --- | --- |
| **Expired leaf** | `notAfter` trước thời điểm kiểm tra | `CertificateExpiredException` trong cause chain | TLS/WSS4J từ chối |
| **Not yet valid leaf** | `notBefore` sau thời điểm kiểm tra | `CertificateNotYetValidException` | TLS/WSS4J từ chối |
| **Untrusted signer/CA** | Không tạo được chuỗi tin cậy tới anchor hợp lệ | PKIX path/trust failure | TLS/WSS4J từ chối |
| **Incomplete chain** | Thiếu intermediate cần để build path | Path building failure ở một số môi trường | Từ chối nếu không có chain từ nguồn tin cậy khác |
| **Hostname mismatch** | SAN không khớp host HTTPS | Endpoint identification failure | TLS client từ chối |
| **Wrong EKU/KeyUsage** | Certificate không được dùng theo vai trò | Invalid usage / policy failure | Từ chối theo provider/policy |
| **No private key** | Keystore chỉ có trustedCertEntry | Không thể ký/decrypt/đáp ứng mTLS | Local crypto failure hoặc TLS client-auth failure |
| **Wrong alias** | Alias cấu hình không tồn tại hoặc trỏ key khác | No key/certificate found | Outbound sign/TLS init/decrypt fail |
| **Wrong key password** | Không mở được private-key entry | `UnrecoverableKeyException` hoặc provider-specific error | Local initialization/securement fail |
| **Key/certificate mismatch** | Public key certificate không đi với private key | Key/chain mismatch hoặc signature verify fail | Từ chối hoặc khởi tạo thất bại |
| **Wrong recipient** | SOAP mã hóa cho certificate không có private key ở bên nhận | Decryption failure | WSS4J inbound fault |
| **Revoked certificate** | CA đã thu hồi certificate | CRL/OCSP policy failure | Từ chối **nếu revocation được bật/phù hợp** |

**Không gộp “không tin cậy” với “hết hạn”:** một certificate có thể chưa hết hạn nhưng signer không đáng tin, hoặc hợp lệ về chain nhưng sai hostname. Kiểm thử mỗi điều kiện **độc lập**, chỉ thay một biến ở một lần test.

## 4. Thiết kế fixture: test CA, leaf certificates và identity stores

Hãy tạo một **PKI thử nghiệm độc lập**, hoàn toàn tách khỏi production. Thay vì sử dụng certificate thật từ đối tác, dựng các fixtures có tên và mục đích rõ ràng:

~~~text
Test CA A (được trust)
 ├── test-server-valid       (HTTPS serverAuth, SAN soap.test.local)
 ├── test-server-expired     (HTTPS serverAuth, SAN soap.test.local, NotAfter quá khứ)
 ├── test-client-valid       (mTLS clientAuth)
 ├── test-client-expired     (mTLS clientAuth, NotAfter quá khứ)
 ├── test-soap-signer-valid  (SOAP signature, digitalSignature)
 ├── test-soap-signer-expired
 └── test-soap-recipient     (SOAP encryption recipient, có private key)

Test CA B (KHÔNG được trust)
 ├── test-server-foreign
 └── test-soap-signer-foreign

Stores riêng:
 ├── test-server-identity.p12   (private key + chain)
 ├── test-client-identity.p12   (private key + chain)
 ├── test-client-trust.p12      (chỉ trust CA A)
 ├── test-server-trust.p12      (chỉ trust CA A)
 ├── test-soap-signing.p12      (private key signer + chain)
 ├── test-soap-verify-trust.p12 (chỉ trusted signer/CA)
 └── test-soap-decrypt.p12      (private key đúng recipient)
~~~

Đây là **sơ đồ fixture dự kiến**, không phải các tệp tồn tại trong workspace. Bài học **không tạo các file này**; chúng chỉ được tạo trong bước setup test của dự án khi cần.

### 4.1. Ma trận fixture tối thiểu

| Fixture | Thay đổi duy nhất | Điều cần cố định | Dùng để test |
| --- | --- | --- | --- |
| `valid` | Không | SAN, issuer, EKU, key alg, chain hợp lệ | Positive baseline |
| `expired` | Leaf `notAfter` trong quá khứ | Issuer/anchor/alias/usage đúng | Certificate expiry |
| `future` | Leaf `notBefore` trong tương lai | Các thuộc tính khác đúng | Not yet valid |
| `unknown-ca` | Leaf ký bởi CA B | Time, SAN, EKU đúng | Untrusted path |
| `missing-intermediate` | Bỏ intermediate khỏi chain gửi | Leaf/time/anchor đúng | Incomplete chain |
| `wrong-san` | SAN host khác | CA/time/usage đúng | TLS hostname mismatch |
| `wrong-eku` | Leaf chỉ có `clientAuth` khi cần `serverAuth` | Các thuộc tính khác đúng | Certificate purpose |
| `cert-only` | Keystore không có PrivateKeyEntry | Cert trùng với positive fixture | Missing private key |
| `wrong-alias` | Cấu hình alias khác | Keystore và cert giữ nguyên | Wrong alias |
| `wrong-key-password` | Password mở private key sai | Alias và cert giữ nguyên | Local key recovery |
| `wrong-recipient-key` | Encrypt bằng public cert B nhưng receiver chỉ có private key A | SOAP Body/algorithms đúng | Decryption mismatch |

**Với test expiry, luôn làm hỏng leaf certificate**, không dựa vào một root CA có `notAfter` quá khứ: cách một trust anchor được xử lý khác với leaf và có thể không kích hoạt cùng kiểm tra validity trên mọi trust provider.

### 4.2. Quy tắc giữ fixture an toàn

- Dùng khóa và certificate **chỉ cho test**, cấp bởi test CA riêng.
- Không sao chép private key production, client certificate thực hay password của đối tác.
- Nếu test keystore chứa private key giả và được lưu trong repository, áp kiểm soát phù hợp của tổ chức; **không** tái sử dụng nó ngoài thử nghiệm.
- Không dùng một khóa test làm certificate của các môi trường thật.
- Test CI chạy trong mạng cô lập, không dùng SOAP URL hoặc secret production.
- Phiên bản fixture nên có **metadata rõ**: subject, issuer, serial, SAN, EKU, NotBefore/NotAfter, fingerprint, use case.
- Positive fixture phải còn hiệu lực đủ xa; có cảnh báo khi nó sắp hết hạn. Không biến một certificate “good” thành “bad” chỉ vì thời gian trôi qua.

## 5. Cách quan sát chứng chỉ và keystore mà không xuất khóa riêng

Những lệnh sau dành cho **lab test** với file giả định, không tạo, ghi đè hoặc xuất private key:

~~~bash
# Liệt kê keystore: kiểm tra alias, entry type và certificate chain.
keytool -list -v -keystore fixtures/client-identity.p12 -storetype PKCS12

# Xem validity, issuer/subject và hostname SAN của certificate PEM.
openssl x509 -in fixtures/server-valid.pem -noout -dates -issuer -subject
openssl x509 -in fixtures/server-valid.pem -noout -ext subjectAltName
openssl x509 -in fixtures/server-valid.pem -noout -ext extendedKeyUsage

# Kiểm tra chain tại thời điểm chạy với CA + intermediate đã chọn.
openssl verify -purpose sslserver \
  -CAfile fixtures/test-ca-a.pem \
  -untrusted fixtures/test-intermediate-a.pem \
  fixtures/server-valid.pem
~~~

Chọn lệnh/tham số đúng phiên bản OpenSSL/keytool của môi trường. `keytool -list -v` sẽ có thể yêu cầu store password; **không thêm mật khẩu thật vào command line**, vì có thể xuất hiện trong shell history/process list. `openssl verify` giúp chẩn đoán chain nhưng **không thay thế TLS hostname verification** trừ khi cấu hình thêm hostname checks phù hợp.

### 5.1. Entry type quan trọng hơn alias name

Một keystore có thể chứa:

~~~text
Alias: soap-client
Entry type: PrivateKeyEntry
Certificate chain length: 2

Alias: partner-trust-anchor
Entry type: trustedCertEntry
~~~

`PrivateKeyEntry` có private key dùng ký hoặc chứng minh client/server identity; `trustedCertEntry` chỉ chứa certificate tin cậy, không cho phép ký. Nếu thử ký bằng `partner-trust-anchor` dù tên alias có vẻ hợp lệ, phía gửi **không có private key** để thực hiện.

**Không giải quyết thiếu private key bằng cách nhập certificate public vào truststore nhiều lần**; private key không thể được suy ra từ certificate.

### 5.2. Certificate chain và SAN/EKU

Một leaf certificate thường có:

~~~text
Subject: CN=soap.test.local
Issuer:  CN=Test Intermediate CA A
SAN:     DNS:soap.test.local
EKU:     TLS Web Server Authentication (serverAuth)
KeyUsage: Digital Signature ...
NotBefore: 2026-01-01T00:00:00Z
NotAfter:  2028-01-01T00:00:00Z
~~~

Đây là metadata **minh họa**, không phải certificate thật. Dựa vào **SAN** để kiểm tra host HTTPS; chỉ trùng `CN` không đủ theo thông lệ xác minh hiện đại. Với mTLS client certificate, EKU thường là `clientAuth`; với TLS server là `serverAuth`. Với SOAP Signature/Encryption, KeyUsage/algorithms cần phù hợp vai trò theo profile, và verifier phải ràng buộc signer identity với đối tác được phép.

## 6. Test 1 — Chứng chỉ hết hạn và chưa có hiệu lực

X.509 có hai mốc:

~~~text
NotBefore ------------------------------ NotAfter
          khoảng thời gian hợp lệ
~~~

- **Expired:** thời điểm xác minh ở sau `NotAfter`.
- **Not yet valid:** thời điểm xác minh ở trước `NotBefore`.
- Một clock skew nhỏ có thể gây lỗi ở ranh giới; hệ thống dùng đồng hồ đồng bộ và test boundary riêng.

### 6.1. Unit test Java kiểm tra validity ở mốc cố định

Java chuẩn có `java.security.cert.X509Certificate.checkValidity(Date)`. Ví dụ JUnit 5 minh họa:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.Test;

class CertificateValidityTest {
    private static X509Certificate readX509(Path pem) throws Exception {
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");
        try (InputStream input = Files.newInputStream(pem)) {
            return (X509Certificate)
                    factory.generateCertificate(input);
        }
    }

    @Test
    void rejectsExpiredCertificateAtKnownInstant() throws Exception {
        X509Certificate cert = readX509(
                Path.of("fixtures/server-expired.pem"));
        Date when = Date.from(Instant.parse("2027-06-01T00:00:00Z"));

        assertThrows(CertificateExpiredException.class,
                () -> cert.checkValidity(when));
    }

    @Test
    void rejectsNotYetValidCertificateAtKnownInstant()
            throws Exception {
        X509Certificate cert = readX509(
                Path.of("fixtures/server-future.pem"));
        Date when = Date.from(Instant.parse("2026-01-01T00:00:00Z"));

        assertThrows(CertificateNotYetValidException.class,
                () -> cert.checkValidity(when));
    }
}
~~~

**Điều kiện fixture:** `server-expired.pem` phải có `NotAfter` trước 2027-06-01; `server-future.pem` phải có `NotBefore` sau 2026-01-01. Ví dụ **không chạy độc lập nếu chưa tạo fixtures**. Dùng `java.security.cert.X509Certificate`, **không** dùng API cũ `javax.security.cert.X509Certificate`.

### 6.2. Giới hạn của checkValidity

`checkValidity(Date)` chỉ kiểm tra thời gian của **chính certificate**. Nó **không tự**:

- Xây và xác minh certificate chain đến trust anchor.
- Kiểm tra SAN có khớp hostname HTTPS hay không.
- Kiểm tra certificate signer được phép gọi SOAP operation nào.
- Kiểm tra certificate đã bị thu hồi.
- Thực hiện TLS handshake hoặc xác minh XML Signature.

Vì vậy unit test này chứng minh **fixture expired/future đúng như mong muốn**, không được báo nó là bằng chứng toàn bộ client/server đã từ chối certificate ở runtime.

### 6.3. Kiểm thử thời gian khi xác minh PKIX path

Với một `CertPath` và trust anchors đã chuẩn bị, Java `PKIXParameters.setDate(Date)` cho phép đặt thời điểm để `CertPathValidator` đánh giá chain trong **unit/PKIX test**:

~~~java
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXParameters;
import java.security.KeyStore;
import java.time.Instant;
import java.util.Date;

void validatePathAt(CertPath path, KeyStore trustAnchors)
        throws Exception {
    PKIXParameters params = new PKIXParameters(trustAnchors);
    params.setDate(
            Date.from(Instant.parse("2027-06-01T00:00:00Z")));
    // Chọn revocation policy/CertStore fixtures thực tế cho test.
    CertPathValidator.getInstance("PKIX").validate(path, params);
}
~~~

Đây là **helper minh họa API**, test âm thật cần `assertThrows(CertPathValidatorException.class, ...)`, kiểm tra lý do lỗi và cung cấp `CertPath` đúng thứ tự, intermediates/trust anchors phù hợp. **Không tắt revocation một cách mặc định trong production**; khi test cô lập không có CRL/OCSP, cần tuyên bố rõ phạm vi test và có một nhánh test riêng cho revocation.

### 6.4. Integration test expiry ở TLS

Với embedded HTTPS server trình bày một **expired leaf certificate**:

1. Start server với certificate/key của `test-server-expired`, CA/chain vẫn đúng, SAN vẫn khớp test host.
2. Client `WebServiceTemplate` dùng sender/SSLContext tin CA A và giữ hostname verification bật.
3. Gửi SOAP request nhỏ, hợp XSD, qua HTTPS.
4. Kỳ vọng **TLS/PKIX failure**, có thể xuất hiện `SSLHandshakeException` với `CertificateExpiredException` trong cause chain.
5. Assert endpoint/service **không được gọi**, không có SOAP success response, không có fallback HTTP.
6. Đối chiếu với `test-server-valid` ở cùng host/CA/keystore policy để bảo đảm test sai **chỉ vì thời hạn certificate**.

**Lưu ý:** exception wrapper phụ thuộc sender, JDK và TLS provider. Không viết test yêu cầu chính xác một câu `"PKIX path building failed"`; thay vào đó assert **loại tầng lỗi**, nguyên nhân có thể quan sát và bất biến không tạo side effect.

### 6.5. Expired client certificate với mTLS

Đổi vị trí: server HTTPS yêu cầu `client-auth=need` và trust CA A, client gửi `test-client-expired`. Nếu server thực thi PKIX/identity policy phù hợp, mTLS handshake phải bị từ chối. Không nhầm với tình huống client **không có certificate nào**: cả hai fail handshake nhưng căn nguyên khác.

### 6.6. Expired signer certificate của WS-Security

Ở tầng SOAP, transport HTTPS **có thể thành công** nhưng WSS4J từ chối chữ ký vì certificate signer đã hết hạn hoặc không đáp ứng trust policy.

- Phía client ký SOAP request bằng test signer đã hết hạn nhưng vẫn sở hữu private key.
- Phía server bật `validationActions="Signature"` và `validationSignatureCrypto` với trust policy đúng.
- Kỳ vọng chữ ký **không được chấp nhận**, endpoint không thực hiện nghiệp vụ; trong đường xử lý SOAP hợp lệ thường có security Fault.
- Dùng positive signer cùng policy để test pass.

**Không mặc định mọi cấu hình WSS4J đều kiểm tra giống nhau:** xác minh runtime thực tế rằng certificate validity/trust validation đang được bật, không chỉ XML Signature digest. Với trust implementation mặc định của WSS4J, certificate validation là một phần của xác minh trust, nhưng custom `Crypto`/validator có thể thay đổi hành vi.

## 7. Test 2 — Chứng chỉ không đáng tin (untrusted)

Chứng chỉ “untrusted” thường nói đến **không dựng được đường tin cậy tới trust anchor mà bên nhận cho phép**, nhưng cần phân biệt thêm các điều kiện:

| Tình huống | Có thể trông giống nhau | Cách tách nguyên nhân |
| --- | --- | --- |
| CA B ký certificate nhưng truststore chỉ có CA A | `PKIX path building failed` | Xem issuer và trust anchors |
| Server quên gửi intermediate | Path building failed | Kiểm tra chain được trình bày và intermediate store |
| Certificate tự ký không nằm trong allowlist | Unknown/self-signed CA | Xem trustedCertEntry, không trust-all |
| Chain tin cậy nhưng SAN sai | SSL peer verification failed | Xem hostname/SAN riêng |
| Chain tin cậy nhưng EKU không đúng | Purpose check failed | Xem `extendedKeyUsage`/provider policy |
| CA tin cậy nhưng signer chưa được phép làm partner này | WS-Security có thể verify cryptographically | Kiểm tra signer-to-partner authorization mapping |

### 7.1. Test CA A / CA B

Thiết lập:

~~~text
Client truststore:  Test CA A only
Server certificate: signed by Test CA B
Server hostname:    soap.test.local (SAN chính xác)
Server leaf dates:  hợp lệ
TLS protocol:       tương thích
~~~

Khi gửi request, client **phải từ chối** server vì path không dẫn tới CA A, dù mọi thứ khác đúng. Positive control dùng server cert ký bởi CA A và cùng hostname để xác nhận TLS pass.

**Không đưa CA B vào truststore chỉ để test pass**. Mục tiêu negative test là xác nhận lựa chọn trust anchor đang được thực thi.

### 7.2. Incomplete chain

Nếu server gửi leaf nhưng bỏ intermediate, một số client có thể **vẫn xây chain thành công** vì intermediate đã được cache/cài trong store hoặc có cơ chế bổ sung certificates. Muốn test ổn định:

- Dùng **isolated truststore** chỉ chứa root CA, không vô tình có intermediate.
- Không dựa vào AIA/network fetch để “sửa” chain trong test.
- Ghi lại chain thực sự server gửi, không chỉ tập cert trong file keystore.
- Assert failure với chain thiếu và pass khi thêm đúng intermediate.

**Đừng kết luận untrusted chỉ từ số lượng chain entries:** một certificate chain dài chưa chắc dẫn tới đúng trust anchor, và trust anchor **không nhất thiết** phải được server gửi.

### 7.3. Certificate trust không phải hostname verification

Nếu server leaf được CA A tin cậy nhưng SAN chỉ chứa `DNS:other.test.local` trong khi URL là `https://soap.test.local`, đúng behavior là từ chối **hostname mismatch**. Thêm CA, chuyển JKS sang PKCS#12 hoặc tăng timeouts **không chữa được** hostname.

Đừng dùng `NoopHostnameVerifier` hay gọi host bằng IP khi SAN chỉ chứa DNS. Đặt SAN đúng host của endpoint được phép sử dụng; test riêng DNS SAN và IP SAN nếu sản phẩm yêu cầu.

### 7.4. WS-Security signer untrusted nhưng HTTPS trusted

Thiết lập:

~~~text
HTTPS server: certificate hợp lệ từ CA A → TLS pass.
SOAP signer:  certificate do Test CA B cấp → trust Crypto chỉ chấp nhận A.
SOAP Body:    đúng XSD, chữ ký có thể đúng về mặt mật mã.
~~~

Server `Wss4jSecurityInterceptor` phải **từ chối SOAP signature/trust** khi certificate signer không được phép, không nhầm việc TLS đã thành công với SOAP signer trust. Tùy policy, cần ràng buộc certificate fingerprint/subject/issuer hoặc partner identity **sau khi kiểm trust**.

### 7.5. Revocation là một điều kiện riêng

Certificate có thể còn trong hạn và có chain tin cậy nhưng đã bị **thu hồi**. Spring-WS `Wss4jSecurityInterceptor#setEnableRevocation(true)` hỗ trợ revocation checks của WSS4J trong phạm vi provider/cấu hình tương ứng. TLS JSSE lại có chính sách PKIX/CRL/OCSP riêng.

Không xem một test expired/untrusted là bằng chứng revocation hoạt động. Nếu contract cần revocation:

1. Dùng test CA phát hành một leaf rồi đưa vào CRL/OCSP test fixture.
2. Bật cơ chế revocation đúng cho TLS/WS-Security.
3. Test leaf bị thu hồi bị từ chối; leaf hợp lệ không bị từ chối.
4. Test server CRL/OCSP unreachable và quyết định **fail-open/fail-closed** theo policy được duyệt.
5. Không bật network fetch tùy ý từ một certificate do attacker gửi vào production.

## 8. Test 3 — Thiếu khóa riêng hoặc khóa không phù hợp

“Thiếu khóa” có thể nói tới **ba vị trí khác nhau**:

1. **Bên ký** không có private key của certificate được dùng ký.
2. **Bên giải mã** không có private key tương ứng với public key dùng mã hóa message.
3. **Bên TLS/mTLS** không có private key/identity certificate phù hợp để chứng minh danh tính trong handshake.

**Không dùng public certificate thay thế private key.** Một truststore có đầy đủ public certificates của đối tác vẫn **không thể** ký request với danh tính client hoặc giải mã ciphertext dành cho private key của client.

### 8.1. Bảng phân biệt lỗi khóa

| Dạng lỗi | Kịch bản | Thời điểm lỗi | Cách kiểm tra |
| --- | --- | --- | --- |
| **Alias không tồn tại** | `securementSignatureUser="signing-a"` nhưng store chỉ có `signing-b` | WSS4J outbound hoặc khởi tạo crypto | Liệt kê aliases + test entry type |
| **Alias trỏ trustedCertEntry** | Có public cert nhưng không có private key | Ký SOAP/TLS identity không thực hiện được | `KeyStore.isKeyEntry` và `getKey` |
| **Password sai** | Private key có nhưng không giải khóa được | `KeyManagerFactory.init` hoặc WSS4J securement | `UnrecoverableKeyException`/provider cause |
| **Certificate/public key không khớp private key** | Identity store cấu hình chain sai | Load/store init, signing hoặc verify | Sign-verify với pair trong test |
| **Key algorithm không phù hợp** | Dùng key EC khi policy yêu cầu RSA hoặc ngược lại | Provider/handshake/WS-Security | `PrivateKey.getAlgorithm`, policy, signature alg |
| **Missing mTLS identity** | Client không gửi certificate/private key | TLS handshake | Server `client-auth=need` |
| **Wrong recipient certificate** | Client mã hóa bằng public key B, server chỉ giữ private key A | WSS4J decrypt inbound | XML Encryption recipient/alias |
| **Missing server TLS key** | Chỉ có server certificate, thiếu private key | HTTPS connector startup/handshake | Server SSL identity config |
| **Wrong WS-Security signing trust** | Ký bằng private key đúng nhưng verifier không trust cert | WSS4J inbound | `validationSignatureCrypto` |

**Chú ý:** thiếu private key để **verify** chữ ký không phải lỗi: xác minh chữ ký dùng **public key** của signer và trust policy. Thiếu private key chỉ là lỗi khi vai trò đó cần **ký hoặc giải mã**, hay chứng minh danh tính TLS/mTLS.

## 9. Unit test keystore: alias, entry type và private key

JDK `java.security.KeyStore` hỗ trợ các thao tác kiểm tra mà không cần tạo SOAP request. Ví dụ sau dùng một **PKCS#12 test store**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.X509Certificate;
import org.junit.jupiter.api.Test;

class PrivateKeyFixtureTest {

    static KeyStore loadP12(Path location, char[] storePassword)
            throws Exception {
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(location)) {
            keyStore.load(input, storePassword);
        }
        return keyStore;
    }

    @Test
    void publicCertificateEntryCannotSign() throws Exception {
        KeyStore store = loadP12(
                Path.of("fixtures/public-cert-only.p12"),
                testStorePassword());

        String alias = "public-certificate";
        assertTrue(store.containsAlias(alias));
        assertTrue(store.isCertificateEntry(alias));
        assertFalse(store.isKeyEntry(alias));
    }

    @Test
    void signingIdentityHasPrivateKeyAndCertificate()
            throws Exception {
        KeyStore store = loadP12(
                Path.of("fixtures/soap-signing.p12"),
                testStorePassword());

        String alias = "signer-a";
        assertTrue(store.containsAlias(alias));
        assertTrue(store.isKeyEntry(alias));

        Key key = store.getKey(alias, testKeyPassword());
        assertInstanceOf(PrivateKey.class, key);
        assertInstanceOf(X509Certificate.class,
                store.getCertificate(alias));
        assertNotNull(store.getCertificateChain(alias));
    }

    private static char[] testStorePassword() {
        return "fixture-store-password".toCharArray();
    }

    private static char[] testKeyPassword() {
        return "fixture-key-password".toCharArray();
    }
}
~~~

**Chỉ dùng mật khẩu giả của fixture trong test.** Ví dụ không tạo được file PKCS#12; project cần cung cấp fixture phù hợp. Trong production, secrets lấy từ secret manager/HSM, không hardcode string. `getKey(alias, password)` có thể ném `UnrecoverableKeyException` nếu password sai; entry type và key algorithm phụ thuộc provider/keystore.

### 9.1. Tại sao isKeyEntry chưa đủ?

`KeyStore.isKeyEntry(alias)` trả về true cho một số loại key entries; nó không bảo đảm entry là **asymmetric PrivateKey** cần cho SOAP Signature/mTLS. Vì thế test cần:

- `key instanceof PrivateKey`.
- `certificate instanceof X509Certificate`.
- Certificate chain có dữ liệu phù hợp.
- Algorithm của key và certificate phù hợp policy.
- **Public/private pair thực sự tương ứng** (kiểm tra ở phần kế).

### 9.2. Kiểm tra private key khớp public certificate bằng sign/verify

Một cách kiểm tra fixture **mà không xuất private key** là ký một thông điệp thử nghiệm bằng private key rồi verify bằng public key trong certificate:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.cert.X509Certificate;

static boolean privateKeyMatchesCertificate(
        PrivateKey privateKey,
        X509Certificate certificate) throws Exception {

    String keyAlgorithm = privateKey.getAlgorithm();
    String signatureAlgorithm = switch (keyAlgorithm) {
        case "RSA" -> "SHA256withRSA";
        case "EC" -> "SHA256withECDSA";
        default -> throw new IllegalArgumentException(
                "Test fixture chỉ hỗ trợ RSA hoặc EC");
    };

    byte[] fixtureBytes =
            "certificate-key-pair-test".getBytes(
                    StandardCharsets.UTF_8);

    Signature signer = Signature.getInstance(signatureAlgorithm);
    signer.initSign(privateKey);
    signer.update(fixtureBytes);
    byte[] signature = signer.sign();

    Signature verifier = Signature.getInstance(signatureAlgorithm);
    verifier.initVerify(certificate.getPublicKey());
    verifier.update(fixtureBytes);
    return verifier.verify(signature);
}
~~~

Đây là **test chẩn đoán fixture**, dùng Java 17+ cho switch expression. Không tự triển khai XML Signature production bằng cách gọi helper này: WSS4J cần canonicalization, XML references, key identifiers và trust policy của SOAP. Nếu key algorithm/provider khác RSA/EC hoặc chính sách yêu cầu RSA-PSS, phải dùng thuật toán test phù hợp.

**Một số PKCS#12 providers có thể từ chối nạp certificate chain không khớp private key ngay từ bước import/load**. Khi đó test negative mismatch nên kiểm tra **khâu khởi tạo bị từ chối**, hoặc dùng cặp raw `PrivateKey`/`X509Certificate` trong môi trường thử nghiệm để xác minh mismatch, thay vì cố tạo keystore không hợp lệ bằng mọi giá.

### 9.3. Kiểm thử alias và password

Trong JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.security.KeyStore;
import java.nio.file.Path;

KeyStore store = PrivateKeyFixtureTest.loadP12(
        Path.of("fixtures/soap-signing.p12"),
        "fixture-store-password".toCharArray());

assertFalse(store.containsAlias("nonexistent-signing-key"));

// Khi alias đúng nhưng key password sai, việc mở private key
// phải thất bại theo provider/keystore được chọn.
// Test cụ thể cần assert exception type/cause của runtime hiện tại.
~~~

Không dùng thông báo exception chứa đường dẫn store hoặc alias nhạy cảm làm SOAP Fault gửi cho đối tác. Log nội bộ đã lọc là đủ để chẩn đoán lỗi cấu hình.

## 10. HTTPS và mTLS: test thông qua kết nối thật

Để chứng minh TLS/mTLS thật sự từ chối certificate sai, phải chạy **embedded HTTPS test server** hoặc hệ thống staging được kiểm soát; unit test `KeyStore.getKey(...)` chưa đủ.

### 10.1. Topology kiểm thử

~~~mermaid
flowchart LR
    A["WebServiceTemplate<br/>HTTP(S) sender"] --> B["SSLContext client<br/>truststore + optional mTLS key"]
    B --> C["Embedded HTTPS server<br/>server keypair"]
    C --> D["Server truststore<br/>clientAuth=need"]
    D --> E["MessageDispatcherServlet<br/>@Endpoint"]
    E --> F["Test domain service<br/>invocation counter"]
~~~

Chạy các test ở **hostname có SAN đúng**, ví dụ `soap.test.local` được ánh xạ đến loopback trong môi trường test, hoặc dùng `localhost` nếu certificate SAN chứa `DNS:localhost`. Không tắt hostname verification. Cấp test certificates đúng host/port hoặc dùng embedded DNS mapping mà không can thiệp máy người dùng ngoài phạm vi CI.

### 10.2. Cấu hình embedded server theo Spring Boot (minh họa)

~~~yaml
server:
  port: 0
  ssl:
    enabled: true
    key-store: classpath:test-pki/server-valid.p12
    key-store-type: PKCS12
    key-store-password: "${TEST_SERVER_STORE_PASSWORD}"
    client-auth: need
    trust-store: classpath:test-pki/server-trust.p12
    trust-store-type: PKCS12
    trust-store-password: "${TEST_SERVER_TRUST_PASSWORD}"
~~~

Đây là **cấu hình test minh họa**. Trong Spring Boot, `port: 0` yêu cầu hệ thống cấp cổng ngẫu nhiên; test lấy actual local port từ embedded server. Các biến môi trường mang password **chỉ cho fixture test**; không áp cấu hình này trực tiếp lên production và không giả định mọi servlet container/Boot version đều có các thuộc tính SSL hoàn toàn giống nhau.

Với test chỉ xác minh **server HTTPS certificate**, có thể dùng `client-auth: none` (nếu Boot/container hỗ trợ) để tránh yêu cầu mTLS che mất nguyên nhân. Với test **client certificate**, giữ `client-auth: need` và cung cấp truststore phía server rõ ràng.

### 10.3. Xây SSLContext client an toàn với JDK

Ví dụ Java helper làm rõ **identity store khác truststore**:

~~~java
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

static SSLContext clientTlsContext(
        KeyStore clientIdentity,
        char[] privateKeyPassword,
        KeyStore serverTrust) throws Exception {

    KeyManagerFactory keyManagers =
            KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
    keyManagers.init(clientIdentity, privateKeyPassword);

    TrustManagerFactory trustManagers =
            TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
    trustManagers.init(serverTrust);

    SSLContext context = SSLContext.getInstance("TLS");
    context.init(
            keyManagers.getKeyManagers(),
            trustManagers.getTrustManagers(),
            new SecureRandom());
    return context;
}
~~~

Đây là **helper TLS**, không phải Spring-WS HTTP sender hoàn chỉnh. Kết nối `SSLContext` vào Apache HttpClient 5 thông qua TLS strategy/connection manager của **đúng phiên bản HttpClient 5** hoặc HTTP sender tương thích; xác minh hostname verification vẫn được bật. Đừng dùng `SSLContext` này để ký SOAP `ds:Signature`: WSS4J dùng `Crypto` và private signing key riêng.

Nếu client **không dùng mTLS**, `KeyManagerFactory` có thể không được cấu hình và `SSLContext.init(null, trustedManagers, ...)` sử dụng default key managers theo semantics của JSSE; test phải khẳng định client không tự nhận certificate ngoài ý muốn từ JVM defaults.

### 10.4. Phân biệt handshake fail với SOAP Fault

| Lỗi | Có HTTP SOAP response? | Test phải assert |
| --- | --- | --- |
| Server certificate hết hạn | Thông thường **không** | Client SSL/cert validation fail, server endpoint không chạy |
| Server CA không được trust | Thông thường **không** | Path/trust failure, endpoint không chạy |
| Server SAN khác hostname | Thông thường **không** | Endpoint identification fail |
| Client mTLS certificate hết hạn | Thông thường **không** | Server từ chối client handshake |
| Client mTLS không có key/cert | Thông thường **không** khi `client-auth=need` | Không bypass client authentication |
| SOAP signature của client không được trust | **Có thể** có SOAP Fault | TLS pass, WSS4J từ chối request |
| Client thiếu private signing key | Không có request hợp lệ; thường local failure | Securement fail, không gửi request |
| Server thiếu SOAP decryption private key | Có thể có SOAP security Fault | TLS pass, endpoint không xử lý Body |

Không assert rằng mọi TLS failure đều là `SSLHandshakeException` trực tiếp: Spring-WS có thể bọc bằng `WebServiceIOException` hoặc exception khác của sender; HTTP client/version có thể đổi cause chain. **Assert tầng lỗi và tác dụng phụ**, không phụ thuộc một chuỗi lỗi không ổn định.

### 10.5. Tránh false positives do keep-alive và connection pooling

Test thay certificate trên server rồi gửi lần hai qua cùng HTTP connection **có thể không thực hiện TLS handshake mới**, vì connection pooling tái sử dụng kết nối cũ. Khi test rotation/expiry:

1. Dùng một server/client instance mới hoặc đóng connection pool cũ theo lifecycle.
2. Bảo đảm bắt đầu **handshake mới** cho mỗi biến thể certificate.
3. Không tái dùng SSLSession/SSLContext một cách làm test bỏ qua mục tiêu.
4. Giữ thời gian, hostname, CA, cipher/protocol, endpoint và request payload giống nhau.
5. Verify positive baseline luôn pass trước mỗi nhóm negative.

Chỉ thấy request vẫn thành công sau khi thay certificate **chưa chứng minh trust validator bỏ qua expiry** nếu nó đi qua connection đã thiết lập.

## 11. Spring-WS/WSS4J: test certificate dùng cho chữ ký SOAP

Trong Spring-WS 4.x, class tích hợp là:

~~~java
org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor
~~~

Với **request signer** và **server verifier**:

| Bên | Action | Material bắt buộc |
| --- | --- | --- |
| **Client gửi** | `securementActions="Timestamp Signature"` | Private signing key + certificate; alias/key password |
| **Server nhận** | `validationActions="Timestamp Signature"` | Signer public certificate/trust Crypto, validation policies |
| **Server trả signed response** | `securementActions="Timestamp Signature"` | Server private signing key |
| **Client nhận signed response** | `validationActions="Timestamp Signature"` | Server signer trust Crypto |

### 11.1. Client securement (khóa ký thuộc client)

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

static Wss4jSecurityInterceptor signingClient(
        Crypto clientSigningCrypto,
        String signingAlias,
        String privateKeyPassword) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setSecurementActions("Timestamp Signature");
    interceptor.setSecurementSignatureCrypto(clientSigningCrypto);
    interceptor.setSecurementSignatureUser(signingAlias);
    interceptor.setSecurementPassword(privateKeyPassword);
    interceptor.setSecurementSignatureKeyIdentifier(
            "DirectReference");
    interceptor.setSecurementTimeToLive(300);
    return interceptor;
}
~~~

Ở đây `Crypto` cần truy cập **private key**. Nếu alias thiếu, trỏ trustedCertEntry hoặc password không đúng, quá trình securement có thể thất bại. Đây là **điểm negative test “missing suitable signing key”**: chắc chắn không được âm thầm gửi request unsigned tới server.

**Không lưu privateKeyPassword trong source.** Hàm nhận password từ cấu hình/secret provider của test hoặc production theo vòng đời hợp lệ. Cách set password/CallbackHandler chính xác còn tùy security profile, HSM và WSS4J provider.

### 11.2. Server signature validation (không cần private key của client)

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

static Wss4jSecurityInterceptor verifyClientSignature(
        Crypto trustedClientCertificates) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setValidationActions("Timestamp Signature");
    interceptor.setValidationSignatureCrypto(
            trustedClientCertificates);
    interceptor.setTimestampStrict(true);
    interceptor.setValidationTimeToLive(300);
    interceptor.setFutureTimeToLive(60);
    interceptor.setBspCompliant(true);
    interceptor.setStrictActionChecking(true);
    return interceptor;
}
~~~

**Validation Crypto chỉ cần chứng chỉ/trust material phù hợp**, không cần private key của đối tác. Nếu client ký bằng signer không trusted, server phải từ chối. Đối với hệ thống nhiều partners, một certificate đáng tin cryptographically **không có nghĩa** được phép đóng vai mọi partner: thêm identity mapping/authorization theo signer, tenant và operation.

### 11.3. CryptoFactoryBean và material

Spring-WS có `CryptoFactoryBean` tạo `org.apache.wss4j.common.crypto.Crypto` từ key/trust material:

~~~java
import java.io.IOException;
import org.springframework.core.io.Resource;
import org.springframework.ws.soap.security.wss4j2.support.CryptoFactoryBean;

static CryptoFactoryBean cryptoFromStore(
        Resource storeResource,
        String storePassword) throws IOException {

    CryptoFactoryBean crypto = new CryptoFactoryBean();
    crypto.setKeyStoreLocation(storeResource);
    crypto.setKeyStorePassword(storePassword);
    return crypto;
}
~~~

Ví dụ thể hiện **factory bean wiring**, không tự đăng ký `@Bean` hay cung cấp `Crypto` chưa khởi tạo. Trong Spring container, lifecycle `FactoryBean` thực hiện khởi tạo và tạo `Crypto`. Nếu khởi tạo thủ công, phải theo đúng lifecycle và xử lý exceptions. Cấu hình `KeyStoreType`, provider, alias và trust validation theo version/PKI, không giả định mọi store đều là JKS.

### 11.4. Kiểm thử thiếu alias khi ký

Chạy một test ở **client boundary**:

~~~text
Given:
  Client SOAP template có WSS4J outbound Signature.
  clientSigningCrypto dùng PKCS#12 hợp lệ.
  securementSignatureUser = "alias-does-not-exist".

When:
  marshalSendAndReceive(GetOrderRequest).

Then:
  Local securement không hoàn thành.
  HTTP test endpoint không nhận SOAP request được ký lỗi.
  Không có fallback sang unsigned/UsernameToken-only.
  Exception được phân loại trong internal logs,
  không lộ keystore password.
~~~

Tương tự, đổi alias trỏ **certificate-only entry** rồi xác minh WSS4J không thể ký. Không sửa truststore của server để “chữa” lỗi local signing key; server còn chưa nhìn thấy request.

## 12. Spring-WS/WSS4J: test thiếu private key để giải mã

Trong XML Encryption:

- **Client mã hóa** bằng **public certificate của server/recipient**.
- **Server giải mã** bằng **private key tương ứng**.
- Public certificate **không đủ** để giải mã một SOAP message đã mã hóa cho private key của recipient.

### 12.1. Bên gửi: chọn public key recipient

~~~java
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

static Wss4jSecurityInterceptor encryptForServer(
        Crypto serverPublicCrypto, String serverRecipientAlias) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setSecurementActions("Encrypt");
    interceptor.setSecurementEncryptionCrypto(serverPublicCrypto);
    interceptor.setSecurementEncryptionUser(serverRecipientAlias);
    interceptor.setSecurementEncryptionKeyTransportAlgorithm(
            "http://www.w3.org/2001/04/xmlenc#rsa-oaep-mgf1p");
    return interceptor;
}
~~~

Đoạn này chỉ minh họa **khóa recipient và key transport**. Các thuật toán mã hóa nội dung (ví dụ AES) và parts được mã hóa phải được chọn theo policy/WS-Policy, có test tương thích với đối tác. Không bật RSA PKCS#1 v1.5 key transport chỉ vì một client cũ không giải mã được RSA-OAEP.

### 12.2. Bên nhận: chỉ private key đúng recipient mới giải mã được

~~~java
import javax.security.auth.callback.CallbackHandler;
import org.apache.wss4j.common.crypto.Crypto;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

static Wss4jSecurityInterceptor decryptAtServer(
        Crypto serverPrivateCrypto,
        CallbackHandler privateKeyPasswordCallbacks) {

    Wss4jSecurityInterceptor interceptor =
            new Wss4jSecurityInterceptor();
    interceptor.setValidationActions("Encrypt");
    interceptor.setValidationDecryptionCrypto(serverPrivateCrypto);
    interceptor.setValidationCallbackHandler(
            privateKeyPasswordCallbacks);
    return interceptor;
}
~~~

**Các test âm cần có:**

| Test | Thay đổi | Kỳ vọng |
| --- | --- | --- |
| `missing-private-key` | Crypto server chỉ có public cert | Không giải mã, domain không chạy |
| `wrong-decryption-alias` | Keystore chứa private key A nhưng ciphertext dành cho B | Không tìm được key phù hợp/decryption fail |
| `wrong-private-key-password` | Password callback của private key sai | Decryption fail; không trả plaintext |
| `wrong-recipient-certificate` | Client chọn public cert B, server chỉ có private key A | Không giải mã được |
| `wrong-key-transport` | Dùng thuật toán trái chính sách | WSS4J validation từ chối |
| `valid-control` | Mã hóa cho public cert A và server giữ private key A | Giải mã pass và payload hợp XSD |

**Lưu ý về thuật toán:** “public/private key không khớp” không nhất thiết tạo exception giống nhau giữa JCE providers. Có thể lỗi khi tìm private key, lúc unwrap content-encryption key hoặc khi giải mã XML. Assert **không đọc được nội dung và không có side effects** thay vì so exact error text.

### 12.3. Cặp khóa signer và recipient có thể khác nhau

Một partner có thể có:

~~~text
client-signing-key:    dùng ký SOAP request
server-verify-trust:   tin public cert của client

server-encryption-cert: dùng để client mã hóa request
server-decryption-key:  private key tương ứng của server

server-signing-key:     dùng ký SOAP response
client-verify-trust:    tin public cert của server
~~~

Đừng nhầm alias của **client-signing-key** với **server-encryption-cert**, hoặc đưa private key của bên gửi vào recipient truststore. Mỗi test cần biểu diễn rõ **ai giữ private key, ai giữ public key và ai là bên xác minh**.

## 13. Server và client: register interceptor để test đúng luồng

Với Spring-WS 4.x, WSS4J interceptor phải được đăng ký **đúng nơi**.

### 13.1. Server endpoint interceptor

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

@Configuration
@EnableWs
public class WsSecurityTestConfiguration implements WsConfigurer {
    private final Wss4jSecurityInterceptor verifier;

    public WsSecurityTestConfiguration(
            Wss4jSecurityInterceptor verifier) {
        this.verifier = verifier;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(verifier);
    }
}
~~~

Test cần khẳng định **request thực sự match một `@Endpoint`** và interceptor đã chạy. Nếu request sai Body QName ngay từ đầu, dispatcher có thể không chọn endpoint, khiến test trả lỗi nhưng **không phải vì certificate bị từ chối** — đó là false positive.

### 13.2. Client WebServiceTemplate interceptor

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.client.support.interceptor.ClientInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;

static void installSecurity(
        WebServiceTemplate template,
        Wss4jSecurityInterceptor security) {
    template.setInterceptors(new ClientInterceptor[] {security});
}
~~~

Đây là cấu hình minh họa; `template` phải có message factory, JAXB marshaller/unmarshaller, HTTP sender và endpoint URL. Nếu test hai clients với certificates khác nhau, **tạo hai template/interceptor configurations độc lập**. Không thay alias/`Crypto` của cùng một singleton `Wss4jSecurityInterceptor` giữa các test chạy song song.

### 13.3. Validation trên response cũng là một nghĩa vụ

Khi server ký SOAP response:

- Server `securementSignatureCrypto` cần private signing key của server.
- Client `validationSignatureCrypto` cần tin đúng server signer/chain.
- Client không được unmarshal response/đưa dữ liệu tới domain khi signature chưa được xác minh theo policy.

Test âm response cần có một SOAP response **được ký thật** bằng signer không đáng tin/expired; `withPayload(...)` mock chỉ chứa XML Body **không chứng minh** kiểm thử certificate trust của signed response.

## 14. Kiểm chứng đúng loại lỗi: failure ở đâu?

Nếu test chỉ assert `assertThrows(Exception.class, ...)` thì một lỗi DNS, XML malformed hoặc request thiếu SOAPAction cũng có thể khiến test “xanh”, trong khi certificate validation chưa chạy.

### 14.1. Xây positive control trước mọi negative test

Với cùng môi trường:

1. Request hợp XSD, SOAP version, WSDL operation và JAXB binding.
2. HTTPS hostname/SAN, CA, certificate validity, key usage và TLS protocol đúng.
3. Nếu mTLS: client key/certificate và server client-auth policy đúng.
4. Nếu WS-Security: signer/decrypter/recipient Crypto/alias/password đúng.
5. Endpoint được dispatch, service gọi đúng số lần, response hợp contract.

Sau khi baseline pass, đổi **một** material hoặc một cấu hình (cert expired, CA B, missing alias) và chạy test âm. Nếu bạn đổi đồng thời hostname, SOAP version và truststore, test không thể quy kết nguyên nhân.

### 14.2. Inspect cause chain thay vì so exception message

Một helper test có thể kiểm tra một exception được framework bọc:

~~~java
static boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {

    for (Throwable current = error;
            current != null;
            current = current.getCause()) {
        if (expectedType.isInstance(current)) {
            return true;
        }
    }
    return false;
}
~~~

Ví dụ assertion sau một lời gọi HTTPS test bị lỗi:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import javax.net.ssl.SSLHandshakeException;

// Throwable failure = assertThrows(..., () -> soapClient.call(...));
assertTrue(hasCause(failure, SSLHandshakeException.class)
        || isOtherDocumentedTlsFailure(failure));
~~~

Đây là **pseudocode assertion**: `failure` và `isOtherDocumentedTlsFailure` là fixture/helper của test harness, không phải Java SDK. Trước khi đánh dấu test PASS, phải xác minh nguồn lỗi là certificate/hostname/PKIX của provider, không phải DNS/connection refused.

### 14.3. Các trạng thái kết quả cần ghi

| Biến | Ví dụ giá trị | Ý nghĩa |
| --- | --- | --- |
| `phase` | `TLS_HANDSHAKE`, `SOAP_SECUREMENT`, `SOAP_VALIDATION` | Xác định tầng thất bại |
| `certificateCase` | `EXPIRED_LEAF`, `UNTRUSTED_CA`, `MISSING_PRIVATE_KEY` | Loại fixture |
| `httpRequestObserved` | true/false | Sender đã tạo POST đến test endpoint? |
| `soapFaultObserved` | true/false | Có SOAP Fault hợp lệ? |
| `domainCalls` | 0 hoặc 1 theo test | Có side effect không? |
| `tlsPeerVerified` | true/false/unknown | TLS peer trust/hostname pass? |
| `wss4jValidated` | true/false/not-reached | Signature/Encryption pass? |
| `noSecretExposure` | true/false | Logs/Fault có rò secret? |

**Không tự kết luận `httpRequestObserved=false` khi handshake fail** chỉ từ việc server endpoint không chạy: client vẫn có thể kết nối TCP/gửi TLS bytes, nhưng **chưa gửi SOAP HTTP POST được xử lý**. Thu thập quan sát ở tầng phù hợp và mô tả chính xác.

## 15. Ma trận negative test đầy đủ theo vai trò certificate

| ID | Tầng | Bên có lỗi | Fixture / biến đổi | Kỳ vọng chính | Có SOAP Fault? |
| --- | --- | --- | --- | --- | --- |
| **TLS-01** | HTTPS | Server | Leaf hết hạn, CA/SAN/EKU đúng | Client từ chối TLS | Thông thường không |
| **TLS-02** | HTTPS | Server | Leaf chưa có hiệu lực | Client từ chối TLS | Thông thường không |
| **TLS-03** | HTTPS | Server | CA B, client chỉ trust A | PKIX path fail | Thông thường không |
| **TLS-04** | HTTPS | Server | Chain thiếu intermediate | Path fail trong test environment được cô lập | Thông thường không |
| **TLS-05** | HTTPS | Server | Leaf được trust nhưng SAN khác host | Endpoint identity fail | Thông thường không |
| **TLS-06** | HTTPS | Server | Certificate chỉ clientAuth | Bị từ chối theo TLS purpose policy | Thông thường không |
| **TLS-07** | HTTPS | Server | Keystore thiếu server private key | Connector không thể thiết lập identity hợp lệ | Không |
| **MTLS-01** | mTLS | Client | Client leaf hết hạn | Server từ chối client authentication | Thông thường không |
| **MTLS-02** | mTLS | Client | Client cert do CA B ký, server chỉ trust A | Server từ chối client | Thông thường không |
| **MTLS-03** | mTLS | Client | Không có client private key/certificate | Không bypass `client-auth=need` | Thông thường không |
| **MTLS-04** | mTLS | Client | Client cert không có clientAuth EKU | Từ chối theo policy/provider | Thông thường không |
| **MTLS-05** | mTLS | Client | Alias/password client private key sai | Client không cung cấp identity hợp lệ hoặc init fail | Thông thường không |
| **WSS-01** | Signature | Client signer | Leaf signer hết hạn, chain đúng | WSS4J không tin signer | Có thể |
| **WSS-02** | Signature | Client signer | CA B, server trust A | WSS4J từ chối untrusted signature | Có thể |
| **WSS-03** | Signature | Client signer | Alias không tồn tại | Client không ký được, không gửi unsigned | Thường không |
| **WSS-04** | Signature | Client signer | Certificate-only entry | Không tìm được private key ký | Thường không |
| **WSS-05** | Signature | Client signer | Private key password sai | Local securement fail | Thường không |
| **WSS-06** | Signature | Client signer | Private key/certificate mismatch | Ký/verify fail hoặc load fail | Phụ thuộc nơi lỗi |
| **WSS-07** | Signature | Server signer | Server thiếu private signing key cho response | Không được trả unsigned response nếu signed response required | Phụ thuộc |
| **WSS-08** | Signature | Server signer | Server signer cert hết hạn/untrusted ở client | Client từ chối signed response | Client-side validation failure |
| **ENC-01** | XML Encryption | Server recipient | Không có decryption private key | Không giải mã, domain không chạy | Có thể |
| **ENC-02** | XML Encryption | Server recipient | Client mã hóa cho public key khác | Decrypt fail | Có thể |
| **ENC-03** | XML Encryption | Server recipient | Password/alias của decryption key sai | Không unwrap/decrypt được | Có thể |
| **ENC-04** | XML Encryption | Client recipient | Server mã hóa response cho public key sai | Client không giải mã response | Client-side validation failure |
| **CERT-01** | PKIX policy | Bên nhận | Certificate bị thu hồi | Từ chối **khi revocation bắt buộc** | Theo TLS/WSS |
| **CERT-02** | Authorization | Bên nhận | Certificate hợp lệ nhưng thuộc partner khác | Từ chối operation/resource access | SOAP authorization fault hoặc policy response |

### 15.1. Không bắt buộc mọi test có cùng HTTP status

- **TLS/mTLS handshake failure:** thường không có SOAP message để tạo Fault. Client nhận transport/TLS exception.
- **WSS4J inbound validation failure:** nếu SOAP Envelope được parse và interceptor chạy, server **có thể** tạo SOAP 1.1 `Client` hoặc SOAP 1.2 `Sender` Fault.
- **Outbound signer thiếu key:** client có thể lỗi **trước gửi**, hoàn toàn không có HTTP response.
- **Outbound server response signing fail:** lỗi có thể xảy ra sau khi domain service đã làm việc, làm outcome nghiệp vụ **không rõ** đối với caller.

Vì vậy **không** viết tất cả tests thành `assertSoapFault("InvalidSecurity")` rồi coi network failures là implementation bug.

## 16. Kiểm thử SOAP Fault, transport error và việc không có side effects

### 16.1. Server-side negative test với MockWebServiceClient

`MockWebServiceClient` chạy SOAP qua Spring-WS server infrastructure và có thể xác minh **interceptor từ chối request không đủ WS-Security**.

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.clientOrSenderFault;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

String validBusinessPayload = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
    """;

MockWebServiceClient mockServer =
        MockWebServiceClient.createClient(applicationContext);

// Không có wsse:Security: test âm xác nhận policy yêu cầu bảo mật.
mockServer.sendRequest(
        withPayload(new StringSource(validBusinessPayload)))
    .andExpect(clientOrSenderFault());

// Thêm assertion verify(domainService, never()).findOrder(...).
~~~

**Đây là đoạn JUnit rút gọn**, cần Spring test context, `@Endpoint` match đúng request, security interceptor được đăng ký và mock domain service. Phương thức `clientOrSenderFault()` kiểm tra SOAP Fault category, **không chứng minh chứng chỉ hết hạn/untrusted**. Với các test certificate, phải gửi SOAP request **được ký thật bằng test private key** và sửa fixture tương ứng.

### 16.2. Tạo SOAP request có chữ ký thật

Một positive/negative test phù hợp:

~~~text
Test client: WebServiceTemplate
    + SaajSoapMessageFactory
    + Jaxb2Marshaller(GetOrderRequest)
    + Wss4jSecurityInterceptor(securementActions="Timestamp Signature")
    + clientSigningCrypto(test private key)

Test server:
    + @Endpoint GetOrderRequest
    + Wss4jSecurityInterceptor(validationActions="Timestamp Signature")
    + validationSignatureCrypto(test truststore)
    + Mock domain service / invocation counter
~~~

Test case `WSS-02` dùng signer key/cert do CA B cấp trong client nhưng server trust CA A. HTTP(S) **vẫn phải thành công** nếu TLS server certificate riêng đang hợp lệ; sau đó WSS4J từ chối chữ ký. Nếu bạn vô tình dùng certificate CA B cũng làm **mTLS identity**, request có thể thất bại từ TLS và không bao giờ chạm WSS4J — đó là một test chưa cô lập đúng tầng.

### 16.3. Client-side test response signed

`MockWebServiceServer` kiểm tra phía `WebServiceTemplate`, nhưng một stub `withPayload(...)` thường chỉ cung cấp XML payload và **không tạo chữ ký X.509 thật**. Để test expired/untrusted **server SOAP signer**:

1. Cho test server tạo SOAP response bằng WSS4J outbound `Signature` với fixture signer.
2. Dùng client `validationActions="Timestamp Signature"` và `validationSignatureCrypto` tin CA A.
3. Lần đầu dùng signer A hợp lệ → response được unmarshaled.
4. Lần sau dùng signer CA B hoặc expired leaf → client từ chối **trước khi domain tiêu thụ response**.
5. Khẳng định không có fallback “nếu verify lỗi thì unmarshal như XML thường”.

Nếu response được tạo qua HTTP(S) server thật, đồng thời kiểm tra TLS server certificate đang hợp lệ để **không nhầm TLS-03 với WSS-08**.

### 16.4. Tránh false positive do test không đi qua interceptor

Một test có thể thấy HTTP 500 nhưng nguyên nhân thật là:

- `@Endpoint` không được component-scan.
- SOAP Envelope dùng sai version, `VersionMismatch`.
- JAXB request root QName không khớp.
- Test fixture thiếu runtime SAAJ/JAXB provider.
- Client POST nhầm `.wsdl` thay vì SOAP endpoint.
- Security interceptor chưa được thêm vào endpoint mapping chain.

Để chứng minh WSS4J validation thật sự đã chạy:

- Có **positive fixture** với cùng Body/URI/SOAP version.
- Chỉ thay certificate/key/trust material.
- Có metrics/counter từ WSS4J/endpoint security rejection hoặc kiểm tra cause/fault đã lọc.
- Assert service invocation count **0** ở negative, **1** ở positive.
- Không để test pass chỉ vì “bất kỳ exception nào”.

## 17. Negative test ký response: rủi ro “server đã xử lý nhưng client không nhận”

Trường hợp dễ bị bỏ qua:

~~~text
Client gửi PlaceOrder request hợp lệ.
Server xác minh request thành công.
Domain service ghi đơn O-100.
Server chuẩn bị ký SOAP response.
WSS4J không tìm được server-signing private key.
Server không thể gửi response được ký theo hợp đồng.
Client timeout hoặc nhận server error.
~~~

Client **không thể biết chắc** đơn hàng đã tạo hay chưa. Đây là lỗi **outbound server securement**, có thể xảy ra sau business side effect.

### Biện pháp phòng ngừa

1. **Preflight key material** khi ứng dụng khởi động hoặc trước khi mở nhận lưu lượng: có signing alias, private key giải được, certificate còn hạn, key pair và algorithms phù hợp.
2. Khi dùng HSM/KMS, theo dõi availability và quyền sử dụng key; cấu hình fail closed nếu không thể tạo response hợp policy.
3. Với operation gây side effect, có **business idempotency key** và endpoint truy vấn trạng thái/reconciliation.
4. Không cố phát response **unsigned** để “báo thành công” nếu WSDL/WS-Policy yêu cầu signed response.
5. Kiểm thử cố ý làm unavailable response-signing key và xác định outcome service/transaction theo thiết kế, thay vì khẳng định domain luôn rollback.

**Không đồng nhất WS-Security replay với business idempotency:** khi retry một nghiệp vụ, request mới có thể cần Timestamp/Nonce/Signature mới nhưng cùng idempotency key gắn với caller và business payload.

## 18. Kiểm thử chuỗi chứng chỉ với nhiều bên và liên thông

Trong doanh nghiệp, SOAP client có thể gọi một .NET/WCF service qua ESB/reverse proxy; certificate có thể được xác minh ở nhiều chặng:

~~~mermaid
flowchart LR
    A["Spring-WS client"] -->|"TLS #1"| B["API gateway / proxy"]
    B -->|"TLS #2"| C["SOAP service"]
    A -->|"WS-Security signed/encrypted SOAP"| C
    C -->|"WS-Security signed response"| A
~~~

### 18.1. Các cặp trust cần phân biệt

| Chặng | Ai xác minh? | Certificate nào? | Test âm chính |
| --- | --- | --- | --- |
| Client → Gateway | Client | Gateway HTTPS server cert | Expired/untrusted/SAN |
| Gateway → Backend | Gateway | Backend HTTPS cert | Expired/untrusted/chain |
| mTLS Client → Gateway | Gateway | Client mTLS cert | Expired/wrong issuer/no key |
| mTLS Gateway → Backend | Backend | Gateway outbound mTLS cert | Wrong identity/expired |
| SOAP request | Backend WS-Security | Client SOAP signer cert | Expired/untrusted/wrong signer |
| SOAP response | Client WS-Security | Backend SOAP signer cert | Expired/untrusted signer |
| Encrypted request | Backend WS-Security | Recipient private key | Wrong/missing private key |

**TLS termination tại gateway không tự làm WS-Security Signature trở nên không cần thiết** nếu hợp đồng yêu cầu bảo vệ message đến backend. Ngược lại, có WS-Security không cho phép bỏ qua hostname verification của HTTPS.

### 18.2. Proxy không được âm thầm sửa SOAP Header đã ký

Nếu `wsa:To`, `wsa:Action`, custom tenant header hoặc SOAP Body nằm trong signed parts, một proxy sửa message XML có thể làm chữ ký hỏng. Test cần:

1. Gửi request đã ký qua proxy thực tế hoặc fixture tương tự.
2. Kiểm tra WSS4J verify thành công khi proxy không sửa signed bytes.
3. Cố ý sửa một signed Header ở môi trường test → verify phải fail.
4. Khẳng định proxy rewrite URL HTTP không dẫn tới việc tự sửa `wsa:To` ngoài hợp đồng.
5. Không bỏ signed headers khỏi policy để làm proxy integration “xanh”.

### 18.3. Test .NET/WCF/ESB

Các stack có thể khác nhau về:

- Nơi chứa `BinarySecurityToken` hoặc cơ chế `KeyIdentifier` (`DirectReference`, `IssuerSerial`, ...).
- Signature/Digest/Canonicalization algorithms.
- Thứ tự `Signature` và `Encrypt`, signed parts.
- SOAP 1.1/1.2 Fault structure và certificate validation behavior.
- Mutual TLS client certificate selection/alias.
- OCSP/CRL availability và certificate chain construction.

Không suy một “cấu hình Spring-WS pass” sẽ pass trên mọi stack. Cần **contract/WS-Policy và wire-level fixtures** mà hai bên đồng ý, với bộ negative tests expiry/trust/mismatch tương ứng.

## 19. Kiểm soát chứng chỉ trong CI/CD và môi trường test

### 19.1. Tránh bài test phụ thuộc đồng hồ thực theo cách mong manh

**Không** tạo một certificate “good” có hạn 24 giờ rồi dùng mãi trong CI; một ngày nào đó tất cả tests hợp lệ sẽ fail vì certificate đã hết hạn, dù code không thay đổi.

Các lựa chọn:

| Hình thức fixture | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Leaf **expired từ lâu** với thời hạn cố định | Test âm luôn xác định sau hạn ở thời điểm hiện tại | Chỉ test một kịch bản thời hạn |
| Leaf **valid dài hạn** chỉ cho test | Positive CI ít biến động | Cần theo dõi/rotate trước ngày hết hạn |
| PKIX unit test dùng `setDate(...)` | Deterministic khi test từng thời điểm | Không thay thế TLS handshake runtime |
| Generate cert mỗi CI run bằng test CA mới | Bảo đảm positive cert valid hiện tại | Tăng độ phức tạp, phải kiểm soát private test keys và reproducibility |
| Clock injection ở application/domain layer | Test chính sách ứng dụng dễ dàng | JSSE/WSS4J provider không mặc định dùng `Clock` này |

**Không đổi đồng hồ OS/JVM toàn cục hoặc sửa NTP của shared CI worker** chỉ để ép TLS fail: dễ làm hỏng test khác, timestamp, token và hệ thống phụ trợ. Với handshake expiry, dùng **fixture leaf đã hết hạn**; với unit/PKIX boundary, dùng API thời gian cố định như `X509Certificate.checkValidity(Date)`/`PKIXParameters.setDate(Date)`.

### 19.2. Test certificates sinh động và khả năng tái lập

Nếu CI tạo test PKI ở mỗi build:

1. Tạo test CA A và CA B độc lập trong môi trường cách ly.
2. Dùng serial number/SAN/EKU/KeyUsage rõ ràng cho từng fixture.
3. Có bước tạo expired/future leaves từ một certificate issuer có thể chỉ định validity window; lưu metadata test kèm fixture.
4. Giữ secret material chỉ trong workspace tạm, quyền file hạn chế.
5. Mỗi test load đúng identity/truststore đã chọn, không dựa vào JVM global `cacerts` ngoài kế hoạch.
6. Xóa private keys tạm sau test theo policy.
7. Trong báo cáo, lưu **public fingerprint/serial/time metadata**, không xuất private keys.

Nếu công cụ chứng chỉ không hỗ trợ set NotBefore/NotAfter theo yêu cầu từ một lệnh đơn giản, dùng CA test library phù hợp hoặc fixture đã tạo offline; **không sử dụng certificate production đã hết hạn** như một shortcut.

### 19.3. Cách chia job test trong pipeline

~~~text
PR / fast tests
  - X509 validity fixed-time tests
  - Keystore alias / entry type / pair checks
  - PKIX chain validation with isolated anchors
  - MockWebServiceClient missing-security negative test

Integration pipeline
  - Embedded HTTPS server: expired/untrusted/SAN
  - Embedded mTLS: expired client/CA mismatch/no key
  - WSS4J request signature: expired/untrusted/missing key
  - WSS4J encryption/decryption: recipient key mismatch
  - Secure response validation: expired/untrusted server signer

Pre-release / contract interoperability
  - Gateway/proxy topology, certificate rotation
  - .NET/WCF or ESB partner test environments
  - Revocation behavior, key algorithm restrictions
  - WS-Addressing signed headers, MTOM attachment coverage
  - Concurrent load/retry/idempotency scenarios
~~~

**Không chạy negative tests với certificate thật của đối tác trên production endpoint** mà chưa có sự cho phép và kế hoạch vận hành. Kết quả lỗi có thể kích hoạt anti-abuse lockout, audit alert hoặc làm gián đoạn kết nối.

## 20. Bảo mật fixture và nhật ký lỗi

Certificate public có thể được lưu để đối chiếu fingerprint; **private key và mật khẩu vẫn là bí mật**, kể cả khi một private key test đã được đặt tên `demo`. Với production keys, tuyệt đối không xuất ra file logs hoặc dán vào support ticket.

### Những thông tin nên log

~~~text
partner=orders-partner
operation=GetOrder
phase=SOAP_VALIDATION
failureClass=UNTRUSTED_SIGNER
soapVersion=1.1
publicCertFingerprint=SHA256:... (đã lọc)
requestCorrelationId=req-8f21
domainCalls=0
~~~

Đây là **log format gợi ý**, không phải log Spring-WS/WSS4J tự cung cấp. Với logs production, dùng cơ chế correlation đã được kiểm soát, tránh để metadata trở thành high-cardinality metrics hoặc lộ danh tính không cần thiết.

### Những thông tin không nên log

- Raw `wsse:Security`, UsernameToken password/digest, Nonce, private key bytes.
- PKCS#12/JKS password, key password và bí mật tải từ secret manager.
- Toàn SOAP Body chứa PII, hợp đồng/tài liệu nhạy cảm.
- Decrypted SOAP message, raw MTOM attachment.
- Chứng chỉ private key xuất ra dưới dạng PEM.
- Lý do trust/alias cực chi tiết trong SOAP Fault công khai.

**Thông điệp lỗi cho đối tác** nên trung tính, ví dụ “Yêu cầu không đáp ứng chính sách bảo mật”. Internal logs có thể phân loại `EXPIRED_CERTIFICATE`, `UNTRUSTED_CHAIN`, `MISSING_SIGNING_KEY` sau khi lọc nội dung bí mật.

### Không “sửa” negative test bằng cách tắt security

Những cách chữa sai cần bị bắt trong code review:

~~~text
TrustManager chấp nhận tất cả certificate.
HostnameVerifier luôn trả true.
Tắt mTLS client-auth trong production.
Tắt WSS4J validationActions khi partner cert lỗi.
Tắt certificate expiry check.
Tự chọn một alias private key bất kỳ nếu alias cấu hình thiếu.
Fallback từ signed SOAP response sang unsigned XML.
Tắt timestamp/replay verification để xử lý retry.
~~~

Các thay đổi này biến một lỗi cấu hình thành **lỗ hổng bảo mật**. Sửa đúng là cấp certificate/chain/key material phù hợp, cập nhật trust policy có kiểm soát, đồng bộ clocks/rotation và kiểm thử lại.

## 21. Chẩn đoán nhanh lỗi chứng chỉ và khóa

| Triệu chứng | Cần điều tra | Điều không nên làm |
| --- | --- | --- |
| `PKIX path building failed` ở HTTPS | CA, intermediate, truststore client/server, chain được gửi | Trust-all, disable SSL verify |
| `CertificateExpiredException` trong TLS | Leaf validity, clock, trust anchors và endpoint đúng | Đổi client time thủ công để pass |
| `CertificateNotYetValidException` | NotBefore, clock skew, CA issuance pipeline | Nới TTL mọi nơi |
| Hostname verification error | SAN, URL host, proxy TLS termination | NoopHostnameVerifier |
| `SSLHandshakeException` khi mTLS | Client cert, private key, server client-auth, EKU/trust | Chuyển sang HTTP |
| Test mTLS dùng cert-only store | Không có PrivateKeyEntry | Import thêm public cert mà mong có private key |
| HTTP(S) pass nhưng SOAP `InvalidSecurity` | WSS4J trust/signature/policy, Body/Headers signed | Thay SSL truststore để chữa SOAP signature |
| Client lỗi trước khi POST | Signing alias/password/private key hoặc JAXB/OXM setup | Tăng HTTP timeout |
| SOAP decrypt fail | Recipient certificate, private decryption key, alias/password, algorithms | Bỏ Encrypt action |
| Server response không ký được | Server signer private key unavailable | Trả unsigned response khi contract required |
| Cert chain hợp lệ nhưng operation bị từ chối | Principal-to-partner/tenant/permission mapping | Coi valid cert là superuser |
| Revoked cert vẫn được chấp nhận | Revocation chưa được bật/CRL-OCSP fail-open | Khẳng định expiry test bao phủ revocation |
| Kết quả thay đổi giữa các pods | Khác trust/key material, clocks, caches | Tắt validation trên một pod |
| Test thay certificate vẫn pass | Reused TLS connection/SSLSession | Kết luận verifier bỏ kiểm hạn |
| SOAP Fault có chi tiết alias/key | Exception nội bộ bị lộ trong faultstring | Log nhiều hơn raw secrets |

### Quy trình debug có thể lặp lại

~~~mermaid
flowchart TD
    A["SOAP call lỗi"] --> B{"Có TLS/mTLS handshake thành công?"}
    B -->|Không| C["Leaf validity, CA chain, SAN, EKU,<br/>identity private key, client-auth"]
    B -->|Có| D{"WS-Security outbound ký/mã hóa được?"}
    D -->|Không| E["Signing/decryption alias, PrivateKeyEntry,<br/>password, recipient key, algorithm"]
    D -->|Có| F{"Server WSS4J validate/giải mã được?"}
    F -->|Không| G["Signer trust, expiry, signed parts,<br/>recipient private key, crypto policy"]
    F -->|Có| H{"XSD/JAXB và principal authorization đạt?"}
    H -->|Không| I["Contract, tenant/resource permission"]
    H -->|Có| J["Domain service và signed response"]
    J --> K{"Client verify/decrypt response đạt?"}
    K -->|Không| L["Server signing cert trust/expiry,<br/>client decryption private key"]
    K -->|Có| M["Thành công; kiểm tra dữ liệu nghiệp vụ"]
~~~

**Dòng đầu tiên không đạt** là gợi ý tầng phải kiểm tra trước. Nếu HTTPS handshake không xong, không nên chỉnh JAXB generated classes. Nếu HTTPS pass nhưng WSS4J từ chối signer, không nên thêm CA tùy tiện vào **TLS truststore** rồi cho rằng đã thay WS-Security trust Crypto.

## 22. Bài tập thực hành và câu hỏi tình huống

### Bài 1 — Test một chứng chỉ hết hạn ở đúng tầng

Chuẩn bị một leaf `test-server-expired` có SAN `DNS:soap.test.local`, được ký bởi CA A (đang trusted) và chỉ sai `NotAfter`. Start HTTPS test server với certificate/key đó rồi gọi bằng `WebServiceTemplate` sử dụng truststore A. Ghi:

- Có tạo được SOAP HTTP response hay không?
- Exception thuộc transport/TLS hay SOAP Fault?
- `@Endpoint` và domain service có được gọi không?
- Cùng test khi thay leaf bằng `test-server-valid` còn hạn thì điều gì đổi?

**Đáp án kỳ vọng:** expired leaf bị TLS client từ chối, không chạy nghiệp vụ; positive valid leaf pass. Không được tắt hostname verification hoặc chuyển sang HTTP.

### Bài 2 — Unit test thời gian có thể tái lập

Dùng `X509Certificate.checkValidity(Date)` với một `Instant` cố định, kiểm `CertificateExpiredException` và `CertificateNotYetValidException`. Sau đó thêm một test chain trust dùng `PKIXParameters.setDate(Date)`.

**Câu hỏi:** vì sao hai unit tests này vẫn chưa chứng minh mTLS handshake hoạt động đúng?

**Hướng trả lời:** chúng không kiểm chứng client certificate selection, TLS protocol, hostname/SAN, HTTP sender hay server client-auth thực tế. Cần thêm embedded HTTPS/mTLS test.

### Bài 3 — Untrusted CA với positive control

Tạo CA A/CA B độc lập. Client chỉ trust A, server dùng leaf B nhưng có SAN, EKU và validity đúng. Thực hiện TLS call và xác minh bị từ chối. Lặp lại với leaf A để chứng minh request hợp lệ pass.

**Câu hỏi:** nếu test leaf B bị từ chối nhưng bạn đồng thời thay hostname, có thể khẳng định test CA trust đạt không?

**Hướng trả lời:** không; cần chỉ thay CA/chain, giữ hostname/SAN và mọi thông số còn lại đúng.

### Bài 4 — Thiếu private key trong PKCS#12

Tạo một store chỉ có `trustedCertEntry` cho `client-cert`. Kiểm bằng `keytool -list -v` và `KeyStore.isCertificateEntry(...)`. Dùng store đó làm identity trong client mTLS tới server `client-auth=need`.

**Đáp án kỳ vọng:** client không thể chứng minh identity bằng private key và server không chấp nhận như một mTLS client hợp lệ. Nhập thêm certificate public **không** giải quyết vấn đề.

### Bài 5 — Alias và password của SOAP Signature

Tạo một signer key/certificate hợp lệ trong test keystore. Cấu hình WSS4J outbound `Signature` với alias tồn tại, chạy positive test. Sau đó:

1. Đổi sang alias không tồn tại.
2. Đổi sang alias chỉ có certificate.
3. Đổi private-key password.
4. Kiểm tra local securement fail và không có request unsigned.

**Điểm cần nêu:** error không nhất thiết là `SoapFaultClientException`; phía client có thể chưa gửi HTTP POST.

### Bài 6 — Chứng chỉ signer không đáng tin

Cho WSS4J server `validationSignatureCrypto` tin signer A. Tạo SOAP request được ký bằng private key/certificate B **vẫn hợp lệ về hạn và có chữ ký mật mã đúng**. Gửi qua HTTPS có TLS riêng luôn hợp lệ.

**Đáp án kỳ vọng:** SOAP signature/trust validation bị từ chối, không gọi endpoint nghiệp vụ. Nếu TLS cũng fail, cần sửa fixture để tách đúng tầng.

### Bài 7 — Thiếu private key để giải mã

Client mã hóa SOAP Body bằng public certificate A. Server chỉ có private key B. Sau đó server có private key A để làm positive control.

**Hướng trả lời:** chỉ cấu hình `validationDecryptionCrypto` trỏ truststore chứa public cert A không đủ. Decryption đòi private key đúng, password/callback và thuật toán được hỗ trợ.

### Bài 8 — Signed response hết hạn

Cho server SOAP ký response bằng certificate signer hết hạn, trong khi HTTPS certificate server vẫn hợp lệ. Client yêu cầu response `Signature` và `Timestamp`.

**Đáp án kỳ vọng:** client từ chối response ở WSS4J validation, không unmarshal rồi dùng dữ liệu “tạm”. Phân biệt được với HTTPS expiry.

### Bài 9 — Certificate rotation và pooled TLS connection

Trong test server, thay certificate A bằng certificate B sau khi client đã thiết lập kết nối. Gửi lại qua connection pool và so với một client/SSLContext mới.

**Câu hỏi:** vì sao hai test có thể cho kết quả khác nhau?

**Hướng trả lời:** connection hoặc SSLSession cũ có thể được tái sử dụng; phải thiết lập handshake mới khi kiểm certificate mới. Đồng thời cần quy trình trust rotation có kiểm soát.

### Bài 10 — Cross-platform incident

Một SOAP client Java gọi .NET/WCF endpoint. HTTPS pass, SOAP request được ký, nhưng server trả `InvalidSecurity`. Hai đội đều khẳng định “certificate còn hạn”. Hãy viết kế hoạch xử lý:

1. Xác nhận SOAP version, action, body QName và WSS4J/WCF policy.
2. Đối chiếu certificate signer fingerprint/issuer/chain, không chỉ `NotAfter`.
3. Kiểm tra key identifier, signed parts, canonicalization, algorithms, timestamp/clock.
4. Xác minh principal mapping và signer được phép gọi operation.
5. Dùng test fixtures A/B, không dán private keys/password vào ticket.

**Hướng trả lời:** certificate còn hạn là **điều kiện cần nhưng chưa đủ**; chữ ký có thể hợp lệ về mật mã nhưng signer không được trust hoặc signed parts/policy sai.

### Bài 11 — Security regression review

Một PR thêm `TrustAllStrategy` để “giải quyết lỗi certificate staging”, đồng thời fallback gửi SOAP không ký khi client signing alias không tìm thấy. Hãy chỉ ra lỗi bảo mật, viết negative test bắt regression và đề xuất cách sửa an toàn.

**Đáp án kỳ vọng:** không chấp nhận PR; cập nhật CA/chain/alias/private key đúng trong staging, giữ validation bắt buộc và fail closed.

## 23. Checklist nghiệm thu kiểm thử certificate và private key

| Nhóm | Phải đạt |
| --- | --- |
| **Scope rõ** | Biết đang kiểm TLS server, mTLS client, SOAP signer hay SOAP decryption recipient |
| **Positive baseline** | Cùng request/URI/hostname/CA/key algorithms với fixture hợp lệ phải pass |
| **Expired** | Leaf đã hết hạn bị từ chối, có test `NotBefore` ở tương lai |
| **Trust** | CA B không được trust bị từ chối; chain thiếu intermediate được kiểm đúng môi trường |
| **Hostname** | SAN mismatch bị từ chối mà không tắt verification |
| **Usage** | `serverAuth`, `clientAuth` và KeyUsage/algorithms phù hợp vai trò |
| **Alias** | Alias được kiểm, không chọn “key đầu tiên” nếu alias cấu hình không tồn tại |
| **Entry type** | Identity cần PrivateKeyEntry, truststore không cần private key |
| **Key pair** | Private key khớp public cert, key password và chain đúng |
| **mTLS** | Không certificate/private key hoặc expired/untrusted client bị handshake reject |
| **WS-Security Signature** | Signer cert expired/untrusted và thiếu signing key bị từ chối, không fallback unsigned |
| **WS-Security Encryption** | Recipient không có decryption private key hoặc key sai bị từ chối |
| **Signed response** | Client validate signer của response và từ chối expired/untrusted cert |
| **Certificate policy** | Trust anchor, signer-to-partner mapping, revocation/usage theo contract |
| **SOAP Fault vs TLS** | Không kỳ vọng SOAP Fault từ handshake error; không nuốt local signing error |
| **Side effects** | Endpoint/domain không thực thi khi inbound security fail; outbound error có idempotency/reconciliation |
| **CI determinism** | Fixture/clock kiểm soát được; không đổi OS time hoặc dựa truststore máy dev |
| **TLS sessions** | Rotation tests bắt buộc handshake mới; không chỉ reused pooled connection |
| **Cross-platform** | Java/.NET/ESB khớp SOAP binding, key identifier, signature/encryption và certificate trust |
| **Hardening** | Không trust-all, không hostname bypass, không tắt validation, không downgrade |
| **Privacy** | Không log private keys/password, SOAP Body nhạy cảm, UsernameToken |
| **Operations** | Certificate expiry monitoring, rotation, alert và rollback plan được thử trước hạn |

## 24. Tài liệu chuẩn để đối chiếu

Những ví dụ minh họa chủ yếu dùng **Java 17+**, **Spring-WS 4.1.x** và Apache WSS4J 2.x. Thay đổi version có thể ảnh hưởng API/exception types và cách cấu hình TLS provider; trước khi áp dụng vào hệ thống thật hãy đối chiếu:

- [Java SE — X509Certificate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html): `checkValidity()`, `checkValidity(Date)`, `getNotBefore()` và `getNotAfter()`.
- [Java SE — PKIXParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, `setDate(Date)` và revocation validation options.
- [Java SE — KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): `isKeyEntry`, `isCertificateEntry`, `getKey`, `getCertificateChain`.
- [Java SE — KeyManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html) và [TrustManagerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): TLS identity và trust configuration.
- [Spring Web Services Reference — Security](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): Signature, Encrypt, certificate trust, Crypto, SOAP Fault và client/server WSS4J integration.
- [Spring-WS 4.1.4 — Wss4jSecurityInterceptor API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/security/wss4j2/Wss4jSecurityInterceptor.html): `validationSignatureCrypto`, `securementSignatureCrypto`, `validationDecryptionCrypto`, key identifiers và revocation.
- [Spring-WS — CryptoFactoryBean](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/security/wss4j2/support/CryptoFactoryBean.html): nạp key/trust material vào Apache WSS4J `Crypto`.
- [Apache WSS4J](https://ws.apache.org/wss4j/): cấu hình Crypto/trust, XML Signature/Encryption và processing errors.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS trust, server identity và cấu hình an toàn.
- [OWASP Web Service Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Web_Service_Security_Cheat_Sheet.html): WS-Security, request processing và bảo vệ thông điệp.

**Kết luận:** Kiểm thử chứng chỉ trong **SPRING_WEB_SERVICES** phải phân biệt rõ **hết hạn**, **không tin cậy** và **thiếu/sai private key**, đồng thời xác định lỗi phát sinh tại **TLS/mTLS handshake**, **WSS4J ký hoặc giải mã outbound/inbound**, hay **authorization nghiệp vụ**. Một bài test đáng tin cần có positive control, thay đổi từng biến độc lập, kiểm tra error boundary và không có side effect, bảo vệ secrets và không sử dụng trust-all/unsigned fallback. Khi các fixture và phép kiểm được áp dụng ở cả phía client lẫn server, từ HTTPS đến SOAP Signature/Encryption và signed response, hệ thống mới có cơ sở chứng minh việc **từ chối danh tính/khóa không hợp lệ một cách nhất quán, an toàn và có thể tái lập**.
