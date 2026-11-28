# SecureRandom và tạo giá trị ngẫu nhiên phục vụ bảo mật

Trong Java 27, nhiều chức năng bảo mật cần những giá trị **khó đoán trước**: mã đặt lại mật khẩu, session token, khóa bí mật, salt khi băm mật khẩu, nonce của giao thức mật mã hoặc mã xác minh một lần. Dùng một bộ sinh số ngẫu nhiên “có vẻ khó đoán” là chưa đủ. Nếu kẻ tấn công suy ra được giá trị tiếp theo, chúng có thể đoán token, chiếm phiên đăng nhập hoặc phá vỡ giả định an toàn của cơ chế mật mã.

Java cung cấp **java.security.SecureRandom** để tạo các byte và số giả ngẫu nhiên phù hợp cho nhiều nhu cầu bảo mật. Đây là một **cryptographically secure pseudorandom number generator (CSPRNG)** được cung cấp thông qua hệ thống provider mật mã của Java. Cách triển khai và nguồn entropy có thể tùy môi trường, nhưng API được thiết kế cho những yêu cầu khác với **Random**, **ThreadLocalRandom** hay **SplittableRandom**.

Bài thuộc chương **Bảo mật ứng dụng Java**, tập trung vào cách tạo và sử dụng dữ liệu ngẫu nhiên một cách an toàn trong ứng dụng Java hiện đại. Các ví dụ dựa trên API đang áp dụng cho Java 27, không sử dụng kỹ thuật tạo seed dễ đoán hoặc những API đã lỗi thời.

Sau bài học, bạn có thể:

- Phân biệt **ngẫu nhiên thống kê** với **khó dự đoán về mặt mật mã**.
- Dùng **SecureRandom.nextBytes()** và **nextInt(bound)** đúng mục đích.
- Tạo token dạng **Base64url**, mã OTP số và salt có độ dài hợp lý.
- Hiểu sự khác nhau giữa **salt**, **nonce**, **IV**, **khóa bí mật** và **token xác thực**.
- Tránh **modulo bias**, seed yếu, tái sử dụng nonce và việc để lộ bí mật qua log.
- Hiểu vai trò của **provider**, **getInstanceStrong()**, **DRBG**, hiệu năng và kiểm thử.
- Thiết kế thêm **thời hạn, chống thử đoán, quyền truy cập, lưu trữ và thu hồi** để giá trị ngẫu nhiên thực sự phục vụ an toàn hệ thống.

## 1. Vì sao ngẫu nhiên phục vụ bảo mật khác ngẫu nhiên thông thường?

Hai chương trình có thể đều tạo một dãy số trông phân bố đều. Tuy nhiên, với mục đích bảo mật, điều cần thiết là kẻ tấn công **không dự đoán được giá trị bí mật tiếp theo**, ngay cả khi chúng quan sát các giá trị đã xuất hiện hoặc biết cách ứng dụng sinh số.

Ví dụ:

~~~java
import java.util.Random;

Random random = new Random();

int number = random.nextInt(1_000_000);
~~~

Đoạn mã này hợp lệ cho mô phỏng, trò chơi không có yếu tố bảo mật hoặc dữ liệu thử. **Random** không được thiết kế để bảo vệ bí mật trước đối thủ có khả năng phân tích đầu ra và trạng thái PRNG.

Với OTP hoặc token, hãy dùng:

~~~java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();

int code = secureRandom.nextInt(1_000_000);
~~~

Cùng một lời gọi **nextInt(bound)** nhưng nguồn dữ liệu khác nhau: **SecureRandom** được thiết kế với các đặc tính bảo mật của CSPRNG.

### Phân biệt các tiêu chí

| Tiêu chí | Ngẫu nhiên thông thường | Ngẫu nhiên phục vụ bảo mật |
|---|---|---|
| Mục tiêu | Mô phỏng, chia tải thử, dữ liệu giả | Chống đoán token, khóa, nonce khi có yêu cầu |
| Phân bố đều | Thường cần | Cũng cần, nhưng chưa đủ |
| Khó dự đoán đầu ra tiếp theo | Không phải bảo đảm của Random thông thường | Là yêu cầu quan trọng |
| Seed có thể công khai hoặc cố định | Có thể hữu ích cho tái lập kiểm thử | Không phù hợp cho bí mật production |
| Ví dụ Java | Random, SplittableRandom, ThreadLocalRandom | SecureRandom |
| Khả năng tái lập dãy kết quả | Hữu ích trong test | Thường không mong muốn trong production |

**Một dãy số vượt qua phép kiểm tra thống kê không chứng minh nó an toàn về mật mã.** Cần chọn bộ sinh phù hợp ngay từ đầu thay vì kiểm tra “trông có vẻ ngẫu nhiên” sau khi tạo.

## 2. SecureRandom trong Java 27

**SecureRandom** nằm trong package **java.security**:

~~~java
import java.security.SecureRandom;

SecureRandom random = new SecureRandom();
~~~

Constructor không tham số chọn cách triển khai thích hợp từ các provider được cấu hình trong môi trường Java. Nó cung cấp API quen thuộc như **nextInt()**, **nextLong()**, **nextBytes(byte[])** và những phương thức khác được kế thừa hoặc triển khai theo hợp đồng tương ứng.

~~~java
byte[] bytes = new byte[32];
random.nextBytes(bytes);

int index = random.nextInt(10);
long value = random.nextLong();
~~~

Ở đây:

- **nextBytes(bytes)** điền dữ liệu giả ngẫu nhiên bảo mật vào mảng byte đã cấp phát.
- **nextInt(10)** trả giá trị từ **0** đến **9**.
- **nextLong()** trả một giá trị long có thể âm hoặc dương; nó không tự tạo một token có cấu trúc phù hợp để đưa vào URL.

SecureRandom được hỗ trợ qua hệ thống **Security Provider**. Thuật toán mặc định, cách lấy entropy, khả năng tái sinh seed, chi phí khởi tạo hoặc tính chất chặn có thể phụ thuộc provider/hệ điều hành. Đừng tự giả định tất cả JVM đều chọn cùng thuật toán nội bộ.

### Không phải mọi RandomGenerator đều dành cho mật mã

Java có những API random generator phục vụ hiệu năng, chất lượng thống kê và khả năng tái lập. Một thuật toán nhanh hoặc có chu kỳ rất dài **không tự động đạt yêu cầu CSPRNG**. Khi API chứa chữ **security token**, **secret**, **salt**, **nonce** hay **key material**, hãy yêu cầu SecureRandom hoặc một API mật mã có hợp đồng tương đương.

