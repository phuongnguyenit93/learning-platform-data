# Referral abuse: Lạm dụng cơ chế giới thiệu qua luồng khôi phục tài khoản

Referral abuse là việc lợi dụng cơ chế giới thiệu người dùng để nhận lợi ích không đúng điều kiện: tự giới thiệu bằng nhiều tài khoản, nhận lại thưởng một lần, chuyển nguồn giới thiệu hoặc chiếm quyền trên tài khoản có giá trị giới thiệu.

Trong module khôi phục tài khoản, vấn đề cần quan tâm là **việc lấy lại quyền truy cập không được làm mất lịch sử định danh, tạo lại quyền nhận thưởng hoặc biến thông tin giới thiệu thành bằng chứng xác minh chủ tài khoản**. Một luồng khôi phục có thể kiểm tra OTP đúng nhưng vẫn tạo lỗ hổng nếu hệ thống phía sau coi người vừa khôi phục là người dùng mới.

Ở đây, referral là quan hệ hoặc mã giới thiệu của sản phẩm. Nó khác với HTTP `Referer`, thông tin chiến dịch quảng cáo và người liên hệ khôi phục đã đăng ký. Nếu sản phẩm không có chương trình giới thiệu, không cần tự thêm cơ chế thưởng vào recovery; nguyên tắc còn lại vẫn là thông tin giới thiệu không tạo quyền sở hữu tài khoản.

## 1. Tại sao referral liên quan đến account recovery?

Một sản phẩm có thể có ba nhóm trạng thái:

1. **Danh tính tài khoản:** tài khoản nào tồn tại, các phương thức đăng nhập gắn với tài khoản nào.
2. **Bảo mật và khôi phục:** ai đang chứng minh quyền kiểm soát, bước nào đã hoàn thành, phiên nào còn hiệu lực.
3. **Giới thiệu và quyền lợi:** ai giới thiệu ai, điều kiện nào đã được đáp ứng, quyền lợi nào đã được cấp.

Lỗi xuất hiện khi thay đổi ở nhóm thứ hai vô tình ghi đè hoặc khởi tạo lại nhóm thứ nhất và thứ ba.

Ví dụ:

~~~text
Tài khoản A đã nhận thưởng người được giới thiệu.
A mất điện thoại và hoàn tất khôi phục.
Hệ thống cập nhật email mới bằng cách tạo hồ sơ B.
Dịch vụ referral nhìn thấy B như một người dùng mới.
B nhập mã giới thiệu và nhận lại quyền lợi chỉ dành cho lần đầu.
~~~

Người dùng có thể cố ý lặp lại hành vi này, hoặc một người dùng hợp lệ vô tình làm lộ lỗi. Cơ chế khôi phục không nên yêu cầu họ hiểu cách các dịch vụ nội bộ gắn định danh.

