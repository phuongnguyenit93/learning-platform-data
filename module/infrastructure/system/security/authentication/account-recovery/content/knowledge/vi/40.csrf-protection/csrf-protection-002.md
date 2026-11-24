# CSRF token for recovery — Token chống CSRF trong khôi phục tài khoản

## 1. Vì sao luồng recovery vẫn có thể bị CSRF?

Người dùng mất mật khẩu có thể chưa đăng nhập, nhưng trình duyệt vẫn có một phiên tạm để tiếp tục khôi phục. Nếu phiên đó được nhận diện bằng cookie, trình duyệt có thể tự gửi cookie khi thực hiện request tới dịch vụ recovery. Một trang bên ngoài có thể cố khiến trình duyệt gửi một hành động mà người dùng không chủ đích thực hiện.

Ví dụ giả định: người dùng đã vượt qua bước xác minh và đang có phiên được phép đặt lại mật khẩu. Endpoint nhận mật khẩu mới chỉ dựa vào cookie recovery, không có cơ chế chống request giả mạo phù hợp. Một trang do kẻ tấn công kiểm soát có thể tìm cách gửi mật khẩu do họ lựa chọn tới endpoint đó. Cuộc tấn công có thành công hay không còn phụ thuộc cơ chế cookie, phương thức, định dạng request và các kiểm soát server đang áp dụng.

CSRF không yêu cầu kẻ tấn công đọc được response. Chỉ cần server chấp nhận một thay đổi trái ý muốn đã có thể gây hại. Trong khôi phục tài khoản, thay đổi đó có thể là đặt mật khẩu, hủy một yêu cầu, xác nhận thay MFA hoặc đăng ký lại phương thức xác thực.

Token chống CSRF bổ sung một giá trị mà trang hợp lệ nhận được và chủ động gửi lại. Cookie tự động đi kèm request không đủ để đáp ứng điều kiện này.

## 2. Phân biệt ba loại giá trị thường bị gọi chung là token

| Giá trị | Mục đích | Nó không chứng minh điều gì? |
| --- | --- | --- |
| Recovery token | Chứng minh quyền tiếp cận một bước khôi phục, chẳng hạn liên kết email | Không tự chứng minh mọi request tiếp theo là hành động có chủ đích |
| Credential của phiên recovery | Cho server tìm ngữ cảnh và quyền hạn tạm thời | Nếu gửi tự động bằng cookie, nó không tự chống CSRF |
| CSRF token | Giúp server từ chối request giả mạo thiếu giá trị gắn với ngữ cảnh hợp lệ | Không chứng minh người gọi là chủ tài khoản hoặc được quyền xóa MFA |

Một CSRF token hợp lệ trong phiên A không được dùng để thay đổi tài khoản của phiên B. Ngược lại, có CSRF token của một phiên chưa xác minh cũng không tạo ra quyền đặt lại mật khẩu.

Không mặc định rằng mọi token recovery đều thiếu khả năng chống CSRF. Nếu một hành động luôn yêu cầu một bí mật không được trình duyệt tự gửi, không bị lộ cho origin ngoài và được ràng buộc đúng hành động, đặc tính đó có thể góp phần ngăn request giả mạo. Tuy nhiên, sau khi hệ thống đổi bí mật ấy lấy cookie recovery, cần xét lại từng endpoint theo credential mà nó thực sự chấp nhận.

## 3. Chọn phạm vi bảo vệ theo hành động

Một chính sách minh họa có thể phân loại các bước như sau:

