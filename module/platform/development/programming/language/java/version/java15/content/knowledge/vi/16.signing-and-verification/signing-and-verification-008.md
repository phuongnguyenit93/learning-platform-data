# Kết quả false và SignatureException khi xác minh chữ ký số trong Java

## Mục tiêu

Với API `java.security.Signature`, lời gọi `verify(...)` **không chỉ có hai kết cục “đúng/sai” đơn giản**. Khi đối tượng đã khởi tạo đúng chế độ và phép kiểm tra được xử lý bình thường, nó trả `true` hoặc `false`. Trong các tình huống khác—chẳng hạn chưa khởi tạo, sai chế độ, chữ ký sai định dạng hoặc engine không xử lý được dữ liệu—lời gọi có thể ném **`SignatureException`**. Ngoài ra, một số lỗi đối số không hợp lệ được báo bằng **`IllegalArgumentException`**.

Đây là bài học thuộc nhóm **Ký và xác minh** trong Java 15. Bạn sẽ:

1. Phân biệt chính xác ý nghĩa của `verify(...) == false` và `SignatureException`.
2. Nhớ vòng đời `getInstance → initVerify → update → verify`, trạng thái reset sau một lần xác minh hoàn tất và cách phục hồi sau exception.
3. Hiểu vì sao **một chữ ký sai có thể cho `false`**, nhưng **chữ ký sai cấu trúc có thể cho `false` *hoặc* ném exception** tùy thuật toán/provider.
4. Xử lý ba kết quả nghiệp vụ rõ ràng: **hợp lệ**, **không hợp lệ**, **lỗi xử lý**; không để lỗi biến thành xác thực thành công.
5. Viết chương trình chạy được trên **JDK 17+** với **Ed25519**, một thuật toán được Java hỗ trợ từ Java 15, và kiểm thử 11 tình huống.

**Giới hạn kiến thức hiện hành:** Các API `Signature`, `KeyPairGenerator` và Ed25519 vẫn được sử dụng trong Java hiện đại. Bài không đề xuất chữ ký MD5 hay SHA-1 cho thiết kế mới, không dùng API nội bộ/legacy và không phụ thuộc cấu hình preview.

## 1. Ý nghĩa của ba khả năng từ verify

Giả sử bạn có một `Signature verifier` đang ở trạng thái VERIFY, một khóa công khai đã được tin cậy, một mảng byte thông điệp và mảng byte chữ ký:

```java
boolean valid = verifier.verify(signatureBytes);
```

Hành vi của API được mô tả như sau:

| Kết cục | Ý nghĩa API | Xử lý bảo mật |
| --- | --- | --- |
| Trả `true` | Chữ ký được xác minh thành công đối với byte thông điệp, khóa công khai và thuật toán đang dùng | Chỉ tiếp tục khi **khóa được tin cậy**, thông điệp hợp lệ và mọi điều kiện nghiệp vụ cũng đạt |
| Trả `false` | Chữ ký **không xác minh được** đối với dữ liệu/khóa/thuật toán đang kiểm tra | **Từ chối**; không công nhận thông điệp đã được ký hợp lệ |
| Ném `SignatureException` | Engine không hoàn tất bình thường: có thể chưa khởi tạo, sai trạng thái, chữ ký sai định dạng/loại, hoặc thuật toán/provider không xử lý được dữ liệu | **Từ chối**, đồng thời ghi nhận/giám sát đây là lỗi xử lý hoặc đầu vào; không chuyển thành `true` |

**Cốt lõi:** `false` là **kết quả boolean của một lần kiểm tra chữ ký**; `SignatureException` là **một ngoại lệ báo phép kiểm tra không hoàn tất bình thường theo hợp đồng API**. Chúng đều không cấp quyền chấp nhận dữ liệu, nhưng **không nên coi chúng có cùng ý nghĩa vận hành**.

Lỗi thường gặp:

```java
// Sai nghiêm trọng: lỗi lại biến thành chấp nhận.
try {
    return verifier.verify(signatureBytes);
} catch (SignatureException error) {
    return true; // TUYỆT ĐỐI KHÔNG
}
```

Ngược lại, việc luôn ném mọi `false` thành exception cũng làm mất thông tin: một chữ ký không khớp là tình huống đầu vào không được chấp nhận **thông thường** trong nhiều giao thức, không nhất thiết là bug hệ thống.

