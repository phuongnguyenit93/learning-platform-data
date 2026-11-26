Service account được thiết kế chủ yếu để đại diện cho đối tượng nào?
A. Nhân viên cần đăng nhập tương tác hằng ngày.
B. Ứng dụng, workload hoặc tác vụ tự động.
C. Nhóm người dùng có cùng phòng ban và chức danh.
D. Quản trị viên chịu trách nhiệm phê duyệt truy cập.
Đáp án đúng: B

Vì sao mỗi workload nhạy cảm nên có danh tính dịch vụ riêng?
A. Để giảm số lượng principal trong hệ thống IAM.
B. Để bỏ qua bước rà soát quyền khi triển khai.
C. Để cô lập quyền và quy trách nhiệm khi audit.
D. Để mọi workload dùng chung một bộ credential.
Đáp án đúng: C

Thông tin nào quan trọng nhất trong inventory service account?
A. Chỉ số lần đăng nhập trong kỳ gần nhất.
B. Owner, mục đích, quyền và credential.
C. Chỉ tên tài khoản và ngày tạo ban đầu.
D. Chỉ hostname của máy chủ chạy ứng dụng.
Đáp án đúng: B

Điểm khác biệt chính giữa service account và user account là gì?
A. Service account luôn có quyền cao hơn user account.
B. User account không thể dùng token hoặc certificate.
C. Service account không cần owner chịu trách nhiệm.
D. Đại diện workload, thường không tương tác.
Đáp án đúng: D

Least privilege cho service account nên bắt đầu từ đâu?
A. Dùng quyền của người triển khai workload.
B. Cho phép mọi API nội bộ để tránh lỗi tích hợp.
C. Xác định tài nguyên và hành động thật sự cần.
D. Cấp role quản trị rồi thu hẹp nếu có cảnh báo.
Đáp án đúng: C

Một workload chỉ cần đọc object trong một prefix thì quyền nào phù hợp?
A. List và delete trên mọi bucket cùng tenant.
B. Read-write trên toàn bucket để tránh permission lỗi.
C. Read-only trên đúng prefix được yêu cầu.
D. Administrator trên project chứa bucket dữ liệu.
Đáp án đúng: C

Khi tách quyền deploy khỏi quyền truy cập dữ liệu, lợi ích chính là gì?
A. Giúp cùng credential dùng được ở nhiều môi trường.
B. Giảm phạm vi ảnh hưởng khi một credential bị lộ.
C. Loại bỏ nhu cầu theo dõi thay đổi quyền truy cập.
D. Cho phép pipeline tự phê duyệt quyền production.
Đáp án đúng: B

Credential của service account khác identity ở điểm nào?
A. Identity là secret được gửi tới token endpoint.
B. Credential và identity luôn là cùng một đối tượng.
C. Credential là role mô tả quyền của principal.
D. Credential chứng minh danh tính workload.
Đáp án đúng: D

Khi nền tảng hỗ trợ managed identity, lựa chọn nào thường an toàn hơn?
A. Đặt mật khẩu service account trong file cấu hình.
B. Dùng danh tính do nền tảng cấp và quản lý.
C. Tạo access key dài hạn rồi lưu trong image.
D. Dùng chung API key giữa các máy chủ ứng dụng.
Đáp án đúng: B

Rủi ro lớn của access key tĩnh có thời hạn rất dài là gì?
A. Khó giới hạn thời gian lạm dụng sau khi bị lộ.
B. Không thể dùng để xác thực API từ workload.
C. Không thể phân quyền theo resource hoặc action.
D. Luôn tự hết hiệu lực khi workload được restart.
Đáp án đúng: A

Workload identity federation thường loại bỏ nhu cầu nào?
A. Lưu credential dài hạn của tài khoản đích.
B. Ràng buộc subject với workload được tin cậy.
C. Kiểm tra audience của token được cấp.
D. Xác minh issuer của token nguồn.
Đáp án đúng: A

Trust policy cho workload federation nên ràng buộc claim nào?
A. Chỉ địa chỉ IP public của runner.
B. Issuer, subject và audience mong đợi.
C. Chỉ tên hiển thị của pipeline hoặc repository.
D. Chỉ thời điểm token được phát hành.
Đáp án đúng: B

