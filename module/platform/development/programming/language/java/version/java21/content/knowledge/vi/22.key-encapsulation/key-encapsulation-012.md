# Kết hợp KEM với giao thức có xác thực và mã hóa đối xứng theo thiết kế đã đánh giá

Key Encapsulation Mechanism (KEM) tạo shared secret giữa bên gửi và bên nhận, nhưng KEM tự nó không xác thực danh tính người gửi. Khi kết hợp KEM với mã hóa đối xứng, ứng dụng còn phải xác định ai được phép tạo thông điệp, public key của bên nhận có đáng tin cậy hay không, dữ liệu có bị sửa đổi hoặc phát lại hay không và hai bên có đang dùng cùng một phiên bản giao thức hay không.

Một thiết kế an toàn cần kết hợp đúng các vai trò: xác thực public key và danh tính, KEM để thiết lập secret, KDF để dẫn xuất khóa theo ngữ cảnh, AEAD để bảo vệ dữ liệu, cùng cơ chế quản lý phiên và chống replay. Trong thực tế, nên ưu tiên giao thức chuẩn đã được đánh giá như TLS 1.3 hoặc HPKE với chế độ xác thực phù hợp thay vì tự ghép các primitive thành một giao thức mới.

Bài viết tập trung vào Java 21, API `javax.crypto.KEM`, chữ ký số, AEAD và cách lựa chọn giao thức. Các ví dụ minh họa nguyên tắc liên kết thông điệp; chúng không thay thế một giao thức hoàn chỉnh đã được kiểm định.

## 1. Vì sao KEM cần được kết hợp với xác thực?

KEM cho phép bên gửi sử dụng public key của bên nhận để tạo shared secret và encapsulation message. Bên nhận dùng private key tương ứng để khôi phục secret. Người quan sát mạng không thể tính secret chỉ từ public key và encapsulation message nếu thuật toán và khóa an toàn.

Tuy nhiên, public key của bên nhận thường là dữ liệu công khai. Bất kỳ ai có public key đó cũng có thể tạo encapsulation mới và mã hóa một thông điệp cho bên nhận. Vì vậy, việc bên nhận giải mã thành công không tự chứng minh ai đã gửi thông điệp.

Ví dụ, nếu ứng dụng chỉ thực hiện KEM rồi dùng AES-GCM:

1. Alice lấy public key của Bob.
2. Alice encapsulate để tạo shared secret.
3. Alice dùng secret làm khóa AES-GCM và mã hóa dữ liệu.
4. Bob decapsulate bằng private key và giải mã thành công.

Quy trình này bảo vệ bí mật và tính toàn vẹn của ciphertext đối với người không có secret. Nhưng Mallory cũng có thể lấy public key của Bob, tự encapsulate, tự tạo secret của mình và gửi một ciphertext hợp lệ cho Bob. Bob có thể decapsulate và giải mã thông điệp do Mallory tạo. AEAD xác nhận thông điệp được tạo bởi người biết khóa của phiên đó; vì bất kỳ ai có public key của Bob đều có thể tạo một phiên KEM mới, điều này không xác định danh tính người gửi.

Do đó cần phân biệt:

- **Confidentiality:** chỉ bên có khóa phù hợp mới đọc được dữ liệu.
- **Integrity:** phát hiện dữ liệu bị thay đổi.
- **Sender authentication:** xác định thông điệp được tạo bởi bên sở hữu khóa xác thực đã được tin cậy.
- **Recipient public-key authentication:** bảo đảm bên gửi đang dùng đúng public key của người nhận.
- **Replay protection:** ngăn thông điệp hợp lệ cũ bị gửi lại để kích hoạt tác dụng phụ lần nữa.

Một thiết kế chỉ có KEM và AEAD không tự cung cấp tất cả các thuộc tính này.

## 2. Vai trò của từng thành phần trong giao thức mật mã lai

Một giao thức KEM kết hợp xác thực và mã hóa đối xứng thường cần các thành phần sau:

| Thành phần | Trách nhiệm |
|---|---|
| Xác thực public key | Bảo đảm public key của bên nhận thuộc đúng danh tính hoặc dịch vụ mong muốn |
| KEM | Thiết lập shared secret mà không truyền secret trực tiếp |
| KDF | Dẫn xuất khóa theo phiên, vai trò và mục đích sử dụng |
| AEAD | Mã hóa payload và xác thực ciphertext cùng associated data |
| Chữ ký số hoặc chế độ KEM xác thực | Xác thực người gửi theo mô hình khóa đã tin cậy |
| Transcript/context binding | Liên kết thuật toán, vai trò, định danh khóa và dữ liệu phiên vào cùng một ngữ cảnh |
| Replay protection | Phát hiện thông điệp trùng lặp hoặc hết hạn |
| Key lifecycle | Quản lý tạo, phân phối, lưu trữ, rotation và thu hồi khóa |

Luồng tổng quát:

~~~text
Bên gửi                                             Bên nhận
--------                                            --------
Xác minh public key của bên nhận
       |
       v
Encapsulate bằng KEM
       |
       +---- shared secret
       |
       +---- encapsulation message -------------------->
       |                                               |
Dẫn xuất khóa bằng KDF                                |
       |                                               v
Mã hóa payload bằng AEAD                         Decapsulate
       |                                               |
Tạo chữ ký / chế độ xác thực                           +--> shared secret
       |                                               |
Gửi envelope ---------------------------------------->|
                                                       v
                                             Dẫn xuất cùng khóa
                                                       |
                                             Xác minh sender / AEAD
                                                       |
                                             Kiểm tra replay và context
                                                       |
                                                       v
                                               Chấp nhận payload
~~~

Thứ tự cụ thể phụ thuộc giao thức. Chẳng hạn, chữ ký có thể bao phủ toàn bộ envelope để người nhận xác minh trước khi xử lý payload; HPKE Auth mode tích hợp xác thực sender trong cơ chế KEM. Không tự chọn thứ tự tùy ý nếu đang triển khai một chuẩn.

## 3. Xác thực public key của bên nhận trước khi encapsulate

Bên gửi phải biết public key mà nó sử dụng thực sự thuộc về bên nhận dự kiến. Nếu kẻ tấn công thay public key của Bob bằng key của Mallory, Alice có thể encapsulate và mã hóa dữ liệu cho Mallory mà vẫn nhận được kết quả kỹ thuật thành công.

Các cách phân phối và xác thực public key thường gặp:

- **PKI và chứng thư số:** kiểm tra chuỗi chứng thư, thời hạn, mục đích sử dụng, tên dịch vụ và trạng thái thu hồi theo chính sách.
- **Key pinning:** đối chiếu public key hoặc fingerprint với giá trị đã được tin cậy qua một kênh độc lập.
- **Authenticated directory:** lấy public key từ dịch vụ danh bạ có xác thực và kiểm tra tính toàn vẹn.
- **Cấu hình tin cậy được quản lý:** dùng public key đã được triển khai qua quy trình quản trị khóa có kiểm soát.

Chỉ tải public key từ cùng một kết nối chưa được xác thực rồi dùng nó để bảo vệ dữ liệu không tạo ra xác thực. Kẻ tấn công có thể thay key trong chính kết nối đó.

Với Java, việc đọc một public key từ certificate hoặc keystore chỉ là bước nạp key. Ứng dụng vẫn cần xác minh certificate chain, hostname hoặc fingerprint theo chính sách trước khi truyền key cho `KEM.newEncapsulator(publicKey)`.

## 4. Xác thực người gửi bằng chữ ký số

Một cách kết hợp KEM với xác thực là để sender ký lên transcript của thông điệp. Bên nhận xác minh chữ ký bằng public key đã được tin cậy của sender.

Chữ ký phải ràng buộc đủ dữ liệu để ngăn việc thay đổi hoặc chuyển thông điệp sang ngữ cảnh khác. Tùy giao thức, transcript thường bao gồm:

- Protocol identifier và phiên bản.
- Thuật toán KEM, KDF và AEAD đã chọn.
- Sender key identifier và recipient key identifier.
- Encapsulation message.
- Nonce hoặc sequence number.
- Associated data và metadata quan trọng.
- Ciphertext hoặc hash được định nghĩa rõ của ciphertext.

