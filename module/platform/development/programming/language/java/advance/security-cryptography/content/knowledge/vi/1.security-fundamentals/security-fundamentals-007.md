# 1.7. Bản đồ JCA, JCE, JSSE, JAAS, PKI và các công cụ của JDK

## Mục tiêu học tập

Sau bài này, bạn có thể (1) phân biệt các lớp công nghệ bảo mật của Java, (2) tìm đúng API khi cần băm, mã hóa, ký số, kết nối TLS hoặc xác thực người dùng, (3) hiểu vì sao `KeyStore`, certificate và truststore xuất hiện ở nhiều lớp, và (4) dùng `keytool`, `jarsigner` cùng cơ chế debug của JDK để kiểm tra vấn đề thực tế. Đây là **bản đồ kiến trúc và cách chọn công cụ**, không phải hướng dẫn tự thiết kế một giao thức mật mã.

## 1. Nhìn toàn cảnh: mỗi tên trả lời câu hỏi nào?

| Thành phần | Vai trò chính | API/khái niệm đại diện | Ví dụ tình huống |
| --- | --- | --- | --- |
| **JCA** – Java Cryptography Architecture | Kiến trúc API và **provider** cho các dịch vụ mật mã, khóa, chứng thư và kiểm tra chứng thư | `MessageDigest`, `Signature`, `SecureRandom`, `KeyPairGenerator`, `KeyStore`, `CertificateFactory` | Băm SHA-256, ký và kiểm chữ ký Ed25519, đọc chứng thư |
| **JCE** – Java Cryptography Extension | Tên lịch sử cho phần API mật mã như mã hóa, MAC, khóa bí mật; **ngày nay đã tích hợp trong JCA/JDK**, không phải hệ thống provider cạnh tranh với JCA | `javax.crypto.Cipher`, `Mac`, `KeyGenerator`, `SecretKey`, `GCMParameterSpec` | Mã hóa AES-GCM, tạo HMAC |
| **JSSE** – Java Secure Socket Extension | Cung cấp giao tiếp mạng bảo mật bằng TLS/DTLS, dùng primitive/provider và thông tin tin cậy bên dưới | `SSLContext`, `SSLSocket`, `SSLEngine`, `KeyManager`, `TrustManager` | Client HTTPS, server TLS, mTLS |
| **JAAS** – Java Authentication and Authorization Service | Mô hình **xác thực danh tính có thể cắm module** và `Subject`/`Principal` đại diện người dùng hoặc dịch vụ | `LoginContext`, `LoginModule`, `CallbackHandler`, `Subject` | Đăng nhập Kerberos hoặc một cơ chế xác thực tích hợp JAAS |
| **PKI** – Public Key Infrastructure | Hạ tầng tin cậy quanh khóa công khai, X.509, CA và chuỗi chứng thư; **không phải một thư viện độc lập duy nhất** | `X509Certificate`, `CertPath`, `CertPathBuilder`, `CertPathValidator`, `TrustAnchor` | Quyết định có tin chứng thư server hay không |
| **Công cụ JDK** | Tạo/kiểm tra khóa, certificate, CSR, chữ ký JAR và chẩn đoán bảo mật | `keytool`, `jarsigner`, `jar`, `java -D...debug=...` | Chuẩn bị keystore cho TLS, kiểm JAR ký số, tìm lỗi handshake |

**Điểm nối quan trọng:** JCE nằm trong hệ sinh thái JCA; JSSE sử dụng các dịch vụ/provider mật mã và thường kiểm chứng X.509 theo PKI; JAAS xử lý xác thực danh tính ở một tầng khác. Một kết nối HTTPS thành công **không tự động** nghĩa là người dùng đã đăng nhập JAAS.

```text
Ứng dụng Java
├─ Bảo vệ dữ liệu/nghiệp vụ
│  └─ JCA + JCE → provider → hash, MAC, mã hóa, khóa, chữ ký
├─ Giao tiếp mạng
│  └─ JSSE (TLS/DTLS) → KeyManager / TrustManager
│                       └─ PKI/X.509 + các dịch vụ JCA
├─ Đăng nhập/xác thực danh tính theo JAAS
│  └─ LoginContext → LoginModule → Subject/Principal
└─ Vận hành
   └─ keytool / jarsigner / security properties / TLS debug
```

Cùng một `KeyStore` có thể được ứng dụng JCA dùng để đọc khóa ký dữ liệu, hoặc JSSE dùng làm nguồn khóa riêng/chứng thư TLS. **Vai trò sử dụng** mới quyết định nó là kho danh tính hay kho tin cậy, không chỉ phần mở rộng tệp.

