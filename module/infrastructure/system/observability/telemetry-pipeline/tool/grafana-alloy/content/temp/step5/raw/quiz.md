Câu 01. Grafana Alloy nằm ở lớp nào trong kiến trúc observability?
A. Lớp lưu trữ dài hạn đứng giữa index và object storage.
B. Lớp dashboard đứng giữa người dùng và truy vấn dữ liệu.
C. Lớp thu thập và xử lý giữa nguồn telemetry và backend.
D. Lớp instrument nằm trong từng thư viện ứng dụng.
Đáp án đúng: C

Câu 02. Component graph trong cấu hình Alloy thể hiện điều gì?
A. Quan hệ dữ liệu từ component nguồn qua xử lý tới đích.
B. Danh sách dashboard sử dụng cùng một data source.
C. Thứ tự file cấu hình được đọc từ thư mục cài đặt.
D. Quan hệ phụ thuộc giữa các pod Kubernetes trong cluster.
Đáp án đúng: A

Câu 03. Trong River, hai component cùng loại cần được phân biệt bằng gì?
A. Tên file YAML cùng namespace Kubernetes hiện tại.
B. Tên service và version lấy từ biến môi trường.
C. Tên component và label định danh trong cấu hình.
D. Địa chỉ IP và port của backend nhận telemetry.
Đáp án đúng: C

Câu 04. Tham chiếu tới trường output của component thường dùng để làm gì?
A. Đọc lại toàn bộ nội dung cấu hình của component nguồn.
B. Đưa target hoặc dữ liệu đã xuất sang component kế tiếp.
C. Tự khởi động lại component nếu receiver đích ngừng hoạt động.
D. Tạo bản sao cấu hình cho mọi Alloy instance trong cluster.
Đáp án đúng: B

Câu 05. discovery.kubernetes thường cung cấp loại dữ liệu nào cho pipeline?
A. Trace spans đã batch và gắn resource attributes.
B. Metric samples đã scrape và sẵn sàng remote write.
C. Targets kèm metadata Kubernetes theo role được chọn.
D. Log events đã parse từ mọi container trong namespace.
Đáp án đúng: C

Câu 06. discovery.relabel thường được đặt ở đâu trong metrics pipeline?
A. Trước Kubernetes API để thay đổi nhãn của Pod.
B. Sau khi dashboard truy vấn xong để đổi legend.
C. Lọc hoặc sửa target metadata trước khi scrape metrics.
D. Sau remote write để sửa mẫu đã lưu ở backend.
Đáp án đúng: C

Câu 07. prometheus.relabel khác discovery.relabel ở điểm nào?
A. Xử lý metric samples sau scrape, không sửa discovery targets.
B. Nó chỉ lọc Kubernetes namespaces trước khi tìm targets.
C. Nó chuyển metric samples thành log events trước khi ghi.
D. Nó định tuyến trace spans dựa trên resource attributes.
Đáp án đúng: A

Câu 08. Muốn chỉ scrape các target có nhãn môi trường production, action nào phù hợp?
A. Dùng keep với matcher cho nhãn môi trường tương ứng.
B. Dùng hashmod để mã hóa toàn bộ target label set.
C. Dùng drop để loại mọi target có nhãn production.
D. Dùng replace để đổi địa chỉ scrape thành tên namespace.
Đáp án đúng: A

Câu 09. prometheus.scrape đảm nhiệm công việc nào trong Alloy?
A. Ghi metric samples vào WAL rồi chuyển tới nhiều backend.
B. Scrape metrics endpoint theo chu kỳ đã được cấu hình.
C. Tạo metric từ log line bằng cách parse nội dung JSON.
D. Nhận metric push từ ứng dụng qua giao thức Remote Write.
Đáp án đúng: B

Câu 10. prometheus.remote_write dùng để làm gì?
A. Scrape endpoint HTTP của exporter theo lịch định kỳ.
B. Phát hiện target mới từ Kubernetes API server.
C. Đẩy metric samples tới endpoint hỗ trợ Remote Write.
D. Chuyển metric samples thành OpenTelemetry trace spans.
Đáp án đúng: C

