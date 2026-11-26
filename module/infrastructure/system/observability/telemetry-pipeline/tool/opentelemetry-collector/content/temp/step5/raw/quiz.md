Trong cấu hình Collector, phần service.pipelines xác định nội dung nào?
A. Liệt kê component có sẵn trong bản phân phối.
B. Định nghĩa endpoint quản trị mà tiến trình mở.
C. Khai báo tín hiệu, component và thứ tự.
D. Khai báo danh tính được phép gửi telemetry.
Đáp án đúng: C

Thành phần receiver thực hiện trách nhiệm nào trong pipeline?
A. Lưu trace và metric lâu dài trong kho lưu trữ.
B. Nhận dữ liệu telemetry để đưa vào pipeline.
C. Đánh giá cảnh báo từ dữ liệu đã thu thập.
D. Gửi dữ liệu đã xử lý đến backend đích.
Đáp án đúng: B

Một processor thường được dùng để thực hiện công việc nào?
A. Cung cấp endpoint kiểm tra trạng thái tiến trình.
B. Mở listener để nhận OTLP từ ứng dụng.
C. Gửi batch đến backend theo lịch định kỳ.
D. Biến đổi hoặc bổ sung dữ liệu telemetry.
Đáp án đúng: D

Exporter có vai trò chính nào trong một pipeline telemetry?
A. Gửi dữ liệu xử lý đến backend đích.
B. Nhận và giải mã telemetry từ nguồn gửi.
C. Xác định thứ tự các bước xử lý.
D. Gắn định danh resource cho dữ liệu nguồn.
Đáp án đúng: A

Một pipeline trong Collector được xác định theo tín hiệu nào?
A. Theo backend đích và chính sách lưu trữ.
B. Theo môi trường chạy và số replica.
C. Theo giao thức truyền tải mà receiver hỗ trợ.
D. Theo loại logs, metrics, traces.
Đáp án đúng: D

Khi khai báo receiver trong service.pipelines, điều gì phải khớp?
A. ID component phải khớp tên tham chiếu.
B. Tên extension phải giống tên của receiver.
C. Tên máy chủ phải trùng với địa chỉ exporter.
D. Tên service nguồn phải có trong resource attributes.
Đáp án đúng: A

Thứ tự processor trong một pipeline ảnh hưởng điều gì?
A. Thứ tự component được biên dịch vào binary.
B. Thứ tự record đi qua từng processor.
C. Thứ tự endpoint được mở trên giao diện mạng.
D. Thứ tự pipeline được khởi tạo trong tiến trình.
Đáp án đúng: B

Vì sao memory_limiter thường được đặt gần đầu pipeline?
A. Kiểm soát áp lực bộ nhớ trước các processor khác.
B. Chuyển dữ liệu sang exporter trước khi lọc.
C. Phát hiện resource attributes thiếu sau enrichment.
D. Gom dữ liệu thành batch trước khi xử lý.
Đáp án đúng: A

Batch processor chủ yếu cải thiện đặc tính nào của pipeline?
A. Khả năng phục hồi dữ liệu sau khi process restart.
B. Gom record thành batch để giảm overhead gửi đi.
C. Độ chính xác trace context khi request qua nhiều dịch vụ.
D. Khả năng xác thực client khi gửi OTLP qua kết nối.
Đáp án đúng: B

Điểm khác biệt chính giữa attributes processor và resource processor là gì?
A. Một bên nhận OTLP, bên kia gửi dữ liệu backend.
B. Một bên lấy mẫu trace, bên kia gom metric thành batch.
C. Một bên kiểm tra TLS, bên kia xác thực client.
D. Một bên sửa thuộc tính record, bên kia sửa resource.
Đáp án đúng: D

Transform processor thường dùng ngôn ngữ nào để mô tả phép biến đổi?
A. OTTL mô tả điều kiện và phép biến đổi telemetry.
B. TraceQL sửa span và resource attributes.
C. SQL truy vấn dữ liệu trực tiếp trong exporter.
D. PromQL chọn time series cần cập nhật.
Đáp án đúng: A

Filter processor thường tác động đến dữ liệu theo cách nào?
A. Lưu record vào queue bền vững trên đĩa.
B. Nén payload trước khi gửi đến exporter.
C. Loại record thỏa điều kiện lọc đã cấu hình.
D. Tạo resource attributes từ thông tin máy chủ.
Đáp án đúng: C

