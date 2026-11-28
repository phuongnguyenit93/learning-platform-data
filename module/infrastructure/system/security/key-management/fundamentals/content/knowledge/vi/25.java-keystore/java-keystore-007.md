# PrivateKeyEntry

Trong chương **Java KeyStore** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích loại entry PrivateKeyEntry trong Java KeyStore và cách nó liên kết private key với certificate chain tương ứng. Đây là entry quan trọng khi ứng dụng Java cần chứng minh danh tính qua TLS/mTLS, ký dữ liệu hoặc thực hiện thao tác mật mã bằng khóa bất đối xứng. Quản lý đúng PrivateKeyEntry giúp ứng dụng chọn đúng khóa, xác minh đúng chứng thư và bảo vệ private key trong suốt vòng đời sử dụng.

## 1. PrivateKeyEntry là gì?

**PrivateKeyEntry** là một loại entry của Java KeyStore dùng để lưu private key cùng chuỗi chứng thư số tương ứng. Private key là phần bí mật của cặp khóa; certificate chain chứa chứng thư lá có public key tương ứng và có thể gồm các chứng thư CA trung gian nối tới trust anchor.

Một PrivateKeyEntry thường có ba thành phần quan trọng:

- **Private key:** khóa bí mật được ứng dụng dùng để ký, giải mã hoặc thực hiện thao tác theo giao thức.
- **Certificate chain:** mảng chứng thư gắn với private key. Phần tử đầu tiên thường là chứng thư của chủ thể sở hữu private key; các phần tử tiếp theo là chứng thư issuer/intermediate theo thứ tự đường dẫn.
- **Alias:** tên định danh entry trong KeyStore để ứng dụng hoặc công cụ quản trị tìm và truy xuất entry.

Chứng thư trong chain là dữ liệu công khai, có thể được gửi cho peer để xác minh danh tính. Private key phải được bảo vệ và không được đưa vào certificate chain. Khi ứng dụng cần dùng private key, Java provider lấy khóa từ KeyStore hoặc cung cấp một đối tượng PrivateKey đại diện cho khóa trong thiết bị bảo vệ.

Một PrivateKeyEntry không chỉ là một file chứng thư. Chứng thư đơn lẻ không đủ để thực hiện thao tác ký bằng danh tính đó nếu ứng dụng không có private key tương ứng. Ngược lại, private key không có certificate chain có thể không đáp ứng các giao thức cần chứng minh danh tính qua PKI.

## 2. Vị trí của PrivateKeyEntry trong mô hình KeyStore

Java KeyStore tổ chức dữ liệu thành các entry được truy xuất bằng alias. Các loại entry phổ biến gồm:

| Loại entry | Nội dung | Mục đích |
|---|---|---|
| PrivateKeyEntry | Private key và certificate chain tương ứng | Danh tính của ứng dụng/chủ thể; TLS server/client, ký số hoặc giải mã |
| TrustedCertificateEntry | Một chứng thư tin cậy, không kèm private key | Trust anchor hoặc chứng thư được ứng dụng cấu hình tin cậy |
| SecretKeyEntry | Khóa bí mật đối xứng | Mã hóa/giải mã dữ liệu hoặc thao tác đối xứng khác |

PrivateKeyEntry thường được dùng trong **identity keystore** của ứng dụng. TrustedCertificateEntry thường được dùng trong **trust store** để xác minh chứng thư của peer. Hai vai trò có thể được lưu trong cùng một file KeyStore, nhưng nên tách theo mục đích và quyền quản trị để tránh nhầm lẫn.

Ví dụ:

| Kho | Entry | Dữ liệu điển hình |
|---|---|---|
| Identity keystore của API | PrivateKeyEntry | Private key của API và certificate chain do CA cấp |
| Trust store của API | TrustedCertificateEntry | Root CA hoặc CA nội bộ mà API dùng để xác minh client |
| Keystore mã hóa dữ liệu | SecretKeyEntry | AES key nếu ứng dụng lưu khóa đối xứng trong KeyStore |

