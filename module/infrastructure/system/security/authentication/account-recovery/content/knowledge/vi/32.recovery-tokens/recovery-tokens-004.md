# Recovery token length

Độ dài recovery token quyết định kích thước không gian mà người tấn công phải tìm kiếm khi đoán bí mật khôi phục. Tuy nhiên, số ký tự nhìn thấy chỉ có ý nghĩa khi biết token được sinh như thế nào, phần nào thực sự ngẫu nhiên và máy chủ chấp nhận bao nhiêu lần thử trong thời gian token còn hiệu lực.

Một chuỗi 64 ký tự tạo từ thời gian hiện tại có thể dễ đoán hơn một chuỗi 22 ký tự mã hóa từ 16 byte ngẫu nhiên mật mã. Một mã sáu chữ số cũng có mô hình bảo vệ khác với một token dài trong liên kết email. Không nên chọn cùng một độ dài cho mọi loại bí mật chỉ vì tất cả đều được gọi là recovery token.

Bài học tập trung vào cách tính và lựa chọn độ dài cho luồng khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực. Các con số xác suất là mô hình minh họa với giả định được nêu rõ; chúng không phải xác suất chiếm đoạt thực tế của toàn hệ thống.

## 1. Xác định loại token trước khi chọn độ dài

| Loại bí mật | Cách người dùng sử dụng | Yêu cầu thiết kế liên quan đến độ dài |
| --- | --- | --- |
| Token trong liên kết khôi phục | Bấm hoặc dán URL | Có thể dùng bí mật dài vì người dùng thường không phải gõ |
| Mã ngắn được cấp khi khôi phục | Đọc từ một kênh rồi nhập vào ứng dụng | Cần cân bằng khả năng nhập với không gian đoán và giới hạn thử |
| Recovery code được lưu từ trước | Lưu an toàn để dùng khi mất phương tiện xác thực | Cần đủ không gian bí mật cho mục đích và thời gian tồn tại, không sao chép tùy tiện độ dài của mã ngắn |
| Grant cho một bước khôi phục | Ứng dụng giữ và dùng để thực hiện hành động được phép | Độ dài đi cùng phạm vi, liên kết yêu cầu, thời hạn và dùng một lần |
| Mã tham chiếu công khai | Tìm đúng yêu cầu hoặc hồ sơ | Không tự là bí mật; biết mã tham chiếu không trao quyền khôi phục |

Nếu một chuỗi cho phép người giữ nó thực hiện hành động nhạy cảm, cần quản lý nó như bí mật trong phạm vi quyền đó. Gọi chuỗi là “request ID” không làm mất vai trò bảo mật nếu backend đang dùng chính nó để cấp quyền.

Ngược lại, một ID tra cứu không cần được tính vào entropy của bí mật khi người tấn công có thể biết ID. Thiết kế nên tách rõ phần định vị và phần chứng minh quyền, thay vì dựa vào việc người ngoài chưa nhìn thấy cấu trúc URL.

OWASP yêu cầu token hoặc mã đặt lại mật khẩu được sinh bằng nguồn ngẫu nhiên mật mã, đủ dài để chống dò, được lưu an toàn, có thời hạn phù hợp và chỉ dùng một lần. Độ dài là một thành phần của các điều kiện này. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 2. Đếm bit ngẫu nhiên, không chỉ đếm ký tự

Với một chuỗi gồm `L` ký tự được chọn độc lập và đều từ bảng chữ cái có `A` ký tự:

```text
Số khả năng: N = A^L
Số bit biểu diễn không gian đều: b = log2(N) = L × log2(A)
```

Ví dụ:

- Một chữ số thập phân có `log2(10) ≈ 3,322` bit.
- Một ký tự hex có 16 khả năng, tương ứng 4 bit.
- Một ký tự được chọn đều từ bảng 32 ký tự có 5 bit.
- Một ký tự được chọn đều từ bảng 64 ký tự có 6 bit.

