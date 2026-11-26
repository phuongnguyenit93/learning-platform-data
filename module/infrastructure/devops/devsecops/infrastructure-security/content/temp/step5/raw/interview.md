Khi đánh giá hạ tầng cloud phục vụ CI/CD, bạn sẽ xác định những tài sản và bề mặt tấn công quan trọng nào, đồng thời phân định trách nhiệm bảo mật giữa nhà cung cấp cloud và đội vận hành ra sao?
Một runner CI/CD cần triển khai ứng dụng lên cloud, bạn sẽ thiết kế quyền IAM tối thiểu, cơ chế cấp danh tính ngắn hạn và quy trình rà soát quyền như thế nào để hạn chế tác động nếu runner bị xâm nhập?
Khi thiết kế mạng cho hệ thống gồm máy chủ ứng dụng, cơ sở dữ liệu và dịch vụ quản trị, bạn sẽ phân đoạn subnet, kiểm soát luồng vào ra và giới hạn di chuyển ngang giữa các thành phần như thế nào?
Bạn sẽ xây dựng và kiểm chứng baseline hardening cho máy chủ Linux chạy build agent như thế nào, xét đến cấu hình SSH, tài khoản đặc quyền, bản vá, dịch vụ đang mở và khả năng kiểm toán?
Đối với dữ liệu và secrets được sử dụng trong hạ tầng DevSecOps, bạn sẽ lựa chọn cơ chế mã hóa khi truyền và khi lưu trữ, quản lý khóa và luân chuyển thông tin nhạy cảm như thế nào?
Nếu một tài nguyên lưu trữ trên cloud bị phát hiện có thể truy cập công khai ngoài dự kiến, bạn sẽ xác minh phạm vi phơi lộ, nguyên nhân cấu hình sai và ảnh hưởng tới dữ liệu như thế nào trước khi khắc phục?
Khi một workload Kubernetes yêu cầu chạy container đặc quyền và sử dụng service account, bạn sẽ đánh giá nhu cầu thực tế và áp dụng các kiểm soát RBAC, security context và Pod Security Standards ra sao?
Bạn sẽ thiết kế và xác minh NetworkPolicy cho các namespace Kubernetes như thế nào để giới hạn giao tiếp giữa pod, vẫn duy trì kết nối cần thiết và bảo đảm chính sách thực sự được hạ tầng mạng thực thi?
Trong một pull request thay đổi Terraform để mở cổng quản trị ra Internet, bạn sẽ tích hợp quét Infrastructure as Code và đánh giá kết quả như thế nào để ngăn cấu hình nguy hiểm trước khi triển khai?
Bạn sẽ triển khai policy as code trong pipeline và tại bước chấp nhận tài nguyên cloud hoặc Kubernetes như thế nào để kiểm soát cấu hình, xử lý ngoại lệ có thời hạn và tránh chính sách làm gián đoạn thay đổi hợp lệ?
Bạn sẽ lựa chọn log, audit event và chỉ số giám sát nào để phát hiện các hành vi bất thường như tăng quyền IAM, thay đổi firewall hoặc truy cập Kubernetes trái phép, đồng thời giảm cảnh báo nhiễu ra sao?
Nếu nghi ngờ một Kubernetes workload bị xâm nhập và thông tin xác thực đã bị lộ, bạn sẽ ưu tiên những bước nào để cô lập ảnh hưởng, bảo toàn bằng chứng, thu hồi quyền và khôi phục dịch vụ an toàn?
