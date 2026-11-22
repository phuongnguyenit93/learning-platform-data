# TrustManager và kiểm tra chuỗi chứng thư X.509 trong Java

**Chủ đề:** Chứng thư gốc — Java 10 và các bản Java hiện đại.

Khi một ứng dụng Java kết nối HTTPS/TLS đến máy chủ, **việc nhận được chứng thư X.509 không có nghĩa máy chủ được tin cậy**. JVM phải xác minh chuỗi chứng thư từ chứng thư đầu cuối (*leaf/end-entity*) qua CA trung gian (*intermediate CA*) đến một **điểm neo tin cậy (*trust anchor*)** do ứng dụng hoặc môi trường chủ động chấp nhận. Trong JSSE (Java Secure Socket Extension), `TrustManager`, nhất là `X509TrustManager` và `X509ExtendedTrustManager`, thực hiện phần kiểm tra tin cậy của bên kết nối. Cơ chế **PKIX** (Public-Key Infrastructure X.509, RFC 5280) là nền tảng phổ biến để xây dựng và xác minh chuỗi.

**Ba mệnh đề cần phân biệt:**

1. **Chữ ký đúng** (`signature verification`): một chứng thư được ký bằng khóa tương ứng với issuer được khai báo. Điều này *chưa* chứng minh issuer ấy được ứng dụng tin cậy.
2. **Chuỗi PKIX hợp lệ và có trust anchor được chấp nhận**: từng bước của đường đi được kiểm tra, quy tắc CA, thời hạn, thuật toán, các extension quan trọng và chính sách thích hợp được áp dụng. Việc có chứng thư root tự ký không tự biến nó thành một CA được tin cậy.
3. **Đúng danh tính máy chủ** (`hostname/endpoint verification`): chứng thư đầu cuối phải phù hợp với tên DNS/IP của dịch vụ mà client thực sự muốn kết nối. Một chứng thư hợp lệ cho `localhost` không tự hợp lệ khi client truy cập `127.0.0.1`.

**Trọng tâm Java 10:** JEP 319 (*Root Certificates*) đã mở nguồn tập chứng thư gốc trong `cacerts` cho OpenJDK từ JDK 10. Các API `TrustManagerFactory`, `X509TrustManager`, `CertPathValidator` và PKIX đã tồn tại từ trước Java 10 và **vẫn được dùng hiện nay**. Bài này không hướng dẫn các thuật toán hoặc giao thức TLS đã bị vô hiệu theo mặc định; ví dụ dùng RSA/SHA-256, TLS theo cấu hình runtime hiện đại, và không bao giờ cài “trust-all manager”.

Bài gồm **bốn chương trình Java hoàn chỉnh**: đọc cấu trúc chứng thư; kiểm tra và xây dựng PKIX certificate path; sử dụng `TrustManagerFactory` để chấp nhận/từ chối chuỗi; chạy TLS loopback để xác nhận cả **trust anchor** lẫn **hostname**. Các ví dụ đã biên dịch với `javac --release 10` và được kiểm thử trên **OpenJDK 21**, dùng một CA gốc, một CA trung gian và một server certificate **tự tạo cho môi trường thử nghiệm cục bộ**.

## 1. Mô hình gốc → trung gian → máy chủ

~~~text
             ROOT CA: Demo Root CA
             self-issued / self-signed
             Được client CẤU HÌNH TIN CẬY
                    (TrustAnchor)
                         |
                         | root private key ký
                         v
          INTERMEDIATE CA: Demo Intermediate CA
              BasicConstraints: CA=true
              KeyUsage: keyCertSign
                         |
                         | intermediate private key ký
                         v
             LEAF: CN=localhost
             SAN: DNS:localhost
             BasicConstraints: CA=false
             ExtendedKeyUsage: serverAuth
                         |
                         v
             TLS server trên localhost

     Client đã tin Root CA? -- Không --> từ chối
                |
               Có
                v
     Chuỗi / chữ ký / policy hợp lệ? -- Không --> từ chối
                |
               Có
                v
     Hostname client kết nối khớp SAN? -- Không --> từ chối
                |
               Có
                v
           TLS authentication thành công
~~~

Trong TLS, server thường gửi **leaf** và **intermediate** (có thể thiếu intermediate, khi đó việc xây đường dẫn tùy khả năng tìm kiếm của client). **Không cần gửi root tự ký** vì phía client phải có hoặc phải tin root đó **từ trước**, qua truststore hoặc cấu hình. Việc một server tự gửi root không tạo ra lòng tin: một kẻ tấn công cũng có thể tự tạo CA và gửi nó.

### Vai trò của từng chứng thư

| Vai trò | Chức năng | Nơi thường được lưu |
| --- | --- | --- |
| **Root CA / trust anchor** | Điểm bắt đầu của chính sách tin cậy; xác minh khóa CA ở phía trên | Truststore của client hoặc cấu hình PKIX |
| **Intermediate CA** | CA được root hoặc CA cấp trên ký, dùng ký chứng thư con | Server certificate chain, kho intermediate hoặc CertStore |
| **Leaf/server** | Gắn public key với danh tính dịch vụ, thường có SAN và EKU serverAuth | Server key store và chuỗi server gửi trong TLS |
| **Private key của server** | Chứng minh server sở hữu khóa bí mật ứng với leaf certificate | KeyStore/secret manager phía server, **không đưa vào truststore client** |
| **Private key của Root CA** | Quyền phát hành/ủy quyền chứng thư CA | Giữ bảo mật nghiêm ngặt; **không phân phối cho client** |

**Một Root CA có thể được đại diện dưới dạng `TrustAnchor` bằng chứng thư hoặc tên CA + public key.** Không phải root nào cũng nằm trong một danh sách Java `CertPath`; theo quy tắc PKIX, certificate đại diện trust anchor **không thuộc `CertPath` đầu vào cần xác minh**.

## 2. Chứng thư tự ký không đồng nghĩa được tin cậy

**Self-signed** là mô tả cách chứng thư được ký: issuer và subject có thể trùng và chữ ký xác minh bằng public key có trong chính chứng thư đó. Đây là thuộc tính mật mã, không phải quyết định quản trị rằng CA ấy đáng tin.

~~~text
Một CA tự ký bất kỳ:
  CN=Unknown Root
  Signature tự kiểm chứng thành công
  ...
  Client không có Root này trong danh sách TrustAnchor
            =>
  Không xây được đường đến một gốc được chấp nhận
            =>
  Kết nối chuẩn phải bị từ chối
~~~

**Trust là một quyết định cấu hình.** Trong Java, quyết định ấy thường nằm ở một `KeyStore` dùng làm **truststore**, hoặc trong một tập đối tượng `TrustAnchor` truyền cho `PKIXParameters`.

Một chứng thư trung gian được root ký **không tự là trust anchor** trừ khi chính sách ứng dụng chủ động đưa nó vào tập tin cậy. Nếu thêm intermediate làm trust anchor, đó là quyết định tin cậy trực tiếp CA trung gian và có thể làm thay đổi phạm vi ủy quyền. Không nhập bừa các intermediate lấy từ Internet vào truststore chỉ để “hết SSL error”.

## 3. `TrustManager`, `KeyManager` và `SSLContext`

Ba khái niệm trong JSSE giải quyết những vấn đề khác nhau:

| Thành phần | Nhiệm vụ | Dữ liệu thường dùng |
| --- | --- | --- |
| `TrustManager` | **Xác định có tin peer hay không** | Trust anchors, CA certificates, policy |
| `X509TrustManager` | Kiểm tra chứng thư X.509 cho peer client/server | Certificate chain, authType |
| `X509ExtendedTrustManager` | Kiểm tra X.509 **gắn với một Socket/SSLEngine**, có thể xử lý SSLParameters/endpoint identification | Chain, TLS session/context, algorithm constraints, host |
| `TrustManagerFactory` | Tạo trust managers do provider triển khai | Truststore `KeyStore` hoặc CertPath parameters |
| `KeyManager` | **Chọn danh tính và khóa riêng của chính bên mình** | Private key, leaf và chuỗi certificate của bên mình |
| `KeyManagerFactory` | Tạo key managers từ key material | Private-key keystore |
| `SSLContext` | Tập hợp cấu hình TLS, key/trust managers, SecureRandom, session | `init(keyManagers, trustManagers, random)` |
| `CertPathBuilder` | Tìm/ghép một certificate path đến trust anchor | Target selector, intermediate certificates, anchors |
| `CertPathValidator` | Xác minh **certificate path đã được cung cấp** | Ordered `CertPath` và `PKIXParameters` |

