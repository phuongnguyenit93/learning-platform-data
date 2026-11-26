Một ứng dụng mã hóa dữ liệu bằng Base64 rồi gọi đó là bảo mật; chuỗi chỉ được encode để truyền tải và bất kỳ ai cũng có thể decode mà không cần khóa.
Nhóm dùng SHA-256 để bảo vệ file khỏi sửa đổi nhưng attacker có thể thay cả file lẫn checksum công khai; hash không có khóa không chứng minh nguồn gốc dữ liệu.
Ứng dụng dùng AES-ECB cho các block dữ liệu giống nhau; cấu trúc lặp của plaintext vẫn lộ qua các ciphertext block giống nhau.
Một hệ thống dùng AES-CBC nhưng tái sử dụng IV cố định; các thông điệp có cùng block đầu tạo ra quan hệ ciphertext có thể quan sát được.
API giải mã CBC rồi trả lỗi khác nhau cho padding sai và MAC sai; khác biệt phản hồi tạo padding oracle giúp attacker suy ra plaintext.
Ứng dụng dùng AES-CBC nhưng không xác thực ciphertext trước khi giải mã; attacker sửa ciphertext có thể làm thay đổi plaintext sau giải mã mà không bị phát hiện.
Một dịch vụ dùng AES-GCM nhưng tái sử dụng nonce với cùng key khi retry một request; nonce reuse làm suy yếu nghiêm trọng tính bí mật và toàn vẹn của AEAD.
Nhiều replica cùng tạo nonce GCM từ counter cục bộ bắt đầu bằng zero; khi các node dùng chung key, nonce bị trùng giữa các máy dù mỗi node tự tăng counter đúng.
Ứng dụng dùng counter làm nonce GCM nhưng không lưu bền vững trước khi ghi ciphertext; crash và restore snapshot khiến counter quay lùi và tái sử dụng nonce.
Client sinh nonce GCM ngẫu nhiên 32-bit để tiết kiệm header; ở lưu lượng lớn xác suất collision tăng nhanh và có thể phá vỡ bảo đảm an toàn.
Ứng dụng mã hóa bằng ChaCha20-Poly1305 nhưng tái sử dụng nonce với cùng key; keystream và tag bị ảnh hưởng, làm lộ dữ liệu và phá xác thực.
Thông điệp AEAD không đưa tenant ID hoặc loại bản ghi vào associated data; ciphertext hợp lệ bị chuyển từ ngữ cảnh tenant này sang tenant khác mà không phát hiện nhầm ngữ cảnh.
Code xử lý AEAD đọc plaintext trước khi xác minh authentication tag; dữ liệu chưa được xác thực được đưa vào parser và tạo ra side effect trước khi lỗi tag xuất hiện.
Nhóm tự rút ngắn authentication tag xuống vài byte để giảm overhead; xác suất giả mạo tag tăng và mức bảo vệ không còn phù hợp với threat model.
Khóa AES được tạo bằng random generator thông thường có seed dựa trên thời gian; attacker dự đoán được seed và thu hẹp không gian tìm kiếm khóa.
Ứng dụng dùng PRNG phục vụ mô phỏng để tạo session secret và key encryption; generator không được thiết kế cho mục đích mật mã nên trạng thái có thể dự đoán.
Container khởi động đồng loạt trong môi trường thiếu entropy và tự tạo khóa ngay khi process start; nguồn ngẫu nhiên chưa sẵn sàng làm chất lượng key hoặc nonce không đạt yêu cầu.
Tiến trình fork sau khi khởi tạo PRNG và hai tiến trình con tiếp tục dùng cùng trạng thái; chúng sinh ra chuỗi random trùng nhau cho nonce hoặc token.
Nhóm dùng UUID v1 hoặc ID tuần tự làm khóa bí mật; cấu trúc và dữ liệu thời gian khiến giá trị dễ dự đoán hơn một secret sinh từ CSPRNG.
Mật khẩu người dùng được băm bằng SHA-256 một vòng; tốc độ hash cao giúp attacker thử hàng tỷ candidate offline sau khi database bị lộ.
Password hash có salt ngẫu nhiên riêng nhưng hệ thống dùng salt cố định cho toàn bộ tài khoản; các mật khẩu giống nhau tạo hash giống nhau và precomputation hiệu quả hơn.
Ứng dụng dùng Argon2id nhưng đặt memory cost quá thấp để giảm thời gian đăng nhập; chi phí dò offline không còn đủ cao trước phần cứng hiện đại.
Pepper được lưu trong cùng database với password hashes; khi database bị exfiltrate, yếu tố bí mật bổ sung cũng bị lấy cùng.
Hệ thống vẫn dùng MD5 để xác minh chữ ký hoặc tính fingerprint cho artifact quan trọng; collision attacks khiến hai nội dung khác nhau có thể có cùng digest.
Một giao thức tự ghép secret prefix với message rồi dùng SHA-256 làm MAC; length-extension attack có thể cho phép mở rộng thông điệp mà không biết secret.
HMAC được xác minh bằng so sánh chuỗi thông thường dừng tại byte khác đầu tiên; timing có thể tiết lộ thông tin về tag hợp lệ.
Ứng dụng dùng cùng một secret cho HMAC webhook, session token và key derivation; lộ một mục đích làm ảnh hưởng các miền bảo mật còn lại.
Webhook HMAC chỉ ký body nhưng không ràng buộc timestamp hoặc nonce; một request hợp lệ bị ghi lại có thể được phát lại nhiều lần.
Ứng dụng xác minh HMAC trên JSON đã parse rồi serialize lại; khác biệt canonicalization, whitespace hoặc thứ tự field khiến chữ ký không đại diện cho bytes thực tế đã nhận.
Nhóm dùng chữ ký số nhưng phân phối public key qua cùng kênh không xác thực; attacker thay public key và khiến người nhận tin chữ ký giả.
Ứng dụng xác minh chữ ký thành công nhưng không kiểm tra certificate chain hoặc danh tính gắn với public key; chữ ký chứng minh có private key tương ứng nhưng không chứng minh người ký là đối tác mong đợi.
Hệ thống ký JSON nhưng không có quy tắc canonicalization thống nhất; hai bên diễn giải thứ tự field hoặc encoding khác nhau và kết quả xác minh không nhất quán.
Thiết bị ký ECDSA dùng nonce kém ngẫu nhiên và lặp lại giữa hai thông điệp; từ các chữ ký có thể suy ra private signing key.
API xác minh RSA signature bằng PKCS#1 v1.5 ở nơi có thể dùng RSA-PSS; cấu hình tương thích cũ được giữ mà không đánh giá các rủi ro và yêu cầu xác minh chặt chẽ.
Ứng dụng dùng RSA raw encryption không padding cho dữ liệu do người dùng kiểm soát; ciphertext có cấu trúc và không đạt tính an toàn của RSA-OAEP.
Nhóm dùng RSA public-key encryption để mã hóa file lớn trực tiếp; giới hạn kích thước và hiệu năng khiến hệ thống cần mô hình hybrid encryption với data key đối xứng.
Ứng dụng dùng cùng một cặp khóa RSA cho ký số và giải mã; compromise hoặc misuse ở một mục đích ảnh hưởng cả hai miền và làm khó quản lý vòng đời.
HKDF dùng cùng input key material nhưng bỏ trống context/info cho nhiều mục đích; các derived keys không được tách biệt rõ theo protocol, tenant hoặc chức năng.
Ứng dụng dùng PBKDF2 để derive encryption key nhưng không lưu salt và tham số phiên bản; sau nâng cấu hình, dữ liệu cũ khó được giải mã hoặc migrate có kiểm soát.
Envelope encryption lưu ciphertext cùng data encryption key ở dạng plaintext trong metadata; attacker chỉ cần lấy object storage là có cả dữ liệu lẫn khóa giải mã.
Data key được mã hóa bằng KMS key nhưng quyền decrypt của workload quá rộng; một service bị chiếm quyền có thể giải mã dữ liệu ngoài phạm vi nghiệp vụ.
KMS key rotation hoàn tất nhưng ứng dụng không lưu key version hoặc key ID cùng ciphertext; sau rotation, hệ thống không biết phải dùng key nào để giải mã dữ liệu cũ.
Nhóm revoke hoặc disable master key ngay sau rotation mà chưa re-encrypt hoặc xác nhận khả năng decrypt dữ liệu cũ; bản backup và ciphertext lưu trữ trở nên không thể khôi phục.
Private signing key được export thành file để tiện triển khai trên nhiều node; bản sao nằm trong filesystem và backup không được bảo vệ như HSM hoặc KMS.
Ứng dụng ghi key material hoặc plaintext nhạy cảm vào debug log khi lỗi mã hóa; người có quyền đọc log có thể lấy bí mật mà không cần quyền KMS.
Quy trình zeroization xóa buffer gốc nhưng secret vẫn còn trong bản sao immutable, crash dump hoặc swap; dữ liệu nhạy cảm tiếp tục tồn tại ngoài vùng dự kiến.
TLS client chỉ kiểm tra certificate chain mà bỏ qua hostname verification; chứng chỉ hợp lệ của domain khác vẫn có thể được dùng để giả mạo endpoint.
Certificate có Common Name đúng nhưng Subject Alternative Name không chứa hostname; client cũ và mới xử lý khác nhau và kết nối có thể bị từ chối hoặc xác minh sai.
Client tin mọi certificate tự ký được cài trong trust store toàn cục; một certificate thử nghiệm bị thêm nhầm có thể trở thành trust anchor cho kết nối production.
TLS verifier không kiểm tra certificate expiry hoặc dùng đồng hồ hệ thống sai; chứng chỉ hết hạn vẫn được chấp nhận hoặc chứng chỉ mới bị từ chối.
Certificate đã bị CA thu hồi nhưng client không kiểm tra OCSP/CRL theo chính sách; chứng chỉ compromise tiếp tục được tin cậy.
PKI client xác minh certificate chain nhưng không kiểm tra EKU hoặc key usage; chứng chỉ chỉ dành cho mục đích khác vẫn được chấp nhận để xác thực client.
mTLS chỉ chứng minh client sở hữu private key của certificate; ứng dụng gán mọi certificate do CA nội bộ cấp cùng một quyền admin mà không ánh xạ danh tính và authorization.
Wildcard certificate cho *.example.com được dùng cho cả subdomain do bên thứ ba quản lý; compromise một subdomain có thể ảnh hưởng phạm vi tin cậy rộng hơn dự kiến.
CA private key được lưu trên máy chủ web online cùng với private key của website; compromise server ứng dụng có thể dẫn đến giả mạo certificate cho nhiều dịch vụ.
TLS server cho phép protocol và cipher suite lỗi thời để hỗ trợ client cũ; attacker có thể ép kết nối xuống cấu hình yếu hơn nếu không có chính sách chống downgrade.
TLS kết thúc tại load balancer rồi traffic nội bộ đi plaintext qua mạng dùng chung; dữ liệu sau điểm termination không còn được bảo vệ như nhóm vận hành giả định.
Key exchange dùng Diffie-Hellman tĩnh hoặc tái sử dụng private key dài hạn cho mọi phiên; lộ khóa có thể cho phép giải mã traffic đã ghi lại và làm mất forward secrecy.
Certificate renewal tạo chứng chỉ mới nhưng các node không reload đồng bộ; một phần cluster tiếp tục trình bày certificate sắp hết hạn hoặc đã hết hạn.
Ứng dụng hard-code thuật toán và key size trong nhiều thành phần; khi tiêu chuẩn hoặc yêu cầu compliance thay đổi, nhóm không thể chuyển đổi an toàn mà không sửa nhiều nơi.
Protocol nhận trường alg từ message rồi tự chọn verifier mà không có allowlist theo loại key; attacker có thể gây algorithm confusion hoặc chọn thuật toán không được chính sách cho phép.
Backup mã hóa được lưu cùng master key trong cùng một bucket; một lần compromise storage làm mất cả bản sao dữ liệu và phương tiện giải mã.
Khóa mã hóa không có owner, purpose, creation time và rotation metadata; đội vận hành không xác định được khóa nào còn được dùng trước khi thu hồi.
Ứng dụng chuyển từ thuật toán cũ sang thuật toán mới nhưng không giữ metadata phiên bản hoặc cơ chế đọc ciphertext cũ; rollout làm dữ liệu lịch sử không thể giải mã.
Nhóm dùng nonce, salt và IV như các khái niệm thay thế nhau; nonce bị tái sử dụng hoặc IV không đạt yêu cầu ngẫu nhiên vì hiểu sai mục tiêu của từng tham số.
