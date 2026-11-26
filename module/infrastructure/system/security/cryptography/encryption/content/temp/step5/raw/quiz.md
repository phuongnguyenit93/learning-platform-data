1. Mã hóa đối xứng có đặc điểm cốt lõi nào?
A. Cùng một khóa bí mật được dùng để mã hóa và giải mã.
B. Khóa công khai mã hóa còn khóa riêng luôn xác minh ciphertext.
C. Mỗi block dữ liệu cần một cặp khóa công khai riêng.
D. Người nhận giải mã bằng certificate của bên gửi.
Đáp án đúng: A

2. AEAD như AES-GCM cung cấp những bảo đảm nào?
A. Chỉ che nội dung, còn thay đổi ciphertext không bị phát hiện.
B. Chỉ xác minh nguồn gửi, không bảo vệ nội dung plaintext.
C. Chỉ kiểm tra hash của dữ liệu sau khi giải mã hoàn tất.
D. Bảo mật nội dung và xác thực ciphertext cùng metadata.
Đáp án đúng: D

3. Mô hình hybrid encryption thường kết hợp hai cơ chế ra sao?
A. Mã hóa toàn bộ file bằng RSA rồi dùng AES kiểm tra kết quả.
B. Dùng hash để mã hóa dữ liệu rồi ký digest bằng khóa công khai.
C. Dùng data key đối xứng cho dữ liệu và public key để bọc key.
D. Dùng khóa riêng để mã hóa file và public key để giải mã file.
Đáp án đúng: C

4. Vì sao AES-ECB không phù hợp để mã hóa dữ liệu có cấu trúc lặp?
A. ECB cần một certificate riêng cho từng block dữ liệu.
B. Các block plaintext giống nhau tạo block ciphertext giống nhau.
C. ECB chỉ hỗ trợ khóa 128 bit và không hỗ trợ khóa dài hơn.
D. ECB luôn thêm nonce ngẫu nhiên trước mỗi block được mã hóa.
Đáp án đúng: B

5. Điều kiện quan trọng khi dùng AES-GCM với cùng một key là gì?
A. Không tái sử dụng nonce giữa các lần mã hóa bằng key đó.
B. Dùng lại nonce khi plaintext và associated data giống nhau.
C. Nonce phải được giữ bí mật giống như khóa mã hóa.
D. Tạo nonce từ timestamp mà không cần xét trùng lặp.
Đáp án đúng: A

6. Ứng dụng nên làm gì với plaintext do AEAD giải mã trả về?
A. Dùng ngay plaintext rồi kiểm tra tag sau khi xử lý nghiệp vụ.
B. Chỉ kiểm tra độ dài plaintext trước khi xác thực tag.
C. Ghi plaintext ra log tạm rồi mới xác minh tag nhận được.
D. Chỉ dùng plaintext sau khi authentication tag hợp lệ.
Đáp án đúng: D

7. Associated data trong AEAD có vai trò nào?
A. Nó được mã hóa cùng ciphertext và có thể khôi phục sau giải mã.
B. Nó thay thế nonce và làm cho nonce có thể được tái sử dụng.
C. Nó được xác thực nhưng không được mã hóa thành ciphertext.
D. Nó được dùng làm khóa bí mật bổ sung cho mỗi request.
Đáp án đúng: C

8. Khi dùng AES-GCM, nonce 96-bit thường được chọn vì lý do nào?
A. Đây là kích thước nonce được hỗ trợ hiệu quả và phổ biến.
B. Độ dài này làm tăng key AES từ 128 bit lên 224 bit.
C. Nonce 96-bit không bao giờ cần quản lý tính duy nhất.
D. Kích thước này cho phép bỏ qua bước xác minh authentication tag.
Đáp án đúng: A

9. AES-CTR cần bảo đảm điều gì giữa các message dùng chung key?
A. Counter có thể lặp nếu plaintext được padding trước.
B. Không dùng lại cùng nonce/counter stream dưới cùng một key.
C. Counter phải được giữ bí mật và mã hóa bằng public key.
D. Mỗi message phải dùng một khóa riêng được tạo từ timestamp.
Đáp án đúng: B

