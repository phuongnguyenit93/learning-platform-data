# initVerify, update, verify trong Java — xác minh chữ ký số EdDSA

Để kiểm tra một chữ ký số, Java cung cấp lớp **`java.security.Signature`** thuộc Java Cryptography Architecture (JCA). Ba bước chính là **`initVerify(...) → update(...) → verify(...)`**: thiết lập **khóa công khai** của bên ký, cung cấp chính xác **dữ liệu đã được ký** ở dạng byte và kiểm tra chữ ký được gửi kèm.

Trong Java 15, **EdDSA** được bổ sung theo **JEP 339**, gồm các biến thể **Ed25519** và **Ed448**. Cơ chế `Signature` để xác minh đã tồn tại từ trước và **vẫn được sử dụng trong Java hiện đại**; EdDSA là một họ thuật toán mới được đưa vào hệ sinh thái JCA tại mốc Java 15. Bài học tập trung vào quy trình xác minh, trạng thái của `Signature`, điều kiện sử dụng API, ngoại lệ, tương thích khóa/dữ liệu và các lỗi bảo mật thường gặp.

## 1. Xác minh chữ ký số đang xác nhận điều gì?

Giả sử bên A có một cặp khóa bất đối xứng:

- **Private key**: bên A giữ bí mật và dùng để ký.
- **Public key**: bên nhận B sử dụng để xác minh. Khóa này có thể được công bố, nhưng B phải có **căn cứ đáng tin cậy** để xác định đó đúng là public key của A.

Bên A ký byte của thông điệp `M` và tạo ra chữ ký `S`. Bên B nhận `M`, `S` và public key đã được xác thực, rồi dùng `verify`.

```text
                 BÊN KÝ (A)                           BÊN XÁC MINH (B)

    dữ liệu M -----> update(M)           dữ liệu M ------> update(M)
    private key ---> initSign(key)       public key ------> initVerify(key)
                       |                                     |
                       v                                     v
                     sign() -------- chữ ký S -----------> verify(S)
                                                            |
                                                     true / false
```

Kết quả `true` cho biết chữ ký khớp với **dữ liệu byte**, thuật toán/tham số và public key đã dùng. Kết quả này **không tự chứng minh danh tính người gửi** nếu public key do kẻ tấn công cung cấp hoặc không được xác thực.

Chữ ký số nhằm bảo vệ **tính toàn vẹn** và hỗ trợ **xác thực nguồn gốc** khi public key được tin cậy. Nó **không mã hóa** thông điệp; dữ liệu ký vẫn có thể đọc được nếu không có cơ chế mã hóa riêng.

## 2. Vai trò chính xác của ba phương thức

| Phương thức | Vai trò | Cần chú ý |
| --- | --- | --- |
| `initVerify(PublicKey key)` | Đưa `Signature` vào trạng thái xác minh bằng public key | Key phải tương thích thuật toán/provider |
| `initVerify(Certificate cert)` | Sử dụng public key lấy từ chứng chỉ | Chưa thay thế kiểm tra chain/độ tin cậy của chứng chỉ |
| `update(byte[] message)` | Cung cấp byte dữ liệu đã được ký | Dùng **dữ liệu gốc**, không phải chữ ký |
| `update(byte[] data, int off, int len)` | Cung cấp một đoạn byte theo offset và length | Có thể gọi nhiều lần theo đúng thứ tự |
| `update(byte b)` | Cung cấp một byte | Dùng khi cần xử lý từng byte |
| `update(ByteBuffer data)` | Cung cấp các byte còn lại của buffer | Tiêu thụ từ `position` đến `limit`, vị trí tiến tới limit |
| `verify(byte[] signature)` | Kiểm tra chữ ký đã cho, trả `boolean` | `false` là kết quả chữ ký không hợp lệ; dữ liệu sai định dạng có thể ném lỗi |
| `verify(byte[] signature, int offset, int length)` | Kiểm tra một đoạn chứa chữ ký trong byte array | `length` là số byte, không phải chỉ số kết thúc |

