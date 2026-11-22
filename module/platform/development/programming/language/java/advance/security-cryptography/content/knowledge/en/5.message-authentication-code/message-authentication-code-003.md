# 5.3 Sử dụng Mac với init, update, doFinal và quản lý trạng thái

Trong Java Cryptography Architecture (JCA), lớp `javax.crypto.Mac` tính **mã xác thực thông điệp** (*Message Authentication Code*, MAC): một giá trị ngắn được tính từ **khóa bí mật** và **đúng dãy byte của thông điệp**. Khi bên nhận có khóa tương ứng, tính lại MAC và so sánh đúng cách, họ có thể phát hiện thông điệp bị thay đổi hoặc được tạo bởi một bên không sở hữu khóa theo giả định an toàn của thuật toán.

Bài này tập trung vào **vòng đời và trạng thái** của `Mac` trong Java: `getInstance` → `init` → `update` → `doFinal`, khi nào dùng `reset`, cách xử lý nhiều thông điệp, cách cho dữ liệu đi theo từng khối, và cách xác minh MAC. Hiểu đúng trạng thái là điều thiết yếu: cùng một đối tượng `Mac` có thể được tái sử dụng tuần tự **sau khi hoàn tất và reset đúng cách**, nhưng rất dễ tạo MAC sai nếu lẫn byte giữa hai thông điệp hoặc chia sẻ đối tượng cho nhiều luồng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích MAC bảo vệ **tính toàn vẹn và xác thực dựa trên khóa chung**, khác với hash thuần, chữ ký số và mã hóa dữ liệu.
2. Khởi tạo `Mac` với thuật toán HMAC như `HmacSHA256`, khóa `SecretKey` phù hợp và một giao thức xác định.
3. Dùng `update(byte)`, `update(byte[])`, `update(byte[], offset, len)` và `update(ByteBuffer)` để cấp dữ liệu theo từng khối.
4. Phân biệt `doFinal()`, `doFinal(byte[])`, `doFinal(byte[], int)` và hành vi **reset tự động** sau khi hoàn tất.
5. Biết `reset()` loại bỏ dữ liệu **đã update nhưng chưa final**, trong khi `init(...)` thiết lập khóa/tham số và bắt đầu trạng thái mới.
6. Tránh lỗi tái sử dụng `Mac` không an toàn giữa các request/luồng, xử lý exception và phân tách thông điệp.
7. Xác minh tag bằng tính lại MAC trên đúng byte và sử dụng phép so sánh phù hợp với ngữ cảnh bảo mật; tách MAC khỏi chống replay.
8. Kiểm thử một HMAC-SHA-256 với test vector chuẩn, rồi áp dụng vào xử lý file/API trong hệ thống Java.

## 2. MAC, HMAC, hash và chữ ký số

Ký hiệu khái quát:

```text
tag = MAC(secretKey, messageBytes)

sender:   messageBytes + tag
receiver: recomputedTag = MAC(secretKey, receivedMessageBytes)
          -> xác minh tag nhận được với recomputedTag
```

MAC là kết quả của phép tính **có khóa**, khác với `MessageDigest` không cần khóa. HMAC là một cách xây MAC dựa trên hàm băm được chuẩn hóa; `HmacSHA256` sử dụng SHA-256 bên trong cấu trúc HMAC. SHA-256 một mình **không thay thế HMAC** cho xác thực thông điệp và không nên tự thiết kế MAC bằng cách ghép `SHA256(key || message)`.

| Công cụ | Có khóa bí mật? | Mục tiêu | Giới hạn đáng nhớ |
| --- | --- | --- | --- |
| `MessageDigest` / SHA-256 | Không | Tạo digest của dãy byte | Ai cũng tính được digest mới nếu sửa dữ liệu; không xác thực người gửi |
| `Mac` / HMAC-SHA-256 | Có, khóa dùng chung | Phát hiện sửa đổi và xác thực thông điệp giữa các bên có khóa | Hai bên cùng có khóa đều tạo được MAC; không cung cấp tính bí mật hay bằng chứng chống chối bỏ như chữ ký bất đối xứng |
| `Signature` (ví dụ Ed25519) | Khóa riêng để ký, khóa công khai để kiểm | Chữ ký số có thể kiểm bằng khóa công khai | Yêu cầu quản lý cặp khóa và xác thực khóa công khai |
| `Cipher` / AEAD (ví dụ AES-GCM) | Có | Bảo mật và/hoặc xác thực dữ liệu theo cơ chế mã hóa xác thực | Phải quản lý khóa, nonce, AAD và tag đúng cách |

**MAC không mã hóa dữ liệu.** Thông điệp có thể vẫn đọc được khi truyền; dùng TLS hoặc mã hóa thích hợp nếu cần tính bí mật. MAC cũng **không tự ngăn phát lại**: kẻ tấn công có thể gửi lại nguyên thông điệp và tag hợp lệ nếu giao thức không có nonce, counter, thời điểm hoặc cơ chế idempotency và xác minh vòng đời.

Bởi vì hai bên đều giữ khóa HMAC, một MAC hợp lệ chứng tỏ dữ liệu đến từ **một bên có khóa** (trong giả định thuật toán và triển khai an toàn), không chứng minh duy nhất cá nhân nào đã gửi khi nhiều thành phần chia sẻ khóa. Để lập luận về quyền thực hiện nghiệp vụ, vẫn cần danh tính, authorization, phân tách khóa và audit theo ngữ cảnh.

## 3. Kiến trúc API Java: Mac là một đối tượng có trạng thái

Các API liên quan nằm trong JCA/JCE:

```java
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
```

Đây là tập import minh họa, không phải chương trình độc lập. Tên thuật toán thông dụng: `HmacSHA256`; có `HmacSHA384`, `HmacSHA512` và các thuật toán khác tùy provider. **Không dùng tên thuật toán do client tự chọn** mà không kiểm soát, và không dùng HMAC-SHA1 cho thiết kế mới nếu không có yêu cầu tương thích đã được đánh giá.

