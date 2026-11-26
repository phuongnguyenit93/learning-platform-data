Câu 1. Mục tiêu của phân loại telemetry là gì?
A. Tăng tốc độ scrape trên mọi nguồn dữ liệu
B. Chuẩn hóa tên metric giữa các ứng dụng
C. Giảm số span được gửi lên backend
D. Bảo vệ dữ liệu theo độ nhạy và mục đích
Đáp án đúng: D

Câu 2. Tiêu chí nào nên chi phối mức phân loại dữ liệu?
A. Số dashboard đang truy cập dữ liệu
B. Kích thước trung bình của mỗi bản ghi
C. Tác động khi dữ liệu bị lộ hoặc dùng sai
D. Ngôn ngữ lập trình tạo ra dữ liệu đó
Đáp án đúng: C

Câu 3. Data minimization trong telemetry có nghĩa là gì?
A. Chỉ thu thập dữ liệu có thể lập chỉ mục
B. Chỉ thu thập trường cần thiết cho mục đích
C. Sao chép toàn bộ payload sang mọi backend
D. Thu thập mọi trường rồi giữ vô thời hạn
Đáp án đúng: B

Câu 4. Trường nào là direct identifier trong log?
A. Mã trạng thái HTTP của response
B. Tên môi trường triển khai production
C. Địa chỉ email gắn với một cá nhân
D. Thời lượng xử lý tính bằng mili giây
Đáp án đúng: C

Câu 5. Pseudonymization khác anonymization ở điểm nào?
A. Dữ liệu giả danh không thể liên kết với cá nhân
B. Dữ liệu giả danh vẫn có thể liên kết lại
C. Dữ liệu ẩn danh luôn cần khóa giải mã riêng
D. Hai cách chỉ thay đổi định dạng lưu trữ
Đáp án đúng: B

Câu 6. Email băm SHA-256 vẫn có thể là dữ liệu cá nhân khi nào?
A. Khi dữ liệu được xuất qua giao thức TLS
B. Khi chuỗi băm được lưu trong file nhị phân
C. Khi salt được đặt trong tên dashboard
D. Khi vẫn dò hoặc liên kết được với người dùng
Đáp án đúng: D

Câu 7. Giá trị nào nên được xem là secret trong telemetry?
A. Tên service không chứa thông tin cá nhân
B. Thời gian khởi động của một process
C. Access token có thể cấp quyền truy cập
D. Mã HTTP 503 của một response
Đáp án đúng: C

Câu 8. Log toàn bộ request body có nguy cơ gì?
A. Luôn làm mất timestamp gốc của sự kiện
B. Tự động biến mọi field thành metric label
C. Có thể chứa PII hoặc credential ngoài ý muốn
D. Ngăn collector gửi dữ liệu bằng OTLP
Đáp án đúng: C

Câu 9. Vì sao tránh đưa user ID hoặc email vào metric label?
A. Làm counter tự đổi thành gauge khi scrape
B. Tăng cardinality và có thể lộ định danh
C. Khiến Prometheus không thể lưu timestamp
D. Làm histogram mất các bucket tích lũy
Đáp án đúng: B

Câu 10. Trace attribute nào cần xem xét kỹ trước khi export?
A. Mã trạng thái HTTP chuẩn của response
B. Tên span operation đã được chuẩn hóa
C. Query string chứa token hoặc dữ liệu người dùng
D. Tên service trong resource attributes
Đáp án đúng: C

Câu 11. Profiles có thể lộ thông tin nhạy cảm qua thành phần nào?
A. Tổng thời lượng của span đã kết thúc
B. Tên metric và đơn vị đo đã chuẩn hóa
C. Số mẫu CPU được lấy trong mỗi giây
D. Tên hàm, source path hoặc stack context
Đáp án đúng: D

Câu 12. OpenTelemetry Collector pipeline thường gồm thành phần nào?
A. Sampler, dashboard và index template
B. Agent, shard và data view
C. Router, alert và retention policy
D. Receiver, processor và exporter
Đáp án đúng: D

Câu 13. Đặt processor loại PII trước exporter mang lại lợi ích gì?
A. Loại dữ liệu nhạy cảm trước khi export
B. Backend nhận dữ liệu thô để tự quyết định lọc
C. Exporter tự thay đổi quyền truy cập của nguồn
D. Collector bỏ qua kiểm tra cấu hình pipeline
Đáp án đúng: A

Câu 14. Attributes processor có thể thực hiện thao tác nào?
A. Đặt thời hạn retention cho mọi index
B. Xóa hoặc sửa attribute theo policy
C. Mã hóa ổ đĩa lưu trữ của backend
D. Cấp role cho người dùng Kibana
Đáp án đúng: B

Câu 15. OTTL trong transform processor phù hợp với mục đích nào?
A. Tạo dashboard theo từng giá trị attribute
B. Phục hồi dữ liệu đã bị xóa khỏi backend
C. Đổi hoặc xóa telemetry theo điều kiện
D. Cấp chứng chỉ TLS cho từng receiver
Đáp án đúng: C

Câu 16. Filter processor trong Collector có thể giúp làm gì?
A. Thay thế mọi metric bằng log tương ứng
B. Mã hóa payload sau khi exporter gửi đi
C. Loại telemetry không đạt điều kiện giữ
D. Tăng sampling rate cho mọi trace
Đáp án đúng: C

Câu 17. Redaction theo allowlist có nguyên tắc nào?
A. Giữ mọi trường trừ khi backend báo lỗi
B. Chỉ lọc dữ liệu sau khi người dùng truy vấn
C. Chỉ áp dụng với log, bỏ qua trace và profile
D. Chỉ giữ trường được cho phép rõ ràng
Đáp án đúng: D

