Câu 1: Website muốn bot Telegram gửi tin riêng cho khách vừa đăng ký. Điều kiện nào cần có trước khi bot nhắn lần đầu?
A. Khách theo dõi kênh công khai do cửa hàng quản lý.
B. Khách cung cấp username Telegram trong biểu mẫu web.
C. Khách bắt đầu cuộc trò chuyện riêng với bot trước.
D. Khách thêm bot vào nhóm thử nghiệm của riêng họ.
Đáp án đúng: C

Câu 2: Ứng dụng cần lưu chat_id của nhóm để gửi thông báo đơn hàng. Nguồn dữ liệu nào đáng tin cậy nhất?
A. Dùng tên nhóm làm chat_id vì tên đó luôn duy nhất.
B. Lấy id người gửi tin gần nhất làm chat_id của nhóm.
C. Dùng id người quản trị đã thêm bot vào nhóm cần gửi.
D. Lấy chat.id từ update ngay trong nhóm cần gửi.
Đáp án đúng: D

Câu 3: Bot đã được thêm vào một Telegram Channel nhưng không thể đăng thông báo. Cần kiểm tra điều gì trước?
A. Cho bot quyền đăng bài với vai trò quản trị kênh.
B. Yêu cầu mọi người theo dõi kênh bấm Start với bot.
C. Thêm bot làm thành viên thường của kênh tương ứng.
D. Cho bot quyền đọc tin của nhóm có liên quan tới kênh.
Đáp án đúng: A

Câu 4: Dịch vụ Spring đang dùng webhook nhưng muốn chuyển sang long polling với getUpdates. Hành động nào phù hợp?
A. Giữ webhook rồi gọi getUpdates bằng cùng bot token.
B. Xóa webhook trước khi bắt đầu gọi getUpdates.
C. Đặt offset cao hơn trong khi vẫn giữ webhook.
D. Đổi chat_id nhận tin trước khi gọi getUpdates.
Đáp án đúng: B

Câu 5: Ứng dụng tự triển khai endpoint webhook cho Telegram. Endpoint nào phù hợp để Telegram chuyển update tới?
A. Dùng địa chỉ nội bộ không có định tuyến ra ngoài.
B. Dùng endpoint HTTPS mà Telegram truy cập được.
C. Dùng kết nối WebSocket tới cổng của ứng dụng.
D. Dùng endpoint HTTP chỉ mở trong mạng máy chủ.
Đáp án đúng: B

Câu 6: Ứng dụng nhận webhook và đưa tác vụ xử lý vào queue. Khi nào nên phản hồi thành công cho Telegram?
A. Đóng kết nối ngay khi bắt đầu phân tích JSON.
B. Phản hồi trước khi lưu bất kỳ dữ liệu update nào.
C. Đợi mọi công việc nền xong rồi mới phản hồi.
D. Xác nhận sau khi update đã được lưu an toàn.
Đáp án đúng: D

Câu 7: Worker dùng getUpdates để nhận sự kiện nhưng sau khi khởi động lại lại xử lý trùng. Cách kiểm soát nào phù hợp?
A. Đặt offset về số không sau mỗi yêu cầu polling.
B. Đọc lại cùng offset cho mọi lượt polling mới.
C. Dùng offset dựa trên update_id đã xử lý.
D. Chọn offset theo thời gian hiện tại của máy chủ.
Đáp án đúng: C

Câu 8: Một endpoint webhook nhận POST có cấu trúc giống update Telegram. Kiểm tra nào giúp xác thực nguồn gửi?
A. Chỉ xác minh tên bot xuất hiện trong nội dung.
B. Chỉ xác nhận chat_id thuộc nhóm từng sử dụng.
C. Chỉ kiểm tra JSON có trường message và chat_id.
D. Đối chiếu secret token trong header webhook.
Đáp án đúng: D

Câu 9: Bot trong nhóm không nhận mọi tin nhắn thường dù vẫn nhận lệnh gửi cho bot. Yếu tố nào cần rà soát?
A. Chuyển mọi update sang một kênh phát thông báo.
B. Thay chat_id nhóm bằng id của người gửi tin.
C. Nâng hạn mức gửi tin của bot trong nhóm hiện tại.
D. Xem privacy mode và các update bot được phép nhận.
Đáp án đúng: D

Câu 10: Dịch vụ Java/Spring lưu token Bot API để gửi thông báo. Cách quản lý nào phù hợp nhất?
A. Cất token ở kho bí mật phía máy chủ.
B. Lưu token trong JavaScript của trang quản trị.
C. Lưu token trong URL công khai để dễ gọi thử.
D. Lưu token trong log khởi động để dễ tra cứu.
Đáp án đúng: A

Câu 11: Token của bot vô tình xuất hiện trong kho mã công khai. Ưu tiên xử lý nào phù hợp?
A. Chỉ xóa bản ghi log mà vẫn giữ token đã lộ.
B. Thu hồi token đã lộ rồi cấp token mới an toàn.
C. Tạm tắt webhook nhưng giữ nguyên token đã lộ.
D. Đổi username bot rồi tiếp tục sử dụng token cũ.
Đáp án đúng: B

