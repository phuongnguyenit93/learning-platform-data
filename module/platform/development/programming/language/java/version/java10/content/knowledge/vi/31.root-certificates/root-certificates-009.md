# Tác động của cập nhật, bổ sung hoặc loại bỏ CA trên JDK — Java 10 và Java hiện đại

## 1. Tình huống: sau khi nâng JDK, HTTPS bỗng báo lỗi

Một dịch vụ Java gọi HTTPS tới API của đối tác. Hôm trước mọi yêu cầu thành công; hôm sau thay JDK image, một số yêu cầu phát sinh ngoại lệ:

```text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed
```

Một trường hợp ngược lại: sau khi cập nhật JDK, ứng dụng bắt đầu kết nối thành công với endpoint dùng một root CA mới, dù không có thay đổi ở source code. Cả hai có thể liên quan đến **tập Certificate Authority (CA) certificates được tin cậy** của JDK.

**Chủ đề chính:** việc JDK **thêm**, **cập nhật** hoặc **loại bỏ** root CA có thể thay đổi những certificate chains mà Java TLS client (hoặc server xác thực client certificate trong mTLS) chấp nhận. Đây không chỉ là cập nhật file, mà là cập nhật **ranh giới tin cậy** của hệ thống.

Java 10 giới thiệu **JEP 319 — Root Certificates**, đưa một bộ root CA mặc định vào các bản phân phối OpenJDK phù hợp. Trên JDK hiện đại, bộ root CA tiếp tục được duy trì; root certificates có thể được thêm hoặc xóa theo chính sách của JDK vendor. Kiến thức về `cacerts`, JSSE, PKIX, trust anchors và quản lý certificate chain vẫn áp dụng với Java 17, 21, 25, 27 và các JDK được hỗ trợ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt root CA, intermediate CA, leaf certificate và trust anchor.
2. Hiểu vai trò JEP 319 và bộ CA mặc định của JDK.
3. Dự đoán tác động **thêm root CA** hoặc **loại root CA** đối với TLS certificate path.
4. Nhận diện khi nào root CA thay đổi **không tác động** vì ứng dụng dùng truststore riêng.
5. Hiểu thứ tự truststore mặc định của **SunJSSE**.
6. Phân biệt root removal với revocation, expiry, hostname mismatch và algorithm restrictions.
7. Sử dụng `keytool` để kiểm tra, so fingerprint SHA-256 và cập nhật store được kiểm soát.
8. Biên dịch một ví dụ Java 17+ kiểm chứng sự thay đổi của trust manager trước/sau khi thêm và bỏ CA.
9. Hiểu vì sao trust manager đã khởi tạo có thể tiếp tục dùng trust state cũ dù store đã đổi.
10. Triển khai JDK/CA rotation an toàn, theo dõi TLS failures và không vô hiệu hóa xác minh chứng chỉ.

**Lưu ý về phạm vi:** không phải mọi lỗi `SSLHandshakeException` đều do root CA; việc xử lý phải dựa trên chain, truststore, security policies và phiên bản JDK thực tế. Bài không khuyến nghị đưa CA đã bị rút vì bảo mật trở lại truststore chỉ để che lỗi.

## 2. Chuỗi chứng chỉ và điểm neo tin cậy

Một TLS server thông thường có **leaf certificate** cho hostname cụ thể. Leaf được ký bởi một **intermediate CA**, rồi chuỗi có thể dẫn tới **root CA**.

```text
Trusted Root CA (trust anchor)
              |
              | ký / xác thực
              v
       Intermediate CA
              |
              | ký
              v
       Server leaf cert
       SAN: api.example.test
              |
              v
         TLS server
              |
         TLS handshake
              v
       Java TLS client
```

Về bản chất:

- **Leaf/server certificate** chứa public key và danh tính máy chủ, thường được xác thực qua Subject Alternative Name (SAN).
- **Intermediate CA** chứng minh liên kết cấp chứng chỉ và có thể được server gửi trong TLS handshake.
- **Root CA** là điểm tin cậy do client/JDK/administrator lựa chọn.
- **Truststore** chứa những certificate entries được chọn làm trust anchors.
- **Keystore chứa private key** dùng cho danh tính của server hoặc mTLS client là một vai trò khác, không phải danh sách CA mà client tin.

Một root CA certificate thường **self-signed**, nhưng self-signed **không có nghĩa trusted**. Trust được quyết định bởi cấu hình của ứng dụng/JDK và chính sách an toàn, không do CA tự tuyên bố.

### Certificate path validation kiểm tra gì?

Trong một PKIX validation thường có nhiều yêu cầu:

- Chữ ký liên kết giữa leaf và issuer hợp lệ.
- CA có Basic Constraints và Key Usage thích hợp.
- Thời hạn và mục đích sử dụng của chứng chỉ phù hợp.
- Các thuật toán hoặc kích thước khóa không bị cấm bởi security policy.
- Name constraints và các certificate policies được tôn trọng.
- Có một đường xây chain tới **trust anchor được chấp nhận**.
- Revocation được kiểm tra theo **cấu hình/chính sách thực tế**.

**Hostname verification là một lớp kiểm tra riêng của TLS client**. Việc chain được tin không bảo đảm certificate được phép sử dụng cho bất cứ domain nào.

## 3. JEP 319: bước ngoặt Java 10 nhưng nội dung còn áp dụng

**JEP 319 — Root Certificates** đưa root certificates mặc định vào OpenJDK, giải quyết tình trạng một số OpenJDK binaries trước đó có `cacerts` rỗng. Tài liệu phát hành JDK 10 ghi nhận OpenJDK 9 Linux x64 từng thiếu trusted root CAs, buộc người dùng chỉ định truststore khác cho nhiều kết nối TLS.

