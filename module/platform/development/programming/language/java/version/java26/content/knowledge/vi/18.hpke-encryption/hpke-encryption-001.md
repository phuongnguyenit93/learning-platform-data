# HPKE trong Cipher của Java 26 và bài toán trao đổi dữ liệu mã hóa

Java 26 bổ sung thuật toán cipher có tên **HPKE** theo RFC 9180 (Hybrid Public Key Encryption). HPKE cho phép bên gửi mã hóa dữ liệu bằng public key của người nhận mà không cần chia sẻ trước một khóa đối xứng riêng cho từng phiên. Nó kết hợp ba thành phần: **KEM** để thiết lập shared secret, **KDF** để dẫn xuất khóa, và **AEAD** để mã hóa có xác thực.

Trong Java, API được dùng qua **Cipher.getInstance("HPKE")** và **HPKEParameterSpec**. Đây là API Java SE chính thức, có từ JDK 26, không phải preview hoặc incubator. Điểm khác biệt quan trọng so với cipher thông thường là HPKE không dùng chuỗi transformation **algorithm/mode/padding**, phải truyền **HPKEParameterSpec** khi khởi tạo, và **Cipher.getIV()** ở phía gửi trả về thông điệp encapsulation của KEM.

Bài học này trình bày cách hai bên trao đổi dữ liệu, cách chọn KEM/KDF/AEAD và mode xác thực, cách truyền **info**, AAD và encapsulation, cùng các giới hạn cần xử lý khi đưa HPKE vào một giao thức ứng dụng.

## 1. HPKE giải quyết bài toán nào?

Giả sử một ứng dụng cần gửi dữ liệu nhạy cảm đến một dịch vụ. Dịch vụ đã có cặp khóa bất đối xứng và công bố public key cho các client. Client cần mã hóa dữ liệu để chỉ dịch vụ có private key tương ứng mới giải mã được.

Mô hình mã hóa lai thông thường cần kết hợp một phép trao đổi khóa hoặc mã hóa khóa với một cipher đối xứng. Nếu tự ghép các API, ứng dụng phải tự chịu trách nhiệm về KDF, context, nonce, định dạng thông điệp và các quy tắc chống lỗi. Việc ghép sai có thể làm mất tính bảo mật dù từng thuật toán thành phần đều mạnh.

HPKE chuẩn hóa cách ghép ba thành phần:

| Thành phần | Vai trò | Ví dụ trong RFC 9180 |
|---|---|---|
| KEM (Key Encapsulation Mechanism) | Thiết lập shared secret giữa sender và recipient; tạo encapsulation để gửi kèm ciphertext | DHKEM(X25519, HKDF-SHA256) |
| KDF (Key Derivation Function) | Dẫn xuất key và nonce từ shared secret cùng context | HKDF-SHA256 |
| AEAD (Authenticated Encryption with Associated Data) | Mã hóa plaintext và xác thực ciphertext/AAD | AES-128-GCM |

Sender dùng public key của recipient để tạo một shared secret dùng cho context. Recipient dùng private key tương ứng và encapsulation nhận được để tái tạo cùng secret. Từ secret, hai bên dẫn xuất trạng thái AEAD giống nhau và trao đổi ciphertext.

Từ "hybrid" trong tên HPKE nói đến việc kết hợp KEM, KDF và AEAD. Nó không tự có nghĩa là thuật toán lai hậu lượng tử (post-quantum). Các bộ DHKEM được định nghĩa trong RFC 9180 là các bộ dựa trên Diffie-Hellman; không tự suy ra HPKE RFC 9180 đang dùng ML-KEM.

## 2. HPKE có trong Java 26 và trạng thái API

JDK 26 thêm thuật toán **HPKE** cho **javax.crypto.Cipher** và lớp **javax.crypto.spec.HPKEParameterSpec** (JDK-8325448). Các thành phần này là API Java SE chính thức, có từ release 26.

| Thành phần | Trạng thái trong Java 26 | Cách sử dụng |
|---|---|---|
| **Cipher** với algorithm **HPKE** | API chính thức | **Cipher.getInstance("HPKE")** |
| **HPKEParameterSpec** | API chính thức, **Since: 26** | Chọn KEM, KDF, AEAD, mode và context |
| RFC 9180 | Chuẩn giao thức | Định nghĩa suite, mode và key schedule |
| **--enable-preview** | Không cần | HPKE không phải preview feature |
| **--add-modules** | Không cần cho API trong **java.base** | **javax.crypto** thuộc module **java.base** |

HPKE không phải transformation kiểu **AES/GCM/NoPadding**. Cách gọi đúng là:

~~~java
Cipher cipher = Cipher.getInstance("HPKE");
~~~

