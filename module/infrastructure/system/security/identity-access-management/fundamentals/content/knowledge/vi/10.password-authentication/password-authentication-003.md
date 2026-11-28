# Password complexity — Thiết kế chính sách mật khẩu khó đoán

## 1. Mục tiêu của chính sách mật khẩu trong IAM

Password complexity thường được hiểu là yêu cầu mật khẩu chứa nhiều loại ký tự: chữ hoa, chữ thường, chữ số và ký hiệu. Tuy nhiên, việc vượt qua một bộ quy tắc về hình thức chưa chứng minh rằng mật khẩu khó đoán.

Trong nền tảng quản lý danh tính và quyền truy cập, chính sách mật khẩu bảo vệ một bằng chứng xác thực: bí mật mà người dùng biết. Kẻ tấn công chiếm được bí mật này có thể đăng nhập dưới danh tính của nạn nhân nếu không còn lớp bảo vệ khác. Các quyền mà tài khoản đang nắm giữ quyết định hậu quả tiếp theo.

Sau bài học, người học cần phân biệt được độ phức tạp hình thức, khả năng chống đoán và tính riêng biệt của mật khẩu; lựa chọn chính sách có thể thực thi tại hệ thống IAM; nhận diện những rủi ro mà mật khẩu không giải quyết được.

Phạm vi ở đây là mật khẩu người dùng. Bí mật ứng dụng, khóa API và danh tính workload cần cơ chế cấp phát, lưu trữ và luân chuyển riêng. Không nên dùng quy trình bắt con người nhớ mật khẩu để thiết kế credential cho workload.

## 2. Ba thuộc tính dễ bị đánh đồng

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ minh họa |
| --- | --- | --- |
| Độ phức tạp hình thức | Chuỗi có đáp ứng quy tắc ký tự không? | `CongTy2026!` có nhiều loại ký tự |
| Khả năng chống đoán | Kẻ tấn công phải thử bao nhiêu ứng viên có khả năng cao trước khi tìm ra? | Tên công ty cộng năm và dấu chấm than là một mẫu dễ đưa vào danh sách thử |
| Tính riêng biệt | Mật khẩu có được dùng ở tài khoản hoặc dịch vụ khác không? | Một mật khẩu sinh ngẫu nhiên vẫn gây rủi ro nếu dùng chung cho email và cổng nhân sự |

Các chuỗi được công khai trong bài chỉ dùng để học, không dùng làm mật khẩu thật.

Giả sử giao diện yêu cầu tám ký tự cùng đủ bốn nhóm ký tự. Người dùng có thể chọn tên công ty, viết hoa chữ đầu, thêm năm và dấu `!`. Bộ kiểm tra trả về “hợp lệ”, nhưng kẻ tấn công biết công ty và năm hiện tại có thể ưu tiên chính mẫu này.

Một quy tắc cú pháp kiểm tra được điều kiện của chuỗi. Nó không biết chuỗi vừa xuất hiện trong một vụ rò rỉ, đang được dùng ở dịch vụ khác hay được người dùng đặt theo thông tin cá nhân. Vì vậy, không nên dùng nhãn “đáp ứng complexity” làm kết luận cuối cùng về mức an toàn của tài khoản.

## 3. Xác định đối thủ đang tấn công ở đâu

Chính sách chỉ có ý nghĩa khi gắn với cách mật khẩu bị khai thác.

| Tình huống | Điều kẻ tấn công đang có | Lớp bảo vệ cần phối hợp |
| --- | --- | --- |
| Đoán qua màn hình đăng nhập | Một hoặc nhiều tên tài khoản | Kiểm soát tốc độ, phát hiện hành vi bất thường, MFA |
| Password spraying | Danh sách nhiều tài khoản và một số mật khẩu phổ biến | Phát hiện theo nhiều tài khoản, chặn lựa chọn phổ biến |
| Credential stuffing | Cặp tài khoản và mật khẩu lấy từ dịch vụ khác | Mật khẩu riêng cho từng dịch vụ, MFA, phát hiện đăng nhập rủi ro |
| Đoán ngoại tuyến sau khi lộ cơ sở dữ liệu | Hash mật khẩu và dữ liệu liên quan | Hàm băm mật khẩu thích hợp, salt và bí mật khó đoán |
| Lừa người dùng nhập vào trang giả | Khả năng thuyết phục người dùng tiết lộ bí mật | Phương thức xác thực chống phishing và bảo vệ luồng đăng nhập |

