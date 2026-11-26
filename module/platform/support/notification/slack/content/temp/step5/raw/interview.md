Bạn sẽ xác định khi nào dùng Slack làm kênh cảnh báo ứng dụng thay vì email hoặc giao diện giám sát như thế nào?
Bạn sẽ phân biệt Incoming Webhooks với Slack Web API khi cần gửi thông báo tới nhiều channel hoặc thread ra sao?
Bạn sẽ mô tả cách cấu hình một Incoming Webhook cho workspace và quản lý URL bí mật của nó như thế nào?
Bạn sẽ xác định giới hạn về channel và hành vi của Incoming Webhook trước khi thiết kế cơ chế định tuyến linh hoạt ra sao?
Bạn sẽ lựa chọn Web API khi cần chọn channel đích, quản lý phản hồi hoặc cập nhật tin nhắn như thế nào?
Bạn sẽ thiết kế interface thông báo trong Java/Spring để tách logic nghiệp vụ khỏi Slack SDK và HTTP client ra sao?
Bạn sẽ tổ chức cấu hình webhook, bot token và channel ID theo môi trường triển khai như thế nào?
Bạn sẽ giải thích sự khác nhau giữa tên hiển thị channel và định danh channel khi lưu cấu hình định tuyến ra sao?
Bạn sẽ xử lý việc channel bị đổi tên, lưu trữ hoặc bot bị xóa khỏi channel mà không làm gián đoạn luồng nghiệp vụ chính như thế nào?
Bạn sẽ xác định quyền và phạm vi truy cập cần thiết của Slack app theo đúng chức năng gửi thông báo ra sao?
Bạn sẽ kiểm tra điều kiện thành viên của bot trong channel riêng tư trước khi gửi thông báo như thế nào?
Bạn sẽ phân biệt kênh cảnh báo vận hành, kênh thông báo nghiệp vụ và tin nhắn dành cho người chịu trách nhiệm như thế nào?
Bạn sẽ xây dựng quy tắc định tuyến theo môi trường, dịch vụ nguồn và mức độ nghiêm trọng của sự kiện ra sao?
Bạn sẽ hạn chế thông báo ở workspace sản xuất xuất hiện trong kênh thử nghiệm hoặc ngược lại như thế nào?
Bạn sẽ thiết kế nội dung thông báo có tiêu đề, mức độ ảnh hưởng, thời gian và liên kết điều tra để người nhận hành động nhanh ra sao?
Bạn sẽ xử lý các trường dữ liệu động có ký tự đặc biệt để chúng không làm sai cách Slack diễn giải nội dung mrkdwn như thế nào?
Bạn sẽ chọn khi nào dùng văn bản thông thường và khi nào dùng Block Kit để cấu trúc thông báo ra sao?
Bạn sẽ lựa chọn các block, section và phần ngữ cảnh phù hợp để một cảnh báo vừa dễ đọc vừa không quá dài như thế nào?
Bạn sẽ thiết kế phần văn bản dự phòng của tin nhắn có Block Kit để người dùng công nghệ hỗ trợ vẫn nắm nội dung chính ra sao?
Bạn sẽ kiểm soát giới hạn kích thước và số block để Slack không từ chối một thông báo có quá nhiều dữ liệu ra sao?
Bạn sẽ tổ chức các mẫu Block Kit tái sử dụng theo loại sự kiện mà không gắn chặt chúng vào lớp nghiệp vụ như thế nào?
Bạn sẽ xác minh nội dung Block Kit trước khi gửi và kiểm thử khả năng hiển thị ở giao diện Slack như thế nào?
Bạn sẽ quyết định khi nào cần gửi tin nhắn mới thay vì trả lời vào thread của một sự cố đang tồn tại ra sao?
Bạn sẽ sử dụng timestamp của tin nhắn gốc làm thông tin tham chiếu để gửi phản hồi vào đúng thread như thế nào?
Bạn sẽ lưu liên kết giữa mã sự cố và thread để các cập nhật tiếp theo không tạo nhiều cuộc thảo luận rời rạc ra sao?
Bạn sẽ xử lý trường hợp không còn tìm thấy tin nhắn gốc hoặc thread đích không còn khả dụng như thế nào?
Bạn sẽ phân biệt thông báo yêu cầu phản hồi ngay với cập nhật tiến trình nên được gom vào thread ra sao?
Bạn sẽ tổ chức thao tác gửi bằng Slack SDK hoặc HTTP client để quản lý timeout, kết nối và parse phản hồi như thế nào?
Bạn sẽ phân biệt phản hồi của Incoming Webhook với cấu trúc thành công hoặc thất bại của Slack Web API ra sao?
Bạn sẽ phân loại lỗi token không hợp lệ, thiếu quyền, channel không tồn tại và lỗi tạm thời để quyết định retry như thế nào?
Bạn sẽ sử dụng HTTP 429 và thông tin Retry-After để trì hoãn lần gửi tiếp theo an toàn ra sao?
Bạn sẽ thiết kế backoff có jitter và giới hạn số lần thử để tránh nhiều worker cùng đẩy lại tin nhắn như thế nào?
Bạn sẽ kiểm soát giới hạn tốc độ theo phương thức và đích nhận khi một ứng dụng gửi cảnh báo với lưu lượng cao như thế nào?
Bạn sẽ thiết kế hàng đợi thông báo để nghiệp vụ không phải chờ Slack trả lời trong cùng một transaction ra sao?
Bạn sẽ dùng khóa chống trùng để giảm nguy cơ cùng một sự kiện được gửi nhiều lần do lỗi mạng hoặc retry như thế nào?
Bạn sẽ xác định cách xử lý khi Slack đã nhận tin nhưng backend mất phản hồi nên không biết có nên gửi lại hay không ra sao?
Bạn sẽ lựa chọn chính sách hết hạn cho cảnh báo không còn giá trị thay vì giữ chúng trong hàng đợi vô hạn như thế nào?
Bạn sẽ gộp những cảnh báo trùng nguyên nhân mà vẫn phản ánh được số lần lặp và mức độ nghiêm trọng như thế nào?
Bạn sẽ thiết kế cơ chế tạm ngưng hoặc giảm tần suất cảnh báo đã được xác nhận để tránh gây nhiễu channel như thế nào?
Bạn sẽ bảo vệ webhook URL và bot token trong hệ thống quản lý bí mật, log và cấu hình CI như thế nào?
Bạn sẽ xử lý quy trình thu hồi và thay thế token khi một thông tin xác thực Slack bị lộ ra sao?
Bạn sẽ bảo đảm nội dung thông báo không chứa dữ liệu cá nhân, token hoặc thông tin vận hành vượt quyền người đọc channel như thế nào?
Bạn sẽ theo dõi tỷ lệ gửi thành công, lỗi quyền, giới hạn tốc độ và độ trễ hàng đợi thông báo bằng những chỉ số nào?
Bạn sẽ liên kết mã sự kiện với yêu cầu gửi và phản hồi Slack để truy vết mà không ghi toàn bộ nội dung nhạy cảm như thế nào?
Bạn sẽ viết unit test cho bộ định tuyến channel, tạo Block Kit và chính sách retry mà không gọi Slack thật ra sao?
Bạn sẽ dùng HTTP stub để kiểm thử phản hồi lỗi của Web API, webhook và xử lý giới hạn tốc độ như thế nào?
Bạn sẽ kiểm thử tích hợp với workspace thử nghiệm để xác nhận quyền bot, channel và định dạng tin nhắn trước khi triển khai như thế nào?
Bạn sẽ đánh giá hệ thống cảnh báo bằng mức độ hữu ích, tỷ lệ phản hồi và lượng thông báo bị bỏ qua thay vì chỉ đếm số tin đã gửi ra sao?
Bạn sẽ điều tra tình huống API phản hồi thành công nhưng nhóm trực ca không thấy cảnh báo ở channel hoặc thread mong đợi như thế nào?
Bạn sẽ thiết kế phương án dự phòng khi Slack tạm gián đoạn để các cảnh báo quan trọng vẫn được lưu và chuyển đến đúng người như thế nào?
