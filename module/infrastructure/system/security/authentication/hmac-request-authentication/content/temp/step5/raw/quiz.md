1. HMAC trong xác thực HTTP request cung cấp bảo đảm chính nào?
A. Xác minh tính toàn vẹn và bên gửi biết shared secret.
B. Ẩn nội dung request khỏi người quan sát trên mạng truyền tải.
C. Cấp quyền đọc hoặc ghi tài nguyên theo role của client.
D. Chứng minh danh tính người dùng cuối bằng khóa công khai.
Đáp án đúng: A

2. Hai bên cần thống nhất điều gì trước khi triển khai canonical request?
A. Tên header chứa MAC cùng dạng Base64URL truyền tải.
B. Hàm hash của body, còn URI và header để framework tự xử lý.
C. Key ID và thời hạn secret, không cần quy định byte được ký.
D. Quy định chính xác trường và byte được đưa vào HMAC.
Đáp án đúng: D

3. Khi ký HTTP method, cách xử lý nào tránh lệch canonicalization?
A. Chuyển method về chữ thường trước khi tính MAC request.
B. Lấy method từ access log sau khi proxy đã rewrite route.
C. Giữ method theo hợp đồng; không tự đổi hoa thường.
D. Bỏ method khỏi canonical request vì URI đã mô tả thao tác.
Đáp án đúng: C

4. Hai bên nhận URI path có percent-encoding khác nhau. Cách xử lý phù hợp là gì?
A. Decode lặp đến khi chuỗi không còn dấu phần trăm nào.
B. Dùng cùng chuẩn path và decode đúng một lần ở hai phía.
C. Bỏ dấu gạch chéo để mọi route có một biểu diễn chung.
D. Dùng path từ log framework mà không công bố quy tắc chuẩn hóa.
Đáp án đúng: B

5. Canonical query string cần xử lý thế nào với tham số lặp và giá trị rỗng?
A. Chuẩn hóa encode, thứ tự và cách giữ tham số lặp.
B. Bỏ tham số lặp vì query chỉ nên có một giá trị cho mỗi tên.
C. Sắp xếp tên tham số rồi loại bỏ giá trị rỗng khỏi chuỗi ký.
D. Giữ thứ tự bất kỳ vì HMAC tự chuẩn hóa query string.
Đáp án đúng: A

6. Khi canonicalize header để ký, quy tắc nào nên được quy định?
A. Chỉ ký header đầu tiên và bỏ qua các header trùng tên.
B. Giữ nguyên chữ hoa thường của tên theo từng HTTP client.
C. Xóa mọi khoảng trắng trong value kể cả khi có ý nghĩa.
D. Chuẩn hóa tên và value theo hợp đồng ký.
Đáp án đúng: D

7. Nếu hợp đồng yêu cầu ký body, thành phần nào nên được đưa vào canonical request?
A. Số byte body mà reverse proxy ghi trong access log.
B. Object JSON sau parse và serialize theo mặc định runtime.
C. Tính digest trên byte body theo hợp đồng ký.
D. Tên file tạm do server tạo khi buffer request body.
Đáp án đúng: C

8. HMAC-SHA-256 tạo ra giá trị MAC có đặc điểm nào?
A. Digest 32 byte; Base64 chỉ đổi cách biểu diễn.
B. Digest 64 byte vì SHA-256 trả về 64 byte nhị phân.
C. Độ dài thay đổi theo số byte của request body được ký.
D. Base64URL làm tăng entropy của MAC so với digest gốc.
Đáp án đúng: A

9. Cách nào phù hợp để so sánh MAC nhận được với MAC vừa tính?
A. So sánh chuỗi thường và dừng tại byte khác đầu tiên.
B. Dùng constant-time compare sau khi kiểm tra định dạng.
C. So sánh riêng bốn byte đầu để giảm thời gian xử lý.
D. Chuyển MAC thành chữ thường rồi so sánh từng ký tự.
Đáp án đúng: B

