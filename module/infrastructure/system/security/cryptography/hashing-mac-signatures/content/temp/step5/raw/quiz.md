1. Thuộc tính nào mô tả khả năng chống tìm hai thông điệp bất kỳ có cùng digest?
A. Kháng tiền ảnh thứ hai khi đã biết thông điệp gốc.
B. Kháng tiền ảnh khi chỉ có digest của thông điệp gốc.
C. Kháng va chạm khi attacker tự chọn cả hai thông điệp.
D. Kháng giả mạo khi digest được truyền công khai.
Đáp án đúng: C

2. Với hàm băm có digest n bit, chi phí tìm va chạm tổng quát theo birthday bound xấp xỉ bao nhiêu?
A. Khoảng 2^n phép thử để tìm một va chạm bất kỳ.
B. Khoảng 2^(n/2) phép thử để tìm một va chạm bất kỳ.
C. Khoảng 2^(n/2) phép thử để khôi phục thông điệp gốc.
D. Khoảng 2^n phép thử để tìm tiền ảnh thứ hai.
Đáp án đúng: B

3. Vì sao digest SHA-256 công khai không chứng minh file do nhà phát hành tạo?
A. Digest cố định độ dài nên không thể dùng kiểm tra file.
B. SHA-256 chỉ hoạt động với dữ liệu được mã hóa trước.
C. Attacker có thể thay file và tự tính digest tương ứng.
D. Digest chỉ có thể được xác minh bằng private key của signer.
Đáp án đúng: C

4. Khác biệt quan trọng giữa CRC và cryptographic hash là gì?
A. CRC có khóa bí mật còn hash luôn dùng khóa công khai.
B. CRC chống va chạm tốt hơn hash khi dữ liệu bị sửa có chủ đích.
C. Hash bảo đảm nguồn gốc người gửi còn CRC bảo đảm bí mật.
D. CRC phát hiện lỗi ngẫu nhiên; hash mật mã có tính kháng va chạm.
Đáp án đúng: D

5. Vì sao không nên dùng MD5 hoặc SHA-1 cho chữ ký artifact mới?
A. Hai thuật toán không hỗ trợ đầu vào có độ dài thay đổi.
B. Va chạm thực tế làm suy yếu bảo đảm kháng va chạm.
C. Digest của chúng không thể được lưu trong manifest.
D. Chúng yêu cầu khóa bí mật cho mỗi lần tính digest.
Đáp án đúng: B

6. Cấu trúc H(secret || message) với hash kiểu Merkle–Damgård có thể gặp lỗi nào?
A. Có thể lộ secret chỉ bằng cách quan sát digest ban đầu.
B. Có thể bị length extension để mở rộng message với digest hợp lệ.
C. Có thể bị đảo ngược trực tiếp thành message và secret ban đầu.
D. Có thể bị replay dù message luôn được mã hóa bằng khóa công khai.
Đáp án đúng: B

7. SHAKE khác SHA3-256 ở đặc điểm nào?
A. SHAKE dùng khóa bí mật còn SHA3-256 không dùng khóa.
B. SHAKE chỉ tạo digest 256 bit còn SHA3-256 có độ dài tùy ý.
C. SHAKE dùng block cipher còn SHA3-256 dùng stream cipher.
D. SHAKE là XOF cho phép ứng dụng chọn độ dài đầu ra tùy ý.
Đáp án đúng: D

8. Đặc điểm kiến trúc nào phân biệt SHA-3 với SHA-2?
A. SHA-3 dùng sponge; SHA-2 dùng cấu trúc Merkle–Damgård.
B. SHA-3 là MAC có khóa, còn SHA-2 là hash không khóa.
C. SHA-3 chỉ xử lý block cố định, còn SHA-2 xử lý luồng tùy ý.
D. SHA-3 dùng RSA để nén dữ liệu, còn SHA-2 dùng AES.
Đáp án đúng: A

