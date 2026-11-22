# 10.8 Thực nghiệm DHKEM và phân biệt khóa sinh ra với dữ liệu encapsulation

## Mục tiêu và yêu cầu môi trường

**DHKEM** (*Diffie–Hellman Key Encapsulation Mechanism*) là một cơ chế thiết lập **bí mật chung** bằng mật mã khóa công khai. Khi bên gửi đã có **public key đáng tin cậy của bên nhận**, họ có thể sinh đồng thời:

1. Một **shared secret** để hai phía sử dụng nội bộ làm vật liệu khóa.
2. Một **encapsulation message** có thể truyền công khai cho bên nhận.

Bên nhận dùng **private key tương ứng** và encapsulation message để tính lại **cùng shared secret**, không cần bên gửi chuyển secret lên mạng.

Bài học này giải thích chính xác vai trò hai kết quả, thử nghiệm API `javax.crypto.KEM` của Java, quan sát độ dài/kiểu dữ liệu, rồi dùng shared secret để dẫn xuất khóa cho AES-GCM. Nội dung nằm trong nhóm **Thỏa thuận và bọc khóa**, nhưng cần phân biệt KEM với **key agreement thuần**, **key wrapping** và **HPKE hoàn chỉnh**.

> **Yêu cầu phiên bản:** `javax.crypto.KEM`, `KEM.Encapsulated`, `KEM.Encapsulator` và `KEM.Decapsulator` xuất hiện từ **Java 21** (JEP 452). Chương trình runnable trong bài yêu cầu **JDK 21 trở lên có provider hỗ trợ `DHKEM` và `X25519`**. Nó **không biên dịch trên Java 17**, dù X25519 và `KeyAgreement` đã tồn tại ở Java 17. Không tự thay bằng `KeyAgreement` rồi gọi đó là cùng DHKEM.

## 1. Bài toán: chia sẻ một bí mật mà không gửi bí mật đó

Giả sử Bob muốn nhận dữ liệu mã hóa từ Alice:

- Bob giữ cặp khóa `(pkR, skR)`: `pkR` được công bố **sau khi xác thực nó thực sự thuộc Bob**, còn `skR` phải được bảo vệ.
- Alice biết `pkR`, nhưng **không biết `skR`**.
- Alice cần tạo một khóa phiên mà Bob cũng phục hồi được; khóa này không được xuất hiện trong thông điệp công khai.

Quy trình **base DHKEM**:

```text
                         BÊN GỬI (ALICE)              BÊN NHẬN (BOB)
                         -----------------            -----------------
Đã có public key Bob:    pkR -----------------------  pkR / skR
                                |                           |
                    KEM.newEncapsulator(pkR)                |
                                |                           |
                         encapsulate()                      |
                          /          \                      |
             shared secret K          encapsulation enc      |
                (GIỮ KÍN)                      |             |
                    |                           | -------->  |
       Dẫn xuất khóa AEAD                     (CÔNG KHAI)    |
                    |                                         |
                    |                             newDecapsulator(skR)
                    |                             decapsulate(enc)
                    |                                         |
               shared secret K <------- cùng giá trị --------+
                    |                                         |
          encrypt với khóa dẫn xuất                 decrypt với khóa dẫn xuất
```

**Quan trọng:** `encapsulation` **không phải shared secret**. Nó là dữ liệu cần để *bên sở hữu private key* tính ra shared secret. Bất kỳ ai thấy `enc` và `pkR` đều biết dữ liệu vận chuyển; họ **không được suy ra khóa bí mật** khi scheme và kích thước khóa còn an toàn.

Với API Java, có thể ghi nhớ cặp kết quả:

```java
// Đoạn minh họa nằm trong phương thức có xử lý checked exceptions:
KEM.Encapsulated result = sender.encapsulate();
SecretKey secret = result.key();        // nội bộ, phải giữ bí mật
byte[] enc = result.encapsulation();    // truyền cho bên nhận
```

Đừng đặt tên cả hai biến là `encryptedKey`: nó làm mờ sự khác nhau giữa **bí mật** và **thông điệp encapsulation**.

## 2. Phân biệt bằng kiểu dữ liệu, nơi sử dụng và mức độ bí mật

| Thuộc tính | `KEM.Encapsulated.key()` | `KEM.Encapsulated.encapsulation()` |
| --- | --- | --- |
| Giá trị trả về | `SecretKey` | `byte[]` |
| Bản chất | **KEM shared secret / keying material** | **KEM encapsulation message** (thường gọi là KEM ciphertext) |
| Nơi sử dụng | Bên gửi giữ kín; dẫn xuất khóa phiên/KDF | Bên gửi **truyền công khai** cho bên nhận |
| Bên nhận làm gì? | Không được nhận `key()` qua mạng; tự thu lại qua `decapsulate` | Đưa nguyên byte vào `decapsulate(enc)` |
| Mức độ bí mật | **Bí mật**: không log, không đặt trong header | **Không phải secret**: có thể lưu/chuyển cùng ciphertext |
| Biểu diễn | `SecretKey` thường có algorithm `"Generic"` khi dùng `encapsulate()` mặc định | Byte encoding theo KEM được chọn, **không tự mang khóa AES** |
| Độ dài | `encapsulator.secretSize()` | `encapsulator.encapsulationSize()` |
| Mục đích bảo mật | Vật liệu để KDF tạo khóa AEAD/MAC | Giúp recipient có `skR` **tái tạo bí mật** |
| Nếu bị công khai | Rò rỉ bí mật; có thể phá bảo mật dữ liệu dùng khóa đó | Bình thường trong thiết kế KEM; **không được giả sử là bí mật** |

