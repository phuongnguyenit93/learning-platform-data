Bạn xác định những ranh giới tin cậy nào giữa mã nguồn, định nghĩa workflow, runner, kho artifact và môi trường triển khai để xây dựng mô hình mối đe dọa cho pipeline CI/CD?
Khi pipeline chạy cho pull request từ fork bên ngoài, bạn thiết kế sự kiện kích hoạt, quyền của token và phạm vi secrets như thế nào để kiểm thử thay đổi mà không trao quyền phát hành cho mã chưa được tin cậy?
Bạn sẽ bảo vệ việc sửa file workflow và các script CI bằng cơ chế xét duyệt mã, bảo vệ nhánh và kiểm toán thay đổi như thế nào để hạn chế kẻ tấn công sửa quy trình build?
Bạn lựa chọn runner dùng chung hay runner chuyên biệt và thiết lập cơ chế cô lập, dọn trạng thái sau job như thế nào để một job độc hại không ảnh hưởng đến các lần build hoặc môi trường khác?
Khi pipeline cần đẩy artifact lên registry và triển khai lên cloud, bạn cấp quyền tối thiểu và thiết kế xác thực bằng thông tin định danh ngắn hạn thay cho thông tin xác thực tồn tại lâu dài như thế nào?
Bạn xây dựng quy trình quản lý secrets từ cấp phát, sử dụng trong job đến luân chuyển và thu hồi ra sao, đồng thời kiểm tra nguy cơ lộ thông tin qua log, biến môi trường hoặc artifact như thế nào?
Bạn kiểm soát nguồn gốc, phiên bản và tính toàn vẹn của action, plugin, container image và dependency mà workflow tải từ bên ngoài bằng những tiêu chí nào?
Nếu job kiểm thử trên nhánh không đáng tin cậy dùng chung cache với job phát hành, bạn sẽ phân tích nguy cơ đầu độc cache và thay đổi cấu hình cache như thế nào để bảo vệ kết quả build?
Bạn tạo và kiểm chứng bằng chứng nguồn gốc bản dựng như thế nào để liên kết một artifact với commit, định nghĩa workflow, hệ thống build và lần chạy CI đã tạo ra nó?
Bạn thiết kế các cổng bảo mật trong pipeline dựa trên quét mã nguồn, dependency, secrets và artifact như thế nào để xử lý cảnh báo sai, ngoại lệ có thời hạn và yêu cầu chặn phát hành?
Trong quá trình thăng hạng từ staging lên production, bạn kiểm chứng digest hoặc chữ ký của artifact và ghi lại quyền phê duyệt, danh tính triển khai cùng kết quả kiểm tra sau triển khai ra sao?
Nếu phát hiện runner có dấu hiệu bị xâm nhập hoặc token CI bị lộ, bạn sẽ sử dụng nhật ký kiểm toán để khoanh vùng ảnh hưởng, thu hồi quyền và xác minh lại các artifact đã phát hành như thế nào?
