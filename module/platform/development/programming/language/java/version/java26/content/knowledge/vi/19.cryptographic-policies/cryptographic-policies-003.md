# Phân biệt hạn chế thuật toán tổng quát, TLS và chứng thư

## 1. Bối cảnh bảo mật trên JDK 26 và JDK 27

JDK không có một danh sách hạn chế thuật toán duy nhất áp dụng đồng nhất cho mọi hoạt động mật mã. Các lớp xử lý khác nhau có những chính sách riêng:

- Tầng JCA/JCE kiểm soát thuật toán được yêu cầu qua các dịch vụ mật mã như Cipher, MessageDigest, Signature và KeyStore.
- JSSE kiểm soát thuật toán và giao thức được phép thương lượng trong TLS/DTLS.
- PKIX CertPath kiểm tra thuật toán, khóa và chữ ký trong chuỗi chứng thư, CRL và OCSP response.
- Chính sách CA distrust có thể từ chối một trust anchor cụ thể theo danh tính CA và thời điểm cấp chứng thư.

JDK 26 có ba thay đổi cần biết:

1. Bổ sung Security Property `jdk.crypto.disabledAlgorithms` để hạn chế thuật toán ở tầng JCA/JCE. Ban đầu property này hỗ trợ các dịch vụ Cipher, KeyStore, MessageDigest và Signature; mặc định ban đầu không vô hiệu hóa thuật toán nào.
2. `SunX509 KeyManagerFactory` được bổ sung kiểm tra algorithm constraints và certificate checks khi chọn chứng thư cục bộ cho TLS, tương tự PKIX KeyManagerFactory.
3. SunJSSE áp dụng chính sách distrust đối với TLS server certificates được cấp sau ngày 17/03/2026 và có chuỗi chứng thư neo tại các Chunghwa root CA thuộc danh sách bị distrust.

JDK 27 tiếp tục cung cấp các chính sách này. Đây là cấu hình bảo mật của JDK/provider, không phải Java language preview hoặc incubator API.

## 2. Bốn lớp kiểm soát cần phân biệt

| Phạm vi | Security Property hoặc API | Kiểm soát điều gì? |
|---|---|---|
| JCA/JCE service | `jdk.crypto.disabledAlgorithms` | Thuật toán được gọi qua các dịch vụ mật mã của JCA/JCE |
| TLS/DTLS | `jdk.tls.disabledAlgorithms` | Protocol, cipher suite, key exchange, signature và key được thương lượng |
| Certificate path | `jdk.certpath.disabledAlgorithms` | Thuật toán và kích thước khóa trong chuỗi chứng thư được PKIX kiểm tra |
| Trust anchor / CA distrust | `jdk.security.caDistrustPolicies` | Một số CA/root cụ thể bị từ chối theo chính sách và thời điểm cấp |

Các chính sách có thể cùng tác động trong một phiên TLS. Ví dụ, một client có thể:

- Từ chối cipher suite do `jdk.tls.disabledAlgorithms`.
- Từ chối chữ ký hoặc khóa trong certificate chain do `jdk.certpath.disabledAlgorithms`.
- Từ chối trust anchor do chính sách CA distrust.

Không nên gộp các lỗi này thành một lỗi chung "JDK không hỗ trợ thuật toán". Phải xác định lớp kiểm soát nào đã từ chối thao tác.

## 3. Hạn chế thuật toán tổng quát ở tầng JCA/JCE

### 3.1. JDK 26 bổ sung jdk.crypto.disabledAlgorithms

JDK 26 giới thiệu property:

~~~properties
jdk.crypto.disabledAlgorithms=Cipher.RSA/ECB/PKCS1Padding, MessageDigest.MD2
~~~

Mỗi mục gồm tên dịch vụ mật mã và thuật toán tương ứng:

- `Cipher.RSA/ECB/PKCS1Padding`: hạn chế transformation này khi yêu cầu dịch vụ Cipher.
- `MessageDigest.MD2`: hạn chế thuật toán MD2 khi yêu cầu dịch vụ MessageDigest.

JDK 26 ban đầu hỗ trợ bốn service type:

| Service | Ví dụ | Công việc |
|---|---|---|
| Cipher | `Cipher.AES/GCM/NoPadding` | Mã hóa/giải mã |
| KeyStore | `KeyStore.PKCS12` | Lưu và nạp khóa/chứng thư |
| MessageDigest | `MessageDigest.MD2` | Tính digest |
| Signature | `Signature.SHA1withRSA` | Tạo và xác minh chữ ký |

Không suy ra property này tự động hỗ trợ mọi JCA service type. Khi muốn hạn chế một dịch vụ khác, kiểm tra tài liệu JDK và provider đang triển khai trước.

Theo JDK 26 Release Notes, giá trị ban đầu của property là rỗng, nghĩa là chưa có thuật toán nào bị chặn bởi chính sách mới này. JDK có thể bổ sung giá trị mặc định trong các bản phát hành sau; luôn kiểm tra file `java.security` của runtime đang triển khai.

### 3.2. Ví dụ cấu hình hạn chế ở JCA/JCE

Một file security properties bổ sung có thể khai báo:

~~~properties
jdk.crypto.disabledAlgorithms=Cipher.RSA/ECB/PKCS1Padding, MessageDigest.MD2
~~~

Ứng dụng yêu cầu dịch vụ tương ứng có thể nhận lỗi không tìm thấy implementation phù hợp hoặc lỗi do provider từ chối thuật toán, tùy API và provider. Không giả định mọi thao tác đều ném cùng một loại exception.

Ví dụ:

~~~java
import java.security.MessageDigest;

public class CryptoServicePolicyDemo {
    public static void main(String[] args) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("MD2");
        System.out.println(digest.getProvider());
    }
}
~~~

Nếu MD2 bị chặn bởi property và provider tuân theo chính sách đó, yêu cầu có thể thất bại với `NoSuchAlgorithmException`. Mục đích là ngăn ứng dụng gọi một thuật toán đã bị tổ chức hoặc runtime đánh dấu không còn được phép dùng.

### 3.3. Phạm vi của property này

`jdk.crypto.disabledAlgorithms` kiểm soát yêu cầu dịch vụ mật mã ở JCA/JCE layer. Nó không thay thế:

- `jdk.tls.disabledAlgorithms` khi thương lượng TLS.
- `jdk.certpath.disabledAlgorithms` khi xác thực certification path.
- Chính sách tin cậy CA, hostname verification hoặc revocation checking.

Một thuật toán có thể bị chặn khi gọi trực tiếp qua Cipher nhưng vẫn có các ràng buộc riêng khác khi được dùng trong TLS hoặc chứng thư. Ngược lại, thuật toán không bị `jdk.crypto.disabledAlgorithms` chặn vẫn có thể không được thương lượng trong TLS vì bị `jdk.tls.disabledAlgorithms` từ chối.

### 3.4. Override bằng system property

JDK 26 cho phép override giá trị Security Property này bằng system property cùng tên:

~~~bash
java -Djdk.crypto.disabledAlgorithms=Cipher.RSA/ECB/PKCS1Padding -jar app.jar
~~~

Cơ chế này có thể phục vụ ứng dụng cần cấu hình riêng, nhưng cũng có thể làm yếu chính sách bảo mật toàn tiến trình. Không dùng override để làm cho thuật toán yếu hoạt động lại chỉ nhằm tránh sửa hệ thống tích hợp.

Đây là điểm đặc biệt của `jdk.crypto.disabledAlgorithms` được JDK 26 Release Notes ghi rõ. Không áp dụng quy tắc override này cho mọi Security Property khác.

## 4. Hạn chế thuật toán trong TLS/DTLS

### 4.1. jdk.tls.disabledAlgorithms

`jdk.tls.disabledAlgorithms` được SunJSSE sử dụng để loại bỏ những thành phần không được phép thương lượng trong TLS/DTLS:

- Phiên bản giao thức.
- Cipher suite.
- Thuật toán mã hóa và MAC.
- Thuật toán trao đổi khóa.
- Kích thước khóa.
- Một số thuật toán chữ ký được dùng trong handshake.

Ví dụ về các loại mục thường có trong cấu hình JDK hiện hành:

~~~properties
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, RC4, DES, MD5withRSA, DH keySize < 1024, EC keySize < 224
~~~

Đây là đoạn minh họa về cú pháp và nhóm hạn chế, không phải danh sách đầy đủ để thay thế nguyên giá trị mặc định của JDK 27. File `java.security` trong từng JDK update có thể chứa danh sách khác.