**Cùng chiều dài không có nghĩa cùng dữ liệu.** Theo RFC 9180, đối với `DHKEM(X25519, HKDF-SHA256)`, `Nsecret = 32 byte` và `Nenc = 32 byte`. Sự trùng kích thước này khiến người mới học dễ gán nhầm `enc` cho khóa AES-256. Chúng có **ý nghĩa hoàn toàn khác**. Các suite khác cho thấy khác biệt rõ hơn:

| RFC 9180 KEM | KEM ID | `Nsecret` (byte) | `Nenc` (byte) |
| --- | --- | ---: | ---: |
| DHKEM(P-256, HKDF-SHA256) | `0x0010` | 32 | 65 |
| DHKEM(P-384, HKDF-SHA384) | `0x0011` | 48 | 97 |
| DHKEM(P-521, HKDF-SHA512) | `0x0012` | 64 | 133 |
| DHKEM(X25519, HKDF-SHA256) | `0x0020` | 32 | 32 |
| DHKEM(X448, HKDF-SHA512) | `0x0021` | 64 | 56 |

Đây là **giá trị của các suite chuẩn RFC 9180**, không có nghĩa provider Java đang cài hỗ trợ mọi suite. `KEM.getInstance("DHKEM")` kết hợp với **loại khóa** phù hợp sẽ cho provider xác định biến thể; giao thức giữa hai hệ thống vẫn phải thống nhất suite cụ thể.

Đối với `DHKEM(X25519, HKDF-SHA256)`, `enc` là **public key tạm thời của bên gửi được serialize theo quy tắc KEM**, không phải byte của shared secret và **không phải `pkR` của Bob**. Cũng đừng thay `enc` bằng `recipient.getPublic().getEncoded()`: Java public key encoded thường dùng **X.509 SubjectPublicKeyInfo (DER)**, có header/định dạng khác với `enc` raw 32 byte của X25519 DHKEM.

## 3. DHKEM bên trong làm gì?

RFC 9180 §4.1 định nghĩa DHKEM bằng **Diffie–Hellman (DH)** và **HKDF** với domain separation. Trong **base mode**:

- Bob đã có cặp khóa `(skR, pkR)`.
- Alice sinh một cặp khóa **ephemeral** `(skE, pkE)` cho lần encapsulation.
- Alice tính `dh = DH(skE, pkR)`.
- Alice gửi `enc = SerializePublicKey(pkE)`; không gửi `skE` hay `dh`.
- Bob nhận `enc`, tạo `pkE = DeserializePublicKey(enc)`, rồi tính `dh = DH(skR, pkE)`.
- Hai phía dùng **HKDF LabeledExtract/LabeledExpand** trên `dh` và **kem_context** được quy định (`enc || SerializePublicKey(pkR)` trong base mode) để nhận cùng **`shared_secret`**.

Dạng khái niệm (rút gọn để hiểu cấu trúc, **không phải mã triển khai HKDF**):

```text
Encap(pkR):
    (skE, pkE) = GenerateKeyPair()
    enc = SerializePublicKey(pkE)
    dh = DH(skE, pkR)
    kem_context = enc || SerializePublicKey(pkR)
    shared_secret = ExtractAndExpand(dh, kem_context)
    return (shared_secret, enc)

Decap(enc, skR):
    pkE = DeserializePublicKey(enc)
    dh = DH(skR, pkE)
    kem_context = enc || SerializePublicKey(pkR)
    shared_secret = ExtractAndExpand(dh, kem_context)
    return shared_secret
```

Trong thực tế, RFC còn gắn `suite_id`, `"KEM"`, các nhãn và kích thước vào HKDF; không được thay bằng một lệnh `KeyAgreement.generateSecret()` đơn giản rồi tuyên bố cho kết quả **cùng byte DHKEM**. `KeyAgreement` có thể sinh **DH raw secret** nhưng chưa thực hiện đúng toàn bộ **DHKEM KDF và context binding**.

**Điểm cần nhớ:**

1. `enc` thường là dữ liệu công khai đại diện cho **ephemeral public key**, không phải AES-encrypted shared secret.
2. `shared_secret` là đầu ra **sau bước dẫn xuất của DHKEM**, không nhất thiết giống byte raw DH.
3. Nếu gọi lại `encapsulate()` với cùng `pkR`, một ephemeral key mới được sinh, nên thường nhận **enc mới và secret mới**. Đừng dựa vào ngẫu nhiên để tạo test vector cố định trong production.
4. `decapsulate(enc)` với một private key khác có thể tạo **một bí mật khác** thay vì luôn ném exception. `decapsulate` thành công **chưa phải phép xác thực nội dung của ứng dụng**.
5. Base DHKEM không chứng minh “Alice là người gửi”, vì bất kỳ ai có `pkR` đều có thể `encapsulate`. Muốn xác thực danh tính, phải dùng giao thức/chứng chỉ/chữ ký hoặc các mode xác thực phù hợp, không mặc định KEM làm việc đó.

## 4. API Java 21+: cấu trúc và thứ tự gọi

