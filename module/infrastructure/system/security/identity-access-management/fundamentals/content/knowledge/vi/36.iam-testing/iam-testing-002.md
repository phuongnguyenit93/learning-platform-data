# MFA test: kiểm thử xác thực đa yếu tố theo toàn bộ vòng đời

## 1. Mục tiêu không chỉ là nhập đúng một mã

MFA test là việc kiểm tra rằng quy trình xác thực đa yếu tố được thực thi đúng theo chính sách: đúng chủ thể, đúng phương tiện, đúng giao dịch và đúng thời điểm.

Một ca nhập mật khẩu rồi nhập mã thành công chỉ kiểm tra một đường đi thuận lợi. Nó chưa chứng minh ứng dụng chặn truy cập khi MFA chưa hoàn tất, mã đã dùng không được dùng lại hoặc việc mất phương tiện không trở thành đường bỏ qua MFA.

Trong hệ thống IAM, cần kiểm tra cả vòng đời: đăng ký phương tiện, sử dụng, hết hạn, thay đổi, thu hồi, khôi phục và áp dụng kết quả tại ứng dụng.

Ví dụ xuyên suốt: An Bình yêu cầu MFA khi nhân viên đăng nhập cổng hợp đồng và yêu cầu xác thực mới hơn trước một số thao tác nhạy cảm. Nhóm phát triển phải kiểm tra cả hệ thống danh tính lẫn cách ứng dụng hiểu kết quả xác thực.

Bài học trình bày cách thiết kế bộ kiểm thử. Các tình huống, tên trạng thái và mẫu dữ liệu đều là minh họa, không phải thao tác kiểm thử trên một hệ thống đang chạy.

## 2. Xác định MFA nghĩa là gì trong luồng đang kiểm tra

MFA liên quan tới các yếu tố khác loại, như điều biết, điều sở hữu hoặc đặc điểm của chủ thể được sử dụng trong cơ chế phù hợp. Hai màn hình hoặc hai bí mật ghi nhớ không tự trở thành hai yếu tố khác loại.

Cũng không mặc định cứ dùng một thiết bị là chỉ có một yếu tố. Một authenticator có thể kết hợp việc sở hữu với bước kích hoạt phù hợp. Điều cần kiểm tra là cơ chế và bằng chứng thực tế, không phải số trang giao diện.

Trước khi viết test, cần ghi rõ:

| Nội dung | Ví dụ câu hỏi |
| --- | --- |
| Phương thức được hỗ trợ | TOTP, push hoặc cơ chế khóa công khai nào được triển khai? |
| Điều kiện yêu cầu MFA | Mọi lần đăng nhập hay chỉ các luồng được xác định? |
| Yêu cầu của thao tác nhạy cảm | Có cần phương thức hoặc độ mới khác không? |
| Trạng thái phương tiện | Đang đăng ký, hoạt động, bị đình chỉ hay đã thu hồi? |
| Luồng khôi phục | Mất phương tiện thì được xử lý theo cơ chế nào? |
| Trường hợp ngoại lệ | Có phạm vi, thời hạn và kiểm toán ra sao? |
| Mốc hoàn tất | Khi nào server coi phiên đạt yêu cầu xác thực? |

Không đặt kỳ vọng test từ một giá trị tùy ý. Thời hạn challenge, cửa sổ chấp nhận thời gian, giới hạn thử và điều kiện ghi nhớ thiết bị phải lấy từ thiết kế hoặc chính sách của hệ thống.

Nếu chưa xác định được kỳ vọng, cần làm rõ yêu cầu trước. Không sửa test để khớp mọi hành vi mà triển khai hiện tại đang có.

## 3. Mô hình hóa trạng thái xác thực

Một luồng minh họa:

~~~mermaid
flowchart TD
    A[Chưa xác thực] --> B[Yếu tố đầu tiên đạt]
    B --> C[Đang chờ MFA]
    C -->|Bằng chứng phù hợp| D[MFA đạt theo chính sách]
    C -->|Sai hoặc bị từ chối| E[Không hoàn tất]
    C -->|Hết hạn hoặc hủy| F[Challenge kết thúc]
    D --> G[Thiết lập hoặc nâng trạng thái phiên]
