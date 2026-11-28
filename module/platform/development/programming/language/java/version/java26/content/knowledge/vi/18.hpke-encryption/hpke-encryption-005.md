# Các chế độ HPKE và tham số tương ứng

HPKE (Hybrid Public Key Encryption) kết hợp mật mã khóa công khai và mật mã khóa đối xứng để mã hóa dữ liệu có độ dài tùy ý cho khóa công khai của người nhận. Người gửi dùng KEM để tạo shared secret và gói encapsulation; KDF dẫn xuất khóa; AEAD mã hóa plaintext và xác thực dữ liệu bổ sung. RFC 9180 định nghĩa bốn chế độ: Base, PSK, Auth và AuthPSK. Mỗi chế độ quyết định người nhận có thể xác thực người gửi dựa trên một pre-shared key (PSK), khóa KEM của người gửi, cả hai hay không có cơ chế xác thực người gửi.

Từ Java 26, JCA cung cấp `Cipher` có tên thuật toán `HPKE` và `HPKEParameterSpec` để chọn ciphersuite cùng tham số của các chế độ. Đây là API Java SE chính thức, không phải preview hoặc incubator. Bài này tập trung vào cách chọn chế độ, ghép đúng tham số ở hai đầu và hiểu những thuộc tính bảo mật mà mỗi chế độ cung cấp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt KEM, KDF và AEAD trong một HPKE ciphersuite.
- Giải thích bốn chế độ Base, PSK, Auth và AuthPSK và mức xác thực người gửi của từng chế độ.
- Chọn các ID KEM/KDF/AEAD phù hợp với loại khóa và provider.
- Dùng `HPKEParameterSpec.of()`, `withInfo()`, `withPsk()`, `withAuthKey()` và `withEncapsulation()` đúng phía.
- Phân biệt `info`, `psk`, `psk_id`, `encapsulation` và AAD.
- Trao đổi đúng `enc` và ciphertext giữa sender và recipient.
- Hiểu cách `Cipher` quản lý sequence number khi mã hóa nhiều thông điệp trong cùng một context.
- Nhận biết giới hạn của HPKE về replay, ordering, forward secrecy, danh tính người gửi và định dạng wire.
- Kiểm tra khả năng hỗ trợ HPKE trên JDK/provider đích.

## 1. HPKE kết hợp ba thành phần mật mã

HPKE không phải một thuật toán mã hóa đơn lẻ. Một ciphersuite gồm ba thành phần:

```text
Recipient public key
       │
       ▼
      KEM ───────> enc + shared_secret
                         │
                         ▼
                        KDF <──── info / PSK / PSK ID
                         │
                         ▼
                    AEAD key + nonce
                         │
       plaintext + AAD ──┴──────> ciphertext
```

- **KEM — Key Encapsulation Mechanism:** người gửi dùng public key của recipient để tạo shared secret và `enc` (encapsulated key message). Recipient dùng private key tương ứng cùng `enc` để khôi phục shared secret. `enc` là dữ liệu công khai cần gửi kèm ciphertext; nó không phải private key hay ciphertext của plaintext.
- **KDF — Key Derivation Function:** kết hợp shared secret với các tham số của HPKE để tạo khóa AEAD, base nonce và exporter secret. RFC 9180 dùng HKDF trong các KDF được định nghĩa.
- **AEAD — Authenticated Encryption with Associated Data:** mã hóa plaintext và xác thực AAD. AAD được xác thực nhưng không được mã hóa; bên nhận phải cung cấp đúng AAD để giải mã thành công.

Một thông điệp HPKE thường được truyền thành ít nhất cặp `(enc, ciphertext)`. Nếu ứng dụng có nhiều khóa recipient, nó còn phải biết khóa riêng nào tương ứng với thông điệp. RFC 9180 không định nghĩa một wire format hoàn chỉnh cho ứng dụng; giao thức tích hợp HPKE phải quy định rõ cách đóng gói các trường, phiên bản, ciphersuite và metadata cần thiết.

RFC 9180 được công bố bởi IRTF/Crypto Forum Research Group dưới dạng Informational RFC, không phải Internet Standards Track RFC. Đây là đặc tả kỹ thuật của HPKE và các test vector liên quan; khi triển khai cần tuân theo chính xác RFC cùng tài liệu API của JDK/provider.

## 2. Bốn chế độ HPKE

RFC 9180 định nghĩa bốn giá trị mode một byte:

| Chế độ | Giá trị | PSK | Khóa xác thực sender | Người nhận xác thực được điều gì? |
|---|---:|---|---|---|
| Base | `0x00` | Không | Không | Chỉ giải mã được nếu có private key recipient; không xác thực danh tính người gửi |
| PSK | `0x01` | Có `psk` và `psk_id` | Không | Người gửi biết PSK tương ứng |
| Auth | `0x02` | Không | Có khóa KEM riêng của sender | Người gửi chứng minh sở hữu private key KEM tương ứng với public key đã được recipient biết |
| AuthPSK | `0x03` | Có `psk` và `psk_id` | Có khóa KEM riêng của sender | Người gửi chứng minh sở hữu cả PSK và private key KEM |

