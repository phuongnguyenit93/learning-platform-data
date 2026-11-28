# Recovery flow test — Kiểm thử luồng khôi phục tài khoản

## 1. Khôi phục truy cập cũng là một đường thiết lập lại quyền kiểm soát tài khoản

**Recovery flow test** kiểm tra người dùng hợp lệ có thể lấy lại khả năng truy cập khi mất phương tiện xác thực, đồng thời người không đủ bằng chứng không thể dùng luồng khôi phục để kiểm soát tài khoản của người khác.

Một hệ thống có đăng nhập nhiều yếu tố tốt vẫn có thể bị suy yếu nếu chức năng “quên mật khẩu” cho phép đổi luôn email và tắt MFA chỉ bằng một thông tin dễ biết. Vì vậy, kiểm thử recovery không chỉ xem email có được gửi hay mật khẩu có đổi thành công không. Nó phải kiểm tra ai được khôi phục, bằng chứng nào được chấp nhận và trạng thái tài khoản sau khi hoàn tất.

Trong bài này, recovery là khôi phục khả năng kiểm soát tài khoản hoặc phương tiện xác thực, không phải khôi phục database hay phục hồi hạ tầng sau thảm họa. Các tình huống, trạng thái và schema được nêu là ví dụ để thiết kế kiểm thử, không phải contract bắt buộc của mọi sản phẩm IAM.

## 2. Phân biệt các luồng trước khi đặt kỳ vọng

| Luồng | Trạng thái ban đầu thường gặp | Điều cần kiểm tra riêng |
|---|---|---|
| Đổi mật khẩu khi còn truy cập | Người dùng có phiên và đáp ứng yêu cầu xác thực lại | Quyền thay đổi credential trong phiên hiện hành |
| Đặt lại mật khẩu đã quên | Người dùng không trình bày được mật khẩu hiện tại | Bằng chứng khôi phục được phép và tài khoản đích |
| Khôi phục hoặc thay MFA | Người dùng mất một hoặc nhiều authenticator | Điều kiện cho phép gắn phương tiện mới và xử lý phương tiện cũ |
| Mở khóa tài khoản | Tài khoản đang bị hạn chế theo chính sách | Ai được mở khóa và việc mở khóa có thay credential hay không |
| Khôi phục qua hỗ trợ | Cần nhân viên hỗ trợ hoặc quy trình xét duyệt | Quyền của người hỗ trợ, bằng chứng và dấu vết quyết định |

Một reset token cho phép đặt lại mật khẩu không tự được dùng để xóa mọi phương thức MFA, đổi role hoặc kích hoạt tài khoản đã bị đình chỉ. Ngược lại, tài khoản không có mật khẩu cục bộ vì dùng federation có thể cần khôi phục tại nhà cung cấp danh tính nguồn, thay vì một endpoint tự tạo mật khẩu mới ở ứng dụng phụ thuộc.

Trước khi viết test, cần xác định chính sách theo nhóm tài khoản và mức rủi ro. Tài khoản thông thường, tài khoản đặc quyền và tài khoản thuộc một nguồn danh tính bên ngoài có thể dùng các luồng khác nhau. Không có một thủ tục duy nhất phù hợp mọi mức bảo đảm.

## 3. Các điều kiện an toàn cần giữ trong suốt luồng

### 3.1. Gửi yêu cầu chưa phải là chứng minh sở hữu

Người biết một username hoặc email có thể bắt đầu yêu cầu recovery. Điều đó không chứng minh người đó kiểm soát tài khoản. Hệ thống không nên đổi credential, thay kênh liên hệ hoặc vô hiệu hóa MFA chỉ vì nhận được yêu cầu ban đầu.

OWASP Forgot Password Cheat Sheet khuyến nghị không làm thay đổi tài khoản trước khi có token hợp lệ, cùng các biện pháp chống dò tìm tài khoản và bảo vệ token khôi phục. Đây là cơ sở để kiểm tra tách biệt bước yêu cầu với bước thực hiện thay đổi. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

### 3.2. Bằng chứng phải gắn đúng tài khoản và mục đích