Công thức trên giả định phân bố đều và các lựa chọn độc lập. Nếu chuỗi có quy luật hoặc một số giá trị xuất hiện nhiều hơn, việc nhân số ký tự với kích thước bảng chữ cái có thể đánh giá quá cao độ khó đoán.

Với `n` byte ngẫu nhiên đều trong mô hình lý tưởng:

```text
b = 8 × n
N = 2^(8 × n)
```

Trong triển khai, khả năng dự đoán còn phụ thuộc chất lượng bộ sinh, trạng thái và nguồn khởi tạo. Việc lấy 32 byte đầu ra không tự chứng nhận rằng toàn bộ hệ thống có mọi tính chất bảo mật ở mức 256 bit.

### 2.1. Phần cố định không tạo thêm entropy

Trong chuỗi giả định:

```text
rt2_<phần bí mật>
```

`rt2_` có thể giúp phân biệt loại và phiên bản token, nhưng là tiền tố công khai. Chỉ phần bí mật được tính vào không gian đoán.

Tương tự, các thành phần sau không tự thêm entropy nếu người tấn công biết hoặc dự đoán được:

- ID tài khoản hoặc mã yêu cầu.
- Thời gian phát hành.
- Tên dịch vụ, tên môi trường hoặc phiên bản.
- Dấu gạch nối để chia nhóm.
- Ký tự kiểm tra được tính từ các ký tự đã có.
- Phần padding của một cách mã hóa.

Một checksum có thể giúp phát hiện nhập sai nhưng không phải phần bí mật ngẫu nhiên mới.

### 2.2. Biến đổi chuỗi không tự làm tăng bí mật

Mã hóa Base64 một chuỗi thời gian vẫn chỉ che cách biểu diễn của thời gian đó. Băm một mã sáu chữ số thành chuỗi hex dài cũng không biến một triệu khả năng đầu vào thành một không gian bí mật 256 bit.

Token có cấu trúc dài cũng không thể được đánh giá chỉ bằng số ký tự. Với một token được ký, khả năng giả mạo phụ thuộc cơ chế ký, khóa và kiểm tra giao thức; độ dài payload công khai không phải entropy của một bí mật bearer ngẫu nhiên.

## 3. Quy đổi byte thành độ dài biểu diễn

Khi mã hóa cùng một lượng byte, độ dài nhìn thấy thay đổi nhưng không gian đầu vào vẫn giữ nguyên.

| Dữ liệu được sinh | Cách biểu diễn | Số ký tự | Không gian ngẫu nhiên danh định |
| --- | --- | ---: | ---: |
| Một giá trị đều từ `000000` đến `999999` | Thập phân, giữ đủ sáu chữ số | 6 | Khoảng 19,93 bit |
| Một giá trị đều từ `00000000` đến `99999999` | Thập phân, giữ đủ tám chữ số | 8 | Khoảng 26,58 bit |
| Một giá trị đều trong toàn bộ mã mười chữ số | Thập phân, giữ số 0 đầu | 10 | Khoảng 33,22 bit |
| 16 byte ngẫu nhiên | Hex | 32 | 128 bit |
| 16 byte ngẫu nhiên | Base64url không padding | 22 | 128 bit |
| 24 byte ngẫu nhiên | Base64url không padding | 32 | 192 bit |
| 32 byte ngẫu nhiên | Hex | 64 | 256 bit |
| 32 byte ngẫu nhiên | Base64url không padding | 43 | 256 bit |

Với hex, số ký tự bằng `2 × n`. Với Base64url không padding:

```text
L = ceil(8 × n / 6)
```

Trong đó `ceil` là làm tròn lên. Vì vậy, 16 byte cần 22 ký tự và 32 byte cần 43 ký tự khi dùng cách biểu diễn này.

### 3.1. Không tính thừa bit ở ký tự cuối

