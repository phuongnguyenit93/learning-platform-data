Câu 01. API key thường được dùng để nhận diện thành phần nào khi gọi API?
A. Một người dùng cụ thể đang ngồi trước thiết bị.
B. Một ứng dụng hoặc client được cấp credential.
C. Vai trò nghiệp vụ gán cho nhân viên.
D. Một phiên đăng nhập tương tác trên trình duyệt.
Đáp án đúng: B

Câu 02. Giới hạn quan trọng của API key khi dùng độc lập là gì?
A. Không xác thực danh tính người dùng cuối.
B. Nó thay thế mọi quyết định phân quyền.
C. Nó luôn xác minh danh tính người dùng cuối.
D. Nó tự cung cấp MFA cho mọi request.
Đáp án đúng: A

Câu 03. Cách phù hợp để tạo API key có độ khó đoán cao là gì?
A. Dùng mã tăng dần theo từng khách hàng.
B. Dùng hash của tên miền và ngày tạo.
C. Dùng timestamp kết hợp tên ứng dụng.
D. Dùng bộ sinh số ngẫu nhiên an toàn.
Đáp án đúng: D

Câu 04. Điều gì quan trọng nhất khi chọn độ dài API key bí mật?
A. Có độ dài cố định giống mã số nhân viên.
B. Có tiền tố dài để che phần bí mật ngắn.
C. Có thể đọc thuộc mà không cần trình quản lý.
D. Có đủ entropy để chống đoán và vét cạn.
Đáp án đúng: D

Câu 05. Một định dạng API key có tiền tố công khai và phần bí mật ngẫu nhiên mang lại lợi ích gì?
A. Tra cứu key mà không lộ phần secret.
B. Thay thế việc lưu trạng thái thu hồi key.
C. Cho phép xác minh request chỉ bằng tiền tố.
D. Làm cho phần bí mật không cần entropy cao.
Đáp án đúng: A

Câu 06. Máy chủ nên lưu API key bí mật theo cách nào?
A. Mã hóa bằng khóa nằm cùng bảng dữ liệu.
B. Lưu digest một chiều để đối chiếu khi xác minh.
C. Lưu Base64 để giảm kích thước bản ghi.
D. Lưu plaintext để có thể hiển thị lại cho chủ key.
Đáp án đúng: B

Câu 07. Khi xác minh API key đã lưu dưới dạng digest, nên làm gì?
A. Giải mã digest đã lưu về API key gốc.
B. So sánh tiền tố công khai và bỏ qua secret.
C. So sánh độ dài trước rồi chấp nhận key.
D. Tính digest đầu vào rồi so sánh an toàn.
Đáp án đúng: D

Câu 08. Vì sao tiền tố hoặc key ID hữu ích trong kho lưu API key?
A. Thay thế việc kiểm tra trạng thái key.
B. Cho phép key ID tự nó cấp quyền truy cập.
C. Giúp lưu secret nguyên văn trong log tra cứu.
D. Tra cứu bản ghi trước khi kiểm tra secret.
Đáp án đúng: D

Câu 09. API key nên được truyền qua kênh nào?
A. Qua fragment URL để trình duyệt tự gửi.
B. Qua tên host để gateway tự suy ra secret.
C. Qua header bảo mật trên kết nối TLS.
D. Qua query string trong URL của request.
Đáp án đúng: C

Câu 10. Đưa API key vào query string tạo thêm nguy cơ nào?
A. Key tự hết hạn khi URL được lưu vào history.
B. Key có thể lộ qua log, history hoặc referrer.
C. TLS tự loại query string khỏi mọi access log.
D. Trình duyệt luôn che query string khỏi proxy.
Đáp án đúng: B

Câu 11. TLS bảo vệ API key chủ yếu trước rủi ro nào?
A. Người dùng cuối bị giả mạo trong ứng dụng.
B. Key bị lộ từ mã nguồn hoặc log ứng dụng.
C. Client có key được cấp scope quá rộng.
D. Nghe lén hoặc sửa dữ liệu khi truyền.
Đáp án đúng: D

Câu 12. Một API key bị đánh cắp thường có đặc tính bảo mật nào?
A. Key yêu cầu chủ sở hữu có mặt khi sử dụng.
B. Ai giữ key đều có thể dùng credential.
C. Key tự gắn với một người dùng đã đăng nhập.
D. Key chỉ dùng được trên máy đã tạo ra nó.
Đáp án đúng: B

Câu 13. Vì sao không nên nhúng API key bí mật dài hạn vào ứng dụng mobile hoặc frontend?
A. Người dùng có thể trích xuất secret từ client.
B. TLS làm mất tác dụng khi key nằm trong client.
C. CORS tự động vô hiệu hóa mọi request ngoài miền.
D. Minify mã nguồn sẽ bảo vệ key khỏi bị đọc.
Đáp án đúng: A

Câu 14. CORS có phải cơ chế xác thực API key không?
A. Không; nhưng CORS thay thế TLS khi truyền key.
B. Có; CORS xác minh secret trước khi xử lý request.
C. Không; CORS kiểm soát truy cập chéo nguồn.
D. Có; CORS cấp danh tính client cho mọi API call.
Đáp án đúng: C

