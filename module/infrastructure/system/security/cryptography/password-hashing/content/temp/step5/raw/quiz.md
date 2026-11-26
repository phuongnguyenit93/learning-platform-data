1. Một hệ thống cần lưu mật khẩu để xác minh lần đăng nhập sau; lựa chọn nào phù hợp nhất?
A. Mã hóa mật khẩu bằng khóa đối xứng lưu trong secret store riêng.
B. Dùng Base64 để có thể khôi phục chuỗi gốc khi cần.
C. Dùng SHA-256 trực tiếp vì hàm băm đã không thể giải mã.
D. Dùng password hashing chuyên dụng một chiều với salt riêng.
Đáp án đúng: D

2. Vì sao SHA-256 trực tiếp không phù hợp để lưu password dù là hàm băm mật mã?
A. SHA-256 có output cố định nên không thể lưu salt cùng digest.
B. SHA-256 nhanh nên attacker thử nhiều mật khẩu ngoại tuyến.
C. SHA-256 không xử lý chuỗi Unicode có nhiều byte sau encoding.
D. SHA-256 cần giữ khóa bí mật cạnh mỗi bản ghi tài khoản.
Đáp án đúng: B

3. Mục đích chính của salt trong password hashing là gì?
A. Salt phải được giữ bí mật ngoài database để ngăn dò đoán ngoại tuyến.
B. Làm mỗi hash khác nhau và ngăn tái sử dụng bảng dò có sẵn.
C. Thay thế cost parameter để tăng số vòng tính toán mà không đổi hàm băm.
D. Salt đóng vai trò khóa để giải mã hash khi cần xác minh lại.
Đáp án đúng: B

4. Cách tạo salt nào phù hợp nhất cho mỗi mật khẩu mới?
A. Dùng user ID để tạo salt ổn định giữa các lần đổi mật khẩu.
B. Dùng một salt chung cho toàn bộ người dùng của hệ thống.
C. Sinh ngẫu nhiên bằng nguồn mật mã và lưu riêng cùng hash.
D. Dùng timestamp làm salt để không cần lưu giá trị.
Đáp án đúng: C

5. Nhận định nào mô tả đúng nhất sự khác nhau giữa salt và pepper?
A. Salt là khóa bí mật trong HSM; pepper được công khai trong hash.
B. Salt dùng để tăng CPU; pepper dùng để tăng RAM cho mỗi lần xác minh password.
C. Salt không cần bí mật và lưu cùng hash; pepper là secret lưu tách biệt.
D. Salt được dùng chung; pepper phải ngẫu nhiên mới cho mỗi tài khoản.
Đáp án đúng: C

6. Một tổ chức muốn dùng pepper để giảm tác động khi database bị dump; nên quản lý pepper thế nào?
A. Lưu pepper ngoài database trong secret manager hoặc HSM với quyền hạn chế.
B. Lưu pepper ở cùng bảng password hash để verifier dễ truy cập và xoay vòng cùng database.
C. Ghi pepper vào cấu hình client để không cần secret manager và dễ phân phối tới verifier.
D. Dùng pepper làm salt công khai rồi lưu giá trị đó cạnh từng hash.
Đáp án đúng: A

7. Argon2id thường được ưu tiên cho password hashing mới vì đặc điểm nào?
A. Kết hợp memory hardness với thiết kế cân bằng chống side-channel.
B. Chỉ dùng CPU và không cấp phát bộ nhớ trong quá trình xác minh.
C. Mã hóa mật khẩu bằng khóa công khai để hỗ trợ giải mã có kiểm soát.
D. Tạo hash cố định mà không cần salt hoặc cost parameter.
Đáp án đúng: A

8. Trong Argon2id, memory cost, time cost và parallelism điều khiển điều gì?
A. Độ dài mật khẩu, số salt, số lần so sánh hash và lượng dữ liệu lưu trong database.
B. Kích thước output, số user cùng đăng nhập và thời hạn phiên.
C. Số khóa pepper, số bản sao database và mức sử dụng mạng trong hệ thống.
D. Bộ nhớ sử dụng, số lượt xử lý và mức độ song song của phép băm.
Đáp án đúng: D

9. Một dịch vụ đặt memory cost Argon2id cao nhưng RAM giới hạn; điều gì cần cân nhắc trước khi triển khai?
A. Chỉ latency trung bình của một lần xác minh trên máy nhàn rỗi, không có request đồng thời.
B. Số lượng salt đang lưu vì mỗi salt chiếm RAM bằng memory cost.
C. Độ dài output hash vì output càng dài thì cần nhiều worker hơn.
D. Tổng RAM theo số phép xác minh đồng thời và ngân sách tải đỉnh.
Đáp án đúng: D

