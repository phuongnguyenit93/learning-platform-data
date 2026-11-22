# 10.7 API KEM từ Java 21 với Encapsulator, Decapsulator và thông điệp đóng gói

Từ **Java 21**, JDK có API chuẩn **`javax.crypto.KEM`** (JEP 452) để thực hiện **Key Encapsulation Mechanism — KEM**. Đây là cầu nối giữa mật mã khóa công khai và mã hóa đối xứng: bên gửi dùng **public key của người nhận** để tạo một **shared secret** và một **thông điệp đóng gói** (encapsulation); bên nhận dùng **private key tương ứng** và thông điệp đóng gói để khôi phục **cùng shared secret**. Hai bên dùng bí mật này làm đầu vào cho cơ chế dẫn xuất khóa hoặc mã hóa dữ liệu.

Mục tiêu của bài là hiểu chính xác **`KEM`, `KEM.Encapsulator`, `KEM.Encapsulated`, `KEM.Decapsulator`**, ý nghĩa của `key()`, `encapsulation()`, `params()`, luồng byte truyền trên mạng, cách xác minh tính đúng và cách ghép KEM với **HKDF + AES-GCM** thành một envelope minh họa. Đồng thời, phải phân biệt **KEM không tự mã hóa file, không tự xác thực người gửi và không tự tạo một giao thức bảo mật hoàn chỉnh**.

Ví dụ chính dùng **DHKEM + X25519**, tương thích với API có từ Java 21 khi provider JDK hỗ trợ cấu hình này. Các API và cấu hình mật mã khả dụng còn phụ thuộc phiên bản JDK/provider; không mặc định rằng mọi thuật toán KEM, đặc biệt các họ hậu lượng tử, đều đã tích hợp trong **JDK 21**.

## 1. KEM giải quyết bài toán gì?

Giả sử Bob muốn nhận dữ liệu bí mật từ Alice. Bob tạo hoặc sở hữu cặp khóa:

- **`pkR`**: public key có thể phân phối cho người gửi sau khi xác minh nguồn gốc;
- **`skR`**: private key Bob giữ bí mật.

Alice chưa có một khóa AES chia sẻ trước với Bob. Nếu phải truyền một khóa AES dạng plaintext, kẻ nghe lén sẽ đọc được khóa. KEM cho phép Alice tạo bí mật chung mà không cần gửi bí mật đó qua mạng.

```text
                   BOB (người nhận)
               KeyPair(pkR, skR)
                     |
           pkR đã được xác thực
                     |
                   ALICE (người gửi)
          Encapsulate(pkR) tạo:
             sharedSecret_A
             encapsulationBytes
                     |
      gửi encapsulationBytes (không gửi sharedSecret_A)
                     |
                   BOB
    Decapsulate(skR, encapsulationBytes)
                     |
             sharedSecret_B

    sharedSecret_A == sharedSecret_B
```

KEM gồm ba ý niệm nền tảng:

1. **Key generation (`KeyGen`):** tạo cặp khóa công khai/riêng phù hợp thuật toán KEM. Trong ví dụ `DHKEM` với X25519, dùng `KeyPairGenerator.getInstance("X25519")`.
2. **Encapsulation (`Encap`):** nhận public key, trả về **bí mật chia sẻ và thông điệp đóng gói**. Bí mật phải giữ riêng; thông điệp đóng gói gửi được.
3. **Decapsulation (`Decap`):** nhận private key và thông điệp đóng gói, trả về bí mật tương ứng hoặc lỗi theo thuật toán/provider.

**Điểm mấu chốt:** `encapsulationBytes` là dữ liệu để người nhận **khôi phục cùng bí mật**, chứ **không phải** file đã mã hóa và cũng không phải shared secret dưới dạng Base64. Một người nhìn thấy encapsulation nhưng không có private key đúng không nên có khả năng suy ra shared secret trong mô hình bảo mật của KEM.

### 1.1. Vì sao gọi là “key encapsulation”, không gọi đơn thuần là “RSA encrypt”?

Với RSA-OAEP kiểu key transport truyền thống, bên gửi thường **tạo sẵn một khóa ngẫu nhiên nhỏ** rồi mã hóa khóa đó bằng RSA. Với nhiều KEM (ví dụ DHKEM), thao tác encapsulation **đồng thời tạo** shared secret và encapsulation, chứ không phải một hàm tổng quát nhận byte khóa tùy ý rồi mã hóa byte ấy. API Java thể hiện đúng khác biệt này: `Encapsulator.encapsulate()` **không nhận message plaintext**.

Các loại KEM khác nhau có thể dựa vào DH/ECDH, cấu trúc lattice hoặc primitive khác; Java `KEM` là **giao diện trừu tượng** để làm việc qua provider. Chọn thuật toán và public/private key phải khớp nhau; tên `KEM` không phải bảo đảm mọi khóa bất đối xứng đều tương thích với mọi KEM.

### 1.2. KEM và key agreement/AEAD không giống nhau

| Thành phần | Đầu vào/đầu ra điển hình | Mục đích |
| --- | --- | --- |
| `KeyPairGenerator` | Algorithm → public/private key pair | Tạo khóa người nhận |
| `KEM` | Algorithm name + provider | Chọn primitive KEM |
| `Encapsulator.encapsulate()` | Public key đã cấu hình → `SecretKey` + encapsulation bytes | Tạo bí mật chung từ phía người gửi |
| `Decapsulator.decapsulate(bytes)` | Private key đã cấu hình + encapsulation → `SecretKey` | Khôi phục bí mật chung bên nhận |
| KDF/HKDF | Shared secret + context → key(s) phục vụ ứng dụng | Tách miền sử dụng, tạo khóa/nonce phù hợp |
| AEAD (AES-GCM, v.v.) | Key + nonce + plaintext + AAD → ciphertext + tag | Mã hóa dữ liệu và xác thực ciphertext/metadata |
| Chữ ký số hoặc giao thức authenticated | Khóa định danh và thông điệp | Xác thực nguồn gửi nếu nghiệp vụ yêu cầu |

Không dùng `KEM.encapsulate()` thay `Cipher.doFinal(file)`. KEM **chỉ xử lý phần thiết lập bí mật chung**; file MB/GB vẫn nên đi qua cơ chế mã hóa đối xứng hoặc authenticated streaming encryption đã được thiết kế phù hợp.

## 2. API Java 21: bốn kiểu dữ liệu quan trọng

JEP 452 bổ sung các lớp trong module `java.base`, package **`javax.crypto`**:

- **`KEM`:** factory/controller cho thuật toán KEM, ví dụ `KEM.getInstance("DHKEM")`; có các phương thức tạo encapsulator hoặc decapsulator.
- **`KEM.Encapsulator`:** đối tượng phía gửi được tạo từ **public key người nhận**; gọi `encapsulate()` để sinh một kết quả mới.
- **`KEM.Encapsulated`:** object chứa **`SecretKey key()`**, **`byte[] encapsulation()`**, **`byte[] params()`** (tham số tùy chọn, có thể `null`).
- **`KEM.Decapsulator`:** đối tượng phía nhận được tạo từ **private key tương ứng**; gọi `decapsulate(byte[])` để lấy shared secret.

### 2.1. Các lời gọi tối thiểu

