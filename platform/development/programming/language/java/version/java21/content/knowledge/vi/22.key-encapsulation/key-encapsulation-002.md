# Phân biệt KEM, key agreement và mã hóa dữ liệu ứng dụng

KEM (Key Encapsulation Mechanism), key agreement và mã hóa dữ liệu ứng dụng là ba khái niệm liên quan nhưng giải quyết các phần việc khác nhau trong một hệ thống mật mã. KEM và key agreement dùng mật mã khóa công khai để hai bên thiết lập cùng một bí mật đối xứng. Mã hóa dữ liệu ứng dụng dùng khóa đối xứng đó, thường qua AEAD, để bảo vệ nội dung thực tế.

Trong Java 21, JCA cung cấp `javax.crypto.KEM` (được chuẩn hóa qua JEP 452) bên cạnh `javax.crypto.KeyAgreement` và `javax.crypto.Cipher`. `KEM` tạo ra shared secret cùng một encapsulation message; `KeyAgreement` tính shared secret từ khóa riêng của mỗi bên và khóa công khai của bên kia; `Cipher` thực hiện mã hóa/giải mã dữ liệu. Không nên nhầm encapsulation message với ciphertext của dữ liệu ứng dụng.

## 1. Ba lớp công việc khác nhau

| Khái niệm | Mục tiêu | Đầu vào chính | Kết quả chính |
| --- | --- | --- | --- |
| KEM | Thiết lập bí mật đối xứng cho bên nhận thông qua public key của bên đó. | Public key của bên nhận; private key tương ứng ở bên giải đóng gói. | Shared secret và encapsulation message. |
| Key agreement | Hai hoặc nhiều bên cùng tính một shared secret từ key material của các bên. | Private key của mỗi bên và public key nhận từ bên kia. | Cùng một shared secret ở mỗi bên. |
| Mã hóa dữ liệu ứng dụng | Bảo vệ nội dung thực tế, bao gồm tính bí mật và tính toàn vẹn. | Khóa đối xứng, nonce, plaintext và tùy chọn additional authenticated data. | Ciphertext có authentication tag đối với AEAD. |

KEM và key agreement không tự động mã hóa một file, JSON hay HTTP body. Chúng thiết lập bí mật để giao thức tiếp theo dẫn xuất khóa và dùng thuật toán đối xứng. Ngược lại, AEAD không tự xác thực danh tính người gửi nếu giao thức không có cơ chế xác thực khóa hoặc danh tính.

## 2. KEM hoạt động như thế nào?

KEM có hai vai trò:

- **Bên nhận (recipient):** tạo key pair gồm public key và private key. Public key được phân phối cho bên gửi qua một kênh có thể xác thực; private key được giữ bí mật.
- **Bên gửi (sender):** dùng public key của recipient để encapsulate, tạo một shared secret và một encapsulation message có thể gửi cho recipient.

Recipient dùng private key cùng encapsulation message để decapsulate và thu được cùng shared secret. Private key không cần truyền qua mạng.

```text
Recipient                                      Sender
---------                                      ------
GenerateKeyPair() -> (pkR, skR)
                 -- pkR --------------------->
                                               Encapsulate(pkR)
                                               -> (enc, sharedSecretS)
                 <-- enc ---------------------
Decapsulate(skR, enc)
-> sharedSecretR

sharedSecretR == sharedSecretS
```

`enc` là encapsulation message. Nó không phải ciphertext của dữ liệu nghiệp vụ. KEM tạo ra shared secret và encapsulation có kích thước được quy định bởi thuật toán KEM; kích thước đó không phụ thuộc ứng dụng cần mã hóa một byte hay một file lớn.

### Trình tự thao tác

