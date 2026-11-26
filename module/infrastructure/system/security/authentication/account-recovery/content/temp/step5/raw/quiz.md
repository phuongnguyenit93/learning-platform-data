Câu 1. Khi người dùng quên mật khẩu, token đặt lại nên có đặc tính nào?
A. Có cấu trúc dễ đoán, sống lâu và dùng lại nhiều lần
B. Ngẫu nhiên mạnh, hết hạn ngắn và chỉ dùng một lần
C. Được tạo từ email, ngày sinh và mã tài khoản người dùng
D. Không hết hạn để người dùng có thể lưu lại dùng khi cần
Đáp án đúng: B

Câu 2. Phản hồi nào phù hợp khi người dùng yêu cầu gửi liên kết khôi phục?
A. Trả mã lỗi riêng cho từng trạng thái tài khoản
B. Thông báo rõ email có tài khoản hay chưa đăng ký
C. Thông báo chung, không tiết lộ tài khoản có tồn tại
D. Hiển thị tên đầy đủ nếu địa chỉ email đã tồn tại
Đáp án đúng: C

Câu 3. Khi gửi liên kết đặt lại mật khẩu qua email, cần làm gì?
A. Dùng hostname lấy trực tiếp từ header request gửi lên
B. Gửi token qua email và cả nội dung log truy cập
C. Đưa token vào query của mọi liên kết điều hướng tiếp theo
D. Dùng HTTPS, URL cố định và tránh ghi token vào log
Đáp án đúng: D

Câu 4. Sau khi mật khẩu được đặt lại thành công, hệ thống nên làm gì?
A. Vô hiệu hóa token reset còn lại và phiên cũ
B. Giữ mọi token reset khác để tránh gián đoạn người dùng
C. Chỉ cập nhật mật khẩu và giữ nguyên các phiên đăng nhập
D. Chờ access token hiện tại hết hạn rồi mới thu hồi phiên
Đáp án đúng: A

Câu 5. Người dùng mất ứng dụng MFA nhưng còn một yếu tố dự phòng đã đăng ký. Nên xử lý thế nào?
A. Xác minh yếu tố dự phòng, đăng ký lại MFA và thu hồi yếu tố mất
B. Tắt MFA vĩnh viễn sau khi người dùng gửi yêu cầu
C. Cho phép đăng nhập chỉ bằng username và email công khai
D. Gửi mã dùng chung cho mọi người dùng bị mất điện thoại
Đáp án đúng: A

Câu 6. Người dùng mất mọi yếu tố MFA và không còn thiết bị tin cậy. Quy trình nào phù hợp?
A. Cho helpdesk tự đặt lại MFA mà không lưu vết phê duyệt
B. Thực hiện identity proofing theo mức rủi ro và chính sách
C. Bỏ qua xác minh vì người dùng biết chính xác username
D. Chấp nhận ngày sinh và địa chỉ công khai làm bằng chứng duy nhất
Đáp án đúng: B

Câu 7. Recovery code nên được thiết kế và lưu trữ như thế nào?
A. Mã giống nhau cho một nhóm người dùng để dễ hỗ trợ
B. Mã entropy cao, dùng một lần và chỉ lưu dạng hash
C. Mã không hết hạn và có thể tra cứu từ trang quản trị
D. Mã ngắn dùng nhiều lần và lưu rõ trong hồ sơ tài khoản
Đáp án đúng: B

Câu 8. Người dùng mất điện thoại chứa passkey duy nhất. Bước nào phù hợp?
A. Tắt xác minh passkey cho toàn bộ tài khoản trong tổ chức
B. Cho phép thiết bị mới đăng ký bằng email chưa xác minh
C. Giữ credential trên thiết bị mất để tránh khóa tài khoản
D. Dùng passkey dự phòng hoặc recovery đã xác minh rồi thu hồi khóa mất
Đáp án đúng: D

