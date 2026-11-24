# Account ownership proof khi hợp nhất tài khoản

## 1. Vì sao hợp nhất cần bằng chứng cho từng tài khoản?

Một người có thể tạo nhiều tài khoản trong cùng dịch vụ: một tài khoản dùng mật khẩu, một tài khoản đăng nhập liên kết, hoặc một tài khoản cũ không còn phương thức xác thực thuận tiện. Hợp nhất giúp gom dữ liệu và cách đăng nhập về một tài khoản được giữ lại. Tuy nhiên, đây cũng là một cách chuyển quyền truy cập vào dữ liệu nếu hệ thống xác minh sai.

Giả sử người dùng kiểm soát tài khoản A và yêu cầu nhập toàn bộ dữ liệu của B vào A. Nếu chỉ yêu cầu đăng nhập A, người đó có thể chọn B của người khác. Nếu chỉ dựa trên hai tài khoản có cùng email, kẻ tấn công có thể lợi dụng email tái cấp, liên kết danh tính sai hoặc dữ liệu hồ sơ chưa được xác minh.

**Account ownership proof** trong luồng hợp nhất là bằng chứng được hệ thống xác minh để xác lập người yêu cầu có quyền hành động đối với từng tài khoản tham gia, ở mức bảo đảm mà policy yêu cầu. Nó phải gắn với đúng phép hợp nhất, không chỉ chứng minh rằng người đó từng đăng nhập đâu đó trong quá khứ.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, yêu cầu này đặc biệt quan trọng khi một tài khoản đang mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Không được biến thao tác hợp nhất thành lối tắt để bỏ qua quy trình khôi phục của tài khoản chưa chứng minh được quyền kiểm soát.

Một nguyên tắc nền tảng là:

```text
Được xem xét hợp nhất =
    bằng chứng hợp lệ cho tài khoản A
    AND bằng chứng hợp lệ cho tài khoản B
    AND sự đồng ý với đúng kế hoạch hợp nhất
    AND quyền hợp nhất theo policy
    AND đánh giá rủi ro cho phép
```

Đủ bằng chứng sở hữu chưa có nghĩa mọi dữ liệu, vai trò và phiên được phép cộng dồn. Việc dữ liệu nào được chuyển vẫn cần kế hoạch và quy tắc riêng.

## 2. Phân biệt danh tính, quyền kiểm soát và thẩm quyền hợp nhất

Từ “sở hữu” dễ khiến người thiết kế đánh đồng nhiều điều khác nhau:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ giới hạn |
| --- | --- | --- |
| Nhận dạng con người | Người xuất trình bằng chứng là ai? | Giấy tờ hợp lệ chưa tự chứng minh quyền với tài khoản cụ thể |
| Kiểm soát tài khoản | Người đó đáp ứng được điều kiện xác thực của tài khoản nào? | Một phiên bị đánh cắp có thể tạo vẻ ngoài đang kiểm soát |
| Thẩm quyền với dữ liệu | Người đó được phép chuyển những tài nguyên nào? | Người dùng có thể đọc dữ liệu nhóm nhưng không sở hữu nhóm |
| Đồng ý hợp nhất | Người có quyền có chấp thuận đúng thay đổi này không? | Đăng nhập thành công chưa phải đồng ý chuyển dữ liệu |

Hai tài khoản do cùng một người truy cập chưa chắc được phép hợp nhất. Một tài khoản có thể thuộc tổ chức, có yêu cầu lưu giữ hoặc có vai trò gắn với tenant. Ngược lại, một quản trị viên có quyền quản lý tài khoản không tự động có quyền nhận toàn bộ dữ liệu của người dùng đó về tài khoản cá nhân.

Policy cần xác định phạm vi được hỗ trợ. Ví dụ: cho phép một người hợp nhất hai tài khoản cá nhân trong cùng tenant sau khi xác thực lại cả hai; không cho tự phục vụ khi một bên là tài khoản dịch vụ hoặc tài khoản tổ chức. Chuyển dữ liệu giữa hai người khác nhau, bàn giao nhân sự hoặc chuyển quyền sở hữu tổ chức nên có quy trình riêng thay vì giả dạng thành hợp nhất tài khoản cá nhân.

## 3. Bằng chứng nào có giá trị và giá trị đến đâu?