Câu 15. Giới hạn API key theo địa chỉ IP nên được xem như thế nào?
A. Bằng chứng chắc chắn về danh tính người dùng.
B. Ràng buộc bổ sung, không thay xác minh key.
C. Biện pháp ngăn key bị lộ trong repository.
D. Cơ chế thay thế hoàn toàn việc xác minh key.
Đáp án đúng: B

Câu 16. Vì sao kiểm tra Origin hoặc Referer không đủ để bảo vệ API key?
A. Origin và Referer không xác thực client.
B. Trình duyệt luôn mã hóa chúng bằng khóa riêng của server.
C. Chúng chỉ được gửi khi request đã có API key hợp lệ.
D. Chúng ngăn mọi công cụ ngoài trình duyệt gọi API.
Đáp án đúng: A

Câu 17. Scope của API key nên được thiết kế theo nguyên tắc nào?
A. Gắn scope vào tên key mà không kiểm tra phía server.
B. Cấp quyền quản trị để tránh lỗi thiếu quyền.
C. Dùng cùng scope rộng cho mọi client của tổ chức.
D. Chỉ cấp các hành động và tài nguyên thực sự cần.
Đáp án đúng: D

Câu 18. Một client chỉ cần đọc báo cáo nhưng key có quyền ghi và xóa. Rủi ro chính là gì?
A. Phạm vi ảnh hưởng tăng nếu key bị lộ.
B. TLS sẽ chặn các thao tác xóa không mong muốn.
C. Key chỉ hoạt động trong giờ làm việc.
D. Quota đọc sẽ tự giới hạn quyền ghi của key.
Đáp án đúng: A

Câu 19. Quota gắn với API key giúp kiểm soát điều gì?
A. Mức sử dụng tài nguyên của client được nhận diện.
B. Danh tính pháp lý của người dùng cuối.
C. Tính bí mật của dữ liệu trong response.
D. Quyền sở hữu của client với từng bản ghi.
Đáp án đúng: A

Câu 20. Khi một khách hàng dùng nhiều key cho cùng một ứng dụng, quota nên được cân nhắc ra sao?
A. Bỏ quota vì mỗi key đã có secret riêng.
B. Chỉ giới hạn theo key để client dễ chia nhỏ tải.
C. Cộng quota của mọi khách hàng vào một ngân sách chung.
D. Có giới hạn theo key và tổng theo client khi phù hợp.
Đáp án đúng: D

Câu 21. Một client vượt giới hạn tốc độ API. Phản hồi vận hành phù hợp thường là gì?
A. Trả dữ liệu rỗng nhưng vẫn tính request thành công.
B. Tự nâng quota cho client để tránh gián đoạn.
C. Từ chối tạm thời và hướng dẫn retry.
D. Thu hồi vĩnh viễn mọi key trong cùng hệ thống.
Đáp án đúng: C

Câu 22. Nếu nhiều tổ chức chia sẻ cùng một API key, khó khăn nào tăng lên?
A. Mỗi tổ chức tự có quota độc lập dù dùng chung key.
B. Khó quy trách nhiệm khi key bị lạm dụng.
C. Key tự phân biệt tổ chức qua địa chỉ IP.
D. Việc thu hồi key chỉ ảnh hưởng một tổ chức.
Đáp án đúng: B

Câu 23. Vì sao nên dùng API key riêng cho development, staging và production?
A. Làm cho key production không cần xoay vòng.
B. Giảm phạm vi ảnh hưởng khi key bị lộ.
C. Giúp mọi môi trường dùng chung quota dễ hơn.
D. Cho phép bỏ qua xác minh key ở môi trường thử nghiệm.
Đáp án đúng: B

Câu 24. Khi xoay vòng API key theo kế hoạch, cách triển khai nào giảm gián đoạn?
A. Dùng lại secret cũ nhưng thay tên hiển thị.
B. Tắt xác minh key trong lúc triển khai.
C. Cho phép hai key cùng hiệu lực ngắn hạn.
D. Thu hồi key cũ trước khi cấp key mới.
Đáp án đúng: C

Câu 25. Điều gì cần xảy ra khi API key bị xác định đã lộ?
A. Chỉ đổi tên key trong bảng quản trị.
B. Thu hồi key lộ và cấp key thay thế.
C. Tăng quota để theo dõi request bất thường.
D. Giữ key hoạt động tới kỳ rotation định kỳ.
Đáp án đúng: B

Câu 26. Thời hạn hết hiệu lực của API key giúp ích điều gì?
A. Bảo đảm key không thể bị sao chép.
B. Tự xác minh danh tính người dùng cuối mỗi ngày.
C. Giới hạn thời gian secret bị lộ còn dùng được.
D. Loại bỏ nhu cầu theo dõi và thu hồi key.
Đáp án đúng: C

Câu 27. Một key bị lộ công khai trên repository. Hành động ưu tiên nào phù hợp?
A. Thu hồi ngay, thay key và điều tra.
B. Đổi tên repository để secret cũ mất hiệu lực.
C. Chờ scanner xác nhận có request lạ mới thu hồi.
D. Chỉ xóa dòng secret khỏi commit mới nhất.
Đáp án đúng: A

