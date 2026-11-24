# Thời hạn hiệu lực của liên kết khôi phục qua email

Trong chương **Email Link Recovery**, **Recovery link expiration** là cơ chế giới hạn khoảng thời gian mà một liên kết khôi phục còn được chấp nhận làm bằng chứng. Đây là một phần của **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, nơi người dùng có thể mất mật khẩu, MFA, passkey hoặc thiết bị xác thực và cần một đường khôi phục có kiểm soát.

Một liên kết nhận qua email thường chứa bí mật dạng bearer token: người có được bí mật có thể trình nó cho server để xin tiếp tục một hành động. Giới hạn thời gian giúp thu hẹp khoảng khai thác khi email bị đọc trộm, liên kết bị chuyển tiếp hoặc URL bị rò rỉ. Tuy nhiên, thời hạn không thay thế tính ngẫu nhiên, ràng buộc mục đích, sử dụng một lần, kiểm tra rủi ro hay xác minh bổ sung cho hành động nhạy cảm.

Bài học này giải thích cách chọn, lưu và thực thi thời hạn; xử lý thư đến chậm, gửi lại, nhiều thiết bị và thao tác đồng thời; đồng thời phân biệt thời hạn của liên kết với thời hạn của phiên khôi phục sau đó.

## 1. Hết hạn là điều kiện xác thực phía server

Lan yêu cầu đặt lại mật khẩu lúc 09:00. Server phát hành một token có hạn cuối là 09:15. Email đến lúc 09:04 và Lan mở liên kết lúc 09:16.

Theo chính sách minh họa này, liên kết đã hết hạn dù email mới xuất hiện trong hộp thư được 12 phút. Server xét thời gian phát hành và hạn cuối đã lưu, không xét thời điểm người dùng nhìn thấy thư.

```text
09:00                 09:04                       09:15       09:16
  | Phát hành token      | Email đến                 | Hết hạn   | Mở link
  |<---------------- khoảng hiệu lực -------------->|
```

Con số 15 phút chỉ phục vụ ví dụ, không phải mức bắt buộc cho mọi hệ thống. Thời hạn thực tế phải phản ánh rủi ro của hành động, khả năng truy cập email và điều kiện vận hành.

Một dòng chữ “liên kết hết hạn sau 15 phút” trong email chưa phải cơ chế bảo mật. Server phải kiểm tra hạn cuối tại thời điểm chấp nhận bằng chứng. Đồng hồ đếm ngược trên trình duyệt, cookie hết hạn hoặc thao tác xóa bản ghi định kỳ đều không thay thế kiểm tra này.

Quy ước rõ ràng cho khoảng hiệu lực:

```text
issued_at <= server_now < expires_at
```

Tại đúng `expires_at`, token đã hết hạn. Dùng nhất quán quy ước này ở mọi endpoint, dịch vụ và phép so sánh; tránh nơi dùng `<`, nơi khác dùng `<=` rồi tạo ra khoảng chấp nhận khác nhau.

## 2. Phân biệt các loại thời hạn và trạng thái

Một hành trình khôi phục có thể có nhiều giới hạn độc lập:

| Thành phần | Thời hạn giới hạn điều gì? | Ví dụ sai cần tránh |
|---|---|---|
| Yêu cầu khôi phục | Tuổi tối đa của một ý định hoặc quy trình khôi phục | Retry liên tục làm yêu cầu sống vô hạn |
| Token trong email | Khoảng thời gian được phép trình bằng chứng từ email | Mở lại link làm token có thêm thời gian |
| Phiên khôi phục hạn chế | Thời gian được thực hiện các bước sau khi bằng chứng đã được chấp nhận | Biến token email thành session đăng nhập dài hạn |
| Quyền thực hiện hành động cuối | Khoảng thời gian cho một thao tác cụ thể, nếu được tách riêng | Dùng quyền đặt lại mật khẩu để gỡ MFA |
| Bản ghi lưu trữ hoặc audit | Thời gian giữ dữ liệu phục vụ vận hành, điều tra | Bản ghi còn tồn tại nên token được coi là còn hiệu lực |

Cũng cần tách ba nguyên nhân mất hiệu lực:

