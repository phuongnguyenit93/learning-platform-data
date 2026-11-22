# Thuật toán và kích thước khóa không còn được chấp nhận

Trong một đợt **Java Advance Compatibility Migration**, ứng dụng có thể biên dịch thành công và khởi động bình thường nhưng vẫn thất bại ở bước kết nối HTTPS, xác thực certificate chain, kiểm tra chữ ký JAR hoặc thực hiện mật mã với khóa đã tạo nhiều năm trước. Nguyên nhân không nhất thiết là Java API bị xóa. Một số **thuật toán, giao thức hoặc kích thước khóa không còn được chính sách bảo mật của JDK chấp nhận trong ngữ cảnh sử dụng cụ thể**.

Những giới hạn này là biện pháp an toàn có chủ đích. Việc xử lý đúng không phải xóa toàn bộ ràng buộc bảo mật để chương trình chạy như cũ, mà là xác định chính sách nào đã từ chối thao tác, thay thế certificate/key/protocol không phù hợp và kiểm thử lại trên runtime mục tiêu.

Bài học giải thích cách JDK quản lý thuật toán và độ dài khóa, các điểm giao nhau giữa TLS, PKIX, JAR signing và JCA/JCE, cách chẩn đoán lỗi khác nhau và quy trình migration bảo toàn bảo mật.

## 1. Tại sao đổi JDK làm hệ thống mật mã ngừng hoạt động?

Kết quả của một phép toán bảo mật phụ thuộc nhiều tầng:

- **JDK vendor và release/update:** cấu hình mặc định có thể thay đổi cả giữa các bản vá cùng dòng LTS.
- **Security provider:** SunJSSE, SunEC, SunRsaSign hoặc nhà cung cấp bên ngoài/HSM quyết định thuật toán được triển khai.
- **Security properties:** một thuật toán có thể bị vô hiệu hóa hoặc bị giới hạn theo mục đích và kích thước khóa.
- **Certificate chain và key material:** certificate có thể có chữ ký yếu, khóa ngắn, hết hạn hoặc bị mất trust anchor.
- **Đầu bên kia của kết nối:** server, load balancer, API gateway, thiết bị mạng hoặc client cũ chỉ hỗ trợ giao thức/cipher đã lỗi thời.
- **Cách đóng gói runtime:** custom image, truststore, modules, PKCS#11 provider và native libraries có thể khác giữa build và production.

Ví dụ: client Java cũ từng giao tiếp với một thiết bị chỉ chấp nhận TLS 1.0. Khi JDK mới không cho sử dụng giao thức này, lời gọi ứng dụng không thay đổi nhưng handshake thất bại. Hoặc server vẫn dùng certificate RSA 1024 bit, khiến client mới từ chối certificate path theo policy đang có hiệu lực.

**Không suy đoán chính sách từ tên phiên bản JDK đơn thuần.** Mốc vô hiệu hóa thuật toán có thể được đưa vào các bản cập nhật JDK 8, 11, 17 và những release khác; vendor cũng có thể tùy chỉnh defaults.

## 2. Các thuật ngữ dễ nhầm

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Giao thức | SSLv3, TLS 1.0, TLS 1.1, TLS 1.2, TLS 1.3 | Hai bên phải đàm phán được phiên bản được phép |
| Cipher suite | TLS suite dùng AES-GCM, ChaCha20-Poly1305 hoặc thuật toán cũ | Phải được cả hai phía và security policy chấp nhận |
| Thuật toán khóa công khai | RSA, DSA, EC | Xác định mô hình khóa và chữ ký |
| Kích thước khóa | RSA 1024/2048/3072 bit, EC P-256 | Không đạt policy có thể làm xác thực/ký thất bại |
| Thuật toán chữ ký | SHA1withRSA, SHA256withRSA, SHA384withECDSA | Gắn digest với cơ chế chữ ký |
| Digest/hash | SHA-1, SHA-256, SHA-384 | Hỗ trợ ở API không đồng nghĩa được phép trong certificate/JAR |
| Mật mã đối xứng | AES, 3DES, RC4 | Mode/key size/thuật toán có thể không còn đáp ứng chuẩn |
| Security provider | SunJSSE, SunRsaSign, SunEC, PKCS#11 | Cung cấp implementation và các khả năng tương ứng |