~~~

Luồng thực tế có thể khác, nhất là khi dùng authenticator đa yếu tố trong một bước. Dù cách trình bày khác nhau, server vẫn cần biết những điều kiện nào đã đạt.

Điểm cần kiểm tra là một trạng thái trung gian không có quyền tương đương trạng thái hoàn tất.

Ví dụ, server có thể tạo cookie hoặc mã tham chiếu cho giao dịch đang chờ MFA. Sự tồn tại của cookie không phải lỗi; lỗi xảy ra nếu cookie đó truy cập được chức năng yêu cầu xác thực hoàn chỉnh.

Các ca kiểm tra nên bao gồm:

- Gọi tài nguyên bảo vệ trước khi bắt đầu xác thực.
- Gọi sau khi yếu tố đầu tiên đạt nhưng MFA chưa hoàn tất.
- Gọi sau khi challenge hết hạn hoặc bị hủy.
- Gọi sau khi MFA đạt.
- Thay đổi tài khoản hoặc bối cảnh giữa các bước.
- Gửi lại kết quả của một giao dịch đã kết thúc.

Không chỉ kiểm tra trang tiếp theo có xuất hiện hay không. Cần kiểm tra khả năng truy cập thực tế và trạng thái server.

## 4. Chia lớp kiểm thử để biết mình đang chứng minh điều gì

| Lớp kiểm thử | Trọng tâm | Giới hạn |
| --- | --- | --- |
| Unit test | Quy tắc trạng thái, thời hạn và điều kiện policy | Không chứng minh tích hợp với nhà cung cấp |
| Integration test | Ràng buộc challenge, lưu trạng thái và xác minh bằng chứng | Có thể chưa đi qua giao diện hoặc hạ tầng thật |
| Kiểm thử hợp đồng | Ý nghĩa request, response, callback và lỗi | Không tự chứng minh mọi đường triển khai |
| End-to-end test | Luồng từ client qua các thành phần tới ứng dụng | Tốn tài nguyên và vẫn cần chọn phạm vi |
| Kiểm thử lỗi và đồng thời | Timeout, retry, kết quả đến muộn và cạnh tranh trạng thái | Cần điều khiển tình huống để có thể lặp lại |

Mock trả “MFA thành công” có ích để thử nhánh xử lý sau xác thực, nhưng không chứng minh bộ xác minh MFA thật hoạt động đúng.

Ngược lại, chỉ thử thủ công trên một thiết bị thật sẽ khó bao phủ lỗi thời gian, race condition và nhiều nhánh vòng đời.

Một bộ kiểm thử tốt dùng mỗi lớp cho câu hỏi phù hợp. Cần ghi rõ thành phần nào được giả lập và thành phần nào đang được kiểm tra thực sự.

Không tuyên bố đã kiểm tra chống dùng lại OTP nếu test thay toàn bộ bộ xác minh bằng một hàm luôn trả thành công hoặc thất bại theo cờ.

## 5. Tạo ma trận ca thử theo rủi ro

Có thể kết hợp các chiều như chủ thể, phương thức, trạng thái tài khoản, trạng thái phương tiện và hành động.

Một ma trận tối thiểu minh họa:

| Tình huống | Kỳ vọng chính |
| --- | --- |
| Đúng tài khoản, phương tiện hoạt động, bằng chứng hợp lệ | Hoàn tất theo đúng policy |
| Bằng chứng sai | Không nâng trạng thái xác thực |
| Bằng chứng hết hiệu lực | Không dùng để hoàn tất giao dịch mới |
| Bằng chứng của tài khoản khác | Không xác thực nhầm chủ thể |
| Challenge của giao dịch khác | Không gắn kết quả vào phiên không tương ứng |
| Phương tiện đã thu hồi | Không còn được chấp nhận theo mốc hiệu lực đã xác định |
| Tài khoản bị đình chỉ | Không tạo quyền truy cập chỉ vì yếu tố MFA hợp lệ |
| Chính sách yêu cầu phương thức khác | Không tự hạ yêu cầu |
| Luồng vượt giới hạn thử | Áp dụng kiểm soát theo policy |
| Nhà cung cấp gặp lỗi | Không tự đánh dấu MFA đạt |

