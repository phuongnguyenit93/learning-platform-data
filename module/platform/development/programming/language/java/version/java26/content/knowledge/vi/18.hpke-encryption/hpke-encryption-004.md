# Khóa người nhận, vật liệu đóng gói và phía giải mã

Trong HPKE (*Hybrid Public Key Encryption*), bên nhận giữ một cặp khóa bất đối xứng: public key được phân phối cho bên gửi, còn private key được giữ bí mật ở phía nhận. Bên gửi dùng public key đó để tạo một shared secret và một thông điệp đóng gói khóa (*encapsulation*). Bên nhận dùng private key tương ứng cùng encapsulation để khôi phục cùng shared secret, sau đó xác thực và giải mã ciphertext.

Từ **JDK 26**, Java cung cấp `Cipher` với tên thuật toán `HPKE` và `HPKEParameterSpec` để cấu hình HPKE theo RFC 9180. Đây là API Java SE ổn định (`Since: 26`), không phải preview hay incubator; JDK 27 tiếp tục cung cấp API này. Bài học tập trung vào khóa của người nhận, dữ liệu `enc` phải nhận từ bên gửi và quy trình giải mã an toàn.

## 1. Vai trò của khóa người nhận

Người nhận tạo hoặc được cấp một cặp khóa KEM:

- **Recipient public key (`pkR`)**: được gửi cho bên gửi qua một kênh phân phối khóa đáng tin cậy.
- **Recipient private key (`skR`)**: chỉ phía nhận giữ; dùng để khôi phục shared secret từ encapsulation.

Ví dụ tạo khóa X25519:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
KeyPair recipientKeyPair = generator.generateKeyPair();

var recipientPublicKey = recipientKeyPair.getPublic();
var recipientPrivateKey = recipientKeyPair.getPrivate();
```

Đoạn code chỉ minh họa khởi tạo khóa. Trong production, khóa nhận thường có vòng đời dài hơn một phiên gửi tin. Private key nên được lưu trong `KeyStore`, HSM hoặc dịch vụ quản lý khóa phù hợp; không hard-code, ghi log hay gửi private key qua mạng. Public key phải được xác thực bằng certificate, pinning hoặc cơ chế phân phối khóa của hệ thống. Nếu kẻ tấn công thay public key của người nhận bằng khóa của họ, bên gửi có thể mã hóa cho kẻ tấn công thay vì người nhận thật.

Mỗi public key nên có một `keyId` hoặc version để bên nhận chọn đúng private key khi giải mã. Khi xoay vòng khóa, cần giữ private key cũ trong thời gian các envelope còn đang lưu hành hoặc còn có thể được gửi đến.

## 2. HPKE gồm KEM, KDF và AEAD

HPKE kết hợp ba thành phần:

| Thành phần | Vai trò | Ví dụ trong JDK |
| --- | --- | --- |
| KEM — Key Encapsulation Mechanism | Dùng khóa công khai để tạo/khôi phục shared secret và encapsulation | DHKEM với X25519 |
| KDF — Key Derivation Function | Dẫn xuất key và nonce từ shared secret | HKDF-SHA256 |
| AEAD — Authenticated Encryption with Associated Data | Mã hóa plaintext và xác thực ciphertext cùng AAD | AES-128-GCM |

Một bộ ba KEM/KDF/AEAD được gọi là *cipher suite*. Hai bên phải dùng cùng algorithm identifiers. JDK định nghĩa các hằng số trong `HPKEParameterSpec`, ví dụ:

```java
HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256
HPKEParameterSpec.KDF_HKDF_SHA256
HPKEParameterSpec.AEAD_AES_128_GCM
```

Không chọn ba thành phần một cách tùy ý. Hãy cố định suite theo giao thức ứng dụng và kiểm tra implementation/provider ở cả hai đầu hỗ trợ suite đó.

## 3. Dữ liệu bên gửi phải chuyển cho bên nhận

Sau khi khởi tạo `Cipher` ở chế độ mã hóa với public key người nhận, bên gửi lấy KEM encapsulation bằng `Cipher.getIV()`. Với HPKE, giá trị này là **encapsulation message (`enc`)** mà bên nhận cần có để khôi phục shared secret. Dù method mang tên `getIV()`, không nên nhầm nó với việc tự tạo IV cho một AES-GCM cipher thông thường.

Một envelope ứng dụng có thể mang các trường sau:

| Trường | Mục đích |
| --- | --- |
| `version` | Phiên bản định dạng envelope/giao thức ứng dụng |
| `keyId` | Chọn đúng private key người nhận |
| `kemId`, `kdfId`, `aeadId` | Chọn đúng HPKE suite, trừ khi suite đã cố định trong giao thức |
| `enc` | KEM encapsulation lấy từ sender `Cipher.getIV()` |
| `ciphertext` | Kết quả `doFinal()` của bên gửi |
| `aad` hoặc metadata tương đương | Dữ liệu ngoài ciphertext nhưng được xác thực, nếu ứng dụng sử dụng AAD |

Giá trị `info` là dữ liệu context của HPKE key schedule. Hai bên phải cung cấp cùng `info`; ứng dụng có thể quy định sẵn theo giao thức hoặc tái tạo từ metadata đã được xác thực. Không nên coi `info` là bí mật hay thay thế AAD. Không đưa PSK hoặc private key vào envelope.

`enc` không phải bí mật, nhưng phải được truyền nguyên vẹn. Nếu mất, cắt cụt hoặc gắn nhầm `enc` với ciphertext, bên nhận không thể khôi phục đúng context để giải mã.

## 4. Cấu hình HPKEParameterSpec ở phía nhận

`HPKEParameterSpec.of(kemId, kdfId, aeadId)` tạo cấu hình ở `mode_base` với `info` rỗng. Các method `with...` trả về một `HPKEParameterSpec` mới, không sửa object cũ.

Phía nhận cần cung cấp:

1. Cùng KEM/KDF/AEAD identifiers mà bên gửi đã dùng.
2. Cùng `info` nếu bên gửi đã đặt.
3. Encapsulation nhận từ bên gửi qua `withEncapsulation(enc)`.
4. PSK hoặc authentication public key nếu giao thức chọn mode tương ứng.

```java
import java.util.HexFormat;
import javax.crypto.spec.HPKEParameterSpec;