### 2.1. Không so sánh số bit giữa các thuật toán khác loại

Khóa RSA 256 bit, AES 256 bit và EC P-256 không cùng mức bảo mật chỉ vì đều có số 256.

- RSA 1024 bit bị coi là yếu cho nhiều mục đích hiện đại.
- RSA 2048 bit là ngưỡng cơ sở thường thấy, nhưng có chính sách yêu cầu mức cao hơn hoặc vòng đời ngắn hơn.
- RSA 3072 bit có thể phù hợp khi cần mức bảo vệ dài hạn hơn, tùy chi phí và khả năng tương tác.
- P-256/P-384 thuộc elliptic-curve cryptography và phải đánh giá theo tính chất hệ mật mã đó.
- AES 128/256 bit được đánh giá theo mô hình mật mã đối xứng.

Chọn khóa theo yêu cầu bảo mật của tổ chức, tiêu chuẩn áp dụng và khả năng hỗ trợ của HSM, server, client và certificate authority (CA), không dựa vào một con số tuyệt đối.

### 2.2. Thuật toán bị từ chối khác thuật toán không tồn tại

`NoSuchAlgorithmException` thường liên quan đến tên thuật toán sai hoặc provider không có implementation phù hợp. Trong khi đó, thông báo dạng `Algorithm constraints check failed` cho biết một thao tác đang bị ràng buộc bởi chính sách của ngữ cảnh cụ thể.

`InvalidKeyException` cũng có thể xuất hiện vì key/parameters sai, key size không được phép, provider không hỗ trợ hoặc quy tắc JCE. Không nên xử lý tất cả bằng cách bổ sung JAR provider.

## 3. Các thuộc tính bảo mật của JDK

Các JDK hiện đại có file cấu hình `java.security`, thường ở thư mục `conf/security` của JDK/runtime image. Đường dẫn và giá trị phải được xác minh trên bản JDK đang chạy.

| Security property | Phạm vi điển hình |
|---|---|
| `jdk.tls.disabledAlgorithms` | Các thuật toán, protocol và ràng buộc TLS/JSSE |
| `jdk.certpath.disabledAlgorithms` | Ràng buộc thuật toán và key size khi xác thực certificate path |
| `jdk.jar.disabledAlgorithms` | Ràng buộc trong JAR signature verification |
| `jdk.security.legacyAlgorithms` | Thuật toán được xem là legacy trong một số công cụ; không đồng nghĩa bị cấm ở mọi ngữ cảnh |
| `crypto.policy` | Chính sách độ mạnh mật mã JCE, khác với disabled algorithms ở trên |

Các giá trị có thể chứa tên thuật toán và điều kiện, ví dụ cú pháp minh họa:

```text
RSA keySize < 2048
```

Đây **không phải khẳng định mặc định của mọi JDK 17 là ngưỡng này**. Một số quy tắc còn phụ thuộc mục đích sử dụng, điều kiện trust anchor hoặc mốc thời gian. Luôn đọc policy thực tế.

### 3.1. Đọc policy có hiệu lực

```java
import java.security.Security;

public final class SecurityPolicySnapshot {
    public static void main(String[] args) {
        print("jdk.tls.disabledAlgorithms");
        print("jdk.certpath.disabledAlgorithms");
        print("jdk.jar.disabledAlgorithms");
        print("jdk.security.legacyAlgorithms");
        print("crypto.policy");
    }

    private static void print(String name) {
        System.out.println(name + " = " + Security.getProperty(name));
    }
}
```

Chạy với đúng JDK của ứng dụng:

```bash
javac SecurityPolicySnapshot.java
java SecurityPolicySnapshot
```

Nên lưu bản snapshot cùng thông tin vendor, full version, runtime image và môi trường triển khai để so sánh trước/sau migration.

