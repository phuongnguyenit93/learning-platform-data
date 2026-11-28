# Private key protection — Bảo vệ khóa riêng trong mật mã bất đối xứng

## 1. Vì sao private key cần được bảo vệ nghiêm ngặt?

Trong **mật mã bất đối xứng**, một cặp khóa gồm **public key** (khóa công khai) và **private key** (khóa riêng). Public key có thể chia sẻ theo mục đích của giao thức; private key phải nằm dưới quyền kiểm soát của chủ thể được phép. Hai khóa liên hệ về toán học nhưng việc biết public key **không cho phép tính private key một cách khả thi** khi thuật toán, tham số và độ dài khóa được chọn đúng.

**Private key protection** là tập hợp biện pháp bảo vệ vật liệu khóa riêng, kiểm soát việc sử dụng khóa và quản lý vòng đời. Đây là phần trọng yếu của quản lý khóa mật mã: private key bị lộ hoặc bị lạm dụng có hậu quả khác nhau theo mục đích của nó.

- **Khóa ký số:** Kẻ tấn công có thể tạo chữ ký giả mạo nếu có private key hoặc chiếm được quyền gọi thao tác ký. Ví dụ: giả mạo bản cập nhật phần mềm.
- **Khóa giải mã:** Kẻ tấn công có thể giải mã dữ liệu đã được mã hóa cho public key tương ứng, kể cả bản mã cũ vẫn còn lưu.
- **Khóa thỏa thuận khóa:** Lộ private key có thể làm tổn hại các phiên thỏa thuận khóa liên quan; mức độ ảnh hưởng tùy thuộc khóa tĩnh hay khóa tạm và giao thức.
- **Khóa xác thực:** Kẻ tấn công có thể mạo danh máy chủ, thiết bị hoặc dịch vụ trong giao thức chấp nhận public key/chứng thư tương ứng.

Ví dụ, một công ty dùng private key ký các gói phần mềm phát hành. Nếu file khóa nằm trên máy build và mọi job CI đọc được, một job bị xâm nhập có thể đánh cắp khóa. Chuyển khóa vào HSM giúp hạn chế xuất vật liệu, nhưng nếu mọi job vẫn được phép gọi `Sign` thì job bị xâm nhập có thể yêu cầu HSM ký mã độc.

> **Nguyên tắc:** Bảo vệ private key có ba lớp liên quan: **giữ bí mật vật liệu khóa**, **kiểm soát quyền thực hiện phép toán bằng khóa** và **quản trị vòng đời từ tạo đến hủy**. Không thể thay lớp này bằng lớp khác.

## 2. Private key được sử dụng vào việc gì?

Không nên phát biểu chung rằng “private key dùng để mã hóa”. Vai trò cụ thể phụ thuộc thuật toán và giao thức.

| Cơ chế | Vai trò của private key | Vai trò của public key | Ví dụ |
| --- | --- | --- | --- |
| **Chữ ký số** | Tạo chữ ký bằng RSA-PSS, ECDSA hoặc Ed25519 | Xác minh chữ ký | Ký phần mềm, hóa đơn, JWT |
| **Mã hóa khóa công khai** | Giải mã dữ liệu/khóa được mã hóa cho public key | Mã hóa cho người nhận | RSA-OAEP trong cơ chế phù hợp |
| **Thỏa thuận khóa** | Tham gia tính shared secret với public key đối tác | Được trao đổi và xác thực giữa các bên | ECDH, X25519 |
| **Xác thực bằng khóa công khai** | Chứng minh quyền kiểm soát private key theo giao thức | Kiểm chứng bằng public key/chứng thư | TLS, SSH, xác thực thiết bị |

Nên **tách cặp khóa theo mục đích**: khóa ký, khóa giải mã và khóa thỏa thuận khóa có yêu cầu quản lý khác nhau. Dùng chung một private key qua nhiều giao thức có thể tăng phạm vi sự cố hoặc vi phạm ràng buộc thuật toán, chứng thư và key usage.

### Những tài sản cần bảo vệ

1. **Key material:** giá trị bí mật thực tế của private key, trong HSM/KMS, file keystore, bộ nhớ hoặc thiết bị.
2. **Passphrase/password:** nếu lộ cùng file khóa đã mã hóa, đối thủ có thể giải mã file.
3. **Quyền gọi phép toán:** quyền `Sign`, `Decrypt`, `DeriveKey` có thể bị lạm dụng khi khóa không thể xuất.
4. **Danh tính quản trị:** token, policy, role và grant có quyền cấp phép hoặc thay trạng thái khóa.
5. **Bản sao và backup:** bản sao nằm ngoài kiểm soát có thể gây rò rỉ hoặc khiến hủy khóa không có hiệu lực như dự kiến.
6. **Metadata và audit:** key ID/version, owner, chứng thư, bằng chứng phê duyệt và nhật ký sự kiện.