Chu trình logic:

```text
                  Mac.getInstance("HmacSHA256")
                               |
                               v
                    [Chưa khởi tạo với khóa]
                               |
                         init(secretKey)
                               |
                               v
                    [Đã khởi tạo, rỗng]
                       /             \
                 update(...)       doFinal(input)
                     |                   |
                     v                   |
                  [Đang tích lũy byte]   |
                   /           \         |
             update(...)     doFinal()    |
                 |              |         |
                 v              v         v
            [Tích lũy]       [Sinh tag, reset]
                                 |
                                 v
                         [Đã khởi tạo, rỗng]
```

Mô hình này mô tả **nội dung logic mà đối tượng đã xử lý**, không tiết lộ các buffer nội bộ của provider. MAC có thể tính dần theo từng khối; chương trình không cần tạo một mảng byte chứa toàn bộ file lớn.

### Phân biệt từng phương thức

| Phương thức | Tác dụng | Trạng thái sau khi gọi |
| --- | --- | --- |
| `Mac.getInstance("HmacSHA256")` | Lấy implementation từ provider | Có đối tượng nhưng **chưa dùng được để update/final nếu chưa init** |
| `mac.init(key)` | Cấp khóa và thiết lập trạng thái tính MAC | Đã init, chưa có byte thông điệp; dữ liệu pending trước đó bị loại bỏ khi khởi tạo lại thành công |
| `mac.init(key, params)` | Khởi tạo với tham số thuật toán khi được hỗ trợ | Trạng thái mới theo khóa/tham số; HMAC thông thường không cần tham số riêng |
| `mac.update(byte)` | Đưa một byte vào thông điệp hiện tại | Đang tích lũy dữ liệu |
| `mac.update(byte[])` | Đưa toàn bộ mảng byte vào thông điệp hiện tại | Đang tích lũy dữ liệu |
| `mac.update(data, offset, len)` | Đưa đúng đoạn byte vào thông điệp hiện tại | Đang tích lũy dữ liệu; tránh phải tạo array con |
| `mac.update(ByteBuffer)` | Đưa các byte từ vị trí hiện tại đến limit của buffer | Vị trí buffer tiến đến limit, MAC tích lũy phần dữ liệu đó |
| `mac.doFinal()` | Tính tag của **tất cả byte đã update** | Tự reset về trạng thái sau lần `init` gần nhất |
| `mac.doFinal(input)` | Update thêm **toàn bộ input**, final, trả tag | Tự reset về trạng thái sau `init` |
| `mac.doFinal(output, offset)` | Ghi tag vào mảng đầu ra từ offset; không trả mảng tag | Tự reset về trạng thái sau `init`; output phải đủ `getMacLength()` byte |
| `mac.reset()` | Hủy dữ liệu pending đang update | Đã init, rỗng, **giữ cùng khóa/tham số** |
| `mac.getMacLength()` | Lấy độ dài tag tính theo **byte** | Không thay đổi dữ liệu thông điệp |
| `mac.getAlgorithm()` | Trả tên thuật toán đối tượng đang sử dụng | Không thay đổi dữ liệu thông điệp |

**Hai hành vi cần nhớ nhất:**

- `doFinal()` và các biến thể sau khi hoàn tất sẽ **tự reset** đối tượng để có thể tính thông điệp mới với khóa/tham số đã dùng ở `init`. Không cần `init` lại với cùng khóa sau mỗi `doFinal` chỉ để reset, dù trong code xử lý request tách biệt thường dễ kiểm soát hơn nếu tạo instance mới.
- `reset()` **không trả về tag**, chỉ bỏ phần dữ liệu đã `update`. Gọi `reset` trước `doFinal` làm mất dữ liệu pending. `reset` không đổi khóa và không phải thao tác xóa khóa khỏi bộ nhớ.

Gọi `update` hoặc `doFinal` khi đối tượng chưa được khởi tạo có thể gây `IllegalStateException`. `init` với khóa sai loại/không được hỗ trợ có thể ném `InvalidKeyException`; việc dùng `init(key, params)` có thể liên quan `InvalidAlgorithmParameterException`. Với output buffer thiếu dung lượng, `doFinal(output, offset)` có thể ném `ShortBufferException`. Nên kiểm tra và xử lý lỗi tại ranh giới ứng dụng, không nuốt exception rồi xem như MAC hợp lệ.

## 4. Chuỗi ví dụ nhỏ: hiểu chính xác update và doFinal

Giả sử `mac` đã được khởi tạo bằng HMAC-SHA-256 và khóa hợp lệ.

### 4.1 Nhiều update là một thông điệp ghép nối

```java
mac.update("order=".getBytes(StandardCharsets.UTF_8));
mac.update("123".getBytes(StandardCharsets.UTF_8));
byte[] tag = mac.doFinal();
```

Đây là đoạn mã minh họa (biến `mac` và các import đã có). Tag ở đây tương đương với HMAC của đúng chuỗi byte UTF-8 `order=123`. **Hai lời gọi `update` không tạo hai tag độc lập**; chúng đang tạo một thông điệp duy nhất.

### 4.2 doFinal(input) nối input vào phần đã update

```java
mac.update("A".getBytes(StandardCharsets.UTF_8));
byte[] tag = mac.doFinal("B".getBytes(StandardCharsets.UTF_8));
```

Tag này xác thực `AB`, **không phải chỉ `B`**. Nếu ý định tính MAC chỉ cho `B`, không được giữ `A` pending từ một thao tác trước. Sau `doFinal`, một lần `mac.doFinal("B".getBytes(UTF_8))` mới trên cùng đối tượng đã reset sẽ xử lý riêng `B`.

