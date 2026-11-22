# KEM.Encapsulated gồm secret key, encapsulation và tham số

Trong Java 21, API `javax.crypto.KEM` cung cấp cơ chế Key Encapsulation Mechanism (KEM). Ở phía gửi, `KEM.Encapsulator` tạo một shared secret và một key encapsulation message. Kết quả được đóng gói trong `KEM.Encapsulated`, gồm ba thành phần: `SecretKey key`, `byte[] encapsulation` và `byte[] params` tùy chọn.

Ba thành phần có vai trò khác nhau. `key()` là bí mật dùng chung mà bên gửi phải giữ kín. `encapsulation()` là dữ liệu encapsulation được gửi cho bên nhận để decapsulate. `params()` chứa byte tham số bổ sung nếu thuật toán cần; giá trị này có thể là `null`. Bên nhận dùng private key cùng encapsulation message và tham số tương ứng để khôi phục cùng shared secret.

## 1. KEM và vai trò của KEM.Encapsulated

KEM là cơ chế dùng public key của bên nhận để bên gửi tạo một shared secret. Bên gửi không truyền shared secret qua mạng. Thay vào đó, bên gửi gửi một key encapsulation message; bên nhận dùng private key tương ứng để decapsulate và thu được cùng shared secret.

Quy trình khái quát:

```text
Bên nhận                                      Bên gửi
   |                                             |
   |--- public key ----------------------------->|
   |                                             |
   |                                  KEM.Encapsulator
   |                                             |
   |                                  encapsulate()
   |                                             |
   |                                  KEM.Encapsulated
   |                                  + key (bí mật)
   |                                  + encapsulation
   |                                  + params (tùy chọn)
   |                                             |
   |<---------- encapsulation + params ---------|
   |                                             |
KEM.Decapsulator                                 |
   |                                             |
decapsulate(encapsulation)                       |
   |                                             |
   +------ shared secret giống bên gửi ----------+
```

`KEM.Encapsulated` là object kết quả ở phía gửi, không phải một gói tin mạng đã được serialize theo một protocol. Ứng dụng phải quyết định cách đóng gói và truyền các trường cần thiết cho bên nhận.

KEM không tự mã hóa toàn bộ dữ liệu ứng dụng. Nó tạo shared secret để hai bên có thể dùng làm đầu vào cho KDF (Key Derivation Function), sau đó dẫn xuất key phù hợp cho mã hóa đối xứng như AEAD. KEM cũng không tự xác thực danh tính người gửi; ứng dụng cần xác thực public key của bên nhận và dùng chữ ký hoặc một giao thức đã xác thực nếu cần xác minh người gửi.

## 2. Ba thành phần của KEM.Encapsulated

Java 21 định nghĩa `KEM.Encapsulated` với ba accessor:

| Accessor | Kiểu trả về | Ý nghĩa | Có gửi cho bên nhận? |
|---|---|---|---|
| `key()` | `SecretKey` | Shared secret được tạo ở phía gửi | Không. Phải giữ bí mật ở phía gửi |
| `encapsulation()` | `byte[]` | Key encapsulation message; API cũng mô tả là ciphertext của KEM | Có. Bên nhận cần dữ liệu này để decapsulate |
| `params()` | `byte[]` | Tham số bổ sung tùy chọn để tạo decapsulator tương ứng | Gửi khi thuật toán/protocol cần; có thể `null` |

Điểm cần nhớ là `params()` trả về `byte[]`, không phải `AlgorithmParameterSpec`. Đây là dạng byte đã mã hóa để truyền hoặc lưu trữ. Khi bên nhận cần tham số dạng object, ứng dụng khôi phục `AlgorithmParameterSpec` thông qua `AlgorithmParameters` và provider phù hợp.

### key(): shared secret dạng SecretKey

`key()` trả về shared secret dưới dạng `javax.crypto.SecretKey`. Đây là thành phần bí mật của kết quả encapsulation. Bên gửi giữ key này để dẫn xuất key mã hóa hoặc sử dụng theo protocol; không gửi nó cùng encapsulation message và không ghi nó vào log.

