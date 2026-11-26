Khi một ứng dụng mã hóa tệp lớn, nhóm phát triển dùng cùng một khóa KMS trực tiếp cho mọi tệp; số lần gọi KMS tăng cao và việc thu hồi khóa sẽ ảnh hưởng đồng thời toàn bộ dữ liệu.
Một hệ thống dùng envelope encryption nhưng lưu plaintext data-encryption key (DEK) lâu dài trong database cùng ciphertext; bản sao database bị đánh cắp làm lộ cả dữ liệu lẫn khóa giải mã.
Nhóm vận hành mã hóa DEK bằng key-encryption key (KEK), nhưng không lưu định danh và phiên bản KEK đã dùng; sau khi rotation, một phần dữ liệu không thể xác định khóa để unwrap.
Một nhóm dùng một key pair cho cả ký số và giải mã dữ liệu; thay đổi chính sách của một mục đích làm ảnh hưởng các luồng nghiệp vụ còn lại.
Khóa mã hóa được tạo bằng bộ sinh ngẫu nhiên yếu trên một máy ảo mới khởi tạo; nhiều workload vô tình tạo ra các khóa có entropy thấp.
Nhà cung cấp gửi khóa đối xứng dưới dạng plaintext qua email để import vào KMS; nhiều bản sao tạm thời xuất hiện trong mailbox và thiết bị người nhận.
Khóa được cấu hình extractable để tiện debug; một tài khoản vận hành có thể xuất private key khỏi HSM mà không có phê duyệt bổ sung.
Một workload chỉ cần giải mã dữ liệu của tenant mình nhưng IAM policy cho phép gọi decrypt với mọi key trong tài khoản cloud.
Nhóm vận hành cấp quyền `encrypt`, `decrypt`, `sign` và `delete` cho cùng một service identity vì muốn giảm số policy cần quản lý.
Một quản trị viên có thể vừa tạo key, thay đổi policy, vừa phê duyệt xóa key; tổ chức không có cơ chế separation of duties.
Ứng dụng dùng key alias cố định; sau rotation alias trỏ sang key mới, nhưng dữ liệu cũ không lưu key version nên quá trình decrypt thất bại.
Chính sách rotation đổi phiên bản key định kỳ nhưng không có kế hoạch rewrap DEK hoặc đọc dữ liệu đã mã hóa bằng phiên bản cũ.
Một nhóm lên lịch xóa key cũ ngay sau khi rotation; các bản backup và archive vẫn chứa ciphertext phụ thuộc vào key đó.
Key bị nghi lộ nhưng đội vận hành chỉ disable key để chặn request mới; họ chưa đánh giá bản sao plaintext, wrapped key và dữ liệu đã giải mã trước đó.
Một khóa ký số bị xâm nhập; hệ thống tiếp tục tin chữ ký được tạo trong khoảng thời gian sự cố vì không lưu thời điểm và key version cho từng chữ ký.
Key bị đánh dấu pending deletion trong thời gian chờ; nhóm ứng dụng không biết trạng thái này và tiếp tục tạo dữ liệu mới phụ thuộc vào key sắp bị xóa.
Yêu cầu cryptographic erasure được thực hiện bằng cách xóa một key trong KMS, nhưng bản sao key trong HSM backup và bản export trước đây chưa được kiểm kê.
Một tổ chức xóa key ngay khi hết thời hạn lưu dữ liệu; sau đó phát sinh legal hold yêu cầu khôi phục dữ liệu từ archive không còn khả năng giải mã.
Nhóm tuân thủ yêu cầu chứng minh key đã bị hủy không thể phục hồi; quy trình hiện tại chỉ ghi nhận thao tác delete mà không có bằng chứng về backup và replica.
Backup HSM được lưu ở cùng phòng máy với thiết bị chính; sự cố vật lý tại địa điểm làm mất cả bản chính và bản sao.
Khôi phục HSM yêu cầu quorum của nhiều người giữ share, nhưng một số người đã rời tổ chức và danh sách người nắm giữ chưa được cập nhật.
Một key backup được tạo nhưng chưa từng thử restore; khi thiết bị HSM chính hỏng, tổ chức phát hiện bản backup không tương thích phiên bản firmware.
Cluster HSM chuyển đổi dự phòng trong lúc mạng phân vùng; hai node cùng nhận lệnh thay đổi trạng thái key và tạo ra trạng thái không nhất quán.
Firmware HSM cần nâng cấp để vá lỗ hổng, nhưng thiết bị đang phục vụ giao dịch ký quan trọng và chưa có quy trình failover hoặc kiểm thử tương thích.
Một thiết bị HSM báo dấu hiệu tamper; nhóm vận hành không rõ nên cô lập thiết bị, zeroize hay duy trì để thu thập bằng chứng điều tra.
KMS tạm thời mất kết nối; ứng dụng chuyển sang dùng một khóa tĩnh được nhúng trong cấu hình để tiếp tục hoạt động, tạo ra đường vòng không được kiểm soát.
Ứng dụng cache plaintext DEK trong bộ nhớ để giảm độ trễ; một memory dump phục vụ chẩn đoán được gửi ra hệ thống hỗ trợ bên ngoài.
Một container chia sẻ vùng nhớ và volume với workload khác mức tin cậy; plaintext key material tồn tại lâu hơn vòng đời request và có thể bị tiến trình khác đọc.
Audit log của KMS chỉ ghi thao tác và key ID, không ghi principal, nguồn gọi hoặc encryption context; nhóm điều tra không thể xác định workload đã giải mã dữ liệu nào.
Nhóm SOC không cảnh báo khi một identity giải mã số lượng lớn bản ghi ngoài giờ; hành vi trích xuất dữ liệu bằng quyền hợp lệ kéo dài nhiều ngày.
Policy key được thay đổi trực tiếp trên console nhưng không đồng bộ về Infrastructure as Code; lần triển khai tiếp theo ghi đè policy và vô tình mở rộng quyền.
Key policy cho phép tài khoản bên ngoài sử dụng key nhưng không giới hạn principal cụ thể; một workload không thuộc dự án có thể gọi decrypt.
Một dịch vụ dùng encryption context để ràng buộc ciphertext với tenant, nhưng khi decrypt lại không truyền context hoặc lấy context từ request chưa xác minh.
Ciphertext của nhiều tenant được lưu chung; metadata tenant bị thay đổi mà không có ràng buộc xác thực trong associated data, dẫn đến nguy cơ tráo đổi dữ liệu giữa tenant.
Nonce của thuật toán AEAD được tạo bằng bộ đếm cục bộ có thể reset khi workload restart; cùng một key có thể dùng lại nonce sau khi khởi động lại.
Ứng dụng dùng thuật toán và kích thước khóa lỗi thời do cấu hình mặc định cũ; hệ thống chưa có inventory để xác định dữ liệu nào cần re-encrypt.
Một tổ chức phải chuyển nhà cung cấp KMS nhưng key material không thể export; chưa có kế hoạch decrypt và re-encrypt dữ liệu theo lộ trình di trú.
Bring Your Own Key được triển khai bằng cách import key vào KMS, nhưng tổ chức chưa xác định ai chịu trách nhiệm rotation, backup và thu hồi key material gốc.
Hold Your Own Key yêu cầu dịch vụ bên ngoài cung cấp thao tác giải mã; sự cố mạng tới dịch vụ giữ khóa khiến ứng dụng không truy cập được dữ liệu hợp lệ.
Một hệ thống đa vùng sao chép key không đồng bộ; workload ở vùng dự phòng nhận traffic trước khi replica key sẵn sàng và phát sinh lỗi decrypt.
Key được nhân bản sang nhiều region để tăng availability nhưng policy và audit không đồng nhất; một vùng có quyền decrypt rộng hơn vùng còn lại.
Quota API KMS bị cạn trong đợt cao điểm; ứng dụng retry đồng loạt làm tăng tải và gây hiệu ứng dây chuyền cho các dịch vụ phụ thuộc.
Một key được dùng cho cả môi trường development, staging và production; người có quyền debug ở môi trường thấp có thể sử dụng key bảo vệ dữ liệu production.
Quy trình key ceremony tạo root key yêu cầu nhiều người chứng kiến, nhưng biên bản không ghi nhận thiết bị, phiên bản phần mềm và danh tính người tham gia.
Private key dùng để ký firmware được lưu trong HSM, nhưng pipeline build có quyền yêu cầu ký mọi digest mà không có kiểm soát nguồn phát hành hoặc phê duyệt.
Chứng thư của key ký số sắp hết hạn trong khi key vẫn còn hoạt động; nhóm vận hành chỉ theo dõi ngày hết hạn chứng thư mà không theo dõi phụ thuộc của hệ thống.
Một key đã hết hạn theo chính sách nhưng vẫn cần để xác minh chữ ký lịch sử; hệ thống chưa phân biệt quyền tạo chữ ký mới và quyền verify chữ ký cũ.
Nhóm ứng phó sự cố cần xác định dữ liệu nào bị ảnh hưởng sau khi key bị lộ, nhưng inventory không ánh xạ key ID, phiên bản, workload và tập ciphertext phụ thuộc.
Nhà cung cấp KMS thay đổi thuật toán hoặc API hỗ trợ; ứng dụng không có crypto-agility plan và nhiều workload ngừng mã hóa khi cấu hình cũ bị loại bỏ.
Một tài khoản break-glass có quyền quản trị toàn bộ key được lưu trong password vault dùng chung; tổ chức không kiểm tra định kỳ việc sử dụng và thay đổi quyền của tài khoản này.