## 3. Mô hình đe dọa đối với private key

Câu hỏi cần trả lời trước khi chọn nơi lưu khóa: **kẻ tấn công có thể lấy key material ở đâu, hoặc buộc hệ thống sử dụng khóa thay mình bằng cách nào?**

| Nguồn rủi ro | Ví dụ thực tế | Hệ quả |
| --- | --- | --- |
| **Repository / build artifact** | Commit `.pem`, `.p12`, nhúng khóa vào image container | Bản sao lan rộng trong lịch sử Git, registry và cache |
| **File system / backup** | Tài khoản không cần thiết vẫn đọc được file khóa | Đánh cắp private key |
| **Bộ nhớ tiến trình** | Heap dump, core dump, debugger, máy chủ bị chiếm | Rò rỉ khóa đã giải mã trong RAM |
| **CI/CD và secrets** | Pipeline in password ra log; job không tin cậy được quyền ký | Lộ bí mật hoặc lạm dụng thao tác ký |
| **IAM và KMS/HSM** | Admin tự cấp `Sign` hoặc `Decrypt`, role quá rộng | Dùng khóa trái phép dù không thể xuất |
| **Nhân sự/vận hành** | Tài khoản dùng chung, bàn giao thiếu thu hồi quyền | Không truy được người thao tác |
| **Giao thức và thư viện** | Dùng thuật toán sai, padding không phù hợp, lỗi side channel | Rò rỉ hoặc phá vỡ mục đích bảo vệ |
| **Thiết bị bị mất** | Laptop lưu private key SSH không bảo vệ | Mạo danh nếu bên xác thực còn tin public key |

### Lộ key material khác lạm dụng quyền như thế nào?

- **Key disclosure:** Đối thủ có một bản sao private key. Gỡ quyền truy cập vào file gốc **không thu hồi được bản sao đã bị lấy**; cần thay cặp khóa và xử lý niềm tin/dữ liệu liên quan.
- **Unauthorized key usage:** Đối thủ không có private key nhưng được gọi API `Sign`, `Decrypt` hay `DeriveKey` do chiếm được danh tính hoặc quyền. Cần cô lập quyền, điều tra các thao tác và đánh giá yêu cầu thay khóa.
- **Loss of availability:** Private key bị xóa nhầm hoặc không có cách khôi phục; hệ thống không thể giải mã dữ liệu hay tiếp tục ký/xác thực. Phải thiết kế khả năng phục hồi cho loại khóa cần lưu lâu dài.

Thuật ngữ **non-exportable** thường chỉ rằng một giao diện quản lý khóa không cho xuất vật liệu private key. Nó không đồng nghĩa không thể lạm dụng quyền ký hoặc hoàn toàn miễn nhiễm với lỗi vận hành, thiết bị và cấu hình.

## 4. Bảo vệ private key ngay từ khi tạo

### 4.1. Bộ sinh khóa và tham số tin cậy

Private key phải được sinh bằng **nguồn ngẫu nhiên mật mã (CSPRNG)** và thuật toán/nhóm tham số được công nhận. Không tự tạo private key từ timestamp, username, hash mật khẩu hay dùng bộ sinh số ngẫu nhiên phổ thông như `java.util.Random`.

| Mục đích | Lựa chọn phổ biến có thể phù hợp | Điều cần xác minh |
| --- | --- | --- |
| Ký số | RSA-PSS với khóa đủ mạnh; ECDSA P-256/P-384; Ed25519 khi được hỗ trợ | Giao thức, định dạng chữ ký, khả năng vận hành và tuân thủ |
| Giải mã khóa được vận chuyển | RSA-OAEP đúng tham số | Không dùng RSA “raw”; không mã hóa trực tiếp lượng dữ liệu lớn |
| Thỏa thuận khóa | ECDH với đường cong tiêu chuẩn, X25519 | Xác thực public key đối tác, xử lý shared secret/KDF |
| Chứng thư máy chủ | Thuật toán khóa công khai được TLS/PKI hỗ trợ | Quản lý chứng thư, gia hạn, trust chain, hostname |

Không tự hoán đổi khóa Ed25519 dùng ký với khóa X25519 dùng thỏa thuận chỉ vì chúng thuộc họ đường cong gần nhau. Thuật toán và key usage phải đúng thiết kế giao thức.

### 4.2. Tạo ở nơi sử dụng khóa khi có thể

Với khóa nhạy cảm, ưu tiên **sinh private key bên trong HSM, TPM, secure enclave hoặc dịch vụ KMS hỗ trợ thuật toán tương ứng**. Ứng dụng nhận **key ID/handle** để thực hiện các phép toán được phép mà không cần lấy key material.