Câu 18. Vì sao không nên đưa dữ liệu nhạy cảm vào OpenTelemetry Baggage?
A. Baggage có thể truyền tiếp qua nhiều service
B. Baggage không thể đi cùng trace context
C. Baggage chỉ tồn tại trong tiến trình đầu tiên
D. Baggage tự động mã hóa ở mọi hop mạng
Đáp án đúng: A

Câu 19. TLS cho OTLP giữa collector và backend bảo vệ điều gì?
A. Secret khỏi người có quyền đọc backend
B. Dữ liệu khỏi retention quá dài
C. Dữ liệu khi truyền qua mạng
D. PII khỏi việc ghi vào payload nguồn
Đáp án đúng: C

Câu 20. Mã hóa dữ liệu khi lưu có thay thế việc redaction không?
A. Có, vì mã hóa loại bỏ PII khỏi bản ghi
B. Không; giải mã vẫn để lộ nội dung nhạy cảm
C. Có, nếu backend hỗ trợ tìm kiếm toàn văn
D. Không, nhưng chỉ cần redaction với metric
Đáp án đúng: B

Câu 21. Least privilege khi cấp quyền đọc telemetry nghĩa là gì?
A. Chỉ cấp quyền cần cho vai trò và nhiệm vụ
B. Cấp quyền quản trị cho mọi kỹ sư vận hành
C. Cho mọi người đọc mọi tenant theo mặc định
D. Dùng chung một tài khoản cho mọi pipeline
Đáp án đúng: A

Câu 22. Phân tách tenant trong telemetry giúp kiểm soát rủi ro nào?
A. Ngăn tenant khác truy cập dữ liệu của nhau
B. Tự rút ngắn retention của mọi log
C. Giảm số lượng metric được tạo trong service
D. Đồng bộ timestamp giữa collector độc lập
Đáp án đúng: A

Câu 23. Retention policy nên dựa trên yếu tố nào?
A. Số dashboard được tạo trong tháng gần nhất
B. Tên exporter đang gửi dữ liệu đến backend
C. Dung lượng ổ đĩa còn trống khi triển khai
D. Mục đích, độ nhạy và nghĩa vụ lưu giữ
Đáp án đúng: D

Câu 24. Khi telemetry hết thời hạn lưu giữ, nên làm gì?
A. Xóa theo policy cả bản chính và bản sao
B. Chỉ ẩn dữ liệu khỏi dashboard nhưng giữ nguyên
C. Chuyển dữ liệu hết hạn sang index đang hoạt động
D. Giữ lại vô thời hạn để tìm kiếm tương lai
Đáp án đúng: A

Câu 25. Chia sẻ telemetry với nhà cung cấp cần kiểm tra điều gì?
A. Mục đích, dữ liệu và quyền truy cập
B. Chỉ cần xác nhận định dạng OTLP tương thích
C. Chỉ cần bật TLS trên đường truyền mạng
D. Chỉ cần đổi tên service trước khi gửi đi
Đáp án đúng: A

Câu 26. Audit log cho truy cập telemetry nên ghi thông tin nào?
A. Tên span đã bị sampler loại bỏ khỏi trace
B. Giá trị CPU trung bình của collector mỗi phút
C. Số bucket histogram được tạo trong dashboard
D. Ai truy cập dữ liệu nào và vào thời điểm nào
Đáp án đúng: D

Câu 27. Phát hiện secret đã xuất vào log cần xử lý gì trước?
A. Giữ nguyên token và xóa cảnh báo phát hiện
B. Thu hồi secret và hạn chế truy cập log
C. Chuyển log sang tenant khác rồi dùng token tiếp
D. Chỉ đổi tên field để secret khó tìm hơn
Đáp án đúng: B

Câu 28. Classification label gắn vào telemetry nên phục vụ mục đích gì?
A. Truyền mức phân loại để áp policy nhất quán
B. Thay thế mọi attribute nghiệp vụ của ứng dụng
C. Tạo một time series mới cho mỗi người dùng
D. Chứa nội dung đầy đủ của dữ liệu nhạy cảm
Đáp án đúng: A

Câu 29. Vì sao cần đánh giá lại phân loại telemetry định kỳ?
A. Nguồn và rủi ro dữ liệu có thể đổi
B. Tên metric luôn tự đổi sau mỗi lần scrape
C. Retention policy không thể được chỉnh sửa
D. TLS certificate buộc phân loại đổi mỗi tháng
Đáp án đúng: A

Câu 30. Pipeline nhận telemetry thiếu nhãn phân loại nên xử lý thế nào?
A. Đưa dữ liệu chưa phân loại vào tenant công khai
B. Áp dụng policy mặc định an toàn khi thiếu nhãn
C. Tự gán mức công khai nếu không có metadata
D. Cho exporter tự bỏ qua mọi policy bảo vệ
Đáp án đúng: B

Câu 31. Kiểm thử quy tắc bảo vệ telemetry nên xác minh điều gì?
A. Mọi loại telemetry có cùng kích thước payload
B. Backend luôn nhận đủ mọi trường từ nguồn
C. Số lượng trường luôn tăng sau processor
D. PII và secret mẫu được che trước export
Đáp án đúng: D

Câu 32. Một trường cần cho điều tra nhưng chứa PII nên xử lý ra sao?
A. Giữ nguyên PII ở mọi bản sao để tiện tra cứu
B. Giữ dạng giảm định danh nếu vẫn đủ mục đích
C. Xóa toàn bộ telemetry của dịch vụ liên quan
D. Đưa PII vào tên index để hạn chế truy vấn
Đáp án đúng: B