Recovery token, mã dự phòng hoặc kết quả xét duyệt cần ràng buộc với đúng tài khoản, namespace và thao tác được phép. Một mã xác minh email không tự tương đương mã cho phép đặt lại mật khẩu. Bằng chứng của tenant A không được đổi credential cho đối tượng cùng tên ở tenant B.

Nếu request gửi thêm `userId`, `email` hoặc `tenantId`, server phải đối chiếu với ngữ cảnh recovery đã được xác minh. Không được chuyển tài khoản đích chỉ vì một field trong bước cuối chứa giá trị khác.

### 3.3. Trạng thái trung gian chỉ có quyền giới hạn

Sau khi người dùng chứng minh một phần điều kiện, hệ thống có thể tạo một phiên giới hạn để tiếp tục recovery. Phiên đó chỉ được làm những việc thuộc mục đích đã được cho phép; không mặc nhiên trở thành phiên đăng nhập đầy đủ hoặc quyền thay mọi thông tin tài khoản.

Các bước hoàn tất không được dựa vào cờ do client tự khai, chẳng hạn `verified=true`. Test cần kiểm tra việc gọi thẳng bước cuối, đổi thứ tự hoặc dùng dữ liệu từ một giao dịch recovery khác đều không bỏ qua điều kiện server phải xác minh.

### 3.4. Hoàn tất không làm tăng quyền nghiệp vụ

Khôi phục credential không nên tự cấp role mới, đổi tenant hoặc nối tài khoản vào một danh tính khác. Trạng thái bị đình chỉ hoặc giới hạn quản trị cũng không được gỡ ngoài chính sách. Nếu quy trình có thao tác mở khóa hợp lệ đi kèm, phải xác định và kiểm thử nó như một thay đổi được cho phép rõ ràng.

## 4. Mô hình trạng thái và điểm cần quan sát

Một luồng đặt lại mật khẩu có thể được mô tả như sau:

```text
Chưa có yêu cầu
    → yêu cầu được tiếp nhận
    → bằng chứng recovery được phát hành hoặc chờ xác minh
    → bằng chứng được xác minh, chỉ có quyền recovery giới hạn
    → credential mới được ghi nhận theo chính sách
    → bằng chứng dùng một lần bị tiêu thụ
    → xử lý phiên liên quan và phát sự kiện thông báo theo contract
    → người dùng đăng nhập bằng luồng thông thường
```

Các bước trên là quan hệ logic, không có nghĩa mọi thành phần phải được triển khai trong một transaction duy nhất. Tuy nhiên, thay đổi credential và trạng thái cho phép dùng lại bằng chứng cần được phối hợp để không tạo ra hai lần thay đổi trái phép từ cùng một proof.

Những đường rẽ cần kiểm tra gồm hết hạn, dùng sai bằng chứng, hủy yêu cầu, hết số lần thử, dependency lỗi và tài khoản đổi trạng thái trong khi recovery đang diễn ra. Chẳng hạn, yêu cầu được tạo khi tài khoản còn hoạt động không tự cho phép kích hoạt lại tài khoản nếu nó đã bị đình chỉ trước lúc hoàn tất.

Thông báo email thường có thể được gửi qua tác vụ bất đồng bộ. Cần phân biệt “credential đã đổi nhưng thông báo đang chờ gửi” với “credential chưa đổi”. Một lỗi gửi thông báo không nên làm UI và audit mô tả sai trạng thái bảo mật thực tế hoặc cho phép dùng lại proof ngoài thiết kế.

## 5. Chuẩn bị fixture và môi trường kiểm thử

### 5.1. Tập tài khoản có tình huống rõ ràng

Một bộ fixture có thể gồm tài khoản A hoạt động, tài khoản B cùng tenant, tài khoản ở tenant khác, tài khoản có MFA, tài khoản bị disable và tài khoản chỉ đăng nhập qua IdP ngoài.

Với mỗi tài khoản, cần biết credential đang hợp lệ, kênh recovery đã đăng ký, authenticator hiện có, phiên đang hoạt động và trạng thái vòng đời. Dữ liệu phải là dữ liệu thử nghiệm và được tách để các ca không làm hỏng điều kiện đầu vào của nhau.