## 2. Các điều kiện phải đúng trước khi gọi verify

Đường xác minh chuẩn:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(trustedPublicKey);
verifier.update(messageBytes);
boolean valid = verifier.verify(signatureBytes);
```

Đây là **trích đoạn bên trong một phương thức**, với `trustedPublicKey`, `messageBytes` và `signatureBytes` đã được cung cấp đúng kiểu.

Các bước có ý nghĩa khác nhau:

- `Signature.getInstance("Ed25519")` tạo engine qua JCA provider. Nếu thuật toán không có ở provider đã chọn, nó có thể ném `NoSuchAlgorithmException`.
- `initVerify(PublicKey)` thiết lập **VERIFY mode** và khóa công khai. Nếu khóa không phù hợp, nó có thể ném `InvalidKeyException`.
- `update(...)` đưa các byte thông điệp vào trạng thái xác minh. Có thể gọi nhiều lần theo đúng thứ tự; **chưa tạo kết quả true/false**.
- `verify(signatureBytes)` xử lý chữ ký nhị phân trên các byte đã `update`; trả `boolean` hoặc ném `SignatureException`.

**Tuyệt đối không thay `initVerify` bằng `initSign` rồi kỳ vọng `verify` sẽ hoạt động.** Hai chế độ dùng hai loại khóa khác nhau.

### Sơ đồ trạng thái dễ nhớ

```text
getInstance(...)
      |
      v
UNINITIALIZED
      |
 initVerify(publicKey)
      |
      v
    VERIFY
      |
 update(messageBytes)
      |
      v
 verify(signatureBytes)
      |
      +-- true  --> xác minh hợp lệ, reset dữ liệu message
      |
      +-- false --> không hợp lệ, reset dữ liệu message
      |
      +-- SignatureException --> từ chối; khởi tạo lại
                               hoặc tạo engine mới trước khi tái sử dụng
```

Một lời gọi `verify` **hoàn tất với giá trị boolean** làm đối tượng quay về trạng thái như sau `initVerify`: có thể `update` thông điệp mới và `verify` tiếp bằng cùng khóa. Sau **ngoại lệ**, cách an toàn là gọi lại `initVerify` hoặc tạo `Signature` mới; đừng suy đoán trạng thái buffer hoặc trạng thái provider còn dùng được.

## 3. Trường hợp nào thường cho false?

### 3.1. Thông điệp đã bị sửa sau khi ký

```java
byte[] original = "payload".getBytes(StandardCharsets.UTF_8);
byte[] changed = "Payload".getBytes(StandardCharsets.UTF_8);

// Chữ ký được tạo trên original, nhưng verifier.update(changed).
```

Chữ hoa `P` và chữ thường `p` tạo các byte khác nhau. Một chữ ký hợp lệ của `original` không hợp lệ với `changed`. Với một signature đúng định dạng được tạo từ cặp khóa phù hợp, trường hợp này thông thường cho `verify(...) == false`.

Các thay đổi khác cũng ảnh hưởng byte: thêm dấu cách, đổi line ending `\n` sang `\r\n`, thay thứ tự trường JSON hoặc đổi cách mã hóa chuỗi.

### 3.2. Sử dụng public key không cùng cặp với private key ký

Nếu thông điệp được ký bằng private key của A nhưng bên nhận xác minh bằng public key của B, phép kiểm tra không khớp và thường trả `false` với chữ ký đúng định dạng.

**Phân biệt:** public key B là một **khóa hợp lệ về cấu trúc** nhưng **không phải khóa đúng**. Lỗi này khác `InvalidKeyException` xảy ra khi `initVerify` không chấp nhận khóa đầu vào. Một public key có định dạng hợp lệ cũng không tự được tin cậy: ứng dụng phải xác minh danh tính/nguồn khóa theo PKI, trust store hoặc chính sách của mình.

### 3.3. Sai byte hoặc thứ tự update

```java
// Bên ký:
signer.update(part1);
signer.update(part2);