- **Hết hạn:** đã vượt hạn cuối theo thời gian.
- **Đã sử dụng:** bằng chứng đã được tiêu thụ thành công.
- **Bị thu hồi:** server chủ động dừng hiệu lực trước hạn, chẳng hạn khi thay thế challenge hoặc thay đổi trạng thái bảo mật liên quan.

Một token có thể chưa hết hạn nhưng đã dùng hoặc bị thu hồi. Chỉ kiểm tra `expires_at` là chưa đủ. Ngược lại, bản ghi vẫn mang trạng thái `ACTIVE` do tác vụ dọn dẹp chưa chạy không làm một token quá hạn trở nên hợp lệ.

Mô hình bản ghi minh họa:

```text
EmailRecoveryChallenge
  challenge_id
  recovery_request_id
  tenant_id
  account_id
  purpose
  token_digest
  issued_at
  expires_at
  consumed_at
  revoked_at
  generation
  policy_version
```

`token_digest` là giá trị dùng để kiểm tra bí mật, không phải token thô. Với token ngẫu nhiên đủ mạnh, có thể dùng cơ chế digest phù hợp để tra cứu và đối chiếu. Không được xem một ID challenge hoặc ID request là bằng chứng thay cho token.

## 3. Chọn thời hạn theo rủi ro và khả năng sử dụng

Thời hạn quá dài kéo dài cơ hội dùng một liên kết bị lộ. Thời hạn quá ngắn có thể khiến người dùng thật liên tục thất bại vì thư đến chậm, đang chuyển thiết bị, cần công nghệ hỗ trợ hoặc không thể truy cập hộp thư ngay lập tức.

Khi chọn chính sách, cần xem xét:

| Yếu tố | Câu hỏi thiết kế |
|---|---|
| Hậu quả của hành động | Liên kết chỉ mở một bước hạn chế hay có thể dẫn đến thay credential? |
| Bằng chứng bổ sung | Email có phải bằng chứng duy nhất hay còn cần một yếu tố khác? |
| Độ trễ gửi thư | Phần lớn thư và các trường hợp chậm đáng kể mất bao lâu? |
| Luồng nhiều thiết bị | Người dùng có thể phải chuyển từ máy tính sang điện thoại hoặc ngược lại không? |
| Bề mặt rò rỉ | Có proxy, hệ thống theo dõi lỗi, chuyển tiếp thư hoặc công cụ quét link nào xử lý URL? |
| Khả năng gửi lại | Có thể cấp link mới mà không gây spam hoặc phá luồng đang hợp lệ không? |
| Khả năng hỗ trợ | Người không dùng được đường tự phục vụ còn quy trình được kiểm soát nào? |

Không có một giá trị TTL phù hợp cho mọi hành động. Thay mật khẩu, khôi phục MFA và đăng ký lại passkey có thể có yêu cầu bằng chứng khác nhau. Rút ngắn TTL không tự biến email thành bằng chứng đủ mạnh cho mọi loại khôi phục.

Một chính sách minh họa có thể quy định token email tối đa 15 phút, yêu cầu khôi phục tối đa 30 phút và phiên hạn chế sau xác minh tối đa 5 phút. Các con số này chỉ giúp diễn giải cách phối hợp; sản phẩm cần chọn và đánh giá chính sách riêng.

Không dùng TTL dài để bù cho một hệ thống gửi thư thường xuyên tắc nghẽn mà không đo nguyên nhân. Theo dõi độ trễ hàng đợi, độ trễ nhà cung cấp và tỷ lệ người dùng nhận thư khi gần hoặc đã hết hạn để điều chỉnh dựa trên dữ liệu.

## 4. Tính hạn cuối và lưu thời gian nhất quán

Khi tạo challenge, server chọn thời điểm phát hành từ nguồn thời gian tin cậy và tính một hạn cuối tuyệt đối:

```text
challenge_expires_at = min(
    issued_at + configured_link_ttl,
    recovery_request_expires_at
)
```

Công thức này phù hợp với thiết kế trong đó token không được sống lâu hơn yêu cầu cha. Nếu có thêm giới hạn nghiệp vụ, server đưa chúng vào cùng phép lấy hạn sớm nhất. Không để client gửi một `expires_at` lớn hơn rồi ghi đè giá trị này.

Nên lưu thời điểm tuyệt đối bằng UTC hoặc kiểu thời gian biểu diễn chính xác một thời điểm. Khi hiển thị, có thể đổi sang múi giờ người dùng. Không dùng chuỗi giờ địa phương thiếu múi giờ làm dữ liệu quyết định hiệu lực.

