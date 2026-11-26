Câu 01. Loki khác hệ tìm kiếm log truyền thống ở cách lập chỉ mục nào?
A. Chỉ mục toàn bộ token trong message trước khi lưu chunk log.
B. Chỉ mục chủ yếu theo labels của stream, không index từng dòng log.
C. Chỉ mục từng byte của stack trace để truy vấn trực tiếp nhanh hơn.
D. Chỉ mục duy nhất theo timestamp, bỏ qua mọi label của stream.
Đáp án đúng: B

Câu 02. Label nào thường phù hợp để phân loại log trong Loki?
A. timestamp_ms, random_uuid và raw_url riêng cho từng request.
B. service, environment và cluster với số giá trị hữu hạn.
C. request_id, user_id và session_id có giá trị thay đổi liên tục.
D. full_message, stack_trace và payload có nội dung không giới hạn.
Đáp án đúng: B

Câu 03. Vì sao không nên đặt request_id làm label của Loki?
A. Mỗi request tạo stream riêng, làm cardinality tăng mạnh.
B. Loki chỉ cho phép label có kiểu số nguyên và không nhận chuỗi.
C. Request ID làm timestamp của mọi dòng log bị thay đổi.
D. Request ID sẽ bị xóa khỏi log line khi collector gửi dữ liệu.
Đáp án đúng: A

Câu 04. Khi cần giữ user_id có cardinality cao để điều tra, nên làm gì?
A. Đưa user_id vào tên tenant để mỗi người dùng có index riêng.
B. Tạo một label mới cho từng user rồi xóa sau mỗi truy vấn.
C. Đưa user_id vào structured metadata thay cho indexed label.
D. Đưa user_id vào tên stream để Loki tự giới hạn số giá trị.
Đáp án đúng: C

Câu 05. Một Loki stream được xác định chủ yếu bởi yếu tố nào?
A. Truy vấn LogQL gần nhất đã đọc stream đó.
B. Bộ label cùng giá trị xác định một stream.
C. Nội dung của dòng log đầu tiên trong một chunk.
D. Tên file cấu hình Alloy đang thu thập log.
Đáp án đúng: B

Câu 06. Một LogQL query thường bắt đầu bằng thành phần nào?
A. Một hàm unwrap không có selector để tự tìm mọi stream.
B. Một biểu thức SQL dùng chọn bảng log trong object storage.
C. Log stream selector trong cặp ngoặc nhọn với label matcher.
D. Một pipeline stage json trước khi xác định stream cần đọc.
Đáp án đúng: C

Câu 07. Trong LogQL, toán tử |= thường được dùng để làm gì?
A. Lọc các stream theo giá trị label được lập chỉ mục.
B. Chọn log line có chứa chuỗi literal đã chỉ định.
C. Chuyển trường JSON đã parse thành một metric số.
D. Đổi nhãn stream thành giá trị có trong dòng log.
Đáp án đúng: B

Câu 08. Toán tử |~ trong LogQL khác |= ở điểm nào?
A. |~ tính tốc độ xuất hiện của chuỗi theo mỗi giây.
B. |~ chỉ so khớp label đã index, không đọc log line.
C. |~ lọc dòng bằng biểu thức chính quy thay vì chuỗi literal.
D. |~ chuyển dòng log sang định dạng JSON trước khi lọc.
Đáp án đúng: C

Câu 09. Pipeline stage | json trong LogQL chủ yếu thực hiện việc gì?
A. Giải nén chunk lưu trữ trước khi chọn tenant của query.
B. Đổi toàn bộ log line thành metric counter trong Loki.
C. Chuyển mọi label hiện có thành một JSON object duy nhất.
D. Parse JSON trong log line thành các extracted fields.
Đáp án đúng: D

Câu 10. Khi log Java dùng định dạng key=value, stage nào có thể parse phù hợp?
A. Dùng | json vì logfmt và JSON có cùng cú pháp dấu ngoặc.
B. Dùng | unwrap để phân tích mọi cặp key=value thành số.
C. Dùng | line_format để tự nhận diện cấu trúc key=value.
D. Dùng | logfmt để trích xuất các trường theo định dạng đó.
Đáp án đúng: D

