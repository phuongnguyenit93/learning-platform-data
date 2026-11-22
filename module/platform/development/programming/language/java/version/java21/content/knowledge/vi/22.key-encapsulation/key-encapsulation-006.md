# Tạo Encapsulator từ public key và sinh encapsulation

Java 21 giới thiệu API Key Encapsulation Mechanism (KEM) qua JEP 452. API này cho phép bên gửi dùng public key của bên nhận để tạo một shared secret key và một gói dữ liệu encapsulation. Bên gửi giữ secret key vừa tạo; bên nhận dùng private key tương ứng cùng gói encapsulation để khôi phục cùng secret key.

Trong Java, `KEM.Encapsulator` đại diện cho thao tác đóng gói khóa dựa trên public key. Gọi `encapsulate()` để sinh kết quả gồm secret key, encapsulation bytes và tham số thuật toán nếu có. Bài này tập trung vào bước tạo Encapsulator và sinh encapsulation; phần decapsulation được dùng để minh họa cách bên nhận sử dụng dữ liệu được gửi.

## 1. KEM giải quyết việc gì?

KEM là cơ chế thiết lập khóa bí mật bằng mật mã khóa công khai. Bên nhận tạo một cặp khóa public/private và công bố public key. Bên gửi dùng public key đó để tạo:

- **Shared secret key:** khóa bí mật mà bên gửi có ngay sau khi encapsulation.
- **Encapsulation:** dữ liệu công khai cần gửi cho bên nhận để bên nhận có thể khôi phục cùng secret key.
- **Parameters:** tham số thuật toán đi kèm nếu KEM provider sử dụng chúng.

Bên nhận dùng private key tương ứng và encapsulation bytes để decapsulate. Hai bên thu được cùng key material mà không gửi secret key trực tiếp qua mạng.

```text
Bên nhận                              Bên gửi
---------                             --------
Tạo key pair
  public key -----------------------> Nhận public key đã xác thực
  private key (giữ bí mật)             Tạo KEM.Encapsulator
                                             |
                                             | encapsulate()
                                             v
                                      SecretKey + encapsulation
  Nhận encapsulation <--------------- Gửi encapsulation
  Tạo KEM.Decapsulator
  decapsulate(encapsulation)
          |
          v
     Cùng shared secret key
```

KEM không tự mã hóa nội dung ứng dụng. Nó thiết lập khóa; ứng dụng thường dùng khóa đó với một thuật toán mã hóa đối xứng có xác thực (AEAD) để bảo vệ dữ liệu.

## 2. Các thành phần chính trong Java 21

API nằm trong package `javax.crypto` và có các kiểu quan trọng:

| Kiểu | Vai trò |
|---|---|
| `KEM` | Lấy implementation KEM từ provider và tạo Encapsulator/Decapsulator |
| `KEM.Encapsulator` | Dùng public key để tạo shared secret key và encapsulation |
| `KEM.Encapsulated` | Kết quả gồm `key()`, `encapsulation()` và `params()` |
| `KEM.Decapsulator` | Dùng private key để khôi phục shared secret key từ encapsulation |

Các bước ở phía gửi thường là:

1. Lấy implementation bằng `KEM.getInstance(algorithm)`.
2. Tạo Encapsulator bằng `kem.newEncapsulator(recipientPublicKey)`.
3. Gọi `encapsulator.encapsulate()` để sinh kết quả.
4. Giữ `result.key()` ở phía gửi và chuyển `result.encapsulation()` đến bên nhận.

## 3. Tạo cặp khóa của bên nhận

Ví dụ dưới đây dùng X25519 làm thuật toán khóa công khai của bên nhận. JDK 21 cung cấp KeyPairGenerator cho X25519 và provider SunJCE hỗ trợ KEM `DHKEM` theo RFC 9180.

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

static KeyPair createRecipientKeyPair() throws Exception {
    KeyPairGenerator keyPairGenerator =
            KeyPairGenerator.getInstance("X25519");
    return keyPairGenerator.generateKeyPair();
}
```

Trong hệ thống thật, bên nhận tạo key pair một lần theo vòng đời khóa phù hợp. Private key phải được bảo vệ trong keystore, HSM hoặc cơ chế quản lý khóa phù hợp; public key được phân phối qua một kênh có thể xác thực.

Không nhận public key từ một nguồn không đáng tin rồi lập tức encapsulate. Nếu kẻ tấn công thay public key bằng khóa của họ, bên gửi có thể thiết lập secret với kẻ tấn công thay vì bên nhận dự kiến.

## 4. Lấy implementation KEM

Dùng `KEM.getInstance("DHKEM")` để yêu cầu provider cung cấp implementation DHKEM:

```java
import javax.crypto.KEM;