1. Recipient sinh key pair và công bố public key.
2. Sender xác minh public key thuộc đúng recipient, sau đó chạy `Encapsulate(publicKey)`.
3. Sender nhận `sharedSecret` và `encapsulation`, rồi gửi `encapsulation` cùng thông tin giao thức cần thiết cho recipient.
4. Sender và recipient dùng một KDF theo giao thức để dẫn xuất khóa đối xứng và các giá trị cần thiết.
5. Sender dùng AEAD để mã hóa dữ liệu; recipient dùng khóa dẫn xuất và thông tin nonce/AAD tương ứng để giải mã.

Trong một DH-based KEM như `DHKEM`, thao tác encapsulation có thể dùng một khóa ephemeral do sender tạo ra và phép tính Diffie-Hellman với public key của recipient. KEM đóng gói các bước đó thành giao diện `encapsulate`/`decapsulate`.

## 3. Key agreement hoạt động như thế nào?

Trong key agreement, mỗi bên có key pair của mình. Các bên trao đổi public key, rồi mỗi bên kết hợp private key của mình với public key của bên kia để tính cùng một shared secret.

Ví dụ khái niệm với Diffie-Hellman:

```text
Alice                                          Bob
-----                                          ---
GenerateKeyPair() -> (pkA, skA)  GenerateKeyPair() -> (pkB, skB)
          -- pkA --------------------->
          <--------------------- pkB --

Agree(skA, pkB) -> sharedSecretA
                              Agree(skB, pkA) -> sharedSecretB

sharedSecretA == sharedSecretB
```