Cần thống nhất đơn vị và độ chính xác. Nhầm epoch giây với epoch mili giây có thể khiến token hết hạn ngay hoặc tồn tại lâu ngoài dự kiến. Nếu database chỉ giữ độ chính xác đến giây còn ứng dụng so sánh đến nano giây, phải xác định cách chuẩn hóa để ranh giới không thay đổi giữa các tầng.

Không tin thời gian từ trình duyệt, header tùy ý hoặc tham số URL. Người gửi có thể sửa tất cả những giá trị đó.

Trong mô hình dùng thời hạn đã lưu, thay đổi cấu hình TTL chỉ áp dụng cho challenge mới. Nếu cần rút ngắn hiệu lực của token cũ vì sự cố, thực hiện thu hồi hoặc thay đổi chính sách có kiểm soát và audit. Tính lại `issued_at + TTL hiện tại` ở mỗi lần dùng có thể vô tình kéo dài token cũ khi TTL cấu hình tăng.

## 5. Đồng hồ và kiểm tra trong hệ thống nhiều máy

Nếu API, worker và database dùng các đồng hồ lệch nhau, cùng một token có thể bị máy A từ chối nhưng máy B chấp nhận. Cần xác định nơi có thẩm quyền quyết định thời gian, đồng bộ đồng hồ và giám sát độ lệch trên các thành phần liên quan.

Có thể chọn database làm điểm quyết định hoặc dùng đồng hồ ứng dụng được quản lý nhất quán. Điều quan trọng là thời điểm dùng để kiểm tra cuối cùng phải phù hợp với thao tác chấp nhận bằng chứng.

Một lỗi tinh vi xảy ra khi request bắt đầu trước hạn nhưng phải chờ khóa lâu. Nếu kiểm tra bằng thời điểm đầu request hoặc đầu transaction, token có thể được chấp nhận sau khi đã quá hạn. Cần lấy thời gian phù hợp tại bước quyết định sau khi đã giành được quyền cập nhật. Một số cơ chế lấy thời gian trong database có thể trả thời điểm đầu transaction; phải hiểu ngữ nghĩa của cơ chế được chọn.

Quy định điểm chấp nhận rõ ràng: trong bài này, token phải còn hiệu lực tại thao tác tiêu thụ nguyên tử phía server. Thời điểm người dùng bấm nút hoặc gói tin rời trình duyệt không phải điểm quyết định vì server không thể tin cậy những mốc đó.

Không tự thêm khoảng chấp nhận quá hạn rộng để che sai lệch đồng hồ. Nếu chính sách có dung sai, nó làm tăng cửa sổ hiệu lực thực tế và phải được giới hạn, mô tả, áp dụng nhất quán. Thiết kế minh họa trong bài sử dụng ranh giới nghiêm ngặt `now < expires_at`.

Nếu hệ thống phát hiện nguồn thời gian không đáng tin cậy hoặc không thể đọc trạng thái bắt buộc, không mặc định cấp quyền. Phân loại đây là sự cố tạm thời và xử lý theo chính sách vận hành an toàn.

## 6. Kiểm tra thời hạn trong mã ứng dụng

Ví dụ Java dưới đây chỉ minh họa phép so sánh thời gian và các trạng thái cơ bản. Nó không thay thế kiểm tra token, quan hệ tài khoản, mục đích, transaction hay hạn mức thử:

```java
import java.time.Clock;
import java.time.Instant;

record LinkWindow(
        Instant issuedAt,
        Instant expiresAt,
        Instant consumedAt,
        Instant revokedAt) {
}

final class LinkTimePolicy {
    private final Clock clock;

    LinkTimePolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isTimeEligible(
            LinkWindow link,
            Instant requestExpiresAt) {
        Instant now = clock.instant();
        Instant deadline = link.expiresAt().isBefore(requestExpiresAt)
                ? link.expiresAt()
                : requestExpiresAt;

        return link.consumedAt() == null
                && link.revokedAt() == null
                && !now.isBefore(link.issuedAt())
                && now.isBefore(deadline);
    }
}
```

Các mốc thời gian bắt buộc phải được kiểm tra hợp lệ khi tạo hoặc đọc dữ liệu. `expiresAt` phải sau `issuedAt`; TTL phải dương và nằm trong giới hạn chính sách. Không coi dữ liệu thiếu hạn cuối là token không bao giờ hết hạn.

