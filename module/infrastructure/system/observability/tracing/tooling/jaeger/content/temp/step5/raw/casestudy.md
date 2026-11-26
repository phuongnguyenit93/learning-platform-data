Một nền tảng thương mại điện tử nâng Jaeger lên v2 nhưng giữ nguyên cấu hình triển khai từ phiên bản cũ; tiến trình mới khởi động mà không nạp đủ receiver, processor và exporter nên UI không có trace mới.
Nhóm chuyển Jaeger sang kiến trúc dựa trên OpenTelemetry Collector nhưng chỉ cấu hình OTLP receiver; chưa có pipeline traces nối receiver với exporter lưu trữ nên endpoint ingest vẫn mở mà dữ liệu không được ghi.
Jaeger v2 chạy với cấu hình Collector hợp lệ về cú pháp nhưng thiếu thành phần storage cần thiết; tiến trình báo lỗi khởi tạo extension và không sẵn sàng nhận trace.
Một cấu hình Jaeger v2 khai báo receiver và exporter nhưng quên đưa chúng vào service pipeline; các component được khởi tạo nhưng không có luồng dữ liệu thực tế.
Đội triển khai một bản Jaeger v2 mới cùng cấu hình cũ có tên component đã thay đổi; một số thành phần không còn được nhận diện và hệ thống chỉ khởi động sau khi bỏ phần cấu hình lỗi.
Nhóm vận hành gộp ingest, query và storage vào một pod để thử nghiệm; khi lượng trace tăng, truy vấn UI và xử lý OTLP cạnh tranh CPU, làm cả hai cùng chậm.
Một cụm Jaeger v2 tách collector và query service thành các deployment riêng; service query trỏ tới backend storage khác với exporter đang ghi nên UI hiển thị dữ liệu cũ.
Đội nâng cấp Jaeger v1 lên v2 nhưng vẫn để ứng dụng gửi qua endpoint agent cũ; traffic không đến OTLP receiver mới và số trace ingest giảm về không.
Ứng dụng Java gửi OTLP gRPC đến cổng 4317 của Jaeger v2 nhưng Service Kubernetes chỉ expose cổng HTTP/protobuf; kết nối bị từ chối dù pod Jaeger đang Running.
Exporter OTLP/HTTP gửi request đến endpoint gRPC của Jaeger v2; client retry liên tục và collector không nhận được span nào.
Một service gửi OTLP đến địa chỉ localhost trong container ứng dụng trong khi Jaeger v2 chạy ở namespace khác; exporter không thể kết nối vì endpoint không phải Collector sidecar.
Nhóm đổi DNS service Jaeger nhưng một số pod ứng dụng giữ connection pool tới IP cũ; trace từ các pod đó biến mất trong khi các pod mới gửi bình thường.
Jaeger v2 nhận trace qua load balancer nhưng health check chỉ kiểm tra cổng TCP; backend storage chưa sẵn sàng nên request ingest được nhận rồi thất bại ở bước export.
Gateway OTLP nhận traffic qua TLS nhưng Java exporter vẫn dùng plaintext; handshake thất bại và log ứng dụng báo lỗi gửi span theo chu kỳ.
Jaeger v2 bật xác thực cho OTLP receiver nhưng một nhóm ứng dụng chưa được cấp credential mới; các trace từ nhóm này bị trả 401 dù những service khác vẫn hoạt động.
Chứng chỉ TLS của endpoint OTLP được gia hạn bằng CA nội bộ mới; một số JVM vẫn dùng truststore cũ nên chỉ các pod chưa restart bị lỗi xác minh chứng chỉ.
Một proxy phía trước Jaeger v2 kết thúc TLS nhưng không chuyển tiếp đúng HTTP/2; OTLP gRPC client kết nối được TCP song không hoàn tất trao đổi giao thức.
Ứng dụng gửi OTLP qua proxy doanh nghiệp có giới hạn body; batch span lớn bị trả 413 và exporter liên tục retry cùng một lô dữ liệu.
Jaeger v2 nhận OTLP từ nhiều cluster nhưng cấu hình gateway chỉ cho phép một số địa chỉ nguồn; các node mới sau autoscaling bị chặn bởi network policy.
Nhóm chuyển sang OTLP/HTTP để đi qua gateway nhưng endpoint path của traces bị cấu hình sai; metrics từ cùng SDK gửi được còn trace exporter trả 404.
Một Java service có server span ở gateway nhưng không có span client tới payment-service; ứng dụng dùng HTTP client chưa được instrument nên trace kết thúc ngay tại service đầu.
Ứng dụng Spring Boot có auto instrumentation và custom instrumentation cùng tạo server span cho một request; Jaeger hiển thị hai span cha chồng lấn và thời gian xử lý bị tính sai.
Nhóm tạo custom span cho bước kiểm tra tồn kho nhưng không đặt span vào current context; các span database phát sinh sau đó trở thành sibling thay vì child.
Một đoạn code mở scope cho span nhưng không đóng trong nhánh exception; thread pool tái sử dụng thread và request sau bị gắn nhầm parent span.
Ứng dụng dùng CompletableFuture để xử lý thanh toán nền; trace context không được truyền sang executor nên worker tạo root span mới và mất quan hệ với request ban đầu.
Một service WebFlux chuyển scheduler giữa các operator; context tracing không được bảo toàn ở một nhánh Reactor và một phần span không nằm trong trace gốc.
Producer Kafka gửi traceparent trong message header nhưng consumer không extract context; trace của xử lý bất đồng bộ tách khỏi request đã tạo sự kiện.
Consumer Kafka xử lý lại message nhiều lần nhưng không ghi attempt hoặc retry event; Jaeger hiển thị nhiều span gần giống nhau và người trực không biết lần nào tạo kết quả cuối.
Một ứng dụng gửi message qua RabbitMQ và worker xử lý sau vài phút; trace context bị mất khi message qua dead-letter exchange nên trace lỗi chỉ còn phần worker.
Gateway nhận traceparent từ client nhưng service trung gian tạo request mới mà không inject context; trace bị đứt ở ranh giới giữa gateway và backend.
Hệ thống có service sử dụng W3C Trace Context còn một thư viện cũ chỉ hỗ trợ B3; Jaeger nhận hai trace ID khác nhau cho cùng một request xuyên dịch vụ.
Một ứng dụng tự tạo trace_id bằng chuỗi không đúng độ dài và định dạng; Jaeger UI không tìm thấy trace dù exporter báo gửi thành công.
Trace ID được tạo lại tại mỗi service vì middleware khởi tạo root span mới thay vì tiếp tục context; service graph cho thấy nhiều trace nhỏ không có liên kết.
Ứng dụng đưa email và mã khách hàng vào baggage để downstream dễ xử lý; baggage được truyền qua nhiều service và xuất hiện trong span attributes không cần thiết.
Nhóm gắn toàn bộ HTTP headers vào span attributes; Cookie và Authorization bị lưu trong Jaeger dù mục tiêu chỉ cần biết content-type và method.
Một custom span dùng tên chứa order_id; Jaeger tạo nhiều operation name duy nhất và việc nhóm thống kê theo operation không còn hữu ích.
Ứng dụng ghi URL đầy đủ vào span attribute nhưng query string chứa token; nhóm đã che log request mà quên áp dụng cùng chính sách cho tracing.
Database span ghi nguyên câu SQL có literal chứa email và mã tài khoản; đội điều tra truy vấn chậm cần loại thao tác và bảng nhưng trace lưu cả dữ liệu người dùng.
Một service đánh dấu span status OK ngay cả khi HTTP trả 500 do exception bị bắt và chuyển thành response; tỷ lệ lỗi nhìn từ trace thấp hơn trải nghiệm client.
Ứng dụng trả HTTP 200 nhưng payload có business_status=DECLINED; Jaeger không đánh dấu span lỗi vì instrumentation chỉ xét HTTP status và nhóm thanh toán bỏ sót lỗi nghiệp vụ.
Span client có thời gian dài hơn span server do đồng hồ hai node Kubernetes lệch nhau; người điều tra tưởng backend xử lý trước khi request được gửi.
Một trace chứa span con bắt đầu trước span cha do lệch clock giữa hai vùng; timeline Jaeger hiển thị thứ tự bất hợp lý và khó xác định service nào chậm.
Nhóm tạo span cho mọi vòng lặp xử lý hàng chục nghìn bản ghi; mỗi trace có quá nhiều span khiến UI tải chậm và dung lượng lưu trữ tăng mạnh.
Một tác vụ batch có thời gian chạy vài giờ nhưng chỉ tạo một span khổng lồ; khi một bước con lỗi, đội vận hành không thể xác định giai đoạn gây chậm hoặc thất bại.
Ứng dụng ghi lỗi bằng log nhưng không ghi exception event hoặc error attributes vào span; Jaeger chỉ hiển thị thời gian request và không giúp tìm nguyên nhân lỗi.
Nhóm tạo span event cho mọi lần retry nhưng không ghi retry count hoặc upstream name; trace dài và nhiều event nhưng không phân biệt được nguồn lỗi.
Head-based sampling 1% được cấu hình trong Java SDK; lỗi thanh toán hiếm gặp thường bị loại ngay đầu request và Jaeger không có trace để điều tra.
Nhóm lấy mẫu 100% ở service gateway nhưng các service downstream dùng ParentBased sampler với sampled flag khác; trace được lưu chỉ có một phần span.
Gateway đặt sampler AlwaysOn còn backend dùng sampler ratio thấp; số trace có root span lớn nhưng nhiều trace thiếu span con do các service không thống nhất chính sách.
Một lỗi chỉ xảy ra ở request có latency cao nhưng head sampling chọn ngẫu nhiên trước khi biết kết quả; phần lớn trace chậm không được lưu trong Jaeger.
Đội triển khai tail sampling tại OpenTelemetry Collector để giữ trace lỗi và chậm; các span của cùng trace được phân phối tới nhiều collector instance nên quyết định sampling không có đủ dữ liệu.
Tail sampling chờ đủ thời gian để gom span nhưng timeout quyết định quá ngắn so với workflow bất đồng bộ; span đến muộn bị bỏ khỏi trace đã được giữ.
Collector tail sampling có giới hạn số trace đang chờ; khi traffic tăng đột biến, trace bị eviction trước khi đủ span để đánh giá lỗi.
Nhóm cấu hình tail sampling chỉ giữ span có status ERROR; request thất bại nghiệp vụ nhưng trả HTTP 200 bị loại dù người dùng không hoàn thành giao dịch.
Sampling policy giữ trace theo service name nhưng resource attributes giữa các ứng dụng không thống nhất; một nhóm service quan trọng bị rơi vào policy mặc định ít ưu tiên.
Ứng dụng tăng tỷ lệ sampling lên 100% trong sự cố nhưng quên hạ lại; lượng span tăng vượt năng lực Collector và storage, làm mất trace đúng lúc tải cao.
Jaeger nhận traces đã được sampling ở SDK và tiếp tục sampling lần nữa ở Collector; tỷ lệ giữ thực tế thấp hơn mục tiêu mà nhóm vận hành tính toán.
Đội muốn giữ toàn bộ trace của tenant VIP nhưng tenant_id chỉ xuất hiện ở span con; quyết định head sampling ở root span không có thông tin để áp chính sách riêng.
Backend storage của Jaeger v2 hết dung lượng trong giờ cao điểm; exporter retry liên tục, queue OTLP đầy và trace mới bị drop.
Jaeger exporter ghi được một phần span vào storage nhưng phản hồi timeout; client retry batch và một số trace bị lưu trùng hoặc có dữ liệu không nhất quán.
Storage backend có latency ghi tăng sau khi shard phân bổ không đều; ingest rate giảm dù CPU Collector còn thấp.
Nhóm cấu hình Jaeger v2 dùng backend Elasticsearch nhưng credential đã hết hạn; tiến trình nhận OTLP song exporter trả lỗi xác thực và trace không được index.
Jaeger v2 không kết nối được storage do TLS CA mới; query service vẫn khởi động nhưng không truy xuất được trace từ cluster backend.
Một index template cho trace data bị mapping conflict sau khi ứng dụng thêm attribute có kiểu khác; một phần document bị từ chối trong khi ingest endpoint vẫn trả request.
Ứng dụng đưa user_id và request_id làm span attributes có cardinality cao; index storage tăng nhanh và truy vấn theo service trở nên chậm.
Nhóm lưu mọi span attribute và event payload không giới hạn; kích thước trace trung bình tăng nhiều lần và storage retention bị rút ngắn ngoài kế hoạch.
Jaeger storage giữ trace trong thời gian dài nhưng không có chính sách TTL/retention phù hợp; dữ liệu tăng liên tục và node gần hết đĩa.
Retention được giảm đột ngột để giải phóng storage; đội điều tra nhận báo cáo lỗi sau vài ngày và trace cần thiết đã bị xóa.
Storage backend có replica nhưng snapshot chưa được cấu hình; khi operator xóa nhầm index, các trace cũ không thể khôi phục dù cụm đã bật replication.
Đội thực hiện restore storage từ snapshot nhưng query service trỏ tới alias cũ; UI hiển thị không có dữ liệu mới dù index đã được phục hồi.
Jaeger query service dùng endpoint storage khác vùng so với collector exporter; dữ liệu ghi ở vùng A nhưng UI truy vấn vùng B và người dùng tưởng trace bị mất.
Một cụm Jaeger dùng storage dùng chung cho nhiều môi trường; trace staging và production trộn lẫn vì service name giống nhau và không có thuộc tính environment đáng tin cậy.
Nhóm thay đổi schema span attributes nhưng không có kế hoạch tương thích cho truy vấn cũ; dashboard và saved search Jaeger không còn lọc đúng dữ liệu sau triển khai.
Query service tìm trace theo service và thời gian rất chậm khi khoảng thời gian truy vấn rộng; người trực thường mở nhiều truy vấn đồng thời và làm backend storage quá tải.
Jaeger UI tìm theo trace ID trả kết quả nhưng truy vấn theo operation name không có dữ liệu; indexing field cho operation bị thiếu sau lần thay đổi mapping.
Trace xuất hiện trong UI khi tìm bằng ID nhưng không hiện trong service list; service name được đặt khác nhau ở resource và span khiến thống kê dịch vụ không nhất quán.
Service dependency graph không hiển thị một số quan hệ giữa microservice; các span client thiếu peer.service hoặc server span không có service.name chính xác.
Jaeger UI hiển thị service A gọi service B nhưng không có số liệu latency theo operation; span name được đặt ngẫu nhiên theo URL chứa ID nên nhóm operation bị phân mảnh.
Một trace có hàng nghìn span khiến trình duyệt tải UI chậm và tab bị treo; nhóm điều tra cần tìm span bất thường nhưng không có cách lọc hợp lý.
Người dùng tìm trace trong Jaeger với khoảng thời gian UTC nhưng dashboard nghiệp vụ dùng giờ địa phương; trace được gửi đúng nhưng truy vấn nhầm cửa sổ thời gian.
Jaeger query service bị giới hạn CPU khi nhiều nhóm cùng tìm kiếm trace dài; ingest vẫn ổn định nhưng UI trả timeout trong giờ ứng cứu.
Một truy vấn Jaeger lọc theo tag có giá trị sai kiểu so với dữ liệu lưu; người dùng tưởng trace không tồn tại dù trace ID trực tiếp vẫn mở được.
Nhóm muốn xem latency p95 của service từ Jaeger nhưng backend chỉ lưu trace đã sampling; phân bố trong UI thiên lệch và không đại diện toàn bộ traffic.
Service graph từ traces bị thiếu một chiều gọi do client instrumentation không có span; nhóm kết luận sai rằng request không đi qua dịch vụ trung gian.
Jaeger UI hiển thị lỗi ở span con nhưng không có log liên quan; trace_id không được đưa vào MDC của ứng dụng nên nhóm phải tìm log bằng timestamp gần đúng.
Một dashboard mở trace bằng link từ alert nhưng trace_id trong annotation bị cắt còn 16 ký tự; Jaeger không tìm được trace tương ứng.
Đội triển khai Jaeger v2 trên Kubernetes bằng Deployment đơn replica; khi node được drain, ingest dừng trong thời gian pod được lập lịch lại.
Jaeger collector được chạy với readiness probe chỉ kiểm tra process; storage exporter chưa kết nối được nhưng pod vẫn nhận traffic từ Service.
Deployment Jaeger v2 đặt resource requests quá thấp; pod bị evict khi node thiếu tài nguyên và OTLP clients bắt đầu mất span trong lúc reschedule.
Collector autoscaling theo CPU nhưng không theo queue length hoặc ingest throughput; lúc traffic tăng đột ngột, replica mới lên chậm hơn tốc độ backlog.
Một cụm Jaeger có nhiều collector replica nhưng load balancer giữ sticky connection tới một pod; pod đó quá tải trong khi các replica khác gần như nhàn rỗi.
Kubernetes NetworkPolicy cho phép ứng dụng tới collector nhưng chặn collector tới storage; traces vào được gateway rồi bị mất ở bước xuất.
DNS service storage trong Kubernetes thay đổi sau khi StatefulSet rollout; Jaeger exporter tiếp tục dùng connection cũ và không tự phục hồi trong thời gian dự kiến.
Jaeger query và collector dùng chung Service port nhưng routing path không phân biệt đúng; traffic truy vấn UI bị chuyển nhầm vào receiver OTLP.
Namespace Jaeger không có quyền đọc Secret chứa storage credentials sau khi RBAC được siết; pod khởi động lại và không thể mở kết nối backend.
Một sidecar proxy chặn OTLP gRPC do HTTP/2 chưa được cấu hình end-to-end; các ứng dụng báo lỗi export dù cổng service mở.
Cluster Kubernetes có đồng hồ node lệch nhau; trace đi qua nhiều node có timestamp không nhất quán và biểu đồ waterfall cho thấy các span chồng lấn.
Đội triển khai nhiều region và Jaeger collector ở từng vùng; một số request chuyển vùng qua gateway nhưng trace context bị thay mới nên trace không nối xuyên vùng.
Một cụm Jaeger đa vùng dùng chung storage nhưng query service ở vùng DR chưa có quyền truy cập; failover hoàn tất về hạ tầng nhưng người trực không xem được trace.
Ứng dụng ở cluster A gửi OTLP tới collector cluster B qua VPN; MTU và packet loss làm batch lớn bị phân mảnh và một số lần export timeout.
Nhóm dùng gateway chung cho nhiều tenant nhưng không gắn tenant identity đã xác thực vào resource; trace của các tổ chức có thể trộn trong cùng storage và kết quả tìm kiếm.
Jaeger UI được mở cho đội hỗ trợ với quyền truy cập rộng; span attributes chứa email và thông tin request nhạy cảm mà nhóm không cần xem.
Collector nhận trace qua mTLS nhưng chỉ kiểm tra CA, không ràng buộc certificate identity với service; workload khác có thể giả service.name của hệ thống thanh toán.
Ứng dụng đưa Authorization, cookie và dữ liệu cá nhân vào span attributes; redaction chỉ được cấu hình cho logs nên dữ liệu vẫn được lưu trong Jaeger.
Nhóm cấp token query cho dashboard với quyền đọc và xóa trace; một plugin bị cấu hình sai có thể xóa dữ liệu dù nhu cầu chỉ là tìm kiếm.
Jaeger storage giữ raw trace lâu hơn chính sách dữ liệu cá nhân; nhóm chưa có quy trình xóa trace theo tenant hoặc theo yêu cầu xóa dữ liệu.
Một service gửi trace với resource service.name là tên pod thay vì tên logical service; Jaeger tạo hàng trăm service riêng và service dependency graph trở nên khó đọc.
Ứng dụng phát service.name là checkout ở môi trường này và order-checkout ở môi trường khác; dashboard so sánh trace theo service không gom được dữ liệu cùng ứng dụng.
Nhóm nâng cấp OpenTelemetry SDK làm đổi semantic conventions của HTTP attributes; Jaeger UI và saved query vẫn tìm theo tên thuộc tính cũ nên bộ lọc không còn hiệu quả.
Một số service gửi span.kind là INTERNAL cho cả client call; Jaeger không nhận diện đúng quan hệ dependency và sơ đồ gọi dịch vụ thiếu chiều.
Span client ghi peer.service bằng hostname động theo pod; service dependency graph phân mảnh thành nhiều đích thay vì một backend logic.
Trace có server span nhưng không có parent span dù request được gọi từ gateway; middleware phía gateway không inject trace context do propagation header bị xóa.
Đội quan sát thấy trace có nhiều root span trong cùng một giao dịch; một số service tạo trace mới khi nhận request vì không extract W3C context.
Ứng dụng xử lý request qua gRPC nhưng instrumentation chỉ tạo span ở client; server span thiếu khiến thời gian xử lý backend không thể phân tích.
Service dùng JDBC instrumentation nhưng không có span SQL trong trace sau khi chuyển connection pool; driver hoặc proxy database chưa được hỗ trợ bởi cấu hình instrumentation.
Nhóm bật profiling cùng tracing để điều tra CPU cao nhưng trace chỉ ghi duration và không liên kết được với profile tương ứng; người trực không tìm ra stack nóng trong request chậm.
Jaeger metrics cho thấy số span received cao nhưng số span exported thấp; đội vận hành chỉ theo dõi pod health và không có alert cho export failures.
Collector queue tăng dần trong khi storage response time ổn định; nhóm chưa theo dõi dropped spans và retry để xác định giới hạn pipeline nằm ở đâu.
Một batch OTLP bị từ chối vì một span có attribute sai kiểu; toàn bộ batch bị ảnh hưởng và ứng dụng không có log cho biết span nào gây lỗi.
Nhóm chạy load test gửi hàng triệu trace ngắn nhưng chỉ kiểm tra HTTP success của exporter; không xác minh số trace thực sự có thể tìm thấy trong Jaeger sau ingest.
Đội kiểm thử end-to-end chỉ mở một trace mẫu trong UI; không kiểm tra context propagation qua Kafka, sampling, lưu trữ và truy vấn sau khi pod restart.
Jaeger v2 config được kiểm tra bằng YAML parser nhưng không xác minh component factory có trong binary; cấu hình tham chiếu exporter không được đóng gói khiến pod crash khi khởi động.
Nhóm thêm exporter storage mới vào config Jaeger v2 nhưng quên bật extension hoặc dependency tương ứng trong image; môi trường local dùng binary đầy đủ còn container production thiếu component.
Đội nâng cấp Jaeger v2 cùng lúc đổi Collector config, storage backend và OpenTelemetry SDK; sau phát hành trace biến mất nhưng không thể khoanh vùng thay đổi nào gây lỗi.
Một nhóm chuyển dữ liệu từ Jaeger v1 sang v2 nhưng không đối chiếu số trace ingest, service names và query latency; báo cáo migration thành công chỉ dựa trên trạng thái pod.
Jaeger v2 chạy song song với hệ thống Jaeger cũ trong thời gian migration; ứng dụng gửi một phần traffic đến mỗi backend và người trực phải tìm trace ở hai giao diện.
Đội cần rollback Jaeger v2 sau khi storage exporter lỗi nhưng schema index đã thay đổi; query service phiên bản cũ không đọc được dữ liệu mới theo cách dự kiến.
Nhóm xóa cấu hình sampling cũ khi chuyển v2; SDK quay về mặc định lấy mẫu khác và số trace được lưu giảm mạnh dù traffic ứng dụng không thay đổi.
Ứng dụng có sampling cấu hình tại SDK, Collector và gateway; các tỷ lệ nhân lên không được tài liệu hóa nên nhóm không biết phần trăm trace cuối cùng được lưu.
Một trace quan trọng có đủ span ở Collector debug exporter nhưng không xuất hiện trong Jaeger storage; đội trực chưa phân biệt lỗi receiver, processor, exporter và backend indexing.
Trong một sự cố mất dữ liệu truy vết, đội chỉ restart collector và query service; chưa kiểm tra OTLP exporter errors, queue saturation, storage rejects, sampling decisions và query time range nên nguyên nhân vẫn chưa rõ.
