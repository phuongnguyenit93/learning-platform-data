Định dạng SPIFFE ID nào biểu diễn đúng một workload trong một trust domain?
A. https://trust-domain/path/workload với host là tên SPIRE Server.
B. spiffe://path/trust-domain/workload với path xác định máy chạy.
C. urn:spiffe:trust-domain:workload với scheme do agent tự chọn.
D. spiffe://trust-domain/path định danh trust domain và workload.
Đáp án đúng: D

Trust domain trong SPIFFE có vai trò nào?
A. Là miền tin cậy quản lý SPIFFE ID và trust bundle.
B. Là namespace mạng dùng để định tuyến packet giữa các node.
C. Là nhóm workload được phép chia sẻ cùng một private key.
D. Là tên cụm agent mà mọi dịch vụ tự động tin cậy.
Đáp án đúng: A

Mô tả nào phân biệt đúng vai trò SPIRE Server và SPIRE Agent?
A. Agent quản lý registration toàn cục, Server chỉ chuyển tiếp SVID.
B. Server xác thực từng request mạng, Agent chỉ lưu trust bundle.
C. Server quản lý entry; Agent phục vụ workload tại node.
D. Server và Agent đều là workload client lấy SVID qua cùng socket.
Đáp án đúng: C

Node attestation trong SPIRE nhằm xác minh điều gì trước tiên?
A. Xác minh ứng dụng có quyền gọi mọi API trong trust domain.
B. Xác minh workload có đúng phiên bản image đã được ký.
C. Xác minh người dùng cuối đã hoàn tất MFA trước khi kết nối.
D. Xác minh node đủ điều kiện tham gia trust domain.
Đáp án đúng: D

Workload attestation có mục tiêu chính nào?
A. Nhận diện workload để gán SPIFFE ID phù hợp.
B. Xác minh route mạng giữa hai node có thể truyền SVID.
C. Cấp quyền quản trị cluster cho tiến trình được khởi chạy.
D. Tạo trust domain mới cho mỗi container được triển khai.
Đáp án đúng: A

Một registration entry của SPIRE thường liên kết những thông tin nào?
A. Địa chỉ IP, cổng lắng nghe và khóa TLS của load balancer.
B. SPIFFE ID, parent ID và các selector nhận diện workload.
C. Tên DNS, route table và danh sách firewall rule của node.
D. JWT audience, mật khẩu người dùng và refresh token của ứng dụng.
Đáp án đúng: B

Selector trong registration entry được dùng để làm gì?
A. Dùng thuộc tính attestation để khớp workload với entry.
B. Chọn thuật toán ký mà workload sẽ dùng khi tạo SVID.
C. Chọn trust domain mà node tự động tham gia khi khởi động.
D. Chỉ định cổng TCP mà Workload API sẽ mở trên node.
Đáp án đúng: A

Workload API của SPIFFE/SPIRE cung cấp khả năng nào cho workload?
A. Quản lý trực tiếp registration entry và cấu hình SPIRE Server.
B. Nhận SVID cùng trust bundle phù hợp với danh tính workload.
C. Cấp quyền truy cập hệ điều hành cho mọi process cùng node.
D. Thay thế hoàn toàn DNS và service discovery trong mạng.
Đáp án đúng: B

Vì sao endpoint Workload API cục bộ cần được bảo vệ chặt chẽ?
A. Vì socket này công khai trust bundle cho mọi máy trong mạng.
B. Vì socket này lưu mật khẩu đăng nhập của tất cả workload.
C. Vì workload có thể nhận SVID và private key qua API.
D. Vì socket này cho phép mọi container sửa cấu hình của SPIRE Server.
Đáp án đúng: C

X.509-SVID biểu diễn danh tính SPIFFE chủ yếu ở đâu?
A. Trong Common Name chứa hostname của node đang chạy workload.
B. Trong URI SAN của chứng thư X.509 theo SPIFFE ID.
C. Trong DNS SAN chứa địa chỉ service discovery của workload.
D. Trong trường issuer là tên registration entry do quản trị viên đặt.
Đáp án đúng: B

JWT-SVID khác X.509-SVID ở đặc điểm nào?
A. Là chứng thư X.509 được mã hóa bằng khóa riêng của workload.
B. Là mật khẩu dùng một lần được Workload API cấp cho node.
C. Là token JWT có chữ ký, subject SPIFFE ID và audience.
D. Là trust bundle chứa các chứng thư gốc của trust domain.
Đáp án đúng: C

Khi một dịch vụ nhận JWT-SVID, kiểm tra nào ngăn token dùng sai nơi nhận?
A. Chỉ kiểm tra subject có chứa đúng tên ứng dụng gửi request.
B. Chỉ kiểm tra token được truyền qua kết nối TLS.
C. Chỉ kiểm tra thời điểm phát hành nằm trong cùng ngày.
D. Kiểm tra audience khớp chính xác với dịch vụ nhận token.
Đáp án đúng: D