Kênh email hoặc SMS thử nghiệm cần cho phép quan sát đúng bên nhận mà không gửi tới người dùng thật. Một mail sink kiểm thử có thể hỗ trợ đọc proof cho fixture, nhưng quyền đọc sink không được mang sang môi trường vận hành hoặc làm raw proof xuất hiện trong báo cáo công khai.

### 5.2. Thời gian, số lần thử và công việc bất đồng bộ

Nên có đồng hồ kiểm thử hoặc cơ chế tạo proof với thời điểm rõ ràng. Kiểm tra trước biên hết hạn, tại biên theo contract và sau khi hết hạn, tính cả dung sai nếu cơ chế đó có định nghĩa.

Với mã dự phòng dùng một lần, cần fixture riêng cho mã chưa dùng và đã dùng. Với resend, phải chốt chính sách: proof cũ còn hiệu lực hay bị vô hiệu hóa khi phát proof mới, và có bao nhiêu yêu cầu đồng thời được phép tồn tại. Không mặc định mọi hệ thống có cùng quy tắc.

Với queue thông báo hoặc thu hồi phiên, cần quan sát trạng thái công việc và kết quả cuối. Không chỉ chèn một khoảng chờ cố định rồi hy vọng hệ thống đã xử lý xong; sử dụng điều kiện hoàn tất và thời hạn kiểm thử phù hợp.

## 6. Ma trận ca kiểm thử nền tảng

| Nhóm | Đầu vào hoặc thao tác | Kết quả cần kiểm tra |
|---|---|---|
| Recovery hợp lệ | Đúng proof, đúng tài khoản, đủ điều kiện và credential mới hợp lệ | Chỉ thay đổi credential hoặc phương tiện được phép, giữ đúng danh tính |
| Tài khoản không tồn tại | Yêu cầu recovery với định danh không có trong namespace | Phản hồi phù hợp chính sách chống dò tìm, không tạo tài khoản ngoài dự kiến |
| Proof không hợp lệ | Thiếu, sai dạng, bị sửa hoặc không khớp | Không thay credential hoặc nâng quyền trạng thái recovery |
| Proof hết hạn | Hoàn tất sau giới hạn thời gian theo contract | Bị từ chối dù proof từng hợp lệ |
| Dùng lại | Gửi lại proof dùng một lần đã hoàn tất | Không có lần thay đổi credential mới trái quy tắc |
| Sai tài khoản | Dùng proof của A với field target là B | Không tác động credential, contact hoặc MFA của B |
| Sai tenant hoặc nguồn | Proof của namespace này được gửi cho đối tượng ở namespace khác | Không vượt ranh giới định danh |
| Sai mục đích | Dùng mã xác minh liên hệ như proof reset mật khẩu | Không chấp nhận ngoài mục đích được phát hành |
| Bỏ bước | Gọi endpoint hoàn tất khi chưa xác minh đủ | Không hoàn thành recovery chỉ nhờ client khai trạng thái |
| Resend | Phát proof mới rồi thử proof cũ và mới | Tuân thủ chính sách hiệu lực đã công bố |
| Đồng thời | Hai request dùng cùng proof trong thời gian gần nhau | Không có hai lần sử dụng có tác dụng trái contract |
| Giới hạn thử | Nhập sai hoặc gửi yêu cầu nhiều lần trong fixture | Throttling và giới hạn hoạt động theo policy, không cho thử vô hạn |
| Tài khoản bị hạn chế | Hoàn tất recovery khi tài khoản đã disable hoặc đổi trạng thái | Không gỡ hạn chế ngoài quy trình được phép |
| MFA | Reset mật khẩu trên tài khoản vẫn yêu cầu MFA | Không tự xóa hoặc bỏ qua yếu tố còn bắt buộc |
| Dependency lỗi | Gửi thông báo, kho proof hoặc dịch vụ xác minh bị lỗi | Không có fallback yếu hơn hoặc trạng thái hoàn tất giả |

Ma trận cần có cả ca thành công. Nếu mọi request đều bị chặn vì cấu hình test lỗi, các ca âm có thể trông như pass trong khi chức năng recovery hợp lệ không hoạt động.

## 7. Kiểm tra bằng chứng, kênh gửi và liên kết recovery

### 7.1. Sinh, lưu và xác minh proof

