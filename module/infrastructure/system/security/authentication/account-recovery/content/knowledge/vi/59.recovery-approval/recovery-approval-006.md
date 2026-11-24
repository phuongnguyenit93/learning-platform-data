# Approval rejection

## 1. Từ chối phê duyệt nghĩa là gì?

Trong quy trình khôi phục tài khoản, một approval request đề nghị cho phép các thay đổi cụ thể như reset mật khẩu, thay thế đăng ký MFA hoặc đăng ký passkey thay thế. **Approval rejection** là việc người có thẩm quyền không chấp nhận đề nghị đó, theo chính sách xét duyệt áp dụng cho request.

Trong phạm vi `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, kết quả từ chối phải chặn đúng quyền recovery đang được đề nghị, bảo toàn dấu vết quyết định và giúp người yêu cầu biết tuyến tiếp tục được phép. Nó không tự xác nhận người yêu cầu là kẻ gian, cũng không tự cấp quyền khóa hoặc xóa tài khoản gốc.

Cần phân biệt hai sự kiện:

- **Một phiếu từ chối**: quyết định của một người xét duyệt đối với một revision của đề nghị.
- **Request bị từ chối**: kết quả cuối cùng khi quy tắc quyết định của request đã được thỏa mãn.

Trong mô hình một người duyệt, hai sự kiện thường xảy ra cùng lúc. Trong mô hình nhiều người duyệt, một phiếu có thể khiến request kết thúc ngay hoặc chỉ được ghi nhận để tiếp tục xét, tùy chính sách.

Ví dụ: một đề nghị thay MFA yêu cầu hai người xem xét. Nếu chính sách quy định bất kỳ một người nào từ chối cũng kết thúc request, phiếu đầu tiên mang ý nghĩa phủ quyết. Nếu chính sách yêu cầu hai phiếu từ chối, phiếu thứ nhất chưa đủ để chuyển trạng thái cuối. Backend phải thực thi quy tắc đã chọn; giao diện không được tự suy diễn từ số nút được bấm.

## 2. Phân biệt rejection với các kết quả khác

Không nên dùng “Reject” cho mọi tình huống chưa thể phê duyệt.

| Kết quả | Ý nghĩa | Tác động đúng |
|---|---|---|
| `REJECT` | Người có thẩm quyền không chấp nhận đề nghị hiện tại | Ghi phiếu; có thể kết thúc request theo chính sách |
| `REQUEST_INFORMATION` | Cần bổ sung một loại thông tin được phép | Chuyển sang chờ thông tin hoặc tạo revision mới theo hợp đồng |
| `ESCALATE` | Người đang xử lý không đủ thẩm quyền hoặc cần chuyên gia | Chuyển tuyến, giữ nguyên giới hạn recovery |
| `EXPIRED` | Request đã quá thời hạn | Không nhận quyết định mới cho request đó |
| `CANCELLED` | Request bị hủy theo một hành động hợp lệ | Kết thúc đề nghị mà không giả lập phiếu từ chối |
| Lỗi hệ thống | Không hoàn tất thao tác do sự cố | Báo chưa xác định kết quả hoặc cho retry; không tự ghi rejection |

Các trạng thái và tên sự kiện ở đây là minh họa. Điều quan trọng là lưu đúng bản chất nghiệp vụ.

Nếu công cụ xem bằng chứng bị lỗi kết nối, nhân viên chưa có đủ dữ liệu để quyết định. Không nên ghi “bằng chứng không hợp lệ” chỉ vì ảnh chưa tải được. Nếu có tín hiệu xung đột chưa được giải quyết, tuyến chuyên trách có thể phù hợp hơn một nhãn gian lận.

Từ chối phê duyệt cũng khác với support denial của toàn case. Một request có thể bị từ chối do đề nghị quá rộng, trong khi case vẫn được phép thu thập thêm bằng chứng. Chính sách cũng có thể quy định rằng rejection này kết thúc luôn tuyến recovery hiện tại. Hai đối tượng phải có trạng thái và quy tắc chuyển riêng.

## 3. Những bất biến cần giữ

Một thiết kế an toàn duy trì các điều kiện sau:

1. Chỉ người đang có thẩm quyền đối với đúng request và tenant mới được bỏ phiếu từ chối.
2. Phiếu được gắn với revision và nội dung đề nghị mà người duyệt thực sự đã xem.
3. Cùng một người không thể vừa đồng ý vừa từ chối trong cùng vòng xét duyệt nếu chính sách chỉ cho một quyết định.
4. Request ở trạng thái kết thúc không bị một request HTTP đến muộn ghi đè sang kết quả khác.
5. Khi request đã bị từ chối, không thể dùng nó để cấp hoặc tiêu thụ quyền recovery.
6. Mọi thay đổi tài khoản cần kiểm tra quyền hợp lệ ở backend, không dựa vào giao diện đã ẩn nút.
7. Quyết định từ chối không tự khóa tài khoản, đổi thông tin xác thực hoặc thu hồi các phiên không thuộc phạm vi được cho phép.
8. Retry không tạo thêm phiếu, thêm sự kiện kết thúc hoặc thông báo lặp ngoài ý muốn.
9. Lịch sử quyết định được giữ lại khi có khiếu nại hoặc một lần xét duyệt mới.

Một mã request khó đoán chỉ giúp giảm khả năng đoán mò. Nó không thay thế kiểm tra quyền. Người có link vẫn phải được xác thực và phân quyền theo cơ chế của sản phẩm.

## 4. Kiểm tra thẩm quyền trước khi nhận phiếu

Tại thời điểm người duyệt bấm từ chối, hệ thống cần kiểm tra lại:

- Danh tính và phiên của người thao tác có hợp lệ hay không.
- Người đó có quyền xét duyệt loại recovery và phạm vi tài khoản này hay không.
- Tenant của người thao tác có khớp với tenant của request hay không.
- Người đó có thuộc tuyến duyệt hiện hành và có bị giới hạn phạm vi hay không.
- Chính sách có yêu cầu xác thực lại hoặc yếu tố mạnh trước quyết định hay không.
- Quy tắc tách người đề nghị và người duyệt có được đáp ứng hay không.
- Request có còn chờ xét, chưa hết hạn và chưa bị thay thế hay không.

Danh sách người duyệt được chụp lúc tạo request phục vụ định tuyến và kiểm toán. Nó không mặc nhiên bảo đảm quyền hiện tại: một nhân viên có thể đã chuyển nhóm hoặc bị thu hồi quyền.

Người yêu cầu recovery không được tự thêm mình vào danh sách người duyệt thông qua địa chỉ email mới. Tương tự, một ghi chú “quản lý đã đồng ý cho tôi xử lý” không thay thế kiểm tra phân quyền trên hệ thống.

Nếu quyền đã mất, không ghi phiếu rồi mới báo lỗi. Hệ thống phải từ chối thao tác xử lý request, đồng thời không tiết lộ thêm dữ liệu mà người đó không còn được xem.

## 5. Ràng buộc quyết định với đúng nội dung

Người duyệt cần biết rõ họ đang từ chối điều gì:

```text
Request: ar_example_608
Proposal revision: 4
Requested actions: REPLACE_MFA_ENROLLMENT
Evidence assessment: assessment_example_311_v2
Risk assessment: risk_example_924_v3
Policy version: recovery-policy-example-v6
```

Không nên chỉ hiển thị một nút “Từ chối tài khoản”. Đối tượng bị xét là một đề nghị có phạm vi, không phải toàn bộ tư cách của chủ tài khoản.

Khi gửi quyết định, client có thể kèm revision và phiên bản request đã đọc. Backend đối chiếu với dữ liệu hiện hành. Nếu đề nghị đã đổi từ reset mật khẩu sang thay MFA, không áp dụng quyết định của màn hình cũ cho payload mới.

Một lựa chọn đơn giản là làm payload đề nghị bất biến sau khi gửi. Thay đổi phạm vi, kênh nhận quyền hoặc bằng chứng có ý nghĩa sẽ tạo revision hay vòng xét duyệt mới. Phiếu cũ vẫn tồn tại trong lịch sử nhưng không tự chuyển thành phiếu cho revision mới.

Với bằng chứng bổ sung không thay đổi payload, chính sách vẫn phải xác định có cần yêu cầu người duyệt đọc lại hay không. Không để một phiếu được ghi dựa trên tài liệu mà người duyệt chưa có cơ hội xem.

## 6. Quy tắc một phiếu và nhiều phiếu

Các mô hình thường gặp có ngữ nghĩa khác nhau:

| Mô hình | Khi nào rejection kết thúc request? | Điều cần định nghĩa |
|---|---|---|
| Một người quyết định | Khi một người hợp lệ từ chối | Cách chọn người có quyền quyết định |
| Một phiếu phủ quyết | Khi có ít nhất một phiếu từ chối hợp lệ trong lúc đang chờ | Phạm vi và thời điểm quyền phủ quyết còn hiệu lực |
| Ngưỡng từ chối | Khi đủ số người khác nhau từ chối | Ngưỡng, tập người đủ điều kiện và cách xử lý xung đột |
| Người quyết định cuối | Phiếu nhóm là khuyến nghị; người được chỉ định kết luận | Phân biệt phiếu tư vấn và quyết định có hiệu lực |

Ngưỡng đồng ý và ngưỡng từ chối phải được thiết kế cùng nhau. Không chỉ viết “hai người đồng ý thì approve” ở một service và “một người từ chối thì reject” ở service khác mà không quy định thứ tự kết thúc.

Ví dụ, nếu hệ thống chốt ngay sau hai phiếu đồng ý, người thứ ba gửi từ chối sau khi đã chốt không còn là một phiếu phủ quyết có hiệu lực cho request đó. Nếu nghiệp vụ yêu cầu mọi người bắt buộc có quyền phủ quyết trước khi chấp thuận, hệ thống phải chờ đủ người hoặc một cửa sổ xét duyệt được xác định; không thể vừa chốt sớm vừa bảo đảm mọi phiếu tương lai đều có quyền đảo ngược.

Nếu nhiều điều kiện kết thúc có thể đồng thời đúng, chính sách cần nêu rõ cách giải quyết, chẳng hạn ưu tiên rejection khi cùng đánh giá một tập phiếu chưa kết thúc. Cả ghi phiếu và đánh giá kết quả phải diễn ra theo một thứ tự được hệ thống bảo đảm, tránh mỗi node tự kết luận theo snapshot khác nhau.

Không thay đổi ngưỡng giữa chừng một cách âm thầm. Khi quyền thành viên hoặc chính sách thay đổi đáng kể, có thể cần hủy và mở vòng xét duyệt mới. Việc áp dụng thay đổi khẩn cấp phải có quy tắc và dấu vết riêng.

## 7. Minh họa kiểm tra ngưỡng rejection bằng Java

Đoạn mã sau chỉ trả lời một câu hỏi: tập phiếu từ chối đã được xác thực có đạt ngưỡng từ chối hay chưa. Nó không tính điều kiện chấp thuận, không phân quyền người gọi và không cập nhật cơ sở dữ liệu.

```java
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public final class RejectionThreshold {
    public boolean reached(
            Set<UUID> eligibleReviewers,
            Set<UUID> validatedRejectingReviewers,
            int requiredRejectVotes) {
        Objects.requireNonNull(eligibleReviewers);
        Objects.requireNonNull(validatedRejectingReviewers);

        Set<UUID> eligible = Set.copyOf(eligibleReviewers);
        Set<UUID> rejected = Set.copyOf(validatedRejectingReviewers);

        if (eligible.isEmpty()
                || requiredRejectVotes < 1
                || requiredRejectVotes > eligible.size()) {
            throw new IllegalArgumentException("Invalid rejection threshold");
        }

        if (!eligible.containsAll(rejected)) {
            throw new IllegalArgumentException("Reviewer outside eligible set");
        }

        return rejected.size() >= requiredRejectVotes;
    }
}
```

Trong mô hình một phiếu phủ quyết, `requiredRejectVotes` bằng 1. Trong mô hình ngưỡng, giá trị do chính sách server cung cấp, không lấy từ JSON của người dùng.

`validatedRejectingReviewers` phải được tổng hợp từ các phiếu đã qua kiểm tra: cùng request, cùng revision, đúng thẩm quyền và chưa bị loại theo chính sách. Không nhận danh sách này trực tiếp từ client.

Kiểu `Set` tránh đếm cùng một mã người nhiều lần trong phép tính. Tuy nhiên, chống ghi phiếu trùng vẫn cần ràng buộc tại nơi lưu; không thể chỉ dựa vào việc chuyển một danh sách thành `Set` sau khi đã chấp nhận các quyết định mâu thuẫn.

Kết quả `false` chỉ có nghĩa **chưa đủ ngưỡng từ chối**. Nó không đồng nghĩa được chấp thuận. Luồng quyết định đầy đủ còn phải xét điều kiện approve, thời hạn, trạng thái case và thứ tự kết thúc theo chính sách.

## 8. API nhận quyết định từ chối

Một endpoint minh họa dành cho công cụ xét duyệt:

```http
POST /recovery-approval-requests/ar_example_608/decisions
Content-Type: application/json
Idempotency-Key: rejection-example-771