10. scrypt dùng những tham số nào để điều chỉnh chi phí và mức song song?
A. N, r và p điều khiển chi phí CPU, bộ nhớ và song song.
B. m, t và lanes điều khiển thời gian, bộ nhớ và số luồng.
C. cost và version quyết định số vòng bcrypt theo cấp số nhân.
D. iterations và PRF điều khiển số lần gọi hàm giả ngẫu nhiên.
Đáp án đúng: A

11. bcrypt điều chỉnh chi phí xử lý mật khẩu chủ yếu bằng cách nào?
A. Cost factor làm số vòng xử lý tăng theo cấp số nhân.
B. Memory cost cấp phát vùng RAM lớn cho từng phép xác minh.
C. Salt length quyết định số vòng lặp CPU được thực hiện.
D. Parallelism quyết định số lần gọi hàm băm độc lập.
Đáp án đúng: A

12. Một hệ thống chọn PBKDF2 vì yêu cầu tương thích hoặc tuân thủ; đặc điểm nào cần hiểu?
A. PBKDF2 yêu cầu bộ nhớ lớn để kháng GPU tương tự Argon2id.
B. PBKDF2 tự sinh pepper bí mật, gắn vào từng tài khoản và lưu trong kết quả hash.
C. PBKDF2 lặp PRF theo iteration count nhưng không memory-hard.
D. PBKDF2 chỉ hỗ trợ SHA-1 và không thể dùng PRF nào khác trong cấu hình.
Đáp án đúng: C

13. Khi so sánh Argon2id, bcrypt, scrypt và PBKDF2, tiêu chí lựa chọn nào hợp lý?
A. Chỉ chọn thuật toán có tên mới nhất mà không cần benchmark trên môi trường thực tế.
B. Chọn thuật toán tạo chuỗi hash ngắn nhất để giảm dung lượng database mà không xét tốc độ dò.
C. Chọn thuật toán chạy nhanh nhất để rút ngắn mọi lần đăng nhập.
D. Mức bảo vệ, chuẩn tuân thủ, thư viện tin cậy và ngân sách tài nguyên.
Đáp án đúng: D

14. Một bản ghi password hash cần hỗ trợ nâng cấp thuật toán trong tương lai; nên lưu những gì?
A. Plaintext, username, timestamp đăng ký và khóa mã hóa toàn cục.
B. Chỉ kết quả hash vì thuật toán có thể suy ra từ độ dài chuỗi.
C. Algorithm/version, cost parameters, salt và kết quả hash.
D. Salt và pepper plaintext để verifier không cần cấu hình thêm.
Đáp án đúng: C

15. Khi xác minh mật khẩu, quy trình nào phù hợp nhất?
A. Đọc metadata, tính hash ứng viên với salt/tham số lưu và so sánh.
B. Mã hóa mật khẩu nhập vào rồi so sánh ciphertext với hash lưu.
C. Băm mật khẩu nhập vào bằng SHA-256 rồi so với mọi thuật toán.
D. So sánh độ dài mật khẩu, salt và metadata trước khi chạy phép xác minh hash.
Đáp án đúng: A

16. Vì sao so sánh kết quả hash nên tránh dừng ngay tại byte đầu tiên khác nhau?
A. So sánh constant-time làm salt bí mật và ngăn attacker biết dữ liệu trong database.
B. Thời gian so sánh có thể tiết lộ thông tin qua timing side-channel.
C. So sánh constant-time khiến hash không thể bị dò ngoại tuyến.
D. So sánh constant-time tự động giới hạn số lần đăng nhập sai.
Đáp án đúng: B

17. Một login endpoint trả lỗi nhanh cho username không tồn tại nhưng chậm với mật khẩu sai; rủi ro nào xuất hiện?
A. Attacker có thể suy ra pepper từ chênh lệch thời gian giữa hai nhánh.
B. Attacker có thể dò sự tồn tại của tài khoản qua response timing.
C. Attacker có thể suy ra cost parameter chính xác từ một lần phản hồi.
D. Attacker có thể thay đổi password hash trong database qua request đăng nhập.
Đáp án đúng: B

18. Cách nào giúp giảm chênh lệch thời gian giữa tài khoản không tồn tại và mật khẩu sai?
A. Bỏ qua password hashing khi username không tồn tại.
B. Trả lỗi khác nhau nhưng thêm cùng một khoảng delay cố định ngắn.
C. Thực hiện dummy verification bằng hash có cost tương đương.
D. Tạo tài khoản giả trong database cho mọi username được thử.
Đáp án đúng: C

