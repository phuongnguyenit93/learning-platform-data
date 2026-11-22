# EdDSA: Vai trò private key, public key và thông điệp trong chữ ký số Java

> **Phạm vi:** Bài thuộc chủ đề **EdDSA** của module Java 15, tập trung chính xác vào ba thành phần **private key**, **public key** và **thông điệp (message)** trong quá trình **ký** và **xác minh chữ ký số**. Java hỗ trợ EdDSA từ **Java 15** (JEP 339); `Ed25519` và `Ed448` vẫn là tên thuật toán chính thức trong các JDK hiện đại. Các ví dụ sử dụng **JDK 17+**, API chuẩn `java.security`, không dùng thuật toán lỗi thời, nội bộ JDK hay tính năng preview.

## 1. Bức tranh tổng quát: ba thành phần, hai thao tác

EdDSA (*Edwards-curve Digital Signature Algorithm*) là một họ **thuật toán chữ ký số khóa bất đối xứng** được tiêu chuẩn hóa trong RFC 8032. Để hiểu chữ ký EdDSA, hãy phân biệt:

1. **Private key (khóa riêng):** bí mật chỉ chủ thể ký được phép sử dụng; cấp khả năng **tạo chữ ký hợp lệ**.
2. **Public key (khóa công khai):** tương ứng về mặt toán học với private key; được phân phối đến bên cần **kiểm tra chữ ký**.
3. **Message (thông điệp):** **chính xác dãy byte** cần xác nhận về nguồn gốc và tính toàn vẹn. Nó không phải khóa.

Còn một thành phần được tạo ra từ quá trình ký là **signature (chữ ký)**: dữ liệu nhị phân mà người nhận dùng cùng **public key** và **message** để kiểm tra.

Sơ đồ luồng:

```text
Bên ký (Signer)                              Bên nhận (Verifier)

private key [BÍ MẬT]                         public key [ĐƯỢC TIN CẬY]
       |                                            |
       |     message bytes                          |       message bytes
       |          |                                 |            |
       v          v                                 v            v
        Ed25519.sign(...)                             Ed25519.verify(...)
               |                                          ^
               v                                          |
          signature bytes -------------------------------+
                                                          |
                                             true / false / lỗi đầu vào
```

Quan hệ cơ bản:

```text
signature = Sign(privateKey, messageBytes)
valid     = Verify(publicKey, messageBytes, signature)
```

**Điểm mấu chốt:** người xác minh **không cần private key**. Chữ ký được tạo bằng **private key**, còn phép kiểm tra dùng **public key tương ứng** và **cùng một dãy byte thông điệp**. Chỉ nhìn signature mà không có message và public key thì không thể thực hiện đầy đủ phép xác minh.

Một chữ ký hợp lệ cho biết dữ liệu khớp với khóa công khai được dùng trong phép kiểm tra. Nhưng để kết luận nó thuộc về **một người/tổ chức cụ thể**, hệ thống còn phải có **cơ chế tin cậy và gắn public key với danh tính**.

## 2. Private key: quyền tạo chữ ký, phải giữ bí mật

Private key thuộc cặp khóa được tạo bằng `KeyPairGenerator`. Với Java:

```java
KeyPairGenerator generator =
        KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = generator.generateKeyPair();

PrivateKey privateKey = pair.getPrivate();
```

Đây là **snippet** cần các import `java.security.*` và phải đặt trong phương thức xử lý `NoSuchAlgorithmException`. Chương trình hoàn chỉnh nằm ở phần 6.

### Vai trò chính xác

- Bên ký cung cấp **private key** cho `Signature.initSign(privateKey)`.
- Sau đó gọi `Signature.update(messageBytes)` để cung cấp nội dung cần ký và `Signature.sign()` để tạo **byte[] signature**.
- Private key **không** được gửi cùng chữ ký đến người nhận, không được in log, không được đặt trong client web/mobile hoặc mã nguồn công khai.
- Bên nhận không cần biết private key: chỉ cần **public key đúng**, message và chữ ký.
- Nếu private key bị lộ, một kẻ khác có thể **giả mạo chữ ký mới** mà vẫn được public key tương ứng xác minh thành công. Khi đó cần **thu hồi/đổi khóa, cập nhật hệ thống tin cậy và điều tra phạm vi ảnh hưởng**.

### Khởi tạo khóa và tính ngẫu nhiên

`KeyPairGenerator.generateKeyPair()` tạo cặp khóa mới bằng nguồn ngẫu nhiên mã hóa được provider sử dụng theo cấu hình của JDK. Cần để **provider bảo mật được hỗ trợ** tạo khóa; không cố tình dùng seed dễ đoán hoặc một `java.util.Random` để tái lập private key trong hệ thống thật.

**Phân biệt hai việc:** tạo private key cần vật liệu ngẫu nhiên an toàn; còn **thuật toán ký Ed25519 theo RFC 8032 là xác định (deterministic)** đối với cùng private key và cùng thông điệp. Vì vậy có thể nhận cùng signature từ việc ký lại cùng message với cùng key; điều đó **không** có nghĩa quá trình sinh cặp khóa không cần random.