Lời gọi `encapsulate()` mặc định tương đương `encapsulate(0, secretSize(), "Generic")`. Key trả về có algorithm name là `Generic` và chứa toàn bộ byte của shared secret. Tài liệu API khuyến nghị shared secret này thường được đưa vào KDF làm input keying material.

Không giả định `SecretKey.getEncoded()` luôn trả byte array. Provider có thể giữ key ở dạng opaque, không cho xuất key material. Ứng dụng nên làm việc qua API mật mã phù hợp và không cố log, serialize hoặc chuyển shared secret thành chuỗi.

### encapsulation(): thông điệp encapsulation

`encapsulation()` trả về key encapsulation message do KEM tạo ra. Bên gửi truyền byte này cho bên nhận; bên nhận đưa nó vào `KEM.Decapsulator.decapsulate(...)` cùng private key tương ứng.

Đây không phải ciphertext chứa payload nghiệp vụ như nội dung file hoặc HTTP body. Nó là dữ liệu mà thuật toán KEM cần để bên nhận tái tạo shared secret. Kích thước phụ thuộc thuật toán và key; có thể xem trước bằng `KEM.Encapsulator.encapsulationSize()`.

### params(): tham số bổ sung tùy chọn

`params()` trả về byte array chứa thông tin bổ sung nếu quá trình tạo encapsulator dùng `AlgorithmParameterSpec` và thuật toán cần truyền một phần thông tin đó để bên nhận khởi tạo decapsulator tương ứng.

- Nếu không có tham số bổ sung, `params()` trả về `null`.
- Nếu có, bên gửi phải chuyển các byte này theo protocol cùng encapsulation message.
- Bên nhận dùng `AlgorithmParameters` có cùng tên thuật toán KEM để khôi phục `AlgorithmParameterSpec` mà provider yêu cầu.
- Không tự diễn giải hoặc sửa byte tham số theo giả định riêng; định dạng phụ thuộc thuật toán và provider.

`params()` không phải public key, private key hay shared secret. Tuy vậy, nó có thể ảnh hưởng đến cách decapsulation được thực hiện, vì vậy cần gắn đúng tham số với đúng thuật toán, recipient key và encapsulation message trong protocol.

## 3. Tạo KEM.Encapsulated ở phía gửi

Trong Java 21, `KEM` thuộc package `javax.crypto`. Ví dụ dưới đây dùng thuật toán `DHKEM` với cặp khóa X25519, theo cách sử dụng được minh họa trong API Java SE 21:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemSender {
    public static void main(String[] args) throws Exception {
        // Trong hệ thống thực tế, bên gửi nhận public key đã được xác thực
        // từ bên nhận qua một kênh hoặc cơ chế quản lý khóa đáng tin cậy.
        KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeyPair = keyPairGenerator.generateKeyPair();

        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulator encapsulator =
                kem.newEncapsulator(recipientKeyPair.getPublic());

        KEM.Encapsulated result = encapsulator.encapsulate();

        SecretKey sharedSecret = result.key();
        byte[] encapsulationMessage = result.encapsulation();
        byte[] optionalParams = result.params();

        System.out.println("Encapsulation bytes: " + encapsulationMessage.length);
        System.out.println("Params present: " + (optionalParams != null));

        // sharedSecret được giữ bí mật ở phía gửi.
        // Chỉ encapsulationMessage và params (nếu có) được chuyển cho bên nhận.
    }
}
```

Trong ví dụ độc lập, cặp khóa được tạo cùng chương trình để minh họa hai phía. Trong hệ thống thật, bên gửi phải nhận public key của bên nhận qua một cơ chế xác thực; không tự tạo một cặp khóa mới cho mỗi lần gửi rồi coi đó là public key đã được tin cậy.

`KEM.getInstance("DHKEM")` yêu cầu một security provider có hỗ trợ thuật toán đó. Việc API `KEM` có sẵn từ Java 21 không có nghĩa mọi provider đều hỗ trợ cùng danh sách thuật toán, loại key hoặc tham số. Nếu không provider nào hỗ trợ, lời gọi `getInstance` ném `NoSuchAlgorithmException`.

## 4. Bên nhận khôi phục shared secret

Bên nhận dùng private key khớp với public key đã dùng khi encapsulate. Với trường hợp không cần tham số bổ sung, có thể tạo decapsulator trực tiếp:

```java
KEM kem = KEM.getInstance("DHKEM");
KEM.Decapsulator decapsulator = kem.newDecapsulator(recipientPrivateKey);