Không ký một chuỗi ghép tùy tiện có thể gây nhập nhằng ranh giới trường. Dùng serialization có định dạng xác định, có length prefix hoặc một encoding chuẩn đã được giao thức quy định. Hai bên phải tạo cùng một transcript byte-for-byte.

Chữ ký cần được xác minh bằng public key sender lấy từ nguồn tin cậy. Một public key không rõ nguồn gốc không xác minh được danh tính, dù phép kiểm tra chữ ký trả về thành công.

### Chữ ký và AEAD có vai trò khác nhau

| Cơ chế | Xác nhận điều gì? |
|---|---|
| AEAD tag | Ciphertext và associated data khớp với khóa bí mật của phiên |
| Chữ ký số | Thông điệp đã ký được tạo bởi bên nắm private signing key tương ứng với public key đã tin cậy |
| Chứng thư số/PKI | Liên kết public key với danh tính theo chính sách tin cậy |
| KEM | Hai phía có thể thiết lập cùng shared secret theo key pair và encapsulation |

AEAD không thay chữ ký khi cần danh tính sender. Chữ ký cũng không thay AEAD: chữ ký không tự mã hóa payload và không cung cấp cùng cách xác thực dữ liệu đối xứng trong phiên.

## 5. Liên kết transcript và ngăn lỗi nhầm ngữ cảnh

Một lỗi thiết kế phổ biến là ký hoặc xác thực ciphertext nhưng bỏ sót thông tin cho biết ciphertext thuộc giao thức, người nhận hoặc phiên nào. Điều này có thể tạo cơ hội chuyển thông điệp sang một ngữ cảnh khác.

Transcript/context binding giúp mọi thành phần liên quan được liên kết:

- Protocol name và version.
- Sender/recipient role.
- Sender và recipient key identifier.
- KEM/KDF/AEAD identifiers.
- Encapsulation message.
- Session identifier hoặc sequence number.
- Nonce và associated data.
- Các tham số thương lượng ảnh hưởng tới cách giải mã.

Với AEAD, những metadata không cần mã hóa nhưng phải được bảo vệ khỏi sửa đổi có thể đặt trong associated data (AAD). Ví dụ: phiên bản envelope, key identifier, loại message hoặc tenant identifier.

Nếu dùng chữ ký số, transcript đã ký cũng phải bao phủ các trường quan trọng đó. Chỉ đưa metadata vào AAD bảo vệ nó bằng khóa AEAD của phiên; chữ ký hoặc authenticated mode mới liên kết nó với danh tính sender theo mô hình xác thực đã chọn.

Không tự thiết kế định dạng transcript nếu giao thức chuẩn đã định nghĩa key schedule và context binding.

## 6. Dùng AEAD để mã hóa dữ liệu sau khi thiết lập khóa

Sau khi KEM tạo shared secret, giao thức dùng KDF hoặc cơ chế dẫn xuất được chuẩn hóa để tạo khóa AEAD. Các thuật toán AEAD phổ biến gồm:

- AES-GCM.
- ChaCha20-Poly1305.

AEAD cung cấp đồng thời confidentiality và integrity cho payload. Nó cũng cho phép xác thực AAD mà không cần mã hóa phần metadata đó.

Khi sử dụng AES-GCM:

- Nonce phải duy nhất cho mỗi lần mã hóa với cùng một khóa.
- Không tái sử dụng nonce dưới cùng một khóa.
- Authentication tag phải được kiểm tra thành công trước khi sử dụng plaintext.
- Nếu tag không hợp lệ, coi toàn bộ thông điệp là thất bại; không sử dụng plaintext một phần.
- AAD khi giải mã phải giống chính xác AAD khi mã hóa.

Trong giao thức nhiều bản tin, không nên chỉ dùng một khóa và tự tạo nonce ngẫu nhiên mà không có phân tích xác suất va chạm. Hãy theo nonce strategy và key schedule của chuẩn đang dùng, bao gồm sequence number và giới hạn số lần sử dụng khóa.

## 7. HPKE: chuẩn kết hợp KEM, KDF và AEAD

HPKE (Hybrid Public Key Encryption, RFC 9180) định nghĩa một cấu trúc chuẩn kết hợp KEM, KDF và AEAD. HPKE giúp tránh việc mỗi ứng dụng tự phát minh cách kết hợp các primitive.