// Bên xác minh:
verifier.update(part2);
verifier.update(part1); // Sai thứ tự.
```

Hai bên phải cung cấp **đúng cùng dãy byte**. Việc chia dữ liệu thành nhiều chunk là hợp lệ nếu thứ tự và tổng số byte không đổi; Java không tự thêm separator. Nếu bên ký ghi `A || B` mà bên xác minh ghi `B || A`, chữ ký sẽ không khớp.

### 3.4. Không nên chỉ sửa byte chữ ký một cách tùy ý để chứng minh false

Thay một byte của **thông điệp** là phép kiểm tra âm tương đối ổn định: chữ ký ban đầu vẫn có cấu trúc hợp lệ, nhưng không khớp nội dung mới.

Nếu thay byte của **chính chữ ký**, nó có thể trở thành chữ ký **không đúng dạng encoding hoặc sai độ dài**. Tùy thuật toán và provider, `verify` có thể trả `false` **hoặc ném `SignatureException`**. Vì vậy test “sửa chữ ký phải luôn cho false” không phải giả định có thể áp dụng chung cho mọi thuật toán/provider.

## 4. Khi nào SignatureException xuất hiện?

`SignatureException` là **checked exception** thuộc `java.security`. Tài liệu của `Signature.verify` cho phép exception khi đối tượng chưa được khởi tạo đúng, chữ ký sai mã hóa hoặc sai loại, hay thuật toán không thể xử lý dữ liệu.

### 4.1. Verify trước initVerify

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.verify(signatureBytes); // SignatureException
```

Đối tượng mới chỉ ở trạng thái **UNINITIALIZED**. Chưa có public key phù hợp để xác minh. Đây là **lỗi vòng đời**, không phải kết quả `false` của chữ ký không hợp lệ.

### 4.2. Verify trong chế độ SIGN

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(messageBytes);
signer.verify(signatureBytes); // SignatureException
```

Đây cũng là lỗi vòng đời: đối tượng được khởi tạo để **ký**, nhưng code yêu cầu **xác minh**. Khi muốn xác minh, tạo engine khác hoặc gọi lại `initVerify(publicKey)`.

Đừng cố gắng “bắt Exception rồi thử ngược lại” theo chuỗi không rõ ràng; hãy cấu trúc đường ký/xác minh rõ ngay từ đầu.

### 4.3. Chữ ký bị hỏng định dạng hoặc sai độ dài

Đối với Ed25519, chữ ký chuẩn dài **64 byte**. Một mảng `new byte[0]` không phải chữ ký Ed25519 hợp lệ. Provider có thể ném `SignatureException` khi gặp dạng chữ ký không chấp nhận được; một số engine có thể từ chối bằng `false`.

```java
verifier.initVerify(publicKey);
verifier.update(messageBytes);
try {
    boolean accepted = verifier.verify(new byte[0]);
    // Nếu trả false: chữ ký bị từ chối.
} catch (SignatureException malformed) {
    // Nếu ném exception: cũng phải từ chối, và xử lý lỗi có cấu trúc.
}
```

**Không thiết kế API dựa vào giả định “mọi chữ ký sai độ dài luôn ném `SignatureException`” cho mọi provider**, cũng không mặc định một chữ ký sửa byte bất kỳ chỉ cho `false`. Hợp đồng bảo mật là **chỉ chấp nhận khi trả `true` mà không có lỗi**.

### 4.4. Lỗi của engine/provider trong quá trình xử lý

Một provider có thể không xử lý được đầu vào hoặc gặp lỗi khi thực hiện thuật toán. `SignatureException` cũng là cách API báo một số lỗi đó. Tùy tình huống còn có unchecked exception từ provider; code production không nên che giấu lỗi nghiêm trọng bằng cách trả giá trị chấp nhận.

Phân biệt **kiểu lỗi** giúp chẩn đoán:

| Vị trí / thao tác | Lỗi tiêu biểu | Khác gì `false`? |
| --- | --- | --- |
| `getInstance("UnknownAlg")` | `NoSuchAlgorithmException` | Không lấy được engine |
| `initVerify(invalidKey)` | `InvalidKeyException` | Khóa không phù hợp/được chấp nhận |
| `update(...)` trước khi init | `SignatureException` | Sai trạng thái |
| `verify(...)` trước init hoặc đang ở SIGN | `SignatureException` | Sai trạng thái |
| `verify(...)` với signature sai cấu trúc | `false` **hoặc** `SignatureException` | Đầu vào chữ ký không được chấp nhận |
| `verify(sig, -1, len)` | `IllegalArgumentException` | Tham số vùng cắt không hợp lệ |
| Giải mã Base64 sai cú pháp | `IllegalArgumentException` từ Base64 decoder | Chưa đến bước kiểm tra mật mã |
| `verify(...)` trên chữ ký đúng cấu trúc nhưng không khớp message | `false` | Phép so khớp chữ ký đã trả kết quả âm |

Trong mọi tình huống chưa có kết quả `true`, request **chưa được xác thực**. Có thể phân loại lỗi để giám sát nhưng không được “fallback sang chấp nhận”.

## 5. verify(byte[]) và verify(byte[], offset, length)

Hai overload đều trả `boolean` và có thể ném `SignatureException`. Với gói dữ liệu chứa chữ ký ở một vùng cụ thể:

```java
boolean valid = verifier.verify(signatureBuffer, offset, signatureLength);
```

Lưu ý:

- `offset` là chỉ số bắt đầu, `length` là **số byte**, không phải end index.
- `signatureBuffer` phải khác null; `offset` và `length` không âm; vùng cắt nằm trong mảng.
- Các lỗi vùng cắt như `offset = -1` hoặc `length` vượt mảng gây **`IllegalArgumentException`**, không phải `false`.
- `verify(signatureBytes)` dùng cả mảng byte chữ ký. Việc gọi `verify(signatureBytes, offset, length)` không có nghĩa là bạn đã xác minh luôn thông điệp: thông điệp phải được đưa vào `update` **trước đó**.
- Đừng lẫn vùng cắt chữ ký của `verify` với `update(message, offset, length)`, vốn chọn vùng của **thông điệp được ký/xác minh**.

Nếu nhận đầu vào từ mạng, phải kiểm tra độ dài và cấu trúc gói trước khi cắt vùng. Đối với protocol có giới hạn chữ ký cố định (chẳng hạn Ed25519 64 byte), nên xác thực độ dài đầu vào theo hợp đồng giao thức, rồi vẫn xử lý `verify` có thể trả false hoặc ném exception.

## 6. Thiết kế luồng kết quả nghiệp vụ: VALID, INVALID, ERROR

Một thiết kế dễ kiểm soát hơn việc trộn `false` và exception là phân biệt **ba trạng thái**:

```text
                                  +-- true ------------> VALID
