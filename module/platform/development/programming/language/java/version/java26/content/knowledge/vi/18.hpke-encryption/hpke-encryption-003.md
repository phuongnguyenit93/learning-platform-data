# HPKEParameterSpec và lựa chọn bộ thuật toán

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích HPKE kết hợp KEM, KDF và AEAD để mã hóa dữ liệu cho khóa công khai của người nhận.
- Tạo HPKEParameterSpec bằng of() và lựa chọn một bộ thuật toán tương thích.
- Phân biệt vai trò của KEM, KDF và AEAD; chọn KEM phù hợp với loại khóa người nhận.
- Chọn chế độ base, PSK, auth hoặc auth_psk bằng các phương thức cấu hình tương ứng.
- Thiết lập info, PSK, khóa xác thực và encapsulation đúng phía gửi/nhận.
- Dùng Cipher.getInstance("HPKE") để mã hóa và giải mã.
- Truyền key encapsulation message, ciphertext và metadata cần thiết giữa hai bên.
- Hiểu cách HPKE quản lý nonce theo sequence counter khi xử lý nhiều thông điệp.
- Kiểm tra lỗi khởi tạo, khả năng hỗ trợ của Provider và các giới hạn bảo mật của HPKE.

## 1. HPKE là gì và Java 26 hỗ trợ ra sao?

HPKE (Hybrid Public Key Encryption) là cơ chế mã hóa dữ liệu cho khóa công khai của người nhận. Nó kết hợp ba thành phần:

1. **KEM – Key Encapsulation Mechanism:** tạo một shared secret cho bên gửi và bên nhận. Bên gửi dùng public key của người nhận; bên nhận dùng private key tương ứng để khôi phục shared secret.
2. **KDF – Key Derivation Function:** dẫn xuất khóa và nonce từ shared secret cùng thông tin ngữ cảnh.
3. **AEAD – Authenticated Encryption with Associated Data:** mã hóa plaintext và bảo vệ tính toàn vẹn của ciphertext cùng dữ liệu xác thực bổ sung.

Từ Java 26, JCA/JCE cung cấp Cipher algorithm có tên chuẩn là HPKE và lớp cấu hình bất biến HPKEParameterSpec trong package javax.crypto.spec. Đây là API Java SE ổn định, không phải preview hoặc incubator; không cần --enable-preview hay thêm module. API có từ Java 26.

Khác với AES/GCM, HPKE không được gọi bằng transformation dạng "algorithm/mode/padding". Hãy lấy Cipher bằng đúng tên đơn:

~~~java
Cipher cipher = Cipher.getInstance("HPKE");
~~~

HPKE không phải một giao thức TLS, không tự định nghĩa định dạng gói tin hoặc quá trình thương lượng phiên bản cho ứng dụng. Ứng dụng vẫn phải quy định cách trao đổi encapsulation, ciphertext, định danh khóa và các tham số giao thức.

Từ "hybrid" trong HPKE chỉ việc kết hợp mật mã khóa công khai với mã hóa đối xứng hiệu quả. Nó không có nghĩa bộ thuật toán DHKEM trong RFC 9180 là cơ chế hậu lượng tử.

## 2. HPKEParameterSpec mô tả bộ thuật toán và ngữ cảnh

HPKEParameterSpec là lớp final, immutable và implement AlgorithmParameterSpec. Nó mô tả các tham số cần thiết để khởi tạo Cipher HPKE:

- KEM algorithm identifier.
- KDF algorithm identifier.
- AEAD algorithm identifier.
- Application-supplied info.
- Pre-shared key và PSK identifier nếu dùng PSK mode.
- Authentication key nếu dùng auth mode.
- Encapsulation message ở phía nhận.

Tạo cấu hình cơ bản bằng factory:

~~~java
HPKEParameterSpec parameters = HPKEParameterSpec.of(
    HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
    HPKEParameterSpec.KDF_HKDF_SHA256,
    HPKEParameterSpec.AEAD_AES_128_GCM
);
~~~

of(kem_id, kdf_id, aead_id) tạo cấu hình ở mode_base với info rỗng. Ba giá trị là mã định danh số theo RFC 9180, không phải tên thuật toán dạng String.

Các tham số được bổ sung bằng phương thức with...(). Mỗi phương thức trả về một HPKEParameterSpec mới; đối tượng ban đầu không bị thay đổi. Có thể nối các lời gọi:

~~~java
HPKEParameterSpec parameters = HPKEParameterSpec.of(
    HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256,
    HPKEParameterSpec.KDF_HKDF_SHA256,
    HPKEParameterSpec.AEAD_AES_128_GCM
).withInfo("orders/v1".getBytes(StandardCharsets.UTF_8));
~~~

Các mã thuật toán phải nằm trong khoảng 0 đến 65535. of() kiểm tra miền số của các identifier; việc tổ hợp có được Provider chấp nhận với key cụ thể hay không được xác định khi gọi Cipher.init().

## 3. Chọn KEM theo loại khóa người nhận

KEM quyết định cách bên gửi tạo shared secret và encapsulation message cho public key của người nhận. KEM cũng xác định loại khóa mà Cipher HPKE yêu cầu.

JDK 26 định nghĩa các KEM identifier DHKEM theo RFC 9180:

| Hằng HPKEParameterSpec | KEM ID | Loại khóa người nhận |
|---|---:|---|
| KEM_DHKEM_P_256_HKDF_SHA256 | 0x0010 | EC trên secp256r1 / P-256 |
| KEM_DHKEM_P_384_HKDF_SHA384 | 0x0011 | EC trên secp384r1 / P-384 |
| KEM_DHKEM_P_521_HKDF_SHA512 | 0x0012 | EC trên secp521r1 / P-521 |
| KEM_DHKEM_X25519_HKDF_SHA256 | 0x0020 | XDH X25519 |
| KEM_DHKEM_X448_HKDF_SHA512 | 0x0021 | XDH X448 |

Tên KEM có chứa HKDF vì mỗi DHKEM dùng một KDF nội bộ để tạo shared secret từ kết quả Diffie-Hellman. Đây là bước bên trong KEM.

**KDF của HPKE suite là một lựa chọn riêng.** Không được suy luận rằng KDF ở tên KEM bắt buộc phải giống KDF identifier truyền cho of(). RFC 9180 định nghĩa hai tầng dẫn xuất khóa: KDF nội bộ của DHKEM và KDF dùng trong key schedule của HPKE. Ví dụ RFC có suite dùng DHKEM(P-256, HKDF-SHA256) nhưng chọn KDF của HPKE là HKDF-SHA512.

### Tạo key pair X25519

Ví dụ tạo khóa người nhận:

~~~java
KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
KeyPair recipientKeys = keyPairGenerator.generateKeyPair();
~~~

Bên gửi chỉ cần public key. Bên nhận giữ private key tương ứng để giải mã. Không gửi private key qua mạng hoặc nhúng nó vào cấu hình công khai.

Nếu dùng P-256, P-384 hoặc P-521, tạo EC key pair với named curve tương ứng và bảo đảm public/private key thực sự thuộc curve mà KEM identifier yêu cầu.

Không chọn KEM chỉ theo tên mà không kiểm tra loại key. Nếu key type hoặc curve không khớp, Cipher.init() có thể ném InvalidKeyException hoặc InvalidAlgorithmParameterException.

## 4. Chọn KDF của HPKE suite

JDK 26 định nghĩa ba KDF identifier:

| Hằng HPKEParameterSpec | KDF ID | Hàm băm nền |
|---|---:|---|
| KDF_HKDF_SHA256 | 0x0001 | HKDF-SHA256 |
| KDF_HKDF_SHA384 | 0x0002 | HKDF-SHA384 |
| KDF_HKDF_SHA512 | 0x0003 | HKDF-SHA512 |

KDF dùng shared secret để dẫn xuất các giá trị phục vụ encryption context. Việc lựa chọn phải theo profile mà cả hai bên hỗ trợ và quy định bảo mật của giao thức.

Không tự chọn KDF độc lập ở hai đầu. Sender và recipient phải dùng cùng KEM ID, KDF ID và AEAD ID. HPKE không tự thương lượng để tìm một bộ thuật toán chung khi khởi tạo Cipher.

Một profile phổ biến trong ví dụ của RFC 9180 là:

- DHKEM(X25519, HKDF-SHA256).
- HPKE KDF HKDF-SHA256.
- AEAD AES-128-GCM.

Profile này được dùng trong các test vector chính thức của RFC, thuận tiện cho kiểm thử tương thích. Khi triển khai, vẫn phải tuân thủ chính sách mật mã và profile mà giao thức của hệ thống đã thống nhất.

## 5. Chọn AEAD

AEAD mã hóa plaintext và xác thực ciphertext cùng dữ liệu bổ sung. JDK 26 định nghĩa:

| Hằng HPKEParameterSpec | AEAD ID | Vai trò |
|---|---:|---|
| AEAD_AES_128_GCM | 0x0001 | AES-128-GCM |
| AEAD_AES_256_GCM | 0x0002 | AES-256-GCM |
| AEAD_CHACHA20_POLY1305 | 0x0003 | ChaCha20-Poly1305 |
| EXPORT_ONLY | 0xFFFF | Chỉ dành cho luồng HPKE exporter, không phải AEAD mã hóa payload thông thường |

Lựa chọn AES-GCM hoặc ChaCha20-Poly1305 theo yêu cầu tương thích, chính sách mật mã và hiệu năng đã đo trên nền tảng triển khai. Không có một lựa chọn nhanh nhất trên mọi CPU.

EXPORT_ONLY là identifier đặc biệt của RFC 9180 dành cho ứng dụng chỉ dùng giao diện Export để dẫn xuất secret. Không chọn nó cho quy trình mã hóa/giải mã thông điệp thông thường bằng Cipher.doFinal().

## 6. Quy trình chọn một bộ thuật toán

Một bộ HPKE suite là bộ ba:

~~~text
(KEM ID, KDF ID, AEAD ID)
       |       |       |
       v       v       v
   Shared   Key      Payload
   secret   schedule encryption
~~~

Có thể chọn theo thứ tự:

1. **Xác định key type của người nhận.** Public key là X25519, X448 hay EC curve nào? Chọn KEM tương ứng.
2. **Xác định profile KDF.** Chọn HKDF-SHA256, SHA384 hoặc SHA512 theo giao thức và yêu cầu bảo mật.
3. **Chọn AEAD.** Chọn AES-GCM hoặc ChaCha20-Poly1305 theo policy và khả năng triển khai.
4. **Xác định mode.** Cần chỉ mã hóa cho người nhận, cần PSK, cần xác thực sender bằng key hay kết hợp cả hai?
5. **Kiểm tra Provider.** Xác nhận Cipher HPKE và tổ hợp tham số được hỗ trợ trong JDK/runtime thực tế.
6. **Đóng băng profile giao thức.** Hai bên phải dùng cùng identifier và cùng quy tắc trao đổi encapsulation, info, PSK hoặc auth key.

Không nên để mỗi request tự chọn một bộ thuật toán tùy ý. Hãy định nghĩa profile được phê duyệt, version hóa profile và có cơ chế chuyển đổi có kiểm soát khi nâng cấp.

## 7. Bốn mode của HPKE

of() tạo mode_base. Các phương thức cấu hình bổ sung xác định mode cần dùng:

| Mode RFC 9180 | Cách cấu hình | Điều được xác thực |
|---|---|---|
| mode_base (0x00) | Không gọi withPsk() hoặc withAuthKey() | Không xác thực danh tính sender |
| mode_psk (0x01) | withPsk(psk, psk_id) ở cả hai bên | Sender chứng minh có PSK chung |
| mode_auth (0x02) | withAuthKey(key) ở cả hai bên | Sender chứng minh có private key xác thực |
| mode_auth_psk (0x03) | Cả withPsk() và withAuthKey() ở cả hai bên | Có cả PSK và asymmetric authentication |

### Base mode

Base mode phù hợp khi mục tiêu là mã hóa dữ liệu cho recipient public key. Bất kỳ ai có public key của người nhận đều có thể tạo ciphertext hợp lệ. AEAD bảo vệ tính toàn vẹn của thông điệp nhưng không chứng minh ai là người gửi.

Nếu ứng dụng cần xác thực sender, base mode không đủ. Cần dùng auth/PSK mode hoặc bổ sung cơ chế xác thực riêng theo giao thức.

### PSK mode

PSK mode sử dụng một secret đã được chia sẻ trước. Cả sender và recipient phải cấu hình cùng PSK và PSK identifier:

~~~java
HPKEParameterSpec parameters = HPKEParameterSpec.of(kemId, kdfId, aeadId)
    .withPsk(preSharedKey, pskId);
~~~

PSK và psk_id phải cùng xuất hiện hoặc cùng vắng mặt. Không sử dụng mật khẩu người dùng có entropy thấp làm PSK. RFC 9180 yêu cầu PSK có ít nhất 32 byte entropy; JDK API cũng từ chối PSK có độ dài dưới 32 byte. API chỉ kiểm tra độ dài, không thể đo entropy thật của khóa.

### Auth mode