Không nên đặt một CA root vào PrivateKeyEntry nếu không có private key CA tương ứng. Tương tự, không nên dùng PrivateKeyEntry của server làm trust anchor để xác minh mọi peer.

## 3. Cấu trúc certificate chain trong PrivateKeyEntry

Certificate chain liên kết public key trong chứng thư lá với các CA phát hành. Thứ tự thường là:

1. Chứng thư lá (leaf certificate) có public key khớp với private key trong entry.
2. Chứng thư CA trung gian đã phát hành leaf certificate.
3. Các CA trung gian cấp cao hơn, nếu có.
4. Root CA có thể xuất hiện hoặc không, tùy quy trình đóng gói chain và yêu cầu của nền tảng.

Ví dụ:

```text
PrivateKeyEntry: alias = api-server
  Private key: K_api_private
  Certificate chain:
    [0] api.example.com
    [1] Example Issuing CA 02
    [2] Example Root CA
```

Trong triển khai TLS, server thường gửi leaf certificate và các intermediate certificate cần thiết. Client đã có trust anchor trong trust store nên server thường không cần gửi root certificate. Việc có root trong chain của PrivateKeyEntry không tự động khiến root trở thành trust anchor của client.

Certificate ở phần tử đầu tiên phải chứa public key tương ứng với private key. Nếu ghép nhầm private key và certificate, thao tác ký hoặc handshake có thể thất bại. Nếu chain thiếu intermediate hoặc sai thứ tự, client có thể không xây dựng được đường dẫn xác minh dù private key vẫn đúng.

## 4. Alias và định danh entry

Alias là tên ứng dụng dùng để tìm một entry. Ví dụ, một keystore có thể chứa alias api-server, client-auth, document-signing hoặc code-signing. Alias không phải danh tính đã được CA xác thực; danh tính nằm trong certificate subject/SAN và được kiểm tra qua certificate path validation.

Một số lưu ý khi thiết kế alias:

- Đặt tên phản ánh mục đích, môi trường hoặc dịch vụ, tránh tên chung như key1 hoặc default.
- Duy trì alias ổn định nếu cấu hình ứng dụng tham chiếu trực tiếp tới alias.
- Dùng quy ước nhất quán giữa development, staging và production.
- Không dùng alias làm nơi lưu mật khẩu, token hoặc bí mật khác.
- Kiểm tra quy tắc phân biệt chữ hoa/chữ thường của provider; hành vi có thể khác giữa các loại KeyStore.
- Tránh tái sử dụng alias cho một danh tính khác khi ứng dụng hoặc hệ thống triển khai vẫn giữ tham chiếu cũ.

Alias giúp định vị entry nhưng không thay thế kiểm tra certificate. Ứng dụng vẫn cần kiểm tra SAN, EKU, thời hạn và chain của chứng thư được lấy ra.

## 5. PrivateKeyEntry trong Java KeyStore API

Java cung cấp lớp lồng nhau KeyStore.PrivateKeyEntry để biểu diễn entry có private key và certificate chain. Một số phương thức thường dùng:

| API | Vai trò |
|---|---|
| KeyStore.getEntry(alias, protection) | Lấy entry theo alias và thông tin bảo vệ |
| KeyStore.setEntry(alias, entry, protection) | Ghi entry cùng cơ chế bảo vệ tương ứng |
| KeyStore.getKey(alias, password) | Lấy key của alias nếu provider cho phép |
| KeyStore.getCertificate(alias) | Lấy chứng thư đầu tiên của entry |
| KeyStore.getCertificateChain(alias) | Lấy certificate chain |
| KeyStore.entryInstanceOf(alias, class) | Kiểm tra alias có thuộc loại entry được chỉ định không |
| PrivateKeyEntry.getPrivateKey() | Lấy đối tượng PrivateKey |
| PrivateKeyEntry.getCertificate() | Lấy chứng thư đầu tiên |
| PrivateKeyEntry.getCertificateChain() | Lấy toàn bộ chain |

