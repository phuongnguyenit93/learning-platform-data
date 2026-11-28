# Đọc key từ KeyStore

Trong bài thực hành này, bạn sẽ tạo một kho khóa PKCS12 dùng riêng cho lab, nạp kho bằng Java KeyStore, lấy khóa riêng theo alias và dùng khóa đó để ký một thông điệp. Sau đó, chương trình dùng public key trong certificate đi kèm để xác minh chữ ký. Qua bài tập, bạn sẽ hiểu cách Java liên kết file KeyStore, password, alias, key entry và certificate trong một luồng sử dụng khóa thực tế.

Bài học thuộc module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, tập trung vào vòng đời khóa mật mã từ tạo, cấp phát và lưu trữ đến sử dụng, xoay vòng, thu hồi và khôi phục. Trong ứng dụng production, đọc được key từ KeyStore mới chỉ là một bước: vị trí lưu, quyền filesystem, nguồn cấp password, quyền của principal và audit đều cần được kiểm soát.

## 1. Mục tiêu thực hành

Sau bài này, bạn có thể:

- Giải thích vai trò của KeyStore, alias, PrivateKeyEntry và certificate.
- Tạo một file PKCS12 phục vụ kiểm thử bằng keytool.
- Nạp KeyStore bằng Java API với password được nhập an toàn.
- Lấy PrivateKey theo alias và kiểm tra kiểu entry.
- Đọc certificate/public key liên kết với private key.
- Dùng private key để ký và public key để xác minh dữ liệu.
- Xử lý trường hợp sai password, alias không tồn tại hoặc entry không phải key.
- Giải thích khác biệt giữa file-backed KeyStore và KeyStore được cung cấp bởi HSM/PKCS#11.

## 2. Chuẩn bị môi trường

Bạn cần:

- JDK 17 trở lên.
- Các lệnh java, javac và keytool trong PATH.
- Một terminal tương tác để nhập password mà không hiển thị ký tự.
- Một thư mục riêng cho file thực hành.

Kiểm tra công cụ:

~~~bash
java -version
javac -version
keytool -help
~~~

Tạo một thư mục mới, ví dụ keystore-read-lab, rồi mở terminal tại thư mục đó. Không dùng file KeyStore production hoặc password thật trong bài tập.

## 3. Hiểu cấu trúc KeyStore

java.security.KeyStore là API của Java để truy cập một kho chứa key và certificate. KeyStore có thể được triển khai bởi nhiều provider và nhiều loại storage.

| Khái niệm | Ý nghĩa |
|---|---|
| KeyStore | Đối tượng đại diện cho kho key/certificate |
| Type | Định dạng hoặc cơ chế storage, ví dụ PKCS12, JKS, PKCS11 |
| Provider | Implementation cung cấp dịch vụ KeyStore |
| Alias | Tên dùng để tham chiếu một entry trong kho |
| PrivateKeyEntry | Private key đi kèm certificate chain |
| SecretKeyEntry | Symmetric key entry |
| TrustedCertificateEntry | Certificate tin cậy, không chứa private key |
| Store password | Password dùng khi load/store kho theo semantics của provider |
| Key password | Password dùng để truy xuất key entry nếu provider/format hỗ trợ tách riêng |

Một alias có thể trỏ tới nhiều loại entry. Vì vậy, không được giả định getKey() luôn trả về PrivateKey. Nó có thể trả về SecretKey, hoặc null nếu alias không chứa key entry.

Trong bài lab, ta dùng PKCS12 chứa một PrivateKeyEntry. keytool tạo RSA key pair và certificate tự ký; Java đọc private key bằng alias, rồi dùng public key trong certificate để xác minh chữ ký.

## 4. Tạo PKCS12 KeyStore bằng keytool

Chạy lệnh sau trong terminal:

~~~bash
keytool -genkeypair -alias app-signing -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -dname "CN=KeyStore Lab" -storetype PKCS12 -keystore app-keys.p12
~~~

