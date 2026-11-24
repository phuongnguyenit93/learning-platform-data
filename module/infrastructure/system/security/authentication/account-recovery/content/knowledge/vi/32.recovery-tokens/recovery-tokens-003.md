# Recovery token entropy — Độ khó đoán của token khôi phục tài khoản

Recovery token thường là một bí mật cho phép tiếp tục luồng đặt lại mật khẩu, khôi phục MFA hoặc đăng ký lại phương tiện xác thực. Nếu người khác có thể đoán được token còn hiệu lực, họ có thể vượt qua bước đáng lẽ chỉ chủ tài khoản hoặc người được phép mới hoàn thành được.

**Entropy của recovery token** liên quan đến mức bất định mà kẻ tấn công phải đối mặt khi đoán bí mật đó. Một chuỗi nhìn dài và lộn xộn chưa đủ: nguồn sinh, phân bố giá trị, cách mã hóa và phần thực sự được server kiểm tra đều ảnh hưởng đến độ khó đoán.

## 1. Xác định bí mật nào đang bảo vệ thao tác

Trước khi tính số bit, cần phân biệt các thành phần trong một yêu cầu recovery:

| Thành phần | Vai trò | Có được tính là bí mật khó đoán không? |
| --- | --- | --- |
| ID tài khoản | Xác định tài khoản liên quan | Không mặc định; thường có thể biết hoặc suy ra |
| `attemptId` | Định danh hồ sơ recovery | Chỉ tính nếu thiết kế thực sự coi nó là bí mật và bảo vệ tương ứng |
| Token ngẫu nhiên | Chứng minh người gửi có bí mật được cấp | Có, nếu được sinh và kiểm tra đúng |
| Thời gian hết hạn | Giới hạn thời gian sử dụng | Không tạo thêm entropy nếu giá trị có thể biết |
| Tiền tố loại token | Phân biệt mục đích hoặc phiên bản | Không, nếu là chuỗi cố định hoặc công khai |
| Mã kiểm tra lỗi nhập | Giảm lỗi khi người dùng gõ | Không phải các bit ngẫu nhiên độc lập |

Ví dụ, cấu trúc `recovery_v1_<accountId>_<secret>` chỉ có phần `secret` đóng góp vào độ khó đoán nếu các phần còn lại đã biết. Không cộng độ dài toàn bộ URL, tên miền hoặc định danh công khai vào entropy của bí mật.

Một token có entropy cao vẫn cần gắn với đúng tài khoản, hồ sơ và mục đích. Token cho phép đặt lại mật khẩu không được tự trở thành quyền gỡ MFA hoặc thêm passkey nếu chính sách chưa cho phép thao tác đó.

## 2. Từ không gian giá trị đến số bit entropy

Nếu token được chọn **đồng đều** từ một tập gồm `N` giá trị, entropy lý tưởng là:

```text
H = log2(N) bit
```

Nếu mỗi vị trí được chọn độc lập, đồng đều từ một bảng chữ cái có `A` ký tự và token dài `L` ký tự:

```text
N = A^L
H = L × log2(A)
```

Điều kiện đồng đều và độc lập rất quan trọng. Không thể dùng công thức này chỉ vì biểu mẫu cho phép nhập nhiều loại ký tự.

| Cách sinh lý tưởng | Không gian | Entropy xấp xỉ |
| --- | --- | --- |
| Mã gồm 6 chữ số, giữ cả số 0 đầu | `10^6` | 19,93 bit |
| Mã gồm 8 chữ số, giữ cả số 0 đầu | `10^8` | 26,58 bit |
| 16 byte ngẫu nhiên | `2^128` | 128 bit |
| 24 byte ngẫu nhiên | `2^192` | 192 bit |
| 32 byte ngẫu nhiên | `2^256` | 256 bit |

Các hàng byte mô tả không gian đầu ra lý tưởng. Độ khó dự đoán thực tế còn phụ thuộc chất lượng bộ sinh, nguồn khởi tạo và khả năng giữ bí mật trạng thái của bộ sinh.

### 2.1. Khi phân bố không đồng đều

Nếu một số token xuất hiện thường xuyên hơn, kẻ tấn công có thể ưu tiên chúng. Một cách diễn đạt hữu ích là min-entropy:

