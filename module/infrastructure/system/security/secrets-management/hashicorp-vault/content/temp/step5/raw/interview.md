Bạn hãy mô tả kiến trúc tổng thể của HashiCorp Vault và vai trò của listener, storage backend, barrier encryption, secrets engine và auth method trong một request đọc secret như thế nào?
Vault xử lý một request từ lúc client gửi token đến khi policy được đánh giá và secrets engine trả dữ liệu như thế nào?
Bạn phân biệt seal, unseal và auto-unseal trong Vault ra sao, và mỗi trạng thái ảnh hưởng thế nào đến khả năng phục vụ request?
Unseal key shares và threshold được thiết kế như thế nào để cân bằng khả năng khôi phục với nguy cơ một cá nhân nắm quyền mở Vault?
Recovery keys trong mô hình auto-unseal khác unseal keys ở những điểm nào, và chúng được dùng trong các quy trình vận hành nào?
Bạn sẽ tổ chức quy trình khởi tạo Vault production, lưu recovery material và xử lý root token ban đầu như thế nào để giảm rủi ro lộ quyền tối cao?
Trong tình huống mất một số unseal key shares hoặc người giữ khóa rời tổ chức, bạn sẽ đánh giá khả năng khôi phục và thay đổi key shares ra sao?
Auto-unseal qua KMS hoặc HSM hoạt động ở mức kiến trúc như thế nào, và Vault phụ thuộc vào dịch vụ quản lý khóa bên ngoài ra sao khi khởi động?
Bạn sẽ đánh giá trade-off giữa Shamir seal và auto-unseal về bảo mật, vận hành, phụ thuộc bên ngoài và khả năng disaster recovery như thế nào?
Vault sử dụng TLS trên listener để bảo vệ client connection ra sao, và bạn sẽ quản lý certificate, trust chain, hostname verification cùng việc gia hạn như thế nào?
Khi triển khai Vault sau load balancer hoặc reverse proxy, bạn sẽ bảo đảm TLS termination, client identity và các header chuyển tiếp không làm sai lệch ranh giới tin cậy như thế nào?
Bạn mô tả mô hình High Availability của Vault với active node và standby node, cơ chế leader election và hành vi client khi active node thay đổi ra sao?
Bạn so sánh Integrated Storage dựa trên Raft với storage backend bên ngoài về vận hành, tính nhất quán, HA, backup và phục hồi như thế nào?
Trong một cụm Raft, quorum được duy trì ra sao và điều gì xảy ra khi mất kết nối mạng hoặc mất quá nửa số node?
Bạn sẽ chọn số lượng node và phân bố chúng qua failure domain như thế nào để giảm nguy cơ mất quorum mà vẫn kiểm soát độ trễ?
Bạn phân biệt snapshot của Integrated Storage, backup dữ liệu storage bên ngoài và replication trong Vault; mỗi cơ chế bảo vệ trước loại sự cố nào?
Bạn sẽ thiết kế quy trình kiểm tra restore snapshot định kỳ như thế nào để chứng minh backup có thể phục hồi được cả dữ liệu lẫn quyền truy cập cần thiết?
Bạn sẽ xử lý thế nào khi Vault khởi động nhưng không thể truy cập KMS/HSM đang cung cấp auto-unseal?
Bạn sẽ xây dựng kế hoạch nâng cấp Vault cluster để kiểm soát tương thích phiên bản, rolling restart, khả năng rollback và thời gian gián đoạn ra sao?
Auth method trong Vault giải quyết bài toán gì, và bạn phân biệt xác thực danh tính với authorization thông qua ACL policy như thế nào?
Bạn sẽ lựa chọn giữa AppRole, Kubernetes auth, cloud IAM auth, LDAP và OIDC cho từng loại workload hoặc người vận hành dựa trên tiêu chí nào?
AppRole gồm role_id và secret_id; bạn sẽ cấp phát, giới hạn số lần sử dụng, thời hạn và bảo vệ secret_id như thế nào?
Với Kubernetes auth, Vault xác minh service account token và ánh xạ workload vào Vault role ra sao, và bạn sẽ giới hạn namespace cùng service account như thế nào?
Với cloud auth, bạn sẽ xác minh workload identity hoặc instance identity để tránh phải lưu access key dài hạn trong máy chạy ứng dụng như thế nào?
Bạn sẽ thiết kế OIDC hoặc LDAP authentication cho nhân viên vận hành, bao gồm nhóm, mapping, MFA và thu hồi quyền khi tài khoản nguồn thay đổi ra sao?
Entity, alias và group trong Vault Identity giúp hợp nhất một danh tính qua nhiều auth method như thế nào, và bạn sẽ quản lý vòng đời các đối tượng đó ra sao?
Bạn sẽ thiết kế ACL policy theo path và capability để một workload chỉ đọc đúng secret path cần thiết mà không được liệt kê hoặc sửa các path khác như thế nào?
Bạn giải thích cách Vault kết hợp policy gắn với token và identity, cùng nguyên tắc deny-by-default và precedence của deny, như thế nào?
Khi viết ACL policy có wildcard hoặc path glob, bạn sẽ kiểm tra nguy cơ mở rộng quyền ngoài dự kiến và xác minh capability hiệu lực bằng cách nào?
Bạn sẽ phân tách quyền quản trị auth method, secrets engine, policy và token để tránh một nhóm vận hành có thể tự cấp quyền không giới hạn như thế nào?
Bạn sẽ thiết kế quy trình cấp token cho người dùng và workload, bao gồm TTL, max TTL, renewal, periodic token và thời điểm thu hồi ra sao?
Bạn phân biệt service token và batch token trong Vault, và sẽ chọn loại nào cho workload có nhu cầu renewal, accessor hoặc revocation như thế nào?
Token accessor hỗ trợ vận hành và kiểm toán ra sao, và bạn sẽ quản lý accessor để tránh nó trở thành một bí mật có thể bị lạm dụng như thế nào?
Parent-child token relationship ảnh hưởng đến việc thu hồi token và các token con như thế nào, và khi nào bạn cần token orphan?
Response wrapping giải quyết vấn đề chuyển giao secret bootstrap như thế nào, và bạn sẽ kiểm soát TTL, số lần unwrap và người nhận dự kiến ra sao?
Bạn sẽ xử lý thế nào khi phát hiện token Vault bị lộ, bao gồm xác định token accessor, thu hồi token, đánh giá lease và điều tra các request đã thực hiện?
Secrets engine được mount theo path và namespace như thế nào, và bạn sẽ tổ chức mount để phân tách môi trường, nhóm ứng dụng và vòng đời secret ra sao?
Bạn so sánh KV version 1 và KV version 2 về versioning, metadata, soft delete, destroy và khả năng khôi phục dữ liệu cũ như thế nào?
Với KV v2, bạn sẽ dùng check-and-set, version metadata và retention policy như thế nào để tránh ghi đè ngoài ý muốn và kiểm soát lịch sử secret?
Bạn sẽ thiết kế quyền đọc, ghi, list, delete, undelete và destroy trên KV v2 ra sao để giảm nguy cơ người dùng xóa vĩnh viễn secret?
Dynamic secrets khác static secrets ở vòng đời và rủi ro như thế nào, và lợi ích của việc cấp credential ngắn hạn cho workload là gì?
Bạn mô tả cách Database secrets engine tạo credential động từ role, policy và connection configuration, rồi thu hồi credential khi lease hết hạn như thế nào?
Bạn sẽ thiết kế quyền và tài khoản database nền mà Vault dùng để tạo, rotate và revoke credential động mà không trao quyền quản trị rộng hơn nhu cầu như thế nào?
Trong trường hợp database không khả dụng khi Vault cần thu hồi lease, bạn sẽ xử lý credential còn tồn tại và đánh giá rủi ro ra sao?
Bạn sẽ vận hành static role rotation cho tài khoản database hiện hữu như thế nào để đồng bộ thay đổi mật khẩu giữa Vault và hệ thống tiêu thụ?
Với cloud secrets engine, bạn sẽ giới hạn quyền của credential động theo account, project, role và thời hạn ra sao?
Lease trong Vault biểu diễn điều gì, và bạn phân biệt renew, revoke, revoke-prefix và expiration trong vòng đời secret như thế nào?
Bạn sẽ lựa chọn TTL và max TTL cho dynamic credential dựa trên thời gian xử lý, mức độ nhạy cảm và khả năng cấp lại như thế nào?
Khi một workload giữ credential lâu hơn TTL hoặc không thể renew lease, bạn sẽ thiết kế cơ chế refresh và xử lý lỗi xác thực ra sao?
Bạn sẽ sử dụng PKI secrets engine để tổ chức CA root, intermediate CA và certificate role như thế nào cho các dịch vụ nội bộ?
Bạn sẽ thiết kế certificate role để ràng buộc domain, SAN, key usage, TTL và danh tính được phép yêu cầu chứng chỉ như thế nào?
Bạn sẽ quản lý phát hành, gia hạn, thu hồi và phân phối certificate từ Vault PKI cho nhiều workload mà không làm gián đoạn kết nối như thế nào?
Khi intermediate CA hoặc private key ký chứng chỉ có dấu hiệu bị lộ, bạn sẽ khoanh vùng ảnh hưởng và chuyển đổi trust chain ra sao?
Bạn sẽ quản lý CRL, thời hạn certificate và quy trình cập nhật trust store ở các client như thế nào để việc thu hồi chứng chỉ có hiệu lực thực tế?
Transit secrets engine cung cấp encryption as a service khác gì với KV storage, và trong trường hợp nào dữ liệu mã hóa vẫn nằm hoàn toàn ở hệ thống ứng dụng?
Bạn sẽ chọn key type, key version và policy rotation cho Transit như thế nào để hỗ trợ mã hóa mới trong khi vẫn giải mã được ciphertext cũ?
Bạn sẽ thiết kế quyền encrypt, decrypt, rewrap, sign và verify cho Transit để tách biệt trách nhiệm giữa workload tạo dữ liệu và workload đọc dữ liệu như thế nào?
Bạn sẽ quản lý key rotation của Transit và đánh giá ảnh hưởng đến dữ liệu đã mã hóa, backup, client cache và quy trình khôi phục ra sao?
Audit device trong Vault ghi nhận request và response như thế nào, và bạn sẽ triển khai nhiều audit device để tăng khả năng truy vết ra sao?
Vault xử lý request như thế nào khi tất cả audit device đang cấu hình đều không ghi được log, và bạn sẽ thiết kế alert cùng vận hành để xử lý tình huống đó ra sao?
Bạn sẽ bảo vệ audit log khỏi sửa đổi hoặc xóa, kiểm soát quyền truy cập và lưu giữ bằng chứng phục vụ điều tra như thế nào?
Bạn sẽ đánh giá việc HMAC hoặc loại bỏ dữ liệu nhạy cảm trong audit log để cân bằng khả năng tương quan sự kiện với nguy cơ lộ secret ra sao?
Bạn sẽ theo dõi health, seal status, request latency, token usage, lease count, storage capacity và audit device để phát hiện vấn đề vận hành như thế nào?
Bạn sẽ thiết kế alert cho tình trạng unseal thất bại, Raft mất quorum, lease không thu hồi được, token bất thường và KMS latency ra sao?
Bạn phân biệt Performance Replication và Disaster Recovery Replication của Vault Enterprise, và sẽ chọn mô hình nào cho nhu cầu đa vùng như thế nào?
Bạn sẽ xử lý failover và failback của DR secondary cluster, bao gồm replication state, promotion, client endpoint và nguy cơ ghi dữ liệu ở hai nơi như thế nào?
Bạn sẽ xây dựng kế hoạch disaster recovery khi mất toàn bộ cluster chính, bao gồm snapshot, seal mechanism, KMS/HSM access, recovery material và kiểm thử định kỳ ra sao?
Bạn sẽ tích hợp Vault vào CI/CD để pipeline lấy secret ngắn hạn mà không ghi credential vào source code, build artifact hoặc log như thế nào?
Bạn sẽ cấp secret cho workload Kubernetes qua Vault Agent, Injector hoặc CSI integration như thế nào, và cách nào phù hợp với yêu cầu cập nhật secret mà không restart workload?
Bạn sẽ thiết kế quy trình bootstrap để workload lần đầu xác thực Vault mà không cần nhúng một credential dài hạn khác trong image hoặc manifest như thế nào?
Bạn sẽ phân tách quyền và path secret giữa development, staging và production khi nhiều pipeline hoặc workload cùng sử dụng một Vault cluster như thế nào?
Bạn sẽ xử lý secret rotation ở phía consumer để ứng dụng, job và dịch vụ cập nhật credential đúng lúc mà không tạo downtime hoặc tiếp tục dùng secret cũ như thế nào?
Bạn sẽ đánh giá rủi ro khi Vault trở thành dependency trung tâm cho nhiều ứng dụng, và thiết kế caching, retry, timeout cùng degraded mode ra sao?
Bạn sẽ xây dựng quy trình ứng phó khi phát hiện một policy bị cấu hình quá rộng hoặc một auth role bị chiếm dụng, từ containment đến audit và khôi phục như thế nào?
Bạn sẽ quản lý plugin, secrets engine và auth method tùy chỉnh để kiểm soát nguồn gốc, phiên bản, quyền thực thi và rủi ro chuỗi cung ứng ra sao?
Bạn sẽ đánh giá hiệu quả triển khai Vault bằng những chỉ số nào về secret inventory, credential lifetime, rotation coverage, policy drift, lease revocation và audit completeness?
