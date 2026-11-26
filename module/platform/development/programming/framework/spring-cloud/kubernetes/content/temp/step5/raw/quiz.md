Câu 1. Khi nào Spring Cloud Kubernetes DiscoveryClient đem lại lợi ích rõ nhất?
A. Khi ứng dụng chỉ gọi Kubernetes Service bằng tên DNS ổn định
B. Khi Pod chỉ cần nhận ConfigMap làm biến môi trường lúc startup
C. Khi client gọi ClusterIP mà không cần biết từng backend Pod
D. Khi ứng dụng cần lấy danh sách instance qua abstraction Spring
Đáp án đúng: D

Câu 2. Nếu chỉ gọi http://orders qua Kubernetes Service DNS, nhận định nào hợp lý?
A. Phải gọi API Kubernetes để phân giải từng HTTP request
B. Cần tạo một ConfigMap mới cho mỗi instance đích
C. Phải cài Spring Cloud Config Server để định tuyến
D. Có thể dùng Service DNS, không bắt buộc dùng DiscoveryClient
Đáp án đúng: D

Câu 3. Trong Kubernetes, Service khác Pod chủ yếu ở điểm nào?
A. Service cung cấp điểm truy cập ổn định tới nhóm Pod phù hợp
B. Service chứa trực tiếp một container và image chạy nghiệp vụ
C. Pod phân phối request tới các Pod khác dựa vào selector
D. Pod cung cấp virtual IP cố định bất kể lần triển khai
Đáp án đúng: A

Câu 4. Kubernetes EndpointSlice thường hỗ trợ lưu thông tin nào cho Service?
A. Các property cấu hình JVM được lưu qua Spring Environment
B. Các endpoint mạng được dùng để định tuyến tới workload
C. Các tên release train tương thích với Spring Cloud
D. Các phiên bản Secret đã đọc bởi Configuration Watcher
Đáp án đúng: B

Câu 5. Kubernetes Service chọn Pod backend thường dựa trên điều gì?
A. Tên bean @Service của Spring khớp tên Kubernetes Service
B. Tên ConfigMap khớp với image của container trong Pod
C. Port của Service trùng tên namespace trong Deployment
D. Label selector của Service khớp label trên Pod mục tiêu
Đáp án đúng: D

Câu 6. Khi một Pod được thay mới nhưng Service vẫn giữ nguyên, client nên dựa vào gì?
A. IP của Pod cũ vì được Kubernetes giữ qua mọi restart
B. Tên ReplicaSet cũ để tạo kết nối trực tiếp tới node
C. Dùng tên Service ổn định khi địa chỉ IP Pod thay đổi
D. Tên container trong image để tìm địa chỉ IP mới
Đáp án đúng: C

Câu 7. DiscoveryClient.getInstances("payment") trong môi trường Kubernetes dùng để làm gì?
A. Lấy các instance của service payment qua discovery
B. Đọc nội dung Secret mang tên payment từ namespace hiện hành
C. Lấy danh sách mọi bean @Service trong ApplicationContext
D. Trả lịch sử Pod restart của ứng dụng payment
Đáp án đúng: A

Câu 8. Địa chỉ orders.sales.svc.cluster.local thường mô tả gì trong DNS Kubernetes?
A. Pod orders thuộc Deployment sales trong namespace mặc định
B. Service orders thuộc namespace sales trong cluster
C. ConfigMap orders chứa cấu hình của registry sales
D. Node orders cung cấp API server cho namespace sales
Đáp án đúng: B

Câu 9. Khi service ở namespace khác, cách tham chiếu DNS nào đáng cân nhắc?
A. Dùng trực tiếp tên Pod vì DNS Service không phân biệt namespace
B. Sử dụng tên Service kèm namespace phù hợp cấu hình cluster
C. Dùng tên Java package làm suffix của hostname Kubernetes
D. Đổi spring.application.name thành địa chỉ của kube-apiserver
Đáp án đúng: B

Câu 10. Trong Pod, danh tính nào thường được dùng để gọi Kubernetes API?
A. Tên Deployment được dùng như bearer token cho mọi request
B. Tên cluster DNS được dùng làm credential của API server
C. Tên Spring ApplicationContext được gửi làm Kubernetes user
D. ServiceAccount gắn với Pod cùng thông tin xác thực phù hợp
Đáp án đúng: D

