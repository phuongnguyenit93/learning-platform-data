# `SecureRandom` cho yêu cầu không thể dự đoán trong Java

## 1. Vì sao “ngẫu nhiên” chưa đủ cho bảo mật?

Một số tác vụ chỉ cần dữ liệu **trông có vẻ ngẫu nhiên**: xáo trộn câu hỏi luyện tập, giả lập tung xúc xắc, sinh dữ liệu kiểm thử. Nhưng một số tác vụ đòi hỏi kẻ tấn công **không thể dự đoán khả thi** giá trị kế tiếp, kể cả khi họ đã nhìn thấy nhiều giá trị trước đó. Đó là yêu cầu phổ biến khi sinh:

- Token đặt lại mật khẩu hoặc xác minh email chứa bí mật.
- Session token, API token, nonce bí mật, mã truy cập ngẫu nhiên.
- OTP được sinh bởi máy chủ (kèm kiểm soát số lần thử).
- Vật liệu ngẫu nhiên dành cho một số thao tác mật mã.

Trong Java, `java.security.SecureRandom` là API sinh số ngẫu nhiên dành cho bối cảnh bảo mật. Nó lấy đầu ra từ một bộ sinh được cung cấp qua **security provider**; với triển khai mật mã phù hợp và nguồn seed đủ entropy, đầu ra được thiết kế để chống dự đoán bằng phương pháp tính toán.

`java.util.Random`, `Math.random()` và `ThreadLocalRandom` có ích cho mô phỏng hay ứng dụng thông thường, nhưng **không đáp ứng hợp đồng cần tính không thể dự đoán của bí mật bảo mật**. Một bộ sinh có thống kê phân bố “đẹp” vẫn có thể bị dự đoán nếu biết trạng thái hoặc seed. Ngược lại, `SecureRandom` ưu tiên thuộc tính bảo mật; không nên lấy một vài kết quả trông hỗn loạn để chứng minh thuật toán an toàn.

Sau bài học, bạn có thể chọn đúng API, tạo token dạng byte và mã OTP bằng `SecureRandom`, hiểu nguồn seed/provider, tránh modulo bias, và kết hợp token với các kiểm soát vận hành phù hợp.

## 2. Mô hình tư duy: random thông thường và cryptographic random

| Tiêu chí | `Random`, `ThreadLocalRandom`, `Math.random()` | `SecureRandom` |
|---|---|---|
| Mục tiêu chính | Mô phỏng, phân bố thống kê, tốc độ | Giá trị khó dự đoán về mặt tính toán |
| Dùng cho token bí mật | **Không nên** | **Nên**, với độ dài và quản lý token phù hợp |
| Seed cố định để tái hiện test | Thường hữu ích với `new Random(seed)` | Không phải cách phù hợp để tạo bí mật thật |
| Thuộc tính đầu ra | Phụ thuộc thuật toán, không cam kết an toàn mật mã | Theo thuật toán/provider mật mã đã chọn |
| Hiệu năng | Thường phù hợp cho lượng lớn dữ liệu mô phỏng | Có thể tốn chi phí khởi tạo hoặc lấy entropy hơn |
| Kết quả có luôn duy nhất? | Không | **Cũng không**; ngẫu nhiên khác với đảm bảo duy nhất |

**Không thể dự đoán** không đồng nghĩa **không bao giờ trùng**. Ngay cả token dài 256 bit cũng có xác suất va chạm khác 0; nếu hệ thống bắt buộc khóa duy nhất, cần ràng buộc dữ liệu tương ứng và xử lý va chạm hiếm gặp.

Về mặt triển khai, nhiều thuật toán `SecureRandom` là **CSPRNG** (*cryptographically secure pseudorandom number generator*): trạng thái bên trong và seed hỗ trợ tạo ra chuỗi đầu ra có đặc tính chống dự đoán. Điều này không có nghĩa từng byte phải được đọc trực tiếp từ phần cứng ở mỗi lần gọi. Một số provider còn có cơ chế RNG khác; hợp đồng `SecureRandom` trừu tượng hóa lựa chọn này.

### Khi nào phải dùng `SecureRandom`?

Đặt câu hỏi: “Nếu người ngoài đoán được giá trị tiếp theo, họ có thể chiếm tài khoản, bỏ qua xác minh, giả mạo yêu cầu hay tiếp cận tài nguyên không?” Nếu câu trả lời là **có**, đây là trường hợp điển hình cần `SecureRandom` (và các biện pháp bảo vệ khác), thay vì generator phục vụ mô phỏng.

