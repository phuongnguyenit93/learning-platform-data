Bạn giải thích xác thực đa yếu tố (MFA) là gì và phân biệt MFA với xác thực hai bước (two-step verification) như thế nào?
Bạn phân biệt ba nhóm yếu tố xác thực knowledge, possession và inherence bằng ví dụ thực tế như thế nào?
Vì sao việc yêu cầu mật khẩu và mã PIN riêng biệt vẫn không nhất thiết tạo thành xác thực đa yếu tố?
Bạn đánh giá tính độc lập giữa các yếu tố xác thực khi nhiều yếu tố cùng phụ thuộc vào một thiết bị như thế nào?
Bạn phân biệt yếu tố xác thực với tín hiệu ngữ cảnh như vị trí, địa chỉ IP, thiết bị và thời gian truy cập như thế nào?
Bạn xác định một phương thức xác thực có thực sự chứng minh quyền kiểm soát của người dùng hay chỉ chứng minh quyền truy cập vào một kênh liên lạc như thế nào?
Bạn phân biệt authenticator, credential, factor và phương thức xác thực trong kiến trúc MFA như thế nào?
Bạn đánh giá mức độ đảm bảo của một cơ chế MFA dựa trên khả năng chống giả mạo, chống đánh cắp và khả năng khôi phục như thế nào?
Bạn lựa chọn số lượng và loại yếu tố xác thực phù hợp với mức độ nhạy cảm của tài khoản và giao dịch như thế nào?
Bạn giải thích vì sao MFA làm giảm rủi ro khi mật khẩu bị lộ nhưng không loại bỏ mọi nguy cơ chiếm đoạt tài khoản như thế nào?
Bạn xây dựng threat model cho quy trình MFA từ đăng ký yếu tố, đăng nhập, xác minh đến khôi phục tài khoản như thế nào?
Bạn phân biệt xác thực đa yếu tố với xác thực đa bước nhưng chỉ sử dụng các yếu tố cùng một nhóm như thế nào?
Bạn đánh giá vai trò của MFA trong mô hình zero trust và trong việc bảo vệ tài khoản đặc quyền như thế nào?
Bạn phân biệt xác thực người dùng với xác thực thiết bị và xác định khi nào cần kết hợp cả hai như thế nào?
Bạn giải thích cách mã OTP dựa trên thời gian (TOTP) được tạo và xác minh giữa authenticator với máy chủ như thế nào?
Bạn so sánh TOTP với HOTP về đầu vào tạo mã, trạng thái cần đồng bộ và cách xử lý mã bị lệch như thế nào?
Bạn thiết kế cơ chế đồng bộ lại HOTP counter khi thiết bị và máy chủ lệch trạng thái mà không mở rộng quá mức cửa sổ chấp nhận như thế nào?
Bạn quản lý shared secret của TOTP khi đăng ký thiết bị mới để hạn chế khả năng bị sao chép hoặc lộ lọt như thế nào?
Bạn sử dụng thời gian hiện tại và time-step để xác minh TOTP, đồng thời xử lý clock drift giữa thiết bị và máy chủ như thế nào?
Bạn lựa chọn cửa sổ chấp nhận mã TOTP để cân bằng trải nghiệm người dùng với nguy cơ chấp nhận mã đã hết hạn như thế nào?
Bạn ngăn một mã OTP đã được xác minh thành công bị sử dụng lại trong cùng cửa sổ thời gian như thế nào?
Bạn thiết kế rate limiting và giới hạn số lần thử OTP để chống brute force mà không dễ gây khóa tài khoản trái phép như thế nào?
Bạn đánh giá entropy và thời gian hiệu lực của mã OTP ảnh hưởng đến khả năng đoán mã như thế nào?
Bạn xử lý tình huống người dùng nhập mã TOTP liên tục không thành công dù đồng hồ thiết bị có vẻ chính xác như thế nào?
Bạn thiết kế quy trình khôi phục khi người dùng mất thiết bị chứa authenticator và không còn mã OTP dự phòng như thế nào?
Bạn đánh giá SMS OTP và voice OTP trước các nguy cơ SIM swap, chuyển tiếp cuộc gọi và tấn công vào mạng viễn thông như thế nào?
Bạn phân biệt OTP gửi qua email với một yếu tố possession độc lập khi email và tài khoản ứng dụng có chung cơ chế khôi phục như thế nào?
Bạn xác định trường hợp nào SMS hoặc email OTP chỉ nên là phương thức dự phòng thay vì yếu tố chính như thế nào?
Bạn thiết kế xác minh số điện thoại khi đăng ký MFA để tránh gắn nhầm số hoặc số do người khác kiểm soát như thế nào?
Bạn bảo vệ OTP khỏi bị lộ qua thông báo màn hình khóa, clipboard, lịch sử tin nhắn hoặc log hệ thống như thế nào?
Bạn giải thích cơ chế push notification MFA và cách máy chủ liên kết yêu cầu xác thực với đúng phiên đăng nhập như thế nào?
Bạn phân tích push fatigue hoặc MFA bombing và thiết kế giới hạn, thông báo ngữ cảnh hoặc cơ chế từ chối hàng loạt như thế nào?
Bạn sử dụng number matching hoặc hiển thị thông tin đăng nhập trong push prompt để giảm nguy cơ người dùng chấp thuận nhầm như thế nào?
Bạn đánh giá push approval có khả năng chống phishing đến đâu khi người dùng vẫn có thể chấp thuận một yêu cầu do kẻ tấn công khởi tạo như thế nào?
Bạn thiết kế cơ chế xác minh push có ràng buộc với thiết bị đã đăng ký và phiên đăng nhập đang chờ như thế nào?
Bạn xử lý push request hết hạn, bị gửi lặp hoặc đến muộn sau khi người dùng đã hủy phiên đăng nhập như thế nào?
Bạn giải thích FIDO2 và WebAuthn sử dụng cặp khóa công khai để xác thực người dùng mà không gửi secret dùng chung tới máy chủ như thế nào?
Bạn mô tả vai trò của challenge, origin, relying party ID và chữ ký trong quá trình xác minh WebAuthn như thế nào?
Bạn phân biệt user presence và user verification trong WebAuthn và xác định khi nào ứng dụng cần yêu cầu từng thuộc tính như thế nào?
Bạn giải thích vì sao WebAuthn gắn credential với relying party giúp chống phishing và giả mạo website như thế nào?
Bạn phân biệt security key vật lý, platform authenticator và passkey trong cách lưu giữ và sử dụng credential như thế nào?
Bạn so sánh passkey được đồng bộ qua hệ sinh thái thiết bị với credential gắn chặt vào một thiết bị về khả năng khôi phục và rủi ro như thế nào?
Bạn đánh giá vai trò của secure element, TPM hoặc vùng phần cứng bảo vệ khóa trong việc bảo vệ private key của authenticator như thế nào?
Bạn giải thích biometric local user verification hoạt động cùng passkey mà không cần gửi dữ liệu sinh trắc học thô lên máy chủ như thế nào?
Bạn phân biệt biometric là cơ chế mở khóa authenticator với việc máy chủ trực tiếp xác minh dấu vân tay hoặc khuôn mặt như thế nào?
Bạn xử lý việc người dùng mất security key hoặc thay thiết bị khi tài khoản sử dụng WebAuthn làm phương thức đăng nhập chính như thế nào?
Bạn lựa chọn chính sách đăng ký nhiều passkey hoặc security key dự phòng để giảm nguy cơ mất khả năng truy cập như thế nào?
Bạn đánh giá các giới hạn tương thích trình duyệt, thiết bị và hệ điều hành khi triển khai WebAuthn cho nhiều nhóm người dùng như thế nào?
Bạn xác định khi nào một cơ chế MFA có thể được xem là phishing-resistant và những thuộc tính kỹ thuật nào cần kiểm tra như thế nào?
Bạn phân biệt MFA dựa trên OTP với MFA dựa trên cryptographic challenge-response về khả năng chống phishing và replay như thế nào?
Bạn thiết kế quy trình đăng ký MFA ban đầu để bảo đảm chỉ người đã xác thực đủ tin cậy mới được gắn authenticator mới như thế nào?
Bạn yêu cầu tái xác thực hoặc step-up authentication trước khi người dùng thêm, xóa hoặc thay đổi phương thức MFA như thế nào?
Bạn xác minh quyền sở hữu authenticator mới trước khi kích hoạt và ngăn kẻ tấn công đã chiếm phiên đăng nhập tự đăng ký yếu tố của họ như thế nào?
Bạn thiết kế thông báo cho người dùng khi một authenticator mới được đăng ký hoặc một yếu tố hiện có bị gỡ bỏ như thế nào?
Bạn quản lý nhiều authenticator trên cùng một tài khoản để người dùng có phương án dự phòng nhưng vẫn kiểm soát được rủi ro như thế nào?
Bạn thiết kế recovery code có entropy đủ lớn, chỉ sử dụng một lần và lưu trữ an toàn để người dùng khôi phục tài khoản như thế nào?
Bạn xử lý yêu cầu reset MFA qua help desk mà không để kẻ tấn công giả mạo danh tính nhân viên hoặc chủ tài khoản như thế nào?
Bạn đánh giá rủi ro của câu hỏi bảo mật, thông tin cá nhân hoặc xác minh qua tổng đài khi dùng làm bước khôi phục MFA như thế nào?
Bạn thiết kế quy trình thay đổi số điện thoại hoặc email khôi phục có kiểm soát thời gian chờ và thông báo tới kênh cũ như thế nào?
Bạn xác định khi nào việc mất toàn bộ yếu tố MFA cần quy trình xác minh danh tính mạnh hơn đăng nhập thông thường như thế nào?
Bạn bảo vệ recovery code khỏi bị chụp ảnh, lưu trên thiết bị dùng chung hoặc chia sẻ qua kênh không an toàn như thế nào?
Bạn lựa chọn cách thu hồi authenticator bị mất hoặc bị đánh cắp và bảo đảm các phiên đăng nhập liên quan bị xử lý phù hợp như thế nào?
Bạn phân biệt MFA bắt buộc cho mọi lần đăng nhập với step-up MFA chỉ kích hoạt khi rủi ro hoặc độ nhạy của thao tác tăng như thế nào?
Bạn xây dựng chính sách adaptive authentication dựa trên thiết bị, vị trí, hành vi, mức độ rủi ro và lịch sử đăng nhập như thế nào?
Bạn đánh giá nguy cơ false positive khi dùng vị trí hoặc fingerprint thiết bị để quyết định yêu cầu MFA bổ sung như thế nào?
Bạn xác định những thao tác nhạy cảm như đổi mật khẩu, thay đổi thông tin thanh toán hoặc cấp quyền cần step-up authentication như thế nào?
Bạn thiết kế transaction signing để yếu tố xác thực gắn với nội dung giao dịch cụ thể thay vì chỉ xác nhận người dùng đang đăng nhập như thế nào?
Bạn phân biệt việc MFA xác nhận danh tính ở đầu phiên với việc xác thực lại trước thao tác có rủi ro cao như thế nào?
Bạn quản lý thời hạn hiệu lực của kết quả MFA trong phiên và xác định điều kiện buộc người dùng xác thực lại như thế nào?
Bạn bảo vệ session và token sau khi MFA thành công để kẻ tấn công không thể bỏ qua MFA bằng cách đánh cắp phiên đã xác thực như thế nào?
Bạn thể hiện mức độ hoặc phương thức xác thực đã hoàn thành trong token hoặc assertion để dịch vụ phía sau áp dụng chính sách phù hợp như thế nào?
Trong mô hình SSO hoặc identity federation, relying party đánh giá bằng chứng MFA từ identity provider dựa trên issuer, assurance level, thời điểm và loại yếu tố như thế nào?
Bạn xử lý việc chuyển đổi từ MFA yếu sang MFA mạnh hơn mà không tạo đường downgrade cho tài khoản đã được bảo vệ như thế nào?
Bạn xác định những luồng đăng nhập thay thế như legacy authentication, API key hoặc service account có thể vô hiệu hóa yêu cầu MFA như thế nào?
Bạn phát hiện và ngăn kẻ tấn công bỏ qua MFA qua password reset, account recovery, trusted device hoặc remember-me flow như thế nào?
Bạn đánh giá rủi ro session hijacking và adversary-in-the-middle có thể chiếm phiên sau khi người dùng hoàn thành MFA như thế nào?
Bạn kết hợp MFA với phát hiện credential stuffing, password spraying và đăng nhập bất thường để giảm nguy cơ chiếm tài khoản như thế nào?
Bạn thiết kế logging và audit cho sự kiện đăng ký, xác minh, thất bại, reset và thu hồi MFA mà không ghi lại OTP hoặc secret như thế nào?
Bạn lựa chọn metric và cảnh báo để phát hiện push fatigue, OTP guessing, thay đổi authenticator bất thường hoặc recovery abuse như thế nào?
Bạn xác định cách phân biệt người dùng nhập sai OTP thông thường với dấu hiệu brute force hoặc tấn công có chủ đích như thế nào?
Bạn bảo vệ endpoint xác minh MFA khỏi enumeration, replay, request flooding và lạm dụng gửi OTP như thế nào?
Bạn đánh giá tác động của rate limiting và account lockout đến khả năng chống tấn công cũng như nguy cơ DoS nhắm vào người dùng hợp lệ như thế nào?
Bạn thiết kế MFA cho tài khoản quản trị, nhân viên hỗ trợ và người dùng phổ thông với mức đảm bảo khác nhau như thế nào?
Bạn cân bằng yêu cầu MFA mạnh với khả năng tiếp cận cho người dùng không có smartphone, không dùng được sinh trắc học hoặc có hạn chế về thiết bị như thế nào?
Bạn xây dựng chính sách ngoại lệ MFA cho tài khoản dịch vụ hoặc tình huống khẩn cấp mà vẫn có kiểm soát, giám sát và thời hạn rõ ràng như thế nào?
Bạn kiểm thử TOTP để phát hiện lỗi clock drift, chấp nhận mã trùng, replay và vượt giới hạn số lần thử như thế nào?
Bạn kiểm thử quy trình WebAuthn để xác minh challenge chỉ dùng một lần và origin hoặc relying party ID không thể bị giả mạo như thế nào?
Bạn xây dựng kiểm thử end-to-end cho đăng ký, đăng nhập, step-up, mất thiết bị, recovery và thu hồi authenticator như thế nào?
Bạn xác định các tiêu chí nghiệm thu để chứng minh MFA tăng mức đảm bảo xác thực, chống bypass và vẫn duy trì khả năng khôi phục an toàn như thế nào?