Không thêm **/mode/padding** phía sau tên HPKE. Cũng không khởi tạo cipher bằng **init(opmode, key)** đơn thuần: HPKE yêu cầu **HPKEParameterSpec** khi gọi **init(opmode, key, params)**.

Trong Oracle JDK 26, SunJCE cung cấp cipher HPKE. Với JDK hoặc provider khác, cần kiểm tra provider thực tế bằng **Cipher.getInstance("HPKE")**; không giả định mọi provider đều hỗ trợ cùng suite hoặc mode.

## 3. Chọn KEM, KDF và AEAD

**HPKEParameterSpec.of(kemId, kdfId, aeadId)** tạo một bộ tham số với ba algorithm identifier theo RFC 9180. Các hằng số trong API Java giúp tránh ghi trực tiếp số ID.

### 3.1. KEM

Các KEM identifier được **HPKEParameterSpec** định nghĩa gồm:

| Hằng số Java | KEM |
|---|---|
| **KEM_DHKEM_P_256_HKDF_SHA256** | DHKEM với P-256 và HKDF-SHA256 |
| **KEM_DHKEM_P_384_HKDF_SHA384** | DHKEM với P-384 và HKDF-SHA384 |
| **KEM_DHKEM_P_521_HKDF_SHA512** | DHKEM với P-521 và HKDF-SHA512 |
| **KEM_DHKEM_X25519_HKDF_SHA256** | DHKEM với X25519 và HKDF-SHA256 |
| **KEM_DHKEM_X448_HKDF_SHA512** | DHKEM với X448 và HKDF-SHA512 |

Kiểu khóa phải tương thích với KEM. Ví dụ, KEM X25519 cần public/private key X25519; các KEM P-256/P-384/P-521 cần EC key trên đúng named curve.

Trong ví dụ thực hành, X25519 thường là lựa chọn gọn và được tài liệu JDK 26 minh họa trực tiếp:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
KeyPair recipientKeyPair = generator.generateKeyPair();
~~~

Trong production, recipient thường tạo và quản lý key pair trong một quy trình riêng, lưu private key trong keystore, HSM hoặc hệ thống quản lý khóa phù hợp. Sender chỉ nhận public key đã được xác thực.

### 3.2. KDF

Java 26 định nghĩa các KDF identifier:

- **KDF_HKDF_SHA256**
- **KDF_HKDF_SHA384**
- **KDF_HKDF_SHA512**

KDF dẫn xuất các giá trị cần thiết cho AEAD từ shared secret và context HPKE. Không tự thay KDF hoặc ghép thêm một hàm băm theo cách riêng nếu giao thức đã định nghĩa suite. Hai bên phải dùng cùng identifier.

### 3.3. AEAD

Các AEAD identifier chính:

- **AEAD_AES_128_GCM**
- **AEAD_AES_256_GCM**
- **AEAD_CHACHA20_POLY1305**

**EXPORT_ONLY** cũng là identifier được định nghĩa trong RFC 9180, phục vụ trường hợp export secret thay vì mã hóa ciphertext thông thường. Khi cần mã hóa thông điệp, hãy chọn một AEAD có chức năng mã hóa/xác thực như AES-GCM hoặc ChaCha20-Poly1305.

Oracle JDK 26 release notes xác nhận các KEM, KDF và AEAD identifier được định nghĩa trong RFC 9180 được hỗ trợ bởi triển khai HPKE của JDK. Tuy nhiên, đặc tả **HPKEParameterSpec** lưu ý một provider bất kỳ có thể hỗ trợ toàn bộ, một phần hoặc không hỗ trợ các identifier này. Vì vậy, ứng dụng dùng provider khác cần kiểm tra trên đúng runtime triển khai.

## 4. Base mode: mã hóa bằng public key của người nhận

**HPKEParameterSpec.of(...)** tạo spec ở **mode_base** với **info** rỗng. Đây là mode đơn giản nhất:

1. Recipient tạo cặp khóa và công bố public key qua một kênh có thể xác thực.
2. Sender khởi tạo HPKE **Cipher** ở **ENCRYPT_MODE** bằng public key của recipient.
3. Sender lấy KEM encapsulation từ **Cipher.getIV()**.
4. Sender mã hóa plaintext bằng **doFinal()**.
5. Sender gửi encapsulation và ciphertext cho recipient.
6. Recipient tạo HPKE spec có cùng suite, **info** và encapsulation.
7. Recipient khởi tạo cipher ở **DECRYPT_MODE** bằng private key của mình rồi giải mã ciphertext.

Base mode bảo vệ nội dung khỏi người không có private key của recipient và xác thực ciphertext bằng AEAD. Tuy nhiên, base mode **không xác thực danh tính sender**: bất kỳ ai biết public key của recipient đều có thể tạo một ciphertext hợp lệ gửi đến recipient.