Nếu yêu cầu nghiệp vụ buộc phải dùng software keystore, hãy tạo, lưu, nạp và sao lưu trong quy trình kiểm soát; hạn chế số bản sao, người có quyền và thời gian private key nằm dưới dạng rõ.

Chính sách **không được xuất khóa** nên được quyết định ngay từ lúc tạo. Một private key đã được sao chép qua nhiều máy không thể được coi là “chưa từng xuất” chỉ vì chuyển bản gốc vào HSM.

## 5. Bảo vệ private key khi lưu trữ (*at rest*)

### 5.1. Phân biệt định dạng khóa và mức độ an toàn

| Định dạng / nơi lưu | Nội dung | Lưu ý bảo vệ |
| --- | --- | --- |
| **PEM `BEGIN PRIVATE KEY`** | Thường là PKCS#8 private key dưới dạng Base64, **không được mã hóa bảo mật** | Base64 không phải encryption; không đưa vào repository/log |
| **PEM `BEGIN ENCRYPTED PRIVATE KEY`** | PKCS#8 đã mã hóa bằng passphrase theo thuật toán tương ứng | Kiểm tra KDF/PBE, chính sách password và quyền file |
| **PKCS#12 (`.p12`, `.pfx`)** | Container chứa private key/chứng thư và cơ chế bảo vệ phụ thuộc cấu hình/provider | Bảo vệ mật khẩu, file và thuật toán mã hóa phù hợp |
| **Java KeyStore (`JKS`)** | Container khóa theo định dạng truyền thống của Java | Thường cân nhắc PKCS#12 hoặc HSM/KMS cho thiết kế mới |
| **PKCS#11 token/HSM** | Tham chiếu private key trong thiết bị/mô-đun | Private key có thể không xuất được; dùng qua phép toán/handle |
| **Cloud KMS resource** | Định danh và metadata của khóa do dịch vụ quản lý | Cần xác minh hỗ trợ asymmetric key và permission thực tế |

Đuôi file `.pem` **không cho biết** khóa đã được mã hóa. Tương tự, có mật khẩu bảo vệ `.p12` không thay được việc kiểm soát máy chủ: tiến trình có quyền đọc file và biết password vẫn có thể đưa private key vào bộ nhớ.

### 5.2. Bảo vệ passphrase

Passphrase mở keystore nên được phân phối qua **secret manager** hoặc cơ chế cấp phát bí mật được phê duyệt, với danh tính riêng và audit. Tránh hard-code trong mã nguồn, lưu cùng file khóa, đưa lên ticket/chat, in ra CI logs hoặc ghi ngay trong tham số dòng lệnh dễ lộ ở shell history.

Nếu phải dùng passphrase do người nhập, cần đánh giá độ mạnh của passphrase và cơ chế **password-based key derivation** dùng để mã hóa file. Không tự biến mật khẩu thành private key bằng một phép hash đơn giản.

Các biện pháp bổ sung gồm: giới hạn quyền file, mã hóa ổ đĩa, cô lập tiến trình, bảo vệ backup, hạn chế quyền debug và thu hồi truy cập khi nhân sự thay đổi. Đây là các lớp **defense in depth**.

## 6. Bảo vệ private key khi truyền (*in transit*) và khi sử dụng (*in use*)

### 6.1. Hạn chế việc chuyển private key

Trong nhiều kiến trúc, **private key không cần được gửi qua mạng**. Public key hoặc chứng thư được phân phối; private key nằm ở nơi thực hiện phép toán. Nếu buộc phải di chuyển private key (nhập khóa, khôi phục được phép, chuyển nhà cung cấp), quy trình cần:

1. Nêu rõ lý do, owner phê duyệt, thời điểm, nguồn và đích.
2. Dùng cơ chế xuất/nhập được hỗ trợ, đường truyền mã hóa và kiểm tra toàn vẹn.
3. Bảo vệ vật liệu khóa bằng cơ chế bọc/mã hóa phù hợp; quản lý riêng key wrapping key hoặc quyền giải bọc.
4. Loại bỏ file trung gian và kiểm tra không lộ qua log, cache, email, chat hay backup ngoài ý muốn.
5. Ghi sự kiện và bằng chứng về người yêu cầu, phê duyệt, thực hiện và kết quả.

Chỉ dùng TLS cho kênh vận chuyển **không đủ** nếu sau đó private key bị để dạng rõ trên máy nhận hoặc được ghi vào log.

### 6.2. Khi private key nằm trong bộ nhớ

Với software keystore, ứng dụng có thể giải mã private key vào RAM và dùng JCA/JCE để ký hoặc giải mã. Cần phòng vệ trước heap dump, core dump, debug endpoint, swap, remote code execution và quyền host quá rộng.