```java
// Ví dụ trích đoạn Java 21+, chưa bao gồm key provisioning/try-catch.
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
KeyPair receiverKeys = generator.generateKeyPair();

KEM kem = KEM.getInstance("DHKEM");

// Sender: chỉ cần public key đã xác thực của receiver.
KEM.Encapsulator sender = kem.newEncapsulator(receiverKeys.getPublic());
KEM.Encapsulated result = sender.encapsulate();
SecretKey senderSecret = result.key();
byte[] messageToSend = result.encapsulation();

// Receiver: phải có private key tương ứng.
KEM.Decapsulator receiver = kem.newDecapsulator(receiverKeys.getPrivate());
SecretKey receiverSecret = receiver.decapsulate(messageToSend);
```

Đây là trích đoạn minh họa quan hệ API, không phải một file Java đầy đủ (cần `import` và xử lý lỗi). Có hai chương trình hoàn chỉnh ở các mục sau.

### 2.2. Phân biệt `KEM`, `Encapsulator`, `Encapsulated` và `encapsulation()`

Tên gần nhau nhưng vai trò rất khác:

| Tên Java | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `KEM` | Đối tượng API | Biết loại thuật toán KEM, tạo worker có khóa phù hợp |
| `KEM.Encapsulator` | Đối tượng phía gửi | Gắn với public key người nhận và provider |
| `KEM.Encapsulated` | Giá trị kết quả | Có shared secret, encapsulation byte array và optional params |
| `result.key()` | `SecretKey` | **Phải giữ bí mật**, không đưa vào network envelope |
| `result.encapsulation()` | `byte[]` | **Thông điệp có thể truyền** cho receiver; không phải secret |
| `result.params()` | `byte[]` hoặc `null` | Tham số tùy chọn để hai phía cấu hình tương thích |
| `KEM.Decapsulator` | Đối tượng phía nhận | Gắn với private key người nhận |
| `decapsulate(encapsulation)` | `SecretKey` | Kết quả secret phía receiver |

API cho phép gọi `Encapsulator.encapsulate()` nhiều lần; **mỗi lần** tạo một shared secret và thông điệp mới. Không nên tái sử dụng secret và nonce mã hóa dữ liệu như thể đây là “khóa dài hạn được định trước”. Đặc biệt, không lấy `encapsulation()` rồi truyền qua `SecretKeySpec` để sử dụng như khóa AES: đó là **dữ liệu công khai**, không phải secret.

### 2.3. Các overload quan trọng

```java
KEM.getInstance("DHKEM");
kem.newEncapsulator(recipientPublicKey);
kem.newEncapsulator(recipientPublicKey, secureRandom);
kem.newEncapsulator(recipientPublicKey, parameterSpec, secureRandom);

kem.newDecapsulator(recipientPrivateKey);
kem.newDecapsulator(recipientPrivateKey, parameterSpec);

encapsulator.encapsulate();
encapsulator.encapsulate(from, to, keyAlgorithm);

decapsulator.decapsulate(encapsulationBytes);
decapsulator.decapsulate(encapsulationBytes, from, to, keyAlgorithm);
```

Các dòng trên chỉ là chữ ký gọi minh họa; `secureRandom`/`parameterSpec`/key là biến cần tạo đúng kiểu, không phải một đoạn chương trình độc lập. Với overload `encapsulate(int from, int to, String algorithm)`, `from`/`to` là **chỉ số byte** của phần shared secret muốn nhận; `to` là **exclusive**, và `algorithm` là **tên thuật toán gán cho SecretKey trả về**. Overload tương ứng của decapsulator phải dùng phạm vi và thuật toán **phù hợp**. Provider có thể không hỗ trợ mọi tổ hợp.

**Cách nên nhớ:** `encapsulate()`/`decapsulate(bytes)` dạng không tham số phụ trả `SecretKey` với `getAlgorithm()` thường là **`"Generic"`**. Giá trị Generic thường thích hợp làm đầu vào cho **KDF**, rồi mới lấy khóa AES/HMAC theo ngữ cảnh ứng dụng. Đừng hiểu `"Generic"` nghĩa là thuật toán mã hóa dữ liệu tên Generic.

### 2.4. Kích thước dữ liệu: `secretSize()` và `encapsulationSize()`

- `Encapsulator.secretSize()` và `Decapsulator.secretSize()` trả **số byte** của shared secret chuẩn của provider/thuật toán.
- `Encapsulator.encapsulationSize()` và `Decapsulator.encapsulationSize()` trả **số byte** của thông điệp encapsulation.
- Đây là hai kích thước khác nhau về ý nghĩa, dù một số cấu hình có thể cho cùng một giá trị.
- Trong **DHKEM(X25519, HKDF-SHA256)**, encapsulation thường **32 byte** và shared secret chuẩn **32 byte**; giá trị này đến từ thuật toán/profile, không phải do file plaintext dài 32 byte.
- Dùng metadata size của decapsulator để kiểm tra input trước khi parse/chuyển vào provider; tránh cấp phát hoặc xử lý mảng không giới hạn từ mạng.

Nếu khóa nằm trong HSM/provider không cho xuất, `SecretKey.getEncoded()` **có thể trả `null`**. Các phương thức size giúp hỏi kích thước mà không phải trích raw key. Khi cần KDF từ non-exportable secret, hãy sử dụng chức năng derivation của provider/HSM phù hợp; không ép ứng dụng phải log/xuất secret.

### 2.5. Encapsulation message khác ciphertext của file

Trong tài liệu KEM, encapsulation message **cũng có thể được gọi là KEM ciphertext**. Dù vậy, nó không phải ciphertext dữ liệu mà AES-GCM trả ra:

```text
encapsulationBytes              : public KEM message, giúp receiver tạo secret
sharedSecret                    : chỉ tồn tại nội bộ phía gửi/nhận
payloadCiphertextAndTag         : dữ liệu ứng dụng đã mã hóa bằng AEAD
envelope                        : metadata + encapsulationBytes + AEAD payload
```

Vì hai loại byte có thể cùng được gọi là “ciphertext” ở các lớp giao thức khác nhau, nên trong code và schema nên đặt tên rõ ràng: **`kemEncapsulation`** và **`aeadCiphertext`**. Không gửi nhầm `key().getEncoded()` thay vì `encapsulation()`.

## 3. Luồng gửi–nhận và vị trí của ba trường `key`, `encapsulation`, `params`

Một KEM exchange chuẩn theo API Java:

```text
Sender                                                   Receiver
  |                                                          |
  | <-- authentic public key pkR / key ID / algorithm --------|
  |                                                          |
  | KEM.getInstance("DHKEM")                                |
  | enc = kem.newEncapsulator(pkR).encapsulate()             |
  |   senderSecret = enc.key()      [GIỮ BÍ MẬT]             |
  |   encBytes     = enc.encapsulation()                     |
  |   optParams    = enc.params()                            |
  |                                                          |
  | --- protocol header + encBytes (+ optParams nếu cần) --->|
  |                                                          |
  |                               kem.newDecapsulator(skR)   |
  |                               .decapsulate(encBytes)     |
  |                                  -> receiverSecret       |
  |                                                          |
  | HKDF(senderSecret, context)   HKDF(receiverSecret, context)
  |          |                                  |
  |       AEAD key ------------------------> cùng AEAD key    |
  |     mã hóa dữ liệu                   xác thực và giải mã  |
```

### 3.1. Bên gửi biết gì?