### 4.3 reset hủy dữ liệu pending

```java
mac.update("draft".getBytes(StandardCharsets.UTF_8));
mac.reset();
byte[] tag = mac.doFinal("final".getBytes(StandardCharsets.UTF_8));
```

Tag cuối là HMAC của `final`. Đây là cách hủy một thao tác chưa hoàn tất trước khi dùng lại **cùng khóa**. Nó không thay thế việc tạo context mới cho request độc lập, cũng không có nghĩa là khóa nhạy cảm đã được xóa khỏi JVM.

### 4.4 init thiết lập một vòng đời mới

```java
mac.init(otherSecretKey);
mac.update(messageBytes);
byte[] tag = mac.doFinal();
```

Đây là đoạn mã minh họa; `otherSecretKey` là `SecretKey` phù hợp thuật toán và `messageBytes` là `byte[]`. Việc `init` lại thay khóa/tham số và bỏ trạng thái xử lý thông điệp cũ; đừng dùng chung một `Mac` rồi đổi khóa liên tục giữa nhiều request đồng thời.

## 5. Ví dụ Java 17+ chạy độc lập, có test vector HMAC-SHA-256

Ví dụ dưới đây dùng **test vector RFC 4231**: key gồm 20 byte `0b`, message ASCII `Hi There`, expected tag là `b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7`.

**Chú ý:** khóa cố định trong ví dụ **chỉ dành cho kiểm thử**. Hệ thống thật cần key bí mật được tạo ngẫu nhiên bằng nguồn phù hợp và được bảo vệ trong secret manager/KMS/HSM hoặc vùng bảo vệ tương đương.

Lưu thành file **`MacLifecycleDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MacLifecycleDemo {
    private static final String ALGORITHM = "HmacSHA256";

    static Mac newMac(byte[] key) throws GeneralSecurityException {
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(key, ALGORITHM));
        return mac;
    }

    public static void main(String[] args) throws Exception {
        byte[] testKey = HexFormat.of().parseHex("0b".repeat(20));
        byte[] message = "Hi There".getBytes(StandardCharsets.US_ASCII);
        Mac mac = newMac(testKey);

        mac.update(message, 0, 2);
        ByteBuffer remainder = ByteBuffer.wrap(message, 2, message.length - 2);
        mac.update(remainder);
        byte[] chunksTag = mac.doFinal();

        byte[] oneShotTag = mac.doFinal(message);
        mac.update((byte) 0x01);
        mac.reset();
        byte[] afterResetTag = mac.doFinal(message);

        boolean valid = MessageDigest.isEqual(
                chunksTag, newMac(testKey).doFinal(message));
        boolean changedValid = MessageDigest.isEqual(
                chunksTag,
                newMac(testKey).doFinal("Hi there".getBytes(StandardCharsets.US_ASCII)));

        System.out.println("Algorithm: " + mac.getAlgorithm());
        System.out.println("MAC length: " + mac.getMacLength());
        System.out.println("Tag: " + HexFormat.of().formatHex(chunksTag));
        System.out.println("Buffer consumed: " + (remainder.position() == remainder.limit()));
        System.out.println("Chunks equal one-shot: " + Arrays.equals(chunksTag, oneShotTag));
        System.out.println("Reset discards pending input: " + Arrays.equals(chunksTag, afterResetTag));
        System.out.println("Fresh verifier: " + valid);
        System.out.println("Changed message accepted: " + changedValid);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên (ví dụ `javac --release 17`):

```bash
javac --release 17 MacLifecycleDemo.java
java MacLifecycleDemo
```

**Stdout chính xác:**

```text
Algorithm: HmacSHA256
MAC length: 32
Tag: b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
Buffer consumed: true
Chunks equal one-shot: true
Reset discards pending input: true
Fresh verifier: true
Changed message accepted: false
```

Giải thích:

1. `newMac` tạo một đối tượng mới và khởi tạo bằng khóa HMAC.
2. `mac.update(message, 0, 2)` nạp `Hi`; `ByteBuffer.wrap(message, 2, message.length - 2)` cung cấp phần còn lại ` There`. `update(ByteBuffer)` xử lý từ `position` đến `limit` và tiến vị trí tới limit.
3. `doFinal()` sinh tag 32 byte đúng RFC 4231. Sau khi final, `Mac` tự reset, nên `doFinal(message)` ngay sau đó tính MAC riêng của đúng `Hi There` và khớp tag cũ.
4. `mac.update((byte) 0x01)` thử đưa một byte khác vào, nhưng `reset()` loại bỏ nó. Vì vậy tag sau reset vẫn khớp.
5. Bên xác minh tạo `Mac` mới với cùng key và tính MAC trên đúng message. Thay `Hi There` thành `Hi there` làm byte thay đổi; xác minh thất bại.
6. `HexFormat` có từ Java 17; `Arrays.equals` ở đây chỉ kiểm tra **tính tương đương trong demo**. Khi xác thực tag, ví dụ sử dụng `MessageDigest.isEqual` với hai dãy byte.

Đây là **test vector công khai**: không nên coi giá trị key hoặc tag ở ví dụ là bí mật thực tế. Khi dùng tag trong API, thường truyền dưới dạng Base64 hoặc hex theo giao thức và decode về byte trước khi kiểm tra.

## 6. Quản lý trạng thái giữa nhiều thông điệp

### 6.1 Một Mac không đồng nghĩa một request

`Mac` có trạng thái mutable. Một đối tượng không được thiết kế để nhiều luồng gọi `update` xen kẽ nhau mà không có đồng bộ hóa. Nếu request A và B cùng dùng một instance chia sẻ, trình tự có thể xảy ra:

```text
A: update(bytesA_1)
B: update(bytesB_1)
A: update(bytesA_2)
B: doFinal()
A: doFinal()
```

Khi đó tag của B có thể bao gồm byte từ A và trạng thái của A đã bị B reset; kết quả phụ thuộc interleaving, tạo lỗi xác thực khó tái hiện. Ngay cả khi code dùng `synchronized` để tránh data race, việc chia một phiên update của A bởi request B cũng không còn đúng ranh giới thông điệp nếu không khóa toàn bộ phiên. Cách triển khai đơn giản và dễ kiểm tra:

- **Tạo một đối tượng `Mac` mới cho mỗi phép tính** hoặc mỗi request; dùng khóa đã được cấp đúng quyền để init.
- Giữ `Mac` **cục bộ trong method** hay phạm vi xử lý tuần tự. Không giữ một `static Mac` để tất cả request tái sử dụng.
- Nếu triển khai pool chỉ vì hiệu năng, phải có ownership rõ ràng, checkout độc quyền, cleanup/reset, cách ly key và xử lý exception; chỉ tối ưu sau đo đạc và review bảo mật.
- `Mac.clone()` có thể được một số provider hỗ trợ, nhưng không phải cơ chế bảo đảm cross-provider, và clone một trạng thái đã update cũng mang theo dữ liệu pending; không dùng clone làm biện pháp thread safety mặc định.

### 6.2 DoFinal và reset theo đơn vị nghiệp vụ

Giả sử hệ thống xử lý hai file hoặc hai webhook:

```java
Mac mac = newMac(key);
byte[] tagA = mac.doFinal(fileA);
byte[] tagB = mac.doFinal(fileB);
```

Đây là đoạn code minh họa (biến `key`, `fileA`, `fileB` thuộc phạm vi method, `newMac` như bài mẫu). Hai tag riêng vì `doFinal` reset. Trái lại:

```java
Mac mac = newMac(key);
mac.update(fileA);
mac.update(fileB);
byte[] combinedTag = mac.doFinal();
```

Tag thứ hai là HMAC của `fileA || fileB` theo thứ tự cấp vào. Điều này có thể đúng nếu hợp đồng quy định một bản tin gồm nhiều khối, nhưng **sai nếu bạn muốn hai file có hai MAC độc lập**.

### 6.3 Xử lý khi thao tác bị lỗi giữa chừng

Nếu đọc file thất bại sau khi `update` một phần dữ liệu, **không** dùng `doFinal` rồi đánh dấu file là đã xác thực; kết quả chỉ thuộc byte đã đọc thành công. Hủy thao tác, bỏ instance, hoặc reset trước khi tính bản tin khác theo quy trình có kiểm soát.

Ví dụ stream bị timeout không làm trạng thái MAC tự biết bản tin “chưa đủ”. MAC không nắm kích thước file, message length hoặc semantic của bản tin nếu ứng dụng không cung cấp. Vì vậy, code nghiệp vụ phải xác nhận **đã nhận đủ toàn bộ byte theo giao thức** trước khi coi tag là MAC của bản tin hoàn chỉnh.

## 7. Xử lý thông điệp lớn bằng update từng khối

Để xác thực file lớn, không cần đọc toàn bộ file vào `byte[]`. Ví dụ sau là **đoạn code minh họa bên trong method**; giả sử đã có `Path path` và `SecretKey key` thích hợp, các import tương ứng và xử lý ngoại lệ:

```java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(key);

