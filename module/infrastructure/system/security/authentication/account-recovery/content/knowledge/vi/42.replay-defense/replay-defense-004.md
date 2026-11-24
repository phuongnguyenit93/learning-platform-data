# OTP replay attempt: Ngăn sử dụng lại OTP trong khôi phục tài khoản

Một mã OTP đúng và chưa hết hạn chưa đủ để cho phép khôi phục tài khoản. Nếu mã đó đã được chấp nhận, việc gửi lại không được tạo thêm bằng chứng xác thực, thêm phiên khôi phục hoặc thêm cơ hội đổi mật khẩu, MFA hay passkey.

Trong hệ thống khôi phục tài khoản, yêu cầu quan trọng là **mỗi lần phát hành hoặc mỗi giá trị sinh OTP được chấp nhận chỉ tạo tối đa một lần chuyển trạng thái xác minh đã commit**. Điều này phải đúng khi người dùng bấm hai lần, mạng gửi lại request, hai máy chủ nhận cùng mã hoặc kẻ tấn công cố tình phát lại dữ liệu đã lấy được.

Bài học dùng “OTP” theo cách gọi phổ biến trong sản phẩm: mã ngắn do máy chủ gửi qua một kênh và mã do ứng dụng xác thực sinh ra. Về phân loại kỹ thuật, mã được máy chủ gửi và TOTP/HOTP có cơ chế khác nhau. Không suy ra rằng dùng mã email hoặc SMS tự động đáp ứng một mức bảo đảm danh tính cụ thể.

## 1. OTP replay attempt là gì?

OTP replay attempt là một lần thử sử dụng lại thông điệp xác thực có OTP đã xuất hiện trước đó, nhằm làm hệ thống chấp nhận thêm một lần. Đối tượng bị phát lại có thể là toàn bộ HTTP request hoặc chỉ phần mã được đưa sang request, phiên hay endpoint khác.

Ví dụ minh họa:

~~~text
10:00:00  Máy chủ tạo challenge C1 cho flow F1, mục đích RESET_PASSWORD.
10:00:20  Người dùng gửi mã "042731".
10:00:20  Máy chủ xác minh thành công, tiêu thụ C1 và ghi nhận bằng chứng cho F1.
10:00:22  Request khác gửi lại cùng C1 và cùng mã.
~~~

Request cuối không được tạo một lần xác minh mới, dù thời hạn của C1 còn vài phút. Nếu hệ thống có cơ chế retry hợp lệ, nó có thể trả lại trạng thái của thao tác đã hoàn tất sau khi kiểm tra quyền truy cập; đó không phải việc chấp nhận lại OTP.

