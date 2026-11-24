# Username recovery verification — Xác minh yêu cầu khôi phục tên đăng nhập

Trong chương **Username Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, xác minh yêu cầu khôi phục tên đăng nhập là quyết định liệu hệ thống có được phép tiết lộ một định danh đăng nhập cho người đang yêu cầu hay không. Kết quả này giúp người dùng quay lại đúng tài khoản nhưng không tự cấp quyền đăng nhập, đổi mật khẩu, gỡ MFA hoặc thay passkey.

Bài học tập trung vào bằng chứng, ràng buộc giao dịch và giới hạn tiết lộ. Một thiết kế tốt cần giúp chủ tài khoản tìm lại username mà không biến biểu mẫu khôi phục thành công cụ dò tài khoản hoặc khai thác dữ liệu cá nhân.

## 1. Xác minh điều gì và cấp quyền gì?

Tên đăng nhập thường không được xem là bí mật có độ mạnh như mật khẩu. Tuy vậy, mối liên hệ giữa tên đăng nhập, email, số điện thoại, tổ chức và một dịch vụ có thể là thông tin nhạy cảm. Việc username xuất hiện công khai ở nơi khác không cho phép endpoint recovery tùy ý tiết lộ mọi quan hệ đó.

Cần phân biệt ba kết luận:

| Kết luận | Bằng chứng có thể hỗ trợ | Không tự suy ra được |
|---|---|---|
| Người yêu cầu kiểm soát một kênh liên hệ lúc này | Trả đúng challenge được gửi tới kênh đó | Họ là chủ lịch sử của mọi tài khoản từng dùng kênh |
| Người yêu cầu được phép nhận username của một tài khoản | Kênh đã liên kết hợp lệ, chính sách tiết lộ và bằng chứng bổ sung nếu cần | Họ đã đủ điều kiện đăng nhập |
| Người yêu cầu được phép thay phương tiện xác thực | Recovery theo chính sách riêng cho mật khẩu, MFA hoặc passkey | Có thể thực hiện chỉ vì đã nhận username |

Một username có thể là bí danh đăng nhập, khác với display name và khác với ID nội bộ bất biến. Luồng recovery phải trả đúng loại định danh sản phẩm dùng để đăng nhập, không vô tình trả khóa nội bộ, mã nhân viên hoặc dữ liệu hồ sơ khác.

Bất biến trung tâm của bài là:

~~~text
Verification thành công
  -> quyền tiết lộ username trong phạm vi được phép

Verification thành công
  không tự tạo session, reset token hoặc quyền thay authenticator.
~~~

## 2. Chọn mức xác minh theo rủi ro tiết lộ

Không cần áp dụng cùng một bộ bằng chứng cho mọi ứng dụng. Điều cần đánh giá là dữ liệu nào sẽ bị lộ và hậu quả của việc lộ đó.

| Bối cảnh | Rủi ro chính | Hướng chính sách có thể phù hợp |
|---|---|---|
| Username vốn công khai, quan hệ tài khoản ít nhạy cảm | Dò email có tài khoản, thu thập định danh để tấn công tiếp | Xác minh kênh đã liên kết, giới hạn dữ liệu và tần suất |
| Tài khoản trong tổ chức | Lộ quan hệ lao động, tenant hoặc vai trò | Giới hạn đúng tổ chức, dùng kênh được quản lý hoặc bằng chứng phù hợp |
| Dịch vụ có tư cách thành viên nhạy cảm | Chỉ việc xác nhận có tài khoản cũng gây hại | Có thể cần bằng chứng độc lập mạnh hơn hoặc hỗ trợ có kiểm soát |
| Hộp thư dùng chung, số điện thoại có khả năng được cấp lại | Người nhận mã không phải chủ tài khoản | Không tự tiết lộ mọi tài khoản; đánh giá liên kết và bằng chứng bổ sung |
| Có dấu hiệu kênh liên hệ bị chiếm quyền | Kẻ tấn công kiểm soát challenge | Hạn chế tiết lộ và chuyển sang phương án độc lập |

Nên viết chính sách theo thao tác, chẳng hạn `DISCLOSE_USERNAME`, thay vì một kết quả chung `verified=true` được dùng cho mọi chức năng.

Tín hiệu như IP quen thuộc, trình duyệt giống trước đây hoặc vị trí địa lý chỉ hỗ trợ đánh giá rủi ro. Chúng không thay thế một bằng chứng cần thiết. Việc người dùng nhớ tên thật hoặc ngày sinh cũng không tự chứng minh quyền nhận username.

Nếu người dùng mất cả mật khẩu, MFA hoặc thiết bị, luồng tìm username có thể là bước đầu để định tuyến đúng tài khoản. Những quyền tiếp theo vẫn cần chính sách recovery tương ứng.

## 3. Bằng chứng phải gắn với liên hệ đã thiết lập

### 3.1. Liên hệ hiện tại khác liên hệ vừa khai báo

Người yêu cầu nhập email hoặc số điện thoại để bắt đầu chưa chứng minh địa chỉ đó là kênh khôi phục của tài khoản.

Backend cần kiểm tra liên kết đã có từ trước:

- Kênh thuộc đúng tài khoản và đúng tenant theo dữ liệu có thẩm quyền.
- Kênh đã được xác minh theo quy trình của sản phẩm.
- Liên kết còn hoạt động, chưa bị thay thế hoặc thu hồi.
- Chính sách cho phép dùng kênh đó để tiết lộ username.
- Không có hạn chế rủi ro buộc phải dùng thêm bằng chứng.

Không được cho người lạ nhập địa chỉ mới, xác minh họ nhận được email rồi tự gắn địa chỉ đó vào tài khoản họ muốn tìm. Điều đó chỉ chứng minh quyền kiểm soát địa chỉ mới.

Một địa chỉ từng được xác minh cũng không phải bằng chứng vĩnh viễn về người kiểm soát nó. Nhân viên nghỉ việc, hộp thư đổi người quản lý hoặc số điện thoại được cấp lại đều có thể làm liên kết mất ý nghĩa.

