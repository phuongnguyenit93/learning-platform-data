# 9.1. Chữ ký số bảo vệ tính toàn vẹn và xác thực nguồn dữ liệu như thế nào?

## 1. Bài toán: biết dữ liệu có bị sửa và có đến từ đúng nguồn không?

Giả sử hệ thống A gửi cho hệ thống B một yêu cầu thanh toán: `order=42;amount=120000`. B cần phân biệt ba câu hỏi:

1. **Tính toàn vẹn (integrity):** các byte dữ liệu có bị thay đổi sau khi người ký tạo chữ ký không?
2. **Tính xác thực nguồn (source authentication):** chữ ký có được tạo bởi bên nắm giữ **khóa riêng tương ứng với khóa công khai đáng tin cậy** hay không?
3. **Tính bí mật (confidentiality):** người không được phép có đọc được nội dung trên đường truyền không?

**Chữ ký số** giải quyết hai câu hỏi đầu **trong các điều kiện mật mã và tin cậy phù hợp**. Nó không tự mã hóa hoặc che giấu thông điệp. Muốn dữ liệu được giữ bí mật, sử dụng TLS, mã hóa dữ liệu phù hợp hoặc cơ chế bảo mật kênh/lưu trữ khác.

Sự phân biệt quan trọng: **xác minh toán học chữ ký hợp lệ** không đồng nghĩa **đã biết người ký là ai**. Nếu kẻ tấn công tự sinh một cặp khóa, tự ký thông điệp và đưa luôn khóa công khai của mình cho người nhận, việc verify có thể trả `true`. Người nhận chỉ có bằng chứng “ai đó giữ private key đi cùng public key này đã ký”, chứ chưa có bằng chứng đó là đối tác A. Cần cơ chế **gắn public key với danh tính/đối tác được tin cậy**.

### Mục tiêu học tập

Sau bài này, bạn có thể giải thích luồng ký–xác minh, thực hiện ký/xác minh với JCA `Signature` trong Java 17+, phân biệt **integrity**, **source authentication**, **identity/trust**, **confidentiality**, chống phát lại và các giới hạn khác; biết vì sao phải ký **đúng chuỗi byte**, kiểm soát khóa công khai, thuật toán và ngữ cảnh ứng dụng.

## 2. Nguyên lý chữ ký số bất đối xứng

Chữ ký số hiện đại sử dụng một **cặp khóa bất đối xứng**:

- **Private key (khóa riêng):** do bên ký giữ bí mật và dùng khi tạo signature. Người nhận không cần biết khóa này.
- **Public key (khóa công khai):** dùng để kiểm tra chữ ký. Có thể công bố, nhưng **nguồn gốc và quyền sử dụng của nó phải được xác thực**.

Quá trình ở mức khái niệm:

```text
BÊN KÝ (được phép ký)                         BÊN NHẬN / XÁC MINH

Thông điệp M (byte chính xác)                Nhận M' + signature + keyId...
          |                                                |
          v                                                v
Signature.initSign(privateKey)               Tìm publicKey tin cậy của bên ký
Signature.update(M)                                         |
Signature.sign() -> chữ ký S                                v
          |                                   Signature.initVerify(publicKey)
          +---------- M + S ------------>    Signature.update(M')
                                              Signature.verify(S)
                                                         |
                                            true: chữ ký hợp lệ cho M' với key đó
                                            false/lỗi: từ chối, không tin dữ liệu
```

Trong các lược đồ như Ed25519, RSA-PSS hoặc ECDSA, thuật toán ký có **cơ chế băm/biểu diễn thông điệp** riêng được quy định trong thuật toán. Không nên tự nghĩ “chỉ cần SHA-256 rồi mã hóa digest bằng private key” là đủ để tự chế chữ ký số. Cần dùng thuật toán chữ ký được chuẩn hóa qua JCA, cùng tham số, encoding và policy ở cả hai phía.

Tại sao việc sửa dữ liệu bị phát hiện? Chữ ký được ràng buộc mật mã với **nội dung thông điệp** và **private key**. Khi kẻ tấn công sửa một byte của thông điệp được kiểm tra nhưng giữ nguyên chữ ký, phép `Signature.verify` với public key của bên ký hợp lệ sẽ thất bại, trừ khả năng phá vỡ giả định an toàn mật mã hoặc một lỗi trong triển khai/protocol.

**Không cần giữ thông điệp bí mật** để có chữ ký hợp lệ: trong nhiều ứng dụng thông điệp và chữ ký đều được gửi ở dạng rõ. Giá trị của chữ ký là khả năng phát hiện thay đổi và ràng buộc nguồn ký với một public key được xác thực.

## 3. “Bảo vệ tính toàn vẹn” nghĩa là gì?

### 3.1. Chữ ký ràng buộc các byte được ký

Nếu bên A ký byte sequence `M`, bên B kiểm tra đúng `M` với chữ ký `S` và public key tin cậy, kết quả hợp lệ chứng tỏ theo giả định mật mã rằng nội dung `M` chưa bị sửa kể từ khi chữ ký được tạo bởi người nắm khóa riêng.