## 3. API quan trọng và cách khởi tạo

Bắt đầu bằng cách đơn giản, không tự cấu hình seed:

```java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
```

Đây là đoạn mã minh họa đặt trong lớp hoặc phương thức. Constructor không tham số chọn một thuật toán và provider mặc định theo cấu hình Java đang chạy. Đừng giả định tất cả máy hoặc phiên bản JDK đều chọn cùng thuật toán.

Một số phương thức cần nắm:

| API | Ý nghĩa |
|---|---|
| `new SecureRandom()` | Lấy bộ sinh mặc định do Java/provider chọn |
| `nextBytes(byte[] bytes)` | Điền byte ngẫu nhiên vào mảng đã cấp |
| `nextInt(int bound)` | Số `int` phân bố đều trong `[0, bound)`; `bound > 0` |
| `nextLong()` | Lấy giá trị `long` ngẫu nhiên |
| `generateSeed(int numBytes)` | Tạo các byte dành cho **seed**, chủ yếu cho bộ sinh khác |
| `getAlgorithm()`, `getProvider()` | Cho biết thuật toán/provider thực tế, hữu ích khi chẩn đoán |
| `SecureRandom.getInstance("DRBG")` | Yêu cầu thuật toán cụ thể; có thể ném `NoSuchAlgorithmException` nếu môi trường không hỗ trợ |
| `SecureRandom.getInstanceStrong()` | Chọn theo cấu hình `securerandom.strongAlgorithms`; có thể có chi phí/chờ entropy tùy provider |

**Lựa chọn mặc định:** Đối với token thông thường trong ứng dụng Java hiện đại, `new SecureRandom()` cùng `nextBytes()` thường là điểm bắt đầu hợp lý. Nếu tổ chức có yêu cầu cụ thể về thuật toán, compliance, DRBG, FIPS hoặc provider, hãy cấu hình và kiểm chứng riêng theo môi trường triển khai. Tên `getInstanceStrong()` không có nghĩa cứ đổi sang đó là hệ thống an toàn hơn trong mọi trường hợp; thuật toán được chọn, khả năng chờ và hiệu năng phụ thuộc cấu hình.

## 4. Ví dụ hoàn chỉnh: token bí mật 32 byte an toàn cho URL

**Mục tiêu:** Sinh **32 byte ngẫu nhiên** (256 bit đầu ra), rồi mã hóa sang Base64 URL-safe **không padding**. Dạng này có thể dùng làm bí mật trong đường dẫn hoặc tham số truyền nếu được xử lý cẩn thận. Base64 chỉ **mã hóa biểu diễn**, không mã hóa bảo mật; giá trị token vẫn là bí mật phải bảo vệ.

**Tệp `SecureTokenDemo.java` — Java 17+:**

```java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final int TOKEN_BYTES = 32;

    public static String newToken() {
        byte[] bytes = new byte[TOKEN_BYTES];
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static void main(String[] args) {
        String token = newToken();

        // Chỉ in thuộc tính kiểm thử, không in bí mật thật.
        System.out.println("tokenLength=" + token.length());
        System.out.println("decodedBytes="
                + Base64.getUrlDecoder().decode(token).length);
        System.out.println("urlSafe="
                + token.matches("[A-Za-z0-9_-]{43}"));
    }
}
```

Biên dịch và chạy:

```bash
javac SecureTokenDemo.java
java SecureTokenDemo
```

Kết quả:

```text
tokenLength=43
decodedBytes=32
urlSafe=true
```

Kết quả in ra ổn định vì chương trình kiểm tra **hình dạng**, không in nội dung token ngẫu nhiên. Giá trị token thay đổi giữa các lần chạy, nhưng **không cam kết mọi lần đều khác nhau tuyệt đối**.

Giải thích từng bước:

1. `new byte[32]` cấp đúng 32 byte.
2. `RANDOM.nextBytes(bytes)` điền các byte không thể dự đoán khả thi theo cam kết của provider bảo mật.
3. `Base64.getUrlEncoder()` dùng bảng ký tự `A–Z`, `a–z`, `0–9`, `-`, `_`, phù hợp để đưa vào URL hơn Base64 thông thường dùng `+` và `/`.
4. `withoutPadding()` bỏ dấu `=` cuối; **32 byte cho chuỗi Base64URL không padding dài 43 ký tự**.
5. Khi cần khôi phục byte ban đầu, `Base64.getUrlDecoder().decode(token)` giải mã lại đúng 32 byte.