## 2. JCA: API engine tách khỏi triển khai provider

JCA định nghĩa các lớp *engine* với mô hình `getInstance(algorithm)`. Ứng dụng yêu cầu dịch vụ bằng tên thuật toán; JDK tra các **security provider** được đăng ký để tìm triển khai phù hợp. Điều này cho phép bổ sung provider phần mềm, HSM/PKCS#11 hoặc provider chuyên biệt mà không viết lại toàn bộ code sử dụng engine.

Ví dụ:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] sha256 = digest.digest(data);

Signature verifier = Signature.getInstance("Ed25519");
// verifier.initVerify(publicKey); verifier.update(data); verifier.verify(signature);
```

Đây là **đoạn minh họa**, `data`/`publicKey`/`signature` phải được cung cấp; chương trình hoàn chỉnh nằm ở mục 8. `MessageDigest` chỉ băm dữ liệu, còn `Signature` dùng khóa bất đối xứng để chứng thực chữ ký.

Quy trình chọn provider:

1. Ứng dụng gọi `Cipher.getInstance("AES/GCM/NoPadding")` hoặc `Signature.getInstance("Ed25519")`.
2. JCA xét provider theo cấu hình/thứ tự ưu tiên và khả năng hỗ trợ dịch vụ; có thể chỉ định provider khi thật sự cần.
3. Engine trả về đối tượng triển khai; ứng dụng khởi tạo bằng khóa và tham số rồi mới xử lý dữ liệu.
4. Có thể truy vấn provider phục vụ đối tượng qua `getProvider()` để chẩn đoán.

Các nhóm engine nên nhận diện:

| Nhiệm vụ | Chọn API | Không nên nhầm với |
| --- | --- | --- |
| Băm không khóa | `MessageDigest` | HMAC/chữ ký: riêng hash **không xác thực người gửi** |
| Mã xác thực dùng bí mật chung | `Mac` | Chữ ký số: HMAC không cho bên thứ ba xác minh bằng public key |
| Ký/kiểm chữ ký bất đối xứng | `Signature` | Mã hóa: chữ ký không che giấu plaintext |
| Mã hóa/giải mã | `Cipher` | Hash: mã hóa có thể giải mã bằng khóa thích hợp |
| Sinh ngẫu nhiên an toàn | `SecureRandom` | `Random` cho mô phỏng/game |
| Sinh khóa đối xứng/bất đối xứng | `KeyGenerator` / `KeyPairGenerator` | `KeyFactory` biến đổi biểu diễn khóa đã có |
| Lưu/truy cập khóa/chứng thư | `KeyStore` | Certificate không chứa private key của chủ thể |
| Xây/kiểm chuỗi chứng thư | `CertPathBuilder` / `CertPathValidator` | Chỉ đọc certificate bằng `CertificateFactory` |

Đừng xem tên thuật toán là bảo đảm toàn bộ thiết kế an toàn: chế độ mã hóa, IV/nonce, độ dài khóa, vòng đời khóa, thuật toán bị vô hiệu, kích thước dữ liệu và cấu hình provider vẫn quan trọng. Đặc biệt không dựa vào mặc định mơ hồ như `Cipher.getInstance("AES")`; hãy yêu cầu transformation đầy đủ.

Có thể tự quan sát provider của JVM:

```java
import java.security.Provider;
import java.security.Security;