Java 21 cung cấp `javax.crypto.KEM` như một **engine API** trong module `java.base`.

| Bước | Java API | Ý nghĩa |
| --- | --- | --- |
| Sinh cặp recipient | `KeyPairGenerator.getInstance("X25519")` | Tạo khóa DH của Bob; `getPublic()` phân phối sau xác thực, `getPrivate()` giữ kín |
| Chọn KEM | `KEM.getInstance("DHKEM")` | Chọn thuật toán Key Encapsulation Mechanism |
| Tạo đối tượng bên gửi | `kem.newEncapsulator(pkR)` | Chuẩn bị encapsulate bằng public key người nhận |
| Sinh kết quả | `encapsulator.encapsulate()` | Tạo `KEM.Encapsulated` chứa **secret + encapsulation** |
| Lấy secret người gửi | `result.key()` | `SecretKey`, giữ kín và đưa vào KDF |
| Lấy thông điệp truyền | `result.encapsulation()` | `byte[]`, gửi cho bên nhận |
| Tham số nếu có | `result.params()` | Byte tham số **tùy chọn**, có thể là `null`; không giả định mọi KEM đều cần hoặc mọi suite đều có |
| Tạo đối tượng bên nhận | `kem.newDecapsulator(skR)` | Chuẩn bị decapsulation bằng private key người nhận |
| Khôi phục secret | `decapsulator.decapsulate(enc)` | Trả `SecretKey` trùng với bên gửi khi input/key hợp lệ |
| Kiểm tra độ dài | `secretSize()`, `encapsulationSize()` | Số **byte** của bí mật và encapsulation, **không thay thế nhau** |

`KEM` cùng các đối tượng `Encapsulator`/`Decapsulator` trong API được thiết kế immutable và có thể gọi ở các thao tác concurrent theo contract, nhưng **vật liệu secret trả về vẫn phải được bảo vệ**. Khóa từ provider/HSM có thể không xuất được; `getEncoded()` có thể trả `null`. Vì vậy dùng `secretSize()` khi cần biết kích thước mà không phụ thuộc khả năng xuất key.

Thông thường `encapsulate()` tương đương dạng `encapsulate(0, secretSize(), "Generic")`. `SecretKey` mang nhãn **`Generic`**, vì nó là vật liệu khóa dùng cho KDF chứ chưa tự có thông số/loại để đưa thẳng vào AES.

API còn cung cấp overload `encapsulate(from, to, algorithm)` và `decapsulate(enc, from, to, algorithm)` để nhận một đoạn key material được gắn tên thuật toán (ví dụ `"AES"`). Chỉ dùng khi **hai phía thống nhất chính xác phạm vi byte, thuật toán và chính sách dẫn xuất**; cách an toàn, linh hoạt cho giao thức là đưa full KEM secret vào **KDF có domain separation** để tạo key chuyên dụng.

### 4.1 Không pin provider vô cớ

```java
// Đoạn minh họa trong phương thức có xử lý checked exception:
KEM kem = KEM.getInstance("DHKEM");
KEM.Encapsulator sender = kem.newEncapsulator(receiverPublicKey);
String senderProvider = sender.providerName();
```

Khi gọi `KEM.getInstance("DHKEM")` không chỉ định provider, việc chọn implementation có thể phụ thuộc public/private key lúc tạo encapsulator/decapsulator. Có thể tra `providerName()` trên từng đối tượng. **Không giả định hai phía sử dụng cùng provider**; chúng cần đồng thuận về algorithm/variant và encoding chuẩn, rồi kiểm thử interoperability. `DHKEM` là **tên KEM**, còn `X25519` là **thuật toán tạo keypair / nhóm DH**, không phải hai chuỗi có thể thay cho nhau ở `getInstance`.

## 5. Chương trình Java 21 chạy được: phân biệt secret, encapsulation và dùng AES-GCM

Mã bên dưới tạo một recipient X25519, chạy DHKEM, in **chỉ tên/độ dài/kết quả so sánh** (không in hex secret), kiểm tra hai bên tính cùng secret, rồi dẫn xuất một khóa AES-128 qua **HKDF-SHA256** để mã hóa/xác thực một thông điệp bằng **AES-GCM**. Cuối cùng, thử sửa ciphertext và cắt ngắn encapsulation để quan sát sự từ chối.

**Giới hạn có chủ đích:** HKDF ứng dụng và AES-GCM ở đây là **minh họa một tổ hợp KEM → KDF → AEAD**, **không phải implementation HPKE chuẩn RFC 9180**; HPKE còn có key schedule, mode, suite identifier, nonce/sequence và context đầy đủ. Trong ứng dụng thật, ưu tiên thư viện/giao thức HPKE được kiểm chứng khi cần wire compatibility với HPKE.

