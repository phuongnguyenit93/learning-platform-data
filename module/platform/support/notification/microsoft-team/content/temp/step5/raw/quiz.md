Câu 1: Ứng dụng Spring chỉ cần đẩy cảnh báo một chiều vào kênh Teams đã cấu hình; cách tích hợp nào phù hợp nhất?
A. Graph đọc hồ sơ người dùng để tự gửi cảnh báo tới kênh
B. Bot Teams theo dõi hội thoại để xử lý mọi lệnh gửi tin
C. Adaptive Card tự chuyển tin mà không có dịch vụ vận chuyển
D. Workflows nhận webhook để đăng cảnh báo vào kênh
Đáp án đúng: D

Câu 2: Hệ thống cần thao tác với tài nguyên Teams dưới quyền được cấp và chính sách Microsoft 365; hướng tích hợp nào phù hợp?
A. Dùng webhook không gắn quyền người dùng để gọi tài nguyên
B. Microsoft Graph với quyền truy cập thích hợp
C. Gửi Adaptive Card thông qua luồng không kiểm tra danh tính
D. Dùng bot đăng tin rồi xem như đã được cấp quyền Graph
Đáp án đúng: B

Câu 3: Cảnh báo Teams cần bố cục mức độ, thời gian và liên kết xử lý rõ ràng; thành phần nào chủ yếu phục vụ trình bày?
A. Adaptive Card mô tả cấu trúc thẻ cảnh báo
B. Dùng Graph để thiết lập quyền truy cập các trường dữ liệu
C. Cấu hình Workflows để phân nhánh luồng theo mức cảnh báo
D. Dùng bot tạo chuỗi văn bản theo mẫu cho từng sự cố
Đáp án đúng: A

Câu 4: Người trực cần bấm nút và gửi phản hồi trong Teams để ứng dụng tiếp tục xử lý; cách tích hợp nào nên cân nhắc?
A. Bot xử lý tương tác theo ngữ cảnh hội thoại
B. Webhook một chiều chỉ chuyển chuỗi cảnh báo đã tạo sẵn
C. Dùng thẻ tĩnh có nút mà không có handler xử lý phản hồi
D. Chạy luồng theo lịch đọc sự kiện và đăng câu trả lời
Đáp án đúng: A

Câu 5: URL Workflows webhook vô tình xuất hiện trong log triển khai; rủi ro trực tiếp nào cần đánh giá?
A. Người biết URL có thể lấy quyền quản trị toàn tenant
B. Người biết URL có thể đọc lịch sử nội dung của kênh
C. Người có URL có thể thử gửi nội dung vào đích nhận
D. Người biết URL có thể đổi thành viên trong luồng
Đáp án đúng: C

Câu 6: Ứng dụng dùng Microsoft Graph nhưng yêu cầu quyền cao hơn nhiệm vụ gửi tin; nguyên tắc nào phù hợp nhất?
A. Chỉ cấp quyền cần cho tác vụ và tài nguyên
B. Cấp quyền quản trị cao nhất để hạn chế lỗi gửi tin
C. Dùng một danh tính toàn quyền cho mọi môi trường chạy
D. Để token dùng chung rồi kiểm tra quyền ở màn hình người dùng
Đáp án đúng: A

Câu 7: Luồng Workflows do một nhân viên sở hữu ngừng chạy khi người đó rời công ty; nên đánh giá vấn đề gì?
A. Token Graph của ứng dụng bị thu hồi ở lần triển khai mới
B. Quyền sở hữu và cơ chế bàn giao kết nối của luồng
C. Mẫu Adaptive Card đã thay đổi cách hiển thị trên Teams
D. Kết nối tới Microsoft 365 bị gián đoạn ở giờ cao điểm
Đáp án đúng: B