OWASP liệt kê tự giới thiệu, tạo nhiều tài khoản và các tính năng cấp giá trị như referral là những bề mặt dễ bị lạm dụng. Đây là vấn đề quy tắc nghiệp vụ, không chỉ là kiểm tra chuỗi đầu vào có đúng định dạng hay không. [OWASP Business Logic Security](https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html#protect-abuse-friendly-features).

## 2. Các đường lạm dụng cần phân biệt

| Đường lạm dụng | Điểm yếu ở luồng khôi phục | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Khôi phục thành hồ sơ mới | Dùng email hoặc số điện thoại mới làm định danh tài khoản mới | Lặp lại quyền lợi dành cho người mới |
| Gắn lại mã giới thiệu | Cho phép sửa người giới thiệu trong biểu mẫu đặt lại mật khẩu | Chuyển người hưởng lợi hoặc ghi nhận sai nguồn |
| Phát lại sự kiện hoàn tất | Consumer coi mỗi callback khôi phục là một lần đăng ký | Cấp thưởng nhiều lần |
| Tự giới thiệu qua nhiều hồ sơ | Mỗi hồ sơ riêng biệt được coi là một người độc lập | Một người điều khiển cả hai phía của quan hệ |
| Chiếm tài khoản người giới thiệu | Luồng recovery yếu hoặc hỗ trợ bị thao túng | Đổi nơi nhận lợi ích hoặc chiếm tài khoản có giá trị |
| Dùng mã giới thiệu để nhận hỗ trợ ưu tiên | Nhân viên coi người giới thiệu là người có thể xác nhận chủ tài khoản | Hạ yêu cầu xác minh hoặc tiết lộ thông tin |
| Dùng lời mời để phát tán phishing | Trộn liên kết giới thiệu với lời nhắn khôi phục | Người nhận bị dẫn sang luồng thu thập bí mật |

Không phải mọi tài khoản khôi phục nhiều lần đều gian lận. Không phải mọi người dùng chung thiết bị hoặc mạng đều do một người điều khiển. Cần phân biệt **bất biến có thể thực thi chắc chắn** với **tín hiệu cần đánh giá thêm**.

Ví dụ, hai request không được cấp cùng một quyền lợi hai lần là bất biến có thể cưỡng chế bằng dữ liệu. Hai tài khoản dùng cùng Wi-Fi chỉ là một tín hiệu yếu về mối liên hệ.

## 3. Những bất biến giữa recovery và referral

Với chương trình minh họa chỉ thưởng một lần cho người dùng mới hợp lệ, có thể quy định:

- Khôi phục thành công giữ nguyên định danh tài khoản nghiệp vụ.
- Đổi mật khẩu, thay MFA hoặc đăng ký lại passkey không làm tài khoản trở thành người mới.
- Đổi email hoặc số điện thoại không xóa lịch sử đã nhận quyền lợi.
- Mã giới thiệu không có quyền thay đổi tài khoản đích của recovery.
- Việc khôi phục không tự sửa người giới thiệu đã được chốt.
- Một quyền lợi theo chính sách chỉ được ghi nhận một lần, kể cả khi request hoặc sự kiện được gửi lại.
- Khôi phục thành công không tự bỏ mọi trạng thái hạn chế quyền lợi hoặc tự kết luận mọi hành vi trước đó là hợp lệ.
- Cờ nghi ngờ referral không tự cho phép từ chối vĩnh viễn việc lấy lại tài khoản của chủ sở hữu hợp lệ.

Các quy tắc về thời điểm chốt attribution, số lần thưởng và điều kiện tham gia phụ thuộc từng sản phẩm. Chúng cần được mô hình hóa rõ ràng; không mặc định mọi chiến dịch đều có cùng chính sách.

Điểm chung là một endpoint recovery không được âm thầm thay đổi các quy tắc đó.

## 4. Giữ định danh ổn định khi thay phương thức xác thực

Nên phân biệt:

~~~text
Account
  accountId                  định danh tài khoản nghiệp vụ
  createdAt                  thời điểm tạo tài khoản
  securityVersion            phiên bản trạng thái bảo mật

Authenticator / LoginIdentity
  authenticatorId
  accountId
  type
  providerSubject
  status

RecoveryFlow
  recoveryFlowId
  accountId
  purpose
  state
  proofReferences

ReferralAttribution
  attributionId
  campaignId
  referrerAccountId
  refereeAccountId
  policyVersion
  state
~~~

Email, số điện thoại và passkey giúp truy cập tài khoản nhưng không nên được coi là toàn bộ định danh tài khoản nghiệp vụ. Ví dụ, Firebase sử dụng `uid` để định danh người dùng và có các thao tác riêng để cập nhật thuộc tính người dùng. [Firebase Authentication: Quản lý người dùng](https://firebase.google.com/docs/auth/admin/manage-users).

Từ đó, một thiết kế ứng dụng có thể giữ `accountId` làm điểm nối ổn định cho lịch sử giới thiệu khi thay thuộc tính đăng nhập. Đây là quyết định của mô hình nghiệp vụ, không phải bảo đảm rằng mọi nhà cung cấp danh tính đều tự xử lý chương trình referral của ứng dụng.

### Không tự gộp hồ sơ để giải quyết trùng lặp

Hai hồ sơ có cùng email, cùng thiết bị hoặc có quan hệ giới thiệu không đủ để kết luận chúng thuộc cùng một chủ thể. Gộp sai có thể trở thành chiếm đoạt tài khoản.

Auth0 cảnh báo liên kết tài khoản không an toàn có thể tạo quyền truy cập trái phép, và yêu cầu xác thực cả hai tài khoản trong quy trình liên kết. [Auth0: Các lưu ý khi liên kết tài khoản](https://auth0.com/docs/manage-users/user-accounts/user-account-linking#precautions).

Nếu sản phẩm cho phép gộp tài khoản:

- Dùng quy trình riêng để chứng minh quyền đối với các tài khoản liên quan.
- Có ánh xạ định danh cũ sang định danh chuẩn để giải quyết lịch sử.
- Đối chiếu các quyền lợi trùng trước khi tạo quyền lợi mới.
- Giữ dấu vết thay đổi, không xóa bút toán cũ để làm dữ liệu có vẻ chưa từng được sử dụng.
- Không dùng việc “cùng người giới thiệu” làm bằng chứng để tự gộp.

Một định danh ổn định chỉ ngăn một số lỗi đặt lại trạng thái. Nó không chứng minh một người ngoài đời chỉ có một tài khoản.

## 5. Mã giới thiệu không phải bằng chứng khôi phục

Mã giới thiệu thường được chia sẻ công khai hoặc dùng nhiều lần theo thiết kế. Người biết mã có thể là bất kỳ người nhận lời mời nào.

Vì vậy, không dùng các dữ liệu sau làm bằng chứng sở hữu độc lập:

- Mã referral mà tài khoản đã nhập.
- Tên hoặc tài khoản của người giới thiệu.
- Số người đã được giới thiệu.
- Thông tin chiến dịch hoặc cookie attribution.
- Header `Referer` hoặc địa chỉ trang trước đó.
- Lời xác nhận của một người tự xưng là người giới thiệu.

Một mã có chữ ký hợp lệ chỉ chứng minh dữ liệu đáp ứng cơ chế kiểm tra chữ ký tương ứng. Nó không tự chứng minh người trình mã là chủ tài khoản, các tài khoản là những người khác nhau hoặc giao dịch nhận thưởng là hợp lệ.

Cần tách rõ token:

| Dữ liệu | Mục đích | Quyền không được suy diễn |
| --- | --- | --- |
| Mã giới thiệu | Xác định nguồn giới thiệu theo chiến dịch | Quyền đặt lại mật khẩu hoặc thay MFA |
| Token khôi phục | Cho phép một bước khôi phục đã xác định | Quyền đổi người giới thiệu hay nơi nhận thưởng |
| Mã hồ sơ hỗ trợ | Tra cứu một hồ sơ trong phạm vi được phép | Quyền nhận thông tin bí mật của tài khoản |
| Xác nhận của người liên hệ khôi phục | Một thành phần của quy trình đã đăng ký trước, nếu có | Quyền bảo lãnh tùy ý chỉ vì đã giới thiệu người dùng |

Nếu sản phẩm có recovery contact, quyền đó phải được thiết lập và kiểm soát bằng chính sách khôi phục riêng. Không tự chuyển một quan hệ referral thành quan hệ recovery contact.

## 6. Giới hạn ghi của thao tác hoàn tất khôi phục

Giả sử người dùng mất MFA và đã thỏa các điều kiện xác minh của dịch vụ. Thao tác hoàn tất có thể có dạng:

~~~text
BEGIN

lock recovery flow and target account
check flow purpose, required evidence, expiry and security version
check the completion operation has not already been applied

replace or disable the authenticator according to the approved recovery action
advance the account security version
complete the recovery flow
record a stable ACCOUNT_RECOVERED event in the outbox

COMMIT
~~~

Trong thiết kế này, dữ liệu đầu vào không có quyền ghi `referrerAccountId`, `newUserEligible`, `rewardAmount` hoặc `payoutDestination`.

Những trường đó cần được từ chối hoặc loại bỏ theo hợp đồng API rõ ràng. Không chỉ ẩn chúng trên giao diện rồi để backend vẫn nhận và áp dụng.

Sự kiện `ACCOUNT_RECOVERED` khác `ACCOUNT_CREATED`. Consumer phải hiểu đúng ý nghĩa và phiên bản schema, thay vì suy luận từ một cờ chung như `active=true` hoặc `emailVerified=true`.

Nếu thay email là một phần được phép của recovery, vẫn giữ tài khoản nghiệp vụ và lịch sử tương ứng. Việc xác minh email mới không phải một sự kiện đăng ký mới.

### Khi khôi phục có ảnh hưởng đến quyền lợi

Khôi phục sau nghi ngờ chiếm tài khoản có thể tạo lý do xem xét giao dịch nhạy cảm tiếp theo. Chẳng hạn, yêu cầu đổi nơi nhận lợi ích ngay sau khi thay MFA có thể cần xác minh bổ sung.

Không đồng nhất điều đó với việc mọi tài khoản vừa khôi phục đều phải bị đóng băng. Cần xét mục đích, loại quyền lợi, trạng thái an toàn của tài khoản và chính sách đã công bố.

Nếu hệ thống có thời gian chờ cho thay đổi nhạy cảm, trạng thái chờ cần được lưu phía máy chủ. Không dùng đồng hồ ở trình duyệt làm cơ chế cưỡng chế.

## 7. Ghi nhận quyền lợi bằng khóa nghiệp vụ ổn định

Một callback được xử lý một lần theo `requestId` chưa đủ. Cùng một sự kiện nghiệp vụ có thể tới qua nhiều request khác nhau.

Với chính sách minh họa “một attribution trên mỗi người được giới thiệu trong một chiến dịch; một khoản thưởng cho mỗi vai trò”, có thể dùng:

~~~text
ReferralAttribution
  attributionId
  campaignId
  referrerAccountId
  refereeAccountId
  state
  policyVersion

ReferralAward
  awardId
  attributionId
  beneficiaryRole            REFERRER hoặc REFEREE
  beneficiaryAccountId
  rewardType
  amount
  state                      PENDING, APPROVED, GRANTED, REJECTED
  qualifyingEventId
~~~

Các ràng buộc minh họa:

~~~sql
ALTER TABLE referral_attribution
ADD CONSTRAINT uq_campaign_referee
UNIQUE (campaign_id, referee_account_id);

ALTER TABLE referral_attribution
ADD CONSTRAINT ck_distinct_accounts
CHECK (referrer_account_id <> referee_account_id);

ALTER TABLE referral_award
ADD CONSTRAINT uq_attribution_role_reward
UNIQUE (attribution_id, beneficiary_role, reward_type);
~~~

Các cột trong khóa nghiệp vụ cần có yêu cầu không rỗng phù hợp. Ví dụ trên giả định mỗi loại thưởng chỉ được cấp một lần cho một vai trò của attribution. Nếu chiến dịch cho phép thưởng theo nhiều mốc, khóa phải chứa định danh mốc ổn định.

Không thêm một `recoveryFlowId` mới hoặc UUID của mỗi lần callback vào khóa duy nhất rồi coi đó là chống cấp trùng. Làm vậy sẽ cho phép mỗi lần khôi phục tạo ra một quyền lợi khác.

Ràng buộc `referrer_account_id <> referee_account_id` chỉ ngăn một tài khoản tự trỏ tới chính nó. Nó không ngăn một người điều khiển hai tài khoản.

### Cấp quyền lợi và retry

Một phác thảo xử lý:

~~~text
BEGIN

lock the attribution and relevant campaign/award state
resolve the beneficiary from trusted attribution data
check the actual qualifying event and applicable policy
check eligibility, review state and campaign limits

create or load the award using the stable business key
if already granted:
    return the existing result only to an authorized caller

transition the existing award to the allowed next state
record the ledger entry and any outbound work atomically

COMMIT
~~~

Không cấp quyền lợi chỉ vì một sự kiện nói “recovery completed”. Điều kiện nhận thưởng phải là điều kiện thực sự của chiến dịch, chẳng hạn một hoạt động đủ tiêu chuẩn đã được hệ thống có thẩm quyền ghi nhận.

Khóa duy nhất giúp chống trùng một quyền lợi nhưng không tự bảo vệ tổng ngân sách chiến dịch hoặc giới hạn nhiều hàng. Những giới hạn đó cần điểm cập nhật nguyên tử hoặc cơ chế đồng bộ riêng.

Nếu phải gọi hệ thống ngoài để cấp lợi ích, dùng định danh tác vụ ổn định và khả năng chống thực thi trùng của bên nhận. Một transaction local không làm lời gọi mạng và việc lưu kết quả trở thành nguyên tử.

Khi kết quả bên ngoài chưa rõ, cần đối soát trước khi phát lệnh mới. Không tạo `awardId` khác chỉ vì một lần gọi bị timeout.

## 8. Phát hiện tự giới thiệu mà không coi tín hiệu là kết luận

Một tài khoản mới có thể do người khác tạo hoặc do cùng người điều khiển tài khoản giới thiệu. Email khác nhau không đủ phân biệt hai trường hợp.

Trong mối liên hệ với recovery, có thể xem xét các nhóm tín hiệu:

| Nhóm tín hiệu | Ví dụ | Giới hạn khi diễn giải |
| --- | --- | --- |
| Thời gian | Nhiều tài khoản cùng khôi phục rồi hoàn thành điều kiện thưởng trong thời gian ngắn | Sự cố diện rộng cũng có thể tạo một đợt khôi phục hợp lệ |
| Quan hệ tài khoản | Nhiều hồ sơ cùng đổi sang một kênh liên hệ sau recovery | Kênh có thể dùng chung theo chính sách; cần kiểm tra ngữ cảnh |
| Luồng quyền lợi | Nhiều attribution tập trung vào một người hưởng lợi | Một người giới thiệu hoạt động tốt cũng có thể có lượng lớn người dùng thật |
| Thiết bị và mạng | Mẫu thiết bị hoặc nguồn mạng lặp lại | Gia đình, doanh nghiệp, trường học có thể dùng chung |
| Thay đổi bảo mật | Khôi phục, đổi yếu tố xác thực và đổi nơi nhận lợi ích nối tiếp nhau | Có thể là người dùng hợp lệ vừa mất thiết bị |
| Hành vi hỗ trợ | Nhiều yêu cầu cùng mẫu hoặc yêu cầu nhân viên bỏ qua bước | Không đủ để tự kết luận các tài khoản cùng chủ sở hữu |

Tín hiệu chỉ có giá trị trong phạm vi được thu thập và sử dụng phù hợp với sản phẩm. Không mặc định phải thu giấy tờ hoặc theo dõi thiết bị rộng hơn chỉ để bảo vệ một ưu đãi nhỏ.

Không chuẩn hóa email bằng cách xóa dấu chấm hoặc phần sau dấu cộng trên mọi tên miền. Quy tắc của từng nhà cung cấp không giống nhau; gộp nhầm có thể làm sai attribution hoặc ảnh hưởng recovery.

Số điện thoại cũng không phải định danh một người bất biến. Thiết kế cần tính đến thay số, chuyển chủ thể sử dụng và việc một người có nhiều số.

Một hệ thống hữu ích lưu được lý do quyết định và cho phép xem xét lại. Nhãn “gian lận” không nên chỉ xuất phát từ việc trùng một IP.

## 9. Tách kiểm soát lạm dụng khỏi quyền được khôi phục

Có thể có bốn tình huống:

| Quyền kiểm soát tài khoản | Tình trạng referral | Hướng xử lý |
| --- | --- | --- |
| Đã xác minh phù hợp | Quyền lợi hợp lệ | Hoàn tất recovery; tiếp tục xử lý quyền lợi theo chính sách |
| Đã xác minh phù hợp | Có nghi ngờ quyền lợi | Hoàn tất hoặc tiếp tục recovery theo yêu cầu bảo mật; đưa phần quyền lợi vào trạng thái xem xét phù hợp |
| Chưa đủ bằng chứng | Quyền lợi có vẻ hợp lệ | Không dùng giá trị referral để thay bằng chứng sở hữu |
| Có dấu hiệu chiếm tài khoản | Có hoặc chưa có quyền lợi bất thường | Xử lý sự cố tài khoản và hạn chế tác vụ nhạy cảm theo rủi ro |

Quyết định về thưởng và quyết định về xác thực có thể liên quan nhưng không phải một quyết định duy nhất.

Nếu mọi báo cáo “tài khoản này gian lận referral” đều khóa recovery của người bị báo cáo, kẻ tấn công có thể dùng tính năng chống gian lận để từ chối dịch vụ với nạn nhân. Đầu vào chưa được xác minh không được có quyền tác động quá rộng.

Tương tự, tài khoản có nhiều người được giới thiệu không nên được bỏ qua bằng chứng khôi phục vì “khách hàng quan trọng”. Người giới thiệu cũng không có quyền xem tiến độ khôi phục hoặc phương thức xác thực của người được giới thiệu.

### Giới hạn theo từng tính năng

Cần phân biệt ngân sách cho tạo yêu cầu khôi phục, gửi lại thông báo, thử mã, gửi lời mời và yêu cầu nhận thưởng. Một giới hạn chung theo IP khó bao phủ đúng từng hành vi và dễ ảnh hưởng người dùng chung mạng.

Với endpoint khôi phục, OWASP khuyến nghị phản hồi nhất quán để hạn chế dò tài khoản và có kiểm soát chống gửi yêu cầu quá mức. [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Một triển khai có thể dùng các khóa đếm phía máy chủ theo tài khoản, flow, nguồn và hành vi, với phạm vi tác động tương ứng. Không đặt lại toàn bộ ngân sách chỉ vì người dùng đổi email hoặc khởi tạo flow mới.

Đối với lời mời, giới hạn khả năng dùng dịch vụ để gửi spam; không nhét token recovery của người nhận vào một thông báo giới thiệu. Đối với recovery, không yêu cầu người dùng giới thiệu thêm bạn bè như điều kiện lấy lại tài khoản.

## 10. Quy trình hỗ trợ và chỉnh sửa attribution

Nhân viên hỗ trợ có thể gặp yêu cầu:

~~~text
“Tôi mất điện thoại. Hãy tạo tài khoản khác giúp tôi,
chuyển toàn bộ người được giới thiệu sang tài khoản mới,
rồi cho nhận lại thưởng vì đây là email mới.”
~~~

Đây là nhiều thao tác có quyền khác nhau. Không xử lý chúng như một lần “sửa hồ sơ” chung.

Nên tách:

- Xác minh và hoàn tất khôi phục quyền truy cập.
- Chỉnh sửa một attribution bị ghi sai, nếu chính sách cho phép.
- Liên kết hoặc chuyển đổi định danh tài khoản.
- Điều chỉnh quyền lợi đã ghi nhận.
- Thay nơi nhận hoặc cách sử dụng quyền lợi.

Mỗi loại thao tác cần quyền phù hợp, lý do, dữ liệu trước/sau và tham chiếu hồ sơ. Với thay đổi có giá trị hoặc xung đột lợi ích cao, có thể yêu cầu một người có thẩm quyền khác phê duyệt.

Nhân viên không nên tự phê duyệt điều chỉnh quyền lợi gắn với tài khoản referral của chính mình. Một ngoại lệ hợp lệ cần được ghi nhận minh bạch; không xóa lịch sử để tạo ra trạng thái “chưa từng nhận”.

Nếu phát hiện cấp thừa đã được xác nhận, sử dụng cơ chế điều chỉnh có liên kết với bút toán gốc theo chính sách. Không tự trừ lợi ích chỉ từ một tín hiệu chưa được xem xét.

## 11. Ví dụ xuyên suốt: Khôi phục không tạo lượt giới thiệu mới

Giả sử chiến dịch C có quy tắc: mỗi người dùng mới hợp lệ chỉ thuộc một attribution trong C; hai phía nhận lợi ích một lần sau hoạt động Q.

Dữ liệu ban đầu:

~~~text
Account A: người giới thiệu
Account B: người được giới thiệu
Attribution R: C, A -> B
Award W1: R, REFERRER, GRANTED
Award W2: R, REFEREE, GRANTED
~~~

B mất điện thoại chứa MFA. Sau quy trình xác minh phù hợp, B thay phương thức MFA và cập nhật email.

Kết quả đúng trong thiết kế này:

~~~text
Account B vẫn là B.
Attribution R vẫn là R.
W1 và W2 vẫn là các quyền lợi đã được ghi nhận.
RecoveryFlow F hoàn tất.
Sự kiện ACCOUNT_RECOVERED tham chiếu B và F.
Không tạo ACCOUNT_CREATED cho B.
Không tạo W3 chỉ vì B vừa khôi phục.
~~~

Nếu callback hoàn tất của F tới hai lần, lần sau không tạo thêm quyền lợi. Nếu B nhập mã referral mới trong một request tự sửa, endpoint recovery không có quyền áp dụng mã đó.

Nếu có một hồ sơ B2 mà người dùng yêu cầu liên kết, việc đó đi qua quy trình riêng. Không mặc nhiên coi B2 là người dùng mới có quyền nhận thưởng, cũng không mặc nhiên gộp B2 vào B chỉ vì hai hồ sơ dùng chung thiết bị.

Nếu người đang thực hiện F là kẻ chiếm tài khoản, việc giữ nguyên attribution chưa giải quyết được nguy cơ chiếm quyền. Vẫn cần bảo vệ bằng chứng khôi phục, token dùng một lần, quyền thay yếu tố xác thực và các phiên liên quan.

## 12. Điều tra sự cố mà không làm mất lịch sử

Khi phát hiện một đợt nhận thưởng sau recovery, cần tái dựng chuỗi sự kiện:

~~~text
accountId
recoveryFlowId
securityVersion trước và sau
attributionId
qualifyingEventId
awardId / khóa nghiệp vụ
thời điểm ghi nhận và chuyển trạng thái
chủ thể hoặc dịch vụ thực hiện
lý do xem xét / phê duyệt / từ chối
~~~

Không ghi OTP, token khôi phục, seed MFA hoặc liên kết có bí mật vào log. Việc điều tra referral không tạo lý do chia sẻ dữ liệu khôi phục với người giới thiệu.

Có thể theo dõi số lần cấp quyền lợi bị chặn do trùng khóa, tỷ lệ quyền lợi được xác nhận có vấn đề sau recovery, độ trễ xem xét và số trường hợp người dùng hợp lệ bị ảnh hưởng. Mọi tỷ lệ cần có khoảng thời gian và mẫu số rõ ràng; lượng recovery tăng đơn thuần không chứng minh có referral abuse.

Hướng xử lý nên đi đúng bề mặt lỗi: sửa consumer nhầm recovery với đăng ký, chặn ghi attribution ngoài quyền, đối soát quyền lợi cấp trùng hoặc xử lý vụ chiếm tài khoản đã xác minh. Không đặt lại mọi hồ sơ referral hay khóa toàn bộ người dùng liên quan chỉ để làm các bộ đếm trở về mức mong muốn.

Một luồng khôi phục an toàn khôi phục quyền truy cập cho đúng chủ thể, giữ tính liên tục của tài khoản và không mở lại các lợi ích đã được sử dụng. Cơ chế referral có thể tiếp tục áp dụng chính sách riêng mà không trở thành đường tắt qua xác minh danh tính.