Sau thay đổi đó:

- JDK thường đi kèm một bộ root CA certificates.
- Chứng chỉ có thể được bổ sung, cập nhật hoặc loại bỏ qua các JDK releases/security updates.
- Danh sách chính xác phụ thuộc vendor/distribution/build và có thể chịu tác động của cách đóng gói hệ điều hành.
- Người vận hành phải có quy trình kiểm thử **sự khác biệt trong chính sách trust** khi nâng JDK.

JEP 319 là mốc lịch sử để hiểu root store; **không nên sử dụng JDK 10 cũ làm runtime production mới** hoặc giữ nguyên danh sách CA của năm 2018. Hãy chọn JDK còn được hỗ trợ và kiểm tra truststore của build định triển khai.

## 4. Truststore thật sự: không phải lúc nào cũng là cacerts

Một câu hỏi phải trả lời trước khi xử lý là: **ứng dụng đang sử dụng bộ trust anchors từ đâu?**

Trong **SunJSSE reference implementation**, khi không cung cấp TrustManager tùy chỉnh, thứ tự tìm nguồn trust thông thường:

1. Nếu định nghĩa system property `javax.net.ssl.trustStore`, dùng store ở đường dẫn được chỉ định.
2. Nếu không chỉ định property mà có `java.home/lib/security/jssecacerts`, dùng file **`jssecacerts`**.
3. Nếu không có nguồn trên nhưng có `java.home/lib/security/cacerts`, dùng **`cacerts`**.
4. Nếu không có truststore hợp lệ theo đường mặc định, trust material có thể rỗng.

```text
Default SunJSSE TrustManagerFactory
             |
             +-- explicit javax.net.ssl.trustStore ?
             |            |
             |            +-- yes --> selected store
             |                         (if missing, empty trust material)
             |
             +-- no --> jssecacerts present?
                            |
                            +-- yes --> jssecacerts
                            |
                            +-- no --> cacerts if present
                                        |
                                        +-- else --> empty store
```

**Điểm dễ mắc lỗi:** nếu đã đặt `javax.net.ssl.trustStore=/etc/app/missing.p12` mà file đó không tồn tại, SunJSSE **không tự động fallback sang `cacerts`**. Theo tài liệu Oracle, một default trust manager với empty keystore có thể được tạo ra. Vì thế import CA vào `cacerts` lúc này có thể hoàn toàn không giải quyết lỗi.

### jssecacerts có độ ưu tiên cao hơn cacerts

Một ứng dụng có `jssecacerts` riêng có thể không nhận thay đổi root CAs trong `cacerts`. Đây là trường hợp cần kiểm tra khi bạn đã update JDK nhưng behavior vẫn giống cũ.

### Custom SSLContext hoặc provider khác

Ứng dụng/framework có thể tạo `SSLContext` và `TrustManagerFactory` với một `KeyStore` riêng. Một số Java distributions trên Linux có tích hợp OS trust store theo cơ chế đóng gói riêng. Một HTTP client native có thể không dùng SunJSSE.

Vì vậy:

- Không suy từ trình duyệt trên cùng máy.
- Không suy từ danh sách CA của OS host.
- Không suy từ file `cacerts` ở một JDK khác trên PATH.
- Không suy một library TLS tùy chỉnh luôn tuân theo JSSE default search order.

**Chỉ tin kết quả từ JVM process, provider và truststore thật sự của ứng dụng.**

## 5. Khi CA mới được bổ sung: lợi ích và mở rộng rủi ro

Giả sử JDK cũ tin root A nhưng chưa tin root B. Một API chuyển sang certificate chain kết thúc ở B.

Sau khi vendor bổ sung B vào `cacerts` và app dùng đúng nguồn đó, TLS client **có thể** xây path tới B và kết nối thành công.

Tác động tích cực:

- Hỗ trợ một CA public mới được duyệt.
- Giảm sự cần thiết phải import riêng một root CA khi endpoint chuyển đổi.
- Hỗ trợ giai đoạn root rotation hoặc cross-signing nếu chain phù hợp.

Tuy nhiên thêm root CA **mở rộng tập certificates có thể được chấp nhận**. CA mới có khả năng cấp certificates cho nhiều domain, không chỉ endpoint hiện tại, trừ khi client có chính sách hạn chế riêng.

**Thêm CA không bảo đảm kết nối thành công**. Hostname SAN sai, thiếu intermediate, leaf hết hạn, thuật toán yếu bị cấm, protocol TLS không tương thích hoặc certificate bị thu hồi theo policy vẫn có thể khiến kết nối thất bại.

### Chỉ import CA từ nguồn đáng tin

Đừng lấy đại certificate từ thông báo trình duyệt hoặc từ endpoint lỗi và import vào global truststore.

Đúng hơn:

1. Xác nhận với CA operator hoặc PKI admin.
2. Lấy certificate qua kênh đã xác minh.
3. So **SHA-256 fingerprint** qua nguồn độc lập.
4. Xem BasicConstraints, KeyUsage, thời hạn và chính sách.
5. Phê duyệt phạm vi truststore sẽ bị ảnh hưởng.
6. Test trước và rollout có kiểm soát.

**Subject/CN có thể trùng nhau dù public key khác**. Vì vậy không dùng duy nhất tên CA để xác thực.

## 6. Khi root CA bị loại bỏ: tại sao PKIX path có thể thất bại?

Giả sử server dùng:

```text
Server leaf --> Intermediate X --> Root A
```

Sau khi root A bị xóa khỏi effective truststore, nếu không còn đường PKIX hợp lệ tới trust anchor khác, Java client có thể lỗi:

```text
javax.net.ssl.SSLHandshakeException:
    PKIX path building failed
sun.security.provider.certpath.SunCertPathBuilderException:
    unable to find valid certification path to requested target
```

Việc xóa A là **thay đổi trong tập trust anchors**, không phải thao tác xóa leaf trên máy chủ.

### Không phải mọi endpoint liên quan A đều chắc chắn ngừng hoạt động

Khi có cross-signing hoặc nhiều alternative paths, client có thể tìm được chuỗi khác dẫn tới root B còn được tin cậy. Ngoài ra, một số applications dùng truststore riêng vẫn chứa A hoặc dùng trust manager đã khởi tạo trước lúc thay đổi.

Vì vậy:

- Bỏ root A khỏi JDK có thể làm **một số** kết nối thất bại.
- Nó không tự làm mọi certificate từng do A cấp bị revoked.
- Nó không ngăn client khác dùng một kho trust độc lập.
- Nó không bảo đảm tất cả process hiện hữu lập tức áp dụng thay đổi.
- Nó có thể là biện pháp cần thiết khi CA không còn đáp ứng chính sách bảo mật.

Các JDK release/migration notes hiện đại đã ghi nhận những lần loại bỏ root certificates. Trước khi update, phải đọc release notes của **đúng vendor/build** và rà soát endpoints phụ thuộc CA bị ảnh hưởng.

## 7. Root removal khác revocation và expiration

| Sự kiện | Nó thay đổi điều gì? | Không nên hiểu thành |
| --- | --- | --- |
| **Remove root CA** | Root không còn là trust anchor ở store được cập nhật | Mọi leaf dưới root bị revoked |
| **Revoke leaf cert** | CA công bố chứng chỉ không còn hợp lệ theo cơ chế CRL/OCSP | Root đã bị xóa khỏi truststore |
| **Leaf hết hạn** | Leaf không còn nằm trong thời gian hiệu lực | Thêm root mới tự chữa được |
| **Root hết hạn** | Có tác động tùy PKIX/trust-anchor processing và chính sách JDK | Mọi JVM đều thất bại đúng một thời điểm |
| **Cross-sign sang root mới** | Có thể xuất hiện một path hợp lệ mới | Root cũ tự được xóa ở mọi nơi |
| **Đổi thuật toán bị cấm** | Chứng chỉ/chuỗi có thể bị từ chối bởi security policy | Chắc chắn thiếu root |

Một PKIX implementation có thể kiểm tra revocation khi được cấu hình phù hợp. **Không mặc định rằng mọi Java TLS client đều tự kiểm tra CRL/OCSP theo cùng một chính sách**.

## 8. JDK security update còn thay đổi gì ngoài CA list?

Danh sách root CAs chỉ là một phần của TLS trust behavior.

Trong các JDK hiện đại, file `java.home/conf/security/java.security` có các security properties như:

- `jdk.certpath.disabledAlgorithms`: chặn thuật toán yếu hoặc keys không đạt tiêu chuẩn khi xây certificate path.
- `jdk.tls.disabledAlgorithms`: hạn chế TLS protocols/cipher suites và các tham số bảo mật.
- Các provider-specific settings và policies liên quan.

Vì vậy một endpoint có root A vẫn trong truststore nhưng sau update **vẫn** có thể bị từ chối vì SHA-1 usage, key length quá ngắn hoặc protocol quá cũ.

**Không sửa lỗi bằng cách xóa các algorithm constraints hoặc dùng accept-all TrustManager.** Nếu server dùng certificate/chain yếu, giải pháp là nâng certificate, key hoặc TLS configuration theo chính sách, không hạ bảo mật của client.

## 9. Ảnh hưởng đến những hệ thống Java khác nhau

| Loại ứng dụng | Thêm CA có thể làm gì? | Bỏ CA có thể làm gì? |
| --- | --- | --- |
| **HTTPS/REST Java client** | Chấp nhận thêm server chains hợp lệ | Mất HTTPS tới server không còn trust path |
| **Database/Kafka client dùng TLS** | Chấp nhận issuer mới nếu driver dùng truststore được cập nhật | Driver TLS handshake có thể thất bại |
| **Java HTTPS server, không mTLS** | Thường không đổi certificate/private key server tự trình | Không tự xóa identity key của server |
| **Java HTTPS server có mTLS** | Có thể chấp nhận thêm client CA chains | Có thể từ chối client cert trước đây tin cậy |
| **Private PKI nội bộ** | Hỗ trợ service/CA rotation | Có thể làm ngắt service dùng old CA |
| **Proxy TLS inspection** | Tin CA proxy thêm nếu chính sách chấp thuận | Có thể không chấp nhận proxy-issued certs |
| **Custom provider/TLS stack** | Có thể không chịu tác động | Có thể không chịu tác động |

**Server identity keystore** với private key khác **server truststore** dùng xác thực client ở mTLS. Đừng import CA vào nhầm store chỉ vì file có đuôi `.p12` hoặc `.jks`.

## 10. Kiểm tra JDK đang dùng và root certificates thực tế

Dùng chính Java launcher mà ứng dụng đang chạy:

```bash
java --version
java -XshowSettings:properties -version
```

Xem `java.home`, JDK vendor/build và các system properties. Trong Docker/Kubernetes, thực hiện **bên trong container image thật**, không chỉ trên host.

Để liệt kê mặc định `cacerts` của một JDK:

```bash
keytool -list -cacerts
```

Xem chi tiết:

```bash
keytool -list -v -cacerts
```

Để xem một alias đã xác định:

```bash
keytool -list -v -cacerts -alias actual-alias
```

Để kiểm tra một certificate file:

```bash
keytool -printcert -file verified-root.pem
```

**Cần đối chiếu SHA-256 fingerprint với kênh độc lập** trước khi thêm CA. Alias có thể khác giữa JDK versions/distributions, nên không dựa vào alias làm danh tính tuyệt đối.

### Kiểm tra truststore riêng

```bash
keytool -list -v \
  -keystore ./app-truststore.p12 \
  -storetype PKCS12
```

Nếu JDK/app dùng JSSE property:

```bash
java -Djavax.net.ssl.trustStore=/app/certs/app-truststore.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     -jar app.jar
```

Lệnh minh họa chỉ hoạt động nếu truststore file tồn tại và app thực sự dùng SunJSSE default trust context. **Không đặt mật khẩu thật trong dòng lệnh** khi có thể bị ghi vào shell history hoặc process metadata; dùng secret manager/password prompt/option-file bảo vệ phù hợp.

## 11. Thêm và xóa CA bằng keytool: chỉ trên kho được phê duyệt

Giả sử PKI admin đã xác minh root CA và lưu ở `verified-root.pem`. Thêm vào **truststore riêng**:

```bash
keytool -importcert \
  -alias partner-root-2026 \
  -file verified-root.pem \
  -keystore ./app-truststore.p12 \
  -storetype PKCS12
```

Lệnh hỏi password và có thể yêu cầu xác nhận certificate. Với production, đừng tự thêm `-noprompt` nếu chưa có quy trình **fingerprint verification tự động và phê duyệt**.

Xóa một alias khỏi store riêng:

```bash
keytool -delete \
  -alias partner-root-2026 \
  -keystore ./app-truststore.p12 \
  -storetype PKCS12
```

Trước khi xóa phải xác minh đúng alias, sao lưu store, kiểm tra candidate chains, các endpoint mTLS và chính sách bảo mật.

**Không nên sửa stock JDK `cacerts` thủ công trên production như thói quen.** Bản vá JDK, image rebuild, container restart có thể làm mất các thay đổi tự ý. Ưu tiên quản lý truststore riêng theo ứng dụng hoặc tạo custom image có version và kiểm soát provenance.

`keytool` cũng hỗ trợ `-cacerts` khi có quyền quản trị. Nhưng biết cú pháp **không đồng nghĩa** việc tùy tiện loại root CA được phép. Nếu root bị loại vì compromise, cần theo incident response, không import lại chỉ để tránh lỗi.

## 12. Bài thực hành Java 17+: tạo root CA và leaf certificate an toàn

Mục tiêu là **thấy chính xác ảnh hưởng của trust anchor**, không truy cập Internet, không sửa JDK cacerts và không chạy server công khai.

Dùng `keytool` tạo:

1. Root CA thử nghiệm.
2. Certificate máy chủ cho `localhost`.
3. CSR của máy chủ.
4. Root CA ký leaf certificate.
5. Chương trình Java dùng một `KeyStore` **trong bộ nhớ** để thêm và xóa CA.

Dùng một thư mục thử riêng, có JDK tools trong PATH. Ví dụ cho POSIX shell:

```bash
mkdir ca-trust-lab
cd ca-trust-lab

# 1. Tạo root CA thử nghiệm
keytool -genkeypair \
  -alias lab-root \
  -keystore root.p12 \
  -storetype PKCS12 \
  -storepass labtestpass123 \
  -keypass labtestpass123 \
  -keyalg RSA -keysize 2048 -validity 30 \
  -dname "CN=Demo Root CA,O=Study,C=US" \
  -ext "BC=ca:true" \
  -ext "KU=keyCertSign,cRLSign" \
  -noprompt

# 2. Export public root certificate
keytool -exportcert -rfc \
  -alias lab-root \
  -keystore root.p12 \
  -storepass labtestpass123 \
  -file root.pem

# 3. Tạo server key pair
keytool -genkeypair \
  -alias leaf \
  -keystore server.p12 \
  -storetype PKCS12 \
  -storepass labtestpass123 \
  -keypass labtestpass123 \
  -keyalg RSA -keysize 2048 -validity 30 \
  -dname "CN=localhost,O=Study,C=US" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -noprompt

# 4. Tạo CSR của server
keytool -certreq \
  -alias leaf \
  -keystore server.p12 \
  -storepass labtestpass123 \
  -file server.csr \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

# 5. Root CA ký leaf certificate
keytool -gencert \
  -alias lab-root \
  -keystore root.p12 \
  -storepass labtestpass123 \
  -infile server.csr \
  -outfile leaf.pem -rfc -validity 30 \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -ext "KU=digitalSignature,keyEncipherment" \
  -ext "EKU=serverAuth"
```

**Mật khẩu trong ví dụ chỉ dùng cho lab tạm thời và đã công khai; tuyệt đối không dùng làm password production.** Đây là các khóa và chứng chỉ giả lập, không phải root CA public thật.

Kiểm tra:

```bash
keytool -printcert -file root.pem
keytool -printcert -file leaf.pem
```

Trong lần chạy kiểm chứng, root có Subject/Issuer `CN=Demo Root CA, O=Study, C=US`, còn leaf có Issuer là root và SAN `localhost`. SHA-256 fingerprints là ngẫu nhiên theo keypair được tạo mới, không có một giá trị cố định cho mọi lần chạy.

