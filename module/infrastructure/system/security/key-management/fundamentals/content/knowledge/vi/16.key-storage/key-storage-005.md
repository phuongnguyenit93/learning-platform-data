# Keystore — Lưu trữ và quản lý khóa mật mã an toàn

## 1. Keystore là gì?

**Keystore** là cơ chế hoặc vùng lưu trữ có cấu trúc dùng để quản lý **khóa mật mã, chứng chỉ và những đối tượng liên quan**. Tùy công nghệ, keystore có thể là **một tệp được bảo vệ bằng mật khẩu**, **một kho khóa thông qua Java Security Provider**, hoặc một lớp API cung cấp quyền truy cập đến khóa nằm trong **HSM**. Vì vậy, câu “khóa nằm trong keystore” mới chỉ nói được một phần: phải hỏi **keystore loại nào, vật liệu khóa được bảo vệ ở đâu, ai có quyền đọc/sử dụng và việc sao lưu diễn ra thế nào**.

Trong Java, **`java.security.KeyStore`** là một API thống nhất để tải, liệt kê và truy xuất những entry như private key, symmetric secret key và chứng chỉ. Nhưng **KeyStore là abstraction, không tự bảo đảm mọi private key đều non-exportable**, không tự thay thế IAM của ứng dụng và cũng không tự cung cấp hệ thống xoay vòng, thu hồi, hủy khóa hay kiểm toán đầy đủ.

Ví dụ, một dịch vụ Java có thể dùng:

- **PKCS#12 keystore** chứa private key TLS cùng chuỗi chứng chỉ của server.
- **Truststore** chứa các chứng chỉ CA hoặc trust anchors mà client được cấu hình tin cậy.
- **KMS/HSM** để bảo vệ một KEK hoặc private signing key không xuất ra khỏi thiết bị.
- **Secret manager** để phân phối thông tin cấu hình hoặc mật khẩu mở file keystore, theo quyền của workload.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, keystore thuộc chương **Key storage**, liên quan trực tiếp đến vòng đời khóa **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Một thiết kế đúng phải gắn lưu trữ khóa với **mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, least privilege và audit**, không chỉ tìm chỗ đặt một tệp `.p12`.

> **Quy tắc cốt lõi:** Keystore không đồng nghĩa “an toàn tuyệt đối”. **Mật khẩu, quyền hệ điều hành, nơi lưu tệp, cơ chế backup, provider, quyền ứng dụng và khóa đang được sử dụng** cùng quyết định mức bảo vệ thực tế.

### 1.1. Vật liệu nào thường có trong keystore?

| Loại vật liệu | Ví dụ | Mức độ cần bảo vệ |
| --- | --- | --- |
| **Private key** | Private RSA/EC/Ed25519 dùng TLS hoặc chữ ký số | Bí mật; kiểm soát quyền Sign/Decrypt/Derive và khả năng xuất |
| **Secret key đối xứng** | AES key, HMAC key trong định dạng/provider có hỗ trợ | Bí mật; cần giới hạn Encrypt/Decrypt/GenerateMac/VerifyMac |
| **Certificate chain** | Certificate của service và intermediate CA | Công khai nhưng phải bảo đảm đúng key và chuỗi tin cậy |
| **Trusted certificate** | Root/intermediate CA được tin cậy theo chính sách | Có thể công khai; phải bảo vệ **tính toàn vẹn và nguồn gốc** |
| **Alias / metadata** | `billing-signing-v2`, `tls-server` | Không nhất thiết bí mật; cần chống tráo đổi hoặc nhầm đối tượng |

Một **chứng chỉ công khai** không cần mã hóa vì tính bí mật của nó, nhưng nếu truststore bị sửa để thêm CA do kẻ tấn công kiểm soát, ứng dụng có thể chấp nhận kết nối giả mạo. Vì vậy **bảo vệ toàn vẹn của truststore quan trọng ngang việc giữ bí mật private key trong keystore**.

## 2. Keystore trong Java hoạt động như thế nào?

Java Cryptography Architecture (**JCA**) cung cấp `KeyStore` thông qua **provider**. Ứng dụng chọn loại keystore, tải nội dung hoặc kết nối đến backend, rồi làm việc với **alias và entry**.

~~~mermaid
flowchart TD
    APP["Java application / JSSE"] --> API["java.security.KeyStore API"]
    API --> P12["PKCS12 provider<br/>file/container có bảo vệ"]
    API --> JKS["JKS provider<br/>định dạng Java legacy"]
    API --> P11["PKCS11 provider<br/>token/HSM nếu cấu hình hỗ trợ"]
    APP --> KMS["KMS SDK / API riêng<br/>không mặc định là KeyStore"]
    APP --> POLICY["Application authorization<br/>và key inventory"]
    POLICY --> API
    POLICY --> KMS
~~~

Điểm cần hiểu:

1. **`KeyStore.getInstance(type)`** chọn implementation; type không nói đủ nơi chứa vật liệu khóa.
2. **`load(...)`** tải hoặc khởi tạo kho; ý nghĩa tham số phụ thuộc provider. Với file PKCS#12, thường dùng InputStream và password; với PKCS#11 có thể dùng cơ chế token/provider riêng.
3. **`getEntry(alias, protection)`** truy xuất entry theo alias. Kiểu entry xác định những gì có trong kho.
4. **`store(...)`** lưu thay đổi nếu backend có hỗ trợ và policy cho phép. Không mặc định mọi token HSM hoạt động như file có thể serialise.
5. **`KeyStore` không thực hiện authorization nghiệp vụ** như “tenant A có được xem hóa đơn B không?”. Tầng ứng dụng và IAM vẫn phải kiểm tra.

### 2.1. Alias là tên tham chiếu, không phải danh tính tin cậy

Alias như `app-server` chỉ là tên để chọn một entry trong kho. Một keystore có thể được cập nhật để alias đó trỏ đến **key/certificate khác**. Vì vậy:

- Không coi alias là bằng chứng chứng chỉ thuộc đúng hostname/issuer.
- Khi rotation, theo dõi **key ID, version, certificate serial/public fingerprint và thời điểm hiệu lực** trong inventory.
- Kiểm tra đúng alias và entry type trước khi dùng; không tự chọn “alias đầu tiên” nếu ứng dụng cần danh tính cụ thể.
- Bảo vệ quyền thay alias/entry; việc tráo trust certificate có thể gây **MITM**, dù không lấy được private key.

### 2.2. Ba entry thường gặp trong Java KeyStore

| Java KeyStore entry | Thành phần | Công dụng điển hình |
| --- | --- | --- |
| **`KeyStore.PrivateKeyEntry`** | Private key + certificate chain liên quan | TLS identity, ký số khi khóa có thể được ứng dụng/provider truy xuất |
| **`KeyStore.SecretKeyEntry`** | SecretKey đối xứng | AES/HMAC key trong provider/format hỗ trợ |
| **`KeyStore.TrustedCertificateEntry`** | Chứng chỉ được đánh dấu trusted | Truststore và quản lý trust anchors |

**`PrivateKeyEntry` cần certificate chain** khi lưu vào API Java KeyStore thông dụng. Một cặp khóa vừa sinh ra bằng `KeyPairGenerator` chưa tự có certificate: chứng chỉ có thể được cấp qua PKI/CSR hoặc một quy trình phát hành đã được kiểm soát.

**Không phải mọi provider hoặc kiểu keystore đều hỗ trợ mọi entry**. Ví dụ, hỗ trợ `SecretKeyEntry`, key wrapping hoặc khả năng export private key có thể khác nhau giữa PKCS#12, JKS, PKCS#11 và nhà cung cấp HSM.

## 3. Những loại keystore cần phân biệt

### 3.1. PKCS#12 (P12/PFX)

**PKCS#12** là định dạng container phổ biến để lưu private key, chứng chỉ và một số loại secret key tùy provider. Trong Java hiện đại, **`PKCS12` là kiểu keystore mặc định thường gặp**. File thường mang đuôi `.p12` hoặc `.pfx`, nhưng **đuôi file không quyết định định dạng thực tế**.

Ưu điểm:

- Hỗ trợ trao đổi chứng chỉ và private key giữa các công cụ khi cấu hình tương thích.
- Hữu ích cho TLS certificate deployments và một số ứng dụng Java standalone.
- Có thể được bảo vệ bằng cơ chế mật khẩu, integrity và encryption của định dạng/provider.

Giới hạn:

- Khi process có quyền mở kho, private key có thể được tải vào bộ nhớ của ứng dụng/provider.
- Mật khẩu yếu, tệp lộ qua artifact/backup hoặc quyền file quá rộng làm tăng rủi ro.
- Các thuật toán bảo vệ bên trong PKCS#12, khả năng nhập/xuất secret key và tương thích công cụ **phụ thuộc provider và phiên bản**.
- Việc có `storePassword` không chứng minh private key hoàn toàn **non-exportable**.

### 3.2. JKS (Java KeyStore) và định dạng legacy

**JKS** là định dạng lịch sử của Java, từng được dùng rộng rãi cho chứng chỉ và private keys. Trong nhiều dự án Java cũ có file `.jks`. Nó vẫn có thể được đọc ở môi trường tương thích, nhưng **không nên tự chọn JKS cho một thiết kế mới chỉ vì tài liệu cũ dùng JKS**.