Ưu tiên dùng getEntry với PasswordProtection khi cần làm việc theo mô hình Entry API. getKey vẫn hữu ích trong mã cũ hoặc trường hợp cần truy xuất trực tiếp key, nhưng ứng dụng cần xử lý đúng loại khóa và thông tin bảo vệ.

### Đọc PrivateKeyEntry từ PKCS12

Ví dụ sau nạp keystore PKCS12 và lấy entry theo alias:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Arrays;

public final class IdentityKeyLoader {
    public static void inspect(
            Path path,
            char[] storePassword,
            char[] entryPassword,
            String alias) throws Exception {

        try {
            KeyStore keyStore = KeyStore.getInstance("PKCS12");
            try (InputStream input = Files.newInputStream(path)) {
                keyStore.load(input, storePassword);
            }

            if (!keyStore.containsAlias(alias)
                    || !keyStore.entryInstanceOf(
                            alias, KeyStore.PrivateKeyEntry.class)) {
                throw new IllegalStateException(
                        "Alias does not contain a PrivateKeyEntry");
            }

            try (KeyStore.PasswordProtection protection =
                         new KeyStore.PasswordProtection(entryPassword)) {
                KeyStore.Entry entry = keyStore.getEntry(alias, protection);
                if (!(entry instanceof KeyStore.PrivateKeyEntry)) {
                    throw new IllegalStateException("Unexpected entry type");
                }

                KeyStore.PrivateKeyEntry privateEntry =
                        (KeyStore.PrivateKeyEntry) entry;
                PrivateKey privateKey = privateEntry.getPrivateKey();
                Certificate[] chain = privateEntry.getCertificateChain();
                if (chain.length == 0
                        || !(chain[0] instanceof X509Certificate)) {
                    throw new IllegalStateException(
                            "Missing X.509 leaf certificate");
                }
                X509Certificate leaf = (X509Certificate) chain[0];

                System.out.println("Key algorithm: "
                        + privateKey.getAlgorithm());
                System.out.println("Certificate count: " + chain.length);
                System.out.println("Leaf subject: "
                        + leaf.getSubjectX500Principal().getName());
            }
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
        }
    }
}
```

Đây là ví dụ minh họa cách nạp và kiểm tra loại entry. Trong ứng dụng thực tế, không in private key, nội dung bí mật hoặc toàn bộ thông tin nhạy cảm ra log. Việc gọi getPrivateKey() trả về đối tượng PrivateKey không bảo đảm key material có thể export; provider HSM có thể trả về đối tượng đại diện/handle thay vì byte của khóa.

Đoạn mã cũng minh họa việc xóa nội dung các mảng mật khẩu sau khi dùng. Cách này giảm thời gian giữ bản sao trong mảng do ứng dụng quản lý, nhưng không bảo đảm mọi bản sao trong heap hoặc provider đã bị xóa vật lý. Nên lấy mật khẩu từ secret manager hoặc cơ chế bảo vệ tương đương và giới hạn thời gian tồn tại.

## 6. Tạo PrivateKeyEntry bằng keytool

Có thể tạo một key pair và entry trong PKCS12 bằng keytool:

```bash
keytool -genkeypair \
  -alias api-server \
  -keyalg RSA \
  -keysize 3072 \
  -validity 365 \
  -dname "CN=api.example.com" \
  -ext "SAN=dns:api.example.com" \
  -keystore identity.p12 \
  -storetype PKCS12
```

Lệnh này tạo key pair và chứng thư tự ký ban đầu trong alias api-server. Chứng thư tự ký chỉ phù hợp cho một số môi trường thử nghiệm hoặc mô hình tin cậy được cấu hình rõ; nó không tự động được client bên ngoài tin cậy.

Để yêu cầu CA cấp chứng thư:

```bash
keytool -certreq \
  -alias api-server \
  -file api-server.csr \
  -ext "SAN=dns:api.example.com" \
  -keystore identity.p12 \
  -storetype PKCS12
