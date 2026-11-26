Một tổ chức đặt root CA online cùng các dịch vụ phát hành chứng thư để tiện vận hành; nếu máy chủ bị xâm nhập, attacker có thể chiếm khóa gốc và giả mạo toàn bộ chuỗi tin cậy.
Subordinate CA được cấp quyền ký chứng thư cho mọi loại tên miền và mục đích; compromise của CA trung gian có thể vượt quá phạm vi mà tổ chức dự định ủy quyền.
Root CA đặt pathLenConstraint bằng zero nhưng vẫn ký một intermediate CA khác; chứng thư con không phù hợp với giới hạn đường dẫn và cần bị từ chối khi xác minh.
Intermediate CA thiếu Basic Constraints CA:TRUE nhưng vẫn được cấu hình làm issuer; relying party không được phép coi chứng thư đó là CA hợp lệ.
CA certificate có Basic Constraints CA:TRUE nhưng Key Usage không cho phép keyCertSign; chuỗi chứng thư bị từ chối do extension không phù hợp với vai trò ký CA.
CA phát hành server certificate với EKU chỉ cho clientAuth; TLS server sử dụng chứng thư này nhưng client kiểm tra mục đích và từ chối.
Server certificate có Key Usage chỉ cho digitalSignature trong khi bộ mã hóa hoặc giao thức được cấu hình đòi keyEncipherment; chứng thư không đáp ứng mục đích sử dụng đã chọn.
CSR do máy chủ gửi lên chứa SAN cho một hostname ngoài quyền quản lý của requester; RA chỉ xác thực người gửi mà không kiểm tra quyền sở hữu tên.
RA chấp nhận Subject CN từ CSR nhưng bỏ qua SAN; certificate được cấp cho tên trong CN không khớp hostname mà TLS client thực tế xác minh.
Nhóm cấp chứng thư wildcard cho *.example.com để tiện triển khai; phạm vi wildcard bao phủ nhiều subdomain có mức tin cậy và chủ sở hữu khác nhau.
CA nhận public key từ enrollment request nhưng bỏ qua xác minh chữ ký CSR; chứng thư có thể được cấp cho khóa mà requester không chứng minh được quyền kiểm soát.
CA dùng một certificate profile chung cho server, client, code signing và email; EKU, Key Usage và policy OID không phản ánh đúng mục đích từng loại chứng thư.
Chứng thư CA có Name Constraints giới hạn namespace nhưng relying party bỏ qua extension khi xây dựng path; chứng thư ngoài miền tên được phép vẫn có thể được chấp nhận.
Certificate Policy OID trong chứng thư không khớp chính sách mà relying party yêu cầu; ứng dụng chỉ kiểm tra chain nên chấp nhận chứng thư sai assurance level.
CA cấp chứng thư với serial number trùng trong cùng issuer do nhiều node phát hành không phối hợp; việc tra cứu, thu hồi và kiểm toán trở nên mơ hồ.
Chứng thư được ký bằng SHA-1 để tương thích thiết bị cũ; relying party tiếp tục tin thuật toán chữ ký đã lỗi thời dù hệ thống có thể nâng cấp.
Public key trong chứng thư quá ngắn hoặc dùng curve không được chính sách cho phép; chứng thư vẫn có chain hợp lệ nhưng không đạt yêu cầu thuật toán hiện hành.
TLS client chỉ kiểm tra certificate chain mà không so hostname với Subject Alternative Name; chứng thư hợp lệ của domain khác có thể bị dùng để giả mạo endpoint.
Relying party tin chứng thư tự ký chỉ vì chữ ký self-signature hợp lệ; self-signature không tự làm certificate trở thành trust anchor được tin cậy.
Trust store trên một nhóm máy trạm không được cập nhật khi tổ chức thay root CA; các máy này từ chối chứng thư mới dù server đã triển khai đúng chain.
Intermediate certificate không được gửi trong TLS handshake và client không thể tải AIA; một số thiết bị không xây dựng được chain dù chứng thư leaf còn hạn.
Server gửi intermediate sai thứ tự hoặc gửi nhầm intermediate cùng Subject nhưng khác key; client xây dựng path không hợp lệ và báo lỗi trust chain.
Cross-signed intermediate tạo ra nhiều đường dẫn tới root khác nhau; một số client chọn path hết hạn hoặc trust anchor không còn được chấp nhận.
Ứng dụng chỉ kiểm tra chữ ký từng certificate mà không kiểm tra path constraints, validity, policy và trust anchor; chain có thể được chấp nhận sai.
Private CA cấp chứng thư nội bộ nhưng trust anchor được cài thủ công không kiểm soát trên từng máy; tổ chức không thể chứng minh máy nào đang tin root nào.
Quy trình enrollment xác minh danh tính bằng email nhưng email alias có thể được tái cấp cho nhân viên khác; chứng thư mới có thể gắn với sai chủ thể.
RA xác minh yêu cầu qua ticket nhưng không lưu người phê duyệt, bằng chứng domain control và profile được dùng; audit không thể tái dựng căn cứ cấp phát.
CA phát hành chứng thư server với SAN chứa cả tên production và staging; private key bị lộ ở môi trường ít tin cậy có thể ảnh hưởng endpoint production.
Private key TLS được lưu dưới dạng file không mã hóa trong image triển khai; người có quyền đọc registry hoặc image layer có thể lấy khóa trước khi workload khởi động.
Khóa riêng CA được lưu trong HSM nhưng quyền ký được cấp cho tài khoản quản trị dùng chung; không thể quy hành động ký chứng thư về cá nhân hoặc quy trình cụ thể.
Backup HSM không được kiểm thử khôi phục và thiếu quorum custodians; khi thiết bị chính hỏng, CA không thể phục hồi signing key để vận hành.
Root CA ceremony không có phân tách nhiệm vụ hoặc biên bản kiểm soát; một cá nhân có thể tạo, sử dụng và sao lưu khóa gốc mà không có giám sát độc lập.
Private key của intermediate CA bị nghi lộ nhưng tổ chức chỉ gia hạn leaf certificate; attacker vẫn có thể phát hành chứng thư giả bằng CA trung gian bị compromise.
CA compromise xảy ra nhưng kế hoạch ứng phó không xác định thứ tự cô lập, revoke intermediate, thông báo relying party và thay trust anchor; các hệ thống tiếp tục tin chuỗi bị xâm phạm.
Chứng thư mới được phát hành trước khi chứng thư cũ hết hạn nhưng client cache chain cũ; rollout không có giai đoạn overlap khiến kết nối gián đoạn.
Certificate renewal tạo chứng thư mới nhưng giữ nguyên private key đã nghi bị lộ; gia hạn validity không khắc phục compromise của key material.
Quy trình gia hạn tự động tạo key pair mới nhưng không cập nhật public key pinning hoặc allowlist ở đối tác; dịch vụ bị gián đoạn sau khi certificate đổi.
ACME client dùng HTTP-01 challenge sau reverse proxy nhưng proxy rewrite đường dẫn challenge; CA không xác minh được domain control và renewal thất bại.
ACME DNS-01 credential có quyền sửa toàn bộ zone DNS; compromise máy chủ cấp chứng thư cho phép attacker thay đổi bản ghi của nhiều domain.
ACME automation được triển khai nhưng không giám sát rate limit và lỗi challenge; nhiều lần retry làm hết quota trước khi chứng thư production hết hạn.
Certificate inventory chỉ theo dõi chứng thư trong load balancer; certificate ở thiết bị mạng, SaaS, database, workload và ứng dụng cũ không được quản lý.
Monitoring chỉ cảnh báo chứng thư sắp hết hạn theo ngày cố định; không theo dõi issuer, SAN, owner, môi trường hoặc trạng thái renewal nên cảnh báo không tới đúng nhóm phụ trách.
Chứng thư đã được gia hạn tại CA nhưng một số node không reload file hoặc secret; cluster trình bày lẫn chứng thư cũ và mới cho client.
Certificate deployment ghi đè file hiện tại trước khi kiểm tra chain và private key match; lỗi triển khai khiến dịch vụ không thể khởi động TLS.
Private key và certificate được cập nhật không nguyên tử; trong khoảng thời gian rollout, tiến trình đọc key mới cùng certificate cũ và handshake thất bại.
CRL được phát hành nhưng relying party dùng bản CRL đã quá thời hạn nextUpdate; trạng thái thu hồi không còn đủ mới để đưa ra quyết định tin cậy.
CRL quá lớn vì CA phát hành số lượng chứng thư lớn và không dùng delta CRL hoặc phân vùng hợp lý; thiết bị hạn chế bộ nhớ không tải hoặc xử lý kịp.
CRL Distribution Point trỏ tới URL nội bộ chỉ một số mạng truy cập được; client bên ngoài không tải được CRL và áp dụng chính sách revocation không nhất quán.
Chứng thư bị revoke nhưng serial number được tra trong CRL của sai issuer; relying party không phát hiện trạng thái thu hồi của certificate.
OCSP responder trả trạng thái unknown cho chứng thư hợp lệ do không đồng bộ database CA; client hard-fail khiến kết nối bị từ chối hàng loạt.
OCSP responder ngừng hoạt động và client áp dụng soft-fail mà không ghi nhận telemetry; chứng thư đã revoke có thể tiếp tục được chấp nhận trong thời gian outage.
OCSP response có chữ ký hợp lệ nhưng thisUpdate/nextUpdate không được kiểm tra; response cũ có thể được replay để che trạng thái thu hồi mới.
OCSP stapling không được cấu hình cho một số virtual host; một số client phải tự truy vấn responder, làm lộ thói quen kết nối và tăng phụ thuộc vào availability bên ngoài.
Chứng thư client mTLS có chain hợp lệ nhưng server chỉ kiểm tra CA mà không ánh xạ SAN hoặc URI SAN vào workload identity; client bất kỳ từ CA nội bộ có thể được tin quá rộng.
mTLS xác minh danh tính workload bằng certificate nhưng ứng dụng coi mọi certificate hợp lệ là quyền admin; xác thực danh tính bị nhầm với quyết định authorization.
Client certificate được cấp cho thiết bị nhân viên đã mất nhưng không được revoke; thiết bị hoặc người nhặt được credential vẫn có thể xác thực với dịch vụ nội bộ.
Certificate có EKU clientAuth và SAN đúng nhưng thuộc tenant khác; gateway không kiểm tra mapping tenant nên cho phép truy cập chéo tenant.
TLS server chấp nhận certificate chain hợp lệ nhưng không kiểm tra key usage, EKU hoặc policy OID phù hợp; chứng thư dành cho mục đích khác vẫn được dùng để xác thực server.
Certificate pinning chỉ lưu một public key duy nhất trong ứng dụng; khi CA hoặc key cần rotate khẩn cấp, client cũ không có pin dự phòng và không thể kết nối.
Relying party tải trust store từ endpoint không xác thực trong quá trình cập nhật; attacker có thể thêm trust anchor giả để chặn hoặc giả mạo TLS.
CA database và audit log không được backup đồng bộ; sau sự cố, tổ chức có certificate đã phát hành nhưng không còn hồ sơ issuance để quản lý revocation.
Private CA được khôi phục từ backup cũ nhưng serial counter và issuance database không được đồng bộ; CA có thể phát hành serial trùng hoặc không biết chứng thư đã cấp.
Root CA rollover không có kế hoạch phân phối trust anchor mới và giai đoạn tin cậy song song; thiết bị offline tiếp tục chỉ tin root cũ sau thời điểm chuyển đổi.
Chính sách PKI không quy định thời hạn tối đa, key algorithm, EKU và quy trình revoke theo loại tài sản; các CA và nhóm ứng dụng cấp chứng thư với mức bảo vệ không đồng nhất.
Đội vận hành đo số lượng certificate sắp hết hạn nhưng không đo renewal success, revocation latency, chain validation failure và key compromise; sức khỏe PKI không được phản ánh đầy đủ.
