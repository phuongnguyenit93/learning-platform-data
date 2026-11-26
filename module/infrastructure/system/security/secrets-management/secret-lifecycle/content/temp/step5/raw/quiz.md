Mục đích chính của secret inventory là gì?
A. Theo dõi secret, owner, mục đích và nơi phụ thuộc.
B. Ghi mọi lỗi cấu hình đã được phát hiện trong hệ thống.
C. Liệt kê toàn bộ tài khoản người dùng theo phòng ban.
D. Lưu nội dung plaintext để nhóm hỗ trợ tra cứu nhanh.
Đáp án đúng: A

Một hồ sơ secret nên có thuộc tính nào để hỗ trợ quản trị vòng đời?
A. Tên người tạo và số lần chỉnh sửa tài liệu liên quan.
B. Owner, scope, consumer, trạng thái và thời hạn.
C. Địa chỉ IP của máy trạm đã yêu cầu secret lần đầu.
D. Chỉ giá trị secret và ngày gần nhất được sao chép.
Đáp án đúng: B

Khi một secret được nhiều workload cùng sử dụng, cách quản lý owner nào phù hợp?
A. Không cần owner nếu secret nằm trong vault tập trung.
B. Để mọi consumer tự quyết định thời hạn và quyền.
C. Gán owner là tài khoản dùng chung của toàn tổ chức.
D. Chỉ định owner chịu trách nhiệm và ghi rõ consumer.
Đáp án đúng: D

Cách nào phù hợp để tạo API key có entropy cao?
A. Sinh bằng CSPRNG với độ dài và uniqueness phù hợp.
B. Ghép tên dịch vụ với ngày tạo để dễ ghi nhớ.
C. Dùng bộ sinh giả ngẫu nhiên mặc định không kiểm tra seed.
D. Lấy hash của hostname làm key cố định cho workload.
Đáp án đúng: A

Khi nào nên ưu tiên dynamic credential thay cho secret tĩnh?
A. Khi mọi consumer phải dùng cùng một mật khẩu lâu dài.
B. Khi không thể xác định danh tính workload truy cập.
C. Khi credential cần được nhúng vào image để khởi động.
D. Khi hệ thống hỗ trợ cấp quyền ngắn hạn theo workload.
Đáp án đúng: D

Secret manager cần bảo vệ secret khi lưu trữ bằng cách nào?
A. Dùng hash không khóa để có thể khôi phục secret khi cần.
B. Chỉ Base64 encode giá trị trước khi ghi vào database.
C. Mã hóa at rest và giới hạn quyền đọc theo principal.
D. Đặt secret trong thư mục chia sẻ có quyền đọc toàn nhóm.
Đáp án đúng: C

Khi truyền secret từ vault tới workload, biện pháp nào phù hợp?
A. Gửi secret qua HTTP nội bộ vì mạng đã riêng tư.
B. Đặt secret trong query string để proxy tự định tuyến.
C. Ghi secret vào response header để dễ chẩn đoán lỗi.
D. Dùng kênh TLS và xác thực hai đầu theo policy.
Đáp án đúng: D

Secret zero mô tả vấn đề nào khi bootstrap workload?
A. Workload cần tạo secret thứ hai sau khi rotation.
B. Một secret đã bị revoke vẫn xuất hiện trong inventory.
C. Workload cần một trust anchor để lấy secret đầu tiên.
D. Vault không thể lưu secret có giá trị bằng số không.
Đáp án đúng: C

Cách nào giảm rủi ro secret zero khi nền tảng hỗ trợ?
A. Dùng workload identity hoặc federation để bootstrap.
B. Đưa secret đầu tiên vào repository dưới dạng Base64.
C. Nhúng bootstrap password dài hạn vào container image.
D. Dùng chung root token cho mọi workload trong cluster.
Đáp án đúng: A

Khi workload chỉ cần một secret trong thời gian ngắn, quyền nào phù hợp?
A. Quản trị vault để tự xử lý mọi lỗi truy cập.
B. List và read toàn bộ secret trong môi trường production.
C. Read đúng secret và giới hạn theo thời gian.
D. Read, update và delete mọi secret thuộc project.
Đáp án đúng: C

Environment variable có thể làm lộ secret qua con đường nào?
A. Chỉ cho phép kernel đọc và không thể bị dump.
B. Ngăn mọi tiến trình cùng quyền xem cấu hình process.
C. Process inspection, crash dump hoặc chẩn đoán.
D. Tự động mã hóa giá trị trước khi process khởi chạy.
Đáp án đúng: C

Khi cần phân phối secret qua file mount, cấu hình nào giảm rủi ro?
A. Sao chép file secret vào image để tránh mount lúc chạy.
B. Giới hạn filesystem permission và phạm vi mount.
C. Mount read-write vào volume dùng chung cho mọi container.
D. Đặt file trong thư mục tạm có quyền đọc toàn máy.
Đáp án đúng: B