initVerify -> update -> verify ---|
                                  +-- false ------------> INVALID
                                  |
                                  +-- exception --------> ERROR
                                                           (không chấp nhận)
```

Ý nghĩa thực tế:

- **VALID:** thuật toán xác minh chữ ký thành công với public key đã được gắn với danh tính/nguồn tin cậy, và các yêu cầu khác của nghiệp vụ cũng đạt.
- **INVALID:** thuật toán đã chạy và trả kết quả không khớp. Đây có thể là message bị sửa, khóa không đúng, signature không hợp lệ hoặc dữ liệu được canonicalize khác.
- **ERROR:** chưa có kết luận xác minh thành công vì môi trường, trạng thái, input, provider hoặc định dạng làm phép kiểm tra không hoàn tất như mong muốn. Luồng này phải **fail closed** giống INVALID về quyền chấp nhận, nhưng cần thông tin chẩn đoán phù hợp.

Ví dụ mã khung ứng dụng, giả định các biến khóa/byte có sẵn:

```java
enum Verdict { VALID, INVALID, ERROR }

static Verdict classify(
        java.security.PublicKey trustedPublicKey,
        byte[] message,
        byte[] signature) {
    try {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedPublicKey);
        verifier.update(message);
        return verifier.verify(signature)
                ? Verdict.VALID
                : Verdict.INVALID;
    } catch (java.security.GeneralSecurityException ex) {
        // Không tiết lộ dữ liệu nhạy cảm trong log.
        // Ghi loại lỗi để điều tra và từ chối xác thực.
        return Verdict.ERROR;
    }
}
```

Đây là **trích đoạn phương thức**, không phải tệp Java độc lập: nó cần import `java.security.Signature` và khai báo enum trong lớp thích hợp. Trong ứng dụng thật, nên log/giám sát lỗi theo chính sách, trả mã lỗi phù hợp ở boundary API và quyết định có cần chuyển `IllegalArgumentException` (input malformed) sang ERROR riêng. Không “nuốt” lỗi vận hành chỉ để trả `false` mà không có dữ liệu chẩn đoán.

**Chú ý về trust:** việc `verify(...) == true` không tự chứng minh public key thuộc người gửi được mong đợi. Đừng lấy public key từ chính payload chưa xác thực rồi xem mọi chữ ký có thể verify bằng nó là đáng tin.

## 7. Chương trình Java đầy đủ: true, false và exception

Đây là chương trình có thể biên dịch và chạy trên **JDK 17 trở lên**. Nó dùng Ed25519 được hỗ trợ từ Java 15, sinh cặp khóa tạm thời cho mục đích học tập, và kiểm tra cả kết quả boolean, ngoại lệ trạng thái và ngoại lệ đối số.

Chương trình **không phụ thuộc** vào việc provider cụ thể xử lý chữ ký rỗng bằng `false` hay `SignatureException`: cả hai đều được nhận diện là *rejected*. Đây là chủ đích giúp test tránh áp đặt hành vi không được hợp đồng chung bảo đảm.

Lưu tệp **`SignatureResultDemo.java`** bằng UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.SignatureException;

public final class SignatureResultDemo {
    private static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError(label + " failed");
        }
        System.out.println(label + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keys = generator.generateKeyPair();
        byte[] message = "Du lieu can ky".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keys.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();
        check("signatureLength", signature.length == 64);

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        check("validTrue", verifier.verify(signature));

        byte[] changedMessage = message.clone();
        changedMessage[0] ^= 1;
        verifier.update(changedMessage);
        check("changedMessageFalse", !verifier.verify(signature));

        // A completed verify resets to the state after initVerify.
        verifier.update(message);
        check("validAfterFalse", verifier.verify(signature));

        KeyPair unrelated = generator.generateKeyPair();
        verifier.initVerify(unrelated.getPublic());
        verifier.update(message);
        check("wrongKeyFalse", !verifier.verify(signature));

        Signature neverInitialized = Signature.getInstance("Ed25519");
        boolean noInitRejected = false;
        try {
            neverInitialized.verify(signature);
        } catch (SignatureException expected) {
            noInitRejected = true;
        }
        check("verifyBeforeInitException", noInitRejected);

        boolean wrongModeRejected = false;
        try {
            signer.verify(signature);
        } catch (SignatureException expected) {
            wrongModeRejected = true;
        }
        check("verifyInSignModeException", wrongModeRejected);

        Signature malformed = Signature.getInstance("Ed25519");
        malformed.initVerify(keys.getPublic());
        malformed.update(message);
        boolean malformedRejected = false;
        try {
            malformedRejected = !malformed.verify(new byte[0]);
        } catch (SignatureException expected) {
            malformedRejected = true;
        }
        check("malformedRejected", malformedRejected);

        Signature invalidRange = Signature.getInstance("Ed25519");
        invalidRange.initVerify(keys.getPublic());
        invalidRange.update(message);
        boolean invalidRangeRejected = false;
        try {
            invalidRange.verify(signature, -1, signature.length);
        } catch (IllegalArgumentException expected) {
            invalidRangeRejected = true;
        }
        check("badRangeIllegalArgument", invalidRangeRejected);

        // Reinitializing is safe after any failed operation.
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        check("reinitAfterFailure", verifier.verify(signature));

        // Base64 is transport encoding, not verification.
        byte[] decoded = java.util.Base64.getDecoder().decode(
                java.util.Base64.getEncoder().encodeToString(signature));
        verifier.initVerify(keys.getPublic());
        verifier.update(message);
        check("base64RoundTrip", verifier.verify(decoded));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SignatureResultDemo.java
java SignatureResultDemo
```