byte[] info = HexFormat.of().parseHex("010203040506");
byte[] enc = receivedEnvelope.encapsulation();

HPKEParameterSpec recipientParameters = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM
).withInfo(info)
 .withEncapsulation(enc);
```

`withEncapsulation` sao chép mảng byte đầu vào để tránh việc caller sửa mảng sau khi cấu hình. `withInfo` cũng sao chép dữ liệu. Theo khuyến nghị RFC 9180 được JDK API nhắc đến, `info` nên không quá 64 byte; `withInfo` yêu cầu mảng khác `null` và không rỗng. Nếu không cần context riêng, để `info` rỗng mặc định thay vì gọi `withInfo(new byte[0])`.

## 5. Giải mã ciphertext bằng private key người nhận

Phía nhận dùng tên thuật toán duy nhất `HPKE`, không dùng chuỗi transformation dạng `HPKE/...`. Khởi tạo cipher ở `DECRYPT_MODE` với private key của chính người nhận và `HPKEParameterSpec` đã gắn encapsulation.

```java
import java.nio.charset.StandardCharsets;
import java.security.PrivateKey;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

static byte[] decryptEnvelope(
        PrivateKey recipientPrivateKey,
        byte[] enc,
        byte[] ciphertext
) throws Exception {

    byte[] info = HexFormat.of().parseHex("010203040506");

    HPKEParameterSpec parameters = HPKEParameterSpec.of(
            HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
            HPKEParameterSpec.KDF_HKDF_SHA256,
            HPKEParameterSpec.AEAD_AES_128_GCM
    ).withInfo(info)
     .withEncapsulation(enc);

    Cipher recipientCipher = Cipher.getInstance("HPKE");
    recipientCipher.init(
            Cipher.DECRYPT_MODE,
            recipientPrivateKey,
            parameters
    );

    return recipientCipher.doFinal(ciphertext);
}
```

`doFinal(ciphertext)` chỉ trả plaintext sau khi AEAD xác thực thành công. Nếu ciphertext bị sửa, `enc` không khớp, key sai hoặc tham số không giống bên gửi, thao tác giải mã thất bại. Không xử lý dữ liệu plaintext một phần hoặc bỏ qua lỗi xác thực.

Trong production, nên bắt và phân loại lỗi ở tầng nội bộ, nhưng trả thông báo thất bại chung cho phía gọi không tin cậy để tránh tạo oracle tiết lộ thông tin về khóa, suite hoặc tính hợp lệ của ciphertext.

## 6. Ví dụ round-trip để hiểu dữ liệu phía nhận

Ví dụ đầy đủ dưới đây tạo cặp khóa người nhận, mô phỏng bên gửi tạo encapsulation/ciphertext, rồi thực hiện phần giải mã ở bên nhận. Phần tạo khóa trong ví dụ chỉ để demo; ứng dụng thực tế nên nạp private key đã quản lý và phân phối public key đã xác thực.

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public class HpkeRecipientDemo {
    public static void main(String[] args) throws Exception {
        // Người nhận tạo key pair. Private key ở lại phía nhận.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        byte[] info = HexFormat.of().parseHex("010203040506");
        byte[] plaintext = "Thông điệp gửi đến người nhận"
                .getBytes(StandardCharsets.UTF_8);

        // Mô phỏng bên gửi: chỉ nhận public key của người nhận.
        Cipher sender = Cipher.getInstance("HPKE");
        HPKEParameterSpec senderParameters = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM
        ).withInfo(info);

        sender.init(
                Cipher.ENCRYPT_MODE,
                recipientKeys.getPublic(),
                senderParameters
        );

        // enc là KEM encapsulation; cần gửi cùng ciphertext.
        byte[] enc = sender.getIV();
        byte[] ciphertext = sender.doFinal(plaintext);

        // Phía nhận: dùng private key tương ứng và enc đã nhận.
        Cipher recipient = Cipher.getInstance("HPKE");
        HPKEParameterSpec recipientParameters = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM
        ).withInfo(info)
         .withEncapsulation(enc);

        recipient.init(
                Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(),
                recipientParameters
        );

        byte[] recovered = recipient.doFinal(ciphertext);
        if (!Arrays.equals(plaintext, recovered)) {
            throw new IllegalStateException("HPKE round-trip failed");
        }

        System.out.println(new String(recovered, StandardCharsets.UTF_8));
    }
}
```