10. Key ID trong header xác thực HMAC nên được dùng vào mục đích nào?
A. Thay thế MAC để chứng minh request có chữ ký hợp lệ.
B. Cấp quyền admin cho client sở hữu key ID đó.
C. Chứa shared secret đã mã hóa để server giải mã trực tiếp.
D. Dùng key ID để chọn khóa ứng viên cần xác minh.
Đáp án đúng: D

11. Timestamp trong canonical request chủ yếu giúp kiểm soát điều gì?
A. Đảm bảo request không thể được gửi lại trong cùng cửa sổ.
B. Mã hóa thời gian để reverse proxy không thể đọc giá trị.
C. Giới hạn tuổi request trong cửa sổ thời gian cho phép.
D. Thay thế bước kiểm tra chữ ký HMAC trên toàn request.
Đáp án đúng: C

12. Nonce giúp chống replay hiệu quả khi server thực hiện bước nào?
A. Chỉ kiểm tra nonce có đúng độ dài đã quy định.
B. Theo dõi nonce đã dùng và từ chối lần xuất hiện lại.
C. Sinh nonce mới sau khi nghiệp vụ của request hoàn tất.
D. Chấp nhận nonce lặp nếu timestamp vẫn còn hiệu lực.
Đáp án đúng: B

13. Request có timestamp còn trong cửa sổ cho phép nhưng đã được gửi trước đó. Điều gì xảy ra nếu chỉ kiểm tra timestamp?
A. Request luôn bị từ chối vì timestamp đã từng được ghi nhận.
B. HMAC tự nhận ra request đã được xử lý ở lần trước.
C. Request được xem là mới nếu body không thay đổi.
D. Replay vẫn có thể xảy ra trong cửa sổ timestamp hợp lệ.
Đáp án đúng: D

14. Trong hệ thống nhiều replica, nonce store nên bảo đảm đặc tính nào?
A. Mỗi replica giữ danh sách nonce riêng để tránh tranh chấp.
B. Nonce chỉ được ghi sau khi nghiệp vụ hoàn tất thành công.
C. Dùng store chung với thao tác check-and-set atomic.
D. Mỗi node tự đặt TTL khác nhau tùy theo tải hiện tại.
Đáp án đúng: C

15. Client và server có clock skew nhỏ. Chính sách timestamp nào hợp lý?
A. Đồng bộ clock và đặt giới hạn skew rõ ràng.
B. Chấp nhận mọi timestamp để tránh lỗi do đồng hồ lệch.
C. Dùng thời gian client làm nguồn chuẩn cho toàn hệ thống.
D. Tăng cửa sổ vô hạn và chỉ dựa vào HMAC chống replay.
Đáp án đúng: A

16. Nonce chống replay và idempotency key có vai trò khác nhau thế nào?
A. Nonce chặn request lặp; idempotency key kiểm soát lặp tác vụ.
B. Nonce bảo đảm giao dịch chỉ chạy một lần; idempotency key ký body.
C. Hai giá trị luôn thay thế nhau nếu đều được sinh ngẫu nhiên.
D. Idempotency key xác minh secret còn nonce cấp quyền truy cập.
Đáp án đúng: A

17. Nơi nào phù hợp để lưu shared secret dùng xác minh HMAC?
A. Trong source repository để mọi replica dễ đồng bộ cấu hình.
B. Trong secret manager hoặc HSM với quyền truy cập tối thiểu.
C. Trong query string để proxy chuyển tiếp tới backend xử lý.
D. Trong log khởi động để hỗ trợ khôi phục khi mất cấu hình.
Đáp án đúng: B

18. Khi xoay vòng HMAC key, cách triển khai giảm gián đoạn phù hợp là gì?
A. Thay key đồng thời và từ chối mọi request dùng key cũ ngay.
B. Chấp nhận mọi key cũ vô thời hạn để tránh lỗi phía client.
C. Dùng một secret chung cho mọi client trong thời gian chuyển đổi.
D. Hỗ trợ key mới và cũ trong cửa sổ giới hạn rồi thu hồi key cũ.
Đáp án đúng: D