| Bước | Vai trò của kiểm soát CSRF |
| --- | --- |
| Mở trang hướng dẫn bằng GET | Không thực hiện thay đổi credential chỉ vì trang được mở |
| Gửi yêu cầu khôi phục ban đầu | Xét ngữ cảnh trình duyệt và nguy cơ lạm dụng; chưa đăng nhập không phải lý do tự động miễn mọi bảo vệ |
| Đổi token liên kết lấy phiên recovery | Bảo vệ việc gắn hoặc thay ngữ cảnh trong trình duyệt theo thiết kế bootstrap |
| Gửi mã xác minh bổ sung bằng phiên cookie | Kiểm tra token CSRF của đúng phiên và quyền truy cập challenge |
| Đặt lại mật khẩu, thay MFA hoặc phương thức xác thực | Kiểm tra CSRF trước tác động nghiệp vụ và kiểm tra đầy đủ quyền recovery |
| Hủy một yêu cầu khôi phục | Cần quyền hủy và chống request giả mạo phù hợp |

Token CSRF không thay thế rate limiting, chống gửi email hàng loạt hoặc giới hạn thử OTP. Một chương trình tự động có thể tự mở phiên của nó rồi lấy CSRF token hợp lệ. Bảo vệ chống CSRF và bảo vệ chống lạm dụng giải quyết những điều kiện khác nhau.

## 4. Synchronizer token gắn với phiên recovery