Nếu một cipher suite bị property này chặn, gọi `SSLSocket.setEnabledCipherSuites()` hoặc `SSLParameters.setCipherSuites()` không làm cipher suite đó được phép sử dụng. JSSE có thể chấp nhận cấu hình ở API nhưng không thương lượng cipher suite đã bị disabled trong handshake.

### 4.2. jdk.tls.legacyAlgorithms không đồng nghĩa với disabled

Một số thuật toán còn được hỗ trợ để duy trì khả năng tương thích, nhưng không được ưu tiên. `jdk.tls.legacyAlgorithms` liệt kê thuật toán TLS/DTLS được xem là legacy.

Trong quá trình thương lượng:

- Thuật toán legacy không được chọn nếu còn ứng viên phù hợp khác.
- Nếu không có ứng viên khác, thuật toán legacy có thể vẫn được thương lượng.
- Nếu một thuật toán đồng thời bị `jdk.tls.disabledAlgorithms` hoặc `AlgorithmConstraints` chặn, nó bị loại bỏ hoàn toàn.

Ví dụ, một hệ thống còn hỗ trợ 3DES vì thiết bị cũ có thể xếp thuật toán đó vào legacy trong một giai đoạn chuyển đổi. Khi 3DES được đưa vào disabled list, nó không còn là phương án dự phòng.

Không dựa vào legacy algorithms làm cấu hình production lâu dài. Hãy nâng cấp peer và thay thế thuật toán yếu bằng lựa chọn còn được khuyến nghị.

### 4.3. AlgorithmConstraints cho chính sách theo kết nối

Ngoài Security Property ở cấp JDK, ứng dụng có thể áp dụng ràng buộc cho TLS context/socket thông qua `java.security.AlgorithmConstraints` và `SSLParameters.setAlgorithmConstraints()`.

Ví dụ cách gắn chính sách vào `SSLParameters`:

~~~java
SSLParameters parameters = sslSocket.getSSLParameters();
parameters.setAlgorithmConstraints(applicationConstraints);
sslSocket.setSSLParameters(parameters);
~~~

`applicationConstraints` là implementation `AlgorithmConstraints` do ứng dụng cung cấp, cần kiểm tra các `CryptoPrimitive`, thuật toán và key theo chính sách đã định nghĩa.

Ràng buộc tùy chỉnh này bổ sung kiểm soát theo ứng dụng/kết nối. Nó không nên được dùng để nới lỏng những thuật toán đã bị Security Property toàn JDK chặn.

### 4.4. Quan sát TLS handshake

Có thể bật JSSE debug khi cần xác định vì sao handshake không chọn được protocol hoặc cipher suite:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

Thông tin hữu ích gồm protocol được đề xuất, cipher suite, signature schemes, named groups và lỗi handshake. Log có thể chứa thông tin định danh chứng thư hoặc metadata kết nối; chỉ bật trong môi trường chẩn đoán được kiểm soát.

## 5. Hạn chế thuật toán trong certificate path

### 5.1. jdk.certpath.disabledAlgorithms

`jdk.certpath.disabledAlgorithms` được CertPath implementation sử dụng để từ chối thuật toán hoặc kích thước khóa yếu trong quá trình xây dựng và xác thực certification path.

Phạm vi có thể bao gồm:

- Chữ ký của chứng thư X.509 trong chuỗi.
- Thuật toán khóa công khai và kích thước khóa.
- CRL và OCSP response trong quá trình kiểm tra path/revocation.
- Các điều kiện theo ngữ cảnh như mục đích sử dụng chứng thư, trust anchor hoặc thời điểm.

Ví dụ cấu hình JDK 27 có các điều kiện như:

~~~properties
jdk.certpath.disabledAlgorithms=MD2, MD5, SHA1 jdkCA & usage TLSServer, RSA keySize < 1024, DSA keySize < 1024, EC keySize < 224
~~~

Danh sách chính xác có thể khác theo JDK update. Ví dụ trên minh họa cách policy kết hợp thuật toán, key-size constraint và ngữ cảnh sử dụng.

### 5.2. Điều kiện theo usage và trust anchor

Một constraint có thể giới hạn SHA-1 trong trường hợp chứng thư TLS server được neo tại root CA có sẵn trong JDK:

~~~properties
SHA1 jdkCA & usage TLSServer
~~~