Tiêm `Clock` giúp mô tả và kiểm chứng các mốc trước hạn, đúng hạn và sau hạn mà không phụ thuộc thời gian thực của máy. Trong luồng dùng database làm nguồn thời gian quyết định, kiểm tra cuối cùng vẫn cần dựa trên thời gian và cơ chế nguyên tử ở database; không trộn hai nguồn đồng hồ như thể chúng hoàn toàn giống nhau.

Kết quả `true` từ hàm trên chỉ là một điều kiện. Server vẫn phải xác minh bí mật bằng cơ chế phù hợp, kiểm tra request còn được phép tiếp tục, đúng tenant, đúng tài khoản, đúng mục đích và phiên bản challenge được chấp nhận.

Nếu dùng token tự chứa có chữ ký, phải xác minh chữ ký, thuật toán được phép và các ràng buộc của token trước khi tin trường hết hạn. Một trường `exp` không được bảo vệ chỉ là dữ liệu do người gửi sửa được. Chữ ký và `exp` cũng không tự cung cấp khả năng sử dụng một lần hoặc thu hồi tức thời; các yêu cầu đó thường cần trạng thái phía server hoặc cơ chế tương đương.

## 7. Tiêu thụ một lần và chống cuộc đua sát hạn

Mẫu xử lý sau có thể sai:

```text
if token_is_valid_and_not_expired():
    show_success_or_create_recovery_session()
    mark_token_consumed_later()
```

Hai request đồng thời có thể cùng qua kiểm tra, rồi cùng tạo quyền tiếp tục. Request cũng có thể chờ đến quá hạn giữa kiểm tra và cập nhật.

Một trình tự minh họa phù hợp hơn:

```text
candidate = findChallengeUsingPresentedSecret(presented_secret)
if candidate is absent:
    return safe_failure

begin transaction
    request = lockRecoveryRequest(candidate.recovery_request_id)
    challenge = lockAndReloadChallenge(candidate.challenge_id)
    decision_time = authoritative_time_at_this_step()

    require challenge belongs to request, tenant, account and purpose
    require request is in a permitted active state
    require challenge is unconsumed and unrevoked
    require challenge generation is accepted by policy
    require challenge.issued_at <= decision_time
    require decision_time < challenge.expires_at
    require decision_time < request.expires_at
    verify presented_secret against challenge
    require all additional policy conditions

    consume challenge exactly once
    record scoped evidence or create a restricted recovery grant
    append audit event
commit
```

Đây là pseudocode mô tả thứ tự và bất biến. Triển khai có thể dùng khóa hàng hoặc cập nhật có điều kiện kết hợp các ràng buộc tương đương. Các đường cập nhật khác cần tuân theo cùng quy tắc cạnh tranh, kể cả thu hồi request và thay thế challenge.

Nếu thao tác cập nhật có điều kiện không tác động bản ghi nào, không được giả định đã tiêu thụ thành công. Có thể token đã quá hạn, đã dùng, bị thu hồi hoặc request đã đổi trạng thái. Chỉ trả thành công khi hệ thống có bằng chứng bền vững cho đúng thao tác được phép.

Tại ranh giới, token được tiêu thụ hợp lệ ngay trước hạn có thể commit ngay sau hạn theo điểm chấp nhận đã định nghĩa. Nếu nghiệp vụ đòi hành động cuối cũng phải xong trước một hạn khác, cần kiểm tra hạn đó riêng. Không để mỗi endpoint tự suy luận một điểm chấp nhận khác nhau.

Một phản hồi mạng bị mất sau commit không làm token trở lại chưa dùng. Retry phải theo hợp đồng chống lặp của thao tác hoặc yêu cầu bằng chứng phù hợp để tiếp tục kết quả đã tạo, thay vì chấp nhận token lần hai như một lần xác minh mới.

## 8. Email đến chậm và yêu cầu gửi lại

### 8.1. Xác định TTL bắt đầu từ đâu

Trong mô hình bài này, TTL bắt đầu lúc challenge được phát hành, trước khi đưa tác vụ gửi thư vào hàng đợi. Email được nhà cung cấp nhận, được chuyển phát hoặc được người dùng mở không tự làm mới thời hạn.

