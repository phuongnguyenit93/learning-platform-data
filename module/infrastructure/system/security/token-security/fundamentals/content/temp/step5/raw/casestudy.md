API nhận JWT từ client nhưng chỉ base64-decode payload để đọc `sub` và `role`, không xác minh chữ ký; token do attacker tự tạo vẫn có thể được dùng để gọi endpoint.
Một thư viện xác minh JWT chấp nhận thuật toán `none` khi header yêu cầu; hệ thống coi token không có chữ ký là hợp lệ.
Verifier hỗ trợ cả HMAC và RSA nhưng chọn thuật toán theo header của token; attacker lợi dụng nhầm lẫn giữa public key và shared secret để tạo chữ ký giả.
Ứng dụng dùng giá trị `kid` trong JWT header để ghép trực tiếp thành đường dẫn tệp khóa; token có `kid` được chế tạo có thể khiến verifier đọc tài nguyên ngoài thư mục khóa.
Dịch vụ xác minh chữ ký bằng JWKS nhưng không kiểm tra `iss`; token được ký bởi issuer khác có khóa tương thích vẫn có thể được chấp nhận.
API kiểm tra chữ ký và issuer nhưng không kiểm tra `aud`; access token phát cho một resource khác được dùng để gọi API hiện tại.
Verifier xử lý claim `aud` như một chuỗi đơn trong khi token hợp lệ có thể chứa danh sách audience; một audience không được phép lọt qua logic so sánh.
API chỉ kiểm tra `exp` nhưng bỏ qua `nbf` và `iat`; token được phát hành cho thời điểm tương lai hoặc có thời gian phát hành bất thường vẫn được sử dụng.
Đồng hồ giữa authorization server và resource server lệch nhiều phút; token hợp lệ bị từ chối ngẫu nhiên hoặc token hết hạn được chấp nhận lâu hơn dự kiến.
Resource server chấp nhận ID Token OIDC như access token vì cả hai đều là JWT; token chứng minh đăng nhập bị dùng sai mục đích để gọi API.
Ứng dụng kiểm tra access token hợp lệ nhưng không ràng buộc token với đúng API resource; token dành cho dịch vụ báo cáo được sử dụng tại dịch vụ quản trị.
Opaque access token được xác minh qua introspection endpoint; khi endpoint timeout, resource server mặc định coi token active để duy trì availability.
Resource server cache kết quả introspection quá lâu; token đã bị thu hồi vẫn được chấp nhận trong khoảng thời gian cache chưa hết hạn.
Opaque token được tạo bằng bộ sinh ngẫu nhiên yếu và có cấu trúc tuần tự; attacker thu thập một số token có thể dự đoán token tiếp theo.
Authorization server phát access token với scope `admin:*` cho mọi client nội bộ; quyền được cấp rộng hơn nhu cầu của từng ứng dụng.
API chỉ kiểm tra scope `orders:read` nhưng không kiểm tra chủ thể có quyền xem đơn hàng cụ thể; người dùng có thể truy cập đơn của tenant khác.
JWT chứa claim role được giữ nguyên sau khi người dùng bị hạ quyền; resource server không có cơ chế cập nhật hoặc thu hồi quyền trước khi token hết hạn.
Token có claim tenant ID hợp lệ về chữ ký nhưng backend lấy tenant từ request thay vì ràng buộc với tenant trong token; dữ liệu giữa các tenant có thể bị truy cập chéo.
Ứng dụng lưu bearer access token dài hạn trong localStorage; lỗ hổng XSS cho phép script cùng origin lấy token và gửi tới máy chủ attacker.
Ứng dụng lưu refresh token trong cookie có thể đọc bằng JavaScript; mã độc chạy trong trang có thể trích xuất token để duy trì quyền truy cập.
Frontend đưa access token vào query string để chuyển qua trang callback; token xuất hiện trong browser history, proxy log và header Referer.
Reverse proxy và hệ thống log ghi nguyên header Authorization khi request lỗi; nhiều nhóm vận hành có thể đọc bearer token còn hiệu lực.
Ứng dụng ghi refresh token vào crash dump và file chẩn đoán; bản dump được tải lên hệ thống hỗ trợ bên ngoài mà không có kiểm soát truy cập tương ứng.
Client mobile công khai được cấu hình một client secret cố định trong binary; attacker trích xuất secret từ ứng dụng và giả mạo client khi đổi authorization code.
Ứng dụng public client dùng Authorization Code Flow nhưng không bật PKCE; authorization code bị chặn có thể được đổi lấy token bởi client khác.
Authorization server chấp nhận redirect URI dùng wildcard subdomain; attacker đăng ký subdomain hoặc khai thác host bị chiếm để nhận authorization code.
Client sử dụng redirect endpoint có open redirect; authorization response được chuyển tiếp tới domain attacker sau khi người dùng xác thực.
Một client kết nối nhiều identity provider nhưng không ràng buộc response với issuer đã khởi tạo luồng; attacker có thể khai thác authorization server mix-up.
Luồng OIDC không kiểm tra `state` và `nonce`; response đăng nhập có thể bị gắn vào phiên trình duyệt khác hoặc assertion cũ được phát lại.
Authorization server phát refresh token thời hạn rất dài nhưng không rotation, không sender-constrain và không có quy trình thu hồi theo thiết bị.
Refresh token rotation đã bật nhưng server không phát hiện token cũ bị dùng lại; attacker tiếp tục sử dụng bản sao refresh token sau lần đổi hợp lệ.
Nhiều tab trình duyệt đồng thời dùng một refresh token; rotation coi request thứ hai là reuse và thu hồi cả token family, làm người dùng bị đăng xuất ngoài dự kiến.
Đăng xuất khỏi ứng dụng chỉ xóa access token phía client; refresh token phía server vẫn hoạt động và có thể cấp token mới.
Người dùng đổi mật khẩu sau khi nghi bị chiếm tài khoản nhưng authorization server không thu hồi refresh token hoặc phiên hiện có; attacker tiếp tục truy cập.
API dùng JWT self-contained và không có denylist hoặc cơ chế kiểm tra trạng thái; token bị đánh cắp vẫn hợp lệ cho tới khi `exp` hết hạn.
Token bearer bị sao chép từ máy bị nhiễm malware sang thiết bị khác; resource server không có bằng chứng ràng buộc token với client hợp lệ.
DPoP được triển khai nhưng resource server không kiểm tra `jti` đã dùng và thời gian proof; cùng một proof có thể bị replay trong cửa sổ chấp nhận.
Resource server kiểm tra DPoP proof nhưng không đối chiếu thumbprint khóa với claim `cnf` trong access token; proof từ khóa khác vẫn được chấp nhận.
Token được ràng buộc với mTLS certificate nhưng TLS termination proxy không chuyển tiếp danh tính certificate an toàn; backend không xác định đúng client sở hữu token.
Authorization server phát token có audience và scope phù hợp nhưng không ràng buộc token với client dự kiến qua `azp` hoặc policy tương đương; token bị dùng bởi client khác.
Workload dùng client credentials flow nhưng secret client được chia sẻ giữa nhiều dịch vụ; khi một workload bị xâm nhập, không thể thu hồi riêng credential của nó.
Token exchange được cấu hình cho phép đổi token đầu vào sang audience tùy ý; một workload có quyền thấp có thể yêu cầu token cho resource nhạy cảm.
JWT ký bằng khóa riêng lưu trong file cấu hình và file được mount cho mọi replica; compromise một container có thể lấy signing key và giả mạo token cho toàn hệ thống.
JWKS rotation diễn ra nhưng resource server cache khóa cũ không có cơ chế refresh khi gặp `kid` mới; token hợp lệ bị từ chối sau khi issuer đổi signing key.
Signing key cũ bị lộ nhưng issuer chỉ ngừng dùng key đó cho token mới; verifier vẫn tin khóa trong JWKS và chấp nhận token giả được ký bằng khóa đã compromise.
Ứng dụng dùng JWS và cho rằng payload JWT đã được mã hóa; dữ liệu cá nhân trong claims có thể được đọc bởi bất kỳ ai lấy được token.
JWT chứa email, nhóm và thông tin cá nhân không cần thiết; token được chuyển qua nhiều dịch vụ và làm tăng phạm vi dữ liệu có thể bị lộ.
API gateway giới hạn kích thước header nhưng token phình lớn do chứa quá nhiều group claims; request hợp lệ bị từ chối không nhất quán giữa các proxy.
Cookie chứa access token được gửi tự động theo request cross-site; ứng dụng không có CSRF protection phù hợp cho các thao tác thay đổi trạng thái.
CORS cho phép origin bất kỳ đọc response có credential; một website attacker có thể thực hiện request và đọc dữ liệu trong phiên người dùng.
Monitoring chỉ đếm số lần token validation thành công; không phát hiện một token được dùng đồng thời từ nhiều địa điểm hoặc nhiều thiết bị bất thường.
Đội ứng phó phát hiện bearer token bị lộ nhưng không có inventory ánh xạ token tới subject, client, audience, scope và thời điểm phát hành; phạm vi thu hồi không xác định được.