### 3.2. `disabledAlgorithms` không có nghĩa cấm tuyệt đối ở mọi API

`MessageDigest.getInstance("SHA-1")` vẫn có thể tìm được implementation SHA-1, nhưng certificate path validator có thể từ chối một chữ ký SHA-1 theo quy tắc riêng. Tương tự, JCA có thể hỗ trợ RSA trong khi certificate RSA quá ngắn bị từ chối trong TLS.

**Algorithm availability** (có implementation) khác **algorithm acceptability** (được policy chấp nhận trong một nghiệp vụ bảo mật). Kiểm tra provider không thay thế kiểm tra PKIX, TLS hoặc JAR signing.

### 3.3. Không sửa file bảo mật toàn cục để né một lỗi

Thay đổi security property của một JDK image có thể ảnh hưởng mọi ứng dụng dùng chung runtime. Tắt constraints toàn cục để một endpoint legacy kết nối được sẽ mở rộng rủi ro sang các endpoint khác.

Định hướng là thay thế protocol, certificate, key hoặc hệ thống đối tác lỗi thời. Mọi ngoại lệ bất khả kháng phải có chủ sở hữu, đánh giá rủi ro, phạm vi cô lập và hạn chót loại bỏ.

## 4. Giao thức TLS không còn được chấp nhận

### 4.1. TLS 1.0 và TLS 1.1

TLS 1.0 và TLS 1.1 đã lỗi thời. Các bản cập nhật JDK mới vô hiệu hóa chúng theo mặc định trong nhiều cấu hình JSSE. Trong kế hoạch migration, nên ưu tiên TLS 1.2 hoặc TLS 1.3.

Nếu server chỉ hỗ trợ giao thức cũ, ứng dụng có thể báo:

```text
javax.net.ssl.SSLHandshakeException:
  Received fatal alert: protocol_version
```

hoặc:

```text
No appropriate protocol
(protocol is disabled or cipher suites are inappropriate)
```

Các thông báo này chưa đủ để xác định toàn bộ nguyên nhân: còn cần xem giao thức được đề xuất ở hai bên, cipher suites, security policy và thiết bị trung gian.

### 4.2. Cipher suites cũng phải tương thích

Hai bên cùng hỗ trợ TLS 1.2 vẫn có thể không bắt tay thành công nếu không có bộ thuật toán được cả hai chấp nhận. Thiết bị cũ chỉ hỗ trợ RC4, 3DES hoặc key exchange lỗi thời có thể không làm việc được với client JDK mới.

Một số lựa chọn hiện đại thường sử dụng AEAD như AES-GCM hoặc ChaCha20-Poly1305, nhưng cipher suite thực tế còn phụ thuộc protocol, provider, compliance policy và phần cứng.

Không nên xem danh sách cipher suites rộng hơn là mặc nhiên tốt hơn; mục tiêu là **tập lựa chọn an toàn và tương tác được**.

### 4.3. Chỉ bật protocol trong code không đủ

```java
sslSocket.setEnabledProtocols(new String[] {"TLSv1.2"});
```

Cấu hình này không vượt qua ràng buộc của `jdk.tls.disabledAlgorithms`. Tương tự, yêu cầu một cipher suite không có nghĩa runtime sẽ dùng được nó nếu provider hoặc security policy đã từ chối.

### 4.4. mTLS chịu ràng buộc hai chiều

Với mutual TLS, server và client đều cần certificate/key phù hợp. Một client certificate có thuật toán chữ ký hoặc độ dài khóa không hợp lệ có thể làm handshake thất bại dù certificate của server đạt chuẩn.

Khi nâng JDK, cần kiểm tra cả hai chiều:

- Certificate/key của server.
- Certificate/key của client.
- CA và truststore hai phía.
- Key usage, extended key usage và certificate aliases.
- Signature schemes, supported groups và cipher suites.

## 5. Certificate path validation và độ dài khóa

### 5.1. Kiểm tra cả chuỗi, không chỉ leaf

```text
Leaf certificate (api.example.com)
       |
       v
Intermediate CA
       |
       v
Root CA / trust anchor
```

