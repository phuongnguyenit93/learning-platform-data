# Kiểm thử trao đổi hai chiều, lỗi xác thực và dữ liệu biên

> **Mốc cập nhật: 27-11-2026.** HPKE được mô tả trong RFC 9180 và có API JCA ổn định trong Java SE 26 qua `Cipher` với tên thuật toán `HPKE` và `HPKEParameterSpec` (`Since: 26`). Đây không phải Preview hay Incubator API; không cần `--enable-preview`. Bài này tập trung kiểm thử hai chiều, nhiều thông điệp trong một context, lỗi xác thực AEAD, sai cấu hình và dữ liệu biên trên JDK 26/27.

## 1. Mục tiêu kiểm thử

Một ví dụ mã hóa rồi giải mã được một chuỗi ngắn chỉ chứng minh luồng cơ bản hoạt động. Trước khi tích hợp HPKE vào giao thức ứng dụng, cần kiểm tra thêm:

- Hai bên có thể gửi dữ liệu cho nhau theo hai hướng độc lập.
- Mỗi bên dùng đúng public/private key, KEM encapsulation và ciphersuite.
- `info`, PSK, PSK ID và sender authentication key khớp giữa hai phía.
- AAD được tạo và xác minh giống nhau.
- Nhiều thông điệp trong cùng HPKE context được xử lý đúng thứ tự.
- Ciphertext bị sửa, cắt ngắn, tráo thứ tự hoặc lặp lại đều bị phát hiện.
- Payload rỗng, rất ngắn, sát ranh giới block và payload lớn được xử lý đúng.
- Các lỗi khởi tạo, key type và thuật toán không hỗ trợ được phân biệt với lỗi xác thực thông điệp.
- Giao thức không nhầm xác thực toàn vẹn ciphertext với xác thực danh tính người gửi.

HPKE kết hợp ba thành phần:

1. **KEM** tạo shared secret và encapsulation message.
2. **KDF** dẫn xuất key, nonce và exporter secret.
3. **AEAD** mã hóa plaintext và xác thực ciphertext cùng AAD.

KEM không trực tiếp mã hóa toàn bộ payload. Sau bước thiết lập, dữ liệu được bảo vệ bằng AEAD.

## 2. Phạm vi API trong Java 26

Java 26 bổ sung thuật toán `HPKE` cho `javax.crypto.Cipher` và class `javax.crypto.spec.HPKEParameterSpec`.

~~~java
Cipher cipher = Cipher.getInstance("HPKE");
HPKEParameterSpec parameters = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM
);
~~~

Tên thuật toán phải là chính xác `HPKE`. Không dùng transformation như `HPKE/GCM/NoPadding`, bởi HPKE tự xác định KEM, KDF và AEAD thông qua `HPKEParameterSpec`.

Một ciphersuite trong ví dụ gồm:

| Thành phần | Giá trị | Vai trò |
|---|---|---|
| KEM | `DHKEM(X25519, HKDF-SHA256)` | Tạo shared secret và encapsulation. |
| KDF | `HKDF-SHA256` | Dẫn xuất key schedule. |
| AEAD | `AES-128-GCM` | Mã hóa và xác thực mỗi thông điệp. |

JDK 26 Release Notes công bố hỗ trợ các KEM, KDF và AEAD algorithm identifier được định nghĩa trong RFC 9180. Tuy nhiên, hợp đồng `HPKEParameterSpec` vẫn cho phép provider có khả năng hỗ trợ khác nhau; cần kiểm tra provider/runtime thật sự được triển khai. Không ghim provider cụ thể nếu không có yêu cầu tương thích rõ ràng.

## 3. Luồng thiết lập và trao đổi một chiều

Trong HPKE, sender mã hóa bằng public key của recipient. Recipient giải mã bằng private key tương ứng.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant R as Recipient

    S->>S: Cipher.getInstance("HPKE")
    S->>S: init(ENCRYPT_MODE, recipientPublicKey, spec)
    S->>S: getIV() lấy encapsulation enc
    S->>R: Gửi enc + ciphertext + metadata
    R->>R: Tạo HPKEParameterSpec cùng suite/info
    R->>R: withEncapsulation(enc)
    R->>R: init(DECRYPT_MODE, recipientPrivateKey, spec)
    R->>R: doFinal(ciphertext)
    R-->>R: Nhận plaintext nếu tag hợp lệ
~~~

`Cipher.getIV()` có ý nghĩa đặc biệt trong HPKE: phía sender dùng nó để lấy KEM encapsulation message. Đây không phải nonce của từng thông điệp để ứng dụng tự quản lý như khi dùng trực tiếp AES/GCM.

### 3.1. Ví dụ một lượt gửi

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import java.nio.charset.StandardCharsets;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public class HpkeOneWay {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        byte[] info = "orders/v1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "order-123:accepted".getBytes(StandardCharsets.UTF_8);

        HPKEParameterSpec senderSpec = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM
        ).withInfo(info);

        Cipher sender = Cipher.getInstance("HPKE");
        sender.init(Cipher.ENCRYPT_MODE, recipientKeys.getPublic(), senderSpec);

        // Encapsulation phải được gửi đến recipient cùng ciphertext.
        byte[] enc = sender.getIV();
        byte[] ciphertext = sender.doFinal(plaintext);

        HPKEParameterSpec recipientSpec = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM
        ).withInfo(info).withEncapsulation(enc);

        Cipher recipient = Cipher.getInstance("HPKE");
        recipient.init(
                Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(),
                recipientSpec
        );

        byte[] recovered = recipient.doFinal(ciphertext);
        if (!Arrays.equals(plaintext, recovered)) {
            throw new AssertionError("HPKE round-trip failed");
        }

        System.out.println(new String(recovered, StandardCharsets.UTF_8));
        System.out.println("enc bytes = " + enc.length);
        System.out.println("ciphertext bytes = " + ciphertext.length);
    }
}
~~~