```text
H_min = -log2(p_max)

p_max = xác suất của giá trị có khả năng xuất hiện cao nhất
```

Ví dụ, token cho phép một triệu giá trị nhưng phần mềm trả về cùng một giá trị mặc định trong nhiều trường hợp lỗi sẽ không có mức khó đoán tương ứng một triệu lựa chọn đồng đều.

Các đánh giá phải xét thông tin kẻ tấn công có thể biết, như thời gian phát hành, định danh tài khoản hoặc đầu ra trước đó của bộ sinh yếu. Entropy nhìn từ bên ngoài thiết kế không đồng nghĩa với mức bất định còn lại sau khi các thông tin ấy bị lộ.

## 3. Định lượng nguy cơ đoán trúng

Giả sử một bí mật được chọn đồng đều từ `N = 2^b` giá trị, chưa bị lộ, server chỉ chấp nhận đúng một giá trị và kẻ tấn công thử `q` giá trị khác nhau. Xác suất đoán trúng là:

```text
P_success = min(q / 2^b, 1)
```

Mô hình này đánh giá tấn công đoán bí mật. Nó không bao gồm phishing, rò rỉ log, chiếm email hoặc lỗi cấp quyền.

Với cùng ngân sách giả định `q = 10^9` lần thử:

| Số bit ngẫu nhiên lý tưởng | Xác suất đoán trúng một token |
| --- | --- |
| 64 bit | Khoảng `5,42 × 10^-11` |
| 96 bit | Khoảng `1,26 × 10^-20` |
| 128 bit | Khoảng `2,94 × 10^-30` |
| 256 bit | Khoảng `8,64 × 10^-69` |

Một tỷ lần thử ở đây chỉ là ngân sách toán học để so sánh, không phải hạn mức một API recovery nên cho phép.

Với mã sáu chữ số đồng đều, nếu chỉ có một mã đúng và cho phép 10 lần đoán khác nhau trong toàn phạm vi đang xét:

```text
P_success = 10 / 1.000.000 = 0,00001
```

Nếu người gửi được tạo lại hồ sơ vô hạn và mỗi lần lại có 10 cơ hội, tổng số lần thử không còn là 10. Do đó, đánh giá mã ngắn cần tính cả việc phát lại mã, tạo hồ sơ mới, nhiều nguồn truy cập và nhiều token còn hiệu lực.

### 3.1. Chọn số bit theo mô hình rủi ro

Với một mục tiêu xác suất tối đa `epsilon` trong mô hình một token, điều kiện toán học là:

```text
b >= ceil(log2(q / epsilon))
```

Đây là công cụ phân tích, không phải một chuẩn tối thiểu áp dụng cho mọi phương pháp recovery. Các yêu cầu tiêu chuẩn, tuổi thọ bí mật, tấn công offline và các đường lạm dụng khác vẫn phải được xem xét.

Đối với token đường dẫn không yêu cầu người dùng nhớ hoặc gõ, việc dùng một bí mật ngẫu nhiên dài thường có chi phí trải nghiệm thấp. Ví dụ Java trong bài chọn 32 byte làm tham số thiết kế minh họa; không khẳng định mọi tiêu chuẩn bắt buộc đúng độ dài này.

### 3.2. Nhiều token còn hiệu lực

Nếu một endpoint chấp nhận bất kỳ token nào trong `m` token đang hoạt động, không gian mục tiêu lớn hơn. Với các token độc lập, đồng đều và `q × m` nhỏ hơn nhiều so với `2^b`, có thể dùng xấp xỉ:

```text
P_success ≈ q × m / 2^b
```

Một cận trên đơn giản là `min(q × m / 2^b, 1)`. Khi server đã giới hạn vào một tài khoản hoặc hồ sơ, chỉ các token đủ điều kiện trong phạm vi ấy mới được tính vào `m`; không cộng toàn bộ token của dịch vụ một cách máy móc.

Giới hạn số token còn hiệu lực giúp giảm bề mặt, nhưng chính sách phát lại cũng phải tránh để người ngoài liên tục hủy token của chủ tài khoản. Không nên giải quyết vấn đề nhiều token bằng một cơ chế gây từ chối dịch vụ cho người dùng thật.

