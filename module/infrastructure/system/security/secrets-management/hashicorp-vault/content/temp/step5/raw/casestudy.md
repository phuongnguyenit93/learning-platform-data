Một tổ chức vừa triển khai HashiCorp Vault cho production nhưng đội vận hành chưa thống nhất cách phân biệt Vault server, storage backend, seal mechanism và client; khi một node dừng, họ không xác định được thành phần nào giữ dữ liệu và thành phần nào xử lý request.
Trong lần khởi tạo cụm Vault mới, quản trị viên lưu toàn bộ unseal key shares và initial root token trong cùng một kho tài liệu nội bộ mà nhiều người có quyền đọc.
Một Vault cluster dùng Shamir seal với ngưỡng unseal ba trên năm; hai người giữ key shares nghỉ việc và tổ chức không còn đủ người để unseal sau khi toàn cụm khởi động lại.
Đội hạ tầng chuyển từ Shamir seal sang auto-unseal bằng cloud KMS nhưng cấu hình IAM của Vault node không cho phép giải mã seal key sau khi khôi phục từ bản sao lưu.
Cloud KMS được dùng cho auto-unseal gặp sự cố vùng khả dụng; Vault node mới không thể unseal và đội vận hành chưa có quy trình khôi phục hoặc kiểm tra quyền truy cập KMS dự phòng.
Một nhóm quản trị viên nhầm recovery keys của Vault dùng với auto-unseal là unseal keys; họ tìm cách dùng recovery keys để mở seal trong khi KMS vẫn hoạt động.
Vault cluster hiển thị trạng thái sealed sau khi thay đổi cấu hình storage; nhóm vận hành định xóa dữ liệu Raft để khởi động lại mà chưa xác minh quorum và khả năng phục hồi.
Một cụm Vault dùng Integrated Storage Raft có ba node nhưng hai node đặt cùng một failure domain; khi vùng đó mất kết nối, cụm không còn quorum để tiếp tục ghi dữ liệu.
Node Vault standby không chuyển tiếp request đúng cách sau khi active node thay đổi; các client tiếp tục gọi địa chỉ cũ và nhận lỗi trong quá trình failover.
Đội vận hành cần nâng cấp Vault server theo từng node trong cụm HA; quy trình hiện tại có thể dừng nhiều node cùng lúc và làm mất quorum Raft.
Một Vault cluster có listener TLS nhưng certificate server hết hạn; các workload từ chối kết nối, trong khi nhóm vận hành cân nhắc tắt xác minh TLS để khôi phục dịch vụ.
Vault được triển khai sau reverse proxy; proxy thay đổi header hoặc scheme của request khiến Vault tạo redirect sai và client không thể xác thực ổn định.
Nhóm bảo mật phát hiện client kết nối Vault bằng HTTP nội bộ vì cấu hình TLS bị bỏ qua ở một listener; bearer token và secret có nguy cơ đi qua mạng không mã hóa.
Quản trị viên dùng initial root token cho các tác vụ vận hành hằng ngày vì thuận tiện; token không có thời hạn ngắn và được chia sẻ giữa nhiều thành viên.
Một token Vault có TTL ngắn được dùng bởi tác vụ chạy dài; tác vụ không renew token trước khi hết hạn và các lần đọc secret giữa chừng bắt đầu trả lỗi.
Token periodic được cấp cho một dịch vụ nền nhưng quy trình giám sát không renew đúng hạn; dịch vụ mất quyền truy cập dù token vẫn được policy cho phép.
Một token service bị lộ trong log triển khai; đội ứng phó chỉ xóa log mà chưa dùng accessor hoặc cơ chế thu hồi phù hợp để vô hiệu token đã phát hành.
Nhóm vận hành tạo token orphan để phục vụ một tác vụ tự động; sau khi token parent bị thu hồi, token con vẫn còn hiệu lực lâu hơn dự kiến.
AppRole được dùng cho workload CI/CD nhưng SecretID có thời hạn dài, số lần sử dụng không giới hạn và không ràng buộc CIDR; một bản sao SecretID bị lấy từ runner dùng chung.
Pipeline bootstrap cần truyền SecretID cho một workload; nhóm đang gửi SecretID rõ qua biến pipeline và muốn thay bằng response wrapping có thời hạn ngắn.
Một workload Kubernetes xác thực với Vault bằng Kubernetes auth method nhưng Vault role ràng buộc sai service account hoặc namespace, khiến pod ngoài phạm vi cũng có thể lấy token.
Vault Kubernetes auth không thể xác minh service account token sau khi cluster xoay signing key; nhóm vận hành chưa cập nhật cấu hình issuer hoặc thông tin xác minh tương ứng.
Một workload trên cloud dùng IAM auth để lấy Vault token; policy trust cho phép nhiều instance role cùng xác thực và không phân biệt môi trường production với staging.
OIDC auth được cấu hình cho người vận hành Vault nhưng bound claims quá rộng; người dùng thuộc nhóm ngoài bộ phận quản trị vẫn đăng nhập được và nhận policy nhạy cảm.
Vault identity entity được tạo trùng khi cùng một người đăng nhập qua hai auth method; alias không được ánh xạ về cùng entity nên audit trail phân tán và quyền truy cập không nhất quán.
Một nhóm người dùng được gán policy thông qua identity group alias; khi IdP đổi group claim, ánh xạ cũ vẫn tồn tại và quyền của người đã rời nhóm không bị thu hồi.
Policy Vault cho phép read trên đường dẫn secret/* vì nhóm ứng dụng muốn truy cập nhanh; một workload có thể đọc secret của dịch vụ khác trong cùng mount.
Policy KV v2 được viết theo đường dẫn secret/team/* nhưng thiếu segment data hoặc metadata cần thiết; request đọc secret bị từ chối dù policy trông có vẻ đúng.
Một policy dùng wildcard và deny rule không bao phủ đúng đường dẫn; nhóm vận hành tưởng thao tác delete đã bị chặn nhưng token vẫn có khả năng xóa metadata của secret.
Quản trị viên cần cấp quyền chỉ đọc metadata secret cho nhóm kiểm toán; policy hiện tại vô tình cho phép đọc cả nội dung secret.
KV v2 được bật versioning nhưng nhóm ứng dụng xóa nhầm một version; họ nhầm soft delete với destroy và không biết dữ liệu còn có thể khôi phục hay không.
Một secret KV v2 được cập nhật đồng thời bởi hai pipeline; pipeline thứ hai ghi đè dữ liệu mới vì không dùng check-and-set để phát hiện version đã thay đổi.
Secret được tạo trong KV v1 trước đây; nhóm chuyển mount sang KV v2 nhưng client và policy vẫn sử dụng đường dẫn cũ nên một số thao tác đọc và xóa thất bại.
Một ứng dụng đọc secret từ KV v2 nhưng luôn lấy latest; lần triển khai mới ghi một version cấu hình lỗi và toàn bộ instance bắt đầu sử dụng giá trị không hợp lệ.
Database secrets engine tạo credential động cho mỗi workload; sau khi lease bị revoke, kết nối mới trong connection pool dùng credential cũ thất bại trong khi các kết nối đã mở vẫn tồn tại.
Lease của credential cloud sắp hết hạn nhưng workload không renew hoặc yêu cầu credential mới; nhóm vận hành cần phối hợp cập nhật cấu hình và đóng tài nguyên đang dùng credential cũ.
Vault database secrets engine cần rotate root credential của database nhưng tài khoản quản trị gốc đã bị đổi thủ công ngoài Vault; thao tác rotation thất bại và việc cấp credential động bị gián đoạn.
Một lease đã hết hạn nhưng backend không thu hồi được credential do database tạm ngừng hoạt động; credential cũ vẫn có thể đăng nhập và cần quy trình reconcile.
Nhóm nền tảng dùng Vault PKI secrets engine để cấp certificate cho dịch vụ nội bộ; role cho phép SAN quá rộng khiến workload có thể yêu cầu chứng thư cho hostname ngoài phạm vi quản lý.
Certificate do Vault PKI phát hành đã được gia hạn nhưng client vẫn nhận certificate cũ vì endpoint triển khai không reload file hoặc secret mount sau khi cập nhật.
Intermediate CA của Vault PKI sắp hết hạn; nhóm vận hành cần thay CA và cập nhật trust bundle cho các client mà không làm gián đoạn xác minh chain.
Một certificate bị nghi lộ private key nhưng tổ chức chưa rõ cách revoke qua Vault PKI, cập nhật CRL và bảo đảm các relying party kiểm tra trạng thái thu hồi.
Đội ứng dụng muốn dùng Vault Transit để mã hóa dữ liệu nghiệp vụ; họ loại bỏ tiền tố phiên bản khỏi ciphertext trả về nên không thể giải mã hoặc rewrap đúng định dạng về sau.
Transit key đã được rotate nhưng dữ liệu cũ vẫn mã hóa bằng version trước; nhóm vận hành cần rewrap ciphertext mà không giải mã plaintext ra khỏi vùng ứng dụng.
Một client có quyền gọi Transit decrypt được cấp policy quá rộng; client có thể giải mã ciphertext ngoài phạm vi dữ liệu của workload dù không đọc được khóa trong Vault.
Audit device của Vault ghi log ra file cục bộ nhưng đĩa đầy; request nhạy cảm bị lỗi và đội vận hành chưa có phương án dự phòng audit sink hoặc cảnh báo dung lượng.
Một Vault cluster bật hai audit device nhưng cả hai cùng ghi về một hệ thống lưu trữ đang mất kết nối; request bị ảnh hưởng và nhóm cần khôi phục audit path mà vẫn giữ khả năng truy vết.
Audit log chứa token accessor, path và metadata nhạy cảm; nhóm phân tích tập trung log nhưng quyền đọc log quá rộng và thời hạn lưu giữ chưa được xác định.
Vault Enterprise performance replication được cấu hình giữa hai site nhưng đội vận hành nhầm replication với backup; khi xóa nhầm secret, họ không có bản phục hồi độc lập.
Một cụm Vault cần disaster recovery sau khi site chính bị mất; bản snapshot Raft gần nhất đã cũ và nhóm chưa diễn tập quy trình restore, unseal và kiểm tra dữ liệu sau phục hồi.
Snapshot Raft được lưu ở object storage với quyền đọc quá rộng; người không thuộc đội vận hành có thể lấy bản sao trạng thái lưu trữ đã được Vault mã hóa và dùng nó trong một nỗ lực khôi phục trái phép nếu lấy được vật liệu giải mã phù hợp.
Một tổ chức dùng nhiều Vault namespace cho các đơn vị kinh doanh; policy và auth mount bị tạo ở namespace gốc thay vì namespace đích, làm rò rỉ quyền giữa các tenant.
Vault Agent được triển khai để auto-auth và render secret template; file đầu ra có permission quá rộng và các tiến trình không liên quan trên node có thể đọc credential.
Vault Agent template chưa được render lại sau khi secret nguồn đổi version; ứng dụng tiếp tục đọc credential cũ từ file đã render vì không có cơ chế refresh và reload phù hợp.
External Secrets workflow lấy secret từ Vault về Kubernetes Secret; quyền đọc mount quá rộng và bản sao trong cluster vẫn tồn tại sau khi secret nguồn bị xóa.
Một nhóm muốn tích hợp Vault với CI/CD; runner cần lấy secret đúng lúc deploy nhưng token hiện được lưu trong pipeline variable và tái sử dụng qua nhiều job.
Vault API trả lỗi 403 cho một workload sau khi policy thay đổi; nhóm vận hành chưa đối chiếu token identity, namespace, auth role và path capability để tìm nguyên nhân.
Vault API trả lỗi 429 trong đợt triển khai đồng loạt; client retry đồng bộ không có backoff hoặc jitter khiến tải tăng và các request hợp lệ tiếp tục bị throttling.
Một Vault cluster tăng trưởng nhanh về số lượng lease và secret version; nhóm vận hành chưa đặt retention, revoke và cleanup policy nên storage cùng thời gian backup và restore tăng.
Root token đã được tạo trong giai đoạn bootstrap nhưng chưa bị revoke sau khi hoàn tất cấu hình; token vẫn tồn tại trong tài liệu triển khai và có thể bị sử dụng ngoài ý muốn.
Một sự cố nghi ngờ Vault token bị lộ; đội phản ứng chưa biết token accessor, parent-child relationship và audit log nào cần dùng để xác định phạm vi rồi thu hồi an toàn.
Một tổ chức chuyển dữ liệu từ secret store cũ sang Vault; nhóm di chuyển secret bằng file tạm trên máy build và không có bước xác minh quyền, version, owner hoặc xóa bản sao trung gian.
Một nhóm tuân thủ cần chứng minh ai đã đọc, ghi, rotate hoặc revoke secret trong Vault; audit hiện chưa liên kết request với danh tính người dùng hoặc workload và ticket thay đổi tương ứng.
