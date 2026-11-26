Bạn phân biệt mục tiêu toàn vẹn dữ liệu, xác thực nguồn gốc và tính bí mật khi lựa chọn hash, MAC hoặc chữ ký số như thế nào?
Bạn giải thích hàm băm mật mã nhận dữ liệu đầu vào có độ dài tùy ý và tạo digest có độ dài cố định như thế nào?
Bạn phân biệt tính kháng tiền ảnh, kháng tiền ảnh thứ hai và kháng va chạm trong thiết kế hàm băm như thế nào?
Bạn giải thích vì sao việc tìm hai thông điệp bất kỳ có cùng digest khác với việc tìm thông điệp khớp một digest đã cho như thế nào?
Bạn phân tích ảnh hưởng của birthday bound đến độ an toàn va chạm khi digest có độ dài hữu hạn như thế nào?
Bạn xác định vì sao digest của dữ liệu công khai chỉ hỗ trợ kiểm tra nội dung có thay đổi, nhưng không chứng minh ai đã tạo ra dữ liệu như thế nào?
Bạn phân biệt cryptographic hash với checksum hoặc CRC về mục tiêu và khả năng chống sửa đổi có chủ đích như thế nào?
Bạn lựa chọn hàm băm cho kiểm tra toàn vẹn tệp, content addressing và xác minh artifact dựa trên yêu cầu an toàn và hiệu năng như thế nào?
Bạn so sánh SHA-256, SHA-512 và các biến thể SHA-2 về độ dài digest, hiệu năng và phạm vi sử dụng như thế nào?
Bạn phân biệt kiến trúc xử lý của SHA-2 với SHA-3 và giải thích sponge construction mang lại đặc điểm gì như thế nào?
Bạn so sánh SHA-3 với SHAKE về đầu ra cố định và đầu ra có thể mở rộng như thế nào?
Bạn đánh giá BLAKE2 và BLAKE3 trong các hệ thống cần băm dữ liệu tốc độ cao hoặc xử lý song song như thế nào?
Bạn xác định vì sao MD5 và SHA-1 không còn phù hợp cho mục tiêu cần kháng va chạm như thế nào?
Bạn giải thích length extension attack có thể ảnh hưởng đến một số cấu trúc hash kiểu Merkle–Damgård khi ứng dụng ghép secret với message như thế nào?
Bạn phân biệt hash thông thường, keyed hash và message authentication code trong việc bảo vệ dữ liệu như thế nào?
Bạn lựa chọn digest length phù hợp với mức rủi ro va chạm và yêu cầu tương thích của hệ thống như thế nào?
Bạn thiết kế quy trình băm tệp lớn theo luồng để giới hạn bộ nhớ mà vẫn bảo đảm digest phản ánh đúng toàn bộ byte đầu vào như thế nào?
Bạn xử lý dữ liệu có nhiều cách biểu diễn tương đương trước khi băm để các bên tính ra cùng digest như thế nào?
Bạn giải thích vai trò của canonicalization và serialization xác định khi băm JSON, XML hoặc cấu trúc dữ liệu phức tạp như thế nào?
Bạn sử dụng domain separation để tránh một digest hoặc kết quả băm trong ngữ cảnh này bị diễn giải nhầm sang ngữ cảnh khác như thế nào?
Bạn phân biệt việc thêm salt cho hash với việc dùng secret key trong MAC và giải thích mục đích của từng cơ chế như thế nào?
Bạn xác định khi nào cần dùng hash để định danh nội dung và khi nào cần MAC hoặc chữ ký để xác minh nguồn gốc như thế nào?
Bạn giải thích vì sao hash hoặc chữ ký số không tự cung cấp tính bí mật cho thông điệp như thế nào?
Bạn mô tả MAC tạo ra tag xác thực thông điệp bằng khóa bí mật dùng chung như thế nào?
Bạn phân biệt MAC với hash không khóa về khả năng chống giả mạo khi attacker có thể tự tạo thông điệp và digest như thế nào?
Bạn giải thích HMAC kết hợp hash function với khóa bí mật qua các lớp inner và outer padding như thế nào?
Bạn so sánh HMAC-SHA-256 với HMAC-SHA-512 về độ an toàn, hiệu năng và khả năng tương thích như thế nào?
Bạn phân biệt HMAC với cách ghép trực tiếp secret key vào trước hoặc sau message rồi băm như thế nào?
Bạn giải thích CMAC sử dụng block cipher như AES để tạo message authentication tag như thế nào?
Bạn so sánh HMAC, CMAC và KMAC về primitive mật mã, cách sử dụng khóa và môi trường phù hợp như thế nào?
Bạn giải thích cách Poly1305 tạo authentication tag và vì sao việc dùng one-time key đúng quy định là điều kiện an toàn quan trọng như thế nào?
Bạn đánh giá khi nào nên dùng chế độ keyed của BLAKE2 hoặc BLAKE3 thay cho HMAC như thế nào?
Bạn lựa chọn độ dài MAC tag và phân tích xác suất giả mạo khi tag bị cắt ngắn như thế nào?
Bạn xác minh MAC tag theo cách so sánh constant-time để giảm rò rỉ thông tin qua thời gian phản hồi như thế nào?
Bạn xử lý trường hợp MAC verification thất bại để tránh tiết lộ chi tiết nội bộ hoặc tạo oracle cho attacker như thế nào?
Bạn giải thích vì sao bên nào giữ khóa MAC đều có khả năng tạo tag hợp lệ và điều đó giới hạn khả năng quy trách nhiệm như thế nào?
Bạn thiết kế phân phối khóa MAC giữa nhiều dịch vụ sao cho chỉ các bên cần tạo hoặc xác minh tag mới có quyền sử dụng khóa như thế nào?
Bạn quản lý khóa MAC riêng cho từng đối tác hoặc từng tenant để giảm phạm vi ảnh hưởng khi một khóa bị lộ như thế nào?
Bạn sử dụng key derivation và context separation để tạo khóa MAC khác nhau cho từng mục đích từ một khóa gốc như thế nào?
Bạn sử dụng HKDF với các bước extract và expand để dẫn xuất khóa MAC hoặc khóa ký theo ngữ cảnh, và vì sao không nên xem hash thông thường là KDF tùy ý như thế nào?
Bạn phân biệt MAC với authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305 về việc bảo vệ toàn vẹn và tính bí mật như thế nào?
Bạn giải thích vì sao MAC hợp lệ không tự ngăn replay một thông điệp đã được gửi trước đó như thế nào?
Bạn kết hợp MAC với nonce, sequence number, timestamp hoặc trạng thái chống phát lại để bảo vệ giao thức như thế nào?
Bạn thiết kế MAC cho webhook để ràng buộc MAC tag với raw request body, timestamp và định danh endpoint như thế nào?
Bạn xử lý canonicalization của HTTP method, path, query, headers và body khi tạo MAC cho API request như thế nào?
Bạn xác định cách xử lý header trùng lặp, thứ tự header hoặc encoding khác nhau để tránh hai bên tính MAC trên dữ liệu khác nhau như thế nào?
Bạn quản lý thời gian chấp nhận timestamp và lưu nonce đã dùng để cân bằng chống replay với sai lệch đồng hồ như thế nào?
Bạn giải thích chữ ký số sử dụng private key để ký và public key để xác minh thông điệp hoặc digest như thế nào?
Bạn phân biệt chữ ký số với MAC về mô hình khóa, khả năng xác minh độc lập và khả năng quy trách nhiệm như thế nào?
Bạn đánh giá giới hạn của khái niệm non-repudiation khi private key có thể bị chia sẻ, đánh cắp hoặc sử dụng qua dịch vụ ký thay mặt như thế nào?
Bạn giải thích vì sao chữ ký số chỉ có ý nghĩa xác thực danh tính khi public key được liên kết đáng tin cậy với chủ thể như thế nào?
Bạn so sánh RSA-PSS với RSA PKCS#1 v1.5 signature về padding, tính ngẫu nhiên và lựa chọn cho hệ thống mới như thế nào?
Bạn phân biệt RSA signature với RSA encryption và giải thích vì sao hai mục đích này không được dùng thay thế cho nhau như thế nào?
Bạn mô tả ECDSA tạo chữ ký từ private key, message digest và nonce dùng trong mỗi lần ký như thế nào?
Bạn giải thích vì sao tái sử dụng hoặc làm lộ nonce của ECDSA có thể dẫn tới khôi phục private key như thế nào?
Bạn so sánh nonce ECDSA được sinh ngẫu nhiên với nonce xác định theo RFC 6979 về yêu cầu triển khai và rủi ro như thế nào?
Bạn đánh giá Ed25519 và Ed448 về trải nghiệm triển khai, hiệu năng và khả năng tương thích so với các lựa chọn chữ ký khác như thế nào?
Bạn phân biệt các biến thể EdDSA thuần, pre-hash và có context khi giao thức cần ký dữ liệu theo ngữ cảnh như thế nào?
Bạn lựa chọn thuật toán chữ ký dựa trên yêu cầu bảo mật, kích thước khóa, chữ ký, hiệu năng và hỗ trợ nền tảng như thế nào?
Bạn giải thích vì sao cần xác định rõ thuật toán và tham số khi xác minh chữ ký thay vì để verifier tự suy đoán từ dữ liệu đầu vào như thế nào?
Bạn xử lý thuật toán chữ ký yếu hoặc đã bị loại bỏ trong quá trình algorithm migration mà vẫn duy trì xác minh dữ liệu lịch sử như thế nào?
Bạn phân biệt chữ ký trên thông điệp gốc với chữ ký trên digest và giải thích quy trình hash-then-sign hoạt động như thế nào?
Bạn thiết kế domain separation hoặc context binding để chữ ký hợp lệ trong một giao thức không thể bị tái sử dụng ở giao thức khác như thế nào?
Bạn chuẩn hóa cấu trúc dữ liệu trước khi ký để tránh khác biệt giữa thứ tự trường, encoding và biểu diễn số như thế nào?
Bạn đánh giá rủi ro khi ký JSON chưa canonicalize hoặc chuỗi dữ liệu có nhiều biểu diễn tương đương như thế nào?
Bạn phân biệt encoding chữ ký ASN.1 DER với dạng chữ ký fixed-width trong các giao thức sử dụng ECDSA như thế nào?
Bạn kiểm tra tính canonical của chữ ký ECDSA và xử lý signature malleability khi cùng một thông điệp có thể có nhiều biểu diễn chữ ký như thế nào?
Bạn xác minh chữ ký trên file hoặc artifact lớn theo luồng và bảo đảm byte được kiểm tra đúng với byte sẽ được sử dụng như thế nào?
Bạn thiết kế quy trình ký và xác minh phần mềm, firmware hoặc gói cập nhật để ngăn artifact bị thay thế trên đường phân phối như thế nào?
Bạn kết hợp chữ ký với manifest, version và metadata để ngăn rollback về một bản phát hành cũ vẫn có chữ ký hợp lệ như thế nào?
Bạn phân biệt xác minh chữ ký mật mã thành công với quyết định tin cậy signer hoặc cho phép cài đặt artifact như thế nào?
Bạn xây dựng chuỗi tin cậy cho public signing key thông qua certificate, trust store, key pinning hoặc cơ chế phân phối khóa như thế nào?
Bạn xác định các bước cần thực hiện khi xác minh certificate chứa public key ký, bao gồm chain, validity, key usage và trạng thái thu hồi như thế nào?
Bạn quản lý private signing key bằng HSM, KMS hoặc secure hardware để giới hạn khả năng xuất khóa và kiểm soát quyền ký như thế nào?
Bạn thiết kế phân quyền signing service để ứng dụng chỉ được yêu cầu ký đúng loại dữ liệu và đúng mục đích như thế nào?
Bạn xoay vòng khóa MAC hoặc signing key mà vẫn hỗ trợ xác minh dữ liệu được tạo bằng khóa cũ trong giai đoạn chuyển tiếp như thế nào?
Bạn xác định thời điểm thu hồi khóa, ngừng ký và xử lý chữ ký lịch sử khi phát hiện private key bị compromise như thế nào?
Bạn quản lý key identifier và phiên bản thuật toán trong message envelope để verifier chọn đúng khóa mà không tin dữ liệu định tuyến khóa một cách mù quáng như thế nào?
Bạn ngăn algorithm downgrade hoặc key confusion khi message cho phép người gửi tự khai báo thuật toán và key identifier như thế nào?
Bạn phân biệt key rotation, key revocation và key destruction trong vòng đời khóa dùng cho MAC và chữ ký số như thế nào?
Bạn thiết kế audit trail cho hoạt động ký và xác minh để truy vết signer, key version, mục đích, thời điểm và kết quả mà không làm lộ private key như thế nào?
Bạn đánh giá cách lưu trữ public key và metadata xác minh để các hệ thống độc lập có thể kiểm tra chữ ký lâu dài như thế nào?
Bạn kiểm thử hash, MAC và chữ ký bằng known-answer test, test vector chuẩn và negative test ra sao?
Bạn xây dựng test để phát hiện việc thay đổi một byte của message, tag, digest hoặc signature mà verifier vẫn chấp nhận như thế nào?
Bạn kiểm thử khả năng chống replay, tag truncation, nonce reuse và key confusion trong một giao thức dùng MAC như thế nào?
Bạn kiểm thử chữ ký với message rỗng, message lớn, encoding lỗi, chữ ký bị cắt và tham số không hợp lệ như thế nào?
Bạn phân tích cách xử lý lỗi khác nhau giữa parse failure, key lookup failure và signature verification failure mà không tạo oracle hoặc rò rỉ dữ liệu như thế nào?
Bạn thiết kế interoperability test giữa nhiều thư viện hoặc nền tảng để bảo đảm cùng một chuẩn hash, MAC hoặc chữ ký cho kết quả tương thích như thế nào?
Bạn xây dựng quy trình ứng phó khi phát hiện MAC key hoặc private signing key bị lộ, bao gồm thu hồi, xoay khóa, đánh giá dữ liệu bị ảnh hưởng và thông báo như thế nào?
