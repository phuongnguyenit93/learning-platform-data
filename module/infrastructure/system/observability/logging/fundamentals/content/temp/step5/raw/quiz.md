Câu 01. Khi nào mức INFO phù hợp hơn DEBUG trong log ứng dụng?
A. Ghi toàn bộ biến cục bộ mỗi lần xử lý request thành công.
B. Ghi sự kiện khởi động và thay đổi trạng thái dịch vụ.
C. Ghi từng vòng lặp nội bộ khi tìm nguyên nhân lỗi hiếm.
D. Ghi payload thô của mọi request để theo dõi chi tiết.
Đáp án đúng: B

Câu 02. Dịch vụ gọi API phụ bị timeout nhưng có thể retry thành công. Mức log nào thường phù hợp?
A. INFO cho mọi timeout vì đã có cơ chế retry ở phía client.
B. ERROR cho mọi lần retry dù yêu cầu cuối vẫn thành công.
C. DEBUG cho tất cả lỗi mà không cần biết tác động người dùng.
D. WARN cho sự cố tạm thời đã có phương án hồi phục.
Đáp án đúng: D

Câu 03. Trong một hệ thống có TRACE, mức TRACE thường dành cho nội dung nào?
A. Chỉ các sự kiện nghiệp vụ bắt buộc lưu trữ dài hạn.
B. Chỉ các mốc triển khai phiên bản để đo uptime.
C. Chi tiết từng bước khi điều tra lỗi khó xác định.
D. Chỉ thông báo lỗi ngừng phục vụ cần báo trực ngay.
Đáp án đúng: C

Câu 04. Structured logging dạng JSON hữu ích nhất vì lý do nào?
A. Giúp mọi log tự động được mã hóa trên đường truyền.
B. Giúp ngăn hoàn toàn việc ghi dữ liệu nhạy cảm vào log.
C. Giúp backend khỏi cần gắn timestamp cho sự kiện.
D. Cho phép lọc, đếm theo field thay vì tách message.
Đáp án đúng: D

Câu 05. Vì sao nên có trường event_name ổn định cho các log cùng loại?
A. Giúp thay thời gian hệ thống bằng chuỗi tên sự kiện.
B. Giúp thay thế hoàn toàn trace_id trong luồng phân tán.
C. Giúp tìm đúng loại sự kiện dù câu thông báo thay đổi.
D. Giúp mọi log khác severity đều có cùng mức ưu tiên.
Đáp án đúng: C

Câu 06. Khi đặt tên field trong log JSON, nguyên tắc nào cải thiện truy vấn?
A. Giữ tên và kiểu dữ liệu nhất quán giữa các phiên bản.
B. Đưa mọi thuộc tính vào một chuỗi message duy nhất.
C. Đặt tất cả giá trị dưới dạng số dù vốn là chuỗi.
D. Đổi tên field theo từng request để tránh đụng khóa JSON.
Đáp án đúng: A

Câu 07. Cách ghi timestamp nào thuận tiện để tương quan log nhiều vùng thời gian?
A. Dùng định dạng có timezone rõ ràng, thường chuẩn UTC.
B. Chỉ ghi giờ phút giây theo múi giờ local của từng máy.
C. Chỉ ghi số giây đã chạy kể từ lúc process khởi động.
D. Chỉ dùng thời gian của trình duyệt khi request kết thúc.
Đáp án đúng: A

Câu 08. Nếu đồng hồ giữa các node lệch nhau, điều gì dễ xảy ra khi tra log?
A. Sắp theo tên pod bảo đảm thứ tự gọi giữa nhiều service.
B. Chỉ cần ingestion timestamp là đủ khôi phục thứ tự sự kiện.
C. Thứ tự sự kiện có thể sai khi ghép log giữa các node.
D. Dùng severity để sắp xếp log sẽ khôi phục thứ tự thực tế.
Đáp án đúng: C

Câu 09. Trong pipeline log, event timestamp khác ingestion timestamp thế nào?
A. Event ghi lúc xóa log; ingestion ghi lúc dashboard mở.
B. Event ghi lúc lưu backup; ingestion ghi lúc cấp quyền.
C. Event ghi lúc tìm kiếm; ingestion ghi lúc ứng dụng bắt đầu.
D. Event ghi lúc phát sinh; ingestion ghi lúc hệ thống nhận.
Đáp án đúng: D

