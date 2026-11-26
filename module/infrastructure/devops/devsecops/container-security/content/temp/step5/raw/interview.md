Bạn sẽ xây dựng mô hình mối đe dọa cho container xuyên suốt quá trình build, lưu trữ image và chạy workload như thế nào, đặc biệt khi các container dùng chung kernel với máy chủ?
Khi rà soát Dockerfile của một dịch vụ, bạn đánh giá việc chọn base image, dùng multi-stage build, giảm gói cài đặt và chạy bằng người dùng không có quyền root theo những tiêu chí nào?
Bạn thiết kế quy trình cố định phiên bản image bằng digest và cập nhật base image ra sao để vừa tái lập được bản build vừa xử lý kịp thời bản vá bảo mật?
Nếu pipeline cần thông tin xác thực khi build và ứng dụng cần secrets lúc chạy, bạn sẽ cấp phát, giới hạn quyền và kiểm tra nguy cơ lộ secrets trong layer, log hoặc cấu hình container như thế nào?
Khi công cụ quét image báo nhiều lỗ hổng ở cả thư viện ứng dụng và gói hệ điều hành, bạn sẽ xác minh kết quả, ưu tiên khắc phục và thiết lập điều kiện chặn phát hành ra sao?
Bạn sẽ tạo, lưu và kiểm chứng SBOM của một image như thế nào để truy vết thành phần dễ bị ảnh hưởng khi xuất hiện lỗ hổng mới sau khi đã triển khai?
Bạn bảo vệ container registry và kiểm soát tính toàn vẹn image bằng xác thực, phân quyền, chính sách tag và xác minh chữ ký hoặc nguồn gốc artifact trước khi triển khai như thế nào?
Bạn sẽ lựa chọn và kiểm thử các giới hạn Linux capabilities, seccomp, quyền ghi filesystem và đặc quyền tiến trình như thế nào để giảm tác động nếu ứng dụng trong container bị chiếm quyền?
Khi một Pod Kubernetes yêu cầu privileged mode hoặc mount đường dẫn của host, bạn sẽ đánh giá rủi ro và áp dụng Pod Security Standards cùng cơ chế kiểm tra chính sách như thế nào?
Bạn thiết kế quyền của service account và kết nối mạng cho các Pod Kubernetes ra sao để một workload bị xâm nhập khó truy cập bí mật, API hoặc dịch vụ nội bộ không cần thiết?
Nếu hệ thống giám sát runtime phát hiện container bất ngờ chạy shell, tạo kết nối lạ hoặc thay đổi tệp nhạy cảm, bạn sẽ điều tra tín hiệu và phân biệt hành vi hợp lệ với dấu hiệu tấn công như thế nào?
Khi xác định một image đã triển khai bị cài mã độc hoặc registry bị lộ thông tin xác thực, bạn sẽ phối hợp cô lập workload, bảo toàn bằng chứng, thu hồi quyền và triển khai lại từ nguồn tin cậy như thế nào?