Vì sao audience restriction quan trọng với access token?
A. Ngăn token được dùng tại API ngoài dự kiến.
B. Làm token có thời hạn dài hơn mà không cần refresh.
C. Ẩn danh tính client khỏi resource server.
D. Thay thế việc kiểm tra scope của API.
Đáp án đúng: A

Resource server xác minh JWT access token cần kiểm tra điều gì?
A. Chỉ kiểm tra token có đúng định dạng JWT.
B. Chỉ so sánh tên client với tên API đích.
C. Chỉ decode payload rồi đọc subject và scope.
D. Chữ ký, issuer, audience và thời hạn.
Đáp án đúng: D

Client Credentials Grant phù hợp nhất với trường hợp nào?
A. Trình duyệt cần xác thực người dùng bằng passkey.
B. Workload gọi API bằng identity riêng.
C. Người dùng đăng nhập và cấp consent cho ứng dụng.
D. Ứng dụng cần khôi phục mật khẩu người dùng.
Đáp án đúng: B

Khi workload gọi API thay mặt người dùng, cần bảo toàn điều gì?
A. Chỉ danh tính service account của proxy trung gian.
B. Chỉ địa chỉ mạng của máy chủ phát request.
C. Một quyền quản trị chung cho toàn bộ downstream.
D. Danh tính người dùng và ngữ cảnh ủy quyền.
Đáp án đúng: D

Mutual TLS giúp xác thực service-to-service bằng cách nào?
A. Hai đầu trình bày certificate và xác minh peer.
B. Hai bên dùng chung một API key trong HTTP header.
C. Client tin mọi certificate được máy chủ gửi tới.
D. Chỉ máy chủ trình certificate, client gửi mật khẩu.
Đáp án đúng: A

Certificate client của workload cần được kiểm tra thuộc tính nào?
A. Chain tin cậy, thời hạn và danh tính SAN.
B. Chỉ việc certificate có thể đọc được bằng Base64.
C. Chỉ Common Name và địa chỉ IP của node.
D. Chỉ thuật toán mã hóa trong certificate request.
Đáp án đúng: A

SSH automation key nên được quản lý theo nguyên tắc nào?
A. Dùng một private key chung cho mọi máy đích.
B. Sao chép private key vào mọi repository triển khai.
C. Không cần rotation nếu key chỉ dùng non-interactive.
D. Tách key theo workload, đích đến và owner.
Đáp án đúng: D

Secret manager nên cấp secret cho workload theo cách nào?
A. Dùng một bootstrap key chung cho toàn tổ chức.
B. Chỉ workload đã xác thực và được cấp quyền.
C. Trả secret qua log để workload lấy khi cần.
D. Mọi process cùng namespace đều được đọc mọi secret.
Đáp án đúng: B

Vì sao hard-code API key trong source code là rủi ro?
A. Key có thể lưu trong history và artifact.
B. Key không thể được dùng từ pipeline CI/CD.
C. Key không thể được rotate sau khi phát hành.
D. Key tự động hết hạn khi repository được clone.
Đáp án đúng: A

Truyền secret qua command-line argument có nguy cơ nào?
A. Secret tự được mã hóa bởi shell trước khi chạy.
B. Lộ qua process listing hoặc log.
C. Secret chỉ hiển thị với tiến trình đã tạo nó.
D. Secret không thể được đọc từ crash dump.
Đáp án đúng: B

Một container image chứa client secret được đẩy lên registry công khai; phản ứng nào phù hợp?
A. Đổi tên repository rồi giữ nguyên secret.
B. Chờ đến kỳ rotation định kỳ tiếp theo.
C. Chỉ xóa tag image mới nhất khỏi registry.
D. Thu hồi key, rebuild và scan image.
Đáp án đúng: D

Bootstrap credential nên được thiết kế như thế nào?
A. Không cần audit vì chỉ dùng trong lần khởi động.
B. Quyền hẹp, TTL ngắn, chỉ cấp identity.
C. Quyền quản trị rộng để hỗ trợ mọi workload mới.
D. Dùng chung lâu dài cho mọi môi trường triển khai.
Đáp án đúng: B

Khi rotate client secret mà cần tránh gián đoạn, cách nào phù hợp?
A. Thu hồi key cũ trước khi tạo key thay thế.
B. Tạo key mới nhưng giữ cả hai vô thời hạn.
C. Thay secret trong vault mà không kiểm tra consumer.
D. Overlap ngắn, chuyển consumer rồi thu hồi key cũ.
Đáp án đúng: D

