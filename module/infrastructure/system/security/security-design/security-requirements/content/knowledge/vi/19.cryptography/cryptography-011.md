# Randomness an toàn

## 1. Khi một giá trị ngẫu nhiên trở thành ranh giới bảo mật

Một liên kết đặt lại mật khẩu có thể cho phép người giữ nó thay đổi credential của tài khoản. Một token phiên có thể đại diện quyền truy cập của người dùng. Nếu các giá trị đó đoán được, hệ thống có thể mất quyền kiểm soát dù xác thực, phân quyền và mã hóa đường truyền ở những phần khác đều hoạt động đúng.

Randomness an toàn không có nghĩa chuỗi trông phức tạp, không có mẫu dễ nhìn hoặc ít bị trùng trong một lần thử. Điều cần thiết là nguồn sinh, trạng thái và cách sử dụng đáp ứng thuộc tính bảo mật của từng trường hợp: khó dự đoán, đủ không gian lựa chọn, không thiên lệch ngoài chủ đích hoặc không lặp trong một phạm vi xác định.

Trong thiết kế yêu cầu bảo mật, câu “sinh chuỗi random” phải được chuyển thành nghĩa vụ cụ thể: sinh cho mục đích gì, cần thuộc tính nào, dùng nguồn nào, độ dài bao nhiêu, đối phó đoán thử ra sao và điều gì xảy ra khi nguồn sinh không đáp ứng yêu cầu.

Sau bài này, người học có thể:

- Phân biệt khó đoán, phân bố, entropy và tính duy nhất.
- Chọn CSPRNG và API phù hợp thay cho bộ sinh dùng trong mô phỏng.
- Xác định yêu cầu khác nhau của bearer token, OTP, salt, khóa, IV và nonce.
- Nhận diện seed dễ đoán, modulo bias, cắt ngắn sai và lỗi vòng đời trạng thái sinh.
- Viết tiêu chí nghiệm thu và vận hành mà không nhầm kiểm tra thống kê với bằng chứng mật mã.

## 2. Những thuộc tính cần phân biệt

### 2.1. Khó đoán không đồng nghĩa duy nhất

Một bộ đếm có thể duy nhất nhưng rất dễ dự đoán. Một giá trị sinh ngẫu nhiên có thể khó đoán nhưng vẫn có xác suất trùng. Hai thuộc tính phục vụ hai mục tiêu khác nhau.

Nếu ID bản ghi chỉ dùng để định vị một đối tượng và luôn có phân quyền, yêu cầu chính có thể là duy nhất và ổn định. Nếu giá trị đóng vai trò bearer token, biết giá trị có thể đủ để thực hiện hành động theo hợp đồng; khi đó độ khó đoán là thuộc tính quan trọng.

Không dùng ID khó đoán để bỏ kiểm tra quyền trên đối tượng. Cũng không dùng một ID duy nhất theo thời gian làm token bí mật chỉ vì chưa thấy nó trùng.

### 2.2. Phân bố đều chưa đủ để an toàn mật mã

Một bộ sinh có thể tạo mẫu thống kê nhìn tốt nhưng trạng thái có thể suy ra từ các đầu ra đã quan sát. Đối với giá trị bảo mật, kẻ tấn công có thể biết thuật toán, thời điểm phát hành và một số giá trị của chính họ.

Do đó, “không thấy mẫu” hoặc “mỗi chữ số xuất hiện gần như nhau” không phải bằng chứng rằng giá trị kế tiếp không thể dự đoán.

### 2.3. Entropy không phải độ dài chuỗi hiển thị

Nếu một giá trị chỉ có N khả năng đồng đều, lượng thông tin lựa chọn là `log2(N)` bit. Một chuỗi 64 ký tự được tạo bằng cách hash một timestamp không mặc nhiên có độ khó đoán của 64 ký tự ngẫu nhiên độc lập.

