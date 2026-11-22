# Code Quality Static Analysis Fundamentals — Nền tảng phân tích tĩnh

Phân tích tĩnh (*static analysis*) là quá trình kiểm tra mã nguồn, biểu diễn cú pháp hoặc bytecode mà không cần thực thi ứng dụng. Các công cụ sử dụng quy tắc và những kỹ thuật phân tích khác nhau để chỉ ra lỗi tiềm ẩn, nguy cơ bảo mật và vấn đề về khả năng bảo trì. Kết quả là các cảnh báo cần được đánh giá trong ngữ cảnh dự án; chúng không tự động chứng minh có lỗi thực tế.

Module này phù hợp với người học đã có kiến thức lập trình Java cơ bản và muốn xây dựng tư duy kiểm soát chất lượng mã từ sớm. Lộ trình đi từ mục đích, đầu vào và cơ chế phân tích đến các nhóm quy tắc, giới hạn của công cụ, cách đọc báo cáo và xác định mức độ ưu tiên. Người học sẽ tập phân biệt cảnh báo hữu ích với trường hợp nhiễu hoặc bị bỏ sót, thay vì chỉ dựa vào số lượng cảnh báo.

Ở phần cuối, bạn sẽ thực hành quy trình xem xét, sửa và xác minh cảnh báo, quản lý baseline cùng suppression có lý do, rồi xác định cách tích hợp phân tích tĩnh vào IDE, build và CI. Sau module, bạn có thể đọc hiểu kết quả phân tích, lựa chọn hướng xử lý phù hợp và duy trì việc kiểm tra theo sự thay đổi của mã nguồn.