## 4. Encoding thay đổi cách biểu diễn, không tạo thêm bí mật

Một dãy byte có thể được biểu diễn bằng hex hoặc Base64url mà không đổi không gian giá trị gốc, nếu phép mã hóa giữ nguyên thông tin.

| Dữ liệu ngẫu nhiên gốc | Số bit lý tưởng | Số ký tự hex | Số ký tự Base64url không padding |
| --- | --- | --- | --- |
| 16 byte | 128 | 32 | 22 |
| 24 byte | 192 | 48 | 32 |
| 32 byte | 256 | 64 | 43 |

Với 32 byte, Base64url không padding tạo 43 ký tự. Không được tính `43 × 6 = 258` bit: dữ liệu gốc chỉ có 256 bit, nên ký tự cuối không có đủ 64 khả năng độc lập.

Những phép biến đổi sau không tăng entropy:

- Chuyển một mã ngắn sang Base64 hoặc QR.
- Hash mã sáu chữ số thành một chuỗi hex dài.
- Thêm tiền tố cố định, dấu gạch ngang hoặc thời gian phát hành.
- Lặp lại một đoạn ngẫu nhiên nhiều lần.
- Chuyển một bí mật thành URL có nhiều tham số công khai.

Nếu server chỉ so sánh một phần token, độ khó đoán phụ thuộc phần đó. Chẳng hạn, chỉ kiểm tra 6 ký tự hex đầu của một token ngẫu nhiên tương đương kiểm tra tối đa 24 bit, dù token đầy đủ được sinh từ 32 byte.

Base64url phân biệt chữ hoa và chữ thường. Tự chuyển token sang chữ thường, cắt khoảng trắng tùy ý ở giữa hoặc so khớp gần đúng có thể làm thay đổi tập giá trị được chấp nhận. Quy tắc nhập cần rõ ràng và không được làm giảm bí mật ngoài thiết kế.

## 5. Sinh token bằng nguồn ngẫu nhiên mật mã

Recovery token cần một bộ sinh ngẫu nhiên dành cho mục đích mật mã — CSPRNG. Bộ sinh có đầu ra trông khó đoán bằng mắt hoặc ít bị trùng trong một lần chạy chưa đủ.

Không nên tạo bí mật recovery chỉ từ:

- Thời gian hiện tại.
- ID tài khoản, số thứ tự bản ghi hoặc email.
- Hàm hash của các dữ liệu công khai đó.
- Bộ sinh phục vụ mô phỏng như `java.util.Random` hoặc `Math.random()`.
- Seed cố định được dùng lại giữa các tiến trình.

Hash của `email + timestamp` vẫn có thể bị tính lại nếu kẻ tấn công biết email và khoảng thời gian. Hash che hình thức của đầu vào; nó không tự tạo một nguồn bí mật mới.

### 5.1. Ví dụ Java

`SecureRandom` là API Java dành cho nguồn số ngẫu nhiên mạnh về mật mã. Khi không được seed thủ công, triển khai có thể tự lấy nguồn khởi tạo khi cần; không nên thay cơ chế đó bằng seed dễ đoán. [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)

```java
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Locale;

public final class RecoveryTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL_ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private RecoveryTokenGenerator() {
    }

    public static String newOpaqueToken() {
        byte[] secret = new byte[32];
        RANDOM.nextBytes(secret);
        return URL_ENCODER.encodeToString(secret);
    }

    public static String newSixDigitCode() {
        int value = RANDOM.nextInt(1_000_000);
        return String.format(Locale.ROOT, "%06d", value);
    }
}
```

Hai method phục vụ hai thiết kế khác nhau:

- `newOpaqueToken()` tạo đầu ra 32 byte rồi mã hóa thành chuỗi Base64url dài 43 ký tự.
- `newSixDigitCode()` tạo mã từ `000000` đến `999999`; số 0 đầu được giữ bằng định dạng chuỗi.

Mã sáu chữ số trong ví dụ có khoảng 19,93 bit, không có mức khó đoán bằng token 32 byte chỉ vì cả hai đều dùng `SecureRandom`. Method sinh mã ngắn chỉ là một thành phần; chưa có hạn mức, thời hạn, liên kết hồ sơ, lưu trữ hay tiêu thụ một lần.