KEM kem = KEM.getInstance("DHKEM");
```

`getInstance()` dùng cơ chế provider của Java Cryptography Architecture (JCA). Nếu runtime không có provider hỗ trợ tên thuật toán, lời gọi ném `NoSuchAlgorithmException`. Nếu public key không tương thích với KEM hoặc tham số đã chọn, việc tạo Encapsulator có thể thất bại với lỗi khóa hoặc tham số.

Với JDK 21 tiêu chuẩn, SunJCE cung cấp `DHKEM` theo RFC 9180 cho các nhóm được provider hỗ trợ, gồm X25519, X448 và các nhóm elliptic-curve tương ứng. Khả năng thực tế vẫn phụ thuộc provider và cấu hình runtime; khi dùng provider bên thứ ba, kiểm tra tài liệu của provider đó.

## 5. Tạo Encapsulator từ public key

`KEM.newEncapsulator(PublicKey)` tạo một `KEM.Encapsulator` gắn với public key của bên nhận:

```java
import java.security.PublicKey;
import javax.crypto.KEM;

static KEM.Encapsulator createEncapsulator(
        KEM kem, PublicKey recipientPublicKey) throws Exception {
    return kem.newEncapsulator(recipientPublicKey);
}
```

Public key quyết định người nhận có thể decapsulate được kết quả hay không. Bên gửi không cần và không được yêu cầu private key của bên nhận.

Có thể cung cấp `SecureRandom` tường minh nếu ứng dụng cần kiểm soát nguồn ngẫu nhiên của provider:

```java
import java.security.PublicKey;
import java.security.SecureRandom;
import javax.crypto.KEM;

KEM.Encapsulator encapsulator = kem.newEncapsulator(
        recipientPublicKey, new SecureRandom());
```

Thông thường, overload không nhận `SecureRandom` là đủ để provider sử dụng nguồn ngẫu nhiên mặc định phù hợp. Chỉ truyền nguồn ngẫu nhiên riêng khi có yêu cầu rõ ràng và đã hiểu cách provider sử dụng nó.

## 6. Sinh encapsulation bằng encapsulate()

Gọi `encapsulate()` để tạo shared secret key và encapsulation message:

```java
import javax.crypto.KEM;
import javax.crypto.SecretKey;

KEM.Encapsulated result = encapsulator.encapsulate();

SecretKey senderKey = result.key();
byte[] encapsulation = result.encapsulation();
var parameters = result.params();
```

Ba thành phần của kết quả có ý nghĩa khác nhau:

- `key()` trả về `SecretKey` chứa shared secret ở phía gửi. Đây là dữ liệu bí mật và phải được bảo vệ.
- `encapsulation()` trả về byte array có thể gửi cho bên nhận. Bản thân encapsulation không phải shared secret key.
- `params()` trả về tham số thuật toán được dùng trong lần encapsulation; có thể là `null` nếu thuật toán không cần tham số bổ sung.

Encapsulation bytes phải được truyền nguyên vẹn đến bên nhận. Nếu lưu hoặc truyền qua JSON, cần mã hóa nhị phân sang định dạng như Base64 và giải mã chính xác trước khi decapsulate.

Nếu ứng dụng cần một `SecretKey` có thuật toán và độ dài cụ thể, `Encapsulator` có overload `encapsulate(int from, int to, String algorithm)`. Hai chỉ số xác định đoạn byte của shared secret được dùng để tạo key; `to` là cận không bao gồm. Bên nhận phải gọi overload `decapsulate(encapsulation, from, to, algorithm)` với cùng đoạn và cùng tên thuật toán.

```java
// Với DHKEM/X25519, secretSize() cho biết số byte shared secret.
int secretSize = encapsulator.secretSize();

// Chọn 16 byte để tạo khóa AES-128.
if (secretSize < 16) {
    throw new IllegalStateException("KEM secret is too short");
}
KEM.Encapsulated result = encapsulator.encapsulate(0, 16, "AES");
SecretKey aesKey = result.key();
byte[] encapsulation = result.encapsulation();
```

Ở phía nhận, dùng đúng `0`, `16` và `AES` khi decapsulate. Không tự cắt hoặc băm `SecretKey.getEncoded()` để tạo khóa; hãy dùng overload của KEM hoặc một KDF được chuẩn hóa cho mục tiêu dẫn xuất khóa.

```java
SecretKey receiverAesKey = decapsulator.decapsulate(
        encapsulation, 0, 16, "AES");