Với KEM X25519 trong ví dụ, encapsulation có độ dài 32 byte. Với AES-128-GCM, ciphertext của một thông điệp có thêm tag 16 byte so với plaintext. Encapsulation được truyền riêng; nó không nằm trong kết quả `doFinal()`.

### 3.2. Điều kiện hai bên phải khớp

| Tham số | Sender | Recipient | Nếu không khớp |
|---|---|---|---|
| KEM/KDF/AEAD IDs | Cùng ciphersuite | Cùng ciphersuite | Có thể lỗi khi `init`, hoặc không thể giải mã. |
| Recipient key pair | Public key | Private key tương ứng | Xác thực AEAD thất bại khi giải mã. |
| Encapsulation | Lấy bằng `getIV()` | Đưa vào `withEncapsulation()` | Recipient không thể tái tạo cùng shared secret. |
| `info` | Giá trị theo giao thức | Chính xác cùng byte | Key schedule khác nhau, tag không hợp lệ. |
| PSK và `psk_id` | Cùng PSK/ID | Cùng PSK/ID | Key schedule khác nhau, tag không hợp lệ. |
| Auth key | Sender private key | Sender public key | Không xác thực được sender hoặc setup bị từ chối. |
| AAD | Byte gửi cùng thông điệp | Cùng byte theo thông điệp | Tag không hợp lệ. |

Không chuyển chuỗi text theo cách tùy ý ở một phía rồi dùng byte encoding khác ở phía còn lại. HPKE so khớp byte, không so khớp ý nghĩa chuỗi.

## 4. Kiểm thử trao đổi hai chiều

HPKE theo RFC 9180 là **một chiều cho mỗi context**: sender context chỉ mã hóa, recipient context chỉ giải mã. Không đảo `Cipher` đang ở `ENCRYPT_MODE` sang `DECRYPT_MODE` để tạo một kênh hai chiều.

Để Alice và Bob trao đổi theo cả hai hướng, tạo hai lần thiết lập độc lập:

- Alice → Bob: Alice dùng public key của Bob; Bob dùng private key của Bob.
- Bob → Alice: Bob dùng public key của Alice; Alice dùng private key của Alice.

Mỗi hướng có encapsulation, sender cipher, recipient cipher và sequence counter riêng.

~~~mermaid
flowchart TD
    A["Alice key pair"] 
    B["Bob key pair"]
    A --> C["Context Alice → Bob"]
    B --> C
    C --> D["Alice encrypt bằng Bob public key"]
    D --> E["Bob decrypt bằng Bob private key"]
    B --> F["Context Bob → Alice"]
    A --> F
    F --> G["Bob encrypt bằng Alice public key"]
    G --> H["Alice decrypt bằng Alice private key"]
~~~

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public class HpkeTwoWay {
    private static final int KEM =
            HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256;
    private static final int KDF = HPKEParameterSpec.KDF_HKDF_SHA256;
    private static final int AEAD = HPKEParameterSpec.AEAD_AES_128_GCM;

    private static HPKEParameterSpec spec(byte[] info) {
        HPKEParameterSpec result = HPKEParameterSpec.of(KEM, KDF, AEAD);
        return info.length == 0 ? result : result.withInfo(info);
    }

    private static byte[] send(
            java.security.PublicKey recipientPublicKey,
            java.security.PrivateKey recipientPrivateKey,
            byte[] info,
            byte[] plaintext) throws Exception {

        Cipher sender = Cipher.getInstance("HPKE");
        sender.init(Cipher.ENCRYPT_MODE, recipientPublicKey, spec(info));
        byte[] enc = sender.getIV();

        Cipher recipient = Cipher.getInstance("HPKE");
        recipient.init(
                Cipher.DECRYPT_MODE,
                recipientPrivateKey,
                spec(info).withEncapsulation(enc)
        );

        byte[] ciphertext = sender.doFinal(plaintext);
        return recipient.doFinal(ciphertext);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();

        byte[] aliceToBobInfo =
                "chat/v1/alice-to-bob".getBytes(StandardCharsets.UTF_8);
        byte[] bobToAliceInfo =
                "chat/v1/bob-to-alice".getBytes(StandardCharsets.UTF_8);

        byte[] fromAlice = "Hello Bob".getBytes(StandardCharsets.UTF_8);
        byte[] fromBob = "Hello Alice".getBytes(StandardCharsets.UTF_8);

        byte[] bobReceived = send(
                bob.getPublic(), bob.getPrivate(), aliceToBobInfo, fromAlice);
        byte[] aliceReceived = send(
                alice.getPublic(), alice.getPrivate(), bobToAliceInfo, fromBob);

        if (!Arrays.equals(fromAlice, bobReceived)
                || !Arrays.equals(fromBob, aliceReceived)) {
            throw new AssertionError("Bidirectional exchange failed");
        }
    }
}
~~~

Đoạn code tạo một setup mới cho từng hướng và minh họa round-trip độc lập trong cùng một JVM test harness. Khi triển khai thật, mỗi endpoint chỉ giữ private key của chính mình; giữ sender/recipient cipher của mỗi hướng trong suốt vòng đời context để gửi nhiều thông điệp mà không lặp lại KEM setup.

