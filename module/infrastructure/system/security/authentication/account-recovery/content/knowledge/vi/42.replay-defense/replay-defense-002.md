# Challenge response replay

Một phản hồi xác thực hợp lệ chứng minh điều gì đó tại thời điểm nó được tạo ra. Nếu máy chủ tiếp tục chấp nhận phản hồi ấy ở lần sau, người ghi lại nó có thể dùng lại bằng chứng cũ để vượt qua bước khôi phục.

Trong khôi phục tài khoản, hậu quả có thể là mở lại quyền đặt mật khẩu, thay MFA hoặc đăng ký thêm passkey sau khi giao dịch ban đầu đã kết thúc. **Challenge response replay** là việc phát lại phản hồi của một lần thử thách trước để được chấp nhận thêm lần nữa, trong cùng giao dịch hoặc trong một giao dịch khác.

Bài này tập trung vào cách giữ cho bằng chứng có tính mới, đúng ngữ cảnh và chỉ được tiêu thụ theo chính sách một lần. Thiết kế minh họa dùng một phương thức xác thực dự phòng đã liên kết với tài khoản; nó không giả định người đã mất mọi phương thức vẫn có thể sử dụng khóa cũ.

## 1. Challenge và response có vai trò khác nhau

Trong mô hình challenge–response, máy chủ đưa ra một giá trị thử thách mới. Bên xác thực tạo phản hồi bằng cơ chế chứng minh quyền kiểm soát phương thức xác thực. Máy chủ kiểm tra cả phản hồi lẫn thử thách mà mình đang chờ.

| Thành phần | Vai trò | Điều không thể suy ra chỉ từ thành phần đó |
| --- | --- | --- |
| Challenge hoặc nonce | Phân biệt lần xác thực hiện tại với lần trước | Ai kiểm soát tài khoản |
| Response | Bằng chứng được tạo theo giao thức | Giao dịch vẫn còn quyền thực hiện hành động |
| Challenge ID | Tra bản ghi thử thách | Bản thân người gửi có đủ quyền khôi phục |
| Recovery transaction | Giữ ngữ cảnh và tiến độ khôi phục | Mọi bằng chứng trong quá khứ đều còn dùng được |
| Quyết định chấp nhận | Kết quả kiểm tra bằng chứng và trạng thái hiện tại | Có thể bỏ qua chính sách cho bước tiếp theo |

Nonce không nhất thiết là bí mật. Trong xác thực bằng khóa công khai, việc nhìn thấy challenge không đủ để tạo chữ ký hợp lệ. Điều quan trọng là challenge khó đoán trước, không bị tái sử dụng sai và được phản hồi đúng theo giao thức.

Nếu server chỉ yêu cầu client gửi lại chính nonce vừa nhận, người nhận được nonce cũng có thể trả lại nó. Cơ chế đó không tự chứng minh quyền kiểm soát một khóa hay một phương thức khôi phục đã đăng ký. Trường hợp mã được gửi qua kênh khôi phục đã xác minh có mô hình bảo vệ riêng, trong đó khả năng truy cập kênh là một phần của bằng chứng.

## 2. Replay khác với đoán và chuyển tiếp trực tiếp

Giả sử người dùng dùng khóa dự phòng để duyệt việc thay MFA:

~~~text
Lần đầu:
  Server phát challenge C1.
  Khóa tạo response R1 cho C1.
  Server chấp nhận R1 và cho giao dịch đi tiếp.

Lần phát lại:
  Một bên gửi lại R1.
  Server vẫn chấp nhận và cấp thêm quyền khôi phục.
~~~

R1 có thể vẫn có chữ ký hợp lệ. Lỗi nằm ở việc máy chủ xem bằng chứng cũ như một lần xác thực mới.

Cần phân biệt các tình huống:

| Tình huống | Vấn đề chính |
| --- | --- |
| Gửi response cũ sau khi đã dùng thành công | Tái sử dụng bằng chứng |
| Gửi hai bản sao cùng lúc | Tranh chấp tiêu thụ challenge |
| Đưa response của giao dịch A sang giao dịch B | Thiếu ràng buộc ngữ cảnh |
| Dự đoán challenge sắp được phát | Thiếu tính khó đoán |
| Chuyển tiếp challenge mới cho nạn nhân và giành gửi response trước | Tấn công chuyển tiếp trong thời gian thực |
| Đánh cắp quyền khôi phục được cấp sau bước xác thực | Lạm dụng credential hoặc session ở bước sau |

