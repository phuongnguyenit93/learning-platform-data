Service discovery giải quyết bài toán địa chỉ IP của microservice thay đổi liên tục bằng những cơ chế nào?
Bạn phân biệt gọi một service qua logical service name với gọi trực tiếp hostname và port cố định ra sao?
Bạn mô tả hành trình từ khi một service instance khởi động đến lúc client có thể gửi request cho nó như thế nào?
Bạn so sánh client-side discovery với server-side discovery về nơi thực hiện lựa chọn instance ra sao?
Bạn lựa chọn registry-based discovery hay DNS-based discovery theo quy mô và hạ tầng nào?
Bạn phân biệt vai trò của service registry với API gateway và load balancer như thế nào?
Bạn xác định dữ liệu tối thiểu cần có trong một service registration để client kết nối đúng như thế nào?
Bạn giải thích vì sao registry có thể trả instance còn đăng ký nhưng không còn xử lý request được ra sao?
Bạn thiết kế cách tách định danh dịch vụ với định danh riêng của từng instance như thế nào?
Bạn phân biệt tên service, instance ID và network address trong một hệ thống triển khai nhiều replica ra sao?
Bạn lựa chọn cơ chế khám phá dịch vụ phù hợp khi pod thường xuyên tạo mới và hủy trong Kubernetes ra sao?
Bạn đánh giá trade-off giữa khả năng sẵn sàng và tính cập nhật của danh sách instance khi registry gặp phân vùng mạng như thế nào?
Bạn phân biệt service discovery với configuration management và secret management theo chức năng nào?
Trong những trường hợp nào gọi trực tiếp địa chỉ service là hợp lý hơn sử dụng service registry?
Bạn thiết kế fallback khi danh sách discovery rỗng nhưng dịch vụ đích có thể vẫn đang hoạt động ra sao?
Bạn đánh giá rủi ro registry trở thành phụ thuộc chung của nhiều microservice khi khởi động ra sao?
Bạn so sánh push-based update và pull-based polling của danh sách instances về độ trễ thay đổi như thế nào?
Bạn tổ chức ranh giới giữa discovery client và business service để không phụ thuộc registry cụ thể như thế nào?
Bạn xác định yêu cầu về consistency khi hai clients nhận được danh sách service instances không giống nhau ra sao?
Bạn thiết kế kiến trúc discovery cho hệ thống chạy ở nhiều region với hạn chế cross-region traffic như thế nào?
Bạn lựa chọn định tuyến theo zone hoặc locality khi các instance có độ trễ mạng khác nhau như thế nào?
Bạn đánh giá tác động của việc chọn sai instance theo region tới chi phí và trải nghiệm người dùng ra sao?
Bạn phân biệt instance availability, service readiness và khả năng xử lý nghiệp vụ ở tầng client như thế nào?
Bạn xác định ai chịu trách nhiệm đăng ký và hủy đăng ký instance giữa ứng dụng với orchestrator như thế nào?
Bạn mô tả vai trò của Spring Cloud Commons trong việc trừu tượng hóa service discovery như thế nào?
DiscoveryClient cung cấp những thông tin nào về dịch vụ đã đăng ký và bạn sử dụng chúng ra sao?
Bạn sử dụng DiscoveryClient.getInstances để lấy các ServiceInstance của một logical service name ra sao?
Bạn phân biệt DiscoveryClient.getServices với DiscoveryClient.getInstances trong mục đích sử dụng như thế nào?
Bạn đọc host, port, URI, secure flag và metadata từ ServiceInstance để xây client kết nối như thế nào?
Bạn phân biệt URI của ServiceInstance với địa chỉ dùng cho health check trong một deployment ra sao?
Bạn xử lý kết quả getInstances trả danh sách rỗng mà không giả định đó là lỗi mạng như thế nào?
Bạn thiết kế adapter nhận DiscoveryClient mà không để domain layer phụ thuộc vào Spring Cloud API ra sao?
Bạn so sánh DiscoveryClient đồng bộ với ReactiveDiscoveryClient theo ứng dụng servlet và reactive như thế nào?
Bạn kiểm tra việc dùng synchronous discovery trên Reactor event loop có gây blocking hay không ra sao?
Bạn xác định thứ tự hoặc ưu tiên khi có nhiều DiscoveryClient implementations cùng xuất hiện trong ApplicationContext như thế nào?
Bạn giải thích CompositeDiscoveryClient ảnh hưởng tới việc tìm kiếm instances từ nhiều nguồn như thế nào?
Bạn sử dụng SimpleDiscoveryClient cho môi trường không có registry động theo tình huống nào?
Bạn quản lý danh sách instance cấu hình tĩnh trong SimpleDiscoveryClient theo các profile khác nhau ra sao?
Bạn xác định giới hạn của discovery tĩnh khi autoscaling làm số lượng instances thay đổi liên tục như thế nào?
Bạn kiểm tra auto-configuration nào khiến Spring tạo discovery client cụ thể sau khi thêm starter ra sao?
Bạn phân biệt việc bật discovery client với việc chủ động đăng ký chính ứng dụng vào registry như thế nào?
Trong những tình huống nào bạn sẽ tắt service registration nhưng vẫn giữ khả năng tra cứu service khác?
ServiceRegistry cho phép thực hiện những thao tác nào với đối tượng Registration?
Bạn phân biệt ServiceRegistry.register và ServiceRegistry.deregister với chỉ đọc instance qua DiscoveryClient như thế nào?
Bạn xác định dữ liệu trong Registration cần khớp với service name và instance address như thế nào?
Bạn xử lý ứng dụng có nhiều endpoint hoặc nhiều network interfaces khi tạo Registration ra sao?
Bạn giải thích tác động của service registration auto-start lên vòng đời Spring Boot application như thế nào?
Bạn kiểm soát việc đăng ký instance trước khi các dependency thiết yếu đã sẵn sàng phục vụ ra sao?
Bạn thiết kế custom registration lifecycle mà không làm đăng ký trùng khi application context restart như thế nào?
Bạn kiểm tra sự khác nhau giữa instance metadata lấy từ registry và thông tin bean cấu hình local ra sao?
Bạn thiết kế cơ chế cache danh sách instances ở client và giới hạn độ cũ chấp nhận được như thế nào?
Bạn kiểm thử DiscoveryClient trả về nhiều instances với metadata khác nhau mà không chạy Eureka hoặc Consul thật ra sao?
Bạn giải thích mục đích của Eureka Server trong mô hình service discovery của Spring Cloud như thế nào?
Bạn mô tả các bước Eureka client đăng ký, gửi heartbeat và truy vấn registry sau khi startup ra sao?
Bạn phân biệt tên ứng dụng Eureka với instance ID khi nhiều instances chạy cùng service như thế nào?
Bạn cấu hình Eureka client trỏ đến danh sách service URLs của Eureka Server như thế nào?
Bạn kiểm tra hostname, IP address và port được Eureka client đăng ký khi chạy trong container ra sao?
Bạn xử lý trường hợp Eureka client quảng bá địa chỉ localhost hoặc địa chỉ không route được từ service khác như thế nào?
Bạn xác định khi nào nên dùng secure port và secure instance metadata khi kết nối HTTPS tới service ra sao?
Bạn phân biệt renewal heartbeat interval với lease expiration duration trong Eureka như thế nào?
Vì sao lease Eureka hết hạn chưa bảo đảm client lập tức ngừng chọn instance đã được cache?
Bạn đánh giá tác động của heartbeat interval quá ngắn lên tải Eureka Server ra sao?
Bạn đánh giá tác động của lease expiration quá dài tới thời gian giữ lại instance đã chết trong registry như thế nào?
Bạn giải thích cơ chế Eureka self-preservation và những rủi ro nếu vô hiệu hóa bừa bãi ra sao?
Bạn xác định tín hiệu nào giúp phân biệt Eureka self-preservation với tình trạng server không còn nhận heartbeat như thế nào?
Bạn phân biệt Eureka instance status UP, DOWN và OUT_OF_SERVICE theo mục tiêu đăng ký ra sao?
Bạn đánh giá sự khác nhau giữa Eureka status và Spring Boot Actuator health của một ứng dụng như thế nào?
Bạn cấu hình health check integration để status công bố phản ánh tình trạng ứng dụng theo khả năng phiên bản như thế nào?
Bạn thiết kế readiness của ứng dụng để không nhận traffic khi Eureka đã ghi nhận instance nhưng chưa warm-up xong ra sao?
Bạn kiểm tra Eureka client đang gửi status nào khi một dependency quan trọng trở nên không sẵn sàng như thế nào?
Bạn xác định cách graceful shutdown và deregister giúp giảm request thất bại trong rolling deployment ra sao?
Bạn phân biệt việc Eureka client pull registry theo chu kỳ với server-side lease renewals như thế nào?
Bạn phân tích rủi ro client cache chưa cập nhật khi một instance mới vừa được đăng ký ra sao?
Bạn kiểm soát khoảng trễ sau scale-out trước khi client thực sự chọn instance mới như thế nào?
Bạn mô tả mục đích của Eureka peer replication khi triển khai nhiều Eureka Servers như thế nào?
Bạn đánh giá những sai khác registry giữa các Eureka peers khi có network partition ra sao?
Bạn thiết kế danh sách Eureka endpoints cho client để tránh phụ thuộc duy nhất một node như thế nào?
Bạn kiểm tra một Eureka Server bị cô lập không tiếp tục quảng bá thông tin sai lệch cho clients như thế nào?
Bạn xây dựng chính sách metadata version hoặc zone để hỗ trợ rollout nhiều phiên bản service qua Eureka ra sao?
Khi nào bạn nên thay đổi Eureka instance status thay vì xóa hẳn đăng ký khỏi registry?
Bạn kiểm tra số registered instances, renewals và evictions để phát hiện bất thường ở Eureka ra sao?
Bạn thiết kế test khi Eureka Server restart nhưng service instances vẫn đang chạy như thế nào?
Bạn phân biệt cơ chế Eureka peer replication với consensus strongly consistent của một registry như thế nào?
Bạn tổ chức bảo vệ Eureka endpoints khỏi các clients không có quyền đăng ký hoặc sửa instance ra sao?
Bạn xác định những rủi ro của việc để dashboard Eureka truy cập công khai trên internet như thế nào?
Bạn giải thích Consul cung cấp service catalog và health checking cho service discovery ra sao?
Bạn phân biệt Consul agent, server và client node trong kiến trúc triển khai như thế nào?
Bạn mô tả cách ứng dụng Spring Cloud Consul đăng ký một service instance với local Consul agent như thế nào?
Bạn phân biệt Consul service name và service ID khi một node đăng ký nhiều instances ra sao?
Bạn thiết kế địa chỉ và port của một Consul service registration để client khác có thể kết nối như thế nào?
Bạn cấu hình Spring Cloud Consul discovery theo datacenter và network topology như thế nào?
Bạn giải thích cách Consul health check ảnh hưởng tới danh sách service instances được coi là healthy ra sao?
Bạn phân biệt HTTP health check, TCP check và TTL check của Consul theo yêu cầu nào?
Bạn thiết kế HTTP health check trỏ tới Actuator endpoint phù hợp mà không lộ thông tin nhạy cảm ra sao?
Bạn xác định tần suất Consul health checks sao cho cân bằng tốc độ phát hiện lỗi và overhead như thế nào?
Bạn đánh giá tác động của check timeout quá thấp khi ứng dụng bị GC pause ngắn ra sao?
Bạn sử dụng TTL health check trong trường hợp ứng dụng cần tự báo trạng thái như thế nào?
Bạn thiết kế cơ chế cập nhật TTL pass/fail khi ứng dụng tạm thời không thể xử lý traffic ra sao?
Bạn xử lý service registration còn tồn tại nhưng Consul health check ở trạng thái critical như thế nào?
Bạn phân biệt health status warning với critical khi quyết định client có nên chọn instance hay không ra sao?
Vì sao Consul có thể giữ registration record dù health check của service không đạt?
Bạn cấu hình thời gian tự deregister critical service sau khoảng lỗi kéo dài theo chính sách nào?
Bạn xác định rủi ro tự deregister quá sớm khi toàn bộ service cùng bị dependency outage ra sao?
Bạn so sánh TTL hoặc HTTP checks của Consul với heartbeat lease của Eureka về phát hiện sự cố như thế nào?
Bạn phân biệt catalog query với health-filtered query của Consul khi liệt kê service instances ra sao?
Bạn xử lý kết quả discovery có instance không healthy do nguồn query không lọc theo health như thế nào?
Bạn tổ chức metadata, tags và zone của một Consul service để hỗ trợ routing theo deployment ra sao?
Bạn sử dụng Consul service tags trong discovery mà không đặt credentials hoặc PII vào tags như thế nào?
Bạn phân biệt Consul KV configuration và Consul service discovery để tránh lẫn mục đích ra sao?
Bạn phân tích cơ chế Consul blocking queries và ảnh hưởng của index/caching đến danh sách instances như thế nào?
Bạn chọn phương án Consul client caching khi nhiều service liên tục tra cứu registry theo yêu cầu nào?
Bạn đánh giá tác động của việc Consul quorum không sẵn sàng đến đăng ký và tra cứu service ra sao?
Bạn triển khai Consul servers với fault tolerance và kiểm tra leader election bằng phương pháp nào?
Bạn xác định khi nào Consul multi-datacenter hoặc federation phù hợp cho service discovery ra sao?
Bạn phân biệt Consul ACL token dành cho service registration với token chỉ đọc discovery như thế nào?
Bạn bảo vệ Consul HTTP API bằng TLS, ACL và giới hạn mạng trong production ra sao?
Bạn kiểm thử trạng thái service registration và health sau khi Consul agent restart như thế nào?
Bạn so sánh Consul DNS interface với Spring Cloud DiscoveryClient sử dụng HTTP API về khả năng metadata ra sao?
Bạn lựa chọn Eureka hay Consul dựa trên deployment environment, health checks và mô hình vận hành nào?
Bạn thiết kế chuẩn chung cho instance metadata khi phải hỗ trợ cả Eureka và Consul như thế nào?
Bạn đánh giá rủi ro cấu hình đồng thời hai registries làm ứng dụng đăng ký hai lần hoặc nhận instances trùng ra sao?
Bạn xây dựng phương án chuyển registry từ Eureka sang Consul mà không làm gián đoạn traffic ra sao?
Bạn phân biệt việc khám phá instance với việc đánh giá instance có đủ readiness nhận request như thế nào?
Bạn thiết kế readiness check để loại instance mới khởi động khỏi lựa chọn traffic cho đến khi warm-up xong ra sao?
Bạn lựa chọn liveness checks không phụ thuộc một database chung nhằm tránh restart đồng loạt như thế nào?
Bạn đánh giá ảnh hưởng của việc đưa dependency bên ngoài vào health check được registry dùng ra sao?
Bạn kiểm soát thời điểm service registration được công bố trong startup lifecycle như thế nào?
Bạn xử lý thay đổi status khi application đang thực hiện database migration hoặc tải cache ban đầu như thế nào?
Bạn dùng ApplicationAvailability hoặc health groups của Spring Boot để thể hiện readiness theo tiêu chí nào?
Bạn phân biệt instance không ready và instance đã deregister khi quan sát từ gateway như thế nào?
Bạn thiết kế draining trước shutdown để các request đang xử lý có thể hoàn thành như thế nào?
Bạn xác định khoảng chờ giữa chuyển status khỏi phục vụ và đóng HTTP server để tránh request rơi vào instance cũ ra sao?
Bạn xử lý trường hợp Kubernetes gửi SIGTERM nhưng Eureka hoặc Consul chưa ghi nhận deregistration như thế nào?
Bạn thiết kế cơ chế xóa instance chết bất ngờ khi không có graceful shutdown ra sao?
Bạn phân biệt phát hiện process crash với network partition trong health checks như thế nào?
Bạn đánh giá rủi ro health check endpoint bị overload do nhiều registry agents và load balancers cùng gọi ra sao?
Bạn xác định khi nào nên tách management port khỏi application port và giới hạn của cách kiểm tra đó ra sao?
Bạn kiểm tra registry health status và application readiness có thể sai lệch ở tình huống nào?
Bạn thiết kế trạng thái degraded cho instance còn phục vụ một phần chức năng nhưng không đủ cho một route cụ thể ra sao?
Bạn lựa chọn health criteria nào tác động tới discovery và tiêu chí nào chỉ phục vụ cảnh báo ra sao?
Bạn điều chỉnh health check intervals khi service có startup chậm và traffic tăng đột biến như thế nào?
Bạn ngăn health flapping liên tục thêm hoặc loại instance khỏi danh sách phục vụ như thế nào?
Bạn sử dụng failure threshold và recovery threshold để giảm dao động trong trạng thái instance ra sao?
Bạn thiết kế kiểm thử health check khi downstream timeout, trả lỗi và hồi phục như thế nào?
Bạn phân biệt lỗi health endpoint 401/403 với instance thật sự không khỏe trong cấu hình registry ra sao?
Bạn xác định cách certificate rotation ảnh hưởng tới HTTPS health checks và discovery client như thế nào?
Bạn xây dựng runbook khi tất cả instances của một service cùng chuyển trạng thái unhealthy trong Consul ra sao?
Bạn giải thích Spring Cloud LoadBalancer sử dụng dữ liệu service discovery để chọn instance như thế nào?
Bạn phân biệt chọn service instance ở client với thực thi HTTP request tới địa chỉ instance đã chọn ra sao?
Bạn thiết kế WebClient với cơ chế load balancing dựa trên tên service như thế nào?
Bạn cấu hình RestClient hoặc RestTemplate để gọi logical service name thông qua Spring Cloud LoadBalancer theo phiên bản hỗ trợ ra sao?
Bạn đánh giá ảnh hưởng của cách dùng builder có @LoadBalanced so với client HTTP thông thường như thế nào?
Bạn sử dụng spring-cloud-starter-loadbalancer cùng discovery starter để phân tách trách nhiệm như thế nào?
Bạn phân biệt DiscoveryClient với ServiceInstanceListSupplier trong pipeline lựa chọn instance ra sao?
Bạn xây dựng danh sách instances để LoadBalancer thử nghiệm khi không có Eureka hoặc Consul thật như thế nào?
Bạn so sánh thuật toán round-robin và random theo đặc điểm latency và số request đồng thời như thế nào?
Bạn xác định khi nào round-robin không phù hợp do instances có năng lực phần cứng khác nhau ra sao?
Bạn thiết kế lựa chọn instance theo zone hoặc availability zone để giảm cross-zone traffic như thế nào?
Bạn đánh giá tác động của metadata filtering khi instance có version hoặc capability khác nhau ra sao?
Bạn tổ chức blue-green hoặc canary routing dựa trên service metadata theo các kiểm soát nào?
Bạn phân biệt load balancing ở Spring Cloud với load balancing tại ingress hoặc service mesh ra sao?
Bạn tránh hai tầng retries và load balancing phối hợp gây tăng tải đột biến như thế nào?
Bạn quyết định dùng sticky routing cho session stateful và đánh giá các trade-off nào?
Bạn kiểm tra service name trong URI với scheme lb:// khi Spring Cloud Gateway cần định tuyến ra sao?
Bạn giải thích Spring Cloud Gateway dùng discovery locator khác gì route được khai báo rõ ràng như thế nào?
Bạn thiết kế Gateway route tới service name khi service đổi port hoặc scale replicas ra sao?
Bạn xử lý gateway trả 503 khi danh sách instances rỗng mà registry có thể đang thiếu dữ liệu như thế nào?
Bạn lựa chọn trả fallback status gì khi không còn healthy instance để bảo toàn hợp đồng API như thế nào?
Bạn xác định thời gian cache instances ở LoadBalancer phù hợp với thời gian cập nhật registry như thế nào?
Bạn đánh giá rủi ro caching trùng nhiều tầng giữa discovery client và LoadBalancer như thế nào?
Bạn thiết kế cache invalidation khi một instance mới đăng ký hoặc bị deregister để giảm stale routing ra sao?
Bạn điều tra việc LoadBalancer vẫn gửi traffic tới tập instance cũ dù registry đã có instance mới ra sao?
Bạn tổ chức retry với lựa chọn lại instance khác khi connection refused mà không retry vô hạn như thế nào?
Bạn quyết định request nào có thể retry an toàn khi client không biết downstream đã xử lý hay chưa ra sao?
Bạn thiết kế idempotency key cho POST qua LoadBalancer để hạn chế side effect trùng như thế nào?
Bạn phân biệt connect timeout, response timeout và service selection timeout trong chẩn đoán request chậm ra sao?
Bạn đánh giá việc đọc metadata của ServiceInstance từ registry có đủ tin cậy để quyết định authorization hay không như thế nào?
Bạn kiểm tra LoadBalancer không chọn instance bị đánh dấu không sẵn sàng bằng những bài test nào?
Bạn xây dựng metrics theo selected instance, service name và outcome mà không tạo cardinality quá cao như thế nào?
Bạn phân biệt client-side circuit breaker với loại instance khỏi registry khi một downstream lỗi như thế nào?
Bạn thiết kế bulkhead hoặc concurrency limit cho service name nhằm bảo vệ client khi chỉ còn một instance ra sao?
Bạn xác định khi nào nên chọn HTTP/gRPC service discovery với cơ chế client riêng thay vì áp trực tiếp HTTP LoadBalancer ra sao?
Bạn kiểm tra nhiều application contexts hoặc reactive clients dùng chung registry nhưng có cấu hình LoadBalancer khác nhau như thế nào?
Bạn phân biệt lựa chọn instance thành công với khả năng request bị từ chối bởi rate limiter của instance đích ra sao?
Bạn đánh giá ảnh hưởng của topology multi-region khi client vô tình chọn instance ở region xa như thế nào?
Bạn thiết kế sử dụng metadata phiên bản khi rollout app mới và cũ cùng nằm trong registry như thế nào?
Bạn giới hạn quyền đăng ký tên service để ứng dụng không giả mạo tên của service quan trọng ra sao?
Bạn bảo vệ endpoint Eureka hoặc Consul khỏi registration poisoning và dữ liệu instance metadata giả như thế nào?
Bạn phân biệt authentication tới service registry với mTLS giữa hai service sau khi discovery như thế nào?
Bạn thiết kế token hoặc ACL cho service chỉ được đọc catalog nhưng không sửa registration của service khác như thế nào?
Bạn lựa chọn xác thực ứng dụng thông qua workload identity thay vì lưu password registry trong source code ra sao?
Bạn tổ chức rotation credentials Eureka hoặc Consul mà các client vẫn tiếp tục discovery như thế nào?
Bạn kiểm tra TLS certificate của registry server và tránh tắt hostname verification khi lỗi kết nối ra sao?
Bạn giới hạn truy cập dashboard và management APIs của registry theo phạm vi mạng nào?
Bạn đánh giá tác động của việc lộ service instance metadata như hostname nội bộ, zone và version ra sao?
Bạn tránh đưa API key, access token hoặc PII vào registry metadata và service tags như thế nào?
Bạn thiết kế phân tách registry giữa production và staging để ngăn client phát hiện nhầm instances ra sao?
Bạn kiểm soát service name và namespace để tránh xung đột khi hai team đặt cùng tên dịch vụ ra sao?
Bạn đánh giá rủi ro client chấp nhận HTTP endpoint từ registry không tin cậy gây SSRF hoặc chuyển hướng nội bộ như thế nào?
Bạn giới hạn địa chỉ instance theo network policy hoặc allowed CIDR khi không thể tin tuyệt đối registry ra sao?
Bạn thiết kế mutual TLS giữa gateway và service khi instance IP thay đổi qua discovery như thế nào?
Bạn phân biệt authorization của một request nghiệp vụ với việc được phép tìm thấy service trong registry ra sao?
Bạn kiểm soát secrets của Consul ACL token hoặc Eureka credentials trong logs và traces như thế nào?
Bạn xây dựng audit trail cho ai đăng ký, thay đổi status hoặc deregister một service instance như thế nào?
Bạn thiết kế cơ chế phát hiện một service bất thường đăng ký hàng nghìn instance IDs giả như thế nào?
Bạn kiểm thử client từ môi trường staging không thể truy cập registry production bằng trường hợp nào?
Bạn đánh giá nguy cơ cho registry endpoint public DNS nhưng không có rate limit hoặc access control ra sao?
Bạn xử lý certificate hoặc token hết hạn khiến toàn bộ clients cùng mất khả năng discovery như thế nào?
Bạn phân biệt quyền thay đổi service health check với quyền chỉ xem trạng thái health như thế nào?
Bạn xác định chính sách giữ nhật ký registry đủ để điều tra security incident mà không lưu dữ liệu nhạy cảm ra sao?
Bạn thiết kế high availability cho Eureka hoặc Consul registry theo số node và failure domains nào?
Bạn đánh giá nguy cơ bootstrap circular dependency khi service registry lại phụ thuộc discovery của chính nó như thế nào?
Bạn lựa chọn cách ứng dụng khởi động khi registry chưa sẵn sàng theo yêu cầu fail-fast hay degraded mode như thế nào?
Bạn thiết kế backoff và jitter cho hàng trăm clients đăng ký lại sau khi registry phục hồi ra sao?
Bạn giảm thác lũ traffic khi mọi clients đồng thời refresh toàn bộ registry snapshot như thế nào?
Bạn phân biệt registry outage với một dịch vụ đích outage khi xem error rate của client ra sao?
Bạn xử lý vùng mạng bị partition khi service instances vẫn hoạt động nhưng không thể gửi heartbeat như thế nào?
Bạn xác định khi nào tiếp tục dùng cached instances và thời gian tối đa chấp nhận cache stale ra sao?
Bạn đánh giá tác động của dùng danh sách cũ đối với graceful draining và bảo mật khi instance đã bị thu hồi quyền ra sao?
Bạn thiết kế fallback tới địa chỉ tĩnh chỉ trong trường hợp khẩn cấp và kiểm soát rollback như thế nào?
Bạn đặt SLO cho registry lookup success, lease freshness và time-to-discovery của instance mới ra sao?
Bạn đo thời gian từ instance ready đến khi client đầu tiên có thể chọn nó qua load balancing như thế nào?
Bạn xác định metrics cần có cho registrations, heartbeats, evictions, failing health checks và stale instances ra sao?
Bạn thiết kế alert phát hiện số instances của một logical service giảm đột ngột nhưng traffic không giảm như thế nào?
Bạn phân biệt client registry fetch failure với cache hit vẫn còn dùng được bằng những metrics nào?
Bạn tạo dashboard đối chiếu dữ liệu từ Eureka/Consul với số pods đang running và ready như thế nào?
Bạn dùng Actuator health và metrics để phát hiện registry client không thể kết nối mà business API vẫn trả 200 ra sao?
Bạn kiểm tra sự khác nhau giữa registry instance count và số endpoints thực sự chấp nhận kết nối như thế nào?
Bạn truyền trace context qua HTTP clients được load balanced mà không làm lộ instance metadata ra sao?
Bạn thiết kế log cho quyết định chọn service instance mà không tạo overhead quá lớn khi traffic cao như thế nào?
Bạn phân tích request 5xx tăng sau scale-down bằng timeline deregistration và client cache như thế nào?
Bạn kiểm tra DNS resolution, proxy và firewall khi registry được truy cập nhưng service đích không kết nối được ra sao?
Bạn xác định readiness của service registry có nên phụ thuộc toàn bộ member nodes trong cluster như thế nào?
Bạn đánh giá registry network latency cao ảnh hưởng trực tiếp đến request path hay chỉ ảnh hưởng refresh cache theo cấu hình nào?
Bạn thiết kế chaos test ngắt một registry node nhưng vẫn giữ phần còn lại phục vụ clients như thế nào?
Bạn kiểm tra backup hoặc snapshot của Consul khi phải phục hồi cluster sau sự cố lớn ra sao?
Bạn phân biệt nhu cầu lưu trạng thái của Consul với registry cache của Eureka khi lập kế hoạch disaster recovery như thế nào?
Bạn tổ chức multi-datacenter service discovery mà không để client liên tục gọi cross-region instance ra sao?
Bạn xử lý discrepancy khi hai zones thấy danh sách service instances khác nhau trong thời gian dài như thế nào?
Bạn quản lý capacity registry khi số service instances tăng từ vài trăm lên vài chục nghìn ra sao?
Bạn đánh giá memory footprint và bandwidth do cache toàn bộ registry ở nhiều clients như thế nào?
Bạn lựa chọn chính sách retention của metrics và logs để tái dựng sự cố discovery xảy ra nhiều giờ trước như thế nào?
Bạn xây dựng runbook khôi phục khi nhiều clients đồng thời nhận danh sách instances rỗng dù service vẫn chạy như thế nào?
Bạn viết unit test cho adapter dùng DiscoveryClient trả nhiều ServiceInstance với metadata khác nhau như thế nào?
Bạn kiểm thử một client không crash khi DiscoveryClient trả danh sách rỗng hoặc ném exception ra sao?
Bạn tạo fake ServiceInstanceListSupplier để kiểm tra thuật toán lựa chọn instance của Spring Cloud LoadBalancer như thế nào?
Bạn sử dụng @SpringBootTest hoặc slice test để xác minh discovery auto-configuration tạo đúng bean theo profile như thế nào?
Bạn kiểm thử tắt auto registration nhưng vẫn đọc discovery được theo cấu hình nào?
Bạn chọn Testcontainers chạy Consul cho integration tests registration và health checking như thế nào?
Bạn kiểm tra health check Consul nhận trạng thái fail khi Actuator readiness chuyển DOWN ra sao?
Bạn mô phỏng Consul agent restart để xác minh service xuất hiện lại trong healthy catalog như thế nào?
Bạn xây dựng integration test với Eureka test server hoặc môi trường cô lập để quan sát registration lifecycle như thế nào?
Bạn kiểm tra heartbeat bị ngắt dẫn tới trạng thái registry thay đổi sau các khoảng thời gian cấu hình như thế nào?
Bạn tránh test thời gian lease phụ thuộc Thread.sleep dài gây flaky CI bằng phương pháp nào?
Bạn xác minh graceful shutdown thực sự deregister và ngừng nhận request theo bước nào?
Bạn kiểm thử client cache còn giữ stale instance khi provider discovery đã cập nhật dữ liệu như thế nào?
Bạn mô phỏng instance trả connection refused và kiểm tra LoadBalancer retry chọn lại instance như thế nào?
Bạn xác minh retry không tạo side effect trùng cho POST chưa có idempotency key ra sao?
Bạn dùng WebTestClient hoặc mock HTTP upstream để kiểm thử WebClient gọi service name qua LoadBalancer như thế nào?
Bạn kiểm thử route lb:// của Spring Cloud Gateway với danh sách instances thay đổi ra sao?
Bạn xác minh version metadata filtering không chọn instance không hỗ trợ contract của client như thế nào?
Bạn xây dựng test service discovery chạy ở nhiều zones và đánh giá ưu tiên local zone ra sao?
Bạn kiểm thử mTLS và TLS certificate validation khi registry hoặc service sử dụng HTTPS như thế nào?
Bạn thiết kế negative tests chứng minh workload chỉ đọc không thể đăng ký instance giả lên Consul ra sao?
Bạn kiểm tra registry ACL hoặc credentials không được vô tình đưa vào test reports như thế nào?
Bạn mô phỏng registry tạm không khả dụng khi client startup để kiểm tra fail-fast hoặc fallback như thế nào?
Bạn kiểm tra client tiếp tục phục vụ bằng cached instances trong giới hạn cho phép khi registry mất kết nối ra sao?
Bạn xây dựng load test để đo registry lookup load và stale cache khi nhiều pods đồng thời scale ra sao?
Bạn xác minh status UP của Actuator không che giấu khả năng gọi downstream service đã thất bại như thế nào?
Bạn phân biệt unit test logic chọn instance với end-to-end test qua Eureka hoặc Consul thực như thế nào?
Bạn thiết kế test bảo đảm chỉ instances thuộc đúng namespace hoặc environment được đưa vào danh sách routing ra sao?
Bạn quyết định chạy registry chaos tests định kỳ thay vì trong mọi pull request dựa trên những tiêu chí nào?
Bạn xác định tiêu chí pass/fail cho một thay đổi cấu hình lease, cache TTL hoặc health interval như thế nào?
Nếu service đăng ký thành công nhưng client không tìm thấy tên dịch vụ, bạn sẽ kiểm tra service ID và registry cache ra sao?
Nếu Eureka client quảng bá localhost trong container, bạn sẽ sửa registration address và kiểm thử kết nối như thế nào?
Nếu một instance chết nhưng tiếp tục được chọn trong nhiều phút, bạn sẽ kiểm tra lease, cache và load balancer ra sao?
Nếu Eureka self-preservation giữ nhiều instance không còn sống, bạn sẽ phục hồi mà không tắt toàn bộ cơ chế bảo vệ như thế nào?
Nếu Eureka peers có danh sách khác nhau sau network partition, bạn sẽ kiểm chứng propagation và khả năng hồi phục ra sao?
Nếu Consul cho thấy service đã đăng ký nhưng health critical, bạn sẽ điều tra Actuator endpoint và check timeout như thế nào?
Nếu Consul health check trả 401 do nâng cấp security, bạn sẽ điều chỉnh authentication và policy như thế nào?
Nếu Consul agent bị restart rồi service biến mất khỏi healthy catalog, bạn sẽ kiểm tra re-registration lifecycle ra sao?
Nếu Spring Cloud Gateway trả 503 cho lb://orders dù service có pods ready, bạn sẽ tìm lỗi discovery hay LoadBalancer như thế nào?
Nếu request 5xx tăng trong rolling deployment, bạn sẽ kiểm tra draining, TTL và deregistration timing ra sao?
Nếu hệ thống nhận traffic cross-region sau một lần scale-out, bạn sẽ điều tra metadata zone và selection policy như thế nào?
Nếu danh sách instance trong client bị cache quá lâu sau scale-down, bạn sẽ giảm stale routing mà không tăng tải registry ra sao?
Nếu client-side retry khiến một POST được thực thi hai lần, bạn sẽ đặt retry boundary và idempotency như thế nào?
Nếu service metadata bị một workload giả mạo để nhận traffic nhạy cảm, bạn sẽ gia cố identity và registry authorization ra sao?
Nếu Consul cluster mất quorum nhưng một số apps vẫn chạy, bạn sẽ quyết định dùng cache hay fail-fast ra sao?
Nếu Eureka Server outage khiến hàng nghìn clients đăng ký lại cùng lúc, bạn sẽ cấu hình backoff và capacity ra sao?
Nếu nhiều pod cùng bị health flapping vì database chung gián đoạn, bạn sẽ tách liveness và readiness như thế nào?
Nếu client phát hiện instance nhưng không kết nối được do mTLS certificate lỗi, bạn sẽ tách lỗi TLS khỏi lỗi discovery ra sao?
Nếu Eureka và Consul cùng được bật dẫn tới trùng service instance, bạn sẽ xác định discovery source và giải quyết ra sao?
Nếu chuyển từ Eureka sang Consul khiến metadata của instance đổi cấu trúc, bạn sẽ bảo vệ logic routing như thế nào?
Nếu hai versions service cùng đăng ký tên orders nhưng API contract không tương thích, bạn sẽ điều phối rollout và routing ra sao?
Nếu danh sách service từ registry bị thiếu một zone dù zone đó vẫn có pods, bạn sẽ phân biệt lỗi network với health như thế nào?
Nếu service nhầm môi trường staging được đăng ký vào production registry, bạn sẽ chặn traffic và sửa namespace như thế nào?
Nếu client tiếp tục dùng registry cache sau khi một instance bị thu hồi quyền truy cập, bạn sẽ xử lý an toàn như thế nào?
Nếu metrics báo registration count bình thường nhưng requests đều timeout, bạn sẽ kiểm tra port và network path ra sao?
Nếu một service có CPU cao làm health checks timeout, bạn sẽ giảm flapping nhưng vẫn phát hiện overload như thế nào?
Nếu một Consul ACL token bị rò rỉ và kẻ tấn công đăng ký instance giả, bạn sẽ điều tra và khôi phục trust ra sao?
Nếu service discovery chỉ lỗi trên WebFlux nhưng hoạt động trên Spring MVC, bạn sẽ kiểm tra reactive client và blocking calls như thế nào?
Nếu số instance tăng gấp mười làm Eureka fetch và Consul queries chậm, bạn sẽ tối ưu caching và refresh ra sao?
Bạn xây dựng runbook khôi phục khi Eureka hoặc Consul bị partition, nhiều instances stale và Gateway liên tục trả 503 như thế nào?