## 3. Bắt đầu bằng SecureRandom.nextBytes()

Đối với một **token bí mật có đủ entropy**, biểu diễn ban đầu đơn giản nhất thường là một mảng byte:

~~~java
import java.security.SecureRandom;

SecureRandom random = new SecureRandom();

byte[] tokenBytes = new byte[32];  // 32 byte = 256 bit.
random.nextBytes(tokenBytes);
~~~

Nếu 32 byte được sinh độc lập và gần như phân bố đều theo hợp đồng của CSPRNG, không gian giá trị là:

\[
2^{32\times 8}=2^{256}
\]

Đây là **256 bit độ dài dữ liệu ngẫu nhiên**, thường được chọn cho token bearer có yêu cầu bảo mật cao. Năng lực bảo mật tổng thể vẫn phụ thuộc cách tạo, lưu, truyền và kiểm tra token.

### Độ dài byte khác độ dài chuỗi

- **16 byte** tương ứng 128 bit.
- **24 byte** tương ứng 192 bit.
- **32 byte** tương ứng 256 bit.

Mã hóa ra chuỗi **hex** hoặc **Base64url** không tạo thêm entropy; nó chỉ đổi cách biểu diễn cùng số byte.

Một giá trị 32 byte khi mã hóa Base64url không padding thường tạo chuỗi **43 ký tự**, nhưng không có nghĩa 43 ký tự đó mang 43 lần entropy của một ký tự ngẫu nhiên độc lập. Nguồn entropy vẫn là 32 byte.

Không nên chuyển trực tiếp byte tùy ý sang String bằng một charset văn bản và xem đó là token: một dãy byte ngẫu nhiên có thể chứa giá trị không hợp lệ hoặc ký tự khó truyền qua URL và giao thức văn bản.

## 4. Tạo token URL-safe bằng Base64url

