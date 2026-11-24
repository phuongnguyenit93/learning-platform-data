# Anti phishing user guidance: Hướng dẫn chống phishing khi khôi phục tài khoản

Khi mất mật khẩu, điện thoại, MFA hoặc passkey, người dùng thường cần lấy lại tài khoản ngay. Một lời nhắn “chúng tôi đang giúp bạn khôi phục” vì thế dễ được tin hơn thông báo đăng nhập thông thường. Kẻ tấn công có thể lợi dụng chính yêu cầu khôi phục có thật để xin mã, chuyển người dùng sang trang giả hoặc khiến họ đăng ký phương thức xác thực cho kẻ khác.

Trong thiết kế khôi phục tài khoản, hướng dẫn chống phishing cần giúp người dùng quyết định được ba việc: **đang giao tiếp với ai, đang cho phép thay đổi gì và phải dừng bằng cách nào**. Một cảnh báo chung “hãy cẩn thận” không trả lời được các câu hỏi đó.

Bài học này tập trung vào nội dung và cách đặt hướng dẫn trong hành trình khôi phục. Những mẫu giao diện, tên miền và quy trình bên dưới là đề xuất thiết kế minh họa; chúng cần được điều chỉnh cho chính sách thực tế của dịch vụ.

## 1. Nhận diện mục tiêu của cuộc lừa đảo

Phishing trong khôi phục tài khoản không chỉ nhằm lấy mật khẩu. Đích đến có thể là một phiên đăng nhập, mã dự phòng, liên kết khôi phục hoặc quyền thay đổi yếu tố xác thực.

| Tình huống giả mạo | Điều kẻ tấn công muốn lấy hoặc khiến người dùng làm | Điều hướng dẫn cần làm rõ |
| --- | --- | --- |
| “Đọc mã để tôi hủy yêu cầu khôi phục trái phép” | Chuyển mã có thể dùng để xác thực sang cuộc gọi | Mã xác thực không phải mã dành cho nhân viên hỗ trợ |
| “Mở liên kết này để xác minh bạn là chủ tài khoản” | Đưa người dùng vào trang thu thập thông tin | Cần có cách tự mở dịch vụ bằng một điểm vào đã biết |
| “Quét QR để sửa lỗi MFA” | Khiến người dùng tham gia một thao tác đăng nhập, cấp quyền hoặc cấu hình không đúng ý định | Phải biết QR thuộc quy trình nào và thao tác cuối cùng cho phép việc gì |
| “Thêm khóa dự phòng do bộ phận hỗ trợ cung cấp” | Gắn phương thức xác thực nằm dưới quyền kiểm soát của kẻ khác | Người dùng chỉ đăng ký phương thức mà mình kiểm soát |
| “Bấm đồng ý để ngừng các thông báo xác thực” | Biến sự mệt mỏi thành một lần phê duyệt | Từ chối yêu cầu ngoài ý định và mở đường báo cáo riêng |
| “Gửi ảnh trang khôi phục để chúng tôi kiểm tra” | Thu được mã, đường dẫn hoặc QR trong ảnh | Bằng chứng hỗ trợ cần che bí mật và dùng kênh nộp được xác minh |

Việc người gọi biết tên, số yêu cầu hoặc thời điểm mất điện thoại chỉ là thông tin bối cảnh. Những thông tin này có thể đã lộ; chúng không chứng minh người gọi có thẩm quyền.

## 2. Một quy trình người dùng có thể thực hiện ngay

Có thể thống nhất hành vi theo bốn bước: **dừng tương tác đáng ngờ → tự mở dịch vụ → xem lại thao tác → chỉ tiếp tục khi hiểu rõ**.

### Bước 1: Dừng tương tác đáng ngờ

Không đọc mã, chuyển tiếp liên kết, chia sẻ màn hình hoặc phê duyệt yêu cầu theo lời thúc giục. Người dùng có thể kết thúc cuộc gọi và đóng trang đang nghi ngờ mà chưa cần kết luận chắc chắn đó là lừa đảo.

