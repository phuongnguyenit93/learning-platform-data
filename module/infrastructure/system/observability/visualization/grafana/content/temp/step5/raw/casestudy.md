Một đội SRE tạo dashboard Grafana cho nền tảng thương mại điện tử nhưng chỉ có biểu đồ CPU và memory; trong sự cố thanh toán, các panel đều xanh dù khách hàng không thể hoàn tất đơn.
Dashboard tổng quan hiển thị request rate, error rate và latency nhưng mỗi panel lấy dữ liệu từ một nguồn khác nhau với bộ lọc thời gian khác nhau; người trực kết luận các tín hiệu không cùng thời điểm.
Nhóm vận hành dùng một dashboard duy nhất cho dev, staging và production; không có biến environment nên người trực thường nhìn nhầm số liệu staging khi xử lý sự cố production.
Một dashboard được chia sẻ qua link trực tiếp nhưng phụ thuộc datasource UID chỉ tồn tại ở máy tác giả; người khác mở dashboard thấy panel báo datasource not found.
Grafana có datasource Prometheus mới nhưng dashboard cũ vẫn tham chiếu datasource theo tên cũ; sau khi đổi tên, nhiều panel chuyển sang trạng thái No data dù Prometheus vẫn hoạt động.
Đội nền tảng cấu hình hai datasource Prometheus cho hai cluster nhưng UID bị hoán đổi trong provisioning; dashboard production bắt đầu hiển thị metrics từ cluster thử nghiệm.
Datasource Prometheus yêu cầu TLS với CA nội bộ nhưng Grafana container chưa có trust bundle; kiểm tra kết nối thất bại dù curl từ máy quản trị truy cập được endpoint.
Grafana kết nối Prometheus bằng service account có quyền quản trị thay vì quyền query chỉ đọc; khi credential bị lộ, phạm vi ảnh hưởng vượt nhu cầu xem dashboard.
Một datasource Loki được thêm với URL gateway nội bộ nhưng Grafana chạy ở namespace khác và không có network route; Explore không tìm được log trong khi Loki backend vẫn healthy.
Datasource Tempo hoạt động trong Explore nhưng trace-to-logs link không chạy vì datasource Loki chưa khai báo liên kết tương ứng; người trực phải sao chép trace ID thủ công.
Đội cấu hình datasource Mixed để so sánh Prometheus và Loki; một panel nhận query từ datasource mặc định khác với dự kiến và trả kết quả không cùng khoảng thời gian.
Grafana datasource dùng proxy access nhưng reverse proxy bỏ qua header xác thực; người dùng đăng nhập Grafana được nhưng các truy vấn backend nhận 401.
Datasource được provision bằng YAML nhưng file cấu hình chứa mật khẩu trực tiếp trong repository; nhiều người có quyền đọc repo có thể truy cập backend telemetry.
Nhóm xoay API token của Prometheus nhưng secret trong Grafana provisioning chưa được cập nhật đồng bộ; panel lỗi theo từng replica sau khi rolling restart.
Một dashboard sử dụng datasource variable để chọn cluster nhưng biến chỉ liệt kê datasource theo tên hiển thị; khi hai datasource trùng tên, truy vấn có thể đi sai cluster.
Prometheus datasource có nhiều exemplar nhưng Grafana panel không bật hiển thị exemplar; người trực không thể nhảy từ điểm latency bất thường tới trace tương ứng.
Nhóm tạo panel time series với PromQL dùng metric counter trực tiếp thay vì rate; biểu đồ tăng liên tục và không thể hiện tốc độ request theo thời gian.
Panel error rate chia số lượng lỗi cho request total nhưng hai truy vấn dùng label matcher khác nhau; tỷ lệ có lúc vượt 100% và làm dashboard gây hiểu nhầm.
Dashboard tính p95 bằng cách lấy trung bình các quantile p95 theo từng pod; kết quả không đại diện phân vị của toàn bộ request trong service.
Panel dùng histogram_quantile nhưng quên giữ label le trong aggregation; truy vấn trả về kết quả sai hoặc không có phân vị latency.
Nhóm cộng bucket histogram trước khi chuẩn hóa theo instance và route; p99 trên dashboard thay đổi bất thường sau khi số replica tăng.
PromQL query dùng rate với cửa sổ cố định 1 phút trong khi dashboard xem khoảng thời gian 7 ngày; dữ liệu thưa làm nhiều điểm No data.
Panel dùng irate trên metric có scrape interval dài; đường biểu đồ nhấp nhô và tạo cảnh báo trực quan giả khi chỉ có ít mẫu trong mỗi cửa sổ.
Dashboard đặt query step cố định 1 giây cho cửa sổ 30 ngày; Prometheus phải trả quá nhiều điểm dữ liệu và panel tải rất chậm.
Nhóm dùng $__interval cho biểu đồ request rate nhưng đặt min interval quá lớn; khi zoom vào sự cố ngắn, các điểm dữ liệu bị gộp và đỉnh lỗi biến mất.
Panel dùng $__rate_interval trong datasource Prometheus nhưng scrape interval của target không được cấu hình đúng; rate query thiếu mẫu và trả khoảng trống.
Dashboard tổng hợp CPU bằng avg mà không nhóm theo cluster và namespace; một cluster quá tải bị che bởi các cluster nhàn rỗi.
Panel hiển thị tổng CPU theo phần trăm nhưng query cộng phần trăm từng core; giá trị vượt 100% khiến người xem tưởng node đã vượt giới hạn phần cứng.
Nhóm dùng phép sum trên Gauge active_connections của các pod nhưng mỗi pod đang quan sát cùng một connection pool dùng chung; dashboard báo số kết nối gấp nhiều lần thực tế.
Panel memory dùng metric working set bytes nhưng đơn vị hiển thị được đặt thành megabytes trong khi query đã chia cho 1024; số liệu nhỏ hơn thực tế nhiều lần.
Dashboard hiển thị latency bằng milliseconds nhưng query lấy metric có đơn vị seconds; người trực đánh giá mức độ chậm cao hơn hoặc thấp hơn một nghìn lần.
Panel hiển thị request count với unit bytes/sec do người tạo sao chép cấu hình panel cũ; đường dữ liệu đúng nhưng nhãn đơn vị làm sai cách diễn giải.
Nhóm cấu hình threshold màu xanh khi error rate cao và đỏ khi thấp do đảo ngưỡng; dashboard trực ca phát tín hiệu thị giác ngược với mức độ nghiêm trọng.
Panel Stat dùng Reduce last nhưng metric không có mẫu mới khi target mất kết nối; số cũ vẫn hiển thị xanh dù dữ liệu đã stale.
Dashboard dùng null value as zero cho tất cả panel; khi datasource mất dữ liệu, biểu đồ rơi về 0 và người trực tưởng hệ thống đã hết request.
Một panel dùng Connect null values để nối đường qua khoảng scrape bị mất; biểu đồ tạo cảm giác số liệu liên tục dù telemetry đã gián đoạn.
Panel Time series hiển thị nhiều label series không có legend format; người trực chỉ thấy hàng trăm đường có tên giống nhau và không xác định được service lỗi.
Nhóm đặt legend theo pod UID thay vì service và namespace; sau mỗi lần rollout, dashboard sinh thêm đường mới và lịch sử so sánh khó đọc.
Dashboard repeat panel theo biến service nhưng biến trả về hàng trăm giá trị; mỗi giá trị tạo một panel riêng và browser hết bộ nhớ khi mở trang.
Panel Table có quá nhiều cột label và giá trị raw; người trực không thấy error rate hoặc latency quan trọng nếu không cuộn ngang.
Nhóm dùng Transformation Organize fields để ẩn cột debug; khi query mới thêm field ở đầu danh sách, transformation chọn nhầm cột và bảng hiển thị sai thông tin.
Transformation Join by field ghép metrics theo instance nhưng một datasource dùng hostname còn datasource khác dùng pod name; bảng kết quả có nhiều hàng không khớp.
Dashboard dùng Outer join giữa request rate và error count; các nhãn khác nhau tạo hàng null và tỷ lệ lỗi bị tính sai ở bước tiếp theo.
Transformation Merge series/table được áp dụng trước khi lọc environment; dữ liệu staging và production bị gộp vào một dòng trong panel.
Nhóm dùng Reduce để tính last value cho một query trả nhiều series; panel Stat chỉ hiển thị một giá trị tổng hợp mà không giải thích phép giảm.
Panel dùng Add field from calculation để chia error count cho request count nhưng hai frame có thứ tự khác nhau; phép tính ghép nhầm series theo vị trí.
Transformation Rename by regex đổi tên trường service.name thành service; một số trường tương tự như service.namespace cũng bị đổi ngoài ý muốn.
Dashboard dùng Filter fields by name để chỉ giữ latency; field error_rate bị loại trước khi panel tính SLI, khiến dashboard chỉ còn độ trễ.
Nhóm áp dụng transformation trên dữ liệu lớn sau khi query toàn bộ logs; browser xử lý hàng trăm nghìn dòng và dashboard treo dù Loki có thể lọc dữ liệu sớm hơn.
Panel sử dụng nhiều query và transformation nhưng không có mô tả nguồn dữ liệu; khi số liệu lệch, đội trực không biết giá trị nào đến từ Prometheus hay Loki.
Explore Loki truy vấn {app="checkout"} nhưng label app thực tế là service_name; truy vấn trả No data và nhóm tưởng log agent đã ngừng hoạt động.
LogQL dùng filter |= "ERROR" trước khi lọc namespace và thời gian; Loki phải quét quá nhiều log và Explore phản hồi chậm.
Nhóm dùng regex rộng trên toàn bộ message trong Loki để tìm exception; truy vấn tốn tài nguyên và trả nhiều log không liên quan.
Dashboard dùng unwrap duration nhưng log parser không trích trường duration thành số; biểu đồ latency từ logs trả lỗi hoặc thiếu dữ liệu.
Log pipeline lưu timestamp theo ingest time thay vì event time; Explore ở khoảng thời gian xảy ra sự cố không hiển thị log đến muộn dù chúng đã được ingest.
Panel Loki lọc theo trace_id nhưng log ứng dụng ghi trace_id dưới dạng traceId; liên kết log và trace không trả kết quả.
Dashboard có panel logs theo service nhưng query không lọc cluster; log từ hai cluster cùng tên service trộn lẫn trong quá trình điều tra.
Nhóm cấu hình derived fields cho trace ID trong Loki nhưng regex không khớp format JSON mới; link sang Tempo không xuất hiện ở các log mới.
Explore cho phép chuyển từ logs sang metrics nhưng datasource Loki không có label tương ứng với metric labels; truy vấn được tạo ra thiếu service và namespace.
Panel log volume dùng count_over_time nhưng nhóm cộng kết quả theo label pod; số lượng pod thay đổi khiến đường tổng không so sánh được giữa các lần rollout.
Dashboard dùng rate log bytes nhưng Loki query range quá dài và không giới hạn label; truy vấn tốn nhiều tài nguyên trong giờ cao điểm.
Nhóm cấu hình Loki datasource với tenant header cố định; người dùng chuyển dashboard sang tenant khác nhưng truy vấn vẫn đọc dữ liệu tenant mặc định.
Grafana Explore chạy query Loki bằng service account có quyền đọc toàn bộ tenant; người dùng chỉ được xem dashboard một tenant nhưng có thể truy cập log tenant khác qua Explore.
Tempo datasource nhận trace ID từ panel nhưng query service không được cấu hình đúng endpoint; link mở trace báo lỗi dù trace đã được lưu.
Panel Tempo service graph không hiển thị dependency vì traces thiếu peer.service hoặc service.name; dashboard cho rằng các service hoạt động độc lập.
Dashboard tìm trace theo service.name nhưng một số ứng dụng phát service.name là tên pod động; truy vấn theo tên service logic bỏ sót phần lớn trace.
TraceQL query lọc span theo http.status_code nhưng dữ liệu đang dùng thuộc tính http.response.status_code; Explore trả No results dù trace tồn tại.
Nhóm dùng TraceQL filter duration > 1s nhưng unit và cú pháp truy vấn không khớp phiên bản Tempo; truy vấn lỗi khi người trực mở dashboard.
Panel latency từ Tempo chỉ dựa trên trace đã được sampling; nhóm diễn giải p99 như độ trễ toàn bộ request dù tập traces lưu không đại diện traffic.
Grafana link từ metrics exemplar sang Tempo dùng datasource UID cũ; sau khi provision datasource mới, exemplar không còn mở đúng trace.
Trace-to-logs link sử dụng trace_id nhưng log backend chỉ lưu traceID viết hoa; liên kết từ Tempo sang Loki trả về kết quả trống.
Logs-to-traces link tạo query theo span_id thay vì trace_id; người trực chỉ thấy log của một span thay vì toàn bộ trace xuyên dịch vụ.
Dashboard có data link mở hệ thống ticket bên ngoài nhưng biến URL encode sai ký tự; khi service name có dấu gạch ngang, link dẫn tới trang không tồn tại.
Nhóm cấu hình dashboard link với biến ${__from} và ${__to} nhưng định dạng thời gian không đúng API đích; người dùng mở link không giữ được khoảng thời gian đang xem.
Panel dùng data link tới Explore nhưng không truyền namespace và cluster; khi trace được mở, kết quả bao gồm nhiều môi trường không liên quan.
Dashboard có annotation triển khai từ datasource Prometheus nhưng query chỉ lấy version hiện tại; người trực không nhìn thấy các lần deploy trước thời điểm latency tăng.
Nhóm nhập annotation deploy từ GitHub webhook nhưng timestamp dùng milliseconds trong khi datasource mong epoch seconds; dấu mốc phát hành nằm sai thời điểm.
Dashboard không hiển thị annotation sự cố từ Alertmanager; nhóm trực phải đối chiếu thủ công giữa lịch sử alert và biểu đồ metric.
Dashboard có time range mặc định Last 5 minutes; khi chia sẻ link sau sự cố, đồng nghiệp mở muộn và không thấy khoảng thời gian đã xảy ra lỗi.
Người dùng đổi timezone Grafana từ browser local sang UTC; dashboard của đội trực và báo cáo quản lý hiển thị thời điểm khác nhau dù cùng dữ liệu.
Panel sử dụng now-24h nhưng truy vấn datasource logs đã lưu timestamp theo local time; sự kiện gần nửa đêm bị lọc sai ngày.
Dashboard auto-refresh mỗi 5 giây với 30 panel và mỗi panel chạy nhiều query; Prometheus và Loki bị truy vấn liên tục ngay cả khi không có người xem.
Nhóm đặt refresh interval 1 giây cho dashboard tổng quan; browser tạo quá nhiều request và backend query bị bão hòa trong giờ trực.
Dashboard tải chậm vì panel table truy vấn toàn bộ logs 30 ngày; người tạo chưa đặt giới hạn số dòng hoặc bộ lọc theo service.
Grafana dashboard có nhiều panel dùng cùng một query nhưng mỗi panel truy vấn độc lập; backend Prometheus nhận tải lặp lại và p95 query tăng.
Nhóm bật caching ở datasource proxy nhưng cache key không xét biến environment; dashboard trả dữ liệu staging đã cache cho người xem production.
Grafana query timeout được đặt quá thấp cho panel lịch sử 30 ngày; dashboard báo lỗi dù truy vấn hoàn thành nếu chạy trực tiếp trên backend.
Panel Prometheus trả Too many datapoints sau khi người dùng chọn 90 ngày; max data points và query step chưa được điều chỉnh theo độ phân giải màn hình.
Dashboard dùng biến cluster nhưng query variable trả về hàng nghìn pod; dropdown mất nhiều thời gian tải và người dùng khó chọn giá trị cần thiết.
Biến service được lấy từ label_values toàn bộ metric mà không lọc environment; tên service trùng giữa staging và production làm panel hiển thị lẫn dữ liệu.
Variable query phụ thuộc biến datasource nhưng thứ tự refresh chưa đúng; khi người dùng đổi datasource, biến service vẫn giữ giá trị từ cluster cũ.
Dashboard có biến multi-value nhưng query PromQL dùng phép so sánh bằng thay vì regex matcher; chọn nhiều service làm panel không có dữ liệu.
Biến All được cấu hình thành chuỗi * trong khi datasource cần regex phù hợp; khi chọn All, truy vấn trả No data hoặc quét toàn bộ dữ liệu.
Nhóm dùng chained variables cluster, namespace và pod; khi đổi cluster, namespace giữ giá trị cũ không tồn tại và toàn bộ dashboard trống.
Panel repeat theo biến region nhưng tên panel giống nhau; người trực không phân biệt được panel nào thuộc vùng gặp sự cố.
Dashboard có biến interval do người dùng chọn nhưng query vẫn dùng cửa sổ rate cố định; đổi khoảng tổng hợp không ảnh hưởng dữ liệu như kỳ vọng.
Nhóm dùng biến adhoc filter cho Loki nhưng datasource không hỗ trợ trường mong muốn; người dùng thêm filter mà query không thay đổi.
Dashboard có biến datasource để chọn Prometheus hoặc Mimir; query expression khác nhau giữa hai backend nhưng cùng panel không có nhánh tương thích.
Datasource Prometheus dùng tên metric cũ ở một cluster và tên mới ở cluster khác; biến cluster thay đổi nhưng panel không chọn đúng query theo schema.
Grafana provisioning nạp datasource trước khi secret được mount; lần khởi động đầu datasource lỗi, còn pod không tự reload cấu hình sau khi secret xuất hiện.
Dashboard JSON được provision từ file nhưng người dùng sửa trực tiếp trên UI; lần restart Grafana ghi đè thay đổi và nhóm không biết bản nào là nguồn chính.
Provisioning dashboard dùng folder UID khác với quyền RBAC được gán; dashboard xuất hiện trong folder mới và người dùng mất quyền xem.
Đội triển khai dashboard qua ConfigMap nhưng giới hạn kích thước ConfigMap bị vượt khi nhúng nhiều dashboard JSON; một số dashboard không được tạo.
Grafana sidecar dashboard watcher chỉ theo dõi một label; ConfigMap mới không có label đó nên dashboard không được provision dù file đã mount.
Nhóm dùng dashboard provisioning với allowUiUpdates tắt; người trực chỉnh panel để xử lý sự cố nhưng không thể lưu thay đổi tạm thời theo quyền hiện có.
Dashboard provisioned có version cũ hơn dashboard trong database; sau restart, provisioning ghi đè phiên bản mới và làm mất panel đã sửa.
Datasource provisioning đặt editable=false; nhóm trực không thể thay đổi cấu hình tạm thời để kiểm tra endpoint mới dù có quyền quản trị folder.
Grafana chạy nhiều replica nhưng dashboard JSON được provision không đồng bộ giữa các pod; người dùng tải trang qua load balancer thấy dashboard khác nhau.
Một dashboard phụ thuộc plugin panel bên thứ ba; sau khi nâng Grafana, plugin không tương thích và các panel hiển thị lỗi plugin unavailable.
Grafana plugin datasource yêu cầu quyền truy cập backend nhưng container chạy với network policy hạn chế; plugin panel hiển thị No data dù datasource tích hợp sẵn hoạt động.
Đội nâng cấp Grafana và plugin cùng lúc; một số field option bị thay đổi và dashboard cũ hiển thị giá trị sai sau migration.
Grafana dùng SQLite trong container ephemeral; pod bị reschedule làm mất users, dashboard sửa thủ công và alert configuration chưa được provision.
Grafana HA dùng nhiều replica nhưng session và database backend chưa được cấu hình phù hợp; người dùng bị đăng xuất ngẫu nhiên khi request chuyển pod.
Đội chuyển Grafana database từ SQLite sang PostgreSQL nhưng không sao lưu dashboard và datasource secrets; sau migration, một số dashboard mở được nhưng datasource credential mất.
Grafana login dùng OIDC nhưng role mapping từ nhóm IdP gán tất cả người dùng vào Admin; quyền quản trị rộng hơn chính sách tối thiểu.
Nhân viên đã bị xóa khỏi nhóm SSO nhưng phiên Grafana còn hiệu lực; người đó vẫn mở được dashboard chứa metrics production sau khi thu hồi quyền.
Grafana anonymous access được bật để hiển thị TV dashboard trong phòng trực; URL dashboard có biến cho phép đổi datasource và xem dữ liệu ngoài phạm vi dự kiến.
Đội hỗ trợ chia sẻ snapshot dashboard công khai; snapshot giữ dữ liệu nhạy cảm trong panel table dù người nhận không có tài khoản Grafana.
Folder RBAC cho phép nhóm frontend xem dashboard ứng dụng nhưng datasource permission không được giới hạn; họ có thể truy vấn trực tiếp logs và traces của hệ thống khác.
Grafana Viewer có thể dùng Explore dù nhóm nghĩ chỉ dashboard được phép; người dùng truy vấn dữ liệu raw vượt phạm vi panel đã phê duyệt.
Dashboard hiển thị dữ liệu tenant theo biến tenant_id nhưng API datasource dùng service credential có quyền đọc mọi tenant; người dùng sửa URL dashboard và xem dữ liệu khách hàng khác.
Nhóm tạo folder theo team nhưng dashboard dùng datasource chung với quyền query production; folder permission không đủ để cô lập dữ liệu backend.
Grafana service account token được dùng bởi nhiều pipeline provisioning; khi token bị lộ, nhóm không thể thu hồi một integration mà không ảnh hưởng các integration khác.
API key Grafana có quyền Admin được lưu trong CI variable dùng chung; một pipeline build không liên quan cũng có thể truy cập và sửa dashboard production.
Dashboard có link chứa token tạm trong query parameter; người dùng chia sẻ URL qua chat khiến token xuất hiện trong lịch sử trình duyệt và proxy logs.
Datasource Loki lưu log có PII nhưng dashboard chỉ che một số cột bằng transformation; người dùng Explore vẫn có thể truy vấn trường gốc.
Panel metrics ẩn label customer_id nhưng query inspector hiển thị PromQL đầy đủ; người có quyền xem panel có thể lấy nhãn đã bị ẩn khỏi visualization.
Dashboard trace hiển thị span attributes chứa Authorization header; nhóm chỉ giới hạn quyền folder mà không làm sạch dữ liệu nhạy cảm tại nguồn.
Grafana audit log chưa bật cho các thao tác thay đổi datasource và quyền folder; sau khi một dashboard bị sửa, nhóm không biết ai đã thay đổi.
Nhóm bật audit logging nhưng chỉ lưu sự kiện đăng nhập; các lần export CSV và query Explore trên dữ liệu nhạy cảm không được ghi nhận.
Dashboard alerting được tạo thủ công trong UI nhưng không nằm trong provisioning; sau khi khôi phục database, các rule cảnh báo không được tái tạo.
Alert rule trong Grafana dùng datasource UID đã bị đổi sau migration; rule chuyển sang No data và không thông báo khi error rate tăng.
Dashboard panel dùng query có biến nhưng alert rule chạy ngoài dashboard context; biến service không được thay thế và cảnh báo đánh giá sai tập dữ liệu.
Nhóm dùng Reduce và Threshold trong panel để hiển thị đỏ khi lỗi tăng nhưng alert rule vẫn dùng query raw; màu panel và trạng thái alert khác nhau.
Alert dashboard dựa trên p95 nhưng query trả nhiều series theo pod; rule không có reduce phù hợp nên chuyển sang trạng thái No data hoặc nhiều alert riêng lẻ.
Grafana alert notification có link tới dashboard nhưng không truyền biến service và time range; người trực mở trang tổng quan rồi phải tìm lại dịch vụ bị lỗi.
Dashboard SLO tính availability bằng request success nhưng bỏ qua các response 429 do rate limit; số liệu cam kết không phản ánh trải nghiệm thực tế.
Panel SLO dùng tỷ lệ trung bình theo từng ngày thay vì tỷ lệ request thành công trên toàn cửa sổ; ngày ít traffic có trọng số ngang ngày cao điểm.
Dashboard hiển thị p99 từ traces đã sampling nhưng tiêu đề không ghi rõ tỷ lệ sampling; người quản lý coi số liệu đó là phân vị của toàn bộ request.
Nhóm dùng transformation để tính error budget còn lại nhưng công thức trộn tỷ lệ phần trăm với số request; panel hiển thị ngân sách âm dù SLO vẫn đạt.
Dashboard dùng nhiều datasource với thời gian ingest khác nhau; metric có dữ liệu mới còn log đến muộn, khiến correlation bằng thời gian không chính xác.
Nhóm tạo link từ panel Prometheus sang Loki bằng biến service nhưng Loki dùng label app; link mở Explore nhưng query không khớp log nào.
Panel metrics có data link sang Tempo bằng exemplar trace ID nhưng trace datasource ở vùng khác; link luôn mở trace not found với các request đa vùng.
Dashboard Explore cho phép chọn trace từ Tempo rồi chuyển sang logs, nhưng service.name trong log và trace khác chuẩn; kết quả liên kết không đầy đủ.
Đội vận hành sử dụng dashboard nhiều tín hiệu để điều tra outage nhưng mỗi panel có legend, đơn vị và ngưỡng khác nhau; không thể so sánh trực tiếp giữa các service.
Một dashboard được sao chép cho nhiều team nhưng query vẫn tham chiếu namespace cũ; nhóm mới nhìn thấy panel trống và tự thêm query khác làm schema phân mảnh.
Nhóm xây dashboard bằng JSON model nhưng không version control; một thay đổi UI làm mất truy vấn gốc và không thể review diff trong pull request.
Dashboard provisioning dùng UID ngẫu nhiên do export từ UI; link nội bộ và alert annotations tham chiếu UID cũ nên điều hướng bị hỏng sau deploy.
Đội kiểm thử dashboard chỉ xác nhận HTTP 200 từ Grafana; không kiểm tra datasource query, panel data frame và link sang Explore nên dashboard lỗi vẫn được phát hành.
CI validate JSON dashboard nhưng không kiểm tra PromQL, LogQL và TraceQL; các panel có query sai cú pháp chỉ lỗi khi người dùng mở dashboard.
Nhóm tạo smoke test dashboard bằng tài khoản admin; kiểm thử pass nhưng người dùng viewer thực tế bị datasource permission từ chối.
Dashboard mới được triển khai ở staging nhưng không có kiểm thử tương thích với schema metric production; sau release, panel không hiển thị vì label mới chưa được xuất.
Đội thêm dashboard mới vào provisioning nhưng quên cập nhật folder permission; dashboard chỉ hiển thị cho admin và người trực không thấy khi cần.
Grafana time range mặc định Last 1 hour nhưng datasource Loki retention chỉ còn 15 phút; dashboard chứa panel logs trống khiến nhóm tưởng ingestion đã dừng.
Panel có query logs từ Loki và metrics từ Prometheus nhưng không cùng biến cluster; khi chọn cluster B, log vẫn truy vấn cluster A và tạo kết luận sai.
Dashboard sử dụng timezone browser nhưng annotation deploy được ghi UTC; dấu mốc deploy lệch khỏi thời điểm latency tăng trong biểu đồ.
Nhóm bật max data points quá cao cho panel traces; Tempo trả nhiều dữ liệu và browser xử lý nặng, làm trang dashboard đóng băng.
Dashboard có nhiều panel tự refresh và nhiều biến chained; khi đổi biến đầu tiên, hàng chục truy vấn chạy đồng thời khiến datasource quá tải.
Đội trực dùng dashboard hiển thị log volume để đánh giá sức khỏe pipeline; log debug tăng làm đường biểu đồ đi lên dù ứng dụng đang phát sinh lỗi nghiêm trọng.
Panel error rate có query lọc status=5xx nhưng không tính lỗi timeout ở gateway do status label khác; dashboard báo xanh trong khi người dùng nhận gateway timeout.
Dashboard có panel về CPU và memory nhưng không có queue depth, saturation và error rate; người trực chỉ nhìn tài nguyên và không thấy hàng đợi đang tăng.
Nhóm hiển thị giá trị hiện tại của Gauge mà không có đường baseline hoặc lịch sử; một mức CPU 70% bình thường vào giờ cao điểm bị hiểu thành bất thường.
Dashboard có threshold cố định cho latency nhưng endpoint đăng nhập và endpoint báo cáo có phân bố bình thường khác nhau; panel báo đỏ liên tục với endpoint xử lý dài hợp lệ.
Đội đặt màu threshold theo percentile nhưng query percentile bị thiếu dữ liệu khi traffic thấp; màu panel chuyển liên tục giữa xanh và đỏ làm giảm độ tin cậy.
Dashboard dùng alias regex để rút gọn tên series nhưng hai service có tên gần giống; cả hai đường được hiển thị cùng legend và người trực không biết đường nào tăng.
Nhóm tạo panel heatmap từ histogram nhưng chọn sai bucket field; phân bố latency không hiển thị đúng và các đợt request chậm bị che.
Grafana Explore truy vấn Prometheus với label filter không có index hữu ích; query kéo dài và người trực không thể nhanh chóng khoanh vùng một service.
Nhóm tạo dashboard tổng quan có query nặng trên metrics raw nhưng không dùng recording rules; mỗi lần mở dashboard tạo tải lớn lên Prometheus.
Datasource Prometheus có query timeout dài nhưng Grafana proxy timeout ngắn; người dùng thấy lỗi gateway timeout dù backend vẫn tiếp tục xử lý truy vấn.
Grafana được đặt sau reverse proxy với root_url sai; link dashboard và callback OAuth sinh URL nội bộ không truy cập được từ browser.
Ứng dụng Grafana dùng subpath /grafana nhưng serve_from_sub_path chưa cấu hình; static assets và link panel bị 404 khi mở qua proxy.
Đội bật gzip và caching ở proxy nhưng response Explore streaming bị buffer; người dùng thấy kết quả log xuất hiện chậm thành từng đợt.
Một dashboard chia sẻ qua playlist trên TV dùng tài khoản service có quyền Admin; thiết bị công cộng có thể truy cập các trang quản trị nếu URL bị thay đổi.
Grafana kiosk mode được bật cho phòng trực nhưng URL dashboard vẫn cho phép mở Explore và menu datasource; người xem trên màn hình công cộng có thể đi sâu vào dữ liệu raw.
Dashboard provisioning lấy file JSON từ ConfigMap nhưng file bị mount read-only và Grafana cần ghi trạng thái; pod lặp lại lỗi provisioning sau mỗi lần restart.
Nhóm xóa datasource cũ nhưng dashboard provisioned còn tham chiếu UID đó; Grafana không tự chuyển sang datasource mới và các panel bị lỗi.
Đội di chuyển từ Prometheus sang Mimir nhưng giữ query có hàm hoặc label không tương thích; panel chỉ sai ở một số cluster sau migration.
Grafana hỗ trợ plugin datasource nhưng phiên bản plugin khác nhau giữa replica; người dùng mở dashboard qua các pod khác nhau nhận kết quả khác nhau.
Nhóm muốn điều tra mất trace nhưng dashboard chỉ có panel trace count; không có panel OTLP ingest errors, exporter failures hoặc sampling ratio để khoanh vùng pipeline.