Tạo file **`DhkemExperiment.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.DecapsulateException;
import javax.crypto.KEM;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class DhkemExperiment {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String MAC = "HmacSHA256";

    // HKDF-SHA256 Extract + one Expand block, L = 16 bytes.
    // Lesson-specific info: this is NOT the full HPKE key schedule.
    private static SecretKey deriveAes128(SecretKey kemSecret)
            throws GeneralSecurityException {
        byte[] ikm = kemSecret.getEncoded();
        if (ikm == null) {
            throw new GeneralSecurityException("Non-exportable key in demo");
        }
        Mac mac = Mac.getInstance(MAC);
        mac.init(new SecretKeySpec(new byte[32], MAC)); // no salt
        byte[] prk = mac.doFinal(ikm);                  // HKDF-Extract
        mac.init(new SecretKeySpec(prk, MAC));
        mac.update("DHKEM-demo/AES128GCM/v1"
                .getBytes(StandardCharsets.UTF_8));
        mac.update((byte) 1);
        byte[] okm = mac.doFinal();                    // HKDF-Expand T(1)
        return new SecretKeySpec(Arrays.copyOf(okm, 16), "AES");
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        KeyPair recipient = generator.generateKeyPair();

        KEM kem = KEM.getInstance("DHKEM");
        KEM.Encapsulator sender = kem.newEncapsulator(recipient.getPublic());
        KEM.Encapsulated packet = sender.encapsulate();
        SecretKey senderSecret = packet.key();         // keep private
        byte[] enc = packet.encapsulation();           // send to receiver

        KEM.Decapsulator receiver = kem.newDecapsulator(
                recipient.getPrivate());
        SecretKey receiverSecret = receiver.decapsulate(enc);

        System.out.println("KEM: " + kem.getAlgorithm());
        System.out.println("Secret algorithm: " + senderSecret.getAlgorithm());
        System.out.println("Secret bytes: " + sender.secretSize());
        System.out.println("Encapsulation bytes: " + sender.encapsulationSize());
        System.out.println("Secrets match: " + MessageDigest.isEqual(
                senderSecret.getEncoded(), receiverSecret.getEncoded()));

        SecretKey writeKey = deriveAes128(senderSecret);
        SecretKey readKey = deriveAes128(receiverSecret);
        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);
        byte[] message = "Hello DHKEM".getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, writeKey,
                new GCMParameterSpec(128, nonce));
        encryptor.updateAAD(enc);
        byte[] body = encryptor.doFinal(message);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, readKey,
                new GCMParameterSpec(128, nonce));
        decryptor.updateAAD(enc);
        byte[] recovered = decryptor.doFinal(body);
        System.out.println("AES-GCM round-trip: " + Arrays.equals(
                message, recovered));

        byte[] modified = body.clone();
        modified[0] ^= 1;
        Cipher verifier = Cipher.getInstance("AES/GCM/NoPadding");
        verifier.init(Cipher.DECRYPT_MODE, readKey,
                new GCMParameterSpec(128, nonce));
        verifier.updateAAD(enc);
        boolean tamperRejected = false;
        try {
            verifier.doFinal(modified);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("Tampered payload rejected: " + tamperRejected);

        boolean shortEncRejected = false;
        try {
            receiver.decapsulate(Arrays.copyOf(enc, enc.length - 1));
        } catch (DecapsulateException expected) {
            shortEncRejected = true;
        }
        System.out.println("Short encapsulation rejected: " + shortEncRejected);
    }
}
```

Biên dịch/chạy trong thư mục chứa file (JDK 21 trở lên):

```bash
javac --release 21 DhkemExperiment.java
java DhkemExperiment
```

Stdout trên JDK hỗ trợ `DHKEM(X25519, HKDF-SHA256)` như môi trường thử nghiệm:

```text
KEM: DHKEM
Secret algorithm: Generic
Secret bytes: 32
Encapsulation bytes: 32
Secrets match: true
AES-GCM round-trip: true
Tampered payload rejected: true
Short encapsulation rejected: true
```

### 5.1 Đọc kết quả đúng cách

**Hai dòng 32 byte có nghĩa gì?**

- `Secret bytes: 32`: kích thước KEM shared secret của X25519/HKDF-SHA256 là 32 byte.
- `Encapsulation bytes: 32`: kích thước public ephemeral X25519 được serialize dưới dạng `enc` là 32 byte.
- **Không thể suy ra** `senderSecret.getEncoded()` bằng `enc`, hoặc có thể dùng `enc` như khóa AES. Việc **cùng length là trùng hợp của biến thể**.

`Secret algorithm: Generic` cho biết KEM default trả về **generic keying material**, không tự tuyên bố đó là khóa AES-128/256. `Secrets match: true` chứng tỏ khi dùng đúng public/private key và cùng `enc`, hai bên sinh ra cùng secret. Trong demo, so sánh byte được vì provider trả khóa **extractable**; code production làm việc với HSM có thể cần API/KDF của provider mà không xuất secret bytes.

**Vì sao dùng HKDF một lần nữa dù DHKEM đã dùng HKDF nội bộ?** DHKEM dùng HKDF để chuyển **DH shared secret** thành **KEM shared secret**, gắn `kem_context`; còn ứng dụng cần dẫn xuất các **khóa có mục đích sử dụng riêng** (ví dụ AES-GCM, MAC, exporter) theo thông tin phiên bản/ngữ cảnh. Hàm `deriveAes128` minh họa HKDF-SHA256 với extract có salt 32 byte zero (cách biểu diễn trường hợp không có salt trong RFC 5869) và một expand block chứa `info` riêng rồi `0x01`, cắt lấy 16 byte làm AES-128. Đây **không phải HPKE key schedule** và không phải mã nguồn thư viện HKDF tổng quát.