19. Argon2id dùng nhiều RAM cho mỗi phép xác minh; cách bảo vệ login endpoint trước flood nào phù hợp?
A. Tăng memory cost vô hạn để request từ attacker luôn chậm dù RAM không giới hạn.
B. Cho phép hàng đợi không giới hạn để không từ chối request hợp lệ.
C. Giới hạn concurrency và queue, kết hợp rate limit theo nhiều tín hiệu.
D. Chuyển mọi phép xác minh sang request thread mà không giới hạn.
Đáp án đúng: C

20. Benchmark password hashing trước production nên đo những yếu tố nào?
A. Đo riêng thời gian hash của một request trên máy không có tải nền.
B. CPU, RAM, concurrency và p95/p99 latency dưới tải đại diện.
C. Dung lượng ổ đĩa của file log và số bản ghi người dùng.
D. Dựa vào iteration count công bố mà không đo trên hệ thống.
Đáp án đúng: B

21. Một hash cũ dùng cost thấp nhưng người dùng vừa nhập đúng mật khẩu; cách nâng cấp thường phù hợp là gì?
A. Xác minh hash cũ rồi rehash mật khẩu vừa nhập với tham số mới.
B. Tạo hash mới từ hash cũ mà không cần biết mật khẩu người dùng.
C. Đổi salt trong database và giữ nguyên output hash hiện tại.
D. Yêu cầu reset tất cả tài khoản ngay cả khi chưa có rủi ro.
Đáp án đúng: A

22. Vì sao không thể rehash toàn bộ mật khẩu cũ sang thuật toán mới chỉ từ các hash hiện có?
A. Hash cũ không chứa username nên không thể xác định bản ghi tài khoản cần đổi.
B. Salt cũ không thể được đọc sau khi lưu vào database.
C. Hash một chiều không cung cấp plaintext cần thiết để tạo hash mới.
D. Thuật toán mới luôn yêu cầu cùng một salt cho mọi tài khoản.
Đáp án đúng: C

23. Khi chuyển từ MD5 hoặc SHA-1 trực tiếp sang Argon2id, chiến lược migration nào phù hợp?
A. Băm lại chuỗi hash cũ bằng Argon2id và coi đó là mật khẩu mới.
B. Đổi thuật toán identifier trong metadata mà không tính lại hash.
C. Giữ legacy hash cho mọi tài khoản để tránh thay đổi luồng login.
D. Xác minh legacy hash khi đăng nhập thành công rồi lưu hash mới.
Đáp án đúng: D

24. Làm thế nào tránh migration vô tình hạ cấp hash của tài khoản đã nâng cấp?
A. Dùng metadata version và policy chỉ cho phép nâng cấp cost/algorithm.
B. Chọn thuật toán theo giá trị do client gửi trong login request và tin metadata đó.
C. Ghi hash theo thuật toán cũ nếu xác minh thành công nhanh hơn.
D. Dùng một định dạng hash duy nhất và bỏ thông tin phiên bản.
Đáp án đúng: A

25. bcrypt có giới hạn đầu vào phổ biến 72 byte trong nhiều triển khai; điều gì cần chú ý?
A. Giới hạn 72 ký tự Unicode áp dụng giống nhau cho mọi thư viện.
B. bcrypt tự băm phần dư bằng SHA-256 trước khi xử lý cost factor.
C. Mọi mật khẩu dài hơn 72 byte đều bị thư viện từ chối theo chuẩn.
D. Một số triển khai cắt phần vượt giới hạn nên cần kiểm soát nhất quán.
Đáp án đúng: D

26. Một mật khẩu Unicode có nhiều byte UTF-8; giới hạn bcrypt nên được đánh giá theo đơn vị nào?
A. Số grapheme người dùng nhìn thấy trên màn hình nhập mật khẩu.
B. Số code point sau khi browser hiển thị chuỗi.
C. Số byte đầu vào sau encoding mà thư viện thực sự xử lý.
D. Số ký tự ASCII sau khi loại bỏ toàn bộ ký tự ngoài bảng.
Đáp án đúng: C

27. Hai dịch vụ xác minh cùng mật khẩu nhưng cho kết quả khác nhau sau migration; điều gì cần kiểm tra?
A. Chỉ kiểm tra username vì password hash không phụ thuộc đầu vào.
B. Độ dài salt trong database vì mọi thuật toán dùng salt cùng kích thước.
C. Encoding, normalization, pepper version và hành vi thư viện.
D. Thứ tự cột database vì verifier đọc hash theo vị trí lưu trữ.
Đáp án đúng: C

