Câu 1: Ứng dụng Spring chỉ cần gửi thông báo một chiều vào một kênh Slack cố định; phương án nào thường đơn giản nhất?
A. Incoming Webhook đã cấu hình cho đích gửi phù hợp
B. Web API với bot và nhiều quyền đọc lịch sử kênh
C. Slack SDK dùng tài khoản cá nhân để mở phiên chat
D. Block Kit tự đăng tin mà không có kênh truyền tải
Đáp án đúng: A

Câu 2: Hệ thống phải chọn nhiều channel và trả lời theo thread từ backend Java; lựa chọn nào linh hoạt nhất?
A. Incoming Webhook cố định tự chọn mọi workspace đích
B. Block Kit tự xác định channel theo tiêu đề của thẻ
C. Mẫu JSON trên ứng dụng client không có xác thực
D. Web API với token và quyền gửi tin phù hợp
Đáp án đúng: D

Câu 3: Sau khi gọi API đăng tin vào Slack, backend muốn trả lời vào cùng chuỗi thảo luận; nên giữ dữ liệu nào?
A. Tên hiển thị của người trực trong workspace Slack
B. Mã của block cuối cùng trong nội dung tin đã gửi
C. Timestamp của tin gốc để dùng làm thread reference
D. Đường dẫn tệp log của server trong lần gọi đầu
Đáp án đúng: C

Câu 4: Một nhân viên dán URL Incoming Webhook vào issue công khai; rủi ro nào cần xử lý trước tiên?
A. Bên thứ ba được cấp mọi quyền đọc của workspace
B. Bên thứ ba có thể dùng URL thử đăng tin vào kênh
C. Mọi thành viên Slack đều tự trở thành chủ sở hữu bot
D. Slack tự xóa toàn bộ lịch sử channel sau khi URL lộ
Đáp án đúng: B

Câu 5: Nhóm muốn cảnh báo có tiêu đề, mức độ, thời gian và nút điều hướng rõ ràng; khả năng nào phù hợp?
A. Block Kit thiết kế các phần bố cục có cấu trúc
B. Slack Web API tự chuyển mọi stack trace thành giao diện
C. Incoming Webhook tự tạo sơ đồ sự cố từ log máy chủ
D. Slack SDK tự thêm các nút điều khiển từ JSON bất kỳ
Đáp án đúng: A

Câu 6: Một bot token chỉ cần gửi cảnh báo nhưng được cấp nhiều quyền quản trị workspace; nên làm gì?
A. Giữ toàn bộ quyền để tránh lỗi khi đổi tên channel
B. Dùng token cá nhân của quản trị viên cho mọi service
C. Đưa token vào nội dung cảnh báo để người trực kiểm tra
D. Giảm quyền về phạm vi cần cho hành động gửi
Đáp án đúng: D

Câu 7: API Slack trả lỗi không thể gửi vào channel riêng dù token hợp lệ; cần kiểm tra giả định nào?
A. Độ dài tên máy chủ chạy service trong mạng nội bộ
B. Số lượng lớp Java gọi Slack SDK trong ứng dụng
C. Kích thước tiêu đề của từng Block Kit notification
D. Quyền truy cập và tư cách thành viên tại channel
Đáp án đúng: D

Câu 8: Một tenant dùng chung service gửi tin cho nhiều workspace Slack; điều gì cần ràng buộc khi định tuyến?
A. Chỉ phân loại theo mức độ lỗi mà bỏ qua workspace
B. Giữ một webhook chung cho mọi tenant trong hệ thống
C. Workspace, token và đích nhận theo đúng tenant
D. Dùng email người gửi làm ID channel của mọi workspace
Đáp án đúng: C

Câu 9: Đội vận hành muốn mỗi sự cố có một thread riêng thay vì nhiều tin rời; thiết kế nào đáp ứng tốt nhất?
A. Duy trì ID sự cố gắn với timestamp tin cha
B. Tạo channel mới cho từng sự kiện log trong hệ thống
C. Đổi tên người gửi theo mã sự cố ở mỗi lần retry
D. Gửi tin nhắn định kỳ và không lưu liên kết thread
Đáp án đúng: A

Câu 10: Một ứng dụng gửi thông báo vào nhiều channel và thấy lỗi rate limit; cách xử lý nào phù hợp nhất?
A. Gửi lại cùng request ngay với số lượng worker gấp đôi
B. Thêm nhiều token để bỏ qua giới hạn workspace
C. Đổi Block Kit sang văn bản để vô hiệu hóa rate limit
D. Điều tiết tốc độ và tuân thủ thời gian chờ trả về
Đáp án đúng: D

Câu 11: Slack Web API trả HTTP thành công nhưng body báo thao tác không thành công; backend cần kiểm tra gì?
A. Chỉ kiểm tra HTTP status rồi xem như đã gửi xong
B. Nội dung phản hồi API và trạng thái nghiệp vụ trả về
C. Chỉ kiểm tra đường truyền HTTPS có chứng chỉ hợp lệ
D. Chỉ ghi thời gian thực hiện mà bỏ qua dữ liệu phản hồi
Đáp án đúng: B