Với HSM/KMS hỗ trợ, ứng dụng yêu cầu thao tác `Sign` hoặc `Decrypt` qua API và private key **không cần rời vùng bảo vệ**. Tuy nhiên, danh tính ứng dụng có quyền gọi API bị chiếm vẫn là một rủi ro thực. Cũng cần xem API có yêu cầu gửi plaintext, digest hay bản mã và bảo vệ những dữ liệu này.

Trong Java, **không thể bảo đảm mọi bản sao private key đã được xóa khỏi RAM** chỉ bằng việc bỏ tham chiếu hoặc xóa một mảng byte. Tránh `getEncoded()` và `String` chứa khóa, không in object key, giảm thời gian tồn tại của dữ liệu nhạy cảm, ưu tiên key handle không xuất được khi phù hợp.

## 7. Lựa chọn KMS, HSM, TPM hay secret manager

| Công cụ | Điểm mạnh | Giới hạn cần hiểu |
| --- | --- | --- |
| **Software keystore mã hóa** | Dễ tích hợp Java và vận hành ở quy mô nhỏ | Khóa thường được nạp vào RAM ứng dụng sau khi mở |
| **HSM** | Bảo vệ private key và thực hiện phép toán trong mô-đun, có thể non-exportable | Cần xác minh thuật toán, driver, HA/DR, PIN, audit và cost |
| **Cloud KMS** | API, IAM, rotation và logging tập trung | Hỗ trợ `Sign`, `Decrypt`, import/export, replication tùy nhà cung cấp |
| **TPM / secure enclave** | Bảo vệ khóa gắn thiết bị | Cơ chế sao lưu/di chuyển và API không giống KMS tập trung |
| **Secret manager** | Lưu và phân phối secrets có kiểm soát | Lưu file private key trong secret manager **không giống** ký trực tiếp trong HSM |

### Sơ đồ chữ ký với non-exportable private key

~~~mermaid
flowchart LR
    O[Key owner] -->|Phê duyệt chính sách và bên được dùng| P[Quyền sử dụng khóa]
    C[Key custodian] -->|Tạo và quản trị theo quy trình| H[KMS/HSM: private signing key]
    P --> H
    A[Ứng dụng có quyền Sign] -->|Yêu cầu ký dữ liệu/digest phù hợp| H
    H -->|Chữ ký| A
    A -->|Dữ liệu và chữ ký| R[Người nhận]
    U[Public key hoặc chứng thư] -->|Verify| R
    H --> L[Audit log: key ID, caller, thời điểm]
    V[Auditor] -->|Rà soát| L
~~~

Điểm cần bảo vệ không chỉ là việc khóa không xuất được, mà còn là **ai được quyền gọi phép ký**, có thể **ký loại dữ liệu gì**, và ai có thể **sửa policy** để cấp quyền cho chính mình.

### Phân công trách nhiệm

| Vai trò | Trách nhiệm | Hạn chế quan trọng |
| --- | --- | --- |
| **Key owner** | Phê duyệt mục đích, ứng dụng, cryptoperiod, rotation và rủi ro | Không tự động có private key hoặc quyền `Sign` |
| **Key custodian** | Tạo/cấu hình khóa, bảo vệ KMS/HSM, thực thi vòng đời, theo dõi log | Không tự cấp phép sử dụng trái phê duyệt |
| **Key user / ứng dụng** | Gọi phép toán được cấp trên đúng key ID | Không sửa policy, tạo/xóa key hoặc xuất vật liệu |
| **Security reviewer / auditor** | Kiểm tra phân tách nhiệm vụ, biến động quyền, lịch sử sử dụng | Quyền xem phù hợp, không cần private key |

**Separation of duties** giúp người quản trị không thể tự yêu cầu, phê duyệt, cấp quyền và sử dụng private key nhạy cảm trong cùng chuỗi hành động. Những việc có rủi ro lớn như nhập/xuất key material hoặc hủy khóa gốc có thể cần **dual control** theo chính sách.

## 8. Ví dụ Java: PKCS#12 và chữ ký số

Ví dụ này minh họa một **software keystore** được bảo vệ bằng password. Ta tạo khóa EC và chứng thư tự ký trên môi trường thử nghiệm, sau đó nạp private key để ký và dùng public key xác minh chữ ký.

**Bước 1 — tạo keystore thử nghiệm** bằng JDK 11+:

~~~bash
keytool -genkeypair \
  -alias demo-signing \
  -keyalg EC \
  -keysize 256 \
  -sigalg SHA256withECDSA \
  -storetype PKCS12 \
  -keystore demo-signing.p12 \
  -validity 30 \
  -dname "CN=Demo Signing, OU=Learning, O=Example, C=VN"