Câu hướng dẫn nên cho phép dừng:

> Bạn có thể đóng trang này và tự mở lại dịch vụ. Nếu cần tiếp tục khôi phục, hãy bắt đầu từ mục Trợ giúp trong ứng dụng hoặc địa chỉ chính thức bạn đã biết.

Thông điệp này chỉ phù hợp nếu sản phẩm thực sự có đường quay lại hoặc bắt đầu lại rõ ràng. Không hứa rằng một thao tác đang dở luôn được lưu.

### Bước 2: Tự mở dịch vụ

Ưu tiên ứng dụng đã cài từ trước, dấu trang đã xác minh hoặc tự nhập địa chỉ chính thức. Nếu cần liên hệ hỗ trợ, lấy thông tin liên hệ từ điểm vào đó.

Một số điện thoại ghi ngay trong tin nhắn đang nghi ngờ không tạo ra kênh xác minh độc lập. Kết quả tìm kiếm hoặc quảng cáo mang tên thương hiệu cũng cần được kiểm tra trước khi sử dụng. FTC hướng dẫn liên hệ tổ chức bằng số điện thoại hoặc website đã biết là thật khi nghi ngờ thông điệp nhận được. [Hướng dẫn nhận diện phishing của FTC](https://consumer.ftc.gov/articles/how-recognize-avoid-phishing-scams).

### Bước 3: Xem lại thao tác cụ thể

Người dùng cần phân biệt:

- Đặt lại mật khẩu.
- Thay thế phương thức MFA đã mất.
- Đăng ký passkey mới.
- Đổi email hoặc số điện thoại khôi phục.
- Cho phép một thiết bị đăng nhập.

“Xác minh tài khoản” quá rộng nếu bước tiếp theo thực chất là thay toàn bộ phương thức xác thực. Một yêu cầu do chính người dùng bắt đầu vẫn có thể bị xen vào; ý định ban đầu không xác nhận mọi yêu cầu xuất hiện sau đó.

### Bước 4: Chỉ tiếp tục khi hiểu rõ

Nếu màn hình yêu cầu hành động khác với mục tiêu, người dùng cần có nút dừng hoặc đường hỗ trợ. Ví dụ, đang đặt lại mật khẩu nhưng xuất hiện yêu cầu thêm passkey cho một thiết bị không nhận ra thì phải dừng để kiểm tra.

## 3. Dạy kiểm tra địa chỉ mà không biến người dùng thành chuyên gia URL

Giả sử dịch vụ minh họa công bố điểm vào khôi phục là:

~~~text
https://accounts.example.com/recovery
~~~

Các địa chỉ bên dưới đều chỉ là ví dụ; không chứa liên kết khôi phục thật.

| Chuỗi hiển thị | Điều cần nhận biết |
| --- | --- |
| accounts.example.com | Host đã được công bố trong ví dụ |
| accounts.example.com.support.example | Host khác; phần đầu giống thương hiệu không làm nó trở thành địa chỉ được phép |
| accounts-example.example | Dấu gạch nối và chữ giống nhau không chứng minh cùng dịch vụ |
| support.example/accounts.example.com | Tên dịch vụ nằm trong đường dẫn, không phải host đang truy cập |
| accounts.example.com@support.example | Phần sau ký tự @ mới là host trong dạng URL này |

Không yêu cầu người dùng đoán mọi biến thể tên miền. Thiết kế nên công bố một số ít điểm vào ổn định và cung cấp cách tự mở chúng.

Biểu tượng kết nối an toàn hoặc HTTPS không xác nhận rằng website thuộc thương hiệu mong muốn. Một trang giả cũng có thể dùng HTTPS. Logo, bố cục đẹp, văn phong chuẩn và tên người gửi quen thuộc cũng không đủ làm bằng chứng.

Trên điện thoại, địa chỉ bị rút gọn hoặc trình duyệt trong ứng dụng có thể làm việc kiểm tra khó hơn. Hướng dẫn cần chỉ ra cách xem địa chỉ đầy đủ hoặc mở lại bằng trình duyệt thông thường, đồng thời giữ lựa chọn quay về ứng dụng chính thức. Đừng buộc người dùng bấm liên kết lạ chỉ để tìm hiểu xem nó có an toàn hay không.

## 4. Giải thích rõ bí mật nào không được chia sẻ

Câu “không chia sẻ OTP” cần đi kèm nơi sử dụng hợp lệ. Nếu giao diện chính thức yêu cầu nhập một mã vừa được gửi, người dùng phải hiểu sự khác biệt giữa **nhập vào biểu mẫu đã xác minh** và **đưa mã cho người khác**.

| Dữ liệu | Hướng dẫn phù hợp với luồng khôi phục |
| --- | --- |
| Mật khẩu | Chỉ nhập vào giao diện đăng nhập hoặc đặt mật khẩu đã xác minh; không đọc cho nhân viên |
| OTP hoặc mã xác nhận khôi phục | Chỉ nhập vào bước chính thức đang thực hiện, đúng mục đích đã mô tả |
| Mã khôi phục dự phòng | Giữ như bí mật xác thực; không gửi cả danh sách qua chat hoặc ảnh chụp |
| Liên kết có token khôi phục | Không chuyển tiếp, dán vào ticket hoặc chia sẻ trên mạng; người có liên kết có thể sử dụng quyền mà token mang lại |
| QR chứa cấu hình ứng dụng xác thực | Không gửi cho người khác; QR có thể chứa bí mật tạo mã |
| PIN thiết bị, PIN khóa bảo mật hoặc thao tác sinh trắc học | Chỉ thực hiện trong lời nhắc của thiết bị/hệ thống phù hợp; không đọc PIN cho người gọi |
| Mã hồ sơ hỗ trợ | Có thể dùng để tìm hồ sơ theo chính sách; biết mã hồ sơ không chứng minh quyền sở hữu tài khoản |

Không phải mọi QR đều có cùng tác dụng. QR cấu hình TOTP khác với QR dùng trong xác thực liên thiết bị. Giao diện phải nói rõ QR dùng để làm gì; lời khuyên “QR nào cũng an toàn” hoặc “QR nào cũng đánh cắp tài khoản” đều không giúp người dùng quyết định.

Với dịch vụ minh họa, nên công bố một cam kết hỗ trợ nhất quán:

> Nhân viên hỗ trợ không yêu cầu bạn đọc mật khẩu, mã xác thực, mã dự phòng, PIN hoặc gửi liên kết khôi phục. Nếu cần nhập mã, hãy nhập trực tiếp trong quy trình chính thức bạn đã tự mở.

Cam kết này phải đúng trong thực tế. Không thể vừa cảnh báo “không chia sẻ mã” vừa để nhân viên yêu cầu mã trong chat để xử lý nhanh.

## 5. Nói đúng về MFA và passkey

OTP có thời hạn hoặc chỉ dùng một lần vẫn có thể bị lừa lấy và sử dụng ngay. Người dùng không nên hiểu “mã chỉ sống vài phút” là lý do có thể đọc mã cho người khác. Tương tự, yêu cầu phê duyệt liên tục không phải lý do chấp nhận một yêu cầu ngoài ý định. [OWASP: Các kiểu tấn công MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#mfa-attack-patterns-and-mitigations).

WebAuthn sử dụng thông tin xác thực khóa công khai gắn với relying party và có xử lý origin trong nghi thức xác thực. Đây là cơ sở kỹ thuật của khả năng chống phishing trong passkey; mức bảo vệ không chỉ đến từ việc người dùng nhìn đúng logo. [Đặc tả WebAuthn](https://www.w3.org/TR/webauthn-3/).

Từ giới hạn đó, hướng dẫn của sản phẩm cần nêu rõ: passkey không tự bảo vệ mọi bước ngoài nghi thức WebAuthn. Nếu luồng thay passkey cho phép khôi phục bằng một mã dễ bị lừa lấy, tài khoản vẫn có thể bị chiếm qua nhánh khôi phục. Việc đồng ý đăng ký một phương thức không thuộc quyền kiểm soát của mình cũng là vấn đề khác với việc xác thực trên một tên miền giả.

Khi người dùng mất thiết bị có passkey, giao diện có thể giới thiệu lựa chọn đã được dịch vụ hỗ trợ, chẳng hạn dùng passkey còn truy cập được trên thiết bị khác hoặc một phương thức dự phòng đã đăng ký. Không được bảo đảm rằng mọi passkey đều đồng bộ, mọi tài khoản đều có bản sao hoặc luôn lấy lại được từ nhà cung cấp thiết bị.

## 6. Đặt hướng dẫn tại đúng thời điểm quyết định

Một trang trợ giúp dài có ích cho việc tra cứu, nhưng thông điệp ngắn cần xuất hiện ngay trước hành động có thể bị lợi dụng.

| Điểm trong hành trình | Người dùng cần biết | Ví dụ nội dung |
| --- | --- | --- |
| Trước khi gửi yêu cầu | Yêu cầu có được bắt đầu từ điểm vào đáng tin cậy không | “Hãy tự mở mục Khôi phục tài khoản. Không tiếp tục theo hướng dẫn của người đang yêu cầu bạn cung cấp mã.” |
| Khi nhập mã | Mã cho phép bước nào và nhập ở đâu | “Mã này dùng cho bước đặt lại mật khẩu đang hiển thị. Chỉ nhập tại đây; không đọc mã qua điện thoại hoặc chat.” |
| Trước khi thay MFA | Phương thức nào sẽ thay đổi | “Bạn sắp thay phương thức xác thực đã mất. Hãy dừng nếu đây không phải thay đổi bạn yêu cầu.” |
| Trước khi thêm passkey | Ai kiểm soát thiết bị mới | “Chỉ thêm passkey trên thiết bị hoặc khóa bảo mật bạn kiểm soát.” |
| Khi không còn kênh xác thực | Cách tìm hỗ trợ có thể tin cậy | “Mở Trợ giúp từ ứng dụng hoặc website chính thức để xem quy trình xác minh thay thế.” |
| Khi hoàn tất | Cần xem lại gì | “Kiểm tra các phương thức đăng nhập và thông tin khôi phục. Báo cáo nếu có thay đổi bạn không nhận ra.” |

Các mẫu trên chỉ dùng khi đúng với quyền mà mỗi bước thực sự cấp. Nếu nhập mã chỉ mở một bước xác minh tiếp theo, không mô tả nó như đã hoàn tất khôi phục. Nếu mã cho phép đổi thông tin nhạy cảm, không che tác dụng đó sau chữ “tiếp tục”.

### Mẫu thông báo cho một yêu cầu ngoài ý định

~~~text
Có yêu cầu khôi phục tài khoản.

Nếu bạn không thực hiện yêu cầu này:
- Không gửi mã hoặc liên kết cho bất kỳ ai.
- Tự mở ứng dụng hoặc website chính thức để kiểm tra bảo mật.
- Dùng mục Báo cáo yêu cầu không phải của tôi nếu cần hỗ trợ.

Không trả lời thông báo này bằng mật khẩu, mã xác thực hoặc ảnh giấy tờ.
~~~

Không khẳng định một yêu cầu khôi phục đơn thuần chứng minh tài khoản đã bị chiếm. Cũng không tạo áp lực giả như “đọc mã ngay nếu không tài khoản sẽ bị xóa”.

Thông tin như thời điểm, tên phương thức hoặc thiết bị có thể giúp đối chiếu khi được hiển thị trong ngữ cảnh đã được cho phép. Đây chỉ là tín hiệu hỗ trợ; chúng không thay thế xác thực. Màn hình công khai không nên tiết lộ sự tồn tại của tài khoản hoặc danh sách đầy đủ các yếu tố xác thực.

## 7. Giữ quy trình hỗ trợ phù hợp với lời hướng dẫn

Một người mất cả điện thoại lẫn email dự phòng cần đường hỗ trợ rõ ràng. Nếu sản phẩm chỉ nói “không tin ai” mà không có lối thoát, họ có thể tìm tới dịch vụ “mở khóa tài khoản” không đáng tin.

Quy trình hỗ trợ được đề xuất cho dịch vụ minh họa:

1. Người dùng tự mở kênh hỗ trợ từ điểm vào chính thức.
2. Hệ thống mô tả các bước xác minh và dữ liệu thực sự cần thu thập.
3. Nhân viên hướng dẫn người dùng thao tác trong quy trình; không thu bí mật xác thực qua cuộc gọi.
4. Nếu phải nộp chứng cứ danh tính, sử dụng khu vực tiếp nhận được xác minh, có giải thích mục đích và cách xử lý dữ liệu.
5. Nếu chưa đủ bằng chứng, giải thích trạng thái hồ sơ và bước có thể làm tiếp; không hạ yêu cầu vì người gọi gây áp lực.

Không hướng dẫn gửi giấy tờ qua tin nhắn cá nhân của nhân viên. Không yêu cầu cài phần mềm điều khiển từ xa để “lấy giúp” mã khôi phục. Không dùng việc trả lời được tên, ngày sinh hay mã hồ sơ như một bảo đảm tuyệt đối về danh tính.

Trong luồng hỗ trợ hợp lệ, người dùng vẫn cần quyền kết thúc cuộc gọi rồi tự mở lại hồ sơ. Việc hỗ trợ phải khuyến khích hành vi xác minh độc lập, thay vì coi đó là sự thiếu hợp tác.

## 8. Hướng dẫn xử lý khi đã tương tác với trang hoặc người giả mạo

Thông điệp cần bình tĩnh và phân biệt mức độ tương tác. Không yêu cầu người dùng tự chứng minh đã bị chiếm tài khoản rồi mới được báo cáo.

| Việc đã xảy ra | Hành động nên hướng dẫn |
| --- | --- |
| Chỉ xem tin nhắn hoặc trang, chưa nhập dữ liệu, chưa chấp thuận gì | Dừng tương tác; tự mở dịch vụ để kiểm tra nếu còn nghi ngờ; báo cáo bằng kênh chính thức |
| Đã nhập mật khẩu trên trang nghi ngờ | Dùng thiết bị đáng tin cậy để đổi mật khẩu qua dịch vụ chính thức; kiểm tra phiên và các thay đổi tài khoản; xử lý mật khẩu dùng lại ở nơi khác nếu có |
| Đã đọc OTP, đưa mã dự phòng hoặc chuyển tiếp liên kết khôi phục | Báo ngay rằng bí mật khôi phục có thể đã lộ; sử dụng chức năng hủy yêu cầu/thu hồi nếu có hoặc nhờ hỗ trợ xử lý; không chờ mã tự hết hạn |
| Đã chấp nhận đăng nhập hoặc đăng ký phương thức không nhận ra | Kiểm tra phiên và danh sách phương thức xác thực; yêu cầu thu hồi quyền truy cập/phương thức trái phép qua quy trình đã xác minh |
| Đã cài công cụ điều khiển từ xa hoặc nghi thiết bị bị kiểm soát | Ngừng phiên hỗ trợ đáng ngờ; chuyển sang thiết bị đáng tin cậy để bảo vệ tài khoản; xử lý tình trạng an toàn của thiết bị trước khi tiếp tục nhập bí mật |
| Kênh email khôi phục cũng có dấu hiệu bị chiếm | Khôi phục và bảo vệ email qua nhà cung cấp chính thức; báo rõ rủi ro kênh email cho dịch vụ tài khoản |

Một lần nhấp liên kết không tự chứng minh đã mất tài khoản. Tuy vậy, cũng không nên bảo đảm an toàn chỉ vì người dùng không nhớ đã nhập gì. Hướng dẫn nên giúp họ mô tả điều đã làm và tìm bước xử lý phù hợp.

Đổi mật khẩu đơn thuần có thể chưa loại bỏ phiên hoặc thay đổi trái phép còn tồn tại. OWASP đề cập việc xem lại thông tin khôi phục, phương thức xác thực và vô hiệu hóa phiên cùng các liên kết/mã khôi phục đang chờ sau khôi phục thành công. [OWASP: Khôi phục sau nghi ngờ bị chiếm tài khoản](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise).

Về thiết kế trải nghiệm, khi người dùng chỉ còn một phiên hợp lệ, cần giải thích tác động trước khi họ tự đăng xuất. Chức năng xử lý sự cố phải giúp chủ tài khoản xác lập lại phương thức an toàn rồi loại bỏ quyền truy cập trái phép theo chính sách, tránh biến một lời hướng dẫn chung thành việc tự khóa mình ngoài tài khoản.

Khi báo cáo, có thể thu thời điểm, kênh liên hệ, hành động đã thực hiện và mã hồ sơ không chứa bí mật. Không yêu cầu dán nguyên token hoặc ảnh có mã còn hiệu lực. Nếu cần nhận thông điệp gốc để điều tra, dùng cơ chế tiếp nhận bảo mật dành cho việc đó.

## 9. Hướng dẫn phải đi cùng kiểm soát phía hệ thống

Người dùng có thể làm đúng hướng dẫn nhưng vẫn mắc lỗi khi căng thẳng. Khả năng chống phishing của luồng khôi phục không nên phụ thuộc hoàn toàn vào việc họ nhớ mọi cảnh báo.

OWASP khuyến nghị token khôi phục đủ ngẫu nhiên, được lưu an toàn, có thời hạn và chỉ dùng một lần; phản hồi yêu cầu phải tránh làm lộ sự tồn tại của tài khoản. [OWASP: Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Các cặp thiết kế dưới đây là cách áp dụng nguyên tắc bảo vệ nhiều lớp cho dịch vụ minh họa:

| Hướng dẫn cho người dùng | Thiết kế cần hỗ trợ |
| --- | --- |
| “Chỉ tiếp tục thao tác bạn yêu cầu” | Tách rõ mục đích đặt mật khẩu, thay MFA, thêm passkey; không âm thầm cấp thêm quyền |
| “Bạn có thể dừng để kiểm tra” | Có hành động hủy, trạng thái chờ và lối vào hỗ trợ rõ ràng |
| “Không gửi mã qua hỗ trợ” | Không có biểu mẫu ticket hoặc kịch bản nhân viên buộc người dùng cung cấp mã |
| “Báo cáo nếu thay đổi không phải của bạn” | Có đường tiếp nhận báo cáo và quy trình xử lý, không chỉ gửi thông báo một chiều |
| “Không phê duyệt yêu cầu lạ” | Hạn chế lạm dụng yêu cầu, tránh để kẻ tấn công làm ngập thông báo không kiểm soát |
| “Kiểm tra sau khôi phục” | Có nơi xem phương thức xác thực, kênh khôi phục và quản lý phiên phù hợp quyền truy cập |

Nút “không phải tôi” trong một thông báo cũng là đầu vào có thể bị lạm dụng. Thiết kế cần cân nhắc xác minh và phạm vi tác động; không để bất kỳ người nhận hoặc người biết mã hồ sơ nào cũng khóa vĩnh viễn tài khoản.

Một thông báo nói “mọi phiên đã được đăng xuất” phải khớp với hành vi hệ thống. Nếu có ngoại lệ, độ trễ hoặc giới hạn, cần diễn đạt đúng để người dùng không hiểu nhầm rằng mọi quyền truy cập của kẻ tấn công chắc chắn đã biến mất.

## 10. Làm hướng dẫn dùng được khi người dùng đang gặp sự cố

Người mất thiết bị thường không ở điều kiện thuận lợi để đọc tài liệu dài. Nội dung cần ngắn ở bước quyết định, có giải thích chi tiết khi họ muốn xem thêm.

- Dùng từ rõ như “mã xác nhận”, “thay phương thức xác thực” và “đăng nhập trên thiết bị mới”.
- Không chỉ dùng màu đỏ, biểu tượng hoặc trạng thái khi rê chuột để truyền đạt cảnh báo.
- Cho phép đọc bằng công cụ hỗ trợ và điều hướng bằng bàn phím.
- Hiển thị thời hạn thật rõ ràng; không tạo đồng hồ giả để thúc ép.
- Không cấm dán mã một cách máy móc rồi buộc người dùng chuyển mã qua ứng dụng khác.
- Giữ thuật ngữ nhất quán giữa ứng dụng, email và kịch bản nhân viên.
- Cho đường báo cáo rõ ràng khi thiết bị nhận thông báo đã bị mất.
- Tránh trách móc người đã cung cấp mã; ưu tiên hành động có thể giảm thiệt hại tiếp theo.

Nếu có bước chờ xử lý, nói rõ người dùng có thể làm gì trong lúc chờ và nơi xem trạng thái hồ sơ. Một khoảng chờ không được giải thích có thể trở thành cơ hội cho người giả mạo hứa “mở khóa nhanh”.

## 11. Ví dụ xuyên suốt: Mất điện thoại và bị gọi giả danh hỗ trợ

Mai mất điện thoại chứa ứng dụng xác thực. Cô tự mở ứng dụng dịch vụ trên máy tính và bắt đầu khôi phục. Ít phút sau, một người gọi nói đúng tên cô, tự xưng là hỗ trợ và yêu cầu đọc mã gửi qua email để “xác nhận hồ sơ”.

Ở thời điểm đó, hai điều có thể đúng cùng lúc: Mai có yêu cầu khôi phục thật, còn cuộc gọi là giả. Vì vậy, hướng dẫn “chỉ nhập mã nếu bạn vừa yêu cầu khôi phục” vẫn chưa đủ.

Một hành trình được thiết kế rõ ràng sẽ giúp Mai:

1. Thấy ngay cạnh ô nhập mã rằng mã chỉ được nhập trong luồng chính thức, không đọc qua điện thoại.
2. Kết thúc cuộc gọi mà không sợ làm mất quyền được hỗ trợ.
3. Tự mở mục Trợ giúp để xem hồ sơ, thay vì gọi lại số do người kia cung cấp.
4. Xác nhận bước hiện tại chỉ đang xử lý việc thay MFA đã mất, không phải cho phép một thiết bị lạ đăng nhập.
5. Báo cáo cuộc gọi nếu đã cung cấp mã, để hệ thống xử lý bí mật bị lộ và quyền truy cập liên quan.
6. Sau khôi phục, kiểm tra lại phương thức xác thực, kênh khôi phục và phiên theo hướng dẫn chính thức.

Điểm quyết định không nằm ở việc Mai phân tích được mọi chi tiết của cuộc gọi. Sản phẩm cung cấp một quy tắc dễ thực hiện, một điểm vào tin cậy và một cách dừng có thể dùng được.

## 12. Chuẩn bị trước khi mất quyền truy cập

Hướng dẫn chống phishing nên xuất hiện cả khi thiết lập bảo mật, lúc người dùng còn đủ khả năng chuẩn bị:

- Lưu điểm vào chính thức và biết cách tìm hỗ trợ từ ứng dụng.
- Thiết lập phương thức dự phòng mà dịch vụ hỗ trợ; tránh để mọi phương thức đều chỉ truy cập được từ cùng một thiết bị.
- Cất mã dự phòng theo cách bảo vệ bí mật và có thể truy cập khi điện thoại bị mất.
- Hiểu khác biệt giữa mã xác thực, mã hồ sơ hỗ trợ và QR thiết lập.
- Biết nơi kiểm tra phiên, phương thức xác thực và thông tin khôi phục.
- Bảo vệ kênh email dùng cho khôi phục bằng các lựa chọn bảo mật phù hợp của nhà cung cấp.

Với một dịch vụ khôi phục tài khoản, hướng dẫn tốt tạo ra hành vi có thể thực hiện trong tình huống thật: tự mở đúng kênh, hiểu quyền đang cấp, giữ bí mật xác thực và báo cáo kịp thời khi có nghi ngờ.