```

Sau khi CA phát hành certificate reply, import chain vào đúng alias theo hướng dẫn của CA và keytool:

```bash
keytool -importcert \
  -alias api-server \
  -file api-server-reply.pem \
  -keystore identity.p12 \
  -storetype PKCS12
```

Khi import certificate reply cho alias đã chứa private key, keytool kiểm tra quan hệ giữa public key trong chứng thư và private key hiện có, rồi cập nhật certificate chain nếu phản hồi hợp lệ. Nếu import một chứng thư không khớp private key, thao tác sẽ thất bại hoặc không tạo được PrivateKeyEntry như mong đợi.

Liệt kê alias và loại entry:

```bash
keytool -list -v \
  -keystore identity.p12 \
  -storetype PKCS12
```

Kết quả cần xác nhận alias có loại PrivateKeyEntry, chain có đúng số lượng và subject/issuer đúng. Trước khi import certificate CA, xác minh nguồn gốc và fingerprint qua kênh độc lập; không tin cậy chứng thư chỉ vì keytool hiển thị lời nhắc import.

## 7. Mật khẩu bảo vệ keystore và entry

KeyStore có thể dùng mật khẩu để bảo vệ nội dung hoặc kiểm tra tính toàn vẹn. PrivateKeyEntry cũng có thể có thông tin bảo vệ riêng khi được đọc hoặc ghi qua Entry API. Cần phân biệt:

- **Keystore password:** được dùng khi nạp/lưu keystore và tùy loại store/provider có thể bảo vệ tính toàn vẹn hoặc nội dung kho.
- **Entry password:** được cung cấp để bảo vệ hoặc mở key entry cụ thể theo cơ chế của provider.
- **Application secret:** mật khẩu, token hoặc thông tin xác thực mà ứng dụng dùng để lấy quyền truy cập kho; không phải một thành phần của certificate.

Không phải mọi định dạng/provider đều hỗ trợ cùng một mô hình mật khẩu. JKS và PKCS12 có lịch sử triển khai và quy tắc riêng; một số provider yêu cầu entry password giống store password hoặc không hỗ trợ mật khẩu entry độc lập theo cách ứng dụng kỳ vọng. Cần kiểm thử với đúng JDK, provider và định dạng triển khai.

Mật khẩu mạnh không thay thế bảo vệ file và quyền truy cập. Nếu kẻ tấn công có thể đọc file keystore và biết hoặc đoán được mật khẩu, private key có thể bị lấy ra. Nếu tiến trình ứng dụng bị chiếm quyền trong lúc khóa được mở, kẻ tấn công có thể gọi thao tác ký/giải mã ngay cả khi không thể export key material.

Các nguyên tắc bảo vệ:

- Không hard-code mật khẩu trong source code, Dockerfile, image layer hoặc file cấu hình được commit.
- Lấy bí mật từ secret manager hoặc cơ chế cấp phát danh tính workload.
- Giới hạn quyền đọc/ghi file keystore cho đúng tài khoản dịch vụ.
- Bảo vệ thư mục cha, bản backup, artifact và kênh phân phối.
- Không ghi mật khẩu, private key hoặc nội dung keystore vào log.
- Tách quyền quản trị keystore khỏi quyền sử dụng private key nếu nền tảng hỗ trợ.
- Rotate mật khẩu theo policy và xử lý các bản backup có thể vẫn dùng mật khẩu cũ.

## 8. PKCS12, JKS và lựa chọn định dạng

Java hỗ trợ nhiều loại KeyStore thông qua provider. Tên loại store là loại được truyền vào KeyStore.getInstance(), không phải tên của entry.

| Loại | Đặc điểm | Lưu ý |
|---|---|---|
| PKCS12 | Định dạng trao đổi khóa/chứng thư tiêu chuẩn, thường dùng cho private key và certificate chain | Là lựa chọn phổ biến cho ứng dụng Java hiện đại; cần kiểm tra tương thích provider và công cụ |
| JKS | Định dạng keystore truyền thống của Java | Có thể gặp trong hệ thống cũ; nên đánh giá khả năng chuyển đổi theo policy |
| JCEKS | Provider/định dạng Java hỗ trợ thêm loại secret key entry | Không nên chọn chỉ vì tên; cần đánh giá khả năng tương thích và yêu cầu bảo vệ |
| PKCS11 | Giao diện tới token/HSM thông qua provider PKCS#11 | Key material có thể nằm trong phần cứng; alias thường ánh xạ tới object/label của token |

PKCS12 và JKS là loại KeyStore; PrivateKeyEntry là loại entry bên trong KeyStore. Không nên gọi một file .p12 là “PrivateKeyEntry”: file có thể chứa nhiều alias và nhiều loại entry.

Khi chuyển JKS sang PKCS12, cần kiểm kê alias, entry type, certificate chain và khả năng truy cập private key trước và sau chuyển đổi. Một lệnh chuyển đổi thường dùng:

```bash
keytool -importkeystore \
  -srckeystore legacy.jks \
  -srcstoretype JKS \
  -destkeystore identity.p12 \
  -deststoretype PKCS12
