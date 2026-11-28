# Quản lý vòng đời vật liệu khóa, dữ liệu nhạy cảm và lỗi provider

## 1. Mục tiêu: dẫn xuất khóa đúng và quản lý được bí mật

Một ứng dụng Java có thể cần nhiều khóa từ cùng một bí mật gốc: khóa mã hóa dữ liệu, khóa xác thực, khóa cho từng phiên hoặc khóa dành riêng cho một giao thức. Tạo một khóa rồi dùng lại cho mọi mục đích làm các ranh giới bảo mật bị trộn lẫn. Tự ghép byte, hash hoặc HMAC theo cách riêng cũng dễ tạo ra một thuật toán không có thiết kế và kiểm chứng đầy đủ.

**Key Derivation Function (KDF)** giải quyết bài toán dẫn xuất vật liệu khóa từ một đầu vào mật mã (*input keying material*, IKM) và các tham số bổ sung. Trong Java 25, API chuẩn là **`javax.crypto.KDF`**, được hoàn thiện theo **JEP 510**. JDK Reference Implementation có triển khai **HKDF** trong provider SunJCE, với các tên chuẩn **`HKDF-SHA256`**, **`HKDF-SHA384`** và **`HKDF-SHA512`**. API này đã là tính năng chính thức, không cần `--enable-preview`. [JEP 510](https://inside.java/2025/09/24/jdk25-security-enhancements/) [Java SE 25 KDF API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html) [Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html)

Bài **Quản lý vòng đời vật liệu khóa, dữ liệu nhạy cảm và lỗi provider** thuộc chương **API dẫn xuất khóa** trong module **JAVA_VERSION_JAVA25**. Trọng tâm là cách xử lý dữ liệu bí mật trước, trong và sau khi dẫn xuất; cách chọn provider phù hợp; và cách phản ứng khi thuật toán, tham số hoặc loại key không được hỗ trợ.

### Sau bài này, người học có thể

1. Phân biệt IKM, salt, PRK, `info` và output keying material (OKM).
2. Dùng `KDF`, `HKDFParameterSpec` và `SecretKey` để dẫn xuất khóa trong Java 25.
3. Chọn `deriveKey()` hay `deriveData()` theo yêu cầu của API tiêu thụ khóa.
4. Thiết kế `info` để tách biệt khóa theo ứng dụng, giao thức và mục đích.
5. Quản lý byte array, `SecretKey`, bản sao dữ liệu và thời điểm hủy vật liệu khóa.
6. Làm việc với key không export được từ HSM/provider và hiểu cơ chế delayed provider selection.
7. Phân loại lỗi `NoSuchAlgorithmException`, `NoSuchProviderException`, `InvalidAlgorithmParameterException` và `UnsupportedOperationException`.
8. Kiểm thử theo vector chuẩn, kiểm tra capability của provider và thiết lập quy trình xử lý lỗi an toàn.

> **Phạm vi phiên bản:** KDF API đã là API chính thức trong Java 25 theo JEP 510. API được preview trong Java 24 theo JEP 478, nhưng các ví dụ của bài này dùng API Java 25 đã hoàn thiện và không bật preview flags.

## 2. KDF giải quyết việc gì?

KDF tạo ra vật liệu khóa mới từ đầu vào mật mã có sẵn. Ví dụ, sau một thỏa thuận khóa Diffie–Hellman hoặc một quy trình trao đổi khóa khác, hai bên có thể cùng có một bí mật chia sẻ. KDF biến bí mật đó thành một hoặc nhiều khóa có định dạng, độ dài và mục đích cụ thể.

~~~mermaid
flowchart TD
    A[Input Keying Material - IKM] --> E[HKDF-Extract]
    B[Salt tùy chọn] --> E
    E --> C[PRK - pseudorandom key]
    C --> F[HKDF-Expand]
    D[Info: context / purpose] --> F
    F --> G[Output keying material]
    G --> H[SecretKey cho AES]
    G --> I[SecretKey cho HMAC]
~~~

KDF **không tạo bí mật từ không khí**. Chất lượng của đầu ra phụ thuộc vào nguồn IKM và cách chọn tham số. Nếu đầu vào có entropy thấp, KDF không thể tự biến nó thành một bí mật có entropy cao.

### 2.1. Phân biệt các thành phần

| Thành phần | Tên đầy đủ | Vai trò | Có cần giữ bí mật? |
| --- | --- | --- | --- |
| IKM | Input Keying Material | Bí mật đầu vào, ví dụ shared secret từ key agreement hoặc key gốc | Có |
| Salt | Salt đầu vào | Tham số hỗ trợ bước Extract, thường là giá trị ngẫu nhiên không bí mật | Thông thường không |
| PRK | Pseudorandom Key | Kết quả của bước Extract, làm đầu vào cho Expand | Có |
| `info` | Context/application-specific information | Gắn đầu ra với protocol, version, algorithm, purpose hoặc hướng truyền | Thường không |
| OKM | Output Keying Material | Vật liệu đầu ra có độ dài được yêu cầu | Có nếu dùng làm key |

Không đưa IKM, PRK, OKM hoặc byte của khóa vào log, exception message, metrics label hay báo cáo hỗ trợ. Salt và `info` thường không bí mật, nhưng vẫn có thể chứa thông tin định danh hoặc metadata cần bảo vệ theo chính sách dữ liệu.

### 2.2. KDF khác với các API mật mã khác

| API / khái niệm | Nhiệm vụ | Khi nào dùng |
| --- | --- | --- |
| `KeyPairGenerator` | Tạo cặp khóa công khai/bí mật | Khởi tạo khóa bất đối xứng |
| `KeyAgreement` | Hai bên thiết lập shared secret | Sau trao đổi khóa |
| `KeyGenerator` | Sinh khóa ngẫu nhiên cho thuật toán | Cần khóa mới độc lập |
| `KDF` | Dẫn xuất khóa từ IKM và context | Tạo khóa theo mục đích từ bí mật đã có |
| `Cipher` | Mã hóa/giải mã dữ liệu | Thực hiện thao tác mã hóa |
| `Mac` | Tạo/xác minh message authentication code | Kiểm tra tính toàn vẹn/xác thực |
| Password hashing / password-based KDF | Lưu hoặc xác minh mật khẩu người dùng | Xác thực người dùng |

KDF không thay `Cipher`, `Mac`, `KeyAgreement` hoặc hệ thống quản lý khóa. Nó là một mắt xích trong quy trình mật mã.

## 3. Java 25 KDF API: các lớp cần biết

API chuẩn nằm trong module `java.base`, package `javax.crypto` và `javax.crypto.spec`.

| Kiểu | Vai trò |
| --- | --- |
| `javax.crypto.KDF` | Tạo instance KDF và gọi thao tác dẫn xuất |
| `javax.crypto.KDFParameters` | Nhóm tham số khởi tạo dành cho một KDF/provider |
| `javax.crypto.KDFSpi` | SPI để provider triển khai thuật toán KDF |
| `javax.crypto.spec.HKDFParameterSpec` | Mô tả Extract, Expand hoặc Extract-then-Expand |
| `javax.crypto.SecretKey` | Đại diện cho khóa bí mật đầu ra hoặc IKM dạng key |
| `javax.security.auth.Destroyable` | API hủy vật liệu nhạy cảm nếu implementation hỗ trợ |

### 3.1. Hai giai đoạn API

**Khởi tạo KDF:**

~~~java
KDF hkdf = KDF.getInstance("HKDF-SHA256");
~~~

**Mô tả đầu vào và dẫn xuất:**

~~~java
AlgorithmParameterSpec params =
    HKDFParameterSpec.ofExtract()
        .addIKM(ikm)
        .addSalt(salt)
        .thenExpand(info, 32);

SecretKey key = hkdf.deriveKey("AES", params);
~~~

`KDF.getInstance(...)` chọn thuật toán và có thể nhận provider/`KDFParameters`. `HKDFParameterSpec` mô tả vật liệu đầu vào và thao tác cụ thể cho lần derive. Hai loại tham số này phục vụ **hai cấp khác nhau**: tham số khởi tạo KDF/provider và tham số dữ liệu cho thao tác dẫn xuất.

### 3.2. deriveKey() và deriveData()

| Phương thức | Kiểu trả về | Nên chọn khi |
| --- | --- | --- |
| `deriveKey(String alg, AlgorithmParameterSpec spec)` | `SecretKey` | API tiêu thụ khóa nhận `SecretKey`, ví dụ `Cipher.init(...)` hoặc `Mac.init(...)` |
| `deriveData(AlgorithmParameterSpec spec)` | `byte[]` | Ứng dụng thật sự cần raw keying material dạng byte |

Ưu tiên `deriveKey()` khi có thể. `SecretKey` giúp giữ biểu diễn khóa theo abstraction của JCA và cho phép provider quản lý key material theo cách riêng. Với HSM hoặc provider giữ khóa không export được, `deriveData()` có thể ném `UnsupportedOperationException`; không nên ép khóa ra byte chỉ để tiện debug.

## 4. HKDF: Extract và Expand

Java 25 cung cấp HKDF theo **RFC 5869**, dựa trên HMAC.

### 4.1. Extract

`HKDF-Extract(salt, IKM)` nhận IKM và salt tùy chọn, tạo ra PRK.

- IKM thường là shared secret có entropy tốt.
- Salt thường là giá trị ngẫu nhiên không bí mật.
- Nếu không có salt, RFC 5869 quy định dùng chuỗi zero có độ dài bằng output hash.
- Salt có thể được lưu cùng metadata cần thiết để tái tạo khóa; không cần giữ bí mật như IKM.

### 4.2. Expand

`HKDF-Expand(PRK, info, L)` dùng PRK và `info` để tạo OKM dài `L` byte.

- `info` gắn đầu ra với một context hoặc ứng dụng cụ thể.
- Cùng IKM/salt nhưng `info` khác nhau sẽ tạo ra các vật liệu khóa được tách biệt theo mục đích.
- `L` là số byte đầu ra; chọn đúng độ dài theo thuật toán đích.
- Với HKDF, giới hạn output là `255 × HashLen` byte. Provider kiểm tra giới hạn này.

Với HKDF-SHA256, `HashLen` là 32 byte nên giới hạn lý thuyết là 8.160 byte. Không vì giới hạn này mà dẫn xuất một khối lớn không cần thiết; ứng dụng nên yêu cầu đúng độ dài khóa hoặc dữ liệu mà giao thức quy định. [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869.html) [HKDFParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html)

### 4.3. Salt và info có vai trò khác nhau

| Tham số | Dùng để | Ví dụ |
| --- | --- | --- |
| Salt | Hỗ trợ bước Extract, tạo sự độc lập giữa các lần dẫn xuất | Nonce công khai hoặc byte ngẫu nhiên của phiên |
| `info` | Domain separation, xác định mục đích của đầu ra | `orders/v1/aes-gcm/encryption-key` |
| IKM | Nguồn bí mật | Shared secret từ key agreement |

Không hoán đổi salt và `info`. `info` không phải bí mật đầu vào và không thể thay thế IKM. Cũng không dùng cùng một chuỗi tùy tiện cho mọi protocol; cần quy ước encoding và domain label ổn định.

## 5. Ví dụ dẫn xuất khóa AES bằng Java 25

Ví dụ sau dùng IKM ngẫu nhiên chỉ để minh họa API. Trong hệ thống thực, IKM thường đến từ một quy trình key agreement, KMS/HSM hoặc một nguồn key material có entropy cao và đã được xác thực.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

public final class HkdfAesExample {

    private static SecretKey deriveAesKey(
            byte[] ikm,
            byte[] salt,
            byte[] info) throws GeneralSecurityException {

        KDF hkdf = KDF.getInstance("HKDF-SHA256");

        var params = HKDFParameterSpec.ofExtract()
            .addIKM(ikm)
            .addSalt(salt)
            .thenExpand(info, 32);

        return hkdf.deriveKey("AES", params);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        SecureRandom random = new SecureRandom();
        byte[] ikm = new byte[32];
        byte[] salt = new byte[32];

        random.nextBytes(ikm);
        random.nextBytes(salt);

        byte[] info =
            "inventory/v1/aes-gcm/encryption-key"
                .getBytes(StandardCharsets.UTF_8);

        SecretKey key = null;

        try {
            key = deriveAesKey(ikm, salt, info);
            System.out.println("Key algorithm: " + key.getAlgorithm());
        } finally {
            Arrays.fill(ikm, (byte) 0);
            Arrays.fill(salt, (byte) 0);

            if (key != null) {
                try {
                    key.destroy();
                } catch (javax.security.auth.DestroyFailedException ex) {
                    // Production: báo sự kiện vận hành đã redact, không log key bytes.
                }
            }
        }
    }
}
~~~

Trong ví dụ, `32` byte đầu ra phù hợp với khóa AES-256. `deriveKey("AES", ...)` trả về `SecretKey`, không cần chuyển khóa thành chuỗi hoặc in ra console.

### 5.1. Những gì ví dụ không chứng minh

- Tạo IKM bằng `SecureRandom` không thay thế giao thức trao đổi khóa giữa hai bên.
- Salt không cần bí mật, nhưng phải được lưu/trao đổi để có thể tái tạo khóa khi protocol yêu cầu.
- `key.destroy()` là nỗ lực giải phóng key material; không đảm bảo mọi bản sao nội bộ của provider/JVM đều bị ghi đè.
- Ví dụ không mã hóa dữ liệu. Sau khi dẫn xuất khóa, ứng dụng vẫn phải dùng `Cipher` với mode, nonce/IV và quy tắc xác thực phù hợp.
- Nếu dùng AES-GCM, mỗi lần mã hóa với cùng khóa phải dùng nonce/IV duy nhất theo yêu cầu của GCM. KDF không tự tạo hoặc quản lý nonce.

## 6. Thiết kế info để không tái sử dụng khóa sai mục đích

Một IKM có thể dùng làm nguồn dẫn xuất cho nhiều khóa. Hãy tạo domain separation bằng `info` khác nhau.

Ví dụ:

~~~java
byte[] encryptionInfo =
    "payments/v1/aes-gcm/encryption-key"
        .getBytes(StandardCharsets.UTF_8);

byte[] authenticationInfo =
    "payments/v1/hmac-sha256/authentication-key"
        .getBytes(StandardCharsets.UTF_8);
~~~

Từ cùng IKM và salt, dẫn xuất hai khóa riêng:

~~~java
KDF hkdf = KDF.getInstance("HKDF-SHA256");

SecretKey encryptionKey = hkdf.deriveKey(
    "AES",
    HKDFParameterSpec.ofExtract()
        .addIKM(ikm)
        .addSalt(salt)
        .thenExpand(encryptionInfo, 32));

SecretKey authenticationKey = hkdf.deriveKey(
    "HmacSHA256",
    HKDFParameterSpec.ofExtract()
        .addIKM(ikm)
        .addSalt(salt)
        .thenExpand(authenticationInfo, 32));
~~~

Ví dụ trên minh họa hai lần dẫn xuất tuần tự. Không chia sẻ cùng một `KDF` instance đồng thời giữa nhiều thread; API không cam kết thread-safe. Nếu muốn chạy song song, tạo instance riêng cho từng task.

### Quy tắc thiết kế info

1. Bao gồm tên ứng dụng hoặc protocol.
2. Bao gồm phiên bản của quy ước dẫn xuất.
3. Bao gồm mục đích cụ thể: encryption, authentication, wrapping hoặc direction.
4. Dùng encoding ổn định, ví dụ UTF-8 của chuỗi chuẩn hóa hoặc một cấu trúc binary có length-prefix.
5. Không dùng giá trị không ổn định như timestamp ngẫu nhiên nếu protocol không yêu cầu.
6. Không chứa secret hoặc dữ liệu cá nhân chỉ để “tạo thêm entropy”.
7. Hai bên tham gia protocol phải thống nhất chính xác bytes của `info`.

Một chuỗi `info` không rõ ràng có thể gây trùng context, dẫn xuất sai khóa hoặc khiến hai hệ thống không tái tạo được cùng kết quả.

## 7. Không dùng HKDF để lưu mật khẩu người dùng

Đây là ranh giới quan trọng.

HKDF phù hợp khi IKM đã có entropy mật mã đủ tốt, chẳng hạn shared secret từ key agreement. Nó không được thiết kế để làm chậm quá trình thử mật khẩu. Một mật khẩu do người dùng chọn thường có entropy thấp; attacker có thể thử danh sách mật khẩu nhanh nếu ứng dụng chỉ áp dụng HKDF một lần.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Dẫn xuất session/encryption keys từ shared secret | HKDF |
| Tạo nhiều khóa từ một key agreement result | HKDF với `info` khác nhau |
| Lưu password verifier | Password hashing/KDF có salt và cost phù hợp, ví dụ Argon2id hoặc giải pháp đạt chuẩn tổ chức |
| Sinh khóa ngẫu nhiên độc lập | `KeyGenerator` + `SecureRandom` |
| Mã hóa dữ liệu | `Cipher` với thuật toán/mode được phê duyệt |

RFC 5869 giải thích rằng HKDF không có cơ chế làm chậm dictionary attack như các password-based KDF. Vì vậy không đưa password trực tiếp vào `addIKM()` rồi coi kết quả là password storage an toàn. Java 25 KDF standard names tập trung vào HKDF-SHA256/384/512; Argon2id không phải một implementation KDF built-in của JDK. Nếu cần xác thực mật khẩu, dùng thư viện password-hashing chuyên dụng hoặc cơ chế được nền tảng bảo mật phê duyệt. [RFC 5869, mục 3.2](https://www.rfc-editor.org/rfc/rfc5869.html) [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html)

## 8. Quản lý IKM, salt và dữ liệu đầu vào

### 8.1. IKM là dữ liệu nhạy cảm

IKM có thể đến từ:

- Shared secret sau `KeyAgreement`.
- Secret được cấp từ KMS/HSM.
- Một khóa gốc do hệ thống quản lý an toàn.
- Một nguồn key material khác được giao thức xác định.

Không dùng `Random` thông thường để tạo IKM. Khi cần sinh bytes ngẫu nhiên cho mục đích mật mã, dùng `SecureRandom` hoặc cơ chế sinh khóa của provider.

### 8.2. Salt thường không bí mật

Salt HKDF có thể công khai và thường được lưu cùng metadata phiên hoặc ciphertext. Salt giúp tạo sự độc lập giữa các lần dẫn xuất; không nên dùng salt như một cách che giấu IKM.

Nếu ứng dụng cần tái tạo khóa sau restart, cần lưu salt và metadata cần thiết theo protocol, nhưng không lưu IKM/PRK/khóa gốc cùng chỗ dưới dạng plaintext.

### 8.3. info là metadata của context

`info` nên được tạo từ các giá trị ổn định đã được chuẩn hóa. Không dùng nội dung request tùy ý, log message, tên người dùng hoặc chuỗi do client kiểm soát làm `info` nếu không có quy tắc encoding và giới hạn rõ.

### 8.4. Không tái sử dụng byte array nhạy cảm vô thức

Một byte array có thể được giữ bởi nhiều tham chiếu hoặc bị sao chép vào object khác. Hãy xác định rõ:

- Ai tạo array?
- Ai sở hữu array?
- API có clone array không?
- Khi nào có thể xóa bản gốc?
- Có bản sao trong `SecretKeySpec`, provider hoặc heap dump không?

Ví dụ `HKDFParameterSpec.Builder.addIKM(byte[])` chuyển dữ liệu vào `SecretKeySpec`, mà constructor của `SecretKeySpec` clone mảng đầu vào. Việc gọi `Arrays.fill()` trên mảng ban đầu không xóa được bản sao nội bộ đó. [HKDFParameterSpec.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.Builder.html) [SecretKeySpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html)

## 9. Làm việc với SecretKey không export được

Một provider có thể giữ khóa bên trong thiết bị phần cứng hoặc vùng bảo vệ, không cho ứng dụng lấy raw bytes. Trong trường hợp này:

- `SecretKey.getEncoded()` có thể trả về `null`.
- Không được giả định mọi key có format `RAW`.
- Không ép key qua `new SecretKeySpec(key.getEncoded(), ...)`.
- Nên giữ key ở dạng `SecretKey` và chuyển trực tiếp cho API mật mã/provider tương thích.
- Dùng `HKDFParameterSpec.Builder.addIKM(SecretKey)` nếu provider hỗ trợ đưa key không extractable làm IKM.

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;

SecretKey hardwareKey = loadSecretKeyFromHsm();

var params = HKDFParameterSpec.ofExtract()
    .addIKM(hardwareKey)
    .addSalt(sessionSalt)
    .thenExpand(
        "service/v1/aes-gcm/key".getBytes(StandardCharsets.UTF_8),
        32);

KDF hkdf = KDF.getInstance("HKDF-SHA256");
SecretKey derivedKey = hkdf.deriveKey("AES", params);
~~~

`loadSecretKeyFromHsm()` là hàm tích hợp của ứng dụng/provider, không phải API JDK. Ví dụ chỉ thành công khi provider KDF được chọn hỗ trợ loại key material đó. Một provider có thể hỗ trợ `HKDF-SHA256` với byte array nhưng không hỗ trợ key handle từ HSM.

### 9.1. Nhiều phần IKM hoặc salt

`HKDFParameterSpec.Builder` cho phép gọi `addIKM(...)` và `addSalt(...)` nhiều lần. Điều này hữu ích khi IKM được ghép từ nhiều phần, một phần là `SecretKey` không extractable.

~~~java
var params = HKDFParameterSpec.ofExtract()
    .addIKM(protocolLabel)
    .addIKM(hardwareKey)
    .addIKM(sharedSecretPart)
    .addSalt(publicSalt)
    .thenExpand(info, 32);
~~~

Thứ tự các phần phải được quy định nhất quán giữa các bên. Đừng tự ghép chuỗi byte theo thứ tự không được protocol xác định.

### 9.2. deriveData() có thể không phù hợp với key không extractable

Nếu provider không cho phép export output keying material, `deriveData()` có thể ném `UnsupportedOperationException`. Khi mục tiêu là dùng khóa với `Cipher` hoặc `Mac`, hãy ưu tiên `deriveKey()` và giữ kết quả trong abstraction `SecretKey`. [KDF API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html) [HKDFParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html)

## 10. Vòng đời của SecretKey và nỗ lực xóa vật liệu nhạy cảm

`SecretKey` trong Java SE 25 mở rộng `Destroyable`, cung cấp `destroy()` và `isDestroyed()`. Các provider implementation được khuyến nghị ghi đè các method này để xóa, giải phóng hoặc bỏ tham chiếu tới thông tin nhạy cảm. Nhưng **không có bảo đảm chung rằng mọi bản sao byte trong JVM, native memory hoặc phần cứng đều bị ghi đè**. [SecretKey API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/SecretKey.html)

### 10.1. Thực hành vòng đời

1. Chỉ tạo IKM khi cần.
2. Giữ key trong `SecretKey` nếu API tiêu thụ hỗ trợ.
3. Không in key, không log `getEncoded()` và không gắn bytes vào exception.
4. Không serialize `SecretKey` tùy tiện hoặc lưu vào cấu hình plaintext.
5. Xóa byte array do ứng dụng sở hữu sau khi không còn cần.
6. Gọi `destroy()` khi kết thúc vòng đời key nếu implementation hỗ trợ.
7. Xử lý `DestroyFailedException` như một tín hiệu vận hành cần đánh giá.
8. Không giả định GC hoặc kết thúc scope đồng nghĩa key đã được xóa khỏi memory.

`SecretKey` kế thừa các method mặc định từ `Destroyable`; tài liệu Java khuyến nghị provider implementation ghi đè `destroy()` và `isDestroyed()` để giải phóng key material. Vì vậy, đừng mặc định mọi `SecretKey` đều có khả năng zeroize như nhau. Một implementation có thể không hỗ trợ hủy vật lý hoặc chỉ có thể bỏ tham chiếu tới dữ liệu. Hãy xem tài liệu provider, xử lý lỗi destroy và coi đây là **best effort**.

### 10.2. Xóa byte array trong finally

~~~java
byte[] ikm = obtainIkm();
byte[] salt = obtainSalt();

try {
    SecretKey key = deriveKey(ikm, salt);
    useKey(key);
} finally {
    Arrays.fill(ikm, (byte) 0);
    Arrays.fill(salt, (byte) 0);
}
~~~

Đoạn trên giả định `obtainIkm()` và `obtainSalt()` trả về array do code hiện tại sở hữu. Nếu array được dùng ở nơi khác, không được xóa khi consumer khác vẫn cần. Trong ví dụ thực tế, salt thường không phải bí mật, nhưng xóa nếu không còn cần có thể giảm dữ liệu lưu trong memory.

### 10.3. Hủy SecretKey sau khi sử dụng

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.security.auth.DestroyFailedException;

static byte[] encryptAndDestroy(
        SecretKey key,
        byte[] plaintext,
        GCMParameterSpec gcmParameterSpec)
        throws GeneralSecurityException {

    Exception primaryFailure = null;
    try {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, gcmParameterSpec);
        return cipher.doFinal(plaintext);
    } catch (GeneralSecurityException | RuntimeException ex) {
        primaryFailure = ex;
        throw ex;
    } finally {
        try {
            key.destroy();
        } catch (DestroyFailedException destroyFailure) {
            if (primaryFailure != null) {
                primaryFailure.addSuppressed(destroyFailure);
            } else {
                throw new GeneralSecurityException(
                    "Provider could not destroy key material", destroyFailure);
            }
        }
    }
}
~~~

Đoạn mã minh họa việc hủy key sau khi thao tác mã hóa kết thúc và giữ nguyên exception chính nếu thao tác lẫn destroy cùng thất bại. Caller phải cung cấp `GCMParameterSpec` với nonce/IV duy nhất theo protocol; hàm không tự tạo nonce. Trong hệ thống có HSM/KMS, việc hủy key handle và lifecycle thực tế phụ thuộc provider.

### 10.4. Cẩn trọng với getEncoded()

`getEncoded()` có thể tạo một byte array mới chứa key material. Nếu thật sự cần export theo yêu cầu của API, hãy giới hạn phạm vi và xóa bản sao:

~~~java
byte[] encoded = key.getEncoded();

if (encoded == null) {
    throw new IllegalStateException("Key is not extractable");
}

try {
    passToApprovedBoundary(encoded);
} finally {
    Arrays.fill(encoded, (byte) 0);
}
~~~

Tên `passToApprovedBoundary` chỉ đại diện cho một integration boundary đã được phê duyệt. Không tạo hàm kiểu này chỉ để né việc API hiện đại không nhận `SecretKey`. Khi provider giữ key không exportable, `getEncoded()` không phải đường thay thế.

## 11. KDF và provider: chọn đúng implementation

JCA dùng provider để cung cấp implementation cho thuật toán. Cùng tên thuật toán có thể được triển khai bởi provider mặc định, provider của HSM hoặc provider bên thứ ba.

Trong JDK Reference Implementation, SunJCE cung cấp HKDF. Tuy nhiên, không nên giả định mọi JDK distribution, phiên bản provider hoặc chế độ bảo mật của môi trường đều có cùng capability. Hãy kiểm tra trong môi trường triển khai.

### 11.1. Liệt kê provider quảng bá dịch vụ KDF

~~~java
import java.security.Provider;
import java.security.Security;

public class KdfProviderInventory {

    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            Provider.Service service =
                provider.getService("KDF", "HKDF-SHA256");

            if (service != null) {
                System.out.println(
                    provider.getName() + " supports HKDF-SHA256");
            }
        }
    }
}
~~~

