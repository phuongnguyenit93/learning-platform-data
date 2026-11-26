Một dịch vụ đặt hàng vẫn báo tiến trình khỏe và CPU thấp nhưng khách hàng liên tục phản ánh không tạo được đơn; dashboard chỉ có metric hạ tầng mà không có tín hiệu về thành công của thao tác nghiệp vụ.
Nhóm triển khai metrics cho một ứng dụng Java nhưng mỗi đội đo request theo cách riêng; khi ghép dashboard giữa gateway và backend, số lượng giao dịch hoàn tất cao hơn số yêu cầu người dùng thực sự gửi.
Ứng dụng Spring Boot ghi số request HTTP thành Counter nhưng dashboard vẽ trực tiếp giá trị tích lũy; biểu đồ luôn tăng ngay cả khi traffic đã giảm gần về không.
Counter tổng số đơn thành công trong một pod trở về không khi pod khởi động lại; dashboard lấy hiệu giữa hai điểm liền nhau nên xuất hiện số đơn được xử lý âm.
Đội vận hành muốn biểu diễn số công việc đang chờ nhưng lại dùng Counter chỉ tăng mỗi khi có job mới; khi worker xử lý xong backlog, chỉ số vẫn tiếp tục tăng.
Một ứng dụng cập nhật Counter thành công ở bước nhận yêu cầu lẫn bước hoàn thành giao dịch; sau đợt mở bán, metric ghi nhận gấp đôi lượng đơn được tạo trong cơ sở dữ liệu.
Nhóm đặt tên một Counter là orders_failed_total nhưng chỉ tăng ở nhánh exception; những trường hợp trả lỗi nghiệp vụ có xử lý không được ghi nhận nên số thất bại thấp hơn thực tế.
Ứng dụng tính tổng byte gửi đi bằng Counter nhưng nhánh retry cộng lại cả payload cũ; trong giờ mạng chập chờn, mức sử dụng băng thông ước tính từ metric cao hơn số byte thực trên đường truyền.
Trong hệ thống xử lý thanh toán, nhiều thread cập nhật một biến đếm tự viết không đồng bộ; tổng số giao dịch metric thấp hơn số bản ghi thanh toán ở cuối ngày.
Nhóm làm mới một Counter theo từng ngày bằng cách đặt về không lúc nửa đêm; đồ thị tốc độ request của hệ thống có các đột biến bất thường ngay thời điểm chuyển ngày.
Một dịch vụ ghi hai Counter cho tổng request và tổng lỗi từ các hook khác nhau; khi timeout xảy ra tại proxy trước khi vào ứng dụng, error rate được tính thấp hơn số lỗi mà client nhìn thấy.
Counter sự kiện nghiệp vụ được phát chỉ sau khi ghi vào Kafka, trong khi hệ thống báo cáo đối chiếu số sự kiện đã được worker tiêu thụ; hai nguồn dữ liệu liên tục chênh lệch trong giờ cao điểm.
Ứng dụng trả HTTP 202 ngay sau khi nhận tác vụ bất đồng bộ; Counter response 2xx vẫn tăng khi worker sau đó không xử lý được đơn, khiến báo cáo thành công theo HTTP khác kết quả nghiệp vụ.
Một dịch vụ phát Gauge cho số kết nối database đang mở nhưng tiến trình chỉ cập nhật khi kết nối được tạo; sau khi kết nối đóng, Gauge vẫn giữ giá trị cao.
Hệ thống quản lý kho dùng Gauge biểu diễn lượng hàng tồn; hai pod phục vụ cùng một kho đều xuất Gauge giống nhau và dashboard cộng chúng thành tồn kho gấp đôi.
Một worker đo số tác vụ đang chạy bằng Gauge nhưng không giảm khi một tác vụ kết thúc bằng exception; số việc đang chạy tăng qua từng ngày dù thread pool đã rảnh.
Nhóm dùng Gauge để thể hiện độ sâu hàng đợi trên từng pod, nhưng hàng đợi được chia sẻ ở Redis; dashboard sum các Gauge cho tất cả pod khiến backlog bị nhân lên theo số replica.
Ứng dụng xuất nhiệt độ thiết bị từ Gauge theo độ C còn dịch vụ khác sử dụng độ F; dashboard tổng hợp hiển thị mức nhiệt trung bình không có ý nghĩa.
Một hệ thống cập nhật Gauge dung lượng cache theo chu kỳ năm phút; cache đầy nhanh trong các đợt traffic ngắn nhưng biểu đồ thường chỉ hiển thị mức trung bình thấp.
Đội phát triển dùng callback ObservableGauge để lấy số phần tử trong bảng database; khi kết nối database chậm, lần collect metrics cũng kéo dài vượt timeout của scraper.
Gauge theo dõi số phiên đăng nhập đã hết hạn nhưng một tác vụ dọn dẹp chạy trễ; dashboard vẫn hiển thị nhiều phiên đang hoạt động dù backend đã coi chúng không còn hợp lệ.
Nhóm đặt một Gauge bằng chênh lệch số job đến và rời hàng đợi; khi hai worker ghi cập nhật sai thứ tự, giá trị tạm thời trở nên âm mặc dù độ sâu hàng đợi không thể âm.
Máy chủ có bộ nhớ JVM heap sử dụng 70% nhưng memory RSS gần đầy; dashboard chỉ nhìn Gauge heap nên không phản ánh phần bộ nhớ native và buffer đang chiếm dụng.
Đội vận hành cộng Gauge phần trăm CPU từ bốn máy để hiển thị mức sử dụng chung; kết quả vượt 100% dù mỗi máy riêng lẻ đều hoạt động dưới giới hạn.
Một node có 64 lõi CPU và một node có 4 lõi, dashboard lấy trung bình đơn giản CPU usage của hai máy; kết quả tổng thể che khuất độ bão hòa thực sự theo năng lực từng node.
Một API ghi nhận thời gian xử lý bằng Histogram nhưng toàn bộ bucket được thiết kế cho thao tác dưới 100 ms; các request 1 giây và 30 giây đều rơi vào bucket vô hạn.
Nhóm định nghĩa bucket độ trễ 0,1; 0,5; 1; 5 nhưng code ghi giá trị theo mili giây còn bộ đo mặc định dùng giây; phân bố Histogram bị dồn vào các bucket cao nhất.
Dịch vụ thanh toán có Histogram request_duration_seconds nhưng dashboard đặt tiêu đề 'thời gian theo mili giây'; người trực báo p95 lệch gấp nghìn lần so với log ứng dụng.
Hai phiên bản ứng dụng có cùng tên Histogram nhưng dùng tập bucket khác nhau; sau rolling deployment, việc tổng hợp histogram theo toàn Service cho ra phân vị khó giải thích.
Một Histogram ghi nhận tổng duration và số lần quan sát nhưng dashboard chia tổng thời gian cho tổng số request của một metric khác; giá trị trung bình sai khi một số request không được instrument.
Nhóm sử dụng Histogram để đo kích thước response nhưng bucket được xây theo KB còn code ghi byte; biểu đồ cho rằng hầu hết response có kích thước cực lớn.
Ứng dụng tạo Histogram cho duration của job từ vài giây đến hai giờ nhưng bucket chỉ dừng ở 60 giây; p99 từ dashboard không phân biệt job chậm vài phút với job kéo dài nhiều giờ.
Đội SRE dùng percentile p99 ước tính từ Histogram có bucket 1–10 giây rất rộng; thao tác thực tế tăng từ 2 lên 8 giây nhưng biểu đồ percentile không phản ánh rõ mức thay đổi.
Trên dashboard, p95 được tính cho từng pod rồi lấy trung bình số học để thành p95 toàn cụm; pod xử lý mười request được đặt trọng số ngang pod xử lý một triệu request.
Một service tính p99 trên Histogram của từng region rồi cộng các p99 để báo cáo độ trễ toàn quốc; giá trị công bố cao hơn tất cả số đo thực tế của request riêng lẻ.
Nhóm sử dụng Summary có sẵn p95 và p99 ở mỗi instance nhưng muốn tổng hợp quantile của nhiều pod bằng phép sum; kết quả trên dashboard không đại diện phân bố của toàn hệ thống.
Một Summary được cấu hình cửa sổ quan sát 10 phút; sau khi hiệu năng đã phục hồi, quantile vẫn bị ảnh hưởng bởi nhiều request chậm từ giai đoạn trước và đội trực tưởng sự cố còn tiếp diễn.
Ứng dụng Java phát Summary latency cho một endpoint rất ít request; khi không có quan sát trong khoảng thời gian liên quan, các giá trị quantile không sẵn sàng và dashboard có những khoảng trống.
Nhóm thay đổi cấu hình quantile của Summary từ 0,95 sang 0,99 nhưng dashboard tiếp tục truy vấn chuỗi cũ; một số panel không còn dữ liệu sau đợt phát hành.
Đội muốn so sánh độ trễ giữa Histogram và Summary của cùng API nhưng một bộ đo xuất duration theo giây, bộ còn lại ghi nhận theo mili giây; hai biểu đồ có hình dạng giống nhau với thang đo khác nhau.
Một ứng dụng tạo Summary để theo dõi số bytes theo mỗi lần upload, nhưng dashboard dùng quantile trong cùng metric như thể đó là thời gian xử lý; nhóm vận hành diễn giải sai ý nghĩa đại lượng.
Trong hệ thống 200 pod, nhóm đặt Histogram đo duration của mọi SQL statement với label chứa nguyên câu truy vấn và tham số; số time series tăng mạnh sau mỗi đợt traffic.
API tra cứu đơn hàng gắn order_id vào label của Counter request; một triệu mã đơn khiến hệ thống lưu metrics phải xử lý hàng triệu tổ hợp nhãn.
Nhóm gắn user_id làm label cho Histogram độ trễ đăng nhập; khi có nhiều người dùng mới, bộ nhớ ứng dụng và backend metrics tăng theo số tài khoản.
Ứng dụng dùng nhãn path bằng URL thực tế có số đơn, thay vì route template, khiến mỗi yêu cầu tạo thêm chuỗi metric dù các URL cùng một endpoint.
Metric lỗi chứa label exception_message với giá trị có mã đơn và thời điểm phát sinh; số series tăng trong suốt ngày dù số kiểu lỗi thực tế rất ít.
Nhóm gắn trace_id vào nhãn metric để liên kết request với trace; sau khi tăng tỷ lệ tracing, cardinality metrics tăng đột biến và dashboard không còn phản hồi nhanh.
Ứng dụng ghi nhãn status_code theo các giá trị 200, 201, 400 và 500, nhưng một nhóm khác dùng '2xx', '4xx', '5xx'; dashboard toàn hệ thống gộp hoặc bỏ sót những chuỗi khác định dạng.
Metric HTTP server có label method dùng chữ thường ở service này và chữ hoa ở service khác; filter GET trên dashboard không hiển thị các yêu cầu get từ hệ thống thứ hai.
Nhóm sử dụng label environment với các giá trị prod, production và live; cùng một nhóm workload bị chia thành nhiều tập metrics khi tính SLO production.
Trong một ứng dụng đa tenant, tất cả metric đều gắn tenant_id; chi phí lưu time series tăng mạnh sau khi tích hợp hàng nghìn khách hàng mới, dù các chỉ số vận hành chung không cần chia theo tenant.
Hệ thống ghi label Kubernetes pod UID vào mọi Counter; sau nhiều đợt rollout, lượng chuỗi không còn active tăng và thời gian truy vấn lịch sử kéo dài.
Một cluster dùng label instance kết hợp hostname và cổng, nhưng một số exporter đổi cổng động sau mỗi lần khởi động; cùng một workload được coi là nhiều chuỗi thời gian kế tiếp.
Đội phát triển thêm label feature_flag với mọi tổ hợp cờ tính năng trên từng request; số chuỗi Histogram tăng theo số kết hợp chứ không chỉ số flag riêng lẻ.
Một nhóm chuẩn hóa label thành các giá trị giới hạn nhưng trong quá trình đổi schema hai tên nhãn cũ và mới cùng tồn tại; truy vấn dashboard chỉ nhìn một phần lượng traffic.
Ứng dụng tạo metric lỗi có label result=success hoặc failure rồi lại tạo tên metric riêng cho từng kết quả; hai dashboard dùng hai cách đếm khiến báo cáo không khớp.
Nhóm đặt service_name trong label của một số exporter, nhưng resource attribute ở nguồn khác lại dùng service.name; dữ liệu cùng ứng dụng không được gom đúng khi vẽ biểu đồ.
Đội quan sát lưu lượng theo HTTP route nhưng một endpoint không tìm được route template và phát giá trị nhãn rỗng; request của nhiều đường dẫn không liên quan bị gộp chung một chuỗi.
Nhóm muốn biết latency của người dùng ở từng tỉnh thành và thêm label tỉnh vào mọi metric; một phần request không có vị trí chính xác còn chuỗi theo tỉnh gần như không có mẫu.
Metric số đơn lỗi chỉ ghi mức severity từ error log thay vì loại lỗi nghiệp vụ; số lượng loại lỗi tăng nhưng phần lớn bị gom vào một label ERROR không giúp phân tích.
Một cụm Prometheus scrape ứng dụng mỗi 15 giây nhưng exporter chỉ cập nhật Gauge độ sâu hàng đợi mỗi hai phút; đồ thị nhiều điểm giống nhau khiến người trực tưởng hàng đợi không thay đổi.
Đội đổi scrape interval từ 15 giây sang 60 giây để giảm chi phí; những đợt tăng CPU kéo dài 10 giây trong mỗi phút không hiện rõ trên biểu đồ.
Một endpoint /metrics của ứng dụng thỉnh thoảng mất 20 giây để trả lời vì collect một metric gọi database; Prometheus scrape timeout sau 10 giây và nhiều chuỗi biến mất cùng lúc.
Hệ thống exporter báo lỗi HTTP 500 khi đang tải cao; dashboard ứng dụng đang coi thiếu dữ liệu như 0 nên hiển thị throughput rơi về không dù người dùng vẫn truy cập được dịch vụ.
Một container bị OOMKilled rồi khởi động lại; Counter quay về không nhưng biểu đồ tốc độ request dựa trên phép trừ trực tiếp xuất hiện đỉnh âm khó giải thích.
Exporter Prometheus của một node tạm mất kết nối trong 20 phút; khi kết nối trở lại, biểu đồ có khoảng trống và người trực không biết sự cố nằm ở ứng dụng hay đường thu thập telemetry.
Nhóm so sánh số request trong hai giờ nhưng một khoảng bị mất scrape; tổng được ngoại suy từ các rate đo được không khớp số giao dịch lưu trong database.
Đội đặt scrape interval 30 giây nhưng một dashboard query ở bước 5 giây; biểu đồ lặp nhiều điểm gần giống nhau và người xem nghĩ hệ thống đã đo ở độ phân giải cao hơn.
Một workload vừa ngừng chạy nhưng dữ liệu ở khoảng gần nhất vẫn hiển thị trên dashboard; người trực không phân biệt được giá trị đang sống với series stale sau khi target biến mất.
Ứng dụng mới đăng ký metric nhưng chưa có request nào; dashboard không thấy time series tương ứng và nhóm diễn giải như instrumentation chưa hoạt động.
Một Counter được tạo nhãn ngay lần request đầu tiên; các cặp label chưa từng xuất hiện không có chuỗi với giá trị bằng không, làm tổng các loại response thiếu cột.
Hai Prometheus replica cùng scrape một pod rồi gửi metrics về kho trung tâm mà không có quy tắc dedup phù hợp; tổng request của toàn cluster gần gấp đôi thực tế.
Nhóm bật recording rules để tổng hợp metric theo service nhưng vẫn tính tổng cả chuỗi raw và chuỗi đã được tổng hợp; biểu đồ request rate cao gấp hai lần sau thay đổi.
Một hệ thống truy vấn tốc độ request bằng cửa sổ rate 30 giây trong khi scrape mỗi 60 giây; nhiều điểm không đủ mẫu để ước lượng tốc độ và dashboard xuất hiện NaN.
Đội tính tốc độ lỗi bằng cửa sổ một giờ khi sự cố 500 chỉ kéo dài ba phút; đỉnh lỗi bị làm phẳng và cảnh báo đến muộn so với thời điểm khách hàng bị ảnh hưởng.
Một API ít người dùng có đúng một request thất bại trong năm phút, khiến tỷ lệ lỗi đạt 100%; người trực bị đánh thức dù chỉ một khách bị ảnh hưởng.
Ứng dụng nhận hơn một triệu request mỗi phút với error rate chỉ 0,1%; dashboard nhìn phần trăm nhỏ nên đánh giá mức độ ảnh hưởng thấp dù số lỗi tuyệt đối rất lớn.
Nhóm tính error ratio bằng tổng lỗi theo mọi môi trường chia tổng request production; tỷ lệ lớn hơn 100% trong một số thời điểm do tử số và mẫu số không cùng tập traffic.
Một gateway chia request theo hai status group, trong khi backend ghi từng mã HTTP cụ thể; phép tổng hợp giữa hai tầng vừa đếm lặp vừa sử dụng tiêu chí thành công khác nhau.
Đội tính latency trung bình của một endpoint bằng cách cộng giá trị trung bình của từng pod rồi chia cho số pod; pod có traffic thấp ảnh hưởng ngang pod nhiều traffic.
Một nhóm lấy tổng số request Counter từ mọi instance rồi áp rate lên dữ liệu đã bị gộp sau khi pod restart; các biến động reset bị che lẫn khiến throughput tính ra bất thường.
Doanh nghiệp chạy ứng dụng ở hai vùng có mức traffic rất khác nhau; dashboard chỉ hiển thị trung bình latency toàn quốc nên sự cố riêng vùng nhỏ bị che khuất.
Một báo cáo tính p95 theo từng endpoint rồi lấy p95 lớn nhất làm chỉ số toàn hệ thống; cùng lượng traffic nhưng tỷ lệ endpoint thay đổi khiến kết quả diễn giải lệch mục tiêu.
Dashboard đo thời gian phản hồi bằng p50 nhưng đội phát triển muốn đánh giá trải nghiệm của nhóm người dùng chậm nhất; các đợt p99 tăng mạnh không xuất hiện trong chỉ số chính.
Nhóm lập biểu đồ thời gian xử lý API theo unit seconds nhưng frontend hiển thị milliseconds; mức trễ thực tế vài trăm mili giây được thông báo thành hàng trăm giây.
Một dịch vụ công bố metric kích thước hàng đợi bằng 'jobs' nhưng dashboard ghi 'requests/sec'; đội vận hành nhìn đường đi lên và hiểu nhầm năng lực xử lý tăng.
Nhóm đổi đơn vị đo và tên metric từ request_duration_ms sang request_duration_seconds trong mã nguồn nhưng không đổi các phép tính dashboard; báo cáo hiệu năng bị lệch sau triển khai.
Một hệ thống dùng thời điểm UTC ở metrics còn bảng đối soát nghiệp vụ theo múi giờ địa phương; tổng giao dịch theo ngày khác nhau dù không có sự kiện bị mất.
Dashboard tự động chọn khoảng tổng hợp một giờ khi xem dữ liệu cả tháng; sự cố timeout dài bốn phút bị pha loãng trong đồ thị và người trực không nhận ra.
Biểu đồ tỷ lệ lỗi theo ngày được làm mượt bằng trung bình trượt; một đợt lỗi ngắn nghiêm trọng bị kéo dài trên đồ thị sau khi ứng dụng đã phục hồi.
Đội vận hành chỉ xem số request trung bình mỗi giây; một endpoint nhận burst hàng nghìn request trong vài giây khiến connection pool cạn nhưng mức trung bình mỗi phút vẫn thấp.
Một dịch vụ batch chạy đúng mỗi 30 phút, nên biểu đồ CPU có các đỉnh đều đặn; ngưỡng cảnh báo tĩnh được đặt mà không đối chiếu lịch vận hành khiến on-call nhận cảnh báo nhiễu.
Người trực xem biểu đồ hai đường latency và CPU tăng cùng lúc rồi khẳng định CPU là nguyên nhân; dữ liệu queue wait và I/O chưa được thu thập để kiểm chứng quan hệ nhân quả.
Nhóm so sánh hiệu năng trước và sau khi thay SQL nhưng giai đoạn sau có số người dùng đồng thời cao hơn; biểu đồ p95 không có nhãn deployment hoặc traffic tương ứng.
Một dashboard có 50 panel với nhiều công thức không chú thích; khi xảy ra lỗi, đội trực không biết panel nào phản ánh triệu chứng người dùng và panel nào chỉ là tài nguyên nội bộ.
Nhóm tạo metric số request theo service nhưng dashboard không có biến lọc region, environment và version; người trực không thể cô lập lỗi chỉ xảy ra ở bản canary.
Một team đặt SLI availability bằng tỷ lệ HTTP 2xx của gateway, nhưng API trả 200 cho đơn hàng bị từ chối vì lỗi nghiệp vụ; SLO báo đạt trong khi khách không đặt được hàng.
Dịch vụ đặt hàng trả HTTP 202 khi nhận đơn vào queue, nhưng worker có thể thất bại sau vài phút; SLI theo status HTTP không thể hiện kết quả hoàn thành giao dịch.
Nhóm đặt SLO 99,9% request có latency dưới 300 ms; histogram được thiết kế không có bucket tại hoặc gần 300 ms, khiến việc ước tính tỷ lệ request đạt mục tiêu có sai số lớn.
Một endpoint trả dữ liệu lớn có thời gian phản hồi thường 2 giây, nhưng được đưa vào SLO latency 300 ms chung với API đăng nhập; dashboard báo vi phạm dù nhu cầu người dùng khác nhau.
Đội xây SLI success bằng số request không phải 5xx chia tổng request nhưng lại không tính timeout ở gateway; trải nghiệm client kém hơn tỷ lệ thành công được công bố.
Một hệ thống có error budget gần cạn sau ba outage, nhưng dashboard chỉ hiện SLO rolling 30 ngày mà không thể hiện tốc độ tiêu hao ngân sách trong các giờ gần đây.
Nhóm cấu hình alert dựa trên error rate một phút; khi traffic rất thấp, một lỗi làm cảnh báo firing, còn khi traffic tăng từ từ trong nhiều phút thì tín hiệu cảnh báo đến không ổn định.
Một SLO có tổng số giao dịch theo ngày rất nhỏ; tỷ lệ thành công biến động lớn theo một hoặc hai request, khiến chỉ số phần trăm khó đánh giá nếu không nhìn thêm số lượng mẫu.
Nhóm theo dõi metric lỗi nội bộ của service nhưng bỏ qua request thất bại ở tầng cân bằng tải trước khi đến ứng dụng; SLI theo góc nhìn người dùng cao hơn thực tế.
Một tổ chức có SLO latency cho thao tác thanh toán nhưng không phân biệt yêu cầu thành công với yêu cầu lỗi 4xx/5xx; những response lỗi nhanh kéo thấp phân vị latency tổng.
Đội định nghĩa SLI độ trễ cho request HTTP trong khi trải nghiệm người dùng bao gồm công việc bất đồng bộ kéo dài sau response; dashboard báo nhanh nhưng khách nhận hàng chậm.
Một nhóm dùng giá trị trung bình latency để đánh giá thỏa SLO percentile; nhiều request cực chậm bị che bởi lượng lớn request nhanh và đánh giá mức dịch vụ không phù hợp cam kết.
Đội vận hành thêm exemplar vào Histogram để tìm trace của request chậm, nhưng chỉ một phần trace được sampling; khi mở một điểm p99 trên dashboard không có trace tương ứng.
Ứng dụng thêm nhãn phiên bản vào metric để so sánh canary với ổn định, nhưng nhãn phát hành được gắn khác nhau ở exporter; dashboard chỉ thấy một phiên bản dù cả hai đang có traffic.
Một dịch vụ đo tỉ lệ cache hit bằng hai Counter hit/miss nhưng nhánh request trả lỗi trước cache không được tính vào mẫu số; nhóm báo hiệu quả cache cao hơn traffic đầu vào thực tế.
Hệ thống ghi số lần retry thành công như các request thành công mới; khi upstream chập chờn, request rate tăng và SLI availability tính theo attempt khác với trải nghiệm của từng yêu cầu người dùng.
Đội phát triển instrument số byte nhận vào bằng Counter có nhãn content_type chứa cả tham số boundary ngẫu nhiên của multipart; cardinality tăng theo từng lần upload.
Người vận hành theo dõi mức sử dụng connection pool bằng một Gauge active connections nhưng không có Gauge pending requests; khi queue chờ phình to, dashboard vẫn báo chưa chạm ngưỡng kết nối.
Nhóm muốn biết backlog của Kafka và dùng Counter số message đã đọc làm chỉ số duy nhất; khi producer gửi nhanh hơn consumer, throughput vẫn tăng trong khi hàng đợi cũng tăng.
Ứng dụng gửi một số metric qua cơ chế push trong khi phần còn lại được scrape; các tín hiệu có độ trễ và chu kỳ cập nhật khác nhau nên dashboard hiển thị những trạng thái không cùng thời điểm.
Nhóm ngừng một batch job đã hoàn tất nhưng metric của lần chạy cũ vẫn tồn tại trong nơi lưu dữ liệu; dashboard tưởng còn một job đang chạy do không có ngữ cảnh về vòng đời.
Đội thu thập metrics từ môi trường production có giới hạn quyền truy cập, nhưng endpoint /metrics mới vô tình phơi thông tin tên máy, phiên bản thư viện và đường dẫn nhạy cảm cho các client không được phép.
Một service dùng label customer_email để phân tích độ trễ nhưng endpoint metrics bị nhiều nhóm đọc; cùng một thay đổi instrumentation vừa tăng cardinality vừa làm lộ dữ liệu cá nhân.
Nhóm tăng số bucket của hàng chục Histogram theo từng method, route và status để tăng độ chính xác; chi phí lưu trữ và CPU thu thập metrics tăng vọt sau khi triển khai.
Đội giảm retention metrics từ 90 xuống 7 ngày để tiết kiệm dung lượng; khi cần phân tích chu kỳ trả lương hàng tháng, dữ liệu đối chiếu cùng kỳ không còn.
Một dịch vụ triển khai instrumentation mới và p99 tăng, nhưng nhóm không giữ baseline CPU, memory, throughput và mức overhead của exporter; thay đổi hiệu năng chưa được quy cho nguyên nhân đáng tin cậy.
Đội trực muốn giải thích vì sao CPU tăng cùng số đơn bị lỗi; metrics có thể chỉ ra thời điểm và mức độ bất thường nhưng không có nhãn liên kết đến logs hoặc traces để xác định thao tác gây lỗi.