keytool sẽ yêu cầu nhập và xác nhận password cho keystore. Khi được hỏi password riêng cho alias app-signing, nhấn Enter để dùng cùng password với keystore. Cách này phù hợp với hành vi tương thích PKCS12 phổ biến của JDK.

Lệnh tạo:

- RSA private key và public key.
- Một certificate tự ký chứa public key.
- Entry có alias app-signing.
- File PKCS12 tên app-keys.p12.

Certificate tự ký chỉ phục vụ bài lab. Việc chữ ký xác minh thành công chứng minh private key và public key khớp nhau; nó không chứng minh certificate được một CA tin cậy hoặc phù hợp để xác thực danh tính trong production.

## 5. Kiểm tra nội dung KeyStore bằng keytool

Liệt kê entry:

~~~bash
keytool -list -v -keystore app-keys.p12 -storetype PKCS12
~~~

Nhập password đã tạo. Kiểm tra kết quả có:

- Alias app-signing.
- Entry type PrivateKeyEntry.
- Certificate chain length lớn hơn 0.
- Public key algorithm là RSA.
- Certificate có subject CN=KeyStore Lab.

Không chia sẻ file app-keys.p12 hoặc password. File này chứa private key của bài lab; hãy giữ trong thư mục riêng và xóa khi hoàn tất.

## 6. Viết chương trình Java đọc key từ KeyStore

Tạo file KeyStoreReadLab.java:

~~~java
import java.io.Console;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Arrays;

public final class KeyStoreReadLab {
    private KeyStoreReadLab() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java KeyStoreReadLab <keystore-file> <alias>");
            System.exit(2);
        }

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Run this lab from an interactive terminal");
        }

        char[] password = console.readPassword("Keystore password: ");
        if (password == null) {
            throw new IllegalStateException("No password was provided");
        }

        byte[] message =
                "Read a key from Java KeyStore".getBytes(StandardCharsets.UTF_8);
        byte[] signatureBytes = null;

        try {
            Path keyStorePath = Path.of(args[0]);
            String alias = args[1];

            KeyStore keyStore = KeyStore.getInstance("PKCS12");
            try (InputStream input = Files.newInputStream(keyStorePath)) {
                keyStore.load(input, password);
            }

            if (!keyStore.containsAlias(alias)) {
                throw new IllegalArgumentException(
                        "Alias does not exist: " + alias);
            }

            if (!keyStore.isKeyEntry(alias)) {
                throw new IllegalArgumentException(
                        "Alias does not contain a key entry: " + alias);
            }

            Key key = keyStore.getKey(alias, password);
            if (!(key instanceof PrivateKey privateKey)) {
                throw new IllegalStateException(
                        "Expected a PrivateKey entry, got: "
                                + (key == null ? "null" : key.getClass().getName()));
            }

            Certificate certificate = keyStore.getCertificate(alias);
            if (!(certificate instanceof X509Certificate x509Certificate)) {
                throw new IllegalStateException(
                        "Expected an X.509 certificate for alias: " + alias);
            }

            System.out.println("KeyStore type: " + keyStore.getType());
            System.out.println("Alias: " + alias);
            System.out.println("Entry type: PrivateKeyEntry");
            System.out.println("Private key algorithm: "
                    + privateKey.getAlgorithm());
            System.out.println("Certificate subject: "
                    + x509Certificate.getSubjectX500Principal());
            System.out.println("Certificate valid until: "
                    + x509Certificate.getNotAfter());

            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(privateKey);
            signer.update(message);
            signatureBytes = signer.sign();

            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(x509Certificate.getPublicKey());
            verifier.update(message);

            if (!verifier.verify(signatureBytes)) {
                throw new SecurityException("Signature verification failed");
            }

            System.out.println("Sign and verify: PASS");
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(message, (byte) 0);
            if (signatureBytes != null) {
                Arrays.fill(signatureBytes, (byte) 0);
            }
        }
    }
}
~~~