public class ProvidersDemo {
    public static void main(String[] args) {
        for (Provider p : Security.getProviders()) {
            System.out.println(p.getName() + " " + p.getVersionStr());
        }
    }
}
```

Chạy bằng `javac ProvidersDemo.java` rồi `java ProvidersDemo`. **Danh sách và phiên bản provider phụ thuộc bản JDK/nhà cung cấp/hệ điều hành**, nên không có stdout cố định. Đừng hard-code tên `SunJCE` hay `SunJSSE` nếu ứng dụng cần chạy trên nhiều JVM/provider, trừ khi có yêu cầu triển khai rõ ràng.

## 3. JCE: mật mã ứng dụng trong cùng kiến trúc JCA

Tên **JCE** xuất phát từ thời các tính năng mã hóa được phát hành như phần mở rộng. Trong Java hiện đại, `javax.crypto` là một phần bình thường của JDK và vận hành qua cơ chế provider của JCA. Không cần “cài JCE riêng” cho Java 17+ chuẩn để dùng AES/HMAC thông thường.

Các lựa chọn thực dụng:

- **Bảo mật bí mật dữ liệu lưu trữ**: thường dùng mã hóa có xác thực (*AEAD*) như `AES/GCM/NoPadding`. Dữ liệu giải mã phải được xác minh tag; bản mã chỉ được chấp nhận khi xác thực thành công.
- **Bảo đảm toàn vẹn và xác thực giữa các bên giữ cùng khóa bí mật**: dùng `HmacSHA256` (API `Mac`); người không biết khóa không tạo được MAC hợp lệ.
- **Chứng minh sở hữu private key cho dữ liệu**: dùng `Signature` với cặp khóa; người xác minh cần public key **và ngữ cảnh tin cậy** nếu muốn gắn chữ ký với một danh tính.
- **Lưu mật khẩu người dùng**: không dùng SHA-256/HMAC đơn thuần như password hash. Dùng cơ chế dẫn xuất mật khẩu chậm, có salt riêng và tham số chi phí phù hợp (ví dụ PBKDF2 qua `SecretKeyFactory` khi phù hợp chính sách; hệ thống có thể dùng giải pháp Argon2/bcrypt được kiểm chứng).

Với AES-GCM, hãy ghi nhớ bốn thành phần: **khóa bí mật**, **nonce/IV duy nhất cho mỗi lần mã hóa với cùng khóa** (thường 12 byte), **ciphertext** và **authentication tag** (thường 128 bit). Có thể thêm **AAD** (authenticated associated data): AAD được xác thực nhưng không được mã hóa. Bên giải mã cần cùng khóa, IV, AAD tương ứng và ciphertext kèm tag. Tuyệt đối không tái sử dụng cặp khóa–nonce trong GCM; không tự tạo nonce bằng `Random` hay hằng số.

Dùng `SecureRandom` cho vật liệu ngẫu nhiên an toàn và `KeyGenerator` cho khóa. Phân phối, lưu, thay mới và thu hồi khóa phải được thiết kế riêng; API mã hóa không tự giải quyết vấn đề quản lý khóa. Không ghi private key, secret key, token, plaintext nhạy cảm hoặc mật khẩu keystore vào log.

## 4. JSSE: dùng TLS cho dữ liệu trên đường truyền

JSSE nằm trong `javax.net.ssl`. Nó cung cấp TLS/DTLS qua `SSLContext`, `SSLSocket`/`SSLServerSocket`, `SSLEngine` và các factory. Các API cao hơn như `java.net.http.HttpClient` dùng TLS để gọi HTTPS mà phần lớn ứng dụng không phải tự quản lý từng bước handshake.

Các vai trò thường gặp:

| Thành phần | Trách nhiệm |
| --- | --- |
| `SSLContext` | Cấu hình/ngữ cảnh TLS dùng để tạo socket/engine, mang thông tin key/trust manager và trạng thái phiên |
| `KeyManager` | Chọn **private key + chuỗi certificate của chính mình** khi cần chứng minh danh tính với phía đối diện |
| `TrustManager` | Đánh giá **certificate của phía đối diện** theo tập chứng thư/anchor tin cậy và chính sách |
| `SSLEngine` | Xử lý TLS độc lập với cách ứng dụng thực hiện I/O; phù hợp mô hình nonblocking |
| `SSLSocket` | Socket có TLS để truyền dữ liệu qua kênh đã bắt tay bảo mật |

Luồng HTTPS thông thường (mô hình đơn giản hóa):

1. Client kết nối server và trao đổi tham số TLS; server xuất trình chứng thư X.509 cùng chuỗi cần thiết.
2. Client kiểm tra chuỗi theo các trust anchor được chấp nhận, thời hạn, ràng buộc và chính sách thuật toán; client HTTPS cũng phải kiểm tra **tên host** khớp danh tính chứng thư (thường ở SAN).
3. Handshake thiết lập khóa phiên; dữ liệu ứng dụng sau đó được mã hóa và xác thực trong kênh TLS.
4. Với **mTLS**, server còn yêu cầu certificate của client, và client chọn khóa/chứng thư tương ứng để xác thực hai chiều. Điều này không tự thay thế mọi yêu cầu phân quyền nghiệp vụ.

Trong ứng dụng HTTPS bình thường, ưu tiên để `HttpClient` hoặc thư viện HTTP có TLS chuẩn thực hiện xác minh certificate và hostname. Không tắt kiểm tra tên host, không dùng `TrustManager` “tin tất cả” để chữa lỗi. Với `SSLSocket` tự tạo, **không nên mặc định rằng mọi xác minh tên endpoint đều tự được bật**: cần cấu hình endpoint identification phù hợp, ví dụ `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` khi giao thức mục tiêu đúng là HTTPS.

Đoạn sử dụng thư viện HTTPS cấp cao (cần mạng; là đoạn minh họa, không có stdout cố định):

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/")).GET().build();
HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());
System.out.println(response.statusCode());
```

