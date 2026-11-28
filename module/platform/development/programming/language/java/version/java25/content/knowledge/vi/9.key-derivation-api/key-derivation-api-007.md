# Tách khóa cho nhiều mục đích bằng thông tin ngữ cảnh phù hợp

> **Chương:** API dẫn xuất khóa  
> **Phiên bản:** Java 25 — Key Derivation Function API (JEP 510) đã là API chính thức, không cần bật preview.  
> **Trọng tâm:** Dùng HKDF trong `javax.crypto.KDF` để dẫn xuất các khóa độc lập từ cùng một nguồn key material, phân biệt mục đích bằng `salt` và `info` theo RFC 5869.

## 1. Bài toán: một bí mật gốc, nhiều khóa chuyên biệt

Một dịch vụ thanh toán có thể cần nhiều khóa cho các mục đích khác nhau:

- Khóa mã hóa dữ liệu bằng AES.
- Khóa xác thực webhook bằng HMAC.
- Khóa cho một phiên bản giao thức hoặc một chiều giao tiếp cụ thể.
- Khóa riêng cho từng tenant hoặc từng phiên, tùy thiết kế bảo mật.

Một cách làm rủi ro là dùng cùng một khóa gốc trực tiếp cho mọi thuật toán. Khi một giao thức hoặc một thành phần bị lộ, việc tái sử dụng khóa có thể làm tăng phạm vi ảnh hưởng. Một cách khác cũng không phù hợp là tự nối chuỗi bí mật với tên mục đích rồi băm bằng một hàm hash tùy ý:

~~~java
byte[] key = MessageDigest.getInstance("SHA-256")
        .digest((masterSecret + "encryption").getBytes(UTF_8));
~~~

Đoạn mã trên không phải một thiết kế KDF được đặc tả; nó tự tạo quy tắc ghép dữ liệu, không mô tả rõ nguồn entropy, salt, giới hạn đầu ra hoặc domain separation.

**HKDF (HMAC-based Extract-and-Expand Key Derivation Function)** giải quyết đúng bài toán này. Từ input keying material (IKM), HKDF tạo một pseudorandom key (PRK), sau đó mở rộng thành các đầu ra có độ dài và ngữ cảnh được xác định. Trường `info` liên kết đầu ra với mục đích cụ thể, giúp tạo các khóa khác nhau cho các giao thức/thuật toán khác nhau dù dùng cùng IKM.

Trong Java 25, API chuẩn cho KDF là `javax.crypto.KDF` và tham số HKDF là `javax.crypto.spec.HKDFParameterSpec`. API được hoàn thiện trong JDK 25 theo JEP 510; ví dụ của bài không sử dụng API preview.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `KeyGenerator`, `KeyAgreement`, `KDF` và `SecretKeyFactory`.
2. Giải thích hai giai đoạn Extract và Expand của HKDF.
3. Dùng `KDF.getInstance("HKDF-SHA256")` cùng `HKDFParameterSpec`.
4. Tách khóa AES và HMAC bằng các giá trị `info` khác nhau.
5. Chọn salt, info, độ dài đầu ra và thuật toán phù hợp.
6. Nhận biết HKDF không phải password hashing KDF và không tự tạo entropy.
7. Xử lý key material không thể export từ HSM/crypto provider bằng overload nhận `SecretKey`.
8. Kiểm tra provider, lỗi thuật toán và vòng đời khóa trong ứng dụng.

## 2. KDF nằm ở đâu trong hệ sinh thái Java Cryptography Architecture?

Java Cryptography Architecture (JCA/JCE) có nhiều engine class với trách nhiệm riêng. Chọn đúng engine giúp tránh dùng một API cho sai bài toán.

| API | Mục đích | Ví dụ |
|---|---|---|
| `KeyGenerator` | Sinh khóa mới theo thuật toán và nguồn ngẫu nhiên của provider | Sinh khóa AES độc lập |
| `KeyAgreement` | Tạo shared secret từ trao đổi khóa | ECDH/X25519 |
| `KDF` | Dẫn xuất thêm một hay nhiều khóa từ IKM và tham số ngữ cảnh | HKDF-SHA256 |
| `SecretKeyFactory` | Chuyển đổi/khởi tạo khóa từ key specification | PBKDF2, chuyển đổi `PBEKeySpec` |
| `Cipher` | Mã hóa/giải mã dữ liệu | AES/GCM/NoPadding |
| `Mac` | Tạo/kiểm tra mã xác thực thông điệp | HmacSHA256 |

Một luồng điển hình:

~~~mermaid
flowchart LR
    A["Nguồn bí mật\nSecureRandom / ECDH / KMS"] --> B["IKM"]
    B --> C["HKDF Extract\nIKM + salt"]
    C --> D["PRK"]
    D --> E["HKDF Expand\ninfo = encryption"]
    D --> F["HKDF Expand\ninfo = webhook"]
    E --> G["AES SecretKey"]
    F --> H["HMAC SecretKey"]
    G --> I["Cipher"]
    H --> J["Mac"]
~~~

Ví dụ: hai bên thực hiện ECDH để có cùng shared secret; sau đó dùng HKDF để tách khóa mã hóa và khóa xác thực theo nhãn giao thức. `KeyAgreement` tạo bí mật chung; `KDF` biến bí mật chung đó thành các khóa chuyên biệt. HKDF không thay thế ECDH và không thực hiện trao đổi khóa.

### KDF không phải thuật toán mã hóa

KDF không mã hóa plaintext, không tạo nonce, không xác thực dữ liệu và không lưu khóa. Nó tạo key material có cấu trúc từ một nguồn bí mật. Sau khi dẫn xuất, dùng khóa với API đúng mục đích như `Cipher`, `Mac` hoặc giao thức mật mã đã được thiết kế.

## 3. Trạng thái API trong Java 25 và các thuật toán có sẵn

Key Derivation Function API được preview trong Java 24 theo JEP 478 và được hoàn thiện trong Java 25 theo **JEP 510**. Các kiểu công khai chính:

- `javax.crypto.KDF`
- `javax.crypto.KDFParameters`
- `javax.crypto.spec.HKDFParameterSpec`
- `javax.crypto.KDFSpi` cho nhà cung cấp triển khai dịch vụ KDF.

Các lớp/kiểu Java SE 25 ghi `Since: 25`; không cần `--enable-preview` khi compile hoặc run bằng JDK 25. Đây là điểm cần phân biệt với mã mẫu cũ từ JDK 24, vốn yêu cầu preview flags.

API này vẫn được duy trì ở các JDK mới hơn: tài liệu Java SE 27 tiếp tục liệt kê `javax.crypto.KDF` với mốc `Since: 25` và các tên HKDF tương ứng. Vì vậy ví dụ Java 25 trong bài vẫn là API chuẩn trên các JDK mới hơn có provider hỗ trợ, không phải một nhánh preview đã bị bỏ.

Java Security Standard Algorithm Names của JDK 25 định nghĩa các tên KDF:

| Tên thuật toán | Cơ chế | Đầu ra hash |
|---|---|---|
| `HKDF-SHA256` | HKDF theo RFC 5869, HMAC-SHA-256 | 32 byte |
| `HKDF-SHA384` | HKDF theo RFC 5869, HMAC-SHA-384 | 48 byte |
| `HKDF-SHA512` | HKDF theo RFC 5869, HMAC-SHA-512 | 64 byte |

Các tên trên là tên chuẩn khi gọi `KDF.getInstance(...)`. Provider cụ thể có thể có giới hạn hoặc chính sách riêng; nếu không có provider hỗ trợ, lời gọi sẽ ném `NoSuchAlgorithmException`.

**Không lấy danh sách thuật toán từ một bản preview JDK 24 để suy luận API Java 25.** Hãy đọc Java SE 25 API và tài liệu provider của JDK đang triển khai.

### Module system

`javax.crypto.KDF` nằm trong module nền tảng `java.base`. Một ứng dụng Java thông thường không cần thêm `requires` cho `java.base`; named module cũng đọc module này ngầm định. Các lớp `Cipher`, `Mac`, `SecretKey` và `HKDFParameterSpec` cũng thuộc các package trong `java.base`.

## 4. HKDF Extract-and-Expand hoạt động thế nào?

HKDF theo RFC 5869 có hai giai đoạn logic:

~~~mermaid
flowchart TD
    A["IKM\nInput Keying Material"] --> C["Extract"]
    B["salt\nkhông cần bí mật"] --> C
    C --> D["PRK\nPseudorandom Key"]
    D --> E["Expand"]
    F["info\nngữ cảnh / mục đích"] --> E
    G["L\nđộ dài đầu ra"] --> E
    E --> H["OKM\nOutput Keying Material"]
~~~

### 4.1. Extract

`HKDF-Extract(salt, IKM) → PRK`

Extract sử dụng HMAC để đưa IKM về một khóa giả ngẫu nhiên có độ dài bằng output hash. Nó hữu ích khi IKM có entropy nhưng phân bố chưa đồng đều hoặc đến từ nguồn như shared secret của một key agreement protocol.

- **IKM:** key material đầu vào, thường là bí mật có entropy cao.
- **salt:** giá trị không cần bí mật, thường là chuỗi ngẫu nhiên. RFC 5869 cho phép không có salt; khi không có, HKDF dùng chuỗi byte 0 có độ dài bằng HashLen.
- **PRK:** pseudorandom key làm đầu vào cho bước Expand.

