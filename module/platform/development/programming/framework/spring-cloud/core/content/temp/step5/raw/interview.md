Bạn giải thích Spring Cloud bổ sung những năng lực gì cho ứng dụng Spring Boot trong môi trường phân tán?
Bạn phân biệt trách nhiệm của Spring Boot và Spring Cloud trong một hệ thống nhiều service như thế nào?
Bạn sẽ xác định khi nào một ứng dụng cần Spring Cloud thay vì chỉ sử dụng Spring Boot ra sao?
Bạn mô tả các vấn đề mà các abstraction chung của Spring Cloud giúp giảm phụ thuộc vào nhà cung cấp như thế nào?
Bạn phân tích những giới hạn của Spring Cloud khi hệ thống vẫn phải xử lý lỗi mạng và nhất quán dữ liệu như thế nào?
Bạn sẽ thiết kế ranh giới giữa logic nghiệp vụ và cơ chế hạ tầng do Spring Cloud cung cấp ra sao?
Bạn phân biệt mô hình nhiều service với một ứng dụng đơn khối về nhu cầu cấu hình và giao tiếp như thế nào?
Bạn giải thích vì sao discovery và cấu hình ngoài trở nên quan trọng khi số instance thay đổi liên tục như thế nào?
Bạn lựa chọn những thành phần Spring Cloud nào cần dùng trong một dịch vụ chỉ xử lý tác vụ nền ra sao?
Bạn sẽ đánh giá chi phí vận hành khi đưa một hệ sinh thái Spring Cloud vào dự án nhỏ như thế nào?
Bạn phân biệt abstraction ở tầng ứng dụng với công nghệ triển khai hạ tầng cụ thể trong Spring Cloud như thế nào?
Bạn xác định các thành phần nào nên dùng chung quy ước giữa nhiều microservice để thuận tiện vận hành ra sao?
Bạn giải thích ý nghĩa của Spring Cloud Commons đối với các implementation discovery và load balancing khác nhau như thế nào?
Bạn phân biệt Spring Cloud Commons với Spring Cloud Context theo phạm vi chức năng ra sao?
Bạn sẽ mô tả vai trò của Spring Cloud Context đối với cấu hình và vòng đời ApplicationContext như thế nào?
Bạn giải thích vì sao Spring Cloud không tự bảo đảm khả năng chịu lỗi nếu thiếu chính sách timeout và kiểm soát tải ra sao?
Bạn xác định những trách nhiệm về security và phân quyền vẫn thuộc ứng dụng dù đã có Spring Cloud như thế nào?
Bạn sẽ tổ chức package và các lớp adapter để thay nhà cung cấp discovery mà không sửa logic nghiệp vụ ra sao?
Bạn đánh giá tác động của một thư viện Spring Cloud lên classpath và khả năng auto-configuration như thế nào?
Bạn sẽ trình bày quy trình khởi tạo một service Spring Boot có sử dụng abstraction của Spring Cloud ra sao?
Bạn giải thích Spring Cloud release train giúp quản lý khả năng tương thích giữa các dự án thành phần như thế nào?
Bạn phân biệt phiên bản Spring Cloud release train với phiên bản riêng của từng module như thế nào?
Bạn sẽ lựa chọn phiên bản Spring Cloud phù hợp với phiên bản Spring Boot hiện có theo nguồn thông tin nào?
Bạn phân tích rủi ro khi kết hợp một phiên bản Spring Cloud không tương thích với Spring Boot ra sao?
Bạn giải thích vai trò của BOM trong quản lý dependency của các thư viện Spring Cloud như thế nào?
Bạn phân biệt việc import Spring Cloud BOM với cách khai báo phiên bản trực tiếp từng dependency ra sao?
Bạn sẽ kiểm tra dependency tree khi hai starter kéo theo phiên bản khác nhau của cùng một thư viện như thế nào?
Bạn xác định cách phát hiện xung đột Spring Framework hoặc Reactor do quản lý phiên bản không thống nhất ra sao?
Bạn sẽ thiết kế ma trận tương thích JDK, Spring Boot và Spring Cloud trước khi nâng cấp hệ thống như thế nào?
Bạn phân tích thay đổi về auto-configuration và cấu hình bootstrap có thể ảnh hưởng quá trình nâng cấp ra sao?
Bạn sẽ xây dựng bộ smoke test để phát hiện một service không thể khởi động sau khi đổi release train như thế nào?
Bạn phân biệt lỗi do API bị loại bỏ với lỗi do điều kiện auto-configuration thay đổi sau nâng cấp ra sao?
Bạn xác định khi nào cần nâng cấp đồng thời nhiều service và khi nào có thể rollout độc lập ra sao?
Bạn sẽ kiểm thử khả năng tương tác giữa các service đang dùng hai phiên bản Spring Cloud khác nhau như thế nào?
Bạn đánh giá rủi ro nâng cấp client discovery trong khi registry server vẫn dùng phiên bản cũ ra sao?
Bạn sẽ chuẩn bị rollback khi một phiên bản mới làm thay đổi cách tải configuration properties ra sao?
Bạn giải thích cơ chế kiểm tra tương thích phiên bản được kích hoạt khi Spring Cloud chạy cùng Spring Boot như thế nào?
Bạn sẽ chẩn đoán một lỗi khởi động liên quan đến compatibility verifier bằng những bước nào?
Bạn phân tích vì sao tắt compatibility check không thể thay thế kiểm thử tương thích thực tế như thế nào?
Bạn xác định khi nào cần loại bỏ một dependency Spring Cloud không còn sử dụng để giảm rủi ro nâng cấp ra sao?
Bạn sẽ tạo quy ước pin phiên bản và cập nhật dependency trong CI để tránh drift như thế nào?
Bạn phân biệt dependency cần để compile API Commons với starter triển khai một registry cụ thể như thế nào?
Bạn giải thích externalized configuration giúp cùng một artifact chạy trong nhiều môi trường như thế nào?
Bạn phân biệt Environment và PropertySource khi Spring Cloud bổ sung nguồn cấu hình bên ngoài ra sao?
Bạn sẽ tổ chức các nhóm cấu hình chung, cấu hình từng service và cấu hình từng môi trường như thế nào?
Bạn phân tích thứ tự ưu tiên property giữa file ứng dụng, biến môi trường và nguồn cấu hình từ xa ra sao?
Bạn xác định bằng cách nào một property bị ghi đè khi xuất hiện trong nhiều PropertySource như thế nào?
Bạn sẽ phân biệt application name, active profiles và label trong việc xác định cấu hình từ nguồn bên ngoài ra sao?
Bạn giải thích vai trò của spring.application.name trong nhận diện service và cấu hình phân tán như thế nào?
Bạn lựa chọn cách đặt tên service để tránh xung đột giữa các môi trường và vùng triển khai ra sao?
Bạn mô tả sự khác biệt giữa cấu hình được tải lúc khởi động và cấu hình được làm mới khi ứng dụng đang chạy ra sao?
Bạn sẽ xác định loại cấu hình nào có thể refresh và loại nào chỉ nên thay đổi bằng redeploy ra sao?
Bạn đánh giá nguy cơ sử dụng một nguồn cấu hình chung làm điểm lỗi tập trung cho nhiều service ra sao?
Bạn sẽ xây dựng chính sách mặc định khi kho cấu hình ngoài tạm thời không khả dụng lúc khởi động như thế nào?
Bạn phân biệt chiến lược fail-fast với cho phép chạy bằng cấu hình dự phòng khi nguồn từ xa lỗi ra sao?
Bạn sẽ thiết kế retry có giới hạn cho việc tải cấu hình trong giai đoạn startup ra sao?
Bạn xác định khi nào một cấu hình quan trọng thiếu giá trị phải khiến service từ chối khởi động như thế nào?
Bạn phân tích việc một cấu hình ngoài thay đổi nhưng application instance chưa nhận được cập nhật sẽ gây hậu quả gì?
Bạn giải thích cơ chế Spring Boot Config Data import liên quan tới việc nạp cấu hình bên ngoài như thế nào?
Bạn sẽ sử dụng spring.config.import để khai báo nguồn cấu hình từ xa theo nguyên tắc nào?
Bạn phân biệt import bắt buộc với import optional khi một nguồn cấu hình không sẵn sàng ra sao?
Bạn phân tích vì sao thứ tự tải cấu hình qua Config Data cần được kiểm tra trong quá trình nâng cấp như thế nào?
Bạn mô tả mục đích của bootstrap context trong mô hình Spring Cloud trước đây như thế nào?
Bạn phân biệt bootstrap context với application context chính về vòng đời và nhiệm vụ ra sao?
Bạn giải thích vì sao không nên giả định bootstrap.yml luôn được kích hoạt ở mọi phiên bản Spring Cloud như thế nào?
Bạn sẽ quyết định khi nào sử dụng cơ chế bootstrap tương thích cũ và khi nào chuyển sang Config Data ra sao?
Bạn xác định cách đưa thông tin truy cập kho cấu hình vào môi trường mà không ghi cứng secret trong repository như thế nào?
Bạn phân tích tác động của profile kích hoạt muộn lên lựa chọn property từ các nguồn cấu hình khác nhau ra sao?
Bạn sẽ chẩn đoán một property remote bị override bởi biến môi trường không mong muốn như thế nào?
Bạn phân biệt property placeholder resolution với binding vào bean @ConfigurationProperties ra sao?
Bạn sẽ dùng validation để chặn cấu hình endpoint hoặc timeout không hợp lệ trước khi service nhận traffic như thế nào?
Bạn đánh giá nên lưu cấu hình nhạy cảm ở kho bí mật chuyên dụng hay kho cấu hình thông thường theo điều kiện nào?
Bạn sẽ thiết kế lịch sử thay đổi và truy vết phiên bản cho cấu hình áp dụng lên nhiều instance như thế nào?
Bạn giải thích vai trò của RefreshScope trong việc cập nhật bean khi cấu hình thay đổi như thế nào?
Bạn phân biệt @RefreshScope với @Scope singleton của Spring khi xét đến vòng đời bean ra sao?
Bạn sẽ mô tả cơ chế proxy và tái tạo target bean được đánh dấu @RefreshScope như thế nào?
Bạn phân tích vì sao thay đổi một property trong kho cấu hình không tự bảo đảm mọi bean lập tức nhận giá trị mới như thế nào?
Bạn sẽ xác định điểm kích hoạt refresh và cách cấu hình mới được đưa vào Environment ra sao?
Bạn giải thích vai trò của ContextRefresher trong quá trình cập nhật property và scope bean như thế nào?
Bạn phân biệt ContextRefresher với việc khởi động lại toàn bộ ApplicationContext như thế nào?
Bạn sẽ phân tích sự khác biệt giữa refresh environment và tái tạo target bean của @RefreshScope ra sao?
Bạn xác định những bean nào không nên refresh giữa chừng do đang quản lý transaction hoặc tài nguyên có trạng thái như thế nào?
Bạn sẽ thiết kế thay đổi cấu hình timeout của HTTP client mà không làm hỏng request đang xử lý ra sao?
Bạn đánh giá rủi ro khi một nhóm bean phụ thuộc nhận cấu hình ở các thời điểm khác nhau như thế nào?
Bạn sẽ kiểm soát trạng thái nhất quán trong quá trình nhiều instance của một service refresh không đồng thời như thế nào?
Bạn phân biệt làm mới @ConfigurationProperties với tạo lại một bean nằm trong refresh scope như thế nào?
Bạn giải thích khi nào một giá trị cấu hình bị xóa khỏi nguồn ngoài nhưng chưa được phản ánh như mong muốn ở runtime như thế nào?
Bạn sẽ kiểm tra thuộc tính không thay đổi sau refresh do bean cache hoặc giá trị được đọc tại constructor ra sao?
Bạn đánh giá ảnh hưởng của refresh đến thread safety và dependency lifecycle như thế nào?
Bạn sẽ xác định cách bảo vệ endpoint quản trị refresh nếu ứng dụng có cho phép gọi qua HTTP ra sao?
Bạn phân tích vì sao không nên mở công khai actuator refresh hoặc các endpoint làm thay đổi trạng thái cấu hình như thế nào?
Bạn sẽ chọn giữa refresh đồng bộ, thông báo sự kiện và rolling restart theo mức độ rủi ro thay đổi cấu hình như thế nào?
Bạn phân biệt refresh được kích hoạt thủ công với cơ chế lan truyền thông báo refresh qua nhiều instance ra sao?
Bạn sẽ kiểm tra cấu hình mới áp dụng thành công bằng metric, log và kiểm tra hành vi nghiệp vụ như thế nào?
Bạn giải thích cách refresh event có thể ảnh hưởng các thành phần đang giữ bản sao cấu hình trong cache như thế nào?
Bạn sẽ lập kế hoạch rollback khi cấu hình mới được refresh khiến một nhóm instance xử lý lỗi ra sao?
Bạn phân tích tại sao thay đổi connection pool hoặc security policy có thể cần restart thay vì refresh ra sao?
Bạn sẽ đo thời gian và tác động bộ nhớ khi refresh một bean tạo connection hoặc thread pool như thế nào?
Bạn xác định khi nào refresh scope gây ra hành vi bất ngờ trong ứng dụng Spring AOT hoặc native image như thế nào?
Bạn sẽ thiết kế test xác nhận bean nhận property mới mà không tạo ra nhiều connection bị rò rỉ ra sao?
Bạn phân biệt cấu hình tĩnh do build quyết định với cấu hình runtime cần được kiểm soát theo môi trường như thế nào?
Bạn giải thích service discovery giúp client tìm instance của dịch vụ phụ thuộc trong môi trường động như thế nào?
Bạn phân biệt service registry với DiscoveryClient về vai trò lưu trữ và truy vấn instance ra sao?
Bạn mô tả các abstraction chung trong Spring Cloud Commons để lấy danh sách ServiceInstance như thế nào?
Bạn giải thích DiscoveryClient cung cấp thông tin gì khi được yêu cầu tìm một service ID ra sao?
Bạn phân biệt service ID với host và port vật lý của một instance như thế nào?
Bạn phân tích rủi ro khi ứng dụng lưu cứng địa chỉ của một instance thay vì dùng discovery ra sao?
Bạn sẽ lựa chọn registry động hay danh sách instance tĩnh theo đặc điểm môi trường triển khai như thế nào?
Bạn giải thích SimpleDiscoveryClient có thể hỗ trợ những trường hợp discovery đơn giản như thế nào?
Bạn xác định cách cấu hình nhiều instance tĩnh để thử nghiệm không cần registry thật ra sao?
Bạn phân biệt DiscoveryClient đồng bộ với ReactiveDiscoveryClient trong code reactive như thế nào?
Bạn sẽ quyết định khi nào sử dụng API reactive để tránh blocking event loop trong đường gọi discovery ra sao?
Bạn mô tả thông tin về URI, scheme, service ID và metadata từ một ServiceInstance như thế nào?
Bạn xác định tiêu chí chọn một instance dựa trên metadata vùng triển khai hoặc phiên bản ứng dụng như thế nào?
Bạn sẽ kiểm tra metadata của registry có đáng tin cậy trước khi dùng định tuyến hay quyết định bảo mật ra sao?
Bạn phân tích ý nghĩa của thứ tự ưu tiên khi có nhiều DiscoveryClient cùng tồn tại như thế nào?
Bạn phân biệt CompositeDiscoveryClient với một DiscoveryClient triển khai bởi registry cụ thể như thế nào?
Bạn sẽ chẩn đoán trường hợp service có tên đúng nhưng DiscoveryClient trả danh sách instance rỗng như thế nào?
Bạn giải thích cơ chế đăng ký và hủy đăng ký instance ảnh hưởng đến khả năng tìm thấy dịch vụ như thế nào?
Bạn sẽ nhận diện instance bị stale trong registry nhưng thực tế không còn phục vụ traffic ra sao?
Bạn phân tích ảnh hưởng của TTL hoặc heartbeat chậm tới danh sách instance được khám phá như thế nào?
Bạn xác định khi nào nên dùng discovery cache và thời gian sống của cache để cân bằng hiệu năng và độ mới ra sao?
Bạn sẽ xử lý trường hợp registry tạm thời không sẵn sàng nhưng client đã có danh sách instance trước đó như thế nào?
Bạn phân biệt instance healthy theo registry với instance thực sự đáp ứng request nghiệp vụ như thế nào?
Bạn sẽ thiết kế kiểm tra readiness để giảm nguy cơ định tuyến tới instance vừa khởi động chưa sẵn sàng ra sao?
Bạn giải thích tại sao service discovery không tự bảo đảm cân bằng tải hoặc khôi phục kết nối thất bại như thế nào?
Bạn sẽ chọn cách test discovery khi số instance tăng, giảm hoặc thay đổi địa chỉ liên tục ra sao?
Bạn phân tích nguy cơ discovery bị chậm làm tăng latency trước cả khi client gửi HTTP request ra sao?
Bạn sẽ thiết kế cách tách danh tính logic của dịch vụ khỏi tên host trong cấu hình client ra sao?
Bạn giải thích ServiceRegistry abstraction khác DiscoveryClient về trách nhiệm như thế nào?
Bạn mô tả trách nhiệm của Registration khi đăng ký một instance vào service registry ra sao?
Bạn sẽ xác định những thông tin nào về instance cần công bố trong Registration như thế nào?
Bạn phân biệt hành vi register và deregister của ServiceRegistry trong vòng đời service ra sao?
Bạn phân tích vì sao đăng ký thành công chưa đồng nghĩa instance đã sẵn sàng nhận traffic như thế nào?
Bạn xác định điều kiện đăng ký service sau khi các dependency bắt buộc đã sẵn sàng như thế nào?
Bạn sẽ tổ chức xử lý sự kiện ứng dụng sẵn sàng và dừng để cập nhật trạng thái đăng ký ra sao?
Bạn giải thích mục đích của service auto-registration trong Spring Cloud như thế nào?
Bạn sẽ quyết định khi nào cần vô hiệu hóa auto-registration cho worker hoặc tác vụ thử nghiệm ra sao?
Bạn phân tích rủi ro khi ứng dụng đăng ký nhầm vào registry production do cấu hình môi trường như thế nào?
Bạn sẽ xử lý tình huống tên service được đăng ký khác tên mà client sử dụng để discovery ra sao?
Bạn xác định cách bảo vệ credential khi service đăng ký vào registry bên ngoài như thế nào?
Bạn đánh giá hành vi khi nhiều instance có cùng service ID nhưng khác version và zone như thế nào?
Bạn sẽ định nghĩa metadata cần thiết cho routing mà không nhét thông tin nhạy cảm vào registry ra sao?
Bạn giải thích vì sao một instance bị kill đột ngột có thể chưa được xóa khỏi registry ngay lập tức như thế nào?
Bạn sẽ thiết kế shutdown có kiểm soát để ngừng nhận traffic trước khi unregister instance ra sao?
Bạn phân biệt health check được registry hỗ trợ với health indicator của Spring Boot Actuator như thế nào?
Bạn đánh giá nguy cơ phụ thuộc tuyệt đối vào registry khi một service cần bootstrap trong hệ thống đang lỗi như thế nào?
Bạn giải thích mục tiêu của client-side load balancing khi có nhiều instance cùng một service ID như thế nào?
Bạn phân biệt client-side load balancing với server-side load balancing ở nơi ra quyết định chọn instance ra sao?
Bạn mô tả cách Spring Cloud LoadBalancer phối hợp với DiscoveryClient để chọn ServiceInstance như thế nào?
Bạn giải thích vai trò của ReactorLoadBalancer trong quá trình chọn instance như thế nào?
Bạn sẽ lựa chọn chính sách RoundRobin hay Random khi phân phối request giữa các instance ra sao?
Bạn đánh giá tác động của instance có năng lực khác nhau đối với một chiến lược cân bằng tải đơn giản như thế nào?
Bạn sẽ thiết kế cơ chế ưu tiên instance cùng zone mà vẫn có fallback khi zone không đủ năng lực ra sao?
Bạn xác định khi nào nên áp dụng bộ lọc theo metadata trước khi chọn instance như thế nào?
Bạn phân tích rủi ro dùng metadata không đồng nhất giữa instance làm phân phối traffic sai ra sao?
Bạn phân biệt việc chọn instance mới cho mỗi request với việc tái sử dụng kết nối HTTP tới một instance đã chọn ra sao?
Bạn sẽ chẩn đoán một service ID có nhiều instance nhưng traffic chỉ tới một địa chỉ ra sao?
Bạn giải thích cách gắn @LoadBalanced vào HTTP client builder thay đổi cách xử lý service-name URI ra sao?
Bạn phân biệt RestTemplate, RestClient và WebClient khi sử dụng Spring Cloud LoadBalancer như thế nào?
Bạn sẽ thiết kế cấu hình một RestClient.Builder có hỗ trợ load balancing mà không làm ảnh hưởng các client gọi URL trực tiếp ra sao?
Bạn mô tả cách một WebClient được cấu hình load-balanced truy cập endpoint qua service ID ra sao?
Bạn phân biệt sử dụng WebClient reactive với gọi blocking RestTemplate trong các workload cụ thể ra sao?
Bạn sẽ xác định ranh giới timeout và retry của một HTTP client đang chọn instance qua load balancer như thế nào?
Bạn đánh giá nguy cơ retry trên instance khác làm lặp một yêu cầu ghi dữ liệu ra sao?
Bạn sẽ thiết kế idempotency cho request có thể được gửi lại sau lỗi mạng khi load balancing ra sao?
Bạn phân biệt lỗi không tìm được instance với lỗi instance trả HTTP 503 theo cách xử lý của caller như thế nào?
Bạn xác định phản hồi phù hợp khi danh sách instance rỗng dù registry vẫn có thể truy cập như thế nào?
Bạn giải thích vai trò của cache instance trong giảm áp lực lên discovery backend như thế nào?
Bạn sẽ kiểm soát thời gian cache để instance đã bị gỡ khỏi registry không tiếp tục nhận request quá lâu ra sao?
Bạn mô tả cách ghi metric phân phối request theo service ID mà không tạo tag có cardinality quá cao ra sao?
Bạn sẽ lựa chọn kiểm thử cân bằng tải có thể tái lập kết quả thay vì dựa vào lịch thực thi ngẫu nhiên như thế nào?
Bạn đánh giá ảnh hưởng của timeout kết nối và keep-alive khi instance được scale down ra sao?
Bạn sẽ thiết kế graceful drain để giảm lỗi kết nối trong lúc rolling deployment ra sao?
Bạn giải thích tại sao việc cân bằng tải tốt không đồng nghĩa với khả năng chịu lỗi nếu thiếu timeout và cơ chế bảo vệ ra sao?
Bạn phân biệt lỗi discovery, lỗi load balancing và lỗi trong logic nghiệp vụ bằng dấu hiệu nào?
Bạn sẽ xây dựng adapter cho giao tiếp service-to-service để không lộ chi tiết registry vào tầng nghiệp vụ ra sao?
Bạn mô tả tiêu chí lựa chọn giao tiếp HTTP đồng bộ hay messaging bất đồng bộ giữa hai service như thế nào?
Bạn đánh giá khi nào dùng tên service logic có lợi hơn việc cấu hình URL đầy đủ ra sao?
Bạn sẽ quyết định nơi áp dụng retry, timeout và circuit breaker trong một chuỗi gọi service như thế nào?
Bạn phân tích vì sao retry ở nhiều tầng có thể nhân số request gây quá tải dependency ra sao?
Bạn phân biệt việc fallback bằng cache với việc trả kết quả thành công giả khi dependency không khả dụng như thế nào?
Bạn sẽ thiết kế giới hạn số lời gọi đồng thời để một service downstream chậm không làm cạn tài nguyên upstream ra sao?
Bạn giải thích vì sao deadline toàn bộ request nên được tính khi chuỗi gọi đi qua nhiều microservice như thế nào?
Bạn sẽ thiết kế correlation ID và trace context đi qua các HTTP client đã được load-balanced ra sao?
Bạn đánh giá rủi ro truyền trực tiếp thông tin người dùng trong metadata của service registry như thế nào?
Bạn sẽ giới hạn mối tin cậy giữa các service dù chúng được tìm thấy thông qua DiscoveryClient như thế nào?
Bạn phân biệt xác thực kết nối tới registry với xác thực giữa các service nghiệp vụ như thế nào?
Bạn giải thích vì sao tìm được một instance từ registry không có nghĩa instance đó được phép truy cập dữ liệu của caller như thế nào?
Bạn sẽ cấu hình TLS và kiểm tra danh tính downstream trong môi trường có discovery động ra sao?
Bạn đánh giá nguy cơ gọi nhầm môi trường do service ID giống nhau trong hai registry khác nhau ra sao?
Bạn sẽ kiểm soát secret cấp cho config client và discovery client theo nguyên tắc quyền tối thiểu ra sao?
Bạn xác định cách ngăn endpoint quản trị refresh gây thay đổi cấu hình trái phép như thế nào?
Bạn phân tích lý do không nên đưa password hoặc token vào URL discovery có thể bị ghi log như thế nào?
Bạn sẽ thiết kế đường đi của config và credential khi service khởi động mà không phụ thuộc vào secret trong image ra sao?
Bạn đánh giá ảnh hưởng của việc xoay vòng credential registry hoặc config backend tới các instance đang chạy ra sao?
Bạn sẽ kiểm tra một sự kiện refresh không làm lộ cấu hình nhạy cảm ra log như thế nào?
Bạn thiết kế kiểm tra tính hợp lệ của endpoint và certificate khi config server hoặc registry được chuyển địa chỉ ra sao?
Bạn sẽ phân biệt availability của registry với authorization failure khi tra cứu instance như thế nào?
Bạn xác định chỉ số nào quan trọng nhất để quan sát discovery và load balancing của Spring Cloud như thế nào?
Bạn sẽ đo tỉ lệ discovery cache hit và thời gian truy vấn instance list ra sao?
Bạn mô tả cách ghi log thay đổi instance membership mà không gây log flood khi autoscaling ra sao?
Bạn lựa chọn metric nào để phát hiện registry bị lỗi hoặc có instance stale tăng bất thường như thế nào?
Bạn sẽ phân tích trace của một request từ client-side load balancer qua HTTP client tới dependency ra sao?
Bạn xác định cách liên kết thời gian refresh cấu hình với biến động error rate sau deploy như thế nào?
Bạn sẽ thiết kế dashboard cho số instance healthy, lỗi kết nối và latency của từng service ID ra sao?
Bạn đánh giá rủi ro gắn host động hoặc request ID vào metric tags khi triển khai auto-scaling ra sao?
Bạn phân biệt lỗi timeout khi truy vấn registry với timeout khi gọi instance được chọn như thế nào?
Bạn sẽ thiết kế cảnh báo khi không còn instance sẵn sàng cho một dependency quan trọng ra sao?
Bạn xác định cách quan sát lỗi do một phiên bản instance mới khi rolling deployment như thế nào?
Bạn giải thích vai trò của actuator health trong việc điều tra trạng thái ứng dụng và dependency như thế nào?
Bạn sẽ sử dụng condition evaluation report để xác định implementation discovery nào được tự cấu hình ra sao?
Bạn phân tích trường hợp hai DiscoveryClient cùng xuất hiện làm kết quả truy vấn không như mong đợi như thế nào?
Bạn sẽ thiết kế runbook điều tra một service liên tục không thể tìm thấy dependency sau khi deploy ra sao?
Bạn phân biệt startup readiness failure do cấu hình với runtime request failure do registry biến động như thế nào?
Bạn sẽ tổ chức log và metrics để so sánh hành vi trước và sau khi refresh properties ra sao?
Bạn giải thích lợi ích của unit test khi code nghiệp vụ phụ thuộc abstraction DiscoveryClient thay vì SDK registry cụ thể như thế nào?
Bạn sẽ sử dụng fake DiscoveryClient để kiểm thử các tình huống instance rỗng, một instance và nhiều instance ra sao?
Bạn thiết kế unit test cho ServiceRegistry adapter mà không kết nối registry thật như thế nào?
Bạn sẽ kiểm thử Spring Cloud LoadBalancer chọn instance hợp lệ từ một danh sách ServiceInstance giả ra sao?
Bạn phân biệt test kiểm tra logic lựa chọn instance với integration test có HTTP server thật như thế nào?
Bạn sẽ viết kiểm thử RestClient hoặc WebClient đã load-balanced mà không gọi dịch vụ production ra sao?
Bạn đánh giá cách xác nhận HTTP client gửi request tới đúng instance khi nhiều URI được đưa vào test như thế nào?
Bạn sẽ dùng ApplicationContextRunner để kiểm tra auto-configuration discovery có bật tắt đúng điều kiện ra sao?
Bạn phân biệt @SpringBootTest với một context test tối giản khi kiểm tra Spring Cloud Context như thế nào?
Bạn thiết kế kiểm thử property source precedence khi cùng một khóa xuất hiện ở Config Data và biến môi trường như thế nào?
Bạn sẽ kiểm thử một cấu hình từ xa vắng mặt trong chế độ optional và bắt buộc như thế nào?
Bạn phân tích cách mô phỏng lỗi tải cấu hình ở startup mà không phụ thuộc hệ thống ngoài như thế nào?
Bạn sẽ kiểm thử một bean @RefreshScope nhận giá trị property mới sau khi kích hoạt refresh ra sao?
Bạn xác định cách bảo đảm refresh không làm mất trạng thái nghiệp vụ hoặc rò rỉ kết nối trong bài kiểm thử như thế nào?
Bạn sẽ kiểm thử thay đổi cấu hình không được áp dụng khi bean không hỗ trợ refresh ra sao?
Bạn thiết kế test phát hiện missing secret làm ứng dụng fail-fast đúng lúc startup như thế nào?
Bạn sẽ kiểm thử sự khác nhau giữa bootstrap context tương thích cũ và Config Data import sau nâng cấp ra sao?
Bạn phân tích vì sao việc dùng registry giả trong unit test không đủ chứng minh khả năng tự phục hồi khi mạng chập chờn ra sao?
Bạn sẽ viết integration test với nhiều instance giả để kiểm tra phản ứng khi scale up và scale down như thế nào?
Bạn xây dựng kiểm thử khi instance mất readiness nhưng vẫn còn trong discovery cache như thế nào?
Bạn sẽ kiểm thử retry không gửi lại thao tác ghi dữ liệu ngoài ý muốn ra sao?
Bạn thiết kế kiểm thử multi-instance refresh để phát hiện tình trạng một số node giữ cấu hình cũ như thế nào?
Bạn xác định tiêu chí kiểm thử tương thích khi nâng cấp Spring Boot và Spring Cloud release train như thế nào?
Bạn sẽ thiết kế kịch bản chaos test khi registry lỗi trong lúc client vẫn đang xử lý nhiều request ra sao?
Bạn phân tích cách xác minh graceful shutdown và deregistration bằng integration test như thế nào?
Bạn sẽ kiểm thử service không được cấp quyền truy cập registry và không vô tình dùng dữ liệu từ môi trường khác ra sao?
Bạn thiết kế test bảo đảm telemetry không ghi lộ secret hoặc dữ liệu nhạy cảm từ cấu hình ra sao?
Nếu ứng dụng Spring Cloud không khởi động sau khi nâng Spring Boot, bạn sẽ kiểm tra release train và dependency như thế nào?
Nếu cấu hình từ xa đã đổi nhưng bean vẫn sử dụng giá trị cũ, bạn sẽ chẩn đoán property source và refresh scope ra sao?
Nếu một service khởi động thành công khi config backend lỗi nhưng chạy sai endpoint, bạn sẽ điều chỉnh chính sách fail-fast như thế nào?
Nếu @RefreshScope tạo lại HTTP client khiến request đang chạy bị lỗi, bạn sẽ thiết kế quy trình cập nhật an toàn ra sao?
Nếu DiscoveryClient trả danh sách rỗng dù registry hiển thị instance, bạn sẽ kiểm tra service ID và namespace như thế nào?
Nếu một instance bị xóa khỏi registry nhưng vẫn nhận traffic, bạn sẽ xem xét cache và connection reuse ra sao?
Nếu nhiều instance đăng ký cùng tên nhưng nằm ở hai vùng địa lý, bạn sẽ định tuyến và xử lý failover như thế nào?
Nếu một lời gọi WebClient qua service ID không được cân bằng tải, bạn sẽ kiểm tra builder và auto-configuration ra sao?
Nếu một service có hai DiscoveryClient implementation, bạn sẽ xác minh thứ tự ưu tiên và kết quả composite như thế nào?
Nếu service chuẩn bị shutdown nhưng registry vẫn cung cấp instance cho client, bạn sẽ thiết kế drain và deregistration ra sao?
Nếu một thay đổi cấu hình áp dụng không đồng bộ trên các node gây lỗi dữ liệu, bạn sẽ xây dựng rollback và rollout như thế nào?
Nếu registry outage làm request chậm dù dependency vẫn khỏe, bạn sẽ phân biệt cache discovery và timeout kết nối ra sao?
Nếu một ứng dụng web và một batch worker dùng chung Spring Cloud dependencies, bạn sẽ chọn các abstraction cần kích hoạt như thế nào?
Nếu phải thiết kế một nền tảng Spring Cloud Core cho nhiều team, bạn sẽ chuẩn hóa phiên bản, cấu hình, discovery và kiểm thử ra sao?
Nếu phải vận hành dịch vụ Spring Cloud khi config backend và registry đều lỗi, bạn sẽ xác định ưu tiên phục hồi và giảm tác động như thế nào?
