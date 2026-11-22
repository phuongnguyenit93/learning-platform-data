# Key Encapsulation Mechanism và vai trò chia sẻ khóa đối xứng

Key Encapsulation Mechanism (KEM) là cơ chế dùng mật mã khóa công khai để hai bên thiết lập cùng một bí mật mà không gửi bí mật đó trực tiếp qua mạng. Bên gửi dùng public key của bên nhận để tạo một shared secret mới và một thông điệp encapsulation. Bên nhận dùng private key tương ứng cùng thông điệp đó để khôi phục cùng shared secret.

Shared secret sau đó được dùng làm khóa đối xứng hoặc đầu vào cho Key Derivation Function (KDF), rồi kết hợp với thuật toán đối xứng như AES-GCM hoặc ChaCha20-Poly1305 để bảo vệ dữ liệu. Đây là mô hình mật mã lai: khóa công khai giải quyết việc thiết lập bí mật, còn mật mã đối xứng xử lý dữ liệu hiệu quả.

Trong Java 21, API KEM chính thức nằm trong package `javax.crypto`, được giới thiệu qua JEP 452. JDK 21 cung cấp triển khai DHKEM; các thuật toán khác phụ thuộc security provider được cài đặt. Bài viết tập trung vào API và hành vi có trong Java 21, đồng thời phân biệt DHKEM cổ điển với các KEM hậu lượng tử đã được chuẩn hóa sau đó.

## 1. Vấn đề KEM giải quyết

Mật mã đối xứng như AES rất phù hợp để mã hóa lượng dữ liệu lớn, nhưng hai bên cần có cùng khóa bí mật trước khi trao đổi dữ liệu. Nếu gửi khóa AES nguyên dạng qua một kênh công khai, người nghe lén có thể lấy được khóa và giải mã dữ liệu.

Mật mã khóa công khai cung cấp một cách để thiết lập bí mật mà không phải truyền khóa đối xứng trực tiếp. KEM chuẩn hóa quy trình này thành hai thao tác:

- **Encapsulation:** bên gửi sử dụng public key của bên nhận để tạo shared secret và encapsulation message.
- **Decapsulation:** bên nhận sử dụng private key tương ứng và encapsulation message để tạo lại shared secret.

Hai bên có cùng shared secret, trong khi người chỉ nhìn thấy public key và encapsulation message không thể dễ dàng tính ra bí mật nếu thuật toán và khóa được chọn đúng.

~~~text
Bên nhận                                      Bên gửi
---------                                     --------
Tạo key pair
(public key, private key)
       |
       +------ public key -------------------->
                                               Dùng public key
                                               để encapsulate
                                               |
                                               +--> shared secret S
                                               |
                                               +--> encapsulation E
       <---------------- E --------------------+
       |
Dùng private key và E
để decapsulate
       |
       +--> shared secret S

Hai bên có cùng S
       |
       v
Dùng S hoặc khóa dẫn xuất để mã hóa đối xứng
       |
       v
Trao đổi dữ liệu bằng AEAD
~~~

Điểm quan trọng: bên gửi không gửi shared secret qua mạng. Bên nhận tính lại bí mật từ private key của mình và encapsulation message.

## 2. Quy trình encapsulation và decapsulation

Một KEM thường có ba thành phần logic:

1. **Key pair của bên nhận:** gồm public key được phân phối cho bên gửi và private key được bảo vệ ở bên nhận.
2. **Encapsulation message:** dữ liệu công khai được tạo trong quá trình encapsulation; bên nhận cần nhận đúng thông điệp này để decapsulate.
3. **Shared secret:** bí mật được tạo ở bên gửi và khôi phục ở bên nhận.

### Phía gửi

Bên gửi đã có public key đáng tin cậy của bên nhận. Nó gọi encapsulation để tạo ra:

- Một shared secret mới.
- Một encapsulation message cần gửi cho bên nhận.
- Có thể có thêm tham số thuật toán nếu KEM/provider yêu cầu.