Token dùng trong URL hoặc HTTP header nên có biểu diễn chỉ gồm ký tự dễ truyền đi. **Base64 URL-safe** dùng bảng ký tự phù hợp với URL và có thể bỏ dấu padding khi giao thức cho phép.

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class SecureTokens {
    private static final SecureRandom RANDOM = new SecureRandom();

    private SecureTokens() {}

    public static String createToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

Dùng:

~~~java
String token = SecureTokens.createToken();

System.out.println(token.length()); // 43
~~~

Chương trình **không in giá trị token** để tránh tạo thói quen ghi bí mật vào log. Trong môi trường phát triển, nếu cần kiểm thử format thì kiểm tra độ dài và các ký tự hợp lệ, không lưu token thật vào log dài hạn.

### Base64url không phải mã hóa bảo mật

Base64url chỉ là phép biểu diễn có thể đảo ngược. Ai có chuỗi token đều có thể giải mã thành dãy byte ban đầu.

**Token an toàn nhờ byte gốc được sinh khó đoán, không phải nhờ Base64url che giấu nội dung.**

### Không tạo token từ thời gian hoặc ID tuần tự

Ví dụ không phù hợp cho bearer token:

~~~java
// KHÔNG dùng cho bí mật xác thực:
String token = Long.toString(System.currentTimeMillis());

// KHÔNG dùng cho bí mật xác thực:
String another = "session-" + userId;
~~~

Thời gian, ID tuần tự và chuỗi dễ đoán không cung cấp không gian tìm kiếm cần thiết. Nếu chỉ cần một định danh hiển thị không phải bí mật, yêu cầu thiết kế có thể khác; đừng dùng cùng tiêu chí cho mọi loại mã.

## 5. Token bearer: entropy chỉ là điều kiện đầu

**Bearer token** là bí mật mà người nắm giữ nó có thể sử dụng để thực hiện một thao tác hoặc truy cập tài nguyên theo hợp đồng hệ thống.

Ví dụ:

- Token xác nhận địa chỉ email.
- Token đặt lại mật khẩu.
- Session token ngẫu nhiên do server phát hành.
- Token mời tham gia hệ thống, truy cập đường dẫn chia sẻ có giới hạn.
- Giá trị chống giả mạo yêu cầu được tạo theo cơ chế phù hợp.

SecureRandom giải quyết **khả năng khó đoán** của token. Nó **không tự giải quyết** các yêu cầu khác:

| Yêu cầu | Cách thiết kế ở tầng ứng dụng |
|---|---|
| Hết hạn | Lưu và kiểm tra thời điểm hết hạn phía server |
| Một lần sử dụng | Đánh dấu đã dùng hoặc xóa/thu hồi nguyên tử |
| Giới hạn quyền | Ràng buộc token với mục đích và đối tượng |
| Thu hồi | Có bản ghi trạng thái hoặc cơ chế vô hiệu hóa |
| Chống thử đoán | Rate limit, phát hiện lạm dụng, phân tích nhật ký phù hợp |
| Chống lộ | HTTPS, không ghi token vào log, bảo vệ cookie/header |
| Chống sử dụng chéo | Phân loại token theo **purpose**, audience và phạm vi |
| Bảo vệ khi database bị lộ | Cân nhắc chỉ lưu hash của token entropy cao |

Một token có 256 bit random vẫn có thể không an toàn nếu bị lộ trong URL lưu ở access log, được gửi qua kết nối không bảo mật hoặc không bị thu hồi sau khi sử dụng.

### Token trong URL có rủi ro gì?

URL có thể đi vào browser history, log của proxy, server, hệ thống phân tích hoặc các chỗ khác. Với token một lần trong đường dẫn, cần tối thiểu: HTTPS, TTL ngắn, single-use, thiết kế hạn chế log và chính sách phù hợp cho trang có tài nguyên từ bên thứ ba.

Các giải pháp dùng cookie nên thiết lập thuộc tính bảo vệ phù hợp như **Secure**, **HttpOnly**, **SameSite**, đồng thời cân nhắc cơ chế chống CSRF tương ứng. Random token không thay thế cấu hình cookie và kiểm tra quyền.

## 6. Lưu hash của token thay vì lưu bản rõ

Với token ngẫu nhiên **có entropy cao**, một thiết kế thường dùng là chỉ trả **token gốc** cho người dùng, còn server lưu **digest** dùng để đối chiếu khi nhận lại.

Ví dụ dùng **SHA-256** cho token được sinh từ CSPRNG:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

static byte[] sha256Token(String token)
        throws NoSuchAlgorithmException {

    MessageDigest digest = MessageDigest.getInstance("SHA-256");

    return digest.digest(
            token.getBytes(StandardCharsets.US_ASCII));
}
~~~

Tại thời điểm phát hành:

1. Sinh token bí mật từ SecureRandom.
2. Gửi token gốc cho người nhận qua kênh được bảo vệ.
3. Chỉ lưu digest, purpose, user/đối tượng, TTL và trạng thái sử dụng.
4. Khi người dùng gửi lại token, tính digest rồi tìm/so sánh bản ghi tương ứng.
5. Kiểm tra expiry, purpose, quyền và trạng thái dùng một lần theo cơ chế nguyên tử trước khi chấp nhận.

**SHA-256 ở đây phù hợp để băm token ngẫu nhiên entropy cao**, không phải khuyến nghị băm mật khẩu người dùng trực tiếp bằng SHA-256. Mật khẩu do con người chọn có entropy thấp hơn và cần **password hashing** có chi phí tính toán/tham số phù hợp, chẳng hạn Argon2id qua thư viện đáng tin cậy hoặc một cơ chế thích hợp khác theo chính sách hệ thống.

### So sánh digest

Nếu cần so sánh trực tiếp hai digest đã có:

~~~java
boolean match = MessageDigest.isEqual(
        presentedDigest,
        storedDigest);
~~~

**MessageDigest.isEqual(...)** được thiết kế để giảm phụ thuộc thời gian so sánh vào dữ liệu bí mật trong phạm vi phép so sánh byte. Tuy nhiên, một hệ thống vẫn có thể để lộ trạng thái qua thời gian truy vấn database, message trả về hoặc các bước xử lý khác. Không nên coi một phép so sánh byte đơn lẻ là giải pháp hoàn chỉnh cho side-channel.

## 7. Tạo OTP sáu chữ số bằng SecureRandom

OTP dạng số thường có độ dài cố định để người dùng dễ nhập. Với mã sáu chữ số:

~~~java
import java.security.SecureRandom;
import java.util.Locale;

SecureRandom random = new SecureRandom();

String otp = String.format(
        Locale.ROOT,
        "%06d",
        random.nextInt(1_000_000)
);
~~~

**nextInt(1_000_000)** tạo một số trong khoảng 0 đến 999999. **%06d** thêm số 0 ở đầu để kết quả luôn dài sáu chữ số, ví dụ **000042**.

### Lỗi thường gặp: mất số 0 đầu

~~~java
// Không đạt yêu cầu mã luôn dài sáu chữ số:
String otp = Integer.toString(random.nextInt(1_000_000));
~~~

Số **42** trở thành **"42"**, không phải **"000042"**. Với mã mà người dùng nhập, cần giữ format thống nhất.

### Sáu chữ số không có 256 bit entropy

Không gian mã sáu chữ số có đúng **1.000.000 khả năng**, tương đương khoảng:

\[
\log_2(1{,}000{,}000)\approx 19{,}93\text{ bit}
\]

Vì không gian tương đối nhỏ, **OTP sáu chữ số không an toàn nếu cho phép thử không giới hạn**. SecureRandom giúp không dự đoán được mã tiếp theo từ mã trước, nhưng không làm mã sáu chữ số chống được brute force trực tuyến nếu server không giới hạn số lần thử.

Một cơ chế OTP thực tế cần:

- TTL ngắn theo chính sách nghiệp vụ.
- Giới hạn số lần nhập sai theo user/phiên/thiết bị và cơ chế chống lạm dụng.
- Phát hành mã mới và vô hiệu hóa mã cũ theo hợp đồng.
- Một lần sử dụng nếu đó là mã xác minh dùng một lần.
- Không ghi mã ra log hoặc trả lại mã ở API cho người chưa được xác thực.
- Bảo vệ kênh gửi mã, đồng thời tính tới rủi ro của email/SMS.
- Xử lý race khi nhiều yêu cầu xác minh cùng lúc.

**OTP ngẫu nhiên do server phát hành** khác với **TOTP chuẩn theo thời gian**: TOTP được tính bằng thuật toán HMAC từ secret và thời điểm, không phải gọi SecureRandom để tạo mã mới mỗi lần. SecureRandom vẫn có vai trò khi tạo secret TOTP ban đầu.

## 8. Tránh modulo bias khi chọn giá trị trong khoảng

Một cách làm tưởng đơn giản:

~~~java
// Không nên dùng khi cần phân bố đều trong khoảng:
int choice = Math.abs(random.nextInt()) % 10;
~~~

Có hai vấn đề:

1. **Math.abs(Integer.MIN_VALUE)** vẫn âm vì giá trị đó không có đối số dương biểu diễn được trong **int**.
2. Phép **% bound** trên không gian số ngẫu nhiên có kích thước không chia hết cho bound có thể gây **modulo bias**, khiến một số kết quả xuất hiện nhiều hơn số khác.

Cách đúng cho khoảng từ **0 (bao gồm)** đến **bound (không bao gồm)**:

~~~java
int choice = random.nextInt(10); // 0..9
~~~

Phương thức **nextInt(bound)** thực hiện các bước cần thiết để tạo phân bố phù hợp trong khoảng theo hợp đồng API, thay vì tự ép số bằng phép modulo thiên lệch.

### Chọn phần tử trong danh sách

~~~java
import java.util.List;

List<String> options = List.of("A", "B", "C");

String selected = options.get(random.nextInt(options.size()));
~~~

Chỉ áp dụng khi danh sách không rỗng; với **size() == 0**, **nextInt(0)** ném **IllegalArgumentException**.

Nếu một lựa chọn tạo ra quyền lợi hoặc có giá trị bảo mật, không dùng ThreadLocalRandom chỉ vì muốn nhanh hơn.

## 9. Xáo trộn danh sách với SecureRandom

Java cung cấp **Collections.shuffle(List, Random)**, chấp nhận **SecureRandom** vì SecureRandom kế thừa Random.

~~~java
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

SecureRandom random = new SecureRandom();

List<String> codes = new ArrayList<>(
        List.of("A1", "B2", "C3", "D4"));

Collections.shuffle(codes, random);
~~~

Mẫu này hữu ích khi cần xáo trộn một danh sách với nguồn CSPRNG. Tuy nhiên, thuật toán shuffle của thư viện và tính chất của từng kiểu list vẫn cần phù hợp với yêu cầu cụ thể; **xáo trộn không mã hóa dữ liệu** và không thay thế quyền truy cập.

Nếu dùng danh sách để phát coupon hay phân bổ phần thưởng, còn cần chống phát trùng, trạng thái dùng một lần và cơ chế kiểm soát ở server. Ngẫu nhiên chỉ giải quyết cách chọn/chia thứ tự, không giải quyết toàn bộ quy tắc nghiệp vụ.

## 10. Salt trong lưu trữ mật khẩu là gì?

**Salt** là giá trị ngẫu nhiên riêng cho mỗi mật khẩu/bản ghi, được đưa vào một thuật toán **password hashing/KDF** thích hợp.

Mục đích:

- Làm cho các bản ghi dùng cùng mật khẩu không mặc nhiên có cùng kết quả hash.
- Hạn chế khả năng tái sử dụng các bảng tính sẵn khi kẻ tấn công có dữ liệu hash.
- Tách việc suy đoán mật khẩu giữa các bản ghi khác nhau.

Tạo salt:

~~~java
import java.security.SecureRandom;

SecureRandom random = new SecureRandom();

byte[] salt = new byte[16];
random.nextBytes(salt);
~~~

Đây là **16 byte = 128 bit** salt ngẫu nhiên, một độ dài thường được dùng trong nhiều cấu hình password hashing. Thông số cuối cùng phải phù hợp thuật toán/KDF và chính sách bảo mật đã chọn.

### Salt không phải secret

Salt thông thường **không cần giữ bí mật**. Nó có thể được lưu cùng password hash và tham số thuật toán. Điều quan trọng là mỗi bản ghi có salt thích hợp được sinh độc lập.

### Salt không thay thế password hashing

Ví dụ **không nên dùng** làm giải pháp lưu mật khẩu:

~~~java
// Không đủ cho lưu mật khẩu người dùng:
// SHA-256(password + salt)
~~~

Một phép băm nhanh vẫn khiến kẻ tấn công có thể thử rất nhiều mật khẩu theo thời gian nếu database bị lộ. Hãy dùng cơ chế băm mật khẩu được thiết kế cho mục đích này với chi phí tính toán/bộ nhớ phù hợp và chính sách nâng cấp tham số.

Trong Java SE có những API mật mã như **SecretKeyFactory** và **PBKDF2WithHmacSHA256** tại các provider phù hợp; các giải pháp như **Argon2id** thường cần thư viện bên ngoài đã được đánh giá. Không tự xây thuật toán băm mật khẩu bằng cách ghép các hàm băm thông thường.

## 11. Khóa bí mật: dùng KeyGenerator khi có thể

Khi cần khóa mã hóa đối xứng, API phù hợp hơn việc tự biến chuỗi thành byte thường là **KeyGenerator**:

~~~java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

SecureRandom random = new SecureRandom();

KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, random);

