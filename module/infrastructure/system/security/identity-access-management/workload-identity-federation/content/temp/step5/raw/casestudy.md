Trong pipeline CI/CD, token OIDC có claim `sub` chứa repository và ref nhưng trust policy chỉ kiểm tra tên repository; pull request từ fork hoặc branch không được bảo vệ vẫn có thể yêu cầu vai trò triển khai production.
Một pipeline xử lý pull request từ fork được cấp quyền yêu cầu OIDC ID token; mã do contributor kiểm soát có thể lấy token của job và thử assume deployment role.
Điều kiện trust chấp nhận mọi ref dạng `refs/heads/*`, bao gồm branch thử nghiệm và branch chưa qua bảo vệ, để nhận vai trò triển khai.
CI issuer phát token với audience mặc định khác audience được cloud federation provider cấu hình, khiến token exchange thất bại dù chữ ký hợp lệ.
Staging và production dùng cùng audience chung; token từ pipeline staging có thể được chấp nhận bởi trust relationship của production.
Trust policy kiểm tra `iss` nhưng bỏ qua `sub` và `aud`, khiến workload khác do cùng issuer phát hành cũng có khả năng nhận role.
Bộ xác minh kiểm chữ ký qua JWKS nhưng không kiểm `iss`, `aud`, `exp` và `nbf`; token đúng chữ ký nhưng sai issuer hoặc đã hết hạn vẫn được chấp nhận.
OIDC discovery metadata của issuer được thay đổi sang `jwks_uri` ngoài dự kiến; relying party vẫn tự động tải khóa mới mà không rà soát cấu hình tin cậy.
Nhà cung cấp xoay signing key và thay `kid`; verifier cache JWKS cũ khiến token hợp lệ bị từ chối trong thời gian cache chưa cập nhật.
Issuer xóa khóa cũ khỏi JWKS ngay sau rotation trong khi token ký bằng khóa đó còn thời hạn, gây lỗi xác minh ở relying party vừa làm mới cache.
Job CI bật debug và ghi toàn bộ OIDC token vào log; log được chia sẻ rộng và token vẫn còn hiệu lực khi bị lộ.
Self-hosted runner tái sử dụng workspace giữa các job không cùng mức tin cậy; job sau có thể đọc tệp hoặc tiến trình còn sót token từ job trước.
Reusable workflow thay đổi cách tạo subject claim; trust condition vẫn dùng mẫu cũ quá rộng nên workflow khác có thể assume deployment role.
Role production được gán theo claim branch `main` nhưng không kiểm tra claim environment hoặc bước phê duyệt release; pipeline bất kỳ trên main có thể deploy production.
Claim `repository` hoặc `sub` không được ràng buộc với tổ chức cụ thể; repository khác cùng issuer có thể trùng mẫu trust condition.
Kubernetes projected service-account token có audience `kubernetes.default.svc`, trong khi cloud STS yêu cầu audience riêng; workload không thể đổi token sang cloud credentials.
Pod không cần truy cập Kubernetes API vẫn tự động mount service-account token do cấu hình mặc định, tạo thêm credential có thể bị đánh cắp.
Trust mapping dùng wildcard namespace cho subject `system:serviceaccount:*:deployer`; workload trong namespace mới có thể nhận cloud role triển khai.
Hai tenant trong cluster có service-account cùng tên; trust policy chỉ so sánh tên service-account mà bỏ qua namespace nên danh tính bị nhập nhằng.
Người dùng có quyền tạo Pod nhưng không có quyền trực tiếp dùng service account đặc quyền; họ vẫn tạo Pod mới tham chiếu service account đó và lấy workload identity.
RBAC cho phép nhóm vận hành tạo `serviceaccounts/token` cho mọi service account; quyền này bị lạm dụng để mint token của workload đặc quyền.
Cluster vẫn chứa legacy service-account token Secret không hết hạn dù workload đã chuyển sang projected token ngắn hạn; token cũ bị lộ trong bản backup.
Nhiều ứng dụng dùng chung một Kubernetes service account được federate tới role có quyền trên nhiều cloud resource; compromise một Pod ảnh hưởng toàn bộ ứng dụng.
Metadata endpoint của node có thể truy cập từ mọi Pod; workload không được phép vẫn lấy được node identity hoặc token có quyền rộng.
Khi federation thất bại, ứng dụng âm thầm fallback sang node role hoặc static credential; sự cố trust policy bị che giấu và quyền truy cập rộng vẫn tồn tại.
Token exchange tại STS ánh xạ mọi subject của một issuer vào role quản trị dự án, vì điều kiện role mapping không phân biệt repository, namespace hoặc workload.
Principal được ánh xạ dựa trên claim email có thể thay đổi hoặc tái sử dụng; nhân sự mới nhận email cũ có thể thừa hưởng quyền của workload identity cũ.
Trust mapping dựa trên claim do pipeline tự truyền qua input có thể bị contributor kiểm soát; giá trị claim bị thao túng để chọn role cao hơn.
Điều kiện trust dùng phép so khớp chuỗi con `main` thay vì so khớp ref chính xác; branch tên `feature/main-cleanup` cũng được chấp nhận.
Verifier xử lý `aud` như chuỗi đơn trong khi issuer phát danh sách audience; logic so sánh bỏ sót trường hợp audience không được cho phép.
Đồng hồ trên runner lệch vài phút so với issuer; token hợp lệ bị từ chối do `nbf` hoặc `exp` trong một số job.
Token OIDC có thời hạn ngắn nhưng được lưu trong artifact debug và tái sử dụng bởi job khác trong cùng thời gian hiệu lực.
Kubernetes xoay projected token file nhưng process giữ token cũ trong memory; workload bắt đầu nhận lỗi exchange sau khi token cũ hết hạn.
STS trả cloud access token tạm thời nhưng workload ghi token vào volume dùng chung giữa container tin cậy và container không tin cậy.
Job build/test được cấp quyền yêu cầu OIDC token giống job deploy; script chạy trong bước test có thể lấy quyền triển khai dù không cần thiết.
Trust relationship của production chấp nhận issuer và subject từ môi trường preview; pull request có thể tạo preview workload rồi yêu cầu production identity.
Role được assume qua federation có policy wildcard trên mọi resource và quyền quản trị IAM; danh tính workload bị xâm nhập dẫn tới leo thang quyền.
Thay đổi trust policy bằng Infrastructure as Code được triển khai mà không review diff hoặc audit; điều kiện audience và subject vô tình bị nới rộng.
Repository CI bị xâm nhập; nhóm ứng phó thu hồi trust relationship nhưng các access token ngắn hạn đã phát hành vẫn còn hiệu lực trong thời gian còn lại.
OIDC discovery/JWKS endpoint tạm thời không truy cập được; hệ thống tự bỏ qua xác minh chữ ký để pipeline tiếp tục chạy, mở đường chấp nhận token giả.
Cloud audit log chỉ ghi role đã assume mà không ghi subject, issuer, repository, namespace và deployment run; đội điều tra không thể quy hành động về workload cụ thể.
CI job có quyền yêu cầu token với audience tùy ý; mã độc xin token cho một cloud service khác mà trust policy chấp nhận.
Kubernetes token được ràng buộc với Pod object nhưng relying party chỉ kiểm subject service account; token bị sao chép khỏi Pod vẫn được dùng ngoài workload gốc.
Một issuer CI được tin cậy bởi nhiều cloud account; trust policy ở account mới chỉ kiểm issuer và bỏ qua tenant, repository hoặc project đích.
Môi trường ephemeral tạo namespace và service account theo tên branch; wildcard subject cho phép workload preview nhận role dùng chung với môi trường thật.
Tổ chức đã chuyển sang federation nhưng vẫn giữ static service account key trong secret manager để dự phòng; key dài hạn không có owner và chưa được thu hồi.
Workload chạy ngoài Kubernetes cần federation nhưng provider chỉ map theo hostname runner; nhiều runner không cùng mức tin cậy có thể assume cùng role.
Một pipeline tạo ID token cho deployment nhưng không ràng buộc `workflow_ref` hoặc commit SHA; workflow đã bị thay đổi vẫn dùng được trust rule của bản phát hành trước.
Subject claim chứa branch name có ký tự hoặc encoding khác nhau; policy normalization không thống nhất khiến một số branch bị match sai.
Nhóm bảo mật yêu cầu chứng minh quyền truy cập của mỗi workload được cấp theo least privilege; hiện tại không có inventory ánh xạ issuer, subject, audience và role.