### Lưu trữ và bảo vệ

- Dùng keystore, secret manager, HSM hoặc dịch vụ quản lý khóa theo năng lực của hệ thống; hạn chế quyền **đọc/xuất/sử dụng khóa**.
- Với provider hỗ trợ khóa **không xuất được**, `PrivateKey.getEncoded()` có thể trả `null`. Không giả định mọi private key đều là một mảng bytes có thể mang đi.
- API `EdECPrivateKey.getBytes()` trả `Optional<byte[]>` và có thể rỗng khi provider không muốn tiết lộ vật liệu khóa; **không** coi trạng thái đó là lỗi.
- Khi bắt buộc lưu private key có thể xuất, cần quy định rõ format, mã hóa bảo vệ lúc lưu, quyền truy cập, sao lưu, đổi khóa và quy trình ứng phó sự cố. **Không bao giờ** lưu private key bên trong log hoặc gửi kèm message cho verifier.
- Không tạo một cặp khóa mới **mỗi lần ký** nếu người nhận vẫn cần xác minh theo một public key đã công bố mà không có cơ chế quản lý thay đổi khóa; phải thiết kế **vòng đời khóa** rõ ràng.

## 3. Public key: kiểm tra chữ ký, nhưng phải biết khóa này của ai

Public key cùng cặp với private key:

```java
PublicKey publicKey = pair.getPublic();
```

Khi xác minh:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
```

Đây là snippet với `publicKey`, `messageBytes`, `signatureBytes` đã được chuẩn bị; các thao tác có checked exceptions và được trình bày thành chương trình runnable ở phần 6.

### Public key có thể công khai, nhưng không thể tin mù quáng

Bên xác minh **không cần giữ bí mật public key**, nhưng phải chắc chắn public key nhận được là **khóa đúng đã được tin cậy**. Nếu kẻ tấn công được phép tự thay cả **public key** lẫn **signature**, họ có thể tạo một cặp khóa của riêng mình rồi gửi chữ ký hợp lệ theo chính khóa giả đó.

Ví dụ:

- Hệ thống A ký một thông báo bằng private key của A.
- Hệ thống B biết public key **đã được xác thực** của A và dùng để kiểm tra.
- Nếu kẻ tấn công thay public key của A bằng public key của chính mình và ký lại nội dung, phép xác minh toán học **sẽ hợp lệ đối với public key giả**. Nhưng đó **không chứng minh** thông báo đến từ A.

Vì vậy cần gắn public key với danh tính/ủy quyền bằng một cơ chế tin cậy thích hợp: cấu hình có kiểm soát, certificate/PKI khi phù hợp, key pinning, khóa được phân phối qua kênh đã xác thực, hoặc một hệ thống quản lý danh tính đáng tin cậy.

**Kết luận:** `verify(...) == true` chỉ là một điều kiện **xác minh mật mã**. Để đưa ra quyết định nghiệp vụ (cho phép giao dịch, cập nhật tài khoản, chấp thuận lệnh), hệ thống còn phải kiểm tra **chủ thể được ủy quyền, phạm vi quyền, hiệu lực của khóa và chính sách giao dịch**.

### Đổi public key khi private key thay đổi

Mỗi cặp khóa gồm hai thành phần liên kết với nhau. Chữ ký tạo bằng private key mới **không** được public key cũ xác minh, trừ trường hợp không thực tế là chúng biểu diễn cùng cặp khóa.

Khi xoay vòng khóa:

1. Tạo cặp khóa mới an toàn.
2. Đưa public key mới vào hệ thống tin cậy bằng kênh xác thực.
3. Quy định thời điểm dùng private key mới để ký.
4. Giữ/thu hồi public key cũ theo chính sách xác minh chữ ký lịch sử.
5. Định nghĩa cách gắn **key identifier**/phiên bản khóa với thông điệp và cách chống thay thế key ID.

Public key nên được quản lý theo **danh tính và phiên bản**. Đừng chỉ để hệ thống tự động lấy public key bất kỳ từ gói dữ liệu vừa nhận rồi coi nó là đáng tin.

## 4. Message: dãy byte chính xác là thành phần được ký

Trong Java, `Signature.update(...)` nhận **byte[]** hoặc dữ liệu nhị phân qua overload khác, **không** tự nhận một đối tượng `String` để quyết định cách mã hóa. Nếu thông điệp là văn bản, chương trình phải tự chọn encoding.

Ví dụ phổ biến:

```java
byte[] messageBytes =
        "order=314;amount=100000;currency=VND"
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

- Người ký cung cấp **đúng các bytes này** cho `update(...)`.
- Người xác minh phải cung cấp **cùng dãy byte**, theo cùng thứ tự.
- Nếu một byte trong message thay đổi, chữ ký hợp lệ cho message ban đầu sẽ **không còn hợp lệ** cho message mới.
- Signature được truyền **kèm theo hoặc bên cạnh** message; chữ ký **không thay thế message** hay cho phép người nhận khôi phục nội dung đã ký.

### Vì sao dùng UTF-8 rõ ràng?