Các dòng trên cần đặt trong method có xử lý exception hoặc `throws Exception`. **JSSE không “là PKI”**: TLS là giao thức truyền thông, còn PKI là cơ sở để xác lập tin cậy cho khóa công khai/chứng thư dùng trong nhiều giao thức.

## 5. JAAS: xác thực Subject, không thay thế TLS hay mã hóa

JAAS dùng kiến trúc xác thực có thể cấu hình. Một ứng dụng gọi `LoginContext` theo tên cấu hình; cấu hình xác định các `LoginModule`; module có thể lấy thông tin qua `CallbackHandler`, xác thực bằng cơ chế thực tế (ví dụ Kerberos), rồi gắn các `Principal`/credential vào một `Subject` khi thành công.

```text
Ứng dụng → LoginContext("MyApp")
         → Configuration → các LoginModule
         → CallbackHandler (nếu cần nhập/chứng thực thông tin)
         → login thành công → Subject { Principal, credentials }
         → logic nghiệp vụ quyết định quyền truy cập
```

Đoạn API ở mức khái niệm:

```java
LoginContext context = new LoginContext("MyApp", handler);
context.login();
Subject authenticated = context.getSubject();
// Dùng principal/credential theo chính sách ứng dụng.
context.logout();
```

Đây **không phải chương trình chạy độc lập**: cần cấu hình login và `handler` phù hợp, cùng nhập `javax.security.auth.Subject` và `javax.security.auth.login.LoginContext`. Khi tự triển khai `LoginModule`, cần hiểu vòng đời `initialize`, `login`, `commit`, `abort` và `logout`; đừng tự tạo thành công giả chỉ vì có `Principal`.

Điều cần phân biệt:

- **TLS server authentication**: phía client biết kênh đang kết nối đến server nào theo certificate/hostname; đây là việc của JSSE/PKI.
- **JAAS authentication**: hệ thống xác thực người dùng hoặc một thực thể theo module đăng nhập; `Subject` biểu diễn thực thể đã xác thực.
- **Authorization**: ứng dụng quyết định principal đó được phép làm gì. JAAS cung cấp mô hình danh tính/credential để hỗ trợ quyết định này, nhưng không tự sinh toàn bộ chính sách phân quyền API, role nghiệp vụ, OAuth2/OIDC hay JWT.
- **Kerberos/JGSS**: có thể liên quan JAAS trong ứng dụng tích hợp Kerberos; không phải cứ dùng JSSE thì cần JAAS.

Trên JDK hiện đại, tránh hiểu “authorization của JAAS” là phải dựa vào SecurityManager cũ. Các ứng dụng nên xác định cơ chế phân quyền thực tế của framework và hệ thống đang dùng.

## 6. PKI/X.509: từ public key đến danh tính được tin cậy

**Cặp khóa bất đối xứng** gồm public key có thể chia sẻ và private key phải giữ bí mật. Một **chứng thư X.509** gắn public key với subject, issuer, serial, thời hạn hiệu lực, chữ ký của bên cấp và các extension. Chứng thư **không chứa private key** của subject.

Mô hình chuỗi thường gặp:

```text
Root CA (trust anchor đã được cấu hình tin cậy)
    ↓ ký/ủy quyền
Intermediate CA
    ↓ ký
Server leaf certificate (SAN: api.example.com)
    + private key tương ứng (chỉ server giữ)
```

Client không chỉ kiểm “certificate có chữ ký hợp lệ”; nó cần một đường chứng thực có thể kiểm tra đến **trust anchor được chấp nhận**. Trong PKIX, còn cần xét ràng buộc cơ bản của CA, key usage/extended key usage, hiệu lực thời gian, chính sách thuật toán, và kiểm tra thu hồi (CRL/OCSP) theo cấu hình. **Kiểm tra hostname là yêu cầu nhận diện endpoint của TLS/HTTPS, không được suy ra chỉ từ việc path validation thành công.**

Các API liên quan:

- `CertificateFactory.getInstance("X.509")`: đọc/biến đổi chứng thư và chuỗi từ dữ liệu mã hóa.
- `X509Certificate`: xem subject, issuer, SAN, validity, extension và public key.
- `CertPathBuilder.getInstance("PKIX")`: tìm đường chứng thực từ leaf theo dữ liệu/chính sách đầu vào.
- `CertPathValidator.getInstance("PKIX")`: kiểm đường chứng thực dựa trên `PKIXParameters` và `TrustAnchor`.
- `CertStore`: nguồn ứng viên certificate/CRL, không tự động là danh sách root được tin cậy.
- `PKIXRevocationChecker`: cấu hình kiểm tra thu hồi khi cần cơ chế phù hợp.

Những phân biệt hay sai:

| Khái niệm | Ý nghĩa thực tế |
| --- | --- |
| **CSR** – Certificate Signing Request | Yêu cầu cấp certificate; thường chứa public key và thông tin nhận diện, được ký bằng private key tương ứng; **CSR chưa phải chứng thư được CA tin cậy cấp** |
| **Self-signed certificate** | Tự ký bằng private key tương ứng; phù hợp thử nghiệm/CA riêng có kiểm soát, không tự nhiên được client bên ngoài tin |
| **Root CA/trust anchor** | Điểm tin cậy do người quản trị, hệ điều hành hoặc runtime chọn; có ý nghĩa vì được **cấu hình tin**, không vì xuất hiện trong chuỗi |
| **SAN** – Subject Alternative Name | Chứa danh tính DNS/IP dùng để đối chiếu endpoint hiện đại; đặt `CN=localhost` riêng thường không đủ |
| **Certificate chain** | Các chứng thư hỗ trợ chứng minh đường cấp phát; thiếu intermediate hoặc sai mục đích sử dụng có thể gây lỗi |
| **PEM, DER, PKCS#12** | Định dạng/bao gói dữ liệu; PEM thường là base64 có header, DER là nhị phân ASN.1, PKCS#12 là container có thể chứa key/certificate |

Đừng nhập certificate nhận được từ một server lạ vào truststore chỉ để hết lỗi. Làm vậy thay đổi trust anchor và có thể bỏ qua vấn đề thật: sai hostname, thiếu intermediate, chứng thư hết hạn hoặc CA không được tổ chức chấp thuận.

## 7. KeyStore, truststore và bộ công cụ JDK

`KeyStore` là API lưu/truy cập entry theo **alias**. Trong ứng dụng Java thường gặp:

- **Keystore danh tính (identity store)**: entry có **private key + certificate chain** của ứng dụng. JSSE `KeyManager` có thể đọc để chọn danh tính trình bày cho server/client.
- **Truststore**: chứa certificate được chọn làm điểm tin cậy; `TrustManager` dùng khi xác minh peer. Hai loại có thể cùng cấu trúc `KeyStore`, nhưng mục đích bảo mật khác nhau.
- **PKCS12 (`.p12`/`.pfx`)**: định dạng keystore mặc định điển hình từ JDK 9, dùng phổ biến để trao đổi key/certificate. `JKS` là định dạng Java cũ; `PKCS11` có thể trỏ tới token/HSM. Phần mở rộng tệp không tự bảo đảm dữ liệu bên trong đã được bảo vệ đúng.
- **`cacerts`**: kho CA được JDK cung cấp để xây dựng trust mặc định (các hệ thống/nhà cung cấp JVM có thể cấu hình khác). Thay đổi `cacerts` trên máy chung có ảnh hưởng rộng; ưu tiên truststore ứng dụng khi cần thiết.

### Bài thực hành local: tạo danh tính TLS tự ký và kho tin cậy riêng

Các lệnh dưới đây là **lệnh đơn dòng**, chạy trong thư mục thử nghiệm trên JDK có `keytool`. Chúng sẽ hỏi mật khẩu qua terminal; không đưa mật khẩu thật vào tham số dòng lệnh hay repository.

**Bước 1 – tạo cặp khóa RSA và certificate tự ký cho localhost:**

```shell
keytool -genkeypair -alias local-server -keyalg RSA -keysize 3072 -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 30 -storetype PKCS12 -keystore server.p12
```

`server.p12` có private key và certificate gắn alias `local-server`. `-ext SAN=...` giúp mô hình hóa danh tính localhost đúng cho thử nghiệm TLS.

**Bước 2 – kiểm entry và xuất chỉ phần certificate công khai:**