~~~

Không đưa password vào dòng lệnh; `keytool` sẽ yêu cầu nhập tương tác. Trên môi trường thực, phải bảo vệ file keystore và password, dùng khóa/chứng thư được cấp theo quy trình. **Chứng thư tự ký trong ví dụ chỉ dùng để học**, không chứng minh danh tính được một CA tin cậy xác thực.

**Bước 2 — nạp private key và thực hiện ký/xác minh**:

~~~java
import java.io.Console;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.cert.Certificate;
import java.util.Arrays;

public final class PrivateKeyProtectionDemo {
    public static void main(String[] args) throws Exception {
        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Use an interactive terminal for password entry");
        }

        char[] password = console.readPassword("PKCS#12 password: ");
        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("Password is required");
        }

        KeyStore store = KeyStore.getInstance("PKCS12");
        PrivateKey privateKey;
        PublicKey publicKey;

        try {
            try (InputStream in = Files.newInputStream(
                    Path.of("demo-signing.p12"))) {
                store.load(in, password);
            }

            Key key = store.getKey("demo-signing", password);
            if (!(key instanceof PrivateKey)) {
                throw new IllegalStateException("Missing private key entry");
            }
            privateKey = (PrivateKey) key;

            Certificate cert = store.getCertificate("demo-signing");
            if (cert == null) {
                throw new IllegalStateException("Missing certificate");
            }
            publicKey = cert.getPublicKey();
        } finally {
            Arrays.fill(password, '\0'); // xóa bản sao do app quản lý
        }

        byte[] message = "release:2026.11".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(privateKey);
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(publicKey);
        verifier.update(message);
        boolean valid = verifier.verify(signature);

        System.out.println("Signature valid: " + valid);
        // Không in private key, getEncoded() hoặc password.
    }
}
~~~

**Kết quả kỳ vọng:** in `Signature valid: true`. Điều này chứng minh chữ ký khớp với public key đã nạp; nó **không chứng minh chứng thư tự ký có độ tin cậy bên ngoài**.

Các điểm cần hiểu rõ:

- `Console.readPassword` hạn chế echo khi nhập, nhưng password và private key vẫn có thể được xử lý trong RAM; xóa `char[]` chỉ là **best effort**.
- `KeyStore.getKey` đưa một đối tượng private key vào tiến trình; file được mã hóa khi lưu không đồng nghĩa khóa không thể bị trích xuất trong quá trình dùng.
- Không ghi key hoặc password vào log, không bật debug in bí mật; kiểm soát quyền file `.p12` và nơi lưu backup.
- Chương trình **không tự kiểm tra độ tin cậy của chứng thư**. Ứng dụng sản xuất phải kiểm chứng trust chain/identity và key usage khi giao thức yêu cầu.
- Đối với hệ thống bảo mật cao, có thể thay software key bằng **provider PKCS#11/HSM** hoặc **KMS Sign API** được nhà cung cấp hỗ trợ, để ứng dụng sử dụng key handle mà không có bản sao private key dạng xuất được.

## 9. Quyền sử dụng private key phải được kiểm soát độc lập

Ngay cả khi key material nằm trong HSM, nếu một microservice được phép ký bất kỳ byte nào theo yêu cầu không kiểm tra, nó có thể trở thành **signing oracle**: kẻ tấn công gửi dữ liệu độc hại và nhận chữ ký hợp lệ.

### 9.1. Quyền tối thiểu

Một dịch vụ ký hóa đơn chỉ nên được quyền `Sign` trên đúng signing key, đúng thuật toán và trong phạm vi yêu cầu. Nó không cần `Decrypt`, sửa policy, tạo grant, xóa khóa hay sử dụng signing key của một hệ thống khác.

~~~text
# Mô hình quyền khái niệm, KHÔNG phải cú pháp policy KMS cụ thể.
principal: invoice-signing-service
resource: invoice-signing-key/production
allowedOperation: Sign
allowedAlgorithm: ECDSA_SHA_256

disallowedOperations:
  - ExportPrivateKey
  - DeleteKey
  - ChangeKeyPolicy
  - UseOtherSigningKeys
~~~

Các quyền/điều kiện thực tế phụ thuộc sản phẩm. Việc viết những tên action trên giấy **không tự ràng buộc API**; phải ánh xạ vào IAM, key policy, service account và cơ chế kiểm tra phù hợp.

### 9.2. Kiểm tra nghiệp vụ trước khi ký

Ngoài IAM, dịch vụ cần kiểm tra bản ghi đã được duyệt, loại nội dung hợp lệ, tenant, version, correlation ID và giới hạn rate. Với phát hành phần mềm, phải kiểm tra artifact/digest đến từ pipeline đã hoàn tất bước kiểm thử và phê duyệt. HSM không thể quyết định một nội dung có hợp pháp hay đã đủ bước phê duyệt.

