# Key store

**Key store** là kho hoặc giao diện quản lý dùng để lưu giữ, tra cứu và cung cấp quyền sử dụng các đối tượng mật mã như private key, secret key, certificate và certificate chain. Ứng dụng truy cập key store thông qua alias, key identifier hoặc API của nền tảng thay vì tự quản lý các byte khóa ở mọi nơi.

Trong quản lý khóa mật mã, key store là một thành phần của vòng đời khóa: tạo hoặc tiếp nhận khóa, lưu trữ, cấp quyền sử dụng, phân phối certificate, sao lưu, xoay vòng, thu hồi và hủy. Key store có thể là một file PKCS#12, kho certificate của hệ điều hành, Java KeyStore, Android Keystore, thiết bị HSM hoặc một dịch vụ KMS trên cloud. Vì vậy, từ “key store” mô tả vai trò lưu giữ và truy cập khóa; nó không nhất thiết chỉ một định dạng file cụ thể.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, kết nối key store với mật mã đối xứng, bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Key store giải quyết vấn đề gì?

Một ứng dụng cần dùng khóa để mã hóa, giải mã, ký hoặc xác minh. Nếu mỗi thành phần tự lưu khóa trong source code, file cấu hình hay thư mục riêng, tổ chức sẽ khó kiểm soát ai được sử dụng khóa, khóa nào đang hoạt động, khóa đã hết hạn hay chưa và làm thế nào thu hồi hoặc thay thế khóa khi có sự cố.

Key store cung cấp một điểm quản lý có cấu trúc:

- Lưu khóa và certificate theo định danh rõ ràng.
- Tách việc sử dụng khóa khỏi việc đọc trực tiếp vật liệu khóa.
- Hỗ trợ kiểm soát truy cập theo ứng dụng, người dùng, vai trò hoặc thiết bị.
- Liên kết private key với certificate và certificate chain tương ứng.
- Cho phép ứng dụng chọn đúng khóa hoặc phiên bản qua alias/key ID.
- Hỗ trợ backup, restore, xoay vòng và kiểm toán theo khả năng của nền tảng.

Ví dụ, một máy chủ HTTPS cần private key để ký thông điệp trong TLS handshake và certificate để cung cấp danh tính. Ứng dụng có thể tải certificate từ key store, còn private key được gọi qua provider. Với HSM-backed key store, private key có thể không bao giờ rời thiết bị; ứng dụng chỉ yêu cầu HSM thực hiện thao tác ký.

## 2. Key store chứa những loại entry nào?

Một key store có thể chứa nhiều loại đối tượng. Trong Java KeyStore API, các loại entry thường gặp là:

| Loại entry | Nội dung | Mục đích |
|---|---|---|
| PrivateKeyEntry | Private key và certificate chain gắn với public key tương ứng | TLS server/client authentication, ký số và các tác vụ cần private key. |
| SecretKeyEntry | Khóa đối xứng như AES hoặc HMAC key | Mã hóa, giải mã, MAC hoặc bảo vệ dữ liệu. |
| TrustedCertificateEntry | Certificate công khai được cấu hình là đáng tin cậy | Lưu trust anchor hoặc certificate phục vụ xác minh. |

Không phải mọi nền tảng đều có đúng các loại entry hoặc cùng cách biểu diễn. HSM/KMS có thể lưu key object, certificate object, policy và metadata riêng. Một số nền tảng chỉ lưu handle/alias ở phía ứng dụng, trong khi vật liệu khóa thực tế nằm trong thiết bị hoặc dịch vụ từ xa.

Certificate thường chứa public key và metadata công khai. Private key và secret key là bí mật cần bảo vệ. Khi kiểm kê, phải phân loại từng entry để đặt quyền truy cập, chính sách backup và thời hạn lưu giữ phù hợp.

## 3. Key store khác trust store như thế nào?

Hai khái niệm thường được nhắc cùng nhau trong TLS nhưng có vai trò khác nhau:

- **Key store** thường giữ private key của chính ứng dụng hoặc chủ thể, cùng certificate và chain của nó.
- **Trust store** giữ trust anchor hoặc certificate mà ứng dụng dùng để xác minh đối tác.

Ví dụ khi một Java service hoạt động như TLS server, nó cần private key và certificate của chính nó từ key store. Khi service đó kết nối đến một HTTPS API khác, nó cần trust store để xác minh certificate của API đối tác.