Nếu mỗi byte có entropy lý tưởng, 32 byte tương ứng không gian khoảng `2^256` giá trị. Tuy nhiên, **độ dài 256 bit không tự động bảo đảm toàn bộ hệ thống an toàn 256 bit**: phải có nguồn entropy/provider tốt, không rò rỉ token và xử lý vòng đời bí mật đúng cách. Việc cắt chuỗi kết quả xuống vài ký tự sẽ làm giảm đáng kể không gian đoán.

### Vì sao không in token ra console?

Token reset hoặc session là **bearer secret**: bất kỳ ai sở hữu token hợp lệ trong thời gian có hiệu lực đều có thể sử dụng quyền mà token đại diện. Log, telemetry, lịch sử URL, hệ thống theo dõi lỗi và analytics đều có thể vô tình giữ lại giá trị bí mật. Ví dụ trên cố ý chỉ in các thuộc tính kiểm tra, không in token.

## 5. Tạo mã OTP sáu chữ số: ngẫu nhiên mạnh vẫn cần bảo vệ bổ sung

OTP dạng `000000`–`999999` chỉ có **1.000.000 giá trị khả dĩ**. `SecureRandom` giúp kẻ tấn công khó dự đoán chuỗi phát sinh, nhưng **không làm tăng không gian đoán** của một mã sáu chữ số. Mã ngắn bắt buộc phải đi kèm TTL ngắn, hạn chế lượt thử, xác minh một lần và ràng buộc vào phiên/yêu cầu/người nhận.

**Tệp `SecureOtpDemo.java`:**

```java
import java.security.SecureRandom;
import java.util.Locale;

public class SecureOtpDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String sixDigitCode() {
        int value = RANDOM.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }

    public static void main(String[] args) {
        String otp = sixDigitCode();

        System.out.println("otpLength=" + otp.length());
        System.out.println("onlyDigits=" + otp.matches("[0-9]{6}"));
    }
}
```

```bash
javac SecureOtpDemo.java
java SecureOtpDemo
```

Kết quả:

```text
otpLength=6
onlyDigits=true
```

Các chi tiết dễ bị bỏ qua:

- `nextInt(1_000_000)` trả số từ **0 đến 999999**, không gồm 1000000; giới hạn phải dương.
- `%06d` giữ **đủ 6 chữ số**, kể cả trường hợp giá trị ngẫu nhiên là `000042`.
- Với một OTP cho phép bắt đầu bằng `0`, không dùng `100_000 + RANDOM.nextInt(900_000)`: cách đó bỏ mất toàn bộ các mã bắt đầu bằng 0 và chỉ còn 900.000 khả năng.
- Nếu chính sách **cấm số 0 đứng đầu**, lúc đó mới dùng miền `100000`–`999999`; đây là quy tắc nghiệp vụ khác.
- **Không** sinh số bằng `Math.abs(RANDOM.nextInt()) % 1_000_000`: modulo không bảo đảm phân bố đều, `Math.abs(Integer.MIN_VALUE)` vẫn âm do tràn, và việc lấy phần dư không xử lý được điều kiện bảo mật.

Đối với miền có giới hạn, dùng trực tiếp `nextInt(bound)` để API chọn giá trị phân bố đều mà không tự viết phép chia dư có bias. Ví dụ chọn chỉ số trong danh sách 10 phần tử: `RANDOM.nextInt(10)` trả các giá trị `0`–`9`.

### OTP được bảo vệ như thế nào ở hệ thống thật?

Cần kết hợp các ràng buộc: mã có hiệu lực ngắn; giới hạn số lượt thử theo tài khoản/yêu cầu/IP phù hợp; khóa hoặc vô hiệu hóa sau quá nhiều lần thử; buộc mã gắn với đúng thao tác, người nhận và thời điểm; mỗi mã chỉ được dùng thành công một lần. Nếu có nhiều request đồng thời, trạng thái “đã dùng” phải được cập nhật **nguyên tử** để ngăn sử dụng lặp. Tất cả kiểm tra cần thực hiện ở máy chủ.

## 6. Vòng đời của token: sinh tốt mới chỉ là bước đầu

Một luồng token đặt lại mật khẩu điển hình:

```text
Máy chủ
  |
  | SecureRandom.nextBytes(32)
  v
Token bí mật (Base64URL) ------> Gửi riêng cho chủ tài khoản
  |
  | SHA-256(token) / hash mật mã thích hợp
  v
Lưu hash + accountId + purpose + expiresAt + used=false
  |
  | Khi người dùng gửi token quay lại
  v
Hash token được gửi -> so khớp với bản lưu
  |
  +-- sai / hết hạn / sai mục đích / đã dùng: từ chối
  |
  +-- đúng: thực hiện tác vụ và đánh dấu used=true theo giao dịch an toàn
```

Trong ứng dụng thật, lưu **hash** của token ngẫu nhiên dài (thay vì giữ token gốc ở dạng plaintext trong cơ sở dữ liệu) có thể hạn chế tác động khi bảng token bị lộ. Với token có entropy cao, hàm băm SHA-256 thường phù hợp để làm dấu đối chiếu; mã OTP sáu chữ số có entropy thấp thì **không thể dựa vào SHA-256 đơn thuần để chống dò offline nếu bị lộ bản hash**. OTP đòi hỏi mô hình lưu trữ và kiểm soát riêng, có thể dùng HMAC với khóa bí mật của máy chủ cùng giới hạn lượt thử và thời hạn.

Đoạn code độc lập sau minh họa cách chỉ lưu/so sánh digest cho token entropy cao, **chưa thay thế đầy đủ** tầng xác thực, TTL hay cập nhật “used” nguyên tử.