Câu 28. Khi thu hồi API key, hệ thống nên bảo đảm điều gì?
A. Mọi request cũ được lưu cache tiếp tục được chấp nhận.
B. Key bị thu hồi vẫn dùng được cho endpoint đọc.
C. Chỉ IdP mới có thể vô hiệu hóa API key.
D. Các request mới với key đó bị từ chối nhanh chóng.
Đáp án đúng: D

Câu 29. Vì sao secret thường chỉ nên hiển thị đầy đủ một lần khi tạo?
A. Giảm cơ hội lộ lại secret qua giao diện quản trị.
B. Để server không cần lưu digest xác minh.
C. Giúp người dùng có thể tự khôi phục key khi quên.
D. Cho phép hỗ trợ kỹ thuật gửi lại key qua email.
Đáp án đúng: A

Câu 30. Ai nên được phép tạo hoặc thu hồi API key cho một client?
A. Mọi caller đã có một API key hợp lệ.
B. Chỉ hệ thống giám sát có quyền đọc log.
C. Chủ sở hữu được ủy quyền theo quy trình quản trị.
D. Bất kỳ người dùng nào biết tên client.
Đáp án đúng: C

Câu 31. Log kiểm toán về API key nên ghi thông tin nào?
A. Key ID, client, hành động và thời điểm.
B. Giá trị secret đầy đủ để tiện điều tra.
C. Header Authorization nguyên vẹn của request.
D. Bản sao key trong mọi response lỗi.
Đáp án đúng: A

Câu 32. Gateway nên xử lý API key như thế nào?
A. Chấp nhận key không rõ nguồn nếu backend đang khỏe.
B. Chuyển secret vào URL nội bộ để backend dễ đọc.
C. Ghi toàn bộ header để hỗ trợ chẩn đoán.
D. Xác minh key, áp policy và che secret.
Đáp án đúng: D

Câu 33. Nếu backend có thể bị gọi trực tiếp ngoài API gateway, rủi ro nào xuất hiện?
A. TLS nội bộ bảo đảm backend không cần xác minh caller.
B. Request có thể né kiểm soát key và quota gateway.
C. Backend sẽ kế thừa quota từ DNS của gateway.
D. Gateway tự động áp dụng policy cho mọi đường truy cập.
Đáp án đúng: B

Câu 34. Cache response API cần xử lý API key thế nào?
A. Bỏ key khỏi cache key để tăng tỷ lệ cache hit.
B. Cache mọi response theo URL bất kể credential.
C. Không chia sẻ response riêng tư giữa client.
D. Chỉ cache response khi key có scope ghi.
Đáp án đúng: C

Câu 35. Dấu hiệu nào có thể cho thấy API key đang bị lạm dụng?
A. Lưu lượng hoặc vị trí lệch mẫu thường lệ.
B. Key được tạo bởi người quản trị hệ thống.
C. Tên hiển thị của key có chứa ký tự lạ.
D. Client dùng TLS phiên bản mới hơn trước đây.
Đáp án đúng: A

Câu 36. API key khác cơ chế ký request bằng HMAC ở điểm nào?
A. HMAC không cần secret chung giữa hai phía.
B. API key tự bảo đảm request không bị phát lại.
C. HMAC ký nội dung request bằng secret chung.
D. API key luôn ký body còn HMAC chỉ nhận diện client.
Đáp án đúng: C

Câu 37. Khi dùng API key cùng access token người dùng, mỗi credential nên phục vụ mục đích nào?
A. Cả hai cùng thay thế nhau để xác minh người dùng.
B. Key cấp quyền người dùng; token chỉ dùng tính quota.
C. Token nhận diện gateway; key xác minh TLS server.
D. Key nhận diện client; token xác định người dùng và quyền của họ.
Đáp án đúng: D

Câu 38. Một API key thuộc service account không còn workload sử dụng. Nên xử lý thế nào?
A. Tăng scope để tái sử dụng cho workload khác.
B. Giữ key vô thời hạn để tránh ảnh hưởng bất ngờ.
C. Xác minh owner và phụ thuộc rồi thu hồi key không còn cần.
D. Chuyển key sang tài khoản nhân viên gần nhất.
Đáp án đúng: C

Câu 39. Làm thế nào giảm nguy cơ secret lọt vào log và hệ thống theo dõi?
A. Mã hóa log bằng cùng API key đang được gửi.
B. Chỉ tắt log ở gateway và giữ log backend nguyên vẹn.
C. Che header nhạy cảm trước khi ghi log và trace.
D. Ghi header đầy đủ rồi giới hạn quyền xem log.
Đáp án đúng: C

Câu 40. Một API nhận nhiều key không hợp lệ liên tiếp. Kiểm soát nào hữu ích ngoài xác minh secret?
A. Tự tạo key mới cho mỗi lần xác minh thất bại.
B. Rate limit, cảnh báo và chặn thử sai.
C. Tắt quota để request hợp lệ không bị ảnh hưởng.
D. Trả về key ID hợp lệ gần nhất để client thử lại.
Đáp án đúng: B
