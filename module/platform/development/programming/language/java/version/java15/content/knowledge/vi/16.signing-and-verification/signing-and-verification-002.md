# initSign, update, sign theo đúng vòng đời trong Java 15+

## Mục tiêu bài học

Trong Java, `java.security.Signature` là API chuẩn để **tạo và xác minh chữ ký số**. Nó hoạt động theo một **vòng đời có trạng thái**: chọn thuật toán, khởi tạo bằng khóa, cung cấp đúng các byte của thông điệp, sau đó kết thúc bằng `sign()` hoặc `verify(...)`. Nếu gọi sai thứ tự, quên chuyển chuỗi sang byte theo một chuẩn thống nhất, hoặc vô tình dùng lại dữ liệu của thông điệp trước, chữ ký có thể không hợp lệ hay ứng dụng mắc lỗi bảo mật.

Bài học tập trung vào **thứ tự `initSign → update → sign`** và cách kiểm tra toàn bộ vòng đời trên API Java hiện đại. Bạn sẽ:

- Hiểu ý nghĩa của `Signature.getInstance(...)`, `initSign(PrivateKey)`, `update(...)` và `sign()`.
- Phân biệt đường **ký** với đường **xác minh**: `initVerify(PublicKey) → update → verify(signatureBytes)`.
- Biết đối tượng `Signature` giữ trạng thái gì sau khi `sign()` hoặc `verify()` thành công.
- Viết đúng nhiều lần `update` cho một thông điệp, hoặc dùng `update(byte[], offset, len)` để xử lý dữ liệu theo từng phần.
- Tránh các lỗi phổ biến như quên `initSign`, gọi `sign` ở chế độ `VERIFY`, ký văn bản với charset khác bên nhận, hoặc dùng nhầm khóa.
- Chạy một chương trình Java 17+ chứng minh vòng đời ký/xác minh bằng thuật toán **Ed25519**, có trong Java từ **Java 15 (JEP 339)**.

**Lưu ý về kiến thức hiện hành:** Các API `Signature`, `KeyPairGenerator` và Ed25519 nêu trong bài vẫn áp dụng trên các JDK hiện đại. Ví dụ không dựa vào thuật toán ký đã lỗi thời như MD5/SHA-1 cho thiết kế mới và không yêu cầu thư viện bên thứ ba.

## 1. Chữ ký số dùng để làm gì?

Một bên có cặp khóa gồm:

- **Private key (khóa riêng):** chỉ bên ký giữ bí mật; truyền vào `initSign(...)`.
- **Public key (khóa công khai):** bên xác minh sử dụng; truyền vào `initVerify(...)`.

Bên ký tạo **chữ ký dạng `byte[]`** trên **chuỗi byte của thông điệp**. Bên nhận dùng đúng thông điệp, chữ ký và khóa công khai phù hợp để xác minh.

Một kết quả `verify(...) == true` cho biết chữ ký hợp lệ **đối với khóa và dữ liệu đang kiểm tra**, trong phạm vi thuật toán và tham số đã chọn. Nó hỗ trợ kiểm tra tính toàn vẹn và tính xác thực dựa trên khóa, nhưng:

- **Chữ ký không mã hóa nội dung.** Người khác vẫn có thể đọc thông điệp nếu nó được truyền ở dạng rõ.
- **Khóa công khai phải được tin cậy theo một cơ chế phù hợp** (ví dụ chứng chỉ/PKI hoặc khóa đã phân phối và xác nhận an toàn). Nếu attacker có thể tự thay cả thông điệp, chữ ký và public key, việc xác minh đúng bằng khóa attacker cung cấp không chứng minh danh tính người gửi như mong muốn.
- Java `Signature` thao tác với **byte**, không tự quyết định cách tuần tự hóa JSON, chuẩn hóa Unicode, sắp xếp field hay chọn charset của ứng dụng.

Với văn bản, nên ghi rõ charset:

```java
byte[] message = "Xin chào Java 15"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

Cả phía ký và xác minh phải dùng **đúng các byte giống nhau**. Thêm một dấu cách, đổi `\n` thành `\r\n` hoặc mã hóa chuỗi khác nhau có thể làm kết quả xác minh thất bại.

## 2. Bốn bước trên đường ký

### Bước 1 — Lấy Signature theo thuật toán

```java
Signature signer = Signature.getInstance("Ed25519");
```

`getInstance(...)` tìm triển khai thuật toán qua **JCA provider**. Bản thân đối tượng mới tạo **chưa có khóa** và chưa sẵn sàng nhận dữ liệu để ký.

Ed25519 là thuật toán chữ ký số hiện đại, được chuẩn hóa trong Java 15 qua JEP 339. Chọn Ed25519 cho ví dụ vì API ngắn, chữ ký có kích thước cố định **64 byte**, và không cần tự chọn hash hay cấu hình padding cho bài nhập môn vòng đời. Khi hệ thống cần tương tác với thuật toán khác như **RSASSA-PSS**, hai phía phải nhất quán về cả thuật toán và các tham số liên quan.

### Bước 2 — Khởi tạo bằng private key: `initSign`

```java
signer.initSign(keyPair.getPrivate());
```

Lúc này `Signature` chuyển sang **chế độ ký (SIGN)** và được gắn với khóa riêng. `initSign` cũng khởi tạo lại trạng thái xử lý thông điệp. Nếu đang có dữ liệu của một lần `update` trước đó, việc khởi tạo lại sẽ không tiếp tục ký trên dữ liệu cũ.

Khóa phải phù hợp với thuật toán. Nếu loại khóa không đúng hoặc provider không chấp nhận, `initSign` có thể ném `InvalidKeyException`. Một overload `initSign(privateKey, secureRandom)` cho phép cung cấp nguồn số ngẫu nhiên đối với thuật toán cần nó; không nên gán ý nghĩa rằng mọi thuật toán đều dùng ngẫu nhiên giống nhau.

### Bước 3 — Cung cấp dữ liệu: `update`

```java
signer.update(message);
```

`update(...)` **tiếp nhận byte của thông điệp vào trạng thái tính chữ ký**; nó không trả về chữ ký. Có thể gọi nhiều lần:

```java
signer.update(message, 0, 4);
signer.update(message, 4, message.length - 4);
```

Hai lần `update` trên xử lý đúng toàn bộ byte `message` theo thứ tự, với điều kiện phần thứ nhất dài 4 byte và phần thứ hai chứa phần còn lại. Về thông điệp logic, nó tương đương một lần `update(message)`.

Các overload hữu ích:

- `update(byte b)`: thêm một byte.
- `update(byte[] data)`: thêm cả mảng.
- `update(byte[] data, int off, int len)`: thêm đúng `len` byte từ vị trí `off`.
- `update(ByteBuffer input)`: thêm các byte còn lại trong buffer; sau lời gọi thành công, vị trí `position` của buffer được nâng đến `limit`.

**Thứ tự byte rất quan trọng:** `update(A); update(B);` có nghĩa là ký `A || B`, khác với `B || A` nếu các byte khác nhau. Không tự thêm dấu phân cách giữa các phần; nếu giao thức cần separator, phải đưa các byte separator ấy vào dữ liệu được ký.

### Bước 4 — Kết thúc: `sign`

```java
byte[] signatureBytes = signer.sign();
```

`sign()` tính và trả chữ ký dưới dạng `byte[]`. Đối với Ed25519, chữ ký hợp lệ có **64 byte**. Không in trực tiếp các byte như một `String` bằng `new String(signatureBytes)`: chúng là dữ liệu nhị phân, không phải văn bản UTF-8.

Khi cần biểu diễn chữ ký trong JSON hoặc HTTP header, có thể dùng Base64:

```java
String encoded = java.util.Base64.getEncoder()
        .encodeToString(signatureBytes);
