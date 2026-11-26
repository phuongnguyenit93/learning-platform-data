Một tổ chức thanh lý máy chủ database cũ sau khi chuyển workload lên cloud; ổ đĩa được tháo khỏi rack nhưng trước đó volume chưa từng được mã hóa và có thể đọc trực tiếp trên thiết bị khác.
Một máy chủ bật full-disk encryption và tự động mở khóa khi boot; kẻ tấn công chiếm được tài khoản quản trị đang đăng nhập nên vẫn đọc được dữ liệu plaintext qua ứng dụng.
Một workload cloud dùng mã hóa block storage do nhà cung cấp quản lý; snapshot được chia sẻ sang tài khoản khác để phục vụ điều tra và nhóm bảo mật không rõ ai có thể giải mã bản sao đó.
Một cụm database đã bật transparent data encryption nhưng DBA có quyền truy vấn trực tiếp vẫn xem được toàn bộ thông tin khách hàng ở dạng plaintext.
Một ứng dụng mã hóa số định danh ở tầng application trước khi ghi database; sau triển khai, chức năng tìm kiếm chính xác và báo cáo nhóm theo trường này không còn hoạt động như trước.
Một hệ thống dùng mã hóa cột cho dữ liệu thẻ thanh toán nhưng khóa giải mã được đặt trong cùng file cấu hình với thông tin kết nối database.
Một nền tảng đa tenant dùng chung một database và một khóa mã hóa cho mọi tenant; sự cố lộ khóa ở một service khiến dữ liệu của tất cả khách hàng có nguy cơ bị đọc.
Một dịch vụ lưu file trên object storage đã bật default server-side encryption; một số bucket cũ và object được copy từ hệ thống legacy vẫn không có mã hóa theo policy mới.
Một bucket lưu hồ sơ khách hàng dùng customer-managed KMS key; quyền decrypt được cấp cho toàn bộ role trong tài khoản cloud khiến ranh giới giữa các tenant không còn rõ.
Một pipeline đồng bộ object sang region dự phòng nhưng KMS key ở region đích không có policy cho replication role, khiến bản sao đã truyền tới nơi nhưng không thể giải mã khi failover.
Một tổ chức mã hóa database backup nhưng quên mã hóa export file do công cụ báo cáo tạo ra; file được đẩy lên thư mục chia sẻ nội bộ có quyền đọc rộng.
Một hệ thống sao lưu volume mã hóa chỉ bảo vệ disk đang chạy; bản snapshot được tạo bằng một workflow khác không kế thừa thiết lập encryption nên chứa dữ liệu đọc được.
Một nhóm vận hành khôi phục database từ backup sang môi trường staging; backup đã mã hóa nhưng staging không có quyền truy cập key cần thiết nên quá trình restore bị dừng giữa chừng.
Một ứng dụng ghi request payload nhạy cảm vào file tạm để xử lý batch; thư mục tạm nằm trên volume không mã hóa và các file còn tồn tại sau khi job kết thúc.
Một máy chủ bật mã hóa ổ đĩa nhưng swap và crash dump được ghi sang một thiết bị khác không mã hóa; dữ liệu nhạy cảm từ RAM có thể xuất hiện trong các bản dump.
Một container ghi dữ liệu xử lý vào ephemeral volume; node bị tái sử dụng cho workload khác và nhóm vận hành không xác định được dữ liệu cũ đã được xóa hoặc crypto-erased chưa.
Một dịch vụ ghi cache và message queue persistence xuống đĩa với dữ liệu khách hàng chưa mã hóa; đội phát triển cho rằng chỉ database mới thuộc phạm vi encryption at rest.
Một hệ thống phân tích tạo search index và data warehouse từ database đã mã hóa; các bản sao index lưu giá trị nhạy cảm ở dạng plaintext để hỗ trợ tìm kiếm nhanh.
Một hệ thống mã hóa từng bản ghi bằng AES-GCM nhưng khi đọc dữ liệu không xác minh authentication tag trước khi trả plaintext cho caller.
Một dịch vụ mã hóa object dùng AES-GCM với nonce ngẫu nhiên; nhiều worker cùng một key xử lý hàng tỷ object và không có theo dõi hoặc bảo đảm nonce không trùng.
Một cụm mã hóa phân tán tạo nonce bằng counter trong bộ nhớ từng node; sau khi pod restart, counter bắt đầu lại và một số nonce bị tái sử dụng dưới cùng một key.
Một hệ thống dùng AES-GCM cho dữ liệu nhiều tenant nhưng không đưa tenant ID hoặc object ID vào associated data; ciphertext bị chuyển nhầm giữa hai bản ghi vẫn có thể được xác thực.
Một ứng dụng mã hóa theo chunk để stream file lớn; các chunk không ràng buộc thứ tự hoặc vị trí trong authenticated metadata nên có thể bị tráo đổi mà không phát hiện đúng ngữ cảnh.
Một API giải mã dữ liệu từng phần và gửi dần ra client trước khi xác minh tag cuối cùng; payload bị sửa đổi khiến một phần plaintext đã thoát khỏi hệ thống.
Một hệ thống lưu ciphertext nhưng không lưu algorithm version, nonce format hoặc key identifier; sau lần nâng cấp thư viện, dữ liệu cũ không còn được giải mã nhất quán.
Một đội phát triển tự thiết kế định dạng mã hóa riêng để giảm kích thước metadata; các phiên bản service khác nhau diễn giải IV, tag và byte order không giống nhau.
Một ứng dụng dùng encryption không xác thực cho trường dữ liệu quan trọng; attacker có thể sửa ciphertext và hệ thống nhận plaintext biến đổi mà không phát hiện tampering.
Một nền tảng dùng cùng một key cho mã hóa dữ liệu, ký webhook và tạo MAC cho token; khi một thành phần bị xâm nhập, các mục đích bảo mật khác cũng bị ảnh hưởng.
Một dịch vụ dùng envelope encryption tạo DEK cho từng object nhưng lưu DEK dạng plaintext cạnh ciphertext trong cùng object metadata.
Một hệ thống envelope encryption bọc DEK bằng KEK trong KMS; khi migrate object sang tenant khác, wrapped DEK được giữ nguyên dù policy của tenant mới không cho phép sử dụng key cũ.
Một tổ chức dùng một DEK chung cho hàng triệu bản ghi để giảm số lần gọi KMS; khi nghi ngờ DEK bị lộ, phạm vi dữ liệu cần mã hóa lại quá lớn.
Một hệ thống xoay KEK trong KMS nhưng chỉ cập nhật key alias; các DEK cũ vẫn được bọc bằng key version trước và nhóm vận hành không có inventory để theo dõi.
Một quy trình rewrap DEK chạy hàng loạt bị gián đoạn giữa chừng; một phần dữ liệu tham chiếu key version cũ, phần còn lại dùng key version mới nhưng trạng thái migration không được ghi nhận.
Một dịch vụ lazy re-encryption cập nhật ciphertext khi đọc dữ liệu; hai request đồng thời đọc và ghi cùng bản ghi khiến một bản cập nhật dùng key mới bị ghi đè bởi ciphertext cũ.
Một ứng dụng cache plaintext DEK trong bộ nhớ worker nhiều giờ để giảm latency; quyền decrypt của workload bị thu hồi nhưng worker vẫn tiếp tục dùng key đã cache.
Một nhóm phát triển cấp quyền KMS decrypt cho role của toàn bộ microservice để tránh lỗi permission; một service ít tin cậy có thể yêu cầu giải mã object ngoài phạm vi nghiệp vụ.
Một API backend có quyền decrypt rộng nhận yêu cầu từ nhiều tenant nhưng không kiểm tra quyền trên object ID; backend trở thành confused deputy cho caller không đủ quyền.
Một KMS key policy cho phép principal từ tài khoản cloud khác sử dụng key; thay đổi trust relationship không được review và dữ liệu backup có thể bị giải mã ngoài tổ chức.
Một hệ thống dùng HSM lưu master key nhưng ứng dụng vẫn gửi lệnh decrypt tùy ý với dữ liệu do người dùng điều khiển; việc giữ key non-exportable không ngăn lạm dụng quyền sử dụng key.
Một cụm dịch vụ phụ thuộc KMS đồng bộ cho từng bản ghi; khi KMS tăng latency hoặc chạm quota, throughput database giảm mạnh và request bắt đầu timeout hàng loạt.
Một vùng cloud bị mất kết nối tới KMS trong sự cố mạng; workload đang chạy vẫn có dữ liệu cần đọc nhưng không có chính sách cache hoặc chế độ degraded được xác định.
Một KMS key bị disable sau cảnh báo bảo mật; hệ thống không phân biệt được thao tác disable tạm thời với key bị xóa nên các job restore và truy vấn production đồng loạt thất bại.
Một quản trị viên đặt lịch xóa KEK trong KMS để dọn tài nguyên cũ; sau đó phát hiện backup dài hạn vẫn phụ thuộc vào KEK đó và không còn bản sao key hợp lệ.
Một tổ chức lưu backup ciphertext ở nhiều region nhưng chỉ lưu key metadata và quyền truy cập KMS trong region chính; thảm họa vùng làm mất cả đường khôi phục.
Một quy trình disaster recovery kiểm tra backup file định kỳ nhưng không thực hiện restore thực tế cùng key và policy tương ứng; đến khi sự cố xảy ra, dữ liệu không thể giải mã.
Một doanh nghiệp dùng chung một master key để mã hóa dữ liệu production và staging; bản dump staging bị chia sẻ rộng khiến phạm vi rủi ro của khóa production tăng lên.
Một quy trình crypto-erasure xóa DEK của một tenant nhưng DEK đó thực tế được dùng chung để mã hóa dữ liệu của nhiều tenant khác.
Một hệ thống cần đáp ứng yêu cầu lưu giữ dữ liệu nhiều năm; key rotation xóa key version cũ quá sớm khiến hồ sơ hợp lệ không thể giải mã trong thời hạn lưu trữ.
Một đội vận hành khôi phục khóa từ bản backup HSM nhưng không có quy trình dual control hoặc phê duyệt kép; một cá nhân có thể tự phục hồi và sử dụng master key.
Một KMS audit log chỉ ghi số lần gọi encrypt/decrypt mà không gắn principal, workload, tenant hoặc resource ID; nhóm điều tra không thể xác định service nào đã giải mã dữ liệu bất thường.
Một dashboard giám sát ghi nguyên request metadata của thao tác decrypt, bao gồm wrapped key và một số trường nhạy cảm; audit pipeline trở thành nguồn rò rỉ mới.
Một hệ thống phát hiện số lượng decrypt tăng đột biến nhưng không có baseline theo workload và tenant; cảnh báo bị bỏ qua vì các batch hợp lệ cũng tạo nhiều request.
Một nhóm kiểm thử chỉ xác nhận ứng dụng có thể mã hóa rồi giải mã lại dữ liệu; họ không thử sửa ciphertext, nonce, tag hoặc associated data để kiểm tra khả năng phát hiện tampering.
Một bản cập nhật mã hóa thay đổi cách tạo nonce nhưng không có test tương thích với ciphertext cũ; dữ liệu đã lưu trước đó không thể đọc sau khi rollout.
Một dịch vụ mã hóa file lớn theo từng chunk nhưng retry có thể ghi đè chunk đã mã hóa bằng nonce cũ; sau sự cố mạng, cùng nonce xuất hiện hai lần dưới một key.
Một hệ thống mã hóa mọi bản ghi bằng khóa riêng nhưng tạo quá nhiều key object trong KMS; chi phí, quota và thời gian rotation tăng nhanh khi số lượng tenant tăng.
Một ứng dụng đo hiệu năng chỉ trên payload nhỏ trong môi trường phát triển; khi xử lý file nhiều gigabyte ở production, CPU, bộ nhớ và chi phí gọi KMS vượt ngân sách.
Một pipeline streaming giải mã file lớn giữ toàn bộ plaintext trong RAM trước khi ghi kết quả; khi worker crash, dữ liệu nhạy cảm còn lại trong heap dump và vùng swap.
Một ứng dụng dùng mã hóa cột khiến truy vấn theo khoảng ngày và sort không còn hiệu quả; nhóm phát triển đề xuất lưu thêm bản plaintext để tối ưu báo cáo.
Một hệ thống tuân thủ yêu cầu xóa dữ liệu cá nhân nhưng không lập inventory các replica, backup, snapshot và key version; nhóm vận hành không chứng minh được dữ liệu đã hết khả năng truy cập.
Một tổ chức chuyển từ provider-managed key sang customer-managed key nhưng không kiểm tra các bản sao cũ, object version và backup lifecycle; một số dữ liệu vẫn dùng khóa ngoài chính sách mới.