Trong Java, `KeyAgreement` cung cấp quy trình này qua `init()`, `doPhase()` và `generateSecret()`. Ví dụ với X25519:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public class X25519AgreementExample {
    public static void main(String[] args) throws GeneralSecurityException {
        KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");

        // Mỗi bên tạo key pair của mình.
        KeyPair aliceKeys = keyPairGenerator.generateKeyPair();
        KeyPair bobKeys = keyPairGenerator.generateKeyPair();

        // Trong ứng dụng thực tế, hai public key được trao đổi qua giao thức.
        KeyAgreement aliceAgreement = KeyAgreement.getInstance("X25519");
        aliceAgreement.init(aliceKeys.getPrivate());
        aliceAgreement.doPhase(bobKeys.getPublic(), true);
        byte[] aliceSecret = aliceAgreement.generateSecret();

        KeyAgreement bobAgreement = KeyAgreement.getInstance("X25519");
        bobAgreement.init(bobKeys.getPrivate());
        bobAgreement.doPhase(aliceKeys.getPublic(), true);
        byte[] bobSecret = bobAgreement.generateSecret();

        System.out.println(Arrays.equals(aliceSecret, bobSecret)); // true
    }
}
```

Ví dụ tạo cả hai bên trong cùng một JVM để minh họa phép tính. Trong hệ thống thực, mỗi bên chỉ có private key của mình và nhận public key của peer qua giao thức. Không gửi private key hoặc shared secret qua mạng.

Key agreement không tự xác thực public key vừa nhận. Nếu public key không được ràng buộc với danh tính peer bằng chứng chỉ, chữ ký số hoặc cơ chế xác thực khác, kẻ trung gian có thể thay public key và thiết lập hai shared secret riêng với hai bên.

## 4. So sánh KEM và key agreement

| Tiêu chí | KEM | Key agreement |
| --- | --- | --- |
| Cách bắt đầu | Sender cần public key của recipient. | Các bên trao đổi public key của nhau. |
| Bên tạo secret | Sender tạo secret trong lúc encapsulate; recipient khôi phục bằng decapsulate. | Mỗi bên tự tính secret từ private key của mình và public key peer. |
| Dữ liệu truyền | Encapsulation message do sender gửi cho recipient. | Public key hoặc key share của các bên. |
| Hướng sử dụng phổ biến | Mô hình gửi dữ liệu đến một public key của recipient. | Thiết lập secret chung giữa các bên tham gia trao đổi. |
| Ví dụ thuật toán/API | DHKEM trong Java 21; ML-KEM trên nền tảng/provider có hỗ trợ; Java API `KEM`. | DH, ECDH, X25519; Java API `KeyAgreement`. |
| Kết quả | Shared secret và encapsulation. | Shared secret được tính ở mỗi bên. |

KEM không nhất thiết là một họ toán học hoàn toàn tách biệt với key agreement. `DHKEM` được xây dựng trên Diffie-Hellman nhưng cung cấp giao diện KEM. Vì vậy, cần phân biệt **mô hình giao thức/API** với **phép toán nền tảng**.

## 5. KEM API trong Java 21

Java 21 bổ sung `javax.crypto.KEM` qua [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452). Các thành phần quan trọng:

- `KEM.getInstance(algorithm)`: lấy implementation từ các security provider đã đăng ký.
- `newEncapsulator(publicKey)`: tạo đối tượng dùng ở phía sender.
- `Encapsulator.encapsulate()`: tạo kết quả gồm shared secret và encapsulation message.
- `newDecapsulator(privateKey)`: tạo đối tượng dùng ở phía recipient.
- `Decapsulator.decapsulate(encapsulation)`: khôi phục shared secret từ encapsulation message.
- `KEM.Encapsulated.key()`: lấy shared secret dưới dạng `SecretKey`.
- `KEM.Encapsulated.encapsulation()`: lấy byte array cần chuyển đến recipient.

Ví dụ dưới đây minh họa một lượt KEM với `DHKEM` và khóa X25519. Trong ví dụ, recipient tạo key pair; sender dùng public key để encapsulate; recipient dùng private key để decapsulate:

```java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemRoundTripExample {
    public static void main(String[] args) throws GeneralSecurityException {
        // Recipient tạo key pair và giữ private key.
        KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = keyPairGenerator.generateKeyPair();

        // Sender dùng public key đã nhận và xác minh của recipient.
        KEM kemForSender = KEM.getInstance("DHKEM");
        KEM.Encapsulator encapsulator = kemForSender.newEncapsulator(recipientKeys.getPublic());
        KEM.Encapsulated encapsulated = encapsulator.encapsulate();

        SecretKey senderSecret = encapsulated.key();
        byte[] encapsulationMessage = encapsulated.encapsulation();

        // Recipient nhận encapsulationMessage rồi dùng private key để decapsulate.
        KEM kemForRecipient = KEM.getInstance("DHKEM");
        KEM.Decapsulator decapsulator = kemForRecipient.newDecapsulator(recipientKeys.getPrivate());
        SecretKey recipientSecret = decapsulator.decapsulate(encapsulationMessage);

        System.out.println(Arrays.equals(
                senderSecret.getEncoded(),
                recipientSecret.getEncoded()
        )); // true
    }
}
```

Đây là ví dụ round-trip trong một tiến trình; ở ứng dụng thực, `encapsulationMessage` được serialize và truyền qua giao thức. Không serialize `senderSecret`, `recipientSecret` hoặc private key để gửi đi. Việc so sánh `getEncoded()` chỉ phục vụ minh họa rằng hai phía có cùng secret; không ghi secret ra log hoặc console.

### Thuật toán và provider trong Java 21

Java SE 21 định nghĩa tên KEM chuẩn `DHKEM`. JDK 21 đi kèm implementation `DHKEM` trong SunJCE; tài liệu provider nêu các loại khóa được hỗ trợ gồm EC trên `secp256r1`, `secp384r1`, `secp521r1` và XDH trên Curve25519/Curve448.

`KEM.getInstance("DHKEM")` có thể ném `NoSuchAlgorithmException` nếu không có provider hỗ trợ thuật toán. Khả năng hỗ trợ còn phụ thuộc provider, loại khóa và tham số. Ứng dụng thông thường nên để JCA chọn provider bằng `getInstance()` thay vì cố định tên provider, trừ khi có yêu cầu triển khai hoặc chứng nhận cụ thể.

Danh sách tên KEM chuẩn của Java SE 21 có `DHKEM`. Không nên giả định `ML-KEM` là thuật toán có sẵn trong mọi JDK 21; một provider bên ngoài có thể bổ sung dịch vụ riêng, nhưng đó không phải bảo đảm của Java SE 21. Khi cần thuật toán hậu lượng tử, phải xác minh rõ phiên bản JDK, provider, thuật toán, định dạng khóa và khả năng tương thích giữa hai đầu.

## 6. `KeyAgreement` API trong Java 21

`javax.crypto.KeyAgreement` cung cấp API key agreement. Quy trình thường gồm:

1. Lấy implementation bằng `KeyAgreement.getInstance("X25519")`, `getInstance("ECDH")` hoặc thuật toán phù hợp.
2. Gọi `init(privateKey)` bằng private key của bên hiện tại.
3. Gọi `doPhase(peerPublicKey, true)` với public key của peer trong trao đổi hai bên.
4. Gọi `generateSecret()` để lấy shared secret.

Các tên thuật toán chuẩn được liệt kê trong Java SE 21 gồm `DiffieHellman`, `ECDH`, `XDH`, `X25519` và `X448` (tùy implementation/provider hỗ trợ). Tài liệu API yêu cầu mọi Java SE implementation hỗ trợ `DiffieHellman`; các thuật toán khác cần kiểm tra provider của runtime đang triển khai.

Kết quả từ `generateSecret()` là material bí mật để đưa vào bước dẫn xuất khóa. Không nên dùng raw shared secret trực tiếp cho nhiều mục đích khác nhau. Hãy dùng KDF có thiết kế và context rõ ràng để tạo khóa riêng cho encryption, authentication hoặc các mục đích khác.

## 7. Vì sao vẫn cần mã hóa dữ liệu ứng dụng?

KEM hoặc key agreement chỉ tạo shared secret. Dữ liệu ứng dụng phải được mã hóa bằng một thuật toán đối xứng. Mô hình phổ biến là:

```text
KEM hoặc KeyAgreement
          |
          v
     Shared secret
          |
          v
       KDF/HKDF
          |
          v
   Khóa đối xứng theo mục đích
          |
          v
       AEAD Cipher
          |
          v
 Ciphertext + authentication tag
