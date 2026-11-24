# MFA bypass eligibility

## Mục tiêu và phạm vi

**MFA bypass eligibility** là việc xác định một yêu cầu có đủ điều kiện được xử lý bằng ngoại lệ đối với luồng MFA thông thường hay không. Quyết định này phải trả lời đồng thời: người yêu cầu đã cung cấp bằng chứng gì, tài khoản và hành động có được phép dùng ngoại lệ không, quyền tạm thời gồm những gì, và ngoại lệ kết thúc bằng cách nào.

Trong chương **MFA Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, bài học tập trung vào cổng quyết định trước khi cấp quyền khôi phục hoặc truy cập tạm thời. Bối cảnh là người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực; mục tiêu là lấy lại quyền truy cập qua đánh giá rủi ro, token dùng một lần, xác minh danh tính, chống lạm dụng và kiểm soát session mà vẫn giảm nguy cơ chiếm đoạt tài khoản.

Sau bài này, người học cần có khả năng:

- Phân biệt dùng phương thức dự phòng hợp lệ, ngoại lệ MFA có giới hạn và vô hiệu hóa MFA.
- Xây dựng tiêu chí đủ điều kiện theo tài khoản, bằng chứng, hành động và trạng thái bảo mật.
- Thiết kế quyết định có lý do, phạm vi, thời hạn, điều kiện phê duyệt và khả năng thu hồi.
- Ngăn helpdesk, token recovery hoặc session tạm thời trở thành đường đăng nhập yếu thường trực.

Các trạng thái, thời hạn, hạn mức và mẫu chính sách trong bài là thiết kế minh họa của một dịch vụ giả định. Chúng không phải quy tắc mặc định của mọi sản phẩm và không tự chứng minh một hệ thống đáp ứng NIST hay một mức bảo đảm xác thực cụ thể.

## 1. Xác định đúng điều đang được xin phép

### 1.1. Không gom mọi trường hợp vào một nút “bỏ qua MFA”

| Trường hợp | Bản chất | Cách xử lý phù hợp |
| --- | --- | --- |
| Người dùng dùng khóa bảo mật dự phòng đã đăng ký và đáp ứng chính sách | Một đường xác thực hợp lệ khác | Tiếp tục xác thực thông thường, không cần tạo ngoại lệ |
| Người dùng dùng một cơ chế dự phòng được chính sách chấp nhận | Mức bảo đảm phụ thuộc cơ chế và tổ hợp bằng chứng thực tế | Đánh giá đúng cơ chế, không mặc nhiên coi mọi recovery code là cùng một loại |
| Người dùng không hoàn thành được MFA hiện tại nhưng đủ bằng chứng để đăng ký lại | Khôi phục phương thức xác thực | Cấp quyền recovery hẹp, kiểm soát việc gắn phương thức mới |
| Người dùng xin truy cập một chức năng trong lúc khôi phục | Ngoại lệ truy cập tạm thời | Đánh giá riêng chức năng, thời hạn và rủi ro còn lại |
| Nhân viên hỗ trợ tắt MFA trên tài khoản để người dùng tự đăng nhập | Thay đổi lâu dài chính sách bảo vệ tài khoản | Không dùng làm lối xử lý mặc định cho yêu cầu recovery |
| Tổ chức phải vận hành khi hạ tầng xác thực gặp sự cố | Vấn đề liên tục dịch vụ hoặc truy cập khẩn cấp | Dùng quy trình sự cố đã thiết kế trước, tách khỏi recovery cá nhân |

Ví dụ, mật khẩu kết hợp một bí mật dự phòng đã được cấp và kiểm tra đúng cách có thể thuộc cơ chế xác thực được chính sách cho phép. Không thể kết luận có hay không có MFA chỉ bằng việc giao diện hiển thị hai màn hình. Một authenticator đa yếu tố cũng có thể đáp ứng nhiều yếu tố trong một luồng tương tác.