Auth mode xác thực sender bằng asymmetric key. Sender cung cấp private key của chính mình; recipient cung cấp public key tương ứng của sender:

~~~java
// Sender: private key của sender
HPKEParameterSpec senderParameters =
    HPKEParameterSpec.of(kemId, kdfId, aeadId)
        .withAuthKey(senderKeyPair.getPrivate());

// Recipient: public key của sender
HPKEParameterSpec recipientParameters =
    HPKEParameterSpec.of(kemId, kdfId, aeadId)
        .withAuthKey(senderKeyPair.getPublic())
        .withEncapsulation(encapsulation);
~~~

Public key của sender phải được gắn với danh tính đáng tin cậy theo chính sách của ứng dụng. Chỉ nhận một public key từ cùng thông điệp không đủ để xác thực danh tính.

### AuthPSK mode

AuthPSK kết hợp cả asymmetric authentication và PSK. Cả hai bên phải cấu hình đúng cặp khóa xác thực và cùng PSK/PSK ID. Chỉ dùng khi giao thức thật sự cần cả hai lớp xác thực và đã quy định cách quản lý khóa.

Một số KEM có thể không hỗ trợ AuthEncap/AuthDecap. Khi đó chỉ base và PSK mode được hỗ trợ. Các DHKEM được định nghĩa trong RFC 9180 hỗ trợ Auth; với KEM khác, phải kiểm tra tài liệu implementation.

## 8. Ý nghĩa của info và AAD

HPKE có hai vị trí nhận dữ liệu bổ sung, nhưng chúng phục vụ hai phạm vi khác nhau.

### info – thông tin ngữ cảnh khi tạo encryption context

Dùng withInfo(byte[]) để đưa thông tin ngữ cảnh vào key schedule:

~~~java
byte[] info = "com.example.orders/v1".getBytes(StandardCharsets.UTF_8);

HPKEParameterSpec parameters = HPKEParameterSpec.of(kemId, kdfId, aeadId)
    .withInfo(info);
~~~

Hai bên phải cung cấp cùng byte sequence. info có thể ràng buộc context với protocol name, phiên bản, loại dữ liệu hoặc ngữ cảnh ứng dụng. Nó không phải khóa bí mật và không phải dữ liệu AAD theo từng thông điệp.

RFC 9180 khuyến nghị giới hạn info tối đa 64 byte để tăng khả năng tương thích. API Java sao chép mảng đầu vào; info() cũng trả về một bản sao. withInfo(null) ném NullPointerException và info rỗng bị từ chối bằng IllegalArgumentException. Nếu không cần info, giữ cấu hình mặc định từ of().

### AAD – dữ liệu xác thực bổ sung theo thông điệp

AAD được truyền bằng Cipher.updateAAD() sau khi init và trước khi xử lý dữ liệu của thông điệp:

~~~java
cipher.updateAAD(aad);
byte[] ciphertext = cipher.doFinal(plaintext);
~~~

AAD không được mã hóa nhưng được xác thực. Recipient phải cung cấp chính xác cùng AAD khi giải mã. AAD phù hợp với metadata cần được bảo vệ khỏi sửa đổi nhưng không cần giữ bí mật, ví dụ content type, message version hoặc record identifier.

Không nhầm info và AAD: info gắn với encryption context; AAD có thể thay đổi cho từng thông điệp trong cùng context.

## 9. Encapsulation message được truyền thế nào?

Trong bước KEM, sender tạo một shared secret và một key encapsulation message, thường gọi là enc.

Sau khi khởi tạo Cipher ở phía gửi, lấy enc bằng:

~~~java
byte[] encapsulation = senderCipher.getIV();
~~~

Trong HPKE, getIV() ở đây trả về key encapsulation message của KEM. Nó không phải nonce AEAD mà ứng dụng phải tự tạo hoặc tự quản lý.

Recipient phải đưa enc vào HPKEParameterSpec bằng withEncapsulation(byte[]):

~~~java
HPKEParameterSpec recipientParameters = HPKEParameterSpec.of(
    kemId, kdfId, aeadId
).withInfo(info)
 .withEncapsulation(encapsulation);
~~~

Encapsulation là dữ liệu công khai cần chuyển tới recipient cùng ciphertext. Không được nhầm nó với private key hoặc shared secret. API sao chép mảng encapsulation đầu vào và trả bản sao khi gọi encapsulation().

