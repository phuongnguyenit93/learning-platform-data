# Tạo Decapsulator từ private key để khôi phục shared secret

Java 21 cung cấp **Key Encapsulation Mechanism (KEM) API** trong `javax.crypto`. Ở phía nhận, ứng dụng tạo `KEM.Decapsulator` từ private key tương ứng với public key mà bên gửi đã dùng để encapsulate. Khi nhận được dữ liệu encapsulation, gọi `decapsulate(...)` để khôi phục cùng shared secret mà bên gửi nhận được.

KEM không phải thao tác giải mã ciphertext của dữ liệu ứng dụng. Bên gửi dùng public key của người nhận để tạo một shared secret và một gói encapsulation công khai; bên nhận dùng private key tương ứng cùng gói đó để tái tạo shared secret. Shared secret sau đó được dùng làm key hoặc đầu vào cho bước bảo vệ dữ liệu bằng thuật toán đối xứng, chẳng hạn AEAD.

## 1. Vai trò của Decapsulator trong KEM

Một quy trình KEM cơ bản có hai phía:

1. **Bên nhận** sở hữu một cặp khóa bất đối xứng gồm public key và private key. Private key được giữ bí mật; public key được phân phối cho bên gửi qua một kênh có xác thực.
2. **Bên gửi** tạo `KEM.Encapsulator` từ public key của bên nhận, sau đó gọi `encapsulate()` để nhận shared secret và dữ liệu encapsulation.
3. Bên gửi gửi dữ liệu encapsulation cùng ciphertext ứng dụng cho bên nhận. Shared secret không cần gửi qua mạng.
4. **Bên nhận** tạo `KEM.Decapsulator` từ private key của mình, rồi gọi `decapsulate(encapsulation)` để khôi phục shared secret.
5. Hai phía dùng shared secret theo cùng một quy trình dẫn xuất khóa và mã hóa/giải mã đối xứng.

```text
BÊN GỬI                                      BÊN NHẬN

Nhận public key <------------------------- Public/private key pair
      |
KEM.newEncapsulator(publicKey)
      |
encapsulate()
      |                                      Private key
      +-- shared secret (giữ cục bộ)             |
      +-- encapsulation --------------------> KEM.newDecapsulator(privateKey)
             + ciphertext ứng dụng                 |
                                             decapsulate(encapsulation)
                                                    |
                                             shared secret giống bên gửi
```

`KEM.Decapsulator` là đối tượng thực hiện bước decapsulation. Nó được tạo từ private key, không phải từ public key hoặc từ ciphertext ứng dụng.

## 2. API Java 21 cần biết

Các kiểu chính nằm trong package `javax.crypto`:

| API | Vai trò |
|---|---|
| `KEM` | Lấy implementation KEM từ provider và tạo encapsulator/decapsulator |
| `KEM.getInstance(String)` | Chọn thuật toán KEM được provider hỗ trợ |
| `KEM.newDecapsulator(PrivateKey)` | Tạo decapsulator từ private key |
| `KEM.Decapsulator` | Đối tượng thực hiện decapsulation |
| `KEM.Decapsulator.decapsulate(byte[])` | Nhận encapsulation bytes và trả về `SecretKey` |
| `KEM.Decapsulator.secretSize()` | Cho biết kích thước shared secret theo byte |
| `KEM.DecapsulateException` | Báo lỗi trong quá trình decapsulation |

Phía gửi dùng các API tương ứng:

- `KEM.newEncapsulator(PublicKey)` tạo encapsulator từ public key người nhận.
- `KEM.Encapsulator.encapsulate()` tạo một `KEM.Encapsulated`.
- `KEM.Encapsulated.key()` trả về shared secret phía gửi.
- `KEM.Encapsulated.encapsulation()` trả về byte array cần chuyển cho bên nhận.

KEM API là API chính thức trong Java 21, không cần bật preview. Tuy nhiên, thuật toán KEM cụ thể phụ thuộc provider được cài đặt trong runtime. Có `KEM` API trong JDK không đồng nghĩa mọi provider đều hỗ trợ mọi thuật toán hoặc mọi loại khóa.

## 3. Tạo Decapsulator từ private key

Giả sử bên nhận đã có private key và đã nhận byte array encapsulation từ bên gửi. Các bước cốt lõi:

```java
import java.security.PrivateKey;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

static SecretKey recoverSecret(PrivateKey recipientPrivateKey,
                               byte[] encapsulation)
        throws Exception {

    KEM kem = KEM.getInstance("DHKEM");
    KEM.Decapsulator decapsulator =
            kem.newDecapsulator(recipientPrivateKey);

    return decapsulator.decapsulate(encapsulation);
}
```

Ý nghĩa:

- `KEM.getInstance("DHKEM")` yêu cầu một provider cung cấp implementation có tên `DHKEM`.
- `newDecapsulator(recipientPrivateKey)` khởi tạo decapsulator từ private key người nhận.
- `decapsulate(encapsulation)` dùng private key và dữ liệu encapsulation để tạo lại shared secret, trả về dưới dạng `SecretKey`.

Trong code production, nên khai báo các exception cụ thể thay vì `throws Exception`. Ví dụ hoàn chỉnh ở phần sau dùng `GeneralSecurityException` để bao quát lỗi lấy thuật toán, khóa không phù hợp và lỗi decapsulation.

## 4. Ví dụ đầy đủ với DHKEM và X25519

Ví dụ sau chạy cả hai phía trong cùng một JVM để minh họa hai shared secret khớp nhau. Trong hệ thống thực tế, bên nhận tạo hoặc nạp key pair một lần, bảo vệ private key trong key store/HSM phù hợp và phân phối public key có xác thực.

```java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemDecapsulationDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        // Bên nhận tạo key pair X25519 cho ví dụ.
        KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = keyPairGenerator.generateKeyPair();

        KEM kem = KEM.getInstance("DHKEM");

        // BÊN GỬI: dùng public key đã được xác thực của bên nhận.
        KEM.Encapsulator encapsulator =
                kem.newEncapsulator(recipientKeys.getPublic());
        KEM.Encapsulated encapsulated = encapsulator.encapsulate();

        SecretKey senderSecret = encapsulated.key();
        byte[] encapsulation = encapsulated.encapsulation();

        // BÊN NHẬN: dùng private key tương ứng để decapsulate.
        KEM.Decapsulator decapsulator =
                kem.newDecapsulator(recipientKeys.getPrivate());
        SecretKey recipientSecret = decapsulator.decapsulate(encapsulation);

        // Chỉ so sánh trong ví dụ; không in shared secret ra log.
        byte[] senderBytes = senderSecret.getEncoded();
        byte[] recipientBytes = recipientSecret.getEncoded();

        if (senderBytes == null || recipientBytes == null) {
            throw new IllegalStateException("Provider không cho export key material");
        }

        boolean sameSecret = MessageDigest.isEqual(senderBytes, recipientBytes);
        System.out.println("Shared secrets match: " + sameSecret);
    }
}
```

Với JDK 21 và provider có hỗ trợ `DHKEM` cùng khóa X25519, kết quả mong đợi:

```text
Shared secrets match: true
```

Ví dụ dùng `getEncoded()` chỉ để kiểm tra hai phía trong môi trường demo. Với provider hoặc phần cứng bảo vệ khóa không cho export secret, `getEncoded()` có thể trả về `null`; ứng dụng thực tế nên dùng `SecretKey` trực tiếp trong API mật mã tiếp theo thay vì xuất raw key material.

## 5. Encapsulation là dữ liệu nào và được truyền ra sao?

Kết quả `encapsulate()` là `KEM.Encapsulated`, gồm:

- `key()`: shared secret phía gửi nhận được.
- `encapsulation()`: dữ liệu công khai cần gửi đến bên nhận để decapsulation.
- `params()`: tham số thuật toán nếu implementation cung cấp.

Chỉ byte array `encapsulation()` được gửi đến bên nhận trong bước KEM. Không gửi private key hoặc shared secret. Encapsulation không phải ciphertext của nội dung ứng dụng; nó là dữ liệu đầu vào để bên nhận khôi phục shared secret.

Trong giao thức thực tế, cần đóng gói và truyền thêm thông tin cần thiết để bên nhận xác định đúng phiên bản giao thức, thuật toán, key identifier và ciphertext. Không tự đoán thuật toán từ độ dài byte array; metadata phải được xác định theo format giao thức và được kiểm tra.

## 6. Chọn thuật toán và khóa phù hợp

Tên thuật toán truyền cho `KEM.getInstance(...)` phải được provider hỗ trợ. Trong ví dụ Java 21, `DHKEM` là tên KEM Diffie-Hellman và X25519 là loại khóa dùng để minh họa. Khả năng hỗ trợ còn phụ thuộc provider và tham số khóa.

```java
KEM kem = KEM.getInstance("DHKEM");
KEM.Decapsulator decapsulator = kem.newDecapsulator(recipientPrivateKey);
```

Nếu provider không có implementation `DHKEM`, `getInstance` sẽ thất bại với `NoSuchAlgorithmException`. Nếu private key không tương thích với KEM hoặc tham số của provider, việc tạo decapsulator có thể thất bại với lỗi khóa/tham số tương ứng.

Các điều kiện phải khớp giữa hai phía:

- Public key mà bên gửi dùng phải thuộc đúng cặp với private key của bên nhận.
- Hai phía phải dùng cùng KEM parameter set và quy ước giao thức.
- Bên nhận phải nhận đúng byte array encapsulation do bên gửi tạo.
- Nếu giao thức dùng lựa chọn thuật toán hoặc tham số ngoài mặc định, metadata cần được truyền và xác thực đúng.

Không tạo một key pair mới cho mỗi lần decapsulation. Bên nhận phải nạp đúng private key đã được liên kết với public key công bố cho bên gửi. Việc xoay vòng key cần có key identifier và thời gian chuyển tiếp để bên nhận chọn đúng private key cho từng encapsulation.

## 7. Chọn kích thước và thuật toán của SecretKey

Overload mặc định `encapsulate()` và `decapsulate(byte[])` trả về `SecretKey` theo quy ước mặc định của provider. Khi ứng dụng cần một key có thuật toán và độ dài cụ thể, API có overload cho phép chọn khoảng byte của shared secret và tên thuật toán:

```java
// Ví dụ: tạo AES key từ 16 byte đầu của shared secret.
KEM.Encapsulated encapsulated = encapsulator.encapsulate(0, 16, "AES");

// Bên nhận phải dùng cùng khoảng byte và cùng tên thuật toán.
SecretKey aesKey = decapsulator.decapsulate(
        encapsulated.encapsulation(), 0, 16, "AES");
```

Hai tham số `from` và `to` xác định đoạn byte của shared secret được dùng để tạo key; `to` là giới hạn cuối không bao gồm. Đoạn được chọn phải nằm trong kích thước shared secret do KEM cung cấp. Hai phía phải dùng cùng khoảng byte và thuật toán để tạo key tương ứng.

Với DHKEM/X25519, shared secret có kích thước theo đặc tả của KEM. Không áp dụng tùy tiện một độ dài cho mọi KEM: hãy kiểm tra `secretSize()` và tài liệu provider/thuật toán. Nếu ứng dụng cần một key size khác hoặc cần dẫn xuất nhiều key cho các mục đích khác nhau, dùng KDF được thiết kế cho giao thức thay vì cắt byte theo ý muốn.

Việc đặt tên thuật toán là `AES` không tự mã hóa dữ liệu. Nó chỉ xác định loại `SecretKey` mà API tạo ra; bước mã hóa nội dung cần dùng `Cipher` với chế độ AEAD và nonce phù hợp.

## 8. Xử lý lỗi khi decapsulate

Một số lỗi có thể xảy ra:

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `NoSuchAlgorithmException` | Provider không hỗ trợ tên KEM yêu cầu | Kiểm tra provider, thuật toán và runtime được triển khai |
| `InvalidKeyException` | Private key không phù hợp với KEM | Nạp đúng private key và kiểm tra loại/parameter set |
| `InvalidAlgorithmParameterException` | Tham số KEM không được hỗ trợ hoặc không hợp lệ | Dùng tham số được provider công bố và đồng nhất với bên gửi |
| `DecapsulateException` | Encapsulation không hợp lệ hoặc provider không thể hoàn tất decapsulation | Từ chối thông điệp, ghi nhận lỗi an toàn và không dùng secret chưa xác minh |
| `NullPointerException` | Encapsulation hoặc đối số bắt buộc là null | Kiểm tra dữ liệu đầu vào tại ranh giới giao thức |

`DecapsulateException` là lỗi bảo mật/đầu vào cần được xử lý như một lần decapsulation thất bại. Không dùng một shared secret mặc định khi decapsulation lỗi và không tiếp tục giải mã ciphertext bằng key rỗng hoặc key cũ.

Không nhất thiết mọi byte array sai đều tạo cùng một lỗi dễ phân biệt. Hãy tránh phản hồi chi tiết cho đối tượng bên ngoài về việc private key nào tồn tại hoặc lỗi mật mã nội bộ nào xảy ra; thông tin trả về cần tuân theo giao thức và không tạo oracle hữu ích cho kẻ tấn công.

## 9. KEM không thay thế mã hóa AEAD hoặc xác thực danh tính

KEM chỉ thiết lập shared secret. Nó không tự mã hóa payload ứng dụng, không cung cấp cấu trúc nonce/tag của AEAD và không chứng minh ai là người gửi.

Một thiết kế bảo vệ dữ liệu thường có các bước:

1. Xác thực và lấy public key của bên nhận.
2. Encapsulate để tạo shared secret và encapsulation bytes.
3. Dùng KDF/key schedule phù hợp với giao thức để tạo key mã hóa và các key phụ trợ nếu cần.
4. Mã hóa payload bằng AEAD như AES-GCM hoặc ChaCha20-Poly1305, với nonce duy nhất theo yêu cầu thuật toán.
5. Gửi encapsulation, nonce, ciphertext, authentication tag và metadata giao thức.
6. Bên nhận decapsulate, dẫn xuất cùng key, rồi xác thực và giải mã AEAD.