```

Sau khi chuyển đổi, phải kiểm tra lại bằng keytool và ứng dụng thực tế. Không xóa bản cũ trước khi xác nhận bản mới chứa đủ entry và có thể được runtime sử dụng.

## 9. PrivateKeyEntry và HSM/PKCS#11

PrivateKeyEntry không nhất thiết có nghĩa private key được lưu dưới dạng byte trong một file. Với HSM hoặc token, Java provider có thể biểu diễn khóa bằng một đối tượng PrivateKey gắn với key object trong thiết bị. Ứng dụng gọi thao tác ký thông qua provider; private key không cần rời khỏi HSM.

Một mô hình thường gặp:

1. HSM tạo key pair bên trong thiết bị.
2. Public key được xuất để tạo CSR.
3. CA cấp certificate cho public key.
4. Certificate chain được import hoặc liên kết với key object trong token.
5. Java KeyStore provider hiển thị alias tương ứng dưới dạng PrivateKeyEntry.
6. Ứng dụng lấy PrivateKey handle và dùng Signature hoặc TLS provider để thực hiện thao tác.

Ví dụ cấu hình provider PKCS#11 phụ thuộc thiết bị và nhà cung cấp. Một số môi trường dùng cấu hình provider trong file, một số dùng API Security.addProvider hoặc cấu hình runtime. Loại store thường là PKCS11 và KeyStore được truy cập qua provider tương ứng.

Không phải mọi HSM/provider đều hỗ trợ đầy đủ mọi thao tác KeyStore hoặc cùng quy tắc alias. Cần kiểm tra khả năng tạo key, import certificate chain, lấy PrivateKey handle, ký thuật toán yêu cầu, phân quyền PIN/session và audit theo tài liệu thiết bị.

HSM bảo vệ key material ở tầng thiết bị nhưng không tự giải quyết mọi rủi ro ứng dụng. Nếu tài khoản dịch vụ có quyền ký tùy ý, tiến trình bị chiếm quyền vẫn có thể lạm dụng HSM như một signing oracle. Cần giới hạn operation, key usage, principal, context và phê duyệt theo yêu cầu.

## 10. Sử dụng PrivateKeyEntry trong TLS

Khi Java server thiết lập TLS, KeyManager thường lấy private key và certificate chain từ identity keystore. TrustManager dùng trust store để xác minh chứng thư của peer. Hai chức năng có vai trò khác nhau:

- KeyManager chọn alias/PrivateKeyEntry phù hợp để chứng minh danh tính server hoặc client.
- TrustManager xác minh certificate chain của peer dựa trên trust anchors và policy.

Một ví dụ nạp identity keystore vào KeyManagerFactory:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;

public final class ServerTlsContext {
    public static SSLContext create(
            Path identityPath, char[] storePassword) throws Exception {
        KeyStore identity = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(identityPath)) {
            identity.load(input, storePassword);
        }

        KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keyManagers.init(identity, storePassword);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keyManagers.getKeyManagers(), null, null);
        return context;
    }
}
```

