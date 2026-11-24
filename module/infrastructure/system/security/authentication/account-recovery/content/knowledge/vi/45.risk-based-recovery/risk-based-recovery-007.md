# Risk decision explanation

## 1. Giải thích quyết định rủi ro trong khôi phục tài khoản

Risk decision explanation là cách hệ thống mô tả **quyết định đã đưa ra, căn cứ của quyết định, phạm vi áp dụng và bước tiếp theo** trong một hồ sơ khôi phục tài khoản.

Người dùng có thể mất mật khẩu, TOTP, passkey hoặc thiết bị xác thực. Hệ thống phục hồi có thể yêu cầu bằng chứng bổ sung, tạm hoãn một thao tác, chuyển sang hỗ trợ hoặc từ chối sử dụng một mã. Nếu chỉ hiện “Không thể tiếp tục”, người dùng khó biết cần làm gì. Nếu trả toàn bộ tín hiệu và ngưỡng điểm, hệ thống có thể tiết lộ thông tin tài khoản hoặc giúp kẻ tấn công điều chỉnh hành vi.

Thiết kế lời giải thích cần đáp ứng đồng thời ba nhu cầu:

- Người dùng hiểu trạng thái và có bước tiếp theo khả thi.
- Nhân viên có thẩm quyền hiểu đủ để hỗ trợ đúng quy trình.
- Nhóm bảo mật truy xuất được quyết định thực tế để điều tra và cải tiến.

Ví dụ, một hồ sơ bị chuyển sang kiểm tra bổ sung vì kênh phục hồi vừa thay đổi và chưa có bằng chứng độc lập đủ mạnh. Lời giải thích cho người dùng có thể là: “Để tiếp tục khôi phục, bạn cần hoàn tất bước xác minh bổ sung được hiển thị.” Bản ghi nội bộ lưu rõ quy tắc, phiên bản chính sách và bằng chứng còn thiếu.

**Phạm vi minh họa:** tên mã lý do, cấu trúc dữ liệu, API và mẫu thông báo trong bài là thiết kế ví dụ. Chúng cần được điều chỉnh theo mô hình đe dọa, phương thức phục hồi và chính sách của từng dịch vụ.

## 2. Phân biệt dữ kiện, suy luận, chính sách và kết quả

Một lời giải thích chính xác không được biến chỉ báo rủi ro thành kết luận chắc chắn về danh tính.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Dữ kiện đã quan sát | Có sự kiện đổi email phục hồi vào thời điểm T | Thông tin có nguồn và thời điểm cụ thể |
| Chất lượng dữ liệu | Nguồn lịch sử thiết bị chưa trả lời | Chưa có đủ dữ liệu để đánh giá phần tương ứng |
| Suy luận rủi ro | Tổ hợp tín hiệu làm tăng mức bất định | Ước lượng hoặc phân loại, có thể sai |
| Điều kiện chính sách | Thay MFA cần bộ bằng chứng được chấp nhận | Điều kiện bắt buộc của thao tác |
| Quyết định | Yêu cầu xác minh bổ sung | Hành động hệ thống chọn tại thời điểm đánh giá |
| Kết quả thực thi | Chưa thay đổi MFA | Điều thực sự đã xảy ra sau quyết định |

“Thiết bị chưa được nhận diện trong lịch sử” không đồng nghĩa “người yêu cầu là kẻ tấn công”. “Không truy xuất được dữ liệu” cũng không đồng nghĩa “người dùng cung cấp thông tin sai”.