Đây là bước **inventory**, không phải bằng chứng cuối cùng rằng provider có thể xử lý mọi kiểu IKM, salt, tham số và output algorithm. Hãy thực hiện một phép dẫn xuất thử với key material/parameter thực tế phù hợp.

### 11.2. Chọn provider mặc định

~~~java
KDF hkdf = KDF.getInstance("HKDF-SHA256");
~~~

Nếu không chỉ định provider, JCA áp dụng thứ tự provider ưu tiên. KDF API có **delayed provider selection**: implementation có thể trì hoãn chọn provider đến khi gọi `deriveKey()` hoặc `deriveData()`, để chọn provider có thể xử lý chính key material truyền vào — ví dụ key handle trong HSM.

### 11.3. Chỉ định provider tường minh

Khi chính sách yêu cầu một provider đã được phê duyệt:

~~~java
KDF hkdf = KDF.getInstance("HKDF-SHA256", "SunJCE");
~~~

Hoặc dùng object `Provider`:

~~~java
Provider provider = Security.getProvider("SunJCE");

if (provider == null) {
    throw new IllegalStateException("Required provider is not installed");
}

KDF hkdf = KDF.getInstance("HKDF-SHA256", provider);
~~~

Tên `SunJCE` minh họa cho JDK Reference Implementation; với HSM, FIPS provider hoặc nhà cung cấp khác, dùng đúng provider name/configuration được triển khai. Không hardcode provider mặc định vào thư viện dùng chung nếu consumer cần lựa chọn provider riêng.