## 13. Chương trình đầy đủ: RootCaChangeDemo.java

Tạo file **`RootCaChangeDemo.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public final class RootCaChangeDemo {
    static X509Certificate readCert(Path file) throws Exception {
        try (InputStream in = Files.newInputStream(file)) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }
    }

    static X509TrustManager trustManager(KeyStore trustStore) throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(trustStore);
        for (TrustManager manager : factory.getTrustManagers()) {
            if (manager instanceof X509TrustManager) {
                return (X509TrustManager) manager;
            }
        }
        throw new IllegalStateException("No X509TrustManager");
    }

    static boolean accepts(X509TrustManager manager, X509Certificate leaf) {
        try {
            manager.checkServerTrusted(new X509Certificate[] {leaf}, "RSA");
            return true;
        } catch (CertificateException | RuntimeException error) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: root.pem leaf.pem");
        }
        X509Certificate root = readCert(Path.of(args[0]));
        X509Certificate leaf = readCert(Path.of(args[1]));

        KeyStore store = KeyStore.getInstance("PKCS12");
        store.load(null, null);

        X509TrustManager before = trustManager(store);
        System.out.println("initialRootCount=" + store.size());
        System.out.println("beforeAddAccepted=" + accepts(before, leaf));

        store.setCertificateEntry("lab-root", root);
        X509TrustManager afterAdd = trustManager(store);
        System.out.println("afterAddRootCount=" + store.size());
        System.out.println("afterAddAccepted=" + accepts(afterAdd, leaf));

        store.deleteEntry("lab-root");
        X509TrustManager afterRemoval = trustManager(store);
        System.out.println("afterRemoveRootCount=" + store.size());
        System.out.println("afterRemoveAccepted=" + accepts(afterRemoval, leaf));
        System.out.println("previousManagerStillAccepts=" + accepts(afterAdd, leaf));
    }
}
```

Biên dịch/chạy trong thư mục lab có `root.pem` và `leaf.pem`:

```bash
javac --release 17 RootCaChangeDemo.java
java RootCaChangeDemo root.pem leaf.pem
```

**Stdout chính xác đã được kiểm chứng** trên HotSpot JDK hiện đại với bộ keytool-generated certificates theo bước 12:

```text
initialRootCount=0
beforeAddAccepted=false
afterAddRootCount=1
afterAddAccepted=true
afterRemoveRootCount=0
afterRemoveAccepted=false
previousManagerStillAccepts=true
```

### Giải thích từng dòng

- **initialRootCount=0:** truststore mới trong bộ nhớ chưa có CA nào.
- **beforeAddAccepted=false:** trust manager tạo từ store rỗng không tin leaf do root thử nghiệm ký.
- **afterAddRootCount=1:** root certificate được thêm vào store.
- **afterAddAccepted=true:** trust manager được **khởi tạo lại** với root mới chấp nhận leaf.
- **afterRemoveRootCount=0:** xóa certificate entry khỏi store.
- **afterRemoveAccepted=false:** trust manager **mới tạo sau khi xóa** không còn tin leaf.
- **previousManagerStillAccepts=true:** trust manager **cũ**, đã khởi tạo trước lúc xóa, vẫn tin leaf trong thí nghiệm.

Dòng cuối cho thấy một rủi ro vận hành: **sửa file/truststore không tự động làm mọi `X509TrustManager` hoặc `SSLContext` hiện có đọc lại CA list**.

### Giới hạn quan trọng của demo

Demo chỉ gọi:

```java
manager.checkServerTrusted(new X509Certificate[] {leaf}, "RSA");
```

để kiểm chứng **trust decision của SunJSSE X509TrustManager**. Nó **không tự kiểm tra hostname/SAN**, không mở TLS socket, không đo negotiation và không kiểm chứng revocation hoặc Certificate Transparency.

Đây **không phải template để ứng dụng bỏ qua hostname verification**. HTTPS client thật vẫn phải dùng endpoint identification, chain/path validation và những security checks thích hợp.

## 14. Khi đổi truststore, JVM đang chạy có cập nhật ngay không?

Không có lời hứa chung rằng việc thay một file trên đĩa sẽ lập tức thay mọi SSLContexts/trust managers đang tồn tại.

Một ứng dụng có thể:

- Tạo `SSLContext` lúc startup rồi dùng nhiều giờ.
- Tạo `TrustManagerFactory` từ truststore một lần.
- Duy trì TLS connections hoặc session cache.
- Có framework tự reload certificates, nhưng phải xem tài liệu version đó.
- Dùng Docker image mới trong khi pods cũ vẫn chạy trên image/JDK cũ.

Vì vậy có thể xảy ra:

```text
Disk truststore: root A removed
Running old TrustManager: still trusts A
Newly initialized TrustManager: no longer trusts A
```

**Thực hành vận hành:** có version truststore, rollout/restart hoặc reinitialize TLS state theo contract của framework; kiểm tra số process cũ còn tồn tại và kết nối/session đang sử dụng.

Nếu CA bị loại do **sự cố bảo mật**, việc quản lý tiến trình cũ và TLS sessions là yêu cầu quan trọng; không thể tuyên bố đã giải quyết chỉ vì một file `cacerts` mới có ít entry hơn.

## 15. Chẩn đoán lỗi TLS sau khi nâng JDK

### PKIX path building failed

Các nguyên nhân có thể:

- Root CA cần thiết thiếu trong effective truststore.
- Intermediate certificate cần thiết không được gửi hoặc path builder không tìm được.
- Explicit trustStore path sai/không tồn tại.
- Root bị loại, CA rotation chưa hoàn tất hoặc alternate chain chưa sẵn sàng.
- Security policies hoặc custom providers ảnh hưởng path building.