Nếu B thay `M` bằng `M'` (khác một byte), chữ ký cũ thông thường không còn hợp lệ. Điều này áp dụng cho **từng byte**, không phải chỉ ý nghĩa ngôn ngữ. Ví dụ:

- `"amount=120000"` khác `"amount=120001"`.
- UTF-8 với dấu xuống dòng `LF` khác `CRLF`.
- Hai đối tượng JSON có cùng dữ liệu nhưng thứ tự trường khác nhau thường tạo byte array khác nhau.
- Unicode có thể biểu diễn các ký tự trông giống nhau bằng các chuỗi code point khác nhau.
- Base64 của cùng byte có thể có biến thể format; quy tắc ký **chuỗi Base64** khác quy tắc ký **byte đã decode**.

Do đó, ứng dụng phải định nghĩa **chính xác cái gì được ký**, chuyển đổi thế nào thành `byte[]` và bên nhận dựng lại byte để verify ra sao.

### 3.2. Chữ ký chỉ bảo vệ những trường thật sự nằm trong phạm vi ký

Giả sử thông điệp có các trường `amount`, `currency`, `tenantId` và `expiresAt`. Nếu bên ký chỉ ký `amount` mà không đưa các trường còn lại vào payload được ký, việc thay `tenantId` hoặc `expiresAt` **không nhất thiết làm chữ ký sai**.

Một thiết kế an toàn phải đưa vào phạm vi ký những trường ảnh hưởng tới **ý nghĩa nghiệp vụ**, định tuyến, quyền truy cập, đơn vị tiền, loại thao tác, phiên bản giao thức, thời hạn và định danh yêu cầu — theo định dạng byte rõ ràng.

**Lỗi nguy hiểm:** kiểm tra signature trên phần thân nhưng lại thực thi một số trường header hoặc query string **chưa được ký**, ví dụ chọn tài khoản nhận tiền bằng `accountId` ở URL không được ràng buộc với payload.

### 3.3. Chữ ký không chứng minh nội dung là đúng sự thật

Một tài liệu ký hợp lệ vẫn có thể chứa giá sai, thông tin gian dối hoặc lệnh mà người ký không có thẩm quyền đưa ra. `Signature.verify(...) == true` **không** là kiểm tra business rules, authorization, số dư, hạn mức, tính hợp lệ của hóa đơn hay đồng ý của người dùng.

Tính toàn vẹn ở đây nghĩa là nội dung **được đối chiếu chính xác với thứ đã ký**, chứ không phải “dữ liệu chắc chắn đúng về mặt thực tế”.

## 4. “Xác thực nguồn dữ liệu” được hiểu như thế nào?

### 4.1. Mật mã chứng minh liên hệ với khóa riêng

Với public key `K_pub`, việc chữ ký hợp lệ trên `M` cho thấy có một bên có khả năng sử dụng private key `K_priv` tương ứng đã tạo chữ ký (theo giả định lược đồ chữ ký an toàn). Không thể từ public key và signature hợp lệ suy ngược chắc chắn **tên người, tổ chức, chức danh hoặc sự cho phép hiện tại** của bên ký.

Phải phân biệt:

- **Cryptographic verification:** thuật toán xác minh byte `M`, chữ ký `S` và public key `K_pub` có hợp lệ không?
- **Key authenticity:** vì sao B tin `K_pub` thuộc về đối tác A chứ không phải khóa do kẻ tấn công gài?
- **Authorization:** khóa này được phép ký loại dữ liệu/tenant/hành động nào, trong giai đoạn nào?
- **Attribution/audit:** ai đã sử dụng private key, trong hoàn cảnh nào và có bằng chứng quản trị hỗ trợ hay không?

Thiếu bước **key authenticity**, kẻ tấn công có thể thực hiện *public-key substitution*: tự tạo khóa, tự ký, rồi thay khóa công khai được dùng để verify. Kết quả `true` chỉ xác thực chữ ký của **khóa giả**, không xác thực đối tác mong đợi.

### 4.2. Các cách gắn public key với nguồn đáng tin

Tùy hệ thống:

1. **Pinning/allowlist:** máy nhận lưu fingerprint hoặc public key của đối tác đã phân phối qua kênh tin cậy; chỉ sử dụng key đã đăng ký và chưa bị thu hồi.
2. **Chứng thư số X.509 (PKI):** chứng thư liên kết một public key với danh tính thuộc tính được xác nhận bởi tổ chức cấp chứng thư; bên xác minh phải kiểm tra **chuỗi chứng thư** tới trust anchor đáng tin, hiệu lực, chính sách, tên/định danh, mục đích sử dụng khóa và tình trạng thu hồi khi cần.
3. **Directory/JWKS được bảo vệ:** dùng nguồn public key có xác thực, TLS, cache/rotation và policy; không chấp nhận URL public key tùy ý từ request không tin cậy mà không kiểm tra miền và trust.
4. **HSM/KMS và quyền ký:** private key ở kho khóa được bảo vệ, quyền gọi sign được kiểm soát và ghi audit. Điều này giảm rủi ro lộ khóa và tăng bằng chứng quy trình, nhưng không biến mọi chữ ký hợp lệ thành ủy quyền vô điều kiện.