Câu 10. Để liên kết log gateway và backend của cùng request, cần gì?
A. Chỉ dùng cùng hostname cho tất cả pod backend.
B. Chỉ ghi một dòng log tổng hợp cho cả cụm gateway.
C. Đặt severity của mọi request về cùng một giá trị.
D. Truyền cùng một request ID qua các hop dịch vụ.
Đáp án đúng: D

Câu 11. trace_id và span_id trong structured log hỗ trợ việc gì?
A. Thay toàn bộ metric độ trễ của từng dịch vụ.
B. Thay chứng chỉ TLS khi xác thực từng kết nối nội bộ.
C. Liên hệ log với trace, span của một yêu cầu.
D. Thay mã lỗi HTTP do backend trả cho client cuối.
Đáp án đúng: C

Câu 12. Khi nhận request_id từ client ngoài Internet, ứng dụng nên làm gì?
A. Kiểm tra ID đầu vào trước khi dùng làm ngữ cảnh log.
B. Ghi nguyên mọi giá trị không giới hạn vào tên file log.
C. Xem request_id như token xác thực người dùng hiện tại.
D. Tin mọi chuỗi client gửi để cấp quyền đọc log production.
Đáp án đúng: A

Câu 13. Trong tác vụ async, vì sao MDC hoặc logging context có thể bị thiếu?
A. Logger tự xóa các field khi response có HTTP status 200.
B. JSON encoder luôn loại bỏ request_id ở thread khác.
C. Context không tự lan qua mọi thread nếu không được truyền.
D. Collector tự bỏ mọi log sinh ra sau khi request trả về.
Đáp án đúng: C

Câu 14. Trong log thao tác đặt hàng, tập field nào giúp chẩn đoán mà vẫn an toàn?
A. Email, số điện thoại và địa chỉ đầy đủ của mọi người mua.
B. event_name, order_id nội bộ, status và correlation_id.
C. password, access_token, cookie phiên và toàn bộ thẻ thanh toán.
D. Toàn bộ request body cùng session secret chưa che thông tin.
Đáp án đúng: B

Câu 15. Lợi ích của parameterized logging thay vì nối chuỗi ngay khi gọi DEBUG là gì?
A. Giúp tự động tạo distributed trace cho mọi lệnh DEBUG.
B. Giúp bỏ hoàn toàn nhu cầu lọc dữ liệu nhạy cảm.
C. Trì hoãn dựng message khi mức DEBUG đang bị tắt.
D. Buộc logger luôn thực thi format dù không ghi dòng nào.
Đáp án đúng: C

Câu 16. Khi một exception đi qua nhiều tầng ứng dụng, nên log thế nào để giảm trùng lặp?
A. Ghi stack trace tại ranh giới xử lý với ngữ cảnh đủ.
B. Ghi stack trace đầy đủ ở tất cả tầng rồi giữ nguyên.
C. Ghi lỗi dưới nhiều request_id khác nhau ở mỗi tầng.
D. Bỏ stack trace hoàn toàn và chỉ ghi HTTP status.
Đáp án đúng: A

Câu 17. Vì sao nên giảm log thành công của health-check endpoint?
A. Các request lặp nhanh dễ tạo nhiễu và tăng chi phí.
B. Log health-check sẽ làm sai timestamp của trace.
C. Mọi request health-check đều là lỗi nên cần giấu.
D. Collector không thể thu thập log có status 200.
Đáp án đúng: A

Câu 18. Khi một lỗi giống nhau lặp hàng nghìn lần mỗi phút, nên cân nhắc gì?
A. Chỉ chuyển mọi log lỗi thành TRACE để tắt cảnh báo.
B. Chỉ ghi lại lần cuối mà không lưu số lượng lần lỗi.
C. Chỉ tăng mức verbosity để thu thêm log giống nhau.
D. Rate-limit hoặc gom sự kiện và đếm số lần bị lặp.
Đáp án đúng: D

Câu 19. Khi sampling log ở lưu lượng cao, loại sự kiện nào cần đặc biệt tránh bỏ sót?
A. Request thành công định kỳ vốn đã có metric tổng hợp.
B. Log DEBUG ở vòng lặp chỉ dùng khi điều tra ngắn hạn.
C. Log heartbeat trùng nhau không có thêm ngữ cảnh.
D. Audit event và lỗi nghiêm trọng cần giữ đầy đủ.
Đáp án đúng: D

Câu 20. Thay đổi log level tại runtime cần lưu ý rủi ro nào?
A. Đổi mức log khiến toàn bộ metric bị xóa khỏi storage.
B. Bật DEBUG rộng có thể tăng tải và lộ dữ liệu ngoài ý muốn.
C. Đổi DEBUG thành INFO luôn làm chậm request hơn trước.
D. Đổi log level tự làm mới certificate cho mọi collector.
Đáp án đúng: B