Vì sao không nên lưu secret production trong file cấu hình được commit?
A. Git tự động chuyển mọi secret thành public key.
B. File cấu hình không thể được đọc bởi pipeline CI/CD.
C. Git history và bản clone có thể giữ secret lâu dài.
D. Secret trong Git sẽ tự hết hạn khi branch bị xóa.
Đáp án đúng: C

Pull request từ fork không tin cậy nên được xử lý thế nào với secret?
A. Chỉ mask log nhưng vẫn truyền secret vào tiến trình.
B. Dùng credential của maintainer để chạy mọi pull request.
C. Không cấp secret production cho job chạy mã từ fork.
D. Cấp toàn bộ secret để kiểm thử giống production.
Đáp án đúng: C

Vì sao Docker build argument không phù hợp để truyền secret build?
A. Build argument tự được xóa khỏi mọi cache sau build.
B. Build argument luôn bị mã hóa bởi registry khi push.
C. Build argument chỉ tồn tại trong RAM của máy build.
D. Giá trị có thể lưu trong image layer hoặc metadata.
Đáp án đúng: D

Secret scanner phát hiện key trong Git history đã push; hành động nào cần ưu tiên?
A. Chỉ xóa dòng chứa key khỏi commit mới nhất.
B. Đổi tên branch và giữ nguyên credential hiện tại.
C. Revoke hoặc rotate key rồi rà soát lịch sử và bản sao.
D. Đánh dấu cảnh báo false positive nếu commit đã bị revert.
Đáp án đúng: C

Khi cấu hình secret scanning, làm sao giảm false positive mà vẫn giữ phát hiện?
A. Chỉ quét file có phần mở rộng .env trong repository.
B. Bỏ qua chuỗi entropy cao nếu không khớp một mẫu cố định.
C. Tắt scanner với mọi file cấu hình và script triển khai.
D. Dùng rule theo ngữ cảnh và quy trình review ngoại lệ.
Đáp án đúng: D

Secret trong log, trace hoặc error report nên được xử lý thế nào?
A. Chuyển header nhạy cảm vào span attribute để điều tra.
B. Redact giá trị trước khi ghi hoặc chuyển tiếp telemetry.
C. Ghi đầy đủ giá trị nhưng giới hạn quyền xem dashboard.
D. Chỉ mã hóa log sau khi secret đã được ghi plaintext.
Đáp án đúng: B

Vì sao không nên truyền secret trong URL query string?
A. Query string luôn bị loại khỏi mọi proxy access log.
B. TLS không bảo vệ URL path nhưng bảo vệ query riêng.
C. URL query được browser mã hóa bằng khóa của máy chủ.
D. URL có thể lưu trong log, history và referrer.
Đáp án đúng: D

Một API key bị lộ công khai; bước phản ứng đầu tiên nào phù hợp?
A. Chỉ xóa bài đăng có chứa key khỏi nơi công khai.
B. Tạo ticket rồi đợi kỳ rotation theo lịch tiếp theo.
C. Chờ điều tra xong toàn bộ mới vô hiệu hóa key.
D. Revoke key bị lộ và ngăn các lần sử dụng mới.
Đáp án đúng: D

Sau khi revoke secret bị lộ, hoạt động nào vẫn cần thực hiện?
A. Điều tra truy cập, tác động và credential liên quan.
B. Bỏ qua consumer vì secret manager đã báo revoke thành công.
C. Đóng sự cố ngay vì credential cũ đã mất hiệu lực.
D. Xóa audit log cũ để tránh lưu dữ liệu nhạy cảm.
Đáp án đúng: A

Rotation có overlap period nhằm giải quyết vấn đề nào?
A. Cho phép secret cũ và mới tồn tại vô thời hạn.
B. Tránh phải xác minh consumer đã nhận secret mới.
C. Cho consumer chuyển sang secret mới không gián đoạn.
D. Giữ credential cũ hoạt động sau khi đã bị compromise.
Đáp án đúng: C

Trước khi revoke secret cũ sau rotation, cần xác minh điều gì?
A. Consumer đã chuyển và không còn dùng giá trị cũ.
B. Alias đã đổi tên dù process vẫn giữ credential cũ.
C. Lịch rotation kế tiếp đã được ghi vào tài liệu vận hành.
D. Secret mới đã được tạo trong vault dù chưa phân phối.
Đáp án đúng: A

Rotation theo sự kiện phù hợp nhất khi nào?
A. Khi secret được đọc thành công theo lịch bình thường.
B. Chỉ khi hết số ngày cố định trong chính sách.
C. Khi có dấu hiệu lộ, thay đổi quyền hoặc thay owner.
D. Khi số lượng consumer tăng nhưng quyền không thay đổi.
Đáp án đúng: C

