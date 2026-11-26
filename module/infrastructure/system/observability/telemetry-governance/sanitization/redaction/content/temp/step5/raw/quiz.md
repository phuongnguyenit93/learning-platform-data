Câu 1. Mục tiêu chính của redaction telemetry là gì?
A. Ẩn trường chỉ trong giao diện dashboard
B. Loại trường nhạy cảm trước khi export
C. Nén payload trước khi gửi sang backend
D. Đổi tên metric theo chuẩn backend
Đáp án đúng: B

Câu 2. Giá trị nào cần được nhận diện là secret trong log?
A. Tên service trong resource attributes
B. Thời lượng xử lý của một request
C. Access token dùng để xác thực API
D. Mã HTTP 503 của response dịch vụ
Đáp án đúng: C

Câu 3. Trường nào là direct identifier trong bản ghi ứng dụng?
A. Email định danh của một cá nhân
B. Thời lượng xử lý request tính bằng ms
C. Mã HTTP 503 từ dịch vụ gateway
D. Tên môi trường production của app
Đáp án đúng: A

Câu 4. Với log JSON có trường customer.email, cách redaction phù hợp là gì?
A. Mask theo đường dẫn customer.email
B. Thay toàn bộ document thành chuỗi rỗng
C. Đổi tên index thay cho xử lý field
D. Ẩn field chỉ trên dashboard Kibana
Đáp án đúng: A

Câu 5. URL trong log có thể làm lộ dữ liệu nhạy cảm qua phần nào?
A. Tên scheme và phiên bản giao thức được dùng
B. Tên host và cổng của dịch vụ đích
C. Mã trạng thái trả về sau khi xử lý request
D. Query chứa token hoặc dữ liệu cá nhân
Đáp án đúng: D

Câu 6. Log có header Authorization Bearer nên được xử lý thế nào?
A. Chỉ ẩn token trên giao diện dashboard
B. Giữ token nếu log chỉ lưu trong nội bộ
C. Đưa token vào label để tiện tìm kiếm
D. Che token trước khi log được export
Đáp án đúng: D

Câu 7. Redaction khác masking một phần ở điểm nào?
A. Redaction chỉ đổi tên trường dữ liệu
B. Redaction xóa giá trị nhạy cảm khỏi bản ghi
C. Masking chỉ áp dụng cho dữ liệu dạng số
D. Masking thay bằng ký tự che một phần
Đáp án đúng: B

Câu 8. Pseudonymization bằng HMAC có ích trong trường hợp nào?
A. Khôi phục plaintext mà không cần khóa
B. Xóa mọi khả năng liên kết giữa các bản ghi
C. Tạo mã ổn định bằng khóa bí mật
D. Thay thế cơ chế phân quyền của backend
Đáp án đúng: C

Câu 9. Trong OpenTelemetry Collector, pipeline thường có thứ tự nào?
A. Processor chạy trước receiver và exporter
B. Exporter nhận dữ liệu trước receiver
C. Receiver chuyển thẳng exporter, bỏ processor
D. Receiver, processor rồi exporter
Đáp án đúng: D

Câu 10. Attributes processor thường hỗ trợ thao tác nào?
A. Xóa hoặc cập nhật attribute theo policy
B. Tạo dashboard theo từng service
C. Cấp quyền đọc index cho người dùng
D. Xoay vòng khóa mã hóa của ổ đĩa
Đáp án đúng: A

Câu 11. OTTL trong transform processor phù hợp để làm gì?
A. Cấp token truy cập cho exporter
B. Tạo snapshot cho backend lưu trữ
C. Đổi hoặc xóa attribute theo rule
D. Mở cổng mạng cho OTLP receiver
Đáp án đúng: C

Câu 12. Filter processor trong Collector thực hiện việc gì?
A. Che một phần ký tự trong trường văn bản
B. Mã hóa payload trước khi gửi qua mạng
C. Đổi nhãn service theo danh sách receiver
D. Loại record không thỏa điều kiện giữ lại
Đáp án đúng: D

Câu 13. Redaction nên diễn ra ở vị trí nào trong pipeline?
A. Sau khi backend đã lưu bản ghi
B. Chỉ khi người dùng chạy truy vấn
C. Trước exporter và các nhánh chuyển tiếp
D. Sau khi hết thời hạn lưu giữ dữ liệu
Đáp án đúng: C

Câu 14. Lợi ích của sanitization trong ứng dụng trước khi phát telemetry là gì?
A. Metric cardinality tự giảm khi đổi tên field
B. Collector khôi phục giá trị gốc từ dữ liệu đã che
C. Backend tự phân quyền nên không cần lọc ở nguồn
D. Không đưa dữ liệu nhạy cảm vào luồng telemetry
Đáp án đúng: D

Câu 15. Redaction tại Collector có giới hạn nào cần nhớ?
A. Có thể thay thế kiểm soát tại nguồn phát
B. Luôn tác động đến mọi exporter trong hệ thống
C. Không sửa được bản sao đã gửi qua luồng khác
D. Tự sửa mọi bản ghi đã lưu ở backend
Đáp án đúng: C

Câu 16. Nếu bước redaction lỗi do cấu hình, hành vi an toàn là gì?
A. Chặn dữ liệu chưa được làm sạch
B. Bỏ qua lỗi rồi gửi payload gốc tiếp
C. Chỉ ghi cảnh báo và tiếp tục export
D. Tự gán nhãn public rồi tiếp tục gửi
Đáp án đúng: A