Khi viết điều kiện OTTL, vì sao cần chọn đúng context?
A. Xác định cấu trúc dữ liệu được tham chiếu.
B. Chọn endpoint mạng mà receiver sẽ mở.
C. Chọn dung lượng queue của exporter.
D. Chọn phiên bản và cách truyền tải OTLP đang dùng.
Đáp án đúng: A

OTLP receiver thường có thể tiếp nhận telemetry qua những kiểu truyền tải nào?
A. Fluent Forward qua TCP.
B. OTLP qua gRPC hoặc HTTP.
C. Prometheus scrape qua HTTP.
D. Syslog qua TCP hoặc UDP.
Đáp án đúng: B

Connector trong Collector có đặc điểm kiến trúc nào?
A. Thay thế receiver và exporter trong mọi pipeline.
B. Chỉ cung cấp endpoint quản trị ngoài pipeline.
C. Nối đầu ra pipeline này với đầu vào pipeline khác.
D. Chỉ ghi telemetry vào bộ nhớ tạm của tiến trình.
Đáp án đúng: C

Extension khác receiver hoặc processor ở điểm cốt lõi nào?
A. Biến đổi từng span trước khi export dữ liệu.
B. Chỉ tiếp nhận metrics từ Prometheus receiver.
C. Xác định schema của mọi resource attribute.
D. Cung cấp chức năng hỗ trợ ngoài pipeline dữ liệu.
Đáp án đúng: D

Tail sampling cần điều kiện định tuyến nào để quyết định đúng theo trace?
A. Mọi trace phải đi qua một receiver duy nhất.
B. Mỗi service tự quyết định sampling độc lập.
C. Các span cùng trace phải đến cùng sampler instance.
D. Mỗi span được gửi đến một exporter riêng.
Đáp án đúng: C

Khi phân phối trace đến nhiều Collector có tail sampling, cách nào phù hợp?
A. Chọn instance theo kích thước span.
B. Dùng trace ID làm khóa định tuyến cho trace.
C. Chia đều span ngẫu nhiên theo số request.
D. Định tuyến theo tên exporter để cân bằng tải.
Đáp án đúng: B

Exporter sending queue giúp giải quyết vấn đề nào?
A. Đệm dữ liệu trong queue trước khi gửi đến backend.
B. Chuẩn hóa tên resource trước khi xử lý.
C. Xác minh chữ ký số của từng span nhận được.
D. Tự tăng replica khi CPU vượt ngưỡng.
Đáp án đúng: A

Cơ chế retry của exporter phù hợp nhất với tình huống nào?
A. Loại record bị policy lọc khỏi pipeline.
B. Receiver chưa được khai báo trong pipeline.
C. Backend gặp lỗi tạm thời và có thể phục hồi sau.
D. Sửa schema dữ liệu sai trước khi gửi lại.
Đáp án đúng: C

Muốn duy trì sending queue qua lần restart, cần bổ sung gì?
A. Đổi pipeline sang traces để lưu trạng thái.
B. Dùng storage extension để lưu queue bền vững.
C. Tăng batch size để queue ở RAM lâu hơn.
D. Thêm receiver để gửi lại dữ liệu sau restart.
Đáp án đúng: B

Khi một pipeline khai báo nhiều exporter, hành vi thông thường là gì?
A. Mỗi exporter đều nhận bản sao dữ liệu của pipeline.
B. Chỉ exporter cuối nhận dữ liệu sau xử lý.
C. Các exporter thay nhau theo trạng thái health.
D. Dữ liệu chia ngẫu nhiên cho một exporter.
Đáp án đúng: A

Trong mô hình agent/gateway, gateway thường đảm nhiệm vai trò nào?
A. Thay thế backend lưu logs, metrics và traces.
B. Xử lý và chuyển tiếp telemetry tập trung từ nhiều nguồn.
C. Chạy một process cạnh từng container ứng dụng.
D. Chỉ instrument code bên trong ứng dụng.
Đáp án đúng: B

Khi triển khai Collector trên Kubernetes, lựa chọn nào phù hợp cho agent mỗi node?
A. CronJob đọc dữ liệu từ API theo lịch.
B. StatefulSet chỉ chạy một pod cho cả cluster.
C. DaemonSet duy trì pod Collector trên từng node phù hợp.
D. Job chạy xong sau mỗi lần thu thập log.
Đáp án đúng: C

