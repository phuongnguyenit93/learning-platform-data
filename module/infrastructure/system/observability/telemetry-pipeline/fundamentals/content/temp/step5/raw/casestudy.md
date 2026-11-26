Một công ty thu thập metrics, logs và traces từ hàng trăm microservice nhưng mỗi nhóm tự gửi dữ liệu trực tiếp tới ba backend quan sát khác nhau; khi một endpoint thay đổi, phải sửa cấu hình ở nhiều ứng dụng và nhóm nền tảng muốn tập trung luồng telemetry qua một pipeline dùng chung.
Một doanh nghiệp triển khai OpenTelemetry Collector dạng agent trên từng node Kubernetes và gateway tập trung ở vùng mạng riêng; một số service gửi trực tiếp tới gateway, số khác đi qua agent, khiến dữ liệu cùng service bị trùng và khó xác định nguồn phát.
Đội vận hành chuyển từ collector sidecar sang DaemonSet agent để giảm số container trên mỗi pod; các workload dùng host network và đường log riêng không còn được thu thập như trước, buộc nhóm phải đánh giá phạm vi quan sát của mô hình agent.
Một cluster có hàng nghìn pod ngắn hạn và cần thu thập cả stdout lẫn host metrics; collector dạng sidecar bị tạo quá nhiều replica, làm chi phí CPU tăng mạnh so với mô hình agent chạy trên node.
Nền tảng có nhiều cluster Kubernetes ở các vùng khác nhau và muốn dùng gateway collector tập trung; lưu lượng telemetry liên vùng làm tăng độ trễ, băng thông và phụ thuộc vào kết nối mạng giữa các vùng.
Một doanh nghiệp triển khai gateway collector theo mô hình active-active nhưng client chỉ cấu hình một endpoint cố định; khi gateway đó ngừng hoạt động, dữ liệu không tự chuyển sang gateway còn lại dù cụm dự phòng vẫn khỏe.
Đội SRE triển khai nhiều agent collector nhưng các agent cùng gửi đến một gateway có giới hạn tài nguyên; giờ cao điểm tạo nút thắt ở gateway và toàn bộ pipeline có độ trễ cao dù các node agent vẫn hoạt động bình thường.
Một tổ chức đặt gateway collector ở namespace observability nhưng NetworkPolicy chỉ cho phép một số namespace gửi dữ liệu; các service mới không được thêm vào danh sách và metrics vẫn có tại ứng dụng nhưng không tới backend.
Một hệ thống sử dụng OpenTelemetry Collector với nhiều receiver cho OTLP, Prometheus scrape và file log; một cấu hình receiver bị trùng port khiến collector không khởi động, làm gián đoạn cả ba loại telemetry.
Nhóm nền tảng thay đổi cổng OTLP từ 4317 sang 4318 nhưng chỉ cập nhật exporter HTTP ở một số service; các client gRPC tiếp tục gửi tới cổng cũ và dữ liệu traces bị mất sau triển khai.
Một ứng dụng Java gửi telemetry bằng OTLP gRPC tới collector, nhưng ingress chỉ cho phép HTTP/1.1 và không hỗ trợ HTTP/2 tới upstream; kết nối từ ứng dụng thất bại dù health check của collector trả thành công.
Một công ty có ứng dụng legacy chỉ xuất Prometheus exposition và log file; nhóm observability cần dùng collector để tiếp nhận các định dạng khác nhau rồi chuẩn hóa trước khi gửi tới backend thống nhất.
Một service dùng Prometheus scrape trực tiếp trong khi các service khác push metrics qua OTLP; khi chuyển backend, cấu hình scrape target không được cập nhật cùng exporter và số liệu của service cũ không xuất hiện ở hệ mới.
Một đội triển khai receiver đọc file log trên node nhưng container collector không được mount đúng đường dẫn /var/log/pods; receiver vẫn chạy mà không thu được bản ghi nào từ workload Kubernetes.
Một hệ thống nhận telemetry từ máy ảo on-premises và cluster cloud qua gateway; DNS nội bộ của một site phân giải hostname gateway sang IP cũ, khiến dữ liệu từ site đó bị ngắt quãng sau lần di chuyển.
Một collector nhận traces qua OTLP và logs qua filelog receiver nhưng pipeline chỉ khai báo exporter cho traces; logs được đọc khỏi nguồn nhưng không được chuyển tới backend, khiến nhóm cần kiểm tra đầy đủ đường đi từng signal.
Một đội khai báo cùng một receiver component trong nhiều pipeline nhưng không kiểm tra các pipeline signal được nối với exporter nào; metrics được tiếp nhận thành công nhưng đi vào backend khác với dự định.
Một tổ chức nâng cấp OpenTelemetry Collector và đổi tên một component trong cấu hình; binary mới không còn nhận component cũ, khiến service khởi động thất bại và pipeline mất dữ liệu trong thời gian rollout.
Một collector gateway dùng cấu hình chung cho nhiều cluster nhưng một cluster cần receiver riêng để đọc log audit; cấu hình chung không có receiver đó nên dữ liệu audit không được tiếp nhận dù agent vẫn gửi metrics.
Đội vận hành chạy collector dưới user không có quyền đọc socket container runtime; receiver container logs báo lỗi quyền và các log mới không được thu thập dù pod collector đang Ready.
Một pipeline tiếp nhận metrics từ nhiều ứng dụng có quy ước tên khác nhau; backend nhận request_count, requests_total và http_requests cùng biểu diễn một khái niệm, khiến dashboard tổng hợp và cảnh báo bị phân mảnh.
Nhóm phát triển chuyển các metric Java từ đơn vị mili giây sang giây nhưng pipeline không chuẩn hóa đơn vị; dashboard gộp dữ liệu hai phiên bản và thể hiện độ trễ sai lệch ba bậc độ lớn.
Một service gửi metric latency dạng gauge trong khi backend kỳ vọng histogram để tính percentile; pipeline không thể khôi phục phân phối từ các giá trị đơn lẻ và p95 toàn dịch vụ không còn đáng tin.
Đội observability chuẩn hóa tên service trong collector nhưng một số ứng dụng dùng tên deployment, một số dùng service catalog; các trace, logs và metrics không thể liên kết bằng cùng thuộc tính resource.
Một doanh nghiệp bổ sung resource attributes cluster, namespace, service.name và deployment.environment ở gateway; agent cũng thêm các thuộc tính cùng tên nhưng giá trị khác, làm pipeline cần quy tắc ưu tiên rõ ràng.
Một collector dùng processor transform để đổi tên thuộc tính service.name; một số backend vẫn chờ tên cũ và các dashboard service map mất liên kết sau khi cấu hình được triển khai.
Nền tảng muốn gắn cloud region và owner vào mọi telemetry; dữ liệu từ một số VM không có metadata cloud API nên processor gán giá trị unknown, làm báo cáo phân bổ chi phí sai lệch.
Một nhóm dùng Kubernetes attributes processor để làm giàu dữ liệu bằng pod labels; collector không thể truy cập API server do RBAC thiếu quyền đọc metadata, khiến các log không có namespace và workload như kỳ vọng.
Một cluster có nhiều pod trùng tên giữa namespace; pipeline chỉ enrich theo pod name và gắn nhầm namespace, khiến sự kiện từ staging bị phân loại thành production.
Một ứng dụng đa tenant đưa tenant_id vào resource attributes do client tự gửi; gateway không xác thực giá trị đó trước khi route, khiến telemetry của khách có nguy cơ đi vào tenant backend khác.
Đội nền tảng chuẩn hóa tên metric bằng transform processor nhưng không cập nhật unit và description; hệ thống nhận tên đồng nhất nhưng ý nghĩa các số đo không còn thống nhất giữa service cũ và mới.
Một pipeline nhận timestamp của logs theo RFC3339 nhưng một service gửi Unix milliseconds; parser diễn giải sai thành thời điểm trong tương lai và backend từ chối hoặc sắp xếp sai bản ghi.
Một collector đọc log JSON có trường nested và chuyển một số thuộc tính thành resource attributes; dữ liệu thay đổi theo từng request bị đưa lên resource, làm cardinality tăng và log của cùng process bị chia thành nhiều nhóm.
Một nhóm chuyển các trường request_id và trace_id thành thuộc tính chung để liên kết signals; processor gán chúng vào resource thay vì record, khiến mỗi request trở thành một resource riêng và làm tăng kích thước dữ liệu.
Một pipeline cần chuẩn hóa status code HTTP từ chuỗi thành số để tạo metric; transform rule chỉ xử lý mã ba chữ số và bỏ qua các trường hợp không có status, khiến một phần request không được tính.
Một service Java ghi exception message chứa mã khách hàng và email; processor chỉ xóa trường user.email dạng JSON nhưng không làm sạch nội dung log tự do, khiến dữ liệu cá nhân vẫn đi qua pipeline.
Đội bảo mật yêu cầu loại Authorization header và cookie khỏi traces trước khi xuất; pipeline logs đã có processor redaction nhưng pipeline traces chưa được gắn processor tương ứng, nên dữ liệu nhạy cảm vẫn rời collector nguyên vẹn.
Một gateway collector nhận log từ nhiều team và thực hiện redaction chung; một số log audit cần giữ actor ID đã khử định danh nhưng quy tắc hiện tại xóa cả trường này, làm giảm giá trị điều tra.
Một tổ chức cần bỏ các query parameter có token khỏi URL trong spans; processor chỉ che query string ở logs mà không xử lý span attributes, khiến token vẫn xuất hiện trong hệ tracing.
Một ứng dụng có metric label chứa email và IP người dùng; pipeline không có bước loại bỏ hoặc hash trường nhạy cảm nên thông tin định danh bị gửi sang hệ phân tích của nhà cung cấp.
Một nhóm áp dụng filter processor để bỏ health check và debug logs; biểu thức lọc nhận nhầm một số endpoint kiểm tra thanh toán thực tế, khiến sự kiện quan trọng bị loại trước khi đến backend.
Một doanh nghiệp chỉ muốn bỏ metric không cần thiết từ namespace thử nghiệm; điều kiện filter dựa trên cluster name sai chính tả nên dữ liệu production bị loại thay vì staging.
Đội observability dùng transform processor để chuyển mức log ERROR thành severity_number; một số nguồn ghi level=err hoặc fatal nhưng mapping không bao phủ nên dashboard cảnh báo không đếm đầy đủ các lỗi nghiêm trọng.
Một pipeline gom stack trace nhiều dòng thành một log record; quy tắc multiline dựa trên đầu dòng timestamp nhưng message của ứng dụng cũng có timestamp, khiến hai exception liền nhau bị gộp sai.
Một hệ thống nhận traces từ Java và Go với tên span database khác nhau; processor chuẩn hóa operation name quá rộng khiến mọi thao tác đọc/ghi trở thành cùng một span name và mất khả năng phân tích chi tiết.
Một đội thay đổi resource attributes ở gateway để sửa service.name nhưng không kiểm tra tính nhất quán giữa metrics, logs và traces; chỉ traces được cập nhật còn logs và metrics vẫn mang tên service cũ.
Một collector enrich telemetry bằng metadata từ cloud API ở mỗi record; khi số lượng log tăng cao, mỗi event tạo thêm truy vấn metadata và làm gateway quá tải dù lượng dữ liệu gốc ổn định.
Nền tảng cần gắn owner từ service catalog nhưng gateway không thể truy cập catalog trong giờ triển khai; processor chờ đồng bộ và làm chậm luồng telemetry của tất cả service.
Một nhóm sử dụng batch processor để gom telemetry trước khi export nhưng đặt batch size quá nhỏ; số request outbound tăng cao, làm backend tốn tài nguyên xử lý dù tổng lượng dữ liệu không lớn.
Một collector có batch timeout dài để tối ưu số request gửi đi; khi traffic thấp, log quan trọng phải chờ lâu mới xuất hiện trên dashboard và người trực tưởng dữ liệu đã mất.
Đội vận hành tăng batch size cho traces nhưng exporter backend có giới hạn kích thước request; các batch lớn bị từ chối và collector retry khiến độ trễ ingest tăng thêm.
Một gateway xử lý metrics, logs và traces chung một pipeline; batch size phù hợp cho logs lớn lại khiến metrics độ trễ thấp bị chờ, làm dashboard cập nhật chậm hơn SLO.
Một doanh nghiệp dùng memory_limiter processor nhưng đặt limit cao hơn giới hạn container; collector bị OOMKilled trước khi processor kịp từ chối dữ liệu và pipeline ngừng gửi telemetry.
Nhóm SRE đặt memory_limiter quá thấp so với tải bình thường; collector liên tục từ chối spans và logs dù node còn bộ nhớ trống, khiến tỷ lệ drop tăng không cần thiết.
Một pipeline dùng sending_queue của exporter nhưng queue không có persistent storage; khi collector restart, dữ liệu đang chờ gửi bị mất và nhóm vận hành không có bằng chứng để phân biệt lỗi nguồn với lỗi pipeline.
Một tổ chức bật file storage extension để lưu queue qua restart nhưng volume bị giới hạn dung lượng; sau sự cố backend kéo dài, queue đầy và collector không thể ghi thêm dữ liệu tạm.
Đội nền tảng cấu hình exporter retry với thời gian tối đa dài nhưng không đặt giới hạn queue; khi backend đích mất kết nối, backlog tăng liên tục cho tới khi collector hết bộ nhớ.
Một collector gateway có queue retry nhưng endpoint backend trả 400 do schema không hợp lệ; exporter tiếp tục thử lại cùng batch không thể xử lý và giữ chỗ queue dành cho dữ liệu mới.
Một doanh nghiệp dùng exporter sending queue với nhiều consumer để tăng throughput; backend giới hạn request đồng thời nên số lần retry tăng và thời gian giao telemetry kéo dài hơn cấu hình ban đầu.
Một hệ thống có ba backend telemetry và một exporter bị lỗi; collector dùng cùng queue cho tất cả signals nên sự cố ở backend logs làm chậm cả metrics và traces không liên quan.
Đội SRE đặt retry_on_failure cho exporter nhưng không theo dõi số lần retry; dữ liệu vẫn đến cuối cùng song độ trễ ingest tăng hàng chục phút mà dashboard pipeline không báo động.
Một gateway có bộ đệm đầy khi kết nối mạng liên vùng bị ngắt; sau khi mạng phục hồi, tốc độ gửi bù thấp hơn tốc độ dữ liệu mới và backlog không bao giờ giảm về 0.
Một ứng dụng gửi telemetry qua UDP tới agent để giảm overhead; trong giờ cao điểm một phần datagram bị mất mà client không nhận lỗi, khiến pipeline thiếu dữ liệu nhưng không có retry ở phía nguồn.
Một hệ thống dùng OTLP gRPC với timeout ngắn ở client; gateway tạm thời chậm và client retry cùng batch, làm dữ liệu duplicate dù collector cuối cùng đã nhận batch đầu.
Một nhóm bật retry ở cả SDK ứng dụng, agent và gateway; một lần backend lỗi tạo retry lồng nhau nhiều tầng, làm tăng lưu lượng đột biến sau khi hệ thống phục hồi.
Một pipeline dùng message broker làm buffer giữa agent và gateway; consumer group bị dừng vài giờ nhưng broker vẫn nhận dữ liệu, đến khi hết retention của topic thì telemetry cũ bị xóa trước khi collector đọc.
Một nền tảng lưu queue telemetry trên Kafka với replication factor phù hợp nhưng producer dùng acks=0 và coi thao tác gửi là thành công ngay; khi broker leader đổi, một số batch chưa được broker xác nhận bị mất sau failover.
Một đội vận hành dùng Kafka làm hàng đợi log và trace nhưng không đặt giới hạn kích thước message; một vài stack trace lớn vượt giới hạn của consumer và partition lag tăng liên tục.
Một hệ thống sử dụng SQS để buffer telemetry nhưng visibility timeout ngắn hơn thời gian exporter xử lý batch; cùng message được nhiều consumer lấy lại và gửi duplicate tới backend.
Một collector nhận dữ liệu từ broker và ghi checkpoint offset trước khi exporter xác nhận thành công; khi backend đích mất kết nối, consumer bỏ qua message đã đọc và làm mất dữ liệu.
Nền tảng đặt checkpoint sau khi gửi thành công nhưng worker crash trước lúc ghi offset; message được xử lý lại khi khởi động và tạo bản ghi telemetry trùng, khiến backend không đảm bảo exactly-once.
Một dịch vụ xử lý batch logs có thứ tự sự kiện quan trọng; khi retry một batch thất bại, các batch mới được gửi trước và dashboard hiển thị thứ tự sự kiện sai so với trình tự nghiệp vụ.
Đội phát triển dùng tail sampling ở gateway để giữ trace có lỗi hoặc latency cao; gateway phải giữ span trong bộ nhớ chờ quyết định và tăng tải mạnh khi hàng triệu trace đồng thời mở.
Một pipeline đặt decision_wait của tail sampler quá ngắn; span cuối của request chưa đến thì trace được quyết định bỏ, khiến những request thực tế lỗi sau đó không còn đầy đủ dữ liệu.
Một nhóm đặt decision_wait quá dài để chờ đủ spans; gateway giữ nhiều trace đang mở và chạm giới hạn bộ nhớ trong giờ cao điểm, buộc collector loại dữ liệu trước khi ra quyết định.
Một hệ thống chia trace qua nhiều gateway replica nhưng các span của cùng trace đến những replica khác nhau; tail sampling quyết định trên dữ liệu không đầy đủ và giữ hoặc bỏ trace sai chính sách.
Đội SRE dùng head sampling ở SDK với tỷ lệ 1% và tail sampling ở gateway để giữ lỗi; các trace không được head sampler gửi đi không thể được tail sampler phục hồi dù sau đó request có lỗi.
Một ứng dụng có luồng giao dịch quan trọng cần giữ 100% traces nhưng sampling rule dựa trên service name cũ; sau khi đổi tên service, các trace mới rơi vào sampling mặc định thấp hơn.
Nền tảng muốn giảm log INFO bằng sampling theo xác suất ở agent; mỗi node dùng seed độc lập và một số nhóm sự kiện liên quan bị lấy mẫu không đồng đều, làm báo cáo tỷ lệ sự kiện khó so sánh.
Một pipeline sample metrics bằng cách bỏ bớt điểm dữ liệu trước khi gửi; counter bị giảm mẫu theo cách không bảo toàn phép tính rate và dashboard hiển thị số request thấp hơn thực tế.
Đội phát triển dùng probabilistic sampling cho logs nhưng không ghi tỷ lệ lấy mẫu vào metadata; người phân tích đếm số dòng và coi đó là tổng số sự kiện thực tế, dẫn đến báo cáo vận hành sai.
Một collector lọc traces theo status code nhưng lỗi nghiệp vụ trả HTTP 200; các trace quan trọng không được giữ dù backend ghi kết quả giao dịch thất bại trong log.
Một nền tảng đặt quy tắc giữ trace chậm trên gateway nhưng service gửi timestamp không đồng bộ; duration tính toán sai và trace nhanh bị coi là chậm, làm tỷ lệ lấy mẫu có lỗi.
Một nhóm chia trace theo tenant để giữ nhiều dữ liệu hơn cho khách VIP; tenant ID do client tự gửi và có thể bị giả mạo, khiến người dùng thường có thể làm tăng lượng trace được giữ.
Một pipeline cần route metrics tới Prometheus, logs tới Loki và traces tới Tempo; cấu hình exporter theo signal bị nối nhầm, làm một phần log được gửi vào endpoint traces và bị từ chối.
Một tổ chức gửi cùng traces tới backend production và hệ phân tích thử nghiệm; khi backend thử nghiệm chậm, pipeline dùng exporter chung và queue khiến đường gửi production cũng bị chậm.
Một gateway có nhiều exporter cho từng tenant; routing processor không có nhánh mặc định cho tenant mới, khiến telemetry của service mới bị drop mà không có cảnh báo rõ ràng.
Một doanh nghiệp dùng routing connector dựa trên resource attribute environment; agent chưa gắn environment cho workload mới và dữ liệu rơi vào exporter mặc định có thời hạn lưu ngắn hơn.
Một service cần gửi audit logs tới kho bảo mật và logs ứng dụng tới kho vận hành; processor phân loại theo severity nhưng một số audit event được ghi ở INFO và đi nhầm backend.
Đội nền tảng thay đổi endpoint exporter của traces nhưng giữ endpoint metrics cũ; sau migration, dashboard hạ tầng vẫn cập nhật trong khi APM không nhận spans và pipeline tổng thể báo Healthy.
Một tổ chức có gateway collector xuất dữ liệu tới hai nhà cung cấp khác nhau để dự phòng; khi cả hai cùng nhận dữ liệu, backend thứ hai tính phí ingest toàn bộ nhưng không có cơ chế xác nhận nhu cầu sao lưu.
Một hệ thống cần định tuyến dữ liệu theo khu vực lưu trữ; gateway dựa trên region tag nhưng tag thiếu hoặc sai khiến một phần telemetry của khách châu Âu đi vào bucket ở vùng khác.
Một pipeline chia dữ liệu theo loại signal và tenant; một nhánh logs gặp lỗi xác thực nhưng nhánh metrics và traces vẫn thành công, dashboard tổng quan chỉ báo collector healthy nên người trực không thấy dữ liệu log đang mất.
Một nhóm triển khai failover exporter sang backend dự phòng khi backend chính không phản hồi; khi chính khôi phục, dữ liệu mới vẫn tiếp tục đi vào dự phòng và các dashboard truy vấn hai nơi không đồng nhất.
Một doanh nghiệp muốn đồng bộ telemetry từ các site bị ngắt mạng sau khi kết nối phục hồi; gateway chỉ lưu buffer trong bộ nhớ và mất toàn bộ dữ liệu tại site khi mất điện trong thời gian offline.
Một ứng dụng đặt địa chỉ gateway cố định trong biến môi trường; sau khi chuyển gateway sang vùng mới, một số pod chưa rollout vẫn gửi tới endpoint cũ và tạo hai luồng dữ liệu song song.
Một tổ chức dùng collector làm điểm kiểm soát egress nhưng firewall cho phép ứng dụng gửi trực tiếp tới backend telemetry công cộng; các service mới bỏ qua pipeline, khiến chính sách redaction và routing không được thực thi.
Đội bảo mật yêu cầu mọi telemetry phải dùng TLS khi truyền; agent tới gateway đã mã hóa nhưng gateway gửi tiếp tới backend qua HTTP trong mạng nội bộ dùng chung, tạo một đoạn truyền không được bảo vệ.
Một gateway yêu cầu mTLS từ agent nhưng certificate của node mới chưa được cấp đúng trust chain; chỉ workload trên node đó mất telemetry và nhóm vận hành phải phân biệt lỗi xác thực với lỗi pipeline.
Một doanh nghiệp xoay client certificate của collector nhưng chỉ cập nhật gateway; các agent dùng chứng chỉ cũ bị từ chối đồng loạt sau thời điểm hết hạn, khiến dữ liệu quan sát bị gián đoạn.
Một hệ thống dùng API key chung cho mọi collector agent; khi một node bị xâm nhập, đội bảo mật không thể thu hồi quyền của riêng node đó mà không ngắt toàn bộ pipeline.
Một nền tảng đa tenant dùng header tenant để định tuyến logs và traces; gateway không kiểm tra header với danh tính client nên một agent có thể ghi telemetry vào tenant khác.
Một nhóm áp dụng redaction cho log message nhưng quên xử lý resource attributes và span events; dữ liệu cá nhân vẫn xuất hiện ở một số loại signal dù pipeline có bước lọc chung.
Một collector có debug logging bật ở production để điều tra lỗi exporter; chính log của collector ghi lại header xác thực và payload nhạy cảm, khiến hệ thống quan sát tự tạo thêm dữ liệu cần bảo vệ.
Đội nền tảng hạn chế quyền truy cập collector config nhưng để endpoint health và pprof công khai trong mạng cluster; thông tin cấu hình và profile tài nguyên có thể bị truy cập từ workload không tin cậy.
Một gateway nhận OTLP từ các workload không xác thực trong mạng nội bộ; một pod bị xâm nhập gửi lượng telemetry khổng lồ và làm đầy queue, ảnh hưởng các service khác dùng chung gateway.
Một pipeline có processor xóa trường password nhưng không xóa bản sao đã được chuyển sang attribute khác ở bước enrichment; dữ liệu nhạy cảm vẫn tồn tại sau transform và được gửi ra backend.
Một doanh nghiệp muốn tuân thủ data residency bằng cách route telemetry theo cloud region; collector gateway nhận request từ nhiều vùng nhưng không xác thực resource region, nên client có thể khai báo sai vị trí dữ liệu.
Một nhóm phát triển thay đổi cấu hình exporter để dùng token mới nhưng quên cập nhật secret ở một số namespace; collector báo lỗi 401 và dữ liệu từ các namespace đó bị gián đoạn trong nhiều giờ.
Một tổ chức cần xác minh nguồn telemetry bằng certificate identity; gateway chỉ ghi source IP và bỏ qua danh tính mTLS, khiến đội điều tra không xác định được agent nào gửi dữ liệu bất thường.
Một pipeline dùng compression gzip cho OTLP để giảm băng thông; gateway proxy giải nén không đúng hoặc giới hạn body thấp, khiến các batch lớn bị trả 413 dù các batch nhỏ vẫn thành công.
Một dịch vụ gửi telemetry qua HTTP proxy có idle timeout ngắn; kết nối keep-alive của exporter bị reset sau thời gian nhàn rỗi và lần gửi đầu tiên sau đó bị lỗi trước khi retry.
Một cluster có gateway collector nằm sau load balancer TCP; load balancer phân phối từng kết nối nhưng các span cùng trace tới nhiều replica, khiến tail sampling không đủ dữ liệu để quyết định.
Đội vận hành đặt timeout exporter ngắn hơn độ trễ bình thường của backend; các batch bị hủy sớm rồi gửi lại, tạo duplicate và làm tăng lưu lượng khi backend đang chậm.
Một pipeline có queue disk-backed để chịu mất kết nối backend nhưng volume chứa queue không được mã hóa; máy chủ bị thu hồi và dữ liệu telemetry nhạy cảm còn lại trên đĩa có thể bị truy cập ngoài ý muốn.
Một doanh nghiệp đặt giới hạn dung lượng buffer theo node nhưng không có cảnh báo mức sử dụng; trong sự cố backend kéo dài, buffer gần đầy và dữ liệu bắt đầu bị drop trước khi nhóm trực nhận ra.
Một gateway dùng persistent queue trên PVC nhưng pod mới được gắn vào volume khác sau khi reschedule; collector khởi động với queue rỗng và dữ liệu đang chờ từ pod cũ không được tiếp tục gửi.
Một nhóm cấu hình retry vô hạn để không mất telemetry; backend đích đã từ chối schema cũ vĩnh viễn, khiến queue đầy và dữ liệu mới bị chặn sau nhiều giờ.
Một hệ thống nhận lỗi 429 từ backend do rate limit nhưng exporter retry ngay không có backoff; số request tăng nhanh và tình trạng quá tải kéo dài sau khi giới hạn đã được nới.
Một collector gateway sử dụng memory_limiter nhưng không có giới hạn số record mỗi batch; một batch log lớn chiếm bộ nhớ đột biến trước khi processor có cơ hội giảm tải.
Đội SRE bật backpressure ở agent để giảm tải gateway nhưng ứng dụng gửi OTLP đồng bộ trong đường xử lý request; khi collector chậm, latency nghiệp vụ tăng và khách hàng bị ảnh hưởng.
Một ứng dụng Java dùng exporter batch trong SDK và collector cũng có queue retry; khi backend ngừng hoạt động, cả hai tầng tích lũy dữ liệu và retry cùng lúc khiến bộ nhớ ở ứng dụng lẫn gateway tăng.
Một nền tảng có gateway collector dùng chung cho logs, metrics và traces; khi trace sampling giữ quá nhiều span, tài nguyên bị chiếm và log audit bắt đầu bị drop dù có mức độ quan trọng cao hơn.
Một hệ thống đặt giới hạn tốc độ ingest chung cho mọi tenant; tenant phát log bất thường chiếm toàn bộ quota và làm mất metrics của các dịch vụ thanh toán quan trọng.
Một công ty phân bổ quota theo namespace nhưng collector gateway chỉ nhận biết cluster; một namespace thử nghiệm gửi nhiều dữ liệu và ảnh hưởng các nhóm production cùng cluster.
Đội vận hành thấy backend nhận ít log hơn số dòng ứng dụng phát ra; không có metric về accepted, refused, dropped và retried record tại từng hop nên không xác định được dữ liệu mất ở đâu.
Một collector tự xuất metric về số request exporter thành công nhưng không đo độ trễ từ event source đến backend; dữ liệu đến muộn nhiều phút mà dashboard pipeline vẫn hiển thị tỷ lệ gửi thành công 100%.
Một nhóm theo dõi CPU và RAM của collector nhưng không theo dõi queue length, send failures và refused spans; gateway có tài nguyên dư nhưng backend từ chối dữ liệu liên tục mà không có cảnh báo.
Nền tảng có nhiều agent và gateway nhưng chỉ kiểm tra health endpoint trả 200; receiver vẫn nhận dữ liệu trong khi exporter không thể gửi tới backend, khiến health check không phản ánh chức năng đầu cuối.
Một đội observability xây synthetic telemetry canary đi qua agent, gateway và backend mỗi phút; sau nâng cấp, canary biến mất ở một cluster nhưng các metric tài nguyên collector vẫn bình thường, đòi hỏi xác định chặng bị lỗi.
Một pipeline có số lượng telemetry accepted cao nhưng backend chỉ hiển thị một phần do tenant routing sai; nhóm trực cần đối chiếu số liệu đầu vào, đầu ra và số liệu truy vấn được theo từng tenant.
Đội SRE muốn phát hiện telemetry stale nhưng metric freshness chỉ được tính tại gateway; dữ liệu bị chờ lâu trong backend query cache và dashboard vẫn không nhận biết khoảng cách giữa event time và ingestion time.
Một tổ chức dùng log collector để tự giám sát pipeline nhưng log lỗi exporter cũng phải đi qua chính exporter đó; khi backend ngừng hoạt động, bằng chứng về lỗi gửi dữ liệu không thể tới nơi quan sát.
Một gateway bị crash loop khi backend chậm và không có hệ giám sát ngoài cụm; nhóm vận hành chỉ phát hiện khi ứng dụng phản ánh dashboard trống, khiến telemetry pipeline trở thành điểm mù khi gặp sự cố.
Một doanh nghiệp nâng cấp collector từ phiên bản cũ và một processor bị loại bỏ; cấu hình vẫn nằm trong repository nhưng binary mới không hỗ trợ, làm pipeline không khởi động sau rollout.
Một nhóm cập nhật cấu hình collector qua GitOps nhưng không kiểm tra syntax và khả năng khởi động trước deploy; một lỗi tên exporter khiến toàn bộ gateway replicas restart cùng lúc.
Một cluster có 20 gateway replicas và cấu hình mới được áp tuần tự; một phần pod dùng pipeline cũ, phần còn lại dùng pipeline mới, khiến metric bị chuẩn hóa khác nhau trong cùng cửa sổ báo cáo.
Một tổ chức cần rollback collector config sau khi filter nhầm log audit; cấu hình cũ được phục hồi nhưng queue đã loại bỏ dữ liệu trước đó nên rollback không thể lấy lại những record đã drop.
Đội phát triển kiểm thử pipeline bằng dữ liệu mẫu nhỏ và chỉ xác nhận exporter nhận được một batch; dưới tải production, queue, memory limiter và backpressure hoạt động khác khiến dữ liệu bị drop mà kiểm thử không phát hiện.
Một công ty muốn đo tỷ lệ mất telemetry end-to-end nhưng nguồn phát không có sequence hoặc canary ID; backend chỉ có tổng số record nên không thể xác định chính xác những sự kiện bị mất giữa các tầng.
Một ứng dụng có clock skew giữa node và gateway; trace span được export thành công nhưng timestamp không đúng thứ tự và hệ phân tích latency cho kết quả âm hoặc bất thường.
Một pipeline chuyển dữ liệu qua ba vùng và dùng timestamp nhận tại từng gateway để ghi lại; khi đối chiếu với event timestamp, độ trễ vận chuyển bị tính sai vì mỗi hop ghi đè thời điểm ban đầu.
Một nhóm muốn giữ thứ tự logs của một giao dịch khi gateway chạy nhiều replica; các batch đến backend không theo thứ tự do retry và xử lý song song, khiến người điều tra cần một khóa correlation đáng tin cậy.
Một adapter tùy chỉnh gom record từ nhiều service thành một resource group và gán service.name theo record đầu tiên; backend phân loại nhầm các record còn lại dù nội dung từng record vẫn có thông tin nguồn.
Một tổ chức muốn chuẩn hóa telemetry từ nhiều đội nhưng mỗi team dùng quy ước riêng cho service.name, deployment.environment và cloud.region; pipeline thiếu schema contract nên thay đổi nhỏ làm dashboard và alert của đội khác bị hỏng.
Một nhóm đưa schema validation vào gateway để từ chối metric thiếu owner và service name; trong đợt migration, các ứng dụng cũ không kịp cập nhật và lượng telemetry bị reject tăng đột ngột.
Một nền tảng sử dụng transform để đổi tên thuộc tính trong traces và logs nhưng không version hóa quy tắc; các dashboard cũ và mới cùng truy vấn một khoảng dữ liệu với hai schema khác nhau, gây sai lệch báo cáo.
Một doanh nghiệp định tuyến telemetry theo mục đích sử dụng, dữ liệu vận hành tới backend nhanh và dữ liệu phân tích tới kho dài hạn; rule chỉ xét service mà không xét loại signal khiến traces chi tiết đi nhầm kho có retention ngắn.
Một pipeline có nhiều nhánh exporter và một nhánh analytics bị chậm; cấu hình fan-out chờ mọi exporter hoàn tất khiến đường gửi dữ liệu vận hành cũng bị chậm theo.
Một tổ chức muốn nhân bản logs audit sang kho bảo mật và kho vận hành; exporter của kho bảo mật thất bại trong khi kho vận hành vẫn nhận log, nhưng upstream retry toàn bộ batch làm dữ liệu ở nhánh khỏe bị gửi trùng.
Một hệ thống gửi metrics tới Prometheus remote write và traces tới Tempo; gateway dùng cùng authentication header cho cả hai endpoint nhưng một backend yêu cầu credential khác, khiến chỉ một signal được chuyển thành công.
Một doanh nghiệp thay đổi tenant routing theo hợp đồng mới; cấu hình pipeline cập nhật nhưng các queue đang giữ batch cũ vẫn được gửi theo tenant mặc định, làm dữ liệu vượt ranh giới sau thời điểm cutover.
Một ứng dụng gửi telemetry của khách hàng doanh nghiệp qua gateway chung; khi một tenant yêu cầu ngừng thu thập, agent vẫn tiếp tục gửi và gateway không có cơ chế chặn theo danh tính tenant đã xác thực.
Một công ty cần lưu lại dấu vết thay đổi pipeline để phục vụ kiểm toán; cấu hình được chỉnh trực tiếp trên pod qua debug endpoint và không được commit vào Git, khiến không thể tái dựng chính sách đã áp trong sự cố.
Một nhóm quản lý collector config bằng nhiều repository và không có chủ sở hữu rõ ràng; thay đổi processor ở một repo không được phản ánh ở gateway production, khiến dữ liệu nhạy cảm tiếp tục đi qua đường cũ.
Một pipeline được thiết kế để xử lý metrics, logs và traces cùng lúc nhưng chưa có mục tiêu độ trễ và mức mất dữ liệu riêng cho từng signal; khi tải tăng, nhóm không biết nên ưu tiên bảo vệ dữ liệu nào.
Một hệ thống telemetry có yêu cầu logs audit không được mất nhưng metrics debug có thể lấy mẫu; queue và quota hiện chia đều cho mọi signal nên log audit bị drop cùng lúc với metric ít quan trọng.
Một công ty cần hoạt động khi mất kết nối Internet trong một giờ; agent chỉ buffer một lượng nhỏ trên node và không có gateway tại site, khiến toàn bộ telemetry trong thời gian offline bị mất.
Một tổ chức triển khai collector gateway tại mỗi vùng để giảm độ trễ nhưng backend tập trung ở một vùng duy nhất; sự cố kết nối vùng chính làm mọi gateway tiếp tục buffer cho tới khi hết dung lượng.
Một đội SRE định kỳ diễn tập tắt backend telemetry để kiểm tra khả năng chịu lỗi; hệ thống vẫn giữ được dữ liệu metrics nhưng logs và traces mất do queue khác nhau, khiến kết quả diễn tập không phản ánh một chính sách tin cậy thống nhất.
Một doanh nghiệp phục hồi collector gateway từ cấu hình backup nhưng không khôi phục persistent queue; pipeline hoạt động trở lại song các batch đang chờ từ trước sự cố không còn, gây khoảng trống lịch sử.
Một tổ chức muốn chuyển từ collector agent cũ sang OpenTelemetry Collector; hai pipeline cùng chạy trong thời gian migration và gửi trùng dữ liệu, nhưng không có nhãn source để so sánh hoặc loại trừ bản ghi duplicate.
Một nhóm ngừng agent cũ sau khi thấy dữ liệu từ collector mới trong dashboard; một số ứng dụng vẫn chỉ gửi theo protocol cũ và telemetry của chúng mất hoàn toàn sau khi endpoint cũ bị tắt.
Một nền tảng có pipeline riêng cho từng cloud provider; mỗi pipeline xử lý resource attributes và retry khác nhau, khiến cùng một service có hành vi dữ liệu không nhất quán khi chuyển region.
Một công ty muốn đưa pipeline telemetry vào SLO nội bộ nhưng chỉ theo dõi uptime của collector; tỷ lệ record bị drop, độ trễ end-to-end và tính đầy đủ dữ liệu không được phản ánh trong mục tiêu dịch vụ.
Đội vận hành đánh giá thành công pipeline bằng việc backend nhận được dữ liệu nhưng không kiểm tra khả năng truy vấn theo tenant, service và thời gian; một lỗi metadata khiến record tồn tại mà người dùng không tìm được.
Một tổ chức có nhiều loại telemetry và mỗi backend có retention, quota cùng giới hạn kích thước khác nhau; pipeline không có cơ chế cảnh báo theo từng exporter nên một signal bị từ chối kéo dài mà không ai nhận biết.
Một service phát telemetry với tốc độ tăng gấp mười trong một đợt sự cố; agent và gateway vẫn sống nhưng queue backlog tăng nhanh hơn khả năng drain, khiến nhóm SRE cần xác định ngưỡng backpressure và hành động giảm tải an toàn.
Một hệ thống nhận telemetry burst sau khi hàng nghìn pod cùng khởi động; gateway bị dồn batch trong vài phút và backend trả 429, trong khi các monitor chỉ theo dõi tải trung bình theo giờ.
Một ứng dụng dùng sampling để giảm traces nhưng không ghi tỷ lệ hoặc lý do bỏ mẫu; khi đội sản phẩm thấy số trace ít hơn số request, họ không phân biệt được sampling có chủ đích với lỗi pipeline.
Một nhóm đặt filter drop spans có thuộc tính health-check trước tail sampling; một service dùng chính luồng health-check để phát hiện lỗi phụ thuộc database, nên span mang bằng chứng sự cố bị loại trước khi sampler có thể giữ trace.
Một pipeline có processor transform tạo bản sao của một số record để phục vụ hai hệ thống; khi retry exporter, bản sao lại được nhân đôi và backend nhận số sự kiện lớn hơn số liệu nguồn.
Một doanh nghiệp có yêu cầu audit về mọi lần thay đổi sampling policy; đội SRE chỉnh tỷ lệ lấy mẫu trực tiếp trên cấu hình runtime nhưng không ghi lại thời gian, người thay đổi và phạm vi ảnh hưởng.
Một tổ chức triển khai pipeline ở nhiều môi trường và muốn kiểm tra dữ liệu không rời khỏi production; exporter staging vô tình nhận resource environment=prod từ client và đưa telemetry nhạy cảm sang backend thử nghiệm.
Một nhóm muốn áp dụng quota theo team nhưng owner tag không được xác thực và có thể bị workload tự gán; tenant gửi dữ liệu lớn tự khai thuộc team khác và làm sai báo cáo phân bổ sử dụng.
Một nền tảng cần bảo đảm trace context không bị mất khi collector batch và route spans; processor tái tạo span record nhưng không giữ parent span ID và trace state, khiến quan hệ phân tán bị đứt dù exporter gửi thành công.
Một ứng dụng Java có baggage chứa dữ liệu nhạy cảm và pipeline chỉ redaction ở logs; instrumentation đã sao chép các giá trị đó sang span attributes và metric attributes nên traces và metrics vẫn mang dữ liệu gốc.
Một tổ chức dùng collector gateway để enrich Kubernetes metadata nhưng workload có thể đổi nhãn sau khi pod chạy; pipeline dùng metadata cũ từ cache và gắn owner sai vào log, làm phân quyền truy vấn không chính xác.
Một nhóm phát hiện collector gateway bị quá tải nhưng dashboard chỉ hiển thị CPU và RAM; họ chưa có số liệu queue capacity, refused records, retry, exporter latency và batch size để phân biệt nguyên nhân gốc.
Một hệ thống tự giám sát collector qua chính pipeline mà collector đó phục vụ; khi exporter chính bị lỗi, metric nội bộ về drop và send failure cũng không thể tới backend, khiến cần một đường quan sát độc lập.
Một công ty thiết kế telemetry pipeline cho 10.000 node nhưng thử tải chỉ trên một agent và một gateway; trong production, fan-in lớn tạo áp lực connection, queue và metadata lookup vượt xa kết quả thử nghiệm ban đầu.
Một nhóm thay đổi topology từ gateway đơn sang nhiều gateway theo vùng nhưng không kiểm thử phân vùng mạng; khi hai vùng mất liên lạc, dữ liệu bị route vòng hoặc gửi trùng và không có quy tắc xử lý split-brain rõ ràng.
Một doanh nghiệp cần xác nhận mọi log audit đã tới kho bảo mật trước khi xóa buffer agent; pipeline chỉ dựa trên HTTP response của gateway mà không có xác nhận từ backend cuối, khiến đội tuân thủ chưa chứng minh được việc giao nhận đầu cuối.
Một nền tảng có collector queue lưu dữ liệu trên đĩa nhưng không kiểm tra khả năng phục hồi sau mất điện; trong diễn tập, file queue bị hỏng và dữ liệu chưa gửi không thể khôi phục dù dung lượng đĩa còn đủ.
Một tổ chức áp dụng schema change cho telemetry mà không hỗ trợ song song phiên bản cũ và mới; các agent chưa nâng cấp gửi record bị từ chối trong khi gateway mới đã hoạt động, tạo khoảng trống dữ liệu trong thời gian rollout.
Một đội phát triển muốn kiểm chứng pipeline bằng dữ liệu canary có sequence ID xuyên qua agent, gateway và backend; hiện tại chỉ đo tổng record accepted nên không thể phát hiện chính xác mất, trùng hoặc đổi thứ tự từng sự kiện.
Một công ty đặt mục tiêu pipeline chuyển 99,9% telemetry trong vòng 60 giây nhưng không có metric event age tại backend; báo cáo nội bộ chỉ dùng thời gian exporter gửi thành công và bỏ qua thời gian chờ ở các queue trung gian.
Một tổ chức có nhiều collector gateway và backend ở các tài khoản cloud khác nhau; sau khi xoay credential, một nhánh exporter không xác thực được nhưng cảnh báo chỉ dựa vào trạng thái process nên sự cố kéo dài mà không ai phát hiện.
Một doanh nghiệp triển khai pipeline telemetry với chính sách ưu tiên logs audit, metrics SLO và traces debug; khi backend mất kết nối, mọi signal dùng chung một queue và các batch trace khối lượng lớn lấp đầy buffer trước khi log audit được gửi.
Một nhóm SRE cần giảm chi phí ingest 30% mà vẫn giữ khả năng điều tra sự cố; pipeline hiện không có phân tích byte theo service, signal, severity và sampling reason nên không biết nên lọc dữ liệu nào an toàn.