Người gửi phải có **public key đích đã được xác thực**, biết **KEM algorithm** được giao thức cho phép, biết suite/hash và tham số kèm theo nếu cần. Người gửi **không cần private key** của người nhận. Vì vậy, chỉ dùng KEM theo public key người nhận **không thể tự chứng minh danh tính người gửi**: bất kỳ ai có public key hợp lệ cũng có thể thực hiện encapsulation mới.

### 3.2. Bên nhận cần gì?

Người nhận cần **private key tương ứng** và đúng KEM/suite/parameter configuration. Đừng chọn private key dựa tùy tiện vào một `keyId` không đáng tin; server phải xác minh tenant, recipient, phiên bản khóa, trạng thái rotation và allowlist thuật toán. Khi private key bị mất, các encapsulation cũ phụ thuộc private key đó có thể không còn giải mã được theo kiến trúc lưu trữ.

### 3.3. `params()` là gì?

`KEM.Encapsulated.params()` là optional byte array chứa **tham số thuật toán** nếu provider/algorithm cần truyền thêm dữ liệu để receiver tạo cấu hình tương ứng. Nó **có thể `null`**. Với ví dụ DHKEM/X25519 mặc định của JDK, giá trị thường `null`.

Nếu thuật toán yêu cầu `AlgorithmParameterSpec`, Java có overload `newEncapsulator(publicKey, spec, random)` và `newDecapsulator(privateKey, spec)`. Khi có params, receiver phải **parse theo định dạng mà provider/giao thức định nghĩa**, kiểm tra giới hạn/độ hợp lệ và khôi phục `AlgorithmParameterSpec` tương ứng (khi provider hỗ trợ `AlgorithmParameters`). Không thể đưa `params()` tùy ý vào `decapsulate(byte[])` rồi mong nó được tự nhận; `decapsulate` chỉ nhận **encapsulation bytes**.

### 3.4. Không log `SecretKey` hoặc binary encapsulation như secret

- **Shared secret/KDF output/AEAD key:** phải giữ bí mật; không log base64, hex, byte array, debug dumper.
- **Encapsulation:** thường không cần bí mật, nhưng phải bảo vệ **integrity/context binding** ở lớp envelope và giới hạn kích thước đầu vào.
- **Metadata:** version, key ID, suite, optional params có thể không bí mật nhưng không được mặc định là **đã xác thực** chỉ vì chúng nằm cùng bản tin.

## 4. Ví dụ độc lập Java 21+: `Encapsulator` và `Decapsulator`

Ví dụ này dùng **X25519** tạo cặp khóa nhận, **DHKEM** tạo encapsulator và decapsulator, kiểm tra hai phía thu được cùng shared secret. Nó cũng kiểm tra `encapsulationSize()`, `secretSize()` và lỗi khi truyền thông điệp encapsulation bị cắt ngắn. **Không in byte secret**.

Lưu đúng tên **KemBasicDemo.java**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.crypto.DecapsulateException;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class KemBasicDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair receiverKeys = generator.generateKeyPair();

        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulator sender = kem.newEncapsulator(receiverKeys.getPublic());
        KEM.Encapsulated result = sender.encapsulate();

        byte[] encapsulation = result.encapsulation();
        SecretKey senderKey = result.key();

        KEM.Decapsulator receiver =
                kem.newDecapsulator(receiverKeys.getPrivate());
        SecretKey receiverKey = receiver.decapsulate(encapsulation);

        System.out.println("KEM algorithm: " + kem.getAlgorithm());
        System.out.println("encapsulation bytes: " + encapsulation.length);
        System.out.println("shared secret bytes: " + sender.secretSize());
        System.out.println("key algorithm: " + senderKey.getAlgorithm());
        System.out.println("same secret: "
                + MessageDigest.isEqual(
                        senderKey.getEncoded(), receiverKey.getEncoded()));
        System.out.println("optional params absent: "
                + (result.params() == null));

        boolean invalidLengthRejected = false;
        try {
            receiver.decapsulate(
                    Arrays.copyOf(encapsulation, encapsulation.length - 1));
        } catch (DecapsulateException expected) {
            invalidLengthRejected = true;
        }
        System.out.println("truncated encapsulation rejected: "
                + invalidLengthRejected);
    }
}
```

Dùng **JDK 21 trở lên** với provider hỗ trợ `DHKEM` và `X25519`:

```bash
javac -encoding UTF-8 KemBasicDemo.java
java KemBasicDemo
```

Stdout của cấu hình DHKEM/X25519 phổ biến trong JDK (đã chạy kiểm tra):

```text
KEM algorithm: DHKEM
encapsulation bytes: 32
shared secret bytes: 32
key algorithm: Generic
same secret: true
optional params absent: true
truncated encapsulation rejected: true
```

### 4.1. Phân tích từng lời gọi

**Bước 1 — tạo key pair:** `KeyPairGenerator.getInstance("X25519")` dùng thuật toán cặp khóa phù hợp với DHKEM trên X25519. Trong hệ thống thật, key pair của người nhận thường được tạo, lưu và cấp phát theo chính sách, không phải sinh mới mỗi khi nhận file cũ.

**Bước 2 — chọn KEM:** `KEM.getInstance("DHKEM")` chọn API KEM trên provider. `DHKEM` là tên thuật toán, còn profile cụ thể (ở đây X25519 + KDF phù hợp) do key/provider xác định theo hỗ trợ. Có thể phát sinh `NoSuchAlgorithmException` hoặc `InvalidKeyException` nếu thuật toán/key không được hỗ trợ; việc tồn tại lớp `KEM` không đảm bảo mọi provider đều dùng được mọi key type.

**Bước 3 — encapsulation:** `sender.encapsulate()` trả **`KEM.Encapsulated`**, gồm secret phía gửi và message `byte[]`. Trong code chỉ truyền byte message.

**Bước 4 — decapsulation:** `kem.newDecapsulator(receiverKeys.getPrivate())` tạo phía nhận; `receiver.decapsulate(encapsulation)` trả secret cùng giá trị. Demo dùng `getEncoded()` để so sánh cho mục đích học tập; production cần lưu ý khóa **không xuất được** trong HSM/provider.

**Bước 5 — kích thước:** 32 byte encapsulation và 32 byte shared secret là giá trị của profile DHKEM/X25519 trong ví dụ; **không** tự suy ra rằng mọi thuật toán KEM luôn có cùng output 32 byte.

**Bước 6 — dữ liệu thiếu:** `Arrays.copyOf(..., len - 1)` làm message thành 31 byte. `DecapsulateException` cho thấy input sai kích thước bị từ chối.

### 4.2. Một điều rất dễ hiểu nhầm

**Không phải cứ sửa một byte trong encapsulation rồi `decapsulate()` là chắc chắn ném exception.** Với một số KEM, chuỗi byte đã bị sửa nhưng vẫn đúng khuôn dạng có thể cho ra **shared secret khác** thay vì lỗi cú pháp. Vì vậy, receiver phải dùng secret đó trong **AEAD được xác thực**; lỗi tag mới chặn việc chấp nhận plaintext không đúng. Đừng xem “decapsulation trả SecretKey” là bằng chứng sender đáng tin hoặc payload hợp lệ.

## 5. Dùng shared secret: KDF, domain separation và AEAD

KEM cung cấp shared secret; ứng dụng thường cần **khóa đối xứng theo mục đích**. Nếu trực tiếp lấy toàn bộ raw secret làm AES key ở mọi giao thức, dễ phát sinh **key reuse** hoặc thiếu ràng buộc context, nhất là khi cùng một KEM outcome cấp khóa cho encryption, MAC hoặc nhiều mục đích khác nhau.

Một kiến trúc có kiểm soát:

```text
KEM encapsulate/decapsulate
        |
   shared secret (Generic)
        |
   HKDF-Extract/Expand + suite/context/version/recipient binding
        |
     +---------+----------+
     |                    |
   AEAD key           other purpose key (nếu giao thức có thiết kế)
     |
 AES-GCM(key, nonce, plaintext, AAD)
     |
 ciphertext || authentication tag
