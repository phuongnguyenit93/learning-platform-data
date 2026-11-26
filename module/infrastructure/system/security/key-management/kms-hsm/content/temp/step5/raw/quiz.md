Vai trò chính của một KMS trong hệ thống là gì?
A. Quản lý khóa và thao tác mật mã theo policy.
B. Lưu mọi plaintext dữ liệu để ứng dụng truy vấn.
C. Thay thế toàn bộ hệ thống IAM của tổ chức.
D. Tự động loại bỏ mọi rủi ro từ ứng dụng sử dụng khóa.
Đáp án đúng: A

HSM tạo ra ranh giới bảo vệ nào cho khóa mật mã?
A. Một proxy mạng chỉ lọc request tới KMS.
B. Phần cứng bảo vệ key material và thao tác.
C. Một dịch vụ lưu metadata nhưng không xử lý khóa.
D. Một kho file mã hóa trên máy chủ ứng dụng.
Đáp án đúng: B

Mối quan hệ phổ biến giữa KMS và HSM trong dịch vụ managed là gì?
A. HSM chỉ sao lưu dữ liệu; KMS thực hiện mọi phép mã hóa.
B. HSM quản lý danh tính; KMS chỉ ghi audit log.
C. KMS thay thế HSM bằng kho lưu khóa dạng văn bản.
D. KMS quản lý chính sách; HSM bảo vệ và xử lý khóa.
Đáp án đúng: D

Trong kiến trúc KMS, thành phần nào thường thuộc control plane?
A. Tạo khóa, cấu hình policy và quản lý vòng đời.
B. Mã hóa payload theo từng request của ứng dụng.
C. Giải mã DEK trong luồng xử lý dữ liệu nghiệp vụ.
D. Tính tag AEAD cho từng khối dữ liệu đầu vào.
Đáp án đúng: A

Khi yêu cầu khóa không thể xuất khỏi HSM, thuộc tính nào cần được đặt?
A. Private key được lưu ở dạng plaintext trong backup.
B. Mọi principal có quyền đọc trực tiếp byte của khóa.
C. Key material được xuất tự động khi ứng dụng gọi encrypt.
D. Key material được tạo và giữ không thể export.
Đáp án đúng: D

FIPS 140-3 validation của HSM cho biết điều gì?
A. Nhà cung cấp được chứng nhận cho mọi sản phẩm mật mã.
B. Toàn bộ ứng dụng dùng HSM không còn lỗ hổng.
C. Module mật mã cụ thể đã được validation.
D. Mọi cấu hình triển khai đều tự động đạt chuẩn.
Đáp án đúng: C

Khi dùng cloud KMS, trách nhiệm nào thường thuộc khách hàng?
A. Bảo trì vật lý máy chủ HSM trong data center.
B. Thay firmware HSM theo lịch của nhà cung cấp.
C. Kiểm soát nhân sự vận hành hạ tầng cloud.
D. Khách hàng quản lý principal và key policy.
Đáp án đúng: D

Bring Your Own Key (BYOK) thường có nghĩa là gì?
A. Nhà cung cấp tạo khóa rồi gửi plaintext cho khách hàng.
B. KMS tự động đồng bộ private key sang mọi ứng dụng.
C. Khách hàng tạo key material rồi import vào KMS.
D. Khách hàng giữ key ngoài hệ thống và tự xử lý mọi crypto.
Đáp án đúng: C

Hold Your Own Key (HYOK) thường khác BYOK ở điểm nào?
A. Khách hàng tự giữ khóa ngoài dịch vụ KMS.
B. KMS giữ plaintext key còn HSM chỉ lưu bản sao.
C. Khóa được import vào KMS nhưng không cần policy.
D. Nhà cung cấp giữ khóa và khách hàng chỉ quản lý alias.
Đáp án đúng: A