Mỗi lần encapsulate thành công tạo một shared secret và encapsulation message mới. Bên gửi giữ bí mật, chỉ gửi encapsulation message cùng dữ liệu được bảo vệ.

### Phía nhận

Bên nhận nhận encapsulation message, dùng private key tương ứng gọi decapsulation và nhận lại shared secret. Nếu cả hai bên dùng đúng thuật toán, khóa và tham số, kết quả shared secret sẽ giống nhau.

Nếu encapsulation message không hợp lệ hoặc không đúng kích thước, thao tác decapsulation có thể thất bại. Ứng dụng phải xử lý lỗi theo giao thức và không tiếp tục giải mã bằng một khóa không hợp lệ.

## 3. KEM khác mã hóa đối xứng và key agreement thế nào?

KEM, mã hóa đối xứng và key agreement đều liên quan đến khóa nhưng có vai trò khác nhau.

| Cơ chế | Mục đích | Dữ liệu đầu ra điển hình |
|---|---|---|
| KEM | Thiết lập shared secret qua public key | Shared secret và encapsulation message |
| Mã hóa đối xứng | Bảo vệ dữ liệu bằng khóa chung | Ciphertext và thông tin nonce/tag cần thiết |
| Key agreement như X25519 | Hai bên dùng key pair của mình để cùng tính shared secret | Shared secret từ phép tính key agreement |
| KDF | Tạo khóa hoặc material riêng từ shared secret | Một hoặc nhiều khóa theo mục đích sử dụng |

KEM không phải thuật toán mã hóa dữ liệu lớn. Nó chỉ thiết lập khóa. Không nên dùng encapsulation message như ciphertext của tài liệu hoặc file cần bảo vệ.

KEM cũng không đồng nghĩa với việc mã hóa một khóa AES đã có sẵn. Thông thường KEM tạo shared secret mới; nếu ứng dụng cần bảo vệ một khóa đã tồn tại, đó là bài toán key wrapping hoặc cơ chế phân phối khóa khác.

DHKEM có thể sử dụng phép toán Diffie-Hellman bên trong, nhưng API KEM biểu diễn quy trình theo cặp thao tác encapsulate/decapsulate. Với key agreement truyền thống, cả hai bên thường tạo key pair và trao đổi public key để cùng tính bí mật. Với KEM, bên nhận có thể tạo trước key pair, còn bên gửi chỉ cần public key của bên nhận để encapsulate.

## 4. KEM là phần thiết lập khóa của mật mã lai

Mô hình phổ biến là kết hợp KEM với KDF và Authenticated Encryption with Associated Data (AEAD):

1. KEM tạo shared secret.
2. KDF dẫn xuất khóa đối xứng từ shared secret và context của phiên.
3. AEAD mã hóa dữ liệu, đồng thời xác thực ciphertext và associated data.
4. Bên nhận decapsulate, dẫn xuất cùng khóa và xác thực/giải mã dữ liệu.

~~~text
Public key bên nhận
       |
       v
     KEM --------------------> Encapsulation message
       |
       v
  Shared secret
       |
       v
      KDF <------------------- Context / protocol info
       |
       v
   AEAD key
       |
Plaintext ---> AEAD encrypt ---> Ciphertext + nonce + tag
                                      |
                                      v
                         Gửi cùng encapsulation message
~~~

KDF hữu ích khi cần tách khóa theo mục đích: ví dụ một khóa cho mã hóa dữ liệu, một khóa cho xác thực hoặc các khóa theo từng hướng truyền. Context nên chứa thông tin phân biệt giao thức, phiên, vai trò hai bên và mục đích khóa để tránh dùng nhầm cùng key material ở những ngữ cảnh khác nhau.