**Lưu ý:** ví dụ dùng `mode_base`. Bất kỳ ai có public key của recipient đều có thể tạo ciphertext hợp lệ gửi cho recipient. Tag AEAD xác thực ciphertext và AAD, nhưng không chứng minh danh tính người gửi.

## 5. AAD, info và xác thực người gửi

Ba khái niệm này giải quyết ba mục đích khác nhau:

| Thành phần | Thời điểm áp dụng | Được mã hóa? | Mục đích |
|---|---|---|---|
| `info` | Khi thiết lập HPKE context | Không phải payload | Tách biệt key schedule theo ứng dụng, giao thức, phiên bản hoặc hướng truyền. |
| AAD | Trước từng `doFinal()` | Không | Xác thực metadata của thông điệp mà không mã hóa metadata đó. |
| Auth key / PSK | Khi thiết lập context | Không gửi secret trong packet | Xác thực việc sender sở hữu key hoặc PSK tương ứng. |

Ví dụ AAD có thể chứa:

- Protocol version.
- Message type.
- Conversation ID.
- Sequence number.
- Recipient key ID.
- Content type.

Sender và recipient phải tạo đúng cùng byte AAD. AAD không bí mật; không đặt dữ liệu cần mã hóa vào AAD.

### 5.1. Bốn HPKE modes

| Mode | Mục đích | Sender cần | Recipient cần |
|---|---|---|---|
| Base | Mã hóa tới recipient; không xác thực danh tính sender. | Recipient public key. | Recipient private key. |
| PSK | Xác thực possession của pre-shared key. | PSK và `psk_id`. | Cùng PSK và `psk_id`. |
| Auth | Xác thực possession của sender asymmetric private key. | Sender private key. | Sender public key. |
| AuthPSK | Kết hợp sender asymmetric key và PSK. | Sender private key, PSK, `psk_id`. | Sender public key, cùng PSK, `psk_id`. |

Với Auth mode, sender dùng private key của chính mình trong `withAuthKey()`, recipient dùng public key của sender. Nếu hai chiều đều cần xác thực danh tính, mỗi chiều phải cấu hình sender key theo đúng vai trò.

Một số KEM không hỗ trợ Auth/AuthPSK. Nếu mode không được KEM/provider hỗ trợ, `Cipher.init()` có thể ném `InvalidAlgorithmParameterException`. Đọc Javadoc và kiểm tra provider trên runtime mục tiêu; không giả định mọi tổ hợp KEM/mode đều dùng được.

### 5.2. PSK không phải password

RFC 9180 yêu cầu PSK có ít nhất 32 byte entropy. `psk` và `psk_id` phải xuất hiện cùng nhau. Java API từ chối PSK ngắn hơn 32 byte và PSK ID rỗng. RFC khuyến nghị giới hạn PSK và PSK ID ở mức tối đa 64 byte để tăng khả năng tương thích.

Không dùng mật khẩu người dùng trực tiếp làm PSK. HKDF không phải password hashing function và không làm chậm việc dò mật khẩu. Nếu cần dùng thông tin xác thực dạng password, phải thiết kế một quy trình password-based key derivation riêng theo tiêu chuẩn phù hợp, có salt và tham số chi phí; không tự đưa password vào `withPsk()`.

## 6. Kiểm thử nhiều thông điệp và sequence counter

Sau khi khởi tạo, sender và recipient có thể gọi `doFinal()` nhiều lần trên cùng context. Mỗi lần gọi tạo/giải mã đúng một thông điệp HPKE hoàn chỉnh và dùng nonce khác nhau dựa trên sequence counter nội bộ.

Ví dụ:

~~~java
Cipher sender = Cipher.getInstance("HPKE");
sender.init(Cipher.ENCRYPT_MODE, recipientPublicKey, senderSpec);
byte[] enc = sender.getIV();

Cipher recipient = Cipher.getInstance("HPKE");
recipient.init(
        Cipher.DECRYPT_MODE,
        recipientPrivateKey,
        recipientSpec.withEncapsulation(enc)
);

for (int i = 0; i < messages.length; i++) {
    byte[] aad = headerFor(i);
    sender.updateAAD(aad);
    byte[] ciphertext = sender.doFinal(messages[i]);

    recipient.updateAAD(aad);
    byte[] plaintext = recipient.doFinal(ciphertext);

    if (!Arrays.equals(messages[i], plaintext)) {
        throw new AssertionError("Message " + i + " did not match");
    }
}
~~~

Các quy tắc bắt buộc:

- Số lần `doFinal()` ở sender và recipient phải khớp nhau.
- Mỗi lần recipient `doFinal()` phải nhận đúng một ciphertext hoàn chỉnh.
- Thông điệp phải được giải mã đúng thứ tự đã mã hóa.
- Không bỏ mất thông điệp giữa chuỗi.
- AAD của từng thông điệp phải khớp.
- Không gọi lại `init()` trên context đang sử dụng để “reset” sequence giữa chừng.

Nếu cần truyền song song, phải có framing và cơ chế sắp xếp để recipient nhận lại theo thứ tự. Một `Cipher` là object có trạng thái; không chia sẻ cùng một HPKE context cho nhiều thread cùng ghi mà không có cơ chế tuần tự hóa.

### 6.1. Sequence number phải nằm trong giao thức framing

Ví dụ cấu trúc packet:

| Trường | Vai trò |
|---|---|
| Protocol version | Chọn phiên bản framing. |
| Ciphersuite ID | Chọn KEM/KDF/AEAD đã thỏa thuận. |
| Recipient key ID | Chọn đúng private key để giải mã. |
| Encapsulation (`enc`) | Thiết lập shared secret cho context. |
| Message sequence | Phát hiện mất, trùng hoặc sai thứ tự gói. |
| Message type / content type | Diễn giải payload. |
| Ciphertext | Dữ liệu mã hóa kèm AEAD tag. |

Sequence number trong packet cần được xác thực bằng AAD. Nếu ứng dụng không xác thực sequence metadata, attacker có thể tráo hoặc sửa framing trước khi logic xử lý thứ tự được thực hiện.

Sequence counter của HPKE phát hiện ciphertext bị lặp hoặc đến sai thứ tự trong cùng context. Tuy nhiên, HPKE không định nghĩa chính sách replay ở cấp ứng dụng qua nhiều session, reconnect hoặc transaction nghiệp vụ; ứng dụng vẫn cần quản lý session ID, message ID và delivery policy.

### 6.2. Mất gói, trùng gói và sai thứ tự

Giả sử sender tạo `ct0`, `ct1`, `ct2`:

- Nếu recipient nhận `ct0`, rồi `ct1`, rồi `ct2`, sequence đồng bộ.
- Nếu `ct1` đến trước `ct0`, recipient đang chờ nonce sequence 0 nên giải mã `ct1` thất bại.
- Nếu `ct0` đã được giải mã rồi gửi lại, recipient đang ở sequence 1 nên ciphertext cũ không hợp lệ.
- Nếu `ct0` bị mất, recipient không thể bỏ qua để giải mã `ct1` bằng cùng context.

RFC 9180 yêu cầu ứng dụng phát hiện mất thông điệp và giữ đúng thứ tự. Khi context không thể khôi phục trạng thái đồng bộ một cách an toàn, thiết lập context mới theo giao thức thay vì tự suy đoán nonce/sequence.

## 7. Kiểm thử dữ liệu biên

Dùng AES-128-GCM trong ví dụ, tag dài 16 byte. Với X25519, encapsulation dài 32 byte. Hai độ dài này thuộc ciphersuite cụ thể; không áp dụng chúng cho mọi KEM/AEAD.

### 7.1. Độ dài plaintext

Nên kiểm thử ít nhất các độ dài:

| Độ dài plaintext | Điều cần kiểm tra |
|---:|---|
| 0 byte | Ciphertext vẫn phải chứa authentication tag. |
| 1 byte | Payload nhỏ nhất không rỗng. |
| 15 byte | Ngay dưới một block AES. |
| 16 byte | Đúng một block AES. |
| 17 byte | Qua ranh giới block. |
| 31/32/33 byte | Ranh giới block tiếp theo. |
| 255/256/257 byte | Ranh giới kích thước buffer phổ biến. |
| 4 KiB / 64 KiB | Payload lớn hơn buffer nhỏ. |
| 1 MiB hoặc hơn | Kiểm tra throughput, memory và giới hạn thực tế. |

Với AES-GCM trong ciphersuite đã chọn, ciphertext dài hơn plaintext 16 byte vì tag được gắn vào cuối. HPKE không thêm padding theo block AES.

### 7.2. Độ dài AAD

Thử AAD rỗng, 1 byte, 16 byte, 64 byte, 65 byte và metadata lớn hơn. AAD có thể rỗng; khi rỗng, bỏ qua `updateAAD()` hoặc truyền mảng rỗng theo cách provider hỗ trợ.

AAD không làm ciphertext dài thêm. Thay đổi một byte AAD phải làm kiểm tra tag thất bại khi giải mã.

### 7.3. Độ dài info

`HPKEParameterSpec.of(...)` tạo base-mode spec với `info` rỗng. Đây là cách đúng khi không cần context string:

~~~java
HPKEParameterSpec spec = HPKEParameterSpec.of(kem, kdf, aead);
~~~

Không gọi `withInfo(new byte[0])`: Java API ném `IllegalArgumentException` nếu `info` rỗng. Khi có `info`, dùng cùng byte array ở hai phía. RFC khuyến nghị giữ `info` tối đa 64 byte để tăng khả năng tương thích.

### 7.4. Độ dài PSK và PSK ID

- PSK phải có ít nhất 32 byte entropy.
- PSK ID không được rỗng.
- RFC khuyến nghị PSK và PSK ID tối đa 64 byte.
- Không dùng byte array toàn số 0 hoặc chuỗi password ngắn làm PSK.
- PSK và PSK ID phải được quản lý như secret/configuration có kiểm soát, không ghi vào log.

### 7.5. Encapsulation và ciphertext

Với X25519:

- Encapsulation đúng có độ dài 32 byte.
- `withEncapsulation(null)` ném `NullPointerException`.
- Encapsulation sai định dạng hoặc không tương thích có thể bị từ chối khi `Cipher.init()` hoặc trong bước giải mã, tùy lỗi cụ thể.
- Ciphertext của AES-GCM phải có ít nhất 16 byte tag, kể cả khi plaintext rỗng.
- Ciphertext bị cắt mất tag phải bị từ chối.

Không tự cắt, ghép hoặc diễn giải lại `enc` như một IV AES-GCM thông thường.

## 8. Ma trận kiểm thử lỗi khởi tạo

Các lỗi cấu hình được phát hiện trước khi có plaintext/ciphertext thường khác lỗi xác thực AEAD.

