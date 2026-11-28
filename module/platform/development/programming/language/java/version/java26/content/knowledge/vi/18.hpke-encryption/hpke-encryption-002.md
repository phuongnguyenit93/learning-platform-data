# Quan hệ giữa KEM, KDF và AEAD

Hybrid Public Key Encryption (HPKE) kết hợp ba primitive mật mã thành một bộ mã hóa khóa công khai hoàn chỉnh: **KEM** tạo shared secret giữa người gửi và người nhận, **KDF** biến shared secret thành các khóa và nonce theo ngữ cảnh, còn **AEAD** dùng khóa đối xứng đó để mã hóa và xác thực từng thông điệp. Ba thành phần này bổ sung cho nhau; không thành phần nào tự thay thế được hai thành phần còn lại.

Trong Java 26, có thể dùng trực tiếp `Cipher.getInstance("HPKE")` cùng `HPKEParameterSpec` để thực hiện RFC 9180. JDK quản lý KEM encapsulation/decapsulation, key schedule HKDF, AEAD và bộ đếm nonce trong một HPKE context. Đây là API Java SE ổn định, có từ Java 26, không phải preview hay incubator. RFC 9180 là tài liệu Informational của IRTF, không phải Internet Standards Track; nó định nghĩa ciphersuite và hành vi mà API HPKE của JDK triển khai. [JDK 26 Release Notes — Hybrid Public Key Encryption](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) · [Java 26 `HPKEParameterSpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html) · [Java Cryptography Architecture Reference Guide — HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html) · [RFC 9180 status](https://www.rfc-editor.org/rfc/rfc9180.html).

## 1. HPKE ghép ba primitive như thế nào?

Một HPKE ciphersuite là bộ ba `(KEM, KDF, AEAD)`. Mỗi thành phần có một nhiệm vụ riêng:

| Thành phần | Đầu vào chính | Đầu ra | Vai trò |
|---|---|---|---|
| **KEM — Key Encapsulation Mechanism** | Public key của người nhận; phía người nhận dùng private key tương ứng. | Một shared secret và một encapsulation message `enc`. | Thiết lập bí mật chung qua kênh không an toàn mà không gửi shared secret trực tiếp. |
| **KDF — Key Derivation Function** | Shared secret, tùy chọn PSK, `info` và ngữ cảnh ciphersuite. | AEAD key, base nonce và exporter secret. | Dẫn xuất khóa đúng kích thước, tách biệt theo mục đích và gắn với ngữ cảnh ứng dụng. |
| **AEAD — Authenticated Encryption with Associated Data** | Khóa, nonce, plaintext và AAD. | Ciphertext kèm authentication tag. | Mã hóa nội dung và phát hiện dữ liệu bị sửa đổi. |

Luồng cơ bản:

```text
NGƯỜI GỬI                                             NGƯỜI NHẬN
public key của người nhận                             private key của người nhận
        |                                                       |
        v                                                       |
KEM.Encap(pkR)                                                  |
  |                                                             |
  +--> shared_secret                                            |
  +--> enc (public encapsulation message) --------------------->|
        |                                                       v
        |                                                KEM.Decap(enc, skR)
        |                                                       |
        +---------------- shared_secret <-----------------------+
        |                                                       |
        v                                                       v
        KDF / HPKE key schedule (cùng suite, info, mode, PSK)
        |                                                       |
        +--> AEAD key                                           +--> AEAD key
        +--> base_nonce                                         +--> base_nonce
        +--> exporter_secret                                    +--> exporter_secret
        |                                                       |
        v                                                       v
AEAD.Seal(key, nonce, aad, plaintext)                 AEAD.Open(key, nonce, aad, ciphertext)
        |                                                       |
        +--> ciphertext + tag --------------------------------->+
                                                                |
                                                                v
                                                         plaintext đã xác thực
```

Người gửi chuyển `enc` cùng ciphertext cho người nhận. `enc` không phải private key, không phải shared secret và cũng không phải ciphertext của thông điệp. Nó là dữ liệu công khai để người nhận dùng private key của mình khôi phục cùng shared secret.

KDF đảm bảo cả hai phía dẫn xuất được cùng khóa và nonce từ shared secret cùng các tham số giống nhau. AEAD sau đó xử lý từng thông điệp. HPKE không gửi khóa AES trực tiếp qua mạng.

## 2. KEM: tạo shared secret mà không gửi bí mật

KEM giải quyết bước thiết lập bí mật chung. Với DHKEM dùng X25519, có thể hình dung quá trình như sau:

1. Người nhận đã có cặp khóa `(skR, pkR)` và công bố `pkR` qua một kênh mà người gửi có thể xác minh.
2. Người gửi tạo cặp khóa ephemeral `(skE, pkE)` mới.
3. Người gửi tính Diffie-Hellman giữa `skE` và `pkR`, sau đó áp dụng bước Extract-and-Expand bên trong DHKEM để tạo `shared_secret`.
4. Người gửi serialize `pkE` thành encapsulation message `enc` và gửi `enc` cho người nhận.
5. Người nhận dùng `skR` và `enc` để tính lại cùng shared secret.

```text
Người gửi:  DH(skE, pkR) -> KEM internal KDF -> shared_secret
             pkE        -> serialize       -> enc

Người nhận: DH(skR, pkE lấy từ enc) -> KEM internal KDF -> shared_secret
```

KEM chỉ thiết lập shared secret. Nó không mã hóa payload có kích thước tùy ý và không tạo authentication tag cho thông điệp. Phần mã hóa nội dung thuộc AEAD.

### `enc` là dữ liệu công khai cần truyền

Người nhận cần có `enc` để decapsulate. Với DHKEM, encapsulation thường chứa public key ephemeral của người gửi. Dữ liệu này không cần giữ bí mật, nhưng phải được chuyển nguyên vẹn và gắn đúng với ciphertext/context. Nếu ứng dụng hỗ trợ nhiều recipient key, envelope cần có key identifier hoặc phiên bản khóa để người nhận chọn đúng private key.

Không nhầm `enc` với AEAD nonce. Trong Java HPKE, `senderCipher.getIV()` trả về **KEM encapsulation message** theo hợp đồng của `HPKEParameterSpec`; đây không phải nonce AES-GCM mà ứng dụng phải tự quản lý.

### KEM trong Java

Java có API độc lập `javax.crypto.KEM` từ Java 21 (JEP 452) để encapsulate/decapsulate khóa. Java 26 bổ sung HPKE Cipher hoàn chỉnh. Khi dùng `Cipher.getInstance("HPKE")`, ứng dụng không cần gọi `KEM.getInstance(...)` rồi tự nối các bước KDF và AEAD. Cipher HPKE thực hiện toàn bộ RFC 9180 theo ciphersuite được chọn.

## 3. KDF: biến shared secret thành khóa dùng được

Shared secret từ KEM là nguyên liệu đầu vào cho key schedule. Không nên lấy vài byte đầu của shared secret rồi dùng trực tiếp làm khóa AES. KDF dẫn xuất khóa theo kích thước cần thiết, đồng thời gắn kết quả với thuật toán, mode và ngữ cảnh của ứng dụng.

RFC 9180 dùng HKDF (HMAC-based Extract-and-Expand Key Derivation Function). Hai giai đoạn chính:

- **Extract:** nhận input keying material (IKM) và salt, tạo pseudorandom key (PRK) có kích thước cố định.
- **Expand:** nhận PRK, context `info` và độ dài yêu cầu, tạo output keying material có kích thước cần thiết.

Trong HPKE key schedule, KDF dẫn xuất tối thiểu:

| Giá trị | Công dụng |
|---|---|
| `key` | Khóa AEAD dùng mã hóa/giải mã thông điệp. |
| `base_nonce` | Giá trị gốc để tạo nonce riêng cho từng thông điệp trong context. |
| `exporter_secret` | Bí mật gốc cho ứng dụng cần export thêm dữ liệu khóa theo exporter context được quy định. |

`exporter_secret` là một phần của HPKE context theo RFC 9180. Java 26 `HPKEParameterSpec` không cung cấp accessor để đọc trực tiếp giá trị này; không tự tái tạo key schedule bên ngoài HPKE Cipher chỉ để lấy nó. Nếu ứng dụng cần HPKE exporter, hãy xác minh API/provider có hỗ trợ chức năng đó hoặc dùng implementation HPKE đã được kiểm thử theo RFC.

KDF còn đưa mode, PSK identifier và `info` vào key schedule context. Vì thế, hai bên phải thống nhất ciphersuite, mode, PSK/PSK ID và `info`; khác một tham số có thể làm hai bên dẫn xuất khóa khác nhau và giải mã thất bại.

### Tại sao DHKEM có HKDF trong tên, trong khi ciphersuite còn chọn một KDF nữa?

Đây là điểm dễ nhầm nhất khi đọc tên thuật toán:

```text
KEM identifier: DHKEM(X25519, HKDF-SHA256)
                         |
                         +-- HKDF dùng bên trong DHKEM để xử lý DH output

HPKE KDF identifier: HKDF-SHA256
                         |
                         +-- HKDF dùng trong HPKE key schedule để dẫn xuất
                             AEAD key, base_nonce và exporter_secret
```

Đó là hai vai trò KDF khác nhau, dù cùng dùng HKDF-SHA256. RFC 9180 sử dụng `suite_id` và các nhãn tách miền (domain separation): lời gọi KDF bên trong KEM được gắn với miền `KEM`, còn key schedule tổng thể gắn với miền `HPKE` và toàn bộ ciphersuite. Nhờ vậy, dữ liệu đầu vào của hai mục đích không bị trộn lẫn chỉ vì dùng chung thuật toán HKDF.

### `info` gắn khóa với ngữ cảnh ứng dụng

`info` là dữ liệu ứng dụng cung cấp để ràng buộc key schedule vào một giao thức hoặc mục đích cụ thể, ví dụ tên protocol, phiên bản message format hay định danh luồng nghiệp vụ. Hai phía phải dùng đúng cùng byte sequence.

`info` không phải AAD và không phải một thông điệp bí mật được mã hóa. Nó tham gia dẫn xuất khóa; nếu hai bên dùng giá trị khác nhau, khóa dẫn xuất khác nhau. Java 26 `HPKEParameterSpec.withInfo(byte[])` yêu cầu mảng không rỗng; RFC 9180 khuyến nghị giới hạn `info` tối đa 64 byte để tương thích.

## 4. AEAD: mã hóa và xác thực từng thông điệp

AEAD nhận khóa đối xứng do KDF dẫn xuất, nonce của thông điệp, plaintext và optional Additional Authenticated Data (AAD). Nó tạo ciphertext cùng authentication tag. Khi giải mã, AEAD kiểm tra tag trước khi chấp nhận plaintext.

| Đầu vào | Có bí mật không? | Vai trò |
|---|---|---|
| AEAD key | Có. | Bảo vệ nội dung và tính toàn vẹn. |
| Nonce | Không cần giữ bí mật. | Phân biệt mỗi lần mã hóa dưới cùng khóa; phải duy nhất theo yêu cầu của AEAD. |
| Plaintext | Có thể chứa dữ liệu bí mật. | Nội dung được mã hóa. |
| AAD | Không được mã hóa. | Được xác thực cùng ciphertext, ví dụ header, loại message hoặc phiên bản protocol. |
| Ciphertext + tag | Có thể truyền qua mạng công khai. | Dữ liệu đã mã hóa; tag cho phép phát hiện sửa đổi. |

AAD không bị mã hóa, nên người quan sát vẫn đọc được AAD. Nếu AAD thay đổi hoặc ciphertext/tag bị sửa, xác thực AEAD thất bại. Không được xử lý plaintext như dữ liệu hợp lệ khi thao tác giải mã báo lỗi xác thực.

### Nonce được HPKE context quản lý

RFC 9180 tạo nonce cho mỗi message từ `base_nonce` và sequence number của context. Trong Java 26, HPKE Cipher tự quản lý sequence counter và dùng nonce riêng cho mỗi lần `doFinal`. Vì vậy, ứng dụng không truyền IV/nonce thủ công như khi dùng trực tiếp `AES/GCM/NoPadding`.

Không tái sử dụng cùng HPKE context theo cách làm mất đồng bộ sequence number. Sender và recipient phải xử lý cùng số lượng message theo đúng thứ tự. Nếu một message bị mất, lặp lại hoặc xử lý ngoài thứ tự, hai phía có thể không còn đồng bộ nonce; giao thức ứng dụng cần quy định cách khôi phục hoặc tạo context mới.

### `EXPORT_ONLY` không phải AEAD để mã hóa payload

RFC 9180 định nghĩa một identifier `EXPORT_ONLY` cho trường hợp chỉ cần exporter secret. Nó không cung cấp thao tác `Seal`/`Open` để mã hóa thông điệp. Nếu mục tiêu là mã hóa payload, chọn AEAD như AES-GCM hoặc ChaCha20-Poly1305.

## 5. Ciphersuite: chọn đúng cả ba thành phần

Một ciphersuite HPKE là bộ ba KEM, KDF và AEAD. Các bên phải thống nhất cùng identifier. Chỉ đổi một thành phần có thể làm key schedule và kết quả mã hóa khác nhau.

Java 26 `HPKEParameterSpec` định nghĩa các identifier theo RFC 9180:

| Nhóm | Constant trong Java | Thuật toán |
|---|---|---|
| KEM | `KEM_DHKEM_X25519_HKDF_SHA256` | DHKEM với X25519 và HKDF-SHA256 bên trong KEM. |
| KEM | `KEM_DHKEM_X448_HKDF_SHA512` | DHKEM với X448 và HKDF-SHA512 bên trong KEM. |
| KEM | `KEM_DHKEM_P_256_HKDF_SHA256` | DHKEM với NIST P-256. |
| KEM | `KEM_DHKEM_P_384_HKDF_SHA384` | DHKEM với NIST P-384. |
| KEM | `KEM_DHKEM_P_521_HKDF_SHA512` | DHKEM với NIST P-521. |
| KDF | `KDF_HKDF_SHA256` | HKDF-SHA256 cho HPKE key schedule. |
| KDF | `KDF_HKDF_SHA384` | HKDF-SHA384 cho HPKE key schedule. |
| KDF | `KDF_HKDF_SHA512` | HKDF-SHA512 cho HPKE key schedule. |
| AEAD | `AEAD_AES_128_GCM` | AES-128-GCM. |
| AEAD | `AEAD_AES_256_GCM` | AES-256-GCM. |
| AEAD | `AEAD_CHACHA20_POLY1305` | ChaCha20-Poly1305. |
| AEAD | `EXPORT_ONLY` | Chỉ dùng exporter secret, không mã hóa payload. |

Oracle JDK 26 Release Notes cho biết implementation JDK hỗ trợ các KEM, KDF và AEAD identifiers được định nghĩa trong RFC 9180. Tuy nhiên, Javadoc `HPKEParameterSpec` cho phép một HPKE Cipher implementation khác chỉ hỗ trợ một phần hoặc không hỗ trợ các identifier đó. Ứng dụng cần kiểm tra provider/JDK thực tế và kiểm thử interoperability với đầu bên kia.

Không tự chọn ciphersuite bằng cách ghép tùy ý các thuật toán chỉ vì tên constant tồn tại. Hãy chọn một suite được RFC định nghĩa, được provider hỗ trợ và được chính sách bảo mật của hệ thống chấp nhận.

## 6. Bốn HPKE mode và ý nghĩa xác thực

RFC 9180 định nghĩa bốn mode. `HPKEParameterSpec.of(kemId, kdfId, aeadId)` tạo cấu hình mặc định ở **Base mode**.

| Mode | Thông tin bổ sung | Điều người nhận có thể xác nhận |
|---|---|---|
| **Base** | Chỉ cần public key của người nhận. | Nội dung chỉ có thể giải mã bởi bên giữ private key tương ứng; không xác thực danh tính người gửi. |
| **PSK** | Cả hai bên có cùng pre-shared key và `psk_id`. | Người gửi biết PSK đã được provision cho nhóm giao tiếp. |
| **Auth** | Người gửi dùng private key xác thực; người nhận có public key tương ứng. | Người gửi chứng minh possession của asymmetric private key theo KEM authenticated mode. |
| **AuthPSK** | Cả PSK và asymmetric authentication key. | Kết hợp xác thực bằng PSK và asymmetric key. |

Trong Java:

- Base: dùng `HPKEParameterSpec.of(...)`.
- PSK: gọi thêm `.withPsk(psk, pskId)` ở cả hai phía.
- Auth: gọi thêm `.withAuthKey(...)`; sender truyền private key của chính mình, recipient truyền public key của sender.
- AuthPSK: dùng cả `.withPsk(...)` và `.withAuthKey(...)` theo đúng vai trò của từng phía.

Không phải KEM nào cũng hỗ trợ Auth/AuthPSK. `withAuthKey` tạo parameter spec nhưng không đảm bảo KEM/provider hỗ trợ mode đó; lỗi có thể xuất hiện khi khởi tạo Cipher dưới dạng `InvalidAlgorithmParameterException`.

### PSK phải là khóa ngẫu nhiên mạnh, không phải password

RFC 9180 yêu cầu PSK có ít nhất 32 byte entropy. `HPKEParameterSpec.withPsk` trong Java 26 cũng từ chối khóa ngắn hơn 32 byte và `psk_id` rỗng; RFC khuyến nghị giới hạn kích thước khóa và identifier tối đa 64 byte để tương thích. Không dùng chuỗi mật khẩu người dùng trực tiếp làm PSK. Nếu nguồn gốc là password, phải có quy trình password-based KDF riêng được thiết kế và cấu hình đúng trước khi dùng như secret key; không tự băm password một lần.

Base mode không chứng minh ai đã gửi ciphertext. Nếu ứng dụng cần sender identity, phải chọn mode xác thực phù hợp hoặc dùng một cơ chế xác thực độc lập. Dù ở Auth mode, public key của sender vẫn cần được xác minh và gắn với danh tính theo chính sách của ứng dụng.

## 7. Java 26 HPKE Cipher: API và cách cấu hình

Java 26 cung cấp:

- `Cipher.getInstance("HPKE")`: tạo HPKE Cipher. Không dùng transformation dạng `algorithm/mode/padding`; tên chuẩn là một chuỗi duy nhất `HPKE`.
- `HPKEParameterSpec.of(kem_id, kdf_id, aead_id)`: chọn ba identifier và tạo Base mode với `info` rỗng.
- `withInfo(byte[])`: tạo parameter spec mới có application-supplied info.
- `withPsk(SecretKey, byte[])`: thêm PSK và identifier.
- `withAuthKey(AsymmetricKey)`: thêm asymmetric authentication key.
- `withEncapsulation(byte[])`: cung cấp `enc` cho recipient.

`HPKEParameterSpec` là immutable; các `with...` method trả về object mới. Mảng byte được truyền vào `withInfo`, `withPsk` và `withEncapsulation` được sao chép để tránh việc caller sửa dữ liệu sau khi tạo spec.

### Ví dụ một thông điệp Base mode với X25519, HKDF-SHA256 và AES-128-GCM

Ví dụ dùng cùng một tiến trình để mô phỏng hai vai trò. Trong hệ thống thật, public key của recipient được provision trước; `enc` và ciphertext được gửi qua transport; recipient lấy private key tương ứng từ key store/HSM.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public final class HpkeExample {
    public static void main(String[] args) throws GeneralSecurityException {
        // Recipient tạo key pair; public key được cung cấp cho sender.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        byte[] info = "example.invoice.v1".getBytes(StandardCharsets.UTF_8);
        byte[] aad = "type=invoice;version=1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Invoice #1042: total=250000".getBytes(StandardCharsets.UTF_8);

        // Sender: KEM + KDF + AEAD được HPKE Cipher thực hiện nội bộ.
        Cipher sender = Cipher.getInstance("HPKE");
        HPKEParameterSpec senderSpec = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM)
                .withInfo(info);

        sender.init(Cipher.ENCRYPT_MODE, recipientKeys.getPublic(), senderSpec);

        // Đây là KEM encapsulation message, không phải AEAD nonce.
        byte[] enc = sender.getIV();

        // AAD được xác thực nhưng không được mã hóa.
        sender.updateAAD(aad);
        byte[] ciphertext = sender.doFinal(plaintext);

        // Transport cần chuyển enc và ciphertext tới recipient.
        // Trong ứng dụng thật, envelope còn mang key ID và suite/version theo giao thức.

        // Recipient: dùng cùng suite + info và encapsulation do sender gửi.
        Cipher recipient = Cipher.getInstance("HPKE");
        HPKEParameterSpec recipientSpec = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM)
                .withInfo(info)
                .withEncapsulation(enc);

        recipient.init(Cipher.DECRYPT_MODE, recipientKeys.getPrivate(), recipientSpec);
        recipient.updateAAD(aad);
        byte[] recovered = recipient.doFinal(ciphertext);

        if (!Arrays.equals(plaintext, recovered)) {
            throw new IllegalStateException("HPKE round trip failed");
        }
    }
}
```

Các điểm quan trọng trong ví dụ:

1. Sender khởi tạo Cipher bằng public key của recipient và `ENCRYPT_MODE`.
2. Recipient khởi tạo Cipher bằng private key của chính mình và `DECRYPT_MODE`.
3. Hai bên dùng cùng KEM/KDF/AEAD identifiers và cùng `info`.
4. Sender lấy `enc` bằng `getIV()` rồi gửi cho recipient.
5. Recipient truyền `enc` vào `withEncapsulation(...)` để decapsulate shared secret.
6. Hai phía cung cấp cùng AAD trước `doFinal`.
7. Không có đoạn mã tự tạo AES key, nonce hay tự gọi HKDF; HPKE Cipher quản lý key schedule và AEAD context.

### `info` khác AAD như thế nào?

| Thuộc tính | `info` | AAD |
|---|---|---|
| Thời điểm được dùng | Trong HPKE key schedule khi tạo context. | Trong từng thao tác AEAD cho message. |
| Ảnh hưởng | Thay đổi khóa/nonce được dẫn xuất. | Không thay khóa; ràng buộc dữ liệu metadata vào authentication tag. |
| Mục tiêu | Ràng buộc context với protocol, phiên bản hoặc mục đích. | Xác thực header/metadata của một message cụ thể. |
| Phải khớp hai phía? | Có. | Có, cho từng message. |
| Có được mã hóa không? | Không phải payload; nó là đầu vào KDF. | Không; AAD được giữ nguyên khi truyền nhưng được xác thực. |

Ví dụ, `info` có thể là chuỗi cố định `example.invoice.v1`, trong khi AAD cho từng message có thể chứa `tenant=42`, loại message hoặc sequence ID. Không đưa dữ liệu bí mật vào AAD với kỳ vọng nó được che giấu.

## 8. Trao đổi nhiều thông điệp trong cùng HPKE context

Sau khi khởi tạo, sender và recipient có thể gọi nhiều lần `doFinal`. Mỗi lần sender mã hóa một message hoàn chỉnh; HPKE dùng sequence counter nội bộ để tạo nonce khác nhau. Recipient cần gọi đúng số lần và đúng thứ tự tương ứng với các ciphertext từ sender.

```java
// Sender context đã init một lần
sender.updateAAD(aad1);
byte[] ciphertext1 = sender.doFinal(message1);

sender.updateAAD(aad2);
byte[] ciphertext2 = sender.doFinal(message2);

// Recipient context đã init với cùng enc, suite và info
recipient.updateAAD(aad1);
byte[] plaintext1 = recipient.doFinal(ciphertext1);

recipient.updateAAD(aad2);
byte[] plaintext2 = recipient.doFinal(ciphertext2);
```

Trong mỗi lần `doFinal`, cung cấp AAD tương ứng với message đó trước khi xử lý ciphertext. Recipient phải giữ đúng thứ tự message; không dùng cùng context để giải mã ciphertext theo thứ tự tùy ý.

Với các message độc lập hoặc các luồng xử lý song song, nên tạo HPKE context riêng cho mỗi luồng/phiên. Không chia sẻ một Cipher đang giữ sequence state giữa nhiều thread mà không có cơ chế đồng bộ và bảo đảm thứ tự. Khi context bị mất đồng bộ, hủy context và thiết lập HPKE context mới theo giao thức ứng dụng.

## 9. Vận chuyển envelope và interoperability

HPKE chỉ quy định cách tạo encryption context và mã hóa/giải mã. Ứng dụng phải quy định cách đóng gói dữ liệu truyền. Một envelope cho một message có thể chứa:

| Trường | Mục đích |
|---|---|
| `version` | Phiên bản định dạng envelope/protocol. |
| `recipientKeyId` | Giúp recipient chọn đúng private key. |
| `kemId`, `kdfId`, `aeadId` | Chỉ rõ ciphersuite đã thống nhất. |
| `enc` | KEM encapsulation message lấy từ sender Cipher. |
| `ciphertext` | Ciphertext và tag AEAD. |
| `aad` hoặc metadata tương đương | Dữ liệu mà ứng dụng dùng để tái tạo AAD giống hệt ở recipient. |

Không nhất thiết phải truyền `info` trong envelope; hai bên có thể xác định `info` từ cấu hình protocol. Nhưng recipient phải tái tạo chính xác byte sequence đó. Nếu metadata như tenant ID hoặc message type được dùng làm AAD, cả hai bên cần tạo cùng bytes với encoding và thứ tự trường được quy định rõ.

Để interoperability:

- Hai phía phải dùng cùng algorithm identifiers.
- Hai phía phải dùng cùng `info`.
- Nếu dùng PSK, phải dùng cùng PSK và `psk_id`.
- Nếu dùng Auth, sender private key phải tương ứng với public key mà recipient sử dụng để xác thực.
- Recipient phải nhận đúng `enc` và ciphertext thuộc cùng một context.
- Hai phía phải đồng bộ thứ tự message khi tái sử dụng context.
- Phải thống nhất encoding, framing và cách tạo AAD ở tầng ứng dụng.

Không serialize Java `Cipher` hoặc `HPKEParameterSpec` để truyền qua mạng. Chỉ serialize các trường protocol đã định nghĩa như suite ID, `enc`, ciphertext và metadata cần thiết.

## 10. Những giới hạn bảo mật cần hiểu

HPKE cung cấp confidentiality và integrity/authentication cho nội dung trong phạm vi mode và ciphersuite đã chọn. Nó không tự giải quyết mọi yêu cầu bảo mật của ứng dụng.

### Base mode không xác thực danh tính người gửi

Base mode mã hóa cho người giữ private key của recipient, nhưng bất kỳ ai có public key của recipient đều có thể tạo ciphertext hợp lệ gửi tới họ. Nếu nghiệp vụ yêu cầu biết chính xác sender là ai, cần dùng Auth/PSK/AuthPSK phù hợp hoặc cơ chế chữ ký/xác thực độc lập.

### Phải xác minh public key của recipient

Nếu sender nhận nhầm public key do attacker cung cấp, sender có thể mã hóa dữ liệu cho attacker. Public key cần được xác minh qua certificate, pinning, directory tin cậy hoặc cơ chế phân phối khóa phù hợp. HPKE không tự xác minh chứng thư hoặc danh tính của public key.

### Không có replay protection tổng quát ở tầng ứng dụng

Sequence counter của HPKE context phục vụ nonce uniqueness và đồng bộ message trong một context. Nó không thay thế cơ chế chống replay xuyên nhiều context hoặc qua nhiều phiên chạy. Nếu nghiệp vụ cần chống phát lại, thêm message ID, sequence nghiệp vụ, timestamp/expiry và lưu trạng thái đã xử lý theo quy tắc của hệ thống.

### Metadata và kích thước vẫn có thể lộ

`enc`, suite ID, recipient key ID, AAD, routing metadata và độ dài ciphertext có thể nhìn thấy tùy envelope. HPKE không mặc định che giấu kích thước plaintext hoặc metadata của ứng dụng. Nếu cần giảm rò rỉ độ dài, ứng dụng có thể padding theo một định dạng đã thiết kế và kiểm thử.

### “Hybrid” không có nghĩa là hậu lượng tử

Từ “Hybrid” trong HPKE mô tả việc kết hợp public-key KEM với KDF và symmetric AEAD. Nó không tự có nghĩa là kết hợp thuật toán cổ điển với post-quantum KEM. Các KEM identifiers của RFC 9180 được liệt kê trong `HPKEParameterSpec` của Java 26 là DHKEM dựa trên X25519/X448 hoặc elliptic curves P-256/P-384/P-521. Không suy luận rằng HPKE suite này chống được máy tính lượng tử. Nếu yêu cầu hậu lượng tử, phải chọn một giao thức/ciphersuite được chuẩn hóa hỗ trợ KEM hậu lượng tử và xác minh provider/JDK triển khai thực sự hỗ trợ; không tự ghép ML-KEM vào RFC 9180 bằng cách thay một identifier tùy ý.

### Không thay thế TLS

HPKE có thể bảo vệ payload end-to-end hoặc mã hóa dữ liệu cho recipient ngay cả khi payload đi qua nhiều intermediary. Nó không tự cung cấp transport security, xác thực server, quản lý phiên TLS hay bảo vệ toàn bộ metadata của kết nối. Trong ứng dụng mạng, vẫn dùng TLS đúng cấu hình và dùng HPKE cho yêu cầu mã hóa ở tầng message khi cần.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `NoSuchAlgorithmException` khi `Cipher.getInstance("HPKE")` | Provider được cài đặt không cung cấp HPKE Cipher. | Kiểm tra JDK/provider thực tế và phiên bản; JDK 26 reference implementation có HPKE. |
| `InvalidKeyException` khi `init` | Key type không phù hợp với KEM identifier hoặc provider không hỗ trợ key type. | Chọn đúng key pair tương ứng với KEM và xác minh provider. |
| `InvalidAlgorithmParameterException` | Suite identifier không hỗ trợ, sai key type, thiếu `enc` ở recipient hoặc truyền `enc` nhầm sang sender. | Kiểm tra KEM/KDF/AEAD IDs, role và parameter spec ở mỗi phía. |
| Giải mã báo lỗi authentication/tag | Ciphertext bị sửa, AAD khác, `info` khác, PSK/ID không giống hoặc sai context/order. | Xác minh envelope và cấu hình; không xử lý plaintext nếu xác thực thất bại. |
| Sender lấy `getIV()` nhưng recipient không giải mã được | `enc` bị thiếu, bị cắt hoặc gắn với ciphertext khác. | Truyền nguyên vẹn encapsulation từ đúng sender context. |
| Recipient chọn sai private key | Envelope không xác định recipient key/version chính xác. | Truyền key ID đã xác thực và chọn private key tương ứng. |
| Message thứ hai giải mã thất bại | Sender và recipient không gọi `doFinal` cùng số lần/thứ tự hoặc AAD từng message khác nhau. | Giữ context đồng bộ; dùng context riêng cho luồng độc lập. |
| Auth mode init thất bại | KEM/provider không hỗ trợ Auth/AuthPSK hoặc truyền sai role key. | Kiểm tra hỗ trợ của KEM; sender dùng private key của mình, recipient dùng public key của sender. |
| PSK mode bị từ chối | PSK không đủ entropy, PSK ID rỗng hoặc một phía thiếu/thay đổi PSK. | Provision cùng PSK mạnh và cùng identifier ở cả hai phía. |

Các lỗi khởi tạo thường xuất hiện dưới dạng `InvalidKeyException` hoặc `InvalidAlgorithmParameterException`. Lỗi xác thực ciphertext xảy ra trong `doFinal`; coi đây là message không hợp lệ và không trả một phần plaintext cho tầng nghiệp vụ.

## 12. Phân biệt API KEM, KDF và HPKE trong các JDK

| API | Có từ | Trạng thái trong Java 26 | Phạm vi |
|---|---:|---|---|
| `javax.crypto.KEM` | Java 21, JEP 452 | Stable | Encapsulation/decapsulation primitive. |
| `javax.crypto.KDF` và `HKDFParameterSpec` | Java 25, JEP 510; preview lần đầu ở Java 24 | Stable | Dẫn xuất khóa độc lập theo thuật toán KDF. |
| `Cipher.getInstance("HPKE")` và `HPKEParameterSpec` | Java 26 | Stable, `Since: 26` | Tích hợp KEM + KDF + AEAD theo RFC 9180. |

Không cần `--enable-preview` hoặc `--add-modules` để dùng HPKE trên JDK 26; các lớp nằm trong module `java.base`. Khi biên dịch ứng dụng bằng JDK 26, có thể dùng `javac --release 26` để giữ baseline API tương ứng.

Nếu runtime production thấp hơn Java 26, `Cipher.getInstance("HPKE")` và `HPKEParameterSpec` không tồn tại trong API baseline đó. Dùng một thư viện HPKE đã được duy trì và có kiểm thử RFC 9180, hoặc nâng runtime; không tự viết lại key schedule/nonce handling bằng cách ghép KEM, KDF và AES-GCM theo phỏng đoán.

### Kiểm tra provider trên runtime triển khai

```java
Cipher hpke = Cipher.getInstance("HPKE");
System.out.println("HPKE provider: " + hpke.getProvider().getName());
```

Ứng dụng thông thường nên gọi `Cipher.getInstance("HPKE")` mà không khóa cứng tên provider để JCA chọn implementation phù hợp theo thứ tự provider. Tuy nhiên, cần kiểm thử ciphersuite với JDK/provider thực tế trong production, vì API cho phép các provider khác nhau hỗ trợ các tập identifier khác nhau.

## 13. Checklist trước khi triển khai

- [ ] Đã chọn ciphersuite cụ thể gồm KEM, KDF và AEAD được cả hai phía hỗ trợ.
- [ ] Đã hiểu KEM chỉ tạo shared secret và `enc`, không mã hóa payload.
- [ ] Đã hiểu KDF dẫn xuất AEAD key, base nonce và exporter secret; không dùng shared secret trực tiếp làm AES key.
- [ ] Đã phân biệt KDF nội bộ trong DHKEM với KDF của HPKE key schedule.
- [ ] Đã để HPKE Cipher quản lý domain separation, key schedule và nonce; không tự ghép primitive bằng mã tùy chỉnh.
- [ ] Đã xác minh public key của recipient và chọn đúng private key ở phía nhận.
- [ ] Đã chọn mode phù hợp: Base, PSK, Auth hoặc AuthPSK; không mặc định Base xác thực sender.
- [ ] Nếu dùng PSK, đã provision secret có ít nhất 32 byte entropy và cùng `psk_id` ở cả hai phía.
- [ ] Đã dùng cùng `info` ở cả hai phía và phân biệt nó với AAD.
- [ ] Đã gửi nguyên vẹn `enc` cùng ciphertext và metadata cần thiết.
- [ ] Đã dùng AAD giống hệt ở hai phía; hiểu AAD được xác thực nhưng không mã hóa.
- [ ] Đã giữ message order và số lần `doFinal` đồng bộ trong cùng context.
- [ ] Đã có cơ chế replay protection và key rotation ở tầng ứng dụng nếu nghiệp vụ yêu cầu.
- [ ] Đã không hiểu nhầm “Hybrid” là hậu lượng tử; đã kiểm tra KEM suite có đáp ứng chính sách PQC hay không.
- [ ] Đã kiểm thử interoperability, lỗi tag, dữ liệu bị sửa, sai AAD, sai key và provider/JDK triển khai.
- [ ] Đã xác nhận Java 26 API HPKE là stable, không bật preview/incubator không cần thiết.

## Tài liệu tham khảo chính thức

- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html)
- [Java SE 26 — `HPKEParameterSpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html)
- [Java SE 26 — `Cipher`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html)
- [Java SE 26 — `KEM`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 26 — `KDF`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/KDF.html)
- [Java Cryptography Architecture Reference Guide — Securely Exchanging Messages with HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java Security Standard Algorithm Names — HPKE](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html)
- [JDK 26 Release Notes — Hybrid Public Key Encryption](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
- [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510)

*Cập nhật nội dung: 27-11-2026. HPKE Cipher và `HPKEParameterSpec` là Java SE API ổn định từ Java 26. Các ví dụ dùng RFC 9180; xác minh provider, ciphersuite và chính sách xác thực của hệ thống trước khi triển khai.*