Base mode cũng không tự xác minh public key mà sender nhận được có thực sự thuộc về recipient dự kiến. Ứng dụng phải xác thực public key qua certificate, pinning, directory tin cậy hoặc một cơ chế phân phối khóa phù hợp.

## 5. Ví dụ hoàn chỉnh: gửi và nhận một thông điệp

Ví dụ sau dùng X25519, HKDF-SHA256 và AES-128-GCM. Cặp khóa được tạo ngay trong chương trình để minh họa; trong ứng dụng thật, recipient private key cần được quản lý lâu dài và bảo vệ riêng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.HPKEParameterSpec;

public class HpkeExchange {
    private static final int KEM =
        HPKEParameterSpec.KEM_DHKEM_X25519_HKDF_SHA256;
    private static final int KDF =
        HPKEParameterSpec.KDF_HKDF_SHA256;
    private static final int AEAD =
        HPKEParameterSpec.AEAD_AES_128_GCM;

    public static void main(String[] args) throws Exception {
        // Recipient tạo key pair. Production cần lưu private key an toàn.
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        byte[] info =
            "example.billing/v1".getBytes(StandardCharsets.UTF_8);
        byte[] aad =
            "content-type=text/plain;message-id=42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext =
            "Thông điệp bí mật".getBytes(StandardCharsets.UTF_8);

        // Sender: dùng public key của recipient.
        Cipher sender = Cipher.getInstance("HPKE");
        HPKEParameterSpec senderParams =
            HPKEParameterSpec.of(KEM, KDF, AEAD)
                .withInfo(info);

        sender.init(
            Cipher.ENCRYPT_MODE,
            recipientKeys.getPublic(),
            senderParams
        );

        // Đây là KEM encapsulation cần gửi cho recipient.
        // Cipher.getIV() được API HPKE dùng để trả về encapsulation.
        byte[] encapsulation = sender.getIV();

        // AAD không được mã hóa nhưng được AEAD xác thực.
        sender.updateAAD(aad);
        byte[] ciphertext = sender.doFinal(plaintext);

        // Recipient: dùng cùng suite, info và encapsulation.
        Cipher recipient = Cipher.getInstance("HPKE");
        HPKEParameterSpec recipientParams =
            HPKEParameterSpec.of(KEM, KDF, AEAD)
                .withInfo(info)
                .withEncapsulation(encapsulation);

        recipient.init(
            Cipher.DECRYPT_MODE,
            recipientKeys.getPrivate(),
            recipientParams
        );

        recipient.updateAAD(aad);
        byte[] recovered = recipient.doFinal(ciphertext);

        if (!Arrays.equals(plaintext, recovered)) {
            throw new IllegalStateException("Plaintext mismatch");
        }

        System.out.println(
            new String(recovered, StandardCharsets.UTF_8)
        );
    }
}
~~~

Biên dịch và chạy bằng JDK 26:

~~~sh
javac --release 26 HpkeExchange.java
java HpkeExchange
~~~

Không cần **--enable-preview** hoặc **--add-modules**.

### 5.1. Đọc đúng vai trò của encapsulation

Sau khi sender gọi **init(ENCRYPT_MODE, recipientPublicKey, params)**, KEM tạo encapsulation. Java cho phép lấy giá trị này bằng **sender.getIV()**.

Tên method **getIV()** được tái sử dụng từ API **Cipher**, nhưng với HPKE giá trị trả về là **KEM encapsulation**, không phải một IV mà ứng dụng phải tự tạo hoặc tự quản lý như khi dùng trực tiếp AES-GCM.

Encapsulation không phải private key hoặc shared secret. Nó là dữ liệu công khai cần gửi cho recipient để recipient dùng private key tái tạo shared secret. Nếu thiếu encapsulation, recipient không thể khởi tạo HPKE context tương ứng; nếu đưa encapsulation vào phía sender, việc khởi tạo sẽ không hợp lệ.

### 5.2. Dữ liệu cần truyền trong envelope

Một giao thức ứng dụng thường cần đóng gói tối thiểu:

| Trường | Mục đích |
|---|---|
| Version | Phiên bản envelope/giao thức ứng dụng |
| Suite identifiers | KEM, KDF và AEAD đã chọn |
| Recipient key ID | Xác định private key recipient cần dùng |
| Encapsulation (**enc**) | KEM message lấy từ sender **getIV()** |
| AAD hoặc header được xác định | Dữ liệu ngoài ciphertext cần xác thực |
| Ciphertext | Kết quả **doFinal()** |

