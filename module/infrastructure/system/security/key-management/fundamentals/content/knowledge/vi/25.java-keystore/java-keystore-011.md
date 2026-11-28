# Key password

Trong Java KeyStore, **key password** là mật khẩu hoặc thông tin bảo vệ được dùng khi truy cập một key entry cụ thể, chẳng hạn private key hoặc secret key. Mục tiêu của nó là kiểm soát việc mở khóa vật liệu bí mật đã được lưu trong keystore. Khái niệm này thường được nhắc cùng **store password**, mật khẩu dùng khi nạp hoặc lưu toàn bộ keystore, nhưng hai loại mật khẩu có vai trò khác nhau và không phải provider nào cũng hỗ trợ tách biệt chúng.

Với một keystore dạng file, store password có thể bảo vệ tính toàn vẹn của container và, tùy định dạng, tham gia mã hóa các key entry. Key password có thể bảo vệ riêng từng private key hoặc secret key entry. Certificate công khai thường không cần key password để đọc. Với HSM hoặc token PKCS#11, thông tin xác thực có thể là PIN hoặc phiên đăng nhập; không nên đồng nhất PIN của token với key password của file keystore.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Java KeyStore**. Nội dung kết nối password protection với vòng đời khóa mật mã: tạo, cấp phát, lưu trữ, sử dụng, backup, xoay vòng, thu hồi và hủy; đồng thời xét private key, secret key, certificate/PKI, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Vì sao cần key password?

Một keystore có thể chứa nhiều loại entry. Nếu chỉ cần đọc certificate công khai, ứng dụng không nên phải mở private key. Ngược lại, khi ký dữ liệu hoặc xác thực TLS bằng private key, hệ thống phải kiểm soát ai được phép sử dụng vật liệu bí mật đó.

Key password có thể tạo thêm một lớp bảo vệ cho entry:

- Giới hạn việc lấy private key hoặc secret key theo mật khẩu của entry.
- Cho phép các entry trong cùng một keystore có thông tin bảo vệ khác nhau, nếu định dạng/provider hỗ trợ.
- Giảm hậu quả khi một người chỉ biết store password nhưng không biết mật khẩu của key entry.
- Hỗ trợ quy trình bàn giao hoặc vận hành, trong đó quyền mở container và quyền sử dụng khóa được quản lý riêng.

Mật khẩu không thay thế kiểm soát truy cập của hệ điều hành, IAM, provider hoặc HSM. Nếu tiến trình đã được phép sử dụng private key và đang chạy với quyền hợp lệ, kẻ tấn công chiếm được tiến trình có thể gọi thao tác ký hoặc giải mã mà không cần biết password gốc. Vì vậy, phải kiểm soát cả quyền mở entry lẫn quyền sử dụng khóa.

## 2. Phân biệt store password, key password và token PIN

Các thuật ngữ thường gặp:

| Thông tin xác thực | Phạm vi | Ví dụ sử dụng |
|---|---|---|
| Store password | Toàn bộ keystore dạng file hoặc container | Nạp keystore bằng KeyStore.load và ghi bằng KeyStore.store. |
| Key password / entry password | Một key entry cụ thể | Lấy private key bằng getKey hoặc getEntry. |
| Token PIN / login credential | Phiên truy cập token hoặc HSM | Đăng nhập token qua provider PKCS#11. |
| Secret manager credential | Danh tính được phép lấy secret | Ứng dụng xác thực với secret manager để lấy store password hoặc entry password. |
| Recovery credential | Quy trình phục hồi được kiểm soát | Mở backup hoặc phục hồi miền bảo mật theo chính sách DR. |

Trong Java API, store password thường được truyền vào load/store. Key password được truyền vào getKey hoặc ProtectionParameter khi lấy entry. PIN token thường được truyền cho provider khi mở phiên làm việc; semantics phụ thuộc thiết bị và provider.

Không nên dùng cùng một chuỗi bí mật cho tất cả các mục đích chỉ vì ứng dụng có ít cấu hình hơn. Nếu một secret bị lộ, việc dùng chung làm tăng phạm vi ảnh hưởng và khiến tổ chức khó thu hồi riêng từng quyền.

## 3. Key password bảo vệ loại entry nào?

Java KeyStore định nghĩa các loại entry phổ biến:

| Entry | Có vật liệu bí mật? | Cần key password? |
|---|---|---|
| PrivateKeyEntry | Có private key và certificate chain | Thường cần cơ chế bảo vệ entry khi lấy private key. |
| SecretKeyEntry | Có secret key đối xứng hoặc HMAC | Thường cần cơ chế bảo vệ entry theo provider. |
| TrustedCertificateEntry | Chỉ có certificate công khai | Không cần key password để đọc certificate. |

Certificate và public key không phải bí mật. Tuy vậy, việc thêm certificate vào trust store là một quyết định tin cậy và cần xác minh nguồn gốc, fingerprint, issuer, mục đích và chính sách CA.

Với PrivateKeyEntry, key password bảo vệ khả năng lấy private key. Certificate chain đi kèm entry thường có thể đọc mà không cần giải mã private key. Với SecretKeyEntry, hành vi phụ thuộc provider và loại store; không phải mọi định dạng đều hỗ trợ lưu mọi loại secret key.

## 4. Luồng sử dụng hai mật khẩu trong Java

Trong một file keystore hỗ trợ tách mật khẩu, luồng thường diễn ra như sau:

1. Ứng dụng lấy store password từ nguồn bí mật được quản lý.
2. Ứng dụng gọi KeyStore.load để xác minh và nạp container.
3. Ứng dụng tra cứu alias cần dùng.
4. Khi cần private key hoặc secret key, ứng dụng lấy key password tương ứng.
5. Ứng dụng gọi getKey hoặc getEntry với thông tin bảo vệ entry.
6. Provider xác minh password và trả về key object nếu hợp lệ.
7. Ứng dụng thực hiện thao tác mật mã; không ghi key bytes hoặc password vào log.
8. Ứng dụng xóa các mảng password do mình quản lý và giải phóng tài nguyên.

~~~mermaid
flowchart TD
    A["Secret manager / nguồn credential"] --> B["Store password"]
    A --> C["Key password"]
    B --> D["KeyStore.load"]
    D --> E["Keystore đã nạp"]
    E --> F["Tra cứu alias"]
    C --> G["getKey / getEntry"]
    F --> G
    G --> H["PrivateKey hoặc SecretKey object"]
    H --> I["Sign / decrypt / MAC"]
~~~

Luồng này mô tả file keystore có entry password riêng. Với PKCS#12 provider yêu cầu một mật khẩu chung, store password và key password có thể phải giống nhau. Với HSM, ứng dụng có thể đăng nhập token một lần rồi thao tác qua key handle mà không truyền key password cho từng entry.

## 5. JKS và key password

JKS là định dạng keystore lịch sử của Java. Trong mô hình JKS truyền thống:

- Store password được dùng để kiểm tra tính toàn vẹn của keystore.
- Private key entry được bảo vệ riêng bằng key password.
- Một keystore có thể chứa các private key entry với mật khẩu khác nhau.
- Trusted certificate entry không chứa private key nên không cần key password để đọc.

Điểm quan trọng: store password của JKS không nên được mô tả như một khóa mã hóa toàn bộ nội dung file. Cơ chế JKS truyền thống dùng mật khẩu store cho kiểm tra integrity, còn private key entry được bảo vệ bằng cơ chế PBE riêng. Certificate công khai có thể đọc được từ file mà không cần mở private key.

JKS là định dạng legacy. Các hệ thống hiện đại thường ưu tiên PKCS#12 khi provider và ứng dụng hỗ trợ. Nếu tiếp tục dùng JKS, cần đánh giá chính sách mật mã của runtime, thuật toán bảo vệ entry và kế hoạch chuyển đổi.

## 6. PKCS#12 và khác biệt về mật khẩu

PKCS#12 là container tiêu chuẩn có thể chứa private key, certificate và chain. Container thường dùng password-based encryption để bảo vệ key material và MAC để kiểm tra tính toàn vẹn.

Tuy nhiên, khả năng dùng mật khẩu riêng cho từng private key entry phụ thuộc định dạng và provider. Với SunPKCS12 provider thường dùng trong OpenJDK/Oracle JDK, store password và key password được yêu cầu giống nhau; key password riêng không được hỗ trợ theo cách JKS hỗ trợ. Một số provider hoặc sản phẩm có thể có hành vi khác, nên phải kiểm tra tài liệu triển khai cụ thể.