### 9.3. Kiểm toán cả sử dụng lẫn quản trị

Nên ghi **key ID/version, caller, thao tác, thuật toán, thời điểm, kết quả, correlation ID** và quyết định phê duyệt liên quan. Khi cần truy nguyên chữ ký, có thể lưu định danh artifact/digest theo chính sách. **Không ghi private key, passphrase, plaintext nhạy cảm hay shared secret**.

Theo dõi các sự kiện quản trị như sửa IAM/grant, tắt logging, đổi alias, vô hiệu hóa và lên lịch hủy khóa. Audit log cần được bảo vệ khỏi sửa/xóa trái phép và có thời hạn lưu rõ ràng.

## 10. Vòng đời private key: tạo, cấp phát, sử dụng, xoay vòng và hủy

| Giai đoạn | Yêu cầu quản lý | Bằng chứng cần có |
| --- | --- | --- |
| **Đề xuất** | Xác định owner, custodian, mục đích, thuật toán, dữ liệu liên quan | Key inventory và phê duyệt |
| **Tạo** | Sinh bằng CSPRNG; chọn nơi bảo vệ, export policy, key usage | Log tạo và metadata |
| **Cấp phát** | Phân phối **public key/chứng thư**, chỉ cấp quyền dùng private key cho dịch vụ cần | Key policy/IAM và phê duyệt |
| **Lưu trữ** | Bảo vệ file/HSM/KMS, passphrase, bản sao lưu | Kiểm tra quyền và kiểm thử restore |
| **Sử dụng** | Giới hạn phép toán, danh tính, thuật toán và dữ liệu | Log `Sign`/`Decrypt`, cảnh báo |
| **Xoay vòng** | Tạo cặp khóa mới, cập nhật chứng thư/public key, chuyển ứng dụng | Kế hoạch và kết quả kiểm thử |
| **Thu hồi/ngừng dùng** | Chặn phép toán mới theo chính sách, thu hồi chứng thư/grant khi cần | Quyết định và log thay đổi |
| **Hủy** | Chỉ hủy khi hết phụ thuộc, retention và yêu cầu pháp lý | Phê duyệt hủy và bằng chứng xử lý backup |

### 10.1. Khóa ký và khóa giải mã có cách nghỉ sử dụng khác nhau

Với **private signing key**, sau khi chuyển sang `v2`, ngừng ký mới bằng `v1` theo chính sách. Người nhận có thể cần **public key, chứng thư cũ, dữ liệu xác minh và timestamp** để kiểm tra chữ ký lịch sử. Không xóa vật liệu public chỉ vì private key nghỉ sử dụng.

Với **private decryption key**, dữ liệu cũ đã mã hóa cho `v1` có thể vẫn cần private key `v1`. Trước khi hủy phải kiểm tra bản mã, archive, backup, kế hoạch **mã hóa lại hoặc chuyển khóa dữ liệu**. Hủy quá sớm có thể gây mất dữ liệu vĩnh viễn.

Với **private key thỏa thuận tạm thời**, cần giới hạn thời gian tồn tại và xóa bí mật phiên khi không còn cần. Việc lưu private key tạm vô hạn có thể phá vỡ kỳ vọng **forward secrecy**.

### 10.2. Phân biệt các hành động “thu hồi”

- **Thu hồi chứng thư (certificate revocation):** Bên dựa vào chứng thư có thể đánh giá trạng thái tin cậy theo PKI/CRL/OCSP và chính sách.
- **Gỡ quyền sử dụng:** Chặn một principal gọi `Sign` hoặc `Decrypt` qua KMS/HSM.
- **Vô hiệu hóa khóa:** Chặn thao tác theo ngữ nghĩa của sản phẩm KMS/HSM.
- **Hủy private key:** Tiêu hủy vật liệu bí mật, có thể không thể đảo ngược.

Thu hồi chứng thư **không tự hủy private key**; hủy private key **không tự thông báo** cho mọi bên đã tin public key/chứng thư. Cần phối hợp các bước.

### 10.3. Backup và khôi phục

Đối với khóa giải mã dữ liệu dài hạn, thường cần cơ chế phục hồi có kiểm soát. Đối với khóa HSM không xuất được, phương án HA/DR có thể dựa vào **replication/backup nội bộ được sản phẩm hỗ trợ**, thay vì xuất file khóa thô. Cần quy định ai được restore, có yêu cầu hai người (**dual control**) không, kiểm thử định kỳ, bảo vệ bản sao và xử lý backup khi hết retention.