**AES-GCM kiểm tra gì?** Cả hai bên dẫn xuất cùng AES key, dùng cùng nonce 12 byte và `enc` làm **associated authenticated data (AAD)**, do đó giải mã thành công. Sửa byte ciphertext làm GCM tag kiểm tra thất bại. Cắt encapsulation từ 32 thành 31 byte bị `DecapsulateException` vì sai kích thước.

> Trong demo, AAD mới ràng buộc `enc` nhằm làm rõ ý tưởng. Giao thức thực phải ràng buộc thêm **version, suite ID, key ID, recipient/context/metadata cần xác thực** bằng encoding duy nhất. Nonce phải **duy nhất theo mỗi khóa AES-GCM**, không tái sử dụng khi dùng cùng key. KEM base mode + AES-GCM không xác thực tên/danh tính **người gửi**.

### 5.2 Vì sao không in raw secret hoặc cố tạo output hex cố định?

Mỗi lượt `encapsulate()` tạo ephemeral key mới và dùng randomness. Vì vậy `enc` và `shared_secret` thay đổi giữa các lần chạy; in hex ra console/log có thể rò rỉ secret và không giúp chứng minh correctness. Bài chỉ in kiểu, độ dài, equality và kết quả AEAD. Nếu cần **test vectors** tái lập, dùng bộ vector chuẩn RFC 9180 và công cụ dành riêng cho test; không tái dùng ephemeral private key/nonce cố định trong production.

Khi thử `KEM` ở provider khác, đừng mặc định `SecretKey.getEncoded()` luôn trả byte. API có `secretSize()` để biết độ dài và cơ chế provider-native để sử dụng key không xuất được. Nếu provider không hỗ trợ khả năng xuất key, demo sẽ dừng bằng lỗi rõ ràng ở hàm HKDF; ứng dụng thực cần thay phần KDF để đáp ứng chính sách khóa.

## 6. Thiết kế dữ liệu truyền: cái gì có thể gửi, cái gì phải giữ kín?

Một bản ghi dùng KEM để mã hóa payload bằng AEAD có thể được khái niệm hóa như:

```text
+------------------+----------------+----------------+-------------------+
| version/suite ID | key ID (Bob)   | enc (public)   | nonce (public)    |
+------------------+----------------+----------------+-------------------+
| ciphertext (encrypted payload)            | AEAD tag (authenticated)   |
+--------------------------------------------------------------------------+

KHÔNG bao giờ có trường: senderSecret / receiverSecret / privateKey.
```

Thành phần và nơi giữ:

| Dữ liệu | Nơi phát sinh | Có thể truyền? | Lưu ý |
| --- | --- | --- | --- |
| Bob public key `pkR` | Bob/PKI/registry | Có | Alice phải xác thực khóa thuộc Bob và đúng loại/mục đích. |
| Bob private key `skR` | Bob/KMS/HSM | **Không** | Giữ kín, không lưu cùng ciphertext. |
| Sender ephemeral private `skE` | Nội bộ quá trình DHKEM | **Không** | Không được tiết lộ; provider tạo và quản lý. |
| `enc` | `packet.encapsulation()` | **Có** | Là thông điệp KEM, phải được phân loại theo suite và kiểm tra size. |
| KEM shared secret | `packet.key()` / `decapsulate(enc)` | **Không** | Vật liệu dẫn xuất khóa ứng dụng. |
| AEAD nonce | Bên mã hóa dữ liệu | **Có** | Phải unique theo AEAD key, không cần bí mật. |
| AEAD ciphertext/tag | Bên mã hóa dữ liệu | **Có** | Không sử dụng plaintext khi tag sai. |
| Suite/version/key ID | Giao thức ứng dụng | Có | Không được để đầu vào chưa xác thực buộc fallback xuống thuật toán yếu. |

**Dữ liệu encapsulation có thể là đầu vào không tin cậy của parser/crypto provider.** Cần kiểm tra giới hạn độ dài, format, algorithm/key ID và resource policy, bắt lỗi giải mã an toàn. Việc `decapsulate` trả `SecretKey` không đồng nghĩa bản ghi nguồn đã được xác thực hoặc ciphertext ứng dụng có integrity. Chỉ sau khi chứng thực payload/context bằng cơ chế AEAD/chữ ký đúng mới dùng dữ liệu để ra quyết định nghiệp vụ.

## 7. `enc` có phải “bản mã chứa shared key” theo nghĩa thông thường?

Tài liệu KEM đôi lúc gọi `encapsulation` là **KEM ciphertext**. Thuật ngữ này có thể gây hiểu nhầm vì nó **không phải** ciphertext của dữ liệu người dùng và cũng không nhất thiết là một **key đã được encrypt trực tiếp**.

Đối với **DHKEM trên DH group**, `enc` là **serialized ephemeral public key**. Shared secret được hình thành nhờ toán học DH giữa ephemeral private của sender và private của recipient, sau đó qua KDF. Điều này khác với:

- Dùng `Cipher.getInstance("AES/GCM/NoPadding")` để mã hóa message: đầu ra là **AEAD ciphertext + tag**.
- Dùng `Cipher.wrap(aesKey)` với một key-encryption algorithm: tạo representation được wrap của **một khóa đã có trước**. Ngữ nghĩa/định dạng phụ thuộc wrap scheme.
- Dùng `KeyAgreement.getInstance("X25519")`: tạo **raw DH shared secret** từ hai khóa phía mỗi bên; API **không tự tạo encapsulation format + RFC 9180 KDF**.
- Dùng `KEM.encapsulate()`: **sinh vật liệu khóa mới cùng message cho phép decapsulation**; người nhận lấy cùng key material bằng private key.
- Dùng **HPKE RFC 9180**: tổ hợp **KEM + một KDF/key schedule riêng + AEAD** trong một ciphersuite/mode được chuẩn hóa, có quy tắc context và nhiều message.