Sender không được cung cấp withEncapsulation(). Nếu sender đưa encapsulation vào cấu hình, Cipher.init() có thể ném InvalidAlgorithmParameterException. Ngược lại, recipient phải cung cấp encapsulation để khôi phục shared secret.

## 10. Ví dụ đầy đủ: X25519 + HKDF-SHA256 + AES-128-GCM

Ví dụ dưới đây dùng base mode để mã hóa một thông điệp cho recipient. Sender dùng public key của recipient; recipient dùng private key tương ứng. AAD được truyền giống nhau ở hai phía.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public final class HpkeExample {
    private static final int KEM =
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256;
    private static final int KDF =
        HPKEParameterSpec.KDF_HKDF_SHA256;
    private static final int AEAD =
        HPKEParameterSpec.AEAD_AES_128_GCM;

    public static void main(String[] args) throws Exception {
        // Recipient tạo và giữ key pair.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        byte[] info =
            "com.example.orders/v1".getBytes(StandardCharsets.UTF_8);
        byte[] aad =
            "type=invoice;version=1".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext =
            "Invoice #2026-001".getBytes(StandardCharsets.UTF_8);

        // Sender: mã hóa bằng public key của recipient.
        HPKEParameterSpec senderParameters =
            HPKEParameterSpec.of(KEM, KDF, AEAD).withInfo(info);

        Cipher sender = Cipher.getInstance("HPKE");
        sender.init(
            Cipher.ENCRYPT_MODE,
            recipientKeys.getPublic(),
            senderParameters
        );

        // Đây là KEM encapsulation message cần gửi cho recipient.
        byte[] encapsulation = sender.getIV();

        sender.updateAAD(aad);
        byte[] ciphertext = sender.doFinal(plaintext);

        // Recipient: dùng private key của mình và cùng bộ tham số.
        HPKEParameterSpec recipientParameters =
            HPKEParameterSpec.of(KEM, KDF, AEAD)
                .withInfo(info)
                .withEncapsulation(encapsulation);

        Cipher recipient = Cipher.getInstance("HPKE");
        recipient.init(
            Cipher.DECRYPT_MODE,
            recipientKeys.getPrivate(),
            recipientParameters
        );

        recipient.updateAAD(aad);
        byte[] recovered = recipient.doFinal(ciphertext);

        if (!Arrays.equals(plaintext, recovered)) {
            throw new AssertionError("HPKE round trip failed");
        }

        System.out.println(new String(recovered, StandardCharsets.UTF_8));
    }
}
~~~

Trong ví dụ:

- KEM identifier khớp X25519 key pair.
- KDF và AEAD giống nhau ở hai phía.
- info giống nhau khi tạo hai encryption context.
- enc được lấy từ sender và đưa vào recipient.
- AAD được truyền ở từng thao tác mã hóa/giải mã.
- Recipient giải mã ciphertext bằng private key của mình.

Đây là ví dụ trao đổi trong cùng tiến trình để minh họa API. Trong hệ thống thật, recipient private key phải được lưu và bảo vệ riêng; sender chỉ nhận public key đã được xác thực. Không gửi private key hoặc PSK trong envelope.

## 11. Đóng gói dữ liệu trao đổi giữa hai bên

HPKE không tự định nghĩa wire format. Ứng dụng phải đóng gói các trường cần thiết để recipient tái tạo đúng cấu hình, ví dụ:

~~~text
Envelope
  protocolVersion
  suiteId:
    kemId
    kdfId
    aeadId
  recipientKeyId
  encapsulation
  ciphertext
  applicationMetadata
~~~

Tùy mode, giao thức còn cần cung cấp psk_id và cách recipient lấy PSK, hoặc định danh sender public key để xác minh auth mode. info cần được tái tạo giống nhau ở cả hai đầu; không nhất thiết phải gửi trực tiếp nếu nó đã được quy định bởi protocol context.

Suite identifier và version phải được chọn theo quy tắc giao thức rõ ràng. Nếu metadata suite có thể bị thay đổi bởi đối thủ, hãy ràng buộc nó với dữ liệu xác thực của giao thức, chẳng hạn đưa phần metadata phù hợp vào AAD. Không cho phép một bên tự hạ cấp suite sang thuật toán yếu hơn mà bên kia không kiểm soát.

## 12. Một Cipher context có thể xử lý nhiều thông điệp

Sau khi Cipher HPKE được khởi tạo, sender và recipient có thể gọi doFinal() nhiều lần trên cùng context. Mỗi lần doFinal() hoàn tất một thông điệp HPKE riêng và sử dụng nonce khác được dẫn xuất từ sequence counter nội bộ.