Không tự “chia nhỏ private key thành nhiều đoạn text” rồi gọi là **split knowledge**. Nếu có yêu cầu chia bí mật, phải sử dụng cơ chế mật mã và quy trình được kiểm chứng.

## 11. Xử lý sự cố khi private key bị nghi lộ

Giả sử một job CI xuất hiện chữ ký trên một artifact chưa được phê duyệt. Có thể danh tính dịch vụ bị chiếm, hoặc private signing key đã bị sao chép.

Quy trình xử lý có thể gồm:

1. **Cô lập:** Tạm dừng quyền ký của danh tính liên quan, ngăn yêu cầu mới và bảo toàn log. Năng lực xử lý khẩn cấp cần được quy định trước.
2. **Phân loại:** Xác định chỉ quyền `Sign` bị lạm dụng hay **private key material đã lộ**; lập mốc thời gian và key version liên quan.
3. **Điều tra:** Tìm những chữ ký, bản mã, phiên và đối tác có thể bị ảnh hưởng; giữ chứng cứ cần thiết.
4. **Thay thế:** Tạo cặp khóa mới tại nguồn đáng tin, cấp lại quyền tối thiểu, cập nhật public key/trust store và thu hồi chứng thư nếu phù hợp.
5. **Khắc phục dữ liệu:** Nếu lộ private decryption key, đánh giá dữ liệu cũ, giải pháp rewrap DEK, mã hóa lại hoặc điều chỉnh kiến trúc.
6. **Khôi phục và kiểm chứng:** Thử ký/verify, truy cập dữ liệu cũ, quyền từ chối và audit trước khi mở lại hệ thống.
7. **Hậu kiểm:** Ghi kết quả, sửa nguyên nhân gốc, kiểm tra backup/bản sao, cập nhật inventory và quy trình.

**Không nên tự động xóa vĩnh viễn private decryption key ngay khi có cảnh báo**, vì có thể làm mất dữ liệu hợp lệ và ảnh hưởng điều tra. Ưu tiên cô lập quyền và bảo toàn chứng cứ, rồi quyết định vòng đời tiếp theo theo đánh giá rủi ro.

Nếu **private key đã bị đánh cắp**, chỉ đổi mật khẩu file keystore cũ không khôi phục được bí mật: đối thủ vẫn có bản sao vật liệu khóa. Cần thay cặp khóa và xử lý các bên còn tin public key cũ.

## 12. Tình huống thực tế: ký hóa đơn, mã hóa database và HTTPS

Một nền tảng hóa đơn có ba nhu cầu riêng:

| Nhu cầu | Loại khóa | Cách bảo vệ |
| --- | --- | --- |
| **Ký hóa đơn PDF** | Private signing key ECDSA/RSA-PSS và public verification key | KMS/HSM khi hỗ trợ, kiểm soát `Sign`, xác minh nội dung trước khi ký |
| **Mã hóa bản ghi trong database** | DEK đối xứng AES-GCM, được KEK trong KMS bọc | Quản lý IV/nonce theo DEK, key version, `Decrypt` và retention |
| **HTTPS/TLS** | Private authentication key gắn chứng thư, khóa (EC)DHE tạm thời và traffic key đối xứng | Quản lý TLS/PKI theo giao thức chuẩn, khóa phiên tạm không lưu vô thời hạn |

### Luồng ký hóa đơn

~~~mermaid
sequenceDiagram
    participant App as billing-service
    participant Approval as Policy/Approval
    participant HSM as KMS/HSM
    participant Client as Người nhận
    App->>Approval: Yêu cầu ký hóa đơn đã xác thực
    Approval-->>App: Phê duyệt
    App->>HSM: Sign(digest/nội dung theo API, key ID)
    Note over HSM: Private key nằm trong vùng bảo vệ
    HSM-->>App: Chữ ký và key metadata
    App->>Client: Hóa đơn + chữ ký + thông tin xác minh
    Client->>Client: Verify bằng public key/chứng thư tin cậy
~~~

Ứng dụng chỉ cần nhận chữ ký, nhưng **phải xác nhận nội dung và trạng thái phê duyệt trước khi gọi HSM**. Một signing API nhận mọi byte để ký mà không kiểm tra có thể bị lạm dụng.