Câu 17. Vì sao nên parse log có cấu trúc trước khi redact field?
A. Chuyển mọi trường thành metric label
B. Nhắm đúng field, tránh sửa nhầm văn bản
C. Giữ nguyên mọi secret trong raw message
D. Bỏ qua khác biệt giữa JSON và plain text
Đáp án đúng: B

Câu 18. Regex quá rộng trong quy tắc redaction có thể gây ra vấn đề gì?
A. Giảm cardinality mà không đổi nội dung log
B. Chỉ khớp đúng một field theo schema
C. Tự động giữ lại mọi token hợp lệ
D. Có thể xóa nhầm nội dung chẩn đoán
Đáp án đúng: D

Câu 19. Trong trace, ngoài span attributes cần kiểm tra vị trí nào?
A. Trace ID và Span ID của span
B. Trạng thái sampling của SDK
C. Resource attributes và span events
D. Tên exporter nhận OTLP request
Đáp án đúng: C

Câu 20. Khi redact span, trường nào thường nên giữ để nối trace?
A. Trace ID và Span ID
B. Email và access token
C. Request body đầy đủ
D. Header Authorization gốc
Đáp án đúng: A

Câu 21. Metric label chứa email nên được xử lý ra sao?
A. Giữ email nhưng rút ngắn tên metric
B. Loại email, giữ nhãn miền hữu hạn
C. Chuyển email thành nhãn khác trên backend
D. Đưa email vào tên exporter để tra cứu
Đáp án đúng: B

Câu 22. Exemplar hoặc trace context cần được cân nhắc thế nào khi redact metrics?
A. Xóa toàn bộ metric khi exemplar có mặt
B. Thêm trace ID thành label cho mọi sample
C. Đưa token xác thực vào exemplar để đối chiếu
D. Giữ liên kết an toàn, không mang PII
Đáp án đúng: D

Câu 23. Sampling có thay thế được redaction không?
A. Có; sampling tự xóa attribute nhạy cảm
B. Không; trace được giữ vẫn phải làm sạch
C. Không; redaction chỉ áp dụng sau sampling
D. Có; trace bị lấy mẫu sẽ không còn PII
Đáp án đúng: B

Câu 24. Khi nhiều pipeline cùng export một nguồn telemetry, cần làm gì?
A. Chỉ redact nhánh lưu trữ lâu nhất
B. Áp policy trên từng nhánh export
C. Chỉ redact nhánh gửi đến dashboard
D. Để backend cuối tự đồng bộ policy
Đáp án đúng: B

Câu 25. Kiểm thử redaction bằng sentinel value nên xác minh điều gì?
A. Sentinel nhạy cảm không còn trong output
B. Payload sau xử lý giống hệt đầu vào
C. Mọi attribute đều bị xóa khỏi record
D. Exporter từ chối toàn bộ dữ liệu kiểm thử
Đáp án đúng: A

Câu 26. Kiểm thử false positive cho quy tắc redaction nhằm xác nhận điều gì?
A. Mọi field đều đổi thành cùng một token
B. Mọi chuỗi có chữ số đều bị xóa
C. Dữ liệu hợp lệ vẫn giữ ngữ cảnh chẩn đoán
D. Tất cả event đều bị loại trước export
Đáp án đúng: C

Câu 27. Sau khi redact log, cần kiểm tra thêm điều gì để bảo đảm khả năng điều tra?
A. Thông tin lỗi và khóa tương quan còn lại
B. Số lượng field luôn bằng bản ghi ban đầu
C. Tên file nguồn được thêm vào từng metric
D. Mọi giá trị gốc vẫn có thể khôi phục trực tiếp
Đáp án đúng: A

Câu 28. Thay đổi quy tắc redaction nên được quản lý ra sao?
A. Review, version hóa và test trước deploy
B. Sửa trực tiếp production mà không lưu lịch sử
C. Cho từng exporter tự đặt quy tắc riêng
D. Chỉ kiểm tra policy khi xảy ra rò rỉ
Đáp án đúng: A

Câu 29. Nếu secret thật đã được xuất vào telemetry, nên ưu tiên hành động nào?
A. Chỉ che token trên dashboard hiện tại
B. Đổi tên attribute rồi tiếp tục dùng token
C. Thu hồi hoặc xoay vòng secret bị lộ
D. Tăng sampling để log ít xuất hiện hơn
Đáp án đúng: C

Câu 30. Khi không chắc một field có nhạy cảm hay không, nên làm gì?
A. Đổi tên field rồi coi như đã được bảo vệ
B. Áp policy an toàn rồi xác minh chủ sở hữu
C. Mặc định cho phép export để tránh mất dữ liệu
D. Gửi field sang mọi backend để so sánh
Đáp án đúng: B

Câu 31. Một quy tắc redact token nên được kiểm thử với dạng đầu vào nào?
A. Chỉ token đã hết hạn trong môi trường test
B. Chỉ token xuất hiện trong tên metric
C. Chỉ token có độ dài cố định duy nhất
D. Token ở header, query và log body
Đáp án đúng: D

Câu 32. Khi redact PII nhưng cần nối sự kiện cùng người dùng, lựa chọn nào phù hợp?
A. Giữ email thật trong log và trace
B. Mã giả ổn định với khóa được bảo vệ
C. Sinh mã ngẫu nhiên mới cho mỗi sự kiện
D. Dùng timestamp làm định danh người dùng
Đáp án đúng: B