**Stdout chính xác (đã kiểm chứng):**

```text
signatureLength=PASS
validTrue=PASS
changedMessageFalse=PASS
validAfterFalse=PASS
wrongKeyFalse=PASS
verifyBeforeInitException=PASS
verifyInSignModeException=PASS
malformedRejected=PASS
badRangeIllegalArgument=PASS
reinitAfterFailure=PASS
base64RoundTrip=PASS
```

### Giải thích những kiểm thử mấu chốt

- `validTrue=PASS`: đúng thông điệp, đúng cặp khóa và chữ ký được sinh thành công.
- `changedMessageFalse=PASS`: thay một byte **trong thông điệp**, không sửa byte chữ ký, nên phép xác minh trả kết quả không khớp.
- `validAfterFalse=PASS`: một lần `verify` trả `false` đã kết thúc; engine có thể `update` lại với đúng message và verify thành công, không cần giả định message trước còn nằm trong buffer.
- `wrongKeyFalse=PASS`: chữ ký vẫn đúng dạng Ed25519 nhưng public key đến từ cặp khác.
- `verifyBeforeInitException=PASS`: chưa khởi tạo `initVerify`; không phải trường hợp boolean false.
- `verifyInSignModeException=PASS`: engine đang ở SIGN mode sau `initSign/sign`, nên `verify` bị từ chối.
- `malformedRejected=PASS`: chữ ký rỗng không được chấp nhận; code cho phép engine trả `false` hoặc ném `SignatureException`. Test không áp đặt cơ chế provider cụ thể.
- `badRangeIllegalArgument=PASS`: `offset=-1` vi phạm điều kiện của overload vùng cắt, nên phải bắt **`IllegalArgumentException`**, không gộp với `SignatureException`.
- `reinitAfterFailure=PASS`: khởi tạo lại đúng khóa và đưa vào đúng byte sẽ xác minh thành công.
- `base64RoundTrip=PASS`: Base64 chỉ mã hóa/giải mã chữ ký thành dạng văn bản để vận chuyển; **điểm quyết định vẫn là `verify`**.