### 11.4. Đừng hỏi provider quá sớm

Với delayed provider selection, gọi `getProviderName()` hoặc `getParameters()` trước lần derive đầu tiên có thể làm provider được chọn dựa trên algorithm và `KDFParameters`, nhưng chưa biết key material sẽ được dùng. Provider được chọn sớm có thể không hỗ trợ key đó.

Quy trình phù hợp:

1. Tạo `KDF`.
2. Tạo HKDF parameters.
3. Gọi `deriveKey()`/`deriveData()` với key material thực tế.
4. Sau khi derive thành công, đọc provider name nếu cần ghi audit cấu hình.
5. Ghi nhận tên provider/algorithm/version, tuyệt đối không ghi bí mật đầu vào/đầu ra.

Provider đã được chọn sẽ không tự đổi giữa các lần gọi trên cùng `KDF` instance. [KDF API — Delayed Provider Selection](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html)

## 12. KDF object và Builder không thread-safe

Java 25 KDF API không cam kết các method của `KDF` thread-safe. `HKDFParameterSpec.Builder` cũng không thread-safe. Nếu nhiều thread cùng thao tác trên một instance, phải tự đồng bộ hóa hoặc dùng object riêng.

**Khuyến nghị cho server:**

- Tạo một `KDF` instance cho mỗi lần xử lý hoặc mỗi task.
- Tạo một `HKDFParameterSpec.Builder` riêng cho mỗi lần dẫn xuất.
- Không giữ Builder như static mutable field.
- Không dùng chung một Builder giữa các request.
- Các parameter object đã build (`Extract`, `ExtractThenExpand`) là immutable theo API; tuy vậy vẫn cần kiểm soát lifecycle của SecretKey/IKM được tham chiếu.
- Nếu có lý do tái sử dụng một `KDF` object giữa nhiều thread, chỉ làm khi provider có tài liệu bảo đảm hoặc ứng dụng tự khóa đầy đủ.

