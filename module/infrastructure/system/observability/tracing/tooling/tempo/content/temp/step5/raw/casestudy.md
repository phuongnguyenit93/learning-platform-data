Một nền tảng thương mại chuyển từ backend tracing tự quản sang Grafana Tempo, nhưng dashboard trace cũ không tìm thấy dữ liệu sau migration; nhóm SRE cần xác định khác biệt về ingest, lưu trữ và truy vấn.
Đội nền tảng triển khai Tempo ở chế độ monolithic cho môi trường nhỏ, khi lượng trace tăng mạnh CPU và bộ nhớ của một tiến trình chạm giới hạn; nhóm kiến trúc cần đánh giá thời điểm tách các thành phần thành microservices.
Một doanh nghiệp triển khai Tempo theo mô hình distributed, distributor nhận dữ liệu nhưng ingester không ghi block mới; nhóm vận hành cần xác định luồng xử lý giữa các thành phần và vị trí lỗi.
Hệ thống có nhiều distributor sau load balancer, một số client giữ kết nối lâu khiến phần lớn OTLP traffic dồn vào một replica; đội SRE cần đánh giá phân phối kết nối và khả năng mở rộng ngang.
Một cụm Tempo có querier và query-frontend nhưng Grafana datasource trỏ nhầm service nội bộ của distributor; nhóm vận hành cần xác định endpoint nhận trace và endpoint phục vụ truy vấn.
Doanh nghiệp triển khai compactor riêng nhưng quên cấp quyền truy cập object storage, block không được compact và số lượng object tăng; nhóm nền tảng cần kiểm tra quyền và trách nhiệm của từng component.
Một ingester Tempo bị restart liên tục sau khi tăng tải, các trace chưa flush từ WAL bị ảnh hưởng; nhóm SRE cần đánh giá WAL, persistent storage và quy trình phục hồi tiến trình.
Hệ thống Tempo dùng ring để phân phối ingester, nhưng một số instance không tham gia ring sau thay đổi mạng; nhóm vận hành cần xác định trạng thái membership và ảnh hưởng đến ghi trace.
Một cụm Tempo dùng memberlist để khám phá thành viên, firewall mới chặn lưu lượng gossip giữa các pod; đội hạ tầng cần kiểm tra các luồng mạng cần thiết cho ring.
Nền tảng mở rộng ingester từ ba lên sáu replica, nhưng phân phối token trong ring mất cân bằng và một số instance chịu tải ghi lớn hơn rõ rệt; nhóm SRE cần đánh giá phân bổ ownership.
Một ingester rời cụm đột ngột khi đang nhận trace, distributor tiếp tục gửi dữ liệu tới instance cũ trong giai đoạn chuyển ring; nhóm vận hành cần kiểm tra hành vi retry và replication khi thành viên thay đổi.
Doanh nghiệp cấu hình replication cho trace ingestion, nhưng số replica khả dụng thấp hơn yêu cầu trong một zone; nhóm SRE cần xác định ảnh hưởng đến độ bền dữ liệu khi mất node hoặc zone.
Một cụm Tempo triển khai zone-aware ingesters nhưng label zone bị thiếu ở một nhóm pod, dữ liệu không được phân bố như dự kiến; đội nền tảng cần kiểm tra topology metadata và anti-affinity.
Một nhóm nâng cấp Tempo giữa hai phiên bản có thay đổi cấu trúc cấu hình, tiến trình mới khởi động nhưng một số component không hoạt động; nhóm DevOps cần xác định tính tương thích và quy trình nâng cấp tuần tự.
Tempo chạy trong Kubernetes, pod compactor bị eviction do thiếu tài nguyên và không tự khởi động lại vì node selector không còn phù hợp; đội vận hành cần đánh giá scheduling và khả năng phục hồi.
Một chart Helm cấu hình sai service port, Alloy gửi OTLP tới cổng truy vấn Tempo thay vì cổng nhận trace; nhóm SRE cần đối chiếu receiver, service và target port.
Một cụm Tempo có nhiều service cùng tên trong các namespace khác nhau, Grafana kết nối nhầm endpoint của môi trường staging; nhóm nền tảng cần xác định định danh cluster và namespace trong cấu hình datasource.
Một hệ thống dùng Tempo gateway phía trước các component, gateway bị giới hạn body size nên trace lớn bị từ chối; nhóm hạ tầng cần đánh giá giới hạn request và kích thước batch.
Ứng dụng gửi trace qua OpenTelemetry Collector tới Tempo, receiver OTLP gRPC được mở nhưng SDK lại cấu hình OTLP HTTP; đội phát triển cần xác định giao thức thực tế ở hai đầu.
Một ứng dụng dùng Grafana Alloy để gửi traces, nhưng exporter đang trỏ tới endpoint Tempo cũ sau khi chuyển cluster; nhóm SRE cần kiểm tra cấu hình đích và thời gian lưu DNS.
Nền tảng có nhiều nguồn gửi OTLP đồng thời, một nhóm SDK dùng TLS còn nhóm khác gửi plaintext tới receiver nội bộ; đội bảo mật cần xác định chính sách transport nhất quán.
Tempo nhận OTLP nhưng từ chối một số request do chứng chỉ client hết hạn sau rotation; nhóm vận hành cần đánh giá vòng đời certificate và giám sát lỗi xác thực.
Một doanh nghiệp gửi trace từ nhiều mạng chi nhánh tới Tempo gateway public, không có authentication hoặc rate limit; nhóm bảo mật cần đánh giá nguy cơ giả mạo telemetry và cạn tài nguyên.
Một hệ thống dùng Jaeger client cũ gửi spans tới Tempo, một số trường metadata không được ánh xạ như mong đợi; nhóm tích hợp cần kiểm tra tương thích protocol và semantic conventions.
Một ứng dụng cũ gửi Zipkin spans vào Tempo nhưng timestamp và service name khác định dạng OTLP mới; nhóm SRE cần xác định cách chuẩn hóa nguồn trace đa giao thức.
Doanh nghiệp chuyển SDK từ Jaeger sang OpenTelemetry, trace ID được tạo lại tại gateway và không còn nối với log cũ; nhóm phát triển cần kiểm tra propagation context qua migration.
Một API gateway nhận W3C traceparent nhưng backend dùng định dạng propagation khác, mỗi service tạo trace riêng; nhóm kiến trúc cần xác định cấu hình propagator xuyên hệ thống.
Ứng dụng dùng baggage để truyền tenant và user context, các thuộc tính này được sao chép vào mọi span rồi lưu trong Tempo; đội governance cần đánh giá nội dung và phạm vi dữ liệu.
Một dịch vụ gửi spans có resource attribute service.name thiếu hoặc khác nhau giữa phiên bản, TraceQL và service graph phân tách cùng ứng dụng thành nhiều service; nhóm observability cần chuẩn hóa resource metadata.
Một hệ thống có span name chứa URL động với mã đơn hàng, số lượng giá trị khác nhau tăng mạnh và truy vấn khó nhóm; đội SRE cần xác định cách đặt tên span theo route template.
Ứng dụng ghi một trace có hàng nghìn spans do vòng lặp gọi dịch vụ, distributor từ chối trace vượt giới hạn; nhóm kỹ thuật cần đánh giá span count, trace size và instrumentation.
Một trace bị chia thành nhiều phần do các service gửi dữ liệu trễ, backend truy vấn chỉ thấy một phần cây span; nhóm vận hành cần xác định nguyên nhân từ propagation, buffering và thời điểm query.
Một service gửi spans với timestamp lệch nhiều phút so với các service khác, timeline trace hiển thị thứ tự không hợp lý; nhóm SRE cần đánh giá đồng bộ đồng hồ và event timestamp.
Một ứng dụng có một số spans kết thúc sau thời gian dài, dữ liệu được gửi theo batch sau khi trace đã hoàn tất từ lâu; đội vận hành cần đánh giá thời gian chờ và khả năng hoàn thiện trace.
Một hệ thống sampling tại SDK chỉ giữ một phần trace, nhóm trực không tìm thấy trace của lỗi hiếm dù ứng dụng đã phát sinh sự cố; nhóm SRE cần đánh giá head sampling và tỷ lệ giữ trace.
Nền tảng dùng tail sampling tại Collector nhưng gateway phân tán nhiều replica, các spans của cùng trace đi tới các collector khác nhau; nhóm kiến trúc cần đánh giá routing theo trace ID.
Một chính sách sampling giữ mọi trace có lỗi nhưng một service không đặt span status error khi trả lỗi nghiệp vụ; nhóm phát triển cần thống nhất cách đánh dấu lỗi và điều kiện giữ trace.
Một đội giảm sampling rate để tiết kiệm chi phí, nhưng trace quan trọng cho SLO latency bị loại quá nhiều; nhóm SRE cần cân đối nhu cầu điều tra, độ đại diện và chi phí.
Ứng dụng phát trace có nhiều spans nhưng một số span không có parent span do tác vụ bất đồng bộ, service graph không thể hiện quan hệ đầy đủ; nhóm kỹ thuật cần đánh giá span links và mô hình quan hệ.
Một pipeline gửi cùng trace qua hai Collector gateway, Tempo nhận dữ liệu lặp và trace có số spans lớn hơn thực tế; đội vận hành cần xác định nguồn gửi trùng và cơ chế chống duplication.
Một dịch vụ gửi trace ID không hợp lệ do thư viện tự viết, distributor ghi nhận lỗi decode; nhóm phát triển cần kiểm tra định dạng ID và tương thích SDK.
Một hệ thống có trace rất dài qua nhiều vùng, spans đến Tempo theo thứ tự khác nhau do mạng; nhóm SRE cần xác định tác động của out-of-order data tới khả năng hiển thị và truy vấn.
Một doanh nghiệp gửi trace qua proxy có timeout ngắn hơn thời gian upload batch, các request lớn bị cắt dù Tempo vẫn khỏe; đội hạ tầng cần đánh giá timeout trên từng chặng.
Ứng dụng gửi OTLP với compression, proxy trung gian không hỗ trợ đúng kiểu encoding nên một phần batch bị từ chối; nhóm tích hợp cần kiểm tra tương thích transport.
Một cụm Tempo nhận burst traces trong đợt flash sale, distributor CPU tăng cao và request bắt đầu timeout; nhóm SRE cần xác định giới hạn ingestion và cách scale.
Một ứng dụng gửi trace có payload lớn chứa nhiều event và exception, giới hạn kích thước span của Tempo bị vượt; đội phát triển cần giảm dữ liệu instrumentation mà vẫn giữ thông tin điều tra.
Nền tảng có nhiều trace chứa stack trace dài, bộ nhớ distributor tăng đột biến khi giải mã batch; nhóm vận hành cần đánh giá giới hạn payload và bảo vệ trước dữ liệu bất thường.
Một nhóm tăng số distributor nhưng load balancer chỉ phân phối theo kết nối lâu, một replica nhận phần lớn traffic; đội hạ tầng cần kiểm tra cân bằng tải và connection lifecycle.
Tempo ingester nhận dữ liệu ổn định nhưng tốc độ flush block thấp hơn ingestion, WAL và bộ nhớ tăng theo thời gian; nhóm SRE cần xác định nút thắt ghi block.
Một ingester bị đầy đĩa WAL do object storage mất kết nối, các request mới bắt đầu bị từ chối; đội vận hành cần đánh giá chính sách khi backend lưu trữ gián đoạn.
Hệ thống Tempo dùng persistent volume cho WAL nhưng pod được schedule sang node không thể mount volume sau bảo trì; nhóm DevOps cần kiểm tra khả năng phục hồi và ràng buộc storage.
Một cụm ingester có WAL trên ephemeral disk, node bị thay thế khiến dữ liệu chưa flush bị mất; nhóm SRE cần đánh giá độ bền của vùng đệm.
Một tổ chức đặt giới hạn bộ nhớ ingester quá thấp, khi flush block và nhận trace đồng thời pod bị OOMKilled; nhóm nền tảng cần đánh giá tài nguyên và tải đỉnh.
Một cụm Tempo có nhiều ingester nhưng một replica xử lý trace có kích thước lớn hơn do phân phối không đồng đều; nhóm SRE cần xác định chênh lệch tải và giới hạn per-tenant.
Một ứng dụng gửi traces với nhiều spans có cùng trace ID nhưng sai thứ tự thời gian, ingester vẫn nhận dữ liệu nhưng giao diện timeline gây hiểu nhầm; đội phát triển cần xác định nguồn timestamp và tính toàn vẹn trace.
Tempo ghi block lên object storage nhưng quyền bucket bị đổi, ingester không thể hoàn tất flush và backlog tăng; nhóm cloud cần kiểm tra IAM và lỗi ghi object.
Một bucket S3 được chuyển sang chính sách lifecycle xóa object sau thời gian ngắn, block Tempo bị xóa trước retention dự kiến; đội vận hành cần đồng bộ lifecycle của object storage với chính sách Tempo.
Doanh nghiệp sử dụng object storage tương thích S3 nhưng endpoint yêu cầu path-style access, cấu hình Tempo dùng virtual-host style nên không tìm thấy bucket; nhóm hạ tầng cần kiểm tra cách định địa chỉ object.
Tempo kết nối tới S3 qua private endpoint, DNS nội bộ không phân giải hostname bucket sau thay đổi mạng; nhóm SRE cần kiểm tra DNS và routing từ từng component.
Một cụm Tempo dùng object storage với TLS, chứng chỉ CA nội bộ không được mount vào compactor nên truy cập bucket thất bại; nhóm vận hành cần xác định cấu hình trust cho mọi component.
Nền tảng lưu trace blocks trên object storage nhiều vùng, latency đọc tăng khi querier truy vấn dữ liệu ở vùng xa; nhóm kiến trúc cần đánh giá vị trí dữ liệu và đường truy cập.
Một doanh nghiệp dùng bucket chung cho nhiều môi trường, prefix và quyền truy cập không được phân tách khiến staging có thể đọc block production; đội bảo mật cần đánh giá cô lập dữ liệu.
Tempo ghi block thành công nhưng compactor không tìm thấy block mới do cấu hình bucket khác với ingester; nhóm SRE cần đối chiếu backend storage và tenant prefix.
Một bucket có hàng triệu object nhỏ do compactor ngừng hoạt động, chi phí request và thời gian truy vấn tăng; đội vận hành cần đánh giá compaction backlog.
Compactor được triển khai nhiều replica nhưng cấu hình sharding không nhất quán, khiến một số block bị nhiều instance xử lý lặp và retry tăng; nhóm nền tảng cần kiểm tra mô hình phân công công việc.
Một compactor có quyền đọc nhưng thiếu quyền ghi và xóa object, quá trình compact không hoàn tất và dữ liệu cũ vẫn tồn tại; nhóm cloud cần kiểm tra quyền theo từng thao tác.
Doanh nghiệp muốn rút ngắn retention trace, nhưng compactor chưa xử lý hết block cũ và lifecycle bucket chưa đồng bộ; nhóm SRE cần đánh giá thời điểm xóa thực tế.
Một bucket object storage bật versioning, compactor xóa object hiện hành nhưng các phiên bản cũ vẫn chiếm dung lượng; đội vận hành cần đánh giá chi phí và chính sách vòng đời phiên bản.
Nền tảng bật object lock cho bucket trace, compactor không thể xóa block hết hạn theo retention; nhóm compliance và hạ tầng cần làm rõ yêu cầu bất biến với yêu cầu xóa.
Một công ty chuyển bucket Tempo sang storage class lạnh, truy vấn trace cũ bị chậm hoặc phát sinh chi phí retrieval; nhóm kiến trúc cần phân loại dữ liệu theo tần suất truy cập.
Object storage trả lỗi 503 theo đợt, querier retry làm thời gian truy vấn tăng và request đồng thời chồng lấn; nhóm SRE cần đánh giá retry budget và timeout.
Một ứng dụng có trace được lưu thành block nhưng object bị thiếu do lỗi upload một phần, querier trả lỗi khi đọc; đội vận hành cần xác định cách phát hiện block hỏng và phạm vi ảnh hưởng.
Một nhóm backup bucket Tempo bằng cách sao chép object đang được ghi, snapshot không nhất quán giữa block và metadata; nhóm hạ tầng cần xác định quy trình backup có thể phục hồi.
Doanh nghiệp cần phục hồi Tempo sau mất vùng lưu trữ, nhưng chỉ backup bucket mà không lưu cấu hình tenant, ring và phiên bản; nhóm SRE cần xác định các thành phần cần thiết cho disaster recovery.
Một lần restore bucket cũ làm các block đã hết hạn xuất hiện lại trong truy vấn, retention metadata không được đồng bộ; nhóm vận hành cần xác định quy trình phục hồi và dọn dữ liệu sau restore.
Nền tảng dùng object storage với encryption at rest, nhưng key quản lý bị disable và querier không đọc được trace cũ; đội bảo mật cần đánh giá vòng đời khóa và khả năng phục hồi.
Một công ty bật server-side encryption cho bucket nhưng một số component ghi vào bucket phụ không có cùng chính sách; nhóm compliance cần kiểm tra toàn bộ storage destination.
Tempo có cấu hình backend S3 bằng secret trong file cấu hình, file được lưu trong repository nội bộ mà nhiều developer có quyền đọc; nhóm bảo mật cần đánh giá cách quản lý credential.
Một hệ thống dùng workload identity để truy cập bucket, nhưng compactor chạy ngoài cluster không nhận được identity và dùng key tĩnh; nhóm nền tảng cần đánh giá quyền theo môi trường triển khai.
Một tổ chức chia bucket theo tenant nhưng prefix cấu hình sai khiến traces của nhiều tenant nằm cùng vùng dữ liệu; nhóm vận hành cần kiểm tra định tuyến tenant tới storage.
Một hệ thống lưu trace theo tenant trong bucket chung, người dùng có thể truy vấn bằng tenant header tùy chọn và vô tình xem dữ liệu tenant khác khi header thiếu; nhóm bảo mật cần kiểm tra chế độ multi-tenancy.
Tempo bật multi-tenancy nhưng gateway không chuyển tiếp X-Scope-OrgID đúng cách, tất cả trace bị ghi vào tenant mặc định; đội SRE cần kiểm tra tenant context từ ingress tới storage.
Một dịch vụ cho phép client tự gửi X-Scope-OrgID, người dùng có thể giả tenant khác để ghi hoặc truy vấn trace; nhóm an ninh cần xác định điểm xác thực tenant identity.
Grafana datasource không gửi tenant header trong truy vấn, người dùng chỉ thấy trace của tenant mặc định và cho rằng dữ liệu đã mất; nhóm vận hành cần kiểm tra cấu hình truy vấn theo tenant.
Một công ty dùng một Grafana datasource cho nhiều tenant, quyền truy cập dashboard được kiểm soát nhưng người dùng có thể sửa header tenant trong truy vấn; nhóm bảo mật cần đánh giá authorization tại backend.
Nền tảng SaaS có khách hàng yêu cầu tách biệt trace giữa các tổ chức, nhưng cùng một service.name được dùng ở mọi tenant và dashboard dễ nhầm dữ liệu; nhóm kiến trúc cần thiết kế nhãn và phạm vi truy vấn.
Một tenant gửi lượng trace lớn hơn nhiều khách khác, làm ingester và object storage dùng chung bị quá tải; đội SRE cần đánh giá quota, rate limit và fairness theo tenant.
Tempo có override cấu hình theo tenant, nhưng một tenant mới chưa có giới hạn ingestion và có thể chiếm phần lớn tài nguyên; nhóm vận hành cần quản lý giá trị mặc định và onboarding tenant.
Một doanh nghiệp thay đổi tên tenant trong hệ thống định danh, nhưng dữ liệu lịch sử vẫn lưu dưới tenant ID cũ; nhóm SRE cần xác định mapping và quyền truy cập xuyên thời gian.
Một khách hàng ngừng hợp đồng, tài khoản bị khóa ở Grafana nhưng trace vẫn còn trong bucket và API Tempo vẫn có thể truy vấn nếu biết tenant ID; nhóm governance cần xác định quy trình đóng tenant.
Nền tảng cần xóa dữ liệu của một tenant, nhưng bucket chung có nhiều prefix và object theo tenant mà quy trình xóa không lập được mapping đầy đủ; đội kiến trúc cần đánh giá khả năng xóa chọn lọc và cơ chế compaction.
Một tổ chức dùng tenant ID từ header do reverse proxy gắn, nhưng endpoint Tempo nội bộ có thể truy cập trực tiếp và bỏ qua proxy; nhóm bảo mật cần kiểm tra đường truy cập bypass.
Tempo nhận trace từ nhiều nhóm sản phẩm, một nhóm quên đặt tenant context nên trace bị từ chối hoặc rơi vào tenant sai; nhóm nền tảng cần phát hiện dữ liệu thiếu tenant metadata.
Một cụm Tempo có nhiều tenant với retention khác nhau, compactor chỉ áp một chính sách chung và xóa dữ liệu của khách có thời hạn dài; nhóm vận hành cần kiểm tra override và thực thi retention.
Một khách hàng yêu cầu chỉ lưu trace ở một khu vực, nhưng multi-tenancy chỉ tách quyền logic chứ không tách bucket hay region; nhóm compliance cần đánh giá mức cô lập vật lý cần thiết.
Một công ty dùng nhiều Tempo cluster theo môi trường, datasource staging trỏ nhầm cluster production và hiển thị trace khách hàng thật; đội SRE cần xác minh endpoint, tenant và môi trường.
Một ứng dụng muốn tìm trace bằng TraceQL theo thuộc tính span, nhưng attribute được ghi ở resource scope nên biểu thức không trả kết quả như kỳ vọng; nhóm observability cần hiểu phạm vi thuộc tính.
Nhóm trực tìm trace có duration cao bằng TraceQL, nhưng các span có duration thiếu hoặc timestamp sai khiến kết quả không phản ánh trải nghiệm người dùng; đội phát triển cần xác định chất lượng dữ liệu đầu vào.
Một team dùng TraceQL lọc theo service.name nhưng SDK cũ ghi service dưới tên khác, truy vấn chỉ tìm thấy một phần trace; nhóm SRE cần quản lý semantic conventions và tương thích schema.
Ứng dụng có span attribute chứa mã khách hàng, người trực dùng TraceQL tìm trực tiếp giá trị đó nhưng chính sách quyền truy vấn không phân biệt tenant; nhóm bảo mật cần đánh giá quyền tìm kiếm.
Một truy vấn TraceQL dùng điều kiện trên event attribute nhưng instrumentation chỉ ghi thông tin vào span attribute; nhóm kỹ thuật cần xác định vị trí dữ liệu trong trace model.
Một trace có lỗi ở span con nhưng root span vẫn status unset, truy vấn TraceQL lọc lỗi ở root bỏ sót sự cố; đội SRE cần xác định cách biểu diễn lỗi qua cây span.
Nền tảng có hàng triệu trace trong block storage, truy vấn TraceQL không giới hạn thời gian và quét nhiều block làm querier dùng hết CPU; nhóm vận hành cần đánh giá phạm vi truy vấn và giới hạn tài nguyên.
Một query TraceQL trả kết quả chậm khi tìm thuộc tính hiếm trên thời gian dài, backend chưa có chiến lược index phù hợp; nhóm kiến trúc cần đánh giá tradeoff giữa khả năng tìm kiếm và chi phí indexing.
Một hệ thống tạo block mới liên tục nhưng querier chỉ thấy dữ liệu sau một khoảng trễ do blocklist polling; đội SRE cần xác định độ trễ khả kiến và kỳ vọng truy vấn gần thời gian thực.
Một người trực tìm trace theo trace ID ngay sau khi request hoàn tất nhưng chưa thấy vì dữ liệu còn trong ingester hoặc chưa được flush; nhóm vận hành cần phân biệt truy vấn dữ liệu mới và dữ liệu block.
Một truy vấn TraceQL trả nhiều kết quả từ nhiều tenant do datasource không truyền tenant scope, người dùng tưởng đó là trace trùng; nhóm nền tảng cần kiểm tra multi-tenancy trong query path.
Một dashboard truy vấn TraceQL liên tục mỗi vài giây với cửa sổ dài, querier tăng CPU và object storage request; nhóm SRE cần đánh giá tần suất refresh và cache.
Một hệ thống dùng query-frontend để chia nhỏ truy vấn, cấu hình concurrency quá cao khiến backend object storage bị burst request; đội vận hành cần cân bằng parallelism và khả năng phục vụ.
Query-frontend cache giữ kết quả trace cũ sau khi dữ liệu mới đã được ghi, người trực không thấy trace vừa phát sinh; nhóm SRE cần đánh giá cache key, TTL và yêu cầu freshness.
Một truy vấn TraceQL chạy lâu bị client timeout trước khi Tempo hoàn thành, nhóm trực lặp lại nhiều lần và làm tải tăng thêm; đội vận hành cần kiểm tra timeout giữa Grafana, gateway và query-frontend.
Một service dùng tên route có giá trị động trong spans, TraceQL tìm theo route template không khớp vì instrumentation ghi raw URL; nhóm phát triển cần chuẩn hóa span attributes.
Một nhóm muốn tìm tất cả traces có lỗi database, nhưng các service dùng nhiều tên span và exception attribute khác nhau; nhóm SRE cần thống nhất schema instrumentation cho truy vấn.
Một hệ thống có trace dài hàng giờ, giới hạn query max duration làm kết quả không đầy đủ khi người dùng tìm cả phiên; đội vận hành cần đánh giá giới hạn truy vấn và chia phạm vi thời gian.
Nền tảng Tempo không trả kết quả tìm kiếm theo tag mới ngay sau deploy, do block cũ chưa được index theo cùng metadata; nhóm SRE cần đánh giá thay đổi schema và dữ liệu lịch sử.
Một doanh nghiệp muốn cung cấp TraceQL cho khách hàng tự phục vụ, nhưng chưa có giới hạn truy vấn và kiểm soát tài nguyên theo tenant; nhóm sản phẩm cần đánh giá nguy cơ một tenant ảnh hưởng tenant khác.
Ứng dụng có spans rất nhiều nhưng không có parent-child relation nhất quán, TraceQL tìm cấu trúc trace không thể nhận diện luồng nghiệp vụ; đội kiến trúc cần kiểm tra instrumentation và propagation.
Một trace chứa link tới trace khác trong tác vụ bất đồng bộ, truy vấn TraceQL chỉ tìm trace gốc và không nối được workflow; nhóm SRE cần đánh giá cách mô hình hóa quan hệ phân tán.
Nền tảng cần tìm trace theo HTTP status code, nhưng một số service chỉ đặt status attribute tùy biến và không đặt span status chuẩn; nhóm kỹ thuật cần chuẩn hóa dữ liệu.
Một ứng dụng phát trace với service.name là tên pod, mỗi lần rollout tạo service mới trong service graph; đội vận hành cần chuẩn hóa service identity.
Tempo metrics-generator bật processor service-graphs nhưng không thấy cạnh giữa hai service do spans thiếu parent relationship hoặc peer metadata; nhóm SRE cần xác định điều kiện dữ liệu đầu vào.
Một hệ thống bật service graph cho toàn bộ trace volume, metrics-generator sử dụng CPU và bộ nhớ cao; đội vận hành cần đánh giá tỷ lệ sampling và phạm vi sinh metric.
Service graph hiển thị một service có lượng request thấp hơn backend metrics, do một phần trace bị sampling trước khi đến Tempo; nhóm SRE cần phân biệt số liệu từ traces với số liệu từ request metrics.
Một service graph có cạnh giữa proxy và ứng dụng nhưng tên service bị trùng giữa hai cluster, dashboard hợp nhất topology của môi trường khác nhau; nhóm nền tảng cần thêm metadata phân biệt.
Metrics-generator tạo span metrics và service graph nhưng remote write endpoint bị lỗi xác thực, trace vẫn lưu bình thường còn metrics không xuất hiện; đội vận hành cần giám sát pipeline sinh metrics riêng.
Một cụm Tempo dùng metrics-generator, nhưng generator không tham gia ring đúng cách sau rollout và các trace được xử lý không đồng đều; nhóm SRE cần kiểm tra membership và phân phối workload.
Một doanh nghiệp bật metrics-generator nhưng cấu hình local blocks và processor chưa nhất quán giữa replicas, service graph bị thiếu cạnh ngẫu nhiên; nhóm nền tảng cần kiểm tra cấu hình và trạng thái từng replica.
Service graph báo nhiều cạnh unknown vì một số spans không có peer.service hoặc service.name, nhóm phát triển cần xác định metadata tối thiểu cho quan hệ giữa dịch vụ.
Một ứng dụng sử dụng proxy và service mesh, spans của cùng request bị gắn service name theo sidecar thay vì workload, topology hiển thị các node trung gian dư thừa; đội observability cần xác định quy ước tên.
Metrics-generator tạo request và error metrics từ spans, nhưng sampling làm tỷ lệ lỗi trong graph khác với Prometheus HTTP metrics; nhóm SRE cần hiểu độ đại diện và nguồn dữ liệu.
Một đội muốn dùng service graph để phát hiện service không có inbound traffic, nhưng các spans một chiều bị mất khi exporter không gửi client hoặc server span; nhóm kỹ thuật cần kiểm tra instrumentation hai đầu.
Nền tảng dùng service graph cho nhiều tenant, nhãn tenant bị loại trước remote write nên các metrics của khách hàng bị gộp; nhóm vận hành cần giữ metadata phân tách.
Một metrics-generator gửi service graph metrics tới Prometheus bằng remote write, nhưng nhãn instance không ổn định làm series liên tục thay đổi; nhóm SRE cần chuẩn hóa nhãn và cardinality.
Một tổ chức bật span metrics với dimensions tùy biến theo user_id, số lượng series tăng nhanh và Prometheus bị quá tải; đội nền tảng cần giới hạn dimensions theo mục tiêu quan sát.
Hệ thống metrics-generator có queue remote write tăng nhưng alert chỉ theo trace ingestion, đội trực không nhận ra service graph đã ngừng cập nhật; nhóm SRE cần thiết kế cảnh báo theo từng luồng.
Một cụm Tempo có service graph nhưng dashboard không cập nhật khi trace sampling rate thay đổi, nhóm sản phẩm hiểu nhầm lưu lượng giữa service đã giảm; đội observability cần ghi nhận nguồn và tỷ lệ lấy mẫu.
Một ứng dụng gửi spans từ service mesh và instrumentation SDK cùng lúc, metrics-generator đếm hai lần cùng request và service graph hiển thị throughput gấp đôi; nhóm SRE cần xác định dữ liệu trùng.
Một team muốn phân tích latency giữa hai service qua service graph, nhưng spans thiếu timestamp đồng bộ và duration sai; nhóm vận hành cần đánh giá độ tin cậy của dữ liệu quan hệ.
Nền tảng có nhiều Tempo replicas, metrics-generator được bật trên mọi replica nhưng cấu hình processor khác nhau; kết quả span metrics không nhất quán giữa các lần ghi; đội SRE cần quản lý config drift.
Một service graph xuất hiện node database như một service độc lập, nhưng các span client không gắn peer.service nhất quán; nhóm kiến trúc cần xác định cách chuẩn hóa dependency metadata.
Một doanh nghiệp muốn lưu traces dài hạn cho điều tra bảo mật, nhưng object storage tăng dung lượng nhanh do mọi span được giữ ở sampling 100%; đội tài chính cần đánh giá retention và sampling theo loại sự kiện.
Nền tảng SaaS bật retention 30 ngày trong Tempo nhưng bucket lifecycle xóa object sau 14 ngày, trace cũ biến mất sớm hơn chính sách; nhóm vận hành cần đồng bộ hai lớp retention.
Một công ty tăng retention từ 7 lên 90 ngày nhưng không dự báo số block và object request, hóa đơn storage tăng ngoài kế hoạch; nhóm SRE cần lập mô hình chi phí theo ingestion và thời gian giữ.
Tempo compact blocks thành object lớn hơn, nhưng compaction concurrency thấp làm backlog kéo dài và số object nhỏ tiếp tục tăng; nhóm vận hành cần đánh giá CPU, memory và giới hạn concurrency.
Một bucket có storage class chuyển sang archival sau 30 ngày, nhưng người trực thường xuyên truy vấn trace trong 45 ngày; đội kiến trúc cần cân nhắc chi phí retrieval so với mức độ truy cập.
Nền tảng lưu trace cho nhiều tenant trong cùng bucket, một tenant tạo trace payload rất lớn làm chi phí lưu và đọc của các tenant khác tăng; nhóm sản phẩm cần xem xét quota và công bằng tài nguyên.
Một hệ thống không có lifecycle dọn object cũ sau khi tenant hết hạn, dữ liệu tiếp tục chiếm dung lượng dù Tempo không còn truy vấn; đội governance cần xác định quy trình xóa dữ liệu.
Doanh nghiệp dùng bucket versioning để phục hồi object, nhưng compactor xóa phiên bản hiện tại trong khi old versions vẫn tính phí; nhóm cloud cần đánh giá chi phí version retention.
Một ứng dụng tạo spans với attribute chứa payload JSON lớn, trace block phình lên và chi phí lưu trữ tăng dù request rate không đổi; nhóm phát triển cần đánh giá giới hạn thuộc tính.
Một đội giảm sampling để tiết kiệm chi phí nhưng bỏ lỡ trace lỗi quan trọng trong một số luồng thanh toán; nhóm SRE cần thiết kế chiến lược sampling theo rủi ro nghiệp vụ.
Tempo query cache được cấu hình quá nhỏ, các truy vấn dashboard lặp lại liên tục đọc lại object storage và tăng chi phí request; đội vận hành cần đánh giá hit ratio và dung lượng cache.
Một công ty bật cache lớn trên querier nhưng workload thay đổi liên tục, cache eviction cao và bộ nhớ bị lãng phí; nhóm SRE cần chọn kích thước và TTL theo mẫu truy vấn.
Object storage tính phí theo số request, query frontend chia truy vấn thành quá nhiều phần nhỏ khiến chi phí GET tăng mạnh; nhóm kiến trúc cần cân bằng parallelism và request volume.
Một nền tảng có lượng trace tăng vào cuối tuần, capacity plan chỉ dựa trên mức trung bình ngày thường và ingester bị quá tải; nhóm SRE cần dự báo peak ingestion.
Hệ thống Tempo lưu nhiều trace không có span hữu ích do instrumentation tạo span rỗng, block storage tăng mà khả năng điều tra không cải thiện; nhóm phát triển cần nâng chất lượng instrumentation.
Một nhóm thêm nhiều custom attributes vào mỗi span để phục vụ dashboard, dữ liệu lặp lại ở mọi span làm block tăng kích thước; đội observability cần đánh giá giá trị và chi phí metadata.
Một công ty lưu trace trong object storage dùng request pricing cao, compactor và querier cùng tạo burst vào giờ báo cáo; nhóm cloud cần đánh giá lịch và giới hạn hoạt động nền.
Nền tảng sử dụng compression cho trace blocks, CPU compactor tăng và thời gian compact vượt ngưỡng; nhóm vận hành cần cân bằng tỷ lệ nén, chi phí lưu và tài nguyên xử lý.
Một doanh nghiệp bật retention theo tenant nhưng một nhóm khách gửi trace vào tenant mặc định, dữ liệu được giữ theo chính sách ngắn hơn hợp đồng; nhóm governance cần phát hiện tenant mapping sai.
Tempo có nhiều tenant, nhưng không theo dõi bytes ingested theo tenant nên không thể phân bổ hóa đơn object storage; nhóm SRE cần xác định cách đo dung lượng và lưu lượng từng khách.
Một cụm Tempo sử dụng nhiều querier, truy vấn lớn của một tenant chiếm hết concurrency và làm dashboard của tenant khác chậm; đội vận hành cần đánh giá giới hạn truy vấn theo tenant.
Một doanh nghiệp giới hạn ingestion theo tenant nhưng không giới hạn trace size, một khách gửi batch rất lớn và làm distributor tăng bộ nhớ; nhóm nền tảng cần xác định các giới hạn kết hợp.
Hệ thống Tempo trả lỗi khi tenant vượt quota, nhưng client Alloy retry không có backoff và tạo thêm áp lực; nhóm SRE cần kiểm tra retry behavior giữa sender và receiver.
Một khách hàng yêu cầu chỉ một nhóm nhân viên được truy vấn traces nhạy cảm, nhưng Tempo chỉ nhận tenant header và không xác định người dùng cuối; nhóm bảo mật cần phân biệt tenant isolation với user authorization.
Một hệ thống có tenant header được thêm ở gateway, nhưng internal service cho phép truy cập trực tiếp và bỏ qua kiểm tra; nhóm an ninh cần rà các endpoint nội bộ và đường bypass.
Doanh nghiệp muốn tenant A và B dùng chung trace backend nhưng retention khác nhau, override cấu hình không được áp dụng do tenant ID sai chữ hoa thường; nhóm vận hành cần kiểm tra định danh tenant.
Một tổ chức chuyển tenant sang cluster Tempo mới, dashboard vẫn truy vấn cluster cũ và hiển thị dữ liệu trễ; nhóm SRE cần xác định mapping datasource và thời điểm chuyển.
Một hệ thống multi-tenant có một tenant ngừng hợp đồng, nhưng bucket versioning, bản sao dự phòng và cache còn giữ object thuộc tenant đó; nhóm kiến trúc cần đánh giá ranh giới lưu trữ và quy trình xóa.
Nền tảng Tempo cần khôi phục một tenant sau khi xóa nhầm, backup bucket không ghi nhận mapping tenant và retention; nhóm vận hành cần đánh giá khả năng phục hồi dữ liệu chọn lọc.
Một công ty dùng Grafana folder permissions để phân tách dashboard nhưng datasource Tempo vẫn cho phép truy vấn mọi tenant; đội bảo mật cần kiểm tra quyền ở backend.
Một truy vấn TraceQL từ dashboard chia sẻ công khai có thể truy xuất spans thuộc tenant khác do biến tenant được truyền từ URL; nhóm SRE cần xác định rủi ro chia sẻ truy vấn.
Một hệ thống gửi traces qua Alloy gateway, header tenant được lấy từ HTTP request do client kiểm soát; nhóm bảo mật cần xác định cách xác thực tenant trước khi chuyển tới Tempo.
Tempo chạy sau ingress, ingress bỏ header X-Scope-OrgID khi proxy request; các trace được ghi vào tenant rỗng và không thể tìm từ dashboard đúng; nhóm vận hành cần kiểm tra header forwarding.
Một doanh nghiệp muốn theo dõi thời gian từ span phát ra tới khi trace tìm được trong Tempo, nhưng chỉ đo ingestion rate; nhóm SRE cần thiết kế chỉ số end-to-end freshness.
Tempo distributor trả lỗi 429 khi vượt giới hạn, nhưng dashboard chỉ hiển thị tổng request nhận được nên nhóm trực không thấy tỷ lệ bị từ chối; đội vận hành cần xác định các chỉ số lỗi ingestion.
Ingester flush block thất bại liên tục do object storage timeout, WAL tăng nhưng alert chỉ dựa trên process up; nhóm SRE cần xây cảnh báo về tiến độ flush và backlog.
Một cụm Tempo có compactor chạy nhưng không xử lý được block do metadata không đọc được, log lỗi không được tổng hợp vào dashboard; nhóm vận hành cần xác định health signal cho compaction.
Query frontend nhận request bình thường nhưng querier thiếu kết nối object storage, truy vấn trả lỗi sau thời gian dài; nhóm SRE cần giám sát từng thành phần và dependency.
Một hệ thống tự giám sát Tempo gửi metrics của chính Tempo vào cùng Tempo cluster qua tracing pipeline, khi backend lỗi nhóm trực mất luôn dữ liệu chẩn đoán; đội kiến trúc cần xác định kênh giám sát độc lập.
Nền tảng có ring unhealthy nhưng alert chỉ kiểm tra replica count của Kubernetes, pod đủ số lượng mà các ingester không tham gia ring; nhóm SRE cần phân biệt process health và ring health.
Một cụm Tempo có blocklist polling chậm, trace mới lưu chưa xuất hiện trong query trong khoảng dài; nhóm vận hành cần đo độ trễ block visibility và đặt kỳ vọng cho người dùng.
Một ứng dụng gửi trace đầy đủ nhưng Grafana datasource không hỗ trợ cấu hình tenant hiện tại, truy vấn trả 401; đội nền tảng cần xác định phiên bản plugin và cấu hình xác thực.
Một tổ chức nâng cấp Grafana và Tempo không đồng bộ, TraceQL query cũ không còn chạy do khác biệt phiên bản hoặc cú pháp; nhóm SRE cần kiểm tra tương thích và kế hoạch nâng cấp.
Một truy vấn TraceQL tìm kiếm rộng làm querier đọc nhiều block, người dùng lặp truy vấn do dashboard refresh liên tục và làm object storage quá tải; nhóm vận hành cần theo dõi query duration và concurrency.
Một hệ thống có latency truy vấn tăng sau khi thêm index hoặc search attributes, chi phí compactor tăng đáng kể; nhóm kiến trúc cần đánh giá tradeoff giữa tốc độ tìm kiếm và chi phí indexing.
Nền tảng dùng trace search trong cửa sổ gần đây nhưng block cũ chưa được compact, kết quả tìm kiếm giữa dữ liệu mới và cũ khác nhau; nhóm SRE cần xác định phạm vi tìm kiếm và tình trạng block.
Một đội phát triển đổi tên span attribute sau release, truy vấn TraceQL và dashboard cũ không còn tìm được lỗi; nhóm observability cần quản lý schema và kiểm thử truy vấn phụ thuộc.
Một service dùng tên pod làm service.name, mỗi lần rollout tạo service mới trong service graph; đội vận hành cần chuẩn hóa service identity.
Một doanh nghiệp dùng Tempo để phân tích trace lỗi nhưng một số service không đặt status code hoặc exception event; nhóm phát triển cần xác định mức instrumentation cần thiết để truy vấn nhất quán.
Một cụm Tempo có query-frontend cache dữ liệu theo tenant nhưng cache key thiếu một thành phần định danh, kết quả có nguy cơ bị trả chéo giữa tenant; đội bảo mật cần đánh giá cách cô lập cache.
Một hệ thống có nhiều querier dùng chung cache, cache hit từ tenant khác làm kết quả truy vấn không đúng phạm vi; nhóm nền tảng cần kiểm tra tenant-aware cache key.
Một công ty lưu trace trong bucket dùng chung với nhiều ứng dụng, IAM chỉ phân quyền ở mức bucket nên một component bị xâm nhập có thể đọc dữ liệu mọi tenant; nhóm bảo mật cần đánh giá phạm vi credential.
Một bucket Tempo có quyền public do cấu hình sai trong đợt migration, traces chứa thông tin request có thể bị tải trực tiếp; đội ứng cứu cần xác định phạm vi phơi lộ và lịch sử truy cập.
Một doanh nghiệp mã hóa object storage nhưng key encryption bị xoay mà không lưu quy trình truy cập khóa cũ, trace lịch sử không còn đọc được; nhóm vận hành cần đánh giá key lifecycle và disaster recovery.
Một công ty bật object lock cho block trace phục vụ kiểm toán, nhưng compactor cần xóa dữ liệu theo retention; nhóm kiến trúc cần xác định chính sách bất biến và thời hạn lưu.
Một hệ thống có bucket versioning và replication đa vùng, xóa tenant data ở vùng chính nhưng object còn trong bản sao; nhóm governance cần kiểm tra xóa và retention trên mọi bản sao.
Tempo chạy trong Kubernetes, một pod querier bị CPU throttling và truy vấn chỉ chậm trên một số node; nhóm SRE cần đối chiếu scheduling, resource requests và tải thực.
Một cluster Tempo bị thiếu memory limit cho query-frontend, một truy vấn TraceQL lớn làm pod OOM và ảnh hưởng người dùng khác; đội vận hành cần xác định giới hạn truy vấn và tài nguyên.
Một cụm ingester dùng persistent volume chậm, thời gian ghi WAL tăng và distributor bắt đầu timeout; nhóm hạ tầng cần đánh giá IOPS và latency storage.
Một tổ chức triển khai Tempo bằng Helm chart mới, giá trị cấu hình object storage không được render như dự kiến và component dùng endpoint mặc định; nhóm DevOps cần kiểm tra manifest thực trước rollout.
Một nhóm cập nhật Tempo config qua GitOps nhưng Secret backend được rotate ngoài Git, pod cũ và mới dùng credential khác nhau; nhóm nền tảng cần kiểm soát drift và đồng bộ secret.
Một doanh nghiệp chạy Tempo trên nhiều availability zones, disruption budget không phù hợp khiến bảo trì node làm mất quá nhiều ingester cùng lúc; nhóm SRE cần đánh giá tính sẵn sàng trong kế hoạch bảo trì.
Một cụm Tempo scale down querier trong giờ thấp điểm nhưng query-frontend vẫn giữ concurrency cao, các querier còn lại quá tải khi traffic tăng bất ngờ; nhóm vận hành cần đánh giá autoscaling và tải đỉnh.
Một tổ chức muốn nâng cấp Tempo không gián đoạn, nhưng schema block và cấu hình compactor khác giữa phiên bản cũ và mới; nhóm nền tảng cần xác định trình tự nâng cấp và khả năng rollback.
Một lần rollout mới làm distributor và ingester chạy hai cấu hình khác nhau về tenant limits, request được chấp nhận ở đầu vào nhưng thất bại khi ghi; nhóm SRE cần đồng bộ overrides giữa component.
Một cụm Tempo được khôi phục từ backup ở cluster mới, ring vẫn chứa địa chỉ instance cũ và các request bị gửi tới thành viên không tồn tại; nhóm vận hành cần xác định dữ liệu trạng thái nào cần tái tạo.
Một doanh nghiệp chuyển object storage provider, dữ liệu block được copy nhưng compactor và querier vẫn trỏ bucket cũ; nhóm kiến trúc cần kiểm chứng cutover cho toàn bộ component.
Một ứng dụng bật instrumentation mới làm spans tăng gấp năm lần, Tempo ingestion vẫn thành công nhưng storage cost và query latency tăng; nhóm SRE cần đo tác động theo service và phiên bản.
Một đội muốn biết service nào tạo nhiều trace bytes nhất, dashboard chỉ có tổng số spans và không có phân bổ theo tenant hoặc service; nhóm observability cần xác định chỉ số ingestion và dung lượng hữu ích.
Nền tảng có số trace nhận vào ổn định nhưng số trace truy vấn được giảm dần, compactor và querier không có chỉ số đối soát; nhóm SRE cần xây dựng kiểm tra đầy đủ từ nhận đến truy vấn.
Một doanh nghiệp muốn cảnh báo khi Tempo mất trace data, nhưng chỉ kiểm tra HTTP health của distributor; nhóm vận hành cần xác định tín hiệu cho WAL, flush, block storage và query.
Một hệ thống có service graph metrics được remote-write tới Prometheus, endpoint đích ngừng hoạt động nhưng Tempo trace ingestion vẫn khỏe; nhóm SRE cần giám sát độc lập pipeline metrics-generator.
Một cụm Tempo bị lệch đồng hồ giữa các node, thời gian block và span không nhất quán làm khó tìm kiếm theo cửa sổ; đội hạ tầng cần xác định đồng bộ thời gian và nguồn timestamp.
Một doanh nghiệp muốn đặt SLO cho trace availability, nhưng không có synthetic trace được gửi định kỳ nên không biết đường ingestion và query có hoạt động hay không; nhóm SRE cần thiết kế kiểm tra đầu cuối.
Một nhóm trực phát hiện dashboard Tempo không có dữ liệu trong một khoảng thời gian, nhưng không phân biệt được ứng dụng không phát trace hay backend mất trace; nhóm observability cần đối chiếu telemetry nguồn và tín hiệu ingestion.
Một công ty có nhiều pipeline Alloy gửi tới Tempo, sau thay đổi cấu hình chỉ một nhóm ứng dụng ngừng gửi nhưng health endpoint của gateway vẫn xanh; đội vận hành cần kiểm tra coverage theo nguồn.
Một hệ thống có lỗi query sau khi nâng cấp object storage, nhóm SRE chỉ xem log Tempo mà không xem latency và lỗi API của bucket; đội vận hành cần xác định các dependency cần quan sát cùng nhau.
Một doanh nghiệp muốn giới hạn chi phí Tempo theo tenant, nhưng hóa đơn object storage chỉ phân bổ theo bucket chung; nhóm tài chính cần xác định cách đo ingestion, bytes và query workload theo tenant.
Một nền tảng giữ trace lâu hơn cho luồng thanh toán quan trọng, nhưng không có cơ chế phân biệt service hoặc loại trace trước khi áp retention; nhóm kiến trúc cần xác định metadata và chính sách lưu theo rủi ro.
Một tổ chức cần đáp ứng yêu cầu xóa trace theo tenant, nhưng dữ liệu trong block có thể gộp nhiều tenant và backup tồn tại lâu hơn; nhóm compliance cần đánh giá khả năng xóa chọn lọc và bằng chứng thực hiện.
Một ứng dụng gửi trace có customer email trong span attributes, Tempo lưu nguyên dữ liệu trên object storage và dashboard chỉ che khi hiển thị; nhóm bảo mật cần xác định điểm redaction trước lưu trữ.
Một doanh nghiệp dùng TraceQL để tìm trace có dữ liệu nhạy cảm, nhưng attribute name thay đổi giữa các SDK nên truy vấn kiểm tra không bao phủ toàn bộ dữ liệu; đội governance cần kiểm thử schema drift.
Một công ty cho phép nhà cung cấp APM hỗ trợ điều tra trên Tempo, nhưng credential cho phép truy vấn mọi tenant; nhóm bảo mật cần xác định quyền tối thiểu và phạm vi truy vấn.
Một đội phát triển chia sẻ link trace trong ticket công khai nội bộ, link có thể truy cập được bởi nhân viên ngoài nhóm sản phẩm; nhóm governance cần đánh giá quyền chia sẻ và thời hạn truy cập.
Nền tảng Tempo bật auth ở ingress nhưng service querier nội bộ vẫn có thể được truy cập trực tiếp từ mạng ứng dụng; nhóm an ninh cần kiểm tra các đường bypass.
Một cụm Tempo có endpoint ingestion công khai, attacker gửi trace với số lượng spans cực lớn làm tăng chi phí object storage; đội bảo mật cần đánh giá rate limiting, tenant limits và kiểm soát nguồn.
Một doanh nghiệp sử dụng trace IDs để liên kết logs và metrics, nhưng chính sách privacy yêu cầu giảm khả năng nhận diện lâu dài; nhóm kiến trúc cần xác định vòng đời và phạm vi của correlation identifiers.
Một hệ thống dùng TraceQL để tìm kiếm thông tin khách hàng theo ID, nhưng quyền query không được kiểm tra ở mức thuộc tính; nhóm bảo mật cần đánh giá rủi ro truy xuất dữ liệu nhạy cảm.
Một công ty triển khai service graph cho các dịch vụ đa tenant, nhãn tenant bị loại trong metrics-generator và topology của khách hàng bị gộp; nhóm SRE cần giữ phân tách mà không làm tăng cardinality quá mức.
Một ứng dụng có spans từ proxy và backend nhưng một số request bị thiếu một phía do sampling khác nhau, service graph hiển thị tỷ lệ lỗi và throughput sai; nhóm observability cần đánh giá sự nhất quán sampling.
Một nhóm cấu hình Tempo retention theo tenant nhưng dashboard báo dữ liệu vẫn tồn tại sau hạn, do block chưa được compactor xử lý và object lifecycle chưa đồng bộ; đội vận hành cần xác định xóa logic và xóa vật lý.
Một tổ chức muốn backup Tempo mỗi ngày, nhưng không xác định RPO/RTO cho WAL, object blocks và cấu hình; nhóm hạ tầng cần xây mục tiêu phục hồi theo thành phần.
Một lần restore Tempo thành công nhưng các trace mới trong WAL trước sự cố không xuất hiện, nhóm vận hành chỉ xác minh bucket cũ đọc được; nhóm SRE cần kiểm thử phục hồi đầu cuối.
Một doanh nghiệp cần audit việc ai truy vấn traces nhạy cảm, Tempo backend chỉ ghi log truy vấn ở gateway mà không gắn người dùng cuối; nhóm bảo mật cần xác định audit trail cho thao tác đọc.
Một cụm Tempo dùng chung object storage credential cho distributor, querier và compactor, quyền xóa của compactor cũng được cấp cho mọi thành phần; nhóm bảo mật cần đánh giá tách quyền theo vai trò.
Một nền tảng có query-frontend và querier ở nhiều zone, một zone mất kết nối object storage nhưng health check vẫn thành công; đội SRE cần kiểm tra dependency health và khả năng phục vụ truy vấn.
Một hệ thống dùng cache cho trace blocks, cache node bị đầy nhưng không có eviction metrics và query latency tăng; nhóm vận hành cần tự giám sát cache hit, miss và dung lượng.
Một doanh nghiệp triển khai Tempo với object storage tương thích S3, backend thay đổi yêu cầu path-style và region signing sau nâng cấp; nhóm hạ tầng cần xác minh cấu hình tương thích và lỗi ký request.
Một team cấu hình bucket lifecycle xóa dữ liệu cũ theo ngày tạo object, compactor tạo object mới từ block cũ khiến thời điểm xóa bị kéo dài; nhóm vận hành cần hiểu tương tác giữa compaction và lifecycle.
Một ứng dụng phát spans với service.name thay đổi theo tenant, metrics-generator tạo hàng nghìn service graph nodes và tăng cardinality; đội observability cần chuẩn hóa service identity.
Một nền tảng dùng Tempo để theo dõi service graph, nhưng một số span server không có span kind chính xác nên quan hệ client-server bị suy luận sai; nhóm phát triển cần chuẩn hóa instrumentation.
Một hệ thống có các span database được đặt tên theo SQL query đầy đủ, service graph và TraceQL trở nên khó nhóm do tên động; nhóm SRE cần chuẩn hóa span name và attributes.
Một doanh nghiệp có nhiều traces từ batch job kéo dài hàng giờ, TraceQL truy vấn cửa sổ ngắn bỏ qua các span bắt đầu trước cửa sổ; nhóm vận hành cần xác định cách tìm theo thời gian bắt đầu và kết thúc.
Một dashboard Grafana truy vấn Tempo với refresh interval rất ngắn, query frontend liên tục tạo công việc lặp và làm chậm truy vấn điều tra; nhóm SRE cần đánh giá tần suất refresh theo nhu cầu.
Một ứng dụng sử dụng exemplars từ Prometheus để mở trace trong Tempo, trace ID được gắn sai sau khi proxy tạo trace mới; đội observability cần kiểm tra propagation giữa metrics và traces.
Một nhóm muốn tìm trace từ log bằng trace_id, nhưng log pipeline chuyển chữ hoa thành chữ thường trong khi trace ID có định dạng khác; nhóm kỹ thuật cần chuẩn hóa ID và giữ tính toàn vẹn.
Một hệ thống dùng Tempo với nhiều cluster, Grafana datasource mặc định chỉ trỏ một cluster và không có thông tin môi trường trên link trace; nhóm vận hành cần xác định cách điều hướng đúng backend.
Một công ty có một Tempo cluster cho production và một cluster cho disaster recovery, exporter gửi trace tới cả hai nhưng tenant IDs khác nhau; đội SRE cần xác định đồng bộ cấu hình và truy vấn khi failover.
Một hệ thống có traces đến từ nhiều SDK với sampling probability khác nhau, số liệu service graph không thể so sánh giữa các service; nhóm observability cần ghi nhận chính sách sampling và nguồn số liệu.
Một nền tảng muốn giảm storage bằng cách loại span event không quan trọng, nhưng một số sự kiện exception là bằng chứng cần cho điều tra; nhóm phát triển cần xác định quy tắc giữ và loại dữ liệu.
Một doanh nghiệp bật compression cho OTLP và object blocks, CPU tăng đáng kể ở distributor và compactor trong giờ cao điểm; đội SRE cần đánh giá chi phí CPU so với tiết kiệm network và storage.
Một cụm Tempo dùng query parallelism cao để cải thiện TraceQL, object storage throttling và số lỗi 503 tăng; nhóm vận hành cần tìm điểm cân bằng giữa tốc độ truy vấn và giới hạn backend.
Một hệ thống có lượng truy vấn lớn nhưng ingestion thấp, query-frontend bị quá tải trong khi ingester nhàn rỗi; đội nền tảng cần tách năng lực đọc và ghi khi scale.
Một doanh nghiệp có ingestion burst theo giờ, autoscaling distributor phản ứng chậm khiến request bị timeout trước khi pod mới sẵn sàng; nhóm SRE cần đánh giá tín hiệu scale và thời gian khởi động.
Một compactor dùng quá nhiều CPU làm ảnh hưởng querier trên cùng node, trace query chậm đúng lúc compact; nhóm vận hành cần phân tách tài nguyên và lịch xử lý nền.
Một tổ chức muốn giám sát chi phí Tempo theo trace bytes, nhưng chỉ thu số spans và không đo kích thước block; nhóm tài chính cần xác định phép đo dung lượng thực tế.
Một hệ thống có nhiều tenant nhưng không có thống kê query bytes và query duration theo tenant, một khách hàng gây tải cao mà không thể xác định; đội SRE cần xây dựng quan sát mức sử dụng công bằng.
Một nền tảng muốn phát hiện trace bị mất giữa Alloy và Tempo, nhưng chỉ đối chiếu tổng số spans ở hai hệ thống trong cửa sổ khác nhau; nhóm kỹ thuật cần xác định phương pháp đối soát có tính đến sampling và batching.
Một ứng dụng nâng cấp SDK làm trace volume tăng gấp đôi nhưng request rate không đổi, đội vận hành không có cảnh báo thay đổi span-per-trace; nhóm SRE cần theo dõi chất lượng và chi phí instrumentation.
Một hệ thống dùng Tempo với object storage có latency biến động, alert chỉ theo tỷ lệ lỗi truy vấn nên không phát hiện tình trạng truy vấn chậm nhưng vẫn thành công; nhóm vận hành cần giám sát độ trễ phân vị.
Một doanh nghiệp cần đặt SLO cho trace availability, nhưng không có synthetic traces hoặc phép đo freshness; nhóm SRE cần thiết kế kiểm tra từ gửi trace đến query thành công.
Một cụm Tempo có distributor healthy nhưng ingester ring không đủ replica, hệ thống vẫn nhận request nhưng độ bền dữ liệu suy giảm; nhóm trực cần xác định chỉ số trạng thái ring và replication.
Một ứng dụng gửi trace tới Tempo trong khi object storage bị lỗi, request ingestion vẫn được buffer tạm thời; nhóm vận hành cần xác định giới hạn thời gian buffer và điều kiện từ chối.
Một công ty triển khai Tempo bằng Terraform và Helm, cấu hình bucket IAM thay đổi nhưng không có kiểm thử quyền đọc/ghi/xóa trước rollout; đội DevOps cần xác định validation cho storage dependency.
Một tổ chức muốn kiểm tra chính sách multi-tenancy, test chỉ xác minh tenant A không đọc tenant B trên Grafana UI mà không gọi trực tiếp API; nhóm bảo mật cần kiểm thử authorization ở mọi lớp.
Một đội SRE phát hiện traces từ tenant mặc định chứa dữ liệu khách hàng thật do header bị thiếu, nhưng chưa có cảnh báo tenant rỗng; nhóm vận hành cần xác định kiểm soát phát hiện và cách xử lý dữ liệu đã ghi.
Một doanh nghiệp triển khai Tempo mới nhưng không chạy kiểm tra truy vấn TraceQL trên bộ trace mẫu, dashboard production chỉ phát hiện sai schema sau release; nhóm QA cần xây dựng kiểm thử truy vấn hồi quy.
Một ứng dụng dùng service graph để phát hiện dependency mới, nhưng processor chỉ bật trên một phần Tempo replicas; nhóm nền tảng cần kiểm tra cấu hình metrics-generator đồng nhất.
Một hệ thống ghi traces vào object storage nhưng không giám sát số block chưa compact và thời gian block visibility, người trực không phân biệt ingest delay với query outage; đội SRE cần xây dashboard vận hành.
Một nền tảng có nhiều phiên bản Tempo, một số component dùng config overrides khác nhau và giới hạn tenant không đồng nhất; nhóm DevOps cần xác định quy trình quản lý cấu hình trung tâm.
Một doanh nghiệp muốn xóa dữ liệu trace sau khi hết thời hạn hợp đồng, nhưng không kiểm kê các bản sao trong backup, cache và bucket versioning; nhóm compliance cần xác định toàn bộ vòng đời dữ liệu.
Một công ty gửi trace chứa customer email và query parameters vào Tempo, chỉ che dữ liệu trong Grafana panel nhưng object storage vẫn chứa giá trị gốc; nhóm bảo mật cần xác định điểm sanitization trước khi lưu trữ.
Một hệ thống dùng Tempo tenant header làm ranh giới logic, nhưng quyền object storage cho phép querier đọc toàn bộ bucket; đội an ninh cần đánh giá phạm vi truy cập ở tầng lưu trữ.
Một doanh nghiệp cung cấp trace access cho đối tác qua Grafana, nhưng không ghi nhận người dùng cuối đã truy vấn trace nào và khi nào; nhóm kiểm toán cần xác định yêu cầu audit cho hoạt động đọc.
Một đội vận hành bật debug log cho distributor để điều tra lỗi ingest, log nội bộ chứa tenant ID và metadata request; nhóm bảo mật cần đánh giá nội dung chẩn đoán và thời hạn giữ.
Một tổ chức thay đổi bucket encryption key nhưng không kiểm tra compactor và querier đều có quyền giải mã, truy vấn trace lịch sử bắt đầu lỗi; nhóm hạ tầng cần kiểm tra phân phối key và quyền.
Một ứng dụng có spans chứa payload lớn, Tempo giới hạn attribute count nhưng đội phát triển chưa xác định trường nào quan trọng; nhóm SRE cần đánh giá cách giới hạn dữ liệu mà vẫn giữ thông tin điều tra.
Một công ty bật TraceQL search trên thuộc tính không được chuẩn hóa, mỗi service đặt tên trường khác nhau nên truy vấn khó dùng; nhóm observability cần thống nhất schema trước khi mở rộng tìm kiếm.
Một cụm Tempo có service graph nhưng không có tài liệu nguồn dữ liệu và sampling rate, nhóm sản phẩm dùng graph làm số liệu chính thức về throughput; đội SRE cần xác định giới hạn diễn giải và nguồn sự thật.
Một doanh nghiệp chạy diễn tập disaster recovery, Tempo khôi phục query nhưng trace ingestion mới vẫn gửi tới cluster cũ; nhóm vận hành cần kiểm tra cutover đồng bộ cả đường đọc và ghi.
Một hệ thống cần phục hồi Tempo trong thời gian ngắn, nhưng object storage restore và compactor rebuild kéo dài hơn RTO; nhóm kiến trúc cần đánh giá phương án phục hồi theo dung lượng thực.
Một tổ chức có nhiều tenant với yêu cầu retention khác nhau, báo cáo compliance chỉ lấy cấu hình mặc định của cluster và bỏ qua overrides; nhóm governance cần kiểm tra cấu hình hiệu lực từng tenant.
Một nhóm muốn chứng minh Tempo không làm mất trace, nhưng chỉ dựa vào số request HTTP 2xx của distributor mà không kiểm tra WAL, block flush và truy vấn; nhóm kiểm toán cần xác định chuỗi bằng chứng end-to-end.
Một nền tảng sử dụng Tempo để điều tra sự cố production, nhưng không có quy trình phân quyền tạm thời và thu hồi quyền sau incident; nhóm bảo mật cần xác định vòng đời quyền truy vấn.