Trong Java, `X509Certificate.getPublicKey()` chỉ **trả public key**; bản thân lời gọi đó **không thực hiện đầy đủ xác thực trust path** cho chứng thư. Để tin vào danh tính trong môi trường PKI, cần dùng cơ chế xác minh chuỗi/đường chứng thư thích hợp như `CertPathValidator` với policy tin cậy đúng. Không tự xem “chứng thư parse được” là “chứng thư đáng tin”.

### 4.3. Khóa bị lộ và quyền sử dụng sai

Nếu private key bị đánh cắp hoặc bên không được phép được quyền gọi hệ thống ký, kẻ tấn công có thể tạo chữ ký hợp lệ. Phép `Signature.verify` không thể tự phát hiện key compromise. Cần quản lý vòng đời khóa, phân quyền, giám sát, rotation, thời hạn chứng thư, thu hồi khóa và quy trình ứng phó sự cố.

Vì vậy phát biểu chuẩn xác là: **chữ ký hợp lệ + public key được gắn đúng nguồn và được tin cậy theo policy + private key chưa bị xâm phạm** cho bằng chứng mạnh về tính toàn vẹn và nguồn ký. Không nên phát biểu “cứ verify trả true là chắc chắn do người X ký”.

## 5. Java 17+: tạo, ký và xác minh với Signature (Ed25519)

JCA cung cấp engine `java.security.Signature`. Trong ví dụ dùng `Ed25519` (thuộc họ EdDSA) vì cú pháp rõ ràng và được JDK hiện đại hỗ trợ; đây là thuật toán chữ ký, **không phải thuật toán mã hóa dữ liệu**.

Luồng API chuẩn:

- `KeyPairGenerator.getInstance("Ed25519")` và `generateKeyPair()` tạo cặp khóa phù hợp cho demo.
- `Signature.getInstance("Ed25519")` lấy engine theo thuật toán chữ ký.
- `initSign(privateKey)` thiết lập khóa riêng; `update(messageBytes)` nạp đúng byte đã định; `sign()` tạo chữ ký.
- `initVerify(publicKey)` thiết lập khóa công khai; `update(messageBytes)` nạp chính xác cùng byte; `verify(signatureBytes)` trả boolean hoặc ném lỗi cho trường hợp không hợp lệ ở mức API/provider.

**Lưu ý về engine state:** một `Signature` sau khi `initSign` đang ở chế độ ký; sau `initVerify` đang ở chế độ xác minh. Không dùng chung một instance mutable để ký/verify đồng thời ở nhiều thread, và không quên khởi tạo lại cho một thông điệp mới. API `update` cho phép nạp nhiều mảnh; thứ tự các mảnh phải giống hoàn toàn với byte được bên kia kiểm tra.

### 5.1. Chương trình độc lập: DigitalSignatureDemo.java