Câu 11. Hàm count_over_time trong LogQL trả về điều gì?
A. Độ trễ trung bình từ lúc Alloy gửi tới Loki.
B. Đếm log entry khớp trong cửa sổ thời gian đã chọn.
C. Tổng số byte đã lưu trong object storage của tenant.
D. Số lượng label khác nhau có trong toàn bộ stream.
Đáp án đúng: B

Câu 12. Trong truy vấn metric từ log, rate thường biểu thị đại lượng nào?
A. Tốc độ log entry xuất hiện trung bình mỗi giây trong range.
B. Tỷ lệ nén chunk sau khi compactor xử lý dữ liệu.
C. Số byte còn trống trên filesystem của ingester.
D. Tỷ lệ phần trăm label có giá trị duy nhất trong stream.
Đáp án đúng: A

Câu 13. LogQL unwrap thường được dùng khi nào?
A. Chuyển label thành tenant ID trước khi truy vấn dữ liệu.
B. Giải mã stack trace nhiều dòng thành một log entry.
C. Loại bỏ mọi label không xuất hiện trong dashboard.
D. Đổi extracted field số thành sample cho phép tính.
Đáp án đúng: D

Câu 14. Muốn lọc theo status đã parse từ JSON, cách viết nào phù hợp?
A. Parse JSON trước rồi lọc extracted field status.
B. Dùng unwrap status trước khi parse nội dung JSON.
C. Chỉ dùng selector {status="500"} dù status chưa là label.
D. Dùng |= "status" để so sánh chính xác giá trị số.
Đáp án đúng: A

Câu 15. Trong LogQL, lọc chuỗi đơn giản trước parser thường có lợi gì?
A. Chuyển line filter thành index lookup có sẵn trong Loki.
B. Đảm bảo mọi kết quả query đều được cache vĩnh viễn.
C. Buộc parser nhận diện được mọi schema log chưa biết.
D. Giảm số dòng cần parse và thường làm query nhẹ hơn.
Đáp án đúng: D

Câu 16. Log Java có stack trace nhiều dòng cần xử lý thế nào khi ingest?
A. Gom các dòng thuộc cùng exception thành một log event.
B. Tạo một stream mới cho từng dòng trong stack trace.
C. Đưa mỗi dòng stack trace thành một label riêng biệt.
D. Loại bỏ các dòng tiếp theo sau dòng đầu của exception.
Đáp án đúng: A

Câu 17. Grafana Alloy đảm nhiệm vai trò nào trong kiến trúc Loki?
A. Đánh giá alert rule trong Loki và gửi email trực tiếp.
B. Alloy thu thập, xử lý log và chuyển chúng tới Loki endpoint.
C. Lập chỉ mục stream và lưu chunk log trong object storage.
D. Truy vấn LogQL rồi render panel dashboard cho Grafana.
Đáp án đúng: B

Câu 18. Trong Alloy, component loki.source.kubernetes thường dùng để làm gì?
A. Thu log từ workload Kubernetes theo cấu hình nguồn.
B. Chuyển đổi log line thành truy vấn LogQL cho dashboard.
C. Tạo bucket object storage và đặt retention cho tenant.
D. Đẩy log đã xử lý tới endpoint ghi dữ liệu của Loki.
Đáp án đúng: A

Câu 19. Khi Alloy đọc log từ file trên node, component nào thường phù hợp?
A. Dùng loki.write để tail file và lưu vị trí đọc.
B. Dùng loki.process để mở file và khám phá pod Kubernetes.
C. Dùng discovery.relabel để tự đọc nội dung file log.
D. Dùng loki.source.file để tail file log được cấu hình.
Đáp án đúng: D

Câu 20. discovery.kubernetes trong Alloy thường cung cấp thông tin gì?
A. Query result và label cardinality từ Grafana dashboard.
B. Cung cấp target và metadata Kubernetes cho pipeline.
C. Nội dung đầy đủ của mọi container log trong cluster.
D. Index schema và vị trí chunk hiện lưu trên Loki.
Đáp án đúng: B