Câu 11. Để cho Pod xem Service trong một namespace với quyền tối thiểu, giải pháp nào phù hợp?
A. Gán cluster-admin cho ServiceAccount để tránh lỗi discovery
B. Cấp Role và RoleBinding theo resource, verb cần thiết
C. Đưa mật khẩu kubeconfig của quản trị viên vào ConfigMap
D. Bật NodePort cho mọi Service để bỏ kiểm soát quyền
Đáp án đúng: B

Câu 12. Khi DiscoveryClient phải theo dõi thay đổi danh sách Service, quyền API nào thường liên quan?
A. Các verb create, patch, delete trên toàn bộ Pod và node
B. Các verb bind, escalate trên mọi cluster-wide role
C. Các verb get, list, watch trên tài nguyên cần truy cập
D. Các verb exec, attach trên container của dịch vụ đích
Đáp án đúng: C

Câu 13. Khi client Kubernetes nhận HTTP 403 lúc liệt kê Service, nên kiểm tra gì?
A. Chỉ tăng timeout vì 403 phản ánh mạng bị nghẽn
B. Kiểm tra RBAC và namespace của ServiceAccount
C. Chỉ thay port của Kubernetes Service mục tiêu
D. Chỉ tăng replica để API server tự cấp thêm quyền
Đáp án đúng: B

Câu 14. Khi client tìm ConfigMap nhưng API trả 404, giả thuyết nào cần kiểm tra trước?
A. Tên resource hoặc namespace có thể không khớp
B. RoleBinding chắc chắn bị thiếu quyền watch tài nguyên
C. Spring Cloud BOM chắc chắn không tương thích với Boot
D. LoadBalancer chắc chắn đã loại toàn bộ Pod backend
Đáp án đúng: A

Câu 15. Để đọc resource ở namespace khác, cần lưu ý điều gì?
A. Role ở namespace nguồn tự cấp quyền cho mọi namespace
B. Chỉ thay profile Spring thì API quyền truy cập sẽ mở
C. Định phạm vi truy vấn và cấp RBAC ở namespace cần đọc
D. Dùng tên Service ngắn là đủ để vượt phạm vi namespace
Đáp án đúng: C

Câu 16. Loại dữ liệu nào phù hợp để lưu trong Kubernetes ConfigMap?
A. Mật khẩu database cần giới hạn người có quyền đọc
B. Khóa riêng TLS phục vụ ký token xác thực
C. Cấu hình không nhạy cảm như feature flag và ngưỡng
D. Access token production dùng đăng nhập registry
Đáp án đúng: C

Câu 17. Kubernetes Secret phù hợp hơn ConfigMap trong tình huống nào?
A. Lưu tên public endpoint để mọi Pod đọc không hạn chế
B. Lưu ngưỡng logging không có dữ liệu bí mật
C. Lưu tên profile mặc định trong cấu hình triển khai
D. Credentials cần kiểm soát người được quyền đọc
Đáp án đúng: D

Câu 18. Vì sao không nên coi dữ liệu Secret dạng base64 là đã được mã hóa an toàn?
A. Base64 là encoding; cần bảo vệ RBAC và cơ chế lưu trữ
B. Base64 bảo đảm mã hóa Secret trong etcd theo mặc định
C. Base64 giới hạn người đọc Secret mà không cần RBAC
D. Base64 thay thế bước mã hóa khi sao lưu Secret ra ngoài
Đáp án đúng: A

Câu 19. Với ConfigMap được đưa vào Pod dưới dạng environment variables, thay đổi ConfigMap có tác dụng gì?
A. Mọi bean Spring tự đọc lại biến mới sau mỗi HTTP request
B. Biến môi trường process không đổi khi ConfigMap cập nhật
C. Kubelet luôn sửa trực tiếp environment của process Java
D. Pod tự khởi động lại ngay khi API nhận ConfigMap mới
Đáp án đúng: B

Câu 20. Khi ConfigMap được mount thành volume thông thường, nhận định nào phù hợp?
A. Mọi property @Value của singleton tự đổi ngay khi file thay
B. Mọi container nhận event trực tiếp vào từng field Java
C. File được cập nhật dần nhưng ứng dụng vẫn cần đọc lại
D. Volume mount luôn buộc Deployment rollout phiên bản mới
Đáp án đúng: C