Cơ chế dùng một lần ngăn chấp nhận lặp lại nhưng không bảo đảm người gửi bản đầu tiên là người hợp pháp nếu bằng chứng đang bị chuyển tiếp. Vì vậy, chống replay cần phối hợp với ràng buộc nguồn xác thực, bảo vệ kênh và kiểm soát session.

NIST mô tả chống replay là khả năng ngăn đạt được xác thực thành công bằng cách ghi lại và phát lại thông điệp cũ. Đặc tính này bổ sung cho bảo vệ của kênh truyền, vì thông điệp có thể bị lấy ở ngoài kênh đó. Xem [NIST SP 800-63B, Replay Resistance](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#replay).

## 3. Phát challenge từ môi trường đáng tin

Với WebAuthn, RP phải tạo challenge ngẫu nhiên trong môi trường mình tin cậy, đối chiếu challenge trong phản hồi và tránh phụ thuộc vào hành vi của client để giữ trạng thái. Đặc tả khuyến nghị challenge dài ít nhất 16 byte với đủ entropy để chống đoán. Xem [WebAuthn Level 3, Cryptographic Challenges](https://www.w3.org/TR/webauthn-3/#sctn-cryptographic-challenges).

Trong thiết kế minh họa của bài này, server phát 32 byte ngẫu nhiên bằng bộ sinh số ngẫu nhiên mật mã. Đây là lựa chọn thiết kế, không phải một con số bắt buộc cho mọi giao thức.

Không dùng những dữ liệu sau làm challenge độc lập:

- Thời gian hiện tại hoặc số thứ tự tăng dần.
- Email, ID tài khoản hoặc ID thiết bị.
- Giá trị do client tự tạo mà server không có cơ chế ràng buộc và xác minh.
- Một chuỗi cố định được chia sẻ giữa các lượt khôi phục.

Base64url chỉ là cách biểu diễn byte. Mã hóa một timestamp sang Base64 không tạo thêm entropy.

Thời hạn hiệu lực giới hạn khoảng thời gian có thể chấp nhận phản hồi. Nó không thay thế tính dùng một lần: nếu challenge còn hạn 60 giây, hai bản sao gửi trong giây đầu tiên vẫn phải tranh cùng một quyền tiêu thụ.

## 4. Ràng buộc challenge với giao dịch khôi phục

Một bản ghi thử thách có thể được thiết kế như sau:

~~~text
ChallengeRecord
  challengeId
  challengeBytes
  recoveryTransactionId
  accountId
  purpose
  allowedCredentialReference
  contextVersion
  boundParametersHash
  expiresAt
  state
  consumedAt
~~~

Các trường trên là mô hình khái niệm, không phải schema bắt buộc.

**Account và transaction:** server xác định tài khoản cùng giao dịch mà bằng chứng thuộc về. Không cho phép sửa các giá trị này chỉ bằng cách thay JSON trong request.

**Purpose:** phân biệt bằng chứng dành cho đăng nhập, duyệt thay MFA, xác nhận đổi email hoặc đăng ký passkey. Một response dùng để đăng nhập không tự trở thành quyền thay mọi phương thức khôi phục.

**Credential:** khóa dùng để kiểm tra phải là khóa được tài khoản và chính sách hiện tại chấp nhận. Một public key mới do người gọi cung cấp có thể xác minh chữ ký của chính người gọi, nhưng chưa chứng minh quyền khôi phục tài khoản.

**Context version:** khi giao dịch bị hủy, thay đổi mục tiêu hoặc bị thu hồi quyền, phiên bản ngữ cảnh có thể thay đổi. Response tạo trước thay đổi đó không được âm thầm áp dụng cho ngữ cảnh mới.

**Tham số quan trọng:** nếu việc duyệt cần gắn với một đích cụ thể, chẳng hạn email khôi phục mới, server lưu giá trị đã chuẩn hóa hoặc dấu vết mật mã của biểu diễn chuẩn. Trước khi áp dụng, server đối chiếu lại các tham số có ý nghĩa bảo mật.

Ràng buộc có thể dựa vào challenge ngẫu nhiên ánh xạ tới bản ghi bất biến phía server. Không nhất thiết phải nhét toàn bộ thông tin tài khoản vào dữ liệu công khai. Nếu giao thức có payload cần ký, phải dùng định dạng và cơ chế tách ngữ cảnh được xác định rõ; tránh ghép chuỗi tùy tiện hoặc tự sáng tác giao thức mật mã.

## 5. Vòng đời của challenge

Một mô hình trạng thái đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> CONSUMED: Xác minh và commit thành công
    ISSUED --> CANCELLED: Giao dịch bị hủy hoặc thay thế hợp lệ
    ISSUED --> EXPIRED: Vượt thời hạn phía server
    CONSUMED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

Ý nghĩa các trạng thái:

- **ISSUED:** còn có thể được xét chấp nhận nếu mọi điều kiện khác phù hợp.
- **CONSUMED:** bằng chứng đã được dùng để tạo ra kết quả đã ghi nhận.
- **CANCELLED:** giao dịch hoặc thử thách đã bị vô hiệu hóa theo chính sách.
- **EXPIRED:** không còn hiệu lực theo thời gian của hệ thống xác minh.

EXPIRED có thể là trạng thái suy ra từ `expiresAt`. Việc từ chối không được phụ thuộc vào tác vụ dọn dẹp đã kịp chạy hay chưa. Một bản ghi vẫn ghi ISSUED nhưng đã quá hạn cũng phải bị từ chối.

Không chuyển CONSUMED trở lại ISSUED để xử lý việc client không nhận được phản hồi HTTP. Thử thách mới phải là một lần phát mới theo quyền của giao dịch hiện tại.

Việc thay challenge cũ cũng cần có phạm vi. Một yêu cầu công khai không xác thực không nên có khả năng liên tục hủy mọi challenge hợp lệ của nạn nhân.

## 6. Xác minh rồi tiêu thụ nguyên tử

Một lỗi phổ biến là tách việc đọc trạng thái và đánh dấu đã dùng thành hai thao tác không được bảo vệ:

~~~text
Request A đọc: ISSUED
Request B đọc: ISSUED

Request A xác minh hợp lệ.
Request B xác minh hợp lệ.

Request A cấp quyền khôi phục.
Request B cũng cấp quyền khôi phục.
~~~

Cả hai đều kiểm tra “chưa dùng”, nhưng không có điểm quyết định duy nhất.

Thiết kế minh họa sử dụng một transaction trong kho dữ liệu có khả năng điều phối đồng thời:

~~~text
1. Tra challenge và ngữ cảnh dự kiến từ dữ liệu server.
2. Kiểm tra cấu trúc, giới hạn kích thước và response theo giao thức.
3. Nếu bằng chứng không hợp lệ: từ chối, không cấp quyền.

4. Bắt đầu database transaction.
5. Khóa hoặc kiểm tra có điều kiện giao dịch khôi phục hiện tại.
6. Kiểm tra lại account, purpose, contextVersion, thời hạn và quyền hiện tại.
7. Chuyển challenge từ ISSUED sang CONSUMED bằng thao tác có điều kiện.
8. Yêu cầu đúng một bản ghi được chuyển trạng thái.
9. Ghi kết quả xác minh và quyền khôi phục có phạm vi phù hợp.
10. Commit.
~~~

Việc xác minh chữ ký có thể diễn ra trước transaction để giảm thời gian giữ khóa. Tuy nhiên, dữ liệu và policy có thể đã thay đổi trong khoảng đó. Bước trong transaction phải kiểm tra lại những điều kiện có thể thay đổi; nếu trạng thái credential thay đổi thì kết quả xác minh trước đó chỉ được dùng khi vẫn phù hợp.

Ví dụ SQL khái niệm cho bước tiêu thụ:

~~~sql
UPDATE recovery_challenge
SET state = 'CONSUMED',
    consumed_at = :trusted_now
WHERE challenge_id = :challenge_id
  AND recovery_transaction_id = :server_transaction_id
  AND account_id = :server_account_id
  AND context_version = :expected_context_version
  AND state = 'ISSUED'
  AND expires_at > :trusted_now;
~~~

Các tham số ngữ cảnh đến từ giao dịch đã được server kiểm tra, không đơn giản lấy nguyên từ request. Câu lệnh này chỉ minh họa phép chuyển trạng thái; nó không thay thế bước xác minh mật mã hoặc kiểm tra quyền.

Nếu số hàng bị cập nhật bằng 0, request không giành được quyền tiêu thụ. Hệ thống không được tiếp tục cấp một grant mới.

Kết quả xác minh và challenge đã tiêu thụ nên được ghi trong cùng ranh giới transaction nếu cùng kho dữ liệu. Nếu bước tiếp theo là thay đổi tài khoản ngay, thay đổi đó cũng cần được phối hợp trong ranh giới nhất quán phù hợp. Không đánh dấu challenge đã dùng rồi tùy tiện giả định một thay đổi ở hệ thống khác chắc chắn thành công.

## 7. Nhiều instance và tác dụng phụ bên ngoài

Trong triển khai nhiều instance, một biến `usedChallenges` trong bộ nhớ của từng tiến trình chỉ ngăn replay trên chính tiến trình đó. Load balancer có thể đưa bản sao tới instance khác.

Tương tự, hai instance cùng đọc từ replica cập nhật chậm có thể đều nhìn thấy trạng thái ISSUED. Quyết định tiêu thụ cần đi qua cơ chế dùng chung với bảo đảm nhất quán phù hợp, chẳng hạn phép cập nhật có điều kiện trên kho dữ liệu có thẩm quyền.

Nếu dùng cache, cần hiểu rõ thao tác nguyên tử, thời gian giữ trạng thái và hành vi khi failover. Khi kho chống replay không sẵn sàng, không được coi đó là lý do để chấp nhận bằng chứng mà không kiểm soát tiêu thụ.

Nếu có tác dụng phụ ngoài database, có thể ghi một sự kiện outbox cùng transaction đã tiêu thụ challenge. Bộ xử lý sự kiện dùng ID thao tác ổn định và cơ chế idempotency ở phía nhận để tránh thực hiện lặp.

Đây là đề xuất kiến trúc cho bài học: nó tách việc chỉ một request được chấp nhận khỏi việc thông điệp có thể được giao nhiều lần. Gửi email thông báo lặp là một vấn đề vận hành; cấp lại quyền thay MFA hoặc thực hiện thay đổi lặp là vấn đề bảo mật cần được kiểm soát riêng.

## 8. Retry hợp lệ không được mở lại bằng chứng

Người dùng có thể gửi response thành công nhưng mất kết nối trước khi nhận kết quả. Khi trình duyệt gửi lại, hệ thống cần xử lý sự không chắc chắn này mà không coi response cũ là một lần xác thực mới.

Một cách thiết kế:

1. Lần đầu commit kết quả và ghi nhận ID thao tác trong giao dịch khôi phục.
2. Request lặp không được tạo thêm grant hoặc lặp thay đổi.
3. Client đã có ngữ cảnh được phép có thể truy vấn trạng thái thao tác.
4. Nếu cần thực hiện một hành động mới, server yêu cầu bằng chứng mới theo policy.

Điểm quan trọng là **idempotency của thao tác** khác với **chấp nhận lại bằng chứng**. Trả “bước này đã hoàn tất” trong một ngữ cảnh được bảo vệ có thể phù hợp. Phát một recovery session mới chỉ vì nhận lại response cũ có thể biến response đó thành credential tái sử dụng.

Challenge ID không đủ để cho bất kỳ ai truy vấn toàn bộ dữ liệu khôi phục. Endpoint xem trạng thái vẫn cần giới hạn thông tin và quyền truy cập thích hợp.

Nếu transaction rollback trước khi tạo bất kỳ kết quả nào, challenge có thể vẫn ở ISSUED theo thiết kế transaction. Lần thử tiếp theo chỉ được xét trong thời hạn và ngữ cảnh còn hợp lệ. Không có lý do tự chuyển một challenge đã commit CONSUMED trở lại chưa dùng.

## 9. Khi dùng WebAuthn, OTP hoặc token tự chứa

### WebAuthn

Không chỉ kiểm tra rằng response có chữ ký đúng. Việc xác minh cần theo giao thức, bao gồm challenge dự kiến, loại nghi thức, origin, RP ID và các yêu cầu xác thực tương ứng. Sau xác minh, hệ thống vẫn phải áp dụng cơ chế tiêu thụ challenge của giao dịch khôi phục.

Bộ đếm chữ ký của authenticator không thay thế kho trạng thái challenge dùng một lần. Trong thiết kế khôi phục, bằng chứng hợp lệ về một credential cũng chỉ đóng góp phần quyền mà policy của giao dịch cho phép.

### OTP

Với OTP, hết thời gian hiệu lực không phải cơ chế duy nhất ngăn phát lại. NIST yêu cầu verifier chỉ chấp nhận một OTP một lần khi nó còn hợp lệ; xem [Single-Factor OTP Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#sfotpver). Điều này cần được áp dụng nhất quán giữa các instance.

OTP không tự có cùng cơ chế ràng buộc giao dịch như một giao thức ký challenge. Dịch vụ cần xác định mã đang phục vụ bước nào, đồng thời tránh việc một mã đã dùng được chấp nhận thêm ở một phiên khác.

### Token tự chứa

Một token có chữ ký, `exp` và ID duy nhất vẫn có thể được phát lại cho tới khi hết hạn nếu server chỉ xác minh chữ ký và thời gian. ID duy nhất giúp nhận diện token; để dùng một lần, hệ thống cần trạng thái tiêu thụ hoặc một cơ chế tương đương.

Server ký challenge chỉ chứng minh challenge do server phát và chưa bị sửa theo cơ chế đó. Việc client đưa token đã ký trở lại không tự chứng minh client kiểm soát phương thức xác thực của tài khoản.

## 10. Ví dụ: hai response giống nhau đến hai instance

Minh mất điện thoại chứa ứng dụng MFA nhưng còn một khóa bảo mật dự phòng. Giao dịch R cho phép dùng khóa đó như một bằng chứng trong quy trình thay MFA.

Server phát C cho R, ràng buộc với tài khoản, mục đích và phiên bản ngữ cảnh. Minh tạo phản hồi hợp lệ P. Do gửi lại trên mạng, P đến cả instance A và B.

Cả hai có thể xác minh chữ ký thành công. Tuy nhiên, khi chuyển trạng thái challenge trong kho dùng chung, chỉ A cập nhật được một bản ghi. A ghi kết quả của bước xác minh và commit. B không được cấp thêm một grant.

Nếu Minh không nhận được kết quả của A, giao diện có thể đọc trạng thái R qua ngữ cảnh khôi phục đã được bảo vệ. Nó không cần mở lại challenge C.

Nếu một bên lấy P rồi đưa sang giao dịch S để đổi email khôi phục, server từ chối vì giao dịch và mục đích không khớp. Nếu R đã bị hủy trước khi commit, bước kiểm tra hiện trạng cũng phải chặn việc tiếp tục, dù chữ ký của P vẫn hợp lệ.

## 11. Giữ bằng chứng cũ khỏi trở thành quyền mới

Thiết kế chống challenge response replay cần phối hợp các yếu tố: challenge mới từ nguồn đáng tin, phản hồi được xác minh đúng giao thức, ngữ cảnh khôi phục được ràng buộc và một điểm tiêu thụ nguyên tử có thẩm quyền.

Dữ liệu vận hành có thể ghi loại kết quả, ID giao dịch nội bộ, thời điểm và nguyên nhân từ chối đã phân loại. Không ghi toàn bộ response, token khôi phục, OTP hoặc credential phiên vào log và công cụ phân tích.

Một bước challenge–response thành công không tự kết thúc mọi đánh giá rủi ro. Khi bằng chứng được dùng để cho phép thay mật khẩu, MFA hoặc passkey, quyền tạo ra sau bước đó vẫn cần có mục đích, thời hạn và cơ chế dùng phù hợp. Nếu không, hệ thống có thể chặn replay ở challenge nhưng lại để quyền khôi phục sau đó bị sử dụng lại.
