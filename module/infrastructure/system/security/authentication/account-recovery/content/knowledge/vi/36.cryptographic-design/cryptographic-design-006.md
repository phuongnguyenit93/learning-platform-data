# Constant time comparison — So sánh hạn chế rò rỉ qua thời gian

Khi kiểm tra recovery token, máy chủ thường cần so sánh một giá trị tính từ secret người dùng gửi với dữ liệu xác minh đã lưu. Nếu phép so sánh dừng ngay tại byte khác đầu tiên, lượng công việc có thể phụ thuộc vào phần dữ liệu đã khớp.

Một người gửi nhiều request có thể tìm cách khai thác khác biệt thời gian ấy để suy đoán thông tin về bí mật. Nhiễu mạng làm việc quan sát khó hơn, nhưng không phải một bảo đảm rằng khác biệt có thể khai thác đã biến mất.

**Constant time comparison** hướng tới việc không để thời gian của phép so sánh tiết lộ nội dung bí mật hoặc vị trí khác nhau, trong những giả định về đầu vào và môi trường đã xác định. Trong account recovery, đây là một lớp bảo vệ cho bước xác minh secret; nó phải đi cùng token đủ mạnh, hạn dùng, dùng một lần, đúng ngữ cảnh và chống lạm dụng.

Các ví dụ dưới đây là minh họa thiết kế. Chúng không khẳng định toàn bộ request có thời gian cố định, và không phải một triển khai recovery hoàn chỉnh.

## 1. Rò rỉ xuất hiện ở phép so sánh như thế nào?

Xét một cách so sánh byte đơn giản:

```java
// Ví dụ không dùng để so sánh dữ liệu xác minh bí mật.
static boolean earlyExitEquals(byte[] expected, byte[] supplied) {
    if (expected.length != supplied.length) {
        return false;
    }

    for (int i = 0; i < expected.length; i++) {
        if (expected[i] != supplied[i]) {
            return false;
        }
    }

    return true;
}
```

Với hai mảng cùng độ dài:

| Trường hợp | Công việc ở vòng lặp |
| --- | --- |
| Khác ngay byte đầu | Kiểm tra một vị trí rồi thoát |
| Khác ở giữa | Kiểm tra đến vị trí giữa rồi thoát |
| Khác ở byte cuối | Đi gần hết hoặc hết mảng |
| Trùng hoàn toàn | Đi hết mảng |

Nếu sự khác biệt này còn hiện diện sau biên dịch và đủ rõ trong môi trường quan sát, nó có thể làm lộ thông tin về mức độ khớp.

Một lần đo lâu hơn chưa chứng minh có thêm byte đúng. Nhưng một thiết kế bảo mật không nên dựa vào giả định người ngoài chỉ đo được một lần.

### Kết quả cần công khai và thông tin không nên công khai

Máy chủ cuối cùng phải quyết định chấp nhận hay từ chối một bằng chứng. Hai kết quả ấy có thể dẫn tới hành vi khác nhau.

Điều cần tránh ở bước so sánh là công khai thêm những thông tin như “đúng ba byte đầu”, “gần đúng” hoặc “khác tại vị trí cuối”. Token là bằng chứng khớp chính xác, không có mức điểm gần đúng để client tận dụng.

## 2. “Constant time” không có nghĩa mọi lần đều cùng số nano giây

Một hàm có thể xử lý toàn bộ N byte, thay vì dừng theo vị trí khác nhau. Lượng công việc có thể phụ thuộc N nếu N là độ dài công khai được xác định bởi định dạng.

Với tag 32 byte cố định, mục tiêu là việc so sánh không phụ thuộc nội dung của 32 byte ấy. Điều này khác với lời hứa rằng hai lần gọi luôn hoàn tất sau cùng một số chu kỳ hoặc cùng thời gian thực.

Các yếu tố như lịch CPU, JIT, bộ nhớ đệm, garbage collection và tải máy vẫn có thể gây biến động.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Độ phức tạp O(N) | Chi phí tăng theo kích thước đầu vào |
| Không thoát theo byte khác đầu tiên | Loại bỏ một nguồn khác biệt phụ thuộc nội dung |
| Primitive có đặc tính timing được tài liệu mô tả | Có cơ sở để chọn và dùng đúng hàm so sánh |
| Endpoint giảm rò rỉ thời gian | Xem cả tra cứu, tính toán, nhánh lỗi và phản hồi |
| Mỗi request cùng thời gian thực tuyệt đối | Không phải bảo đảm mặc nhiên từ primitive so sánh |