| Đặc điểm | JKS truyền thống | PKCS#12 |
|---|---|---|
| Store password | Kiểm tra integrity của keystore | Thường tham gia bảo vệ nội dung và MAC |
| Key password riêng | Hỗ trợ cho private key entry | Phụ thuộc provider; SunPKCS12 thường yêu cầu trùng store password |
| Khả năng tương thích | Tập trung vào Java | Được hỗ trợ rộng trên nhiều nền tảng |
| Khuyến nghị | Duy trì có kiểm soát cho hệ thống cũ | Thường phù hợp hơn cho hệ thống mới |

Không suy ra semantics chỉ từ phần mở rộng .p12 hoặc .jks. Cần xác định store type, provider, phiên bản JDK và cách file được tạo.

## 7. Mật khẩu entry trong Java KeyStore API

API KeyStore cung cấp một số phương thức quan trọng:

| API | Mục đích | Password liên quan |
|---|---|---|
| load(InputStream, char[]) | Nạp keystore | Store password |
| store(OutputStream, char[]) | Ghi keystore | Store password |
| getKey(alias, char[]) | Lấy key object | Key password theo provider |
| getEntry(alias, ProtectionParameter) | Lấy entry theo cơ chế bảo vệ | Entry password hoặc cơ chế provider |
| setKeyEntry(alias, Key, char[], Certificate[]) | Thêm key entry | Key password theo provider |
| setEntry(alias, Entry, ProtectionParameter) | Thêm entry với protection parameter | Entry protection |

Password được truyền dưới dạng char[] để ứng dụng có thể xóa mảng sau khi sử dụng. Điều này giảm thời gian giữ bí mật trong mảng do ứng dụng sở hữu, nhưng không bảo đảm JVM hoặc provider không tạo bản sao nội bộ.

## 8. Lấy private key bằng getKey

Ví dụ sau minh họa việc nạp keystore rồi lấy private key theo alias. Thành phần passwordProvider là một abstraction do ứng dụng xây dựng để lấy secret từ nguồn được quản lý; đây không phải lớp có sẵn trong JDK.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.util.Arrays;

Path storePath = Path.of("config", "signing-identity.jks");
char[] storePassword = passwordProvider.getStorePassword();

KeyStore keyStore = KeyStore.getInstance("JKS");
try {
    try (InputStream input = Files.newInputStream(storePath)) {
        keyStore.load(input, storePassword);
    }

    String alias = "document-signing";
    if (!keyStore.containsAlias(alias) || !keyStore.isKeyEntry(alias)) {
        throw new IllegalStateException("Private key entry is unavailable");
    }

    char[] keyPassword = passwordProvider.getKeyPassword(alias);
    try {
        Key key = keyStore.getKey(alias, keyPassword);
        if (!(key instanceof PrivateKey privateKey)) {
            throw new IllegalStateException("Entry is not a private key");
        }

        System.out.println("Algorithm: " + privateKey.getAlgorithm());
        // Dùng privateKey qua Signature; không export hoặc log key bytes.
    } finally {
        Arrays.fill(keyPassword, '\0');
    }
} finally {
    Arrays.fill(storePassword, '\0');
}
~~~

Nếu alias không tồn tại, getKey có thể trả về null; nếu mật khẩu sai hoặc key không thể khôi phục, provider có thể ném UnrecoverableKeyException. Ứng dụng cần xử lý lỗi rõ ràng và không được chuyển sang một key alias khác một cách âm thầm.

Không gọi getEncoded() chỉ để debug. Với private key non-exportable trong HSM, getEncoded() thường trả về null; ứng dụng nên dùng key object do provider cung cấp để gọi Signature hoặc Cipher theo khả năng thiết bị.

## 9. Dùng PasswordProtection với getEntry

API Entry cho phép truyền cơ chế bảo vệ rõ ràng:

~~~java
import java.security.KeyStore;
import java.util.Arrays;

char[] entryPassword = passwordProvider.getKeyPassword("document-signing");
KeyStore.PasswordProtection protection =
        new KeyStore.PasswordProtection(entryPassword);

try {
    KeyStore.Entry entry = keyStore.getEntry("document-signing", protection);
    if (!(entry instanceof KeyStore.PrivateKeyEntry privateEntry)) {
        throw new IllegalStateException("Expected PrivateKeyEntry");
    }

    // Dùng privateEntry.getPrivateKey() cho thao tác ký.
} finally {
    try {
        protection.destroy();
    } finally {
        Arrays.fill(entryPassword, '\0');
    }
}
~~~