Trong Java, `HPKEParameterSpec.of(kemId, kdfId, aeadId)` tạo cấu hình Base mặc định. Không có tham số `mode` riêng trong factory này. Chế độ được xác định bởi các tham số được thêm vào:

- Không gọi `withPsk()` và không gọi `withAuthKey()` → Base.
- Chỉ gọi `withPsk()` → PSK.
- Chỉ gọi `withAuthKey()` → Auth.
- Gọi cả `withPsk()` và `withAuthKey()` → AuthPSK.

Không được cung cấp PSK trong Base hoặc Auth; cũng không được bỏ thiếu một trong hai giá trị `psk` và `psk_id` trong PSK/AuthPSK. RFC yêu cầu `psk` và `psk_id` phải xuất hiện cùng nhau hoặc cùng vắng mặt.

### Base — mã hóa tới public key recipient

Base là chế độ đơn giản nhất. Người gửi chỉ cần public key recipient. KEM tạo shared secret và encapsulation; KDF dẫn xuất khóa; AEAD mã hóa dữ liệu. Recipient dùng private key của mình và `enc` để tạo cùng context rồi giải mã.

Base cung cấp tính bí mật và xác thực toàn vẹn của ciphertext đối với người không có khóa recipient. Tuy nhiên, Base **không xác thực người gửi**. Bất kỳ ai biết public key recipient đều có thể tạo một thông điệp HPKE Base hợp lệ gửi cho recipient. Nếu ứng dụng cần xác thực nguồn gửi, phải dùng Auth/PSK/AuthPSK hoặc một cơ chế chữ ký/xác thực ở tầng giao thức.

### PSK — xác thực bằng khóa bí mật chia sẻ trước

PSK mode thêm `psk` và `psk_id` vào key schedule. Hai phía phải được provision cùng PSK và identifier. Recipient chỉ khôi phục được context tương ứng nếu dùng đúng PSK.

PSK mode xác thực rằng người gửi biết PSK. `psk_id` chỉ là định danh để chọn PSK; bản thân ID không phải bí mật và không chứng minh danh tính. Ứng dụng phải quản lý vòng đời, phân phối, luân chuyển và thu hồi PSK an toàn.

RFC 9180 yêu cầu PSK có ít nhất 32 byte entropy; độ dài nên bằng hoặc lớn hơn `Nh` của KDF khi có thể. Không dùng mật khẩu người dùng làm PSK trực tiếp: HKDF không phải password hashing/KDF chậm chống dictionary attack. Tạo PSK bằng nguồn ngẫu nhiên mật mã và quản lý bằng secret manager hoặc cơ chế provision an toàn.

### Auth — xác thực bằng khóa KEM riêng của sender

Auth mode sử dụng cặp khóa KEM lâu dài của sender. Sender gọi KEM authenticated encapsulation bằng private key của mình; recipient dùng public key tương ứng của sender để authenticated decapsulation. Recipient chỉ tạo được shared secret phù hợp nếu `enc` được tạo bằng khóa riêng tương ứng.

Khóa Auth phải là khóa bất đối xứng phù hợp với KEM đã chọn. Với DHKEM(X25519), ví dụ dùng khóa X25519; với DHKEM(P-256), dùng EC key trên secp256r1. Không lấy một khóa chữ ký bất kỳ như Ed25519 hoặc RSA rồi giả định nó dùng được làm khóa Auth của DHKEM.

Auth xác thực việc sở hữu cặp khóa KEM, không tự xác thực tên người, email, tổ chức hay domain. Ứng dụng phải có cách tin cậy để gắn public key sender với danh tính, ví dụ provisioning, certificate hoặc một cơ chế xác minh khóa riêng. RFC khuyến nghị đưa định danh cần ràng buộc vào `info` để tránh identity misbinding.

### AuthPSK — kết hợp khóa KEM của sender và PSK

AuthPSK kết hợp Auth với PSK. Sender phải chứng minh sở hữu private key KEM và biết PSK; recipient cần public key sender và cùng PSK/PSK ID. Cấu hình này hữu ích khi ứng dụng cần hai yếu tố bí mật độc lập hoặc muốn tăng khả năng chống chịu trong một số mô hình tấn công.

AuthPSK không thay thế việc xác thực và quản lý public key sender. Nếu khóa công khai bị gắn sai danh tính hoặc PSK bị chia sẻ quá rộng, chính sách ở tầng ứng dụng vẫn có thể sai. Cũng không được coi AuthPSK với DHKEM cổ điển là một giải pháp hậu lượng tử hoàn chỉnh; RFC thảo luận các thuộc tính hybrid-quantum trong những giả định cụ thể và không đưa ra bảo đảm PQ tổng quát cho mọi cấu hình.

## 3. Chọn KEM, KDF và AEAD

`HPKEParameterSpec.of()` nhận ba ID theo RFC 9180/IANA. Java 26 định nghĩa các hằng tương ứng trong `HPKEParameterSpec`:

### KEM — Key Encapsulation Mechanism