SecretKey key = generator.generateKey();
~~~

Trong ví dụ:

- **KeyGenerator** cung cấp khóa theo thuật toán đã chọn.
- **256** là độ dài khóa tính bằng bit, phù hợp khi provider và môi trường hỗ trợ.
- SecureRandom cung cấp nguồn ngẫu nhiên bảo mật cho quá trình sinh khóa.

**Không in, ghi log, commit vào repository hoặc trả trực tiếp khóa** qua API không được bảo vệ. Quản lý khóa, quyền truy cập, xoay vòng, sao lưu và thu hồi quan trọng không kém việc tạo khóa.

Nếu cần khóa có thể tồn tại giữa các lần chạy, hãy lưu qua cơ chế quản lý bí mật/khóa phù hợp. Tạo khóa mới mỗi khi restart rồi cố giải mã dữ liệu cũ sẽ thất bại nếu không có chính sách lưu khóa.

### Không tạo khóa từ mật khẩu bằng getBytes()

~~~java
// Không nên coi đây là khóa AES an toàn:
// byte[] key = password.getBytes(StandardCharsets.UTF_8);
~~~

Mật khẩu của con người không có phân bố đồng đều như khóa ngẫu nhiên và có độ dài byte không chắc phù hợp AES. Nếu bắt buộc dẫn xuất khóa từ mật khẩu, dùng KDF phù hợp với tham số và salt được quản lý đúng.

## 12. IV và nonce: ngẫu nhiên chưa phải toàn bộ hợp đồng

Trong mã hóa có xác thực như **AES-GCM**, dữ liệu **nonce/IV** phải tuân theo điều kiện rất quan trọng: **không được tái sử dụng cùng nonce với cùng khóa**.

Một cấu hình phổ biến là IV dài **12 byte (96 bit)**:

~~~java
SecureRandom random = new SecureRandom();

byte[] nonce = new byte[12];
random.nextBytes(nonce);
~~~

Nhưng **độ dài 12 byte ngẫu nhiên không bảo đảm tuyệt đối uniqueness**. Khi số lượng bản mã dưới cùng một khóa tăng, xác suất trùng nonce tăng theo hiệu ứng birthday. Trong hệ thống tạo rất nhiều bản mã, cần xét giới hạn thông điệp/khóa, chính sách xoay vòng và khả năng dùng bộ đếm nonce được quản lý an toàn theo giao thức cụ thể.

### Ví dụ khởi tạo AES-GCM

~~~java
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

static byte[] encrypt(
        byte[] plaintext,
        SecretKey key,
        SecureRandom random) throws Exception {

    byte[] nonce = new byte[12];
    random.nextBytes(nonce);

    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(128, nonce));

    byte[] ciphertextAndTag = cipher.doFinal(plaintext);

    // Trong giao thức thật, cần lưu/truyền nonce cùng ciphertextAndTag.
    // Không được dùng lại nonce này với cùng key.
    return ciphertextAndTag;
}
~~~

Đoạn trên **chỉ minh họa cách sinh và sử dụng nonce**, không phải một hàm mã hóa có hợp đồng hoàn chỉnh, vì nó chưa trả nonce cần thiết cho giải mã. Khi triển khai thực tế, định nghĩa định dạng bản mã có version, nonce, ciphertext và authentication tag; dùng AAD khi cần ràng buộc metadata, và xử lý lỗi xác thực khi giải mã.

**Không tái sử dụng nonce dưới cùng một khóa GCM**, kể cả khi plaintext khác. Lỗi này có thể làm mất các bảo đảm bảo mật quan trọng của GCM.

### Nonce có nhất thiết bí mật?

Trong nhiều giao thức, nonce/IV **không cần bí mật**, nhưng cần đáp ứng điều kiện uniqueness hoặc unpredictability tương ứng với thuật toán. **Salt**, **nonce**, **key** và **bearer token** có các yêu cầu khác nhau: không thể thay thế các khái niệm đó chỉ vì cùng là “giá trị random”.

