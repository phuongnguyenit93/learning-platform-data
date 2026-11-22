# 5.2 HMAC và khác biệt với băm dữ liệu có nối thêm khóa

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao **hash thông thường** và **mã xác thực thông điệp (MAC)** giải quyết hai bài toán khác nhau; mô tả cấu trúc HMAC và lý do **HMAC-SHA256 khác với `SHA-256(key || message)`**; nhận diện điểm yếu length-extension của cách tự ghép khóa vào dữ liệu; tạo và kiểm tra HMAC bằng Java 17+; kiểm thử implementation bằng test vector chính thức; và biết cách quản lý khóa, định dạng thông điệp, chống phát lại khi ứng dụng vào API.

Chủ đề thuộc **5. Mã xác thực** trong Java Security/JCA. Trọng tâm là HMAC dựa trên hàm băm, nhất là `HmacSHA256`. Bài học không yêu cầu tự viết thuật toán mật mã hoặc xây dựng giao thức chữ ký API đầy đủ.

## 1. Vì sao chỉ băm dữ liệu chưa đủ để xác thực?

Hàm băm mật mã như SHA-256 nhận các byte `M` và tính `H(M)`. Bất kỳ ai biết `M` đều có thể tự tính cùng digest. Vì thế, nếu một bên truyền cả nội dung và digest qua kênh mà đối thủ có thể sửa, đối thủ có thể thay dữ liệu **và tính lại digest**, khiến kiểm tra `SHA-256` vẫn thành công.

Mã xác thực thông điệp (*Message Authentication Code*, MAC) nhận **khóa bí mật K** và **thông điệp M**, tạo **tag T**. Bên kiểm tra dùng cùng khóa để xác nhận tag tương ứng với thông điệp. Khi khóa còn bí mật và cấu trúc MAC an toàn, kẻ không biết khóa rất khó tạo tag hợp lệ cho một thông điệp mới.

| Tiêu chí | `SHA-256(message)` | `SHA-256(key \|\| message)` tự chế | `HMAC-SHA256(key, message)` |
| --- | --- | --- | --- |
| Có khóa bí mật | Không | Có | Có |
| Được thiết kế/chuẩn hóa như một MAC | Không | Không | Có (HMAC) |
| Chống việc bên thứ ba sửa cả nội dung lẫn digest | Không, nếu digest không được xác thực độc lập | Không bảo đảm | Có, với khóa đủ mạnh và triển khai đúng |
| Dễ mắc **length-extension** kiểu SHA-256 | Không phải bài toán MAC | **Có**, với cấu trúc tiền tố `H(K \|\| M)` | Không chịu kiểu tấn công mở rộng độ dài trực tiếp đó |
| Engine Java | `MessageDigest` | `MessageDigest` (dùng sai mục đích xác thực) | `Mac` |
| Tên chuẩn trong Java | `SHA-256` | `SHA-256` | `HmacSHA256` |

**Dùng khóa không tự biến một phép băm thành MAC an toàn.** Công thức `H(K || M)` và `H(M || K)` nhìn đơn giản nhưng không thừa hưởng những bảo đảm an toàn của một cấu trúc MAC đã nghiên cứu. Một số kiểu nối dữ liệu đặc biệt có những tấn công khác nhau; không kết luận mọi kiểu đều chịu chính xác cùng một đòn length-extension.

HMAC bảo vệ **tính toàn vẹn có xác thực và tính xác thực của bên biết khóa**; nó **không mã hóa nội dung**, không ngăn ai đó đọc plaintext, không ngăn bản tin hợp lệ bị phát lại và không tạo tính không thể chối bỏ như chữ ký số bất đối xứng vì cả hai bên cùng biết khóa.

## 2. Cấu trúc HMAC: hai lớp băm có khóa