**Không hoán đổi truststore với keystore:** một client tin root qua truststore **không cần biết private key của root**. Server sử dụng private key riêng từ keystore để chứng minh danh tính; client xác minh bằng public-key certificates và trust anchor. Trong mTLS, cả hai bên có thể cần key manager và trust manager vì cả client lẫn server đều trình chứng thư.

### API `X509TrustManager`

~~~java
void checkServerTrusted(X509Certificate[] chain, String authType)
        throws CertificateException;

void checkClientTrusted(X509Certificate[] chain, String authType)
        throws CertificateException;

X509Certificate[] getAcceptedIssuers();
~~~

Đây là **chữ ký các method**, không phải file Java độc lập. `checkServerTrusted` được gọi khi phía **client** cần xác minh chứng thư server, còn `checkClientTrusted` khi phía **server** xác minh chứng thư client trong mTLS. **Nếu không tin được, implementation ném `CertificateException`.** Không phải trả `false`.

`authType` đại diện kiểu xác thực thực tế. **Trong TLS chạy thật để JSSE/provider quyết định giá trị phù hợp; không hard-code `"RSA"` trong một custom trust manager production rồi nghĩ rằng phù hợp mọi TLS handshake.** Demo dùng `"RSA"` vì chứng thư thử nghiệm sử dụng RSA và test API trực tiếp.

### Vì sao nên dùng `X509ExtendedTrustManager` nếu cần mở rộng?

`X509TrustManager` chỉ nhận chain và authType, **không nhận socket/TLS engine**. Trong khi đó `X509ExtendedTrustManager` cung cấp các overload có `Socket` hoặc `SSLEngine`, giúp kiểm tra ràng buộc của connection và **endpoint identification** khi SSLParameters được cấu hình thích hợp. Oracle JSSE hiện hành khuyến nghị khả năng này hơn việc tự viết lớp chỉ triển khai interface cũ, đặc biệt đối với TLS hiện đại.

**Không bắt buộc tự subclass `X509ExtendedTrustManager`.** Đa số ứng dụng nên dùng **trust manager do `TrustManagerFactory` tạo** thay vì tự viết chính sách xác minh mật mã.

## 4. Các bước PKIX certificate path validation

Với đường đi `leaf → intermediate → trust anchor`, validator phải xử lý nhiều điều kiện:

1. **Liên kết issuer/subject và chữ ký:** issuer của leaf tương ứng intermediate; chữ ký leaf có thể kiểm bằng public key của intermediate; intermediate tương ứng root hoặc CA cấp trên.
2. **Một trust anchor chấp nhận được:** đường dẫn phải kết thúc tại CA/public key đã nằm trong tập tin cậy của ứng dụng. Không tự thêm root từ peer vào tập trust.
3. **Thời hạn:** `notBefore`/`notAfter` của các certificate cần kiểm tra tại thời điểm validation; có thể đặt ngày đánh giá tường minh trong PKIXParameters.
4. **Basic Constraints:** certificate đóng vai trò CA phải được phép ký cấp dưới; leaf thường có `CA=false`.
5. **Key Usage:** CA cần quyền `keyCertSign`; leaf phải có key usage hợp với mục đích TLS và thuật toán được dùng.
6. **Extended Key Usage (EKU):** leaf cho TLS server thường cần `id-kp-serverAuth` nếu extension hiện diện.
7. **Path length/name constraints/certificate policies:** giới hạn số cấp CA trung gian, không gian tên và chính sách phải được áp dụng khi liên quan.
8. **Critical extensions:** extension `critical` không được hỗ trợ/hiểu đúng sẽ làm path validation thất bại.
9. **Thuật toán/key strength:** cấu hình security policy có thể vô hiệu thuật toán yếu hoặc khóa ngắn; ví dụ `jdk.certpath.disabledAlgorithms` và các hạn chế TLS.
10. **Revocation policy:** CRL/OCSP/PKIXRevocationChecker chỉ hoạt động theo cấu hình và dữ liệu có được; không hứa mọi đường đi luôn được tra cứu revocation.
11. **Hostname verification:** kiểm tra **tên dịch vụ dự kiến** với SAN của leaf, thường là bước gắn với HTTPS/endpoint, **không thể suy ra chỉ từ kết quả `CertPathValidator.validate`**.

**Điểm dễ sai:** gọi trực tiếp `leaf.verify(intermediate.getPublicKey())` chỉ xác minh **một chữ ký**. Nó không tự thực hiện đầy đủ BasicConstraints, EKU, name constraints, policy, revocation hoặc hostname verification.

### Path validation và path building

- **`CertPathValidator`**: đã có danh sách certificate **theo đúng thứ tự** rồi, dùng các `PKIXParameters` để kiểm tra.
- **`CertPathBuilder`**: biết certificate mục tiêu và các nguồn candidate certificates, tự **tìm một đường hợp lệ** kết thúc tại trust anchor.
- **`CertPath`** cho X.509 thường sắp **leaf trước, intermediate sau**, **không thêm root trust anchor vào danh sách**.
- **JSSE `X509TrustManager.checkServerTrusted`** có thể sử dụng khả năng xây dựng/xác minh đường đến gốc tin cậy theo implementation và cert stores được cấu hình; ứng dụng không nên phỏng đoán rằng peer phải gửi mọi chứng thư hay JVM sẽ tự tải mọi intermediate từ Internet.

### Kết luận “PKIX valid” chưa đủ cho HTTPS

Một certificate path có thể hợp lệ về chữ ký, thời hạn và policy nhưng chỉ chứa **SAN DNS:localhost**. Nếu client kết nối đến **127.0.0.1**, IP đó **không khớp SAN**, nên **TLS client có endpoint verification HTTPS bật phải từ chối**. Đây không phải lỗi chain-of-trust mà là lỗi danh tính máy chủ.

## 5. Truststore mặc định và `cacerts` trong Java

JSSE thường tìm trust material qua cấu hình của runtime:

1. Nếu khai báo `javax.net.ssl.trustStore`, SunJSSE sẽ dùng truststore được trỏ đến (cùng type/password/provider nếu có). **Nếu đường dẫn chỉ định không tồn tại, trust manager có thể hoạt động với truststore trống, làm mọi chứng thư công khai thất bại**, chứ không nhất thiết tự fallback về cacerts.
2. Nếu không chỉ định truststore, SunJSSE trước hết tìm truststore JSSE-specific `jssecacerts` (nếu có), sau đó `cacerts` đi kèm JDK.
3. Nếu không có nguồn trust material, trust manager mặc định có thể không có CA nào để tin cậy.
4. Các truststores cụ thể và chính sách trust có thể khác theo JDK distribution/provider, Java image, hệ điều hành hoặc cấu hình triển khai; **không assume truststore của host bằng truststore trong Docker image**.

**JEP 319 (Java 10):** OpenJDK bổ sung tập chứng thư root CA của chương trình Java SE Root CA vào `cacerts` nhằm tạo khả năng xác minh TLS thực tế trong các bản OpenJDK. **Đây là nguồn trust anchors do nhà phân phối bảo trì**, không phải “mọi root trên thế giới đều được tin cậy” hoặc “mọi Java 10, 17, 21, 25 chắc chắn có cùng một danh sách root”. Root có thể được thêm/bỏ/đánh dấu không tin cậy theo security policy và update release.

### Cách xem truststore, không sửa tùy tiện

~~~bash
keytool -list -cacerts
~~~

Lệnh `keytool -list -cacerts` hỏi passphrase khi phù hợp; hiển thị certificate entries của JDK đang được sử dụng. Nếu cần xem thông tin một alias:

~~~bash
keytool -list -v -cacerts -alias <alias-thuc-te>
~~~

Trong lệnh này, thay token `<alias-thuc-te>` bằng **alias tồn tại** được liệt kê từ lệnh trước (đây là câu lệnh thao tác mang tham số, không phải output chương trình Java). **Không tự sửa file `cacerts` của JDK cài trên host** chỉ để thử nghiệm; dùng một truststore riêng và trong CI/CD đóng gói artifact rõ ràng.

**Cảnh báo:** `javax.net.ssl.trustStorePassword` truyền trên command line có thể bị lộ qua process listings/logs. Dùng secret management phù hợp thay vì công khai secret thật trong script. Mật khẩu `changeit` ở ví dụ bên dưới **chỉ dùng cho khóa test cục bộ**, không phải khuyến nghị bảo mật production.