Đặt tên các biến theo mục đích:

```text
KemOutput = {
    secret: KEM shared secret,         // private
    encapsulation: KEM transport bytes // public
}

Envelope = {
    kemId, recipientKeyId, enc,
    aeadNonce, encryptedPayloadAndTag
}
```

Đừng dùng `secret = enc`, `AES(enc, plaintext)` hoặc `recipientPrivateKey = packet.key()`. Cả ba cách hiểu đều sai về vai trò/thuật toán.

## 8. Lỗi thực nghiệm cần tự kiểm chứng

| Tình huống | Kết quả đúng | Giải thích |
| --- | --- | --- |
| `encapsulate` với Bob.public, `decapsulate` bằng Bob.private | Secret giống nhau | Đúng cặp recipient và biến thể KEM. |
| Dùng `enc` như AES key vì có 32 byte | **Sai thiết kế** | `enc` public, attacker biết; không có confidentiality. |
| Chuyển `packet.key().getEncoded()` cho bên nhận | **Sai thiết kế** | Tiết lộ shared secret lên đường truyền, phá lợi ích KEM. |
| Dùng private key của người khác để decapsulate | Không thu được đúng secret của sender; có thể tạo secret khác hoặc lỗi | **Đừng đòi một exception cố định** cho mọi wrong-key/tamper case. |
| Cắt `enc` từ 32 còn 31 byte (X25519) | `DecapsulateException` | Sai `encapsulationSize`; test minh họa trong code. |
| Lật 1 bit trong `enc` nhưng độ dài vẫn đúng | Có thể trả secret khác hoặc bị từ chối; **không đảm bảo tag-style rejection** | KEM base không có authentication tag của dữ liệu ứng dụng. |
| Lật 1 bit của AES-GCM body/tag | Bị từ chối khi tag verification thất bại | Điều kiện integrity do AEAD cung cấp, không phải KEM tự có. |
| Đổi AAD `enc` sau khi encrypt, giữ nguyên body/tag | GCM verification thất bại | Ràng buộc `enc` vào ciphertext đã xác thực. |
| Gọi `decapsulate()` nhưng quên chuyển đủ `enc` | Lỗi hoặc sai secret | Phải truyền nguyên byte của encapsulation theo format chuẩn. |
| In ra key material để kiểm tra equality | Có nguy cơ lộ secret | Chỉ so sánh nội bộ hoặc dùng vector kiểm thử riêng, không log secret. |
| Chạy trên JDK 17 rồi import `javax.crypto.KEM` | **Lỗi biên dịch** | API bắt đầu Java 21; dùng JDK 21+ hoặc thuật toán/giao thức khác được đặc tả. |
| Đưa raw X25519 public key SPKI vào `decapsulate` thay `enc` | Sai encoding/size | `enc` không phải `PublicKey.getEncoded()` tùy ý. |

**Một điều đặc biệt quan trọng:** Không viết test “mọi encapsulation bị sửa đều khiến `decapsulate` ném lỗi” hoặc “`decapsulate` thành công thì peer đã được xác thực”. Cả hai kết luận đều sai. Kiểm tra **AEAD tag hoặc authentication của giao thức** sau khi thiết lập key material.

## 9. Lựa chọn thuật toán, provider và tương thích

### 9.1 Java 21 và chuẩn RFC 9180

`DHKEM` là tên trong **Java Security Standard Algorithm Names**. Các nhóm DHKEM được RFC 9180 xác định có KEM ID, KDF và encoding riêng. Java `KEM.getInstance("DHKEM")` có thể lựa chọn implementation/variant tương thích dựa trên key type/params; Java 21 API không tự tạo wire-format ciphersuite đầy đủ cho ứng dụng.

Thực hành tốt:

- Ghi **protocol version**, **KEM suite ID** theo chuẩn bạn đã chọn, key ID người nhận và định dạng encapsulation đã thống nhất.
- Trước khi decode, kiểm tra `encapsulationSize()`, kích thước bản ghi và cận trên của mọi length field.
- Nếu application cần tương tác với ngôn ngữ khác, kiểm tra theo **RFC 9180 test vectors** đúng suite, không chỉ dựa vào “cùng X25519”.
- Khi đổi provider, kiểm thử `encapsulate` ở provider A và `decapsulate` ở provider B với cùng public/private key, đúng encoding và params.
- Không ép provider cụ thể như `SunJCE` trừ khi yêu cầu kỹ thuật/compliance/HSM bắt buộc; lúc đó cần mô tả dependency.
- Nếu `KEM.getInstance()` hoặc `newEncapsulator()`/`newDecapsulator()` báo không hỗ trợ algorithm/key, coi đó là lỗi cấu hình; **không tự fallback** sang KEM không được phê duyệt.

### 9.2 Một số ngoại lệ/API behavior