Câu 9. Yêu cầu thay đổi yếu tố MFA trên tài khoản quản trị có rủi ro cao. Nên áp dụng gì?
A. Chỉ xác nhận qua phiên hiện tại dù phiên đã tồn tại lâu
B. Xác minh mạnh, kiểm tra rủi ro và thông báo kênh cũ
C. Chấp nhận yêu cầu ngay khi có tên đăng nhập chính xác
D. Không cần thông báo nếu người dùng đã gửi ticket hỗ trợ
Đáp án đúng: B

Câu 10. Helpdesk nhận cuộc gọi tự xưng là lãnh đạo cần reset MFA khẩn cấp. Cách nào an toàn hơn?
A. Gửi mã khôi phục tới email mới do người gọi cung cấp
B. Gọi vào số người yêu cầu vừa đọc trong cuộc gọi
C. Ưu tiên yêu cầu nếu người gọi biết tên quản lý trực tiếp
D. Gọi lại số đã đăng ký và áp dụng quy trình phê duyệt
Đáp án đúng: D

Câu 11. Email khôi phục của người dùng vừa bị chiếm quyền. Có nên chỉ dựa vào email đó để reset tài khoản chính?
A. Có, nếu liên kết reset được gửi trong cùng một phút
B. Không, nhưng có thể thay bằng câu hỏi bảo mật công khai
C. Có, vì email khôi phục luôn đáng tin hơn thiết bị cá nhân
D. Không, cần yếu tố độc lập và đánh giá rủi ro bổ sung
Đáp án đúng: D

Câu 12. Người dùng báo số điện thoại vừa bị chuyển SIM trái phép. Nên xử lý SMS recovery ra sao?
A. Tiếp tục gửi OTP SMS vì số điện thoại vẫn còn hoạt động
B. Tăng thời hạn OTP SMS để người dùng có thêm thời gian
C. Tạm ngừng dựa vào SMS và xác minh qua kênh độc lập
D. Gửi OTP SMS đồng thời tới mọi số từng có trong hồ sơ
Đáp án đúng: C

Câu 13. Hệ thống đánh giá rủi ro recovery nên sử dụng tín hiệu nào?
A. Chỉ dựa vào địa chỉ IP hiện tại của người gửi yêu cầu
B. Chỉ dựa vào vị trí địa lý suy ra từ mạng di động
C. Kết hợp lịch sử thiết bị, hành vi và tín hiệu bất thường
D. Tin mọi thiết bị mới nếu request đến từ quốc gia quen thuộc
Đáp án đúng: C

Câu 14. Khi xác minh danh tính để khôi phục tài khoản, tổ chức nên thu thập gì?
A. Bằng chứng cần thiết và tương xứng với mức rủi ro
B. Thông tin của người thân để thay thế mọi yếu tố xác minh
C. Toàn bộ giấy tờ cá nhân dù không liên quan tới tài khoản
D. Mọi dữ liệu sinh trắc học để dùng cho lần hỗ trợ sau
Đáp án đúng: A

Câu 15. Vì sao câu hỏi bảo mật dựa trên thông tin cá nhân công khai không phù hợp làm yếu tố duy nhất?
A. Câu hỏi bảo mật không thể được lưu trữ an toàn dưới dạng hash
B. Người dùng không thể nhớ câu trả lời khi dùng thiết bị mới
C. Câu trả lời có thể bị tìm thấy hoặc suy đoán dễ dàng
D. Câu trả lời luôn thay đổi sau mỗi lần đăng nhập thành công
Đáp án đúng: C

Câu 16. Người dùng yêu cầu đổi email khôi phục sang địa chỉ mới. Nên làm gì?
A. Chỉ gửi xác nhận đến địa chỉ mới vừa được nhập
B. Cập nhật ngay mà không cần xác minh phiên hoặc danh tính
C. Xác minh yêu cầu và thông báo cả kênh cũ lẫn kênh mới
D. Xóa địa chỉ cũ trước khi kiểm tra quyền sở hữu địa chỉ mới
Đáp án đúng: C