9. Hai hệ thống băm cùng một JSON nhưng cho digest khác nhau do thứ tự key và khoảng trắng. Cần làm gì?
A. Mã hóa JSON bằng AES trước khi gọi hàm băm.
B. Dùng canonical serialization trước khi băm.
C. Thêm salt ngẫu nhiên giống nhau vào cuối mỗi trường.
D. Tăng độ dài digest để bỏ qua khác biệt biểu diễn.
Đáp án đúng: B

10. Domain separation trong thiết kế hash hoặc MAC nhằm mục đích gì?
A. Dùng cùng kết quả mật mã an toàn cho mọi giao thức.
B. Tách kết quả mật mã theo từng ngữ cảnh sử dụng.
C. Giảm độ dài khóa khi một key dùng nhiều ứng dụng.
D. Thay salt bằng timestamp để tránh lưu trạng thái.
Đáp án đúng: B

11. HMAC tạo tag xác thực thông điệp bằng cách nào?
A. HMAC kết hợp hash với khóa qua inner/outer padding.
B. Mã hóa message bằng public key rồi băm ciphertext.
C. Băm message hai lần bằng hai salt công khai khác nhau.
D. Ký digest bằng private key rồi gửi public key kèm theo.
Đáp án đúng: A

12. Vì sao nên so sánh MAC tag bằng constant-time comparison?
A. Để tag có thể được xác minh mà không cần khóa bí mật.
B. Để tự động chống replay khi tag đã được xác minh.
C. Để thời gian phản hồi không tiết lộ prefix khớp của tag.
D. Để cho phép tag ngắn hơn mà không tăng xác suất giả mạo.
Đáp án đúng: C

13. Vì sao HMAC không cung cấp non-repudiation giữa hai bên dùng chung secret?
A. Mọi bên giữ cùng shared key đều có thể tự tạo tag hợp lệ.
B. HMAC luôn dùng khóa khác nhau cho người gửi và người nhận.
C. HMAC không thể xác minh nếu message được truyền qua mạng.
D. HMAC chỉ tạo digest công khai nên không có xác thực nguồn.
Đáp án đúng: A

14. Nếu MAC tag bị cắt còn t bit, xác suất đoán đúng một tag trong một lần thử là bao nhiêu?
A. Xấp xỉ 2^-n với n là độ dài thông điệp đầu vào.
B. Xấp xỉ 2^-k với k là số bit của khóa bí mật.
C. Xấp xỉ 2^t vì tag ngắn làm tăng entropy.
D. Xấp xỉ 2^-t với t là độ dài tag còn lại.
Đáp án đúng: D

15. Một webhook có HMAC hợp lệ bị phát lại để lặp giao dịch. Cần bổ sung kiểm soát nào?
A. Dùng timestamp hoặc nonce duy nhất, từ chối request đã dùng.
B. Tăng kích thước digest để mỗi lần gửi tạo tag khác.
C. Đổi HMAC thành hash công khai để receiver tự tính lại.
D. Chỉ kiểm tra địa chỉ IP vì tag đã bảo vệ nội dung.
Đáp án đúng: A

16. CMAC khác HMAC ở điểm chính nào?
A. CMAC dùng hash SHA-3, còn HMAC dùng RSA.
B. CMAC cần public/private key, còn HMAC dùng khóa chung.
C. CMAC xây dựng MAC dựa trên block cipher như AES.
D. CMAC chỉ xác minh chữ ký file, không xác thực message.
Đáp án đúng: C

17. Vì sao Poly1305 yêu cầu one-time key không được tái sử dụng?
A. Tái sử dụng làm digest của hai message luôn giống nhau.
B. Tái sử dụng khiến tag trở thành chữ ký có thể bị thu hồi.
C. One-time key phải được gửi công khai cùng message.
D. Có thể lộ thông tin giúp attacker giả mạo tag.
Đáp án đúng: D

18. HKDF có hai giai đoạn extract và expand để làm gì?
A. Nén message trước khi ký bằng khóa bất đối xứng.
B. Thay certificate chain bằng một digest công khai.
C. Dẫn xuất khóa riêng từ input keying material và context xác định.
D. Tạo nonce ngẫu nhiên có thể dùng lại cho mọi giao thức.
Đáp án đúng: C