Một vòng lặp có đúng N lượt chưa tự chứng minh cả chương trình chống mọi kênh phụ. Cần phân biệt đặc tính của một thao tác với đặc tính của toàn hệ thống.

## 3. Chọn đúng dữ liệu để so sánh

Trong một mô hình recovery token opaque, client có thể nhận:

```text
selector.secret
```

Ở đây:

- `selector` phục vụ định vị bản ghi theo thiết kế; nó không được coi là bí mật đủ để cấp quyền.
- `secret` là phần bí mật cần chứng minh sở hữu.
- Bản ghi trên server chứa dữ liệu xác minh và các ràng buộc của quyền recovery.

Một thiết kế minh họa có thể dùng secret ngẫu nhiên 32 byte và một HMAC verifier 32 byte. Định dạng và kích thước này là lựa chọn của ví dụ, không phải yêu cầu bắt buộc cho mọi phương thức recovery.

```text
storedVerifier =
    HMAC(serverKey, canonicalBoundMessage(originalSecret, trustedContext))

candidateVerifier =
    HMAC(serverKey, canonicalBoundMessage(submittedSecret, trustedContext))

secretMatches =
    safeCompare(storedVerifier, candidateVerifier)
```

`trustedContext` có thể gồm phiên bản định dạng, tenant, hồ sơ, token record reference và purpose. Giá trị ràng buộc phải được xác định từ ngữ cảnh có thẩm quyền, không do body request tùy ý thay thế.

Việc mã hóa message phải không nhập nhằng: dùng một định dạng có cấu trúc hoặc cách phân định độ dài được xác định. Ghép trực tiếp nhiều chuỗi bằng phép nối có thể tạo ra các tổ hợp trường mang cùng biểu diễn.

### Vì sao ưu tiên so sánh byte cố định?

- Tránh phụ thuộc vào biểu diễn hex hoặc Base64 ở bước so sánh dữ liệu xác minh.
- Có kích thước rõ ràng cho primitive.
- Dễ tách lỗi parse khỏi kết quả khớp secret.
- Không cần so sánh chuỗi secret thô với dữ liệu lưu trong kho.

HMAC là một lựa chọn lưu verifier trong ví dụ. Nó không phải điều kiện bắt buộc để mọi phép so sánh byte có thể được thực hiện an toàn.

## 4. Dùng hàm có hợp đồng phù hợp trong Java

Trong Java, `MessageDigest.isEqual(byte[], byte[])` là API dành cho so sánh digest. Tài liệu Java SE 25 ghi chú rằng khi mảng thứ hai không null và không rỗng, thời gian tính toán phụ thuộc độ dài mảng thứ nhất, không phụ thuộc nội dung hai mảng; các trường hợp null hoặc rỗng có ngoại lệ riêng. Vì vậy, ví dụ này dùng hai mảng không rỗng cùng độ dài đã xác định. [Java SE 25, MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D))

Đây là tham chiếu API cho ví dụ, không khẳng định dự án đang chạy Java 25. Khi triển khai, cần đối chiếu runtime thực tế với tài liệu và đặc tính tương ứng.

Một thành phần chỉ thực hiện phần HMAC và so sánh:

```java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class RecoveryVerifier {
    private static final int TAG_BYTES = 32;
    private static final int MAX_MESSAGE_BYTES = 2048;

    private RecoveryVerifier() {
    }

    public static boolean matches(
            SecretKey verifierKey,
            byte[] canonicalBoundMessage,
            byte[] storedVerifier
    ) throws GeneralSecurityException {

        if (verifierKey == null) {
            throw new IllegalStateException("Verifier key unavailable");
        }

        if (canonicalBoundMessage == null
                || canonicalBoundMessage.length > MAX_MESSAGE_BYTES) {
            throw new IllegalArgumentException("Invalid verifier input");
        }

        if (storedVerifier == null
                || storedVerifier.length != TAG_BYTES) {
            throw new IllegalStateException("Invalid stored verifier");
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(verifierKey);

        byte[] candidateVerifier = mac.doFinal(canonicalBoundMessage);

        if (candidateVerifier.length != TAG_BYTES) {
            throw new IllegalStateException("Unexpected verifier length");
        }

        return MessageDigest.isEqual(storedVerifier, candidateVerifier);
    }
}
```

