Resource Server nhận opaque access token nhưng chỉ kiểm tra token có tồn tại trong request; dịch vụ không gọi introspection endpoint nên token ngẫu nhiên hoặc đã bị thu hồi vẫn được dùng.
Authorization Server trả introspection response với `active: false` nhưng Resource Server chỉ kiểm tra HTTP 200 và coi mọi response thành công là token hợp lệ.
Resource Server nhận `active: true` nhưng bỏ qua `exp`; token đã hết hạn vẫn được chấp nhận vì Authorization Server chưa cập nhật trạng thái kịp thời.
Introspection response có `scope` chỉ gồm `orders:read` nhưng API cho phép cả thao tác cập nhật đơn hàng; scope không được đối chiếu với action cụ thể.
Opaque token được phát cho audience của reporting API nhưng Resource Server của admin API không kiểm tra `aud`; token bị dùng sai resource.
Resource Server chỉ kiểm tra `active` và `sub` mà bỏ qua `iss` hoặc metadata issuer; response từ Authorization Server không được tin cậy có thể bị sử dụng.
Introspection endpoint trả `client_id` và `token_type` nhưng Resource Server không kiểm tra loại token; refresh token bị gửi nhầm vào API như access token.
Authorization Server phát opaque token có scope quá rộng cho mọi client nội bộ; Resource Server thực thi nguyên scope mà không giới hạn theo nghiệp vụ và principal.
Introspection response chứa nhiều audience nhưng Resource Server so sánh bằng phép substring; audience gần giống tên API cũng được chấp nhận.
API dùng `username` từ introspection để truy cập dữ liệu nhưng không ràng buộc `tenant_id`; người dùng có quyền ở tenant này có thể truy vấn tenant khác.
Một Resource Server dùng chung cache introspection cho nhiều tenant nhưng cache key chỉ là token hash; context tenant khác nhau có thể nhận nhầm kết quả authorization.
Cache introspection lưu kết quả `active: true` lâu hơn thời hạn token; sau khi token hết hạn, request vẫn được cho phép từ cache.
Token bị thu hồi tại Authorization Server nhưng Resource Server tiếp tục dùng cache positive chưa hết TTL; quyền truy cập vẫn tồn tại sau sự cố.
Nhóm vận hành đặt TTL cache introspection rất ngắn để giảm cửa sổ thu hồi; lưu lượng tăng khiến Authorization Server bị quá tải bởi số lần gọi introspection.
Cache âm lưu `active: false` quá lâu sau khi token được kích hoạt hợp lệ; người dùng tiếp tục bị từ chối dù Authorization Server đã cập nhật trạng thái.
Resource Server cache response theo chuỗi token thô làm token xuất hiện trong distributed cache key và công cụ giám sát cache.
Cache introspection bị chia sẻ giữa các region nhưng invalidation event không được truyền tới region dự phòng; token đã thu hồi vẫn hoạt động tại một vùng.
Authorization Server bị gián đoạn mạng; Resource Server chuyển sang fail-open và cho phép request khi không xác minh được trạng thái token.
Introspection endpoint timeout; Resource Server fail-closed nhưng không phân biệt lỗi tạm thời với token inactive, khiến toàn bộ giao dịch hợp lệ bị từ chối.
Resource Server retry introspection ngay lập tức nhiều lần khi Authorization Server quá tải; retry storm làm sự cố lan rộng và kéo dài thời gian phục hồi.
Client timeout ngắn hơn thời gian xử lý introspection bình thường; request hợp lệ thường xuyên bị từ chối dù Authorization Server vẫn hoạt động.
Resource Server không giới hạn số kết nối đồng thời tới introspection endpoint; attacker tạo nhiều request bằng token ngẫu nhiên để làm cạn connection pool.
Authorization Server trả HTTP 429 khi vượt quota introspection; Resource Server bỏ qua Retry-After và tiếp tục gửi request với tốc độ cũ.
Resource Server coi HTTP 500 từ introspection như response `active: false` nhưng không ghi nhận lỗi phụ thuộc; đội vận hành nhầm outage thành hàng loạt token hết hạn.
Authorization Server trả response JSON thiếu trường `active`; Resource Server mặc định giá trị null thành true để tương thích với phiên bản cũ.
Introspection response bị sửa trên đường truyền do Resource Server gọi endpoint qua HTTP nội bộ không mã hóa và không xác thực máy chủ.
Resource Server xác thực với introspection endpoint bằng một client secret dùng chung cho mọi service; khi một service bị lộ secret, attacker có thể introspect token ngoài phạm vi.
Client secret dùng gọi introspection được lưu trong file cấu hình và xuất hiện trong image registry; người có quyền đọc registry có thể giả danh Resource Server.
Authorization Server chỉ cho phép một Resource Server introspect token nhưng không kiểm tra danh tính client; client khác có thể dò trạng thái token và metadata người dùng.
Introspection endpoint trả nhiều claim cá nhân không cần thiết; Resource Server ghi toàn bộ response vào log và làm lộ thông tin danh tính.
Access token bị đưa vào URL query parameter trước khi gọi API; token xuất hiện trong browser history, proxy access log và header Referer.
Reverse proxy ghi nguyên header Authorization khi lỗi upstream; opaque bearer token còn hiệu lực bị lưu trong log mà không có cơ chế masking.
Token bị lộ trong log nhưng nhóm vận hành chỉ xóa dòng log mới nhất; bản sao trong log archive, SIEM và backup vẫn còn khả năng truy cập.
Một nhân viên hỗ trợ lấy opaque token từ ảnh chụp màn hình lỗi để tái hiện sự cố; token chưa bị thu hồi và vẫn cho phép truy cập dữ liệu khách hàng.
Resource Server không có inventory ánh xạ token tới subject, client, audience, scope và thời điểm phát hành; khi phát hiện rò rỉ không xác định được phạm vi cần thu hồi.
Authorization Server thu hồi token sau khi phát hiện compromise nhưng không có kênh thông báo tới Resource Server; hệ thống phụ thuộc hoàn toàn vào TTL cache để ngừng chấp nhận token.
Logout chỉ xóa token ở browser nhưng không revoke token tại Authorization Server; token bị sao chép trước đó vẫn hoạt động đến khi hết hạn.
Người dùng đổi mật khẩu sau khi nghi tài khoản bị chiếm nhưng Authorization Server không revoke các opaque access token và refresh token liên quan.
Token opaque được phát hành với thời hạn rất dài để giảm tần suất đăng nhập; khi token bị đánh cắp, cửa sổ lạm dụng kéo dài và phụ thuộc vào quy trình revoke.
Authorization Server lưu token lookup bằng hash yếu hoặc token entropy thấp; kẻ tấn công có thể dò token hợp lệ và gọi introspection để xác nhận.
Một ứng dụng phát token theo client credentials nhưng không ràng buộc token với workload cụ thể; nhiều dịch vụ dùng chung token nên không thể thu hồi riêng.
Token exchange cho phép đổi token của tenant A sang audience dùng chung mà không giữ nguyên tenant context; Resource Server có thể chấp nhận quyền sai tenant.
Authorization Server trả `scope` dưới dạng chuỗi phân tách khoảng trắng; Resource Server kiểm tra bằng substring nên `read:orders-admin` có thể bị coi như `read:orders`.
Resource Server nhận introspection response có `exp` theo Unix timestamp nhưng diễn giải nhầm đơn vị mili giây; token được coi là còn hiệu lực quá lâu hoặc hết hạn tức thì.
Đồng hồ giữa Authorization Server và Resource Server lệch nhau; logic áp dụng expiry và clock skew không thống nhất dẫn đến chấp nhận token quá hạn.
Authorization Server xoay client secret của Resource Server nhưng rollout không đồng bộ; một số instance không introspect được và nhóm vận hành tạm bật fail-open.
Blue-green deployment tạo hai phiên bản Resource Server với policy scope khác nhau; cùng một introspection response được diễn giải khác nhau tùy instance nhận request.
Resource Server không phân biệt token inactive với lỗi xác thực client khi gọi introspection; cảnh báo và quy trình xử lý sự cố không xác định đúng thành phần lỗi.
Attacker gửi token ngẫu nhiên liên tục để ép Resource Server gọi introspection; không có rate limit theo client hoặc nguồn nên Authorization Server bị DoS.
Audit log chỉ ghi endpoint được gọi mà không ghi client identity, token reference đã băm, audience, scope và kết quả introspection; không thể truy vết truy cập bất thường.
Một sự cố lộ opaque token được xử lý bằng cách tăng TTL cache để giảm tải Authorization Server; thao tác này vô tình kéo dài thời gian token bị thu hồi vẫn được chấp nhận.
Kiến trúc chọn opaque token để kiểm soát thu hồi tập trung qua introspection thay vì JWT tự xác minh cục bộ; nhóm chưa tính chi phí phụ thuộc Authorization Server, độ trễ và cache invalidation khi lưu lượng tăng.