Partition trong HSM chủ yếu hỗ trợ mục đích nào?
A. Tăng dung lượng ổ đĩa để lưu ciphertext ứng dụng.
B. Chia một private key thành nhiều file plaintext.
C. Tạo miền quản trị và truy cập được cách ly logic.
D. Thay thế kiểm soát quyền của từng ứng dụng gọi HSM.
Đáp án đúng: C

Một key ceremony an toàn thường cần kiểm soát nào?
A. Chia sẻ PIN quản trị qua email cho nhóm vận hành.
B. Bỏ audit để tránh lưu thông tin nhạy cảm về khóa.
C. Quy trình có ghi nhận và dual control.
D. Một quản trị viên tự tạo và giữ mọi bí mật khởi tạo.
Đáp án đúng: C

Vì sao nên tạo private key không thể export ngay trong HSM?
A. Loại bỏ nhu cầu xác thực người gọi thao tác ký.
B. Tạo private key trong HSM, giữ non-exportable.
C. Giúp ứng dụng đọc private key để tự ký offline.
D. Cho phép sao chép private key sang mọi vùng triển khai.
Đáp án đúng: B

Khi import key material vào HSM, biện pháp nào phù hợp?
A. Gửi key plaintext qua email rồi xóa hộp thư.
B. Dán key vào terminal dùng chung trong lúc bảo trì.
C. Import bằng key wrapping, kiểm tra nguồn gốc.
D. Lưu key tạm trên ổ đĩa rồi import khi thuận tiện.
Đáp án đúng: C

Key wrapping được dùng chủ yếu để làm gì?
A. Tạo chữ ký số để xác minh người gửi thông điệp.
B. Nén key material để giảm kích thước khi truyền mạng.
C. Bảo vệ key material bằng một khóa dùng để wrap.
D. Mã hóa payload nghiệp vụ thay cho mọi data key.
Đáp án đúng: C

Trong envelope encryption, vai trò của DEK và KEK là gì?
A. DEK và KEK cùng mã hóa payload theo hai lớp đối xứng.
B. KEK mã hóa payload; DEK xác minh chữ ký của dữ liệu.
C. DEK lưu audit; KEK xác thực principal gọi KMS.
D. DEK mã hóa dữ liệu; KEK wrap và bảo vệ DEK.
Đáp án đúng: D

Encryption context trong một số KMS có tác dụng nào?
A. Giữ bí mật metadata bằng cách mã hóa riêng context.
B. Thay thế key policy để cấp quyền decrypt tự động.
C. Ràng buộc ciphertext với metadata được xác thực.
D. Tạo nonce ngẫu nhiên và lưu nonce trong HSM.
Đáp án đúng: C

Khi decrypt yêu cầu encryption context không khớp, hệ thống nên làm gì?
A. Thử lần lượt context của các tenant lân cận.
B. Giải mã rồi ghi context mới vào ciphertext.
C. Bỏ qua context nếu principal có quyền decrypt.
D. Từ chối giải mã khi context không khớp.
Đáp án đúng: D

Vì sao plaintext DEK trong ứng dụng cần có thời gian tồn tại ngắn?
A. Để mọi tiến trình khác có thể tái sử dụng DEK.
B. Giảm thời gian key material nằm trong bộ nhớ.
C. Để tăng số lần gọi KMS trong mỗi request.
D. Để tránh phải lưu key version cùng ciphertext.
Đáp án đúng: B

Separation of duties trong quản trị KMS/HSM nhằm mục đích gì?
A. Cho một người toàn quyền tạo, dùng và xóa khóa.
B. Cho ứng dụng tự phê duyệt quyền decrypt của chính nó.
C. Loại bỏ vai trò auditor khỏi quy trình vận hành khóa.
D. Tách người quản trị policy khỏi người dùng khóa.
Đáp án đúng: D