Đối với từng phương thức được hỗ trợ, cần thử đường thành công để biết chức năng vẫn sử dụng được. Bộ test chỉ có ca từ chối có thể bỏ sót việc hệ thống đang chặn tất cả người dùng.

Cũng nên kiểm tra các vai trò và luồng có tác động cao. Chính sách cho tài khoản quản trị hoặc thao tác nhạy cảm có thể khác luồng thông thường.

## 6. Kiểm thử đăng ký phương tiện

Đăng ký là thời điểm hệ thống gắn một phương tiện với tài khoản. Nếu bước này không đúng, các lần xác thực sau có thể xác minh đúng phương tiện nhưng thuộc sai người kiểm soát.

Các ca nên xét:

- Người chưa đạt điều kiện được phép đăng ký có thể gọi API đăng ký không.
- Phiên đăng ký có gắn với đúng tài khoản không.
- Phương tiện chưa được xác nhận có bị coi là hoạt động không.
- Dữ liệu xác nhận từ phiên khác có thể hoàn tất đăng ký không.
- Đăng ký bị hủy hoặc hết hạn để lại trạng thái gì.
- Retry có tạo nhiều phương tiện ngoài dự kiến không.
- Danh sách phương tiện có tiết lộ bí mật không.

Với TOTP, seed hoặc dữ liệu QR dùng để thiết lập là bí mật. Bộ test cần kiểm tra luồng truy cập và log không làm lộ dữ liệu này ngoài phạm vi cần thiết.

Không đánh dấu phương tiện hoạt động chỉ vì giao diện đã hiển thị QR. Cần có bằng chứng hoàn tất theo cơ chế đăng ký đã chọn.

Nếu hệ thống cho phép đăng ký phương tiện đầu tiên và thêm phương tiện bổ sung theo các điều kiện khác nhau, phải tách ca kiểm thử. Một ngoại lệ ở bước đầu không nên tự áp dụng cho mọi lần thay đổi về sau.

## 7. Kiểm thử OTP, cửa sổ thời gian và giới hạn thử

Với OTP, cần kiểm tra cả xác minh giá trị và vòng đời sử dụng.