```

### 5.1. KDF có tác dụng gì ở đây?

- **Chuyển đổi/điều chỉnh vật liệu khóa** theo độ dài của thuật toán đích, ví dụ AES-128 cần 16 byte, AES-256 cần 32 byte.
- **Domain separation:** đưa protocol name, version, algorithm suite, purpose, recipient/tenant vào `info` KDF để tránh lấy một secret cho nhiều mục đích ngoài thiết kế.
- **Context binding:** hai bên đồng ý chính xác cách encode `info`. Khi context không khớp, khóa dẫn xuất không khớp và giải mã AEAD thất bại.
- **Giới hạn quyền:** key dùng cho encryption không tự nhiên được dùng làm HMAC hoặc signing key cho giao thức khác.

DHKEM của RFC 9180 **đã có nội bộ cơ chế dẫn xuất secret từ DH**, nhưng điều đó không có nghĩa đầu ra là key schedule đầy đủ cho mọi ứng dụng. Bước HKDF riêng theo context của ứng dụng vẫn hữu ích để dẫn xuất AES key và tách miền sử dụng.

Trong Java 21, có thể triển khai HKDF theo RFC 5869 bằng `Mac.getInstance("HmacSHA256")` hoặc dùng thư viện mật mã đã được kiểm định. **Không giả định `javax.crypto.KDF` là API chuẩn có sẵn trong Java 21**; bài này cố tình chỉ dùng API chắc chắn có ở Java 21.

### 5.2. Vì sao phải có AES-GCM sau KEM?

KEM chỉ tạo **khóa/secret** và encapsulation message. Nó **không** mã hóa plaintext file, không tự có nonce, không tự tạo authentication tag và không phát hiện việc ai đó thay đổi payload ciphertext. Với AES-GCM:

- `Cipher.getInstance("AES/GCM/NoPadding")` là transformation AEAD.
- `GCMParameterSpec(128, nonce)` chọn **tag 128 bit**, nonce là một `byte[]` riêng; nonce 96 bit/12 byte thường là lựa chọn đơn giản theo profile.
- `Cipher.updateAAD(...)` đưa metadata/encapsulation vào phần dữ liệu được xác thực nhưng **không mã hóa**.
- `Cipher.doFinal(plaintext)` trả ciphertext + tag trong dạng Java provider thông dụng.
- Khi giải mã, **phải để `doFinal()` kiểm tra tag**; lỗi `AEADBadTagException` nghĩa là không chấp nhận plaintext.

Nonce AES-GCM **phải không lặp dưới cùng AES key**. Ví dụ tạo shared secret/KDF key mới cho một message rồi sinh nonce ngẫu nhiên 12 byte; khi thiết kế cho nhiều message trên một key, phải có chiến lược nonce và giới hạn số lượng message theo giao thức, không chỉ dựa vào “nonce dài đúng 12 byte”.

### 5.3. Mã hóa không đồng nghĩa xác thực người gửi

Chỉ biết public key người nhận, **bất kỳ ai** cũng có thể encapsulate và mã hóa một payload mới mà receiver giải được. Do đó, dữ liệu được mã hóa bởi KEM + AEAD đúng có thể **giữ bí mật và toàn vẹn của ciphertext cho một key context**, nhưng **không tự chứng minh tác giả**. Nếu cần xác thực danh tính người gửi, dùng giao thức authenticated, chữ ký số trên envelope, mutual TLS hoặc xác thực bên gửi theo thiết kế; public key của bên ký/xác thực phải có hệ thống trust riêng.

## 6. Ví dụ độc lập Java 21+: KEM → HKDF → AES-GCM

Chương trình này minh họa **một envelope đơn giản trong bộ nhớ**. Alice encapsulate bằng public key X25519 của Bob; hai bên dẫn xuất AES-128 key thông qua một vòng **HKDF-Extract + HKDF-Expand (16 byte output)**, dùng AES-GCM để mã hóa một payload và kiểm tra:

- Hai phía giải mã đúng plaintext.
- Sửa ciphertext sẽ bị GCM từ chối.
- Sửa AAD/header sẽ bị GCM từ chối.
- Dùng sai private key phía nhận sẽ không giải mã/xác thực được payload.

**Lưu ý:** HKDF helper chỉ triển khai **1 block Expand** để lấy **16 byte AES key**; nó **không phải** một triển khai tổng quát cho mọi `L` của RFC 5869. Example giữ mọi byte trong RAM, không serialize wire format hoặc quản lý key ID thật.

Lưu **KemEnvelopeDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KEM;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class KemEnvelopeDemo {
    private static final byte[] HEADER =
            "demo:v1|DHKEM-X25519|AES-128-GCM|recipient-01"
                    .getBytes(StandardCharsets.UTF_8);

    private static byte[] hmac(byte[] key, byte[]... inputs)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        for (byte[] value : inputs) mac.update(value);
        return mac.doFinal();
    }

    // HKDF-SHA256 Extract, rồi Expand 1 block lấy 16 byte AES-128 key.
    private static SecretKeySpec deriveKey(SecretKey kemSecret)
            throws Exception {
        byte[] raw = kemSecret.getEncoded();
        if (raw == null) {
            throw new IllegalStateException(
                    "non-exportable KEM secret needs provider KDF support");
        }
        byte[] prk = hmac(new byte[32], raw); // salt zero theo HKDF
        byte[] block = hmac(prk, HEADER, new byte[]{1}); // T(1)
        SecretKeySpec key =
                new SecretKeySpec(Arrays.copyOf(block, 16), "AES");
        Arrays.fill(raw, (byte) 0);
        Arrays.fill(prk, (byte) 0);
        Arrays.fill(block, (byte) 0);
        return key;
    }

    private static Cipher newGcm(int mode, SecretKeySpec key,
                                 byte[] nonce, byte[] enc, byte[] header)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode, key, new GCMParameterSpec(128, nonce));
        cipher.updateAAD(header);
        cipher.updateAAD(enc);
        return cipher;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator keyGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair recipient = keyGenerator.generateKeyPair();
        KEM kem = KEM.getInstance("DHKEM");

        // Sender: có public key đã được xác thực của receiver.
        KEM.Encapsulated result =
                kem.newEncapsulator(recipient.getPublic()).encapsulate();
        byte[] encapsulation = result.encapsulation();
        SecretKeySpec senderAesKey = deriveKey(result.key());

        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] plain =
                "file-content-from-sender".getBytes(StandardCharsets.UTF_8);
        byte[] ciphertextAndTag =
                newGcm(Cipher.ENCRYPT_MODE, senderAesKey,
                        nonce, encapsulation, HEADER).doFinal(plain);

        // Receiver: lấy encapsulation + nonce + ciphertext và private key.
        SecretKey recoveredSecret =
                kem.newDecapsulator(recipient.getPrivate())
                   .decapsulate(encapsulation);
        SecretKeySpec recipientAesKey = deriveKey(recoveredSecret);
        byte[] recovered =
                newGcm(Cipher.DECRYPT_MODE, recipientAesKey,
                        nonce, encapsulation, HEADER)
                        .doFinal(ciphertextAndTag);

        System.out.println("encapsulation bytes: " + encapsulation.length);
        System.out.println("AES key bytes: "
                + senderAesKey.getEncoded().length);
        System.out.println("nonce bytes: " + nonce.length);
        System.out.println("GCM tag overhead bytes: "
                + (ciphertextAndTag.length - plain.length));
        System.out.println("round-trip: "
                + Arrays.equals(plain, recovered));

        byte[] edited = ciphertextAndTag.clone();
        edited[0] ^= 1;
        boolean tamperedCiphertextRejected = false;
        try {
            newGcm(Cipher.DECRYPT_MODE, recipientAesKey, nonce,
                   encapsulation, HEADER).doFinal(edited);
        } catch (AEADBadTagException expected) {
            tamperedCiphertextRejected = true;
        }
        System.out.println("changed ciphertext rejected: "
                + tamperedCiphertextRejected);

        boolean changedHeaderRejected = false;
        try {
            newGcm(Cipher.DECRYPT_MODE, recipientAesKey, nonce,
                   encapsulation, "demo:v2".getBytes(StandardCharsets.UTF_8))
                    .doFinal(ciphertextAndTag);
        } catch (AEADBadTagException expected) {
            changedHeaderRejected = true;
        }
        System.out.println("changed AAD rejected: "
                + changedHeaderRejected);

        KeyPair wrongRecipient = keyGenerator.generateKeyPair();
        SecretKey wrongSecret =
                kem.newDecapsulator(wrongRecipient.getPrivate())
                   .decapsulate(encapsulation);
        SecretKeySpec wrongAes = deriveKey(wrongSecret);
        boolean wrongPrivateKeyRejected = false;
        try {
            newGcm(Cipher.DECRYPT_MODE, wrongAes, nonce,
                   encapsulation, HEADER).doFinal(ciphertextAndTag);
        } catch (AEADBadTagException expected) {
            wrongPrivateKeyRejected = true;
        }
        System.out.println("wrong recipient key rejected: "
                + wrongPrivateKeyRejected);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 KemEnvelopeDemo.java
java KemEnvelopeDemo
```