Câu 21. Trong ứng dụng container Kubernetes, vì sao thường ghi log ra stdout/stderr?
A. Runtime thu stream để agent tập trung chuyển log đi.
B. stderr giúp tự chuyển mọi exception thành alert firing.
C. stdout cho phép bỏ mọi tầng lưu trữ log tập trung.
D. Pod dùng stdout để bảo đảm log được giữ vĩnh viễn.
Đáp án đúng: A

Câu 22. Tại sao chỉ dựa vào file log nằm trong container là rủi ro?
A. File log trong container luôn được nhân bản sang mọi node.
B. File log khiến HTTP header của ứng dụng thay đổi.
C. Container không thể đọc file log đã được ứng dụng ghi.
D. Container bị thay có thể làm mất log chưa gửi đi.
Đáp án đúng: D

Câu 23. Collector bổ sung namespace, pod và service vào sự kiện nhằm mục đích nào?
A. Biến mọi log ERROR thành cảnh báo dù không có rule.
B. Cho phép lọc log theo workload và môi trường chạy.
C. Thay timestamp sự kiện bằng thời gian pod được tạo.
D. Giúp collector tự xác định nguyên nhân gốc chỉ theo pod.
Đáp án đúng: B

Câu 24. Một node agent thu log và gửi tới hệ lưu trữ tập trung làm nhiệm vụ nào?
A. Đọc, xử lý và forward sự kiện qua pipeline ingest.
B. Chỉ gom log vào volume chung mà không ship qua mạng.
C. Chỉ tách log theo pod rồi bỏ qua retry khi gửi đi.
D. Chỉ nén log và xóa file trước khi nhận ACK phía đích.
Đáp án đúng: A

Câu 25. Với Java stack trace gồm nhiều dòng, collector cần lưu ý gì?
A. Gộp đúng các dòng của cùng một sự kiện lỗi.
B. Tách từng dòng thành request độc lập không có ngữ cảnh.
C. Chỉ giữ dòng đầu vì các dòng sau luôn trùng nội dung.
D. Gộp mọi stack trace của cùng service vào một event.
Đáp án đúng: A

Câu 26. Khi schema JSON thay đổi và parser bắt đầu lỗi, nên xử lý thế nào?
A. Xóa timestamp ở bản ghi để collector tự đoán schema.
B. Kiểm tra trường thay đổi và định tuyến bản ghi lỗi riêng.
C. Âm thầm bỏ mọi bản ghi không parse mà không đo số lượng.
D. Đổi mọi trường về chuỗi rỗng rồi coi dữ liệu vẫn hợp lệ.
Đáp án đúng: B

Câu 27. Pipeline logging bị backlog tăng khi storage đích chậm. Cần đo gì?
A. Chỉ thời gian mở trang dashboard của một người dùng.
B. Chỉ số request HTTP thành công từ gateway công khai.
C. Độ trễ ingest, queue, retry và tỷ lệ sự kiện bị mất.
D. Chỉ bộ nhớ heap của ứng dụng không liên quan luồng log.
Đáp án đúng: C

Câu 28. Với cơ chế gửi log at-least-once, tình huống nào có thể xảy ra?
A. Mỗi sự kiện chỉ được gửi một lần dù có lỗi mạng.
B. Mọi log mất khi receiver phản hồi thành công HTTP 200.
C. Collector tự xóa log nếu không có field severity.
D. Retry khiến một sự kiện được lưu trùng nếu đã nhận trước.
Đáp án đúng: D

Câu 29. Vì sao buffer ghi xuống disk ở collector hữu ích khi mất kết nối ngắn?
A. Buộc ứng dụng ngừng trả response cho mọi request.
B. Giữ log tạm để gửi lại sau thay vì chỉ dựa vào RAM.
C. Đảm bảo log luôn được nhận đúng một lần tuyệt đối.
D. Thay việc kiểm tra quota và dung lượng đĩa của node.
Đáp án đúng: B

Câu 30. Khi điều tra lỗi chỉ xảy ra ở production, cách lọc log nào hiệu quả?
A. Chỉ lọc mọi dòng có chữ error rồi bỏ qua thời điểm.
B. Chỉ xem bản ghi lâu nhất bất kể môi trường chạy.
C. Thu hẹp thời gian, service, version và correlation ID.
D. Chỉ tìm toàn bộ log của mọi namespace trong một năm.
Đáp án đúng: C