```

AEAD (Authenticated Encryption with Associated Data) vừa bảo vệ tính bí mật vừa kiểm tra tính toàn vẹn của ciphertext và AAD. Các lựa chọn phổ biến trong Java gồm `AES/GCM/NoPadding` và `ChaCha20-Poly1305`, tùy yêu cầu và provider.

Ví dụ minh họa cách dùng AES-GCM sau khi ứng dụng đã có `SecretKey aeadKey` được dẫn xuất đúng cách từ shared secret:

```java
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

static byte[] encrypt(
        SecretKey aeadKey,
        byte[] plaintext,
        byte[] associatedData,
        byte[] nonce
) throws Exception {
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    GCMParameterSpec parameters = new GCMParameterSpec(128, nonce);
    cipher.init(Cipher.ENCRYPT_MODE, aeadKey, parameters);
    cipher.updateAAD(associatedData);
    return cipher.doFinal(plaintext);
}

static byte[] decrypt(
        SecretKey aeadKey,
        byte[] ciphertext,
        byte[] associatedData,
        byte[] nonce
) throws Exception {
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    GCMParameterSpec parameters = new GCMParameterSpec(128, nonce);
    cipher.init(Cipher.DECRYPT_MODE, aeadKey, parameters);
    cipher.updateAAD(associatedData);
    return cipher.doFinal(ciphertext);
}