Chương trình không gọi privateKey.getEncoded() và không in key bytes. Nó dùng private key trực tiếp qua Signature.initSign(), sau đó lấy public key từ certificate để xác minh. Đây cũng là cách làm việc phù hợp với một số private key không export được, miễn provider hỗ trợ thao tác ký bằng key object đó.

Password được nhập bằng Console.readPassword() nên không hiển thị khi gõ. Nếu System.console() trả về null, hãy chạy chương trình từ terminal tương tác thay vì một môi trường IDE không cấp console. Không thay bằng cách hardcode password hoặc truyền password trên command line.

## 7. Biên dịch và chạy chương trình

~~~bash
javac KeyStoreReadLab.java
java KeyStoreReadLab app-keys.p12 app-signing
~~~

Nhập password đã dùng khi tạo PKCS12. Kết quả dự kiến có dạng:

~~~text
Keystore type: PKCS12
Alias: app-signing
Entry type: PrivateKeyEntry
Private key algorithm: RSA
Certificate subject: CN=KeyStore Lab
Certificate valid until: ...
Sign and verify: PASS
~~~

Ngày hết hạn certificate phụ thuộc thời điểm tạo. Các dòng output không chứa private key hoặc password.

## 8. Hiểu luồng đọc key

~~~mermaid
flowchart TD
    A[Nhận đường dẫn và alias] --> B[Đọc password an toàn]
    B --> C[KeyStore.getInstance PKCS12]
    C --> D[load file bằng password]
    D --> E{Alias tồn tại?}
    E -->|Không| X[Từ chối]
    E -->|Có| F{Là key entry?}
    F -->|Không| X
    F -->|Có| G[getKey alias password]
    G --> H{PrivateKey?}
    H -->|Không| X
    H -->|Có| I[getCertificate alias]
    I --> J[Sign bằng private key]
    J --> K[Verify bằng public key]
    K --> L[Kết quả]
~~~

Các bước cần nhớ:

1. KeyStore.getInstance("PKCS12") chọn implementation theo type.
2. load() mở kho và xác minh nội dung bằng password theo cơ chế PKCS12/provider.
3. containsAlias() xác nhận alias tồn tại.
4. isKeyEntry() xác nhận entry là key entry.
5. getKey() lấy key object theo alias và key password.
6. getCertificate() lấy certificate liên kết với private key.
7. Signature sử dụng key object mà không cần xuất key material ra byte array.

Trong ứng dụng thực tế, cần xác minh certificate chain và trust theo PKI policy riêng. Bài lab chỉ kiểm tra quan hệ toán học giữa private key và public key.

## 9. Phân biệt PrivateKeyEntry và SecretKeyEntry

getKey(alias, password) trả về kiểu Key. Cách xử lý tiếp theo phụ thuộc loại entry:

~~~java
Key key = keyStore.getKey(alias, password);

if (key instanceof PrivateKey privateKey) {
    // Dùng privateKey cho Sign, Decrypt hoặc KeyAgreement theo policy.
} else if (key instanceof javax.crypto.SecretKey secretKey) {
    // Dùng secretKey cho Encrypt/Decrypt, MAC hoặc key derivation phù hợp.
} else {
    throw new IllegalStateException("Unsupported key type");
}
~~~

| Entry | Nội dung | Certificate đi kèm | Ví dụ sử dụng |
|---|---|---|---|
| PrivateKeyEntry | Private key và certificate chain | Có | Ký số hoặc giải mã bất đối xứng |
| SecretKeyEntry | Symmetric key | Không bắt buộc/không có theo mô hình entry | AES, HMAC |
| TrustedCertificateEntry | Certificate tin cậy | Chính entry là certificate | Xác minh certificate chain hoặc TLS trust |

Với SecretKeyEntry, không gọi getCertificate() để tìm certificate tương ứng. Khi dùng PKCS12 cho secret key, khả năng và cách bảo vệ entry phụ thuộc JDK/provider; cần kiểm tra tương thích của môi trường mục tiêu.