Ví dụ:

~~~java
byte[] ciphertext1 = sender.doFinal(message1);
byte[] ciphertext2 = sender.doFinal(message2);

byte[] plaintext1 = recipient.doFinal(ciphertext1);
byte[] plaintext2 = recipient.doFinal(ciphertext2);
~~~

Các điều kiện quan trọng:

- Số lần và thứ tự doFinal() phải khớp giữa sender và recipient.
- Mỗi doFinal() phía nhận tương ứng chính xác một ciphertext hoàn chỉnh.
- Nếu dùng updateAAD(), AAD của từng thông điệp phải khớp ở hai phía.
- Không bỏ qua, đảo thứ tự hoặc ghép ciphertext của nhiều message thành một lần giải mã.
- Không tự tạo hoặc tái sử dụng nonce AEAD; HPKE quản lý sequence và nonce nội bộ.

Điểm này khác với việc dùng trực tiếp Cipher AES/GCM, nơi ứng dụng phải quản lý IV và khởi tạo lại cipher đúng cách cho mỗi thông điệp. HPKE quản lý nonce trong context để tránh sử dụng lại nonce theo đặc tả RFC 9180.

Nếu một message được chia thành nhiều chunk, hãy dùng update() cho các phần của cùng message và chỉ gọi doFinal() khi hoàn tất message đó. Giao thức phải xác định ranh giới message để hai bên giữ cùng sequence.

Không chia sẻ cùng một Cipher instance giữa nhiều thread gửi message đồng thời. Hãy quản lý context theo luồng giao thức và bảo đảm thứ tự thao tác nhất quán.

## 13. Lỗi khi chọn suite hoặc khởi tạo Cipher

Các lỗi thường xuất hiện khi key type, mode hoặc tham số không tương thích:

| Tình huống | Kết quả có thể gặp | Cách xử lý |
|---|---|---|
| Provider không có Cipher HPKE | NoSuchAlgorithmException | Dùng JDK/Provider có HPKE hoặc chọn implementation tương thích |
| Khởi tạo không cung cấp HPKEParameterSpec | InvalidKeyException | Truyền tham số HPKE khi init |
| KEM không khớp loại public/private key | InvalidKeyException hoặc InvalidAlgorithmParameterException | Kiểm tra curve/key type và KEM ID |
| KDF hoặc AEAD identifier không được hỗ trợ | InvalidAlgorithmParameterException | Chọn suite mà Provider hỗ trợ |
| Sender cung cấp encapsulation | InvalidAlgorithmParameterException | Chỉ cung cấp enc ở phía recipient |
| Recipient thiếu encapsulation | InvalidAlgorithmParameterException | Truyền enc nhận từ sender |
| withAuthKey dùng key không tương thích | InvalidAlgorithmParameterException khi init | Kiểm tra loại key và KEM có hỗ trợ auth mode |
| PSK thiếu hoặc PSK ID không đúng | Khởi tạo thất bại hoặc giải mã thất bại | Hai phía dùng cùng PSK và psk_id |
| AAD hoặc info khác nhau | Giải mã thất bại hoặc không tương thích | Đồng bộ context và metadata theo protocol |
| Ciphertext bị sửa hoặc sai thứ tự | Lỗi xác thực/giải mã | Từ chối thông điệp và ghi nhận lỗi an toàn |

of() chỉ tạo cấu hình và kiểm tra miền số identifier. Việc một Provider chấp nhận tổ hợp cụ thể thường chỉ được xác định tại Cipher.init().

Không bắt lỗi giải mã rồi trả plaintext rỗng hoặc dữ liệu chưa xác thực. Nếu AEAD tag không hợp lệ, phải coi thông điệp là không đáng tin cậy và không xử lý plaintext.

## 14. Khả năng hỗ trợ Provider và tính tương thích

Oracle JDK 26 Release Notes xác nhận hỗ trợ các KEM, KDF và AEAD identifier được định nghĩa trong RFC 9180. Oracle JDK 26 cung cấp Cipher HPKE qua SunJCE; DHKEM hỗ trợ EC trên secp256r1, secp384r1, secp521r1 và XDH Curve25519/Curve448.

Tuy vậy, HPKEParameterSpec Javadoc cảnh báo một HPKE Cipher implementation có thể hỗ trợ toàn bộ, một phần hoặc không hỗ trợ các identifier được định nghĩa trong lớp; Provider cũng có thể hỗ trợ identifier riêng. Vì vậy, code cần chạy trên nhiều JDK vendor hoặc Provider phải kiểm thử đúng runtime triển khai.