Đây là ví dụ rút gọn cho identity keystore. Ứng dụng production cần cấu hình trust managers phù hợp, hostname verification ở client, protocol/cipher policy, quản lý mật khẩu và xử lý lỗi. Nếu keystore chứa nhiều PrivateKeyEntry, cần bảo đảm KeyManager chọn đúng alias theo hostname, thuật toán và mục đích.

Với mTLS, server cũng cần trust store để xác minh client certificate. Nạp identity keystore không tự động khiến server tin cậy mọi client; trust policy là cấu hình riêng.

## 11. Dùng PrivateKeyEntry để ký số

PrivateKeyEntry cũng thường được dùng khi ứng dụng ký dữ liệu. Java Signature API nhận private key và thực hiện thuật toán ký đã chọn. Ví dụ minh họa:

```java
import java.security.PrivateKey;
import java.security.Signature;

public final class DocumentSigner {
    public static byte[] sign(byte[] data, PrivateKey privateKey)
            throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(data);
        return signature.sign();
    }
}
```

Thuật toán phải phù hợp với loại private key, policy và định dạng chữ ký. Với EC, dùng thuật toán chữ ký tương ứng; không dùng tên thuật toán RSA cho EC key. Ứng dụng cần ghi nhận key ID/alias, certificate serial hoặc fingerprint, thời điểm và mục đích ký để hỗ trợ kiểm toán.

Không nên cho phép mọi thành phần ứng dụng tùy ý lấy PrivateKeyEntry rồi ký dữ liệu không giới hạn. Có thể đóng gói thao tác ký trong một service riêng, kiểm tra quyền gọi, loại dữ liệu và policy trước khi dùng khóa.

## 12. Quản lý nhiều PrivateKeyEntry và chọn alias

Một keystore có thể chứa nhiều danh tính, chẳng hạn certificate cho API public, API nội bộ, client mTLS và code signing. Ứng dụng cần chọn alias rõ ràng thay vì dựa vào entry đầu tiên hoặc thứ tự liệt kê.

Quy trình lựa chọn nên:

1. Xác định mục đích và peer cần xác thực.
2. Lọc entry có private key và certificate chain hợp lệ.
3. Kiểm tra public key algorithm và key usage phù hợp.
4. Kiểm tra SAN hoặc subject nếu dùng cho TLS server.
5. Kiểm tra thời hạn và trạng thái certificate.
6. Chọn alias theo policy rõ ràng, có log về định danh không bí mật.

Nếu ứng dụng dùng alias cố định trong cấu hình, thay đổi alias trong lần deploy có thể làm TLS handshake thất bại. Khi rotation, cần cập nhật alias hoặc dùng cơ chế chọn entry theo metadata được kiểm soát.

## 13. Backup, rotation và destruction của PrivateKeyEntry

PrivateKeyEntry chứa private key nên việc backup và sao chép phải được quản lý như thao tác đối với key material. Không nên sao chép keystore sang nhiều máy chỉ để đơn giản hóa triển khai nếu có thể dùng HSM/KMS hoặc cơ chế cấp phát khóa phù hợp hơn.

Khi backup được phép:

- Dùng phương thức backup được provider hỗ trợ.
- Bảo vệ bản sao bằng wrapping key độc lập hoặc cơ chế mã hóa phù hợp.
- Giới hạn người có quyền restore và sử dụng entry.
- Lưu backup ở miền lỗi riêng, ghi nhận alias, phiên bản và thời hạn.
- Diễn tập restore trong môi trường kiểm soát.
- Xử lý cả backup, replica và bản export khi hủy key.

Khi rotation:

1. Tạo key pair mới.
2. Yêu cầu CA cấp certificate mới.
3. Tạo PrivateKeyEntry mới với alias/version phù hợp.
4. Kiểm tra certificate chain và private key tương ứng.
5. Triển khai dần sang entry mới và xác minh mọi endpoint.
6. Retire entry cũ sau khi không còn phụ thuộc.
7. Revoke certificate cũ nếu có compromise hoặc policy yêu cầu.
8. Hủy private key cũ và các bản sao khi không còn nhu cầu lưu giữ.

Không xóa alias cũ ngay sau khi tạo alias mới. Các instance, client pinning hoặc quy trình giải mã lịch sử có thể còn phụ thuộc. Ngược lại, giữ private key cũ không giới hạn thời gian làm tăng bề mặt tấn công.

## 14. Các lỗi thường gặp

- **Alias không tồn tại:** ứng dụng tham chiếu sai tên hoặc file keystore không đúng phiên bản.
- **Entry không phải PrivateKeyEntry:** alias trỏ tới TrustedCertificateEntry hoặc loại khác, nên không thể lấy private key.
- **Certificate không khớp private key:** certificate reply được import cho sai key pair hoặc nhầm alias.
- **Chain thiếu intermediate:** peer không thể xây dựng đường dẫn chứng thư tới trust anchor.
- **Sai mật khẩu hoặc provider:** keystore không load được hoặc entry không mở được.
- **Nhầm store password và entry password:** ứng dụng hoạt động với provider này nhưng lỗi khi chuyển định dạng/provider.
- **Dùng trust store làm identity keystore:** ứng dụng không có private key để chứng minh danh tính.
- **Chọn alias không xác định:** ứng dụng có thể lấy nhầm certificate khi có nhiều entry.
- **Hard-code mật khẩu:** bí mật bị lộ qua source code, artifact hoặc log.
- **Cho rằng HSM ngăn mọi lạm dụng:** ứng dụng vẫn có thể gọi thao tác ký nếu principal bị chiếm quyền.
- **Sao chép keystore không kiểm soát:** tạo thêm nhiều bản private key ngoài inventory.
- **Xóa entry nhưng bỏ quên backup:** private key vẫn có thể được phục hồi từ bản sao.

## 15. Checklist vận hành PrivateKeyEntry

- [ ] Alias được đặt tên rõ ràng và được quản lý trong inventory.
- [ ] Entry được xác nhận đúng loại PrivateKeyEntry.
- [ ] Private key và public key trong leaf certificate là một cặp tương ứng.
- [ ] Certificate chain đúng thứ tự và có đủ intermediate cần thiết.
- [ ] Subject/SAN, EKU, Key Usage, validity và issuer phù hợp mục đích.
- [ ] Định dạng và provider được chọn rõ ràng, có kiểm thử tương thích.
- [ ] Store password và entry protection được quản lý an toàn, không hard-code.
- [ ] Quyền đọc keystore và quyền sử dụng private key được giới hạn.
- [ ] HSM/KMS được cấu hình đúng nếu private key không exportable.
- [ ] TLS KeyManager hoặc signing service chọn đúng alias.
- [ ] Backup, restore, rotation và destruction có quy trình cùng người chịu trách nhiệm.
- [ ] Audit log không chứa private key hoặc mật khẩu.
- [ ] Đã kiểm thử lỗi sai alias, sai password, chain thiếu và certificate không khớp.

PrivateKeyEntry là cầu nối giữa private key và danh tính công khai được xác nhận bằng certificate chain trong Java KeyStore. Khi ứng dụng quản lý đúng alias, loại entry, thứ tự chain, cơ chế bảo vệ và provider, nó có thể dùng private key đúng mục đích mà vẫn duy trì khả năng xác minh danh tính. Vòng đời của entry cần gắn với vòng đời của key pair và certificate: tạo, cấp, triển khai, sử dụng, backup nếu được phép, rotation, retirement và destruction phải có kiểm soát cùng bằng chứng.
