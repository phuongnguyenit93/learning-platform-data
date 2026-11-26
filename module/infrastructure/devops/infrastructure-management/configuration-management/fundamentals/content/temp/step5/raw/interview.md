Khi quản lý hàng trăm máy chủ, bạn sẽ mô tả trạng thái mong muốn của gói phần mềm, tệp cấu hình và dịch vụ như thế nào, và làm sao xác nhận trạng thái thực tế đã khớp với mô tả?
Tính idempotency trong tự động hóa cấu hình là gì, và bạn sẽ phát hiện trường hợp một bước vô tình ghi lại tệp hoặc khởi động lại dịch vụ ở mọi lần chạy như thế nào?
Nếu quá trình áp dụng cấu hình bị ngắt giữa chừng vì mất kết nối, bạn sẽ thiết kế cơ chế hội tụ và xử lý thứ tự phụ thuộc như thế nào để lần chạy sau đưa hệ thống về trạng thái mong muốn?
Bạn sẽ xây dựng inventory cho các máy chủ thuộc nhiều nhóm và liên tục thay đổi số lượng như thế nào để chọn đúng đích triển khai và tránh tác động nhầm môi trường production?
Khi giá trị cấu hình được khai báo ở mức chung, môi trường, nhóm máy và từng máy, bạn sẽ xác định quy tắc ưu tiên và truy tìm nguồn gốc giá trị cuối cùng như thế nào?
Bạn sẽ thiết kế, kết xuất và kiểm chứng template cấu hình dịch vụ như thế nào để xử lý khác biệt giữa môi trường, tránh lỗi cú pháp và chỉ khởi động lại dịch vụ khi nội dung thực sự thay đổi?
Nếu ứng dụng phải nhận mật khẩu cơ sở dữ liệu qua hệ thống quản lý cấu hình, bạn sẽ tổ chức lưu trữ, cấp phát, che giấu và xoay vòng bí mật thế nào để giá trị nhạy cảm không xuất hiện trong mã nguồn, log hoặc bản kiểm tra thay đổi?
Bạn sẽ thiết kế bộ kiểm thử thay đổi cấu hình ra sao, từ kiểm tra tĩnh và mô phỏng thay đổi đến chạy trên môi trường thử nghiệm và xác nhận dịch vụ hoạt động đúng?
Khi một quản trị viên sửa trực tiếp cấu hình trên máy production, bạn sẽ phát hiện drift, xác định nguyên nhân và quyết định thời điểm tự động hòa giải với trạng thái mong muốn như thế nào?
Trước khi triển khai thay đổi tường lửa hoặc SSH trên hàng trăm máy chủ, bạn sẽ chọn chiến lược triển khai theo đợt, kiểm tra sức khỏe và kế hoạch khôi phục thế nào để giảm nguy cơ mất quyền quản trị?
Bạn sẽ tổ chức quản lý phiên bản, rà soát thay đổi và truy vết người phê duyệt cho inventory, template và biến cấu hình như thế nào để có thể kiểm toán và phục hồi một phiên bản cấu hình trước đó?
Nếu hai quy trình tự động cùng quản lý một tệp hoặc dịch vụ và liên tục đảo ngược thay đổi của nhau, bạn sẽ chẩn đoán xung đột quyền sở hữu và thiết kế cách phối hợp để tránh vòng lặp cấu hình như thế nào?