Một certificate leaf mới có khóa đủ mạnh nhưng intermediate dùng thuật toán chữ ký yếu vẫn có thể gây lỗi, tùy ràng buộc cụ thể.

Thông báo có thể gồm:

```text
javax.net.ssl.SSLHandshakeException:
  PKIX path validation failed
```

và sâu hơn:

```text
java.security.cert.CertPathValidatorException:
  Algorithm constraints check failed ...
```

Cần đọc nested cause và xem phần nào trong chain thực sự bị từ chối.

### 5.2. SHA-1 bị hạn chế theo ngữ cảnh

SHA-1 không còn phù hợp cho nhiều mục đích chữ ký mới. Tuy nhiên, ràng buộc trong `jdk.certpath.disabledAlgorithms` có thể áp dụng điều kiện riêng liên quan trust anchor hoặc usage. Không nên khẳng định mọi certificate SHA-1 đều bị từ chối tuyệt đối trong mọi Java 17.

Cần xem:

1. Thuật toán chữ ký của leaf và intermediate.
2. Public key algorithm/key size của từng certificate.
3. Trust anchor và certificate usage.
4. Giá trị policy trên JDK mục tiêu.
5. Full exception chain khi xác thực.

Mục tiêu lâu dài là cấp lại certificate chain đáp ứng chính sách của tổ chức và khả năng tương tác của client.

### 5.3. Truststore không thay thế policy

Import một certificate vào truststore không tự động làm thuật toán hoặc key size của nó đạt chuẩn. Trust decision và algorithm constraints là các lớp kiểm soát khác nhau.

Các lỗi cần phân biệt:

- CA không được tin cậy.
- Server gửi thiếu intermediate.
- Certificate hết hạn hoặc chưa có hiệu lực.
- Subject Alternative Name không khớp hostname.
- Certificate/key usage không đúng mục đích.
- Thuật toán hoặc key size vi phạm policy.

Đổi key size không sửa được một hostname mismatch; thêm trust anchor không nhất thiết sửa được một algorithm constraint.

## 6. RSA, DSA và EC: key size phải phù hợp từng loại

### 6.1. RSA 1024 bit trong hệ thống legacy

RSA 1024 bit thường xuất hiện trong những certificate/keystore được tạo nhiều năm trước, ví dụ server nội bộ, thiết bị gateway, client mTLS, JAR signer hoặc HSM token chưa được rotate.

Trong nhiều chính sách hiện đại, khóa này không đạt ngưỡng. Cách sửa là **tạo key pair mới và cấp lại certificate**, không phải đổi một thuộc tính metadata.

Quy trình gồm xác định owner, chọn key algorithm/size, tạo khóa mới trong kho an toàn, xin certificate mới từ CA, triển khai full chain và kiểm tra toàn bộ client còn được hỗ trợ.

### 6.2. RSA 2048/3072 hoặc ECDSA

Một số chiến lược phổ biến:

- RSA 2048 bit cho các hệ thống có chính sách cho phép và thời hạn phù hợp.
- RSA 3072 bit khi cần dư địa bảo mật cao hơn, tùy khả năng tương tác.
- ECDSA trên một named curve được hỗ trợ rộng như P-256/P-384, nếu server/client/HSM và certificate chain phù hợp.

Không chuyển từ RSA sang ECDSA bằng cách chỉ đổi cấu hình JDK; cần cập nhật key, certificate, signature scheme, TLS stack và kiểm thử client legacy.

### 6.3. DSA và provider khác nhau

Một số ứng dụng cũ sử dụng DSA hoặc provider đặc thù. Cần xem loại thuật toán, kích thước khóa, tham số và ngữ cảnh dùng. Một thuật toán có thể còn được triển khai nhưng không phù hợp để ký certificate mới.

Trường hợp HSM/PKCS#11 còn phụ thuộc native driver, token policy và cơ chế ký được thiết bị hỗ trợ. Kiểm thử bằng software provider trên laptop chưa chứng minh HSM production tương thích.