byte[] buffer = new byte[8192];
try (var input = java.nio.file.Files.newInputStream(path)) {
    int n;
    while ((n = input.read(buffer)) != -1) {
        if (n > 0) {
            mac.update(buffer, 0, n);
        }
    }
}
byte[] tag = mac.doFinal();
```

Điểm cần quan sát:

- `update(buffer, 0, n)` chỉ đưa **n byte thực đọc** vào MAC, không đưa byte còn sót từ vòng trước trong buffer. Dùng `update(buffer)` ở đây là sai nếu lần đọc cuối nhỏ hơn `buffer.length`.
- Mọi vòng lặp cùng đóng góp vào **một thông điệp duy nhất**; chỉ gọi `doFinal` **sau** khi đã nhận hết file.
- Nên có giới hạn dung lượng, quyền đọc file, cơ chế xác định file không bị thay đổi ngoài ý muốn trong lúc đọc, timeout/cancellation, và chính sách khi xảy ra lỗi I/O. Không xác thực một file đang bị thay đổi giữa các bước theo giả định file là bất biến.
- Nếu MAC cũng phải bảo vệ tên file, tenant, content type hoặc metadata, phải đưa những trường đó vào thông điệp MAC theo serialization không mơ hồ; HMAC riêng byte file không tự bảo vệ metadata ở bên ngoài.
- `Files.newInputStream` cung cấp stream; ở API HTTP, luồng bytes ký phải đúng với phiên bản raw/canonical mà cả bên gửi và bên nhận thống nhất, không tự deserialize rồi serialize lại trước khi xác minh.

Ví dụ khi nhận webhook có JSON: bên gửi định nghĩa MAC trên **raw body bytes**, bên nhận cần lấy đúng raw bytes đó để kiểm MAC (và bổ sung các trường khác theo đặc tả chữ ký). Thêm khoảng trắng, đổi thứ tự field hoặc Unicode normalization trước kiểm MAC đều có thể làm tag không khớp.

## 8. Thiết kế key, thuật toán và ngữ cảnh sử dụng

### 8.1 Test key khác key sản xuất

Trong ví dụ học, `"0b".repeat(20)` là key của RFC 4231. Hệ thống sản xuất không lấy key từ ví dụ, password thường hoặc chuỗi cố định trong mã nguồn.

Có thể tạo khóa HMAC-SHA-256 mới bằng `KeyGenerator`:

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

KeyGenerator generator = KeyGenerator.getInstance("HmacSHA256");
generator.init(256, new SecureRandom());
SecretKey secretKey = generator.generateKey();
```