Khi cần migration, cần:

- Biết **định dạng gốc thực tế**, không chỉ suy từ extension.
- Xác minh alias, entry types, certificate chains, thuật toán bảo vệ và password.
- Chuyển sang **PKCS#12 hoặc giải pháp HSM/KMS** phù hợp chính sách và kiểm thử thực tế.
- Không mất khả năng TLS handshake, Verify chữ ký lịch sử hay phục hồi backup sau migration.

**JCEKS** cũng là định dạng/provider legacy thường thấy trong hệ Java cũ. Không mặc định “JCEKS hỗ trợ secret key” đồng nghĩa an toàn hơn PKCS#12/KMS hiện đại. Đánh giá thuật toán bảo vệ nội bộ và chính sách hiện hành trước khi giữ hoặc di chuyển.

### 3.3. PKCS#11 và HSM

**PKCS#11** là giao diện tiêu chuẩn để tương tác với **cryptographic token/HSM**, không phải chỉ là một đuôi file khác. Khi Java có provider tương thích (chẳng hạn họ SunPKCS11 trên môi trường phù hợp), `KeyStore` loại `PKCS11` có thể cho phép **tham chiếu đến các object trong token**.

Ở đây:

- Private key có thể được tạo **ngay trong HSM** và đánh dấu non-exportable theo chính sách thiết bị.
- `PrivateKey` trong Java có thể đóng vai trò **handle/đối tượng proxy** phục vụ phép toán, không phải chứa bytes giải mã được.
- Việc load, PIN/slot/token selection, login, alias và key availability có **ngữ nghĩa đặc thù provider**.
- Phải xét HSM partitions, cluster/replicas, quyền Sign/Decrypt, backup, tamper response và audit.

**Không mặc định Java KeyStore PKCS11 là một “bản sao HSM nằm trong RAM”**, cũng không nên ép xuất raw private key chỉ để chuyển thành file P12 nếu mục tiêu là bảo vệ trong HSM.

### 3.4. KMS, cloud secret manager và OS key store

Một **KMS managed service** có thể cung cấp APIs như **CreateKey, Sign, Decrypt, GenerateDataKey, Wrap/Unwrap** nhưng không nhất thiết expose toàn bộ qua `java.security.KeyStore`. Ứng dụng có thể dùng **SDK KMS riêng** và chỉ giữ **key ID/resource reference**.

**Secret manager** có thể lưu một file PKCS#12 hoặc password của keystore, nhưng điều đó không đồng nghĩa với cơ chế **non-exportable private key** của HSM. Hệ điều hành cũng có những keystore/truststore riêng, có thể được một provider Java tích hợp tùy nền tảng.

| Giải pháp | Vật liệu khóa nằm ở đâu? | Ranh giới cần đánh giá |
| --- | --- | --- |
| File PKCS#12 | File được bảo vệ, có thể được ứng dụng tải vào JVM | File ACL, password, process memory, backup |
| File JKS/JCEKS legacy | File định dạng Java/provider tương ứng | Tương thích, thuật toán bảo vệ, kế hoạch thay đổi |
| PKCS#11/HSM | Token/HSM theo key attributes | Non-exportability, key usage, PIN, slots, grants và HSM audit |
| Managed KMS | Backend của nhà cung cấp qua API/SDK | IAM, API scope, key deletion/rotation, replication, logging |
| Secret manager | Kho bí mật có quản lý phiên bản/truy cập | Có thể trả nguyên private key bytes; policy cấp phát và cache |

**Kết luận:** Chọn **kiểu lưu giữ theo mô hình đe dọa**. Định dạng `.p12` không tự đồng nghĩa an toàn cao hay thấp; khả năng bảo vệ phụ thuộc cả **quy trình cấp phát, định danh, vận hành và giới hạn xuất khóa**.

## 4. Keystore khác truststore như thế nào?

Trong triển khai TLS/JSSE của Java, hai thuật ngữ này thường đi cùng nhau nhưng khác **vai trò**:

- **Keystore dùng cho identity** thường chứa **private key và certificate chain** của endpoint để chứng minh danh tính qua cơ chế TLS.
- **Truststore** chứa các **chứng chỉ/trust anchors** mà endpoint được phép tin khi xác minh chứng chỉ của bên kia.

Điểm quan trọng: **Keystore và truststore đều có thể sử dụng cùng API `KeyStore` và cùng định dạng PKCS#12/JKS**. Sự khác nhau là **nội dung và cách sử dụng**, không nhất thiết là hai loại file khác nhau.

~~~mermaid
sequenceDiagram
    participant CLIENT as Java HTTPS client
    participant SERVER as TLS server
    participant KS as Server identity keystore
    participant TS as Client truststore
    SERVER->>KS: Sử dụng private key qua provider
    KS-->>SERVER: Phép ký/chứng minh sở hữu khóa
    CLIENT->>SERVER: TLS handshake
    SERVER-->>CLIENT: Certificate chain + handshake authentication
    CLIENT->>TS: Kiểm tra trust anchor theo chính sách
    TS-->>CLIENT: Trust material được cấu hình
    CLIENT->>CLIENT: Verify chain, hostname/identity, validity, usage, policy
    Note over CLIENT,SERVER: TLS key agreement và traffic keys thuộc TLS stack
~~~

### 4.1. Truststore không biến một chứng chỉ thành an toàn nếu cấu hình sai

Ngay cả khi certificate chain dẫn đến một CA trong truststore, ứng dụng vẫn cần kiểm tra:

1. **Hostname/endpoint identity** phù hợp với đích kết nối.
2. Chứng chỉ đúng **thời hạn, Key Usage/EKU, thuật toán và chain** theo policy.
3. Trạng thái **thu hồi** theo cơ chế PKI được yêu cầu trong hệ thống.
4. Trust anchor có đúng **mục đích/môi trường** không.

**Không dùng một TrustManager “accept all certificates”** để giải quyết lỗi truststore. Việc này bỏ qua một lớp bảo vệ chống man-in-the-middle.

### 4.2. mTLS yêu cầu hai phía có vai trò rõ ràng

Với **mutual TLS (mTLS)**, cả client lẫn server có thể cần:

- **Identity keystore:** Chứng chỉ + private key của chính mình.
- **Truststore:** Danh sách trust anchors/chứng chỉ cần thiết để xác minh đối tác.

Keystore bảo vệ danh tính kỹ thuật; **mTLS không tự thay thế authorization nghiệp vụ** như tenant, scope, quyền sửa hoặc đọc đơn hàng. Cần phân biệt **“đã xác thực workload”** với **“được phép làm hành động này”**.

## 5. Mật khẩu keystore bảo vệ những gì và có giới hạn nào?

Với keystore dạng file, mật khẩu thường phục vụ một hoặc nhiều mục tiêu như **bảo vệ nội dung nhạy cảm, dẫn xuất khóa để mã hóa entry và kiểm tra tính toàn vẹn của kho**, tùy định dạng/provider. Đừng xem password là cơ chế bảo vệ duy nhất.

### 5.1. Những lớp mật khẩu dễ nhầm lẫn

| Khái niệm | Dùng vào việc gì? | Lưu ý |
| --- | --- | --- |
| **Store password** | Tải/lưu keystore và các cơ chế bảo vệ ở mức container tùy provider | Không phải quyền nghiệp vụ theo tenant |
| **Key entry password / PasswordProtection** | Bảo vệ hoặc truy xuất một entry chứa key khi backend hỗ trợ | Một số kiểu/provider yêu cầu trùng store password |
| **Token PIN / HSM login** | Xác thực phiên hoặc vai trò với cryptographic token | Thường là quyền token/provider, không phải password file P12 |
| **Secret manager credential** | Cho phép workload lấy password hoặc secret cần thiết | Bị chiếm có thể dẫn đến lấy password rồi mở file |
| **OS account / file ACL** | Kiểm soát tiến trình/người có thể đọc hoặc thay file | Vẫn cần ngay cả khi file được mã hóa bằng password |

**Không giả định một PKCS#12 entry được bảo vệ riêng độc lập chỉ vì code truyền hai biến password khác nhau.** Khả năng đặt password riêng và khả năng tương tác khi import/export phụ thuộc **provider, loại entry và công cụ**; phải kiểm thử chính xác môi trường triển khai.

### 5.2. Kẻ tấn công có file nhưng không có password

Nếu attacker lấy được file keystore:

- Có thể thử **đoán password offline** tùy thuật toán bảo vệ và cách định dạng được cấu hình.
- Nếu password yếu, khả năng bị mở kho tăng lên, dù file được mã hóa.
- Nếu có thêm backup, build artifact, password trong file cấu hình hoặc môi trường chạy, mức độ xâm phạm có thể cao hơn nhiều.
- Khóa đã được xuất và lưu ngoài keystore trước đó không còn được bảo vệ bởi password của file hiện tại.