Độ mạnh của bằng chứng phụ thuộc cơ chế xác thực, thời điểm, nguồn xác minh và bối cảnh rủi ro. Không có một trường `owner=true` đáng tin cậy nếu client tự cung cấp nó.

| Dạng bằng chứng | Có thể hỗ trợ xác lập | Không nên suy ra ngay |
| --- | --- | --- |
| Xác thực lại bằng phương thức đã đăng ký | Quyền kiểm soát hiện tại ở mức bảo đảm của phương thức đó | Được phép hợp nhất mọi tài nguyên |
| Xác thực liên kết đã được kiểm tra đầy đủ | Quyền với principal cụ thể từ nhà cung cấp danh tính | Mọi tài khoản có email giống nhau đều cùng chủ |
| Quy trình khôi phục đã hoàn tất hợp lệ | Khả năng truy cập đã được tái lập theo policy | Không cần kiểm tra rủi ro và xác thực cho thao tác hợp nhất |
| Kiểm soát hộp thư | Người đó nhận được thư ở thời điểm kiểm tra | Đã chứng minh toàn bộ quyền với tài khoản có MFA mạnh hơn |
| Thông tin hồ sơ hoặc lịch sử sử dụng | Ngữ cảnh hỗ trợ điều tra | Bằng chứng đủ để chuyển quyền truy cập |
| Quyết định từ hệ thống quản trị tổ chức | Thẩm quyền trong phạm vi được cấp | Được bỏ qua giới hạn tenant hoặc quyền sở hữu tài nguyên |

Biết tên hiển thị, ngày sinh, email, số điện thoại hoặc một giao dịch cũ không mặc nhiên đủ. Những thông tin đó có thể công khai, bị chia sẻ hoặc đã lộ. Một nhân viên hỗ trợ nhìn thấy hai hồ sơ giống nhau cũng chưa tạo ra bằng chứng sở hữu.

Đối với tài khoản nhạy cảm, policy có thể yêu cầu xác thực tăng cường bằng phương thức đã đăng ký, xác minh bổ sung, thời gian chờ hoặc xử lý thủ công. Các điều kiện này phải được quyết định theo mức rủi ro, không hạ ngưỡng chỉ vì người dùng muốn hợp nhất nhanh.

### Email trùng nhau là tín hiệu, không phải kết luận

Một địa chỉ email có thể được đổi chủ hoặc tái cấp. Địa chỉ có thể là alias, mailbox chung hoặc trường hồ sơ do người dùng tự nhập. Việc chuẩn hóa dấu chấm, hậu tố hoặc chữ hoa theo một quy tắc chung có thể làm đồng nhất những địa chỉ mà nhà cung cấp thực tế coi là khác nhau.

Ngay cả khi cả hai hệ thống đều có dấu hiệu email đã xác minh, điều đó chủ yếu nói về quá trình kiểm tra email của từng hệ thống. Nó không tự chứng minh cùng một người có quyền hợp nhất hai tài khoản hiện tại. Dùng định danh tài khoản và danh tính liên kết ổn định, đồng thời yêu cầu bằng chứng đối với từng bên.

## 4. Định danh đúng tài khoản và nguồn danh tính

Phép hợp nhất nên sử dụng ID tài khoản nội bộ ổn định, cùng tenant hoặc miền quản trị tương ứng. Email và tên đăng nhập dùng để hiển thị hoặc tìm kiếm có kiểm soát, không phải khóa duy nhất của quyền sở hữu.

Với danh tính liên kết, cần phân biệt nhà phát hành và subject trong ngữ cảnh tích hợp. Cặp định danh như `issuer + subject` xác định principal theo contract của nhà cung cấp; một subject đơn lẻ không nên được coi là duy nhất xuyên mọi nguồn danh tính. Không nối tài khoản chỉ bằng trường email trong kết quả đăng nhập.

Nếu dùng kết quả xác thực từ nhà cung cấp, dịch vụ phải kiểm tra tính xác thực và các ràng buộc của giao thức đang dùng: nguồn phát hành, đối tượng nhận, thời hạn, tương quan với yêu cầu đăng nhập và khả năng chống phát lại. Không lấy ảnh chụp màn hình “đăng nhập thành công”, tên tài khoản trên trang trình duyệt hoặc JSON do client dựng làm bằng chứng.