HMAC được mô tả trong [RFC 2104](https://www.rfc-editor.org/rfc/rfc2104) và được thử nghiệm bằng các vector như [RFC 4231](https://www.rfc-editor.org/rfc/rfc4231). Với hàm băm `H`, ký hiệu `||` là phép **nối chuỗi byte**, `⊕` là XOR từng byte, công thức là:

\[
\mathrm{HMAC}(K,M)=H\big((K_0\oplus\mathrm{opad})\parallel H((K_0\oplus\mathrm{ipad})\parallel M)\big)
\]

Trong đó:

- `K` là khóa bí mật; `M` là dãy byte thông điệp.
- `B` là **block size của hàm băm**, không phải độ dài digest. Với HMAC-SHA256, `B = 64` byte; digest SHA-256 dài **32 byte**.
- Nếu khóa dài hơn `B`, HMAC trước hết băm khóa bằng `H`; sau đó thêm byte `0x00` vào cuối để tạo `K₀` dài đúng `B`. Nếu khóa đã ngắn hơn `B`, chỉ cần đệm zero; khóa đúng `B` không cần đệm.
- `ipad` là `B` byte `0x36`, còn `opad` là `B` byte `0x5c`.
- HMAC tạo một giá trị băm **bên trong** của `(K₀ ⊕ ipad) || M`, rồi băm **bên ngoài** của `(K₀ ⊕ opad) || innerDigest`.

Tóm tắt luồng:

```text
K --[normalize to block size B]--> K0
                 |                    |
                 v                    v
           K0 XOR ipad          K0 XOR opad
                 |                    |
                 v                    |
        hash((K0 XOR ipad) || M)      |
                 |                    |
                 +--------> hash((K0 XOR opad) || innerDigest)
                                        |
                                        v
                                    HMAC tag
```

Đầu ra của HMAC-SHA256 nguyên vẹn là **32 byte = 256 bit**. Độ dài tag không phụ thuộc độ dài thông điệp. Khi cần hiển thị, 32 byte trở thành **64 ký tự hex**; hex là cách mã hóa để lưu hoặc truyền, không phải bản thân tag.

**Tại sao có hai lớp?** HMAC không đưa trực tiếp trạng thái cuối của `H(K || M)` làm tag; giá trị băm bên trong được xử lý qua lớp băm khác với khóa đã biến đổi bởi `opad`. Kẻ chỉ biết tag ngoài không lấy được trạng thái nội bộ `H((K₀ ⊕ ipad) || M)` để thực hiện phép kéo dài thông điệp như với cấu trúc `H(K || M)`. Bảo đảm an toàn của HMAC dựa trên các giả định mật mã về hàm băm và thiết kế HMAC, chứ không chỉ dựa vào việc ghép khóa.

**Không tự hiện thực `ipad/opad` trong production.** Dùng `javax.crypto.Mac` và implementation của provider đã kiểm thử để tránh lỗi xử lý khóa dài, khối đệm, trạng thái hash và byte encoding.

## 3. Rủi ro thực sự khi băm dữ liệu có nối thêm khóa

### 3.1 Kiểu tiền tố: `SHA-256(key || message)`

SHA-256 sử dụng cấu trúc băm lặp với trạng thái có thể tiếp tục xử lý các block bổ sung. Nếu một giao thức ngây thơ định nghĩa:

```text
tag = SHA-256(secretKey || message)
```

và kẻ tấn công biết `message`, `tag` cùng độ dài khóa (hoặc đoán được một số độ dài ứng viên), họ có thể thực hiện **length-extension attack** về mặt mật mã: tính tag cho một chuỗi byte mở rộng tương ứng với

```text
message || gluePadding(secretKey || message) || attackerSuffix
```

mà không cần biết byte của `secretKey`. `gluePadding` là padding SHA-256 phụ thuộc **tổng độ dài byte** của `secretKey || message`, chứa dấu kết thúc và độ dài thông điệp theo đặc tả SHA-256. Việc một payload giả mạo như vậy còn được parser ứng dụng chấp nhận hay không phụ thuộc cách hệ thống diễn giải các byte; nhưng đây đã là lỗi thiết kế cơ bản của MAC tiền tố.

Đặc biệt, cách nối thêm một dấu phân cách cố định như `SHA-256(secretKey || ":" || message)` **không biến nó thành HMAC** và không loại trừ một cách tổng quát tấn công length-extension.

### 3.2 Kiểu hậu tố: `SHA-256(message || key)`

Với kiểu hậu tố, tag quan sát được là trạng thái sau khi băm **cả khóa ở cuối**. Do đó không thể đơn giản áp dụng cùng thao tác kéo dài rồi đặt phần mở rộng vào sau `message` mà vẫn giữ khóa ở cuối. Tuy nhiên, điều này **không chứng minh** công thức là MAC an toàn: các tính chất, rủi ro va chạm và bảo đảm an toàn còn phụ thuộc cấu trúc hash và mô hình tấn công. Không triển khai `hash(message || key)` hoặc biến thể tự chế để thay cho `Mac`.

### 3.3 Tại sao có HMAC nếu SHA-256 vẫn an toàn?

Một hash có tính chất khó tìm va chạm/chống tiền ảnh **không đương nhiên** tạo MAC chống giả mạo khi ghép khóa. HMAC được định nghĩa để giải quyết chính xác bài toán MAC, tránh cấu trúc tiền tố dễ bị length-extension và có phân tích mật mã độc lập. Với ứng dụng Java, lựa chọn mặc định khi cần MAC từ SHA-256 là **`HmacSHA256`**.

## 4. Java 17: HMAC, phép băm nối khóa và kiểm thử chính thức

Java JCA/JCE phân biệt rõ engine:

- `MessageDigest.getInstance("SHA-256")` tạo **hàm băm không khóa**.
- `Mac.getInstance("HmacSHA256")` tạo **HMAC có khóa**; phải khởi tạo bằng `mac.init(key)` rồi mới `update` hoặc `doFinal`.
- `SecretKeySpec(keyBytes, "HmacSHA256")` đóng gói byte khóa phù hợp cho `Mac` trong ví dụ; đây không phải cơ chế sinh hay lưu trữ khóa.
- `HexFormat` (Java 17+) chuyển `byte[]` sang hex và giải mã hex để đối chiếu test vector.

Chương trình bên dưới sử dụng **khóa thử nghiệm công khai của RFC 4231**, chỉ dành cho học tập và kiểm thử. Đừng dùng khóa này trong dịch vụ thật.

Tạo tệp **`HmacVsConcatDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacVsConcatDemo {
    private static final String ALGORITHM = "HmacSHA256";

    public static void main(String[] args) throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        byte[] message = "Hi There".getBytes(StandardCharsets.UTF_8);

        byte[] tag = hmac(key, message);
        byte[] rfcExpected = HexFormat.of().parseHex(
                "b0344c61d8db38535ca8afceaf0bf12b"
                        + "881dc200c9833da726e9376c2e32cff7");
        System.out.println("HMAC-SHA256: " + HexFormat.of().formatHex(tag));
        System.out.println("Matches RFC 4231 case 1: "
                + MessageDigest.isEqual(tag, rfcExpected));

        byte[] naive = prefixedSha256(key, message);
        System.out.println("SHA-256(key || message): "
                + HexFormat.of().formatHex(naive));
        System.out.println("HMAC equals naive hash: "
                + MessageDigest.isEqual(tag, naive));

        System.out.println("Verify original: " + verify(key, message, tag));
        System.out.println("Verify modified: " + verify(
                key, "Hi There!".getBytes(StandardCharsets.UTF_8), tag));

        Mac streaming = newMac(key);
        streaming.update("Hi ".getBytes(StandardCharsets.UTF_8));
        streaming.update("There".getBytes(StandardCharsets.UTF_8));
        System.out.println("Streaming equals one-shot: "
                + MessageDigest.isEqual(tag, streaming.doFinal()));

        byte[] key2 = "Jefe".getBytes(StandardCharsets.US_ASCII);
        byte[] message2 = "what do ya want for nothing?"
                .getBytes(StandardCharsets.US_ASCII);
        System.out.println("RFC 4231 case 2: "
                + HexFormat.of().formatHex(hmac(key2, message2)));
    }

    private static Mac newMac(byte[] key) throws Exception {
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(key, ALGORITHM));
        return mac;
    }

    private static byte[] hmac(byte[] key, byte[] message)
            throws Exception {
        return newMac(key).doFinal(message);
    }

    private static boolean verify(byte[] key, byte[] message, byte[] suppliedTag)
            throws Exception {
        byte[] expectedTag = hmac(key, message);
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }

    private static byte[] prefixedSha256(byte[] key, byte[] message)
            throws NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        digest.update(key);
        digest.update(message);
        return digest.digest();
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 HmacVsConcatDemo.java
java HmacVsConcatDemo
```

**Stdout khi chạy trên JDK có implementation `HmacSHA256` và `SHA-256` đúng chuẩn** (đã đối chiếu khi chạy ví dụ):

```text
HMAC-SHA256: b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
Matches RFC 4231 case 1: true
SHA-256(key || message): 9000e06f7d262eac9b27728faaaee3a54d901591a9262c1af171f25fe97c7717
HMAC equals naive hash: false
Verify original: true
Verify modified: false
Streaming equals one-shot: true
RFC 4231 case 2: 5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843
```

**Điều rút ra từ kết quả:**

1. Dữ liệu `"Hi There"` với khóa 20 byte `0x0b` cho HMAC-SHA256 trùng **RFC 4231 test case 1**. Tương tự, khóa ASCII `Jefe` và thông điệp ASCII `what do ya want for nothing?` khớp **test case 2**.
2. `SHA-256(key || message)` vẫn cho chuỗi dài 64 ký tự hex nhưng **khác HMAC-SHA256**. Cùng độ dài đầu ra **không** đồng nghĩa cùng thuật toán hoặc cùng tính an toàn.
3. Kiểm tra tag với cùng khóa/dữ liệu cho `true`; đổi **một byte** của thông điệp thành `"Hi There!"` nhưng giữ tag cũ cho `false`.
4. Gọi `Mac.update` với các đoạn `"Hi "` và `"There"` rồi `doFinal()` cho cùng tag với gọi `doFinal(message)` một lần, vì chuỗi byte cuối cùng giống hệt.

`prefixedSha256` chỉ nhằm **minh họa một thiết kế không nên dùng làm MAC**; không sử dụng hàm đó để ký request, phiên đăng nhập hay dữ liệu nhạy cảm.

Trong ví dụ, `newMac`/`hmac` khai báo `throws Exception` để dễ tập trung vào thuật toán. Ở ứng dụng thực, xử lý tường minh các lỗi như `NoSuchAlgorithmException` và `InvalidKeyException` theo chính sách của hệ thống. Khi provider không có `HmacSHA256`, chương trình sẽ không thể chạy đúng phần này; đó là lỗi cấu hình cần giải quyết, không phải tín hiệu để tự fallback về `SHA-256(key || message)`.

## 5. Sử dụng `Mac` đúng trong Java

### 5.1 Khởi tạo và cập nhật theo từng phần

API điển hình:

```java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secretKeyBytes, "HmacSHA256"));
mac.update(part1);
mac.update(part2);
byte[] tag = mac.doFinal();
```

Đây là đoạn code **minh họa bên trong một phương thức**: `part1`, `part2` và `secretKeyBytes` là các `byte[]` đã được cung cấp, phương thức phải xử lý ngoại lệ bảo mật, và cần import `javax.crypto.Mac` cùng `javax.crypto.spec.SecretKeySpec`. `doFinal()` kết thúc lần tính toán và đưa đối tượng về trạng thái có thể dùng lại với khóa đã khởi tạo. Đừng gọi `doFinal()` giữa hai đoạn của **cùng một thông điệp**, vì như vậy bạn sẽ tính hai tag riêng. Không chia sẻ cùng một `Mac` đang được `update` giữa nhiều luồng: nó là engine có trạng thái; dùng instance riêng cho từng thao tác khi cần đồng thời.

Streaming giúp xử lý request body/tệp lớn mà không cần nạp toàn bộ vào bộ nhớ; `update(buffer, 0, count)` phải sử dụng đúng số byte thực đọc trong mỗi vòng. HMAC được tính trên **byte chính xác**, nên việc đổi encoding hoặc thứ tự chunk sẽ thay đổi tag nếu làm thay đổi byte đầu vào.

### 5.2 Sinh và bảo vệ khóa thật

Đừng dùng chuỗi dễ đoán như `"secret123"` hoặc khóa thử nghiệm RFC. Một ví dụ **tạo khóa ngẫu nhiên 32 byte (256 bit)** bằng Java là:

```java
byte[] secretKeyBytes = new byte[32];
new SecureRandom().nextBytes(secretKeyBytes);
```

Đoạn này cần import `java.security.SecureRandom`. Tạo khóa **một lần theo chính sách**, lưu trong secret manager/KMS/HSM hoặc kho khóa được kiểm soát, và phân phối an toàn cho các bên được phép xác thực. Không sinh khóa mới trước **mỗi lần verify**, vì lúc đó không còn cùng khóa với phía tạo tag.

Dùng khóa có entropy phù hợp với nhu cầu bảo mật, ví dụ **ít nhất 256 bit ngẫu nhiên** khi thiết kế mới với HMAC-SHA256. HMAC không đòi hỏi khóa bắt buộc dài 32 byte trong mọi giao thức; độ mạnh phụ thuộc entropy và quản lý khóa. Với HMAC-SHA256, khóa dài hơn block size của SHA-256 (64 byte) sẽ được chuẩn hóa bằng cách băm trước khi sử dụng; kéo dài khóa tùy tiện không tự tăng mức bảo mật.

Trong production: không ghi khóa hoặc toàn bộ tag bí mật vào log; không hardcode khóa trong mã nguồn; kiểm soát quyền truy cập, rotation, phạm vi sử dụng và phiên bản `keyId`. Nên **tách khóa theo mục đích** (ví dụ webhook và session token dùng khóa khác nhau), theo chiều gửi/nhận khi giao thức cần, và có quy trình thu hồi nếu lộ khóa. `SecretKeySpec` chỉ bọc byte khóa trong chương trình; không bảo vệ khóa khỏi người có quyền đọc bộ nhớ.

### 5.3 Xác minh tag an toàn

Bên nhận phải tính lại HMAC từ **đúng byte nội dung nhận được** và khóa phù hợp, rồi so sánh tag dưới dạng byte:

```java
byte[] expectedTag = hmac(secretKeyBytes, receivedMessageBytes);
boolean accepted = MessageDigest.isEqual(expectedTag, receivedTagBytes);
```

Đây là đoạn minh họa trong phạm vi class có phương thức `hmac` từ ví dụ hoàn chỉnh, import `java.security.MessageDigest`. `MessageDigest.isEqual` dùng để so sánh giá trị byte của hai digest/tag và được thiết kế để hạn chế rò rỉ timing so với phép so sánh ngây thơ từng byte; để đạt hành vi thời gian so sánh phù hợp, hãy **kiểm tra định dạng và dùng tag có độ dài cố định theo giao thức**. Với HMAC-SHA256 nguyên vẹn, expected tag dài **32 byte**. Không chấp nhận tag rỗng, độ dài bất kỳ hoặc đối chiếu chỉ vài byte đầu không có thiết kế truncation rõ ràng.

Không dùng:

```java
// SAI: so reference của 2 mảng byte, không so nội dung.
boolean equal = expectedTag == receivedTagBytes;
```

Không so hex string bằng logic tự viết có thể dừng ở ký tự đầu khác nhau rồi cố diễn giải là “constant time”; chuyển tag được truyền (ví dụ hex/Base64) về byte đúng định dạng, xác nhận độ dài theo giao thức và so byte. Nếu giao thức cho phép **tag cắt ngắn**, độ dài truncation và chính sách an toàn phải được xác định trước, thống nhất hai phía và không phụ thuộc ý muốn của người gửi.

**Đừng trả về thông báo chi tiết khác nhau cho “sai tag” và “sai khóa” nếu tạo ra oracle hữu ích cho đối thủ.** Ghi nguyên nhân chi tiết trong kênh logging nội bộ có kiểm soát; API có thể dùng phản hồi lỗi xác thực thống nhất.

## 6. Kiểm tra provider có hỗ trợ HMAC trong môi trường chạy

HMAC trong Java thuộc engine **`Mac`**, không phải engine `MessageDigest`. Hai tên chuẩn có liên quan nhưng không hoán đổi:

- `Mac.getInstance("HmacSHA256")`: tên HMAC SHA-256 của Java.
- `MessageDigest.getInstance("SHA-256")`: tên digest SHA-256, không dùng khóa.
- `Mac.getInstance("SHA-256")`: không phải cách gọi chuẩn để yêu cầu HMAC.

Để khám phá các tên thuật toán `Mac` mà runtime đăng ký, đoạn sau là **một phần của phương thức Java** có import `java.security.Security` và `java.util.Set`:

```java
Set<String> names = Security.getAlgorithms("Mac");
names.stream().sorted(String.CASE_INSENSITIVE_ORDER)
        .forEach(System.out::println);
```

Để tra cứu theo provider cụ thể, đặt đoạn sau trong một phương thức có import `java.security.Provider`, `java.security.Security` và `javax.crypto.Mac`, với xử lý `NoSuchAlgorithmException`:

```java
for (Provider provider : Security.getProviders()) {
    Provider.Service service = provider.getService("Mac", "HmacSHA256");
    if (service != null) {
        System.out.println(provider.getName() + ": " + service.getAlgorithm());
    }
}
```

`provider.getService` cho biết provider **quảng bá** một service trùng engine/tên (hoặc alias). Để biết nó dùng được với khóa thật, tạo `Mac.getInstance("HmacSHA256", provider)`, `init` bằng khóa theo chính sách và kiểm tra `doFinal` bằng vector. `Security.getAlgorithms("Mac")` không chứng minh mọi provider hỗ trợ mọi tên được liệt kê. Đừng hardcode tên `SunJCE` hoặc cho rằng tên/alias provider là đồng nhất trên mọi JDK, FIPS mode, thiết bị hoặc môi trường container.

Các lỗi đáng phân biệt:

| Lỗi/hiện tượng | Ý nghĩa và cách xử lý |
| --- | --- |
| `NoSuchAlgorithmException` từ `Mac.getInstance("HmacSHA256")` | Không có implementation được tìm thấy theo cơ chế chọn provider; xác minh tên chuẩn và provider thực tế |
| `NoSuchAlgorithmException` khi chỉ định provider | Provider được chỉ định không cung cấp tên thuật toán đó; thử kiểm tra `getService("Mac", "HmacSHA256")` rồi xác nhận factory |
| `InvalidKeyException` từ `mac.init(key)` | Khóa sai/không được provider chấp nhận; kiểm tra kiểu khóa, độ dài, policy, quyền HSM/keystore |
| `IllegalStateException` khi `update`/`doFinal` trước `init` | Engine chưa khởi tạo khóa; luôn `init` trước khi xử lý dữ liệu |
| HMAC không khớp dù thuật toán có hỗ trợ | Byte input/charset, phiên bản key, keyId, canonicalization, field order, tag encoding hoặc tag truncation khác nhau |
| Cùng tag cũ vẫn được dùng lại để gọi API | HMAC không tự chống replay; cần đưa thời gian/nonce/counter vào dữ liệu được xác thực và kiểm tra việc sử dụng lại |

Khi HMAC là yêu cầu bắt buộc của giao thức, **fail fast** nếu provider/khóa không sẵn sàng; không tự chuyển sang `SHA-256(key || message)` hay chọn một thuật toán MAC khác mà hai phía chưa thương lượng rõ ràng.

## 7. Thiết kế thông điệp được HMAC bảo vệ

Một tag chỉ có nghĩa khi hai phía thống nhất **chính xác byte nào được ký** và cách diễn giải của chúng. Những lỗi ứng dụng có thể làm hệ thống yếu đi dù `Mac` tính đúng.

### 7.1 Không nối nhiều trường mơ hồ

Nếu ký `HMAC(K, fieldA || fieldB)` mà không mã hóa ranh giới, cặp `("ab", "c")` và `("a", "bc")` cùng tạo byte `"abc"`, khiến tag hợp lệ cho một tổ hợp cũng hợp lệ cho tổ hợp khác. Dùng định dạng binary có **độ dài từng trường**, serialization chuẩn hóa, hoặc encoding đơn nghĩa có cấu trúc rõ ràng. Đừng ghép các chuỗi bằng một dấu phân cách mà input có thể chứa nếu chưa có cơ chế escape chính xác.

### 7.2 Bao phủ đủ ngữ cảnh cần xác thực

Nếu tag dùng để xác thực một request API, giao thức có thể cần bao phủ `method`, `path`, một tập header đã định nghĩa, timestamp, nonce/counter, phiên bản giao thức và **byte chính xác của body** (hoặc digest của body với thuật toán được quy định) trong một encoding không mơ hồ. Nếu chỉ ký body nhưng không ký phương thức hoặc đích đến, tag hợp lệ có thể bị dùng sai ngữ cảnh.

Giao thức cũng phải quy định cách xử lý query encoding, đường dẫn đã normalize, Unicode, JSON và line endings. Bên gửi và bên nhận phải tính HMAC trên **cùng một dãy byte**, không phụ thuộc thứ tự trường do thư viện serialize tùy ý.

### 7.3 HMAC không tự ngăn replay

Đối thủ có thể ghi lại cả thông điệp **và tag đúng**, rồi gửi lại nguyên cặp. Kiểm tra HMAC vẫn cho `true`. Để hạn chế replay, xác thực timestamp hoặc nonce/sequence **nằm bên trong dữ liệu được HMAC bảo vệ**, áp dụng giới hạn thời gian, đồng hồ phù hợp và **lưu trạng thái các nonce/counter đã sử dụng** trong cửa sổ xác định nếu cần từ chối request trùng.

### 7.4 Quy tắc xác thực và điều hành khóa

Bên nhận chọn đúng khóa theo `keyId`/phiên bản được cấu hình, không theo khóa do bên gửi tự cung cấp. Tránh cho người gửi tùy chọn thuật toán yếu; dùng danh sách thuật toán cho phép và xác thực cả ngữ cảnh thuật toán/phiên bản nếu giao thức có nhiều lựa chọn. Rotation cần một khoảng hỗ trợ có kiểm soát đối với khóa cũ, cùng cơ chế revoke khi bị lộ.

Trong một hệ thống có nhiều phía cùng biết khóa, HMAC xác nhận rằng tag được tạo **bởi ai đó biết khóa**, không chứng minh duy nhất một cá nhân đã ký; vì vậy nó không thay được chữ ký số cho yêu cầu non-repudiation.

## 8. Lỗi phổ biến cần tránh

| Cách làm sai hoặc ngộ nhận | Cách đúng |
| --- | --- |
| `SHA-256(K \|\| M)` “cũng là HMAC vì có key” | Dùng `Mac` với `HmacSHA256`; tránh length-extension của tiền tố keyed hash |
| `SHA-256(M \|\| K)` “chắc chắn an toàn vì không bị length-extension như tiền tố” | Không suy từ một kiểu tấn công sang chứng minh an toàn; dùng MAC đã chuẩn hóa |
| So `HMAC-SHA256` với output của `SHA-256(K \|\| M)` và cho rằng lỗi Java | Đó là hai công thức khác nhau; HMAC có inner/outer pad và hai lần hash |
| Đưa Java `String.getBytes()` không chỉ định charset | Dùng `StandardCharsets.UTF_8` và xác định schema byte ở hai phía |
| Dùng `new String(tagBytes)` để lưu tag | Dùng hex/Base64 với encoding chuẩn; giữ tag dưới dạng byte khi so |
| Dùng `==` so hai `byte[]` | So nội dung bằng `MessageDigest.isEqual`, xác thực format/độ dài tag |
| Tạo khóa từ mật khẩu dễ đoán rồi làm HMAC | Dùng khóa ngẫu nhiên đủ entropy và quản lý khóa; nếu đầu vào là password, cần KDF theo thiết kế riêng |
| Thấy HMAC hợp lệ rồi cho phép lặp giao dịch | Ràng buộc và kiểm tra nonce/timestamp/counter; HMAC không tự chống replay |
| Chia sẻ một `Mac` instance mutable qua nhiều request đồng thời | Tạo instance mới hoặc tổ chức state riêng cho từng thao tác |
| Log khóa, dùng khóa RFC trong production | Dùng secret manager/KMS/HSM, kiểm soát quyền và rotation |
| Dùng HMAC làm cơ chế lưu mật khẩu | HMAC là MAC cho thông điệp; lưu mật khẩu cần hàm password hashing phù hợp như Argon2id/scrypt/bcrypt/PBKDF2 theo hệ thống |

## 9. Tự kiểm tra

1. Từ cấu trúc SHA-256 tiền tố `H(K || M)`, giải thích vì sao một đối thủ biết tag và độ dài khóa có thể tính tiếp digest cho dữ liệu được mở rộng, trong khi HMAC không lộ trực tiếp trạng thái hash bên trong.
2. Chạy `HmacVsConcatDemo`. Tại sao output của `prefixedSha256` và `hmac` cùng dài 32 byte nhưng khác nhau? Hai test vector RFC 4231 giúp bắt lỗi gì?
3. Đổi chỉ một byte của thông điệp `"Hi There"` rồi giữ tag cũ. Tại sao `verify` trả `false`? Nếu thay **cả khóa lẫn tag**, hai phía sẽ xảy ra điều gì?
4. Giải thích ví dụ `("ab", "c")` và `("a", "bc")`. Đề xuất một format encoding rõ ràng để HMAC hai trường có ranh giới không mơ hồ.
5. Thiết kế quy trình xác thực webhook bằng HMAC-SHA256: trường nào cần được bao phủ, cách quản lý `keyId`, giới hạn timestamp, theo dõi nonce và xử lý rotation?
6. Thử kiểm tra danh sách provider trên môi trường Java của bạn; phân biệt “provider quảng bá `Mac.HmacSHA256`” với “`Mac` khởi tạo và cho đúng test vector”.

## Tài liệu tham khảo

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): công thức HMAC, xử lý khóa, `ipad` và `opad`.
- [RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512](https://www.rfc-editor.org/rfc/rfc4231): test vector HMAC-SHA256 case 1 và 2.
- [Java SE 17 — `Mac`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): engine MAC, `init`, `update`, `doFinal`.
- [Java SE 17 — `SecretKeySpec`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/SecretKeySpec.html): bao gói khóa byte cho `Mac`.
- [Java SE 17 — `MessageDigest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): hash SHA-256 và so sánh byte bằng `isEqual`.
- [Java SE 17 — Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): chuẩn hóa tên `HmacSHA256` và `SHA-256`.