Vì vậy, chọn **password mạnh sinh từ cơ chế bí mật phù hợp**, hạn chế quyền lấy password, không hardcode trong Git, image, environment dump hoặc command line. Mật khẩu có thể được cấp qua secret manager với danh tính workload và chính sách truy cập cụ thể; vẫn phải xem xét cache, việc xuất hiện trong memory và quá trình rotation.

### 5.3. Kẻ tấn công có quyền trong process

Khi JVM đang chạy và đã mở file PKCS#12, hệ điều hành, debugger hoặc một mã độc trong cùng process có thể có khả năng truy cập **đối tượng khóa đã giải bảo vệ** hoặc yêu cầu provider thực hiện phép toán. Chỉ dùng password dài không tự bảo vệ trước một process bị chiếm hoàn toàn.

Với HSM non-exportable, việc trích xuất raw bytes có thể khó hơn, nhưng attacker chiếm workload có quyền **Sign/Decrypt** vẫn có thể yêu cầu phép toán trái phép. Bảo vệ khóa bao gồm **IAM, giới hạn phạm vi operation, authorization trước khi ký/giải mã, audit và phát hiện bất thường**.

### 5.4. Bảo vệ tính toàn vẹn của truststore

Truststore có thể chỉ chứa public certificates; việc “không có secret để lộ” **không cho phép ai cũng được sửa file**. Attacker thay nội dung truststore bằng root CA của mình có thể làm ứng dụng tin chứng chỉ giả.

Phải kiểm soát:

- Quyền thay file/entry và nguồn certificate import.
- Cơ chế integrity bảo vệ container (nếu có) và tính toàn vẹn của quá trình deployment.
- Fingerprint/trust anchor được phê duyệt, thay đổi có ticket và audit.
- Không để application runtime không cần thiết có quyền **ghi** truststore.

## 6. Java 17: tạo và đọc PKCS#12 SecretKeyEntry trong bộ nhớ

Đoạn mã minh họa sự khác nhau giữa **secret key đối xứng** và **password bảo vệ keystore**. Nó dùng **AES-256 SecretKey**, đặt vào một **PKCS#12 KeyStore**, serialize container vào byte array, tải lại rồi so sánh key bytes. Đây là **bài tập API**, không phải kiến trúc lưu trữ DEK production.

**Yêu cầu:** Java 17 với provider PKCS#12 hỗ trợ SecretKeyEntry. Nếu provider cụ thể không hỗ trợ kiểu entry hoặc cấu hình bảo vệ, nó sẽ báo lỗi; không tự động chuyển sang một legacy keystore chỉ để né policy.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.Console;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class Pkcs12SecretKeyDemo {
    private Pkcs12SecretKeyDemo() {}

    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Run in a console so password is not in source/arguments");
        }
        char[] password = console.readPassword("Demo PKCS12 password: ");
        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("Password is required");
        }

        try {
            KeyGenerator generator = KeyGenerator.getInstance("AES");
            generator.init(256); // Provider sử dụng RNG mật mã phù hợp.
            SecretKey generated = generator.generateKey();

            KeyStore store = KeyStore.getInstance("PKCS12");
            store.load(null, password); // Tạo kho mới trong bộ nhớ.
            store.setEntry(
                    "demo-aes-key-v1",
                    new KeyStore.SecretKeyEntry(generated),
                    new KeyStore.PasswordProtection(password)
            );

            ByteArrayOutputStream serialized = new ByteArrayOutputStream();
            store.store(serialized, password);
            byte[] containerBytes = serialized.toByteArray();

            // Mô phỏng quá trình tải lại kho đã được bảo vệ.
            KeyStore reopened = KeyStore.getInstance("PKCS12");
            reopened.load(
                    new ByteArrayInputStream(containerBytes), password);
            KeyStore.Entry entry = reopened.getEntry(
                    "demo-aes-key-v1",
                    new KeyStore.PasswordProtection(password)
            );

            if (!(entry instanceof KeyStore.SecretKeyEntry)) {
                throw new SecurityException("Expected a secret key entry");
            }

            SecretKey loaded = ((KeyStore.SecretKeyEntry) entry).getSecretKey();
            byte[] originalBytes = generated.getEncoded();
            byte[] recoveredBytes = loaded.getEncoded();
            try {
                System.out.println("Entry type: SecretKeyEntry");
                System.out.println("Key recovered: " +
                        MessageDigest.isEqual(originalBytes, recoveredBytes));
            } finally {
                if (originalBytes != null) {
                    Arrays.fill(originalBytes, (byte) 0);
                }
                if (recoveredBytes != null) {
                    Arrays.fill(recoveredBytes, (byte) 0);
                }
                Arrays.fill(containerBytes, (byte) 0);
            }
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Kết quả dự kiến, nếu provider hỗ trợ:

~~~text
Entry type: SecretKeyEntry
Key recovered: true
~~~

### 6.1. Vì sao ví dụ không ghi file?

Mục tiêu ở đây là minh họa **API và protection**, tránh tạo ra một file secret không được quản trị ngay trong ví dụ. Dù byte array chỉ ở RAM, nó vẫn có **sao chép và giới hạn zeroization**:

- **ByteArrayOutputStream** có thể giữ bản sao buffer ngoài mảng trả bởi toByteArray.
- **SecretKey/provider** có thể giữ bản sao của raw key.
- **Arrays.fill** chỉ xóa những mảng byte/char mà chương trình có quyền truy cập, không chứng minh JVM đã loại bỏ mọi bản sao.
- Mật khẩu được nhập qua console để không in lên command line, nhưng phải tiếp tục bảo vệ nguồn cấp phát/password ở môi trường thực tế.

**Không dùng generated.getEncoded() trong production chỉ để kiểm tra key** nếu khóa phải non-exportable. Ví dụ thao tác trên khóa đối xứng xuất được bytes; trong HSM nên kiểm tra bằng phép toán được phép và handle thay vì xuất key material.

### 6.2. Nếu cần ghi PKCS#12 xuống disk

Trong ứng dụng thực, phải dùng **thư mục do hệ thống quản lý, quyền file tối thiểu, mật khẩu được cấp qua kênh phù hợp và cơ chế ghi an toàn**. Cân nhắc tạo file tạm trong cùng filesystem với quyền hạn chế rồi thay thế có kiểm soát, xử lý crash/rollback và kiểm tra độ toàn vẹn sau khi cập nhật.

Lưu ý:

- **Không** ghi vào đường dẫn tạm công khai hoặc thư mục artifact không kiểm soát.
- **Không** đưa store password trực tiếp vào shell history hoặc command-line arguments.
- **Không** giả định file permission kiểu POSIX hoạt động tương tự trên Windows; phải xem xét ACL theo hệ điều hành.
- **Không** xem copy/backup keystore file là một hành động vô hại: đó có thể là bản sao private key.
- **Không** bỏ qua đồng bộ giữa key file, certificate chain, alias và key inventory khi triển khai.

### 6.3. Khi SecretKeyEntry là lựa chọn không phù hợp

Đối với dữ liệu production ở quy mô lớn, thường **không nên đưa hàng triệu DEK riêng vào một file PKCS#12**. Thiết kế envelope encryption thường lưu DEK ở dạng **wrapped DEK cạnh ciphertext**, còn KEK trong KMS/HSM; ứng dụng dùng DEK trong phạm vi ngắn hạn và bảo vệ memory/caches.

Một tệp keystore chứa nhiều secret keys làm phức tạp **rotation theo tenant, backup, quyền phân tách và crypto-erasure**. Tách cấu trúc theo nhu cầu thay vì biến keystore thành một “secret database” tổng quát.

## 7. Java 17: tải keystore/truststore cho SSLContext

Trong Java, **JSSE (Java Secure Socket Extension)** dùng **KeyManager** để chọn danh tính/chứng chỉ cùng private key của endpoint và **TrustManager** để kiểm tra trust khi xác minh peer. Các thành phần này có thể được cấu hình từ hai keystore PKCS#12 khác nhau.

Ví dụ dưới đây **không tạo chứng chỉ**, chỉ tải hai tệp do hệ thống triển khai cung cấp. Mật khẩu được truyền tới hàm từ nguồn an toàn do caller quản lý; ví dụ không hardcode mật khẩu. Chứng chỉ và private key phải được cấp/phân phối trước qua PKI/quy trình tin cậy.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class TlsKeyStoreLoader {
    private TlsKeyStoreLoader() {}

    static KeyStore loadPkcs12(Path path, char[] password)
            throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(path)) {
            store.load(input, password);
        }
        return store;
    }

    public static SSLContext createTlsContext(
            Path identityKeystore,
            char[] identityStorePassword,
            char[] privateKeyPassword,
            Path truststorePath,
            char[] truststorePassword
    ) throws Exception {
        KeyStore identities = loadPkcs12(
                identityKeystore, identityStorePassword);
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(identities, privateKeyPassword);

        KeyStore trustedCertificates = loadPkcs12(
                truststorePath, truststorePassword);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustedCertificates);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
        return tls;
    }
}
~~~

### 7.1. Phần code đã làm được