Câu 21. Vì sao mount một key ConfigMap bằng subPath cần lưu ý khi muốn cập nhật?
A. subPath tự gửi sự kiện refresh đến mọi Spring bean
B. subPath cập nhật nhanh hơn mount toàn bộ ConfigMap
C. Mount subPath không nhận cập nhật volume tự động
D. subPath làm ConfigMap trở thành Kubernetes Secret
Đáp án đúng: C

Câu 22. Nếu ứng dụng đọc ConfigMap trực tiếp qua Kubernetes API, yêu cầu quyền nào phù hợp?
A. Cấp quyền cập nhật tất cả Deployment để đọc ConfigMap
B. Cấp quyền tạo ServiceAccount mới mỗi khi đọc thuộc tính
C. Cấp quyền xóa Pod để làm mới cấu hình client
D. Chỉ cấp quyền đọc tài nguyên cần thiết trong namespace
Đáp án đúng: D

Câu 23. Pod nhận Secret qua volume do Kubernetes quản lý có nhất thiết cần quyền API đọc Secret trực tiếp không?
A. Có; ứng dụng phải có cluster-admin cho Secret volume
B. Không; mount volume khác việc ứng dụng gọi API Secret
C. Có; mọi mount buộc cấp verb watch trên tất cả Secret
D. Không; vì RBAC của Kubernetes bị tắt khi Pod có volume
Đáp án đúng: B

Câu 24. Khi có cùng key trong nhiều nguồn property Spring, yếu tố nào quyết định giá trị được dùng?
A. Thứ tự ưu tiên PropertySource và cấu hình môi trường
B. ConfigMap có tên ngắn nhất luôn thắng các source khác
C. Secret luôn thắng command-line property trong mọi trường hợp
D. Bean nào inject key đầu tiên quyết định giá trị chung
Đáp án đúng: A

Câu 25. Để tránh lộ Secret trong quá trình chẩn đoán, hành động nào phù hợp?
A. In toàn bộ Environment vào log INFO sau mỗi refresh
B. Giới hạn log và che giá trị khi kiểm tra cấu hình
C. Gắn token vào tag Micrometer để truy ra Pod sử dụng
D. Gửi Secret tới health endpoint để so sánh phiên bản
Đáp án đúng: B

Câu 26. Nếu ứng dụng chỉ cần ConfigMap qua volume và Kubernetes DNS, nên cân nhắc gì với starter Cloud?
A. Cài toàn bộ starter discovery và watcher để dùng DNS
B. Bắt buộc bật Secret API client để đọc mounted ConfigMap
C. Chỉ thêm tính năng Spring Cloud Kubernetes khi thật sự cần
D. Dùng Config Server từ xa để kích hoạt Kubernetes Service
Đáp án đúng: C

Câu 27. Configuration Watcher trong Spring Cloud Kubernetes phục vụ mục tiêu nào?
A. Theo dõi cập nhật và phát tín hiệu refresh khi được cấu hình
B. Tự triển khai ConfigMap thành Docker image mới ở mọi cluster
C. Thay ReplicaSet controller để cập nhật số lượng Pod
D. Trực tiếp thay đổi biến môi trường của Java process đang chạy
Đáp án đúng: A

Câu 28. Khi triển khai Configuration Watcher, cần phân biệt trách nhiệm nào?
A. Watcher tự sửa mọi bean singleton dù chúng không refreshable
B. Watcher phát sự kiện; ứng dụng cần cơ chế reload riêng
C. Watcher tự khởi động lại JVM cho mỗi thay đổi Secret
D. Watcher tự tạo ClusterRoleBinding với quyền admin mặc định
Đáp án đúng: B

Câu 29. Vì Configuration Watcher dùng API theo dõi cấu hình, quyền nào là phù hợp?
A. Cấp get, list, watch cho namespace và resource cần xem
B. Chỉ cấp exec vào Pod của ứng dụng đích để đọc biến JVM
C. Cấp delete Deployment để cập nhật property từ ConfigMap
D. Chỉ cấp quyền đọc HTTP metrics thay cho Kubernetes API
Đáp án đúng: A