Trong giao thức thực tế, sender và recipient là hai tiến trình khác nhau. Sender đóng gói `enc`, `ciphertext`, `keyId` và metadata cần thiết vào envelope. Recipient chọn private key theo `keyId`, dựng đúng `HPKEParameterSpec`, rồi giải mã. Không gửi `recipientKeys.getPrivate()` hoặc shared secret qua mạng.

## 7. AAD và info có vai trò khác nhau

`info` và AAD đều có thể gắn ngữ cảnh ứng dụng vào HPKE, nhưng chúng được dùng ở các giai đoạn khác nhau:

| Dữ liệu | Vai trò | Phía nhận cần làm gì? |
| --- | --- | --- |
| `info` | Tham gia key schedule, phân tách mục đích sử dụng/context của HPKE | Cung cấp cùng byte sequence khi tạo `HPKEParameterSpec` |
| AAD | Dữ liệu không mã hóa nhưng được AEAD xác thực cùng ciphertext | Gọi `updateAAD()` với đúng byte sequence trước `doFinal()` |
| `enc` | KEM encapsulation để khôi phục shared secret | Đưa vào `withEncapsulation()` |
| `ciphertext` | Nội dung đã mã hóa và có authentication tag | Truyền vào `doFinal()` |

Ví dụ nếu sender xác thực metadata như loại tài liệu và tenant ID bằng AAD, recipient phải dựng đúng byte sequence đó:

```java
byte[] aad = (tenantId + ":" + documentType)
        .getBytes(StandardCharsets.UTF_8);

recipientCipher.updateAAD(aad);
byte[] plaintext = recipientCipher.doFinal(ciphertext);
```

Sender cũng phải gọi `updateAAD(aad)` trước khi xử lý ciphertext. AAD không được mã hóa nên bên nhận vẫn nhìn thấy nó, nhưng nếu bị sửa thì xác thực AEAD thất bại. Nên dùng encoding có cấu trúc và không mơ hồ; tránh nối chuỗi tùy tiện nếu có thể tạo ra nhiều cách phân tách khác nhau.

## 8. PSK mode và authenticated mode ở phía nhận

HPKE định nghĩa bốn mode. `HPKEParameterSpec.of(...)` mặc định tạo `mode_base`. Base mode bảo vệ nội dung cho người nhận nhưng **không xác thực danh tính bên gửi**. Bất kỳ ai có public key của người nhận đều có thể tạo một ciphertext hợp lệ.

| Mode | Phía gửi cung cấp | Phía nhận cung cấp | Mục đích |
| --- | --- | --- | --- |
| `mode_base` | Public key người nhận | Private key người nhận | Mã hóa tới người nhận, không xác thực sender |
| `mode_psk` | PSK và `psk_id` giống cấu hình giao thức | Cùng PSK và `psk_id` | Hai bên đã chia sẻ bí mật ngoài băng |
| `mode_auth` | Private key xác thực của sender | Public key xác thực tương ứng của sender | Xác thực sender sở hữu khóa riêng |
| `mode_auth_psk` | Sender private key và PSK/ID | Sender public key và cùng PSK/ID | Kết hợp hai yếu tố xác thực |

### Nhận bằng PSK

Nếu giao thức dùng `mode_psk`, phía nhận phải gọi `withPsk` với đúng secret key và identifier:

```java
HPKEParameterSpec recipientParameters = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM
).withInfo(info)
 .withPsk(preSharedKey, pskId)
 .withEncapsulation(enc);
```

RFC 9180 yêu cầu PSK có ít nhất 32 byte entropy. `psk_id` phải không rỗng; RFC khuyến nghị giới hạn key và identifier tối đa 64 byte để tăng khả năng tương thích. PSK phải được phân phối/lưu trữ an toàn; không đưa vào envelope.

### Nhận bằng sender authentication key

Với `mode_auth`, sender cấu hình `withAuthKey(senderPrivateKey)`. Recipient phải cấu hình `withAuthKey(senderPublicKey)`:

```java
HPKEParameterSpec recipientParameters = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM
).withInfo(info)
 .withAuthKey(authenticatedSenderPublicKey)
 .withEncapsulation(enc);
```

Public key xác thực của sender cũng cần được gắn với danh tính qua certificate, pinning hoặc trust configuration. `withAuthKey` không tự xác minh chuỗi chứng thư hay quyền nghiệp vụ của sender. Không phải KEM nào cũng hỗ trợ `mode_auth`/`mode_auth_psk`; API có thể ném `InvalidAlgorithmParameterException` khi khởi tạo nếu mode không được hỗ trợ.

## 9. Một context có thể xử lý nhiều message theo thứ tự

Sau khi HPKE cipher được khởi tạo, sender và recipient có thể gọi nhiều lần `doFinal()`. Mỗi lần `doFinal` tương ứng một message hoàn chỉnh và HPKE tự tăng sequence counter để dẫn xuất nonce khác nhau.

Ví dụ về nguyên tắc phía nhận:

```java
// Cipher đã được init một lần với private key, suite và enc.
for (ReceivedMessage message : messagesInOriginalOrder) {
    if (message.aad() != null) {
        recipientCipher.updateAAD(message.aad());
    }

    byte[] plaintext = recipientCipher.doFinal(message.ciphertext());
    handleAuthenticatedPlaintext(plaintext);
}
```

Điều kiện quan trọng:

- Mỗi `doFinal` của recipient phải nhận đúng một ciphertext hoàn chỉnh.
- Số lần gọi và thứ tự phải khớp với sender trong cùng HPKE context.
- Nếu có AAD, AAD của từng message phải khớp và được cung cấp trước `doFinal` tương ứng.
- Không bỏ qua message, đảo thứ tự hoặc thử lại một ciphertext tùy tiện trong cùng context; sequence counter hai phía có thể lệch nhau.
- Nếu cần giải mã message độc lập, có thể tạo một HPKE context riêng cho từng message hoặc thiết kế protocol sequence rõ ràng.

Đây là điểm khác với việc tự dùng `AES/GCM/NoPadding`: HPKE quản lý nonce theo sequence của context. Không tự lấy `getIV()` rồi truyền nó làm IV của một AES-GCM cipher khác.

## 10. Xác thực, replay và vòng đời khóa

HPKE cung cấp bảo mật cho ciphertext theo context và mode đã chọn, nhưng ứng dụng vẫn cần thiết kế quản lý message và danh tính:

- **Base mode không xác thực sender:** nếu cần biết ai gửi, chọn authenticated mode hoặc dùng chữ ký số/protocol xác thực riêng.
- **Replay ở tầng ứng dụng:** một envelope hợp lệ có thể bị phát lại nếu ứng dụng chấp nhận lại nó. Gắn message ID/sequence vào AAD và lưu trạng thái chống replay theo chính sách nghiệp vụ.
- **Key rotation:** mang `keyId` trong envelope và giữ private key cũ đủ lâu để giải mã dữ liệu còn tồn tại.
- **Private-key storage:** bảo vệ private key bằng keystore/HSM/secret management; giới hạn quyền truy cập và audit thao tác.
- **Metadata integrity:** đưa tenant ID, loại payload, version hoặc resource ID quan trọng vào AAD nếu chúng phải được xác thực cùng ciphertext.
- **Error handling:** không trả plaintext cho ứng dụng trước khi `doFinal` xác thực thành công; không tiết lộ chi tiết lỗi giải mã cho caller không tin cậy.

HPKE không tự phân phối public key, không kiểm tra certificate trust, không cấp quyền truy cập dữ liệu và không thay thế TLS cho kênh truyền. Ứng dụng cần kết hợp cơ chế nhận diện người nhận, xác thực sender và chính sách lưu trữ khóa phù hợp.

## 11. Lỗi thường gặp khi giải mã