Nếu cần xác thực người gửi, phải bổ sung chữ ký số, chứng thư, PSK hoặc một giao thức đã được thiết kế để cung cấp xác thực. KEM công khai không ngăn kẻ tấn công thay public key trong quá trình phân phối nếu ứng dụng không xác thực public key.

Trong hệ thống thực tế, ưu tiên một giao thức đã được chuẩn hóa và triển khai đã được kiểm thử thay vì tự thiết kế format KEM + KDF + AEAD. Ví dụ, HPKE (Hybrid Public Key Encryption, RFC 9180) định nghĩa cách kết hợp KEM, KDF và AEAD cùng các mode và quy tắc context.

## 10. Bảo vệ private key và dữ liệu encapsulation

- Private key phải được giữ bí mật, giới hạn quyền truy cập và bảo vệ khi lưu trữ. Với yêu cầu bảo mật cao, cân nhắc keystore hoặc HSM hỗ trợ loại khóa/thuật toán cần dùng.
- Public key có thể công bố, nhưng cần xác thực nguồn gốc và liên kết với danh tính người nhận.
- Encapsulation thường không phải bí mật, nhưng cần gắn đúng với thông điệp, phiên, key identifier và metadata giao thức để tránh nhầm lẫn hoặc phát lại ngoài ngữ cảnh.
- Không ghi private key, shared secret hoặc key bytes vào log, exception message hay telemetry.
- Không dùng lại shared secret hoặc encapsulation theo cách trái với đặc tả KEM/protocol; thông thường bên gửi tạo encapsulation mới cho mỗi phiên/trao đổi theo yêu cầu giao thức.
- Khi xoay vòng khóa, phải xác định key identifier và chính sách chấp nhận encapsulation cũ trong khoảng chuyển tiếp.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao sai | Cách khắc phục |
|---|---|---|
| Tạo Decapsulator bằng public key | Decapsulation cần private key tương ứng | Dùng `newDecapsulator(privateKey)` |
| Truyền ciphertext ứng dụng vào `decapsulate` | API cần encapsulation bytes, không phải payload đã mã hóa | Tách rõ trường encapsulation và ciphertext trong giao thức |
| Gửi shared secret qua mạng | Làm mất mục tiêu thiết lập bí mật của KEM | Chỉ gửi encapsulation; mỗi phía tự tạo shared secret |
| Dùng private key không khớp | Hai phía không thể tạo cùng shared secret | Liên kết key identifier với đúng key pair |
| Giả định mọi provider đều hỗ trợ `DHKEM` | Thuật toán KEM là dịch vụ do provider cung cấp | Kiểm tra provider và hỗ trợ thuật toán trên JDK mục tiêu |
| In `SecretKey.getEncoded()` ra log | Làm lộ key material | Chỉ dùng trong kiểm tra demo; production không xuất hoặc ghi secret |
| Coi KEM là thuật toán mã hóa payload | KEM chỉ tạo shared secret | Dùng KDF và AEAD theo giao thức đã thiết kế |
| Coi KEM xác thực người gửi | Public-key encapsulation tự nó không xác thực danh tính bên gửi | Xác thực public key và bổ sung cơ chế authentication |
| Dùng secret khi decapsulation lỗi | Tạo đường xử lý không an toàn | Dừng xử lý, không fallback sang key mặc định |

## 12. Checklist triển khai Decapsulator

- Dùng Java 21 với KEM API chính thức trong `javax.crypto`.
- Chọn tên KEM mà provider/runtime thực sự hỗ trợ.
- Tạo decapsulator bằng private key tương ứng với public key bên gửi đã dùng.
- Nhận đúng encapsulation bytes, không nhầm với ciphertext payload.
- Dùng `decapsulate(...)` và xử lý `DecapsulateException`.
- Hai phía phải thống nhất KEM, tham số, đoạn shared secret và thuật toán `SecretKey` nếu dùng overload tùy chọn.
- Bảo vệ private key; xác thực public key trước khi bên gửi encapsulate.
- Không gửi hoặc log shared secret.
- Dùng KDF/AEAD hoặc giao thức chuẩn như HPKE để bảo vệ dữ liệu ứng dụng.
- Có key identifier, chính sách xoay vòng và xử lý lỗi nhất quán.

`KEM.newDecapsulator(privateKey)` tạo đối tượng dùng private key của người nhận để khôi phục shared secret từ encapsulation bytes. Phân biệt rõ private key, encapsulation, shared secret và ciphertext ứng dụng là điều cốt lõi để dùng KEM API đúng cách trong Java 21.
