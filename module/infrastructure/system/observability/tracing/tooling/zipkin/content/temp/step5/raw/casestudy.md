Một request đặt hàng đi qua API gateway, order service, inventory service và payment service nhưng giao diện Zipkin chỉ hiển thị một span gốc; các service phía sau xử lý bình thường và log ứng dụng có request ID riêng.
Trace của một request có root span nhưng thiếu parent-child relationship giữa order và payment; mỗi service tự tạo trace ID mới khi nhận HTTP request dù header truyền ngữ cảnh vẫn có mặt.
Một span payment có timestamp bắt đầu sớm hơn parent span order vài giây; các node chạy JVM lệch đồng hồ NTP và đội trực đang dựa vào thời gian tuyệt đối để suy luận thứ tự.
Một trace có tổng duration 8 giây nhưng tổng duration các child spans lớn hơn 20 giây vì các dependency được gọi song song; nhóm vận hành cộng thời gian span và kết luận sai điểm nghẽn.
Trace hiển thị span server của gateway kéo dài 4 giây, còn các span con đều dưới 50 ms; phần thời gian chưa instrument có thể nằm ở queue, middleware hoặc chờ kết nối trước khi gọi service.
Một service tạo span cho cả HTTP server và HTTP client trong cùng request nhưng đặt tên operation giống nhau; Zipkin UI khiến người điều tra khó phân biệt thời gian xử lý inbound với outbound.
Ứng dụng tạo span con cho thao tác cache nhưng không đóng span khi exception xảy ra; một số trace có span duration bất thường hoặc không có thời điểm kết thúc như mong đợi.
Một span được tạo trong nhánh xử lý lỗi nhưng không đặt error tag hoặc status; Zipkin hiển thị request hoàn tất bình thường dù người dùng nhận HTTP 500.
Trace của một giao dịch có nhiều span cùng tên 'process' và không có tag route hoặc method; nhóm hỗ trợ không xác định được thao tác nào chiếm phần lớn latency.
Một ứng dụng gắn toàn bộ thời gian request vào một span lớn và không instrument các lời gọi database, Redis hoặc HTTP client; trace không đủ chi tiết để xác định dependency gây chậm.
Service A gọi B rồi B gọi C, nhưng span của C xuất hiện như một trace độc lập; context propagation bị mất ở client HTTP nằm giữa B và C.
Một trace có trace ID khác nhau giữa gateway và backend do gateway tạo span mới thay vì tiếp tục context nhận từ client; việc tìm theo trace ID ở Zipkin chỉ thấy một nửa hành trình.
Client gửi B3 multi-header nhưng proxy xóa X-B3-TraceId trong lúc chuẩn hóa header; backend tạo trace mới dù các header span còn lại vẫn được chuyển tiếp.
Một ứng dụng Brave phát B3 single-header b3, còn gateway cũ chỉ đọc X-B3-TraceId và X-B3-SpanId; trace bị tách ở ranh giới hai phiên bản.
Service mới dùng W3C traceparent trong khi service cũ dùng B3; không có cấu hình propagation format tương thích nên mỗi bên quan sát một trace ID khác nhau.
Một gateway hỗ trợ cả W3C Trace Context và B3 nhưng ưu tiên sai nguồn header khi cả hai cùng xuất hiện; trace từ một client được ghép vào context cũ không tương ứng.
Header X-B3-Sampled=0 được gửi từ upstream nhưng ứng dụng backend tự tạo sampled span; dữ liệu xuất hiện không đồng nhất giữa các service trong cùng request.
Một client gửi X-B3-Flags=1 để yêu cầu debug sampling nhưng gateway loại bỏ header flags; trace giao dịch hỗ trợ không được giữ như đội trực mong đợi.
Ứng dụng tạo trace ID 128-bit trong khi một thư viện cũ chỉ hỗ trợ 64-bit; khi chuyển context, phần ID bị cắt và Zipkin hiển thị các trace tách rời.
Service Java nhận header trace ID không hợp lệ từ client bên ngoài; instrumentation không kiểm tra định dạng trước khi tiếp tục context và reporter từ chối span khi gửi.
Một HTTP client dùng thread pool bất đồng bộ; MDC được truyền nhưng Brave current trace context không được chuyển sang executor, khiến span ở callback không có parent đúng.
Ứng dụng Spring WebFlux chuyển xử lý qua Reactor scheduler; trace context bị mất khi đổi thread và các span sau bước flatMap trở thành root độc lập.
Một tác vụ CompletableFuture được tạo trong request nhưng chạy sau khi request thread kết thúc; context không được capture nên span gửi email không liên kết với trace gốc.
Ứng dụng dùng @Async của Spring để xử lý cập nhật kho; task executor chưa được instrument nên trace dừng tại lúc enqueue và không thể đo thời gian chờ queue.
Một scheduled job chạy mỗi phút tạo span mới nhưng cần liên kết với trace của yêu cầu đã lên lịch; hệ thống không lưu context an toàn khi chuyển từ request sang scheduler.
Message được publish lên Kafka từ order service và consumer xử lý ở worker khác; trace context không được đưa vào message headers nên span consumer không liên kết với producer.
Consumer Kafka nhận message có B3 headers nhưng framework chỉ đọc W3C traceparent; mỗi message tạo một trace độc lập dù producer đã ghi context.
Một message được retry nhiều lần và mỗi lần consumer tạo trace mới; nhóm vận hành không phân biệt được các attempt của cùng một nghiệp vụ với những message khác.
Ứng dụng dùng batch consumer xử lý 100 message trong một poll; một span gốc đại diện cả batch nhưng không có span hoặc link cho từng message, khiến lỗi một phần khó truy nguyên.
Trong workflow saga, payment service phát event sang shipping service; trace context chỉ được truyền ở bước đầu và mất sau khi event đi qua dead-letter queue.
Ứng dụng gọi dịch vụ đối tác qua HTTP proxy; proxy không forward B3 headers tới upstream nên trace kết thúc ở proxy mặc dù request đã tới đối tác.
Gateway tạo server span mới nhưng không ghi parent ID của context nhận từ client; Zipkin hiển thị trace mới và không thể nối với frontend trace.
Một service dùng Brave nhưng một thư viện khác tạo span bằng OpenTelemetry API; cả hai instrumentation cùng hoạt động nhưng không chia sẻ cùng context storage và tạo hai trace.
Spring Boot nâng cấp từ Spring Cloud Sleuth sang Micrometer Tracing; dependency cũ vẫn còn trong classpath và cả hai instrumentation cùng tạo server span cho một request.
Ứng dụng Spring MVC có Micrometer Observation và Brave bridge nhưng một custom interceptor cũng tự tạo span HTTP; mỗi request tạo span trùng và duration bị tính hai lần.
Micrometer Tracing được cấu hình B3 propagation nhưng OpenTelemetry agent trong cùng JVM inject W3C context; các outbound call mang hai bộ header với trace ID không thống nhất.
Ứng dụng Java dùng OpenTelemetry SDK và Zipkin exporter nhưng endpoint exporter vẫn trỏ tới collector cũ; span được tạo trong process song Zipkin server không nhận dữ liệu mới.
Nhóm bật Zipkin exporter và OTLP exporter đồng thời để migration; cùng span được gửi tới hai backend, nhưng dashboard tổng hợp số trace từ cả hai và đếm trùng.
Thư viện Brave reporter dùng async queue; queue đầy khi Zipkin server chậm và reporter loại bỏ span nhưng ứng dụng vẫn phục vụ request bình thường.
Ứng dụng cấu hình sampling rate 10% trong Brave, trong khi một service downstream đặt rate 100%; trace chỉ có một phần span vì quyết định sampled không được truyền nhất quán.
Đội đặt sampler xác suất 1% ở gateway để giảm chi phí; một lỗi thanh toán hiếm xuất hiện trong số request không được lấy mẫu và không có trace để điều tra.
Sampling được cấu hình theo request đầu vào nhưng một số request nội bộ không đi qua gateway; các service này tự quyết định sampling khác nhau và tạo trace không đầy đủ.
Một nhóm bật debug sampling cho tài khoản hỗ trợ bằng B3 flags; hệ thống bên ngoài cho phép client tự gửi cờ debug và có thể làm tăng đột biến lượng trace được thu thập.
Head-based sampling loại trace ngay khi request bắt đầu; sau đó request gặp lỗi ở database nhưng không thể phục hồi trace vì quyết định bỏ đã được thực hiện từ đầu.
Đội muốn tail sampling giữ các trace chậm trên Zipkin server, nhưng Zipkin chỉ nhận các span đã được SDK gửi; không có cơ chế tail sampling ở Zipkin UI để khôi phục trace chưa được xuất.
Sampling rate giảm từ 10% xuống 1% nhưng dashboard vẫn so số trace thô giữa hai ngày; nhóm kết luận traffic giảm 90% dù số request thực tế không đổi.
Một service dùng rate limit sampler theo process restart; sau khi rollout đồng loạt, mỗi pod bắt đầu lấy mẫu lại cùng thời điểm và tổng tỷ lệ sample toàn cluster vượt ngân sách.
Ứng dụng đặt sampler theo tên operation nhưng operation name thay đổi theo URL có ID; các request mới không khớp rule và được lấy mẫu theo default khác dự kiến.
Trace có tag debug=true được giữ lâu hơn nhưng SDK chỉ gắn tag sau khi hoàn tất request; sampler đưa ra quyết định trước khi tag được thêm nên policy không có hiệu lực.
Zipkin server nhận spans qua endpoint collector nhưng HTTP body có định dạng JSON v2 không hợp lệ; client retry và log exporter ghi lỗi parse payload.
Một thư viện reporter gửi JSON v2 tới endpoint cũ dành cho định dạng v1; server trả 400 và các spans không được lưu dù TCP kết nối bình thường.
Zipkin collector chỉ mở cổng HTTP 9411 trên localhost; ứng dụng ở pod khác không gửi được span dù health endpoint kiểm tra nội bộ thành công.
Ứng dụng gửi span qua Kafka collector nhưng Kafka receiver chưa được bật trong Zipkin server; message tích tụ ở topic trong khi dashboard Zipkin không có trace mới.
Zipkin server nhận request batch lớn hơn giới hạn HTTP body của reverse proxy; các traces nhiều spans bị trả 413 trong khi trace ngắn vẫn ingest thành công.
Reporter gửi một batch spans nhưng server trả 202 hoặc 200 trước khi storage hoàn tất ghi dữ liệu; nhóm kiểm tra response code và tưởng dữ liệu đã bền vững dù storage đang lỗi.
Zipkin server yêu cầu Basic Authentication ở reverse proxy nhưng reporter không gửi credential; endpoint UI truy cập được qua trình duyệt đã đăng nhập còn ingest từ ứng dụng nhận 401.
Ứng dụng dùng HTTPS để gửi spans nhưng chứng chỉ Zipkin server được ký bởi CA nội bộ chưa có trong truststore của JVM; reporter log lỗi SSL handshake và queue tăng.
Zipkin server bật TLS client authentication nhưng một nhóm reporter không có client certificate; một phần service gửi trace thành công còn nhóm khác bị từ chối.
Load balancer phân phối ingest requests giữa nhiều Zipkin server replicas nhưng storage backend cấu hình không đồng nhất; một số spans được ghi ở backend khác và truy vấn không thấy toàn bộ trace.
Zipkin collector nhận nhiều spans nhưng server quá tải CPU khi xử lý dependency aggregation; ingest latency tăng và reporter queue ở các service dần đầy.
Zipkin server có endpoint health trả 200 dù storage backend mất kết nối; Kubernetes không restart pod và trace ingest liên tục lỗi ở bước lưu trữ.
Reporter retry khi Zipkin server trả 503 nhưng retry interval quá ngắn; một đợt storage outage khiến lượng retry tăng và làm server quá tải hơn khi phục hồi.
Server ghi span thành công nhưng kết nối bị reset trước khi client nhận response; reporter retry cùng batch và storage có các span trùng nếu backend không khử trùng lặp theo ID.
Ứng dụng dùng reporter queue nhỏ hơn burst spans tạo ra trong chiến dịch; queue overflow loại bỏ spans mà không ảnh hưởng tới HTTP response, khiến mất dữ liệu khó nhận biết.
Brave AsyncReporter dùng queue đầy khi Zipkin server không sẵn sàng; metric dropped spans tăng nhưng đội vận hành không scrape metric reporter nên chỉ phát hiện qua log ứng dụng.
Reporter được cấu hình flush khi JVM shutdown nhưng Kubernetes termination grace period quá ngắn; pod bị SIGKILL trước khi gửi hết spans đang chờ.
Một service scale từ 5 lên 50 replicas nhưng mỗi JVM dùng queue và flush thread mặc định; tổng số kết nối ingest tăng mạnh và Zipkin server đạt giới hạn connection.
Zipkin server chạy trong cluster có ingress timeout ngắn; ingest batch mất lâu hơn timeout và client retry dù server vẫn đang xử lý request.
Storage Zipkin dùng in-memory backend trong môi trường production; sau khi pod restart, lịch sử trace biến mất dù ingest trước đó đã trả thành công.
Zipkin server lưu traces vào Elasticsearch nhưng index template không được áp dụng sau nâng cấp; một số field span duration và tags bị mapping sai kiểu.
Elasticsearch storage backend hết dung lượng disk; Zipkin collector vẫn nhận request nhưng thao tác lưu span bị reject và trace không xuất hiện trong truy vấn.
Elasticsearch cluster đang rebalance shard; truy vấn Zipkin UI tăng latency và một số trace tìm theo service name trả kết quả không đầy đủ trong thời gian di chuyển shard.
Zipkin dùng Cassandra storage và TTL dữ liệu ngắn hơn thời gian điều tra sự cố; trace cũ biến mất trước khi đội hỗ trợ bắt đầu phân tích.
Cassandra storage có consistency level không phù hợp giữa ghi và đọc; ingest thành công nhưng truy vấn ngay sau đó đôi lúc chưa thấy trace mới.
MySQL storage backend bị khóa bảng khi tác vụ bảo trì chạy; Zipkin ingest latency tăng và reporter queue của nhiều ứng dụng bắt đầu đầy.
Zipkin server ghi span vào storage nhưng dependency index hoặc service name index cập nhật chậm; truy vấn theo trace ID có dữ liệu còn tìm theo service không thấy.
Storage backend giữ trace theo TTL nhưng không đồng bộ timezone giữa các node; thời điểm hết hạn của một phần dữ liệu khác với chính sách lưu giữ mong muốn.
Một trace có hàng nghìn spans từ batch job; truy vấn theo trace ID chậm và Zipkin UI tải toàn bộ cây span gây timeout ở trình duyệt.
Zipkin server lưu tags với giá trị động gồm customer ID; index và storage tăng nhanh, truy vấn autocomplete service operation chậm theo cardinality.
Nhóm bật lưu toàn bộ annotation và tags từ request headers; dữ liệu trace tăng nhiều lần và storage retention thực tế giảm do giới hạn dung lượng.
Zipkin UI tìm theo service name và time range nhưng service mới không xuất hiện trong danh sách autocomplete; ingestion có span nhưng metadata index chưa cập nhật.
Truy vấn Zipkin tìm trace theo endpoint /checkout trả về nhiều trace không liên quan vì operation name của instrumentation chỉ là POST mà không chứa route template.
Nhóm tìm trace lỗi bằng tag error=true nhưng instrumentation mới chỉ gắn error tag khi có exception; HTTP 500 được trả trực tiếp mà không có exception nên truy vấn bỏ sót.
Zipkin UI lọc theo duration tối thiểu 500 ms nhưng người dùng nhập đơn vị nhầm từ microseconds sang milliseconds; kết quả không chứa trace chậm cần tìm.
Nhóm tìm theo annotation 'error' nhưng phiên bản Brave mới ghi error vào tag hoặc span status theo quy ước khác; truy vấn cũ không phát hiện các lỗi mới.
Trace hiển thị span với tag http.status_code=200 nhưng nghiệp vụ trả trạng thái declined trong response body; nhóm vận hành kết luận request thành công dù giao dịch bị từ chối.
Một span database có duration 2 giây nhưng không có db.statement, db.operation hoặc connection pool tags; đội trực không biết chậm do câu SQL, chờ pool hay network.
Zipkin dependency graph cho thấy service A gọi B nhiều hơn số request thực; client và server spans cùng được đếm như hai cạnh độc lập do truy vấn tổng hợp sai.
Dependency graph không hiển thị service database vì instrumentation chỉ tạo client spans mà không có server-side spans hoặc service metadata phù hợp cho backend.
Service name trong một nhóm spans được ghi là order-service, nhóm khác là order_service; dependency graph hiển thị hai node khác nhau dù cùng một ứng dụng.
Một service đổi tên sau triển khai nhưng các dashboard và cảnh báo Zipkin vẫn truy vấn service cũ; traces mới đã ingest nhưng không xuất hiện trong bảng điều khiển.
Trace duration trong Zipkin UI lớn hơn thời gian request ở access log; một số span được tạo trước khi request vào gateway hoặc kết thúc sau khi response đã gửi.
Trace có span client dài 3 giây nhưng server span phía đối tác chỉ 20 ms; phần thời gian còn lại có thể nằm ở DNS, TCP, TLS hoặc queue trước khi request đến đối tác.
Trong một trace, span Redis cache dài 1 giây nhưng database span chỉ 5 ms; đội phát triển nghi ngờ cache backend nhưng chưa đo thời gian chờ connection pool và serialization.
Trace của API chậm không có span database; JDBC instrumentation bị vô hiệu sau khi đổi datasource bean và nhóm chỉ nhìn thấy controller span.
Ứng dụng dùng R2DBC nhưng chỉ cài JDBC tracing instrumentation; truy vấn database bất đồng bộ không tạo span dù HTTP server tracing hoạt động.
Một service dùng RestTemplate đã được instrument nhưng WebClient mới không có observation propagation; outbound call từ WebClient không xuất hiện trong Zipkin.
Spring Boot actuator hiển thị observation metrics nhưng Zipkin không nhận spans; tracing bridge được cấu hình mà không có reporter hoặc exporter tương ứng.
Micrometer Tracing tạo span và Brave bridge xuất Zipkin v2 nhưng endpoint collector trỏ nhầm sang service UI; UI trả HTML còn reporter cần ingest endpoint.
Ứng dụng dùng OpenTelemetry Zipkin exporter nhưng export interval dài; request đã hoàn tất nhưng trace chỉ xuất hiện sau vài giây và nhóm trực nhầm cho rằng span bị mất.
OpenTelemetry SDK export Zipkin JSON nhưng một custom attribute có kiểu array không được exporter chuyển đổi như mong đợi; server từ chối một phần spans hoặc bỏ thuộc tính.
Java agent và Spring Micrometer instrumentation cùng instrument servlet server; trace có hai server spans lồng nhau và duration hiển thị lớn hơn thực tế.
Một thư viện Brave và OpenTelemetry bridge được cấu hình song song nhưng propagation context không dùng chung; span server và span client có trace ID khác nhau.
Service dùng Spring Cloud Sleuth cũ với B3 propagation nhưng dependency mới dùng Micrometer Tracing W3C; sau nâng cấp, trace bị tách tại outbound call.
Ứng dụng đặt sampling probability trong cấu hình Micrometer nhưng Brave sampler được override bằng bean tùy chỉnh; tỷ lệ trace thực tế khác cấu hình khai báo.
Nhóm dùng OpenTelemetry baggage để truyền tenant ID xuyên service; Zipkin exporter ghi baggage thành span tags và dữ liệu tenant xuất hiện trong UI rộng quyền.
Trace tags chứa email, số điện thoại và query parameters; Zipkin UI được chia sẻ cho toàn bộ đội phát triển và dữ liệu cá nhân không được che trước khi ingest.
Span annotation ghi nguyên request body khi lỗi validation; body có thông tin tài khoản và được lưu trong Elasticsearch lâu hơn thời gian lưu log nghiệp vụ.
Nhóm ghi Authorization header vào span tag để debug lỗi 401; token truy cập xuất hiện trong Zipkin search index và có thể được đọc bởi người có quyền xem trace.
Trace ID được gửi tới khách hàng trong response header để hỗ trợ ticket; người dùng có thể dùng ID này tra cứu trace chứa thông tin nội bộ nếu Zipkin UI không giới hạn quyền truy cập.
Zipkin UI mở công khai trong mạng VPN dùng chung; người dùng không thuộc đội thanh toán vẫn có thể xem span tags và tên database nội bộ.
Reverse proxy bảo vệ Zipkin UI bằng SSO nhưng ingest endpoint vẫn mở không xác thực; một workload bị xâm nhập có thể gửi trace giả làm nhiễu dữ liệu điều tra.
Zipkin server chấp nhận tags do client tùy ý gửi; người ngoài có thể đưa chuỗi rất dài hoặc giá trị độc hại vào index, làm tăng dung lượng và gây lỗi truy vấn.
Chính sách lưu trace yêu cầu 7 ngày nhưng Elasticsearch index giữ 30 ngày; dữ liệu request nhạy cảm vẫn còn sau thời gian mục đích vận hành đã kết thúc.
Sampling rate tăng lên 100% trong một incident và không được hạ sau đó; chi phí storage tăng mạnh và trace chứa dữ liệu cá nhân được giữ nhiều hơn dự kiến.
Đội muốn lưu 100% traces có lỗi nhưng SDK chỉ quyết định sampling trước khi biết kết quả; nhiều trace thất bại không được gửi tới Zipkin và không thể chọn lại ở server.
Một khách hàng yêu cầu xóa dữ liệu cá nhân; đội đã xóa log nhưng trace trong Zipkin storage vẫn giữ email ở span tags và bản sao Elasticsearch snapshot.
Nhóm dùng tag user.id đã hash để giả danh, nhưng giá trị hash ổn định có thể liên kết hành vi của cùng người dùng trên nhiều dịch vụ và nhiều ngày.
Zipkin storage backup được sao sang tài khoản cloud khác; quyền đọc backup rộng hơn quyền truy cập UI và chứa toàn bộ tags nhạy cảm.
Ứng dụng truyền trace context từ Internet không tin cậy; client có thể gửi trace ID tùy ý và liên kết request của mình với trace khác trong hệ thống.
Một hệ thống đa tenant dùng chung Zipkin server và storage nhưng không gắn tenant boundary trong truy vấn; người dùng của tenant này có thể tìm trace của tenant khác.
Đội triển khai nhiều Zipkin server replicas sau load balancer nhưng không cấu hình chung storage backend; trace được ghi ở replica A không thể truy vấn khi request UI được route tới replica B.
Zipkin server autoscale theo CPU nhưng storage Elasticsearch là nút nghẽn; tăng server replicas làm số kết nối storage tăng và latency query còn tệ hơn.
Một đợt rollout Zipkin server nâng schema storage nhưng một replica cũ vẫn chạy; hai phiên bản ghi dữ liệu khác cấu trúc và query trả kết quả không nhất quán.
Collector Zipkin bị restart trong khi reporter queue ở ứng dụng vẫn gửi batch; một số batch thất bại nhưng ứng dụng không log rõ số spans bị drop.
Network policy mới chặn traffic từ namespace ứng dụng tới Zipkin port 9411; reporter retries tăng và trace mới không xuất hiện dù service health xanh.
Zipkin server và storage backend nằm ở hai vùng khác nhau; RTT tăng khiến ingest latency và query duration tăng, dù CPU server không thay đổi.
DNS service Zipkin chuyển sang IP mới nhưng JVM reporter cache DNS cũ trong thời gian dài; một nhóm ứng dụng vẫn gửi tới địa chỉ cũ đã ngừng hoạt động.
TLS certificate của Zipkin server hết hạn; reporter JVM không gửi span mới và queue tăng trong khi UI vẫn hiển thị dữ liệu lịch sử nên người trực không nhận ra ingestion đã dừng.
Một proxy giới hạn HTTP request body nhỏ hơn kích thước batch Zipkin; lỗi chỉ xảy ra với traces nhiều spans, còn các request ngắn vẫn thành công.
Zipkin collector nhận span với timestamp tương lai do máy client lệch clock; truy vấn theo khoảng thời gian hiện tại không tìm thấy trace vừa gửi.
Ứng dụng tạo span duration âm do dùng wall clock thay vì monotonic elapsed time khi đồng hồ hệ thống được điều chỉnh; Zipkin UI hiển thị duration không hợp lệ.
Một trace chứa span bắt đầu sau span con do clock skew giữa các JVM; nhóm hiểu nhầm thứ tự gọi service và điều tra sai hướng.
Zipkin server nhận spans thiếu localEndpoint serviceName; trace vẫn có ID nhưng không thể tìm theo service và dependency graph không có tên node.
Instrumentation ghi remoteEndpoint sai địa chỉ do service mesh NAT; dependency graph hiển thị nhiều IP thay vì tên service ổn định.
Span client dùng tag peer.service khác nhau giữa các phiên bản; Zipkin dependency graph tách một dependency thành nhiều node và không thể đánh giá tổng độ trễ của đối tác.
Ứng dụng ghi annotation CS và CR thủ công nhưng thiếu timestamp hoặc dùng sai thứ tự; Zipkin tính duration client không khớp với thời gian network thực tế.
Một thư viện cũ gửi span không có kind SERVER hoặc CLIENT; Zipkin UI không phân biệt được phía gọi và phía nhận khi phân tích dependency.
Span được tạo nhưng không kết thúc trong finally block khi CompletableFuture bị cancel; trace giữ trạng thái span chưa hoàn tất và thời gian duration không chính xác.
Ứng dụng tạo span cho mỗi lần retry nhưng không gắn attempt number; khi backend lỗi ba lần, nhóm chỉ thấy nhiều span giống nhau mà không xác định được lần nào đã thành công.
Trace của request timeout không có span database vì JDBC call bị block trước khi instrumentation tạo span; đội trực chỉ thấy server span dài và không biết thread đang chờ ở đâu.
Zipkin UI tìm trace theo service và operation nhưng dữ liệu được lưu ở Elasticsearch với analyzer không phù hợp cho tag value; tìm kiếm tag chính xác trả kết quả không đầy đủ.
Một truy vấn Zipkin tìm trace duration lớn hơn 2 giây chạy trên khoảng thời gian 30 ngày; storage index thiếu time-based partition và query làm tăng tải Elasticsearch.
Dashboard phụ thuộc Zipkin API v2 nhưng reverse proxy chỉ cho phép endpoint UI; các truy vấn trace từ dashboard nhận 403 dù trang Zipkin mở được.
Zipkin query service trả danh sách trace ID nhưng tải chi tiết từng trace timeout do số spans mỗi trace lớn; nhóm điều tra chỉ nhìn được metadata mà không mở được cây span.
Service name autocomplete trong Zipkin UI chậm sau khi hệ thống thêm hàng nghìn tên service động theo tenant; metadata index không được chuẩn hóa.
Dependency link từ Zipkin được tính trên cửa sổ thời gian ngắn; một service chỉ nhận traffic batch theo giờ biến mất khỏi graph dù vẫn hoạt động.
Nhóm so sánh latency giữa hai release bằng trace duration nhưng sampling rate và loại endpoint được lấy mẫu khác nhau; kết quả không phải so sánh cùng phân phối request.
Một trace có duration thấp nhưng user request chậm do thời gian DNS và TLS trước root span; instrumentation bắt đầu sau khi HTTP framework đã nhận kết nối.
Trace cho thấy database span 10 ms nhưng request mất 2 giây do chờ lấy connection từ pool; instrumentation chỉ bọc query execution và không đo acquire time.
Ứng dụng dùng connection pool JDBC và thread chờ pool lâu; trace có khoảng trống giữa controller và database span, nhưng không có span hoặc tag thể hiện pool wait.
Một service gọi API ngoài qua retry interceptor; mỗi attempt không tạo child span riêng nên trace chỉ có một span dài và không thể phân biệt backend chậm với retry backoff.
Gateway timeout sau 3 giây trong khi downstream span hoàn tất ở 5 giây; trace cho thấy child span kết thúc sau response của parent và nhóm cần kiểm tra cancellation propagation.
Trong một request, payment và inventory chạy song song; Zipkin hiển thị cả hai span nhưng không có annotation về barrier hoặc thời điểm join, khiến việc hiểu thời gian chờ tổng khó khăn.
Trace của một request có span cache hit và database query cùng xuất hiện; instrumentation cache không đánh dấu hit/miss nên nhóm không biết query có phải fallback sau cache miss.
Service Java ghi lỗi ở span event nhưng không thêm exception type hoặc stack trace; truy vấn theo error tag không tìm được trace có lỗi và đội trực phải mở từng trace.
Một span ghi HTTP status 499 từ reverse proxy nhưng ứng dụng không nhận được request; nhóm phân tích nhầm là lỗi xử lý backend do không biết status do client ngắt kết nối.
Ứng dụng gRPC trả status RESOURCE_EXHAUSTED nhưng span chỉ có http.status_code=200; Zipkin không thể phân loại lỗi gRPC nếu instrumentation không ghi grpc.status_code.
Service nhận request từ mobile qua gateway; gateway đổi trace ID do policy privacy nhưng không giữ liên kết qua span link, khiến hỗ trợ khách hàng không nối được request ngoài với trace nội bộ.
Nhóm migrate từ Zipkin sang Jaeger nhưng chuyển đổi span model làm mất annotation và local endpoint; dependency graph sau migration thiếu một số service.
Ứng dụng xuất OTel spans tới Zipkin exporter nhưng resource attributes service.namespace và deployment.environment không được chuyển thành tags mà backend truy vấn; nhóm không lọc được traces theo môi trường.
OpenTelemetry Zipkin exporter gửi trace ID 128-bit nhưng storage backend cũ chỉ hỗ trợ định dạng 64-bit; một phần trace bị cắt ID và không liên kết với context W3C.
Đội cấu hình OTel propagation composite gồm B3 và W3C nhưng exporter Zipkin chỉ giữ một context; trace ID trong headers khác với ID được lưu ở Zipkin UI.
Một ứng dụng dùng Micrometer Observation tạo span cho HTTP server nhưng không instrument Kafka listener; trace kết thúc ở lúc publish và phần xử lý message không xuất hiện.
Spring Boot bật management tracing sampling nhưng custom ObservationConvention đổi tên operation; dashboard và alert truy vấn tên cũ, dẫn đến các trace mới không được nhóm.
Ứng dụng dùng @NewSpan nhưng không có annotation processor hoặc AOP proxy hoạt động trong đường gọi nội bộ; method chạy nhưng span tùy chỉnh không xuất hiện.
Một method được gọi nội bộ trong cùng Spring bean có @NewSpan; self-invocation bỏ qua proxy và không tạo span như nhóm mong đợi.
Ứng dụng dùng RestClient mới nhưng tracing instrumentation chỉ được cấu hình cho RestTemplate; outbound HTTP call không có client span sau khi migration thư viện.
Nhóm instrument cả WebClient filter và Micrometer observation handler; mỗi outbound request tạo hai client spans và latency bị hiển thị lặp.
Zipkin reporter gửi dữ liệu theo batch mỗi 5 giây; nhóm so thời gian request hoàn tất với thời điểm trace xuất hiện trên UI và tưởng rằng ứng dụng phản hồi chậm hơn thực tế.
Một service chỉ gửi spans khi request hoàn tất; request treo vô thời hạn chưa export nên trace quan trọng không xuất hiện trong Zipkin trong lúc sự cố đang diễn ra.
Sampling policy loại bỏ trace của health checks nhưng health check là luồng duy nhất phát hiện lỗi DNS giữa hai service; khi dependency mất kết nối, không có trace kiểm tra đường đi.
Đội bật 100% sampling trên một service có 50.000 RPS; reporter queue và Zipkin storage tăng nhanh, gây overhead CPU trong ứng dụng và làm query UI chậm.
Nhóm đặt sampling thấp nhưng giữ trace có error tag; exception chỉ được gắn sau khi sampler quyết định, nên lỗi hiếm vẫn không được giữ.
Một hệ thống đa vùng dùng sampler xác suất khác nhau theo region; so sánh số trace lỗi tuyệt đối giữa vùng không phản ánh cùng tỷ lệ lấy mẫu.
Zipkin UI hiển thị ít trace hơn sau khi rollout nhưng application request count không đổi; đội chưa đối chiếu sampled spans, reporter dropped spans và ingestion errors.
Đội trực không có dashboard cho reporter queue size, spans dropped và export latency; Zipkin UI không có trace mới nhưng không biết lỗi nằm ở ứng dụng, mạng hay server.
Zipkin server có health check xanh và UI truy vấn lịch sử thành công, nhưng endpoint ingest bị chặn bởi ingress rule; nhóm nhầm storage/query hoạt động với ingestion hoạt động.
Một pipeline Fluent Bit hoặc Collector chuyển tiếp spans tới Zipkin nhưng filter loại các span có status OK; trace lỗi còn lại thiếu span cha thành công để tái hiện đầy đủ luồng.
Span tags chứa SQL statement với literal customer email; storage index cho phép tìm kiếm toàn văn và quyền truy cập rộng hơn database audit log.
Zipkin dependency graph được chia sẻ trong báo cáo bên ngoài; tên service, endpoint nội bộ và địa chỉ host hiển thị dù dữ liệu trace chi tiết đã bị ẩn.
Một đội giữ trace samples 30 ngày nhưng log tương ứng chỉ 7 ngày; sau khi trace cho thấy lỗi ở payment, log chi tiết đã bị xóa và không thể xác minh nguyên nhân.
Nhóm dùng trace ID trong ticket hỗ trợ nhưng không đặt TTL hoặc giới hạn quyền tìm kiếm; nhân viên ngoài nhóm có thể dùng ID để truy cập trace của giao dịch.
Ứng dụng gắn customer_id vào baggage và Zipkin exporter chuyển baggage thành tag; trace chia sẻ cho nhà cung cấp ngoài chứa mã định danh khách hàng.
Zipkin server sử dụng Elasticsearch có snapshot tự động; dữ liệu trace đã hết TTL vẫn tồn tại trong snapshot và có thể được phục hồi sau khi xóa ở index chính.
Đội nâng cấp Zipkin server và storage cùng lúc; phiên bản mới thay đổi cách lưu dependency index và các truy vấn so sánh trước/sau release không cùng cấu trúc.
Một nhóm vận hành Zipkin server in-memory để demo và quên thay backend trước khi chạy production; khi pod restart, trace phục vụ điều tra biến mất.
Ứng dụng gửi span qua Zipkin collector nhưng service.name bị cấu hình mặc định là unknown_service:java; toàn bộ traces từ nhiều service bị gộp thành một tên.
Service chạy nhiều instance nhưng localEndpoint.ip được lấy từ loopback; dependency graph cho thấy mọi instance có cùng địa chỉ và không xác định được node có lỗi.
Zipkin collector nhận annotation từ Brave nhưng timestamp dùng microseconds; một custom reporter gửi milliseconds khiến duration trace chênh lệch hàng nghìn lần.
Trong một lần outage, storage backend phục hồi nhưng reporter đã loại bỏ các spans trong queue sau retry limit; UI vẫn có dữ liệu cũ nên nhóm không biết khoảng trống ingestion.
Một trace được tạo ở frontend và chuyển qua backend nhưng frontend không gửi sampled flag; backend mặc định sampled=true và chỉ phần server xuất hiện.
Gateway tạo B3 single header nhưng downstream proxy chỉ forward các header bắt đầu bằng X-B3; trace bị đứt ở proxy dù header b3 vẫn có trong request.
Ứng dụng gửi trace context qua gRPC metadata nhưng interceptor chỉ propagate HTTP headers; các service gRPC có span root riêng và không liên kết được.
Trace qua message broker cần tạo span link thay vì parent-child trực tiếp cho batch nhiều message; instrumentation dùng một parent duy nhất làm các giao dịch khác nhau bị ghép chung.
Job batch xử lý dữ liệu của nhiều request và tạo một span cha duy nhất; trace hiển thị như mọi giao dịch đều thuộc cùng một request và không giữ được ranh giới nghiệp vụ.
Nhóm tạo span cho từng dòng trong batch 1 triệu bản ghi; Zipkin nhận quá nhiều spans và lưu trữ chậm trong khi chỉ cần span cho batch và các bước tổng hợp.
Ứng dụng ghi tag error.message chứa nguyên exception message với SQL parameters; dữ liệu bí mật có thể xuất hiện trong Zipkin UI dù log đã được redaction.
Zipkin UI phân quyền theo người dùng nhưng API /api/v2/traces không áp dụng cùng authorization middleware; truy vấn trực tiếp vẫn có thể lấy trace chi tiết.
Nhóm dùng sampling debug để điều tra một khách hàng nhưng không giới hạn theo thời gian hoặc tenant; dữ liệu nhạy cảm của các request khác cũng được giữ ở mức 100%.
Đội vận hành đánh giá migration từ Brave sang OTel bằng số spans tổng; tên span và cách đặt kind thay đổi làm cùng một request tạo số span khác, chưa chứng minh được trace completeness.
Zipkin server trả trace theo ID nhưng một phần spans đến muộn sau lần query đầu; đội trực lưu kết quả query tức thời và bỏ qua child spans được ingest sau đó.
Một collector ingest span từ nhiều clock domain; khi đồng hồ node thay đổi trong lúc request đang chạy, các span có timestamp bất thường và dependency latency không còn tin cậy.
Ứng dụng tạo trace context từ client không tin cậy và dùng trace ID để xác định quyền truy cập bản ghi; kẻ gọi API có thể đoán hoặc tự đặt ID nhưng không được dùng làm cơ chế authorization.
Đội vận hành so latency Zipkin với APM agent khác nhưng một hệ thống đo thời gian từ lúc nhận socket, hệ thống kia bắt đầu ở servlet filter; số liệu lệch nhau dù cùng request.
Một dashboard dùng trace duration p95 từ Zipkin nhưng chỉ query những trace được sample; sau khi sampling thay đổi theo route, percentile không còn đại diện cho cùng phân phối request.
Nhóm kiểm thử tích hợp chỉ xác nhận Zipkin UI có trace mới; không kiểm tra parent-child, trace ID continuity, error tags, span kind và dữ liệu nhạy cảm trong tags.
Một bài load test tạo traffic bằng một trace ID cố định; Zipkin storage và UI xử lý khác với phân bố trace ID thực tế, khiến kết quả capacity test không đại diện production.
Đội kiểm thử reporter outage bằng cách dừng Zipkin trong 30 giây; không kiểm tra queue đầy, retry limit hoặc quá trình flush backlog sau outage dài hơn.
Ứng dụng triển khai sampling rate mới nhưng không có metric về số span được tạo, sample, gửi, drop và nhận; nhóm không xác định được mất dữ liệu xảy ra ở SDK hay server.
Một trace có parent span bị sampling out ở service đầu nhưng child spans vẫn được gửi do sampler cục bộ; Zipkin hiển thị orphan spans và người điều tra tưởng context propagation bị lỗi.
Service payment tạo span client tới ngân hàng nhưng không ghi remoteEndpoint serviceName; dependency graph không hiển thị ngân hàng và nhóm không thấy latency external dependency.
Trace của một request có các span DB, Redis và HTTP nhưng operation name chỉ là method Java; query theo endpoint API không gom được trace của các request cùng route.
Zipkin storage có retention dài nhưng index service name và autocomplete bị giới hạn; dữ liệu trace còn tồn tại nhưng người dùng không tìm được service trong UI.
Nhóm dùng tags để ghi build version nhưng mỗi lần deploy tạo một tag value mới; truy vấn so sánh release cần lọc nhiều giá trị và index tăng theo lịch sử deploy.
Zipkin query theo annotation không tìm thấy sự kiện vì instrumentation mới ghi span tags; nhóm chưa cập nhật cách truy vấn sau khi thay đổi phiên bản Brave.
Một lỗi chỉ xảy ra ở một phần request khi circuit breaker mở; trace chỉ ghi exception ở client span nhưng không gắn tag trạng thái circuit breaker, làm nhóm nhầm với lỗi mạng.
Service mesh retry một request ba lần nhưng ứng dụng chỉ có một span client tổng; không thể phân biệt thời gian mỗi attempt và khoảng backoff từ trace.
Gateway timeout request nhưng downstream vẫn tiếp tục xử lý do cancellation không được truyền; trace parent kết thúc trước child spans và backend tiếp tục tiêu tốn tài nguyên sau khi client đã rời đi.
