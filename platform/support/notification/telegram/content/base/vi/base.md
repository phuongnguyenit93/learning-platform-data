# Support Notification Telegram

Telegram là một kênh thông báo giúp ứng dụng gửi thông tin về sự kiện, cảnh báo và trạng thái xử lý đến cá nhân, nhóm hoặc kênh. Với **Telegram Bot API**, ứng dụng Java/Spring có thể gửi tin nhắn qua HTTPS mà không cần xây dựng giao diện chat riêng. Tuy nhiên, bot phải có quyền tương tác với cuộc trò chuyện đích; việc gửi qua một API bên ngoài cũng đòi hỏi xử lý lỗi, giới hạn tần suất và bảo vệ dữ liệu.

Module dành cho người đã biết Java, HTTP và cấu hình ứng dụng Spring ở mức cơ bản. Lộ trình bắt đầu từ mô hình bot và tạo token với BotFather, tiếp đến xác định `chat_id`, kiểm tra quyền gửi và sử dụng `sendMessage`. Sau đó, người học thiết kế nội dung thông báo, định dạng văn bản an toàn, tích hợp dịch vụ gửi vào ứng dụng, áp dụng hàng đợi và cơ chế retry, cuối cùng là kiểm thử và giám sát.

Sau tám mốc, bạn có thể xây dựng chức năng gửi thông báo Telegram tối thiểu nhưng có thể vận hành: gửi đúng cuộc trò chuyện, không để lộ token, phát hiện lỗi trả về, hạn chế gửi trùng và theo dõi kết quả. Phạm vi tập trung vào **thông báo đi từ ứng dụng**, không mở rộng sang toàn bộ tính năng bot hội thoại hay Telegram Mini Apps.