| Tình huống | Key store | Trust store |
|---|---|---|
| Server cung cấp danh tính TLS | Private key và certificate của server | Có thể không cần nếu không xác thực client certificate. |
| Client xác thực server | Có thể không cần private key client nếu không dùng mutual TLS | Root/intermediate trust anchors để xác minh server. |
| Mutual TLS | Private key và certificate của client/server tương ứng | Trust anchors để xác minh certificate của bên kia. |
| Xác minh chữ ký tài liệu | Private key nếu cần ký tài liệu mới | Certificate/public key đáng tin cậy để xác minh người ký. |

Một file có thể được cấu hình làm key store hoặc trust store tùy cách ứng dụng sử dụng; tên file không quyết định vai trò. Không đưa private key của ứng dụng vào trust store chỉ vì đó là nơi đang chứa certificate.

~~~mermaid
flowchart TD
    A["Ứng dụng TLS"] --> B["Key store của chính ứng dụng"]
    B --> C["Private key + certificate"]
    A --> D["Trust store"]
    D --> E["Trust anchors / CA certificates"]
    C --> F["Chứng minh quyền kiểm soát private key"]
    E --> G["Xác minh certificate của đối tác"]
~~~

## 4. Key store là định dạng file hay dịch vụ?

Key store có thể được triển khai ở nhiều lớp:

| Kiểu triển khai | Ví dụ | Đặc điểm |
|---|---|---|
| File-based key store | PKCS#12, JKS | Dễ triển khai và di chuyển; bảo mật phụ thuộc mã hóa file, mật khẩu, quyền filesystem và cách backup. |
| OS certificate/key store | Windows Certificate Store, Apple Keychain | Tích hợp danh tính người dùng/máy, quyền của hệ điều hành và phần cứng hỗ trợ. |
| Application/platform keystore | Java KeyStore, Android Keystore | Cung cấp API chuẩn hoặc API nền tảng để ứng dụng truy cập key entry. |
| Hardware-backed key store | HSM, TPM hoặc Secure Enclave | Có thể tạo và sử dụng khóa trong vùng phần cứng, hạn chế export vật liệu khóa. |
| Managed key service | Cloud KMS hoặc dịch vụ quản lý khóa doanh nghiệp | Quản lý key object, policy, phiên bản, audit và thao tác mật mã qua API. |

Một key store API có thể là lớp trừu tượng phía trên nhiều backend. Ví dụ, Java KeyStore có thể đọc file PKCS#12, nhưng cũng có provider tích hợp HSM hoặc thiết bị mật mã. Do đó, thấy ứng dụng dùng API KeyStore không có nghĩa private key nhất thiết được lưu trong file.

Khi thiết kế, phải xác định rõ backend thực tế, nơi vật liệu khóa tồn tại, thao tác nào có thể thực hiện, khóa có export được không và ai quản trị backend đó.

## 5. Các định dạng key store phổ biến

### PKCS#12

PKCS#12 là định dạng container tiêu chuẩn thường dùng để đóng gói certificate, private key và certificate chain. File thường có đuôi .p12 hoặc .pfx. Container có thể được bảo vệ bằng mật khẩu và cơ chế mã hóa/kiểm tra tính toàn vẹn.

PKCS#12 thuận tiện cho triển khai TLS và trao đổi certificate cùng private key, nhưng file chứa private key phải được xem là tài sản bí mật. Nếu kẻ tấn công lấy được file và mật khẩu, khóa có thể bị lộ. Không đặt file và mật khẩu ở cùng một thư mục hoặc cùng một hệ thống backup với quyền truy cập tương đương.

### JKS

JKS (Java KeyStore) là định dạng lịch sử của Java. Nó từng phổ biến trong ứng dụng Java để lưu private key, secret key và trusted certificate. Với ứng dụng mới, PKCS#12 thường là lựa chọn tương thích tốt hơn giữa các nền tảng. Cần kiểm tra phiên bản Java và provider khi di chuyển định dạng.

### JCEKS và định dạng khác

JCEKS từng được dùng để lưu secret key trong hệ sinh thái Java. Đây là định dạng cũ; không nên chọn cho thiết kế mới nếu có định dạng/provider hiện đại được hỗ trợ. Một số nền tảng có định dạng riêng, chẳng hạn Android Keystore hoặc kho khóa do nhà cung cấp HSM quản lý.