SecretKey receiverSecret = decapsulator.decapsulate(encapsulationMessage);
```

`receiverSecret` là shared secret tương ứng với `result.key()` ở phía gửi. Bên nhận không cần và không được nhận secret key từ bên gửi; nó tự khôi phục key bằng private key và encapsulation message.

Nếu protocol truyền `params()` khác null, bên nhận phải khôi phục tham số đúng theo thuật toán/provider rồi dùng overload `newDecapsulator(privateKey, spec)`. Ví dụ về trình tự xử lý:

1. Đọc KEM algorithm identifier và byte `params` từ message đã xác thực.
2. Tạo `AlgorithmParameters` với cùng tên thuật toán KEM.
3. Gọi `init(paramsBytes)` để nạp byte tham số.
4. Lấy `AlgorithmParameterSpec` có đúng lớp mà provider/thuật toán yêu cầu.
5. Gọi `kem.newDecapsulator(privateKey, spec)` rồi `decapsulate(encapsulationBytes)`.

Lớp `AlgorithmParameterSpec` cụ thể phụ thuộc thuật toán và provider. Không có một lớp spec chung áp dụng cho mọi KEM, nên protocol cần xác định thuật toán và cách giải mã tham số tương ứng. Nếu `params()` là `null` và thuật toán không yêu cầu spec, dùng `newDecapsulator(privateKey)`.

## 5. Khi nào params khác null?

`KEM.newEncapsulator(publicKey, spec, secureRandom)` cho phép cung cấp một `AlgorithmParameterSpec` tùy chọn. Một thuật toán có thể dùng spec để chỉ định cách dẫn xuất shared secret, ví dụ khi cùng một key có thể được sử dụng với những lựa chọn tham số khác nhau.

Nếu một phần thông tin trong spec cần được gửi để bên nhận tạo decapsulator tương ứng, provider đưa thông tin đó vào trường `params` của `KEM.Encapsulated`. Provider cần cung cấp `AlgorithmParameters` có cùng tên thuật toán KEM để bên nhận nạp byte và khôi phục spec.

Ví dụ về API phía gửi:

```java
KEM kem = KEM.getInstance("DHKEM");

// ProviderSpecificParameterSpec là placeholder cho lớp spec
// do thuật toán/provider cụ thể định nghĩa; không phải lớp Java chung.
AlgorithmParameterSpec spec = obtainProviderSpecificSpec();

KEM.Encapsulator encapsulator = kem.newEncapsulator(
        recipientPublicKey,
        spec,
        new SecureRandom()
);

KEM.Encapsulated result = encapsulator.encapsulate();
byte[] paramsBytes = result.params();
```

Đoạn `obtainProviderSpecificSpec()` chỉ biểu diễn nơi ứng dụng tạo spec theo tài liệu của provider; nó không phải method có sẵn trong JDK. Không nên tự tạo một lớp tham số tùy ý rồi kỳ vọng mọi provider hiểu được.

## 6. Byte array được bảo vệ bằng defensive copy

Constructor của `KEM.Encapsulated` nhận `SecretKey`, `byte[] encapsulation` và `byte[] params`. Hai mảng byte được sao chép khi object được tạo để thay đổi mảng ban đầu không làm thay đổi dữ liệu bên trong object.

Hai accessor `encapsulation()` và `params()` cũng trả về bản sao mới của mảng byte. Vì vậy, sửa mảng nhận được không làm thay đổi nội dung lưu trong `KEM.Encapsulated`:

```java
byte[] firstCopy = result.encapsulation();
firstCopy[0] ^= 0x01;