Với ứng dụng phổ thông, nên để JCA tìm Provider phù hợp:

~~~java
Cipher cipher = Cipher.getInstance("HPKE");
System.out.println(cipher.getProvider().getName());
~~~

Chỉ chỉ định Provider cụ thể khi có yêu cầu vận hành hoặc chứng nhận rõ ràng. Việc gọi Cipher.getInstance("HPKE", "SunJCE") sẽ ràng buộc ứng dụng vào Provider cụ thể và có thể giảm khả năng chuyển sang implementation khác.

Có thể kiểm tra hỗ trợ thực tế bằng cách tạo key pair, khởi tạo Cipher với suite dự kiến và chạy test vector hoặc round-trip giữa hai phía. Không chỉ kiểm tra rằng Cipher.getInstance("HPKE") thành công; một Provider có thể có HPKE nhưng không chấp nhận mọi KEM/key type/mode.

## 15. Những giới hạn bảo mật cần hiểu

HPKE cung cấp cơ chế mã hóa và xác thực thông điệp theo mode đã chọn, nhưng không thay thế toàn bộ giao thức bảo mật.

### Base mode không xác thực sender

Bất kỳ ai có public key của recipient đều có thể tạo ciphertext trong base mode. Nếu cần chứng minh người gửi là ai, hãy chọn auth mode/PSK mode phù hợp hoặc bổ sung chữ ký và xác thực ở tầng giao thức.

### Auth mode cần xác thực public key của sender

withAuthKey() ở recipient nhận public key của sender. Ứng dụng phải xác minh public key này gắn với danh tính đúng thông qua PKI, pinning hoặc cơ chế tin cậy của giao thức. HPKE không tự xác minh certificate hoặc danh tính người gửi.

### PSK phải có entropy cao

Không dùng password ngắn hoặc secret dễ đoán làm PSK. HKDF không phải password hashing function và không được thiết kế để chống tấn công từ điển với secret entropy thấp. Lấy PSK từ hệ thống quản lý secret an toàn hoặc quy trình dẫn xuất khóa có đặc tả phù hợp.

### Quản lý private key và recipient key rotation

Nếu recipient private key bị lộ, ciphertext đã lưu trước đó có thể bị giải mã nếu kẻ tấn công có đủ encapsulation và ciphertext. HPKE với recipient key tĩnh không tự cung cấp forward secrecy trước việc private key bị lộ về sau. Cần quản lý vòng đời khóa, xoay vòng key và chính sách xóa dữ liệu theo yêu cầu bảo mật.

### Chống replay và quản lý phiên bản

Sequence counter bên trong một context giúp quản lý nonce duy nhất theo context; nó không thay thế cơ chế chống replay ở tầng ứng dụng giữa các phiên hoặc các envelope được gửi lại. Ứng dụng cần message ID, timestamp, counter hoặc trạng thái replay phù hợp nếu nghiệp vụ yêu cầu.

### Không tự xây dựng định dạng giao thức thiếu ràng buộc

HPKE không tự thương lượng suite, không quản lý certificate, không định nghĩa envelope và không xác thực metadata tùy ý. Giao thức cần quy định rõ version, recipient key ID, suite, mode, info, PSK ID và cách xác thực metadata. Dùng AAD để ràng buộc những trường cần bảo vệ tính toàn vẹn.

## 16. Kiểm thử tương thích và an toàn

Một bộ kiểm thử nên bao gồm:

- Sender và recipient dùng cùng suite, mode và info.
- Thay đổi từng KEM/KDF/AEAD được phép trong profile.
- Mismatch KEM ID với loại key.
- Thiếu hoặc sai encapsulation.
- Sai PSK hoặc psk_id.
- Sai sender authentication key.
- AAD bị sửa hoặc không khớp.
- Ciphertext bị sửa, cắt ngắn hoặc đảo thứ tự.
- Gọi nhiều doFinal() liên tiếp và kiểm tra sequence đồng bộ.
- Kiểm thử giữa các Provider/JDK mà hệ thống cần tương thích.
- Kiểm tra dữ liệu envelope và key ID khi recipient có nhiều key đang hoạt động.

Dùng test vector chính thức của RFC 9180 khi xây dựng implementation hoặc kiểm tra interoperability. Test round-trip giữa cùng một Provider là cần thiết nhưng chưa đủ để chứng minh tương thích với một hệ thống HPKE khác.