1. Tải **identity keystore** chứa private key entry với certificate chain.
2. Cấp **private key password** cho KeyManagerFactory. Với một số PKCS#12/provider, key entry password phải phù hợp store password; phải kiểm thử.
3. Tải **truststore** riêng và khởi tạo TrustManagerFactory.
4. Tạo SSLContext từ KeyManagers và TrustManagers; ứng dụng có thể dùng nó để cấu hình TLS client/server.
5. Dùng InputStream trong **try-with-resources** để đóng tệp sau khi đọc.

### 7.2. Những điều SSLContext chưa bảo đảm

**SSLContext không tự thực hiện một handshake chỉ vì nó được tạo.** Khi dùng client socket/engine hoặc HTTP client, phải bảo đảm:

- **Endpoint identification/hostname verification** được bật đúng với API và loại kết nối. Với raw SSLSocket, cần cấu hình **SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")** cho client khi muốn kiểm tra danh tính HTTPS; với HttpClient tiêu chuẩn, không tắt cơ chế hostname verification.
- Chọn **giao thức/cipher suites** phù hợp chính sách; `SSLContext.getInstance("TLS")` không có nghĩa code tự ép chỉ TLS 1.3.
- Server yêu cầu **client authentication** khi mTLS là yêu cầu; cấu hình client certificate và truststore tương ứng.
- Chứng chỉ có **SAN, Key Usage, EKU, trust chain và thời hạn** phù hợp; chính sách revocation cần được cấu hình/kiểm chứng theo hệ thống.
- **Authorization** theo người dùng, service, tenant và resource vẫn được ứng dụng xử lý sau TLS.
- Không cài một custom TrustManager chấp nhận toàn bộ chứng chỉ để bỏ qua lỗi cấu hình.

### 7.3. Mật khẩu và khả năng làm mới phiên TLS

Phần code nhận **char[]** nhưng không tự xóa vì **caller có thể còn sử dụng chúng**. Ở nơi sở hữu mật khẩu, phải quản lý thời gian sống, sau khi cấu hình xong thì xóa những mảng được phép xóa. Việc xóa char[] không loại bỏ mọi bản sao trong Java provider.

Khi **rotate certificate/private key**, ứng dụng đang chạy có thể giữ **SSLContext, KeyManager hoặc kết nối TLS cũ**. Thay file `.p12` trên disk không bảo đảm mọi connection ngay lập tức sử dụng key mới. Cần thiết kế **reload/recreate SSLContext, rolling deployment, connection draining và kiểm thử handshake**, tùy framework.

## 8. Quản trị keystore bằng keytool: thao tác nào cần biết?

**keytool** là công cụ kèm Java để làm việc với keystores và certificates. Nó hữu ích cho kiểm tra, tạo mẫu thử và chuyển định dạng, nhưng **không thay thế PKI/CA, HSM policy hoặc quy trình phê duyệt production**.

### 8.1. Xem danh sách entry và loại kho

Ví dụ lệnh:

~~~text
keytool -list -v -keystore service-identity.p12 -storetype PKCS12
~~~

Thông thường công cụ sẽ yêu cầu nhập store password. Quan sát **alias, entry type, certificate chain, serial, issuer, validity và fingerprint** theo nhu cầu. **Không hiển thị hoặc chia sẻ password, private key hoặc nội dung nhạy cảm** trong ticket/log.

### 8.2. Tạo keystore cho thử nghiệm (không phải chứng chỉ production)

~~~text
keytool -genkeypair -alias demo-tls -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -keystore demo-identity.p12 -storetype PKCS12 -validity 30 -dname "CN=demo.local" -ext "SAN=dns:demo.local"
~~~

Lệnh tạo RSA key pair và một **chứng chỉ tự ký** để minh họa thao tác. Nó **không tạo chứng chỉ tự động được client production tin cậy**. Với dịch vụ thật, cần cơ chế cấp chứng chỉ/chứng minh danh tính được quản lý và thuật toán/cấu hình theo chính sách.

Đối với những môi trường bắt buộc **HSM non-exportable**, **không chạy lệnh sinh file private key** rồi dùng như đường vòng của chính sách.

### 8.3. Import certificate/trust anchor có kiểm soát

~~~text
keytool -importcert -alias approved-root-ca -file approved-root-ca.pem -keystore client-trust.p12 -storetype PKCS12
~~~

**Trước khi import**, xác minh CA certificate/fingerprint qua **nguồn tin cậy độc lập** và quyết định phạm vi trust. Việc import một certificate do attacker gửi rồi chấp nhận confirmation không tạo niềm tin an toàn.

Một truststore chứa CA root quá rộng có thể mở rộng những tổ chức phát hành được ứng dụng tin. **Không nhập mọi CA công khai vào truststore nội bộ** nếu ứng dụng chỉ cần tin một miền dịch vụ cụ thể.

### 8.4. Chuyển JKS sang PKCS#12

~~~text
keytool -importkeystore -srckeystore legacy.jks -srcstoretype JKS -destkeystore migrated.p12 -deststoretype PKCS12
~~~

Đây chỉ là **ví dụ lệnh chuyển đổi**. Khi migration:

1. Đọc được **nguồn** và bảo vệ các password theo cơ chế an toàn.
2. Kiểm tra **alias, private key entry, certificate chains và loại thuật toán** được chuyển đủ.
3. Chỉ thực hiện trong môi trường được cấp quyền, không làm rò keystore qua log hoặc artifact.
4. Kiểm thử **TLS handshake, Sign/Verify, DR restore và key usage** trước khi chuyển production.
5. Xử lý file/backup JKS cũ theo retention và quy trình hủy; không xóa ngay khi chưa biết còn phụ thuộc.

**Chuyển format không tự thay private key hoặc nâng độ mạnh của cặp khóa**. Nếu private key yếu hoặc đã lộ, phải xem xét **sinh cặp mới và thay chứng chỉ/trust**, không chỉ đưa nó vào container mới.

## 9. Thiết kế quyền truy cập keystore: không chỉ có password

**Least privilege** yêu cầu người dùng, workload và hệ thống vận hành chỉ có **quyền cần thiết** đối với file, secret, HSM hoặc API KMS.

### 9.1. Ranh giới truy cập thực tế

| Lớp | Câu hỏi kiểm soát | Rủi ro nếu cấu hình sai |
| --- | --- | --- |
| **Filesystem** | Ai có thể đọc, ghi, thay tệp PKCS#12/JKS? | Lấy file, thay certificate/private key |
| **Secret distribution** | Ai lấy được password/token/PIN và trong bao lâu? | Mở kho từ backup hoặc nạp kho trái phép |
| **Process identity** | Service nào được mount/đọc file? | Workload không liên quan dùng private key |
| **IAM/KMS/HSM** | Principal có những operation Sign/Decrypt/Unwrap/Delete nào? | Lạm dụng API dù vật liệu non-exportable |
| **Application authorization** | Ai được yêu cầu ký hoặc giải mã dữ liệu nào? | Ký tài liệu giả hoặc đọc dữ liệu sai tenant |
| **Deployment pipeline** | Ai thay file keystore/truststore được? | Chèn khóa hoặc CA giả từ CI/CD |
| **Audit** | Có phát hiện thay file, policy hoặc khối lượng Sign bất thường? | Không thể điều tra và thu hồi kịp thời |

### 9.2. File permissions và mount chỉ đọc

Một ứng dụng không cần cập nhật keystore tại runtime nên thường chỉ cần **đọc** file keystore và truststore, không có quyền **ghi**. Thao tác thay certificate/key được thực hiện qua **deployment đã kiểm soát**.

Trên Windows cần kiểm tra **NTFS ACL, service account, quyền backup và file share**. Trên Linux/Unix kiểm tra **owner, permission bits, ACL, container bind mount, secret volume và snapshot**. Không dùng một câu lệnh chmod mang tính minh họa rồi cho rằng mọi môi trường đều đã được bảo vệ.

### 9.3. Không chia sẻ cùng keystore và secret giữa mọi môi trường

**Development/test/staging/production** nên có **key material, password, identity và trust policy riêng**. Nếu production private key bị sao chép vào dev, việc xâm nhập máy phát triển có thể dẫn đến mạo danh production.

Đối với mTLS, test certificate nên được phân phối bởi **CA/trust domain** phù hợp cho test; không chỉ dùng chung production CA và hi vọng mỗi ứng dụng tự phân biệt bằng tên file.

### 9.4. Non-exportable key vẫn cần kiểm soát nội dung phép toán

Nếu dịch vụ được quyền gọi **HSM Sign**, application owner cần yêu cầu:

- Kiểm tra **issuer/tenant, nội dung ký, loại tài liệu và quyền nghiệp vụ** trước khi gọi Sign.
- Giới hạn request rate, principal, môi trường và key ID.
- Không cấp quyền **Export, Delete, ChangePolicy** cho service chỉ cần ký.
- Audit **ai gọi, key nào, operation nào, kết quả** mà không ghi private bytes.

Điều này phân biệt **bảo vệ key material** với **ngăn lạm dụng quyền sử dụng khóa**.

## 10. Keystore trong vòng đời khóa: từ tạo đến hủy

Một keystore là **một phần của key lifecycle**, không phải nơi cất khóa bất biến mãi mãi. Mỗi giai đoạn cần quyết định rõ ràng.