Ý nghĩa:

- `SHA1`: thuật toán chữ ký sử dụng SHA-1.
- `jdkCA`: áp dụng trong ngữ cảnh chain neo tại CA được JDK nhận diện là JDK CA.
- `usage TLSServer`: áp dụng cho mục đích chứng thư máy chủ TLS.

Đây không phải lệnh cấm mọi chứng thư SHA-1 trong mọi hoàn cảnh. Các điều kiện ngữ cảnh là một phần của biểu thức constraint.

Một số constraint có thể dùng `denyAfter` để giới hạn thuật toán theo thời điểm. Khi kiểm tra policy của một runtime, đọc nguyên biểu thức trong `java.security` thay vì chỉ tìm tên thuật toán.

### 5.3. Trust anchor và self-signed certificate

Oracle PKI Guide nêu rõ `jdk.certpath.disabledAlgorithms` không áp dụng các hạn chế đó cho trust anchors hoặc self-signed certificates.

Vì vậy, không suy luận rằng mọi root certificate trong truststore đều đã được kiểm tra bằng cùng một bộ constraint như chứng thư intermediate hoặc end-entity. Quản trị viên vẫn phải quản lý truststore, loại bỏ CA không còn tin cậy và theo dõi chính sách distrust của JDK.

Ngoài ra, việc parse được chứng thư hoặc xác minh chữ ký riêng lẻ không đồng nghĩa certification path hợp lệ. Ứng dụng cần xác minh chuỗi, trust anchor, thời hạn, mục đích sử dụng, hostname và revocation theo yêu cầu của giao thức.

### 5.4. Kiểm tra certificate path độc lập

Có thể yêu cầu CertPath debug khi chẩn đoán lỗi xác thực:

~~~bash
java -Djava.security.debug=certpath -jar app.jar
~~~

Log giúp tìm điều kiện thuật toán, key size hoặc certificate path đã khiến PKIX validator từ chối chain. Đối với TLS, kết hợp thêm JSSE handshake debug để biết lỗi xảy ra trong negotiation hay certificate validation.

## 6. CA distrust là chính sách tin cậy riêng

Không phải mọi certificate bị từ chối đều do thuật toán yếu.

JDK 26 bổ sung chính sách distrust đối với TLS server certificates được cấp sau ngày 17/03/2026 và có chain neo tại các Chunghwa root CA được liệt kê trong release notes.

Chính sách này được thực thi bởi SunJSSE và điều khiển qua `jdk.security.caDistrustPolicies`. Mã policy liên quan là `CHUNGHWA_TLS`.

Phân biệt:

| Trường hợp | Nguyên nhân |
|---|---|
| Chứng thư ký bằng thuật toán bị chặn | `jdk.certpath.disabledAlgorithms` |
| Chứng thư neo tại CA bị distrust theo thời điểm | `jdk.security.caDistrustPolicies` |
| TLS handshake dùng cipher suite/protocol bị chặn | `jdk.tls.disabledAlgorithms` |
| Ứng dụng gọi Cipher/Signature service bị hạn chế | `jdk.crypto.disabledAlgorithms` |

Các chứng thư Chunghwa được cấp vào hoặc trước ngày 17/03/2026 tiếp tục được tin cậy cho đến khi hết hạn theo chính sách được công bố. Chứng thư cấp sau ngày này và neo tại các root bị ảnh hưởng sẽ bị từ chối.

Không loại bỏ `CHUNGHWA_TLS` khỏi cấu hình để chữa lỗi kết nối production. Nếu một hệ thống còn phụ thuộc CA bị distrust, hãy làm việc với CA và thay chứng thư bằng chain được chấp nhận.

## 7. JDK 26: thay đổi trong SunX509 KeyManagerFactory

JDK 26 bổ sung hỗ trợ algorithm constraints và certificate checks cho default `SunX509 KeyManagerFactory`, đưa hành vi chọn chứng thư cục bộ gần với `PKIX KeyManagerFactory`.

Khi chọn local certificate cho TLS, SunX509 có thể xét:

1. Signature algorithms mà peer gửi trong TLS `signature_algorithms_cert` extension.
2. Constraint từ `jdk.tls.disabledAlgorithms`.
3. Constraint từ `jdk.certpath.disabledAlgorithms`.
4. Thời hạn chứng thư và certificate extensions.