## 13. Phân biệt token, key, salt, nonce và OTP

| Giá trị | Có cần bí mật? | Yêu cầu nổi bật | Thời gian sống thường gặp |
|---|---|---|---|
| Bearer token | Có | Khó đoán, scope, TTL, thu hồi | Theo phiên hoặc mục đích |
| Khóa mã hóa/HMAC | Có | Độ dài/định dạng đúng, sinh an toàn, quản lý khóa | Theo vòng đời khóa |
| Salt password hashing | Thường không | Ngẫu nhiên/duy nhất thích hợp cho từng bản ghi | Lưu cùng bản ghi |
| Nonce/IV AES-GCM | Thường không | Không tái sử dụng với cùng key, định dạng đúng | Theo từng lần mã hóa |
| OTP sáu chữ số | Có trong thời gian hiệu lực | Khó đoán, TTL, chống thử đoán, single-use | Ngắn |
| Định danh bản ghi không bí mật | Không nhất thiết | Uniqueness và tính tương thích hệ thống | Tùy dữ liệu |

Ví dụ **không đúng**: dùng một giá trị random duy nhất đồng thời làm **salt**, **nonce**, **khóa** và **token** chỉ để tiết kiệm một lần gọi SecureRandom. Những vai trò này cần tách biệt; đặc biệt bí mật khóa cần được quản lý độc lập.

## 14. Không tự chọn seed dễ đoán

Một số cách dùng không phù hợp cho bảo mật:

~~~java
import java.security.SecureRandom;
import java.nio.charset.StandardCharsets;

// KHÔNG nên dùng thời gian làm seed bảo mật:
SecureRandom weakIdea = new SecureRandom();
weakIdea.setSeed(System.currentTimeMillis());

// KHÔNG nên dùng password cố định làm seed bảo mật:
SecureRandom anotherWeakIdea = new SecureRandom(
        "fixed-seed".getBytes(StandardCharsets.UTF_8));
~~~

Đoạn trên minh họa **thiết kế cần tránh**, không phải cách cấu hình. Tùy provider, **setSeed(...)** có thể bổ sung trạng thái seed thay vì thay thế hoàn toàn trạng thái hiện có. Vì thế không thể suy ra rằng một lời gọi như vậy luôn khiến generator dự đoán được, nhưng **đây không phải phương pháp tạo entropy đáng tin cậy**, càng không nên dùng fixed seed để cố tái lập chuỗi bí mật trong production.

### Cách làm mặc định nên dùng

~~~java
SecureRandom random = new SecureRandom();

byte[] secret = new byte[32];
random.nextBytes(secret);
~~~

Thông thường, SecureRandom và provider sẽ xử lý cơ chế khởi tạo trạng thái từ nguồn entropy thích hợp. Bạn không cần tự lấy thời gian hiện tại, PID, tên máy hay một mã cứng để “bổ sung bảo mật”.

### setSeed() không phải lời hứa về tính tái lập

Ngay cả khi một provider có đặc tính deterministic khi nhận một seed cụ thể, **Java không cam kết một dãy SecureRandom cố định giống nhau giữa mọi provider/phiên bản khi đặt cùng seed**. Điều này khác với nhu cầu tạo dữ liệu test tái lập bằng bộ sinh phi mật mã.

Nếu môi trường có yêu cầu mật mã cụ thể, hãy cấu hình và kiểm chứng provider/thuật toán theo chính sách thay vì tự xây seeding protocol.

## 15. getInstanceStrong() có phải luôn tốt hơn không?

Java cung cấp:

~~~java
import java.security.SecureRandom;

SecureRandom strong = SecureRandom.getInstanceStrong();
~~~

**getInstanceStrong()** chọn một triển khai theo cấu hình thuật toán mạnh của môi trường Java. Nó có thể ném **NoSuchAlgorithmException** nếu không có cấu hình/thuật toán đáp ứng.

**Đừng mặc định getInstanceStrong() luôn là lựa chọn tốt nhất cho token được tạo liên tục trong một web service.** Một số triển khai/cấu hình có thể chặn khi lấy dữ liệu ngẫu nhiên hoặc gây chi phí khởi tạo/sinh số đáng kể. Ngay cả SecureRandom thông thường cũng có thể chặn theo provider và trạng thái entropy trong một số môi trường.

Với phần lớn ứng dụng, **new SecureRandom()** là điểm bắt đầu hợp lý. Khi có yêu cầu về chứng nhận, thuật toán hoặc provider, lựa chọn nên được quyết định bởi chính sách an ninh của hệ thống và kiểm thử trong môi trường chạy thật.

### Phân biệt “strong” và “không bao giờ block”

Tên method **getInstanceStrong** không hứa hẹn không chặn hoặc luôn có throughput cao hơn. Độ mạnh mật mã, khả năng cung cấp entropy và tính sẵn sàng khi tải lớn là các thuộc tính riêng cần xem xét.

## 16. DRBG, algorithm và Security Provider

**DRBG** là viết tắt của **Deterministic Random Bit Generator**, một loại CSPRNG dựa trên trạng thái nội bộ được khởi tạo từ entropy thích hợp. Java hiện đại có API cho những cấu hình DRBG khi provider hỗ trợ.

Ví dụ lựa chọn thuật toán tường minh:

~~~java
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;

static SecureRandom createDrbg()
        throws NoSuchAlgorithmException {
    return SecureRandom.getInstance("DRBG");
}
~~~

Việc **getInstance("DRBG")** thành công phụ thuộc provider được cài đặt và cấu hình. Không nên mặc định mọi môi trường Java tùy biến hoặc mọi runtime đều có cùng thuật toán này.

Khi cần cấu hình chi tiết, Java còn có **java.security.DrbgParameters** với các lựa chọn liên quan đến strength, capability và tham số thích hợp, tùy khả năng của provider.

### Khi nào cần chỉ định thuật toán cụ thể?

- Chính sách tổ chức yêu cầu thuật toán/provider xác định.
- Hệ thống cần chứng nhận hoặc môi trường FIPS đã được cấu hình.
- Có benchmark/kiểm thử thực tế về độ trễ hoặc tính sẵn sàng.
- Một giao thức yêu cầu khả năng đặc thù của generator.

Nếu không có yêu cầu như vậy, hardcode tên provider/thuật toán có thể làm mã khó di chuyển giữa các runtime. Quan trọng là bảo đảm **nguồn CSPRNG phù hợp và cấu hình đã được kiểm chứng**, không phải ghi một tên thuật toán trông có vẻ mạnh.