| Hằng Java | ID RFC | KEM | Kiểu khóa recipient/sender |
|---|---:|---|---|
| `KEM_DHKEM_P_256_HKDF_SHA256` | `0x0010` | DHKEM(P-256, HKDF-SHA256) | EC key trên secp256r1 |
| `KEM_DHKEM_P_384_HKDF_SHA384` | `0x0011` | DHKEM(P-384, HKDF-SHA384) | EC key trên secp384r1 |
| `KEM_DHKEM_P_521_HKDF_SHA512` | `0x0012` | DHKEM(P-521, HKDF-SHA512) | EC key trên secp521r1 |
| `KEM_DHKEM_X25519_HKDF_SHA256` | `0x0020` | DHKEM(X25519, HKDF-SHA256) | XDH/X25519 key |
| `KEM_DHKEM_X448_HKDF_SHA512` | `0x0021` | DHKEM(X448, HKDF-SHA512) | XDH/X448 key |

KEM quyết định loại public/private key và authenticated KEM capability. Trong các DHKEM được RFC 9180 định nghĩa ở trên, các KEM có hỗ trợ `AuthEncap()`/`AuthDecap()`, nên phù hợp với Auth và AuthPSK. Một KEM mới hoặc KEM do provider mở rộng có thể không hỗ trợ authenticated mode; phải kiểm tra tài liệu KEM/provider.

### KDF — Key Derivation Function

| Hằng Java | ID RFC | KDF | `Nh` |
|---|---:|---|---:|
| `KDF_HKDF_SHA256` | `0x0001` | HKDF-SHA256 | 32 byte |
| `KDF_HKDF_SHA384` | `0x0002` | HKDF-SHA384 | 48 byte |
| `KDF_HKDF_SHA512` | `0x0003` | HKDF-SHA512 | 64 byte |

Chọn KDF có mức an toàn phù hợp với KEM và PSK. RFC khuyến nghị KDF ít nhất có security level tương đương KEM và PSK. Không chọn KDF chỉ dựa trên tốc độ mà bỏ qua mức an toàn của toàn bộ ciphersuite.

### AEAD — Authenticated Encryption with Associated Data

| Hằng Java | ID RFC | AEAD | Key length | Nonce | Tag |
|---|---:|---|---:|---:|---:|
| `AEAD_AES_128_GCM` | `0x0001` | AES-128-GCM | 16 byte | 12 byte | 16 byte |
| `AEAD_AES_256_GCM` | `0x0002` | AES-256-GCM | 32 byte | 12 byte | 16 byte |
| `AEAD_CHACHA20_POLY1305` | `0x0003` | ChaCha20-Poly1305 | 32 byte | 12 byte | 16 byte |
| `EXPORT_ONLY` | `0xFFFF` | Export-only | Không có AEAD key | Không có nonce | Không có tag |

Các AEAD mã hóa plaintext và xác thực AAD. Tag được ghép vào ciphertext theo định dạng của AEAD; với các thuật toán trong RFC, tag dài 16 byte. Export-only là lựa chọn cho ứng dụng chỉ cần secret exporter, không dùng API mã hóa thông điệp thông thường. Nếu định dùng export-only, cần xác minh provider/API có cung cấp đúng exporter interface; không coi `0xFFFF` là một AEAD để mã hóa plaintext.

### Ciphersuite ví dụ

Một cấu hình thường dùng để bắt đầu thử nghiệm là:

```java
HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256
HPKEParameterSpec.KDF_HKDF_SHA256
HPKEParameterSpec.AEAD_AES_128_GCM
```

Đây là một lựa chọn ciphersuite minh họa có test vectors trong RFC 9180. Môi trường triển khai cần xác nhận chính sách mật mã, yêu cầu bảo mật, hỗ trợ provider và khả năng tương tác với peer. Hai phía phải dùng cùng ba ID; khác một thành phần sẽ tạo key schedule khác và không giải mã được.

## 4. Các tham số của `HPKEParameterSpec`

`HPKEParameterSpec` là immutable và triển khai `AlgorithmParameterSpec`. Factory:

```java
HPKEParameterSpec spec = HPKEParameterSpec.of(kemId, kdfId, aeadId);
```

Factory tạo cấu hình Base với `info` rỗng. Các phương thức `with...()` trả về một `HPKEParameterSpec` mới; chúng không sửa đối tượng cũ.

| Tham số | Java API | Vai trò | Bên nào cung cấp? |
|---|---|---|---|
| KEM/KDF/AEAD IDs | `of(kemId, kdfId, aeadId)` | Chọn ciphersuite | Sender và recipient giống hệt |
| `info` | `withInfo(byte[])` | Ràng buộc context ứng dụng vào key schedule | Cả hai bên giống hệt |
| `psk` | `withPsk(SecretKey, byte[])` | Khóa bí mật chia sẻ trước cho PSK/AuthPSK | Cả hai bên cùng secret |
| `psk_id` | `withPsk(SecretKey, byte[])` | Chọn PSK tương ứng; không phải secret | Cả hai bên giống hệt |
| Auth key | `withAuthKey(AsymmetricKey)` | Chứng minh sender sở hữu private KEM key | Sender dùng private key; recipient dùng public key sender |
| `encapsulation` | `withEncapsulation(byte[])` | KEM message để recipient khôi phục shared secret | Sender lấy qua `Cipher.getIV()`; recipient truyền vào spec |
| AAD | `Cipher.updateAAD(byte[])` | Dữ liệu phụ được xác thực theo từng thông điệp | Cả hai bên giống hệt cho từng message |