Câu 31. Vì sao nên lưu latency và status dưới các field riêng thay vì trong message?
A. Cho phép bỏ timestamp khi truy vấn theo mức INFO.
B. Cho phép parser đoán mọi field thiếu trong schema.
C. Cho phép lọc theo điều kiện và tính thống kê theo trường.
D. Cho phép ghi ít log hơn mà không cần điều chỉnh sampling.
Đáp án đúng: C

Câu 32. Với Loki, dùng request_id làm label cho từng request gây rủi ro gì?
A. Làm thay đổi thứ tự HTTP request do kernel chọn.
B. Tạo quá nhiều stream do cardinality label rất cao.
C. Không thể tìm request_id trong nội dung log nếu không gắn label.
D. Tự động xóa toàn bộ log được gửi từ nhiều namespace.
Đáp án đúng: B

Câu 33. Khi đối chiếu log với biểu đồ tỷ lệ lỗi tăng, bước nào hữu ích?
A. Chỉ xem mọi dòng DEBUG ở một môi trường development.
B. Chỉ xem lỗi đầu tiên trong ngày mà bỏ qua mốc tăng.
C. Chọn khoảng thời gian và nhóm service bị ảnh hưởng để tìm log.
D. Chỉ tìm log của service không có traffic trong khoảng đó.
Đáp án đúng: C

Câu 34. Log-based metric đếm số lỗi parse phù hợp nhất khi nào?
A. Khi cần chứng minh pipeline đã thu đủ mọi log không mất.
B. Khi cần tổng hợp số sự kiện từ log có cấu trúc ổn định.
C. Khi cần thay mọi metric trực tiếp bằng truy vấn full-text.
D. Khi cần tính chính xác số CPU core đang chạy trên node.
Đáp án đúng: B

Câu 35. Với audit log cho thay đổi quyền truy cập, điều nào quan trọng?
A. Chỉ lưu tại bộ nhớ của pod để tránh rò rỉ nội dung.
B. Ghi chủ thể, hành động, kết quả và bảo vệ tính toàn vẹn.
C. Chỉ ghi số dòng log đã tạo rồi bỏ thông tin thao tác.
D. Cho người được audit tự xóa bản ghi để giảm lưu trữ.
Đáp án đúng: B

Câu 36. Trước khi ghi HTTP request, nên xử lý Authorization header thế nào?
A. Loại bỏ hoặc che token, chỉ giữ metadata cần chẩn đoán.
B. Gắn token vào log label để tìm nhanh mỗi tài khoản.
C. Mã hóa Base64 token rồi coi như đã không còn nhạy cảm.
D. Ghi nguyên bearer token để tiện tái hiện request sau này.
Đáp án đúng: A

Câu 37. Vì sao hash email trong log chưa chắc khiến dữ liệu vô danh?
A. Hash có thể bị liên kết hoặc đoán lại từ tập giá trị nhỏ.
B. Hash luôn bảo đảm không ai liên hệ lại tới chủ thể gốc.
C. Hash khiến collector bỏ qua hoàn toàn mọi quy định privacy.
D. Hash tự động xóa dữ liệu gốc khỏi mọi bản sao log.
Đáp án đúng: A

Câu 38. Khi cấp quyền vào hệ tìm kiếm log, nguyên tắc nào phù hợp?
A. Dùng một tài khoản admin chung cho tất cả nhóm vận hành.
B. Cấp quyền xem toàn bộ log cho mọi tài khoản phát triển.
C. Cho mọi người tải log chứa thông tin khách hàng để debug.
D. Phân quyền tối thiểu theo vai trò và phạm vi dữ liệu.
Đáp án đúng: D

Câu 39. Để giảm chi phí lưu log dài hạn nhưng vẫn phục vụ sự cố, nên làm gì?
A. Xóa mọi log ERROR sau vài phút bất kể chính sách.
B. Đặt retention theo nhóm log và yêu cầu lưu giữ.
C. Tắt hoàn toàn log ứng dụng và chỉ xem CPU metric.
D. Giữ mọi log DEBUG ở storage nóng vô thời hạn.
Đáp án đúng: B

Câu 40. Kiểm thử end-to-end pipeline log sau thay đổi cấu hình nên xác minh gì?
A. Chỉ kiểm tra ứng dụng khởi động mà không tra kho log.
B. Chỉ xác minh collector chạy mà không kiểm tra log đã lưu.
C. Chỉ xem số dòng có tăng, bỏ qua parsing và quyền đọc.
D. Kiểm tra field, tìm kiếm, lộ secret và ingest lag.
Đáp án đúng: D