Với ứng dụng lưu trạng thái phía server, một lựa chọn là synchronizer token: server tạo giá trị bí mật, lưu trong phiên, cấp cho trang hợp lệ và so sánh với giá trị được gửi lại. Token cần khó đoán và riêng cho phiên; thiếu hoặc không khớp thì từ chối request được bảo vệ. [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#synchronizer-token-pattern).

Một thiết kế cho recovery có thể thực hiện:

1. Server tạo hoặc tìm context tạm thời theo cơ chế quản lý phiên của hệ thống.
2. Server sinh CSRF token bằng bộ sinh số ngẫu nhiên mật mã và giữ giá trị mong đợi trong context đó.
3. Trang recovery nhận token qua HTML hoặc response được phép đọc; response chứa bí mật không được chia sẻ qua cache chung.
4. Khi người dùng xác nhận, client chủ động gửi token trong body form hoặc header đã quy định.
5. Server tải giá trị mong đợi từ chính context đang xử lý, xác minh token rồi kiểm tra quyền recovery và thực hiện hành động nếu đủ điều kiện.

Quan hệ cần giữ rõ là:

```text
session credential -> recovery context -> expected CSRF token
                           |
                           +-> request + account + purpose + allowed actions
```

Giá trị mong đợi không được lấy từ một field khác của cùng request rồi đem so sánh với nhau. Hai chuỗi bằng nhau do client tự cung cấp không tạo ra liên kết với phiên phía server.

Việc lấy CSRF token trong phiên do kẻ tấn công tự tạo cũng không giúp họ giả mạo phiên của nạn nhân: hai context phải có giá trị và ràng buộc riêng. Nếu toàn ứng dụng dùng một token cố định, sự phân biệt này bị mất.

## 5. Đưa token vào form và request JavaScript

### Form do server render

Ví dụ template minh họa:

```html
<form method="post" action="/recovery/password">
  <input type="hidden" name="_csrf" value="{{csrfToken}}">
  <label>
    Mật khẩu mới
    <input type="password" name="newPassword"
           autocomplete="new-password" required>
  </label>
  <button type="submit">Xác nhận mật khẩu mới</button>
</form>
```

`{{csrfToken}}` là placeholder được server thay bằng giá trị thực của phiên, có mã hóa thuộc tính HTML phù hợp. Nó không phải một giá trị cố định để đưa vào mọi form.

Trường hidden chỉ là cách vận chuyển. Server phải đọc và xác minh nó. Việc trình duyệt gửi field tên `_csrf` không có ý nghĩa nếu backend chỉ kiểm tra field có tồn tại hoặc chấp nhận một chuỗi tùy ý.

### Request JavaScript tới endpoint cố định

Server có thể render token vào một vị trí trên trang:

```html
<meta name="csrf-token" content="{{csrfToken}}">
```

Ví dụ hàm gửi dữ liệu từ form:

```javascript
async function submitRecoveryPassword(form) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  if (!csrf) {
    throw new Error("Không có thông tin xác nhận của phiên.");
  }

  return fetch("/recovery/password", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrf
    },
    body: JSON.stringify({
      newPassword: form.elements.namedItem("newPassword").value
    })
  });
}
```

Đây là ví dụ cho endpoint cùng origin. Client chỉ gắn token vào đích đã biết; không lấy URL từ query rồi gửi token tới đó. Một interceptor tự thêm CSRF token vào mọi request có thể làm bí mật đi sang dịch vụ bên ngoài.

Tên header, field và định dạng token phải khớp cơ chế server. Cách nhận token bằng JSON, form field hay header không thay đổi yêu cầu ràng buộc đúng phiên. Không đặt token CSRF vào query string hoặc liên kết gửi email chỉ để thuận tiện cho frontend.

## 6. Ví dụ Java về sinh và so sánh giá trị

Lớp sau chỉ minh họa thao tác với token ngẫu nhiên trong một thiết kế tự quản lý. Khi framework đã có cơ chế CSRF phù hợp, tích hợp cơ chế đó giúp tránh duy trì thêm một giao thức song song.

```java
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class RecoveryCsrfValues {
    private static final int BYTE_LENGTH = 32;
    private static final int TEXT_LENGTH = 43;
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DECODER =
            Base64.getUrlDecoder();

    private RecoveryCsrfValues() {
    }

    public static String create() {
        byte[] value = new byte[BYTE_LENGTH];
        RANDOM.nextBytes(value);
        return ENCODER.encodeToString(value);
    }

    public static boolean matches(String expected, String submitted) {
        if (expected == null || submitted == null
                || expected.length() != TEXT_LENGTH
                || submitted.length() != TEXT_LENGTH) {
            return false;
        }
        try {
            byte[] expectedBytes = DECODER.decode(expected);
            byte[] submittedBytes = DECODER.decode(submitted);
            return expectedBytes.length == BYTE_LENGTH
                    && submittedBytes.length == BYTE_LENGTH
                    && MessageDigest.isEqual(expectedBytes, submittedBytes);
        } catch (IllegalArgumentException invalidEncoding) {
            return false;
        }
    }
}
```

32 byte ngẫu nhiên được mã hóa Base64URL không padding thành 43 ký tự. Kích thước này là lựa chọn của ví dụ, không phải giá trị duy nhất hợp lệ cho mọi cơ chế CSRF. Giới hạn chiều dài và xử lý lỗi giải mã giúp đầu vào sai định dạng bị từ chối rõ ràng.

`MessageDigest.isEqual` được dùng để so sánh mảng byte. Tài liệu Java mô tả việc triển khai kiểm tra toàn bộ byte của đối số thứ nhất trong các điều kiện được nêu, thay vì tự viết vòng lặp dừng ngay khi gặp byte khác. [Java MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html#isEqual(byte%5B%5D,byte%5B%5D)).

Quan trọng hơn cách so sánh là nguồn của `expected`: nó phải được tải từ context hợp lệ phía server. Lớp trên không quản lý cookie, lưu phiên, thời hạn, quyền đặt mật khẩu hay tiêu thụ quyền recovery. Không gọi `create()` ngay lúc nhận POST rồi coi một giá trị mới sinh là token mong đợi của form cũ.

## 7. Khởi tạo phiên và thay đổi ranh giới tin cậy

Luồng recovery có thể bắt đầu trước khi người dùng chứng minh danh tính. Vì vậy, có thể cần một pre-session để bảo vệ form khởi tạo hoặc thao tác đổi token liên kết sang context recovery. CSRF token của pre-session phục vụ việc xác nhận request trong context đó; nó chưa cấp quyền thay đổi tài khoản.

Một luồng minh họa:

```text
GET trang bắt đầu
  -> tạo pre-session và cấp CSRF token ban đầu
POST đổi bằng chứng mở đầu
  -> kiểm tra pre-session, CSRF và recovery token
  -> thay context phiên theo chính sách chống fixation
  -> cấp CSRF token cho context recovery mới
POST đặt lại mật khẩu
  -> kiểm tra CSRF của context mới và quyền đặt mật khẩu
  -> cam kết thay đổi, tiêu thụ quyền và kết thúc context
```

Việc thay context phải làm mất hiệu lực credential cũ theo thiết kế, thay vì chỉ đổi một cờ `verified=true` trên một phiên có thể đã bị cố định trước đó. Nếu kết thúc recovery rồi chuyển sang đăng nhập thông thường, phiên đăng nhập cần được thiết lập qua cơ chế của hệ thống; không tự nâng một cookie recovery thành quyền truy cập đầy đủ.

Khi chuyển tài khoản đích, mục đích hoặc mức quyền, cần xác định CSRF token cũ còn được chấp nhận trong context nào. Không giữ một token xuyên qua mọi luồng chỉ để nhiều tab không báo lỗi. Server phải duy trì sự nhất quán giữa token, context và recovery request đang có hiệu lực.

## 8. Tích hợp với Spring Security

Spring Security có cơ chế CSRF cho các phương thức không an toàn và mặc định có repository lưu token trong HTTP session. Bộ lọc xử lý trường hợp token thiếu hoặc không hợp lệ trước khi request đi tiếp. [Tài liệu Spring Security về CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

Đối với recovery, quyền truy cập công khai và bảo vệ CSRF là hai cấu hình cần hiểu riêng. Cho phép người chưa đăng nhập mở trang hoặc gọi endpoint khởi tạo không tự dẫn tới việc phải tắt CSRF cho toàn bộ `/recovery/**`.

Một số điểm cần xác định trong kiến trúc ứng dụng:

- Context recovery có dùng cùng `HttpSession` mà repository CSRF đang dùng hay không?
- Form và frontend đang nhận đúng giá trị do cơ chế framework cung cấp hay một token tự tạo khác?
- Khi ứng dụng thay hoặc hủy phiên, frontend có nhận token của context mới không?
- Chuỗi filter thực sự áp dụng cho endpoint cuối có giữ bảo vệ CSRF không?

Token framework đưa ra cho client có thể qua cơ chế xử lý hoặc che giá trị của framework. Không dùng lớp `RecoveryCsrfValues` để tự so sánh một token framework theo định dạng giả định. Một ứng dụng cần chọn và tích hợp rõ một cơ chế, không trộn giá trị từ nhiều repository rồi tìm cách bỏ qua lỗi không khớp.

## 9. Vòng đời token và xử lý lỗi

CSRF token có thể được giữ theo phiên hoặc được thiết kế theo từng request. Với recovery có nhiều tab và nhiều bước, token dùng một lần cho mọi lần submit tạo ra các tình huống cần xử lý: tab cũ giữ token đã thay, nút Back quay về form cũ hoặc request trước đã tới server nhưng response bị mất.

Cần phân biệt ba loại dùng một lần:

| Giá trị | Ý nghĩa của việc dùng một lần |
| --- | --- |
| CSRF token theo request | Một lựa chọn của cơ chế chống request giả mạo |
| Recovery token hoặc quyền recovery | Giới hạn số lần một bằng chứng hoặc quyền được dùng |
| Idempotency key của thao tác | Giúp nhận diện lệnh lặp do retry theo hợp đồng ứng dụng |

CSRF token hợp lệ không khiến một quyền đã tiêu thụ được dùng lại. Ngược lại, dùng token CSRF theo phiên không có nghĩa được đổi mật khẩu nhiều lần bằng cùng quyền recovery. Giới hạn một lần của hành động phải do nghiệp vụ thực thi nguyên tử.

Khi CSRF token thiếu hoặc sai, server nên từ chối trước tác động nghiệp vụ. Không đổi mật khẩu, không đánh dấu challenge thành công và không tự tiếp tục chỉ vì cookie recovery còn hợp lệ. Phản hồi có thể hướng người dùng tải lại bước phù hợp mà không tiết lộ token mong đợi.

Nếu context recovery đã hết hạn, lấy một CSRF token mới không được làm sống lại bằng chứng hoặc quyền đã hết hạn. Nếu token cũ vì thay phiên, frontend cần đồng bộ theo context mới; server không tắt kiểm tra để form cũ tiếp tục chạy.

Không tự thu hồi mọi recovery request của một tài khoản chỉ vì nhận một request sai CSRF từ bên ngoài. Một phản ứng như vậy có thể biến request giả mạo thành cách gây gián đoạn khôi phục. Audit và giới hạn lạm dụng cần phản ánh đúng sự kiện, không trao thêm khả năng gây tác động cho người gửi.

## 10. Các lớp bổ sung và giới hạn của token

`SameSite`, kiểm tra `Origin` hoặc Fetch Metadata có thể bổ sung bảo vệ theo kiến trúc trình duyệt. Không suy rằng subdomain cùng tổ chức luôn đáng tin, hoặc chỉ cần CORS không cho đọc response là endpoint đã an toàn trước mọi request giả mạo.

Nếu API chỉ chấp nhận bearer credential do ứng dụng chủ động gắn và không dùng credential tự động của trình duyệt, cần đánh giá theo mô hình đó. Nếu cùng endpoint vẫn chấp nhận cookie như phương án thay thế, nhánh cookie vẫn phải có chính sách CSRF thích hợp. Thông báo “API dùng JWT” chưa cho biết JWT được gửi chủ động trong header hay tự động trong cookie.

Nếu không lưu synchronizer token phía server, có thể dùng một cơ chế signed double-submit có ràng buộc với phiên. Chỉ so sánh cookie và header do client đưa tới mà không bảo vệ tính toàn vẹn và liên kết context là một thiết kế khác, có rủi ro khác. Không đưa raw session ID vào token đọc được chỉ để tạo liên kết; chữ ký hoặc HMAC cũng không làm nội dung tự trở nên bí mật.

XSS trên origin recovery có thể đọc token được cấp cho trang hoặc gửi request từ chính ngữ cảnh đó. Token CSRF không thay thế mã hóa đầu ra, giới hạn script và bảo vệ origin. Tương tự, token không ngăn clickjacking tự nó; việc bảo vệ trang khỏi bị nhúng cần cơ chế riêng.

Token phải được loại khỏi log body, log header, báo lỗi và dữ liệu phân tích. Khi cần đối chiếu sự kiện, dùng ID nội bộ phù hợp, không dùng token chống CSRF làm mã theo dõi được chia sẻ rộng rãi.

## 11. Những cách triển khai dễ tạo cảm giác đã được bảo vệ

| Cách triển khai | Vấn đề |
| --- | --- |
| Form có hidden field nhưng server không kiểm tra | Request giả mạo vẫn có thể được xử lý |
| Mọi phiên dùng một token cố định | Người ngoài có thể lấy giá trị rồi dùng cho phiên khác |
| Chỉ yêu cầu cookie CSRF có tồn tại | Cookie vẫn là dữ liệu có thể được gửi tự động |
| Lấy cả `expected` và `submitted` từ request | Không có giá trị tin cậy gắn với phiên |
| Bỏ kiểm tra khi thiếu header để hỗ trợ client cũ | Tạo đường bỏ qua cơ chế bảo vệ |
| Tắt CSRF cho toàn bộ recovery vì chưa đăng nhập | Bỏ sót các bước đang có quyền tạm thời bằng cookie |
| CSRF hợp lệ thì cho đổi mọi tài khoản | Thiếu kiểm tra đối tượng, mục đích và quyền recovery |
| Refresh CSRF đồng thời gia hạn quyền đã hết hạn | Vòng đời của hai loại token bị dùng lẫn |

Trong luồng recovery dùng phiên cookie, CSRF token cần được cấp cho đúng context, gửi lại có chủ đích và kiểm tra trước khi hành động được thực hiện. Quyền thay đổi tài khoản vẫn phải được xác minh riêng, có phạm vi và vòng đời phù hợp với mật khẩu, MFA hoặc phương thức xác thực đang được khôi phục.