Một hệ thống khác có thể chọn tạo token ngay trước lần gửi đầu tiên để giảm thời gian nằm trong hàng đợi. Nếu chọn cách đó, phải xác định rõ thời điểm phát hành, giới hạn tuổi yêu cầu cha và hành vi khi gửi lại. Không dùng sự kiện mở thư làm mốc tin cậy vì nó không chứng minh người dùng đã đọc và có thể do công cụ quét tạo ra.

Ví dụ:

| Mốc | Diễn biến |
|---|---|
| 10:00 | Tạo challenge, hạn cuối 10:15 |
| 10:12 | Worker mới xử lý được tác vụ gửi |
| 10:14 | Người dùng nhận email |
| 10:16 | Người dùng bấm liên kết |

Nếu giữ mô hình phát hành lúc 10:00, lần bấm lúc 10:16 phải bị từ chối. Server không lấy 10:14 làm mốc mới để chấp nhận đến 10:29.

Worker cần kiểm tra tác vụ còn thích hợp trước khi gửi, tránh phát thư đã hết hạn hoặc không còn đủ thời gian sử dụng theo chính sách. Nếu cấp challenge mới, đó phải là một quyết định phát hành mới có hạn mức và trạng thái tương ứng, không phải âm thầm sửa `expires_at` của token cũ.

### 8.2. Retry gửi thư khác với cấp link mới

Hàng đợi có thể giao lại cùng sự kiện sau lỗi mạng. Giao lại cùng ý định gửi không được tự tạo một token mới, đặt lại số lần thử hoặc kéo dài thời hạn của token cũ.

Để dựng thư, dịch vụ gửi cần một cách truy cập bí mật được bảo vệ trong thời gian cần thiết. Không thể khôi phục token ngẫu nhiên từ `token_digest` chỉ để gửi lại. Thiết kế payload hoặc kho bí mật tạm thời phải xét quyền truy cập, thời hạn lưu và việc không đưa token vào log.

Khi người dùng chủ động xin một link mới, server áp dụng hạn mức và chính sách thay thế. Một lựa chọn là thu hồi challenge trước; lựa chọn khác là cho phép một số challenge cùng tồn tại trong giới hạn được kiểm soát. Cần đánh giá nguy cơ kẻ tấn công dùng yêu cầu vô danh để làm hỏng link hợp lệ của nạn nhân.

Trong mọi lựa chọn, token cũ đã hết hạn không được hồi sinh. Hạn cuối của token mới vẫn phải nằm trong giới hạn tuổi yêu cầu hoặc một yêu cầu mới được tạo theo chính sách. Chỉ biết email không cho phép người gửi liên tục kéo dài toàn bộ hành trình khôi phục.

## 9. Mở link, công cụ quét email và phiên hạn chế

Một số hệ thống email hoặc phần mềm bảo vệ sẽ tự mở URL để kiểm tra. Nếu chỉ một lần `GET` là tiêu thụ token, người dùng có thể nhận thông báo “đã dùng” ngay lần mở đầu tiên của họ.

Có thể thiết kế trang đích không thực hiện đổi credential hoặc tiêu thụ bằng chứng chỉ vì được tải. Sau đó yêu cầu một thao tác xác nhận rõ ràng bằng phương thức phù hợp, với kiểm soát ngữ cảnh và chống giả mạo yêu cầu theo thiết kế. Tuy nhiên, không coi một nút bấm hay `POST` là bằng chứng mới về danh tính, và không giả định mọi công cụ quét đều chỉ gửi `GET`.

Thời hạn vẫn phải được kiểm tra lại ở bước tiêu thụ cuối cùng. Trang được mở lúc 11:14 nhưng người dùng xác nhận lúc 11:16 không được chấp nhận token có hạn cuối 11:15 chỉ vì trang đã hiển thị trước đó.

Sau khi token được tiêu thụ hợp lệ, server có thể cấp phiên khôi phục hạn chế. Cần công bố mô hình thời hạn của phiên đó. Ví dụ:

```text
Token email:
  expires_at = 11:15
  consumed_at = 11:14

Request khôi phục:
  expires_at = 11:30

Phiên hạn chế được tạo lúc 11:14:
  expires_at = min(11:14 + 5 phút, 11:30) = 11:19
```