NIST quy định việc thiết lập địa chỉ recovery cần có bước xác minh địa chỉ trong mô hình recovery của họ. Bài này vận dụng nguyên tắc phân biệt địa chỉ đã liên kết với địa chỉ vừa khai báo; đó không phải tuyên bố mọi luồng tìm username đều đạt một mức bảo đảm NIST cụ thể. [NIST SP 800-63B-4, Issued Recovery Codes](https://pages.nist.gov/800-63-4/sp800-63b/events/#issued-recovery-codes).

### 3.2. Chuẩn hóa để tìm đúng liên kết

Dùng cùng quy tắc địa chỉ ở đăng ký, thay liên hệ và recovery. Không thêm một bộ chuẩn hóa mới chỉ cho biểu mẫu quên username.

Đặc biệt với email:

- Không tùy ý bỏ dấu chấm hoặc phần `+tag` ở mọi nhà cung cấp.
- Không gộp các địa chỉ chỉ vì trông gần giống nhau.
- Xác định rõ chính sách so sánh local-part và domain.
- Giữ địa chỉ gửi thực tế từ liên kết đã xác minh, tránh tự dựng lại từ đầu vào.
- Giới hạn kích thước và dùng thư viện phân tích phù hợp với phạm vi địa chỉ sản phẩm hỗ trợ.

RFC 5321 phân biệt ngữ nghĩa local-part với domain và yêu cầu bảo toàn khả năng phân biệt hoa/thường của local-part trong SMTP. Vì vậy, không thể coi `lowercase toàn bộ email` là quy tắc phổ quát cho mọi hệ thống. Nếu sản phẩm chọn cách so sánh riêng, phải nhất quán với dữ liệu đã đăng ký và không tạo va chạm ngoài ý muốn. [RFC 5321, mục 2.4](https://www.rfc-editor.org/rfc/rfc5321.html#section-2.4).

Với số điện thoại, chuẩn hóa theo định dạng và vùng đã xác định, nhưng đừng coi chuẩn hóa đúng là đã chứng minh quyền sở hữu hoặc tính liên tục của số.

### 3.3. Username không phải khóa định tuyến tin cậy

Người quên username có thể chỉ nhớ một phần định danh. Phần này có thể dùng để hỗ trợ tìm hồ sơ nội bộ theo chính sách, nhưng không được biến thành endpoint tìm gần đúng công khai trả danh sách ứng viên.

Đối tượng cần xác minh nên được gắn bằng account ID nội bộ và liên kết liên hệ. Không dùng chuỗi username có thể được đổi hoặc cấp lại làm gốc liên kết của toàn bộ giao dịch.

## 4. Ràng buộc challenge với mục đích và ngữ cảnh

Một mã đúng chỉ có ý nghĩa trong challenge đúng. Không thiết kế một hàm dùng chung kiểu `verifyCode(email, code)` rồi cho mọi endpoint lấy kết quả đó để cấp quyền.

Challenge cần gắn ít nhất với:

~~~text
purpose = USERNAME_RECOVERY
tenant_id
attempt_id
account_id được suy ra phía máy chủ
contact_binding_id và contact_version
challenge_generation
thời hạn và ngân sách thử
browser/context binding nếu thiết kế yêu cầu
policy_version
~~~

Một OTP gửi để xác minh địa chỉ mới không được dùng làm bằng chứng tìm username của tài khoản cũ. Mã tìm username cũng không được dùng để reset mật khẩu, gỡ MFA hoặc đăng ký passkey.

### 4.1. Mô hình trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Khởi tạo attempt
    PENDING --> VERIFIED: Đúng challenge và đủ chính sách
    PENDING --> EXPIRED: Quá hạn
    PENDING --> LOCKED: Hết ngân sách thử
    PENDING --> CANCELLED: Liên kết hoặc chính sách không còn hợp lệ
    VERIFIED --> [*]
    EXPIRED --> [*]
    LOCKED --> [*]
    CANCELLED --> [*]
~~~

Ở thiết kế minh họa, `VERIFIED` chỉ nói attempt đã đổi được một quyền tiết lộ có giới hạn. Việc đọc username dùng grant riêng:

~~~text
Disclosure grant:
  ACTIVE -> USED
  ACTIVE -> EXPIRED hoặc REVOKED
~~~

Nếu chính sách yêu cầu thêm bằng chứng sau khi xác nhận kênh, nên biểu diễn một trạng thái trung gian rõ như `CHANNEL_CONFIRMED`. Không dùng `VERIFIED` theo nghĩa “đã đủ quyền” khi bằng chứng còn thiếu.

### 4.2. Browser binding không phải một yếu tố xác thực độc lập

Một cookie ngẫu nhiên hoặc secret của context giúp ngăn lấy mã từ attempt A ghép vào attempt B. Nó không tự chứng minh danh tính con người và không chống được mọi hình thức phishing.

Nếu cần chuyển thiết bị, thiết kế một luồng chuyển tiếp có kiểm soát hoặc cho phép bắt đầu lại. Không âm thầm bỏ binding khi người dùng mở email trên một trình duyệt khác.

Không dùng IP làm binding cứng duy nhất: mạng di động, proxy hoặc thiết bị thay mạng có thể làm IP đổi. IP có thể là tín hiệu rủi ro, còn binding mật mã cần được quản lý bằng dữ liệu phù hợp.

## 5. Khởi tạo mà không tiết lộ tài khoản

Bài này chọn ví dụ: trong phạm vi một tenant, có một tài khoản đích đủ điều kiện cho liên hệ đã xác minh. Trường hợp một liên hệ có nhiều tài khoản được xử lý riêng ở mục 10; không áp dụng giả định một-một cho mọi sản phẩm.

Request khởi tạo có thể nhập địa chỉ liên hệ. Response công khai dùng cấu trúc ổn định:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "message": "Nếu thông tin phù hợp, bạn sẽ nhận được hướng dẫn xác minh.",
  "attemptId": "<mã tham chiếu ngẫu nhiên>"
}
~~~

`attemptId` không chứa account ID, email, tenant bí mật hoặc dấu hiệu “đã tìm thấy”. Nó cũng không phải quyền đọc username.

Có thể tạo một attempt có hình thức công khai tương đương cho đầu vào hợp lệ dù không có liên kết đủ điều kiện. Quyết định tìm thấy, khả năng gửi và lý do từ chối nằm ở phía máy chủ. Không cần gửi email tới mọi địa chỉ không tồn tại trong dữ liệu; nếu chọn gửi, phải cân nhắc nguy cơ phát tán thư rác.

Việc xử lý và gửi nên được tách phù hợp để response không chờ nhà cung cấp email chỉ khi tài khoản tồn tại. Không trả cờ `emailSent` hoặc mở endpoint polling lộ trạng thái giao hàng cho request chưa được phép.

OWASP khuyến nghị phản hồi công khai nhất quán và tránh khác biệt dễ khai thác về thời gian ở các luồng recovery. Thiết kế khởi tạo username recovery ở đây áp dụng mẫu kiểm soát đó cho nguy cơ tiết lộ định danh. [OWASP Authentication, Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages), [OWASP Forgot Password, Forgot Password Request](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Không khóa tài khoản hoặc hủy mọi attempt của chủ tài khoản chỉ vì người lạ yêu cầu một mã mới. Tính sẵn sàng của đăng nhập bình thường phải được bảo vệ khỏi lạm dụng biểu mẫu recovery.

## 6. Thiết kế mã xác minh, hạn dùng và ngân sách thử

### 6.1. Ví dụ mã nhập tay

Giả sử sản phẩm chọn mã **8 chữ số ngẫu nhiên**, giữ nguyên các số 0 đầu, hiệu lực 5 phút và tối đa 5 lần thử sai trong một challenge. Các giá trị này là ví dụ chính sách, không phải quy định chung cho username recovery.

Với một mã phân bố đều trong `10^8` khả năng, một challenge chỉ chấp nhận một mã và tối đa `q` lần đoán khác nhau:

~~~text
P(đoán đúng) <= q / 10^8

Nếu q = 5:
P <= 5 x 10^-8 cho một challenge.
~~~

Đây chỉ là xác suất đoán trực tuyến trong các giả định đã nêu. Nó không tính việc email bị chiếm quyền, phishing, lộ log hoặc kẻ tấn công tạo nhiều challenge.

Không chuyển mã thành số nguyên làm mất số 0 đầu. Dùng tập ký tự và quy tắc đầu vào rõ ràng, giới hạn kích thước trước xử lý, từ chối ký tự ngoài định dạng đã công bố.

### 6.2. Dấu kiểm chứng phía máy chủ

Với mã ngắn, chỉ lưu SHA-256 không khóa vẫn cho phép dò toàn bộ không gian mã nếu database bị lộ. Một phương án cho challenge ngắn hạn là dùng HMAC với khóa máy chủ được bảo vệ riêng:

~~~text
verifier = HMAC-SHA-256(
  server_key[key_id],
  encode_with_lengths(
    "username-recovery/v1",
    tenant_id,
    attempt_id,
    contact_binding_id,
    contact_version,
    challenge_generation,
    code
  )
)
~~~

Đây là lựa chọn triển khai minh họa, không phải xác nhận tuân thủ một tiêu chuẩn lưu OTP cụ thể. Nếu khóa và database cùng lộ, HMAC không còn ngăn được việc dò không gian mã nhỏ.

Dùng mã hóa trường có cấu trúc hoặc kèm độ dài để tránh nhập nhằng khi nối chuỗi. So sánh verifier bằng primitive phù hợp của thư viện mật mã, không tự viết phép so sánh dừng sớm theo từng ký tự.

Thời hạn của mã bắt đầu theo quy tắc đã xác định lúc cấp. Không gia hạn vô hạn khi email gửi chậm hoặc client kiểm tra sai.

### 6.3. Resend và ngân sách chung

Một mô hình resend đơn giản:

- Mỗi attempt chỉ có một `challenge_generation` hiện hành.
- Resend có cooldown, giới hạn tổng số lần và tạo mã mới.
- Mã thế hệ trước mất hiệu lực.
- Không đặt lại ngân sách thử chung của tài khoản/liên hệ chỉ vì resend hoặc tạo attempt mới.
- Resend chỉ thao tác trong context hợp lệ; người lạ không được liên tục thay mã của attempt đang dùng.

Mã đến muộn do email không đảm bảo thứ tự phải có cách giải thích cho người dùng. Worker gửi mã cần kiểm tra generation và deadline để giảm gửi những mã đã bị thay thế.

Giới hạn theo attempt là chưa đủ. Cần giới hạn thêm theo liên hệ/tài khoản, tenant, nguồn truy cập và ngân sách gửi thông báo. Nếu có `N` challenge độc lập cùng được thử, rủi ro tổng tăng theo tổng ngân sách đoán được cấp.

## 7. Xác minh nguyên tử và ghi nhận thất bại bền vững

### 7.1. Mô hình dữ liệu

| Thực thể | Trường quan trọng | Vai trò |
|---|---|---|
| `account_security` | `account_id`, `tenant_id`, `disclosure_allowed`, `policy_version` | Chính sách có thẩm quyền |
| `contact_binding` | `id`, `account_id`, `tenant_id`, `status`, `verified_at`, `version` | Liên kết đã thiết lập |
| `username_recovery_attempt` | `id`, `purpose`, `account_id`, `tenant_id`, `contact_binding_id`, `contact_version`, `generation`, `code_verifier`, `state`, `failed_count`, `max_failures`, `expires_at`, `context_binding` | Challenge và ngân sách |
| `username_disclosure_grant` | `id`, `attempt_id`, `account_id`, `tenant_id`, `contact_version`, `token_digest`, `expires_at`, `used_at`, `revoked_at` | Quyền nhận username |
| `security_event` | `event_id`, `attempt_ref`, `event_type`, `created_at` | Audit không chứa bí mật |

Cần ràng buộc duy nhất một disclosure grant trên mỗi attempt, khóa ngoại đúng phạm vi tài khoản/tenant và các kiểm tra giá trị phù hợp. Nếu grant cần `policy_version`, `contact_binding_id` và binding riêng để kiểm tra về sau, phải lưu hoặc tham chiếu chúng một cách rõ ràng.

### 7.2. Thứ tự khóa

Với attempt có liên kết thật, ví dụ dùng thứ tự:

~~~text
account_security -> contact_binding -> attempt -> disclosure_grant
~~~

Đường đổi liên hệ, thu hồi, resend và sử dụng grant phải tuân theo cơ chế phối hợp tương thích. Nếu chỉ khóa attempt, một thay đổi liên hệ ở hàng khác có thể diễn ra mà không bị kiểm tra lại.

Attempt không có liên kết đủ điều kiện cũng phải đi qua xử lý có giới hạn, phản hồi công khai phù hợp và không có khả năng tạo grant. Không tiết lộ loại attempt đó cho client.

### 7.3. Mã giả cho một lần kiểm tra

Ví dụ dưới đây minh họa ranh giới nghiệp vụ, không phải mã hoàn chỉnh cho một framework:

~~~java
VerificationResult verify(VerificationCommand command) {
    inputLimits.check(command);
    recoveryLimiter.check(command.context());

    VerificationResult result = transactions.execute(tx -> {
        LockedRecoveryState state =
                recoveryStore.lockFromTrustedContext(
                        tx, command.attemptId(), command.context());

        if (!state.isPendingAndUsableNow()) {
            return VerificationResult.denied();
        }

        if (!codeVerifier.matches(
                state.challenge(), command.code())) {

            // Ghi thất bại và khóa challenge khi hết ngân sách.
            recoveryStore.recordFailure(tx, state);
            return VerificationResult.denied();
        }

        // Kiểm tra tenant, contact version, binding, mục đích,
        // chính sách tiết lộ và đủ tổ hợp bằng chứng.
        disclosurePolicy.requireEligible(state);

        int changed = recoveryStore.markVerifiedIfPending(
                tx, state.attemptId(), state.generation());

        requireExactlyOne(changed);

        DisclosureGrant grant =
                disclosureGrants.createForAttempt(tx, state);

        securityEvents.recordVerificationSuccess(tx, state);
        return VerificationResult.granted(grant);
    });

    // transactions.execute chỉ trả thành công sau commit.
    return result;
}
~~~

`lockFromTrustedContext` phải đọc lại trạng thái có thẩm quyền, không tin account ID hoặc tenant ID tùy ý trong request. Tenant được xác định và kiểm chứng từ context/route đáng tin cậy, rồi đối chiếu với attempt.

`isPendingAndUsableNow` cần kiểm tra hạn dùng bằng thời gian hiện tại sau chờ khóa, ngân sách thử, generation và trạng thái thu hồi. Đúng mã không cho phép bỏ qua một liên hệ đã bị thay.

Nhánh sai mã phải commit tăng bộ đếm trước khi phản hồi lỗi công khai. Nếu ném exception làm rollback cả transaction ngay sau `recordFailure`, số lần thử sai sẽ không tồn tại. Có thể dùng một cơ chế limiter bền vững riêng, nhưng phải xác định rõ ranh giới đó.

Sai định dạng và request bị chặn trước transaction vẫn cần được tính vào giới hạn chống lạm dụng thích hợp; không để định dạng sai thành cách gửi vô hạn request miễn phí.

Token rõ của grant nên được sinh đủ ngẫu nhiên, ví dụ 32 byte từ CSPRNG; chỉ lưu digest và chỉ trả sau commit. Việc tạo grant, chuyển `PENDING -> VERIFIED` và ghi sự kiện thành công phải cùng commit. Không trả token trước khi biết commit thành công.

Khi hai request cùng mã chạy trên hai instance, chỉ một request được chuyển trạng thái và tạo grant. Một phép `synchronized` trong JVM hoặc một nút bị khóa trên giao diện không bảo đảm điều này cho toàn hệ thống.

## 8. Từ xác minh thành công tới tiết lộ username

### 8.1. Chỉ cấp quyền cần thiết

Disclosure grant có thể có mục đích `DISCLOSE_USERNAME`, thời hạn ngắn và một lần đọc kết quả theo thiết kế minh họa. Nó không được chấp nhận ở endpoint login, đổi mật khẩu, gỡ MFA hoặc thay email.

Nếu cùng một định dạng token dùng cho nhiều nghiệp vụ, mỗi nơi nhận vẫn phải kiểm tra mục đích, audience, tenant và trạng thái. Không dùng một hàm `isValidToken` chung mà bỏ kiểm tra quyền cụ thể.

Một request đọc kết quả phải xác minh lại:

- Token khớp grant đã commit và đúng mục đích.
- Grant còn hạn, chưa dùng và chưa bị thu hồi.
- Context binding còn đúng nếu được yêu cầu.
- Tài khoản và liên hệ vẫn đủ điều kiện tiết lộ.
- Phiên bản liên hệ và chính sách không thay đổi theo cách làm mất hiệu lực quyền.
- Username được lấy từ đúng account ID và tenant đã ràng buộc.

Không nhận `accountId` từ body để quyết định tài khoản sẽ hiển thị sau khi xác minh một grant khác. Đây là lỗi phân quyền dù OTP đã được kiểm tra chính xác.

### 8.2. Đọc kết quả có điều kiện

Sau khi khóa và kiểm tra account/contact/grant theo quy ước, một đoạn cập nhật quyết định có thể là:

~~~sql
-- Ví dụ PostgreSQL, không phải transaction hoàn chỉnh.
-- Các tham số :server_* và :locked_* đều do backend xác định.
UPDATE username_disclosure_grant
SET used_at = clock_timestamp()
WHERE id = :server_grant_id
  AND token_digest = :server_token_digest
  AND purpose = 'DISCLOSE_USERNAME'
  AND tenant_id = :server_tenant_id
  AND contact_version = :locked_contact_version
  AND used_at IS NULL
  AND revoked_at IS NULL
  AND expires_at > clock_timestamp()
RETURNING account_id;
~~~

Phải có đúng một dòng. Trước đó backend cần kiểm tra liên hệ hiện tại, policy version và binding; chỉ kiểm tra `contact_version` trong một tham số chưa được đối chiếu không đủ.

Trong cùng transaction, lấy username hiện hành của `account_id` được trả về, giới hạn đúng tenant và xác nhận chính sách cho phép. Nếu truy vấn hoặc kiểm tra cuối thất bại, rollback để không ghi nhận một lần tiết lộ chưa có kết quả hợp lệ. Chỉ trả username sau commit.

Grant cần lưu các trường hoặc tham chiếu cần thiết cho các kiểm tra này, gồm `purpose`, `contact_binding_id`, policy version và context binding. Schema ở mục 7 là mô hình rút gọn, không thay thế định nghĩa cột đầy đủ.

### 8.3. Kết quả tối thiểu

Có thể trả chỉ định danh cần đăng nhập và đích đăng nhập hợp lệ của sản phẩm:

~~~json
{
  "username": "nguoidung_minhhoa",
  "nextAction": "SIGN_IN"
}
~~~

Không trả kèm ngày sinh, vai trò quản trị, trạng thái đình chỉ, số điện thoại, email khác hoặc các tenant mà người đó chưa được phép biết.

Nếu chính sách chỉ cho phép gợi ý một phần, phần được che vẫn cần được bảo vệ. Một mẫu như `ng***_2024` có thể đủ để xác định một người trong tập nhỏ; che ký tự không phải là thay thế cho xác minh.

Username lấy từ database cũng cần được xử lý an toàn khi hiển thị: encode theo ngữ cảnh, không ghép thẳng vào HTML hoặc URL chưa được kiểm soát. Không đặt kết quả vào URL công khai để tránh lịch sử và referrer.

### 8.4. Không tự tạo session đăng nhập

Sau khi nhận username, người dùng tiếp tục đăng nhập theo chính sách hiện hành. Nếu quên mật khẩu, bắt đầu password reset; nếu mất MFA hoặc passkey, dùng luồng riêng với bằng chứng tương ứng.

Không lấy trạng thái `VERIFIED` của username recovery để đặt `mfaSatisfied=true`. Không chuyển nguyên cookie context thành session đăng nhập đầy đủ. Nếu sau đó có xác thực thật và tạo session, thực hiện quản lý session theo framework và chính sách của hệ thống.

## 9. Replay, resend, thay liên hệ và retry

### 9.1. Hai request xác minh cùng lúc

Cả hai request có thể nhận đúng mã trước khi một request commit. Điểm khóa và chuyển trạng thái có điều kiện phải bảo đảm một attempt chỉ tạo một grant.

Ràng buộc duy nhất trên `username_disclosure_grant(attempt_id)` là hàng rào bổ sung. Nếu một bước lỗi sau khi đánh dấu `VERIFIED`, transaction phải rollback cả trạng thái và grant.

Không tạo grant trước rồi gửi response, sau đó mới ghi attempt đã xác minh. Khoảng trống này có thể cho phép phát hành nhiều quyền.

### 9.2. Resend cạnh tranh với xác minh

Nếu resend commit trước, generation cũ bị thay; mã cũ phải bị từ chối. Nếu xác minh commit trước, attempt đã đóng; resend không được kéo nó về `PENDING`.

Đường resend phải kiểm tra binding và phối hợp với đường verify. Người lạ tạo một attempt khác không được quyền vô hiệu hóa attempt của người dùng đang giữ context hợp lệ.

Việc hạn chế số attempt đồng thời cần cân bằng chống đoán với từ chối dịch vụ. Không giải quyết bằng quy tắc bất kỳ request mới nào cũng hủy mọi mã trước đó cho cùng email.

### 9.3. Liên hệ bị thay hoặc thu hồi

Giả sử challenge được cấp khi `contact_version=4`, nhưng địa chỉ bị thay thành phiên bản 5 trước lúc xác minh:

~~~text
Attempt giữ contact_version=4
  -> thay liên hệ và tăng version
  -> verify hoặc disclosure đọc version hiện tại
  -> từ chối quyền dựa trên liên kết cũ
~~~

Cần kiểm tra ở cả bước verify và bước tiết lộ. Nếu chỉ kiểm tra khi gửi mã, một mã đã nằm trong hộp thư cũ vẫn có thể tiết lộ thông tin sau khi kênh đó bị thu hồi.

Các thao tác thay liên hệ, xóa tài khoản hoặc thay chính sách phải phối hợp với cùng trạng thái có thẩm quyền. Không chỉ cập nhật cache hiển thị.

### 9.4. Username đổi hoặc được cấp lại

Ràng buộc grant với account ID bất biến, không với chuỗi username do người dùng nhập. Khi đọc kết quả, lấy định danh hiện hành của đúng tài khoản.

Nếu sản phẩm yêu cầu vô hiệu hóa grant khi username thay đổi, thêm version tương ứng và kiểm tra tại nơi tiết lộ. Không dùng username cũ làm khóa để tìm ngược rồi vô tình chuyển sang tài khoản khác vừa nhận tên đó.

Một kết quả đã trả chỉ đúng tại thời điểm quyết định. Không hứa username sẽ không bao giờ thay đổi sau khi người dùng đọc nó.

### 9.5. Response bị mất sau commit

Có hai ranh giới cần xét:

| Sự cố | Trạng thái có thể có | Xử lý phù hợp |
|---|---|---|
| Verify rollback | Attempt chưa tạo grant thành công | Có thể thử lại nếu còn điều kiện |
| Verify commit, mất response chứa token grant | Attempt đã đóng, grant đã có | Resume có ràng buộc hoặc bắt đầu lại theo hợp đồng |
| Disclosure rollback | Chưa ghi lần đọc thành công | Có thể thử lại nếu grant còn hợp lệ |
| Disclosure commit, response username bị mất | Grant đã dùng | Không tự đặt lại `used_at`; dùng cơ chế tiếp tục đã thiết kế |

Nếu chỉ lưu digest token grant, server không thể tái tạo token rõ từ digest. Một cơ chế idempotency hoặc resume cần được thiết kế trước, ràng buộc với đúng attempt/context và kiểm tra lại trạng thái hiện tại.

Có thể chọn một lần đọc duy nhất để đơn giản hóa bảo mật, nhưng phải chấp nhận và giải thích hạn chế khi response mất. Nếu cho phép phát lại cùng kết quả trong một cửa sổ ngắn, phải giới hạn người nhận, thời hạn và việc thu hồi; đó không phải quyền truy vấn username vô thời hạn.

## 10. Nhiều tài khoản, tenant và hộp thư dùng chung

### 10.1. Một email không luôn tương ứng một tài khoản

Các mô hình có thể gồm nhiều tài khoản cá nhân, tài khoản gia đình, các vai trò khác nhau hoặc nhiều tenant sử dụng cùng một địa chỉ.

Không thực hiện:

~~~text
Nhận OTP của email
  -> SELECT mọi tài khoản ở mọi tenant có email tương tự
  -> trả toàn bộ username, vai trò và tổ chức.
~~~

Bằng chứng phải được đánh giá trên từng liên kết mà chính sách cho phép. Một challenge không được mở rộng phạm vi ngầm sau khi xác minh.

Các lựa chọn thiết kế có thể là:

- Chỉ xử lý trong tenant đã xác định từ context phù hợp.
- Trả một tập username đã được chính sách cho phép trong đúng phạm vi.
- Yêu cầu bằng chứng bổ sung trước khi tiết lộ tài khoản nhạy cảm.
- Hỗ trợ tách biệt khi liên kết không đủ rõ ràng.

Nếu cần người dùng chọn tổ chức, không hiện danh sách các tổ chức gắn với email trước khi đủ bằng chứng. Tên tenant có thể chính là thông tin cần bảo vệ.

### 10.2. Hộp thư chung và người đại diện

Người đọc được một hộp thư nhóm không tự có quyền biết mọi tài khoản của từng người từng sử dụng hộp thư đó. Tương tự, email của phụ huynh hoặc người đại diện cần được gắn với quyền đại diện trong chính sách ứng dụng, không suy ra quyền từ việc nhận OTP.

Nếu liên hệ dùng chung là mô hình được hỗ trợ, phải thiết kế rõ đối tượng được nhận gì và giới hạn nào áp dụng. Không tự khắc phục bằng cách trả một danh sách đầy đủ rồi yêu cầu người nhận “chọn tài khoản của mình”.

### 10.3. Tài khoản SSO và tên đăng nhập bên ngoài

Ứng dụng có thể không quản lý username dùng tại IdP. Sau xác minh, chỉ trả định danh hoặc hướng dẫn mà ứng dụng được phép và có dữ liệu chính xác.

Không tự tạo mật khẩu cục bộ, bypass SSO hoặc suy đoán username ở nhà cung cấp khác từ email. Nếu cần chuyển người dùng tới IdP, dùng đích đáng tin cậy và tránh lộ token/grant trong redirect.

Một phiên SSO hiện hữu chỉ có thể giúp nhận diện tài khoản theo chính sách và assertion đã xác minh; một cookie của ứng dụng khác không tự là bằng chứng hợp lệ cho recovery ở tenant này.

## 11. Hiểu đúng email verification và đường thay thế

### 11.1. Nhận email không đồng nghĩa đã xác thực đăng nhập

NIST không cho dùng email làm out-of-band authenticator theo mô hình xác thực của họ, đồng thời nêu ngoại lệ về mã xác nhận địa chỉ và mã recovery. Vì vậy, không diễn giải rằng gửi mã tìm username qua email tự tạo MFA hoặc chứng nhận người dùng đã đạt AAL2. Cũng không suy ra email bị cấm cho mọi hoạt động xác nhận hoặc recovery. [NIST SP 800-63B-4, Out-of-Band Authenticators](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#out-of-band-authenticators).

Thiết kế trong bài dùng challenge để xét quyền tiết lộ username theo chính sách, không dùng nó để tự tạo session. Nếu kết quả được dùng cho quyền mạnh hơn, phải đánh giá lại toàn bộ bằng chứng và tiêu chuẩn tương ứng.

Mã nhập tay hoặc liên kết bearer có thể bị chuyển tiếp qua phishing. Binding với attempt giúp chống ghép nhầm giao dịch nhưng không bảo đảm ngăn một trang giả yêu cầu người dùng nhập mã ngay lúc kẻ tấn công đang chờ.

### 11.2. Người dùng không còn kênh đã đăng ký

Không cho thay kênh nhận mã chỉ bằng tên, ngày sinh hoặc một phần username. Đó là thay đổi quyền khôi phục, không còn chỉ là tìm lại định danh.

Có thể dùng:

- Authenticator khác đã đăng ký và còn sử dụng được.
- Passkey có khả năng nhận diện tài khoản mà không cần nhập username trước, nếu sản phẩm hỗ trợ.
- Một phương án recovery độc lập đã được thiết lập.
- Hỗ trợ có kiểm chứng phù hợp với dữ liệu và mô hình tài khoản.

Không tạo vòng lặp buộc nhập username để sử dụng chính phương tiện được chọn nhằm tìm lại username. Nếu giao thức hoặc giao diện hiện tại không hỗ trợ nhận diện không cần username, cần một đường khác được thiết kế rõ.

### 11.3. Hỗ trợ thủ công

Nhân viên cần biết họ đang được phép tiết lộ username hay thực hiện một thao tác recovery rộng hơn. Công cụ hỗ trợ nên thực thi cùng chính sách phạm vi và ghi audit.

Biết dữ liệu hồ sơ có thể giúp tìm tài khoản nội bộ, nhưng không tự cấp quyền đọc username cho người gọi. Với tài khoản chưa từng gắn với danh tính thật, giấy tờ mới xuất trình cũng không tự chứng minh người đó là chủ tài khoản cũ.

Không yêu cầu người dùng đọc mã xác minh cho nhân viên qua chat để bỏ qua nơi kiểm tra có thẩm quyền. Cần quy trình riêng cho assisted recovery với bằng chứng, giới hạn và khả năng từ chối khi chưa đủ điều kiện.

## 12. Ngăn rò rỉ qua phản hồi và chống lạm dụng

### 12.1. Các kênh rò rỉ trước xác minh

Không chỉ câu chữ mới tiết lộ tài khoản:

| Bề mặt | Ví dụ rò rỉ cần tránh |
|---|---|
| HTTP status | Có tài khoản trả 202, không có trả 404 |
| JSON | Một nhánh có `eligible=true` hoặc `accountCount` |
| Header, cookie | Chỉ tài khoản thật mới có cookie hoặc header đặc trưng |
| Redirect | Chuyển sang URL chứa username hoặc tenant của tài khoản |
| Thời gian | Chỉ trường hợp thật mới chờ gửi email đồng bộ |
| Hint | Hiện email khác bị che hoặc một phần username quá sớm |
| Polling | Cho xem email đã giao hoặc mã đã phát ra trước khi được phép |
| Thông báo lỗi | “Mã đúng nhưng tài khoản bị đình chỉ” |

OWASP chỉ ra HTTP code và thời gian xử lý có thể trở thành yếu tố phân biệt ngay cả khi nội dung thông báo chung giống nhau. [OWASP Authentication, Error Codes and URLs](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#error-codes-and-urls).

Không cần làm mọi lỗi cú pháp và lỗi hạ tầng giống nhau. Có thể trả lỗi đầu vào hoặc lỗi tạm thời nhất quán theo hợp đồng, miễn không phản ánh một bí mật về tài khoản. Với lỗi mã, dùng phản hồi chung như:

> Không thể xác minh yêu cầu này. Hãy kiểm tra mã hoặc bắt đầu lại theo hướng dẫn.

Kết quả thành công có thể khác sau khi đã có đủ bằng chứng; đó là sự tiết lộ có chủ đích trong phạm vi chính sách. Vấn đề là tránh để người chưa được phép phân biệt các tài khoản bằng nhánh lỗi hoặc metadata.

### 12.2. Giới hạn nhiều chiều

Áp dụng ngân sách phù hợp cho tạo attempt, gửi lại, nhập mã, phát grant và đọc kết quả. Các lớp cần phối hợp:

- Attempt và generation.
- Liên hệ hoặc tài khoản đích đã được chuẩn hóa.
- Nguồn truy cập và context.
- Tenant và năng lực nhà cung cấp thông báo.
- Ngân sách tổng để chống tấn công phân tán.

Limiter phải dùng chung hoặc có bảo đảm tương đương trong hệ thống nhiều instance. Không để resend hoặc tạo attempt mới xóa backoff.

Nếu dùng khóa limiter theo liên hệ, có thể tạo khóa định danh bằng HMAC thay vì ghi email rõ. Khóa đó vẫn cần được bảo vệ; nó không tự biến dữ liệu thành hoàn toàn vô danh.

Không để hạn mức hoặc header còn lại tiết lộ tài khoản tồn tại. Những bucket cho đầu vào không khớp cũng cần hành vi công khai phù hợp. CAPTCHA có thể bổ sung tín hiệu nhưng không thay thế OTP binding và trạng thái dùng một lần.

### 12.3. Khả năng phục vụ người dùng hợp lệ

Không khóa đăng nhập của tài khoản chỉ vì người ngoài gửi nhiều yêu cầu username recovery. Có thể khóa challenge bị thử sai, giảm tốc nguồn gửi và cung cấp cách bắt đầu lại có kiểm soát.

Giới hạn gửi email cần ngăn quấy rối mà không tạo quyền cho người lạ vô hiệu hóa vĩnh viễn kênh của chủ tài khoản. Theo dõi tình huống hết ngân sách do lạm dụng và chuẩn bị đường hỗ trợ không hạ yêu cầu xác minh.

## 13. Gửi mã, audit và xử lý bí mật

### 13.1. Mã cần được giao một cách có thể vận hành

Database chỉ có verifier một chiều không thể tái tạo mã rõ để gửi. Nếu dùng worker/outbox để gửi mã, cần thiết kế cách chuyển giao bí mật phù hợp, chẳng hạn payload mã hóa với khóa được quản lý riêng, quyền truy cập hẹp và TTL ngắn.

Đây là dữ liệu phục vụ giao mã, khác với event audit thông thường. Không đưa mã rõ vào một event được nhiều dịch vụ tiêu thụ hoặc lưu dài hạn. Xóa payload giao mã theo vòng đời sau khi hoàn thành hoặc hết hạn.

Worker phải kiểm tra generation và hạn dùng hiện tại, quản lý retry và chịu được sự kiện trùng. Không để một lần gửi lại từ hàng đợi cũ làm sống lại generation đã bị hủy.

Thông báo nên chỉ gồm mã hoặc hướng dẫn và ngữ cảnh tối thiểu. Nếu mục tiêu là chỉ tiết lộ username sau khi xác minh trên ứng dụng, đừng gửi username ngay trong email chứa challenge; làm vậy đã bỏ qua bước tiết lộ được thiết kế.

### 13.2. Những gì không được log

Không ghi:

- OTP, token grant, context secret hoặc cookie.
- Verifier của mã/token trong log hay metric.
- Toàn bộ email, số điện thoại hoặc username nếu không có nhu cầu đã xác định.
- Request/response body bí mật từ proxy, APM, trace hoặc session replay.

Một audit event có thể có dạng sau; các giá trị chỉ để minh họa:

~~~json
{
  "eventId": "evt-username-example-01",
  "eventType": "USERNAME_RECOVERY_VERIFIED",
  "attemptRef": "attempt-internal-42",
  "contactBindingRef": "contact-internal-17",
  "tenantRef": "tenant-internal-03",
  "outcome": "COMMITTED"
}
~~~

Ghi thời gian và lý do nội bộ tối thiểu để điều tra, phân quyền truy cập và thời gian lưu. Sự kiện `VERIFIED` và `USERNAME_DISCLOSED` nên được phân biệt: đã chứng minh đủ điều kiện không đồng nghĩa client đã nhận được response chứa username.

Không ghi thành công trước commit nếu không thể phân biệt trạng thái chưa commit. Với response bị mất, audit chỉ xác nhận server đã thực hiện bước được ghi nhận, không chứng minh người nhận đã đọc thông tin.

### 13.3. Bảo vệ trang nhập mã và kết quả

Dùng HTTPS, hạn chế cache và referrer phù hợp, giảm script bên thứ ba ở trang chứa bí mật. Ví dụ:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Khi dùng cookie, áp dụng thuộc tính bảo vệ và chống CSRF theo kiến trúc. Một attempt ID không đoán được chưa tự thay thế context binding hoặc mọi biện pháp chống CSRF.

Với liên kết thay mã nhập tay, không tiết lộ username hoặc tiêu thụ quyền chỉ vì email scanner gửi GET. Cần bước chủ đích phù hợp. Token trong URL còn có thể lọt vào log trước khi trang gửi header bảo vệ; phải che ở hạ tầng tiếp nhận.

## 14. Tình huống và các kiểm chứng cần có

### 14.1. Người dùng quên username, liên hệ đổi giữa chừng

An có tài khoản trong tenant A, còn email đã đăng ký nhưng quên username.

1. An nhập email tại luồng của tenant A. Response không xác nhận tài khoản có tồn tại.
2. Backend tìm liên kết đủ điều kiện, tạo attempt có `contact_version=6` và context binding.
3. Mã được gửi đúng kênh; request verify phải mang đúng attempt và context.
4. Nếu mã sai, ngân sách thất bại được ghi bền vững và response không lộ trạng thái tài khoản.
5. Nếu đúng mã và đủ chính sách, transaction chuyển attempt sang `VERIFIED` và tạo một disclosure grant.
6. Trước khi An đọc kết quả, liên hệ bị thu hồi hoặc đổi sang phiên bản 7.
7. Endpoint kết quả kiểm tra trạng thái hiện tại và từ chối grant dựa trên liên kết cũ.
8. An đi theo hướng dẫn bắt đầu lại hoặc hỗ trợ phù hợp; grant cũ không được mở lại.

Nếu liên hệ không thay và mọi điều kiện còn đúng, An nhận username hiện hành của đúng tài khoản, rồi đăng nhập theo cơ chế thông thường. Không có bước nào tự gỡ MFA hoặc đổi mật khẩu.

Nếu An có thêm tài khoản ở tenant B, grant của tenant A không cho phép liệt kê tài khoản đó. Ngay cả khi hai tài khoản dùng cùng địa chỉ, phạm vi đã xác minh vẫn phải được tôn trọng.

### 14.2. Tình huống kiểm chứng khi triển khai

Bảng này mô tả yêu cầu đối chiếu thiết kế, không phải kết quả kiểm thử đã chạy trên ứng dụng.

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Liên hệ khớp hoặc không khớp | Khởi tạo không tiết lộ tồn tại qua response và metadata |
| Đúng mã, đúng context và đủ chính sách | Một attempt tạo tối đa một disclosure grant |
| Đúng mã nhưng sai attempt/context | Không cấp grant |
| Mã của mục đích khác | Không dùng được cho username recovery |
| Client sửa account ID hoặc tenant | Không thay đổi đối tượng được phép tiết lộ |
| Mã có số 0 đầu | Được xử lý đúng định dạng, không bị biến đổi ngoài quy tắc |
| Mã sai nhiều lần | Bộ đếm tồn tại qua các request và giới hạn được thực thi |
| Hai instance verify cùng mã | Tối đa một kết quả cấp quyền đã commit |
| Resend cạnh tranh với verify | Generation và trạng thái được tôn trọng |
| Tạo attempt mới hoặc đổi IP | Không xóa ngân sách thử liên hệ/tài khoản |
| Liên hệ thay trước verify | Từ chối bằng chứng của liên kết cũ |
| Liên hệ thay sau verify nhưng trước disclosure | Grant cũ không tiết lộ username |
| Username đổi hoặc được cấp lại | Không định tuyến sang tài khoản khác qua chuỗi tên cũ |
| Cùng email ở nhiều tenant | Không tự liệt kê ngoài phạm vi |
| Hộp thư dùng chung hoặc liên hệ mới nhập | Không tự coi người nhận mã là chủ mọi tài khoản |
| Grant đúng nhưng gửi tới endpoint reset/login | Không được cấp quyền vượt mục đích |
| Commit xong nhưng mất response | Không phát grant hoặc tiết lộ lại trái hợp đồng retry |
| Hàng đợi gửi mã bị trùng hoặc chậm | Không hồi sinh mã thế hệ cũ |
| Email scanner mở liên kết | Không tự hoàn tất bước tiết lộ |
| Log, trace, metric và session replay | Không chứa bí mật hoặc định danh ngoài nhu cầu |
| Dịch vụ xác minh hoặc kho trạng thái không khả dụng | Không bỏ qua xác minh hoặc hạ về câu hỏi kiến thức |
| Restore bản sao trước lần dùng mã/grant | Có hàng rào để không làm quyền đã dùng sống lại |

Kiểm tra cần quan sát dữ liệu được tiết lộ và quyền thực tế được cấp, không chỉ mã HTTP. Một response lỗi nhưng đã gửi username vào email hoặc ghi nó trong analytics vẫn có thể là một lần tiết lộ ngoài chính sách.

Với restore/failover, lịch sử dùng một lần và thu hồi phải được giữ hoặc tái lập đáng tin cậy. Nếu mất lịch sử, cần xử lý các attempt/grant bị ảnh hưởng trước khi tiếp tục chấp nhận; khóa ứng dụng không thể sửa trạng thái đã bị phục hồi lùi.

## 15. Tài liệu đối chiếu và phạm vi ví dụ

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages): phản hồi tránh dò tài khoản và các kênh khác biệt.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request): mẫu kiểm soát request recovery và chống lạm dụng.
- [NIST SP 800-63B-4 — Out-of-Band Authenticators](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#out-of-band-authenticators): phân biệt email confirmation/recovery với authenticator.
- [NIST SP 800-63B-4 — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/): thiết lập địa chỉ và chính sách recovery.
- [RFC 5321, mục 2.4](https://www.rfc-editor.org/rfc/rfc5321.html#section-2.4): ngữ nghĩa so sánh địa chỉ email.

Mã 8 chữ số, hạn dùng 5 phút, ngân sách 5 lần, HMAC, mô hình grant và thứ tự khóa là lựa chọn minh họa. Khi áp dụng, cần đối chiếu rủi ro tiết lộ, chính sách tài khoản, kiến trúc session và nguồn dữ liệu thực tế; bài học không tự xác nhận một triển khai đã đạt mức bảo đảm hoặc tuân thủ tiêu chuẩn.