Ví dụ sinh keypair cho sender và một keypair **khác** để kiểm tra sai khóa. Bên ký tạo signature cho một chuỗi byte có tiền tố `app=orders;v=1;...`; bên nhận xác minh đúng, rồi thử sửa message, sửa signature và thay public key. Không in key hay signature thực tế.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public final class DigitalSignatureDemo {
    static byte[] sign(PrivateKey privateKey, byte[] message)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(PublicKey publicKey, byte[] message, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair sender = generator.generateKeyPair();
        KeyPair stranger = generator.generateKeyPair();

        byte[] message = "app=orders;v=1;order=42;amount=120000"
                .getBytes(StandardCharsets.UTF_8);
        byte[] signed = sign(sender.getPrivate(), message);
        byte[] changedMessage = message.clone();
        changedMessage[changedMessage.length - 1] ^= 1;

        byte[] changedSignature = signed.clone();
        changedSignature[changedSignature.length - 1] ^= 1;

        System.out.println("Signature length: " + signed.length + " bytes");
        System.out.println("Valid signature: " +
                verify(sender.getPublic(), message, signed));
        System.out.println("Modified message accepted: " +
                verify(sender.getPublic(), changedMessage, signed));
        System.out.println("Wrong public key accepted: " +
                verify(stranger.getPublic(), message, signed));
        System.out.println("Modified signature accepted: " +
                verify(sender.getPublic(), message, changedSignature));
        System.out.println("Same bytes again: " +
                verify(sender.getPublic(), message.clone(), signed));
    }
}
```

Biên dịch và chạy bằng JDK 17+ có provider hỗ trợ Ed25519:

```bash
javac DigitalSignatureDemo.java
java DigitalSignatureDemo
```

Stdout chính xác của ví dụ:

```text
Signature length: 64 bytes
Valid signature: true
Modified message accepted: false
Wrong public key accepted: false
Modified signature accepted: false
Same bytes again: true
```

### 5.2. Giải thích kết quả theo thuộc tính bảo mật

1. **Signature length: 64 bytes:** Ed25519 xuất chữ ký 64 byte theo định dạng thuật toán; đây là một đặc trưng riêng của Ed25519, **không** phải độ dài chữ ký của mọi thuật toán (ví dụ RSA-PSS phụ thuộc cỡ modulus).
2. **Valid signature: true:** message giữ nguyên; public key đúng cặp với private key ký; phép kiểm tra thành công. Trong ví dụ, public key được lấy trực tiếp từ `sender` nên **chưa mô phỏng vấn đề phân phối khóa tin cậy**.
3. **Modified message accepted: false:** chỉ thay byte cuối của message, không tạo chữ ký mới. Điều này minh họa liên kết chữ ký với **byte đã ký**.
4. **Wrong public key accepted: false:** chuyển sang public key của một keypair độc lập thì chữ ký không hợp lệ; chứng tỏ chữ ký phụ thuộc vào khóa tương ứng.
5. **Modified signature accepted: false:** thay một byte của signature mà giữ nguyên message/key cũng khiến kiểm tra thất bại trong ví dụ.
6. **Same bytes again: true:** tạo mảng mới bằng `message.clone()`, nội dung byte không đổi nên verify thành công. **Reference object** của array không ảnh hưởng; chữ ký bảo vệ nội dung byte.

Các biến `sender`/`stranger` được sinh ngẫu nhiên ở mỗi lần chạy nên byte khóa/signature sẽ khác, nhưng các dòng stdout về độ dài và kết quả boolean vẫn như trên. Chương trình cố ý đơn giản để hiểu **cơ chế ký và verify**, không phải ứng dụng production: không lưu khóa, không tạo/trust chứng thư, không truyền thông qua mạng và không tự giải quyết chống replay.

**Với signature hỏng định dạng**, tùy thuật toán/provider, `Signature.verify` có thể trả `false` **hoặc ném `SignatureException`. Không biến exception thành chấp nhận; lớp ứng dụng cần coi cả `false` lẫn lỗi xác minh/malformed input là không hợp lệ, xử lý/log theo chính sách mà không lộ thông tin nhạy cảm.

## 6. Vì sao băm dữ liệu rồi lưu SHA-256 là chưa đủ để xác thực nguồn?

Một phép hash như `SHA-256(message)` có thể phát hiện thay đổi **khi digest kỳ vọng đến từ nguồn được tin cậy và được bảo vệ**. Nhưng nếu kẻ tấn công có thể sửa cả message **và** digest đi kèm, họ tính lại SHA-256 mà không cần bí mật nào. Hash đơn lẻ không tạo bằng chứng về người gửi.

HMAC dùng **khóa bí mật chung**. Ai có khóa đều có thể tạo và xác minh HMAC; vì vậy HMAC phù hợp khi các bên cùng chia sẻ khóa, nhưng bên thứ ba không thể độc lập phân biệt bên nào trong nhóm cùng giữ khóa đã tạo tag.

Chữ ký số dùng **khóa riêng để ký** và **khóa công khai để xác minh**. Nhiều bên có thể xác minh mà không cần biết private key. Khi public key được liên kết với nguồn tin cậy và private key chỉ người ký có quyền dùng, chữ ký mang bằng chứng xác thực nguồn mạnh hơn mô hình shared-secret ở những hệ thống có nhiều bên xác minh.

| Thuộc tính | SHA-256 digest đơn lẻ | HMAC-SHA256 | Chữ ký Ed25519 / RSA-PSS / ECDSA |
| --- | --- | --- | --- |
| Có cần bí mật để tạo mã kiểm tra? | Không | Có, shared key | Có, private key |
| Bên xác minh cần gì? | Digest kỳ vọng đã đáng tin | Cùng khóa bí mật | Public key đáng tin |
| Phát hiện sửa dữ liệu nếu kiểm tra đúng? | Có khi digest kỳ vọng được bảo vệ | Có | Có |
| Xác thực nguồn như một bên giữ khóa? | Không | Có, trong nhóm chia sẻ secret | Có, bên có quyền dùng private key tương ứng |
| Bên xác minh có thể tự tạo mã hợp lệ? | Ai cũng tính digest được | Có, vì cùng giữ secret | **Không**, nếu chỉ có public key |
| Chứng minh danh tính bên ký mà không có trust binding? | Không | Không | **Không** |
| Mã hóa / che giấu nội dung? | Không | Không | Không |
| Chống replay tự động? | Không | Không | Không |

Không nhầm lẫn thuật ngữ: **digital signature** không có nghĩa là “mã hóa bằng private key rồi giải mã bằng public key”. Cách giải thích dân gian đó gây hiểu sai về padding, hash, thuật toán và mục tiêu an ninh. Luôn dùng API ký/xác minh chuẩn `Signature` và lược đồ được duyệt.

## 7. Thiết kế thông điệp ký: phải ký đúng byte và ngữ cảnh

### 7.1. Chọn định dạng byte có thể tái tạo chính xác

Bên ký và bên xác minh phải thống nhất:

- Encoding: dùng UTF-8 hoặc một định dạng nhị phân được quy định, **không** dựa vào charset mặc định.
- Thứ tự field và tên field; loại dữ liệu; quy tắc số (ví dụ `120000` khác `120000.0`); cách mã hóa timestamp/timezone.
- Quy tắc escaping, Unicode normalization, newline và padding; có/không whitespace.
- Version của serialization/canonicalization, và cách xử lý field không biết.
- Nếu dùng JSON/XML, phải ký **byte đã chuẩn hóa theo quy ước rõ ràng** hoặc ký **byte gốc đã nhận/lưu**, thay vì tùy tiện parse rồi tự xuất lại theo cách khác.
- Nếu truyền signature dưới dạng Base64, định nghĩa rõ **ký payload bytes** hay **ký chuỗi Base64 textual representation**; thông thường ký byte payload trước khi encode signature.

Đặc biệt, **nối field độ dài biến đổi không có ranh giới** tạo nguy cơ ambiguity: ký `"ab" + "c"` cho cùng byte như `"a" + "bc"` mặc dù hai cặp trường khác nhau. Dùng binary framing, length prefix, tag–length–value, hoặc canonical format để biểu diễn không mơ hồ.

### 7.2. Domain separation và scope của chữ ký

Nếu cùng một khóa được dùng ở nhiều ứng dụng/giao thức, chữ ký trên chuỗi `"approve=1"` có thể được kẻ tấn công **chuyển ngữ cảnh** sang quy trình khác cũng tin public key đó, nếu cả hai nơi cho thông điệp ký/verify giống byte và không kiểm tra mục đích.

Một cách phòng vệ là **gắn ngữ cảnh vào byte được ký**, ví dụ:

```text
applicationId = orders
schemaVersion = 1
operation = authorize-payment
tenantId = shop-7
orderId = 42
amountMinorUnits = 120000
currency = VND
expiresAt = 2026-12-01T00:00:00Z
requestId = unique-id
```

Đây là **mô tả các trường logic**, không phải byte serialization đã chuẩn hóa. Hãy định nghĩa format chính xác và ký toàn bộ phiên bản byte đã mã hóa. `app=orders;v=1` trong demo minh họa domain prefix, **không** phải sự thay thế cho một schema production có ranh giới trường, quyền, hạn mức và version chặt chẽ.

Dùng **khóa khác nhau theo mục đích** khi phù hợp, ví dụ tách khóa ký giao dịch khỏi khóa ký gói cập nhật; cả bên nhận và bên ký phải kiểm soát loại thao tác được phép thực hiện.

### 7.3. Ký file lớn hoặc dữ liệu dạng stream

`Signature.update(byte[])` có thể gọi nhiều lần với các chunk liên tiếp rồi `sign()` hoặc `verify(...)`. Khi cập nhật từng chunk, **thứ tự và toàn bộ byte** phải đúng như khi ký một lần. Tránh tự băm bên ngoài rồi lại yêu cầu `Ed25519` ký digest khi protocol thực tế quy định ký **message nguyên bản**: điều đó thay đổi nội dung được ký (và với Ed25519 không đồng nghĩa tự động chuyển sang chế độ Ed25519ph).

Không kiểm tra một bản sao file rồi thực thi/tin **bản sao khác có thể bị thay đổi giữa hai bước**. Với artefact nhạy cảm, đảm bảo dữ liệu được verify là chính dữ liệu sẽ sử dụng; cân nhắc stream/buffer immutable, atomic storage, file handle và giới hạn TOCTOU theo môi trường.

## 8. Chọn thuật toán và làm việc với provider Java

### 8.1. Thuật toán ký phổ biến

| Thuật toán | Đặc điểm cần lưu ý |
| --- | --- |
| **Ed25519** | Thuộc EdDSA, thường đơn giản để dùng, chữ ký cố định 64 byte; có sẵn trong các JDK 17 hiện đại khi provider hỗ trợ. |
| **SHA256withECDSA** | ECDSA trên đường cong phù hợp, với SHA-256; kích thước/định dạng public key và signature phải thống nhất. Java `Signature` thường biểu diễn chữ ký ECDSA bằng mã hóa ASN.1 DER cho cặp `r,s`. |
| **RSASSA-PSS** | Chữ ký RSA-PSS; cần thống nhất digest, MGF1 digest, salt length, trailer field, độ dài modulus; tránh các cấu hình không nhất quán hoặc bị downgrade. |
| **SHA256withRSA** | Thường biểu thị RSA PKCS#1 v1.5 với SHA-256 trong JCA; có thể cần vì tương thích cũ, nhưng thiết kế mới thường cân nhắc Ed25519 hoặc RSA-PSS theo tiêu chuẩn/chính sách tương thích. |

Không đồng nhất “ECDSA” với “ECDH”: ECDH là thỏa thuận khóa, không phải chữ ký. Không dùng khóa mã hóa RSA tùy tiện để thay cho khóa ký nếu mục đích, key usage và quản trị khóa tách biệt.

**Không bao giờ cho request không đáng tin tự chọn mọi algorithm/provider mà hệ thống sẽ chấp nhận.** Header `alg` hoặc thông tin tương đương có thể là dữ liệu giúp định tuyến theo một allowlist/khóa đã cấu hình; phải kiểm tra thuật toán thực sự được phép cho đúng key và use case để tránh algorithm-confusion/downgrade.

### 8.2. JCA Signature là API theo trạng thái

Với `Signature`, quy trình gồm `getInstance` → `initSign` hoặc `initVerify` → nhiều lần `update` → `sign`/`verify`. Những lỗi thường gặp:

- Gọi `update` trước `initSign/initVerify`: sai trạng thái engine.
- Lấy `Signature.getInstance("Ed25519")` nhưng public key không đúng loại hoặc chữ ký được tạo bằng lược đồ khác.
- Dùng sai tham số PSS giữa hai phía.
- Xác minh trên byte đã bị parse/serialize lại không giống bản đã ký.
- Giả định `Signature` thread-safe để dùng chung nhiều request mà không đồng bộ.
- Coi `Signature.verify(...)` thành công là **chứng thực danh tính** dù public key chỉ lấy từ request.

### 8.3. Lưu, trao đổi và xoay vòng khóa

Trong Java, `PublicKey.getEncoded()` của nhiều khóa thông thường dùng định dạng `X.509 SubjectPublicKeyInfo (SPKI)`; `PrivateKey.getEncoded()` (nếu khóa có thể export) thường là `PKCS#8`. **Không** hiểu định dạng key encoding là chứng thư X.509 đã được xác nhận: SPKI chỉ biểu diễn thông tin public key.

