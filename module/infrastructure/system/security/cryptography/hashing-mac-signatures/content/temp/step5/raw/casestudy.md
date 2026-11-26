Một cổng tải xuống công khai cung cấp SHA-256 cạnh file để người dùng kiểm tra lỗi truyền tải, nhưng nhóm vận hành quảng bá digest này như bằng chứng file chắc chắn do nhà phát hành tạo ra dù attacker có thể thay cả file lẫn digest.
Hệ thống lưu trữ artifact vẫn chấp nhận MD5 để xác định hai gói có giống nhau; một đối thủ tạo được hai file khác nội dung nhưng cùng digest và lợi dụng việc hệ thống coi chúng là cùng artifact.
Một dịch vụ dùng SHA-1 để ký manifest phát hành mới, dù môi trường đã có thể hỗ trợ thuật toán chữ ký hiện đại hơn và yêu cầu kháng va chạm.
Nhóm phát triển đánh giá độ an toàn của digest 256 bit bằng cách cho rằng cần thử đủ 2^256 khả năng mới tìm được bất kỳ va chạm nào, bỏ qua birthday bound.
Một hệ thống kiểm tra tính toàn vẹn dùng CRC32 cho file cấu hình được tải từ nguồn không tin cậy; attacker sửa nội dung và tính lại checksum để qua bước kiểm tra.
Ứng dụng băm file nhiều gigabyte bằng cách đọc toàn bộ file vào RAM, khiến worker hết bộ nhớ khi nhiều tác vụ kiểm tra artifact chạy đồng thời.
Hai hệ thống tính SHA-256 trên cùng một JSON nhưng kết quả khác nhau vì thiếu canonicalization thống nhất cho thứ tự key, khoảng trắng và cách biểu diễn số.
Một hệ thống ký XML canonicalize tài liệu trước khi ký nhưng verifier canonicalize theo quy tắc namespace khác, dẫn đến chữ ký không xác minh được dù dữ liệu nghiệp vụ nhìn giống nhau.
API dùng `SHA256(secret || message)` làm cơ chế xác thực request; attacker khai thác length extension trên cấu trúc hash phù hợp để tạo message mở rộng với digest hợp lệ.
Nhóm thay hash thường bằng keyed hash nhưng dùng cùng một secret key cho định danh nội dung công khai và xác thực nội bộ, khiến hai ngữ cảnh bảo mật bị trộn lẫn.
Một dịch vụ dùng hash công khai để xác minh webhook và cho rằng attacker không thể giả mạo digest, dù bất kỳ ai cũng có thể tính lại hash sau khi sửa payload.
Kho artifact dùng digest làm content address nhưng không xác minh nguồn gốc nhà phát hành; gói độc hại được tải lên cùng digest được tham chiếu bởi một manifest không được xác thực.
Một nhóm chọn SHA-3 (SHA3-256) nhưng thư viện đối tác chỉ hỗ trợ SHA-256, và hai bên không thống nhất thuật toán trong metadata nên không thể xác minh digest liên nền tảng.
Hệ thống cần tạo output có độ dài linh hoạt nhưng dùng SHA-256 rồi cắt hoặc nối nhiều digest theo cách tự thiết kế thay vì dùng XOF như SHAKE với quy tắc rõ ràng.
Pipeline xử lý song song bằng BLAKE3 nhưng các node khác nhau dùng mode hash, keyed hoặc derive-key và context không thống nhất, khiến digest artifact khác nhau.
Một ứng dụng dùng salt cố định giống nhau cho mọi đối tượng và nhầm salt là secret key, nên các giá trị giống nhau vẫn dễ bị liên kết và cơ chế xác thực nguồn gốc không được cung cấp.
Nhóm dùng hash mật mã thông thường cho mật khẩu người dùng vì SHA-256 nhanh, làm việc thử đoán mật khẩu ngoại tuyến trở nên rẻ khi cơ sở dữ liệu bị lộ.
Một giao thức tạo MAC bằng cách nối secret key vào cuối message rồi băm với SHA-256, nhưng thiết kế không có phân tích an toàn cho cấu trúc keyed hash tự chế.
Webhook receiver xác minh HMAC nhưng không dùng constant-time comparison và dừng tại byte khác đầu tiên, tạo khác biệt thời gian có thể quan sát qua nhiều lần gửi.
API gateway dùng HMAC-SHA-256 nhưng các dịch vụ phía sau dùng HMAC-SHA-512 với cùng key identifier; request hợp lệ bị từ chối vì hai bên không thống nhất thuật toán và encoding tag.
Một hệ thống dùng HMAC tag bị cắt còn 32 bit để giảm kích thước header, nhưng lưu lượng xác minh rất lớn khiến xác suất giả mạo tích lũy không còn phù hợp với mức rủi ro.
Nhiều tenant dùng chung một HMAC key cho webhook; khi một tenant làm lộ key, attacker có thể tạo request giả được chấp nhận cho các tenant còn lại.
Đội vận hành thực hiện key rotation cho HMAC ở sender nhưng receiver xóa key cũ ngay lập tức, khiến webhook đang trên đường truyền hoặc retry hợp lệ không thể được xác minh.
Ứng dụng dùng cùng một khóa gốc cho HMAC request, HMAC session token và MAC backup mà không dẫn xuất khóa riêng theo mục đích, tạo nguy cơ key reuse giữa các giao thức.
Một nhóm tự dùng SHA-256 với tiền tố chuỗi để dẫn xuất nhiều khóa từ master secret nhưng không xác định salt, context và độ dài output theo một KDF chuẩn như HKDF.
Hai hệ thống triển khai HMAC trên cùng message nhưng một bên chuẩn hóa newline và encoding UTF-8, bên kia giữ nguyên byte nhận được, khiến MAC mismatch khó chẩn đoán.
Webhook signer ký JSON sau khi parse và serialize lại, trong khi receiver xác minh raw request body; khác biệt thứ tự field hoặc số thập phân làm chữ ký thất bại.
API ký request chỉ gồm body nhưng bỏ qua HTTP method, path và query string, cho phép attacker chuyển một request hợp lệ sang endpoint khác trong cùng hệ thống.
Webhook có HMAC hợp lệ bị replay attack nhiều lần vì receiver không ràng buộc timestamp hoặc nonce; thao tác thanh toán lặp lại dù payload chưa bị sửa.
Receiver kiểm tra timestamp của request ký nhưng không lưu nonce đã dùng, nên attacker phát lại cùng request nhiều lần trong cửa sổ thời gian được chấp nhận.
Một hệ thống chọn CMAC-AES cho thiết bị hạn chế nhưng triển khai không thống nhất cách mã hóa block cuối và padding, khiến tag giữa firmware và server khác nhau.
Thiết bị IoT dùng Poly1305 với one-time key tái sử dụng cho nhiều message sau reconnect, làm mất giả định an toàn cốt lõi của MAC này.
Nhóm dùng keyed mode của BLAKE2 cho một giao thức mới nhưng không ghi thuật toán, key version và context vào envelope, khiến các consumer khó xác minh và chuyển đổi phiên bản.
Một hệ thống chỉ cần xác thực nguồn gửi nhưng chọn cơ chế hash công khai thay vì MAC; bất kỳ bên nào có payload đều có thể tạo digest mà receiver chấp nhận.
Đội tích hợp nhầm MAC với chữ ký số và yêu cầu đối tác xác minh bằng public key dù HMAC cần cùng secret key ở cả bên tạo và bên kiểm tra.
Một tổ chức tuyên bố chữ ký HMAC cung cấp non-repudiation, dù mọi bên giữ shared secret đều có khả năng tạo tag hợp lệ.
Dịch vụ ký RSA dùng cùng một API cho RSA encryption và RSA signature, dẫn đến nhóm phát triển áp dụng nhầm padding mã hóa vào quy trình xác minh chữ ký.
Nhà phát hành dùng RSA PKCS#1 v1.5 signature cho hệ thống mới dù chính sách yêu cầu ưu tiên RSA-PSS và các thư viện triển khai đã hỗ trợ PSS.
Thiết bị ký ECDSA dùng bộ sinh nonce yếu; nhiều chữ ký cho thấy nonce có quan hệ dự đoán được và attacker có thể khôi phục private key.
Một thư viện ECDSA vô tình tái sử dụng nonce khi ký hai message khác nhau, khiến hai chữ ký làm lộ thông tin đủ để tính private key.
Nhóm triển khai ECDSA bằng nonce ngẫu nhiên nhưng không kiểm tra nguồn entropy lúc khởi động; thiết bị vừa boot tạo nhiều chữ ký với trạng thái random generator yếu.
Verifier ECDSA chỉ chấp nhận một encoding fixed-width nhưng signer gửi chữ ký ASN.1 DER, khiến hai hệ thống bất đồng về cách biểu diễn chữ ký dù giá trị toán học hợp lệ.
Parser chữ ký ECDSA chấp nhận cả biểu diễn high-S và low-S, tạo nhiều biểu diễn cho cùng thông điệp và gây vấn đề khi chữ ký được dùng làm định danh trong cache.
Một nền tảng mới chọn Ed25519 nhưng hệ thống thiết bị cũ chỉ hỗ trợ thuật toán khác; quá trình rollout thiếu metadata thuật toán và kế hoạch tương thích verifier.
Ứng dụng dùng Ed25519 nhưng verifier và signer không thống nhất giữa chế độ thuần, pre-hash hoặc context variant của EdDSA, dẫn đến xác minh thất bại.
Verifier cho phép message tự khai báo thuật toán `none` hoặc thuật toán yếu và tự chọn cách xác minh theo metadata không đáng tin cậy, tạo đường algorithm downgrade.
Manifest phần mềm được ký hợp lệ nhưng không ràng buộc version và release channel; attacker phát lại bản cũ có chữ ký hợp lệ để hạ cấp thiết bị.
Quy trình ký firmware xác minh signature trên file tạm, sau đó cài file được tải lại từ đường dẫn có thể bị thay đổi, tạo khoảng trống time-of-check/time-of-use.
Chữ ký trên manifest hợp lệ nhưng manifest không ràng buộc digest của mọi thành phần tải xuống, nên một thư viện bên trong gói có thể bị thay thế mà verifier không phát hiện.
Verifier kiểm tra chữ ký bằng public key lấy trực tiếp từ cùng gói tải xuống, nhưng không có certificate chain, pinning hoặc trust store độc lập để xác thực signer.
Certificate chứa public signing key còn hạn nhưng đã bị thu hồi sau khi private key bị lộ; hệ thống xác minh chỉ kiểm tra chữ ký toán học mà không kiểm tra trạng thái tin cậy của certificate.
Signing service giữ private key xuất được trong file cấu hình trên máy chủ ứng dụng thay vì quản lý qua KMS hoặc HSM, khiến người có quyền đọc filesystem có thể sao chép khóa và ký artifact giả.
HSM chỉ cho phép ký qua signing service nhưng policy cho phép mọi workload yêu cầu ký mọi payload, không ràng buộc loại artifact, tenant hoặc mục đích ký.
Private signing key bị compromise nhưng tổ chức chỉ đổi key cho bản phát hành mới, không thực hiện revocation cho key hoặc certificate cũ và không đánh giá lại artifact đã ký trong khoảng thời gian bị ảnh hưởng.
Verifier nhận key identifier từ message và tra cứu đúng key nhưng không kiểm tra key thuộc tenant, issuer hoặc mục đích ký tương ứng, tạo nguy cơ key confusion.
Một khóa MAC được xoay vòng nhưng hệ thống không giữ key version trong envelope; receiver thử mọi key cũ mới theo thứ tự và tạo đường xác minh không rõ ràng.
Audit log của signing service chỉ ghi kết quả thành công mà không lưu signer identity, key version, artifact digest và lý do yêu cầu, khiến điều tra ký sai không thể truy vết.
Nhóm kiểm thử hash và chữ ký chỉ chạy happy path với một file mẫu, không có known-answer test, test vector liên thư viện hoặc trường hợp message bị thay đổi một byte.
Verifier trả lỗi khác nhau cho key không tồn tại, MAC sai và chữ ký sai, làm lộ thông tin nội bộ có thể được attacker dùng để dò key hoặc tạo verification oracle.