```shell
keytool -list -v -keystore server.p12
keytool -exportcert -rfc -alias local-server -keystore server.p12 -file server.crt
keytool -printcert -v -file server.crt
```

`-exportcert` không xuất private key. Kiểm SAN, issuer = subject trong trường hợp tự ký, hiệu lực và fingerprint. Fingerprint chỉ có ý nghĩa khi được đối chiếu qua kênh tin cậy.

**Bước 3 – tạo truststore chỉ tin certificate local đó:**

```shell
keytool -importcert -alias local-server -file server.crt -keystore client-trust.p12 -storetype PKCS12
keytool -list -v -keystore client-trust.p12
```

Khi công cụ hỏi có tin certificate không, **chỉ xác nhận trong thí nghiệm bạn vừa tự tạo/đối chiếu fingerprint**. `client-trust.p12` chứa chứng thư được tin, không có private key của server. Bài này minh họa một trust anchor local; production nên dùng CA được tổ chức chấp thuận và quản trị quy trình cấp phát, gia hạn, thu hồi.

**Bước 4 – hình dung quy trình CA thật:** `keytool -certreq -alias local-server -keystore server.p12 -file server.csr` tạo CSR cho cặp khóa đang có. CA kiểm soát danh tính và cấp chứng thư; sau đó cần nhập chuỗi CA/certificate reply vào đúng entry có private key. Không nhầm việc tạo CSR với việc hệ thống đã được tin cậy.

**Các công cụ đáng nhớ khác:**

| Công cụ/lệnh | Khi dùng | Giới hạn cần nhớ |
| --- | --- | --- |
| `keytool -list -cacerts` | Xem kho CA mặc định của JDK đang chạy | Danh sách phụ thuộc distribution/cấu hình; không nói trước chính xác mọi JVM |
| `keytool -importkeystore ...` | Chuyển/copy entry giữa keystore | Cần kiểm alias, entry type, mật khẩu, certificate chain |
| `jarsigner -keystore signing.p12 -signedjar app-signed.jar app.jar signing-alias` | Ký **JAR** bằng private key thuộc alias ký | Cần có `app.jar` và keystore có private key; không phải thao tác cấp certificate TLS |
| `jarsigner -verify -verbose -certs app-signed.jar` | Xem chữ ký và nội dung đã được bảo vệ của JAR | JAR có chữ ký hợp lệ **không mặc nhiên** đồng nghĩa signer đã được hệ thống tin; đọc warning/chain |
| `jar tf app.jar` | Liệt kê nội dung JAR khi kiểm artifact | Không thay thế xác minh chữ ký |
| `java -Djavax.net.debug=ssl,handshake ...` | Quan sát bắt tay TLS khi chạy ứng dụng | Có thể in thông tin nhạy cảm; chỉ dùng lúc debug có kiểm soát |
| `java -Djava.security.debug=certpath ...` | Khảo sát quá trình kiểm chứng chứng thư PKIX | Log lớn; cần quản lý dữ liệu và quyền truy cập |

`jarsigner` là **ký mã phân phối (code signing)**; `keytool` chủ yếu quản lý material khóa/certificate; cả hai dùng các thành phần JCA/PKI. Chúng không thay thế TLS cho dữ liệu trao đổi qua mạng.

### Cấu hình bảo mật runtime cần nhận diện

JDK có file cấu hình bảo mật thường tại `<java-home>/conf/security/java.security`. Các property như `security.provider.N` xác định thứ tự provider; `jdk.tls.disabledAlgorithms` giới hạn thuật toán/protocol cho TLS; `jdk.certpath.disabledAlgorithms` ràng buộc kiểm đường chứng thư; `jdk.jar.disabledAlgorithms` liên quan chữ ký JAR. Cách nạp, override và giá trị mặc định phụ thuộc phiên bản/distribution. **Ưu tiên nâng JDK, sửa certificate/cấu hình đúng nguyên nhân; không nới lỏng các danh sách thuật toán yếu để xử lý nhanh lỗi.**

Một số thuộc tính hệ thống trong triển khai JSSE có thể chỉ định keystore/truststore ứng dụng, ví dụ `javax.net.ssl.keyStore`, `javax.net.ssl.trustStore` và các tùy chọn type/password tương ứng. Cần phân biệt **system property** này với **security property** trong `java.security`; không phải mọi API/framework đều dùng default `SSLContext` hoặc các property mặc định.

## 8. Java 17+: chọn engine theo provider và nhận diện ranh giới API

