# Integration HTTP Request Response Client

**HTTP Request–Response Client** là phần ứng dụng chủ động gửi yêu cầu đến một dịch vụ HTTP, nhận phản hồi và chuyển kết quả thành dữ liệu hoặc lỗi có nghĩa với nghiệp vụ. Thiết kế client không chỉ là gọi một URL: cần hiểu method, status, headers, payload, cơ chế xác thực và giới hạn của kết nối để việc tích hợp chính xác, an toàn và dễ bảo trì.

Lộ trình gồm **8 mốc**: nắm hợp đồng HTTP; xây URI, query và headers; sử dụng Java HttpClient; chọn Spring RestClient hoặc WebClient; xử lý JSON và bảo mật; ánh xạ response và lỗi; thiết lập timeout, retry an toàn; cuối cùng là kiểm thử và quan sát. Người học thực hành tích hợp một API mẫu, thử response bất thường và mô phỏng dịch vụ chậm hoặc không sẵn sàng.

Học phần phù hợp với Java developer đã biết HTTP, JSON, đối tượng Java và lập trình ứng dụng cơ bản. Sau khi hoàn thành, bạn có thể xây HTTP client có cấu trúc rõ ràng, gọi API đồng bộ hoặc bất đồng bộ theo nhu cầu, bảo vệ credentials, xử lý lỗi và retry phù hợp, cũng như kiểm chứng hành vi bằng mock server và các chỉ số vận hành.