HPKE định nghĩa bốn mode:

| Mode | Thành phần | Mô hình xác thực |
|---|---|---|
| Base | KEM + KDF + AEAD | Không xác thực danh tính sender |
| PSK | Base + pre-shared key | Xác thực dựa trên việc biết PSK; không phân biệt sender nếu PSK dùng chung |
| Auth | KEM với static key của sender + KDF + AEAD | Xác thực sender với điều kiện recipient đã tin cậy public key sender |
| AuthPSK | Auth + pre-shared key | Kết hợp xác thực bằng sender key và PSK |

### Chọn mode phù hợp

- Dùng **Base** khi chỉ cần mã hóa tới public key của recipient và không cần xác thực sender ở lớp HPKE.
- Dùng **PSK** khi hai phía đã có một secret chia sẻ an toàn và cần kết hợp nó vào thiết lập khóa.
- Dùng **Auth** khi recipient cần xác thực sender thông qua public key sender đã biết.
- Dùng **AuthPSK** khi thiết kế cần cả sender key authentication và PSK.

Trong Auth mode, sender dùng static private key của mình cùng public key recipient để tạo encapsulation. Recipient cần public key sender đáng tin cậy để decapsulate theo cùng chế độ. Điều này xác thực sender với recipient; nó không tự động chứng minh cho sender rằng recipient là đúng danh tính. Sender vẫn cần xác minh public key recipient trước khi dùng.

PSK mode chỉ chứng minh bên tham gia biết PSK. Nếu cùng một PSK được chia sẻ cho nhiều client, việc xác thực bằng PSK không cho biết client cụ thể nào đã tạo thông điệp.

### HPKE không giải quyết mọi chính sách ứng dụng

HPKE cung cấp cơ chế mã hóa và xác thực theo mode đã chọn, nhưng ứng dụng vẫn phải quản lý:

- Phân phối và xác minh public key.
- Danh tính và quyền truy cập của sender.
- Key identifier, rotation và thu hồi.
- Replay protection, sequence number hoặc message expiry.
- Cách xử lý lỗi, retry và tác dụng phụ nghiệp vụ.
- Serialization và framing của thông điệp trong giao thức ứng dụng.

HPKE không phải một giao thức đăng nhập, không thay thế PKI và không tự cung cấp chính sách chống replay cho mọi ứng dụng.

## 8. TLS 1.3 cho kết nối client-server có xác thực

Nếu mục tiêu là bảo vệ một kết nối mạng tương tác giữa client và server, TLS 1.3 thường là lựa chọn phù hợp hơn tự ghép KEM, chữ ký và AEAD.

TLS 1.3 cung cấp handshake để thương lượng key material và bảo vệ record bằng AEAD; khi dùng certificate-based authentication, handshake xác thực server bằng certificate và chữ ký. Nếu cần xác thực client, có thể cấu hình mutual TLS (mTLS) với client certificate. TLS 1.3 cũng có các chế độ dựa trên PSK theo RFC 8446.

Java 21 hỗ trợ TLS thông qua JSSE, `SSLContext`, `SSLSocket` và `SSLEngine`. Ví dụ khởi tạo client context:

```java
import javax.net.ssl.SSLContext;

SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, null);
```

Trong ứng dụng thực tế, `keyManagers` và `trustManagers` cần được cấu hình từ key material và trust anchors đã được quản lý. Không dùng trust manager chấp nhận mọi certificate trong production.

TLS 1.3 trong JSSE quản lý handshake, xác thực và mã hóa record. Nó không yêu cầu ứng dụng tự gọi `javax.crypto.KEM` để tạo khóa phiên. Key exchange cốt lõi của TLS 1.3 theo RFC 8446 sử dụng (EC)DHE hoặc PSK modes; không nên nhầm API KEM của Java 21 với việc TLS 1.3 mặc định đã sử dụng KEM. Hỗ trợ thuật toán mở rộng hoặc hybrid key exchange phụ thuộc phiên bản giao thức, provider và cấu hình triển khai.

Dùng TLS 1.3 khi cần bảo vệ luồng kết nối client-server. Dùng HPKE khi cần mã hóa thông điệp tới public key của recipient mà không nhất thiết phải duy trì kết nối tương tác.