KEM API của Java 21 cung cấp shared secret. Nó không phải một API hoàn chỉnh để xây dựng toàn bộ giao thức mật mã lai. Java 21 cũng không định nghĩa một KDF engine chuẩn trong `javax.crypto`; nếu cần KDF như HKDF trong ứng dụng, hãy dùng một triển khai/provider đã được đánh giá hoặc một giao thức cấp cao đã được chuẩn hóa. Không tự thiết kế phép băm hoặc cắt byte tùy tiện để thay thế KDF.

## 5. API KEM trong Java 21

Java 21 bổ sung lớp `javax.crypto.KEM` trong module `java.base`. API cung cấp các kiểu chính:

| Kiểu | Vai trò |
|---|---|
| `KEM` | Lấy implementation của thuật toán KEM và tạo encapsulator/decapsulator |
| `KEM.Encapsulator` | Thực hiện encapsulation ở phía gửi |
| `KEM.Decapsulator` | Thực hiện decapsulation ở phía nhận |
| `KEM.Encapsulated` | Chứa shared secret, encapsulation message và tham số tùy chọn |

Các phương thức thường dùng:

- `KEM.getInstance(algorithm)`: lấy implementation của thuật toán từ security provider phù hợp.
- `newEncapsulator(publicKey)`: tạo encapsulator với public key của bên nhận.
- `encapsulate()`: tạo shared secret và encapsulation message.
- `newDecapsulator(privateKey)`: tạo decapsulator với private key của bên nhận.
- `decapsulate(encapsulation)`: khôi phục shared secret từ encapsulation message.

`KEM`, `Encapsulator` và `Decapsulator` là các đối tượng immutable theo API. Mỗi lần gọi `encapsulate()` sẽ tạo một shared secret và encapsulation message mới.

### Thuật toán DHKEM có trong JDK 21

Tên chuẩn của thuật toán KEM trong JDK 21 là `DHKEM`, được định nghĩa trong RFC 9180. SunJCE provider của Oracle JDK 21 hỗ trợ DHKEM với:

- EC key trên các curve `secp256r1`, `secp384r1`, `secp521r1`.
- XDH key trên `Curve25519` và `Curve448`, thường được gọi tương ứng là `X25519` và `X448` trong API tạo key.

Ví dụ trong bài dùng X25519 để giữ code ngắn. Việc `KEM.getInstance("DHKEM")` thành công còn phụ thuộc provider trong runtime có hỗ trợ thuật toán và loại key tương ứng hay không. Nếu không có provider phù hợp, Java ném `NoSuchAlgorithmException` hoặc lỗi liên quan đến key/parameters.

Ứng dụng tổng quát thường nên để JCA chọn provider thay vì hard-code tên provider. Có thể kiểm tra provider thực sự được chọn bằng `providerName()` trên encapsulator hoặc decapsulator.

## 6. Ví dụ Java 21: tạo shared AES key bằng DHKEM

Ví dụ sau minh họa cả hai phía trong cùng một chương trình:

1. Bên nhận tạo cặp khóa X25519.
2. Bên gửi dùng public key để encapsulate và lấy khóa AES-128.
3. Bên nhận dùng private key cùng encapsulation message để lấy lại khóa AES-128.
4. Hai bên dùng khóa đó với AES-GCM để mã hóa và giải mã dữ liệu.

Java KEM API hỗ trợ overload `encapsulate(from, to, algorithm)` và `decapsulate(encapsulation, from, to, algorithm)`. Với `from = 0`, `to = 16`, `algorithm = "AES"`, API yêu cầu 16 byte đầu của shared secret làm khóa AES-128. Provider phải hỗ trợ tổ hợp tham số này.

~~~java
import javax.crypto.Cipher;
import javax.crypto.KEM;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.util.Arrays;