Mẫu sử dụng đơn giản:

```java
import java.security.Signature;
import java.security.PublicKey;

static boolean verifyEd25519(
        PublicKey publicKey, byte[] message, byte[] signatureBytes)
        throws Exception {

    Signature verifier = Signature.getInstance("Ed25519");
    verifier.initVerify(publicKey);
    verifier.update(message);
    return verifier.verify(signatureBytes);
}
```

Đây là **phương thức minh họa cần đặt trong class**, giả định các biến byte và `PublicKey` đã được truyền vào. Ví dụ chạy hoàn chỉnh có tại mục 6.

Điểm phân biệt rất quan trọng: **`update(...)` nhận nội dung được ký; `verify(...)` mới nhận bytes của chữ ký**. Nếu đưa chữ ký vào `update`, bạn đang yêu cầu kiểm tra chữ ký đối với *nội dung sai*.

## 3. Trạng thái của đối tượng Signature

API `Signature` làm việc theo các trạng thái chính:

```text
                         getInstance("Ed25519")
                                  |
                                  v
                            UNINITIALIZED
                             /          \\
           initSign(privateKey)        initVerify(publicKey)
                  |                            |
                  v                            v
                SIGN                         VERIFY
                  |                            |
            update(message)              update(message)
                  |                            |
                sign()                      verify(sig)
                  |                            |
                  v                            v
           SIGN (được reset)            VERIFY (được reset)
```

`Signature.getInstance("Ed25519")` tạo một đối tượng `Signature` nhưng **chưa thể xác minh ngay**. Trước khi gọi `update`/`verify` cho chức năng xác minh, phải gọi `initVerify` với khóa công khai phù hợp.

Ví dụ thứ tự sai:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.update(message); // SignatureException: chưa initVerify
```

Đoạn trên **chỉ minh họa lỗi trạng thái**; `message` được giả định là `byte[]`. Cách sửa là đặt `verifier.initVerify(publicKey)` trước `update`.

### Sau khi verify() thì sao?

Theo Javadoc, sau lời gọi `verify(...)`, đối tượng `Signature` được **reset về trạng thái sau lần `initVerify(...)` trước đó**. Có thể cấp một thông điệp **mới** bằng `update(...)` rồi xác minh chữ ký khác **với cùng public key**.

```java
verifier.initVerify(publicKey);
verifier.update(firstMessage);
boolean a = verifier.verify(firstSignature);

