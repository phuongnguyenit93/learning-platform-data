Bạn sẽ giải thích metric là gì và vì sao hệ thống cần metrics bên cạnh logs và distributed traces?
Bạn sẽ phân biệt dữ liệu đo theo thời gian với sự kiện đơn lẻ khi phân tích hành vi ứng dụng như thế nào?
Bạn sẽ xác định những câu hỏi vận hành cần trả lời trước khi quyết định tạo một metric mới ra sao?
Bạn sẽ phân biệt metrics phản ánh sức khỏe hạ tầng với metrics phản ánh trải nghiệm người dùng như thế nào?
Bạn sẽ lựa chọn các golden signals cho một API phục vụ request trực tuyến dựa trên tiêu chí nào?
Bạn sẽ áp dụng phương pháp RED và USE vào các thành phần khác nhau của một dịch vụ như thế nào?
Bạn sẽ xác định chủ sở hữu, ý nghĩa và đơn vị của một metric trước khi đưa nó vào dashboard ra sao?
Bạn sẽ phân biệt metric name, metric type, label set, sample và time series bằng một ví dụ cụ thể như thế nào?
Bạn sẽ giải thích vì sao cùng một metric name có thể tạo ra nhiều time series khác nhau?
Bạn sẽ mô tả chuỗi từ thao tác nghiệp vụ tới instrumentation, thu thập, lưu trữ và biểu đồ như thế nào?
Bạn sẽ phân biệt chỉ số có thể dùng để ra quyết định với chỉ số chỉ hấp dẫn về mặt trình bày ra sao?
Bạn sẽ kiểm tra liệu một metric mới có trùng mục đích với metric đã tồn tại trong hệ thống như thế nào?
Bạn sẽ giải thích Counter phù hợp với loại dữ liệu nào và vì sao giá trị tích lũy thông thường không giảm?
Bạn sẽ lựa chọn Counter cho request thành công, request lỗi và số lần retry như thế nào?
Bạn sẽ thiết kế bộ đếm sự kiện để tránh tăng hai lần khi cùng một request đi qua nhiều tầng ứng dụng ra sao?
Bạn sẽ mô tả hành vi của Counter khi tiến trình khởi động lại và cách hệ thống giám sát nhận biết reset như thế nào?
Bạn sẽ phân biệt giá trị Counter thô với tốc độ thay đổi của Counter trong một khoảng thời gian ra sao?
Khi phân tích Counter theo nhiều cửa sổ thời gian, bạn sẽ chọn rate hoặc increase dựa trên mục đích nào?
Bạn sẽ xác định cửa sổ tính rate phù hợp cho dịch vụ có lưu lượng thấp hoặc biến động mạnh ra sao?
Vì sao lấy hiệu trực tiếp hai giá trị Counter có thể sai sau một lần reset, và bạn sẽ tính thay thế ra sao?
Bạn sẽ tính tỷ lệ request thất bại từ hai Counter cùng phạm vi label và thời gian ra sao?
Bạn sẽ thiết kế Counter cho job đã xử lý với kết quả success, failed và skipped như thế nào?
Bạn sẽ phân biệt đếm số lần thử thanh toán với đếm số lần giao dịch nghiệp vụ được xác nhận thành công ra sao?
Bạn sẽ kiểm tra nguồn gây Counter tăng đột biến sau khi một retry mechanism được kích hoạt như thế nào?
Bạn sẽ đánh giá khi nào đếm số lượng lỗi theo error class phù hợp hơn tạo một metric riêng cho mỗi loại lỗi ra sao?
Bạn sẽ xử lý Counter của nhiều replica được thay thế khi autoscaling để tính tổng tốc độ toàn dịch vụ như thế nào?
Bạn sẽ giải thích Gauge phù hợp với những đại lượng tăng giảm theo trạng thái hệ thống như thế nào?
Bạn sẽ lựa chọn Gauge cho số request đang xử lý, độ sâu hàng đợi và dung lượng bộ nhớ đang sử dụng ra sao?
Bạn sẽ phân biệt Gauge ghi nhận trạng thái hiện tại với Counter ghi nhận tổng số sự kiện tích lũy như thế nào?
Bạn sẽ bảo đảm Gauge số tác vụ đang chạy quay về giá trị đúng sau exception hoặc cancellation bằng cơ chế nào?
Bạn sẽ xác định trường hợp nào nên đo Gauge trực tiếp từ nguồn dữ liệu thay vì tự tăng giảm bằng code?
Bạn sẽ phân tích ảnh hưởng của việc scrape Gauge thưa hơn tốc độ biến động thực tế như thế nào?
Bạn sẽ phân biệt trung bình, giá trị cực đại và giá trị cuối cùng của Gauge trong một khoảng thời gian ra sao?
Bạn sẽ giải thích vì sao tổng số connection đang mở trên các replica có ý nghĩa khác với trung bình connection mỗi replica?
Bạn sẽ lựa chọn Gauge hay Counter để theo dõi số message chưa được xử lý và số message đã xử lý như thế nào?
Bạn sẽ xử lý trường hợp Gauge hiển thị giá trị cũ khi exporter ngừng cập nhật nhưng endpoint vẫn được scrape như thế nào?
Bạn sẽ thiết kế Gauge đo thời gian kể từ lần thành công gần nhất của một batch job bằng cách nào?
Histogram lưu những thống kê nào để mô tả phân phối thời lượng request?
Bạn sẽ phân biệt Histogram với Counter và Gauge khi cần biết bao nhiêu request nhanh hơn ngưỡng SLA ra sao?
Bạn sẽ lựa chọn các bucket boundaries cho latency dựa trên mục tiêu trải nghiệm và phân phối quan sát được như thế nào?
Khi bucket quá rộng hoặc quá thưa, việc ước lượng percentile latency có thể bị ảnh hưởng ra sao?
Bạn sẽ giải thích ý nghĩa của các chuỗi bucket, count và sum trong Histogram truyền thống như thế nào?
Bạn sẽ kiểm tra đặc điểm cộng dồn của các bucket Histogram truyền thống khi đọc dữ liệu như thế nào?
Bạn sẽ tính số request nằm trong một khoảng latency từ các bucket cộng dồn ra sao?
Bạn sẽ tính tốc độ request và thời gian xử lý trung bình từ dữ liệu count và sum của Histogram như thế nào?
Bạn sẽ xác định ảnh hưởng của cấu hình bucket đến độ chính xác percentile ước lượng từ Histogram bằng cách nào?
Bạn sẽ lựa chọn P50, P95 hoặc P99 để đánh giá trải nghiệm của nhóm request chậm theo mục tiêu nào?
Bạn sẽ mô tả cách ước lượng P95 latency khi tổng hợp nhiều instance bằng các bucket tương thích như thế nào?
Bạn sẽ phân tích vì sao lấy trung bình P95 của các replica thường không cho P95 của toàn dịch vụ ra sao?
Bạn sẽ đánh giá sự đánh đổi giữa số lượng bucket, chi phí time series và độ chính xác thống kê như thế nào?
Bạn sẽ phân biệt Histogram latency và Histogram kích thước payload theo đơn vị và cách chọn bucket ra sao?
Bạn sẽ thiết kế Histogram cho thời gian thực thi truy vấn database với những nhãn nào để tránh cardinality quá cao?
Bạn sẽ giải thích khi nào một Histogram phù hợp hơn một Gauge lưu thời gian xử lý request gần nhất?
Bạn sẽ lựa chọn biểu đồ heatmap hoặc percentile line để trực quan hóa Histogram trong điều kiện nào?
Bạn sẽ phân biệt Histogram buckets dạng cổ điển và các cách biểu diễn histogram mới theo điều kiện hỗ trợ của hệ thống như thế nào?
Bạn sẽ kiểm tra độ ổn định của Histogram khi một phiên bản ứng dụng thay đổi ranh giới bucket trong lúc rollout ra sao?
Bạn sẽ giải thích Summary dùng để ghi nhận phân phối quan sát và những thông tin có thể được xuất ra như thế nào?
Bạn sẽ phân biệt cách Summary và Histogram tính hoặc ước lượng quantile như thế nào?
Bạn sẽ đánh giá ưu điểm của Summary khi cần quantile tại từng instance và giới hạn khi tổng hợp nhiều instance ra sao?
Bạn sẽ giải thích vì sao không thể cộng hoặc lấy trung bình trực tiếp quantile của Summary để suy ra quantile toàn cụm?
Bạn sẽ lựa chọn Summary hay Histogram cho latency của API khi cần dashboard toàn hệ thống như thế nào?
Bạn sẽ phân tích ảnh hưởng của cửa sổ quan sát Summary đến khả năng so sánh với metric rate trong dashboard ra sao?
Bạn sẽ chọn cách dùng count và sum do Summary xuất ra để tính thời lượng trung bình theo cửa sổ như thế nào?
Bạn sẽ xác minh hành vi của Summary khi số quan sát quá ít để quantile ổn định ra sao?
Bạn sẽ cân nhắc chi phí tính toán phía ứng dụng của Summary so với nhu cầu phân tích tập trung như thế nào?
Bạn sẽ giải thích time series được nhận diện bởi metric name và tập labels theo cách nào?
Bạn sẽ phân biệt timestamp của sample với thời gian diễn ra sự kiện nghiệp vụ khi dữ liệu được scrape muộn ra sao?
Bạn sẽ thiết kế một time series có nhãn service, environment và method để so sánh nhiều API như thế nào?
Bạn sẽ phân biệt label mang thuộc tính ổn định với giá trị thay đổi gần như mỗi request ra sao?
Bạn sẽ lựa chọn nhãn route template thay cho URL đầy đủ để theo dõi HTTP latency như thế nào?
Bạn sẽ giải thích vì sao user ID, session ID và trace ID thường không phù hợp làm metric labels?
Bạn sẽ xác định cardinality của một metric khi mỗi nhãn có nhiều giá trị và nhiều nhãn kết hợp như thế nào?
Bạn sẽ dự báo số time series nếu một metric được gắn nhãn service, region, status và endpoint ra sao?
Bạn sẽ kiểm tra sự khác nhau giữa số label values riêng lẻ và số tổ hợp label thực sự tồn tại như thế nào?
Bạn sẽ phân tích tác động của một nhãn có cardinality cao lên RAM, CPU, storage và tốc độ truy vấn ra sao?
Bạn sẽ phân biệt labels gắn tại instrumentation với resource attributes do môi trường chạy cung cấp như thế nào?
Bạn sẽ xây dựng quy ước tên metric và label sao cho nhiều nhóm ứng dụng có thể dùng thống nhất như thế nào?
Bạn sẽ xử lý thay đổi tên label hoặc tên metric mà không làm dashboard và alerting đứt dữ liệu như thế nào?
Bạn sẽ đánh giá khi nào cần bổ sung nhãn tenant và làm sao hạn chế nguy cơ lộ thông tin hoặc bùng nổ cardinality?
Bạn sẽ chọn các nhãn cần giữ lại hoặc loại bỏ trước khi đưa metric vào hệ thống lưu trữ như thế nào?
Bạn sẽ giải thích vì sao metrics không phù hợp làm nguồn lưu chi tiết từng request để điều tra một người dùng cụ thể?
Bạn sẽ liên kết metrics với logs và traces bằng những chiều tổng hợp nào mà không lưu trace ID trên time series?
Bạn sẽ xác định điều kiện nào khiến một metric bị chia thành nhiều time series ngoài ý muốn sau khi deploy ra sao?
Bạn sẽ thiết kế chiến lược ngăn tăng cardinality do error message hoặc exception text được dùng làm label như thế nào?
Bạn sẽ kiểm tra ảnh hưởng của nhãn có giá trị thay đổi theo phiên bản deployment đối với biểu đồ dài hạn ra sao?
Bạn sẽ phân biệt đơn vị seconds, milliseconds, bytes và ratio khi thiết kế tên cùng giá trị metric như thế nào?
Bạn sẽ lựa chọn đơn vị cơ sở thống nhất cho latency và dung lượng trước khi ghi metric ra sao?
Bạn sẽ phát hiện dashboard diễn giải sai do một service ghi duration bằng milliseconds còn service khác ghi seconds như thế nào?
Bạn sẽ phân biệt số lượng tuyệt đối, rate trên giây, tỷ lệ phần trăm và ratio không có đơn vị như thế nào?
Bạn sẽ lựa chọn quy tắc đặt hậu tố đơn vị trong metric name để người truy vấn không phải suy đoán ra sao?
Vì sao không thể cộng trực tiếp Gauge biểu diễn phần trăm CPU của nhiều máy, và bạn sẽ tổng hợp tín hiệu đó ra sao?
Bạn sẽ xác định đơn vị cần thể hiện trên trục biểu đồ khi vẽ latency, throughput và dung lượng còn lại như thế nào?
Bạn sẽ giải thích cửa sổ thời gian ảnh hưởng đến độ mượt và khả năng phát hiện đột biến của rate như thế nào?
Bạn sẽ so sánh cửa sổ một phút và một giờ khi tính error rate cho dịch vụ có traffic thay đổi mạnh ra sao?
Bạn sẽ phân biệt khoảng lấy mẫu, khoảng scrape, khoảng tính toán và độ phân giải biểu đồ như thế nào?
Bạn sẽ chọn khoảng scrape theo độ biến động tín hiệu, chi phí thu thập và yêu cầu phát hiện sự cố như thế nào?
Bạn sẽ đánh giá tác động của downsampling lên khả năng nhìn thấy spike ngắn trong dữ liệu metrics cũ ra sao?
Bạn sẽ giải thích vì sao không nên so sánh một rate theo giây với một Counter tích lũy trên cùng thang giá trị?
Bạn sẽ chọn khoảng thời gian hiển thị dashboard khi điều tra sự cố vừa xảy ra so với xu hướng năng lực nhiều tháng ra sao?
Bạn sẽ phân biệt metric tính từ một điểm đo tức thời với metric tổng hợp từ nhiều quan sát trong cửa sổ ra sao?
Bạn sẽ thiết kế điểm instrumentation cho một HTTP server để đo tổng số request, lỗi và latency như thế nào?
Bạn sẽ lựa chọn nơi tăng Counter trong luồng xử lý để phản ánh chính xác kết quả cuối của request ra sao?
Bạn sẽ ghi nhận duration bằng đồng hồ đo phù hợp để hạn chế sai số do đồng hồ hệ thống bị chỉnh như thế nào?
Bạn sẽ thiết kế instrumentation cho bước gọi database để phân biệt thời gian chờ connection và thời gian thực thi query ra sao?
Bạn sẽ xác định các metric cần thiết cho một worker xử lý hàng đợi gồm backlog, throughput, retry và duration như thế nào?
Bạn sẽ instrument một batch job để phát hiện chạy trễ, thất bại và tiến độ xử lý theo từng giai đoạn ra sao?
Bạn sẽ phân biệt metrics do ứng dụng tự tạo với metrics từ runtime JVM, container và node như thế nào?
Bạn sẽ tránh ghi trùng cùng một request vào metrics ở API gateway và backend khi tính SLI người dùng như thế nào?
Bạn sẽ xác định chỗ nào cần instrument ở tầng thư viện và chỗ nào cần instrument theo nghiệp vụ để tránh đo lặp ra sao?
Bạn sẽ đánh giá ảnh hưởng của việc tạo labels từ tham số động của method lên số time series như thế nào?
Bạn sẽ kiểm soát các phép đo âm, không hợp lệ hoặc vượt miền giá trị khi instrument duration và kích thước payload như thế nào?
Bạn sẽ thiết kế metric cho xử lý retry để tách lần thử kỹ thuật khỏi một giao dịch nghiệp vụ duy nhất như thế nào?
Bạn sẽ phân biệt metric xử lý thành công với metric gửi response thành công trong trường hợp client ngắt kết nối ra sao?
Bạn sẽ viết bài kiểm thử xác minh Counter tăng đúng một lần và Gauge quay về trạng thái ban đầu sau exception như thế nào?
Bạn sẽ kiểm thử Histogram có ghi nhận đúng số quan sát và ranh giới bucket bằng những ví dụ nào?
Theo những tiêu chí nào bạn sẽ chọn instrumentation library hoặc framework metrics thay vì tự viết logic thu thập?
Bạn sẽ kiểm tra tác động của việc instrument quá nhiều event lên thời gian phản hồi ứng dụng và bộ nhớ ra sao?
Bạn sẽ giải thích mô hình thu thập metrics kiểu pull và push khác nhau về cách phát hiện endpoint như thế nào?
Bạn sẽ mô tả luồng từ ứng dụng xuất metrics đến scraper và hệ thống lưu trữ time series như thế nào?
Bạn sẽ thiết kế endpoint metrics cho ứng dụng mà không vô tình công khai dữ liệu vận hành ra Internet ra sao?
Bạn sẽ phân biệt scrape target không truy cập được với target hoạt động nhưng không phát metric cần thiết như thế nào?
Bạn sẽ xác định những thông số của scrape như interval và timeout phù hợp với số lượng instance và tải hệ thống ra sao?
Bạn sẽ xử lý trường hợp thời gian xuất metrics của ứng dụng dài hơn scrape timeout theo những hướng nào?
Metric up của target thể hiện điều gì về lần scrape và không thể khẳng định điều gì về sức khỏe ứng dụng?
Bạn sẽ phân tích sự khác nhau giữa dữ liệu bị thiếu, giá trị bằng không và chuỗi đã trở nên stale ra sao?
Bạn sẽ nhận diện Counter reset sau restart khi kết hợp metrics với lifecycle của Pod như thế nào?
Bạn sẽ đánh giá ảnh hưởng của autoscaling và Pod churn đối với số time series đang hoạt động trong hệ thống như thế nào?
Bạn sẽ thiết kế discovery targets để theo dõi Pod mới mà không giữ mãi endpoint của Pod đã bị xóa như thế nào?
Bạn sẽ xác định cách gắn resource labels cho metrics thu thập từ Kubernetes nhằm phân biệt cluster và namespace ra sao?
Bạn sẽ so sánh exporter, sidecar và thư viện instrumentation trong ứng dụng theo chi phí triển khai như thế nào?
Bạn sẽ xác định rủi ro và giới hạn của push gateway khi dùng cho batch jobs có vòng đời ngắn ra sao?
Bạn sẽ thiết kế chính sách xác thực, phân quyền và mã hóa khi scraper truy cập các endpoint metrics nội bộ như thế nào?
Nếu quá trình thu thập metrics thất bại, dashboard và alerting có thể diễn giải nhầm trạng thái dịch vụ ra sao?
Bạn sẽ kiểm tra chênh lệch timestamp hoặc scrape lag khi một metric xuất hiện muộn trong dashboard ra sao?
Bạn sẽ thiết kế quy trình kiểm tra khi cùng một target bị scrape hai lần và dữ liệu bị trùng như thế nào?
Bạn sẽ phân biệt tổng hợp Counter theo instance với việc cộng các rate đã được xử lý reset như thế nào?
Bạn sẽ giải thích vì sao tính rate trước rồi mới sum theo service thường an toàn hơn cộng Counter thô rồi tính rate?
Bạn sẽ xây dựng phép tổng hợp request rate theo service và status mà vẫn giữ nhãn cần thiết để điều tra như thế nào?
Bạn sẽ phân biệt sum, avg, min, max và count khi áp dụng lên Gauge ở nhiều instance ra sao?
Bạn sẽ tính tỷ lệ lỗi toàn dịch vụ từ tổng tốc độ lỗi và tổng tốc độ request thay vì trung bình tỷ lệ lỗi từng instance như thế nào?
Bạn sẽ xác định cách xử lý mẫu số bằng không khi tính error ratio mà không hiển thị kết quả sai ra sao?
Bạn sẽ chọn cửa sổ rate đủ dài để có mẫu nhưng đủ ngắn để phát hiện thay đổi sau rollout như thế nào?
Bạn sẽ mô tả cách tổng hợp histogram buckets theo service trước khi ước lượng P95 latency ra sao?
Bạn sẽ phân biệt bucket aggregation đúng với việc trung bình các quantile từng instance như thế nào?
Bạn sẽ xác định label nào phải giữ khi tổng hợp histogram buckets để phép tính quantile vẫn hợp lệ ra sao?
Bạn sẽ xây dựng biểu đồ throughput và error rate để nhìn được sự khác biệt giữa traffic tăng và tỷ lệ lỗi tăng như thế nào?
Bạn sẽ lựa chọn biểu đồ time series, stacked area, bar chart hoặc heatmap dựa trên câu hỏi phân tích nào?
Bạn sẽ giải thích vì sao hai biểu đồ cùng dữ liệu nhưng trục Y hoặc khoảng thời gian khác nhau có thể dẫn đến kết luận trái ngược?
Bạn sẽ phát hiện hiện tượng biểu đồ bị làm mượt quá mức khiến spike ngắn bị che khuất ra sao?
Bạn sẽ đánh giá độ chính xác của biểu đồ khi số điểm hiển thị ít hơn đáng kể số sample gốc như thế nào?
Bạn sẽ thiết kế dashboard cho API gồm throughput, latency, errors và saturation với thứ tự ưu tiên như thế nào?
Bạn sẽ sử dụng metric theo region hoặc availability zone để phát hiện lỗi cục bộ bị trung bình toàn hệ thống che lấp ra sao?
Bạn sẽ phân biệt sự thay đổi mức tải với thay đổi hiệu suất khi CPU tăng nhưng request rate cũng tăng như thế nào?
Bạn sẽ diễn giải tình huống P99 latency tăng trong khi P50 ổn định bằng những giả thuyết nào?
Bạn sẽ phân tích nguyên nhân Gauge queue depth liên tục tăng dù Counter processed jobs vẫn tăng theo thời gian ra sao?
Bạn sẽ kết hợp metrics của runtime, database pool và HTTP server để tìm nút thắt gây tăng latency như thế nào?
Bạn sẽ xác định một biểu đồ đang phản ánh dữ liệu thực hay chỉ dữ liệu cũ còn tồn tại sau khi target chết như thế nào?
Bạn sẽ chọn annotation thời điểm deployment để liên hệ sự thay đổi metric với thay đổi ứng dụng ra sao?
Bạn sẽ thiết kế các truy vấn so sánh cùng khung giờ giữa hai ngày để kiểm tra tính mùa vụ của lưu lượng như thế nào?
Bạn sẽ lựa chọn phương pháp nhận diện lỗi hệ thống giám sát khi một dashboard đột ngột mất toàn bộ dữ liệu ra sao?
Bạn sẽ phân biệt SLI và SLO với chính metric dùng để tính chúng theo mục đích và mức trừu tượng ra sao?
Bạn sẽ lựa chọn tập request hợp lệ làm mẫu số của availability SLI cho một dịch vụ như thế nào?
Bạn sẽ tính availability SLI từ các Counter request thành công và thất bại sau khi loại traffic không thuộc phạm vi ra sao?
Bạn sẽ thiết kế latency SLI theo tỷ lệ request hoàn thành trong ngưỡng thay vì chỉ lấy trung bình latency như thế nào?
Bạn sẽ lựa chọn histogram bucket trùng ngưỡng latency SLO để giảm sai số đo tỷ lệ đạt mục tiêu như thế nào?
Bạn sẽ đánh giá các giới hạn của percentile latency khi dùng nó làm mục tiêu SLO so với tỷ lệ request dưới ngưỡng như thế nào?
Bạn sẽ phân biệt SLI cho dịch vụ ít request với SLI của dịch vụ có lưu lượng lớn khi lựa chọn cửa sổ và phép đo ra sao?
Bạn sẽ giải thích error budget được tính từ SLO và lượng traffic quan sát trong cửa sổ đánh giá như thế nào?
Bạn sẽ thiết kế tín hiệu burn rate dựa trên error ratio và error budget để nhận biết nguy cơ cạn ngân sách lỗi ra sao?
Bạn sẽ cân nhắc kết hợp cửa sổ ngắn và dài cho cảnh báo SLO để giảm false positive như thế nào?
Bạn sẽ xác định điều gì xảy ra khi một SLI bị mất dữ liệu do scrape lỗi nhưng alert rule vẫn cần đánh giá rủi ro?
Bạn sẽ sử dụng metrics để phân biệt sự cố ảnh hưởng người dùng với mức tiêu thụ tài nguyên cao nhưng chưa gây lỗi ra sao?
Bạn sẽ thiết kế tiêu chí thống nhất metric và SLI giữa các phiên bản API khác nhau như thế nào?
Bạn sẽ lựa chọn thời hạn lưu trữ và độ phân giải dữ liệu để tính SLO dài hạn nhưng vẫn kiểm soát chi phí ra sao?
Bạn sẽ phân tích nguyên nhân kết quả tính SLI trên dashboard và báo cáo định kỳ không khớp nhau như thế nào?
Bạn sẽ thiết kế quy trình review metric khi một nhãn hoặc định nghĩa request success thay đổi qua bản phát hành ra sao?
Bạn sẽ kiểm thử một metric mất sau deploy bằng cách truy ngược từ dashboard, scraper, endpoint đến instrumentation như thế nào?
Bạn sẽ phát hiện lỗi Counter tăng hai lần do instrumentation trùng bằng những phép thử nào?
Bạn sẽ kiểm tra histogram có bucket sai đơn vị sau nâng cấp framework khi P95 xuất hiện đột biến như thế nào?
Bạn sẽ phân tích nguyên nhân số lượng time series tăng mạnh sau khi thêm một label động và phương án khắc phục ra sao?
Bạn sẽ tổ chức bài thử tải để đo chi phí CPU, RAM và lưu lượng mạng của instrumentation và scrape như thế nào?
Bạn sẽ kiểm tra tính đúng đắn của metrics khi ứng dụng xử lý exception, timeout, retry và cancellation bằng cách nào?
Bạn sẽ thiết kế cảnh báo về mục tiêu scrape bị lỗi mà không nhầm với cảnh báo dịch vụ không sẵn sàng như thế nào?
Khi error rate tăng ở một region nhưng biểu đồ toàn cầu gần như không đổi, bạn sẽ điều tra bằng những phép phân tách nào?
Bạn sẽ đánh giá khi nào metrics chưa đủ để tìm root cause và cần chuyển sang traces hoặc logs ra sao?
Bạn sẽ đặt các tiêu chí nghiệm thu nào cho tính đúng đắn, đơn vị, labels, cardinality, độ mới, chi phí và khả năng dùng metrics trong SLI/SLO trước khi triển khai sản xuất?