10. Điểm yếu chính của AES-CBC khi dùng riêng lẻ là gì?
A. CBC không thể mã hóa dữ liệu dài hơn một block.
B. CBC không hỗ trợ IV và luôn dùng block đầu làm IV.
C. CBC tự xác thực ciphertext nên không cần kiểm tra integrity.
D. CBC không cung cấp xác thực toàn vẹn nếu thiếu cơ chế riêng.
Đáp án đúng: D

11. ChaCha20-Poly1305 yêu cầu quy tắc nonce nào?
A. Nonce có thể lặp nếu Poly1305 tag khác nhau.
B. Nonce cần được mã hóa bằng cùng khóa ChaCha20.
C. Không tái sử dụng nonce với cùng khóa AEAD.
D. Nonce phải được sinh từ password của người dùng cuối.
Đáp án đúng: C

12. IV của AES-CBC nên có đặc tính nào?
A. Có thể cố định miễn là khóa thay đổi mỗi tháng.
B. Khó đoán tại thời điểm mã hóa và được truyền cùng ciphertext.
C. Phải được giữ bí mật như key để ngăn người nhận giải mã.
D. Được tính từ plaintext bằng hash không khóa để dễ tái tạo.
Đáp án đúng: B

13. Một hệ thống cũ dùng AES-CBC kèm HMAC. Thứ tự xử lý nào phù hợp?
A. Giải mã trước rồi chỉ xác minh HMAC nếu padding hợp lệ.
B. Bỏ HMAC nếu ciphertext có độ dài chia hết cho block size.
C. Kiểm tra plaintext theo nghiệp vụ trước khi xác minh HMAC.
D. Xác minh MAC trước khi giải mã và xử lý plaintext.
Đáp án đúng: D

14. Điều gì quyết định sức mạnh thực tế của một khóa AES?
A. Độ dài chuỗi hex hiển thị trong file cấu hình.
B. Số lần khóa được sử dụng trước khi rotation.
C. Entropy của key material và độ an toàn của cách quản lý.
D. Tên thuật toán được ghi trong metadata của ciphertext.
Đáp án đúng: C

15. Trong RSA-OAEP, cặp khóa thường được dùng thế nào khi mã hóa cho người nhận?
A. Mã hóa bằng public key người nhận và giải mã bằng private key.
B. Mã hóa bằng private key người gửi và giải mã bằng public key.
C. Dùng cùng public key ở cả hai phía để khôi phục plaintext.
D. Dùng certificate để mã hóa và hash để giải mã dữ liệu.
Đáp án đúng: A

16. Vì sao không nên dùng RSA trực tiếp để mã hóa file lớn?
A. RSA phù hợp bọc khóa nhỏ; dữ liệu lớn dùng mã hóa đối xứng.
B. RSA không thể dùng public key và private key trong cùng hệ thống.
C. RSA yêu cầu mỗi block plaintext có độ dài đúng bằng modulus.
D. RSA luôn tạo ciphertext ngắn hơn plaintext nên không lưu được file.
Đáp án đúng: A

17. Hybrid encryption thường truyền data encryption key cho người nhận ra sao?
A. Gửi DEK plaintext qua cùng kênh với ciphertext dữ liệu.
B. Bọc DEK bằng public key của người nhận hoặc khóa KMS.
C. Hash DEK rồi yêu cầu người nhận tự đoán lại khóa ban đầu.
D. Ký DEK bằng private key của người gửi thay cho việc bọc khóa.
Đáp án đúng: B

18. Forward secrecy trong TLS thường dựa trên cơ chế nào?
A. Dùng lại RSA private key dài hạn để mã hóa mọi phiên.
B. Dùng cùng session key cho các kết nối của một client.
C. Lưu mọi ephemeral secret trong certificate để phục hồi sau này.
D. Dùng khóa trao đổi tạm thời riêng cho từng phiên kết nối.
Đáp án đúng: D

