Bạn giải thích client-side load balancing giải quyết vấn đề gì trong giao tiếp giữa các microservice?
Bạn phân biệt cân bằng tải phía client và cân bằng tải phía server theo nơi quyết định chọn endpoint như thế nào?
Bạn mô tả vai trò của Spring Cloud LoadBalancer trong hệ sinh thái Spring Cloud Commons ra sao?
Bạn sẽ chọn Spring Cloud LoadBalancer thay vì gọi trực tiếp một URL cố định trong tình huống nào?
Bạn phân biệt định danh logic service ID với địa chỉ IP và port vật lý của một instance như thế nào?
Bạn giải thích lợi ích của việc tách danh tính dịch vụ khỏi địa chỉ triển khai khi autoscaling như thế nào?
Bạn so sánh cách gọi qua Kubernetes Service DNS với lựa chọn từng ServiceInstance ở phía client ra sao?
Bạn phân tích những trường hợp hai tầng load balancing có thể gây khó khăn khi điều tra sự cố như thế nào?
Bạn xác định ranh giới trách nhiệm của discovery, load balancing và HTTP client trong một lời gọi như thế nào?
Bạn sẽ mô tả đường đi của request từ business service tới một backend được chọn bởi LoadBalancer ra sao?
Bạn phân biệt tính khả dụng của danh sách instance với độ sẵn sàng thực tế của từng instance như thế nào?
Bạn xác định khi nào load balancing chỉ cần cấu hình đơn giản và khi nào cần chính sách định tuyến riêng ra sao?
Bạn giải thích tại sao nhiều instance cùng một service ID không tự bảo đảm phân phối tải đồng đều ra sao?
Bạn đánh giá những chi phí phát sinh khi load balancer chọn endpoint mới cho mỗi request như thế nào?
Bạn phân biệt lựa chọn instance ở cấp request với phân phối kết nối TCP trong connection pool như thế nào?
Bạn mô tả ảnh hưởng của rolling deployment tới danh sách backend mà client sử dụng như thế nào?
Bạn sẽ chọn đơn vị cấu hình riêng cho từng downstream service dựa trên những yếu tố nào?
Bạn phân tích vì sao thuật toán chọn instance tốt vẫn không giải quyết được dependency bị quá tải toàn hệ thống như thế nào?
Bạn giải thích mối liên hệ giữa timeout, retry và quyết định chọn instance của client-side load balancer ra sao?
Bạn sẽ đánh giá hiệu quả của LoadBalancer bằng những chỉ số ngoài tỷ lệ request thành công như thế nào?
Bạn phân biệt việc chuyển request sang backend khác với việc thực thi lại cùng một thao tác nghiệp vụ ra sao?
Bạn xác định những hệ thống nào không cần discovery động mà vẫn có thể dùng load balancing tĩnh như thế nào?
Bạn giải thích vì sao Spring Cloud LoadBalancer không thay thế xác thực hay phân quyền giữa các dịch vụ như thế nào?
Bạn thiết kế lớp adapter outbound để các tầng nghiệp vụ không phụ thuộc trực tiếp vào cơ chế chọn instance như thế nào?
Bạn sẽ kiểm tra khả năng tương thích của Spring Boot, Spring Cloud release train và starter LoadBalancer ra sao?
Bạn phân biệt vai trò của DiscoveryClient và ReactiveDiscoveryClient khi lấy danh sách instance như thế nào?
Bạn mô tả các thông tin quan trọng trong ServiceInstance mà client dùng để tạo URI yêu cầu ra sao?
Bạn xác định cách ánh xạ service ID sang danh sách endpoint qua một registry cụ thể như thế nào?
Bạn giải thích lý do discovery có thể trả instance nhưng ứng dụng vẫn kết nối thất bại như thế nào?
Bạn sẽ lựa chọn nguồn ServiceInstance tĩnh khi viết ứng dụng chạy local hoặc integration test ra sao?
Bạn phân biệt cấu hình SimpleDiscoveryClient với một DiscoveryClient kết nối service registry ra sao?
Bạn đánh giá thời điểm nên tích hợp Eureka, Consul hoặc Kubernetes discovery qua abstraction của Spring Cloud như thế nào?
Bạn giải thích rủi ro khi client lấy danh sách instance rỗng trong quá trình service vừa scale down ra sao?
Bạn sẽ thiết kế xử lý lỗi khi không còn bất kỳ ServiceInstance nào khả dụng cho service ID ra sao?
Bạn phân biệt lỗi do registry không sẵn sàng với lỗi do không có instance đăng ký bằng những tín hiệu nào?
Bạn xác định khi nào cần đọc metadata để chọn zone, version hoặc nhóm backend như thế nào?
Bạn giải thích vì sao metadata dùng để định tuyến không thể coi là nguồn đáng tin cậy cho phân quyền người dùng như thế nào?
Bạn sẽ đặt quy ước cho service ID và metadata để giảm nhầm lẫn giữa các môi trường triển khai ra sao?
Bạn phân tích tác động của service ID phân biệt chữ hoa chữ thường hoặc sai tên lên kết quả khám phá như thế nào?
Bạn sẽ quyết định thời gian cache danh sách instance dựa trên nhịp autoscaling và chi phí discovery ra sao?
Bạn phân biệt stale discovery cache với stale HTTP connection khi một instance bị xóa khỏi registry như thế nào?
Bạn mô tả tác động của độ trễ cập nhật registry tới các lời gọi trong giai đoạn rolling update ra sao?
Bạn sẽ theo dõi các sự kiện instance được thêm, bị xóa hoặc thay đổi trạng thái readiness như thế nào?
Bạn giải thích vai trò của ServiceInstanceListSupplier trong chuỗi cung cấp backend cho LoadBalancer ra sao?
Bạn phân biệt ServiceInstanceListSupplier với DiscoveryClient ở trách nhiệm biến đổi danh sách instance như thế nào?
Bạn sẽ xây dựng một chuỗi ServiceInstanceListSupplier để thêm cache và lọc instance theo điều kiện ra sao?
Bạn phân tích vì sao thứ tự ghép các supplier có thể làm thay đổi kết quả lựa chọn backend như thế nào?
Bạn mô tả cách DiscoveryClientServiceInstanceListSupplier nhận danh sách backend từ discovery như thế nào?
Bạn sẽ xác định nơi đặt bước lọc zone và nơi đặt bước chọn thuật toán cuối cùng ra sao?
Bạn phân biệt danh sách ServiceInstance chưa qua xử lý với danh sách đã được lọc trước khi chọn ra sao?
Bạn giải thích lợi ích của CachingServiceInstanceListSupplier khi registry có độ trễ hoặc giới hạn truy vấn như thế nào?
Bạn sẽ đo tần suất gọi registry trước và sau khi bật cache trong supplier như thế nào?
Bạn phân tích rủi ro dùng đồng thời nhiều lớp cache khiến danh sách instance cập nhật quá chậm như thế nào?
Bạn xác định cách hết hạn hoặc làm mới cache khi instance mới được đăng ký ra sao?
Bạn sẽ xử lý một instance đã bị deregister nhưng còn nằm trong danh sách cache như thế nào?
Bạn phân biệt cache instance với HTTP response cache về dữ liệu và chính sách làm mới như thế nào?
Bạn giải thích mục đích của HealthCheckServiceInstanceListSupplier trong việc sàng lọc backend như thế nào?
Bạn sẽ quyết định khi nào health check từ client có giá trị bổ sung so với health của service registry ra sao?
Bạn phân tích tải mà health check chủ động từ nhiều client có thể tạo lên từng backend như thế nào?
Bạn sẽ lựa chọn endpoint và timeout health check sao cho không gây tác dụng phụ nghiệp vụ như thế nào?
Bạn giải thích tại sao trả HTTP 200 ở health endpoint chưa chắc đồng nghĩa backend xử lý mọi nghiệp vụ thành công như thế nào?
Bạn phân biệt liveness, readiness và health check chủ động của LoadBalancer về mục tiêu như thế nào?
Bạn sẽ thiết kế chính sách xử lý khi toàn bộ instance bị health check đánh dấu không khả dụng ra sao?
Bạn phân tích rủi ro health check flapping làm instance liên tục ra vào danh sách lựa chọn như thế nào?
Bạn xác định khoảng kiểm tra health và ngưỡng lỗi phù hợp cho downstream có lưu lượng cao ra sao?
Bạn sẽ so sánh chi phí health check qua Kubernetes API và gọi trực tiếp endpoint backend như thế nào?
Bạn giải thích cách ZonePreferenceServiceInstanceListSupplier hỗ trợ ưu tiên instance cùng zone như thế nào?
Bạn sẽ thiết kế fallback khi không tìm được instance phù hợp zone ưu tiên như thế nào?
Bạn phân tích hậu quả của metadata zone không nhất quán giữa các instance trong registry như thế nào?
Bạn sẽ tạo policy chọn instance theo thuộc tính canary hoặc phiên bản phần mềm bằng cách nào?
Bạn xác định cơ chế phân biệt metadata phục vụ routing với thông tin phiên bản dùng cho observability ra sao?
Bạn sẽ quản lý danh sách backend khi registry trả nhiều instance trùng ID hoặc trùng địa chỉ như thế nào?
Bạn phân tích vấn đề đồng thời khi supplier nhận nhiều sự kiện cập nhật danh sách instance liên tiếp ra sao?
Bạn sẽ kiểm thử một supplier tùy chỉnh chỉ lọc instance được phép và không làm rò rỉ dữ liệu tenant như thế nào?
Bạn đánh giá ảnh hưởng của supplier có logic blocking tới thời gian lựa chọn endpoint trong WebFlux ra sao?
Bạn phân biệt cache hit của supplier với lần chọn instance theo thuật toán load balancing như thế nào?
Bạn sẽ thiết kế chiến lược quan sát số instance trước và sau từng bước lọc ra sao?
Bạn giải thích cơ chế RoundRobinLoadBalancer phân phối các lượt chọn trên danh sách instance như thế nào?
Bạn phân biệt RoundRobinLoadBalancer và RandomLoadBalancer về hành vi và tính dự đoán được ra sao?
Bạn sẽ chọn round-robin khi các backend có năng lực tương đối đồng đều dựa trên tiêu chí nào?
Bạn phân tích vì sao round-robin không nhất thiết cho phân bố request hoàn toàn đồng đều khi traffic thấp như thế nào?
Bạn giải thích tình huống thời gian xử lý của các backend khác nhau khiến round-robin chưa tối ưu ra sao?
Bạn sẽ đánh giá khi nào một thuật toán chọn ngẫu nhiên đủ tốt thay vì tạo policy phức tạp như thế nào?
Bạn phân biệt cân bằng theo số request với cân bằng theo số kết nối đang hoạt động như thế nào?
Bạn sẽ thiết kế quy tắc chọn instance có trọng số khi backend có năng lực xử lý khác nhau ra sao?
Bạn phân tích rủi ro dùng weighted routing khi metadata trọng số không được cập nhật theo năng lực thực tế như thế nào?
Bạn xác định khi nào session affinity hoặc sticky routing thật sự là yêu cầu và hệ quả của nó ra sao?
Bạn sẽ giải quyết nhu cầu đồng nhất route người dùng mà không giữ state phiên trong bộ nhớ của Pod như thế nào?
Bạn phân biệt service affinity với việc sử dụng load balancer cache cùng instance giữa các request như thế nào?
Bạn giải thích tác động của trạng thái backend không đồng nhất lên quyết định sticky routing như thế nào?
Bạn sẽ thiết kế failover khi instance ưu tiên trở nên không khả dụng nhưng request có session affinity ra sao?
Bạn phân tích khả năng chuyển request giữa instance mà không làm mất tính nhất quán dữ liệu ra sao?
Bạn sẽ chọn tiêu chí lọc instance bằng zone, version hoặc trạng thái trước khi thuật toán quyết định backend như thế nào?
Bạn mô tả ReactorLoadBalancer<ServiceInstance> trừu tượng hóa quá trình chọn backend bất đồng bộ ra sao?
Bạn phân biệt một ReactorLoadBalancer chọn một instance với ServiceInstanceListSupplier cung cấp danh sách như thế nào?
Bạn sẽ tạo triển khai policy load balancing riêng mà vẫn giữ contract lựa chọn ServiceInstance như thế nào?
Bạn đánh giá rủi ro khi policy tùy chỉnh tự truy cập Kubernetes hoặc registry thay vì dùng supplier ra sao?
Bạn sẽ xác định nên giữ state của thuật toán lựa chọn ở cấp service hay cấp request như thế nào?
Bạn phân tích cách tăng hoặc giảm số instance có thể ảnh hưởng đến bộ đếm round-robin ra sao?
Bạn sẽ xử lý danh sách instance thay đổi ngay giữa thời điểm chọn và thời điểm kết nối như thế nào?
Bạn phân biệt fallback chọn instance khác với retry toàn bộ một lời gọi đã gửi đi như thế nào?
Bạn sẽ kiểm tra policy có công bằng khi backend liên tục vào hoặc rời khỏi danh sách ra sao?
Bạn xác định cách tránh tạo policy khiến một nhóm instance bị đói traffic quá lâu như thế nào?
Bạn sẽ đo độ lệch phân phối traffic giữa các instance trong một kịch bản tải thực tế ra sao?
Bạn đánh giá khi nào nên bỏ policy tùy chỉnh để sử dụng lại hành vi mặc định của Spring Cloud LoadBalancer như thế nào?
Bạn giải thích ý nghĩa của annotation @LoadBalanced khi tích hợp client HTTP với service-name URI ra sao?
Bạn mô tả cách RestTemplate được gắn @LoadBalanced để gọi một service qua tên logic như thế nào?
Bạn sẽ phân biệt RestTemplate được load-balanced với RestTemplate thường trong cùng ứng dụng ra sao?
Bạn giải thích vì sao nên khai báo qualifier cho các HTTP client builder khi có nhiều loại client như thế nào?
Bạn thiết kế RestClient.Builder được gắn @LoadBalanced mà không làm hỏng lời gọi tới URL công khai ra sao?
Bạn sẽ kiểm tra một RestClient dùng URI theo service ID đã thực sự đi qua LoadBalancer như thế nào?
Bạn phân biệt sử dụng RestClient và RestTemplate theo API style, khả năng duy trì và môi trường Java như thế nào?
Bạn mô tả cách WebClient.Builder được gắn @LoadBalanced để kết nối tới service ID ra sao?
Bạn phân tích vai trò của ReactorLoadBalancerExchangeFilterFunction trong đường đi WebClient reactive như thế nào?
Bạn sẽ giải thích vì sao phải giữ non-blocking behavior khi chọn instance trong một WebFlux request như thế nào?
Bạn phân biệt việc dùng WebClient với dùng RestClient trong service Spring MVC có workload I/O như thế nào?
Bạn sẽ lựa chọn kiểu client theo throughput, thread model và nhu cầu streaming như thế nào?
Bạn phân tích tác động của việc gọi block trong pipeline WebClient dù LoadBalancer hoạt động đúng ra sao?
Bạn sẽ thiết kế WebClient có base URL động theo service ID và header bảo mật theo từng request như thế nào?
Bạn phân biệt truyền Host header, SNI và DNS hostname khi URL ban đầu chứa logical service name như thế nào?
Bạn xác định cách xử lý HTTPS khi địa chỉ được chọn có scheme hoặc chứng chỉ khác dự kiến như thế nào?
Bạn sẽ kiểm tra URI được biến đổi từ service ID sang host và port cuối cùng mà không log token nhạy cảm ra sao?
Bạn phân tích rủi ro một HTTP client tự tạo không dùng bean được instrument nên bỏ qua LoadBalancer như thế nào?
Bạn sẽ chọn cấu hình HTTP connection pool để tránh mở kết nối mới mỗi request ra sao?
Bạn giải thích vì sao keep-alive có thể tiếp tục dùng kết nối cũ dù danh sách instance đã thay đổi như thế nào?
Bạn đánh giá tác động của DNS caching và connection reuse đến chính sách chọn instance của client ra sao?
Bạn sẽ xác định lúc nào một lỗi kết nối xuất hiện trước và sau khi chọn ServiceInstance như thế nào?
Bạn mô tả cách OpenFeign diễn giải một client theo service name khi tích hợp Spring Cloud LoadBalancer ra sao?
Bạn phân biệt việc OpenFeign sử dụng URL cụ thể và sử dụng service ID qua discovery như thế nào?
Bạn giải thích vai trò của FeignBlockingLoadBalancerClient trong việc thực hiện lời gọi có cân bằng tải như thế nào?
Bạn sẽ chọn OpenFeign thay vì RestClient cho một API downstream có hợp đồng interface ổn định khi nào?
Bạn phân tích ảnh hưởng của cấu hình Feign client riêng từng service đến chính sách timeout và retry ra sao?
Bạn sẽ kiểm tra một Feign client có thực sự đi qua load balancing thay vì gọi URL cố định như thế nào?
Bạn xác định cách cấu hình OpenFeign để hai downstream có chính sách kết nối khác nhau ra sao?
Bạn so sánh khả năng mở rộng của HTTP request interceptor trong OpenFeign với filter của WebClient như thế nào?
Bạn sẽ đảm bảo header xác thực, trace và tenant hợp lệ được truyền qua OpenFeign mà không dựa vào metadata registry ra sao?
Bạn phân tích rủi ro retry do cả Feign và Spring Cloud LoadBalancer được cấu hình đồng thời như thế nào?
Bạn sẽ phân biệt lỗi do decoder hoặc encoder của Feign với lỗi kết nối tới backend được chọn ra sao?
Bạn xác định cách xử lý fallback khi một Feign client không nhận được ServiceInstance nào như thế nào?
Bạn sẽ thiết kế một wrapper để logic nghiệp vụ thay đổi từ Feign sang RestClient mà không phải sửa business flow ra sao?
Bạn giải thích thời điểm discovery, chọn instance, mở kết nối và chờ response trong một HTTP request như thế nào?
Bạn phân biệt connect timeout với read hoặc response timeout trong lời gọi tới downstream ra sao?
Bạn sẽ phân bổ deadline tổng của request giữa việc chọn instance và thực hiện HTTP call như thế nào?
Bạn phân tích tác động của discovery chậm tới latency khi HTTP timeout được đặt đúng nhưng request vẫn chậm ra sao?
Bạn sẽ cấu hình timeout riêng cho endpoint truy vấn nhanh và endpoint xử lý lâu theo SLA nào?
Bạn phân biệt timeout của HTTP client với TimeLimiter hoặc circuit breaker ở tầng service như thế nào?
Bạn sẽ xác định khi nào lời gọi đã đến backend nhưng response bị mất và kết quả nghiệp vụ không rõ như thế nào?
Bạn giải thích tại sao retry không thể tự bảo đảm exactly-once cho thao tác ghi dữ liệu như thế nào?
Bạn thiết kế idempotency key để có thể retry một lệnh tạo đơn hàng qua các instance khác nhau ra sao?
Bạn sẽ chọn những status code và exception nào đủ điều kiện retry khi downstream tạm thời lỗi như thế nào?
Bạn phân biệt retry trên cùng một instance với retry để chọn instance khác như thế nào?
Bạn sẽ kiểm tra chính sách retry có làm reselect ServiceInstance sau lỗi kết nối như thế nào?
Bạn phân tích rủi ro gửi lại request POST sau timeout dù backend đã commit thành công như thế nào?
Bạn sẽ quyết định số lần retry, thời gian backoff và jitter trong ngân sách deadline như thế nào?
Bạn xác định cách phối hợp retry của LoadBalancer, HTTP client và resilience layer để tránh retry amplification ra sao?
Bạn phân biệt lỗi trả về do circuit breaker OPEN với lỗi do không có ServiceInstance trong cách xử lý caller như thế nào?
Bạn giải thích vì sao load balancing không thay thế bulkhead khi nhiều request cùng chờ dependency chậm như thế nào?
Bạn sẽ đặt giới hạn concurrency cho từng downstream để tránh cạn connection pool chung ra sao?
Bạn thiết kế cách ưu tiên giảm tải thay vì retry khi downstream báo 429 Too Many Requests ra sao?
Bạn sẽ phân tích khả năng retry storm khi một Deployment vừa phục hồi sau outage như thế nào?
Bạn xác định khi nào nên bỏ retry hoàn toàn với thao tác không idempotent ra sao?
Bạn sẽ kết hợp fallback với load balancing mà không trả dữ liệu giả tạo cho nghiệp vụ nhạy cảm như thế nào?
Bạn phân biệt fallback do thiếu instance với fallback do response lỗi nghiệp vụ như thế nào?
Bạn sẽ thiết kế chính sách fail-fast khi supplier trả danh sách rỗng để không tích lũy request đang chờ như thế nào?
Bạn đánh giá ảnh hưởng của việc mở circuit breaker tới phân bố traffic trên các instance còn lại ra sao?
Bạn giải thích tại sao một instance bị chậm không nhất thiết có thể được loại khỏi danh sách chỉ bằng retry như thế nào?
Bạn sẽ thiết kế xử lý cancellation khi client hủy WebClient subscription trong lúc đang kết nối backend ra sao?
Bạn phân tích tác động của một request streaming dài tới khả năng phân phối các request mới giữa instance như thế nào?
Bạn sẽ xác định cách kiểm soát max in-flight request khi các backend có khả năng xử lý không đồng đều ra sao?
Bạn phân biệt lỗi hạ tầng do timeout với lỗi nghiệp vụ HTTP 4xx khi lập metric retry như thế nào?
Bạn sẽ tính toán số lời gọi outbound thực tế trên mỗi request inbound khi có cả retry và fallback ra sao?
Bạn xác định vị trí tốt nhất để đo tổng thời gian retry thay vì chỉ thời gian một attempt như thế nào?
Bạn giải thích vai trò của LoadBalancerLifecycle trong quan sát các bước lựa chọn và kết quả request như thế nào?
Bạn sẽ thiết kế metric tách thời gian chọn instance khỏi thời gian thực hiện HTTP call ra sao?
Bạn phân biệt độ trễ của discovery, lựa chọn backend và phản hồi từ dependency trong distributed trace như thế nào?
Bạn sẽ đặt tên metric theo service ID để theo dõi tỷ lệ lỗi mà không dùng request ID làm tag như thế nào?
Bạn đánh giá nguy cơ gắn host hoặc Pod UID vào metric label khiến cardinality tăng quá lớn ra sao?
Bạn sẽ sử dụng Micrometer và Spring Boot Actuator để theo dõi chất lượng lời gọi downstream như thế nào?
Bạn phân biệt lỗi không tìm thấy instance với lỗi DNS và lỗi connect timeout qua telemetry như thế nào?
Bạn thiết kế log ghi service ID, policy lựa chọn và loại lỗi mà không lộ bearer token như thế nào?
Bạn sẽ gắn correlation ID để liên hệ request inbound, lần chọn instance và retry attempt ra sao?
Bạn phân tích vì sao một trace có nhiều client span khi một yêu cầu phải retry tới nhiều backend như thế nào?
Bạn sẽ tạo dashboard theo dependency gồm request rate, error rate và p95 latency như thế nào?
Bạn lựa chọn chỉ số nào để phát hiện mất cân bằng tải giữa các instance mà không cần đọc từng log như thế nào?
Bạn phân biệt phân phối tổng số request với phân phối số request đang xử lý đồng thời trong dashboard như thế nào?
Bạn sẽ theo dõi số instance available trước và sau health filter như thế nào?
Bạn phân tích dấu hiệu khi health check flapping làm tỷ lệ lỗi thực tế tăng ra sao?
Bạn thiết kế cảnh báo khi số instance về 0 hoặc tỷ lệ lời gọi thất bại tăng trong rolling deployment như thế nào?
Bạn sẽ phân biệt cache discovery stale với backend thực sự không healthy bằng log và metric nào?
Bạn đánh giá cách so sánh chỉ số trước và sau khi bật một policy load balancing mới ra sao?
Bạn sẽ xác định một instance mới gây lỗi nhiều hơn các instance cũ trong canary rollout như thế nào?
Bạn thiết kế trace context propagation qua RestClient, WebClient và OpenFeign theo cách nhất quán ra sao?
Bạn phân biệt metadata dùng để routing với dữ liệu bảo mật không nên gắn vào ServiceInstance như thế nào?
Bạn sẽ cấu hình TLS và xác minh danh tính backend khi địa chỉ cuối được LoadBalancer thay đổi ra sao?
Bạn phân tích rủi ro client-side routing đưa traffic sang namespace hoặc môi trường triển khai sai ra sao?
Bạn thiết kế allowlist service ID hoặc namespace để không định tuyến tới dịch vụ ngoài phạm vi cho phép như thế nào?
Bạn sẽ bảo vệ credentials truy cập service registry khỏi bị ghi log khi discovery thất bại ra sao?
Bạn xác định cách kiểm tra quyền truy cập một dependency độc lập với việc nó đã được discovery ra sao?
Bạn đánh giá khi nào một custom supplier có thể gây rò rỉ tenant do lọc metadata sai như thế nào?
Bạn sẽ xác định cách giới hạn quyền của discovery client chỉ đủ đọc instance liên quan ra sao?
Bạn phân biệt xác thực giữa các service với xác thực khi kết nối registry trong cùng một yêu cầu ra sao?
Bạn thiết kế kiểm thử bảo mật để một service ID giả mạo không được chuyển thành host nội bộ ngoài dự kiến như thế nào?
Bạn giải thích cách unit test LoadBalancer khác integration test của HTTP client được cân bằng tải như thế nào?
Bạn sẽ dùng fake ServiceInstanceListSupplier để cấp danh sách instance ổn định cho test như thế nào?
Bạn kiểm thử RoundRobinLoadBalancer có phân phối các lượt chọn trên ba instance như thế nào?
Bạn thiết kế kiểm thử RandomLoadBalancer sao cho không phụ thuộc một chuỗi lựa chọn ngẫu nhiên cố định ra sao?
Bạn sẽ kiểm thử supplier trả danh sách rỗng và xác minh caller nhận lỗi có kiểm soát như thế nào?
Bạn xây dựng test khi service registry trả hai instance trùng địa chỉ hoặc metadata không hợp lệ như thế nào?
Bạn sẽ kiểm tra thứ tự lọc zone và health khi kết hợp nhiều ServiceInstanceListSupplier ra sao?
Bạn thiết kế test khi một instance bị loại khỏi danh sách giữa hai lượt gọi liên tiếp như thế nào?
Bạn sẽ dùng ApplicationContextRunner để xác minh auto-configuration LoadBalancer theo classpath và properties ra sao?
Bạn phân biệt kiểm thử RestClient.Builder có @LoadBalanced với một RestClient thông thường như thế nào?
Bạn kiểm tra WebClient được cấu hình đúng exchange filter chọn ServiceInstance bằng phương pháp nào?
Bạn sẽ mock một server downstream để xác minh Host, port và path cuối mà HTTP client sử dụng ra sao?
Bạn thiết kế integration test cho OpenFeign đi qua FeignBlockingLoadBalancerClient thay vì URL cố định ra sao?
Bạn sẽ kiểm thử timeout xảy ra trước khi backend phản hồi mà vẫn xác minh request không bị retry quá mức như thế nào?
Bạn đánh giá cách test retry sang instance khác mà không phụ thuộc mạng cluster thật như thế nào?
Bạn kiểm thử POST timeout nhưng backend đã commit để xác minh idempotency như thế nào?
Bạn sẽ viết test cho health check supplier khi instance trả 200, 503 hoặc kết nối bị từ chối ra sao?
Bạn xác định cách kiểm thử client không dùng instance bị đánh dấu unhealthy trong thời gian danh sách còn hiệu lực như thế nào?
Bạn kiểm thử stale discovery cache khi một Pod bị xóa và client vẫn giữ kết nối như thế nào?
Bạn sẽ mô phỏng rolling deployment để kiểm tra behavior khi endpoint được thêm và bị gỡ ra sao?
Bạn xây dựng test cho zone fallback khi zone ưu tiên không có instance nào như thế nào?
Bạn kiểm thử một policy canary chỉ đưa một phần traffic tới phiên bản mới như thế nào?
Bạn xác định cách kiểm tra thời gian chọn backend không block event loop trong WebFlux ra sao?
Bạn sẽ dùng StepVerifier để kiểm thử một reactive load balancing flow lỗi khi không có backend như thế nào?
Bạn phân tích cách load test phát hiện connection pool saturation do số instance tăng như thế nào?
Bạn xây dựng chaos test làm mất discovery backend trong khi các instance HTTP vẫn hoạt động như thế nào?
Bạn sẽ kiểm thử một instance có độ trễ cao làm biến động p99 latency của toàn service ra sao?
Bạn xác định tiêu chí nghiệm thu về lỗi, throughput và fairness trước khi thay chính sách load balancing ra sao?
Bạn thiết kế quy trình rollout policy mới cho một phần instance caller và cách rollback khi kết quả xấu như thế nào?
Bạn sẽ lập runbook điều tra lỗi không tìm thấy instance dù registry hiển thị backend khỏe ra sao?
Bạn mô tả cách kiểm tra dependency compatibility khi nâng cấp Spring Cloud LoadBalancer hoặc OpenFeign như thế nào?
Bạn sẽ quyết định khi nào giảm số lớp cache và filter để đơn giản hóa việc vận hành ra sao?
Bạn xác định cấu hình nào cần tách theo môi trường để tránh client staging gọi service production như thế nào?
Bạn thiết kế cảnh báo khi load balancer liên tục chọn một backend đã bị loại khỏi registry như thế nào?
Bạn sẽ phối hợp grace period, readiness và connection draining để hạn chế lỗi khi scale down như thế nào?
Bạn phân tích ảnh hưởng của việc thay đổi service ID trong quá trình migration tới các HTTP client cũ ra sao?
Bạn lựa chọn cách theo dõi phát hiện lỗi sau deploy trước khi bật traffic toàn bộ tới backend mới như thế nào?
Nếu một RestClient gọi service ID nhưng báo UnknownHostException, bạn sẽ xác định nó có đi qua @LoadBalanced hay chưa như thế nào?
Nếu OpenFeign bỏ qua discovery vì cấu hình URL cố định, bạn sẽ kiểm tra và sửa cấu hình thế nào?
Nếu WebClient vẫn gọi Pod vừa bị xóa, bạn sẽ phân biệt lỗi cache ServiceInstance với connection pool ra sao?
Nếu HealthCheckServiceInstanceListSupplier đánh dấu tất cả instance unhealthy, bạn sẽ thiết kế phản ứng và điều tra như thế nào?
Nếu client có ba instance nhưng 90 phần trăm traffic dồn vào một instance, bạn sẽ đo lường và kiểm tra thuật toán ra sao?
Nếu retry trên POST tạo hai đơn hàng ở hai backend khác nhau, bạn sẽ xử lý idempotency và đối soát như thế nào?
Nếu tất cả client cùng polling health khiến dependency tăng tải, bạn sẽ điều chỉnh kiến trúc health check ra sao?
Nếu một zone bị mất kết nối nhưng zone khác còn khỏe, bạn sẽ chọn cơ chế lọc và fallback như thế nào?
Nếu circuit breaker liên tục OPEN dù một số instance vẫn đáp ứng tốt, bạn sẽ xác định ranh giới breaker và policy chọn instance ra sao?
Nếu người dùng báo timeout nhưng HTTP client log cho thấy chưa mở connection, bạn sẽ tìm latency ở discovery và supplier như thế nào?
Nếu một Deployment rolling update làm tăng lỗi kết nối ngắt quãng, bạn sẽ kiểm tra readiness, cache và drain như thế nào?
Nếu hai tầng retry từ Feign và LoadBalancer cùng được bật, bạn sẽ đo amplification và giảm retry như thế nào?
Nếu registry bị outage nhưng cache còn danh sách backend, bạn sẽ cân nhắc độ mới dữ liệu và chính sách failover ra sao?
Nếu service mesh đã có routing theo version nhưng ứng dụng cũng lọc canary bằng LoadBalancer, bạn sẽ tránh xung đột chính sách như thế nào?
Nếu phải xây dựng giao tiếp dịch vụ Spring Cloud từ đầu, bạn sẽ chọn discovery, supplier, LoadBalancer, HTTP client, retry, timeout và telemetry theo quy trình nào?