static byte[] newGcmNonce(SecureRandom random) {
    byte[] nonce = new byte[12];
    random.nextBytes(nonce);
    return nonce;
}
```

Đây là phần mã hóa dữ liệu sau khi đã có khóa AES phù hợp; nó không thay thế KEM hoặc KDF. Khi giải mã, hai bên phải dùng đúng khóa, nonce và AAD. Nếu tag xác thực không hợp lệ, thao tác giải mã phải thất bại; không xử lý plaintext chưa được xác thực.

Các nguyên tắc quan trọng với AEAD:

- Không bao giờ tái sử dụng nonce với cùng một khóa AES-GCM.
- Gửi nonce cùng ciphertext; nonce thường không cần bí mật nhưng phải được quản lý đúng.
- Nếu một khóa dùng cho nhiều bản tin, giao thức phải quy định cách cấp nonce không trùng; nonce ngẫu nhiên 96-bit cần giới hạn số bản tin và đánh giá xác suất va chạm.
- Dùng AAD để ràng buộc metadata cần xác thực nhưng không cần mã hóa, chẳng hạn phiên bản giao thức, loại bản ghi hoặc định danh người nhận.
- Xác thực thành công trước khi sử dụng plaintext.
- Giới hạn số lượng và kích thước bản tin theo khuyến nghị của thuật toán AEAD.

## 8. KDF và HPKE: cách ghép các thành phần thành giao thức

KDF (Key Derivation Function) chuyển shared secret thành một hoặc nhiều khóa có mục đích cụ thể. HKDF được mô tả trong RFC 5869 và thường dùng HMAC làm nền tảng. KDF còn giúp tách miền (domain separation), ràng buộc khóa với thuật toán, phiên giao thức và thông tin ngữ cảnh. Java SE 21 có `KEM` API nhưng chưa có một `javax.crypto.KDF` engine chuẩn tương đương; nếu cần HKDF, hãy dùng thư viện/provider đã được kiểm tra hoặc một implementation giao thức hoàn chỉnh.

Không nên tự ghép `KEM`, một hàm hash và `Cipher` theo một công thức tùy ý. Cần dùng một giao thức đã được phân tích, quy định chính xác cách tạo khóa, nonce, AAD, định dạng bản tin, xử lý lỗi và xác thực.

HPKE (Hybrid Public Key Encryption) trong [RFC 9180](https://www.rfc-editor.org/rfc/rfc9180.html) là ví dụ chuẩn về cách kết hợp ba thành phần:

1. **KEM:** tạo shared secret và encapsulation.
2. **KDF:** dẫn xuất key schedule và các giá trị cần thiết cho phiên mã hóa.
3. **AEAD:** mã hóa/giải mã nội dung và xác thực AAD.

HPKE định nghĩa các mode `base`, `psk`, `auth` và `auth_psk`. Tuy nhiên, API `javax.crypto.KEM` trong Java 21 chỉ cung cấp primitive encapsulation/decapsulation; nó không phải một implementation HPKE đầy đủ và không tự cung cấp toàn bộ key schedule, wire format hay các mode xác thực của RFC 9180. Nếu ứng dụng cần HPKE, hãy chọn thư viện đã triển khai RFC 9180 và kiểm tra các ciphersuite/provider được hỗ trợ.

## 9. Xác thực danh tính không tự có từ KEM hoặc key agreement

Một shared secret giống nhau ở hai phía không chứng minh hai phía đã nói chuyện với đúng người. Cần xác thực public key và danh tính peer:

- Public key của recipient dùng cho KEM phải được lấy từ nguồn đáng tin cậy, chẳng hạn chứng chỉ đã xác thực, pinning hoặc một kênh phân phối khóa có xác thực.
- Public key dùng trong key agreement phải được xác thực bằng chữ ký, chứng chỉ hoặc cơ chế xác thực khác. Nếu không, kẻ trung gian có thể thay public key trong quá trình trao đổi.
- AEAD xác thực dữ liệu được tạo bằng khóa tương ứng, nhưng trong KEM base mode bất kỳ ai có public key của recipient đều có thể encapsulate và tạo ciphertext hợp lệ. Điều đó không xác định danh tính người gửi.
- Nếu cần xác thực người gửi, dùng chữ ký số, giao thức có authenticated key exchange hoặc một mode HPKE có xác thực phù hợp với KEM và thư viện hỗ trợ.

Không suy luận rằng “đã mã hóa thành công” đồng nghĩa “đã xác thực người gửi”. Bí mật, toàn vẹn và xác thực danh tính là các thuộc tính cần được thiết kế riêng.

## 10. Forward secrecy, vòng đời khóa và chống replay

Forward secrecy phụ thuộc cách tạo, sử dụng và hủy khóa, không chỉ phụ thuộc việc giao thức có tên KEM hay key agreement. Nếu sender encapsulate đến public key dài hạn của recipient, kẻ tấn công lưu được `encapsulation` và ciphertext có thể có cơ hội giải mã dữ liệu cũ nếu sau này private key dài hạn của recipient bị lộ. Muốn có forward secrecy, cần một giao thức và vòng đời khóa được thiết kế để compromise khóa hiện tại không giải mã được các phiên cũ; ví dụ dùng khóa ephemeral phù hợp ở cả hai phía, ratchet hoặc cơ chế thay khóa đã được chuẩn hóa.

AEAD cũng không tự chống replay. Kẻ tấn công có thể phát lại một ciphertext hợp lệ nếu ứng dụng không kiểm tra sequence number, message ID, timestamp hoặc trạng thái đã xử lý. Hãy ràng buộc metadata thích hợp vào AAD và duy trì chính sách chống replay ở tầng giao thức.

Ngoài ra, cần:

- Luân chuyển và thu hồi recipient key theo chính sách.
- Gắn key identifier hoặc thông tin lựa chọn khóa vào định dạng bản tin khi recipient quản lý nhiều key pair.
- Kiểm tra algorithm identifier và phiên bản giao thức, không để bên nhận tự suy đoán thuật toán từ dữ liệu không tin cậy.
- Không log private key, shared secret, AEAD key hoặc dữ liệu nhạy cảm.
- Xử lý lỗi decapsulation/decryption theo cách không làm lộ thông tin nhạy cảm qua thông báo lỗi hoặc timing.

## 11. Định dạng bản tin cần quy định rõ

KEM API trả về encapsulation message nhưng không định nghĩa toàn bộ định dạng bản tin ứng dụng. Giao thức cần quy định cách truyền và diễn giải các trường, ví dụ:

| Trường | Mục đích |
| --- | --- |
| Protocol version | Xác định phiên bản định dạng và quy tắc xử lý. |
| KEM/KDF/AEAD identifiers | Xác định chính xác bộ thuật toán được dùng. |
| Recipient key ID | Chọn đúng private key để decapsulate. |
| Encapsulation message | Dữ liệu công khai đầu vào của decapsulation. |
| Nonce | Tham số cần thiết cho AEAD. |
| Ciphertext và authentication tag | Nội dung đã mã hóa và xác thực. |
| AAD/context fields | Metadata được xác thực cùng ciphertext nhưng không bị mã hóa. |

RFC 9180 định nghĩa HPKE nhưng để ứng dụng sử dụng HPKE quy định cách mã hóa/đóng gói các trường trên dây. Vì vậy, hai hệ thống phải thống nhất serialization, byte order, độ dài, cách xử lý trường thiếu hoặc thừa và cách báo lỗi.

## 12. Lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| Coi encapsulation message là ciphertext dữ liệu | Encapsulation chỉ cho recipient khôi phục shared secret. | Mã hóa payload bằng AEAD sau bước KEM/KDF. |
| Coi KEM và key agreement là cùng một API | KEM có vai trò encapsulate/decapsulate; key agreement có các bên trao đổi key material và cùng tính secret. | Chọn primitive theo mô hình giao thức và API. |
| Gửi shared secret hoặc private key qua mạng | Làm mất mục tiêu của cơ chế khóa công khai. | Chỉ gửi public key, encapsulation và ciphertext theo giao thức. |
| Dùng raw shared secret trực tiếp cho nhiều mục đích | Không có domain separation và quản lý khóa theo ngữ cảnh. | Dẫn xuất khóa riêng bằng KDF đã được chuẩn hóa. |
| Nghĩ KEM tự xác thực người gửi | KEM base mode thường cho phép bất kỳ ai có public key encapsulate. | Bổ sung chữ ký hoặc mode xác thực phù hợp. |
| Nghĩ `KeyAgreement` ngăn MITM | Public key trao đổi có thể bị thay nếu không xác thực. | Xác thực public key và danh tính peer. |
| Tự tạo nonce AES-GCM theo bộ đếm không đồng bộ | Có thể tái sử dụng nonce với cùng khóa. | Dùng chiến lược nonce duy nhất được thiết kế cho giao thức và quản lý theo khóa. |
| Cho rằng KEM API Java 21 là HPKE | `KEM` chỉ cung cấp primitive encapsulation/decapsulation. | Dùng implementation HPKE đầy đủ nếu cần RFC 9180. |
| Giả định mọi JDK 21 đều hỗ trợ mọi KEM | Provider quyết định thuật toán và loại khóa được hỗ trợ. | Kiểm tra provider, thuật toán và loại key trên runtime triển khai. |
| Giả định `ML-KEM` là thuật toán chuẩn trong Java 21 | Danh sách tên KEM chuẩn Java SE 21 chỉ nêu `DHKEM`. | Kiểm tra phiên bản JDK/provider; không gán tính năng của phiên bản mới cho Java 21. |

## 13. Cách chọn primitive

| Nhu cầu | Thành phần nên xem xét |
| --- | --- |
| Gửi dữ liệu đến public key của recipient và tạo shared secret | KEM. |
| Hai peer cùng trao đổi key share và tính shared secret | Key agreement như ECDH/X25519. |
| Mã hóa dữ liệu lớn hoặc luồng dữ liệu | AEAD với khóa đối xứng được dẫn xuất hoặc quản lý an toàn. |
| Cần một giao thức public-key encryption có KEM, KDF, AEAD và key schedule đã quy định | HPKE theo RFC 9180 qua thư viện phù hợp. |
| Cần xác thực danh tính peer | Chứng chỉ/chữ ký hoặc mode authenticated key establishment phù hợp. |
| Cần thuật toán hậu lượng tử | Chọn KEM hậu lượng tử đã được chuẩn hóa và provider/thư viện có hỗ trợ; kiểm tra riêng khả năng tương thích với Java 21. |

## 14. Tài liệu tham khảo chính thức

- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452): lý do và API KEM được đưa vào Java 21.
- [Java SE 21 API — `javax.crypto.KEM`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): `Encapsulator`, `Encapsulated`, `Decapsulator`, `encapsulate()` và `decapsulate()`.
- [Java SE 21 API — `javax.crypto.KeyAgreement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyAgreement.html): `init`, `doPhase` và `generateSecret`.
- [Java SE 21 API — `javax.crypto.Cipher`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html): API mã hóa và giải mã đối xứng.
- [Java SE 21 API — `GCMParameterSpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tham số nonce và độ dài authentication tag cho GCM.
- [Java Security Standard Algorithm Names — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên thuật toán KEM, KeyAgreement và Cipher trong Java 21.
- [JDK Providers Documentation — Java 21](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html): thuật toán `DHKEM` của SunJCE và các loại khóa được hỗ trợ.
- [RFC 9180 — Hybrid Public Key Encryption (HPKE)](https://www.rfc-editor.org/rfc/rfc9180.html): mô hình KEM + KDF + AEAD, các mode và key schedule.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869.html): cơ chế dẫn xuất khóa từ input keying material.
- [RFC 5116 — An Interface and Algorithms for Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116.html): giao diện AEAD và cách sử dụng associated data.