`String.getBytes()` không truyền charset sẽ sử dụng charset mặc định; dữ liệu gửi qua mạng hoặc lưu tệp có thể gây nhầm lẫn khi bên ký và bên xác minh không dùng cùng biểu diễn. Hãy dùng `StandardCharsets.UTF_8` hoặc một serialization/encoding được giao thức quy định.

Các chuỗi trông giống nhau có thể có **bytes khác nhau**:

- `"\n"` (LF) khác `"\r\n"` (CRLF).
- `"A B"` khác `"A  B"` (hai spaces).
- Một chữ Unicode có dấu có thể biểu diễn bằng composed hoặc decomposed code points.
- JSON với thứ tự thuộc tính khác hoặc whitespace khác có thể khác bytes dù cùng ý nghĩa cấu trúc.

Nếu giao thức quy định **canonicalization**, hai phía phải sử dụng **cùng quy tắc chuẩn hóa và serialization chính thức trước khi ký và trước khi xác minh**. Không tự tiện gọi `strip()`, thay newline hoặc đổi trường JSON chỉ để làm chữ ký hợp lệ: việc đó có thể thay đổi nội dung hợp đồng hoặc tạo lỗ hổng ngữ nghĩa.

### Message không nhất thiết là bí mật

EdDSA tạo **chữ ký số**, không mã hóa message. Nội dung được ký có thể là văn bản công khai hoặc riêng tư tùy ứng dụng, nhưng **chữ ký tự nó không bảo mật nội dung**.

Nếu cần bí mật nội dung khi truyền, dùng cơ chế bảo mật phù hợp (ví dụ TLS khi truyền qua mạng; mã hóa lưu trữ nếu cần). Nếu cần cả tính toàn vẹn và bảo mật, phải thiết kế cả **xác minh chữ ký** và **bảo mật kênh/dữ liệu** theo mô hình đe dọa.

## 5. EdDSA, Ed25519, Ed448 và API chữ ký của Java

**EdDSA** là tên họ thuật toán. **Ed25519** và **Ed448** là hai biến thể phổ biến dựa trên các đường cong/param tương ứng theo RFC 8032.

| Thành phần | Ed25519 | Ed448 |
| --- | --- | --- |
| Thuộc họ EdDSA | Có | Có |
| Tên `KeyPairGenerator`/`Signature` dùng rõ biến thể | `"Ed25519"` | `"Ed448"` |
| Độ dài chữ ký chuẩn | **64 bytes** | **114 bytes** |
| Dùng khóa hai biến thể thay lẫn nhau | Không | Không |
| Vai trò private/public/message | Ký bằng private, xác minh bằng public trên cùng message bytes | Tương tự |
| Trạng thái ở Java | API chính thức được giới thiệu trong Java 15, vẫn được các JDK hiện đại hỗ trợ theo provider | Tương tự |

Trong bài thực hành, dùng **tên `"Ed25519"` cụ thể** ở cả `KeyPairGenerator`, `Signature` và `KeyFactory`. Tên `"EdDSA"` cũng nằm trong danh sách tên thuật toán chuẩn của Java; việc chọn thuật toán family mà không chỉ rõ tham số có thể khiến ứng dụng phụ thuộc cấu hình mặc định của provider. Với ví dụ học tập và giao thức có hợp đồng rõ, ghi **đúng biến thể** là lựa chọn minh bạch.

Các lớp `java.security` liên quan:

- `KeyPairGenerator`: tạo cặp khóa.
- `KeyPair`: giữ tham chiếu đến `PrivateKey` và `PublicKey`.
- `Signature`: hỗ trợ chuỗi thao tác `initSign → update → sign` hoặc `initVerify → update → verify`.
- `KeyFactory` và `X509EncodedKeySpec`: tái tạo một public key có dạng encoded chuẩn từ thông tin được chuyển qua hệ thống, khi provider hỗ trợ.
- `Base64`: chỉ **mã hóa biểu diễn** bytes thành ký tự có thể truyền, **không phải** mã hóa bảo mật và không phải chữ ký.

### Vòng đời của một đối tượng `Signature`

**Bên ký**:

```text
Signature.getInstance("Ed25519")
     → initSign(privateKey)
     → update(messageBytes)
     → sign()
     → signatureBytes
```

**Bên xác minh**:

```text
Signature.getInstance("Ed25519")
     → initVerify(publicKey)
     → update(theSameMessageBytes)
     → verify(signatureBytes)
     → true hoặc false
```

Cả `sign()` và `verify()` đều xử lý dữ liệu được cung cấp qua `update(...)` từ sau lần khởi tạo thích hợp. Đừng nhầm việc gọi `sign()` với việc gọi `verify()`; chúng dùng **khóa khác nhau** và cho **kiểu kết quả khác nhau**.

`sign()` trả `byte[]`. `verify(...)` trả `boolean` khi chữ ký được phân tích và kiểm tra bình thường, nhưng có thể ném `SignatureException` nếu bytes chữ ký không đúng định dạng hoặc bộ máy chữ ký không thể xử lý đầu vào.

## 6. Chương trình Java hoàn chỉnh: ba yếu tố trong một lần ký