## 9. Ví dụ Java 21: ràng buộc chữ ký sender với envelope KEM + AES-GCM

Ví dụ sau minh họa nguyên tắc liên kết chữ ký với một envelope đã mã hóa. Bên gửi:

1. Dùng public key recipient đã được xác thực để encapsulate bằng DHKEM.
2. Dùng khóa AES sinh ra để mã hóa payload bằng AES-GCM.
3. Tạo transcript xác định từ protocol version, key identifiers, KEM message, nonce và ciphertext.
4. Ký transcript bằng Ed25519.

Bên nhận:

1. Kiểm tra sender key identifier và recipient key identifier.
2. Xác minh chữ ký bằng public signing key sender đã được tin cậy.
3. Decapsulate bằng private key recipient.
4. Xác thực AAD và giải mã AES-GCM.

Đoạn mã là ví dụ học tập về binding giữa các primitive, không phải định dạng giao thức được chuẩn hóa. Ứng dụng production nên dùng HPKE Auth hoặc giao thức đã được đánh giá thay vì triển khai envelope riêng.

```java
import javax.crypto.Cipher;
import javax.crypto.KEM;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Objects;

record Envelope(
        String senderKeyId,
        String recipientKeyId,
        byte[] encapsulation,
        byte[] nonce,
        byte[] ciphertext,
        byte[] signature
) {
    Envelope {
        Objects.requireNonNull(senderKeyId);
        Objects.requireNonNull(recipientKeyId);
        encapsulation = encapsulation.clone();
        nonce = nonce.clone();
        ciphertext = ciphertext.clone();
        signature = signature.clone();
    }

    @Override
    public byte[] encapsulation() {
        return encapsulation.clone();
    }

    @Override
    public byte[] nonce() {
        return nonce.clone();
    }

    @Override
    public byte[] ciphertext() {
        return ciphertext.clone();
    }

    @Override
    public byte[] signature() {
        return signature.clone();
    }
}

public class AuthenticatedKemEnvelope {
    private static final String PROTOCOL = "example-envelope-v1";
    private static final String KEM_ALGORITHM = "DHKEM";
    private static final String AEAD_ALGORITHM = "AES-128-GCM";
    private static final String SIGNATURE_ALGORITHM = "Ed25519";

    static Envelope seal(
            PublicKey trustedRecipientKemPublicKey,
            String recipientKeyId,
            PrivateKey senderSigningPrivateKey,
            String senderKeyId,
            byte[] plaintext
    ) throws Exception {
        KEM kem = KEM.getInstance(KEM_ALGORITHM);

        KEM.Encapsulated result = kem
                .newEncapsulator(trustedRecipientKemPublicKey)
                .encapsulate(0, 16, "AES");

        SecretKey aeadKey = result.key();
        byte[] encapsulation = result.encapsulation();

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] header = encodeHeader(
                senderKeyId,
                recipientKeyId,
                encapsulation
        );

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                aeadKey,
                new GCMParameterSpec(128, nonce)
        );
        cipher.updateAAD(header);
        byte[] ciphertext = cipher.doFinal(plaintext);

        byte[] signedData = encodeSignedData(header, nonce, ciphertext);

        Signature signer = Signature.getInstance(SIGNATURE_ALGORITHM);
        signer.initSign(senderSigningPrivateKey);
        signer.update(signedData);
        byte[] signature = signer.sign();

        return new Envelope(
                senderKeyId,
                recipientKeyId,
                encapsulation,
                nonce,
                ciphertext,
                signature
        );
    }

    static byte[] open(
            Envelope envelope,
            String expectedSenderKeyId,
            String expectedRecipientKeyId,
            PublicKey trustedSenderSigningPublicKey,
            PrivateKey recipientKemPrivateKey
    ) throws Exception {
        if (!expectedSenderKeyId.equals(envelope.senderKeyId())
                || !expectedRecipientKeyId.equals(envelope.recipientKeyId())) {
            throw new SecurityException("Unexpected key identity");
        }

        byte[] header = encodeHeader(
                envelope.senderKeyId(),
                envelope.recipientKeyId(),
                envelope.encapsulation()
        );

        byte[] signedData = encodeSignedData(
                header,
                envelope.nonce(),
                envelope.ciphertext()
        );

        Signature verifier = Signature.getInstance(SIGNATURE_ALGORITHM);
        verifier.initVerify(trustedSenderSigningPublicKey);
        verifier.update(signedData);

        if (!verifier.verify(envelope.signature())) {
            throw new SecurityException("Invalid sender signature");
        }

        SecretKey aeadKey = KEM.getInstance(KEM_ALGORITHM)
                .newDecapsulator(recipientKemPrivateKey)
                .decapsulate(envelope.encapsulation(), 0, 16, "AES");

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                aeadKey,
                new GCMParameterSpec(128, envelope.nonce())
        );
        cipher.updateAAD(header);

        // doFinal chỉ trả plaintext khi AEAD authentication thành công.
        return cipher.doFinal(envelope.ciphertext());
    }

    private static byte[] encodeHeader(
            String senderKeyId,
            String recipientKeyId,
            byte[] encapsulation
    ) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            writeField(out, PROTOCOL.getBytes(StandardCharsets.UTF_8));
            writeField(out, KEM_ALGORITHM.getBytes(StandardCharsets.UTF_8));
            writeField(out, AEAD_ALGORITHM.getBytes(StandardCharsets.UTF_8));
            writeField(out, SIGNATURE_ALGORITHM.getBytes(StandardCharsets.UTF_8));
            writeField(out, senderKeyId.getBytes(StandardCharsets.UTF_8));
            writeField(out, recipientKeyId.getBytes(StandardCharsets.UTF_8));
            writeField(out, encapsulation);
        }

        return bytes.toByteArray();
    }

    private static byte[] encodeSignedData(
            byte[] header,
            byte[] nonce,
            byte[] ciphertext
    ) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            writeField(out, header);
            writeField(out, nonce);
            writeField(out, ciphertext);
        }

        return bytes.toByteArray();
    }

    private static void writeField(
            DataOutputStream out,
            byte[] value
    ) throws Exception {
        out.writeInt(value.length);
        out.write(value);
    }
}
```