| Trường hợp | Thời điểm phát hiện | Kết quả mong đợi |
|---|---|---|
| Không truyền `HPKEParameterSpec` | `Cipher.init()` | `InvalidKeyException` theo Javadoc HPKE. |
| Key type không được implementation hỗ trợ | `Cipher.init()` | `InvalidKeyException`. |
| KEM/KDF/AEAD ID không được hỗ trợ hoặc không khớp key type | `Cipher.init()` | `InvalidAlgorithmParameterException`. |
| Sender được cấu hình `withEncapsulation()` | `Cipher.init()` | `InvalidAlgorithmParameterException`. |
| Recipient thiếu encapsulation | `Cipher.init()` | `InvalidAlgorithmParameterException`. |
| `withInfo(null)` | Tạo spec | `NullPointerException`. |
| `withInfo(empty)` | Tạo spec | `IllegalArgumentException`; dùng `of()` để giữ info mặc định rỗng. |
| PSK ngắn hơn 32 byte | `withPsk()` | `IllegalArgumentException`. |
| PSK ID rỗng | `withPsk()` | `IllegalArgumentException`. |
| `withEncapsulation(null)` | Tạo spec | `NullPointerException`. |
| `withAuthKey(null)` | Tạo spec | `NullPointerException`. |
| Auth mode không được KEM hỗ trợ | `Cipher.init()` | `InvalidAlgorithmParameterException`. |

Không bắt tất cả exception rồi coi đó là “authentication failed”. Hãy phân loại lỗi setup, lỗi framing và lỗi tag để chẩn đoán đúng.

## 9. Kiểm thử lỗi xác thực và toàn vẹn

Sau khi context đã được khởi tạo thành công, những thay đổi khiến hai phía dẫn xuất key/nonce khác nhau hoặc làm AEAD input khác nhau sẽ khiến `doFinal()` thất bại.

Các trường hợp cần kiểm tra:

| Tình huống | Cách tạo lỗi | Kết quả |
|---|---|---|
| Sai recipient private key | Sender mã hóa cho public key A, recipient dùng private key B. | Tag không hợp lệ. |
| Sai `info` | Sender và recipient dùng context string khác nhau. | Tag không hợp lệ. |
| Sai AAD | Recipient thay đổi message type hoặc sequence trong AAD. | Tag không hợp lệ. |
| Sửa ciphertext | Đảo một bit trong phần ciphertext. | Tag không hợp lệ. |
| Sửa tag | Đảo một bit ở byte cuối. | Tag không hợp lệ. |
| Cắt ngắn ciphertext | Bỏ một hoặc nhiều byte tag. | Decryption thất bại. |
| Sai PSK | Hai bên dùng secret khác nhau. | Tag không hợp lệ. |
| Sai PSK ID | PSK ID khác nhau. | Key schedule khác, tag không hợp lệ. |
| Sai sender auth public key | Sender dùng private key A, recipient xác minh bằng public key B. | Authenticated setup/decryption thất bại. |
| Sai `enc` | Sửa encapsulation trước khi recipient khởi tạo. | KEM/AEAD setup hoặc decryption thất bại. |
| Sai thứ tự | Đưa ciphertext sequence 1 trước sequence 0. | Tag không hợp lệ. |
| Gửi lặp ciphertext | Gửi lại một ciphertext sau khi sequence đã tăng. | Tag không hợp lệ. |

Với AEAD, Java có `AEADBadTagException`, là subclass của `BadPaddingException`. Đây là lỗi phù hợp để nhận biết tag không khớp. Lỗi framing hoặc encapsulation sai có thể xuất hiện ở giai đoạn khởi tạo thay vì `doFinal()`.

### 9.1. Ví dụ kiểm thử ciphertext bị sửa

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public class HpkeTamperTest {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        HPKEParameterSpec senderSpec = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM
        );

        Cipher sender = Cipher.getInstance("HPKE");
        sender.init(Cipher.ENCRYPT_MODE, recipientKeys.getPublic(), senderSpec);

        byte[] enc = sender.getIV();
        byte[] ciphertext = sender.doFinal(
                "sensitive payload".getBytes(java.nio.charset.StandardCharsets.UTF_8)
        );

        // Tạo bản sao để thử sửa tag, giữ bản gốc cho đối chiếu.
        byte[] tampered = ciphertext.clone();
        tampered[tampered.length - 1] ^= 0x01;

        HPKEParameterSpec recipientSpec = HPKEParameterSpec.of(
                HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                HPKEParameterSpec.KDF_HKDF_SHA256,
                HPKEParameterSpec.AEAD_AES_128_GCM
        ).withEncapsulation(enc);

        Cipher recipient = Cipher.getInstance("HPKE");
        recipient.init(
                Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(),
                recipientSpec
        );

        try {
            recipient.doFinal(tampered);
            throw new AssertionError("Tampered ciphertext was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Authentication failure detected");
        }

        // Tạo context mới để xác minh đường giải mã thành công.
        Cipher freshRecipient = Cipher.getInstance("HPKE");
        freshRecipient.init(
                Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(),
                HPKEParameterSpec.of(
                        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
                        HPKEParameterSpec.KDF_HKDF_SHA256,
                        HPKEParameterSpec.AEAD_AES_128_GCM
                ).withEncapsulation(enc)
        );

        byte[] recovered = freshRecipient.doFinal(ciphertext);
        if (recovered.length == 0) {
            throw new AssertionError("Unexpected empty plaintext");
        }
    }
}
~~~

Trong ứng dụng thực tế, không trả stack trace hoặc chi tiết phân biệt giữa sai key, sai AAD và sai tag cho caller không đáng tin cậy. Trả lỗi giao thức thống nhất và ghi log an toàn ở phía server để tránh tạo oracle giúp attacker phân tích trạng thái giải mã.

