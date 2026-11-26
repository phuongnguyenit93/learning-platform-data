Bạn sẽ xác định những vấn đề nào của kiến trúc microservices khiến một hệ thống cần cân nhắc triển khai service mesh?
Bạn sẽ giải thích service mesh khác thư viện giao tiếp tích hợp trong ứng dụng ở phạm vi trách nhiệm và cách triển khai ra sao?
Bạn sẽ phân biệt vai trò service mesh, API Gateway, ingress controller và reverse proxy trong một hệ thống phân tán như thế nào?
Bạn sẽ dựa trên tiêu chí nào để quyết định chỉ dùng Kubernetes Service hay bổ sung service mesh?
Bạn sẽ đánh giá lợi ích và chi phí của việc đưa chức năng mạng dùng chung ra khỏi mã nguồn từng microservice như thế nào?
Bạn sẽ xác định những chính sách nào nên xử lý tập trung tại mesh và logic nào phải ở lại trong ứng dụng?
Bạn sẽ phác thảo đường đi của một request giữa hai microservice trước và sau khi bật service mesh ra sao?
Bạn sẽ so sánh mô hình service mesh với giao tiếp trực tiếp giữa các service về độ phức tạp vận hành và khả năng quan sát như thế nào?
Bạn sẽ thiết lập mục tiêu về độ trễ, tính sẵn sàng và bảo mật trước khi đưa mesh vào production bằng cách nào?
Bạn sẽ lựa chọn những nhóm ứng dụng nào nên tham gia mesh trước khi triển khai trên toàn hệ thống dựa vào yếu tố nào?
Bạn sẽ phân biệt control plane và data plane theo thành phần, dữ liệu xử lý và những bảo đảm vận hành ra sao?
Bạn sẽ mô tả quá trình control plane nhận cấu hình, xác thực chính sách và phân phối đến data plane như thế nào?
Bạn sẽ giải thích vai trò của proxy trong data plane khi một request đi từ service A đến service B ra sao?
Những rủi ro nào phát sinh nếu control plane nằm trên đường đi của mọi request dữ liệu, và kiến trúc mesh tránh rủi ro đó ra sao?
Bạn sẽ phân tích các loại metadata về service, endpoint và chính sách mà control plane cần duy trì ra sao?
Bạn sẽ xác định cơ chế nào giúp data plane tiếp tục phục vụ lưu lượng khi control plane tạm thời không sẵn sàng?
Bạn sẽ kiểm tra tác động của cấu hình cũ trong data plane khi control plane mất kết nối một thời gian như thế nào?
Bạn sẽ thiết kế ranh giới lỗi giữa control plane và data plane để tránh một sự cố cấu hình ảnh hưởng toàn bộ cluster ra sao?
Bạn sẽ phân biệt dữ liệu điều khiển và dữ liệu quan sát được gửi từ proxy lên hệ thống giám sát như thế nào?
Bạn sẽ lựa chọn số lượng replica và phạm vi triển khai control plane để đáp ứng yêu cầu sẵn sàng cao ra sao?
Bạn sẽ mô tả sidecar proxy được gắn với workload và tham gia luồng traffic trong Kubernetes như thế nào?
Bạn sẽ giải thích cách intercept lưu lượng inbound và outbound khi Pod sử dụng sidecar proxy ra sao?
Bạn sẽ phân tích vai trò của iptables, CNI hoặc cơ chế chuyển hướng phù hợp với mesh đang sử dụng như thế nào?
Bạn sẽ xác định các rủi ro khi sidecar khởi động chậm hơn ứng dụng hoặc dừng trước khi request hoàn tất ra sao?
Bạn sẽ đo chi phí CPU, RAM, số kết nối và thời gian khởi động do sidecar tạo ra trên mỗi Pod như thế nào?
Bạn sẽ so sánh mô hình sidecar với kiến trúc mesh không dùng sidecar ở khả năng cô lập, vận hành và hiệu năng ra sao?
Những nhu cầu traffic policy nào khiến bạn chọn waypoint hoặc proxy ở tầng node thay vì sidecar riêng cho mỗi Pod?
Bạn sẽ phân biệt xử lý mạng tầng 4 và tầng 7 trong các chế độ data plane khác nhau của service mesh như thế nào?
Bạn sẽ kiểm tra ứng dụng có thực sự đi qua data plane hay đang vô tình bypass proxy bằng những cách nào?
Bạn sẽ thiết kế ngoại lệ cho traffic không cần qua mesh mà không phá vỡ chính sách bảo mật của workload khác ra sao?
Bạn sẽ giải thích cách mesh tìm endpoint của service dựa trên thông tin từ Kubernetes hoặc nguồn khám phá dịch vụ khác như thế nào?
Bạn sẽ phân biệt tên service logic với địa chỉ IP của từng Pod khi proxy quyết định đích đến ra sao?
Bạn sẽ mô tả sự thay đổi danh sách endpoint trong data plane khi Pod được scale up, scale down hoặc bị thay thế như thế nào?
Bạn sẽ xử lý trường hợp service không có endpoint sẵn sàng nhưng proxy vẫn nhận request từ client ra sao?
Bạn sẽ lựa chọn định tuyến trực tiếp đến endpoint hay thông qua cluster IP dựa trên khả năng của mesh như thế nào?
Bạn sẽ kiểm tra các tình huống DNS, service discovery và cấu hình route không đồng bộ gây lỗi truy cập như thế nào?
Bạn sẽ tổ chức traffic giữa những service nằm ở các namespace khác nhau và kiểm tra quy tắc định danh ra sao?
Bạn sẽ thiết kế service discovery cho workload nằm ngoài Kubernetes nhưng vẫn cần tham gia mesh như thế nào?
Bạn sẽ phân biệt ingress gateway của mesh với proxy sidecar đối với traffic từ Internet đi vào cụm như thế nào?
Bạn sẽ dựa trên yêu cầu kiểm soát outbound nào để quyết định traffic cần đi qua egress gateway?
Bạn sẽ thiết kế chính sách công bố các dịch vụ bên ngoài được phép truy cập thông qua egress của mesh ra sao?
Bạn sẽ ngăn các workload truy cập trực tiếp ra ngoài để bỏ qua kiểm soát egress bằng biện pháp mạng nào?
Bạn sẽ kiểm tra đường đi qua ingress, sidecar và egress khi cùng một request trải qua nhiều lớp proxy như thế nào?
Bạn sẽ phân định trách nhiệm giữa edge gateway và mesh khi cả hai đều hỗ trợ xác thực, định tuyến và giới hạn lưu lượng ra sao?
Bạn sẽ thiết kế định tuyến HTTP theo host, path hoặc header giữa nhiều phiên bản của cùng một service như thế nào?
Bạn sẽ lựa chọn chiến lược chia lưu lượng 90/10 để canary một phiên bản backend và kiểm chứng tỷ lệ phân phối ra sao?
Bạn sẽ thực hiện chuyển đổi canary theo từng bước và xác định tiêu chí rollback dựa trên metric nào?
Bạn sẽ phân biệt traffic splitting theo trọng số với định tuyến nhất quán theo người dùng hoặc session như thế nào?
Bạn sẽ sử dụng header-based routing để thử một phiên bản mới cho nhóm kiểm thử mà không ảnh hưởng người dùng khác ra sao?
Bạn sẽ giải thích vai trò của các quy tắc destination và route khi cấu hình nhiều phiên bản service như thế nào?
Bạn sẽ kiểm tra xung đột giữa nhiều quy tắc route cùng áp dụng cho một service và xác định thứ tự ưu tiên ra sao?
Bạn sẽ tổ chức mirror traffic đến một phiên bản thử nghiệm mà không cho phản hồi thử nghiệm ảnh hưởng client như thế nào?
Bạn sẽ đánh giá rủi ro của traffic mirroring đối với thao tác ghi có tác dụng phụ và dữ liệu nhạy cảm ra sao?
Bạn sẽ chọn chiến lược cân bằng tải round robin, least-request hoặc consistent hashing theo đặc điểm workload nào?
Bạn sẽ phân tích ảnh hưởng của locality-aware routing tới độ trễ và khả năng phục hồi khi một vùng lỗi mạng ra sao?
Bạn sẽ cấu hình ưu tiên endpoint cùng zone và cơ chế fallback khi các endpoint nội vùng không còn khỏe như thế nào?
Bạn sẽ kiểm tra sự khác nhau giữa trạng thái ready của Pod và trạng thái upstream khỏe mà proxy quan sát được ra sao?
Bạn sẽ xử lý tình huống một endpoint luôn trả lỗi nhưng vẫn vượt qua health check ở nền tảng điều phối như thế nào?
Bạn sẽ định nghĩa connection pool và giới hạn số kết nối đồng thời đến backend để bảo vệ service yếu ra sao?
Bạn sẽ phân biệt yêu cầu HTTP, gRPC và giao tiếp TCP thuần khi áp dụng chính sách định tuyến lớp 7 như thế nào?
Bạn sẽ đánh giá tác động của HTTP/2 multiplexing và kết nối dài đến cơ chế cân bằng tải giữa các endpoint ra sao?
Bạn sẽ thiết kế traffic policy cho WebSocket, streaming hoặc giao tiếp lâu dài khi triển khai qua mesh như thế nào?
Bạn sẽ xác định những dấu hiệu nào cho thấy proxy phân loại nhầm giao thức và làm request thất bại?
Bạn sẽ thiết lập timeout tổng cho một request đi qua nhiều service để không vượt quá ngân sách thời gian ra sao?
Bạn sẽ so sánh timeout kết nối, timeout chờ phản hồi và timeout của toàn bộ request trong traffic policy như thế nào?
Những điều kiện về loại lỗi và tính idempotent nào cho phép bạn bật retry cho một request tại mesh?
Bạn sẽ điều chỉnh retry count, backoff và jitter để tránh khuếch đại tải khi backend đang gặp sự cố ra sao?
Bạn sẽ xác định nguy cơ retry trùng giữa client SDK, service mesh và ứng dụng, rồi phân bổ trách nhiệm như thế nào?
Bạn sẽ thiết kế chính sách tránh retry thao tác thanh toán khi backend đã xử lý thành công nhưng phản hồi bị mất như thế nào?
Bạn sẽ giải thích circuit breaking tại data plane giới hạn lỗi lan truyền giữa các service như thế nào?
Bạn sẽ đặt ngưỡng kết nối, request đang chờ và số request đồng thời để mesh tự bảo vệ backend ra sao?
Bạn sẽ đánh giá lợi ích và rủi ro của outlier detection khi một endpoint thường xuyên trả HTTP 5xx như thế nào?
Bạn sẽ xử lý tình huống chính sách loại endpoint lỗi khiến toàn bộ backend bị loại khỏi nhóm phục vụ ra sao?
Bạn sẽ phân biệt load shedding, rate limiting và circuit breaking trong các kịch bản quá tải như thế nào?
Bạn sẽ lựa chọn vị trí thực thi rate limiting cục bộ hoặc phân tán khi nhiều sidecar cùng nhận lưu lượng ra sao?
Bạn sẽ xác định fallback nào phù hợp khi thành phần tính quota bị mất kết nối mà hệ thống vẫn cần bảo vệ backend?
Bạn sẽ thiết kế fault injection để thử nghiệm timeout và lỗi HTTP giữa các service mà không gây ảnh hưởng ngoài ý muốn ra sao?
Bạn sẽ sử dụng dữ liệu từ fault injection để xác nhận khả năng chịu lỗi của chuỗi request nhiều hop như thế nào?
Bạn sẽ xử lý trường hợp retry làm p99 latency tăng mặc dù tỷ lệ thành công được cải thiện như thế nào?
Bạn sẽ phân biệt mTLS ở tầng truyền tải với cơ chế xác thực người dùng cuối trong ứng dụng như thế nào?
Bạn sẽ mô tả quá trình hai workload xác minh danh tính lẫn nhau khi thiết lập kết nối mTLS qua mesh ra sao?
Bạn sẽ giải thích cách định danh workload dựa trên service account hoặc identity được cấp phát trong mesh như thế nào?
Bạn sẽ đánh giá vai trò của CA và chuỗi tin cậy chứng chỉ trong việc cấp danh tính cho service như thế nào?
Bạn sẽ kiểm tra cơ chế phân phối, gia hạn và thay chứng chỉ ngắn hạn cho proxy mà không phải restart ứng dụng ra sao?
Bạn sẽ xây dựng lộ trình chuyển từ mTLS permissive sang strict để giảm rủi ro gián đoạn như thế nào?
Bạn sẽ chẩn đoán khi chuyển sang strict mTLS khiến một workload chưa tham gia mesh bị từ chối kết nối ra sao?
Bạn sẽ phân biệt mã hóa traffic trong mesh với mã hóa end-to-end đến chính ứng dụng đối với các yêu cầu tuân thủ ra sao?
Bạn sẽ kiểm tra thông tin định danh peer qua metadata xác thực thay vì dựa vào địa chỉ IP trong môi trường Pod thay đổi liên tục như thế nào?
Bạn sẽ tổ chức trust domain và quan hệ tin cậy khi hai cluster có CA hoặc chính sách danh tính khác nhau ra sao?
Bạn sẽ giải thích SPIFFE ID hoặc chuẩn định danh tương đương giúp xác thực workload giữa nhiều nền tảng như thế nào?
Bạn sẽ thiết kế quy trình thu hồi hoặc thay khóa khi một chứng chỉ workload hoặc khóa CA bị lộ như thế nào?
Bạn sẽ phân biệt authentication policy và authorization policy trên một luồng gọi service từ frontend đến backend ra sao?
Bạn sẽ áp dụng nguyên tắc quyền tối thiểu để chỉ service A được phép gọi một tập endpoint của service B như thế nào?
Bạn sẽ xây dựng chính sách phân quyền dựa trên namespace, service account, HTTP method và path ra sao?
Bạn sẽ xác định những trường hợp phân quyền theo IP không còn đủ tin cậy trong môi trường mesh như thế nào?
Bạn sẽ kiểm tra chính sách mặc định deny và các ngoại lệ cần thiết trước khi áp dụng toàn namespace ra sao?
Bạn sẽ xử lý khi một service bị từ chối dù hai đầu đã bắt tay mTLS thành công bằng quy trình kiểm tra nào?
Bạn sẽ phối hợp Kubernetes NetworkPolicy với authorization policy của mesh mà không nhầm vai trò của hai cơ chế như thế nào?
Bạn sẽ bảo vệ traffic không được proxy hỗ trợ hoặc bị bypass bằng các biện pháp an ninh bổ sung ra sao?
Bạn sẽ lựa chọn bước kiểm tra xác thực JWT ở ingress hoặc tại backend theo phạm vi tin cậy và dữ liệu cần bảo vệ như thế nào?
Bạn sẽ xử lý tình huống application authorization phụ thuộc dữ liệu nghiệp vụ mà proxy không có quyền truy cập như thế nào?
Bạn sẽ đánh giá giới hạn của policy lớp 7 đối với traffic đã mã hóa thêm ở tầng ứng dụng như thế nào?
Bạn sẽ phân biệt kiểm soát truy cập north-south và east-west trong một kiến trúc microservices ra sao?
Bạn sẽ tổ chức phân quyền thay đổi chính sách mesh để nhóm ứng dụng không thể làm suy yếu cấu hình bảo mật chung như thế nào?
Bạn sẽ xác định những chỉ số request rate, error rate và duration mà proxy có thể thu thập mà không sửa ứng dụng?
Bạn sẽ phân biệt telemetry thu ở data plane với log nghiệp vụ cần được phát ra từ ứng dụng như thế nào?
Bạn sẽ sử dụng distributed tracing để theo dõi một request đi qua nhiều sidecar và backend như thế nào?
Bạn sẽ kiểm tra sự liên tục của trace context khi request đổi từ HTTP sang gRPC hoặc đi qua gateway như thế nào?
Bạn sẽ phân tích vì sao mesh có thể thấy latency kết nối nhưng không biết nguyên nhân xử lý chậm bên trong ứng dụng ra sao?
Bạn sẽ phân biệt độ trễ do proxy, thời gian chờ mạng và thời gian xử lý backend bằng những phép đo nào?
Bạn sẽ lựa chọn p50, p95 và p99 latency khi đánh giá tác động của mesh lên trải nghiệm người dùng như thế nào?
Bạn sẽ xây dựng dashboard theo source workload, destination workload, namespace và response code để phát hiện bất thường ra sao?
Bạn sẽ kiểm soát cardinality của metric labels để tránh hệ thống giám sát quá tải khi số service tăng mạnh như thế nào?
Bạn sẽ tổ chức access log ở proxy để điều tra lỗi mà không ghi lộ token hoặc thông tin cá nhân như thế nào?
Bạn sẽ đánh giá sampling của tracing theo lưu lượng thực tế để cân bằng chi phí và khả năng điều tra lỗi ra sao?
Bạn sẽ tìm nguyên nhân số liệu success rate trong mesh khác với số liệu do backend báo cáo như thế nào?
Bạn sẽ thiết kế cảnh báo khi tỷ lệ 5xx, timeout hoặc kết nối bị từ chối tăng cao trong một luồng gọi service như thế nào?
Bạn sẽ xác định sự cố nằm ở DNS, route, mTLS, authorization hay upstream bằng thứ tự kiểm tra nào?
Bạn sẽ đọc thông tin cấu hình thực tế của proxy để xác định route hoặc cluster nào đã được control plane áp dụng ra sao?
Bạn sẽ đối chiếu trạng thái desired configuration với trạng thái đã nhận tại data plane để phát hiện cấu hình chưa đồng bộ như thế nào?
Bạn sẽ dùng log của control plane, proxy và ứng dụng để truy vết một lỗi request qua các lớp ra sao?
Bạn sẽ kiểm tra các thay đổi mesh policy bằng môi trường staging và traffic mô phỏng trước khi triển khai như thế nào?
Bạn sẽ đánh giá tương thích phiên bản control plane và data plane trước khi thực hiện nâng cấp rolling upgrade ra sao?
Bạn sẽ thiết kế rollback cấu hình route hoặc policy khi một thay đổi làm tăng lỗi kết nối như thế nào?
Bạn sẽ kiểm soát resource requests và limits cho proxy để tránh làm Pod bị thiếu CPU hoặc bộ nhớ như thế nào?
Bạn sẽ lựa chọn workload cần tắt sidecar injection dựa trên các giới hạn về vòng đời và giao tiếp nào?
Bạn sẽ phân biệt tác động của readiness, startup và termination lifecycle của proxy đối với request đang xử lý như thế nào?
Bạn sẽ thiết kế quy trình drain kết nối trước khi Pod hoặc sidecar bị dừng để giảm số request thất bại ra sao?
Bạn sẽ lên kế hoạch triển khai mesh vào namespace đang chạy production mà vẫn giữ hoạt động của dịch vụ ngoài mesh như thế nào?
Bạn sẽ đánh giá tác động của network policy, CNI và Pod security khi bật tự động injection hoặc chuyển hướng traffic ra sao?
Bạn sẽ tổ chức cấu hình mesh bằng GitOps hoặc infrastructure as code để xem xét và kiểm toán thay đổi như thế nào?
Bạn sẽ xác định SLO và ngân sách lỗi riêng cho control plane và data plane theo mức ảnh hưởng đến ứng dụng như thế nào?
Bạn sẽ thiết kế thử nghiệm tải trước và sau khi triển khai mesh để đo mức tăng CPU, RAM và latency ra sao?
Bạn sẽ đánh giá tổng chi phí sở hữu của mesh dựa trên số workload, số proxy và yêu cầu vận hành như thế nào?
Bạn sẽ lựa chọn một mô hình mesh phù hợp cho workload ngoài Kubernetes hoặc nhiều cluster dựa trên những giới hạn nào?
Bạn sẽ mô tả cách thiết lập danh tính và định tuyến traffic giữa hai cluster trong một multi-cluster mesh như thế nào?
Bạn sẽ xác định rủi ro khi các cluster mất kết nối với nhau nhưng vẫn cần giải quyết request cục bộ ra sao?
Bạn sẽ so sánh service mesh với việc dùng thư viện resilience và telemetry trong ứng dụng để quyết định có nên áp dụng ra sao?
Nếu Pod đã được inject sidecar nhưng request vẫn gọi thẳng đến backend, bạn sẽ kiểm tra quá trình chuyển hướng lưu lượng như thế nào?
Nếu mTLS strict vừa bật khiến một service không giao tiếp được với service khác, bạn sẽ khoanh vùng identity, trust và policy ra sao?
Nếu canary nhận nhiều lưu lượng hơn tỷ lệ cấu hình, bạn sẽ kiểm tra hành vi kết nối dài, route và load balancing như thế nào?
Nếu latency của ứng dụng tăng mạnh sau khi bật mesh, bạn sẽ xác định chi phí proxy, cấu hình retry và độ trễ mạng như thế nào?
Nếu control plane tạm ngừng hoạt động trong giờ cao điểm, bạn sẽ xác định loại request nào vẫn phục vụ được và loại thay đổi nào bị ảnh hưởng ra sao?
Nếu backend đã xử lý thành công nhưng client nhận timeout và retry, bạn sẽ phân chia cơ chế chống lặp giữa mesh và ứng dụng như thế nào?
Nếu một namespace áp dụng default-deny làm gián đoạn việc gọi service, bạn sẽ xây dựng quy trình khôi phục và giảm thiểu tái diễn như thế nào?
Nếu hệ thống microservices có hàng trăm service, nhiều nhóm phát triển và yêu cầu mTLS, canary, tracing, bạn sẽ đề xuất kiến trúc mesh và lộ trình triển khai ra sao?