Điều này giúp key manager tránh chọn chứng thư không phù hợp với thuật toán peer chấp nhận hoặc chính sách bảo mật của JDK.

Cần phân biệt hai phía:

- `KeyManager` chọn credential/certificate cục bộ để gửi cho peer.
- `TrustManager` xác minh certificate chain mà peer gửi đến.

JDK 26 cải tiến lựa chọn local certificate trong SunX509. Việc đó không thay thế trust manager hoặc certificate path validation phía nhận.

## 8. So sánh các chính sách bằng tình huống thực tế

| Tình huống | Chính sách cần xem | Vì sao |
|---|---|---|
| Ứng dụng gọi `MessageDigest.getInstance("MD2")` | `jdk.crypto.disabledAlgorithms` | Hạn chế dịch vụ MessageDigest ở JCA/JCE |
| Ứng dụng yêu cầu Cipher transformation yếu | `jdk.crypto.disabledAlgorithms` | Hạn chế dịch vụ Cipher |
| Client không thể thương lượng TLSv1.1 | `jdk.tls.disabledAlgorithms` | Protocol version bị loại |
| Server chỉ có cipher suite 3DES | `jdk.tls.disabledAlgorithms` và `jdk.tls.legacyAlgorithms` | Phân biệt bị cấm hoàn toàn với legacy fallback |
| TLS chain chứa SHA-1 trong ngữ cảnh bị cấm | `jdk.certpath.disabledAlgorithms` | PKIX từ chối certificate path |
| TLS server dùng root CA bị distrust sau ngày chính sách | `jdk.security.caDistrustPolicies` | Trust anchor bị từ chối theo chính sách CA |
| SunX509 chọn sai local certificate | JDK 26 SunX509 checks, TLS/certpath properties | Kiểm tra peer signature algorithms và constraints khi chọn local credential |
| JAR ký bằng thuật toán yếu | `jdk.jar.disabledAlgorithms` và `jdk.security.legacyAlgorithms` | Đây là phạm vi xác minh chữ ký JAR, không phải TLS handshake |

## 9. Cấu hình Security Properties an toàn

### 9.1. Vị trí file cấu hình

File cấu hình bảo mật chính của JDK 26/27:

~~~text
<java-home>/conf/security/java.security
~~~

Có thể xem giá trị trong file này để biết chính sách mặc định của bản JDK đang chạy. Các giá trị có thể thay đổi theo JDK feature release, CPU/security update, vendor hoặc custom distribution.

### 9.2. Dùng file cấu hình bổ sung

Có thể thêm security properties file riêng bằng system property:

~~~bash
java -Djava.security.properties=C:/security/company.security -jar app.jar
~~~

File bổ sung được nạp cùng master security properties file. Nếu cùng một property xuất hiện trong file sau, giá trị sau thay thế toàn bộ giá trị trước; JVM không tự nối thêm danh sách.

Do đó, nếu muốn thêm một constraint vào `jdk.tls.disabledAlgorithms` hoặc `jdk.certpath.disabledAlgorithms`, cần giữ lại những mục mặc định cần thiết trong giá trị mới. Không ghi một giá trị ngắn rồi vô tình bỏ toàn bộ hạn chế hiện có.

Dạng hai dấu bằng:

~~~bash
-Djava.security.properties==C:/security/company.security
~~~

thay thế toàn bộ master security properties file. Không dùng dạng này nếu mục tiêu chỉ là bổ sung một vài policy; việc đó có thể làm mất provider registration và các chính sách bảo mật mặc định.

### 9.3. Security.setProperty và thời điểm cấu hình

Ứng dụng có thể dùng:

~~~java
String current =
        Security.getProperty("jdk.certpath.disabledAlgorithms");

System.out.println(current);
~~~

Một số Security Property được đọc và cache khi security subsystem hoặc provider khởi tạo. Gọi `Security.setProperty()` sau thời điểm đó có thể không ảnh hưởng đến component đã cache giá trị. Đối với chính sách triển khai, ưu tiên cấu hình trước khi JVM khởi động hoặc dùng security properties file có quản lý.

Riêng `jdk.crypto.disabledAlgorithms` còn có cơ chế override bằng system property cùng tên như đã trình bày; không suy rộng cơ chế này sang TLS hoặc CertPath properties.