Điểm rủi ro thấp chỉ thể hiện đánh giá trong bối cảnh đã quan sát. Nó không tự chứng minh quyền đặt lại mật khẩu, gỡ MFA hoặc đăng ký passkey. NIST SP 800-63B-4 nêu rõ chỉ báo gian lận không thay thế yếu tố xác thực hoặc tự thay đổi AAL của giao dịch. [NIST SP 800-63B-4, mục 2](https://pages.nist.gov/800-63-4/sp800-63b.html#aal)

Lời giải thích cần giữ đúng ranh giới này. Tránh diễn đạt “đã xác minh danh tính” khi hệ thống mới chỉ xác nhận người yêu cầu truy cập được một hộp thư.

## 3. Tách lời giải thích theo đối tượng được phép xem

Một bản ghi quyết định có thể tạo ra nhiều cách trình bày. Quyền xem phải được kiểm tra trên máy chủ cho từng lần truy cập.

| Đối tượng | Thông tin phù hợp | Thông tin cần hạn chế |
| --- | --- | --- |
| Người chưa xác minh quyền đối với hồ sơ | Thông báo tiếp nhận chung và hướng dẫn chung | Tài khoản có tồn tại không, phương thức đã đăng ký, tín hiệu nội bộ |
| Người có ngữ cảnh phục hồi đã được xác minh phù hợp | Trạng thái hồ sơ, bước xác minh được phép, cách nhờ hỗ trợ | Trọng số, ngưỡng phát hiện, danh sách nguồn tình báo |
| Nhân viên hỗ trợ đúng thẩm quyền | Lý do nghiệp vụ, yêu cầu còn thiếu, đường xử lý được phép | Bí mật xác thực, dữ liệu điều tra ngoài phạm vi công việc |
| Nhóm điều tra được phân quyền | Chuỗi quyết định, căn cứ, phiên bản chính sách, tham chiếu bằng chứng | Dữ liệu không cần thiết cho mục đích điều tra |

Mức chi tiết không chỉ phụ thuộc người xem đã đăng nhập hay chưa. Phiên hiện tại có thể bị chiếm quyền hoặc chưa đủ bảo đảm cho một thao tác nhạy cảm. Ngữ cảnh phục hồi chỉ nên cấp quyền hẹp, gắn với đúng hồ sơ và mục đích.

Một người đã xác minh mã gửi qua email không mặc nhiên có quyền xem toàn bộ lịch sử thiết bị, đổi số điện thoại hoặc thay MFA. Hệ thống xác định phạm vi được xem riêng với phạm vi được thay đổi.

### 3.1. Không làm lộ tài khoản ở bước khởi tạo

Tại endpoint công khai nhận email hoặc tên đăng nhập, lời giải thích có thể dùng:

> Nếu thông tin phù hợp với một tài khoản và có phương thức khôi phục khả dụng, hướng dẫn sẽ được gửi qua kênh đã đăng ký. Bạn cũng có thể xem hướng dẫn hỗ trợ chung.

Không trả “Tài khoản này vừa thay số điện thoại nên bị chặn” cho bất kỳ ai nhập email. Thông báo như vậy vừa xác nhận tài khoản tồn tại vừa tiết lộ lịch sử bảo mật.

OWASP khuyến nghị phản hồi xác thực và phục hồi theo cách chung để hạn chế dò tài khoản; sự khác biệt ở HTTP status hoặc thời gian xử lý cũng có thể làm lộ thông tin dù nội dung trang giống nhau. [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages)

Trong một API minh họa, server có thể trả cùng dạng 202 Accepted cho các yêu cầu khởi tạo được tiếp nhận. Đây là lựa chọn thiết kế, không phải yêu cầu phải dùng 202 cho mọi lỗi. Lỗi cú pháp hoặc giới hạn lưu lượng có thể có phản hồi riêng, nhưng không được phụ thuộc vào việc tài khoản có tồn tại để tạo kênh dò.

## 4. Thiết kế mã lý do ổn định và có ý nghĩa

Mã lý do là định danh máy đọc được, tách khỏi câu chữ hiển thị. Mỗi mã cần có định nghĩa, nguồn sinh, điều kiện áp dụng và chính sách tiết lộ.

| Mã lý do nội bộ minh họa | Định nghĩa | Hướng giải thích cho người dùng đã có quyền xem |
| --- | --- | --- |
| REQUIRED_PROOF_MISSING | Chưa có đủ bằng chứng cho thao tác yêu cầu | Cần hoàn tất xác minh bổ sung |
| RECENT_RECOVERY_CHANNEL_CHANGE | Có thay đổi kênh phục hồi trong khoảng theo dõi | Dùng thông báo về yêu cầu kiểm tra bổ sung nếu chính sách cho phép |
| ELEVATED_REQUEST_RISK | Tổ hợp tín hiệu đạt điều kiện xử lý tăng cường | Yêu cầu cần được xem xét thêm |
| REQUIRED_SIGNAL_UNAVAILABLE | Thiếu dữ liệu bắt buộc để ra quyết định hiện tại | Chưa thể hoàn tất kiểm tra; thử lại hoặc chọn đường hỗ trợ |
| CURRENT_PROOF_INVALID | Bằng chứng hiện tại không dùng được | Không thể dùng mã hoặc liên kết này |
| RECOVERY_CASE_EXPIRED | Hồ sơ đã hết hạn | Cần bắt đầu lại theo hướng dẫn |
| PROTECTED_ACCOUNT_POLICY | Tài khoản hoặc thao tác có kiểm soát đặc biệt | Cần đi theo quy trình được chỉ định |

Một mã như RECENT_RECOVERY_CHANNEL_CHANGE không nên chứa cả email, số điện thoại và tên nguồn phát hiện trong chuỗi của nó. Dữ liệu ngữ cảnh, nếu cần lưu, phải nằm trong trường có cấu trúc và được kiểm soát truy cập.

Không sử dụng câu tiếng Việt làm khóa nghiệp vụ. Thay đổi bản dịch hoặc sửa chính tả không được làm thay đổi logic hoặc phá liên kết lịch sử.

### 4.1. Chọn lý do chính nhưng giữ các lý do liên quan

Một hồ sơ có thể đồng thời thiếu bằng chứng, có điểm cao và gặp nguồn dữ liệu timeout. Không nên lấy phần tử đầu tiên của một tập hợp không có thứ tự rồi gọi đó là “lý do chính”.

Chính sách cần quy định ưu tiên. Ví dụ:

1. Tình trạng làm thao tác hiện tại không còn hợp lệ, như hồ sơ hết hạn.
2. Điều kiện bảo vệ bắt buộc của tài khoản hoặc sự cố đã được xác nhận.
3. Dữ liệu bắt buộc chưa đủ.
4. Yêu cầu kiểm soát tăng cường do đánh giá rủi ro.
5. Bộ bằng chứng còn thiếu ở đường phục hồi hiện tại.

Thứ tự này là ví dụ, không phải quy tắc chung cho mọi hệ thống. Điều quan trọng là bộ quyết định và bộ trình bày sử dụng cùng cách xác định nguyên nhân.

Bản ghi nội bộ vẫn giữ toàn bộ lý do có liên quan. Thông báo người dùng có thể chỉ nêu một trạng thái và một bước tiếp theo để tránh gây rối hoặc tiết lộ quá mức.

## 5. Tạo bản ghi giải thích cùng lúc với quyết định

Không đợi đến khi có khiếu nại rồi chạy lại mô hình hiện tại để đoán vì sao hệ thống đã xử lý hồ sơ hôm trước.

Một cấu trúc nội bộ có thể như sau:

~~~json
{
  "decisionId": "d-example-17",
  "caseRef": "internal-case-ref",
  "evaluatedAt": "2026-11-23T03:00:00Z",
  "policyVersion": "recovery-policy-v8",
  "modelVersion": "rules-v3",
  "action": "ADDITIONAL_REVIEW",
  "primaryReason": "RECENT_RECOVERY_CHANNEL_CHANGE",
  "reasonCodes": [
    "RECENT_RECOVERY_CHANNEL_CHANGE",
    "REQUIRED_PROOF_MISSING"
  ],
  "dataQuality": "COMPLETE_FOR_THIS_POLICY",
  "accountSecurityRevision": 42,
  "evidenceRefs": ["event-ref-101", "proof-evaluation-ref-29"],
  "requiredProofPolicyRef": "factor-replacement-policy-v4",
  "publicTemplateVersion": "vi-recovery-v5",
  "executionStatus": "NOT_EXECUTED"
}
~~~

Đây là dữ liệu giả định dành cho hệ thống nội bộ. Không dùng nguyên đối tượng này làm response của endpoint công khai.

Các trường cần được hiểu cụ thể:

- policyVersion xác định chính sách đã dùng, bao gồm ưu tiên quy tắc.
- modelVersion xác định mô hình hoặc bộ quy tắc chấm điểm, nếu có.
- dataQuality mô tả độ đầy đủ đối với chính sách đó; COMPLETE không có nghĩa hệ thống biết mọi thông tin về người dùng.
- evidenceRefs tham chiếu sự kiện hoặc kết quả kiểm tra, không chứa OTP, recovery code hay token.
- publicTemplateVersion giúp xác định người dùng đã nhận loại thông báo nào.
- executionStatus tách đề xuất xử lý khỏi việc thay đổi tài khoản đã thực hiện.

Nếu dữ liệu và mô hình cho phép, lưu đủ đặc trưng đã chuẩn hóa để tái hiện đánh giá trong thời hạn lưu cho phép. Không giữ mọi dữ liệu thô vô thời hạn chỉ để phục vụ khả năng tái hiện.

Sau khi dữ liệu được xóa theo chính sách, hệ thống phải phản ánh giới hạn điều tra còn lại. Không khẳng định có thể tái hiện chính xác nếu những đầu vào cần thiết đã không còn.

## 6. Viết thông báo rõ ràng và có bước tiếp theo

Một thông báo dành cho người dùng đã có quyền xem hồ sơ nên làm rõ bốn điểm:

~~~text
Trạng thái: Hồ sơ đang ở đâu?
Phạm vi: Thao tác nào chưa được thực hiện?
Bước tiếp theo: Người dùng có thể làm gì?
Hỗ trợ: Có đường thay thế nào nếu không còn phương tiện đó?
~~~

Ví dụ:

> Yêu cầu thay phương thức xác thực cần thêm một bước kiểm tra. Phương thức hiện tại chưa được thay đổi. Hãy chọn một cách xác minh khả dụng bên dưới. Nếu bạn không còn truy cập được các phương thức này, hãy dùng quy trình hỗ trợ khôi phục.

Câu “phương thức hiện tại chưa được thay đổi” chỉ được hiển thị khi máy chủ đã xác định đúng trạng thái thực thi. Nếu chưa biết thao tác đã thành công hay chưa, dùng trạng thái đang xác nhận và ngăn gửi lặp gây thay đổi cạnh tranh.

### 6.1. Tránh hứa hẹn không có cơ sở

Không nói “Sau 24 giờ tài khoản chắc chắn được mở lại” nếu hết thời gian chờ vẫn còn phải đánh giá và xác minh.

Có thể nói:

> Yêu cầu đang trong giai đoạn chờ kiểm tra. Sau thời điểm hiển thị, hệ thống sẽ đánh giá điều kiện tiếp tục. Nếu cần thêm thông tin, hướng dẫn sẽ được cập nhật trong hồ sơ.

Chỉ hiển thị thời điểm khi chính sách cho phép công bố và server đã có mốc thời gian hợp lệ. Thời gian chờ không tự chứng minh người yêu cầu là chủ tài khoản.

### 6.2. Tránh yêu cầu không thể hoàn thành

Nếu người dùng đã khai mất thiết bị TOTP, lời giải thích không nên kết thúc bằng “Hãy nhập TOTP trên thiết bị đã mất” mà không cung cấp phương án khác.

Hệ thống chỉ hiển thị phương thức thay thế thực sự được hỗ trợ và được phép cho hồ sơ. Không bịa đường phục hồi, không tự hạ yêu cầu xác minh vì người dùng không còn phương tiện.

### 6.3. Tránh quy kết người dùng gian lận

| Câu dễ gây hiểu nhầm | Cách diễn đạt phù hợp hơn |
| --- | --- |
| Bạn là người dùng nguy hiểm | Yêu cầu này cần kiểm tra bổ sung |
| Bạn đã khai sai thông tin vì hệ thống không có dữ liệu | Hiện chưa thể hoàn tất một số kiểm tra cần thiết |
| Điểm 82 chứng minh tài khoản bị đánh cắp | Đánh giá hiện tại yêu cầu xử lý tăng cường |
| Mã sai vì email không thuộc tài khoản nào | Không thể dùng mã hoặc liên kết này; hãy làm theo hướng dẫn khôi phục |
| Tắt VPN là chắc chắn được chấp thuận | Hãy dùng quy trình xác minh được cung cấp |

Thông báo cần hỗ trợ khả năng tiếp cận và bản địa hóa. Không dùng riêng màu đỏ hoặc một biểu tượng để truyền đạt trạng thái; nút hành động cần có tên rõ ràng.

## 7. Không biến lời giải thích thành công cụ dò quy tắc

Một endpoint trả chi tiết sau mỗi lần thử có thể trở thành oracle: kẻ tấn công thay một đầu vào, quan sát điểm hoặc mã lý do, rồi suy ra cách né kiểm soát.

Những dữ liệu không nên mặc nhiên công bố gồm:

- Trọng số và ngưỡng chính xác của từng tín hiệu.
- Danh sách IP hoặc thiết bị được tin cậy của một tài khoản.
- Phương thức MFA hoặc kênh phục hồi khi chưa đủ quyền xem.
- Tên nguồn chống gian lận, kết quả tra cứu hoặc dữ liệu điều tra.
- Quy tắc nội bộ cho phép bỏ qua một điều kiện.
- Khác biệt chi tiết giữa mã không tồn tại, mã của tài khoản khác và mã đã dùng.

Thông báo chung cần nhất quán ở response body, header, URL chuyển hướng và luồng giao diện. Trang tracking hoặc endpoint xem lời giải thích cũng có thể làm lộ thông tin nếu chỉ endpoint khởi tạo được bảo vệ.

Nếu cung cấp mã tham chiếu công khai, mã đó không phải bằng chứng danh tính và không thay thế kiểm soát truy cập. Việc biết caseId hoặc decisionId không được cho phép đọc hồ sơ, thay email, gỡ MFA hoặc duyệt khôi phục.

Để giảm lạm dụng, áp dụng kiểm soát truy cập theo đối tượng và giới hạn truy vấn phù hợp. Với API hiển thị dữ liệu nhạy cảm, cần cấu hình cache để tránh trình duyệt hoặc proxy dùng lại thông tin giữa các người dùng.

## 8. Ví dụ Java: tách quyết định nội bộ khỏi thông báo

Đoạn mã sau chỉ minh họa lớp biểu diễn thông báo. Nó không thực hiện xác thực, xác minh danh tính, chấm điểm hoặc thay đổi tài khoản. Ví dụ dùng record nên cần Java 16 trở lên.

~~~java
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class RecoveryExplanation {
    public enum Action {
        CONTINUE_PROOF,
        STEP_UP,
        WAIT,
        ADDITIONAL_REVIEW,
        STOP_CURRENT_CASE
    }

    public enum Reason {
        REQUIRED_PROOF_MISSING,
        RECENT_RECOVERY_CHANNEL_CHANGE,
        ELEVATED_REQUEST_RISK,
        REQUIRED_SIGNAL_UNAVAILABLE,
        CURRENT_PROOF_INVALID,
        RECOVERY_CASE_EXPIRED,
        PROTECTED_ACCOUNT_POLICY
    }

    public record InternalDecision(
            UUID decisionId,
            Action action,
            List<Reason> reasons,
            String policyVersion) {
        public InternalDecision {
            Objects.requireNonNull(decisionId);
            Objects.requireNonNull(action);
            reasons = List.copyOf(reasons);
            if (reasons.isEmpty()) {
                throw new IllegalArgumentException("A reason is required");
            }
            Objects.requireNonNull(policyVersion);
        }
    }

    public record PublicReceipt(
            String messageKey,
            String nextStepKey) {}

    public record CaseExplanation(
            String messageKey,
            String nextStepKey) {}

    public static PublicReceipt anonymousReceipt() {
        return new PublicReceipt(
                "recovery.request.received",
                "recovery.general.help");
    }

    // Caller must authorize access to this exact recovery case first.
    static CaseExplanation forAuthorizedCase(InternalDecision decision) {
        Objects.requireNonNull(decision);

        return switch (decision.action()) {
            case CONTINUE_PROOF -> new CaseExplanation(
                    "recovery.proof.required",
                    "recovery.choose.available.method");
            case STEP_UP -> new CaseExplanation(
                    "recovery.additional.proof.required",
                    "recovery.choose.stronger.method.or.support");
            case WAIT -> new CaseExplanation(
                    "recovery.check.pending",
                    "recovery.follow.case.instructions");
            case ADDITIONAL_REVIEW -> new CaseExplanation(
                    "recovery.review.required",
                    "recovery.open.approved.support.flow");
            case STOP_CURRENT_CASE -> new CaseExplanation(
                    "recovery.case.cannot.continue",
                    "recovery.follow.restart.or.support.instructions");
        };
    }

    private RecoveryExplanation() {}
}
~~~

Các điểm thiết kế trong ví dụ:

- PublicReceipt không nhận thông tin tài khoản hoặc quyết định nội bộ, nên lớp này không tạo thông báo khác nhau theo việc tài khoản tồn tại.
- CaseExplanation chỉ biểu diễn bước tiếp theo, không chứa score hoặc reasonCodes.
- InternalDecision là đối tượng riêng; không serialize nó trực tiếp vào response.
- Danh sách lý do được sao chép để hạn chế việc sửa dữ liệu sau khi tạo đối tượng.
- Message key do server chọn từ tập hữu hạn, sau đó được dịch bằng bộ tài nguyên đã quản lý phiên bản.

Phương thức forAuthorizedCase không tự kiểm tra quyền. Tên phương thức và phạm vi package không phải biện pháp phân quyền. Service gọi nó phải xác minh người yêu cầu có quyền xem đúng hồ sơ ở trạng thái hiện tại.

Đường hỗ trợ trong nextStepKey cũng không cấp quyền thay đổi tài khoản. Backend vẫn cần kiểm tra mọi điều kiện khi người dùng thực hiện bước tiếp theo.

Trong hệ thống thật, cần ràng buộc tổ hợp action và reasons bằng schema hoặc bộ quyết định để tránh tổ hợp mâu thuẫn. Ví dụ chỉ mô tả cách tách DTO, không mô tả toàn bộ workflow.

## 9. Giữ lời giải thích nhất quán với thực thi

Giả sử đánh giá D1 lúc 10:00 cho phép tiếp tục xác minh. Lúc 10:02, tài khoản nhận báo cáo sự cố đã được xác nhận. Lúc 10:03, người dùng nộp mã để hoàn tất.

Nếu server chỉ dựa vào D1, quyết định cũ có thể không còn phù hợp. Nếu giao diện hiển thị lời giải thích của D1 trong khi backend đã chuyển sang D2, người dùng và nhân viên hỗ trợ có thể hiểu sai trạng thái.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant R as Dịch vụ phục hồi
    participant P as Bộ chính sách
    participant S as Kho quyết định
    U->>R: Yêu cầu tiếp tục hồ sơ
    R->>R: Kiểm tra quyền và trạng thái hiện tại
    R->>P: Đánh giá với dữ liệu và revision hiện tại
    P-->>R: Quyết định và căn cứ
    R->>S: Lưu quyết định cùng phiên bản giải thích
    R->>R: Kiểm tra điều kiện và thực hiện bước được phép
    R->>S: Ghi kết quả thực thi
    R-->>U: Trạng thái phù hợp với quyền xem
~~~

Một thiết kế có thể lưu quyết định mới với supersedesDecisionId tham chiếu quyết định trước. Không sửa bản ghi cũ thành lý do mới rồi mất dấu lịch sử.

Trước thay đổi nhạy cảm, kiểm tra revision hoặc dùng cơ chế kiểm soát đồng thời tương đương để phát hiện dữ liệu đã thay đổi. Nếu cần đánh giá lại, tạo quyết định và lời giải thích tương ứng với lần đánh giá mới.

Khi thông báo gửi bất đồng bộ, thông báo nên cho biết trạng thái tại thời điểm được ghi nhận hoặc hướng người dùng tới hồ sơ hiện tại. Không để một email cũ được hiểu là giấy phép thực hiện thao tác mới.

Lời giải thích không thay thế kiểm soát token dùng một lần, thời hạn, ràng buộc đúng mục đích hoặc kiểm soát phiên. Dù màn hình hiện “được tiếp tục”, backend vẫn phải xác minh các điều kiện khi thao tác thực sự được thực hiện.

## 10. Giải thích khi dùng mô hình học máy hoặc dịch vụ bên ngoài

Với mô hình quy tắc, lý do có thể bắt nguồn trực tiếp từ các quy tắc đã kích hoạt. Với mô hình học máy, các yếu tố đóng góp cần được diễn giải thận trọng.

Một đặc trưng đóng góp nhiều vào dự đoán không chứng minh nó gây ra gian lận. Hai đặc trưng tương quan có thể chia sẻ ảnh hưởng; lời giải thích sau mô hình có thể không phản ánh đầy đủ logic chính sách ở lớp ngoài.

Cần phân biệt:

| Nội dung | Ví dụ |
| --- | --- |
| Đầu ra mô hình | Đánh giá rủi ro tăng so với baseline |
| Giải thích mô hình | Các nhóm đặc trưng đóng góp lớn |
| Quy tắc chính sách | Đầu ra đó yêu cầu xem xét thêm |
| Hành động thực tế | Chưa thay MFA, đã tạo yêu cầu hỗ trợ |

Nếu nhà cung cấp chỉ trả một score và không có lý do đáng tin cậy, ghi rõ giới hạn này. Không tự gán RECENT_RECOVERY_CHANNEL_CHANGE chỉ vì điểm cao trong khi không có dữ kiện về thay đổi kênh.

Nếu dùng công cụ sinh ngôn ngữ để soạn thông báo, nội dung phải bị giới hạn bởi dữ kiện đã xác thực và chính sách tiết lộ. Một cách triển khai dễ kiểm soát hơn là dùng template được duyệt và tập biến đầu vào hữu hạn. Công cụ viết câu không được quyết định thêm phương thức phục hồi hoặc hứa hẹn chấp thuận.

Lời giải thích có thể tự tin về điều hệ thống đã làm, chẳng hạn “hồ sơ đã chuyển sang xem xét”, trong khi vẫn thể hiện bất định về việc người yêu cầu có phải chủ tài khoản hay không.

## 11. Hỗ trợ xem xét lại mà không mở đường bỏ qua xác minh

Người dùng hợp lệ có thể bị yêu cầu kiểm tra thêm vì đang đi công tác, đổi thiết bị hoặc không còn phương tiện xác thực cũ. Lời giải thích cần chỉ ra đường hỗ trợ dễ tìm và khả thi.

NIST SP 800-63B-4 yêu cầu cơ chế xử lý phản ánh và vấn đề phát sinh từ xác thực phải dễ tìm, dễ sử dụng và được đánh giá hiệu quả trong phạm vi áp dụng của hướng dẫn. [NIST SP 800-63B-4, mục 2.4.4](https://pages.nist.gov/800-63-4/sp800-63b.html#redress)

Trong thiết kế minh họa này, quy trình xem xét lại cần:

1. Gắn yêu cầu với hồ sơ và quyết định đã được lưu.
2. Cho nhân viên thấy đúng căn cứ và yêu cầu còn thiếu trong quyền hạn của họ.
3. Kiểm tra thông tin hoặc bằng chứng bổ sung theo quy trình.
4. Ghi một quyết định mới khi kết quả thay đổi.
5. Thông báo kết quả và bước tiếp theo trong phạm vi được phép.

Nhân viên không nên có nút “bỏ qua mọi kiểm tra” chỉ vì người yêu cầu biết mã hồ sơ hoặc kể được lịch sử sử dụng tài khoản. Thông tin đó có thể bị thu thập từ nguồn khác.

Nếu có quyền ngoại lệ, phải xác định rõ ai có quyền, điều kiện sử dụng, phạm vi thao tác và yêu cầu phê duyệt. Ghi nguyên nhân thay đổi quyết định; không xóa hoặc sửa ngược lý do ban đầu.

## 12. Bảo vệ dữ liệu giải thích và dấu vết quyết định

Bản ghi giải thích có thể chứa thông tin bảo mật nhạy cảm ngay cả khi không chứa mật khẩu. Cần kiểm soát quyền đọc, việc xuất dữ liệu và thời hạn lưu.

OWASP hướng dẫn ghi sự kiện với hành động, kết quả và lý do, đồng thời hạn chế ghi trực tiếp các giá trị như access token, mật khẩu và session identifier. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#event-attributes)

Áp dụng vào hồ sơ phục hồi:

- Không ghi OTP, recovery code, reset token hoặc liên kết chứa token vào log.
- Tham chiếu kết quả kiểm tra bằng chứng thay vì sao chép bí mật.
- Hạn chế dữ liệu cá nhân ở mức cần thiết; giá trị đã che bớt vẫn có thể nhạy cảm khi kết hợp với dữ liệu khác.
- Dùng trường có cấu trúc, giới hạn độ dài và xử lý dữ liệu không tin cậy trước khi hiển thị.
- Phân quyền truy cập theo nhiệm vụ; ghi lại việc nhân viên xem hoặc xuất dữ liệu cần bảo vệ.
- Bảo vệ tính toàn vẹn của bản ghi và quản lý thay đổi phiên bản template.
- Quy định cách xử lý khi không lưu được bản ghi quyết định bắt buộc; không tự tuyên bố thao tác đã hoàn tất khi chưa xác nhận được kết quả.

Bản dịch mới có thể cải thiện câu chữ cho các lần hiển thị tiếp theo, nhưng lịch sử cần còn thông tin về template đã dùng lúc thông báo được tạo. Khi điều tra, phải phân biệt câu đã gửi với câu đang hiển thị hiện nay.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ trả “risk score quá cao” | Người dùng không biết làm gì | Nêu trạng thái và bước tiếp theo được phép |
| Công bố chi tiết trọng số sau mỗi lần thử | Tạo vòng phản hồi để dò kiểm soát | Ánh xạ sang thông báo theo quyền xem |
| Giải thích dựa trên mô hình hiện tại thay vì bản ghi cũ | Mất căn cứ lịch sử | Lưu snapshot và phiên bản lúc quyết định |
| Trả nguyên đối tượng nội bộ ra API | Lộ dữ liệu và quy tắc không cần thiết | Dùng DTO công khai riêng |
| Dùng caseId như quyền truy cập | Người biết mã có thể xem hồ sơ khác | Kiểm tra quyền đối với từng hồ sơ |
| Gọi timeout là “người dùng gian lận” | Quy kết sai và gây khó hỗ trợ | Phân biệt dữ liệu thiếu với cảnh báo |
| Báo đã đổi mật khẩu khi mới cho phép bước tiếp theo | Người dùng hiểu sai trạng thái bảo mật | Tách quyết định khỏi kết quả thực thi |
| Dùng lời giải thích làm căn cứ duyệt khôi phục | Thông báo bị biến thành quyền | Backend kiểm tra bằng chứng và trạng thái độc lập |
| Hứa chắc chắn được duyệt khi hết thời gian chờ | Tạo kỳ vọng sai và áp lực bỏ qua kiểm soát | Mô tả đúng điều kiện đánh giá tiếp |
| Cung cấp đường hỗ trợ không thực sự hoạt động | Người hợp lệ bị mắc kẹt | Duy trì quy trình thay thế có thẩm quyền rõ ràng |

Một lời giải thích hữu ích phải bám vào quyết định thực tế, giữ đúng mức độ chắc chắn của dữ liệu và chỉ dẫn được hành động tiếp theo. Khả năng giải thích cần được xây cùng bộ quyết định, cơ chế thực thi và phân quyền của luồng khôi phục.