### `info` — context chung của phiên

`info` là byte string ứng dụng đưa vào key schedule. Dùng nó để domain-separate các mục đích hoặc giao thức, ví dụ tên giao thức, version, tenant hoặc loại dữ liệu. Nếu một context được dùng cho nhiều thông điệp, `info` có thể áp dụng chung cho toàn context.

Ví dụ:

```java
byte[] info = "com.example.invoice/v1".getBytes(StandardCharsets.UTF_8);
HPKEParameterSpec spec = HPKEParameterSpec.of(kemId, kdfId, aeadId)
        .withInfo(info);
```

Hai phía phải cung cấp cùng byte sequence. Không dựa vào charset mặc định; dùng UTF-8 hoặc một encoding được giao thức quy định. `withInfo()` sao chép mảng đầu vào; API yêu cầu `info` khác rỗng nếu gọi phương thức này và khuyến nghị giới hạn tối đa 64 byte để tương thích. Nếu không có info, giữ giá trị mặc định rỗng của `of()` thay vì gọi `.withInfo(new byte[0])`.

`info` không phải mật khẩu hoặc khóa bí mật. Đưa định danh vào `info` giúp ràng buộc context nhưng không tự chứng minh định danh đó đúng; ứng dụng vẫn cần xác thực nguồn của metadata.

### `psk` và `psk_id`

`withPsk(psk, pskId)` phải được gọi ở cả sender và recipient trong PSK/AuthPSK. Hai bên cần cùng secret key bytes và cùng `psk_id` bytes.

```java
HPKEParameterSpec spec = HPKEParameterSpec.of(kemId, kdfId, aeadId)
        .withInfo(info)
        .withPsk(pskFromSecretStore, pskId);
```

Các quy tắc quan trọng:

- PSK phải có ít nhất 32 byte entropy theo RFC 9180.
- Java API ném `IllegalArgumentException` nếu PSK ngắn hơn 32 byte hoặc `psk_id` rỗng.
- Kiểm tra độ dài không chứng minh entropy: ứng dụng phải tạo PSK bằng nguồn ngẫu nhiên mật mã hoặc lấy từ secret provisioning có chất lượng phù hợp.
- RFC khuyến nghị độ dài `psk`, `psk_id` và `info` tối đa 64 byte để tăng khả năng tương thích.
- Không dùng password người dùng làm PSK. HKDF không được thiết kế để làm chậm dictionary attack.
- Không log PSK, không đưa PSK vào metadata gửi qua mạng và không dùng `psk_id` như một bằng chứng xác thực.

### `authKey` — khóa xác thực của sender

Với Auth/AuthPSK, hai phía gọi `withAuthKey()` nhưng truyền hai thành phần khác nhau của cùng một cặp khóa KEM:

```java
// Sender: private KEM key của chính sender
HPKEParameterSpec senderSpec = baseSpec.withAuthKey(senderKeyPair.getPrivate());

// Recipient: public KEM key đã tin cậy của sender
HPKEParameterSpec recipientSpec = baseSpec.withAuthKey(senderKeyPair.getPublic());
```

Không truyền private key sender sang recipient. Recipient cần public key sender đã được xác thực và liên kết với danh tính mà ứng dụng kỳ vọng. Nếu public key được nhận trực tiếp từ cùng một thông điệp không đáng tin mà không có cơ chế kiểm tra, ứng dụng có thể xác thực một khóa do kẻ tấn công tự chọn.

`withAuthKey()` chỉ tạo spec; nó không kiểm tra KEM có hỗ trợ Auth mode hay không. Việc kiểm tra được thực hiện khi `Cipher.init()`. Nếu KEM không hỗ trợ authenticated encapsulation hoặc key không tương thích, init ném `InvalidAlgorithmParameterException` hoặc `InvalidKeyException`.

### `encapsulation` — dữ liệu KEM từ sender sang recipient

Sau khi sender gọi `init(ENCRYPT_MODE, recipientPublicKey, spec)`, lấy KEM encapsulation message bằng:

```java
byte[] enc = senderCipher.getIV();
```

Tên phương thức `getIV()` có thể gây nhầm lẫn: trong HPKE, giá trị này là KEM encapsulation `enc`, không phải nonce AEAD mà ứng dụng tự tạo. Không thay thế hoặc tự sửa bytes này. Truyền nguyên vẹn cho recipient:

```java
HPKEParameterSpec recipientSpec = HPKEParameterSpec.of(kemId, kdfId, aeadId)
        .withInfo(info)
        .withEncapsulation(enc);
```