Salt không phải password và không cần giữ kín như IKM. Khi hai bên cần tái tạo cùng khóa, cả hai phải dùng cùng IKM, salt, thuật toán và info. Salt có thể được lưu hoặc truyền kèm metadata của ciphertext/protocol.

### 4.2. Expand

`HKDF-Expand(PRK, info, L) → OKM`

Expand tạo output keying material có độ dài `L` từ PRK và `info`.

- **info:** dữ liệu ngữ cảnh và mục đích ứng dụng; có thể chứa tên giao thức, phiên bản, thuật toán, hướng truyền hoặc loại khóa.
- **L:** số byte đầu ra mong muốn.
- **OKM:** output keying material; có thể được chuyển thành `SecretKey` cho thuật toán đích.

Giới hạn theo RFC 5869:

\[
L \leq 255 \times \text{HashLen}
\]

Ví dụ với HKDF-SHA256, giới hạn lý thuyết là \(255 \times 32 = 8160\) byte. Đây là giới hạn giao thức, không phải gợi ý tạo khóa dài hàng kilobyte. Chọn đúng độ dài mà thuật toán đích yêu cầu: AES-128 cần 16 byte, AES-256 cần 32 byte; HMAC-SHA256 thường dùng khóa ngẫu nhiên đủ mạnh, ví dụ 32 byte.

### 4.3. Extract-and-Expand kết hợp

Trong ứng dụng phổ biến, có thể xây dựng một spec thực hiện cả hai bước:

~~~java
AlgorithmParameterSpec spec =
        HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, 32);
~~~

`thenExpand(info, 32)` tạo tham số cho chuỗi Extract-then-Expand. Sau đó truyền spec vào `deriveKey` hoặc `deriveData`.

## 5. Vì sao info tạo được key separation?

Giả sử cùng một IKM và salt được dùng cho hai mục đích. Nếu cả hai lần Expand dùng cùng info và cùng độ dài, HKDF tạo cùng output. Để tách khóa, mỗi mục đích phải có nhãn ngữ cảnh khác nhau:

~~~text
IKM + salt
   ├─ info = "payments/v1/encryption/aes-256-gcm"
   │     └─ K_enc
   └─ info = "payments/v1/webhook/hmac-sha256"
         └─ K_webhook
~~~

`info` không cần bí mật. Nó dùng để ràng buộc đầu ra với giao thức/mục đích, không phải để tăng entropy. Một nhãn tốt có thể chứa:

| Thành phần | Ví dụ | Vì sao cần |
|---|---|---|
| Namespace ứng dụng | `com.example.payments` | Tránh trùng với hệ thống khác |
| Phiên bản giao thức | `v1` | Tách key giữa các phiên bản |
| Mục đích | `encryption`, `webhook-auth` | Không dùng cùng key cho hai nhiệm vụ |
| Thuật toán | `aes-256-gcm`, `hmac-sha256` | Gắn key với thuật toán dự kiến |
| Hướng giao tiếp | `client-to-server` | Tách khóa hai chiều nếu protocol yêu cầu |

Khi info có nhiều trường, hãy mã hóa chúng bằng một định dạng rõ ràng, có ranh giới trường (ví dụ length-prefix, CBOR hoặc encoding chuẩn của protocol). Tránh nối chuỗi không phân tách như `"ab" + "c"` và `"a" + "bc"`, vì hai bộ trường có thể tạo cùng byte sequence.

**Không dùng dữ liệu tùy ý từ người dùng làm info mà không có quy tắc canonicalization.** Cùng một ý nghĩa nhưng cách mã hóa khác nhau có thể khiến hai bên dẫn xuất hai khóa khác nhau.

## 6. Ví dụ 1 — Dẫn xuất hai khóa từ cùng IKM

Ví dụ sau dùng một IKM ngẫu nhiên đủ dài và salt ngẫu nhiên. Cùng một HKDF-SHA256 tách hai khóa với hai nhãn mục đích riêng:

- `AES`, 32 byte cho AES-256.
- `HmacSHA256`, 32 byte cho HMAC-SHA256.