Có thể dùng CBOR, JSON với quy tắc canonical hóa, protobuf hoặc định dạng nhị phân riêng. Điều quan trọng là hai bên phải thống nhất encoding của các trường dùng làm AAD. Nếu AAD được tái tạo từ header, phải canonicalize giống hệt trước khi gọi **updateAAD()**.

Không gửi private key, shared secret hoặc PSK trong envelope. Các algorithm identifier nhận từ mạng cũng cần được kiểm tra với allowlist trước khi tạo **HPKEParameterSpec**; không cho đối phương tùy ý ép ứng dụng dùng suite yếu hoặc ngoài chính sách.

## 6. Phân biệt info và AAD

**info** và AAD đều là dữ liệu bổ sung, nhưng có vai trò khác nhau.

| Thuộc tính | **info** | AAD |
|---|---|---|
| API Java | **HPKEParameterSpec.withInfo(byte[])** | **Cipher.updateAAD(byte[])** |
| Thời điểm cung cấp | Khi tạo **HPKEParameterSpec**, trước **init()** | Sau **init()**, trước dữ liệu của từng thông điệp |
| Vai trò | Context input cho key schedule của HPKE, giúp tách miền sử dụng khóa | Dữ liệu ngoài ciphertext được AEAD xác thực |
| Có được mã hóa không? | Không | Không |
| Hai bên cần giống nhau? | Có | Có cho từng thông điệp |
| Phạm vi | Context của HPKE session | Từng lần mã hóa/giải mã |

**info** có thể chứa định danh ứng dụng, phiên bản giao thức, loại dữ liệu hoặc mục đích sử dụng để tách context. Hai bên phải thống nhất chính xác byte sequence này.

AAD phù hợp để ràng buộc metadata của một thông điệp, ví dụ tenant ID, message ID, content type hoặc header nghiệp vụ. Nếu metadata bị thay đổi trên đường truyền, kiểm tra AEAD sẽ thất bại khi recipient giải mã.

AAD không che giấu metadata. Nếu header có dữ liệu nhạy cảm, hãy đưa phần đó vào plaintext mã hóa thay vì chỉ đặt trong AAD.

Không dùng **info** như chữ ký số hoặc chứng minh danh tính. Không dùng AAD thay cho xác thực public key của recipient hay xác thực sender.

## 7. Gửi nhiều thông điệp trong cùng HPKE context

HPKE hỗ trợ nhiều thông điệp liên tiếp sau một lần khởi tạo. Mỗi lần **doFinal()** hoàn tất một phép mã hóa/giải mã HPKE, dùng nonce riêng được dẫn xuất từ sequence counter nội bộ theo RFC 9180.

Ví dụ:

~~~java
// Sender đã init một lần.
sender.updateAAD(aad1);
byte[] ciphertext1 = sender.doFinal(message1);

sender.updateAAD(aad2);
byte[] ciphertext2 = sender.doFinal(message2);

// Recipient đã init cùng context và cùng encapsulation.
recipient.updateAAD(aad1);
byte[] plaintext1 = recipient.doFinal(ciphertext1);

recipient.updateAAD(aad2);
byte[] plaintext2 = recipient.doFinal(ciphertext2);
~~~

Các quy tắc bắt buộc:

- Số lần và thứ tự gọi **doFinal()** ở hai bên phải khớp.
- Mỗi lần giải mã nhận đúng một ciphertext hoàn chỉnh tương ứng với một lần mã hóa.
- AAD cho từng thông điệp phải giống nhau giữa sender và recipient.
- Không tự đặt IV cho từng thông điệp; HPKE quản lý nonce theo sequence counter.
- Không hoán đổi thứ tự ciphertext hoặc xử lý song song cùng một context theo cách làm sai thứ tự.
- Khi bắt đầu một context/session độc lập, khởi tạo cipher context mới và truyền encapsulation mới.

Cipher HPKE là đối tượng có trạng thái. Không chia sẻ cùng một instance sender/recipient cho nhiều thread gọi đồng thời. Nếu ứng dụng cần gửi song song hoặc nhiều luồng dữ liệu độc lập, hãy thiết kế context riêng cho từng luồng và quản lý framing/sequence rõ ràng.

## 8. Các mode xác thực của HPKE

RFC 9180 định nghĩa bốn mode. **HPKEParameterSpec.of(...)** bắt đầu ở **mode_base**; các method bổ sung chọn mode có PSK hoặc authentication key.

| Mode | Cách cấu hình trong Java | Đặc điểm |
|---|---|---|
| Base | **of(kem, kdf, aead)** | Mã hóa đến recipient; không xác thực sender |
| PSK | **withPsk(psk, pskId)** ở cả hai phía | Kết hợp shared PSK đã được phân phối an toàn |
| Auth | **withAuthKey(key)** ở cả hai phía | Sender chứng minh sở hữu static private key |
| Auth + PSK | Dùng cả **withAuthKey()** và **withPsk()** ở hai phía | Kết hợp xác thực khóa sender và PSK |