`withEncapsulation()` chỉ dành cho phía recipient. Sender không được truyền encapsulation vào spec khi khởi tạo encrypt mode; recipient bắt buộc phải cung cấp nó. API sao chép mảng đầu vào để tránh thay đổi ngoài ý muốn.

## 5. Cấu hình sender và recipient trong Java 26

Java 26 dùng JCA `Cipher`:

```java
Cipher cipher = Cipher.getInstance("HPKE");
```

Khác với AES/GCM, tên thuật toán là đúng một chuỗi `HPKE`, không phải transformation kiểu `HPKE/GCM/NoPadding`. Sender luôn khởi tạo bằng public key của recipient và `Cipher.ENCRYPT_MODE`; recipient luôn khởi tạo bằng private key của mình và `Cipher.DECRYPT_MODE`.

Ví dụ Base mode với X25519, HKDF-SHA256 và AES-128-GCM:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
KeyPair recipientKeyPair = keyPairGenerator.generateKeyPair();

int kem = HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256;
int kdf = HPKEParameterSpec.KDF_HKDF_SHA256;
int aead = HPKEParameterSpec.AEAD_AES_128_GCM;
byte[] info = "example-protocol/v1".getBytes(StandardCharsets.UTF_8);
byte[] aad = "message-type:invoice".getBytes(StandardCharsets.UTF_8);
byte[] plaintext = "Invoice #123".getBytes(StandardCharsets.UTF_8);

// Sender khởi tạo bằng public key của recipient.
Cipher sender = Cipher.getInstance("HPKE");
HPKEParameterSpec senderSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info);
sender.init(Cipher.ENCRYPT_MODE, recipientKeyPair.getPublic(), senderSpec);

// Gửi enc cùng ciphertext tới recipient.
byte[] enc = sender.getIV();
sender.updateAAD(aad);
byte[] ciphertext = sender.doFinal(plaintext);

// Recipient dùng private key của mình, cùng suite/info và enc nhận được.
Cipher recipient = Cipher.getInstance("HPKE");
HPKEParameterSpec recipientSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info)
        .withEncapsulation(enc);
recipient.init(Cipher.DECRYPT_MODE, recipientKeyPair.getPrivate(), recipientSpec);

recipient.updateAAD(aad);
byte[] recovered = recipient.doFinal(ciphertext);
assert Arrays.equals(plaintext, recovered);
```

Ví dụ thể hiện Base mode vì không gọi `withPsk()` hoặc `withAuthKey()`. Trong ứng dụng thật, `enc`, ciphertext, ciphersuite IDs, recipient key ID và metadata cần thiết phải được đóng gói theo wire format đã định nghĩa. Không gửi private key hoặc PSK trong gói tin.

## 6. Tham số tương ứng cho từng mode trong Java

Giả sử `base` là spec đã chọn ciphersuite và `info`, các cấu hình phía sender/recipient như sau:

| Mode | Sender spec | Recipient spec |
|---|---|---|
| Base | `base` | `base.withEncapsulation(enc)` |
| PSK | `base.withPsk(psk, pskId)` | `base.withPsk(psk, pskId).withEncapsulation(enc)` |
| Auth | `base.withAuthKey(senderPrivateKey)` | `base.withAuthKey(senderPublicKey).withEncapsulation(enc)` |
| AuthPSK | `base.withPsk(psk, pskId).withAuthKey(senderPrivateKey)` | `base.withPsk(psk, pskId).withAuthKey(senderPublicKey).withEncapsulation(enc)` |

Trong bảng, `base` đã bao gồm cùng KEM/KDF/AEAD và cùng `info` ở hai phía. `enc` được tạo bởi sender sau khi init và truyền cho recipient. `senderPrivateKey` và `senderPublicKey` là hai thành phần của cùng cặp khóa KEM, được recipient tin cậy.

Ví dụ fragment PSK mode:

```java
// psk là SecretKey được lấy từ secret manager; pskId là byte[] không rỗng.
HPKEParameterSpec senderPskSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info)
        .withPsk(psk, pskId);

sender.init(Cipher.ENCRYPT_MODE, recipientPublicKey, senderPskSpec);
byte[] enc = sender.getIV();

HPKEParameterSpec recipientPskSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info)
        .withPsk(psk, pskId)
        .withEncapsulation(enc);

recipient.init(Cipher.DECRYPT_MODE, recipientPrivateKey, recipientPskSpec);
```

Ví dụ fragment Auth mode:

```java
// Sender dùng private key KEM của chính mình.
HPKEParameterSpec senderAuthSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info)
        .withAuthKey(senderKemKeyPair.getPrivate());

sender.init(Cipher.ENCRYPT_MODE, recipientPublicKey, senderAuthSpec);
byte[] enc = sender.getIV();

// Recipient dùng public key KEM đã tin cậy của sender.
HPKEParameterSpec recipientAuthSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info)
        .withAuthKey(senderKemKeyPair.getPublic())
        .withEncapsulation(enc);