Điều kiện tin cậy quan trọng của ví dụ:

- `trustedRecipientKemPublicKey` phải được xác minh trước khi sender gọi `seal`.
- `trustedSenderSigningPublicKey` phải được liên kết với sender identity qua PKI, pinning hoặc trust store đã quản lý.
- Key identifier phải được tra cứu và kiểm tra theo chính sách, không chỉ so sánh một chuỗi do message tự khai báo.
- Sender signature bao phủ header, encapsulation, nonce và ciphertext; AAD của AES-GCM là header tương tự.
- Nếu tag GCM không hợp lệ, `doFinal` ném lỗi xác thực và plaintext không được chấp nhận.

Ví dụ chưa triển khai replay cache, message expiry, key rotation, mutual authentication, canonical wire framing hoàn chỉnh hoặc key confirmation cho sender. Các phần đó phải được định nghĩa bởi giao thức. Không dùng đoạn mã này như giao thức production chỉ vì các primitive riêng lẻ là API chuẩn.

## 10. Key confirmation và xác thực hai chiều

Sender có thể tạo ciphertext hợp lệ bằng shared secret mà nó tự tạo với public key recipient. Nhưng sender không thể chỉ từ việc tạo ciphertext biết chắc recipient đã decapsulate thành công hoặc đang giữ đúng private key.

Nếu ứng dụng cần sender biết recipient đã nhận và khôi phục cùng key, cần một bước **key confirmation**. Ví dụ, recipient gửi một phản hồi được xác thực bằng khóa phiên hoặc một khóa dẫn xuất riêng theo chiều recipient-to-sender. Phản hồi phải gắn với session identifier và transcript để không thể chuyển từ phiên khác.

Nếu cần xác thực hai chiều, cần xác minh cả hai danh tính theo giao thức. Chữ ký sender chỉ xác thực sender với recipient; nó không xác thực recipient với sender. Có thể dùng mutual TLS, một giao thức trao đổi khóa có xác thực hai chiều hoặc một thiết kế HPKE kết hợp cơ chế phản hồi được xác thực phù hợp.