Độ khó dự đoán thực tế của đầu ra phụ thuộc provider, nguồn khởi tạo và trạng thái môi trường. Việc gọi API này không tự chứng nhận toàn bộ ứng dụng đáp ứng một chuẩn mật mã cụ thể.

### 5.2. Tránh modulo bias

Giả sử cần sinh từng ký tự trong bảng chữ cái 62 ký tự và lấy một byte ngẫu nhiên rồi tính `byteValue % 62`.

```text
256 = 62 × 4 + 8
```

Tám giá trị đầu có 5 cách xuất hiện từ byte, còn các giá trị khác chỉ có 4 cách. Phân bố ký tự bị lệch, nên không còn cơ sở để tính mỗi ký tự có đúng `log2(62)` bit như mô hình đồng đều.

Có thể dùng API chọn số nguyên có cận như `SecureRandom.nextInt(62)` hoặc thuật toán rejection sampling đúng. Với token byte, dùng `nextBytes` rồi Base64url giúp tránh tự thiết kế bảng chữ cái và phép ánh xạ không cần thiết.

### 5.3. Khởi tạo và trạng thái bộ sinh

CSPRNG mở rộng trạng thái đã được khởi tạo thành chuỗi đầu ra khó dự đoán về mặt tính toán. Nó không tạo nguồn bất định vật lý vô hạn từ một seed công khai.

Nếu một bộ sinh tùy biến chỉ có một seed thuộc `2^16` khả năng, xuất ra token dài 256 bit không làm mất khả năng duyệt toàn bộ các seed ấy. Đây là lý do không tự seed bằng đồng hồ hoặc cấu hình cố định.

Khi vận hành, cũng cần tránh sao chép trạng thái bộ sinh tùy biến giữa các worker hoặc phục hồi trạng thái cũ theo cách làm lặp chuỗi token. Nếu nguồn ngẫu nhiên cần thiết không khả dụng, không fallback sang timestamp hay bộ đếm để tiếp tục cấp bí mật.

## 6. Phân biệt token đường dẫn và mã nhập tay

Không nên áp dụng cùng một phép chọn độ dài cho mọi loại recovery secret.

| Loại bí mật | Cách sử dụng | Hệ quả thiết kế |
| --- | --- | --- |
| Opaque token trong đường dẫn | Người dùng mở link, ít phải gõ thủ công | Có thể dùng nhiều byte ngẫu nhiên mà vẫn thuận tiện |
| Mã nhập tay được gửi qua kênh đã thiết lập | Người dùng chép mã từ một kênh sang giao diện | Cần đánh đổi độ dài với khả năng nhập và hạn mức thử rất chặt |
| Mã recovery lưu trước | Người dùng giữ bí mật để dùng khi mất phương tiện | Tuổi thọ có thể dài, cần nguồn ngẫu nhiên và lưu giữ phù hợp |
| Token có chữ ký | Server kiểm tra tính hợp lệ mật mã của thông điệp | Chống giả phụ thuộc thuật toán và khóa, không phải độ dài payload |

NIST SP 800-63B-4 yêu cầu saved recovery code có ít nhất 64 bit từ bộ sinh được chấp nhận; issued recovery code có ít nhất sáu chữ số thập phân hoặc tương đương từ nguồn ngẫu nhiên phù hợp, cùng các điều kiện giao thức riêng. Không lấy mức của mã gửi qua kênh để thay thế yêu cầu cho mọi bearer token. [NIST SP 800-63B-4, Account Recovery Methods](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery-methods)

Một mã ngắn chỉ khó bị đoán online khi tổng số lần thử thực sự bị giới hạn trong phạm vi liên quan. Giới hạn theo IP đơn lẻ không đủ trước nguồn phân tán; chỉ đặt lại bộ đếm theo `attemptId` cũng không đủ nếu người gửi tạo hồ sơ mới được liên tục.

Thời gian hết hạn làm giảm cửa sổ thử, không thay đổi số bit của mã. Hệ thống không thể lấy lý do mã sống ngắn để bỏ hạn mức hoặc dùng nguồn sinh dự đoán được.