### Tránh dựa vào tên thuật toán để ước lượng chất lượng ngẫu nhiên

Một đoạn code in **random.getAlgorithm()** chỉ giúp quan sát cấu hình thuật toán được chọn; nó không chứng minh hệ thống đã có entropy tốt hoặc toàn bộ lifecycle của bí mật đã an toàn.

## 17. generateSeed(), nextBytes() và reseed()

SecureRandom cung cấp một số thao tác có thể bị nhầm mục đích:

| API | Ý nghĩa chính | Dùng cho trường hợp thông thường |
|---|---|---|
| **nextBytes(byte[])** | Tạo byte giả ngẫu nhiên bảo mật vào mảng | Lựa chọn mặc định cho token, salt, nonce |
| **generateSeed(int)** | Sinh seed bytes, thường phục vụ khởi tạo bộ sinh khác hoặc yêu cầu seed đặc thù | Không cần cho hầu hết token |
| **setSeed(byte[]/long)** | Cung cấp seed bổ sung/theo hợp đồng provider | Không tự chế seed từ thời gian, PID, password |
| **reseed()** / cấu hình DRBG | Yêu cầu tái seed ở những môi trường/implementation hỗ trợ | Chỉ khi chính sách và provider yêu cầu |

Một lỗi thiết kế là gọi **generateSeed(32)** ở mọi request chỉ vì tưởng “seed bytes chắc chắn mạnh hơn nextBytes”. **nextBytes()** là API thích hợp cho việc tạo dữ liệu giả ngẫu nhiên bảo mật thông thường; **generateSeed()** có thể truy cập nguồn entropy theo đường khác và có chi phí khác.

Không cần tự gọi **setSeed(System.nanoTime())** trước mỗi lần **nextBytes()**. Cách làm đó không có ý nghĩa bảo mật được chứng minh và có thể làm phức tạp hành vi của generator.

## 18. Tái sử dụng SecureRandom và thread safety

Một SecureRandom có thể được dùng chung giữa các thread theo hợp đồng đồng bộ của implementation. API SecureRandom xử lý vấn đề thread safety ở mức provider/JDK; nếu provider khai báo triển khai SPI không thread-safe, Java có cơ chế đồng bộ phù hợp cho các lời gọi tương ứng.

Mẫu đơn giản cho ứng dụng:

~~~java
import java.security.SecureRandom;

public final class TokenSource {
    private static final SecureRandom RANDOM = new SecureRandom();

    private TokenSource() {}

    public static byte[] newSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return bytes;
    }
}
~~~

Lợi ích:

- Tránh tạo một SecureRandom mới cho mỗi token không cần thiết.
- Centralize chính sách entropy/sinh số trong một thành phần.
- Dễ kiểm soát nơi sinh và kiểm thử format.

Tuy nhiên, một instance chia sẻ có thể tạo **contention** dưới tải rất cao tùy provider. Nếu cần throughput lớn, hãy đo trên runtime thật và cân nhắc cấu hình hoặc phân tách instance theo tài liệu provider; không tự dùng một PRNG không an toàn làm “tối ưu” cho bảo mật.

### Không dùng synchronization thủ công không cần thiết

Nếu chỉ gọi **nextBytes()** trên SecureRandom, thường không cần tự khóa thêm toàn bộ service. Ngược lại, việc dùng SecureRandom thread-safe **không làm các map, token store hay quy tắc cấp phát nghiệp vụ** xung quanh nó trở nên thread-safe.

## 19. Không chuyển một số nhỏ thành token entropy cao

Ví dụ không phù hợp:

~~~java
SecureRandom random = new SecureRandom();

String token = Integer.toHexString(random.nextInt());
~~~

Dù nguồn là CSPRNG, kết quả ở đây nhiều nhất chỉ chứa khoảng **32 bit dữ liệu ngẫu nhiên**, không thể trở thành token 256 bit nhờ chuyển sang hex.

Một số lỗi tương tự:

- Chỉ dùng **nextInt(1_000_000)** cho session ID.
- Tạo 10 ký tự từ một bảng ký tự nhưng dùng modulo thiên lệch hoặc seed yếu.
- Lấy một phần rất ngắn của token 32 byte làm secret thật.
- Dùng thời gian kết hợp một số random nhỏ rồi cho rằng chiều dài chuỗi tạo ra đủ bảo mật.

**Độ dài chuỗi hiển thị không đồng nghĩa với entropy.** Bắt đầu từ số byte ngẫu nhiên thích hợp rồi mã hóa mà không cắt ngắn tùy tiện.

### UUID.randomUUID() có phù hợp không?

**UUID.randomUUID()** tạo UUID phiên bản 4 sử dụng nguồn số ngẫu nhiên phù hợp với hợp đồng Java. Nó hữu ích cho nhiều yêu cầu định danh khó va chạm, nhưng UUID v4 có các bit dành riêng cho phiên bản/biến thể nên không có 128 bit ngẫu nhiên thuần túy (thông thường còn **122 bit ngẫu nhiên**).

Với token bearer mà chính sách yêu cầu **256 bit entropy**, cách rõ ràng hơn là sinh **32 byte với SecureRandom**. UUID có thể là ID công khai và token bearer có thể là một bí mật độc lập.

## 20. Sinh mã từ bảng chữ cái: hiểu rõ khoảng mẫu

Đôi khi giao thức bắt buộc token chỉ gồm ký tự chữ và số. Có thể chọn từng ký tự bằng **nextInt(alphabet.length())**:

~~~java
import java.security.SecureRandom;

static String randomCode(
        SecureRandom random,
        int length) {

    String alphabet =
            "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

    if (length <= 0) {
        throw new IllegalArgumentException("length must be positive");
    }

    StringBuilder result = new StringBuilder(length);

    for (int i = 0; i < length; i++) {
        int index = random.nextInt(alphabet.length());
        result.append(alphabet.charAt(index));
    }

    return result.toString();
}
~~~

Ví dụ bỏ các ký tự dễ nhầm như I, O, 0 và 1 để người dùng đọc mã thuận tiện hơn.

**Entropy tối đa** của mã có **N** ký tự, mỗi vị trí chọn đều từ bảng **A** ký tự, là:

\[
H=N\times \log_2(A)
\]

Ví dụ bảng 32 ký tự cung cấp **5 bit cho mỗi ký tự** nếu chọn đều; mã 12 ký tự cung cấp tối đa **60 bit**, thấp hơn token 32 byte.