Câu 8: Cảnh báo thanh toán nghiêm trọng liên tục được gửi nhầm vào kênh marketing; cần xem xét yếu tố nào?
A. Quy tắc ánh xạ sự cố tới đúng nhóm và kênh
B. Cấu hình retry làm cảnh báo được gửi tới nhiều đích
C. Quyền gửi tin ở kênh trực chưa được gán cho luồng
D. Thứ tự xử lý hàng đợi làm cảnh báo đến trễ hơn
Đáp án đúng: A

Câu 9: Staging và production cùng sử dụng URL Workflows nhận cảnh báo; vấn đề nào dễ xảy ra nhất?
A. Luồng ở staging có thể mất quyền khi đổi cấu hình
B. Tin ở production có thể bị gửi trùng do retry
C. Tin thử nghiệm bị lẫn vào kênh cảnh báo thực
D. Giới hạn tốc độ có thể làm một môi trường chậm
Đáp án đúng: C

Câu 10: Microsoft Graph phản hồi tín hiệu giới hạn tốc độ trong đợt gửi lớn; hành động nào phù hợp?
A. Gửi lại ngay các tin lỗi bằng nhiều luồng kết nối hơn
B. Giảm kích thước thẻ nhưng không đổi nhịp gọi Graph
C. Điều tiết gửi và tôn trọng thời gian chờ phản hồi
D. Chia yêu cầu sang nhiều worker để giữ nguyên thông lượng
Đáp án đúng: C

Câu 11: Yêu cầu gửi cảnh báo bị timeout khi Teams có thể đã nhận; nguy cơ nào có thể phát sinh khi retry?
A. Một cảnh báo có thể bị gửi nhiều lần vào kênh
B. Webhook sẽ tự hợp nhất tin có cùng nội dung cảnh báo
C. Graph sẽ tự hủy giao dịch nếu client gặp timeout
D. Teams sẽ luôn sửa tin đã gửi thay vì tạo bản mới
Đáp án đúng: A

Câu 12: Worker gửi tin thất bại khi Teams gián đoạn; dữ liệu nào cần lưu để có thể gửi lại có kiểm soát?
A. Chỉ lưu nội dung tin không kèm ID và thông tin nhận
B. Chỉ lưu tổng số lỗi theo ngày của các worker gửi tin
C. Định danh cảnh báo, đích nhận và trạng thái gửi
D. Chỉ lưu tên kênh cuối cùng mà worker đã xử lý
Đáp án đúng: C

Câu 13: Nhóm trực nhận hàng trăm tin trùng từ một lỗi kéo dài; chính sách nào giúp giảm nhiễu?
A. Gộp cảnh báo lặp theo khóa sự cố và thời gian
B. Tăng tốc worker để đẩy hết hàng đợi cảnh báo hiện có
C. Kèm thêm log chi tiết vào mỗi lần lặp cảnh báo
D. Gửi cảnh báo giống nhau tới các kênh dự phòng
Đáp án đúng: A

Câu 14: Cảnh báo Teams cần giúp người trực mở đúng log nhanh chóng; nội dung nào có ích nhất?
A. Mã HTTP của request mà không liên kết ID sự cố gốc
B. Tên tài khoản bot và số phiên bản của connector
C. Mã tương quan, thời điểm và liên kết sự cố
D. Tổng số tin được gửi mà thiếu thời điểm phát sinh
Đáp án đúng: C

Câu 15: Bot gửi tin vào Teams nhưng người trực không được nhắc đích danh; cần kiểm tra điều gì?
A. Đặt dấu @ trước bất kỳ chuỗi tên người dùng nào
B. Mention gắn với danh tính người nhận hợp lệ
C. Đặt tên thẻ bằng tên người trực mà không gắn danh tính
D. Dùng thông tin hiển thị của người nhận thay cho mention
Đáp án đúng: B

Câu 16: Hệ thống chèn mô tả lỗi do người dùng nhập vào Adaptive Card; cần kiểm soát yếu tố nào?
A. Chỉ giới hạn số ký tự trong mô tả trước khi nhúng thẻ
B. Dữ liệu động phải được xử lý an toàn khi hiển thị
C. Đổi sang Markdown nhưng vẫn ghép trực tiếp giá trị thô
D. Chỉ xác thực URL webhook rồi tin vào phần nội dung thẻ
Đáp án đúng: B