Credential bị xác nhận lộ cần được xử lý ưu tiên thế nào?
A. Chỉ xóa file chứa credential khỏi máy phát hiện.
B. Tắt audit để tránh lộ thêm thông tin điều tra.
C. Revoke, thay mới và điều tra phạm vi.
D. Chờ hết cryptoperiod rồi mới thay credential.
Đáp án đúng: C

Access token ngắn hạn giúp giảm rủi ro nào?
A. Bảo đảm token không thể bị sao chép khỏi process.
B. Loại bỏ nhu cầu xác minh audience và scope.
C. Ngăn mọi hành vi replay trong thời hạn token.
D. Giới hạn thời gian sử dụng token bị đánh cắp.
Đáp án đúng: D

Thu hồi service account cần xem xét thành phần nào?
A. Chỉ xóa tên principal khỏi giao diện quản trị.
B. Chỉ thu hồi mật khẩu, giữ nguyên token đã phát hành.
C. Identity, credential, token và quyền đã cấp.
D. Chỉ gỡ workload, không thay đổi trust relationship.
Đáp án đúng: C

Một service account đã nghỉ sử dụng nhưng có batch job theo quý; cách xử lý nào hợp lý?
A. Giữ vô thời hạn vì từng được tạo cho batch job.
B. Tăng quyền để job dễ hoạt động khi chạy lại.
C. Xác minh lịch và dependency trước khi thu hồi.
D. Thu hồi ngay nếu 30 ngày không có đăng nhập.
Đáp án đúng: C

Service account có cần quyền đăng nhập tương tác mặc định không?
A. Không, nhưng nên cho phép đăng nhập từ xa không hạn chế.
B. Có, để operator dễ kiểm tra hoạt động của nó.
C. Có, vì mọi service account đều cần shell.
D. Không; chỉ cấp nếu có nhu cầu được phê duyệt.
Đáp án đúng: D

Vì sao không nên cho con người dùng chung service account?
A. Làm token access không thể được refresh.
B. Ngăn workload tự động chạy khi không có user.
C. Làm mất khả năng quy hành động về cá nhân.
D. Khiến certificate không thể được gia hạn tự động.
Đáp án đúng: C

Khi gateway chuyển tiếp danh tính workload qua header, cần bảo vệ điều gì?
A. Chỉ tin proxy xác thực, chặn gọi thẳng backend.
B. Cho phép caller tự đặt principal để hỗ trợ delegation.
C. Bỏ xác thực peer nếu header đã có service name.
D. Chấp nhận header từ mọi client trong mạng nội bộ.
Đáp án đúng: A

Service account có quyền tạo principal mới tạo ra rủi ro nào?
A. Duy trì truy cập bằng principal phụ trái phép.
B. Ngăn quản trị viên xem lịch sử thay đổi policy.
C. Chỉ làm tăng số lượng log khi workload chạy.
D. Khiến token của service account hết hạn sớm hơn.
Đáp án đúng: A

Token service account của Kubernetes nên được cấu hình thế nào khi workload không gọi API?
A. Mount token dài hạn để sẵn sàng cho tác vụ mới.
B. Dùng token mặc định của node cho mọi pod.
C. Không mount token vào workload không cần nó.
D. Cấp token cluster-admin để tránh lỗi phân quyền.
Đáp án đúng: C

Tác vụ CI/CD cần quyền production nên lấy identity theo cách nào?
A. Dùng credential của developer khởi chạy pipeline.
B. Nhận quyền admin chỉ dựa trên tên project.
C. Federation ràng buộc subject và môi trường.
D. Dùng access key production chung trong repository.
Đáp án đúng: C

Dấu hiệu nào có thể cho thấy service credential đang bị lạm dụng?
A. Truy cập mới hoặc tăng đột biến bất thường.
B. Job hoàn tất trong thời gian và lịch dự kiến.
C. Workload gia hạn token đúng chu kỳ đã cấu hình.
D. Service account gọi API đúng audience được cấp.
Đáp án đúng: A

Audit event cho hành động của service account nên ghi gì?
A. Principal, workload, resource, action, kết quả.
B. Chỉ tên tài khoản và thời điểm không có resource.
C. Chỉ địa chỉ IP mà không có principal hoặc action.
D. Toàn bộ secret và token để tiện tái hiện request.
Đáp án đúng: A