### 8.1. PSK mode

PSK mode yêu cầu hai bên có cùng pre-shared key và cùng **psk_id**:

~~~java
HPKEParameterSpec params =
    HPKEParameterSpec.of(KEM, KDF, AEAD)
        .withPsk(psk, pskId)
        .withInfo(info);
~~~

Sender và recipient phải gọi **withPsk()** với cùng PSK và cùng identifier. PSK cần được tạo, lưu trữ, phân phối và xoay vòng bằng một cơ chế quản lý bí mật riêng. Không lấy mật khẩu người dùng trực tiếp làm **SecretKey**, không hard-code PSK trong source code và không truyền PSK qua cùng envelope đang được mã hóa.

### 8.2. Auth mode

Auth mode dùng khóa bất đối xứng dài hạn của sender:

- Sender gọi **withAuthKey()** với **private key của chính sender**.
- Recipient gọi **withAuthKey()** với **public key tương ứng của sender**.

~~~java
// Sender
HPKEParameterSpec senderParams =
    HPKEParameterSpec.of(KEM, KDF, AEAD)
        .withAuthKey(senderPrivateKey);

// Recipient
HPKEParameterSpec recipientParams =
    HPKEParameterSpec.of(KEM, KDF, AEAD)
        .withAuthKey(senderPublicKey)
        .withEncapsulation(encapsulation);
~~~

Recipient phải biết và tin cậy rằng public key đó thuộc đúng sender. Việc chỉ nhận public key từ cùng thông điệp không tạo ra xác thực danh tính.

Không phải mọi KEM/provider đều hỗ trợ mọi mode. Nếu mode hoặc key không tương thích với KEM, **Cipher.init()** có thể ném **InvalidAlgorithmParameterException** hoặc **InvalidKeyException**.

### 8.3. Auth + PSK

Khi giao thức yêu cầu cả hai yếu tố, hai bên cấu hình cả hai:

~~~java
HPKEParameterSpec params =
    HPKEParameterSpec.of(KEM, KDF, AEAD)
        .withPsk(psk, pskId)
        .withAuthKey(authenticationKey)
        .withInfo(info);
~~~

Vai trò khóa vẫn theo quy tắc auth mode: sender dùng private key của mình; recipient dùng public key sender. PSK và PSK identifier phải giống nhau ở cả hai phía.

Không chọn mode chỉ vì tên nghe mạnh hơn. Hãy xác định rõ ai cần được xác thực, khóa nào đã được tin cậy, PSK được phân phối thế nào và provider mục tiêu hỗ trợ mode nào.

## 9. HPKE không tự thay thế xác thực danh tính và TLS

HPKE bảo vệ dữ liệu ở tầng thông điệp. Nó không tự định nghĩa toàn bộ quy trình kết nối mạng, chứng thực certificate, thương lượng phiên bản giao thức, quản lý người dùng hoặc chống replay ở cấp ứng dụng.

| Nhu cầu | HPKE tự đáp ứng? | Phần ứng dụng/giao thức cần làm |
|---|---|---|
| Bí mật dữ liệu với recipient private key | Có | Bảo vệ private key và xác thực public key được công bố |
| Phát hiện ciphertext/AAD bị sửa | Có, qua AEAD | Xử lý lỗi xác thực an toàn |
| Xác thực sender trong base mode | Không | Dùng auth mode hoặc một cơ chế chữ ký/xác thực riêng |
| Xác thực public key recipient | Không | Certificate, pinning, directory hoặc trust model |
| Chống replay qua nhiều session | Không tự động | Nonce nghiệp vụ, message ID, timestamp và trạng thái chống replay |
| Định tuyến, framing, retry và thứ tự truyền | Không | Giao thức truyền tải |
| Quản lý chứng chỉ và TLS handshake | Không | Dùng JSSE/TLS khi cần bảo vệ kênh truyền |

Không xem HPKE là thay thế TLS. TLS bảo vệ kết nối và có cơ chế xác thực peer, thương lượng cipher suite, chống replay ở cấp record và quản lý session. HPKE phù hợp khi cần mã hóa payload đến một public key, ví dụ dữ liệu được lưu hoặc chuyển tiếp qua hệ thống trung gian mà không muốn trung gian đọc được nội dung.

Có thể dùng HPKE bên trong một giao thức chạy trên TLS, nhưng hai lớp có mục đích khác nhau. Không bỏ TLS chỉ vì payload đã được mã hóa HPKE nếu ứng dụng vẫn cần bảo vệ metadata, xác thực endpoint và toàn vẹn kênh truyền.