19. Mã hóa at rest chủ yếu bảo vệ dữ liệu trước tình huống nào?
A. Ứng dụng đã được cấp quyền đọc plaintext từ database.
B. Thiết bị hoặc storage bị lấy cắp khi không có quyền giải mã.
C. Người dùng có quyền hợp lệ truy vấn dữ liệu qua ứng dụng.
D. Service đã giải mã dữ liệu rồi gửi plaintext tới client.
Đáp án đúng: B

20. Khi nào mã hóa in transit cần được áp dụng?
A. Chỉ khi dữ liệu được lưu lâu dài trong database.
B. Chỉ với traffic đi qua mạng internet công cộng.
C. Khi dữ liệu truyền giữa client, gateway và dịch vụ liên quan.
D. Chỉ khi payload chứa file lớn hơn giới hạn upload.
Đáp án đúng: C

21. Vai trò phù hợp của KMS hoặc HSM trong kiến trúc mã hóa là gì?
A. Bảo vệ và kiểm soát thao tác với key theo quyền được cấp.
B. Thay thế hoàn toàn authorization trên dữ liệu ứng dụng.
C. Tự động mã hóa mọi plaintext mà không cần tích hợp dịch vụ.
D. Lưu key cạnh ciphertext để việc giải mã luôn có sẵn.
Đáp án đúng: A

22. Envelope encryption thường hoạt động theo cách nào?
A. Mã hóa ciphertext bằng nhiều password do người dùng chọn.
B. Dùng một master key trực tiếp mã hóa mọi byte của mọi file.
C. Lưu DEK plaintext trong metadata và mã hóa master key riêng.
D. Dùng DEK mã hóa dữ liệu; KEK bọc DEK để bảo vệ khóa.
Đáp án đúng: D

23. Ciphertext cần lưu thông tin nào để hỗ trợ key rotation và giải mã?
A. Plaintext gốc để đối chiếu khi giải mã thất bại.
B. Mật khẩu người dùng đã dùng lúc tạo bản ghi.
C. Key ID/version cùng nonce, IV và tag cần thiết.
D. Danh sách mọi khóa bí mật hiện có trong KMS.
Đáp án đúng: C

24. Chiến lược rotation khóa mã hóa dữ liệu đang lưu phù hợp là gì?
A. Xóa key cũ ngay khi tạo key mới, không cần xét ciphertext cũ.
B. Dùng key mới để giải mã mọi ciphertext đã tạo bằng key cũ.
C. Giữ nguyên key cũ mãi mãi để không phải migrate dữ liệu.
D. Giữ khả năng đọc key version cũ và chuyển đổi có kế hoạch.
Đáp án đúng: D

25. Vì sao nên tách khóa mã hóa dữ liệu khỏi khóa dùng cho mục đích khác?
A. Để mọi thuật toán dùng cùng một key có định dạng thống nhất.
B. Để giới hạn ảnh hưởng khi key bị lộ hoặc dùng sai mục đích.
C. Để có thể công khai key mã hóa mà không cần xác thực người nhận.
D. Để bỏ qua metadata key version khi dữ liệu được lưu trữ.
Đáp án đúng: B

26. Mã hóa xác định (deterministic encryption) có thể làm lộ thông tin nào?
A. Private key của hệ thống sau một lần quan sát ciphertext.
B. Nonce ngẫu nhiên của mọi message được tạo trong tương lai.
C. Quan hệ bằng nhau và tần suất lặp của các plaintext.
D. Nội dung đầy đủ của plaintext trong mọi trường hợp.
Đáp án đúng: C

27. Một hệ thống dùng AES-CBC kèm HMAC. Điều gì cần tránh khi xác minh dữ liệu?
A. Dùng một IV riêng cho mỗi lần mã hóa theo hợp đồng.
B. Trả lỗi khác nhau cho padding sai và MAC không hợp lệ.
C. Xác minh MAC trước khi giải mã ciphertext.
D. Tách khóa MAC khỏi khóa mã hóa bằng KDF phù hợp.
Đáp án đúng: B