### 6.4. AES/JCE policy là chủ đề riêng

Các JDK lịch sử từng có giới hạn độ mạnh JCE ở một số cấu hình. Các JDK hiện đại thường có hỗ trợ strong cryptography rộng hơn; khi gặp `InvalidKeyException: Illegal key size`, cần đọc `crypto.policy`, provider và runtime thực tế.

AES-256 không nên được đánh giá theo cùng con số hoặc cùng ràng buộc như RSA 2048. Đừng hạ độ dài khóa hoặc đổi sang thuật toán yếu hơn trước khi xác định lỗi thật.

## 7. Chữ ký JAR và `jdk.jar.disabledAlgorithms`

Một JAR có thể đã được ký từ rất lâu bằng digest hoặc signature algorithm lỗi thời. Khi nâng JDK, công cụ xác minh có thể cảnh báo hoặc xử lý chữ ký không còn đáp ứng policy.

### 7.1. Xác minh JAR

```bash
jarsigner -verify -verbose -certs release.jar
```

Trong CI có thể dùng:

```bash
jarsigner -verify -strict -verbose -certs release.jar
```

Kiểm tra exit code và output, bao gồm warning về thuật toán yếu, certificate signer, timestamp, key size hoặc chain. Không chỉ tìm chuỗi “jar verified” rồi bỏ qua các warning có ý nghĩa.

### 7.2. Phát hành lại với chữ ký phù hợp

Ví dụ về cú pháp ký JAR bằng một RSA private key hợp lệ:

```bash
jarsigner \
  -keystore signer.p12 \
  -storetype PKCS12 \
  -digestalg SHA-256 \
  -sigalg SHA256withRSA \
  -signedjar release-signed.jar \
  release.jar signer
```

Lệnh giả định `signer.p12` có alias `signer` và private key/certificate phù hợp. Đây không phải toàn bộ quy trình signing production; phải bảo vệ key và password bằng cơ chế bí mật được tổ chức phê duyệt.

Nếu sản phẩm cần xác minh sau khi signer certificate hết hạn, timestamping và chính sách lưu trữ bằng chứng ký có thể rất quan trọng.

### 7.3. Ký lại artifact không rõ nguồn là rủi ro

Không chỉ tải JAR từ một nguồn bất kỳ rồi ký lại để hết warning. Cần xác minh provenance của source, dependency và build pipeline trước khi phát hành signature mới.

JAR signature verification là một phần của bảo mật chuỗi cung ứng, không thay thế HTTPS, repository access control hay checksum validation.

## 8. API mật mã JCA/JCE và security providers

JCA/JCE có các API như `KeyPairGenerator`, `Signature`, `Cipher` và `MessageDigest`. Provider có thể hỗ trợ một phép toán trực tiếp nhưng TLS, certificate validator hoặc JAR verifier lại có policy nghiêm ngặt hơn.

Ví dụ tạo chữ ký minh họa:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public final class SignExample {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair pair = generator.generateKeyPair();

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(pair.getPrivate());
        signature.update("payload".getBytes(StandardCharsets.UTF_8));

        byte[] signed = signature.sign();
        System.out.println("Signature length: " + signed.length);
    }
}
```

Ví dụ trên **không phải quy trình quản lý key production**. Một hệ thống ký nghiệp vụ cần private key ổn định theo chính sách, bảo vệ bằng keystore/KMS/HSM, audit và rotation.

Đừng dùng việc `Signature.getInstance(...)` thành công làm bằng chứng rằng certificate TLS hoặc JAR đã được chấp nhận.

### 8.1. Provider có thể biến đổi theo JDK

Một provider cũ có thể hỗ trợ một curve hoặc alias mà provider mới không còn cung cấp. HSM có thể không hỗ trợ signature scheme cần cho TLS hiện đại. Custom `jlink` image cũng có thể thiếu module/provider cần thiết.

Vì vậy kiểm thử phải bao gồm đúng runtime image và thiết bị hoặc provider tương ứng, không chỉ JDK đầy đủ trên máy developer.

## 9. Chẩn đoán trên runtime thực tế

### 9.1. Xác định đúng JDK

```bash
java -version
java --list-modules
```

Ghi vendor, full update, architecture và container image. Gradle daemon, test JVM fork, application server và desktop client có thể chạy bằng JDK khác nhau.

### 9.2. Xem certificate

Với certificate file:

```bash
keytool -printcert -file server.crt
```

Với TLS server:

```bash
keytool -printcert -sslserver api.example.com:443
```

Với keystore:

```bash
keytool -list -v \
  -keystore server-keystore.p12 \
  -storetype PKCS12