Ví dụ service không chia sẻ KDF instance:

~~~java
public SecretKey deriveForRequest(
        byte[] ikm, byte[] salt, byte[] info)
        throws GeneralSecurityException {

    KDF hkdf = KDF.getInstance("HKDF-SHA256");

    var spec = HKDFParameterSpec.ofExtract()
        .addIKM(ikm)
        .addSalt(salt)
        .thenExpand(info, 32);

    return hkdf.deriveKey("AES", spec);
}
~~~

Việc tạo instance mới không có nghĩa phải tạo provider mới hoặc tải lại provider mỗi request; `getInstance` lấy implementation theo JCA. Đo hiệu năng trên workload thực trước khi tối ưu lifecycle object, và không đánh đổi thread safety để tiết kiệm một đối tượng nhỏ.

## 13. Phân biệt KDFParameters và HKDFParameterSpec

Hai tên gần giống nhau nhưng khác mục đích.

| Kiểu | Được dùng ở đâu? | Ví dụ thông tin |
| --- | --- | --- |
| `KDFParameters` | Các overload `KDF.getInstance(...)` | Tham số khởi tạo/đặc thù provider hoặc thuật toán |
| `HKDFParameterSpec` | `deriveKey(...)` / `deriveData(...)` | IKM, salt, info, output length và Extract/Expand mode |