Đây là đoạn code minh họa trong method có xử lý `GeneralSecurityException`. Kích thước 256 bit là lựa chọn phổ biến cho key HMAC-SHA-256 của một triển khai mới, nhưng yêu cầu key/thuật toán phải được ghi trong chính sách và phù hợp provider. Để sử dụng key, gọi `mac.init(secretKey)`. Với key thô lấy từ kho bí mật, có thể dùng `SecretKeySpec(keyBytes, "HmacSHA256")`, nhưng việc lớp này có thể tạo object từ byte **không** chứng minh nguồn key đủ ngẫu nhiên, có phân quyền hay được luân chuyển an toàn.

Quy tắc quản lý khóa:

- Sinh key bằng bộ sinh ngẫu nhiên mật mã phù hợp, hoặc nhận từ KMS/HSM có cơ chế được phê duyệt; hạn chế xuất byte key khi hệ thống quản lý khóa có API ký/MAC chuyên dụng.
- Bảo vệ key ở cấu hình, log, memory dump, backup và quyền của tài khoản dịch vụ; tránh commit hoặc gửi key qua message queue.
- Dùng **key ID/version** để xác định key khi xác minh message cũ. Có kế hoạch rotation, thu hồi, thời gian chấp nhận key cũ và ứng phó khi nghi lộ.
- Tách key theo mục đích/protocol, tenant hoặc trust domain khi yêu cầu cách ly; không dùng cùng key cho HMAC và AES hay nhiều giao thức khác nếu không có thiết kế và key derivation có domain separation rõ ràng.
- Nếu dùng key derivation, dùng KDF chuẩn đã được thiết kế cho mục đích đó, ví dụ HKDF theo tiêu chuẩn áp dụng; không tự ghép key với text rồi hash và gọi là quản lý khóa.
- Hạn chế chủ thể có quyền tạo MAC: bất kỳ ai có key đều có khả năng làm giả tag trong cùng phạm vi key. Việc chỉ đọc được tag không cho phép tự tạo tag hợp lệ nếu HMAC và key an toàn.

### 8.2 Thuật toán nằm trong hợp đồng

`HmacSHA256` tạo tag dài **32 byte** theo HMAC-SHA-256. `mac.getMacLength()` trả độ dài theo byte, không phải số ký tự Base64/hex. Hex của tag 32 byte dài 64 ký tự ASCII; Base64 thông thường biểu diễn cùng tag với độ dài khác.

Không tự đổi `HmacSHA256` sang `HmacSHA512` hoặc thay provider chỉ dựa trên ý thích ở phía receiver: hai bên phải thỏa thuận thuật toán, key, độ dài tag, cách serialization và policy. Khi giao thức có ID thuật toán trên wire, receiver phải **giới hạn danh sách thuật toán được phép** theo cấu hình đáng tin; không nhận mọi thuật toán client đề nghị.

Cắt ngắn tag (*truncation*) là một lựa chọn giao thức phải được phân tích, kiểm thử và chỉ định chính xác độ dài/thuật toán, không phải phép “lấy vài ký tự đầu cho gọn”. Bài này dùng **toàn bộ 32 byte tag**.

## 9. Cách xác minh MAC an toàn

Cách xác minh điển hình:

1. Nhận dãy byte message theo định dạng được công bố. Phân biệt **raw bytes** với dữ liệu đã parse/canonicalize.
2. Đọc key theo key ID/context đã được kiểm soát bởi server, không để request chỉ định key thô.
3. Tạo `Mac` mới, gọi `init` và tính `doFinal(messageBytes)` hoặc streaming với `update` rồi `doFinal`.
4. Decode tag đính kèm (ví dụ từ Base64) về byte; kiểm tra encoding hợp lệ và độ dài theo giao thức.
5. Dùng `MessageDigest.isEqual(calculatedTag, receivedTag)` để so sánh hai dãy tag; xử lý lỗi xác minh bằng phản hồi thống nhất theo chính sách.
6. Sau xác thực, vẫn kiểm tra **chống replay, quyền truy cập, thời hạn thông điệp và ràng buộc với tài nguyên/hành động**.

Ví dụ trong ngữ cảnh method đã có `key`, `messageBytes` và `receivedTag`:

```java
Mac verifier = Mac.getInstance("HmacSHA256");
verifier.init(key);
byte[] calculated = verifier.doFinal(messageBytes);

boolean accepted = receivedTag != null
        && receivedTag.length == verifier.getMacLength()
        && MessageDigest.isEqual(calculated, receivedTag);
```

Đây là đoạn code minh họa, không phải chương trình độc lập. Kiểm độ dài giúp từ chối dữ liệu sai giao thức; `MessageDigest.isEqual` là công cụ Java phù hợp hơn `Arrays.equals` khi so sánh tag bảo mật. Tuy nhiên, **không tự khẳng định toàn endpoint chạy constant-time**: chọn key, xử lý lỗi, length check, decode, truy vấn DB và logic nghiệp vụ vẫn có thể khác biệt về thời gian. Cần đánh giá toàn protocol nếu threat model coi side-channel là quan trọng.

Không dùng `Arrays.equals(tag, received)` làm phương pháp mặc định để xác thực MAC nhạy cảm, và không so sánh string Base64/hex trực tiếp bằng `String.equals` khi có thể decode và kiểm tra byte. Việc xác minh MAC không được coi là phép đo quyền: một tag hợp lệ có thể đến từ client có key chung nhưng **không được phép** thực hiện hành động trong tenant khác.

### 9.1 Không biến so sánh byte thành logic chống replay

Một request đã ký có thể được gửi lại nguyên vẹn. Ví dụ `POST /pay` với body và tag hợp lệ được replay sẽ có **tag vẫn hợp lệ**. Cần gắn timestamp/nonce/request ID/sequence number và phạm vi tác vụ vào dữ liệu MAC rồi thực thi policy hạn dùng, phát hiện nonce đã sử dụng, kiểm tra idempotency của xử lý nghiệp vụ và chống đua tranh trong kho dữ liệu.

