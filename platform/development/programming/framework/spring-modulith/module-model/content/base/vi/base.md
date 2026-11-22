# Spring Modulith Module Model

Spring Modulith giúp tổ chức một ứng dụng Spring Boot thành các mô-đun nghiệp vụ có ranh giới và giao diện rõ ràng ngay trong cùng một ứng dụng. *Module Model* là cách Spring Modulith nhận diện những mô-đun đó từ cấu trúc package và cấu hình, đồng thời mô tả API công khai, phần triển khai nội bộ và phụ thuộc giữa chúng. Module học này dành cho người đã quen Java, Spring Boot và cấu trúc package.

Bạn sẽ bắt đầu từ việc chọn ranh giới nghiệp vụ, tổ chức package và đọc mô hình thông qua `ApplicationModules`. Tiếp đó là cách đóng gói API và mã nội bộ, công bố thêm API bằng `@NamedInterface`, giới hạn phụ thuộc với `@ApplicationModule`, rồi tìm hiểu mô-đun lồng nhau, mô-đun mở và chiến lược phát hiện tùy chỉnh.

Kết thúc lộ trình, bạn có thể phác thảo cấu trúc mô-đun cho một ứng dụng, giải thích quyền truy cập giữa các phần và sử dụng mô hình Spring Modulith để kiểm tra xem cấu trúc package có phản ánh đúng thiết kế hay không. Đây là nền tảng cho các bước kiểm chứng kiến trúc, kiểm thử mô-đun và tài liệu hóa sau này.