Câu 17. Endpoint xác minh mã recovery bị dò thử liên tục. Kiểm soát nào phù hợp?
A. Giới hạn thử theo tài khoản, thiết bị và nguồn truy cập
B. Chỉ giới hạn theo IP để không ảnh hưởng người dùng thật
C. Cho phép thử vô hạn nếu mã có thời hạn ngắn
D. Khóa vĩnh viễn tài khoản ngay sau lần nhập sai đầu tiên
Đáp án đúng: A

Câu 18. Làm sao ngăn một recovery token bị phát lại đồng thời ở hai request?
A. Chỉ xóa token khỏi giao diện sau khi xác minh thành công
B. Kiểm tra token hợp lệ rồi đánh dấu đã dùng sau khi xử lý xong
C. Tiêu thụ token nguyên tử và từ chối lần dùng tiếp theo
D. Cho phép dùng token nhiều lần trong thời hạn hiệu lực
Đáp án đúng: C

Câu 19. Token recovery xuất hiện trong access log và header Referer. Cần giảm rủi ro thế nào?
A. Giữ log lâu hơn để có thể điều tra mọi lần khôi phục
B. Thu hồi token lộ, che log và hạn chế referrer
C. Chuyển token sang fragment rồi ghi lại URL đầy đủ
D. Tăng độ dài URL để token khó nhìn thấy hơn
Đáp án đúng: B

Câu 20. Biểu mẫu đặt lại mật khẩu có thể bị CSRF. Biện pháp nào phù hợp?
A. Dùng CSRF token và kiểm tra Origin trước khi xử lý
B. Chỉ ẩn nút submit khi request đến từ website khác
C. Dùng token reset dài hơn để thay thế kiểm soát CSRF
D. Cho phép mọi request POST nếu URL có chứa mã tài khoản
Đáp án đúng: A

Câu 21. Sau khi khôi phục tài khoản bị nghi chiếm đoạt, cần xử lý session ra sao?
A. Chỉ đóng phiên trình duyệt vừa dùng để khôi phục
B. Giữ phiên cũ để tránh gián đoạn các thiết bị đang hoạt động
C. Thu hồi phiên và refresh token hiện có trên các thiết bị
D. Chỉ thu hồi session nếu người dùng nhớ được thiết bị bị mất
Đáp án đúng: C

Câu 22. Tài khoản bị xâm nhập và có nhiều personal access token đang hoạt động. Nên làm gì?
A. Chuyển mọi token sang quyền quản trị để tránh lỗi tích hợp
B. Thu hồi token bị ảnh hưởng và cấp lại theo nhu cầu
C. Giữ token cũ vì chúng không liên quan mật khẩu người dùng
D. Chỉ đổi mật khẩu và chờ từng token tự hết hạn
Đáp án đúng: B

Câu 23. Dịch vụ gửi email recovery tạm thời không khả dụng. Hệ thống nên làm gì?
A. Dùng kênh dự phòng độc lập đã xác minh hoặc thông báo chờ an toàn
B. Gửi token qua kênh bất kỳ người dùng yêu cầu trong lúc lỗi
C. Cho nhân viên hỗ trợ đặt lại mật khẩu trực tiếp không kiểm tra
D. Tắt toàn bộ xác minh để mọi người vẫn khôi phục được
Đáp án đúng: A

Câu 24. Một người dùng muốn bỏ qua MFA vì đang cần truy cập gấp. Chính sách phù hợp là gì?
A. Tắt MFA cho tài khoản đến khi người dùng báo đã ổn
B. Dùng quy trình khẩn cấp có kiểm soát và hậu kiểm
C. Cho phép bỏ qua nếu request đến từ mạng nội bộ công ty
D. Dùng cùng một mã bypass cho tất cả nhân viên trực ca
Đáp án đúng: B