Trong mô hình này, link không dùng lại được sau 11:14. Phiên hạn chế có thể tiếp tục đến 11:19 dù link có hạn cuối 11:15, vì bằng chứng đã được chấp nhận trước đó và server cấp một quyền mới có thời hạn riêng.

Nếu chính sách yêu cầu mọi bước kết thúc trước hạn link ban đầu, phải giới hạn phiên theo hạn đó. Hai mô hình đều cần được thiết kế rõ; không vô tình tạo phiên dài hạn chỉ vì token được dùng một giây trước khi hết hạn.

Phiên hạn chế chỉ được phép thực hiện những bước khôi phục đã cho phép, có thời hạn tuyệt đối và kiểm tra trạng thái cần thiết. Gia hạn theo hoạt động, nếu có, vẫn cần một trần tuyệt đối. Không tự biến phiên này thành session đăng nhập toàn quyền hoặc cho phép đổi mọi yếu tố xác thực.

## 10. Trải nghiệm khi link hết hạn và bảo vệ URL

Thông báo công khai có thể là:

> Liên kết không còn hiệu lực. Bạn có thể bắt đầu lại để nhận hướng dẫn mới.

Câu chữ này có thể dùng chung cho token không hợp lệ, hết hạn, đã dùng hoặc bị thu hồi, tùy mức thông tin được phép tiết lộ. Không trả tên tài khoản, địa chỉ nhận thư hoặc trạng thái MFA chỉ vì người gửi có một chuỗi URL.

Chức năng bắt đầu lại vẫn cần giới hạn tần suất và phản hồi tránh dò tài khoản. Đừng tự gửi email mới mỗi lần ai đó mở một link cũ; kẻ tấn công có thể khai thác việc đó để gây spam.

Có thể hiển thị thời hạn trong email và trạng thái trên giao diện để người dùng biết cần hành động sớm. Nếu dùng bộ đếm ngược, coi nó là thông tin hỗ trợ. Server vẫn quyết định sau khi người dùng đổi giờ máy, treo tab, quay lại bằng nút Back hoặc mở link trên thiết bị khác.

URL chứa token cần được bảo vệ dù TTL ngắn:

- Chỉ truyền qua HTTPS và sử dụng miền khôi phục được kiểm soát.
- Tránh tài nguyên bên thứ ba trên trang nhận token; dùng chính sách referrer phù hợp, chẳng hạn `Referrer-Policy: no-referrer`.
- Ngăn lưu phản hồi nhạy cảm bằng chính sách cache phù hợp, chẳng hạn `Cache-Control: no-store`.
- Không ghi URL đầy đủ chứa token vào access log, trace, công cụ phân tích hoặc báo lỗi.
- Khi đã đổi sang một ngữ cảnh an toàn theo thiết kế, chuyển tới URL sạch để giảm việc token tiếp tục tồn tại trên thanh địa chỉ và các lần điều hướng.

Các biện pháp header và chuyển hướng không xóa được mọi bản sao đã có trong lịch sử hoặc hệ thống trung gian. Phải ngăn thu thập bí mật tại các điểm liên quan, thay vì dựa vào việc token sắp hết hạn.

## 11. Dọn dữ liệu, cache và khả năng quan sát

Tác vụ dọn token quá hạn phục vụ lưu trữ và vận hành. Tác vụ này có thể chạy trễ; kiểm tra hiệu lực không được phụ thuộc vào việc bản ghi đã bị xóa hay chưa.

Tương tự, cache hết hạn không phải nguồn duy nhất chứng minh token hợp lệ. Cache một kết quả “token còn dùng được” trong vài phút có thể bỏ qua việc token đã được tiêu thụ hoặc bị thu hồi ở nơi khác. Bước chấp nhận bằng chứng phải dựa trên trạng thái có thẩm quyền và thao tác nguyên tử.

Nếu lưu token trong một kho có TTL tự xóa, vẫn phải hiểu độ trễ xóa và tính nguyên tử của thao tác đọc, kiểm tra, tiêu thụ. Không suy luận rằng “còn đọc thấy khóa” đồng nghĩa “còn hiệu lực”.

Audit có thể ghi các trường hữu hạn như:

```json
{
  "event_type": "EMAIL_RECOVERY_LINK_REJECTED",
  "challenge_reference": "<tham-chieu-noi-bo>",
  "reason_code": "EXPIRED",
  "policy_version": "<phien-ban-chinh-sach>",
  "decision_at": "<thoi-diem-UTC>",
  "expires_at": "<han-cuoi-UTC>"
}
```

