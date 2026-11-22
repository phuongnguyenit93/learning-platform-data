# Spring Rest Docs

Spring REST Docs giúp tạo tài liệu REST API từ các kiểm thử HTTP thực tế. Thay vì chỉ mô tả endpoint bằng tay, công cụ sinh những snippet về request, response, tham số và trường dữ liệu từ các test sử dụng Spring MVC Test (MockMvc) hoặc WebTestClient. Những snippet này được kết hợp với nội dung giải thích để tạo tài liệu chính xác, dễ đọc và gắn với hành vi API.

Module phù hợp với người đã nắm Java, Spring Web và kiểm thử HTTP cơ bản. Lộ trình bắt đầu từ cách REST Docs hoạt động, cấu hình dependency và build, rồi thiết lập test sinh snippet. Tiếp đó, bạn mô tả request/response, ghép snippet vào Asciidoctor để xuất HTML, và vận hành bước kiểm tra tài liệu trong CI.

Sau khi học, bạn có thể xây dựng tài liệu cho một REST endpoint thông qua kiểm thử, xác định thay đổi payload khiến test tài liệu thất bại, đồng thời duy trì tài liệu API nhất quán với mã nguồn mà không phải cập nhật ví dụ HTTP thủ công ở nhiều nơi.