```

## 7. Ví dụ hoàn chỉnh ở phía gửi

Ví dụ tạo key pair X25519 cho bên nhận, tạo Encapsulator từ public key và sinh encapsulation:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemSenderDemo {
    public static void main(String[] args) throws Exception {
        // Mô phỏng public/private key đã được tạo ở phía nhận.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        // Lấy KEM implementation.
        KEM kem = KEM.getInstance("DHKEM");

        // Tạo Encapsulator từ public key của bên nhận.
        KEM.Encapsulator encapsulator =
                kem.newEncapsulator(recipientKeys.getPublic());

        // Sinh shared secret key và encapsulation bytes.
        KEM.Encapsulated result = encapsulator.encapsulate();
        SecretKey senderKey = result.key();
        byte[] encapsulation = result.encapsulation();

        System.out.println("KEM: " + kem.getAlgorithm());
        System.out.println("Encapsulation bytes: " + encapsulation.length);
        System.out.println("Secret key algorithm: " + senderKey.getAlgorithm());

        // Gửi encapsulation đến bên nhận qua giao thức ứng dụng.
        // senderKey được giữ bí mật ở phía gửi.
    }
}
```

Ví dụ tạo key pair tại cùng chương trình chỉ nhằm minh họa luồng dữ liệu. Trong hệ thống thực tế, bên gửi nhận public key đã được xác thực từ bên nhận; private key ở phía nhận không được gửi cho bên gửi.

## 8. Bên nhận sử dụng encapsulation như thế nào?

Bên nhận tạo `KEM.Decapsulator` từ private key tương ứng, sau đó gọi `decapsulate()` với encapsulation bytes nhận được:

```java
import java.security.PrivateKey;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

static SecretKey recoverSecret(
        PrivateKey recipientPrivateKey, byte[] encapsulation)
        throws Exception {
    KEM kem = KEM.getInstance("DHKEM");
    KEM.Decapsulator decapsulator =
            kem.newDecapsulator(recipientPrivateKey);
    return decapsulator.decapsulate(encapsulation);
}
```

Bên gửi và bên nhận sẽ có hai object `SecretKey` riêng, nhưng key material được tạo ra tương ứng với cùng một shared secret. Không so sánh object bằng `==`; đó là hai object khác nhau trong hai phía.

Để kiểm thử trong môi trường demo, có thể so sánh encoded key material nếu provider cho phép export. Không log, in ra console hoặc lưu encoded secret key trong ứng dụng thật.

