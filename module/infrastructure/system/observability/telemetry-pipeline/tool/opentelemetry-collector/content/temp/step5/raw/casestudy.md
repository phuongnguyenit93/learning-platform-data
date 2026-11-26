Một ứng dụng Java gửi traces qua OTLP gRPC tới cổng 4317 nhưng Collector chỉ mở OTLP HTTP trên cổng 4318; client liên tục báo connection refused dù pod Collector ở trạng thái Ready.
Ứng dụng gửi OTLP HTTP tới /v1/traces nhưng endpoint receiver chỉ được expose qua reverse proxy với path prefix khác; health check của Collector thành công còn trace request nhận 404.
Collector lắng nghe OTLP trên localhost bên trong container; pod khác kết nối tới Pod IP bị timeout dù lệnh kiểm tra ngay trong container Collector gọi được endpoint.
Một cụm ứng dụng gửi đồng thời logs, metrics và traces tới cùng OTLP receiver, nhưng cấu hình chỉ khai báo traces pipeline; logs và metrics không được xử lý dù receiver nhận kết nối.
OTLP receiver bật TLS với chứng chỉ do CA nội bộ cấp; một nhóm service chưa cập nhật trust bundle nên chỉ traces từ các pod cũ bị từ chối trong handshake.
Client OTLP yêu cầu mTLS nhưng Collector chỉ xác thực server certificate; kết nối từ workload không có chứng chỉ client vẫn được chấp nhận ngoài chính sách.
Một ứng dụng gửi OTLP với compression gzip nhưng Collector hoặc proxy trung gian không xử lý đúng header encoding; request bị từ chối trước khi dữ liệu vào pipeline.
Collector nhận OTLP qua HTTP/2 từ SDK nhưng load balancer phía trước chuyển kết nối thành HTTP/1.1 không tương thích; các request lớn thất bại còn request nhỏ đôi khi thành công.
Một gateway Collector có nhiều replicas nhưng OTLP receiver không được đặt sau service load balancing đúng cách; một số SDK giữ kết nối lâu tới replica đã quá tải trong khi replica khác gần như nhàn rỗi.
Ứng dụng ghi endpoint OTLP bằng DNS service name cũ sau khi Collector chuyển namespace; DNS trả NXDOMAIN ở một nhóm pod còn các ứng dụng khác đã dùng tên mới.
Collector agent trên node nhận OTLP từ ứng dụng qua localhost nhưng ứng dụng chạy hostNetwork; port trùng với tiến trình khác và chỉ các pod trên một số node gặp lỗi bind.
Một hệ thống gửi traces và metrics đến cùng cổng OTLP qua gateway; proxy ingress giới hạn body size thấp khiến batch traces lớn bị 413 còn metrics request nhỏ vẫn được nhận.
SDK gửi nhiều resource attributes nhưng Collector receiver nhận dữ liệu hợp lệ; exporter phía sau từ chối một số resource do giới hạn kích thước request, làm mất telemetry của những service có metadata dài.
Ứng dụng gửi OTLP với temporality cumulative cho counter nhưng một thành phần trung gian mong delta; dashboard downstream xuất hiện reset hoặc giá trị tăng không đúng sau khi đổi tuyến collector.
Một service sử dụng OTLP gRPC với deadline 2 giây, trong khi gateway đang xử lý batch lớn và cần lâu hơn; SDK retry làm số request tới Collector tăng thêm khi gateway đã gần bão hòa.
Collector nhận logs qua filelog receiver nhưng include pattern chỉ khớp đường dẫn cũ của container runtime; sau khi node chuyển sang containerd, log mới không được đọc dù agent vẫn hoạt động.
Filelog receiver theo dõi file container bị rotate; cấu hình fingerprint hoặc cơ chế nhận diện file không phù hợp khiến một số dòng đầu của file mới bị bỏ qua hoặc đọc lại.
Collector agent restart và mất checkpoint của filelog receiver do storage extension chưa được cấu hình bền vững; sau khởi động lại, log lịch sử bị gửi trùng hoặc một đoạn bị bỏ sót.
Filelog receiver đọc file application log có nhiều dòng stack trace nhưng multiline recombine rule không nhận diện prefix của framework mới; mỗi dòng thành một log record riêng.
Ứng dụng ghi JSON vào stdout và container runtime thêm CRI timestamp, stream và flag; parser filelog không tách đúng prefix nên JSON parse lỗi ở một phần record.
Filelog receiver đọc cả file active và file archive đã nén; parser chỉ xử lý văn bản thuần và log cũ trong archive bị lỗi hoặc tiêu tốn CPU khi retry.
Một ứng dụng ghi log với encoding UTF-16 nhưng filelog receiver giả định UTF-8; ký tự tiếng Việt bị hỏng và một số dòng không parse được JSON.
Collector agent chạy dưới quyền user không có quyền đọc /var/log/pods; DaemonSet Ready nhưng filelog receiver không thu thập log của các namespace ứng dụng.
Hostmetrics receiver chạy trong container nhưng chỉ nhìn filesystem namespace của container; dashboard báo dung lượng đĩa nhỏ và thiếu thông tin mount cùng CPU của host node.
Hostmetrics receiver không mount các đường dẫn host cần thiết sau khi chuyển sang image distroless; metric CPU và memory chỉ phản ánh container Collector thay vì máy chủ.
Hostmetrics receiver scrape quá nhiều filesystem mount ảo và thiết bị loop; số series tăng mạnh, trong khi đội vận hành chỉ cần phân tích các filesystem chứa dữ liệu ứng dụng.
Prometheus receiver scrape endpoint của ứng dụng qua ServiceMonitor nhưng Collector không có quyền truy cập Kubernetes endpoints; một số target mới không xuất hiện sau scale out.
Prometheus receiver scrape cùng target với Prometheus server đang chạy trong cluster; số request scrape và số lượng mẫu tăng gấp đôi, làm backend metrics nhận dữ liệu trùng.
Prometheus receiver dùng cấu hình relabeling chỉ giữ job=production nhưng target thực tế gắn job=prod; không có sample nào được đưa vào metrics pipeline dù target vẫn truy cập được.
Receiver syslog nhận dữ liệu UDP từ firewall nhưng receive buffer của node không đủ trong đợt burst; số packet bị drop tăng trước khi Collector tạo được log record.
Receiver Kafka đọc topic telemetry nhưng consumer group dùng lại tên group với một ứng dụng khác; partition assignment thay đổi và một phần message không còn được xử lý bởi Collector dự kiến.
Receiver Kafka bắt đầu lại từ offset mới nhất sau khi pod được thay thế; log tồn đọng trước thời điểm restart không được đọc dù topic vẫn còn retention.
Receiver OTLP và filelog cùng tạo log record nhưng schema khác nhau; pipeline downstream giả định mọi record có severity_text và body dạng chuỗi nên dữ liệu filelog bị xử lý sai.
Một Collector nhận traces qua Jaeger receiver và OTLP receiver trong giai đoạn migration; cùng một request được gửi theo cả hai giao thức, tạo trace trùng ở backend.
Nhóm dùng receiver tạo dữ liệu tổng hợp từ file audit nhưng file có thể được cập nhật đồng thời; Collector đọc file giữa lúc truncate và ghi mới, dẫn tới record thiếu phần cuối.
Collector có nhiều receivers trong một service instance nhưng chỉ một receiver cần credential riêng; cấu hình xác thực đặt ở sai tầng khiến tất cả nguồn gửi dùng chung quyền truy cập.
Nhóm triển khai memory_limiter processor sau batch processor; batch giữ nhiều record trong bộ nhớ trước khi limiter có thể từ chối dữ liệu và Collector bị OOM khi burst.
Memory_limiter được cấu hình ngưỡng gần bằng memory limit của container; runtime và exporter buffers không còn headroom, pod bị OOMKilled trước khi processor kịp giảm áp lực.
Collector có memory_limiter nhưng không có GOMEMLIMIT phù hợp với giới hạn container; Go runtime chỉ phản ứng sau khi RSS tăng cao và pod bị kill trong giờ cao điểm.
Memory_limiter từ chối telemetry khi bộ nhớ vượt ngưỡng nhưng đội vận hành không theo dõi refused records; dashboard cho thấy collector vẫn Ready trong khi số log đến backend giảm.
Batch processor gom dữ liệu theo timeout dài để tăng hiệu suất nén; ứng dụng cần cảnh báo gần thời gian thực nhưng log và alert telemetry chỉ xuất hiện sau vài chục giây.
Batch processor đặt send_batch_size quá lớn; backend OTLP nhận request vượt giới hạn payload và từ chối, trong khi Collector liên tục retry cùng batch.
Batch processor chia batch theo metadata của tenant làm số batch đang chờ tăng nhanh; mỗi tenant ít traffic tạo batch nhỏ và tốn overhead hơn dự kiến.
Batch processor đặt timeout ngắn và batch size nhỏ; số request export tăng mạnh, backend bị quá tải bởi nhiều request nhỏ dù tổng lượng telemetry không đổi.
Attributes processor dùng action upsert cho service.name dựa trên trường app_name; các SDK đã gửi service.name chính xác bị ghi đè và dashboard gộp workload sai.
Resource processor xóa cloud.region để giảm số chiều nhưng nhóm vận hành cần phân tích sự cố theo vùng; sau triển khai không còn khả năng xác định zone gây latency cao.
Resourcedetection processor được cấu hình phát hiện metadata cloud nhưng không có quyền truy cập metadata endpoint; resource attributes thiếu cloud provider và instance ID mà pipeline vẫn tiếp tục.
Kubernetes attributes processor không xác định được pod IP khi traffic đi qua NAT; log và spans không được gắn namespace, pod và deployment nên dashboard theo workload bị thiếu dữ liệu.
Kubernetes attributes processor có quyền get pods nhưng thiếu quyền watch namespaces; metadata cập nhật chậm sau khi workload đổi namespace hoặc được thay thế.
Collector gateway nhận telemetry từ nhiều cluster nhưng k8sattributes processor chạy ở gateway không còn thông tin pod IP nguồn; các record bị gắn nhầm metadata của cluster gateway.
Groupbyattrs processor được dùng để gom telemetry theo resource attributes nhưng có quá nhiều tổ hợp thuộc tính duy nhất; số nhóm tăng cao và làm memory usage của Collector tăng mạnh.
Transform processor đổi tên trường http.status_code nhưng các downstream exporter và backend vẫn tham chiếu tên cũ; dashboard lỗi sau khi rollout cấu hình mới.
OTTL transform expression giả định attributes['http.route'] luôn tồn tại; một số span từ gRPC không có trường này và processor ghi evaluation error trong giờ cao điểm.
Filter processor loại mọi span có status code bằng 200; các request chậm nhưng thành công biến mất khỏi traces và nhóm không thể điều tra p99 latency.
Filter processor được đặt trong traces pipeline nhưng nhóm kỳ vọng nó cũng loại log records có cùng trường; logs pipeline độc lập tiếp tục export dữ liệu nhạy cảm.
Attributes processor xóa http.request.header.authorization ở span attributes nhưng log body vẫn chứa cùng token; dữ liệu nhạy cảm đi qua logs pipeline không được bảo vệ.
Redaction processor chỉ mask email ở top-level attributes; một số SDK gửi email trong nested map và span events nên thông tin vẫn được export.
Transform processor thay giá trị user.id bằng hash ổn định để giả danh; nhóm quên xử lý cùng định danh trong baggage và log body nên có thể liên kết lại dữ liệu từ các signal.
Tail sampling processor giữ trace có lỗi nhưng decision_wait quá ngắn; child spans tới muộn sau quyết định bị loại và trace được lưu không đầy đủ.
Tail sampling processor chạy trên nhiều Collector replicas nhưng các span của cùng trace không được route tới cùng replica; mỗi replica đưa ra sampling decision dựa trên phần trace riêng.
Load balancing exporter chọn gateway theo endpoint hash không dựa trên trace ID; các spans của cùng trace được gửi tới nhiều tail-sampling collectors và trace bị chia tách.
Tail sampling giữ tất cả trace có status ERROR nhưng một service trả lỗi nghiệp vụ trong HTTP 200; các trace cần giữ không thỏa điều kiện status và bị loại.
Tail sampling giữ trace chậm dựa vào latency, nhưng clock skew giữa các spans khiến duration tính sai; một số trace vượt ngưỡng giả và một số trace thực sự chậm bị bỏ.
Tail sampling có nhiều policy chồng lấn; một policy giữ trace theo service còn policy khác loại trace theo attribute, kết quả cuối không như nhóm thiết kế ban đầu.
Probabilistic sampling được áp dụng ở SDK rồi Collector tiếp tục tail sampling; tỷ lệ trace giữ lại thấp hơn dự kiến và trace lỗi hiếm thường không đến được nơi có thể quyết định giữ.
Collector nhận trace đã được head-sampled từ SDK; đội bật tail sampling ở gateway nhưng không nhận ra các spans đã bị bỏ trước khi tới gateway nên trace không thể phục hồi đầy đủ.
Group-by-trace processor cần giữ trạng thái trong bộ nhớ; khi traffic tăng và trace kéo dài, số trace đang mở vượt giới hạn và Collector bị memory pressure.
Group-by-trace timeout quá thấp so với thời gian xử lý bất đồng bộ; spans consumer tới sau khi trace đã được phát ra và không được ghép vào trace hoàn chỉnh.
Routing connector định tuyến logs theo resource attribute tenant nhưng một số SDK đặt tenant_id ở record attributes; các record đi vào nhánh mặc định và được lưu sai vùng dữ liệu.
Routing connector có bảng route không có nhánh mặc định; một service mới gửi giá trị environment chưa khai báo và telemetry không có pipeline đích.
Spanmetrics connector tạo metrics từ traces nhưng số route và status labels không được chuẩn hóa; cardinality tăng mạnh khi URL có ID động.
Servicegraph connector cần span client và server tương ứng; một gateway lọc span client trước connector nên đồ thị phụ thuộc hiển thị nhiều cạnh một chiều hoặc thiếu service.
Connector tạo metrics từ traces được đặt sau một processor chỉ giữ sampled spans; số request và error rate ở metrics thấp hơn traffic thật vì connector chỉ thấy trace được lấy mẫu.
Collector pipeline logs, metrics và traces dùng chung một exporter nhưng endpoint backend chỉ nhận OTLP traces; logs và metrics liên tục bị từ chối do sai loại signal.
Exporter OTLP được cấu hình endpoint gRPC nhưng dùng port HTTP của backend; TLS có thể kết nối nhưng export request không đúng giao thức và nhận lỗi.
OTLP exporter dùng TLS với CA nội bộ nhưng Collector image không chứa CA bundle mới; exporter báo x509 unknown authority sau khi chứng chỉ backend được thay.
OTLP HTTP exporter gửi traces qua proxy yêu cầu authentication; cấu hình headers authenticator chỉ được gắn cho một pipeline nên logs pipeline nhận 401.
Exporter Prometheus mở endpoint metrics nhưng bind localhost trong pod; Prometheus server ở namespace khác không thể scrape dù curl nội bộ Collector thành công.
Prometheus exporter chuyển metrics OTLP sang Prometheus exposition; hai nguồn cùng phát metric name nhưng khác unit và type, gây xung đột hoặc series không nhất quán.
Prometheus remote write exporter nhận histogram native từ pipeline nhưng backend đích chưa bật hỗ trợ tương ứng; các sample histogram bị từ chối trong khi counter vẫn ghi được.
Kafka exporter gửi logs với partition key là service.name; một service có lưu lượng lớn chiếm một partition và consumer lag tăng trong khi các partition khác nhàn rỗi.
Kafka exporter ghi message thành công nhưng consumer downstream xử lý chậm; Collector queue không tăng nên dashboard Collector xanh trong khi độ trễ end-to-end tiếp tục tăng.
File exporter ghi telemetry vào volume ephemeral của pod; khi pod bị reschedule, dữ liệu xuất ra chưa được đồng bộ và mất cùng filesystem cũ.
Debug exporter được bật ở mức verbose trong production để điều tra một trace; nội dung span attributes chứa token và dữ liệu người dùng xuất hiện trong stdout của Collector.
Exporter load balancing dùng DNS resolver cache cũ sau khi gateway scale; một số request vẫn được gửi tới địa chỉ gateway đã bị xóa và queue retry tăng.
Exporter OTLP có sending_queue tắt; khi backend ngừng hoạt động ngắn hạn, request export thất bại ngay và không có lớp đệm để chờ backend phục hồi.
Sending queue của exporter được bật nhưng queue size quá nhỏ; backend bảo trì vài phút làm queue đầy và các record mới bị từ chối.
Sending queue lưu dữ liệu trong memory và Collector bị OOMKilled; các telemetry đã được nhận nhưng chưa export mất theo process.
File storage extension được cấu hình cho queue bền vững nhưng thư mục chưa mount PersistentVolume; pod restart làm queue trở về trạng thái rỗng.
Exporter retry_on_failure có thời gian retry giới hạn; backend gián đoạn lâu hơn giới hạn khiến queue bị giải phóng và telemetry chưa gửi bị mất.
Retry policy không phân biệt lỗi tạm thời với lỗi cấu hình 400; Collector retry vô hạn những request không thể thành công và queue bị chiếm bởi dữ liệu lỗi.
Backend trả 429 khi ingest vượt quota; Collector retry với backoff ngắn và nhiều replicas đồng thời retry, tạo thêm đợt tải làm backend tiếp tục từ chối.
Exporter gửi một batch tới backend, backend ghi thành công nhưng kết nối bị reset trước ACK; Collector retry và dữ liệu downstream xuất hiện duplicate.
Collector có queue lớn nhưng consumer export chậm hơn tốc độ nhận liên tục; queue không đầy trong một đợt ngắn nhưng tăng đều qua nhiều giờ và cuối cùng chạm giới hạn.
Batch processor và exporter queue cùng giữ bản sao dữ liệu lớn; khi tăng batch size, memory usage tăng nhiều hơn dự kiến dù số record đầu vào không đổi.
Collector có nhiều exporters cho nội bộ và SaaS; một exporter ngoài bị chậm nhưng pipeline fan-out chờ cả hai nhánh, khiến telemetry nội bộ cũng trễ theo.
Nhóm tách pipeline logs và traces nhưng dùng chung exporter queue; backlog logs chiếm toàn bộ queue và traces cảnh báo lỗi không được gửi kịp thời.
Collector exporter trả lỗi cho một signal nhưng service health endpoint chỉ báo process đang sống; nhóm trực không nhận ra traces pipeline đã ngừng export.
Collector tự giám sát metrics nhưng Prometheus scrape endpoint của Collector bị cấu hình filter loại bỏ; đội vận hành mất các số đo queue size và refused spans ngay khi cần điều tra.
Metric otelcol_exporter_send_failed_spans tăng nhưng dashboard chỉ hiển thị CPU và memory; sự cố export kéo dài mà không có cảnh báo dựa trên số span thất bại.
Collector scrape metrics self-observability qua endpoint riêng nhưng endpoint bind sai địa chỉ; dashboard cho thấy không có collector metrics và nhóm nhầm với việc Collector không phát sinh hoạt động.
Collector process còn sống nhưng receiver accepted logs không tăng dù ứng dụng đang phát log; input plugin bị lỗi cấu hình và health check chỉ kiểm tra PID.
Nhóm theo dõi exporter queue size nhưng không theo dõi queue capacity hoặc oldest item age; queue mới tăng 20% đã gần hết thời gian SLA nhưng dashboard vẫn xanh.
Một Collector gateway nhận traffic từ 200 agent; CPU còn thấp nhưng network egress bị giới hạn và exporter send latency tăng, làm backlog tập trung tại gateway.
Collector agent có CPU thấp nhưng filelog receiver không đọc thêm file vì permission denied; dashboard chỉ theo dõi resource usage và không phát hiện input throughput bằng không.
Memory limiter refused data tăng trong một khoảng ngắn nhưng không có log hoặc metric phân biệt signal nào bị từ chối; nhóm không xác định được logs, metrics hay traces bị ảnh hưởng.
Collector bật health_check extension và liveness probe chỉ kiểm tra endpoint HTTP; pipeline exporter đã bị kẹt nhưng endpoint vẫn trả 200 nên Kubernetes không restart pod.
Readiness probe đánh giá Collector chưa sẵn sàng khi một exporter phụ bị lỗi; toàn bộ agent ngừng gửi tới gateway dù pipeline chính vẫn có thể xử lý telemetry nội bộ.
Collector gateway chạy nhiều replicas nhưng không có load balancing exporter; các trace spans cùng trace ID có thể vào nhiều gateway và tail sampling đưa ra quyết định không đồng nhất.
Kiến trúc agent-gateway gửi OTLP từ agent tới gateway; agent bật sampling và filter trước khi gửi, khiến gateway không thể giữ lại trace lỗi đã bị loại ở tầng node.
Agent Collector chạy trên mỗi node nhưng cấu hình hostmetrics chỉ mount namespace của container; dữ liệu CPU, memory và filesystem host bị thiếu ở mọi node.
Gateway Collector nhận telemetry từ nhiều cluster nhưng không gắn cluster identity; dashboard tổng hợp trộn resource cùng service.name và không xác định được nguồn khi một cluster lỗi.
Nhóm scale gateway bằng HPA dựa trên CPU nhưng bottleneck là exporter queue và network egress; replica tăng mà queue vẫn không giảm do backend đích đang throttling.
Load balancer phân phối OTLP gRPC theo connection, còn SDK giữ HTTP/2 connection lâu; một gateway nhận hầu hết spans từ client có traffic lớn và các gateway khác nhàn rỗi.
Collector gateway được triển khai sau Kubernetes Service nhưng session affinity theo client IP; các agent cùng NAT tập trung vào một replica và gây lệch tải.
Collector agent và gateway cùng áp batch processor với timeout dài; độ trễ tổng cộng tăng vì mỗi tầng chờ đủ batch trước khi export.
Agent gửi dữ liệu theo resource attributes nhưng gateway thêm resource attributes khác bằng upsert; service.name của workload bị ghi đè thành tên gateway và truy vấn theo service sai.
Gateway resourcedetection processor chạy trong pod Kubernetes và nhận metadata của node gateway thay vì workload nguồn; mọi telemetry được gắn cloud instance ID giống nhau.
Collector gateway nhận spans từ nhiều tenant nhưng authentication extension chỉ xác thực token mà không gắn danh tính tenant vào resource; dữ liệu có thể bị trộn trong cùng backend.
Receiver OTLP dùng authentication extension nhưng một số pipeline phụ không gắn authenticator; workload có thể gửi dữ liệu vào endpoint phụ không có xác thực.
Collector sử dụng OAuth2 client credentials để export tới backend; token hết hạn và token refresh endpoint không truy cập được do egress policy, khiến exporter retry liên tục.
Secret TLS được mount từ Kubernetes Secret nhưng Collector không reload certificate khi Secret được rotate; kết nối export tiếp tục dùng chứng chỉ cũ cho tới lần restart.
Collector chạy trên nhiều node với đồng hồ lệch nhau; resource timestamps và span timestamps không đồng nhất, làm duration và thứ tự trace khó phân tích.
OTLP receiver chấp nhận telemetry có resource attributes chứa dữ liệu không đáng tin cậy; một client gửi service.name giả và làm dashboard gộp dữ liệu của workload khác.
Collector dùng transform processor xóa http.request.header.authorization khỏi spans nhưng không xử lý log body và span events; credential vẫn có thể bị export qua signal khác.
Filter processor được đặt ở traces pipeline nhưng logs pipeline có cùng payload nhạy cảm; nhóm bảo mật kiểm tra trace backend và kết luận an toàn trong khi log exporter vẫn nhận dữ liệu thô.
Nhóm dùng OTTL để mask email trong log attributes nhưng SDK mới chuyển email vào body dạng map; điều kiện cũ không xử lý trường mới sau nâng cấp semantic conventions.
Tail sampling giữ toàn bộ trace lỗi nhưng error event chứa dữ liệu thanh toán; dữ liệu nhạy cảm được giữ lâu hơn và gửi tới backend bên ngoài do policy retention chưa tách theo classification.
Collector nhận PII ở receiver trước khi áp redaction processor; debug exporter hoặc telemetry internal log ghi raw record trong quá trình lỗi parser.
Nhóm muốn loại span health check để giảm chi phí; health check bị loại trước spanmetrics connector nên metrics availability và request count của endpoint không còn khớp với load balancer.
Collector lọc span có status OK nhưng span thành công có duration dài vượt SLO; hệ thống chỉ còn trace lỗi và không thể điều tra latency tail.
Transform processor đổi tên attribute theo quy ước mới nhưng sampling policy chạy trước transform; tail sampling không thấy trường service tier cần thiết và đưa trace vào policy mặc định.
Memory limiter đặt sau groupbytrace processor; state của trace chưa hoàn chỉnh tích tụ trước khi limiter hoạt động và Collector vượt giới hạn bộ nhớ.
Batch processor đặt trước tail sampling; spans của cùng trace nằm trong các batch khác nhau và quyết định lấy mẫu ở gateway không còn đầy đủ context khi trace kéo dài.
Collector config khai báo processor nhưng không gắn vào traces pipeline; cấu hình tải thành công nhưng dữ liệu không đi qua bước redaction như nhóm triển khai kỳ vọng.
Một processor được khai báo trong pipeline metrics nhưng cấu hình chỉ hỗ trợ logs; Collector không khởi động sau khi deploy config mới vì component không tương thích signal.
Collector config tham chiếu exporter tên otlp nhưng chỉ khai báo exporter otlphttp; pipeline không khởi động dù cả hai component đều có trong image.
Nhóm chuyển từ Collector core sang contrib distribution nhưng image mới thiếu filelog receiver; cấu hình hợp lệ với image cũ không còn chạy khi pod khởi động.
Một Collector custom distribution được build để thêm exporter nội bộ nhưng thiếu extension health_check; liveness probe gọi endpoint không tồn tại và pod bị restart liên tục.
ConfigMap chứa cấu hình Collector có lỗi indent YAML; rollout khiến tất cả pod gateway crash và agent tiếp tục retry vào endpoint không có backend.
Nhóm cập nhật cấu hình qua GitOps nhưng một số Collector replica chưa reconcile; telemetry cùng service được xử lý bởi hai pipeline khác nhau trong giai đoạn chuyển tiếp.
Collector config được reload nhưng không có kiểm tra config validate trong CI; một lỗi tên processor chỉ phát hiện khi production pod restart.
Đội bật zpages và pprof để chẩn đoán Collector nhưng endpoint debug mở trên interface công khai; thông tin pipeline và profiling có thể bị truy cập ngoài phạm vi vận hành.
Collector internal telemetry được export về chính Collector qua OTLP receiver; pipeline tạo vòng lặp telemetry và số log/metric internal tăng liên tục.
Exporter debug gửi dữ liệu trở lại cùng OTLP endpoint mà Collector đang nhận; một cấu hình test bị giữ trong production và tạo vòng lặp export.
Collector nhận telemetry từ một service có hàng triệu resource attributes khác nhau; memory và series count tăng dù request volume ổn định.
Nhóm bật spanmetrics connector trên trace có URL path chứa order ID; metric labels tạo cardinality gần bằng số giao dịch và backend Prometheus tăng dung lượng nhanh.
Servicegraph connector xử lý nhiều cặp service và dimension tùy chỉnh; số edge và series tăng mạnh khi thêm tenant_id làm dimension.
Collector tail sampling dùng decision cache quá nhỏ so với số trace đồng thời; decision cho trace cũ bị mất và span đến muộn được xử lý như trace mới.
Một trace có hàng nghìn spans do instrumentation lặp ở client và server; Collector giữ toàn bộ spans trong tail sampling window và bị memory pressure trong giờ cao điểm.
SDK gửi spans với trace ID không hợp lệ từ một thư viện legacy; Collector nhận record nhưng exporter từ chối hoặc backend không thể hiển thị trace, trong khi số received spans vẫn tăng.
Collector nhận metrics delta nhưng exporter backend chỉ hỗ trợ cumulative; sau restart gateway, giá trị counter bắt đầu lại và dashboard hiển thị spike hoặc reset không đúng.
Collector chuyển histogram exponential sang backend chỉ hỗ trợ classic histogram; bucket bị chuyển đổi không tương đương và p99 trên Grafana thay đổi sau khi migration.
Metrics pipeline dùng cumulative-to-delta processor nhưng state không được lưu bền vững qua restart; sau khi pod thay thế, delta đầu tiên không phản ánh đúng lượng tăng.
Nhóm dùng attributes processor thêm tenant label vào mọi datapoint; số chuỗi thời gian tăng theo tenant và exporter Prometheus bắt đầu chậm.
Collector chuyển metric name theo quy ước mới nhưng recording rules vẫn truy vấn tên cũ; metrics vẫn được ingest nhưng dashboard và alerts hiển thị No data.
Exporter Prometheus trong Collector scrape được nhưng không có target labels cluster và region; dữ liệu từ nhiều gateway bị gộp và không thể khoanh vùng.
Collector dùng prometheusremotewrite exporter nhưng remote endpoint yêu cầu tenant header; cấu hình header không được gắn cho một pipeline và chỉ metrics của pipeline đó bị 401.
Remote write queue tích tụ khi backend metrics chậm; Collector tiếp tục nhận OTLP và memory limiter bắt đầu từ chối dữ liệu dù backend cuối cùng vẫn đang hoạt động.
Logs pipeline dùng batch processor nhưng exporter file ghi theo từng record; cấu hình batch không cải thiện throughput và làm tăng thời gian chờ log trước khi xuất.
Một Collector có logs và traces pipeline cùng ghi tới Kafka nhưng topic và partition key không tách; lưu lượng log lớn chiếm partition và consumer xử lý trace bị chậm.
Exporter OTLP trả lỗi partial success với rejected data points; nhóm chỉ theo dõi HTTP status 200 nên không phát hiện backend đã từ chối một phần telemetry.
Collector nhận OTLP request lớn và backend trả partial success; SDK không nhận được số record bị reject vì Collector chỉ log tổng số export failure mà không ghi signal cụ thể.
Nhóm cấu hình queue và retry giống nhau cho audit logs và debug traces; khi backend chậm, telemetry ít quan trọng chiếm queue khiến audit events bị trễ hoặc drop.
Collector có hai exporters, một backend nội bộ và một SaaS; exporter SaaS bị rate limit và retry lâu, làm shared pipeline queue ảnh hưởng đến dữ liệu nội bộ.
Gateway nhận log với timestamp gốc nhưng transform processor ghi đè bằng observed timestamp; sau outage, dữ liệu backlog xuất hiện như mới và không còn đo được event age.
Nhóm kiểm tra Collector bằng số records accepted nhưng không so với exported, refused và dropped; pipeline báo nhận đủ dữ liệu trong khi backend thiếu hàng triệu spans.
Collector exporter retry làm tăng số bản ghi ở backend sau timeout; nhóm so accepted với stored mà không tính at-least-once delivery và không có event ID để deduplicate.
Đội muốn xác minh cấu hình mới giảm 30% chi phí telemetry; họ chỉ đo số byte export nhưng không so mức độ đầy đủ của trace, tỷ lệ lỗi bị giữ và khả năng điều tra sau một bài diễn tập.
Trong một đợt mất mạng tới backend, Collector gateway queue tăng và pod được autoscale; khi mạng phục hồi, tất cả replica xả backlog cùng lúc làm backend quá tải lần hai.
Collector agent bị mất kết nối gateway trong 45 phút; file storage extension chưa được cấu hình và agent chỉ có memory queue, nên telemetry trong thời gian outage biến mất khi pod restart.
Một cụm Collector chạy active-active nhưng hai replica không chia sẻ state của tail sampling; cùng trace được gửi qua hai đường và backend nhận quyết định sampling không nhất quán.
Đội nâng cấp Collector version và một số component contrib đổi cấu hình; file config vẫn parse được nhưng component không còn hỗ trợ option cũ và pipeline không chạy như trước.
Một Collector dùng health_check extension nhưng readiness chỉ xác nhận process và receiver; exporter queue đã đầy và mọi dữ liệu mới bị từ chối mà pod vẫn Ready.
Đội trực theo dõi CPU Collector và không thấy tăng, nhưng metric exporter_enqueue_failed tăng nhanh; network backend bị chặn và telemetry đang mất dù resource usage thấp.
Collector memory usage ổn định nhưng file descriptor tăng dần do exporter không đóng kết nối; sau vài giờ process không mở được socket mới và pipeline dừng export.
Một gateway nhận nhiều client gRPC HTTP/2 giữ kết nối lâu; giới hạn connection và stream không phù hợp làm một số client mới không thiết lập được phiên dù CPU còn dư.
Collector chạy trên node có disk pressure; file storage extension không ghi được checkpoint và queue persistent, nhưng pipeline tiếp tục nhận record cho tới khi mất dữ liệu.
Nhóm triển khai Collector bằng DaemonSet nhưng không cấu hình tolerations cho node có workload nhạy cảm; log của các pod trên node đó không được thu thập.
Agent Collector gắn metadata pod bằng IP nhưng pod network dùng hostPort và NAT; k8sattributes processor liên kết nhầm record với workload khác có cùng địa chỉ sau tái sử dụng.
Một gateway nhận OTLP từ cluster staging và production nhưng route dựa trên resource.environment do client tự gửi; client production có thể khai báo staging và dữ liệu đi nhầm backend.
Collector xử lý telemetry của nhiều tenant nhưng không áp quota theo tenant; một tenant gửi burst lớn chiếm memory và exporter queue của gateway chung.
Trong quá trình drain node, Collector DaemonSet bị terminate trước khi flush queue; terminationGracePeriodSeconds ngắn hơn thời gian drain và telemetry cuối cùng không được gửi.
Đội triển khai config mới có filter bỏ span thành công nhưng không chạy regression test cho trace hoàn chỉnh; sau phát hành, lỗi latency chỉ có ở response 200 không còn đủ dữ liệu điều tra.
Nhóm bật verbose logging của Collector trong incident và gửi log nội bộ sang cùng pipeline; các thông báo exporter retry tạo thêm lượng log lớn và làm tăng áp lực lên chính Collector.