## 6. Chuẩn bị một bộ chứng thư demo hoàn toàn cục bộ

Để các ví dụ có **input xác định, không phụ thuộc Internet hoặc một website bất kỳ**, dùng `keytool` từ JDK để phát hành:

- `root.p12`: private key của Demo Root CA (chỉ dành cho test).
- `root.pem`: public root CA certificate.
- `intermediate.p12`: private key + certificate chain của Demo Intermediate CA.
- `intermediate.pem`: intermediate certificate do root CA ký.
- `server.p12`: server private key + certificate chain, phục vụ TLS loopback.
- `server.pem`: server certificate do intermediate ký, với **DNS SAN:localhost**.
- `wrong-root.pem`: root CA không liên quan, dùng cho negative test.

**Chỉ chạy trong một thư mục thử nghiệm riêng và xóa các private keys sau khi học.** Không đưa `root.p12`, `intermediate.p12`, hay mật khẩu demo vào repository hoặc deployment image. Cấu hình sinh root CA ở đây chỉ phù hợp **bài thực hành**.

### Bước 1 — Root CA RSA/SHA-256

~~~bash
keytool -genkeypair -alias root -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Demo Root CA,O=Training,C=VN" -ext "bc:critical=ca:true,pathlen:1" -ext "ku:critical=keyCertSign,cRLSign" -validity 365 -storetype PKCS12 -keystore root.p12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -rfc -alias root -keystore root.p12 -storepass changeit -file root.pem
~~~

`basicConstraints CA=true` và `keyUsage keyCertSign` cho biết đây là CA certificate. `pathlen:1` giới hạn số CA trung gian tiếp theo theo cách diễn giải của PKIX. **Private key trong `root.p12` là vật liệu nhạy cảm**, không phải trust material nên phân phối sang client.

### Bước 2 — Tạo Intermediate CA và yêu cầu Root ký

~~~bash
keytool -genkeypair -alias intermediate -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Demo Intermediate CA,O=Training,C=VN" -validity 180 -storetype PKCS12 -keystore intermediate.p12 -storepass changeit -keypass changeit -noprompt

keytool -certreq -alias intermediate -keystore intermediate.p12 -storepass changeit -file intermediate.csr

keytool -gencert -alias root -keystore root.p12 -storepass changeit -infile intermediate.csr -outfile intermediate.pem -rfc -validity 120 -ext "bc:critical=ca:true,pathlen:0" -ext "ku:critical=keyCertSign,cRLSign"

keytool -importcert -alias root -file root.pem -keystore intermediate.p12 -storepass changeit -noprompt
keytool -importcert -alias intermediate -file intermediate.pem -keystore intermediate.p12 -storepass changeit -noprompt
~~~

`pathlen:0` của intermediate có nghĩa **không được tiếp tục phát hành một CA trung gian ở dưới**, nhưng vẫn có thể ký end-entity server certificate.

### Bước 3 — Phát hành server certificate với DNS SAN

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=localhost,O=Training,C=VN" -validity 90 -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -ext "san=dns:localhost" -noprompt

keytool -certreq -alias server -keystore server.p12 -storepass changeit -file server.csr -ext "san=dns:localhost"

keytool -gencert -alias intermediate -keystore intermediate.p12 -storepass changeit -infile server.csr -outfile server.pem -rfc -validity 60 -ext "bc:critical=ca:false" -ext "ku:critical=digitalSignature,keyEncipherment" -ext "eku=serverAuth" -ext "san=dns:localhost"

keytool -importcert -alias root -file root.pem -keystore server.p12 -storepass changeit -noprompt
keytool -importcert -alias intermediate -file intermediate.pem -keystore server.p12 -storepass changeit -noprompt
keytool -importcert -alias server -file server.pem -keystore server.p12 -storepass changeit -noprompt
~~~

Các lệnh `-gencert` và `-importcert` được thực nghiệm trên JDK 21 với chain trong `server.p12` dài **3 certificates**. Khi phát hành/kiểm thử bằng một JDK khác, xem output và bảo đảm `root.p12`/`intermediate.p12` chỉ ở môi trường CA offline/test. **Trong production, không cấp phát private root key trên cùng server đang phục vụ TLS**.

**Chú ý:** `server.pem` do `keytool -gencert -rfc` xuất có thể kèm nhiều PEM certificates. Trong các ví dụ bên dưới, `CertificateFactory.generateCertificate(InputStream)` đọc **certificate đầu tiên (leaf)**; file `intermediate.pem` tương tự được đọc intermediate đầu tiên. Trường hợp muốn đọc toàn bộ chain, dùng `generateCertificates(...)` hoặc giải mã theo đúng định dạng.

### Bước 4 — Root CA sai để thử negative case

~~~bash
keytool -genkeypair -alias wrongroot -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Unrelated Root CA,O=Training,C=VN" -ext "bc:critical=ca:true" -ext "ku:critical=keyCertSign,cRLSign" -validity 365 -storetype PKCS12 -keystore wrong-root.p12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -rfc -alias wrongroot -keystore wrong-root.p12 -storepass changeit -file wrong-root.pem
~~~

Dùng **một root riêng biệt không ký intermediate/server** để kiểm thử việc thiếu đường tin cậy. Không có endpoint bên ngoài nào được gọi trong cả quá trình phát hành.

### Kiểm tra certificate chain trong keystore demo

~~~bash
keytool -list -v -keystore server.p12 -storepass changeit -alias server
~~~

Trong môi trường kiểm thử, entry là `PrivateKeyEntry` với certificate chain length **3**. Không hard-code một chuỗi PEM fingerprint trong tài liệu: keytool tạo **keypair và serial khác nhau ở mỗi lần chạy**, nên thumbprint sẽ khác.

## 7. Chương trình Java 10 số 1 — Đọc và xem cấu trúc certificates

File **`ReadCertificatesDemo.java`**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;

public class ReadCertificatesDemo {
    static X509Certificate load(String file) throws Exception {
        try (InputStream in = Files.newInputStream(Paths.get(file))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);
        }
    }

    static boolean sanContainsDns(X509Certificate certificate, String expected)
            throws Exception {
        Collection<List<?>> sans = certificate.getSubjectAlternativeNames();
        if (sans == null) return false;
        for (List<?> san : sans) {
            if (Integer.valueOf(2).equals(san.get(0))
                    && expected.equals(san.get(1))) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        X509Certificate root = load("root.pem");
        X509Certificate intermediate = load("intermediate.pem");
        X509Certificate server = load("server.pem");

        root.checkValidity();
        intermediate.checkValidity();
        server.checkValidity();

        root.verify(root.getPublicKey());
        intermediate.verify(root.getPublicKey());
        server.verify(intermediate.getPublicKey());

        System.out.println("root-self-issued=" +
                root.getSubjectX500Principal()
                        .equals(root.getIssuerX500Principal()));
        System.out.println("intermediate-is-ca=" +
                (intermediate.getBasicConstraints() >= 0));
        System.out.println("server-is-end-entity=" +
                (server.getBasicConstraints() < 0));
        System.out.println("server-san-localhost=" +
                sanContainsDns(server, "localhost"));
        System.out.println("signature-links-verified=true");
    }
}
~~~

Chạy tại thư mục có các file PEM vừa tạo:

~~~bash
javac --release 10 ReadCertificatesDemo.java
java ReadCertificatesDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
root-self-issued=true
intermediate-is-ca=true
server-is-end-entity=true
server-san-localhost=true
signature-links-verified=true
~~~

Giải thích:

- `getBasicConstraints() >= 0` báo certificate đóng vai trò CA; `< 0` cho biết leaf không phải CA.
- SAN kiểu **2** là DNS name theo `X509Certificate.getSubjectAlternativeNames()`; `localhost` là SAN hợp lệ cho hostname `localhost`.
- `root.verify(root.getPublicKey())` xác minh chữ ký tự ký; điều đó **không tự tạo trust**.
- `intermediate.verify(root.getPublicKey())` và `server.verify(intermediate.getPublicKey())` kiểm đúng liên kết chữ ký trong bài test.
- **Chương trình này không thay thế PKIX validation hoặc hostname verification của TLS client**. Nó chưa xét đầy đủ policy, EKU, name constraints, trust anchor hoặc revocation.

## 8. Chương trình Java 10 số 2 — `CertPathValidator` và `CertPathBuilder`