| Giai đoạn | Yêu cầu đối với keystore | Ví dụ lỗi |
| --- | --- | --- |
| **Tạo** | Chọn thuật toán, provider, key size/curve, password/attributes, key ID | Sinh RSA key yếu hoặc JKS không đáp ứng policy |
| **Cấp phát** | Đưa kho/key handle tới đúng workload qua kênh được kiểm soát | Gửi file P12 cùng password qua cùng một chat |
| **Lưu trữ** | ACL, secret manager, backup, integrity, môi trường và region | Bỏ file P12 vào container image hoặc public artifact |
| **Sử dụng** | Chỉ đúng alias, Key Usage, IAM, kiểm tra certificate/authorization | Truy xuất alias bất kỳ và dùng để Sign |
| **Xoay vòng** | Sinh key mới, certificate mới, rollout trust, reload keystore, versioning | Thay file nhưng tiến trình vẫn dùng SSLContext cũ |
| **Thu hồi** | Chặn Sign/Decrypt/Derive hoặc ngừng tin certificate theo policy | Disable HSM key nhưng verifier vẫn tin public key cũ |
| **Hủy** | Kiểm kê bản sao và dữ liệu/chữ ký phụ thuộc, xác minh destruction | Xóa file private RSA key khi ciphertext cũ cần giải mã |
| **Kiểm toán** | Truy vết thay file/entry, key ID, version, quyền và yêu cầu API | Log chỉ ghi “keystore loaded” mà không biết phiên bản nào |

### 10.1. Không xoay vòng chỉ bằng đổi password

Thay mật khẩu một file PKCS#12 có thể tăng bảo vệ file nếu password cũ không còn an toàn, nhưng **không đổi vật liệu private key hoặc symmetric key bên trong**.

Nếu **private signing key đã bị sao chép**, đổi store password chỉ làm bản sao hiện tại khó mở hơn; attacker vẫn có thể dùng **private key bytes đã lấy được**. Khi key material bị compromised, cần **tạo cặp khóa mới và cập nhật trust**, cùng xử lý chữ ký/dữ liệu bị ảnh hưởng.

### 10.2. Rotation chứng chỉ không luôn là rotation private key

**Gia hạn/reissue certificate** có thể dùng lại public/private key cũ trong một số quy trình, hoặc có thể sinh key pair mới. Đó là hai quyết định khác nhau.

Với một chính sách yêu cầu **thay key pair**, application owner phải xác minh private/public material thực sự thay đổi, không chỉ **certificate serial, ngày hết hạn hay alias**.

### 10.3. KeyStore alias không thay key inventory

Giả sử alias `tls-server` trước đây chứa certificate v1, nay được thay bằng v2. Nếu log chỉ ghi alias đó, sau một sự cố sẽ khó xác định request nào được ký bằng v1.

Nên lưu trong inventory **key ID/version, certificate serial hoặc public key fingerprint, owner, environment, purpose, keystore resource/version và mốc active/retired**. Không đưa raw private key vào inventory.

## 11. Rotation keystore và certificate: triển khai mà không gián đoạn

Các dịch vụ Java thường giữ KeyManager và SSLContext trong bộ nhớ, nên **thay file không đồng nghĩa thay khóa đang được dùng**. Một kế hoạch rotation cần phối hợp phía **identity producer** và các **trust consumers**.

### 11.1. Luồng rotation khái niệm

~~~mermaid
sequenceDiagram
    participant AO as Application owner
    participant CA as CA / KMS-HSM
    participant DEP as Deployment / Secret manager
    participant SERVER as Java TLS server
    participant CLIENT as Client / verifier
    AO->>CA: Request key/cert v2 được phê duyệt
    CA-->>AO: Key reference + public certificate chain v2
    AO->>CLIENT: Chuẩn bị trust/identity policy cho v2
    AO->>DEP: Phát hành keystore/key handle v2
    DEP->>SERVER: Reload/restart SSLContext có kiểm soát
    SERVER->>CLIENT: TLS handshake dùng identity v2
    CLIENT->>CLIENT: Verify chain, endpoint identity và policy
    CLIENT-->>AO: Kết quả test handshake/trust
    AO->>DEP: Ngừng dùng key/cert v1 theo kế hoạch
    Note over AO,CLIENT: Đối soát phiên cũ, cache, DR và audit
~~~

**Không phải mọi client cần import certificate riêng của server**: nếu client tin một CA phù hợp và certificate mới nằm trong chuỗi được tin, có thể không cần thêm leaf certificate vào truststore. Nhưng nếu client **pin leaf public key/certificate** hoặc dùng trust registry riêng, rollout phải tính đến cập nhật đó.

### 11.2. Trình tự đề xuất cho planned rotation

1. **Kiểm kê:** Key/cert v1 ở keystore nào, alias nào, instance nào, truststore/pin của client nào, khi nào hết hạn?
2. **Sinh vật liệu mới:** Nếu policy yêu cầu key pair mới, sinh trong đúng KMS/HSM hoặc môi trường được phê duyệt.
3. **Cấp certificate chain:** Kiểm tra SAN, issuer, validity, KU/EKU, signature algorithm và danh tính endpoint.
4. **Kiểm tra trust trước:** Client cần biết trust anchor hoặc pin mới trước thời điểm server chuyển, nếu thiết kế có yêu cầu.
5. **Triển khai v2:** Ghi file/secret mới, cập nhật cấu hình/alias, restart hoặc reload KeyManager/SSLContext theo framework.
6. **Test:** TLS handshake mới dùng v2, hostname verification đạt, client authentication hoạt động nếu là mTLS; không có fallback không an toàn.
7. **Quan sát:** Lỗi handshake theo cert version, client chưa cập nhật, instance còn dùng v1, DR và các endpoint dự phòng.
8. **Retire v1:** Ngừng sử dụng theo lịch và policy, lưu metadata/certificate lịch sử khi cần.
9. **Destruction:** Xóa private v1 theo điều kiện phụ thuộc, retention, backup và phê duyệt; không xóa chỉ vì v2 đã sẵn sàng.

### 11.3. Khóa bị compromised cần xử lý khác planned rotation

Nếu private key v1 đã lộ, cho phép v1 tiếp tục phục vụ một “cửa sổ tương thích” dài có thể tạo thời gian cho đối thủ **mạo danh endpoint hoặc giả mạo chữ ký**. Khi đó cần **emergency revocation**:

- Chặn việc dùng private key cũ ở workload và KMS/HSM theo mức rủi ro.
- Thu hồi certificate/trust liên quan, phân phối thay đổi và kiểm tra cache/clients.
- Cấp khóa/chứng chỉ mới từ nguồn đáng tin cậy.
- Kiểm tra các phiên/kết nối/chữ ký trong khoảng có thể bị xâm phạm.
- Ghi lại những bên nhận chưa cập nhật, không tuyên bố “revoke hoàn tất” chỉ vì thay tệp server.

### 11.4. Rollback phải giữ nguyên an toàn

Khi deploy v2 gây lỗi, rollback có thể làm app quay về keystore v1. Nếu v1 đã **revoked do compromise**, **không được hồi sinh v1** chỉ để hết lỗi. Cần thiết kế khả năng khôi phục qua v2 hoặc khóa mới hợp lệ, không hạ kiểm tra trust.

## 12. Backup, DR và bí mật tồn tại trong nhiều bản sao

Một file PKCS#12 có thể được copy vào:

- Database backup hoặc VM snapshot.
- Container image layer, CI/CD artifact và file phát hành.
- Máy laptop quản trị, thư mục upload, file share hoặc ticket.
- Region khác, ổ lưu trữ DR và hệ thống backup offline.
- Bộ nhớ JVM, heap/core dump, file swap hoặc bản cache của secret sidecar.

**Hủy hoặc thay mật khẩu file trên máy hiện tại không xóa những bản sao trước đó.** Inventory phải mô tả **đường phân phối, nơi backup, chủ thể được phép khôi phục và retention**.

### 12.1. Chính sách phục hồi phụ thuộc loại khóa

| Loại khóa trong keystore/HSM | Nhu cầu khôi phục | Điều phải tránh |
| --- | --- | --- |
| **TLS private signing key** | Có thể tạo key/cert mới; một số hệ thống cần continuity có kiểm soát | Phân phối file private key tràn lan chỉ để dễ DR |
| **Private decryption key** | Có thể cần giải mã DEK/ciphertext cũ | Hủy key khi còn bản mã không có đường migration |
| **MAC key** | Cần điều phối bên phát/bên nhận trong thời gian chuyển đổi | Giữ secret cũ mãi hoặc tái sử dụng giữa môi trường |
| **DEK trong file keystore** | Còn ciphertext phụ thuộc cho đến migration/retention | Sao chép file mất kiểm soát hoặc xóa quá sớm |
| **Public trust anchors** | Phải được khôi phục từ nguồn đúng với trạng thái thu hồi mới nhất | Restore truststore cũ làm sống lại CA/key đã ngừng tin |

### 12.2. HSM cluster và KMS replication không giống copy file

