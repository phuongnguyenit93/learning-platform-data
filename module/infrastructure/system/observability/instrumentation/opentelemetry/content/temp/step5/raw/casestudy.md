Một hệ thống đặt hàng Java/Spring Boot đã có log và metric HTTP nhưng không lần theo được yêu cầu đi qua gateway, order-service và payment-service; mỗi đội quan sát một dịch vụ riêng và không biết bước nào gây chậm toàn giao dịch.
Nhóm gắn OpenTelemetry Java agent vào ứng dụng Spring Boot nhưng dashboard không thấy trace; tiến trình khởi động không nhận được tham số agent ở môi trường Kubernetes dù file JAR có trong image.
Một dịch vụ Spring Boot vừa dùng OpenTelemetry Java agent vừa cài thư viện instrumentation tự động cho cùng HTTP client; một lời gọi sang upstream tạo hai client span gần giống nhau khiến thời gian trên trace khó diễn giải.
Ứng dụng đang dùng Spring Boot Actuator và Micrometer để xuất metrics, sau đó bổ sung OpenTelemetry SDK riêng; dashboard xuất hiện hai chuỗi request metric khác tên và số lượng request được báo cáo không khớp.
Nhóm cấu hình OpenTelemetry SDK thủ công ở một module thư viện dùng chung; mỗi lần module được khởi tạo lại tạo thêm provider và exporter, làm số thread nền cùng kết nối tới Collector tăng.
Một ứng dụng Java chạy trên laptop có trace nhưng phiên bản đóng gói thành container không xuất gì; biến môi trường của OpenTelemetry được đặt ở script cục bộ mà chưa có trong manifest triển khai.
Đội phát triển muốn đổi từ instrument tự động sang manual instrumentation cho một service; sau phát hành, trace có thêm server span lồng trong server span dù logic nghiệp vụ chỉ có một request.
Ứng dụng dùng hai bản thư viện OpenTelemetry API và SDK không tương thích trong cùng classpath; tiến trình khởi động báo lỗi phương thức không tồn tại sau lần nâng cấp dependency.
Một batch job Java hoàn tất công việc rồi thoát ngay lập tức; Collector chỉ nhận được một phần trace cuối vì tiến trình kết thúc trước khi exporter gửi hết các span đang đệm.
Ứng dụng đổi cấu hình OTEL_SERVICE_NAME giữa dev, staging và production nhưng một số pod vẫn dùng tên mặc định; service map chia cùng một service thành nhiều thực thể không thể so sánh.
Một dịch vụ chạy ba phiên bản ứng dụng đồng thời sau rolling deployment nhưng thiếu deployment.environment và service.version trong resource attributes; không thể xác định phiên bản nào tạo nhiều lỗi hơn.
Nhóm đặt service.instance.id bằng một giá trị tĩnh dùng chung cho toàn bộ replica; dashboard không thể phân biệt instance đang lỗi dù mỗi pod gửi telemetry độc lập.
Đội nền tảng gắn cả tên pod, container và node vào mọi span dưới dạng thuộc tính riêng, nhưng thông tin resource được gửi không nhất quán giữa agent và Collector khiến việc lọc theo Kubernetes khó tin cậy.
Trong ứng dụng Spring MVC, nhóm tạo custom span cho bước xác nhận thanh toán nhưng đặt tên bằng mã đơn hàng; số lượng tên operation tăng liên tục và công cụ truy vấn trace khó nhóm theo nghiệp vụ.
Một endpoint báo cáo có ba bước kiểm tra quyền, đọc database và dựng dữ liệu; trace tự động chỉ có span HTTP bên ngoài nên đội phát triển không biết bước nghiệp vụ nào chiếm phần lớn thời gian.
Nhóm tạo span mới cho mỗi phép gán giá trị trong vòng lặp xử lý 100 nghìn dòng; một request sinh hàng trăm nghìn span và độ trễ tăng mạnh sau khi bật tracing.
Một bộ xử lý đơn hàng tạo span bằng API OpenTelemetry nhưng không kết thúc span khi nhánh exception xảy ra; giao diện quan sát hiển thị nhiều span kéo dài và exporter bắt đầu dùng thêm bộ nhớ.
Ứng dụng ghi exception trong log nhưng custom span vẫn có trạng thái OK khi request thất bại; dashboard trace tính tỷ lệ lỗi thấp hơn những lỗi nghiệp vụ mà người dùng nhìn thấy.
Một tác vụ bắt lỗi gọi đối tác và tự phục hồi bằng fallback, nhưng mọi span trong trace đều bị đánh dấu ERROR; nhóm vận hành không phân biệt được lỗi đã được xử lý với thất bại thực sự của yêu cầu.
Đội triển khai gắn toàn bộ stack trace vào span attributes thay vì ghi nhận sự kiện lỗi; kích thước span và chi phí lưu telemetry tăng sau một đợt exception hàng loạt.
Trong một custom span, code lấy Span.current trước khi mở đúng scope nên phần lớn sự kiện và thuộc tính nghiệp vụ được ghi vào span cha thay vì span đang xử lý.
Một đoạn mã Java mở scope cho span ở đầu phương thức nhưng không đóng scope khi return sớm; các request tái sử dụng thread bắt đầu có parent span không thuộc request hiện tại.
Nhóm tạo span độc lập trong callback hoàn tất thanh toán mà không liên kết context gốc; cùng một giao dịch hiển thị thành hai trace tách biệt dù chạy trên cùng JVM.
Ứng dụng dùng CompletableFuture.supplyAsync trên thread pool; trace đến bước đặt hàng rồi mất các span của công việc chạy nền vì context không đi theo luồng thực thi mới.
Một phương thức Spring Boot gắn @Async gửi email xác nhận sau khi tạo đơn; log worker có nội dung đúng nhưng trace_id khác với request sinh công việc nên người trực không liên kết được hai giai đoạn.
Một ứng dụng WebFlux tạo context tracing trong luồng imperative nhưng tiếp tục bằng Reactor chain; trace trên các thread xử lý bất đồng bộ bị đứt sau khi chuyển scheduler.
Nhóm tối ưu request bằng parallelStream trên một danh sách sản phẩm; những custom span trong nhánh song song có parent không ổn định, và service map xuất hiện nhiều root span lạ.
Một Scheduled task Spring chạy ngoài request HTTP và phát hiện đơn quá hạn; người vận hành kỳ vọng trace này có parent HTTP dù nó được kích hoạt độc lập nhiều giờ sau yêu cầu gốc.
Trong pipeline xử lý Kafka, producer gửi sự kiện tạo đơn kèm trace context nhưng consumer không extract headers; span xử lý thông điệp xuất hiện như root trace khác với HTTP request ban đầu.
Một consumer Spring Kafka xử lý lại bản tin sau lỗi, nhưng mỗi lần retry dùng cùng trace_id và không có dấu hiệu attempt; đội vận hành không phân biệt lần xử lý đầu với lần thử lại trong trace.
Ứng dụng nhận batch Kafka gồm nhiều sự kiện từ nhiều producer; nhóm tạo một consumer span có duy nhất parent từ sự kiện đầu, làm lịch sử các sự kiện còn lại không có quan hệ quan sát rõ ràng.
Một ứng dụng Spring AMQP gửi message qua RabbitMQ và worker xử lý bất đồng bộ; bên phát ghi context vào payload nghiệp vụ nhưng bên nhận chỉ đọc message headers, khiến trace bị tách sau hàng đợi.
Đội phát triển truyền traceparent sang một đối tác HTTP nhưng đối tác dùng format B3 mà không hỗ trợ W3C Trace Context; cùng request xuất hiện thành hai trace ở hai nền tảng.
Gateway gửi traceparent đúng chuẩn W3C nhưng một service trung gian tạo request HTTP mới mà không inject context; toàn bộ span downstream bị gắn vào trace khác sau service này.
Ứng dụng dùng RestTemplate qua proxy mà tracing chỉ bọc WebClient; các lời gọi tới hệ thống thanh toán không xuất hiện trong trace dù proxy access log xác nhận request đã được gửi.
Một dịch vụ chuyển từ RestTemplate sang WebClient; sau phát hành, trace vẫn có server span nhưng phần lớn client span biến mất vì cấu hình instrumentation không bao phủ HTTP client mới.
Nhóm tự thêm header traceparent bằng cách nối chuỗi từ trace_id nhưng thiếu thông tin trace flags và parent id; upstream từ chối hoặc bỏ qua context không hợp lệ.
Trình duyệt gửi traceparent vào API cross-origin; sau khi bật propagation ở frontend, các request có header mới bị chặn bởi CORS preflight trên gateway trước khi vào Spring Boot.
Một hệ thống có ingress proxy tạo trace mới cho mọi request và bỏ traceparent từ client; trace backend có dữ liệu nhưng không nối được với tương tác trên ứng dụng web.
Ứng dụng nhận trace context từ hệ thống không đáng tin cậy rồi sao chép nguyên trạng vào tất cả downstream; nhóm bảo mật phát hiện trace ID do đối tác tự đặt gây khó khăn khi phân biệt các nguồn.
Một nhà phát triển đưa email và mã khách hàng vào OpenTelemetry baggage để chuyển qua nhiều microservice; các header mang dữ liệu cá nhân được gửi cả tới những dịch vụ không cần thông tin này.
Nhóm gắn nhiều trường tìm kiếm và giỏ hàng vào baggage; mỗi lần gọi HTTP mang header lớn hơn, một số request bị gateway từ chối vì vượt giới hạn header.
Service A gắn region vào baggage nhưng service B chỉ đọc span attribute và không thấy giá trị; các nhóm tưởng OpenTelemetry sẽ tự chuyển mọi attribute sang downstream.
Trong một pipeline async, trace context được truyền qua task queue nhưng baggage tenant bị mất vì cơ chế lưu context chỉ sao chép traceparent; log của worker thiếu phạm vi tenant để khoanh vùng.
Một service Java phát logs qua Logback với MDC thủ công; sau khi bật tracing, log HTTP có trace_id nhưng log ở CompletableFuture lại thiếu trace_id khi chạy trên thread khác.
Đội phát triển thêm trace_id và span_id vào structured logs nhưng format JSON của shipper đổi tên các trường; liên kết từ log explorer sang trace viewer không hoạt động.
Một hệ thống ghi log với trace_id theo định dạng chữ hoa trong khi backend traces lưu dạng chữ thường; khi tìm chính xác trace ID từ log, người trực không tìm thấy span tương ứng.
Nhóm cài OpenTelemetry Java agent để có traces nhưng kỳ vọng log body tự động được xuất qua cùng exporter; dashboard logs trống trong khi ứng dụng vẫn ghi file Logback bình thường.
Ứng dụng dùng nhiều appender Logback xuất log trực tiếp và qua OpenTelemetry; sau lần triển khai, cùng một sự kiện xuất hiện hai lần trong kho log tập trung.
Một transaction thanh toán có trace_id nhưng log ngoại lệ được ghi ngoài context span đang active; chỉ những dòng DEBUG trước exception có thể liên kết với trace, còn dòng ERROR quan trọng nhất không có correlation.
Đội vận hành bật thu thập exception stack trace đầy đủ cho mọi span và log; khi upstream lỗi liên tục, dung lượng telemetry tăng đột biến và chi phí lưu trữ vượt ngân sách.
Ứng dụng gắn số thẻ thanh toán và Authorization header vào span attributes để dễ truy vết; dữ liệu nhạy cảm được gửi sang Collector dùng chung nhiều nhóm.
Một nhóm muốn tìm lỗi một người dùng cụ thể nên gắn user_id vào metric labels; khi tài khoản tăng lên hàng triệu, số time series bùng nổ dù số endpoint cố định.
Nhóm gắn order_id vào span attributes rồi dùng cùng thuộc tính đó làm nhãn histogram metric; một thay đổi instrumentation làm cardinality metric tăng nhanh và backend lưu trữ bị nghẽn.
Một HTTP server span đặt tên theo URL thực tế chứa mã đơn, thay vì route template; trace backend không thể thống kê độ trễ theo nhóm endpoint vì mỗi đơn tạo một tên mới.
Ứng dụng Spring Boot phát metric độ trễ HTTP có nhãn status_code theo chuỗi '200 OK' trong khi service khác dùng '200'; dashboard tổng hợp tỷ lệ lỗi không nhất quán giữa các service.
Nhóm chuyển phiên bản OpenTelemetry semantic conventions, làm tên thuộc tính HTTP của span cũ và mới khác nhau; bộ lọc dashboard chỉ hiển thị một nửa traffic trong rolling deployment.
Thông tin cơ sở dữ liệu trong span từ JDBC driver khác với các span SQL được tạo thủ công; hai nhóm đặt db.system và tên thao tác khác nhau nên không thể so sánh độ trễ theo database.
Một dịch vụ ghi nguyên câu SQL chứa giá trị tham số nhạy cảm vào trace; sau khi tăng sampling để điều tra lỗi database, nhiều thông tin khách hàng bị xuất sang hệ thống quan sát.
Đội phát triển gắn exception message trực tiếp vào nhãn metric lỗi; mỗi message chứa ID khác nhau làm số chuỗi metric tăng vượt dự tính chỉ sau vài giờ.
Một ứng dụng Spring Boot xuất số request thành counter nhưng dashboard lại đọc giá trị tích lũy thay vì tốc độ trên cửa sổ thời gian; mỗi lần pod restart đường lưu lượng đột ngột giảm.
Nhóm triển khai histogram latency với đơn vị mili giây ở một service và giây ở service khác; metric có tên tương tự khiến báo cáo p95 toàn hệ thống lệch lớn.
Một dịch vụ định kỳ đọc dung lượng hàng đợi để xuất ObservableGauge, nhưng callback thỉnh thoảng gọi tới database chậm; quá trình collect metrics kéo dài và có lần bị timeout.
Trong ứng dụng quản lý đơn, nhóm dùng UpDownCounter cho số đơn đang xử lý nhưng một nhánh lỗi không giảm giá trị; dashboard liên tục tăng dù queue và thread pool đã về mức bình thường.
Một API phát counter request cả trong HTTP filter và interceptor do hai nhóm phát triển độc lập; tổng số request trên dashboard tăng gần gấp đôi sau khi ghép instrumentation.
Nhóm đổi từ bộ đo histogram tự viết sang SDK OpenTelemetry nhưng không xóa tên metric cũ; dashboard đang cộng cả hai nguồn dẫn đến số liệu latency không phản ánh traffic thực.
Ứng dụng ghi metric số đơn hàng thành công và trace cho toàn bộ request, nhưng thiếu exemplar hoặc liên kết ngữ cảnh thích hợp; người trực không thể mở một trace liên quan trực tiếp từ điểm bất thường trên biểu đồ.
Một Java worker chạy batch tạo metrics theo nhãn job_type nhưng nhãn được lấy từ tên tệp đầu vào thay đổi liên tục; sau vài ngày backend metrics báo vượt giới hạn series.
Nhóm gắn tài khoản tenant vào mọi metric từ Java agent thông qua resource attribute; khi một tiến trình phục vụ nhiều tenant, các metric không thể phân biệt chính xác request theo tenant như nhóm kỳ vọng.
Trên cùng ứng dụng, thư viện tự viết dùng MeterProvider riêng với exporter khác Java agent; metric JVM và metric nghiệp vụ đến hai nơi khác nhau và dashboard dịch vụ không hiển thị đầy đủ.
Đội phát triển cấu hình head-based sampling 1% trên các dịch vụ giao dịch; lỗi thanh toán hiếm xuất hiện trong logs nhưng phần lớn không có trace tương ứng để phân tích.
Service A dùng sampler AlwaysOn còn service B dùng ParentBased với sampled flag từ upstream; số trace được giữ sau B khác giả định của đội vận hành khi A nhận request chưa được lấy mẫu.
Gateway lấy mẫu trace ở mức 5% nhưng backend tạo root span mới cho mỗi request không có context; backend lưu hàng loạt trace không liên kết và chi phí tăng dù tỷ lệ sampling đầu vào thấp.
Trong giờ cao điểm, nhân viên phát hiện trace chậm nhất bị thiếu khỏi bộ lưu trữ do head sampling chọn ngẫu nhiên trước khi biết kết quả; dashboard latency vẫn chỉ ra p99 tăng.
Nhóm bật tail sampling trong OpenTelemetry Collector để giữ trace lỗi nhưng pipeline phân tán các span của cùng trace qua nhiều collector không dùng chung trạng thái; nhiều trace chỉ có một phần span.
Collector sử dụng tail sampling với thời gian chờ quyết định ngắn hơn thời gian xử lý một workflow bất đồng bộ; các span đến muộn không được giữ cùng quyết định với phần đầu của trace.
Nhóm tăng tỷ lệ giữ traces trên môi trường production trong một sự cố; Collector bắt đầu dùng quá nhiều bộ nhớ và bỏ dữ liệu ngay lúc cần phân tích nhất.
Ứng dụng đã có parent-based sampling nhưng một service trung gian bỏ trace flags khi truyền header; downstream quyết định lấy mẫu khác nhau, khiến những trace được giữ thiếu nhiều span.
Nhóm cấu hình nhiều processor sampling ở Collector mà không ghi nhận tỷ lệ dữ liệu bị bỏ tại từng điểm; sau triển khai, số trace sụt mạnh nhưng không biết mất tại SDK, gateway hay backend.
Một hệ thống dùng logging để ghi 100% lỗi và tracing lấy mẫu 2%; khi đối chiếu báo cáo lỗi, đội trực tưởng exporter mất dữ liệu vì số exception log cao hơn số error spans.
Collector nhận OTLP gRPC ở cổng 4317 nhưng ứng dụng Java cấu hình endpoint theo HTTP/protobuf tới cùng cổng; exporter báo lỗi kết nối hoặc phản hồi không hợp lệ dù Collector đang chạy.
Một service gửi OTLP/HTTP tới đường dẫn không khớp endpoint traces của Collector; metrics vẫn được xuất còn traces liên tục thất bại sau lần đổi biến môi trường.
Ứng dụng Java cấu hình OTLP exporter tới localhost:4317 bên trong container riêng; Collector chạy ở pod khác nên tiến trình liên tục thử kết nối chính nó thay vì service Collector trong Kubernetes.
Nhóm bật TLS trên OTLP receiver của Collector nhưng một số Java exporter vẫn kết nối plaintext; các service này không xuất được telemetry và error log hiển thị lỗi bắt tay.
Collector dùng chứng chỉ do private CA cấp, trong khi JVM chỉ tin CA công cộng; exporter OTLP liên tục báo lỗi certificate verify failed dù endpoint DNS và TCP đều truy cập được.
Một cụm Kubernetes dùng Collector gateway nhận dữ liệu từ nhiều namespace; sau khi network policy chặn kết nối egress của một namespace, chỉ telemetry của nhóm ứng dụng đó biến mất.
OpenTelemetry Collector nhận traces và metrics qua receiver nhưng cấu hình pipeline chưa kết nối exporter tương ứng; endpoint receiver vẫn phản hồi trong khi dashboard đích không có dữ liệu.
Đội nền tảng bật processor đổi tên service.name trên Collector để đồng nhất dashboard; một số service bị gom nhầm vào cùng tên và service map không phân biệt được luồng nghiệp vụ.
Collector thêm k8sattributes vào telemetry để truy xuất namespace và pod, nhưng thiếu quyền đọc metadata Kubernetes; biểu đồ theo namespace có nhiều chuỗi nhãn rỗng.
Một cluster dùng Collector ở chế độ DaemonSet để nhận log và gateway trung tâm để xử lý trace; khi route exporter thay đổi, một phần dữ liệu bị gửi vòng qua nhiều Collector và độ trễ ingest tăng.
Nhóm áp batch processor với kích thước lô lớn để tiết kiệm overhead mạng; những service rất ít request chỉ xuất hiện trace trên dashboard sau một khoảng trễ dài.
Trong đợt bão hòa bộ lưu trữ tracing, exporter Collector retry liên tục và bộ đệm đầy; một phần dữ liệu bị drop nhưng ứng dụng Java vẫn trả request thành công.
Một Collector dùng memory limiter nhưng không có hàng đợi và cơ chế retry phù hợp; khi backend ngừng nhận dữ liệu, metrics bị thiếu theo từng đợt trong lúc pod vẫn khỏe.
Nhóm cấu hình file storage cho sending queue của Collector nhưng volume của pod không bền vững; sau khi pod restart giữa outage, telemetry chờ gửi biến mất.
Một backend telemetry áp hạn mức request mỗi giây và phản hồi 429; Collector tăng retry/backoff, còn dashboard mất dữ liệu ở giờ cao điểm dù ứng dụng không có lỗi nghiệp vụ.
Collector và SDK được đặt giữa mạng liên vùng có độ trễ cao; khi endpoint OTLP phản hồi chậm, thread exporter và bộ đệm trong JVM tăng sử dụng bộ nhớ.
Đội triển khai Collector dùng duy nhất một replica cho cả cụm; khi node chạy pod đó bảo trì, tất cả ứng dụng tiếp tục hoạt động nhưng traces, metrics và logs có khoảng trống.
Nhóm nâng cấp OpenTelemetry Collector và một processor cấu hình cũ không còn hợp lệ; collector mới không khởi động được trong khi các Java agent tiếp tục gửi telemetry vào địa chỉ service.
Một ứng dụng dùng Java agent cũ sau khi Collector thay chính sách giao thức OTLP; trace vẫn có trên một môi trường nhưng không xuất ở production do cấu hình exporter của các pod không đồng bộ.
Backend lưu trace dùng tên service đặt theo resource attributes nhưng log platform dùng tên ứng dụng do Fluent Bit gắn; người trực không thể tìm log bằng thông tin service nhìn thấy ở trace.
Nhóm triển khai công cụ hiển thị distributed trace nhưng thời gian span giữa các service chồng chéo bất hợp lý; đồng hồ của các node Kubernetes không đồng bộ và dashboard sắp xếp timeline khó tin cậy.
Một endpoint HTTP báo 500 sau khi gọi database chậm, nhưng trace chỉ có span ngoài mà thiếu JDBC instrumentation; người trực chưa thể phân biệt thời gian ở truy vấn SQL với xử lý Java.
Trong một trace có nhiều request con chạy song song, nhóm cộng toàn bộ duration của các client span và kết luận sai rằng tổng thời gian HTTP phải lớn hơn thời gian server span cha.
Ứng dụng có nhiều bản ghi lỗi 404 do bot nhưng OpenTelemetry HTTP server spans đều được tính vào error rate như lỗi 500; dashboard phản ánh chất lượng ứng dụng khác với định nghĩa SLI của nhóm.
Nhóm chỉ xem span status và không đối chiếu HTTP status code, nên một request thất bại theo nghiệp vụ nhưng trả 200 không được coi là lỗi; số error trace thấp hơn số lần thanh toán thất bại.
Một người dùng gửi yêu cầu tạo đơn rồi ứng dụng trả 202 và xử lý qua queue trong năm phút; trace HTTP kết thúc sớm khiến người trực nhầm toàn bộ quy trình đã hoàn thành.
Nhóm triển khai instrumentation cho việc xử lý task bất đồng bộ có nhiều message đầu vào; chỉ dùng quan hệ parent-child làm đồ thị trace không thể hiện rõ mối liên hệ giữa các sự kiện hội tụ.
Ứng dụng thử ghi các bước quan trọng vào Span.addEvent nhưng event name là chuỗi chứa order ID; khi điều tra, hệ thống không thể nhóm các loại sự kiện nghiệp vụ tương tự.
Đội vận hành so sánh p95 từ histogram metric với p95 của những trace đã được tail-sample theo lỗi; hai giá trị chênh lệch lớn vì tập request được giữ ở tracing không đại diện toàn lưu lượng.
Nhóm chuyển SDK và semantic conventions giữa hai phiên bản Spring Boot; cùng một loại HTTP operation có tên span, thuộc tính và metric khác nhau, khiến dashboard lịch sử bị đứt đoạn.
Một team bổ sung OpenTelemetry instrumentation vào thư viện Java dùng chung và mặc định ghi mọi lỗi dưới dạng span event; nhiều ứng dụng sử dụng thư viện này tăng lượng telemetry dù không thay đổi luồng HTTP.
Trong một đợt áp dụng Java agent, CPU của ứng dụng tăng và thời gian khởi động lâu hơn; nhóm chưa có baseline để tách overhead instrumentation khỏi thay đổi traffic và GC.
Đội phát triển chỉ kiểm thử rằng Collector nhận được một trace mẫu, nhưng chưa xác minh context qua HTTP, Kafka và CompletableFuture; sau phát hành production, trace vẫn bị đứt ở các ranh giới bất đồng bộ.
Trong một sự cố, nhóm bật log TRACE và tăng sampling lên 100% mà không giới hạn thời gian; khối lượng dữ liệu quan sát tăng mạnh khiến chính pipeline telemetry thành nút thắt cho ứng dụng cần điều tra.
Một dịch vụ Java ghi trace_id trong log, tạo histogram latency và xuất span qua OTLP nhưng mỗi tín hiệu mang service.name và environment khác nhau; người trực không kết nối được metric bất thường, log lỗi và trace liên quan.