{
  "proposalRevision": 4,
  "expectedVersion": 12,
  "decision": "REJECT",
  "reasonCode": "EVIDENCE_REQUIREMENTS_NOT_MET",
  "comment": "Bằng chứng được đánh giá chưa đáp ứng điều kiện của tuyến này."
}
```

Danh tính người duyệt lấy từ phiên đã xác thực. Server không cho client quyết định `reviewerId`, tenant, số phiếu đã có hoặc trạng thái cuối của request.

Nếu dùng cookie, endpoint thay đổi trạng thái cần cơ chế chống request giả mạo phù hợp. Link trong email chỉ mở trang; không sử dụng GET để ghi phiếu, vì trình quét email có thể tự mở link.

Phản hồi cần phân biệt ghi nhận phiếu và kết thúc request:

```json
{
  "decisionRecorded": true,
  "recordedDecision": "REJECT",
  "requestState": "PENDING_REVIEW",
  "message": "Đã ghi nhận quyết định; vòng xét duyệt chưa kết thúc."
}
```

Nếu phiếu này đạt điều kiện kết thúc, `requestState` có thể là `REJECTED`. Không trả cùng một thông điệp “đã từ chối recovery” cho cả hai trường hợp.

Các chi tiết như số phiếu, danh tính người duyệt khác và lý do nội bộ chỉ hiển thị khi người gọi có quyền. API dành cho người yêu cầu recovery nên có một hợp đồng phản hồi riêng, tránh lộ cấu trúc xét duyệt hoặc dữ liệu chống gian lận.

## 9. Giao dịch ghi phiếu và chốt rejection

Một thao tác từ chối bền vững thường gồm:

1. Xác thực, kiểm tra quyền và kiểm tra đầu vào cơ bản.
2. Bắt đầu giao dịch, đọc hoặc khóa request theo chiến lược đồng thời đã chọn.
3. Kiểm tra trạng thái, hạn dùng, proposal revision và các điều kiện liên quan của case.
4. Kiểm tra người duyệt còn đủ điều kiện trong ngữ cảnh hiện hành.
5. Kiểm tra idempotency và phiếu trước đó của cùng người trong cùng vòng.
6. Ghi phiếu từ chối cùng mã lý do, chủ thể, thời điểm và phiên bản chính sách.
7. Đánh giá điều kiện kết thúc dựa trên tập phiếu hợp lệ.
8. Nếu đủ điều kiện, chuyển request sang `REJECTED` và vô hiệu hóa khả năng cấp quyền recovery của request.
9. Cập nhật case theo chính sách, ghi audit và outbox cần thiết.
10. Commit rồi gửi phản hồi; xử lý thông báo ở bước riêng.

Có thể dùng ràng buộc duy nhất cho `(request_id, proposal_revision, reviewer_id)` nếu mỗi người chỉ có một phiếu trong một vòng. Nếu người dùng gửi lại cùng quyết định, trả kết quả đã lưu. Nếu gửi quyết định trái ngược, báo xung đột theo hợp đồng; không ghi đè phiếu cũ.

Nếu chính sách cho phép rút hoặc thay phiếu khi chưa kết thúc, đó phải là thao tác riêng có phân quyền, lịch sử và đánh giá lại kết quả. Không cho một câu lệnh cập nhật trực tiếp xóa mất dấu vết của phiếu trước.

Một cập nhật trạng thái có điều kiện có thể là:

```sql
UPDATE recovery_approval_request
SET state = 'REJECTED',
    terminal_reason_code = :reason_code,
    decided_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :request_id
  AND proposal_revision = :proposal_revision
  AND state = 'PENDING_REVIEW'
  AND version = :expected_version
  AND expires_at > CURRENT_TIMESTAMP;