Ví dụ API có thể nhận KDFParameters:

~~~java
KDF kdf = KDF.getInstance(
    "HKDF-SHA256",
    kdfParameters,
    provider);
~~~

`kdfParameters` ở đây phải là kiểu tham số phù hợp với implementation/provider. Không truyền `HKDFParameterSpec` thay cho `KDFParameters`; HKDFParameterSpec là `AlgorithmParameterSpec` dành cho lần derive.

Trong trường hợp HKDF tiêu chuẩn thông dụng, có thể dùng:

~~~java
KDF kdf = KDF.getInstance("HKDF-SHA256");
var derivationSpec = HKDFParameterSpec.ofExtract()
    .addIKM(ikm)
    .addSalt(salt)
    .thenExpand(info, 32);

SecretKey key = kdf.deriveKey("AES", derivationSpec);
~~~

`getParameters()` trả về `KDFParameters` của instance; nó không phải nơi đọc `info` hoặc IKM đã dùng cho từng phép derive. Có thể trả về `null` nếu implementation không cung cấp các tham số khởi tạo tương ứng.

## 14. Các lỗi provider và cách xử lý

Một ứng dụng mật mã không nên coi mọi lỗi provider là lỗi có thể retry bằng một thuật toán yếu hơn. Trước hết phải xác định lỗi đến từ thuật toán không có, provider không có, tham số sai hay key material không thể export.

| Exception | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Không provider nào hỗ trợ tên KDF; hoặc tên thuật toán khóa đầu ra không hợp lệ | Kiểm tra tên chuẩn, JDK/provider version và capability |
| `NoSuchProviderException` | Provider name yêu cầu không có trong security provider list | Kiểm tra cài đặt, cấu hình provider và môi trường |
| `InvalidAlgorithmParameterException` | Provider không hỗ trợ parameter set hoặc tham số không hợp lệ | Kiểm tra HKDF spec, output length, provider capability |
| `UnsupportedOperationException` | `deriveData()` yêu cầu xuất raw bytes nhưng key material không extractable | Dùng `deriveKey()` nếu consumer chấp nhận `SecretKey` |
| `IllegalArgumentException` | Ví dụ output length không dương khi tạo HKDF parameter spec | Kiểm tra input trước khi gọi API |
| `NullPointerException` | Truyền null vào algorithm/spec bắt buộc | Validate đầu vào ở boundary |
| `DestroyFailedException` | Provider không thể thực hiện yêu cầu destroy | Ghi nhận sự cố lifecycle; kiểm tra provider/key policy |

