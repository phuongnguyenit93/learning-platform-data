# Spring Modulith Verification Testing

Spring Modulith giúp tổ chức một ứng dụng Spring Boot thành các module nghiệp vụ có ranh giới rõ ràng. Việc xác minh kiến trúc kiểm tra xem mã nguồn có tuân thủ ranh giới ấy hay không; kiểm thử tích hợp theo module lại xác nhận hành vi mà không cần khởi tạo mọi thành phần của ứng dụng. Kết hợp hai việc này giúp phát hiện sớm các phụ thuộc sai và hồi quy khi hệ thống phát triển.

Module dành cho người đã biết Spring Boot, JUnit và khái niệm dependency injection. Bạn sẽ học cách xây dựng mô hình `ApplicationModules`, kiểm tra chu trình phụ thuộc, phạm vi API và `allowedDependencies`; phân tích vi phạm bằng `verify()` và `detectViolations()`; rồi viết test với `@ApplicationModuleTest`, chọn chế độ bootstrap, cô lập bean bên ngoài module và dùng `Scenario` để kiểm chứng tương tác qua sự kiện.

Lộ trình có tám mốc, kết thúc bằng việc đưa các phép kiểm tra kiến trúc và hành vi module vào quy trình regression/CI. Sau khi hoàn thành, bạn có thể viết bài kiểm chứng ranh giới module, chọn phạm vi integration test thích hợp và nhận diện nguyên nhân khi thay đổi mã làm hỏng kiến trúc hoặc hành vi liên module.