28. Ứng dụng muốn hỗ trợ Unicode password; nguyên tắc nào giúp xác minh nhất quán?
A. Tự động trim mọi khoảng trắng và đổi chữ hoa thành chữ thường để tránh nhập sai.
B. Quy định rõ encoding/normalization và áp dụng nhất quán khi tạo lẫn xác minh.
C. Chuyển mọi ký tự sang chữ thường trước khi tính hash ở mọi dịch vụ.
D. Loại bỏ ký tự ngoài ASCII để mọi thư viện cho cùng kết quả.
Đáp án đúng: B

29. Một tổ chức muốn xoay pepper nhưng không có plaintext của toàn bộ người dùng; cách tiếp cận nào phù hợp?
A. Duy trì version pepper để xác minh rồi rehash khi có mật khẩu đúng; reset khi cần.
B. Tính pepper mới từ hash cũ để đổi toàn bộ bản ghi ngay lập tức mà không cần plaintext hay reset.
C. Thay salt bằng pepper mới trong database mà giữ nguyên hash hiện tại.
D. Bỏ pepper khỏi verifier trước rồi coi hash cũ là hash mới trong database.
Đáp án đúng: A

30. Sau khi pepper bị lộ cùng database hash, đánh giá nào đúng nhất?
A. Thay salt trong database vì pepper cũ không ảnh hưởng hash đã lưu.
B. Xem xét phạm vi dò đoán ngoại tuyến và yêu cầu rotation/reset theo rủi ro.
C. Không phát sinh phản ứng nếu pepper không được ghi trong bảng người dùng.
D. Revoke session hiện tại là đủ vì password hash không thể bị tấn công.
Đáp án đúng: B

31. Vì sao salt không đủ bảo vệ mật khẩu yếu khi database hash bị đánh cắp?
A. Salt làm cho mọi password hash không thể được tính lại ngoại tuyến nếu attacker chỉ có database.
B. Attacker vẫn có thể thử từng mật khẩu đoán được với salt công khai.
C. Salt tự giới hạn số lần thử dựa trên địa chỉ IP của người dùng ở server.
D. Salt biến password hashing thành dạng mã hóa cần khóa bí mật để giải mã.
Đáp án đúng: B

32. Password blocklist bổ sung lớp bảo vệ nào bên cạnh password hashing?
A. Thay thế salt riêng vì mật khẩu phổ biến đã được loại bỏ.
B. Làm cho hash chậm hơn mà không cần điều chỉnh cost parameters.
C. Cho phép khôi phục mật khẩu khi người dùng quên.
D. Ngăn chọn mật khẩu phổ biến hoặc đã xuất hiện trong dữ liệu rò rỉ.
Đáp án đúng: D

33. Một bản dump database chứa password hash được sao chép vào backup và file export; kiểm soát nào phù hợp?
A. Đưa hash vào log để nhóm vận hành phát hiện bản sao bị thiếu.
B. Coi hash không nhạy cảm vì không thể giải mã như ciphertext.
C. Chia sẻ file export rộng rãi vì salt đã ngăn mọi dạng dò đoán.
D. Giới hạn quyền truy cập, mã hóa bản sao và kiểm soát vòng đời lưu trữ.
Đáp án đúng: D

34. Một dịch vụ cần hỗ trợ reset password; nên lưu reset token như thế nào?
A. Sinh token ngẫu nhiên, lưu bản hash và giới hạn thời hạn cùng trạng thái dùng một lần.
B. Lưu plaintext token lâu dài để gửi lại khi người dùng yêu cầu.
C. Dùng password hash hiện tại làm reset token để không tạo bí mật mới.
D. Mã hóa token bằng salt của password rồi cho phép dùng nhiều lần.
Đáp án đúng: A

35. Đội vận hành muốn điều tra login performance mà không làm lộ credential; dữ liệu nào phù hợp?
A. Plaintext password cùng hash để tái hiện chính xác lần đăng nhập.
B. Pepper, salt và toàn bộ hash string cho mọi request bị lỗi.
C. Password reset token và request body để hỗ trợ debug nhanh.
D. Latency theo giai đoạn, thuật toán/cost version và mã sự kiện không chứa bí mật.
Đáp án đúng: D

36. Cost factor bcrypt tăng thêm một đơn vị thường ảnh hưởng chi phí xác minh như thế nào?
A. Số vòng xử lý giảm một nửa để bù độ trễ.
B. Số vòng xử lý xấp xỉ tăng gấp đôi theo cost.
C. Bộ nhớ sử dụng tăng gấp đôi nhưng CPU giữ nguyên.
D. Kích thước salt tăng gấp đôi nhưng số vòng giữ nguyên.
Đáp án đúng: B