Private key cần lưu trong `KeyStore`, HSM, KMS hoặc hệ thống khóa được bảo vệ phù hợp. Hạn chế xuất private bytes, quyền sign và việc ghi vào log/config. Public key có thể được phân phối nhưng phải kiểm tra identity binding và key rotation; khi thay key, không mặc định bỏ mọi chữ ký cũ hay chấp nhận key cũ vô thời hạn. Thiết kế keyId, thời gian hiệu lực, phiên bản và quy tắc thu hồi cho dữ liệu ký lâu dài.

## 9. Các giới hạn bảo mật mà chữ ký số không giải quyết tự động

### 9.1. Không cung cấp tính bí mật

Người thấy `message + signature` vẫn đọc được message nếu nó truyền dạng rõ. Cần TLS/AEAD hoặc mã hóa thích hợp khi payload nhạy cảm. **Ký rồi mã hóa** hoặc **mã hóa rồi ký** đều có thể xuất hiện trong các giao thức chuẩn, nhưng không tự ghép các bước này mà thiếu thiết kế vì có nhiều vấn đề liên quan đối tượng được ký và cách xác minh.

### 9.2. Không tự chống replay

Một request ký hợp lệ ở thời điểm T có thể được gửi lại nguyên vẹn ở T+1; chữ ký vẫn hợp lệ với cùng byte message. Nếu nghiệp vụ yêu cầu chống phát lại:

- Ký `requestId`/nonce nghiệp vụ duy nhất, timestamp/expiry và các trường ngữ cảnh cần thiết.
- Bên nhận kiểm tra thời hạn với độ lệch đồng hồ hợp lý.
- Lưu trạng thái xử lý `requestId` hoặc sequence number để từ chối trùng.
- Dùng giao thức idempotency khi hành động có thể được retry hợp lệ.

Lưu ý **timestamp được ký** mới bảo vệ không bị sửa tùy ý; timestamp *không* tự chặn replay nếu server không áp dụng cửa sổ thời gian hoặc cơ chế chống dùng lại.

### 9.3. Không tự đảm bảo quyền và tính chính xác của nghiệp vụ

Bên ký đã xác thực có thể không được phép thay đổi tenant khác, vượt hạn mức hoặc ký một loại thông điệp ngoài quyền hạn. Sau khi verify, server vẫn phải kiểm tra **authorization**, policy theo keyId/identity, trạng thái tài khoản, hạn mức, schema và điều kiện nghiệp vụ.

### 9.4. Không chứng minh tuyệt đối “không thể chối bỏ”

Chữ ký số có thể hỗ trợ bằng chứng về nguồn ký, nhưng **non-repudiation** ở góc độ pháp lý/vận hành còn phụ thuộc vào việc kiểm soát private key, nhận dạng người ký, chứng thư, chứng cứ thời gian, quy trình cấp quyền, audit và khả năng khóa bị lộ. Nếu một private key được chia sẻ cho nhiều nhân viên hoặc dịch vụ, verify không phân biệt chính xác cá nhân nào đã dùng khóa đó.

Chữ ký hợp lệ không chứng minh con người đã đọc, hiểu hoặc đồng ý với toàn bộ điều khoản, cũng không chứng minh nội dung không bị tạo ra bởi máy có quyền ký nhưng bị xâm phạm.

### 9.5. Không xác minh trust chain thay cho ứng dụng

Nếu ứng dụng tải một certificate bất kỳ từ mạng rồi lấy `certificate.getPublicKey()` để verify, việc trả `true` không thay thế xác minh certificate chain, trust anchor, name/identity, key usage, effective validity/revocation và policy. Tương tự, một key ID trong header mà client điều khiển chỉ nên dùng làm *gợi ý tra khóa dưới policy*, không phải chứng cứ danh tính.