Tạo file `SeparateKeysDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

public class SeparateKeysDemo {

    private static final SecureRandom RANDOM = new SecureRandom();

    private static SecretKey derive(
            KDF kdf,
            byte[] ikm,
            byte[] salt,
            String purpose,
            String targetAlgorithm,
            int length) throws GeneralSecurityException {

        byte[] info = purpose.getBytes(StandardCharsets.UTF_8);

        var spec = HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, length);

        return kdf.deriveKey(targetAlgorithm, spec);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        // IKM phải đến từ nguồn bí mật có entropy cao.
        byte[] ikm = new byte[32];
        RANDOM.nextBytes(ikm);

        // Salt không cần bí mật; lưu lại nếu cần dẫn xuất lại cùng key.
        byte[] salt = new byte[32];
        RANDOM.nextBytes(salt);

        KDF hkdf = KDF.getInstance("HKDF-SHA256");

        SecretKey encryptionKey = derive(
                hkdf,
                ikm,
                salt,
                "com.example.payments/v1/encryption/aes-256-gcm",
                "AES",
                32);

        SecretKey webhookKey = derive(
                hkdf,
                ikm,
                salt,
                "com.example.payments/v1/webhook-auth/hmac-sha256",
                "HmacSHA256",
                32);

        // Chỉ in metadata, không in key bytes.
        System.out.println("Encryption key algorithm: "
                + encryptionKey.getAlgorithm());
        System.out.println("Webhook key algorithm: "
                + webhookKey.getAlgorithm());

        // Trong ứng dụng thật, quản lý và xóa bản sao IKM theo chính sách.
        java.util.Arrays.fill(ikm, (byte) 0);
    }
}
~~~

Biên dịch và chạy bằng JDK 25:

~~~bash
javac SeparateKeysDemo.java
java SeparateKeysDemo
~~~

Kết quả:

~~~text
Encryption key algorithm: AES
Webhook key algorithm: HmacSHA256
~~~

Mỗi lần chạy tạo IKM và salt mới nên các khóa cũng thay đổi. Trong ứng dụng phân tán, hai bên cần nhận cùng key material và cùng salt/info theo giao thức đã thống nhất; không tự sinh salt riêng biệt ở hai đầu nếu mục tiêu là tái tạo cùng key.

**Ghi chú:** `KDF` không được đảm bảo thread-safe. Ví dụ gọi tuần tự trên một instance. Nếu dẫn xuất đồng thời từ nhiều thread, tạo instance riêng cho từng tác vụ hoặc đồng bộ hóa theo tài liệu API/provider; không chia sẻ một `KDF` instance giữa nhiều thread mà không kiểm soát.

## 7. Ví dụ 2 — Dùng khóa dẫn xuất cho AES-GCM và HMAC

KDF chỉ tạo khóa. Sau khi có `SecretKey`, dùng API đích để thực hiện thao tác mật mã.

### 7.1. AES-GCM

~~~java
byte[] nonce = new byte[12];
new SecureRandom().nextBytes(nonce);

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(
        Cipher.ENCRYPT_MODE,
        encryptionKey,
        new GCMParameterSpec(128, nonce));

byte[] plaintext = "invoice-2026-001"
        .getBytes(StandardCharsets.UTF_8);

byte[] ciphertext = cipher.doFinal(plaintext);
~~~

Khi giải mã, cần lưu/truyền nonce cùng ciphertext và khởi tạo cipher ở chế độ `DECRYPT_MODE` với cùng key và nonce. AES-GCM cung cấp cả mã hóa và xác thực; không cần tự thêm HMAC lên cùng dữ liệu chỉ để "có thêm bảo mật".

**Nonce GCM phải duy nhất với mỗi lần mã hóa dưới cùng một khóa.** Ví dụ dùng random 96-bit nonce phù hợp minh họa một thao tác đơn lẻ; ứng dụng có lượng dữ liệu lớn cần chiến lược bảo đảm không tái sử dụng nonce (ví dụ bộ đếm/sequence được quản lý đúng cách theo key).

### 7.2. HMAC cho một mục đích riêng

Khóa `webhookKey` có thể được dùng để tạo MAC cho payload webhook:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(webhookKey);

byte[] canonicalPayload =
        "{\"event\":\"invoice.paid\",\"id\":\"evt-001\"}"
                .getBytes(StandardCharsets.UTF_8);

byte[] tag = mac.doFinal(canonicalPayload);
~~~

Bên nhận dùng cùng key và cùng cách canonicalize payload để tính lại MAC, rồi so sánh tag bằng hàm so sánh constant-time thích hợp như `MessageDigest.isEqual(...)`. Không so sánh MAC bằng `String.equals` hoặc so sánh byte array theo vòng lặp dừng sớm.

Hai khóa được tách bởi `info` khác nhau. Không dùng `encryptionKey` làm HMAC key hoặc `webhookKey` làm AES key chỉ vì cả hai đều là `SecretKey`.

## 8. Chọn salt và quản lý metadata

Salt không phải secret, nhưng vẫn là một phần đầu vào của phép dẫn xuất. Nếu mất salt, bên nhận không thể tạo lại cùng key từ IKM và info.

Một bản ghi mã hóa có thể lưu metadata như:

~~~json
{
  "kdf": "HKDF-SHA256",
  "keyVersion": "master-2026-03",
  "salt": "<base64-salt>",
  "purpose": "com.example.payments/v1/encryption/aes-256-gcm",
  "cipher": "AES/GCM/NoPadding",
  "nonce": "<base64-nonce>",
  "ciphertext": "<base64-ciphertext>"
}
~~~

Đây là cấu trúc minh họa. Không lưu IKM, PRK hoặc key dẫn xuất vào metadata công khai.

### Nguyên tắc chọn salt

- Ưu tiên salt ngẫu nhiên có độ dài phù hợp với hash output (ví dụ 32 byte cho HKDF-SHA256).
- Salt không cần giữ bí mật; có thể lưu cùng ciphertext hoặc metadata.
- Khi các bên phải tái tạo cùng khóa, salt cần được chia sẻ và xác thực theo protocol.
- Salt không thay thế IKM; một salt ngẫu nhiên không thể biến một nguồn bí mật yếu thành nguồn có entropy cao.
- Không dùng một giá trị salt khác nhau ở hai bên nếu cần cùng đầu ra.
- Đừng dùng salt để mã hóa tên người dùng hoặc đưa dữ liệu nhạy cảm vào metadata.

### Key version và rotation

Đưa phiên bản key/protocol vào `info` hoặc metadata đã được xác thực để xác định chính xác cách dẫn xuất. Khi xoay master key, cần lưu thông tin key version để giải mã dữ liệu cũ bằng đúng key material và tham số cũ; dữ liệu mới dùng version mới theo chính sách rotation.

HKDF không tự quản lý key rotation, lưu trữ khóa gốc hay quyền truy cập. Hãy lưu IKM/master key trong KMS/HSM/secret manager phù hợp và chỉ lấy quyền sử dụng theo nguyên tắc tối thiểu.

## 9. Extract riêng và Expand riêng

Trong đa số trường hợp, dùng `thenExpand(...)` để thực hiện Extract-and-Expand trong một spec. Tuy nhiên API còn hỗ trợ từng pha riêng.

### 9.1. Chỉ Extract

~~~java
var extractSpec = HKDFParameterSpec.ofExtract()
        .addIKM(ikm)
        .addSalt(salt)
        .extractOnly();

SecretKey prk = kdf.deriveKey("HmacSHA256", extractSpec);
~~~

`extractOnly()` tạo tham số chỉ thực hiện Extract. PRK là key trung gian; không dùng PRK trực tiếp cho nhiều mục đích khác nhau nếu protocol yêu cầu Expand với `info` riêng.

### 9.2. Chỉ Expand từ PRK đã có

~~~java
byte[] info = "com.example.service/v1/aes-256-gcm"
        .getBytes(StandardCharsets.UTF_8);

var expandSpec = HKDFParameterSpec.expandOnly(prk, info, 32);
SecretKey encryptionKey = kdf.deriveKey("AES", expandSpec);
~~~

Chỉ dùng Expand-only khi bạn đã có PRK hợp lệ theo protocol. Không dùng một giá trị tùy ý, password hoặc chuỗi text làm PRK chỉ vì nó có đủ byte.

### 9.3. Vì sao phải giữ ranh giới giữa PRK và output key?

PRK là đầu vào cho bước Expand; output key được ràng buộc với `info` và độ dài cụ thể. Một ứng dụng thường nên lưu/giữ IKM trong hệ thống quản lý bí mật và dẫn xuất output khi cần, thay vì xuất PRK ra nhiều nơi.

Nếu API/provider trả về một `SecretKey` không thể export, hãy tiếp tục dùng object đó qua API mật mã tương ứng. Không giả định `getEncoded()` luôn trả byte array.

## 10. HKDF không phải password hashing KDF

Đây là phân biệt an toàn quan trọng nhất của bài.

HKDF được thiết kế để xử lý IKM có entropy cao hoặc nguồn key material từ giao thức mật mã. Extract có thể tập trung entropy sẵn có; **nó không tạo thêm entropy** và không làm chậm quá trình thử đoán password.

| Đầu vào | Dùng HKDF trực tiếp? | Hướng phù hợp |
|---|---|---|
| Shared secret từ ECDH/X25519 | Phù hợp sau khi protocol xác thực/kiểm tra cần thiết | HKDF-Extract-Expand |
| Master key ngẫu nhiên do KMS tạo | Phù hợp | HKDF với salt/info theo mục đích |
| Khóa ngẫu nhiên sinh bằng SecureRandom | Có thể phù hợp | HKDF khi cần tách nhiều khóa |
| Password do người dùng chọn | **Không dùng HKDF như password KDF** | Password KDF có salt và chi phí tính toán/memory phù hợp |
| Chuỗi API key entropy thấp hoặc token dễ đoán | Không nên coi HKDF là cách tăng entropy | Thiết kế lại nguồn bí mật hoặc dùng cơ chế lưu/verify credential phù hợp |

HKDF không chống brute-force password bằng cách tăng chi phí tính toán. Với password, dùng password-based KDF như Argon2id (qua thư viện phù hợp) hoặc PBKDF2 với tham số được chọn theo tiêu chuẩn/chính sách triển khai. Trong Java, PBKDF2 được truy cập qua `SecretKeyFactory` với thuật toán phù hợp, không phải gọi `KDF.getInstance("PBKDF2")`.

Ví dụ tên engine API khác nhau:

~~~java
import javax.crypto.SecretKeyFactory;

// HKDF: dành cho key material có entropy cao.
KDF hkdf = KDF.getInstance("HKDF-SHA256");

// PBKDF2: API password-based trong JCA.
SecretKeyFactory pbkdf2 =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
~~~

Không thay thế các tham số password KDF bằng `salt` của HKDF; hãy theo hướng dẫn chuyên biệt cho password storage/key derivation.

## 11. Dùng key material không thể export từ HSM/provider

Một lợi ích của API Java 25 là `HKDFParameterSpec.Builder` hỗ trợ `addIKM(SecretKey)` và `addSalt(SecretKey)`, ngoài overload byte array. Có thể ghép nhiều phần IKM, kể cả thành phần nằm trong thiết bị mật mã và không thể export ra ứng dụng.

~~~java
var spec = HKDFParameterSpec.ofExtract()
        .addIKM(labelBytes)
        .addIKM(nonExtractableSecretKey)
        .addSalt(saltKey)
        .thenExpand(info, 32);

SecretKey derived = kdf.deriveKey("AES", spec);
~~~

Đoạn mã trên chỉ hoạt động nếu provider KDF hỗ trợ loại key material và các tham số đó. Không phải mọi provider hoặc HSM đều hỗ trợ cùng cách phối hợp. Cần kiểm tra:

1. Provider nào cung cấp KDF?
2. Provider có thể sử dụng trực tiếp key handle/non-extractable secret không?
3. Thuật toán HKDF-SHA256/384/512 và loại key có được hỗ trợ?
4. HSM có chính sách cho phép dẫn xuất key theo đúng mục đích không?
5. Key dẫn xuất có tiếp tục ở dạng non-extractable và nằm trong phạm vi bảo vệ mong muốn không?

Tài liệu API mô tả cơ chế **delayed provider selection**: nếu không chỉ định provider, provider được chọn khi thực hiện `deriveKey` hoặc `deriveData`, để xét cả key material thực tế. Nếu gọi `getProviderName()` hoặc `getParameters()` quá sớm, provider có thể được chọn trước khi hệ thống biết key material mà bạn sẽ truyền; với HSM, hãy hiểu rõ hành vi này trước khi khóa provider.

## 12. An toàn khi dùng KDF object trong ứng dụng đa luồng

Tài liệu Java SE 25 ghi rõ các method của `KDF` không được bảo đảm thread-safe. Vì vậy:

- Không giữ một instance `KDF` trong singleton rồi gọi đồng thời từ nhiều request nếu chưa đồng bộ.
- Có thể tạo instance riêng cho mỗi tác vụ/operation hoặc bảo vệ truy cập bằng synchronization nếu phù hợp.
- `HKDFParameterSpec.Builder` cũng không thread-safe; tạo builder riêng cho mỗi lần dẫn xuất.
- Spec được build là immutable; nhưng vẫn cần quản lý vòng đời IKM, salt và các byte array của ứng dụng.
- Không log IKM, PRK, derived key, secret bytes hoặc dữ liệu nhạy cảm trong `info`.

Ví dụ helper ở mục 6 dùng builder mới cho mỗi lần dẫn xuất và gọi tuần tự trên một KDF instance. Nếu chuyển helper sang xử lý đồng thời, thay đổi cách quản lý KDF instance.

### Không export khóa nếu không cần

Ưu tiên:

~~~java
SecretKey key = kdf.deriveKey("AES", spec);
cipher.init(Cipher.ENCRYPT_MODE, key, gcmSpec);
~~~

Hạn chế:

~~~java
byte[] rawKey = key.getEncoded();
~~~

`getEncoded()` có thể trả `null` nếu key không exportable. Ngay cả khi có byte array, việc sao chép secret vào nhiều object làm khó kiểm soát vòng đời bộ nhớ. Dùng `deriveKey` để giữ kết quả trong dạng `SecretKey` khi API đích chấp nhận nó.

## 13. Kiểm tra tính tách biệt và tái lập của khóa

Cùng một IKM, salt, algorithm, info và length phải tạo cùng kết quả theo đặc tả HKDF. Đổi info sang nhãn mục đích khác phải tạo output khác với xác suất va chạm không đáng kể.

Trong test dùng software provider, có thể kiểm tra raw output bằng `deriveData`. Không dùng cách export raw key này làm yêu cầu cho production/HSM.

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.KDF;
import javax.crypto.spec.HKDFParameterSpec;
import org.junit.jupiter.api.Test;

class HkdfSeparationTest {

    private byte[] derive(
            byte[] ikm,
            byte[] salt,
            String info) throws GeneralSecurityException {

        var spec = HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info.getBytes(StandardCharsets.UTF_8), 32);

        return KDF.getInstance("HKDF-SHA256").deriveData(spec);
    }

    @Test
    void sameInputsReproduceSameOutputAndPurposeSeparatesKeys()
            throws GeneralSecurityException {

        byte[] ikm = new byte[32];
        byte[] salt = new byte[32];

        // Dữ liệu cố định chỉ phục vụ test; production cần IKM mạnh.
        java.util.Arrays.fill(ikm, (byte) 0x41);
        java.util.Arrays.fill(salt, (byte) 0x25);

        byte[] encryption1 = derive(
                ikm, salt, "demo/v1/encryption/aes-256-gcm");
        byte[] encryption2 = derive(
                ikm, salt, "demo/v1/encryption/aes-256-gcm");
        byte[] webhook = derive(
                ikm, salt, "demo/v1/webhook/hmac-sha256");

        assertTrue(MessageDigest.isEqual(encryption1, encryption2));
        assertFalse(MessageDigest.isEqual(encryption1, webhook));

        java.util.Arrays.fill(encryption1, (byte) 0);
        java.util.Arrays.fill(encryption2, (byte) 0);
        java.util.Arrays.fill(webhook, (byte) 0);
        java.util.Arrays.fill(ikm, (byte) 0);
        java.util.Arrays.fill(salt, (byte) 0);
    }
}
~~~

Test minh họa tính xác định và phân tách mục đích. Nó **không chứng minh** thiết kế giao thức đã an toàn, không kiểm tra chất lượng entropy của IKM và không thay cho review mật mã. Việc xóa byte array bằng `Arrays.fill` là best effort; JVM/provider có thể giữ bản sao nội bộ.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách kiểm tra/hướng xử lý |
|---|---|---|
| `NoSuchAlgorithmException: HKDF-SHA256` | Provider không cung cấp thuật toán hoặc JDK không phải bản hỗ trợ API | Xác minh JDK 25+, provider và tên chuẩn |
| `NoSuchAlgorithmException` với `KDF` | Đang chạy JDK cũ hoặc classpath/runtime không đúng | Kiểm tra `java --version`, `javac --version` và runtime thực tế |
| `InvalidAlgorithmParameterException` | Spec/độ dài/tham số không phù hợp với provider | Kiểm tra HKDF parameter spec, IKM, salt, độ dài và provider |
| Hai dịch vụ dẫn xuất ra khóa khác nhau | IKM, salt, info, algorithm hoặc length không giống nhau | So sánh toàn bộ tham số protocol và encoding của info |
| Hai mục đích vô tình có cùng key | Dùng cùng IKM/salt/info/length cho cả hai | Dùng nhãn info riêng, có namespace và version |
| Khóa thay đổi sau mỗi lần chạy | IKM hoặc salt được tạo mới nhưng không lưu/chia sẻ theo protocol | Giữ đúng key material/salt metadata để hai bên tái tạo |
| Mất khóa sau khi restart | IKM gốc hoặc key version không được quản lý bền vững | Lưu master key trong KMS/HSM và lưu version/salt không bí mật |
| `getEncoded()` trả `null` | Key không thể export từ provider/HSM | Truyền `SecretKey` trực tiếp vào Cipher/Mac hoặc API tương thích |
| KDF hoạt động sai khi có nhiều request | Chia sẻ KDF instance không thread-safe | Tạo instance riêng hoặc đồng bộ |
| HKDF được dùng trực tiếp với password | Nhầm HKDF với password hashing KDF | Dùng PBKDF2/Argon2id phù hợp, không kỳ vọng HKDF tăng entropy |
| Provider HSM không nhận IKM | Key type hoặc KDF service không hỗ trợ non-extractable key | Kiểm tra provider và overload `addIKM(SecretKey)` |
| Output quá dài | Vượt giới hạn HKDF 255 × HashLen hoặc chọn sai length | Chọn độ dài theo thuật toán đích, kiểm tra RFC 5869 |
| Hai bên dùng cùng info nhưng khác cách viết | Khác charset, delimiter hoặc canonical encoding | Định nghĩa encoding byte chính xác trong protocol |

### Kiểm tra phiên bản và provider

~~~bash
java --version
javac --version
~~~

Một chương trình kiểm tra nhanh các tên KDF có thể gọi:

~~~java
for (String algorithm : new String[] {
        "HKDF-SHA256", "HKDF-SHA384", "HKDF-SHA512"
}) {
    try {
        KDF kdf = KDF.getInstance(algorithm);
        System.out.println(algorithm + " -> available");
    } catch (java.security.NoSuchAlgorithmException ex) {
        System.out.println(algorithm + " -> unavailable");
    }
}
~~~

Kết quả phụ thuộc provider trong runtime. Nếu môi trường production dùng provider FIPS hoặc HSM riêng, kiểm tra chính sách và danh sách thuật toán của provider đó thay vì suy từ máy phát triển.

## 15. Bài tập thực hành và checklist

### Bài tập A — Tách khóa cho hai mục đích

Dùng một IKM 32 byte và một salt 32 byte. Dẫn xuất:

1. AES-256 key với info `inventory/v1/encryption/aes-256-gcm`.
2. HMAC-SHA256 key với info `inventory/v1/event-auth/hmac-sha256`.

Kiểm tra `getAlgorithm()` và dùng từng khóa với `Cipher`/ `Mac` đúng mục đích. Không in key bytes ra console.

### Bài tập B — Thay đổi info và quan sát kết quả

Giữ IKM, salt, KDF algorithm và output length không đổi. Chạy ba lần với info:

- `service/v1/client-to-server`
- `service/v1/server-to-client`
- `service/v2/client-to-server`

Giải thích vì sao mỗi mục đích/phiên bản tạo key riêng và tại sao cả hai bên phải thống nhất chính xác byte encoding.

### Bài tập C — Tái tạo khóa sau restart

Lưu salt và key version cùng metadata ciphertext. Khởi động lại chương trình, nạp cùng master key từ secret store, dẫn xuất lại với cùng info và giải mã dữ liệu thử nghiệm. Chứng minh chỉ cần lưu metadata không bí mật nhưng không được làm mất IKM.

### Bài tập D — Phân biệt HKDF với password KDF

Một nhóm muốn lấy password người dùng, gọi `HKDF-SHA256` và tạo AES key. Hãy giải thích vì sao đây là thiết kế không phù hợp, chọn một password-based KDF và xác định những tham số cần quản lý.

### Checklist nghiệm thu

- [ ] Đang chạy JDK 25 hoặc mới hơn; KDF API là API chính thức, không cần preview flags.
- [ ] IKM đến từ nguồn bí mật có entropy cao; không dùng password trực tiếp làm IKM.
- [ ] Chọn HKDF-SHA256/384/512 theo yêu cầu tương thích và chính sách mật mã.
- [ ] Dùng salt theo giao thức; biết salt không cần bí mật và phải có sẵn để tái tạo khóa.
- [ ] Đặt `info` riêng cho từng ứng dụng, phiên bản, thuật toán và mục đích.
- [ ] Chọn độ dài đúng với thuật toán đích; không vượt giới hạn 255 × HashLen.
- [ ] Dùng `deriveKey` khi cần SecretKey; không export key bytes nếu không cần.
- [ ] Không dùng chung một KDF instance đồng thời nếu chưa đồng bộ.
- [ ] Không log IKM, PRK, derived key hoặc thông tin nhạy cảm.
- [ ] Quản lý master key, version, salt, rotation và quyền truy cập bằng quy trình riêng.
- [ ] Đã kiểm tra provider thật sự có thuật toán và hỗ trợ loại key material đang dùng.
- [ ] Có test tái lập cùng tham số và tách biệt khi thay đổi info.

## 16. Tài liệu chính thức

- [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510): hoàn thiện KDF API trong JDK 25.
- [Java SE 25 — KDF API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html): `getInstance`, `deriveKey`, `deriveData`, provider selection và thread safety.
- [Java SE 27 — KDF API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/KDF.html): xác nhận API được giữ từ Java 25 trên JDK mới hơn.
- [Java SE 25 — HKDFParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html): Extract, Expand, Extract-and-Expand và các tham số HKDF.
- [Java SE 25 — HKDFParameterSpec.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.Builder.html): `addIKM`, `addSalt`, `extractOnly`, `thenExpand`.
- [Java SE 25 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên HKDF-SHA256, HKDF-SHA384 và HKDF-SHA512.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869): định nghĩa Extract, Expand, salt, info và giới hạn độ dài.
- [Oracle — JDK 25 Security Enhancements](https://inside.java/2025/09/24/jdk25-security-enhancements/): tổng quan KDF API và lý do đưa vào JDK 25.

> **Ghi nhớ:** Dùng HKDF để tách nhiều khóa từ IKM có entropy cao. **Salt** hỗ trợ Extract; **info** gắn khóa với ứng dụng, phiên bản và mục đích. Cùng IKM/salt/info tạo cùng đầu ra; thay info để tách mục đích. HKDF không phải password hashing KDF và không thay thế quản lý khóa.