verifier.update(secondMessage);
boolean b = verifier.verify(secondSignature);
```

Đây là ví dụ minh họa API, cần có các biến `publicKey`, `firstMessage`, `secondMessage` và chữ ký phù hợp. **Không nối trực tiếp** hai lần `update` của hai thông điệp khác nhau nếu mục tiêu là xác minh từng thông điệp độc lập: phải kết thúc lần đầu bằng `verify` trước khi cập nhật thông điệp tiếp theo.

Để **đổi khóa** từ A sang B, gọi lại `initVerify(publicKeyB)` trước khi cấp dữ liệu của B. Không dùng một verifier đang gắn khóa A để xác minh chữ ký của B.

Trong mã chạy đồng thời, đừng chia sẻ một đối tượng `Signature` mutable cho nhiều request/thread mà không bảo vệ trạng thái. Cách dễ hiểu, ít lỗi nhất là **mỗi thao tác/request tạo một instance riêng** hoặc quản lý vòng đời và đồng bộ một cách rõ ràng.

## 4. update(...) xử lý byte và thứ tự các đoạn

Chữ ký được tính trên **dãy byte chính xác**. Bạn có thể cung cấp một lần:

```java
verifier.update(messageBytes);
```

Hoặc chia thành nhiều đoạn liên tiếp **không đổi thứ tự, không thêm hoặc bỏ byte**:

```java
int middle = messageBytes.length / 2;
verifier.update(messageBytes, 0, middle);
verifier.update(messageBytes, middle, messageBytes.length - middle);
```

Hai cách có cùng ý nghĩa logic khi toàn bộ dãy byte truyền vào là như nhau. Với các API, `off` là **vị trí bắt đầu** trong array và `len` là **số byte cần xử lý**, không phải chỉ số cuối.

Trường hợp dữ liệu nằm trong `ByteBuffer`:

```java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.wrap(messageBytes);
verifier.update(buffer);
```

`update(ByteBuffer)` xử lý các byte còn lại từ `position()` đến `limit()`. Khi trả về, vị trí buffer được chuyển tới `limit` và limit không đổi. Nếu tái sử dụng buffer cho lần verify khác, phải thiết lập lại vùng dữ liệu cần đọc đúng cách. Tránh gọi `update(buffer)` lần thứ hai khi buffer đã hết dữ liệu rồi tưởng rằng nội dung được cung cấp hai lần.

**Lưu ý hiệu năng:** API cho phép gọi `update` theo đoạn, nhưng **không bảo đảm provider EdDSA xử lý với dung lượng nhớ hằng số**. Một số triển khai có thể buffer dữ liệu để đáp ứng quy trình ký/xác minh. Nếu xác minh file rất lớn, cần đo và kiểm soát tài nguyên thực tế của provider.

## 5. Những byte nào phải khớp giữa hai bên?

Nếu bên ký đã ký:

```java
byte[] original =
        "invoice=123|currency=VND".getBytes(StandardCharsets.UTF_8);
```

thì bên xác minh phải đưa **đúng byte của chuỗi ấy** vào `update`. Cả những thay đổi nhỏ cũng làm thay đổi đầu vào xác minh:

- Dùng `"invoice=999|currency=VND"` thay vì `"invoice=123|currency=VND"`.
- Thêm hoặc bỏ dấu cách, tab, `\\n`, `\\r\\n`, hoặc ký tự cuối dòng.
- Đổi chữ hoa/thường hoặc thứ tự các trường.
- Mã hóa text khác UTF-8, hoặc dùng `String.getBytes()` không chỉ định charset.
- Thay đổi Unicode normalization (ví dụ ký chuỗi dạng tổ hợp nhưng verify sau khi chuyển về NFC) mà giao thức không quy định.
- Parse JSON rồi serialize lại với thứ tự trường hoặc whitespace khác.
- Thay đổi cách biểu diễn số, ngày giờ, dấu phẩy/dấu chấm hoặc escape sequence.

**Ký/xác minh không tự chuẩn hóa dữ liệu.** Với giao thức JSON/XML, hai bên cần thống nhất chính xác tập byte nào được ký: **canonical serialization**, định dạng thông điệp định nghĩa trước, hoặc truyền nguyên vẹn bytes gốc. Không tự gọi `.trim()`, `.strip()` hay chuyển đổi line ending trước khi xác minh nếu giao thức không quy định.

Khi nội dung gốc là text Java, luôn chỉ định charset:

```java
import java.nio.charset.StandardCharsets;