Với proof ngẫu nhiên hoặc mã dự phòng, cần kiểm tra cơ chế sinh và bảo vệ phù hợp với thiết kế; không thể kết luận đủ khó đoán chỉ từ vài chuỗi nhìn có vẻ ngẫu nhiên. Review cấu hình và implementation cần bổ sung cho kiểm thử hành vi.

Nếu dùng JWT làm recovery token, chữ ký hợp lệ chưa đủ để hoàn tất: hệ thống còn cần kiểm tra mục đích, tài khoản, thời hạn và điều kiện dùng một lần theo contract. JWT không tự ngăn replay chỉ vì payload có `exp` hoặc `jti`.

Không lưu proof thô vào log, tracing, báo cáo lỗi hoặc test artifact chia sẻ rộng. Kho proof cần bảo vệ giá trị xác minh phù hợp với loại proof; không dùng cùng một cách lưu thiếu cân nhắc cho mọi loại mã ngắn, token ngẫu nhiên và authenticator.

### 7.2. Bên nhận phải đến từ một nguồn được phép

Kiểm tra recovery không bị chuyển sang địa chỉ liên hệ tùy ý do người chưa xác thực đưa vào request. Nếu quy trình cho phép thay kênh recovery, thao tác đó cần bằng chứng và điều kiện riêng; không được dùng chính kênh vừa được thay mà chưa xác minh để chứng minh quyền thay đổi đó.

Với liên kết gửi qua email, kiểm tra domain và scheme của URL được tạo từ cấu hình tin cậy. Header hoặc tham số không tin cậy không được khiến proof được gửi tới một host khác ngoài mục đích. Các điểm chuyển hướng sau recovery cũng cần được giới hạn theo thiết kế.

Trang chứa proof cần được xem xét về referrer, nội dung bên thứ ba, analytics và cache để tránh truyền proof ra ngoài. Test nên kiểm tra cả browser và các lớp proxy hoặc error reporter có thể ghi URL, không chỉ kiểm tra response của endpoint reset.

### 7.3. Link scanner và thao tác mở trang

Email có thể được công cụ an toàn hoặc trình duyệt đọc trước. Chỉ mở một liên kết recovery không nên vô tình đổi credential hoặc thực hiện một thay đổi tài khoản cần hành động xác nhận.

Nếu thiết kế trao đổi token lấy một phiên recovery giới hạn khi mở link, cần kiểm tra rõ việc tiêu thụ token, quyền của phiên và cách người dùng hợp lệ tiếp tục. Không nên giả định mọi lần GET đều có cùng hành vi; mục tiêu là tránh thay đổi tài khoản hoặc mất khả năng recovery ngoài contract do prefetch hoặc mở link tự động.

## 8. Khôi phục MFA và luồng hỗ trợ cần test riêng

### 8.1. Đặt lại mật khẩu không tự là khôi phục mọi authenticator

Với tài khoản có MFA, test cần xác định proof reset mật khẩu cho phép làm gì. Nếu nó chỉ cho đổi mật khẩu, đăng nhập sau đó vẫn phải đáp ứng các yếu tố còn bắt buộc. Không được ghi nhận toàn bộ recovery thành công chỉ vì yếu tố đầu tiên đã đổi.

OWASP MFA Cheat Sheet lưu ý các đường bypass hoặc reset MFA có thể trở thành điểm bị khai thác; cơ chế khôi phục cần được đánh giá trong bối cảnh ứng dụng. Vì vậy, một test password reset không thay cho bộ test mất thiết bị và gắn MFA mới. [OWASP Multifactor Authentication Cheat Sheet — Resetting MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa).

Với mã khôi phục dùng một lần, kiểm tra mã của tài khoản khác, mã đã dùng, số lần thử và trạng thái sau thành công. Nếu sinh bộ mã mới làm bộ cũ mất hiệu lực theo chính sách, cần chứng minh điều đó bằng kiểm tra trạng thái và hành vi.

### 8.2. Gắn phương tiện mới và xử lý phương tiện bị mất

Sau khi đủ điều kiện recovery, test cần xác minh authenticator mới được gắn đúng tài khoản, không vượt phạm vi và không làm mất những bảo vệ khác ngoài yêu cầu. Nếu phương tiện cũ bị đánh dấu mất hoặc bị xâm phạm, cần kiểm tra trạng thái sử dụng của nó theo chính sách thu hồi tương ứng.