### 14.1. Không fallback âm thầm sang thuật toán khác

**Không nên:**

~~~java
try {
    return deriveWithHkdf(secret);
} catch (GeneralSecurityException ex) {
    return secret; // Sai: trả lại IKM như thể đã derive thành công
}
~~~

Hoặc thử lần lượt một thuật toán yếu hơn mà không có thiết kế protocol và phê duyệt bảo mật.

**Nên:**

- Phân loại lỗi và giữ nguyên nguyên nhân trong exception chain.
- Fail closed nếu key derivation là điều kiện bảo mật bắt buộc.
- Không tiếp tục mã hóa bằng khóa mặc định hoặc khóa hardcode.
- Phát tín hiệu readiness/health phù hợp nếu provider bắt buộc không sẵn sàng.
- Ghi log algorithm, provider, operation, error category và request correlation ID nếu an toàn.
- Không ghi IKM, PRK, output key, salt nếu chính sách coi salt nhạy cảm, hoặc `info` có dữ liệu riêng tư.

### 14.2. Ví dụ phân loại lỗi tại boundary

~~~java
try {
    KDF kdf = KDF.getInstance("HKDF-SHA256");
    SecretKey key = kdf.deriveKey("AES", spec);
    return key;
} catch (NoSuchAlgorithmException ex) {
    throw new IllegalStateException(
        "Required KDF/key algorithm is unavailable", ex);
} catch (InvalidAlgorithmParameterException ex) {
    throw new IllegalArgumentException(
        "KDF parameters are invalid for the configured provider", ex);
}
~~~

Đoạn này minh họa chuyển lỗi ở boundary của ứng dụng. Trong service thật, hãy quyết định exception type phù hợp với contract; không bắt lỗi rồi trả về một key rỗng hay một giá trị mặc định.

## 15. Kiểm tra algorithm và parameter trước khi đưa lên production

JDK 25 chuẩn hóa các tên HKDF:

| Tên KDF | Hash function | HashLen |
| --- | --- | ---: |
| `HKDF-SHA256` | HMAC-SHA-256 | 32 byte |
| `HKDF-SHA384` | HMAC-SHA-384 | 48 byte |
| `HKDF-SHA512` | HMAC-SHA-512 | 64 byte |

Tên thuật toán chuẩn không bảo đảm mọi provider cài đặt đều hỗ trợ. Dùng tài liệu provider và kiểm tra runtime.

### 15.1. Smoke test capability

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.KDF;
import javax.crypto.spec.HKDFParameterSpec;

static void verifyHkdfCapability() throws GeneralSecurityException {
    byte[] ikm = new byte[32];
    byte[] salt = new byte[32];
    byte[] info = "startup/self-test/v1".getBytes(StandardCharsets.UTF_8);

    try {
        KDF kdf = KDF.getInstance("HKDF-SHA256");

        var spec = HKDFParameterSpec.ofExtract()
            .addIKM(ikm)
            .addSalt(salt)
            .thenExpand(info, 32);

        byte[] output = kdf.deriveData(spec);

        try {
            if (output.length != 32) {
                throw new GeneralSecurityException(
                    "Unexpected HKDF output length");
            }
        } finally {
            Arrays.fill(output, (byte) 0);
        }
    } finally {
        Arrays.fill(ikm, (byte) 0);
        Arrays.fill(salt, (byte) 0);
    }
}
~~~

Đây là smoke test cấu hình, không phải bằng chứng đầy đủ về provider, HSM, interoperability hay độ an toàn của giao thức. Trong production, test với **loại key thật** (ví dụ non-extractable key) và provider thật ở môi trường staging hoặc integration test được bảo vệ.

### 15.2. Xác minh provider sau phép derive

~~~java
KDF kdf = KDF.getInstance("HKDF-SHA256");
SecretKey key = kdf.deriveKey("AES", spec);

// Đọc provider sau lần derive đầu tiên.
String providerName = kdf.getProviderName();
System.out.println("KDF provider: " + providerName);
~~~

Nếu chính sách yêu cầu provider cụ thể, hãy chỉ định provider trong `getInstance` thay vì chỉ log provider được chọn theo cấu hình hiện tại.

## 16. Kiểm thử theo RFC 5869

Một test tốt nên xác minh kết quả với vector chuẩn, thay vì chỉ kiểm tra API trả về một object không null. RFC 5869 có các test vector cho HKDF-SHA256.

Ví dụ dưới đây dùng **Test Case 1** của RFC 5869, với IKM 22 byte `0x0b`, salt, `info` và output length 42 byte. Test sử dụng `deriveData()` vì mục tiêu là so sánh raw output với vector công khai.

~~~java
import java.util.Arrays;
import java.util.HexFormat;

import javax.crypto.KDF;
import javax.crypto.spec.HKDFParameterSpec;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;

class HkdfRfc5869Test {

    @Test
    void matchesRfc5869Sha256TestCase1() throws Exception {
        byte[] ikm = new byte[22];
        Arrays.fill(ikm, (byte) 0x0b);

        byte[] salt = HexFormat.of().parseHex(
            "000102030405060708090a0b0c");

        byte[] info = HexFormat.of().parseHex(
            "f0f1f2f3f4f5f6f7f8f9");

        byte[] expected = HexFormat.of().parseHex(
            "3cb25f25faacd57a90434f64d0362f2a" +
            "2d2d0a90cf1a5a4c5db02d56ecc4c5bf" +
            "34007208d5b887185865");

        byte[] actual = null;

        try {
            KDF hkdf = KDF.getInstance("HKDF-SHA256");

            var spec = HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, 42);

            actual = hkdf.deriveData(spec);

            assertArrayEquals(expected, actual);
        } finally {
            Arrays.fill(ikm, (byte) 0);
            if (actual != null) {
                Arrays.fill(actual, (byte) 0);
            }
        }
    }
}
~~~

Vector này là dữ liệu kiểm thử công khai, không phải khóa production. Không dùng vector cố định để mã hóa dữ liệu thật. Trong test, `expected`, salt và `info` không phải bí mật; có thể giữ nguyên để đối chiếu.

### 16.1. Kiểm tra domain separation

Với cùng IKM và salt, hai `info` khác nhau phải tạo đầu ra khác nhau theo HKDF. Có thể viết thêm test dẫn xuất hai key hoặc raw outputs rồi so sánh bằng `MessageDigest.isEqual(...)`. Không in output để xem sự khác nhau; chỉ assert trong test.

### 16.2. Test lỗi provider

~~~java
import java.security.NoSuchAlgorithmException;
import java.security.NoSuchProviderException;