PasswordProtection triển khai ProtectionParameter và giữ thông tin password cho thao tác entry. Phương thức destroy có thể ném DestroyFailedException; vì vậy, ví dụ đặt việc xóa mảng do ứng dụng sở hữu trong finally lồng nhau để vẫn được thực hiện khi destroy thất bại.

Với provider hỗ trợ cơ chế khác, ProtectionParameter có thể không phải PasswordProtection. HSM có thể dựa trên phiên đăng nhập, token PIN hoặc policy thiết bị. Không ép mọi backend phải dùng mật khẩu của file keystore.

## 10. PasswordProtection và giới hạn bộ nhớ

PasswordProtection có thể giữ một bản sao password bên trong object. Gọi destroy giúp provider/API xóa bản sao do object quản lý theo khả năng triển khai. Ứng dụng vẫn nên xóa mảng char[] gốc của mình.

Một số giới hạn cần hiểu:

- Java String là immutable; không thể chủ động ghi đè nội dung String.
- Mảng char[] có thể được ghi đè, nhưng bản sao do JVM/provider tạo ra có thể vẫn tồn tại.
- Garbage collection không phải cơ chế zeroization có thời điểm xác định.
- Heap dump, crash dump hoặc debugger có thể làm lộ password trong bộ nhớ.
- Việc xóa password khỏi mảng không xóa private key đã được nạp hoặc bản sao do provider quản lý.

Do đó, nên lấy password sát thời điểm sử dụng, giới hạn phạm vi biến, không giữ trong singleton hoặc cache lâu dài, tránh log/debug dump và dùng HSM/KMS khi phù hợp để giảm việc đưa key material vào heap ứng dụng.

## 11. Tạo và lưu key entry với mật khẩu

Với keystore dạng file và private key có thể export, setKeyEntry nhận private key, key password và certificate chain:

~~~java
keyStore.setKeyEntry(
        "service-signing",
        privateKey,
        keyPassword,
        certificateChain);
~~~

Với secret key entry, provider có thể hỗ trợ setEntry với SecretKeyEntry và PasswordProtection:

~~~java
KeyStore.SecretKeyEntry secretEntry =
        new KeyStore.SecretKeyEntry(secretKey);
KeyStore.PasswordProtection protection =
        new KeyStore.PasswordProtection(entryPassword);

try {
    keyStore.setEntry("data-encryption", secretEntry, protection);
} finally {
    try {
        protection.destroy();
    } finally {
        java.util.Arrays.fill(entryPassword, '\0');
    }
}
~~~

Khả năng lưu secret key và cơ chế mã hóa entry phụ thuộc store type/provider. Không dùng ví dụ file-based để suy luận rằng HSM cho phép export hoặc import key theo cùng cách.

## 12. Đổi store password

Đổi store password là thay thông tin bảo vệ của container. Với file-based keystore, quy trình tổng quát:

1. Xác minh quyền thực hiện và backup hiện trạng theo chính sách.
2. Nạp keystore bằng store password hiện tại.
3. Ghi keystore ra file tạm bằng store password mới.
4. Nạp lại file tạm bằng password mới để xác minh.
5. Kiểm tra alias, certificate và thao tác lấy key entry cần thiết.
6. Thay thế file cũ bằng file mới theo cơ chế an toàn và có thể rollback.
7. Cập nhật secret manager/configuration để ứng dụng dùng password mới.
8. Thu hồi password cũ và ghi audit.

Ví dụ:

~~~java
KeyStore keyStore = KeyStore.getInstance("JKS");
try (InputStream input = Files.newInputStream(sourcePath)) {
    keyStore.load(input, oldStorePassword);
}

try (OutputStream output = Files.newOutputStream(tempPath)) {
    keyStore.store(output, newStorePassword);
}
~~~

Đoạn mã chỉ minh họa phần nạp và ghi. Trong triển khai thật, tempPath phải có quyền filesystem chặt, nằm trên filesystem phù hợp để atomic move, và file sau ghi phải được nạp lại để xác minh trước khi thay thế. Đổi store password không nhất thiết đổi key password của từng entry, đặc biệt trong JKS.

## 13. Đổi key password của một entry

Với JKS và key entry có thể export, quy trình thường là:

1. Nạp keystore bằng store password.
2. Lấy key bằng key password cũ.
3. Lấy certificate chain hiện tại.
4. Ghi lại entry bằng key password mới.
5. Lưu keystore bằng store password.
6. Nạp lại và thử lấy key bằng password mới.
7. Cập nhật nguồn secret và thu hồi password cũ.