19. Khi nghi ngờ shared secret đã bị lộ, hành động ưu tiên là gì?
A. Chỉ đổi key ID để giữ nguyên secret đang bị lộ.
B. Thu hồi/thay key, khoanh vùng và điều tra request.
C. Tăng timestamp window để client có thêm thời gian cập nhật.
D. Tắt kiểm tra HMAC tạm thời để tránh gián đoạn dịch vụ.
Đáp án đúng: B

20. Muốn tạo khóa HMAC riêng cho từng mục đích từ một secret gốc, nên làm gì?
A. Dùng nguyên secret gốc cho mọi giao thức và endpoint.
B. Nối secret với timestamp mỗi lần request để tạo khóa mới.
C. Dùng HKDF với context riêng cho từng mục đích.
D. Hash secret một lần rồi dùng cùng digest cho mọi client.
Đáp án đúng: C

21. Vì sao nên cấp shared secret riêng cho từng client tích hợp?
A. Giới hạn blast radius và thu hồi từng client độc lập.
B. Giúp mọi client tạo cùng một MAC cho cùng request.
C. Loại bỏ nhu cầu xác minh key ID khi nhận request.
D. Cho phép client tự chia sẻ secret với các tenant khác.
Đáp án đúng: A

22. Hai tenant dùng chung HMAC secret. Rủi ro chính là gì?
A. HMAC-SHA-256 không thể xử lý nhiều tenant cùng lúc.
B. Timestamp của tenant này tự động làm hết hạn key kia.
C. Query string của hai tenant luôn được chuẩn hóa giống nhau.
D. Lộ secret ở một tenant có thể giả mạo request tenant khác.
Đáp án đúng: D

23. Một request có HMAC hợp lệ chứng minh điều gì về quyền truy cập?
A. Người dùng cuối đã đăng nhập bằng MFA.
B. Client được phép đọc và sửa mọi tài nguyên của hệ thống.
C. HMAC chứng minh biết secret, không cấp quyền.
D. Request được mã hóa và không thể bị đọc trên mạng.
Đáp án đúng: C

24. Nếu Host header và X-Forwarded-Host do client tự gửi, verifier nên xử lý thế nào?
A. Tin mọi forwarded header vì proxy thường thêm chúng.
B. Chọn giá trị dài nhất để tránh header bị cắt.
C. Dùng Host bất kỳ vì HMAC chỉ phụ thuộc vào body.
D. Chỉ tin proxy tin cậy và quy định header được ký.
Đáp án đúng: D

25. Gateway rewrite path trước khi backend xác minh HMAC. Cách thiết kế nào tránh signature mismatch?
A. Backend tự đoán path ban đầu từ route name nội bộ.
B. Chốt điểm canonicalize và dùng cùng path hai phía.
C. Bỏ path khỏi canonical request trong mọi trường hợp.
D. Decode path nhiều lần ở backend để khôi phục chuỗi gốc.
Đáp án đúng: B

26. Request chứa hai header cùng tên nhưng khác giá trị. Chính sách nào an toàn hơn?
A. Luôn lấy header cuối vì mọi HTTP server xử lý giống nhau.
B. Ghép hai value bằng dấu phẩy mà không xét semantics.
C. Từ chối header mơ hồ hoặc chuẩn hóa theo quy tắc.
D. Ký header đầu tiên nhưng ứng dụng lại sử dụng header cuối.
Đáp án đúng: C

27. Proxy giải nén Content-Encoding trước khi backend xác minh body digest. Hợp đồng ký nên làm gì?
A. Bỏ digest body vì proxy đã thay đổi nội dung truyền.
B. Quy định rõ ký byte trước hay sau giải nén và giữ nhất quán.
C. Ký kích thước compressed body nhưng xác minh body đã giải nén.
D. Parse body thành object rồi bỏ qua encoding ban đầu.
Đáp án đúng: B