byte[] secondCopy = result.encapsulation();
// secondCopy vẫn giữ dữ liệu encapsulation ban đầu.
```

Quy tắc defensive copy giúp tránh việc một thành phần vô tình sửa dữ liệu mà thành phần khác đang sử dụng. Tuy nhiên, điều đó không có nghĩa có thể bỏ qua kiểm tra message hoặc chia sẻ byte array tùy tiện giữa các thread. Ứng dụng vẫn nên giữ quyền sở hữu dữ liệu và xác thực message ở ranh giới protocol.

`key()` trả về `SecretKey`; không nên suy diễn rằng object key có thể được clone hoặc serialize giống hai mảng byte. Giữ key trong phạm vi cần dùng và tránh tạo thêm bản sao key material.

## 7. Đóng gói message để truyền qua mạng

`KEM.Encapsulated` không tự định nghĩa định dạng message mạng. Một protocol cần gửi tối thiểu thuật toán KEM, thông tin nhận diện public key của recipient, encapsulation bytes và params nếu có. Thường cũng cần version, context hoặc metadata để hai bên thống nhất cách dẫn xuất và sử dụng key.

Ví dụ mô hình message ở cấp ứng dụng:

```java
record KemMessage(
        int version,
        String algorithm,
        String recipientKeyId,
        byte[] encapsulation,
        byte[] params
) { }
```

Đây chỉ là cấu trúc minh họa. Khi triển khai, cần chọn serialization có định dạng rõ ràng, giới hạn kích thước byte array, kiểm tra version và thuật toán được cho phép, đồng thời xác thực tính toàn vẹn và nguồn gốc của metadata theo protocol. Không đưa `SecretKey` vào `KemMessage`.

Nếu dùng message làm đầu vào cho AEAD, các trường như version, algorithm identifier, recipient key ID và context có thể cần được ràng buộc làm associated data hoặc transcript theo thiết kế giao thức. Không tự thiết kế cách kết hợp KEM, KDF và AEAD nếu hệ thống cần một chuẩn đã được phân tích; ưu tiên protocol chuẩn và thư viện được đánh giá.

## 8. Phân biệt dữ liệu bí mật và dữ liệu được truyền

| Thành phần | Mức độ nhạy cảm | Xử lý |
|---|---|---|
| `key()` | Bí mật | Giữ ở hai endpoint sau khi tạo/khôi phục; không gửi, log hoặc lưu dạng rõ |
| `encapsulation()` | Không phải shared secret; cần truyền cho bên nhận | Gửi đúng byte do KEM tạo; không sửa hoặc cắt bỏ |
| `params()` | Tham số tùy chọn, không phải secret key | Gửi nếu thuật toán yêu cầu; giữ đúng byte và gắn với đúng message |
| Recipient public key | Công khai nhưng cần xác thực tính toàn vẹn và danh tính | Phân phối qua certificate, pinning hoặc cơ chế tin cậy phù hợp |
| Recipient private key | Bí mật | Bảo vệ bằng keystore/HSM hoặc cơ chế quản lý khóa phù hợp |

Không gọi `toString()` của object hoặc in `key().getEncoded()` ra log để debug. Nếu cần kiểm tra hoạt động, log algorithm identifier, provider name, độ dài encapsulation và trạng thái có/không có params; tránh log secret hoặc raw key material.

## 9. Kích thước secret và cách chọn key algorithm

`KEM.Encapsulator.secretSize()` trả kích thước shared secret theo byte. `encapsulationSize()` trả kích thước key encapsulation message. Hai giá trị này có thể dùng để chuẩn bị buffer hoặc giới hạn kích thước protocol trước khi thực hiện encapsulation.

Overload `encapsulate(from, to, algorithm)` cho phép chọn một phần byte của shared secret và tên thuật toán cho `SecretKey` trả về. Ví dụ API mô tả `encapsulate(0, 16, "AES")` dùng 16 byte đầu làm AES-128 key. Tuy nhiên, implementation có thể không hỗ trợ mọi tổ hợp `from`, `to` và `algorithm`; có thể ném `UnsupportedOperationException`.

Không chọn một đoạn byte tùy ý chỉ để khớp độ dài cipher. Với thiết kế mới, thường nên dùng toàn bộ shared secret làm input keying material cho KDF, rồi dẫn xuất key theo context, mục đích, chiều truyền và thuật toán sử dụng. KDF giúp tách biệt key theo mục đích và ràng buộc key với thông tin protocol.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gửi `key()` cho bên nhận | Làm lộ shared secret, phá vỡ mục tiêu của KEM | Chỉ gửi encapsulation và params cần thiết |
| Nghĩ `encapsulation()` là ciphertext của payload ứng dụng | Dùng sai dữ liệu KEM và bỏ qua bước mã hóa dữ liệu | Dùng shared secret qua KDF và AEAD để bảo vệ payload |
| Nghĩ `params()` trả `AlgorithmParameterSpec` | Sai kiểu và không thể truyền trực tiếp cho `newDecapsulator` | Nhớ `params()` trả `byte[]`; khôi phục spec qua `AlgorithmParameters` |
| Giả định params luôn khác null | Protocol xử lý sai trường hợp không có tham số | Kiểm tra null và dùng overload decapsulator phù hợp |
| Bỏ params khi thuật toán yêu cầu | Bên nhận không thể tạo decapsulator tương thích | Truyền nguyên byte params và khôi phục đúng spec |
| Sửa mảng byte nhận từ accessor rồi dùng lại | Tạo message không còn khớp dữ liệu ban đầu | Giữ bản sao nguyên vẹn; accessor đã trả defensive copy |
| Giả định mọi provider hỗ trợ cùng KEM | `NoSuchAlgorithmException` hoặc lỗi key/spec | Kiểm tra thuật toán, provider, loại key và spec được hỗ trợ |
| Log SecretKey hoặc key bytes | Rò rỉ khóa | Chỉ log metadata không nhạy cảm |
| Coi KEM là cơ chế xác thực người gửi | Chấp nhận public key/message từ nguồn không đáng tin | Xác thực public key và dùng chữ ký/giao thức xác thực khi cần |

## 11. Quy trình sử dụng KEM.Encapsulated

1. Chọn KEM algorithm và provider được hỗ trợ trên cả hai phía.
2. Xác thực public key của bên nhận và xác định key ID tương ứng.
3. Tạo `KEM.Encapsulator`, cung cấp spec nếu thuật toán yêu cầu.
4. Gọi `encapsulate()` và lấy `key()`, `encapsulation()` cùng `params()`.
5. Giữ `key()` bí mật ở phía gửi; không đưa key vào message hoặc log.
6. Đóng gói algorithm ID, recipient key ID, encapsulation bytes và params nếu có theo protocol đã định nghĩa.
7. Bên nhận khôi phục spec từ params nếu cần, tạo `KEM.Decapsulator` bằng private key rồi gọi `decapsulate()`.
8. Hai bên dùng shared secret làm input cho KDF và dẫn xuất key theo context giao thức; dùng AEAD để mã hóa/xác thực payload.
9. Xác thực metadata và nguồn gốc public key; dùng cơ chế xác thực sender riêng nếu yêu cầu bảo đảm danh tính người gửi.
10. Không log hoặc serialize shared secret; quản lý vòng đời key và xóa tham chiếu khi không còn cần theo chính sách của ứng dụng.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 21 API — KEM.Encapsulated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html)
- [Java SE 21 API — KEM.Encapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html)
- [Java SE 21 API — KEM.Decapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html)
- [Java SE 21 API — AlgorithmParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/AlgorithmParameters.html)
- [OpenJDK JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452)