Không nên đặt một kỳ vọng chung rằng recovery luôn phải dùng chính authenticator đã mất. Chính sách có thể cho phép mã recovery, phương tiện còn lại hoặc một quy trình xác minh khác phù hợp. NIST SP 800-63B-4 phân biệt quản lý việc gắn authenticator với các phương thức recovery và yêu cầu tương ứng; cần chọn nguồn kỳ vọng theo trường hợp cùng mức bảo đảm áp dụng. [NIST SP 800-63B-4 — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/).

### 8.3. Nhân viên hỗ trợ không được tự vượt phạm vi

Luồng helpdesk cần ca kiểm tra role hỗ trợ, tài khoản đích, tenant và điều kiện xét duyệt. Một nhân viên có thể được phép hỗ trợ tài khoản thông thường nhưng không được reset MFA của quản trị viên đặc quyền hoặc tự phê duyệt trường hợp của mình nếu chính sách cấm.

Tên, phòng ban hoặc thông tin công khai không nên bị coi là bằng chứng đủ chỉ vì người yêu cầu trả lời trùng hồ sơ. Kiểm thử quy trình cần xác định bằng chứng nào được chấp nhận, ai kiểm tra và quyết định đó được ghi nhận ra sao, thay vì chỉ kiểm tra một nút “Approve” có hoạt động.

## 9. Xác minh trạng thái sau hoàn tất hoặc từ chối

### 9.1. Credential và tài khoản

Sau recovery hợp lệ, kiểm tra credential mới hoạt động theo đúng luồng xác thực thông thường và credential cũ bị xử lý đúng chính sách. Với mật khẩu mới, việc nó vượt qua bước đầu chưa chứng minh đã hoàn tất đăng nhập nếu tài khoản còn yêu cầu MFA.

Đồng thời kiểm tra role, tenant, định danh liên kết và những thuộc tính không nằm trong mục đích recovery không bị thay đổi. Với ca sai proof hoặc sai target, cần xác minh không có thay đổi credential hoặc authenticator ở cả tài khoản sở hữu proof lẫn tài khoản bị nhắm tới.

### 9.2. Phiên và token còn tồn tại

Kế hoạch test cần nêu chính sách với session cũ, refresh token, phiên tại IdP và phiên cục bộ ở các ứng dụng phụ thuộc. Không mặc định đổi mật khẩu tại một nơi đã làm mọi phiên trong hệ sinh thái mất hiệu lực ngay.

Nếu chính sách yêu cầu thu hồi, kiểm tra từng loại artifact và giới hạn thời gian thực thi. Nếu hệ thống dùng access token tự chứa còn được chấp nhận trong một khoảng đã công bố, phải phân biệt hành vi đó với thu hồi tức thời; không đánh dấu pass chỉ vì một cờ “revoke sessions” đã được ghi ở nguồn.

Một phiên recovery giới hạn cũng không nên tự trở thành phiên có mức xác thực cao hơn bằng chứng đã đạt. Trường hợp ứng dụng yêu cầu quay lại login sau reset, test cần kiểm tra không có credential đăng nhập đầy đủ được cấp ngoài luồng đó.

### 9.3. Audit, thông báo và lỗi một phần

Audit nên ghi được giao dịch, tài khoản đích, loại recovery, kết quả và người hỗ trợ nếu có, với dữ liệu đủ để điều tra nhưng không chứa proof hoặc credential thô. Thông báo sau thay đổi cần được gửi qua kênh được thiết kế, không vô tình chuyển sang một địa chỉ mới chưa được xác minh.

Khi dịch vụ lỗi giữa chừng, cần đối chiếu trạng thái proof, credential và các công việc tiếp theo. Tránh trường hợp credential đã đổi nhưng proof vẫn có thể dùng để ghi một credential khác ngoài quy tắc, hoặc UI thông báo thành công trong khi thay đổi chưa được lưu.

## 10. Một ca kiểm thử replay có đặc tả rõ ràng

Ví dụ sau chỉ là đặc tả nội dung, không phải schema của một framework:

```yaml
testId: RECOVERY-SINGLE-USE-001
purpose: Proof dùng một lần không tạo lần đổi mật khẩu thứ hai
given:
  account: account-a
  accountState: ACTIVE
  recoveryPurpose: PASSWORD_RESET
  proofState: VALID_UNUSED
  passwordPolicy: SATISFIED
when:
  firstCompletion: Đặt mật khẩu thử nghiệm P1 bằng proof hợp lệ
  repeatedCompletion: Dùng lại cùng proof để thử đặt mật khẩu P2
then:
  firstCredentialUpdateCommitted: true
  secondCredentialUpdateCommitted: false
  currentPasswordMatches: P1
  passwordP2Accepted: false
  accountRolesUnchanged: true
  rawProofOrPasswordInAudit: false
```

Nếu endpoint hỗ trợ retry idempotent, request lặp có thể trả lại kết quả của thao tác đầu theo contract mà không thực hiện một lần thay đổi mới. Vì vậy, số lượng response `2xx` không phải phép đo duy nhất cho tính dùng một lần. Điều cần chứng minh là proof không cho phép một thay đổi credential mới trái quy tắc.

Với hai request đồng thời, cần kiểm tra kết quả commit và credential cuối cùng trong một fixture được kiểm soát. Chỉ chạy tuần tự hai lần không chứng minh cơ chế chống dùng đồng thời hoạt động. Ngược lại, không nên dựa vào một lần chạy tranh chấp tình cờ mà thiếu cách điều khiển hoặc quan sát thời điểm quan trọng.

## 11. Chọn tầng kiểm thử và báo cáo đúng phạm vi

Unit test phù hợp với chuyển trạng thái, kiểm tra thời hạn và điều kiện của proof. Integration test cần đi qua validator, kho trạng thái, đường ghi credential và audit thật trong môi trường thử nghiệm. End-to-end test bổ sung kênh gửi, mở link, giao diện recovery và đăng nhập sau khôi phục.

Mock toàn bộ bước xác minh thành `true` chỉ giúp kiểm tra phần xử lý sau một kết quả đã cho, không chứng minh proof được kiểm tra đúng. Một mail stub cũng không chứng minh cấu hình domain, template và chuyển hướng ở triển khai thật đã an toàn; cần có ca phù hợp tại tầng tích hợp hoặc đầu-cuối.

Mỗi ca nên báo cáo contract được kiểm tra, trạng thái đầu vào, điều kiện thời gian, kết quả mong đợi, quan sát thực tế và bằng chứng đã loại bí mật. Phân biệt pass, fail, chưa chạy và không áp dụng. Sửa cấu hình recovery, MFA, session hoặc connector danh tính cần có hồi quy cho những ranh giới liên quan.

## 12. Tự kiểm tra cách hiểu

**Gửi email reset thành công có chứng minh tài khoản đã được khôi phục an toàn không?**

Chưa. Cần kiểm tra proof, tài khoản đích, điều kiện hoàn tất, credential mới và trạng thái phiên hoặc MFA sau thay đổi.

**Một proof hợp lệ của A có được đổi mật khẩu B nếu body ghi `userId=B` không?**

Không. Tài khoản đích phải được ràng buộc với giao dịch và bằng chứng recovery đã xác minh, không được chuyển theo input tùy ý.

**Đặt lại mật khẩu có nghĩa là được bỏ mọi yêu cầu MFA không?**

Không. Phạm vi bằng chứng và quy trình khôi phục MFA phải được xác định riêng theo chính sách.

**Hai response thành công khi retry cùng proof có luôn chứng minh lỗi dùng lại không?**

Không nhất thiết nếu retry được xử lý idempotent. Cần kiểm tra có lần thay đổi credential mới trái contract hay chỉ trả lại kết quả cũ.

**Một recovery flow test tốt cần cho thấy điều gì?**

Người đủ bằng chứng có thể lấy lại đúng khả năng truy cập được cho phép; các proof sai, hết hạn, sai mục đích hoặc sai tài khoản không tạo thay đổi trái phép. Luồng hoàn tất giữ đúng quyền, trạng thái authenticator, phiên và dấu vết kiểm toán theo contract đã xác định.