Một dynamic credential có lease cần được workload xử lý ra sao?
A. Theo dõi TTL, renew hợp lệ hoặc lấy credential mới.
B. Lưu credential vĩnh viễn sau lần cấp đầu tiên.
C. Tiếp tục dùng credential sau lease expiry mà không kiểm tra.
D. Gia hạn lease bằng cách tự sửa thời hạn trong vault.
Đáp án đúng: A

Lease của database credential hết hạn nhưng connection pool còn kết nối mở; cần xem xét gì?
A. Thu hồi hoặc đóng session hiện có theo chính sách.
B. Kết nối mở luôn bị database ngắt ngay khi lease hết hạn.
C. Không cần xử lý vì credential chỉ được kiểm tra lúc query.
D. Chỉ đổi password trong vault là mọi session tự đóng.
Đáp án đúng: A

Revocation của một secret cần được truyền tới thành phần nào?
A. Chỉ dashboard giám sát vì request sau sẽ tự bị từ chối.
B. Chỉ inventory vì consumer tự đọc trạng thái từ đó.
C. Chỉ source repository vì secret ban đầu được tạo ở đó.
D. Vault, cache, gateway và consumer đang giữ bản sao.
Đáp án đúng: D

Secret manager nên xử lý cache secret theo nguyên tắc nào?
A. Cache vô thời hạn để vault outage không ảnh hưởng.
B. Dùng chung cache giữa các tenant để tiết kiệm bộ nhớ.
C. Không ghi version vì cache luôn chứa giá trị mới nhất.
D. TTL ngắn, quyền hẹp và invalidation có kiểm soát.
Đáp án đúng: D

Một secret đã bị revoke xuất hiện lại sau restore backup; cần cơ chế nào?
A. Đổi tên secret để tránh trùng với trạng thái cũ.
B. Áp dụng trạng thái revocation và version tombstone sau restore.
C. Cho phép consumer tự quyết định secret nào còn đáng tin.
D. Khôi phục nguyên trạng mọi secret từ backup gần nhất.
Đáp án đúng: B

Khi hai nhóm cập nhật cùng một secret gần như đồng thời, cơ chế nào giúp tránh ghi đè?
A. Dùng cùng timestamp để hợp nhất hai giá trị bí mật.
B. Dùng version hoặc optimistic concurrency check.
C. Cho phép lần ghi cuối luôn thắng mà không cần audit.
D. Xóa version cũ trước khi nhận giá trị mới.
Đáp án đúng: B

Audit log về secret nên ghi gì để hỗ trợ điều tra mà không làm lộ giá trị?
A. Principal, secret ID, action, thời điểm và kết quả.
B. Plaintext secret, token và toàn bộ request body.
C. Chỉ tên vault mà không có principal hoặc action.
D. Nội dung secret đã mask một phần nhưng vẫn tái dựng được.
Đáp án đúng: A

Break-glass access tới secret production nên có kiểm soát nào?
A. Một tài khoản dùng chung không ghi nhận người thao tác.
B. Lý do, phê duyệt, thời hạn và hậu kiểm độc lập.
C. Bỏ audit trong thời gian khẩn cấp để xử lý nhanh hơn.
D. Quyền đọc vĩnh viễn cho nhóm trực sự cố.
Đáp án đúng: B

Khi nào nên dùng credential riêng cho từng môi trường?
A. Khi mọi môi trường nằm trong cùng một tài khoản cloud.
B. Khi cần cô lập quyền và giới hạn blast radius.
C. Khi muốn giảm số lượng secret phải quản lý.
D. Khi staging cần dùng đúng key production để giống thật.
Đáp án đúng: B

Secret do vendor cấp nên được quản lý theo cách nào?
A. Ghi owner, scope, expiry và quy trình revoke.
B. Dùng chung key vendor cho nhiều đối tác tích hợp.
C. Không rotate vì vendor là bên tạo credential.
D. Lưu key trong ticket để cả hai bên dễ tra cứu.
Đáp án đúng: A

Hủy secret an toàn cần xem xét những bản sao nào?
A. Backup, replica, cache, artifact và thiết bị consumer.
B. Chỉ file gốc đã được dùng để import secret.
C. Chỉ bản secret đang được một workload active đọc.
D. Chỉ giá trị hiện tại trong giao diện secret manager.
Đáp án đúng: A

Khi secret manager mất kết nối, lựa chọn vận hành nào phù hợp?
A. Cache mọi secret vô thời hạn cho đến khi vault phục hồi.
B. Theo mức rủi ro, dùng cache có TTL hoặc fail closed.
C. Chuyển sang credential admin nhúng sẵn để tiếp tục.
D. Bỏ xác thực trong lúc vault không khả dụng.
Đáp án đúng: B

Chỉ số nào giúp đo hiệu quả ứng phó khi secret bị lộ?
A. Số lượng secret được tạo trong một tháng.
B. Thời gian từ phát hiện tới revoke trên mọi consumer.
C. Tổng dung lượng database lưu metadata secret.
D. Số người có quyền truy cập dashboard của vault.
Đáp án đúng: B