Không tự dùng cùng một khóa AEAD cho hai chiều nếu giao thức yêu cầu tách khóa. KDF/key schedule cần dẫn xuất khóa riêng cho từng hướng và từng mục đích.

## 11. Replay protection và quản lý trạng thái phiên

Chữ ký hợp lệ và AEAD tag hợp lệ không có nghĩa thông điệp chưa từng được xử lý. Kẻ tấn công có thể ghi lại một envelope hợp lệ rồi gửi lại. Nếu thông điệp kích hoạt thanh toán, thay đổi trạng thái hoặc thực hiện lệnh, replay có thể gây tác dụng phụ lặp.

Giao thức ứng dụng nên dùng một hoặc nhiều cơ chế:

- Session ID hoặc challenge gắn với phiên.
- Sequence number đơn điệu theo phiên.
- Message ID duy nhất và kho lưu dấu message đã xử lý.
- Timestamp/expiry với đồng hồ và chính sách sai lệch được xác định.
- Idempotency key cho thao tác có tác dụng phụ.

Thông tin chống replay cần được liên kết mật mã vào transcript, chữ ký hoặc AAD. Chỉ đặt sequence number trong metadata không được xác thực sẽ cho phép kẻ tấn công thay đổi nó.

KEM không tự chống replay. HPKE cũng không thay thế chính sách replay của ứng dụng; HPKE context quản lý việc mã hóa theo sequence trong context, nhưng ứng dụng vẫn phải quyết định cách xử lý message trùng, context mới và tác dụng phụ nghiệp vụ.

## 12. Lựa chọn giữa HPKE và TLS 1.3

Hai công nghệ phục vụ các mô hình giao tiếp khác nhau:

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Bảo vệ kết nối client-server hai chiều | TLS 1.3 |
| Xác thực server bằng certificate | TLS 1.3 với trust validation đúng |
| Xác thực cả client và server | TLS 1.3 mutual authentication (mTLS) |
| Mã hóa một thông điệp tới public key recipient | HPKE |
| Mã hóa thông điệp và xác thực sender bằng static sender key | HPKE Auth mode |
| Xác thực dựa trên secret đã chia sẻ | HPKE PSK/AuthPSK theo mô hình phù hợp |
| Tự xây dựng KEM + signature + AEAD envelope | Chỉ khi có thiết kế giao thức được đánh giá và kiểm thử chuyên môn |

TLS 1.3 thường là lựa chọn cho kết nối liên tục, quản lý handshake, xác thực certificate và bảo vệ nhiều record. HPKE phù hợp cho mã hóa message tới recipient mà không cần một kết nối TLS đang mở, chẳng hạn dữ liệu lưu trữ hoặc message gửi qua hệ thống trung gian.

Java 21 cung cấp JSSE cho TLS và `javax.crypto.KEM` cho primitive KEM. Việc có KEM API không có nghĩa Java 21 có sẵn API HPKE hoàn chỉnh. Nếu cần HPKE, chọn thư viện triển khai RFC 9180 được duy trì và đánh giá; kiểm tra hỗ trợ mode, KEM, KDF, AEAD và encoding của thư viện.

## 13. Quản lý key lifecycle và rotation

Xác thực chỉ có ý nghĩa nếu key lifecycle được quản lý đúng:

- Tạo key bằng thuật toán và tham số được chấp thuận.
- Bảo vệ private key bằng keystore, HSM hoặc dịch vụ quản lý khóa phù hợp.
- Phân phối public key qua nguồn có xác thực.
- Gắn key identifier và thời hạn sử dụng.
- Hỗ trợ rotation mà không nhầm key mới với key cũ.
- Thu hồi key khi nghi ngờ lộ lọt.
- Giới hạn thời gian và số lượng phiên dùng một key theo chính sách thuật toán.
- Không ghi private key, shared secret hoặc khóa AEAD vào log.

