# Spring HATEOAS

Spring HATEOAS hỗ trợ xây dựng REST API theo nguyên lý *Hypermedia as the Engine of Application State* (HATEOAS): ngoài dữ liệu, phản hồi còn mô tả những tài nguyên liên quan và các hành động khả dụng qua liên kết. Cách tiếp cận này giúp client khám phá API dựa trên quan hệ liên kết thay vì phụ thuộc hoàn toàn vào URL viết sẵn.

Module dành cho người đã có nền tảng Spring MVC, REST và HTTP. Bạn sẽ đi từ nguyên lý hypermedia, `Link` và `LinkRelation`, đến tạo link từ controller, thiết kế `RepresentationModel` cho tài nguyên đơn, danh sách và trang, tái sử dụng assembler, biểu diễn HAL và affordances, rồi kiểm thử khả năng điều hướng của client. Sau lộ trình, bạn có thể xây dựng API Spring có phản hồi hypermedia rõ ràng và kiểm chứng được.