## 10. Replay, thứ tự thông điệp và quản lý context

Sequence counter nội bộ bảo đảm các lần **doFinal()** trong cùng context dùng nonce khác nhau. Điều đó không tự tạo kho trạng thái chống replay cho toàn bộ ứng dụng.

Nếu một envelope hoàn chỉnh bị phát lại và ứng dụng tạo một HPKE context mới từ cùng recipient private key và encapsulation, HPKE không biết message đó đã được xử lý trước đó trong một session khác. Vì vậy, giao thức cần message ID, version, timestamp, counter nghiệp vụ hoặc trạng thái chống replay riêng.

Với nhiều thông điệp trong cùng context, recipient phải giải mã theo đúng thứ tự. Nếu mất một ciphertext, bị trùng, hoặc đến sai thứ tự, sequence counter hai bên sẽ lệch và các thông điệp tiếp theo có thể không giải mã được. Ứng dụng cần định nghĩa rõ hành vi retry, resynchronization và khi nào phải thiết lập context mới.

Không dùng một HPKE context chung cho nhiều luồng độc lập nếu không có cơ chế phân luồng và đồng bộ sequence rõ ràng. Không lưu ciphertext mà bỏ encapsulation hoặc suite metadata cần thiết để tái tạo context ở phía nhận.

## 11. Quản lý khóa và vòng đời recipient key

Recipient private key là tài sản nhạy cảm nhất trong base mode. Nếu private key bị lộ, kẻ tấn công có thể giải mã các envelope đã thu thập có encapsulation tương ứng. HPKE với static recipient key không tự cung cấp forward secrecy cho dữ liệu lưu trữ dài hạn.

Các nguyên tắc vận hành:

- Sinh khóa bằng **KeyPairGenerator**/provider đáng tin cậy hoặc hệ thống quản lý khóa được tổ chức phê duyệt.
- Giữ private key trong keystore, HSM hoặc KMS phù hợp; không ghi private key ra log hoặc envelope.
- Phân phối public key qua kênh xác thực và gắn key ID/version rõ ràng.
- Khi rotate recipient key, phát hành key ID mới và có chính sách xử lý envelope cũ.
- Giới hạn quyền truy cập private key và ghi nhận hoạt động sử dụng khóa.
- Có quy trình thu hồi hoặc thay khóa khi nghi ngờ lộ lọt.
- Không dùng lại private key giữa các môi trường test, staging và production nếu chính sách yêu cầu cô lập.

Nếu cần forward secrecy cho phiên trao đổi tương tác, hãy đánh giá một giao thức key exchange/session được thiết kế cho mục tiêu đó. Không suy ra rằng HPKE base mode với recipient static key tự có forward secrecy chỉ vì sender dùng ephemeral KEM key.

## 12. Kiểm tra provider và lỗi khi khởi tạo

JCA chọn provider theo thứ tự ưu tiên khi gọi **Cipher.getInstance("HPKE")**. Có thể xem provider được chọn:

~~~java
Cipher cipher = Cipher.getInstance("HPKE");
System.out.println(cipher.getProvider().getName());
~~~

Ứng dụng phổ thông nên để JCA chọn provider thay vì hard-code **SunJCE**. Nếu cần HSM hoặc provider đã được chứng nhận, phải xác nhận provider đó thực sự hỗ trợ HPKE, KEM, KDF, AEAD và mode đang dùng.

Một số lỗi có thể gặp:

| Exception | Nguyên nhân thường gặp |
|---|---|
| **NoSuchAlgorithmException** | Provider được chọn không cung cấp **Cipher** algorithm **HPKE** |
| **InvalidKeyException** | Key type không phù hợp với KEM hoặc không có implementation hỗ trợ key đó |
| **InvalidAlgorithmParameterException** | Suite identifier không được hỗ trợ, thiếu encapsulation ở recipient hoặc tham số/mode không hợp lệ |
| **AEADBadTagException** | Ciphertext hoặc AAD bị thay đổi, sai khóa/context, sai thứ tự hoặc dữ liệu không hợp lệ |
| **BadPaddingException** | Lỗi xác thực/decryption được biểu diễn qua lớp exception cha trong chữ ký API |

Không gửi chi tiết exception mật mã nội bộ cho client từ xa. Ở ranh giới giao thức, trả lỗi chung và ghi log an toàn ở phía server; không ghi plaintext, private key, PSK hoặc dữ liệu bí mật vào log.

## 13. HPKE khác KEM API và các cipher truyền thống ra sao?

Java đã có **javax.crypto.KEM** từ JDK 21. KEM API cho phép encapsulate/decapsulate để hai bên có shared secret. HPKE đi xa hơn: nó chuẩn hóa KEM, KDF và AEAD thành một scheme mã hóa thông điệp hoàn chỉnh.

