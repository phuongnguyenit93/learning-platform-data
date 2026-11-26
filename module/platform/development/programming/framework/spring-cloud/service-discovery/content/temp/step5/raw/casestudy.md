Một dịch vụ đặt hàng dùng Spring Cloud DiscoveryClient để tìm inventory-service, nhưng tên dịch vụ được đăng ký khác giữa staging và production khiến chỉ môi trường thật không tìm được instance.
Ứng dụng Spring Boot sử dụng DiscoveryClient lấy danh sách payment-service lúc khởi động rồi giữ nguyên trong bộ nhớ, khiến các instance mới được autoscale không bao giờ nhận lưu lượng.
Một API tổng hợp gọi DiscoveryClient để tìm customer-service trên mỗi request, nhưng khi registry chậm thì thời gian trả kết quả của API cũng tăng đột biến.
Nhóm phát triển dựa vào tên dịch vụ logic trong DiscoveryClient nhưng một microservice cũ vẫn gọi thẳng địa chỉ IP, khiến traffic tiếp tục đến pod đã bị thu hồi.
Một service dùng DiscoveryClient trên laptop với một instance giả, nhưng production có nhiều instance và logic chọn endpoint luôn lấy phần tử đầu tiên làm phân phối tải lệch hẳn.
Ứng dụng sử dụng spring.application.name chung cho hai service độc lập, khiến DiscoveryClient trả instance của cả hai loại nghiệp vụ dưới cùng một service ID.
Nhóm đổi tên billing-service thành invoice-service nhưng chưa cập nhật tên lookup trong client, khiến các request từ ứng dụng cũ trả lỗi khi không còn tên cũ trong registry.
Một hệ thống trả danh sách instance rỗng từ DiscoveryClient khi đường tới registry gián đoạn, nhưng tầng API ghi nhận đó là lỗi không tồn tại khách hàng thay vì lỗi hạ tầng.
Đội tích hợp xây một adapter lấy host và port từ ServiceInstance, nhưng logic không tôn trọng cờ secure khiến request HTTPS bị gửi qua HTTP tới một số instance.
Ứng dụng có nhiều DiscoveryClient implementations trên classpath, nhưng danh sách instance nhận được khác với backend mà đội vận hành tưởng đang sử dụng.
Một luồng Spring Boot xử lý giao dịch tài chính dùng tên inventory-service qua DiscoveryClient, nhưng metadata vùng của instance không được xét khiến lưu lượng đi xuyên vùng không mong muốn.
Nhóm gọi getServices để hiện danh sách ứng dụng nội bộ trên dashboard, nhưng cho rằng danh sách đó phản ánh chính xác mọi instance đang khỏe và bỏ qua trạng thái đăng ký.
Một client tạo endpoint từ service ID và context path cố định, trong khi một instance mới đổi base path nên chỉ các request đi tới phiên bản này trả 404.
Ứng dụng lưu một ServiceInstance trong singleton để giảm lookup, nhưng instance đó ngừng hoạt động sau rolling deployment và client tiếp tục kết nối tới địa chỉ cũ.
Một service chạy hai tên đăng ký khác nhau cho cùng codebase theo profile, nhưng người điều hành chỉ giám sát một tên khiến một nửa traffic không được quan sát.
Nhóm viết fallback khi DiscoveryClient không tìm được instance bằng cách chuyển tới địa chỉ thử nghiệm mặc định, khiến một đợt lỗi production vô tình gửi dữ liệu thật sang sandbox.
Một ứng dụng gateway nhận tên dịch vụ từ tham số HTTP của người dùng rồi tra DiscoveryClient, làm lộ khả năng định tuyến tới các service nội bộ ngoài phạm vi API công khai.
Một service phát hiện nhiều instance có cùng ID nhưng port khác nhau trong DiscoveryClient, khiến một số lời gọi nhận địa chỉ không phản ánh tiến trình đang phục vụ.
Ứng dụng kết hợp tra cứu instance động với cấu hình URL tĩnh nhưng không có tiêu chí chọn nguồn, khiến hai pod cùng version truy cập hai backend khác nhau.
Nhóm kiểm thử DiscoveryClient bằng danh sách ServiceInstance tự tạo nhưng không mô phỏng instance không có host hợp lệ, khiến lỗi tạo URL chỉ xuất hiện trên một node production.
Một hệ thống dùng ServiceRegistry để đưa ứng dụng bảo trì sang trạng thái OUT_OF_SERVICE, nhưng client vẫn có danh sách instance cũ và tiếp tục gửi request trong một khoảng thời gian.
Nhóm đăng ký service với ServiceRegistry khi tiến trình còn đang migrate database, khiến client gọi vào một ứng dụng chưa sẵn sàng xử lý giao dịch.
Ứng dụng tắt auto-registration để kiểm soát rollout nhưng không có bước đăng ký thủ công tương ứng, khiến pod khỏe ở Kubernetes mà DiscoveryClient không tìm thấy.
Một service đổi trạng thái đăng ký khi kết thúc xử lý nền nhưng lỗi bất đồng bộ làm thao tác deregister không chạy, khiến registry còn giữ endpoint đã tắt.
Đội triển khai nhiều instance dùng cùng service instance ID được tạo từ tên máy, khiến hai container trên cùng node ghi đè bản ghi đăng ký của nhau.
Một ứng dụng đăng ký ServiceRegistry với địa chỉ và port lúc khởi động nhưng thực tế web server được gán cổng ngẫu nhiên sau đó, khiến client gọi nhầm port chưa mở.
Nhóm cấu hình service registration cho môi trường container nhưng quảng bá hostname chỉ resolve được bên trong pod, khiến các service ở node khác không thể kết nối.
Một ứng dụng đặt nhầm management port làm service port trong bản ghi đăng ký, khiến load balancer gọi endpoint Actuator thay vì API nghiệp vụ.
Đội vận hành đổi cổng server.port nhưng quên cập nhật cấu hình service registry tự khai báo, khiến health endpoint lên UP còn caller nhận connection refused.
Một service có hai interface mạng công cộng và riêng, nhưng cơ chế chọn địa chỉ quảng bá tự động lấy interface public mà mạng microservice không thể truy cập.
Ứng dụng đăng ký địa chỉ IPv6 ở môi trường hỗn hợp, trong khi một nhóm client chỉ được phép đi IPv4 nên các request thất bại tùy instance.
Nhóm tạo ServiceRegistry adapter tùy biến lưu thông tin instance vào Consul, nhưng chưa làm rõ điều gì xảy ra nếu bước đăng ký thành công còn bước khởi tạo listener thất bại.
Một tiến trình batch ngắn hạn tự đăng ký như service lâu dài rồi kết thúc nhanh, khiến registry chứa các instance chỉ sống vài giây và client gặp lỗi kết nối ngẫu nhiên.
Đội hạ tầng cấu hình nhiều application contexts trong một Spring Boot process, nhưng mỗi context đăng ký cùng tên và ID khiến việc hủy đăng ký ảnh hưởng cả phiên còn chạy.
Một client dựa vào metadata zone trong ServiceInstance để chọn vùng nhưng service đăng ký field đó không nhất quán về chữ hoa, khiến affinity theo vùng không hoạt động.
Nhóm xây cơ chế đặt trạng thái bảo trì qua ServiceRegistry, nhưng lệnh từ hai operator gần nhau cập nhật status ngược thứ tự khiến instance được nhận traffic sớm.
Ứng dụng triển khai graceful shutdown nhưng tiến trình chỉ deregister sau khi đóng socket, khiến các client nhận endpoint hợp lệ trong registry rồi kết nối bị từ chối.
Một service cần báo trạng thái sẵn sàng theo business readiness nhưng hệ thống đăng ký chỉ dựa trên việc JVM đã chạy, khiến request đầu tiên sau restart thất bại.
Đội muốn theo dõi tuổi thọ instance trong ServiceRegistry nhưng không mang phiên bản triển khai hay thời điểm khởi tạo, khiến bản ghi cũ khó phân biệt với bản mới.
Một ứng dụng có hai vùng hoạt động độc lập nhưng service registration gửi cả hai vùng vào cùng namespace mà không gắn metadata vùng, khiến client gọi xuyên khu vực không có kiểm soát.
Một Eureka client đăng ký thành công trên Eureka Server nhưng không gửi heartbeat ổn định do pool thread bị nghẽn, khiến instance vẫn phục vụ request nhưng biến mất khỏi registry.
Nhóm rút ngắn lease expiration của Eureka để loại nhanh instance chết nhưng không xét network jitter, khiến các pod khỏe bị đánh dấu hết hạn khi cluster chịu tải.
Ứng dụng Eureka client dừng đột ngột do OOM và không kịp gửi deregistration, khiến client khác vẫn thấy endpoint đó cho tới khi lease bị xử lý.
Đội vận hành cho rằng mỗi lần Eureka Server trả status UP là nó đã kiểm tra endpoint nghiệp vụ, khiến một process bị deadlock vẫn được load balancer gọi tới.
Một Eureka client dùng hostname lấy từ container ID không có DNS nội bộ, khiến registry hiển thị UP nhưng request tới instance luôn thất bại.
Nhóm cấu hình Eureka instance prefer-ip-address ở một cụm đa mạng, nhưng địa chỉ IP được đăng ký thuộc bridge network không thể truy cập từ client ở cụm khác.
Một ứng dụng chạy Eureka ở hai availability zones nhưng metadata zone của instance thiếu nhất quán, khiến client gọi xuyên zone ngay cả khi có instance cục bộ.
Đội bật Eureka server peer replication giữa hai vùng nhưng một peer bị tách mạng, khiến các client kết nối từng peer nhìn thấy bộ instance khác nhau.
Một Eureka Server trải qua network partition và giữ lại nhiều instance nhờ cơ chế self-preservation, khiến các client tiếp tục nhận endpoint đã chết trong lúc sự cố kéo dài.
Nhóm tắt self-preservation của Eureka để dọn registry nhanh, nhưng đợt mất mạng tạm thời làm số instance được giữ trong registry giảm đột ngột dù ứng dụng vẫn chạy.
Ứng dụng dựa vào Eureka cache ở client để chọn instance nhưng deployment liên tục scale up/down, khiến độ trễ cập nhật danh sách làm request được gửi tới pod vừa dừng.
Một Eureka client mới khởi động giữa đợt registry outage, nhưng cấu hình retry và thời gian chờ không phù hợp khiến nó không đăng ký trước khi rollout timeout.
Đội di chuyển Eureka Server sang cổng mới nhưng một nhóm client vẫn dùng defaultZone cũ, khiến chỉ các service thuộc nhóm đó bị cô lập sau deploy.
Nhóm dùng Eureka ở nhiều trung tâm dữ liệu và cấu hình serviceUrl khác nhau giữa các pod, khiến cùng một tên service cho ra danh sách instance khác nhau.
Một API gateway kết nối Eureka Server có registry gần đúng nhưng Eureka client còn giữ cache một địa chỉ cũ, khiến chỉ một tỷ lệ request bị lỗi sau khi service scale down.
Ứng dụng muốn bỏ một Eureka instance khỏi traffic trước khi dừng nhưng chỉ đổi Spring Boot readiness, trong khi status Eureka vẫn UP và client tiếp tục chọn.
Đội vận hành thay health check handler của Eureka client để phản ánh dependency bắt buộc, nhưng lỗi mạng tới database làm mọi instance chuyển trạng thái không khỏe cùng lúc.
Một Eureka client đăng ký status STARTING lâu hơn dự kiến sau deploy, khiến dashboard thấy pod sẵn sàng mà client dùng Eureka không tìm được instance có thể gọi.
Nhóm nâng Eureka client cùng lúc thay đổi cấu hình instanceId, khiến các bản ghi cũ chưa hết lease cùng tồn tại với bản ghi mới và số instance trên dashboard tăng giả tạo.
Ứng dụng đăng ký nhiều virtual host names cho cùng instance Eureka nhưng consumer nhìn nhầm loại tên, khiến lookup không trả đúng nhóm service.
Đội triển khai Eureka Server sau gateway với xác thực, nhưng client không gửi được credentials nên chỉ những instance đã đăng ký trước đó còn xuất hiện trong cache.
Nhóm sao chép một cấu hình Eureka từ staging sang production, khiến service production cố gửi heartbeat tới registry staging và không được các caller production tìm thấy.
Một Eureka registry đã có instance lỗi nhưng bảng điều khiển vẫn hiển thị dữ liệu cache cũ sau khi khôi phục peer connection, khiến việc kiểm chứng sửa lỗi bị chậm.
Ứng dụng đăng ký metadata securePortEnabled không phù hợp với cổng HTTPS thực tế, khiến client chọn giao thức kết nối khác với service đang lắng nghe.
Một Eureka client trong Kubernetes có IP pod thay đổi sau rescheduling, nhưng bản ghi instance cũ vẫn tồn tại và load balancer đôi lúc chọn địa chỉ không còn tuyến.
Đội thấy hai region trong Eureka nhưng chính sách gọi remote region không được cấu hình như kỳ vọng, khiến client fallback sang vùng xa khi vùng chính bận tải.
Một hệ thống dùng Eureka trong rolling deployment, nhưng phiên bản cũ và mới quảng bá cùng metadata phiên bản khiến canary traffic không thể được tách biệt.
Nhóm tăng heartbeat frequency cho hàng nghìn Eureka clients mà không đo năng lực server, khiến registry chịu áp lực request cao trong đợt autoscaling.
Một Spring Boot service cố đăng ký Eureka khi service discovery được tắt ở một profile test, khiến integration test chờ endpoint registry không tồn tại.
Ứng dụng có endpoint health trả DOWN khi cache phụ trợ lỗi, nhưng Eureka vẫn báo UP vì health check propagation không được cấu hình theo yêu cầu của đội trực.
Đội khởi động Eureka Server trong môi trường container và dùng hostname local trong peer URL, khiến cụm nhiều node không trao đổi được registration với nhau.
Một Consul agent đăng ký một service Spring Boot nhưng health check HTTP đang trỏ tới cổng cũ, khiến service được Consul đánh dấu critical dù API mới vẫn hoạt động.
Nhóm cấu hình Consul service registration dùng địa chỉ localhost, khiến health check trên cùng host thành công nhưng client từ host khác không thể kết nối.
Ứng dụng Spring Cloud Consul tạo service ID giống nhau cho nhiều pod, khiến bản đăng ký của pod sau che khuất pod trước trong Consul catalog.
Đội dùng Consul health check với đường dẫn Actuator không tồn tại sau khi đổi management base path, khiến toàn bộ service bị loại khỏi kết quả tra cứu healthy.
Một Consul agent kiểm tra health endpoint qua HTTPS nhưng chứng chỉ self-signed không nằm trong trust chain, khiến instance báo critical chỉ ở production.
Nhóm dùng TTL health check trong Consul nhưng ứng dụng không cập nhật trạng thái định kỳ khi thread pool bị nghẽn, khiến instance bị loại dù endpoint nghiệp vụ vẫn trả lời.
Ứng dụng giữ TTL health check ở passing sau khi worker nền đã chết, khiến Consul tiếp tục cho client tìm instance không còn xử lý tác vụ chính.
Một Consul agent đang mất kết nối tới Consul servers nên catalog của một vùng không phản ánh thay đổi mới, khiến client của vùng đó gọi tới các IP đã bị thu hồi.
Đội triển khai Consul cluster qua nhiều datacenters nhưng query của client chỉ xét datacenter mặc định, khiến hệ thống dự phòng không tìm được instance ở vùng khác khi failover.
Nhóm dùng Consul ACL token có quyền đăng ký service nhưng thiếu quyền quản lý health check liên quan, khiến thao tác đăng ký thành công một phần và status không cập nhật.
Một service Spring Cloud Consul chỉ có quyền đọc catalog của nhóm mình, nhưng cấu hình client thử lookup service khác và nhận danh sách rỗng bị nhầm thành hết instance.
Ứng dụng dùng Consul service tags để phân tách phiên bản blue và green, nhưng tag của một phiên bản bị thiếu nên cùng một truy vấn trả kết quả không mong muốn.
Đội sử dụng Consul metadata để chọn instance gần khách nhưng metadata vùng từ hai nhóm triển khai viết khác quy ước, khiến kết quả chọn zone thiếu ổn định.
Nhóm đưa một service Consul sang trạng thái maintenance trong đợt nâng cấp, nhưng ứng dụng client giữ cache địa chỉ cũ và vẫn gửi request tới instance đó.
Một Consul agent gặp lỗi disk và restart liên tục, khiến các health check flapping và số instance hợp lệ dao động dù tiến trình Spring Boot không thay đổi.
Ứng dụng đổi địa chỉ cổng management của Actuator nhưng Consul HTTP check tiếp tục dùng application port với route mới, khiến health hiển thị không phản ánh endpoint muốn đo.
Đội triển khai Consul DNS cho một số client và HTTP API catalog cho một số client khác, khiến thời điểm cập nhật danh sách instance không trùng nhau trong một lần scale down.
Một hệ thống dùng Consul DNS với TTL cache dài tại client JVM, khiến các request vẫn đi tới địa chỉ cũ sau khi operator đã deregister instance lỗi.
Nhóm cấp quyền Consul agent cho nhiều microservice bằng cùng một ACL token, khiến một token bị lộ có thể tác động lên service registration của các nhóm khác.
Ứng dụng dùng Consul KV và service discovery trong cùng cluster, nhưng quyền đọc cấu hình KV được cấp rộng hơn quyền đọc catalog khiến thông tin nhạy cảm bị lộ.
Một workload phát triển trên Consul chạy được với HTTP cục bộ, nhưng production bật TLS cho Consul API và client chưa trust CA của server.
Đội thay Consul client tới datacenter dự phòng trong sự cố, nhưng mỗi datacenter có tên service/tag khác nhau khiến lookup thành công nhưng trả ứng dụng không tương thích.
Một service được đăng ký Consul qua service-registration API của ứng dụng, nhưng Consul agent còn lưu một bản đăng ký thủ công cũ với địa chỉ đã ngừng sử dụng.
Nhóm cấu hình Consul deregister_critical_service_after quá ngắn cho dịch vụ cần warm-up lâu, khiến instance bị xóa khỏi catalog trước khi bước khởi tạo hoàn tất.
Một Consul service check trả HTTP 200 cho health tổng hợp nhưng không phản ánh lỗi publisher broker nền, khiến caller vẫn gửi tác vụ tới worker không xử lý được.
Đội dùng Consul blocking query để quan sát thay đổi service, nhưng client xử lý token index sai và lặp nhiều request không cần thiết khi catalog ổn định.
Một ứng dụng đăng ký service qua Consul agent ở sidecar, nhưng container sidecar bị restart và bản ghi biến mất trong khi process Spring Boot còn phục vụ bình thường.
Nhóm triển khai Consul catalog với nhiều node cùng service name nhưng không gắn unique instance ID rõ ràng, khiến dashboard coi các bản ghi là một và báo sai số lượng.
Đội sử dụng Consul prepared query để ưu tiên các instance healthy trong vùng, nhưng một số service không gắn datacenter metadata phù hợp khiến lưu lượng bị chuyển xuyên vùng.
Ứng dụng vừa dùng Eureka cho nhóm dịch vụ Java vừa dùng Consul cho hệ thống legacy, nhưng cùng một tên service xuất hiện ở hai registry với tập instance khác nhau.
Một Spring Cloud LoadBalancer chọn ngẫu nhiên instance từ DiscoveryClient nhưng danh sách có endpoint đã ngừng hoạt động, khiến tỷ lệ lỗi tăng sau khi rolling update.
Nhóm dùng RoundRobinLoadBalancer trên cluster với các instance cấu hình CPU khác nhau, khiến node yếu thường xuyên vượt tải dù tổng tài nguyên còn dư.
Một service dùng Spring Cloud LoadBalancer cho request checkout nhưng kết quả chọn instance không xét vùng mạng, khiến cuộc gọi đồng bộ xuyên zone tăng cả latency lẫn chi phí.
Ứng dụng cấu hình WebClient gọi theo service name với load balancing, nhưng một bean WebClient khác không có bộ lọc tương ứng nên chỉ một số outbound calls resolve được tên logic.
Đội dùng RestClient gọi URL chứa service ID trong Spring Boot nhưng RestClient được tạo không qua load-balancer-aware builder, khiến DNS không phân giải được host logic.
Một Feign client và một WebClient trong cùng ứng dụng lấy danh sách instance qua các cơ chế khác nhau, khiến chỉ một đường gọi tiếp tục tới pod đã deregister.
Nhóm bật retry trên Spring Cloud LoadBalancer cho các request GET, nhưng endpoint đích có tác dụng ghi thông qua GET legacy làm một thao tác tạo dữ liệu trùng khi mạng lỗi.
Ứng dụng thử lại HTTP POST qua instance khác sau timeout mà không có mã yêu cầu ổn định, khiến hai instance downstream có thể cùng ghi một giao dịch.
Đội cấu hình health-check-based instance supplier cho LoadBalancer nhưng endpoint health phản hồi chậm, khiến danh sách instance rỗng trong những thời điểm tải cao.
Một service Spring Cloud LoadBalancer cache danh sách ServiceInstance quá lâu, khiến instance bị đặt maintenance vẫn được chọn trong suốt thời gian cache chưa hết hạn.
Nhóm giảm thời gian cache danh sách instance xuống rất ngắn để cập nhật nhanh, nhưng registry bị gọi liên tục và gây tăng latency dưới tải cao.
Ứng dụng có hai instance customer-service ở hai vùng, nhưng LoadBalancer không biết instance có version tương thích với request nên đôi lúc JSON response thiếu trường mới.
Một API quan trọng dùng load balancing theo zone nhưng một vùng tạm hết instance, khiến fallback gửi traffic sang vùng có luật lưu trữ dữ liệu khác.
Đội muốn canary 5% request tới phiên bản mới nhưng cấu hình instance weights bị áp nhầm cho tất cả môi trường, khiến staging và production có phân phối tải khác dự tính.
Nhóm thực hiện sticky routing theo session nhưng instanceId thay đổi sau rescheduling, khiến những phiên người dùng đang chạy được chuyển đột ngột sang node khác.
Ứng dụng xử lý yêu cầu streaming dài và dùng LoadBalancer chọn instance lúc mở kết nối, nhưng instance đó bị drain giữa stream làm nhiều client mất dữ liệu chưa nhận.
Đội tắt kết nối keep-alive ở HTTP client nhưng cho rằng LoadBalancer sẽ tái sử dụng connection pool theo service ID, khiến tài nguyên socket tăng mạnh khi gọi nhiều instance.
Một service chọn instance bằng vùng metadata rồi trả IP trực tiếp cho client mobile, khiến địa chỉ private của microservice bị lộ và ứng dụng di động không kết nối được.
Nhóm muốn loại instance không sẵn sàng khỏi kết quả LoadBalancer nhưng registry chỉ biết trạng thái process UP, khiến request đi tới pod đang chạy migration dữ liệu.
Ứng dụng có ServiceInstanceListSupplier kết hợp nhiều filter, nhưng thứ tự lọc zone, health và version khiến danh sách còn rỗng khi mỗi tiêu chí riêng vẫn có instance hợp lệ.
Đội triển khai weighted routing theo metadata capacity nhưng một số instance thiếu field trọng số, khiến traffic dồn vào các node không phù hợp với năng lực.
Một service đặt timeout gọi downstream thấp hơn thời gian registry lookup cộng connection establishment, khiến nhiều request thất bại dù backend xử lý nghiệp vụ nhanh.
Nhóm dùng client-side load balancing cho API đối tác nhưng endpoint của đối tác còn có cơ chế global load balancing riêng, khiến việc xác định nguyên nhân lệch tải khó khăn.
Ứng dụng phân phối gọi qua nhiều zone nhưng dữ liệu phiên lưu tại local memory, khiến user có thể bị mất trạng thái khi LoadBalancer chọn instance khác.
Đội kiểm thử LoadBalancer với hai ServiceInstance cố định và không thử trường hợp toàn bộ instance không khỏe, khiến API trả exception chung khó hiểu trong sự cố thực.
Một bộ chọn instance tùy biến dùng vị trí cuối trong danh sách nhưng không kiểm tra danh sách rỗng, khiến một đợt registry outage làm request trả 500 thay vì lỗi có ngữ cảnh.
Nhóm chạy hai phiên bản API cùng đăng ký payment-service nhưng gắn metadata release khác nhau, khiến caller không đọc metadata vẫn chọn nhầm instance chưa hỗ trợ hợp đồng cũ.
Một hệ thống bật metrics cho số request đến từng instance nhưng chỉ đếm request bắt đầu, khiến load balancing bị báo công bằng dù nhiều request timeout tập trung tại một node.
Ứng dụng chạy Spring Cloud Gateway với route service-discovery nhưng service ID có chữ hoa khác giữa các nhóm triển khai, khiến một số route động không được tạo như dự kiến.
Nhóm cấu hình gateway tự động phát hiện mọi service trong registry, khiến một số endpoint nội bộ không có mục đích public vô tình được định tuyến qua gateway.
Một API gateway cache route dựa trên registry lâu hơn tuổi thọ pod, khiến request vẫn được chuyển tới endpoint cũ ngay sau khi service mới đã đăng ký.
Đội chuyển từ Eureka discovery sang Consul trong gateway nhưng giữ nguyên quy tắc metadata filtering, khiến canary route phân phối sai giữa các phiên bản.
Ứng dụng dùng lb://inventory-service trong Gateway nhưng môi trường test thiếu cơ chế discovery phù hợp, khiến route có mặt mà gọi downstream trả 503.
Nhóm bật load balancing ở Spring Cloud Gateway và đồng thời ở HTTP client downstream, khiến cùng yêu cầu đi qua nhiều tầng chọn instance mà trace không ghi rõ lựa chọn từng tầng.
Một gateway dựa trên service discovery cho route thanh toán nhưng không giới hạn danh sách service được công bố, khiến người dùng có thể truy cập đường dẫn của service quản trị.
Đội đổi context path của một service trong khi gateway vẫn dùng route mapping từ phiên bản trước, khiến registry lookup thành công nhưng endpoint nghiệp vụ trả 404.
Một service mesh đã quản lý endpoint và retry ở tầng mạng, nhưng Spring Cloud LoadBalancer cũng retry POST, khiến một lần timeout tạo ra nhiều yêu cầu lặp ngoài dự tính.
Ứng dụng đang dùng Consul Connect sidecar để bảo vệ giao tiếp service, nhưng client tự lấy IP trực tiếp từ registry và bỏ qua địa chỉ proxy cần thiết trong môi trường triển khai.
Nhóm triển khai mTLS giữa các service nhưng registry quảng bá cả HTTP port không được bảo vệ, khiến một số client gửi dữ liệu nhạy cảm qua cổng cũ.
Một Eureka Server mở endpoint đăng ký không có xác thực trong mạng mà nhiều team cùng truy cập, khiến một workload không được tin cậy có thể đăng ký instance giả.
Đội cấp Consul ACL token cho ứng dụng client chỉ cần tra cứu, nhưng token còn có quyền deregister service khác khiến rủi ro thao tác nhầm rất lớn.
Ứng dụng ghi log URL Eureka chứa thông tin xác thực khi gặp lỗi kết nối, khiến credential registry xuất hiện trong hệ thống log tập trung.
Nhóm dùng chứng chỉ TLS riêng cho Consul Server nhưng client Spring Boot chưa tin CA mới, khiến lookup instance thất bại ngay sau đợt xoay chứng chỉ.
Một service client trỏ tới registry qua DNS nội bộ nhưng thay đổi firewall chỉ chặn lưu lượng từ một namespace, khiến lỗi discovery xảy ra theo nhóm pod thay vì toàn cluster.
Đội chuyển Eureka Server sau ingress có định tuyến nhiều host, nhưng X-Forwarded headers không được xử lý đúng và client nhận các URL registry không thể truy cập.
Một Consul agent được quảng bá trên IP ngoài mạng cho một số node, khiến service registration trông bình thường tại local nhưng các client liên vùng không kết nối được.
Ứng dụng chạy Spring Cloud Discovery ở Kubernetes và dùng IP pod làm địa chỉ quảng bá, nhưng một nhóm caller đặt ở mạng ngoài cluster không có route tới dải IP này.
Nhóm cài đặt network policy chỉ cho phép traffic tới service port nhưng chặn heartbeat Eureka từ client, khiến instance hết lease dù API hoạt động bình thường bên trong namespace.
Một dịch vụ dùng ServiceInstance metadata chứa internal hostname và thông tin build bí mật, nhưng gateway đưa metadata đó vào response public cho người dùng.
Đội tách quyền quản trị Consul catalog theo namespace nhưng client mới dùng ACL token thuộc namespace khác, khiến truy vấn nhận danh sách rỗng mà không chỉ rõ nguyên nhân.
Một Eureka Server nằm trong vùng mạng bị NAT, nhưng instance đăng ký địa chỉ riêng của node thay vì địa chỉ mà client từ vùng khác có thể kết nối.
Ứng dụng dùng Consul service-to-service access policy theo service identity, nhưng đổi tên service đăng ký làm các kết nối proxy bị từ chối dù lookup vẫn trả instance.
Nhóm triển khai TLS cho Spring Boot health endpoint nhưng Eureka client health handler không thể gọi đường dẫn yêu cầu mutual TLS, khiến status không phản ánh khả năng phục vụ.
Một service dùng DiscoveryClient tra cứu instance qua region nhưng bỏ qua ranh giới dữ liệu khách, khiến truy vấn có thể được gửi đến node ở quốc gia khác.
Đội quản trị cấu hình Eureka peers qua một certificate chung đã hết hạn, khiến đăng ký ở từng server vẫn có nhưng quá trình đồng bộ registry giữa peers bị gián đoạn.
Ứng dụng ký request tới downstream bằng hostname logic nhưng LoadBalancer chuyển sang hostname vật lý khác, khiến một dịch vụ kiểm tra chữ ký gắn với host trả lỗi.
Nhóm xây health check truy cập endpoint actuator qua cổng public của gateway thay vì cổng service thật, khiến Consul đánh dấu instance khỏe dù service không xử lý trực tiếp được.
Một cụm microservice triển khai blue-green bằng Eureka nhưng instance của hai màu đều mang cùng metadata, khiến load balancer không tách được lượng request thử nghiệm.
Đội rollout canary của order-service trong khi Eureka cache tại một số caller chưa cập nhật, khiến tỉ lệ truy cập bản canary thấp hơn mục tiêu nhiều phút.
Một ứng dụng quy định chỉ instance có schema version mới được nhận request, nhưng registry không mang schema version và caller chọn nhầm node đang chạy migration.
Nhóm scale down một service đang xử lý đơn dài, nhưng trạng thái registry được cập nhật sau khi pod nhận tín hiệu shutdown nên các request mới vẫn đi vào pod đang drain.
Đội deploy nhiều pod cùng lúc nhưng registry giới hạn khả năng cập nhật trạng thái, khiến client thấy thiếu instance tạm thời ngay trong đợt tăng tải.
Ứng dụng triển khai instance ở hai availability zones nhưng thời gian đồng bộ registry khác nhau, khiến zone này tưởng zone kia không còn service và phát sinh failover không cần thiết.
Một batch job hằng đêm đột ngột gọi discovery theo tên service hàng nghìn lần đồng thời, khiến backend registry quá tải và các API thông thường cũng khó lookup instance.
Nhóm nâng cấp Eureka Server nhưng chưa đánh giá tương thích metadata/status với phiên bản Eureka clients cũ, khiến một phần service không đăng ký như trước.
Một hệ thống Consul dùng health check HTTP tần suất rất cao cho hàng nghìn instance, khiến chính các request health trở thành nguồn tải đáng kể trên ứng dụng.
Ứng dụng đưa kết quả health dependency từ dịch vụ thanh toán vào trạng thái discovery của mọi endpoint, khiến sự cố đối tác thanh toán làm cả chức năng tra cứu độc lập bị loại khỏi tải.
Đội cho rằng autoscaler tạo pod mới đồng nghĩa service registry đã biết instance, nhưng đợt tăng tải khiến pod READY trước khi bản đăng ký có mặt trên caller cache.
Nhóm triển khai một instance dự phòng có công suất thấp dưới cùng service ID, khiến round-robin gửi quá nhiều yêu cầu tới node dự phòng khi bật failover.
Một hệ thống sử dụng Consul cho discovery và Kubernetes readiness cho endpoint, nhưng hai nguồn trạng thái không thống nhất làm pod bị gửi traffic khi chưa sẵn sàng.
Ứng dụng đổi dữ liệu metadata dùng cho routing mà không restart hay cập nhật đăng ký, khiến registry vẫn quảng bá thông tin cũ suốt vòng đời của instance.
Nhóm chuyển ứng dụng khỏi máy chủ vật lý lên container nhưng ID đăng ký còn sử dụng hostname vật lý cũ, làm nhiều pod cạnh tranh trên cùng một bản ghi.
Đội sử dụng Eureka để giữ danh sách instance trong đợt chia tách mạng nhưng không đo tỷ lệ endpoint còn truy cập được, khiến tự bảo toàn registry che khuất lỗi kết nối thực.
Một sự cố DNS nội bộ làm một số Eureka clients chỉ kết nối được registry peer phụ, khiến danh sách service bị phân mảnh nhưng dashboard chính vẫn hiển thị đủ instance.
Nhóm dùng Consul để định tuyến traffic theo phiên bản nhưng đã xóa một tag canary từ service registration mà không dọn bộ lọc client, khiến canary không nhận request nào.
Một service quan trọng đặt lifecycle shutdown nhanh hơn thời gian các caller cập nhật danh sách load balancer, khiến một phần request bị lỗi kết nối khi triển khai liên tục.
Đội khôi phục registry từ snapshot cũ sau sự cố nhưng một số IP thuộc pod đã bị tái sử dụng, khiến client gọi nhầm process khác ở địa chỉ tưởng là service hợp lệ.
Một hệ thống có registry hai vùng và cùng một ID service instance nhưng địa chỉ IP trùng nhau trong các mạng riêng, khiến việc ghép registry xuyên vùng gây nhầm endpoint.
Ứng dụng giữ connection pool tới instance cũ sau khi registry đổi sang instance mới, khiến việc deregister không loại bỏ ngay request trên các connection đang mở.
Nhóm muốn giới hạn traffic tới một vùng khi sự cố lớn xảy ra nhưng metadata instance chỉ có zone chứ không có chính sách ưu tiên business, khiến failover làm quá tải vùng dự phòng.
Một API quan trọng dựa vào Eureka discovery nhưng không có kịch bản vận hành khi registry không truy cập được, khiến pod mới không tham gia tải dù các instance cũ vẫn phục vụ.
Một hệ thống có nhiều registry implementations trong cùng ứng dụng nhưng không xác định ưu tiên nguồn instance, khiến cùng một service ID trả tập endpoint khác giữa các call paths.
Nhóm chạy thử DiscoveryClient với in-memory service registry nhưng production dùng Eureka cache có độ trễ cập nhật, khiến bài test bỏ sót request tới instance vừa bị xóa.
Một bài integration test dùng mock ServiceInstance có host luôn hợp lệ nhưng không mô phỏng URL HTTPS, IPv6 và management port, khiến lỗi xây endpoint không xuất hiện trước release.
Đội kiểm thử Eureka heartbeat bằng cách dừng service gọn gàng, nhưng không mô phỏng mất điện node và mất mạng đột ngột nên không đánh giá được tuổi thọ bản ghi lỗi.
Nhóm chỉ kiểm thử ServiceRegistry register thành công mà không thử lỗi giữa ghi registration và bật readiness, khiến một pod chưa sẵn sàng vẫn xuất hiện trong catalog.
Một bộ test Consul chỉ kiểm tra service có trong catalog mà không truy vấn trạng thái health, khiến lỗi check HTTP path không được phát hiện ở môi trường staging.
Đội dùng Docker Compose với Consul cho integration test nhưng production bật ACL, khiến service không đủ quyền đăng ký và lỗi chỉ lộ ra sau khi deploy.
Nhóm chạy Testcontainers để thử Eureka Server với một instance nhưng không mô phỏng peer replication, khiến sự cố phân mảnh registry hai vùng chưa có bài kiểm thử.
Ứng dụng có custom LoadBalancer chọn instance theo zone nhưng test chỉ đưa một instance trong danh sách, khiến quy tắc fallback khi zone rỗng không được kiểm chứng.
Nhóm kiểm thử retry sang instance khác bằng HTTP GET nhưng không thử POST có side effect, khiến lỗi xử lý trùng chỉ xuất hiện trong những giao dịch thanh toán.
Đội QA chạy smoke test bằng cách gọi trực tiếp IP của service thay vì gọi tên logic qua DiscoveryClient, khiến lỗi registry và load balancing không làm pipeline đỏ.
Một hệ thống có hai phiên bản API cùng service ID nhưng contract test chỉ kiểm tra phiên bản mới, khiến caller chọn instance cũ vẫn gặp lỗi schema trong rolling deployment.
Nhóm kiểm thử scale down khi không có request đang chạy, nhưng chưa mô phỏng streaming hoặc transaction kéo dài nên không biết thời gian drain phù hợp.
Đội tạo synthetic check cho mỗi service bằng một request qua gateway, nhưng tuyến gateway có cache riêng khiến kết quả không phản ánh instance mà các worker nội bộ đang chọn.
Một service dùng Consul ACL token lấy từ secret manager nhưng test chỉ chạy với token toàn quyền, khiến lỗi phân quyền trong production không được phát hiện.
Nhóm phát hiện service discovery thất bại ngẫu nhiên trên CI do test server dùng cổng cố định, nhưng kết quả bị gộp với assertion nghiệp vụ khiến khó tìm nguyên nhân.
Một bài test Spring Cloud LoadBalancer được chạy ở môi trường không có actuator health endpoints, khiến nhà phát triển chỉ thử trên danh sách instance thủ công và bỏ sót health filtering.
Đội benchmark discovery lookup khi registry khỏe nhưng không thử latency khi mạng giữa client và registry bị chập chờn, khiến SLO gọi API không được đánh giá đầy đủ.
Nhóm triển khai hợp đồng test cho Consul tags nhưng không kiểm tra trường hợp metadata bị thiếu, khiến phiên bản canary được chọn sai khi service mới gia nhập catalog.
Một ứng dụng đăng ký và deregister ở integration test nhưng không dọn trạng thái registry giữa các case, khiến kết quả phụ thuộc thứ tự chạy và xuất hiện instance ảo.
Đội cấu hình metrics cho Eureka client nhưng không theo dõi số lần heartbeat thất bại, khiến instance biến mất khỏi registry trước khi hệ thống phát cảnh báo.
Nhóm chỉ quan sát số instance đăng ký trên Eureka dashboard mà không đo xác suất gọi được endpoint thật, khiến sự cố mạng một chiều bị đánh giá là hệ thống khỏe.
Một service dùng Consul blocking query để cập nhật danh sách instance nhưng telemetry không ghi index và độ tuổi dữ liệu, khiến đội trực không phát hiện client đang dùng snapshot cũ.
Đội tổng hợp traffic theo service ID mà không gắn instance ID, zone và version, khiến khi một node hỏng không biết những request lỗi đã được LoadBalancer gửi đến đâu.
Ứng dụng gọi payment-service qua WebClient có load balancing nhưng trace chỉ ghi tên service logic, không lưu endpoint đích, khiến điều tra lỗi theo từng pod rất khó.
Nhóm theo dõi latency tổng của API nhưng không tách thời gian lookup instance, connect và xử lý downstream, khiến lỗi registry chậm bị nhầm với lỗi nghiệp vụ.
Một dashboard báo tổng số instance Eureka tăng sau deploy, nhưng không phân biệt bản ghi đang sống với bản ghi hết lease đang chờ dọn, khiến đánh giá năng lực phục vụ bị sai.
Đội đặt alert khi số Consul services healthy giảm về không, nhưng một service quan trọng còn một instance không đủ tải cũng không tạo cảnh báo sớm.
Một hệ thống phát cảnh báo registry mất kết nối từ từng pod riêng lẻ, nhưng không nhóm theo vùng nên cùng một sự cố mạng tạo hàng trăm ticket trùng.
Nhóm đo tỷ lệ retry HTTP giữa các instance mà không theo dõi yêu cầu gốc, khiến báo cáo số giao dịch lớn hơn số lượng khách thực sự đã gửi.
Một service giữ Eureka client cache khi offline nhưng không ghi độ tuổi cuối cùng được cập nhật, khiến sau sự cố không thể xác định nó đã dùng dữ liệu registry cũ bao lâu.
Đội cần audit ai đã thay đổi Consul service tags trong production, nhưng công cụ vận hành không nối được ACL identity với bản ghi metadata bị sửa.
Một hệ thống đo số HTTP request nhận được của từng instance nhưng không ghi thời điểm deregistration, khiến không xác định được traffic tới node sau khi operator đặt maintenance.
Nhóm triển khai discovery cho nhiều tenant nhưng không phân biệt tenant trong service metadata, khiến telemetry không giải thích được vì sao tenant A đôi lúc đi vào backend của tenant B.
Một ứng dụng có health endpoint báo UP nhưng dữ liệu của một registry peer đã lỗi thời; dashboard chỉ thu health JVM nên không phát hiện sự khác biệt giữa peer snapshots.
Đội giám sát lỗi connection refused trên client nhưng không liên kết với sự kiện scale down của Kubernetes và registry, khiến các lỗi ngắn trong deployment bị xem là ngẫu nhiên.
Một tổ chức cần đối soát thời điểm instance được đăng ký, chuyển trạng thái, nhận request và ngừng hoạt động, nhưng các hệ thống Eureka, Consul và gateway không có correlation ID chung.
Một đợt sự cố Consul server quorum làm registration mới thất bại trong khi các client vẫn dùng danh sách cache; nhóm điều hành không có dấu hiệu phân biệt lỗi control plane và data plane.
Đội muốn đánh giá rủi ro chuyển dịch vụ từ Eureka sang Consul nhưng thử nghiệm mới chỉ đo tốc độ lookup, chưa xét sự khác biệt lease, check và thời gian loại instance hỏng.
Một hệ thống chuyển Eureka service names sang Consul với quy ước dấu gạch nối khác, khiến các HTTP clients không cùng tìm được một tên dịch vụ logic sau migration.
Nhóm triển khai đa vùng với Eureka cho Java services và Consul cho hạ tầng nền, nhưng không có mapping chính thức giữa tên và zone khiến route dự phòng bị lệch.
Một service kết nối registry thành công nhưng cache List<ServiceInstance> bị cập nhật đồng thời không an toàn, khiến thỉnh thoảng danh sách trả về thiếu các instance vốn đang khỏe.
Đội thay cấu hình ServiceRegistry bằng feature flag khi rollout nhưng chưa xác định cách xử lý bản ghi ở registry cũ, khiến một số caller tiếp tục chọn endpoint không còn được quản lý.
Một hệ thống xử lý dữ liệu cá nhân theo khu vực sử dụng service discovery chung nhưng quy tắc load balancing không ràng buộc vùng lưu trữ, khiến request nhạy cảm đi qua zone ngoài chính sách.
Nhóm xây quy trình disaster recovery dựa trên registry dự phòng nhưng chưa mô phỏng việc chỉ một phần client chuyển registry, khiến sau failover traffic bị chia theo những danh sách instance khác nhau.