## 9. Kiểm tra hai phía trong một ví dụ

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemRoundTripDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = generator.generateKeyPair();

        KEM senderKem = KEM.getInstance("DHKEM");
        KEM.Encapsulator encapsulator =
                senderKem.newEncapsulator(recipientKeys.getPublic());
        KEM.Encapsulated encapsulated = encapsulator.encapsulate();

        SecretKey senderKey = encapsulated.key();
        byte[] message = encapsulated.encapsulation();

        KEM receiverKem = KEM.getInstance("DHKEM");
        KEM.Decapsulator decapsulator =
                receiverKem.newDecapsulator(recipientKeys.getPrivate());
        SecretKey receiverKey = decapsulator.decapsulate(message);

        // Chỉ dùng phép so sánh encoded key trong ví dụ kiểm thử.
        boolean same = MessageDigest.isEqual(
                senderKey.getEncoded(), receiverKey.getEncoded());
        System.out.println("Same shared secret: " + same);
    }
}
```

`MessageDigest.isEqual()` so sánh hai byte array theo cách giảm rủi ro timing leak so với tự viết vòng lặp dừng ở byte khác nhau. Trong ứng dụng production, ưu tiên giữ key ở dạng `SecretKey` và dùng trực tiếp với API mật mã; không cần export key chỉ để so sánh.

## 10. Encapsulator và dữ liệu được truyền đi

Bên gửi cần phân biệt rõ dữ liệu nào được giữ bí mật và dữ liệu nào được gửi:

| Dữ liệu | Có thể gửi qua kênh công khai? | Xử lý |
|---|---|---|
| Recipient public key | Có, nhưng phải xác thực nguồn và tính toàn vẹn | Phân phối qua chứng thư, cấu hình tin cậy hoặc cơ chế xác thực khóa |
| Encapsulation bytes | Có | Gửi cho đúng bên giữ private key tương ứng |
| `SecretKey` từ `result.key()` | Không | Giữ trong bộ nhớ an toàn và dùng cho mã hóa/giải mã đối xứng |
| Recipient private key | Không | Chỉ lưu ở phía nhận trong kho khóa được bảo vệ |
| `params()` | Tùy thuật toán và giao thức | Truyền cùng metadata cần thiết nếu decapsulator yêu cầu |

Không gửi secret key qua mạng cùng encapsulation. Nếu làm vậy, mục tiêu của KEM bị phá vỡ.

## 11. Lựa chọn thuật toán và tham số

`KEM.getInstance("DHKEM")` chọn thuật toán KEM do provider cung cấp. Public key và tham số phải tương thích với implementation đó.

- Với ví dụ Java 21, `X25519` là lựa chọn phổ biến để minh họa DHKEM.
- Một số provider hỗ trợ các nhóm khác như X448 hoặc NIST elliptic curves; danh sách cụ thể phụ thuộc provider.
- Không tự chuyển public key của thuật toán này sang một KEM khác nếu provider không hỗ trợ cặp thuật toán đó.
- Nếu dùng overload `newEncapsulator(publicKey, params)`, tham số phải đúng loại và phù hợp với public key/KEM implementation.
- Ghi nhận tên KEM, nhóm khóa và các tham số giao thức để bên nhận chọn cách decapsulate tương ứng.

Đừng hard-code một thuật toán chỉ vì nó có trong một máy phát triển. Hãy xác minh thuật toán và provider trên runtime triển khai, đặc biệt khi ứng dụng chạy trong môi trường FIPS hoặc dùng provider mật mã được quản lý riêng.

## 12. Lưu ý bảo mật khi tạo Encapsulator

1. **Xác thực public key:** KEM không tự xác minh public key thuộc về đúng người nhận. Dùng chứng thư, pinning hoặc cơ chế xác thực phù hợp.
2. **Giữ private key an toàn:** private key chỉ được dùng ở phía decapsulate và phải được bảo vệ khỏi truy cập trái phép.
3. **Không tiết lộ shared secret:** không ghi `SecretKey.getEncoded()` vào log, exception hoặc telemetry.
4. **Không nhầm encapsulation với ciphertext:** encapsulation không chứa trực tiếp dữ liệu ứng dụng đã mã hóa.
5. **Dùng AEAD sau KEM:** dùng shared secret theo thiết kế giao thức để tạo hoặc sử dụng khóa đối xứng cho AES-GCM hoặc ChaCha20-Poly1305.
6. **Xác thực giao thức:** KEM đơn lẻ không cung cấp xác thực danh tính người gửi, chống replay hoặc quản lý phiên đầy đủ.
7. **Không tự thiết kế KDF:** khi cần dẫn xuất nhiều khóa hoặc gắn context, dùng KDF và cấu trúc giao thức được chuẩn hóa, chẳng hạn HPKE (RFC 9180), thay vì tự nối byte hoặc hash tùy tiện.

KEM là một primitive mật mã. Một giao thức an toàn cần định nghĩa thêm xác thực, dẫn xuất khóa, nonce, AEAD, định dạng thông điệp, chống replay và vòng đời khóa.

## 13. Lỗi thường gặp

| Vấn đề | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NoSuchAlgorithmException` | Provider không hỗ trợ tên KEM yêu cầu | Kiểm tra provider, tên thuật toán và phiên bản runtime |
| `InvalidKeyException` | Public key không phù hợp với KEM hoặc nhóm tham số | Dùng key pair đúng loại và đúng thuật toán |
| `InvalidAlgorithmParameterException` | Tham số truyền vào không tương thích | Kiểm tra `AlgorithmParameterSpec` theo provider |
| Bên nhận không khôi phục được cùng secret | Sai private key, sai encapsulation hoặc không đồng nhất thuật toán/tham số | Xác minh cặp khóa, dữ liệu truyền và cấu hình KEM |
| Public key bị thay thế | Không xác thực nguồn public key | Xác thực public key trước khi tạo Encapsulator |

Không xử lý lỗi bằng cách thử lần lượt các private key không liên quan hoặc hạ xuống thuật toán yếu hơn. Cấu hình sai phải được phát hiện và xử lý rõ ràng.

## 14. Biên dịch với Java 21

KEM API được hoàn thiện trong Java 21 qua JEP 452. Có thể biên dịch ví dụ với release 21 mà không bật Preview:

```bash
javac --release 21 -d out src/KemRoundTripDemo.java
java -cp out KemRoundTripDemo
```

API nằm trong module `java.base` thuộc package `javax.crypto`, nên không cần thêm module bên ngoài. Runtime phải có provider hỗ trợ thuật toán KEM và nhóm khóa đang dùng.

## 15. Tài liệu tham khảo

- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
- [Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 21 API — KEM.Encapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html)
- [Java SE 21 API — KEM.Encapsulated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html)
- [Java SE 21 API — KEM.Decapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html)
- [RFC 9180 — Hybrid Public Key Encryption (HPKE)](https://www.rfc-editor.org/rfc/rfc9180)