`Mac` cung cấp thao tác MAC, bao gồm cách khởi tạo với khóa và tính kết quả bằng `doFinal`; `HmacSHA256` là một tên thuật toán được tài liệu Java mô tả. [Java SE 25, Mac](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/Mac.html)

Các giới hạn của ví dụ cần được hiểu rõ:

1. Message đã được parse, kiểm tra định dạng và mã hóa theo hợp đồng trước khi gọi.
2. Giới hạn 2048 byte chỉ là ngân sách minh họa cho message có cấu trúc; endpoint còn cần giới hạn kích thước request trước khi cấp phát và giải mã.
3. Khóa được lấy từ cơ chế quản lý khóa, không hardcode trong source.
4. Verifier phải được lưu và đọc nguyên byte theo định dạng đã chọn.
5. Ví dụ tạo đối tượng `Mac` cục bộ; không giả định có thể dùng chung một đối tượng có trạng thái giữa các request đồng thời.
6. Kết quả `true` chỉ nói dữ liệu xác minh khớp; nó chưa cho phép thay đổi tài khoản.

Nếu khóa hoặc verifier trong kho không hợp lệ, đó là vấn đề khả năng xác minh hoặc dữ liệu hệ thống. Tầng API cần xử lý an toàn; không được đổi exception thành `true`, và không nên quy mọi lỗi ấy thành người dùng nhập sai secret.

## 5. Kiểm tra độ dài có làm mất ý nghĩa constant time không?

Độ dài công khai của định dạng có thể được kiểm tra trước. Ví dụ, endpoint đã quy định secret sau giải mã là 32 byte thì chuỗi chỉ giải mã được 5 byte là đầu vào không đúng hợp đồng.

Việc từ chối một đầu vào quá lớn hoặc sai cấu trúc không tự làm lộ byte nào của verifier bí mật. Nó bảo vệ tài nguyên và làm rõ miền đầu vào mà hàm xác minh chấp nhận.

Tuy nhiên, nếu độ dài của chính bí mật cần được che giấu mà chương trình trả sớm theo độ dài ấy, cần một thiết kế khác. Không được dùng một khẩu hiệu “kiểm tra length luôn an toàn” cho mọi giao thức.

Trong ví dụ:

| Dữ liệu | Cách xử lý |
| --- | --- |
| Request vượt giới hạn công khai | Chặn trước khi thực hiện công việc tốn tài nguyên |
| Secret sai encoding | Từ chối theo hợp đồng parse |
| Secret đúng định dạng nhưng sai nội dung | Tạo candidate verifier rồi so sánh bằng primitive phù hợp |
| Verifier trong kho không đúng 32 byte | Xử lý lỗi dữ liệu có kiểm soát; không cắt hoặc đệm để tiếp tục |
| Tag có độ dài khác do cấu hình hoặc provider bất thường | Không cấp quyền; xử lý lỗi kỹ thuật |

### Không sửa token để làm phép so sánh “dễ hơn”

Không cắt bớt secret, tự thêm byte, so sánh một tiền tố hoặc tự đổi chữ hoa thành chữ thường khi định dạng không cho phép.

Với Base64url hoặc mã người dùng nhập, quy tắc biểu diễn và chuẩn hóa phải được xác định ngay từ đầu. Các thành phần phát hành, phân phối và xác minh phải dùng cùng hợp đồng.

Một primitive tốt vẫn có thể được dùng sai nếu chỉ nhận 8 byte đầu của verifier 32 byte rồi coi đó là kiểm tra đầy đủ.

## 6. Những cách thay thế dễ tạo cảm giác an toàn giả

### 6.1. Dùng equals thông thường

```java
boolean ok = expectedText.equals(submittedText);
```

Không nên dựa vào `String.equals`, `Arrays.equals` hoặc một toán tử so sánh thông thường như một bảo đảm timing cho dữ liệu xác minh bí mật. Hành vi tối ưu hóa cụ thể có thể thay đổi theo runtime và không thay thế hợp đồng bảo mật cần có.

Một phép so sánh tiện dụng trả về đúng boolean chưa đủ để trở thành primitive phù hợp cho mục tiêu này.

