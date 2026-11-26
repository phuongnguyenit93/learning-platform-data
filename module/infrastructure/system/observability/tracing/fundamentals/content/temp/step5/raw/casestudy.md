Một khách hàng đặt hàng qua gateway rồi đi qua inventory, payment và shipping; log ở từng service có request ID riêng nhưng không có trace ID chung, khiến đội SRE mất hàng giờ ghép các mốc thời gian để tìm chặng làm giao dịch thất bại.
Một API gateway tạo root span cho mỗi request nhưng service catalog lại tự tạo trace mới khi nhận HTTP call; các span đều xuất hiện trong backend tracing nhưng không có quan hệ parent-child để dựng hành trình xuyên dịch vụ.
Một nhóm phát triển thấy trace có đủ span của gateway và payment nhưng thiếu inventory; inventory vẫn trả kết quả trong log và metric, nên đội kỹ thuật cần xác định lỗi nằm ở instrumentation, propagation hay quá trình export.
Một hệ thống dùng trace ID làm khóa tương quan giữa log và trace, nhưng một số service ghi trace ID dưới dạng chữ hoa còn backend chuẩn hóa chữ thường; tìm kiếm từ log không mở được trace tương ứng dù dữ liệu đã được thu thập.
Một ứng dụng Java tạo span cho controller và database query nhưng quên kết thúc span trong nhánh exception; trace hiển thị request kéo dài lâu hơn thời gian thực tế và các span sau bị gắn sai trạng thái.
Một service mở span thủ công cho từng bước nghiệp vụ nhưng không đặt span cha hiện hành trước khi gọi helper; các span xuất hiện thành nhiều root riêng biệt thay vì là con của request HTTP.
Một nhóm dùng cùng tên span process cho mọi thao tác trong service; dashboard có hàng nghìn span nhưng không phân biệt được bước xác thực, truy vấn kho và tính giá, khiến việc phân tích latency không có giá trị.
Một hệ thống tạo span cho mỗi lần gọi hàm nội bộ rất nhỏ; trace của một request có hàng chục nghìn span và tốn nhiều dung lượng, trong khi các chặng I/O quan trọng bị chìm giữa chi tiết không cần thiết.
Một endpoint trả response sau 200 mili giây nhưng trace hiển thị tổng thời gian 1,5 giây vì span background task vẫn được gắn như con của request; nhóm phát triển cần xác định ranh giới vòng đời giữa request và công việc bất đồng bộ.
Một ứng dụng Java sử dụng OpenTelemetry SDK và auto-instrumentation agent cùng lúc; mỗi HTTP request xuất hiện hai span server gần giống nhau, khiến latency và số lượng trace bị đếm trùng.
Đội nền tảng nâng cấp OpenTelemetry Java agent nhưng một số pod vẫn chạy phiên bản cũ; semantic attributes của span khác nhau và dashboard APM không thể so sánh nhất quán giữa các replica.
Một service Spring Boot được instrument tự động nhưng dùng HTTP client do nhóm tự viết; inbound server span có đầy đủ còn outbound call không tạo client span, khiến cây trace dừng tại service trung gian.
Một nhóm thêm custom span cho truy vấn database nhưng không ghi database system, operation và tên query đã chuẩn hóa; người trực thấy span chậm mà không xác định được loại backend đang gây nghẽn.
Một ứng dụng ghi span attribute là toàn bộ SQL statement có literal email và số tài khoản; trace giúp debug nhanh nhưng dữ liệu nhạy cảm xuất hiện trong hệ quan sát và có thể bị tìm kiếm bởi nhiều nhóm.
Một service tạo span event khi retry request tới đối tác nhưng chỉ ghi message chung chung; trace cho thấy có retry nhưng không có attempt number, mã lỗi và thời gian từng lần để phân tích nguyên nhân.
Một nhóm đánh dấu mọi span có HTTP status dưới 500 là thành công; lỗi nghiệp vụ trả 200 vẫn được xem là thành công trong APM và báo cáo error rate thấp hơn thực tế.
Một ứng dụng gRPC trả status RESOURCE_EXHAUSTED nhưng instrumentation chỉ đánh giá HTTP status của transport; trace không đánh dấu lỗi và nhóm SRE bỏ sót sự cố quota ở backend.
Một service nhận request qua reverse proxy và tạo span server với URL nội bộ; thuộc tính host và route không phản ánh endpoint khách gọi, khiến dashboard theo endpoint công khai không thể phân tích đúng.
Một nhóm gắn user_id và order_id vào span name để tìm kiếm nhanh; mỗi giao dịch tạo một tên span khác nhau, làm aggregation bị phân mảnh và chi phí index tăng cao.
Một API có route /orders/{id} nhưng instrumentation ghi path chứa từng order ID; cardinality span name và resource attributes tăng mạnh sau chiến dịch bán hàng, làm truy vấn latency theo route khó sử dụng.
Một service tạo span thủ công trong một thư viện được gọi từ nhiều ứng dụng nhưng không ghi instrumentation scope; đội observability không phân biệt được span đến từ phiên bản thư viện nào khi hành vi thay đổi.
Một ứng dụng Java dùng nhiều tracer provider do hai thư viện khởi tạo độc lập; một số span được export từ provider thứ nhất, số khác từ provider thứ hai và không cùng trace context dù xử lý thuộc cùng request.
Một đội phát triển khởi tạo OpenTelemetry SDK trong static initializer trước khi cấu hình resource attributes; service.name mặc định được gắn vào các span đầu tiên và không thể sửa lại sau khi ứng dụng khởi động.
Một service chạy trên Kubernetes có nhiều replica nhưng tất cả dùng cùng service.name và không có deployment.environment; trace từ staging và production bị gộp vào cùng dịch vụ trong giao diện phân tích.
Một hệ thống dùng service.name lấy từ tên pod có hậu tố ngẫu nhiên; sau mỗi rollout, Datadog hoặc Jaeger hiển thị một service mới và xu hướng độ trễ dài hạn bị chia thành nhiều thực thể.
Một nhóm muốn so sánh latency giữa các phiên bản Java nhưng resource attribute service.version không được gắn ở một số pod; trace không thể lọc chính xác bản phát hành gây ra regression.
Một ứng dụng ghi span status ERROR nhưng không đặt exception.type hoặc exception.message; trace được đánh dấu lỗi nhưng người trực phải mở log ở nơi khác để biết loại exception và nguyên nhân cụ thể.
Một nhóm thêm exception stack trace vào cả span attribute và span event; kích thước trace tăng mạnh, một số backend cắt payload và dữ liệu nhạy cảm trong thông báo lỗi bị lưu lặp.
Một hệ thống có request timeout tại gateway nhưng service backend tiếp tục xử lý; trace server span kết thúc muộn hơn client span và dashboard latency hiển thị hai con số khác nhau, khiến đội SRE cần hiểu thời điểm đo ở mỗi ranh giới.
Một ứng dụng tạo span cho tác vụ chạy nền sau khi trả HTTP response; span nền được tạo không có link tới span request ban đầu và đội hỗ trợ không thể xác định tác vụ được kích hoạt bởi giao dịch nào.
Một nhóm dùng span link để nối công việc được kích hoạt từ nhiều message nhưng dashboard chỉ hiển thị cây parent-child; nhân viên trực tưởng các message là tác vụ độc lập và bỏ qua quan hệ nhân quả.
Một nền tảng xử lý một batch gồm nhiều event từ các trace khác nhau; đội phát triển gắn cả batch dưới parent span của event đầu tiên, làm trace sai lệch quan hệ giữa các giao dịch.
Một service gọi song song ba backend và dùng một span chung cho toàn bộ fan-out; khi một backend chậm, trace không thể tách thời gian từng lời gọi để xác định dependency nào làm p99 tăng.
Một nhóm sử dụng span kind INTERNAL cho cả HTTP server và client; service map không nhận diện đúng quan hệ gọi giữa các service và các báo cáo dependency thiếu dữ liệu.
Một ứng dụng Java khởi tạo span trong constructor của singleton service; span tồn tại lâu hơn request và các thao tác đồng thời ghi event vào cùng một span, làm dữ liệu trace của nhiều người dùng bị trộn.
Một service ghi exception vào span rồi bắt lỗi và retry thành công; span cuối vẫn mang status ERROR dù giao dịch hoàn tất, khiến error rate APM cao hơn số giao dịch thất bại.
Một API trả 404 hợp lệ khi người dùng tìm đơn hàng không tồn tại; instrumentation đánh mọi mã 4xx là lỗi và tạo cảnh báo quá nhiều cho hành vi nghiệp vụ bình thường.
Một nhóm cấu hình span status dựa trên HTTP response nhưng bỏ qua lỗi xảy ra trong callback sau khi response đã gửi; trace request báo thành công trong khi tác vụ xử lý đơn thất bại.
Một ứng dụng dùng JDBC connection pool và instrument span database nhưng không phân biệt thời gian chờ lấy connection với thời gian query; nhóm SRE nhầm nghẽn pool thành truy vấn SQL chậm.
Một service thực hiện DNS lookup và TLS handshake trước khi gọi đối tác nhưng HTTP client span chỉ ghi tổng thời gian request; đội vận hành không biết latency tăng nằm ở phân giải tên, thiết lập kết nối hay xử lý từ xa.
Một ứng dụng Java sử dụng thư viện HTTP có connection pooling; span client chỉ tạo khi gửi request và không thể hiện thời gian chờ connection pool, khiến một nút thắt quan trọng không được phát hiện.
Một nhóm instrument database query và ghi nguyên tham số truy vấn vào span; thông tin cá nhân và dữ liệu tài khoản bị gửi sang backend tracing dù chỉ cần loại query và thời gian thực thi.
Một service có cache hit và cache miss nhưng chỉ tạo span cho truy vấn database; trace của request cache hit không cho biết dữ liệu được lấy từ cache, khiến tỷ lệ cache và đường đi nghiệp vụ khó giải thích.
Một API xử lý upload file lớn và tạo span server cho toàn bộ thời gian truyền dữ liệu; thời gian truyền mạng chiếm phần lớn span nên nhóm phát triển nhầm cho rằng xử lý nghiệp vụ phía server bị chậm.
Một hệ thống streaming response giữ server span mở trong nhiều phút sau khi gửi header đầu tiên; dashboard latency tính tới lúc stream đóng thay vì thời gian phản hồi đầu tiên mà người dùng quan tâm.
Một service dùng gRPC streaming và tạo một span cho toàn bộ stream kéo dài hàng giờ; đội vận hành không thể phân tích độ trễ từng message và lỗi chỉ xuất hiện ở giữa phiên không được định vị rõ.
Một ứng dụng Java dùng CompletableFuture để gọi nhiều dependency; span của callback chạy trên common pool không giữ context gốc nên trace bị chia thành nhiều root sau khi đổi thread.
Một service sử dụng ExecutorService tùy chỉnh để xử lý ảnh sau request; context propagation chỉ được cài cho ForkJoinPool mặc định nên log và span trên executor riêng thiếu trace ID.
Một nhóm wrap Runnable để truyền OpenTelemetry Context nhưng quên đóng scope trong finally; thread pool tái sử dụng worker và request sau kế thừa span của request trước.
Một ứng dụng Spring dùng @Async để gửi email sau khi tạo đơn; tác vụ gửi email có trace mới không liên kết với request tạo đơn dù message được tạo trong cùng transaction.
Một service chạy ScheduledExecutorService để retry tác vụ thanh toán sau vài phút; context của request ban đầu được giữ trong task quá lâu và baggage chứa thông tin phiên đăng nhập đã hết hiệu lực.
Một ứng dụng Reactor chuyển scheduler qua publishOn và subscribeOn; trace ở controller đầy đủ nhưng các operator sau khi đổi scheduler không còn context và span không liên kết với request.
Một nhóm dùng ThreadLocal để lưu trace ID trong ứng dụng reactive; các signal chạy trên nhiều thread làm log mang trace ID rỗng hoặc của request khác.
Một ứng dụng dùng parallel stream để xử lý danh sách đơn hàng; span tạo bên trong worker thread không có parent và cây trace không thể hiện các nhánh xử lý song song.
Một service dùng virtual threads sau khi nâng cấp Java nhưng thư viện tracing tự viết giả định context gắn cố định với thread pool; correlation ID mất ở một số tác vụ khi chuyển sang virtual thread.
Một ứng dụng gửi message vào Kafka rồi consumer xử lý sau vài phút; producer trace và consumer trace độc lập vì traceparent không được đưa vào message headers.
Một nhóm truyền trace ID trong payload JSON thay vì header chuẩn; consumer đọc payload nhưng một hệ thống trung gian chỉ chuyển headers nên context bị mất sau khi message đi qua broker.
Một consumer Kafka nhận batch chứa nhiều message từ các request khác nhau; chỉ một context hiện hành được dùng cho cả batch và log của từng message bị gắn trace ID của message đầu.
Một dịch vụ RabbitMQ retry message qua dead-letter queue; message được chuyển sang queue mới nhưng trace context không được giữ, khiến trace dừng ở lần xử lý đầu tiên.
Một ứng dụng dùng SQS và visibility timeout để retry message; mỗi lần nhận lại message tạo root trace mới, không có link hoặc metadata để xem các attempt thuộc cùng một công việc.
Một webhook nhận traceparent từ đối tác bên ngoài; nhóm phát triển tin hoàn toàn trace ID do client gửi và cho phép metadata không hợp lệ ảnh hưởng trace nội bộ, khiến ranh giới tin cậy chưa được xác định.
Một gateway nhận W3C traceparent và tracestate nhưng service Java chỉ trích xuất định dạng B3; request thành công nhưng trace bị tách tại ranh giới giữa hai thư viện instrumentation.
Một proxy xóa header traceparent vì cấu hình allowlist chưa cập nhật; backend tự tạo trace mới và đội SRE không nhận ra propagation bị đứt cho tới khi điều tra sự cố xuyên service.
Một service tự tạo traceparent mới cho outbound call thay vì inject context hiện hành; mỗi dependency có trace riêng và service map không thể dựng đúng chuỗi request.
Một hệ thống chuyển từ B3 sang W3C Trace Context nhưng một số mobile client vẫn gửi header cũ; backend ưu tiên sai propagator và tạo trace mới cho một phần lưu lượng.
Một nhóm dùng tracestate để truyền metadata của nhà cung cấp tracing; proxy cắt bớt header dài và các thông tin vendor-specific biến mất dù traceparent vẫn hợp lệ.
Một ứng dụng ghi traceparent từ request vào log nhưng không xác thực định dạng trước khi ghi; header rất dài từ client làm log phình và tăng nguy cơ lạm dụng tài nguyên.
Một tổ chức dùng baggage để truyền tenant, region và experiment ID; một service trung gian không propagate baggage nên các span cuối không có metadata cần cho phân tích theo tenant.
Một nhóm đưa email, số điện thoại và access token vào baggage để mọi service truy cập tiện lợi; các giá trị lan sang traces và log của nhiều backend, tạo rủi ro riêng tư vượt phạm vi mục đích quan sát.
Một gateway chấp nhận tenant_id trong baggage từ client rồi dùng nó để chọn sampling policy; người dùng có thể tự khai tenant VIP và làm tăng lượng trace được lưu ngoài dự toán.
Một hệ thống truyền baggage có hàng chục khóa qua nhiều service; kích thước HTTP header vượt giới hạn ở gateway và request bị trả 431 dù nghiệp vụ không cần tất cả metadata đó.
Một nhóm dùng correlation ID và trace ID như cùng một giá trị trong mọi hệ thống; khi một tác vụ nền không có request cha, ID được tái sử dụng khiến các hoạt động độc lập bị ghép nhầm.
Một ứng dụng ghi trace ID trong MDC ở đầu request nhưng không dọn MDC khi exception; thread xử lý request tiếp theo mang trace ID cũ và log của hai khách hàng bị liên kết sai.
Một service có trace propagation đúng nhưng logger không lấy trace_id và span_id từ context; đội hỗ trợ phải tìm log bằng timestamp và host, mất khả năng điều tra theo một trace cụ thể.
Một nhóm cấu hình log correlation dùng trường traceId nhưng backend log search yêu cầu trace_id; trace và log đều có dữ liệu nhưng liên kết tự động trong giao diện không hoạt động.
Một tổ chức sử dụng trace ID làm nhãn metric để nối biểu đồ với trace; mỗi request tạo series mới và cardinality metrics tăng không kiểm soát, khiến hệ thống quan sát quá tải.
Một service muốn thêm exemplar trace ID vào histogram latency nhưng SDK metrics và tracing dùng context provider khác nhau; biểu đồ có latency nhưng không có liên kết tới trace mẫu.
Một ứng dụng tạo span trong code nhưng không có exporter được cấu hình; test unit thấy span object tồn tại nên nhóm tưởng tracing hoạt động, trong khi backend không nhận được dữ liệu nào.
Một Java service export OTLP tới OpenTelemetry Collector nhưng dùng endpoint HTTP trong khi collector chỉ mở gRPC; Agent báo lỗi kết nối và trace không xuất hiện dù request ứng dụng thành công.
Một nhóm đặt timeout exporter ngắn hơn thời gian phản hồi bình thường của collector; batch spans bị retry và xuất hiện duplicate trace data khi backend xử lý chậm.
Một ứng dụng bật BatchSpanProcessor nhưng shutdown hook không flush trước khi JVM thoát; các span của job ngắn hạn bị mất khi container kết thúc ngay sau khi xử lý xong.
Một service serverless chỉ sống vài giây và export spans đồng bộ khi kết thúc; cold start và giới hạn thời gian shutdown khiến một số trace bị mất trước khi gửi hoàn tất.
Một đội triển khai collector gateway có queue nhưng collector bị restart khi backend ngừng hoạt động; queue chỉ lưu trong bộ nhớ nên tất cả spans chưa gửi biến mất dù SDK đã export thành công.
Một nền tảng có nhiều collector replica nhưng client dùng DNS round-robin; spans của cùng trace được phân tán đến nhiều gateway, làm tail sampling không có đủ dữ liệu của trace để quyết định.
Một tổ chức cấu hình tail sampling giữ trace lỗi ở gateway nhưng SDK đã head-sample chỉ 10%; những trace bị bỏ ở SDK không bao giờ tới gateway để được giữ khi có lỗi.
Một nhóm đặt decision_wait của tail sampler quá ngắn; span database cuối cùng đến muộn sau khi quyết định bỏ trace, khiến sự cố query chậm không có trace hoàn chỉnh.
Một service có request kéo dài nhiều phút nhưng tail sampler chỉ giữ dữ liệu trong bộ nhớ giới hạn; số trace đồng thời tăng cao và collector loại bỏ một phần trace trước khi có quyết định.
Một ứng dụng có lỗi nghiệp vụ nhưng HTTP status vẫn 200; tail sampling chỉ giữ trace có span status ERROR nên các giao dịch thất bại không được giữ lại.
Một nhóm sampling dựa trên thời lượng toàn trace từ root span tới span con ở service khác; đồng hồ giữa các service lệch nhau nên timeline bị kéo dài giả tạo và sampler giữ nhầm request nhanh, bỏ request chậm.
Một tổ chức dùng probabilistic sampling với tỷ lệ cố định 1% cho mọi service; luồng thanh toán ít lưu lượng và rủi ro cao không có đủ trace để điều tra, trong khi health check chiếm phần lớn trace được giữ.
Một hệ thống tăng sampling lên 100% trong giờ xảy ra sự cố nhưng quên hạ về mức bình thường; chi phí ingest và lưu trữ tăng mạnh sau khi incident đã kết thúc.
Một nhóm giữ tất cả trace có customer tier premium nhưng thuộc tính tier được client tự gửi; người dùng thường có thể tự nâng tier để được lấy mẫu nhiều hơn và gây tăng chi phí.
Một backend tracing báo số trace ít hơn số request vì sampling; nhóm sản phẩm so sánh trực tiếp hai con số và kết luận mất dữ liệu mà không tính đến tỷ lệ lấy mẫu.
Một ứng dụng chỉ lưu trace lỗi trong 24 giờ nhưng ticket hỗ trợ thường được mở sau ba ngày; nhóm điều tra không còn trace để xác minh sự cố dù log vẫn tồn tại.
Một doanh nghiệp giữ trace trong backend 30 ngày nhưng sampling policy thay đổi theo từng phiên bản; khi phân tích xu hướng tháng, tập trace không đại diện cùng một tỷ lệ lưu giữa các tuần.
Một nhóm sử dụng trace làm bằng chứng cho giao dịch tài chính; do sampling và giới hạn retention, không phải mọi request đều có trace, khiến nhóm kiểm toán cần xác định loại dữ liệu nào đủ giá trị pháp lý.
Một hệ thống phân tán có nhiều service và một request p99 chậm; đội SRE chỉ xem tổng duration của root span và chưa xác định được span con chiếm thời gian, khiến việc khoanh vùng dependency không hiệu quả.
Một trace cho thấy span database chiếm 80% thời gian nhưng không có thông tin về connection pool wait; nhóm phát triển cần tách thời gian chờ lấy connection và thời gian thực thi query để tìm nguyên nhân.
Một API gọi ba dịch vụ song song và một dịch vụ trả chậm; root span kết thúc khi nhánh cuối hoàn tất nhưng dashboard chỉ hiển thị latency trung bình, khiến p99 và nhánh chậm không được nhận diện.
Một hệ thống có trace span chồng lấn do xử lý song song; nhân viên trực cộng thời lượng tất cả span con và cho rằng request mất nhiều giây hơn thực tế, thay vì xem critical path.
Một nhóm điều tra trace có khoảng trống 400 mili giây giữa hai span; thời gian này thực tế nằm ở queue hoặc network nhưng không có span ở producer và consumer để phân biệt thời gian chờ với xử lý.
Một service mesh tự tạo span cho proxy sidecar và ứng dụng cũng tạo span server; trace hiển thị hai span gần giống nhau và nhóm SRE không biết đo latency ở lớp proxy hay ứng dụng.
Một request có retry ba lần tới database và chỉ attempt cuối thành công; trace ghi một span tổng hợp nên đội kỹ thuật không biết hai lần đầu thất bại đã tiêu tốn bao nhiêu thời gian.
Một hệ thống có circuit breaker mở khi dependency lỗi; trace không ghi event trạng thái breaker và không có client span vì request bị chặn trước network, khiến người trực tưởng dependency không được gọi.
Một service sử dụng cache nhưng trace chỉ có span database khi cache miss; khi cache hit tăng bất thường và dữ liệu cũ được trả về, trace không có thông tin cache key hoặc kết quả để điều tra.
Một ứng dụng gọi API đối tác qua DNS service discovery; latency tăng theo vùng nhưng trace chỉ ghi tổng thời gian HTTP, không có thông tin peer address và vùng đích để xác định endpoint chậm.
Một hệ thống có request bị timeout ở client nhưng server vẫn hoàn thành sau đó; trace hiển thị span server thành công và client span lỗi, khiến đội SRE phải phân tích cancellation và deadline propagation.
Một ứng dụng truyền deadline gRPC nhưng service trung gian không chuyển tiếp deadline; request tiếp tục xử lý sau khi người dùng đã hủy và tạo tải không cần thiết, trong khi trace không thể hiện nguyên nhân cancellation.
Một nhóm phân tích trace từ nhiều service có đồng hồ lệch nhau; thời gian span con xuất hiện trước span cha trên timeline và người trực nhầm đây là lỗi propagation dù quan hệ parent-child vẫn đúng.
Một ứng dụng có nhiều region và trace được export qua collector ở vùng khác; latency mạng giữa các vùng bị tính chung với xử lý backend, khiến nhóm kiến trúc khó tách độ trễ ứng dụng khỏi độ trễ truyền dữ liệu.
Một nền tảng dùng trace ID để tìm lỗi nhưng một số service ghi log không có trace ID do context bị mất ở executor; đội SRE phải tái hiện lỗi để thu được bằng chứng đầy đủ.
Một service có p95 latency ổn định nhưng một số trace cụ thể kéo dài hàng chục giây; sampling không giữ các trace chậm nên dashboard trung bình không thể chỉ ra nhóm request gây trải nghiệm xấu.
Một nhóm chỉ instrument HTTP và database nhưng không instrument lock contention trong JVM; trace cho thấy khoảng thời gian xử lý nội bộ lớn mà không có span chi tiết, khiến nguyên nhân nằm ở synchronized block không được phát hiện.
Một ứng dụng xử lý CPU-intensive computation và không có span cho giai đoạn tính toán; trace server span dài nhưng không thể phân biệt CPU-bound với chờ I/O, cần kết hợp profiler để giải thích.
Một hệ thống có lỗi chỉ xuất hiện khi một service phụ thuộc DNS; trace bị cắt ở client span vì resolver không được instrument, khiến nhóm kỹ thuật không biết request chưa bao giờ tới server đích.
Một đội phát triển thêm span cho mọi lần đọc cache và database; khi tải tăng, overhead instrumentation và export làm latency tăng, khiến dữ liệu quan sát tự tạo ra một phần vấn đề đang đo.
Một công ty muốn đo end-to-end latency từ browser tới backend; frontend RUM tạo trace ID nhưng gateway không tiếp nhận context do CORS và header allowlist, khiến hành trình người dùng bị tách.
Một ứng dụng mobile gửi traceparent từ thiết bị nhưng mạng di động có proxy xóa header; backend tạo trace mới và đội hỗ trợ không thể nối trải nghiệm trên thiết bị với các span server.
Một nhóm dùng synthetic test để tạo trace mẫu mỗi phút; trace synthetic không có thuộc tính phân biệt với traffic thật nên dashboard tính cả hai và báo latency thấp hơn trải nghiệm người dùng thực.
Một hệ thống nhận webhook từ đối tác và tạo root span mới tại ingress; đối tác gửi trace ID của họ nhưng nhóm bảo mật không muốn tin hoàn toàn context bên ngoài, cần chính sách link hoặc tiếp nhận có kiểm soát.
Một ứng dụng sử dụng OpenTelemetry Collector để đổi tên service và route trace tới hai backend; processor chỉ áp cho một pipeline nên backend thứ hai nhận attributes khác và hai giao diện hiển thị service map không giống nhau.
Một tổ chức gửi trace tới cả backend nội bộ và nhà cung cấp SaaS; span attributes chứa URL nội bộ và tên database, khiến việc chia sẻ trace bên ngoài cần kiểm tra dữ liệu trước khi export.
Một đội bật debug logging của OpenTelemetry SDK trong production; log chẩn đoán chứa trace payload và metadata người dùng, tạo thêm nguồn dữ liệu nhạy cảm ngoài hệ tracing.
Một doanh nghiệp có nhiều tenant dùng chung collector; resource tenant_id lấy từ client request chưa được xác thực và có thể làm trace của tenant này xuất hiện trong dashboard tenant khác.
Một nhóm phát triển giữ toàn bộ span attributes để điều tra nhưng không đặt giới hạn kích thước; các payload JSON lớn làm exporter batch vượt giới hạn và một số trace bị từ chối.
Một service ghi span event mỗi lần message được xử lý; message burst tạo hàng triệu event và chi phí trace tăng nhanh trong khi người trực chỉ cần các sự kiện lỗi và chuyển trạng thái chính.
Một tổ chức đặt SLO cho tracing pipeline dựa trên tỷ lệ span export thành công nhưng không theo dõi tỷ lệ span bị sampling bỏ có chủ đích; báo cáo chất lượng dữ liệu bị hiểu nhầm là mất dữ liệu.
Một nhóm viết unit test cho hàm tạo span và chỉ xác minh tên span; test không kiểm tra parent context, status, attributes hoặc việc export, khiến lỗi propagation chỉ lộ ra ở production.
Một đội kiểm thử integration trace qua HTTP gateway, Kafka và consumer nhưng chỉ xác nhận request nghiệp vụ thành công; test không kiểm tra trace ID xuyên suốt nên thay đổi middleware làm trace bị đứt mà không ai nhận ra.
Một công ty tạo canary trace đi qua nhiều service và kiểm tra backend mỗi phút; sau deploy, canary có root span nhưng thiếu span ở service cuối, giúp nhóm phát hiện lỗi instrumentation trước khi khách hàng báo.
Một nền tảng có hàng nghìn service và mỗi team tự chọn sampler, exporter và resource attributes; trace không thể so sánh giữa team và chi phí quan sát không dự báo được, khiến tổ chức cần tiêu chuẩn tracing dùng chung.
Một tổ chức muốn giảm chi phí tracing 40% mà vẫn giữ khả năng điều tra p99 và lỗi hiếm; hiện không có số liệu span theo service, sampling reason và kích thước payload để xác định phần nào nên giảm.
Một đội SRE thay đổi retention trace từ 30 ngày xuống bảy ngày nhưng chưa cập nhật quy trình hỗ trợ khách hàng vốn thường điều tra sau hai tuần; nhóm cần đánh giá tác động lên thời gian phát hiện và xử lý sự cố.
Một doanh nghiệp xóa trace theo retention ở backend nhưng các bản export JSON, snapshot và dữ liệu phân tích phụ vẫn tồn tại; đội bảo mật không thể chứng minh yêu cầu xóa telemetry đã bao phủ mọi bản sao.
Một hệ thống gửi traces từ OpenTelemetry Collector tới Tempo nhưng backend không nhận được spans do exporter dùng sai protocol; collector vẫn nhận OTLP từ ứng dụng và health endpoint trả 200, khiến nhóm vận hành cần kiểm tra trạng thái từng chặng export.
Một đội chuyển backend tracing từ Jaeger sang Tempo nhưng giữ nguyên truy vấn dashboard phụ thuộc vào tên tag cũ; trace mới đã lưu nhưng panel latency và service dependency không tìm được dữ liệu theo schema mới.
Một cụm Jaeger lưu trace trong Elasticsearch nhưng index lifecycle xóa dữ liệu nhanh hơn thời hạn công bố; đội hỗ trợ tìm trace của ticket 20 ngày trước và phát hiện backend chỉ còn dữ liệu 7 ngày.
Một hệ thống Tempo dùng object storage và compactor nhưng quyền xóa object bị thiếu; trace hết hạn không còn xuất hiện trong một số truy vấn nhưng dung lượng bucket vẫn tăng, khiến nhóm phải kiểm tra việc xóa vật lý.
Một doanh nghiệp đặt trace retention 30 ngày nhưng bucket lifecycle xóa chunk sau 10 ngày; dashboard không giải thích khác biệt giữa thời hạn ở tracing backend và vòng đời object storage.
Một nhóm bật block retention dài cho Tempo nhưng không tính dung lượng khi tăng sampling; chi phí object storage tăng gấp nhiều lần sau một đợt incident và đội tài chính không biết service nào tạo nhiều spans nhất.
Một tổ chức muốn tìm trace theo mã giao dịch sau 60 ngày nhưng backend chỉ giữ trace 14 ngày; log vẫn lưu trace ID trong 90 ngày và bộ phận hỗ trợ nhầm rằng có thể truy vấn ngược trace từ ID bất kỳ.
Một nền tảng có nhiều tenant dùng chung tracing backend; tenant ID được lấy từ header client mà không xác thực, khiến người dùng có thể tìm kiếm trace thuộc tổ chức khác.
Một nhóm cấp quyền xem trace theo service nhưng span attributes chứa email và mã khách hàng; người có quyền đọc service kỹ thuật vẫn thấy dữ liệu cá nhân không thuộc nhiệm vụ của họ.
Một ứng dụng ghi URL đầy đủ gồm query token vào span http.url; pipeline chỉ che Authorization header và không xử lý query parameter, khiến credential xuất hiện trong trace search.
Một tổ chức cho phép export trace JSON để gửi nhà cung cấp hỗ trợ; file export chứa span events và baggage nhạy cảm, trong khi chính sách chia sẻ chỉ cho phép metadata đã khử định danh.
Một nhóm bảo mật yêu cầu xóa trace của một tenant sau khi kết thúc hợp đồng; trace backend có thể lọc theo tenant nhưng snapshot và bản export phân tích vẫn còn dữ liệu cũ, khiến quy trình xóa chưa hoàn tất.
Một đội SRE chỉ bật tracing cho production và staging dùng tỷ lệ sampling khác nhau; khi điều tra lỗi chỉ xuất hiện ở staging, trace thiếu dữ liệu vì policy môi trường thử nghiệm không đủ chi tiết.
Một service có tỷ lệ lỗi rất thấp nhưng mỗi lỗi gây mất giao dịch; sampling cố định theo tỷ lệ khiến trace của lỗi hiếm thường không được lưu, trong khi yêu cầu của đội sản phẩm là giữ tất cả giao dịch thất bại.
Một hệ thống tail sampling giữ trace có span status ERROR nhưng một số lỗi được biểu diễn bằng span event mà status vẫn UNSET; trace lỗi bị bỏ và nhóm cần thống nhất cách gắn trạng thái trước khi áp policy.
Một ứng dụng có nhiều root span độc lập cho các bước của cùng workflow; tail sampler đánh giá từng trace riêng và không giữ đủ các phần liên quan, khiến việc phân tích hành trình nghiệp vụ không đầy đủ.
Một gateway tail sampling dùng memory limiter và exporter queue chung; trong đợt tải tăng, memory limiter từ chối span trước khi sampler hoàn tất quyết định, làm số trace lỗi được giữ thấp bất thường.
Một tổ chức muốn giữ 100% trace của endpoint chuyển tiền nhưng rule chỉ so khớp tên route đã đổi sau refactor; endpoint mới áp sampling mặc định 2% mà không có cảnh báo cấu hình.
Một nhóm bật parent-based sampler với tỷ lệ thấp ở root nhưng một service downstream tự tạo root span khi mất context; các trace downstream được lấy mẫu độc lập và số liệu trace không còn phản ánh một request xuyên dịch vụ.
Một ứng dụng truyền sampled flag từ client bên ngoài và backend tôn trọng cờ này cho toàn bộ service; người dùng có thể ép hệ thống lưu nhiều trace hơn dự kiến bằng cách gửi cờ sampled bật.
Một công ty dùng trace ID làm khóa correlation trong hệ thống hỗ trợ khách hàng; trace ID bị rút gọn khi ghi vào log để tiết kiệm dung lượng và không còn đủ thông tin để tìm trace gốc.
Một service có log ghi span_id nhưng không ghi trace_id; nhân viên hỗ trợ lấy span ID từ log và tìm kiếm trong giao diện tracing nhưng không thể xác định trace chứa span đó.
Một ứng dụng Java sử dụng nhiều logging framework và MDC bridge; một framework có trace_id nhưng framework khác không có, khiến log của cùng request bị chia thành bản ghi có và không có correlation.
Một hệ thống xử lý request trên thread pool và có filter xóa MDC ở cuối request; exception trước khi filter chạy cleanup khiến thread tiếp theo mang trace context cũ, tạo nhầm lẫn trong log điều tra.
Một nhóm sử dụng OpenTelemetry API nhưng tự tạo Context storage riêng; instrumentation tự động dùng Context global còn span thủ công dùng storage riêng, khiến hai loại span không có quan hệ cha-con.
Một thư viện nội bộ tự wrap HTTP client để inject traceparent nhưng không kiểm tra header đã có; request bị gửi hai giá trị traceparent và server nhận không biết nên dùng context nào.
Một gateway tạo trace mới cho mỗi request và muốn liên kết với trace ID do đối tác gửi; nhóm phát triển đang cân nhắc tiếp nhận context trực tiếp hay tạo span link để giữ ranh giới tin cậy.
Một ứng dụng dùng W3C Trace Context nhưng header traceparent bị proxy viết lại version không hợp lệ; backend từ chối context và tạo trace mới mà không ghi metric về số header bị loại.
Một service có tracestate chứa thông tin vendor và dữ liệu nội bộ; header được forward tới đối tác ngoài tổ chức dù chính sách chỉ cho phép truyền traceparent, tạo rủi ro tiết lộ metadata.
Một hệ thống truyền baggage với khóa debug=true để bật log chi tiết ở downstream; client có thể tự thêm khóa này và kích hoạt chế độ ghi log nhiều dữ liệu nhạy cảm trên nhiều service.
Một tổ chức dùng baggage để truyền customer tier và region; các service đọc giá trị mà không xác thực nguồn, dẫn đến phân loại sai tenant và route trace vào backend có quyền truy cập khác.
Một ứng dụng dùng trace ID trong URL callback để tương quan sự kiện; URL được ghi vào access log của proxy và có thể bị chia sẻ ra ngoài, khiến định danh trace bị lộ qua nhiều hệ thống.
Một nhóm instrument ứng dụng bằng agent nhưng không khóa phiên bản agent trong image; sau khi node tải bản mới, các pod cùng service tạo span attributes khác nhau và lỗi chỉ xuất hiện ở một phần replica.
Một service có instrumentation library được đóng gói riêng trong ứng dụng và Java agent cũng instrument cùng JDBC driver; mỗi query tạo hai client span và flame graph thể hiện thời gian database gấp đôi.
Một tổ chức dùng OpenTelemetry Collector để tail sample nhưng collector nhận spans từ nhiều service qua load balancer không có affinity theo trace ID; trace bị phân tán giữa replica và sampling quyết định không nhất quán.
Một đội kiểm thử chỉ chạy trace test trong một request đơn lẻ; lỗi context leak chỉ xuất hiện khi nhiều request đồng thời dùng chung worker thread nên test không phát hiện trước khi deploy.
Một hệ thống cần kiểm tra trace propagation qua HTTP, Kafka và worker nền; test chỉ xác nhận root trace được export và không so sánh trace ID, parent span ID cùng span link ở từng ranh giới.
Một nhóm muốn đo tỷ lệ request có trace end-to-end nhưng chỉ kiểm tra số lượng root span tại gateway; downstream spans có thể bị mất mà dashboard coverage vẫn báo 100%.
Một nền tảng không có monitor cho exporter failures và queue backlog; trace backend dừng nhận dữ liệu trong 40 phút nhưng service vẫn hoạt động, khiến đội SRE phát hiện muộn qua khiếu nại khách hàng.
Một tổ chức xây tracing SLO theo tỷ lệ trace có đủ span ở các service trọng yếu; hệ thống chỉ đếm trace được lưu mà không kiểm tra các span bắt buộc, nên dữ liệu thiếu chặng vẫn được tính là thành công.
Một công ty cần giới hạn overhead tracing dưới 2% CPU của service; sau khi thêm custom span cho mọi method, không có benchmark trước và sau nên nhóm không biết instrumentation ảnh hưởng bao nhiêu tới latency.
Một ứng dụng serverless tạo trace cho mỗi invocation nhưng exporter flush khi runtime freeze; các span cuối cùng không được gửi và dashboard cho thấy số trace thấp hơn số invocation.
Một hệ thống dùng trace để tìm nguyên nhân memory leak nhưng sampling chỉ giữ request có lỗi HTTP; memory tăng dần không làm request thất bại nên không có trace nào được giữ ở thời điểm bất thường.
Một nhóm phân tích p99 dựa trên trace được lấy mẫu theo xác suất nhưng không hiệu chỉnh trọng số; các request dài hiếm có khả năng bị thiếu và percentile báo thấp hơn phân phối request thực.
Một công ty thay đổi sampling rate giữa hai tuần và so sánh số lượng trace lỗi trực tiếp; lưu lượng thực tế không đổi nhưng số trace tăng gấp năm do policy, khiến báo cáo chất lượng dịch vụ sai lệch.
Một hệ thống dùng trace để phân tích dependency nhưng các span từ proxy và ứng dụng cùng đại diện một HTTP call; service map đếm hai lần lưu lượng và tỷ lệ lỗi của dependency bị phóng đại.
Một nhóm điều tra lỗi retry thấy nhiều span client có cùng operation name nhưng không có attempt number hoặc retry reason; họ không xác định được lần thử nào nhận lỗi và lần nào thành công.
Một ứng dụng ghi span status OK ở cuối request dù một span con database đã ERROR; dashboard tổng hợp theo root span báo thành công và không hiển thị các lỗi đã được retry hoặc fallback.
Một nền tảng có trace từ nhiều service và các span con kết thúc sau root span do công việc nền; backend hiển thị trace kéo dài bất thường và đội vận hành cần quyết định dùng span link hay workflow trace riêng.
Một tổ chức có trace từ mobile client và backend nhưng thiết bị có đồng hồ sai; timeline hiển thị span client xảy ra sau response server và người trực nhầm là lỗi thứ tự xử lý.
Một đội dùng trace để đo thời gian chờ queue nhưng chỉ tạo span ở consumer khi bắt đầu xử lý; thời gian từ lúc producer publish tới khi consumer nhận không được đo, khiến backlog latency bị bỏ sót.
Một hệ thống có nhiều message retry và redelivery; mỗi attempt tạo trace mới không có liên kết với message gốc, làm số workflow trong dashboard tăng hơn số nghiệp vụ thực tế.
Một công ty muốn giữ trace cho các sự kiện audit nhưng sampler chỉ giữ span có latency cao hoặc status error; thao tác phân quyền thành công và nhanh không được lưu dù có giá trị kiểm toán.
Một nhóm đưa dữ liệu tài khoản vào span attributes để điều tra lỗi thanh toán nhưng không có quy tắc redaction ở collector; dữ liệu đã xuất tới backend ngoài tổ chức trước khi phát hiện.
Một nền tảng yêu cầu trace phải được xóa sau 14 ngày nhưng log chứa trace ID được giữ 90 ngày; người dùng có thể suy ra hành trình giao dịch từ log còn lại dù trace payload đã bị xóa.
Một đội vận hành thay đổi backend tracing và di chuyển dữ liệu cũ; trace ID được giữ nhưng resource attributes service.name và environment bị chuyển sai, khiến người dùng truy vấn nhầm service sau migration.
Một tổ chức khôi phục snapshot tracing từ trước khi có yêu cầu xóa dữ liệu; trace đã hết hạn xuất hiện trở lại sau restore và quy trình phục hồi chưa có bước áp lại danh sách xóa.
Một công ty muốn giảm chi phí bằng cách hạ retention traces xuống ba ngày nhưng thời gian phát hiện lỗi từ khách hàng trung bình là năm ngày; dữ liệu chẩn đoán biến mất trước khi đội hỗ trợ nhận ticket.
Một nhóm dùng backend tracing chung cho production và development; trace của môi trường phát triển chiếm phần lớn quota và làm trace thanh toán production bị từ chối trong giờ cao điểm.
Một tổ chức phân bổ chi phí tracing theo service nhưng một số span không có service.name hoặc owner; báo cáo chi phí dồn vào unknown và không nhóm nào nhận trách nhiệm tối ưu lượng trace.
Một hệ thống đặt giới hạn kích thước attribute và span event nhưng không theo dõi số span bị truncate; nhóm điều tra thấy trace có status lỗi nhưng thiếu exception detail mà không biết dữ liệu bị cắt ở SDK hay backend.
Một ứng dụng có trace ID được truyền đúng nhưng exporter bỏ qua một số spans vì payload vượt giới hạn; trace vẫn xuất hiện ở giao diện với root span và không báo rõ các span con đã bị từ chối.
Một nhóm xây dashboard về tracing pipeline chỉ theo dõi số span nhận được; khi sampling rate thay đổi, dashboard tưởng ingestion bị giảm và tạo incident dù đó là thay đổi chính sách có chủ đích.
Một doanh nghiệp cần so sánh trace coverage trước và sau khi nâng cấp agent; không có canary request cố định hoặc bộ trace mẫu nên không xác định được chênh lệch do code hay cấu hình.
Một đội SRE muốn xác minh trace của một giao dịch đi qua đủ gateway, service và consumer; hiện không có test định kỳ tạo giao dịch mẫu và kiểm tra span bắt buộc trong backend.