Chỉ “ký nonce” mà không **lưu/kiểm tra nonce đã dùng** sẽ không ngăn phát lại. Chỉ gắn timestamp mà không có giới hạn thời gian hoặc xử lý clock skew cũng không hoàn chỉnh.

### 9.2 Đừng quên xác định chính xác thứ được MAC bảo vệ

Ví dụ token có HMAC trên `userId` nhưng không bao gồm `role` hay `tenantId`: sửa những trường nằm ngoài MAC có thể làm sai ý nghĩa xác thực. Với webhook, nếu chữ ký chỉ bao gồm body mà không có method/path/time trong khi protocol yêu cầu ràng buộc đường đi, kẻ tấn công có thể thử đem cùng body/tag tới endpoint khác.

Mỗi định dạng nên công bố: **thứ tự trường, encoding, cách biểu diễn null/empty, version, thuật toán, key ID, tag encoding, phạm vi thời gian, nonce và nơi lấy danh tính đã xác minh**.

## 10. Cấu trúc byte không mơ hồ khi dùng nhiều update

Vì `update(partA); update(partB)` tương đương xử lý byte nối nhau, một giao thức ghép chuỗi tùy tiện có thể tạo cùng byte cho các cặp trường khác nhau.

Ví dụ:

```text
("ab", "c") -> UTF8("abc")
("a", "bc") -> UTF8("abc")
```

Nếu đây là hai bộ dữ liệu nghiệp vụ khác nhau, HMAC của cùng dãy byte sẽ **giống hệt**; điều đó không phải điểm yếu của HMAC mà là **thiếu ranh giới serialization**. Cần định nghĩa format rõ ràng, ví dụ:

```text
version | domain | length(field1) | field1 | length(field2) | field2
```

Các trường length-prefix phải xác định width, endianness và đơn vị (byte), mọi giá trị được mã hóa theo charset rõ ràng, và các byte version/domain cũng được đưa vào MAC. Có thể dùng protobuf/CBOR canonical hoặc một format đã được đặc tả; tránh tự chế nếu có chuẩn thích hợp.

Giữa các dịch vụ, chốt quy tắc cho Unicode normalization, JSON number, URL decoding, newline, ký tự rỗng, thứ tự field và literal escape. **NFC, UTF-8, canonical JSON và canonical HTTP request là những lớp khác nhau.** Không giả định gọi `String.getBytes(UTF_8)` đủ để hai hệ thống ký cùng một đối tượng JSON.

### Domain separation

Dùng một key hoặc hệ key có phạm vi rộng, nếu thiếu ngữ cảnh, một tag hợp lệ từ giao thức A có thể bị diễn giải là hợp lệ cho thông điệp B có byte trùng nhau. Tách key theo mục đích là lựa chọn mạnh; đồng thời đưa **nhãn ngữ cảnh và version giao thức** vào đúng phần dữ liệu được MAC bảo vệ, ví dụ nhãn ASCII `"invoice-webhook:v1"` đi cùng bộ field có ranh giới rõ ràng.

Không cho user thay đổi tự do nhãn mục đích hoặc key ID để né policy. Với multi-tenant, ràng buộc tenant vào dữ liệu xác thực và **kiểm tra quyền** ở service. Domain separation hỗ trợ chống dùng nhầm tag, nhưng không thay thế authorization.

## 11. Những vấn đề đặc biệt của trạng thái và ByteBuffer

### 11.1 Trạng thái của ByteBuffer

`mac.update(buffer)` chỉ xử lý byte giữa `position` và `limit` của `buffer`. Sau khi thành công, vị trí buffer tiến đến limit; không được mặc định rằng dữ liệu từ đầu mảng backing array đã được xử lý nếu position không ở 0. Nếu muốn đọc lại cùng byte, cần `duplicate`, `rewind` hoặc chỉnh lại position/limit theo quy tắc ByteBuffer có kiểm soát.

Trong demo, `ByteBuffer.wrap(message, 2, message.length - 2)` tạo buffer có vị trí 2 và limit bằng 8, nên xử lý đúng **6 byte còn lại**. Không nhầm nó với mảng mới dài 6 byte. Nếu sử dụng buffer tái sử dụng trong pipeline I/O, kiểm tra `flip`/`clear` theo hợp đồng producer/consumer để không ký byte thừa hoặc bỏ byte.

### 11.2 Output buffer của doFinal

Nếu tránh cấp phát mảng mới, `doFinal(byte[] output, int outOffset)` ghi tag vào mảng đã cấp. Mảng phải đủ chỗ kể từ `outOffset` cho `mac.getMacLength()` byte; method này trả `void`. Ví dụ minh họa với `mac` đã init và update xong:

```java
byte[] output = new byte[mac.getMacLength()];
mac.doFinal(output, 0);
```

Không nhầm `doFinal(output, 0)` là “xác thực mảng output”; đây là **mảng nhận tag**, khác `doFinal(byte[] input)` nơi mảng là **thông điệp được MAC**. Đây là lỗi overload dễ gây nhầm khi đọc code.

### 11.3 reset, init và clear key khác nhau

- `reset()` chỉ hủy kết quả update pending và trả object về trạng thái MAC mới **với cùng key**.
- `doFinal()` làm final rồi reset, giữ khả năng tính thông điệp mới cùng key.
- `init(newKey)` thiết lập khóa/tham số mới và trạng thái mới khi thành công.
- Không có API `Mac.destroyKey()` tổng quát đảm bảo xóa tất cả bản sao key trong provider/JVM; `SecretKey` có thể do provider/HSM quản lý, và thao tác xóa/thu hồi phụ thuộc loại key, bộ nhớ, đời sống object và cơ chế quản lý khóa.

