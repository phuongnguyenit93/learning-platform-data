Bạn giải thích Spring Cloud Kubernetes bổ sung năng lực gì cho một ứng dụng Spring Boot triển khai trên Kubernetes?
Bạn phân biệt khả năng Kubernetes cung cấp sẵn với các abstraction do Spring Cloud Kubernetes thêm vào như thế nào?
Bạn sẽ quyết định khi nào ứng dụng cần Spring Cloud Kubernetes thay vì chỉ sử dụng DNS và biến môi trường của Kubernetes ra sao?
Bạn mô tả các thành phần chính tham gia khi một ứng dụng Spring gọi một dịch vụ khác trong cùng cluster như thế nào?
Bạn phân biệt Pod, Deployment và Service về vai trò đối với một ứng dụng Spring Boot như thế nào?
Bạn giải thích vì sao không nên dùng IP của Pod làm địa chỉ cố định cho một dependency như thế nào?
Bạn lựa chọn các tính năng discovery, config hoặc load balancing theo nhu cầu ứng dụng ra sao?
Bạn sẽ thiết kế lớp truy cập hạ tầng để giảm phụ thuộc logic nghiệp vụ vào API của Kubernetes như thế nào?
Bạn phân tích tác động của việc thêm starter Spring Cloud Kubernetes đối với auto-configuration của Spring Boot ra sao?
Bạn kiểm tra sự tương thích giữa Spring Boot, Spring Cloud và Spring Cloud Kubernetes trước khi nâng cấp như thế nào?
Bạn sẽ lựa chọn BOM và phiên bản dependency để không trộn các thế hệ Spring Cloud không tương thích ra sao?
Bạn giải thích vì sao cài mọi tính năng Spring Cloud Kubernetes có thể làm tăng quyền truy cập và độ phức tạp như thế nào?
Bạn xác định thành phần nào thực sự cần Kubernetes API access và thành phần nào chỉ cần kết nối mạng thông thường ra sao?
Bạn so sánh một service chỉ chạy trong cluster với một ứng dụng chạy cả local và cluster về nhu cầu cấu hình ra sao?
Bạn thiết kế cách tách cấu hình Kubernetes-specific khỏi business service để dễ kiểm thử như thế nào?
Bạn phân biệt việc chạy ứng dụng trong Pod với chạy ứng dụng bên ngoài cluster có kết nối tới API server như thế nào?
Bạn xác định những ranh giới tin cậy giữa ứng dụng, Kubernetes API server và các service nghiệp vụ ra sao?
Bạn sẽ chọn cách xử lý khi không tìm thấy namespace hoặc thông tin cluster trong môi trường local ra sao?
Bạn đánh giá ảnh hưởng của độ trễ truy vấn Kubernetes API đến thời gian khởi động ứng dụng như thế nào?
Bạn sẽ định nghĩa tiêu chí kiểm chứng Spring Cloud Kubernetes thực sự cần thiết trước khi đưa lên production ra sao?
Bạn giải thích DiscoveryClient trong Spring Cloud giúp ứng dụng khám phá các service trong cluster như thế nào?
Bạn phân biệt Spring Cloud DiscoveryClient với cơ chế DNS discovery do Kubernetes Service cung cấp ra sao?
Bạn mô tả cách Kubernetes Service cung cấp địa chỉ logic cho nhiều Pod backend như thế nào?
Bạn sẽ lựa chọn DNS tên Service thay vì gọi DiscoveryClient trực tiếp trong những trường hợp nào?
Bạn giải thích vai trò của ServiceInstance khi Spring Cloud trả thông tin về một endpoint ra sao?
Bạn phân biệt service name, namespace, Pod name và endpoint IP trong quá trình discovery như thế nào?
Bạn xác định cách ứng dụng tìm một service nằm ở namespace khác trong cluster như thế nào?
Bạn thiết kế quy tắc đặt tên service để tránh nhầm lẫn giữa các namespace và môi trường ra sao?
Bạn đánh giá tác động của selector và labels lên danh sách Pod được một Service định tuyến như thế nào?
Bạn sẽ chẩn đoán trường hợp Kubernetes Service tồn tại nhưng không có endpoint khả dụng ra sao?
Bạn phân biệt EndpointSlice và danh sách Pod khi xác định endpoint phục vụ request như thế nào?
Bạn giải thích readiness của Pod ảnh hưởng thế nào tới việc được đưa vào endpoint sẵn sàng phục vụ ra sao?
Bạn sẽ kiểm tra thông tin nào khi DiscoveryClient trả về danh sách instance rỗng dù Service đã được tạo?
Bạn phân biệt lỗi truy vấn API server với tình huống service thực sự không có instance như thế nào?
Bạn đánh giá tác động của watch events so với polling khi theo dõi danh sách endpoint thay đổi ra sao?
Bạn sẽ lựa chọn chiến lược cache kết quả discovery để giảm số lượt gọi Kubernetes API như thế nào?
Bạn phân tích rủi ro cache chứa Pod đã bị xóa hoặc chưa sẵn sàng nhận traffic như thế nào?
Bạn thiết kế cách làm mới danh sách instance trong lúc Deployment rolling update như thế nào?
Bạn sẽ giới hạn discovery trong một namespace so với nhiều namespace theo tiêu chí bảo mật và vận hành nào?
Bạn phân biệt việc khám phá mọi service trong namespace với chỉ tìm các service được allowlist ra sao?
Bạn đánh giá ảnh hưởng của network policy tới việc một instance được discovery nhưng không thể gọi HTTP như thế nào?
Bạn lựa chọn cách kết hợp DiscoveryClient với Spring Cloud LoadBalancer khi cần chọn Pod backend ra sao?
Bạn giải thích vì sao Service discovery không tự động bảo đảm ứng dụng gọi thành công một endpoint như thế nào?
Bạn sẽ kiểm tra loại port và protocol công bố bởi Service trước khi xây dựng URI gọi dependency ra sao?
Bạn phân biệt một Service thông thường với headless Service trong việc trả địa chỉ và chọn backend như thế nào?
Bạn mô tả ảnh hưởng của headless Service đến lựa chọn client-side load balancing như thế nào?
Bạn sẽ xử lý khi nhiều container trong Pod có các port khác nhau và metadata discovery không rõ port nào cần dùng ra sao?
Bạn đánh giá rủi ro dùng Pod IP khi service mesh hoặc proxy cần đứng trên đường gọi như thế nào?
Bạn kiểm thử discovery khi số replica tăng từ một lên nhiều instance bằng phương pháp nào?
Bạn sẽ phân tích sự khác nhau giữa DNS cache và cache ServiceInstance khi scale down một Deployment ra sao?
Bạn thiết kế fallback khi Kubernetes API tạm thời không truy cập được nhưng các Service vẫn có thể gọi bằng DNS như thế nào?
Bạn giải thích ReactiveDiscoveryClient khác DiscoveryClient đồng bộ khi tích hợp WebFlux như thế nào?
Bạn sẽ xác định khi nào việc truy vấn Kubernetes API có nguy cơ chặn event loop ra sao?
Bạn đánh giá cách tránh gọi blocking API client trong pipeline reactive như thế nào?
Bạn sẽ kiểm tra kết quả discovery nhất quán giữa ứng dụng chạy servlet và ứng dụng chạy reactive như thế nào?
Bạn phân biệt trực tiếp dùng Kubernetes client với dùng abstraction DiscoveryClient về khả năng thay thế implementation ra sao?
Bạn thiết kế một adapter dự phòng để chạy integration test không cần cluster Kubernetes thật như thế nào?
Bạn sẽ xác định thông tin metadata nào có thể dùng định tuyến theo zone hoặc phiên bản service ra sao?
Bạn giải thích tại sao không nên dựa vào metadata từ Pod để xác thực quyền truy cập người dùng như thế nào?
Bạn phân tích rủi ro khi ứng dụng đọc endpoint của mọi namespace chỉ để hỗ trợ một dependency như thế nào?
Bạn sẽ quyết định tắt tính năng discovery Kubernetes khi hạ tầng đã cung cấp DNS và Service ổn định ra sao?
Bạn giải thích Spring Cloud LoadBalancer giúp chọn ServiceInstance cho lời gọi service-to-service như thế nào?
Bạn phân biệt client-side load balancing với cân bằng tải do kube-proxy hoặc tầng mạng Kubernetes thực hiện ra sao?
Bạn sẽ lựa chọn cơ chế cân bằng tải nào nếu ứng dụng chỉ gọi DNS của một Kubernetes Service ra sao?
Bạn mô tả cách @LoadBalanced thay đổi quá trình xử lý URI dựa trên service ID trong HTTP client như thế nào?
Bạn sẽ tạo RestClient.Builder hỗ trợ load balancing nhưng không ảnh hưởng client gọi URL trực tiếp ra sao?
Bạn phân biệt sử dụng RestClient, RestTemplate và WebClient khi cần tích hợp Spring Cloud LoadBalancer như thế nào?
Bạn thiết kế WebClient có thể gọi một service theo logical name mà không chặn event loop như thế nào?
Bạn sẽ lựa chọn cơ chế RoundRobin hay Random trong client-side load balancing dựa trên yêu cầu nào?
Bạn phân tích ảnh hưởng của các Pod có CPU hoặc latency khác nhau lên thuật toán chọn instance như thế nào?
Bạn xác định khi nào cần ưu tiên Pod cùng zone và khi nào nên cho phép cross-zone fallback ra sao?
Bạn sẽ kiểm tra metadata ServiceInstance để tránh định tuyến tới phiên bản chưa được phép rollout như thế nào?
Bạn phân biệt việc load balancer chọn endpoint mới với HTTP connection pool vẫn tái sử dụng kết nối cũ ra sao?
Bạn sẽ xử lý trường hợp Pod được scale down nhưng client vẫn giữ persistent connection tới Pod đó như thế nào?
Bạn đánh giá cách kết hợp graceful termination với drain kết nối để giảm lỗi trong rolling deployment như thế nào?
Bạn giải thích vì sao retry lời gọi ghi có thể tạo giao dịch trùng dù load balancer chuyển sang endpoint khác như thế nào?
Bạn sẽ thiết kế idempotency cho request có thể được gửi lại sau lỗi kết nối như thế nào?
Bạn xác định chỗ áp dụng timeout và retry để tránh nhiều tầng cùng retry làm nhân tải ra sao?
Bạn phân biệt lỗi không có ServiceInstance với lỗi một Pod trả HTTP 503 như thế nào?
Bạn sẽ thiết kế phản hồi có kiểm soát khi không tìm được instance sẵn sàng cho dependency quan trọng ra sao?
Bạn đánh giá khi nào dùng circuit breaker hoặc bulkhead dù Kubernetes Service đã có cân bằng tải như thế nào?
Bạn sẽ kiểm chứng client-side load balancing có lợi hơn native Kubernetes Service bằng đo đạc nào?
Bạn phân tích hệ quả của việc dùng đồng thời service mesh load balancing và Spring Cloud LoadBalancer ra sao?
Bạn xác định những trường hợp không nên chạy hai tầng chọn Pod để tránh hành vi khó dự đoán ra sao?
Bạn thiết kế metric theo service ID để theo dõi traffic distribution mà không tạo cardinality cao như thế nào?
Bạn sẽ kiểm thử thứ tự chọn instance của load balancer bằng danh sách endpoint giả lập như thế nào?
Bạn đánh giá tác động của stale endpoints lên tỷ lệ lỗi khi Pod chưa hoàn tất quá trình shutdown ra sao?
Bạn giải thích vai trò của ConfigMap trong việc cung cấp cấu hình không nhạy cảm cho ứng dụng Spring Boot như thế nào?
Bạn phân biệt ConfigMap với application.yml được đóng gói bên trong executable jar như thế nào?
Bạn sẽ lựa chọn cách đưa ConfigMap vào Pod qua environment variables hay mounted files theo tiêu chí nào?
Bạn giải thích vì sao environment variable thường không tự thay đổi trong tiến trình khi ConfigMap gốc được sửa như thế nào?
Bạn phân tích cách cập nhật file được mount từ ConfigMap khác với cập nhật cấu hình đã bind vào bean như thế nào?
Bạn thiết kế cấu trúc key trong ConfigMap để phân biệt cấu hình chung và cấu hình của từng service ra sao?
Bạn sẽ xử lý khi cấu hình ConfigMap và cấu hình ứng dụng đóng gói chứa cùng một property như thế nào?
Bạn phân biệt giá trị property lấy từ ConfigMap với giá trị lấy từ Kubernetes Downward API ra sao?
Bạn sẽ kiểm tra thứ tự ưu tiên giữa ConfigMap, biến môi trường và command-line arguments trong Spring Environment như thế nào?
Bạn đánh giá rủi ro thay đổi ConfigMap gây đổi endpoint hoặc timeout của nhiều service cùng lúc ra sao?
Bạn thiết kế quy tắc đặt tên ConfigMap theo application name, namespace hoặc profile như thế nào?
Bạn sẽ quyết định dùng một ConfigMap lớn hay nhiều ConfigMap theo nhóm tính năng dựa trên tiêu chí nào?
Bạn giải thích sự khác nhau giữa cấu hình được đọc từ Kubernetes API và cấu hình từ một volume mount như thế nào?
Bạn lựa chọn cách nạp configuration properties bằng Spring Cloud Kubernetes so với Spring Boot Config Data theo điều kiện nào?
Bạn sẽ thiết kế nguồn cấu hình rõ ràng để tránh cùng một key được nạp hai lần với độ ưu tiên bất ngờ ra sao?
Bạn xác định cách phát hiện một property không được bind do kiểu dữ liệu hoặc tên key không phù hợp như thế nào?
Bạn sẽ dùng @ConfigurationProperties và validation để ngăn cấu hình Kubernetes không hợp lệ như thế nào?
Bạn phân tích lúc nào nên fail-fast nếu ConfigMap bắt buộc bị thiếu và khi nào nên có giá trị dự phòng ra sao?
Bạn thiết kế cách triển khai cùng một container image trên dev, staging và production mà không bake config vào image như thế nào?
Bạn sẽ kiểm tra ConfigMap không mang secret vô tình do lỗi phân loại dữ liệu như thế nào?
Bạn giải thích vì sao Kubernetes Secret không đồng nghĩa với dữ liệu được mã hóa đầu cuối và an toàn tuyệt đối như thế nào?
Bạn phân biệt ConfigMap và Secret về mục tiêu, quyền truy cập và cách triển khai vào Pod ra sao?
Bạn sẽ lựa chọn giữa Secret environment variables và Secret volume mount dựa trên nhu cầu cập nhật và rủi ro rò rỉ như thế nào?
Bạn phân tích ảnh hưởng của thay đổi Secret lên các tiến trình đã nhận credential ở startup như thế nào?
Bạn thiết kế chu kỳ xoay vòng credential để ứng dụng Spring nhận secret mới mà không mất kết nối đang xử lý ra sao?
Bạn sẽ ngăn việc ghi giá trị Secret vào log, Actuator hoặc error response như thế nào?
Bạn đánh giá tác động của quyền đọc Secrets trên toàn namespace so với từng Secret cần thiết như thế nào?
Bạn xác định khi nào nên dùng cơ chế quản lý secret bên ngoài thay cho Kubernetes Secret mặc định như thế nào?
Bạn phân biệt Secret dạng chuỗi được mã hóa biểu diễn với mã hóa tại nơi lưu trữ ra sao?
Bạn sẽ kiểm soát secret bị lưu trong Git history hoặc build artifact bằng quy trình nào?
Bạn thiết kế chính sách hạn chế service account chỉ đọc ConfigMap mà không có quyền đọc Secrets khi không cần thiết như thế nào?
Bạn sẽ xử lý khi ứng dụng cần Secret có tên khác nhau giữa các namespace mà không hardcode chúng trong mã nguồn ra sao?
Bạn kiểm tra startup behavior khi thiếu Secret bắt buộc hoặc Secret chưa được mount như thế nào?
Bạn sẽ thiết kế phương án rollback khi credential mới làm kết nối tới hệ thống hạ nguồn thất bại ra sao?
Bạn phân tích rủi ro của việc sao chép một Secret dùng chung cho quá nhiều ứng dụng như thế nào?
Bạn xác định cách audit truy cập Secrets trong Kubernetes mà không ghi lại nội dung bí mật ra sao?
Bạn sẽ đánh giá yêu cầu compliance khi metadata hoặc biến môi trường chứa thông tin nhạy cảm như thế nào?
Bạn giải thích mục đích của Configuration Watcher trong việc phát hiện thay đổi ConfigMap hoặc Secret như thế nào?
Bạn phân biệt Configuration Watcher với việc ứng dụng tự polling Kubernetes API theo chu kỳ ra sao?
Bạn mô tả luồng từ thay đổi một ConfigMap đến khi các instance Spring Boot nhận cấu hình mới như thế nào?
Bạn sẽ xác định cơ chế gửi tín hiệu refresh hoặc sự kiện cho ứng dụng khi Configuration Watcher phát hiện thay đổi như thế nào?
Bạn phân biệt việc phát hiện một resource thay đổi với việc bean trong ApplicationContext đã áp dụng thay đổi đó ra sao?
Bạn giải thích vì sao chỉ cập nhật Kubernetes Secret không bảo đảm mọi bean Spring đọc lại giá trị mới như thế nào?
Bạn sẽ chọn refresh bean hay rolling restart ứng dụng khi thay đổi cấu hình quan trọng theo tiêu chí nào?
Bạn đánh giá tác động của @RefreshScope khi bean quản lý connection pool hoặc tài nguyên dùng chung như thế nào?
Bạn thiết kế cách cập nhật timeout của outbound client mà không hủy bất ngờ các request đang chạy như thế nào?
Bạn sẽ quản lý những property không phù hợp cho runtime refresh bằng quy tắc nào?
Bạn phân tích nguy cơ các Pod nhận thông báo refresh ở các thời điểm khác nhau dẫn tới cấu hình không đồng nhất như thế nào?
Bạn xác định cách gắn version hoặc checksum cấu hình để nhận biết Pod nào đang dùng bản cũ như thế nào?
Bạn sẽ kiểm tra và giới hạn các loại tài nguyên được Configuration Watcher theo dõi để giảm tải API server ra sao?
Bạn giải thích vai trò của labels hoặc annotations trong việc chọn resource cần quan sát khi tích hợp watcher như thế nào?
Bạn đánh giá rủi ro watcher nhận nhiều sự kiện gần nhau cho cùng một ConfigMap và kích hoạt refresh dồn dập như thế nào?
Bạn sẽ thiết kế cơ chế debounce hoặc hợp nhất sự kiện thay đổi cấu hình như thế nào?
Bạn phân biệt refresh thông qua endpoint quản trị với restart qua Deployment rollout về bảo mật và độ tin cậy ra sao?
Bạn sẽ kiểm soát quyền gọi endpoint refresh để Configuration Watcher không trở thành đường tấn công như thế nào?
Bạn phân tích nhu cầu xác thực giữa watcher và ứng dụng đích khi phát tín hiệu cấu hình thay đổi như thế nào?
Bạn xác định hành vi khi một Pod tạm thời offline và bỏ lỡ thông báo refresh như thế nào?
Bạn sẽ thiết kế cách xác minh phiên bản cấu hình khi một Pod quay lại sau thời gian gián đoạn ra sao?
Bạn giải thích cơ chế thay đổi file mount không tự động cập nhật giá trị đã inject bằng @Value như thế nào?
Bạn đánh giá nguy cơ tài nguyên refresh tạo bean mới nhưng không đóng bean hoặc kết nối cũ đúng cách như thế nào?
Bạn sẽ tạo runbook rollback ConfigMap và xác minh tất cả Pod đã nhận cấu hình cũ như thế nào?
Bạn phân biệt cấu hình cần tính nhất quán đồng thời và cấu hình cho phép rollout dần như thế nào?
Bạn kiểm thử một thay đổi ConfigMap có thật sự làm hành vi ứng dụng thay đổi thay vì chỉ ghi log refresh thành công như thế nào?
Bạn sẽ chọn mô hình ConfigMap immutable và rollout Deployment trong những trường hợp nào?
Bạn xác định khi nào Configuration Watcher không cần thiết vì hệ thống đã có GitOps và rollout theo checksum như thế nào?
Bạn giải thích vai trò của ServiceAccount khi Pod truy cập Kubernetes API qua Spring Cloud Kubernetes như thế nào?
Bạn phân biệt ServiceAccount, Role, RoleBinding, ClusterRole và ClusterRoleBinding trong mô hình RBAC ra sao?
Bạn sẽ lựa chọn Role theo namespace thay vì ClusterRole cho một ứng dụng chỉ quan sát tài nguyên nội bộ như thế nào?
Bạn phân tích khác nhau giữa quyền get, list và watch đối với ConfigMap hoặc endpoint resources như thế nào?
Bạn xác định quyền Kubernetes API tối thiểu để một DiscoveryClient hoạt động theo tính năng đã bật như thế nào?
Bạn sẽ phân quyền riêng cho Configuration Watcher thay vì dùng chung ServiceAccount với tất cả ứng dụng như thế nào?
Bạn giải thích vì sao quyền list hoặc watch Secrets có thể mở rộng phạm vi dữ liệu nhạy cảm mà ứng dụng nhìn thấy ra sao?
Bạn thiết kế RBAC sao cho một service chỉ đọc cấu hình trong namespace của chính nó như thế nào?
Bạn đánh giá rủi ro gán ClusterRoleBinding rộng cho ứng dụng chỉ cần đọc một ConfigMap ra sao?
Bạn sẽ xử lý một lỗi Kubernetes API trả 403 Forbidden bằng cách tìm đúng tài nguyên và verb thiếu ra sao?
Bạn phân biệt lỗi thiếu RBAC với lỗi sai namespace khi ứng dụng không lấy được ConfigMap ra sao?
Bạn sẽ kiểm tra danh tính ServiceAccount thực sự được Pod sử dụng khi quyền hoạt động khác local ra sao?
Bạn phân tích rủi ro mount ServiceAccount token vào Pod không cần truy cập Kubernetes API như thế nào?
Bạn xác định khi nào nên tắt automountServiceAccountToken trong cấu hình Pod ra sao?
Bạn sẽ thiết kế namespace isolation cho các ứng dụng đa tenant dùng Spring Cloud Kubernetes như thế nào?
Bạn kiểm tra NetworkPolicy và RBAC khác nhau thế nào khi điều tra thất bại kết nối tới Kubernetes API server?
Bạn sẽ tổ chức xoay vòng và sử dụng token service account mà không ghi cứng thông tin xác thực như thế nào?
Bạn phân tích nguy cơ một ứng dụng bị xâm nhập có thể dùng token để đọc Secrets hoặc service metadata như thế nào?
Bạn sẽ quyết định khi nào dùng Kubernetes API client trực tiếp và khi nào loại bỏ toàn bộ API permission bằng DNS hoặc volume mount ra sao?
Bạn xây dựng quy trình kiểm tra manifest RBAC bằng policy-as-code trước khi triển khai như thế nào?
Bạn sẽ audit quyền hiện tại của một ServiceAccount so với quyền thực tế ứng dụng dùng bằng phương pháp nào?
Bạn phân biệt quyền cho ứng dụng đọc resource với quyền cho pipeline triển khai tạo hoặc sửa resource như thế nào?
Bạn sẽ hạn chế cập nhật cấu hình trái phép khi một service không cần verb update hoặc patch ra sao?
Bạn giải thích tại sao RBAC đúng vẫn cần bảo vệ secret ở mức log và response ứng dụng như thế nào?
Bạn xác định cách kiểm thử một service không được quyền truy cập resource thuộc namespace khác như thế nào?
Bạn giải thích readinessProbe, livenessProbe và startupProbe kiểm soát vòng đời Pod khác nhau như thế nào?
Bạn phân biệt readiness của ứng dụng với tình trạng một container đang chạy và chưa thoát như thế nào?
Bạn sẽ ánh xạ Spring Boot Actuator health groups vào probe của Kubernetes theo nhu cầu nào?
Bạn thiết kế readiness để Pod không nhận traffic trước khi ứng dụng khởi tạo xong các dependency bắt buộc như thế nào?
Bạn phân tích rủi ro đặt trạng thái của dependency ngoài vào liveness khiến Pod bị restart hàng loạt khi downstream lỗi ra sao?
Bạn xác định khi nào startupProbe cần thiết để một ứng dụng Spring Boot khởi động lâu không bị kill quá sớm như thế nào?
Bạn sẽ chọn initialDelay, period và failure threshold của probe dựa trên thời gian startup thực tế ra sao?
Bạn giải thích vì sao pod readiness false có thể khiến Service tạm thời không còn endpoint khả dụng như thế nào?
Bạn phân biệt lỗi probe HTTP, lỗi ứng dụng và lỗi mạng nội bộ khi Pod bị đánh dấu unready ra sao?
Bạn sẽ thiết kế graceful shutdown để ngừng nhận request mới trước khi container bị dừng hẳn ra sao?
Bạn đánh giá cách terminationGracePeriodSeconds và preStop hook ảnh hưởng các request đang chạy như thế nào?
Bạn sẽ phân tích mối quan hệ giữa readiness false, EndpointSlice cập nhật và client connection reuse khi rolling update ra sao?
Bạn xác định cách tránh HTTP 502 hoặc connection reset trong Deployment rollout như thế nào?
Bạn sẽ kiểm tra OOMKilled, CrashLoopBackOff và ImagePullBackOff như các nhóm sự cố có nguyên nhân khác nhau ra sao?
Bạn phân biệt cấu hình JVM heap với memory limit của container khi theo dõi OOM như thế nào?
Bạn phân tích cách CPU throttling trong container có thể làm tăng latency và probe failure như thế nào?
Bạn sẽ thiết kế resource requests và limits để ứng dụng Spring Boot có đủ CPU và RAM theo tải ra sao?
Bạn đánh giá ảnh hưởng của Horizontal Pod Autoscaler tới số instance được discovery và load balancing như thế nào?
Bạn giải thích vì sao tăng số replica không luôn tăng throughput nếu database hoặc API chung đã nghẽn ra sao?
Bạn sẽ quan sát sự thay đổi membership khi Pod được reschedule sang node khác như thế nào?
Bạn xác định khi nào cần PodDisruptionBudget để tránh nhiều instance bị dừng cùng lúc ra sao?
Bạn sẽ lựa chọn metrics cho autoscaling mà không tạo dao động replica quá mức như thế nào?
Bạn phân tích tại sao chính sách rollout và cấu hình watcher cần phối hợp để tránh thay đổi cấu hình khi ứng dụng chưa ổn định như thế nào?
Bạn mô tả các bước chẩn đoán khi Pod healthy nhưng ứng dụng không thể truy cập Kubernetes API như thế nào?
Bạn sẽ kiểm tra DNS resolution, Service endpoints, NetworkPolicy và RBAC theo trình tự nào khi discovery lỗi ra sao?
Bạn phân biệt lỗi do kube-dns hoặc CoreDNS với lỗi do Spring Cloud DiscoveryClient ra sao?
Bạn sẽ thiết kế metrics về số lần truy vấn API server, tỷ lệ lỗi và thời gian refresh instance list như thế nào?
Bạn đánh giá ảnh hưởng của watch connection bị đứt đến độ mới của discovery cache như thế nào?
Bạn xác định cách giám sát event watcher bị chậm hoặc không nhận được cập nhật ConfigMap ra sao?
Bạn thiết kế log tương quan giữa thay đổi cấu hình, trạng thái refresh và phiên bản deployment như thế nào?
Bạn sẽ giới hạn log để không tiết lộ nội dung Secret hoặc ServiceAccount token ra sao?
Bạn lựa chọn các chỉ số theo service ID và namespace mà không dùng Pod UID làm metric label có cardinality cao như thế nào?
Bạn phân tích ý nghĩa của timeout khi gọi API server so với timeout khi gọi một ứng dụng qua Kubernetes Service như thế nào?
Bạn sẽ đo request latency p95 hoặc p99 trong thời gian Deployment scaling để đánh giá hiệu quả load balancing ra sao?
Bạn xác định cách tìm Pod nào phục vụ một request chậm khi Service có nhiều backend như thế nào?
Bạn sẽ truyền trace context qua HTTP client và service mesh nếu có mà không tạo span trùng lặp như thế nào?
Bạn thiết kế cảnh báo khi Kubernetes Service mất toàn bộ endpoint sẵn sàng trong namespace quan trọng như thế nào?
Bạn đánh giá vì sao warning từ Configuration Watcher không đủ chứng minh cấu hình đã được áp dụng bởi tất cả Pod như thế nào?
Bạn phân biệt lỗi khởi động do thiếu ConfigMap với lỗi runtime do refresh cấu hình sai như thế nào?
Bạn sẽ kiểm tra sự tương thích giữa Spring Cloud Kubernetes và phiên bản Kubernetes API thực tế như thế nào?
Bạn xây dựng checklist deploy bao gồm dependency version, ServiceAccount, RBAC, probes và nguồn cấu hình như thế nào?
Bạn lựa chọn chiến lược rollout canary khi thay đổi cách Spring Cloud Kubernetes discovery hoạt động như thế nào?
Bạn sẽ thiết kế rollback manifest và cấu hình khi một starter mới khiến ứng dụng yêu cầu quyền API không cần thiết ra sao?
Bạn phân tích nhu cầu giữ ứng dụng chạy được khi API server tạm thời không khả dụng nhưng traffic nội bộ vẫn hoạt động như thế nào?
Bạn sẽ tổ chức runbook xử lý lỗi 403 RBAC và lỗi 404 resource để không sửa quyền vượt mức như thế nào?
Bạn thiết kế unit test cho service dùng DiscoveryClient bằng danh sách ServiceInstance giả như thế nào?
Bạn phân biệt unit test với integration test cần Kubernetes cluster thật khi kiểm thử discovery ra sao?
Bạn sẽ viết bài kiểm thử khi Service không có endpoint hoặc namespace sai để xác minh xử lý lỗi như thế nào?
Bạn dùng fake Kubernetes client hoặc test double để kiểm thử việc đọc ConfigMap mà không cần cluster như thế nào?
Bạn thiết kế test kiểm tra property precedence giữa ConfigMap, application.yml và biến môi trường ra sao?
Bạn sẽ kiểm thử validation khi một property từ ConfigMap có kiểu sai hoặc thiếu giá trị bắt buộc như thế nào?
Bạn mô phỏng việc Secret không tồn tại tại startup để kiểm tra fail-fast và thông báo lỗi an toàn như thế nào?
Bạn xây dựng kiểm thử RBAC negative để xác nhận ứng dụng không đọc được resource ngoài phạm vi quyền như thế nào?
Bạn sẽ kiểm thử ServiceAccount với quyền get nhưng không có watch để hiểu hành vi của thành phần cần theo dõi như thế nào?
Bạn phân biệt hành vi Configuration Watcher khi resource thay đổi với hành vi @RefreshScope sau khi nhận tín hiệu như thế nào?
Bạn sẽ kiểm thử ConfigMap cập nhật nhiều lần liên tiếp mà ứng dụng vẫn chỉ áp dụng phiên bản mới nhất như thế nào?
Bạn thiết kế integration test bảo đảm hai Pod nhận thay đổi cấu hình mà không để lộ nội dung Secret ra sao?
Bạn kiểm tra tác động của refresh tới connection pool hoặc HTTP client đang xử lý request như thế nào?
Bạn sẽ thử nghiệm chạy lại Pod khi ConfigMap thay đổi để so sánh với refresh tại runtime ra sao?
Bạn thiết kế test khi watch stream bị đứt và kết nối lại để không bỏ sót cập nhật quan trọng như thế nào?
Bạn sẽ kiểm thử Deployment rolling update với probe readiness và request còn đang chạy ra sao?
Bạn kiểm tra graceful shutdown và drain connection trong môi trường có nhiều replica bằng cách nào?
Bạn thiết kế load test khi Horizontal Pod Autoscaler tăng replica và discovery cache phải cập nhật như thế nào?
Bạn sẽ mô phỏng một Pod mất readiness giữa lúc client đang giữ kết nối để kiểm thử timeout và retry ra sao?
Bạn phân biệt kiểm thử native DNS Service với client-side LoadBalancer trên cùng danh sách endpoint như thế nào?
Bạn xác định các assertion nào chứng minh Spring Cloud LoadBalancer không gửi request tới instance đã loại khỏi danh sách ra sao?
Bạn sẽ kiểm thử ứng dụng không yêu cầu Kubernetes API access khi các tính năng discovery và config API đã tắt như thế nào?
Bạn xây dựng contract test cho cấu hình starter để phát hiện thay đổi hành vi sau nâng cấp Spring Boot và Spring Cloud như thế nào?
Bạn đánh giá khi nào cần chaos test giả lập API server mất kết nối nhưng Service DNS vẫn hoạt động như thế nào?
Bạn sẽ đặt tiêu chí nghiệm thu trước production về phân quyền, config refresh, tính sẵn sàng Pod và latency ra sao?
Nếu DiscoveryClient trả danh sách rỗng nhưng lệnh truy vấn Kubernetes Service trả địa chỉ DNS, bạn sẽ chẩn đoán như thế nào?
Nếu Pod nhận lỗi 403 khi đọc ConfigMap nhưng ứng dụng vẫn gọi Service qua DNS được, bạn sẽ sửa cấu hình quyền ở đâu?
Nếu một Secret mới đã được lưu nhưng ứng dụng vẫn dùng mật khẩu cũ, bạn sẽ xác định phương thức nạp và refresh ra sao?
Nếu Configuration Watcher phát sự kiện nhưng một số Pod không đổi hành vi, bạn sẽ kiểm tra delivery và refresh scope như thế nào?
Nếu ConfigMap đổi timeout và các request đang chạy bị hủy khi refresh, bạn sẽ xây dựng phương án rollout an toàn ra sao?
Nếu nhiều Pod đồng thời refresh làm mất kết nối tới database, bạn sẽ chọn cách giới hạn thay đổi như thế nào?
Nếu Pod bị restart hàng loạt khi database ngoài cluster lỗi, bạn sẽ xem xét lại health probes ra sao?
Nếu ứng dụng có RBAC quyền watch Secrets toàn namespace nhưng chỉ dùng một Secret, bạn sẽ giảm quyền và thay đổi cách tích hợp như thế nào?
Nếu Kubernetes Service routing và client-side LoadBalancer cùng hoạt động gây traffic lệch, bạn sẽ đo lường và đơn giản hóa đường đi ra sao?
Nếu rolling deployment tạo 502 do Pod bị dừng khi request còn chạy, bạn sẽ sửa readiness và graceful shutdown như thế nào?
Nếu API server gặp sự cố nhưng các Pod vẫn healthy, bạn sẽ quyết định giữ discovery cache hay chuyển sang Service DNS ra sao?
Nếu một ConfigMap dùng chung vô tình chứa cấu hình production trong môi trường staging, bạn sẽ thiết kế namespace và quy tắc tên như thế nào?
Nếu cần triển khai một Spring Boot service mới trên Kubernetes, bạn sẽ chọn tính năng Spring Cloud Kubernetes nào thay vì bật tất cả như thế nào?
Nếu phải thiết kế giải pháp Spring Cloud Kubernetes cho nhiều team, bạn sẽ chuẩn hóa RBAC, cấu hình, discovery, probes, kiểm thử và vận hành ra sao?