Ví dụ minh họa cho private key trong file-based JKS:

~~~java
Key key = keyStore.getKey(alias, oldKeyPassword);
if (!(key instanceof java.security.PrivateKey privateKey)) {
    throw new IllegalStateException("Expected a private key");
}

java.security.cert.Certificate[] chain =
        keyStore.getCertificateChain(alias);
if (chain == null || chain.length == 0) {
    throw new IllegalStateException("Certificate chain is missing");
}

keyStore.setKeyEntry(alias, privateKey, newKeyPassword, chain);

try (OutputStream output = Files.newOutputStream(tempPath)) {
    keyStore.store(output, storePassword);
}
~~~

Đây là thao tác đọc key rồi ghi lại entry với protection mới. Nó không phù hợp cho non-exportable HSM key hoặc provider không cho phép xuất/đặt lại key object. Với PKCS#12, phải kiểm tra provider; SunPKCS12 thường dùng cùng password cho store và key entry nên không thể giả định đổi key password độc lập.

Đổi key password không phải xoay vòng khóa mật mã. Vật liệu private key/secret key vẫn là cùng một khóa; chỉ cơ chế bảo vệ entry thay đổi. Nếu nghi ngờ key material đã bị lộ, đổi password không khắc phục được compromise. Phải thay khóa và xử lý bản sao cũ theo incident response.

## 14. Dùng keytool để quản lý password

keytool là công cụ dòng lệnh của JDK để quản lý keystore, certificate và key pair. Các lệnh sau minh họa cho file-based keystore. Nên để keytool hỏi password tương tác thay vì đặt secret trực tiếp trong command line.

Tạo key pair trong JKS:

~~~bash
keytool -genkeypair -alias app-signing -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=App Signing" -validity 365 -keystore app-signing.jks -storetype JKS
~~~

Liệt kê entry:

~~~bash
keytool -list -v -keystore app-signing.jks -storetype JKS
~~~

Đổi store password:

~~~bash
keytool -storepasswd -keystore app-signing.jks -storetype JKS
~~~

Đổi key password cho alias:

~~~bash
keytool -keypasswd -alias app-signing -keystore app-signing.jks -storetype JKS
~~~

Đổi alias:

~~~bash
keytool -changealias -alias app-signing -destalias app-signing-v2 -keystore app-signing.jks -storetype JKS
~~~

Với PKCS#12, khả năng đổi riêng key password phụ thuộc provider và thường không được SunPKCS12 hỗ trợ như JKS. Các option như -storepass, -keypass hoặc -new có thể nhận secret trực tiếp; tránh dùng dạng đó trong môi trường có process listing, shell history hoặc log. Xem trợ giúp của đúng phiên bản JDK và thử trên bản sao trước khi thay đổi keystore production.

## 15. Chọn mật khẩu đủ mạnh

Key password cần chống đoán và tấn công offline nếu kẻ tấn công có thể lấy file keystore. Chọn mật khẩu theo chính sách của tổ chức và mức độ quan trọng của khóa:

- Dùng mật khẩu dài, ngẫu nhiên và duy nhất cho từng phạm vi cần tách biệt.
- Tránh từ điển, tên dự án, tên người dùng, ngày tháng hoặc mẫu dễ đoán.
- Không tái sử dụng mật khẩu đăng nhập cá nhân hoặc mật khẩu CI/CD.
- Không lưu password trong cùng file, thư mục hoặc backup với keystore.
- Dùng password manager hoặc secret manager có kiểm soát truy cập và audit.
- Có quy trình thay thế khi credential bị lộ, nhân sự thay đổi hoặc quyền bị thu hồi.

Độ mạnh của password-based encryption còn phụ thuộc thuật toán dẫn xuất khóa, salt, số vòng lặp và cấu hình provider. Mật khẩu dài không thể bù cho thuật toán yếu hoặc tham số PBE lỗi thời. Ngược lại, thuật toán tốt không thể bảo vệ file nếu password là chuỗi dễ đoán.

## 16. Password-based encryption và tham số bảo vệ

Với file keystore, password có thể được dùng làm đầu vào để dẫn xuất khóa mã hóa hoặc kiểm tra tính toàn vẹn. Cơ chế cụ thể phụ thuộc định dạng:

- JKS truyền thống có cơ chế integrity dựa trên password và cơ chế PBE riêng cho private key entry.
- PKCS#12 có thể dùng password-based encryption cho key bag và MAC để kiểm tra integrity.
- Provider có thể chọn thuật toán, salt, iteration count và encoding theo phiên bản hoặc cấu hình.

Salt giúp mỗi lần bảo vệ có tham số riêng, làm giảm hiệu quả của bảng tra cứu tiền tính. Iteration count làm tăng chi phí thử mỗi password. Tuy nhiên, nếu file dùng thuật toán legacy hoặc iteration count thấp, cần lập kế hoạch chuyển đổi sang định dạng/provider có cơ chế hiện đại hơn.

Không tự viết thuật toán dẫn xuất password để mã hóa lại keystore. Hãy dùng định dạng và provider được hỗ trợ, cập nhật JDK, kiểm tra cấu hình mật mã và theo dõi cảnh báo về thuật toán yếu.

## 17. Mật khẩu không phải là phân quyền

Key password thường là bí mật tĩnh. Nó không cho biết chắc chắn ai đang sử dụng khóa và không cung cấp đầy đủ ngữ cảnh workload. Trong môi trường nhiều ứng dụng, nhiều tenant hoặc nhiều người vận hành, cần thêm:

- IAM hoặc service identity để xác thực workload.
- Least privilege để giới hạn alias, key ID và operation.
- Phân tách quyền sử dụng khóa với quyền export, xóa hoặc thay policy.
- MFA, dual control hoặc quorum cho thao tác quản trị nhạy cảm.
- Audit ghi nhận principal, key ID, operation, thời điểm và kết quả.
- Secret manager policy để chỉ workload được phê duyệt mới lấy password.

Nếu mọi ứng dụng dùng chung một key password, việc thu hồi một ứng dụng có thể buộc phải đổi mật khẩu cho toàn bộ ứng dụng. Tách key, entry và identity theo mục đích giúp giảm blast radius.

## 18. Quản lý password trong ứng dụng và CI/CD

Không commit password vào source code, Dockerfile, manifest Kubernetes, file properties hoặc pipeline YAML. Các cấu hình mã hóa bằng Base64 không phải biện pháp bảo mật; Base64 chỉ là encoding.

Một quy trình tốt:

1. Workload xác thực với secret manager bằng identity riêng.
2. Secret manager kiểm tra policy, môi trường, tenant và quyền truy cập.
3. Workload nhận password qua kênh bảo vệ, trong thời gian ngắn.
4. Ứng dụng mở keystore và lấy đúng entry.
5. Password được xóa khỏi mảng do ứng dụng quản lý sau khi dùng.
6. Secret manager ghi audit truy cập; ứng dụng không ghi password ra log.

Trong CI/CD, tránh truyền password bằng tham số lệnh hoặc biến môi trường nếu nền tảng có thể hiển thị chúng trong process dump, diagnostic hoặc log. Dùng cơ chế secret masking và ephemeral credential được nền tảng hỗ trợ; giới hạn job, runner và người có quyền xem log.

## 19. HSM, PKCS#11 và PIN

Với HSM hoặc smart card, quyền sử dụng khóa thường được kiểm soát bằng phiên đăng nhập token. PIN của token xác thực người dùng hoặc vai trò trong thiết bị; nó không nhất thiết là password mã hóa một key entry như trong JKS.

Một số lưu ý:

- PIN có thể mở phiên để truy cập nhiều key object theo policy.
- Provider có thể cache phiên đăng nhập hoặc giữ session cho đến khi đóng.
- HSM có thể hỗ trợ role riêng cho user, security officer hoặc backup operator.
- Sai PIN nhiều lần có thể khóa token hoặc kích hoạt cơ chế bảo vệ thiết bị.
- Một số HSM yêu cầu dual control/quorum cho backup, restore hoặc thay đổi policy.
- Non-exportable key có thể được dùng qua handle mà không cần trả key bytes cho JVM.

Không ghi PIN trong cấu hình tĩnh hoặc log. Dùng cơ chế xác thực được nhà cung cấp hỗ trợ, giới hạn quyền truy cập thiết bị và theo dõi login failure. Nếu provider cho phép callback hoặc login manager, ưu tiên cơ chế đó theo tài liệu chính thức.

## 20. Lỗi khi load hoặc lấy key do password sai

Các lỗi có thể xuất hiện ở những giai đoạn khác nhau:

| Giai đoạn | Triệu chứng có thể gặp | Hướng kiểm tra |
|---|---|---|
| KeyStore.load | IOException, lỗi integrity hoặc lỗi định dạng | Store type, file, store password, provider và tính toàn vẹn file. |
| getKey | UnrecoverableKeyException | Alias, key password, entry type và provider semantics. |
| getEntry | UnrecoverableEntryException hoặc lỗi bảo vệ | ProtectionParameter, password, token login và quyền entry. |
| KeyStore.store | IOException hoặc lỗi provider | Store password, output path, quyền filesystem và backend support. |
| HSM login | Login failed, token locked hoặc session error | PIN, role, slot, trạng thái token và policy thiết bị. |

Không xử lý mọi lỗi như password sai. File hỏng, provider không tương thích, token không sẵn sàng hoặc alias không tồn tại có thể tạo lỗi tương tự. Log mã lỗi, operation, alias/key ID đã phân loại và request ID; không log password hoặc key material.

Không thử password liên tục bằng vòng lặp tự động. Điều đó có thể gây khóa token, tăng tải hoặc tạo điều kiện cho denial of service. Dùng retry có giới hạn và tuân theo lockout policy.

## 21. Thay đổi password và tính nguyên tử

Khi đổi store password hoặc key password, tránh sửa file production trực tiếp trong lúc ứng dụng đang đọc. Một quy trình cập nhật an toàn nên:

1. Xác minh quyền và phê duyệt.
2. Tạo bản sao backup được bảo vệ theo chính sách.
3. Nạp file hiện tại bằng credential cũ.
4. Ghi bản mới vào file tạm có quyền truy cập tối thiểu.
5. Nạp lại file tạm bằng credential mới.
6. Kiểm tra alias, certificate chain và thao tác ký/giải mã bằng dữ liệu thử.
7. Đồng bộ secret manager và cấu hình workload theo một cutover có kiểm soát.
8. Thay thế file bằng atomic move nếu filesystem hỗ trợ.
9. Giám sát instance cũ, rollback window và các bản sao chưa cập nhật.
10. Thu hồi credential cũ sau khi xác nhận không còn consumer hợp lệ.

Nếu nhiều instance cùng dùng một keystore, phải có chiến lược rollout để tránh instance này dùng password mới trong khi instance khác vẫn dùng password cũ. Credential rotation và file deployment cần có phiên bản hoặc trạng thái rõ ràng.

## 22. Backup và khôi phục password

Backup keystore mà không backup hoặc không có cách phục hồi password sẽ làm mất khả năng sử dụng key entry. Ngược lại, lưu password cạnh backup làm giảm hiệu quả bảo vệ.

Nên:

- Quản lý password trong secret manager hoặc recovery vault có kiểm soát độc lập.
- Tách quyền đọc keystore backup khỏi quyền đọc password.
- Có owner, retention, phiên bản và quy trình luân chuyển credential.
- Kiểm thử restore keystore cùng quy trình lấy password trong môi trường cô lập.
- Ghi audit ai đã truy cập password và ai đã phục hồi entry.
- Không đưa password vào manifest, ticket hoặc log backup.

Với HSM/KMS, khôi phục thường dựa trên quy trình backup/restore của backend, không phải phục hồi một PIN duy nhất. Cần hiểu rõ token identity, security domain, quorum và key backup package.

## 23. Key password, rotation và incident response

Đổi key password chỉ thay cơ chế mở entry. Nó không tạo khóa mới và không thay đổi certificate/public key. Phải phân biệt:

| Hành động | Thay đổi gì? | Khi nào dùng? |
|---|---|---|
| Change store password | Credential bảo vệ container | Password store bị lộ hoặc cần luân chuyển định kỳ. |
| Change key password | Credential bảo vệ một entry | Cần tách hoặc thay password của entry theo khả năng provider. |
| Rotate key | Tạo key material mới | Theo cryptoperiod, chính sách hoặc giảm rủi ro khóa cũ. |
| Reissue certificate | Phát hành certificate mới | Certificate hết hạn, thay đổi danh tính hoặc key pair mới. |
| Revoke certificate | Thay đổi trạng thái tin cậy | Private key bị compromise hoặc certificate không còn hợp lệ. |
| Destroy key | Hủy vật liệu khóa và đường khôi phục | Khi hết nhu cầu hợp lệ hoặc theo incident/destruction policy. |

