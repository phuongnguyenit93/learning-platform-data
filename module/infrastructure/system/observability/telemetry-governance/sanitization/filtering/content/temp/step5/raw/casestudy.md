Một dịch vụ đặt hàng ghi log INFO cho mọi lần đọc cache với 30.000 request mỗi phút; sau khi tăng số replica, chi phí ingest logs tăng gấp bốn trong khi đội vận hành chỉ cần giữ những lỗi cache và sự kiện cập nhật trạng thái.
API thanh toán ghi log DEBUG chứa toàn bộ payload request ở môi trường production; nhân viên hỗ trợ có thể nhìn thấy địa chỉ khách hàng khi tra lỗi và bộ lọc hiện chỉ loại log theo severity.
Một thư viện HTTP tạo log INFO 'connection acquired' cho từng lượt gọi; nhóm cấu hình lọc theo chuỗi connection nhưng cùng mẫu chữ xuất hiện trong log cảnh báo 'connection pool exhausted' cần giữ để điều tra.
Ứng dụng Java gửi log health check mỗi năm giây; đội muốn giảm dữ liệu nhưng route /health cũng là mục tiêu tấn công dò quét, khiến việc bỏ mọi request theo đường dẫn làm mất một số tín hiệu bảo mật.
Access log gateway chứa hàng triệu HTTP 200 của endpoint /ready nhưng thỉnh thoảng có HTTP 503; quy tắc lọc dựa riêng vào đường dẫn khiến các phản hồi lỗi của endpoint này cũng không còn trong hệ giám sát.
Một nhóm lọc mọi log có severity INFO trở xuống để tiết kiệm chi phí; log nghiệp vụ xác nhận hoàn tiền đang được ghi INFO và báo cáo điều tra tranh chấp không thể tìm lại sự kiện này.
OpenTelemetry Collector nhận log chứa tên người dùng trong trường body dạng chuỗi tự do; điều kiện lọc chỉ kiểm tra attribute user.name nên bản ghi còn body nhạy cảm vẫn được xuất tới vendor.
Dịch vụ quản lý tài khoản đưa bearer token vào exception.message khi request lỗi; pipeline loại các log mang thuộc tính http.request.header.authorization nhưng không nhận ra token trong thông điệp lỗi.
Một bộ lọc loại log có nhãn data.classification=restricted nhưng hệ thống legacy không gắn nhãn; những log chứa thông tin hồ sơ vẫn được xuất vì thuộc tính phân loại không tồn tại.
Ứng dụng Java ghi nhiều dòng stack trace cho một lỗi; collector nhận từng dòng thành các log record rời và chỉ dòng đầu có severity ERROR, khiến các dòng còn lại bị xử lý theo chính sách lọc khác.
Trong một cụm Kubernetes, log ứng dụng được gắn resource attribute service.name từ SDK, còn log container nhận qua filelog receiver chỉ có k8s.container.name; điều kiện OTTL dựa vào service.name loại không đều những bản ghi dự định bỏ.
Một nhóm muốn bỏ log audit của môi trường thử nghiệm khỏi kho vận hành, nhưng dấu môi trường xuất hiện trong resource attributes ở một số nguồn và trong log attributes ở nguồn khác.
Nhà cung cấp xuất logs có severity_number bằng 0 nhưng severity_text='ERROR'; bộ lọc chỉ nhìn giá trị số nên một nhóm lỗi nghiêm trọng không được xử lý như quy định.
Một ứng dụng đưa trạng thái thanh toán trong JSON body, trong khi collector chỉ kiểm tra status_code ở attributes; khi đối tác trả lỗi nghiệp vụ trong HTTP 200, log vẫn bị loại như một request thành công.
Đội dùng biểu thức so khớp regex để loại log lặp lại có tiền tố 'Heartbeat'; một bản cập nhật SDK thêm mã timestamp ở đầu thông điệp khiến số log thu thập tăng mạnh mà quy tắc vẫn được báo tải thành công.
Một quy tắc lọc log dựa trên service.name='checkout' nhưng service tại một vùng khai báo tên là 'checkout-api'; dashboard chỉ còn log của vùng chưa đổi tên sau canary.
Ứng dụng ghi log kiểm toán bằng event.name='user.permission.changed'; biểu thức lọc bỏ các event có tiền tố user.* trong môi trường production và kho kiểm toán mất bằng chứng về những lần thay quyền.
Nhân viên trực tìm sự cố đăng nhập bằng log 401 nhưng gateway trả 429 khi rate limit; bộ lọc đã loại mọi access log không có HTTP 5xx nên nhóm không nhìn thấy đợt khóa truy cập hợp lệ.
Collector nhận log từ database gồm truy vấn chậm và thông báo checkpoint; nhóm lọc theo tên logger 'database' thay vì loại sự kiện có tần suất cao, khiến cả log deadlock cũng biến mất.
Nhóm bảo mật yêu cầu mọi log chứa session cookie không được xuất ra SaaS, nhưng bộ lọc hiện chỉ bỏ toàn bộ log có key cookie; những dòng đã được mask an toàn cũng bị mất khi điều tra lỗi đăng nhập.
API hỗ trợ lưu trữ gửi log có mã hợp đồng trong URL query; sau khi loại hoàn toàn các bản ghi chứa ký tự '?', đội vận hành không còn log của những endpoint có tham số phân trang bình thường.
Một log báo timeout Redis được gắn severity WARN và trace_id; bộ lọc bỏ phần lớn WARN để giảm chi phí nhưng điều tra latency cần liên kết WARN đó với span chậm của giao dịch.
Trong luồng xử lý bất đồng bộ, message producer ghi log 'publish accepted' còn consumer ghi log 'processing failed'; quy tắc bỏ log thành công dựa vào event.name giống nhau ở cả hai phía nên mất dấu nguồn sự kiện.
Một exporter log ghi message chứa chuỗi số thẻ bị tách bởi dấu gạch ngang; chính sách nhận diện dữ liệu nhạy cảm hiện chỉ tìm dãy số liền nhau và các bản ghi đó tiếp tục sang backend.
Trong sự cố, nhóm bật debug logging của OpenTelemetry Collector để xem record bị loại; debug exporter nằm trước bước bảo vệ và bắt đầu in ra giá trị header Authorization từ traffic thực.
Nhà cung cấp gửi một phần security log với severity='NOTICE' còn ứng dụng dùng 'WARN'; quy tắc lọc theo mức nghiêm trọng không thống nhất làm báo cáo số sự kiện đáng ngờ giữa hai nguồn lệch nhau.
Một service xuất Counter cho mọi user_id và method; bộ lọc metrics chỉ loại metric tên login_attempts nhưng các metrics khác vẫn có nhãn định danh cá nhân trong sample.
Prometheus bắt đầu lưu hàng triệu series sau khi HTTP client exporter thêm label request_url chứa ID đơn; nhóm cấu hình lọc theo tên http.client.requests và mất luôn số liệu tổng cần cho SLO.
Ứng dụng có histogram latency với hàng chục bucket và nhiều chiều; đội chỉ muốn giữ số liệu phục vụ SLO nhưng bộ lọc loại toàn bộ metric khiến biểu đồ p99 trong Grafana trả No data.
Một chỉ số cache hit được gửi dưới dạng metric với attributes tenant_id và cache_result; chính sách không cho lưu danh tính tenant nhưng bước filter chọn bỏ tất cả datapoint chứa tenant_id khiến tỷ lệ hit toàn hệ thống thiếu phần lớn traffic.
Collector lọc datapoint của hai vùng địa lý chỉ giữ production; một số nguồn gửi region ở resource attributes và nguồn khác đặt region vào datapoint attributes, khiến kết quả tổng hợp thiếu các node hợp lệ.
Một rule bỏ datapoint có status='success' để giảm chi phí; dashboard error rate sử dụng tổng request và số request lỗi, nên sau triển khai mẫu số nhỏ hơn thực tế và tỷ lệ lỗi bị phóng đại.
Nhóm xóa các metric không có dữ liệu mới bằng điều kiện theo timestamp, nhưng exporter gửi cumulative Counter với thời gian start cố định; nhiều chuỗi còn hoạt động bị đánh giá như đã cũ.
Pod Java có một metric heap_used_bytes được dùng cho cảnh báo OOM và một metric debug về GC; rule chỉ so tên chứa java để giảm lưu lượng khiến cả cảnh báo bộ nhớ biến mất.
Một ứng dụng xuất metric business_order_total từ resource service.name='billing', trong khi filter chỉ dành cho service.name='checkout'; sau đổi tên service, metric cần giữ bị loại mà không có thay đổi ở code đo lường.
Đội thống kê doanh thu theo nhãn currency nhưng một số exporter ghi currency ở resource level và số còn lại ở datapoint; biểu thức lọc theo nhãn datapoint làm bỏ sót cả một nhóm tiền tệ.
Nhóm muốn loại metric phát sinh từ sandbox trong khi Prometheus còn cần up của các exporter sandbox để biết trạng thái kết nối; sau cấu hình lọc, target vẫn UP nhưng dashboard giám sát khả năng scrape không đầy đủ.
Service có Counter request với nhãn outcome=SUCCESS và outcome=ERROR; biểu thức lọc dùng một điều kiện phủ định quá rộng khiến sample lỗi cũng bị loại, tỷ lệ thành công hiển thị 100%.
Một nhóm cấu hình lọc những histogram datapoint không thuộc bộ phận thanh toán; sau đợt thay đổi tên resource service.namespace, tất cả bucket latency của dịch vụ thanh toán bị bỏ, còn các Counter liên quan vẫn giữ.
Exporter từ node Linux xuất hàng trăm metric filesystem cho mount ảo; nhóm lọc theo thiết bị /dev nhưng một số volume thật cũng có đường dẫn không khớp mẫu nên biểu đồ dung lượng đĩa bị thiếu.
Đội bỏ toàn bộ metric có label pod trống để giảm nhiễu; các metric từ node_exporter vốn không có nhãn pod bị loại khỏi kho dữ liệu mặc dù phục vụ cảnh báo hạ tầng.
Một custom metric dùng value=0 để biểu diễn số cuộc gọi thất bại của một tenant; nhóm nhầm giá trị bằng 0 với dữ liệu không cần thiết nên ngừng quan sát những tenant vừa phục hồi.
Nhóm muốn bỏ metric chỉ có trên mỗi request và giữ aggregation theo endpoint; filter processor được dùng thay cho cơ chế tổng hợp, dẫn tới mất toàn bộ những datapoint cần làm mẫu cho tổng.
Một exporter có metric name phát sinh theo tên phiên bản ứng dụng; quy tắc chỉ giữ whitelist tên cố định, nên khi deploy một phiên bản mới, nhóm không có metric của tính năng vừa phát hành.
Hệ thống đa tenant triển khai bộ lọc metrics dựa vào tenant ID dạng số; một tenant mới dùng UUID nên biểu thức chuyển kiểu thất bại và kết quả tùy thuộc chính sách xử lý lỗi OTTL.
Một datapoint mang label customer_email đã được mã hóa base64 bởi SDK cũ; filter chỉ tìm ký tự @ trong giá trị nhãn nên vẫn xuất định danh được mã hóa sang hệ thống ngoài.
Collector chỉ giữ histogram bucket cho các endpoint chậm nhưng loại các datapoint sum/count liên quan; dashboard không còn tính được giá trị trung bình và tổng số request như trước.
Đội sử dụng metric filtering để giảm cardinality từ nhãn session_id; số series không giảm đáng kể vì một exporter khác dùng token_id dưới nhãn khác cho cùng loại thông tin.
Một trace đặt hàng đi qua gateway, inventory, payment và delivery; filter loại toàn bộ span thành công của inventory nhưng giữ span payment lỗi, khiến đường đi hiển thị thiếu một bước quan trọng ngay trước khi lỗi.
Một gateway tạo span server cho HTTP request và span client cho upstream; quy tắc bỏ mọi span status=OK khiến trace chỉ còn một vài span lỗi, không thể xác định phần thời gian đã tiêu tốn trước khi lỗi xảy ra.
Đội muốn giảm lưu lượng tracing bằng cách bỏ span của endpoint /health, nhưng lệnh health check gây nghẽn connection pool; khi xảy ra timeout, traces không còn dữ kiện của nguồn tạo tải.
Một collector chỉ nhận span tại dịch vụ backend và lọc theo thuộc tính http.route; span client không có thuộc tính này nên các request định loại bị xử lý không nhất quán.
Trace tìm kiếm sản phẩm có span client gửi tới Elasticsearch và span server tại API; quy tắc loại các span chứa 'search' trong tên làm mất cả span nghiệp vụ cần giữ để phân tích truy vấn chậm.
Một luồng async có span producer gửi Kafka và span consumer xử lý message; policy lọc toàn bộ span messaging thành công khiến các trace còn lại không xác định được thời gian nằm trong hàng đợi.
Trace từ hệ thống thanh toán có attribute card.bin tại span client; filter chỉ bỏ span khi có card.number nên một số giá trị vẫn được export dù đội bảo mật cấm chia sẻ metadata giao dịch.
Ứng dụng ghi `http.request.header.authorization` trên span; đội muốn giữ duration và status để chẩn đoán nhưng cấu hình filter loại cả span, khiến API này mất hoàn toàn telemetry hiệu năng.
Trace của một giao dịch thất bại có span exception event chứa stack trace và query parameter nhạy cảm; điều kiện chỉ kiểm tra span attributes không nhận ra dữ liệu nằm trong event.
Nhóm lọc span events có tên exception để giảm kích thước trace nhưng khi service trả HTTP 500, đội điều tra chỉ còn status mà không biết lớp nào ném exception.
Một API gọi ba dependency song song, trong đó một span chậm có status=OK; quy tắc chỉ giữ span lỗi khiến tổng trace thời gian không phản ánh vị trí nghẽn dù người dùng đã gặp timeout.
Hệ thống sampling giữ 1% trace và thêm filter loại span database ngắn hơn 5 ms; các truy vấn N+1 gồm hàng trăm span ngắn biến mất, trong khi tổng thời gian thực tế vẫn rất lớn.
Một nhóm lọc các span có duration nhỏ hơn 10 ms để giảm dung lượng; span ghi nhận việc retry và dấu mốc transaction xuất hiện ngắn nhưng cần cho việc dựng lại thứ tự gọi.
Một trace đi qua ingress gateway và service mesh sidecar; quy tắc loại span tên proxy để giảm trùng lặp vô tình xóa thông tin thời gian queue chờ upstream khi backend quá tải.
Nhóm chọn bỏ span từ một thư viện HTTP dựa trên instrumentation scope name, nhưng thư viện được nâng cấp và đổi scope; lượng trace export tăng gấp đôi dù cấu hình filter không lỗi.
Trace ở staging dùng service.version='candidate' còn production dùng số build; rule lọc theo biểu thức so sánh phiên bản không phù hợp khiến một số trace production bị loại.
Một filter nhắm bỏ span health check theo http.target='/health', nhưng SDK mới ghi url.path và http.route; cùng endpoint được giữ ở phiên bản mới và bị bỏ ở phiên bản cũ.
Một dịch vụ gRPC trả lỗi nghiệp vụ bằng grpc.status_code nhưng HTTP status của span vẫn là 200; điều kiện chỉ dựa vào http.response.status_code đánh giá span là thành công và loại khỏi trace.
Đội muốn bỏ các span lặp lại của Redis GET nhưng vẫn giữ Redis timeout; rule lọc chỉ dựa vào db.operation='GET' khiến thời gian gọi lỗi cũng biến mất khỏi trace.
Một backend gọi kho dữ liệu với query SQL có tham số; collector lọc toàn bộ span có db.statement để tránh lộ PII, nhưng không còn dấu vết thời gian truy vấn của các endpoint quan trọng.
Nhóm lấy mẫu traces ở SDK và tiếp tục lọc ở Collector; tỷ lệ trace hoàn chỉnh có root span và đủ child spans giảm mạnh, dù số trace được backend lưu vẫn đạt ngân sách.
Collector nhận một span có thuộc tính business.event='refund.completed' cùng trace của người dùng; policy loại toàn bộ span thuộc namespace billing thành công làm mất bằng chứng ghép với audit log.
Một trace dùng parent span từ dịch vụ mobile và child spans tại microservice; filter chỉ giữ child spans có lỗi nhưng loại parent, nên giao diện tracing hiển thị nhiều root rời rạc cho cùng một phiên.
Một collector lọc resource của tenant A ở pipeline traces trong khi span của tenant B có link tới trace ID của tenant A; khi điều tra liên dịch vụ, mối liên kết còn trong dữ liệu nhưng trace đích không có quyền truy xuất.
API nhận nhiều request có status 404 hợp lệ trong chức năng tra cứu; nhóm lọc mọi span HTTP 404 để giảm nhiễu, nhưng tấn công quét tài nguyên cũng sinh ra 404 và mất thông tin điều tra.
Trong đợt mất một availability zone, trace lỗi 503 được giữ nhưng các span điều hướng failover thành công bị lọc; đội vận hành không biết cơ chế phục hồi đã chuyển qua vùng nào.
Một nhà cung cấp SaaS nhận traces đã lọc nhưng bảng exemplars của Prometheus vẫn liên kết tới trace_id của các span đã bị bỏ; người dùng Grafana nhấn drill-down và nhận kết quả không tìm thấy.
Đội muốn bỏ request body nhạy cảm nằm trong span events nhưng vẫn cần sự kiện exception và timing; rule filter được áp ở cấp span thay vì cấp event khiến cả request biến mất.
Collector dùng một rule OTTL để đọc `attributes["http.route"]` nhưng log records nhận từ filelog không có map attributes tương tự; rule được dùng chung cho nhiều signal và gây kết quả không dự đoán.
Trong môi trường có cả spans và span events, đội cấu hình cùng một điều kiện tên event ở span context; sự kiện nhạy cảm không được lọc vì thuộc tính nằm ở ngữ cảnh span event.
Một policy dùng biểu thức regex để so chuỗi trên thuộc tính có kiểu số nguyên; một số bản ghi gây lỗi đánh giá OTTL và số telemetry được giữ hay bỏ phụ thuộc error_mode của processor.
Đội vận hành cấu hình filter để loại tài nguyên có service.name rỗng nhưng có workload dùng service.name không được gắn; khi mất nhãn, toàn bộ dữ liệu của dịch vụ đó bị bỏ thay vì chỉ không thể phân nhóm.
Một OTTL condition kiểm tra `attributes["environment"] == "prod"`, trong khi resource attribute thực tế là deployment.environment.name; các production span vẫn được giữ ở pipeline thử nghiệm ngoài ý muốn.
Nhóm viết nhiều điều kiện filter cho log nhưng nhầm logic kết hợp giữa các điều kiện; một log chỉ thỏa một trong hai quy tắc bị loại dù người triển khai dự kiến phải thỏa cả hai.
Đội cấu hình điều kiện OTTL có phủ định kép để chỉ giữ lỗi từ service checkout; sau chỉnh sửa, policy loại các lỗi checkout và giữ hầu hết log thông thường mà không phát hiện ở bước kiểm thử.
Trong một chuỗi OTTL conditions, biểu thức so `severity_number` với giá trị chuỗi 'ERROR' thay vì mức số; collector báo lỗi kiểu dữ liệu hoặc không khớp như đội phát triển dự kiến.
Một rule lọc theo `IsMatch` cho phép regex từ tệp cấu hình bên ngoài; khi biểu thức mới có ký tự escape không phù hợp, collector không tải được cấu hình vừa phát hành.
Nhóm muốn lọc HTTP 2xx theo số trạng thái, nhưng một số instrumentation gửi status code dưới dạng chuỗi còn SDK khác gửi kiểu số; cùng điều kiện OTTL xử lý khác nhau trên các nguồn.
Một điều kiện OTTL truy cập nested map mà không kiểm tra giá trị null; khi một exporter không gửi trường cha, bộ lọc tạo evaluation error cho một nhóm log thường ngày.
Một rule dùng biểu thức thời gian để lọc metric cũ nhưng dữ liệu đầu vào có cả timestamp nanoseconds và epoch milliseconds; dữ liệu còn mới bị coi là quá hạn sau lần đổi SDK.
Nhóm deploy OTTL condition viết theo ví dụ của một phiên bản Collector mới; collector hiện tại không hỗ trợ function được gọi nên startup thất bại ngay sau cập nhật cấu hình.
Trong khi kiểm tra filter, đội dùng giá trị `nil` để so trường optional; bản ghi không có trường và bản ghi có trường chứa chuỗi rỗng tạo hành vi khác mà bộ test chưa bao phủ.
Một quy tắc lọc tag http.route dựa vào đường dẫn có Unicode; traffic với dấu tiếng Việt đã percent-encode không khớp regex của đường dẫn đã giải mã nên các span cùng nghiệp vụ được xử lý khác nhau.
Collector được cấu hình xử lý OTTL error bằng chế độ tiếp tục; hàng nghìn bản ghi có kiểu dữ liệu không phù hợp không bị lọc như mong đợi, trong khi biểu đồ health của collector vẫn xanh.
Một nhóm chuyển error mode sang dừng xử lý khi biểu thức OTTL lỗi; một SDK mới gửi giá trị attribute không đúng kiểu làm cả luồng telemetry liên quan bị ảnh hưởng, không chỉ record có vấn đề.
Đội gắn một filter processor lên pipeline metrics và mong log chứa PII cũng được chặn; logs pipeline được định tuyến qua danh sách processors khác nên log vẫn export bình thường.
Một cấu hình Collector có hai pipelines traces cho nội bộ và đối tác; rule lọc Restricted được đặt trên pipeline nội bộ, còn traces pipeline đi đối tác không có bước này.
Collector được triển khai với cấu hình filter ở agent và gateway; một ứng dụng gửi OTLP thẳng tới gateway, bỏ qua agent, khiến chính sách lọc dự kiến chỉ áp dụng một phần traffic.
Nhóm muốn filter ở Collector gateway sau khi nhận dữ liệu từ các node; debug exporter được gắn trước filter và ghi lại cả những log nhạy cảm mà gateway cuối cùng không gửi đi.
OpenTelemetry Collector fan-out logs tới Elasticsearch và một vendor SaaS; cùng filter được bật trên pipeline Elasticsearch nhưng exporter SaaS vẫn nối tới pipeline không có processor đó.
Trong một cụm nhiều collector replicas, config rollout bị lệch phiên bản; log của cùng service khi qua một replica được lọc còn replica khác vẫn xuất nguyên bản tới backend.
Nhóm sửa cấu hình filter qua ConfigMap nhưng không restart hoặc reload collector đúng cơ chế; file trên disk đã đổi nhưng telemetry vẫn được xử lý theo quy tắc trước đó.
Collector gateway nhận traffic từ Kubernetes và máy ảo legacy; các log máy ảo không có k8s.namespace.name nên filter dựa vào namespace bỏ qua dữ liệu đó và chi phí lưu trữ không giảm.
Đội lọc logs level DEBUG tại gateway nhưng processor batch và memory_limiter phía trước vẫn phải giữ lượng lớn record chưa lọc; memory của collector tăng trong đợt lỗi ứng dụng.
Một collector queue của exporter tăng mạnh sau khi bên lưu trữ chậm; nhóm bổ sung filter ở sau bước xử lý tốn CPU, nhưng CPU ingress vẫn bão hòa vì dữ liệu đã được parse và transform trước khi loại.
Trong khi scrape Prometheus, OpenTelemetry Collector nhận cả metrics self-observability và metrics của ứng dụng; rule lọc theo tiền tố otelcol vô tình loại metric giám sát chính collector trước khi tới Grafana.
Đội chỉ muốn giảm traffic đến vendor thương mại nhưng cần giữ dữ liệu đầy đủ trong kho nội bộ; áp filter ở nguồn SDK khiến cả hai bên đều mất dữ liệu phân tích chi tiết.
Nhóm muốn lọc dữ liệu nhạy cảm tại egress gateway nhưng log file thô đã tồn tại trên node và trong queue của agent; kiểm toán chỉ xem dữ liệu sau exporter và bỏ qua những bản sao trung gian.
Một collector xử lý metrics theo pipeline pull từ Prometheus receiver, trong khi application logs đẩy OTLP qua đường khác; chính sách lọc chung được đặt ở một nhánh và số liệu chi phí hai tín hiệu thay đổi không đồng đều.
Nhóm vận hành có bốn nhóm ứng dụng chia sẻ collector nhưng dùng một filter theo service.name; một team đổi tên service mà không thông báo, làm rule khác lọc nhầm metrics của team đó.
OTTL rule được triển khai qua Helm template; ký tự ngoặc kép trong regex bị template engine thay đổi trước khi tới Collector, khiến điều kiện thực thi khác với file review ở Git.
Một exporter vào kho ngoài báo request rejected do chứa dữ liệu cấm; filter trước exporter vẫn ghi nhận số record đã xử lý nhưng không có chỉ số rõ ràng về số record còn sót bị kho từ chối.
Đội loại bỏ 80% logs 'không quan trọng' bằng filter, nhưng trong một incident CPU tăng, bản ghi có giá trị DEBUG về connection pool bị loại; thời gian xác định nguyên nhân gốc kéo dài so với trước.
Một incident xảy ra chỉ ở khu vực miền Trung; filter telemetry chỉ giữ dữ liệu từ region trung tâm để giảm chi phí và đội trực không có dấu vết yêu cầu từ các vùng khác.
Nhóm chỉ giữ spans lỗi và bỏ spans thành công; khi một request người dùng mất 20 giây nhưng cuối cùng trả HTTP 200, toàn bộ trace chậm bị loại, khiến SLO latency khó điều tra.
Collector lọc logs HTTP 2xx ở gateway để giảm lưu trữ; khi backend trả JSON lỗi nghiệp vụ với HTTP 200, bằng chứng trong access logs bị loại dù số giao dịch thành công thực giảm.
Nhóm loại mọi datapoint có giá trị 0 để giảm dung lượng; một thiết bị vừa phục hồi và bắt đầu báo error_count=0 nhưng dashboard không nhận được dấu hiệu hồi phục.
Một dịch vụ dùng log 'authorization denied' để phân tích gian lận nhưng log ở severity INFO; rule lọc INFO của tất cả service làm mất hồ sơ từ chối truy cập trong một đợt tấn công.
Đội lọc metrics của các pod batch sau khi job kết thúc để giảm cardinality; số liệu tổng thời gian xử lý job không được giữ đủ để so sánh các lần chạy bị chậm.
Nhóm giảm số sự kiện trace bằng cách lọc các span event dưới ngưỡng severity, nhưng sự kiện thay đổi trạng thái saga không có severity và mất khỏi quá trình dựng lại giao dịch.
Trong chiến dịch tải lớn, collector chỉ lọc các logs có dung lượng body hơn 64 KB; nhiều log ngắn chứa token vẫn lọt qua và chính sách bảo vệ không đạt yêu cầu kiểm toán.
Một bộ lọc dựa vào thông điệp có chữ 'test' để bỏ telemetry thử nghiệm; tên service production 'contest-api' cũng khớp chuỗi và phần lớn lỗi thật không còn được lưu.
Đội phát triển đặt quy tắc filter theo danh sách exception thường gặp; khi ứng dụng nâng cấp thư viện và đổi tên exception class, lượng log tăng mạnh dù bản chất lỗi không đổi.
Nhóm đo lượng dữ liệu giảm bằng số log records sau filter nhưng không theo dõi kích thước byte; một số log lớn còn lại khiến hóa đơn ingest vendor không giảm tương xứng.
Một cảnh báo nghiêm trọng dựa trên số 5xx ở metrics biến mất sau khi bật filter; exporter ứng dụng vẫn trả metric nguyên vẹn nhưng các datapoint có label status_code từ 500 bị loại trước backend.
Đội tuyên bố filter giúp giảm 90% traces nhưng dashboard tracing thiếu các span gốc; metrics về số trace hoàn chỉnh và tỉ lệ orphan spans chưa được đưa vào kiểm tra nghiệm thu.
Nhóm chạy load test với traffic tổng hợp chỉ gồm endpoint /health và /users; filter hoạt động đúng trên tập thử nhưng production có WebSocket, gRPC và background job sử dụng các attributes khác.
Bài test OTTL chỉ kiểm tra điều kiện với attributes luôn có; khi record thật thiếu resource attributes, processor phát lỗi đánh giá và số dữ liệu export lệch khỏi kỳ vọng.
QA test lọc log PII chỉ đưa vào email dạng ASCII; production nhận địa chỉ email chứa Unicode và chuỗi bị escape, nên một số bản ghi không khớp tiêu chí.
Một test kiểm tra filter loại span theo http.route nhưng SDK ở production đã đổi semantic conventions; build test vẫn xanh trong khi span có attribute url.path mới được giữ.
Đội kiểm thử rule chỉ trên logs signal mà quên xem tác động lên metrics và traces; cùng config processor được tái sử dụng và điều kiện chung làm mất bucket latency của một dịch vụ.
Nhóm thử nghiệm filter trên một phần nhỏ traffic staging và thấy chi phí giảm, nhưng production có 100 lần số tenant và rất nhiều nhãn động nên áp lực regex trên collector vượt dự báo.
Trong một thử nghiệm A/B cấu hình Collector, nhóm so lượng telemetry nhận được mà không cố định lưu lượng và tỉ lệ sampling SDK; kết quả giảm ingest bị gán nhầm hoàn toàn cho filter mới.
Đội đánh giá chất lượng filter bằng số record bị loại mà không so các chỉ số SLO hoặc sự cố đã điều tra; giảm chi phí đạt mục tiêu nhưng các trace quan trọng mất khiến nhóm phải yêu cầu rollback.
Trong một bài diễn tập bảo mật, token giả được chèn vào cả http headers, log body và exception events; pipeline chỉ ngăn xuất ở một signal, còn bảng test hiện chỉ xác minh logs.
Một custom rule hoạt động khi collector xử lý bản ghi riêng lẻ, nhưng trong load test có batch lớn với record lỗi kiểu dữ liệu; thống kê drop count không khớp số bản ghi cần loại theo policy.
Đội không có bộ dữ liệu regression để kiểm thử regex filter sau mỗi thay đổi; một sửa đổi nhỏ để nhận diện URL mới khiến log của endpoint thanh toán cũng bị lọc mà không được phát hiện.
Một canary Collector mới chạy song song với bản cũ nhưng hai nhóm nhận traffic từ service khác nhau; so sánh số lỗi và lượng log không đủ điều kiện để kết luận chất lượng filter cải thiện.
Nhóm cập nhật OTTL để bảo vệ PII nhưng exporter vẫn phát metric từ collector cho thấy queue và drop tăng; đội vận hành không biết số record mất do filter có chủ đích hay do backpressure.
Trong một đợt khắc phục sự cố, on-call tắt filter để lấy thêm trace; cùng lúc vendor ngoài nhận bản ghi có dữ liệu nhạy cảm vì quy trình bật chế độ chẩn đoán chưa phân định đường export an toàn.
Một hệ thống muốn tạm tăng log DEBUG trong 30 phút, nhưng filter đang loại mọi DEBUG trên toàn pipeline; kỹ sư chỉ đổi log level tại ứng dụng và không thấy thêm dữ liệu trên backend.
Đội dùng filter để giảm dữ liệu trước khi đưa lên SaaS, nhưng nhà cung cấp vẫn tính phí theo số byte ingress trước bước lọc của họ; chi phí không thay đổi dù dashboard chỉ hiển thị ít records hơn.
Sau khi áp rule filter mới, thời gian CPU của collector tăng do regex phức tạp trên từng log message; số telemetry được gửi đi giảm nhưng autoscaler phải tăng số collector replicas.
Nhóm lọc các span có attribute session_id nhưng trình duyệt cũng gửi session_id ở baggage rồi các service ghi lại vào log; chỉ traces giảm dữ liệu nhạy cảm còn log export vẫn có identifier đó.
Một pipeline dùng filter processor loại log và metrics theo tenant nhưng chưa phân biệt quyền truy cập từng export destination; dữ liệu tenant B được giữ trong backend nội bộ dành cho tenant A do nhãn định tuyến sai.
Đội muốn giữ error logs cho đội bảo mật nhưng không xuất PII; khi dùng filter loại cả log chứa email, điều tra account takeover không còn mốc thời gian xác thực của người bị ảnh hưởng.
Filter đang loại các metric debugging chưa được dùng trên dashboard; sau khi service gặp memory leak, hệ thống thiếu allocation-rate metrics và đội phải khôi phục cấu hình đo trong lúc production đang lỗi.
Một quy tắc filter loại traces có thời gian dưới 100 ms nhưng vẫn giữ traces lâu; khi thay đổi đường đi làm latency request tăng từ 60 lên 120 ms, số trace đột ngột tăng và hóa đơn lưu trữ biến động khó giải thích.
Một collector duy trì filter cho status=success ở log, metrics và traces nhưng mỗi signal ghi trạng thái bằng loại trường khác nhau; doanh nghiệp thấy mức giảm dữ liệu không đồng nhất giữa ba kho quan sát.
Nhóm kiểm toán yêu cầu báo cáo trường dữ liệu bị loại, mức phân loại và lý do giữ ngoại lệ; cấu hình filter đã thay đổi nhiều lần qua GitOps nhưng không có bảng theo dõi tác động theo phiên bản.
Trong một vụ việc, đội bảo mật cần tra lại truy cập 403 trước khi người dùng bị khóa; policy filter coi tất cả 4xx là nhiễu và log đã bị bỏ trước khi vào kho lưu giữ.
Nhóm loại hoàn toàn metrics của endpoint ít được truy cập, nhưng endpoint đó là đường khôi phục tài khoản; khi bị tấn công có chủ đích, hệ thống không còn dữ liệu phát hiện tỷ lệ lỗi bất thường.
Đội đặt filter loại bỏ logs của mọi service ở namespace staging; một dịch vụ sản xuất được triển khai nhầm vào staging nhưng vẫn phục vụ traffic thật và không có log phục vụ điều tra.
Trong một đợt chuyển hệ thống quan sát, pipeline cũ và mới có quy tắc lọc khác nhau; báo cáo tổng số lỗi tuần này giảm mạnh nhưng chưa xác định có phải vì chất lượng dịch vụ tốt hơn hay vì dữ liệu bị bỏ.