| API/cách tiếp cận | Cung cấp | Ứng dụng còn phải tự làm |
|---|---|---|
| **javax.crypto.KEM** | Encapsulation, decapsulation và shared secret | KDF, key schedule, AEAD, nonce, framing và protocol rules |
| **Cipher.getInstance("AES/GCM/NoPadding")** | Mã hóa đối xứng có xác thực | Thiết lập và phân phối key, nonce uniqueness, key rotation |
| **Cipher.getInstance("HPKE")** | KEM + KDF + AEAD theo RFC 9180 | Xác thực public key, envelope/framing, replay policy, key lifecycle |
| TLS/JSSE | Kênh truyền có thương lượng và xác thực theo cấu hình | Quản lý certificate/trust, endpoint identity và ứng dụng protocol |

Nếu mục tiêu chỉ là thiết lập shared secret cho một giao thức tự thiết kế, KEM API có thể là thành phần phù hợp nhưng phải có thiết kế protocol và security review riêng. Nếu mục tiêu là mã hóa thông điệp đến public key theo RFC 9180, dùng HPKE tránh tự ghép các primitive.

Không tự viết lại HPKE bằng cách gọi KEM, HKDF và AES-GCM thủ công nếu không có lý do và review mật mã chuyên sâu. Các chi tiết context, label, sequence number, nonce và mode trong RFC rất dễ bị triển khai sai.

## 14. Kiểm thử interoperability và tính toàn vẹn

Một bài test round-trip trong cùng JVM chỉ xác nhận sender và recipient trong cùng provider có thể giải mã lẫn nhau. Nó chưa đủ để chứng minh hai implementation khác nhau tuân thủ RFC 9180.

Nên kiểm tra:

1. Dùng bộ test vector chính thức của RFC 9180 cho suite và mode được triển khai.
2. So sánh với một implementation độc lập khác nếu hệ thống cần interoperability.
3. Xác nhận hai bên thống nhất KEM/KDF/AEAD identifier và mode.
4. Xác nhận **info**, PSK/PSK ID hoặc authentication keys giống nhau.
5. Thay đổi một byte của encapsulation, ciphertext hoặc AAD và xác nhận giải mã thất bại.
6. Thử sai recipient key, sai suite, thiếu encapsulation và key type không phù hợp.
7. Kiểm tra nhiều lần **doFinal()** theo đúng thứ tự và kiểm tra trường hợp mất/đảo/trùng thông điệp.
8. Kiểm tra key rotation và lựa chọn key ID khi có nhiều recipient key.
9. Kiểm tra provider thực tế trong runtime production, không chỉ trên máy lập trình viên.

Đối với lỗi xác thực, kiểm tra rằng ứng dụng không trả một phần plaintext trước khi tag được xác minh. Với **doFinal()** của AEAD, chỉ sử dụng plaintext sau khi thao tác hoàn tất thành công.

## 15. Trạng thái phiên bản và tương thích

HPKE trong JDK 26 là API Java SE ổn định. **HPKEParameterSpec** có **Since: 26**; JDK 26 release notes ghi nhận **Cipher** algorithm HPKE theo JDK-8325448.

| Phiên bản | Hướng dẫn |
|---|---|
| JDK 25 trở xuống | Không có API **HPKEParameterSpec** Java SE; cần provider/thư viện ngoài nếu muốn HPKE |
| JDK 26 | Dùng **Cipher.getInstance("HPKE")** và **HPKEParameterSpec**; API chính thức, không preview |
| JDK 27 trở lên | Kiểm tra Javadoc và provider của JDK đích; không cần preview flag cho API Java SE đã được phát hành từ JDK 26 |

Không nhầm **HPKEParameterSpec** với **KEM** API từ JDK 21 hoặc **PEMDecoder** preview của JDK 26. HPKE là cipher algorithm có tham số riêng; PEM là định dạng biểu diễn khóa/chứng chỉ; KEM API là primitive encapsulation/decapsulation.

Khi nâng cấp JDK hoặc thay provider, chạy lại interoperability test và kiểm tra suite/mode được hỗ trợ. Đừng chỉ dựa vào việc source code biên dịch thành công.