recipient.init(Cipher.DECRYPT_MODE, recipientPrivateKey, recipientAuthSpec);
```

AuthPSK là kết hợp hai fragment: thêm cùng `.withPsk(psk, pskId)` vào spec ở cả hai phía. Phía sender vẫn dùng private KEM key; phía recipient vẫn dùng public KEM key sender.

## 7. `info` khác AAD như thế nào?

HPKE có hai nơi nhận dữ liệu phụ đã được ràng buộc mật mã:

| Thuộc tính | Thời điểm áp dụng | Phạm vi | Java API |
|---|---|---|---|
| `info` | Khi tạo HPKE context/key schedule | Chung cho toàn context; phù hợp protocol/version/tenant/purpose | `HPKEParameterSpec.withInfo()` |
| AAD | Mỗi lần mã hóa/giải mã thông điệp | Riêng cho từng message; phù hợp message type, sequence, routing metadata | `Cipher.updateAAD()` |

`info` tham gia dẫn xuất khóa. Nếu hai phía khác `info`, chúng tạo context khác và giải mã sẽ thất bại. AAD không được mã hóa nhưng được AEAD xác thực; nếu AAD khác, kiểm tra tag thất bại. AAD có thể chứa metadata công khai cần được bảo vệ tính toàn vẹn.

Ví dụ nhiều message trong cùng context:

```java
sender.updateAAD(aadForMessage1);
byte[] ciphertext1 = sender.doFinal(plaintext1);

sender.updateAAD(aadForMessage2);
byte[] ciphertext2 = sender.doFinal(plaintext2);

recipient.updateAAD(aadForMessage1);
byte[] plaintext1Recovered = recipient.doFinal(ciphertext1);

