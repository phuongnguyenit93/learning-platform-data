Một dịch vụ lưu hồ sơ khách hàng mã hóa từng bản ghi bằng AES-GCM; sau khi mở rộng thành nhiều instance, hai instance có thể phát cùng nonce dưới một data key do bộ đếm nonce được khởi tạo lại khi process restart.
Một hệ thống mã hóa file dung lượng nhiều gigabyte bằng RSA trực tiếp; thời gian xử lý tăng mạnh và giới hạn kích thước plaintext khiến luồng upload thất bại khi file vượt ngưỡng.
Ứng dụng dùng hybrid encryption: tạo data encryption key cho từng file, mã hóa nội dung bằng AES-GCM rồi bọc data key bằng public key của người nhận; sau khi thay cặp khóa, file mới giải mã được nhưng file cũ không còn xác định được key version.
Một hệ thống lưu dữ liệu nhị phân bằng AES-ECB; các block plaintext giống nhau tạo ra block ciphertext lặp lại, khiến cấu trúc mẫu trong ảnh và tài liệu vẫn có thể quan sát được.
Kho lưu trữ dùng AES-CBC với một IV cố định cho mọi bản ghi; hai plaintext có cùng block đầu tạo ciphertext block đầu giống nhau dù khóa không đổi.
Một giao thức tự thiết kế dùng AES-CTR nhưng bộ đếm nonce quay về giá trị ban đầu sau khi thiết bị mất điện; các thông điệp mới dùng lại keystream của những thông điệp cũ.
Hệ thống mã hóa dữ liệu bằng AES-GCM và tái sử dụng cùng cặp key/nonce khi gửi lại một payload đã chỉnh sửa; sau một thời gian, ciphertext bị lộ quan hệ và authentication tag không còn bảo đảm như kỳ vọng.
Một cụm worker tạo nonce GCM bằng bộ đếm cục bộ riêng; khi nhiều worker dùng chung key, các bộ đếm trùng nhau khiến nonce bị lặp giữa các node.
Thiết bị IoT tạo IV ngẫu nhiên từ bộ sinh số giả ngẫu nhiên yếu ngay sau boot; các thiết bị cùng model thường sinh ra các IV trùng nhau dưới cùng key.
Một API mã hóa giá trị hóa đơn nhưng không đưa tenant ID và invoice ID vào authenticated additional data; ciphertext hợp lệ bị chuyển sang bản ghi khác mà ứng dụng không phát hiện sai ngữ cảnh.
Thư viện giải mã AES-GCM trả plaintext cho tầng nghiệp vụ trước khi kiểm tra authentication tag; dữ liệu bị sửa có thể được xử lý tạm thời như nội dung hợp lệ.
Một hệ thống rút ngắn authentication tag của AEAD xuống vài byte để tiết kiệm băng thông; số lần thử xác thực tăng cao nhưng không có giới hạn, làm giảm mạnh khả năng chống giả mạo.
Một API giải mã hỗ trợ cả CBC và AEAD trả thông báo khác nhau cho lỗi tag, lỗi định dạng nonce và lỗi padding; người gọi bên ngoài có thể quan sát phản hồi để suy luận thông tin về ciphertext.
Một dịch vụ mã hóa bằng AES-CBC nhưng không kèm MAC hoặc cơ chế xác thực; kẻ có thể sửa ciphertext khiến plaintext sau giải mã thay đổi mà ứng dụng vẫn tiếp nhận.
Một endpoint nhận ciphertext CBC và phản hồi khác nhau khi padding sai hoặc dữ liệu giải mã không đúng cấu trúc; sự khác biệt này tạo thành oracle cho các lần thử có chủ đích.
Một nền tảng chạy trên máy chủ có AES acceleration nhưng cũng có thiết bị di động không hỗ trợ tăng tốc tương tự; nhóm phát triển đang cân nhắc AES-GCM và ChaCha20-Poly1305 cho cùng giao thức.
Một định dạng lưu ciphertext ghi nonce và tag cạnh dữ liệu đã mã hóa; nhóm vận hành nhầm nonce công khai với secret key và loại nonce khỏi bản sao lưu, khiến dữ liệu không thể giải mã.
Một nhóm phát triển dùng cùng một key cho AES-GCM encryption và một mục đích MAC độc lập; thay đổi ở một luồng giao thức làm phạm vi sử dụng key chồng lấn và khó kiểm soát.
Một thiết bị tạo khóa mã hóa từ bộ sinh số ngẫu nhiên chưa được seed đủ entropy; các khóa tạo ra trong giai đoạn khởi động có cấu trúc lặp và dễ dự đoán.
Ứng dụng mã hóa dữ liệu bằng khóa suy ra trực tiếp từ mật khẩu người dùng qua một hash nhanh; tài khoản có mật khẩu yếu khiến bản sao ciphertext có thể bị thử đoán ngoại tuyến với chi phí thấp.
Hệ thống dùng HKDF để tạo nhiều khóa con nhưng bỏ qua context info; cùng một input key material được dùng ở nhiều giao thức nên các khóa con có thể bị tái sử dụng ngoài mục đích dự kiến.
Một hệ thống dùng RSA PKCS#1 v1.5 encryption cho dữ liệu mới trong khi API giải mã tiết lộ khác biệt giữa padding error và message error; đội vận hành nhận thấy bề mặt tấn công tăng khi endpoint công khai.
Một cặp khóa RSA được dùng đồng thời cho mã hóa dữ liệu và ký thông điệp; quy trình luân chuyển khóa và phân quyền truy cập không thể tách biệt hai mục đích sử dụng.
Client nội bộ bỏ qua kiểm tra hostname và chuỗi tin cậy của chứng chỉ TLS vì môi trường staging từng dùng chứng chỉ tự ký; cấu hình tương tự được triển khai nhầm lên production.
Một ứng dụng tải public key từ endpoint không xác thực rồi dùng key đó mã hóa dữ liệu nhạy cảm; kẻ đứng giữa thay public key khiến dữ liệu được mã hóa cho khóa của họ.
Một endpoint TLS cũ vẫn cho phép cipher suite dùng static RSA key exchange; khi private key máy chủ bị lộ, các bản ghi phiên đã thu trước đó có nguy cơ bị giải mã.
Proxy trung gian cho phép client thương lượng lại phiên bản và bộ cipher yếu để tương thích thiết bị cũ; một bên thứ ba có thể ép kết nối xuống cấu hình kém an toàn.
Hệ thống mutual TLS chỉ kiểm tra chứng chỉ client tại thời điểm bắt tay; chứng chỉ của một thiết bị bị thu hồi nhưng kết nối dài hạn hiện tại vẫn tiếp tục gửi dữ liệu.
Database volume được mã hóa ở cấp đĩa nhưng bản snapshot và file export được lưu sang bucket khác không có cùng kiểm soát mã hóa; bản sao dữ liệu nhạy cảm tồn tại ngoài vùng bảo vệ ban đầu.
Một hệ thống cần tìm kiếm theo số định danh đã mã hóa; nhóm chọn mã hóa toàn bộ cột bằng AEAD nhưng truy vấn equality không còn hoạt động và yêu cầu báo cáo bị ảnh hưởng.
Khóa mã hóa được ghi trực tiếp trong repository cùng file cấu hình; bản build container và các fork cũ vẫn giữ lại khóa sau khi repository đã được sửa.
Một workload có quyền gọi KMS decrypt trên mọi key trong tài khoản; khi credential của workload bị lộ, phạm vi dữ liệu có thể giải mã rộng hơn nhiều so với tenant mà nó phục vụ.
Private key được tạo và giữ trong HSM nhưng nhiều nhóm cùng dùng một identity quản trị; log audit không phân biệt được ai đã yêu cầu ký hoặc giải mã dữ liệu.
Ứng dụng dùng envelope encryption với DEK mã hóa dữ liệu và KEK bọc DEK; bản ghi chỉ lưu ciphertext và DEK đã bọc nhưng không lưu key identifier hoặc thuật toán phiên bản tương ứng.
Quy trình rotation thay KEK hiện tại nhưng không cập nhật mọi wrapped DEK trong kho; một phần dữ liệu cũ không thể mở khi key cũ bị vô hiệu hóa.
Một cụm ứng dụng triển khai key rotation không đồng bộ; instance mới chỉ biết key version mới trong khi instance cũ vẫn mã hóa bằng key cũ, khiến các node không thể đọc dữ liệu của nhau.
Đội vận hành sao lưu toàn bộ ciphertext sang vùng dự phòng nhưng không sao lưu hoặc kiểm thử khả năng khôi phục KMS key; sau sự cố vùng chính, dữ liệu còn nguyên nhưng không thể giải mã.
Một khóa mã hóa bị nghi đã lộ; nhóm chỉ tạo key mới cho dữ liệu phát sinh mà không đánh giá ciphertext cũ, bản sao lưu, token cache và bản export từng được mã hóa bằng key bị ảnh hưởng.
Nhiều tenant dùng chung một data key để giảm chi phí KMS; một lỗi phân quyền trong dịch vụ giải mã có thể làm phạm vi ảnh hưởng vượt qua ranh giới tenant.
Ứng dụng cần giải mã dữ liệu ở nhiều region nhưng KMS key replica chưa đồng bộ hoặc quyền truy cập khác nhau; dịch vụ tại region dự phòng không thể xử lý request sau failover.
Chính sách xóa dữ liệu yêu cầu hủy khả năng giải mã sau khi hết hạn; nhóm vận hành không xác định được mọi bản sao wrapped key và bản backup nào còn giữ khả năng khôi phục dữ liệu.
Middleware ghi request và response đã giải mã vào log khi xử lý lỗi; log tập trung có quyền truy cập rộng hơn kho dữ liệu gốc và giữ lại nội dung nhạy cảm ở dạng plaintext.
Một hệ thống dùng deterministic encryption để hỗ trợ so khớp giá trị; các ciphertext giống nhau làm lộ tần suất và mối liên hệ giữa các bản ghi dù plaintext không hiển thị.
Dịch vụ nén dữ liệu bí mật cùng nội dung do người dùng kiểm soát trước khi mã hóa; kích thước ciphertext thay đổi theo nội dung nén và có thể làm lộ thông tin qua quan sát độ dài phản hồi.
Khóa giống nhau được dùng ở môi trường development, staging và production để đơn giản hóa triển khai; bản sao môi trường thử nghiệm bị truy cập trái phép làm tăng nguy cơ với dữ liệu production.
Ứng dụng dùng AES-XTS để mã hóa sector của ổ đĩa nhưng coi ciphertext là đã được xác thực; dữ liệu bị sửa ở mức sector không được phát hiện bằng authentication tag.
Một hệ thống truyền ciphertext cùng metadata thuật toán do client cung cấp; server chấp nhận thuật toán yếu hoặc phiên bản cũ mà không ràng buộc chính sách mật mã cho từng loại dữ liệu.
Trong quá trình nâng cấp thuật toán, hệ thống cần đọc đồng thời ciphertext cũ và mới nhưng metadata không ghi algorithm ID, nonce format hoặc key version; một số bản ghi không thể được phân loại để giải mã đúng.
Ứng dụng cache plaintext sau khi giải mã để giảm tải KMS; cache không gắn với phiên bản quyền truy cập hoặc thời hạn key, nên dữ liệu vẫn được phục vụ sau khi quyền giải mã bị thu hồi.
Một hệ thống dùng cùng key material cho key wrapping, token signing và mã hóa dữ liệu nghiệp vụ; chính sách xoay vòng và thu hồi của một mục đích ảnh hưởng tới các mục đích còn lại.