public class KemAesExample {
    public static void main(String[] args) throws Exception {
        // Bên nhận tạo key pair và bảo vệ private key.
        KeyPairGenerator keyPairGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeyPair = keyPairGenerator.generateKeyPair();

        // Hai phía dùng cùng thuật toán KEM.
        KEM kem = KEM.getInstance("DHKEM");

        // Bên gửi: dùng public key của bên nhận để tạo AES-128 key.
        KEM.Encapsulated encapsulated = kem
                .newEncapsulator(recipientKeyPair.getPublic())
                .encapsulate(0, 16, "AES");

        SecretKey senderKey = encapsulated.key();
        byte[] encapsulationMessage = encapsulated.encapsulation();

        // Bên gửi mã hóa payload bằng AES-GCM.
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);

        byte[] aad = "protocol=v1;recipient=receiver-01"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Sensitive message"
                .getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(
                Cipher.ENCRYPT_MODE,
                senderKey,
                new GCMParameterSpec(128, nonce)
        );
        encryptor.updateAAD(aad);
        byte[] ciphertext = encryptor.doFinal(plaintext);

        // Bên nhận: dùng private key và encapsulation để tạo cùng AES key.
        SecretKey receiverKey = kem
                .newDecapsulator(recipientKeyPair.getPrivate())
                .decapsulate(encapsulationMessage, 0, 16, "AES");

        // Bên nhận xác thực và giải mã payload.
        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(
                Cipher.DECRYPT_MODE,
                receiverKey,
                new GCMParameterSpec(128, nonce)
        );
        decryptor.updateAAD(aad);
        byte[] recovered = decryptor.doFinal(ciphertext);

        System.out.println(Arrays.equals(
                senderKey.getEncoded(),
                receiverKey.getEncoded()
        )); // true

        System.out.println(
                new String(recovered, StandardCharsets.UTF_8)
        ); // Sensitive message
    }
}
~~~

Trong một giao thức thực tế, bên gửi chuyển cho bên nhận ít nhất các dữ liệu sau:

- Encapsulation message.
- Nonce của AES-GCM.
- Ciphertext, bao gồm authentication tag.
- Định danh thuật toán/phiên bản giao thức và key identifier cần thiết.

Bên nhận phải chọn đúng private key theo key identifier, decapsulate đúng encapsulation message, sau đó dùng đúng nonce và associated data để giải mã.

Ví dụ tạo key pair ngay trong một tiến trình chỉ nhằm minh họa API. Trong hệ thống thật, bên nhận tạo và quản lý key pair trong vòng đời dài hơn; private key cần được lưu trữ an toàn và public key cần được phân phối qua một kênh có xác thực.

## 7. Dùng shared secret đầy đủ làm đầu vào KDF

Nếu gọi `encapsulate()` không tham số, API trả về toàn bộ shared secret dưới dạng `SecretKey` có algorithm name là `Generic`. Java API mô tả khóa này thường được dùng làm input keying material cho KDF.

~~~java
KEM.Encapsulated result =
        kem.newEncapsulator(recipientPublicKey).encapsulate();

SecretKey inputKeyingMaterial = result.key();
byte[] encapsulationMessage = result.encapsulation();
~~~

Bên nhận lấy cùng input keying material:

~~~java
SecretKey inputKeyingMaterial = kem
        .newDecapsulator(recipientPrivateKey)
        .decapsulate(encapsulationMessage);
~~~

Sau đó hai phía dùng cùng một KDF và cùng context để dẫn xuất khóa đối xứng. Context cần được xác định bởi giao thức, không được tùy ý thay đổi giữa hai phía. Ví dụ, nếu một phiên cần khóa mã hóa theo chiều gửi và khóa mã hóa theo chiều nhận, KDF nên tạo hai khóa tách biệt với nhãn khác nhau.

Overload `encapsulate(from, to, algorithm)` cho phép lấy một đoạn của shared secret và gắn tên thuật toán khóa, ví dụ AES. Đây là tiện ích của KEM API, không phải một KDF tổng quát có context separation. Với giao thức cần nhiều khóa hoặc có yêu cầu dẫn xuất phức tạp, dùng KDF được chuẩn hóa và triển khai đáng tin cậy.

## 8. Encapsulation message và tham số tùy chọn

`KEM.Encapsulated` chứa ba thành phần:

- `key()`: shared secret dưới dạng `SecretKey`.
- `encapsulation()`: key encapsulation message cần gửi cho bên nhận.
- `params()`: tham số được mã hóa thành byte array nếu thuật toán/provider cần truyền thêm thông tin để bên nhận tạo decapsulator tương ứng.

Với DHKEM mặc định trong ví dụ, ứng dụng sử dụng cặp key tương thích và không cần tự đóng gói tham số riêng. Tuy nhiên, API cho phép thuật toán/provider nhận `AlgorithmParameterSpec` khi tạo encapsulator hoặc decapsulator. Nếu tham số cần truyền sang bên nhận, nó có thể được đặt trong `params()` của kết quả encapsulation. Giao thức phải truyền và khôi phục đúng tham số đó để tạo decapsulator tương ứng.

Không nên giả định mọi KEM provider hỗ trợ mọi tổ hợp `from`, `to`, tên thuật toán hoặc parameter spec. Hợp đồng của provider quyết định các tổ hợp được hỗ trợ. Hãy kiểm tra tài liệu provider và xử lý `UnsupportedOperationException`, `InvalidAlgorithmParameterException` hoặc lỗi key phù hợp.

## 9. KEM không tự xác thực danh tính bên gửi

KEM giúp bên gửi tạo shared secret cho bên nhận có public key tương ứng. Nhưng chỉ riêng KEM không chứng minh ai là người tạo encapsulation message.

Bất kỳ ai có public key của bên nhận đều có thể tạo encapsulation mới và gửi ciphertext tới bên nhận. Vì vậy:

- Bên gửi phải xác minh public key thực sự thuộc về bên nhận, chẳng hạn qua chứng thư số, PKI hoặc key pinning.
- Nếu bên nhận cần biết danh tính bên gửi, phải thêm cơ chế xác thực như chữ ký số hoặc dùng một giao thức đã định nghĩa chế độ xác thực phù hợp.
- AEAD xác thực ciphertext và associated data theo khóa phiên, nhưng không tự chứng minh danh tính người gửi nếu ai cũng có thể tạo một phiên KEM với public key công khai.
- Cần có chính sách chống replay ở tầng giao thức nếu việc nhận lại một thông điệp hợp lệ có thể gây tác dụng phụ.

Associated data của AEAD có thể ràng buộc phiên bản giao thức, key identifier, loại thông điệp hoặc metadata quan trọng với ciphertext. Nó không thay thế xác thực danh tính public key hay chữ ký số.

## 10. KEM và HPKE

Hybrid Public Key Encryption (HPKE, RFC 9180) là một giao thức mật mã lai kết hợp ba thành phần chính:

- KEM để thiết lập shared secret.
- KDF để dẫn xuất key schedule.
- AEAD để mã hóa và xác thực dữ liệu.

DHKEM trong JDK 21 là một thuật toán KEM được định nghĩa trong RFC 9180. Tuy nhiên, việc Java cung cấp `javax.crypto.KEM` không có nghĩa JDK 21 đã cung cấp đầy đủ API HPKE. Ứng dụng cần HPKE nên dùng một triển khai thư viện đã được kiểm tra và tương thích RFC 9180, thay vì tự ghép các bước thành một giao thức riêng.

Dùng một giao thức chuẩn giúp giảm rủi ro sai khác về context, key schedule, nonce, xác thực và định dạng thông điệp giữa hai phía.

## 11. Provider, thuật toán và khả năng tương thích

KEM API tuân theo kiến trúc JCA provider. `KEM.getInstance("DHKEM")` tìm provider có implementation phù hợp. Việc chọn provider còn có thể phụ thuộc loại public key/private key và parameter spec được truyền vào `newEncapsulator` hoặc `newDecapsulator`.

Có thể quan sát provider đã được chọn:

~~~java
KEM kem = KEM.getInstance("DHKEM");

KEM.Encapsulator encapsulator =
        kem.newEncapsulator(recipientPublicKey);