Thành công của đăng nhập liên kết cũng phải được ánh xạ về đúng tài khoản nội bộ đã chọn. Nếu người dùng chọn nhầm principal ở nhà cung cấp, luồng phải dừng hoặc yêu cầu chọn lại; không đổi âm thầm đối tượng hợp nhất sang tài khoản khác.

Độ mới của phiên cục bộ và độ mới của lần xác thực thực tế cần được phân biệt. Mở lại một phiên ứng dụng nhờ SSO đang tồn tại không nhất thiết có nghĩa người dùng vừa xuất trình yếu tố xác thực. Policy phải dựa trên thông tin được xác minh và mức bảo đảm phù hợp cho hành động nhạy cảm.

## 5. Gắn bằng chứng với một kế hoạch hợp nhất cụ thể

Một bằng chứng dùng chung kiểu “đã xác thực tài khoản B trong hôm nay” có thể bị lạm dụng cho phép hợp nhất khác. Hãy tạo một **merge intent** trước khi thu thập bằng chứng, chứa đề xuất bất biến hoặc có phiên bản rõ ràng.

```text
MergeIntent
  intent_id
  tenant_id hoặc phạm vi tenant được policy cho phép
  source_account_id
  destination_account_id
  proposal_version
  allowed_data_categories
  credential_and_session_plan
  policy_version
  expires_at
  state
```

Tài khoản nguồn là bên có dữ liệu hoặc liên kết được chuyển; tài khoản đích là bên được giữ lại theo kế hoạch. Đảo chiều nguồn và đích có thể thay đổi kết quả nên phải được coi là thay đổi đề xuất, không phải tùy chọn hiển thị.

Bằng chứng cho từng bên cần liên kết tối thiểu tới:

```text
intent_id + proposal_version + proposal_digest
account_id + proof_purpose + challenge_id
verified_authentication_reference
verified_at + expires_at + consumption_state
```

`proof_purpose` cho biết bằng chứng dành cho tài khoản nguồn hay đích của phép hợp nhất. Challenge cần không thể đoán trước, có thời hạn và được kiểm tra phía máy chủ. Một nonce chỉ được ghi vào URL nhưng không được đối chiếu với trạng thái đáng tin cậy không tạo ra ràng buộc có ích.

Chữ ký hoặc hash không tự thay thế kiểm tra ngữ cảnh. Hash đề xuất giúp kiểm tra nội dung khớp nếu việc tạo và lưu được bảo vệ. Chữ ký trên một assertion phải được kiểm tra cùng issuer, audience, thời hạn, mục đích và khả năng bị phát lại theo kiến trúc sử dụng.

Nếu đổi tài khoản đích, hướng hợp nhất, phạm vi dữ liệu hoặc kế hoạch xử lý thông tin xác thực, phải tạo phiên bản mới và yêu cầu các bằng chứng hoặc sự đồng ý bị ảnh hưởng được thiết lập lại theo policy. Không lấy bằng chứng cho một đề xuất nhỏ để thực hiện đề xuất lớn hơn.

## 6. Luồng chứng minh quyền với cả hai tài khoản

Một luồng tự phục vụ có kiểm soát có thể đi qua các bước sau:

1. Người dùng xác thực vào tài khoản đang dùng và chọn tính năng hợp nhất trong giao diện chính thức.
2. Máy chủ tạo merge intent, cố định tài khoản nguồn, đích và kế hoạch dự kiến.
3. Người dùng xác thực lại cho tài khoản thứ nhất theo yêu cầu của policy.
4. Máy chủ tạo bằng chứng thứ nhất gắn với đúng intent và account ID đã xác minh.
5. Người dùng hoàn tất một luồng xác thực riêng cho tài khoản thứ hai.
6. Máy chủ kiểm tra kết quả thuộc đúng tài khoản thứ hai và tạo bằng chứng tương ứng.
7. Người dùng xem lại hướng, phạm vi, xung đột và hậu quả của việc hợp nhất; hệ thống ghi nhận sự đồng ý cần thiết cho cả hai bên.
8. Máy chủ kiểm tra lại toàn bộ điều kiện ngay trước khi tiêu thụ quyền thực thi.