Stdout kỳ vọng với DHKEM/X25519 và AES-GCM của provider JDK thông dụng:

```text
encapsulation bytes: 32
AES key bytes: 16
nonce bytes: 12
GCM tag overhead bytes: 16
round-trip: true
changed ciphertext rejected: true
changed AAD rejected: true
wrong recipient key rejected: true
```

### 6.1. Đọc luồng mã hóa

1. **`recipient`:** cặp khóa X25519 của Bob. Demo sinh cặp khóa trong tiến trình để dễ thử; hệ thống thực phải cấp phát public key từ nguồn đáng tin và lưu private key đúng chính sách.
2. **`KEM.Encapsulated`:** chứa shared secret mới và **32 byte encapsulation**. Chỉ encapsulation được đặt vào envelope; `result.key()` không truyền.
3. **`deriveKey`:** lấy shared secret, dùng HKDF-Extract với salt rỗng/zero theo biểu diễn HMAC, rồi một bước HKDF-Expand có `info = HEADER` và counter `0x01` để lấy **16 byte** cho AES-128. Cả sender và receiver dùng **cùng HEADER** mới tạo cùng key.
4. **`nonce`:** 12 byte ngẫu nhiên cho lần mã hóa này. Nonce không cần bí mật, nhưng phải tránh trùng dưới cùng AES key.
5. **`cipher.updateAAD(HEADER)` rồi `updateAAD(encapsulation)`:** ràng buộc **header và encapsulation** vào tag GCM. Khi receiver thay header, nonce hoặc ciphertext, hoặc dùng sai key, xác minh không thành công.
6. **`ciphertextAndTag`:** payload đã mã hóa + tag GCM; demo không tự lưu thành file. Độ dài tăng **16 byte** vì tag 128 bit; nonce và encapsulation được giữ riêng.
7. **`doFinal` khi decrypt:** chỉ khi tag đúng mới coi plaintext là hợp lệ. Không lấy một phần plaintext từ stream trước xác minh rồi dùng trong nghiệp vụ.

### 6.2. Vì sao có hai chỗ dẫn xuất?

Trong DHKEM của RFC 9180, shared secret vốn được dẫn xuất từ quá trình Diffie–Hellman theo cách của KEM. Sau đó, ứng dụng **tiếp tục dùng HKDF với application context** để thu được key phục vụ một giao thức cụ thể. Điều này giúp phân biệt “bí mật thỏa thuận” với “khóa AES dùng cho payload của phiên bản giao thức X”.

**Không được** thay helper HKDF bằng `new SecretKeySpec(encapsulation, "AES")`, vì encapsulation không bí mật. Cũng không lấy một shared secret và dùng song song làm nhiều khóa độc lập mà không có key schedule/domain separation.

### 6.3. Hạn chế quan trọng của demo

- **DHKEM + một HKDF nhỏ + AES-GCM không tự biến thành triển khai HPKE đầy đủ**. HPKE RFC 9180 định nghĩa key schedule, suite IDs, nonce management, modes và điều kiện sử dụng cụ thể; không thể gọi code mẫu là “HPKE-compatible” nếu chưa triển khai đầy đủ đúng chuẩn.
- Header demo là **hằng số do chương trình tin cậy định nghĩa**, chưa phải serializer/parser production. Nếu header có trường động, hãy dùng cấu trúc length-prefix/TLV/format canonical, không ghép chuỗi tùy ý có delimiter mơ hồ.
- Không có xác thực danh tính sender, anti-replay, key rotation, giới hạn message, streaming hoặc chính sách access. Đây là minh họa thành phần mật mã, **không phải một protocol triển khai nguyên mẫu**.
- `getEncoded()` trong `deriveKey` có thể trả `null` nếu secret không xuất được; provider/HSM có thể yêu cầu KDF nội bộ và cơ chế key handle khác.
- `Arrays.fill` chỉ xóa mảng tạm đang sở hữu ở mức best effort; nó **không bảo đảm** xóa mọi bản sao bên trong JVM/provider. Demo không in raw key nhưng application thật phải xem xét secret retention, log và crash dump.
- Phép thử private key sai với X25519 có thể tạo một secret khác thay vì ném lỗi decapsulation; **AES-GCM** mới bác bỏ ciphertext dùng key sai. Với KEM/provider khác, sai encapsulation có thể bị từ chối ngay trong decapsulation.
- AEAD tag đúng không chứng minh sender là ai, vì **ai cũng có thể dùng public key đích** để tạo một encrypted message mới.

## 7. “Thông điệp đóng gói” khi gửi trên mạng phải chứa gì?

Bản thân `encapsulation()` chỉ có byte KEM; nó không tự có version, người nhận, nonce hoặc ciphertext. Một giao thức thực cần một **envelope** mô tả tất cả byte đủ để receiver chọn đúng thuật toán/khóa và xác minh toàn bộ payload.

Ví dụ schema ý tưởng:

```text
EnvelopeV1:
  magic/version                 :  định dạng được hỗ trợ
  suiteId                       :  KEM + KDF + AEAD được allowlist
  recipientKeyId                :  ID chọn private key, scope đã kiểm tra
  kemParamsLength/kemParams     :  nếu thuật toán cần
  encapsulationLength           :  độ dài binary, giới hạn
  encapsulationBytes            :  KEM message
  nonceLength/nonce             :  nonce của AEAD
  ciphertextLength/ciphertext   :  AEAD ciphertext || tag
  associatedData                 :  metadata đã xác thực (theo quy ước)
```