```

Câu SQL chỉ minh họa việc chốt trạng thái; điều kiện đủ phiếu và mọi kiểm tra quyền phải được thực hiện trong ranh giới nhất quán phù hợp. Không gọi riêng câu lệnh này dựa trên `reasonCode` người dùng gửi.

Nếu cập nhật không được đúng một hàng, không tiếp tục gửi thông báo request đã bị từ chối. Hệ thống phải đọc lại nguyên nhân: xung đột phiên bản, hết hạn hoặc một trạng thái kết thúc đã được ghi trước. Các phần ghi thuộc thao tác mới phải rollback khi thất bại, trừ trường hợp hợp đồng cố ý lưu phiếu độc lập và diễn đạt rõ điều đó.

## 10. Quyết định đồng thời và thao tác đến muộn

Giả sử người A đang đồng ý và người B đang từ chối cùng request. Hai giao dịch không được độc lập nhìn thấy `PENDING_REVIEW`, tự ghi kết quả cuối rồi lần lượt ghi đè nhau.

Có thể tuần tự hóa bằng khóa bản ghi request hoặc dùng optimistic concurrency cùng cơ chế retry có kiểm tra. Bất kỳ luồng nào tính kết quả phải dựa trên phiên bản và tập phiếu được bảo vệ bởi cùng chiến lược.

| Tình huống | Cách xử lý |
|---|---|
| Rejection đã kết thúc trước | Luồng approval đến sau không được cấp quyền recovery |
| Approval đã kết thúc trước | Phiếu rejection mới không được ghi đè lịch sử bằng đường xử lý thông thường |
| Request đã hết hạn | Không nhận phiếu mới cho vòng đó |
| Request đã bị thay thế | Yêu cầu người duyệt mở revision hiện hành |
| Cùng người gửi hai quyết định | Ràng buộc và chính sách phiếu quyết định cách trả xung đột |

Trường hợp approval đã có hiệu lực rồi xuất hiện thông tin nguy hiểm không nên được giải quyết bằng việc sửa cột trạng thái thành `REJECTED` như thể chưa từng approve. Cần quy trình thu hồi quyền recovery hoặc ứng phó bảo mật có thẩm quyền, bảo toàn sự kiện cũ và xử lý cả trường hợp quyền đã được tiêu thụ.

Điểm thực thi reset mật khẩu, thay MFA hoặc đăng ký passkey phải kiểm tra quyền recovery còn hợp lệ. Một cache chứa kết quả approval cũ không được tiếp tục cấp quyền sau khi có sự kiện thu hồi hợp lệ. Với rejection xảy ra trước khi approval hợp lệ, hệ thống không được tạo grant từ request đó ngay từ đầu.

## 11. Kết thúc quyền của request, không gây khóa tài khoản ngoài ý muốn

Khi request chuyển sang `REJECTED`, các thao tác liên quan cần có phạm vi rõ ràng:

- Không cho tạo quyền thực thi recovery từ request đã từ chối.
- Không cho một lời mời xét duyệt cũ tạo thêm quyết định có hiệu lực cho request kết thúc.
- Đóng phiên thao tác hoặc token chỉ phục vụ riêng vòng recovery đó nếu hợp đồng yêu cầu.
- Hủy công việc nhắc duyệt và chặn gửi thông báo không còn phù hợp.
- Cập nhật case thành tiếp tục thu thập, chờ khiếu nại hoặc kết thúc theo chính sách đã định.

Không dùng email hay accountId làm điều kiện rộng để thu hồi mọi phiên của tài khoản. Nếu kẻ ngoài có thể tạo một đề nghị thất bại rồi khiến nạn nhân bị đăng xuất toàn bộ, rejection đã trở thành công cụ quấy rối hoặc từ chối dịch vụ.

Việc tạm khóa tài khoản do có bằng chứng bị chiếm đoạt thuộc quy trình bảo vệ tài khoản riêng. Nó có thể được kích hoạt từ tín hiệu trong case, nhưng cần điều kiện và thẩm quyền tương ứng; không phải hậu quả mặc định của một phiếu từ chối.

Nếu có quyền recovery được cấp từ một request khác, cần xác định quan hệ xung đột giữa các case theo chính sách. Không mặc nhiên thu hồi quyền đó chỉ vì một đề nghị không liên quan bị từ chối.

## 12. Lý do nội bộ và phản hồi bên ngoài

Mã lý do nên phản ánh điều đã được xác lập:

| Mã minh họa | Ý nghĩa | Không nên suy diễn |
|---|---|---|
| `EVIDENCE_REQUIREMENTS_NOT_MET` | Chưa đáp ứng điều kiện bằng chứng | Không tự kết luận người yêu cầu gian lận |
| `REQUESTED_SCOPE_NOT_ALLOWED` | Phạm vi thao tác không được phép trong tuyến này | Không tự từ chối mọi tuyến recovery khác |
| `VERIFIED_POLICY_RESTRICTION` | Có hạn chế được xác lập theo chính sách | Không công bố thông tin nội bộ không cần thiết |
| `CONFIRMED_ABUSE` | Có kết luận lạm dụng từ đánh giá được tin cậy | Không dùng chỉ vì người dùng phàn nàn hoặc liên hệ nhiều lần |

Các lỗi như hết hạn hoặc sai revision nên được ghi theo sự kiện tương ứng, thay vì gán sai lý do nghiệp vụ cho người duyệt.

Phản hồi cho người yêu cầu có thể là:

> Đề nghị khôi phục hiện tại chưa được chấp thuận. Chúng tôi chưa thể cho phép các thay đổi được đề nghị qua yêu cầu này. Bạn có thể xem các bước tiếp theo được cung cấp trong kênh hỗ trợ chính thức hoặc gửi yêu cầu xem xét nếu đủ điều kiện. Mã tham chiếu chỉ phục vụ theo dõi; không chia sẻ mật khẩu, OTP hoặc mã khôi phục trong cuộc trò chuyện.

Thông điệp cụ thể cần phù hợp với tình trạng cuối và mức xác thực của kênh. Không nói toàn bộ tài khoản “đã bị khóa” nếu chỉ có request bị từ chối. Không hứa khiếu nại chắc chắn làm thay đổi kết quả.

Không tiết lộ người duyệt nào từ chối, phần thông tin nào đã đúng, ngưỡng chống gian lận hoặc yếu tố xác thực đang đăng ký cho một người chưa có quyền biết. Việc dùng câu chữ chung cũng cần đi cùng kiểm soát API tra cứu, mã phản hồi và hành vi thông báo để tránh lộ trạng thái tài khoản.

## 13. Thông báo, audit và retry

Ghi phiếu và chốt request là hai loại sự kiện khác nhau. Có thể dùng các tên sự kiện:

```text
APPROVAL_REJECTION_VOTE_RECORDED
RECOVERY_APPROVAL_REQUEST_REJECTED
```

Sự kiện đầu không tự động làm phát thông báo từ chối cuối cùng cho người yêu cầu. Chỉ khi request thực sự kết thúc, hệ thống mới gửi thông báo tương ứng theo chính sách.

Outbox cho sự kiện kết thúc có thể mang mã request, revision, mã sự kiện và khóa mẫu thông báo. Không đưa token, OTP, ảnh giấy tờ hoặc ghi chú nhạy cảm vào message bus chỉ vì tiện xử lý.

Consumer cần chống trùng theo sự kiện, người nhận và loại thông báo. Nếu gửi email thất bại, retry gửi bằng sự kiện cũ; không mở request trở lại, không ghi thêm phiếu hoặc tạo thêm quyết định cuối.

Audit nên đủ để xác định:

```text
request_id / proposal_revision
decision_id / decision_type
reviewer_reference / authority_context
reason_code / policy_version
evidence_and_risk_version_references
request_version_before / request_version_after
previous_state / resulting_state
occurred_at / correlation_id
notification_event_reference
```

Thời điểm của phiếu và thời điểm kết thúc có thể khác nhau. Lưu riêng giúp tránh diễn giải rằng người đầu tiên bỏ phiếu đã tự quyết định toàn bộ kết quả.

Ghi chú tự do phải có giới hạn, hướng dẫn và kiểm soát truy cập. Không ghi bí mật xác thực hay sao chép giấy tờ vào log. Thời hạn lưu và quyền đọc cần phù hợp từng loại dữ liệu; không mặc định lưu mọi thứ vô thời hạn.

## 14. Khiếu nại và xét duyệt lại

Người dùng hợp lệ vẫn có thể không được chấp thuận vì bằng chứng không đủ hoặc đề nghị không phù hợp. Tuyến khiếu nại cần giúp xem xét sai sót hoặc bằng chứng mới mà không biến thành cách bỏ qua chính sách.

Một lần xét lại cần:

1. Liên kết với request và quyết định cũ.
2. Ghi lý do xem xét cùng bằng chứng bổ sung được phép thu thập.
3. Xác định revision, chính sách và tuyến duyệt áp dụng cho vòng mới.
4. Kiểm tra lại quyền, độ mới bằng chứng và rủi ro.
5. Giữ nguyên lịch sử vòng cũ, không xóa phiếu để giả lập kết quả khác.

Có thể tạo request mới hoặc một vòng mới trong cùng mô hình dữ liệu. Dù cách nào, phiếu cũ không tự trở thành phiếu của vòng mới và token của vòng bị từ chối không được kích hoạt lại.

Khiếu nại không được ưu tiên phê duyệt chỉ vì số lần liên hệ, vị trí xã hội hoặc sức ép với nhân viên. Hệ thống có thể áp dụng giới hạn chống lạm dụng, đồng thời giữ tuyến hỗ trợ cho sai sót và nhu cầu tiếp cận hợp lệ.

Nếu không còn phương thức recovery nào được cho phép, phải nói rõ giới hạn hiện tại. Không hứa rằng người duyệt khác sẽ có thể mở tài khoản bằng một bộ câu hỏi yếu hơn.

## 15. Tình huống xuyên suốt

Hà mất passkey cuối cùng và đề nghị đăng ký passkey thay thế. Request revision 4 được chuyển tới hai người duyệt, theo chính sách một phiếu từ chối hợp lệ là đủ để kết thúc khi request còn chờ.

1. Người duyệt A mở request và xem đúng bản đề nghị, bằng chứng cùng phiên bản chính sách.
2. A xác định bằng chứng chưa đáp ứng điều kiện. A chọn mã lý do phù hợp; không gắn nhãn gian lận khi chưa có kết luận đó.
3. Backend kiểm tra phiên, quyền hiện tại, tenant, revision và trạng thái request.
4. Trong giao dịch, hệ thống ghi phiếu của A, đánh giá quy tắc và chuyển request sang `REJECTED`, đồng thời ghi audit cùng outbox.
5. Người duyệt B đang mở màn hình cũ gửi approval. Backend phát hiện request đã kết thúc và không tạo quyền đăng ký passkey mới.
6. A bị timeout rồi gửi lại cùng khóa idempotency. Hệ thống trả lại kết quả đã lưu, không thêm phiếu hoặc gửi thêm thông báo cuối.
7. Request bị từ chối không làm khóa tài khoản, xóa passkey hay thu hồi phiên hợp lệ của Hà trên thiết bị khác nếu có.
8. Hà được thông báo kết quả phù hợp và có thể cung cấp bằng chứng mới qua tuyến xem xét lại được cho phép.

Nếu một vòng mới được mở, hệ thống tạo ngữ cảnh xét duyệt mới, không sửa request revision 4 thành đã chấp thuận. Quyền recovery của vòng mới chỉ được tạo sau khi mọi điều kiện hiện hành được đáp ứng.

## 16. Những lỗi thiết kế thường gặp

- **Đồng nhất phiếu từ chối với kết quả cuối:** thông báo sai khi mô hình nhiều người chưa kết thúc.
- **Không xác định thứ tự kết thúc:** approval và rejection đồng thời ghi đè nhau.
- **Tin quyền từ lúc gửi email:** người đã mất quyền vẫn quyết định được request.
- **Bỏ qua revision:** quyết định cũ áp dụng cho đề nghị mới hoặc phạm vi lớn hơn.
- **Cho sửa phiếu tại chỗ không có lịch sử:** mất khả năng giải thích ai đã quyết định điều gì.
- **Dùng GET để reject:** trình quét link hoặc thao tác mở nhầm gây thay đổi trạng thái.
- **Tự khóa toàn tài khoản khi reject:** biến yêu cầu thất bại thành công cụ gây hại cho nạn nhân.
- **Gửi email trước khi commit:** người dùng nhận kết quả chưa hề có hiệu lực.
- **Dùng retry để ghi thêm phiếu:** tạo dữ liệu trùng và sai ngưỡng quyết định.
- **Mở lại token cũ khi khiếu nại thành công:** bỏ qua phạm vi và thời hạn của vòng xét duyệt mới.

Approval rejection được thực hiện đúng khi quyết định gắn với đúng người, đúng thẩm quyền, đúng revision và đúng quy tắc kết thúc. Kết quả phải được lưu nhất quán, chặn quyền recovery của đề nghị đã bị từ chối và giữ nguyên ranh giới với tài khoản gốc. Các bước thông báo và xét lại giúp người dùng tiếp tục theo tuyến được phép mà không làm giảm tiêu chuẩn xác minh.