| Lỗi/tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` khi gọi `Cipher.getInstance("HPKE")` | Provider hiện tại không cung cấp HPKE | Kiểm tra JDK/provider, dùng provider hỗ trợ HPKE và xác minh suite |
| `InvalidKeyException` khi `init` | Key type không khớp KEM hoặc implementation không hỗ trợ key | Kiểm tra X25519/P-256/P-384/P-521/X448 và provider |
| `InvalidAlgorithmParameterException` | Thiếu `enc` ở phía nhận, suite không hỗ trợ, tham số hoặc mode không hợp lệ | Kiểm tra suite, mode, `withEncapsulation` và auth key |
| `AEADBadTagException` hoặc lỗi `BadPaddingException` | Ciphertext bị sửa, sai private key, sai `enc`, `info`, PSK hoặc AAD | Xem đây là lỗi xác thực/giải mã; không sử dụng plaintext |
| Giải mã message thứ hai thất bại | Hai phía gọi `doFinal` khác thứ tự/số lần hoặc AAD không khớp | Đồng bộ sequence và AAD trong cùng context |
| Dùng nhầm `getIV()` như nonce AES-GCM | Nhầm tên method với IV truyền thống | Xem giá trị HPKE này là KEM encapsulation và truyền qua `withEncapsulation()` |
| Đổi suite sau khi nhận envelope | Metadata suite không đồng bộ với sender | Dùng đúng KEM/KDF/AEAD identifiers đã thỏa thuận |

Không nên tự động thử nhiều private key, suite hoặc AAD rồi trả về lý do chi tiết cho client không tin cậy. Thiết kế key ID và protocol version rõ ràng để chọn đúng cấu hình trước khi giải mã.

## 12. Kiểm tra provider và khả năng hỗ trợ

`HPKEParameterSpec` định nghĩa các hằng số chuẩn, nhưng Java API lưu ý rằng một implementation HPKE có thể hỗ trợ toàn bộ, một phần hoặc không hỗ trợ các identifier được liệt kê. JDK 26 Release Notes của Oracle ghi nhận các KEM/KDF/AEAD identifiers trong RFC 9180 được hỗ trợ trong JDK đó; provider khác có thể có phạm vi khác.

Có thể kiểm tra provider được chọn:

```java
Cipher cipher = Cipher.getInstance("HPKE");
System.out.println("HPKE provider: " + cipher.getProvider().getName());
```

Kiểm tra `Cipher.getInstance` chỉ xác nhận có provider cung cấp tên thuật toán `HPKE`; nó không chứng minh provider hỗ trợ mọi suite hoặc mode. Hãy chạy integration test với đúng key type, KEM/KDF/AEAD, mode và cấu hình production. Không thay đổi provider hoặc suite âm thầm giữa hai bên.

## 13. Trạng thái API theo JDK

| JDK | HPKE trong Java | Trạng thái |
| --- | --- | --- |
| JDK 25 trở xuống | Chưa có `Cipher` HPKE và `HPKEParameterSpec` trong Java SE | Cần thư viện/provider ngoài nếu muốn dùng HPKE |
| JDK 26 | Bổ sung `Cipher` tên `HPKE` và `HPKEParameterSpec` (`Since: 26`) | API Java SE ổn định |
| JDK 27 | Tiếp tục cung cấp cùng API HPKE | API Java SE ổn định |

HPKE thuộc module `java.base`, package `javax.crypto` và `javax.crypto.spec`. Không cần `--enable-preview` hoặc `--add-modules`. Với custom runtime image tạo bằng `jlink`, module `java.base` luôn là module nền tảng.

## Ghi nhớ

- Người nhận giữ cặp khóa KEM: public key phân phối cho sender, private key được bảo vệ ở recipient.
- Sender khởi tạo `Cipher("HPKE")` bằng public key recipient; sau `init`, lấy `enc` bằng `senderCipher.getIV()`.
- Recipient dùng private key của mình, cùng KEM/KDF/AEAD identifiers, `info` và `withEncapsulation(enc)` để khởi tạo `DECRYPT_MODE`.
- `getIV()` trong HPKE cung cấp encapsulation message, không phải IV để tự truyền cho AES-GCM.
- `doFinal(ciphertext)` chỉ trả plaintext sau khi AEAD xác thực thành công.
- Base mode không xác thực danh tính sender; cần `mode_auth`, PSK hoặc cơ chế xác thực riêng nếu yêu cầu danh tính.
- AAD được truyền qua `updateAAD()` trước `doFinal()`; `info` là context của key schedule; hai giá trị không thay thế nhau.
- Một HPKE context có thể xử lý nhiều message, nhưng số thứ tự và số lần `doFinal()` hai bên phải khớp.
- API HPKE là Java SE ổn định từ JDK 26; JDK 27 tiếp tục hỗ trợ, không cần preview flag.

## Tài liệu tham khảo

- [HPKEParameterSpec, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html) — suite identifiers, `withEncapsulation`, `withInfo`, PSK/auth key và quy tắc sequence.
- [HPKEParameterSpec, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html) — xác nhận API tiếp tục có trong JDK 27.
- [Cipher, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html) — `getInstance`, `init`, `getIV`, `updateAAD` và `doFinal`.
- [Java Cryptography Architecture Reference Guide, Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html) — ví dụ sender/recipient và cấu hình HPKE.
- [Java Cryptography Architecture Reference Guide, Java SE 27](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html) — hướng dẫn HPKE trên JDK 27.
- [JDK 26 Release Notes — Hybrid Public Key Encryption](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — tính năng `Cipher` HPKE và hỗ trợ algorithm identifiers trong JDK 26.
- [JDK Providers Documentation, SunJCE](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html) — dịch vụ HPKE, DHKEM và HKDF trong provider Oracle JDK.
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180) — định nghĩa HPKE, KEM/KDF/AEAD, modes, encapsulation và sequence.
