Một dịch vụ thanh toán cần lưu API key của nhà cung cấp bên ngoài; nhóm phát triển đang đặt key trực tiếp trong tệp cấu hình được commit cùng mã nguồn.
Nhóm vận hành chuyển mật khẩu cơ sở dữ liệu từ biến môi trường sang secret manager, nhưng quyền đọc secret được cấp cho toàn bộ workload trong cùng tài khoản cloud.
Một ứng dụng cần lấy secret khi khởi động; secret manager tạm thời không khả dụng và ứng dụng đang ghi giá trị mặc định vào log khi không lấy được bí mật.
Một secret có cùng tên được tạo riêng ở môi trường development, staging và production; pipeline triển khai vô tình trỏ workload production đến secret của staging.
Một nhóm có nhiều dự án dùng chung secret manager; chính sách IAM dựa trên wildcard khiến developer của một dự án đọc được credential của dự án khác.
Một nhân viên chuyển nhóm vẫn giữ quyền truy cập secret cũ vì quy trình offboarding chỉ thu hồi tài khoản đăng nhập mà không cập nhật policy của secret manager.
Một workload dùng access key dài hạn được nhúng trong image container; image được sao chép sang registry công khai và credential vẫn còn hiệu lực.
Một ứng dụng cần truy cập secret mà không dùng credential tĩnh; nền tảng hỗ trợ workload identity nhưng nhóm triển khai vẫn tạo access key cố định cho từng pod.
Một service account được cấp quyền đọc toàn bộ secret trong namespace để sửa lỗi nhanh; sau đó một pod bị xâm nhập có thể lấy credential của mọi ứng dụng trong namespace.
Một secret manager cấp credential cơ sở dữ liệu động với lease ngắn; ứng dụng giữ connection pool lâu hơn thời hạn lease và bắt đầu gặp lỗi xác thực.
Một credential động đã hết lease nhưng tác vụ nền vẫn dùng thông tin cũ; hệ thống cần xử lý việc gia hạn, tạo credential mới và đóng kết nối hiện hữu.
Nhà cung cấp cơ sở dữ liệu hỗ trợ tài khoản tạm thời nhưng quy trình thu hồi lease không chạy khi secret manager mất kết nối trong lúc sự cố.
Một API token được chia sẻ giữa nhiều dịch vụ để giảm số lượng secret; khi một dịch vụ bị xâm nhập, đội vận hành không thể xác định phạm vi sử dụng và thu hồi riêng.
Một secret được mã hóa bằng KMS nhưng quyền decrypt được cấp cho role quá rộng; người dùng không đọc được ciphertext trực tiếp nhưng có thể yêu cầu giải mã tùy ý.
Một khóa mã hóa gốc được dùng trực tiếp để mã hóa nhiều loại secret; nhóm bảo mật muốn tách khóa theo mục đích và môi trường mà không làm mất khả năng giải mã dữ liệu cũ.
KMS key sắp đến thời điểm rotation nhưng các bản backup và ciphertext cũ vẫn phụ thuộc vào phiên bản khóa trước; nhóm vận hành chưa có kế hoạch re-encryption và recovery.
Một key policy cho phép principal bên ngoài tài khoản cloud sử dụng khóa; thay đổi trust relationship khiến một workload không dự kiến có thể giải mã secret.
Một secret được lưu trong hệ thống quản lý cấu hình dưới dạng ciphertext; khóa giải mã lại được đặt trong cùng repository nên việc mã hóa không giảm đáng kể rủi ro lộ bí mật.
Pipeline CI/CD cần triển khai ứng dụng lên production; runner dùng một credential quản trị có quyền truy cập tất cả môi trường và được chia sẻ giữa nhiều repository.
Một pull request từ nhánh fork có thể kích hoạt workflow CI; workflow vô tình nhận được biến chứa production secret khi chạy mã do người ngoài đóng góp.
Log của pipeline in toàn bộ environment khi bước triển khai thất bại; API token xuất hiện trong log và được lưu lâu dài trong hệ thống CI.
Nhóm phát triển dùng secret masking trong CI nhưng token được encode hoặc chia nhỏ trước khi in nên bộ lọc không che được giá trị nhạy cảm.
Một artifact build chứa tệp cấu hình có credential vì bước đóng gói sao chép cả thư mục môi trường; artifact được lưu trong registry dùng chung.
Credential của runner CI bị lộ trong một cache build; cùng credential đó còn có quyền publish image và thay đổi cấu hình triển khai production.
Pipeline cần truy cập cloud trong thời gian ngắn; tổ chức đang cân nhắc OIDC federation thay cho lưu access key dài hạn trong secret store của CI.
Cluster Kubernetes dùng Secret object mặc định; đội nền tảng cho rằng dữ liệu đã được bảo vệ vì manifest chỉ hiển thị chuỗi Base64.
Quyền get/list/watch Kubernetes Secret được cấp cho nhóm vận hành toàn cluster; một người dùng chỉ cần xem pod cũng có thể truy xuất secret của namespace khác.
Secret được mount vào pod dưới dạng volume; ứng dụng ghi nội dung file vào log khi phát hiện cấu hình không hợp lệ và làm lộ credential.
Một pod bị xâm nhập có thể đọc token của service account được mount tự động; nhóm nền tảng cần giới hạn audience, quyền và thời hạn token.
External Secrets Operator đồng bộ secret từ vault vào Kubernetes; khi secret nguồn bị thu hồi, bản sao trong cluster vẫn tồn tại vì chu kỳ refresh không được kiểm soát.
Một secret rotation cập nhật Kubernetes Secret thành công nhưng pod đang chạy không reload file mount; ứng dụng tiếp tục dùng credential cũ đến lần restart tiếp theo.
Helm chart chứa giá trị nhạy cảm trong values file; lịch sử release và quyền đọc metadata khiến secret có thể bị truy xuất ngoài dự kiến.
Một ứng dụng serverless cần đọc secret khi khởi chạy; nhóm triển khai đưa bí mật vào biến cấu hình của function và không xác định rõ ai có thể xem cấu hình đó.
Credential của tài khoản dịch vụ được dùng chung cho nhiều workload; nhóm điều tra không thể phân biệt workload nào đã thực hiện thao tác nhạy cảm trong audit log.
Một secret có thời hạn sử dụng không được đặt metadata owner hoặc ngày hết hạn; sau khi chủ sở hữu rời công ty, không ai biết ứng dụng nào còn phụ thuộc vào nó.
Inventory secret phát hiện nhiều credential không có lần sử dụng gần đây; nhóm vận hành muốn thu hồi nhưng chưa xác định được các batch job chạy theo lịch thưa.
Một API key được rotation bằng cách vô hiệu hóa key cũ ngay khi tạo key mới; một số instance chưa nhận cấu hình mới và toàn bộ request của chúng bị lỗi.
Nhà cung cấp chỉ cho phép một API key hoạt động tại một thời điểm; quy trình rotation cần tránh gián đoạn trong khi vẫn bảo đảm key cũ không tồn tại lâu.
Một database password được rotation thành công nhưng ứng dụng có nhiều replica và connection pool; các instance cập nhật cấu hình ở thời điểm khác nhau gây lỗi đăng nhập xen kẽ.
Secret manager hỗ trợ versioning; ứng dụng production vô tình đọc alias trỏ đến phiên bản thử nghiệm sau một thay đổi cấu hình trong đợt triển khai.
Một credential bị nghi lộ nhưng chưa xác định được nơi sử dụng; đội ứng phó cần chọn thứ tự thu hồi, thay thế và kiểm tra phụ thuộc để giảm thời gian phơi nhiễm.
Secret scanner phát hiện private key trong lịch sử Git; developer xóa dòng chứa khóa ở commit mới nhưng bản sao cũ vẫn còn trong lịch sử và fork.
Một repository public chứa token đã bị commit; nhóm chỉ xóa token khỏi source mà chưa thu hồi credential hoặc kiểm tra hoạt động bất thường sau thời điểm lộ.
Endpoint hỗ trợ tải file cấu hình có thể trả về secret nếu người dùng đoán được đường dẫn; nhóm phát hiện request bất thường nhưng log chưa ghi principal và phạm vi truy cập.
Một nhân viên gửi secret qua kênh chat để hỗ trợ khắc phục production; nội dung đã được lưu trong bản sao lưu và nhiều người ngoài nhóm có quyền tìm kiếm.
Audit log của secret manager ghi nhận thao tác đọc nhưng không ghi danh tính workload, phiên bản secret và lý do truy cập; điều tra sự cố không thể xác định chính xác nguồn.
Một tài khoản break-glass có quyền truy cập toàn bộ secret được dùng trong đợt xử lý sự cố; sau sự kiện không có quy trình rotate credential và rà soát hoạt động.
Backup của secret manager được lưu ở một tài khoản cloud khác; quyền khôi phục quá rộng và bản backup không được kiểm tra khả năng phục hồi định kỳ.
Secret manager gặp sự cố vùng khả dụng; ứng dụng cần tiếp tục chạy bằng secret đã cache nhưng chính sách cache hiện tại không đặt giới hạn thời gian hoặc cơ chế xóa an toàn.
Một tổ chức mua lại công ty khác và cần hợp nhất hai hệ thống secret manager; tên secret trùng nhau nhưng owner, policy và vòng đời của từng credential khác nhau.
Một nhóm tuân thủ yêu cầu chứng minh secret nhạy cảm chỉ được truy cập từ workload đã xác thực, được rotation đúng hạn và có người chịu trách nhiệm; dữ liệu kiểm toán hiện phân tán ở nhiều hệ thống.
Một secret chứa thông tin cá nhân và credential được sao chép sang môi trường thử nghiệm để tái hiện lỗi; nhóm chưa có quy trình tạo dữ liệu thay thế hoặc giới hạn thời gian lưu.
Một ứng dụng phụ thuộc secret manager bên ngoài; khi thay đổi nhà cung cấp, tổ chức cần chuyển secret và khóa mã hóa mà không để lộ giá trị trong tệp trung gian hoặc log.