**Đây chỉ là sơ đồ dữ liệu**, không phải một wire format đã tiêu chuẩn hóa và không phải code Java chạy độc lập. Một định dạng production phải quyết định byte order, length-prefix, phiên bản, kích thước tối đa, xử lý unknown fields, backward compatibility và cách canonicalize dữ liệu được AAD bảo vệ.

### 7.1. Trường nào công khai, trường nào bí mật?

| Dữ liệu | Truyền được? | Ý nghĩa |
| --- | --- | --- |
| Recipient public key | Có, nhưng phải **xác thực nguồn** | Giúp sender encapsulate đúng người nhận |
| Recipient private key | **Không** | Chỉ receiver giữ hoặc HSM sử dụng |
| `KEM.Encapsulated.key()` | **Không** | Shared secret phía sender |
| `encapsulation()` | **Có** | Bắt buộc gửi để receiver decapsulate |
| `params()` nếu được thuật toán yêu cầu | Có nếu giao thức/provider quy định | Receiver dùng để tạo cấu hình tương ứng |
| KDF-derived AES key | **Không** | Chỉ sử dụng nội bộ |
| AEAD nonce | Có | Tham số giải mã, phải duy nhất dưới cùng key |
| AES-GCM ciphertext + tag | Có | Dữ liệu đã mã hóa và authentication tag |
| Suite, version, key ID, payload ID | Thường có | Cho phép chọn đúng cấu hình; phải kiểm tra và ràng buộc integrity |

### 7.2. `keyId` không phải bằng chứng tin cậy

`recipientKeyId` trong envelope đến từ nguồn bên ngoài. Receiver có thể dùng nó để **tìm đúng khóa đã được phê duyệt**, nhưng phải kết hợp tenant/đối tượng, version, chính sách và trạng thái. Không tự động lấy khóa từ đường dẫn/tên file/URL do `keyId` do attacker cung cấp. Không cho client chọn thuật toán yếu hoặc vượt scope chỉ bằng cách sửa `suiteId`.

### 7.3. Ràng buộc metadata vào AAD và KDF context

Nếu header mô tả **recipient, protocol, suite, version, file ID, tenant** nhưng không được xác thực, attacker có thể thay đổi ý nghĩa nghiệp vụ mà ciphertext vẫn hợp lệ dưới một cách diễn giải sai. Nên canonicalize và đưa metadata liên quan tính toàn vẹn vào **AEAD AAD** theo giao thức, đồng thời đưa phần context phù hợp vào **KDF info**.

KDF info và AAD phục vụ hai mục đích bổ trợ:

- **KDF info:** tách miền khóa (domain-separated key schedule).
- **AAD:** bảo vệ integrity của byte metadata gắn với ciphertext.

Nếu header có nhiều trường động hoặc có thể chứa ký tự `|`, không sử dụng nối chuỗi “`a|b|c`” không escape/không length-prefix để làm giao thức thật; hai bộ tham số khác nhau có thể vô tình sinh cùng chuỗi. Thống nhất schema canonical với test vectors liên ngôn ngữ.

### 7.4. `params()` không phải `encapsulation()`

Nếu `result.params() == null`, không cần trường params có nội dung. Nếu thuật toán yêu cầu params, envelope phải mô tả byte params **tách riêng** và receiver khôi phục spec tương ứng trước khi tạo decapsulator.

Không gộp raw `params` vào `encapsulation` rồi hy vọng provider tự phân tích. Dùng `Decapsulator.encapsulationSize()` để kiểm tra phần KEM message thực, không coi chiều dài **toàn bộ envelope** là chiều dài encapsulation.

## 8. Lỗi KEM, kết quả sai và xử lý thất bại

### 8.1. Lỗi khi tạo KEM/Encapsulator

| Lỗi hoặc trạng thái | Nguyên nhân thường gặp | Xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | KEM `"DHKEM"` hoặc thuật toán key không có provider phù hợp | Kiểm tra JDK/provider và policy, không fallback ngầm sang primitive yếu |
| `InvalidKeyException` | Public/private key sai hoặc không phù hợp KEM | Từ chối, kiểm tra loại khóa, trust và phiên bản |
| `InvalidAlgorithmParameterException` | `AlgorithmParameterSpec` sai hoặc thiếu | Thực hiện theo đặc tả thuật toán/provider |
| `UnsupportedOperationException` | Một overload/combination chưa được provider hỗ trợ | Chọn profile được phép hoặc sửa cấu hình, không đoán |
| `DecapsulateException` | Encapsulation hỏng, sai chiều dài hoặc quá trình decapsulation thất bại | Từ chối request, ghi lỗi chung không lộ private-key state |

### 8.2. Không nhầm cú pháp hợp lệ với message hợp lệ

Một encapsulation 32 byte chỉ vượt qua kiểm tra **độ dài**, chưa chắc do người gửi đáng tin tạo. Một decapsulation không ném exception cũng **không chứng minh** payload/metadata hợp lệ. Cần:

1. Chọn KEM, key và context từ cấu hình đáng tin.
2. Kiểm tra độ dài byte và format theo allowlist, giới hạn bộ nhớ.
3. Decapsulate bằng private key có quyền.
4. Dẫn xuất AEAD key đúng context.
5. Xác minh ciphertext/tag/AAD.
6. Sau xác minh còn kiểm tra quyền nghiệp vụ, chống replay, hạn dùng và tính hợp lệ của dữ liệu.

Đặc biệt tránh trả lỗi với thông tin quá chi tiết làm phân biệt các trường hợp private key, encapsulation, tag hoặc policy. Kiểu phản hồi chung như “Không thể xử lý thông điệp bảo mật” thường tốt hơn việc tiết lộ rằng một bí mật cụ thể đã “gần đúng”.

### 8.3. Dữ liệu bị sửa và replay

**Tamper:** sửa ciphertext/AAD/tag phải bị AEAD từ chối. Sửa encapsulation có thể dẫn đến lỗi decapsulation **hoặc** shared secret khác, khiến AEAD tag sai. Không được coi thành công của `decapsulate()` là đủ.

**Replay:** một envelope đúng, được gửi lại nguyên vẹn, vẫn có thể giải mã thành công. Nếu nghiệp vụ yêu cầu chống phát lại (thanh toán, tác vụ thay đổi trạng thái), cần timestamp, nonce/sequence, idempotency key, replay cache hoặc protocol state có kiểm tra nguyên tử. AEAD và KEM **không tự chống replay**.

**Truncation:** kiểm tra payload length, framing, tổng số chunk, finalization marker nếu stream; mỗi chunk có tag đúng không tự bảo đảm toàn file đã đầy đủ trừ khi giao thức ràng buộc rõ.

## 9. KEM trong Java 21 và các thuật toán khác: giới hạn hỗ trợ

`KEM.getInstance("DHKEM")` trong ví dụ là thuật toán **DHKEM** (Diffie–Hellman-based KEM). Với `X25519`, cơ chế tương ứng được mô tả trong **RFC 9180**. Các thuật toán khác có thể được provider bổ sung trong các JDK tương lai; **không suy ra** Java 21 bao gồm mọi KEM hậu lượng tử chỉ vì lớp `KEM` tồn tại.