Với yêu cầu nghiêm ngặt về vòng đời secret, xác định rõ provider, key store/KMS, rotation và cơ chế dispose; đừng dựa vào `reset()` như hành động bảo mật xóa khóa.

### 11.4 Lỗi mid-stream và retry

Ví dụ hệ thống streaming tính HMAC của body được đọc dở, rồi retry bằng cách gọi `update` với body từ đầu **trên cùng Mac chưa reset**. Kết quả là HMAC của `partial || full`, không phải `full`. Khi retry thao tác, tốt nhất **khởi tạo instance mới** hoặc reset dưới ownership độc quyền, rồi tính lại từ đầu. Đảm bảo kết quả của lượt xử lý thất bại không được publish.

Không log byte key/tag nhạy cảm, nội dung payload có thông tin cá nhân hoặc toàn bộ file chỉ để debug thất bại. Có thể log request ID, algorithm đã được allowlist, key version không nhạy cảm, độ dài byte và mã lỗi theo policy.

## 12. Xác thực khác với bảo mật đường truyền và phân quyền

Một MAC hợp lệ trả lời câu hỏi: “Thông điệp này có được tạo bởi **bên có khóa** và còn nguyên vẹn trong phạm vi byte đã ký không?”. Nó **không** tự trả lời:

- User/client đang gọi API là ai? (authentication/identity)
- User đó có quyền làm gì với đối tượng/tenant? (authorization)
- Message này đã được xử lý trước đây chưa? (anti-replay/idempotency)
- Payload có hợp lệ về schema, logic nghiệp vụ và giới hạn tài nguyên không? (validation)
- Nội dung có bí mật trên kênh truyền và khi lưu trữ không? (confidentiality)
- Key có bị lộ hoặc bị chia sẻ vượt miền tin cậy không? (key management)

Ví dụ với webhook từ đối tác, sau khi verify MAC vẫn phải kiểm tenant mapping, business order ID, trạng thái đơn hàng và chống xử lý lặp. Với yêu cầu cấp quyền, đừng tin trường `role=admin` chỉ vì cùng một key HMAC dùng chung cho nhiều service; policy phải dựa trên ngữ cảnh đáng tin và quyền đã cấp.

## 13. Bảng lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng |
| --- | --- | --- |
| Quên `init` trước `update`/`doFinal` | `IllegalStateException` hoặc luồng xử lý sai | Tạo và init Mac trong cùng phạm vi tính tag; fail fast |
| Dùng một `static Mac` chung cho request song song | Trộn byte, reset chéo, kết quả race | Một `Mac` riêng cho mỗi phép tính/request |
| Nghĩ `update` tạo MAC độc lập mỗi lần | Ghép nhiều bản tin thành một MAC | Gọi `doFinal` đúng ranh giới bản tin |
| Gọi `doFinal(input)` sau khi đã update prefix không chủ ý | Tag tính trên `prefix \|\| input` | Reset hoặc new instance trước input độc lập |
| Gọi `reset` trước khi final dữ liệu cần xác thực | Mất byte pending | Chỉ reset khi cố tình hủy phép tính |
| Retry mà không reset/new instance | HMAC của `partial \|\| retry` | Retry với context mới |
| Dùng `getBytes()` không charset | Byte thay đổi theo runtime | Chỉ định UTF-8 hay charset đã thỏa thuận |
| Serialize lại JSON trước verify raw-body signature | Byte khác body gốc | Verify trên byte theo đúng đặc tả bên gửi |
| Ghép field không có length/boundary | Hai tuple khác nhau cho cùng byte | Canonical serialization, length-prefix, version/domain |
| Dùng `Arrays.equals` / string equality khi verify tag | Không phù hợp mục tiêu kiểm soát timing | Decode byte và dùng `MessageDigest.isEqual`, đánh giá toàn pipeline |
| Cắt tag tùy tiện hoặc dùng thuật toán từ request | Hạ mức bảo vệ, giao thức không tương thích | Allowlist thuật toán, độ dài tag theo hợp đồng |
| Dùng key cứng hoặc key tái sử dụng quá rộng | Rủi ro giả mạo lớn khi key lộ | Sinh key an toàn, scope, rotation, key version |
| Dùng HMAC để “mã hóa” | Payload vẫn đọc được | TLS/mã hóa khi cần bí mật |
| Không bảo vệ replay | Bản tin/tag cũ có thể gửi lại | Nonce/counter/time window và kiểm soát xử lý lặp |
| Không MAC các trường quyết định quyền | Tag hợp lệ nhưng resource/action bị sửa | Bao phủ mọi field nhạy cảm đúng phạm vi và xác minh quyền riêng |
| Chỉ xem unit test là bằng chứng đủ | Provider, key và wire protocol có thể khác thật | Test tích hợp với provider, vectors và giao thức thực tế |

## 14. Checklist thiết kế và kiểm thử

Đối với một service Java tính hoặc xác minh HMAC, đi qua checklist sau:

1. **Thuật toán:** dùng `HmacSHA256` được chọn server-side và tương thích chuẩn của đối tác.
2. **Key:** key đủ entropy, không hard-code; quyền sử dụng và rotation rõ ràng, key ID không dẫn tới lấy nhầm key.
3. **Dữ liệu:** byte input đúng contract, charset/serialization rõ ràng, không thay đổi âm thầm ở phía xác minh.
4. **Ranh giới:** một tag cho **một thông điệp**; `update` theo thứ tự đúng, `doFinal` sau đúng byte cuối.
5. **Trạng thái:** không chia sẻ `Mac` qua thread; reset khi hủy pending; không tái sử dụng trạng thái lỗi.
6. **Lỗi:** fail closed khi tag sai, input không hợp lệ, key không tìm thấy hoặc provider lỗi; không coi payload chưa đọc hết là đã xác thực.
7. **Kiểm tag:** độ dài/encoding theo chuẩn; `MessageDigest.isEqual` trên byte, kiểm tra thời gian đáp ứng nếu cần.
8. **Chống replay:** timestamp/nonce/idempotency có trạng thái và hạn dùng theo thiết kế.
9. **Authorization:** kiểm actor, action và resource độc lập với MAC; ghi audit vừa đủ.
10. **Test:** RFC vector, chunked vs one-shot, reset, thay byte, lỗi stream, các trường metadata ngoài body, số lượng request đồng thời và key rotation.

