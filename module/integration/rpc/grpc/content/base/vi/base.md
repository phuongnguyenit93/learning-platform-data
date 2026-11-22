# Integration Rpc gRPC

gRPC là mô hình giao tiếp Remote Procedure Call (RPC) giúp một dịch vụ gọi phương thức của dịch vụ khác thông qua hợp đồng xác định trước. Với Protocol Buffers và HTTP/2, gRPC hỗ trợ dữ liệu nhị phân, sinh mã client/server và cả giao tiếp dạng streaming. Module này tập trung vào tích hợp giữa các ứng dụng Java, từ thiết kế hợp đồng `.proto` đến triển khai dịch vụ, kết nối client và xử lý các tình huống mạng thực tế; không phụ thuộc riêng vào Spring.

Bạn nên biết Java, kiến thức mạng client–server và cách dùng Gradle hoặc Maven. Lộ trình bắt đầu bằng so sánh RPC với các kiểu tích hợp khác, sau đó định nghĩa protobuf, sinh stub, xây dựng unary server/client và mở rộng sang streaming. Các phần cuối đi vào deadline, status, TLS, metadata, kiểm thử tích hợp và quan sát vận hành.

Hoàn thành module, bạn có thể thiết kế một gRPC service, tạo Java stub, xây dựng luồng gọi client–server và kiểm tra các loại RPC cơ bản. Bạn cũng biết cách đặt giới hạn thời gian, xử lý lỗi đúng ngữ nghĩa và duy trì tương thích hợp đồng khi nhiều hệ thống cùng sử dụng API.