## 10. Kiểm thử nhiều thông điệp với dữ liệu biên

Đoạn sau kiểm tra nhiều kích thước trên cùng một sender/recipient context. Nó dùng sequence trong AAD để gắn metadata ứng dụng với từng message.

~~~java
import java.nio.ByteBuffer;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.util.Arrays;
import java.nio.charset.StandardCharsets;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public class HpkeBoundaryTest {
    private static final int KEM =
            HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256;
    private static final int KDF = HPKEParameterSpec.KDF_HKDF_SHA256;
    private static final int AEAD = HPKEParameterSpec.AEAD_AES_128_GCM;

    private static HPKEParameterSpec spec(byte[] info) {
        HPKEParameterSpec result = HPKEParameterSpec.of(KEM, KDF, AEAD);
        return info.length == 0 ? result : result.withInfo(info);
    }

    private static byte[] aad(int sequence, int length) {
        return ByteBuffer.allocate(8)
                .putInt(sequence)
                .putInt(length)
                .array();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();
        SecureRandom random = new SecureRandom();

        byte[] info = "files/v1/upload".getBytes(StandardCharsets.UTF_8);

        Cipher sender = Cipher.getInstance("HPKE");
        sender.init(Cipher.ENCRYPT_MODE, recipientKeys.getPublic(), spec(info));
        byte[] enc = sender.getIV();

        if (enc.length != 32) {
            throw new AssertionError("Unexpected X25519 encapsulation length");
        }

        Cipher recipient = Cipher.getInstance("HPKE");
        recipient.init(
                Cipher.DECRYPT_MODE,
                recipientKeys.getPrivate(),
                spec(info).withEncapsulation(enc)
        );

        int[] lengths = {0, 1, 15, 16, 17, 31, 32, 33, 255, 256, 257, 4096, 65536, 1 << 20};

        for (int sequence = 0; sequence < lengths.length; sequence++) {
            int length = lengths[sequence];
            byte[] plaintext = new byte[length];
            random.nextBytes(plaintext);

            byte[] aad = aad(sequence, length);

            sender.updateAAD(aad);
            byte[] ciphertext = sender.doFinal(plaintext);

            // AES-GCM trong ciphersuite này thêm authentication tag 16 byte.
            if (ciphertext.length != plaintext.length + 16) {
                throw new AssertionError("Unexpected ciphertext length");
            }

            recipient.updateAAD(aad);
            byte[] recovered = recipient.doFinal(ciphertext);

            if (!Arrays.equals(plaintext, recovered)) {
                throw new AssertionError("Mismatch at sequence " + sequence);
            }
        }

        System.out.println("All boundary messages passed");
    }
}
~~~

Đây là test in-memory với payload tối đa 1 MiB. Khi kiểm tra dữ liệu lớn hơn, có thể dùng `Cipher.update()` theo nhiều chunk rồi gọi `doFinal()` đúng một lần để kết thúc message. Phía recipient vẫn phải cung cấp một ciphertext hoàn chỉnh cho mỗi lần `doFinal()`.

## 11. Kiểm thử PSK và Auth modes

### 11.1. PSK mode

PSK mode cần cùng PSK và cùng PSK ID ở hai phía. Tạo PSK từ nguồn ngẫu nhiên mật mã, không dùng password trực tiếp:

~~~java
import java.security.SecureRandom;
import javax.crypto.spec.SecretKeySpec;

byte[] pskBytes = new byte[32];
new SecureRandom().nextBytes(pskBytes);

int kem = HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256;
int kdf = HPKEParameterSpec.KDF_HKDF_SHA256;
int aead = HPKEParameterSpec.AEAD_AES_128_GCM;
var psk = new SecretKeySpec(pskBytes, "RAW");
byte[] pskId = "service-key-2026".getBytes(java.nio.charset.StandardCharsets.UTF_8);
byte[] info = "service/v1".getBytes(java.nio.charset.StandardCharsets.UTF_8);

HPKEParameterSpec senderPskSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info)
        .withPsk(psk, pskId);

Cipher senderCipher = Cipher.getInstance("HPKE");
senderCipher.init(Cipher.ENCRYPT_MODE, recipientPublicKey, senderPskSpec);
byte[] enc = senderCipher.getIV();

HPKEParameterSpec recipientPskSpec = HPKEParameterSpec.of(kem, kdf, aead)
        .withInfo(info)
        .withPsk(psk, pskId)
        .withEncapsulation(enc);
~~~

Đoạn trên minh họa cách gắn PSK vào parameter spec; `kem`, `kdf`, `aead`, `enc` và `psk` phải là giá trị được hai bên cấu hình thống nhất. Kiểm tra provider có hỗ trợ KEM/mode đang chọn trước khi dùng trong production.

Các ca kiểm thử PSK:

- PSK hợp lệ và PSK ID hợp lệ: round-trip thành công.
- PSK khác nhau: decryption thất bại.
- PSK ID khác nhau: decryption thất bại.
- PSK ngắn hơn 32 byte: `withPsk()` ném `IllegalArgumentException`.
- PSK ID rỗng: `withPsk()` ném `IllegalArgumentException`.
- PSK entropy thấp: test có thể chạy nhưng thiết kế không an toàn; không chấp nhận trong production.

### 11.2. Auth mode

Trong Auth mode:

- Sender gọi `withAuthKey(senderPrivateKey)`.
- Recipient gọi `withAuthKey(senderPublicKey)`.
- Recipient vẫn dùng private key của chính mình để giải mã.
- Encapsulation vẫn phải được truyền như Base mode.

