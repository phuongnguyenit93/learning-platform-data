Một ứng dụng Spring Boot trả metrics ở /actuator/prometheus trên cổng 9091, nhưng scrape config trỏ vào cổng HTTP nghiệp vụ 8080; target Prometheus liên tục DOWN dù API và readiness probe vẫn hoạt động bình thường.
Nhóm vận hành mở endpoint /metrics bằng localhost trên pod thành công, nhưng Prometheus chạy ở namespace khác nhận connection timeout; NetworkPolicy vừa được siết chặt chỉ cho traffic nội bộ của namespace ứng dụng.
Exporter trên máy ảo trả HTTP 200 khi chạy curl bằng tài khoản quản trị nhưng Prometheus nhận 401; reverse proxy phía trước exporter yêu cầu Basic Authentication mà scrape job chưa được cấu hình tương ứng.
Một dịch vụ đổi metrics path từ /metrics sang /internal/metrics sau bản phát hành; target mới trả 404 trong khi số liệu cũ còn hiển thị trên dashboard khiến đội trực tưởng thu thập vẫn bình thường.
Prometheus scrape một exporter phản hồi sau 12 giây trong khi scrape_timeout chỉ có 10 giây; exporter tự ghi log kết quả thành công nhưng target hiển thị DOWN và không có sample mới.
Nhóm thiết lập scrape_interval 5 giây để quan sát spike ngắn, trong khi exporter tạo report thống kê mất 4 giây và thỉnh thoảng mất 8 giây; số lượt scrape chồng áp lực lên hệ thống bị giám sát.
Endpoint metrics của dịch vụ bắt đầu trả phản hồi lớn hơn 40 MB sau khi thêm nhãn product_id; scrape_duration_seconds và body size tăng mạnh dù số request nghiệp vụ gần như không đổi.
Trước khi nâng cấp bảo mật, Prometheus scrape exporter bằng HTTPS bình thường; sau khi chứng chỉ TLS đổi CA, target báo x509 unknown authority trong khi trình duyệt quản trị vẫn truy cập được.
Exporter của database yêu cầu chứng chỉ client mTLS nhưng một Prometheus replica chưa nhận Secret chứng chỉ mới; cùng scrape job có replica UP và replica DOWN sau đợt luân chuyển khóa.
Một service trả redirect 302 từ /metrics sang trang đăng nhập vì middleware được áp lên toàn bộ router; Prometheus không thu được exposition format mong muốn dù endpoint root vẫn trả nội dung HTML.
Application exporter đưa chuỗi 'NaN' trong mẫu metric dưới định dạng không hợp lệ của Prometheus; scrape target không nhận dữ liệu mới dù HTTP status của endpoint là 200.
Một exporter xuất hai dòng cùng tên metric và cùng tập nhãn nhưng giá trị khác nhau trong một lượt scrape; Prometheus ghi lỗi duplicate sample và dữ liệu của target không xuất hiện như dự kiến.
Nhóm tích hợp exporter của nhà cung cấp cũ dùng các metric name bắt đầu bằng dấu số và có ký tự không hợp lệ; scrape không đọc được exposition text dù server HTTP phản hồi 200.
Đội triển khai node_exporter lên toàn bộ máy chủ nhưng job Prometheus chỉ có danh sách IP tĩnh từ tháng trước; hai máy mới đã phục vụ sản xuất nhưng không có dữ liệu CPU hoặc filesystem trong dashboard.
Một cụm Kubernetes mở rộng từ 20 lên 70 pod; Prometheus vẫn dùng static_configs để scrape từng địa chỉ pod, khiến phần lớn pod mới không có metrics cho tới khi người trực thêm thủ công.
Prometheus dùng Kubernetes service discovery nhưng service account thiếu quyền list/watch endpointslices; những target mới không được cập nhật sau khi triển khai lại Service, trong khi target cũ còn tồn tại một thời gian.
ServiceMonitor mới có nhãn release=monitoring nhưng Prometheus Operator được cấu hình chọn một release label khác; ServiceMonitor tồn tại hợp lệ mà targets page không xuất hiện endpoint nào của ứng dụng.
Một PodMonitor chỉ chọn pod trong namespace staging, nhưng ứng dụng đã được chuyển sang namespace production; metrics của các pod production không xuất hiện dù label app và port không thay đổi.
Kubernetes Service khai báo port metrics có tên telemetry, còn ServiceMonitor tham chiếu port metrics; pod và service đều Ready nhưng Prometheus Operator không tạo scrape target tương ứng.
Ứng dụng đa tenant được deploy thành nhiều Service với cùng nhãn app=api; relabeling của scrape job chỉ giữ service name api-main nên metrics của các tenant còn lại không có trong hệ giám sát.
Sau khi pod được tái tạo với IP khác, danh sách target trên Prometheus vẫn thấy endpoint đã bị xóa vài phút; đội vận hành chưa phân biệt độ trễ khám phá dịch vụ với việc exporter thực sự DOWN.
Một nhóm sử dụng file-based service discovery và cập nhật file targets theo cách ghi trực tiếp từng dòng; trong lúc file chưa hoàn chỉnh, Prometheus đọc cấu hình JSON không hợp lệ và giữ danh sách target cũ.
Prometheus được cấu hình nhiều scrape job cùng chọn một endpoint Kubernetes; cùng một request của ứng dụng có metrics dưới hai nhãn job khác nhau và dashboard cộng gộp thành gần gấp đôi.
Một relabel_config với action keep chỉ chấp nhận namespace prod, nhưng giá trị nhãn metadata thực tế là production; tất cả target bị loại trước khi scrape và không xuất hiện dưới trạng thái DOWN.
Nhóm dùng metric_relabel_configs để loại bỏ metric quá chi tiết rồi kỳ vọng số lần scrape HTTP giảm; lưu lượng từ exporter tới Prometheus vẫn lớn dù số series được lưu trong TSDB đã giảm.
Một relabel rule thay thế nhãn instance bằng tên hostname viết tay, nhưng nhiều pod trên cùng node nhận cùng instance; dashboard không còn phân biệt pod bị lỗi với pod khỏe mạnh.
Đội dùng labeldrop để xóa nhãn endpoint và pod nhằm tiết kiệm bộ nhớ; hai series có tên và các nhãn còn lại giống nhau nhưng giá trị khác nhau bắt đầu va chạm khi được lưu.
Một exporter đã có nhãn job trong payload để thể hiện loại công việc, còn Prometheus thêm nhãn job của scrape config; khi bật honor_labels, các truy vấn cũ theo scrape job trả dữ liệu khác trước.
Nhóm đổi relabeling từ __address__ sang địa chỉ proxy chung để scrape qua gateway; hàng trăm target trông có cùng địa chỉ và một số request được proxy chuyển nhầm backend.
Blackbox exporter kiểm tra HTTP từ ngoài cluster trả probe_success bằng 0, còn metric up của chính blackbox exporter vẫn bằng 1; dashboard chỉ nhìn up nên kết luận website vẫn sẵn sàng.
Đội giám sát chứng chỉ HTTPS bằng blackbox probe chỉ kiểm tra TCP connect; một website có chứng chỉ hết hạn vẫn được đánh dấu xanh vì bước TLS validation không nằm trong phép thử.
SNMP exporter báo ifHCInOctets tăng đều nhưng port switch đã bị shutdown; chỉ số được scrape thuộc interface index cũ sau khi thiết bị thay đổi thứ tự đánh số interface.
Một máy chủ chạy nhiều exporter ở các cổng khác nhau; job scrape được đặt cùng nhãn instance cho tất cả exporter, khiến dashboard phân loại CPU node và số liệu ứng dụng khó tách biệt.
Batch job chạy 10 giây rồi kết thúc, trong khi Prometheus scrape mỗi 30 giây; nhiều lần chạy không bao giờ được quan sát nếu chỉ dựa vào endpoint metrics trong tiến trình job.
Một batch job đẩy số liệu thời gian chạy tới Pushgateway với grouping key chứa execution_id; sau ba tháng, hàng nghìn series của những lần chạy cũ vẫn hiện dù job đã hoàn tất từ lâu.
Batch job đẩy gauge trạng thái 'last_success' lên Pushgateway rồi ngừng chạy vĩnh viễn; dashboard vẫn hiển thị giá trị thành công từ lần cuối vì vòng đời metric không gắn với thời điểm job còn hoạt động.
Nhóm dùng Pushgateway làm nơi tổng hợp request counter của từng pod web đang chạy liên tục; khi một pod bị xóa, metrics cũ vẫn tồn tại và số request trên dashboard bị tính thêm.
Hai Prometheus replica cấu hình external_labels khác nhau để tạo HA; hệ thống remote storage nhận cùng một chuỗi nghiệp vụ từ cả hai, nhưng các truy vấn không khử trùng lặp như nhóm trực giả định.
Một kiến trúc federation lấy metrics từ ba cluster bằng match[] quá rộng; sau khi mở rộng ứng dụng, Prometheus trung tâm nhận hàng triệu series làm thời gian evaluate rule tăng mạnh.
Prometheus cấp trên chỉ federate các recording rules tổng hợp; đội hỗ trợ muốn phân tích pod lỗi nhưng dữ liệu nhãn pod chỉ nằm ở Prometheus cluster nguồn và không thể tra từ bảng điều khiển trung tâm.
Một Counter http_requests_total tăng từ 900.000 về 0 sau khi pod restart; dashboard dùng phép trừ mẫu liền kề nên xuất hiện lưu lượng âm trong khi công cụ phát tải vẫn ghi request đều.
Nhóm vẽ Counter orders_processed_total trực tiếp trên Grafana và kết luận doanh số tăng mỗi giây vì đường đồ thị dốc lên; số đơn được xử lý mỗi phút thực tế đang giảm trong khoảng cùng thời gian.
Đội vận hành dùng irate trên cửa sổ ngắn để báo cáo tốc độ traffic trung bình một giờ; dashboard dao động mạnh theo hai mẫu cuối dù số request mỗi phút gần như ổn định.
Prometheus scrape mỗi 60 giây nhưng biểu thức rate của dashboard chỉ nhìn cửa sổ một phút; nhiều thời điểm không đủ mẫu nên biểu đồ xuất hiện khoảng trống hoặc spike khó diễn giải.
Một nhóm so sánh increase của Counter lỗi trên 5 phút với Counter request trên 30 phút rồi gọi thương số là error rate; sau đợt traffic đột biến, tỷ lệ hiển thị khác xa thống kê gateway.
Ứng dụng export active_connections dưới dạng Gauge nhưng dashboard tính rate của Gauge này để biểu diễn số kết nối đang mở; giá trị âm xuất hiện khi kết nối được đóng.
Hệ thống đo CPU cumulative seconds của container nhưng biểu đồ dùng giá trị nguyên thủy và hiển thị hàng nghìn giây; đội trực đọc thành mức CPU đang sử dụng tại thời điểm hiện tại.
Nhóm tính trung bình p95 latency từ ba Prometheus instance độc lập; một vùng nhận gấp mười lần traffic vùng khác nên kết quả trung bình các quantile không đại diện cho người dùng toàn hệ thống.
Timer histogram có bucket le=0.1, 0.5 và 1.0, trong khi p99 thực tế có nhiều request trên 10 giây; kết quả histogram_quantile từ các bucket hiện tại không mô tả đầy đủ phần đuôi.
Biểu thức histogram_quantile được đặt lên tổng các bucket nhưng vô tình bỏ nhãn le trong phép group by; truy vấn lỗi hoặc trả kết quả không phù hợp với phân phối mong muốn.
Đội dùng rate cho metric histogram_bucket nhưng lấy trực tiếp count của le=0.5 làm số request chậm hơn 500 ms; bộ đếm bucket tích lũy chỉ phản ánh request không vượt ngưỡng này.
Một dashboard tính quantile cho từng pod rồi cộng các giá trị để ra latency toàn service; biểu đồ nhận kết quả lớn hơn nhiều lần latency người dùng ghi nhận trong access log.
Hệ thống phát hành bản mới hỗ trợ native histogram trong một số pod, nhưng một số truy vấn và rule cũ chỉ xử lý classic histogram; dashboard tổng hợp chỉ thể hiện traffic từ nhóm phiên bản cũ.
API đặt hàng xuất counter theo status và method, nhưng PromQL tính tỷ lệ lỗi bằng phép chia hai vector vẫn giữ nhãn khác nhau; kết quả trống dù cả hai nhóm metrics đều tồn tại.
Một query join request rate với thông tin deployment tạo lỗi many-to-many matching; hai exporter cùng phát metric thông tin phiên bản với nhãn service giống nhau và nhiều dòng cho mỗi service.
Đội muốn hiển thị mức tải theo namespace nhưng sum loại bỏ luôn nhãn cluster; request từ hai cluster cùng tên namespace bị gộp thành một đường khiến sự cố vùng bị che khuất.
Biểu thức topk(5) lấy pod có lưu lượng cao nhất tại từng bước thời gian; thành phần danh sách pod thay đổi giữa các thời điểm và người xem tưởng cùng một pod có đường traffic nhảy bất thường.
Một rule so sánh metric lỗi lớn hơn 0 nhưng lúc ứng dụng ngừng export metric, biểu thức trả vector rỗng thay vì giá trị 0; cảnh báo không kích hoạt dù dữ liệu giám sát đã mất.
Dashboard hiển thị up bằng 0 cho exporter lỗi kết nối, nhưng khi job scrape bị xóa khỏi cấu hình thì series up biến mất; đội trực dùng cùng một biểu thức để tìm cả hai tình huống và bỏ sót sự cố cấu hình.
Prometheus vừa deploy target mới và không có lịch sử một giờ; quy tắc dùng rate trên cửa sổ dài cùng tham chiếu offset ngày trước không đủ dữ liệu để so với baseline.
Một service đặt giá trị Counter lỗi tăng ngay khi retry bắt đầu còn Counter tổng request chỉ tăng ở ingress; dashboard chia attempts lỗi cho requests đầu vào nên tỷ lệ lỗi vượt 100%.
Đội dùng phép so sánh bool trong PromQL nhưng điều kiện không khớp series nhãn mong muốn; giá trị 0 và series không tồn tại bị diễn giải giống nhau trong biểu đồ báo cáo.
Một rule dùng avg_over_time trên Gauge queue_depth để phát hiện nghẽn kéo dài; queue thực tế đầy trong vài chục giây rồi rỗng, còn số trung bình năm phút không vượt ngưỡng.
Đội tìm nguyên nhân memory spike bằng max_over_time của metric memory usage nhưng chỉ truy vấn instant vector; giá trị hiện tại đã hạ nên sự cố trước đó không còn hiển thị.
Một dashboard so sánh lưu lượng hiện tại với cùng giờ tuần trước bằng offset, nhưng khách hàng vừa thêm một vùng cloud và thay đổi quy mô; phần trăm tăng không phản ánh cùng tập workload.
Một recording rule tính sum(rate(http_requests_total[5m])) rồi đặt tên như Counter thô; dashboard khác tiếp tục áp dụng rate lên kết quả đã là tốc độ, khiến đơn vị cuối không còn đúng.
Nhóm thêm label_replace để gom tên service theo regex, nhưng một phần workload dùng tên mới không khớp biểu thức; dashboard chỉ đếm phiên bản cũ trong một đợt rolling deploy.
Prometheus chạy quá nhiều truy vấn PromQL trên biểu đồ Grafana có step một giây và khoảng thời gian 30 ngày; query engine dùng CPU cao và trả lỗi vượt giới hạn samples.
Một PromQL subquery lồng nhiều khoảng thời gian làm lượng mẫu trung gian tăng hàng chục lần; khi nhiều người mở dashboard cùng lúc, thời gian phản hồi của API /api/v1/query_range kéo dài.
Nhóm bật recording rule cho một truy vấn phức tạp dùng trong 20 dashboard, nhưng rule group chạy mỗi 60 giây còn dashboard kỳ vọng cập nhật mỗi 10 giây; số liệu có vẻ đứng yên giữa các lần evaluate.
Đội cập nhật một file recording rules nhưng không thực hiện reload thành công; Prometheus vẫn chạy bộ rule cũ trong khi tệp trên đĩa đã chứa công thức mới.
Một nhóm đổi tên recording rule từ job:http_requests:rate5m thành service:http_requests:rate5m nhưng không sửa các dashboard tham chiếu tên cũ; panel Grafana trở thành No data sau phát hành.
Recording rule tổng hợp tỷ lệ lỗi theo môi trường nhưng bỏ nhãn team; khi Alertmanager cần chuyển cảnh báo tới đúng nhóm trực, thông tin định tuyến không còn trong label của alert.
Một alert rule dùng biểu thức CPU > 80% với for: 10m; pod restart vào phút thứ chín làm trạng thái điều kiện bị gián đoạn, trong khi node tiếp tục quá tải nhưng cảnh báo chưa firing.
Đội đặt cảnh báo HTTP error rate > 5% mà không yêu cầu số request tối thiểu; một endpoint chỉ có hai request trong giờ đêm tạo cảnh báo nghiêm trọng sau một lỗi duy nhất.
Một endpoint phục vụ hàng nghìn request mỗi giây nhưng cảnh báo chỉ kiểm tra số lỗi tuyệt đối; trong đợt lưu lượng tăng gấp mười, số 5xx tăng dù tỷ lệ lỗi thực không thay đổi.
Một metric bị mất do exporter down khiến biểu thức so sánh error_rate không còn vector; alert kết luận hệ thống tốt mặc dù không có dữ liệu để kiểm tra SLO.
Đội tạo alert cho mọi container có CPU > 90% mà không lọc pod job batch; trong giờ sao lưu, hàng trăm cảnh báo kích hoạt dù người dùng API không bị ảnh hưởng.
Một alert dùng rate của Counter với khoảng nhìn ngắn hơn chu kỳ scrape; chuỗi thiếu đủ mẫu trong một số thời điểm và alert dao động Firing/Resolved mỗi vài phút.
Một alert rule kiểm tra dung lượng đĩa khi còn dưới 10%, nhưng ổ đĩa TSDB được dùng thêm WAL và dữ liệu cũ chưa compact; chỉ số free space thay đổi nhanh hơn khả năng phản ứng của nhóm trực.
Nhóm thêm alert latency p99 > 1 giây mà không phân biệt loại endpoint; job export hợp lệ chạy vài phút khiến cảnh báo ứng dụng thông thường liên tục nổ.
Một SLO có error budget 0,1% cho 30 ngày, nhưng alert chỉ theo mức lỗi trong một phút; các sự cố ngắn bị đánh thức liên tục trong khi giai đoạn lỗi kéo dài chậm lại không có cảnh báo phù hợp.
Đội triển khai multi-window burn-rate alerts cho SLO nhưng cửa sổ ngắn và dài được cấu hình cùng độ dài; hệ thống mất khả năng phân biệt sự cố đột biến với suy giảm chậm.
Alertmanager nhận cảnh báo của nhiều pod trong một incident nhưng group_by gồm cả pod name và instance; on-call nhận hàng trăm thông báo thay vì một nhóm sự cố cùng service.
Hệ thống có hai vùng cloud nhưng Alertmanager grouping bỏ region; cảnh báo từ vùng A và vùng B được gộp vào một thông báo khiến nhân viên trực không biết cần xử lý ở đâu.
Một alert giảm mức độ nghiêm trọng sau khi ứng dụng tự hồi phục nhưng Alertmanager gửi lại thông báo liên tục vì repeat_interval và group_interval được chỉnh không phù hợp với chu kỳ trực.
Nhóm cấu hình inhibition để chặn cảnh báo ở service khi cluster down, nhưng nhãn cluster không khớp giữa hai rule; on-call vẫn nhận hàng trăm alert hậu quả từ một sự cố hạ tầng.
Một silence được tạo để bảo trì cluster staging nhưng matcher chỉ theo nhãn job và không lọc environment; một cảnh báo production có cùng job cũng bị im lặng trong giờ sự cố.
Alertmanager có route tới nhóm database dựa trên label team=db, nhưng recording rule và alert rule dùng owner=database; cảnh báo lock wait cao được gửi tới receiver mặc định thay vì nhóm phụ trách.
Một alert gửi thông báo thiếu mô tả service, cluster và link dashboard; người nhận biết có lỗi 5xx nhưng phải tìm nhiều nguồn để xác định nơi phát sinh và xem chứng cứ.
Đội kiểm thử alert bằng cách cố tình tạo CPU spike rồi xóa dữ liệu test, nhưng sau deploy không có kế hoạch xác minh đường truyền từ Prometheus đến Alertmanager và kênh trực cuối cùng.
Một trong hai Alertmanager instance mất kết nối đến hệ thống gửi thông báo; Prometheus vẫn hiển thị alert Firing nhưng kênh chat không nhận được thông báo trong thời gian trực.
Prometheus reload cấu hình scrape mới nhưng cú pháp một alert rule YAML không hợp lệ khiến reload thất bại; các file scrape trên đĩa không trùng với trạng thái đang chạy và target mới không xuất hiện.
Trong một đợt scale out, cardinality tăng đột ngột vì exporter thêm label user_id cho request; số series active và memory usage của Prometheus tăng dù tổng request mỗi giây gần như không thay đổi.
Nhóm gắn URL thực tế như /customers/18283/orders/917 vào label path; sau một ngày số series tăng theo số đơn hàng và TSDB tốn nhiều RAM hơn số workload đang chạy.
Exporter có label exception chứa error message với mã giao dịch khác nhau; mỗi sự cố tạo thêm series mới và số chuỗi cũ tiếp tục lưu trong TSDB tới khi hết retention.
Đội bật histogram latency với 40 bucket cho mỗi tổ hợp method, route, status, tenant và pod; số time series tăng theo tích số nhãn khiến scrape và lưu trữ chậm hơn dự đoán.
Nhóm loại label tenant ở metrics bằng metric_relabel_config để giảm cardinality, nhưng nhiều series khác nhau chỉ phân biệt bởi tenant trở nên trùng nhau trong cùng một lượt scrape.
Exporter sử dụng customer_email làm label trên request counter; ngoài việc phình cardinality, endpoint metrics còn công bố dữ liệu định danh cho người có quyền đọc nội bộ.
Trong một số cluster, label service=checkout còn cluster khác dùng app=checkout; truy vấn tổng theo service không hiển thị đủ traffic dù tất cả target đang UP.
Ứng dụng được deploy qua nhiều region nhưng target labels không có region; sau sự cố mạng ở một vùng, dashboard chỉ thấy tổng p99 tăng mà không biết nơi phát sinh.
Một team sửa nhãn environment từ prod sang production trong giai đoạn rolling deploy; dashboard Grafana chỉ lọc prod nên lượng request hiển thị giảm một nửa dù traffic thực không đổi.
Prometheus giữ series cũ có label pod name sau khi pod bị xóa; truy vấn không giới hạn thời gian cho thấy hàng trăm pod đã chết và nhân viên trực nhầm chúng với target đang chạy.
Một exporter đặt metric name ở định dạng khác sau lần nâng cấp thư viện, nhưng recording rules và panel Grafana vẫn tham chiếu tên cũ; hệ thống báo không có dữ liệu dù endpoint trả metrics.
Hai exporter có tên metric chuẩn hóa về cùng tên Prometheus nhưng ý nghĩa và đơn vị khác nhau; kết quả tổng hợp qua job gộp byte với số bản ghi và tạo số liệu vô nghĩa.
Dashboard Grafana dùng biến namespace lọc bằng regex quá rộng; khi khách chọn prod, panel vẫn kéo dữ liệu từ prod-test do biểu thức khớp một phần tên.
Grafana dùng đơn vị seconds cho timer được đổi sang milliseconds ở một custom exporter; đường latency tăng gấp một nghìn lần sau nâng cấp dù thời gian người dùng không đổi.
Hai dashboard Grafana cùng hiển thị error rate nhưng một dashboard tính retries tại sidecar, dashboard còn lại đếm HTTP requests tại ingress; khi dịch vụ chậm, hai tỷ lệ khác nhau rất lớn.
Một panel Grafana chọn step một phút và hàm rate với cửa sổ 30 giây cho metrics scrape mỗi 30 giây; biểu đồ xuất hiện lỗ hổng ở nhiều điểm dù Prometheus vẫn thu dữ liệu.
Một dashboard sử dụng max điểm lấy mẫu tự động thay đổi theo độ rộng màn hình; khi xem từ laptop và màn hình lớn, đỉnh latency hiển thị khác nhau và nhóm chưa hiểu ảnh hưởng của bước lấy mẫu.
Grafana đang kết nối tới Prometheus cluster A để phân tích sự cố cluster B; bộ lọc dashboard có nhãn cluster=B nhưng dữ liệu region không đầy đủ khiến người trực nhầm là workload không phát sinh traffic.
Một panel diễn giải chuỗi up=1 là ứng dụng xử lý thành công; phía backend liên tục trả HTTP 500 nhưng exporter vẫn cho scrape thành công nên trạng thái trên dashboard luôn xanh.
Prometheus bị đầy filesystem lưu TSDB sau khi retention được tăng từ 15 ngày lên 90 ngày; ingest ngừng hoạt động dù CPU và bộ nhớ pod còn đủ.
Một node lưu Prometheus WAL trên ổ đĩa chậm; thời gian ingest tăng trong đợt traffic lớn và log xuất hiện cảnh báo ghi WAL dù scrape targets vẫn đáp ứng.
Prometheus bị kill đột ngột khi node hết bộ nhớ, sau khi khởi động lại mất nhiều thời gian replay WAL và liveness probe restart quá sớm, khiến hệ thống giám sát không phục hồi ổn định.
Máy chủ Prometheus có số block TSDB tăng nhanh vì compaction liên tục bị gián đoạn; disk I/O cao và thời gian chạy query tăng so với trước đợt nâng cấp.
Đội giảm retention time nhưng vẫn không giải phóng lượng dung lượng dự kiến ngay lập tức; ổ đĩa còn chứa các block chưa được xóa và nhiều dữ liệu trong WAL.
Prometheus chạy trên ổ PersistentVolume chỉ có khả năng IOPS thấp; truy vấn dashboard 7 ngày đồng thời với compaction làm scrape ingestion latency tăng đáng kể.
Nhóm đặt retention 7 ngày nhưng bộ phận tuân thủ yêu cầu xem lại sự cố từ sáu tháng trước; một cảnh báo quan trọng đã biến mất khỏi dữ liệu cục bộ dù được ghi trong biên bản sự cố.
Một Prometheus instance giữ dữ liệu ở emptyDir trong Kubernetes; khi pod bị chuyển sang node mới, dashboard chỉ có các metrics kể từ lần khởi động gần nhất.
Đội triển khai hai Prometheus replicas và nghĩ rằng đã có dữ liệu bền vững; cả hai replica cùng đặt storage trên một node, nên khi node hỏng thì lịch sử metrics của cả hai đều mất.
Prometheus remote_write tới hệ thống lưu trữ dài hạn chậm trong vài giờ; số pending samples và retry queue tăng, trong khi scrape tại nguồn vẫn có các sample mới.
Trong một đợt mất kết nối WAN dài, remote_write queue tích tụ nhiều sample đến mức các mẫu cũ bị loại sau khi vượt giới hạn đệm; dashboard trung tâm có khoảng trống dù Prometheus nguồn vẫn lưu dữ liệu cục bộ.
Remote storage từ chối remote_write vì credential đã hết hạn; Prometheus local tiếp tục query được dữ liệu nhưng cluster giám sát tập trung không thấy metric mới sau mốc luân chuyển secret.
Nhóm bật remote_write cho mọi series high-cardinality sang nhà cung cấp cloud; hóa đơn lưu trữ tăng nhanh và thời gian truy vấn của nhóm vận hành không cải thiện như kỳ vọng.
Prometheus ghi external_labels cluster=prod-a nhưng remote storage nhận từ nguồn khác cùng giá trị cluster và replica; các chuỗi trùng nhau khó được phân biệt khi tổng hợp nhiều cụm.
Đội nâng cấp Prometheus và một truy vấn native histogram trong remote backend chưa được hỗ trợ như kỳ vọng; dashboard chỉ mất số liệu p99 của dịch vụ mới trong khi counter request vẫn có.
Một cluster có hàng nghìn node nhưng đội cấu hình Prometheus đơn lẻ để scrape toàn bộ mỗi năm giây; CPU, memory và thời gian scrape tăng đến mức một số target thường xuyên bị timeout.
Nhóm tăng query.max-concurrency và thời gian query timeout để xử lý dashboard chậm; khi nhiều người mở truy vấn nặng cùng lúc, CPU Prometheus tăng và scrape interval liên tục bị trễ.
Endpoint /metrics của một ứng dụng xuất số liệu được tính bằng query database nặng mỗi lần scrape; sau khi tăng số replica Prometheus để HA, tải database tăng theo số lần scrape dù business traffic không đổi.
Đội vận hành cho truy cập trực tiếp giao diện Prometheus từ Internet để tiện tra cứu; kẻ ngoài có thể xem tên service, địa chỉ target và nhãn nội bộ của hệ thống.
Một exporter tích hợp endpoint metrics trong service yêu cầu cookie đăng nhập của quản trị viên; Prometheus scrape không có session và đội đang tính cách đưa credential dài hạn vào file cấu hình không được quản lý bí mật.
Nhóm thêm basic_auth password vào file prometheus.yml được commit cùng source code; trong lúc điều tra scrape lỗi, một log CI vô tình in nội dung cấu hình cùng mật khẩu của exporter.
Một team đổi metrics target từ HTTPS sang HTTP để xử lý lỗi chứng chỉ tạm thời; metrics vẫn thu được nhưng đường truyền đi qua mạng liên vùng không còn đáp ứng yêu cầu mã hóa.
Prometheus self-monitoring ghi prometheus_tsdb_head_series tăng gấp ba và scrape_samples_post_metric_relabeling tăng đều, nhưng dashboard on-call chỉ có metric CPU nên không phát hiện sớm nguy cơ OOM.
Một số target có up=0 suốt 15 phút nhưng Prometheus tự báo healthy; đội trực mới nhận ra thiếu alert giám sát chính Prometheus và alert pipeline khi system lưu metrics gặp lỗi.
Ứng dụng chỉ thỉnh thoảng mất scrape do network packet loss, nhưng biểu đồ Prometheus của Counter nhìn vẫn mượt vì query rate trên cửa sổ dài; số liệu thu thập bị thiếu trong những đoạn mạng chập chờn.
Một alert về tỉ lệ HTTP 5xx không còn Firing sau khi target bị xóa khỏi service discovery; đội vận hành nhầm trạng thái Resolved với việc ứng dụng đã phục hồi thay vì dữ liệu đo đã biến mất.