Key policy và IAM policy nên được thiết kế theo nguyên tắc nào?
A. Chỉ kiểm tra tên hiển thị của ứng dụng gọi KMS.
B. Dùng quyền admin chung để tránh policy xung đột.
C. Cho phép mọi principal trong tài khoản gọi mọi thao tác.
D. Giới hạn principal, thao tác và tài nguyên theo nhu cầu.
Đáp án đúng: D

Một workload chỉ cần ký dữ liệu nên được cấp quyền nào?
A. Quyền sign trên đúng key được chỉ định.
B. Quyền export key material để ký ngoài hệ thống.
C. Quyền sign, decrypt và xóa mọi key trong project.
D. Quyền quản trị policy của toàn bộ HSM cluster.
Đáp án đúng: A

Quorum hoặc multi-party approval phù hợp nhất với thao tác nào?
A. Mọi request encrypt thông thường từ ứng dụng.
B. Mọi lần đọc metadata công khai của một key.
C. Khôi phục hoặc hủy khóa có kiểm soát.
D. Mọi lần xác minh chữ ký bằng public key.
Đáp án đúng: C

Vì sao KMS cần lưu key version hoặc key identifier cùng ciphertext?
A. Để chọn đúng phiên bản khóa khi giải mã dữ liệu cũ.
B. Để bỏ qua kiểm tra policy khi dữ liệu đã lưu lâu.
C. Để tự động chuyển ciphertext cũ sang thuật toán mới.
D. Để suy ra plaintext từ ciphertext mà không cần key.
Đáp án đúng: A

Automatic key rotation thường không tự thực hiện việc nào?
A. Cập nhật trạng thái phiên bản hiện hành của khóa.
B. Tạo phiên bản key material mới theo lịch cấu hình.
C. Mã hóa lại mọi ciphertext đã tạo bằng phiên bản cũ.
D. Giữ khả năng dùng phiên bản cũ cho thao tác được phép.
Đáp án đúng: C

Rewrap DEK khác re-encrypt payload ở điểm nào?
A. Rewrap thay lớp bảo vệ DEK, giữ payload ciphertext.
B. Rewrap giải mã toàn bộ dữ liệu rồi ghi plaintext mới.
C. Re-encrypt chỉ thay metadata mà không dùng khóa.
D. Hai thao tác luôn tạo ciphertext payload giống hệt nhau.
Đáp án đúng: A

Trước khi xóa key version cũ, cần xác minh điều gì?
A. Ứng dụng mới đã gọi encrypt bằng key version mới.
B. Số lượng request encrypt của key cũ bằng không trong ngày.
C. Alias đã được đổi tên trong giao diện quản trị.
D. Không còn dữ liệu, backup hoặc archive phụ thuộc khóa.
Đáp án đúng: D

Disable key và schedule deletion khác nhau như thế nào?
A. Hai trạng thái đều xóa ngay key material khỏi mọi bản sao.
B. Disable xóa key material; schedule deletion chỉ đổi alias.
C. Disable chỉ áp dụng cho public key; deletion cho private key.
D. Disable chặn sử dụng; schedule deletion đặt lịch hủy.
Đáp án đúng: D

Khi nghi ngờ key bị xâm phạm, bước kiểm soát ban đầu nào phù hợp?
A. Xóa audit log để tránh lộ thông tin về key.
B. Chặn sử dụng mới và điều tra phạm vi bị ảnh hưởng.
C. Tiếp tục dùng key đến hết kỳ rotation định sẵn.
D. Chỉ đổi alias nhưng giữ nguyên quyền và key material.
Đáp án đúng: B

Backup HSM an toàn cần có thuộc tính nào?
A. Bản backup được bảo vệ, tách biệt và kiểm soát truy cập.
B. Bản sao không mã hóa để rút ngắn thời gian restore.
C. Một tài khoản admin chung có thể tải backup bất kỳ lúc nào.
D. Bản plaintext key được lưu cạnh thiết bị chính.
Đáp án đúng: A