Cặp khóa được tạo tạm thời mỗi lần chạy nên bytes chữ ký thay đổi theo khóa; chỉ khẳng định những tính chất ổn định như chiều dài Ed25519 và kết quả xác minh, không hardcode chữ ký nhị phân.

## 8. Lỗi Base64, chữ ký nhị phân và dữ liệu giao thức

Trong nhiều API, chữ ký được truyền qua JSON hoặc HTTP bằng Base64:

```java
String encoded = Base64.getEncoder().encodeToString(signatureBytes);
byte[] bytes = Base64.getDecoder().decode(encoded);
```

Đoạn trích này giả định import `java.util.Base64` và biến `signatureBytes` tồn tại. Bản thân việc decode **không chứng minh chữ ký hợp lệ**. Nếu Base64 bị sai cú pháp, decoder có thể ném `IllegalArgumentException` **trước cả bước gọi `verify`**.

Một luồng nhận dữ liệu hợp lý:

1. Kiểm tra giới hạn kích thước request và cấu trúc payload, tránh cấp phát không kiểm soát.
2. Lấy public key **đã được xác thực nguồn** theo danh tính/key ID phù hợp.
3. Giải mã signature theo encoding giao thức, kiểm tra chiều dài/định dạng tối thiểu được quy định.
4. Xác định **chính xác byte message đã được ký**; tránh parse rồi serialize khác đi nếu giao thức ký raw bytes.
5. Gọi `initVerify → update → verify`.
6. Chỉ chấp nhận khi `verify` trả `true` và các kiểm tra nghiệp vụ đều đạt. Với `false` hoặc exception, từ chối; phân loại lỗi để chẩn đoán, không tiết lộ dữ liệu nhạy cảm trong log.

Với Ed25519, chữ ký chuẩn có độ dài 64 byte. Kiểm tra kích thước là một bước kiểm soát input tốt nhưng **không thay thế xác minh mật mã**. Một mảng ngẫu nhiên dài 64 byte vẫn có thể không hợp lệ.

## 9. Test gì để không nhầm false và exception?

### 9.1. Unit test bảng hành vi