byte[] decoded = java.util.Base64.getDecoder().decode(encoded);
```

Base64 chỉ là cách **mã hóa biểu diễn byte**, không cung cấp bí mật hay bảo vệ chống sửa đổi. Bên nhận phải giải mã để lấy chữ ký và xác minh; không thể thay bước `verify` bằng việc “Base64 decode thành công”.

## 3. Trạng thái của Signature và thứ tự lời gọi

Một đối tượng `Signature` không phải hàm stateless. Có thể hình dung vòng đời như sau:

```text
getInstance("Ed25519")
        |
        v
  UNINITIALIZED
     |        |
 initSign   initVerify
     |        |
     v        v
    SIGN    VERIFY
     |        |
 update(*)  update(*)
     |        |
     v        v
    sign()   verify(signature)
     |        |
     +--------+
   Sau khi kết thúc thành công:
   quay về trạng thái sau initSign / initVerify tương ứng
   (bộ dữ liệu đang tích lũy đã được reset)
```

`(*)` có thể gọi `update` **0 lần hoặc nhiều lần** sau khởi tạo; nếu không cung cấp dữ liệu, bạn đang làm việc với **thông điệp rỗng**, không phải thông điệp trước đó.

| Trạng thái | Thao tác | Hành vi |
| --- | --- | --- |
| Mới `getInstance`, chưa khởi tạo | `update(...)` | Không hợp lệ; có thể ném `SignatureException` |
| Mới `getInstance`, chưa khởi tạo | `sign()` | Không hợp lệ; `SignatureException` |
| Đã `initSign(privateKey)` | `update(...)` một hoặc nhiều lần | Tiếp tục tích lũy thông điệp để ký |
| Đã `initSign(privateKey)` | `sign()` | Trả chữ ký; **sau khi thành công** reset về trạng thái sau `initSign` |
| Đã `initVerify(publicKey)` | `update(...)` | Tiếp nhận thông điệp để xác minh |
| Đã `initVerify(publicKey)` | `verify(signature)` | Trả `boolean` hoặc báo lỗi nếu input/engine có vấn đề; **sau khi kết thúc thành công** reset về trạng thái sau `initVerify` |
| Đang ở VERIFY | `sign()` | Sai chế độ; `SignatureException` |
| Đang ở SIGN | `initSign(newKey)` | Khởi tạo lại cho lần ký mới, bỏ trạng thái message cũ |
| Đang ở VERIFY | `initSign(privateKey)` | Chuyển từ VERIFY sang SIGN và khởi tạo lại |

**Điểm cần nhớ:** Sau `sign()` thành công, đối tượng **vẫn có thể dùng tiếp với cùng private key** bằng `update(newMessage)` rồi `sign()`. Nhưng nó **không giữ các byte của lần ký trước** để ghép với lần tiếp theo. Tương tự, sau một lần `verify(...)` hoàn tất, có thể `update` cho thông điệp kế tiếp với cùng public key.

Nếu gọi `sign()` lần thứ hai **không có `update`**, bạn đang yêu cầu ký thông điệp rỗng chứ không “in lại chữ ký vừa tạo”. Đừng dùng `Signature` như nơi lưu chữ ký để lấy lại ở lần gọi sau.

**Quy tắc thực hành:** Mặc dù JCA cho phép tái sử dụng sau khi hoàn tất, trong code xử lý từng request, dễ kiểm soát nhất là **tạo một `Signature` mới hoặc chủ động `initSign`/`initVerify` lại cho mỗi giao dịch**. Khi xảy ra exception ở giữa vòng đời, nên khởi tạo lại thay vì suy đoán trạng thái bị bỏ dở.

## 4. Đường xác minh đối xứng: `initVerify → update → verify`

Để xác minh một chữ ký đã được tạo:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(keyPair.getPublic());
verifier.update(message);
boolean accepted = verifier.verify(signatureBytes);
```

Những yêu cầu phải đồng thời đúng:

1. Public key đúng cặp với private key đã ký và được bên nhận tin cậy theo chính sách ứng dụng.
2. Thuật toán (và tham số nếu thuật toán yêu cầu) đúng.
3. Byte của thông điệp được cung cấp cho `update` phải **giống hệt** những byte đã ký, theo cùng thứ tự.
4. `signatureBytes` chính là byte chữ ký, không phải chữ ký Base64 còn đang ở dạng ký tự.