Câu 12: Backend mất kết nối ngay sau lần gọi đăng tin, chưa biết Slack đã nhận chưa; retry có nguy cơ gì?
A. Cùng cảnh báo có thể được đăng hai lần trong kênh
B. Slack sẽ luôn hợp nhất nội dung khi có retry liên tiếp
C. Tin đầu tiên tự bị xóa khi client gặp lỗi timeout
D. Mọi request lặp sẽ được đổi thành tin nhắn thread
Đáp án đúng: A

Câu 13: Một incident nghiêm trọng bị trộn giữa hàng trăm bản tin thống kê; cần ưu tiên điều gì trong thiết kế?
A. Lọc, gộp và định tuyến theo mức độ khẩn cấp
B. Dùng thêm màu sắc nhưng giữ nguyên mọi kênh nhận
C. Phát mọi sự kiện cùng mức ưu tiên để tránh thiên lệch
D. Tăng số thông báo định kỳ để người trực quan tâm hơn
Đáp án đúng: A

Câu 14: Bản tin Slack chứa thông tin khách hàng cá nhân nhưng channel có nhiều đối tác; trước khi gửi cần đánh giá gì?
A. Số lượng blocks hiển thị trong nội dung hiện tại
B. Phạm vi người nhận và chính sách bảo vệ dữ liệu
C. Chế độ sáng tối đang bật ở ứng dụng Slack desktop
D. Độ dài username của người sở hữu ứng dụng webhook
Đáp án đúng: B

Câu 15: Một thông báo dùng chuỗi từ lỗi hệ thống để dựng nội dung Slack và bị hiển thị sai ký tự đặc biệt; cần kiểm tra gì?
A. Cách thay tất cả dữ liệu thành tên channel mặc định
B. Cách tăng tần suất retry nhưng giữ nguyên payload
C. Cách escape nội dung cho định dạng Slack sử dụng
D. Cách lưu token bot trong phần mô tả của tin nhắn
Đáp án đúng: C

Câu 16: Bot đăng tin có tên người trực trong nội dung nhưng không tạo mention đúng người; cần kiểm tra gì?
A. Thay tên hiển thị bot bằng tên của người trực cần nhắc
B. Định danh người dùng và cú pháp mention của Slack
C. Gửi lại nội dung với mức ưu tiên cao hơn mặc định
D. Tăng số lượng block chứa tên người dùng được nhập
Đáp án đúng: B

Câu 17: Bản tin Block Kit hiển thị đầy đủ trong kênh nhưng bản xem trước không rõ nội dung; nên xem xét thành phần nào?
A. Số luồng worker đang chờ gọi tới Slack Web API
B. Mã định danh máy chủ database của dịch vụ thông báo
C. Tên của từng package Java dùng dựng đối tượng JSON
D. Văn bản dự phòng dễ hiểu bên cạnh các blocks
Đáp án đúng: D

Câu 18: Một bot được thêm vào workspace nhưng chưa có quyền đăng một channel cụ thể; rủi ro nào thực tế nhất?
A. Bot có thể tự thêm mình vào mọi channel riêng tư
B. Có thể gặp lỗi khi đăng dù xác thực bot thành công
C. Token sẽ tự chuyển thành quyền quản trị của workspace
D. Mọi channel khác cũng không nhận được tin từ người dùng
Đáp án đúng: B

Câu 19: Đội Java dùng Slack SDK nhưng thử nghiệm nghiệp vụ vẫn gọi Internet thật; cách kiểm thử nào phù hợp hơn?
A. Dùng token production trong mọi kiểm thử để dễ tái hiện
B. Tách lớp gọi Slack để giả lập phản hồi khi unit test
C. Chỉ test nội dung khởi tạo mà không kiểm tra lỗi gửi
D. Bỏ kiểm thử retry vì đó là trách nhiệm của SDK
Đáp án đúng: B

Câu 20: Một channel được đổi tên nhưng service đang dùng ID channel ổn định; lựa chọn nào thường ít phụ thuộc hơn?
A. Định tuyến bằng ID channel thay vì tên hiển thị
B. Định tuyến bằng thứ tự alphabet của các tên channel
C. Dùng tên của người gửi làm đích gửi thay cho channel
D. Đổi token bot mỗi lần channel đổi tên hiển thị
Đáp án đúng: A

Câu 21: Webhook mới hoạt động trong staging nhưng production không gửi được vì cấu hình đích khác nhau; cần quản lý gì?
A. Một webhook dùng chung để không cần kiểm tra quyền
B. Bí mật và cấu hình đích nhận theo từng môi trường
C. Chỉ thay màu Block Kit mà không đổi URL tích hợp
D. Dựa vào tên chi nhánh trong log để chọn mọi workspace
Đáp án đúng: B

Câu 22: Đội sử dụng retry không giới hạn cho lỗi gửi Slack do token bị thu hồi; hậu quả nào dễ xảy ra?
A. Token sẽ tự hợp lệ lại nếu request được gửi đủ lần
B. Hàng đợi tích lũy lỗi không thể hồi phục bằng retry
C. Kênh sẽ tự chuyển sang webhook khác có quyền cao hơn
D. Slack SDK tự lấy lại token đã thu hồi từ browser
Đáp án đúng: B