```

Không đưa keystore password lên command line hoặc commit vào repository. Công cụ có thể nhắc nhập password tương tác.

Cần kiểm tra issuer, subject/SAN, validity, public key algorithm/size, signature algorithm, chain, alias và trust anchor.

### 9.3. Bật log có kiểm soát

```bash
java -Djavax.net.debug=ssl:handshake -jar app.jar
```

Nếu cần certificate path details:

```bash
java -Djava.security.debug=certpath \
  -Djavax.net.debug=ssl:handshake \
  -jar app.jar
```

Log có thể rất lớn và chứa thông tin vận hành nhạy cảm. Chỉ bật trong môi trường phù hợp và bảo vệ output.

### 9.4. Phân biệt exception

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `SSLHandshakeException: protocol_version` | Không có protocol chung | Xem TLS versions và JSSE policy |
| `No appropriate protocol` | Giao thức/cipher disabled | Xem `jdk.tls.disabledAlgorithms` và hai đầu |
| `PKIX path validation failed` | Chain/truststore/thời hạn/constraints | Đọc nested cause |
| `Algorithm constraints check failed` | Chữ ký/key size không đạt policy | Xác định property và certificate cụ thể |
| `InvalidKeyException` | Khóa/parameters/provider/policy không phù hợp | Kiểm tra JCE, key, provider |
| `NoSuchAlgorithmException` | Provider/algorithm không sẵn có | Kiểm tra tên và implementation |
| JAR signer warning | Digest/signature/key không đạt chuẩn | Dùng `jarsigner -verify -strict` |
| mTLS failure | Client certificate/key/usage không phù hợp | Kiểm tra chain cả hai chiều |

Một exception không thể thay thế việc phân tích đầy đủ security policy và stack trace.

## 10. Tình huống 1: server chỉ hỗ trợ TLS cũ

```text
Ứng dụng Java mới
       |
       | TLS handshake
       v
Legacy server: chỉ TLS 1.0
```

Lộ trình:

1. Xác minh server thật sự chỉ hỗ trợ protocol/cipher cũ.
2. Nâng server, TLS library hoặc reverse proxy để hỗ trợ TLS 1.2/1.3 và cipher được phê duyệt.
3. Kiểm tra certificate/key và chain trong cùng đợt nâng.
4. Chạy lại integration test bằng JDK mục tiêu.
5. Nếu thiết bị không thể nâng ngay, đánh giá một integration gateway được cô lập, giám sát, có hạn chót thay thế.

**Không nên bật lại TLS 1.0 hoặc cipher yếu trên toàn bộ JVM chỉ vì một đối tác lỗi thời.** Gateway, nếu được dùng, chỉ giới hạn vùng chịu rủi ro chứ không làm kết nối legacy trở nên an toàn.

## 11. Tình huống 2: certificate RSA 1024 bit

Giả sử server dùng RSA 1024 bit, bị client runtime mục tiêu từ chối theo security policy. Nhập lại certificate vào truststore không nhất thiết sửa được algorithm constraint.

Các bước:

1. Xác định owner, vị trí private key và certificate chain cũ.
2. Chọn thuật toán/kích thước khóa mới theo policy và yêu cầu tương tác.
3. Tạo key pair mới trong keystore/HSM được quản lý.
4. Tạo CSR, xin cấp certificate mới từ CA phù hợp.
5. Thiết lập SAN, key usage, extended key usage và full chain đúng mục đích.
6. Rollout, test TLS/mTLS và rotate/thu hồi khóa cũ.

Ví dụ tạo khóa RSA trong keystore thử nghiệm:

```bash
keytool -genkeypair \
  -alias app-server \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype PKCS12 \
  -keystore server-keystore.p12 \
  -validity 365