28. Rút ngắn authentication tag của AEAD quá mức có tác động gì?
A. Tăng xác suất giả mạo tag và giảm mức bảo vệ toàn vẹn.
B. Làm ciphertext dài hơn nhưng giữ nguyên khả năng xác thực.
C. Làm nonce trở thành duy nhất dù ứng dụng có tái sử dụng.
D. Chuyển thuật toán AEAD thành mã hóa bất đối xứng.
Đáp án đúng: A

29. Lỗi giải mã nên được phản hồi ra bên ngoài thế nào?
A. Dùng lỗi tổng quát, tránh tiết lộ padding hay tag sai.
B. Trả khác biệt chi tiết giữa padding sai và tag không hợp lệ.
C. Trả plaintext một phần để client xác định vị trí lỗi.
D. Ghi key material vào response để hỗ trợ debug.
Đáp án đúng: A

30. Ứng dụng nhận tên thuật toán từ request header. Cách chọn thuật toán an toàn là gì?
A. Chấp nhận mọi thuật toán client khai báo để tăng tương thích.
B. Thử lần lượt các thuật toán cũ cho tới khi giải mã được.
C. Dùng thuật toán yếu hơn nếu ciphertext không giải mã được.
D. Chọn từ allowlist do server cấu hình và gắn với key policy.
Đáp án đúng: D

31. TLS bảo vệ dữ liệu truyền tải. Vì sao client vẫn cần xác minh certificate hostname?
A. Để client có thể bỏ qua kiểm tra certificate chain.
B. Để server tự chọn thuật toán mã hóa theo hostname gửi lên.
C. Để xác nhận endpoint đang kết nối đúng danh tính mong đợi.
D. Để biến TLS thành cơ chế phân quyền cho từng object.
Đáp án đúng: C

32. TLS được kết thúc tại load balancer. Dữ liệu từ đó tới backend cần được xem xét thế nào?
A. Luôn an toàn vì request đã đi qua một kết nối TLS trước đó.
B. Có thể chuyển plaintext vì mạng nội bộ mặc định tin cậy.
C. Cần bảo vệ hop nội bộ theo threat model và trust boundary.
D. Không cần xác thực backend nếu load balancer có certificate hợp lệ.
Đáp án đúng: C

33. Backup chứa ciphertext nhưng không có key version hoặc đường truy cập KMS khả dụng. Rủi ro nào xuất hiện?
A. Backup tự giải mã được vì ciphertext chứa thông tin khóa đầy đủ.
B. Không thể khôi phục plaintext dù các file backup còn nguyên.
C. KMS tự tái tạo key cũ từ checksum của backup.
D. Ciphertext tự chuyển sang key mới khi backup được restore.
Đáp án đúng: B

34. Vì sao không nên ghi plaintext hoặc key vào log khi lỗi mã hóa?
A. Log không thể được lưu trữ bền vững trên hệ thống tập trung.
B. Log làm thay đổi ciphertext đã được lưu trong database.
C. Log khiến nonce của AEAD tự động bị tái sử dụng.
D. Log mở rộng bề mặt lộ dữ liệu và bí mật vận hành.
Đáp án đúng: D

35. Crypto agility giúp tổ chức xử lý thay đổi nào?
A. Dùng một thuật toán cố định để mọi client tương thích mãi mãi.
B. Chuyển thuật toán và key version có kiểm soát khi tiêu chuẩn đổi.
C. Bỏ metadata phiên bản vì KMS luôn chọn đúng key tự động.
D. Tắt thuật toán mới cho tới khi mọi dữ liệu được giải mã.
Đáp án đúng: B

36. Kiểm thử triển khai AEAD nên bao gồm trường hợp nào?
A. Sửa ciphertext, nonce hoặc tag và xác nhận giải mã thất bại.
B. Chỉ kiểm tra ciphertext giải mã đúng với plaintext ban đầu.
C. Chỉ đo tốc độ mã hóa trên một payload không đổi.
D. Bỏ qua thử nghiệm nonce reuse vì thư viện tự quản lý mọi trường hợp.
Đáp án đúng: A