Câu 23: Một nhóm cần nhận cảnh báo đúng kênh nhưng thỉnh thoảng webhook được cấu hình trỏ sai nơi; nên kiểm soát gì?
A. Giữ kênh cuối cùng từng gửi thành công cho mọi loại lỗi
B. Cho mọi ứng dụng chọn tên channel từ nội dung người dùng
C. Ánh xạ nguồn sự kiện với workspace và channel đích
D. Dùng một thread cho tất cả sự cố của mọi workspace
Đáp án đúng: C

Câu 24: Ứng dụng Java gửi tin trực tiếp ngay trong transaction thanh toán; khi Slack chậm đơn hàng cũng timeout; nên đánh giá gì?
A. Tăng timeout giao dịch để đợi Slack phản hồi xong
B. Hủy thanh toán nếu channel trực đang giới hạn tốc độ
C. Tạo thêm Block Kit để kéo dài thời gian gửi thông báo
D. Tách giao dịch nghiệp vụ khỏi chuyển phát thông báo
Đáp án đúng: D

Câu 25: Trong thời gian Slack gián đoạn, worker khởi động lại và mất toàn bộ thông báo chưa gửi; cần cơ chế nào?
A. Giữ mọi thông báo chỉ trong bộ nhớ worker hiện tại
B. Tăng số thread tạo nội dung mà không lưu hàng đợi
C. Chỉ lưu tổng số tin phát sinh ở mỗi lần triển khai
D. Lưu công việc gửi bền vững cùng trạng thái retry
Đáp án đúng: D

Câu 26: Một request Slack bị giới hạn tốc độ và trả thời gian chờ; xử lý nào phù hợp trước khi thử lại?
A. Đổi tên channel nhưng tiếp tục gửi ngay lập tức
B. Thay token bằng token có quyền đọc lịch sử rộng hơn
C. Đợi theo chỉ dẫn hạn mức và áp dụng backoff
D. Cắt bỏ timestamp của sự cố rồi gửi lại liên tục
Đáp án đúng: C

Câu 27: Ứng dụng gắn một correlation ID vào mỗi sự cố trước khi gửi Slack; mục đích chính là gì?
A. Thay thế quyền của bot khi gửi tới channel riêng tư
B. Cho phép Block Kit tự tạo được các hình ảnh động
C. Liên kết thông báo với log và kết quả xử lý gốc
D. Bỏ qua giới hạn số request tại Slack Web API
Đáp án đúng: C

Câu 28: Nhóm muốn tránh đăng lặp thông báo khi hàng đợi gửi lại cùng một sự kiện; dữ liệu nào quan trọng nhất?
A. Khóa nghiệp vụ ổn định cho mỗi lần phát cảnh báo
B. Token mới tạo ngẫu nhiên cho mỗi request retry
C. Thời gian máy chủ khởi chạy dịch vụ lần gần nhất
D. Tên file cấu hình được lưu trên ứng dụng Spring
Đáp án đúng: A

Câu 29: Một webhook Slack bị nghi lộ trên kho mã; thao tác phản ứng nào phù hợp nhất?
A. Đổi tên người gửi nhưng giữ nguyên webhook URL cũ
B. Tăng số lần retry để phát hiện tin không hợp lệ
C. Chỉ chỉnh nội dung Block Kit mà không thay secret
D. Thu hồi hoặc thay bí mật rồi kiểm tra phạm vi lộ
Đáp án đúng: D

Câu 30: Đội chỉ kiểm tra mã HTTP mà không lưu lỗi của Slack Web API; hậu quả nào đáng chú ý?
A. Khó phân biệt lỗi quyền, hạn mức và nội dung gửi
B. Không thể kiểm tra màu sắc của thẻ trong ứng dụng
C. Không thể biết thứ tự tệp nguồn được Java biên dịch
D. Không thể thay đổi tên của channel trong hệ thống
Đáp án đúng: A

Câu 31: Một workflow gửi thông báo vào channel và thread khác nhau nhưng bản tin thiếu mã vụ việc; nhóm cần thêm gì?
A. Thêm tất cả stack trace bất kể kích thước của tin
B. Chỉ thêm tên bot rồi dựa vào thời gian đăng để tìm
C. Thông tin sự cố và liên kết hành động trong nội dung
D. Đổi mỗi block thành một tin nhắn không kèm ngữ cảnh
Đáp án đúng: C

Câu 32: Một hệ thống Spring gửi cảnh báo Slack cho nhiều nhóm với ràng buộc bảo mật và độ tin cậy; tiêu chí thiết kế nào bao quát nhất?
A. Chọn công cụ theo tên package Java ngắn nhất
B. Chọn workflow theo số trường của Block Kit
C. Chọn API theo quyền, đích, ngữ cảnh và hành vi lỗi
D. Chọn channel có số tin đăng cao nhất trong ngày
Đáp án đúng: C