Để bảo vệ OTLP receiver bằng mutual TLS, cấu hình cần đáp ứng điều gì?
A. Cả client và server đều xác thực chứng chỉ peer.
B. Client chỉ gửi API key trong query string.
C. Receiver bỏ kiểm tra certificate chain để giảm trễ.
D. Exporter ký payload nhưng không xác thực kết nối.
Đáp án đúng: A

Authentication extension được dùng trong pipeline nhằm mục đích nào?
A. Tạo span metrics từ trace đã nhận.
B. Bổ sung hostname và metadata cloud cho resource.
C. Cấp cơ chế xác thực cho component hỗ trợ.
D. Gom nhiều record thành batch trước khi export.
Đáp án đúng: C

Muốn loại bỏ trường nhạy cảm trước khi gửi ra ngoài, nên làm gì?
A. Retry lại khi backend báo lỗi tạm thời.
B. Mã hóa kết nối nhưng giữ nguyên trường nhạy cảm.
C. Đổi tên thuộc tính trước khi gửi sang backend.
D. Redact trường nhạy cảm trước khi export.
Đáp án đúng: D

Resource detection processor chủ yếu bổ sung loại thông tin nào?
A. Trạng thái retry của từng exporter trong pipeline.
B. Metadata về host, cloud và môi trường chạy.
C. Nội dung message và exception của log record.
D. Mã trạng thái HTTP của request đầu vào.
Đáp án đúng: B

Cách nào giúp kiểm soát cardinality cao trong metrics?
A. Tăng queue để giữ thêm label trong bộ nhớ.
B. Bật sampling cho log trước khi export.
C. Tăng exporter để chia nhỏ cùng một time series.
D. Giảm label có giá trị biến thiên không giới hạn.
Đáp án đúng: D

Nhóm chỉ số nào hữu ích để giám sát nội bộ Collector?
A. Số request nghiệp vụ thành công của ứng dụng.
B. Số user và lần đổi mật khẩu backend.
C. Telemetry nhận, từ chối, lỗi gửi.
D. Số file lưu và dung lượng bucket object storage.
Đáp án đúng: C

Health_check extension thường được dùng để làm gì?
A. Profile CPU và heap cho từng component.
B. Lưu checkpoint exporter queue lên đĩa.
C. Định tuyến trace theo trace ID đến sampler.
D. Endpoint để kiểm tra trạng thái Collector.
Đáp án đúng: D

Khi cần profile CPU hoặc memory của Collector, extension nào phù hợp?
A. health_check thu stack trace của process.
B. zpages hiển thị trạng thái pipeline và span.
C. pprof cung cấp dữ liệu profiling.
D. file_storage ghi snapshot bộ nhớ ra đĩa.
Đáp án đúng: C

Khi backend chậm và queue tăng, biện pháp nào giúp hạn chế cạn bộ nhớ?
A. Tăng số bản sao record trước khi export.
B. Tăng queue để giữ dữ liệu không giới hạn.
C. Tắt processor để gửi thẳng đến backend.
D. Đặt giới hạn queue và memory limiter.
Đáp án đúng: D

Muốn tìm điểm dữ liệu bị mất, nên đối chiếu những chỉ số nào?
A. So sánh số accepted, dropped và failed.
B. Đối chiếu user, session và login ở backend.
C. Đối chiếu CPU client và dung lượng database.
D. Đối chiếu số pod và lần deploy.
Đáp án đúng: A

Trước khi triển khai cấu hình mới, bước kiểm tra nào phù hợp?
A. Chỉ xác nhận tiến trình cũ vẫn chạy bình thường.
B. Gửi telemetry production rồi mới quan sát lỗi.
C. Chỉ kiểm tra file YAML mở được trong editor.
D. Dùng validator của bản build rồi chạy thử cấu hình.
Đáp án đúng: D

Vì sao cùng một cấu hình Collector có thể chạy ở bản phân phối này nhưng lỗi ở bản khác?
A. Receiver biến component chưa có thành extension.
B. Binary chỉ nạp component có trong bản build.
C. Mọi bản phân phối chứa toàn bộ component hiện có.
D. Exporter tự tải component thiếu khi pipeline khởi động.
Đáp án đúng: B

Spanmetrics connector minh họa khả năng nào của connector?
A. Chuyển metric thành log qua pipeline khác.
B. Xác thực chứng chỉ client trước khi nhận trace.
C. Lưu trace theo tenant trong storage.
D. Sinh metrics từ span cho pipeline metrics.
Đáp án đúng: D
