# Success message wording

## 1. Thông báo thành công phải xác nhận đúng điều đã xảy ra

Trong khôi phục tài khoản, “thành công” có thể là đã tiếp nhận yêu cầu, đã xác minh một mã, đã đổi mật khẩu hoặc đã hoàn tất một quy trình phục hồi. Những kết quả đó có phạm vi khác nhau.

Success message wording là cách diễn đạt thông báo để người dùng biết **thao tác nào đã hoàn tất, điều đó có nghĩa gì và họ cần làm gì tiếp theo**. Câu chữ phải dựa trên trạng thái được máy chủ xác nhận, thay vì suy từ việc người dùng bấm nút hoặc nhận HTTP response không có lỗi mạng.

Ví dụ:

> Mật khẩu đã được cập nhật. Hãy đăng nhập bằng mật khẩu mới và hoàn tất các bước xác thực được yêu cầu.

Thông báo này cụ thể hơn “Thành công!”, đồng thời không khẳng định người dùng đã đăng nhập, MFA đã được đặt lại hoặc mọi phiên cũ đã kết thúc.

Trong module phục hồi mật khẩu, MFA, passkey và thiết bị xác thực, một thông báo đúng còn giúp người dùng phát hiện thay đổi ngoài ý muốn. Tuy nhiên, nó không được tiết lộ bí mật hoặc xác nhận thông tin tài khoản cho người chưa có quyền xem.

**Phạm vi minh họa:** tên trạng thái, message key, mẫu câu và mã Java trong bài là thiết kế học tập. Chúng cần được gắn với workflow và trạng thái thực tế của từng dịch vụ.

## 2. Phân biệt thành công của từng bước với hoàn tất toàn bộ phục hồi

| Sự kiện đã được xác nhận | Có thể nói | Chưa được suy ra |
| --- | --- | --- |
| Yêu cầu công khai được tiếp nhận | Đã tiếp nhận yêu cầu; hướng dẫn sẽ được gửi nếu đủ điều kiện | Tài khoản tồn tại hoặc email đã được gửi thành công |
| Mã được chấp nhận cho một bước | Bước xác minh này đã hoàn tất | Danh tính đã được xác minh đầy đủ cho mọi thao tác |
| Mật khẩu mới đã được lưu | Mật khẩu đã được cập nhật | Người dùng đã đăng nhập hoặc mọi yếu tố khác đã thay đổi |
| Phương thức xác thực mới đã được liên kết | Đã thêm phương thức xác thực mới | Phương thức cũ đã bị gỡ nếu chưa thực hiện |
| Passkey mới đã được đăng ký | Passkey mới đã được thêm | Tất cả passkey cũ đã vô hiệu |
| Các yêu cầu phục hồi bắt buộc đã hoàn tất | Quy trình phục hồi đã hoàn tất | Mọi dữ liệu hoặc hoạt động trước đây đều an toàn |
| Yêu cầu kết thúc phiên đã được xếp hàng | Đang xử lý việc kết thúc các phiên thuộc phạm vi đã chọn | Mọi phiên đã mất hiệu lực trên toàn hệ thống |

Mỗi thông báo nên gắn với một mốc có ý nghĩa đối với người dùng. Tránh để cùng một câu “Tài khoản đã được khôi phục” xuất hiện sau cả bước gửi email, nhập OTP và đổi mật khẩu.

### 2.1. Tiếp nhận yêu cầu công khai không xác nhận tài khoản

Ở bước nhập email hoặc tên đăng nhập, có thể dùng:

> Đã tiếp nhận yêu cầu. Nếu thông tin phù hợp với một tài khoản và có phương thức khôi phục khả dụng, hướng dẫn sẽ được gửi qua kênh đã đăng ký.

Không nên viết “Chúng tôi đã gửi mã tới email của bạn” khi chưa xác nhận việc gửi hoặc khi thông báo đó tạo khác biệt giữa tài khoản tồn tại và không tồn tại.

OWASP khuyến nghị phản hồi khởi tạo quên mật khẩu nhất quán cho tài khoản có tồn tại và không tồn tại, đồng thời tránh chênh lệch thời gian dễ dùng để dò tài khoản. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request)