| Test case | Đầu vào/trạng thái | Kỳ vọng |
| --- | --- | --- |
| Đúng chữ ký | đúng message, public key và signature | `verify` trả `true` |
| Message thay đổi | chữ ký cũ, message bị đổi 1 byte | `verify` trả `false` |
| Sai cặp khóa | đúng message/signature, public key khác | `verify` trả `false` |
| Chưa init | `getInstance` rồi `verify` | `SignatureException` |
| Sai mode | `initSign` rồi `verify` | `SignatureException` |
| Signature sai độ dài | ví dụ `new byte[0]` với Ed25519 | Phải **bị từ chối**; `false` hoặc `SignatureException` theo provider |
| Vùng cắt chữ ký sai | `offset < 0` ở overload vùng cắt | `IllegalArgumentException` |
| Sau một lượt `false` | `update` message gốc rồi `verify` lại | `true` nếu chữ ký đúng |
| Sau một exception | khởi tạo lại engine rồi verify đúng | xác minh được, không phụ thuộc trạng thái lỗi trước |
| Chữ ký đi qua Base64 | encode/decode rồi verify | vẫn `true` nếu byte không đổi |

Test nên kiểm tra **kiểu exception chính xác** ở những trường hợp API cam kết. Với chữ ký malformed, đừng mặc định cách provider phân biệt `false` và `SignatureException` nếu đặc tả không bắt buộc một cách duy nhất. Việc bỏ qua khác biệt này dễ khiến test chỉ chạy được trên một engine.

### 9.2. Gợi ý JUnit Jupiter (đã có dependency JUnit)

```java
// Trích đoạn trong lớp kiểm thử có import JUnit và Java Security.
@Test
void tamperedMessageIsNotVerified() throws Exception {
    var keys = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();

    byte[] original = "ok".getBytes(StandardCharsets.UTF_8);
    Signature signer = Signature.getInstance("Ed25519");
    signer.initSign(keys.getPrivate());
    signer.update(original);
    byte[] signature = signer.sign();

    byte[] tampered = "no".getBytes(StandardCharsets.UTF_8);
    Signature verifier = Signature.getInstance("Ed25519");
    verifier.initVerify(keys.getPublic());
    verifier.update(tampered);

    assertFalse(verifier.verify(signature));
}
```

Đây là **mã minh họa trong lớp JUnit**, không tự biên dịch chỉ bằng `javac` nếu dự án chưa có JUnit và import thích hợp. Unit test nêu đúng kỳ vọng `false` của trường hợp message khác; nên thêm test `assertThrows(SignatureException.class, ...)` cho lời gọi verify trước init và sai chế độ.

Không phải trường hợp “không xác minh được” nào cũng nên được biểu diễn bởi cùng một exception ở tầng HTTP. Ứng dụng có thể trả lỗi truy cập thống nhất để tránh tiết lộ thông tin, trong khi giám sát nội bộ vẫn phân biệt lỗi xác minh thông thường, input bị hỏng và lỗi hệ thống.

## 10. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| `catch (SignatureException) { return true; }` | Lỗi xử lý lại cho phép xác thực | **Fail closed**: luôn từ chối nếu chưa có `true` |
| Luôn coi `verify == false` là “provider hỏng” | Một chữ ký không khớp thường là kết quả kiểm tra hợp lệ | Ghi nhận INVALID, không tự quy lỗi hệ thống |
| Nghĩ mọi chữ ký malformed đều chỉ trả `false` | API cho phép `SignatureException` khi chữ ký sai encoding/loại | Xử lý cả boolean và exception |
| Nghĩ mọi chữ ký sai độ dài đều phải ném exception | Phụ thuộc thuật toán/provider | Kiểm tra rejection, không áp đặt một kiểu kết quả mọi nơi |
| Thấy `SignatureException` rồi thử tiếp trên engine cũ | Trạng thái sau lỗi có thể không như dự kiến | `initVerify` lại hoặc tạo engine mới |
| Gọi `verify` trước `initVerify` | Chưa có key, sai state | Khởi tạo đúng mode trước update/verify |
| Gọi `verify` trên signer ở SIGN mode | Không thể xác minh trong chế độ ký | Tạo/verifier instance với `initVerify` |
| Nhầm `verify(sig, offset, len)` với phân đoạn message | Cắt nhầm dữ liệu chữ ký | `update` chọn message; `verify` chọn signature |
| Bắt `SignatureException` để xử lý `offset < 0` | Overload cắt có thể ném `IllegalArgumentException` | Xác thực biên, bắt đúng kiểu lỗi |
| Đưa Base64 string bytes trực tiếp vào `verify` | Byte Base64 khác byte chữ ký gốc | Decode Base64 trước; kiểm tra kích thước |
| Chỉ dùng `verify == true` với public key do attacker tự cung cấp | Chữ ký có thể đúng với khóa không được tin | Xác thực nguồn public key/trust policy |
| Ký chuỗi dùng default charset | Byte giữa hai hệ thống có thể khác | Chọn UTF-8 hoặc chuẩn hóa được hợp đồng yêu cầu |
| So khớp message dựa trên cách hiển thị | Whitespace, newline, JSON field order có thể khác | Kiểm tra raw/canonical bytes thật |
| Chia sẻ một `Signature` instance giữa các luồng | Engine có trạng thái message/khóa, dễ trộn dữ liệu | Tạo mới theo request hoặc bảo vệ state đúng cách |
| Hardcode exact message của exception | Provider/JDK có thể đổi thông báo | Khẳng định kiểu lỗi và nhánh xử lý |

