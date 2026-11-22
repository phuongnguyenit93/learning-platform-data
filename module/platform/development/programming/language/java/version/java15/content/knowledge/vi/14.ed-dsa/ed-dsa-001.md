# EdDSA: chữ ký số và mục tiêu xác thực tính toàn vẹn trong Java

> **Phạm vi:** Java 15 đưa **Edwards-Curve Digital Signature Algorithm (EdDSA)** vào Java Cryptography Architecture qua **JEP 339**. `Ed25519` và `Ed448` vẫn là các thuật toán chữ ký số được Java hỗ trợ trên JDK hiện đại. Bài học tập trung vào **tính toàn vẹn dữ liệu**, xác thực nguồn gốc **theo khóa**, sự khác biệt với mã hóa và cách dùng API `Signature` đúng, an toàn.

## 1. Vì sao cần chữ ký số?

Xét một bản ghi giao dịch:

~~~text
transactionId=tx-42
recipient=account-7
amount=100
currency=VND
~~~

Nếu dữ liệu chỉ được gửi/lưu dưới dạng văn bản, bên nhận không thể chỉ nhìn nội dung mà xác nhận rằng số tiền, tài khoản nhận và định danh giao dịch đã được bên phát hành chấp thuận, hoặc các byte có bị thay trong quá trình truyền/lưu hay chưa.

**Chữ ký số** là bằng chứng mật mã được tạo bằng **khóa riêng** (private key) trên **một thông điệp chính xác**. Người nhận sử dụng **khóa công khai** (public key) tương ứng để kiểm tra:

- **Integrity / tính toàn vẹn:** thông điệp đang kiểm tra có đúng các bytes mà người giữ private key đã ký hay không. Khi bytes thay đổi, signature gốc sẽ không còn verify thành công theo giả định an toàn mật mã.
- **Origin authentication / xác thực nguồn theo khóa:** chữ ký hợp lệ chứng minh quan hệ với private key tương ứng **public key dùng để verify**. Muốn xác thực *danh tính đối tác, tổ chức hoặc người dùng*, còn phải xác thực rằng public key đó thực sự được cấp cho chủ thể có quyền.

Không suy luận rằng `verify(...) == true` tự động có nghĩa “dữ liệu này do công ty X phát hành” khi chưa có **trust relationship** đối với public key. Kẻ tấn công có thể tự tạo cặp khóa, ký dữ liệu giả và đưa cả public key của mình; phép kiểm tra có thể đúng với public key đó, nhưng **không chứng minh đúng đối tác**.

### Một chữ ký không che giấu dữ liệu

EdDSA **không mã hóa thông điệp**: nội dung có thể được gửi ở dạng đọc được. Nếu cần bảo mật nội dung trên đường truyền, dùng TLS được xác thực đúng; nếu cần bảo mật dữ liệu lưu trữ, dùng cơ chế encryption phù hợp. Chữ ký số và encryption giải quyết **các yêu cầu khác nhau** và có thể kết hợp khi cần.

## 2. Mô hình hai bên: ký bằng khóa riêng, xác minh bằng khóa công khai

~~~text
BÊN KÝ                                      BÊN XÁC MINH

privateKey                                  trusted publicKey
messageBytes                                      |
     |                                            |
     v                                            v
EdDSA Sign --------------> signatureBytes ---> EdDSA Verify
     |                                            ^
     +---------------> messageBytes --------------+
                                                  |
                                                  v
                                     valid true / false / lỗi
~~~

Các thành phần:

1. **Message bytes:** dãy byte chính xác được đưa vào thuật toán, ví dụ UTF-8 của một văn bản có định dạng rõ.
2. **PrivateKey:** chỉ bên có quyền ký được sử dụng; phải được bảo vệ.
3. **Signature bytes:** chữ ký được trả về từ `Signature.sign()`.
4. **PublicKey:** dùng để xác minh; **không** cần biết private key.
5. **Chính sách tin cậy:** ánh xạ public key sang signer, quyền ký, loại thông điệp và kỳ hiệu lực.

Nếu signature không hợp lệ, hệ thống phải **từ chối**, không được tự thay bytes hoặc chọn lại một public key do người gửi tự khai để cố đạt kết quả `true`.

## 3. EdDSA, Ed25519 và Ed448 trong Java 15