## 10. Kiểm thử lỗi và trường hợp âm

Thử từng tình huống trong thư mục lab:

| Test | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Alias đúng | Chạy với app-signing | Lấy được PrivateKey và ký-xác minh thành công |
| Alias không tồn tại | Chạy với missing-alias | Báo alias không tồn tại |
| Sai store password | Nhập password khác | Load thất bại |
| Sai key password | Dùng kho có entry password riêng nếu provider hỗ trợ | Không lấy được key entry |
| Certificate-only alias | Tạo/nhập trusted certificate entry rồi thử đọc như key | Bị từ chối vì không phải key entry |
| File không tồn tại | Truyền đường dẫn sai | Báo lỗi I/O |
| File hỏng | Dùng bản sao test bị cắt cụt/sửa đổi | Load thất bại hoặc báo lỗi integrity/format |

Không sửa file gốc khi thử tampering. Không assert chính xác toàn bộ exception message vì chúng có thể khác giữa JDK và provider; hãy kiểm tra loại lỗi hoặc kết quả thất bại theo hợp đồng API.

## 11. KeyStore trên HSM qua PKCS#11

File PKCS12 trong bài lab lưu key entry trong một file được bảo vệ bằng password. Với HSM, Java có thể truy cập key object thông qua provider PKCS#11 và KeyStore type PKCS11, tùy provider và cấu hình.

Một luồng PKCS#11 có thể có dạng:

~~~java
// Pseudocode: cần cấu hình provider PKCS#11 theo tài liệu HSM.
KeyStore tokenKeyStore = KeyStore.getInstance("PKCS11", pkcs11Provider);
tokenKeyStore.load(null, tokenPin);

Key tokenKey = tokenKeyStore.getKey("signing-key", tokenPin);
~~~

Đây là pseudocode, không thể chạy nếu chưa cấu hình provider, native PKCS#11 library, slot/partition và token. Với HSM, load(null, pin) và cách xác thực phụ thuộc implementation. Không giả định PIN luôn giống password PKCS12 hoặc mọi HSM có cùng cách đăng nhập.

Private key có thể không export được. Điều đó không ngăn ứng dụng dùng key object để ký nếu HSM/provider hỗ trợ. Không cần gọi getEncoded() để chứng minh đọc thành công; hãy thực hiện thao tác được phép như ký và kiểm tra audit/device evidence.

## 12. Bảo vệ KeyStore sau khi đọc

Đọc được key không có nghĩa có thể để key tồn tại không kiểm soát trong ứng dụng:

- Không hardcode store password hoặc key password trong source code.
- Không truyền password trên command line hoặc ghi vào shell history.
- Giới hạn quyền filesystem đối với file PKCS12 và thư mục cha.
- Không đưa file KeyStore vào source control, image công khai hoặc artifact không được bảo vệ.
- Không log password, private key, secret key hoặc output của getEncoded().
- Giữ thời gian sử dụng key trong bộ nhớ ở mức cần thiết.
- Tách quyền đọc key khỏi quyền thay policy, export hoặc destroy key.
- Có backup/recovery, rotation và quy trình thu hồi khi nghi ngờ lộ password/key.
- Theo dõi audit event cho việc load, ký và các thao tác key nhạy cảm.

Việc xóa char[] password sau khi sử dụng là best effort. Java không bảo đảm mọi bản sao trong heap hoặc bên trong provider đều được zeroize tức thì. Hãy tránh tạo thêm bản sao không cần thiết và dùng secret-management mechanism phù hợp trong production.

## 13. Bài tập mở rộng

### Bài tập A — Đọc certificate mà không lấy private key

- Dùng getCertificate(alias) để lấy certificate.
- In subject, issuer, serial number và thời hạn.
- Giải thích vì sao certificate/public key có thể công khai nhưng private key phải được bảo vệ.
- Thử getCertificateChain(alias) và quan sát chain length.