| Khái niệm | Có thể dùng với Java 21 KEM API? | Lưu ý |
| --- | --- | --- |
| `javax.crypto.KEM`, `KEM.Encapsulator`, `KEM.Decapsulator` | **Có**, API chuẩn kể từ Java 21 | Thuộc `java.base` |
| `DHKEM` với X25519 | Có trong profile/provider JDK thông dụng | Public/private key X25519; encapsulation và secret 32 byte ở cấu hình ví dụ |
| DHKEM với curve khác | Tùy profile/provider | Không giả định cùng kích thước |
| KEM hậu lượng tử như ML-KEM | **Phụ thuộc JDK/provider/version** | Không mô tả là có sẵn trong JDK 21; cần xác minh nơi chạy |
| `javax.crypto.KDF` dạng API cấp cao | **Không phải API Java 21** | Ví dụ dùng `Mac` để minh họa HKDF |
| AES-GCM với `javax.crypto.Cipher` | Có | Phụ thuộc key/nonce/tag và policy |
| HPKE đầy đủ | Không được tạo tự động chỉ bằng `KEM.getInstance` | Phải có đúng key schedule, AEAD, mode, framing và profile chuẩn |

### 9.1. Provider selection ảnh hưởng đến điều gì?

Nếu không chỉ định provider trong `KEM.getInstance(algorithm)`, Java có thể chọn provider khác nhau lúc tạo **encapsulator** và **decapsulator** tùy key/spec. Có thể hỏi:

```java
String kemAlgorithm = kem.getAlgorithm();
String senderProviderName = encapsulator.providerName();
String receiverProviderName = decapsulator.providerName();
int kemMessageBytes = encapsulator.encapsulationSize();
int sharedBytes = decapsulator.secretSize();
```

Đây là trích đoạn để giải thích API chứ không phải chương trình hoàn chỉnh. Trước triển khai, kiểm thử **cùng key type, profile, version, params và wire-format** của cả hai phía. Không ép tên provider chỉ để “khớp” trong khi keys nằm trong HSM: provider cụ thể có thể có key handle riêng và yêu cầu sử dụng API phù hợp.

### 9.2. Provider khác không có nghĩa secret khác

KEM chuẩn và profile phải tạo **shared secret tương thích** cho đúng khóa và encapsulation. Tuy nhiên, việc hai runtime đều có class `KEM` không bảo đảm chúng hỗ trợ cùng suite. Nếu sender Java 21 và receiver hệ thống khác, hai bên phải cùng hiểu X25519 public-key encoding, DHKEM profile, encapsulation bytes, thuật toán KDF, `info` và AEAD wire format.

Dùng **test vector liên nền tảng**; tuyệt đối không dựa vào `toString()` hoặc Java serialization của `SecretKey`/`KEM.Encapsulated` để truyền giao thức.

## 10. Trách nhiệm bảo mật khi dùng KEM

### 10.1. Xác minh public key người nhận

KEM chỉ tốt nếu Alice nhận đúng `pkR` của Bob. Nếu attacker thay public key Bob bằng public key của attacker, Alice sẽ encapsulate một shared secret mà attacker giải được, rồi mã hóa data cho sai người. Cần certificate/PKI, authenticated directory, key pinning theo policy hoặc quy trình cấp phát khóa tin cậy.

### 10.2. Bảo vệ private key dài hạn

Private key của người nhận có thể ở Java KeyStore, HSM/KMS hoặc cơ chế quản lý khóa theo yêu cầu. Phải hạn chế quyền sử dụng, audit, backup và rotation. Nếu private key tĩnh bị lộ, nhiều envelope lịch sử còn giữ encapsulation và ciphertext có thể bị giải mã. Do đó **KEM với một private key người nhận tĩnh không mặc định mang forward secrecy**, dù sender dùng ephemeral key trong DHKEM.

### 10.3. Key rotation/version

Envelope nên có `recipientKeyId` và `suiteVersion`. Khi rotate, sender dùng public key mới đã xác thực; receiver có thể giữ key cũ ở phạm vi cho phép để xử lý dữ liệu còn phải đọc. Nếu mất private key cũ trước khi rewrap/reencrypt dữ liệu, dữ liệu cũ có thể không khôi phục được. Nếu private key bị lộ, phải thu hồi/truyền đạt tác động và chuyển khóa theo incident response, không chỉ đổi tên key ID.

### 10.4. Secret handling

- Không in `result.key().getEncoded()` hoặc derived AES key trong log.
- Không gửi shared secret dưới dạng hex/Base64 vì encoding không phải encryption.
- Không giữ key hơn thời gian cần thiết; giới hạn quyền debug, heap dump, secret exports.
- Java `Arrays.fill` dọn byte array ở mức best effort, không có bảo đảm xóa mọi bản sao trong provider/JVM.
- Nếu provider giữ secret non-exportable, ưu tiên KDF/AEAD theo provider/key handle thay vì ép xuất raw key.

### 10.5. KEM không giải quyết mọi yêu cầu hệ thống

Một hệ thống dùng KEM + AEAD vẫn phải có **authentication sender**, authorization, anti-replay, expiry, quản trị nonce, input validation, cấu hình thuật toán được allowlist, giới hạn tài nguyên, giám sát và kiểm tra nâng cấp. Không xem mã hóa thành công là cho phép thao tác nghiệp vụ.

## 11. Lỗi phổ biến khi học và sử dụng `javax.crypto.KEM`

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `encapsulation()` như AES key | Encapsulation là message có thể công khai | Dùng `key()` / `decapsulate()` tạo secret, rồi KDF |
| Gửi `result.key().getEncoded()` cho receiver | Làm lộ shared secret, vô hiệu bảo mật | Chỉ gửi encapsulation và metadata cần thiết |
| Gọi `encapsulate(fileBytes)` để mã hóa file | Java KEM không có API encrypt arbitrary message | KEM cho secret; AEAD cho payload |
| Coi KEM là thuật toán mã hóa dữ liệu khối lớn | KEM chỉ thiết lập khóa nhỏ | Hybrid KEM + KDF + AES-GCM/streaming |
| Chỉ cần `KeyPairGenerator("X25519")` là đảm bảo đúng Bob | Public key có thể bị tráo | Xác thực danh tính/nguồn public key |
| Xem `decapsulate()` thành công là xác thực sender | Ai có public key cũng có thể gửi KEM message | Thêm sender authentication nếu cần |
| Xem `params()` là ciphertext | Optional params có nghĩa cấu hình | Parse thành tham số đúng spec/giao thức |
| Nhầm `secretSize()` là bit | API trả byte | Đổi byte × 8 khi cần hiển thị bit |
| Cố định 32 byte cho mọi KEM | Kích thước phụ thuộc thuật toán/provider | Hỏi `encapsulationSize()`, `secretSize()` |
| Dùng `getEncoded()` mà không xét `null` | Key non-exportable có thể không xuất được | KDF nội bộ provider hoặc interface hỗ trợ |
| Coi Java 21 có mọi post-quantum KEM | API ≠ tập thuật toán của provider | Kiểm tra JDK, provider, policy thực tế |
| Dùng `javax.crypto.KDF` và tuyên bố code là Java 21 | API này không thuộc Java 21 | Dùng `Mac`/thư viện HKDF tương thích Java 21 |
| Sửa một byte encapsulation mà không throw nghĩa là hợp lệ | Decapsulation đôi khi tạo secret khác | Dùng AEAD để xác minh payload cuối |
| Không ràng buộc version/keyId/AAD | Context confusion và downgrade | Canonical header, allowlist suite, authenticated metadata |
| Dùng cùng AEAD key/nonce nhiều lần | AES-GCM nonce reuse có thể nguy hiểm nghiêm trọng | Quản lý cặp key/nonce duy nhất và giới hạn |
| Nghiễm nhiên gọi tự ghép KEM + AES là HPKE RFC 9180 | HPKE còn định nghĩa key schedule, modes, format | Theo đúng HPKE suite hoặc thư viện chuẩn |
| Không quản lý private key rotation | Dữ liệu cũ có thể mất hoặc dễ lộ | Key ID, version, backup/re-encrypt/rewrap theo policy |