Đối với lưu trữ, mô hình **envelope encryption** thường dùng DEK AES-GCM mã hóa dữ liệu, còn KEK được quản lý trong KMS để bọc DEK. Không nên dùng private signing key làm DEK hay thay thế trực tiếp KEK. Nếu dùng public-key encryption để vận chuyển một khóa dữ liệu cho đối tác, private decryption key của đối tác cần chính sách bảo vệ, khôi phục và vòng đời riêng.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đưa `.pem`/`.p12` và password vào Git | Lộ khóa qua lịch sử, cache và artifact | Thay khóa nếu đã lộ; xử lý bản sao, quyền và quy trình |
| Coi PEM/Base64 là mã hóa | Private key ở dạng rõ | Dùng mã hóa khóa thực hoặc HSM/KMS |
| Hard-code passphrase trong ứng dụng | Mật khẩu dễ bị lấy từ source hoặc log | Secret manager, phân quyền và audit |
| Cho nhiều service quyền `Sign` cùng khóa | Một service bị chiếm ảnh hưởng nhiều chức năng | Key riêng theo ứng dụng/mục đích và IAM tối thiểu |
| Chỉ bảo vệ key material, không kiểm tra payload ký | Signing oracle ký dữ liệu độc hại | Quy trình phê duyệt nội dung và giới hạn nghiệp vụ |
| Admin tự cấp quyền `Decrypt` cho mình | Bỏ qua phân tách trách nhiệm | Kiểm soát policy/grant và phê duyệt độc lập |
| Ghi `getEncoded()` hoặc private key object ra log | Lộ khóa và bản sao trong hệ quan sát | Không xuất khi không cần, kiểm tra logging/dump |
| Dùng một cặp khóa cho ký, giải mã và ECDH | Tăng phạm vi sự cố, lỗi giao thức/key usage | Tách khóa theo thuật toán và mục đích |
| Xoay signing key rồi xóa public key/chứng thư cũ | Không xác minh chữ ký lịch sử | Giữ thông tin xác minh theo retention |
| Hủy decryption key khi dữ liệu cũ còn phụ thuộc | Không giải mã được archive/backup | Kiểm kê phụ thuộc và kiểm thử restore |
| Thu hồi chứng thư nhưng vẫn để API ký hoạt động | Vẫn có thể lạm dụng phép toán hoặc các bên chưa cập nhật | Thu hồi quyền, thay khóa và thông báo tin cậy |

## 14. Checklist trước khi triển khai production

1. **Mục đích:** Đây là private key dùng `Sign`, `Decrypt` hay `Key Agreement`? Có tách khóa theo mục đích và môi trường không?
2. **Sinh khóa:** Có CSPRNG, thuật toán/độ dài phù hợp và quyết định nơi tạo khóa trước khi triển khai không?
3. **Lưu trữ:** Khóa nằm ở đâu: encrypted PKCS#8, PKCS#12, HSM, KMS hay thiết bị? Có chính sách export rõ ràng không?
4. **Passphrase/secret:** Được cấp phát qua cơ chế tin cậy? Có nguy cơ lộ qua shell, CI/CD, log, image, backup hay không?
5. **Trong lúc dùng:** Có hạn chế quyền host/debug/dump và tránh đưa private key ra bộ nhớ ứng dụng khi không cần không?
6. **Phân quyền:** Chỉ đúng principal được quyền gọi thao tác hợp lệ? Ai có thể sửa policy, tạo grant và tự cấp quyền?
7. **Kiểm soát nghiệp vụ:** Nội dung ký đã được phê duyệt và ràng buộc với đúng hệ thống/tenant/phiên bản chưa?
8. **Vòng đời:** Owner, custodian, key state, cryptoperiod, rotation, thu hồi và hủy có được quản lý qua inventory không?
9. **Khả năng phục hồi:** Khóa giải mã cũ và backup còn cần để đọc dữ liệu không? Cơ chế HSM/KMS HA/DR đã được thử chưa?
10. **Chữ ký lịch sử:** Public key/chứng thư cũ và bằng chứng xác minh được giữ đủ lâu theo chính sách không?
11. **Giám sát:** Log có đầy đủ caller, key ID/version, thao tác, thời gian, phê duyệt, cảnh báo mà không chứa private key/password không?
12. **Ứng cứu:** Có runbook để cô lập nhanh, thay khóa, xử lý trust store và đánh giá dữ liệu khi nghi lộ khóa không?

### Ghi nhớ

**Private key protection** không chỉ là “đặt password cho file khóa”. Hệ thống an toàn cần tạo private key bằng nguồn đáng tin, ưu tiên **key không xuất được trong KMS/HSM** khi phù hợp, kiểm soát **quyền sử dụng phép toán**, bảo vệ file/bộ nhớ/bản sao và quản lý **xoay vòng, thu hồi, phục hồi, hủy, kiểm toán**. Khóa ký tập trung bảo vệ khả năng tạo chữ ký; khóa giải mã phải cân nhắc khả năng đọc dữ liệu cũ; khóa thỏa thuận cần xét shared secret và forward secrecy. Kết hợp đúng các lớp này với mật mã đối xứng, chữ ký số và envelope encryption sẽ tạo nên vòng đời khóa có thể vận hành và kiểm chứng.
