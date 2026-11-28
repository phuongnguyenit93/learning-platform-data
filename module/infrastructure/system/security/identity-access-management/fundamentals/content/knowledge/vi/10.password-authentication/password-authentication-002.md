# Password length — Độ dài mật khẩu

Độ dài mật khẩu là số ký tự mà hệ thống thực sự đưa vào quá trình xác minh bí mật của người dùng. Một chính sách có ý nghĩa phải quy định cả độ dài tối thiểu, độ dài tối đa, cách đếm ký tự và cách xử lý đầu vào xuyên suốt luồng xác thực.

Trong nền tảng quản lý danh tính và quyền truy cập (IAM), chính sách này bảo vệ một yếu tố xác thực. Nó không quyết định người dùng được truy cập tài nguyên nào, cũng không tự thay thế MFA, quản lý phiên hay nguyên tắc ít quyền nhất. Tài khoản có mật khẩu dài vẫn cần được kiểm soát quyền và vòng đời truy cập phù hợp.

Sau bài học, người học có thể chọn giới hạn độ dài có căn cứ, giải thích vì sao mật khẩu dài vẫn có thể dễ đoán, xử lý tiếng Việt và Unicode nhất quán, và nhận diện những điểm khiến hệ thống chỉ kiểm tra một phần mật khẩu.

## 1. Độ dài giúp chống lại điều gì?

Kẻ tấn công có thể thử đoán mật khẩu theo hai cách chính:

| Tình huống | Kẻ tấn công làm gì? | Vai trò của độ dài |
| --- | --- | --- |
| Đoán trực tuyến | Gửi nhiều yêu cầu đăng nhập tới dịch vụ | Làm việc đoán khó hơn khi bí mật được chọn tốt; vẫn cần giới hạn tần suất thử |
| Đoán ngoại tuyến | Có được dữ liệu hash và tự thử ứng viên trên hạ tầng của họ | Tăng chi phí tìm kiếm khi có đủ tính khó đoán; thuật toán hash và tham số chi phí vẫn quan trọng |
| Credential stuffing | Dùng lại cặp tài khoản và mật khẩu đã lộ ở nơi khác | Không bảo vệ nếu người dùng tái sử dụng đúng mật khẩu đã lộ |
| Lừa đảo lấy mật khẩu | Khiến người dùng cung cấp bí mật cho trang giả | Không ngăn việc người dùng gửi toàn bộ mật khẩu cho kẻ tấn công |

Hai tình huống cuối cho thấy giới hạn của chính sách độ dài: biết được bí mật thì kẻ tấn công không cần đoán nó. Khi đánh giá thiết kế IAM, cần hỏi cả “mật khẩu có khó đoán không?” và “hệ thống ngăn sử dụng bí mật bị đánh cắp bằng cách nào?”.

### Mô hình toán học có điều kiện

Nếu từng ký tự được chọn **ngẫu nhiên, độc lập và đồng đều** từ tập gồm `R` ký tự, mật khẩu dài `L` có không gian lựa chọn:

```text
Số khả năng = R^L
Entropy của cách sinh = L × log2(R) bit
```

Giữ nguyên cách sinh, thêm một ký tự sẽ nhân số khả năng với `R`. Nhưng công thức này mô tả một quy trình tạo ngẫu nhiên, không phải phép đo tự động cho mọi chuỗi người dùng gõ vào.

Một câu quen thuộc dài, tên công ty nối năm hiện tại, hoặc một ký tự lặp nhiều lần không có tính khó đoán tương đương chuỗi ngẫu nhiên cùng độ dài. Tương tự, bốn từ được người dùng chọn theo một câu chuyện quen thuộc khác với bốn từ được bộ sinh chọn độc lập từ danh sách từ.

Ví dụ toán học: chọn độc lập bốn từ từ danh sách `7.776` từ có khoảng `4 × log2(7.776) ≈ 51,7` bit entropy của **quy trình sinh**. Con số đó không áp dụng cho một câu bốn từ bất kỳ và không suy ra trực tiếp thời gian bẻ khóa. Thời gian còn phụ thuộc thuật toán hash, tài nguyên và kiến thức của kẻ tấn công.