import javax.crypto.KDF;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class KdfProviderFailureTest {

    @Test
    void unsupportedKdfAlgorithmFailsClearly() {
        assertThrows(
            NoSuchAlgorithmException.class,
            () -> KDF.getInstance("NO-SUCH-KDF-FOR-TEST"));
    }

    @Test
    void missingProviderFailsClearly() {
        assertThrows(
            NoSuchProviderException.class,
            () -> KDF.getInstance(
                "HKDF-SHA256",
                "NoSuchProviderForTest"));
    }
}
~~~

Đây là test negative path trên một JDK test environment bình thường. Nếu hệ thống cài provider custom dùng chính tên test đó, hãy chọn tên provider giả định chắc chắn không được cài đặt trong môi trường test.

## 17. Xử lý lỗi tham số và dữ liệu đầu vào

Một số lỗi có thể phát hiện trước khi gọi provider:

- IKM null hoặc salt null khi code yêu cầu dữ liệu bắt buộc.
- Output length bằng 0 hoặc âm.
- Output length vượt giới hạn HKDF.
- `info` không được chuẩn hóa hoặc không khớp protocol.
- `SecretKey` đầu vào không phù hợp với provider.
- Output algorithm không hợp lệ hoặc provider không hỗ trợ.

Ví dụ kiểm tra độ dài:

~~~java
static void validateLength(int length) {
    if (length <= 0) {
        throw new IllegalArgumentException(
            "Derived output length must be positive");
    }
}
~~~

Không nên tự mã hóa toàn bộ quy tắc provider vào một validator chung. Một số kiểm tra phụ thuộc hash length, kiểu key hoặc provider cụ thể; để implementation chuẩn thực hiện kiểm tra cuối cùng và giữ exception gốc.

### 17.1. Không chuyển lỗi cấu hình thành lỗi dữ liệu người dùng

`NoSuchAlgorithmException` thường biểu thị cấu hình/deployment không hỗ trợ thuật toán. Không trả HTTP 400 cho người dùng cuối như thể họ gửi sai request. Tách rõ:

- Lỗi input của ứng dụng: tham số nghiệp vụ không hợp lệ.
- Lỗi thuật toán/provider: cấu hình hoặc capability của môi trường.
- Lỗi lifecycle: key không thể sử dụng/hủy theo chính sách.
- Lỗi protocol: hai bên không thống nhất salt, info, output length hoặc thuật toán.

Việc phân loại giúp vận hành điều tra đúng nguyên nhân và không tiết lộ chi tiết provider cho client.

## 18. Chính sách dữ liệu nhạy cảm và logging

| Dữ liệu | Ghi log? | Gợi ý |
| --- | --- | --- |
| Tên thuật toán KDF | Có thể | `HKDF-SHA256` |
| Provider name | Có thể theo policy | Hữu ích cho audit cấu hình |
| Output length | Có thể | Chỉ ghi số byte, không ghi bytes |
| IKM / PRK | Không | Bí mật mật mã |
| Raw key / `SecretKey.getEncoded()` | Không | Có thể làm lộ khóa trực tiếp |
| Salt | Thường không bí mật, nhưng theo policy | Không log nếu liên kết với định danh nhạy cảm |
| `info` | Tùy nội dung | Tránh đưa PII/secret vào context |
| Exception type | Có thể | Phân loại lỗi provider |
| Exception message | Có chọn lọc | Kiểm tra không chứa dữ liệu bí mật |
| Request ID | Có thể theo policy | Dùng correlation, không phải secret |

Không tạo metric label từ key ID có cardinality không giới hạn hoặc từ dữ liệu nhạy cảm. Với audit, ghi **key alias/version** do KMS/HSM quản lý, algorithm, provider, operation và outcome theo schema an toàn. Không ghi key bytes hoặc shared secret.

## 19. Triển khai với HSM/KMS và provider bên thứ ba

Khi hệ thống dùng HSM/KMS:

1. Key có thể tồn tại dưới dạng handle thay vì raw bytes.
2. `SecretKey.getEncoded()` có thể trả `null`.
3. Provider phải hỗ trợ KDF operation với loại key handle và parameter cụ thể.
4. Delayed provider selection giúp chọn implementation có khả năng xử lý key material đầu vào.
5. Provider name/version và firmware/HSM policy có thể ảnh hưởng capability.
6. Key export policy có thể cấm `deriveData()` nhưng cho phép `deriveKey()`.
7. Cần test trên đúng HSM partition/tenant/policy được deploy.

Không giả định provider hỗ trợ HKDF chỉ vì nó hỗ trợ AES hoặc HMAC. KDF là một service type riêng; phải kiểm tra đúng service `KDF` và thực hiện phép derive thực tế.

### Checklist tích hợp provider

- [ ] Provider đã được cài và đăng ký trong môi trường chạy.
- [ ] Provider hỗ trợ tên KDF cụ thể.
- [ ] Provider chấp nhận `HKDFParameterSpec`/parameter set cần dùng.
- [ ] Provider xử lý được loại IKM (byte array hoặc `SecretKey` handle).
- [ ] Provider hỗ trợ output key algorithm/length cần thiết.
- [ ] Export policy tương thích với việc dùng `deriveKey` hay `deriveData`.
- [ ] Provider selection đúng theo chính sách, không dựa vào thứ tự mặc định không kiểm soát.
- [ ] Test thành công trong môi trường staging tương đương production.
- [ ] Không có fallback sang provider/algorithm yếu hơn khi lỗi.
- [ ] Có quy trình rotate key, cập nhật provider và khôi phục khi HSM/KMS không sẵn sàng.

## 20. Quy trình vận hành vòng đời key

Một quy trình có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A[Nhận IKM từ nguồn tin cậy] --> B[Validate nguồn và protocol context]
    B --> C[Chọn KDF algorithm/provider]
    C --> D[Build HKDF parameters]
    D --> E[Derive SecretKey]
    E --> F[Đưa key vào Cipher/Mac]
    F --> G[Hoàn tất operation]
    G --> H[Destroy/release key theo provider]
    H --> I[Clear arrays do ứng dụng sở hữu]
    I --> J[Audit metadata, không ghi bí mật]
~~~

### 20.1. Khi nào lưu metadata?

Để tái tạo hoặc giải mã dữ liệu đã lưu, ứng dụng có thể cần lưu metadata như:

- Algorithm/KDF name và version của quy ước `info`.
- Salt.
- Key alias hoặc key version từ KMS/HSM.
- Nonce/IV và các tham số mã hóa liên quan.
- Identifier của protocol hoặc purpose label.

Không cần lưu IKM hoặc PRK dạng plaintext chỉ để “đảm bảo tái tạo”. Nguồn key gốc phải được quản lý bằng key store/KMS/HSM hoặc một cơ chế bảo vệ phù hợp.

### 20.2. Rotation và versioning

Khi đổi KDF algorithm, provider hoặc cách encode `info`, đừng âm thầm thay đổi cho dữ liệu cũ. Lưu metadata version để biết cách derive/decrypt tương ứng. Quy trình rotation nên:

