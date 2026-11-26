Một cụm Fluentd nhận log container qua tail input nhưng file log được Docker rotate mỗi ngày; sau rotation, Fluentd tiếp tục đọc inode cũ và không thu thập các dòng mới từ file được tạo lại.
Fluentd chạy trong Kubernetes DaemonSet và tail đường dẫn /var/log/containers, nhưng container runtime của node ghi log vào đường dẫn khác sau khi nâng cấp; các pod mới không có log trong backend dù Fluentd process vẫn Ready.
Một input tail được cấu hình path chỉ khớp /var/log/app/*.log, trong khi ứng dụng tạo file theo thư mục ngày; log của ngày hôm sau không được thu thập và dashboard dừng cập nhật lúc nửa đêm.
Ứng dụng ghi log vào symlink current.log trỏ tới file mới sau mỗi lần deploy; Fluentd theo dõi target cũ và không phát hiện file mới vì cấu hình follow_inodes chưa phù hợp.
Một input tail dùng position file trên filesystem tạm của container; khi pod Fluentd restart, vị trí đọc bị mất và hàng triệu dòng cũ được gửi lại hoặc bỏ qua tùy trạng thái file.
Fluentd chạy nhiều worker nhưng các worker cùng đọc một file log với position file dùng chung; offset cập nhật cạnh tranh khiến một số dòng bị gửi trùng hoặc bỏ sót.
Một file log được truncate khi ứng dụng khởi động lại thay vì rotate; Fluentd giữ offset lớn hơn kích thước file và chờ dữ liệu mới, khiến log đầu phiên sau không được đọc.
Ứng dụng ghi JSON mỗi dòng nhưng một số log có ký tự xuống dòng nằm trong chuỗi message; parser line-oriented tách thành nhiều bản ghi và phần sau không còn là JSON hợp lệ.
Fluentd nhận log qua forward input từ các agent nhưng một agent cấu hình shared key khác; kết nối bị từ chối trong khi các agent còn lại gửi dữ liệu bình thường.
Một hệ thống dùng forward input qua TCP nhưng firewall chỉ mở cổng UDP cùng số hiệu; agent liên tục retry kết nối và Fluentd không nhận được event nào.
Ứng dụng gửi log qua HTTP input với header xác thực nhưng reverse proxy loại bỏ header trước khi chuyển tiếp; Fluentd nhận request không có thông tin cần thiết để xác minh nguồn gửi.
Fluentd nhận syslog từ firewall nhưng parser đang giả định RFC3164 trong khi thiết bị gửi định dạng RFC5424; timestamp, hostname và severity bị tách sai trường.
Một số thiết bị mạng gửi syslog qua UDP với burst hàng nghìn gói mỗi giây; socket receive buffer của Fluentd không đủ và kernel drop packet trước khi event được parse.
Input syslog nhận thông điệp có PRI và facility nhưng cấu hình parser bỏ qua phần PRI; dashboard phân loại severity sai và đội trực không phân biệt được cảnh báo hệ thống với thông tin thông thường.
Một ứng dụng Java ghi stack trace nhiều dòng vào stdout, nhưng Fluentd tail input chưa cấu hình multiline parser; mỗi dòng stack trace thành một event riêng và không còn gắn với exception đầu tiên.
Multiline parser dùng pattern nhận diện đầu stack trace 'Exception in thread', trong khi framework mới bắt đầu bằng timestamp và level ERROR; các dòng lỗi bị ghép vào bản ghi trước đó.
Ứng dụng ghi log Python có dòng continuation bắt đầu bằng tab; parser multiline chỉ nhận dòng có bốn dấu cách nên một phần stack trace bị tách rời.
Một container ghi nhiều loại log trên cùng stdout: JSON access log và text application log; parser duy nhất được áp dụng cho cả hai nên các dòng text tạo parse error và trường access log bị thiếu.
Parser JSON của Fluentd gặp một dòng có trailing comma do thư viện cũ; cấu hình emit_invalid_record_to_error không bật và bản ghi lỗi biến mất khỏi output chính mà không có tuyến điều tra.
Fluentd parse timestamp theo UTC nhưng ứng dụng ghi local time +07:00; dữ liệu được gán sai thời điểm và dashboard cho thấy lỗi xảy ra trước khi bản phát hành bắt đầu.
Log từ ứng dụng chứa timestamp với độ chính xác microsecond, nhưng parser chỉ giữ tới giây; khi ghép nhiều sự kiện trong cùng giây, thứ tự xử lý giao dịch không thể xác định.
Một parser regex được dùng cho access log nhưng URL query chứa dấu cách được percent-encode khác dự kiến; regex không khớp và Fluentd đưa record vào error stream.
Nhóm đổi tên trường time thành timestamp trong parser nhưng filter sau đó vẫn đọc key time; event timestamp bị thay bằng thời điểm ingest và độ trễ pipeline hiển thị gần bằng không.
Parser nginx ghi status dưới dạng chuỗi còn filter downstream so sánh với số nguyên 500; lỗi HTTP 5xx không được tách ra và tất cả request bị coi là không lỗi.
Một input tail đọc JSON có trường log chứa object lồng nhau; parser flatten cấu trúc thành chuỗi và downstream không thể truy vấn các trường con như user.id hoặc error.type.
Fluentd nhận log CRI có prefix timestamp và stream stdout/stderr; parser chỉ loại prefix stdout nên log stderr còn nguyên tiền tố và không parse được JSON.
Nhóm triển khai parser mới cho log nginx nhưng chưa chạy thử với các định dạng cũ đang tồn tại; một số máy chủ chưa nâng cấp gửi format khác và bị đẩy vào error label liên tục.
Ứng dụng ghi log có trường message dài hơn giới hạn parser; Fluentd cắt dữ liệu trước khi parse và thông tin cuối stack trace chứa nguyên nhân gốc bị mất.
Một parser dùng key_name log nhưng container runtime chuyển sang trường message; Fluentd coi cả JSON object là text và các filter theo severity không còn hoạt động.
Nhóm dùng parser multi_format để nhận cả JSON và regex, nhưng pattern đầu tiên khớp quá rộng; dòng JSON hợp lệ bị parse theo regex và mất các field có cấu trúc.
Fluentd filter grep loại mọi event có status không bằng 200; log không có trường status như application event cũng bị loại, bao gồm audit event cần giữ.
Nhóm dùng record_transformer thêm environment và service nhưng cấu hình renew_record chỉ giữ hai trường mới; message, timestamp và request_id gốc bị mất trước khi tới output.
Một filter record_transformer tạo trường log_level bằng cách tham chiếu severity nhưng một số nguồn dùng level; giá trị nil được ghi vào record và bộ phân loại downstream gán nhầm tất cả là INFO.
Fluentd dùng filter parser để parse trường message JSON, nhưng reserve_data không bật; sau parse, các metadata ban đầu như container_id và stream bị loại.
Nhóm bật remove_key_name_field khi parse nội dung JSON để tránh lặp message; một số ứng dụng vẫn cần message gốc cho full-text search và dữ liệu không còn ở output.
Filter Kubernetes metadata truy vấn API server cho mỗi container mới; khi API server throttling, event vẫn được tail nhưng thiếu namespace, pod labels và owner metadata.
Fluentd enrich record bằng metadata Kubernetes nhưng cache TTL quá dài; sau khi pod được thay thế bằng version mới, log mới tiếp tục gắn nhãn image và deployment của pod cũ.
Một filter Kubernetes metadata dùng tag regex không khớp tên container có dấu gạch dưới; log của một nhóm workload không được enrich và dashboard theo namespace bỏ sót chúng.
Ứng dụng ghi user_id vào log record và nhóm muốn che PII bằng filter; filter chỉ xóa trường user.id nhưng dữ liệu tương tự vẫn nằm trong message và nested payload.
Fluentd dùng grep để loại log có chứa chuỗi token, nhưng token được ghi dưới dạng Authorization:Bearer không có dấu cách; regex hiện tại không khớp và credential lọt qua output.
Một filter loại bỏ trường password nhưng ứng dụng mới ghi secret dưới tên db_password; log sau deploy vẫn chứa credential dù cấu hình Fluentd không báo lỗi.
Đội dùng record_transformer để mask số điện thoại bằng biểu thức thay thế; biểu thức chỉ xử lý chuỗi ASCII và bỏ sót số có dấu cách, mã quốc gia hoặc ký tự phân cách.
Nhóm lọc access log health check dựa vào path /health; request có query string /health?full=1 không khớp và tạo lượng log lớn trong giờ kiểm tra.
Fluentd lọc tất cả log level DEBUG để giảm chi phí, nhưng một thư viện ghi audit event quan trọng ở DEBUG; sự kiện thay đổi quyền không còn trong kho kiểm toán.
Một filter grep giữ lại các record có severity ERROR nhưng parser đặt severity dưới dạng lowercase 'error'; các bản ghi lỗi bị loại do so khớp phân biệt hoa thường.
Nhóm lọc log thành công theo HTTP status 2xx nhưng một số ứng dụng ghi status dạng '200 OK'; điều kiện số không nhận dạng được và record thành công vẫn đi vào output.
Fluentd có hai filter cùng sửa trường tag và service; thứ tự filter đổi sau khi thêm plugin mới, làm route downstream chọn nhầm index theo service cũ.
Filter geo enrichment gọi dịch vụ ngoài để tra IP cho từng record; khi dịch vụ lookup chậm, worker Fluentd bị giữ và buffer của các input khác tăng dù log không cần vị trí địa lý.
Một filter dùng Lua script để chuẩn hóa event và script có lỗi khi field request.path là nil; mỗi bản ghi thiếu trường này tạo exception và làm tăng error rate của Fluentd.
Nhóm dùng filter concat để ghép log multiline nhưng key nhận diện container bị thiếu ở một số record; log của hai container cùng tag có thể bị ghép chung thành một stack trace.
Concat filter có timeout thấp hơn khoảng nghỉ giữa hai dòng stack trace; mỗi exception dài bị tách thành nhiều event khi ứng dụng bận và ghi chậm.
Ứng dụng ghi JSON log một dòng nhưng filter concat vẫn áp dụng pattern multiline; các event không cần ghép bị giữ trong buffer chờ timeout, làm chậm việc chuyển log.
Fluentd dùng filter dedup để loại log trùng theo message trong một cửa sổ thời gian; hai giao dịch hợp lệ có cùng thông báo 'payment accepted' bị gộp thành một record.
Nhóm dùng filter sampling giữ 1% access log thành công nhưng sampling được áp dụng trước khi tách loại endpoint; một API hiếm có sự cố mất gần hết bằng chứng request.
Filter parser chuyển trường duration từ milliseconds sang seconds nhưng không đổi tên field; dashboard downstream coi giá trị mới vẫn là milliseconds và latency giảm giả một nghìn lần.
Fluentd gắn tag app.production bằng rewrite_tag_filter dựa vào trường environment; record không có environment được gắn tag mặc định production và đi vào index dữ liệu thật.
Rewrite tag rule có biểu thức khớp mọi service bắt đầu bằng 'pay'; tag của payment-test cũng bị đổi thành payment-prod và log thử nghiệm trộn vào kho production.
Một rule rewrite_tag_filter phát sinh tag mới rồi tag mới lại khớp rule ban đầu; event bị chuyển qua nhiều tag liên tục và tăng tải CPU cho worker.
Nhóm dùng label app để route logs tới output tương ứng; một ứng dụng mới đặt app name có dấu chấm và regex route không khớp nên log rơi vào output mặc định.
Fluentd dùng tag prefix để chọn index theo namespace nhưng tag được tạo từ tên namespace chứa chữ hoa; index template chỉ hỗ trợ chữ thường nên output Elasticsearch từ chối một số event.
Một source forward gửi tag app.api nhưng source khác gửi app_api; các match pattern hiện tại chỉ nhận dấu chấm và dữ liệu của source thứ hai không được route tới output.
Đội muốn route audit log sang storage bất biến và application log sang Elasticsearch; rule match audit được đặt sau rule catch-all nên mọi event đã đi vào output chung trước.
Một tag được tạo dựa trên customer_id để tách output theo tenant; số tenant tăng nhanh tạo quá nhiều route và index, khiến Fluentd cùng backend lưu trữ chịu áp lực.
Nhóm dùng copy output để gửi cùng log tới Elasticsearch và S3; một output chậm giữ buffer chung và làm chậm cả nhánh output còn lại dù storage S3 đang hoạt động.
Fluentd match rule không có catch-all cho tag mới; event được parse thành công nhưng không có output nào nhận và log cảnh báo no patterns matched xuất hiện.
Một match rule sử dụng wildcard quá rộng cho tag app.**; audit event và debug event cùng được gửi tới output đắt tiền dù yêu cầu chỉ giữ access log.
Ứng dụng thêm tag version vào mỗi record để chọn index; khi deploy rolling update, tên index phân mảnh theo từng build và chi phí lưu trữ tăng mạnh.
Fluentd dùng label để gom nhiều tag vào một route chung nhưng output cần biết source file để điều tra; filter xóa tag gốc và thông tin nguồn không còn trong record.
Một file cấu hình Fluentd có nhiều match block trùng pattern; block đầu tiên bắt toàn bộ event khiến block thứ hai dành cho audit log không bao giờ được thực thi.
Nhóm sửa thứ tự match block để ưu tiên security log; rule mới lại bắt cả application error log có tag chung và gửi dữ liệu sang kho hạn chế quyền đọc.
Fluentd dùng @label để chuyển event qua nhánh xử lý phụ; một filter trong label nhánh thay đổi record nhưng output chính vẫn nhận bản gốc, khiến dữ liệu nhạy cảm không được mask ở một nơi.
Một route chuyển event sang secondary label khi parser lỗi nhưng secondary output không được cấu hình; log lỗi parse chỉ xuất hiện trong internal log của Fluentd mà không có nơi lưu.
Buffer file của Fluentd đặt trên ephemeral storage của pod; node bị drain làm pod mất toàn bộ chunk chưa gửi và hàng triệu log chưa tới backend.
Fluentd dùng memory buffer cho access log lưu lượng cao; khi output Elasticsearch chậm, bộ nhớ process tăng đến giới hạn container và pod bị OOMKilled trước khi buffer được flush.
File buffer đặt trên PersistentVolume có dung lượng 5 GB, nhưng tốc độ log tăng gấp năm trong chiến dịch bán hàng; buffer đầy và Fluentd bắt đầu từ chối hoặc loại event mới.
Buffer chunk được đặt giới hạn 8 MB nhưng mỗi record có payload lớn chứa stack trace và request body; chunk bị retry liên tục vì kích thước vượt giới hạn output.
Fluentd cấu hình total_limit_size quá thấp cho buffer file; khi backend ngừng hoạt động 20 phút, buffer đầy và các event mới bị drop dù pod còn CPU và RAM.
Đội đặt queued_chunks_limit_size lớn nhưng không tăng dung lượng volume; số chunk chờ vượt khả năng lưu trữ và Fluentd dừng nhận thêm dữ liệu.
Một output Elasticsearch trả 429 khi ingest cao; Fluentd retry nhưng backoff quá ngắn khiến số request retry tăng và làm cụm Elasticsearch càng quá tải.
Output S3 gặp lỗi 503 tạm thời nhưng retry_max_times bị giới hạn nhỏ; sau vài lần thử, chunk bị đánh dấu lỗi và log chưa được lưu dù dịch vụ S3 đã phục hồi.
Fluentd không nhận phản hồi từ backend trước khi retry timeout; backend thực tế đã ghi chunk nhưng Fluentd gửi lại cùng dữ liệu, gây duplicate documents trong index.
Nhóm bật retry_forever để tránh mất log khi backend ngừng hoạt động; sau khi backend phục hồi, backlog nhiều giờ được flush đồng loạt và gây quá tải ngược cho storage.
Một output dùng retry_wait tăng theo exponential backoff nhưng retry_max_interval đặt quá lớn; backend chỉ gián đoạn vài phút, còn backlog tiếp tục chờ lâu sau khi dịch vụ đã sẵn sàng.
Fluentd lưu buffer theo file nhưng quyền truy cập thư mục buffer không cho user chạy tiến trình ghi; plugin khởi động được nhưng lần flush đầu tiên lỗi permission denied.
Pod Fluentd được di chuyển sang node khác và hai replica cùng mount một buffer directory không hỗ trợ chia sẻ an toàn; chunk metadata bị tranh chấp và event có thể được gửi trùng.
Fluentd restart khi đang ghi chunk file; file tạm còn lại được phục hồi như chunk chưa hoàn tất và một số event bị lặp sau khi tiến trình khởi động.
Nhóm đặt flush_interval 1 giây để log xuất hiện nhanh trên dashboard; lượng request tới Elasticsearch tăng mạnh và mỗi chunk nhỏ làm overhead ingest tăng.
Output Elasticsearch dùng bulk request nhưng chunk size quá lớn; một vài document lỗi làm cả bulk response chứa item failure, trong khi plugin chỉ đánh dấu chunk thành công theo HTTP 200.
Một index Elasticsearch đạt giới hạn mapping field do mỗi ứng dụng tạo tên field động; output Fluentd nhận HTTP 400 và retry liên tục các chunk chứa mapping conflict.
Output Kafka từ chối event vì message vượt max.message.bytes; Fluentd chỉ ghi lỗi output và buffer giữ chunk mãi dù tăng retry không thể giải quyết giới hạn kích thước.
Fluentd gửi log sang Kafka với partition key là user_id; một khách hàng có lưu lượng lớn dồn vào một partition và consumer lag tăng dù các partition khác gần như rảnh.
Output forward tới aggregator Fluentd trung tâm bị ngắt kết nối khi load balancer thay đổi backend; retry queue tăng và các agent vùng xa không thể gửi dữ liệu trong thời gian failover.
Aggregator nhận forward chunk nhưng worker xử lý chậm hơn tốc độ gửi từ agent; số kết nối TCP ổn định song buffer queue tăng liên tục và độ trễ log end-to-end vượt SLA.
Fluentd output tới HTTP endpoint của vendor nhận 202 Accepted trước khi dữ liệu được xử lý bền vững; vendor sau đó loại record không hợp lệ nhưng Fluentd đã xóa chunk khỏi buffer.
Một output file dùng path theo ngày nhưng directory chưa được tạo sau lần rotate; flush thất bại và chunk bị giữ lại dù filesystem còn dung lượng.
Fluentd ghi output file bằng append nhưng tiến trình downstream đọc file cùng lúc với rotation; record cuối chunk bị đọc hai lần do rename và offset collector không đồng bộ.
Nhóm cấu hình secondary output cho lỗi gửi Elasticsearch nhưng secondary cũng trỏ về cùng cluster; khi cluster ngừng hoạt động, cả output chính và phụ cùng thất bại.
Fluentd dùng copy output với ignore_error ở một nhánh; output audit không ghi được do permission nhưng nhánh application log vẫn thành công và lỗi audit không được thông báo đúng mức.
Đội muốn gửi error log tới kho lâu dài và access log tới kho 7 ngày; match rule hiện tại đưa cả hai vào cùng index nên retention ngắn làm mất log lỗi cần cho kiểm toán.
Một plugin output mới được cài trên một node Fluentd nhưng thiếu trên các node khác; cùng cấu hình chạy ở vài replica và thất bại khi scheduler chuyển pod tới node chưa có plugin.
Fluentd plugin Elasticsearch nâng phiên bản và thay đổi cách xác thực TLS; endpoint vẫn mở nhưng handshake thất bại vì CA bundle trên container cũ.
Output HTTP yêu cầu client certificate nhưng secret mount trong Kubernetes chưa được cập nhật ở một số pod; một phần replica flush thành công còn phần khác retry liên tục.
Fluentd dùng DNS để tìm aggregator nhưng resolver cache giữ IP của pod cũ sau khi Service chuyển endpoint; output tiếp tục gửi tới địa chỉ không còn nhận traffic.
Agent Fluentd chạy trên node không thể resolve tên Elasticsearch khi CoreDNS quá tải; các output khác dùng IP trực tiếp vẫn hoạt động và nhóm chưa phân biệt lỗi DNS với lỗi backend.
Fluentd forward qua TLS nhưng hai bên không thống nhất tên SNI; kết nối chỉ thất bại khi đi qua load balancer có nhiều virtual host.
Ứng dụng Java log vào stdout, container runtime chuyển thành CRI log và Fluentd tail file; sau nâng cấp runtime, prefix timestamp đổi định dạng khiến parser không nhận dạng được một phần event.
Kubernetes DaemonSet Fluentd có toleration cho node worker nhưng thiếu toleration cho node có taint dedicated; log từ workload chạy trên node chuyên dụng không được thu thập.
Một node có nhiều container ephemeral và file log bị xóa nhanh sau khi pod kết thúc; Fluentd poll interval dài nên chưa kịp đọc hết file trước khi kubelet dọn dẹp.
Fluentd Kubernetes metadata filter cần quyền get/list/watch pods và namespaces; sau khi RBAC bị thu hẹp, event vẫn tới nhưng plugin liên tục báo forbidden và metadata enrichment thất bại.
Nhóm đặt hostPath /var/log/pods nhưng pod Fluentd chạy read-only root filesystem và volume mount không cho đọc file; daemonset Ready nhưng input tail không theo dõi được log container.
Fluentd sidecar trong từng pod và DaemonSet node agent cùng tail một file application log; cùng event được gửi hai lần tới Elasticsearch và số request trong dashboard tăng gấp đôi.
Ứng dụng gửi log trực tiếp tới sidecar Fluentd qua localhost, nhưng sidecar bị restart trong lúc pod vẫn phục vụ request; log phát sinh ở khoảng trống không có agent nhận.
DaemonSet Fluentd dùng một position file duy nhất cho nhiều đường dẫn file log; khi một file bị rotate, offset của file khác bị áp nhầm và một phần dòng bị bỏ qua.
Cluster nâng cấp từ Docker runtime sang containerd; cấu trúc tên file symlink thay đổi và Fluentd path cũ không còn khớp với log của pod mới.
Fluentd chạy trong pod có memory limit 256 MiB; khi multiline parser giữ nhiều bản ghi chưa hoàn chỉnh, bộ nhớ tăng nhanh và pod bị OOMKilled.
Nhóm tăng số worker Fluentd từ 2 lên 8 để xử lý throughput; plugin parser không thread-safe tạo lỗi dữ liệu và record bị xử lý không nhất quán giữa worker.
Fluentd dùng worker affinity để chia file theo tag nhưng các tag nóng đều được gán cho cùng một worker; CPU tổng còn thấp trong khi worker đó bão hòa và buffer của nó tăng.
Ứng dụng phát sinh burst log khi batch hoàn tất; input buffer nhận được dữ liệu nhưng output flush theo tốc độ cố định, khiến queue depth tăng rồi giảm nhiều giờ sau.
Fluentd ghi log nội bộ vào cùng output với log ứng dụng; khi output gặp lỗi, thông báo retry của chính Fluentd tạo thêm log đầu vào và làm tăng tải theo vòng lặp.
Monitoring chỉ kiểm tra tiến trình Fluentd sống và cổng forward mở; buffer queue đã đầy nhiều giờ nhưng health check vẫn xanh vì không theo dõi trạng thái flush và retry.
Dashboard đo số event được input nhận nhưng không đo số event output thành công; nhóm kết luận không mất log dù hàng triệu chunk đang nằm trong retry queue.
Một agent Fluentd ngừng hoạt động trong 30 phút nhưng DaemonSet tự khởi động lại; log file trên node đã rotate nhiều lần và position file không còn bao phủ khoảng thời gian bị gián đoạn.
Đội vận hành chỉ theo dõi số lỗi plugin mà không quan sát buffer_stage_length, buffer_queue_length và retry_count; sự cố chậm dữ liệu được phát hiện sau khi người dùng phản ánh.
Fluentd có CPU thấp nhưng output latency cao và số chunk đang chờ tăng; nhóm tăng worker count trong khi nút nghẽn thực sự là giới hạn ingest của Elasticsearch.
Một bộ lọc Lua chiếm CPU đáng kể cho từng record; throughput Fluentd giảm sau khi thêm chuẩn hóa chuỗi, dù network và output backend không có dấu hiệu quá tải.
Fluentd scrape metric plugin mỗi 60 giây; một đợt buffer đầy chỉ kéo dài 20 giây rồi tự hồi phục nên dashboard không ghi nhận đỉnh và đội trực bỏ lỡ cảnh báo.
Log pipeline ghi timestamp lúc ingest thay vì timestamp sự kiện; khi backlog được flush sau outage, toàn bộ log cũ xuất hiện như sự kiện mới và thứ tự điều tra bị sai.
Một nhóm so thời gian event timestamp với thời gian lưu ở backend nhưng không đo thời gian chờ buffer; dashboard cho thấy độ trễ trung bình thấp trong khi một số chunk bị giữ hơn một giờ.
Ứng dụng ghi timestamp dạng milliseconds, Fluentd parser hiểu là seconds; log được gắn vào mốc thời gian xa trong tương lai và không xuất hiện trong truy vấn theo ngày hiện tại.
Fluentd cấu hình timekey theo giờ nhưng time_slice_format theo ngày; chunk được chia theo cửa sổ không như mong muốn và file output có tên trùng nhau khi flush.
Đội bật compression gzip cho buffer file nhưng CPU node tăng trong đợt ingest lớn; throughput đọc file và khả năng flush không theo kịp dù dung lượng đĩa giảm.
Fluentd dùng file buffer trên ổ đĩa network filesystem có độ trễ cao; mỗi lần ghi metadata chunk mất nhiều thời gian và input tail bắt đầu trễ so với tốc độ log thực tế.
Disk buffer được mount trên volume có giới hạn IOPS; khi compaction và backup cùng chạy, Fluentd ghi chunk chậm và số lượng file buffer tăng nhanh.
Nhóm tăng chunk_limit_size để giảm số lần request tới Elasticsearch; chunk lớn hơn thời gian retry và tốn nhiều RAM khi flush đồng thời, làm container vượt memory limit.
Fluentd có nhiều plugin filter chạy tuần tự trên cùng worker; một filter enrich DNS chậm làm toàn bộ record phía sau chờ, dù parser và output đều có năng lực xử lý dư.
Đội triển khai cấu hình buffer overflow_action=drop_oldest_chunk để tránh đầy disk; trong đợt outage backend, dữ liệu cũ quan trọng bị loại trước khi backend phục hồi.
Buffer overflow_action=block làm tail input ngừng đọc file; log rotate xóa file chưa đọc và dữ liệu bị mất dù Fluentd không chủ động drop chunk.
Agent gửi forward tới aggregator với ACK timeout quá ngắn; aggregator vẫn xử lý chunk nhưng agent retry trước khi nhận ACK và sinh bản ghi trùng.
Một aggregator Fluentd nhận event từ nhiều agent nhưng tag không có hostname; khi một máy bị lệch cấu hình, nhóm không xác định được nguồn phát sinh record sai.
Nhóm cấu hình source forward với phiếu xác thực shared key dùng chung giữa mọi node; khi một agent bị xâm nhập, credential không thể thu hồi riêng mà không ảnh hưởng toàn bộ cụm.
Fluentd HTTP input được mở trên mọi interface và không có TLS; một máy trong mạng dùng chung có thể gửi log giả vào pipeline và làm nhiễu bằng chứng điều tra.
Log application chứa password và access token được Fluentd gửi qua forward plaintext giữa hai subnet; việc mã hóa ở output Elasticsearch không bảo vệ dữ liệu trên chặng agent-to-aggregator.
Nhóm muốn mask PII trước khi gửi tới vendor nhưng parser chưa tách được nested JSON body; filter chỉ xóa top-level email và dữ liệu vẫn còn ở payload con.
Fluentd ghi file buffer trên đĩa mã hóa nhưng log nội bộ plugin hiển thị raw record khi debug; quyền truy cập file log của tiến trình rộng hơn quyền đọc dữ liệu trong backend.
Một output S3 đặt object key theo tenant_id và ngày; tenant_id do client kiểm soát có thể chứa dấu phân cách đường dẫn và tạo key ngoài cấu trúc prefix dự kiến.
Fluentd gửi audit log cùng access log tới một bucket có lifecycle 7 ngày; dữ liệu kiểm toán cần lưu lâu hơn và bị xóa trước thời hạn quy định.
Đội dùng backup volume buffer nhưng chỉ chụp snapshot mỗi ngày; khi node hỏng giữa hai lần snapshot, chunk chưa flush trong nhiều giờ không thể khôi phục.
Một plugin parser được nâng cấp và đổi tên trường error thành error_message; filter downstream vẫn tham chiếu error và output không ghi nguyên nhân parse failure.
Nhóm đổi cấu hình tag từ app.nginx sang nginx.access nhưng chưa sửa tất cả match rule; log mới được parse nhưng không có output phù hợp và bị bỏ khỏi pipeline.
Fluentd config có syntax hợp lệ nhưng plugin parser không được cài trên image mới; pod restart vào CrashLoopBackOff và log thu thập trên node bị gián đoạn.
Đội triển khai cấu hình qua ConfigMap nhưng một số pod Fluentd chưa restart; cùng cluster có hai phiên bản pipeline và kết quả parse khác nhau giữa node.
Helm chart cập nhật buffer path trong config nhưng PersistentVolume mount vẫn ở đường dẫn cũ; Fluentd ghi buffer vào filesystem container và mất dữ liệu khi pod bị thay thế.
Một nhóm kiểm tra cấu hình bằng fluentd --dry-run thành công nhưng image production thiếu plugin output; lỗi chỉ xuất hiện khi tiến trình khởi động với cấu hình thật.
Fluentd đang chạy hai process do entrypoint khởi động supervisor sai; cả hai cùng tail file và forward event, gây duplicate logs và cạnh tranh position file.
Đội muốn drain node trước khi bảo trì nhưng Fluentd chưa flush hết buffer; DaemonSet bị terminate sau grace period và chunk chưa gửi bị bỏ lại trên volume cũ.
Ứng dụng tạo log multiline với JSON object pretty-printed; parser JSON mỗi dòng không thể đọc độc lập và concat rule không nhận biết dấu ngoặc lồng nhau.
Nhóm dùng parser regexp để lấy timestamp và message từ log có stack trace; dòng continuation bị ghép vào message nhưng dấu newline bị mất, làm stack trace không thể copy để tái hiện.
Log nginx có escaped quote trong user agent và query string; parser CSV tùy chỉnh không xử lý escape đúng và các cột phía sau bị dịch vị trí.
Một ứng dụng ghi dấu phẩy thập phân trong trường duration theo locale; parser numeric mặc định dùng dấu chấm và chuyển giá trị thành chuỗi, khiến dashboard tính trung bình sai.
Fluentd parser nhận timestamp không có timezone từ nhiều node đặt timezone khác nhau; cùng một format log được diễn giải thành những thời điểm khác nhau.
Đội dùng filter record_transformer để chuyển status string thành integer nhưng không xử lý giá trị '-' của access log; plugin báo lỗi type conversion và record không được route như dự kiến.
Một parser gán event time từ trường created_at của nghiệp vụ thay vì timestamp log; event được phát sinh hôm nay nhưng dữ liệu giao dịch cũ làm log bị ghi vào cửa sổ lưu trữ lịch sử.
Ứng dụng ghi log có trường message là mảng object khi lỗi validation; parser downstream kỳ vọng string và output Elasticsearch từ chối mapping của một số event.
Fluentd route security log theo tag audit.**, nhưng input syslog tạo tag syslog.security; sự kiện đăng nhập thất bại được gửi vào index application chung.
Nhóm dùng rewrite tag để tách log theo level; giá trị severity có thể là WARN, WARNING hoặc warn từ các nguồn khác nhau và một số event rơi vào route mặc định.
Fluentd nhận log từ nhiều namespace có cùng tên service; tag chỉ chứa service name và các record bị trộn, không thể áp dụng retention khác nhau theo namespace.
Output Elasticsearch dùng index theo tag nhưng tag có ký tự viết hoa và dấu cách từ tên ứng dụng; index name không hợp lệ và chunk retry mãi.
Nhóm route event tới Kafka theo tag chứa tenant; một tenant mới có dấu gạch chéo trong ID làm tên topic không hợp lệ và riêng log tenant đó không được xuất.
Fluentd dùng match ** để forward mọi tag tới aggregator, đồng thời có match cụ thể ghi file cục bộ; do thứ tự match, event chỉ đi một nhánh dù nhóm mong muốn copy sang cả hai.
Đội thêm secondary output để lưu file khi Elasticsearch lỗi; secondary chỉ được gọi sau lỗi retry cuối cùng và không phù hợp yêu cầu lưu song song audit event ngay khi nhận.
Một output Elasticsearch bulk trả HTTP 200 nhưng một số item trong response có status 400 do mapping conflict; plugin không tách item lỗi theo cấu hình hiện tại và chunk bị xem như gửi thành công.
Output Kafka xác nhận broker nhận message nhưng consumer group xử lý chậm; đội chỉ nhìn output success của Fluentd nên không phát hiện dữ liệu đang tồn đọng ở downstream.
Fluentd gửi dữ liệu sang OpenSearch với index template mới; dynamic mapping nhận trường duration lúc là số lúc là chuỗi, khiến các batch sau bị từ chối do type conflict.
Nhóm dùng output HTTP gửi NDJSON tới endpoint nhận một JSON object mỗi request; endpoint phản hồi 400 và retry liên tục vì định dạng body không phù hợp.
Fluentd output tới S3 dùng buffer timekey nhưng timezone chunk key không khớp lịch partition của data lake; dữ liệu xuất hiện ở thư mục ngày khác với báo cáo nghiệp vụ.
Output file dùng permission mặc định quá rộng trên host; log có email và thông tin thanh toán được ghi vào thư mục mà nhiều tài khoản hệ điều hành đọc được.
Đội bật gzip output nhưng không đặt Content-Encoding ở HTTP plugin; server nhận payload nén như văn bản và báo JSON parse error.
Fluentd output HTTP có timeout 5 giây, còn API nhận log cần 8 giây để xử lý batch lớn; mọi request vượt thời gian bị retry dù server đã ghi nhận dữ liệu.
Đội triển khai aggregator mới và cập nhật DNS; agent giữ kết nối TCP cũ tới IP aggregator đã ngừng hoạt động và chỉ chuyển endpoint sau nhiều lần retry.
Fluentd aggregator có số worker thấp hơn agent gửi vào; hàng đợi accept và CPU tăng, còn output Elasticsearch vẫn chưa đạt giới hạn ingest.
Trong giờ cao điểm, số event nhận vào tăng từ 20.000 lên 100.000 mỗi giây nhưng buffer queue chỉ giảm chậm; nhóm chưa tính tốc độ output bền vững và thời gian cần để xả backlog.
Fluentd có buffer queue tăng nhưng chunk bytes không tăng; nhiều chunk nhỏ đang chờ do flush thread thiếu tài nguyên và dashboard chỉ cảnh báo dung lượng buffer.
Một bộ lọc parser chuyển log thành record lớn gấp năm do giữ cả raw message và bản parsed; dung lượng buffer và băng thông output tăng sau khi bật parse.
Đội đặt flush_thread_count quá cao cho output chậm; nhiều request bulk đồng thời khiến Elasticsearch thread pool reject và Fluentd bước vào vòng retry.
Fluentd chạy trên node có CPU throttling cao; parser regexp phức tạp làm thời gian xử lý mỗi record tăng và log tới backend chậm hơn dù output khỏe.
Một nhóm giảm số worker để tránh CPU spike nhưng input forward không đọc kịp socket; kernel receive queue đầy và agent gửi nhận timeout.
Agent Fluentd ghi buffer vào ổ đĩa local nhưng disk pressure khiến kubelet eviction pod; chunk chưa flush mất theo pod và log của workload trên node có khoảng trống.
Nhóm đo end-to-end lag bằng thời điểm ingest trừ timestamp event, nhưng một số máy nguồn lệch NTP 4 phút; dashboard báo độ trễ âm và che khuất backlog thực tế.
Fluentd buffer retry tăng theo từng giờ nhưng alert chỉ kích hoạt khi process DOWN; pipeline có thể chậm nhiều giờ trước khi người dùng nhận thấy thiếu log.
Một sự cố mất log được điều tra bằng cách so số event ở ứng dụng và Elasticsearch; ứng dụng đếm mỗi lần log, còn Elasticsearch đếm document sau dedup theo event_id, khiến phép đối chiếu không cùng định nghĩa.
Nhóm triển khai Fluentd với file buffer nhưng không bật persistent volume trong môi trường staging; test pod restart luôn xanh vì dữ liệu thử ít, còn production mất chunk khi node drain.
Đội thay đổi retention index Elasticsearch từ 30 ngày xuống 7 ngày để giảm chi phí nhưng không thay đổi archive S3; người dùng vẫn truy vấn log cũ từ S3 qua đường khác và chính sách lưu giữ không nhất quán.
Một pipeline mới lọc bỏ access log 2xx trước khi xuất; số event giảm 90% nhưng không còn mẫu request thành công để so sánh khi điều tra lỗi chỉ xảy ra với một nhóm khách.
Nhóm kiểm thử buffer bằng cách tắt Elasticsearch trong 2 phút; thử nghiệm không đủ dài để làm đầy queue và không phát hiện cấu hình overflow sẽ drop chunk khi outage kéo dài một giờ.
Đội đánh giá độ bền dữ liệu bằng việc Fluentd process không restart trong load test; bài test không mô phỏng node mất điện, volume detach hoặc pod bị kill khi đang ghi chunk.
Trong một incident, on-call tạm tắt filter parser để Fluentd bắt kịp lưu lượng; raw logs được gửi tới kho bên ngoài mà chưa mask token, tạo sự cố bảo mật thứ cấp.
Fluentd chỉ log lỗi plugin ở stderr, còn collector sidecar thu thập stdout; các lỗi output và retry không được đưa vào dashboard giám sát pipeline.
Nhóm đặt log Fluentd ở mức debug trong giờ cao điểm; log nội bộ về từng chunk và từng retry làm tăng I/O trên chính node đang có buffer pressure.
Đội nâng cấp Fluentd từ phiên bản cũ nhưng một plugin concat không còn tương thích với parser config; pod chạy được nhưng multiline behavior thay đổi và stack trace bị tách.
Một plugin filter tự viết không đóng file handle sau khi đọc dictionary mapping; số open file descriptor tăng dần và Fluentd cuối cùng không mở được file position mới.
Fluentd chạy nhiều worker nhưng plugin output cũ không hỗ trợ multi-worker; các worker tranh chấp client connection và phát sinh lỗi ngẫu nhiên khi flush.
Nhóm dùng một file position duy nhất cho hai input tail cùng trỏ tới file symlink; offset cập nhật bởi input này làm input kia bỏ qua một đoạn log.
Ứng dụng ghi event ID nhưng Fluentd filter xóa event_id trước khi output; khi retry gây duplicate, hệ thống downstream không còn khóa để loại bản ghi trùng.
Một output forward dùng at-least-once delivery; sau khi aggregator nhận chunk và crash trước khi gửi ACK, agent retry và downstream nhận trùng event dù không có packet loss.
Fluentd được cấu hình lưu buffer trên NFS dùng chung cho hai pod active-active; locking không phù hợp khiến metadata chunk không nhất quán và dữ liệu có thể bị gửi hai lần.
Nhóm muốn chuyển Fluentd từ DaemonSet sang sidecar để giảm quyền đọc host log; cấu hình mới chỉ thu được log của một container trong pod và bỏ mất log sidecar nghiệp vụ khác.
Một ứng dụng có log audit cần gửi đồng bộ trước khi trả response; Fluentd chỉ nhận log bất đồng bộ qua stdout và process có thể kết thúc trước khi agent đọc hết buffer runtime.
Đội đặt parser multi_format với regex đầu tiên bắt cả JSON string; record JSON không còn được parse theo cấu trúc và các filter theo trường severity hoặc request_id thất bại.
Một file log có UTF-8 không hợp lệ sau khi ứng dụng ghi binary payload vào message; parser dừng ở ký tự lỗi và event không được chuyển sang output error riêng.
Fluentd nhận log có timestamp trước năm 1970 do ứng dụng gửi giá trị epoch microseconds nhưng parser hiểu milliseconds; hệ thống retention xóa dữ liệu ngay vì thời điểm bị coi là quá cũ.
Nhóm route log theo trường namespace nhưng filter Kubernetes metadata chỉ bổ sung namespace sau route stage; event đi nhầm output mặc định trước khi metadata được thêm.
Trong đợt deploy rolling, pod cũ và mới ghi hai schema log khác nhau; Fluentd parser chỉ hỗ trợ schema mới nên log của pod cũ tăng parse error tới khi rollout hoàn tất.
Fluentd nhận log từ container có tag chứa dấu chấm và slash; rule match wildcard bị diễn giải khác kỳ vọng nên một phần event không tới output chính.
Một nhóm dùng filter grep để bỏ trường health=true, nhưng ứng dụng ghi giá trị boolean ở phiên bản mới và string 'true' ở phiên bản cũ; kết quả lọc khác nhau giữa các pod.
Nhóm dùng filter record_transformer với enable_ruby để tạo field normalized_message; biểu thức Ruby có lỗi khi message nil và record không đi tiếp tới output như dự định.
Fluentd parser regex bắt trường duration nhưng không neo cuối dòng; chuỗi request có suffix mới khiến duration lấy nhầm con số ở cuối message.
Output Elasticsearch có index lifecycle theo ngày, nhưng Fluentd dùng UTC trong index name còn Kibana filter theo timezone địa phương; dashboard một số bản ghi như nằm ở ngày trước.
Nhóm gửi log multiline từ Java vào Kafka bằng JSON; serializer escape newline hai lần và consumer hiển thị ký tự \n thay vì stack trace nhiều dòng.
Fluentd dùng tag per-file để phân loại audit, nhưng file path chứa tên tenant do người dùng đặt; một tenant có thể tạo tag ngoài quy ước và đi vào index sai.
Đội bật buffer compression nhưng không kiểm tra CPU khi giải nén ở aggregator; agent nhẹ hơn còn aggregator trở thành nút nghẽn và backlog tập trung ở một vùng.
Fluentd có buffer file và output S3, nhưng quyền IAM hết hạn khi flush chunk; retry tiếp tục dùng credential cũ và queue không được giải phóng sau khi IAM đã cấp quyền mới cho pod khác.
Nhóm thiết lập retry_forever và lưu chunk trên volume có quota; khi outage kéo dài, quota đầy và Fluentd không thể ghi chunk mới dù chính sách retry vẫn giữ dữ liệu cũ.
Một output HTTP trả 413 khi chunk vượt giới hạn request body; Fluentd retry cùng chunk không thay đổi kích thước nên backlog không bao giờ được giải phóng.
Fluentd dùng chunk key theo tag và time nhưng output yêu cầu thêm tenant; khi tenant key không được khai báo trong buffer chunk keys, event từ nhiều tenant bị gom vào cùng chunk và không thể route đúng.
Đội bật overflow_action=drop_oldest_chunk nhưng alert chỉ theo retry_count; dữ liệu cũ bị loại có chủ đích và pipeline vẫn hiển thị hoạt động bình thường.
Fluentd flush thread bị block khi DNS output không phân giải được; input queue tiếp tục nhận dữ liệu cho đến khi buffer đầy và pod bị restart do memory pressure.
Một node có thời gian hệ thống nhảy lùi sau đồng bộ NTP; file buffer timekey mở lại chunk cũ và output tạo object key trùng, ghi đè log đã flush trước đó.
Nhóm dùng source forward với ack_response_timeout ngắn hơn thời gian flush ở aggregator; agent retry chunk dù aggregator cuối cùng đã ghi xong, tạo duplicate trong output.
Fluentd nhận sự kiện qua TCP input nhưng producer đóng kết nối ngay sau khi gửi mà không chờ xác nhận; một số record cuối chưa được xử lý khi agent bị restart.
Đội chuyển output từ Elasticsearch sang OpenSearch nhưng plugin vẫn dùng bulk API response parsing không tương thích; request trả HTTP 200 nhưng item failures không được phát hiện.
Một hệ thống dùng Fluentd để thu thập audit log từ node, nhưng agent chạy bằng user không có quyền đọc file auth.log; chỉ application logs được thu thập và đội an ninh không nhận biết thiếu nguồn.
Fluentd nhận container stdout từ nhiều ứng dụng, nhưng không có field source_type; downstream không phân biệt audit, application và access log để áp dụng retention khác nhau.
Một pipeline chuẩn hóa timestamp, severity và service nhưng xóa hostname gốc; sau khi một node bị cấu hình sai, nhóm không thể xác định event phát sinh từ máy nào.
Đội triển khai parser mới và filter xóa raw log ngay sau parse; một số record parse sai không còn bản gốc để debug và không thể viết lại parser dựa trên dữ liệu thực tế.
Một nhóm kiểm tra log completeness bằng số dòng input và output trong cùng phút; backlog đang tăng khiến output trễ 20 phút nhưng hai bộ đếm cùng tăng và phép so sánh không phát hiện lag.
Fluentd nhận log từ ứng dụng qua stdout và systemd journal; cùng một service được cấu hình hai input cho cùng sự kiện, dẫn đến mỗi event xuất hiện hai lần trong backend.
Trong sự cố storage, nhóm chỉ kiểm tra Fluentd log error nhưng không đối chiếu chunk state và retry state; hàng đợi đã bị kẹt ở một output cụ thể trong khi các output khác vẫn flush bình thường.
Một collector trung tâm phục vụ nhiều cluster; một cluster gửi lượng log debug quá lớn và chiếm buffer shared, làm log audit từ cluster khác bị chậm dù nguồn gửi vẫn bình thường.
Fluentd dùng label @ERROR để nhận record parse lỗi nhưng không cấu hình output cho label này; số parse error tăng mà không có dữ liệu để xác định mẫu lỗi và nguồn.
Một pipeline lọc log có trường status_code 2xx để giảm chi phí; các response 200 chứa lỗi nghiệp vụ không được giữ và báo cáo vận hành đánh giá sai tỷ lệ thành công.
Đội bật compression gzip trên output HTTP nhưng backend mong Content-Encoding zstd; response 415 xuất hiện và buffer retry liên tục dù network kết nối bình thường.
Fluentd chạy trong môi trường FIPS nhưng plugin TLS dùng cipher suite không được phép; kết nối output thất bại trong production còn staging không bật FIPS nên không tái hiện được.
Nhóm route log theo tag 'prod' nhưng một nguồn gửi tag 'production'; sự kiện của workload mới đi vào output mặc định có retention ngắn hơn.
Fluentd được nâng cấp plugin parser và thay đổi default time_key; timestamp của log cũ không còn được sử dụng, khiến dashboard sắp xếp theo ingest time thay vì event time.
Một output Elasticsearch yêu cầu document_id ổn định để chống duplicate nhưng Fluentd không chuyển event ID từ record; retry sau timeout tạo nhiều document cho cùng một sự kiện.
Nhóm dùng event time làm document ID, nhưng nhiều log hợp lệ của cùng service được ghi trong cùng millisecond; document sau ghi đè document trước và số lượng event giảm bất thường.
Fluentd buffer queue tăng sau khi output Kafka gặp lỗi authentication; nhóm chỉ kiểm tra reachability của broker và không nhận ra credential SASL đã bị rotate.
Ứng dụng ghi log vào stdout nhưng kubelet log rotation đặt giới hạn file nhỏ; Fluentd poll chậm hơn tốc độ rotation và các file cũ bị xóa trước khi agent đọc hết.
Đội muốn kiểm chứng không mất log khi nâng cấp node; thử nghiệm chỉ restart pod Fluentd mà không drain workload, không kiểm tra vị trí file và không so event ID đầu/cuối.
Trong một đợt tăng tải, Fluentd process còn sống nhưng input plugin bị treo do thread lock; health check chỉ kiểm tra PID nên không phát hiện event rate đầu vào đã về 0.
Nhóm thay đổi parser và filter trong cùng một lần deploy; sau khi lỗi parse tăng, không thể xác định phần nào gây ra vì không có canary config hoặc số liệu baseline riêng.
Fluentd được cấu hình nhận log từ nhiều ứng dụng nhưng output dùng một buffer queue duy nhất; một index đích lỗi mapping làm queue chung chặn cả log của các ứng dụng không liên quan.
Đội đặt retry_max_interval dài và retry_forever cho output quan trọng, nhưng không có cảnh báo thời gian chunk oldest; log quan trọng có thể bị giữ nhiều giờ mà không ai nhận ra.
Fluentd forward dùng TLS và shared key nhưng không giới hạn IP nguồn; một host lạ trong mạng nội bộ gửi lượng lớn event giả làm đầy buffer của aggregator.
Một plugin parser ghi raw record vào log nội bộ khi parse thất bại; record chứa access token được in ra stderr và collector log được gửi tới một kho ít bảo vệ hơn.
Đội giảm log bằng cách bỏ mọi request có path /metrics; endpoint metrics cũng nhận POST cấu hình từ một integration cũ, và sự kiện thay đổi cấu hình bị lọc nhầm.
Một ứng dụng ghi audit event qua Fluentd forward input nhưng input bị rate limit theo tag chung với access logs; trong đợt traffic cao, audit event bị từ chối cùng các log không quan trọng.
Nhóm thiết kế pipeline có output audit riêng nhưng filter trước đó loại các record thiếu request_id; một số thao tác hệ thống hợp lệ không có request_id và mất khỏi kho audit.
Fluentd tail input đọc file có inode tái sử dụng sau khi filesystem khôi phục; position file nhận nhầm file mới là file đã đọc và bỏ qua log đầu tiên của ứng dụng.
Một node reboot bất ngờ khi Fluentd đang flush chunk; output nhận một phần request nhưng không có ACK cuối, sau khởi động lại chunk được gửi lại và downstream xuất hiện bản ghi trùng.
Đội triển khai nhiều aggregator Fluentd sau load balancer nhưng sticky session theo source IP khiến một aggregator nhận phần lớn agent NAT chung; buffer tại node đó đầy trong khi các node khác nhàn rỗi.
Fluentd có output S3 partition theo namespace, nhưng filter Kubernetes metadata không bổ sung namespace cho log systemd; các bản ghi hạ tầng được ghi vào prefix default và khó áp retention.
Một nhóm muốn dùng Fluentd để chuẩn hóa OpenTelemetry log record; mapping timestamp, severity_text và resource attributes không đầy đủ khiến backend không phân biệt được resource metadata với record attributes.
Fluentd gửi logs sang backend qua OTLP bridge nhưng trường trace_id bị ghi hoa chữ; backend yêu cầu định dạng hex chuẩn lowercase và không liên kết được log với trace.
Ứng dụng log một exception có trace_id trong MDC, nhưng Fluentd parser không trích MDC fields khỏi JSON nested; log vẫn tới backend nhưng correlation với trace bị mất.
Đội vận hành muốn giảm độ trễ pipeline xuống dưới 5 giây; flush_interval đặt 1 giây nhưng buffer queue time tăng 10 phút do output throttling và nhóm chưa theo dõi chunk age.
Fluentd dùng output buffered nhưng không bật retry status cho HTTP 429; backend rate limit trả 429, plugin xem là lỗi không retryable và chunk bị loại.
Một nhóm bật retry cho tất cả HTTP 4xx; lỗi cấu hình 400 không thể tự hồi phục nhưng chunk cứ retry đến khi buffer đầy, làm chậm toàn bộ pipeline.
Fluentd nhận syslog có hostname rỗng và dùng giá trị default 'unknown'; nhiều thiết bị bị gộp thành một nguồn, làm việc điều tra thiết bị gửi log bất thường khó khăn.
Nhóm dùng filter record_transformer để chuyển severity thành số, nhưng mapping không bao phủ CRITICAL và NOTICE; hai mức này được chuyển thành 0 và lọt qua filter bỏ log debug.
Một ứng dụng ghi request ID dạng UUID có chữ hoa, còn Fluentd normalize thành chữ thường; downstream audit lookup phân biệt chuỗi theo nguyên bản và không tìm thấy event liên quan.
Trong quá trình nâng cấp Fluentd, file buffer được giữ nguyên nhưng plugin output đổi định dạng metadata chunk; pod mới không đọc được chunk cũ và dữ liệu chưa flush cần quy trình phục hồi.
Nhóm triển khai file buffer trên hostPath nhưng thư mục bị xóa khi node được reprovision; Fluentd khởi động mới bình thường và không có dấu hiệu cấu hình lỗi dù backlog cũ đã mất.
Đội kiểm tra throughput bằng số event mỗi giây nhưng mỗi event production có kích thước trung bình lớn hơn dữ liệu benchmark 20 lần; buffer và network saturate ở tải thấp hơn kết quả thử.
Fluentd có nhiều input plugin nhưng chỉ một output worker xử lý tất cả; nhóm tăng input buffer để nhận nhiều hơn nhưng latency và memory tăng vì năng lực output không đổi.
Một bộ lọc chuyển message sang lowercase để chuẩn hóa tìm kiếm; dữ liệu JSON có case-sensitive identifier bị thay đổi và hệ thống downstream không ghép được mã giao dịch.
Ứng dụng ghi log multiline có hai exception lồng nhau; concat parser chỉ nhận một pattern đầu dòng nên phần exception thứ hai bị gắn vào stack trace đầu và gây nhầm nguyên nhân.
Fluentd dùng parser JSON nhưng một trường message chứa JSON lồng được escape hai lần; downstream filter cần parse lần thứ hai nhưng pipeline chỉ parse một lớp và không tìm được error_code.
Nhóm triển khai pipeline Fluentd mới với tag routing và buffer tách theo tenant; số file chunk tăng vượt giới hạn inode của volume dù dung lượng byte còn trống.
Một node có hàng trăm nghìn file chunk nhỏ do timekey quá ngắn và tag quá đa dạng; filesystem hết inode trước khi đầy dung lượng, Fluentd không thể tạo file buffer mới.
Đội thiết lập output flush_at_shutdown nhưng Kubernetes terminationGracePeriodSeconds ngắn hơn thời gian flush backlog; pod bị SIGKILL trước khi gửi xong chunk cuối.
Fluentd có buffer queue và retry tăng sau khi backend chậm, nhưng ứng dụng upstream không có backpressure; log tiếp tục sinh nhanh hơn khả năng lưu trữ và cuối cùng input bị drop.
Nhóm so sánh số record được parser thành công với số document ở Elasticsearch; filter loại event theo policy và output retry tạo duplicate, nên chênh lệch không thể diễn giải nếu không tách drop, retry và dedup.