Các chuỗi xuất hiện trong tài liệu hoặc ví dụ công khai không phải bí mật để dùng cho tài khoản thật.

## 2. Chọn độ dài tối thiểu và tối đa

NIST SP 800-63B-4, mục 3.1.1.2, quy định:

| Trường hợp | Yêu cầu hoặc khuyến nghị |
| --- | --- |
| Mật khẩu là yếu tố xác thực duy nhất | Tối thiểu 15 ký tự — `SHALL` |
| Mật khẩu chỉ dùng trong quy trình MFA | Có thể cho phép ngắn hơn, nhưng tối thiểu 8 ký tự — `MAY` và `SHALL` |
| Độ dài tối đa được hỗ trợ | Nên cho phép ít nhất 64 ký tự — `SHOULD` |

NIST yêu cầu đếm mỗi Unicode code point là một ký tự và xác minh toàn bộ mật khẩu, không cắt bớt. Đây là yêu cầu trong phạm vi hướng dẫn NIST, không phải khẳng định mọi hệ thống đều có nghĩa vụ pháp lý giống nhau. [Nguồn: NIST SP 800-63B-4, Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

Khi vận dụng vào sản phẩm, cần xác định những đường đăng nhập thực tế. Một nút “bật MFA” trên giao diện chưa chứng minh mọi lần đăng nhập đều hoàn tất hai yếu tố. Chẳng hạn, nếu API cũ cấp phiên chỉ từ username và password, đường đó vẫn cho phép xác thực bằng mật khẩu đơn lẻ.

Một lựa chọn triển khai đơn giản là áp dụng tối thiểu 15 ký tự cho toàn bộ mật khẩu mới, dù tài khoản có MFA hay chưa. Đây là quyết định thiết kế trong ví dụ, không phải yêu cầu phải nâng mọi mật khẩu MFA lên cùng một mức.

Đối với tài khoản quản trị, tăng thêm độ dài không tự giải quyết rủi ro quyền cao. Quyết định về đặc quyền cần đi cùng MFA phù hợp, giới hạn phiên và kiểm soát hành động nhạy cảm.

### Vì sao không đặt tối đa quá ngắn?

Giới hạn tối đa thấp có thể loại bỏ mật khẩu do trình quản lý mật khẩu tạo ra hoặc cụm mật khẩu mà người dùng có thể nhớ. Ví dụ, nếu chỉ cho phép tối đa 16 ký tự, một người dùng đang có bí mật ngẫu nhiên dài 32 ký tự sẽ phải tạo bí mật khác để dùng dịch vụ.

Ngược lại, nhận đầu vào dài tùy ý cũng gây chi phí truyền, phân tích và xử lý. Cần tách hai giới hạn:

- **Giới hạn nghiệp vụ:** số code point của mật khẩu được phép thiết lập, chẳng hạn tối đa 128 trong ví dụ của bài.
- **Giới hạn tài nguyên:** kích thước HTTP body, bộ nhớ hoặc lượng đầu vào trước xử lý, nhằm loại bỏ yêu cầu quá lớn sớm.

Các giá trị 128 và giới hạn tài nguyên cụ thể là lựa chọn của hệ thống. Chúng cần được kiểm tra với thư viện hash, giao thức và các client được hỗ trợ.

## 3. Ký tự, code point và byte là ba đơn vị khác nhau

Trong ứng dụng tiếng Việt, hai chuỗi nhìn giống nhau có thể có biểu diễn Unicode khác nhau. Một số emoji cũng chiếm nhiều đơn vị mã hơn một chữ cái ASCII.

| Đơn vị | Ý nghĩa | Dùng ở đâu? |
| --- | --- | --- |
| UTF-16 code unit | Một đơn vị 16 bit trong biểu diễn chuỗi Java | Chỉ số chuỗi và `String.length()` |
| Unicode code point | Một giá trị mã Unicode; một ký tự ngoài BMP cần hai code unit UTF-16 | Đếm độ dài theo chính sách đang xét |
| Byte UTF-8 | Dung lượng sau mã hóa thành byte | Truyền dữ liệu và đầu vào của thư viện hash |
| Grapheme cluster | Cụm ký tự mà người dùng thường cảm nhận như một ký tự hiển thị | Trình bày giao diện; không đồng nhất với code point |

Java dùng UTF-16 cho `String`. Vì vậy, `length()` không phải lúc nào cũng bằng số code point. Phương thức `codePointCount()` đếm theo code point trong đoạn được chỉ định. [Nguồn: Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)

```java
String sample = "A😀é";

int utf16Units = sample.length();                    // 4
int codePoints = sample.codePointCount(0, sample.length()); // 3
int utf8Bytes = sample.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;   // 7
```

Nếu giao diện hiển thị “đủ 15 ký tự” dựa trên đơn vị khác backend, người dùng có thể bị từ chối sau khi gửi biểu mẫu. Bộ đếm trên giao diện cần cùng định nghĩa với server; server vẫn là nơi quyết định chấp nhận đầu vào.

### Chuẩn hóa Unicode phải nhất quán

Chữ `é` có thể được biểu diễn bằng một code point `U+00E9`, hoặc bằng `e` nối dấu sắc kết hợp `U+0301`. NFC đưa các biểu diễn tương đương chuẩn tắc về dạng tổ hợp phù hợp. NFC không có nghĩa là bỏ dấu tiếng Việt, đổi chữ hoa thành chữ thường hay xóa khoảng trắng. [Nguồn: Unicode UAX #15](https://www.unicode.org/reports/tr15/)

```java
String composed = "\u00E9";
String decomposed = "e\u0301";

String a = java.text.Normalizer.normalize(
        composed, java.text.Normalizer.Form.NFC);
String b = java.text.Normalizer.normalize(
        decomposed, java.text.Normalizer.Form.NFC);

boolean sameAfterNormalization = a.equals(b); // true
```

`java.text.Normalizer` cung cấp các dạng chuẩn hóa Unicode, trong đó có NFC. [Nguồn: Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)

NIST khuyến nghị NFC trước khi hash nếu chấp nhận Unicode. [Nguồn: NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

Trong thiết kế minh họa bên dưới, việc đếm độ dài diễn ra **sau NFC**. Đăng ký, đặt lại mật khẩu và đăng nhập phải dùng cùng quy tắc biểu diễn cho cùng phiên bản credential. Nếu đăng ký chuẩn hóa còn đăng nhập giữ nguyên chuỗi ban đầu, hai lần nhập nhìn giống nhau vẫn có thể tạo byte khác nhau để xác minh.

Không thêm `trim()`, `strip()`, chuyển chữ thường hay bỏ dấu vào một helper xử lý input dùng chung. Những thao tác đó có thể làm nhiều bí mật khác nhau trở thành cùng đầu vào mà người dùng không được biết.

## 4. Độ dài được nhập phải là độ dài được xác minh

Một form cho phép nhập 128 ký tự chưa chứng minh hệ thống kiểm tra đủ 128 ký tự. Cần xem toàn bộ đường đi:

```text
Client → HTTP/API → xử lý Unicode → kiểm tra policy → mã hóa → thư viện hash
```

Nếu một thành phần cắt chuỗi giữa đường, phần bị cắt không đóng góp vào bí mật mà hệ thống kiểm tra. Hai mật khẩu khác nhau ở phần đuôi có thể bị coi là giống nhau.

Ví dụ lỗi:

```java
// Sai: thông báo chấp nhận toàn bộ nhưng chỉ dùng 16 code unit đầu.
String shortened = password.substring(0, Math.min(password.length(), 16));
```

Với lỗi này, `hai_chuoi_co_cung_tien_to_A` và `hai_chuoi_co_cung_tien_to_B` có thể đi vào cùng đầu vào hash. Việc tăng giới hạn trên giao diện không sửa được lỗi đó.

Một trường hợp cần chú ý là bcrypt: nhiều triển khai có giới hạn đầu vào 72 **byte**. Không được hiểu 72 byte thành 72 ký tự Unicode, hoặc âm thầm bỏ phần vượt giới hạn. [Nguồn: OWASP Password Storage Cheat Sheet — Input Limits of bcrypt](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#input-limits-of-bcrypt)

Nếu một hệ thống dùng thư viện có giới hạn byte, nhóm triển khai phải giải quyết tương thích giữa lời hứa của policy và khả năng thực tế của thư viện. Đặt tối đa 64 ký tự Unicode không tự bảo đảm đầu vào vừa 72 byte. Giải pháp chuyển đổi thuật toán hoặc định dạng credential cần được thiết kế và kiểm thử riêng; không sửa bằng cách tự cắt chuỗi hoặc ghép thêm một bước hash tùy ý.

## 5. Ví dụ Java: kiểm tra độ dài khi thiết lập mật khẩu

Ví dụ sau minh họa chính sách cho **mật khẩu mới**:

- Tối thiểu 15, tối đa 128 code point sau NFC.
- Từ chối đầu vào quá lớn trước khi chuẩn hóa.
- Từ chối chuỗi UTF-16 không hợp lệ trước khi mã hóa.
- Giữ nguyên chữ hoa, chữ thường, dấu và khoảng trắng ngoài biến đổi NFC đã công bố.

```java
import java.text.Normalizer;

public final class PasswordLengthPolicy {
    private static final int MIN_CODE_POINTS = 15;
    private static final int MAX_CODE_POINTS = 128;

    // Giới hạn tài nguyên của ví dụ, không phải độ dài mật khẩu tối đa.
    private static final int MAX_RAW_UTF16_UNITS = 4096;

    private PasswordLengthPolicy() {
    }

    public static String prepareForEnrollment(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Cần nhập mật khẩu.");
        }
        if (raw.length() > MAX_RAW_UTF16_UNITS) {
            throw new IllegalArgumentException("Đầu vào quá lớn.");
        }

        requireValidUtf16(raw);
        String normalized = Normalizer.normalize(raw, Normalizer.Form.NFC);
        int length = normalized.codePointCount(0, normalized.length());

        if (length < MIN_CODE_POINTS || length > MAX_CODE_POINTS) {
            throw new IllegalArgumentException(
                    "Mật khẩu cần dài từ 15 đến 128 ký tự Unicode sau NFC.");
        }
        return normalized;
    }

    private static void requireValidUtf16(String value) {
        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);
            if (Character.isHighSurrogate(current)) {
                if (i + 1 >= value.length()
                        || !Character.isLowSurrogate(value.charAt(i + 1))) {
                    throw new IllegalArgumentException("Unicode không hợp lệ.");
                }
                i++;
            } else if (Character.isLowSurrogate(current)) {
                throw new IllegalArgumentException("Unicode không hợp lệ.");
            }
        }
    }
}
```

Giá trị trả về là đầu vào đã chuẩn bị để các bước tiếp theo kiểm tra và hash; không phải dữ liệu được phép lưu dưới dạng plaintext. Hàm cũng chưa thực hiện kiểm tra mật khẩu phổ biến hoặc đã lộ, giới hạn tần suất, MFA hay quản lý phiên.

Kiểm tra surrogate giúp tránh tình huống bộ mã hóa thay dữ liệu Unicode lỗi bằng ký tự thay thế, làm bí mật thực tế khác với đầu vào ban đầu. Ở biên HTTP/JSON cũng cần xác định cách từ chối dữ liệu mã hóa sai; helper này chỉ xử lý `String` đã được ứng dụng nhận.

Hằng số 4096 giới hạn lượng dữ liệu mà helper tiếp tục xử lý; nó không thay thế giới hạn request ở gateway hoặc server. Ví dụ cũng giả định đường hash tiếp theo có thể xử lý đầy đủ các mật khẩu được chấp nhận.

### Vì sao không dùng cùng hàm này cho mọi lần đăng nhập?

Giả sử một tài khoản cũ được tạo khi policy cho phép 10 ký tự. Sau đó dịch vụ tăng mức tối thiểu lên 15. Nếu endpoint đăng nhập gọi `prepareForEnrollment()`, người dùng có thể bị từ chối trước cả khi hệ thống xác minh bí mật đang có.

Hai mục đích cần được triển khai rõ:

| Thao tác | Cách áp dụng độ dài |
| --- | --- |
| Đăng ký, đặt hoặc đổi mật khẩu | Áp dụng policy thiết lập hiện hành trước khi lưu credential mới |
| Đăng nhập bằng credential đã tồn tại | Xử lý theo quy tắc biểu diễn và thuật toán của credential đó rồi xác minh; không mặc nhiên dùng minimum mới |
| Nâng policy cho tài khoản cũ | Quy định việc chuyển đổi sau khi xác minh thành công hoặc qua luồng phục hồi được kiểm soát |

Nếu dữ liệu cũ chưa dùng NFC, không nên chuẩn hóa đầu vào mới rồi so với hash cũ một cách đồng loạt. Có thể cần metadata phiên bản xử lý để biết credential nào được tạo với quy tắc nào. Chỉ đổi quy tắc sau một luồng xác minh/chuyển đổi hợp lệ; không thể tính lại hash mật khẩu mới từ hash cũ khi không có bí mật gốc.

## 6. Trải nghiệm người dùng phải hỗ trợ chính sách

Một thông báo có ích là: “Dùng từ 15 đến 128 ký tự. Bạn có thể dùng khoảng trắng và trình quản lý mật khẩu.” Nếu hệ thống đếm theo NFC và code point, bộ đếm giao diện cũng cần phản ánh cùng cách tính.

OWASP khuyến nghị hỗ trợ trình quản lý mật khẩu và cho phép dán vào trường mật khẩu. Điều này giúp người dùng sử dụng bí mật do công cụ tạo thay vì phải gõ lại từng ký tự. [Nguồn: OWASP Authentication Cheat Sheet — Password Managers](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#password-managers)

Độ dài là một điều kiện chấp nhận, không phải chứng nhận “an toàn tuyệt đối”. Trên form tạo mật khẩu, có thể phân biệt thông báo “chưa đủ độ dài” với thông báo “mật khẩu này quá phổ biến”. NIST yêu cầu đối chiếu toàn bộ mật khẩu dự kiến với danh sách chặn khi thiết lập hoặc thay đổi mật khẩu. [Nguồn: NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

Không ghi nguyên mật khẩu vào log để điều tra lỗi đếm ký tự. Có thể ghi mã lỗi, phiên bản policy và thông tin tổng hợp cần thiết để vận hành. Nếu form báo đủ độ dài nhưng server từ chối, hãy tái hiện bằng dữ liệu giả cùng kiểu Unicode, thay vì yêu cầu người dùng gửi bí mật thật.

## 7. Tình huống áp dụng trong một hệ thống IAM

Một công ty có cổng nhân viên, ứng dụng di động và dịch vụ xác thực tập trung. Cổng web đã bật MFA, nhưng ứng dụng di động cũ vẫn có thể nhận token bằng mật khẩu đơn lẻ.

Nhóm phát triển định giảm minimum cho toàn bộ tài khoản vì “hệ thống đã có MFA”. Khi đối chiếu các đường cấp phiên, họ phát hiện nhận định đó chưa đúng với ứng dụng cũ. Quyết định về độ dài phải dựa trên cách credential thực sự được sử dụng, không chỉ trạng thái hiển thị trên cổng web.

Nhóm chọn mức tối thiểu chung 15 code point cho mật khẩu mới và tối đa 128. Khi kiểm tra tương thích, họ phát hiện backend cũ giới hạn 72 byte ở bước hash. Như vậy, trước khi công bố policy mới, họ phải giải quyết đường hash và kế hoạch chuyển credential. Giao diện chấp nhận 128 ký tự không đủ để kết luận backend hỗ trợ policy.

Đối với đăng nhập SSO qua một nhà cung cấp danh tính (IdP), mật khẩu do IdP quản lý không được gửi về ứng dụng sử dụng SSO để kiểm tra độ dài lại. Ứng dụng cần xác định nơi sở hữu chính sách credential. Nếu vẫn giữ tài khoản local để dự phòng, đường đăng nhập local là một phạm vi cần quản lý riêng.

Tình huống này liên kết ba vấn đề của IAM: nơi quản lý danh tính, các cách xác thực có thể cấp phiên, và khả năng thực thi chính sách của từng thành phần.

## 8. Các ca kiểm tra có ý nghĩa

Bảng dưới là tập dữ liệu minh họa để kiểm tra thiết kế ở mục 5. “Qua kiểm tra độ dài” không có nghĩa là được phép dùng làm mật khẩu thật; các bước kiểm tra khác vẫn có thể từ chối.

| Đầu vào hoặc tình huống | Kết quả mong đợi | Lỗi có thể phát hiện |
| --- | --- | --- |
| `"a".repeat(14)` | Từ chối vì quá ngắn | Sai biên tối thiểu |
| `"a".repeat(15)` | Qua riêng kiểm tra độ dài | Nhầm tối thiểu 15 thành lớn hơn 15 |
| `"a".repeat(128)` | Qua riêng kiểm tra độ dài | Sai biên tối đa |
| `"a".repeat(129)` | Từ chối, không cắt còn 128 | Cắt ngầm dữ liệu |
| `"😀".repeat(8)` | Từ chối: 8 code point dù có 16 code unit | Dùng `String.length()` cho policy |
| `"e\u0301".repeat(15)` | NFC thành 15 code point `é`; qua riêng kiểm tra độ dài | Đếm khác thời điểm chuẩn hóa |
| Có khoảng trắng đầu hoặc cuối | Xử lý theo policy đã công bố, không tự `trim()` | Biến đổi bí mật ngoài dự kiến |
| Hai đầu vào chỉ khác phần đuôi | Chỉ đúng bí mật đã đặt mới xác minh thành công | Giới hạn ngầm ở client, API hoặc thư viện hash |
| Surrogate đứng một mình, như `"\uD800"` | Từ chối Unicode không hợp lệ | Mã hóa thay thế làm đổi đầu vào |
| Mật khẩu đúng của tài khoản cũ ngắn hơn minimum mới | Xử lý theo kế hoạch chuyển đổi, không chặn bởi hàm enrollment | Áp policy mới sai giai đoạn |

Một kiểm tra tích hợp quan trọng là đặt mật khẩu có phần đuôi riêng biệt, sau đó thử đăng nhập bằng chuỗi giống tiền tố nhưng khác phần đuôi. Phép thử này cần đi qua đúng đường hash và xác minh thật của ứng dụng. Chỉ kiểm tra form hoặc hàm đếm ký tự sẽ không phát hiện được việc thư viện bỏ phần cuối.

## 9. Những điểm cần ghi nhớ

Độ dài có tác dụng khi phần tăng thêm tạo ra tính khó đoán và được hệ thống xác minh đầy đủ. Chính sách phải có cùng ý nghĩa ở giao diện, API, xử lý Unicode và bước hash.

Khi triển khai trong IAM, cần biết credential thuộc về hệ thống nào, những đường nào có thể cấp phiên và cách chuyển đổi tài khoản cũ. Việc nâng minimum là thay đổi vòng đời credential, không chỉ là sửa một con số trong biểu mẫu.

## Tài liệu tham khảo

- [NIST SP 800-63B-4 — Authentication and Authenticator Management, mục Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