**Tệp `TokenDigestDemo.java`:**

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public class TokenDigestDemo {
    private static byte[] sha256(String text)
            throws NoSuchAlgorithmException {
        return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.US_ASCII));
    }

    public static void main(String[] args)
            throws NoSuchAlgorithmException {
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);

        byte[] storedDigest = sha256(token);
        byte[] presentedDigest = sha256(token);

        System.out.println("digestBytes=" + storedDigest.length);
        System.out.println("match="
                + MessageDigest.isEqual(storedDigest, presentedDigest));
    }
}
```

```bash
javac TokenDigestDemo.java
java TokenDigestDemo
```

```text
digestBytes=32
match=true
```

`SHA-256` tạo digest 32 byte; `MessageDigest.isEqual` là API so sánh mảng byte thích hợp cho giá trị nhạy cảm về thời gian so sánh. Ở ví dụ này, `token` là giá trị riêng tư trong chương trình nhưng không được in ra; trong ứng dụng thật, máy chủ lưu `storedDigest` và chỉ chuyển token gốc đến người dùng qua kênh được bảo vệ.

**Không nhầm SHA-256 với thuật toán hash mật khẩu người dùng.** Mật khẩu do người dùng chọn có thể bị đoán, nên thường cần thuật toán KDF chuyên dụng như Argon2id, scrypt hoặc PBKDF2 với tham số phù hợp. Token ngẫu nhiên dài và OTP ngắn là hai tình huống lưu trữ có mô hình rủi ro khác nhau.

## 7. Seed, entropy, provider và `getInstanceStrong()`

### 7.1. Seed quyết định khả năng chống dự đoán

CSPRNG cần trạng thái khởi tạo có entropy đủ mạnh. Một `SecureRandom` mặc định thường tự khởi tạo bằng cơ chế/provider thích hợp khi cần dùng; lập trình viên không phải tự tạo seed từ đồng hồ.

**Tránh:**

```java
// Minh họa cách không nên dùng để tạo token bảo mật.
byte[] guessableSeed = {
        1, 2, 3, 4
};
SecureRandom random = new SecureRandom(guessableSeed);
```

Seed cố định hoặc đoán được từ thời gian, PID, tên tài khoản, mã học viên... có thể làm giảm thuộc tính không thể dự đoán. Cũng không có cơ sở để cho rằng chỉ vì tham số kiểu `byte[]` dài thì seed đã có entropy cao. Tùy provider, việc cung cấp seed và hành vi reseed khác nhau; **không dùng seed tự chế để tạo hoặc kiểm thử token thật**.

Một điểm API: `setSeed(...)` trên `SecureRandom` có thể bổ sung entropy vào trạng thái hiện có, chứ không nhất thiết thay thế seed như một cơ chế khởi tạo `Random` thông thường. Không nên dựa vào seed cố định để tái tạo cùng chuỗi `SecureRandom` giữa các JDK, provider hay máy chạy. Trong kiểm thử logic phụ thuộc nguồn ngẫu nhiên, có thể **tiêm giao diện nguồn dữ liệu giả** (fake) cho test, còn môi trường production phải dùng CSPRNG thật.

### 7.2. `getInstanceStrong()` có luôn là lựa chọn tốt hơn?

`SecureRandom.getInstanceStrong()` đọc cấu hình các thuật toán được ưu tiên mạnh tại thuộc tính bảo mật `securerandom.strongAlgorithms`. Phương thức có thể ném `NoSuchAlgorithmException`, và một số nguồn entropy/provider có thể chặn trong khi khởi tạo hoặc sinh dữ liệu.

Đối với endpoint chịu nhiều truy cập và cần token ngắn hạn, không nên tự động thay mọi lệnh `new SecureRandom()` bằng `getInstanceStrong()` mà chưa đánh giá thuật toán, cấu hình triển khai, tốc độ và độ trễ. Nếu yêu cầu tổ chức bắt buộc dùng DRBG hoặc provider cụ thể, hãy chọn tường minh theo quy định và kiểm thử trên đúng runtime, bao gồm trường hợp thiếu provider.

### 7.3. `nextBytes` và `generateSeed` khác nhau

Để **sinh token sử dụng ngay**, phương thức tiêu chuẩn là `nextBytes(byte[])`. `generateSeed(int)` có mục đích tạo byte seed, chẳng hạn để khởi tạo một RNG khác; nó có đặc điểm lấy entropy và hiệu năng phụ thuộc provider. Không bắt buộc phải gọi `generateSeed` trước `nextBytes` khi dùng `new SecureRandom()`.

### 7.4. Dùng cùng một đối tượng `SecureRandom`

Trong Java hiện đại, `SecureRandom` được tài liệu hóa là an toàn khi nhiều thread sử dụng chung; lớp có thể đồng bộ hoạt động với provider không công bố hỗ trợ thread safety. Vì vậy, cách đặt `private static final SecureRandom RANDOM = new SecureRandom();` trong ví dụ là một mô hình hợp lệ cho nhiều ứng dụng.

Nếu throughput rất cao, vẫn nên đo đạc trên provider thực tế: mức contention, entropy và khởi tạo có thể ảnh hưởng hiệu năng. Không tạo lại `SecureRandom` bên trong mỗi vòng lặp chỉ để hy vọng kết quả “ngẫu nhiên hơn”.

## 8. Các lỗi thường gặp

| Lỗi | Tác hại | Cách làm phù hợp |
|---|---|---|
| Dùng `Math.random()` cho token reset mật khẩu | Không có hợp đồng chống dự đoán của CSPRNG | Dùng `SecureRandom.nextBytes` |
| Dùng `new Random(System.currentTimeMillis())` cho OTP | Seed đồng hồ có thể đoán | Dùng `SecureRandom.nextInt(bound)` |
| Tạo token rất ngắn rồi tin rằng `SecureRandom` là đủ | Không gian đoán thấp | Dùng đủ số byte và bảo vệ vòng đời |
| Dùng `Math.abs(nextInt()) % bound` | Có thể bias và gặp `Integer.MIN_VALUE` | `nextInt(bound)` |
| Dùng Base64 rồi cho rằng đã mã hóa bí mật | Base64 dễ dàng giải mã | Coi chuỗi Base64URL là bearer secret |
| Ghi token thô vào log hoặc analytics | Rò rỉ bí mật | Chỉ ghi metadata không nhạy cảm |
| Dùng mã OTP không TTL/không giới hạn thử | Có thể brute force online | TTL, rate limit, khóa/thay mã và một lần dùng |
| Mặc định `getInstanceStrong()` luôn nhanh và không chặn | Có thể tăng độ trễ/khác provider | Đánh giá môi trường triển khai |
| Tạo seed từ timestamp hoặc một chuỗi hằng | Seed kém entropy | Để provider cung cấp entropy thích hợp |
| Cho rằng token ngẫu nhiên luôn duy nhất | Va chạm tuy hiếm vẫn có thể xảy ra | Kiểm tra/ràng buộc uniqueness nếu cần |
| In thử vài token rồi kết luận an toàn | Đầu ra “không lặp” không chứng minh chống dự đoán | Dựa vào thuật toán/provider phù hợp và kiểm thử hệ thống |

## 9. Cách kiểm thử đúng khi kết quả phải thay đổi

Vì đầu ra của CSPRNG không có giá trị cố định, không viết test dạng:

```java
// KHÔNG đúng: không thể kỳ vọng một giá trị token cố định.
assert token.equals("abc123");
```

Thay vào đó, kiểm thử những thuộc tính tất định:

```java
String token = SecureTokenDemo.newToken();