Việc xác thực riêng không nhất thiết bắt buộc hai thiết bị hoặc hai người khác nhau. Nó có nghĩa mỗi tài khoản phải có bằng chứng được kiểm tra đúng, không suy ra B đã được xác minh chỉ vì phiên hiện tại đăng nhập A.

Hai luồng có thể diễn ra trong cùng trình duyệt hoặc qua các phiên khác nhau nếu thiết kế hỗ trợ. Trong cả hai trường hợp, kết quả phải quay về đúng intent và đúng bên. Không dùng một cờ toàn cục trong session như `secondAccountVerified=true` mà không biết tài khoản nào, đề xuất nào và thời hạn nào.

### Ngăn nhầm phiên và đăng nhập do kẻ tấn công dẫn dắt

Luồng cần chống CSRF, nhầm tài khoản và tráo kết quả xác thực theo giao thức triển khai. Không để một trang ngoài tự khởi tạo hoặc hoàn tất hợp nhất bằng phiên người dùng đang mở. Callback phải gắn với trạng thái khởi tạo được máy chủ quản lý và không được tin các tham số nhận dạng từ client.

Hiển thị rõ tài khoản nào vừa được xác minh và tài khoản nào được giữ lại. Đăng nhập thành công vào một tài khoản do kẻ tấn công chuẩn bị sẵn không được âm thầm gắn dữ liệu của nạn nhân vào tài khoản đó. Một chuyển hướng về trang “thành công” chỉ là kết quả điều hướng, không phải bằng chứng hay sự đồng ý cuối cùng.

Người dùng cần có khả năng hủy. Hủy intent làm mất hiệu lực các quyền tiếp tục liên quan theo policy; một callback đến muộn không được tự khôi phục intent đã hủy.

## 7. Khi một tài khoản đang mất quyền truy cập

Tình huống thường gặp là người dùng đăng nhập được A nhưng nói B là tài khoản cũ của mình, hiện đã mất mật khẩu và MFA. Lời khai đó là lý do để bắt đầu quy trình khôi phục B, không phải bằng chứng đủ để chuyển B vào A.

Luồng phù hợp là:

```text
Đang kiểm soát A
    ↓
Không xác thực được B
    ↓
Thực hiện quy trình khôi phục B theo policy của B
    ↓
Hoàn tất xác minh danh tính, đánh giá rủi ro và các điều kiện bắt buộc
    ↓
Tái lập khả năng xác thực cho B
    ↓
Đánh giá riêng việc B có được tham gia hợp nhất hay chưa
    ↓
Tạo hoặc làm mới bằng chứng hợp nhất cho A và B
```

Không gửi token khôi phục của B đến email mới gắn với A chỉ vì người yêu cầu đang đăng nhập A. Kênh nhận của quy trình khôi phục B phải được chấp nhận theo policy của B. Nếu cần đổi kênh vì mất quyền truy cập, việc đổi đó cũng cần được xác minh chứ không được suy ra từ tài khoản đích mong muốn.

Một token khôi phục B chỉ nên có phạm vi đã được cấp. Token cho phép đăng ký lại MFA không mặc nhiên cho phép hợp nhất dữ liệu. Không chuyển token đó sang endpoint hợp nhất như thể nó là một phiên xác thực đầy đủ.

Tài khoản vừa được khôi phục có thể cần thời gian chờ, xác thực tăng cường hoặc kiểm tra thủ công trước một thay đổi khó đảo ngược. Policy phải xác định tiêu chí và thời gian theo rủi ro; không có một số phút chung phù hợp cho mọi dịch vụ. Việc vừa thay email, vừa khôi phục MFA rồi yêu cầu hợp nhất ngay là chuỗi thay đổi cần được đánh giá cùng nhau.

Nếu không thể thu thập bằng chứng đủ mạnh cho B, giữ yêu cầu ở trạng thái chờ, từ chối hoặc chuyển đúng quy trình được cho phép. Nhân viên hỗ trợ không nên tự đặt `ownership_verified=true` vì hồ sơ hai bên trông giống nhau. Phê duyệt của quản trị viên có thể là điều kiện bổ sung, nhưng không tự biến bằng chứng yếu thành quyền sở hữu đã được xác lập.

## 8. Bằng chứng và sự đồng ý phải khớp nhau