Câu 11. Trong pipeline metrics cơ bản, dữ liệu đi theo luồng nào?
A. Scrape, exporter, discovery rồi log write.
B. Remote write, scrape, exporter rồi discovery relabel.
C. Discovery, remote write, scrape rồi exporter.
D. Exporter targets, scrape, relabel rồi remote write.
Đáp án đúng: D

Câu 12. prometheus.exporter.self được dùng để làm gì?
A. Đẩy log nội bộ của Alloy sang Loki endpoint.
B. Tạo trace nội bộ để gửi sang Tempo backend.
C. Thu metric hệ điều hành từ mọi node Kubernetes.
D. Expose metric nội bộ Alloy thành targets để scrape.
Đáp án đúng: D

Câu 13. Component nào thường tail file log cục bộ trong Alloy?
A. loki.write đọc file và quản lý vị trí tail trên node.
B. loki.process theo dõi filesystem rồi tự phát hiện file mới.
C. loki.source.file đọc log từ các đường dẫn cấu hình.
D. discovery.relabel mở file log và tách từng dòng.
Đáp án đúng: C

Câu 14. Muốn thu log từ các Pod Kubernetes, component nguồn nào phù hợp?
A. Dùng loki.source.kubernetes với targets từ discovery.
B. otelcol.exporter.loki để đọc stdout trực tiếp từ Pod.
C. loki.write với targets lấy từ Prometheus scrape job.
D. prometheus.scrape với file path của từng container log.
Đáp án đúng: A

Câu 15. loki.process thường làm nhiệm vụ nào trong pipeline logs?
A. Ghi log events vào object storage và quản lý retention.
B. Nhận OTLP traces rồi chia span thành log entries.
C. Khám phá Pod, Service rồi tạo Kubernetes targets.
D. Parse, lọc, xử lý multiline và chuyển đổi log entries.
Đáp án đúng: D

Câu 16. loki.write là thành phần nào trong pipeline logs?
A. Source đọc file log từ host và lưu offset đã đọc.
B. Processor parse JSON và loại bỏ trường nhạy cảm.
C. Writer gửi log đã xử lý tới Loki endpoint.
D. Discovery tìm Pod và gắn metadata namespace.
Đáp án đúng: C

Câu 17. Vì sao cần multiline processing cho Java exception logs?
A. Loại bỏ mọi dòng sau exception message đầu tiên.
B. Tách từng frame thành một Loki stream độc lập.
C. Đổi mỗi dòng stack trace thành một metric counter.
D. Gom stack trace nhiều dòng thành một log event.
Đáp án đúng: D

Câu 18. otelcol.receiver.otlp thường nhận telemetry qua giao thức nào?
A. Loki Push API qua HTTP và syslog qua UDP.
B. Pyroscope profile upload qua gRPC hoặc WebSocket.
C. OTLP qua gRPC hoặc HTTP theo cấu hình receiver.
D. Prometheus Remote Write qua TCP hoặc UDP tùy backend.
Đáp án đúng: C

Câu 19. Trong OTel pipeline, processor batch thường có tác dụng nào?
A. Gom telemetry thành batch để giảm request gửi đi.
B. Tách mỗi request thành một span riêng trước sampling.
C. Lưu telemetry vào WAL trước khi receiver nhận dữ liệu.
D. Đổi mọi resource attribute thành metric label.
Đáp án đúng: A

Câu 20. Vì sao memory_limiter thường được đặt sớm trong OTel pipeline?
A. Giới hạn áp lực bộ nhớ trước khi xử lý thêm dữ liệu.
B. Tạo resource attributes từ Kubernetes metadata.
C. Gom batch trước để tăng kích thước hàng đợi trong RAM.
D. Chỉ lọc span sau khi exporter đã gửi thành công.
Đáp án đúng: A