Câu 17: Thẻ hiển thị đủ trường trên một client Teams nhưng thiếu ở client khác; giả định nào cần kiểm tra?
A. Quyền nhận tin có thể khác nhau theo thành viên kênh
B. Bộ nhớ đệm của từng client có thể làm chậm cập nhật
C. Mức hỗ trợ phần tử và phiên bản Adaptive Card
D. Cài đặt ngôn ngữ người dùng có thể làm đổi nhãn hiển thị
Đáp án đúng: C

Câu 18: Ứng dụng cần nhận và đáp lời những câu hỏi trực tiếp của nhân viên trong Teams; phương án nào phù hợp?
A. Bot xử lý hội thoại theo ngữ cảnh người gửi
B. Webhook Workflows chỉ đăng các cảnh báo một chiều
C. Dùng mẫu thẻ tĩnh rồi lưu phản hồi ở client người dùng
D. Gửi câu hỏi qua Graph nhưng không nhận sự kiện trả lời
Đáp án đúng: A

Câu 19: Một kênh Teams có khách mời bên ngoài nhưng ứng dụng định gửi thông tin khách hàng; cần kiểm tra gì trước tiên?
A. Bộ phận trực có được phép nhắc tên khách trong nhóm
B. Mẫu thẻ gửi tin có phù hợp giới hạn trường dữ liệu
C. Luồng Workflows có quyền phát thông báo trong kênh
D. Phạm vi người xem và chính sách chia sẻ dữ liệu
Đáp án đúng: D

Câu 20: Ứng dụng gửi báo cáo nhóm và nhắc việc riêng từng nhân viên; tiêu chí nào quyết định đích gửi phù hợp?
A. Người cần hành động và quyền xem của họ
B. Chọn theo ứng dụng có sẵn webhook cho từng môi trường
C. Chọn theo thứ tự sự kiện đã vào hàng đợi gửi tin
D. Chọn theo loại thẻ mà từng kênh đang hỗ trợ
Đáp án đúng: A

Câu 21: Webhook có URL hợp lệ nhưng Teams không hiển thị tin; dữ liệu nào hữu ích nhất để điều tra?
A. Chỉ kiểm tra mẫu thẻ trên máy dev trước khi gửi
B. Phản hồi luồng, thời gian và mã yêu cầu gửi
C. Chỉ xác nhận token hợp lệ mà không đọc kết quả luồng
D. Chỉ so sánh nội dung tin ở các lần thử nghiệm
Đáp án đúng: B

Câu 22: Kênh Teams có nhiều cuộc thảo luận sự cố; khi phản hồi cần giữ ngữ cảnh nào?
A. Đăng tin mới rồi gắn mã sự cố vào phần tiêu đề
B. Tạo một chủ đề mới cho mọi cập nhật cùng sự cố
C. Đổi nhãn thẻ trong khi không tham chiếu hội thoại
D. Gắn phản hồi với cuộc hội thoại hoặc sự cố gốc
Đáp án đúng: D

Câu 23: Graph nhận token hợp lệ nhưng thao tác với kênh Teams vẫn bị từ chối; cần xem xét gì?
A. Tăng thời gian sống của token đang còn hiệu lực
B. Đổi nội dung từ Markdown sang HTML khi gửi Graph
C. Quyền API và chính sách truy cập ở đích nhận
D. Giảm số trường trong Adaptive Card của tin gửi
Đáp án đúng: C

Câu 24: Teams tạm không nhận cảnh báo trong lúc xác nhận thanh toán; nguyên tắc xử lý nào phù hợp?
A. Chờ Teams phản hồi xong mới commit việc thanh toán
B. Tách gửi tin khỏi giao dịch thanh toán cốt lõi
C. Hủy thanh toán nếu API Teams chưa phản hồi ngay
D. Lưu cấu hình URL Teams trong bản ghi thanh toán
Đáp án đúng: B

