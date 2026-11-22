# Spring Graphql

GraphQL là cách xây dựng API dựa trên schema, trong đó client chọn chính xác các trường cần lấy thay vì phụ thuộc hoàn toàn vào một tập endpoint cố định. Spring for GraphQL tích hợp cơ chế thực thi GraphQL Java với Spring Boot, giúp ứng dụng Java khai báo hợp đồng dữ liệu, ánh xạ từng trường đến nghiệp vụ và xử lý request qua những giao thức được hỗ trợ.

Module dành cho người đã biết Java, Spring Boot và khái niệm API. Bạn sẽ bắt đầu từ cú pháp schema, các thao tác Query, Mutation và Subscription; tiếp theo cấu hình schema trong Spring Boot, xây resolver với `@QueryMapping`, `@SchemaMapping`, `@MutationMapping`; dùng `@BatchMapping` để hạn chế N+1, thiết kế phân trang, xử lý luồng sự kiện, quyền truy cập và lỗi thực thi. Phạm vi tập trung vào server-side Spring GraphQL, không thay thế kiến thức cơ bản về cơ sở dữ liệu hoặc Spring Security.

Sau tám mốc học, bạn có thể thiết kế một API GraphQL đơn giản, ánh xạ schema tới các dịch vụ Spring, nhận diện vấn đề hiệu năng ở quan hệ lồng nhau và viết kiểm thử bằng `GraphQlTester`. Trọng tâm là hiểu cơ chế và các lựa chọn thiết kế để phát triển API nhất quán, an toàn và dễ kiểm chứng.