28. HTTP chunked transfer encoding ảnh hưởng canonical body thế nào?
A. Ký entity body sau khi bỏ framing truyền tải.
B. Ký từng chunk cùng delimiter do transport tự sinh ra.
C. Dùng chunk size làm nonce để tránh request bị gửi lại.
D. Loại body khỏi chữ ký vì chunked không có Content-Length.
Đáp án đúng: A

29. Tên HTTP header không phân biệt hoa thường. Canonicalization nên làm gì?
A. Chuẩn hóa tên header cố định và xử lý value theo quy tắc.
B. Chuyển cả tên header và mọi value sang chữ thường.
C. Giữ nguyên byte tên header do từng client gửi lên.
D. Bỏ header khỏi canonical request nếu cách viết hoa khác nhau.
Đáp án đúng: A

30. Khi ký một tập header, cách chọn header nào hợp lý?
A. Ký mọi header hop-by-hop mà proxy có thể tự thay đổi.
B. Chỉ ký User-Agent vì header này xác định phần mềm client.
C. Ký một header bất kỳ để giảm kích thước canonical request.
D. Liệt kê header cần ký; loại header proxy tự đổi.
Đáp án đúng: D

31. Thông báo lỗi xác minh HMAC nên được thiết kế thế nào?
A. Trả MAC kỳ vọng để client tự so sánh và sửa request.
B. Phân biệt chi tiết key không tồn tại và MAC sai cho mọi caller.
C. Trả lỗi chung, log chi tiết có kiểm soát và không lộ secret.
D. Trả canonical request cùng thông tin secret để tiện debug.
Đáp án đúng: C

32. Client gửi trường thuật toán trong header. Verifier nên chọn thuật toán ra sao?
A. Chấp nhận bất kỳ thuật toán nào client khai báo trong request.
B. Thử lần lượt mọi thuật toán cho tới khi có MAC khớp.
C. Dùng allowlist thuật toán do server quy định.
D. Bỏ qua key ID và suy ra thuật toán từ độ dài chữ ký.
Đáp án đúng: C

33. Body lớn được truyền dạng stream. Cách xác minh nào phù hợp?
A. Xác minh MAC từ vài byte đầu rồi xử lý phần body còn lại.
B. Hash theo stream; chỉ xử lý sau khi xác minh.
C. Bỏ body khỏi chữ ký vì buffer toàn bộ sẽ tốn bộ nhớ.
D. Tin Content-Length thay cho kiểm tra byte body thực tế.
Đáp án đúng: B

34. Khi dùng thư viện constant-time compare, điều kiện nào vẫn cần kiểm tra?
A. Không cần kiểm tra định dạng vì thư viện tự chuẩn hóa mọi input.
B. Chỉ kiểm tra byte đầu của MAC trước khi gọi thư viện.
C. Chuyển MAC thành Unicode string để so sánh không phân biệt hoa.
D. Kiểm tra độ dài và encoding trước constant-time compare.
Đáp án đúng: D

35. Vì sao canonicalization protocol nên có version được ký?
A. Để server tự bỏ qua các trường không tương thích với client.
B. Để hai phía chọn đúng quy tắc và tránh downgrade chuẩn yếu.
C. Để tăng độ dài HMAC mà không cần đổi thuật toán.
D. Để key ID thay thế được timestamp và nonce trong request.
Đáp án đúng: B

36. Gateway đã xác minh HMAC rồi gửi header X-Client-Identity tới backend. Điều kiện nào giúp backend tin header này?
A. Tin header chỉ từ gateway xác thực; chặn truy cập trực tiếp.
B. Tin header từ mọi nguồn vì tên header khó đoán từ bên ngoài.
C. Client được tự gửi header đó nếu HMAC ở gateway hợp lệ.
D. Bỏ xác thực TLS nội bộ để giảm độ trễ truyền tải giữa dịch vụ.
Đáp án đúng: A