```

Lệnh trên tạo key pair và certificate tự ký theo hành vi của `keytool`; **certificate tự ký không mặc nhiên được client production tin cậy**. Cần CSR và quy trình CA phù hợp:

```bash
keytool -certreq \
  -alias app-server \
  -keystore server-keystore.p12 \
  -storetype PKCS12 \
  -file app-server.csr
```

Không lưu private key hoặc password trong source, script và log.

## 12. Tình huống 3: JAR ký bằng thuật toán legacy

Một artifact cũ có chữ ký SHA-1 hoặc key signer yếu. Runtime/công cụ mới cảnh báo chữ ký không còn đáp ứng chính sách.

Cách xử lý:

1. Lưu artifact gốc, checksum và provenance.
2. Xác minh bằng `jarsigner -verify -strict -verbose -certs`.
3. Xác định algorithm, digest, key size, signer chain, timestamp.
4. Tái build từ source đáng tin cậy.
5. Ký với key/cert đáp ứng chuẩn và timestamp khi cần.
6. Kiểm tra artifact phát hành trên runtime consumer thực tế.

Đừng chỉ ký lại JAR không rõ nguồn để vượt qua một warning.

## 13. Tình huống 4: dữ liệu được mã hóa bằng thuật toán cũ

Một ứng dụng có thể còn dữ liệu mã hóa bằng 3DES hoặc mode không xác thực. Chỉ thay tên thuật toán trong `Cipher.getInstance(...)` sẽ không làm ciphertext cũ đọc được bằng thuật toán mới.

Cần thiết kế format versioning:

```text
Dữ liệu legacy v1
       |
       v
Giải mã có kiểm soát (nếu policy cho phép)
       |
       v
Kiểm tra integrity và metadata
       |
       v
Mã hóa lại với format v2/key mới
       |
       v