### 2.2. Xác minh một bằng chứng không mở mọi quyền

Một mã email được chấp nhận có thể chỉ cho phép tiếp tục đặt lại mật khẩu trong hồ sơ hiện tại. Câu “Danh tính của bạn đã được xác minh” có thể khiến người dùng hoặc nhân viên hỗ trợ hiểu quá mức.

Cách diễn đạt hẹp hơn:

> Bước xác minh này đã hoàn tất. Hãy tiếp tục theo hướng dẫn để xử lý yêu cầu khôi phục.

Nếu còn bước bổ sung bắt buộc, nói rõ bước đó thay vì tạo cảm giác quy trình đã xong.

## 3. Cấu trúc một thông báo thành công dễ hiểu

Một thông báo thường cần ba thành phần, thêm thành phần thứ tư khi có ý nghĩa bảo mật:

~~~text
Kết quả chính: Điều gì đã hoàn tất?
Bước tiếp theo: Người dùng nên thực hiện hành động nào?
Phạm vi cần lưu ý: Có phần nào vẫn đang xử lý hoặc chưa được thay đổi?
Hỗ trợ sự cố: Nếu không phải người dùng thực hiện thì cần làm gì?
~~~

Không phải màn hình nào cũng cần đủ bốn phần. Một màn hình trung gian có thể chỉ cần kết quả và nút tiếp tục; thông báo đổi credential nên cung cấp đường xử lý thay đổi trái phép.

Ví dụ màn hình sau đặt lại mật khẩu:

> **Mật khẩu đã được cập nhật.**  
> Hãy đăng nhập bằng mật khẩu mới và hoàn tất các bước xác thực được yêu cầu.  
> Nếu bạn không thực hiện thay đổi này, hãy mở quy trình bảo vệ tài khoản.

Chỉ thêm “Các phiên đăng nhập trước đã kết thúc” khi backend có đủ căn cứ về phạm vi và hiệu lực của việc kết thúc đó.

### 3.1. Nêu hành động bằng động từ cụ thể

Các câu “Đã cập nhật mật khẩu”, “Đã thêm passkey mới” hoặc “Đã hoàn tất bước xác minh” giúp người dùng hiểu kết quả hơn các câu như “Xử lý thành công” hay “Mọi thứ đã ổn”.

Dùng từ ngữ phù hợp với đối tượng học hoặc sử dụng dịch vụ. Trên giao diện, “phiên đăng nhập” thường dễ hiểu hơn “session”, còn “phương thức xác thực” dễ hiểu hơn “authenticator binding”.

### 3.2. Không để lời khen làm mờ thông tin

Một lời chúc ngắn không có vấn đề nếu kết quả vẫn rõ. Tuy nhiên, thông báo kiểu “Tuyệt vời! Bạn đã hoàn toàn an toàn!” đưa ra bảo đảm quá rộng.

Sau một thay đổi, hệ thống thường chỉ biết một tập thao tác đã thành công. Nó không thể chỉ từ đó bảo đảm không còn phiên bị chiếm quyền, email phục hồi không bị thay đổi hoặc thiết bị không có phần mềm độc hại.

## 4. Mẫu câu theo tình huống phục hồi

| Tình huống | Mẫu câu phù hợp | Điều kiện trước khi hiển thị |
| --- | --- | --- |
| Hoàn tất bước xác minh | Bước xác minh đã hoàn tất. Hãy tiếp tục theo hướng dẫn. | Bằng chứng đã được chấp nhận cho bước đó |
| Đổi mật khẩu | Mật khẩu đã được cập nhật. Hãy đăng nhập bằng mật khẩu mới. | Thay đổi đã được commit và đường đăng nhập phù hợp |
| Thêm phương thức MFA mới | Đã thêm phương thức xác thực mới. | Việc liên kết đã được xác nhận |
| Thay thế phương thức MFA cũ | Phương thức xác thực mới đã được thiết lập; phương thức cũ được chọn đã bị gỡ. | Cả hai thao tác trong phạm vi được chọn đã hoàn tất |
| Thêm passkey | Passkey mới đã được thêm vào tài khoản. | Máy chủ đã xác minh và lưu liên kết credential mới |
| Lưu lựa chọn kết thúc phiên | Đã tiếp nhận yêu cầu kết thúc các phiên đã chọn. | Mới tiếp nhận hoặc xếp hàng yêu cầu |
| Hoàn tất phục hồi | Các bước phục hồi yêu cầu đã hoàn tất. Hãy đăng nhập theo hướng dẫn. | Mọi điều kiện hoàn tất của workflow đã đạt |
| Khôi phục sau sự cố chiếm quyền | Các thay đổi khôi phục đã hoàn tất. Hãy kiểm tra lại cài đặt bảo mật và hoạt động gần đây. | Những thay đổi được nêu đã thực hiện, còn hướng dẫn rà soát phù hợp |

