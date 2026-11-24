# Enumeration security test cho luồng khôi phục tài khoản

## 1. Kiểm thử đang tìm loại rò rỉ nào?

**Account enumeration** xảy ra khi người chưa có quyền biết một thông tin có thể suy ra tài khoản tồn tại, thuộc một tenant hoặc có một trạng thái bảo mật nào đó bằng cách quan sát hệ thống. Luồng khôi phục thường dễ bị dùng cho mục đích này vì người gọi có thể bắt đầu khi chưa đăng nhập.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, người dùng có thể mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Một endpoint khôi phục không nên vô tình cung cấp danh sách người dùng, phương thức xác thực đã đăng ký hoặc địa chỉ khôi phục của họ trước khi người gọi đạt điều kiện được xem thông tin đó.

Ví dụ, cùng một API trả “Đã gửi hướng dẫn” cho tài khoản tồn tại nhưng “Không tìm thấy email” cho tài khoản không tồn tại. Đây là rò rỉ trực tiếp. Nếu hai nhánh cùng trả một câu nhưng có HTTP status, cookie hoặc thời gian khác nhau ổn định, vẫn có thể hình thành một kênh phân biệt.

[OWASP WSTG-IDNT-04](https://github.com/OWASP/wstg/blob/v4.2/document/4-Web_Application_Security_Testing/03-Identity_Management_Testing/04-Testing_for_Account_Enumeration_and_Guessable_User_Account.md) mô tả việc kiểm tra enumeration qua phản hồi, điều hướng và thời gian. Bài học này áp dụng mục tiêu đó vào một kế hoạch kiểm thử khôi phục có fixture, ranh giới quyền và tiêu chí kết luận cụ thể.

Đây là kiểm thử về **thông tin người gọi quan sát được**, không chỉ là kiểm tra câu chữ trong một thông báo. Kết quả cần trả lời được: trước khi chứng minh quyền với tài khoản, người gọi có phân biệt được các nhóm cần giữ kín bằng những dấu hiệu lặp lại hay không?

## 2. Xác định điều cần giữ kín và người được phép biết

Không thể đặt một kỳ vọng chung rằng mọi phản hồi ở mọi bước đều giống nhau. Người đã chứng minh quyền với một tài khoản có thể cần thông tin để hoàn tất khôi phục, trong khi một người lạ chỉ biết email không nên nhận cùng mức chi tiết.

| Ngữ cảnh người gọi | Ví dụ thông tin có thể hợp lệ | Thông tin cần xem xét giữ kín |
| --- | --- | --- |
| Chưa xác thực, chỉ nhập định danh | Hướng dẫn công khai và lỗi định dạng đầu vào | Tài khoản có tồn tại hoặc thuộc tenant nào |
| Có một mã theo dõi công khai chưa đủ bằng chứng | Trạng thái tiếp nhận tối thiểu theo contract | Kênh gửi thật, số điện thoại, MFA hoặc passkey của tài khoản |
| Đã trình bằng chứng hợp lệ cho một bước | Thông tin cần cho đúng bước đã được cấp quyền | Membership khác hoặc khả năng reset ngoài phạm vi bằng chứng |
| Nhân viên hỗ trợ được phân công | Phần hồ sơ đúng nhiệm vụ và tenant | Danh tính hoặc hồ sơ của tenant khác |
| Người dùng đã đăng nhập và xác thực tăng cường | Các thiết lập của chính tài khoản theo policy | Thông tin người dùng khác chỉ vì biết định danh của họ |

Một kế hoạch kiểm thử nên viết giả thuyết trước khi chạy:

```text
Với người gọi chưa chứng minh quyền sở hữu,
hai định danh hợp lệ về cú pháp và cùng ngữ cảnh công khai,
khác nhau ở việc có tài khoản đủ điều kiện khôi phục hay không,
không được tạo ra tín hiệu phân biệt ngoài phần disclosure đã được chấp nhận.
```

“Cùng ngữ cảnh công khai” bao gồm loại endpoint, tenant đang truy cập, ngôn ngữ, trạng thái phiên, mức giới hạn tốc độ và cấu trúc đầu vào. Không so một email sai cú pháp với một email hợp lệ rồi coi mọi khác biệt là enumeration.

Nếu sản phẩm chủ ý công khai một danh bạ thành viên hoặc tên nhà cung cấp SSO của tổ chức, cần ghi rõ dữ liệu nào đã công khai. Việc đó không mặc nhiên cho phép tiết lộ tài khoản cụ thể có đăng ký MFA hay có membership trong một tổ chức nhạy cảm.

## 3. Chuẩn bị fixture có nhãn đúng

Kiểm thử so sánh cần biết chắc trạng thái của dữ liệu. Một email đoán là không tồn tại có thể thực ra thuộc tài khoản cũ, alias hoặc principal được liên kết, làm kết luận sai.

Trong môi trường kiểm thử được quản lý, có thể chuẩn bị các nhóm sau:

| Fixture | Trạng thái đã xác nhận | Mục đích so sánh |
| --- | --- | --- |
| E1 | Tài khoản hoạt động, có kênh khôi phục hợp lệ | Nhóm tồn tại cơ bản |
| N1 | Không có tài khoản sau cùng quy tắc tra cứu | Nhóm không tồn tại cơ bản |
| E2 | Có tài khoản nhưng chưa xác minh email | Rò rỉ trạng thái xác minh |
| E3 | Có tài khoản bị vô hiệu hóa hoặc đang chờ xử lý | Rò rỉ trạng thái quản trị |
| E4 | Tài khoản do nhà cung cấp danh tính bên ngoài quản lý | Rò rỉ loại danh tính hoặc phương thức đăng nhập |
| E5 | Tài khoản có MFA hoặc passkey | Rò rỉ phương thức bảo mật |
| T1 | Có membership ở tenant A, không có ở B | Rò rỉ membership xuyên tenant |
| R1 | Tài khoản đang có luồng khôi phục hoặc cooldown | Rò rỉ hoạt động khôi phục đang diễn ra |

Tên fixture chỉ là nhãn nội bộ của bài học. Không đưa nhãn như `E1`, `exists=true` hoặc trạng thái fixture vào phản hồi công khai của hệ thống thật.

Một cặp định danh mẫu:

```text
member01@recovery-fixture.test   -> tồn tại trong fixture
absent01@recovery-fixture.test   -> không tồn tại trong fixture
```

Hai địa chỉ có cấu trúc và độ dài giống nhau để giảm nhiễu ở bước đầu. Cần nhiều fixture độc lập trong mỗi nhóm để tránh kết luận dựa vào cache, shard hoặc một tài khoản có cấu hình đặc biệt.

Môi trường nên dùng mail sink, SMS sandbox và dữ liệu danh tính giả được quản lý. Kế hoạch xác định ngân sách yêu cầu, mức đồng thời, quyền reset fixture và ngưỡng dừng khi hệ thống bất thường. Đây là điều kiện để kết quả phản ánh hành vi bảo mật thay vì tác dụng phụ do tạo quá nhiều email hoặc làm cạn quota.

## 4. Lập bản đồ toàn bộ bề mặt khôi phục

Chỉ kiểm thử trang “quên mật khẩu” chưa đủ. Một bước sau có thể tiết lộ kết quả mà bước đầu đã che.

| Bề mặt | Ví dụ câu hỏi kiểm thử |
| --- | --- |
| Bắt đầu khôi phục mật khẩu | HTTP status hoặc nội dung có khác theo tồn tại tài khoản không? |
| Bắt đầu khôi phục MFA hoặc passkey | Có trả danh sách yếu tố chỉ khi tài khoản tồn tại không? |
| Chọn phương thức khôi phục | Có lộ số điện thoại, email che một phần hoặc loại kênh quá sớm không? |
| Gửi lại challenge | Cooldown, bộ đếm hoặc `Retry-After` có tiết lộ trạng thái tài khoản không? |
| Kiểm tra mã hoặc token sai | Có phân biệt “không có tài khoản” với “mã sai” trước khi đủ quyền không? |
| Poll trạng thái luồng | ID trả từ bước đầu có cho phép phân biệt luồng thật với nhánh không tồn tại không? |
| Hủy hoặc tiếp tục luồng | Có thông báo khác nhau làm lộ hồ sơ đã tồn tại không? |
| Tra cứu hỗ trợ | Nhân viên hoặc client ít quyền có dò được tài khoản ngoài phạm vi không? |
| Web, mobile, API cũ và giao diện khác ngôn ngữ | Có một đường cũ trả lỗi chi tiết hơn các đường còn lại không? |

Một response chung ở `/recovery/start` không đạt mục tiêu nếu `/recovery/status/{id}` sau đó trả `ACCOUNT_NOT_FOUND` cho cùng người gọi. Cần kiểm tra chuỗi thao tác bằng cùng mức quyền, không chỉ từng request riêng lẻ.

Token hợp lệ mà người kiểm thử lấy từ mail sink của fixture là bằng chứng ở một mức khác. Những thông tin chỉ xuất hiện sau bằng chứng đó phải được đánh giá theo quyền mới; không trộn chúng với tập quan sát của người lạ chỉ biết email.

## 5. Định nghĩa những gì cần thu thập

Mỗi lần gọi nên giữ bản quan sát đầy đủ trong kho bằng chứng được phân quyền, sau đó tạo một biểu diễn dùng cho so sánh. Tránh bỏ dữ liệu ngay từ lúc thu thập chỉ vì nghĩ rằng trường đó không quan trọng.

| Thành phần | Dấu hiệu có thể làm lộ thông tin |
| --- | --- |
| HTTP status | Một nhóm nhận 202, nhóm khác nhận 404 hoặc 409 |
| JSON hoặc HTML | Mã lỗi, field thừa, giá trị boolean, title hoặc thông báo khác nhau |
| Header | `Location`, `Retry-After`, cache header hoặc header debug khác nhánh |
| Cookie | Chỉ nhóm tồn tại được tạo cookie hay một loại session khác |
| Điều hướng | Chuỗi 302 dẫn tới trang khác nhau, query string chứa loại lỗi |
| Kích thước | Độ dài body, cấu trúc cookie hoặc payload có tương quan với nhóm |
| Thời gian | Nhánh tồn tại phải đợi gửi email, nhánh không tồn tại trả ngay |
| Bước kế tiếp | Poll, resend hoặc chọn kênh làm lộ kết quả tra cứu |
| Tín hiệu trình duyệt | Giao diện che thông báo nhưng API hoặc luồng tải tài nguyên vẫn khác |

Header ngày giờ và request ID thường thay đổi độc lập giữa mọi request. Có thể đối chiếu chúng bằng quy tắc định dạng và cách xuất hiện thay vì đòi giá trị bằng nhau. Tuy nhiên, không xóa một trường khỏi phân tích chỉ vì nó có tên `requestId`: ID có thể mang prefix hoặc độ dài khác nhau giữa nhánh thật và nhánh giả.

Khi chuẩn hóa JSON, chỉ bỏ hoặc biến đổi những field đã được contract xác nhận là biến thiên không mang ý nghĩa nhạy cảm. Giữ nguyên và báo mọi field mới chưa được chấp nhận. Một bộ so sánh bỏ tất cả field lạ có thể vô tình che chính lỗi `accountExists` vừa được thêm.

## 6. Ví dụ kiểm thử khác biệt phản hồi trực tiếp

Giả sử API minh họa nhận:

```http
POST /api/recovery/start HTTP/1.1
Host: recovery.staging.example.test
Content-Type: application/json
Accept-Language: vi

{"identifier":"member01@recovery-fixture.test","purpose":"PASSWORD_RESET"}
```

Request thứ hai giữ cùng ngữ cảnh, thay định danh bằng fixture `absent01@recovery-fixture.test`. Không đưa field `accountExists` vào request; nhãn tồn tại chỉ thuộc dữ liệu kiểm thử.

Một contract phản hồi công khai minh họa cho cả hai nhánh:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{"code":"RECOVERY_REQUEST_ACCEPTED","message":"Nếu yêu cầu phù hợp, hướng dẫn sẽ được gửi qua kênh đã đăng ký."}
```

202 ở đây mô tả việc tiếp nhận yêu cầu theo contract, không khẳng định tài khoản tồn tại hoặc email đã được gửi. Sản phẩm khác có thể chọn một status phù hợp khác; kiểm thử cần bám contract đã thống nhất.

Những khác biệt minh họa phải được phát hiện:

| Nhóm tồn tại | Nhóm không tồn tại | Kết luận |
| --- | --- | --- |
| 202 | 404 | Lộ qua status dù body giống nhau |
| Có `recoveryMethods: ["SMS"]` | Không có field đó | Lộ qua cấu trúc và loại phương thức |
| Có cookie `recovery_context` | Không có cookie | Cần điều tra tín hiệu phân biệt qua cookie |
| `Retry-After: 60` | Không có header | Có thể lộ cooldown chỉ áp dụng sau khi tìm thấy tài khoản |
| Redirect tới trang nhập mã | Redirect tới trang trợ giúp | Lộ qua chuỗi điều hướng |
| Cùng body công khai | Cùng body công khai | Chưa đủ kết luận nếu chưa kiểm tra các kênh khác |

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị thông báo phản hồi nhất quán và tránh chênh lệch thời gian làm lộ tài khoản. Response và ma trận fixture trong bài là ví dụ thiết kế để kiểm tra mục tiêu đó, không phải một schema do OWASP quy định.

## 7. Mã Java minh họa một kiểm tra contract hẹp

Đoạn mã sau kiểm tra một response đã được adapter kiểm thử thu thập. Nó dùng các kiểu Java cơ bản, không gửi request và không đại diện cho một bộ kiểm thử enumeration hoàn chỉnh.

```java
import java.util.Objects;

record StartRecoveryObservation(
        int status,
        String mediaType,
        String cacheControl,
        String body,
        boolean hasSetCookie,
        String location,
        String retryAfter) {
}

final class PublicRecoveryContract {
    private static final String EXPECTED_BODY =
            "{\"code\":\"RECOVERY_REQUEST_ACCEPTED\","
            + "\"message\":\"Nếu yêu cầu phù hợp, hướng dẫn sẽ được gửi "
            + "qua kênh đã đăng ký.\"}";

    static void requireBaseline(StartRecoveryObservation observation) {
        Objects.requireNonNull(observation, "observation");

        if (observation.status() != 202
                || !"application/json".equals(observation.mediaType())
                || !"no-store".equals(observation.cacheControl())
                || !EXPECTED_BODY.equals(observation.body())
                || observation.hasSetCookie()
                || observation.location() != null
                || observation.retryAfter() != null) {
            throw new AssertionError("Public recovery contract differs");
        }
    }
}
```

Contract của ví dụ chọn không tạo cookie, không redirect và không có `Retry-After` trong kịch bản baseline chưa bị giới hạn. Một hệ thống có cookie chống lạm dụng hoặc một contract khác cần kiểm tra đúng đặc tính của nó; không sao chép những điều kiện này thành quy tắc phổ quát.

Adapter cần đọc response trước khi tự theo redirect và thu thập toàn bộ header, cookie cùng timing riêng. `mediaType` trong ví dụ là loại nội dung đã được phân tích từ header, không phải chuỗi header thô có thể chứa tham số charset.

Việc so body nguyên văn giúp ví dụ dễ thấy field thừa, nhưng có thể quá chặt với JSON hợp lệ khác khoảng trắng hoặc thứ tự thuộc tính. Bộ kiểm thử thực tế có thể parse JSON và kiểm schema đóng, giữ đủ bằng chứng thô để điều tra những khác biệt đó.

Gọi kiểm tra baseline cho cả E1 và N1 chỉ xác nhận các thuộc tính đã liệt kê trong kịch bản này. Nó không kiểm tra thời gian, toàn bộ cookie attribute, bước tiếp theo hoặc hiệu lực của rate limiter. Một kết quả PASS ở đây không được đặt tên là “không thể enumeration”.