## 16. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi **Cipher.getInstance("HPKE/GCM/NoPadding")** | Không đúng tên transformation của HPKE | Dùng duy nhất **"HPKE"** |
| Không truyền **HPKEParameterSpec** khi init | HPKE không thể chọn suite/context | Dùng **init(opmode, key, spec)** |
| Sender dùng private key recipient | Sai vai trò khóa | Sender dùng recipient public key; recipient dùng private key |
| Không truyền encapsulation | Recipient không tái tạo được shared secret | Gửi giá trị **sender.getIV()** và dùng **withEncapsulation()** |
| Nghĩ **getIV()** là nonce cần tự quản lý | Nhầm KEM message với IV AEAD thông thường | Xem đây là encapsulation công khai của KEM |
| Hai bên chọn suite khác nhau | Không tạo cùng key schedule | Thống nhất KEM/KDF/AEAD identifier |
| Hai bên dùng **info** khác nhau | Context key schedule khác nhau | Định nghĩa và tái tạo **info** chính xác |
| AAD khác nhau | AEAD authentication thất bại | Canonicalize header và dùng cùng AAD |
| Nghĩ base mode xác thực sender | Bất kỳ ai có recipient public key đều có thể gửi | Dùng auth/PSK mode hoặc chữ ký/xác thực riêng |
| Tin public key lấy trực tiếp từ message | Có thể bị thay khóa recipient | Xác thực public key qua trust mechanism |
| Gọi nhiều **doFinal()** không đồng bộ thứ tự | Sequence counter hai phía lệch | Giữ số lần và thứ tự message giống nhau |
| Reuse context cho nhiều thread đồng thời | Trạng thái HPKE/sequence có thể bị đua | Dùng context riêng hoặc serialize truy cập |
| Nghĩ HPKE tự chống replay qua session | Envelope cũ có thể được xử lý lại trong context mới | Thêm message ID/counter và trạng thái chống replay |
| Dùng HPKE như TLS replacement | Thiếu endpoint auth, negotiation và transport protection | Dùng TLS/JSSE cho kênh truyền; HPKE bảo vệ payload khi cần |
| Cho phép suite ID tùy ý từ mạng | Có thể dẫn tới suite ngoài chính sách | Kiểm tra allowlist trước khi init |

## 17. Checklist triển khai HPKE

- [ ] Xác định HPKE có đúng là bài toán cần mã hóa payload tới recipient public key hay không.
- [ ] Chọn suite RFC 9180 phù hợp với yêu cầu bảo mật và interoperability.
- [ ] Kiểm tra provider mục tiêu có **Cipher** algorithm **HPKE** và hỗ trợ suite/mode đã chọn.
- [ ] Xác thực recipient public key trước khi sender sử dụng.
- [ ] Quản lý recipient private key bằng keystore/HSM/KMS phù hợp.
- [ ] Sender dùng public key recipient; recipient dùng private key tương ứng.
- [ ] Truyền encapsulation lấy từ **Cipher.getIV()** trong envelope.
- [ ] Hai phía dùng cùng KEM/KDF/AEAD và cùng **info**.
- [ ] Định nghĩa AAD từ metadata có encoding ổn định và tái tạo được.
- [ ] Chọn base, PSK, auth hoặc auth_psk theo yêu cầu xác thực thật sự.
- [ ] Không gửi PSK hoặc private key trong envelope.
- [ ] Đồng bộ thứ tự và số lần **doFinal()** trong mỗi context.
- [ ] Dùng context riêng cho session/luồng độc lập và không chia sẻ Cipher đồng thời.
- [ ] Có message ID/counter và chính sách chống replay ở tầng ứng dụng.
- [ ] Kiểm thử tamper, sai key, sai suite, sai AAD và mất/đảo/trùng thông điệp.
- [ ] Kiểm thử interoperability với implementation độc lập khi giao thức cần liên thông.
- [ ] Không coi HPKE là TLS hoặc là cơ chế xác thực danh tính tự động.
- [ ] Biên dịch/chạy bằng JDK 26 trở lên mà không bật preview.

## Tài liệu tham khảo

- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180): chuẩn định nghĩa KEM, KDF, AEAD, mode, key schedule và sequence number.
- [Java SE 26 — HPKEParameterSpec API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/spec/HPKEParameterSpec.html): suite identifiers, **of**, **withInfo**, **withPsk**, **withAuthKey**, **withEncapsulation** và ví dụ sender/recipient.
- [Java SE 26 — Cipher API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html): **getInstance**, **init**, **getIV**, **updateAAD** và **doFinal**.
- [JDK 26 Release Notes — Hybrid Public Key Encryption (JDK-8325448)](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận thuật toán **Cipher** HPKE và hỗ trợ các identifier RFC 9180 trong JDK 26.
- [Java SE 26 — JCA Reference Guide: Securely Exchanging Messages with HPKE](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html): ví dụ trao đổi dữ liệu với X25519 và hướng dẫn các mode.
- [Java SE 26 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): provider SunJCE và danh sách cipher algorithm được cung cấp.
- [Java SE 26 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên chuẩn **HPKE** trong Cipher algorithms.