## 10. Kiểm tra chính sách đang có hiệu lực

### 10.1. In security settings

Dùng:

~~~bash
java -XshowSettings:security -version
~~~

Lệnh này in tổng quan security settings mà JDK đang sử dụng. Có thể dùng để xác nhận runtime thực tế thay vì chỉ đọc một file cấu hình chưa chắc được process nạp.

### 10.2. Theo dõi quá trình nạp security properties

~~~bash
java -Djava.security.debug=properties -version
~~~

Các dòng log cho biết property cuối cùng và cách các file/include được xử lý. Khi property được định nghĩa ở nhiều file, cần kiểm tra giá trị cuối cùng thay vì chỉ xem file cấu hình bổ sung.

### 10.3. Kiểm tra TLS protocol và cipher suites

~~~bash
keytool -showinfo -tls
~~~

Hoặc:

~~~bash
java -XshowSettings:security:tls -version
~~~

Danh sách hiển thị về các protocol/cipher suite mặc định không nhất thiết chứa mọi thuật toán có thể được provider hỗ trợ; các thuật toán đã bị `jdk.tls.disabledAlgorithms` loại vẫn không thể được thương lượng.

### 10.4. Debug certificate path và TLS handshake

~~~bash
java -Djava.security.debug=certpath -jar app.jar
~~~

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

Hai nhóm log giúp phân biệt lỗi ở PKIX path validation và lỗi ở TLS negotiation. Không nên chỉ tăng danh sách cipher suite khi nguyên nhân thật sự là certificate chain không được tin cậy.

## 11. Legacy, disabled và không được bật mặc định

Ba trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Có thể được sử dụng không? |
|---|---|---|
| Disabled | Bị chính sách chặn | Không được sử dụng trong phạm vi policy |
| Legacy | Còn được hỗ trợ nhưng bị giảm ưu tiên hoặc cảnh báo | Có thể chỉ dùng khi không còn lựa chọn phù hợp, tùy subsystem |
| Not enabled by default | Không được bật mặc định | Có thể được ứng dụng cấu hình bật nếu không bị disabled |

Đặc biệt trong TLS, `jdk.tls.legacyAlgorithms` không đồng nghĩa với `jdk.tls.disabledAlgorithms`. Một thuật toán legacy có thể được dùng làm fallback; một thuật toán disabled thì không được thương lượng dù ứng dụng cố bật qua `SSLParameters`.

Với signed JAR, `jdk.jar.disabledAlgorithms` quyết định thuật toán khiến chữ ký JAR bị xem là không hợp lệ; các công cụ như `keytool` và `jarsigner` cũng có thể cảnh báo về thuật toán legacy qua các security properties tương ứng.

Không chọn thuật toán legacy chỉ vì nó vẫn xuất hiện trong danh sách provider. Khả năng provider triển khai một thuật toán không đồng nghĩa policy cho phép dùng thuật toán đó trong một ngữ cảnh cụ thể.

## 12. Quy trình kiểm thử khi nâng cấp JDK 25 lên JDK 26/27

### 12.1. Kiểm tra JCA/JCE service

- Ghi nhận các Cipher, KeyStore, MessageDigest và Signature mà ứng dụng thực sự gọi.
- Kiểm tra giá trị `jdk.crypto.disabledAlgorithms` trên JDK 26 và JDK 27.
- Thử các đường code phụ thuộc thuật toán bị hạn chế.
- Xác nhận ứng dụng có thông báo lỗi rõ ràng và có phương án thay thế an toàn.

### 12.2. Kiểm tra TLS

- Ghi nhận TLS protocol, cipher suites, signature schemes và named groups của peer.
- Kiểm tra `jdk.tls.disabledAlgorithms` và `jdk.tls.legacyAlgorithms`.
- Test handshake với server/client thực tế.
- Xác nhận không dựa vào TLS version hoặc cipher suite đã bị disabled.
- Kiểm tra ứng dụng không cố bật lại cipher suite bị policy chặn.

### 12.3. Kiểm tra certificate path

- Test chain có thuật toán chữ ký và key size theo chính sách hiện tại.
- Test certificate hết hạn, sai mục đích hoặc sai hostname.
- Test trust anchor không còn được tin cậy.
- Test CRL/OCSP nếu ứng dụng bật revocation checking.
- Kiểm tra `jdk.certpath.disabledAlgorithms` và các policy CA distrust.