### 6.2. Tự viết một vòng lặp XOR rồi tuyên bố đã chứng minh

Một cách thường gặp là duyệt toàn bộ mảng và OR các kết quả XOR. Ý tưởng giúp hiểu vì sao không dừng theo byte khác đầu tiên.

Nhưng mã nguồn không có nhánh thoát sớm vẫn chưa chứng minh mọi thuộc tính của mã máy sau JIT, cách truy cập bộ nhớ hoặc toàn bộ đường xử lý. Thực thi mật mã trên runtime được quản lý cần dựa vào thành phần phù hợp và những giả định môi trường được xác định.

Vì vậy, ví dụ Java sử dụng API có tài liệu mô tả thay vì cung cấp một primitive tự chế.

### 6.3. Đổi sang so sánh chuỗi hash

Hash secret rồi chuyển digest thành chuỗi hex không làm phép `equals` của chuỗi có bảo đảm mới.

Băm cũng không sửa được các vấn đề khác: mã ngắn vẫn có không gian đoán nhỏ; token sinh yếu vẫn có thể đoán; verifier bị lộ vẫn cần được đánh giá theo cơ chế lưu trữ thực tế.

Nếu dùng digest hoặc MAC, hãy giữ dữ liệu nhị phân có độ dài xác định cho bước so sánh.

### 6.4. Thêm sleep hoặc random delay

Chèn một khoảng chờ có thể thay đổi tín hiệu quan sát, nhưng không loại bỏ nguyên nhân phụ thuộc nội dung. Thêm cùng một độ trễ cho mọi request vẫn giữ phần chênh lệch cũ.

Độ trễ ngẫu nhiên cũng không phải chứng minh chống phân tích thống kê, đồng thời có thể tăng chi phí tài nguyên và làm người dùng thật bị ảnh hưởng.

Không dùng sleep thay cho sửa primitive, giảm khác biệt trong luồng xử lý và chống lạm dụng.

## 7. Constant time comparison chỉ là một đoạn trong endpoint

Một request recovery thường đi qua:

```text
Giới hạn request
    -> parse và kiểm tra định dạng
    -> tra cứu bản ghi
    -> lấy phiên bản khóa
    -> tính candidate verifier
    -> so sánh verifier
    -> kiểm tra quyền và trạng thái hiện tại
    -> thực hiện thay đổi có bảo đảm nhất quán
    -> tạo phản hồi
```

Ngay cả khi bước so sánh phù hợp, các bước khác có thể gây khác biệt lớn.

| Nguồn khác biệt | Ví dụ |
| --- | --- |
| Tra cứu dữ liệu | Không có selector thì trả ngay; có selector thì thực hiện thêm nhiều công việc |
| Cache | Một nhánh hit cache, nhánh kia truy cập kho từ xa |
| Phiên bản khóa | Chỉ bản ghi tồn tại mới gọi một dịch vụ khóa chậm |
| Trạng thái | Lỗi expired và lỗi secret sai đi qua các đường rất khác nhau |
| Công việc phụ | Chỉ một nhánh ghi log đồng bộ hoặc gửi thông báo |
| Phản hồi | Status, redirect, cookie hoặc kích thước body khác nhau |

OWASP lưu ý thông báo chung vẫn có thể đi kèm khác biệt thời gian từ logic xử lý, chẳng hạn trả sớm khi không có tài khoản. Vì vậy cần xem cả luồng xác minh và phản hồi, không chỉ câu chữ lỗi. [OWASP Authentication Cheat Sheet, Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages)

Không cần làm cho luồng thành công và mọi loại request rác thực hiện tất cả công việc giống hệt nhau. Cần xác định những bí mật nào không được suy ra và những nhóm phản hồi nào cần tránh tạo khác biệt hữu ích.

### Lookup theo selector thay vì nhờ cơ sở dữ liệu so secret

Trong mô hình `selector.secret`, ứng dụng có thể đọc bản ghi bằng selector rồi tự xác minh phần secret.

Không nên giả định một câu SQL dùng `WHERE verifier = :candidate` sẽ cung cấp đặc tính so sánh bí mật mong muốn. Cách tra cứu chỉ mục và so sánh của kho dữ liệu không tự có cùng hợp đồng với primitive mật mã được chọn.