Ví dụ này **không mã hóa hay ký dữ liệu lần nữa**. Thay vào đó, nó kiểm chứng cách các engine phân giải nhà cung cấp thực tế và nhận diện những package tách biệt của JSSE/JAAS. Đây là câu hỏi riêng của **bản đồ JDK**, khác với ví dụ primitive ở bài so sánh mã hóa, hash, MAC và chữ ký.

Tạo file `SecurityApiMapDemo.java`:

```java
import java.security.MessageDigest;
import java.security.Provider;
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.security.auth.login.LoginContext;

public class SecurityApiMapDemo {
    public static void main(String[] args) throws Exception {
        MessageDigest digest =
                MessageDigest.getInstance("SHA-256");
        Cipher aesGcm = Cipher.getInstance("AES/GCM/NoPadding");

        Provider digestProvider = digest.getProvider();
        Provider cipherProvider = aesGcm.getProvider();

        System.out.println("Digest provider resolved: "
                + (digestProvider != null));
        System.out.println("Cipher provider resolved: "
                + (cipherProvider != null));
        System.out.println("JSSE package: "
                + SSLContext.class.getPackageName());
        System.out.println("JAAS package: "
                + LoginContext.class.getPackageName());
    }
}
```

Biên dịch/chạy trên JDK 17+ có provider SHA-256 và AES-GCM thông dụng:

```bash
javac --release 17 SecurityApiMapDemo.java
java SecurityApiMapDemo
```

Stdout:

```text
Digest provider resolved: true
Cipher provider resolved: true
JSSE package: javax.net.ssl
JAAS package: javax.security.auth.login
```

Dòng đầu/cuối chỉ cho biết engine đã có provider và lớp thuộc package tương ứng, **không** nói TLS đã xác minh certificate, JAAS đã login, hay phép mã hóa đã được thực hiện đúng. Muốn biết provider cụ thể, có thể in `digestProvider.getName()` và `cipherProvider.getName()`, nhưng tên phụ thuộc JDK/distribution/cấu hình. `Cipher.getInstance(...)` cũng mới xác nhận có transformation; dùng đúng khóa, nonce/AAD và xử lý tag vẫn là trách nhiệm của ứng dụng.

Qua các ví dụ và công cụ của chương, luôn tách: **engine Java**, **provider triển khai**, **cấu hình tin cậy PKI** và **quyền nghiệp vụ**.

## 9. Chọn đúng lớp trong tình huống thực tế

**Tình huống A – file cấu hình nội bộ cần giữ bí mật và phát hiện sửa đổi:** mã hóa bằng `Cipher` với AEAD (JCE/JCA); khóa cần có nguồn lưu an toàn, rotation, kiểm quyền và định dạng dữ liệu bao gồm nonce/tag. TLS không bảo vệ nội dung sau khi ghi xuống đĩa.

**Tình huống B – gọi API HTTPS:** dùng `HttpClient` hoặc HTTP client có TLS chuẩn (JSSE); xác minh certificate chain theo PKI và hostname; khi cần mTLS, cấu hình client private key/certificate cùng trust của server. Không dùng JAAS để “thay” việc xác minh certificate HTTPS.

**Tình huống C – tài liệu phải kiểm được tác giả ký:** `Signature` dùng private key ký và public key kiểm; nếu cần tin “ai là người ký”, phải phân phối public key đáng tin hoặc dùng PKI/chính sách certificate. `MessageDigest` đơn lẻ chưa đủ.

**Tình huống D – tích hợp đăng nhập Kerberos:** xem xét JAAS `LoginContext`/`LoginModule`, `Subject`, và tích hợp Kerberos/GSS liên quan; quyền vào endpoint vẫn phụ thuộc policy ứng dụng.

**Tình huống E – ký JAR nội bộ:** quản lý khóa ký bằng `keytool`/hệ thống quản lý khóa, dùng `jarsigner`, kiểm signature và chuỗi tin cậy. Ký JAR không tự mã hóa bytecode và không mặc nhiên bảo đảm tải/chạy JAR là an toàn.

## 10. Chẩn đoán lỗi và sai lầm phổ biến