Câu 12: Ứng dụng gửi tên khách vào thông điệp dùng parse_mode HTML. Cách nào giữ định dạng và hạn chế lỗi?
A. Chỉ xóa dấu tiếng Việt trước khi gửi nội dung HTML.
B. Giữ nguyên markup người dùng nhập khi đưa vào HTML.
C. Trộn cú pháp MarkdownV2 vào mọi vị trí của HTML.
D. Escape nội dung động theo định dạng HTML của Bot API.
Đáp án đúng: D

Câu 13: Tin Telegram dùng MarkdownV2 gặp lỗi khi có dấu ngoặc và dấu gạch dưới. Cách xử lý nào hợp lý?
A. Chỉ escape các dấu xuất hiện trong URL của tin.
B. Bỏ qua escape nếu nội dung được mã hóa UTF-8.
C. Đổi mọi dấu câu thành dấu cách trước khi gửi.
D. Escape ký tự đặc biệt theo cú pháp MarkdownV2.
Đáp án đúng: D

Câu 14: Một bot cần gửi cho khách tệp báo cáo giữ nguyên dữ liệu nhị phân, không phải ảnh xem trước. Cách gửi nào phù hợp?
A. Dùng gửi văn bản để truyền toàn bộ byte của tệp.
B. Gửi tệp dưới dạng tài liệu thay vì ảnh.
C. Dùng gửi vị trí để gửi cùng tên và kích thước tệp.
D. Dùng gửi ảnh để giữ nguyên mọi kiểu dữ liệu tệp.
Đáp án đúng: B

Câu 15: Bot gửi ảnh kèm phần mô tả dài vượt giới hạn caption. Thiết kế nào phù hợp?
A. Bật chế độ webhook để tăng kích thước caption.
B. Đổi chat_id để làm tăng giới hạn chữ ở caption.
C. Gửi ảnh và tách mô tả dài thành tin riêng.
D. Chuyển sang MarkdownV2 để nới giới hạn caption.
Đáp án đúng: C

Câu 16: Job gửi tệp lớn qua Telegram Bot API thường bị từ chối. Bước đầu nào phù hợp?
A. Lặp lại upload đến khi máy chủ chấp nhận tệp lớn.
B. Nén mọi loại tệp thành ảnh rồi dùng phương thức gửi ảnh.
C. Kiểm tra giới hạn tải tệp của phương thức gửi.
D. Đổi ngôn ngữ tin nhắn để giảm lỗi tệp lớn.
Đáp án đúng: C

Câu 17: Một worker Spring nhận lỗi 429 khi gửi Telegram. Chính sách retry nào phù hợp nhất?
A. Đổi chat_id của người nhận khi gặp lỗi giới hạn.
B. Tuân thủ retry_after và giảm nhịp gửi tin.
C. Thay parse_mode để yêu cầu tiếp theo chạy nhanh hơn.
D. Gửi lại ngay với nhiều worker để vượt quá thời hạn.
Đáp án đúng: B

Câu 18: Nhiều instance cùng gửi thông báo bằng một bot và vượt hạn mức chung. Cách điều tiết nào phù hợp?
A. Đổi tên bot định kỳ để giảm số lượt bị giới hạn.
B. Mỗi worker đặt giới hạn độc lập mà không chia sẻ.
C. Tăng số worker khi thấy lỗi hạn mức từ Telegram.
D. Điều tiết tốc độ chung cho mọi worker của bot.
Đáp án đúng: D

Câu 19: Bot gửi tin bị timeout sau khi đã gửi request; không rõ Telegram nhận hay chưa. Cách xử lý nào phù hợp?
A. Mặc định coi timeout là chưa gửi rồi retry vô hạn.
B. Mặc định coi timeout là gửi xong và xóa mọi dấu vết.
C. Ghi nhận kết quả chưa rõ và giới hạn retry.
D. Đổi chat_id trước khi retry để tránh lỗi timeout cũ.
Đáp án đúng: C

Câu 20: Một người dùng chặn bot nên yêu cầu gửi tới chat trả lỗi quyền truy cập. Worker nên làm gì?
A. Dừng retry và ghi nhận chat không thể nhận.
B. Chuyển sang webhook để bỏ qua lỗi quyền gửi tin.
C. Thay parse_mode rồi gửi lại ngay cho cùng chat đó.
D. Giảm kích thước tin rồi retry liên tục đến khi đạt.
Đáp án đúng: A

Câu 21: Tin khôi phục mật khẩu bị chờ sau hàng nghìn thông báo ít quan trọng. Thiết kế queue nào phù hợp?
A. Đặt ưu tiên cao hơn cho tin bảo mật cấp thiết.
B. Đẩy quảng cáo trước các tin có tính bảo mật cao.
C. Giữ chung một hàng đợi và tăng số lần thử lại.
D. Gửi tuần tự mọi thông báo theo thời điểm đăng ký.
Đáp án đúng: A