Xác nhận rồi ngừng ghi format v1
```

Migration cần quản lý key rotation, IV/nonce, authentication tag, batch recovery và rollback. Nếu chuyển sang AES-GCM, **không được tái sử dụng nonce với cùng key**.

Hệ thống cần phân biệt đọc dữ liệu lịch sử theo quy trình chuyển đổi với tiếp tục tạo dữ liệu mới bằng thuật toán yếu.

## 14. Các thay đổi có thể đến từ patch JDK

Khi Java 17 cập nhật sang bản 17.x mới, defaults bảo mật có thể thay đổi ngay cả khi source và dependency không đổi.

Vì vậy cần so sánh:

- Full JDK vendor/version.
- `java.security` và security properties.
- Các provider được cài và thứ tự provider.
- Key/certificate material thực tế.
- Server/client TLS stacks.
- Runtime image và container digest.
- Các native/HSM/PKCS#11 components.

Nếu browser truy cập một trang thành công nhưng Java client thất bại, cần nhớ browser và JVM có thể dùng truststore và validator khác nhau. Kiểm thử phải dùng Java runtime đang được triển khai.

## 15. Không hạ chuẩn bảo mật để “fix nhanh”

Những cách làm cần tránh:

- Tắt hostname verification.
- Viết `TrustManager` tin mọi certificate.
- Bật TLS 1.0 hoặc cipher yếu cho toàn bộ máy chủ/runtime.
- Hạ key-size constraints toàn cục.
- Chuyển sang khóa quá ngắn vì thiết bị cũ không nhận thuật toán mạnh.
- Đưa private key/password vào code hoặc CI log.
- Ký lại artifact không có provenance.
- Giữ ngoại lệ bảo mật vô thời hạn.

Nếu không thể thay ngay một thiết bị legacy, cần có đánh giá rủi ro, phân đoạn mạng/process, owner, giám sát và hạn chót loại bỏ. Đây là phương án chuyển tiếp có kiểm soát, không phải tiêu chuẩn bảo mật mới.

## 16. Quy trình migration tổng thể

### Bước 1: Kiểm kê

Liệt kê TLS/mTLS endpoints, keystore, truststore, certificate chains, JAR signing keys, HSM, provider và API mã hóa đang dùng.

### Bước 2: Chốt baseline

Lưu JDK vendor/update, security property snapshot, certificate metadata, thử nghiệm TLS và kết quả xác minh JAR hiện tại.

### Bước 3: Chạy JDK mục tiêu

Thử integration test trên JDK mới với security defaults ban đầu; ghi exception chain và log đúng JVM gây lỗi.

### Bước 4: Phân loại

Xác định lỗi là protocol, cipher, truststore, certificate signature/key size, missing provider, JCE limit, mTLS hay lỗi ứng dụng không liên quan.

### Bước 5: Thay đúng thành phần

Nâng TLS stack của server; cấp lại certificate/key; nâng provider/HSM; ký lại JAR theo chuẩn; hoặc xây dựng đường di chuyển dữ liệu legacy an toàn.

### Bước 6: Kiểm thử hai đầu

Chạy với certificate, truststore, runtime image, container và endpoint thực sự tương đương production. Kiểm tra các tình huống certificate rotation, key rollover và phiên bản client còn tồn tại.

### Bước 7: Phát hành có giám sát

Rollout theo giai đoạn, theo dõi handshake failures, certificate validation, signer warnings và lỗi provider. Ghi version và policy vào release record để điều tra.

### Bước 8: Loại bỏ di sản

Thu hồi key/cert yếu, bỏ ngoại lệ tạm thời, cập nhật CI kiểm tra key size/algorithm và đưa việc rà soát security patch vào lịch định kỳ.

## 17. Checklist trước khi chấp nhận migration

- [ ] Đã xác định đúng JDK vendor, full update và runtime image.
- [ ] Đã đọc `jdk.tls.disabledAlgorithms`, `jdk.certpath.disabledAlgorithms` và `jdk.jar.disabledAlgorithms`.
- [ ] Đã phân biệt lỗi provider availability với lỗi security policy.
- [ ] Đã kiểm kê TLS versions và cipher suites của hai đầu.
- [ ] Đã xem public key algorithm/key size/curve của leaf và intermediates.
- [ ] Đã kiểm tra chữ ký, SAN, trust anchor, expiry, key usage và EKU.
- [ ] Đã kiểm tra cả client certificate nếu có mTLS.
- [ ] Đã dùng `jarsigner -verify -strict` nếu cần ký JAR.
- [ ] Đã xem `crypto.policy` nếu gặp vấn đề JCE key-size.
- [ ] Đã kiểm thử HSM/PKCS#11/native provider tương ứng.
- [ ] Đã chọn thuật toán/key mới theo policy tổ chức.
- [ ] Đã chạy test trên runtime, truststore và endpoint cuối.
- [ ] Đã có kế hoạch rotation, rollback, expiry alert và monitoring.
- [ ] Đã kiểm tra thay đổi chính sách khi update JDK.
- [ ] Đã loại bỏ hoặc kiểm soát có thời hạn các ngoại lệ legacy.

## 18. Kết luận

Trong Java Compatibility Migration, một thuật toán hoặc kích thước khóa từng hoạt động không có nghĩa nó sẽ tiếp tục được JDK chấp nhận mãi mãi. TLS/JSSE, PKIX certificate path validation, chữ ký JAR và JCA/JCE có các chính sách khác nhau, còn security provider và JDK update có thể làm thay đổi kết quả mà source code không hề đổi.

Để migration bền vững, cần **đọc đúng security policy, xác định ngữ cảnh bị từ chối, thay thế key/certificate/giao thức yếu, rồi kiểm thử trên môi trường triển khai cuối cùng**. Mục tiêu là duy trì chức năng đồng thời nâng chuẩn bảo mật, thay vì khôi phục các cấu hình mật mã rủi ro chỉ để vượt qua lỗi khởi động.