byte[] messageBytes = messageText.getBytes(StandardCharsets.UTF_8);
```

Một chữ ký ở dạng **Base64** là dữ liệu văn bản đại diện cho các byte chữ ký, không phải chính byte của chữ ký ở dạng raw. Cần giải mã Base64 trước khi đưa vào `verify(...)`.

## 6. Chương trình Java 17+ hoàn chỉnh, kiểm tra được kết quả

Chương trình tạo hai cặp khóa Ed25519, dùng private key của chủ sở hữu để ký, rồi kiểm tra:

- Thông điệp gốc có thể được cấp bằng **hai lần `update`**.
- Có thể **reuse** đối tượng sau `verify` với cùng public key.
- Sửa thông điệp làm verify trả `false`.
- Dùng public key của người khác làm verify trả `false`.
- Có thể xác minh chữ ký nằm ở một **đoạn của byte array lớn hơn**.
- Gọi `update` trước `initVerify` gây `SignatureException`.
- Base64 encode/decode chữ ký là phép chuyển đổi biểu diễn, không thay đổi byte.
- Chữ ký Ed25519 theo RFC 8032 có chiều dài **64 byte**.

Lưu file **`EdVerifyFlowDemo.java`** dưới mã hóa UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public class EdVerifyFlowDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator keygen = KeyPairGenerator.getInstance("Ed25519");
        KeyPair owner = keygen.generateKeyPair();
        KeyPair outsider = keygen.generateKeyPair();

        byte[] original = "invoice=123|currency=VND"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(owner.getPrivate());
        signer.update(original);
        byte[] signed = signer.sign();

        // Khôi phục public key từ SubjectPublicKeyInfo/X.509.
        byte[] encoded = owner.getPublic().getEncoded();
        PublicKey publicKey = KeyFactory.getInstance("Ed25519")
                .generatePublic(new X509EncodedKeySpec(encoded));

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(publicKey);

        int middle = original.length / 2;
        verifier.update(original, 0, middle);
        verifier.update(original, middle, original.length - middle);
        System.out.println("valid=" + verifier.verify(signed));

        // verify(...) tự reset về trạng thái đã initVerify.
        verifier.update(original);
        System.out.println("reused=" + verifier.verify(signed));

        // Thay đổi dữ liệu, giữ nguyên chữ ký và public key.
        verifier.update("invoice=999|currency=VND"
                .getBytes(StandardCharsets.UTF_8));
        System.out.println("changedMessage=" + verifier.verify(signed));

        // Đổi sang public key không khớp private key đã ký.
        verifier.initVerify(outsider.getPublic());
        verifier.update(original);
        System.out.println("wrongPublicKey=" + verifier.verify(signed));

        // verify một đoạn (slice) trong byte array.
        verifier.initVerify(publicKey);
        byte[] framed = new byte[signed.length + 2];
        System.arraycopy(signed, 0, framed, 1, signed.length);
        verifier.update(original);
        System.out.println("offsetLength=" +
                verifier.verify(framed, 1, signed.length));

        // Thử thao tác sai trạng thái.
        Signature notInitialized = Signature.getInstance("Ed25519");
        try {
            notInitialized.update(original);
            System.out.println("updateBeforeInit=accepted");
        } catch (SignatureException e) {
            System.out.println("updateBeforeInit=SignatureException");
        }

        String base64 = Base64.getEncoder().encodeToString(signed);
        byte[] decoded = Base64.getDecoder().decode(base64);
        System.out.println("base64RoundTrip=" +
                Arrays.equals(signed, decoded));
        System.out.println("signatureBytes=" + signed.length);
    }
}
```

Biên dịch và chạy với một JDK 17+ có provider Ed25519 hỗ trợ các engine sử dụng:

```bash
javac -encoding UTF-8 EdVerifyFlowDemo.java
java EdVerifyFlowDemo
```

**Đầu ra đã đối chiếu bằng JDK 24:**

```text
valid=true
reused=true
changedMessage=false
wrongPublicKey=false
offsetLength=true
updateBeforeInit=SignatureException
base64RoundTrip=true
signatureBytes=64
```

Trong ví dụ này, key pair được tạo ngẫu nhiên mỗi lần chạy, nhưng các dòng stdout là kết quả logic tương ứng với những tình huống đã nêu. Chương trình **không in private key** hoặc chữ ký thô. Kích thước chữ ký Ed25519 là 64 byte, khác kích thước biểu diễn khóa X.509 hoặc PKCS#8.

**Giới hạn môi trường:** Nếu JDK/runtime tùy biến không cung cấp `Ed25519` trong `KeyPairGenerator`, `Signature` hoặc `KeyFactory`, chương trình có thể ném `NoSuchAlgorithmException`. Đó là vấn đề về khả năng provider, không làm thay đổi quy tắc của ba phương thức `initVerify/update/verify`. Nếu provider dùng key không thể export, ví dụ HSM, cách dựng lại `PublicKey` từ `getEncoded()` cần được điều chỉnh theo giao thức và khả năng của provider.

