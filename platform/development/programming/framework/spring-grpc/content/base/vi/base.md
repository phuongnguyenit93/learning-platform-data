# Spring Grpc

Spring gRPC giúp xây dựng dịch vụ giao tiếp từ xa bằng gRPC trong ứng dụng Spring, tận dụng Protocol Buffers để mô tả dữ liệu và API theo hợp đồng rõ ràng. Khác với REST/JSON thường dùng, gRPC sử dụng HTTP/2, mã hóa nhị phân và hỗ trợ nhiều dạng streaming. Module tập trung vào cách tạo, gọi và kiểm tra một dịch vụ gRPC bằng Java và hệ sinh thái Spring.

Người học nên biết Java, Spring Boot và khái niệm client–server. Lộ trình bắt đầu từ gRPC và file `.proto`, tiếp theo là sinh mã Java bằng công cụ build, triển khai server với `BindableService`, cấu hình client qua `GrpcChannelFactory`, và xử lý unary/streaming RPC. Những phần cuối đề cập đến status, deadline, metadata, bảo mật kết nối và kiểm thử in-process cùng quan sát vận hành.

Hoàn thành module, bạn có thể thiết kế hợp đồng RPC, triển khai và gọi dịch vụ gRPC trong Spring, kiểm soát luồng phản hồi và lỗi, đồng thời tổ chức các kiểm thử nhằm bảo đảm client/server tương thích. Khi cấu hình thực tế, hãy chọn dependency và API đúng với phiên bản Spring Boot và Spring gRPC đang sử dụng.