Trong giai đoạn rotation, bên nhận có thể cần nhận diện nhiều key ID trong một khoảng chuyển tiếp. Mỗi message phải chỉ rõ recipient key ID đã được xác thực và server chỉ tra cứu trong tập key còn hiệu lực. Không chấp nhận một key ID tùy ý do sender cung cấp nếu nó không nằm trong chính sách tin cậy.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ KEM tự xác thực sender | Bất kỳ ai có recipient public key đều có thể tạo encapsulation | Dùng HPKE Auth, chữ ký hoặc giao thức xác thực phù hợp |
| Nghĩ AEAD tag chứng minh danh tính sender | Tag chỉ chứng minh biết khóa phiên | Liên kết sender identity bằng chữ ký hoặc authenticated mode |
| Dùng public key tải từ nguồn chưa xác thực | Có thể mã hóa cho key của attacker | Xác minh certificate, pinning hoặc authenticated directory |
| Chỉ ký ciphertext, bỏ metadata quan trọng | Có thể nhầm protocol, key ID hoặc phiên | Ký transcript có cấu trúc và ràng buộc context |
| Ghép byte bằng nối chuỗi không phân định | Có thể tạo transcript nhập nhằng | Dùng serialization xác định với length prefix hoặc chuẩn encoding |
| Dùng một khóa cho mọi hướng và mục đích | Tăng nguy cơ key/nonce misuse | Dùng KDF/key schedule để tách khóa |
| Cho rằng chữ ký ngăn replay | Một message đã ký vẫn có thể bị gửi lại | Dùng sequence number, message ID, expiry và replay store |
| Tự ghép KEM, KDF và AEAD thành giao thức mới | Dễ bỏ sót xác thực, context, key confirmation và replay | Ưu tiên TLS/HPKE hoặc thiết kế được đánh giá |
| Cho rằng Java 21 KEM API đồng nghĩa có HPKE API | Dùng nhầm primitive với giao thức hoàn chỉnh | Dùng thư viện HPKE phù hợp hoặc JSSE TLS |

## 15. Checklist trước khi đưa vào production

Trước khi triển khai giao thức KEM kết hợp xác thực và mã hóa đối xứng, hãy xác nhận:

1. Mục tiêu là bảo vệ kết nối hay mã hóa message; đã chọn TLS 1.3 hoặc HPKE nếu phù hợp chưa?
2. Public key recipient được xác minh bằng PKI, pinning hoặc nguồn tin cậy nào?
3. Sender authentication dựa trên chữ ký, HPKE Auth hay PSK?
4. Public key sender được liên kết với danh tính và quyền truy cập ra sao?
5. KEM, KDF, AEAD và parameter set có được thống nhất và hỗ trợ bởi provider/thư viện không?
6. Transcript có ràng buộc protocol version, role, key ID, encapsulation và thuật toán không?
7. Nonce và sequence number có được quản lý theo đúng hợp đồng AEAD không?
8. Có replay protection và idempotency cho message có tác dụng phụ không?
9. Có key confirmation hoặc mutual authentication nếu nghiệp vụ yêu cầu không?
10. Có key rotation, revocation, logging an toàn và xử lý lỗi thống nhất không?
11. Đã kiểm thử message bị sửa, sai chữ ký, sai key ID, replay, sai nonce, sai tag và downgrade thuật toán chưa?
12. Thiết kế đã được review bởi người có chuyên môn mật mã trước khi dùng để bảo vệ dữ liệu production chưa?

## Kết luận

KEM thiết lập shared secret nhưng không tự xác thực sender. Để bảo vệ một giao thức hoàn chỉnh, cần xác thực public key recipient, xác thực sender bằng chữ ký hoặc mode phù hợp, dẫn xuất khóa theo context bằng KDF, dùng AEAD để mã hóa và xác thực payload, đồng thời quản lý replay và key lifecycle.

Với Java 21, `javax.crypto.KEM` cung cấp primitive KEM và JSSE cung cấp TLS. HPKE là chuẩn kết hợp KEM, KDF và AEAD với các mode xác thực được định nghĩa rõ. Ưu tiên giao thức đã được chuẩn hóa và triển khai được đánh giá; chỉ xây envelope riêng khi có thiết kế, serialization, kiểm thử và review mật mã đầy đủ.

## Tài liệu tham khảo

- [Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 21 API — Signature](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Signature.html)
- [Java SE 21 API — Cipher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [Java SE 21 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180)
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [NIST SP 800-56C Rev. 2 — Key-Derivation Methods](https://csrc.nist.gov/pubs/sp/800/56/c/r2/final)