Không dùng bảng ký tự nhỏ và mã ngắn cho session token có yêu cầu chống đoán cao. Các mã ngắn dành cho người dùng nhập cần kết hợp TTL, rate limit và phạm vi quyền chặt chẽ.

## 21. Kiểm thử SecureRandom thế nào?

Một số kiểu kiểm thử hữu ích:

1. **Kiểm tra định dạng:** token Base64url chỉ có ký tự thuộc bảng hợp lệ và độ dài dự kiến.
2. **Kiểm tra ranh giới:** nextInt(bound) không trả số nằm ngoài khoảng yêu cầu.
3. **Kiểm tra không dùng lại giá trị cố ý:** không hardcode secret hoặc tái sử dụng cùng nonce trong một đơn vị xử lý có trạng thái.
4. **Kiểm tra lifecycle:** token hết hạn, đã dùng hoặc bị thu hồi đều bị từ chối.
5. **Kiểm tra xử lý lỗi:** provider/thuật toán không có, hết hạn kết nối, token store lỗi.
6. **Kiểm tra đồng thời:** nhiều luồng phát hành token mà không dùng chung trạng thái nghiệp vụ không an toàn.
7. **Kiểm tra phân quyền:** token của user A hoặc purpose X không dùng được cho user B hoặc purpose Y.

Không nên viết test kiểu:

~~~java
// Không nên biến thành tiêu chí mật mã:
// assert token1 != token2 ở mọi lần test
// assert phân bố số trong 1000 mẫu là hoàn toàn đều
~~~

Các giá trị ngẫu nhiên **có thể trùng về mặt xác suất**; số lượng mẫu nhỏ không chứng minh CSPRNG an toàn. Bảo đảm về xác suất va chạm phải được đánh giá bằng không gian giá trị, số lần sinh và mô hình đe dọa, không phải kỳ vọng “test luôn khác nhau”.

### Testability và dependency injection

Có thể thiết kế một lớp nhận **SecureRandom** từ bên ngoài:

~~~java
import java.security.SecureRandom;
import java.util.Objects;

public final class RandomTokenIssuer {
    private final SecureRandom random;

    public RandomTokenIssuer(SecureRandom random) {
        this.random = Objects.requireNonNull(random);
    }

    public byte[] issue() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return bytes;
    }
}
~~~

Cách này giúp test gọi một thành phần có thể kiểm soát, nhưng trong production, **không được để một bộ sinh deterministic yếu hoặc seed cố định được vô tình inject vào hệ thống cấp bí mật**. Có thể cô lập kiểm thử thông qua một abstraction của token issuer để test nghiệp vụ mà không phải cố tái lập đầu ra mật mã.

## 22. Ví dụ tổng hợp chạy độc lập

Chương trình **SecureRandomDemo.java** sau minh họa:

- Tạo bearer token 32 byte mã hóa Base64url.
- Tạo OTP sáu chữ số có padding.
- Tạo salt 16 byte cho một bước password hashing về sau.
- Tạo nonce 12 byte cho AES-GCM và khóa AES bằng KeyGenerator.
- Tạo một giá trị trong khoảng bằng **nextInt(bound)**.
- Tính digest SHA-256 của token entropy cao và so sánh bằng **MessageDigest.isEqual**.
- Không in giá trị thực của token, OTP, khóa, salt hoặc nonce.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Locale;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class SecureRandomDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    private SecureRandomDemo() {}

    static byte[] randomBytes(int length) {
        if (length <= 0 || length > 1024) {
            throw new IllegalArgumentException("Invalid byte length");
        }

        byte[] bytes = new byte[length];
        RANDOM.nextBytes(bytes);
        return bytes;
    }

    static String bearerToken() {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(randomBytes(32));
    }

    static String sixDigitOtp() {
        return String.format(
                Locale.ROOT,
                "%06d",
                RANDOM.nextInt(1_000_000));
    }

    static byte[] tokenDigest(String token)
            throws GeneralSecurityException {

        MessageDigest digest =
                MessageDigest.getInstance("SHA-256");

        return digest.digest(
                token.getBytes(StandardCharsets.US_ASCII));
    }

    static SecretKey generateAesKey()
            throws GeneralSecurityException {

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        String token = bearerToken();
        String otp = sixDigitOtp();

        byte[] salt = randomBytes(16);
        byte[] nonce = randomBytes(12);

        SecretKey key = generateAesKey();

        byte[] storedDigest = tokenDigest(token);
        byte[] presentedDigest = tokenDigest(token);

        boolean valid = MessageDigest.isEqual(
                storedDigest, presentedDigest);

        System.out.println("tokenChars=" + token.length());
        System.out.println("otpDigits=" + otp.length());
        System.out.println("saltBytes=" + salt.length);
        System.out.println("nonceBytes=" + nonce.length);
        System.out.println("aesAlgorithm=" + key.getAlgorithm());
        System.out.println("digestMatches=" + valid);

        int index = RANDOM.nextInt(10);

        System.out.println(
                "indexInRange=" + (index >= 0 && index < 10));
    }
}
~~~

Kết quả có dạng:

~~~text
tokenChars=43
otpDigits=6
saltBytes=16
nonceBytes=12
aesAlgorithm=AES
digestMatches=true
indexInRange=true
~~~

Giải thích:

1. **RANDOM** là SecureRandom được tái sử dụng trong ví dụ.
2. **bearerToken()** sinh 32 byte khó đoán rồi mã hóa Base64url không padding; kết quả không chứa thông tin xác thực dựa trên user ID hoặc thời gian.
3. **sixDigitOtp()** dùng **nextInt(1_000_000)** để tránh tự modulo và format thành sáu chữ số; chưa có server-side TTL/rate limit vì đây chỉ là chương trình sinh mã.
4. **randomBytes(16)** và **randomBytes(12)** minh họa dữ liệu ngẫu nhiên ở độ dài thường gặp cho salt và nonce; không biến salt/nonce thành secret phải được xử lý như key.
5. **generateAesKey()** dùng KeyGenerator; không tạo khóa từ chuỗi người dùng.
6. **tokenDigest()** băm token entropy cao để minh họa lưu hash thay token bản rõ.
7. **MessageDigest.isEqual(...)** đối chiếu hai digest. Trong thực tế, token gửi từ bên ngoài phải còn trải qua kiểm tra expiry, purpose, trạng thái thu hồi và bảo vệ chống lạm dụng.
8. **indexInRange** chỉ kiểm tra biên của một lần lấy số; không phải test chứng minh chất lượng mật mã.
9. Giá trị token, OTP và key **không được in**. Ứng dụng thật còn cần cơ chế quản lý bí mật, quyền truy cập và lifecycle phù hợp.

