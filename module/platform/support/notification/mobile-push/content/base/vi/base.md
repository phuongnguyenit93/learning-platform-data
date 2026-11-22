# Support Notification Mobile Push

Mobile Push Notification là cơ chế đưa thông tin từ hệ thống đến ứng dụng di động thông qua dịch vụ thông báo của nền tảng, phổ biến là Firebase Cloud Messaging (FCM) và Apple Push Notification service (APNs). Module này tập trung vào việc thiết kế luồng gửi từ backend, quản lý người nhận và xử lý thông báo ở thiết bị sao cho an toàn, có thể kiểm chứng và tôn trọng lựa chọn của người dùng.

Lộ trình gồm tám mốc: kiến trúc FCM/APNs, thiết lập dịch vụ, xin quyền nhận thông báo, quản lý định danh thiết bị, thiết kế payload và xử lý trong ứng dụng, nhắm đích từ backend, bảo đảm độ tin cậy/bảo mật và quan sát/kiểm thử. Người học sẽ nhận diện sự khác biệt giữa việc dịch vụ push chấp nhận yêu cầu gửi và việc thông báo thực sự xuất hiện trên thiết bị; từ đó thiết kế retry, cập nhật đăng ký và theo dõi lỗi phù hợp.

Module phù hợp với lập trình viên backend hoặc mobile đã biết HTTP API, JSON và khái niệm xác thực cơ bản. Sau khi học, bạn có thể xây dựng một luồng push đơn giản, gửi đúng nhóm thiết bị, xử lý tình huống quyền bị từ chối hoặc thiết bị mất kết nối, tránh lộ dữ liệu nhạy cảm và kiểm tra các tín hiệu giao nhận để hỗ trợ vận hành.