Nếu sender dùng private key A nhưng recipient cấu hình public key B, authenticated setup hoặc AEAD decryption sẽ thất bại. Xác thực key possession không thay thế việc xác minh public key đó thuộc đúng identity được phép. Ứng dụng cần một cơ chế tin cậy để ánh xạ sender public key với identity/quyền truy cập.

Với DHKEM, RFC 9180 cũng nêu giới hạn key-compromise impersonation (KCI): nếu private key của recipient bị lộ, bảo đảm sender đã sở hữu private key tương ứng không còn giữ nguyên. Vì vậy Auth mode không thay thế việc bảo vệ recipient private key và thiết kế xác thực ở tầng ứng dụng.

Không phải mọi KEM đều hỗ trợ Auth/AuthPSK. Kiểm tra `InvalidAlgorithmParameterException` khi khởi tạo và xác nhận provider cụ thể trước khi đưa mode đó vào giao thức.

Ví dụ cách đặt authentication key cho X25519 Auth mode:

~~~java
HPKEParameterSpec senderAuthSpec = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM
).withInfo(info).withAuthKey(senderKeyPair.getPrivate());

Cipher sender = Cipher.getInstance("HPKE");
sender.init(Cipher.ENCRYPT_MODE, recipientKeyPair.getPublic(), senderAuthSpec);
byte[] enc = sender.getIV();

HPKEParameterSpec recipientAuthSpec = HPKEParameterSpec.of(
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
        HPKEParameterSpec.KDF_HKDF_SHA256,
        HPKEParameterSpec.AEAD_AES_128_GCM
).withInfo(info)
 .withEncapsulation(enc)
 .withAuthKey(senderKeyPair.getPublic());

Cipher recipient = Cipher.getInstance("HPKE");
recipient.init(
        Cipher.DECRYPT_MODE,
        recipientKeyPair.getPrivate(),
        recipientAuthSpec
);
~~~

Trong ví dụ, `senderKeyPair` là key pair dùng để xác thực người gửi; `recipientKeyPair` là key pair dùng để giải mã. Mỗi endpoint phải xác minh public key sender theo trust policy của ứng dụng.

## 12. Phân biệt các nhóm lỗi

| Nhóm lỗi | Ví dụ | Nên xử lý ở đâu |
|---|---|---|
| Cấu hình/API | Algorithm ID sai, thiếu params, key type không đúng. | Kiểm tra khi khởi tạo; báo lỗi cấu hình hoặc tương thích. |
| Framing/transport | Thiếu enc, packet thiếu trường, payload bị cắt. | Parser giao thức trước khi gọi HPKE. |
| KEM/setup | Encapsulation không hợp lệ, sai recipient key, mode không hỗ trợ. | `Cipher.init()` hoặc bước decapsulation. |
| AEAD authentication | Sai AAD, sửa ciphertext/tag, sai PSK/info/key. | `doFinal()` thất bại. |
| Sequence/protocol | Mất, trùng hoặc sai thứ tự message. | Sequence framing và quản lý context. |
| Resource/limit | Payload quá lớn, hết bộ nhớ, vượt giới hạn sử dụng AEAD/context. | Giới hạn kích thước và vòng đời session. |

Không dùng một `catch (Exception)` duy nhất rồi coi mọi lỗi là “sai password”. HPKE không dùng password làm cơ chế mặc định; mỗi loại lỗi có nguyên nhân và cách xử lý khác nhau.

## 13. Kiểm thử interoperability và RFC 9180

Một bộ test tốt có ba lớp:

1. **Unit tests:** round-trip, dữ liệu biên, AAD, tamper, sequence và cấu hình sai.
2. **Provider tests:** chạy với provider/JDK thật trong môi trường production; kiểm tra algorithm support và exception behavior.
3. **Interoperability tests:** trao đổi packet với một implementation HPKE độc lập và test vectors RFC 9180.

Không so sánh ciphertext byte-for-byte giữa hai lần chạy HPKE bình thường. Sender sinh ephemeral KEM material ngẫu nhiên nên encapsulation và ciphertext có thể khác nhau dù plaintext, key và ciphersuite giống nhau. Test đúng là bên kia giải mã được đúng plaintext và xác minh đúng AAD.

RFC 9180 có test vectors cho KEM, KDF, AEAD, key schedule và nhiều sequence number. JCA có overload `Cipher.init(..., SecureRandom)` để truyền nguồn randomness; có thể dùng một nguồn deterministic chỉ trong harness kiểm thử vector nếu provider hỗ trợ đúng cách tiêu thụ randomness đó. Không dùng deterministic randomness trong production. Nếu không kiểm soát được randomness của provider, ưu tiên test interoperability và các invariant của giao thức thay vì so sánh ciphertext byte-for-byte.

### 13.1. Không nhầm HPKE với TLS hoặc chữ ký số

HPKE bảo vệ payload theo public key và ciphersuite đã chọn. Nó không tự cung cấp đầy đủ:

- Xác minh certificate chain hoặc PKI trust.
- Handshake và negotiation của TLS.
- Replay protection ở tầng ứng dụng.
- Reliable delivery hoặc retransmission.
- Authorization theo user/tenant.
- Total ordering cho thông điệp phân tán.

Nếu cần bảo vệ kênh transport và xác thực server/client, tiếp tục dùng TLS phù hợp. HPKE có thể bổ sung mã hóa end-to-end tới recipient, nhưng cần giao thức bao quanh để quản lý identity, framing, sequence và key rotation.