Chương trình giả định provider hỗ trợ AES 256-bit như môi trường Java thông dụng hiện đại. Nếu môi trường có cấu hình mật mã hạn chế, **KeyGenerator.init(256, ...)** có thể không được chấp nhận; ứng dụng cần kiểm thử policy/provider thực tế.

## 23. Lỗi thường gặp và cách phòng tránh

| Sai lầm | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Dùng **Math.random()**, **Random**, **ThreadLocalRandom** cho token | Không có hợp đồng CSPRNG | Dùng **SecureRandom** |
| Tạo token từ timestamp hoặc ID tuần tự | Dễ đoán | Sinh byte bí mật đủ entropy |
| Tạo 32-bit random rồi mã hóa thành chuỗi dài | Entropy vẫn tối đa khoảng 32 bit | Chọn độ dài byte gốc phù hợp |
| Chuyển byte ngẫu nhiên thẳng thành UTF-8 | Có thể sinh ký tự lỗi hoặc khó truyền | Dùng Base64url hoặc hex |
| Dùng **Math.abs(random.nextInt()) % bound** | Có modulo bias và lỗi Integer.MIN_VALUE | Dùng **nextInt(bound)** |
| Cố định seed để tái lập token | Không phù hợp phát hành bí mật | Cho SecureRandom/provider khởi tạo an toàn |
| Dùng **getInstanceStrong()** cho mọi request mà không đo | Có thể chậm hoặc block tùy môi trường | Đánh giá provider, chọn theo yêu cầu |
| Gọi **generateSeed()** thay nextBytes cho mọi token | Khó kiểm soát chi phí, không cần thiết | Dùng **nextBytes()** thông thường |
| Dùng một nonce AES-GCM nhiều lần với cùng key | Có thể phá bảo đảm bảo mật của GCM | Bảo đảm uniqueness theo key |
| Xem salt như mật khẩu hoặc key | Nhầm vai trò và xử lý | Salt có thể công khai; password hash/key cần bảo vệ |
| Băm password bằng SHA-256 trực tiếp | Dễ bị tấn công thử mật khẩu | Dùng password hashing có tham số phù hợp |
| Token OTP sáu số nhưng không rate limit | Có thể bị thử đoán trực tuyến | TTL, giới hạn lần thử, single-use |
| Ghi token, OTP hoặc key vào log | Rò rỉ bí mật | Log metadata an toàn thay vì secret |
| Dùng UUID công khai như session secret theo mọi yêu cầu | Có thể không đáp ứng chính sách entropy hoặc tách biệt quyền | Tạo token bearer riêng khi cần |
| Dùng token ngẫu nhiên nhưng không giới hạn quyền | Token có thể bị lạm dụng ngoài mục đích | Ràng buộc purpose, audience, expiry |
| So sánh token rồi bỏ qua trạng thái đã dùng | Token dùng lại được | Thu hồi hoặc đánh dấu single-use nguyên tử |
| Chỉ kiểm tra format trong unit test rồi tuyên bố an toàn | Không đánh giá lifecycle và threat model | Kiểm tra rủi ro hệ thống cùng chính sách mật mã |
| Chọn provider/DRBG mà không kiểm tra production | Khác biệt thuật toán, entropy hoặc blocking | Kiểm thử môi trường mục tiêu và cấu hình chính sách |

## 24. Checklist bảo mật trước khi phát hành giá trị ngẫu nhiên

Trước khi sử dụng SecureRandom trong ứng dụng Java 27, hãy tự hỏi:

1. Giá trị được sinh là **token**, **OTP**, **salt**, **nonce**, **key** hay chỉ là **ID không bí mật**?
2. Nguồn sinh có phải **SecureRandom** hoặc API mật mã đáng tin cậy không?
3. Số **bit ngẫu nhiên thực tế** có đáp ứng mục đích và mô hình tấn công không?
4. Có đang dùng phép modulo thủ công, seed cố định hoặc dữ liệu dự đoán được không?
5. Nếu encode thành chuỗi, format có tương thích URL/header/DB và không tự giảm entropy không?
6. Nếu là token, có **TTL**, purpose, đối tượng, quyền, trạng thái và thu hồi không?
7. Nếu là OTP ngắn, có chống thử đoán, giới hạn lần nhập sai và single-use không?
8. Nếu lưu token, có thể chỉ lưu **digest của token entropy cao** thay cho giá trị bản rõ không?
9. Nếu là salt, có được tạo mới phù hợp cho từng bản ghi và dùng cùng password hashing đúng chuẩn không?
10. Nếu là key, có dùng **KeyGenerator/KDF** và quản lý secret đúng quy trình không?
11. Nếu là nonce/IV, có bảo đảm quy tắc **không dùng lại với cùng key**, nhất là AES-GCM không?
12. Có tránh ghi key/token/OTP vào logs, metrics, traces và thông báo lỗi không?
13. Có phân định ai sinh, ai lưu, ai kiểm tra và ai có quyền thu hồi bí mật không?
14. Provider/thuật toán có phù hợp môi trường triển khai, chính sách tổ chức và khả năng chạy liên tục không?
15. Hệ thống có kiểm thử cả lỗi, quá tải, concurrency, vòng đời secret và tình huống database bị lộ không?

## Kết luận

**SecureRandom** là API chuẩn cần ưu tiên khi tạo các byte và số khó dự đoán phục vụ bảo mật trong Java 27. Dùng **nextBytes()** cho token, salt và những giá trị cần chuỗi byte; dùng **nextInt(bound)** để chọn đều trong một khoảng, tránh tự modulo dữ liệu từ CSPRNG. Nếu cần token văn bản, **Base64url** là cách mã hóa phù hợp và không làm thay đổi entropy gốc.

Tuy nhiên, **ngẫu nhiên tốt không tự tạo ra hệ thống an toàn**. Bearer token cần TTL, quyền, thu hồi và bảo vệ chống rò rỉ; OTP ngắn cần rate limit; salt phải đi cùng password hashing phù hợp; nonce của AES-GCM phải được bảo đảm không lặp lại dưới cùng khóa; key cần một vòng đời quản lý bí mật độc lập.

Thiết kế bảo mật đúng là **chọn nguồn sinh đáng tin cậy, xác định số bit cần thiết và bảo vệ toàn bộ vòng đời của giá trị**, từ lúc phát hành đến khi xác minh, hết hạn hoặc thu hồi.