Selector cũng có thể để lộ sự tồn tại của một yêu cầu recovery nếu thiết kế phản hồi sai. “Dùng để định vị” không có nghĩa được tự do công khai mọi thông tin liên quan.

## 8. Đường xử lý khi không tìm thấy bản ghi

Một lựa chọn giảm khác biệt ở một số kiến trúc là dùng dữ liệu dummy có cùng hình dạng cho bước tính toán khi selector không tồn tại.

Mô hình logic minh họa:

```text
record = lookupBySelector(selector)
recordFound = record exists

if recordFound:
    verificationInput = buildInput(record, submittedSecret)
    expectedVerifier = record.verifier
    verificationKey = keyForRecord(record)
else:
    verificationInput = buildBoundedDummyInput(submittedSecret)
    expectedVerifier = fixedLengthDummyVerifier
    verificationKey = configuredDummyVerificationKey

secretMatches = verifyWithSamePrimitive(
    verificationKey,
    verificationInput,
    expectedVerifier
)

if not recordFound:
    rejectWithoutGrantingRights()

if not secretMatches:
    rejectWithoutGrantingRights()

continueWithCurrentStateAndPolicyChecks(record)
```

Điều quan trọng là **kết quả dummy không bao giờ được cấp quyền**, kể cả trong trường hợp phép so sánh tình cờ trả `true`.

Đây là một kỹ thuật thiết kế cần đánh giá trong bối cảnh cụ thể, không phải bằng chứng toàn endpoint đã có thời gian giống nhau. Tra cứu, chọn khóa và cache vẫn có thể khác.

Không cho client tùy chọn key ID khiến máy chủ thử không giới hạn mọi khóa. Không tạo một đường dummy tốn tài nguyên không giới hạn để phục vụ request rác.

Nếu phụ thuộc không sẵn sàng, cần giữ ý nghĩa “chưa xác minh được” và không cấp quyền; không dùng dữ liệu dummy để giả vờ rằng hệ thống đã kiểm tra trạng thái có thẩm quyền.

## 9. Phối hợp với hạn dùng, dùng một lần và kiểm soát phạm vi

Một comparator trả `true` chỉ là một điều kiện:

```text
Có thể thực hiện hành động =
    bằng chứng secret khớp
    và đúng tenant, tài khoản, hồ sơ, purpose
    và binding cần thiết hợp lệ
    và token chưa hết hạn
    và token chưa bị dùng hoặc thu hồi
    và các bằng chứng recovery khác đáp ứng policy
```

Các điều kiện có thể cần thứ tự xử lý riêng tùy kiến trúc và mục tiêu giảm rò rỉ. Không phải mọi phép kiểm tra đều có thể hoặc cần được biến thành cùng một comparator.

OWASP khuyến nghị token đặt lại mật khẩu được tạo an toàn, đủ khó đoán, lưu an toàn, dùng một lần và có hạn dùng phù hợp; chức năng yêu cầu recovery cũng cần phản hồi nhất quán và chống yêu cầu tự động quá mức. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Nếu token hợp lệ nhưng hai request hoàn tất đồng thời, comparator không ngăn cả hai nhận cùng kết quả `true`. Cơ chế tiêu thụ quyền phải được gắn với thay đổi nghiệp vụ bằng transaction hoặc cơ chế nhất quán tương đương.

Tương tự, token đặt lại mật khẩu không tự có quyền gỡ MFA hoặc đăng ký passkey mới. So sánh được thực hiện an toàn không mở rộng purpose.

### Áp dụng đúng cho các loại bằng chứng khác

- Với mật khẩu, dùng hàm verify của cơ chế lưu mật khẩu phù hợp; không thay bằng một hash nhanh chỉ để tiện có mảng 32 byte.
- Với OTP hoặc recovery code ngắn, độ mạnh và giới hạn thử vẫn là vấn đề riêng.
- Với chữ ký, JWT hoặc assertion của passkey, dùng thành phần xác minh giao thức phù hợp; so sánh byte đơn thuần không thay việc kiểm chữ ký và các ràng buộc cần thiết.
- Với token hoặc grant đã hết hiệu lực, khớp verifier không làm quyền sống lại.

## 10. Đánh giá timing cần mô hình quan sát rõ ràng

Khi triển khai một hệ thống thật, câu hỏi đánh giá không phải chỉ là “hai request có cùng thời gian không”, mà là:

- Người quan sát biết và điều khiển những đầu vào nào?
- Họ đo từ xa, từ cùng mạng hay từ môi trường gần tiến trình?
- Họ có thể lấy bao nhiêu mẫu trước khi bị giới hạn?
- Khác biệt đang phụ thuộc nội dung secret, độ dài công khai hay trạng thái nghiệp vụ?
- Các đường lỗi và phụ thuộc có tạo ra tín hiệu mạnh hơn comparator không?

Một phép đo thủ công bằng `System.nanoTime()` trong một vòng lặp nhỏ không đủ để chứng minh an toàn. JIT warm-up, tối ưu loại bỏ công việc, cách sử dụng kết quả và tải máy đều có thể làm số đo sai lệch.

Ngay cả đánh giá có kiểm soát cũng cần tách hai mục tiêu:

| Mục tiêu | Điều có thể kết luận |
| --- | --- |
| Đánh giá primitive trên runtime đã chọn | Có hay chưa thấy khác biệt theo các lớp đầu vào được xem xét |
| Đánh giá endpoint trong môi trường triển khai | Có hay chưa thấy tín hiệu từ toàn bộ đường request trong điều kiện đó |

“Chưa phát hiện khác biệt” có phạm vi hẹp hơn “đã chứng minh không tồn tại mọi timing side channel”. Không tạo một ngưỡng nano giây phổ quát rồi dùng nó cho mọi máy và mạng.

Nội dung này mô tả cách lập luận khi triển khai; ví dụ trong bài không kèm số đo hay tuyên bố kết quả thử nghiệm.

## 11. Ví dụ tổng hợp cho endpoint recovery

Giả sử một endpoint nhận selector và secret. Một người gửi bốn loại request:

| Request | Trạng thái xử lý mong muốn |
| --- | --- |
| Secret sai nhưng đúng định dạng | Không cấp quyền; bước so sánh không dừng theo vị trí byte sai |
| Selector không tồn tại | Không cấp quyền; tránh một khác biệt xử lý dễ dùng để dò thông tin theo thiết kế |
| Secret đúng nhưng token bị thu hồi | Không thực hiện hành động |
| Secret đúng và mọi điều kiện hiện tại đều hợp lệ | Thực hiện đúng hành động trong phạm vi được cấp và tiêu thụ quyền nhất quán |

Với request có secret sai, server không trả “sai ký tự thứ 12” hoặc một phần token mong đợi. Với request đúng, server vẫn kiểm purpose, hồ sơ và trạng thái hiện tại trước khi commit.

Nếu lỗi lấy khóa xuất hiện, request không được cấp quyền. Hệ thống ghi lý do vận hành an toàn để xử lý, nhưng không ghi key, token, candidate verifier hoặc giá trị verifier trong kho vào log debug.

Những tham chiếu như request reference hoặc token record reference giúp điều tra khi có căn cứ ánh xạ. Chúng không được trở thành secret thay thế hay quyền đọc hồ sơ.

## 12. Những nguyên tắc cần giữ

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Đã dùng HMAC nên so sánh bằng equals được” | Tính MAC và so sánh MAC là hai bước cần thiết kế đúng |
| “Không return trong loop là chắc chắn constant time” | Mã nguồn chưa đủ chứng minh hành vi trên mọi runtime |
| “isEqual làm cả API có thời gian cố định” | Đặc tính của comparator không bao phủ tra cứu và nghiệp vụ |
| “Đầu vào nào cũng phải xử lý lâu như nhau” | Giới hạn công khai và chống lạm dụng vẫn cần được thực thi |
| “Token khớp là recovery thành công” | Còn hạn dùng, trạng thái, scope, bằng chứng và commit |
| “Sleep ngẫu nhiên giải quyết timing” | Nhiễu không thay thế loại bỏ nguyên nhân rò rỉ |
| “Không đo thấy khác biệt là không có rủi ro” | Kết luận phụ thuộc mô hình quan sát và phạm vi đánh giá |

Một bước so sánh phù hợp giúp tránh tiết lộ nội dung bí mật qua cách tìm byte khác nhau. Để bảo vệ luồng khôi phục tài khoản, cần đặt bước ấy trong một thiết kế có định dạng rõ, dữ liệu xác minh được bảo vệ, đường lỗi được kiểm soát và quyền recovery được cưỡng chế đúng tại thời điểm thực hiện.