| Triệu chứng | Nơi kiểm tra trước | Điều cần tránh |
| --- | --- | --- |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | Tên engine/thuật toán/transformation, provider được đăng ký, bản JDK | Đổi thuật toán bảo mật tùy tiện để “chạy được” |
| `AEADBadTagException` | Key, nonce, AAD, ciphertext/tag; có bị sửa, lỗi encoding/truyền tải hay không | Bỏ qua tag hoặc giải mã trả plaintext khi auth thất bại |
| `SSLHandshakeException` với `PKIX path building failed` | Truststore client, CA root/intermediate, chuỗi server gửi, thời hạn và chính sách PKIX | Tắt trust validation hoặc nhập bừa leaf certificate |
| Lỗi hostname/SAN | DNS/IP thực sự truy cập so với SAN certificate | Tắt hostname verification |
| `UnrecoverableKeyException` / không chọn được alias | Password, key entry, entry type, alias và chain | Log private key hoặc mật khẩu để debug |
| TLS không thương lượng được version/cipher suite | Chính sách TLS của hai phía, `jdk.tls.disabledAlgorithms`, provider/JDK | Bật lại SSL/TLS yếu trong production |
| JAAS `LoginException` | Tên app trong configuration, LoginModule, CallbackHandler, thông tin định danh và dependency xác thực | Xem thành công TLS như bằng chứng `login()` đã chạy |
| `jarsigner -verify` có warning | Certificate người ký, trust, thời gian hiệu lực, timestamp, thuật toán bị vô hiệu | Đồng nhất “có chữ ký” với “nhà phát hành đáng tin” |

Luồng debug hợp lý: **xác định tầng lỗi → kiểm đúng API/cấu hình → quan sát log có giới hạn → sửa nguyên nhân → chạy lại kiểm chứng**. Hạn chế bật debug TLS/CertPath ở production trong thời gian dài vì log có thể lộ metadata, tăng kích thước và làm khó tìm tín hiệu quan trọng.

## 11. Checklist ghi nhớ và câu hỏi tự kiểm tra

- **Cần hash?** `MessageDigest`. **Cần MAC?** `Mac`. **Cần mã hóa?** `Cipher`/AEAD. **Cần ký?** `Signature`. Tất cả sống trong hệ JCA (bao gồm phần lịch sử gọi là JCE).
- **Cần kênh mạng TLS?** JSSE/HTTP client chuẩn. **Cần đánh giá certificate/chuỗi?** PKI/X.509 và TrustManager/CertPath. **Cần đăng nhập có module cắm thêm?** JAAS.
- **Cần tạo/xem khóa, certificate, CSR?** `keytool`. **Cần ký/kiểm JAR?** `jarsigner`. **Cần debug handshake?** `javax.net.debug`; cần debug đường chứng thư thì xét `java.security.debug=certpath`.
- **Cần triển khai thật?** Dùng cấu hình trust/identity rõ ràng, thuật toán hiện đại, khóa lưu an toàn, xác thực hostname, rotation và quyền nghiệp vụ; không tin mọi certificate và không dùng các ví dụ local tự ký làm chính sách production.

Tự trả lời: (1) Vì sao `AES/GCM` và TLS đều có mã hóa nhưng không thay thế nhau? (2) Tại sao một certificate hợp lệ về chữ ký vẫn có thể bị HTTPS từ chối? (3) Điểm khác nhau giữa HMAC, chữ ký số và chỉ SHA-256 là gì? (4) Nếu server yêu cầu mTLS thì client cần thêm vật liệu gì? (5) Vì sao JAAS `Subject` không tự cấp quyền truy cập mọi API?

**Đáp án định hướng:** (1) AEAD bảo vệ payload theo khóa/nonce của ứng dụng; TLS bảo vệ phiên truyền mạng cùng xác thực peer. (2) Có thể sai trust anchor, thời hạn, SAN/hostname, key usage hoặc chính sách. (3) Hash không khóa; HMAC dùng secret chung; chữ ký dùng private/public key. (4) Client cần private key và certificate chain phù hợp để trình bày; vẫn phải tin server. (5) Ứng dụng phải thực thi authorization theo policy nghiệp vụ riêng.

## Tài liệu chính thống để đọc sâu

- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html): provider/engine, khóa và các phép mật mã; giải thích vì sao JCE thuộc JCA hiện đại.
- [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, `SSLContext`, key/trust manager, endpoint identification.
- [JAAS Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-authentication-authorization-service-jaas-reference-guide.html): `LoginContext`, `LoginModule`, `Subject`, cấu hình xác thực.
- [Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/21/security/java-pki-programmers-guide.html): `CertPathBuilder`, `CertPathValidator`, `TrustAnchor`, kiểm chứng PKIX.
- [keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html) và [jarsigner](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html): cú pháp công cụ, chữ ký và cảnh báo.