## 7. Tấn công online khác tấn công offline

### 7.1. Đoán qua endpoint

Khi mỗi lần thử phải đi qua server, dịch vụ có thể giới hạn tần suất, số lần sai, số hồ sơ và số token còn hoạt động. Cần xem tổng ngân sách mà kẻ tấn công thực sự có, không chỉ tốc độ của một kết nối.

Thông báo lỗi không nên biến endpoint thành công cụ dò tài khoản hay từng phần token. Việc biết mã sai không được tiết lộ “ba ký tự đầu đúng” hoặc làm khác biệt rõ theo độ dài tiền tố khớp.

Không dùng token làm cơ chế cấp quyền duy nhất cho mọi thao tác nhạy cảm nếu chính sách recovery yêu cầu thêm bằng chứng. Entropy giải quyết một phần khả năng đoán, không định nghĩa đầy đủ quyền mà token được phép mang.

### 7.2. Khi dữ liệu kiểm tra bị lấy cắp

Nếu kẻ tấn công có hash của mã sáu chữ số và có thể kiểm tra offline, họ chỉ cần xét một triệu đầu vào. Một output SHA-256 dài không biến không gian một triệu giá trị thành `2^256` giá trị.

Salt công khai giúp tránh dùng chung bảng tính trước nhưng không tăng số khả năng của từng mã. Hàm dẫn xuất tốn chi phí có thể làm mỗi lần thử đắt hơn; nó vẫn không biến mã ngắn thành bí mật ngẫu nhiên dài.

Với opaque token có đủ ngẫu nhiên, có thể thiết kế lưu digest hoặc HMAC thay vì token nguyên văn. Khóa HMAC cần được giữ tách biệt theo mô hình đe dọa; nếu cả khóa và dữ liệu đều bị lấy, không nên tiếp tục giả định lợi ích bảo vệ trước đó còn nguyên.

Lựa chọn lưu trữ phải theo loại bí mật và yêu cầu áp dụng. Không mặc định một cách lưu token ngẫu nhiên cũng phù hợp cho mật khẩu do người dùng chọn hoặc cho mọi mã recovery theo tiêu chuẩn.

## 8. Đừng nhầm khó đoán, không trùng và có chữ ký

### 8.1. Va chạm không phải đoán trúng

Một bộ đếm tăng dần có thể không bao giờ trùng nhưng rất dễ đoán. Ngược lại, một bộ sinh ngẫu nhiên mạnh vẫn có xác suất va chạm về mặt toán học.

Với `n` token độc lập, đồng đều từ không gian `2^b`, khi xác suất còn nhỏ, xác suất có va chạm xấp xỉ:

```text
P_collision ≈ n × (n - 1) / (2 × 2^b)
```

Đây là bài toán birthday collision, khác với đoán một bí mật cụ thể bằng `q` lần thử. Không lấy ngưỡng birthday rồi khẳng định một token 128 bit chỉ có 64 bit chống đoán trực tiếp.

Server vẫn cần bảo đảm bản ghi token được liên kết đúng. Khi có ràng buộc duy nhất và phát hiện trùng, có thể sinh token mới; không dùng cách thêm một bộ đếm công khai để thay thế toàn bộ bí mật.

### 8.2. UUID không mặc nhiên có 128 bit ngẫu nhiên

Theo RFC 9562, UUIDv4 có 122 bit dành cho dữ liệu ngẫu nhiên, phần còn lại biểu diễn version và variant. Những phiên bản UUID khác có cấu trúc khác. [RFC 9562, UUID Version 4](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.4)

Vì vậy, không suy ra “UUID dài 128 bit” đồng nghĩa “mọi UUID đều là secret 128 bit”. Khi một thiết kế đã yêu cầu 128 bit ngẫu nhiên, UUIDv4 không tự đáp ứng con số đó. Dùng API sinh byte cho recovery secret giúp biểu đạt trực tiếp tham số cần thiết.

### 8.3. Payload dài và chữ ký

JWT có header và payload đọc được không tự có entropy bằng tổng số ký tự của token. Khả năng chống tạo token giả phụ thuộc cơ chế ký hoặc MAC, khóa, thuật toán được cho phép và quy tắc xác minh.