Các mẫu này cần được điều chỉnh theo khả năng thực tế của sản phẩm. Nếu không có trang hoạt động gần đây, không hướng người dùng tới một chức năng không tồn tại.

### 4.1. Sau thay mật khẩu vẫn có thể cần MFA

Đổi mật khẩu không có nghĩa gỡ MFA. Nếu tài khoản vẫn yêu cầu yếu tố thứ hai, bước tiếp theo nên nêu rằng đăng nhập còn có bước xác thực được yêu cầu.

OWASP khuyến nghị sau khi đặt mật khẩu mới, người dùng đăng nhập bằng cơ chế thông thường thay vì tự động được đăng nhập từ luồng reset. [OWASP Forgot Password Cheat Sheet, User Resets Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password)

Nếu người dùng đang khôi phục cả mật khẩu lẫn MFA, không đưa họ tới một nút đăng nhập hứa hẹn hoàn tất trong khi workflow vẫn đang chờ thiết lập yếu tố mới.

### 4.2. Thêm mới khác với thay thế

“Passkey đã được thêm” không nói rằng mọi passkey cũ đã bị thu hồi. Nếu chính sách cho phép nhiều passkey, đây là mô tả chính xác.

Chỉ dùng câu “Passkey cũ đã bị gỡ” cho đúng credential mà backend đã gỡ thành công. Không suy ra trạng thái toàn tài khoản từ thao tác trên một credential.

Tương tự, việc thiết lập TOTP mới không tự chứng minh các recovery code cũ đã bị vô hiệu. Nếu bộ mã được thay, cần xác nhận riêng theo trạng thái của bộ mã đó.

## 5. Thành công phải dựa trên trạng thái máy chủ

Không hiển thị thành công chỉ vì:

- Validation trên trình duyệt đã qua.
- Request đã được gửi.
- Một tác vụ đã được xếp hàng.
- Máy chủ trả 202 Accepted cho thao tác còn xử lý.
- Trình duyệt chuyển sang một URL chứa success=true.
- Request timeout nhưng người dùng đã bấm nút trước đó.

Một luồng đồng bộ có thể đi qua:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant F as Giao diện
    participant R as Dịch vụ phục hồi
    participant D as Kho dữ liệu
    U->>F: Xác nhận thay đổi
    F->>R: Gửi yêu cầu cùng ngữ cảnh phục hồi
    R->>R: Kiểm tra quyền, bằng chứng và trạng thái
    R->>D: Lưu thay đổi và hoàn tất bước liên quan
    D-->>R: Xác nhận commit
    R-->>F: Kết quả đã xác nhận trong phạm vi được phép
    F-->>U: Thông báo đúng thao tác và bước tiếp theo
~~~

Thông báo không thay thế kiểm tra token một lần, thời hạn hoặc quyền thực hiện thao tác. Những kiểm tra đó diễn ra trên backend trước khi thay đổi được thực hiện.

### 5.1. Khi request timeout, kết quả có thể chưa biết

Timeout ở client không chứng minh thao tác thất bại. Backend có thể đã commit nhưng response không tới được người dùng.

Có thể dùng:

> Chưa thể xác nhận kết quả của yêu cầu này. Hãy kiểm tra trạng thái theo hướng dẫn trước khi thực hiện lại.