Câu 21. Component loki.process trong Alloy thường dùng để làm gì?
A. Phục vụ truy vấn LogQL và trả dữ liệu cho Grafana.
B. Quản lý dashboard, alert contact point và data source.
C. Khởi tạo tenant, ring và replication factor của Loki.
D. Áp dụng stage để parse, xử lý multiline, relabel và lọc log.
Đáp án đúng: D

Câu 22. Component loki.write có vai trò nào trong pipeline Alloy?
A. Đọc log file từ pod và quản lý vị trí tail trên node.
B. Parse JSON, ghép multiline và tạo Kubernetes metadata.
C. Gửi log đã xử lý tới một hoặc nhiều Loki endpoint.
D. Hiển thị log stream thành panel trong Grafana Explore.
Đáp án đúng: C

Câu 23. Vì sao collector cần lưu trạng thái vị trí đã đọc file?
A. Giúp Kubernetes giữ nguyên IP pod sau mỗi lần rollout.
B. Giúp Loki xác định label nào cần index trong mỗi chunk.
C. Giúp Grafana khôi phục biến dashboard sau khi refresh.
D. Tiếp tục tail file từ offset đã checkpoint sau restart.
Đáp án đúng: D

Câu 24. Khi parse log JSON lỗi trong LogQL, trường __error__ hữu ích ra sao?
A. Đại diện cho số lần Loki retry ghi chunk vào storage.
B. Đánh dấu log line đã bị xóa theo retention policy.
C. Chứa HTTP status cuối cùng do ứng dụng trả về client.
D. Báo lỗi phát sinh ở một stage trong pipeline xử lý.
Đáp án đúng: D

Câu 25. Nên xử lý password hoặc token nhạy cảm ở đâu trong pipeline log?
A. Chỉ ẩn ở dashboard vì log gốc trong Loki vẫn an toàn.
B. Base64 dữ liệu trước khi ghi rồi xem như đã được bảo vệ.
C. Che hoặc loại bỏ token trước khi gửi log tới Loki.
D. Đưa token vào label riêng để giới hạn người có thể truy vấn.
Đáp án đúng: C

Câu 26. Trong kiến trúc Loki phân tán, distributor thường đảm nhiệm việc gì?
A. Nhận log push, kiểm tra và định tuyến tới ingester.
B. Thu log stdout của pod bằng Kubernetes API.
C. Lưu trữ lâu dài mọi chunk và index trên object storage.
D. Thực thi LogQL và trả kết quả cuối cho Grafana.
Đáp án đúng: A

Câu 27. Ingester trong Loki chịu trách nhiệm chính nào?
A. Đọc file trên node rồi gắn label Kubernetes vào log.
B. Nhận log, gom thành chunk và ghi theo cấu hình lưu trữ.
C. Xác thực người dùng Grafana và cấp quyền folder.
D. Phân tích dashboard và tính toán biến truy vấn Grafana.
Đáp án đúng: B

Câu 28. WAL của ingester giúp ích gì khi tiến trình gặp sự cố?
A. Giữ lịch sử truy vấn LogQL của từng người dùng Grafana.
B. Thay thế replication giữa các ingester ở nhiều vùng.
C. Khôi phục các log đã nhận nhưng chưa flush thành công.
D. Lưu cấu hình dashboard khi Grafana bị restart.
Đáp án đúng: C

Câu 29. Querier của Loki thường làm nhiệm vụ nào?
A. Querier đọc index cùng chunk liên quan để thực thi LogQL query.
B. Đặt retention period và xóa dữ liệu hết hạn khỏi bucket.
C. Nhận log mới từ Alloy rồi chia đều sang các ingester.
D. Phát hiện file log mới trên filesystem của Kubernetes node.
Đáp án đúng: A

Câu 30. Trong triển khai Loki dùng object storage, dữ liệu nào thường được lưu ở đó?
A. Chỉ file positions của Alloy và trạng thái pod Kubernetes.
B. Lưu chunk log cùng index theo schema đã cấu hình.
C. Chỉ cache kết quả query còn mọi log nằm trong RAM.
D. Chỉ dashboard JSON và datasource YAML của Grafana.
Đáp án đúng: B