Vì sao JWT-SVID nên có thời hạn ngắn và audience cụ thể?
A. Để tránh phải xác minh chữ ký ở phía dịch vụ nhận.
B. Giảm cửa sổ replay và giới hạn nơi nhận token.
C. Để token có thể được chia sẻ an toàn giữa mọi service.
D. Để biến JWT thành chứng thư X.509 có thể dùng cho TLS.
Đáp án đúng: B

Trust bundle của một trust domain thường chứa thành phần nào?
A. Danh sách mọi workload đang hoạt động cùng private key tương ứng.
B. Registration entry và selector để workload tự xác thực node.
C. Access token của các service được phép gọi Workload API.
D. Trust anchor dùng để xác minh SVID thuộc trust domain đó.
Đáp án đúng: D

Khi xoay trust anchor của một trust domain, cách triển khai nào an toàn?
A. Phát hành anchor mới, chồng lấp trust rồi gỡ anchor cũ.
B. Xóa anchor cũ trên mọi peer trước khi phát hành anchor mới.
C. Chỉ thay private key của workload và giữ nguyên bundle hiện tại.
D. Tắt xác minh chứng thư trong lúc tất cả peer cập nhật bundle.
Đáp án đúng: A

Federation giữa hai SPIFFE trust domain cần dựa trên điều gì?
A. Mặc định tin mọi trust domain có thể phân giải DNS lẫn nhau.
B. Trao đổi trust bundle qua federation đã xác thực.
C. Dùng chung một SPIFFE ID cho workload ở cả hai miền.
D. Sao chép toàn bộ private key của mỗi miền sang miền còn lại.
Đáp án đúng: B

Khi xác minh X.509-SVID của peer, kiểm tra nào là cần thiết?
A. Xác minh chain và SPIFFE ID trong URI SAN.
B. Chỉ so sánh Common Name với hostname mà DNS trả về.
C. Chỉ kiểm tra chứng thư được ký bởi bất kỳ CA công khai nào.
D. Chỉ kiểm tra địa chỉ IP peer có thuộc subnet nội bộ.
Đáp án đúng: A

mTLS xác thực danh tính workload có ý nghĩa gì đối với authorization?
A. Danh tính hợp lệ tự động cấp mọi quyền trên tài nguyên đích.
B. mTLS xác thực peer; policy riêng cấp quyền.
C. Khi đã dùng mTLS, dịch vụ không cần kiểm tra SPIFFE ID.
D. Chứng thư hợp lệ thay thế hoàn toàn kiểm soát truy cập ứng dụng.
Đáp án đúng: B

Workload API thông báo SVID mới khi credential sắp hết hạn để ứng dụng làm gì?
A. Khởi động lại toàn bộ node trước khi chứng thư cũ hết hạn.
B. Ghi đè trust bundle của mọi trust domain bằng chứng thư mới.
C. Thay credential mà không restart workload.
D. Giữ chứng thư cũ vô thời hạn để tránh thay đổi kết nối.
Đáp án đúng: C

Ứng dụng nhận X.509-SVID qua Workload API nên bảo vệ private key ra sao?
A. Giữ key trong bộ nhớ, giới hạn quyền truy cập.
B. Ghi key vào log debug để hỗ trợ điều tra lỗi TLS.
C. Lưu key trong thư mục chia sẻ để mọi process cùng node dùng.
D. Đưa key vào biến môi trường chung của toàn bộ container.
Đáp án đúng: A

Trong Kubernetes, thuộc tính nào có thể hỗ trợ workload attestation?
A. Chỉ địa chỉ IP pod vì địa chỉ này luôn gắn cố định với workload.
B. Tên node do container tự gửi trong HTTP request.
C. Namespace, service account và pod attributes đã xác minh.
D. Nhãn do workload tự khai báo mà không cần xác minh nguồn.
Đáp án đúng: C

Node attestation dựa trên cloud instance identity giúp giảm rủi ro nào?
A. Giảm việc workload phải khai báo port trong registration entry.
B. Giảm nhu cầu kiểm tra audience của JWT-SVID ở phía nhận.
C. Giảm khả năng kẻ tấn công giả mạo danh tính node khi tham gia.
D. Giảm số trust anchor cần có trong trust bundle của miền.
Đáp án đúng: C

Parent SPIFFE ID trong registration entry giúp biểu diễn điều gì?
A. Danh tính của dịch vụ đích mà workload được phép gọi.
B. CA gốc dùng để ký chứng thư X.509-SVID của node.
C. Audience mặc định cho mọi JWT-SVID trong trust domain.
D. Danh tính node hoặc workload cha của entry con.
Đáp án đúng: D

Một selector quá rộng trong registration entry tạo ra rủi ro nào?
A. Trust bundle tự động bị xóa khi workload đầu tiên đăng nhập.
B. X.509-SVID chuyển thành JWT-SVID khi pod được khởi động lại.
C. Nhiều workload ngoài dự kiến có thể nhận cùng SPIFFE ID.
D. Workload API không thể gửi sự kiện rotation cho agent.
Đáp án đúng: C