## 7. Có thể lấy public key từ đâu?

### Từ một đối tượng PublicKey có sẵn

Đây là trường hợp đơn giản nhất:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
```

Đoạn trên là **mã minh họa trong một phương thức**. `publicKey` phải là đối tượng public key tương thích Ed25519 và phải được liên kết đáng tin với danh tính hoặc thực thể cần xác minh.

### Từ public key được mã hóa dạng X.509 SubjectPublicKeyInfo

Nếu ứng dụng nhận dữ liệu byte của public key theo chuẩn **X.509 SubjectPublicKeyInfo (SPKI)**:

```java
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;

PublicKey publicKey = KeyFactory.getInstance("Ed25519")
        .generatePublic(new X509EncodedKeySpec(publicKeyDer));
```

Đây là ví dụ cần biến `byte[] publicKeyDer` đã có. **SPKI không phải 32 raw bytes của public key Ed25519**. Không đưa raw key thẳng vào `X509EncodedKeySpec` rồi cho rằng JCA tự hiểu đúng định dạng.

Nếu public key được vận chuyển bằng Base64, hãy giải mã Base64 thành byte SPKI rồi dùng `KeyFactory`, sau đó mới gọi `initVerify`. Việc parse được public key **không tự chứng minh rằng key đáng tin**.

### Từ Certificate

`Signature` hỗ trợ overload:

```java
verifier.initVerify(certificate);
```

Overload nhận một `java.security.cert.Certificate` và dùng public key của chứng chỉ. Đối với **X.509 certificate** có critical KeyUsage extension không cho dùng để ký số, API có thể ném `InvalidKeyException`.

**Rất quan trọng:** `initVerify(certificate)` không tự thực hiện đầy đủ xác minh **certificate chain, trust anchor, thời hạn, thu hồi, hostname hoặc ràng buộc danh tính**. Các kiểm tra PKIX/trust cần được hệ thống chứng chỉ hoặc logic ứng dụng thực hiện riêng tùy giao thức. Chỉ có một đối tượng certificate hoặc một public key không biến nó thành nguồn đáng tin.

## 8. Ed25519, Ed448 và nhà cung cấp JCA

Trong Java 15, **JEP 339** đưa EdDSA vào JDK, và các tên tiêu chuẩn trong JCA bao gồm **`EdDSA`, `Ed25519`, `Ed448`**.

| Thuật toán | Mục tiêu sử dụng | Lưu ý khi verify |
| --- | --- | --- |
| `Ed25519` | Chữ ký EdDSA theo biến thể edwards25519 | Phải dùng đúng public key/thông điệp/chữ ký Ed25519; chữ ký thô dài 64 byte |
| `Ed448` | Chữ ký EdDSA theo biến thể edwards448 | Sử dụng key Ed448 tương ứng; chữ ký thô dài 114 byte |
| `EdDSA` | Tên tổng quát cho họ EdDSA | Phải kiểm soát biến thể thực tế qua key/parameter và provider |

**Không trộn lẫn**:

- `Ed25519` và `Ed448`: khóa/chữ ký hai biến thể không thay thế trực tiếp cho nhau.
- `ECDSA`: họ chữ ký khác EdDSA.
- `X25519` và `X448`: thuật toán thỏa thuận khóa (**key agreement**), không phải chữ ký số.

Đối với giao thức quy định Ed25519, sử dụng rõ `Signature.getInstance("Ed25519")` thay vì chọn tên tổng quát rồi hy vọng provider dùng đúng mặc định. Những hệ thống sử dụng **Ed25519ctx, Ed25519ph hoặc tham số context/prehash theo một profile khác** phải bảo đảm API/provider hỗ trợ đúng profile và tất cả các bên thống nhất tham số. Không được tự thay bằng cách băm trước thông điệp nếu giao thức không định nghĩa như vậy.

JCA cho phép nhiều **security providers**. Một bản JDK tham chiếu thường có provider **SunEC** hỗ trợ Ed25519/Ed448, nhưng runtime tùy biến, module được cắt gọn hoặc HSM có thể cung cấp các tập dịch vụ khác nhau. Khi có lỗi `NoSuchAlgorithmException`, hãy kiểm tra tên thuật toán, provider được đăng ký và môi trường triển khai.

Có thể xem provider của verifier sau khi khởi tạo với khóa:

```java
String name = verifier.getProvider().getName();
```

Đoạn minh họa này cần đối tượng `verifier` đã được tạo/khởi tạo. Không hard-code tên provider trong stdout hay dùng tên provider làm điều kiện để xác nhận chữ ký. **Provider đã được chọn không làm chữ ký trở nên đáng tin nếu public key sai**.

## 9. verify() trả false khác gì với ném exception?

`verify(...)` có hai kiểu kết quả cần phân biệt:

**Trường hợp chạy hợp lệ nhưng chữ ký không khớp:**

```java
boolean valid = verifier.verify(signatureBytes);
// valid == false → không xác minh được chữ ký cho key+message hiện tại.
```

Ứng dụng phải **từ chối thông điệp** trong trường hợp này. Không cho phép một bước thao tác quan trọng tiếp tục chỉ vì phương thức không ném exception.

**Trường hợp API hoặc dữ liệu chữ ký không được xử lý bình thường:**

- `NoSuchAlgorithmException`: không tìm được provider/engine theo tên thuật toán khi gọi `Signature.getInstance(...)`.
- `InvalidKeyException`: `initVerify(...)` nhận khóa không phù hợp hoặc bị provider từ chối.
- `SignatureException`: gọi sai trạng thái, chữ ký sai kiểu/sai encoding, hoặc provider không thể xử lý thao tác. **Không đảm bảo mọi chữ ký sai dạng đều trả `false`**.
- `IllegalArgumentException`: offset/length không hợp lệ với overload `verify(byte[], int, int)` hoặc `update(byte[], int, int)`.
- `NullPointerException` hoặc một số lỗi input khác có thể phát sinh tùy API khi dữ liệu bắt buộc bị thiếu.
- `ProviderException`: có thể báo lỗi runtime thuộc implementation/provider, ví dụ lỗi token hoặc HSM.

Khi thiết kế ứng dụng, nên **fail closed**: chỉ chấp nhận nội dung khi quá trình xác minh thành công và kết quả là `true`. Khi có ngoại lệ hay `false`, ứng dụng cần từ chối xử lý dữ liệu cần xác thực, đồng thời ghi log phù hợp (không ghi private key hoặc bí mật).

| Tình huống | Kết quả/biện pháp |
| --- | --- |
| Đúng public key, đúng dữ liệu và đúng chữ ký | Thông thường `true` |
| Dữ liệu bị sửa nhưng chữ ký giữ nguyên | Thông thường `false` |
| Public key thuộc bên khác | Thông thường `false` nếu key vẫn là Ed25519 hợp lệ |
| Chữ ký sai encoding/cấu trúc | Có thể `SignatureException`, không chỉ `false` |
| `update` trước `initVerify` | `SignatureException` |
| Key sai loại/không được provider hỗ trợ | `InvalidKeyException` |
| Runtime không cung cấp `Ed25519` | `NoSuchAlgorithmException` từ `getInstance` |

## 10. verify(byte[], offset, length) có nghĩa gì?

Overload:

```java
boolean valid = verifier.verify(signatureArray, offset, length);
```

chỉ lấy phần chữ ký từ **`signatureArray[offset]`** với đúng **`length` byte**. Nó không dùng `length` làm vị trí kết thúc. Ví dụ nếu chữ ký Ed25519 nằm giữa một buffer lớn:

```java
byte[] framed = new byte[signatureBytes.length + 2];
System.arraycopy(signatureBytes, 0, framed, 1, signatureBytes.length);

verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(framed, 1, signatureBytes.length);
```

Đây là mã minh họa với các biến đã được chuẩn bị. Kết quả tương ứng `true` nếu đúng public key và message. Nếu truyền `length = framed.length` trong khi offset bằng 1, phạm vi có thể vượt cuối mảng và API ném `IllegalArgumentException`.

Overload này **không thể tự phân tách một giao thức truyền tin**. Ứng dụng vẫn phải kiểm tra cấu trúc frame, kích thước, vị trí và giới hạn dữ liệu trước khi gọi JCA. Một hệ thống cần tránh việc để offset/length từ input tùy ý quyết định các vùng byte không được kiểm tra.

## 11. Những lỗi thiết kế bảo mật dễ bỏ qua

1. **Tin public key từ chính payload cần xác minh.** Nếu kẻ tấn công được thay cả message, signature lẫn public key, chúng có thể tự ký rồi tạo kết quả `true`. Hệ thống phải gắn public key với danh tính đáng tin bằng kênh kiểm soát hoặc quy trình xác thực riêng.
2. **Cho dữ liệu đi vào quy trình nghiệp vụ trước khi verify.** Với thông điệp cần xác thực, phải hoàn tất xác minh rồi mới thực hiện thay đổi trạng thái nhạy cảm.
3. **Cho phép algorithm downgrade khi verify thất bại.** Không tự thay từ Ed25519 sang một thuật toán khác chỉ để thử cho tới khi có `true`; giao thức phải xác định thuật toán được phép.
4. **Không có cơ chế chống phát lại (replay).** Một chữ ký hợp lệ của thông điệp cũ vẫn có thể được phát lại. Nếu nghiệp vụ cần chống replay, đưa message ID/nonce/timestamp/sequence vào **chính dữ liệu được ký** và kiểm tra cửa sổ thời gian/trạng thái đã sử dụng.
5. **Không ràng buộc ngữ cảnh giao thức.** Nếu cùng một key dùng để ký nhiều loại hành động, thiết kế thông điệp cần định danh mục đích/version/domain được ký, tránh dùng một chữ ký hợp lệ cho một chức năng khác.
6. **Không bảo đảm cùng bytes giữa hệ thống.** Trước khi ký, thống nhất serialization/encoding; khi verify không vô tình chuẩn hóa, trim hoặc parse/serialize lại theo cách thay bytes.
7. **Dùng sai API để hiển thị/lưu chữ ký.** Chữ ký là dữ liệu byte, không phải văn bản UTF-8 tùy ý. Dùng `Base64` hoặc hex khi cần vận chuyển dạng text; decode trước verify.
8. **Dùng lại Signature trên nhiều thread mà không kiểm soát trạng thái.** Đây là đối tượng mutable chứa message/key state; dùng riêng cho thao tác hoặc quản lý đồng bộ rõ ràng.
9. **Cho rằng verify=true chứng minh certificate chain hợp lệ.** Cần cơ chế tin cậy public key/certificate riêng.
10. **Log private key hoặc dữ liệu nhạy cảm.** Kết quả xác minh và tên thuật toán/provider có thể hữu ích khi debug; không để lộ khóa bí mật.

## 12. Checklist triển khai thực tế

- [ ] **Chọn chính xác thuật toán** được giao thức chỉ định: Ed25519 hay Ed448.
- [ ] Kiểm tra provider/JDK triển khai có hỗ trợ `Signature` và thao tác với key tương ứng.
- [ ] Có **public key đáng tin**, không chỉ là key do payload không xác thực gửi kèm.
- [ ] Xác nhận định dạng public key (SPKI, certificate hoặc API của keystore/HSM).
- [ ] Lấy **đúng byte thông điệp** mà người gửi đã ký, đúng thứ tự, byte encoding và serialization.
- [ ] Gọi `initVerify(publicKey)` trước mọi `update`.
- [ ] Cấp thông điệp vào một hoặc nhiều `update`, tránh thiếu/lặp/đổi byte.
- [ ] Gọi `verify(signatureBytes)`; chỉ tiếp tục khi kết quả đúng `true`.
- [ ] Xử lý riêng lỗi provider/key/state/format và kết quả verify `false`, nhưng đều **từ chối thông điệp không xác thực**.
- [ ] Nếu reuse cùng verifier, hiểu việc `verify` reset về trạng thái `initVerify`; **reinit** khi đổi khóa.
- [ ] Tạo các bài test: thông điệp đúng, bị thay đổi, sai public key, chữ ký lỗi, dữ liệu null/rỗng, boundary offset, thông điệp lớn.
- [ ] Nếu có yêu cầu chống replay, kiểm tra nonce/timestamp/sequence đã được ký và trạng thái server.
- [ ] Không log private key, không lưu private key trong source hoặc file cấu hình không an toàn.

## 13. Bài tập tự kiểm tra

**Câu 1.** Cho `Signature verifier = Signature.getInstance("Ed25519");`, rồi gọi ngay `verifier.verify(signatureBytes)`. Có đúng không? Vì sao?

**Câu 2.** Bên ký gửi `"hello\\n"` (có newline ở cuối), nhưng bên xác minh dùng `"hello"` trong `update`. Dù cùng public key, verify có chắc thành công không?

**Câu 3.** Trước khi verify, bạn gọi `update(firstHalf)` và `update(secondHalf)` của cùng một thông điệp. Điều này có hợp lệ không?

**Câu 4.** Sau khi gọi `verify(sigA)`, verifier có thể dùng lại với **cùng public key** để verify `sigB` không? Cần làm gì trước?

**Câu 5.** Một kẻ tấn công gửi một thông điệp, một chữ ký và **public key do họ tự tạo**. Nếu `verify` trả `true`, có nghĩa kẻ đó chắc chắn là người dùng đã đăng ký không?

**Câu 6.** Một chữ ký được đặt trong buffer 70 byte, offset=3, length=64. `verify(buffer, 3, 64)` kiểm tra bao nhiêu byte và bắt đầu từ vị trí nào?

**Đáp án:**

1. Chưa. Đối tượng chưa ở trạng thái VERIFY; cần `initVerify(publicKey)` trước, rồi `update(messageBytes)`, sau đó mới `verify(signatureBytes)`.
2. Không. Newline cũng là byte được ký; thay đổi message làm chữ ký không khớp.
3. Có, nếu đúng thứ tự và tổng byte bằng **đúng một thông điệp** được ký.
4. Có, vì `verify` reset về trạng thái sau `initVerify`. Cần gọi `update(messageB)` để cung cấp dữ liệu mới trước `verify(sigB)`. Nếu thay public key, phải `initVerify` lại.
5. Không. Cần **xác thực nguồn public key và danh tính** qua cơ chế độc lập; chữ ký hợp lệ chỉ chứng minh người ký tương ứng với public key dùng để xác minh.
6. Kiểm tra **64 byte bắt đầu từ index 3**. `length` là số byte, không phải index cuối.

## Tài liệu tham khảo chính thức, còn áp dụng

- [Oracle Java SE 26 — Signature API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): `initVerify(...)`, các overload `update(...)`, `verify(...)`, trạng thái và ngoại lệ.
- [Oracle Java SE 26 — Security Developer’s Guide](https://docs.oracle.com/en/java/javase/26/security/): phần Java Cryptography Architecture, chữ ký số và nhà cung cấp JCA.
- [Oracle Java SE 26 — Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên `Ed25519`, `Ed448`, `EdDSA`.
- [OpenJDK — JEP 339: Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): bổ sung EdDSA vào Java 15.
- [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): đặc tả Ed25519/Ed448 và định dạng chữ ký.