HSM có thể quản lý backup bằng **domain/quorum/secure wrapping** riêng. Managed KMS có thể có tính năng **multi-region keys, replication hoặc recovery** theo mô hình nhà cung cấp. Không tự kết luận private key có thể xuất file P12 để “backup HSM”; điều đó có thể vi phạm chính sách non-exportable.

Hãy xác minh:

1. Các khóa có thể phục hồi ở region/cluster nào?
2. DR workload được cấp quyền trong điều kiện nào? Có cần phê duyệt break-glass?
3. Key ID/ARN, alias, version và certificate chain được đồng bộ thế nào?
4. Backup HSM có chứa material mà chính sách destruction cần xử lý hay không?
5. Hủy/suspend key ở production có được phản ánh ở DR hay không?

### 12.3. Restore có thể hồi sinh trạng thái bị thu hồi

Nếu một snapshot cũ chứa keystore và truststore trước khi key bị revoked, restore có thể khiến:

- Server dùng private key cũ.
- Client tiếp tục tin certificate/CA cũ.
- IAM grants hoặc cấu hình alias quay lại giá trị trước sự cố.
- Ứng dụng đọc các secret từ backup không đúng môi trường.

Cần lưu **revocation record, key version và tombstone** ở control plane đáng tin cậy, đối soát sau restore và kiểm thử **negative cases**. Việc có file restore thành công **không chứng minh hệ thống phục hồi an toàn**.

### 12.4. Crypto-shredding và file keystore

Nếu DEK duy nhất mở được một tập ciphertext được lưu trong keystore, **hủy DEK cùng mọi bản sao có khả năng khôi phục** có thể góp phần thực hiện **cryptographic erasure**. Tuy nhiên:

- Nếu backup vẫn giữ DEK hoặc wrapped DEK có thể giải bọc, mục tiêu erasure chưa đạt hoàn toàn.
- Nếu có plaintext copy, xóa key không xóa bản plaintext đó.
- Nếu attacker đã lấy key+ciphertext trước khi hủy, hủy key ở hệ thống không thu hồi được dữ liệu từ attacker.
- Nếu dữ liệu vẫn phải giữ, hủy khóa có thể gây mất dữ liệu không thể phục hồi.

**Crypto-shredding phải được đánh giá theo mô hình đe dọa, tập bản sao và retention**, không chỉ dựa vào lệnh xóa file.

## 13. KMS/HSM, key inventory và envelope encryption: nơi nào cần keystore?

Một hệ thống dữ liệu quy mô lớn có thể có:

- **TLS identity keystore** của từng service (cặp private key và certificate).
- **Truststore** để xác minh CA/service identity.
- **KMS/HSM KEK** để bảo vệ DEK trong lưu trữ dữ liệu.
- **Wrapped DEK + ciphertext** trong database hoặc object storage.
- **Key inventory** để biết key ID/version, owner, purpose, environment và quan hệ phụ thuộc.

Không bắt buộc cất **mọi khóa** vào cùng một file. Một private signing key trong HSM có thể được dùng qua **key handle**, trong khi database chỉ giữ **wrapped DEK**. Việc áp dụng cùng một định dạng lưu trữ cho mọi loại vật liệu thường làm khó phân quyền và rotation.

~~~mermaid
flowchart TD
    AO["Application owner + security policy"] --> INV["Key inventory<br/>key ID, version, owner, purpose"]
    APP["Java application"] --> TLS["TLS identity keystore<br/>private key/certificate"]
    APP --> TRUST["Truststore<br/>approved CA/certificates"]
    APP --> KMS["KMS/HSM KEK hoặc signing key"]
    APP --> DATA["Encrypted data store<br/>wrapped DEK + IV + tag + ciphertext"]
    INV --> TLS
    INV --> TRUST
    INV --> KMS
    INV --> DATA
    KMS -->|"Authorized unwrap"| APP
    APP -->|"AEAD operations"| DATA
~~~

### 13.1. Vì sao không đặt tất cả DEK trong PKCS#12?

Giả sử mỗi tenant có hàng triệu bản mã và cần **rotation, crypto-erasure, vùng DR, định danh version và IAM riêng**. Một file PKCS#12 duy nhất chứa tất cả DEK có thể tạo ra:

- Điểm tập trung lớn khi file/password lộ.
- Khó tách quyền theo tenant: process mở file có thể thấy nhiều keys.
- Backup, cập nhật file và đồng bộ giữa nhiều instance khó quản lý.
- Khó xác định DEK nào đã được dùng trong bản mã nào nếu thiếu metadata ngoài.

Thiết kế thường tốt hơn là **DEK bảo vệ dữ liệu theo miền**, DEK được wrap và lưu có tham chiếu cùng ciphertext, **KEK trong KMS/HSM**. Nhưng chọn hạt độ DEK phải xét mức độ rủi ro, hiệu năng và khả năng của nhà cung cấp.

### 13.2. Keystore không thay Authorization

Một service có quyền mở file PKCS#12 chứa private key để ký **không có nghĩa mọi user được phép yêu cầu service ký mọi hóa đơn**. Một service được KMS cho phép Unwrap DEK **không có nghĩa người gọi được xem mọi dữ liệu tenant**.

Đặt **authorization nghiệp vụ** trước thao tác nhạy cảm. Khi cần, AEAD **AAD/encryption context** ràng buộc record ID, tenant và purpose qua metadata đáng tin cậy; không tin các trường client tự khai báo là quyết định cuối.

## 14. Keystore bị lộ hoặc bị tráo đổi: ứng phó ra sao?

**Incident response** phải bắt đầu bằng câu hỏi **thành phần nào đã bị xâm phạm**. Không phải mọi sự cố liên quan keystore đều có cùng hậu quả:

| Sự cố | Rủi ro chính | Hành động đầu tiên nên cân nhắc |
| --- | --- | --- |
| **File PKCS#12 bị sao chép, password chưa rõ có bị lộ** | Attacker có thể thử phá password offline | Cô lập file và password, xác định độ mạnh/thuật toán, đánh giá có cần thay private key |
| **File và password cùng bị lộ** | Private/secret key có thể bị khôi phục | Xem là key material exposure, chặn dùng cũ, thay keys và xử lý dữ liệu/trust phụ thuộc |
| **Private signing key bị lộ rõ** | Chữ ký giả, mạo danh TLS, JWT hoặc tài liệu | Chặn Sign, thay key/cert, thu hồi trust, điều tra chữ ký |
| **Kẻ tấn công sửa truststore** | Ứng dụng có thể tin CA hoặc endpoint giả | Khôi phục truststore từ nguồn tin cậy, kiểm tra kết nối/giao dịch trong khoảng |
| **HSM Sign API bị lạm dụng** | Có chữ ký giả dù private key không được xuất | Revoke principal/grant, chặn Sign, kiểm toán kết quả ký |
| **Private decryption key bị lộ** | Ciphertext/DEK gửi đến public key đó có thể bị giải mã | Thay key pair, rewrap DEK khi phù hợp, đánh giá bản mã đã sao chép |
| **Password keystore lộ nhưng file vẫn trong vùng được kiểm soát** | Tăng rủi ro nếu attacker lấy được bản file về sau | Thay password, kiểm tra quyền và đánh giá có bản file nào đã bị lấy |
| **Backup cũ khôi phục trust đã revoked** | Client/server tiếp tục tin khóa bị thu hồi | Đồng bộ revocation/tombstone, đối soát và negative tests |

### 14.1. Các bước phản ứng

1. **Triage:** Xác định file/resource ID, alias, key ID/version, owner, environment, host và thời điểm có thể xâm phạm.
2. **Containment:** Thu hồi credential, giới hạn principal, chặn Sign/Decrypt/Unwrap nguy hiểm, bảo toàn audit.
3. **Scope:** Tìm bản sao file/password, private key, chứng chỉ, hệ thống dùng keystore/truststore, ciphertext và chữ ký.
4. **Replace:** Sinh private/secret key mới khi cần, phát hành cert mới hoặc khôi phục trust source; không chỉ đổi alias.
5. **Migrate:** Rewrap/re-encrypt các DEK/ciphertext có liên quan, cập nhật public trust/JWKS, xử lý phiên/token còn hiệu lực.
6. **Verify:** Thử từ chối key/cert cũ ở nơi policy yêu cầu, xác minh dữ liệu cần giữ vẫn giải mã được, test DR.
7. **Retire/destroy:** Hủy key material/bản sao còn kiểm soát được theo retention và bằng chứng.
8. **Review:** Điều tra nguyên nhân (CI artifact, quyền file, password lộ, truststore bị sửa, HSM API abuse) và giảm rủi ro tồn dư.

**Không vội xóa toàn bộ keystore trước khi biết còn private decryption key cần đọc dữ liệu hợp lệ hay không.** Có thể cần tạm vô hiệu hóa rồi chuyển dữ liệu qua đường migration được phê duyệt. Ngược lại, không kéo dài việc sử dụng một private signing key rõ ràng đã compromised chỉ để tránh cập nhật client.

### 14.2. Thu hồi chứng chỉ không đồng nghĩa thu hồi key bytes