Câu 30. Khi chỉ muốn Watcher xử lý một số ConfigMap, nên làm gì?
A. Theo dõi mọi Secret ở toàn cluster rồi bỏ qua bằng log filter
B. Dùng tên Java class để Kubernetes tự lọc sự kiện API
C. Cấu hình phạm vi theo namespace, nhãn và quy ước được hỗ trợ
D. Tạo một Namespace riêng cho mỗi key trong ConfigMap
Đáp án đúng: C

Câu 31. Khi ứng dụng nhận tín hiệu refresh, nhận định nào đúng về singleton thông thường?
A. Singleton không tự tái tạo hay inject lại các field cấu hình
B. Singleton được tạo lại ngay khi Environment thay đổi
C. Singleton được proxy hóa mặc định như bean @RefreshScope
D. Singleton được đóng ngay khi Watcher quan sát Secret mới
Đáp án đúng: A

Câu 32. @RefreshScope có thể giúp bean cấu hình được cập nhật theo cách nào?
A. Sửa trực tiếp field final trên bean hiện tại bằng reflection
B. Buộc Kubernetes tạo Pod mới trước khi gọi phương thức bean
C. Đồng bộ giá trị config vào tất cả replica không cần tín hiệu
D. Tạo lại target bean khi scope bị refresh và được truy cập
Đáp án đúng: D

Câu 33. Khi một thay đổi đụng tới tham số chỉ đọc ở lúc khởi động, hướng xử lý nào đáng cân nhắc?
A. Chỉ tăng polling interval để mọi resource tự khởi tạo lại
B. Đổi Service selector để property mới được JVM biên dịch
C. Rollout hoặc restart Pod khi config chỉ đọc lúc khởi động
D. Chỉ bật liveness probe để thay thế mọi cơ chế rollout
Đáp án đúng: C

Câu 34. Khi ứng dụng có nhiều replica, cập nhật ConfigMap nên kiểm chứng điều gì?
A. Refresh một replica đồng nghĩa mọi replica đã cập nhật đồng thời
B. Service DNS tự đồng bộ mọi @Value của tất cả process Java
C. Chỉ cần Config Server ghi nhận một lần đọc thành công
D. Xác minh từng replica áp dụng phiên bản config mới
Đáp án đúng: D

Câu 35. Khi cần truy vết thay đổi cấu hình ở production, nên theo dõi gì?
A. Chỉ số lượng class trong image và số bean hiện có
B. Theo dõi lần sửa resource, lần reload và config version
C. Chỉ tổng số request HTTP của service từ lúc deploy
D. Chỉ số NodePort được cấp cho Kubernetes Service
Đáp án đúng: B

Câu 36. Readiness probe của Pod chủ yếu giúp Kubernetes quyết định điều gì?
A. Pod đã sẵn sàng nhận lưu lượng qua Service hay chưa
B. Pod có cần restart do deadlock của process hay không
C. Node nào phải nâng cấp kubelet ở lần rollout tiếp theo
D. ConfigMap nào cần chuyển đổi thành Secret để bảo mật
Đáp án đúng: A

Câu 37. Liveness probe thất bại liên tục thường dẫn tới hành động nào?
A. Kubernetes tự tăng replica mà không có controller
B. Kubelet khởi động lại container theo chính sách probe
C. ServiceAccount được cấp thêm quyền đọc Pod và Secret
D. Spring Cloud Watcher tự cập nhật dữ liệu trong ConfigMap
Đáp án đúng: B

Câu 38. Startup probe hỗ trợ ứng dụng khởi động chậm như thế nào?
A. Thay Service DNS bằng danh sách Pod IP tĩnh khi khởi động
B. Tự tăng mức log DEBUG cho toàn bộ package Spring
C. Cho thời gian startup trước khi liveness và readiness kiểm tra
D. Tắt vĩnh viễn health endpoint sau khi Pod trở thành Ready
Đáp án đúng: C

Câu 39. Để tận dụng Spring Boot Actuator cho Kubernetes probe, hướng nào phù hợp?
A. Dùng /actuator/beans cho mọi readiness và liveness check
B. Dùng /actuator/env để Kubernetes đọc tất cả Secret của app
C. Gắn health check vào ConfigMap thay vì HTTP endpoint
D. Bật health probe phù hợp và cấu hình endpoint được kiểm tra
Đáp án đúng: D