Câu 21. otelcol.processor.attributes có thể hỗ trợ việc gì?
A. Tạo Loki labels từ nội dung log multiline.
B. Khám phá process trên host để thu CPU profiles.
C. Scrape endpoint Prometheus rồi gửi metric qua remote write.
D. Thêm, cập nhật hoặc xóa attributes theo policy.
Đáp án đúng: D

Câu 22. otelcol.processor.filter thường được dùng để làm gì?
A. Loại telemetry không khớp điều kiện đã cấu hình.
B. Mã hóa payload OTLP trước khi gửi tới exporter.
C. Gom các span cùng trace thành một batch duy nhất.
D. Phát hiện receiver không mở port trên node.
Đáp án đúng: A

Câu 23. Tail sampling khác head sampling ở quyết định nào?
A. Tail sampling chọn log line sau khi chúng được index.
B. Tail sampling quyết định ngay khi span đầu tiên bắt đầu.
C. Tail sampling chỉ chọn metric samples trước khi scrape.
D. Xét trace sau khi đã thu thập thêm span liên quan.
Đáp án đúng: D

Câu 24. Muốn tail sampling nhất quán, cần bảo đảm điều gì?
A. Chỉ root span được gửi tới collector thực hiện sampling.
B. Các span của cùng trace tới cùng điểm ra quyết định.
C. Các span được gửi tới những exporter khác nhau theo thời gian.
D. Mỗi service chọn sampling rate riêng và độc lập.
Đáp án đúng: B

Câu 25. pyroscope.ebpf trong Alloy chủ yếu thu thập dữ liệu nào?
A. Metric counters từ kernel qua Prometheus Remote Write.
B. CPU profiles từ tiến trình bằng cơ chế eBPF.
C. Log events từ syscall rồi chuyển sang Loki.
D. Trace spans từ OTLP receiver và batch processor.
Đáp án đúng: B

Câu 26. Khi dùng pyroscope.java để profile JVM cục bộ, cần lưu ý gì?
A. Alloy cần root và host PID namespace để truy cập JVM.
B. Ứng dụng phải ghi heap dump vào Loki trước khi profile.
C. Chỉ cần quyền đọc dashboard của Pyroscope backend.
D. JVM phải gửi profile qua OTLP receiver trên HTTP.
Đáp án đúng: A

Câu 27. pyroscope.write đảm nhiệm vai trò nào trong profile pipeline?
A. Parse stack trace thành OpenTelemetry span events.
B. Gửi profiles tới Pyroscope-compatible endpoint.
C. Lập chỉ mục profile samples để Prometheus truy vấn.
D. Thu profile trực tiếp từ mọi JVM đang chạy trong cluster.
Đáp án đúng: B

Câu 28. Triển khai Alloy dạng DaemonSet thường phù hợp khi nào?
A. Cần một gateway tập trung nhận OTLP từ nhiều vùng.
B. Cần một replica duy nhất quản lý dashboard Grafana.
C. Thu telemetry node-local từ các node trong cluster.
D. Cần chạy batch job định kỳ để xóa log đã hết hạn.
Đáp án đúng: C

Câu 29. Triển khai Alloy dạng gateway tập trung phù hợp với mục đích nào?
A. Thay thế Kubernetes API server để phát hiện Pod.
B. Nhận và xử lý telemetry từ nhiều ứng dụng tập trung.
C. Đọc file log host-local trên mọi node mà không mount volume.
D. Chạy profiler cho process của host mà không cần host access.
Đáp án đúng: B

Câu 30. Khi Alloy discovery Kubernetes không tìm thấy Pod, nên kiểm tra gì trước?
A. Dung lượng retention của Loki object storage.
B. Sampling fraction của OpenTelemetry tracing block.
C. Ngưỡng alert của Prometheus remote write endpoint.
D. Kiểm tra quyền service account với tài nguyên Kubernetes.
Đáp án đúng: D