**EdDSA** là họ thuật toán chữ ký số dựa trên đường cong Edwards, được mô tả trong **RFC 8032**. JEP 339 đưa các thuật toán cần thiết vào Java SE/JDK 15. Hai biến thể phổ biến:

| Đặc tính | Ed25519 | Ed448 |
| --- | --- | --- |
| Đường cong | edwards25519 | edwards448 |
| Tên thuật toán Java | `"Ed25519"` | `"Ed448"` |
| Độ dài chữ ký thuần theo RFC 8032 | **64 byte** | **114 byte** |
| Độ mạnh an toàn danh nghĩa theo RFC | Khoảng 128 bit | Khoảng 224 bit |
| Hàm băm nằm trong định nghĩa thuật toán | SHA-512 | SHAKE256 |
| Công dụng | Chữ ký số | Chữ ký số |

Tên `"EdDSA"` cũng là tên thuật toán chuẩn trong JCA, nhưng khi cần đảm bảo chính xác curve, hãy dùng tên cụ thể `"Ed25519"` hoặc `"Ed448"` trong cả `KeyPairGenerator` và `Signature`.

Ví dụ khởi tạo:

~~~java
// Mảnh mã minh họa trong phương thức có xử lý ngoại lệ bảo mật.
KeyPairGenerator keyGenerator =
        KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = keyGenerator.generateKeyPair();

Signature signature = Signature.getInstance("Ed25519");
~~~

Các lớp trên thuộc `java.security`. Đoạn này tạo khóa mới cho demo; trong production, private key phải được quản lý với danh tính, quyền ký, rotation và bảo vệ phù hợp.

**Phân biệt ba thuật toán dễ nhầm:**

- **Ed25519:** ký và xác minh chữ ký số.
- **X25519:** trao đổi/thỏa thuận khóa (key agreement), **không** phải signature. Không dùng `KeyAgreement.getInstance("X25519")` để ký.
- **ECDSA:** một họ chữ ký số khác, có quy tắc và encoding khác; thuật toán `SHA256withECDSA` không tương đương Ed25519.

### Ed25519 có tính xác định

Ed25519 thuần theo RFC 8032 là thuật toán ký **deterministic**: cùng private key và cùng message bytes cho cùng chữ ký. Điều đó **không** làm cho quá trình sinh **cặp khóa** trở thành dễ đoán: key generation vẫn cần randomness an toàn.

Tính xác định cũng **không đồng nghĩa chống phát lại**. Một bản tin và chữ ký hợp lệ có thể bị gửi lại nguyên vẹn nếu giao thức không kiểm tra requestId/nonce/thời hạn.

Không tự tạo một biến thể ký bằng cách hash message trước bằng SHA-256 rồi gọi Ed25519. RFC 8032 đã quy định việc băm nội bộ; Ed25519ph là một biến thể prehash riêng và **không đồng nghĩa** ký digest SHA-256 bằng Ed25519 thuần.

## 4. Java Signature API: vòng đời một lần ký

`java.security.Signature` là API chính của Java Cryptography Architecture:

~~~java
// Mảnh mã minh họa: PrivateKey privateKey và byte[] bytes đã có.
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(bytes);
byte[] signatureBytes = signer.sign();
~~~

Quy trình:

1. **`getInstance("Ed25519")`:** tìm security provider hỗ trợ algorithm này; có thể ném `NoSuchAlgorithmException` nếu thiếu.
2. **`initSign(privateKey)`:** đặt engine vào trạng thái ký với khóa riêng; có thể ném `InvalidKeyException` nếu khóa không phù hợp.
3. **`update(bytes)`:** truyền đúng dữ liệu cần ký theo thứ tự.
4. **`sign()`:** hoàn tất chữ ký, trả một `byte[]`.

**Không** sử dụng private key làm “khóa giải mã” hay chuyển `Signature` thành cipher. Chữ ký trả về có định dạng của thuật toán EdDSA, không phải nội dung được mã hóa.

### Xác minh đối xứng về dữ liệu, bất đối xứng về khóa

~~~java
// Mảnh mã minh họa: PublicKey trustedPublicKey,
// byte[] bytes và byte[] signatureBytes đã có.
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(trustedPublicKey);
verifier.update(bytes);
boolean valid = verifier.verify(signatureBytes);
~~~

Ở đây:

- Khóa **công khai** phải là khóa đã được bên nhận tin cậy để xác minh đối tác/nguồn phát hành.
- `update` phải nhận **đúng cùng dãy bytes** như phía ký.
- `verify` trả `true` khi thuật toán xác minh thành công, `false` khi không hợp lệ; các lỗi khóa/provider/định dạng cũng có thể gây **ngoại lệ**.
- Một ngoại lệ không phải “thành công một phần”; hệ thống nên **fail closed**.

`Signature` là engine có trạng thái. Tránh chia sẻ cùng một instance như singleton giữa nhiều request/thread nếu không có kiểm soát theo hợp đồng provider; cách đơn giản là tạo engine riêng cho từng operation.

## 5. Java runnable: thông điệp gốc, bị sửa, sai khóa và Base64

Lưu file **`EdDsaIntegrityDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Arrays;
import java.util.Base64;

public class EdDsaIntegrityDemo {
    static byte[] sign(PrivateKey key, byte[] message)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initSign(key);
        s.update(message);
        return s.sign();
    }

    static boolean verify(
            PublicKey key, byte[] message, byte[] signature)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance("Ed25519");
        s.initVerify(key);
        s.update(message);
        return s.verify(signature);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair owner = generator.generateKeyPair();

        String content = "Hóa đơn #42: amount=100 VND";
        byte[] original =
                content.getBytes(StandardCharsets.UTF_8);

        byte[] signed = sign(owner.getPrivate(), original);
        System.out.println("signature bytes: " + signed.length);
        System.out.println("original valid: "
                + verify(owner.getPublic(), original, signed));

        byte[] changed = content.replace("100", "900")
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("tampered valid: "
                + verify(owner.getPublic(), changed, signed));

        byte[] withNewline = (content + "\n")
                .getBytes(StandardCharsets.UTF_8);
        System.out.println("newline changed valid: "
                + verify(owner.getPublic(), withNewline, signed));

        KeyPair another = generator.generateKeyPair();
        System.out.println("different key valid: "
                + verify(another.getPublic(), original, signed));

        String transport =
                Base64.getEncoder().encodeToString(signed);
        byte[] restored =
                Base64.getDecoder().decode(transport);
        System.out.println("Base64 roundtrip valid: "
                + verify(owner.getPublic(), original, restored));

        byte[] signedAgain = sign(owner.getPrivate(), original);
        System.out.println("deterministic: "
                + Arrays.equals(signed, signedAgain));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ có provider hỗ trợ Ed25519:

~~~bash
javac EdDsaIntegrityDemo.java
java EdDsaIntegrityDemo
~~~

**Stdout kỳ vọng:** (cặp khóa khác được tạo ngẫu nhiên; xác suất trùng là không đáng kể)

~~~text
signature bytes: 64
original valid: true
tampered valid: false
newline changed valid: false
different key valid: false
Base64 roundtrip valid: true
deterministic: true
~~~

Giải thích:

- **64 byte** là độ dài chữ ký Ed25519 theo RFC 8032.
- Với đúng public key và đúng message bytes, `verify` trả `true`.
- Thay `amount=100` thành `amount=900` làm thay đổi bytes, khiến chữ ký cũ không còn đúng.
- Chỉ thêm một byte LF (`\n`) cũng khiến verification sai.
- Khóa công khai của một cặp khóa **khác** không xác minh được chữ ký tạo từ private key ban đầu.
- Chuyển signature sang Base64 rồi decode về bytes gốc **không ảnh hưởng** khả năng verify; Base64 chỉ là **encoding để truyền tải**.
- Ed25519 thuần tạo cùng chữ ký khi ký lại cùng bytes bằng cùng private key.

Trong thực tế, public key mà hệ thống tin cậy phải được **phân phối, lưu và quản lý** theo chính sách danh tính. Demo sinh cặp khóa mới mỗi lần chạy chỉ để học API.

Khi compiler hỗ trợ kiểm tra mức API Java 15:

~~~bash
javac --release 15 EdDsaIntegrityDemo.java
~~~

JEP 339 là tính năng Java 15 đã hoàn thiện, không cần `--enable-preview`.

## 6. Tính toàn vẹn áp dụng lên **bytes**, không phải nội dung nhìn thấy

Chữ ký EdDSA được tạo trên **dãy byte**. Một số chuỗi trông gần giống nhau vẫn có bytes khác:

- Dấu xuống dòng `LF` và `CRLF`.
- Hai biểu diễn Unicode `NFC`/`NFD` của cùng chữ có dấu.
- UTF-8 và một charset khác.
- Thêm khoảng trắng ở đầu/cuối, tab hay BOM.
- Hai dạng serialization JSON khác thứ tự key hoặc khác cách escape.
- Hai cách biểu diễn số, thời điểm hoặc URL có ý nghĩa giống nhau nhưng bytes khác.

Ví dụ:

~~~java
String a = "A\nB";
String b = "A\r\nB";
boolean same = Arrays.equals(
        a.getBytes(StandardCharsets.UTF_8),
        b.getBytes(StandardCharsets.UTF_8)); // false
~~~

Đoạn trên là **mảnh mã trong một phương thức**, giả định có import `Arrays` và `StandardCharsets`.

`Signature.verify` không tự sửa newline, không chuẩn hóa Unicode, không canonicalize JSON và không bỏ khoảng trắng. Nếu một bên ký **raw bytes** nhưng bên còn lại parse rồi serialize lại trước khi verify, chữ ký có thể thất bại dù người đọc thấy nội dung tương tự.

### Cách thiết kế A: ký đúng payload bytes

~~~text
Nguồn dữ liệu
    -> serialize chính xác một lần -> payloadBytes
    -> sign(payloadBytes) -> signature
    -> truyền payloadBytes + signature + keyId
    -> verify(payloadBytes, signature, publicKey tin cậy)
    -> parse dữ liệu sau khi xác minh
~~~

Đây là thiết kế tương đối đơn giản và dễ debug. Không thay đổi payload bytes trên đường vận chuyển. `keyId` chỉ giúp tra khóa; nó không phải bảo đảm về danh tính nếu tra sai registry.

### Cách thiết kế B: ký dạng canonical được định nghĩa

Nếu giao thức cần so khớp dữ liệu đã parse và chuẩn hóa, phải định nghĩa **canonicalization** chi tiết: encoding, quy tắc Unicode, thứ tự trường, cách encode số, string escaping, null, whitespace, dấu xuống dòng và các trường được phép bỏ/giữ.

Ví dụ **sơ đồ ý tưởng**:

~~~text
object nghiệp vụ
 -> canonical serializer theo đặc tả chung
 -> canonicalBytes
 -> Ed25519 signature trên canonicalBytes
 -> bên nhận tạo lại chính xác canonicalBytes
 -> verify
~~~

Không tự cho rằng “sort key rồi gọi `toString()`” đã tạo JSON canonical đáng tin cậy. Nếu ký JSON theo dạng chuẩn, có thể xem xét cơ chế canonical hóa được định nghĩa rõ và phù hợp giao thức (ví dụ JSON Canonicalization Scheme). Bất cứ bên nào tham gia cũng phải dùng **đúng một quy tắc** và test các trường hợp Unicode, số lớn, escaping và newline.

**Nguyên tắc:** đừng chuẩn hóa “cho dễ đọc” ở một phía nhưng không quy định trong hợp đồng dữ liệu. Đó là nguồn lỗi xác minh chữ ký thường gặp.

## 7. Chữ ký không thay thế chống phát lại và quyền hạn

Chữ ký không tự mang timestamp đáng tin cậy và cũng không đánh dấu “giao dịch này đã xử lý một lần”.

Ví dụ một yêu cầu hợp lệ:

~~~text
version=1
requestId=req-123
recipient=account-7
amount=100
issuedAt=2026-11-08T00:00:00Z
expiresAt=2026-11-08T00:05:00Z
~~~

Nếu người nhận chỉ gọi `verify` rồi thực hiện chuyển tiền, kẻ tấn công có thể phát lại **nguyên thông điệp đã ký và signature**. Mọi byte vẫn không đổi, vì thế verification vẫn có thể `true`.

Cần ràng buộc **và ký** các trường có ý nghĩa cho nghiệp vụ:

- `requestId`/nonce/idempotency key: đánh dấu yêu cầu đã dùng.
- `issuedAt`/`expiresAt` và policy đồng hồ: giới hạn hiệu lực.
- `recipient`, `amount`, `currency`: không cho phép sửa một thành phần quan trọng mà chữ ký vẫn hợp lệ trên phần còn lại.
- `messageType`, `protocolVersion`, `audience`, `tenantId`, `resourceId` nếu có: giới hạn ngữ cảnh sử dụng chữ ký.

Sau verify thành công, hệ thống vẫn phải **xác thực quyền của signer**, kiểm tra hạn dùng, từ chối requestId đã xử lý và thực hiện idempotency/atomicity phù hợp. Kiểm tra timestamp mà không lưu trạng thái request có thể vẫn cho phép replay trong cửa sổ hiệu lực.

### Domain separation

Cùng một khóa đôi khi được dùng cho nhiều loại thông điệp; rủi ro là chữ ký cho message có cùng bytes ở giao thức A lại được nhận ở giao thức B.

Ở **tầng ứng dụng**, dùng message encoding không nhập nhằng và prefix/ngữ cảnh tĩnh đã được định nghĩa trong **bytes được ký**, ví dụ có version + messageType + body length. Không chỉ thêm một nhãn ngoài signature rồi giả định nhãn đó được bảo vệ.

Không tự thay đổi công thức mật mã Ed25519; mục tiêu là **định dạng message** một cách rõ ràng trước `Signature.update`.

## 8. So sánh EdDSA với hash, HMAC, encryption và TLS

| Cơ chế | Khả năng chính | Điều không tự cung cấp |
| --- | --- | --- |
| Hash như SHA-256 | Digest kiểm tra dữ liệu có đổi hay không | Nếu attacker sửa payload và tính lại hash, **không có xác thực người gửi** |
| HMAC | Xác thực tính toàn vẹn bằng **shared secret** | Không hỗ trợ public verification nếu không tiết lộ shared secret |
| Chữ ký EdDSA | Xác minh message với **public key**, private key dùng để ký | Không mã hóa, không tự xác thực danh tính/khả năng replay |
| TLS được cấu hình đúng | Bảo mật và toàn vẹn kết nối mạng | Không nhất thiết cung cấp chữ ký payload tồn tại sau chuyển tiếp/lưu trữ |
| Encryption/AEAD | Bảo mật nội dung; AEAD còn bảo vệ tính toàn vẹn theo secret key | Không phải chữ ký công khai của một signer |
| Checksum/CRC | Phát hiện hỏng dữ liệu ngẫu nhiên | Không chống sửa đổi có chủ ý |

**Dùng EdDSA khi** nhiều bên cần xác minh một bản phát hành, message hay artifact mà không cần được cấp private key: manifest phần mềm đã ký, thông điệp được xác minh sau lưu trữ, tài liệu/bản tin giao tiếp với bên thứ ba, hoặc record có nguồn phát hành được quản lý.

**Không nhất thiết dùng EdDSA** khi ứng dụng chỉ cần kiểm tra lỗi truyền ngẫu nhiên; ở các giao thức dựa trên shared secret, HMAC có thể phù hợp. Quyết định phụ thuộc mục tiêu và trust model, không phụ thuộc khẩu hiệu “ký luôn an toàn hơn”.

## 9. Public key phải được tin cậy từ trước

Một tình huống tấn công:

1. Ứng dụng mong nhận dữ liệu từ **Đối tác A**.
2. Attacker tự tạo cặp Ed25519 và ký payload giả.
3. Attacker gửi payload, chữ ký và **public key của chính attacker**.
4. Ứng dụng gọi `verify(payload, signature, suppliedPublicKey)` → `true`.
5. Ứng dụng nhận là “Đối tác A đã ký” → **sai**, vì không xác thực sở hữu khóa.

Giải pháp đúng ở tầng ứng dụng:

- Phân phối public key qua kênh được xác thực, trust store, certificate/pinning hoặc cơ chế đăng ký khóa tin cậy.
- `keyId` chỉ là một **tên tra khóa**; phải resolve sang public key trong registry **được phép**, không tin key mới do message bất kỳ đưa vào.
- Ràng buộc khóa với danh tính signer, tenant/audience, loại thông điệp, phiên bản thuật toán, quyền ký và trạng thái hiệu lực.
- Có chính sách key rotation, revocation, xử lý khi khóa bị lộ, và quy tắc đọc lại chữ ký cũ.
- Ghi audit có mức độ phù hợp, tránh log private key hoặc dữ liệu nhạy cảm.

### Bảo vệ private key

Private key là tài sản quan trọng:

- Không hardcode private key vào mã nguồn, commit lên Git hay ghi vào log.
- Dùng cơ chế lưu trữ có quản lý quyền, secret manager, KeyStore/HSM/KMS phù hợp với thuật toán và yêu cầu vận hành.
- Hạn chế ai/process nào được gọi chức năng ký; không cấp cho mọi dịch vụ quyền tạo chữ ký phát hành.
- Có quy trình rotation, revoke và ứng phó khi nghi ngờ compromise.
- Không tưởng `Base64.encode(privateKeyBytes)` là cách mã hóa an toàn; Base64 chỉ đổi cách biểu diễn.

Một chữ ký mật mã hợp lệ không tự đảm bảo **không thể chối bỏ về mặt pháp lý**: còn phụ thuộc việc định danh chủ thể, quản lý quyền truy cập khóa, lịch sử thu hồi, timestamp đáng tin và các quy trình nghiệp vụ/pháp lý.

## 10. Chữ ký và key encoding: Base64 không phải mã hóa

`Signature.sign()` trả `byte[]` chữ ký. Có thể chuyển thành Base64 khi giao tiếp qua JSON/HTTP:

~~~java
String value = Base64.getEncoder().encodeToString(signatureBytes);
byte[] restored = Base64.getDecoder().decode(value);
~~~

Đây là **mảnh minh họa trong phương thức**, cần import `java.util.Base64`.

- Với **Ed25519**, signature thuần dài **64 bytes**.
- Với **Ed448**, signature thuần dài **114 bytes**.
- Độ dài Base64 sẽ khác độ dài raw bytes do encoding; không suy ra algorithm chỉ từ hình thức văn bản nếu protocol đã có metadata chuẩn.
- Chữ ký không chứa message gốc, và Base64 không tạo secrecy.

Khi xuất/nhập khóa Java, đừng giả định `PublicKey.getEncoded()` luôn là raw 32-byte Ed25519 public key. Key objects của JCA thường sử dụng **X.509 SubjectPublicKeyInfo** cho public key và **PKCS#8** cho private key, với header/algorithm identifiers. Khi cần import, dùng `KeyFactory` cùng `X509EncodedKeySpec`/`PKCS8EncodedKeySpec` theo định dạng thực tế; một số khóa trong HSM không được export.

**Không dùng `SecretKeySpec` cho private/public keys EdDSA**: EdDSA là thuật toán bất đối xứng, không phải HMAC key.

## 11. Lỗi xử lý dữ liệu lớn và prehash tùy tiện

`Signature.update(...)` có overload nhận từng phần buffer. Đối với tệp lớn, có thể đọc theo block thay vì tự tạo một array chứa toàn file:

~~~java
// Mảnh mã minh họa trong method có IOException/SignatureException.
// Giả định signer.initSign(privateKey) và InputStream input đã có.
byte[] buffer = new byte[8192];
int count;
while ((count = input.read(buffer)) != -1) {
    if (count > 0) {
        signer.update(buffer, 0, count);
    }
}
byte[] signed = signer.sign();
~~~

Bên verify phải truyền **đúng byte sequence, đúng thứ tự**, kể cả khi kích thước các block khác nhau.

**Không tự SHA-256 trước rồi gọi Ed25519 và mong tương thích với bên ký message gốc:**

~~~java
// Cảnh báo: đoạn minh họa này ký digest, không phải ký message gốc.
byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(messageBytes);
signer.update(digest);
~~~

Nếu bạn đưa digest vào `update`, thuật toán **ký chính digest bytes**. Điều đó khác ký trực tiếp message bytes theo định nghĩa Ed25519 thuần. Ed25519ph/Ed448ph trong RFC 8032 là **biến thể riêng**; không được đồng nhất với việc tự băm SHA-256.

Provider có thể đệm dữ liệu nội bộ, vì thế API `update` theo block **không cam kết** mọi triển khai sẽ dùng bộ nhớ hằng số với payload bất kỳ. Cần kiểm tra provider và workload nếu tệp rất lớn.

## 12. Quy trình verify theo nguyên tắc fail closed

Một hệ thống nên có pipeline theo thứ tự rõ ràng:

~~~text
1. Nhận payload + signature + keyId + protocolVersion
2. Áp giới hạn kích thước, cấu trúc và định dạng
3. Xác định thuật toán từ allowlist/policy của hệ thống
4. Tra publicKey TIN CẬY theo keyId và kiểm tra quyền/hiệu lực
5. Khôi phục CHÍNH XÁC các bytes đã được ký
6. Signature.initVerify(publicKey), update(bytes), verify(signature)
7. verify=false hoặc exception -> TỪ CHỐI
8. verify=true -> kiểm tra audience, expiry, nonce/requestId, quyền hạn
9. Nếu tất cả đạt -> thực hiện nghiệp vụ/idempotency atomically
~~~

Không cho người gửi tự chọn thuật toán yếu hoặc tự đổi key tùy ý từ trường `alg` trong payload. Chọn algorithm theo allowlist và ràng buộc với key policy, version, message type. Nếu metadata như tenant, thời hạn hoặc amount ảnh hưởng quyết định, nó phải được **bao gồm hoặc ràng buộc không nhập nhằng trong các bytes được ký**.

## 13. Lỗi thường gặp, triệu chứng và hướng sửa

| Hiện tượng | Nguyên nhân điển hình | Cách khắc phục |
| --- | --- | --- |
| `verify()` sai nhưng văn bản nhìn giống | Newline, charset, Unicode, JSON escaping khác | So sánh chính xác bytes; thống nhất serialization |
| `verify()` đúng với payload giả của attacker | Public key chưa được gắn với signer tin cậy | Trust store/certificate/khóa đã đăng ký |
| Signature hợp lệ nhưng request bị xử lý hai lần | Không chống replay | Nonce/requestId, expiry, idempotency |
| `NoSuchAlgorithmException` | Provider không có Ed25519 | Chọn JDK/provider hỗ trợ tên chuẩn |
| `InvalidKeyException` | Khóa không khớp thuật toán/curve | Dùng đúng Ed25519 key pair và encoding |
| `SignatureException` hoặc signature sai định dạng | Dữ liệu chữ ký bị hỏng hoặc không hợp lệ | Fail closed; giới hạn độ dài và kiểm tra transport |
| Sử dụng `X25519` với `Signature` | X25519 là key agreement | Dùng `Signature.getInstance("Ed25519")` |
| Tự tính `SHA-256(message)` trước Ed25519 | Ký digest thay vì message theo protocol | Ký bytes mà giao thức định nghĩa |
| Nhầm Base64 thành encryption | Chữ ký/nội dung vẫn công khai | Mã hóa riêng khi cần bí mật |
| Private key bị lưu trong repository/log | Attacker có thể ký message giả | Key management và rotation/revocation |
| Thấy `verify=true` và tự động cho phép mọi action | Chưa kiểm tra quyền/timestamp/resource | Kiểm tra policy sau signature |
| Chỉ ký một số field và bỏ recipient | Field không được ký có thể bị sửa | Ký toàn bộ fields quan trọng |
| Algorithm do input chỉ định không kiểm soát | Algorithm confusion/downgrade | Allowlist và key policy |
| Dùng một `Signature` object đồng thời nhiều request | State engine bị trộn | Instance riêng cho mỗi operation hoặc quản lý an toàn |

## 14. Test cần có trước khi dùng trong sản phẩm

1. **Happy path:** đúng bytes, đúng public key, đúng signature → `true`.
2. **Đổi dữ liệu:** sửa một ký tự, một byte hoặc một field có ý nghĩa → verify fail.
3. **Sai khóa:** verify với public key khác → fail.
4. **Sai signature:** sửa/truncate signature → fail hoặc ngoại lệ được xử lý như fail.
5. **Encoding:** LF/CRLF, Unicode dạng dựng sẵn/tách dấu, UTF-8, khoảng trắng → kiểm tra đúng hợp đồng.
6. **Base64:** encode/decode tròn vòng giữ nguyên signature bytes.
7. **Replay:** message/sig hợp lệ nhưng requestId cũ → tầng nghiệp vụ từ chối.
8. **Hết hạn:** signature hợp lệ nhưng `expiresAt` cũ → từ chối.
9. **Key rotation:** key cũ/mới được resolve qua keyId và trạng thái policy.
10. **Input sai:** Base64 hỏng, keyId lạ, message quá lớn, thuật toán không cho phép → fail closed.
11. **Cross-provider:** khi trao đổi giữa hệ thống khác nhau, dùng **RFC 8032 test vectors** và bộ dữ liệu nghiệp vụ để xác minh interoperability.

Không chỉ kiểm tra `verify=true`. Security test phải xác nhận các **điều kiện thất bại quan trọng** đều bị từ chối.

## 15. Câu hỏi tự đánh giá

**Câu 1.** Kẻ tấn công đổi `amount=100` thành `amount=900` sau khi thông điệp được ký. Nếu `amount` nằm trong dữ liệu đã ký, chuyện gì xảy ra?

**Đáp án:** signature cũ không còn xác minh thành công với trusted public key và dữ liệu mới, theo giả định an toàn Ed25519.

**Câu 2.** Attacker tự tạo Ed25519 key pair, ký thông điệp giả và gửi public key của attacker kèm message. `verify=true` có chứng minh message do đối tác thật phát hành không?

**Đáp án:** **Không**. Chỉ có thể kết luận chữ ký phù hợp **public key được cung cấp**. Phải xác định public key tin cậy gắn với đối tác theo cơ chế ngoài chữ ký.

**Câu 3.** Chữ ký EdDSA có tự chống phát lại không?

**Đáp án:** Không. Cần requestId/nonce, hết hạn và trạng thái/idempotency phía nhận; các trường liên quan cần được ký.

**Câu 4.** Vì sao đổi `LF` sang `CRLF` có thể khiến verify sai dù văn bản hiển thị giống?

**Đáp án:** EdDSA ký **bytes chính xác**. Một byte LF khác hai bytes CRLF. Bên nhận phải verify đúng biểu diễn bytes hoặc áp dụng cùng canonicalization được định nghĩa từ trước.

**Câu 5.** `MessageDigest.getInstance("SHA-256")` có đủ đảm bảo message từ đối tác thật không?

**Đáp án:** Không. Hash không có private key/secret để xác thực người gửi; attacker có thể đổi message và tính lại hash.

**Câu 6.** HMAC và EdDSA khác nhau quan trọng nhất ở khả năng verify bởi bên thứ ba ra sao?

**Đáp án:** HMAC đòi bên verify biết shared secret; EdDSA cho phép verify bằng public key mà không cần được cấp private key.

**Câu 7.** Có nên gọi `Signature.getInstance("SHA256withEd25519")` để “băm mạnh hơn” không?

**Đáp án:** Không. Dùng tên chuẩn `Ed25519` và quy trình RFC 8032. Không giả định một tên thuật toán ghép tùy ý tương đương hay được provider hỗ trợ.

**Câu 8.** Vì sao `Base64.encode(signature)` không tăng mức độ an toàn?

**Đáp án:** Base64 là cách trình bày bytes thành văn bản có thể giải mã ngược; nó không thêm bí mật, không cấp trust và không thay đổi signature.

**Câu 9.** Sau khi key bị lộ, `verify=true` cho một tài liệu cũ có chứng minh chắc tài liệu được ký trước thời điểm lộ khóa không?

**Đáp án:** Không. Signature không tự chứng minh thời điểm ký; cần quy trình tin cậy, timestamp/audit có kiểm chứng, trạng thái thu hồi và chính sách xác thực.

## 16. Tài liệu chính thức còn giá trị

- **JEP 339 — EdDSA trong Java 15:** https://openjdk.org/jeps/339
- **RFC 8032 — Ed25519, Ed448 và test vectors:** https://www.rfc-editor.org/rfc/rfc8032
- **Oracle Java SE 17 — `java.security.Signature`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- **Oracle Java SE 17 — `KeyPairGenerator`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html
- **Oracle Java SE 17 — Security Standard Algorithm Names:** https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html
- **Oracle Java SE 17 — JDK Providers Documentation:** https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html

**Kết luận:** EdDSA là cơ chế **chữ ký số** dùng private key để ký và public key để xác minh **tính toàn vẹn, nguồn gốc theo khóa** của thông điệp. Nó **không thay thế** encryption, quản lý danh tính, quyền hạn hay chống phát lại. Thiết kế đúng cần chọn thuật toán chuẩn, bảo vệ private key, phân phối public key tin cậy, ký đúng bytes và triển khai đầy đủ bước kiểm tra nghiệp vụ.