Câu 25: Thông báo cùng một sự kiện đơn hàng xuất hiện nhiều lần vì worker retry; dữ liệu nào hỗ trợ chống trùng?
A. Mã ngẫu nhiên mới tạo cho mỗi lần thử gửi lại
B. Tên máy chủ hiện tại đang chạy worker gửi tin
C. Dùng mã thông báo của worker làm khóa chống trùng
D. Mã sự kiện hoặc khóa nghiệp vụ ổn định
Đáp án đúng: D

Câu 26: Flash sale tạo nhiều tin thống kê khiến cảnh báo lỗi nghiêm trọng bị chậm; cần ưu tiên điều gì?
A. Giữ nguyên một tốc độ cho mọi tin không phân loại
B. Gộp mọi lỗi không liên quan vào một cảnh báo lớn
C. Tắt toàn bộ thông báo từ các dịch vụ không lỗi
D. Phân mức độ và điều tiết gửi theo độ khẩn cấp
Đáp án đúng: D

Câu 27: Người nhận ở nhiều quốc gia gặp thông báo Teams sai ngôn ngữ; nên xem xét thành phần nào?
A. Dùng ngôn ngữ hệ điều hành của worker để tạo tin
B. Dùng ngôn ngữ mặc định của kênh cho mọi người
C. Mẫu nội dung và ngôn ngữ được chọn theo đích
D. Đổi kiểu chữ của thẻ theo thiết bị người xem
Đáp án đúng: C

Câu 28: Bí mật tích hợp Teams bị nghi ngờ lộ; hành động nào cần ưu tiên?
A. Giữ URL cũ nhưng giảm giới hạn tin gửi mỗi phút
B. Thay endpoint mới nhưng vẫn cho phép token cũ
C. Ngừng ghi log lỗi để không lưu thêm thông tin
D. Thay hoặc thu hồi bí mật và đánh giá phạm vi lộ
Đáp án đúng: D

Câu 29: Đội chỉ kiểm thử gửi tin với mô phỏng, không kiểm tra kênh và quyền thật; nguy cơ chính là gì?
A. Mẫu thẻ có thể khác giữa ứng dụng Teams thực tế
B. Token thử nghiệm có thể khác token ở môi trường thật
C. Cách xử lý lỗi mạng có thể khác khi triển khai thật
D. Tin có thể không được chấp nhận tại đích thực
Đáp án đúng: D

Câu 30: Sau sự cố thiếu cảnh báo, dữ liệu nào giúp truy vết đường đi của tin nhắn tốt nhất?
A. Chỉ lưu nội dung đã gửi nhưng không giữ mã sự cố
B. Trạng thái, mã tương quan và nguyên nhân lỗi
C. Chỉ lưu tổng số yêu cầu mà không ghi trạng thái
D. Chỉ xem lịch sử ở client mà không kiểm tra log
Đáp án đúng: B

Câu 31: Các bản tin thống kê định kỳ làm nhóm trực bỏ qua cảnh báo lỗi thật; nhóm cần đánh giá điều gì?
A. Tăng giới hạn gửi nhưng giữ tất cả tin ở một kênh
B. Gửi tin tổng hợp định kỳ với cùng mức ưu tiên
C. Chuyển toàn bộ thống kê thành thông báo có mention
D. Định tuyến và giảm nhiễu theo loại, mức độ tin
Đáp án đúng: D

Câu 32: Hệ thống Java/Spring gửi Teams tới nhiều đơn vị, đôi khi cần tương tác hai chiều; tiêu chí chọn tích hợp nào đúng nhất?
A. Chỉ xét loại công cụ đã có sẵn trên server
B. Nhu cầu tương tác, quyền, đích nhận và vận hành
C. Chỉ xét tên thư viện Java triển khai luồng gửi
D. Chỉ xét số URL webhook đang được cấu hình
Đáp án đúng: B