19. Keyed mode của BLAKE2 hoặc BLAKE3 phù hợp với mục đích nào?
A. Thay thế certificate để xác thực danh tính người ký độc lập.
B. Cung cấp non-repudiation vì verifier không cần giữ secret.
C. Mã hóa nội dung message để che dữ liệu khỏi người nhận.
D. Tạo tag xác thực bằng hash có khóa theo mode chuẩn.
Đáp án đúng: D

20. Khác biệt nào đúng giữa MAC và authenticated encryption như AES-GCM?
A. MAC luôn cung cấp bí mật còn AEAD chỉ kiểm tra nguồn gửi.
B. AEAD không cần nonce còn MAC luôn yêu cầu nonce duy nhất.
C. MAC bảo vệ toàn vẹn và xác thực; AEAD còn mã hóa dữ liệu.
D. MAC dùng public key còn AEAD dùng cặp private/public key.
Đáp án đúng: C

21. Khác biệt cốt lõi giữa MAC và chữ ký số là gì?
A. MAC dùng shared key; chữ ký dùng private/public key.
B. MAC bảo vệ bí mật; chữ ký số chỉ phát hiện lỗi truyền tải.
C. MAC cho phép xác minh độc lập; chữ ký yêu cầu shared secret.
D. MAC không cần khóa; chữ ký dùng một khóa đối xứng duy nhất.
Đáp án đúng: A

22. Vì sao RSA-PSS thường được ưu tiên hơn PKCS#1 v1.5 signature cho hệ thống mới?
A. RSA-PSS dùng khóa ngắn hơn và không cần xác minh padding.
B. RSA-PSS dùng salt ngẫu nhiên trong padding chữ ký.
C. RSA-PSS mã hóa message nên không cần hash trước khi ký.
D. RSA-PSS loại bỏ nhu cầu bảo vệ private signing key.
Đáp án đúng: B

23. Điều gì có thể xảy ra nếu ECDSA tái sử dụng nonce khi ký hai message khác nhau?
A. Attacker có thể suy ra private key nếu hai chữ ký dùng cùng nonce.
B. Public key tự thay đổi sau mỗi lần xác minh chữ ký.
C. Chữ ký trở thành MAC và chỉ verifier có secret mới đọc được.
D. Digest bị kéo dài để chứa nonce của cả hai message.
Đáp án đúng: A

24. RFC 6979 giúp ECDSA giảm rủi ro nào?
A. Dùng chung một public key cho nhiều certificate khác nhau.
B. Tái sử dụng cùng nonce cho mọi chữ ký để tăng tốc.
C. Làm lộ nonce qua metadata để verifier kiểm tra độc lập.
D. Sinh nonce xác định từ private key và message hash.
Đáp án đúng: D

25. Đặc điểm nào đúng về Ed25519?
A. Là MAC dựa trên AES với tag cố định 128 bit.
B. Là cơ chế mã hóa bất đối xứng dùng public key để giải mã.
C. Là biến thể RSA dùng padding xác suất cho chữ ký.
D. Ed25519 là thuật toán chữ ký số thuộc họ EdDSA.
Đáp án đúng: D

26. Chữ ký số hợp lệ nhưng public key lấy từ nguồn không tin cậy. Verifier còn thiếu điều gì?
A. Cần băm lại public key bằng cùng hash của message.
B. Cần mã hóa message bằng private key của verifier.
C. Cần xác minh binding giữa public key và signer.
D. Cần thay chữ ký bằng HMAC dùng chung giữa mọi verifier.
Đáp án đúng: C

27. Vì sao RSA signature không thể xem như RSA encryption đảo chiều?
A. Ký và mã hóa dùng mục tiêu, padding và quy trình khác nhau.
B. RSA signature chỉ dùng khóa đối xứng còn encryption dùng public key.
C. RSA encryption tạo digest còn signature tạo ciphertext có thể giải mã.
D. Chữ ký RSA không dùng phép toán modular exponentiation.
Đáp án đúng: B