recipient.updateAAD(aadForMessage2);
byte[] plaintext2Recovered = recipient.doFinal(ciphertext2);
```

Mỗi `doFinal()` tạo hoặc giải mã đúng một thông điệp hoàn chỉnh. AAD của mỗi thông điệp phải giống nhau ở hai phía và phải được đặt trước `doFinal()` tương ứng. Không chuyển AAD của message này sang message khác.

## 8. Sequence number và dùng nhiều thông điệp

Sau khi HPKE context được thiết lập, HPKE quản lý sequence number nội bộ. Mỗi message sử dụng nonce khác nhau được tính từ base nonce và sequence number. Điều này giúp tránh nonce reuse khi dùng cùng context nhiều lần.

Java 26 `HPKE Cipher` cho phép gọi nhiều lần `doFinal()` sau một lần init. Theo API:

- Mỗi `doFinal()` phía sender thực hiện một lần HPKE encryption hoàn chỉnh và dùng sequence number tiếp theo.
- Mỗi `doFinal()` phía recipient phải nhận đúng một ciphertext hoàn chỉnh.
- Số lần gọi và thứ tự gọi ở recipient phải khớp với sender.
- `updateAAD()` và `update()` có thể được gọi trước `doFinal()` của từng message.

Không gửi ciphertext thứ hai tới recipient trước ciphertext thứ nhất nếu chúng thuộc cùng context. Nếu message bị mất hoặc thứ tự bị đảo, context có thể không giải mã được đúng message tiếp theo. Giao thức ứng dụng phải đánh số hoặc kiểm soát thứ tự và đưa thông tin thứ tự vào AAD khi cần.

Không chia một ciphertext hoàn chỉnh thành nhiều lần `doFinal()` ở phía recipient. Có thể dùng `update()` để nạp các phần dữ liệu của một message, nhưng kết thúc bằng một lần `doFinal()` cho đúng ciphertext đó. Nếu cần xử lý độc lập, song song hoặc khôi phục sau mất message, hãy thiết kế context riêng cho từng luồng/record hoặc một giao thức framing có sequence và rekey rõ ràng.

## 9. Chọn mode theo yêu cầu xác thực

| Yêu cầu | Mode thường phù hợp | Điều cần có |
|---|---|---|
| Mã hóa dữ liệu tới public key recipient; sender không cần được xác thực | Base | Public key recipient |
| Sender và recipient đã provision cùng một secret ngẫu nhiên có entropy cao | PSK | Public key recipient, PSK, PSK ID |
| Recipient cần xác thực sender bằng khóa KEM đã tin cậy | Auth | Public key recipient, private KEM key sender và public key tương ứng được provision ở recipient |
| Cần đồng thời PSK và xác thực bằng khóa KEM sender | AuthPSK | Tất cả thành phần của PSK và Auth |

Không chọn Base chỉ vì cấu hình ít tham số nếu ứng dụng thực tế cần xác thực người gửi. Ngược lại, không chọn PSK chỉ vì có mật khẩu người dùng; PSK phải là secret có entropy cao và được provision đúng cách.

## 10. Giới hạn bảo mật phải xử lý ở tầng ứng dụng

HPKE là một cơ chế mã hóa mức thấp, không phải một giao thức truyền tin hoàn chỉnh. Những thuộc tính sau không tự động được cung cấp:

- **Replay protection:** HPKE chỉ có một mức bảo vệ replay trong cùng một stream context thông qua sequence/order. Không có replay protection tổng quát. Ứng dụng phải có message ID, sequence number, nonce nghiệp vụ hoặc trạng thái chống phát lại.
- **Ordering và message loss:** recipient phải xử lý ciphertext đúng thứ tự sender đã tạo. Ứng dụng cần phát hiện message bị mất; khi không thể phục hồi, phải bỏ context liên quan và thiết lập context mới.
- **Downgrade prevention:** HPKE giả định hai bên đã thống nhất thuật toán. Nếu kẻ trung gian có thể can thiệp vào việc thương lượng suite, ứng dụng phải có cơ chế chống downgrade và xác thực lựa chọn suite.
- **Danh tính sender:** Base không xác thực sender. Auth chỉ xác thực possession của KEM key, không tự chứng minh tên hoặc tổ chức. PSK xác thực possession của secret, còn `psk_id` chỉ là ID.
- **Key-compromise impersonation:** Auth có giới hạn KCI được RFC thảo luận. Nếu cần chống KCI mạnh hơn, ứng dụng có thể cần ký số trên cặp `(enc, ciphertext)` bằng khóa chữ ký độc lập và xác minh theo trust policy.
- **Forward secrecy đối với recipient compromise:** RFC 9180 nêu ciphertext không forward-secret trước việc lộ recipient long-term private key; kẻ tấn công có private key recipient có thể giải mã ciphertext cũ đã thu thập.
- **Độ dài plaintext:** AEAD ciphertext không che giấu độ dài plaintext. Nếu độ dài là thông tin nhạy cảm, ứng dụng cần padding theo giao thức.
- **Metadata:** `enc`, PSK ID, sender public key và recipient key ID có thể tiết lộ metadata. Nếu cần che giấu, phải thiết kế thêm cơ chế bảo vệ metadata.

Không dùng HPKE để thay TLS hoặc giao thức xác thực toàn diện mà không phân tích các yêu cầu transport, identity, replay, ordering, forward secrecy và key lifecycle.

## 11. Wire format và dữ liệu cần trao đổi

RFC 9180 không chỉ định định dạng serialization chung. Tối thiểu, ứng dụng phải đóng gói:

- `enc` — encapsulated key message do sender lấy từ `Cipher.getIV()`.
- Ciphertext của từng message và thứ tự của chúng nếu dùng nhiều message trong cùng context.
- Ciphersuite IDs (KEM, KDF, AEAD) hoặc một suite ID đã được protocol định nghĩa cố định.
- Recipient key ID nếu recipient có nhiều cặp khóa.
- PSK ID trong PSK/AuthPSK nếu cần chọn secret tương ứng.
- Sender key ID hoặc certificate reference trong Auth/AuthPSK.
- `info` nếu không được suy ra từ protocol; AAD và sequence metadata nếu giao thức dùng.

Không truyền PSK hoặc private key. `enc` không phải ciphertext; hai trường này phải được lưu/truyền riêng theo framing không nhập nhằng. Nếu metadata suite có thể bị thay đổi trên đường truyền, cần ràng buộc chúng vào AAD hoặc cơ chế xác thực thương lượng phù hợp.

## 12. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `NoSuchAlgorithmException` khi `Cipher.getInstance("HPKE")` | JDK/provider không triển khai HPKE | Kiểm tra JDK 26+, provider và danh sách dịch vụ được cài |
| `InvalidKeyException` | Không có HPKE implementation hỗ trợ kiểu khóa hoặc init thiếu tham số | Kiểm tra loại khóa KEM, public/private role và truyền `HPKEParameterSpec` |
| `InvalidAlgorithmParameterException` | ID không được hỗ trợ, KEM/key không tương thích, sai phía của `enc`, Auth mode không hỗ trợ | Đối chiếu suite, key type, sender/recipient spec và provider |
| Recipient giải mã thất bại | Khác KEM/KDF/AEAD, info, PSK/PSK ID, auth key, AAD hoặc ciphertext bị sửa | Đảm bảo tất cả tham số hai phía giống nhau và metadata truyền nguyên vẹn |
| PSK mode init thất bại | PSK dưới 32 byte hoặc PSK ID rỗng | Dùng secret ngẫu nhiên có entropy đủ và ID không rỗng |
| Auth mode không hoạt động | Dùng nhầm signing key hoặc key không thuộc KEM đã chọn | Dùng private/public key pair đúng thuật toán KEM |
| Recipient init thất bại | Quên `withEncapsulation(enc)` | Lấy `enc` từ sender `getIV()` và gắn vào spec recipient |
| Sender init thất bại | Đưa `withEncapsulation()` vào spec encrypt mode | Chỉ truyền encapsulation ở phía decrypt/recipient |
| Message thứ hai giải mã lỗi | Hai phía lệch số lần gọi hoặc thứ tự `doFinal()` | Đồng bộ framing, ordering và sequence; bỏ context nếu mất message không phục hồi được |
| Auth thành công nhưng ứng dụng nhận sai danh tính | Public key sender không được liên kết với identity đáng tin | Provision/trust public key; ràng buộc identity vào `info` và policy |

`HPKEParameterSpec` là immutable và các mảng `info`, `psk_id`, `encapsulation` được sao chép khi cấu hình. Tuy nhiên, ứng dụng vẫn phải bảo vệ PSK và private key, quản lý secret lifetime và không ghi nội dung nhạy cảm vào log.

## 13. Trạng thái API và tương thích JDK/provider

| Thành phần | Trạng thái |
|---|---|
| `Cipher.getInstance("HPKE")` | API/algorithm chính thức trong JDK 26 |
| `javax.crypto.spec.HPKEParameterSpec` | Java SE API, `Since: 26` |
| `HPKEParameterSpec.of()` và các `with...()` | API final; không cần `--enable-preview` |
| HPKE protocol | RFC 9180; không phải tính năng preview của Java |
| Java 25 trở xuống | Không có `HPKEParameterSpec` chuẩn của Java 26 |
| Oracle JDK 26 SunJCE | Có cipher `HPKE`; release notes công bố hỗ trợ các KEM/KDF/AEAD IDs trong RFC 9180 |

Tài liệu `HPKEParameterSpec` lưu ý implementation có thể hỗ trợ tất cả, một phần hoặc không hỗ trợ các algorithm identifiers được liệt kê; implementation cũng có thể thêm ID riêng. Vì vậy, đừng giả định mọi vendor JDK hoặc provider thứ ba đều có cùng mức hỗ trợ. Với ứng dụng đa provider, kiểm tra `Cipher.getInstance("HPKE")` và chạy interoperability test bằng suite thực tế trên runtime đích. Thông thường không nên hard-code tên provider; để JCA chọn provider phù hợp trừ khi có yêu cầu vận hành cụ thể.

JDK 21 đã có API `javax.crypto.KEM` cho thao tác Key Encapsulation Mechanism riêng lẻ. API KEM không đồng nghĩa với HPKE: HPKE còn kết hợp KEM, KDF, AEAD, mode, key schedule, context và sequence management. Java 26 bổ sung `HPKEParameterSpec` cùng cipher `HPKE` để dùng cấu trúc HPKE theo RFC 9180.

## 14. Bài tập thực hành

Một dịch vụ gửi hóa đơn cho recipient qua một kênh lưu trữ không tin cậy. Recipient cần bảo đảm dữ liệu chỉ đọc được bằng private key của mình; ở một số tenant, sender và recipient còn có PSK chung hoặc khóa KEM sender đã được provision.

**Yêu cầu:**

1. Tạo X25519 key pair cho recipient và một X25519 key pair cho sender.
2. Dùng `Cipher.getInstance("HPKE")` với ciphersuite X25519/HKDF-SHA256/AES-128-GCM.
3. Viết luồng Base: lấy `enc` qua `getIV()`, mã hóa một hóa đơn và giải mã bằng private key recipient.
4. Thêm `info` chứa protocol name/version và AAD chứa message type cùng sequence number.
5. Viết PSK mode bằng PSK ngẫu nhiên có ít nhất 32 byte entropy và `psk_id` không rỗng; kiểm tra cả hai phía dùng cùng giá trị.
6. Viết Auth mode: sender dùng private X25519 key, recipient dùng public X25519 key đã được tin cậy của sender.
7. Viết AuthPSK bằng cách kết hợp cả hai tham số.
8. Thử sai `info`, sai PSK, sai PSK ID, sai public key sender, sai AAD và ciphertext bị thay đổi; quan sát lỗi xác thực/decrypt.
9. Gửi hai message trong cùng context, rồi thử đảo thứ tự và bỏ một message để thấy yêu cầu ordering.
10. Kiểm tra cùng mã trên provider/JDK mục tiêu và ghi lại các suite được hỗ trợ.

**Kết quả mong đợi:**

- Người học phân biệt được confidentiality với sender authentication.
- Base không được mô tả nhầm là xác thực sender.
- PSK/Auth/AuthPSK dùng đúng tham số và khóa ở hai phía.
- `enc` được truyền cùng ciphertext; recipient không tự tạo encapsulation.
- `info` và AAD được phân biệt theo phạm vi context/message.
- Nhiều `doFinal()` dùng sequence nội bộ và phải giữ thứ tự.
- Hệ thống có wire format và chính sách replay/downgrade/identity riêng.
- Người học nhận biết HPKE API là final từ JDK 26, không cần preview flag.

## Tài liệu tham khảo

- [RFC 9180: Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html): định nghĩa bốn mode, key schedule, KEM/KDF/AEAD identifiers, sequence, AAD và security considerations.
- [HPKEParameterSpec — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html): factory, algorithm ID constants, `withInfo`, `withPsk`, `withAuthKey`, `withEncapsulation` và các điều kiện kiểm tra.
- [Java Cryptography Architecture Reference Guide — HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html): ví dụ sender/recipient và cách trao đổi encapsulation trong JDK 26.
- [JDK Providers Documentation — SunJCE](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): hỗ trợ cipher `HPKE` và lưu ý về tên transformation.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): bổ sung HPKE Cipher và `HPKEParameterSpec` trong JDK 26.
- [IANA HPKE Registries](https://www.iana.org/assignments/hpke/hpke.xhtml): các KEM, KDF và AEAD identifiers hiện hành.
