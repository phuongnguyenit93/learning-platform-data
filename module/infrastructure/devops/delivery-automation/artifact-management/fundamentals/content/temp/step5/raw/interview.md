Bạn hiểu artifact trong quy trình CI/CD là gì, và JAR, package cùng container image khác nhau ra sao về cách đóng gói, lưu trữ và sử dụng?
Bạn sẽ xây dựng quy ước định danh và đánh phiên bản cho artifact như thế nào để mỗi lần build truy xuất đúng một đầu ra cụ thể?
Điều gì có thể xảy ra khi ghi đè một phiên bản đã công bố hoặc triển khai bằng tag `latest`, và bạn sẽ bảo đảm tính bất biến của artifact bằng cách nào?
Bạn sẽ tổ chức kho artifact và container registry ra sao để tách bản thử nghiệm với bản phát hành, phân quyền truy cập và hỗ trợ nhiều định dạng package?
Sau khi CI tạo ra artifact, bạn sẽ đặt những điều kiện kiểm tra và quy trình công bố nào để tránh phát hành đầu ra chưa đạt chất lượng hoặc upload dở dang?
Khi một deployment tải artifact về, bạn sẽ xác minh tính toàn vẹn, tính xác thực và đúng nội dung cần chạy như thế nào?
Bạn sẽ ghi nhận và kiểm chứng thông tin nguồn gốc của artifact như thế nào để truy ra commit, job CI, môi trường build và bản phát hành liên quan?
Bạn sẽ tạo, gắn và lưu SBOM của một artifact ở đâu trong quy trình, và làm thế nào để bảo đảm SBOM luôn khớp với artifact tương ứng?
Giả sử một thành phần phụ thuộc có lỗ hổng mới được công bố, bạn sẽ dùng SBOM và dữ liệu artifact để tìm các bản phát hành bị ảnh hưởng và xử lý ra sao?
Khi registry dùng cache hoặc mirror để phân phối container image tới nhiều môi trường, bạn sẽ kiểm soát điều gì để tránh tải sai phiên bản hoặc dùng dữ liệu cũ?
Bạn sẽ xây dựng chính sách lưu giữ và dọn dẹp artifact thế nào để tiết kiệm dung lượng nhưng vẫn đáp ứng rollback, kiểm toán và khả năng tái triển khai?
Bạn sẽ thiết kế promotion từ staging sang production như thế nào để dùng chính artifact đã vượt qua kiểm thử, và sẽ điều tra ra sao nếu production chạy nội dung khác staging?