| Định dạng/loại | Thường dùng cho | Lưu ý |
|---|---|---|
| PKCS#12 | Private key, certificate và chain | Phổ biến, có thể mang private key ra ngoài nếu export được. |
| JKS | Ứng dụng Java cũ, trusted certificates và key entries | Cần đánh giá khi di chuyển hệ thống legacy. |
| JCEKS | Secret key trong ứng dụng Java cũ | Kiểm tra khả năng tương thích và chính sách mật mã trước khi tiếp tục sử dụng. |
| OS/Hardware store | Khóa gắn với user, device hoặc phần cứng | Quyền và tính năng phụ thuộc hệ điều hành/thiết bị. |
| KMS/HSM object store | Khóa được quản lý tập trung | Thường truy cập qua API/provider, không nhất thiết có file key store. |

Định dạng và provider là hai khái niệm riêng. Một file PKCS#12 mô tả cách đóng gói dữ liệu; provider quyết định cách Java hoặc ứng dụng đọc và thao tác với nội dung đó.

## 6. Alias, key ID và metadata

Ứng dụng cần một định danh ổn định để tìm đúng entry. Trong Java KeyStore, định danh thường là **alias**. Trong KMS/HSM, hệ thống có thể dùng key ID, URI, object handle hoặc tên tài nguyên.

Metadata nên giúp xác định:

- Chủ sở hữu (key owner) và ứng dụng được phép dùng khóa.
- Mục đích: TLS, ký số, mã hóa dữ liệu, HMAC hoặc xác minh.
- Thuật toán, độ dài khóa/đường cong và thuộc tính exportability.
- Phiên bản, thời điểm tạo, kích hoạt, hết hạn và trạng thái.
- Certificate fingerprint, serial number, issuer và chain nếu có.
- Vị trí backend, môi trường, tenant và chính sách truy cập.
- Quan hệ giữa KEK, DEK và dữ liệu được bảo vệ.

Alias không phải bằng chứng về danh tính hay tính toàn vẹn. Hai key store khác nhau có thể dùng cùng alias cho hai khóa hoàn toàn khác nhau. Không nên dùng alias làm định danh duy nhất xuyên môi trường; cần gắn nó với key store/provider, key ID hoặc fingerprint phù hợp.

Với dữ liệu đã mã hóa, cần lưu key ID và version chính xác cùng ciphertext hoặc DEK đã bọc. Nếu alias trỏ sang phiên bản mới sau khi xoay vòng, dữ liệu cũ vẫn phải có cách tìm được phiên bản cũ để giải mã.

## 7. Mật khẩu key store bảo vệ được điều gì?

File-based key store thường dùng mật khẩu để mở container hoặc bảo vệ entry. Mật khẩu có thể tham gia dẫn xuất khóa mã hóa và kiểm tra tính toàn vẹn. Tuy nhiên, mật khẩu không thay thế toàn bộ biện pháp bảo vệ:

- Người có quyền đọc file vẫn có thể sao chép file để thử tấn công offline.
- Mật khẩu yếu hoặc bị lộ làm mất hiệu quả bảo vệ.
- Nếu file và mật khẩu được lưu cùng một nơi, kẻ tấn công có thể lấy cả hai.
- Nếu tiến trình ứng dụng bị xâm nhập khi key store đang mở, khóa có thể bị lạm dụng qua API hoặc bị trích xuất tùy provider.
- Mật khẩu trong command line, environment dump, log hoặc source code có thể bị lộ.

Một số định dạng/provider có mật khẩu cấp store và mật khẩu cấp entry. Không được giả định hai mật khẩu luôn độc lập hoặc mọi định dạng đều hỗ trợ cùng semantics. Hãy kiểm tra tài liệu của provider và dùng cấu hình rõ ràng.

Với khóa quan trọng, cân nhắc HSM/KMS để giới hạn quyền sử dụng và không cho export private key. Nếu phải dùng file key store, bảo vệ file bằng quyền truy cập filesystem chặt, mã hóa thiết bị, secret management, backup có kiểm soát và giám sát truy cập.

## 8. Hardware-backed và non-exportable key

Một key store có thể chỉ lưu vật liệu khóa trong file, hoặc có thể giao tiếp với phần cứng bảo vệ khóa. HSM, TPM, Secure Enclave và Android Keystore có thể hỗ trợ tạo/giữ khóa trong vùng cách ly.

Với khóa **non-exportable**, ứng dụng không lấy được byte private key dạng rõ. Thay vào đó, ứng dụng gửi yêu cầu ký, giải mã hoặc thao tác được phép đến provider; provider thực hiện trong thiết bị và trả về kết quả.

Ưu điểm:

- Giảm khả năng private key bị sao chép khỏi vùng bảo vệ.
- Có thể ràng buộc thao tác với policy, thiết bị, người dùng hoặc trạng thái xác thực.
- Có thể cung cấp audit và kiểm soát nhiều người cho thao tác nhạy cảm.
- Hỗ trợ phân tách quyền quản trị thiết bị và quyền sử dụng khóa.

Giới hạn cần tính đến:

- Khóa có thể phụ thuộc vào thiết bị, miền bảo mật hoặc provider cụ thể.
- Backup/restore có thể yêu cầu HSM tương thích và quorum quản trị.
- Ứng dụng cần xử lý độ trễ, lỗi mạng, quota và sự cố thiết bị.
- Không thể giả định khóa non-exportable sẽ di chuyển được sang backend khác.
- API trả về key handle không có nghĩa vật liệu khóa đã được xuất.

Không đánh đồng non-exportable với an toàn tuyệt đối. Nếu ứng dụng bị chiếm quyền, kẻ tấn công vẫn có thể gọi API ký hoặc giải mã nếu danh tính ứng dụng được phép. Vì vậy, phải giới hạn cả quyền sử dụng khóa, không chỉ quyền export.

## 9. Key store trong Java

Java cung cấp API KeyStore để thao tác với các loại key store do provider hỗ trợ. Các thao tác phổ biến gồm:

- Tạo hoặc lấy một KeyStore instance theo loại/provider.
- Nạp store từ InputStream hoặc khởi tạo store rỗng.
- Đọc alias và loại entry.
- Lấy certificate, certificate chain hoặc key entry khi được phép.
- Thêm trusted certificate hoặc lưu key entry theo policy.
- Ghi store ra OutputStream khi backend hỗ trợ.

Với file PKCS#12, nên chỉ định rõ loại store thay vì phụ thuộc giá trị mặc định của runtime. Ví dụ dưới đây minh họa cách nạp file, lấy private key và certificate theo alias. Mật khẩu được truyền vào từ một nguồn bí mật do ứng dụng quản lý; ví dụ không ghi mật khẩu vào source code.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Arrays;

public final class KeyStoreReader {
    public static void inspectEntry(
            Path storePath,
            String alias,
            char[] storePassword,
            char[] entryPassword) throws Exception {

        try {
            KeyStore keyStore = KeyStore.getInstance("PKCS12");

            try (InputStream input = Files.newInputStream(storePath)) {
                keyStore.load(input, storePassword);
            }

            if (!keyStore.containsAlias(alias)) {
                throw new IllegalArgumentException("Unknown key alias");
            }

            if (!keyStore.isKeyEntry(alias)) {
                throw new IllegalStateException("Alias is not a key entry");
            }

            Key key = keyStore.getKey(alias, entryPassword);
            if (!(key instanceof PrivateKey)) {
                throw new IllegalStateException("Entry is not a private key");
            }

            Certificate certificate = keyStore.getCertificate(alias);
            if (!(certificate instanceof X509Certificate x509)) {
                throw new IllegalStateException("Missing X.509 certificate");
            }

            Certificate[] chain = keyStore.getCertificateChain(alias);
            System.out.println("Key algorithm: " + key.getAlgorithm());
            System.out.println("Certificate subject: "
                    + x509.getSubjectX500Principal());
            System.out.println("Certificate chain length: "
                    + (chain == null ? 0 : chain.length));

            // Do not call key.getEncoded() or print private-key material.
        } finally {
            Arrays.fill(storePassword, '\0');
            Arrays.fill(entryPassword, '\0');
        }
    }
}
~~~

Đây là ví dụ đọc entry để minh họa API. Trong ứng dụng thật, cần xử lý ngoại lệ, nguồn mật khẩu, quyền file, audit và vòng đời object phù hợp. Xóa nội dung mảng char sau khi dùng giúp giảm thời gian giữ mật khẩu trong mảng do ứng dụng quản lý, nhưng không bảo đảm mọi bản sao trong JVM/provider đã biến mất. Một số provider có thể tạo bản sao nội bộ.

Không gọi getEncoded() để lấy byte private key chỉ nhằm kiểm tra. Với provider HSM, key object có thể là handle không export được; ứng dụng nên dùng key object qua API ký hoặc API mật mã được hỗ trợ.

## 10. Dùng key store trong TLS Java

Java thường kết hợp KeyStore, KeyManagerFactory, TrustManagerFactory và SSLContext để thiết lập TLS:

- KeyStore chứa private key và certificate của ứng dụng khi cần chứng minh danh tính.
- KeyManagerFactory tạo key managers để TLS chọn certificate/private key phù hợp.
- TrustStore được nạp vào TrustManagerFactory để xác minh certificate của đối tác.
- SSLContext kết hợp key managers và trust managers để tạo kết nối TLS.

Ví dụ cấu hình logic:

~~~java
KeyStore identityStore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(identityPath)) {
    identityStore.load(in, identityPassword);
}

KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(identityStore, identityEntryPassword);

KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(trustPath)) {
    trustStore.load(in, trustPassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(
        keyManagers.getKeyManagers(),
        trustManagers.getTrustManagers(),
        null);
~~~

Đoạn mã chỉ thể hiện mối quan hệ giữa các thành phần; ứng dụng cần quản lý password lifecycle, chọn protocol/cipher policy phù hợp, hostname verification và xử lý certificate status theo yêu cầu. Không tắt hostname verification hoặc cài trust-all TrustManager để làm cho kết nối “chạy được”.

## 11. Quyền truy cập và phân tách trách nhiệm

Key store cần bảo vệ cả quyền đọc file lẫn quyền thực hiện thao tác mật mã. Một chính sách tốt phân biệt:

| Quyền | Khả năng | Cách kiểm soát |
|---|---|---|
| List/Discover | Liệt kê alias, key ID hoặc metadata | Chỉ cấp cho công cụ kiểm kê cần thiết. |
| Read certificate/public key | Đọc dữ liệu công khai | Có thể cấp rộng hơn nhưng cần kiểm tra tính toàn vẹn và nguồn gốc. |
| Use key | Sign, decrypt, unwrap hoặc encrypt | Giới hạn theo workload, purpose, tenant và resource. |
| Export key | Xuất vật liệu khóa | Tắt mặc định; chỉ bật theo quy trình đặc biệt được phê duyệt. |
| Create/import | Tạo hoặc nhập khóa | Giới hạn theo key owner và quy trình provisioning. |
| Rotate/Disable/Revoke | Thay đổi trạng thái hoặc phiên bản | Tách quyền vận hành khỏi quyền sử dụng thường ngày. |
| Delete/Destroy | Hủy key object hoặc vật liệu khóa | Yêu cầu phê duyệt độc lập, dual control/quorum và audit. |
| Administer store | Thay đổi cấu hình, provider, policy hoặc quyền | Không mặc định cho ứng dụng runtime. |

Ứng dụng thường chỉ cần quyền dùng khóa trong phạm vi hẹp. Nó không cần quyền export, xóa hoặc thay đổi policy của key store. Người quản trị hạ tầng không nhất thiết phải có quyền dùng private key để ký tài liệu hoặc giải mã dữ liệu nghiệp vụ.

Trong môi trường nhiều tenant, policy phải ràng buộc key với tenant, mục đích, ứng dụng và resource. Không dựa vào alias do client gửi mà không xác minh quyền truy cập.

## 12. Key store và KMS/HSM

Key store thường cung cấp cách lưu và tra cứu khóa; KMS/HSM bổ sung khả năng quản lý vòng đời, policy và thực hiện thao tác mật mã trong môi trường kiểm soát.

| Thành phần | Vai trò chính |
|---|---|
| Key store file | Lưu entry trong container/file, thường do ứng dụng hoặc hệ điều hành mở. |
| KMS | Quản lý key object, version, policy, audit và API cryptographic operations. |
| HSM | Thiết bị hoặc dịch vụ phần cứng bảo vệ vật liệu khóa và thực hiện thao tác mật mã trong miền bảo mật. |
| Key store provider | Adapter nối API ứng dụng với file, OS store, HSM hoặc KMS. |

Một số KMS có thể dùng HSM làm nền tảng bảo vệ khóa gốc. Một số HSM có provider để ứng dụng dùng qua Java Cryptography Architecture (JCA/JCE). Tuy nhiên, khả năng tương thích, thuật toán, exportability, backup và semantics của từng thao tác phụ thuộc nhà cung cấp.

Khi lựa chọn, hãy xác minh:

- Khóa được tạo ở đâu và vật liệu khóa có rời backend không.
- Provider có hỗ trợ thuật toán và thao tác ứng dụng cần không.
- Quyền được đánh giá theo IAM, policy thiết bị hay cả hai.
- Có hỗ trợ versioning, rotation, disable, revoke và destroy không.
- Backup/restore cần cùng thiết bị, miền bảo mật hoặc quorum nào.
- Audit log có đủ danh tính, key ID, operation và kết quả không.
- Hệ thống xử lý thế nào khi backend mất kết nối hoặc vượt quota.

## 13. Key store trong envelope encryption

Với envelope encryption, dữ liệu thường được mã hóa bằng Data Encryption Key (DEK), còn DEK được bọc bởi Key Encryption Key (KEK). Key store hoặc KMS giữ KEK và cung cấp thao tác wrap/unwrap.

~~~mermaid
flowchart TD
    A["Ứng dụng yêu cầu mã hóa"] --> B["Tạo hoặc lấy DEK"]
    B --> C["Mã hóa dữ liệu bằng DEK"]
    B --> D["Yêu cầu key store/KMS wrap DEK"]
    D --> E["KEK trong key store"]
    C --> F["Ciphertext"]
    D --> G["Wrapped DEK + key ID/version"]
    F --> H["Lưu dữ liệu và metadata"]
    G --> H
~~~

Ứng dụng lưu ciphertext cùng DEK đã được bọc và metadata cần thiết. Khi đọc, ứng dụng lấy đúng key ID/version để unwrap DEK rồi giải mã ciphertext.

Key store cần hỗ trợ định danh phiên bản rõ ràng. Nếu chỉ lưu alias chung và alias bị trỏ sang KEK mới, ứng dụng vẫn phải biết phiên bản KEK cũ để mở DEK đã bọc trước đó. Xoay vòng KEK không đồng nghĩa có thể xóa ngay phiên bản cũ.

Không lưu DEK dạng rõ vào key store chỉ để thuận tiện nếu có thể giữ DEK trong bộ nhớ giới hạn thời gian và bọc nó bằng KEK. Ngược lại, nếu DEK được giữ trong key store, phải áp dụng quyền truy cập, backup và retention tương ứng.

## 14. Nạp key store an toàn

Quy trình nạp key store cần bảo đảm đúng file, đúng định dạng, đúng mật khẩu và đúng nguồn gốc:

1. Xác định loại store/provider một cách rõ ràng, ví dụ PKCS#12 hoặc HSM provider.
2. Lấy file từ vị trí tin cậy với quyền filesystem tối thiểu.
3. Lấy mật khẩu hoặc credential từ secret manager/identity provider phù hợp.
4. Xác minh file và certificate metadata nếu quy trình yêu cầu.
5. Nạp store, kiểm tra alias, loại entry, certificate chain và thời hạn.
6. Chỉ cung cấp key object cho thành phần cần sử dụng.
7. Ghi audit về hoạt động truy cập mà không ghi password hoặc vật liệu khóa.
8. Đóng stream và giải phóng tài nguyên; hạn chế thời gian giữ credential trong bộ nhớ.

Nếu file key store bị thay thế bởi một file giả, ứng dụng có thể dùng private key của kẻ tấn công. Vì vậy, cần kiểm soát tính toàn vẹn của artifact, quyền ghi thư mục, nguồn phân phối và quy trình deploy. Hash của file chỉ hữu ích khi giá trị hash được lấy từ một kênh tin cậy.

## 15. Backup và restore key store

Backup key store có thể chứa private key và secret key, nên phải được phân loại theo mức nhạy cảm của entry bên trong. Một bản backup key store bị lộ cùng mật khẩu có thể tương đương với việc làm lộ private key.

Trước khi backup:

- Xác định entry nào được phép backup và entry nào không được export.
- Mã hóa backup bằng cơ chế được phê duyệt và khóa bảo vệ độc lập.
- Lưu metadata, alias, key ID/version và certificate chain cần để khôi phục.
- Tách quyền tạo backup, đọc backup và restore.
- Lưu bản sao trong miền lỗi khác khi yêu cầu DR đòi hỏi.
- Không lưu password cạnh file backup hoặc trong cùng log/ticket.

Khi restore:

1. Xác minh nguồn gốc, tính toàn vẹn và phiên bản backup.
2. Xác minh người phê duyệt và quyền restore.
3. Khôi phục vào key store/provider đúng loại và miền bảo mật.
4. Kiểm tra alias, key ID/version, certificate chain và policy.
5. Thử thao tác mật mã bằng dữ liệu kiểm thử.
6. Kiểm tra audit và cập nhật inventory.

Với HSM/KMS non-exportable key, không thể giả định có thể sao chép file store sang thiết bị khác. Hãy dùng backup/clone/replication chính thức của nền tảng và xác minh các điều kiện tương thích trước khi đưa vào sản xuất.

## 16. Xoay vòng và cập nhật key store

Khi khóa đến hạn hoặc cần thay thế, quy trình xoay vòng có thể tạo entry hoặc key version mới, cập nhật certificate và chuyển ứng dụng sang dùng khóa mới.

Các bước thường gồm:

1. Tạo khóa mới theo policy và mục đích đã phê duyệt.
2. Tạo CSR và xin certificate mới nếu khóa dùng cho PKI.
3. Thêm entry mới vào key store hoặc tạo key object mới trong KMS/HSM.
4. Cập nhật ứng dụng để dùng alias/version mới cho thao tác mới.
5. Giữ khả năng truy cập khóa cũ cho dữ liệu hoặc chữ ký còn phụ thuộc nếu cần.
6. Rewrap hoặc re-encrypt dữ liệu theo kế hoạch.
7. Thu hồi certificate cũ hoặc ngừng sử dụng khóa theo chính sách.
8. Xóa/hủy bản sao cũ sau khi xác nhận không còn phụ thuộc.

Không ghi đè entry đang dùng bằng một khóa khác mà không có migration plan. Nếu nhiều instance cập nhật không đồng thời, hệ thống có thể ký bằng hai khóa khác nhau hoặc không thể giải mã dữ liệu vừa ghi. Dùng version rõ ràng và chiến lược rollout/rollback.

## 17. Thu hồi certificate và hủy key store entry

Thu hồi certificate và xóa entry khỏi key store là hai hành động khác nhau:

- Revoke certificate thay đổi trạng thái tin cậy được CA công bố qua CRL/OCSP.
- Xóa alias có thể chỉ loại bỏ tham chiếu hoặc entry khỏi một key store cụ thể.
- Destroy key material yêu cầu hủy vật liệu khóa theo semantics của backend và mọi bản sao cần xử lý.

Xóa alias không bảo đảm private key biến mất khỏi file backup, snapshot, HSM backup blob hoặc một key store khác. Ngược lại, xóa certificate khỏi trust store không tự động xóa private key tương ứng trong key store của chủ thể.

Khi private key bị compromise, cần cô lập quyền sử dụng, revoke certificate, tạo key pair mới, cập nhật hệ thống phụ thuộc và xử lý bản sao khóa cũ theo incident/key destruction procedure. Nếu chỉ xóa entry khỏi một file nhưng backup cũ vẫn có thể restore, khóa bị lộ có thể quay lại hoạt động.

## 18. Quản lý nhiều môi trường và nhiều tenant

Không nên dùng một key store và một bộ credential chung cho development, staging và production. Việc tách môi trường giúp giảm nguy cơ một tài khoản hoặc một file bị lộ ảnh hưởng toàn bộ hệ thống.

Với kiến trúc nhiều tenant:

- Dùng key riêng theo tenant hoặc phạm vi chia sẻ được phê duyệt.
- Ràng buộc thao tác với tenant ID và resource context.
- Kiểm tra quyền ở backend; không tin alias hoặc key ID do client tùy ý truyền.
- Tách policy export, decrypt, sign và admin theo tenant.
- Audit cả danh tính workload, tenant, key version và operation.
- Xác minh backup/restore không làm trộn key giữa các tenant.

Nếu dùng chung KEK để bọc DEK cho nhiều tenant, phải có threat model và policy rõ ràng. Việc dùng chung giúp giảm số lượng key nhưng tăng blast radius khi KEK hoặc quyền truy cập bị compromise.

## 19. Giám sát và kiểm toán

Key store cần tạo đủ dấu vết để trả lời ai đã truy cập, entry nào được dùng và hành động nào đã xảy ra. Tùy backend, audit event có thể gồm:

- Danh tính người dùng hoặc workload.
- Key store/provider, alias hoặc key ID và version.
- Operation: list, read certificate, sign, decrypt, wrap, unwrap, import, export, rotate, disable hoặc destroy.
- Thời điểm, nguồn truy cập, request ID và kết quả.
- Policy/approval liên quan đến thao tác nhạy cảm.

Không ghi password, private key bytes, DEK dạng rõ hoặc secret vào log. Log cần được bảo vệ chống sửa đổi, phân quyền truy cập và giữ theo chính sách.

Các chỉ số vận hành hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| Key store load failures | Phát hiện sai mật khẩu, file hỏng, provider lỗi hoặc quyền filesystem sai. |
| Key operation errors/latency | Theo dõi sign/decrypt/wrap/unwrap và sự cố backend. |
| Certificate expiry horizon | Cảnh báo certificate sắp hết hạn. |
| Unauthorized access attempts | Phát hiện truy cập alias hoặc operation ngoài policy. |
| Key inventory coverage | Tỷ lệ entry có owner, purpose, version và trạng thái rõ ràng. |
| Backup/restore drill results | Đo khả năng phục hồi thực tế của key store. |

## 20. Những lỗi thường gặp

- Lưu password key store trong source code hoặc file cấu hình được commit.
- Đặt file key store và mật khẩu cạnh nhau với cùng quyền truy cập.
- Coi PKCS#12/JKS là an toàn tuyệt đối chỉ vì có password.
- Dùng chung key store giữa nhiều môi trường hoặc tenant mà không có phân tách.
- Cấp quyền export private key cho ứng dụng chỉ cần ký hoặc giải mã.
- Nhầm key store với trust store và cài trust-all certificate validation.
- Dùng alias làm định danh duy nhất mà không quản lý provider và version.
- Ghi đè entry đang hoạt động khi xoay vòng, làm ứng dụng không thể giải mã dữ liệu cũ.
- Xóa alias nhưng bỏ qua backup, snapshot, replica và HSM backup blob.
- Cho rằng non-exportable key không thể bị lạm dụng qua API.
- Không kiểm thử restore hoặc không xác minh certificate chain sau khi restore.
- Không phân biệt revoke certificate, disable key và destroy key material.
- Không audit thao tác ký, giải mã, export và thay đổi policy.

## 21. Ví dụ: key store cho một Java HTTPS service

Một Java service cung cấp HTTPS và gọi đến một API nội bộ khác:

1. Đội nền tảng tạo private key của service trong HSM hoặc file PKCS#12 được bảo vệ.
2. CA phát hành certificate có SAN đúng với tên service.
3. Key store của service chứa private key và certificate chain.
4. Trust store chứa CA certificate được phép xác minh API nội bộ.
5. Java KeyManagerFactory lấy danh tính server từ key store.
6. TrustManagerFactory xác minh certificate của API đối tác.
7. IAM và filesystem policy chỉ cho service identity đọc hoặc sử dụng key store.
8. Audit ghi lại việc sử dụng khóa và cảnh báo khi certificate sắp hết hạn.
9. Khi xoay vòng, service triển khai certificate/key version mới theo rollout có kiểm soát; key cũ được giữ chỉ trong thời gian dữ liệu hoặc kết nối còn phụ thuộc.

Nếu private key được giữ trong HSM, file cấu hình của service có thể chỉ chứa provider reference và alias. Việc sao lưu cấu hình không đồng nghĩa đã backup vật liệu khóa; DR plan phải bao gồm quy trình phục hồi HSM/KMS.

## 22. Checklist thiết kế và vận hành key store

Trước khi đưa key store vào sử dụng, hãy kiểm tra:

- [ ] Đã xác định loại backend: file, OS store, Java provider, HSM hay KMS.
- [ ] Đã phân loại private key, secret key, certificate và trusted certificate.
- [ ] Đã phân biệt key store với trust store theo vai trò ứng dụng.
- [ ] Đã chọn định dạng/provider tương thích và còn được hỗ trợ.
- [ ] Đã xác định alias/key ID/version và owner của từng entry.
- [ ] Đã xác định thuật toán, purpose, exportability và thời hạn.
- [ ] Password/credential được lấy từ nguồn phù hợp và không hardcode.
- [ ] File permission, IAM, MFA và quyền quản trị được giới hạn.
- [ ] Ứng dụng chỉ có quyền thực hiện thao tác cần thiết.
- [ ] Private key quan trọng được bảo vệ bằng HSM/KMS khi phù hợp.
- [ ] Không log hoặc export vật liệu khóa trái phép.
- [ ] Backup/restore có miền lỗi, phê duyệt và kiểm thử.
- [ ] Có kế hoạch rotation, revoke, disable và destruction.
- [ ] Có inventory, audit log, cảnh báo và người chịu trách nhiệm.
- [ ] Đã kiểm tra khả năng DR với provider/backend thực tế.

Key store là điểm kiểm soát quan trọng giữa ứng dụng và vật liệu mật mã. Thiết kế tốt phải xác định rõ khóa nằm ở đâu, ai có thể sử dụng, ứng dụng được phép làm gì, cách khôi phục khi sự cố và cách loại bỏ khóa khi hết vòng đời. Khi key store được quản lý cùng certificate, KMS/HSM, quyền truy cập và audit, tổ chức có thể duy trì danh tính mật mã và bảo vệ dữ liệu xuyên suốt vòng đời khóa.