Chuỗi Base64url mã hóa từ 16 byte có 128 bit đầu vào, không phải `22 × 6 = 132` bit ngẫu nhiên. Ký tự cuối chỉ mang hai bit dữ liệu còn lại; các bit còn lại phục vụ biểu diễn chuẩn. Với 32 byte, tổng dữ liệu là 256 bit dù chuỗi có 43 ký tự.

Nếu thay vì mã hóa byte, hệ thống chọn đều và độc lập 22 ký tự từ bảng 64 ký tự, không gian lý thuyết lại là 132 bit. Đây là hai cách sinh khác nhau, nên không thể lấy kết quả của cách này gán cho cách kia.

### 3.2. Dấu phân cách và padding không tăng bảo vệ

Một mã được hiển thị theo nhóm bốn ký tự có thể dễ nhập hơn. Dấu phân cách giúp trình bày nhưng không thêm bit ngẫu nhiên. Nếu dùng padding `=`, ký tự đó cũng không bổ sung bí mật.

Java cung cấp bộ mã hóa URL-safe qua `Base64.getUrlEncoder()` và tùy chọn `withoutPadding()` để bỏ padding. Đây là lựa chọn về biểu diễn, không phải cơ chế tự sinh ngẫu nhiên. [Java SE 21 — Base64](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.html), [Base64.Encoder.withoutPadding](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.Encoder.html#withoutPadding()).

## 4. Liên hệ độ dài với xác suất đoán trực tuyến

Giả sử có đúng một token hợp lệ, token được chọn đều từ không gian `N`, và người tấn công không có thông tin về giá trị token.

Với `Q` lần đoán độc lập, chọn ngẫu nhiên có thể lặp lại:

```text
P(thành công) = 1 - (1 - 1/N)^Q
P(thành công) ≤ min(1, Q/N)
```

Nếu người tấn công thử `Q` giá trị khác nhau và `Q ≤ N`, xác suất trúng một token đều là `Q/N`. Khi `Q` rất nhỏ so với `N`, cách xấp xỉ `Q/N` cũng thuận tiện cho mô hình đoán ngẫu nhiên.

### 4.1. Ví dụ mã sáu chữ số

Mã sáu chữ số có `N = 1.000.000`. Nếu đúng một mã còn hợp lệ cho yêu cầu và hệ thống thực sự chỉ cho phép năm lần đoán khác nhau trong toàn bộ phạm vi đang xét:

```text
P = 5 / 1.000.000
  = 0,000005
  = 0,0005%
```

Con số này chỉ mô tả một yêu cầu dưới những giả định trên. Nó không chứng minh toàn hệ thống có rủi ro nhỏ tương ứng. Người tấn công có thể nhắm nhiều tài khoản, khai thác nhiều mã cùng còn hiệu lực hoặc lợi dụng việc đặt lại bộ đếm.

Năm lần thử trên mỗi phiên trình duyệt không phải năm lần thử trên mỗi tài khoản. Nếu mở phiên mới hoặc gửi lại mã làm ngân sách thử tăng không kiểm soát, `Q` thực tế lớn hơn giá trị thiết kế.

### 4.2. Ví dụ token 128 bit

Trong cùng mô hình đều và không rò rỉ, một token 128 bit có khoảng `3,40 × 10^38` khả năng. Với `10^9` lần đoán, cận trên `Q/N` vào khoảng:

```text
10^9 / 2^128 ≈ 2,94 × 10^-30
```

Điều này giải thích giá trị của token dài đối với tấn công đoán. Nó không nói gì về trường hợp token bị lấy nguyên vẹn từ log, hộp thư, thiết bị hoặc trang phishing.

### 4.3. Ước lượng ngân sách bit

Nếu chỉ xét mô hình một token và dùng cận `Q / 2^b`, có thể viết:

```text
b ≥ ceil(log2(Q / pMax))
```

`pMax` là cận xác suất đoán mà mô hình muốn đạt, không phải một mức rủi ro được tiêu chuẩn tự động chấp nhận.

Ví dụ toán học: với `Q = 2^30` và mục tiêu cận `2^-80`, cần ít nhất 110 bit trong mô hình đó. Một thiết kế có thể chọn 128 bit hoặc nhiều hơn để có khoảng dự phòng. Không nên dùng phép tính đơn giản này để bỏ qua chất lượng bộ sinh, các mã hợp lệ khác hoặc những đường tấn công ngoài đoán.

## 5. Số lượng token còn hiệu lực cũng ảnh hưởng kết quả

Nếu một endpoint chấp nhận bất kỳ token nào trong `M` token hợp lệ khác nhau, mỗi token thuộc không gian `N`, một lần đoán đều có xác suất trúng một token là `M/N`. Với `Q` lần thử, cận hợp đơn giản là:

```text
P(thành công với ít nhất một token) ≤ min(1, Q × M / N)
```

Cần phân biệt hai mục tiêu:

- **Nhắm một tài khoản hoặc yêu cầu cụ thể:** chỉ những token có thể cấp quyền cho đích đó được tính vào tập hợp tương ứng.
- **Tìm bất kỳ tài khoản nào có thể chiếm quyền:** nhiều token đang hoạt động trong toàn hệ thống có thể trở thành mục tiêu nếu endpoint cho phép tra cứu toàn cục bằng token.

Nếu token được kiểm tra trong đúng bản ghi yêu cầu đã chọn, số token của tài khoản khác không tự động nhân vào xác suất của yêu cầu đó. Tuy nhiên, ID yêu cầu công khai cũng không được tính như một bí mật bổ sung nếu kẻ tấn công biết ID.

Việc gửi lại cần có chính sách rõ: dùng lại token hiện tại hay cấp token mới; nếu cấp mới thì token cũ có còn được chấp nhận không. Cấp một mã mới mà giữ nhiều mã cũ có thể làm `M` tăng. Cấp mới rồi đặt lại mọi giới hạn cũng có thể làm `Q` tăng.

Thời hạn có thể giảm khoảng thời gian thử. Trong mô hình thô với tốc độ hiệu dụng `r` và thời hạn `T`, có thể ước lượng `Q ≈ r × T`, nhưng hệ thống phân tán, nhiều nguồn gửi hoặc nhiều API cùng kiểm tra có thể làm tốc độ hiệu dụng khác xa một giới hạn đơn lẻ.

Token dài không loại bỏ nhu cầu hạn chế lạm dụng, còn thời hạn ngắn không đủ để bù cho một không gian quá nhỏ khi tốc độ thử không được kiểm soát.

## 6. Phân biệt đoán trúng và va chạm khi phát hành

Hai câu hỏi thường bị trộn lẫn:

1. Người tấn công cần đoán bao nhiêu lần để trúng token đang có?
2. Hệ thống phát hành bao nhiêu token trước khi có khả năng sinh trùng giá trị?

Với `k` token được sinh độc lập và đều từ không gian `N`, xác suất có ít nhất một va chạm có thể xấp xỉ bằng:

```text
P(va chạm) ≈ 1 - exp(-k × (k - 1) / (2 × N))
```

Khi xác suất còn nhỏ, có thể dùng xấp xỉ `k × (k - 1) / (2 × N)`.

Ví dụ, với khoảng một tỷ giá trị sinh ra trong không gian 128 bit, xác suất va chạm theo mô hình này vào khoảng `1,47 × 10^-21`. Với không gian 64 bit và cùng số lượng, xác suất có va chạm xấp xỉ 2,7%.

Các con số về 64 bit ở đây là mô hình một tập rất lớn được xét chung. Chúng không có nghĩa mọi mã 64 bit ở mọi tài khoản đều có nguy cơ vận hành giống nhau: phạm vi định danh, các mã còn hiệu lực và cách lưu quyết định việc trùng có gây xung đột hay không.

Không dùng xác suất va chạm để thay cho xác suất đoán một mục tiêu. Hệ thống cũng nên có cách xử lý xung đột trong phạm vi cần duy nhất, thay vì giả định xác suất nhỏ đồng nghĩa không bao giờ xảy ra.

Nếu dùng mã ngắn theo từng yêu cầu, cùng một chuỗi số ở hai tài khoản khác nhau có thể là bình thường khi backend luôn kiểm tra đúng phạm vi. Nếu dùng chuỗi đó làm khóa toàn cục duy nhất để tìm tài khoản, vấn đề hoàn toàn khác.

## 7. Chọn độ dài theo cách sử dụng

### 7.1. Token trong URL hoặc ứng dụng

Khi người dùng bấm liên kết, việc có thêm một số ký tự thường ít gây khó khăn hơn so với mã phải nhập tay. Có thể chọn số byte ngẫu nhiên trước, sau đó dùng biểu diễn phù hợp với URL và hạ tầng.

Một lựa chọn thiết kế minh họa trong bài là 32 byte ngẫu nhiên, mã hóa Base64url không padding thành 43 ký tự. Đây là lựa chọn của ví dụ, không phải tuyên bố mọi tiêu chuẩn đều bắt buộc đúng 32 byte.

Thiết kế khác có thể chọn 16 byte cho không gian 128 bit hoặc độ dài lớn hơn tùy yêu cầu. Quyết định cần nêu rõ mục đích, mô hình đoán, chất lượng bộ sinh và vòng đời; không chọn vì một chuỗi “trông có vẻ dài”.

### 7.2. Mã phải nhập tay

Mã số hoặc bảng ký tự dễ phân biệt có thể giảm lỗi nhập. Đổi lại, cần kiểm soát chặt số lần thử, thời hạn, phạm vi yêu cầu và các giá trị còn được chấp nhận.

Nếu mã có số 0 ở đầu, hệ thống phải giữ nguyên số vị trí đã thiết kế. Chuyển `003821` thành số nguyên rồi hiển thị `3821` làm thay đổi định dạng và có thể tạo lỗi giữa các thành phần.

Nhóm ký tự và dấu phân cách có thể giúp nhập liệu. Nếu loại bỏ ký tự dễ nhầm, kích thước bảng chữ cái thay đổi; phải tính lại số bit theo bảng thực tế. Không cộng entropy cho cả chữ hoa và chữ thường nếu bộ xác minh đang coi chúng là cùng một ký tự.

### 7.3. Mã lưu từ trước khác mã được cấp lúc khôi phục

NIST SP 800-63B-4 yêu cầu saved recovery code có ít nhất 64 bit từ bộ sinh ngẫu nhiên được chấp thuận; issued recovery code có yêu cầu tối thiểu sáu chữ số thập phân hoặc tương đương, cùng các điều kiện khác của phương thức. Hai yêu cầu thuộc hai loại mã khác nhau. Không lấy mức tối thiểu của mã được cấp để thiết kế mọi token URL hoặc mã dự phòng lưu lâu. [NIST SP 800-63B-4 — Account Recovery Methods](https://pages.nist.gov/800-63-4/sp800-63b.html).

Đạt độ dài tối thiểu của một loại mã cũng không tự làm toàn bộ luồng đạt một mức đảm bảo. Việc khôi phục tài khoản còn phụ thuộc tổ hợp bằng chứng và các điều kiện của chính sách đang áp dụng.

## 8. Sinh token bằng Java và giữ đúng độ dài đầu vào

Ví dụ dưới đây chỉ minh họa bước sinh token dài. Nó chưa bao gồm phát hành, lưu, gửi, xác minh hoặc tiêu thụ quyền khôi phục.

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class RecoveryTokenGenerator {
    private static final int TOKEN_BYTES = 32;
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private RecoveryTokenGenerator() {
    }

    public static String generate() {
        byte[] tokenBytes = new byte[TOKEN_BYTES];
        RANDOM.nextBytes(tokenBytes);
        return ENCODER.encodeToString(tokenBytes);
    }
}
```

`TOKEN_BYTES` là số byte trước khi mã hóa. Giá trị 32 cho ra chuỗi 43 ký tự trong định dạng đã chọn. Nếu muốn 32 ký tự Base64url từ byte đầu vào, 24 byte mới là phép quy đổi tương ứng, với không gian danh định 192 bit.

Java mô tả `SecureRandom` là bộ sinh ngẫu nhiên mạnh về mật mã và cung cấp `nextBytes` để lấy byte. Không tự khởi tạo bằng timestamp, ID tài khoản hoặc một giá trị dự đoán được để làm cho token “dễ tái tạo”. [Java SE 21 — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html).

Không thay bước sinh bằng `Math.random()`, một bộ sinh dùng cho mô phỏng thông thường hoặc một chuỗi tăng dần. Việc mã hóa hay băm đầu ra của nguồn dễ đoán không sửa được vấn đề nguồn bí mật ban đầu.

### 8.1. Tránh thiên lệch khi tạo bảng ký tự tùy chỉnh

Lấy một byte rồi tính `% A` không luôn cho phân bố đều. Ví dụ, với `A = 62`, 256 giá trị byte không chia hết cho 62; một số ký tự sẽ nhận nhiều giá trị đầu vào hơn các ký tự khác.

Nếu cần sinh trực tiếp theo bảng tùy chỉnh, sử dụng cơ chế chọn đều có nguồn ngẫu nhiên mật mã và cách xử lý thiên lệch phù hợp. Sinh byte rồi dùng một encoding chuẩn thường giúp giảm phần mã tùy chỉnh phải tự xây dựng.

### 8.2. Không rút ngắn sau khi sinh để vừa giao diện

Nếu sinh 32 byte rồi chỉ giữ 16 ký tự đầu của chuỗi Base64url, phần được dùng chỉ còn 96 bit dữ liệu trong trường hợp này, không còn không gian 256 bit ban đầu.

Mọi thao tác `substring`, cắt cột dữ liệu, giới hạn trường nhập hoặc rút gọn trong template phải được tính vào độ dài thực sự được xác minh. Việc đã từng sinh một token dài không bảo vệ được một phiên bản bị cắt ngắn ở bước sau.

## 9. Giữ nguyên độ dài qua API, lưu trữ và giao diện

Token cần có đặc tả định dạng đầy đủ, gồm phiên bản, bảng ký tự, độ dài phần bí mật, padding và cách chuẩn hóa được phép.

Ví dụ đặc tả minh họa:

```text
Loại: opaque recovery token
Bí mật đầu vào: 32 byte ngẫu nhiên
Encoding: Base64url, không padding
Độ dài phần bí mật: đúng 43 ký tự ASCII
Nếu có tiền tố rt2_: tổng độ dài là 47 ký tự
Phân biệt chữ hoa và chữ thường: có
Cắt ngắn hoặc so khớp tiền tố: không
```

Cần giữ đặc tả xuyên suốt các thành phần:

| Thành phần | Lỗi liên quan đến độ dài |
| --- | --- |
| Bộ sinh | Nhầm số byte với số ký tự |
| DTO hoặc API gateway | Giới hạn nhỏ hơn định dạng thực tế |
| Giao diện | `maxlength` cắt token, tự đổi chữ hoa hoặc chữ thường |
| Template thông báo | Bỏ phần cuối URL hoặc làm sai dấu phân cách |
| Kho dữ liệu | Cột nhỏ, so sánh không phân biệt hoa thường khi cần phân biệt |
| Bộ xác minh | Chỉ so sánh một đoạn, chấp nhận token ngắn hơn quy định |
| Chuyển đổi phiên bản | Dùng parser cũ để chấp nhận một định dạng mới không đúng nghĩa |

Base64 thông thường có thể chứa `+` và `/`, trong khi Base64url dùng bảng phù hợp với URL. Việc một thành phần chuyển `+` thành khoảng trắng có thể làm hỏng token nếu chọn sai cách biểu diễn cho đường truyền.

Không đưa token vào log để tìm xem thành phần nào đã cắt ngắn. Có thể quan sát loại định dạng, độ dài nhận được và mã lỗi không chứa bí mật. Khi cần dữ liệu minh họa cho vận hành, dùng giá trị không có hiệu lực.

### 9.1. Kiểm tra định dạng không phải xác minh quyền

Đúng 43 ký tự chỉ chứng minh chuỗi có độ dài phù hợp. Một người tấn công cũng có thể tạo chuỗi đúng độ dài. Backend vẫn phải kiểm tra bí mật, bản ghi yêu cầu, mục đích, thời hạn, trạng thái sử dụng và các điều kiện liên quan.

Một đường xác minh minh họa:

```text
Giới hạn kích thước request trước khi xử lý tốn tài nguyên
→ kiểm tra phiên bản và độ dài theo định dạng
→ kiểm tra bảng ký tự, padding và biểu diễn chuẩn
→ xác định đúng bản ghi hoặc phạm vi kiểm tra
→ xác minh bí mật theo cơ chế lưu đã chọn
→ kiểm tra mục đích, thời hạn và trạng thái
→ tiêu thụ quyền dùng một lần theo cơ chế nguyên tử
```

Nếu giải mã byte rồi dùng byte đó làm giá trị chuẩn, cần xử lý thống nhất mọi nơi tính khóa tra cứu, giới hạn thử và kiểm tra dùng một lần. Nếu yêu cầu duy nhất một cách biểu diễn văn bản, có thể mã hóa lại và đối chiếu với đầu vào theo đặc tả. Tránh để các biểu diễn tương đương của cùng byte trở thành nhiều danh tính token khác nhau.

Không tự sửa token bằng cách bỏ ký tự bất kỳ, chuyển hết sang chữ thường hoặc chấp nhận đoạn đầu “gần đúng”. Những phép biến đổi đó có thể thu hẹp không gian bí mật hoặc làm việc dùng một lần không nhất quán.

## 10. Độ dài khi lưu token và khi người dùng trình token

Một hệ thống có thể lưu giá trị xác minh như digest thay vì lưu bản rõ token ngẫu nhiên. Khi đó cần phân biệt:

- Số byte bí mật được phát hành.
- Độ dài chuỗi người dùng nhận.
- Độ dài giá trị lưu phục vụ xác minh.

Ví dụ, token đầu vào 32 byte và chuỗi Base64url 43 ký tự không có nghĩa cột digest cũng phải có đúng 43 ký tự. Digest có kiểu và biểu diễn riêng. Cấu trúc lưu cần được xác định từ cơ chế thực tế, không sao chép độ dài giữa các trường vì cùng mang tên token.

Với bí mật ngẫu nhiên đủ lớn, lưu digest thích hợp có thể giúp giảm hậu quả khi lộ kho dữ liệu so với lưu bản rõ. Tuy nhiên, digest của mã sáu chữ số vẫn có tập đầu vào nhỏ. Người có dữ liệu xác minh có thể thử toàn bộ tập mã nếu không còn cơ chế bảo vệ phù hợp với mô hình tấn công đó.

Vì vậy, chống đoán trực tuyến và bảo vệ trước việc lộ dữ liệu xác minh là hai vấn đề khác nhau. Một mã ngắn có thể cần cơ chế bảo vệ bằng khóa máy chủ được quản lý tách biệt hoặc phương án khác đã được phân tích cho bối cảnh triển khai. Băm thành chuỗi dài không tự giải quyết rủi ro dò ngoại tuyến.

Việc chọn cơ chế lưu cũng không thay cho bảo vệ đường gửi. Nếu token bản rõ xuất hiện trong log, analytics, lịch sử hỗ trợ hoặc một thiết bị bị xâm nhập, người tấn công không cần đoán không gian bí mật nữa.

## 11. Những giới hạn độ dài không thể khắc phục

| Vấn đề | Vì sao tăng số ký tự không đủ |
| --- | --- |
| Token bị lộ nguyên vẹn | Người giữ token có thể trình trực tiếp trong phạm vi quyền của token |
| Bộ sinh dự đoán được | Chuỗi dài vẫn có thể xuất phát từ ít trạng thái bí mật |
| Chấp nhận nhiều lần | Người tấn công có thể phát lại một token đã dùng |
| Không ràng buộc mục đích | Token của bước ít nhạy cảm có thể bị dùng cho hành động khác |
| Không kiểm tra đúng tài khoản hoặc yêu cầu | Bí mật có thể bị áp dụng sai đối tượng |
| Không xử lý đồng thời | Hai request có thể cùng tiêu thụ một quyền |
| Nhánh dự phòng quá yếu | Người tấn công bỏ qua token dài bằng một đường khác |
| Kênh khôi phục bị chiếm quyền | Token được gửi thẳng tới bên không còn an toàn |

Độ dài có giá trị lớn đối với khả năng đoán, nhưng token khôi phục vẫn là một quyền nhạy cảm. Cần giới hạn mục đích, thời hạn và trạng thái sử dụng; quyết định có cần thêm bằng chứng để gỡ MFA hoặc đăng ký passkey mới phải được xác định ở cấp luồng.

Token dài cũng không nên dẫn tới việc tự động cấp phiên đăng nhập đầy đủ chỉ vì hình thức bí mật trông mạnh. Sau khi thực hiện hành động được phép, việc xử lý session, refresh token, yếu tố bị xâm nhập và thông báo bảo mật vẫn thuộc chính sách khôi phục.

## 12. Ví dụ lựa chọn và ghi lại quyết định thiết kế

Một dịch vụ cần gửi liên kết đặt lại mật khẩu. Người dùng chủ yếu bấm liên kết, nên đội thiết kế chọn ví dụ sau:

```text
Nguồn bí mật: SecureRandom theo cấu hình triển khai phù hợp
Đầu vào: 32 byte ngẫu nhiên
Biểu diễn: Base64url không padding
Độ dài bí mật được truyền: 43 ký tự
Không gian đầu ra danh định: 256 bit
Phạm vi: một tài khoản, một yêu cầu, một mục đích
Vòng đời: có thời hạn, dùng một lần, có thể bị thu hồi
```

Trong quyết định đó, lý do chọn 32 byte là tạo không gian đoán rất lớn mà không buộc người dùng gõ thủ công. Đội thiết kế vẫn phải xác định giới hạn phát hành, số token được chấp nhận đồng thời, xử lý gửi lại và đường xác minh có nhất quán không.

Một màn hình khác cần mã nhập tay từ kênh khôi phục. Đội thiết kế không rút ngắn token URL hiện có rồi giả định đặc tính bảo mật được giữ nguyên. Họ coi đây là một loại mã riêng, tính lại không gian khả năng và ngân sách thử, kiểm tra yêu cầu của phương thức, đồng thời xác định tổ hợp bằng chứng cần thiết cho hành động.

Nếu sau này muốn thêm tiền tố hoặc thay encoding, phần bí mật không được vô tình ngắn đi. Nếu muốn giảm số byte, thay đổi phải được xem như thay đổi tham số bảo mật có phiên bản, cùng thời gian chuyển tiếp và cách xử lý các token cũ còn hiệu lực. Việc giao diện chấp nhận chuỗi ngắn hơn không tự làm máy chủ hiểu hoặc chấp nhận một chính sách token mới.
