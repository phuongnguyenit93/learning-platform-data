Một dịch vụ đặt hàng chạy trên Kubernetes sử dụng Spring Cloud Kubernetes DiscoveryClient để tìm service thanh toán, nhưng khi Pod thanh toán khởi động lại lời gọi vẫn trỏ tới địa chỉ không còn tiếp nhận kết nối.
Một ứng dụng được triển khai ở namespace bán hàng nhưng DiscoveryClient chỉ truy vấn namespace mặc định, khiến service kho đang hoạt động ở namespace khác không xuất hiện trong danh sách instance.
Một nhóm đổi tên Kubernetes Service từ inventory-api sang inventory-v2, nhưng client vẫn tìm theo service ID cũ nên quy trình kiểm tồn đột ngột không có đích gọi.
Một hệ thống có hai Kubernetes Service cùng tên ở hai namespace, khiến ứng dụng sử dụng cơ chế khám phá đa namespace chọn nhầm instance thuộc môi trường thử nghiệm.
Một dịch vụ có Deployment ba replica nhưng chỉ một Pod đạt readiness, khiến danh sách endpoint có thể gọi ít hơn số Pod mà đội vận hành nhìn thấy trên dashboard.
Một ứng dụng truy vấn Kubernetes Service qua DiscoveryClient, nhưng Service không có selector phù hợp với nhãn Pod khiến kết quả khám phá không có endpoint khả dụng.
Một nhóm thay đổi nhãn app của các Pod trong Deployment mà quên cập nhật selector của Service, khiến client nhận danh sách instance rỗng dù tất cả Pod đang chạy.
Một API sử dụng Service có nhiều cổng đặt tên khác nhau, nhưng client chọn sai cổng quản trị thay cho cổng nghiệp vụ khi dựng URL từ thông tin khám phá.
Một hệ thống chạy Service chỉ công bố cổng HTTPS, nhưng metadata trả về không đủ để client xác định scheme phù hợp và các lời gọi bị từ chối khi kết nối.
Một ứng dụng dùng tên Service dạng ngắn ở một namespace, nhưng khi chuyển client sang namespace khác tên DNS và quy tắc discovery không còn trỏ tới cùng đối tượng.
Một nhóm thêm quyền khám phá tất cả namespace để giải quyết lỗi không tìm thấy service, nhưng phạm vi này cho phép workload liệt kê nhiều dịch vụ ngoài nhu cầu nghiệp vụ.
Một dịch vụ sử dụng Kubernetes API để tìm các endpoint, nhưng NetworkPolicy chỉ cho phép kết nối đến cổng ứng dụng và chặn đường tới API server từ Pod.
Một ứng dụng hoạt động khi gọi trực tiếp DNS của Kubernetes Service nhưng lỗi khi dùng DiscoveryClient, khiến đội vận hành khó phân biệt sự cố API discovery với sự cố mạng tới backend.
Một nhóm bật discovery trong môi trường không chạy trên Kubernetes, khiến Spring Boot tạo client tới API server không tồn tại và quá trình khởi động có lỗi không cần thiết.
Một ứng dụng chuyển từ registry truyền thống sang Kubernetes DiscoveryClient nhưng vẫn giữ logic lấy metadata của registry cũ, khiến việc phân nhóm instance theo vùng hoạt động sai.
Một hệ thống có Service kiểu headless để truy cập từng Pod, nhưng client giả định luôn có một virtual IP và tạo đường gọi không phù hợp với cách endpoint được công bố.
Một nhóm lưu kết quả DiscoveryClient trong cache tự viết quá lâu, khiến Pod đã bị scale down vẫn được chọn khi xử lý request ở giờ cao điểm.
Một dịch vụ theo dõi số lượng replica bằng DiscoveryClient, nhưng bản ghi endpoint đang thay đổi trong lúc rolling deployment làm số liệu dao động khác với số Pod thực tế.
Một ứng dụng truy vấn service ở nhiều namespace theo nhãn môi trường, nhưng chính sách phân quyền chỉ cho phép đọc tài nguyên trong namespace đang chạy nên thiếu một phần kết quả.
Một nhóm kỳ vọng mọi Pod có trạng thái Running đều là đích hợp lệ, nhưng readiness probe của một Pod còn thất bại do chưa tải xong dữ liệu tham chiếu.
Một dịch vụ đọc tên Pod từ metadata của ServiceInstance để ghi log, nhưng một dạng endpoint không cung cấp thông tin Pod như dự kiến khiến bộ phân tích log thiếu định danh node.
Một ứng dụng sử dụng DiscoveryClient trên cluster có nhiều service nội bộ, nhưng mỗi request làm mới danh sách bằng lời gọi API riêng khiến API server chịu tải lớn khi traffic tăng.
Một nhóm dùng Kubernetes Endpoints trong một adapter cũ, nhưng cluster chuyển sang cơ chế EndpointSlice và cấu hình quyền hiện tại không cho phép đọc dữ liệu endpoint được cần tới.
Một hệ thống nhiều vùng duy trì cùng tên Kubernetes Service nhưng client chỉ nhìn thấy đối tượng trong cluster hiện tại, khiến ứng dụng không tìm được instance dự phòng ở cluster khác.
Một ứng dụng thấy Kubernetes Service có ClusterIP hợp lệ nhưng không có backend ready, khiến truy vấn DNS thành công còn request HTTP vẫn thất bại vì không có endpoint phục vụ.
Một nhóm áp dụng @LoadBalanced cho RestTemplate gọi tên logic của service, nhưng một nơi khác tạo RestTemplate thủ công nên cùng URL hoạt động ở service này mà lỗi ở service khác.
Một dịch vụ dùng WebClient.Builder được cấu hình load balancing, nhưng một worker nền lại inject builder mặc định khiến lời gọi qua service ID bị hiểu như tên host DNS thông thường.
Một ứng dụng có cả Kubernetes Service load balancing và Spring Cloud LoadBalancer, nhưng đội triển khai không phân biệt hai lần lựa chọn đích khi phân tích độ trễ.
Một nhóm mở rộng dịch vụ sản phẩm lên mười Pod, nhưng cache instance phía Spring Cloud LoadBalancer còn dữ liệu cũ nên các Pod mới gần như không nhận traffic.
Một hệ thống có nhiều backend không đồng đều về CPU, nhưng bộ chọn instance phân phối đều nên các Pod nhỏ liên tục chạm giới hạn tài nguyên.
Một ứng dụng muốn ưu tiên vùng khả dụng gần nhất, nhưng metadata zone không được cung cấp nhất quán giữa Pod và consumer khiến request đi qua liên vùng.
Một nhóm dùng load-balanced RestClient để gọi Service nội bộ qua HTTPS, nhưng certificate do service mesh cung cấp không phù hợp với hostname mà client dùng để kiểm tra danh tính.
Một dịch vụ cần gọi endpoint theo service ID qua gateway nội bộ, nhưng load balancing trực tiếp tới Pod bỏ qua một số chính sách xác thực và định tuyến đặt ở gateway.
Một ứng dụng có hai cổng HTTP và gRPC trên cùng Service, nhưng load balancer chọn instance không kèm cổng giao thức đúng làm các lời gọi gRPC thất bại.
Một nhóm sử dụng cache danh sách endpoint với TTL ngắn trên hàng trăm replica, khiến số truy vấn tới Kubernetes API tăng mạnh trong đợt kiểm thử tải.
Một hệ thống triển khai canary bằng hai Deployment có chung Service, nhưng caller kỳ vọng chỉ chọn Pod bản stable trong khi selector vẫn bao gồm cả canary.
Một ứng dụng cần duy trì phiên trên cùng node, nhưng cơ chế chọn instance mới ở mỗi request làm dữ liệu phiên lưu cục bộ không còn truy cập được.
Một nhóm xử lý HTTP 503 bằng retry tới instance khác, nhưng API tạo giao dịch đã có thể ghi thành công trước lúc client nhận timeout nên nguy cơ ghi trùng tăng.
Một dịch vụ có retry ở Spring Cloud LoadBalancer và retry ở SDK, khiến một lần gọi nghiệp vụ có số attempt thực tế lớn hơn giới hạn mà đội vận hành đang theo dõi.
Một ứng dụng dùng service discovery để gọi các Pod của một API nhạy cảm, nhưng token được chuyển tiếp nguyên trạng tới mọi instance mà không xét ranh giới tin cậy giữa các namespace.
Một nhóm muốn gọi service ở namespace khác bằng đường dẫn logic, nhưng tên service trùng ở namespace hiện tại khiến client gọi vào API không đúng hợp đồng.
Một hệ thống chạy Spring Cloud LoadBalancer nhưng service đích bị scale về không, khiến caller liên tục nhận không có instance và tầng controller trả lỗi chung không giải thích nguyên nhân.
Một ứng dụng ghi metric theo tên service logic nhưng không ghi Pod hoặc instance được chọn, khiến một backend lỗi riêng lẻ không thể được khoanh vùng từ số liệu tổng.
Một nhóm chuyển từ gọi qua Kubernetes Service DNS sang gọi trực tiếp Pod do discovery trả về, khiến chính sách mạng và hành vi phân phối lưu lượng thay đổi ngoài dự kiến.
Một client lấy danh sách Pod trực tiếp thay vì endpoint ready của Service, khiến request tới Pod mới trước khi readiness hoàn thành bị lỗi và làm circuit breaker mở sớm.
Một ứng dụng muốn loại Pod sắp bị terminate khỏi lựa chọn đích, nhưng dữ liệu endpoint của client cập nhật chậm hơn quá trình graceful shutdown.
Một nhóm gắn thông tin phiên bản vào nhãn Pod để chọn instance, nhưng một Deployment chưa cập nhật nhãn khiến request tương thích phiên bản mới bị gửi tới backend cũ.
Một dịch vụ tăng replica khi CPU cao, nhưng danh sách đích của load balancer không được đồng bộ đủ nhanh nên các request tiếp tục quá tải trên một số Pod cũ.
Một ứng dụng dùng ConfigMap để truyền cấu hình HTTP timeout, nhưng nhóm vận hành đổi giá trị trên cluster rồi kỳ vọng tất cả bean đã khởi tạo tự nhận timeout mới.
Một nhóm mount ConfigMap thành volume nhưng ứng dụng chỉ đọc file tại startup, khiến nội dung file trên Pod thay đổi mà HTTP client vẫn dùng giá trị ban đầu.
Một dịch vụ lấy biến môi trường từ ConfigMap, nhưng sau khi ConfigMap được cập nhật Pod đang chạy vẫn giữ giá trị môi trường cũ và xử lý theo chính sách trước đó.
Một ứng dụng có ConfigMap chứa nhiều tệp cấu hình nhưng tên tệp không khớp đường dẫn Spring Boot dự kiến, khiến chỉ cấu hình mặc định trong jar có hiệu lực.
Một nhóm dùng Spring Cloud Kubernetes Config để đọc key từ ConfigMap bằng Kubernetes API, nhưng ServiceAccount của Pod không có quyền get tài nguyên nên ứng dụng lỗi lúc startup.
Một hệ thống lưu ConfigMap cùng tên ở hai namespace, nhưng ứng dụng cấu hình nguồn sai namespace nên nạp tham số kết nối của môi trường khác.
Một dịch vụ đọc cấu hình từ nhiều ConfigMap với các key trùng nhau, khiến giá trị cuối cùng phụ thuộc vào thứ tự nguồn mà nhóm triển khai chưa kiểm soát.
Một ứng dụng dùng Config Data import cho nguồn Kubernetes nhưng dependency cấu hình tương ứng không có trong artifact production, khiến giá trị remote không được nạp.
Một nhóm triển khai ConfigMap bằng Helm chart với dấu thụt lề YAML sai, khiến một số giá trị cấu hình được mount thành chuỗi không thể binding vào đối tượng Spring.
Một hệ thống thay đổi tên ConfigMap giữa hai bản release, nhưng cấu hình nguồn của ứng dụng vẫn trỏ tới tên cũ khiến một số Pod mới không thể khởi động.
Một ứng dụng chứa key application.yaml trong ConfigMap nhưng parser cấu hình không xử lý đúng định dạng kỳ vọng, khiến trường lồng nhau không xuất hiện trong Environment.
Một nhóm lấy cấu hình qua Kubernetes API và đồng thời mount cùng ConfigMap dưới dạng file, khiến hai đường đọc có thời điểm cập nhật khác nhau và thông số vận hành bị lệch.
Một dịch vụ triển khai nhiều profile dùng chung ConfigMap, nhưng profile production chưa được kích hoạt trên một nhóm Pod nên timeout mặc định được sử dụng.
Một ứng dụng dùng tên service để xác định ConfigMap cần nạp, nhưng metadata spring.application.name thay đổi khi refactor khiến cấu hình của bản triển khai cũ không còn khớp.
Một nhóm thêm property tùy chọn vào ConfigMap nhưng một bản Spring Boot cũ chưa biết key mới, khiến các instance cùng deployment có hành vi khác nhau sau rolling update.
Một hệ thống chỉnh ConfigMap trực tiếp bằng kubectl để xử lý sự cố, nhưng lần triển khai GitOps sau hoàn nguyên giá trị và đội trực không biết vì sao cấu hình đổi lại.
Một ứng dụng cấu hình số lượng worker từ ConfigMap theo giá trị vượt tài nguyên thực tế của Pod, khiến service khởi động được nhưng cạn thread ở giờ cao điểm.
Một nhóm dùng ConfigMap chứa hàng trăm khóa môi trường, nhưng đội vận hành không lưu phiên bản cấu hình đã được từng Pod sử dụng nên rất khó điều tra sai lệch hành vi.
Một hệ thống truyền URL dịch vụ ngoài qua ConfigMap nhưng NetworkPolicy của namespace không cho phép kết nối đích mới, khiến ứng dụng nhận cấu hình hợp lệ mà vẫn không gọi được.
Một ứng dụng dùng Spring Cloud Kubernetes đọc ConfigMap bằng API trong cluster, nhưng khi chạy local với kubeconfig của kỹ sư lại lấy dữ liệu production ngoài ý muốn.
Một nhóm cấu hình nguồn Kubernetes là optional để tiện phát triển, nhưng production vẫn khởi động bằng default khi ConfigMap bắt buộc bị xóa và trả kết quả sai nghiệp vụ.
Một dịch vụ sử dụng ConfigMap làm feature flags cho nhiều API, nhưng đội triển khai thay một key giữa lúc traffic cao khiến các Pod xử lý request với hai bộ quy tắc khác nhau.
Một ứng dụng gắn @ConfigurationProperties cho thông tin lưu trữ trong ConfigMap, nhưng dữ liệu thay đổi không hợp lệ làm lỗi binding chỉ lộ khi bean được tạo lại.
Một nhóm lưu tham số quan trọng trong ConfigMap rồi expose Environment endpoint để điều tra, khiến thông tin cấu hình nội bộ xuất hiện cho tài khoản không cần xem.
Một hệ thống đổi port của dịch vụ ngoài trong ConfigMap nhưng Kubernetes Service vẫn sử dụng targetPort cũ, khiến ứng dụng và cấu hình định tuyến không tương thích.
Một ứng dụng lưu credential của database trong Kubernetes Secret nhưng log tại startup vẫn in toàn bộ property đã binding, khiến bí mật bị gửi tới hệ thống log chung.
Một nhóm đặt Secret dưới dạng biến môi trường rồi xoay vòng mật khẩu, nhưng tiến trình Spring Boot hiện tại vẫn sử dụng credential cũ cho đến khi có vòng đời thay đổi phù hợp.
Một dịch vụ mount Secret thành volume và đọc certificate khi tạo HTTP client, nhưng sau khi Secret được cập nhật kết nối TLS vẫn dùng vật liệu khóa đã tải lúc đầu.
Một ứng dụng có nhiều namespace chia sẻ Secret cùng tên, nhưng cấu hình sai namespace khiến client tới hệ thống ngoài bị xác thực bằng tài khoản khác.
Một nhóm bật Spring Cloud Kubernetes Secrets API access để đọc token nhưng ServiceAccount thiếu quyền đọc secrets, khiến startup thất bại với lỗi forbidden.
Một hệ thống cấp quyền list mọi Secret trong cluster cho workload chỉ cần một credential, khiến phạm vi lộ dữ liệu lớn hơn yêu cầu thực tế.
Một dịch vụ sử dụng Secret chứa chuỗi base64 nhưng đội phát triển nhầm phần biểu diễn này là cơ chế mã hóa bảo vệ, khiến việc lưu và trao đổi Secret không tuân thủ chính sách an toàn.
Một ứng dụng cập nhật Secret bằng cách tạo đối tượng tên mới nhưng Deployment vẫn tham chiếu tên trước đó, khiến các Pod mới tiếp tục nhận dữ liệu xác thực đã bị thu hồi.
Một nhóm đưa nội dung Secret vào thông báo lỗi khi kết nối database thất bại, khiến secret bị lộ qua log truy cập được bởi nhiều người vận hành.
Một hệ thống chỉ cho phép đọc Secret tại namespace hiện tại, nhưng ứng dụng cố khám phá và nạp Secret từ namespace khác khiến lỗi quyền xuất hiện khi cấu hình được nạp.
Một ứng dụng có cấu hình fallback khi thiếu Secret, nhưng fallback dùng credential dùng chung không được phép sử dụng trong production.
Một nhóm dùng tài khoản mặc định của namespace để đọc Secret, nhưng sau khi chính sách cluster được siết chặt quyền broad access bị thu hồi và ứng dụng không thể khởi động.
Một dịch vụ lấy token từ Secret qua cấu hình Spring, nhưng refresh kích hoạt trong lúc request đang chạy khiến một số request dùng token cũ và số khác dùng token mới.
Một ứng dụng sử dụng Secret làm truststore TLS nhưng giá trị file được cập nhật trong volume, trong khi SSL context đã tạo trước đó không tự phản ánh chứng chỉ mới.
Một nhóm lưu cả API key và URL công khai trong cùng Secret, khiến việc xoay vòng credential đồng thời kích hoạt làm mới thông số không nhạy cảm mà nhiều service cùng dùng.
Một hệ thống cung cấp Secret qua environment từ Kubernetes, nhưng khi Secret bị xóa Pod đang chạy vẫn giữ giá trị cũ và đội hỗ trợ nhầm rằng dữ liệu đã biến mất khỏi tiến trình.
Một ứng dụng dùng volume mount Secret qua subPath, khiến đội vận hành kỳ vọng nội dung mount sẽ tự thay đổi cùng Secret nhưng bản Pod hiện tại không phản ánh cập nhật.
Một nhóm vận hành cho phép nhiều workload dùng cùng ServiceAccount có quyền đọc Secret, khiến khó biết ứng dụng nào đã truy cập dữ liệu nhạy cảm sau sự cố.
Một dịch vụ có secret key chứa ký tự đặc biệt, nhưng cách parse property khi đóng gói cấu hình bị thay đổi khiến chuỗi kết nối database không còn hợp lệ.
Một ứng dụng kéo Secret bằng Kubernetes API lúc startup, nhưng API server tạm không khả dụng khiến service không thể khởi động dù credential đã được mount sẵn.
Một nhóm đưa Secret vào annotation trên Pod để theo dõi phiên bản, nhưng annotation có dữ liệu nhạy cảm và được phép đọc rộng hơn chính Secret gốc.
Một hệ thống có hai phiên bản Secret trong rollout nhưng chỉ một số replica cập nhật, khiến request qua load balancer đôi lúc xác thực thành công và đôi lúc thất bại.
Một ứng dụng cần lấy certificate từ Secret nhưng file được mount với quyền truy cập không phù hợp với UID của container, khiến tạo SSL context thất bại khi khởi động.
Một nhóm thay đổi quyền truy cập Secret để giảm rủi ro, nhưng không kiểm tra các service thực sự sử dụng chung Secret khiến một tính năng phụ thất bại sau deploy.
Một hệ thống bật tính năng config reload cho thông tin từ Secret nhưng không quản lý thời điểm hủy client cũ, khiến pool kết nối tiếp tục giữ credential đã xoay.
Một đội vận hành dùng Configuration Watcher để theo dõi thay đổi ConfigMap, nhưng ConfigMap chưa được gắn nhãn hoặc cấu hình theo phạm vi watch nên không có sự kiện làm mới tới ứng dụng.
Một ứng dụng chỉnh ConfigMap và quan sát file trong container đã đổi, nhưng Spring bean giữ giá trị cũ vì không có cơ chế refresh ứng dụng tương ứng.
Một nhóm triển khai Spring Cloud Kubernetes Configuration Watcher như thành phần riêng, nhưng Watcher không thể gọi management endpoint của service nên thay đổi nguồn không đến được instance.
Một dịch vụ expose endpoint refresh trên cổng quản trị riêng nhưng Watcher gửi yêu cầu tới cổng nghiệp vụ, khiến mỗi thông báo cập nhật nhận lỗi không tìm thấy đường dẫn.
Một nhóm bật Configuration Watcher cho nhiều namespace nhưng ServiceAccount của Watcher chỉ có quyền watch ConfigMap trong một namespace, khiến cập nhật ở các namespace còn lại bị bỏ qua.
Một ứng dụng nhận refresh từ Watcher nhưng bean tạo tại startup không dùng cơ chế hỗ trợ refresh, khiến HTTP client vẫn giữ timeout cũ dù Environment đã thay đổi.
Một hệ thống cập nhật ConfigMap hàng loạt trong một đợt deploy, khiến Watcher phát nhiều thông báo và các instance tạo lại bean tốn tài nguyên nhiều lần liên tiếp.
Một nhóm triển khai Watcher ở hai replica để tăng khả dụng, nhưng hai Watcher cùng xử lý một thay đổi và gây nhiều lần refresh trùng nhau cho cùng service.
Một dịch vụ cần cập nhật thuộc tính kết nối database không gián đoạn, nhưng lần refresh làm client đang xử lý transaction và client mới cùng tồn tại ngoài kỳ vọng của đội vận hành.
Một ứng dụng đánh dấu Secret vừa được xoay vòng nhưng Watcher hiện chỉ theo dõi thay đổi ConfigMap, khiến token trong Spring context không được làm mới.
Một nhóm dùng cơ chế gửi thông báo refresh qua Spring Cloud Bus, nhưng ứng dụng nhận không đúng event và không cập nhật bean dù message broker báo đã chuyển tin.
Một hệ thống dựa vào Watcher để cập nhật một cluster lớn, nhưng NetworkPolicy chặn đường từ Watcher tới endpoint quản trị của các Pod nên một số service không nhận lệnh.
Một ứng dụng được triển khai qua Service có nhiều Pod, nhưng Watcher gọi một URL chung và chỉ một replica nhận yêu cầu refresh trong khi các replica khác giữ cấu hình cũ.
Một nhóm dùng nhãn của ConfigMap để chọn ứng dụng cần refresh, nhưng nhãn trỏ tới service khác khiến thay đổi nhạy cảm được thông báo sai đối tượng.
Một hệ thống nâng cấp Spring Cloud Kubernetes và đổi cách cấu hình Watcher, khiến manifest cũ vẫn triển khai thành công nhưng sự kiện không còn kích hoạt refresh.
Một ứng dụng có ConfigMap được chỉnh liên tục bởi bộ điều khiển GitOps, khiến Watcher tạo các đợt refresh lặp lại dù giá trị nghiệp vụ không thực sự đổi.
Một nhóm cấp quyền watch Secret cho Watcher mà không giới hạn namespace, khiến controller có thể quan sát thay đổi của những secret không thuộc nhóm ứng dụng cần quản lý.
Một dịch vụ có @RefreshScope cho bean kết nối ngoài, nhưng refresh làm hủy tài nguyên trong khi lời gọi vẫn đang thực thi và lỗi chỉ xuất hiện dưới tải cao.
Một ứng dụng nhận sự kiện refresh khi Kubernetes API đang gặp lỗi tạm, khiến bước lấy cấu hình mới thất bại và đội vận hành không biết bean đang giữ phiên bản nào.
Một nhóm dùng Configuration Watcher với cơ chế delay gộp sự kiện, nhưng đội vận hành kỳ vọng config áp dụng tức thì và báo sự cố do hai Pod khác nhau tạm dùng giá trị khác nhau.
Một hệ thống thay ConfigMap và Secret gần cùng thời điểm, khiến hai sự kiện refresh đến lệch nhau và một số bean tạm được tạo bằng cặp credential và endpoint không tương thích.
Một ứng dụng ghi log lệnh refresh nhưng không lưu phiên bản resourceVersion của ConfigMap, khiến hậu kiểm không xác định được phiên bản cấu hình nào đang áp dụng.
Một nhóm cho phép người dùng không thuộc đội vận hành gọi management refresh endpoint, khiến việc tạo lại các bean có thể bị kích hoạt ngoài quy trình thay đổi đã phê duyệt.
Một hệ thống giám sát chỉ đếm số sự kiện watcher nhận mà không đo số instance đã áp dụng thành công, khiến dashboard báo đã cập nhật dù phần lớn Pod vẫn giữ giá trị cũ.
Một ứng dụng chạy native image được đội vận hành kỳ vọng hỗ trợ cùng cơ chế refresh runtime như JVM, nhưng vòng đời bean và giới hạn AOT làm giả định đó không phù hợp.
Một dịch vụ được triển khai với ServiceAccount mặc định không có quyền list services, khiến DiscoveryClient trả lỗi forbidden trong khi DNS Service vẫn phân giải bình thường.
Một nhóm cấp quyền get ConfigMap nhưng quên list và watch cần cho cơ chế theo dõi biến động, khiến việc nạp cấu hình lúc startup thành công còn cập nhật động thất bại.
Một ứng dụng được phép xem Service trong namespace của mình, nhưng DiscoveryClient cấu hình tìm nhiều namespace khiến yêu cầu API tới namespace khác trả HTTP 403.
Một nhóm dùng ClusterRole có quyền đọc tất cả secrets chỉ để hỗ trợ một ứng dụng, khiến việc kiểm tra bảo mật phát hiện đặc quyền vượt nhu cầu truy cập.
Một hệ thống đặt RoleBinding tại namespace staging trong khi Pod chạy ở namespace production, khiến các lệnh đọc Kubernetes API bị từ chối dù Role đã được định nghĩa.
Một ứng dụng dùng một ServiceAccount tên shared cho cả discovery, config và quản trị, khiến khó tách quyền từng chức năng khi cần thu hồi đường đọc secrets.
Một nhóm tắt tự động mount ServiceAccount token để giảm rủi ro, nhưng code vẫn dựa vào token trong cluster để gọi Kubernetes API và thất bại khi startup.
Một dịch vụ có token ServiceAccount được cấp theo cơ chế ngắn hạn, nhưng client Kubernetes tùy biến giữ credential tĩnh nên sau khi token được thay thế các request API bắt đầu bị từ chối.
Một ứng dụng chạy ở cluster được cấu hình RBAC nghiêm ngặt, nhưng bộ manifest thử nghiệm không có Role cho endpoints hoặc endpoint slices khiến discovery không tìm được Pod đích.
Một nhóm tăng quyền cho service account sau khi gặp HTTP 403 nhưng không phân tích verb và resource bị từ chối, khiến workload nhận quyền tạo hoặc xóa tài nguyên không cần thiết.
Một hệ thống có Role cho secrets tại namespace A nhưng Secret nằm ở namespace B, khiến team mất thời gian tìm lỗi nội dung Secret thay vì kiểm tra phạm vi cấp quyền.
Một ứng dụng thay Kubernetes ServiceAccount trong Deployment nhưng Pod hiện tại vẫn dùng danh tính cũ, khiến quyền mới chỉ có hiệu lực khi Pod được thay thế theo rollout.
Một nhóm tạo RoleBinding với subject sai namespace, khiến ServiceAccount có cùng tên ở namespace khác nhận được cấu hình không tương ứng với Pod cần chạy.
Một hệ thống dùng permission list pods để hỗ trợ discovery nhưng log debug in toàn bộ danh sách nhãn và annotation, khiến thông tin nội bộ bị thu thập nhiều hơn dự kiến.
Một ứng dụng chạy dưới service mesh có quyền gọi API server nhưng sidecar chặn đường kết nối, khiến lỗi phát sinh ở proxy trong khi audit RBAC không cho thấy từ chối.
Một nhóm dùng kubeconfig cá nhân có quyền cluster-admin khi chạy local, khiến tính năng đọc Secret hoạt động trong test nhưng thất bại dưới ServiceAccount hạn chế ở production.
Một dịch vụ có quyền watch ConfigMap nhưng Kubernetes API báo quá nhiều request do informer được khởi tạo cho từng bean, khiến hệ thống điều khiển chịu tải lớn bất thường.
Một ứng dụng quan sát lỗi 403 từ watcher nhưng bộ theo dõi log gộp với lỗi ConfigMap không tồn tại, khiến đội trực điều tra sai nguồn sự cố.
Một nhóm muốn giảm quyền read pod details cho service nhưng DiscoveryClient đang dựa vào metadata nhãn Pod, khiến sau khi thu hồi quyền cơ chế chọn instance theo vùng suy giảm.
Một hệ thống cho phép workload đọc Service ở nhiều namespace nhưng NetworkPolicy vẫn ngăn kết nối tới backend, khiến việc discover thành công bị hiểu nhầm là đường giao tiếp đã sẵn sàng.
Một ứng dụng có ClusterRoleBinding mở rộng cho toàn cluster nhưng nhóm không đặt cơ chế kiểm tra khi bổ sung namespace mới, khiến workload bắt đầu nhìn thấy service nhạy cảm không mong muốn.
Một nhóm dùng cùng ServiceAccount cho ứng dụng và Configuration Watcher, khiến khi Watcher bị xâm nhập kẻ tấn công có thể sử dụng quyền đọc dữ liệu của ứng dụng.
Một hệ thống áp chính sách không cấp quyền secrets API nhưng dùng Secret qua volume mount, khiến một thư viện mới tự bật đường đọc API và làm ứng dụng lỗi sau nâng cấp dependency.
Một ứng dụng được cấu hình chỉ dùng Kubernetes DNS nhưng starter cloud discovery vẫn bật và yêu cầu quyền API, khiến manifest phải xin thêm quyền dù chức năng không cần.
Một nhóm chuyển workload sang namespace khác mà không chuyển RoleBinding tương ứng, khiến Pod ở namespace mới vẫn Running nhưng ứng dụng không nạp được cấu hình động.
Một dịch vụ tăng số Pod khi tải lớn, nhưng Pod mới đạt Running trước readiness và Service vẫn chưa đưa chúng vào tập endpoint có thể nhận traffic.
Một ứng dụng đặt liveness probe phụ thuộc vào API đối tác, khiến khi đối tác mất kết nối Kubernetes liên tục restart Pod mặc dù JVM và các chức năng khác vẫn hoạt động.
Một nhóm dùng chung endpoint health cho readiness và liveness, khiến sự cố Config Server hoặc database ngắn hạn dẫn đến cả việc ngừng nhận traffic lẫn restart không cần thiết.
Một hệ thống nâng số lượng replica nhưng startup probe chưa phù hợp với thời gian khởi tạo, khiến những Pod tải dữ liệu chậm bị kill trước khi đạt readiness.
Một ứng dụng có Spring Boot Actuator health UP nhưng Kubernetes readiness thất bại do probe gọi sai management port, khiến Service không có endpoint ready.
Một nhóm cấu hình readiness probe trỏ tới đường dẫn không tồn tại sau khi đổi context path, khiến tất cả Pod hoạt động nhưng load balancer không có backend khả dụng.
Một dịch vụ có readiness báo thành công trước khi hoàn tất đồng bộ cache, khiến request tới Pod mới nhận dữ liệu thiếu trong giai đoạn rollout.
Một ứng dụng bắt đầu graceful shutdown nhưng load balancer vẫn giữ Pod trong cache endpoint ngắn hạn, khiến một số lời gọi vẫn tới instance đã ngừng xử lý.
Một nhóm dùng PodDisruptionBudget và rolling update để giữ tính sẵn sàng, nhưng Service có quá ít Pod ready khi một instance không tải được Secret mới.
Một hệ thống coi trạng thái Pod Running là bằng chứng ứng dụng đã đăng ký với discovery, nhưng cổng HTTP chưa bind và caller gặp connection refused khi gọi.
Một dịch vụ dùng health indicator gọi Kubernetes API mỗi giây, khiến khi API server chậm endpoint health cũng chậm và probe thất bại theo dây chuyền.
Một ứng dụng thay đổi readiness dựa trên khả năng truy cập registry, nhưng vẫn có dữ liệu cache và phục vụ các chức năng nội bộ không cần discovery nên nhiều Pod bị loại khỏi traffic hơn cần thiết.
Một nhóm dùng EndpointSlice để quan sát địa chỉ backend nhưng không ghi trạng thái ready và terminating, khiến bảng điều khiển hiển thị các Pod sắp rời cụm như vẫn có thể nhận request.
Một hệ thống có Service selector đúng nhưng targetPort trỏ sai cổng container, khiến readiness của Pod thành công còn request từ caller tới Service vẫn thất bại.
Một dịch vụ chạy ở hai availability zones nhưng phần lớn Pod ready nằm cùng một zone, khiến khi zone đó gặp sự cố hệ thống mất phần lớn năng lực phục vụ.
Một nhóm xem Kubernetes Event về Pod restart nhưng không liên kết với metric lỗi DiscoveryClient, khiến sự cố định tuyến theo service ID bị chẩn đoán thành lỗi nghiệp vụ.
Một ứng dụng bảo vệ chức năng chính bằng readiness nhưng dependency phụ chậm, khiến endpoint tổng hợp không còn sẵn sàng dù phần quan trọng vẫn hoạt động.
Một nhóm cấu hình HPA dựa trên CPU nhưng hệ thống thực bị nghẽn trong HTTP connection pool, khiến scale-out không cải thiện latency dù số replica tăng.
Một ứng dụng chạy thành công trên minikube với quyền ServiceAccount rộng, nhưng triển khai lên cluster tổ chức có RBAC nghiêm ngặt thì cấu hình và discovery bị từ chối.
Một nhóm kiểm thử DiscoveryClient với một Kubernetes Service duy nhất, nhưng không mô phỏng namespace trùng tên nên lỗi chọn service sai môi trường không xuất hiện.
Một ứng dụng test cấu hình bằng file application.yml thay vì nguồn ConfigMap thật, khiến lỗi key và thứ tự property source chỉ xuất hiện khi Pod chạy trên cluster.
Một nhóm thử refresh bằng thay trực tiếp field trong bean, nhưng không phát sự kiện và không kiểm tra Watcher nên lỗi tự cập nhật cấu hình không được phát hiện.
Một dịch vụ kiểm thử với Secret được đưa qua biến môi trường, nhưng production dùng API đọc Secret nên lỗi RBAC và quyền truy cập không có trong phạm vi test.
Một nhóm kiểm thử load-balanced WebClient với instance mock luôn khỏe, khiến tình huống endpoint biến mất sau rolling update chưa được xác minh.
Một ứng dụng dùng Testcontainers để chạy dịch vụ phụ thuộc nhưng không có Kubernetes API giả lập phù hợp, khiến bài test không kiểm tra được phần discovery trong cluster.
Một nhóm dùng bản manifest test có quyền cluster-admin, khiến suite pass dù ServiceAccount sản xuất không đủ quyền get ConfigMap hoặc list Services.
Một dịch vụ kiểm thử cập nhật ConfigMap bằng cách restart Pod, khiến khả năng refresh không cần restart vẫn chưa được đánh giá trước khi phát hành.
Một nhóm chỉ kiểm tra Secret có thể được mount, nhưng chưa kiểm thử quá trình xoay vòng khi application đã giữ TLS context cũ trong bộ nhớ.
Một hệ thống kiểm thử Watcher với một ConfigMap thay đổi đơn lẻ, nhưng chưa thử hai cập nhật gần nhau làm nhiều instance nhận các sự kiện theo thứ tự khác nhau.
Một ứng dụng chạy bài test gọi Kubernetes Service trực tiếp bằng DNS, nhưng production dùng Spring Cloud LoadBalancer nên lỗi cấu hình client được load balance bị bỏ qua.
Một nhóm kiểm thử request HTTP thành công mà không xác minh instance được chọn, khiến lỗi canary phân phối traffic tới Pod sai version không bị phát hiện.
Một dịch vụ có kịch bản nhiều namespace trong production, nhưng QA chỉ chạy một namespace và không thử RoleBinding cũng như quyền cross-namespace.
Một nhóm dùng health check giả lập luôn thành công, khiến lỗi readiness trong giai đoạn khởi động chậm không xuất hiện khi chạy CI.
Một ứng dụng kiểm thử Pod shutdown bằng cách kết thúc ngay tiến trình, khiến các request đang bay và vấn đề deregistration khỏi Service không được đánh giá.
Một nhóm đo thời gian startup trên laptop nhưng không tính thời gian đọc ConfigMap/Secret qua API server khi cluster tải lớn, khiến dự toán readiness không đúng.
Một dịch vụ thử thay ConfigMap khi có một replica, nhưng khi tăng lên nhiều replica watcher chỉ refresh một nhóm instance và suite không phát hiện sự khác biệt cấu hình.
Một nhóm benchmark service discovery chỉ trên dữ liệu registry tĩnh, khiến chi phí watch/list các tài nguyên Kubernetes dưới tải autoscaling không được đo trước release.
Một ứng dụng có regression test cho Cloud Kubernetes nhưng không khóa tổ hợp version Spring Boot và Spring Cloud, khiến việc nâng starter làm thay đổi cách cấu hình mà test không dự báo.
Một nhóm chỉ kiểm thử chức năng với discovery được bật, nhưng không thử phương án tắt starter và dùng DNS thuần khiến ứng dụng không chạy được ở môi trường hạn chế RBAC.
Một dịch vụ ghi metric tên Pod làm nhãn cho mọi request, khiến số series tăng nhanh khi autoscaling liên tục tạo và xóa instance.
Một nhóm dashboard dựa vào số Pod Running thay vì số endpoint ready, khiến tình trạng không có backend phục vụ bị che bởi số replica mong muốn vẫn đủ.
Một ứng dụng theo dõi số lượt refresh của Watcher nhưng không ghi phiên bản ConfigMap đã áp dụng, khiến điều tra sai lệch cấu hình giữa các Pod không có bằng chứng.
Một nhóm bật log DEBUG cho Kubernetes API client nhưng log chứa metadata Secret và URL nội bộ, khiến dữ liệu nhạy cảm bị gửi tới hệ thống thu thập chung.
Một dịch vụ gọi Kubernetes API quá thường xuyên để list Services, khiến API server trả throttling và độ trễ khám phá tăng đúng lúc cluster mở rộng nhanh.
Một nhóm chạy Configuration Watcher trong một namespace nhưng dashboard chỉ hiển thị tổng số sự kiện toàn cluster, khiến thay đổi bị bỏ lỡ của một ứng dụng cụ thể không được phát hiện.
Một hệ thống muốn theo dõi tỷ lệ HTTP 503 do Service không có endpoint ready, nhưng log caller chỉ ghi tên service logic mà không ghi namespace và thời điểm lựa chọn đích.
Một ứng dụng bị lỗi kết nối sau rolling update nhưng trace không có thông tin instance được chọn, khiến việc xác định Pod cũ hay Pod mới gây lỗi rất tốn thời gian.
Một nhóm mở rộng quyền RBAC sau nhiều lỗi forbidden nhưng không lưu bằng chứng resource/verb cần truy cập, khiến về sau không thể đánh giá quyền thừa trong ServiceAccount.
Một dịch vụ triển khai ở nhiều cluster với cùng cấu hình Spring Cloud Kubernetes, nhưng sự khác biệt phiên bản Kubernetes API và chính sách RBAC làm số liệu lỗi chỉ tăng ở một cluster.
Một nhóm chỉ theo dõi độ trễ request HTTP mà không tách thời gian load-balanced discovery, khiến khi API server chậm đội vận hành chẩn đoán sai là backend nghiệp vụ chậm.
Một ứng dụng thay đổi ConfigMap để giảm timeout trong sự cố, nhưng không liên kết sự kiện refresh với metric timeout nên không biết lần điều chỉnh nào thực sự có hiệu lực.
Một nhóm thu thập Kubernetes Events nhưng không liên kết với log Spring Cloud LoadBalancer, khiến khi một Pod bị evict đội trực không hiểu vì sao tỷ lệ gọi thất bại tăng.
Một dịch vụ có cấu hình liveness và readiness khác nhau giữa các namespace, nhưng dashboard không lưu phiên bản manifest nên kết quả deploy giống nhau vẫn có tỷ lệ restart khác nhau.
Một nhóm phải giảm chi phí vận hành cho một API đơn giản nhưng vẫn bật cả discovery API, ConfigMap watcher và load balancer trong khi chỉ cần DNS Service và cấu hình tĩnh.
Một ứng dụng không có nhu cầu thay cấu hình runtime nhưng vẫn cấp quyền watch Secret, khiến phạm vi đặc quyền vượt nhu cầu thực và khó đáp ứng kiểm toán.
Một nhóm bật Kubernetes discovery cho mọi client HTTP theo starter chung, khiến các lời gọi ra Internet bị xử lý như service ID nội bộ và thất bại trên một số môi trường.
Một dịch vụ chỉ dùng Kubernetes Secret qua file mount nhưng vẫn cài module đọc Secret API, khiến lỗi quyền truy cập mới xuất hiện sau khi nâng cấp Spring Cloud Kubernetes.
Một hệ thống sử dụng service mesh để định tuyến và retry nhưng còn bật retry của Spring Cloud LoadBalancer, khiến số lần gọi thực tế tới backend lớn hơn mức dự toán.
Một ứng dụng sử dụng cả ConfigMap, Secret và nguồn cấu hình từ xa nhưng chưa định nghĩa thứ tự ưu tiên rõ ràng, khiến khi thay profile các Pod nạp giá trị khác mong đợi.
Một nhóm đặt ServiceAccount khác nhau cho controller watcher và workload ứng dụng, nhưng bộ tài liệu triển khai chỉ mô tả một tập quyền chung khiến khi tách namespace hệ thống không khởi động được.
Một dịch vụ chuyển từ cluster phát triển sang production có chính sách không cho truy cập Kubernetes API, khiến đội cần đánh giá lại tính năng Spring Cloud Kubernetes nào thực sự đang được sử dụng.