Khi triển khai nhiều cluster Kubernetes, lựa chọn trust domain nào hợp lý?
A. Dùng một trust domain cho tất cả mà không cần xét ranh giới quản trị.
B. Chọn trust domain theo ranh giới tin cậy; federation rõ ràng.
C. Đặt trust domain theo IP của từng node để dễ định tuyến.
D. Dùng cùng SPIFFE ID cho các workload có tên giống nhau.
Đáp án đúng: B

Để xác minh JWT-SVID, dịch vụ nhận cần kiểm tra nhóm yếu tố nào?
A. Chỉ hostname trong TLS certificate của máy gửi request.
B. Chỉ subject và tên namespace ghi trong payload token.
C. DNS record của SPIRE Agent và địa chỉ IP node nguồn.
D. Kiểm tra chữ ký, issuer, audience và hạn token.
Đáp án đúng: D

Khi xác minh X.509-SVID cho kết nối mTLS, điều kiện nào phải được kiểm tra?
A. Chỉ chứng thư còn hạn và được ký bởi một CA bất kỳ.
B. Chỉ SPIFFE ID trong URI SAN mà không cần xác minh chuỗi.
C. Kiểm tra chain, thời hạn và SPIFFE ID mong đợi.
D. Chỉ địa chỉ IP của peer khớp với node registration.
Đáp án đúng: C

SPIRE Server tạm thời không khả dụng nhưng Agent còn SVID chưa hết hạn; ứng dụng nên làm gì?
A. Tự tạo chứng thư tự ký mới để tiếp tục kết nối.
B. Bỏ qua mọi kiểm tra peer cho đến khi Server hoạt động.
C. Dùng SVID còn hạn và tiếp tục theo dõi refresh.
D. Xóa trust bundle cục bộ để buộc các peer kết nối lại.
Đáp án đúng: C

Thiết kế HA cho SPIRE Server cần chú ý thành phần nào?
A. HA cho Server, datastore và backup/restore.
B. Chỉ tăng số Workload API socket trên mỗi workload.
C. Chỉ nhân bản chứng thư leaf của workload sang mọi node.
D. Chỉ tăng TTL SVID để tránh mọi lần gọi tới Server.
Đáp án đúng: A

Khi thay đổi registration entry, audit nào hữu ích nhất?
A. Ghi actor, thời điểm, entry, selector và phê duyệt.
B. Chỉ ghi số lượng workload đang chạy sau khi thay đổi.
C. Chỉ lưu snapshot trust bundle cuối ngày mà không lưu actor.
D. Chỉ ghi lại log ứng dụng của workload được cấp SVID.
Đáp án đúng: A

Khi nghi ngờ workload private key bị lộ, phản ứng nào phù hợp?
A. Chờ chứng thư hết hạn tự nhiên rồi mới rà soát quyền.
B. Chỉ đổi tên SPIFFE ID nhưng giữ nguyên key material.
C. Tắt mTLS trên toàn bộ trust domain để tránh lỗi kết nối.
D. Chặn SPIFFE ID trong policy, gỡ entry và cấp lại SVID.
Đáp án đúng: D

Vì sao trust bundle rotation cần có giai đoạn chồng lấp?
A. Để hai trust domain dùng chung một SPIFFE ID trong thời gian chuyển đổi.
B. Để SVID cũ được gia hạn bằng private key của trust anchor mới.
C. Để bỏ qua xác minh chain trong khi các agent đang khởi động.
D. Để peer có thời gian nhận anchor mới trước khi anchor cũ bị loại.
Đáp án đúng: D

Quyền truy cập Workload API socket nên được thiết kế thế nào?
A. Cho mọi process trên node truy cập để giảm lỗi phân quyền.
B. Giới hạn quyền socket và xác minh workload qua attestation.
C. Mở socket ra mạng công khai để workload ở node khác dùng.
D. Chỉ giới hạn truy cập theo tên file socket mà không xét danh tính.
Đáp án đúng: B

Chọn TTL cho SVID cần cân nhắc đánh đổi nào?
A. TTL dài luôn tăng khả năng thu hồi tức thời của chứng thư.
B. TTL không ảnh hưởng tải lên SPIRE Server hoặc Agent.
C. TTL chỉ áp dụng cho JWT-SVID, không áp dụng X.509-SVID.
D. TTL ngắn giảm phơi nhiễm, tăng nhu cầu refresh.
Đáp án đúng: D

Kiểm thử âm tính nào giúp xác nhận xác minh SVID đúng cách?
A. Chỉ thử kết nối giữa hai workload cùng namespace hợp lệ.
B. Thử sai trust domain/audience, hết hạn và bundle lạ.
C. Chỉ đo thời gian cấp SVID khi SPIRE Server đang ổn định.
D. Chỉ kiểm tra workload có thể đọc socket Workload API.
Đáp án đúng: B

Ứng dụng cần xác thực workload bằng TLS hai chiều và danh tính URI cho peer; nên chọn SVID nào?
A. X.509-SVID vì chứng thư hỗ trợ TLS và mang SPIFFE ID.
B. JWT-SVID vì TLS stack tự đọc audience từ mọi JWT.
C. JWT-SVID vì token mang private key dùng cho bắt tay TLS.
D. Trust bundle vì bundle đại diện trực tiếp cho một workload.
Đáp án đúng: A