Một người có thể đăng nhập được hai tài khoản nhưng không hiểu rằng thao tác sắp xóa một danh tính, thay đổi liên kết đăng nhập hoặc chuyển dữ liệu. Vì vậy cần ghi nhận sự đồng ý đối với kế hoạch cụ thể sau khi đã trình bày rõ hậu quả.

Nội dung xác nhận nên nêu ít nhất:

- Tài khoản nào là nguồn và tài khoản nào được giữ lại.
- Nhóm dữ liệu được chuyển, dữ liệu bị loại trừ và xung đột chưa giải quyết.
- Các phương thức đăng nhập nào được giữ, loại bỏ hoặc cần đăng ký lại.
- Vai trò, thành viên tổ chức và quyền đặc biệt được xử lý thế nào.
- Các phiên cũ sẽ bị thu hồi hoặc bị hạn chế ra sao.
- Khả năng hủy, thời điểm bắt đầu thực thi và giới hạn hoàn tác.

Không áp dụng quy tắc cộng dồn mọi quyền. Nếu A là tài khoản cá nhân và B có một vai trò được tổ chức cấp, bằng chứng kiểm soát B chưa chắc cho phép mang vai trò đó sang A. Các quyền gắn với tổ chức hoặc điều kiện tuyển dụng cần được xác định lại theo nguồn cấp quyền có thẩm quyền.

Tương tự, một tài nguyên dùng chung không trở thành tài sản riêng của người hợp nhất chỉ vì họ có quyền đọc nó. Kế hoạch cần phân biệt tài nguyên thuộc sở hữu, thành viên nhóm và quyền được chia sẻ.

Phương thức xác thực cũng không nên được cộng dồn mù quáng. Một mật khẩu cũ hoặc kênh khôi phục yếu từ tài khoản nguồn có thể làm giảm mức bảo vệ của tài khoản đích. Kế hoạch giữ hoặc loại bỏ thông tin xác thực phải được policy cho phép, có sự đồng ý thích hợp và kiểm tra lại trước thực thi.

Các quyết định và sự đồng ý phải gắn với cùng phiên bản, dấu vân tay đề xuất và tài khoản. Nếu một bên đồng ý chuyển dữ liệu học tập nhưng đề xuất sau đó thêm dữ liệu thanh toán, không dùng sự đồng ý cũ để chuyển cả hai.

## 9. Ví dụ Java: kiểm tra ràng buộc của một bằng chứng

Ví dụ sau minh họa riêng việc một bản ghi bằng chứng có khớp với tài khoản và đề xuất đang xét hay không. Các đối tượng phải được nạp từ kho dữ liệu do máy chủ quản lý sau khi đã xác minh xác thực. Không nhận một đối tượng `OwnershipProof` do client tự khai báo rồi tin nó.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

enum ProofPurpose {
    SOURCE_ACCOUNT,
    DESTINATION_ACCOUNT
}

record MergeIntent(
        UUID id,
        UUID tenantId,
        UUID sourceAccountId,
        UUID destinationAccountId,
        long proposalVersion,
        String proposalDigest,
        Instant expiresAt) {
}

record OwnershipProof(
        UUID intentId,
        UUID tenantId,
        UUID accountId,
        ProofPurpose purpose,
        long proposalVersion,
        String proposalDigest,
        Instant verifiedAt,
        Instant expiresAt) {
}