Câu 31. Muốn đọc container log từ node filesystem, cấu hình triển khai cần gì?
A. Mount đúng thư mục log của host vào Alloy container.
B. Mount thư mục dashboard Grafana vào container Alloy.
C. Expose cổng OTLP của mọi Pod ra Internet công khai.
D. Dùng host network để bỏ qua quyền đọc filesystem.
Đáp án đúng: A

Câu 32. Receiver OTLP chỉ cần truy cập nội bộ cluster. Cách bind nào hợp lý?
A. Dùng hostPath để giới hạn kết nối tới receiver.
B. Bind mọi interface công khai rồi dựa vào port ngẫu nhiên.
C. Tắt xác thực vì traffic chỉ được gửi từ Pod nội bộ.
D. Bind receiver nội bộ, rồi giới hạn bằng network policy.
Đáp án đúng: D

Câu 33. Bảo vệ credential trong cấu hình Alloy nên làm thế nào?
A. Đặt mật khẩu trong label để component downstream đọc.
B. Dùng secret manager hoặc biến môi trường để nạp credential.
C. Mã hóa Base64 token rồi lưu như giá trị công khai.
D. Ghi token trực tiếp vào file cấu hình và commit cùng code.
Đáp án đúng: B

Câu 34. Khi forward telemetry qua mạng không tin cậy, nên bật gì?
A. Tắt TLS để giảm CPU và chỉ đổi port sang số cao.
B. Chỉ thêm label environment để mã hóa payload tự động.
C. TLS và cơ chế xác thực phù hợp với backend đích.
D. Chỉ dùng compression vì nó ngăn đọc trộm dữ liệu.
Đáp án đúng: C

Câu 35. Cardinality metric tăng mạnh sau relabeling thường nên xử lý ra sao?
A. Đổi tên metric theo từng Pod để tránh trùng lặp.
B. Loại dimension biến thiên cao trước khi ghi metric.
C. Thêm request ID vào mọi sample để dễ nhóm kết quả.
D. Tăng scrape frequency để backend tổng hợp ít series hơn.
Đáp án đúng: B

Câu 36. Khi scrape target quá thường xuyên, tác động nào có thể xuất hiện?
A. Tự động tăng độ chính xác của mọi metric histogram.
B. Làm remote write WAL bỏ qua các mẫu mới hơn.
C. Giảm số request scrape và giảm CPU của exporter.
D. Scrape quá dày làm tăng tải lên target và collector.
Đáp án đúng: D

Câu 37. Một OTel pipeline có queue và batch cần cân bằng điều gì?
A. Số dashboard, số người xem và kích thước panel.
B. Số nhãn Kubernetes, số container và tên namespace.
C. Sampling trace, retention log và màu sắc dashboard.
D. Cân bằng throughput, memory, latency và độ tin cậy.
Đáp án đúng: D

Câu 38. Cách nào phù hợp để tự giám sát Alloy?
A. Thu metrics nội bộ, kiểm tra lỗi và queue của Alloy.
B. Tắt Alloy logs để tránh tăng chi phí telemetry.
C. Chỉ kiểm tra dashboard backend có hiển thị dữ liệu mới.
D. Chỉ theo dõi CPU host mà không xem pipeline component.
Đáp án đúng: A

Câu 39. Alloy UI component graph hữu ích nhất khi xử lý pipeline lỗi vì sao?
A. Hiển thị mọi log đã index trong backend Loki.
B. Hiển thị trạng thái component và các kết nối dữ liệu.
C. Thay thế kiểm tra cấu hình và kiểm thử kết nối backend.
D. Tự sửa cấu hình component sai và restart toàn bộ node.
Đáp án đúng: B

Câu 40. Trước khi triển khai cấu hình Alloy mới, nên kiểm tra gì?
A. Chỉ restart Agent và xem process còn chạy hay không.
B. Validate config, rồi kiểm thử telemetry end-to-end.
C. Chỉ kiểm tra cú pháp YAML dù cấu hình dùng River.
D. Chỉ kiểm tra backend có dashboard mặc định hay chưa.
Đáp án đúng: B
