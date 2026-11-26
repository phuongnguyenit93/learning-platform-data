Bạn giải thích cách GitLab CI đọc file .gitlab-ci.yml để tạo job và stage, và khi nào bạn dùng needs để thay đổi thứ tự chạy mặc định giữa các stage?
Với repository có push lên nhánh, merge request và Git tag, bạn thiết kế workflow:rules cùng rules của từng job thế nào để chạy đúng loại pipeline và tránh tạo pipeline trùng?
Bạn lựa chọn runner, executor và runner tag cho các job build, test và deploy dựa trên tiêu chí nào về tài nguyên, khả năng tái lập và mức độ tin cậy của mã nguồn?
Khi một job liên tục ở trạng thái pending dù pipeline đã được tạo, bạn sẽ kiểm tra runner, tag, quyền chạy và cấu hình job theo trình tự nào để tìm nguyên nhân?
Bạn tổ chức các template dùng chung trong .gitlab-ci.yml bằng include, extends hoặc cấu hình tái sử dụng như thế nào để nhiều dự án cập nhật pipeline nhất quán mà vẫn dễ kiểm soát thay đổi?
Bạn thiết kế các job build và kiểm thử tự động như thế nào để merge request nhận được phản hồi sớm, báo cáo kiểm thử hữu ích và chặn việc hợp nhất khi cổng chất lượng không đạt?
Bạn phân biệt cache với artifact trong GitLab CI ra sao và sẽ cấu hình phạm vi, thời hạn lưu cùng cách truyền kết quả giữa các job thế nào để tránh sử dụng dữ liệu cũ?
Bạn xây dựng bước đóng gói và xuất bản artifact hoặc container image như thế nào để liên kết chính xác phiên bản được phát hành với commit, pipeline và kết quả kiểm thử đã tạo ra nó?
Bạn bảo vệ token, khóa triển khai và các biến nhạy cảm trong GitLab CI như thế nào khi có nhiều nhánh, môi trường và runner với mức độ tin cậy khác nhau?
Nếu dự án nhận merge request từ fork bên ngoài, bạn thiết kế pipeline kiểm tra mã và quyền truy cập tài nguyên như thế nào để vẫn kiểm thử được thay đổi mà không làm lộ bí mật phát hành?
Bạn thiết kế quy trình triển khai từ staging đến production bằng GitLab environments và các bước phê duyệt như thế nào để dùng lại đúng artifact đã kiểm thử và kiểm soát người được phép phát hành?
Khi bản triển khai production vừa hoàn tất nhưng kiểm tra sức khỏe thất bại, bạn sẽ dùng kết quả pipeline, lịch sử deployment và tín hiệu giám sát như thế nào để quyết định dừng, quay lui và xác minh dịch vụ đã phục hồi?