| Vị trí | Lỗi hoặc trạng thái | Hướng xử lý |
| --- | --- | --- |
| `KeyPairGenerator.getInstance("X25519")` | `NoSuchAlgorithmException` | JDK/provider không hỗ trợ tên tạo khóa. |
| `KEM.getInstance("DHKEM")` | `NoSuchAlgorithmException` | KEM chưa khả dụng trên runtime/provider. |
| `newEncapsulator(pkR)` / `newDecapsulator(skR)` | `InvalidKeyException` hoặc thiếu tham số/provider hỗ trợ | Kiểm tra loại/nguồn khóa và policy; public/private key không được hoán đổi. |
| `encapsulate()` | Lỗi provider/randomness | Không tái sử dụng output lỗi hoặc thay bằng key/enc tự chế. |
| `decapsulate(enc)` | `DecapsulateException` khi input có lỗi như size không hợp lệ | Từ chối bản ghi; không log secret, không fallback KEM khác. |
| `secret.getEncoded() == null` | Khóa không xuất được | Dùng API provider-native/KDF phù hợp; **không mặc định byte[] luôn có**. |
| `AES/GCM/NoPadding` `doFinal()` | `AEADBadTagException` | Ciphertext/key/nonce/AAD bị sửa hoặc không khớp; từ chối mọi plaintext. |

`KEM.Decapsulator.decapsulate(encapsulation)` kiểm tra kích thước `enc`; trong ví dụ sai 31 byte được từ chối. Nhưng **validation của cấu trúc KEM không thay thế authentication của payload**.

### 9.3 Vòng đời key pair và tính chất bảo mật

- Recipient public key phải được **xác thực** (PKI, pinning, registry đáng tin). Nếu attacker thay `pkR` trước khi sender encapsulate, sender sẽ chia sẻ secret với attacker chứ không phải Bob.
- Recipient private key phải được bảo vệ bởi keystore/KMS/HSM phù hợp, có key usage/policy, rotation và chiến lược lưu lịch sử khi còn cần giải mã bản ghi cũ.
- Dùng ephemeral sender key mới từng lần giúp phiên hóa bí mật, nhưng nếu Bob dùng **recipient private key tĩnh** và sau này nó bị lộ, attacker có thể decapsulate các `enc` cũ lưu được. **Không mặc nhiên có forward secrecy đối với compromise của khóa nhận tĩnh.**
- Base DHKEM (bất kỳ bên nào biết `pkR` cũng encapsulate được) **không xác thực sender**. AES-GCM chỉ chứng minh ciphertext hợp lệ với key phiên; cần cơ chế xác thực nguồn/identity riêng nếu ứng dụng yêu cầu.
- Không coi KEM X25519 là hậu lượng tử. Nếu threat model yêu cầu hậu lượng tử/hybrid PQ, phải chọn một scheme được đặc tả và triển khai phù hợp, không tự nối bytes của hai KEM rồi gọi là an toàn.
- Chữ ký số, key agreement, KEM, key wrapping và AEAD giải quyết các lớp khác nhau. **Đúng API không tự bảo đảm đúng protocol**.

## 10. Bài tập thực nghiệm mở rộng

**Bài tập 1 — Quan sát độ dài:** Chạy chương trình nhiều lần với X25519. Ghi nhận `Secret bytes=32`, `Encapsulation bytes=32`, kết quả equality. Không in secret. Giải thích vì sao cùng độ dài **không** cho phép gán `enc` làm key.

**Bài tập 2 — Sai khóa nhận:** Sinh thêm một cặp X25519, dùng private key mới gọi `decapsulate(enc)` từ cặp cũ. Nếu provider trả secret, so sánh **nội bộ** với sender secret; không giả định bắt buộc ném exception. Sau đó thử dùng khóa sai với AES-GCM để xác minh tag không chấp nhận ciphertext.

**Bài tập 3 — Sai độ dài:** Sửa `enc` thành 31 hoặc 33 byte; dự đoán `DecapsulateException` và đối chiếu `encapsulationSize()` trước khi gọi để parser không chấp nhận dữ liệu thừa/thiếu.

**Bài tập 4 — Tách nguồn lỗi:** Thử riêng (a) hỏng encapsulation, (b) hỏng AEAD body, (c) sai AEAD nonce, (d) sai AAD. Phân biệt lỗi KEM với lỗi GCM tag; không in ra private key hoặc plaintext chưa xác thực.

**Bài tập 5 — Chuẩn hóa format:** Đề xuất binary envelope có magic/version, KEM suite, recipient key ID, `enc` length + bytes, AEAD nonce, ciphertext length + body/tag. Định nghĩa encoding/endianness, max sizes và phạm vi AAD. Nêu rõ **không có trường truyền KEM shared secret**.

**Bài tập 6 — Interoperability:** Nếu có hai provider, thử encapsulate/decapsulate chéo. Giữ nguyên suite/encoding và so sánh kết quả với test vector RFC 9180, tránh chỉ kiểm tra một runtime.

## 11. Checklist thiết kế và review

