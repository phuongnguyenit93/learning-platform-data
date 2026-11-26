Bạn sẽ xây dựng threat model cho dữ liệu lưu trữ bằng cách xác định tài sản, đối thủ, ranh giới tin cậy và kịch bản mất thiết bị như thế nào?
Bạn sẽ phân biệt encryption at rest với encryption in transit và access control về mục tiêu bảo vệ cùng giới hạn của từng lớp ra sao?
Bạn sẽ xác định những bản sao dữ liệu nào thuộc phạm vi at rest gồm dữ liệu chính, replica, snapshot, log, cache, file tạm và backup như thế nào?
Bạn sẽ lựa chọn mức mã hóa phù hợp theo độ nhạy cảm, thời gian lưu giữ, yêu cầu pháp lý và hậu quả khi khóa bị lộ ra sao?
Bạn sẽ phân biệt bảo vệ trước mất cắp thiết bị hoặc media với bảo vệ trước tài khoản quản trị hay ứng dụng đã bị xâm nhập như thế nào?
Bạn sẽ xác định trường hợp mã hóa toàn bộ ổ đĩa là đủ và trường hợp cần mã hóa ở tầng database hoặc ứng dụng ra sao?
Bạn sẽ đánh giá những rủi ro còn lại khi storage đã mã hóa nhưng dữ liệu đang được ứng dụng đọc ở dạng plaintext như thế nào?
Bạn sẽ thiết kế data classification và mapping mỗi loại dữ liệu với thuật toán, phạm vi mã hóa, thời hạn khóa và quyền truy cập ra sao?
Bạn sẽ xác định nơi cần mã hóa theo vòng đời dữ liệu từ ingest, xử lý, lưu trữ, replication, export đến xóa bỏ như thế nào?
Bạn sẽ giải thích full-disk encryption bảo vệ dữ liệu khi thiết bị tắt hoặc media bị tháo nhưng không ngăn người dùng đã đăng nhập truy cập ra sao?
Bạn sẽ so sánh full-disk encryption, partition encryption và file-level encryption theo phạm vi bảo vệ cùng khả năng vận hành như thế nào?
Bạn sẽ thiết kế quản lý khóa cho volume encryption để hỗ trợ boot, unlock tự động và phục hồi khi mất thiết bị ra sao?
Bạn sẽ đánh giá rủi ro khi khóa giải mã volume được lưu trên cùng thiết bị hoặc trong cấu hình có thể truy cập cùng dữ liệu như thế nào?
Bạn sẽ lựa chọn mã hóa filesystem hoặc volume cho máy chủ, laptop, thiết bị biên và môi trường cloud theo yêu cầu nào?
Bạn sẽ phân biệt mã hóa block storage ở tầng cloud provider với mã hóa trong guest operating system về ranh giới trách nhiệm ra sao?
Bạn sẽ giải thích transparent database encryption bảo vệ data file và transaction log ở tầng lưu trữ như thế nào?
Bạn sẽ phân biệt TDE với mã hóa cột, mã hóa trường ở tầng ứng dụng và mã hóa toàn bộ database về phạm vi plaintext ra sao?
Bạn sẽ xác định khi nào cần mã hóa một số cột nhạy cảm thay vì dựa hoàn toàn vào TDE như thế nào?
Bạn sẽ đánh giá ảnh hưởng của application-level encryption đến tìm kiếm, indexing, join, sorting và truy vấn dữ liệu ra sao?
Bạn sẽ thiết kế mã hóa cho database backup, transaction log, dump và snapshot để tránh bản sao lưu trở thành điểm yếu như thế nào?
Bạn sẽ xử lý replica hoặc read replica để bảo đảm dữ liệu sao chép luôn được bảo vệ bằng chính sách khóa phù hợp ra sao?
Bạn sẽ xác định metadata nào vẫn có thể bị lộ qua kích thước bản ghi, thời điểm truy cập, index hoặc pattern truy vấn dù payload đã mã hóa như thế nào?
Bạn sẽ thiết kế mã hóa object storage theo bucket, object hoặc tenant và xác định phạm vi áp dụng default encryption ra sao?
Bạn sẽ so sánh server-side encryption với customer-managed key và client-side encryption trong object storage như thế nào?
Bạn sẽ đánh giá SSE-S3, SSE-KMS và client-side encryption theo quyền kiểm soát khóa, khả năng kiểm toán và mô hình tin cậy ra sao?
Bạn sẽ bảo vệ object version, replica, lifecycle transition và archived object để không có bản sao nào bị bỏ sót khỏi chính sách mã hóa như thế nào?
Bạn sẽ thiết kế mã hóa cho file upload và file export khi dữ liệu đi qua staging bucket, processing worker và vùng lưu trữ cuối ra sao?
Bạn sẽ xử lý dữ liệu tạm trong /tmp, swap, pagefile, crash dump và scratch volume để giảm rò rỉ plaintext như thế nào?
Bạn sẽ xác định cách mã hóa cache, message spool và queue persistence khi chúng có thể chứa dữ liệu nhạy cảm ra sao?
Bạn sẽ lựa chọn secure deletion, crypto-erasure hoặc xóa vật lý khi cần chấm dứt khả năng truy cập dữ liệu đã mã hóa như thế nào?
Bạn sẽ giải thích vì sao xóa ciphertext mà vẫn giữ khóa có ý nghĩa khác với xóa hoặc hủy khóa giải mã ra sao?
Bạn sẽ lựa chọn authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305 để bảo đảm cả bí mật và tính toàn vẹn dữ liệu lưu trữ như thế nào?
Bạn sẽ phân biệt encryption có xác thực với encryption không xác thực và giải thích rủi ro khi ciphertext bị sửa đổi ra sao?
Bạn sẽ xác định cách lưu nonce hoặc IV cùng ciphertext và bảo đảm nonce đáp ứng yêu cầu riêng của chế độ AEAD như thế nào?
Bạn sẽ ngăn nonce reuse trong AES-GCM khi nhiều process hoặc region mã hóa đồng thời bằng cùng một khóa ra sao?
Bạn sẽ lựa chọn cách tạo nonce ngẫu nhiên hoặc bộ đếm có phân vùng để bảo đảm uniqueness trong hệ thống phân tán như thế nào?
Bạn sẽ sử dụng associated data để ràng buộc ciphertext với tenant ID, object ID, schema version hoặc loại bản ghi mà không mã hóa metadata đó ra sao?
Bạn sẽ xử lý lỗi xác thực AEAD khi giải mã để không trả plaintext một phần hoặc tiết lộ chi tiết giúp attacker phân biệt lỗi như thế nào?
Bạn sẽ thiết kế định dạng ciphertext có version, algorithm identifier, key identifier, nonce, tag và payload để hỗ trợ nâng cấp ra sao?
Bạn sẽ giải thích envelope encryption dùng DEK mã hóa dữ liệu và KEK bảo vệ DEK như thế nào?
Bạn sẽ phân biệt data encryption key, key-encryption key, wrapping key và root key trong hệ thống phân cấp khóa ra sao?
Bạn sẽ thiết kế key hierarchy nhiều tầng để giới hạn phạm vi ảnh hưởng khi một DEK hoặc KEK bị compromise như thế nào?
Bạn sẽ lựa chọn một DEK cho mỗi object, mỗi file, mỗi tenant hoặc mỗi data set dựa trên yêu cầu cô lập và chi phí nào?
Bạn sẽ giải thích vì sao không nên dùng trực tiếp master key KMS để mã hóa toàn bộ dữ liệu lớn thay vì dùng envelope encryption như thế nào?
Bạn sẽ thiết kế quy trình generate, wrap, unwrap và cache DEK để vừa giảm số lần gọi KMS vừa giới hạn plaintext key exposure ra sao?
Bạn sẽ bảo vệ DEK trong bộ nhớ ứng dụng và giảm thời gian tồn tại của plaintext key sau khi mã hóa hoặc giải mã như thế nào?
Bạn sẽ phân biệt key rotation với data re-encryption và giải thích việc xoay khóa KMS không tự động mã hóa lại mọi ciphertext cũ như thế nào?
Bạn sẽ thiết kế lazy re-encryption khi dữ liệu được đọc hoặc cập nhật để chuyển dần sang DEK/KEK mới ra sao?
Bạn sẽ lựa chọn rotation theo lịch, theo số lượng dữ liệu mã hóa hoặc theo sự kiện nghi ngờ compromise như thế nào?
Bạn sẽ quản lý key version và key identifier để ciphertext cũ vẫn giải mã được sau nhiều lần rotation ra sao?
Bạn sẽ xử lý rewrapping DEK khi thay KEK mà không cần giải mã rồi mã hóa lại toàn bộ payload như thế nào?
Bạn sẽ xác định khi nào phải re-encrypt dữ liệu bằng DEK mới thay vì chỉ rewrap DEK cũ như thế nào?
Bạn sẽ thiết kế KMS policy để workload chỉ được phép encrypt hoặc decrypt các key thuộc đúng tenant và mục đích được giao ra sao?
Bạn sẽ phân biệt quyền quản lý key, quyền sử dụng key và quyền quản trị dữ liệu để áp dụng separation of duties như thế nào?
Bạn sẽ lựa chọn cloud KMS, on-premises HSM hoặc phần cứng bảo vệ khóa theo yêu cầu chủ quyền dữ liệu, độ sẵn sàng và vận hành ra sao?
Bạn sẽ giải thích HSM bảo vệ key material và thực thi thao tác mật mã trong boundary phần cứng như thế nào?
Bạn sẽ đánh giá giới hạn của non-exportable key trong HSM khi ứng dụng vẫn có thể yêu cầu dịch vụ giải mã dữ liệu tùy ý ra sao?
Bạn sẽ thiết kế key provisioning và bootstrap trust giữa workload với KMS mà không lưu master credential dài hạn trong image như thế nào?
Bạn sẽ kiểm soát quyền decrypt theo workload identity, environment, tenant và context của request ra sao?
Bạn sẽ ngăn confused deputy khi một service có quyền KMS rộng thực hiện decrypt thay cho caller không đủ quyền như thế nào?
Bạn sẽ xác định cách tách quyền backup, restore, key administration và data access để một cá nhân không thể tự ý đọc hoặc hủy toàn bộ dữ liệu ra sao?
Bạn sẽ xử lý KMS outage hoặc giới hạn quota khi ứng dụng cần giải mã dữ liệu để phục vụ request quan trọng như thế nào?
Bạn sẽ lựa chọn cache plaintext DEK và thời gian cache dựa trên trade-off giữa latency, khả năng thu hồi và mức độ lộ khóa ra sao?
Bạn sẽ thiết kế multi-region key strategy để dữ liệu có thể phục hồi ở vùng dự phòng mà không mở rộng quyền giải mã quá mức như thế nào?
Bạn sẽ lập kế hoạch backup và recovery cho cả ciphertext lẫn key material, key metadata và policy cần thiết ra sao?
Bạn sẽ đánh giá rủi ro khi backup dữ liệu thành công nhưng key hoặc quyền truy cập KMS không được backup hoặc phục hồi tương ứng như thế nào?
Bạn sẽ thiết kế quy trình khôi phục khi KMS key bị disable, scheduled deletion hoặc mất quyền truy cập ngoài dự kiến ra sao?
Bạn sẽ phân biệt key deletion, key revocation, key disable và crypto-erasure về tác động đến dữ liệu đã mã hóa như thế nào?
Bạn sẽ kiểm chứng khả năng restore backup trong môi trường cô lập mà không làm lộ dữ liệu hoặc thay đổi khóa production ra sao?
Bạn sẽ thiết kế escrow hoặc dual control cho khóa phục hồi quan trọng để giảm nguy cơ một cá nhân làm mất hoặc lạm dụng khóa như thế nào?
Bạn sẽ xác định RPO và RTO cho key management service và kiểm tra chúng cùng quy trình khôi phục dữ liệu ra sao?
Bạn sẽ bảo vệ khóa trong memory dump, swap, crash report, debug log và công cụ hỗ trợ vận hành như thế nào?
Bạn sẽ thiết kế audit log cho key creation, encrypt, decrypt, unwrap, rotation, policy change và deletion mà không ghi lộ key material ra sao?
Bạn sẽ liên kết sự kiện KMS audit với danh tính workload, tenant, object và hoạt động nghiệp vụ để điều tra truy cập dữ liệu như thế nào?
Bạn sẽ phát hiện bất thường khi một workload đột ngột decrypt số lượng lớn object hoặc gọi KMS từ vùng triển khai lạ ra sao?
Bạn sẽ xây dựng cảnh báo cho key policy thay đổi, key bị disable, quyền decrypt mở rộng hoặc rotation thất bại như thế nào?
Bạn sẽ đánh giá tác động hiệu năng của mã hóa at rest qua throughput, latency, CPU, IOPS và chi phí gọi KMS ra sao?
Bạn sẽ tối ưu mã hóa cho dữ liệu lớn bằng streaming, chunking hoặc data key reuse mà vẫn kiểm soát nonce và key exposure như thế nào?
Bạn sẽ đánh giá overhead của AEAD tag, nonce, metadata và key wrapping đối với kích thước object nhỏ và số lượng object rất lớn ra sao?
Bạn sẽ đo hiệu năng full-disk, database TDE và application-level encryption bằng workload đại diện như thế nào?
Bạn sẽ thiết kế kiểm thử để xác minh ciphertext không thể đọc trực tiếp, tampering bị phát hiện và plaintext không rò vào log hoặc file tạm ra sao?
Bạn sẽ kiểm thử phân quyền KMS bằng các trường hợp đúng tenant, sai tenant, sai workload identity và policy bị thu hồi như thế nào?
Bạn sẽ xây dựng kiểm thử rotation để bảo đảm dữ liệu mới dùng key version mới và dữ liệu cũ vẫn giải mã được trong thời gian chuyển đổi ra sao?
Bạn sẽ diễn tập backup restore, key recovery và crypto-erasure để chứng minh quy trình bảo vệ dữ liệu hoạt động thực tế như thế nào?
Bạn sẽ đánh giá phạm vi bảo vệ thực tế của encryption at rest khi attacker lấy được database dump, snapshot, storage media hoặc quyền quản trị ứng dụng như thế nào?
Bạn sẽ thiết kế kiến trúc encryption at rest đầu cuối cho nền tảng nhiều tenant gồm phân loại dữ liệu, AEAD, envelope encryption, KMS/HSM, rotation, recovery, audit và kiểm chứng như thế nào?