Câu 40. Vì sao không nên đưa mọi dịch vụ downstream tùy chọn vào liveness check?
A. Sự cố downstream có thể gây restart Pod không cần thiết
B. Liveness chỉ đọc Secret và không có hỗ trợ network check
C. Kubernetes mặc định bỏ qua mọi dependency health indicator
D. Service discovery chỉ hoạt động nếu liveness gọi downstream
Đáp án đúng: A

Câu 41. Pod chuyển sang NotReady ảnh hưởng thế nào tới Service routing thông thường?
A. Pod bị xóa vĩnh viễn khỏi Deployment và không thể trở lại
B. Service DNS sẽ đổi tên theo Pod đầu tiên còn sẵn sàng
C. Kubernetes cập nhật endpoint routing để loại Pod NotReady
D. Mọi client Spring tự chuyển sang Config Server dự phòng
Đáp án đúng: C

Câu 42. Kubernetes Service load balancing khác Spring Cloud LoadBalancer như thế nào?
A. Service chỉ phân giải Secret; Cloud LoadBalancer mở HTTP port
B. Service gọi trực tiếp Config Server; LoadBalancer theo dõi Pod log
C. Service tạo CircuitBreaker; Cloud LoadBalancer quản lý cluster DNS
D. Service phân phối ở hạ tầng; Cloud LoadBalancer chọn instance ở client
Đáp án đúng: D

Câu 43. Khi dùng @LoadBalanced WebClient với Spring Cloud Kubernetes, điều gì cần có?
A. Chỉ khai @RefreshScope lên WebClient.Builder là đủ để route
B. Mọi service bắt buộc dùng NodePort thay vì ClusterIP
C. WebClient phải gọi trực tiếp Pod IP và bỏ tên Service
D. Cần DiscoveryClient và LoadBalancer cho service ID
Đáp án đúng: D

Câu 44. Khi ứng dụng đã dùng Kubernetes Service DNS ổn định, lợi ích của client-side discovery cần đánh giá ra sao?
A. Mọi request đều phải truy vấn API Kubernetes mới gọi được
B. Bắt buộc có Spring Cloud LoadBalancer để dùng ClusterIP
C. Chỉ thêm nếu cần chính sách chọn instance phía client
D. Client-side discovery tự giải quyết lỗi readiness của Pod
Đáp án đúng: C

Câu 45. Khi discovery trả danh sách instance rỗng, logic gọi dịch vụ nên làm gì?
A. Xử lý trường hợp thiếu instance hoặc fallback an toàn
B. Tự chọn một Pod bất kỳ ở namespace khác để gửi request
C. Gửi yêu cầu vào một địa chỉ IP rỗng để chờ API server
D. Tự tạo Service trong Kubernetes khi chưa được cấp quyền
Đáp án đúng: A

Câu 46. Để tránh metric cardinality tăng quá nhanh, nhãn nào đáng dùng khi đo discovery?
A. UID của mọi Pod mới làm tên metric theo từng request
B. Token từ ServiceAccount để xác định từng request nội bộ
C. Tên Secret và giá trị credential làm nhãn telemetry
D. Dùng service ID, namespace ổn định làm metric tag
Đáp án đúng: D

Câu 47. Muốn kiểm thử logic ứng dụng mà không cần Kubernetes cluster thật, lựa chọn nào phù hợp?
A. Tắt mọi unit test vì phải có API server và ServiceAccount
B. Mock DiscoveryClient hay property source theo ca test
C. Chỉ dùng container production để xác nhận từng branch logic
D. Khởi tạo Pod thật cho mỗi assertion của unit test
Đáp án đúng: B

Câu 48. Để kiểm thử RBAC tối thiểu của watcher, xác nhận nào có ý nghĩa?
A. Xác minh watcher chỉ read/watch được resource cho phép
B. Watcher có thể tạo và xóa Pod ở mọi namespace cluster
C. Watcher truy cập được tất cả Secret dù chưa khai namespace
D. Pod ứng dụng có cluster-admin nên watcher tự có quyền
Đáp án đúng: A