## 10. Quy trình xác minh ở ứng dụng thực tế

Một hệ thống nhận chữ ký nên thực hiện các bước có thứ tự:

1. **Đọc envelope dưới giới hạn an toàn:** kích thước message, length của signature, encoding Base64, version, keyId, content type; loại bỏ malformed input. Không phân tích JSON thiếu giới hạn hoặc tin trường do client cung cấp.
2. **Xác định key và thuật toán được phép:** tra allowlist/key registry/truststore; nếu dùng X.509, kiểm tra trust path và policy; xác định quyền ký loại thông điệp này.
3. **Chuẩn hóa hoặc lấy byte được ký theo đúng giao thức:** không reformat âm thầm; include version, purpose, tenant, amount, currency và hạn sử dụng nếu protocol yêu cầu.
4. **Xác minh mật mã:** `Signature.initVerify(trustedPublicKey)`, `update(exactMessageBytes)`, `verify(signatureBytes)`. Chỉ coi thành công nếu trả true và không có lỗi.
5. **Xác minh ngữ cảnh và nghiệp vụ:** key còn được phép, schema/authorization, signed timestamp/expiry, replay/idempotency, trạng thái tài nguyên.
6. **Chỉ sau đó** chấp nhận, lưu hoặc thực thi dữ liệu; audit việc xác minh và key identifier bằng metadata cần thiết, không log private key hay dữ liệu nhạy cảm.

**Thứ tự có thể cần một số bước parse sơ bộ trước khi verify** để tìm keyId/version, nhưng các trường sơ bộ này phải luôn được xem là **chưa xác thực** cho đến khi chữ ký và policy thành công. Tránh quyết định có tác dụng không thể đảo ngược trước bước xác minh.

### Ví dụ lỗi: xác minh đúng chữ ký nhưng sai đối tượng dữ liệu

Giả sử phần JSON body `{"amount":120000}` được ký, trong khi server lấy `currency=USD` từ query string chưa ký. Bên tấn công có thể giữ nguyên body+signature rồi thay query string từ `VND` sang `USD` mà chữ ký vẫn hợp lệ cho body. Khắc phục: **ràng buộc currency vào dữ liệu ký** và dùng cùng nguồn dữ liệu đã ký khi thực thi.

### Ví dụ lỗi: tin public key do người gửi tự đưa

Request chứa `payload`, `signature`, `publicKey`. Server chạy `verify(publicKey, payload, signature)` và cho phép thao tác nếu true. Đối thủ tự tạo keypair, ký payload của chính mình, gửi cả ba và được chấp nhận. Khắc phục: đối chiếu public key với **registry/trust anchor do server quản lý**, rồi kiểm tra quyền hạn theo identity/scope; không dựa vào public key trôi nổi trong request.

## 11. Bảng kiểm nhanh về bảo đảm và giới hạn

| Nhận định | Kết luận chính xác |
| --- | --- |
| Chữ ký số có thể phát hiện thông điệp đã bị sửa sau khi ký không? | **Có**, nếu ký/xác minh trên đúng byte và thuật toán/khóa đủ an toàn. |
| Verify true có xác thực danh tính người ký không? | **Chỉ khi** public key đã được gắn với đúng danh tính và policy đáng tin, có xét nguy cơ khóa bị lộ. |
| Ai có public key đều có thể tạo chữ ký hợp lệ không? | **Không** theo giả định an toàn của chữ ký; cần private key hoặc quyền sử dụng nó. |
| Verify true có đảm bảo message đúng về mặt nghiệp vụ không? | **Không**; cần validation và authorization. |
| Chữ ký có mã hóa dữ liệu không? | **Không**; signed payload vẫn có thể đọc được. |
| Chữ ký có chống replay không? | **Không tự động**; cần dữ liệu chống replay được ký và kiểm tra phía server. |
| Chữ ký có bảo vệ các trường ngoài phần byte được ký không? | **Không**; phải đưa trường có ý nghĩa vào phạm vi ký. |
| SHA-256 checksum và chữ ký số có tương đương không? | **Không**; hash không có private key để xác thực nguồn. |
| HMAC và chữ ký có cùng mô hình phân phối khóa không? | **Không**; HMAC dùng khóa chung, chữ ký dùng private/public key. |
| Chứng thư X.509 parse được có nghĩa nó đáng tin không? | **Không**; cần xác minh trust path và các ràng buộc thích hợp. |
| Chữ ký hợp lệ có chứng minh chắc chắn một người cụ thể tự tay thao tác không? | **Không**; cần chứng cứ kiểm soát khóa/quy trình và các yếu tố liên quan. |

## 12. Lỗi phổ biến khi học và triển khai