Kết quả `false` có nghĩa chữ ký **không hợp lệ đối với dữ liệu/khóa/thuật toán đang xác minh**. Một chữ ký có cấu trúc không hợp lệ, lỗi provider hoặc trạng thái API sai có thể tạo **exception**, vì vậy không nên dùng `catch (Exception) { return true; }` hay coi mọi lỗi của thư viện là xác minh thành công.

### Tại sao `update` phải nhận đúng byte ở hai phía?

Ví dụ cùng chuỗi hiển thị nhưng không cùng byte:

```java
byte[] unix = "A\nB".getBytes(StandardCharsets.UTF_8);
byte[] windows = "A\r\nB".getBytes(StandardCharsets.UTF_8);
```

Hai giá trị trên **khác nhau**. Chữ ký tính trên `unix` không thể được xác minh hợp lệ bằng `windows` chỉ vì nội dung khi in trên màn hình trông tương tự.

Với JSON, thay đổi thứ tự trường hoặc khoảng trắng cũng thay đổi **byte raw**. Nếu ứng dụng ký một biểu diễn canonical JSON, hai phía phải thống nhất chính xác quy tắc canonicalization trước khi ký/xác minh. `Signature` tự nó không thực hiện canonicalization.

## 5. Chương trình Java hoàn chỉnh kiểm chứng vòng đời

Tạo tệp **`SignatureLifecycleDemo.java`** bằng UTF-8. Chương trình sau dùng Ed25519 từ Java 15; để dễ kiểm thử và tránh lưu trữ khóa ngoài phạm vi bài học, nó tạo một cặp khóa mới khi chạy. **Đây là khóa mẫu tạm thời**; mã production phải quản lý private key an toàn và dùng public key được tin cậy.

Chương trình chứng minh:

- `initSign` → nhiều lần `update` → `sign`.
- Xác minh thành công bằng đúng public key.
- Phát hiện thông điệp bị sửa.
- `verify` và `sign` reset trạng thái sau khi hoàn tất, không giữ message cũ.
- Không thể xác minh chữ ký bằng public key của một cặp khóa độc lập.
- Lệnh `update` trước khi khởi tạo và `sign` trong chế độ xác minh là không hợp lệ.
- Gọi lại `initSign` loại bỏ dữ liệu thông điệp đang chờ từ lượt trước.

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.SignatureException;

public class SignatureLifecycleDemo {
    private static void check(String label, boolean passed) {
        if (!passed) {
            throw new AssertionError(label + " FAILED");
        }
        System.out.println(label + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keyPair = generator.generateKeyPair();

        byte[] message = "Xin chào Java 15".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keyPair.getPrivate());
        signer.update(message, 0, 4);
        signer.update(message, 4, message.length - 4);
        byte[] signature = signer.sign();
        check("signatureLength", signature.length == 64);

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keyPair.getPublic());
        verifier.update(message);
        check("validSignature", verifier.verify(signature));

        byte[] tampered = message.clone();
        tampered[0] ^= 1;
        verifier.update(tampered);
        check("tamperRejected", !verifier.verify(signature));

        verifier.update(message);
        check("validAfterFailedVerify", verifier.verify(signature));

        byte[] second = "Thong diep thu hai".getBytes(StandardCharsets.UTF_8);
        signer.update(second); // sign() reset về trạng thái sau initSign
        byte[] secondSignature = signer.sign();

        verifier.update(second);
        check("signerReused", verifier.verify(secondSignature));

        verifier.update(message);
        check("noPreviousMessageLeak",
                !verifier.verify(secondSignature));

        KeyPair unrelated = generator.generateKeyPair();
        verifier.initVerify(unrelated.getPublic());
        verifier.update(message);
        check("wrongKeyRejected", !verifier.verify(signature));

        Signature uninitialized = Signature.getInstance("Ed25519");
        boolean updateBeforeInitRejected = false;
        try {
            uninitialized.update(message);
        } catch (SignatureException expected) {
            updateBeforeInitRejected = true;
        }
        check("updateBeforeInitRejected", updateBeforeInitRejected);

        boolean signInVerifyModeRejected = false;
        try {
            verifier.sign();
        } catch (SignatureException expected) {
            signInVerifyModeRejected = true;
        }
        check("signInVerifyModeRejected", signInVerifyModeRejected);

