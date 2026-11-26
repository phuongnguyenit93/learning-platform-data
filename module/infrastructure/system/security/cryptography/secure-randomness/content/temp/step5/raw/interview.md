Bạn sẽ phân biệt randomness, pseudorandomness và cryptographic randomness theo mục tiêu sử dụng và khả năng dự đoán như thế nào?
Bạn sẽ giải thích entropy biểu thị mức độ bất định của nguồn ngẫu nhiên và vì sao số byte đầu ra không đồng nghĩa với lượng entropy như thế nào?
Bạn sẽ phân biệt Shannon entropy với min-entropy khi đánh giá nguồn seed cho hệ thống mật mã ra sao?
Bạn sẽ xác định những nguồn entropy phù hợp từ hệ điều hành, phần cứng và môi trường vận hành như thế nào?
Bạn sẽ đánh giá rủi ro khi seed được tạo từ timestamp, process ID, counter hoặc các giá trị dễ quan sát ra sao?
Bạn sẽ giải thích vì sao PRNG thông thường có thể tạo chuỗi thống kê tốt nhưng vẫn không an toàn cho khóa và token như thế nào?
Bạn sẽ mô tả yêu cầu của CSPRNG về tính không thể dự đoán, khả năng chống khôi phục trạng thái và bảo vệ đầu ra trước quan sát như thế nào?
Bạn sẽ phân biệt entropy source, entropy pool, seed và deterministic random bit generator trong kiến trúc sinh số ngẫu nhiên ra sao?
Bạn sẽ giải thích DRBG mở rộng seed thành chuỗi bit dài và vai trò của reseeding trong duy trì an toàn như thế nào?
Bạn sẽ so sánh các họ DRBG dựa trên hash, HMAC và block cipher về cấu trúc và yêu cầu triển khai ra sao?
Bạn sẽ xác định khi nào CSPRNG cần reseed và lựa chọn giới hạn số byte hoặc số request giữa các lần reseed như thế nào?
Bạn sẽ đánh giá rủi ro khi một CSPRNG khởi động với entropy chưa đủ trong giai đoạn boot sớm ra sao?
Bạn sẽ phân biệt API random an toàn của hệ điều hành với hàm random mặc định của thư viện ứng dụng như thế nào?
Bạn sẽ lựa chọn API hệ điều hành như getrandom hoặc nguồn CSPRNG tương đương để lấy byte ngẫu nhiên an toàn ra sao?
Bạn sẽ đánh giá implementation và provider của SecureRandom hoặc API CSPRNG tương đương để xác định nguồn entropy thực tế như thế nào?
Bạn sẽ xử lý trường hợp API sinh số ngẫu nhiên chặn trong lúc chờ entropy và ảnh hưởng đến startup hoặc request latency ra sao?
Bạn sẽ giải thích vì sao không nên tự xây entropy pool hoặc CSPRNG khi hệ điều hành đã cung cấp primitive đã được kiểm chứng như thế nào?
Bạn sẽ phân biệt kiểm tra chất lượng thống kê với kiểm chứng tính không thể dự đoán của CSPRNG như thế nào?
Bạn sẽ sử dụng bộ kiểm thử thống kê để phát hiện bias hoặc lỗi triển khai mà không kết luận nhầm rằng chuỗi đã an toàn mật mã ra sao?
Bạn sẽ đánh giá entropy source và DRBG theo tiêu chuẩn hoặc quy trình kiểm định như NIST SP 800-90A, 90B và 90C như thế nào?
Bạn sẽ giải thích nguy cơ state compromise extension khi attacker biết trạng thái DRBG và những điều kiện để hệ thống phục hồi ra sao?
Bạn sẽ xử lý fork safety khi tiến trình sinh số ngẫu nhiên bị fork và các tiến trình con có thể thừa hưởng cùng trạng thái như thế nào?
Bạn sẽ đánh giá nguy cơ VM snapshot, container checkpoint hoặc clone image làm nhiều instance sinh cùng chuỗi ngẫu nhiên ra sao?
Bạn sẽ thiết kế reseed hoặc cơ chế phân biệt instance sau restore snapshot để tránh lặp khóa, nonce và token như thế nào?
Bạn sẽ phân tích tác động của entropy starvation trong hệ thống headless, embedded hoặc cloud instance mới khởi động ra sao?
Bạn sẽ xác định cách bảo vệ nguồn entropy trước lỗi phần cứng, cấu hình sai hoặc can thiệp từ môi trường ảo hóa như thế nào?
Bạn sẽ chọn số bit entropy cần thiết cho session ID, reset token, API key và challenge theo thời hạn cùng mức rủi ro nào?
Bạn sẽ tính xác suất va chạm của token ngẫu nhiên theo số bit và số lượng token được phát hành như thế nào?
Bạn sẽ thiết kế token opaque có entropy đủ lớn, encoding phù hợp và không để lộ dữ liệu nhạy cảm trong cấu trúc token ra sao?
Bạn sẽ phân biệt UUID ngẫu nhiên dùng làm định danh với token bí mật dùng để cấp quyền truy cập như thế nào?
Bạn sẽ giải thích vì sao UUID hoặc identifier có thể đoán được không nên tự động được xem là credential an toàn như thế nào?
Bạn sẽ tránh modulo bias khi chuyển byte ngẫu nhiên thành số trong một khoảng không chia hết cho miền giá trị nguồn như thế nào?
Bạn sẽ sử dụng rejection sampling hoặc API bounded random để tạo số nguyên phân bố đều trong một khoảng như thế nào?
Bạn sẽ xác định khi nào cần random nonce không thể đoán trước và khi nào yêu cầu quan trọng hơn là nonce không bao giờ lặp lại ra sao?
Bạn sẽ phân biệt nonce uniqueness với unpredictability trong các chế độ mã hóa và giao thức khác nhau như thế nào?
Bạn sẽ giải thích vì sao nonce reuse trong AES-GCM có thể làm lộ thông tin và phá vỡ tính toàn vẹn như thế nào?
Bạn sẽ lựa chọn cách tạo nonce cho AES-GCM khi có nhiều node mã hóa đồng thời và cần bảo đảm không trùng lặp ra sao?
Bạn sẽ phân biệt yêu cầu IV của CBC, nonce của CTR/GCM và tweak của XTS để tránh dùng cùng một quy tắc ngẫu nhiên cho mọi chế độ như thế nào?
Bạn sẽ thiết kế generation của salt, nonce, IV và challenge để mỗi giá trị đáp ứng đúng yêu cầu của primitive sử dụng ra sao?
Bạn sẽ tạo khóa đối xứng từ CSPRNG và xác định độ dài khóa phù hợp với AES-128, AES-256 hoặc thuật toán tương ứng như thế nào?
Bạn sẽ phân biệt tạo khóa ngẫu nhiên trực tiếp với dẫn xuất khóa từ secret gốc bằng KDF trong các tình huống khác nhau ra sao?
Bạn sẽ sử dụng HKDF để tách nhiều khóa theo mục đích từ input keying material và context như thế nào?
Bạn sẽ giải thích key separation giúp tránh tái sử dụng cùng một khóa cho encryption, MAC và các giao thức khác như thế nào?
Bạn sẽ phân biệt KDF mật mã như HKDF với password-based KDF như Argon2id hoặc PBKDF2 theo đầu vào và mục tiêu bảo vệ ra sao?
Bạn sẽ lựa chọn authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305 thay cho encryption không có kiểm tra toàn vẹn như thế nào?
Bạn sẽ giải thích vai trò của associated data trong AEAD và lựa chọn metadata cần được xác thực nhưng không mã hóa ra sao?
Bạn sẽ xác định cách quản lý key, nonce và tag để quá trình giải mã từ chối dữ liệu bị sửa đổi như thế nào?
Bạn sẽ phân biệt hash, MAC và digital signature về tính toàn vẹn, xác thực nguồn gốc và khả năng chống chối bỏ ra sao?
Bạn sẽ lựa chọn SHA-256, SHA-3 hoặc hash phù hợp cho fingerprint và integrity check theo yêu cầu nào?
Bạn sẽ giải thích vì sao hash nhanh không thể thay thế password hashing function khi đầu vào là mật khẩu như thế nào?
Bạn sẽ lựa chọn HMAC khi cần xác thực thông điệp bằng secret chung và bảo vệ khóa MAC ra sao?
Bạn sẽ so sánh RSA-PSS, ECDSA và EdDSA về giả định mật mã, kích thước chữ ký và đặc điểm triển khai như thế nào?
Bạn sẽ giải thích vì sao ECDSA yêu cầu nonce ký duy nhất và khó đoán, cùng hậu quả khi nonce bị lặp hoặc rò rỉ như thế nào?
Bạn sẽ đánh giá rủi ro dùng nguồn random yếu trong quá trình sinh khóa RSA hoặc khóa elliptic-curve ra sao?
Bạn sẽ thiết kế quy trình sinh cặp khóa bất đối xứng để bảo đảm private key có entropy đủ và public key được kiểm tra hợp lệ như thế nào?
Bạn sẽ phân biệt key generation với key derivation và xác định khi nào cần mỗi cơ chế ra sao?
Bạn sẽ thiết kế phân cấp khóa gồm root key, key-encryption key và data-encryption key để giới hạn phạm vi ảnh hưởng khi lộ khóa như thế nào?
Bạn sẽ quản lý khóa trong KMS hoặc HSM để kiểm soát quyền sử dụng, audit, backup và rotation ra sao?
Bạn sẽ phân biệt envelope encryption với mã hóa dữ liệu trực tiếp bằng master key trong hệ thống lưu trữ như thế nào?
Bạn sẽ lựa chọn quy trình key rotation và key versioning để giải mã dữ liệu cũ trong khi ghi dữ liệu mới bằng khóa mới ra sao?
Bạn sẽ xác định cách thu hồi, hủy hoặc khôi phục khóa khi nghi ngờ compromise mà vẫn duy trì khả năng phục hồi dữ liệu như thế nào?
Bạn sẽ bảo vệ private key khỏi xuất khỏi HSM hoặc secure enclave và đánh giá giới hạn của non-exportable key ra sao?
Bạn sẽ giải thích PKI liên kết public key với danh tính thông qua certificate và trust chain như thế nào?
Bạn sẽ xác minh certificate chain, hostname, validity period, key usage và revocation status trong một kết nối TLS ra sao?
Bạn sẽ mô tả TLS sử dụng randomness, nonce và key derivation trong handshake để tạo traffic keys như thế nào?
Bạn sẽ giải thích vai trò của client random, server random và ephemeral key exchange trong các phiên bản TLS hiện đại ra sao?
Bạn sẽ đánh giá vì sao TLS certificate hợp lệ không thể bù đắp cho private key yếu hoặc nguồn random không an toàn như thế nào?
Bạn sẽ lựa chọn TLS 1.3 cipher suite và xác định trách nhiệm của hệ thống đối với certificate, key và random generation ra sao?
Bạn sẽ phân tích hậu quả khi random generator yếu làm lặp ephemeral key hoặc nonce trong giao thức bảo mật như thế nào?
Bạn sẽ thiết kế quy trình kiểm tra và giám sát việc tạo khóa, nonce và token để phát hiện giá trị trùng lặp hoặc entropy bất thường ra sao?
Bạn sẽ xác định những sự kiện liên quan đến key generation và random provider cần ghi audit mà không làm lộ seed hoặc secret như thế nào?
Bạn sẽ kiểm thử CSPRNG integration bằng cách kiểm tra API usage, lỗi khởi tạo, fork behavior và snapshot restore như thế nào?
Bạn sẽ xây dựng test để phát hiện nonce reuse trong môi trường nhiều worker hoặc nhiều region như thế nào?
Bạn sẽ sử dụng fault injection để đánh giá hành vi khi entropy source, KMS hoặc HSM không khả dụng ra sao?
Bạn sẽ phân biệt lỗi nguồn entropy với lỗi provider, lỗi quyền truy cập thiết bị hoặc lỗi cấu hình thuật toán khi điều tra sự cố như thế nào?
Bạn sẽ nhận diện các sai lầm mật mã phổ biến như tự chế thuật toán, tái sử dụng nonce, hard-code key và dùng random không an toàn ra sao?
Nếu nhiều VM clone từ cùng snapshot sinh ra token hoặc khóa giống nhau, bạn sẽ xác định nguyên nhân và thiết kế phục hồi như thế nào?
Nếu một hệ thống mã hóa phát hiện nonce AES-GCM bị trùng giữa hai instance, bạn sẽ đánh giá phạm vi ảnh hưởng và xử lý khóa ra sao?
Nếu API token có đủ độ dài nhưng được tạo từ timestamp và counter, bạn sẽ đánh giá khả năng đoán và thay thế cơ chế sinh token như thế nào?
Nếu ECDSA signature của nhiều giao dịch vô tình dùng lại nonce, bạn sẽ xác định rủi ro lộ private key và kế hoạch thay khóa ra sao?
Nếu dịch vụ khởi động trong môi trường thiếu entropy và request tạo khóa bị treo, bạn sẽ chẩn đoán nguồn random và thiết kế readiness như thế nào?
Bạn sẽ xây dựng kiến trúc cryptographic randomness đầu cuối cho ứng dụng gồm entropy, CSPRNG, key/nonce/token generation, key management, PKI/TLS và kiểm thử như thế nào?
