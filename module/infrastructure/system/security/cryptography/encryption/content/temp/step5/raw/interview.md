Bạn phân biệt mục tiêu bảo mật của mã hóa với hashing, signing và message authentication code như thế nào?
Bạn giải thích sự khác nhau giữa confidentiality, integrity và authenticity trong một thiết kế mã hóa ra sao?
Trong mã hóa đối xứng, khóa bí mật được dùng ở bước mã hóa và giải mã như thế nào?
Bạn đánh giá ưu điểm và giới hạn của mã hóa đối xứng khi xử lý lượng dữ liệu lớn ra sao?
Trong mã hóa bất đối xứng, vai trò của public key và private key khác nhau như thế nào?
Vì sao mã hóa bất đối xứng thường không được dùng trực tiếp để mã hóa toàn bộ tệp dữ liệu lớn?
Bạn phân biệt encryption key với signing key và giải thích vì sao không nên tái sử dụng cùng một khóa cho cả hai mục đích như thế nào?
Bạn thiết kế hybrid encryption kết hợp mã hóa bất đối xứng và đối xứng cho việc chia sẻ tệp ra sao?
Trong mô hình KEM-DEM, encapsulation và data encryption đảm nhiệm những vai trò nào?
Bạn chọn RSA-OAEP hoặc một cơ chế dựa trên elliptic curve cho bài toán bảo vệ khóa như thế nào?
Bạn giải thích vì sao elliptic-curve Diffie-Hellman thường là cơ chế thỏa thuận khóa chứ không phải thuật toán mã hóa dữ liệu trực tiếp như thế nào?
Bạn phân biệt key agreement và key transport trong một giao thức bảo mật ra sao?
Bạn chọn kích thước khóa và thuật toán dựa trên mức độ nhạy cảm, vòng đời dữ liệu và yêu cầu tương thích như thế nào?
Bạn đánh giá AES-128 và AES-256 theo mức an toàn, hiệu năng và môi trường triển khai ra sao?
Bạn giải thích vì sao ECB không phù hợp để mã hóa dữ liệu có cấu trúc lặp lại như thế nào?
Bạn mô tả cách CBC sử dụng IV và padding, cùng những yêu cầu bảo mật đi kèm ra sao?
Bạn phân tích rủi ro khi tái sử dụng IV hoặc nonce trong các chế độ mã hóa khác nhau như thế nào?
Bạn phân biệt yêu cầu IV ngẫu nhiên khó đoán của CBC với yêu cầu nonce không lặp lại của CTR và GCM ra sao?
Bạn giải thích cách CTR biến block cipher thành luồng keystream và điều gì xảy ra nếu nonce-counter bị lặp như thế nào?
Bạn mô tả cách GCM kết hợp mã hóa và xác thực dữ liệu trong một thao tác AEAD ra sao?
Bạn giải thích vai trò của authentication tag trong AES-GCM và cách ứng dụng nên xử lý khi xác minh tag thất bại như thế nào?
Bạn phân biệt dữ liệu được mã hóa với Additional Authenticated Data trong AEAD ra sao?
Bạn chọn AAD nào để ràng buộc ciphertext với metadata như tenant, phiên bản bản ghi hoặc loại nội dung như thế nào?
Bạn giải thích vì sao không được sử dụng lại nonce với cùng khóa trong AES-GCM và hậu quả có thể xảy ra như thế nào?
Bạn thiết kế cách sinh và lưu nonce để tránh trùng lặp khi nhiều worker cùng mã hóa bằng một khóa như thế nào?
Bạn so sánh AES-GCM với ChaCha20-Poly1305 theo yêu cầu phần cứng, hiệu năng và khả năng triển khai như thế nào?
Bạn giải thích lợi ích của AEAD so với việc tự ghép một chế độ mã hóa với MAC theo cách thủ công như thế nào?
Bạn phân tích giới hạn của AES-XTS khi dùng để mã hóa sector trên thiết bị lưu trữ và vì sao nó không thay thế AEAD ra sao?
Bạn lựa chọn chế độ mã hóa khi cần cả confidentiality và integrity thay vì chỉ che nội dung như thế nào?
Bạn xử lý padding oracle risk trong hệ thống dùng chế độ CBC và thông báo lỗi giải mã như thế nào?
Bạn giải thích vì sao plaintext không nên được sử dụng trước khi authentication tag của AEAD được xác minh thành công như thế nào?
Bạn thiết kế xử lý lỗi giải mã sao cho không tiết lộ thông tin qua thông báo lỗi, thời gian phản hồi hoặc hành vi khác biệt ra sao?
Bạn xác định yêu cầu về random number generator và entropy khi tạo khóa, nonce hoặc IV như thế nào?
Bạn phân biệt cryptographically secure random generator với bộ sinh số giả ngẫu nhiên thông thường trong ứng dụng mật mã ra sao?
Bạn xây dựng vòng đời khóa từ sinh, phân phối, lưu trữ, sử dụng, xoay vòng đến hủy bỏ như thế nào?
Bạn lựa chọn KMS hoặc HSM cho hệ thống có yêu cầu bảo vệ khóa ở mức cao dựa trên tiêu chí nào?
Bạn phân biệt data encryption key và key encryption key trong mô hình envelope encryption như thế nào?
Bạn mô tả quy trình envelope encryption khi mã hóa một đối tượng dữ liệu và lưu wrapped data key cùng ciphertext ra sao?
Bạn xoay vòng key encryption key mà không phải giải mã và mã hóa lại toàn bộ dữ liệu lớn bằng cách nào?
Bạn xử lý việc xoay vòng data encryption key để bảo vệ dữ liệu cũ và dữ liệu mới như thế nào?
Bạn lập kế hoạch re-encryption khi thuật toán hoặc khóa hiện tại không còn đáp ứng yêu cầu bảo mật ra sao?
Bạn kiểm soát quyền truy cập khóa theo danh tính workload, vai trò vận hành và nguyên tắc least privilege như thế nào?
Bạn phân tách quyền quản trị khóa với quyền sử dụng khóa để giảm rủi ro nội bộ ra sao?
Bạn bảo vệ bản sao lưu khóa và quy trình khôi phục khi KMS hoặc HSM gặp sự cố như thế nào?
Bạn phản ứng ra sao khi nghi ngờ khóa mã hóa đã bị lộ hoặc bị sử dụng trái phép?
Bạn đánh giá tác động của việc thu hồi khóa đối với dữ liệu đã mã hóa, bản sao lưu và dịch vụ đang hoạt động như thế nào?
Bạn quản lý phiên bản metadata mã hóa để biết ciphertext được tạo bằng thuật toán, nonce và key version nào ra sao?
Bạn thiết kế định dạng lưu ciphertext sao cho có thể hỗ trợ thay đổi thuật toán và crypto agility như thế nào?
Bạn mã hóa dữ liệu at rest ở cấp thiết bị, volume, cơ sở dữ liệu và ứng dụng khác nhau ra sao?
Bạn lựa chọn mã hóa toàn đĩa hay mã hóa ở cấp ứng dụng dựa trên ranh giới tin cậy và mô hình đe dọa như thế nào?
Bạn đánh giá giới hạn của mã hóa toàn đĩa khi hệ điều hành hoặc ứng dụng đã được mở khóa như thế nào?
Bạn bảo vệ dữ liệu trong backup, snapshot, object storage và bản sao dữ liệu bằng chính sách mã hóa nào?
Bạn giải thích vai trò của TLS trong bảo vệ dữ liệu in transit và phân biệt nó với mã hóa dữ liệu lưu trữ ra sao?
Bạn mô tả cách TLS sử dụng chứng thư, thỏa thuận khóa và mã hóa đối xứng để bảo vệ một phiên kết nối như thế nào?
Bạn đánh giá forward secrecy và vai trò của ephemeral key exchange trong việc giảm tác động khi khóa dài hạn bị lộ ra sao?
Bạn thiết kế quản lý certificate và private key cho dịch vụ để hạn chế nguy cơ lộ khóa hoặc hết hạn chứng thư như thế nào?
Bạn lựa chọn thư viện mật mã và API cấp cao thay vì tự triển khai thuật toán như thế nào?
Bạn đánh giá một thuật toán hoặc chế độ mã hóa đã lỗi thời và lập kế hoạch thay thế mà vẫn tương thích dữ liệu cũ ra sao?
Bạn phân biệt mã hóa mật khẩu bằng encryption với lưu mật khẩu bằng password hashing có salt và work factor như thế nào?
Bạn lựa chọn KDF như Argon2id, scrypt hoặc PBKDF2 cho mục đích dẫn xuất khóa từ mật khẩu dựa trên tiêu chí nào?
Bạn sử dụng HKDF để dẫn xuất các khóa độc lập từ một secret gốc và phân tách mục đích sử dụng ra sao?
Bạn giải thích vì sao cần domain separation khi một secret hoặc key derivation process phục vụ nhiều mục đích như thế nào?
Bạn thiết kế cơ chế xác thực tính toàn vẹn cho metadata hoặc header đi kèm ciphertext như thế nào?
Bạn kiểm thử hệ thống mã hóa bằng known-answer test và test vector để xác minh điều gì?
Bạn xây dựng negative test cho nonce lặp, tag sai, ciphertext bị sửa và key version không hợp lệ như thế nào?
Bạn kiểm thử khả năng tương tác giữa nhiều thư viện hoặc nền tảng khi trao đổi ciphertext ra sao?
Bạn sử dụng fuzzing và kiểm thử biên để tìm lỗi trong parser, định dạng ciphertext và quy trình giải mã như thế nào?
Bạn đánh giá side-channel risk như timing, cache behavior hoặc lỗi xử lý khóa trong môi trường triển khai ra sao?
Bạn bảo vệ secret key khỏi bị ghi vào log, crash dump, telemetry hoặc file cấu hình không an toàn như thế nào?
Bạn xử lý dữ liệu plaintext trong bộ nhớ để giảm nguy cơ lộ qua bản sao tạm, swap hoặc dump tiến trình ra sao?
Bạn xây dựng quy trình migration từ thuật toán cũ sang AEAD mà vẫn đọc được dữ liệu lịch sử và xác minh tính toàn vẹn như thế nào?
Bạn xác định tiêu chí nghiệm thu cho một hệ thống encryption về confidentiality, integrity, key lifecycle, hiệu năng và khả năng phục hồi như thế nào?
