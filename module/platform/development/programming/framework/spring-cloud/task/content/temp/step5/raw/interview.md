Bạn giải thích Spring Cloud Task phù hợp với loại ứng dụng Spring Boot nào có thời gian chạy hữu hạn?
Bạn phân biệt Spring Cloud Task với một Spring Boot web service chạy liên tục như thế nào?
Bạn sẽ lựa chọn Spring Cloud Task thay vì scheduled method trong một service web khi nào?
Bạn phân biệt một task thực thi theo yêu cầu với worker liên tục nhận thông điệp từ queue ra sao?
Bạn xác định ranh giới trách nhiệm nghiệp vụ cho một task có thể chạy độc lập như thế nào?
Bạn giải thích vì sao task có thời gian chạy ngắn vẫn cần ghi metadata thực thi vào database ra sao?
Bạn phân biệt vòng đời của một task với vòng đời của ApplicationContext như thế nào?
Bạn sẽ thiết kế ứng dụng task không cần khởi động embedded web server bằng cách nào?
Bạn phân tích nguyên nhân một task xử lý xong nhưng JVM vẫn không thoát như thế nào?
Bạn sẽ đánh giá chi phí startup Spring Boot khi mỗi lượt task chỉ chạy một thao tác rất ngắn ra sao?
Bạn lựa chọn cách tách các tác vụ lớn thành nhiều task nhỏ mà vẫn giữ khả năng điều phối như thế nào?
Bạn phân biệt trạng thái kỹ thuật của tiến trình với kết quả nghiệp vụ của dữ liệu đã xử lý ra sao?
Bạn mô tả vai trò của @EnableTask khi chuẩn bị một ứng dụng Spring Cloud Task như thế nào?
Bạn giải thích mối quan hệ giữa SpringApplication và các runner khi thực thi task như thế nào?
Bạn phân biệt ApplicationRunner và CommandLineRunner trong việc nhận và xử lý tham số task ra sao?
Bạn sẽ tổ chức thứ tự thực thi nếu có nhiều runner cùng đăng ký trong một task như thế nào?
Bạn phân tích nguy cơ hai runner thực hiện tác dụng phụ trên cùng dữ liệu trong một lượt chạy ra sao?
Bạn xác định cách đặt tên task nhất quán giữa môi trường development và production như thế nào?
Bạn sẽ thiết kế lệnh khởi chạy một executable jar với tham số theo môi trường ra sao?
Bạn phân biệt tham số chỉ định phạm vi nghiệp vụ với cấu hình hạ tầng được truyền qua environment như thế nào?
Bạn giải thích cách task khởi tạo dependency và bắt đầu thực thi logic trước khi kết thúc tiến trình như thế nào?
Bạn xác định vị trí thích hợp để xác thực tham số trước khi task thay đổi dữ liệu như thế nào?
Bạn đánh giá rủi ro khi tác vụ mở kết nối tới nhiều dependency trong giai đoạn startup ra sao?
Bạn sẽ thiết kế cơ chế hủy ứng dụng sau khi task hoàn tất mà vẫn đóng các bean đúng vòng đời như thế nào?
Bạn phân biệt hoàn tất runner với việc mọi công việc bất đồng bộ của task đã thật sự kết thúc ra sao?
Bạn giải thích tại sao thread nền không được quản lý có thể giữ tiến trình task chạy mãi như thế nào?
Bạn sẽ kiểm tra một task không vô tình chạy lần thứ hai khi ApplicationContext được khởi tạo lại ra sao?
Bạn phân tích các vấn đề khi dùng mutable singleton state để chia sẻ dữ liệu giữa nhiều bước xử lý task như thế nào?
Bạn sẽ thiết kế task nhận đúng cấu hình khi cùng một image được chạy ở nhiều namespace ra sao?
Bạn phân biệt một lượt chạy được kích hoạt thủ công với một lượt chạy định kỳ theo định danh nào?
Bạn giải thích TaskRepository có nhiệm vụ gì trong cơ chế quản lý lịch sử thực thi của Spring Cloud Task?
Bạn phân biệt TaskRepository với repository lưu dữ liệu nghiệp vụ như thế nào?
Bạn mô tả một TaskExecution chứa những thông tin nào hữu ích cho việc vận hành?
Bạn phân biệt task name với task execution ID khi cùng một tác vụ chạy nhiều lần ra sao?
Bạn giải thích ý nghĩa của start time, end time và duration khi điều tra một TaskExecution ra sao?
Bạn phân biệt exit code của TaskExecution với trạng thái thành công do một rule nghiệp vụ xác định như thế nào?
Bạn sẽ sử dụng exit message để chẩn đoán lỗi mà không tiết lộ thông tin nhạy cảm ra sao?
Bạn xác định cách lưu task arguments có kiểm soát để phục vụ khả năng tái hiện một lượt chạy như thế nào?
Bạn phân tích nguyên nhân TaskExecution có start time nhưng không có end time như thế nào?
Bạn sẽ phân biệt một task còn chạy với một task đã crash nhưng metadata chưa được kết thúc ra sao?
Bạn giải thích TaskExplorer hỗ trợ đọc lịch sử và tra cứu TaskExecution như thế nào?
Bạn sẽ thiết kế API quản trị đọc trạng thái qua TaskExplorer với phân quyền phù hợp ra sao?
Bạn xác định cách tìm những lượt task thất bại gần nhất từ dữ liệu TaskRepository như thế nào?
Bạn phân tích nguy cơ một exit message quá dài gây khó khăn trong lưu trữ và truy vấn metadata như thế nào?
Bạn sẽ thiết kế correlation ID để nối yêu cầu của người dùng với TaskExecution như thế nào?
Bạn phân biệt external execution ID với task execution ID nội bộ khi tích hợp hệ điều phối ra sao?
Bạn sẽ giải thích vì sao TaskRepository không thay thế hệ thống audit của hành động nghiệp vụ như thế nào?
Bạn xác định thông tin metadata nào cần được giữ lại theo chính sách retention như thế nào?
Bạn sẽ thiết kế dọn dẹp lịch sử TaskExecution mà không xóa nhầm những lượt chạy đang hoạt động ra sao?
Bạn phân tích cách migration schema TaskRepository ảnh hưởng các phiên bản task đang chạy đồng thời như thế nào?
Bạn xác định những index cần thiết để truy vấn theo task name, thời gian và kết quả ra sao?
Bạn sẽ bảo vệ thông tin TaskExecution khi nhiều tenant cùng sử dụng database metadata như thế nào?
Bạn phân biệt TaskExplorer với việc truy vấn bảng metadata trực tiếp bằng SQL như thế nào?
Bạn đánh giá tác động khi dữ liệu TaskRepository bị mất nhưng dữ liệu nghiệp vụ vẫn còn đầy đủ ra sao?
Bạn sẽ thiết kế phương án sao lưu và khôi phục metadata cho một hệ thống có nhiều task quan trọng như thế nào?
Bạn xác định cách phân biệt nhiều TaskExecution có cùng tham số nhưng được khởi chạy bởi các yêu cầu khác nhau như thế nào?
Bạn phân tích nguy cơ nhầm một TaskExecution chưa đóng với một tiến trình còn hoạt động như thế nào?
Bạn sẽ kiểm tra các bất thường giữa thời gian tiến trình chạy và thời gian được ghi trong TaskRepository ra sao?
Bạn giải thích tại sao TaskRepository nên được cấu hình bằng DataSource có khả năng ghi bền vững như thế nào?
Bạn lựa chọn dùng chung hay tách DataSource cho metadata task và dữ liệu nghiệp vụ dựa trên tiêu chí nào?
Bạn phân biệt lỗi kết nối TaskRepository với lỗi kết nối database nghiệp vụ khi chẩn đoán một task ra sao?
Bạn sẽ kiểm tra schema metadata đã có trước khi khởi chạy task lần đầu như thế nào?
Bạn đánh giá rủi ro cho phép task tự tạo bảng metadata trong môi trường production ra sao?
Bạn sẽ phân quyền DDL và DML cho tài khoản metadata theo các giai đoạn triển khai như thế nào?
Bạn xác định chiến lược migration khi một bản Spring Cloud Task mới cần schema khác ra sao?
Bạn sẽ kiểm tra sự tương thích của schema với thư viện Spring Cloud Task trong CI như thế nào?
Bạn phân tích rủi ro dùng một connection pool quá lớn cho hàng trăm task ngắn chạy đồng thời ra sao?
Bạn lựa chọn giới hạn pool connection riêng cho metadata và cho truy cập dữ liệu nghiệp vụ như thế nào?
Bạn sẽ thiết kế chính sách fail-fast khi TaskRepository không truy cập được lúc khởi động ra sao?
Bạn giải thích vì sao tiếp tục xử lý dữ liệu khi không thể ghi metadata có thể làm khó đối soát như thế nào?
Bạn sẽ xử lý khi cập nhật thời gian kết thúc của TaskExecution thất bại sau khi nghiệp vụ đã commit ra sao?
Bạn phân biệt transaction ghi metadata với transaction thao tác dữ liệu nghiệp vụ như thế nào?
Bạn xác định ranh giới transaction để lỗi ghi một bản ghi nghiệp vụ không làm hỏng toàn bộ lịch sử task như thế nào?
Bạn sẽ đánh giá lock contention khi nhiều task cùng cập nhật metadata trong một database ra sao?
Bạn xác định cách theo dõi task metadata database khi nó trở thành điểm nghẽn chung của hệ thống ra sao?
Bạn phân tích rủi ro clock drift giữa các node khi so sánh thời gian bắt đầu và kết thúc task như thế nào?
Bạn sẽ xây dựng cơ chế kiểm tra metadata bất thường mà không tự ý sửa lịch sử thực thi hợp lệ ra sao?
Bạn lựa chọn cách quản lý credential cho TaskRepository khác credential của business database như thế nào?
Bạn sẽ bảo đảm các lỗi database không làm lộ connection string hoặc password trong exit message ra sao?
Bạn phân biệt cấu hình mặc định trong application.yml với tham số truyền cho từng TaskExecution như thế nào?
Bạn sẽ định nghĩa contract tham số cho một task nhập dữ liệu theo khoảng thời gian như thế nào?
Bạn xác định cách validation ngày bắt đầu, ngày kết thúc và timezone trước khi chạy như thế nào?
Bạn sẽ xử lý tham số thiếu, sai kiểu hoặc ngoài phạm vi quyền của người khởi chạy ra sao?
Bạn phân tích nguy cơ một tham số tenantId hợp lệ cú pháp nhưng không thuộc quyền xử lý của caller như thế nào?
Bạn sẽ xác định những trường hợp nên cho task chạy ở chế độ dry-run trước khi ghi dữ liệu ra sao?
Bạn phân biệt các tham số nghiệp vụ bất biến với giá trị cấu hình có thể thay đổi theo môi trường như thế nào?
Bạn sẽ thiết kế giá trị mặc định an toàn khi bộ điều phối không truyền một tham số tùy chọn ra sao?
Bạn phân tích ảnh hưởng của profile tới lựa chọn database và endpoint cho một tác vụ chạy theo lịch như thế nào?
Bạn sẽ điều tra một thuộc tính bị override bởi command line thay vì environment variable như thế nào?
Bạn xác định cách truyền Secret qua mounted file hoặc environment thay vì command-line arguments như thế nào?
Bạn phân tích vì sao command-line arguments có thể bị ghi vào process list hoặc task metadata như thế nào?
Bạn sẽ định nghĩa business run key để xác định một phạm vi dữ liệu đã được xử lý trước đó ra sao?
Bạn phân biệt business run key với TaskExecution ID sinh mới cho mỗi lượt khởi chạy như thế nào?
Bạn xác định chiến lược versioning khi tên và kiểu tham số task thay đổi theo bản phát hành ra sao?
Bạn sẽ bảo vệ task có tham số dẫn tới thao tác xóa hoặc cập nhật hàng loạt bằng bước xác nhận nào?
Bạn phân tích rủi ro truyền URL do người dùng cung cấp trực tiếp vào một task gọi HTTP ra sao?
Bạn sẽ thiết kế allowlist nguồn dữ liệu đầu vào để tránh đọc nhầm tài nguyên nội bộ ra sao?
Bạn đánh giá cách test tham số task độc lập với các secret của production như thế nào?
Bạn giải thích vai trò của TaskExecutionListener trong quan sát vòng đời một task như thế nào?
Bạn phân biệt callback trước task, khi task kết thúc và khi task lỗi về loại thông tin được ghi nhận ra sao?
Bạn sẽ sử dụng TaskExecutionListener để tính thời gian và ghi metadata bổ sung mà không thực thi nghiệp vụ chính như thế nào?
Bạn phân tích hậu quả nếu TaskExecutionListener tự ném exception trong khi task đang kết thúc như thế nào?
Bạn sẽ thiết kế listener an toàn khi task được scheduler retry và các callback có thể thực thi lại ra sao?
Bạn phân biệt lifecycle listener với @PostConstruct và @PreDestroy của bean như thế nào?
Bạn sẽ quản lý resource cleanup khi task ném exception mà ApplicationContext vẫn được đóng bình thường ra sao?
Bạn xác định lúc nào listener không thể chạy do tiến trình bị kill đột ngột như thế nào?
Bạn phân tích vì sao task báo hoàn tất nhưng một tác vụ async không được await vẫn đang chạy ra sao?
Bạn sẽ đo số lượng bản ghi xử lý và lỗi theo từng công đoạn mà không nhét tất cả vào exit message ra sao?
Bạn xác định cách gắn trace ID và correlation ID khi task không có HTTP request cha như thế nào?
Bạn phân biệt exception kỹ thuật với kết quả nghiệp vụ từ chối xử lý khi chọn mã thoát như thế nào?
Bạn sẽ sử dụng ExitCodeGenerator để trả mã lỗi phù hợp cho bộ điều phối như thế nào?
Bạn giải thích SpringApplication.exit phối hợp với việc đóng ApplicationContext và mã thoát như thế nào?
Bạn sẽ xác định cách tránh task trả exit code 0 khi đã bắt và nuốt exception trong runner ra sao?
Bạn phân tích rủi ro biến một lỗi nghiệp vụ không hoàn thành thành exit status thành công ra sao?
Bạn sẽ thiết kế phân loại lỗi validation, lỗi dependency và lỗi dữ liệu để quyết định retry như thế nào?
Bạn phân biệt lỗi có thể retry với lỗi xác thực hoặc lỗi cấu hình không nên retry như thế nào?
Bạn sẽ truyền kết quả lỗi cho cả TaskRepository và scheduler theo một quy ước nhất quán ra sao?
Bạn đánh giá sự khác nhau giữa TaskExecution exit code và exit code của container khi ứng dụng bị kill ra sao?
Bạn sẽ thiết kế timeout tổng cho một task để tránh chạy treo vô thời hạn như thế nào?
Bạn xác định tác động của timeout khi transaction nghiệp vụ chưa commit và tiến trình chuẩn bị dừng ra sao?
Bạn sẽ triển khai graceful shutdown để dừng nhận công việc mới và hoàn tất thao tác đang chạy ra sao?
Bạn phân tích hậu quả nếu task bị SIGKILL hoặc OOMKilled trước khi ghi end time ra sao?
Bạn sẽ kiểm tra TaskExecution bị treo và trạng thái process thực tế trong một runbook như thế nào?
Bạn xác định khi nào cần can thiệp thủ công để sửa trạng thái vận hành thay vì tự chạy lại task ra sao?
Bạn sẽ thiết kế retry một thao tác bên trong task khác với retry toàn bộ tiến trình như thế nào?
Bạn giải thích vì sao lưu TaskExecution không tự cung cấp checkpoint để restart nghiệp vụ như thế nào?
Bạn sẽ tạo checkpoint riêng cho một task nhập dữ liệu rất dài không dùng Spring Batch như thế nào?
Bạn xác định cách lưu watermark ổn định nếu dữ liệu nguồn có thể được thêm hoặc xóa trong lúc xử lý ra sao?
Bạn phân biệt việc retry từ checkpoint với chạy lại toàn bộ tập dữ liệu ban đầu như thế nào?
Bạn phân tích tác động khi task crash sau khi commit dữ liệu nhưng trước khi lưu checkpoint ra sao?
Bạn sẽ thiết kế idempotency key để cùng một thao tác không được ghi hai lần sau retry ra sao?
Bạn phân biệt ít nhất một lần xử lý với kết quả nghiệp vụ đúng một lần như thế nào?
Bạn sẽ dùng unique constraint, upsert hoặc bảng deduplication để chống trùng dữ liệu ra sao?
Bạn đánh giá khi nào nên dùng transaction thay vì cơ chế bù trừ cho một chuỗi thao tác nghiệp vụ như thế nào?
Bạn phân tích rủi ro gọi API ngoài database transaction khi task phải restart như thế nào?
Bạn sẽ thiết kế quy trình đối soát khi downstream commit nhưng response bị mất ra sao?
Bạn xác định khi nào cần exponential backoff và jitter để tránh retry storm từ nhiều task cùng lỗi ra sao?
Bạn phân biệt chạy lại bản ghi lỗi với chạy lại toàn bộ task trong quyết định vận hành như thế nào?
Bạn sẽ xác định số lần retry tối đa theo deadline của lịch chạy và giới hạn tài nguyên ra sao?
Bạn đánh giá rủi ro scheduler khởi chạy một task mới khi lượt trước chưa hoàn tất như thế nào?
Bạn sẽ thiết kế distributed lock để ngăn hai TaskExecution cùng sửa một phạm vi dữ liệu ra sao?
Bạn phân tích rủi ro lease hết hạn trong khi task cũ chưa dừng hẳn như thế nào?
Bạn sẽ sử dụng fencing token để tránh hai worker cùng thực thi tác dụng phụ trên một run key ra sao?
Bạn xác định khi nào cho phép nhiều task cùng tên chạy song song mà không xung đột dữ liệu như thế nào?
Bạn sẽ kiểm soát concurrency khi nhiều task chia sẻ một connection pool hoặc API quota như thế nào?
Bạn phân biệt task-level concurrency limit với rate limit của dịch vụ hạ nguồn như thế nào?
Bạn sẽ xử lý tình huống scheduler đẩy nhiều yêu cầu khởi chạy hơn năng lực xử lý hiện tại ra sao?
Bạn phân tích ảnh hưởng của queue backlog tới độ trễ từ lúc đặt lịch đến lúc bắt đầu task như thế nào?
Bạn sẽ lựa chọn cách từ chối, xếp hàng hoặc dời lịch khi task đã đạt giới hạn đồng thời ra sao?
Bạn giải thích vì sao Spring Cloud Task không tự là một hệ thống scheduler hoàn chỉnh như thế nào?
Bạn phân biệt bộ lập lịch, cơ chế khởi chạy và mã xử lý nghiệp vụ của task ra sao?
Bạn sẽ lựa chọn giữa cron của hệ điều hành, Kubernetes CronJob và bộ điều phối workflow theo tiêu chí nào?
Bạn phân tích cách timezone và thay đổi giờ địa phương ảnh hưởng task chạy theo lịch hằng ngày ra sao?
Bạn xác định chính sách xử lý một lượt chạy bị bỏ lỡ trong lúc scheduler không hoạt động ra sao?
Bạn sẽ quyết định khi nào chạy bù dữ liệu cũ và khi nào chỉ chạy mốc thời gian gần nhất như thế nào?
Bạn thiết kế API khởi chạy task theo yêu cầu mà không giữ HTTP connection đến khi task kết thúc ra sao?
Bạn sẽ trả task execution ID hoặc correlation ID để caller theo dõi kết quả sau khi khởi chạy như thế nào?
Bạn phân biệt xác nhận đã tạo yêu cầu với xác nhận task đã hoàn tất thành công ra sao?
Bạn phân tích khả năng API launcher timeout làm caller gửi lại yêu cầu và tạo task trùng như thế nào?
Bạn sẽ thiết kế idempotency cho yêu cầu khởi chạy từ API hoặc scheduler ra sao?
Bạn xác định cách truyền identity và quyền hạn caller tới hệ điều phối mà không đưa thông tin nhạy cảm vào command line như thế nào?
Bạn sẽ phối hợp nhiều task phụ thuộc nhau bằng một workflow scheduler như thế nào?
Bạn phân biệt Spring Cloud Data Flow với bản thân Spring Cloud Task về điều phối và theo dõi các lượt chạy ra sao?
Bạn sẽ lựa chọn cách triển khai bằng executable jar hay container image theo yêu cầu vận hành nào?
Bạn giải thích vai trò của Kubernetes Job khi chạy một lượt Spring Cloud Task như thế nào?
Bạn phân biệt Kubernetes Job và CronJob về nơi định nghĩa lịch và vòng đời thực thi ra sao?
Bạn sẽ cấu hình Kubernetes restartPolicy và backoffLimit phù hợp với tính idempotent của task như thế nào?
Bạn phân tích vì sao retry của Kubernetes và retry bên trong task phải có chung ngân sách ra sao?
Bạn sẽ cấu hình resource requests và limits để Pod chạy task không tranh giành tài nguyên quá mức như thế nào?
Bạn xác định cách dùng activeDeadlineSeconds để giới hạn thời gian chạy mà vẫn hiểu rủi ro kết thúc cưỡng bức ra sao?
Bạn sẽ quản lý logs và metadata sau khi Pod hoàn tất rồi bị xóa theo TTL như thế nào?
Bạn phân biệt Pod phase, Kubernetes Job status và TaskExecution exit code khi điều tra như thế nào?
Bạn sẽ bảo đảm TaskRepository nằm ngoài vòng đời Pod để không mất lịch sử chạy ra sao?
Bạn phân tích nguy cơ cùng một Kubernetes Job bị thử lại trên node khác làm dữ liệu đích bị xử lý hai lần như thế nào?
Bạn sẽ phát hiện scheduler tạo trùng Kubernetes Job do nhiều instance điều phối chạy đồng thời ra sao?
Bạn xác định cách liên kết Kubernetes Job name với TaskExecution ID và business run key ra sao?
Bạn sẽ thiết kế graceful termination khi node bị drain giữa lúc một task đang ghi dữ liệu như thế nào?
Bạn đánh giá các kịch bản autoscaling làm nhiều task đồng thời khiến TaskRepository quá tải như thế nào?
Bạn phân biệt cơ chế task history của Spring Cloud Task với khả năng checkpoint của Spring Batch như thế nào?
Bạn giải thích sự khác nhau giữa TaskExecution, JobExecution và StepExecution trong ứng dụng Spring Cloud Task kết hợp Batch ra sao?
Bạn sẽ xác định khi nào nhiệm vụ xử lý dữ liệu nhiều bước nên dùng Spring Batch thay vì runner thuần như thế nào?
Bạn mô tả cách một Spring Cloud Task khởi chạy một Spring Batch Job như thế nào?
Bạn phân biệt TaskRepository và JobRepository theo loại metadata cần lưu như thế nào?
Bạn giải thích vì sao một TaskExecution có thể cần liên kết với nhiều JobExecution trong một quy trình ra sao?
Bạn sẽ truy vết từ TaskExecution tới JobExecution và StepExecution khi một chunk lỗi như thế nào?
Bạn xác định cách đặt correlation ID để tránh nhầm TaskExecution ID với JobExecution ID ra sao?
Bạn sẽ chuyển JobParameters từ task arguments theo hợp đồng nào để tránh mất tính tương thích như thế nào?
Bạn phân tích ảnh hưởng của identifying JobParameters tới việc restart một Batch JobInstance ra sao?
Bạn phân biệt restart Batch JobInstance cũ với khởi chạy TaskExecution mới cho cùng dữ liệu như thế nào?
Bạn sẽ xử lý khi Spring Batch Job báo FAILED nhưng Spring Cloud Task vẫn trả mã thoát thành công như thế nào?
Bạn xác định cách ánh xạ ExitStatus của batch job sang exit code process task như thế nào?
Bạn sẽ thiết kế metadata liên kết đủ để người vận hành tra cứu một Step thất bại từ dashboard task ra sao?
Bạn phân tích rủi ro retry ở cả tầng Spring Batch và tầng task scheduler gây xử lý trùng như thế nào?
Bạn sẽ quản lý checkpoint và skip/retry của Spring Batch khác với lỗi khởi chạy task như thế nào?
Bạn xác định cách đối soát read/write/skip count của batch với số bản ghi nghiệp vụ đầu ra ra sao?
Bạn sẽ quyết định dùng một task cho mỗi batch job hay một task điều phối nhiều batch job theo yêu cầu nào?
Bạn phân tích tải lên cùng một database khi TaskRepository và JobRepository cùng lưu metadata cho nhiều job chạy đồng thời ra sao?
Bạn sẽ thiết kế integration test khởi chạy batch job từ Spring Cloud Task mà không gọi hệ thống production ra sao?
Bạn phân biệt chạy lại task sau lỗi hạ tầng với restart batch job sau lỗi dữ liệu như thế nào?
Bạn xác định khi nào một bước batch đang chạy không nên bị dừng ngay dù task nhận SIGTERM ra sao?
Bạn sẽ tổ chức monitoring theo TaskExecution, JobExecution và StepExecution để tránh trộn các cấp thống kê như thế nào?
Bạn phân tích cách một batch job chạy dài ảnh hưởng timeout của task và Kubernetes Job như thế nào?
Bạn sẽ lựa chọn metric phản ánh số lượt task thành công, thất bại và thời gian thực thi như thế nào?
Bạn thiết kế metric theo task name và outcome mà không đưa TaskExecution ID vào label có cardinality cao ra sao?
Bạn phân biệt thời gian startup Spring Boot và thời gian xử lý nghiệp vụ khi đọc duration task như thế nào?
Bạn sẽ đo queue wait time trước khi task bắt đầu như thế nào?
Bạn sử dụng Micrometer để đo throughput bản ghi và retry count của task ra sao?
Bạn xác định cách phát hiện task chậm nhưng không lỗi qua dữ liệu TaskRepository và metric nào?
Bạn sẽ thiết kế cảnh báo khi TaskExecution chưa có end time sau thời hạn SLA ra sao?
Bạn phân tích vì sao log của một TaskExecution crash có thể không chứa thông điệp kết thúc thông thường như thế nào?
Bạn sẽ gắn trace ID vào request outbound của task không có HTTP request cha như thế nào?
Bạn phân biệt lỗi application startup với lỗi logic nghiệp vụ trong telemetry như thế nào?
Bạn sẽ thiết kế dashboard kết hợp scheduler history, TaskRepository và container exit status ra sao?
Bạn xác định cách báo động khi task bị lặp lịch hoặc có quá nhiều TaskExecution thất bại liên tiếp như thế nào?
Bạn sẽ xây dựng runbook kiểm tra một task bị treo hoặc không cập nhật trạng thái kết thúc ra sao?
Bạn phân tích tác động của việc log raw parameters tới dữ liệu cá nhân và secret ra sao?
Bạn sẽ thiết kế chính sách retention cho logs, metric và metadata đáp ứng yêu cầu kiểm toán như thế nào?
Bạn xác định quyền đọc TaskExplorer khác quyền khởi chạy hoặc chạy lại task như thế nào?
Bạn sẽ xây dựng cơ chế audit ghi người yêu cầu, lý do và thời điểm chạy lại thủ công như thế nào?
Bạn phân tích nguy cơ người dùng thay đổi tenantId trong task arguments để truy cập dữ liệu ngoài quyền như thế nào?
Bạn sẽ kiểm tra danh tính và quyền ở bước nhận yêu cầu khởi chạy thay vì tin tưởng tham số như thế nào?
Bạn xác định cách giới hạn truy cập database metadata và business database theo nguyên tắc least privilege ra sao?
Bạn sẽ xoay vòng credential cho task chạy dài mà không làm lộ token trong log như thế nào?
Bạn phân biệt quyền truy cập Kubernetes API của launcher với quyền truy cập dữ liệu nghiệp vụ của task ra sao?
Bạn sẽ kiểm thử task bằng unit test không cần ApplicationContext theo cách nào?
Bạn phân biệt unit test runner với integration test toàn bộ lifecycle Spring Cloud Task ra sao?
Bạn sẽ kiểm tra TaskExecution có start time, end time và exit code đúng qua một integration test như thế nào?
Bạn xây dựng test cho TaskExplorer khi nhiều TaskExecution cùng tên được tạo liên tiếp như thế nào?
Bạn sẽ xác minh task arguments và exit message không lưu credential trong TaskRepository ra sao?
Bạn thiết kế test runner ném exception để xác minh listener và exit code hoạt động đúng như thế nào?
Bạn kiểm thử tham số sai bị từ chối trước khi xuất hiện tác dụng phụ nghiệp vụ ra sao?
Bạn sẽ mô phỏng TaskRepository không thể ghi lúc startup và quan sát chính sách fail-fast như thế nào?
Bạn kiểm thử lỗi database đúng thời điểm lưu kết thúc TaskExecution theo phương pháp nào?
Bạn sẽ tạo test SIGTERM để xác minh task đóng connection và dọn tài nguyên như thế nào?
Bạn phân tích cách kiểm thử task bị SIGKILL bằng tiến trình con mà không giả định listener luôn được gọi ra sao?
Bạn sẽ kiểm thử scheduler gửi hai yêu cầu trùng business run key để xác minh deduplication ra sao?
Bạn thiết kế test hai task instance tranh chấp cùng dữ liệu nhằm phát hiện race condition như thế nào?
Bạn sẽ kiểm tra checkpoint và watermark không làm mất hoặc ghi trùng bản ghi sau crash ra sao?
Bạn đánh giá lợi ích của Testcontainers khi cần thử nghiệm lock, transaction và migration schema thực tế ra sao?
Bạn sẽ chạy integration test cho Spring Batch Job được kích hoạt từ task và phản ánh chính xác trạng thái thất bại như thế nào?
Bạn thiết kế test Kubernetes Job bị retry sau commit để xác minh idempotency ra sao?
Bạn sẽ kiểm thử application context kết thúc đúng sau khi runner hoàn thành thay vì giữ web thread chạy ra sao?
Bạn xây dựng load test cho TaskRepository khi hàng trăm task khởi chạy cùng thời điểm như thế nào?
Bạn xác định tiêu chí QA cần có trước khi cho scheduler production khởi chạy một task như thế nào?
Nếu TaskExecution có start time nhưng không có end time, bạn sẽ đối chiếu tiến trình và TaskRepository ra sao?
Nếu task hoàn thành xử lý nhưng process không thoát, bạn sẽ truy tìm thread hoặc resource nào đang giữ JVM như thế nào?
Nếu TaskExecution báo thành công nhưng dữ liệu đích thiếu bản ghi, bạn sẽ thiết kế đối soát và báo lỗi ra sao?
Nếu hai scheduler cùng khởi chạy một business run key, bạn sẽ ngăn xử lý trùng và ghi audit như thế nào?
Nếu task bị Kubernetes retry sau khi ghi một phần dữ liệu, bạn sẽ xác định phạm vi phải xử lý lại ra sao?
Nếu database metadata bị outage còn database nghiệp vụ vẫn hoạt động, bạn sẽ quyết định task có nên tiếp tục như thế nào?
Nếu access token lộ trong task arguments được TaskRepository lưu lại, bạn sẽ thay đổi cơ chế truyền tham số ra sao?
Nếu Spring Batch Job FAILED nhưng exit code task vẫn bằng 0, bạn sẽ sửa cách truyền trạng thái như thế nào?
Nếu task bị kill ngay sau khi gọi dịch vụ thanh toán thành công, bạn sẽ tránh tạo giao dịch trùng khi retry ra sao?
Nếu người dùng bấm khởi chạy task nhiều lần do không nhận phản hồi API, bạn sẽ thiết kế idempotency như thế nào?
Nếu lịch chạy hằng ngày gặp thay đổi timezone hoặc daylight saving time, bạn sẽ chuẩn hóa business run key ra sao?
Nếu task version mới và cũ cùng chạy trong rolling deployment, bạn sẽ kiểm tra tương thích schema và tham số ra sao?
Nếu operator cần chạy lại một phần dữ liệu hôm trước, bạn sẽ thiết kế tham số, checkpoint và quyền thao tác như thế nào?
Nếu phải xây dựng một Spring Cloud Task xử lý nhập liệu định kỳ trên production, bạn sẽ thiết kế TaskRepository, tham số, orchestration, Spring Batch, bảo mật và kiểm thử ra sao?