System.out.println(encapsulator.providerName());
~~~

Không nên ép một provider cụ thể nếu ứng dụng không có yêu cầu triển khai rõ ràng. Nếu bên gửi và bên nhận dùng runtime/provider khác nhau, cần xác nhận hai phía hỗ trợ cùng thuật toán, loại key, encoding và parameter spec. Một API chuẩn không bảo đảm mọi provider đều có cùng danh sách thuật toán hoặc cùng khả năng mở rộng.

Các lỗi có thể gặp:

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NoSuchAlgorithmException` | Không có provider hỗ trợ tên KEM yêu cầu | Kiểm tra thuật toán và provider đã cài đặt |
| `InvalidKeyException` | Public key hoặc private key không phù hợp với KEM | Kiểm tra loại key, curve và nguồn key |
| `InvalidAlgorithmParameterException` | Parameter spec không hợp lệ hoặc không được hỗ trợ | Dùng tham số đúng theo tài liệu thuật toán |
| `DecapsulateException` | Encapsulation message không hợp lệ hoặc quá trình decapsulation thất bại | Kiểm tra định dạng, độ dài, thuật toán và xử lý như lỗi giao thức |
| `UnsupportedOperationException` | Provider không hỗ trợ overload hoặc tổ hợp tham số được yêu cầu | Dùng tổ hợp được provider hỗ trợ hoặc provider khác đã được đánh giá |

Không tiết lộ private key, shared secret hoặc nội dung nhạy cảm trong log khi xử lý các lỗi này. Log nên chứa mã lỗi, key identifier không nhạy cảm, thuật toán và correlation ID cần thiết.

## 12. Lưu ý bảo vệ khóa và dữ liệu

Khi đưa KEM vào ứng dụng, cần bảo vệ cả key pair lẫn key material sinh ra:

- Private key của bên nhận phải được bảo vệ bằng keystore, HSM hoặc cơ chế quản lý bí mật phù hợp.
- Public key phải được xác thực trước khi bên gửi sử dụng.
- Shared secret và khóa đối xứng không được ghi log, đưa vào telemetry hoặc lưu trữ tùy tiện.
- Không truyền shared secret qua mạng; chỉ truyền encapsulation message.
- Mỗi khóa AES-GCM phải dùng nonce duy nhất theo yêu cầu của GCM. Nếu tái sử dụng khóa cho nhiều bản tin, phải có bộ đếm/nonce strategy bảo đảm không lặp nonce.
- Dùng AEAD để vừa bảo vệ bí mật vừa phát hiện sửa đổi dữ liệu.
- Có key identifier, phiên bản thuật toán và quy trình rotation để bên nhận biết private key nào cần dùng.
- Xử lý replay ở tầng giao thức; KEM không tự ngăn một encapsulation message hợp lệ bị gửi lại.

Khi cần bảo vệ dữ liệu dài hạn, phải chọn thuật toán và chiến lược key lifecycle theo thời gian lưu trữ, mô hình đe dọa và yêu cầu tuân thủ. Không mặc định một thuật toán KEM có trong JDK là lựa chọn phù hợp cho mọi hệ thống.

## 13. DHKEM và KEM hậu lượng tử

DHKEM trong JDK 21 dựa trên Diffie-Hellman với EC/XDH key. Đây là mật mã khóa công khai cổ điển, không phải KEM hậu lượng tử. Vì vậy, không nên mô tả DHKEM/X25519 là có khả năng chống lại máy tính lượng tử quy mô đủ lớn.

NIST đã công bố FIPS 203 cho ML-KEM vào tháng 8 năm 2024. ML-KEM là KEM dựa trên lattice và được chuẩn hóa cho mục tiêu mật mã hậu lượng tử. Tuy nhiên, danh sách thuật toán của SunJCE trong JDK 21 cung cấp DHKEM; không được suy luận rằng `KEM.getInstance("ML-KEM")` sẽ hoạt động trong mọi cài đặt Java 21.

Nếu hệ thống cần ML-KEM, hãy kiểm tra provider cụ thể có triển khai chuẩn FIPS 203 hay không, hỗ trợ parameter set nào và cách mã hóa key/encapsulation tương thích giữa các bên. Không dùng các bản thử nghiệm hoặc tên thuật toán tiền chuẩn hóa thay cho ML-KEM đã được chuẩn hóa nếu yêu cầu là FIPS 203.

## 14. Khi nào nên dùng KEM?

KEM phù hợp khi ứng dụng cần thiết lập một bí mật đối xứng qua kênh công khai bằng public key của bên nhận. Những trường hợp thường gặp:

- Thiết lập khóa phiên để mã hóa dữ liệu lớn.
- Xây dựng giao thức mã hóa lai.
- Là thành phần của giao thức HPKE hoặc giao thức bảo mật cấp cao khác.
- Phân phối một bí mật mới cho bên nhận mà không truyền bí mật trực tiếp.
- Chuẩn bị kiến trúc có thể thay đổi thuật toán KEM qua provider khi yêu cầu mật mã thay đổi.

KEM không phù hợp để thay thế trực tiếp AES-GCM khi mã hóa payload, cũng không thay thế chữ ký số để xác thực danh tính. Nếu ứng dụng chỉ cần trao đổi dữ liệu qua mạng, hãy ưu tiên giao thức đã được kiểm chứng như TLS thay vì tự xây dựng giao thức truyền khóa và mã hóa.

## 15. Checklist khi tích hợp KEM vào Java 21

Trước khi đưa KEM vào môi trường thật, hãy xác nhận:

1. Hai bên thống nhất tên thuật toán, provider capability, loại key và parameter spec.
2. Public key của bên nhận được xác thực trước khi encapsulate.
3. Private key được lưu và truy cập qua cơ chế bảo vệ phù hợp.
4. Encapsulation message được truyền đầy đủ và gắn với đúng key identifier/phiên bản giao thức.
5. Hai phía dùng cùng KDF và context nếu cần dẫn xuất khóa từ shared secret.
6. Payload được bảo vệ bằng AEAD với nonce duy nhất và associated data nhất quán.
7. Có cơ chế xác thực bên gửi nếu nghiệp vụ yêu cầu danh tính.
8. Có xử lý replay, key rotation, timeout và lỗi decapsulation.
9. Không log hoặc lưu shared secret và private key.
10. Nếu yêu cầu hậu lượng tử, provider phải hỗ trợ ML-KEM theo FIPS 203; DHKEM của JDK 21 không đáp ứng yêu cầu đó.

## Kết luận

KEM cho phép bên gửi và bên nhận thiết lập cùng một shared secret qua public channel mà không gửi trực tiếp khóa bí mật. Bên gửi encapsulate bằng public key; bên nhận decapsulate bằng private key để lấy lại cùng secret. Secret này được dùng trực tiếp theo hợp đồng thuật toán hoặc đưa qua KDF, rồi kết hợp với AEAD để bảo vệ dữ liệu.

Java 21 chuẩn hóa quy trình đó bằng `javax.crypto.KEM` và cung cấp DHKEM trong JDK. Khi tích hợp, cần xác thực public key, quản lý private key, dùng KDF/AEAD đúng giao thức, xử lý replay và kiểm tra provider. KEM là nền tảng thiết lập khóa trong mật mã lai, không phải cơ chế mã hóa payload hay xác thực danh tính độc lập.

## Tài liệu tham khảo

- [Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 21 API — KEM.Encapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html)
- [Java SE 21 API — KEM.Decapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html)
- [Java SE 21 API — KEM.Encapsulated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html)
- [Oracle JDK 21 — JDK Providers / SunJCE](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html)
- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180)
- [NIST FIPS 203 — Module-Lattice-Based Key-Encapsulation Mechanism Standard](https://csrc.nist.gov/pubs/fips/203/final)