- [ ] Runtime dùng **Java 21+** cho `javax.crypto.KEM`; không gắn nhầm vào API Java 17.
- [ ] Recipient key pair phù hợp `DHKEM` (ví dụ X25519); public key được **xác thực danh tính**.
- [ ] `KEM.Encapsulated.key()` được bảo vệ như **secret**, không gửi/log/lưu công khai.
- [ ] `KEM.Encapsulated.encapsulation()` được gửi/lưu như **public transport message**, không coi nó là raw secret hoặc khóa AES.
- [ ] Bên nhận dùng **private key recipient** và đúng byte `enc` cho `newDecapsulator(...).decapsulate(...)`.
- [ ] Protocol biết suite/algorithm, encoding và `encapsulationSize()`, có max-length và version/key ID rõ ràng.
- [ ] KEM shared secret được dẫn xuất thành key cho mục đích riêng bằng **KDF/HPKE key schedule phù hợp**; không dùng raw DH secret thay cho output DHKEM.
- [ ] Payload dùng AEAD có nonce/tag/AAD đúng; tag thất bại thì **fail closed**.
- [ ] Không khẳng định `decapsulate` tự xác thực người gửi, chống replay hoặc luôn báo lỗi khi encapsulation bị thay bit.
- [ ] Có kế hoạch quản lý/luân chuyển recipient private key và threat model compromise/forward secrecy.
- [ ] Có kiểm thử đúng/sai key, truncated `enc`, tampered payload, mismatched AAD, cross-provider và encoding.

## 12. Câu hỏi tự kiểm tra

**1. `packet.key()` và `packet.encapsulation()` khác nhau thế nào?**  
`key()` là **secret `SecretKey`**, phải giữ kín, thường đưa vào KDF. `encapsulation()` là **byte thông điệp KEM công khai** gửi cho recipient, không chứa bản sao raw secret.

**2. Với X25519, vì sao cả hai đều dài 32 byte?**  
Bởi RFC 9180 quy định **`Nsecret = Nenc = 32`** cho suite này. Hai giá trị cùng độ dài nhưng khác vai trò và cơ chế tạo; nhiều suite khác có Nenc và Nsecret khác nhau.

**3. Bob cần dữ liệu gì để lấy cùng shared secret?**  
Private key `skR` và byte `enc` của sender, thêm lựa chọn KEM/params nhất quán. Bob **không cần nhận secret từ sender**.

**4. Đã `decapsulate(enc)` được `SecretKey` có chứng minh Alice gửi không?**  
**Không.** Base DHKEM cho bất kỳ ai có `pkR` làm encapsulation; cần xác thực sender theo giao thức nếu cần.

**5. Có thể dùng `getEncoded()` của X25519 public key thay cho `enc` không?**  
**Không tùy tiện.** `enc` tuân theo serialization của KEM (raw ephemeral public key X25519 32 byte), còn `PublicKey.getEncoded()` trong Java thường là X.509 SPKI.

**6. Vì sao Java 17 không chạy ví dụ?**  
API `javax.crypto.KEM` được bổ sung từ **Java 21**. `KeyAgreement` X25519 từ phiên bản cũ không tự thực hiện cùng `DHKEM ExtractAndExpand`.

**7. Dữ liệu encapsulation bị thay đổi có luôn gây `DecapsulateException` không?**  
**Không.** Input sai kích thước bị lỗi, còn input đủ kích thước nhưng khác byte có thể tạo secret khác. Cần **AEAD tag hoặc authentication riêng** để phát hiện sai lệch của dữ liệu ứng dụng.

**8. Ví dụ Java trong bài có phải HPKE RFC 9180 đầy đủ không?**  
**Không.** Nó dùng chuẩn DHKEM, thêm một HKDF đơn giản có info riêng và AES-GCM để học cách kết hợp. HPKE chính thức có key schedule/context/modes/nonce quy định chi tiết và cần implementation riêng.

## Nguồn tham khảo chính thức

- [Java SE 21 — `javax.crypto.KEM`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html): mô hình sender/receiver, `newEncapsulator`, `encapsulate`, `newDecapsulator`, `decapsulate`, lựa chọn provider.
- [Java SE 21 — `KEM.Encapsulated`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulated.html): `key()`, `encapsulation()`, `params()` và kiểu dữ liệu của từng trường.
- [Java SE 21 — `KEM.Encapsulator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Encapsulator.html): `secretSize`, `encapsulationSize`, overload `encapsulate`.
- [Java SE 21 — `KEM.Decapsulator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.Decapsulator.html): `decapsulate` và các điều kiện lỗi.
- [Java SE 21 — `DecapsulateException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/DecapsulateException.html): lỗi trong quá trình decapsulation.
- [Java SE 21 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên `DHKEM` trong nhóm KEM và chuẩn hóa thuật toán.
- [OpenJDK JEP 452 — Key Encapsulation Mechanism API](https://openjdk.org/jeps/452): lý do ra đời và phạm vi API (JDK 21).
- [RFC 9180 — Hybrid Public Key Encryption](https://www.rfc-editor.org/rfc/rfc9180.html): §4.1 DHKEM, §7.1 các KEM IDs và độ dài Nsecret/Nenc, §5 HPKE key schedule/context.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869): extract/expand và context binding ở mức KDF.

**Ghi nhớ:** `KEM.encapsulate()` **sinh ra hai thứ**: **`SecretKey` để giữ kín và dẫn xuất khóa**, và **`encapsulation` để gửi công khai cho người nhận**. `decapsulate(enc)` kết hợp dữ liệu công khai đó với **private key** để tái lập shared secret. Dùng `enc` như khóa bí mật là lỗi thiết kế nghiêm trọng; đồng thời không nhầm KEM base với mã hóa AEAD, xác thực danh tính, hay full HPKE.