Bảng trên là cách phân tích tình huống cho một hệ thống IAM, không phải mô hình dự báo số lần thử. Ví dụ, giới hạn đăng nhập ở API không can thiệp được vào máy của kẻ tấn công khi họ đã có bản sao hash. Ngược lại, tăng chi phí hàm băm không xử lý việc người dùng tự nhập mật khẩu vào trang giả.

Điểm quan trọng khi thiết kế là tránh giao quá nhiều trách nhiệm cho complexity. Mỗi lớp bảo vệ phải có một nguy cơ cụ thể mà nó làm giảm.

## 4. Độ dài và tính ngẫu nhiên phải được xét cùng nhau

Với một bộ sinh chọn độc lập, đồng đều từ tập `A` ký tự ở mỗi vị trí, mật khẩu dài `L` có không gian lựa chọn:

```text
N = A^L
H = log2(N) = L × log2(A)
```

`H` là entropy tính bằng bit trong mô hình sinh vừa nêu. Chẳng hạn, nếu một bộ sinh chọn 20 ký tự độc lập từ 64 ký tự, ta có `H = 20 × 6 = 120 bit`. Đây là kết quả của giả thiết về bộ sinh, không phải phép chấm điểm mọi chuỗi dài 20 ký tự.

Với một passphrase gồm sáu từ được chọn độc lập, đồng đều từ danh sách 2.048 từ, mô hình cho `H = 6 × 11 = 66 bit`. Nếu con người tự chọn sáu từ thành một câu quen thuộc, giả thiết đồng đều đã mất; không được giữ nguyên con số 66 bit để quảng cáo mức an toàn.

Không gian lý thuyết cũng không trực tiếp cho biết “mất bao nhiêu năm để phá”. Muốn ước lượng thời gian còn cần phân phối thứ tự thử, tốc độ thử trong môi trường cụ thể và cách lưu mật khẩu. Không nên hiển thị một con số thời gian chính xác trên giao diện nếu những giả thiết này chưa được xác định.

Đối với người dùng, hai cách thực hành có thể cân nhắc là dùng trình quản lý mật khẩu để sinh bí mật riêng cho từng tài khoản, hoặc dùng passphrase với quy trình chọn từ ngẫu nhiên rõ ràng khi cần ghi nhớ. Tự kéo dài một mẫu dễ đoán bằng cách lặp lại mẫu đó không tương đương với sinh thêm lựa chọn độc lập.

## 5. Mốc tham chiếu và chính sách triển khai cụ thể

NIST SP 800-63B-4, mục 3.1.1.2, đưa ra các mốc sau: tối thiểu 15 ký tự nếu mật khẩu là yếu tố duy nhất; có thể giảm khi chỉ dùng trong MFA nhưng vẫn tối thiểu 8; nên hỗ trợ độ dài tối đa ít nhất 64; không bắt buộc trộn nhóm ký tự; không ép đổi định kỳ khi thiếu bằng chứng bị xâm phạm. Đây là yêu cầu và khuyến nghị trong phạm vi hướng dẫn NIST, không tự động là nghĩa vụ cho mọi sản phẩm. [Nguồn: NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver).

Để triển khai một cổng nhân sự giả định, nhóm thiết kế chọn chính sách sau. Các giá trị 128 và 15 áp dụng đồng nhất bên dưới là quyết định của ví dụ, không phải một bộ cấu hình bắt buộc cho mọi hệ thống.

| Quyết định của cổng nhân sự | Cách giải thích cho người triển khai |
| --- | --- |
| Tối thiểu 15 code point cho mọi tài khoản | Dùng một ngưỡng thống nhất, kể cả tài khoản đã bật MFA |
| Tối đa 128 code point sau chuẩn hóa | Đặt giới hạn được công bố, thống nhất giữa giao diện, API và thành phần lưu trữ |
| Cho phép khoảng trắng và tiếng Việt | Hỗ trợ passphrase và các bàn phím người dùng thực sự sử dụng |
| Không yêu cầu đủ bốn nhóm ký tự | Không dùng regex thành phần làm bằng chứng về độ mạnh |
| Có danh sách từ chối khi tạo hoặc đổi mật khẩu | Loại các ứng viên phổ biến, đã lộ hoặc dễ đoán theo ngữ cảnh |
| Cho phép dán và tự động điền | Tránh cản trở công cụ sinh và quản lý mật khẩu |