## 14. Checklist test suite

- [ ] Chạy trên JDK 26+; không bật Preview flags cho HPKE.
- [ ] Dùng đúng algorithm name `HPKE`.
- [ ] Kiểm tra provider hỗ trợ KEM/KDF/AEAD đã chọn.
- [ ] Sender dùng recipient public key và `ENCRYPT_MODE`.
- [ ] Recipient dùng recipient private key và `DECRYPT_MODE`.
- [ ] Truyền `enc` từ `sender.getIV()` sang `withEncapsulation()`.
- [ ] `info`, PSK, PSK ID và authentication keys khớp.
- [ ] AAD của mỗi message khớp byte-for-byte.
- [ ] Kiểm tra plaintext 0, 1, 15, 16, 17, 31, 32, 33 byte và payload lớn.
- [ ] Kiểm tra AAD rỗng, ngắn và lớn.
- [ ] Kiểm tra nhiều `doFinal()` trong đúng thứ tự.
- [ ] Kiểm tra mất, trùng và đảo thứ tự message.
- [ ] Kiểm tra sai recipient private key.
- [ ] Kiểm tra sai `info`, AAD, PSK, PSK ID và sender auth key.
- [ ] Sửa ciphertext, sửa tag và cắt ngắn ciphertext.
- [ ] Kiểm tra encapsulation thiếu, rỗng, sai độ dài và bị sửa.
- [ ] Kiểm tra lỗi cấu hình ở `init()` tách biệt với lỗi tag ở `doFinal()`.
- [ ] Kiểm tra hai hướng dùng hai context riêng.
- [ ] Xác định rõ Base mode có chấp nhận việc không xác thực sender hay không.
- [ ] Giới hạn số message/bytes cho mỗi context và có kế hoạch tạo context mới.
- [ ] Không log private key, PSK, plaintext nhạy cảm hoặc shared secret.
- [ ] Có test interoperability với implementation khác hoặc RFC test vectors.

## 15. Bài tập thực hành

1. Chạy ví dụ một chiều Alice → Bob và xác minh plaintext giống nhau.
2. Tạo hai context độc lập để kiểm tra Alice → Bob và Bob → Alice.
3. Gửi 100 thông điệp liên tiếp trên cùng context; xác minh sender/recipient giữ đúng sequence.
4. Gắn sequence number và message type vào AAD; thử thay đổi từng byte.
5. Thử payload có độ dài 0, 1, 15, 16, 17, 255, 256 và 1 MiB.
6. Thử AAD rỗng và AAD có metadata.
7. Thử `info` rỗng bằng cách không gọi `withInfo()`, sau đó thử `withInfo(new byte[0])` và quan sát `IllegalArgumentException`.
8. Sửa byte cuối ciphertext và xác nhận tag failure.
9. Cắt 1 byte ciphertext và xác nhận decryption thất bại.
10. Dùng private key khác để giải mã ciphertext đã tạo cho recipient ban đầu.
11. Thay `info`, AAD, PSK hoặc PSK ID ở một phía; xác nhận thất bại.
12. Thử message bị mất, bị gửi lặp và bị đảo thứ tự.
13. Kiểm tra Auth mode nếu KEM/provider hỗ trợ; thay sender public key để xác minh thất bại.
14. Kiểm tra PSK có ít hơn 32 byte entropy và PSK ID rỗng; xác nhận API từ chối.
15. Chạy test trên đúng JDK/provider production và ghi nhận các thuật toán được hỗ trợ.
16. Trao đổi packet với một implementation RFC 9180 khác; xác minh `enc`, AAD và ciphertext.
17. Thiết kế packet framing có version, ciphersuite, recipient key ID, enc, sequence, AAD và ciphertext.

Bảng kết quả mẫu:

| Nhóm | Ca thử | Kết quả mong đợi | Pass |
|---|---|---|---|
| Round-trip | Một message bình thường | Plaintext khôi phục chính xác | |
| Hai chiều | Alice→Bob và Bob→Alice | Cả hai hướng thành công với context riêng | |
| Boundary | Payload 0/1/15/16/17 byte | Thành công, ciphertext có tag đúng | |
| Large payload | 1 MiB trở lên | Thành công trong giới hạn môi trường | |
| AAD | AAD giống nhau | Thành công | |
| AAD tamper | AAD khác nhau | Tag failure | |
| Ciphertext tamper | Sửa ciphertext/tag | Tag failure | |
| Wrong key | Recipient private key khác | Decryption failure | |
| Context mismatch | `info` hoặc suite khác | Setup/decryption failure | |
| PSK | PSK/ID khớp | Thành công nếu mode hỗ trợ | |
| PSK mismatch | Secret hoặc ID khác | Decryption failure | |
| Sequence | Nhiều message đúng thứ tự | Thành công | |
| Replay/order | Lặp, mất hoặc đảo thứ tự | Phát hiện và từ chối | |
| Provider | Runtime production | Đúng ciphersuite/mode đã chọn | |
| Interop | Implementation khác | Giải mã cùng plaintext và AAD | |

## Tài liệu tham khảo chính thức

- [RFC 9180: Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html)
- [Java SE 26 — HPKEParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html)
- [Java SE 27 — HPKEParameterSpec](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html)
- [Java SE 26 — Cipher API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html)
- [Java Cryptography Architecture Reference Guide — Securely Exchanging Messages with HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
- [JDK 26 Release Notes — Hybrid Public Key Encryption](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java SE 26 — Oracle JDK Providers](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html)