Câu 22: Một sự kiện đơn hàng được phát hai lần khiến cùng thông báo Telegram bị xếp hàng trùng. Cách chống trùng nào phù hợp?
A. So sánh nội dung hiển thị của tin trước khi enqueue.
B. Dùng mã sự kiện nghiệp vụ để ngăn enqueue trùng.
C. Dùng thời gian máy worker tạo làm mã chống trùng.
D. Dùng chat_id làm mã loại bỏ tất cả tin về sau.
Đáp án đúng: B

Câu 23: Nhóm Telegram được chuyển sang loại supergroup và bot không gửi được tới chat_id cũ. Hướng xử lý nào phù hợp?
A. Thay token bot để tiếp tục dùng chat_id cũ.
B. Dùng id người quản trị thay cho chat_id mới.
C. Giữ chat_id cũ vì bot token không thay đổi.
D. Cập nhật chat_id mới từ sự kiện chuyển nhóm.
Đáp án đúng: D

Câu 24: Bot trước đây gửi được trong nhóm nhưng sau đó bị xóa hoặc mất quyền. Cách xử lý nào phù hợp?
A. Kiểm tra lại quyền gửi của bot trong nhóm.
B. Chuyển parse_mode rồi giữ nguyên quyền và chat_id.
C. Tăng timeout rồi tiếp tục gửi lại mà không xét quyền.
D. Giảm độ dài tin để vượt lỗi bot bị xóa khỏi nhóm.
Đáp án đúng: A

Câu 25: Đội vận hành muốn biết kênh Telegram gửi thông báo có khỏe không. Bộ số liệu nào hữu ích nhất?
A. Theo dõi RAM ứng dụng nhưng bỏ qua trạng thái gửi.
B. Theo dõi queue lag, mã lỗi và kết quả gửi.
C. Chỉ theo dõi số lần người dùng mở màn hình thông báo.
D. Chỉ thống kê yêu cầu mới được đưa vào hàng đợi.
Đáp án đúng: B

Câu 26: Thông báo Telegram đôi lúc chứa dữ liệu hồ sơ nhạy cảm. Biện pháp vận hành nào phù hợp?
A. Gửi vào nhóm chung để nhân viên dễ theo dõi lỗi.
B. Giữ tệp đính kèm vô hạn để giảm thời gian hỗ trợ.
C. Giảm dữ liệu nhạy cảm trong tin và nhật ký.
D. Ghi đầy đủ token và nội dung tin vào nhật ký lỗi.
Đáp án đúng: C

Câu 27: Một ứng dụng cần ánh xạ người dùng nội bộ với đúng chat Telegram đã đồng ý nhận tin. Cách nào phù hợp?
A. Dùng id nhóm thử nghiệm cho tất cả người dùng.
B. Dùng tên hiển thị khách hàng làm khóa chat_id.
C. Lấy chat_id từ tương tác đã xác minh với bot.
D. Dùng email người dùng để suy ra chat_id tương ứng.
Đáp án đúng: C

Câu 28: Webhook Telegram gửi lại cùng update sau gián đoạn mạng. Cách xử lý nào giảm tác động lặp?
A. Coi mọi lần webhook được gọi là sự kiện khác nhau.
B. Lọc update_id đã xử lý để tránh thực hiện lặp.
C. Loại bỏ mọi update thuộc cùng một loại thông báo.
D. Thay bot token khi nhận hai update có cùng nội dung.
Đáp án đúng: B

Câu 29: Hệ thống có endpoint HTTPS công khai ổn định và muốn Telegram chủ động đẩy sự kiện. Phương án nào phù hợp?
A. Chọn webhook trên endpoint HTTPS công khai ổn định.
B. Chọn webhook dù server chỉ có kết nối mạng riêng.
C. Chạy webhook và polling cùng lúc để nhân đôi update.
D. Chọn long polling khi cần Telegram gọi vào server.
Đáp án đúng: A

Câu 30: Nhóm bắt đầu tích hợp Telegram Bot API cho ứng dụng Spring và chưa có bot. Bước nào phù hợp để tạo bot?
A. Tạo bot qua BotFather rồi bảo vệ token Bot API.
B. Tạo Channel rồi dùng chat_id của kênh thay token.
C. Lấy username người quản trị làm token của bot.
D. Bật webhook để Telegram tự cấp token cho bot.
Đáp án đúng: A

Câu 31: Trước khi gửi tệp chứa thông tin khách hàng qua Telegram, ứng dụng cần ưu tiên điều gì?
A. Lấy tên hiển thị nhóm làm bằng chứng đúng người nhận.
B. Gửi tệp vào channel công khai để tăng khả năng tải.
C. Kiểm tra đúng chat nhận trước khi gửi tệp nhạy cảm.
D. Đưa tệp vào log trước để đối chiếu khi có sự cố.
Đáp án đúng: C

Câu 32: Bộ kiểm thử tích hợp kênh Telegram hiện chỉ chạy nhánh gửi thành công. Bổ sung nào giúp kiểm tra độ tin cậy?
A. Bổ sung test cho 429, 403, timeout và update lặp.
B. Chỉ chạy thử với một chat cá nhân ở máy dev.
C. Chỉ kiểm tra payload khi không có tệp đính kèm.
D. Chỉ kiểm tra một lần sendMessage thành công.
Đáp án đúng: A