final class ProofBinding {
    static boolean matches(
            MergeIntent intent,
            OwnershipProof proof,
            ProofPurpose expectedPurpose,
            Instant trustedNow) {

        if (intent == null || proof == null || trustedNow == null
                || expectedPurpose == null
                || intent.id() == null || intent.tenantId() == null
                || intent.sourceAccountId() == null
                || intent.destinationAccountId() == null
                || intent.proposalDigest() == null
                || intent.expiresAt() == null
                || proof.verifiedAt() == null
                || proof.expiresAt() == null) {
            return false;
        }

        if (intent.sourceAccountId().equals(intent.destinationAccountId())
                || !trustedNow.isBefore(intent.expiresAt())
                || !trustedNow.isBefore(proof.expiresAt())
                || proof.verifiedAt().isAfter(trustedNow)) {
            return false;
        }

        UUID expectedAccount = expectedPurpose == ProofPurpose.SOURCE_ACCOUNT
                ? intent.sourceAccountId()
                : intent.destinationAccountId();

        return Objects.equals(intent.id(), proof.intentId())
                && Objects.equals(intent.tenantId(), proof.tenantId())
                && Objects.equals(expectedAccount, proof.accountId())
                && expectedPurpose == proof.purpose()
                && intent.proposalVersion() == proof.proposalVersion()
                && Objects.equals(
                        intent.proposalDigest(), proof.proposalDigest());
    }
}
```

Luồng gọi cần kiểm tra một bằng chứng với `SOURCE_ACCOUNT` và bằng chứng khác với `DESTINATION_ACCOUNT`. Do account ID và mục đích đều phải khớp, không thể dùng một bằng chứng cho A để thay thế bằng chứng của B.

`trustedNow` phải lấy từ thời gian đáng tin cậy phía máy chủ, không lấy từ client. Hạn của bằng chứng phải được tính từ policy và tham chiếu xác thực thực tế; việc đoạn mã thấy `expiresAt` còn tương lai không có nghĩa một hạn do người dùng tự chọn là hợp lệ.

Phương thức này không kiểm tra toàn bộ điều kiện bảo mật: nó chưa xử lý trạng thái bị thu hồi hoặc đã tiêu thụ, mức bảo đảm xác thực, độ mới tối đa theo policy, sự đồng ý, rủi ro và quyền chuyển tài nguyên. Các điều kiện đó phải được kiểm tra trong cổng thực thi. Mô hình ví dụ giới hạn cùng một tenant; luồng liên tenant cần chính sách và kiểm soát riêng, không bỏ kiểm tra tenant để làm cho ví dụ chấp nhận được.

## 10. Thời hạn, thu hồi và thực thi một lần

Quyền kiểm soát được chứng minh tại một thời điểm không phải quyền vĩnh viễn. Trong lúc yêu cầu chờ, một tài khoản có thể bị khóa, người dùng báo bị chiếm, mật khẩu thay đổi hoặc liên kết danh tính bị thu hồi.

Bằng chứng cần có thời hạn phù hợp, tham chiếu sự kiện xác thực và trạng thái có thể vô hiệu hóa. Những thay đổi bảo mật có liên quan phải khiến cổng thực thi đánh giá lại hoặc yêu cầu bằng chứng mới theo policy. Không chỉ kiểm tra chữ ký rồi bỏ qua trạng thái tài khoản hiện tại.

### Kiểm tra ngay trước khi sử dụng

Ngay trước thực thi, máy chủ cần xác minh:

1. Intent đang ở trạng thái cho phép và chưa hết hạn hoặc bị hủy.
2. Cả hai tài khoản vẫn đúng định danh, đúng phạm vi và đủ điều kiện hợp nhất.
3. Bằng chứng mỗi bên khớp phiên bản, mục đích, phạm vi và thời hạn.
4. Không có bằng chứng bị thu hồi hoặc đã tiêu thụ trái với contract.
5. Mức bảo đảm, độ mới xác thực và điều kiện sau khôi phục vẫn đạt policy.
6. Sự đồng ý, phê duyệt bổ sung nếu có và đánh giá rủi ro vẫn hợp lệ.
7. Trạng thái tài khoản không bị một phép hợp nhất hoặc thay đổi cạnh tranh làm lệch kế hoạch.

Kiểm tra ở màn hình xác nhận rồi thực thi sau bằng một cờ `canMerge=true` do client gửi tạo ra khoảng trống giữa kiểm tra và sử dụng. Không để client tự quyết định rằng các điều kiện trước đó vẫn đúng.

Trong cơ sở dữ liệu có giao dịch, có thể khóa hoặc kiểm tra phiên bản của intent, hai tài khoản và các bằng chứng liên quan; kiểm tra điều kiện rồi ghi việc tiêu thụ cùng kế hoạch thực thi trong một giao dịch. Các đường hủy, thu hồi bằng chứng và thay đổi tài khoản phải tuân thủ cơ chế phối hợp tương ứng. Khóa một hàng không tự khóa mọi tác dụng phụ ở hệ thống bên ngoài.

Nếu bằng chứng phụ thuộc nhà cung cấp danh tính hoặc hệ thống quyền bên ngoài, cần xác định độ mới chấp nhận được, cách nhận biết thu hồi và cách xử lý khi không xác minh được. Giao dịch cục bộ không bảo đảm trạng thái bên ngoài bất biến trong suốt quá trình.

### Phân biệt challenge, proof và execution

Challenge được sử dụng để tạo bằng chứng sau khi xác minh thành công; nó không nên được phát lại để tạo vô hạn bằng chứng mới. Proof là bản ghi đã xác minh, gắn với intent và được kiểm tra hiệu lực khi sử dụng. Execution là lần thực thi kế hoạch được chấp nhận.

Ba vòng đời này cần liên kết nhưng không được trộn thành một token toàn năng. Một token dùng để hoàn tất xác thực thứ hai không nên đồng thời là quyền tải dữ liệu, quyền đổi email và quyền thực thi lại phép hợp nhất.

Khi thực thi có nhiều dịch vụ, cần một execution ID và cơ chế tiếp tục hoặc đối soát từng bước. Timeout không chứng minh rằng chưa có thay đổi. Lần gọi lại phải tra cứu hoặc tiếp tục kế hoạch cũ theo khóa chống trùng, không tạo lượt hợp nhất mới với bằng chứng đã dùng.

Các bước có thể hoàn tất từng phần cần được ghi nhận để xử lý sự cố. Không tự khôi phục mật khẩu cũ, cấp thêm quyền hoặc chuyển thêm dữ liệu như một cách “sửa cho xong” ngoài kế hoạch được cho phép.

## 11. Đánh giá rủi ro và bảo vệ thông tin trong quá trình chứng minh

Những tín hiệu sau cần được xem xét theo policy:

- Tài khoản vừa được khôi phục hoặc vừa thay nhiều yếu tố xác thực.
- Người yêu cầu chỉ chứng minh được email chung nhưng không xác thực được một bên.
- Tài khoản đích mới tạo muốn nhận dữ liệu lâu năm hoặc quyền đặc biệt.
- Hai tài khoản thuộc các tổ chức, tenant hoặc loại chủ thể khác nhau.
- Luồng xác thực thứ hai trả về principal khác với tài khoản được chọn.
- Nhiều lần thử thay nguồn, đích hoặc tái sử dụng challenge đã hết hạn.
- Có cảnh báo chiếm tài khoản hoặc yêu cầu hủy từ một bên có quyền.

Các tín hiệu mạng và thiết bị giúp đánh giá nhưng không tự chứng minh cùng chủ. Hai tài khoản đăng nhập từ cùng một IP có thể là hai người khác nhau; một người có thể dùng nhiều mạng hợp lệ. Không dùng tương đồng thiết bị để thay bằng chứng xác thực.

Giới hạn tốc độ tạo intent, yêu cầu challenge, nhập mã và thử xác thực theo các chiều phù hợp. Không để người thử nhiều account ID dò được tài khoản nào có MFA, email nào đang dùng hoặc ai sở hữu dữ liệu. Phản hồi công khai nên tiết lộ ít thông tin; chi tiết cần thiết chỉ xuất hiện sau khi xác thực và phân quyền thích hợp.

Không yêu cầu người dùng gửi mật khẩu, backup code hoặc khóa bí mật cho nhân viên hỗ trợ để “chứng minh sở hữu”. Thông tin xác thực nên được nhập vào giao diện xác thực chính thức. Nhân viên xem kết quả xác minh và hồ sơ cần thiết, không thu thập lại các bí mật đó qua chat hoặc ticket.

Nếu có xử lý bằng chứng danh tính, giới hạn dữ liệu thu thập, người được xem và thời hạn lưu. Một tham chiếu đến kết quả xác minh có thể đủ cho hồ sơ hợp nhất; không mặc nhiên sao chép giấy tờ thô vào mọi hệ thống tham gia.

Thông báo cho các bên qua kênh phù hợp với policy để họ nhận biết yêu cầu và kết quả. Không đưa bí mật hay toàn bộ thông tin của tài khoản kia vào email, đặc biệt khi quyền với cả hai bên chưa được xác lập. Link thông báo chỉ nên định vị hồ sơ; nó không tự cấp quyền hợp nhất.

## 12. Nhật ký cần chứng minh được điều gì?

Hồ sơ truy vết nên giúp giải thích vì sao một phép hợp nhất được cho phép mà không cần lưu bí mật xác thực. Có thể ghi:

```text
intent_id, proposal_version, proposal_digest
source_account_id, destination_account_id, tenant_scope
proof_id_for_source, proof_id_for_destination
verified_authentication_reference, assurance_policy_result
verified_at, proof_expires_at, invalidation_reason
consent_reference, approval_reference_if_required
risk_decision_reference, policy_version
execution_id, outcome, occurred_at, actor_reference
```

Ghi nhận cả các lần từ chối do sai tài khoản, sai mục đích, hết hạn hoặc phát lại. Không ghi token đầy đủ, mật khẩu, mã MFA hoặc nguyên assertion nhạy cảm vào log vận hành thông thường.

Nhật ký cần phân biệt “đã nhận được dữ liệu xác thực”, “đã xác minh bằng chứng”, “đã đồng ý” và “đã tiêu thụ quyền thực thi”. Nếu chỉ ghi một dòng `ownership passed`, người điều tra khó biết bằng chứng thuộc bên nào hoặc đã bị áp dụng cho đề xuất nào.

Những người có quyền xử lý hợp nhất không nên đồng thời có thể sửa tùy ý lịch sử để che giấu hành động. Quyền truy cập nhật ký và hồ sơ bằng chứng cần được giới hạn, còn các định danh lịch sử cần giữ được khả năng đối chiếu sau khi tài khoản nguồn bị vô hiệu hóa theo kế hoạch.

## 13. Tình huống xuyên suốt

Linh có tài khoản A dùng mật khẩu và tài khoản B đăng nhập qua một nhà cung cấp danh tính. Linh muốn giữ A và chuyển dữ liệu học tập cá nhân từ B sang A. Hai tài khoản hiển thị cùng email, nhưng hệ thống không tự nối chúng dựa trên email đó.

Máy chủ tạo intent với A là đích, B là nguồn và phạm vi chỉ gồm dữ liệu học tập được phép chuyển. Linh xác thực lại A, sau đó thực hiện luồng đăng nhập liên kết cho B. Hệ thống kiểm tra kết quả thuộc đúng principal đã liên kết với B rồi tạo hai bằng chứng riêng, cùng gắn với intent và phiên bản đề xuất.

Giả sử nhà cung cấp tự chọn một phiên đăng nhập khác và trả về principal của tài khoản C. Hệ thống không coi việc đăng nhập thành công đó là bằng chứng cho B. Luồng yêu cầu chọn lại hoặc dừng; dữ liệu B chưa được đọc hay chuyển.

Sau khi xác minh đúng B, Linh đề nghị đổi hướng để giữ B thay vì A. Đây là đề xuất khác vì tài khoản được giữ lại và kế hoạch xử lý phương thức đăng nhập thay đổi. Hệ thống làm mới phiên bản và các xác nhận cần thiết, không dùng nguyên quyền cho hướng cũ.

Trong một lần thử khác, Linh không thể đăng nhập B vì đã mất thiết bị xác thực. Hệ thống đưa Linh qua quy trình khôi phục B theo policy, thay vì gửi token của B sang A để bỏ qua kiểm tra. Khi quyền truy cập B được tái lập, yêu cầu hợp nhất vẫn được đánh giá riêng, bao gồm điều kiện đối với tài khoản vừa khôi phục.

Cuối cùng, khi đề xuất hợp lệ đủ bằng chứng và sự đồng ý, máy chủ tiêu thụ quyền thực thi một lần cho đúng kế hoạch. Tài nguyên dùng chung và vai trò tổ chức không tự được cộng dồn. Các phiên và phương thức đăng nhập được xử lý theo kế hoạch đã chấp nhận, còn nhật ký liên kết được bằng chứng của cả hai bên với kết quả thực tế.

Account ownership proof bảo vệ ranh giới giữa “tôi đang dùng một tài khoản” và “tôi được phép chuyển quyền đối với cả hai tài khoản này”. Ranh giới đó chỉ được giữ khi bằng chứng có nguồn đáng tin cậy, đúng đối tượng, đủ mới, có phạm vi, có thể thu hồi và được kiểm tra tại thời điểm sử dụng.