NIST phân loại AAL theo độ mạnh của giao dịch xác thực. AAL2 yêu cầu bằng chứng kiểm soát hai yếu tố phân biệt; AAL3 bổ sung các yêu cầu chặt hơn, gồm cơ chế chống phishing và khóa xác thực không thể xuất. Sự phê duyệt của nhân viên không tự thay thế các yêu cầu kỹ thuật của một mức AAL. [NIST SP 800-63B-4 — Introduction](https://pages.nist.gov/800-63-4/sp800-63b/introduction/)

### 1.2. Ba quyền cần đánh giá riêng

Trong thiết kế ứng dụng, nên tách ba câu hỏi:

1. Người này có đủ điều kiện **đi vào quy trình recovery** không?
2. Quy trình đã đủ căn cứ để **gắn phương thức xác thực thay thế** chưa?
3. Người này có được **thực hiện hành động nghiệp vụ** trước khi khôi phục đầy đủ không?

Một quyết định cho phép bước 1 không tự cho phép bước 2 hoặc 3. Tương tự, quyền đăng ký TOTP mới không tự bao gồm quyền đổi email chính, tạo API key hoặc cấp quyền quản trị.

Một tên quyền như `MFA_BYPASS` quá rộng nếu được hiểu là bỏ mọi kiểm tra MFA trên toàn hệ thống. Thay vào đó, quyết định cần chỉ rõ mục đích, chẳng hạn `REENROLL_AUTHENTICATOR`, và tập hành động được phép trong thời gian có hiệu lực.

## 2. Eligibility là một tập điều kiện bắt buộc

Một mô hình khái niệm có thể viết như sau:

~~~text
Đủ điều kiện cấp ngoại lệ =
    chính sách cho phép đúng trường hợp
  AND không có điều kiện chặn bắt buộc
  AND bằng chứng đạt yêu cầu cho hành động
  AND bối cảnh hiện tại được chấp nhận
  AND hoàn tất các phê duyệt cần thiết
  AND có thể thực thi giới hạn và thu hồi ngoại lệ
~~~

Đây là phép hội các cổng kiểm soát, không phải công thức cộng điểm. Mười tín hiệu thuận lợi không bù được một điều kiện bắt buộc đang thất bại. Chẳng hạn, IP quen thuộc không thể bù cho việc tài khoản đang bị đình chỉ, và người quản lý đồng ý không thể bù cho việc chưa xác minh người nhận token.

### 2.1. Những chiều phải có trong quyết định

| Chiều đánh giá | Dữ liệu cần biết | Câu hỏi phải trả lời |
| --- | --- | --- |
| Chính sách | Tenant, ứng dụng, loại tài khoản, hành động, policy version | Loại ngoại lệ này có được phép trong phạm vi đang xét không? |
| Trạng thái tài khoản | Active, disabled, security hold, sự cố đang mở | Có được phép khôi phục bằng đường này không? |
| Bằng chứng | Kết quả kiểm tra credential còn lại, recovery code, quy trình định danh | Bằng chứng nào đã được server xác minh và đủ cho quyền nào? |
| Bối cảnh | Độ mới của bằng chứng, biến động bảo mật, tín hiệu thiết bị và nguồn yêu cầu | Có dấu hiệu bị lừa đảo, chiếm session hoặc thay đổi gần đây không? |
| Quyền hạn | Vai trò hiện tại, tài nguyên đích, tác động của hành động | Ngoại lệ có mở ra quyền vượt mức chấp nhận không? |
| Phê duyệt | Người duyệt, thẩm quyền, tính độc lập, thời hạn | Đã có đầy đủ phê duyệt đúng quy trình chưa? |
| Thực thi | Scope, audience, TTL, trạng thái grant, session, khả năng thu hồi | Hệ thống có thực sự giữ được các giới hạn đã hứa không? |

Lý do “mất điện thoại”, “đang đi công tác” hoặc “cần làm gấp” giúp chọn quy trình hỗ trợ. Những lời khai này không phải bằng chứng đủ để cấp quyền.

### 2.2. Có yếu tố dự phòng chưa chắc phải dùng ngoại lệ

Trước khi đánh giá bypass, dịch vụ có thể đề nghị những phương thức đã đăng ký khác. Nếu người dùng hoàn thành xác thực đáp ứng chính sách, chuyển về đường đăng nhập thông thường.

Tuy nhiên, chỉ thấy một credential trong cơ sở dữ liệu không chứng minh người dùng còn sử dụng được nó. Không thiết kế vòng lặp buộc người mất cả hai thiết bị liên tục chọn một authenticator đã mất. Lời khai “không dùng được” cho phép xem xét đường recovery; quyền thực hiện recovery vẫn cần bằng chứng riêng.

### 2.3. Thiếu dữ liệu phải tạo kết quả chưa đủ điều kiện

Nếu không lấy được trạng thái security hold, phiên bản tài khoản hoặc kết quả kiểm tra bằng chứng, hệ thống không nên biến sự cố đó thành quyết định cho phép. Có thể trả kết quả cần thử lại hoặc đánh giá bổ sung, đồng thời giữ nguyên các đường xác thực bình thường còn hoạt động.

Không đồng nhất “chưa đủ dữ liệu để cấp ngoại lệ” với “tài khoản chắc chắn bị tấn công”. Hai kết luận này có cách truyền đạt và xử lý khác nhau.

## 3. Chất lượng và tính độc lập của bằng chứng

### 3.1. Bằng chứng nào có thể được xem xét?

| Loại thông tin | Giá trị có thể có | Giới hạn cần hiểu |
| --- | --- | --- |
| Authenticator khác đã đăng ký và được xác minh thành công | Có thể đủ cho xác thực thông thường hoặc quản lý factor, tùy chính sách | Phải xét loại authenticator, độ mới và yêu cầu chống phishing |
| Recovery code đã cấp trước đó | Có thể tham gia một cơ chế phục hồi đã thiết kế | Phải xác minh, giới hạn thử, kiểm soát sử dụng lại và tổ hợp bằng chứng |
| Quy trình tái xác minh danh tính | Có thể phục hồi mối liên kết với danh tính đã được thiết lập | Cần căn cứ định danh cũ đủ tin cậy và quy trình phù hợp |
| Recovery contact đã thiết lập từ trước | Có thể tham gia quy trình khôi phục được chính sách chấp nhận | Không đồng nghĩa với bất kỳ đồng nghiệp nào xác nhận qua tin nhắn |
| Email hoặc số điện thoại đã xác minh từ trước | Chứng minh kiểm soát một kênh trong điều kiện nhất định | Có thể cùng bị mất hoặc bị chiếm đoạt với factor đang mất |
| Session còn hoạt động | Hỗ trợ xác định bối cảnh và điều hướng | Session có thể bị đánh cắp; không đủ để tự thay MFA |
| Thiết bị được quản lý hoặc khóa thiết bị được chứng minh bằng mật mã | Một tín hiệu kiểm soát thiết bị có chất lượng xác định | Không đồng nhất với cookie, fingerprint hoặc tên máy do client gửi |
| Họ tên, ngày sinh, mã nhân viên, tên quản lý | Hỗ trợ tìm hồ sơ | Thường không phải bí mật; không đủ để chứng minh quyền sở hữu |

Đối với thay đổi factor, OWASP khuyến nghị xác thực lại bằng phương thức đã đăng ký, không chỉ dựa vào session hiện tại, và kết hợp kiểm tra rủi ro cùng thông báo cho người dùng. Khi không còn phương thức như vậy, cần một đường recovery riêng đủ căn cứ. [OWASP — Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors)

### 3.2. Đếm nguồn tin cậy, không đếm số màn hình

Giả sử người dùng mất quyền kiểm soát tài khoản email nền tảng, và cùng tài khoản đó lưu cả mật khẩu, passkey lẫn bản chụp recovery code. Ba mục xuất hiện khác nhau trong giao diện nhưng có thể cùng nằm trong một miền bị chiếm đoạt.

Tương tự:

- Mật khẩu vừa được reset bằng email và mã recovery tiếp tục gửi vào email đó không tự tạo thành hai bằng chứng độc lập.
- Hai mã được gửi vào cùng một hộp thư không trở thành hai phương thức recovery khác nhau chỉ vì có hai giá trị.
- Quản lý xác nhận “tôi biết nhân viên này” chưa chứng minh người đang nhận token là nhân viên đó.
- Ảnh chụp authenticator hoặc giấy tờ không tự chứng minh người gửi đang kiểm soát factor đã gắn với tài khoản.

Chính sách cần ghi rõ sự kết hợp nào được chấp nhận, cách chứng minh mỗi thành phần và giả định phụ thuộc giữa chúng. Không dùng bộ đếm `evidenceCount >= 2` thay cho việc đánh giá tổ hợp bằng chứng.

### 3.3. Phân biệt recovery theo NIST với ngoại lệ tùy ý

Với tài khoản có mức xác thực tối đa AAL2, NIST nêu ba đường recovery: hai recovery code từ các phương thức khác nhau; một recovery code kết hợp authenticator đơn yếu tố đã gắn với tài khoản; hoặc tái xác minh danh tính nếu tài khoản đã được định danh. Recovery cũng phải tạo thông báo. [NIST SP 800-63B-4 — Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b/events/#recovery)

Các yêu cầu đó không đồng nghĩa “bất kỳ mật khẩu cộng email nào cũng đủ” và không tự tạo quyền truy cập nghiệp vụ đầy đủ. Nếu áp dụng một tiêu chuẩn, hệ thống phải triển khai đầy đủ các yêu cầu liên quan, không chỉ chép một tổ hợp bằng chứng vào danh sách điều kiện.

Đặc biệt, với tài khoản chưa từng có mối liên kết danh tính được kiểm chứng, không thể tự coi việc gửi giấy tờ mới là tái xác minh một danh tính cũ. Cần có căn cứ nối người yêu cầu với đúng tài khoản; nếu thiếu căn cứ, có thể chưa đủ điều kiện phục hồi.

## 4. Điều kiện chặn và điều kiện cần đánh giá thêm

### 4.1. Các trường hợp không cấp ngoại lệ trực tiếp

Trong một chính sách minh họa, các điều kiện sau chặn việc cấp bypass trực tiếp:

- Tài khoản bị vô hiệu hóa do quyết định quản trị hoặc không còn quyền truy cập tài nguyên.
- Có security hold đang hiệu lực hoặc dấu hiệu chiếm đoạt cần quy trình xử lý sự cố.
- Chính sách của tài nguyên không cho phép loại ngoại lệ đang xin.
- Người yêu cầu chỉ biết mật khẩu hoặc thông tin cá nhân, chưa có đủ bằng chứng theo đường recovery.
- Địa chỉ nhận token là địa chỉ mới do người yêu cầu cung cấp, chưa có căn cứ liên kết đáng tin cậy.
- Người thao tác không có quyền cấp ngoại lệ cho tài khoản hoặc tenant đích.
- Phê duyệt bắt buộc còn thiếu, hết hạn hoặc người yêu cầu tự phê duyệt.
- Token hoặc bằng chứng đã dùng, bị thu hồi hoặc không thuộc đúng yêu cầu.
- Dịch vụ đích không thể thực thi scope và thời hạn của session ngoại lệ.

“Chặn bypass trực tiếp” không nhất thiết là từ chối mọi hỗ trợ. Hệ thống có thể chuyển sang quy trình xác minh khác, bộ phận xử lý sự cố hoặc người có thẩm quyền theo chính sách.

### 4.2. Các dấu hiệu cần tăng mức kiểm tra

Một số dấu hiệu không đủ để kết luận có tấn công, nhưng cần được đưa vào quyết định:

| Dấu hiệu | Cách xử lý có thể áp dụng |
| --- | --- |
| Nguồn truy cập hoặc thiết bị mới | Yêu cầu thêm bằng chứng phù hợp, không chỉ tăng số câu hỏi cá nhân |
| Vừa thay kênh recovery hoặc reset mật khẩu | Đánh giá nguồn gốc thay đổi, không coi kênh mới là bằng chứng đã ổn định |
| Nhiều yêu cầu bypass trong thời gian ngắn | Hạn mức và đánh giá nguyên nhân, ngăn cấp nối tiếp thành ngoại lệ vĩnh viễn |
| Vừa được nâng quyền quản trị | Áp dụng chính sách theo quyền hiện tại, không dùng phân loại tài khoản cũ |
| Có nhiều lần từ chối push hoặc thử MFA bất thường | Xem xét khả năng mật khẩu đã bị lộ hoặc MFA fatigue |
| Kênh liên hệ và factor cùng nằm trên thiết bị mất | Tìm tổ hợp bằng chứng không dựa hoàn toàn vào thiết bị đó |
| Người yêu cầu gây áp lực thời gian hoặc muốn đổi kênh liên hệ | Giữ nguyên quy trình kiểm tra, xác minh qua nguồn đã thiết lập |

Không công bố chi tiết ngưỡng phát hiện và mọi mã lý do nội bộ trên màn hình công khai. Người dùng vẫn cần biết bước tiếp theo có thể thực hiện, nhưng không cần nhận một bản đồ giúp né kiểm soát.

## 5. Phân biệt các kết quả quyết định

Một trường boolean `eligible=true` không đủ diễn đạt quyền thực tế. Nên trả về một tập kết quả có nghĩa rõ ràng:

| Kết quả minh họa | Ý nghĩa | Quyền được cấp |
| --- | --- | --- |
| `ROUTE_NORMAL_AUTH` | Đã có đường xác thực thông thường đáp ứng yêu cầu | Theo chính sách đăng nhập thông thường |
| `REQUIRE_MORE_EVIDENCE` | Có thể tiếp tục quy trình nhưng chưa đủ bằng chứng | Chỉ nộp hoặc xác minh bằng chứng theo quyền hẹp |
| `REQUIRE_APPROVAL` | Bằng chứng và chính sách cho phép xem xét, còn thiếu phê duyệt | Chưa phát grant sử dụng được |
| `ALLOW_RECOVERY_ONLY` | Đủ điều kiện cho các bước khôi phục được chỉ định | Chỉ các endpoint recovery được phép |
| `ALLOW_RESTRICTED_ACCESS` | Có ngoại lệ nghiệp vụ riêng được phê duyệt | Chỉ tài nguyên và hành động cụ thể trong thời hạn |
| `DENY_EXCEPTION` | Không cấp ngoại lệ này | Không phát grant; có thể chỉ dẫn đường hỗ trợ khác |

Ví dụ, người dùng đủ điều kiện đăng ký lại TOTP có thể nhận `ALLOW_RECOVERY_ONLY`. Nếu cũng xin xuất toàn bộ dữ liệu, yêu cầu thứ hai phải có quyết định riêng; không suy ra từ quyết định thứ nhất.

Trạng thái `REQUIRE_APPROVAL` không phải “đã được cấp quyền nhưng tạm ẩn nút”. Token chỉ được phát sau khi các điều kiện phát hành đã hoàn tất và được kiểm tra lại.

## 6. Mẫu chính sách đủ cụ thể để thực thi

### 6.1. Tách chính sách theo loại tài khoản và hành động

Một dịch vụ có thể bắt đầu bằng ma trận minh họa dưới đây. Mọi tổ hợp vẫn phải qua các điều kiện chặn ở phần trước.

| Tài khoản và yêu cầu | Bằng chứng tối thiểu trong ví dụ | Quyết định dự kiến |
| --- | --- | --- |
| Người dùng thường mất TOTP, đã xác thực bằng phương thức khác đủ mạnh cho hành động | Sự kiện xác thực mới, hợp lệ, đáp ứng chính sách quản lý factor | Dùng đường quản lý factor thông thường |
| Người dùng thường không còn MFA, có recovery code và credential còn lại phù hợp | Tổ hợp bằng chứng được đường recovery chấp nhận | Cho recovery với quyền đăng ký lại, chưa cấp mọi quyền nghiệp vụ |
| Người dùng chỉ có mật khẩu và thiết bị có cookie cũ | Chưa đạt yêu cầu phục hồi | Yêu cầu thêm bằng chứng |
| Người dùng có bằng chứng recovery hợp lệ, muốn đổi cả email lẫn MFA | Chưa có quyền thay email trong quyết định hiện tại | Giữ recovery hẹp; đánh giá đổi email riêng |
| Tài khoản quản trị mất mọi authenticator | Quy trình phục hồi tài khoản đặc quyền, bằng chứng phù hợp và phê duyệt độc lập bắt buộc | Chuyển đường đặc quyền, không tự cấp bypass từ helpdesk thông thường |
| Tài khoản đang bị security hold | Dù có mã recovery, cần giải quyết hold theo quy trình sự cố | Không cấp bypass trực tiếp |
| Người dùng xin tạm truy cập một chức năng đã được phép ngoại lệ | Bằng chứng đạt yêu cầu, tài nguyên chấp nhận ngoại lệ, có phê duyệt cần thiết | Cấp quyền đúng chức năng, không mở session đầy đủ |
| Tài khoản dịch vụ hoặc tác vụ tự động | Không thuộc đường recovery cho người dùng cá nhân | Chuyển quy trình quản lý credential của workload |

Không phân loại chỉ bằng tên đăng nhập. Phải lấy vai trò, tenant, trạng thái và quyền hiện tại từ nguồn có thẩm quyền. Một tài khoản vừa được nâng quyền không được tiếp tục hưởng ngoại lệ dành cho người dùng thường chỉ vì kết quả đánh giá trước đó còn trong cache.

### 6.2. Ví dụ cấu hình nội bộ

~~~yaml
policyId: mfa-recovery-standard-user
version: 7
appliesTo:
  accountClass: STANDARD_HUMAN
  purpose: REENROLL_AUTHENTICATOR

hardStops:
  - ACCOUNT_DISABLED
  - SECURITY_HOLD
  - RESOURCE_DISALLOWS_EXCEPTION

requiredEvidenceProfile: STANDARD_ACCOUNT_RECOVERY_V3
approvalProfile: AS_REQUIRED_BY_VERIFIED_CASE

grant:
  audience: recovery-service
  exchangeTtlSeconds: 300
  maxExchanges: 1

recoverySession:
  absoluteTtlSeconds: 900
  renewable: false
  allowedActions:
    - recovery:read-own-status
    - recovery:enroll-replacement-factor
    - recovery:confirm-replacement-factor

completion:
  requireReplacementProof: true
  revokeRecoverySession: true
  requireFreshLoginForBusinessAccess: true
~~~

`STANDARD_ACCOUNT_RECOVERY_V3` phải là một chính sách có định nghĩa về tổ hợp bằng chứng, độ mới, nguồn kiểm tra và điều kiện không chấp nhận. Nó không phải chuỗi tùy ý mà client có thể đưa vào request để tự chọn mức kiểm tra dễ hơn.

Các giá trị 300 và 900 giây ở đây lần lượt là cửa sổ đổi grant và thời hạn tuyệt đối của recovery session sau khi đổi thành công. Hết cửa sổ đổi grant thì không thể tạo session mới từ grant đó; session đã được tạo có thời hạn riêng theo quyết định. Nếu nghiệp vụ yêu cầu mọi truy cập dừng tại một mốc chung, cả hai phải bị chặn bởi `exceptionEndsAt` do server xác định.

Nếu có thời gian chờ dài hơn TTL, lưu trạng thái chờ ở server và chỉ phát grant sau khi thời gian chờ đã đủ, bằng chứng vẫn còn giá trị và điều kiện hiện tại được kiểm tra lại. Không tự gia hạn token ngắn hạn suốt thời gian chờ.

### 6.3. Nội dung quyết định

Một quyết định cấp quyền cần chứa hoặc tham chiếu tới:

- Account ID và tenant ID đã xác định ở server.
- Recovery request ID, mục đích, audience và các action được phép.
- Loại kết quả, mã lý do nội bộ, policy version và phiên bản bảo mật tài khoản.
- Các bằng chứng đã xác minh, thời điểm kiểm tra, nguồn kiểm tra và hạn sử dụng.
- Phê duyệt liên quan, người duyệt, vai trò tại thời điểm duyệt và thời điểm hết hạn.
- Cửa sổ phát hành, TTL, số lần đổi grant và giới hạn session.
- Điều kiện thu hồi, yêu cầu sau recovery và đường xử lý khi một điều kiện không còn đúng.

Không trả toàn bộ dữ liệu này cho người chưa được xác thực. Bản ghi quyết định dùng để thực thi và kiểm toán; thông báo cho người dùng chỉ cần nêu trạng thái cùng bước tiếp theo phù hợp.

## 7. Phê duyệt thủ công và đường truy cập khẩn cấp

### 7.1. Phê duyệt không thay thế bằng chứng

Trong một tổ chức, người quản lý có thể xác nhận nhu cầu nghiệp vụ hoặc quan hệ lao động. Bộ phận hỗ trợ có thể xác minh bằng chứng theo quy trình. Người chịu trách nhiệm an ninh có thể quyết định phạm vi ngoại lệ được phép. Những vai trò này trả lời các câu hỏi khác nhau.

Một quy trình tốt cần chỉ rõ:

1. Ai kiểm tra người yêu cầu và bằng chứng?
2. Ai có thẩm quyền cho loại tài khoản và phạm vi này?
3. Khi nào phải có người thứ hai độc lập?
4. Ai nhận thông báo và có thể thu hồi ngoại lệ?
5. Bằng chứng, scope hoặc quyền thay đổi thì phải duyệt lại thế nào?

Với đường yêu cầu hai người, không chấp nhận cùng một người dùng hai vai trò để tự phê duyệt. Approval phải gắn với request, account, purpose, scope và nội dung bằng chứng đã xét. Nếu scope chuyển từ đăng ký lại factor sang tạo API key, approval cũ không còn bao phủ yêu cầu mới.

Nhân viên hỗ trợ nên dùng console có luồng cấp grant được kiểm soát, thay vì sửa trực tiếp trường `mfaEnabled=false` trong cơ sở dữ liệu. Mọi quyền hỗ trợ cũng cần được bảo vệ tương xứng với khả năng ảnh hưởng nhiều tài khoản.

### 7.2. Tài khoản đặc quyền

Tài khoản quản trị có thể thay đổi chính sách, cấp quyền cho người khác hoặc tạo credential dài hạn. Vì vậy, một ngoại lệ nhỏ tại cổng MFA có thể trở thành khả năng kiểm soát cả hệ thống.

Đường phục hồi đặc quyền cần được thiết kế riêng theo rủi ro. Ví dụ, yêu cầu bằng chứng độc lập mạnh hơn, người duyệt có thẩm quyền riêng và môi trường truy cập phù hợp. Nếu các điều kiện chưa đạt, không cấp session quản trị chỉ vì người yêu cầu nói đang có sự cố.

Việc tạm bỏ vai trò quản trị cũng chưa đủ nếu session, token hoặc grant cũ còn mang quyền đó. Phải đồng bộ kiểm soát quyền thực tế ở các tài nguyên liên quan.

### 7.3. Sự cố hạ tầng MFA khác với mất factor cá nhân

Nếu nhà cung cấp MFA ngừng hoạt động, nhiều người dùng hợp lệ có thể cùng không đăng nhập được. Tự động tắt MFA cho toàn bộ tenant tạo ra một thay đổi bảo mật rộng hơn rất nhiều so với một yêu cầu recovery.

Tổ chức nên chuẩn bị trước phương thức dự phòng đáp ứng chính sách hoặc đường truy cập khẩn cấp được quản lý riêng, có người sở hữu, phạm vi, thời hạn và giám sát. Một tài khoản khẩn cấp, nếu được sử dụng, phải theo thiết kế đó; nó không chứng minh nhân viên bất kỳ đủ điều kiện bypass trên tài khoản cá nhân.

Mức khẩn cấp có thể thay đổi ưu tiên xử lý và người có thẩm quyền. Nó không biến bằng chứng chưa xác minh thành bằng chứng hợp lệ.

## 8. Luồng quyết định tại backend

### 8.1. Sơ đồ xử lý

~~~mermaid
flowchart TD
    A[Nhận yêu cầu recovery hoặc ngoại lệ] --> B[Xác định account, tenant và purpose]
    B --> C{Đã hoàn thành xác thực thường phù hợp?}
    C -->|Có| D[Đi theo đường thông thường]
    C -->|Chưa| E[Nạp chính sách và trạng thái có thẩm quyền]
    E --> F{Có điều kiện chặn?}
    F -->|Có| G[Không cấp ngoại lệ trực tiếp]
    F -->|Không| H[Kiểm tra bằng chứng và bối cảnh]
    H --> I{Đủ bằng chứng cho hành động?}
    I -->|Chưa| J[Yêu cầu thêm bằng chứng hoặc hướng hỗ trợ]
    I -->|Đủ| K{Phê duyệt và điều kiện chờ đã đạt?}
    K -->|Chưa| L[Giữ trạng thái chờ, chưa phát grant]
    K -->|Đạt| M[Kiểm tra lại trạng thái hiện tại]
    M --> N{Có thể thực thi giới hạn?}
    N -->|Không| G
    N -->|Có| O[Phát grant hẹp và ghi audit]
    O --> P[Đổi grant một lần sang session giới hạn]
    P --> Q[Đăng ký và xác nhận factor thay thế]
    Q --> R[Đánh giá hoàn tất recovery]
    R --> S[Thu hồi ngoại lệ, yêu cầu đăng nhập mới]
~~~

Đường truy cập nghiệp vụ tạm thời cần một quyết định riêng với scope tài nguyên riêng. Không thêm quyền nghiệp vụ vào session recovery chỉ vì người dùng đã qua một phần sơ đồ.

### 8.2. Mã giả kiểm tra và cấp grant

Đoạn Java dưới đây minh họa cấu trúc điều phối, không phải mã hoàn chỉnh để triển khai mật mã, kiểm tra WebAuthn hoặc tích hợp nhà cung cấp danh tính.

~~~java
Decision issueRecoveryGrant(VerifiedRecoveryContext context) {
    return transaction.execute(() -> {
        Instant now = clock.instant();
        Account account = accounts.lock(context.accountId());
        RecoveryRequest request = requests.lock(context.requestId());

        requireSameTenantAccountAndPurpose(context, account, request);
        requireRequestAcceptsNewDecision(request, now);

        Policy policy = policies.currentFor(account, request.purpose());
        TrustedSnapshot snapshot =
            facts.currentValidatedSnapshot(account, request, now);

        if (!snapshot.requiredFactsAvailable()) {
            return decisions.needMoreEvidence("REQUIRED_FACTS_UNAVAILABLE");
        }
        if (policy.hasHardStop(account, snapshot)) {
            return decisions.denyException("HARD_STOP");
        }
        if (!evidence.satisfies(policy.evidenceProfile(), snapshot, now)) {
            return decisions.needMoreEvidence("EVIDENCE_NOT_SUFFICIENT");
        }
        if (!approvals.satisfy(policy, request, snapshot, now)) {
            return decisions.requireApproval("APPROVAL_INCOMPLETE");
        }
        if (!policy.waitingConditionsSatisfied(request, snapshot, now)) {
            return decisions.waitForConditions("WAITING_CONDITIONS");
        }

        AllowedScope scope = policy.scopeFor(request, snapshot);
        requireScopeEnforceableByTarget(scope);
        requireSnapshotVersionsStillCurrent(snapshot, account, request);

        Grant grant = grants.issueOpaqueOneUseGrant(
            account.id(), account.securityVersion(), request.id(),
            policy.version(), scope, policy.grantDeadline(now)
        );
        request.recordGranted(grant.id(), scope, now);
        outbox.appendExceptionGranted(account, request, grant);
        return decisions.allowRecoveryOnly(grant);
    });
}
~~~

`VerifiedRecoveryContext` là context mà backend đã xác minh, không phải DTO ánh xạ trực tiếp từ JSON của client. Các thuộc tính như vai trò, kết quả bằng chứng, security hold, trạng thái phê duyệt và scope phải xuất phát từ server hoặc nguồn tin cậy được xác thực.

Mẫu mã trả `allowRecoveryOnly` nên chỉ dùng cho purpose recovery tương ứng. Một endpoint cấp ngoại lệ nghiệp vụ phải có chính sách và kết quả riêng; không tái sử dụng hàm rồi âm thầm mở rộng scope.

`requireSnapshotVersionsStillCurrent` thể hiện yêu cầu chống quyết định dựa vào trạng thái cũ. Trong hệ thống nhiều dịch vụ, một giao dịch cơ sở dữ liệu cục bộ không khóa được mọi nguồn bên ngoài. Cần bản ghi phiên bản, hiệu lực bằng chứng và cơ chế vô hiệu hóa quyết định khi dữ kiện quan trọng thay đổi; không chỉ gọi một API rủi ro rồi coi kết quả hợp lệ vô thời hạn.

Việc phát grant phải ngăn hai request đồng thời tạo nhiều ngoại lệ ngoài hạn mức. Có thể ràng buộc duy nhất theo account, purpose và trạng thái còn hiệu lực, đồng thời quản lý trạng thái request trong giao dịch. Retry sau khi đã cấp phải trả trạng thái hiện tại theo context hợp lệ hoặc dùng quy trình cấp lại có thu hồi rõ ràng, không sinh thêm token không kiểm soát.

### 8.3. Kiểm tra lại khi đổi grant

Quyết định tại thời điểm duyệt chưa đủ cho thời điểm sử dụng. Ví dụ, sau khi được duyệt, tài khoản có thể bị đặt security hold hoặc người duyệt có thể thu hồi approval.

Khi đổi grant thành session, backend phải kiểm tra:

- Grant đúng account, tenant, purpose, audience và recovery request.
- Grant chưa hết hạn, chưa bị thu hồi và chưa được tiêu thụ.
- Quyết định, bằng chứng và approval còn hiệu lực theo chính sách.
- Phiên bản bảo mật và chính sách vẫn tương thích; thay đổi không tương thích buộc đánh giá lại.
- Không xuất hiện điều kiện chặn mới.
- Context nhận session thuộc đúng luồng đã được bảo vệ.

Tiêu thụ grant và tạo session giới hạn cần là một thao tác nguyên tử trong phạm vi hệ thống quản lý chúng. Nếu thành phần phát token nằm ngoài giao dịch, phải có giao thức phát hành bảo đảm một lần sử dụng và khả năng xử lý lỗi, thay vì giả định hai thao tác rời rạc không thể bị lặp.

## 9. Token và session phải giữ nguyên ý nghĩa ngoại lệ

### 9.1. Token dùng một lần không tự là session an toàn

Ví dụ, grant opaque có thể được tạo bằng 32 byte ngẫu nhiên mật mã, lưu digest hoặc HMAC ở server và chỉ đổi một lần qua kết nối được bảo vệ. Không đưa token vào log, analytics hoặc tài nguyên bên thứ ba.

Nếu token được gửi qua email, phải xét chất lượng kênh đó trong chính sách bằng chứng. Một token mạnh về entropy vẫn không bảo vệ được khỏi người đang kiểm soát hộp thư nhận token. Cũng không gửi grant tới số điện thoại mới chỉ vì người yêu cầu nói đã mất số cũ.

Với cookie, cần các thuộc tính bảo vệ thích hợp và chống CSRF. Với liên kết, cần kiểm soát referrer và tránh việc tải tài nguyên ngoài làm rò token. Những biện pháp vận chuyển này bổ sung cho eligibility; chúng không sửa được một quyết định cấp sai người.

### 9.2. Không biến “đã duyệt” thành “đã hoàn tất MFA”

Không dùng logic:

~~~text
if bypassApproved:
    session.mfaCompleted = true
    issueNormalRefreshToken()
~~~

Logic này xóa mất khác biệt giữa một ngoại lệ đã được phê duyệt và một sự kiện xác thực đáp ứng yêu cầu thông thường. Downstream có thể tin nhầm rằng session đủ quyền cho mọi hành động cần MFA.

RFC 8176 định nghĩa `amr` để mô tả các phương thức đã được sử dụng; giá trị `mfa` biểu thị xác thực đa yếu tố. `acr` mô tả lớp ngữ cảnh được đáp ứng, không phải danh sách phương thức. Không tự gắn các claim này chỉ vì helpdesk đã duyệt bypass. [RFC 8176 — Authentication Method Reference Values](https://www.rfc-editor.org/rfc/rfc8176.html)

Nếu hệ thống dùng federation, RP phải xác minh token/assertion từ issuer tin cậy và diễn giải assurance theo hợp đồng với IdP. Không đọc một claim do client tự gửi hoặc suy ra mức chống phishing chỉ từ một cờ chung chung.

### 9.3. Biểu diễn quyền giới hạn rõ ràng

Trong trạng thái session nội bộ, có thể lưu:

~~~json
{
  "sessionClass": "RECOVERY_ONLY",
  "purpose": "REENROLL_AUTHENTICATOR",
  "allowedActions": [
    "recovery:read-own-status",
    "recovery:enroll-replacement-factor",
    "recovery:confirm-replacement-factor"
  ],
  "exceptionId": "server-generated-reference",
  "accountSecurityVersion": 42,
  "renewable": false
}
~~~

Đây là mô hình dữ liệu nội bộ, không phải tập claim chuẩn bắt buộc của OAuth hoặc OpenID Connect. Trong hệ thống thật cần thêm định danh tài khoản, tenant, thời điểm phát hành, thời điểm hết hạn và cơ chế kiểm tra tính toàn vẹn phù hợp.

Resource server phải kiểm tra các giới hạn cần thiết trên từng request. Ẩn nút không chặn việc gọi API trực tiếp. Một gateway cho phép recovery cũng không đủ nếu API phía sau chỉ nhìn vai trò tài khoản rồi cho xuất dữ liệu.

Không phát refresh token thông thường, không cho session recovery tạo API key hoặc đổi sang token có scope rộng hơn. Nếu một thành phần không hiểu loại session giới hạn, không chuyển session ngoại lệ tới thành phần đó.

### 9.4. Thu hồi và kết thúc thời hạn

Ngoại lệ phải có đường thu hồi khi:

- Người dùng đã hoàn tất recovery.
- Request bị hủy, bằng chứng bị phủ nhận hoặc approval bị thu hồi.
- Tài khoản chuyển trạng thái bảo mật hoặc thay đổi quyền làm quyết định cũ không còn phù hợp.
- Grant, session hoặc cửa sổ ngoại lệ hết thời hạn.

Token hết hạn không tự bảo đảm mọi session phát sinh trước đó đã bị chấm dứt. Nếu dùng JWT chỉ kiểm tra chữ ký và `exp`, việc thu hồi tức thời cần thêm trạng thái thu hồi, introspection hoặc cơ chế phiên bản được API thực sự kiểm tra. Cần xác định độ trễ thu hồi chấp nhận được và cách xử lý khi nguồn trạng thái không khả dụng.

Giới hạn quan trọng cần áp dụng cho cả account hoặc luồng cấp session liên quan. Nếu chỉ gắn giới hạn vào session recovery, người dùng có thể đăng nhập lại bằng factor mới và vô tình nhận session vượt quá các điều kiện còn hiệu lực.

## 10. Chống lạm dụng quy trình eligibility

### 10.1. Không để yêu cầu chưa xác minh thay đổi tài khoản

Một endpoint bắt đầu recovery công khai không nên tiết lộ tài khoản có tồn tại, đang có bao nhiêu factor hay có được bypass hay không. Có thể trả thông điệp trung tính và chỉ mở thêm thông tin sau khi đạt điều kiện xác minh phù hợp.

Không vô hiệu hóa factor, thu hồi mọi session hoặc bật security hold tự động chỉ vì có người nhập đúng email. Những thay đổi có tác động cần căn cứ bảo mật tương ứng; nếu không, kẻ tấn công có thể dùng luồng recovery để gây từ chối dịch vụ.

Giới hạn yêu cầu theo nhiều chiều như account, tenant, nguồn truy cập và tổng mức sử dụng. Kiểm soát cả việc gửi thông báo, cấp token và số ngoại lệ đang hoạt động, thay vì chỉ đếm số lần nhập mã sai.

### 10.2. Không cho gia hạn nối tiếp thành truy cập lâu dài

Một ngoại lệ 15 phút được cấp lại liên tục vẫn có thể trở thành một cơ chế đăng nhập thường trực. Vì vậy, eligibility phải xem xét lịch sử ngoại lệ còn hiệu lực và gần đây:

- Yêu cầu cấp lại có nguyên nhân gì, bằng chứng nào vẫn còn giá trị?
- Ngoại lệ cũ đã bị thu hồi hay còn sử dụng được?
- Người dùng có thực sự tiến tới khôi phục factor không?
- Có cần nâng cấp hỗ trợ hoặc điều tra thay vì tiếp tục cấp cùng loại quyền?

Không tự gia hạn chỉ vì session tạm thời có hoạt động. Chính hoạt động đó có thể do người đã chiếm grant thực hiện. Hạn mức cần kèm đường hỗ trợ phù hợp để người gặp lỗi kỹ thuật thực tế không bị bỏ rơi.

### 10.3. Bảo vệ kênh helpdesk

Nhân viên hỗ trợ cần xác minh account qua nguồn chính thức, tránh chọn hồ sơ chỉ dựa vào tên hiển thị trùng nhau. Các yêu cầu đổi người nhận token, bỏ bước xác minh, chuyển sang kênh liên hệ mới hoặc nhờ một người khác nhận hộ phải được đánh giá theo chính sách.

Không yêu cầu người dùng đọc mật khẩu, seed TOTP, private key hoặc mã dự phòng cho nhân viên như một thủ tục hỗ trợ mặc định. Nếu cần xác minh code, để người dùng nhập qua giao diện bảo mật do dịch vụ kiểm soát và chỉ đưa kết quả xác minh cần thiết cho người xử lý.

Một cuộc gọi từ người tự xưng lãnh đạo không tạo quyền vượt quy trình. Sự quen thuộc trong giọng nói, thông tin tổ chức hoặc nội dung trao đổi trước đó có thể bị giả mạo hoặc thu thập.

### 10.4. Thông báo và audit

Thông báo nên được gửi ở các mốc phù hợp: ngoại lệ được cấp, phương thức xác thực được thay đổi và recovery hoàn tất. Dùng các kênh đã được thiết lập trước yêu cầu khi có thể, thay vì chỉ thông báo tới địa chỉ vừa nhập trong luồng recovery.

Một liên kết báo cáo “không phải tôi” cần có quyền hẹp. Không để chỉ cần đọc email là có thể quản trị toàn bộ tài khoản, đổi người nhận token hoặc xóa mọi factor.

Audit cần đủ để giải thích:

| Nhóm dữ liệu | Nội dung cần ghi |
| --- | --- |
| Đối tượng | Account, tenant, ứng dụng và tài nguyên đích |
| Quyết định | Kết quả, purpose, scope, lý do nội bộ và policy version |
| Bằng chứng | Tham chiếu bằng chứng đã xác minh, nguồn, thời điểm và hạn hiệu lực |
| Phê duyệt | Người duyệt, thẩm quyền, phạm vi và thời điểm |
| Vòng đời | Phát grant, đổi grant, tạo session, hoàn tất, hết hạn và thu hồi |
| Tác động | Factor được thêm hoặc thu hồi, phiên bản bảo mật, session bị ảnh hưởng |

Không ghi raw token, recovery code, seed TOTP hoặc toàn bộ giấy tờ vào log vận hành. Nếu cần lưu hồ sơ xác minh, dùng kho và chính sách truy cập phù hợp, với thời gian lưu được xác định.

## 11. Ví dụ sản phẩm: Temporary Access Pass

Microsoft Entra ID cung cấp Temporary Access Pass, một passcode có thời hạn, có thể cấu hình dùng một lần hoặc nhiều lần để hỗ trợ thiết lập phương thức xác thực và recovery. Chính sách quy định đối tượng được dùng; việc phát TAP không tự thực hiện xác minh danh tính người nhận. [Microsoft Learn — Configure Temporary Access Pass](https://learn.microsoft.com/en-us/entra/identity/authentication/howto-authentication-temporary-access-pass)

Bài học thiết kế là phải phân biệt khả năng của sản phẩm với chính sách đủ điều kiện của tổ chức. Có API tạo passcode không có nghĩa bất kỳ người liên hệ helpdesk nào cũng được nhận passcode.

TAP cũng không nên được giả định tự có đúng scope `RECOVERY_ONLY` trong mẫu ứng dụng ở bài này. Quyền truy cập thực tế phụ thuộc các chính sách và thành phần tích hợp. Tài liệu Microsoft lưu ý hết hạn TAP không tự thu hồi hồi tố mọi session đã thiết lập; thời lượng truy cập còn cần các kiểm soát session phù hợp. [Microsoft Learn — TAP expiration](https://learn.microsoft.com/en-us/entra/identity/authentication/howto-authentication-temporary-access-pass#expiration)

Do đó, khi tích hợp một cơ chế có sẵn, phải xác minh đầy đủ các điểm: ai được cấp, ai được dùng, thời hạn, số lần sử dụng, quyền sau khi đăng nhập, hành vi thu hồi và cách đăng ký factor thay thế. Không suy luận rằng mọi mã tạm đều tương đương một grant hẹp do ứng dụng tự thiết kế.

## 12. Hoàn tất recovery và quay về xác thực thông thường

Một ngoại lệ cần có tiêu chí hoàn tất rõ ràng:

1. Factor mới được gắn vào đúng account qua recovery context đã được cấp quyền.
2. Người dùng chứng minh có thể sử dụng factor mới bằng ceremony phù hợp.
3. Các điều kiện chờ, phê duyệt hoặc security review còn lại được giải quyết.
4. Factor bị mất hoặc bị nghi lộ được thu hồi theo phạm vi sự cố.
5. Recovery grant và session tạm thời bị tiêu thụ hoặc thu hồi.
6. Người dùng đăng nhập mới bằng cơ chế đáp ứng yêu cầu cho truy cập nghiệp vụ.

Việc chứng minh sử dụng được factor mới chỉ chứng minh quyền kiểm soát factor đó. Nếu kẻ tấn công đã được cấp nhầm quyền enrollment, họ cũng có thể thêm TOTP hoặc passkey hợp lệ. Vì vậy, không dùng factor vừa tạo để thay thế hồi tố bằng chứng đã thiếu ở cổng eligibility.

Khi cấp session thông thường sau recovery, phải xét các hạn chế cấp account còn hiệu lực. Không tự bỏ thời gian chờ chỉ vì factor mới đã hoạt động.

Đối với TOTP, không cần và không nên đưa seed cũ cho người dùng hoặc helpdesk để “phục hồi”. Có thể đăng ký một seed mới qua đường đã được cấp quyền rồi thu hồi seed cũ theo chính sách. Với passkey, RP đăng ký public key mới; RP không khôi phục private key cũ từ bản ghi public key.

Việc hoàn tất cần được ghi nhận nhất quán với thay đổi factor và trạng thái bảo mật. Nếu gửi thông báo lỗi sau khi giao dịch đã commit, hệ thống phải retry thông báo qua cơ chế bền vững; không để giao diện hiểu rằng factor chưa đổi rồi cấp thêm một ngoại lệ ngoài dự kiến.

## 13. Các tình huống áp dụng tiêu chí

### 13.1. Mất điện thoại nhưng có phương án recovery đã chuẩn bị

Lan biết mật khẩu và có recovery code đã cấp trước đó, lưu tách khỏi điện thoại. Dịch vụ xác minh cả hai theo một đường recovery được chính sách chấp nhận, kiểm tra tài khoản không bị hold và đối tượng không thuộc nhóm đặc quyền.

Kết quả có thể là `ALLOW_RECOVERY_ONLY`: Lan được đăng ký và xác nhận factor mới trong session ngắn hạn. Lan chưa được đổi email hoặc tạo API key bằng session đó. Sau khi hoàn tất các điều kiện, ngoại lệ kết thúc và Lan đăng nhập mới.

Điểm quyết định nằm ở tổ hợp bằng chứng và quyền được cấp, không phải lời khai “điện thoại bị mất”.

### 13.2. Biết mật khẩu, có cookie cũ nhưng không có bằng chứng phù hợp

Minh nhập đúng mật khẩu, dùng một trình duyệt có cookie cũ và gửi đúng mã nhân viên. Minh yêu cầu bỏ MFA để đăng nhập ngay.

Các dữ kiện này chưa đủ cho chính sách recovery của dịch vụ. Kết quả là `REQUIRE_MORE_EVIDENCE`, không phải tự cộng điểm thiết bị quen thuộc rồi cho phép. Nếu còn session sử dụng được, session đó có thể xem hướng dẫn hoặc trạng thái phù hợp, nhưng không tự được quyền thay MFA.

Nếu có dấu hiệu session bị chiếm đoạt, việc xử lý phải chuyển sang quy trình bảo mật tương ứng. Không dùng bypass để giải quyết một nghi vấn xâm nhập chưa được đánh giá.

### 13.3. Tài khoản quản trị xin ngoại lệ do công việc khẩn cấp

Hà là quản trị viên, mất khóa bảo mật và cần thay đổi cấu hình gấp. Quản lý của Hà xác nhận nhu cầu công việc qua một kênh nội bộ.

Xác nhận này chứng minh có nhu cầu nghiệp vụ trong phạm vi người quản lý biết; nó chưa chứng minh người đang nhận token là Hà và chưa đáp ứng chính sách phục hồi đặc quyền. Helpdesk thông thường không được phát session quản trị chỉ từ xác nhận đó.

Yêu cầu được chuyển sang đường phục hồi đặc quyền hoặc đường xử lý sự cố đã thiết kế trước. Nếu tổ chức có cơ chế truy cập khẩn cấp riêng, việc sử dụng cơ chế đó tuân theo chính sách riêng, không làm tài khoản của Hà tự đủ điều kiện bypass.

### 13.4. Đã được duyệt nhưng tài khoản xuất hiện security hold

Một request đã được phê duyệt và còn trong TTL. Trước khi người dùng đổi grant, hệ thống phát hiện sự cố và đặt security hold.

Kiểm tra tại thời điểm sử dụng phải từ chối đổi grant theo điều kiện mới. Nếu hệ thống chỉ kiểm tra chữ ký và hạn token mà không xét trạng thái hiện tại, approval cũ sẽ vượt qua một quyết định bảo mật mới.

Tình huống này cho thấy eligibility là quyết định có hiệu lực trong điều kiện xác định, không phải một giấy phép không thể thu hồi.

## 14. Những bất biến cần giữ

- Không có ngoại lệ được cấp chỉ từ lý do khẩn cấp, thông tin cá nhân hoặc mật khẩu đúng.
- Quyền recovery và quyền nghiệp vụ được đánh giá riêng; scope không tự mở rộng.
- Điều kiện chặn bắt buộc có ưu tiên hơn tín hiệu rủi ro thuận lợi.
- Bằng chứng và approval phải thuộc đúng account, tenant, request và mục đích.
- Quyết định được kiểm tra lại khi phát grant, đổi grant và thực hiện hành động có tác động.
- Token dùng một lần không tự cấp refresh token hoặc session đầy đủ.
- Trạng thái ngoại lệ không được ghi giả thành sự kiện MFA đã hoàn tất.
- Factor mới không tự chứng minh người đã xin recovery là chủ tài khoản trước đó.
- Mọi ngoại lệ đều có thời hạn, điều kiện kết thúc, đường thu hồi và audit.
- Khi không thể thực thi giới hạn hoặc chưa có đủ bằng chứng, hệ thống chưa cấp ngoại lệ đó.

MFA bypass eligibility an toàn là quyết định về một quyền cụ thể trong một khoảng thời gian cụ thể, dựa trên bằng chứng đã xác minh và các điều kiện có thể kiểm tra lại. Thiết kế tốt giữ được sự liên tục của quá trình phục hồi mà không biến ngoại lệ thành một đường chiếm đoạt tài khoản.