Hệ thống cần cách đối chiếu kết quả trong ngữ cảnh được phép và cơ chế chống thực hiện trùng phù hợp. Không để nút thử lại tự tạo một thay đổi credential khác mà không kiểm tra kết quả trước đó.

Idempotency key, nếu được dùng, cần gắn với chủ thể hoặc hồ sơ và thao tác thích hợp. Biết mã operation không phải quyền đọc kết quả hoặc thay credential.

### 5.2. Tách thành công chính khỏi tác vụ phụ

Sau đổi mật khẩu, gửi thông báo có thể là tác vụ bất đồng bộ. Nếu mật khẩu đã đổi nhưng email đang chờ gửi, không nói “Chưa đổi mật khẩu” chỉ vì hệ thống gửi thư chậm.

Cách trình bày phải phản ánh từng kết quả:

~~~text
Mật khẩu: đã cập nhật.
Thông báo bảo mật: đang được xử lý.
Kết thúc phiên: trạng thái theo phạm vi đã chọn.
~~~

Không đưa chi tiết kỹ thuật như tên queue, outbox hoặc mã lỗi nhà cung cấp vào giao diện khi chúng không giúp người dùng quyết định bước tiếp theo.

## 6. Diễn đạt đúng phạm vi session và đăng nhập

Câu “Đã đăng xuất khỏi mọi thiết bị” đòi hỏi hiểu rõ phạm vi thực thi. Một ứng dụng có thể quản lý session cục bộ nhưng không tự kết thúc mọi session tại identity provider hoặc mọi ứng dụng liên kết.

Cần phân biệt:

| Trạng thái thực tế | Cách diễn đạt phù hợp |
| --- | --- |
| Đã kết thúc session hiện tại | Bạn đã đăng xuất khỏi phiên này |
| Đã vô hiệu các session do dịch vụ quản lý trong phạm vi xác định | Các phiên thuộc phạm vi được nêu đã bị vô hiệu |
| Mới gửi lệnh thu hồi sang hệ thống khác | Yêu cầu kết thúc phiên đang được xử lý |
| Còn độ trễ hiệu lực hoặc chưa xác nhận được | Chưa thông báo rằng mọi phiên đã kết thúc |
| Chưa xử lý session | Chỉ xác nhận thay đổi credential đã hoàn tất |

Thay mật khẩu không tự bảo đảm các access token hoặc refresh token đã mất hiệu lực. Lời thông báo phải bám vào cơ chế đã thực thi, không dựa vào kỳ vọng của người viết nội dung.

Nếu việc hạn chế phiên là điều kiện an toàn bắt buộc của workflow, backend cần giữ đúng điều kiện đó trước khi cấp quyền sử dụng tiếp. Không dùng câu “đang xử lý” để che việc cấp quyền quá sớm.

Không hiển thị “Bạn đã đăng nhập” nếu hệ thống chỉ tạo phiên phục hồi giới hạn. Phiên giới hạn có thể chỉ được dùng cho một số bước xác minh hoặc thiết lập credential.

## 7. Bảo vệ quyền riêng tư trong màn hình và thông báo gửi ra ngoài

Mức chi tiết tùy thuộc người xem đã có quyền đối với hồ sơ hay chưa. Trước khi hiển thị kết quả thay đổi, backend phải kiểm tra quyền xem đúng đối tượng, không chỉ thấy operationId trong URL.

Thông báo thành công không nên chứa:

- Mật khẩu mới hoặc một phần mật khẩu.
- OTP, seed TOTP, recovery code hoặc private key.
- Reset token, cookie hoặc liên kết còn có thể cấp quyền ngoài mục đích cần thiết.
- Toàn bộ thông tin giấy tờ, số điện thoại hoặc email không cần thiết.
- Trọng số, ngưỡng và tín hiệu phát hiện gian lận nội bộ.

Một màn hình thành công thường chỉ cần kết quả, bước tiếp theo và đường báo thay đổi trái phép. Không đưa thêm danh sách phương thức xác thực đã đăng ký chỉ để trấn an.

### 7.1. Thông báo bảo mật cần cho phép phát hiện thay đổi trái phép