Tạo tệp **`EdDsaRolesDemo.java`**. Ví dụ không in private key, public key hoặc signature ngẫu nhiên; chỉ in các thuộc tính xác định để có thể kiểm tra stdout ổn định.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Arrays;

public class EdDsaRolesDemo {
    private static final String ALGORITHM = "Ed25519";

    private static byte[] sign(PrivateKey privateKey, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance(ALGORITHM);
        signer.initSign(privateKey);
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(
            PublicKey publicKey, byte[] message, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(ALGORITHM);
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance(ALGORITHM);
        KeyPair owner = generator.generateKeyPair();
        KeyPair other = generator.generateKeyPair();

        byte[] message = "invoice=314;amount=100000;currency=VND"
                .getBytes(StandardCharsets.UTF_8);

        // Chỉ thay đổi giá trị amount, giữ nguyên các phần khác.
        byte[] changed = "invoice=314;amount=900000;currency=VND"
                .getBytes(StandardCharsets.UTF_8);

        byte[] signature = sign(owner.getPrivate(), message);

        System.out.println("privateKey.present="
                + (owner.getPrivate() != null));
        System.out.println("publicKey.present="
                + (owner.getPublic() != null));
        System.out.println("original.valid="
                + verify(owner.getPublic(), message, signature));
        System.out.println("changed.valid="
                + verify(owner.getPublic(), changed, signature));
        System.out.println("otherPublic.valid="
                + verify(other.getPublic(), message, signature));
        System.out.println("repeat.equal="
                + Arrays.equals(signature,
                        sign(owner.getPrivate(), message)));
        System.out.println("signature.length=" + signature.length);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 EdDsaRolesDemo.java
java EdDsaRolesDemo
```

**Stdout:**

```text
privateKey.present=true
publicKey.present=true
original.valid=true
changed.valid=false
otherPublic.valid=false
repeat.equal=true
signature.length=64
```

Giải thích từng kết quả:

1. `privateKey.present=true`: generator đã tạo private key để ký. Chương trình **không tiết lộ nội dung khóa**.
2. `publicKey.present=true`: public key tương ứng được tạo cùng cặp.
3. `original.valid=true`: signature do `owner.getPrivate()` tạo cho `message` được `owner.getPublic()` xác minh trên **đúng message bytes**.
4. `changed.valid=false`: giá trị amount thay đổi, nên chữ ký cho message cũ **không khớp** message mới.
5. `otherPublic.valid=false`: public key thuộc **cặp khóa khác** không xác minh được chữ ký của private key gốc.
6. `repeat.equal=true`: Ed25519 theo RFC 8032 tạo chữ ký **deterministic** cho cùng private key và cùng bytes message; ký lại cùng nội dung cho cùng bytes signature.
7. `signature.length=64`: chữ ký Ed25519 chuẩn có 64 bytes. **Không** nhầm độ dài này với độ dài dữ liệu public key được encode theo X.509 hoặc private key theo PKCS#8.

Do cặp khóa được tạo mới mỗi lần chạy, **bytes của khóa và chữ ký thay đổi giữa các lần chạy**, nhưng các phép kiểm tra trên có kết quả dự kiến như đã in. Mẫu không in bytes khóa/chữ ký để tránh nhầm lẫn và tránh tiết lộ thông tin nhạy cảm trong log.

### Vì sao test này chứng minh đúng vai trò ba thành phần?

| Thử nghiệm | Private key ký | Public key xác minh | Message xác minh | Kết quả |
| --- | --- | --- | --- | --- |
| Đúng cặp khóa, đúng message | Owner | Owner | Message gốc | `true` |
| Đúng cặp khóa, message bị sửa | Owner | Owner | Message đã đổi amount | `false` |
| Public key không khớp | Owner | Other | Message gốc | `false` |
| Ký lại cùng message | Owner | Owner | Message gốc | Signature giống về bytes theo Ed25519 |

Như vậy có thể tách bạch: **private key quyết định khả năng ký**, **public key quyết định khóa xác minh**, và **message bytes quyết định nội dung được bảo vệ**.

## 7. Truyền public key và signature giữa hai hệ thống

Trong ứng dụng thật, người ký có thể gửi:

- **Thông điệp** dưới dạng bytes hoặc một biểu diễn đã định nghĩa chính xác.
- **Signature** dưới dạng bytes hoặc Base64 (mã hóa để vận chuyển).
- **Key ID** hoặc thông tin tham chiếu để verifier chọn **public key đáng tin cậy** tương ứng.

Thông thường không gửi private key. Public key có thể được công bố qua một kênh đáng tin hoặc gắn với chứng chỉ. Nếu giao thức cho phép gửi public key trong cùng payload, verifier vẫn phải **xác minh tính đáng tin** của nó từ một nguồn độc lập.

### Chương trình minh họa encode/decode public key

Với các provider hỗ trợ xuất public key thông thường (như provider Ed25519 có sẵn trong OpenJDK), `getEncoded()` thường trả định dạng **X.509 SubjectPublicKeyInfo (SPKI)**. Đây **không** phải mảng 32 bytes “raw Ed25519 public key” của một giao thức khác. Dùng `X509EncodedKeySpec` để nhập lại đúng định dạng.

Tạo **`EdDsaTransportDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

public class EdDsaTransportDemo {
    private static boolean verify(
            PublicKey key, byte[] data, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPair pair =
                KeyPairGenerator.getInstance("Ed25519").generateKeyPair();

        byte[] message = "CONTRACT-V1\nid=42\namount=100\n"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        // Mã hóa biểu diễn để có thể chuyển qua kênh dạng text.
        String publicB64 = Base64.getEncoder()
                .encodeToString(pair.getPublic().getEncoded());
        String signatureB64 = Base64.getEncoder()
                .encodeToString(signature);

        // Bên nhận giải Base64 và dựng lại public key dạng SPKI.
        byte[] receivedPublic = Base64.getDecoder().decode(publicB64);
        byte[] receivedSignature =
                Base64.getDecoder().decode(signatureB64);

        PublicKey trustedPublic = KeyFactory.getInstance("Ed25519")
                .generatePublic(new X509EncodedKeySpec(receivedPublic));

        System.out.println("imported.valid="
                + verify(trustedPublic, message, receivedSignature));

        byte[] changed = "CONTRACT-V1\nid=42\namount=200\n"
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("changed.valid="
                + verify(trustedPublic, changed, receivedSignature));

        System.out.println("signature.length="
                + receivedSignature.length);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 EdDsaTransportDemo.java
java EdDsaTransportDemo
```

**Stdout:**

```text
imported.valid=true
changed.valid=false
signature.length=64
```

**Giới hạn của ví dụ:** biến `trustedPublic` trong chương trình được đặt tên để minh họa cách gọi API, nhưng dữ liệu thực tế vừa được truyền qua một đường vòng nội bộ; ví dụ **chưa triển khai quy trình xác thực danh tính của bên gửi**. Trong hệ thống thật, phải xác minh public key từ kênh hoặc kho tin cậy **trước khi** dùng nó để quyết định chấp nhận thông điệp.

Nếu provider cấp public key không thể xuất mã hóa (`getEncoded() == null`), luồng SPKI trong ví dụ không áp dụng nguyên xi; cần dùng API/provider hoặc dịch vụ xác minh được hỗ trợ. Không ép một khóa không xuất được thành bytes bằng cách dùng API nội bộ.

**Base64 không phải chữ ký hoặc mã hóa bảo mật.** Nó chỉ giúp chuyển `byte[]` qua JSON/text; ai có chuỗi Base64 cũng có thể giải nó trở lại thành bytes.

## 8. Kết quả `verify()` nói điều gì — và không nói điều gì?

Khi `Signature.verify(signatureBytes)` trả `true`, phép toán mật mã đã chứng minh rằng **signature hợp lệ đối với message bytes đang kiểm tra và public key đã cung cấp**, trong phạm vi thuật toán/provider được dùng.

Chữ ký hỗ trợ:

- **Integrity (tính toàn vẹn):** các bytes được xác minh là những bytes đã được ký, dưới giả định thuật toán an toàn và private key không bị lộ.
- **Origin authentication (xác thực nguồn theo khóa):** chữ ký phù hợp với cặp khóa của public key được chọn. Muốn gắn nó với cá nhân/tổ chức, cần xác thực quan hệ public key → chủ thể.
- **Chống giả mạo chữ ký:** người không có private key không thể thực tế tạo chữ ký hợp lệ cho dữ liệu tùy ý với xác suất đáng kể khi thuật toán được dùng đúng.

Nhưng chữ ký **không tự bảo đảm**:

- **Bí mật nội dung:** chữ ký không mã hóa message.
- **Freshness (tính mới):** một message có chữ ký hợp lệ của hôm qua **có thể bị phát lại** hôm nay.
- **Authorization (ủy quyền):** một public key thuộc về A không có nghĩa A có quyền thực hiện mọi thao tác.
- **Định danh tin cậy:** bất kỳ ai cũng có thể tạo một cặp khóa mới; phải có trust binding.
- **Hợp lệ nghiệp vụ:** chữ ký hợp lệ không xác nhận số tiền, hạn mức hoặc quy tắc đặt hàng là hợp pháp.

### Ví dụ về replay attack

Giả sử một lệnh `"chuyển 100000 VND"` được ký hợp lệ. Kẻ quan sát có thể gửi lại **chính message và signature** để yêu cầu xử lý lần thứ hai. Phép `verify` vẫn có thể trả `true`, vì bytes và public key **không đổi**.

Để hạn chế phát lại, ứng dụng cần ký **các trường ràng buộc với yêu cầu**: message ID/nonce, timestamp/expiry, loại thao tác, đối tượng nhận, số tiền; rồi **kiểm tra và ghi nhận nonce/message ID đã dùng** theo chính sách. Chỉ đưa timestamp vào dữ liệu ký mà **không kiểm tra** hạn sử dụng hoặc trùng lặp vẫn chưa giải quyết replay.

### Ngữ cảnh miền ứng dụng

Nếu cùng một khóa ký nhiều loại thông điệp, dùng định dạng message có **nhãn giao thức và phiên bản** trong phần bytes được ký, ví dụ:

```text
PAYMENT_APPROVAL_V1
transactionId=314
amount=100000
currency=VND
```

Đây là văn bản minh họa giao thức, không phải quy tắc canonicalization đủ an toàn cho mọi đầu vào. Khi đưa dữ liệu không đáng tin vào message, dùng serialization được định nghĩa chặt chẽ (độ dài trường, escape, thứ tự trường, version, charset) để tránh việc hai cấu trúc khác nhau tạo ra cùng dãy bytes hoặc một văn bản bị diễn giải theo nhiều cách.

## 9. Phân biệt EdDSA với encryption, HMAC và hashing

| Cơ chế | Khóa sử dụng | Mục tiêu chính | Cần nhớ |
| --- | --- | --- | --- |
| **EdDSA digital signature** | Private key để ký; public key để xác minh | Xác minh chữ ký của message và nguồn theo khóa | Có thể đưa public key cho nhiều verifier |
| **Symmetric MAC/HMAC** | **Cùng secret key** dùng để tạo và xác minh MAC | Xác thực thông điệp giữa các bên cùng giữ secret | Verifier có secret cũng có thể tạo MAC mới, khác mô hình private/public |
| **Hash/digest** | Không cần secret key trong phép băm thông thường | Tạo giá trị tóm lược dữ liệu | Chỉ hash message không chứng minh ai tạo ra nó |
| **Encryption** | Khóa mã hóa/giải mã theo cơ chế tương ứng | Bảo mật nội dung dữ liệu | Không được đồng nhất “encrypt bằng private key” với quy trình ký EdDSA |

EdDSA không phải mã hóa dữ liệu bằng private key để người nhận “giải mã bằng public key”. Đó là mô tả không chính xác của cơ chế chữ ký Ed25519.

**Không tự pre-hash message** rồi ký digest bằng `Signature.getInstance("Ed25519")` để cho rằng đó là chế độ `Ed25519ph`. Thuật toán prehash là một biến thể được quy định riêng trong RFC 8032; việc đưa `SHA-512(message)` vào `update(...)` của chữ ký `Ed25519` thông thường chỉ làm bạn ký **bytes của digest như một message khác**, không tự chuyển thuật toán thành Ed25519ph.

Đối với mục tiêu bài này, hãy ký **đúng bytes của message theo giao thức** bằng `Ed25519`, và dùng API/provider có hợp đồng tường minh nếu giao thức đòi một biến thể khác.

## 10. Các lỗi phổ biến trong mã Java

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `verify` luôn `false` | Bên ký và verifier dùng message bytes khác, kể cả newline cuối | Đặc tả encoding/serialization; so sánh bytes trước khi gọi API |
| `verify` `false` với message không đổi | Public key lấy từ cặp **khác** hoặc signature bị biến đổi | Quản lý key ID, lấy khóa tin cậy đúng phiên bản, kiểm tra bước Base64 |
| `InvalidKeyException` khi `initSign`/`initVerify` | Đưa sai loại khóa hoặc khóa không tương thích với thuật toán/provider | Dùng private key khi ký, public key khi verify; khớp Ed25519/Ed448 |
| `NoSuchAlgorithmException` | Provider hiện có không cung cấp thuật toán yêu cầu | Kiểm tra JDK/provider đang chạy, chọn provider hiện hành hỗ trợ EdDSA |
| `SignatureException` | Signature không đúng format, đối tượng `Signature` sai trạng thái hoặc không xử lý được dữ liệu | Kiểm tra phương thức `init...`, `update`, signature bytes và loại thuật toán |
| Bytes thay đổi khi qua JSON | Serializer đổi newline, escape, thứ tự trường hoặc Unicode | Ký một định dạng byte canonical đã được hợp đồng quy định |
| Cho rằng ai cũng có thể thay public key | Không xác thực nguồn của khóa công khai | Phân phối/ghim public key bằng kênh tin cậy; không lấy tùy ý từ request |
| Gửi private key kèm signature | Hiểu nhầm verifier cần private key | Chỉ truyền message, signature và tham chiếu/public key đáng tin |
| Tưởng `verify=true` nghĩa là được phép xử lý | Đánh đồng xác thực chữ ký với authorization | Kiểm tra quyền, thời hạn, nonce, trạng thái tài khoản và chính sách |
| Tưởng signature là message đã mã hóa | Nhầm chữ ký với mã hóa | Gửi/giữ message theo giao thức; dùng TLS/encryption riêng khi cần |
| Tự đặt seed cố định khi tạo keypair thực | Làm private key dễ đoán hoặc tái tạo | Dùng cơ chế sinh khóa an toàn của provider |
| Muốn ép mọi private key sang bytes | HSM/provider có thể không cho xuất khóa | Dùng API ký của key provider, giữ khóa trong kho được quản lý |
| Ký thông điệp văn bản trên một JVM rồi verify JVM khác thất bại | Charset hoặc cách chuẩn hóa khác nhau | Chốt charset UTF-8 và serialization versioned |
| Tạo Ed448 key nhưng tạo `Signature("Ed25519")` | Không cùng biến thể thuật toán | Dùng tên thuật toán cụ thể đồng nhất |

### Ngoại lệ có ý nghĩa khác với chữ ký không hợp lệ

Hai kết quả không giống nhau:

- `verify(...) == false`: signature **không hợp lệ** đối với key và message được cung cấp, trong lần kiểm tra đã chạy bình thường.
- Một ngoại lệ như `SignatureException` hoặc `InvalidKeyException`: có vấn đề về **định dạng/điều kiện đầu vào/trạng thái**, cần xử lý và ghi nhận riêng.

Không bắt mọi ngoại lệ rồi trả `true` hoặc im lặng chấp nhận yêu cầu. Trong hệ thống xác thực, mặc định nên **từ chối xử lý** khi verify không thành công hoặc gặp lỗi, đồng thời tạo log chẩn đoán không chứa private key hay dữ liệu nhạy cảm.

## 11. Quy trình triển khai an toàn cho ký/xác minh

### Bên ký

1. Xác định **mục đích** của chữ ký và schema/serialization version.
2. Xác định danh tính chủ sở hữu và **private key đúng** đang còn hiệu lực.
3. Chuẩn hóa/serialize dữ liệu thành **dãy bytes có nghĩa rõ ràng**, bao gồm loại hành động, ID, giá trị, hạn hiệu lực/nonce nếu nghiệp vụ cần.
4. Dùng `Signature.getInstance("Ed25519")`, `initSign(privateKey)`, `update(messageBytes)`, `sign()`.
5. Gửi message, signature (có thể Base64) và key ID/tham chiếu khóa. Không tiết lộ private key.
6. Ghi log mã giao dịch, thuật toán, key ID, trạng thái ký, nhưng **không log private key**.

### Bên xác minh

1. Giải mã message/signature từ giao thức theo đúng format quy định; kiểm tra giới hạn độ dài trước khi xử lý.
2. Chọn **public key đáng tin cậy** theo danh tính/key ID đã được xác thực; kiểm tra hiệu lực/thu hồi.
3. Dùng đúng thuật toán `Ed25519` tương ứng, `initVerify(publicKey)`, `update(messageBytes)`, `verify(signatureBytes)`.
4. Nếu `false` hoặc ngoại lệ: **từ chối** và phân biệt lỗi để chẩn đoán.
5. Nếu `true`: vẫn kiểm tra **authorization**, điều kiện nghiệp vụ, timestamp/expiry, nonce, replay protection và phạm vi sử dụng khóa.
6. Chỉ khi mọi điều kiện đều đạt mới xử lý giao dịch hoặc tác vụ.

### Ví dụ logic ứng dụng (pseudocode)

```text
publicKey = trustedKeyStore.findById(request.keyId)
if publicKey not trusted or revoked:
    reject

messageBytes = canonicalSerializer.encode(request.signedFields)
if !Ed25519.verify(publicKey, messageBytes, request.signature):
    reject

if request.expired or nonceAlreadyUsed(request.nonce):
    reject

if !authorizationPolicy.allows(request.identity, request.action):
    reject

markNonceAsUsedAtomically(request.nonce)
performAuthorizedOperation()
```

Đây là **pseudocode**, không phải Java compilable. Thứ tự và tính nguyên tử của bước chống replay phụ thuộc mô hình giao dịch; với hệ thống đồng thời, không được tách kiểm tra “nonce chưa dùng” và ghi nhận trạng thái thành hai bước không được đồng bộ, vì hai yêu cầu song song có thể vượt qua kiểm tra.

Chữ ký hợp lệ **là cần thiết** cho giao thức đã chọn, nhưng không thay thế quy trình kiểm tra tin cậy/ủy quyền.

## 12. Bài tập tự kiểm tra và đáp án

**Bài 1.** Bạn ký bytes của chuỗi `"A\nB"` bằng private key K. Người nhận dùng đúng public key nhưng xác minh `"A\r\nB"`. Kết quả mong đợi?

**Đáp án:** `false` vì hai dãy bytes khác nhau. Phải thống nhất biểu diễn trước khi ký và verify nếu giao thức cho phép chuẩn hóa.

**Bài 2.** Chỉ có public key và message, có thể tạo chữ ký Ed25519 hợp lệ không?

**Đáp án:** Không theo giả định an toàn của thuật toán. Private key cần thiết để tạo chữ ký; public key được dùng để xác minh.

**Bài 3.** Hai người tạo hai cặp Ed25519 khác nhau. Public key người thứ hai có thể xác minh chữ ký do private key người thứ nhất tạo cho một message cố định không?

**Đáp án:** Không trong trường hợp đúng chuẩn thông thường. Phép thử với wrong public key trong chương 6 minh họa `false`.

**Bài 4.** Vì sao bên nhận không được tin public key nằm sẵn trong một request chưa được xác thực?

**Đáp án:** Kẻ gửi có thể tự tạo cặp khóa, ký message và đưa public key của mình vào request. Verify sẽ hợp lệ với khóa ấy nhưng không chứng minh người gửi là chủ thể đã đăng ký/được ủy quyền.

**Bài 5.** `Signature.sign()` trả gì và `Signature.verify(...)` trả gì?

**Đáp án:** `sign()` trả `byte[]` chữ ký. `verify(...)` trả `boolean` khi kiểm tra hoàn tất bình thường, có thể ném checked exception cho dữ liệu/trạng thái không hợp lệ.

**Bài 6.** Chữ ký Ed25519 có giữ kín số tiền của một giao dịch không?

**Đáp án:** Không. Chữ ký bảo vệ tính toàn vẹn và xác thực theo khóa, **không mã hóa message**. Cần bảo mật kênh/dữ liệu riêng khi cần bí mật.

**Bài 7.** Ký lại cùng message bằng cùng private key Ed25519 có cần một nonce ngẫu nhiên mới của thuật toán chữ ký không?

**Đáp án:** Ed25519 chuẩn của RFC 8032 sử dụng quy trình ký xác định cho cùng private key và message; không cần tự cấp nonce ngẫu nhiên mới cho phép ký đó. Nhưng **nonce giao dịch chống replay** là khái niệm khác và có thể vẫn cần trong **message nghiệp vụ**.

**Bài 8.** Nếu message được gửi ở dạng Base64, có nên ký các ký tự Base64 hay bytes đã giải mã?

**Đáp án:** Phụ thuộc **hợp đồng giao thức**. Phải quy định rõ cái gì là message bytes được ký và dùng **cùng lựa chọn** khi xác minh. Không tự ý thay đổi giữa dạng text Base64 và bytes gốc.

**Bài 9.** Khi cần hỗ trợ Ed448, có thể giữ `Signature.getInstance("Ed25519")` và chỉ đổi tên file khóa không?

**Đáp án:** Không. Phải dùng thuật toán/khóa cùng biến thể, ví dụ `KeyPairGenerator.getInstance("Ed448")` và `Signature.getInstance("Ed448")` với provider hỗ trợ.

**Bài 10.** Vì sao `verify(...) == true` chưa đủ để thực hiện giao dịch thanh toán?

**Đáp án:** Còn cần xác thực public key thuộc đúng chủ thể, kiểm tra hiệu lực khóa, ủy quyền thực hiện giao dịch, hợp lệ nghiệp vụ và chống phát lại.

### Checklist

- [ ] Tôi phân biệt **private key ký** và **public key xác minh**, không trao private key cho verifier.
- [ ] Tôi hiểu message là **bytes chính xác**, không chỉ là văn bản “trông giống nhau”.
- [ ] Tôi hiểu signature được tạo từ private key + message và kiểm tra bằng public key + cùng message.
- [ ] Tôi dùng `KeyPairGenerator`, `Signature.initSign`, `update`, `sign`, `initVerify` và `verify` đúng thứ tự.
- [ ] Tôi hiểu sự khác nhau giữa EdDSA, Ed25519 và Ed448; không trộn hai biến thể.
- [ ] Tôi biết `verify=true` chỉ chứng minh theo public key đã chọn, cần trust binding với danh tính.
- [ ] Tôi không nhầm chữ ký với mã hóa, HMAC hoặc phép hash dữ liệu.
- [ ] Tôi chủ động chọn UTF-8 và chuẩn biểu diễn thông điệp xuyên hệ thống.
- [ ] Tôi không tiết lộ private key, không nhầm Base64 với bảo mật.
- [ ] Tôi có cơ chế kiểm tra key ID, quyền hạn, thời gian và chống replay khi nghiệp vụ yêu cầu.
- [ ] Tôi phân biệt chữ ký sai (`false`) với đầu vào không hợp lệ (exception).
- [ ] Tôi có thể biên dịch, chạy hai chương trình Java và giải thích stdout.

## Tài liệu chính thức và còn áp dụng

1. [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): EdDSA được đưa vào Java 15, các API và biến thể thuật toán.
2. [Java SE 25 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên chuẩn `EdDSA`, `Ed25519`, `Ed448` cho `Signature`, `KeyPairGenerator` và `KeyFactory`.
3. [Java SE 25 — `Signature`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign`, `verify`, trạng thái và ngoại lệ.
4. [Java SE 25 — `KeyPairGenerator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyPairGenerator.html): sinh cặp khóa bằng provider.
5. [Java SE 25 — `KeyFactory`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyFactory.html) và [`X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): biểu diễn/import public key chuẩn.
6. [Java SE 25 — `EdECPrivateKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html): biểu diễn khóa riêng và điều kiện có thể không xuất được vật liệu khóa.
7. [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032): quy tắc Ed25519/Ed448, dữ liệu được ký và độ dài chữ ký.

**Ghi nhớ:** **Private key** tạo chữ ký và phải giữ bí mật; **public key** kiểm tra chữ ký nhưng phải được ràng buộc với chủ thể đáng tin; **message** là **chính xác bytes được bảo vệ**. Chữ ký số EdDSA xác minh sự phù hợp của ba yếu tố ấy, **không** tự mã hóa dữ liệu, chống replay hoặc trao quyền thực hiện mọi hành động.