Nếu một certificate bị thu hồi qua CA, các client có thể ngừng tin nó **theo chính sách và khả năng cập nhật revocation information**, nhưng attacker vẫn giữ private key đã lấy. Một bên xác minh cũ hoặc offline có thể tiếp tục chấp nhận.

Tương tự, **đổi password PKCS#12 không khôi phục bí mật của private key đã xuất**. Quy trình sự cố phải xử lý cả **vật liệu khóa, các bên tin cậy và tác động nghiệp vụ**.

## 15. Tình huống thực tế: một Java Payments Service dùng mTLS và KMS

Một nền tảng có:

- **Payments Service** chạy nhiều instance Java trong production.
- **Identity keystore PKCS#12** chứa private key TLS của Payments và certificate chain.
- **Truststore** chỉ chứa trust anchors được phép để xác minh những dịch vụ liên quan.
- **KMS** giữ KEK production, ứng dụng dùng **AES-GCM DEK** qua envelope encryption cho dữ liệu thanh toán.
- **Security/IAM** quản lý chính sách, certificate provisioning và workload identities.
- **SRE** phụ trách deployment, backup, monitoring và DR.

### 15.1. Thiết kế lưu trữ

| Thành phần | Lựa chọn triển khai minh họa | Mục tiêu |
| --- | --- | --- |
| TLS identity | Keystore P12 cấp phát qua secret/deployment mechanism an toàn | Chỉ Payments workload đọc được; cert đúng tên dịch vụ |
| Truststore | PKCS#12 hoặc cơ chế trust do runtime quản lý | Chỉ tin CA/đối tác được phê duyệt, bảo vệ integrity |
| Password của identity P12 | Secret manager + workload IAM | Không hardcode, không dùng chung với test |
| KMS KEK | KMS key resource riêng của production theo scope | Không phát raw KEK cho Payments process |
| DEK | Sinh/unwrap qua KMS theo policy, dùng tạm trong ứng dụng | AEAD cho dữ liệu; hạn chế thời gian tồn tại |
| Database envelope | Ciphertext + wrapped DEK + IV/tag + key reference | Cho phép đọc đúng version và lập dependency inventory |
| Inventory | Key IDs, versions, owner, tenant, purpose, usage state | Rotation, incident, destruction có cơ sở |

**Không copy raw KEK vào PKCS#12 identity keystore** chỉ để gom hết secrets vào một chỗ. **TLS identity private key** và **DEK/KEK bảo vệ dữ liệu at rest** có mục tiêu, quyền sử dụng và vòng đời khác nhau.

### 15.2. Khi certificate Payments sắp hết hạn

1. Application owner và Security tạo yêu cầu thay certificate; xác định có cần sinh **private key mới** theo chính sách không.
2. PKI/CA phát hành certificate chain mới; kiểm tra SAN và identity của Payments.
3. Chuẩn bị trust cho phía đối tác/client nếu họ pin leaf/public key hoặc cần CA/truststore mới.
4. Phát hành file/handle v2 và password tương ứng qua kênh có quyền và audit.
5. Triển khai từng instance, **reload/recreate SSLContext** hoặc restart theo framework, kiểm thử handshake và mTLS.
6. Giám sát những instance còn chứng chỉ v1 và lỗi kết nối; xử lý DR/trust cache.
7. Retire v1 sau khi không còn phụ thuộc hợp lệ; giữ bản ghi inventory và audit.

### 15.3. Khi file P12 bị lộ trong CI artifact

1. Dừng phân phối artifact, giới hạn truy cập, bảo toàn bản ghi ai đã đọc.
2. Xác minh file có chứa **private key production** không, password có khả năng bị lộ không và phạm vi bản sao.
3. Nếu có căn cứ private key compromised, **sinh key pair và certificate mới**, chặn dùng/tin v1 theo quy trình.
4. Cập nhật Payments, đối tác mTLS, truststore/JWKS liên quan nếu có, và kiểm tra cache cũ.
5. Đối soát KMS IAM: việc lộ TLS private key **không tự chứng minh KEK bị lộ**, nhưng attacker có thể đã dùng danh tính bị chiếm để gọi API khác; cần điều tra log.
6. Sửa CI/CD: secrets không đưa vào artifact công khai, secret scanning, mount runtime, access scope và retention.

### 15.4. Những bài test cần chạy

| Test case | Kết quả mong đợi |
| --- | --- |
| Client kết nối đúng hostname/cert | TLS handshake thành công theo trust policy |
| Client đổi hostname sang tên không có trong cert | Endpoint identification thất bại |
| Truststore bị thêm CA không được duyệt | Integrity/deployment review phát hiện và chặn |
| Identity P12 được mở bằng password sai | Load/KeyManager khởi tạo thất bại, không fallback secret khác |
| Test workload cố lấy production keystore | Bị IAM/ACL/secret manager policy từ chối |
| Service signer bị cấm Sign sau revoke | KMS/HSM chặn thao tác; có audit |
| Thay certificate nhưng process chưa reload | Giám sát phát hiện vẫn đang dùng cert/SSLContext cũ |
| KMS KEK không khả dụng | Không dùng hardcoded DEK hay bỏ mã hóa; xử lý outage có kiểm soát |
| Đổi KEK bình thường | Wrapped DEK được migrate đúng; ciphertext vẫn đọc được |
| Khôi phục DR từ snapshot trước revocation | Không làm sống lại trust/key state đã bị thu hồi |
| Destroy private decryption key khi còn wrapped DEK | Dependency preflight chặn hoặc yêu cầu migration |

## 16. Kiểm soát audit và inventory cho keystore

Một keystore được vận hành tốt cần có **owner và dữ liệu truy vết**, không chỉ tên file. Mẫu metadata minh họa:

~~~yaml
# Registry metadata minh họa, không chứa raw key/password.
keystoreId: payments-identity-prod
environment: production
owner: payments-platform
locationType: managed-secret-volume
format: PKCS12
accessScope: payments-prod-workload
entries:
  - alias: payments-tls-v2
    entryType: PrivateKeyEntry
    keyPurpose: tls-server-authentication
    algorithm: RSA
    keyVersion: 2
    certificateIdentity: payments.internal.example
    lifecycleState: ACTIVE
    certificateReference: approved-pki-cert-v2
controls:
  storePasswordLocation: secret-manager-reference
  prohibitPrivateKeyExport: true
  requireChangeApproval: true
  auditCertificateReload: true
  requireBackupReview: true
~~~

**Đây chỉ là mô hình inventory**, không phải cấu hình tự động được PKCS#12 hay mọi HSM hiểu. Trường **prohibitPrivateKeyExport** là yêu cầu chính sách; nếu private key ở file P12, không được tự tuyên bố có cùng bảo đảm **non-exportable của HSM**.

### 16.1. Nên audit những sự kiện nào?

- Sinh/import/export keystore hoặc key material theo quyền.
- Thay alias/entry/certificate chain hoặc trust anchors.
- Đổi password, file permissions, secret manager grants hoặc KMS policy.
- Load keystore vào workload mới, restart/reload identity sau certificate rotation.
- API Sign/Decrypt/Unwrap từ HSM/KMS, nếu nền tảng hỗ trợ log ở mức cần thiết.
- Thất bại xác minh chứng chỉ, revocation check, mTLS handshake hoặc key version mismatch.
- Đặt keystore/key thành retired, revoked, disabled hoặc pending destruction.
- Restore DR, thay đổi principal/tenant/environment và hoạt động khẩn cấp.

**Không audit bằng cách ghi raw private key, AES DEK hoặc keystore password.** Ghi key ID/version, resource, actor, action, result, thời điểm và correlation/incident ID là cơ sở chính.

### 16.2. Khác biệt giữa audit tại file và audit tại KMS

Với **file P12**, provider Java không mặc nhiên gửi mọi lần **PrivateKeyEntry.getPrivateKey()** hoặc sử dụng key bytes đến một dịch vụ audit tập trung. Ứng dụng phải bổ sung **application/deployment/filesystem audit** phù hợp, nhưng không thể chứng minh một file đã bị copy hay đọc ở ngoài vùng kiểm soát chỉ bằng application log.

Với **HSM/KMS**, nhà cung cấp có thể log những API **Sign/Decrypt/Unwrap** và admin events theo khả năng; cần cấu hình, bảo vệ log và đối chiếu với **quyền nghiệp vụ**. Một lệnh Sign hợp lệ về mặt HSM vẫn có thể ký nội dung bị kẻ tấn công yêu cầu.