NIST SP 800-63B nêu yêu cầu chỉ chấp nhận một OTP một lần khi còn hiệu lực, đồng thời mô tả cửa sổ thời gian và kiểm soát số lần thử cho các cơ chế tương ứng. Có thể dùng những yêu cầu phù hợp này làm căn cứ xây dựng tiêu chí của hệ thống. [NIST SP 800-63B, Single-Factor OTP Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#single-factor-otp-verifiers)

Những nhóm ca cần thiết:

| Nhóm ca | Điều cần xác nhận |
| --- | --- |
| Giá trị | Mã đúng, mã sai và đầu vào không đúng định dạng được xử lý theo thiết kế |
| Thời gian | Trước, trong và sau ranh giới chấp nhận |
| Dùng lại | Bằng chứng đã dùng không tạo thêm lần xác thực |
| Ràng buộc | Mã gắn với đúng chủ thể và luồng sử dụng |
| Giới hạn thử | Nhiều lần sai được quản lý ở đúng phạm vi |
| Gửi lại hoặc tạo lại | Hành vi cũ và mới đúng với policy, không mở thêm số lần đoán |

Không coi thời gian đếm ngược trên giao diện là nguồn xác định mã còn hiệu lực. Server mới là nơi thực thi điều kiện chấp nhận.

Với TOTP, việc thời gian chuyển bước và việc challenge của ứng dụng hết hạn có thể là hai điều kiện khác nhau. Test cần làm rõ mình đang kiểm tra điều kiện nào.

Khi có dung sai thời gian, thử đúng các mép trong và ngoài khoảng dung sai đã xác định. Không thay đổi đồng hồ của cả máy dùng chung để làm test; nên sử dụng khả năng điều khiển thời gian trong môi trường kiểm thử.

Với cơ chế gửi mã mới, cần kiểm tra hành vi của mã trước đó theo thiết kế. Không tự giả định mọi phương thức có cùng quy tắc thay thế challenge, đặc biệt không trộn TOTP với mã được server phát qua kênh khác.

Giới hạn thử cũng cần được kiểm tra khi đổi phiên, yêu cầu gửi lại hoặc có nhiều request song song. Chỉ đếm lỗi ở client không chứng minh kiểm soát phía server có hiệu lực.

## 8. Kiểm thử push và phản hồi bất đồng bộ

Một luồng push có ít nhất hai phía: phiên yêu cầu xác thực và phương tiện nhận yêu cầu phê duyệt.

Các ca nên bao gồm:

- Chấp nhận đúng yêu cầu đang chờ.
- Từ chối yêu cầu.
- Người dùng không phản hồi tới lúc hết hạn.
- Phản hồi tới sau khi giao dịch đã hủy.
- Phản hồi trùng hoặc đến không đúng thứ tự.
- Kết quả thuộc chủ thể, phương tiện hoặc challenge khác.
- Lỗi gửi thông báo hoặc lỗi nhận callback.

Kết quả chấp nhận phải gắn với đúng giao dịch. Không coi “tài khoản vừa phê duyệt một push nào đó” là đủ để hoàn tất mọi phiên đang chờ của tài khoản đó.

Nếu có nội dung giúp người dùng đối chiếu giao dịch, cần thử nội dung đó khớp với giao dịch phía server. Giao diện hiển thị đúng nhưng server dùng nhầm challenge vẫn là lỗi.

Các giới hạn yêu cầu push cần được kiểm tra theo policy, trong môi trường có kiểm soát. Test tự động không nên gửi lượng lớn thông báo thật tới thiết bị cá nhân.

Callback từ bên cung cấp cần được kiểm tra nguồn và tính hợp lệ theo hợp đồng tích hợp. Một callback tự khai thành công không được bỏ qua các điều kiện ràng buộc giao dịch.

## 9. Kiểm thử khóa công khai và WebAuthn khi được triển khai

Không nên coi mọi cơ chế khóa công khai hoặc mọi passkey đều tự đáp ứng cùng một yêu cầu MFA. Cần đối chiếu khả năng của authenticator, việc xác minh người dùng và policy của luồng.

Nếu dùng WebAuthn, bộ test cần bao phủ challenge, origin, RP ID, liên kết credential với tài khoản, chữ ký và những yêu cầu user verification áp dụng cho ca đó. Đây là các phần của quy trình xác minh assertion trong đặc tả, không chỉ là kiểm tra có response từ trình duyệt. [W3C WebAuthn, Verifying an Authentication Assertion](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion)

Các ca minh họa:

| Tình huống | Kỳ vọng |
| --- | --- |
| Assertion hợp lệ cho challenge hiện tại | Đạt nếu mọi điều kiện khác cũng đúng |
| Challenge không tương ứng | Không hoàn tất giao dịch |
| Origin hoặc phạm vi RP không phù hợp | Không chấp nhận ngoài cấu hình được phép |
| Credential không thuộc tài khoản đang xét | Không xác thực nhầm chủ thể |
| Policy yêu cầu user verification nhưng kết quả không đạt | Không nâng trạng thái lên mức yêu cầu |
| Người dùng hủy thao tác | Giữ trạng thái phù hợp, không coi là thành công |
| Credential đã bị thu hồi tại hệ thống | Không tiếp tục được chấp nhận theo thiết kế |

Thiết bị hoặc authenticator giả lập có ích cho nhiều ca tự động. Vẫn cần những kiểm tra thích hợp trên tổ hợp thiết bị, trình duyệt và phương tiện được hỗ trợ thực tế.

Không đánh đồng việc có thao tác chạm xác nhận với việc mọi yêu cầu xác minh người dùng đã được đáp ứng. Kỳ vọng cần dựa trên bằng chứng giao thức và policy.

## 10. Dùng lại, retry và xử lý đồng thời

Những lỗi quan trọng có thể chỉ xuất hiện khi hai request cùng kiểm tra một trạng thái trước khi trạng thái đó được cập nhật.

Ví dụ, hai request gửi cùng bằng chứng tới cùng challenge gần như đồng thời. Nếu cả hai đều thấy trạng thái “chưa dùng”, hệ thống có thể tạo hai lần hoàn tất ngoài dự kiến.

Test cần quan sát tác động nghiệp vụ, không chỉ mã HTTP:

- Có bao nhiêu lần chuyển challenge sang hoàn tất.
- Có bao nhiêu phiên hoặc kết quả xác thực mới được tạo.
- Bằng chứng có bị tiêu thụ đúng cách không.
- Audit thể hiện điều gì.
- Retry sau mất response được xử lý ra sao.

Một hệ thống có thể trả lại kết quả đã có cho retry hợp lệ theo thiết kế idempotent. Vì vậy, hai response giống nhau chưa tự chứng minh có hai lần xác thực mới.

Một ca minh họa:

~~~yaml
testId: MFA-REPLAY-01
preconditions:
  - Tài khoản tổng hợp đã có phương tiện hoạt động
  - Có một challenge đang chờ
  - Có bằng chứng OTP hợp lệ trong môi trường kiểm thử
steps:
  - Hoàn tất challenge bằng bằng chứng hợp lệ
  - Gửi lại cùng bằng chứng cho giao dịch đã hoàn tất
expected:
  - Không phát sinh lần xác thực mới từ việc dùng lại
  - Không phát sinh phiên bổ sung ngoài hành vi retry đã xác định
  - Có thể đối chiếu trạng thái và sự kiện xử lý
~~~

Đối với OTP, cần kiểm tra chống dùng lại ở đúng phạm vi của bộ xác minh, không chỉ lưu cờ trên một màn hình hoặc một challenge cục bộ.

Nếu cùng tài khoản có nhiều giao dịch đồng thời, kết quả ở một giao dịch không được tự làm các giao dịch khác đạt MFA, trừ khi cơ chế tái sử dụng trạng thái xác thực đó được thiết kế và giới hạn rõ.

## 11. Kiểm thử phiên, step-up và thiết bị được ghi nhớ

Kết quả MFA phải được ứng dụng sử dụng đúng. Một nhà cung cấp xác thực kiểm tra đúng nhưng ứng dụng đọc sai kết quả vẫn có thể tạo lỗ hổng.

Những ca cần xét gồm:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Chỉ đạt yếu tố đầu tiên | Không có quyền của phiên đã hoàn tất |
| Client tự gửi cờ MFA đạt | Không thay đổi trạng thái đáng tin cậy phía server |
| Phiên đã có từ trước | Không tự được nâng mức khi chưa đạt điều kiện |
| Thao tác cần xác thực mới hơn | Kiểm tra độ mới và phương thức theo policy |
| MFA hoàn tất nhưng không có quyền nghiệp vụ | Vẫn bị kiểm tra authorization |
| Thay đổi chủ thể hoặc tenant | Không dùng lại ngữ cảnh sai phạm vi |
| Thiết bị được ghi nhớ | Chỉ có tác dụng trong phạm vi đã xác định |
| Thu hồi trạng thái ghi nhớ | Có hiệu lực theo cơ chế và thời hạn công bố |

Ghi nhớ thiết bị không phải lý do để bỏ mọi bước kiểm tra cho mọi hành động. Một luồng đăng nhập thông thường và một hành động quản trị có thể có yêu cầu khác nhau.

Không chỉ thử nút “tin cậy thiết bị này”. Cần kiểm tra giá trị do server quản lý, thời gian, phạm vi, khả năng thu hồi và hành vi trên thiết bị hoặc tài khoản khác.

Sau logout hoặc thu hồi phiên, cần kiểm tra những gì còn được phép tiếp tục theo thiết kế. Không mặc định xóa cookie ở một trình duyệt là đã kết thúc mọi phiên hoặc token ở mọi nơi.

## 12. Thay phương tiện, tắt MFA và khôi phục tài khoản

Đây là những đường có thể thay đổi người kiểm soát tài khoản. Không nên kiểm tra ít hơn chỉ vì chúng không nằm trên màn hình đăng nhập chính.

OWASP nhấn mạnh cần bảo vệ việc thay yếu tố, không chỉ dựa vào phiên đang hoạt động, và nên có thông báo thích hợp khi thay đổi. Những điểm này giúp xác định các ca thử cho luồng quản lý phương tiện. [OWASP MFA Cheat Sheet, Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors)

Các nhóm ca:

- Đổi tên phương tiện có khác thêm hoặc thay phương tiện không.
- Thêm phương tiện mới có yêu cầu điều kiện phù hợp không.
- Thay phương tiện cần xác thực lại theo luồng nào.
- Thu hồi phương tiện cũ có được thực thi tại điểm xác minh không.
- Tắt MFA có bị giới hạn theo policy tài khoản không.
- Mất mọi phương tiện có đi đúng đường khôi phục riêng không.
- Bộ phận hỗ trợ có quyền và bằng chứng gì khi xử lý.
- Người dùng có nhận được thông báo cần thiết không.

Nếu dùng recovery code, cần kiểm tra tính dùng một lần, phạm vi tài khoản và hành vi khi cấp bộ mã thay thế theo thiết kế. Mã khôi phục là bí mật, không phải dữ liệu tiện ghi vào báo cáo test.

Luồng khôi phục cần được kiểm tra để không vô tình tạo một đường yếu hơn làm mất tác dụng của yêu cầu MFA. Không coi việc biết email, số điện thoại hoặc thông tin hồ sơ công khai là bằng chứng đủ chỉ vì đó là một yêu cầu hỗ trợ.

Các thao tác thay đổi cũng có thể có trạng thái trung gian. Nếu thêm phương tiện mới thất bại, cần biết phương tiện đang hoạt động trước đó có còn dùng được không và có dữ liệu tạm nào phải xử lý.

## 13. Kiểm thử lỗi phụ thuộc và điều kiện thời gian

Các phụ thuộc có thể lỗi ở những mốc khác nhau: trước khi gửi challenge, sau khi gửi nhưng chưa nhận phản hồi, hoặc sau khi xác minh nhưng trước khi ứng dụng nhận kết quả.

Một số ca hữu ích:

| Lỗi được tạo trong môi trường thử | Kỳ vọng cần đối chiếu |
| --- | --- |
| Dịch vụ gửi mã không sẵn sàng | Không coi mã đã được gửi hoặc MFA đã đạt |
| Bộ xác minh timeout | Không tự chấp nhận bằng chứng |
| Callback tới muộn | Không làm sống lại giao dịch đã kết thúc trái policy |
| Lưu trạng thái thành công bị lỗi | Không tạo trạng thái nửa hoàn tất không kiểm soát |
| Response mất sau khi hoàn tất | Retry không tạo tác động thừa |
| Đồng hồ kiểm thử qua ranh giới | Kết quả đúng theo cửa sổ và dung sai |
| Chính sách đổi trong lúc chờ | Hành vi theo quy tắc chuyển tiếp đã xác định |

Cần phân biệt người dùng bị từ chối với lỗi kỹ thuật. Phân loại giúp vận hành, nhưng cả hai đều không được tự mở quyền.

Nếu hỗ trợ phương thức dự phòng, chỉ những phương thức và điều kiện đã được cho phép mới có thể sử dụng. Không tự hạ yêu cầu khi một nhà cung cấp gặp lỗi.

Dùng đồng hồ có thể điều khiển, giả lập callback và điểm lỗi phù hợp giúp test có thể lặp lại. Tránh phụ thuộc vào các khoảng chờ dài hoặc việc một nhà cung cấp thật tình cờ gặp sự cố.

## 14. Dữ liệu kiểm thử, bí mật và CI

Bộ test MFA cần bí mật để thực hiện những ca hợp lệ, nhưng phải giữ chúng trong phạm vi kiểm thử.

Nên tổ chức:

- Tài khoản tổng hợp và tenant kiểm thử riêng.
- Phương tiện và credential không dùng chung với người dùng thật.
- Kênh nhận thông báo sandbox hoặc giả lập khi phù hợp.
- Cấu hình rõ thành phần thật và thành phần giả lập.
- Thời gian, trạng thái và dữ liệu có thể thiết lập lại.
- Quy tắc dọn dữ liệu được tạo trong từng lần chạy.
- Quyền chạy test phù hợp với môi trường.

Không đưa TOTP seed, recovery code, access token hoặc dữ liệu QR vào log CI, ảnh chụp lỗi hoặc báo cáo chia sẻ rộng.

Một cơ chế bỏ qua MFA dành cho test có thể giúp thử chức năng khác, nhưng không được dùng làm bằng chứng bộ xác minh thật đã đạt. Cũng cần kiểm soát để cấu hình kiểm thử không trở thành cấu hình hoạt động ngoài phạm vi dự kiến.

Với các test cần gửi SMS hoặc push thật, cần giới hạn phạm vi và tần suất theo môi trường kiểm thử. Bộ test không nên tạo thông báo hàng loạt hoặc ảnh hưởng tài khoản thật.

Khi chạy song song, mỗi ca cần dữ liệu đủ độc lập. Một test tiêu thụ mã hoặc thu hồi phương tiện có thể làm test khác thất bại nếu dùng chung cùng trạng thái.

## 15. Bằng chứng và tiêu chí hoàn tất bộ kiểm thử

Một kết quả test có ích cần cho biết:

| Nội dung | Ví dụ |
| --- | --- |
| Phiên bản triển khai và policy | Biết hệ thống nào đã được thử |
| Phương thức và luồng | Không gộp mọi loại MFA vào một nhãn |
| Điều kiện ban đầu | Tài khoản và phương tiện ở trạng thái nào |
| Hành động | Request hoặc bước nào đã được thực hiện |
| Kỳ vọng | Trạng thái và quyền cần đạt hoặc không đạt |
| Quan sát | Response, trạng thái và tác động thực tế |
| Giới hạn | Thành phần nào được giả lập hoặc chưa bao phủ |
| Kết quả | Đạt, không đạt hoặc không thể kết luận |

Không ghi bí mật để làm bằng chứng. Có thể dùng tham chiếu ca thử, sự kiện đã giảm thông tin và trạng thái tổng hợp.

Số lượng test hoặc tỷ lệ pass không tự chứng minh MFA được bảo vệ đầy đủ. Cần biết những luồng quan trọng như khôi phục, thay phương tiện, API trực tiếp và dùng lại bằng chứng đã được bao phủ hay chưa.

Tại An Bình, một bộ test chỉ kiểm tra nhập TOTP trên trình duyệt sẽ được mở rộng sang trạng thái chờ MFA ở API, challenge song song, thay phương tiện và quyền của phiên sau xác thực. Sau đó, mỗi lỗi được sửa có thêm ca hồi quy ở lớp phù hợp.

MFA test có giá trị khi chứng minh cả hai phía: người dùng đáp ứng đúng điều kiện có thể hoàn tất công việc, còn dữ liệu sai, trạng thái thiếu, lỗi phụ thuộc và đường thay đổi phương tiện không làm phát sinh quyền ngoài chính sách.