Lý do nội bộ giúp vận hành phân biệt hết hạn với đã dùng, bị thu hồi và lỗi hạ tầng. Không nhất thiết trả các lý do đó cho client. Không ghi token thô, digest có thể bị lạm dụng ngoài dự kiến, cookie hoặc nội dung email chứa bí mật vào log thông thường.

Các chỉ số hữu ích gồm độ trễ phát hành đến gửi, độ trễ gửi đến lần trình token, tỷ lệ quá hạn và số lần xin gửi lại. Tránh dùng ID từng challenge hay email làm nhãn metric tổng hợp. Việc thu thập thời điểm sử dụng cũng cần chính sách dữ liệu và quyền truy cập phù hợp.

Tỷ lệ hết hạn cao có thể do TTL không phù hợp, email bị trễ, công cụ quét, thông báo khó hiểu hoặc người dùng không còn truy cập được hộp thư. Không tự kéo dài toàn bộ token đang tồn tại để xử lý một chỉ số tăng mà chưa xác định nguyên nhân.

## 12. Các tình huống cần kiểm chứng khi triển khai

Bảng này là đặc tả hành vi để kiểm chứng, không phải kết quả kiểm thử đã chạy cùng bài viết.

| Tình huống | Hành vi cần đạt |
|---|---|
| Thời điểm chấp nhận trước hạn một đơn vị chính xác được hỗ trợ | Có thể tiếp tục nếu mọi điều kiện khác đều đạt |
| Thời điểm chấp nhận đúng bằng hạn cuối | Từ chối theo quy ước `now < expires_at` |
| Token đã quá hạn nhưng bản ghi chưa được dọn | Vẫn từ chối |
| Trình duyệt sửa giờ về trước | Không thay đổi quyết định phía server |
| Đổi múi giờ hoặc nhầm đơn vị epoch | Không kéo dài hay rút ngắn hạn ngoài chính sách |
| Email đến sau hạn cuối | Link không được hồi sinh; người dùng có đường xin lại được kiểm soát |
| Hàng đợi giao lại cùng sự kiện gửi thư | Không tự cấp token mới hoặc gia hạn token cũ |
| Hai request tiêu thụ cùng token đồng thời | Chỉ một lần được chấp nhận như bằng chứng mới |
| Request chờ khóa đến sau hạn | Kiểm tra bằng thời gian tại điểm quyết định phù hợp, không dùng mốc đầu request |
| Token còn thời gian nhưng đã dùng hoặc bị thu hồi | Từ chối |
| Yêu cầu cha đã hết hạn trước token | Không cho token vượt giới hạn của yêu cầu cha |
| Mở trang trước hạn, xác nhận sau hạn | Kiểm tra lại và từ chối nếu link không còn hiệu lực |
| Công cụ quét tải trang đích | Không tự đổi credential hoặc coi đó là hành động khôi phục hoàn tất |
| Tăng TTL trong cấu hình | Không âm thầm gia hạn các challenge có hạn cuối đã lưu |
| Token tự chứa có `exp` bị sửa | Không tin dữ liệu khi chưa xác minh tính toàn vẹn và các ràng buộc |
| Token hợp lệ cho đặt lại mật khẩu được dùng để xin gỡ MFA | Không cấp quyền ngoài mục đích và bằng chứng được phép |
| Phiên hạn chế được cấp ngay trước hạn link | Có hạn cuối và phạm vi theo mô hình đã công bố, không thành phiên vô hạn |
| Phản hồi bị mất sau khi tiêu thụ đã commit | Retry không biến token thành bằng chứng mới lần hai |
| Không đọc được trạng thái hoặc nguồn thời gian bắt buộc | Không mặc định chấp nhận token |

Thiết kế thời hạn cần xác định được **mốc bắt đầu**, **hạn cuối tuyệt đối**, **nguồn thời gian có thẩm quyền** và **điểm chấp nhận nguyên tử**. Khi các yếu tố đó được gắn với trạng thái sử dụng một lần, đúng mục đích và đường gửi lại có kiểm soát, liên kết email mới có một vòng đời rõ ràng trong toàn bộ quá trình khôi phục tài khoản.