## 17. Những hiểu nhầm và lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Biện pháp đúng |
| --- | --- | --- |
| “Đã dùng keystore nên private key chắc chắn an toàn.” | File, password hoặc process memory vẫn có thể bị xâm phạm | Xác định format, provider, ACL, storage boundary và threat model |
| “PKCS#12 nghĩa là HSM non-exportable.” | File P12 có thể bị copy và mở khi có password | Dùng HSM/KMS để sinh và giữ key khi policy yêu cầu non-exportable |
| Ghi store password trong mã nguồn hoặc CLI args | Password rơi vào Git, process list, shell history hoặc log | Cấp qua secret manager/console/workload identity, hạn chế scope |
| Lưu file P12 trong container image | Secret bị sao chép qua registry, image layers, CI cache | Runtime secret provisioning/mount và quyền chặt |
| Dùng cùng password cho dev/test/prod | Lộ môi trường thấp có thể tăng nguy cơ ở prod | Tách secrets, identities, keystores và key material |
| Chỉ đổi password sau khi private key đã lộ | Key bytes đã bị sao chép vẫn dùng được | Sinh/thay khóa, thu hồi trust, đánh giá dữ liệu |
| Lấy alias đầu tiên trong kho làm identity | Dùng nhầm certificate hoặc private key | Chọn theo key reference/identity đã được cấu hình và review |
| Tự tin certificate đúng vì được import vào truststore | Trust anchor bị thêm sai hoặc hostname mismatch | Kiểm tra nguồn trust, chain, identity và KU/EKU |
| Dùng TrustManager accept-all để sửa lỗi TLS | Mất xác thực đối tác, dễ MITM | Sửa cấu hình CA/SAN/chain/revocation đúng |
| Thay file keystore mà không reload TLS | JVM tiếp tục dùng SSLContext hoặc identity cũ | Reload/recreate context, rolling deploy và handshake tests |
| Chỉ gia hạn certificate mà nghĩ đã thay private key | Private key cũ tồn tại và còn rủi ro | Kiểm tra key pair/version theo rotation policy |
| Coi JKS/JCEKS legacy là bảo mật tương đương P12 mới | Thuật toán bảo vệ và interoperability có thể không đáp ứng | Đánh giá provider, migration PKCS12/HSM và test |
| Ép HSM xuất key để import vào file P12 | Phá bảo đảm non-exportable và mở rộng phạm vi | Dùng provider/handle/SDK đã được duyệt |
| Xem public key trong P12 là đúng chủ thể nhận | Public key parse được nhưng có thể bị thay | Chứng chỉ/PKI hoặc trusted public-key registry |
| Dùng PKCS#12 làm database giữ tất cả DEK | Khó multi-tenant isolation, rotation và crypto-erasure | DEK dạng wrapped gắn với ciphertext, KEK ở KMS/HSM |
| Dùng một private key cho nhiều purpose tùy tiện | Khó IAM, Key Usage, audit và xử lý sự cố | Tách signing/encryption/derivation keys theo policy |
| Cho phép mọi workload có quyền đọc truststore sửa file | Có thể chèn CA giả | Mount read-only, protected deployment và integrity checks |
| Coi copy file keystore backup không có rủi ro | Tạo thêm bản sao private keys có thể truy xuất | Bảo vệ backup, inventory, access/retention |
| Xóa P12 ngay sau rotation | Có thể mất khả năng đọc dữ liệu hoặc verify lịch sử | Kiểm kê dependency, retention và recovery trước destruction |
| Restore snapshot cũ không kiểm tra key state | Hồi sinh revoked key/trust/grants | Revocation epoch, tombstone và reconciliation |
| Có mTLS nên bỏ authorization | Service đúng danh tính nhưng user vẫn vượt quyền | Kiểm tra user, tenant, resource và operation |
| Log private key/password để debug load failure | Tự gây sự cố lộ khóa | Log mã lỗi, alias, key ID, provider và correlation ID |
| API KMS gọi thành công là ứng dụng được phép đọc dữ liệu | KMS IAM khác application authorization | Kiểm tra nghiệp vụ trước hoặc cùng quy trình bảo vệ dữ liệu |

## 18. Checklist review keystore cho ứng dụng Java

Khi đánh giá một ứng dụng chuẩn bị lên production hoặc thực hiện security review, hãy trả lời:

1. **Mục đích:** Keystore giữ private signing key, decryption key, symmetric key hay trust certificates? Có đang trộn mục đích không?
2. **Định dạng:** Dùng PKCS#12, JKS legacy, PKCS#11/HSM hoặc KMS SDK? Provider và runtime có hỗ trợ đúng loại entry/thuật toán?
3. **Ranh giới:** Vật liệu private key sinh ở đâu, có từng nằm ngoài HSM không, có khả năng export hay không?
4. **Tham số mật mã:** Thuật toán, key size/curve, signature padding, Key Usage/EKU và certificate chain đáp ứng chính sách?
5. **Mật khẩu:** Store/key passwords có được quản lý riêng từ source và deployment artifact, với scope/quyền/rotation phù hợp?
6. **File access:** OS ACL, service account, backup permissions, container mounts và quyền ghi truststore/identity file đã được kiểm soát?
7. **Khóa nội bộ:** PrivateKeyEntry/SecretKeyEntry/TrustedCertificateEntry có đúng alias và được provider hỗ trợ? Có tránh fallback format không được duyệt?
8. **Identity:** Public certificate/SPKI có liên kết tới đúng hostname/issuer/workload, và trust source có được bảo vệ?
9. **Truststore:** Có phân biệt CA root, intermediate và leaf; không bật trust-all hoặc bỏ hostname verification?
10. **mTLS:** Client/server có đúng key identity, trust anchors và chính sách yêu cầu xác thực hai chiều?
11. **Authorization:** Ai có quyền mở kho, Sign/Decrypt/Unwrap và ai có quyền yêu cầu nghiệp vụ? Có tách quyền này?
12. **Môi trường:** Dev/test/staging/prod/DR có material, password, role và trust domain riêng theo thiết kế?
13. **Inventory:** Có key ID/version, owner, environment, purpose, certificate serial/fingerprint, trạng thái và các tài sản phụ thuộc?
14. **Rotation:** Có quy trình cấp key/cert mới, cập nhật verifier, reload SSLContext, connection drain và kiểm tra client cache?
15. **Emergency revoke:** Khi private key lộ, có chặn API, thu hồi cert/trust, thay key, điều tra log và thử negative tests?
16. **DEK/KEK:** Có phân biệt identity keystore với KMS envelope encryption, không lưu tràn lan raw DEK/KEK?
17. **Backup/DR:** Đã xác định bản sao của file/secret/key, restore strategy và khả năng không hồi sinh revoked trust?
18. **Destruction:** Có kiểm kê ciphertext/chữ ký/retention trước xóa, phân biệt scheduled/pending với executed?
19. **Audit:** Có ghi người gọi, key ID/version, operation, kết quả, thay đổi policy/cert mà không log secret bytes?
20. **Failure modes:** Sai password, hết hạn certificate, trust mismatch, KMS outage và provider lỗi có fail closed và cảnh báo?
21. **Migration:** Khi đổi từ JKS sang P12/HSM, có xác minh key entries, certificate chains, TLS handshake, data restore và rollback?
22. **Review:** Có chu kỳ rà soát orphaned keys, grants dư, certificate sắp hết hạn và key/cert được sử dụng ngoài environment?

## 19. Ghi nhớ

- **Keystore** là phương tiện quản lý key/certificate; với Java, **KeyStore API là abstraction** có thể dùng nhiều provider/backend. Không đồng nhất file PKCS#12 với HSM/KMS.
- **PKCS#12** thường phù hợp lưu/trao đổi identity key và certificates có bảo vệ; **JKS/JCEKS** là lựa chọn legacy cần xem xét; **PKCS#11** thường là giao diện tới token/HSM chứ không đơn thuần là định dạng file.
- **PrivateKeyEntry, SecretKeyEntry và TrustedCertificateEntry** có cách dùng khác nhau. Không phải mọi kiểu/provider hỗ trợ mọi loại entry.
- **Identity keystore khác truststore về mục đích**, dù đều có thể dùng java.security.KeyStore. Truststore cần bảo vệ **toàn vẹn**, còn identity keystore cần bảo vệ **bí mật private key và quyền sử dụng**.
- **Password không thay IAM, ACL hoặc ứng dụng authorization**. Process bị chiếm có thể lạm dụng key đã load; HSM non-exportable vẫn cần hạn chế API Sign/Decrypt.
- **Java KeyStore và JSSE** có thể tải identity/trust, nhưng ứng dụng phải cấu hình endpoint identity, TLS policy, mTLS khi cần, reload sau rotation và kiểm tra quyền nghiệp vụ.
- **KMS/HSM và envelope encryption** thường phù hợp bảo vệ KEK/private signing key, trong khi DEK được bọc theo dữ liệu. Không gom tất cả secrets vào một file chỉ vì thuận tiện.
- **Vòng đời đầy đủ** gồm generation, provisioning, storage, usage, rotation, revocation, destruction, backup/DR và audit. Đổi password, đổi alias, đổi certificate và thay key material là những hành động khác nhau.

Trước khi kết luận **“khóa đã được lưu an toàn trong keystore”**, hãy hỏi: **“Vật liệu khóa thực sự nằm ở đâu và ai có thể đọc hoặc sử dụng nó?”, “Public key/chứng chỉ và trust anchors có được xác thực đúng nguồn không?”, “Nếu file, mật khẩu hoặc quyền HSM bị xâm phạm, chúng ta có thể ngừng tin, thay khóa và phục hồi dữ liệu hợp lệ ra sao?”** Trả lời được bằng kiến trúc, chính sách và bằng chứng kiểm thử mới cho thấy keystore là một phần đáng tin cậy của hệ thống quản lý khóa.