- **“Sign là encrypt bằng private key.”** Sai mô hình; dùng `Signature` và các lược đồ chuẩn, không xây thuật toán ký thủ công.
- **Tự ký rồi tin public key tự gửi.** Chỉ xác thực một cặp khóa do request cung cấp; không chứng minh nguồn được ủy quyền.
- **Ký thiếu trường nghiệp vụ.** Chữ ký không bảo vệ currency, tenant, account, expiry hoặc action nếu chúng không ở trong byte ký.
- **Sign và verify chuỗi được serialize khác nhau.** Byte mismatch gây verify false dù đối tượng có vẻ giống nhau; chuẩn hóa format rõ ràng.
- **Dùng key sign sai algorithm/parameter.** Không nhất quán Ed25519/ECDSA/RSA-PSS, signature encoding hoặc hash khiến xác minh lỗi.
- **Không phân biệt lỗi format với chữ ký đúng.** `Signature.verify` có thể false hoặc exception; cả hai đều không được chấp nhận.
- **Tin verify success là đủ để thực thi.** Vẫn cần kiểm tra policy, quyền ký, chống replay, hạn dùng và nghiệp vụ.
- **Nhầm non-repudiation thành bảo đảm tuyệt đối.** Private key có thể bị chia sẻ, bị đánh cắp, hoặc dịch vụ ký có thể bị lạm dụng.
- **Không bảo vệ private key.** Đặt key ở repo, log, container image, CI artifacts hoặc file world-readable làm suy yếu nguồn xác thực.
- **Bỏ qua key rotation/revocation.** Chấp nhận key đã bị hủy hoặc không còn quyền ký vô thời hạn.
- **Gọi `Signature.update` trên các chunk sai thứ tự.** Chữ ký gắn với concatenation byte chính xác.
- **Nhầm signature với confidentiality.** Dữ liệu ký có thể bị đọc; cần bảo vệ bí mật độc lập.

## 13. Tự kiểm tra và bài tập thực hành

1. Nếu người gửi tự sinh keypair và gửi `message, signature, publicKey`, verify true chứng minh **được** và **chưa chứng minh được** điều gì?
2. Nếu thay một byte `amount` nhưng giữ chữ ký cũ, phép kiểm tra bằng public key chuẩn phản ứng ra sao? Vì sao?
3. Hai hệ thống dùng cùng thông tin JSON nhưng một hệ thống đổi thứ tự field trước khi verify. Có thể xảy ra lỗi nào? Cách định nghĩa canonical byte là gì?
4. Vì sao phải ký `currency`, `tenantId`, `operation` và `expiresAt` nếu chúng ảnh hưởng đến quyền hoặc kết quả xử lý?
5. Bên xác minh sở hữu public key nhưng không có private key. Họ có thể kiểm tra chữ ký không? Có thể tạo chữ ký mới hợp lệ không?
6. Digest SHA-256, HMAC-SHA256 và Ed25519 khác nhau ở yêu cầu khóa và xác thực nguồn ra sao?
7. Bản ghi ký hợp lệ từ hôm qua được phát lại hôm nay. Vì sao `Signature.verify` có thể vẫn trả true, và ứng dụng cần bổ sung gì?
8. Một certificate X.509 có public key nhưng do CA không tin cậy phát hành. `Signature.verify` true có đủ để gắn danh tính không?
9. Vì sao private key bị lộ làm suy yếu kết luận về nguồn ký dù thuật toán Ed25519 vẫn hoạt động chính xác?
10. Tại sao chữ ký hợp lệ **không** thay thế kiểm tra authorization hoặc không tự đảm bảo confidentiality?

**Thực hành 1:** chạy `DigitalSignatureDemo`, đổi byte đầu/byte cuối của message; xác nhận verify false. Đổi `"amount=120000"` sang `"amount=120001"` trước khi verify nhưng giữ signature cũ.

**Thực hành 2:** mở rộng message với `tenantId`, `currency`, `expiresAt` và serialize bằng một format không mơ hồ; viết test mà đổi mỗi trường đều khiến signature sai. Đảm bảo sender và receiver có test vector cùng byte UTF-8.

**Thực hành 3:** mô phỏng key registry có hai public key cho hai đối tác khác nhau. Chỉ cho phép đối tác A dùng public key A để ký `orders`. Verify với key B phải thất bại hoặc bị policy từ chối; không cho người gửi tự thay key tùy ý.

**Thực hành 4:** thêm `requestId` và `expiresAt` vào nội dung ký và tạo state cache kiểm soát request đã xử lý; quan sát rằng `verify` không tự phát hiện trùng, nhưng application có thể từ chối lần replay thứ hai.

## 14. Tham khảo chính thức

- [Signature — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): `getInstance`, `initSign`, `initVerify`, `update`, `sign`, `verify`, lỗi và lifecycle.
- [KeyPairGenerator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): sinh cặp public/private key.
- [Java Security Standard Algorithm Names — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên thuật toán như `Ed25519`, `SHA256withECDSA` và `RSASSA-PSS` theo provider/spec.
- [X509Certificate — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): truy cập public key và thuộc tính chứng thư; không phải kiểm tra trust chain hoàn chỉnh.
- [CertPathValidator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): xác thực certification path tới trust anchor bằng policy phù hợp.
- [JCA Reference Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): nền tảng provider, public key cryptography và signature engine.