## 11. Bài tập tự kiểm tra

**Bài 1.** Một chữ ký đúng định dạng được tạo trên `"hello"`. Bạn kiểm tra chữ ký đó trên `"Hello"` với cùng public key. Kết quả thông thường là gì?

**Đáp án:** `false` vì byte thông điệp khác nhau; không nên chờ `SignatureException` chỉ vì message bị sửa.

**Bài 2.** Một `Signature` mới lấy từ `getInstance` chưa được `initVerify`. Nếu gọi `verify(signatureBytes)`, nên kiểm tra kết quả nào?

**Đáp án:** Nó báo lỗi trạng thái bằng `SignatureException`, không phải một boolean `false` “chữ ký sai”.

**Bài 3.** Tại sao test với `new byte[0]` không nên luôn yêu cầu `assertFalse(verifier.verify(...))` cho mọi provider?

**Đáp án:** Chữ ký không đúng cấu trúc có thể bị từ chối bằng `false` hoặc `SignatureException` theo thuật toán/provider. Hợp đồng quan trọng là **không chấp nhận chữ ký rỗng**.

**Bài 4.** Sau khi `verify(...)` trả `false` bình thường, có thể dùng cùng verifier với public key cũ để kiểm tra một thông điệp khác không?

**Đáp án:** Có. Một lời gọi `verify` hoàn tất sẽ reset engine về trạng thái sau `initVerify`; cần `update` byte của **thông điệp mới**. Sau exception nên chủ động khởi tạo lại.

**Bài 5.** Lệnh `verify(signatureBytes, -1, signatureBytes.length)` nên báo lỗi gì?

**Đáp án:** `IllegalArgumentException` do tham số vùng cắt không hợp lệ, khác với `SignatureException` do trạng thái hoặc engine kiểm tra chữ ký.

**Bài 6.** Một server trả thành công khi `verify` ném `SignatureException`, vì cho rằng lỗi không chứng minh chữ ký sai. Có đúng không?

**Đáp án:** Không. **Chưa xác minh thành công thì không được chấp nhận**. Server cần fail closed; có thể ghi nhận ERROR khác INVALID để xử lý vận hành, nhưng cả hai đều không cấp quyền tin vào thông điệp.

## Ghi nhớ

`Signature.verify(...)` có ba kết cục thực tế cần phân biệt: **`true`** là đã xác minh được chữ ký trên byte và khóa đang xét; **`false`** là kiểm tra hoàn tất nhưng không khớp; **`SignatureException`** là lỗi khiến phép kiểm tra không hoàn tất bình thường (chẳng hạn sai state hoặc signature sai encoding). Trường hợp chữ ký malformed có thể trả `false` **hoặc** ném exception tùy provider; lỗi vùng cắt của overload còn có thể là `IllegalArgumentException`. Đường an toàn luôn là **`initVerify → update → verify`**, chỉ chấp nhận khi có `true` và khóa đã được xác thực nguồn; sau exception nên khởi tạo lại hoặc tạo instance mới.

### Tài liệu chính thức còn áp dụng

- [Java SE 17 — java.security.Signature: verify, SignatureException và vòng đời](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html)
- [Java SE 17 — SignatureSpi: engineVerify và các dạng lỗi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SignatureSpi.html)
- [Java Cryptography Architecture Reference Guide — Signature states và sử dụng](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html)
- [Java SE 17 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html)
- [JEP 339 — EdDSA chính thức từ Java 15](https://openjdk.org/jeps/339)
