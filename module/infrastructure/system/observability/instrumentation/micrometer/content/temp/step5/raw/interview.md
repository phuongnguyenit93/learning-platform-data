Bạn sẽ giải thích Micrometer giải quyết nhu cầu đo lường ứng dụng Java khác với việc tự ghi log số liệu như thế nào?
Bạn sẽ phân biệt metrics, logs và traces qua những loại câu hỏi vận hành mà từng loại dữ liệu có thể trả lời ra sao?
Bạn sẽ xác định các tín hiệu quan trọng cần đo cho một dịch vụ Java trước khi lựa chọn loại meter như thế nào?
Bạn sẽ xây dựng mục tiêu instrumentation từ SLI và SLO thay vì đo mọi biến có sẵn trong ứng dụng ra sao?
Bạn sẽ phân biệt dữ liệu về hành vi người dùng, hiệu năng ứng dụng và mức sử dụng tài nguyên khi thiết kế metric như thế nào?
Bạn sẽ đánh giá lợi ích của một facade đo lường như Micrometer khi hệ thống dùng nhiều backend giám sát ra sao?
Bạn sẽ giải thích vai trò của MeterRegistry trong việc tạo, quản lý và xuất metrics như thế nào?
Bạn sẽ mô tả mối quan hệ giữa meter name, meter type, tags, giá trị và time series khi dữ liệu được xuất ra backend ra sao?
Bạn sẽ phân biệt số liệu đo tại thời điểm hiện tại với số liệu tích lũy theo thời gian khi thiết kế dashboard như thế nào?
Bạn sẽ xác định những phép đo nào phải thực hiện ở client, server hoặc cả hai đầu để không bỏ sót thời gian chờ ra sao?
Bạn sẽ cân nhắc chi phí CPU, bộ nhớ và số chuỗi thời gian trước khi thêm một metric mới bằng cách nào?
Bạn sẽ chọn cách đặt tên metric sao cho nhất quán về đơn vị, phạm vi và ý nghĩa nghiệp vụ như thế nào?
Bạn sẽ phân biệt metric có hậu tố biểu thị đơn vị với tag biểu thị thuộc tính ngữ cảnh khi thiết kế tên ra sao?
Bạn sẽ xây dựng quy ước tên và mô tả metric để các nhóm có thể dùng chung dashboard mà không nhầm ý nghĩa như thế nào?
Bạn sẽ dựa trên tiêu chí nào để quyết định tái sử dụng metric chuẩn từ framework hay thêm metric tùy chỉnh?
Bạn sẽ giải thích counter dùng cho dữ liệu nào và vì sao không nên coi giá trị counter tích lũy là tốc độ sự kiện hiện tại?
Bạn sẽ chọn Counter để đo số yêu cầu thành công hoặc số lỗi nghiệp vụ và xác định nơi tăng counter ra sao?
Bạn sẽ thiết kế phép đo số lần retry để phân biệt request gốc với các lần thử lại như thế nào?
Bạn sẽ tránh đếm trùng một sự kiện khi cùng request đi qua controller, service và interceptor như thế nào?
Bạn sẽ phân biệt tăng counter khi một tác vụ được nhận, được bắt đầu và hoàn thành bằng cách đặt metric nào?
Bạn sẽ giải thích vì sao counter có thể trở về giá trị nhỏ sau khi ứng dụng restart và backend nên tính rate ra sao?
Bạn sẽ xử lý một dashboard hiển thị tổng counter giảm đột ngột khi một instance được thay thế như thế nào?
Bạn sẽ xác định khi nào sử dụng function counter thay cho counter được tăng chủ động dựa trên dữ liệu nguồn nào?
Bạn sẽ phân biệt counter sự kiện với gauge trạng thái hiện tại bằng trường hợp queue backlog như thế nào?
Bạn sẽ mô tả cách Gauge theo dõi số phần tử trong hàng đợi hoặc số tác vụ đang thực hiện ra sao?
Bạn sẽ chứng minh bằng ví dụ nào rằng gauge không thay thế được counter khi cần đếm sự kiện theo thời gian?
Bạn sẽ thiết kế gauge theo dõi số kết nối đang sử dụng trong connection pool và kiểm tra tính nhất quán của số liệu ra sao?
Bạn sẽ lựa chọn cách đọc gauge từ một đối tượng hoặc hàm cung cấp trạng thái thay vì cập nhật tay trong mọi nhánh code như thế nào?
Bạn sẽ kiểm tra vòng đời và tham chiếu đối tượng được gauge quan sát để tránh meter mất dữ liệu ngoài ý muốn ra sao?
Bạn sẽ diễn giải tình huống gauge hiển thị NaN, bằng không hoặc không còn được xuất sau một thay đổi mã nguồn như thế nào?
Bạn sẽ phân biệt gauge ở từng instance với tổng số tác vụ đang xử lý của toàn hệ thống khi tổng hợp dashboard ra sao?
Bạn sẽ đánh giá các giới hạn của gauge khi giá trị biến động nhanh hơn chu kỳ scrape như thế nào?
Bạn sẽ lựa chọn Timer để đo thời gian xử lý request hoặc nghiệp vụ thay vì chỉ ghi thời điểm bắt đầu và kết thúc trong log ra sao?
Bạn sẽ giải thích sự khác nhau giữa count, total time và max time mà một timer có thể cung cấp như thế nào?
Bạn sẽ xác định phạm vi bắt đầu và kết thúc timer để đo đúng độ trễ người dùng quan sát được ra sao?
Bạn sẽ sử dụng Timer.Sample để đo thời gian của một luồng xử lý có kết quả và nhãn chỉ xác định được lúc kết thúc như thế nào?
Bạn sẽ phân biệt thời gian xử lý thành công với thời gian bị timeout hoặc ném exception khi instrument timer ra sao?
Bạn sẽ chọn cách đo thời gian bất đồng bộ khi phương thức trả Future hoặc kết quả reactive bằng tiêu chí nào?
Bạn sẽ đánh giá nguy cơ timer chỉ đo thời gian tạo tác vụ mà bỏ qua thời gian thực thi bất đồng bộ như thế nào?
Bạn sẽ kiểm tra sai lệch giữa độ trễ timer ở controller và độ trễ HTTP mà client đo được bằng cách nào?
Bạn sẽ phân biệt Timer và LongTaskTimer khi muốn quan sát các tác vụ chạy hàng phút hoặc hàng giờ ra sao?
Bạn sẽ thiết kế phép đo số tác vụ dài đang hoạt động và thời gian đã chạy mà không chờ chúng hoàn tất như thế nào?
Bạn sẽ xác định khi nào dùng DistributionSummary để đo kích thước payload hoặc số lượng phần tử trong mỗi batch?
Bạn sẽ phân biệt DistributionSummary với Timer khi cùng có thống kê count, sum và phân phối giá trị ra sao?
Bạn sẽ lựa chọn base unit phù hợp cho DistributionSummary đo byte, item hoặc bản ghi như thế nào?
Bạn sẽ kiểm tra việc chuyển đổi đơn vị ở meter và backend để tránh hiểu nhầm millisecond, second và nanosecond ra sao?
Bạn sẽ mô tả cách MeterRegistry xử lý việc đăng ký lại meter cùng tên, loại và tập tag như thế nào?
Bạn sẽ xác định những hậu quả nào có thể xảy ra khi cùng tên metric được tạo với các loại meter hoặc nhãn không tương thích?
Bạn sẽ thiết kế lớp instrumentation dùng chung để tránh nhiều nơi trong code tạo meter với tên và tag khác nhau như thế nào?
Bạn sẽ lựa chọn lúc khởi tạo meter một lần so với tìm meter mỗi khi xử lý request dựa trên chi phí nào?
Bạn sẽ hạn chế việc tạo meter động theo dữ liệu từng request để tránh tăng bộ nhớ và cardinality như thế nào?
Bạn sẽ phân biệt registry dùng trong môi trường test với registry xuất dữ liệu thật trong môi trường production ra sao?
Bạn sẽ giải thích composite registry giúp gửi cùng bộ meter đến nhiều backend nhưng tạo ra những rủi ro nào?
Bạn sẽ xác định những trường hợp nên tắt hoặc giới hạn metric mặc định để giảm chi phí thu thập như thế nào?
Bạn sẽ phân biệt histogram, percentile và average khi diễn giải độ trễ request theo thời gian ra sao?
Bạn sẽ giải thích vì sao trung bình thấp không bảo đảm p95 hoặc p99 latency của ứng dụng tốt như thế nào?
Bạn sẽ lựa chọn phân phối bucket cho histogram thời gian xử lý dựa trên SLO và mức độ phân giải cần thiết ra sao?
Bạn sẽ cấu hình service-level objective boundaries cho timer theo các ngưỡng độ trễ nghiệp vụ như thế nào?
Bạn sẽ đánh giá rủi ro tạo quá nhiều bucket histogram đối với số chuỗi thời gian trong hệ thống giám sát ra sao?
Bạn sẽ phân biệt percentile tính tại client với percentile tính từ histogram trên backend về khả năng tổng hợp ra sao?
Bạn sẽ giải thích giới hạn của việc lấy trung bình p99 giữa các instance qua một ví dụ phân phối độ trễ như thế nào?
Bạn sẽ tổng hợp histogram từ nhiều instance để xem phân phối độ trễ toàn dịch vụ bằng cách nào?
Bạn sẽ chọn truy vấn rate, increase hoặc hàm lượng tử histogram phù hợp để tính tốc độ và phân vị từ metrics xuất ra ra sao?
Bạn sẽ nhận biết sự khác nhau giữa số request được đo bởi timer và số request được ghi bởi counter riêng như thế nào?
Bạn sẽ xử lý timer có ít sample khiến giá trị p99 biến động lớn hoặc không đủ ý nghĩa thống kê ra sao?
Bạn sẽ quyết định có nên bật histogram cho mọi endpoint hay chỉ những endpoint quan trọng bằng tiêu chí nào?
Bạn sẽ đánh giá ảnh hưởng của minimum expected value và maximum expected value đến số bucket và độ chính xác như thế nào?
Bạn sẽ phân biệt giá trị max trong cửa sổ đo của meter với giá trị lớn nhất từng xuất hiện trong lịch sử hệ thống ra sao?
Bạn sẽ kiểm tra trường hợp timer báo count tăng nhưng các series histogram không xuất hiện như mong đợi ra sao?
Bạn sẽ lựa chọn tag nào mô tả service, endpoint, HTTP method và status mà vẫn hỗ trợ truy vấn khoanh vùng như thế nào?
Bạn sẽ phân biệt tag có cardinality thấp và cao bằng ví dụ HTTP status, user ID và request ID ra sao?
Bạn sẽ so sánh số chuỗi thời gian khi gắn nhãn bằng URL chứa ID động và bằng route template ra sao?
Bạn sẽ chuẩn hóa đường dẫn có tham số thành route template trước khi gắn tag cho metric HTTP như thế nào?
Bạn sẽ thiết kế bộ tag riêng cho lỗi nghiệp vụ mà không đưa nội dung exception message vào nhãn ra sao?
Bạn sẽ ước lượng tổng số chuỗi thời gian theo tích số lượng giá trị của các tag trên một meter như thế nào?
Bạn sẽ xây dựng giới hạn cardinality theo service hoặc meter và xác định cách giám sát khi vượt ngưỡng ra sao?
Bạn sẽ dùng MeterFilter để chặn, đổi tên hoặc chuẩn hóa meter không mong muốn như thế nào?
Bạn sẽ áp dụng giới hạn số giá trị tag được phép cho một meter và thiết kế hành vi khi vượt giới hạn ra sao?
Những tiêu chí nào giúp bạn quyết định gộp các giá trị tag hiếm thành nhãn chung thay vì tạo time series mới?
Bạn sẽ xử lý tag tenant hoặc customer khi nhu cầu chẩn đoán theo khách hàng xung đột với ngân sách cardinality ra sao?
Bạn sẽ thiết kế cơ chế đo lỗi theo exception class mà không gắn thông điệp hoặc dữ liệu nhạy cảm làm tag như thế nào?
Bạn sẽ xác định các common tags nào cần thống nhất giữa các service và cách tránh lặp giá trị ra sao?
Bạn sẽ phân biệt tag instance, pod, environment và region theo nhu cầu nhóm hoặc tổng hợp metrics như thế nào?
Bạn sẽ kiểm soát metric tags được lấy từ input người dùng để tránh bùng nổ chuỗi thời gian hoặc lộ dữ liệu cá nhân ra sao?
Bạn sẽ đánh giá chi phí lưu trữ và truy vấn khi thêm một tag mới vào metric đã có lưu lượng lớn như thế nào?
Bạn sẽ thiết kế quy trình review instrumentation để phát hiện tên meter trùng, tag động và đơn vị không nhất quán ra sao?
Bạn sẽ lựa chọn cách thu hồi một metric dư thừa và cập nhật dashboard hoặc alert đang phụ thuộc vào nó như thế nào?
Bạn sẽ giải thích Micrometer tích hợp với Spring Boot Actuator để cung cấp metrics tự động và tùy chỉnh như thế nào?
Bạn sẽ xác định dependency và cấu hình cần có để Spring Boot xuất metrics cho một backend giám sát dự kiến ra sao?
Bạn sẽ kiểm tra endpoint Actuator cung cấp metrics có được bật và được phân quyền phù hợp như thế nào?
Bạn sẽ phân biệt endpoint liệt kê metrics với endpoint scrape dành cho Prometheus trong ứng dụng Spring Boot ra sao?
Bạn sẽ chọn các endpoint quản trị nào được công khai và endpoint nào chỉ cho phép truy cập nội bộ dựa trên chính sách nào?
Bạn sẽ xác định cách Micrometer tự đo HTTP server requests trong Spring Boot và các nhãn cần theo dõi ra sao?
Bạn sẽ kiểm tra phiên bản Spring Boot và Micrometer khi tên metric HTTP mặc định khác với dashboard cũ như thế nào?
Bạn sẽ bổ sung observation hoặc instrumentation cho một đoạn business logic mà không đo trùng với HTTP metric mặc định ra sao?
Bạn sẽ phân biệt tự động đo request tại web framework với đo thao tác trong service layer như thế nào?
Bạn sẽ sử dụng annotation đo thời gian trong trường hợp nào và kiểm tra các điều kiện để annotation có hiệu lực ra sao?
Bạn sẽ cân nhắc instrumentation thủ công và cơ chế interceptor hoặc AOP khi số phương thức cần đo tăng như thế nào?
Bạn sẽ thiết kế metric cho Scheduled task để phân biệt số lần chạy, thời gian chạy và số lần thất bại ra sao?
Bạn sẽ thiết kế metric cho message consumer để theo dõi tốc độ xử lý, độ trễ và backlog nhưng không đếm trùng sự kiện như thế nào?
Bạn sẽ instrument HTTP client hoặc RestClient trong Spring Boot để phân biệt độ trễ kết nối và thời gian upstream phản hồi ra sao?
Bạn sẽ xác định cách gắn tên route hoặc remote service cho metric outbound mà không đưa URL động vào tag như thế nào?
Bạn sẽ đo khả năng sử dụng thread pool, executor queue và active threads khi ứng dụng chạy tác vụ bất đồng bộ ra sao?
Bạn sẽ sử dụng metrics JVM về heap, GC và thread để giải thích hiện tượng API latency tăng như thế nào?
Bạn sẽ phân biệt số liệu memory từ JVM binder với RSS hoặc container memory metric khi tìm nguy cơ OOMKilled ra sao?
Bạn sẽ kiểm tra metric garbage collection khi nghi ngờ pause time tăng gây spike p99 latency như thế nào?
Bạn sẽ đánh giá kết hợp metrics về connection pool và thời gian request để chẩn đoán pool exhaustion ra sao?
Bạn sẽ quyết định mức độ instrumentation cho truy vấn cơ sở dữ liệu để tránh dùng SQL raw hoặc ID làm metric tags như thế nào?
Bạn sẽ tạo metric cho cache hit, cache miss hoặc cache eviction và đánh giá hiệu quả cache bằng cách nào?
Bạn sẽ xác định các meter mặc định của framework khác gì với meter nghiệp vụ tự tạo khi giải thích số liệu vận hành ra sao?
Bạn sẽ giải thích sự khác nhau giữa cách xuất metrics theo mô hình pull và push khi chọn backend phù hợp như thế nào?
Bạn sẽ thiết kế luồng Prometheus scrape từ ứng dụng qua endpoint metrics đến hệ thống lưu trữ và dashboard ra sao?
Bạn sẽ xác định cấu hình scrape interval và scrape timeout phù hợp với số lượng instance và độ nhạy phát hiện sự cố như thế nào?
Bạn sẽ so sánh MeterRegistry cho Prometheus với một registry xuất theo bước thời gian sang backend khác ra sao?
Bạn sẽ phân biệt temporality và cách backend xử lý counter tích lũy, delta hoặc histogram khi chuyển hệ xuất metrics như thế nào?
Bạn sẽ đối chiếu tên metric và đơn vị trong mã Java với dữ liệu backend nhận được để phát hiện khác biệt do quy ước xuất ra sao?
Bạn sẽ lần theo đường xuất metrics từ endpoint Actuator đến backend để tìm nguyên nhân thiếu dữ liệu như thế nào?
Bạn sẽ phân biệt scrape failure, target down và meter chưa phát sinh dữ liệu khi dashboard trống như thế nào?
Bạn sẽ kiểm tra firewall, Kubernetes Service và quyền truy cập khi Prometheus không scrape được endpoint metrics ra sao?
Bạn sẽ thiết kế nhãn phân biệt application, environment, instance và version trong quá trình scrape mà không bị xung đột nhãn như thế nào?
Bạn sẽ đánh giá ảnh hưởng của việc restart Pod đến các series counter và biểu đồ rate trên dashboard như thế nào?
Bạn sẽ lựa chọn một cửa sổ tính rate phù hợp để tránh kết quả quá nhiễu khi lưu lượng ít hoặc scrape gián đoạn như thế nào?
Bạn sẽ phân biệt metric missing với metric bằng không trong Prometheus khi phát hiện lỗi instrumentation ra sao?
Bạn sẽ thiết kế dashboard theo request rate, error rate, latency và saturation cho một ứng dụng Java như thế nào?
Bạn sẽ dùng histogram thời gian xử lý để xây dựng cảnh báo số request vượt ngưỡng SLO như thế nào?
Bạn sẽ xác định ngưỡng cảnh báo dựa trên tỷ lệ request lỗi thay vì số lỗi tuyệt đối trong một hệ thống có tải biến đổi ra sao?
Bạn sẽ kiểm tra timestamp, nhãn và target khi dashboard hiển thị số liệu từ phiên bản ứng dụng không mong đợi như thế nào?
Bạn sẽ đối chiếu dashboard với log hoặc trace để tìm nguồn gốc của một đợt tăng thời gian xử lý như thế nào?
Bạn sẽ sử dụng SimpleMeterRegistry trong unit test để xác minh số lần tăng counter của một luồng nghiệp vụ như thế nào?
Bạn sẽ viết kiểm thử cho timer để xác nhận thao tác thành công và thất bại đều được ghi nhận thời gian ra sao?
Bạn sẽ sử dụng clock có thể điều khiển trong test để kiểm chứng logic tính thời gian mà không phải chờ thời gian thực như thế nào?
Bạn sẽ kiểm tra gauge đọc đúng giá trị trạng thái sau khi đối tượng bị thay đổi trong test như thế nào?
Bạn sẽ xác minh metric đăng ký có tên, base unit, description và tập tag mong đợi bằng cách nào?
Bạn sẽ kiểm thử số lần retry để chứng minh counter chỉ tăng theo định nghĩa nghiệp vụ đã thống nhất ra sao?
Bạn sẽ viết kiểm thử bảo đảm exception được phát ra đúng nhưng timer vẫn ghi nhận duration như thế nào?
Bạn sẽ kiểm tra meter không tăng cardinality khi đầu vào request chứa nhiều path ID ngẫu nhiên ra sao?
Bạn sẽ xác minh MeterFilter chặn nhãn vượt ngưỡng hoặc metric bị cấm trong bài kiểm thử như thế nào?
Bạn sẽ dùng integration test Spring Boot để xác nhận endpoint metrics thực sự xuất dữ liệu sau khi gọi một API ra sao?
Bạn sẽ xây dựng kiểm thử phát hiện một sự kiện bị đếm trùng bởi metric chuẩn của framework và metric tùy chỉnh như thế nào?
Bạn sẽ lựa chọn điều kiện kiểm thử về histogram và bucket sao cho ít phụ thuộc chi tiết backend như thế nào?
Bạn sẽ thiết kế thử nghiệm tải để đo overhead CPU, RAM và thời gian xử lý do instrumentation mới gây ra ra sao?
Bạn sẽ xác định nguy cơ meter registration trong mỗi request tạo áp lực bộ nhớ bằng profiler hoặc metric nào?
Bạn sẽ kiểm tra hành vi của instrumentation khi registry tạm không xuất được dữ liệu nhưng ứng dụng vẫn phải xử lý request như thế nào?
Bạn sẽ thiết kế quy trình phát hành một metric mới gồm review, test, dashboard, alert và kế hoạch rollback như thế nào?
Bạn sẽ kiểm soát việc thay đổi tên hoặc nhãn metric giữa hai phiên bản ứng dụng để không làm dashboard bị đứt dữ liệu ra sao?
Bạn sẽ đánh giá nhu cầu tách metric kỹ thuật và metric nghiệp vụ để phân quyền truy cập và thời gian lưu trữ như thế nào?
Bạn sẽ thiết kế kiểm tra tự động để phát hiện metric không còn người dùng hoặc meter có cardinality tăng bất thường ra sao?
Bạn sẽ phân biệt tác động của instrumentation lên latency với tác động của exporter hoặc backend giám sát lên hệ thống như thế nào?
Bạn sẽ chọn những metric nào để chứng minh CPU thấp nhưng độ trễ request cao do connection pool hoặc hàng đợi?
Bạn sẽ điều tra khi metric HTTP 5xx tăng nhưng log ứng dụng không có exception bằng cách đối chiếu những nguồn dữ liệu nào?
Bạn sẽ xử lý trường hợp gauge số tác vụ đang chạy trở thành NaN sau khi thay đổi vòng đời đối tượng như thế nào?
Nếu Prometheus chỉ thấy một phần meter sau khi tăng lưu lượng, bạn sẽ kiểm tra cache meter, endpoint scrape và cardinality ra sao?
Nếu một endpoint mới làm số time series tăng đột biến, bạn sẽ xác định tag gây bùng nổ và sửa cách instrument như thế nào?
Nếu p99 latency cao ở một instance nhưng p99 tổng dịch vụ vẫn bình thường, bạn sẽ lựa chọn cách phân nhóm metric để khoanh vùng ra sao?
Nếu metric counter hiển thị giá trị thấp hơn hôm qua sau khi Pod restart, bạn sẽ giải thích và thiết kế truy vấn rate phù hợp như thế nào?
Nếu thời gian đo bởi timer trong Java thấp hơn đáng kể so với thời gian phản hồi client quan sát, bạn sẽ xác định các đoạn chưa được đo ra sao?
Nếu cảnh báo lỗi nghiệp vụ tăng nhưng throughput HTTP không thay đổi, bạn sẽ dùng counter và tag nào để kiểm chứng loại lỗi phát sinh?
Nếu kết quả integration test cho thấy Timer count cao gấp đôi số request, bạn sẽ kiểm tra các lớp instrumentation trùng nhau theo thứ tự nào?
Bạn sẽ thiết kế bộ metrics Micrometer cho một dịch vụ Spring Boot xử lý đơn hàng với HTTP API, database, queue và tác vụ nền, kèm chiến lược tag, test và dashboard như thế nào?