Câu 31. Compactor trong Loki thường tham gia nhiệm vụ nào?
A. Xử lý index và thực thi retention hoặc xóa dữ liệu hết hạn.
B. Thu log từ stdout và gắn nhãn namespace cho từng dòng.
C. Chuyển truy vấn LogQL thành PromQL trước khi chạy.
D. Đồng bộ user account giữa Grafana và Kubernetes.
Đáp án đúng: A

Câu 32. Muốn bật retention cho Loki dùng object storage, cần chú ý gì?
A. Cấu hình retention cùng compactor và cơ chế xóa phù hợp.
B. Chỉ đặt lifecycle bucket mà không xét index và compactor.
C. Chỉ giảm TTL của Grafana dashboard để log tự hết hạn.
D. Chỉ xóa label cũ khỏi stream để chunk được tự động xóa.
Đáp án đúng: A

Câu 33. Trong Loki multi-tenant, X-Scope-OrgID thường được dùng làm gì?
A. Chỉ định label bắt buộc để mọi log stream được lập chỉ mục.
B. Chọn tenant đích cho request đọc hoặc ghi dữ liệu Loki.
C. Chỉ định user đăng nhập Grafana cho mỗi dashboard.
D. Chỉ định tên bucket object storage của một cluster Kubernetes.
Đáp án đúng: B

Câu 34. Vì sao không nên để client tùy ý tự gửi X-Scope-OrgID tới Loki?
A. Header này chỉ được dùng để nén log trước khi gửi đi.
B. Tenant ID quyết định timestamp nên client sẽ làm sai thứ tự log.
C. Gateway xác thực tenant để ngăn truy cập chéo.
D. Loki tự bỏ qua header nếu request được gửi qua HTTPS.
Đáp án đúng: C

Câu 35. Replication factor trong Loki phân tán chủ yếu giúp ích gì?
A. Chia mỗi log line thành nhiều tenant độc lập.
B. Tạo nhiều bản sao dashboard cho các Grafana user khác nhau.
C. Giữ bản sao log trên nhiều ingester để chịu lỗi.
D. Nhân số label trong index để query chạy nhanh hơn.
Đáp án đúng: C

Câu 36. Grafana Explore thường được dùng trong quy trình nào?
A. Chạy LogQL tương tác để tìm và điều tra log stream.
B. Tail file container trên node và cập nhật positions Alloy.
C. Đặt retention và compaction policy của object storage.
D. Quản lý ring membership và replication của Loki ingester.
Đáp án đúng: A

Câu 37. Khi tạo alert từ Loki, loại truy vấn nào thường phù hợp?
A. Chỉ mở Explore mà không chạy truy vấn LogQL.
B. Truy vấn danh sách label rồi cảnh báo khi có label mới.
C. Dùng LogQL metric query theo cửa sổ thời gian.
D. Truy vấn cấu hình Alloy và cảnh báo khi file thay đổi.
Đáp án đúng: C

Câu 38. Một dashboard Loki có nhiều service, biến nào giúp lọc linh hoạt?
A. Biến đổi trực tiếp tenant ID sau khi query đã chạy xong.
B. Biến chứa request_id riêng cho từng log line đã ingest.
C. Lọc dashboard bằng variable dựa trên service hoặc namespace.
D. Biến lưu toàn bộ nội dung stack trace trong URL dashboard.
Đáp án đúng: C

Câu 39. Khi LogQL query chậm trên dữ liệu lớn, bước tối ưu nào nên thử trước?
A. Tăng số panel trên dashboard để chia nhỏ kết quả.
B. Xóa line filter để Loki phải đọc thêm nhiều log hơn.
C. Thêm request_id làm label cho mọi stream đang lưu.
D. Thu hẹp time range và chọn selector có label phù hợp.
Đáp án đúng: D

Câu 40. Muốn giảm chi phí lưu Loki mà vẫn giữ khả năng điều tra, nên làm gì?
A. Giữ mọi log DEBUG vô hạn trong storage nóng có tốc độ cao.
B. Tạo label mới cho mỗi request để giảm kích thước chunk.
C. Tắt compression để giảm CPU mà không xét chi phí lưu trữ.
D. Giảm log nhiễu, đặt retention hợp lý và chọn storage tier.
Đáp án đúng: D