Nếu password bị lộ nhưng key material chưa có bằng chứng bị lộ, có thể đổi password và điều tra phạm vi truy cập. Nếu private key/secret key đã bị trích xuất hoặc bị sử dụng trái phép, đổi password là không đủ: phải cô lập khóa, đánh giá dữ liệu/chữ ký bị ảnh hưởng, rotate/revoke và xử lý mọi bản sao theo quy trình.

## 24. Ví dụ vận hành: tách password cho hai private key entry

Một hệ thống Java dùng JKS chứa hai private key: một key phục vụ TLS và một key ký tài liệu. Tổ chức muốn nhóm vận hành TLS không có password của key ký tài liệu.

Thiết kế có thể:

1. Dùng alias riêng cho TLS và document signing.
2. Dùng store password do workload được phép nạp keystore lấy từ secret manager.
3. Lưu key password của TLS và key ký trong hai secret riêng với policy khác nhau.
4. Workload TLS chỉ được lấy secret TLS; service ký tài liệu chỉ được lấy secret ký.
5. Chỉ một nhóm quản trị được phê duyệt mới được thay đổi entry hoặc export key.
6. Ghi audit việc lấy secret và sử dụng key theo key ID/alias.
7. Kiểm thử rằng workload TLS không lấy được key password ký tài liệu.

Mô hình này chỉ hoạt động nếu keystore type/provider hỗ trợ mật khẩu riêng cho từng entry. Với SunPKCS12, cần thiết kế theo yêu cầu mật khẩu chung của provider hoặc tách key store/backend; không được giả định có thể dùng hai key password độc lập như JKS.

## 25. Những lỗi thường gặp

- Nhầm store password với key password.
- Giả định PKCS#12 luôn hỗ trợ mật khẩu riêng cho từng private key.
- Dùng password yếu vì file chỉ được đặt trong mạng nội bộ.
- Đặt password trong source code, command line, shell history hoặc log.
- Lưu password cạnh file keystore và cùng quyền truy cập.
- Dùng String lâu dài cho password thay vì hạn chế vòng đời secret.
- Nghĩ rằng xóa mảng char[] đồng nghĩa mọi bản sao bộ nhớ đã bị zeroize.
- Cho rằng đổi key password là rotate key.
- Cho rằng revoke certificate sẽ xóa private key.
- Dùng password chung cho mọi entry, môi trường và tenant.
- Thử password liên tục khiến token/HSM bị khóa.
- Coi mọi lỗi load/getKey là lỗi password.
- Đổi password nhưng quên cập nhật tất cả workload và backup/DR.
- Không kiểm thử nạp lại keystore sau khi thay password.

## 26. Checklist quản lý key password

Trước khi đưa quy trình password vào production, hãy xác nhận:

- [ ] Đã phân biệt store password, key password, token PIN và recovery credential.
- [ ] Đã xác định keystore type/provider và semantics password thực tế.
- [ ] Đã xác nhận JKS hoặc PKCS#12 hỗ trợ cách tách mật khẩu theo nhu cầu.
- [ ] Password đủ mạnh, duy nhất và được tạo bằng nguồn an toàn.
- [ ] Password được lưu trong secret manager/recovery vault có policy và audit.
- [ ] Quyền lấy store password và key password được tách theo workload.
- [ ] Không hardcode hoặc truyền secret qua command line/log.
- [ ] Password char[] được xóa trong finally; hiểu giới hạn của zeroization.
- [ ] PasswordProtection được destroy khi dùng và xử lý checked exception.
- [ ] HSM PIN được quản lý theo role/session/lockout policy của thiết bị.
- [ ] Có quy trình đổi store password và key password riêng.
- [ ] Có quy trình rotate key riêng với đổi password.
- [ ] Có backup/restore test bao gồm việc phục hồi credential.
- [ ] Có kiểm tra sau đổi password: load, getEntry và thao tác mật mã.
- [ ] Có audit, alert và xử lý khi credential bị lộ.
- [ ] Có kế hoạch cập nhật đồng bộ tất cả instance, môi trường và DR.

Key password là một phần của cơ chế bảo vệ entry trong Java KeyStore. Để dùng đúng, cần hiểu provider đang áp dụng semantics nào, tách credential theo phạm vi cần bảo vệ, quản lý secret ngoài source code và kiểm thử quy trình đổi/khôi phục. Khi password bị lộ, phải đánh giá xem chỉ credential hay cả key material đã bị ảnh hưởng; hai trường hợp đòi hỏi hành động vòng đời khóa khác nhau.