Trong certificate path X.509 truyền cho PKIX, thứ tự là **leaf trước → intermediate sau**; root trust anchor được cung cấp **riêng** trong `PKIXParameters`. Đây là khác biệt rất quan trọng với việc “server gửi ba certificates thì phải thêm cả ba vào CertPath”.

File **`PkixChainDemo.java`**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.cert.CertPath;
import java.security.cert.CertPathBuilder;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertStore;
import java.security.cert.CertificateFactory;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXBuilderParameters;
import java.security.cert.PKIXCertPathBuilderResult;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.Set;

public class PkixChainDemo {
    static X509Certificate load(String file) throws Exception {
        try (InputStream in = Files.newInputStream(Paths.get(file))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);
        }
    }

    static boolean fails(CertPath path, PKIXParameters params)
            throws Exception {
        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return false;
        } catch (CertPathValidatorException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        X509Certificate root = load("root.pem");
        X509Certificate intermediate = load("intermediate.pem");
        X509Certificate server = load("server.pem");
        X509Certificate wrongRoot = load("wrong-root.pem");

        CertificateFactory certificates =
                CertificateFactory.getInstance("X.509");
        CertPath path = certificates.generateCertPath(
                Arrays.asList(server, intermediate));

        Set<TrustAnchor> trusted =
                Collections.singleton(new TrustAnchor(root, null));
        PKIXParameters params = new PKIXParameters(trusted);

        System.out.println("pkixparameters-revocation-default=" +
                params.isRevocationEnabled());

        // ONLY FOR OFFLINE REPRODUCIBLE TEST:
        // This skips revocation status; production needs a real policy.
        params.setRevocationEnabled(false);

        PKIXCertPathValidatorResult result =
                (PKIXCertPathValidatorResult)
                CertPathValidator.getInstance("PKIX")
                        .validate(path, params);

        System.out.println("pkix-valid=true");
        System.out.println("path-certificate-count=" +
                path.getCertificates().size());
        System.out.println("anchor-not-in-path=" +
                !path.getCertificates().contains(root));
        System.out.println("correct-trust-anchor=" +
                root.equals(result.getTrustAnchor().getTrustedCert()));

        CertPath missingIntermediate = certificates.generateCertPath(
                Collections.singletonList(server));
        System.out.println("missing-intermediate-rejected=" +
                fails(missingIntermediate, params));

        PKIXParameters wrongParams = new PKIXParameters(
                Collections.singleton(new TrustAnchor(wrongRoot, null)));
        wrongParams.setRevocationEnabled(false);
        System.out.println("wrong-anchor-rejected=" +
                fails(path, wrongParams));

        PKIXParameters expiredParams = new PKIXParameters(trusted);
        expiredParams.setRevocationEnabled(false);
        expiredParams.setDate(new Date(
                server.getNotAfter().getTime() + 24L * 60 * 60 * 1000));
        System.out.println("expired-server-rejected=" +
                fails(path, expiredParams));

        X509CertSelector selector = new X509CertSelector();
        selector.setCertificate(server);
        PKIXBuilderParameters buildParams =
                new PKIXBuilderParameters(trusted, selector);
        buildParams.setRevocationEnabled(false);
        buildParams.addCertStore(CertStore.getInstance("Collection",
                new CollectionCertStoreParameters(
                        Arrays.asList(server, intermediate))));

        PKIXCertPathBuilderResult buildResult =
                (PKIXCertPathBuilderResult)
                CertPathBuilder.getInstance("PKIX").build(buildParams);
        System.out.println("built-certificates=" +
                buildResult.getCertPath().getCertificates().size());
        System.out.println("built-root-trusted=" +
                root.equals(buildResult.getTrustAnchor().getTrustedCert()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 PkixChainDemo.java
java PkixChainDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK 21:**

~~~text
pkixparameters-revocation-default=true
pkix-valid=true
path-certificate-count=2
anchor-not-in-path=true
correct-trust-anchor=true
missing-intermediate-rejected=true
wrong-anchor-rejected=true
expired-server-rejected=true
built-certificates=2
built-root-trusted=true
~~~

### Đọc từng negative test

- **`missing-intermediate-rejected=true`:** `CertPathValidator` nhận path chỉ có leaf, không có intermediate; trong demo không có đường nào trực tiếp đến root.
- **`wrong-anchor-rejected=true`:** có đủ leaf/intermediate nhưng root ở policy **không phải CA đã ký đường đi**; chữ ký từng bước đúng **vẫn không đủ tin cậy**.
- **`expired-server-rejected=true`:** validator được yêu cầu đánh giá **sau ngày `notAfter` của leaf**, nên path thất bại ở phần thời hạn. Không cố ý đổi đồng hồ máy thực.
- **`built-certificates=2`:** `CertPathBuilder` có thể lấy server/intermediate từ `CertStore` và xây path tới root; root vẫn nằm trong `TrustAnchor`, **không thuộc danh sách certificate của path**.

### Lưu ý đặc biệt về revocation

`new PKIXParameters(Set<TrustAnchor>)` có `isRevocationEnabled()==true` **theo hợp đồng API**. Demo chủ động gọi `setRevocationEnabled(false)` để mọi test **offline** có kết quả xác định vì certificates thử nghiệm không có CRL/OCSP responder. **Đây là nới lỏng chỉ phục vụ bài thực hành**, không phải cấu hình PKIX nên áp dụng chung cho production. Nếu ứng dụng có yêu cầu revocation, cần thiết kế CRL/OCSP và chính sách network/error response phù hợp.

**Khác biệt dễ nhầm:** Theo Oracle JSSE Guide, khi SunJSSE PKIX `TrustManagerFactory` được khởi tạo bằng `init(KeyStore)`, revocation checking trong cấu hình mặc định này **bị tắt**; điều đó **không mâu thuẫn** với mặc định của **`PKIXParameters` mới tạo là `true`**, vì hai đường cấu hình khác nhau. Không dựa vào một mặc định được kể lại mà bỏ kiểm tra policy revocation của service thực tế.

## 9. Chương trình Java 10 số 3 — `TrustManagerFactory` với Root CA đã tin cậy

Bài thử này dùng một **truststore trong bộ nhớ** chứa đúng Demo Root CA; không sửa `cacerts` của JDK đang cài.

File **`TrustManagerDemo.java`**:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.KeyStore;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509ExtendedTrustManager;
import javax.net.ssl.X509TrustManager;

public class TrustManagerDemo {
    static X509Certificate load(String file) throws Exception {
        try (InputStream in = Files.newInputStream(Paths.get(file))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);
        }
    }

    static X509TrustManager managerFor(X509Certificate anchor)
            throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        trustStore.load(null, null);
        trustStore.setCertificateEntry("selected-anchor", anchor);

        TrustManagerFactory factory =
                TrustManagerFactory.getInstance("PKIX");
        factory.init(trustStore);

        for (TrustManager manager : factory.getTrustManagers()) {
            if (manager instanceof X509TrustManager) {
                return (X509TrustManager) manager;
            }
        }
        throw new IllegalStateException(
                "No X.509 manager from provider");
    }

    static boolean rejected(X509TrustManager manager,
                            X509Certificate[] chain) {
        try {
            manager.checkServerTrusted(chain, "RSA");
            return false;
        } catch (CertificateException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        X509Certificate root = load("root.pem");
        X509Certificate intermediate = load("intermediate.pem");
        X509Certificate leaf = load("server.pem");

        X509TrustManager trusted = managerFor(root);
        trusted.checkServerTrusted(
                new X509Certificate[]{leaf, intermediate}, "RSA");

        System.out.println("server-chain-trusted=true");
        System.out.println("selected-is-extended=" +
                (trusted instanceof X509ExtendedTrustManager));
        System.out.println("accepted-issuers=" +
                trusted.getAcceptedIssuers().length);

        System.out.println("missing-intermediate-rejected=" +
                rejected(trusted,
                        new X509Certificate[]{leaf}));

        System.out.println("wrong-root-rejected=" +
                rejected(managerFor(load("wrong-root.pem")),
                        new X509Certificate[]{leaf, intermediate}));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 TrustManagerDemo.java
java TrustManagerDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK 21/SunJSSE:**

~~~text
server-chain-trusted=true
selected-is-extended=true
accepted-issuers=1
missing-intermediate-rejected=true
wrong-root-rejected=true
~~~

### Những kết luận được và không được rút ra

- `checkServerTrusted` **không ném exception** với chain phù hợp và đúng trust anchor → kiểm tra tin cậy thành công với API/thuật toán/provider hiện tại.
- `selected-is-extended=true` cho thấy `TrustManagerFactory("PKIX")` trên SunJSSE đã trả một manager hỗ trợ connection-sensitive overloads. **Không khẳng định mọi provider bắt buộc cùng class/implementation**.
- `getAcceptedIssuers().length==1` vì demo truststore chứa một root CA. **Đây không phải hàm trả “tổng số server được tin cậy”**; nó liệt kê các issuer certificates mà manager sẵn sàng xem xét.
- Không có intermediate hoặc chỉ tin wrong root → kiểm tra không thành công trong demo.
- **`checkServerTrusted(chain,"RSA")` không biết hostname** của một kết nối HTTPS cụ thể. Chưa có endpoint identification cho `localhost`/`127.0.0.1` ở chương trình này.
- Chỉ tin một root thử nghiệm trong **scoped SSLContext** nghĩa là client **không tự kế thừa toàn bộ default CA anchors** của JDK. Nếu service cần kết nối đồng thời đến public HTTPS và internal PKI, hãy thiết kế chính sách truststore/SSLContext có chủ đích; không mặc định một truststore tùy biến sẽ tự cộng thêm `cacerts`.

**Không làm:** implement `X509TrustManager` với `checkServerTrusted` rỗng, hoặc một `HostnameVerifier` luôn trả `true`. Những đoạn đó **loại bỏ bảo vệ chống tấn công giả mạo máy chủ**, không phải cách sửa lỗi TLS hợp lệ.

## 10. Kiểm tra tên máy chủ: trust chain hợp lệ vẫn có thể sai SAN

HTTPS xác thực **đúng peer mà client định liên hệ**, không chỉ “một server certificate do một CA đáng tin cấp”. Trên JSSE, `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` yêu cầu xác minh danh tính endpoint theo quy tắc HTTPS trong quá trình TLS handshake khi sử dụng trust manager/provider hỗ trợ đúng.

Ví dụ:

~~~java
SSLParameters params = socket.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(params);
socket.startHandshake();
~~~

Đây là **đoạn code bên trong method**, không phải chương trình độc lập. Không chỉ gọi `checkServerTrusted(chain, "RSA")` rồi coi như đã xác minh hostname. Với client dùng `HttpsURLConnection`, Java `HttpClient` từ Java 11+, hoặc framework HTTP khác, hãy dùng **cấu hình xác minh endpoint mặc định và đúng chính sách của thư viện**; đừng tự tắt host verification để xử lý một certificate mismatch.

**`SAN DNS:localhost` chỉ khớp DNS hostname `localhost`, không tự khớp IP address `127.0.0.1`.** Nếu client kết nối bằng IP, leaf cần **IP SAN** thích hợp (không phải chỉ DNS SAN). Trong môi trường production, nên phát hành certificate với tên thực tế mà client sẽ sử dụng, không tạo một root CA mới để che lỗi tên.

## 11. Chương trình Java 10 số 4 — TLS loopback xác minh cả trust và hostname

Ví dụ này mở một **TLS server chỉ trên loopback `127.0.0.1`** bằng `server.p12` của bài thực hành, rồi tạo ba client connections:

1. Trust đúng Root CA và xác minh hostname `localhost` → **thành công**.
2. Trust đúng Root CA nhưng xác minh tên `127.0.0.1` → **bị từ chối** do leaf chỉ có **DNS SAN:localhost**.
3. Trust **wrong-root.pem** nhưng hostname vẫn là `localhost` → **bị từ chối** vì không có trust anchor phù hợp.

Không kết nối Internet và không cần sửa `cacerts`.

Tạo file **`LocalTlsHostnameDemo.java`**:

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.KeyStore;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class LocalTlsHostnameDemo {
    static X509Certificate certificate(String path) throws Exception {
        try (InputStream in = Files.newInputStream(Paths.get(path))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(in);
        }
    }

    static SSLContext tlsServer() throws Exception {
        char[] password = "changeit".toCharArray(); // Local demo only.
        KeyStore serverKeys = KeyStore.getInstance("PKCS12");
        try (InputStream in =
                Files.newInputStream(Paths.get("server.p12"))) {
            serverKeys.load(in, password);
        }

        KeyManagerFactory keys = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keys.init(serverKeys, password);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys.getKeyManagers(), null, null);
        return context;
    }

    static SSLContext tlsClient(X509Certificate root) throws Exception {
        KeyStore trust = KeyStore.getInstance("PKCS12");
        trust.load(null, null);
        trust.setCertificateEntry("local-root", root);

        TrustManagerFactory managers =
                TrustManagerFactory.getInstance("PKIX");
        managers.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, managers.getTrustManagers(), null);
        return context;
    }

    static boolean connect(SSLContext context, int port,
                           String tlsPeerName) throws Exception {
        try (Socket tcp = new Socket("127.0.0.1", port);
             SSLSocket tls = (SSLSocket) context.getSocketFactory()
                     .createSocket(tcp, tlsPeerName, port, true)) {
            SSLParameters params = tls.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            tls.setSSLParameters(params);
            tls.startHandshake();
            return true;
        } catch (SSLHandshakeException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        SSLContext serverContext = tlsServer();
        SSLContext clientTrusted =
                tlsClient(certificate("root.pem"));
        SSLContext clientUntrusted =
                tlsClient(certificate("wrong-root.pem"));

        try (SSLServerSocket server = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 10, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(8000);

            Thread listener = new Thread(() -> {
                for (int i = 0; i < 3; i++) {
                    try (SSLSocket tls =
                            (SSLSocket) server.accept()) {
                        tls.setSoTimeout(4000);
                        tls.startHandshake();
                    } catch (Exception expectedForRejectedClient) {
                        // Negative test clients intentionally reject TLS.
                    }
                }
            }, "local-tls-listener");
            listener.start();

            boolean valid = connect(clientTrusted,
                    server.getLocalPort(), "localhost");
            boolean hostnameMismatch = connect(clientTrusted,
                    server.getLocalPort(), "127.0.0.1");
            boolean untrusted = connect(clientUntrusted,
                    server.getLocalPort(), "localhost");

            listener.join(10000);
            if (listener.isAlive()) {
                server.close();
                throw new IllegalStateException(
                        "Server thread did not finish");
            }

            System.out.println("trusted-chain-and-hostname=" + valid);
            System.out.println("mismatched-ip-rejected=" +
                    !hostnameMismatch);
            System.out.println("untrusted-root-rejected=" +
                    !untrusted);
        }
    }
}
~~~

Chạy (cùng thư mục có `server.p12`, `root.pem` và `wrong-root.pem`):

~~~bash
javac --release 10 LocalTlsHostnameDemo.java
java LocalTlsHostnameDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
trusted-chain-and-hostname=true
mismatched-ip-rejected=true
untrusted-root-rejected=true
~~~

**Phân tích kết quả:**

- Kết nối TCP ở cả ba ca đều tới `127.0.0.1` để chạy cục bộ. Tuy nhiên tên peer TLS ở `createSocket(..., tlsPeerName, ...)` lần lượt là `localhost` hoặc `127.0.0.1`. Endpoint identification **dựa vào peer name cần kiểm tra**, không chỉ địa chỉ TCP dùng để truyền byte.
- Ca thành công dùng chuỗi server → intermediate → root đã tin, đồng thời SAN khớp `localhost`.
- Ca hostname mismatch vẫn có **đúng CA**, nhưng thất bại ở **TLS identity check** vì leaf không có `IP SAN:127.0.0.1`.
- Ca wrong root dùng **đúng tên**, nhưng không có đường tin cậy dẫn đến CA được client cho phép.
- Code trên bắt `SSLHandshakeException` cho hai ca negative, không tắt xác minh. `listener` cũng chấp nhận việc client cố ý từ chối handshake; đây là **test harness cục bộ**, không phải server production. Trong production, cần phân loại và log lỗi handshake thay vì bắt rộng.
- Mật khẩu `changeit` và root private key ở bộ thử này **không dùng trong sản phẩm thật**. Không deploy code hard-code password hoặc lưu root private key trên ứng dụng server.

## 12. Khi gặp `PKIX path building failed`

Một số lỗi thường gặp trong Java HTTPS clients:

~~~text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed
sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
~~~

Đây là **ví dụ dạng thông báo** từ SunJSSE/OpenJDK; văn bản chi tiết có thể khác theo JDK/provider. Nó thường chỉ ra **không tìm được certificate path hợp lệ đến một trust anchor được tin cậy**, nhưng không được kết luận ngay “chắc chắn Java thiếu root CA”.

Những nguyên nhân khả dĩ:

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý đúng |
| --- | --- | --- |
| Server dùng internal/private CA | Client chưa có **root CA được tổ chức phê duyệt** | Thêm đúng root certificate vào truststore riêng và quản lý lifecycle |
| Server gửi leaf nhưng thiếu intermediate | Không xây được đường tới root | **Sửa cấu hình server** để gửi chain intermediate thích hợp |
| Client chạy trong container khác host | JDK image có truststore khác | Kiểm tra truststore của đúng process/container |
| `javax.net.ssl.trustStore` trỏ sai path | JVM tải truststore rỗng hoặc sai | Kiểm tra path, format, type, secret và quyền |
| Có root trong truststore nhưng policy từ chối | Expired leaf, key usage, name constraints, algorithm restrictions, revocation | Xem exception cause và `certpath` debug đúng phạm vi |
| Có chứng thư hợp lệ nhưng sai hostname | `SSLHandshakeException` về name mismatch | Sửa SAN/dịch vụ truy cập; **không tắt hostname verification** |
| Server chứng thư hết hạn | `CertificateExpiredException` hoặc PKIX validation error | Renew/redeploy certificate hợp lệ |
| CA từng tin đã bị loại bỏ | Root store/security update thay đổi | Kiểm tra root policy/rollover, không downgrade TLS security |
| TLS version/cipher không tương thích | Protocol negotiation thất bại, không nhất thiết do trust | Xem TLS handshake logs và security algorithms |
| Client cert trong mTLS bị từ chối | Server trust manager từ chối client chain | Kiểm tra client key material, CA root của server, EKU clientAuth |

**Không phải lỗi TLS nào cũng là `PKIX path building failed`.** Protocol/cipher mismatch, certificate parsing, hostname mismatch, revocation failure và client authentication khác nhau. Xem **root cause của exception**, không chỉ phần đầu stack trace.

### Ghi log chẩn đoán JSSE và CertPath

Trong môi trường kiểm thử, có thể dùng:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath -jar your-app.jar
~~~

Đây là **lệnh chẩn đoán có application JAR cụ thể**, thay `your-app.jar` bằng artifact thực tế. Nó có thể in nhiều thông tin về handshake, trust manager, path building, danh tính server và cấu hình. **Không bật debug quá rộng trong production lâu dài:** log có overhead, có thể lộ metadata nhạy cảm và quá nhiều dòng. Không gửi nguyên debug log chứa thông tin nội bộ/certificates cho người không có quyền.

### Kiểm tra server gửi chuỗi gì

Bên ngoài Java, với OpenSSL có thể dùng ở môi trường được phép:

~~~bash
openssl s_client -connect example.test:443 -servername example.test -showcerts
~~~

Đây là **lệnh minh họa**, không phải yêu cầu kết nối URL thật hoặc lời khuyên xem kết quả “Verify return code 0” như bằng chứng đầy đủ cho Java. Thay host bằng địa chỉ hợp lệ mà bạn sở hữu/được phép kiểm tra. **OpenSSL sử dụng truststore khác** với JDK, nên kết quả OpenSSL thành công **không đảm bảo** Java client dùng truststore tương tự.

## 13. Revocation: CRL/OCSP không phải lúc nào cũng tự bật

Một certificate có thể còn hạn nhưng bị CA **thu hồi** do khóa bị lộ hoặc thay đổi trạng thái. Các phương án xác minh:

- **CRL (Certificate Revocation List):** danh sách chứng thư bị thu hồi do CA công bố, cần có nguồn CRL đáng tin và còn hiệu lực.
- **OCSP:** hỏi responder hoặc dùng thông tin được cung cấp theo protocol/provider; cần xem freshness, nonce/policy và lỗi kết nối.
- **`PKIXRevocationChecker`:** API cho kiểm soát revocation trong PKIX path validation.
- **Provider security properties:** JSSE/CertPath có nhiều property liên quan OCSP, CRLDP và revocation; hành vi có thể khác tùy cách init và security policy.

**Hai default dễ nhầm nhất:**

1. Một `new PKIXParameters(anchors)` có **revocation enabled = true** theo Javadoc.
2. **SunJSSE PKIX `TrustManagerFactory.init(KeyStore)` mặc định tắt revocation checking** theo JSSE Guide; nếu muốn bật phải cấu hình thêm. Cách dùng `TrustManagerFactory.init(ManagerFactoryParameters)` với CertPath parameters có những default/behavior khác.

Không dựa vào việc “TLS handshake thành công” để kết luận **OCSP/CRL chắc chắn đã được kiểm tra**. Đặc biệt, code demo ở mục 8 cố ý `setRevocationEnabled(false)` để kiểm thử offline, **không phải phương án security production**.

### Vì sao không bật `SOFT_FAIL` bừa bãi?

`PKIXRevocationChecker.Option.SOFT_FAIL` có thể bỏ qua một số lỗi không xác định được trạng thái revocation do hạ tầng mạng/CRL/OCSP, theo định nghĩa của API. Điều này có ý nghĩa availability nhưng **làm thay đổi chính sách an ninh**; phải được đánh giá theo threat model và yêu cầu tuân thủ, không chỉ bật để “cho TLS chạy”.

Với system yêu cầu xác minh thu hồi nghiêm ngặt, hãy định nghĩa **fail-closed vs fail-open** rõ ràng, cập nhật trust anchors, bảo đảm endpoint OCSP/CRL có thể truy cập và theo dõi lỗi. **Không hard-code revocation disabled như ví dụ offline**.

## 14. Algorithm constraints và key strength trên Java hiện đại

Một chứng thư hợp lệ trong tài liệu cũ có thể bị Java hiện đại từ chối vì thuật toán yếu. JVM có **security properties** như:

- `jdk.certpath.disabledAlgorithms`: giới hạn các thuật toán/chứng thư trong quá trình xây/kiểm tra certificate path.
- `jdk.tls.disabledAlgorithms`: giới hạn TLS/DTLS protocols, cipher suites và các thuật toán liên quan handshake.
- `jdk.tls.legacyAlgorithms`: mô tả các thuật toán cũ có chính sách negotiation riêng.

**Danh sách cụ thể có thể thay đổi theo JDK update**, nên không sao chép bảng blacklist cố định từ một tài liệu Java 10 rồi coi đó là hiện trạng. Trong JDK hiện hành, nhiều thuật toán/protocol yếu bị vô hiệu mặc định. Không giảm bảo vệ chỉ để chứng thư quá cũ hoạt động; ưu tiên **phát hành lại chứng thư và cấu hình TLS hiện đại**.

RSA 2048/3072 với SHA-256 dùng trong **bộ thử cục bộ** nhằm tránh các thuật toán legacy. Điều đó không tự chứng minh chúng là **bộ tham số tối ưu cho mọi môi trường**. Chính sách production cần dựa trên hướng dẫn bảo mật của tổ chức, chuẩn áp dụng và vendor/JDK.

## 15. Tạo truststore riêng cho private CA trong triển khai

Nếu tổ chức vận hành **private CA** và Java client cần kết nối internal service, quy trình an toàn là:

1. Xác định **đúng Root CA hoặc trust anchor được phê duyệt**; kiểm tra fingerprint/public key qua kênh tin cậy **ngoài** kết nối TLS đang lỗi.
2. Import **public certificate** vào truststore riêng, **không import private key CA**.
3. Kiểm soát quyền ghi và phân phối truststore bằng hệ thống cấu hình/secrets/immutable image.
4. Cấu hình **đúng client/SSLContext** dùng truststore; tránh thay global truststore của mọi ứng dụng trong JVM nếu chỉ một dịch vụ cần CA nội bộ.
5. Kiểm tra SAN của leaf, chain intermediate, EKU và mốc expiry/rotation.
6. Áp revocation/security algorithms policy riêng và thử cả trường hợp CA không được tin.
7. Cập nhật trust anchors khi CA rollover, thu hồi trust một cách có kế hoạch, không tự tin mọi chứng thư cũ mãi được chấp nhận.

Ví dụ **chỉ import public root CA của bài test**:

~~~bash
keytool -importcert -alias demo-root -file root.pem -keystore client-truststore.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

Với lệnh JSSE dựa trên truststore mặc định:

~~~bash
java -Djavax.net.ssl.trustStore=client-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.trustStorePassword=changeit -jar your-app.jar
~~~

**Đây là ví dụ cấu hình test với mật khẩu công khai, không phải khuyến nghị production.** Trong thực tế, passphrase cần được quản lý bí mật; command-line arguments có thể bị quan sát. Ngoài ra, **một truststore riêng thường không tự cộng thêm toàn bộ public CA roots** của `cacerts`. Nếu sản phẩm vừa gọi internal CA vừa gọi public HTTPS, cần cấu hình truststore/contexts tương ứng, tránh vô tình cắt mất gốc công khai hoặc mở rộng trust quá mức.

**Không dùng `trust-all` trong staging/production** rồi chỉ “bật trust nghiêm ngặt khi có thời gian”: một kết nối không xác minh peer hoàn toàn có thể bị middlebox/attacker giả mạo.

## 16. Thời hạn chứng thư, trust anchor và vận hành rotation

Chứng thư server/intermediate có **`notBefore` và `notAfter`**; khi quá hạn, chain có thể bị từ chối. Root/trust anchor còn chịu **quyết định tin cậy** của trust policy. Theo PKIX, root trust anchor được cung cấp bên ngoài `CertPath`, nên không được suy luận rằng mọi thuộc tính của trust anchor đều được kiểm tra **y hệt** một leaf/intermediate bình thường.

**Cách vận hành đúng:**

- Theo dõi expiry của **leaf** và **intermediate**; thay certificate trước khi hết hạn.
- Quản lý root CA rollover và danh sách trust anchors có quy trình phê duyệt.
- Khi đổi server cert, bảo đảm SAN/EKU/chain vẫn đúng; thử trên JDK và client truststores đang triển khai.
- Theo dõi algorithm deprecations và root store updates. Một root có trong JDK A có thể không còn ở JDK B/update mới.
- Trong multi-region hoặc cluster, xác định **client nào** đang tin root cũ/root mới; không dựa vào một thành công cục bộ.
- Không ghi private key/certificate password vào log, không tái sử dụng CA private key ở nhiều ứng dụng.
- Đối với mTLS, cả client và server đều phải xác minh certificate và phân biệt `clientAuth`/`serverAuth` theo use case.

### Vì sao một certificate “đã verify chữ ký” vẫn bị từ chối?

Có ít nhất bốn nhóm lý do độc lập: **thiếu trust anchor**, **vi phạm policy PKIX** (expiry/constraints/algorithm), **sai hostname**, hoặc **revocation/security configuration**. Đừng nhìn duy nhất `openssl verify` hoặc `cert.verify(...)` rồi kết luận Java TLS phải thành công.

## 17. Quy trình điều tra lỗi SSL trong Java

~~~text
Handshake TLS thất bại
        |
        v
Đọc cause thực tế, truststore, tên host và JDK build
        |
        +--> Không xây được path đến Root CA tin cậy?
        |         |
        |         +--> Root/CA thiếu hoặc truststore sai
        |         +--> Intermediate không được cung cấp
        |         +--> Policy/constraints/algorithm path lỗi
        |
        +--> Path hợp lệ nhưng endpoint identification lỗi?
        |         |
        |         +--> DNS/IP client dùng không nằm trong SAN
        |         +--> Client kết nối theo tên khác hostname cert
        |
        +--> Certificate expiry/revocation?
        |         |
        |         +--> Renew cert, xác minh CRL/OCSP policy
        |
        +--> TLS protocol/cipher/key exchange?
                  |
                  +--> Kiểm tra TLS config, security properties
                       và stacktrace / debug logs đúng JDK
~~~

Các bước cụ thể:

1. **Xác định Java process thực tế** và JDK build, provider, container image; không dùng cấu hình máy developer thay cho container.
2. **Ghi lại hostname/IP** mà client sử dụng và so với SAN leaf.
3. **Kiểm tra certificate chain server gửi**: leaf, intermediate và các dấu hiệu sai thứ tự/thiếu.
4. **Xác định truststore thật sự được load**, đặc biệt nếu `javax.net.ssl.trustStore` được chỉ định.
5. **Kiểm tra root CA được phê duyệt**, không lấy root do server tự đề nghị làm trust anchor.
6. **Phân loại exception**: path building, expired, revoked, algorithm constraints, hostname mismatch hoặc handshake protocol.
7. **Bật log JSSE/CertPath có chọn lọc** trong môi trường test, chú ý thông tin nhạy cảm.
8. **Sửa đúng nguyên nhân**: deploy intermediate, cập nhật root được tin, renew leaf, sửa SAN, cập nhật JDK hoặc TLS settings.
9. **Chạy negative tests**: wrong-root, expired, wrong host; đừng chỉ kiểm tra đường thành công.
10. **Bảo toàn hostname verification và PKIX validation**; không chấp nhận “works with trust-all” làm solution.

## 18. Những lỗi phổ biến và cách tránh

| Sai lầm | Tại sao nguy hiểm/sai? | Cách làm đúng |
| --- | --- | --- |
| “Server đưa certificate là phải tin” | Một attacker cũng có thể đưa certificate | Tin **trust anchor được cấu hình**, không tin peer tự khai |
| “Self-signed nghĩa là trusted” | Self-signed chỉ là thuộc tính chữ ký | Trust do policy/truststore quyết định |
| “Root phải luôn được server gửi” | Trust anchor thường là cấu hình **ở client** | Gửi leaf và intermediates; client duy trì root đáng tin |
| “CertPath luôn chứa root” | Trong PKIX, trust anchor nằm ngoài path | Path leaf → intermediates, root trong PKIXParameters |
| “Verify chữ ký một lần là đủ” | Bỏ qua CA/expiry/EKU/name constraints/revocation | Dùng PKIX validator/trust manager chuẩn |
| “`checkServerTrusted` thành công nghĩa là đúng hostname” | Overload 2 tham số không biết tên endpoint | Kiểm tra SAN theo HTTPS/endpoint identification |
| “SAN DNS localhost cũng hợp IP 127.0.0.1” | DNS SAN không phải IP SAN | Phát hành SAN theo tên client thực dùng |
| “`X509TrustManager` phải return boolean” | Hợp đồng là **ném `CertificateException`** | Giữ hành vi throw khi không tin |
| “Viết `checkServerTrusted` rỗng là sửa SSL” | Tắt authentication của peer, rủi ro MITM | Sửa CA/chain/SAN đúng |
| “`getAcceptedIssuers()==1` nghĩa chỉ tin một server” | Trả các CA issuer certificates | Hiểu trust anchors và path rules |
| “Bổ sung root tự động bằng cách tin cert server gửi” | Attacker tự cấp root và được chấp nhận | Pin/verify root qua kênh ngoài, quản lý trust |
| “Mọi JDK đều có cùng cacerts” | Root store phụ thuộc build/update/provider | Kiểm tra artifact/truststore của đúng JVM |
| “Không có intermediates cũng tự hoạt động” | Path building chỉ dùng nguồn mà implementation có | Sửa server chain hoặc cấu hình CertStore hợp lệ |
| “Tắt revocation trong demo là mặc định production tốt” | Bỏ qua nguy cơ certificate bị thu hồi | Thiết kế CRL/OCSP và fail policy |
| “PKIXParameters default và TMF.init(KeyStore) giống nhau” | JSSE SunJSSE có khác biệt revocation defaults | Đọc đúng API/initialization path |
| “Chỉnh `jdk.certpath.disabledAlgorithms` về legacy là sửa đúng” | Hạ chuẩn an ninh | Renew certificates/algorithms đủ mạnh |
| “Dùng cùng root cert cả làm server private key” | Trộn trust anchors với key material, làm lộ CA | Phân quyền CA vs server keystore |
| “Truststore riêng mặc định được cộng với cacerts” | Scoped factory thường chỉ dùng tập được cấu hình | Thiết kế trust contexts/anchor sets có chủ đích |
| “Cứ root trusted thì TLS 1.0 hoạt động” | Protocol/cipher policy là vấn đề khác | Dùng TLS hiện hành, kiểm tra negotiation |
| “Log `PKIX path building failed` chắc do root thiếu” | Intermediate/expiry/policy cũng có thể lỗi | Điều tra đầy đủ cause và chain |

## 19. Checklist QA cho bài chứng thư gốc và TrustManager

- [ ] Đã xác định đúng leaf, intermediate(s), root/trust anchor và vai trò của từng certificate.
- [ ] Root CA được thêm vào truststore **chỉ sau khi xác minh nguồn tin cậy ngoài kênh TLS đang lỗi**.
- [ ] Truststore chứa **public certificate**, không chứa private CA key.
- [ ] Leaf có SAN DNS/IP phù hợp đúng tên client sử dụng.
- [ ] Intermediate có `CA=true`, `keyCertSign` và giới hạn path phù hợp.
- [ ] Leaf có keyUsage/EKU server phù hợp; certificate còn hạn.
- [ ] Các chữ ký trong chain xác minh theo public keys của issuers.
- [ ] PKIX path xây được tới **đúng anchor**; root không đưa nhầm vào `CertPath`.
- [ ] TrustManagerFactory được khởi tạo từ truststore/PKIX policy do ứng dụng lựa chọn.
- [ ] `X509TrustManager.checkServerTrusted` reject chain không được tin.
- [ ] Endpoint identification `HTTPS` không bị tắt; hostname mismatch phải bị từ chối.
- [ ] Đã thử negative: thiếu intermediate, sai root, leaf expired và wrong hostname.
- [ ] Mặc định revocation được hiểu đúng theo **loại PKIX API và JSSE initialization**; có policy CRL/OCSP production khi cần.
- [ ] Security properties chặn thuật toán yếu được giữ theo chuẩn hiện hành.
- [ ] Không có custom trust-all manager hoặc `HostnameVerifier` trả `true` vô điều kiện.
- [ ] Nếu dùng custom truststore, đã kiểm tra có vô tình làm mất những public roots cần thiết không.
- [ ] JDK/vendor/runtime image đang chạy có `cacerts`/`jssecacerts` như mong đợi.
- [ ] Không lộ truststore passwords, private keys hoặc debug logs nhạy cảm.
- [ ] CA/private test keys không được commit hoặc copy sang production.
- [ ] Có quy trình rotation, CA rollover và theo dõi expiry trước hạn.
- [ ] Test Java đã chạy dưới compile baseline phù hợp (`--release 10` trong bài).
- [ ] Không suy luận “PKIX valid” đồng nghĩa “HTTP endpoint authenticated” nếu chưa kiểm tra host.

## 20. Câu hỏi tự kiểm tra

1. Chứng thư root tự ký có tự được mọi Java client tin cậy không?
2. Vì sao server thường không cần gửi root CA của mình trong TLS handshake?
3. Trong PKIX, trust anchor có nằm trong danh sách `CertPath.getCertificates()` không?
4. `TrustManager` và `KeyManager` khác nhau thế nào?
5. `checkServerTrusted` trả `false` khi không tin hay ném exception?
6. Vì sao `certificate.verify(issuerPublicKey)` chưa đủ cho TLS authentication?
7. Khi đã có root hợp lệ mà thiếu intermediate, `CertPathValidator` có nhất thiết tự lấy nó từ Internet không?
8. `CertPathBuilder` khác `CertPathValidator` ở điểm nào?
9. Leaf SAN chỉ có `DNS:localhost` có xác minh được peer `127.0.0.1` theo HTTPS endpoint identification không?
10. `X509ExtendedTrustManager` bổ sung thông tin gì so với interface cũ?
11. Vì sao một `TrustManagerFactory` khởi tạo bằng truststore riêng có thể làm mất public trust anchors?
12. `PKIXParameters` mới tạo có revocation enabled mặc định không?
13. SunJSSE PKIX `TrustManagerFactory.init(KeyStore)` bật revocation checking mặc định không?
14. Vì sao demo offline tắt revocation chưa phải policy production?
15. Thông điệp `PKIX path building failed` luôn có nghĩa root thiếu không?
16. Trong bài, số certificates trong validated `CertPath` là mấy? Root nằm ở đâu?
17. Root được tin nhưng hostname sai phải được chấp nhận hay từ chối?
18. Có nên sửa lỗi TLS bằng trust manager rỗng không?
19. `cacerts` có phải danh sách CA bất biến giữa mọi JDK không?
20. JEP 319 liên quan Java 10 đóng góp gì?
21. Khi phát hành private CA trong tổ chức, CA private key có được đưa vào truststore client không?
22. Có thể xem `getAcceptedIssuers` như danh sách mọi host được phép truy cập không?

**Đáp án:**

1. Không. Trust được cấu hình, không đến từ việc tự ký.
2. Client cần có root từ nguồn đáng tin; server tự gửi root không tự tạo lòng tin.
3. Không. Root trust anchor được truyền riêng qua `TrustAnchor`/`PKIXParameters`.
4. TrustManager kiểm tra peer; KeyManager lựa chọn **khóa/chứng thư của chính mình**.
5. Ném `CertificateException`.
6. Chỉ kiểm chữ ký, chưa kiểm trust anchor, validity, CA constraints, EKU, revocation, hostname.
7. Không. Việc tìm kiếm intermediate phụ thuộc các CertStore/AIA/policy thực tế.
8. Builder tìm/ghép path; Validator xác minh một path đã có.
9. Không; không có IP SAN cho 127.0.0.1.
10. Overloads gắn TLS Socket/SSLEngine, hỗ trợ constraints/endpoint verification theo context.
11. Factory/scoped truststore chỉ dùng nguồn được cung cấp nếu không chủ động kết hợp các anchors.
12. Có, `true`.
13. Theo Oracle SunJSSE Guide, **không** trong đường khởi tạo bằng `KeyStore` mặc định.
14. Revocation có yêu cầu bảo mật riêng, cần CRL/OCSP và policy rõ ràng.
15. Không. Có thể thiếu intermediate, sai truststore hoặc constraints/algorithm.
16. **2** (server và intermediate); root nằm trong `TrustAnchor`.
17. Từ chối. Chain trust không thay hostname verification.
18. Không; nó vô hiệu xác thực và mở cửa MITM.
19. Không. Root sets thay đổi theo distribution/update/policy.
20. Open-source các root certificates cho OpenJDK `cacerts` trong JDK 10.
21. Không. Chỉ phân phối **public root certificate**; bảo vệ CA private key.
22. Không. Nó liên quan trusted issuer certificates, không phải danh sách endpoint host.

## 21. Tài liệu chính thức còn áp dụng

- **Oracle Java SE 25 — Java Secure Socket Extension (JSSE) Reference Guide:** https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html
- **Oracle Java SE 25 — Java PKI Programmer's Guide:** https://docs.oracle.com/en/java/javase/25/security/java-pki-programmers-guide.html
- **Oracle Java SE 25 — `X509TrustManager`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509TrustManager.html
- **Oracle Java SE 25 — `X509ExtendedTrustManager`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html
- **Oracle Java SE 25 — `TrustManagerFactory`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html
- **Oracle Java SE 25 — `SSLParameters` và endpoint identification:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html
- **Oracle Java SE 25 — `CertPathValidator`, `CertPathBuilder`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/CertPathValidator.html
- **Oracle Java SE 26 — `PKIXParameters` và revocation defaults:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXParameters.html
- **Oracle Java SE 25 — `TrustAnchor`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/TrustAnchor.html
- **OpenJDK — JEP 319, Root Certificates (Java 10):** https://openjdk.org/jeps/319
- **Oracle JDK 25 — `keytool` công cụ quản lý certificate/keystore:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html
- **IETF RFC 5280 — X.509 Public Key Infrastructure Certificate and CRL Profile:** https://www.rfc-editor.org/rfc/rfc5280
- **IETF RFC 6125 — Service Identity in TLS (historical); hiện dùng RFC 9525:** https://www.rfc-editor.org/rfc/rfc9525

**Kết luận:** `TrustManager` trong JSSE xác minh **chuỗi chứng thư X.509** theo trust policy của client; **gốc tin cậy đến từ truststore/TrustAnchor do client phê duyệt**, không đến từ certificate tự ký do server gửi. PKIX kiểm tra đường leaf→intermediate→anchor, nhưng **hostname verification** phải được áp dụng riêng đúng HTTPS/endpoint. Một Java application an toàn dùng **TrustManagerFactory PKIX/X509ExtendedTrustManager hoặc JSSE defaults đã được cấu hình đúng**, xử lý revocation/algorithm constraints theo chính sách, và **không bao giờ thay lỗi PKIX bằng trust-all manager**. Các ví dụ RSA/SHA-256 trong bài đều chạy cục bộ và có negative tests để chứng minh một chuỗi có chữ ký đúng vẫn có thể bị từ chối vì thiếu anchor, hết hạn hoặc không khớp hostname.