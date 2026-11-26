Khi quản lý máy chủ development, staging và production có địa chỉ thường xuyên thay đổi, bạn sẽ thiết kế inventory tĩnh hoặc động, nhóm host và phạm vi chạy playbook như thế nào để tránh tác động nhầm môi trường?
Nếu Ansible kết nối SSH thành công nhưng task cài gói hệ thống thất bại vì thiếu quyền, bạn sẽ chẩn đoán tài khoản kết nối, become, phương thức nâng quyền và quyền trên máy đích ra sao?
Bạn giải thích tính idempotent trong Ansible như thế nào và sẽ kiểm chứng một playbook chạy lặp lại không tạo thay đổi ngoài ý muốn, đặc biệt khi có task dùng command hoặc shell, ra sao?
Với yêu cầu cập nhật cấu hình một dịch vụ rồi chỉ khởi động lại khi nội dung thật sự thay đổi, bạn sẽ phối hợp module quản lý tệp, template Jinja2 và handler như thế nào?
Khi cùng một biến được khai báo trong role defaults, group_vars, host_vars và extra vars, bạn sẽ phân tích thứ tự ưu tiên và truy tìm nguyên nhân giá trị thực tế khác dự kiến như thế nào?
Bạn sử dụng facts, biến của từng host và biểu thức Jinja2 như thế nào để sinh cấu hình riêng cho nhiều máy, đồng thời xử lý dữ liệu thiếu hoặc giá trị không hợp lệ trước khi ghi tệp?
Trong dự án có nhiều playbook cùng dùng cấu hình web server và database, bạn sẽ tổ chức roles, collections, dependency và phiên bản thành phần ra sao để dễ tái sử dụng, kiểm thử và nâng cấp an toàn?
Khi playbook phải phân phối mật khẩu hoặc khóa riêng đến máy chủ, bạn sẽ sử dụng Ansible Vault và các biện pháp bảo vệ log, tệp tạm, quyền truy cập cùng quy trình luân chuyển bí mật như thế nào?
Trước khi áp dụng một thay đổi lớn lên production, bạn sẽ phối hợp kiểm tra cú pháp, check mode, diff mode và chạy thử trên staging như thế nào, kể cả với những task không hỗ trợ mô phỏng đầy đủ?
Nếu cần cập nhật cấu hình trên hàng trăm máy đang phục vụ lưu lượng, bạn sẽ lựa chọn serial, forks, giới hạn host và kiểm tra sức khỏe theo từng đợt ra sao để hạn chế gián đoạn dịch vụ?
Khi một task cấu hình thất bại giữa playbook nhưng cần thu thập thông tin chẩn đoán và dọn dẹp tài nguyên, bạn sẽ vận dụng block, rescue, always cùng điều kiện xác định failed hoặc changed như thế nào?
Nếu máy chủ bị chỉnh sửa cấu hình thủ công sau nhiều tuần vận hành, bạn sẽ phát hiện drift, xác định nguyên nhân và thiết kế lịch chạy Ansible cùng cơ chế kiểm toán như thế nào để đưa hạ tầng về trạng thái mong muốn?