**Không kết luận chỉ từ chữ PKIX rằng vấn đề chắc chắn do CA removal.**

### Certificate expired hoặc not yet valid

Có thể là leaf/intermediate hết hạn hoặc đồng hồ hệ thống lệch. Không nên thêm root tùy tiện để chữa một vấn đề về thời gian/certificate renewal.

### Hostname mismatch

Certificate không có SAN cho host được gọi. Chỉnh certificate hoặc URL; **không tắt hostname verification**.

### Algorithm constraints

Một thuật toán chữ ký hoặc key length có thể bị JDK mới chặn. Kiểm tra `jdk.certpath.disabledAlgorithms`, `jdk.tls.disabledAlgorithms` và hướng dẫn hiện hành của JDK vendor; phối hợp server owner thay keys/certificates.

### mTLS identity failure

Nếu server yêu cầu client authentication, cần xem **client private key/certificate chain** và **server truststore** dùng validate client. Không nhầm client truststore với mTLS identity store.

## 16. Bật logging khi cần, nhưng không lạm dụng

Với SunJSSE trong một môi trường được kiểm soát:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
```

Với CertPath debugging:

```bash
java -Djava.security.debug=certpath -jar app.jar
```

Tùy JDK/provider, logs có thể cho biết:

- Truststore đã chọn.
- Certificate chain/issuers/trust anchors được xem xét.
- Thông tin lỗi xác thực và những algorithm constraints.
- Có một handshake nào bị từ chối vì trust hay protocol.
- Những trạng thái TLS giúp phân biệt root issue với transport issue.

**Debug logs có thể chứa thông tin nhạy cảm** như hostname, certificate chains, session details và gây CPU/I/O overhead. Chỉ bật đủ thời gian, quản lý quyền xem và tắt sau khi chẩn đoán.

Không dùng `-Dcom.sun.net.ssl.checkRevocation=false` hoặc hạ security properties chỉ để làm lỗi biến mất. Với một yêu cầu bảo mật, thay chain/CA/keys phù hợp là lựa chọn an toàn hơn.

## 17. Đánh giá rủi ro khi thêm hoặc xóa CA

### Thêm CA public mới

Ưu điểm: client có thể kết nối tới endpoint chuyển sang CA mới.

Rủi ro: trust boundary mở rộng; CA mới có thể cấp certificates cho nhiều host trong phạm vi cho phép.

Biện pháp: CA được phê duyệt, SHA-256 fingerprint kiểm chứng, giới hạn phạm vi truststore ở application khi khả thi, lưu log thay đổi và test negative cases.

### Xóa CA cũ

Ưu điểm: bỏ trust anchor không còn được đánh giá an toàn.

Rủi ro: các endpoints vẫn phụ thuộc root đó có thể mất kết nối. Với mTLS, server có thể từ chối client certs từ CA đó.

Biện pháp: thống kê dependencies, xây migration/alternate chain, triển khai CA mới trước khi chuyển nếu chính sách cho phép, rồi xóa root cũ có kiểm soát.

### Xóa CA do compromise

**Khác với rotation thông thường:** nếu CA đã bị rút vì sự cố bảo mật, không nên kéo dài trust chỉ để giữ ứng dụng hoạt động. Thực hiện theo incident response, chuyển sang CA và chain đáng tin; tránh rollback một security removal mà chưa có phê duyệt.

## 18. Rolling upgrade theo nguyên tắc ít gián đoạn

Với CA rotation đã được phê duyệt và không có sự cố compromise:

1. **Phân tích chain hiện hành** của tất cả endpoint liên quan.
2. **Xác minh root CA mới** bằng fingerprint độc lập.
3. **Tạo truststore mới** hoặc chọn JDK version có root mới.
4. **Deploy tới staging** và chạy integration tests.
5. Nếu cần, duy trì tạm **A và B** trong quá trình endpoint chuyển đổi.
6. **Chuyển server leaf/intermediate chain** sang đường có root B.
7. **Kiểm tra hết các pods/regions** và các clients dùng JDK image cũ.
8. **Loại A** sau khi ứng dụng không còn cần và policy cho phép.
9. **Khởi tạo lại trust managers/restart** theo contract để tránh trust state cũ.
10. **Theo dõi SSLHandshakeException, error rates và readiness** sau rollout.

Không nên thay cả JDK, CA, cipher suite, cert issuer và truststore cùng một lúc rồi không thể phân biệt nguyên nhân lỗi.

## 19. Docker/Kubernetes: CA có thể khác giữa pods

Các pods Java có thể dùng:

- JDK vendor hoặc update build khác nhau.
- Base image Linux khác nhau.
- Custom truststore được mount bằng Secret/ConfigMap.
- JDK `cacerts` có bản nội dung khác do Dockerfile tạo.
- `jssecacerts` riêng.
- TLS client library có TrustManager chuyên biệt.

Vì vậy staging HTTPS thành công **không chứng minh** production cũng thành công.

Kiểm tra trong container đang chạy:

```bash
java --version
keytool -list -cacerts
```

Nếu app có:

```text
-Djavax.net.ssl.trustStore=/app/certs/truststore.p12
```

phải kiểm tra file đó và nguồn cung cấp nó. Một ConfigMap/Secret mount có thể che bản `cacerts` mới của image. Thay đổi volume không bảo đảm SSLContexts đang chạy tự reload.

**Đừng sửa trực tiếp file trong pod đang chạy** như giải pháp bền vững. Sử dụng truststore artifact được quản lý, image build pipeline và rolling deployment được kiểm thử.

## 20. Những sai lầm cần tránh

**1.** “Thấy PKIX path building failed, cứ import leaf từ server vào cacerts.” Sai; phải xác minh trust chain/issuer, CA thật và nguyên nhân.

**2.** “Có self-signed root certificate nghĩa là nó đáng tin.” Sai; trust là quyết định của policy/truststore.

**3.** “Browser mở được thì JVM chắc chắn mở được.” Sai; truststores/providers có thể khác.

**4.** “Cùng Subject CA thì chắc chắn cùng public key.” Sai; dùng SHA-256 fingerprint/provenance.

**5.** “JDK nâng cấp không bao giờ thay CA root list.” Sai; đây là dữ liệu security được bảo trì.

**6.** “Xóa root trong cacerts luôn làm mọi endpoint liên quan thất bại.” Sai; có custom store, alternate chain và manager cũ.

**7.** “Xóa root trong truststore tức thu hồi mọi certificate.” Sai; removal khác revocation.

**8.** “CA mới được thêm là hostname verification tự động đạt.” Sai; SAN/host là bước riêng.

**9.** “Thêm root mới sửa được leaf hết hạn.” Sai; cần certificate hợp lệ.

**10.** “Thêm root mới sửa được TLS version hoặc algorithm disabled.” Sai; kiểm tra riêng.

**11.** “Explicit trustStore sai path tự fallback cacerts.” Sai với SunJSSE default described behavior.

**12.** “jssecacerts được JSSE tự gộp cùng cacerts.” Sai; thứ tự chọn có ưu tiên.

**13.** “Sửa file truststore làm mọi X509TrustManager cập nhật tức thì.” Sai; demo cho thấy old manager giữ trust state.

**14.** “Nâng image JDK đồng nghĩa các pods cũ tự đổi runtime.” Sai; cần rollout/restart.

**15.** “Accept-all TrustManager là cách sửa TLS ở production.” Không an toàn, tăng nguy cơ MITM.

**16.** “Tắt hostname verification là tối ưu cho API nội bộ.” Không an toàn.

**17.** “Import CA của proxy TLS interception không làm tăng quyền tin cậy.” Sai; đây là thay đổi nhạy cảm.

**18.** “Một alias tương đương một certificate trên mọi JDK vendor.” Sai; alias naming khác nhau.

**19.** “Hồi sinh root bị xóa do sự cố bảo mật là cách rollback hợp lý mặc định.” Không; cần incident-response approval.

**20.** “JDK cacerts thay đổi là đủ, không cần test mTLS.” Sai; server/client trust directions khác nhau.

**21.** “TrustManager.checkServerTrusted kiểm tra hostname như HTTPS client.” Không; demo không thực hiện endpoint identification.

**22.** “Bật debug trustmanager mãi mãi không tốn tài nguyên.” Sai; debug có overhead và có thể lộ dữ liệu nhạy cảm.

## 21. Checklist QA trước và sau CA update

- [ ] Đã xác nhận JDK vendor, version/build, runtime image và `java.home`.
- [ ] Đã xác định effective truststore (explicit, jssecacerts, cacerts hoặc custom).
- [ ] Đã phân biệt identity keystore với truststore cho peer authentication.
- [ ] Đã kiểm tra các CA thực sự thêm/bớt qua SHA-256 fingerprints.
- [ ] Đã đọc release notes và security updates của JDK vendor.
- [ ] Root mới đã được xác minh từ nguồn đáng tin và được phê duyệt.
- [ ] Không import ngẫu nhiên leaf hoặc self-signed cert từ endpoint lỗi.
- [ ] Đã đánh giá trust boundary mở rộng khi thêm CA.
- [ ] Đã xem cross-signed alternate chains khi loại CA.
- [ ] Đã kiểm tra leaf/intermediate, thời hạn, SAN và algorithm constraints.
- [ ] Đã kiểm thử mTLS nếu ứng dụng xác thực client certificates.
- [ ] Đã kiểm thử trên JDK/container image thật của staging và production.
- [ ] Có phương án chuyển tiếp CA khi không có security incident.
- [ ] Khi là security incident, không kéo dài trust chỉ vì tránh lỗi.
- [ ] Có versioning/backup của truststore và audit log thay đổi.
- [ ] Có kế hoạch restart/reinitialize SSLContext hoặc TrustManager.
- [ ] Đã kiểm tra pods/processes cũ và TLS sessions có thể còn trust state cũ.
- [ ] Đã theo dõi TLS error rate, SSLHandshakeException và endpoint health.
- [ ] Không hạ thấp TLS/certpath security properties để né lỗi.
- [ ] Không tắt hostname verification và không dùng trust-all.
- [ ] Đã tắt diagnostic logging chi tiết sau khi sử dụng.
- [ ] Có rollback hợp lệ với policy bảo mật, không phục hồi root bị rút tùy tiện.

## 22. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** JEP nào đưa bộ root CA certificates mặc định vào OpenJDK từ Java 10?

**Đáp án:** **JEP 319 — Root Certificates**.

**Câu 2.** Root CA có phải tự tin cậy chỉ vì self-signed không?

**Đáp án:** Không. Nó chỉ là trust anchor khi được đưa vào store/policy tin cậy.

**Câu 3.** Thêm root B có làm mọi HTTPS chain dưới B thành công ngay không?

**Đáp án:** Không. Leaf/intermediate, SAN, validity, thuật toán và các điều kiện TLS khác vẫn phải hợp lệ.

**Câu 4.** Xóa root A khỏi cacerts có xóa leaf trên server không?

**Đáp án:** Không. Nó chỉ xóa trust anchor khỏi store đó.

**Câu 5.** Nếu root A bị bỏ, nhưng có một cross-signed path tới root B, endpoint còn có thể kết nối được không?

**Đáp án:** Có thể, nếu path và constraints đều hợp lệ.

**Câu 6.** Tại sao cập nhật cacerts không tác động app dùng custom truststore?

**Đáp án:** Vì app không lấy trust anchors từ cacerts đó.

**Câu 7.** SunJSSE mặc định ưu tiên jssecacerts hay cacerts?

**Đáp án:** `jssecacerts`, khi không có explicit trustStore property.

**Câu 8.** Nếu explicit trustStore path không tồn tại, JVM có mặc nhiên dùng cacerts không?

**Đáp án:** Không theo SunJSSE reference implementation; trust material có thể rỗng.

**Câu 9.** Vì sao xác minh SHA-256 fingerprint quan trọng hơn tên Subject?

**Đáp án:** Chủ thể có thể bị giả danh hoặc trùng tên; fingerprint nhận diện nội dung certificate cần đối chiếu với nguồn tin cậy.

**Câu 10.** Demo sau khi thêm root có stdout gì tại afterAddAccepted?

**Đáp án:** `afterAddAccepted=true`.

**Câu 11.** Sau khi xóa root khỏi KeyStore và tạo manager mới, kết quả là gì?

**Đáp án:** `afterRemoveAccepted=false`.

**Câu 12.** Vì sao previousManagerStillAccepts=true có thể xảy ra?

**Đáp án:** Manager cũ đã nạp trust state khi root vẫn có mặt và không được bảo đảm tự reload.

**Câu 13.** checkServerTrusted trong demo đã verify localhost hostname chưa?

**Đáp án:** Chưa. Đó là thử nghiệm chain trust, không thay toàn bộ HTTPS handshake.

**Câu 14.** Certificate revocation có đồng nghĩa root removal không?

**Đáp án:** Không. Revocation policy/CRL/OCSP và việc xóa trust anchor là hai thứ khác nhau.

**Câu 15.** Root vẫn còn nhưng JDK mới chặn thuật toán yếu thì kết nối có thể lỗi không?

**Đáp án:** Có. `jdk.certpath.disabledAlgorithms` và `jdk.tls.disabledAlgorithms` được áp dụng độc lập.

**Câu 16.** Có nên tắt hostname verification để phục hồi kết nối?

**Đáp án:** Không. Cần sửa certificate SAN hoặc endpoint URL phù hợp.

**Câu 17.** Vì sao phải test trên Docker image cuối thay vì laptop?

**Đáp án:** JDK/vendor, cacerts, custom store và configuration có thể khác.

**Câu 18.** Khi CA bị rút vì compromise, có nên tự import lại để giữ uptime không?

**Đáp án:** Không. Cần xử lý theo incident response và chọn một trust path an toàn.

**Câu 19.** Trong mTLS, client identity keystore và truststore có khác nhau không?

**Đáp án:** Có. Identity store chứa private key/client cert; truststore chứa anchors dùng validate peer.

**Câu 20.** Làm sao chứng minh CA update hoàn tất trong hệ thống nhiều pods?

**Đáp án:** Các pods/processes đã dùng trust config mới, integration tests qua đúng endpoints pass, metrics ổn định, root bị loại không còn được tin trái chính sách và TLS state cũ đã được xử lý.

## 23. Nguồn tài liệu chính thức còn áp dụng

1. [Oracle JDK 10 Release Notes — JEP 319 Root Certificates](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): cột mốc OpenJDK có root CAs mặc định.
2. [OpenJDK JEP 319 — Root Certificates](https://openjdk.org/jeps/319): mục tiêu đưa tập root CA tin cậy vào OpenJDK.
3. [Oracle Java SE 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): effective truststore order, TrustManager và TLS certificate handling.
4. [Oracle Java SE 25 — keytool Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html): `-list`, `-printcert`, `-importcert`, `-delete`, `-cacerts` và xác thực fingerprint.
5. [Oracle Java SE 25 — Security Updates](https://docs.oracle.com/en/java/javase/25/migrate/security-updates.html): ví dụ security/CA removals theo JDK releases.
6. [Oracle Java SE 25 — Security Properties File](https://docs.oracle.com/en/java/javase/25/security/security-properties-file.html): thuật toán/certificate path/TLS restrictions.
7. [Java SE 25 — X509TrustManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509TrustManager.html): hợp đồng kiểm tra peer certificate.
8. [Java SE 25 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust managers từ trusted material.
9. [Java SE 25 — KeyStore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html): quản lý trusted certificate entries.
10. [Oracle Java SE 27 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): đối chiếu phiên bản Java mới.
11. [Oracle Java SE 25 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/25/security/java-pki-programmers-guide.html): PKIX cert paths và anchors.

**Kết luận:** việc JDK bổ sung hoặc loại bỏ root CAs **có thể thay đổi tập TLS certificate chains mà ứng dụng Java tin cậy**. Tuy nhiên tác động phụ thuộc truststore thực tế, đường chứng chỉ/cross-signing, thuật toán bảo mật, SSLContexts đã khởi tạo và sự khác biệt giữa các JDK/container images. Hãy kiểm tra đúng trust material, xác thực SHA-256 fingerprints, thử nghiệm qua các endpoint thật, rollout có kiểm soát và **không tắt kiểm tra TLS chỉ để làm kết nối thành công**.
