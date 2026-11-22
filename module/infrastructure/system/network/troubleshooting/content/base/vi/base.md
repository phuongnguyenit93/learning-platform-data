# Network Troubleshooting

Network Troubleshooting là quá trình tìm và xử lý nguyên nhân khiến các thiết bị hoặc ứng dụng không thể kết nối, kết nối chậm hay hoạt động thiếu ổn định. Cách tiếp cận hiệu quả bắt đầu bằng việc mô tả triệu chứng và phạm vi ảnh hưởng, sau đó kiểm tra từng lớp liên quan để phân biệt sự cố liên kết, địa chỉ IP, định tuyến, DNS, giao thức vận chuyển và dịch vụ ứng dụng.

Module dành cho lập trình viên, người vận hành và người học đã biết kiến thức mạng cơ bản như TCP/IP, địa chỉ IP và mô hình client–server. Nội dung chú trọng tư duy kiểm chứng bằng bằng chứng: xác lập điểm xuất phát và điểm đích, chạy phép thử phù hợp, đọc kết quả có giới hạn và không vội kết luận từ một công cụ đơn lẻ. Ví dụ, ping thất bại chưa đủ chứng minh máy đích mất kết nối vì ICMP có thể bị lọc.

Lộ trình bắt đầu từ khoanh vùng triệu chứng và kiểm tra kết nối, tiếp theo là IP/route, DNS, đường đi, TCP/UDP, TLS và tầng ứng dụng. Cuối cùng, người học dùng bắt gói và đối chiếu thời gian, lỗi, độ trễ để xác định nguyên nhân gốc, thực hiện thay đổi có kiểm soát và kiểm tra lại kết quả.