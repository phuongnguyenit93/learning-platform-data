Một API tạo đơn hàng dùng Counter để tăng số lượt thành công ngay khi request bắt đầu; sau đợt database timeout, dashboard báo số đơn thành công cao hơn số đơn thực sự được ghi nhận trong bảng orders.
Nhóm vận hành muốn xem số request đang thực thi nhưng ứng dụng dùng Counter chỉ tăng khi bắt đầu mà không giảm khi kết thúc; số liệu tiếp tục lớn dần dù không còn request đang xử lý.
Một worker Java ghi Counter cho số message đã nhận và số message xử lý thành công; khi broker phát lại message sau timeout, tổng số lần nhận tăng nhanh hơn số message nghiệp vụ duy nhất mà dashboard đang giả định.
Dịch vụ giao dịch sử dụng Counter tăng một đơn vị khi số tiền chuyển là 100.000 đồng; dashboard đọc giá trị counter như tổng tiền giao dịch nên doanh thu hiển thị thấp hơn dữ liệu kế toán.
Một ứng dụng dùng Counter tăng số lần retry và Counter khác tăng tổng request; khi retry diễn ra ở cả HTTP client và proxy, tỷ lệ retry tính từ hai nguồn không phản ánh chính xác số lần gọi thực tế tới backend.
Một job khởi động lại mỗi ngày làm Counter tổng số sự kiện trở về 0; dashboard cộng chênh lệch thô giữa các mẫu thay vì xét reset và hiện những đoạn số sự kiện âm.
Đội sản phẩm muốn biết tỷ lệ thanh toán thành công nhưng chỉ có Counter lỗi mà không đo tổng số giao dịch; khi lưu lượng tăng gấp mười, số lỗi tuyệt đối tăng nhưng chưa thể kết luận chất lượng dịch vụ xấu đi.
Một service ghi Counter lỗi theo tên exception cụ thể bao gồm thông điệp có mã đơn; số chuỗi thời gian tăng nhanh sau khi phát sinh nhiều loại lỗi và backend Prometheus bắt đầu tiêu thụ nhiều bộ nhớ.
Một API tạo báo cáo bị retry tự động ở SDK; Counter tại handler đo tất cả lượt thực thi, còn báo cáo nghiệp vụ đếm một lượt theo idempotency key, khiến hai hệ thống có số liệu khác nhau trong giờ cao điểm.
Nhóm thêm một Counter riêng cho từng endpoint bằng cách đưa toàn bộ URL chứa ID khách hàng vào tên meter; sau vài tuần, số lượng metric name tăng gần bằng số request có đường dẫn duy nhất.
Một API có ba nhánh lỗi nhưng Counter failure chỉ tăng trong khối catch Exception; các request bị từ chối sớm do validation trả HTTP 400 không được tính vào metric thất bại.
Đội tích hợp tăng Counter số giao dịch thành công ở hai tầng service và repository rồi cộng hai metric cùng tên lên dashboard; số lượng giao dịch sau triển khai dường như tăng gấp đôi dù tải không đổi.
Một ứng dụng tạo Gauge từ biến local chứa độ dài queue rồi không giữ tham chiếu đến đối tượng được quan sát; sau nhiều lần GC, metric không còn giá trị hợp lệ tại endpoint scrape.
Nhóm dùng Gauge cho số kết nối JDBC bằng cách truyền một giá trị số chụp tại thời điểm startup; lúc pool chạm giới hạn, biểu đồ gauge vẫn hiển thị giá trị ban đầu và không phản ánh pool hiện tại.
API cho phép người dùng tạo tác vụ và dashboard cần thấy số tác vụ đang chờ; đội phát triển sử dụng Counter tích lũy để biểu diễn backlog, nên sau khi xử lý hết tác vụ biểu đồ vẫn tăng.
Một queue có hàng nghìn phần tử nhưng Gauge lấy kích thước qua hàm đếm toàn bộ một cấu trúc dữ liệu lớn mỗi lần được scrape; dưới lịch thu thập dày, CPU ứng dụng tăng dù không có thay đổi traffic.
Ứng dụng đăng ký Gauge nhiều lần với cùng tên và tập tag khi mỗi request tới; dashboard chỉ có một chuỗi thời gian và không chuyển sang đọc biến quan sát mới mà nhóm kỳ vọng.
Một Gauge theo dõi lượng bộ nhớ cache bằng giá trị âm khi code cập nhật số phần tử không đồng bộ giữa nhiều thread; biểu đồ xuất hiện các giá trị không thể có dù cache vẫn trả dữ liệu hợp lệ.
Dashboard hiển thị Gauge active sessions của mỗi pod nhưng phép cộng toàn cluster bị thiếu các pod vừa restart; dữ liệu được scrape không cùng thời điểm và không đủ thông tin nhận diện các instance còn sống.
Một service tạo Gauge quan sát một đối tượng queue tạm rồi không giữ tham chiếu mạnh tới đối tượng đó; sau vài giờ giá trị gauge trở thành NaN dù hàng đợi chính vẫn có dữ liệu.
Nhóm đo lượng hàng tồn bằng Gauge nhận dữ liệu từ cache cập nhật mỗi 15 phút; dashboard hiển thị số mới ở mỗi scrape 15 giây nhưng giá trị thực chất vẫn cũ so với thay đổi trong database.
Một backend ghi Gauge nhiệt độ thiết bị theo Celsius nhưng dashboard gắn nhãn Fahrenheit; mức cảnh báo vượt ngưỡng được kích hoạt ở thời điểm không phù hợp.
Ứng dụng có Gauge theo dõi số job đang chạy từ AtomicInteger, nhưng nhánh xử lý lỗi trả sớm mà không giảm biến đếm; sau mỗi ngày số active job tăng dù không có tiến trình nào chạy.
Nhóm hiển thị độ dài queue của 10 shard bằng gauge theo tag shard; sau khi resharding từ 10 lên 100 shard, số chuỗi thời gian và tốc độ thu thập tăng dù tổng số tác vụ không thay đổi.
Một API dùng Timer mang tên database.query nhưng bắt đầu và dừng đo quanh toàn bộ HTTP controller; kết quả gồm cả validation, logic nghiệp vụ và lời gọi dịch vụ khác, nên nhóm gán nhầm độ trễ lên database.
Dịch vụ Java tạo Timer cho một request bất đồng bộ nhưng dừng ghi nhận ngay sau khi tạo CompletableFuture; dashboard báo dưới 10 ms trong khi client thường chờ vài giây cho kết quả.
Một scheduled job chạy được 25 phút nhưng Timer được gắn cho mỗi thao tác con thay vì vòng đời toàn job; giám sát không có số đo phù hợp về thời gian hoàn thành tác vụ tổng thể.
Ứng dụng đặt Timer quanh một phương thức có thể ném exception; các lần lỗi chưa tới điểm kết thúc ghi nhận nên biểu đồ duration bị thiên lệch về những request thành công.
Một Timer dùng để đo thời gian xử lý request nhưng đối tượng Stopwatch bắt đầu trước lúc request vào queue; dashboard không thể phân biệt thời gian đợi worker với thời gian thực thi nghiệp vụ.
Đội tích hợp dùng Timer ghi một giá trị tính theo millisecond nhưng truyền vào API record với đơn vị seconds; histogram mới hiển thị độ trễ cao hơn thực tế hàng nghìn lần.
Một hệ thống chuyển dữ liệu giữa hai thread khi đo duration, nhưng code dùng thời gian đồng hồ hệ thống ở hai máy khác nhau để trừ thay vì đo elapsed time ổn định; một số quan sát có giá trị âm.
API xử lý 50.000 request mỗi phút và Timer có count tăng đều; dashboard chỉ biểu diễn sum duration mà không đối chiếu số request khiến tổng thời gian tăng bị hiểu nhầm là latency trung bình tăng.
Nhóm tính p99 bằng trung bình các p99 Timer trên từng pod; một pod nhận gấp mười lần traffic các pod khác nên kết quả không đại diện cho phân phối latency toàn ứng dụng.
Timer được cấu hình xuất client-side percentile nhưng dashboard Prometheus muốn tính p95 toàn cluster; khi gộp percentile đã tính tại từng instance, giá trị tổng hợp thay đổi khó giải thích.
API có p99 12 giây nhưng histogram Timer chỉ có bucket đến 1 giây; truy vấn ước lượng p99 từ Prometheus không thể phản ánh chính xác đuôi chậm mà log truy cập ghi nhận.
Nhóm bật percentile histogram cho toàn bộ Timer gồm hàng trăm tên route và nhiều tag; số time series tăng đột biến, bộ nhớ process cùng chi phí lưu trữ metrics đều cao hơn trước.
Một service cấu hình SLO buckets cho Timer với ngưỡng 100 ms, 300 ms và 1 giây, nhưng đội vận hành đánh giá ngưỡng 300 ms bằng biểu đồ duration trung bình thay vì tỷ lệ request nằm trong bucket.
Một API đọc dữ liệu chỉ chậm trong 1% request; sau khi bật histogram, p95 không đổi nhưng p99 tăng cao và nhóm đã từng dựa chỉ vào duration mean để kết luận không có vấn đề.
Hệ thống đo độ trễ gRPC bằng Timer nhưng dashboard đặt tên latency theo HTTP status; những response có grpc-status khác 0 vẫn được xếp vào nhóm thành công dù HTTP response là 200.
Người dùng thấy response chậm do truyền body lớn qua mạng, còn Timer của backend chỉ bao quanh handler đến khi trả đối tượng phản hồi; số liệu Micrometer không bao gồm thời gian gửi body thực tế.
Một ứng dụng có Timer cho API xuất báo cáo nhưng tác vụ được chuyển sang queue và endpoint trả 202 ngay; dashboard ghi latency thấp trong khi thời gian từ lúc nhận yêu cầu đến lúc file sẵn sàng kéo dài hàng phút.
Nhóm muốn đo một batch job kéo dài hàng giờ và theo dõi số job đang chạy cùng thời gian thực thi liên tục; Timer thông thường chỉ ghi duration khi kết thúc nên dashboard không hiển thị tiến độ thời gian của job còn chạy.
Một nhóm đo kích thước payload bằng DistributionSummary nhưng lại gọi record một lần cho mỗi KB thay vì ghi kích thước toàn request; số lượng sự kiện trong metric lớn hơn số request đã xử lý.
Ứng dụng dùng DistributionSummary theo dõi kích thước thông điệp trong byte nhưng đội vận hành gắn đơn vị kilobyte lên dashboard; ngưỡng cảnh báo message lớn bị sai lệch.
Đội muốn tính kích thước trung bình của file upload và chỉ thu thập tổng số byte; dashboard không có count quan sát tương ứng nên không thể phân biệt thay đổi dung lượng trung bình với tăng số upload.
DistributionSummary được cấu hình bucket theo kích thước 1 KB, 10 KB, 100 KB nhưng các file tải thực tế thường hơn 10 MB; biểu đồ phần trăm tải vượt 10 MB không đủ phân giải.
Nhóm đặt scale factor của DistributionSummary để chuẩn hóa dữ liệu tỷ lệ 0–1 thành phần trăm, nhưng dashboard tiếp tục coi giá trị ghi nhận là tỷ lệ thô; các biểu đồ vượt 100% hoặc có ngưỡng sai.
Service ghi kích thước response vào DistributionSummary tại controller trước khi JSON serialization; khi bật nén gzip, băng thông mạng giảm nhưng metric kích thước vẫn không đổi và đội phát triển chưa phân biệt payload logic với byte truyền đi.
Nhóm dùng DistributionSummary để đo số món hàng trong giỏ và gắn tag cart_id cho từng giỏ; Prometheus phải lưu chuỗi metric theo từng người dùng trong một chiến dịch flash sale.
Ứng dụng đo số bytes tải về bằng một Counter nhưng muốn phân tích phân phối kích thước mỗi response; dashboard chỉ có tổng bytes và không trả lời được bao nhiêu request lớn hơn 5 MB.
Trong Spring Boot, đội phát triển đã thêm dependency Micrometer nhưng không có registry xuất metrics phù hợp; endpoint Actuator hiển thị một số meter trong ứng dụng nhưng Prometheus không có dữ liệu scrape được.
Ứng dụng chạy tốt ở local với endpoint /actuator/prometheus nhưng môi trường production không mở quyền exposure cho endpoint này; Prometheus ghi scrape 404 trong khi health check vẫn xanh.
Một service chạy Spring Security và bảo vệ mọi đường dẫn bằng yêu cầu đăng nhập; sau bản phát hành, Prometheus bị trả 401 khi gọi /actuator/prometheus dù ứng dụng phục vụ request nghiệp vụ bình thường.
Prometheus scrape ứng dụng qua Kubernetes Service có port name trỏ tới cổng HTTP nghiệp vụ thay vì cổng management; target báo DOWN dù pod vẫn Ready và có metrics ở cổng khác.
Ứng dụng Spring Boot dùng management.server.port tách khỏi server.port, nhưng NetworkPolicy mới chỉ mở cổng nghiệp vụ; scrape metrics timeout còn các API vẫn hoạt động.
Nhóm chuyển đường dẫn Actuator sang base-path mới khi nâng phiên bản Spring Boot; ServiceMonitor tiếp tục scrape path cũ và dashboard ngừng cập nhật sau deploy.
Một thư viện Java tự tạo MeterRegistry khác với registry do Spring Boot quản lý; metric được ghi trong service không xuất hiện tại endpoint Actuator mà nhóm đang kiểm tra.
Ứng dụng đăng ký CompositeMeterRegistry và xuất cùng bộ meter tới Prometheus và một backend đẩy metrics; hai hệ giám sát hiển thị giá trị khác nhau khi chu kỳ thu thập và quy tắc temporality không tương đồng.
Ứng dụng đẩy metric tới một backend theo chu kỳ bước 60 giây, đồng thời Prometheus scrape registry khác mỗi 15 giây; hai dashboard biểu diễn số sự kiện theo các cửa sổ khác nhau mà đội vận hành lại so sánh từng điểm dữ liệu trực tiếp.
Một nhóm muốn quan sát số task hoàn thành theo phút nhưng lại nhìn vào giá trị Counter tích lũy tại endpoint Prometheus; dashboard liên tục tăng ngay cả khi tốc độ xử lý đang giảm.
Prometheus scrape cùng một pod qua hai ServiceMonitor bị trùng và coi hai target như hai series độc lập; phép cộng tổng request của dịch vụ tăng gần gấp đôi sau lần thay đổi cấu hình giám sát.
Ứng dụng dùng tag instance được gắn thủ công là tên máy cố định trong image; khi nhiều replica chạy cùng cấu hình, các series có nhãn trùng nhau và khó xác định từng pod đóng góp số liệu nào.
Đội phát triển gắn commonTags environment=staging trước khi triển khai Docker image lên production; dashboard tách theo môi trường cho thấy production thiếu số liệu dù endpoint metrics vẫn trả dữ liệu.
Nhóm thêm commonTags sau khi nhiều meter đã được đăng ký trong quá trình startup; một số metric xuất hiện với tag mới còn các meter tạo trước đó lại không có, khiến bộ lọc dashboard bỏ sót dữ liệu.
Ứng dụng ghi tag region cho các meter nhưng một nhóm dùng 'ap-southeast-1' và nhóm khác dùng 'singapore'; dashboard phân theo vùng hiển thị hai nhóm cho cùng địa điểm triển khai.
Một service tạo meter tên orders.processed với tag result=success và meter cùng tên với tag result=error, nhưng bộ phận dữ liệu gọi hai metric khác nhau trong biểu đồ và không nhận thấy cùng một quy ước nhãn.
Một ứng dụng ghi metric cho các loại thanh toán bằng tag provider có vài giá trị cố định, nhưng sau tích hợp đối tác mới tag lại dùng mã transaction do SDK trả về; số chuỗi thời gian tăng theo mỗi giao dịch.
HTTP server metrics dùng URI thực tế /customers/1847/orders/938 thay vì mẫu /customers/{id}/orders/{orderId}; backend metrics tăng hàng trăm nghìn series sau khi traffic tăng.
Một API có endpoint public và endpoint nội bộ nhưng tất cả request bị gắn tag uri=UNKNOWN do quy tắc mapping không khớp; dashboard không còn phân biệt route chậm trong hai nhóm endpoint.
Nhóm ghi email người dùng vào tag account để phân tích lỗi theo khách hàng; ngoài cardinality tăng, endpoint metrics còn vô tình công bố dữ liệu định danh trong hệ thống giám sát dùng chung.
MeterFilter giới hạn 100 giá trị khác nhau cho tag tenant, nhưng khi dịch vụ đạt 101 tenant, metrics của tenant mới không còn được đăng ký như nhóm sản phẩm mong đợi.
Đội triển khai MeterFilter từ chối metric HTTP có tag uri chứa số để giảm cardinality; sau cập nhật filter, metric của một API hợp lệ cũng biến mất và không có cảnh báo về thiếu dữ liệu.
Một thư viện dùng tag status là số HTTP 200, 404, 500 còn thư viện khác dùng success, error cho meter cùng tên; truy vấn Prometheus trên một tập tag không phản ánh đầy đủ tất cả request.
Trong quá trình đổi tên tag http.status sang status, nhóm phát hành ứng dụng mới và cũ cùng chạy; dashboard đang lọc theo tag mới chỉ thấy traffic ở các pod vừa được nâng cấp.
Ứng dụng ghi động mỗi giá trị product_id vào tag của Timer; dù request count mỗi product rất nhỏ, registry giữ ngày càng nhiều meter và bộ nhớ ứng dụng tăng trong phiên dài hạn.
Nhóm quản trị muốn xóa series cũ khi tenant rời hệ thống, nhưng ứng dụng đã tạo meter động gắn tenant_id; các meter và time series lịch sử còn tồn tại sau khi tenant không phát sinh request.
Một API chỉ dùng ba endpoint nhưng có tag exception từ message lỗi chứa địa chỉ file và mã khách; khi hệ thống gặp lỗi khác nhau liên tục, metric cardinality tăng bất thường dù traffic không đổi.
Nhóm bật histogram cho tất cả Timer và đồng thời nhân mỗi series theo method, status, uri, tenant và pod; cardinality kết hợp khiến số bucket metrics tăng nhanh hơn dự báo.
Service ghi metric theo tên kèm dấu chấm và dấu gạch ngang; registry Prometheus chuẩn hóa tên nhưng một dashboard cũ truy vấn tên trước khi chuẩn hóa nên báo không còn số liệu.
Hai meter có tên logic giống nhau nhưng một cái là Counter còn cái khác là Timer sau một lần refactor; hệ thống xuất metrics ghi nhận xung đột về loại hoặc tên và một trong các meter không được hiển thị như kỳ vọng.
Nhóm đặt chung tên meter cho hai DistributionSummary nhưng một loại ghi byte còn một loại ghi số lượng sản phẩm; biểu đồ sum và count trộn hai đại lượng không cùng đơn vị.
Một thư viện tự động instrument HTTP requests đã được Spring Boot bật sẵn, nhưng nhóm thêm filter thủ công cũng tăng Counter cùng tên cho mỗi request; tổng số lượt gọi tăng gấp đôi sau phát hành.
Nhóm bật instrumentation cho JDBC nhưng Timer tùy chỉnh đã đo cả thời gian chờ connection pool; khi cộng duration của hai metric, dashboard báo database chậm hơn thời gian người dùng thực tế trải nghiệm.
Spring Boot có metric JVM threads tự động, nhưng nhóm tạo Gauge threads_active bằng số thread HTTP; dashboard gộp hai metric khác định nghĩa và báo tổng thread không thể đối chiếu với thread dump.
Một ứng dụng dùng Timer recordCallable để đo thao tác gửi email nhưng việc gửi email thực sự xảy ra trên executor sau khi phương thức trả về; duration chỉ ghi thời gian đưa task vào hàng đợi.
Nhóm đăng ký Timer cho xử lý batch bằng annotation ở một phương thức được gọi nội bộ trong cùng Spring bean; AOP proxy không đi qua nên metric không tăng dù phương thức chạy thường xuyên.
Một scheduled job được gọi qua đường code không có request HTTP, còn nhóm giám sát chỉ dựa trên http.server.requests; khi job thất bại, dashboard ứng dụng vẫn cho thấy tỷ lệ request web thành công cao.
Service ghi một custom Counter cho login failures nhưng endpoint đăng nhập còn có rate limit ở gateway; log gateway có nhiều 429 mà metric ứng dụng không ghi nhận vì request không tới handler.
Một dịch vụ Java vừa chuyển từ Spring MVC sang WebFlux; dashboard Timer cũ đặt tại servlet filter không còn ghi đầy đủ các request bất đồng bộ và số lượng sample giảm sau deploy.
Một thư viện dùng Micrometer Observation để gắn thời gian và tag cho luồng xử lý; nhóm lại bọc cùng đoạn code bằng Timer thủ công nên cùng nghiệp vụ xuất hiện dưới hai tên và bị cộng lặp trong báo cáo.
Ứng dụng đo một request trải qua nhiều service bằng Timer tại gateway và Timer tại từng backend; dashboard cộng sum duration của các hop song song và kết luận latency end-to-end cao hơn thực tế.
Một Counter cho event published tăng trước khi broker xác nhận và Counter event consumed tăng sau khi xử lý; khi broker mất kết nối, số phát hành trên dashboard vẫn tăng dù event chưa tới consumer.
Trong integration test, nhóm dùng SimpleMeterRegistry kiểm tra Counter tăng khi thanh toán thất bại nhưng assertion chỉ kiểm tra metric tồn tại, không xác minh tag kết quả và số lần increment.
Một bài unit test sử dụng registry singleton được dùng chung giữa nhiều test class; Counter tích lũy từ test trước khiến test mới đôi lúc thất bại khi chạy cả suite nhưng chạy riêng lại thành công.
Một test tạo Gauge bằng AtomicInteger trong phương thức setup nhưng không giữ tham chiếu sau khi test chạy; kết quả kiểm tra giá trị gauge thay đổi ngẫu nhiên theo thời điểm garbage collection.
Nhóm kiểm thử Timer bằng Thread.sleep trên máy CI; test thỉnh thoảng thất bại vì scheduler và tải máy ảo làm duration thực tế vượt giới hạn mong đợi.
Một bài kiểm thử instrumentation chỉ đo nhánh thành công của method có exception và timeout; production lại xuất hiện lỗi ở nhánh thất bại, khiến metric failure không được tăng như kỳ vọng.
Một test kiểm tra metric http.server.requests bằng tag URI chứa ID cụ thể, nhưng cấu hình production chuẩn hóa URI thành template; test ở local và dashboard triển khai cho kết quả khác nhau.
Trong môi trường staging, Prometheus scrape mỗi 30 giây còn bài kiểm thử smoke test kiểm tra metric ngay sau khi gọi API; truy vấn tức thời không thấy giá trị mới dù endpoint metrics đã cập nhật.
Một đội muốn kiểm chứng rằng MeterFilter bảo vệ cardinality nhưng test chỉ tạo mười giá trị tag; khi production có hàng nghìn tenant, số series vượt ngân sách chưa được phát hiện từ trước.
Nhóm triển khai custom metric cho kích thước request và quên giới hạn bộ nhớ registry theo tag động; test tải kéo dài 30 phút cho thấy heap tăng dần mặc dù lượng dữ liệu nghiệp vụ được giải phóng.
Trong một diễn tập load test, metric Prometheus hiển thị rate request thấp hơn công cụ tạo tải; một phần request bị từ chối ở ingress trước khi vào ứng dụng và một phần request ở pod chưa được scrape.
Một cảnh báo ghi nhận timer p95 trên mỗi instance cao hơn 500 ms, nhưng báo cáo SLO tính toàn cluster từ histogram; hai biểu đồ cho kết luận trái ngược vì loại dữ liệu và cách tổng hợp khác nhau.
Nhóm đặt SLO 99% request dưới 300 ms nhưng chỉ có Timer count và sum mà không bật bucket phù hợp; dashboard không thể đếm trực tiếp số request vi phạm ngưỡng đã công bố.
Một bộ metric xuất lên Prometheus có nhãn outcome=SUCCESS nhưng code đặt outcome ngay trước khi gọi dependency cuối; khi dependency đó thất bại, sample lỗi vẫn nằm trong nhóm SUCCESS và alert không kích hoạt.
Ứng dụng trả HTTP 200 chứa lỗi nghiệp vụ trong JSON; metric HTTP tự động ghi status=200, còn Counter business_failure tăng đúng, khiến nhóm trực chưa thống nhất chỉ số nào đại diện cho tỷ lệ giao dịch thất bại.
Một hệ thống có các instance chạy phiên bản ứng dụng khác nhau; cùng một custom Timer tại bản cũ đo từ lúc nhận request, còn bản mới chỉ đo đoạn database; dashboard gộp dữ liệu tạo bước giảm latency giả khi rollout.
Sau khi tăng số pod gấp ba, tổng count từ Counter application tăng đột biến trên biểu đồ tích lũy dù rate đầu vào ổn định; nhiều series mới có điểm khởi đầu khác và dashboard chưa phân biệt reset với thay đổi tải.
Nhóm muốn giảm overhead instrumentation và tắt toàn bộ histogram khi CPU tăng; p99 dashboard trở nên không có dữ liệu nhưng nhóm vẫn diễn giải khoảng trống như hiệu năng đã cải thiện.
Một release thay đổi cấu hình percentiles và SLO của Timer, khiến số bucket thay đổi giữa pod cũ và pod mới trong rolling deployment; truy vấn histogram gộp gặp kết quả không nhất quán trong giai đoạn chuyển tiếp.
Ứng dụng ghi mỗi HTTP request vào Timer kèm tag tenant và request_type; sau khi bật thêm histograms, endpoint /actuator/prometheus xuất lượng dữ liệu lớn khiến mỗi lần scrape kéo dài hơn lịch đã định.
Đội vận hành đặt scrape interval rất ngắn để quan sát spike cỡ mili giây nhưng metric Timer chỉ ghi các lần thực thi hoàn tất; một số request đang treo dài không xuất hiện trong duration cho tới khi chúng kết thúc.
Nhóm tính tốc độ nhập dữ liệu bằng rate của Counter số bytes, trong khi dashboard trình bày đơn vị message/s; sau lần tăng kích thước message, biểu đồ throughput tăng dù số message mỗi giây không đổi.
Một service chỉ gặp GC pause lâu trên pod có traffic nhiều, nhưng metric JVM memory gộp theo service che khuất pod bất thường; dashboard chưa liên kết các số đo JVM với tên pod và phiên bản ứng dụng.
Sau khi thay đổi cấu hình MeterFilter, các metric của thư viện bên thứ ba có tiền tố tương tự metric nội bộ bị từ chối; dashboard JDBC pool và HTTP client mất dữ liệu mà không có thay đổi code nghiệp vụ.
Endpoint Actuator metrics bị mở công khai trong production; người ngoài truy cập có thể đọc tên database pool, đường dẫn API và các nhãn nội bộ dù endpoint không chứa thông tin đăng nhập.
Nhóm tạo custom metric dùng tên người dùng thật trong label để tìm kiếm dễ hơn; khi log và metrics được chuyển sang nhà cung cấp giám sát bên ngoài, chính sách chia sẻ dữ liệu không còn phù hợp với nội dung đã xuất.
Trong đợt lỗi Prometheus 5 phút, ứng dụng vẫn ghi Counter đều nhưng dashboard có khoảng trống; sau khôi phục, nhóm dùng tổng Counter theo thời gian và giả định mọi lần scrape đã xảy ra đúng lịch.
Một ứng dụng có Micrometer registry được cấu hình export tới hai hệ thống giám sát; trong lúc một backend đẩy metrics bị chậm, hàng đợi export tăng khiến thread thu thập metric cạnh tranh tài nguyên với luồng xử lý chính.
Đội chuyển từ push-based registry sang Prometheus pull nhưng vẫn giữ code flush metrics khi shutdown; trong Kubernetes, pod bị terminate quá nhanh trước lần scrape cuối nên một phần biến động cuối vòng đời không được phản ánh trực tiếp.
