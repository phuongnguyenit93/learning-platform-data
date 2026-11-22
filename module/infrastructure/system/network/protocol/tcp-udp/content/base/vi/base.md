# Network Protocol TCP - UDP

TCP (Transmission Control Protocol) và UDP (User Datagram Protocol) là hai giao thức vận chuyển phổ biến trong mạng IP. TCP cung cấp luồng byte có kết nối, truyền theo thứ tự và khôi phục dữ liệu bị mất; UDP chuyển datagram với cơ chế tối giản, không tự bảo đảm truyền đủ hay đúng thứ tự. Hiểu hai mô hình giúp lập trình viên chọn giao thức phù hợp và đọc đúng hiện tượng mạng thay vì suy đoán từ lỗi ứng dụng.

Module đi từ tầng vận chuyển, port và socket đến cấu trúc UDP, vòng đời kết nối TCP, cơ chế sequence/acknowledgment và retransmission. Bạn tiếp tục phân biệt flow control với congestion control, cân nhắc các đánh đổi khi dùng TCP hoặc UDP, rồi thực hành đọc gói tin để chẩn đoán kết nối chậm, timeout và mất dữ liệu. QUIC được nhắc đến như ví dụ giao thức xây trên UDP với các cơ chế riêng.

Lộ trình phù hợp với lập trình viên và kỹ sư vận hành đã biết địa chỉ IP và khái niệm client/server cơ bản. Sau khi hoàn thành, bạn có thể giải thích sự khác nhau giữa TCP và UDP, diễn giải các dấu hiệu trong packet capture và lựa chọn chiến lược giao tiếp dựa trên độ tin cậy, độ trễ và yêu cầu ứng dụng.