Kiểm thử restore HSM nên chứng minh điều gì?
A. Quản trị viên có thể đăng nhập vào giao diện thiết bị.
B. Khôi phục được key và thực hiện crypto operation cần thiết.
C. Thiết bị mới bật nguồn và hiển thị trạng thái online.
D. File backup tồn tại và có kích thước khác không.
Đáp án đúng: B

Trong cụm HSM HA, điều gì cần được đồng bộ có kiểm soát?
A. Plaintext DEK của mọi ứng dụng trên tất cả node.
B. Đồng bộ key state và policy giữa các node.
C. Mật khẩu người dùng cuối và session web của họ.
D. Toàn bộ dữ liệu nghiệp vụ đã được ứng dụng mã hóa.
Đáp án đúng: B

Khi KMS replication đa vùng bị gián đoạn, rủi ro nào cần kiểm soát?
A. Mọi key version cũ lập tức bị xóa khỏi vùng chính.
B. Các request sign được chuyển thành request encrypt.
C. Vùng dự phòng có thể thiếu key version hoặc policy mới.
D. Ciphertext tự động trở thành plaintext ở vùng còn lại.
Đáp án đúng: C

KMS không khả dụng và ứng dụng cần decrypt; hành vi nào an toàn hơn?
A. Retry có giới hạn; fail closed khi cần.
B. Gửi plaintext DEK qua kênh hỗ trợ để tiếp tục xử lý.
C. Chuyển sang key tĩnh yếu hơn được nhúng trong cấu hình.
D. Bỏ qua xác thực tag để duy trì khả năng đọc dữ liệu.
Đáp án đúng: A

Khi quota KMS cạn, client nên xử lý thế nào?
A. Retry liên tục không delay cho đến khi thành công.
B. Backoff có jitter và giới hạn retry theo ngân sách.
C. Tạo thêm key mới cho mỗi request bị từ chối.
D. Tắt circuit breaker để mọi request tiếp tục tới KMS.
Đáp án đúng: B

Audit event của thao tác KMS nên ghi những trường nào?
A. Chỉ tên sản phẩm KMS mà không có principal gọi.
B. Principal, key, thao tác, thời điểm và kết quả.
C. Chỉ mã HTTP phản hồi mà không có key identifier.
D. Plaintext key, secret token và dữ liệu đã giải mã.
Đáp án đúng: B

Tín hiệu nào có thể cho thấy khóa đang bị lạm dụng?
A. Decrypt tăng đột biến hoặc policy đổi bất thường.
B. Backup được kiểm tra theo lịch DR định kỳ.
C. Ứng dụng verify chữ ký theo lịch tải thông thường.
D. Key version mới được tạo theo rotation đã phê duyệt.
Đáp án đúng: A

Một HSM phát hiện tampering vật lý; phản ứng nào phù hợp?
A. Cô lập thiết bị và theo quy trình ứng phó tamper.
B. Tiếp tục dùng thiết bị cho đến kỳ bảo trì tiếp theo.
C. Tắt mọi audit để thiết bị không ghi thêm sự kiện.
D. Xuất private key ra ngoài trước khi kiểm tra thiết bị.
Đáp án đúng: A

PKCS#11 và KMIP thường được dùng để hỗ trợ điều gì?
A. Giao thức thay thế TLS để truyền dữ liệu ứng dụng.
B. Giao diện chuẩn để tích hợp thiết bị và quản lý khóa.
C. Cơ chế xác minh danh tính người dùng qua passkey.
D. Định dạng lưu trữ ciphertext cho mọi thuật toán AEAD.
Đáp án đúng: B

Crypto-agility trong nền tảng KMS/HSM đòi hỏi khả năng nào?
A. Xóa metadata thuật toán để tránh phụ thuộc nhà cung cấp.
B. Thay thuật toán hoặc nhà cung cấp có kiểm soát.
C. Tự chấp nhận thuật toán do request bên ngoài chỉ định.
D. Giữ một key version duy nhất cho toàn bộ dữ liệu lâu dài.
Đáp án đúng: B