NIST SP 800-63B-4 yêu cầu thông báo khi phục hồi tài khoản xảy ra và yêu cầu hướng dẫn rõ cách liên hệ nếu người nhận phủ nhận sự kiện, trong phạm vi áp dụng của hướng dẫn. [NIST SP 800-63B-4, Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b.html#account-notifications)

Một mẫu nội dung gửi qua kênh đã được chọn đúng chính sách:

> Mật khẩu tài khoản của bạn đã được cập nhật vào thời điểm được ghi nhận. Nếu bạn không thực hiện thay đổi này, hãy truy cập ứng dụng hoặc trang bảo mật chính thức để báo cáo và nhận hướng dẫn.

Không gửi mật khẩu trong email. OWASP cũng khuyến nghị thông báo việc reset mà không gửi giá trị mật khẩu. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#user-resets-password)

Không mặc nhiên gửi mọi thông báo tới địa chỉ mới mà người đang phục hồi vừa nhập. Việc chọn người nhận phải theo chính sách và trạng thái kênh, đặc biệt khi nghi ngờ chiếm quyền.

Trên màn hình khóa hoặc notification preview, dùng mức chi tiết phù hợp. Nội dung đầy đủ có thể yêu cầu mở ứng dụng và xác thực theo phạm vi cần thiết.

## 8. Ví dụ Java: ánh xạ kết quả sang message key

Ví dụ sau chỉ tạo nội dung trình bày từ kết quả nghiệp vụ đã được chuẩn hóa. Nó không xác minh token, không đổi mật khẩu và không cấp session. Record yêu cầu Java 16 trở lên.

~~~java
import java.util.Objects;

public final class RecoverySuccessMessages {
    public enum Outcome {
        PENDING,
        COMMITTED,
        UNKNOWN,
        REJECTED
    }

    public enum Effect {
        PASSWORD_UPDATED,
        AUTHENTICATOR_ADDED,
        PASSKEY_ADDED,
        RECOVERY_COMPLETED
    }

    public record Result(
            Outcome outcome,
            Effect effect) {
        public Result {
            Objects.requireNonNull(outcome);
            Objects.requireNonNull(effect);
        }
    }

    public record Message(
            String titleKey,
            String nextStepKey,
            boolean showSuccessStyle) {}

    public static Message renderAuthorizedResult(Result result) {
        Objects.requireNonNull(result);

        if (result.outcome() == Outcome.PENDING) {
            return new Message(
                    "recovery.request.processing",
                    "recovery.check.status",
                    false);
        }

        if (result.outcome() == Outcome.UNKNOWN) {
            return new Message(
                    "recovery.result.not.confirmed",
                    "recovery.check.before.retry",
                    false);
        }

        if (result.outcome() == Outcome.REJECTED) {
            return new Message(
                    "recovery.action.not.completed",
                    "recovery.follow.current.instructions",
                    false);
        }

        return switch (result.effect()) {
            case PASSWORD_UPDATED -> new Message(
                    "recovery.password.updated",
                    "recovery.sign.in.with.required.factors",
                    true);
            case AUTHENTICATOR_ADDED -> new Message(
                    "recovery.authenticator.added",
                    "recovery.follow.next.required.step",
                    true);
            case PASSKEY_ADDED -> new Message(
                    "recovery.passkey.added",
                    "recovery.follow.next.required.step",
                    true);
            case RECOVERY_COMPLETED -> new Message(
                    "recovery.required.steps.completed",
                    "recovery.follow.sign.in.instructions",
                    true);
        };
    }

    private RecoverySuccessMessages() {}
}
~~~

Result phải do backend tạo từ kết quả thực tế sau kiểm tra trạng thái. Không nhận outcome=COMMITTED từ client rồi dùng để tạo thông báo.

renderAuthorizedResult không tự kiểm tra quyền. Lớp gọi nó phải xác minh người xem có quyền đối với đúng hồ sơ hoặc thao tác trước khi lấy kết quả.

Các message key là định danh nội dung, không phải điều kiện cấp quyền. Backend không được lấy showSuccessStyle=true làm lý do cho phép đăng nhập hoặc thay một yếu tố khác.

Ví dụ cố ý không tuyên bố gì về session hoặc việc gỡ authenticator cũ. Nếu giao diện cần các thông tin đó, bổ sung kết quả có phạm vi rõ ràng đã được xác nhận, thay vì suy từ effect.

RECOVERY_COMPLETED chỉ được tạo khi các yêu cầu hoàn tất của workflow đã đạt. Nó không bảo đảm tài khoản không còn mọi loại rủi ro.

## 9. Hiển thị để người dùng thực sự nhận biết kết quả

Một thông báo đúng nhưng biến mất quá nhanh hoặc chỉ hiển thị bằng màu sắc vẫn khó sử dụng.

Các nguyên tắc trình bày:

- Đặt kết quả chính ở vị trí dễ nhận thấy gần bước vừa hoàn tất.
- Dùng văn bản rõ ràng, không chỉ biểu tượng dấu tích hoặc màu xanh.
- Đặt tên nút theo hành động như “Đăng nhập” hoặc “Tiếp tục xác minh”.
- Giữ hướng dẫn đủ lâu để người dùng đọc và thực hiện.
- Tránh tự chuyển trang trước khi người dùng kịp biết kết quả.
- Không dùng thông báo bật lên nhỏ làm nơi duy nhất chứa hướng dẫn xử lý thay đổi trái phép.

W3C giải thích rằng status message động không nhận focus cần có vai trò hoặc thuộc tính để công nghệ hỗ trợ nhận biết và thông báo cho người dùng. role=status là một kỹ thuật phù hợp với nhiều thông báo thành công. [W3C Understanding WCAG 2.2, Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)

Ví dụ vùng thông báo được đặt sẵn trên trang và cập nhật sau khi nhận kết quả:

~~~html
<div id="recovery-status" role="status" aria-atomic="true"></div>
<a id="next-step" href="/login" hidden>Đăng nhập</a>
~~~

~~~javascript
// authorizedResult comes from a server response for this recovery context.
if (
  authorizedResult.outcome === "COMMITTED" &&
  authorizedResult.effect === "PASSWORD_UPDATED"
) {
  document.getElementById("recovery-status").textContent =
    "Mật khẩu đã được cập nhật. Hãy đăng nhập và hoàn tất " +
    "các bước xác thực được yêu cầu.";

  document.getElementById("next-step").hidden = false;
}
~~~

Đường /login chỉ là ví dụ. Ứng dụng cần dùng route chính thức và không lấy URL điều hướng tùy ý từ dữ liệu không tin cậy.

Dùng textContent cho văn bản không cần HTML giúp tránh chèn markup ngoài ý muốn. Không đưa giá trị người dùng vừa nhập vào thông báo theo dạng HTML không được xử lý.

Ví dụ trên không thay thế quản lý các trạng thái đang xử lý, chưa biết kết quả và bị từ chối. Mỗi trạng thái cần thông báo phù hợp; chỉ chuyển sang câu thành công khi có kết quả tương ứng.

Với một trang mới hoặc thay đổi ngữ cảnh, cách quản lý focus và tiêu đề trang có thể khác một status message cập nhật tại chỗ. Không mặc định gắn role=alert vào mọi thông báo thành công.

## 10. Bản địa hóa và nhất quán giữa các kênh

Giữ message key ổn định và tách bản dịch khỏi logic nghiệp vụ. Khi dịch, không làm rộng phạm vi của lời xác nhận.

| Ý nghĩa gốc | Bản diễn đạt giữ đúng phạm vi | Bản dễ làm sai nghĩa |
| --- | --- | --- |
| Password updated | Mật khẩu đã được cập nhật | Tài khoản đã được khôi phục hoàn toàn |
| Request received | Đã tiếp nhận yêu cầu | Đã gửi mã thành công |
| Passkey added | Passkey mới đã được thêm | Đã thay toàn bộ passkey |
| Verification step completed | Bước xác minh đã hoàn tất | Danh tính đã được xác minh đầy đủ |
| Session revocation pending | Đang xử lý yêu cầu kết thúc phiên | Mọi thiết bị đã đăng xuất |

Nếu hiển thị thời điểm, nêu múi giờ hoặc định dạng phù hợp người dùng. Tránh để cùng một sự kiện xuất hiện với thời gian mơ hồ giữa email và màn hình hồ sơ.

Không đưa email hoặc số điện thoại vào template chỉ vì đó là biến sẵn có. Mỗi biến cần có mục đích và mức hiển thị phù hợp với người xem.

Thông báo trong ứng dụng và thông báo gửi ra ngoài nên thống nhất về hành động đã xảy ra. Chúng có thể khác mức chi tiết vì bối cảnh quyền riêng tư khác nhau.

## 11. Xử lý lịch sử, thao tác lặp và thay đổi sau đó

Một trang thành công có thể được mở lại từ lịch sử trình duyệt. Không được thực hiện lại thay đổi credential chỉ vì trang được tải.

Một GET hiển thị kết quả không nên tự đổi mật khẩu, gỡ MFA hoặc tiêu thụ token để tạo ra thay đổi. Các thao tác nhạy cảm cần đi qua cơ chế xác nhận và kiểm tra riêng.

Nếu kết quả được xem lại, phân biệt hai câu:

~~~text
Lịch sử: Mật khẩu đã được cập nhật lúc thời điểm T.
Hiện tại: Trạng thái hiện tại sau khi kiểm tra quyền và dữ liệu mới nhất.
~~~

Một sự kiện thành công trong quá khứ không chứng minh hiện tại tài khoản vẫn ở trạng thái đó. Sau sự kiện có thể xảy ra thay đổi khác, thu hồi hoặc xử lý sự cố.

Không dựa vào cache công khai để trả thông tin kết quả riêng tư. Khi hồ sơ hết hạn hoặc người xem không còn quyền, endpoint phải kiểm tra lại thay vì tiếp tục tiết lộ dữ liệu từ một trang thành công cũ.

Với request lặp, thông báo chỉ có thể nói thao tác đã hoàn tất nếu backend xác định được đó là kết quả của đúng thao tác trong đúng ngữ cảnh. Không dùng cùng một màn hình thành công để che mọi trường hợp token sai, hết hạn hoặc thuộc hồ sơ khác.

## 12. Những câu nên tránh và cách sửa

| Câu cần tránh | Vấn đề | Cách sửa theo trạng thái thực tế |
| --- | --- | --- |
| Thành công! | Không rõ việc gì đã xong | Nêu thao tác cụ thể |
| Tài khoản của bạn đã hoàn toàn an toàn | Bảo đảm vượt quá bằng chứng | Chỉ xác nhận thay đổi và hướng dẫn kiểm tra tiếp |
| Mã đúng, bạn đã là chủ tài khoản | Gán quyền quá rộng cho một bằng chứng | Bước xác minh này đã hoàn tất |
| Đã gửi mã thành công | Có thể mới xếp hàng hoặc làm lộ tài khoản | Đã tiếp nhận yêu cầu; hướng dẫn sẽ được gửi nếu đủ điều kiện |
| Đã đăng xuất tất cả thiết bị | Có thể chưa bao phủ mọi session hoặc hệ thống | Nêu đúng phạm vi và trạng thái được xác nhận |
| Đã thay MFA | Mơ hồ giữa thêm mới, gỡ cũ và hoàn tất thiết lập | Nêu chính xác phương thức được thêm hoặc thay thế |
| Bạn không cần làm gì nữa | Có thể còn bước xác thực hoặc rà soát | Chỉ ra bước tiếp theo thực sự được yêu cầu |
| Đổi mật khẩu thất bại vì email chưa gửi | Trộn kết quả chính với tác vụ thông báo | Phân biệt mật khẩu đã đổi và thông báo đang xử lý |

Thông báo thành công tốt giúp người dùng hiểu một sự kiện đã được xác nhận, không tạo thêm quyền và không hứa bảo vệ vượt quá điều hệ thống đã làm. Câu chữ cần đi cùng trạng thái nghiệp vụ, kiểm soát quyền xem và hướng dẫn bước tiếp theo phù hợp.