1. Dẫn xuất key mới với context/version mới.
2. Ghi dữ liệu mới bằng key mới.
3. Giữ khả năng đọc dữ liệu cũ trong thời gian migration nếu yêu cầu nghiệp vụ.
4. Re-encrypt hoặc migrate dữ liệu cũ theo kế hoạch.
5. Thu hồi key cũ sau khi hết retention và xác minh không còn consumer.
6. Theo dõi lỗi provider và key version trong giai đoạn chuyển tiếp.

## 21. Các lỗi thiết kế thường gặp

### 21.1. Dùng HKDF cho mật khẩu

HKDF không có cơ chế làm chậm brute-force password guessing. Dùng password hashing/KDF chuyên dụng thay thế.

### 21.2. Dùng IKM có entropy thấp

KDF không tạo thêm entropy. Dùng nguồn key material có chất lượng mật mã và xác thực phù hợp.

### 21.3. Dùng cùng info cho nhiều mục đích

Có thể dẫn tới tái sử dụng cùng key material cho encryption và authentication. Tách `info` theo purpose, protocol và version.

### 21.4. Log getEncoded() để debug

Đây là rò rỉ key material. Chỉ log metadata không nhạy cảm.

### 21.5. Giả định Arrays.fill() xóa mọi bản sao

Builder có thể clone array; provider có thể giữ bản sao trong heap/native memory/hardware. Xóa bản sao do ứng dụng sở hữu và dùng provider lifecycle, nhưng không tuyên bố zeroization tuyệt đối.

### 21.6. Gọi getProviderName() trước khi derive

Có thể kích hoạt delayed provider selection trước khi provider thấy key material thực tế. Derive trước, kiểm tra provider sau.

### 21.7. Chia sẻ KDF/Builder giữa các thread

API không cam kết thread-safe. Tạo instance riêng cho task hoặc đồng bộ hóa có chủ đích.

### 21.8. Fallback âm thầm khi provider lỗi

Có thể khiến hệ thống dùng thuật toán/provider không được phê duyệt. Fail closed và xử lý như lỗi cấu hình/availability.

### 21.9. Giả định SecretKey luôn export được

HSM/KMS có thể trả key không extractable. Giữ `SecretKey` handle và chọn provider có khả năng xử lý.

### 21.10. Dùng deriveData() dù consumer nhận SecretKey

Không cần tạo raw byte copy nếu API tiếp theo nhận `SecretKey`. Ưu tiên `deriveKey()`.

## 22. Bài tập thực hành và tiêu chí nghiệm thu

### Bài tập A — dẫn xuất AES key

Tạo IKM và salt giả lập bằng `SecureRandom`, dùng HKDF-SHA256 để dẫn xuất `SecretKey` AES 32 byte. Không in key bytes.

**Đạt khi:** key algorithm là AES, chiều dài đúng theo test provider hỗ trợ, không có secret trong log.

### Bài tập B — domain separation

Dùng cùng IKM/salt nhưng hai `info` khác nhau cho encryption và authentication. Dẫn xuất hai key và kiểm tra chúng khác nhau trong test.

**Đạt khi:** hai purpose không dùng chung output key material; `info` có encoding ổn định và version.

### Bài tập C — so sánh deriveKey và deriveData

Dùng `deriveKey()` để nhận `SecretKey`, sau đó thử `deriveData()` trong test provider hỗ trợ. Giải thích khi nào raw bytes không thể export từ HSM.

**Đạt khi:** code production không cần `getEncoded()` chỉ để truyền key cho `Cipher`/`Mac`.

### Bài tập D — kiểm thử provider failure

Tạo test cho KDF name không tồn tại, provider name không tồn tại và HKDF parameter length không hợp lệ. Kiểm tra exception type.

**Đạt khi:** phân biệt lỗi thuật toán, lỗi provider và lỗi tham số; không fallback sang key mặc định.

### Bài tập E — kiểm tra lifecycle

Tạo key, dùng trong một thao tác thử nghiệm, gọi `destroy()` và xử lý `DestroyFailedException`. Xóa byte arrays do ứng dụng sở hữu trong `finally`.

**Đạt khi:** không log/serialize key, giải thích giới hạn zeroization và bản sao nội bộ.

### Bài tập F — HSM/provider capability

Liệt kê provider có service `KDF.HKDF-SHA256`, thực hiện một derive test với key material đúng loại và kiểm tra provider được chọn sau derive.

**Đạt khi:** xác nhận capability thực tế, không chỉ dựa vào tên provider hoặc một service entry.

### Checklist hoàn thành

- [ ] Hiểu vai trò IKM, salt, PRK, `info` và OKM.
- [ ] Dùng KDF API chính thức của Java 25, không bật preview.
- [ ] Dùng HKDF-SHA256/384/512 theo tên thuật toán chuẩn và provider hỗ trợ.
- [ ] Phân biệt `KDFParameters` với `HKDFParameterSpec`.
- [ ] Chọn `deriveKey()` khi consumer chấp nhận `SecretKey`.
- [ ] Tạo `info` riêng cho từng application/protocol/purpose.
- [ ] Không dùng HKDF để lưu mật khẩu người dùng.
- [ ] Không export/log/serialize IKM, PRK hoặc output key.
- [ ] Có lifecycle cho byte array và `SecretKey.destroy()` theo provider.
- [ ] Không giả định mọi key đều extractable hoặc mọi provider hỗ trợ cùng tham số.
- [ ] Hiểu delayed provider selection và giới hạn thread safety.
- [ ] Có RFC 5869 vector test, negative provider tests và staging capability test.
- [ ] Có chính sách fail closed, rotation và audit metadata an toàn.

## 23. Tài liệu tham khảo chính thức

1. [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510): API KDF được hoàn thiện trong Java 25; tiền thân preview ở Java 24 không còn là trạng thái áp dụng cho JDK 25.
2. [Java SE 25 API — `javax.crypto.KDF`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html): `getInstance`, `deriveKey`, `deriveData`, delayed provider selection và concurrency.
3. [Java SE 25 API — `HKDFParameterSpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html): Extract/Expand, Builder, IKM, salt, info và output length.
4. [Java SE 25 API — `HKDFParameterSpec.Builder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.Builder.html): `addIKM`, `addSalt`, `extractOnly`, `thenExpand` và thread safety.
5. [Java SE 25 API — `SecretKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/SecretKey.html): `Destroyable`, `getEncoded` và lifecycle của key.
6. [Oracle Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html): HKDF, KDF provider, cách dẫn xuất key bằng JCA.
7. [Java Security Standard Algorithm Names — KDF](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên `HKDF-SHA256`, `HKDF-SHA384`, `HKDF-SHA512`.
8. [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869.html): đặc tả HKDF, vai trò salt/info và test vectors.

**Kết quả mong đợi:** người học không chỉ gọi được `KDF.deriveKey()`, mà còn kiểm soát được nguồn IKM, context `info`, output key, provider, lỗi và thời điểm giải phóng dữ liệu nhạy cảm. Một triển khai tốt dùng KDF chuẩn với provider được kiểm tra, giữ khóa trong `SecretKey` khi có thể, hạn chế bản sao raw bytes, và không để lỗi provider dẫn tới một cơ chế fallback yếu hơn.