Với nguồn không đồng đều, mức khó đoán còn phụ thuộc vào giá trị dễ xuất hiện nhất và thông tin mà đối thủ biết. NIST SP 800-90B tập trung vào nguồn entropy và cách đánh giá chúng; đó là phần khác với chỉ đếm byte đầu ra. [NIST SP 800-90B về entropy source](https://csrc.nist.gov/pubs/sp/800/90/b/final).

Ứng dụng thông thường nên dựa vào nguồn và cơ chế đã được nền tảng quản lý thay vì tự ước lượng entropy từ thời gian, số tiến trình hoặc chuyển động chuột rồi tuyên bố mức an toàn.

### 2.4. Không gian giá trị và mức an toàn của bộ sinh

Sinh 32 byte tạo ra một biểu diễn có 256 bit dữ liệu. Điều đó không tự chứng minh có 256 bit entropy độc lập hoặc 256 bit security strength. Mức bảo vệ còn bị giới hạn bởi nguồn entropy, trạng thái, thuật toán và cách cấu hình bộ sinh.

Tăng độ dài đầu ra không tự sửa một seed dễ đoán. Hash nhiều lần hoặc thêm một tiền tố dài cũng không tạo thêm bí mật mà hệ thống chưa có.

## 3. CSPRNG và nguồn entropy

### 3.1. Bộ sinh bảo mật có thể là tất định bên trong

Cryptographically secure pseudorandom number generator, gọi tắt là CSPRNG, được thiết kế cho các mục đích cần đầu ra khó dự đoán theo mô hình bảo mật của nó. Một DRBG có thể mở rộng trạng thái đã được khởi tạo thích hợp thành nhiều bit đầu ra bằng thuật toán tất định.

NIST SP 800-90A mô tả các cơ chế DRBG dựa trên hàm băm hoặc block cipher. Việc thuật toán bên trong là tất định không mâu thuẫn với mục tiêu đầu ra khó đoán khi nguồn, trạng thái và sử dụng đáp ứng điều kiện của cơ chế. [NIST SP 800-90A Rev. 1 về DRBG](https://csrc.nist.gov/pubs/sp/800/90/a/r1/final).

### 3.2. Chuỗi bảo đảm

```mermaid
flowchart LR
    A[Nguồn entropy được nền tảng quản lý] --> B[Khởi tạo và cập nhật trạng thái bộ sinh]
    B --> C[CSPRNG được chọn theo profile]
    C --> D[Byte hoặc giá trị có giới hạn]
    D --> E[Biểu diễn token hoặc tham số]
    E --> F[Hợp đồng sử dụng và vòng đời]
```

Lỗi có thể xuất hiện ở bất kỳ đoạn nào. CSPRNG đúng không bù được việc cắt token còn quá ngắn. Token dài không bù được việc ghi nó vào log công khai. Nonce được sinh từ nguồn tốt không tự chứng minh không lặp trong toàn bộ vòng đời một khóa.

### 3.3. Bộ sinh dùng cho mô phỏng không có cùng hợp đồng

Trong Java, `java.util.Random` không phải bộ sinh an toàn mật mã. Nó phù hợp với những công việc không yêu cầu bí mật, nhưng không nên dùng làm nguồn cho session token, reset token hoặc khóa. [Java Random API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Random.html).

Không chọn một API chỉ dựa trên tên có chữ random, tốc độ cao hoặc khả năng tái lập. `Math.random()` và các bộ sinh tối ưu cho xử lý thông thường không được dùng thay cơ chế bảo mật theo thói quen.

### 3.4. Không tự chế seed từ dữ liệu dễ biết

Các nguồn như timestamp, user ID, IP, số tiến trình, bộ đếm hoặc tên máy có thể giúp tạo định danh, nhưng không tự trở thành entropy bí mật. Đối thủ thường có thể thu hẹp hoặc quan sát nhiều giá trị trong số đó.

Không thay cơ chế seed của nền tảng bằng một chuỗi cố định để “ổn định”, hoặc bằng thời gian hiện tại để “mỗi lần khác nhau”. Nếu một giao thức cần deterministic derivation, đó phải là cơ chế khác có thiết kế khóa và miền sử dụng rõ, không giả dạng một bộ sinh ngẫu nhiên mới.

## 4. Chọn thuộc tính theo mục đích

| Giá trị | Thuộc tính cần ưu tiên | Kiểm soát bổ sung |
| --- | --- | --- |
| Session hoặc bearer token | Khó đoán, không gian đủ lớn, phạm vi rõ | Hết hạn, thu hồi, bảo vệ lưu trữ và đường truyền |
| Reset token | Khó đoán, gắn đúng tài khoản và mục đích | Dùng một lần, thời hạn, giới hạn thử và cấp phát |
| OTP ngắn | Sinh đúng phân bố trong không gian đã chọn | Giới hạn thử nghiêm ngặt, thời hạn và ràng buộc challenge |
| Salt | Phân biệt các lần xử lý theo yêu cầu cơ chế | Lưu cùng metadata khi phù hợp; không coi là khóa bí mật |
| Nonce hoặc IV | Đáp ứng điều kiện của mode cụ thể | Phạm vi theo khóa, đồng thời, restart và giới hạn sử dụng |
| Khóa mật mã | Đúng thuật toán, kích thước và nguồn sinh | Quản lý khóa, quyền dùng, rotation và bảo vệ bí mật |
| ID công khai | Duy nhất và ổn định theo nghiệp vụ | Không thay phân quyền; yêu cầu khó đoán nếu mô hình cần |

Không đặt một quy tắc “mọi thứ đều random 16 byte” rồi dùng chung cho mọi hàng. Tên salt, IV và nonce cũng không đủ để suy ra chính sách; phải đọc hợp đồng của cơ chế mật mã đang sử dụng.

### 4.1. Bearer token

Nếu giữ token cho phép thực hiện một quyền, token phải được xử lý như credential. Cần nguồn CSPRNG được chấp thuận, độ dài theo profile, scope, thời hạn và cách xác minh an toàn.

Một profile minh họa có thể chọn 32 byte sinh từ CSPRNG cho token khôi phục. Đây là lựa chọn thiết kế của ví dụ, không phải tuyên bố mọi hệ thống hoặc mọi cơ chế xác thực đều cần cùng định dạng.

### 4.2. OTP không có cùng không gian với token dài

OTP 6 chữ số, nếu cho phép cả số 0 đầu và có phân bố đều, có một triệu khả năng, tương đương khoảng 19,93 bit lựa chọn. Nó không đạt độ khó đoán của token 32 byte chỉ vì cũng được CSPRNG sinh ra.

Nếu cho 5 lần đoán độc lập đối với một challenge đồng đều, xác suất thành công gần `5 / 1.000.000` trong mô hình đơn giản. Các con số này chỉ minh họa phép tính; lựa chọn số lần thử và thời hạn phải dựa trên mô hình rủi ro thực tế.

Việc cấp lại challenge, nhiều tài khoản, nhiều worker xác minh và giới hạn không đồng bộ có thể làm tổng số lần thử cao hơn dự kiến. Yêu cầu không nên chỉ giới hạn một request đơn lẻ hoặc một instance.

### 4.3. Salt không cần được giữ như token bí mật

Salt thường có vai trò làm các lần xử lý khác nhau không chia sẻ cùng đầu vào hiệu lực theo cơ chế sử dụng. Với cơ chế lưu mật khẩu phù hợp, salt có thể được lưu cùng kết quả và các tham số.

Salt không biến mật khẩu yếu thành mật khẩu có entropy cao. Không thay KDF mật khẩu bằng một hash nhanh chỉ vì đã thêm chuỗi random.

### 4.4. Nonce không phải lúc nào cũng chỉ cần khó đoán

Một số cơ chế, như AEAD dùng nonce phải không lặp theo khóa, cần kiểm soát tính duy nhất trong phạm vi đó. Nguồn ngẫu nhiên không tự loại bỏ xác suất trùng hoặc lỗi chia sẻ trạng thái. [RFC 5116 về yêu cầu nonce của AEAD](https://www.rfc-editor.org/rfc/rfc5116.html#section-3.1).

Không lấy quy tắc của một mode áp dụng cho mode khác. Có IV cần thuộc tính không dự đoán được; có nonce được phép hình thành từ bộ đếm nếu toàn bộ điều kiện duy nhất, lưu trạng thái và giới hạn của cơ chế được bảo đảm.

### 4.5. Khóa nên đi qua API sinh khóa phù hợp

Đối với khóa đối xứng trong Java, `KeyGenerator` cho phép sinh khóa theo thuật toán và tham số tương ứng, có thể nhận nguồn randomness khi khởi tạo. [Java KeyGenerator API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KeyGenerator.html).

Không chuyển một chuỗi dễ nhớ thành byte rồi gọi đó là khóa ngẫu nhiên. Nếu đầu vào là mật khẩu, cần một thiết kế dẫn xuất khóa phù hợp với loại mật khẩu và yêu cầu, không giả định nó giống khóa được sinh từ nguồn mật mã.

## 5. Ví dụ sinh giá trị bảo mật trong Java

### 5.1. Dùng SecureRandom và để nền tảng quản lý nguồn phù hợp

`SecureRandom` là API Java dành cho bộ sinh mạnh về mật mã. Tài liệu cũng nêu tác động của seed do caller cung cấp và khả năng một số thao tác chờ nguồn entropy, tùy implementation. Không tự seed bằng dữ liệu đoán được. [Java SecureRandom API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html).

Ví dụ minh họa:

```java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Locale;

public final class SecurityRandoms {
    private static final SecureRandom SOURCE = new SecureRandom();
    private static final Base64.Encoder TOKEN_ENCODER =
        Base64.getUrlEncoder().withoutPadding();

    private SecurityRandoms() {
    }

    public static String newOpaqueToken() {
        byte[] bytes = new byte[32];
        SOURCE.nextBytes(bytes);
        return TOKEN_ENCODER.encodeToString(bytes);
    }

    public static String newSixDigitCode() {
        int value = SOURCE.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }
}
```

`newOpaqueToken()` tạo 32 byte rồi biểu diễn bằng Base64url không padding. Kết quả có 43 ký tự ở định dạng này. Đây là biểu diễn của cùng dữ liệu, không phải bước tạo thêm entropy. Java cung cấp encoder URL-safe và tùy chọn bỏ padding. [Java Base64](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Base64.html), [Java Base64.Encoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Base64.Encoder.html).

`newSixDigitCode()` giữ cả các số 0 ở đầu và dùng API sinh số trong khoảng thay vì tự lấy phần dư. Hai hàm phục vụ hai hợp đồng khác nhau; không dùng mã 6 số thay token dài chỉ vì chúng cùng nằm trong một class.

Ví dụ chỉ thực hiện bước sinh. Nó chưa bao gồm profile provider, lưu trữ, hết hạn, chống đoán thử, xác minh, dùng một lần hoặc xử lý sự cố. Độ dài 32 byte cũng không chứng minh mọi runtime có mức an toàn nội tại là 256 bit.

### 5.2. Dùng lại nguồn sinh không đồng nghĩa dùng lại token

Đối tượng `SecureRandom` hỗ trợ sử dụng từ nhiều thread theo hợp đồng API. Có thể quản lý nguồn sinh theo vòng đời ứng dụng thay vì tự tạo và seed lại bằng timestamp trên mỗi request. [Java SecureRandom, thread safety](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html).

Mỗi lần cần một bí mật mới phải lấy đầu ra mới theo giao thức. Không cache một token rồi dùng cho nhiều người để tiết kiệm chi phí khởi tạo.

Hiệu năng, khả năng chờ và lựa chọn provider cần được đánh giá trên môi trường triển khai. Không thay bằng bộ sinh không an toàn khi có tải hoặc khi nguồn bảo mật khởi tạo chậm.

### 5.3. Provider và yêu cầu profile

Java có kiến trúc provider; nguồn và thuật toán thực tế phụ thuộc vào cấu hình và môi trường. Khi profile yêu cầu một cơ chế cụ thể, cần có ánh xạ và bằng chứng cho runtime đó. [Tài liệu JDK về provider và SecureRandom](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html).

Không hard-code tên một provider chỉ vì nó tồn tại trên máy phát triển rồi giả định mọi hệ điều hành đều giống nhau. Cũng không coi tên API là bằng chứng tự động về chứng nhận hoặc sự phù hợp với mọi profile tuân thủ.

Nếu một cơ chế yêu cầu không khả dụng, hành vi đúng là lỗi cấu hình hoặc lỗi cấp phát được quản lý, không âm thầm chọn nguồn yếu hơn ngoài policy.

## 6. Chuyển đổi đầu ra và modulo bias

### 6.1. Nguồn đúng vẫn có thể bị dùng sai

Giả sử lấy một byte phân bố đều trong 256 giá trị rồi tính phần dư cho 10:

```text
digit = unsignedByte % 10
```

256 không chia hết cho 10. Các số dư từ 0 đến 5 có 26 đầu vào tương ứng, còn từ 6 đến 9 có 25 đầu vào. Kết quả không còn đồng đều.

Sai lệch có thể nhỏ ở một chữ số nhưng là một lỗi có thể tránh được. Không suy ra “đã dùng CSPRNG” nghĩa là mọi phép chuyển đổi sau đó đều đúng.

### 6.2. Dùng API có giới hạn hoặc cơ chế được xác định

Với mã số trong Java, dùng API có bound như ví dụ ở trên. Với alphabet hoặc định dạng khác, dùng thư viện hoặc phương pháp lấy mẫu có hợp đồng rõ thay vì tự modulo một giá trị bất kỳ.

Nếu cần rejection sampling, ngưỡng chấp nhận và vòng lặp phải được thiết kế đúng, có nguồn sinh phù hợp và giới hạn vận hành. Không tự đưa một thuật toán chưa đánh giá vào đường cấp credential chỉ để có định dạng đẹp.

Cách `abs(randomInt) % bound` cũng không phải giải pháp chung. Ngoài vấn đề phân bố, một số phép biến đổi số nguyên còn có trường hợp biên cần xử lý. API có hợp đồng thích hợp giúp tránh những lỗi không cần thiết.

### 6.3. Cắt ngắn và chuẩn hóa có thể giảm không gian

Những thao tác cần đánh giá gồm:

- Chỉ giữ một phần token vì cột dữ liệu hoặc URL quá ngắn.
- Bỏ ký tự không thích rồi không sinh bù theo quy tắc.
- Chuyển hoa thường hoặc thay các ký tự dễ nhầm bằng cùng một ký tự.
- Gắn prefix dài rồi đếm toàn bộ độ dài như phần ngẫu nhiên.
- Đổi số sang chuỗi rồi làm mất số 0 đầu hoặc dấu cần thiết cho profile.

Một định dạng thân thiện với con người có thể hợp lệ nếu không gian và cách lấy mẫu được tính theo định dạng cuối. Không tính độ khó đoán của byte đầu vào rồi bỏ qua việc nhiều đầu vào đã bị ánh xạ về cùng kết quả.

### 6.4. Encoding không phải mã hóa hoặc che giấu

Base64url giúp biểu diễn byte theo một alphabet thuận tiện, nhưng ai có token vẫn có thể dùng nó theo hợp đồng bearer. Không công khai token vì nghĩ nó đã được “mã hóa Base64”.

Định dạng chấp nhận ở bước xác minh cũng cần rõ, có giới hạn độ dài và xử lý đầu vào không hợp lệ. Không để một chuỗi quá lớn tiêu thụ tài nguyên chỉ vì hệ thống đang chờ một token ngẫu nhiên.

## 7. Đoán thử và va chạm là hai mô hình khác nhau

### 7.1. Đoán một bí mật cụ thể

Trong mô hình đơn giản, mục tiêu phân bố đều trên không gian `2^b` và đối thủ có g lần đoán khác nhau, xác suất thành công gần `g / 2^b` khi tỷ lệ này còn nhỏ.

Nếu nhiều token đang hoạt động đều có thể tạo thành công cho cùng một phép đoán, phạm vi tấn công có thể rộng hơn. Với v mục tiêu độc lập và các giả định đơn giản, cần xét cả g và v, không chỉ độ dài một token.

Các phép tính này không chứng minh an toàn nếu bộ sinh bị dự đoán, trạng thái bị lộ hoặc token đã lọt qua log. Chúng chỉ mô tả phần rủi ro đoán mù trong mô hình đã nêu.

### 7.2. Va chạm giữa các giá trị đã phát hành

Với q giá trị độc lập đồng đều trên không gian `2^b`, xác suất có va chạm có xấp xỉ:

```text
P_collision ≈ q × (q − 1) / (2 × 2^b)
```

Xấp xỉ này áp dụng khi xác suất còn nhỏ. Nó cho thấy rủi ro tăng theo số cặp giá trị, không chỉ theo số giá trị.

Không dùng xác suất đoán một token để thay phép tính va chạm của một tập token lớn, hoặc ngược lại. Đặc tả phải chỉ rõ thuộc tính cần giới hạn.

### 7.3. Ràng buộc lưu trữ vẫn cần khi trùng không được phép

Nếu token dùng để tra cứu một bản ghi duy nhất, thiết kế cần ngăn trạng thái mơ hồ khi xảy ra trùng trong phạm vi đó. Có thể dùng ràng buộc duy nhất thích hợp và sinh lại với giới hạn số lần theo policy.

Không ghi đè bản ghi cũ khi token trùng. Không sửa token bằng cách thêm user ID hoặc timestamp rồi coi đó là cách phục hồi mật mã đã được chứng minh.

Với OTP được ràng buộc rõ vào một challenge và tài khoản, cùng chuỗi số ở hai tài khoản không nhất thiết là lỗi. Không ép duy nhất toàn cầu nếu giao thức không cần, nhưng cũng không tra OTP trần trên toàn hệ thống rồi bỏ ràng buộc người dùng.

## 8. Nonce, đồng thời và vòng đời khóa

### 8.1. Phạm vi duy nhất thường theo khóa

Với cơ chế có yêu cầu nonce không lặp theo khóa, phải tính mọi thao tác sử dụng cùng khóa: tất cả instance, worker, vùng triển khai và các lần khôi phục. Một counter riêng ở mỗi instance có thể trùng nếu chúng bắt đầu từ cùng giá trị.

Nếu dùng nonce ngẫu nhiên, cần áp dụng giới hạn sử dụng và độ dài của cơ chế cụ thể, đánh giá xác suất trùng và vòng đời khóa. Không coi một nonce ngẫu nhiên ngắn là bảo đảm duy nhất tuyệt đối.

### 8.2. Restart và phục hồi có thể làm lặp trạng thái

Một counter có thể quay lại sau restore. Một trạng thái bộ sinh bị sao chép có thể tạo các chuỗi liên quan hoặc trùng nếu môi trường không có cơ chế xử lý phù hợp. Một khóa được khôi phục cùng dữ liệu nhưng không cùng trạng thái nonce cũng có thể phá giả định ban đầu.

Yêu cầu cần mô tả cơ chế phân vùng không gian, lưu trạng thái, đổi khóa hoặc giải pháp phù hợp với thư viện và giao thức. Không tự thêm thời gian hiện tại rồi tuyên bố đã giải quyết mọi trường hợp khởi động lại.

### 8.3. Không áp dụng một mẫu cho mọi mode

Một mode yêu cầu IV không dự đoán được không được thay bằng bộ đếm chỉ vì bộ đếm duy nhất. Ngược lại, một mode cho phép nonce xác định có kiểm soát không bắt buộc phải dùng random nếu thiết kế duy nhất đã được bảo đảm.

Câu hỏi đúng là “tham số này phải thỏa điều kiện nào theo cơ chế?”, không phải “có thể sinh nó bằng hàm random nào cho nhanh?”.

## 9. Vòng đời token và OTP

### 9.1. Nguồn sinh tốt chỉ là một phần của giao thức

Token khôi phục cần được gắn với tài khoản và mục đích, có thời hạn, dùng một lần và được bảo vệ khỏi lộ lọt. OWASP nêu các thuộc tính này cùng yêu cầu dùng nguồn sinh an toàn. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Một token khó đoán nhưng không hết hạn hoặc có thể dùng để thực hiện một mục đích khác vẫn có thể không đáp ứng thiết kế bảo mật.

### 9.2. Dùng một lần cần tính nguyên tử

Hai request có thể cùng xác minh một token chưa dùng. Nếu việc kiểm tra và đánh dấu đã dùng không phối hợp đúng, cả hai có thể tạo tác dụng phụ.

Yêu cầu nên nêu việc tiêu thụ token và hành động cần bảo vệ được kết hợp bằng transaction hoặc cơ chế nhất quán phù hợp. Randomness không tự giải quyết cạnh tranh ở bước xác minh.

### 9.3. Lưu giá trị xác minh phù hợp độ mạnh của bí mật

Với token entropy cao, có thể thiết kế lưu giá trị dẫn xuất phục vụ đối chiếu thay cho token nguyên văn, theo mô hình đe dọa và vòng đời đã chọn. Quyền đọc dữ liệu và log vẫn cần được giới hạn.

Với OTP ngắn, một hash không khóa không làm biến mất không gian nhỏ có thể dò offline nếu kho dữ liệu bị lộ. Nếu mô hình cần bảo vệ tình huống đó, phải có cơ chế như xác minh bằng bí mật server được quản lý hoặc thiết kế khác phù hợp, không chỉ thêm một hash nhanh.

Đây là yêu cầu về giao thức lưu và xác minh, không phải lý do tự phát minh cách băm hoặc MAC mới. Dùng thư viện và primitive được chấp thuận theo profile.

### 9.4. Giới hạn cấp phát và thử xác minh

Rate limit chỉ ở bước xác minh có thể chưa đủ nếu kẻ gọi liên tục yêu cầu mã mới và đặt lại bộ đếm. Cần xét tổng số lần thử, số challenge đang hoạt động, thời hạn và phạm vi danh tính hoặc tenant.

Hành vi gửi lại mã và thay thế challenge cũ phải được công bố. Không để người dùng không biết mã nào còn hiệu lực, hoặc để nhiều đường xác minh dùng các bộ đếm độc lập ngoài chủ đích.

## 10. Trạng thái hệ thống và hành vi khi lỗi

### 10.1. Khởi tạo và khả năng sẵn sàng

Nguồn sinh bảo mật có thể cần khởi tạo hoặc lấy entropy theo nền tảng. Hệ thống phải có thời gian chờ, khả năng quan sát và hành vi lỗi phù hợp với profile vận hành.

Nếu không thể cấp giá trị đáp ứng yêu cầu, thao tác cấp credential phải thất bại an toàn hoặc được trì hoãn theo hợp đồng. Không fallback sang timestamp, `Random`, giá trị cố định hoặc một token dùng chung.

Lỗi nguồn sinh cũng không được để lại hành động nghiệp vụ nửa chừng, chẳng hạn đổi trạng thái tài khoản nhưng không có cách hoàn tất luồng khôi phục đúng thiết kế.

### 10.2. Snapshot, clone và restore

Nếu môi trường có thể sao chép trạng thái DRBG đã khởi tạo, cần đánh giá các instance sau phục hồi có tiếp tục cùng trạng thái hay không và cơ chế nền tảng xử lý tình huống đó.

Không mặc định mọi container đều sao chép cùng trạng thái bộ sinh; cũng không mặc định mọi cơ chế snapshot đều tự khôi phục an toàn. Yêu cầu phải dựa trên cách triển khai thật, bao gồm checkpoint, restore, fork nếu có và nguồn entropy của runtime.

Cơ chế reseed hoặc khởi tạo lại phải sử dụng nguồn và API thích hợp theo profile. PID, thời gian hoặc một chuỗi ngẫu nhiên tự tạo bằng bộ sinh yếu không phải giải pháp thay thế.

### 10.3. Môi trường test không được điều khiển production bằng seed cố định

Deterministic stub có thể hữu ích để kiểm tra luồng nghiệp vụ hoặc tạo tình huống trùng có chủ đích. Nó phải được cô lập và không trở thành cấu hình có thể vô tình bật trong môi trường cấp bí mật thật.

Không serialize trạng thái nguồn sinh vào image để mọi instance khởi động nhanh từ cùng vị trí chỉ nhằm đạt hiệu năng. Nếu hạ tầng sử dụng một hình thức phục hồi trạng thái, phải có thiết kế chứng minh điều kiện an toàn tương ứng.

### 10.4. Bảo vệ đầu ra và trạng thái

Một nguồn sinh tốt không bù được việc lộ token hoặc trạng thái. Cần hạn chế log, dump, telemetry, quyền debug và các kênh sao chép dữ liệu nhạy cảm theo mô hình hệ thống.

Không hứa rằng gán một biến về null sẽ xóa mọi bản sao khỏi bộ nhớ. Với khóa hoặc bí mật có yêu cầu đặc biệt, cần dùng cơ chế quản lý và bảo vệ phù hợp thay vì suy ra từ thao tác quản lý đối tượng thông thường.

## 11. Chuyển thành yêu cầu bảo mật có thể kiểm chứng

### 11.1. Từ câu chung sang hợp đồng giá trị

Yêu cầu yếu:

> Token phải random và đủ dài.

Yêu cầu này không cho biết token có vai trò gì, nguồn sinh nào, độ dài tính theo byte hay ký tự, cần bao nhiêu độ khó đoán hoặc xử lý ra sao khi nguồn sinh lỗi.

Yêu cầu rõ hơn:

> Token khôi phục được sinh từ nguồn CSPRNG đáp ứng profile đã chọn, dùng 32 byte mới cho mỗi lần cấp theo giao thức, biểu diễn bằng Base64url không padding và không bị cắt ngắn. Token được gắn tài khoản, tenant nếu có và mục đích; có thời hạn, dùng một lần và không được ghi nguyên văn vào log. Lỗi nguồn sinh không được dẫn tới cấp giá trị từ nguồn yếu hơn.

Câu này vẫn cần profile provider, thời hạn và giới hạn cấp phát hoặc xác minh cụ thể của sản phẩm. Những tham số đó phải được lựa chọn, không để thành tên trống trong cấu hình.

### 11.2. Bộ yêu cầu minh họa

| Mã | Yêu cầu | Bằng chứng dự kiến |
| --- | --- | --- |
| RNG-01 | Mỗi giá trị liên quan bảo mật phải có mục đích và thuộc tính khó đoán, duy nhất hoặc phân bố được xác định | Danh mục giá trị và hợp đồng sử dụng |
| RNG-02 | Bí mật phải dùng CSPRNG hoặc cơ chế sinh khóa được chấp thuận; không dùng bộ sinh thông thường | Ánh xạ API, provider và cấu hình runtime |
| RNG-03 | Không dùng seed cố định hoặc dữ liệu dự đoán được thay nguồn entropy được quản lý | Rà soát đường khởi tạo và cấu hình môi trường |
| RNG-04 | Độ dài đầu ra và mức an toàn mục tiêu phải phân biệt rõ; định dạng cuối không giảm ngoài policy | Profile, phép tính không gian và ca định dạng |
| RNG-05 | Chuyển đổi sang số hoặc alphabet phải tránh bias ngoài hợp đồng | Cơ chế lấy mẫu và kiểm thử biên phù hợp |
| RNG-06 | Token phải được ràng buộc với phạm vi, thời hạn và chính sách dùng một lần | Ca sai tài khoản, sai mục đích, hết hạn và dùng lại |
| RNG-07 | OTP ngắn phải có giới hạn thử và cấp phát nhất quán qua instance | Ca thử lại, gửi lại mã và cạnh tranh |
| RNG-08 | Nonce hoặc IV phải đáp ứng điều kiện cơ chế trong toàn phạm vi khóa và vòng đời | Thiết kế đa instance, restart và restore |
| RNG-09 | Lỗi nguồn sinh không được cấp bí mật dự đoán được hoặc nới profile | Ca khởi tạo lỗi và lỗi cấp phát |
| RNG-10 | Trùng bị cấm phải được xử lý mà không ghi đè hoặc tạo tra cứu mơ hồ | Ca trùng cưỡng bức bằng nguồn thử nghiệm |
| RNG-11 | Đầu ra bí mật và trạng thái nguồn sinh không được lộ qua log hoặc cấu hình test | Kiểm tra dữ liệu quan sát và quyền truy cập |
| RNG-12 | Thay runtime, provider hoặc cơ chế snapshot phải đánh giá lại bằng chứng liên quan | Hồ sơ thay đổi và kiểm thử môi trường |

Các mã là ví dụ tổ chức yêu cầu. Không coi một yêu cầu về nonce của mode này là quyền áp dụng cùng quy tắc cho mọi mode khác.

### 11.3. Truy vết từ tài sản tới bằng chứng

```text
Tài sản: quyền khôi phục tài khoản
    ↓
Mối đe dọa: đối thủ dự đoán hoặc đoán được reset token
    ↓
Yêu cầu: nguồn CSPRNG, độ dài và giới hạn vòng đời theo profile
    ↓
Thiết kế: nguồn được quản lý, token mới, biểu diễn không cắt ngắn,
lưu giá trị xác minh và tiêu thụ token theo cơ chế nhất quán
    ↓
Bằng chứng: cấu hình nguồn, kiểm tra định dạng và các ca âm tính
cho token sai, sai mục đích, hết hạn, dùng lại và lỗi nguồn sinh
```

Một rủi ro nonce lặp theo khóa cần chuỗi truy vết riêng tới dữ liệu đã mã hóa và vòng đời khóa. Không lấy bằng chứng token khó đoán để bao phủ mặc định rủi ro đó.

## 12. Tiêu chí nghiệm thu

Phần này mô tả bằng chứng cần có khi triển khai, không tuyên bố một hệ thống đã được kiểm thử chỉ vì bài có danh sách ca thử.

### 12.1. Bằng chứng nguồn và tích hợp

Cần xác nhận đường tạo bí mật thực sự gọi cơ chế đã chọn, không có nhánh khác dùng bộ sinh yếu hoặc seed thử nghiệm. Ghi nhận runtime, provider, cấu hình và môi trường có ảnh hưởng.

Nếu tổ chức cần bằng chứng xác nhận hoặc chứng nhận của một module mật mã, phải kiểm tra đúng module, chế độ và phạm vi áp dụng. Tên `SecureRandom` trong mã nguồn không tự chứng minh mọi yêu cầu tuân thủ.

### 12.2. Ma trận trường hợp

| Trường hợp | Thiết lập | Kết quả cần chứng minh |
| --- | --- | --- |
| Token hợp lệ | Đường cấp token thật theo profile | Đúng số byte, định dạng cuối và phạm vi sử dụng |
| Chuỗi bị cắt | Ràng buộc cột hoặc đường truyền ngắn hơn | Không âm thầm cắt mất phần ngẫu nhiên |
| OTP có số 0 đầu | Dùng nguồn thử để tạo giá trị biên | Định dạng và xác minh giữ đủ chữ số |
| Chuyển đổi số | Các giá trị biên của cơ chế lấy mẫu | Không có modulo bias hoặc lỗi số nguyên do tự chuyển đổi |
| Nguồn sinh lỗi | Tiêm lỗi vào ranh giới nguồn trong môi trường thử | Không fallback sang nguồn yếu hoặc cấp token cố định |
| Trùng token | Nguồn thử trả cùng giá trị có chủ đích | Không ghi đè bản ghi, xử lý theo giới hạn đã chọn |
| Sai phạm vi | Token của tài khoản hoặc mục đích khác | Không được sử dụng ngoài hợp đồng |
| Hết hạn hoặc đã dùng | Token từng hợp lệ | Bị từ chối theo trạng thái hiện tại |
| Xác minh đồng thời | Hai request tiêu thụ cùng token | Chỉ hiệu ứng được hợp đồng cho phép xảy ra |
| OTP bị đoán nhiều lần | Nhiều request hoặc nhiều instance | Giới hạn tổng được thực thi nhất quán |
| Restart hoặc restore | Cách triển khai có trạng thái liên quan | Không phá điều kiện nguồn hoặc nonce của profile |
| Log và telemetry | Luồng thành công và lỗi | Không có bí mật nguyên văn ngoài chính sách |
| Cấu hình test | Đổi profile hoặc dependency injection | Nguồn tất định thử nghiệm không được dùng để cấp bí mật thật |

Ca định dạng của ví dụ token có thể kiểm tra Base64url hợp lệ, không padding và giải mã được thành 32 byte. Không cần so với một token thật cố định rồi bắt nguồn bảo mật sinh lại đúng chuỗi đó.

### 12.3. Kiểm tra thống kê có vai trò giới hạn

Có thể dùng các kiểm tra phù hợp để phát hiện lỗi rõ ràng như toàn số 0, độ dài sai, đầu ra cố định hoặc thiên lệch do phép chuyển đổi. Chúng là tín hiệu kỹ thuật, không chứng minh bộ sinh có thuộc tính mật mã trước mọi đối thủ.

Một triệu đầu ra không trùng chưa chứng minh nguồn không thể dự đoán. Một tập đầu ra có tỷ lệ ký tự đẹp chưa chứng minh seed có đủ entropy. Đánh giá nguồn, thiết kế và triển khai vẫn là bằng chứng khác.

Không dùng một kiểm tra mẫu tùy tiện trong ứng dụng thay cho health testing của nguồn theo profile. Nếu môi trường có yêu cầu đánh giá entropy chuyên biệt, phải thực hiện theo quy trình và chuyên môn tương ứng.

### 12.4. Kiểm thử có tính tất định mà không làm yếu production

Có thể đưa một stub chỉ trong test để điều khiển tình huống OTP bằng 0, nguồn lỗi hoặc va chạm. Stub giúp kiểm tra xử lý nghiệp vụ; nó không chứng minh nguồn CSPRNG thật an toàn.

Cần tách hai loại bằng chứng: test logic tích hợp với nguồn điều khiển được, và bằng chứng cấu hình hoặc hành vi của nguồn thật trong môi trường mục tiêu. Không trộn chúng bằng cách seed cố định nguồn production.

### 12.5. Những bằng chứng chưa đủ

- Chuỗi dài chưa chứng minh nhiều entropy hoặc security strength tương ứng.
- Dùng hash chưa chứng minh đầu vào khó đoán.
- Không trùng trong một lần chạy chưa chứng minh duy nhất suốt vòng đời khóa.
- Có class `SecureRandom` chưa chứng minh mọi đường cấp bí mật đều dùng đúng.
- Một instance chạy đúng chưa chứng minh snapshot và multi-instance giữ điều kiện nguồn.
- Sinh OTP bằng CSPRNG chưa chứng minh giới hạn đoán thử đã đủ.
- Token dùng một lần trong test tuần tự chưa chứng minh an toàn khi tiêu thụ đồng thời.

## 13. Vận hành và ứng phó khi nguồn bị ảnh hưởng

### 13.1. Quản lý thay đổi theo môi trường thật

Thay JDK, provider, hệ điều hành, image hoặc cơ chế restore có thể ảnh hưởng tới nguồn sinh và vòng đời trạng thái. Cần có owner đánh giá và cập nhật bằng chứng liên quan trước khi mở rộng triển khai.

Không giữ một thuật toán hoặc provider cũ chỉ vì muốn token có hình thức giống trước; định dạng token và nguồn sinh là hai lớp có thể có hợp đồng riêng.

### 13.2. Quan sát mà không thu thập bí mật

Có thể ghi metric lỗi khởi tạo, thời gian cấp giá trị, lỗi nguồn và tình huống trùng được phát hiện theo chính sách. Không log token, OTP, seed hoặc trạng thái DRBG để tìm lỗi.

Một dấu hiệu trùng bất thường cần điều tra cả nguồn, phép chuyển đổi, ràng buộc lưu trữ và tình huống cố tình lặp trong test. Không lập tức kết luận đó chỉ là xác suất rồi bỏ qua.

### 13.3. Xác định phạm vi ảnh hưởng

Nếu nguồn có thể dự đoán hoặc trạng thái bị lộ, cần xác định giá trị nào đã được cấp, giai đoạn nào và những quyền còn hiệu lực. Tùy loại giá trị, có thể cần thu hồi token, cấp lại khóa hoặc xử lý dữ liệu đã được bảo vệ bằng tham số không đúng.

Chỉ sửa hàm sinh không làm các token đã phát hành trở nên khó đoán hơn. Với khóa và nonce đã dùng sai, còn cần đánh giá hậu quả đối với dữ liệu và tính toàn vẹn theo cơ chế cụ thể.

### 13.4. Phục hồi không tái sử dụng nguồn yếu

Quy trình khôi phục phải đưa hệ thống về nguồn và profile được chấp thuận, xử lý trạng thái clone nếu có và kiểm tra các đường cấp bí mật trước khi tiếp tục.

Không sửa bằng cách nối thêm một timestamp vào token cũ hoặc hash lại toàn bộ giá trị đã bị dự đoán. Những thao tác đó không thay thế việc tạo bí mật mới đúng nguồn và thu hồi quyền gắn với bí mật cũ.

## 14. Mẫu đặc tả token khôi phục

```text
ID: SEC-CRYPTO-ACCOUNT-RECOVERY-RANDOMNESS

Tài sản:
Quyền khôi phục tài khoản theo token bearer được hệ thống phát hành.

Nguồn sinh:
CSPRNG đáp ứng profile đã chọn trên runtime và môi trường triển khai.
Không dùng Random, seed cố định, timestamp hoặc dữ liệu tài khoản
để thay nguồn entropy được quản lý.

Định dạng:
Sinh 32 byte mới cho mỗi lần cấp theo giao thức, biểu diễn Base64url
không padding. Không cắt ngắn hoặc chuẩn hóa làm giảm ngoài policy.
Mức an toàn mục tiêu phải được profile nguồn xác định, không chỉ suy
ra từ số byte đầu ra.

Phạm vi và vòng đời:
Gắn với tài khoản, tenant nếu có, mục đích và thời hạn đã công bố.
Tiêu thụ token và hành động liên quan theo cơ chế nhất quán để đáp ứng
yêu cầu dùng một lần, kể cả khi có request đồng thời.

Lưu và truyền:
Lưu giá trị xác minh theo mô hình đã chọn; hạn chế quyền và thời hạn.
Không log token hoặc seed. Truyền qua kênh và luồng khôi phục được bảo vệ.

Hành vi lỗi:
Không cấp bí mật từ nguồn yếu hơn khi CSPRNG hoặc cấu hình lỗi.
Trùng bị cấm không được ghi đè bản ghi hoặc tạo kết quả tra cứu mơ hồ.

Bằng chứng:
Ánh xạ nguồn và profile; kiểm tra byte, định dạng, ràng buộc phạm vi,
hết hạn, dùng lại, cạnh tranh, lỗi nguồn, log và môi trường restore.
Kiểm tra thống kê chỉ là tín hiệu bổ sung, không thay bằng chứng mật mã.

Chủ sở hữu:
Nhóm nền tảng quản lý nguồn và môi trường; nhóm danh tính quản lý giao
thức token; nhóm dữ liệu quản lý trạng thái tiêu thụ; vận hành quản lý
quan sát, thay đổi và thu hồi khi có sự cố.
```

Randomness an toàn là một chuỗi bảo đảm từ nguồn, trạng thái và phép lấy mẫu tới giao thức sử dụng. Yêu cầu bảo mật có thể kiểm chứng khi mỗi giá trị được gắn với thuộc tính cần có và vòng đời rõ ràng, thay vì chỉ được mô tả là một chuỗi “random” trông đủ dài.