### 12.4. Kiểm tra KeyManager

Nếu hệ thống dùng `SunX509 KeyManagerFactory`, kiểm thử lại lựa chọn local certificate sau khi nâng JDK 26. Xác nhận chứng thư được chọn:

- Phù hợp signature algorithms mà peer quảng bá.
- Không vi phạm TLS/certpath constraints.
- Còn hiệu lực và có extensions phù hợp.
- Được cấu hình đúng trong keystore.

### 12.5. Kiểm tra JDK vendor và update

Các Security Property này thuộc hành vi implementation của JDK/provider. Oracle JDK và các JDK distribution khác có thể khác giá trị hoặc mức hỗ trợ. Luôn kiểm tra runtime thật, security file của runtime và provider đang xử lý kết nối.

## 13. Các lỗi cấu hình cần tránh

- Không ghi đè toàn bộ `jdk.tls.disabledAlgorithms` hoặc `jdk.certpath.disabledAlgorithms` chỉ để thêm một mục.
- Không dùng `java.security.properties==...` khi chỉ muốn thêm một vài policy.
- Không xem `jdk.crypto.disabledAlgorithms` là chính sách thay thế TLS hoặc CertPath.
- Không giả định mọi provider đều thực thi các property riêng của Oracle/SunJSSE.
- Không bật lại thuật toán yếu chỉ để khắc phục lỗi tương thích.
- Không coi `legacyAlgorithms` là thuật toán đã bị vô hiệu hóa hoàn toàn.
- Không coi certificate parse thành công là certificate path đáng tin cậy.
- Không bỏ qua hostname verification hoặc revocation checking chỉ vì thuật toán chữ ký được phép.
- Không sửa trực tiếp JDK installation dùng chung mà không quản lý phiên bản và quy trình triển khai.
- Không đặt Security Property quá muộn sau khi provider đã cache giá trị.

## 14. Kết luận

JDK 26 bổ sung `jdk.crypto.disabledAlgorithms` để tổ chức có thể hạn chế thuật toán ở tầng dịch vụ JCA/JCE. Đây là chính sách chung cho một số service type, không phải bộ lọc thay thế mọi kiểm tra TLS hoặc certificate path.

Ba lớp cần nhớ:

- `jdk.crypto.disabledAlgorithms`: hạn chế thuật toán theo JCA/JCE service như Cipher, KeyStore, MessageDigest và Signature.
- `jdk.tls.disabledAlgorithms`: loại bỏ protocol, cipher suite, key exchange hoặc signature không được phép thương lượng trong TLS/DTLS.
- `jdk.certpath.disabledAlgorithms`: kiểm tra thuật toán và key size trong certification path; có thể có điều kiện theo usage và trust anchor.

Ngoài ra, `jdk.security.caDistrustPolicies` xử lý việc từ chối một số CA cụ thể theo chính sách tin cậy, còn `jdk.tls.legacyAlgorithms` biểu thị lựa chọn cũ được giảm ưu tiên chứ không đồng nghĩa với disabled.

JDK 26 còn cải thiện việc chọn local certificate trong SunX509 KeyManagerFactory bằng cách áp dụng peer signature algorithms và TLS/CertPath constraints. Khi nâng cấp lên JDK 26/27, hãy kiểm tra từng lớp policy, chạy test trên đúng provider và chỉ điều chỉnh sau khi xác định chính xác nguyên nhân.

## Tài liệu tham khảo chính thức

- [JDK 26 Release Notes — New Security Property jdk.crypto.disabledAlgorithms](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 26 Release Notes — Support Algorithm Constraints and Certificate Checks in SunX509 Key Manager](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 26 Release Notes — Distrust TLS Server Certificates Anchored by Chunghwa Root Certificates](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Security Properties File — Java SE 27](https://docs.oracle.com/en/java/javase/27/security/security-properties-file.html)
- [Java Secure Socket Extension (JSSE) Reference Guide — Java SE 27](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java PKI Programmer's Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html)
- [JCA Reference Guide — Java SE 27](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html)
- [JDK 26 Security Updates — Java SE 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/security-updates.html)
- [Disabling and Restricting Cryptographic Algorithms in the JDK — Oracle Java Security](https://ops.java/security/articles/disabling-crypto-algorithms/)