Các test tối thiểu hữu ích:

| Ca | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Vector RFC 4231 | Key 20 byte `0b`, payload `Hi There`, HmacSHA256 | Tag bằng `b0344c61...e32cff7` |
| Chia chunk | Cấp cùng byte theo `update` nhiều lần rồi `doFinal` | Bằng tag của `doFinal(fullInput)` |
| Sau `doFinal` | Tính cùng input ngay lần kế | Tag bằng nhau vì trạng thái reset |
| `reset` trước final | `update(bad)`, `reset`, `doFinal(good)` | Tag bằng HMAC của `good` riêng |
| Thay một byte | Đổi `Hi There` thành `Hi there` | Xác minh không chấp nhận |
| Quên `init` | Cố update/final trên Mac chưa init | Lỗi; không sinh tag hợp lệ |
| Streaming | File 20.000 byte, read từng khối 8192 byte | Tag khớp one-shot của toàn bộ file |
| Lỗi streaming | Stream lỗi sau một phần nội dung | Không công nhận tag; hủy lượt xử lý |
| Hai request đồng thời | Cùng service, hai message khác nhau | Tag của từng message ổn định, không trộn trạng thái |
| Replay | Gửi lại request và tag hợp lệ | MAC vẫn hợp lệ nhưng anti-replay/idempotency phải chặn lặp khi policy yêu cầu |
| Key rotation | Verify tag cũ bằng key version cũ còn được cho phép | Đúng trong giai đoạn chuyển đổi; key đã thu hồi thì bị từ chối theo chính sách |

**Gợi ý test lớn:** Đừng chỉ kiểm tag của cùng thư viện với chính nó. Hãy lưu ít nhất một **golden vector độc lập** (RFC 4231 hoặc từ đối tác) để phát hiện lỗi algorithm, charset, key parsing và serialization.

## 15. Bài tập thực hành

### Bài 1 — Ba phương thức update

Sử dụng key test `0b` lặp 20 lần và message `Hi There`. Viết ba phép tính:

1. `mac.doFinal(messageBytes)`.
2. `mac.update(messageBytes, 0, 2)` rồi `mac.update(messageBytes, 2, messageBytes.length - 2)`, cuối cùng `mac.doFinal()`.
3. `mac.update(ByteBuffer.wrap(messageBytes))` rồi `mac.doFinal()`.

So sánh cả ba tag với RFC 4231. Giải thích tại sao chunking không thay đổi tag khi **thứ tự byte và nội dung không đổi**.

### Bài 2 — Bắt lỗi quản lý trạng thái

Một developer viết:

```java
static final Mac SHARED_MAC = createAndInitializeMac();
byte[] sign(byte[] requestBody) {
    SHARED_MAC.update(requestBody);
    return SHARED_MAC.doFinal();
}
```

Đây là **mã giả minh họa lỗi**, không phải chương trình Java độc lập: `createAndInitializeMac()` không được định nghĩa ở đây. Hãy chỉ ra vì sao code có thể sai trong web service xử lý nhiều request song song, kể cả khi một request riêng có vẻ chạy đúng. Sửa theo hướng tạo `Mac` mới cho từng phép tính và giữ khóa trong secret manager/KMS. Viết test hai luồng để chứng minh tính độc lập.

### Bài 3 — Thiết kế chữ ký webhook

Một đối tác gửi các trường `timestamp`, `eventId`, `tenantId`, `body` và tag HMAC.

- Định nghĩa byte chính xác đưa vào MAC, version, charset và ranh giới giữa field.
- Quyết định lúc nào xác minh MAC và lúc nào parse JSON.
- Đề xuất cách lưu nonce/event ID để chống xử lý lặp với các request concurrent.
- Xác minh tenant và quyền cập nhật một bản ghi nghiệp vụ cụ thể.
- Kiểm thử request hợp lệ, body thay một byte, tag sai, timestamp quá hạn, event ID trùng, thay `tenantId` và dùng key đã thu hồi.

### Bài 4 — Streaming file

Viết method tính HMAC-SHA-256 của một file theo từng block; kết quả phải bằng one-shot của toàn byte. Sau đó giả lập file 1 MB, file rỗng, đọc được một phần rồi lỗi I/O, hai file liên tiếp và retry. Đảm bảo failure không xuất tag như thể file đã xác thực thành công.

**Điều kiện hoàn thành bài:** bạn có thể giải thích chính xác byte nào đã đi qua từng `update`, vì sao `doFinal` tạo ranh giới thông điệp và reset trạng thái, khi nào nên khởi tạo lại `Mac`, và tại sao việc có một tag HMAC hợp lệ vẫn cần authorization cùng anti-replay riêng.

## 16. Tài liệu tham khảo

- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): API, trạng thái init/update/doFinal/reset, các overload và exceptions.
- [Java SE 17 — SecretKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html): biểu diễn khóa bí mật từ byte.
- [Java SE 17 — MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)): so sánh byte trong trường hợp kiểm tag.
- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): mô tả cấu trúc HMAC.
- [RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512](https://www.rfc-editor.org/rfc/rfc4231): test vector chuẩn cho HMAC-SHA-256 và các biến thể.
- [OWASP — Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): quản lý key, thuật toán và các lưu ý bảo vệ dữ liệu.
