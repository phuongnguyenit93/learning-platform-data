Một API dùng PRNG phục vụ mô phỏng để sinh session token; chuỗi đầu ra có thể dự đoán từ trạng thái generator nên attacker có thể giả mạo phiên đăng nhập.
Ứng dụng dùng Math.random hoặc hàm random tổng quát để tạo reset token; generator không có bảo đảm mật mã và token có thể bị dò từ các đầu ra quan sát được.
Backend tạo API secret bằng cách hash timestamp với user ID; SHA-256 không biến đầu vào dễ đoán thành bí mật có entropy cao.
Hệ thống dùng UUID phiên bản dựa trên timestamp và địa chỉ node làm bearer credential; cấu trúc ID để lộ thời gian tạo và có thể suy đoán các giá trị lân cận.
ID bản ghi tuần tự được dùng trực tiếp làm password-reset token; attacker chỉ cần tăng hoặc giảm ID để thử truy cập tài khoản khác.
Service khởi động trong môi trường thiếu entropy nhưng vẫn phát hành khóa trước khi nguồn ngẫu nhiên sẵn sàng; key material có thể lặp hoặc dễ dự đoán giữa các lần boot.
Khi secure random source trả lỗi, ứng dụng tự fallback sang PRNG thường để giữ availability; token và key vẫn được phát hành dù không còn bảo đảm an toàn.
Nhóm tự viết generator bằng cách trộn timestamp, process ID và counter; các giá trị này có thể khác nhau nhưng không cung cấp entropy bí mật trước attacker.
Tất cả replica được cấu hình cùng một seed cố định để kết quả test nhất quán; cấu hình test bị đưa vào production khiến các node sinh cùng chuỗi token và nonce.
Process fork sau khi khởi tạo trạng thái DRBG; tiến trình cha và con tiếp tục từ cùng state và có thể sinh ra các chuỗi ngẫu nhiên trùng nhau.
VM được snapshot sau khi CSPRNG đã khởi tạo rồi clone thành nhiều instance; bản sao tiếp tục từ cùng trạng thái RNG và có nguy cơ phát hành token hoặc nonce giống nhau.
Container image chứa file seed được tạo lúc build; mọi container khởi chạy từ image dùng chung material khởi tạo và không có reseed độc lập phù hợp.
Attacker đọc được trạng thái nội bộ của generator nhưng hệ thống không reseed hoặc phục hồi trạng thái; các giá trị tương lai tiếp tục có thể bị dự đoán.
DRBG được reseed từ nguồn entropy chất lượng thấp nhưng hệ thống đánh dấu đã reseed thành công; thao tác reseed không khôi phục được tính khó đoán nếu entropy mới không đủ.
Ứng dụng gọi hàm seed bằng timestamp sau khi CSPRNG đã được khởi tạo và giả định việc đó làm generator mạnh hơn; seed bổ sung có entropy thấp không thay thế nguồn entropy an toàn.
Nhóm thu thập thời gian gõ phím và chuyển động chuột làm nguồn entropy duy nhất cho server headless; nguồn sự kiện thiếu hoặc có thể bị điều khiển khiến seed không đáng tin.
Dashboard báo entropy pool có số bit cao nên đội vận hành kết luận mọi token đầu ra đều an toàn; entropy estimate không thay thế đánh giá CSPRNG, seed và trạng thái generator.
Hardware random number generator bắt đầu trả dữ liệu lặp nhưng không có kiểm tra sức khỏe nguồn; lỗi phần cứng âm thầm ảnh hưởng chất lượng seed.
Ứng dụng chờ nguồn random blocking trong giai đoạn khởi động và readiness probe hết hạn; nhóm cần xác định provider và trạng thái entropy thay vì chuyển sang random yếu.
SecureRandom được khởi tạo với provider khác nhau giữa các hệ điều hành; cấu hình production vô tình chọn implementation không tương thích với giả định về blocking, reseeding hoặc hiệu năng.
Ứng dụng dùng deterministic random provider trong test để snapshot kết quả nhưng profile test bị bật trong production; khóa và token được sinh từ chuỗi có thể tái tạo.
Mỗi request tạo SecureRandom mới và tự seed từ đồng hồ hệ thống; chi phí khởi tạo tăng nhưng entropy thực tế vẫn không được cải thiện bởi seed dễ đoán.
Service gọi nguồn secure-random có thể blocking trong đường xử lý request; khi nguồn entropy hoặc provider chậm, latency tăng và worker pool bị chiếm dụng.
Ứng dụng lấy random integer bằng cách lấy số ngẫu nhiên modulo N; khi miền nguồn không chia hết cho N, một số kết quả xuất hiện thường xuyên hơn và tạo modulo bias.
Chức năng rút thăm dùng Fisher-Yates nhưng chọn chỉ số bằng phép modulo trên random integer; phân phối kết quả không đều dù thuật toán shuffle đúng.
Token reset chỉ có 32 bit entropy vì nhóm giới hạn độ dài URL; attacker có thể brute-force hoặc dò online nếu rate limit không đủ chặt.
Ứng dụng tạo token 256 bit rồi Base64URL encode và tin rằng encoding làm tăng entropy; độ khó đoán vẫn chỉ phụ thuộc số bit ngẫu nhiên ban đầu.
Random identifier được dùng vừa làm ID công khai vừa làm bằng chứng ủy quyền; tính khó đoán của ID bị nhầm với kiểm tra quyền truy cập tài nguyên.
Token bearer được tạo đủ dài nhưng lưu plaintext trong database và log; database dump hoặc log access cho phép replay token cho tới khi hết hạn.
Reset token có entropy cao nhưng không gắn với user, mục đích và thời hạn; một token hợp lệ có thể bị dùng nhầm cho luồng xác thực khác.
One-time token không được đánh dấu đã dùng sau lần xác minh đầu tiên; attacker phát lại cùng token trong thời gian hiệu lực để lặp thao tác nhạy cảm.
OTP sáu chữ số được tạo từ CSPRNG nhưng endpoint không giới hạn số lần thử; không gian chỉ một triệu giá trị vẫn có thể bị brute-force online.
Challenge xác thực được sinh ngẫu nhiên nhưng không gắn với phiên hoặc giao dịch đang chờ; response hợp lệ của một luồng có thể bị ghép vào luồng khác.
Ứng dụng tạo nonce cho AES-GCM bằng random 32-bit; ở lưu lượng lớn, xác suất collision tăng và nonce reuse có thể phá vỡ bảo đảm AEAD.
Nhiều node sinh nonce GCM bằng counter bắt đầu cùng giá trị trong khi chia sẻ một key; nonce bị trùng giữa replica dù từng counter cục bộ tăng đúng.
Counter nonce được lưu trong bộ nhớ và quay về zero sau restart hoặc restore backup; cùng key tiếp tục được dùng với nonce đã phát hành trước đó.
Ứng dụng dùng nonce cố định cho AES-CTR để giảm metadata; hai plaintext dưới cùng key tạo keystream giống nhau và làm lộ quan hệ giữa dữ liệu.
ChaCha20-Poly1305 được triển khai với nonce ngẫu nhiên nhưng key được dùng qua thời gian dài và volume rất lớn mà không đánh giá xác suất collision hoặc giới hạn sử dụng.
AES-CBC dùng IV cố định cho mọi bản ghi; plaintext có cùng block đầu tạo ra ciphertext có thể so sánh và làm lộ mẫu dữ liệu.
IV CBC được tạo từ counter có thể dự đoán trước khi gửi plaintext; CBC cần IV khó đoán tại thời điểm mã hóa, nên tính duy nhất đơn thuần chưa đủ.
Nhóm dùng password salt làm nonce AEAD vì cả hai đều là chuỗi ngẫu nhiên; salt không được thiết kế để đáp ứng quy tắc duy nhất theo key của nonce.
Mọi password hash dùng chung một salt cấu hình; mật khẩu giống nhau tạo digest giống nhau và precomputation có thể tái sử dụng giữa các tài khoản.
Password salt được sinh bằng CSPRNG nhưng chỉ có vài byte; không gian salt nhỏ làm tăng khả năng trùng lặp khi hệ thống có nhiều tài khoản, kể cả khi dùng KDF như Argon2id.
Nhóm dùng salt như một bí mật và lưu nó trong KMS, trong khi bỏ qua việc dùng salt riêng cho từng password; mô hình lưu trữ và KDF bị thiết kế sai mục đích.
Pepper được tạo từ timestamp và đặt tên là random secret; attacker có thể đoán pepper sau khi lấy được password hashes và metadata thời gian.
Encryption key được tạo bằng cách lấy một chuỗi cấu hình dễ nhớ rồi hash SHA-256; entropy của key không vượt quá entropy của passphrase ban đầu.
Ứng dụng yêu cầu 256-bit AES key nhưng chỉ sinh 128 bit rồi nối hai lần; độ dài biểu diễn tăng nhưng entropy không tăng và key space vẫn chỉ có 128 bit.
HKDF dùng một input key material cho nhiều mục đích nhưng bỏ qua context label trong info; derived keys không được tách biệt theo protocol hoặc chức năng.
RSA key pair được tạo trên máy ảo có trạng thái RNG bị clone; hai máy có thể sinh prime trùng nhau và tạo khóa riêng dễ bị phân tích.
ECDSA signer tái sử dụng cùng nonce k cho hai message; từ các chữ ký có thể suy ra private signing key.
ECDSA dùng nonce sinh từ generator yếu; attacker quan sát nhiều chữ ký và khai thác nonce bias để khôi phục khóa riêng.
Thư viện chữ ký hỗ trợ deterministic ECDSA nhưng nhóm tự triển khai thuật toán nonce; lỗi xử lý hash hoặc scalar khiến kết quả không tuân chuẩn và có nguy cơ lộ khóa.
HMAC key được sinh từ chuỗi cố định trong file cấu hình; attacker biết cấu hình hoặc dò được secret và có thể tạo message authentication code giả.
Một hệ thống dùng chung một random secret cho HMAC webhook, token session và key derivation; lộ một mục đích làm ảnh hưởng tất cả miền bảo mật.
Webhook signature có HMAC hợp lệ nhưng không kèm timestamp hoặc nonce duy nhất; request bị ghi lại có thể phát lại mà không bị phát hiện.
Ứng dụng so sánh HMAC tag bằng phép so sánh dừng tại byte sai đầu tiên; thời gian phản hồi có thể tiết lộ độ dài prefix khớp.
AES-GCM tag bị cắt ngắn quá mức để giảm kích thước message; xác suất giả mạo tag tăng và không còn phù hợp với yêu cầu an toàn.
Private key TLS được sinh từ entropy yếu trên một nhóm thiết bị cùng firmware; nhiều thiết bị có thể tạo key trùng hoặc dễ dự đoán và làm suy yếu PKI.
Certificate serial number được tạo bằng bộ đếm cục bộ không phối hợp giữa các CA replica; cùng issuer có thể phát hành serial trùng và gây vấn đề nhận diện hoặc thu hồi.
TLS ephemeral key exchange tái sử dụng private ephemeral key qua nhiều phiên; lộ khóa làm suy giảm forward secrecy so với việc tạo khóa tạm thời mới.
TLS session ticket key được tạo một lần rồi dùng vô thời hạn trên toàn cluster; compromise một node ảnh hưởng các ticket và phiên được bảo vệ bằng cùng key.
KMS tạo data encryption key nhưng ứng dụng tự sinh wrapping key bằng PRNG thường; bảo vệ envelope encryption bị suy yếu ở lớp khóa bọc.
Key rotation sinh master key mới nhưng không ghi key ID/version cạnh ciphertext; hệ thống không biết dùng khóa nào để giải mã dữ liệu cũ.
Nhóm kiểm tra RNG bằng cách xác nhận output không có chuỗi lặp ngắn; kiểm tra thống kê đơn giản bị hiểu nhầm là chứng minh CSPRNG an toàn trước tấn công.
Quy trình kiểm thử randomness chỉ chạy trên máy phát triển và không kiểm tra fork, VM snapshot, restart, entropy starvation hoặc nhiều replica; lỗi triển khai chỉ xuất hiện trong production.