        // Reinitialization discards any buffered message.
        signer.update("discarded".getBytes(StandardCharsets.UTF_8));
        signer.initSign(keyPair.getPrivate());
        byte[] third = "Third".getBytes(StandardCharsets.UTF_8);
        signer.update(third);
        byte[] thirdSignature = signer.sign();
        verifier.initVerify(keyPair.getPublic());
        verifier.update(third);
        check("reinitDiscardsPendingData",
                verifier.verify(thirdSignature));
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn (chỉ dùng API có từ Java 15):

```bash
javac --release 17 -encoding UTF-8 SignatureLifecycleDemo.java
java SignatureLifecycleDemo
```

**Stdout chính xác:**

```text
signatureLength=PASS
validSignature=PASS
tamperRejected=PASS
validAfterFailedVerify=PASS
signerReused=PASS
noPreviousMessageLeak=PASS
wrongKeyRejected=PASS
updateBeforeInitRejected=PASS
signInVerifyModeRejected=PASS
reinitDiscardsPendingData=PASS
```

Các giá trị `PASS` không phụ thuộc vào chữ ký nhị phân hoặc public key ngẫu nhiên được tạo khi chạy. Chữ ký Ed25519 luôn có chiều dài 64 byte; các kiểm tra còn lại dùng tính hợp lệ qua `verify` thay vì hardcode chữ ký.

### Đọc kết quả đúng cách

- `signatureLength=PASS` cho biết đối tượng đã ký bằng Ed25519 và byte chữ ký có kích thước mong đợi.
- `validSignature=PASS` xác nhận chuỗi `initVerify → update → verify` thành công.
- `tamperRejected=PASS` cho thấy một byte thông điệp bị sửa làm chữ ký cũ không còn khớp.
- `validAfterFailedVerify=PASS` cho thấy verifier đã sẵn sàng cho lượt cập nhật tiếp theo sau một phép xác minh trả `false`.
- `signerReused=PASS` chứng minh `sign()` thành công reset trạng thái đủ để ký thông điệp khác bằng cùng khóa.
- `noPreviousMessageLeak=PASS` cho thấy chữ ký của thông điệp thứ hai không xác minh hợp lệ với thông điệp thứ nhất.
- `wrongKeyRejected=PASS` kiểm tra không thể dùng khóa công khai của cặp khóa khác để xác minh chữ ký trong ví dụ.
- `updateBeforeInitRejected=PASS` và `signInVerifyModeRejected=PASS` chứng minh các lỗi vòng đời được phát hiện bằng `SignatureException`.
- `reinitDiscardsPendingData=PASS` chứng minh khởi tạo lại không cộng dồn dữ liệu cũ vào thông điệp mới.

**Không dùng mẫu này để lưu khóa thực:** Việc `KeyPairGenerator` tạo khóa mỗi lần chỉ phù hợp với ví dụ/test; dịch vụ ký thật cần quản lý khóa, phân quyền, lưu trữ bảo vệ và chiến lược xoay vòng khóa. Không log private key hay đưa private key vào source code.

## 6. Ký dữ liệu lớn bằng nhiều lần update

Khi ký một file hoặc một stream, không cần gọi `readAllBytes()` rồi giữ cả file trong bộ nhớ. Có thể cập nhật theo buffer:

```java
// Mã minh họa bên trong phương thức đã có:
// Signature signer; java.nio.file.Path file;
// signer đã được initSign(privateKey).
try (java.io.InputStream in = java.nio.file.Files.newInputStream(file)) {
    byte[] buffer = new byte[8192];
    int count;
    while ((count = in.read(buffer)) != -1) {
        if (count > 0) {
            signer.update(buffer, 0, count);
        }
    }
}
byte[] signatureBytes = signer.sign();
```

Những điểm cần đúng:

- `count` là số byte thực sự đã đọc, không phải kích thước buffer. Gọi `update(buffer)` cho mọi vòng lặp có thể ký thêm các byte **cũ còn lại** của lần đọc trước.
- `update(buffer, 0, count)` giúp không lẫn phần thừa khi lượt đọc cuối ngắn hơn 8192 byte.
- Thứ tự chunk phải đúng như thứ tự byte trong file; chia chunk khác nhau **không thay đổi** thông điệp nếu các byte ghép lại y hệt.
- Nếu việc đọc file thất bại, không nên tiếp tục `sign()` trên dữ liệu chỉ được đọc một phần rồi coi đó là chữ ký của toàn file.
- Khi xác minh, phải đọc/chuẩn hóa **cùng phiên bản dữ liệu**; nếu file thay đổi giữa lúc ký và lúc xác minh, phép xác minh có thể thất bại.
- Với dữ liệu không tin cậy, kiểm soát kích thước, thời gian xử lý và lỗi I/O theo yêu cầu hệ thống.

`Signature.update(ByteBuffer)` cũng được hỗ trợ nếu dữ liệu vốn đang nằm trong `ByteBuffer`. Sau khi cập nhật thành công, `position` buffer sẽ tiến tới `limit`; cần tính đến sự thay đổi vị trí này khi code còn dùng lại buffer.

## 7. Nên tạo Signature mới hay tái sử dụng?

Cả hai cách sau đều hợp lệ khi dùng đúng trạng thái:

**Cách A — một đối tượng cho một lần ký, đơn giản để review:**

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(message);
byte[] signature = signer.sign();
```

**Cách B — tái sử dụng cho nhiều thông điệp, hiểu rõ reset:**

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);

signer.update(firstMessage);
byte[] firstSignature = signer.sign(); // Reset về trạng thái sau initSign

signer.update(secondMessage);
byte[] secondSignature = signer.sign();
```

Hai đoạn này **chỉ minh họa** và giả định đã có biến `privateKey`, `message` hoặc `firstMessage`/`secondMessage` phù hợp. Chúng không phải hai chương trình có thể chạy độc lập.

Trong dịch vụ nhiều request, **không chia sẻ cùng một đối tượng `Signature` khả biến giữa các thread** nếu không có cơ chế bảo vệ vòng đời phù hợp. `Signature` giữ cả trạng thái thuật toán, khóa và các byte đã `update`; hai luồng cùng thao tác dễ trộn dữ liệu.

Có thể tạo mới đối tượng per request hoặc thiết kế việc tái sử dụng theo cách tránh chia sẻ giữa các yêu cầu đồng thời. Nếu phải đổi khóa hoặc nghi ngờ dữ liệu đang tích lũy, gọi lại `initSign`/`initVerify` hoặc tạo đối tượng mới. Đừng chỉ “xóa” dữ liệu bằng cách gọi `sign()` vì thao tác đó thật sự tạo một chữ ký.

## 8. Lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| `getInstance` rồi gọi ngay `update` | Đối tượng chưa được khởi tạo; `SignatureException` | Gọi `initSign(privateKey)` trước |
| `initVerify(publicKey)` rồi gọi `sign()` | Đang ở chế độ VERIFY, không phải SIGN | Ký bằng `initSign(privateKey)` |
| Ký chuỗi bằng `getBytes()` không chỉ rõ charset | Byte có thể khác theo cấu hình/môi trường | Dùng `StandardCharsets.UTF_8` và cùng hợp đồng hai phía |
| Ký bằng nhiều `update` nhưng sai offset/count | Byte ký bị thiếu, lặp hoặc thừa | Dùng `update(buffer, 0, bytesRead)`; kiểm soát thứ tự |
| Nghĩ `sign()` lần hai trả lại chữ ký cũ | Sau `sign()` thành công, dữ liệu message đã reset | Lưu `byte[]` chữ ký nếu cần dùng lại |
| Sau `sign()`, cập nhật dữ liệu mới nhưng tưởng dữ liệu cũ còn | Ký message mới độc lập | Dựa vào reset có chủ đích hoặc tạo Signature mới |
| Tái sử dụng một `Signature` qua nhiều thread | Có thể trộn trạng thái các thông điệp | Dùng instance riêng cho từng luồng/giao dịch |
| Gọi `verify` trên dữ liệu đã parse rồi serialize lại tùy ý | Byte không giống bản ký | Định nghĩa serialization/canonicalization thống nhất |
| Dùng public key lấy trực tiếp từ payload không tin cậy | Attacker có thể thay cả khóa và chữ ký | Xác thực nguồn public key theo trust policy |
| Dùng `new String(signatureBytes)` để truyền chữ ký | Byte nhị phân bị biến dạng khi decode/encode | Dùng Base64/bytes và giải mã trước khi verify |
| Thấy `verify(...) == false` nhưng coi request thành công | Chữ ký không hợp lệ đối với dữ liệu/khóa | Từ chối, ghi lý do phù hợp và không công nhận nội dung |
| Chỉ so sánh hai `byte[]` chữ ký để kiểm thử | Có thuật toán chữ ký dùng ngẫu nhiên hợp lệ | Kiểm thử bằng `verify` và các trường hợp tamper/wrong key |
| Lấy private key từ một file plaintext trong repo | Rủi ro lộ khóa, không thể thu hồi đơn giản | Dùng kho khóa/KMS/HSM hoặc hệ thống quản lý khóa phù hợp |
| Dùng thuật toán chữ ký cũ cho thiết kế mới | Có thể không đạt yêu cầu bảo mật hiện nay | Chọn thuật toán được chấp nhận trong chính sách, ví dụ Ed25519 hoặc RSA-PSS phù hợp |

## 9. Chọn thuật toán và kiểm thử tương thích

Ví dụ này dùng **Ed25519**. Với hệ thống có yêu cầu tương tác với PKI/RSA, một thuật toán hiện hành khác là **RSASSA-PSS** nhưng phải thỏa thuận rõ tham số hash, MGF và độ dài salt. Không được cho rằng hai phía chỉ cần ghi cùng một chuỗi thuật toán là mọi tham số sẽ tự khớp.

Điều quan trọng hơn tên thuật toán là **cấu hình thống nhất toàn hệ thống**:

- Bên ký và bên xác minh dùng thuật toán/parameters tương ứng.
- Public key phù hợp và được tin cậy; private key được bảo vệ.
- Hai bên xử lý chính xác **byte message**; nếu ký JSON, biết rõ ký raw JSON hay biểu diễn canonical.
- Chữ ký được truyền trong cấu trúc nhị phân/Base64 có metadata cần thiết và được kiểm tra đầy đủ.
- API không rơi về cơ chế yếu hoặc thuật toán cũ khi thiếu hỗ trợ; nếu thuật toán/provider không khả dụng, phải xử lý lỗi rõ ràng.

Ed25519 không cần ứng dụng băm thông điệp trước bằng `MessageDigest` trong quy trình ký thông thường; `Signature` triển khai thuật toán ký trên dữ liệu được `update`. **Đừng tự băm trước hoặc băm hai lần** nếu giao thức không quy định rõ cơ chế prehash tương thích: chữ ký xác minh trên byte khác sẽ thất bại.

Ngoài unit test, với hệ thống thực tế cần kiểm thử cả **dữ liệu ký và khóa do bên còn lại cung cấp**, test trên đúng JDK/provider của môi trường triển khai và test trường hợp chữ ký bị sửa, dữ liệu bị sửa, khóa sai, thuật toán không được hỗ trợ.

## 10. Unit test thực tế và cách kiểm tra trạng thái

Với JUnit Jupiter đã cấu hình trong dự án, một test có thể viết theo mô hình sau:

```java
// Trích đoạn trong lớp kiểm thử JUnit 5, cần imports JUnit và Java Security:
@Test
void signThenVerifyWithMatchingKey() throws Exception {
    KeyPair keyPair = KeyPairGenerator.getInstance("Ed25519")
            .generateKeyPair();
    byte[] message = "payload".getBytes(StandardCharsets.UTF_8);

    Signature signer = Signature.getInstance("Ed25519");
    signer.initSign(keyPair.getPrivate());
    signer.update(message);
    byte[] signature = signer.sign();

    Signature verifier = Signature.getInstance("Ed25519");
    verifier.initVerify(keyPair.getPublic());
    verifier.update(message);

    assertTrue(verifier.verify(signature));
}
```

Đoạn trên là **mã minh họa JUnit**, không phải tệp độc lập để biên dịch bằng `javac` thuần. Một suite tốt nên thêm các test:

- `update` gọi nhiều chunk tạo được chữ ký xác minh hợp lệ với đúng full message.
- Thay đúng một byte thông điệp khiến `verify` thất bại.
- Khóa công khai không tương ứng không xác minh được.
- Lời gọi trước `initSign` hoặc sai SIGN/VERIFY mode ném đúng loại exception.
- Sau khi `sign()` và `verify()` thành công, lần xử lý tiếp theo không giữ byte message cũ.
- Với dữ liệu đường mạng/file, byte sau canonicalization hoặc encoding chính là byte được ký.

Không nên phụ thuộc vào **chuỗi thông báo exception** hay hardcode chữ ký nhị phân khi test mục đích là xác nhận vòng đời; xét kiểu lỗi và hiệu lực chữ ký qua `verify` thường ổn định hơn.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Sau `Signature.getInstance("Ed25519")`, có thể gọi thẳng `sign()` mà không `initSign` không?

**Đáp án:** Không. Đối tượng chưa khởi tạo chế độ ký và khóa riêng, `sign()` sẽ không thực hiện hợp đồng ký hợp lệ.

**Câu 2.** Hai lần `update` theo các đoạn 4 byte rồi phần còn lại có khác với một lần `update(message)` không?

**Đáp án:** Không nếu thứ tự và toàn bộ byte nhận vào **giống hệt**. `update` chỉ cung cấp phần tiếp theo của cùng thông điệp.

**Câu 3.** Sau khi gọi `sign()` thành công, `sign()` tiếp ngay mà không `update` có trả lại chữ ký cũ không?

**Đáp án:** Không. Trạng thái xử lý message đã reset về lúc sau `initSign`. Gọi ký tiếp mà không cập nhật dữ liệu là ký thông điệp rỗng, không phải truy xuất chữ ký trước.

**Câu 4.** Public key được lấy từ chính request chưa được xác thực; `verify(...) == true` có đủ chứng minh người gửi là đối tác tin cậy không?

**Đáp án:** Không. Chữ ký hợp lệ với **khóa do request đưa ra** không chứng minh khóa đó là của đối tác được tin cậy. Cần chính sách xác thực public key.

**Câu 5.** Tại sao khi ký một file theo các chunk `update(buffer, 0, count)` lại an toàn hơn `update(buffer)`?

**Đáp án:** Lượt đọc cuối có thể nhận ít byte hơn chiều dài buffer; `update(buffer)` sẽ vô tình đưa cả byte thừa hoặc byte cũ vào thông điệp, còn `count` ghi đúng số byte đã đọc.

**Câu 6.** `verify` trả `false` khi dữ liệu bị sửa. Có thể tiếp tục `update(messageGoc)` và `verify(chuKy)` với cùng verifier không?

**Đáp án:** Có, sau một lần `verify` hoàn tất theo hợp đồng API, trạng thái được reset về sau `initVerify`. Chương trình hoàn chỉnh đã kiểm tra trường hợp này.

## Ghi nhớ

Vòng đời ký hợp lệ của `Signature` là **`getInstance → initSign(privateKey) → update(bytes)* → sign()`**. Phía xác minh dùng **`getInstance → initVerify(publicKey) → update(chính xác các bytes)* → verify(signatureBytes)`**. `sign` trả chữ ký `byte[]`; cả `sign` và `verify` sau khi hoàn tất sẽ reset trạng thái xử lý dữ liệu để có thể bắt đầu thông điệp mới với khóa đã chọn. Khi đổi khóa hoặc cần cô lập giao dịch, hãy khởi tạo lại. Quan trọng nhất: **đúng khóa, đúng thuật toán, đúng byte và đúng thứ tự gọi API**; mọi trường hợp khác phải bị kiểm tra và xử lý như lỗi thực sự.

### Tài liệu chính thức

- [Java SE 17 — java.security.Signature: initSign, update, sign, initVerify và verify](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [Java SE 17 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html)
- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA), chuẩn từ Java 15](https://openjdk.org/jeps/339)
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html)
- [Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