if (token.length() != 43
        || !token.matches("[A-Za-z0-9_-]{43}")
        || Base64.getUrlDecoder().decode(token).length != 32) {
    throw new AssertionError("Invalid token format");
}
```

Đây là đoạn mã minh họa dùng cùng lớp `SecureTokenDemo` đã định nghĩa ở mục 4; cần import `java.util.Base64` khi đặt trong tệp riêng. Có thể kiểm tra bổ sung việc token bị sửa hoặc đã dùng sẽ bị từ chối và cách xử lý sau khi hết hạn.

Các **bài kiểm tra phân bố thống kê** không chứng minh tính không thể dự đoán của một RNG. Tránh viết test dễ flake kiểu “100 token chắc chắn khác nhau” rồi xem đó là bằng chứng mật mã. Khi cần bảo đảm thuật toán tuân thủ tiêu chuẩn hoặc cấu hình provider, hãy dựa vào thư viện/provider được đánh giá, môi trường runtime được quản lý và test tích hợp đối với đường xử lý bí mật.

## 10. Câu hỏi tự kiểm tra

1. **Ứng dụng xáo trộn câu hỏi trắc nghiệm, kết quả không dùng làm bí mật. Có bắt buộc `SecureRandom` không?**  
   Không. `Random` hoặc một nguồn ngẫu nhiên thông thường có thể đủ nếu không có yêu cầu bảo mật.

2. **Ứng dụng phát token reset mật khẩu, người ngoài thấy token của vài người dùng khác. Nên dùng gì?**  
   Một CSPRNG như `SecureRandom`, tạo đủ byte entropy và bảo vệ token khi truyền, lưu, dùng và hết hạn.

3. **`RANDOM.nextInt(6)` có trả số 6 không?**  
   Không. Nó trả một trong `0, 1, 2, 3, 4, 5`.

4. **Vì sao `%06d` quan trọng trong OTP sáu chữ số?**  
   Vì số ngẫu nhiên `42` phải được biểu diễn thành `000042` nếu miền cho phép số 0 đứng đầu.

5. **Base64URL biến token thành dữ liệu đã mã hóa bảo mật hay chưa?**  
   Chưa. Đây chỉ là cách biểu diễn byte thành chuỗi có thể đọc/truyền; người nhận có thể giải mã mà không cần khóa.

6. **Vì sao OTP `000000`–`999999` vẫn có thể bị brute force dù sinh bằng `SecureRandom`?**  
   Vì chỉ có 1.000.000 khả năng; cần TTL, giới hạn lượt thử, ràng buộc phiên và cơ chế sử dụng một lần.

7. **Có nên dùng `SecureRandom.getInstanceStrong()` cho mọi request mà không kiểm tra provider?**  
   Không nên. Việc chọn thuật toán và chi phí/lúc chờ entropy phụ thuộc cấu hình, cần được đánh giá theo runtime.

8. **`SecureRandom` có đảm bảo hai lần sinh 32 byte không bao giờ giống nhau không?**  
   Không có bảo đảm tuyệt đối. Xác suất va chạm rất nhỏ nếu triển khai và entropy tốt, nhưng ràng buộc duy nhất phải được xử lý riêng khi nghiệp vụ yêu cầu.

## 11. Ghi nhớ và tài liệu tham khảo

Khi nhiệm vụ yêu cầu **khó dự đoán**, sử dụng `SecureRandom` với provider đáng tin cậy và seed từ nguồn entropy phù hợp. Dùng `nextBytes` cho secret token dài; dùng `nextInt(bound)` khi cần giá trị trong một miền; không tự modulo để tạo OTP. `SecureRandom` là thành phần **sinh bí mật**, không thay thế xác thực, giới hạn lượt thử, TTL, lưu trữ bí mật an toàn hay khả năng phát hiện lạm dụng.

Javadoc và tài liệu chính thức:

- [Java 21: `java.security.SecureRandom`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)
- [Java 21: `java.util.Base64`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.html)
- [Java 21: `java.security.MessageDigest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Java 21 Security Developer's Guide](https://docs.oracle.com/en/java/javase/21/security/)