Chữ ký đúng cũng không tự bảo đảm token chỉ dùng một lần hoặc có thể thu hồi ngay. Nếu bearer token hợp lệ bị sao chép, kẻ cầm bản sao có thể không cần đoán hay giả chữ ký. Những kiểm soát đó cần trạng thái hoặc giao thức riêng.

## 9. Những lỗi làm mất lợi ích của entropy cao

| Lỗi thiết kế | Vì sao số bit lớn không cứu được |
| --- | --- |
| Ghi token nguyên văn vào log hoặc công cụ phân tích | Kẻ tấn công lấy giá trị trực tiếp, không phải đoán |
| Gửi token qua kênh đã bị chiếm | Bí mật bị lộ ở nơi nhận |
| Chỉ so sánh một tiền tố ngắn | Phần còn lại không tham gia kiểm tra |
| Cho phép token của tài khoản A đổi tài khoản B | Sai ràng buộc cấp quyền |
| Chấp nhận token hết hạn hoặc đã dùng | Tăng khả năng replay, không liên quan đến độ khó sinh bí mật |
| Hai request đồng thời cùng tiêu thụ token | Thiếu kiểm soát trạng thái một lần |
| Lỗi nguồn ngẫu nhiên được thay bằng giá trị mặc định | Phân bố đầu ra trở nên dự đoán được |
| Token mới luôn giống token cũ trong môi trường nhân bản | Trạng thái hoặc seed bị lặp |

OWASP đặt nguồn sinh mật mã, độ dài chống brute force, lưu trữ an toàn, thời hạn và sử dụng một lần trong cùng nhóm yêu cầu đối với token reset. Chỉ tăng độ dài không thay thế các yêu cầu còn lại. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Trong một luồng đặt lại mật khẩu, việc kiểm tra và tiêu thụ token cần phối hợp với thay đổi mật khẩu theo cơ chế nhất quán. Không đọc `used=false`, cập nhật mật khẩu rồi mới đánh dấu dùng ở một bước tách rời có thể bị chạy đồng thời.

Quyền gỡ MFA, đăng ký passkey và xử lý session sau recovery phải được quyết định rõ. Một token đủ khó đoán không tự cho phép giữ lại mọi session cũ hoặc tự cấp một session đầy đủ trước khi chính sách hoàn tất.

## 10. Cách mô tả entropy trong đặc tả

Một đặc tả có thể ghi theo cấu trúc sau. Các tham số thuộc ví dụ, không phải chuẩn chung cho mọi hệ thống:

| Thuộc tính | Ví dụ cho opaque recovery token |
| --- | --- |
| Nguồn sinh | CSPRNG của nền tảng qua `SecureRandom` |
| Dữ liệu bí mật | 32 byte đầu ra ngẫu nhiên |
| Không gian lý tưởng | `2^256` giá trị, với giả định sinh đúng |
| Biểu diễn | Base64url không padding, 43 ký tự |
| Thành phần không tính entropy | Tiền tố phiên bản, ID hồ sơ, thời gian phát hành |
| Kiểm tra | Đúng toàn bộ bí mật cùng liên kết tài khoản và mục đích |
| Phạm vi đoán | Endpoint, các token đủ điều kiện và tổng số lần thử |
| Trạng thái | Có thời hạn, thu hồi và tiêu thụ một lần theo giao thức |
| Khi không sinh được bí mật | Không cấp token bằng timestamp hoặc giá trị dự phòng |
| Khả năng quan sát | Ghi mã tham chiếu và kết quả, không ghi secret |

Không thể chứng minh độ mạnh mật mã chỉ bằng một lần sinh nhiều token rồi thấy không trùng. Một bộ sinh dự đoán được vẫn có thể tạo nhiều giá trị khác nhau và vượt qua những kiểm tra thống kê đơn giản.

Điều cần bảo đảm là nguồn bí mật phù hợp, không gian đủ lớn cho mô hình đe dọa và phép kiểm tra không làm giảm phần khó đoán. Entropy cao làm việc đoán token trở nên khó; giao thức recovery an toàn còn phải bảo vệ token khỏi bị lộ và giới hạn chính xác quyền mà nó đại diện.