## 12. Checklist kiểm tra code và giao thức KEM

1. **JDK/API:** ứng dụng đang dùng Java 21+? `javax.crypto.KEM` tồn tại và KEM/provider được chọn hỗ trợ đúng profile?
2. **Key pair:** private key được bảo vệ an toàn và public key người nhận đến từ nguồn đã xác thực?
3. **Thuật toán:** `KEM.getInstance("DHKEM")` có tương thích loại key (ví dụ X25519) ở cả hai phía?
4. **Encapsulation:** chỉ `encapsulation()` được gửi, không có shared secret hoặc derived AES key bị lộ?
5. **Params:** nếu `params()` khác null, receiver có thiết kế parse/validate và tạo spec tương ứng không?
6. **Kích thước:** validate `encapsulationSize()`, giới hạn byte và version trước khi decapsulate/cấp phát?
7. **KDF:** shared secret được đưa qua key schedule/domain separation với context rõ, không dùng enc bytes hoặc một key cho nhiều purpose tùy tiện?
8. **AEAD:** nonce duy nhất với key, tag đúng, AAD ràng buộc metadata và encapsulation, plaintext chỉ được chấp nhận sau verify?
9. **Authentication:** có yêu cầu xác thực bên gửi không, và đã dùng cơ chế riêng thay vì coi public-key encryption là chữ ký?
10. **Envelope:** byte encoding, key ID, suite, params, lengths, AAD và compatibility giữa runtime/ngôn ngữ đã được mô tả và kiểm thử?
11. **Vòng đời:** key rotation, backup/restore, incident response, private-key compromise, secret log/heap dump và error handling đã tính đến?
12. **Kiểm thử âm:** truncated enc, sai key, sai version, sửa ciphertext/tag/header, replay, input quá lớn và thuật toán không hỗ trợ bị từ chối đúng cách?

## 13. Bài tập tự kiểm tra

**Câu 1.** Java 21 dùng class nào để khởi tạo KEM và hai nested class nào ở hai phía?  
**Đáp án:** `javax.crypto.KEM`; phía gửi là `KEM.Encapsulator`, phía nhận là `KEM.Decapsulator`.

**Câu 2.** `sender.encapsulate()` trả về byte array encapsulation trực tiếp hay một object?  
**Đáp án:** `KEM.Encapsulated` object; dùng `result.key()` lấy secret, `result.encapsulation()` lấy byte message, `result.params()` lấy optional params.

**Câu 3.** Trong DHKEM/X25519, ví dụ trả encapsulation 32 byte và shared secret 32 byte. Hai mảng này có giống nhau không?  
**Đáp án:** **Không**. Trùng kích thước không có nghĩa trùng ý nghĩa. Encapsulation có thể công khai; shared secret phải giữ bí mật.

**Câu 4.** Alice gửi `result.key().getEncoded()` qua mạng “để Bob dễ giải mã”. Vấn đề là gì?  
**Đáp án:** Lộ trực tiếp shared secret. Bob phải dùng private key và `encapsulation()` để `decapsulate`, không nhận raw secret.

**Câu 5.** Một `encapsulation()` bị sửa đúng một byte nhưng vẫn có độ dài 32. Có bảo đảm `decapsulate()` throw không?  
**Đáp án:** Không. Tùy KEM/provider, có thể ra secret khác. Phải xác minh AEAD tag của payload và metadata để bác bỏ.

**Câu 6.** Nếu code `encapsulate(0, 16, "AES")` hoạt động, hai tham số số học có nghĩa bit hay byte?  
**Đáp án:** Phạm vi theo **byte** trong shared secret, `from=0`, `to=16` exclusive. Overload decapsulation cần tương thích; không được hiểu là từ bit 0 đến bit 16.

**Câu 7.** Vì sao receiver không thể khôi phục secret từ `encapsulation()` nếu chỉ có public key?  
**Đáp án:** Decapsulation cần private key tương ứng; public key không đủ để khôi phục shared secret trong mô hình bảo mật dự kiến.

**Câu 8.** Dùng KEM + AES-GCM có đủ để Bob biết Alice là người đã gửi không?  
**Đáp án:** Không. Ai có public key Bob cũng có thể tạo secret/envelope mới. Cần xác thực người gửi riêng.

**Câu 9.** Một envelope có `keyId`, `nonce` và `encapsulation`. Chỉ cần parse là có thể tin những trường đó?  
**Đáp án:** Không. Chúng là dữ liệu ngoài; phải validate policy/key scope/độ dài và bind metadata quan trọng vào AAD/KDF context.

**Câu 10.** Có thể đổi Java 21 sang JDK khác rồi mặc định `KEM.getInstance("ML-KEM")` luôn chạy không?  
**Đáp án:** Không. Hỗ trợ thuật toán phụ thuộc JDK/provider phiên bản cụ thể; lớp KEM có từ Java 21 không đồng nghĩa mọi KEM có sẵn.

**Câu 11.** Khi đã có encapsulation, có cần nonce và tag AES-GCM không?  
**Đáp án:** **Có** nếu dùng AES-GCM: KEM không thay thế nonce/tag và không mã hóa payload.

**Câu 12.** Vì sao KEM + KDF + AES-GCM tự viết chưa mặc định tương thích HPKE?  
**Đáp án:** HPKE định nghĩa đầy đủ suite IDs, KDF key schedule, mode, context, nonce policy và các quy tắc giao thức. Phải theo đặc tả HPKE mới có interoperability đúng.

## 14. Tài liệu tham khảo API

- [JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452): giới thiệu lý do thiết kế API mới trong JDK 21.
- [Java SE 21 — javax.crypto.KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): contract, factory, overload, provider selection.
- [Java SE 21 — KEM.Encapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html): `encapsulate` và hai loại size.
- [Java SE 21 — KEM.Encapsulated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html): `key`, `encapsulation`, `params`.
- [Java SE 21 — KEM.Decapsulator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html): `decapsulate`, lỗi và input size.
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180): DHKEM, KDF, AEAD và các giao thức HPKE chuẩn.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869): HKDF-Extract/Expand dùng trong ví dụ dẫn xuất key.

### Ghi nhớ

**Java 21 `KEM` cung cấp primitive đóng gói khóa; `Encapsulator` tạo secret và encapsulation message; `Decapsulator` khôi phục secret bằng private key. Chỉ gửi encapsulation, không gửi secret.** Từ shared secret, thiết kế thêm **KDF có context + AEAD có nonce/AAD/tag**, kiểm chứng public key, chọn đúng key ID/suite và xử lý lỗi. KEM giúp thiết lập khóa an toàn theo mô hình thuật toán, **không thay thế mã hóa dữ liệu lớn, xác thực bên gửi hoặc toàn bộ giao thức bảo mật**.