28. ECDSA signature có thể được biểu diễn theo dạng nào tùy giao thức?
A. Một digest SHA-256 duy nhất không chứa thành phần chữ ký.
B. Một certificate DER chứa cả private key của signer.
C. Cặp r,s có thể ở dạng fixed-width hoặc ASN.1 DER.
D. Một nonce công khai và một MAC tag dùng khóa chung.
Đáp án đúng: C

29. Khi xác minh certificate gắn với public signing key, verifier cần kiểm tra gì?
A. Chain tin cậy, thời hạn hiệu lực, key usage và trạng thái thu hồi.
B. Chỉ subject name vì tên chứng thư luôn duy nhất toàn cầu.
C. Chỉ chữ ký của message vì certificate không ảnh hưởng trust.
D. Chỉ thời hạn certificate, không cần xác minh issuer.
Đáp án đúng: A

30. Chữ ký số trên message cung cấp bảo đảm nào?
A. Xác minh tính toàn vẹn và liên hệ với private key tương ứng.
B. Tự động ngăn message cũ được phát lại trong giao thức.
C. Xác minh chữ ký cũng chứng minh certificate chưa bị thu hồi.
D. Tự động giữ bí mật nội dung khỏi mọi bên không có private key.
Đáp án đúng: A

31. Vì sao non-repudiation của chữ ký số vẫn phụ thuộc quy trình vận hành?
A. Vì public key có thể tạo chữ ký thay private key khi cần.
B. Vì digest có độ dài cố định nên không thể kiểm toán.
C. Vì chữ ký số không thể xác minh sau khi certificate hết hạn.
D. Vì cần kiểm soát ai giữ private key, cách dùng và nguy cơ bị lộ.
Đáp án đúng: D

32. Cách xoay vòng signing key nào hỗ trợ xác minh artifact cũ trong giai đoạn chuyển tiếp?
A. Ngừng ký bằng key cũ, giữ public key cũ để verify.
B. Xóa key cũ khỏi mọi trust store ngay khi tạo key mới.
C. Dùng private key mới để xác minh chữ ký tạo bằng key cũ.
D. Cho verifier thử mọi key không phân biệt issuer hoặc mục đích.
Đáp án đúng: A

33. Lợi ích bảo mật chính của việc giữ private signing key không thể export trong HSM là gì?
A. HSM tự động xác minh danh tính người nhận mọi artifact đã ký.
B. HSM loại bỏ nhu cầu phân quyền và audit cho signing service.
C. HSM khiến public key không cần phân phối cho verifier.
D. Giảm khả năng sao chép private key và giới hạn quyền ký.
Đáp án đúng: D

34. Một envelope cho phép người gửi khai báo thuật toán và key ID. Verifier nên làm gì?
A. Chấp nhận mọi thuật toán được ghi trong envelope nếu parse được.
B. Ràng buộc thuật toán và key với issuer cùng mục đích.
C. Dùng key đầu tiên tìm được trong trust store để xác minh.
D. Thử lần lượt mọi thuật toán cho tới khi một chữ ký hợp lệ.
Đáp án đúng: B

35. Kiểm thử nào giúp phát hiện triển khai hash/MAC/signature sai so với chuẩn?
A. Chỉ đo throughput với message ngẫu nhiên có kích thước lớn.
B. Chỉ xác minh một message hợp lệ do chính thư viện tạo ra.
C. Chạy known-answer test, test vector chuẩn và negative test.
D. Chỉ so sánh tên thuật toán trong cấu hình giữa các hệ thống.
Đáp án đúng: C

36. Phát hiện private signing key bị compromise cần ưu tiên hành động nào?
A. Chỉ tăng độ dài digest của các artifact phát hành tiếp theo.
B. Ngừng ký bằng key đó, thu hồi trust và đánh giá artifact đã ký.
C. Giữ nguyên key để verifier không phải cập nhật trust store.
D. Xóa public key khỏi log nhưng tiếp tục chấp nhận chữ ký cũ.
Đáp án đúng: B
