Bạn sẽ giải thích vì sao mật khẩu cần được password hashing thay vì lưu plaintext hoặc mã hóa có thể giải mã như thế nào?
Bạn sẽ phân biệt password hashing, encryption và message authentication code theo mục tiêu bảo mật và khả năng khôi phục dữ liệu ra sao?
Bạn sẽ mô tả cách kẻ tấn công dùng bản dump cơ sở dữ liệu để dò mật khẩu ngoại tuyến và vì sao hash chậm làm tăng chi phí tấn công như thế nào?
Bạn sẽ giải thích vì sao SHA-256 hoặc MD5 dùng trực tiếp không phù hợp để lưu mật khẩu dù chúng là hàm băm mật mã như thế nào?
Bạn sẽ xác định các đặc tính cần có của password hashing function như one-way, salt support và khả năng điều chỉnh chi phí ra sao?
Bạn sẽ lựa chọn password hashing algorithm dựa trên mức độ chống GPU/ASIC, khả năng triển khai và yêu cầu vận hành như thế nào?
Bạn sẽ so sánh Argon2id, bcrypt, scrypt và PBKDF2 về thiết kế, khả năng chống dò đoán và chi phí tài nguyên ra sao?
Bạn sẽ giải thích Argon2id kết hợp các cơ chế của Argon2i và Argon2d để cân bằng side-channel resistance với memory hardness như thế nào?
Bạn sẽ lựa chọn giữa Argon2id, Argon2i và Argon2d theo mô hình đe dọa và khuyến nghị triển khai nào?
Bạn sẽ giải thích memory cost, time cost và parallelism của Argon2 ảnh hưởng đến bảo mật và hiệu năng xác minh như thế nào?
Bạn sẽ xác định cách chọn memory cost cho Argon2id khi server có giới hạn RAM và phải xử lý nhiều đăng nhập đồng thời ra sao?
Bạn sẽ hiệu chỉnh time cost và parallelism để tăng chi phí dò mật khẩu nhưng không làm endpoint đăng nhập dễ bị DoS như thế nào?
Bạn sẽ phân biệt Argon2 memory cost với số vòng lặp CPU và giải thích vì sao memory hardness làm tăng chi phí GPU cracking ra sao?
Bạn sẽ so sánh scrypt với Argon2id về memory usage, parallelization và khả năng chống phần cứng chuyên dụng như thế nào?
Bạn sẽ giải thích tham số N, r và p của scrypt ảnh hưởng đến bộ nhớ, CPU và mức độ song song ra sao?
Bạn sẽ lựa chọn tham số scrypt theo ngân sách tài nguyên của dịch vụ và tốc độ xác minh mục tiêu như thế nào?
Bạn sẽ mô tả bcrypt dùng cost factor để điều chỉnh số vòng xử lý và chi phí tăng theo cấp số nhân như thế nào?
Bạn sẽ đánh giá giới hạn độ dài đầu vào phổ biến của bcrypt và nguy cơ các thư viện xử lý khác nhau với mật khẩu vượt giới hạn ra sao?
Bạn sẽ xử lý mật khẩu dài hơn giới hạn đầu vào của một triển khai bcrypt mà không âm thầm cắt cụt hoặc tạo tương thích sai như thế nào?
Bạn sẽ giải thích PBKDF2 sử dụng pseudorandom function lặp nhiều vòng và lựa chọn hash PRF phù hợp ra sao?
Bạn sẽ so sánh PBKDF2 với các thuật toán memory-hard khi attacker dùng GPU hoặc ASIC để dò mật khẩu như thế nào?
Bạn sẽ xác định khi nào PBKDF2 phù hợp do yêu cầu tương thích hoặc tiêu chuẩn tuân thủ và những biện pháp bù đắp cần thiết ra sao?
Bạn sẽ đánh giá tác động của số iteration PBKDF2 đến latency đăng nhập và khả năng xử lý tải đồng thời như thế nào?
Bạn sẽ giải thích salt là giá trị ngẫu nhiên riêng cho từng mật khẩu và vì sao salt không cần giữ bí mật như thế nào?
Bạn sẽ xác định độ dài salt và nguồn sinh số ngẫu nhiên mật mã cần dùng khi tạo password hash ra sao?
Bạn sẽ phân tích vì sao salt riêng ngăn rainbow table và làm cho cùng một mật khẩu tạo ra các hash khác nhau như thế nào?
Bạn sẽ giải thích vì sao dùng chung salt cho nhiều tài khoản làm giảm khả năng chống dò mật khẩu ngoại tuyến ra sao?
Bạn sẽ phân biệt salt với pepper về vai trò, cách lưu trữ và cách quản lý vòng đời như thế nào?
Bạn sẽ thiết kế pepper được lưu ngoài database trong secret manager hoặc HSM để giảm tác động khi database bị dump ra sao?
Bạn sẽ lựa chọn cách kết hợp pepper với password hashing function và bảo đảm xác minh vẫn nhất quán giữa các phiên bản như thế nào?
Bạn sẽ xử lý pepper rotation khi không thể tính lại hash của toàn bộ người dùng nếu không có mật khẩu gốc ra sao?
Bạn sẽ đánh giá tác động khi pepper bị lộ cùng database và xác định phạm vi reset mật khẩu cần thiết như thế nào?
Bạn sẽ thiết kế định dạng lưu hash có algorithm identifier, version, salt và cost parameters để hỗ trợ nâng cấp về sau ra sao?
Bạn sẽ xác định cách lưu trữ hash để ứng dụng có thể biết thuật toán và tham số nào cần dùng khi xác minh mật khẩu như thế nào?
Bạn sẽ lựa chọn cách encode password hash và tham số sao cho không bị mất thông tin khi chuyển database hoặc ngôn ngữ triển khai ra sao?
Bạn sẽ mô tả quy trình xác minh mật khẩu bằng cách đọc algorithm metadata, tính lại hash và so sánh kết quả như thế nào?
Bạn sẽ giải thích vì sao phép so sánh hash nên có hành vi constant-time và những giới hạn của constant-time ở tầng ứng dụng ra sao?
Bạn sẽ ngăn account enumeration qua khác biệt thời gian xác minh giữa tài khoản không tồn tại và mật khẩu sai như thế nào?
Bạn sẽ lựa chọn dummy hash để giảm chênh lệch thời gian cho username không tồn tại mà không làm tăng nguy cơ DoS ra sao?
Bạn sẽ bảo vệ password verification endpoint bằng rate limiting, concurrency limit và kiểm soát chi phí hashing như thế nào?
Bạn sẽ xác định rủi ro memory exhaustion khi nhiều request Argon2id chạy đồng thời với memory cost cao ra sao?
Bạn sẽ thiết kế hàng đợi hoặc semaphore để giới hạn số password hash operation đồng thời mà vẫn giữ trải nghiệm đăng nhập như thế nào?
Bạn sẽ phân biệt rate limiting theo IP, tài khoản và thiết bị khi bảo vệ endpoint đăng nhập trước brute force ra sao?
Bạn sẽ lựa chọn tham số password hashing dựa trên benchmark thực tế của môi trường production thay vì chỉ dùng giá trị mặc định như thế nào?
Bạn sẽ xây dựng benchmark có tính đến CPU, RAM, concurrency, p95/p99 latency và tải nền để chọn cost parameters ra sao?
Bạn sẽ đánh giá khi nào cần tăng cost parameters theo thời gian và cách lập lịch rà soát định kỳ như thế nào?
Bạn sẽ giải thích vì sao cost parameters cần được lưu cùng hash để mỗi tài khoản có thể được nâng cấp dần ra sao?
Bạn sẽ thiết kế rehash-on-login khi người dùng nhập đúng mật khẩu nhưng hash đang dùng thuật toán hoặc tham số cũ như thế nào?
Bạn sẽ sử dụng needsRehash hoặc cơ chế tương đương để xác định hash nào cần nâng cấp mà không yêu cầu reset hàng loạt ra sao?
Bạn sẽ xử lý migration từ MD5, SHA-1 hoặc hash nhanh cũ sang Argon2id khi người dùng đăng nhập như thế nào?
Bạn sẽ lựa chọn giữa rehash-on-login, bắt buộc reset mật khẩu và migration theo lô khi nâng cấp hệ thống hash ra sao?
Bạn sẽ quản lý nhiều định dạng hash cùng lúc trong giai đoạn chuyển đổi mà vẫn tránh hạ cấp thuật toán mới như thế nào?
Bạn sẽ ngăn downgrade attack khiến ứng dụng tiếp tục xác minh hoặc ghi mật khẩu bằng thuật toán yếu hơn sau migration ra sao?
Bạn sẽ xử lý trường hợp thư viện password hashing được nâng cấp làm thay đổi encoding hoặc hành vi xác minh hash cũ như thế nào?
Bạn sẽ xác định cách bảo toàn khả năng đăng nhập khi thay đổi phiên bản thuật toán hoặc chuyển hash giữa nhiều dịch vụ như thế nào?
Bạn sẽ thiết kế password reset sau khi phát hiện database hash bị rò rỉ và xác định nhóm tài khoản cần ưu tiên xử lý ra sao?
Bạn sẽ giải thích vì sao salt không bảo vệ được mật khẩu yếu khi attacker đã có hash database và có thể thử đoán ngoại tuyến như thế nào?
Bạn sẽ kết hợp password hashing với password blocklist để ngăn người dùng đặt mật khẩu phổ biến hoặc đã bị lộ ra sao?
Bạn sẽ thiết kế chính sách mật khẩu dựa trên độ dài, mật khẩu bị lộ và khả năng dùng password manager thay vì quy tắc ký tự cứng như thế nào?
Bạn sẽ xử lý Unicode normalization và encoding để cùng một mật khẩu được xác minh nhất quán giữa các nền tảng ra sao?
Bạn sẽ xác định cách xử lý khoảng trắng đầu/cuối, ký tự null và chuỗi đa byte mà không âm thầm thay đổi mật khẩu như thế nào?
Bạn sẽ phân tích rủi ro bcrypt 72-byte truncation khi người dùng dùng passphrase dài hoặc ký tự UTF-8 nhiều byte ra sao?
Bạn sẽ lựa chọn cách xử lý peppered pre-hash hoặc post-hash khi cần tương thích mật khẩu dài và tránh các lỗi thiết kế phổ biến như thế nào?
Bạn sẽ bảo vệ password hash trong database backup, replica, export và log để hạn chế thêm các bản sao có thể bị dò ngoại tuyến ra sao?
Bạn sẽ phân biệt hash password với password reset token và lựa chọn cách lưu reset token an toàn như thế nào?
Bạn sẽ quản lý quyền truy cập database để chỉ thành phần xác thực cần thiết mới có thể đọc password hash ra sao?
Bạn sẽ ngăn password hoặc hash xuất hiện trong application log, tracing, error report và telemetry như thế nào?
Bạn sẽ thiết kế audit event cho password change, reset, hash upgrade và credential compromise mà không ghi lại bí mật ra sao?
Bạn sẽ kiểm thử password hashing bằng known test vectors, test tương thích, test cost parameters và kiểm tra xử lý lỗi như thế nào?
Bạn sẽ xây dựng kiểm thử xác minh rằng mỗi mật khẩu mới nhận salt ngẫu nhiên riêng và hash không trùng nhau như thế nào?
Bạn sẽ kiểm tra constant-time comparison và chênh lệch response timing giữa tài khoản tồn tại với tài khoản không tồn tại ra sao?
Bạn sẽ thực hiện load test cho đăng nhập để xác định cost parameters có gây cạn CPU hoặc RAM khi tải tăng đột biến hay không như thế nào?
Bạn sẽ đánh giá tính tương thích của password hash khi nhiều ứng dụng hoặc vùng triển khai dùng phiên bản thư viện khác nhau ra sao?
Bạn sẽ thiết kế quy trình ứng phó khi pepper hoặc password hash database bị lộ gồm rotation, reset, session revoke và monitoring như thế nào?
Nếu database password hash bị đánh cắp và attacker bắt đầu dò ngoại tuyến, bạn sẽ đánh giá rủi ro theo thuật toán, cost, salt và chất lượng mật khẩu ra sao?
Nếu tăng memory cost của Argon2id khiến login latency tăng mạnh và worker cạn RAM, bạn sẽ điều chỉnh tham số và concurrency như thế nào?
Nếu người dùng cũ không thể đăng nhập sau khi chuyển từ bcrypt sang Argon2id, bạn sẽ điều tra encoding, giới hạn độ dài và migration metadata ra sao?
Nếu hai hệ thống xác minh cùng một mật khẩu cho kết quả khác nhau, bạn sẽ kiểm tra normalization, character encoding, pepper version và thư viện như thế nào?
Nếu pepper bị lộ nhưng password hash chưa bị đánh cắp, bạn sẽ đánh giá phạm vi phản ứng và kế hoạch rotation dựa trên kiến trúc lưu trữ nào?
Nếu một số tài khoản vẫn dùng SHA-256 trực tiếp sau nhiều năm, bạn sẽ lập chiến lược nâng cấp không làm mất khả năng đăng nhập như thế nào?
Bạn sẽ thiết kế vòng đời password hashing đầu cuối từ lựa chọn thuật toán, tạo salt, lưu hash, xác minh, rehash, reset đến ứng phó rò rỉ như thế nào?