NIST yêu cầu verifier chỉ chấp nhận một OTP một lần trong thời gian mã còn hợp lệ. NIST cũng phân biệt replay resistance với việc chỉ sử dụng kênh truyền được bảo vệ: dữ liệu có thể bị lấy trước khi đi vào kênh đó. [NIST SP 800-63B: OTP verifiers và replay resistance](https://pages.nist.gov/800-63-4/sp800-63b.html).

### Những tình huống dễ bị nhầm lẫn

| Tình huống | Bản chất | Cách xử lý cần có |
| --- | --- | --- |
| Nhập sai một mã chưa dùng | Thử xác thực thất bại | Ghi nhận thất bại và áp dụng giới hạn thử |
| Gửi lại mã đã được chấp nhận | Replay hoặc retry của thao tác cũ | Không tạo thêm bằng chứng xác thực |
| Hai request cùng gửi một mã chưa dùng | Cạnh tranh để sử dụng lần đầu | Tối đa một request được commit chuyển trạng thái |
| Mã cũ bị thay thế nhưng chưa từng dùng | Dùng dữ liệu đã mất hiệu lực | Từ chối theo chính sách thay thế |
| Mã bị đánh cắp và kẻ tấn công dùng trước chủ tài khoản | Chiếm lần sử dụng đầu tiên | Cần thêm chống phishing, ràng buộc giao dịch và đánh giá rủi ro |
| Chuỗi sáu chữ số trùng nhau trong hai lần phát hành khác nhau | Va chạm giá trị ngắn | Phải phân biệt thế hệ/challenge; không coi chuỗi số là định danh toàn cục |

Chống replay chỉ bảo đảm giới hạn sử dụng. Nó không bảo đảm người sử dụng trước là chủ tài khoản.

## 2. Thời hạn và tính dùng một lần là hai điều kiện độc lập

Một thiết kế thiếu sót thường kiểm tra:

~~~text
mã nhập vào đúng
AND thời gian hiện tại < expiresAt
=> cho phép tiếp tục
~~~

Điều kiện này chỉ nói mã còn nằm trong khoảng chấp nhận. Nó không nói mã đã được sử dụng hay chưa.

Với mã do máy chủ cấp, quyết định cần xét thêm:

~~~text
challenge tồn tại
AND thuộc đúng flow và tài khoản do máy chủ xác định
AND đúng mục đích
AND đúng ngữ cảnh khôi phục được phép
AND đang ở trạng thái ISSUED
AND chưa hết hạn
AND chưa vượt giới hạn thử
AND mã khớp
AND có thể tiêu thụ challenge một cách nguyên tử
~~~

Một thời hạn ngắn không sửa được lỗi dùng lại. Rate limit cũng không sửa được lỗi này: nếu hai lần gửi cùng mã đều được phép và đều thành công thì tính dùng một lần đã bị phá vỡ.

TLS cần thiết để bảo vệ đường truyền, nhưng một request hợp lệ được gửi lại qua kết nối TLS khác vẫn cần bị xử lý đúng ở tầng ứng dụng.

## 3. Mô hình dữ liệu cho mã khôi phục do máy chủ cấp

Ví dụ dưới đây là một mô hình thiết kế, không phải schema bắt buộc cho mọi dịch vụ.

~~~text
RecoveryFlow
  id
  accountId
  purpose
  state
  securityVersion
  contextBinding
  expiresAt
  verifiedAt

RecoveryOtpChallenge
  id
  recoveryFlowId
  generation
  state
  otpVerifier
  verifierKeyVersion
  issuedAt
  expiresAt
  consumedAt
  failedAttempts
  maxAttempts
~~~

Các trường quan trọng có ý nghĩa như sau:

- `id` và `generation` phân biệt những lần phát hành. Một chuỗi số có thể xuất hiện lại ở thế hệ khác.
- `purpose` phân biệt đặt mật khẩu, thay MFA, thay passkey hoặc tác vụ khác. Bằng chứng cho một mục đích không tự có quyền làm mục đích khác.
- `securityVersion` là phiên bản trạng thái bảo mật của tài khoản tại thời điểm lập flow. Dịch vụ phải quy định những thay đổi nào làm tăng phiên bản và làm flow cũ mất hiệu lực.
- `contextBinding` gắn flow với ngữ cảnh khôi phục được máy chủ kiểm soát. Biết `flowId` hoặc `challengeId` không tự tạo quyền truy cập.
- `state` và `consumedAt` ghi nhận việc sử dụng đã xảy ra. Chúng phải được cập nhật cùng bước ghi nhận bằng chứng khôi phục.
- `failedAttempts` phục vụ giới hạn đoán mã. Bộ đếm này không thay thế trạng thái đã dùng.

Máy chủ cần suy ra tài khoản từ dữ liệu đáng tin cậy của flow/challenge và kiểm tra quyền trên flow. Không nhận `accountId` trong body rồi mặc nhiên dùng nó làm tài khoản đích.

Một `contextBinding` có thể sử dụng ngữ cảnh phiên khôi phục được bảo vệ hoặc một cơ chế chứng minh quyền truy cập khác. Không nên ràng buộc cứng vào địa chỉ IP như bằng chứng sở hữu duy nhất: mạng di động, NAT và thay đổi mạng có thể làm IP thay đổi hoặc dùng chung.

### Lưu OTP thế nào?

Mã ngắn có không gian giá trị nhỏ. Lưu một hash nhanh không có bí mật bảo vệ vẫn cho phép người đọc được cơ sở dữ liệu thử hết các giá trị tương đối dễ dàng.

Một lựa chọn thiết kế cho mã do máy chủ phát hành là lưu verifier có khóa:

~~~text
otpVerifier = HMAC(
    serverKey,
    encode(challengeId, accountId, purpose, generation, otp)
)
~~~

`encode` cần có cấu trúc xác định, tránh nối chuỗi mơ hồ. Khóa máy chủ phải được quản lý ngoài bản ghi challenge, có kiểm soát truy cập và phiên bản khóa phù hợp. Khi kiểm tra ở tầng ứng dụng, so sánh kết quả theo cách tránh rò rỉ qua thời gian.

Giữ OTP như chuỗi để không làm mất số 0 ở đầu. Không đưa OTP, seed TOTP, khóa HMAC hoặc verifier nhạy cảm vào log. Cách lưu này bảo vệ dữ liệu lưu trữ; tính dùng một lần vẫn cần trạng thái tiêu thụ nguyên tử.

## 4. Vòng đời challenge và quyền của bằng chứng khôi phục

Một vòng đời minh họa:

~~~text
ISSUED
  | mã đúng, đủ điều kiện, commit thành công
  v
CONSUMED

ISSUED -- quá hạn ----------------> EXPIRED
ISSUED -- vượt giới hạn thử ------> LOCKED
ISSUED -- bị thay bằng thế hệ mới -> SUPERSEDED
ISSUED -- flow bị hủy ------------> CANCELLED
~~~

Chỉ `ISSUED` mới có thể chuyển sang `CONSUMED`. Không có đường chuyển từ `CONSUMED` trở lại `ISSUED` chỉ vì client không nhận được phản hồi.

Trạng thái `OTP_VERIFIED` của flow cũng không nên được hiểu là đã hoàn tất toàn bộ khôi phục. Nó chỉ chứng minh một điều kiện đã được thỏa mãn theo chính sách. Tài khoản có thể còn cần bằng chứng độc lập, thời gian chờ hoặc xét duyệt rủi ro trước khi thay yếu tố xác thực.

Nếu người dùng mất chính thiết bị sinh TOTP, không thể yêu cầu họ dùng TOTP đó rồi gọi đây là cách xử lý việc mất thiết bị. Khi ấy cần nhánh khôi phục khác đã được thiết kế và phê duyệt. Ngược lại, TOTP còn truy cập được có thể là một yếu tố trong flow xử lý việc mất phương thức khác.

## 5. Vì sao đọc rồi ghi riêng rẽ gây dùng lại?

Đoạn xử lý sau có cửa sổ cạnh tranh:

~~~text
challenge = read(challengeId)

if challenge.state == ISSUED and otpMatches(challenge, input):
    createRecoveryEvidence(flowId)
    challenge.state = CONSUMED
    save(challenge)
~~~

Hai request có thể cùng đọc `ISSUED` trước khi bất kỳ request nào ghi lại:

| Thời điểm | Request A | Request B |
| --- | --- | --- |
| t1 | Đọc trạng thái ISSUED | |
| t2 | | Đọc trạng thái ISSUED |
| t3 | Xác nhận mã đúng | |
| t4 | | Xác nhận mã đúng |
| t5 | Tạo bằng chứng khôi phục | |
| t6 | | Tạo bằng chứng khôi phục lần nữa |
| t7 | Ghi CONSUMED | |
| t8 | | Ghi CONSUMED |

Cuối cùng cơ sở dữ liệu vẫn có `CONSUMED`, nhưng quyền khôi phục đã được cấp hai lần. Nhìn trạng thái cuối không phát hiện được toàn bộ hậu quả.

Một `synchronized` trong Java hoặc khóa trong bộ nhớ chỉ bảo vệ các luồng thực sự dùng cùng đối tượng khóa trong cùng tiến trình. Nó không bao phủ request đi tới instance khác, tiến trình sau khi restart hoặc dịch vụ khác cùng xác minh OTP.

## 6. Một transaction tiêu thụ OTP và ghi nhận bằng chứng

Ví dụ này chọn PostgreSQL làm nơi quyết định trạng thái có thẩm quyền. Mục tiêu là minh họa ranh giới transaction và việc kiểm tra kết quả, không cung cấp một endpoint hoàn chỉnh.

Giả định thiết kế:

1. Mọi đường thay trạng thái bảo mật, phát hành/thay thế challenge và xác minh của cùng tài khoản tuân theo thứ tự khóa thống nhất: tài khoản → flow → challenge.
2. Flow đã gắn với mục đích, tài khoản và ngữ cảnh khôi phục; các thông tin này được xác minh phía máy chủ.
3. Việc ghi nhận OTP đã dùng và cập nhật bằng chứng nằm trong cùng cơ sở dữ liệu, cùng transaction.
4. Không phát hành phiên, bearer token hoặc thực hiện tác dụng phụ bên ngoài trước khi commit.

Phác thảo xử lý ở tầng dịch vụ:

~~~text
BEGIN

lock account row
lock recovery flow row
lock OTP challenge row

check flow ownership/context, purpose, securityVersion and flow expiry
check challenge belongs to that flow
check challenge is ISSUED, unexpired and within attempt budget

if code does not match:
    increment failedAttempts atomically
    set LOCKED if the configured threshold is reached
    COMMIT the failed-attempt update
    return a controlled failure response

consume challenge conditionally
if affected row count != 1:
    ROLLBACK
    return failure

record the OTP evidence on this flow conditionally
if affected row count != 1:
    ROLLBACK
    return failure

COMMIT
return the committed operation status to the authorized recovery context
~~~

Nhánh mã sai phải lưu được bộ đếm thất bại. Nếu ném exception khiến toàn bộ transaction rollback luôn bộ đếm thì giới hạn thử có thể không hoạt động như dự định.

Hai cập nhật cuối có thể có dạng:

~~~sql
-- Được chạy sau khi lấy khóa và xác minh các điều kiện ở tầng dịch vụ.
-- Các tham số là giá trị đã được máy chủ xác định/kiểm tra.

UPDATE recovery_otp_challenge
SET state = 'CONSUMED',
    consumed_at = clock_timestamp()
WHERE id = :challenge_id
  AND recovery_flow_id = :flow_id
  AND state = 'ISSUED'
  AND expires_at > clock_timestamp()
  AND failed_attempts < max_attempts
RETURNING id;

-- Chỉ chạy nếu câu trên trả đúng một hàng.
UPDATE recovery_flow
SET state = 'OTP_VERIFIED',
    verified_at = clock_timestamp()
WHERE id = :flow_id
  AND account_id = :account_id
  AND purpose = :expected_purpose
  AND security_version = :expected_security_version
  AND state = 'OTP_PENDING'
  AND expires_at > clock_timestamp()
RETURNING id;
~~~

Ứng dụng phải kiểm tra đúng một hàng cho cả hai cập nhật. Không được bỏ qua kết quả cập nhật rồi vẫn trả thành công.

Khóa hàng giữ cho các kiểm tra liên quan của thiết kế này không bị thay đổi đồng thời bởi các đường ghi tuân cùng quy ước. Điều kiện `state = 'ISSUED'` là thêm một cổng quyết định ở bước tiêu thụ. PostgreSQL mô tả việc chờ transaction đang cập nhật hàng và đánh giá lại điều kiện `WHERE` trên phiên bản hàng mới ở mức Read Committed. [PostgreSQL: Read Committed](https://www.postgresql.org/docs/current/transaction-iso.html#XACT-READ-COMMITTED).

Không suy rộng rằng một transaction bất kỳ ở Read Committed tự giải quyết mọi bất biến nhiều hàng. Tính đúng ở đây còn phụ thuộc thứ tự khóa, những hàng được khóa, mọi đường ghi liên quan và ràng buộc dữ liệu. Nếu chọn optimistic locking hoặc isolation khác, vẫn phải xử lý xung đột và không được phát hành quyền khi transaction thất bại.

### Khi có tác dụng phụ ở dịch vụ khác

Không thể làm hai thao tác dưới đây trở thành nguyên tử chỉ bằng việc gọi nối tiếp:

~~~text
xóa OTP trong kho A
gọi dịch vụ B để cấp quyền khôi phục
~~~

Nếu B lỗi, không tùy tiện khôi phục OTP về trạng thái chưa dùng. Nếu B thành công nhưng phản hồi bị mất, cũng không tạo quyền mới ở mỗi lần retry.

Một hướng thiết kế là commit bằng chứng và bản ghi tác vụ/outbox cùng transaction, sau đó xử lý tác vụ bằng định danh ổn định và cơ chế chống thực thi trùng ở bên nhận. Cần tách rõ trạng thái “đã xác minh OTP”, “đang xử lý” và “đã hoàn tất thay đổi”; không hứa một lần giao thông điệp duy nhất trên mạng.

## 7. TOTP cần trạng thái dùng lại theo authenticator

TOTP khác với mã ngẫu nhiên được phát hành riêng cho từng challenge. Cùng một authenticator có thể tạo mã mà nhiều flow hoặc endpoint cùng kiểm tra. Chỉ đánh dấu `flow F1 đã dùng OTP` không ngăn cùng giá trị sinh mã được đem sang flow F2.

RFC 6238 quy định không chấp nhận lần thử thứ hai sau khi OTP đầu tiên đã được xác minh thành công. Cửa sổ chấp nhận có thể bao gồm các time step lân cận để xử lý độ lệch đồng hồ; điều đó không cho phép dùng lại mã đã được chấp nhận. [RFC 6238, mục 5.2–6](https://www.rfc-editor.org/rfc/rfc6238.html#section-5.2).

Một lựa chọn triển khai là lưu mốc counter đã chấp nhận cao nhất:

~~~text
key = (accountId, authenticatorId, secretVersion)

lastAcceptedCounter
~~~

Sau khi tìm được counter `c` khớp mã trong cửa sổ được phép:

~~~text
BEGIN

lock account and recovery flow
lock authenticator replay state

check recovery policy and allowed TOTP time window
require c > lastAcceptedCounter
advance lastAcceptedCounter to c conditionally
record the evidence for this recovery flow

COMMIT
~~~

Cần hiểu các giới hạn của lựa chọn này:

- Counter được xác định theo trạng thái thời gian phía verifier và cửa sổ đã cấu hình, không phải một counter tùy ý do client đưa lên.
- Nếu đã chấp nhận một counter phía trước trong cửa sổ, counter thấp hơn sẽ bị từ chối dù chưa dùng. Đây là hệ quả của chính sách mốc tăng dần.
- Đồng hồ nhảy hoặc cấu hình cửa sổ quá rộng có thể ảnh hưởng khả năng sử dụng. Không khắc phục bằng cách tùy tiện đặt lại mốc đã chấp nhận.
- Tất cả endpoint sử dụng cùng authenticator phải chia sẻ trạng thái tiêu thụ tương ứng. Khóa chỉ theo `challengeId` không giải quyết dùng lại xuyên flow.
- Thay secret cần gắn với phiên bản authenticator thực sự mới; không đổi nhãn phiên bản của cùng secret chỉ để bỏ qua lịch sử sử dụng.

Một cách khác là giữ tập counter đã sử dụng với ràng buộc duy nhất trên định danh authenticator, phiên bản secret và counter. Dấu đã dùng phải tồn tại ít nhất suốt khoảng mà counter còn có thể được mọi verifier chấp nhận, kể cả độ lệch cho phép. Xóa quá sớm sẽ mở lại khả năng replay.

Không dùng riêng chuỗi sáu chữ số làm khóa chống dùng lại vĩnh viễn. Không gian mã hữu hạn có thể lặp lại. Nếu một mã khớp nhiều counter trong cùng cửa sổ, cần chính sách xử lý xác định; không được thử một counter khác chỉ để biến một lần đã bị nhận diện replay thành thành công. Một chính sách bảo thủ có thể từ chối trường hợp mơ hồ và hướng dẫn người dùng chờ mã kế tiếp.

## 8. Resend và nhiều challenge đang chờ

Nút “gửi lại mã” tạo ra vấn đề về thế hệ và trạng thái.

Dịch vụ có thể chọn gửi lại cùng challenge chưa dùng hoặc phát hành challenge mới. Dù chọn cách nào, không được làm một challenge đã tiêu thụ trở lại trạng thái chưa dùng.

Với chính sách chỉ chấp nhận thế hệ mới nhất:

~~~text
C1: ISSUED
resend tạo C2
C1: SUPERSEDED
C2: ISSUED
~~~

Việc thay thế phải dùng cùng cơ chế đồng bộ với xác minh. Nếu resend và verify không phối hợp, hệ thống có thể vừa tiêu thụ C1 vừa phát hành C2 như một đường xác minh độc lập ngoài ý định.

Nếu C1 đã giúp flow đạt `OTP_VERIFIED`, resend không được đưa flow trở lại `OTP_PENDING` rồi cấp thêm một bằng chứng. Nếu nghiệp vụ cho phép nhiều challenge cùng sống, cần quy định rõ khi một challenge thành công thì những challenge còn lại mất hiệu lực thế nào.

Số lần thử cũng cần được giới hạn ở phạm vi phù hợp như flow, tài khoản hoặc authenticator, không chỉ mỗi challenge. Nếu cứ resend là có lại một ngân sách thử hoàn toàn mới, kẻ tấn công có thể kéo dài khả năng đoán mã.

## 9. Retry hợp lệ và idempotency

Mạng có thể mất phản hồi sau khi transaction đã commit:

~~~text
Client          Máy chủ                Cơ sở dữ liệu
  | verify OTP     |                         |
  |--------------->| consume + evidence      |
  |                |------------------------>|
  |                |        COMMIT           |
  |                |<------------------------|
  |    mất phản hồi                          |
  | retry          |                         |
  |--------------->|                         |
~~~

Giải pháp không phải chấp nhận OTP lần hai. Dịch vụ có thể dùng một định danh thao tác để trả lại kết quả đã commit cho đúng ngữ cảnh có quyền.

Bản ghi idempotency nên ràng buộc với flow, ngữ cảnh được phép và nội dung thao tác. Cùng một key nhưng payload hoặc chủ thể khác phải được xử lý như xung đột, không dùng để lấy kết quả của người khác.

Những quy tắc quan trọng:

1. Retry hợp lệ chỉ đọc lại hoặc tiếp tục cùng thao tác đã định danh, không tạo một lần xác minh OTP mới.
2. Dùng idempotency key khác không vượt qua được trạng thái `CONSUMED` hoặc mốc TOTP đã dùng.
3. OTP và một key do client biết không đủ làm bằng chứng để cấp lại bearer token khôi phục cho phiên khác.
4. Nếu trả lại kết quả có chứa bí mật, phải có chính sách lưu trữ và xác thực truy cập riêng; lựa chọn đơn giản hơn là trả trạng thái thao tác không chứa bí mật.
5. Khi flow đã hết hạn, bị hủy hoặc trạng thái bảo mật đã thay đổi, việc xem lại kết quả cũ không được hồi sinh quyền khôi phục.

Tính dùng một lần nói về số lần tạo hiệu lực xác thực. Idempotency nói về việc gửi lại một thao tác có tạo thêm hiệu lực nghiệp vụ hay không. Hai cơ chế bổ sung cho nhau.

## 10. Triển khai nhiều instance và lỗi kho trạng thái

Dữ liệu chống dùng lại cần có một nơi quyết định thống nhất cho các request cạnh tranh.

| Thiết kế | Vấn đề cần tránh |
| --- | --- |
| Mỗi instance giữ `usedCodes` trong RAM | Instance khác không biết mã đã dùng |
| Đọc trạng thái từ replica có độ trễ | Request sau có thể thấy trạng thái trước khi tiêu thụ |
| Cache dấu đã dùng với TTL quá ngắn | Mã được chấp nhận lại khi dấu biến mất |
| Kho dùng lại không truy cập được nhưng vẫn cho qua | Mất khả năng chứng minh tính dùng một lần |
| Chuyển vùng/failover làm mất bản ghi đã commit | Replay có thể thành công lại sau sự cố |
| Xóa mã ở cache rồi cập nhật flow trong DB | Hai trạng thái có thể lệch nhau nếu một thao tác thất bại |

Một thao tác nguyên tử như `SET NX` có thể tranh quyền ghi một khóa trong Redis, nhưng tự nó không bảo đảm bằng chứng ở cơ sở dữ liệu khác được ghi nguyên tử, cũng không tự chứng minh chính sách bền vững khi failover. Nếu chọn một kho ngoài cơ sở dữ liệu nghiệp vụ, cần thiết kế rõ điểm commit, độ bền và cách phục hồi.

Khi không xác định được mã đã dùng hay chưa, không phát hành quyền mới dựa trên giả định có lợi. Có thể trả lỗi tạm thời, giữ trạng thái đang xử lý và hướng dẫn retry cùng thao tác theo cơ chế được hỗ trợ.

## 11. Phản hồi, ghi nhận và xử lý một lần dùng lại

Trạng thái nội bộ có thể phân biệt:

~~~text
OTP_INVALID
OTP_EXPIRED
OTP_ALREADY_CONSUMED
OTP_ATTEMPT_LIMIT_REACHED
RECOVERY_CONTEXT_MISMATCH
RECOVERY_FLOW_NOT_ACTIVE
VERIFICATION_TEMPORARILY_UNAVAILABLE
~~~

Không nhất thiết trả nguyên mọi chi tiết này ra một endpoint công khai. Phản hồi phải phù hợp ngữ cảnh xác thực, tránh biến API thành công cụ dò tài khoản, mã hợp lệ hoặc trạng thái bảo mật của người khác.

Có thể ghi nhận mã định danh nội bộ của flow/challenge, thời điểm, endpoint, instance xử lý, kết quả quyết định và định danh thao tác. Dữ liệu giám sát cần có chính sách truy cập và lưu giữ; không ghi OTP, token phiên khôi phục hoặc seed.

Một lần dùng lại có thể do người dùng bấm hai lần, proxy gửi lại, client retry sau timeout hoặc kẻ tấn công phát lại. Vì vậy, không khóa vĩnh viễn tài khoản chỉ từ một sự kiện trùng.

Nên xem sự kiện cùng bối cảnh: đã có thay đổi nhạy cảm hay chưa, request đến từ ngữ cảnh nào, có nhiều lần thử xuyên flow hay không và chủ tài khoản có báo mất quyền truy cập không. Khi nghi ngờ chiếm tài khoản, sử dụng quy trình đã xác minh để xử lý flow đang chờ, bằng chứng khôi phục, phương thức xác thực và phiên liên quan.

Thông báo người dùng cần chỉ ra bước an toàn tiếp theo. Không hướng dẫn họ đọc mã cho nhân viên để “xác minh lần dùng lại”.

## 12. Hậu quả thực tế của một điểm tiêu thụ duy nhất

Giả sử A và B đồng thời gửi đúng mã cho C1. A giành được quyền cập nhật trước, tiêu thụ C1 và ghi bằng chứng cho F1 trong cùng transaction. Sau khi A commit, B không còn thỏa điều kiện sử dụng challenge.

Nếu A rollback trước khi có bất kỳ hiệu lực xác thực được phát hành, trạng thái chưa commit không được coi là một lần xác minh thành công. Một request sau có thể tiếp tục nếu challenge và mọi điều kiện khác vẫn hợp lệ. Ngược lại, nếu A đã commit nhưng mất phản hồi, C1 vẫn đã dùng; hệ thống xử lý việc lấy lại kết quả bằng định danh thao tác và kiểm tra quyền, không mở lại mã.

Từ bằng chứng đã commit, flow chỉ được thực hiện bước khôi phục mà chính sách cho phép. Thay mật khẩu, thay MFA hoặc thêm passkey cần tiếp tục kiểm soát hiệu lực bằng chứng, phiên bản bảo mật và tính dùng một lần của quyền thực hiện bước cuối. Nếu bước cuối có thể bị phát lại, việc chặn replay OTP riêng lẻ chưa bảo vệ được toàn bộ hành trình.