Không tự triển khai lại KEM, KDF hoặc AEAD bằng code ứng dụng khi JCA đã cung cấp HPKE. Hãy sử dụng implementation đã được kiểm tra, cập nhật JDK/Provider và có quy trình đánh giá bảo mật.

## 17. Trạng thái API trong Java 26 và tương thích JDK

| Thành phần | Trạng thái trong JDK 26 |
|---|---|
| Cipher algorithm "HPKE" | Java SE API ổn định, có từ JDK 26 |
| HPKEParameterSpec | Java SE API ổn định, có từ JDK 26 |
| KEM/KDF/AEAD identifiers | Theo RFC 9180 và các constant trong HPKEParameterSpec |
| Provider implementation | Phụ thuộc JDK vendor/Provider; Oracle JDK 26 cung cấp qua SunJCE |
| Preview/incubator flag | Không cần |

Các API thuộc module java.base, package javax.crypto và javax.crypto.spec. Không cần --enable-preview hoặc --add-modules.

Nếu biên dịch trực tiếp với JDK 26 và tham chiếu HPKEParameterSpec, runtime cũ hơn Java 26 không có class/method này và không thể chạy binary như thể API đã tồn tại. Nếu phải hỗ trợ runtime cũ, cần adapter hoặc implementation khác đã được kiểm tra và thống nhất giao thức.

JDK 26 Release Notes ghi nhận HPKE là tính năng bảo mật mới với mã theo JDK-8325448. Đây không phải preview feature. Tuy nhiên, tính ổn định của API Java không tự bảo đảm mọi Provider hoặc mọi hệ thống đối tác đều hỗ trợ cùng một bộ thuật toán; khả năng tương thích phải được xác minh ở cả hai đầu.

## 18. Checklist chọn HPKEParameterSpec

- [ ] Recipient key type và curve đã được xác định.
- [ ] KEM ID khớp public/private key.
- [ ] KDF và AEAD thuộc profile đã thống nhất giữa hai bên.
- [ ] Mode được chọn theo yêu cầu xác thực sender.
- [ ] withInfo() chỉ dùng khi hai bên có cùng context bytes.
- [ ] PSK và psk_id luôn được cấu hình cùng nhau.
- [ ] PSK có ít nhất 32 byte entropy; không dùng password trực tiếp.
- [ ] Auth mode dùng sender private key ở phía gửi và sender public key ở phía nhận.
- [ ] Encapsulation được lấy bằng senderCipher.getIV() và chuyển cho recipient qua withEncapsulation().
- [ ] AAD được truyền giống nhau cho từng message.
- [ ] Message boundaries và thứ tự doFinal() đồng bộ giữa hai phía.
- [ ] Ciphertext, encapsulation, suite ID và key ID được đóng gói theo protocol đã version hóa.
- [ ] Provider và JDK mục tiêu đã được kiểm thử bằng test vector và integration test.
- [ ] Có quy trình quản lý private key, key rotation, replay protection và xác thực danh tính.

## Kết luận

HPKEParameterSpec là lớp cấu hình bất biến cho Cipher HPKE trong Java 26. of(kem_id, kdf_id, aead_id) chọn bộ KEM, KDF và AEAD ở base mode; withInfo(), withPsk(), withAuthKey() và withEncapsulation() bổ sung ngữ cảnh, xác thực và dữ liệu KEM theo đúng vai trò từng phía. KEM phải khớp loại khóa người nhận, còn KDF và AEAD phải được hai bên thống nhất. Sender lấy encapsulation qua Cipher.getIV(); recipient truyền nó bằng withEncapsulation(). HPKE Cipher có thể xử lý nhiều message theo sequence nội bộ, nhưng sender và recipient phải gọi doFinal() cùng số lần và cùng thứ tự. Trong Java 26, HPKE là API ổn định thuộc java.base, không cần preview flag; việc chọn suite, xác thực danh tính, đóng gói dữ liệu, quản lý khóa và chống replay vẫn là trách nhiệm của giao thức ứng dụng.

## Tài liệu tham khảo

- [Java SE 26 API – HPKEParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html)
- [Java SE 26 API – Cipher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html)
- [Oracle JDK 26 Release Notes – Hybrid Public Key Encryption](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [Java Cryptography Architecture Reference Guide – Securely Exchanging Messages with HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
- [JDK 26 Providers Documentation – SunJCE](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html)
- [RFC 9180 – Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html)
