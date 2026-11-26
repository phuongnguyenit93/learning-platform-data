Bạn sẽ giải thích mục tiêu chính của logging trong observability khác với monitoring metrics và distributed tracing như thế nào?
Bạn sẽ phân biệt log event, metric measurement và trace span bằng một tình huống request thất bại ra sao?
Những tiêu chí nào giúp bạn xác định một sự kiện đáng ghi log thay vì chỉ xử lý âm thầm trong ứng dụng?
Bạn sẽ phân loại log theo nguồn phát, mục đích sử dụng và đối tượng cần đọc bằng cách nào?
Bạn sẽ giải thích vì sao một hệ thống cần nhiều loại log thay vì dùng một luồng thông điệp chung?
Bạn sẽ thiết kế sơ đồ các nguồn log của một hệ thống web có frontend, API, database và Kubernetes như thế nào?
Bạn sẽ lựa chọn những thông tin tối thiểu nào để người trực xác định thời điểm và vị trí phát sinh sự kiện?
Bạn sẽ phân biệt sự kiện nghiệp vụ với sự kiện kỹ thuật khi cả hai đều xuất hiện trong cùng một request như thế nào?
Bạn sẽ xác định chủ sở hữu, mục đích sử dụng và chính sách truy cập của từng loại log trước khi vận hành như thế nào?
Bạn sẽ đánh giá những trường hợp nào nên ghi log liên tục và những trường hợp nào chỉ nên ghi khi có bất thường?
Bạn sẽ giải thích application log phản ánh hành vi và trạng thái của ứng dụng ở những cấp độ nào?
Bạn sẽ lựa chọn các sự kiện trong vòng đời khởi động, xử lý request và shutdown đáng ghi vào application log ra sao?
Bạn sẽ thiết kế application log cho một tác vụ nền không có HTTP request để vẫn theo dõi được tiến độ như thế nào?
Bạn sẽ xác định ranh giới giữa log trạng thái ứng dụng và log chi tiết từng bước triển khai thuật toán ra sao?
Bạn sẽ đánh giá tác động của việc ghi toàn bộ dữ liệu đầu vào vào application log về dung lượng và quyền riêng tư như thế nào?
Bạn sẽ sử dụng log để phân biệt lỗi cấu hình, lỗi phụ thuộc bên ngoài và lỗi logic ứng dụng ra sao?
Bạn sẽ thiết kế thông điệp log mô tả sự kiện cụ thể thay vì chỉ ghi một chuỗi chung chung như thế nào?
Bạn sẽ quyết định đặt log ở lớp controller, service hay repository dựa trên thông tin cần điều tra như thế nào?
Bạn sẽ ngăn việc nhiều lớp trong ứng dụng cùng ghi một lỗi gây trùng lặp log bằng cách nào?
Bạn sẽ tổ chức logging khi một background job có nhiều bước và có thể chạy lại sau thất bại như thế nào?
Bạn sẽ giải thích access log giúp trả lời những câu hỏi gì về traffic đến API hoặc web server?
Bạn sẽ lựa chọn các trường như phương thức HTTP, đường dẫn, status, thời gian xử lý và kích thước phản hồi trong access log ra sao?
Bạn sẽ phân biệt access log của reverse proxy với access log do ứng dụng tạo theo góc nhìn và thời gian đo như thế nào?
Bạn sẽ thiết kế access log khi request đi qua CDN, load balancer và API gateway để không đếm nhầm số lượt truy cập ra sao?
Bạn sẽ phân biệt địa chỉ IP nguồn thực tế với IP của proxy khi xử lý các header chuyển tiếp như thế nào?
Bạn sẽ xác định điều kiện tin cậy của X-Forwarded-For hoặc thông tin client IP từ proxy ra sao?
Bạn sẽ chọn cách biểu diễn URL, query string và route template để vừa phân tích traffic vừa tránh lưu token bí mật như thế nào?
Bạn sẽ phân biệt request hoàn tất bình thường, client ngắt kết nối và upstream timeout qua access log ra sao?
Bạn sẽ liên kết access log với log ứng dụng khi một request nhận HTTP 502 nhưng ứng dụng không ghi exception như thế nào?
Bạn sẽ sử dụng access log để phân tích thay đổi tỷ lệ 4xx, 5xx và latency sau một lần triển khai ra sao?
Bạn sẽ giải thích error log khác application log thông thường về nội dung và nhu cầu xử lý như thế nào?
Bạn sẽ lựa chọn những thông tin nào phải có trong error log để tái hiện và khoanh vùng một lỗi bất thường?
Bạn sẽ phân biệt mã lỗi nghiệp vụ dự kiến với exception ngoài dự kiến khi quyết định ghi ở mức ERROR ra sao?
Bạn sẽ xử lý stack trace trong error log sao cho đủ ngữ cảnh nhưng không gây trùng lặp ở nhiều tầng như thế nào?
Bạn sẽ ghi nhận chuỗi nguyên nhân exception để không mất root cause khi lỗi bị bọc qua nhiều lớp như thế nào?
Bạn sẽ cân nhắc khi nào ghi toàn bộ stack trace, khi nào chỉ ghi mã lỗi và thông điệp ngắn?
Bạn sẽ phân tích rủi ro ghi nguyên payload hoặc thông tin xác thực khi xử lý exception như thế nào?
Bạn sẽ phân biệt error log từ ứng dụng với lỗi kết nối được ghi bởi database driver hoặc reverse proxy ra sao?
Bạn sẽ thiết kế log cho một request lỗi nhưng được retry thành công để người trực không hiểu nhầm kết quả cuối như thế nào?
Bạn sẽ chọn mức độ nghiêm trọng của log theo tác động thực tế thay vì dựa duy nhất vào tên exception như thế nào?
Bạn sẽ giải thích security log ghi nhận những hoạt động nào liên quan xác thực, phân quyền và hành vi bất thường?
Bạn sẽ lựa chọn sự kiện đăng nhập thành công, đăng nhập thất bại và tài khoản bị khóa để ghi security log như thế nào?
Bạn sẽ phân biệt sự kiện bị từ chối quyền truy cập với lỗi xử lý thông thường khi phân tích security log ra sao?
Bạn sẽ thiết kế log cho hành vi thay đổi quyền, xoay vòng credential hoặc sử dụng tài khoản đặc quyền như thế nào?
Bạn sẽ xác định những dấu hiệu có thể là brute-force, dò quét endpoint hoặc lạm dụng API từ chuỗi security log ra sao?
Bạn sẽ lựa chọn trường nhận dạng chủ thể, nguồn yêu cầu, hành động và kết quả trong security log mà không ghi secret như thế nào?
Bạn sẽ phân biệt thông tin về IP, thiết bị hoặc vị trí người dùng có ích cho an ninh với dữ liệu cần hạn chế thu thập ra sao?
Bạn sẽ thiết kế cảnh báo dựa trên security log mà tránh kết luận nhầm nhiều lần đăng nhập thất bại là tấn công như thế nào?
Bạn sẽ phân tích tác động của việc client điều khiển nội dung message làm giả dòng log hoặc chèn ký tự xuống dòng ra sao?
Bạn sẽ mô tả cách security log hỗ trợ điều tra một phiên đăng nhập bị đánh cắp mà vẫn bảo vệ dữ liệu nhạy cảm như thế nào?
Bạn sẽ giải thích audit log cần bảo đảm những thuộc tính nào để phục vụ truy cứu trách nhiệm và kiểm chứng thay đổi?
Bạn sẽ phân biệt audit log với debug log và security log theo độ tin cậy, nội dung và chính sách lưu giữ như thế nào?
Bạn sẽ thiết kế bản ghi kiểm toán cho thao tác sửa thông tin tài khoản gồm chủ thể, hành động, thời gian và kết quả ra sao?
Bạn sẽ ghi nhận danh tính người thực hiện thay đổi khi thao tác đi qua service account hoặc hệ thống ủy quyền như thế nào?
Bạn sẽ phân biệt thời điểm yêu cầu thay đổi với thời điểm thay đổi thực sự được commit trong audit log ra sao?
Bạn sẽ xử lý trường hợp nghiệp vụ rollback transaction sau khi một sự kiện audit đã được tạo như thế nào?
Bạn sẽ đánh giá các phương án bảo đảm audit event không bị mất khi ứng dụng gặp lỗi sau khi ghi dữ liệu như thế nào?
Bạn sẽ thiết kế quyền truy cập và cơ chế ngăn sửa hoặc xóa audit log trái phép ra sao?
Bạn sẽ phân biệt lưu trữ bất biến, chữ ký kiểm tra toàn vẹn và kiểm soát truy cập trong bảo vệ audit log như thế nào?
Bạn sẽ cân nhắc quy định và thời hạn lưu giữ audit log theo rủi ro nghiệp vụ và yêu cầu tuân thủ ra sao?
Bạn sẽ xác minh audit trail đủ để tái dựng chuỗi thay đổi khi một bản ghi được sửa qua nhiều ứng dụng như thế nào?
Bạn sẽ giải thích business log giúp theo dõi trạng thái của đơn hàng, thanh toán và quy trình nghiệp vụ như thế nào?
Bạn sẽ phân biệt business event log với audit trail và transaction log của cơ sở dữ liệu ra sao?
Bạn sẽ chọn các mốc chuyển trạng thái quan trọng của một đơn hàng cần ghi business log như thế nào?
Bạn sẽ thiết kế correlation ID nghiệp vụ để theo dõi một đơn hàng qua nhiều request và message như thế nào?
Bạn sẽ ghi nhận trạng thái trước và sau của một nghiệp vụ mà không đưa dữ liệu nhạy cảm dư thừa vào log ra sao?
Bạn sẽ phân biệt một giao dịch bị từ chối theo quy tắc nghiệp vụ với sự cố kỹ thuật khi biểu diễn trong business log như thế nào?
Bạn sẽ xử lý business log trong luồng bất đồng bộ có thể phát lại message để tránh hiểu nhầm sự kiện trùng là hoạt động mới ra sao?
Bạn sẽ thiết kế business log để hỗ trợ chăm sóc khách hàng nhưng không cho phép người đọc truy cập thông tin ngoài thẩm quyền như thế nào?
Bạn sẽ liên kết business log với tracing kỹ thuật mà không sử dụng trace ID làm khóa định danh nghiệp vụ lâu dài ra sao?
Bạn sẽ cân nhắc dùng event store chính thức thay vì business log để tái tạo trạng thái khi cần độ tin cậy cao như thế nào?
Bạn sẽ giải thích infrastructure log phản ánh những nguồn nào trong hệ điều hành, container, orchestrator và mạng?
Bạn sẽ phân biệt log từ node, container runtime, kubelet, ingress và ứng dụng chạy bên trong container ra sao?
Bạn sẽ tìm thông tin nào trong log hệ điều hành khi máy chủ bị thiếu bộ nhớ hoặc khởi động lại bất thường?
Bạn sẽ sử dụng Kubernetes events và container logs kết hợp như thế nào khi Pod liên tục restart?
Bạn sẽ phân biệt thông điệp ứng dụng ngừng phục vụ với thông tin container bị OOMKilled hoặc bị eviction ra sao?
Bạn sẽ chọn log từ DNS, load balancer và firewall để điều tra lỗi kết nối giữa hai dịch vụ theo cách nào?
Bạn sẽ phân tích khác biệt giữa database server log, slow query log và application error log khi truy vấn chậm như thế nào?
Bạn sẽ xác định nguồn log nào cần xem đầu tiên khi người dùng báo một endpoint lúc được lúc không trong giờ cao điểm?
Bạn sẽ thiết kế nhãn chuẩn hóa service, namespace, pod và node để kết hợp infrastructure log với application log ra sao?
Bạn sẽ xác minh đồng bộ timestamp giữa nhiều máy trước khi sắp xếp các sự kiện từ hạ tầng như thế nào?
Bạn sẽ giải thích những log level phổ biến như TRACE, DEBUG, INFO, WARN và ERROR phản ánh mức độ thông tin nào?
Bạn sẽ lựa chọn log level cho các sự kiện khởi động, request thành công, retry, validation failure và exception như thế nào?
Bạn sẽ phân biệt WARNING về nguy cơ sắp xảy ra với ERROR thể hiện một thao tác đã thất bại ra sao?
Bạn sẽ phân tích vì sao không nên ghi mọi lỗi HTTP 4xx ở mức ERROR khi nhiều lỗi là hành vi người dùng bình thường?
Bạn sẽ thiết kế chính sách bật DEBUG tạm thời trong production theo phạm vi và thời hạn cụ thể như thế nào?
Bạn sẽ đánh giá chi phí của TRACE hoặc DEBUG đối với CPU, I/O, hệ thống thu thập và khả năng lộ dữ liệu như thế nào?
Bạn sẽ xử lý tình huống một thư viện bên thứ ba tạo quá nhiều log ở cùng mức severity bằng cách nào?
Bạn sẽ phân biệt log level với mức độ ưu tiên xử lý incident và severity của cảnh báo như thế nào?
Bạn sẽ thiết kế cơ chế thay đổi log level động mà vẫn có quyền kiểm soát và lịch sử thay đổi ra sao?
Bạn sẽ xác định sự kiện quan trọng nào vẫn cần ghi ngay cả khi giảm mức độ chi tiết để tiết kiệm tài nguyên?
Bạn sẽ so sánh log dạng văn bản tự do với structured logging theo khả năng tìm kiếm và xử lý tự động như thế nào?
Bạn sẽ lựa chọn schema JSON cho log gồm timestamp, severity, service, environment, event name và message ra sao?
Bạn sẽ phân biệt trường event.name, message và error.type để tránh truy vấn phải phân tích chuỗi tự do như thế nào?
Bạn sẽ chuẩn hóa định dạng timestamp, timezone và độ chính xác thời gian trong log của nhiều dịch vụ ra sao?
Bạn sẽ cân nhắc UTC và timezone hiển thị khi điều tra sự cố xảy ra trên nhiều khu vực như thế nào?
Bạn sẽ lựa chọn cách ghi elapsed time và đơn vị đo trong log để tránh nhầm milliseconds với seconds ra sao?
Bạn sẽ thiết kế cấu trúc log cho một exception có nguyên nhân và stack trace mà vẫn giữ JSON hợp lệ như thế nào?
Bạn sẽ lựa chọn phương thức escape ký tự xuống dòng, dấu nháy và Unicode khi phát structured log như thế nào?
Bạn sẽ kiểm soát sự thay đổi tên trường giữa các phiên bản ứng dụng để dashboard và truy vấn log không bị hỏng ra sao?
Bạn sẽ phân biệt nhãn có cardinality thấp để lập chỉ mục với các trường có cardinality cao chỉ phục vụ tìm kiếm như thế nào?
Bạn sẽ đánh giá chi phí khi index trực tiếp user ID, request ID hoặc URL đầy đủ trong hệ thống lưu log như thế nào?
Bạn sẽ lựa chọn một event ID hoặc error code ổn định để tổng hợp sự kiện qua nhiều ngôn ngữ hiển thị như thế nào?
Bạn sẽ kiểm tra chất lượng schema logging bằng cách phát hiện các bản ghi thiếu service name, timestamp hoặc severity ra sao?
Bạn sẽ giải thích correlation ID, request ID, trace ID và span ID khác nhau về phạm vi và vòng đời ra sao?
Bạn sẽ thiết kế luồng truyền trace ID qua HTTP gateway, service và database access để log liên kết được như thế nào?
Trong tình huống nào correlation ID nghiệp vụ cần tồn tại lâu hơn một distributed trace, và vì sao?
Bạn sẽ sử dụng MDC hoặc context logging để gắn thông tin request vào log mà không truyền tay qua mọi hàm ra sao?
Bạn sẽ phân tích nguy cơ rò rỉ MDC giữa hai request khi thread pool tái sử dụng thread như thế nào?
Bạn sẽ thiết kế log correlation cho tác vụ CompletableFuture, Reactor hoặc message consumer khi chuyển thread ra sao?
Bạn sẽ phân biệt log thiếu trace ID do context propagation lỗi với log không thuộc một HTTP request như thế nào?
Bạn sẽ ghép log của API gateway và service downstream khi mỗi thành phần dùng format hoặc tên trường khác nhau như thế nào?
Bạn sẽ kiểm tra quan hệ nhân quả giữa các sự kiện nếu đồng hồ của nhiều server bị lệch vài giây ra sao?
Bạn sẽ lựa chọn các trường liên kết log với metrics và traces theo tiêu chí nào để tránh bùng nổ cardinality?
Bạn sẽ xây dựng đường điều tra từ một trace lỗi tới đúng các log và Pod liên quan như thế nào?
Bạn sẽ nhận diện và phân loại dữ liệu nhạy cảm có nguy cơ xuất hiện trong application, access, security và business log ra sao?
Bạn sẽ thiết kế cơ chế che, loại bỏ hoặc băm các trường PII trước khi log được phát sinh ra sao?
Bạn sẽ phân biệt masking, redaction, tokenization và hashing theo khả năng đảo ngược và mục đích điều tra như thế nào?
Bạn sẽ ngăn việc đưa access token, API key, cookie phiên hoặc mật khẩu vào URL, header và body logs như thế nào?
Bạn sẽ kiểm soát rủi ro khi framework tự động ghi request và response payload mà lập trình viên không chủ động gọi logger ra sao?
Bạn sẽ thiết kế allowlist những trường được phép log thay vì chỉ sử dụng blacklist các trường nhạy cảm như thế nào?
Bạn sẽ nhận diện đường rò rỉ thông tin qua exception message, stack trace hoặc kết quả query được ghi tự động ra sao?
Bạn sẽ kiểm tra chính sách bảo mật cho log ở môi trường development, staging và production có khác nhau hợp lý như thế nào?
Bạn sẽ phân quyền cho nhóm vận hành, phát triển, bảo mật và kiểm toán truy cập từng loại log theo nguyên tắc nào?
Bạn sẽ xác định khi nào cần mã hóa dữ liệu log trên đường truyền và lúc lưu trữ ra sao?
Bạn sẽ quản lý và kiểm toán hoạt động truy vấn hoặc xuất log nhạy cảm bởi người vận hành như thế nào?
Bạn sẽ thiết kế cách xóa hoặc hạn chế truy cập dữ liệu cá nhân trong log theo chính sách lưu giữ và yêu cầu tuân thủ ra sao?
Bạn sẽ lựa chọn thời hạn retention riêng cho access log, debug log, security log và audit log dựa trên những tiêu chí nào?
Bạn sẽ phân biệt thời hạn lưu giữ để điều tra sự cố với thời hạn phải giữ phục vụ kiểm toán như thế nào?
Bạn sẽ thiết kế chính sách lưu trữ nhiều tầng để log mới dễ tìm còn log cũ có chi phí thấp hơn ra sao?
Bạn sẽ cân nhắc sampling hoặc drop log lặp lại với access log có lưu lượng rất cao theo những giới hạn nào?
Bạn sẽ phân biệt sampling log chẩn đoán với yêu cầu ghi đầy đủ audit event quan trọng như thế nào?
Bạn sẽ xác định những yếu tố nào khiến dung lượng log tăng đột biến và dự báo chi phí lưu trữ ra sao?
Bạn sẽ thiết kế quota hoặc rate limiting cho log mà không làm mất các sự kiện bảo mật và kiểm toán quan trọng như thế nào?
Bạn sẽ xử lý khi logging backend tạm thời không khả dụng để ứng dụng vẫn phục vụ mà không âm thầm mất sự kiện quan trọng như thế nào?
Bạn sẽ phân biệt buffer, batch, retry và backpressure trong pipeline chuyển log từ ứng dụng đến hệ thống tập trung như thế nào?
Bạn sẽ đánh giá ảnh hưởng của ghi log đồng bộ trong luồng request so với logging bất đồng bộ ra sao?
Bạn sẽ phân tích rủi ro log bị mất hoặc bị ghi trùng khi agent thu thập restart trong lúc chuyển dữ liệu như thế nào?
Bạn sẽ mô tả các bước parse, enrich, transform và route log khi hợp nhất dữ liệu từ nhiều nguồn ra sao?
Bạn sẽ thiết kế cơ chế nhận diện schema khác nhau giữa access log và audit log trước khi đưa vào cùng nền tảng tìm kiếm như thế nào?
Bạn sẽ xác định cần giữ nguyên bản ghi gốc hay chỉ giữ phiên bản đã chuẩn hóa khi điều tra sự cố ra sao?
Bạn sẽ thiết kế bộ kiểm tra để phát hiện pipeline logging làm mất trường quan trọng hoặc sửa sai timestamp như thế nào?
Bạn sẽ đánh giá mức độ tin cậy của logging pipeline từ độ trễ ingest, tỷ lệ lỗi parse và số bản ghi bị loại ra sao?
Bạn sẽ thiết kế cảnh báo khi không còn log từ một dịch vụ quan trọng dù request và metrics vẫn tồn tại như thế nào?
Bạn sẽ điều tra tình huống dashboard hiển thị lượng error log tăng nhưng tỷ lệ lỗi request không thay đổi như thế nào?
Bạn sẽ chọn thứ tự xem access log, application log, error log và infrastructure log khi API đột nhiên trả HTTP 503 ra sao?
Bạn sẽ sử dụng trace ID để xác định bước xử lý chậm nhất khi hệ thống log ghi các mốc ở nhiều service như thế nào?
Bạn sẽ phân tích nguyên nhân người dùng báo thanh toán thất bại nhưng audit log ghi thay đổi thành công theo những khả năng nào?
Bạn sẽ xác định ranh giới giữa sự cố bảo mật và lỗi nghiệp vụ khi security log chứa nhiều lần bị từ chối quyền truy cập ra sao?
Bạn sẽ kết hợp log firewall, reverse proxy và application để điều tra một IP có dấu hiệu quét API như thế nào?
Bạn sẽ xử lý tình huống database slow query log báo chậm nhưng application log không có error bằng cách nào?
Bạn sẽ xác minh một sự kiện có thật bị mất log hay chỉ không tìm thấy do filter, index hoặc time range sai như thế nào?
Bạn sẽ phân tích tình huống log từ nhiều nguồn có các timestamp xung đột và xây dựng thứ tự sự kiện đáng tin cậy ra sao?
Bạn sẽ nhận diện nguyên nhân lỗi deployment mới bằng cách so sánh tỷ lệ sự kiện và error code trước, sau rollout như thế nào?
Bạn sẽ kiểm tra việc các hệ thống ghi log khác nhau dùng severity không đồng nhất và làm méo báo cáo như thế nào?
Bạn sẽ thiết kế một bài kiểm thử xác minh request và response chứa secret không xuất hiện trong access log hay application log ra sao?
Bạn sẽ kiểm thử logging khi ứng dụng phát sinh exception, task bị hủy và container bị restart để đảm bảo đủ bằng chứng như thế nào?
Bạn sẽ xây dựng tiêu chí nghiệm thu về khả năng truy tìm sự kiện, log correlation, kiểm soát dữ liệu nhạy cảm, retention và chi phí trước khi triển khai logging production như thế nào?