OWASP cũng hướng dẫn dùng blocklist, hỗ trợ công cụ quản lý mật khẩu và không âm thầm cắt ngắn chuỗi nhập. [Nguồn: OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#implement-proper-password-strength-controls).

Nếu một sản phẩm dùng ngưỡng thấp hơn cho tài khoản có MFA, cần xác định toàn bộ đường đăng nhập và khôi phục của tài khoản. Không lấy giá trị `mfaEnabled` từ request của trình duyệt để quyết định chính sách. Một luồng dự phòng chỉ kiểm tra mật khẩu sẽ làm sai giả thiết rằng mật khẩu luôn được dùng cùng yếu tố thứ hai.

## 6. Danh sách từ chối và phản hồi cho người dùng

Trong ví dụ cổng nhân sự, danh sách từ chối gồm các mật khẩu phổ biến, mật khẩu đã biết bị lộ và các ứng viên theo ngữ cảnh như tên dịch vụ ghép năm. Việc kiểm tra diễn ra ở backend khi tạo, đặt lại hoặc đổi mật khẩu.

So khớp cần có hợp đồng rõ ràng. Chẳng hạn, kiểm tra xem toàn bộ mật khẩu đã chuẩn hóa có nằm trong tập bị chặn hay không khác với việc từ chối mọi chuỗi chứa một từ bất kỳ. Nếu chặn tất cả chuỗi chứa tên công ty ở bất cứ vị trí nào, hệ thống có thể loại bỏ cả một passphrase dài mà không có phân tích phù hợp.

Không gửi nguyên mật khẩu đến một dịch vụ chấm điểm bên ngoài. Có thể dùng dữ liệu cục bộ hoặc một giao thức tra cứu riêng tư đã được đánh giá cho mục đích này. Nếu dịch vụ kiểm tra không sẵn sàng, cần có quyết định vận hành rõ: dùng bộ dữ liệu cục bộ đã cập nhật, hoặc tạm hoãn thao tác đổi mật khẩu. Không lặng lẽ coi lỗi kiểm tra là kết quả “không bị lộ”.

Phản hồi ở màn hình đặt mật khẩu nên chỉ ra hành động có thể thực hiện:

```text
Mật khẩu này nằm trong danh sách không được chấp nhận.
Hãy chọn một mật khẩu khác, dài và riêng cho tài khoản này.
Bạn có thể sử dụng trình quản lý mật khẩu để tạo mật khẩu mới.
```

Thông báo này phục vụ luồng chọn mật khẩu, không thay thế thiết kế thông báo đăng nhập chống dò tài khoản. Không kèm lại mật khẩu bị từ chối trong response, log, sự kiện kiểm toán hoặc công cụ theo dõi lỗi.

## 7. Unicode và tính nhất quán giữa các luồng

Đối với tiếng Việt, một ký tự có dấu có thể có nhiều biểu diễn Unicode tương đương. Java cung cấp `Normalizer` để chuyển chuỗi về dạng chuẩn hóa đã chọn; NFC là dạng ghép chuẩn tắc. [Nguồn: Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html).

Ví dụ, hai cách mã hóa sau có thể trông giống nhau trên giao diện:

```text
U+00E9           → é
U+0065 U+0301    → e + dấu sắc kết hợp
```

Trong chính sách của cổng nhân sự, cả hai được chuẩn hóa về NFC trước khi xét độ dài, kiểm tra danh sách từ chối và băm. Cùng quy tắc biểu diễn phải được áp dụng khi xác minh lại mật khẩu. Nếu lúc đăng ký băm NFC nhưng lúc đăng nhập băm nguyên chuỗi nhập, người dùng có thể không đăng nhập được dù nhìn thấy cùng một mật khẩu.

NIST khuyến nghị NFC khi chấp nhận Unicode và quy định tính độ dài theo code point. [Nguồn: NIST, mục Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver).

Trong Java, cần phân biệt `String.length()` tính đơn vị UTF-16 với `codePointCount(...)` tính code point. Một code point ngoài BMP có thể chiếm hai đơn vị UTF-16. Code point cũng chưa chắc tương ứng với một ký tự người dùng nhìn thấy, vì một cụm ký tự có thể gồm nhiều code point.

Không tự gọi `trim()`, chuyển về chữ thường hoặc xóa dấu tiếng Việt đối với mật khẩu. Những thao tác đó làm thay đổi bí mật theo một quy tắc khác với NFC. Giao diện, ứng dụng di động và API phải thống nhất về cách xử lý; dữ liệu nhập cũng cần là Unicode hợp lệ.

Đối với tài khoản đã tồn tại, thay đổi cách chuẩn hóa là một thay đổi định dạng credential. Cần cơ chế phiên bản hoặc quy trình chuyển đổi được kiểm thử, thay vì áp dụng ngay quy tắc mới rồi làm mọi mật khẩu cũ mất hiệu lực.

## 8. Ví dụ Java: kiểm tra khi đặt mật khẩu mới

Đoạn mã dưới minh họa phần kiểm tra chính sách cho cổng nhân sự giả định. Nó nhận một hàm kiểm tra blocklist đã được cấu hình ở phía server. Nó không triển khai băm, truy vấn cơ sở dữ liệu, HTTP hay cơ chế xác thực hoàn chỉnh.

```java
import java.text.Normalizer;
import java.util.Objects;
import java.util.function.Predicate;

public final class EnrollmentPasswordPolicy {
    private static final int MIN_CODE_POINTS = 15;
    private static final int MAX_CODE_POINTS = 128;

    // Giới hạn tài nguyên đầu vào của ví dụ, trước khi chuẩn hóa.
    private static final int MAX_RAW_UTF16_UNITS = 4096;

    private final Predicate<String> isBlocked;

    public EnrollmentPasswordPolicy(Predicate<String> isBlocked) {
        this.isBlocked = Objects.requireNonNull(isBlocked);
    }

    public String validateAndNormalize(String rawPassword) {
        if (rawPassword == null) {
            throw new IllegalArgumentException("PASSWORD_REQUIRED");
        }
        if (rawPassword.length() > MAX_RAW_UTF16_UNITS) {
            throw new IllegalArgumentException("PASSWORD_INPUT_TOO_LARGE");
        }

        String normalized = Normalizer.normalize(
                rawPassword, Normalizer.Form.NFC);
        int length = normalized.codePointCount(0, normalized.length());

        if (length < MIN_CODE_POINTS || length > MAX_CODE_POINTS) {
            throw new IllegalArgumentException("PASSWORD_LENGTH_INVALID");
        }
        if (isBlocked.test(normalized)) {
            throw new IllegalArgumentException("PASSWORD_BLOCKED");
        }
        return normalized;
    }
}
```

Kết quả trả về là bí mật đã chuẩn hóa để chuyển ngay sang thành phần băm mật khẩu. Không đưa nó vào đối tượng có `toString()` tự động, không ghi log và không trả về cho client. Ví dụ dùng `String` để làm rõ xử lý Unicode; `String` bất biến không cung cấp thao tác xóa bộ nhớ tại chỗ, nên phải hạn chế thời gian giữ và số bản sao.

Giới hạn đầu vào thô 4.096 đơn vị UTF-16 và giới hạn nghiệp vụ 128 code point có mục đích khác nhau: một giới hạn bảo vệ chi phí xử lý, một giới hạn quy định mật khẩu được chấp nhận. Cần thêm giới hạn request tại lớp HTTP; không để backend nhận một chuỗi nhiều megabyte rồi mới gọi hàm này.

Hợp đồng của `isBlocked` phải xử lý đúng chuỗi NFC và phân biệt lỗi tra cứu với kết quả không bị chặn. Nếu nó ném lỗi vận hành, lớp ứng dụng cần xử lý như lỗi của thao tác đặt mật khẩu, không chuyển thành “mật khẩu hợp lệ”. Việc kiểm tra theo ngữ cảnh của tài khoản cũng thuộc thành phần server này, không do client tự khai báo kết quả.

Không gọi nguyên hàm kiểm tra đặt mật khẩu mới trong mọi lần đăng nhập. Một tài khoản cũ có thể có credential được tạo theo chính sách trước đây; xác minh credential và yêu cầu nâng cấp chính sách là hai quyết định khác nhau. Khi đăng nhập, dùng cách biểu diễn tương ứng với phiên bản credential, kiểm tra hash và các yếu tố xác thực cần thiết. Nếu cần thay mật khẩu vì sự cố, đưa người dùng vào luồng phục hồi hoặc đổi mật khẩu phù hợp.

## 9. Từ chính sách đến luồng tạo credential

Một luồng đặt mật khẩu có thể tổ chức như sau:

```text
Xác minh quyền tạo hoặc đổi credential
    ↓
Giới hạn request và giải mã Unicode hợp lệ
    ↓
Chuẩn hóa theo phiên bản chính sách
    ↓
Kiểm tra độ dài và danh sách từ chối
    ↓
Băm bằng thành phần lưu mật khẩu đã cấu hình
    ↓
Lưu credential và phiên bản biểu diễn
    ↓
Ghi sự kiện kiểm toán không chứa bí mật
```

Khi đổi mật khẩu, server còn phải xác minh người đang thực hiện có quyền đổi credential của tài khoản đích. Một request có mật khẩu mới rất tốt vẫn là trái phép nếu kẻ tấn công đổi mật khẩu cho tài khoản của người khác.

Về lưu trữ, dùng hàm băm chuyên dụng cho mật khẩu cùng salt riêng; OWASP ưu tiên Argon2id khi phù hợp. Salt không biến một mật khẩu dễ đoán thành mật khẩu mạnh. Với bcrypt, cần chú ý giới hạn đầu vào 72 byte ở nhiều triển khai để tránh cắt mất phần cuối của mật khẩu dài. [Nguồn: OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Sự kiện kiểm toán có thể ghi mã tài khoản nội bộ, thời điểm, loại thao tác, kết quả và phiên bản chính sách. Không cần ghi mật khẩu để chứng minh một thao tác đổi credential đã thành công.

## 10. Các tình huống dùng để kiểm tra thiết kế

Các tình huống dưới đây giúp người triển khai đánh giá tính nhất quán của chính sách, không phải một bộ ước lượng độ mạnh tuyệt đối.

| Tình huống | Kết quả mong đợi với cổng nhân sự trong bài |
| --- | --- |
| Chuỗi 14 code point sau chuẩn hóa | Bị từ chối do độ dài |
| Chuỗi 15 code point, không nằm trong danh sách từ chối | Vượt phần kiểm tra minh họa; chưa có nghĩa là đã xác thực người dùng |
| Chuỗi dài đủ nhưng nằm trong danh sách đã lộ | Bị từ chối khi đặt mật khẩu mới |
| Passphrase có khoảng trắng | Không bị từ chối chỉ vì có khoảng trắng |
| Hai biểu diễn Unicode tương đương theo NFC | Có cùng biểu diễn đầu vào cho bước băm mới |
| Chuỗi 129 code point sau chuẩn hóa | Bị từ chối, không bị cắt còn 128 |
| Trình duyệt bỏ qua kiểm tra giao diện và gửi thẳng API | Backend vẫn thực thi toàn bộ chính sách |
| Tra cứu blocklist gặp lỗi | Không báo thành công dựa trên một kết quả chưa kiểm tra |
| Người dùng dán từ trình quản lý mật khẩu | Giao diện cho phép thao tác |

Thử thêm các đường đi thực tế: đăng ký, đổi mật khẩu, quên mật khẩu, quản trị viên cấp tài khoản và ứng dụng di động. Nếu một đường cho phép tạo mật khẩu mà đường khác không chấp nhận khi xác minh, chính sách chưa được triển khai thống nhất.

## 11. Liên hệ với vòng đời danh tính và quyền truy cập

Ở bước cấp phát tài khoản, người dùng phải có cách thiết lập bí mật mà bên cấp phát không cần biết. Ở bước thay đổi credential, cần kiểm soát quyền thực hiện, xử lý phiên theo chính sách và thông báo phù hợp. Khi có bằng chứng lộ mật khẩu, cần ngăn tiếp tục sử dụng credential bị ảnh hưởng và đánh giá các phiên đang hoạt động; chỉ nâng yêu cầu complexity cho lần đăng ký tiếp theo chưa xử lý được sự cố hiện tại.

Trong mô hình SSO, cần xác định nơi nào thực sự xác minh mật khẩu. Nếu IdP thực hiện xác thực và ứng dụng chỉ nhận kết quả qua OIDC, chính sách mật khẩu chủ yếu nằm tại IdP. Một tài khoản quản trị cục bộ hoặc luồng đăng nhập dự phòng vẫn cần được xét riêng vì nó có thể đi ngoài chính sách SSO.

Mật khẩu mạnh không quyết định người dùng được đọc hồ sơ nào hoặc thực hiện thao tác quản trị nào. Sau xác thực, hệ thống vẫn cần RBAC hoặc ABAC, nguyên tắc ít quyền nhất và quản lý vòng đời quyền. Đối với tài khoản đặc quyền, độ khó đoán của mật khẩu chỉ là một phần của thiết kế còn có MFA, quản lý đặc quyền và kiểm toán.

Khi đánh giá một chính sách password complexity, người học nên giải thích được từng quyết định bằng nguy cơ và luồng thực tế: ai chọn bí mật, ở đâu kiểm tra, dùng biểu diễn nào, lưu thế nào và tài khoản có những đường truy cập nào. Đó là cơ sở để biến một danh sách quy tắc trên giao diện thành một cơ chế bảo vệ credential có thể vận hành trong nền tảng IAM.