### Bài tập B — Phân biệt alias và entry type

- Tạo một alias không tồn tại và quan sát containsAlias().
- Tạo một trusted certificate entry trong kho test.
- So sánh isKeyEntry() và isCertificateEntry().
- Giải thích vì sao không thể gọi mọi alias như một private key.

### Bài tập C — Kiểm tra sai password

- Chạy chương trình với password sai.
- Ghi lại loại exception nhưng không ghi password.
- Giải thích khác biệt giữa lỗi load keystore và lỗi lấy key entry.

### Bài tập D — Kiểm tra chữ ký

- Thay đổi một byte của message trước bước verify.
- Xác minh chữ ký không còn hợp lệ.
- Giải thích vai trò của public key trong kiểm tra chữ ký.

### Bài tập E — Đọc SecretKeyEntry

- Tạo một kho test và entry symmetric key bằng API/provider hỗ trợ.
- Lấy key bằng getKey(alias, password).
- Xác minh object là SecretKey.
- Dùng key trong AES-GCM với nonce mới.
- Không in hoặc lưu key bytes.

## 14. Câu hỏi tự kiểm tra

1. KeyStore.getInstance("PKCS12") chọn loại implementation nào?
2. Alias dùng để làm gì?
3. PrivateKeyEntry khác TrustedCertificateEntry như thế nào?
4. Vì sao phải kiểm tra isKeyEntry() trước khi xử lý key?
5. getKey() có thể trả về những kiểu key nào?
6. Vì sao bài lab dùng certificate để lấy public key xác minh chữ ký?
7. Chữ ký xác minh thành công có chứng minh certificate được CA tin cậy không?
8. Vì sao không nên truyền password qua command line?
9. File PKCS12 khác KeyStore PKCS11 trên HSM ở điểm nào?
10. Vì sao private key không export được vẫn có thể dùng để ký?

## 15. Tiêu chí hoàn thành

- [ ] Tạo được file PKCS12 bằng keytool.
- [ ] Xác nhận alias app-signing là PrivateKeyEntry.
- [ ] Biên dịch và chạy được KeyStoreReadLab.
- [ ] Nhập password qua terminal mà không hiển thị.
- [ ] Đọc được private key và certificate theo alias.
- [ ] Ký và xác minh thông điệp thành công.
- [ ] Thử alias không tồn tại và password sai.
- [ ] Giải thích được PrivateKeyEntry, SecretKeyEntry và TrustedCertificateEntry.
- [ ] Không in, log hoặc commit key material/password.
- [ ] Xóa file KeyStore test sau khi hoàn tất nếu không còn cần dùng.

## 16. Áp dụng vào hệ thống thực tế

Trong production, lựa chọn KeyStore phụ thuộc mô hình bảo vệ khóa:

- PKCS12 phù hợp cho file-backed keystore cần tính tương thích, nhưng file và password phải được bảo vệ riêng.
- JKS là định dạng cũ; chỉ giữ khi cần tương thích với hệ thống hiện hữu.
- PKCS11 có thể kết nối Java với HSM/token, nơi key object được bảo vệ bởi thiết bị.
- KMS phù hợp khi cần quản lý key tập trung, policy theo principal, versioning và audit.

Ứng dụng nên nhận key reference/alias từ cấu hình được kiểm soát, dùng workload identity hoặc cơ chế xác thực phù hợp để truy cập storage, và chỉ thực hiện thao tác được cấp quyền. Khi key bị rotate, cần quản lý version để đọc dữ liệu cũ; khi key bị revoke, phải cập nhật quyền và trạng thái tin cậy; khi destroy, cần xác minh backup/archive không còn phụ thuộc.

Hoàn thành bài tập khi bạn có thể nạp một KeyStore, lấy đúng loại key theo alias và thực hiện một thao tác mật mã mà không làm lộ key material. Đây là nền tảng để tiếp tục thực hành KMS/HSM, quản lý quyền truy cập và rotation trong các bài tiếp theo.