Câu 25. Tài khoản quản trị cấp cao yêu cầu recovery nhưng bằng chứng chưa đầy đủ. Nên xử lý thế nào?
A. Khôi phục ngay vì vai trò quản trị cần tính sẵn sàng cao
B. Chuyển quyền quản trị sang email mới do người dùng cung cấp
C. Bỏ qua bước kiểm tra vì tài khoản đã có lịch sử đăng nhập
D. Giữ trạng thái hạn chế và yêu cầu xác minh bổ sung
Đáp án đúng: D

Câu 26. Cơ chế khóa tài khoản cứng sau vài yêu cầu recovery có thể bị lạm dụng thế nào?
A. Cơ chế này bảo đảm email recovery luôn được giao thành công
B. Cơ chế này ngăn mọi dạng dò token và chiếm tài khoản
C. Khóa cứng tự xác minh danh tính người gửi yêu cầu
D. Kẻ tấn công có thể cố tình khóa tài khoản người khác
Đáp án đúng: D

Câu 27. Trang recovery trả thông báo khác nhau khi username tồn tại và không tồn tại. Rủi ro là gì?
A. Token recovery tự động bị dùng lại sau mỗi lần truy cập
B. Kẻ tấn công có thể dò danh sách tài khoản hợp lệ
C. Hệ thống không thể ghi audit event cho yêu cầu thất bại
D. Người dùng có thể đặt lại mật khẩu mà không cần token
Đáp án đúng: B

Câu 28. Nhiều yêu cầu recovery bất thường xuất hiện cho cùng một tài khoản. Nên làm gì?
A. Tự động chấp thuận yêu cầu mới nhất để giảm hàng đợi
B. Gửi cùng một token tới tất cả địa chỉ từng đăng ký
C. Xóa lịch sử recovery để ngăn lộ thông tin cá nhân
D. Tăng kiểm tra rủi ro, giới hạn yêu cầu và cảnh báo bảo mật
Đáp án đúng: D

Câu 29. Ticket hỗ trợ chứa ảnh giấy tờ và recovery code của khách hàng. Cần xử lý thế nào?
A. Hạn chế truy cập, che dữ liệu nhạy cảm và xóa theo lịch
B. Cho toàn bộ nhân viên hỗ trợ quyền đọc để phối hợp nhanh
C. Sao chép nội dung ticket sang chat nhóm để xin xác nhận
D. Giữ ảnh và recovery code vô thời hạn để kiểm toán
Đáp án đúng: A

Câu 30. Sau khi recovery hoàn tất, dữ liệu tạm và token dùng trong quy trình nên được xử lý ra sao?
A. Xóa hoặc hết hiệu lực theo chính sách lưu giữ
B. Sao chép dữ liệu xác minh sang mọi hệ thống phân tích
C. Giữ token còn hiệu lực để hỗ trợ lần khôi phục tiếp theo
D. Đưa token vào hồ sơ người dùng để helpdesk tra cứu
Đáp án đúng: A

Câu 31. Người dùng đổi điện thoại nhưng còn đăng nhập trên thiết bị cũ. Cách chuyển authenticator nào an toàn?
A. Xóa MFA cũ trước khi kiểm tra thiết bị mới có hoạt động
B. Đăng ký thiết bị mới bằng mã dùng chung do helpdesk phát
C. Xác minh lại, đăng ký thiết bị mới rồi thu hồi thiết bị cũ
D. Chỉ sao chép secret MFA qua email cá nhân không mã hóa
Đáp án đúng: C

Câu 32. Tài khoản liên kết với nhà cung cấp danh tính bên ngoài bị mất quyền truy cập. Ứng dụng phụ nên xử lý ra sao?
A. Tạo mật khẩu cục bộ mới để thay thế mọi kiểm soát của IdP
B. Bỏ qua kiểm tra issuer vì người dùng đã có hồ sơ cũ
C. Cho phép email ứng dụng phụ tự đặt lại danh tính liên kết
D. Đi theo quy trình recovery của IdP và xác minh lại danh tính
Đáp án đúng: D
