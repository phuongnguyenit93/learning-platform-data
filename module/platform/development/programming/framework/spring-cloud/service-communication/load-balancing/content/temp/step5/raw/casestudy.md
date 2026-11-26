Một dịch vụ đặt hàng dùng Spring Cloud LoadBalancer gọi inventory-service theo service ID, nhưng sau khi đổi tên registry entry các request đều không tìm được instance dù Pod kho vẫn hoạt động.
Một ứng dụng thanh toán dùng DiscoveryClient để lấy danh sách service instances, nhưng một namespace triển khai có service ID trùng với môi trường thử nghiệm khiến giao dịch đến nhầm backend.
Một nhóm chuyển từ URL cố định sang tên logic trong HTTP client, nhưng service đích chưa được đăng ký với discovery provider nên client không có địa chỉ thực để kết nối.
Một hệ thống có hai discovery providers cùng trả instance cho một service ID, nhưng thứ tự nguồn được ưu tiên thay đổi khi thêm starter và client bắt đầu chọn vùng không mong muốn.
Một ứng dụng đọc địa chỉ host từ ServiceInstance nhưng bỏ qua port do registry công bố, khiến lời gọi đến một endpoint quản trị không phục vụ nghiệp vụ.
Một dịch vụ nhận ServiceInstance có cờ secure nhưng tự ghép URL HTTP theo mặc định, khiến request đến backend chỉ hỗ trợ HTTPS bị từ chối.
Một nhóm dùng cùng service ID cho các API đọc và ghi với các implementation khác nhau, khiến bộ chọn instance phân phối lời gọi ghi tới node chỉ cho phép đọc.
Một ứng dụng tìm service theo tên viết hoa trong khi registry công bố tên khác kiểu chữ, khiến discovery trả danh sách rỗng trên một môi trường cụ thể.
Một nền tảng đa tenant có service ID tương tự nhau giữa các khu vực, nhưng bộ chọn đích không xét ranh giới tenant khiến request có thể tới instance ngoài phạm vi dữ liệu.
Một hệ thống triển khai service trên hai cụm Kubernetes, nhưng DiscoveryClient chỉ nhìn registry của cụm hiện tại nên giả định có thể failover sang cụm khác không đúng.
Một ứng dụng lấy danh sách instance từ SimpleDiscoveryClient ở local, nhưng bản production dùng registry động khiến các địa chỉ thay đổi nhanh hơn logic cache tự viết.
Một đội vận hành thấy service được đăng ký đầy đủ, nhưng DNS hostname trong ServiceInstance không thể phân giải từ mạng của consumer nên nhiều lời gọi lỗi trước khi kết nối.
Một ứng dụng chọn instance dựa trên metadata version của registry, nhưng vài node sau rolling deployment chưa cập nhật metadata nên client đưa payload mới tới backend cũ.
Một hệ thống có ServiceInstance với IP pod nội bộ, nhưng consumer chạy ngoài mạng cluster nên dù discovery thành công mọi yêu cầu kết nối đều bị chặn.
Một nhóm chuyển sang dùng reactive discovery cho một dịch vụ, nhưng một đường gọi đồng bộ vẫn dùng provider khác nên hai loại HTTP client nhìn thấy tập backend không giống nhau.
Một dịch vụ nhận danh sách instance đã đăng ký nhưng không biết instance nào đã sẵn sàng, khiến request đầu tiên sau deploy liên tục kết nối tới node chưa mở cổng.
Một hệ thống dùng danh sách backend tĩnh trong cấu hình để thay discovery khi offline, nhưng địa chỉ staging vẫn còn trong file production khiến một phần traffic rời khỏi mạng nội bộ.
Một ứng dụng tạo instance list supplier cho một service ID nhưng nhầm tên service trong cấu hình, khiến các request của chức năng tính phí tới hệ thống vận chuyển.
Một nhóm trông đợi ServiceInstance metadata chứa vùng triển khai, nhưng provider registry không công bố trường đó và bộ lọc theo zone loại nhầm mọi node.
Một hệ thống dùng chung tên service giữa hai hợp đồng API không tương thích, khiến load balancing có lúc trả đúng JSON và có lúc trả định dạng mà client không đọc được.
Một ứng dụng sử dụng RoundRobinLoadBalancer cho dịch vụ tra cứu hàng tồn, nhưng thứ tự instance thay đổi sau refresh danh sách khiến biểu đồ phân phối request không trùng lịch sử trước đó.
Một dịch vụ áp dụng random selection để tránh tập trung lưu lượng, nhưng đội hỗ trợ kỳ vọng lần gọi liên tiếp chắc chắn đi đến instance khác nên chẩn đoán sai lỗi lặp trên một node.
Một nhóm dùng round-robin cho hai Pod có CPU chênh lệch lớn, khiến Pod nhỏ thường xuyên quá tải dù số request phân phối gần bằng nhau.
Một hệ thống dùng weighted routing để ưu tiên backend cấu hình mạnh, nhưng metadata trọng số bị thiếu ở một subset instance và kết quả phân phối khác dự tính.
Một ứng dụng triển khai canary bản mới với trọng số thấp, nhưng một ServiceInstanceListSupplier không giữ metadata version nên yêu cầu vẫn vào canary nhiều hơn mục tiêu.
Một nhóm muốn giữ request của một khách trên cùng backend, nhưng rule round-robin phá vỡ session được lưu cục bộ ở instance đầu tiên.
Một dịch vụ có sticky session theo cookie nhưng trình duyệt không gửi cookie ở một số request cross-origin, khiến cùng người dùng bị chuyển giữa nhiều instance.
Một ứng dụng chọn backend bằng hash của customer ID nhưng mã khách đôi lúc vắng mặt, khiến những request không có ID tập trung vào cùng một node.
Một hệ thống định tuyến đọc tới zone gần nhất, nhưng một zone hết instance khỏe và rule hiện tại không có đích phù hợp, khiến chức năng đọc thất bại dù zone khác còn capacity.
Một nhóm cố định danh sách instance theo zone nhưng service đang được autoscale, khiến phần lớn Pod mới ở zone khác không nhận traffic.
Một ứng dụng muốn phân phối đều theo lưu lượng byte, nhưng thuật toán round-robin chỉ cân bằng số lời gọi và một node thường phải xử lý request kích thước rất lớn.
Một dịch vụ cung cấp API streaming kéo dài hàng phút, nhưng rule chọn instance chỉ đếm số lần mở kết nối khiến một số node giữ nhiều stream nặng hơn các node khác.
Một hệ thống chọn backend theo vùng dữ liệu người dùng, nhưng nhãn zone được khai báo cho vị trí máy chủ thay vì nơi lưu dữ liệu nên định tuyến liên vùng tăng độ trễ.
Một nhóm cài chính sách ưu tiên instance vừa được triển khai, nhưng Pod mới chưa làm nóng cache nên request đầu tiên có latency tăng đột biến.
Một ứng dụng có nhiều instance cùng hostname nhưng khác port, nhưng custom policy chỉ so hostname khiến một số instance không bao giờ được chọn.
Một dịch vụ muốn tránh gửi request vào node đang draining, nhưng trạng thái ngừng nhận kết nối không được truyền qua metadata của service discovery.
Một nhóm so sánh random và round-robin bằng một bộ test chỉ có hai request, khiến kết quả dao động bị hiểu nhầm là thuật toán cân bằng tải không đúng.
Một hệ thống dùng request hint để chọn khu vực dữ liệu, nhưng một interceptor khác không chuyển hint vào lời gọi HTTP client khiến policy sử dụng danh sách mặc định.
Một ứng dụng truyền tên tenant từ header người dùng vào routing policy mà không xác thực phạm vi tenant, khiến caller có thể yêu cầu route tới vùng dữ liệu khác.
Một nhóm thêm instance filter loại endpoint có version cũ, nhưng các backend trong đợt rolling update đều mang version cũ và bộ chọn không còn instance hợp lệ.
Một dịch vụ đổi chiến lược load balancing từ round-robin sang random sau nâng cấp, nhưng không lưu cấu hình chiến lược tại thời điểm lỗi khiến hậu kiểm không tái hiện được đường chọn đích.
Một hệ thống phân phối request qua Spring Cloud LoadBalancer và thêm lớp L7 load balancer bên ngoài, khiến một request có thể trải qua hai cơ chế chọn đích khác nhau.
Một ứng dụng có API đối tác chỉ cho phép số kết nối cố định trên mỗi instance, nhưng việc phân phối đều số request không giới hạn lượng kết nối đồng thời tới từng node.
Một nhóm muốn dùng healthy-instance preference nhưng chỉ dựa vào trạng thái đăng ký, khiến instance có health endpoint lỗi vẫn tiếp tục nhận traffic.
Một dịch vụ dùng HealthCheckServiceInstanceListSupplier để kiểm tra backend định kỳ, nhưng endpoint health có authentication và các lần kiểm tra nhận HTTP 401.
Một ứng dụng dùng health check URL chung cho mọi instance, nhưng vài phiên bản backend đặt endpoint quản trị ở path khác nên bị xem là không khỏe.
Một nhóm bật health check cho service ở port quản trị, nhưng thông tin ServiceInstance chỉ có port nghiệp vụ khiến probe đi sai đích và loại hết node.
Một hệ thống dùng health check HTTP tới từng instance, nhưng một backend yêu cầu TLS còn client probe dùng HTTP khiến danh sách đích khỏe trở nên rỗng.
Một ứng dụng coi mọi phản hồi 200 từ health endpoint là sẵn sàng, nhưng backend trả UP trước khi nạp đủ dữ liệu tham chiếu nên các request nghiệp vụ đầu tiên vẫn lỗi.
Một nhóm dùng health check phụ thuộc database không bắt buộc, khiến sự cố database phụ làm mọi instance bị loại dù một phần API vẫn có thể hoạt động.
Một hệ thống kiểm tra sức khỏe instance quá thường xuyên trên hàng trăm caller, khiến các backend chịu lượng health requests đáng kể ngoài traffic nghiệp vụ.
Một dịch vụ giảm tần suất health check để tiết kiệm tài nguyên, nhưng Pod đã mất kết nối vẫn ở danh sách instance hợp lệ nhiều phút sau sự cố.
Một nhóm có health check định kỳ hoạt động nhưng cache danh sách instance đặt bên ngoài lớp lọc, khiến kết quả kiểm tra khỏe không cập nhật đích được chọn như mong đợi.
Một ứng dụng thấy ServiceRegistry vẫn báo healthy nhưng lời gọi TCP bị NetworkPolicy chặn, khiến health thông qua metadata và khả năng kết nối thực tế mâu thuẫn.
Một hệ thống có hai vùng địa lý, nhưng health check chạy từ một zone không có đường mạng tới zone khác nên các backend vùng xa bị đánh dấu không thể dùng.
Một dịch vụ dùng health probe trỏ tới gateway thay vì instance được chọn, khiến gateway khỏe che giấu backend cụ thể đang hỏng.
Một nhóm nhận danh sách instance rỗng khi tất cả health probes lỗi, nhưng tầng controller không phân biệt mất khám phá với việc không còn đích khỏe.
Một ứng dụng sử dụng instance health kết hợp readiness Kubernetes, nhưng Pod đổi readiness chậm hơn trạng thái lỗi HTTP nên nhiều request vẫn tới Pod chưa sẵn sàng.
Một hệ thống có health endpoint phản hồi chậm trong giờ cao điểm, khiến bộ lọc nhầm backend đang bận nhưng còn dùng được thành instance chết.
Một dịch vụ chèn kiểm tra sức khỏe đòi đăng nhập bằng token, nhưng token probe đã hết hạn làm danh sách backend bị loại cùng lúc.
Một nhóm không phân biệt liveness và readiness của backend, khiến node đang khởi động vẫn được coi là phù hợp cho traffic chỉ vì JVM đang sống.
Một ứng dụng có vài instance bị lỗi theo kiểu chỉ một endpoint, nhưng health probe chỉ kiểm đường root nên chúng vẫn nhận các lời gọi vào chức năng bị hỏng.
Một hệ thống dùng cơ chế phát hiện instance khỏe trên một loại HTTP client, nhưng client khác không dùng cùng supplier và vẫn gửi request vào các node lỗi.
Một ứng dụng dùng CachingServiceInstanceListSupplier với TTL dài, khiến Pod vừa bị xóa vẫn được chọn dù registry đã loại bỏ nó khỏi danh sách.
Một nhóm đặt TTL cache instance rất ngắn trên vài trăm replica, khiến registry bị hỏi liên tục và discovery trở thành nút thắt trong đợt bán hàng cao điểm.
Một hệ thống có cache instance ở client và cache khác ở discovery provider, khiến khi backend chết hai lớp cache làm việc loại bỏ địa chỉ diễn ra muộn.
Một dịch vụ dùng hai lớp cache có cùng danh sách instance, nhưng đội vận hành chỉ chỉnh một TTL nên hành vi chọn đích khác xa thời gian mong đợi.
Một ứng dụng cho rằng danh sách từ ServiceInstanceListSupplier luôn được cập nhật tức thời, nhưng các lần yêu cầu gần nhau vẫn nhận một snapshot cũ từ cache.
Một nhóm triển khai scale-out nhanh với hai mươi instance mới, nhưng client giữ danh sách cũ nên khả năng mở rộng không cải thiện throughput như tính toán.
Một hệ thống service discovery bị gián đoạn vài phút, nhưng cache instance đã hết hạn làm client không có đích dù các backend cũ vẫn đang phục vụ.
Một ứng dụng nhận danh sách instance có thứ tự khác sau lần refresh, khiến báo cáo round-robin theo vị trí bị nhầm là có backend mới xuất hiện.
Một nhóm cache ServiceInstance cùng metadata credentials, nhưng token hoặc certificate của node được thay đổi mà client còn giữ dữ liệu đã cũ.
Một dịch vụ đổi cổng nội bộ sau deployment nhưng cache vẫn giữ port trước đó, khiến những request vào node mới bị connection refused.
Một hệ thống dùng endpoint list từ một zone duy nhất trong cache, khiến khi zone đó mất điện client không nhận ra instance còn khỏe ở zone dự phòng.
Một ứng dụng cấp instance supplier theo service ID động từ tham số request, khiến số lượng cache nội bộ tăng theo dữ liệu người dùng và tiêu thụ bộ nhớ lớn.
Một nhóm thay đổi danh sách backend tĩnh bằng cấu hình nhưng không tái tạo supplier, khiến client tiếp tục chọn các địa chỉ trước khi cập nhật.
Một dịch vụ dùng cơ chế refresh registry ở nhiều thread, nhưng policy tự viết giữ một danh sách mutable không đồng bộ khiến một số request gặp lỗi khi chọn instance.
Một hệ thống đặt TTL cache của load balancer thấp hơn refresh interval của discovery quá nhiều, khiến cache thường xuyên làm mới bằng cùng danh sách cũ mà không có lợi ích thực tế.
Một ứng dụng đặt circuit breaker ở ngoài load balancer theo service ID, khiến một instance lỗi liên tục làm ngắt mọi lời gọi tới cả các instance khỏe của cùng service.
Một nhóm gắn circuit breaker theo từng host nhưng host của Pod thay đổi nhanh, khiến số breaker được tạo liên tục và thống kê không đủ mẫu để bảo vệ ổn định.
Một dịch vụ dùng round-robin chọn các instance nhưng không có bulkhead cho downstream, khiến trước khi loại backend lỗi nhiều request vẫn chiếm hết connection pool.
Một ứng dụng có endpoint tải file nặng và endpoint đọc metadata nhẹ trên cùng service ID, khiến request nặng chiếm tài nguyên của instance mà hai chức năng cùng dùng.
Một hệ thống chỉ quan sát trạng thái health của load balancer ở production, nhưng một instance trả kết quả nghiệp vụ sai mà vẫn có HTTP 200 nên không được loại khỏi danh sách.
Một dịch vụ quản lý hàng tồn có hai replica chung database nhưng một replica mất quyền truy cập, khiến các request được load balance luân phiên thành công và thất bại.
Một nhóm muốn khoanh vùng node lỗi bằng metadata nhưng load balancer chỉ trả service ID cho log, khiến sự cố của một instance bị hiểu thành lỗi toàn bộ dịch vụ.
Một ứng dụng dùng RestClient.Builder được đánh dấu @LoadBalanced cho lời gọi nội bộ, nhưng component khác tự khởi tạo builder mới và tên service không còn được phân giải.
Một dịch vụ sử dụng RestClient với URL dạng tên logic nhưng chưa bật tích hợp load balancing cho client, khiến máy phát triển gọi được do DNS tĩnh còn production thất bại.
Một nhóm có hai RestClient.Builder dành cho internal và external calls, nhưng inject nhầm builder load balanced vào client internet khiến hostname ngoài bị xử lý như service ID.
Một hệ thống có interceptor đăng ký trên RestClient.Builder thông thường, nhưng RestClient nội bộ được tạo từ builder khác nên request thiếu trace header và timeout riêng.
Một ứng dụng truyền URI tuyệt đối tới RestClient load balanced nhưng lại đặt service ID trong metadata request khác, khiến đích cuối không đúng nhà cung cấp mà nhóm kỳ vọng.
Một dịch vụ dùng RestClient để gửi POST tạo đơn qua load balancer, nhưng lỗi đọc response xảy ra sau khi backend commit khiến retry sang instance khác có nguy cơ tạo đơn trùng.
Một nhóm chỉ cấu hình connect timeout của HTTP transport cho RestClient, khiến lời gọi đã kết nối nhưng đọc response chậm vẫn treo quá thời hạn nghiệp vụ.
Một ứng dụng quản lý tài khoản tạo RestClient với cấu hình xác thực trên builder mặc định, nhưng khi chuyển sang builder load balanced credentials không còn được gắn vào request.
Một dịch vụ có load balanced RestClient nhưng dùng endpoint path có context path khác nhau giữa các instance, khiến một phần request nhận HTTP 404 sau rolling deployment.
Một nhóm dùng RestClient cho lời gọi tới HTTPS backend, nhưng một instance có certificate khác hostname service ID khiến bước TLS handshake thất bại không đều.
Một ứng dụng nạp cấu hình baseUrl của RestClient từ ConfigMap, nhưng sau khi đổi service ID bean client vẫn dùng URI đã tạo lúc startup nên không chuyển đích.
Một dịch vụ muốn ghi request ID cho từng lần gọi RestClient nhưng interceptors bị sắp xếp khác trong hai builder, khiến các lần retry không có cùng định danh theo dõi.
Một nhóm đặt error handler của RestClient chuyển HTTP 429 thành exception, nhưng tầng retry coi đây là lỗi kết nối tức thời và gây thêm tải vào nhà cung cấp đang giới hạn lưu lượng.
Một hệ thống dùng RestClient lấy kết quả lớn về bộ nhớ rồi retry khi timeout, khiến các response body chưa đóng giữ connection trong pool lâu hơn dự tính.
Một ứng dụng tạo RestClient qua builder có khả năng quan sát, nhưng một nhánh chuyển sang client thủ công làm outbound spans biến mất khỏi trace phân tán.
Một dịch vụ nhập dữ liệu dùng RestClient gọi service ID với query parameters đặc biệt, nhưng URI được dựng sai khiến người dùng nhận kết quả lọc khác nhau trên các backend.
Một ứng dụng WebFlux inject WebClient.Builder có @LoadBalanced nhưng một luồng xử lý dùng WebClient.create trực tiếp, khiến một số request không tìm được service theo tên logic.
Một nhóm chuyển REST call sang WebClient trên Reactor nhưng dùng block trong event-loop thread, khiến toàn bộ API phản hồi chậm dù load balancer chọn backend khỏe.
Một hệ thống khởi tạo publisher từ WebClient một lần rồi subscribe hai lần, khiến cùng lời gọi GET được phát hai lần và load balancer có thể chọn hai instance khác nhau.
Một dịch vụ dùng WebClient nhận Flux sự kiện dài nhưng tầng timeout của client được cấu hình cho request-response ngắn, khiến stream hợp lệ bị ngắt theo chu kỳ.
Một ứng dụng gọi song song nhiều backend qua WebClient, nhưng một nhánh trả lỗi và zip kết thúc sớm làm các nhánh còn lại bị hủy ngoài dự kiến.
Một nhóm dùng onErrorResume trước tầng đo lỗi của WebClient, khiến backend HTTP 500 được chuyển thành dữ liệu mặc định và metric của call ra ngoài không phản ánh lỗi.
Một ứng dụng lưu thông tin tenant trong ThreadLocal khi gọi WebClient reactive, khiến sau khi pipeline chuyển scheduler một số request dùng sai tenant để chọn vùng backend.
Một dịch vụ tạo WebClient cho service nội bộ bằng builder có load balancing, nhưng một filter tự đổi URI thành IP cố định làm mất khả năng chọn instance theo discovery.
Một hệ thống có WebClient fallback trả Mono.empty khi không còn ServiceInstance, khiến controller hiểu nhầm đây là kết quả tìm kiếm rỗng thay vì sự cố giao tiếp.
Một nhóm retry Mono từ WebClient khi đọc response timeout, nhưng API bên ngoài đã xử lý POST trước đó và lần subscribe tiếp theo tạo thao tác trùng.
Một ứng dụng reactive dùng một instance list supplier đồng bộ chậm, khiến thao tác lấy danh sách trong đường reactive kéo dài và ảnh hưởng thread dùng cho request.
Một dịch vụ gọi WebClient qua tên service nhưng không truyền Reactor context vào observation, khiến log của các request retry mất trace ID gốc.
Một nhóm phát triển WebFlux chỉ kiểm tra onNext khi test client, khiến nhánh onError do load balancer không tìm được instance không được xác nhận.
Một ứng dụng dùng WebClient tới service có endpoint rất nhanh, nhưng mỗi request mất thời gian chọn instance vì tầng discovery bị gọi trực tiếp thay vì dùng dữ liệu đã có.
Một hệ thống ghép response từ hai WebClient load balanced khác nhau, nhưng lỗi của một service được catch như thành công và báo cáo thời gian xử lý tổng bị lệch.
Một dịch vụ dùng Spring Cloud OpenFeign gọi inventory-service theo tên logic, nhưng ứng dụng thiếu phần tích hợp load balancing và việc tạo client không tìm được đích như dự kiến.
Một nhóm cấu hình Feign client với URL cố định trong staging nhưng production muốn dùng service ID, khiến cùng interface Feign hoạt động theo hai mô hình định tuyến khác nhau.
Một ứng dụng có hai Feign clients cùng name nhưng trỏ hai nhóm backend khác nhau, khiến cấu hình client context hoặc tên nhận diện bị trùng và một client dùng nhầm tham số.
Một hệ thống đổi service ID của nhà cung cấp sau triển khai nhưng annotation khai báo Feign client vẫn chứa tên cũ, khiến mọi lời gọi tới provider mới thất bại.
Một nhóm dùng OpenFeign để đọc dữ liệu và nhận HTTP 404 hợp lệ, nhưng error decoder chuyển nó thành lỗi cần retry và làm tăng số request không cần thiết.
Một dịch vụ áp dụng retry riêng trong Feign client cùng retry ở Spring Cloud LoadBalancer, khiến một lời gọi lỗi có nhiều attempt hơn số team đã thống nhất.
Một ứng dụng dùng Feign gọi POST tạo hóa đơn nhưng không mang idempotency key qua lần retry, khiến timeout ở response có thể dẫn đến ghi trùng hóa đơn.
Một hệ thống có timeout Feign dài hơn deadline HTTP từ gateway, khiến các worker tiếp tục chờ backend sau khi người dùng đã nhận timeout ở phía trên.
Một nhóm thêm header Authorization bằng Feign RequestInterceptor nhưng một client dùng context cấu hình khác và không gắn token, khiến lỗi chỉ xảy ra ở một đường tích hợp.
Một ứng dụng dùng Feign decoder phụ thuộc định dạng JSON cụ thể, nhưng các instance của service đích chạy nhiều version trả field khác nhau và lỗi xảy ra không đều.
Một dịch vụ bật logging đầy đủ request/response Feign để điều tra, nhưng body chứa thông tin cá nhân và token được gửi nguyên vẹn lên hệ thống log chung.
Một nhóm đặt tên Feign client giống service ID nhưng config key trong file properties có khác biệt, khiến timeout cài riêng không được áp dụng ở production.
Một ứng dụng dùng OpenFeign từ tác vụ nền và HTTP client khác từ controller, nhưng hai đường gọi có timeout và retry không đồng nhất nên số liệu lỗi khó đối chiếu.
Một dịch vụ gọi service ID bằng OpenFeign nhưng fallback trả dữ liệu cache không có dấu thời điểm, khiến người dùng tưởng dữ liệu cũ là kết quả mới từ provider.
Một nhóm nâng Spring Cloud release train mà không xác minh tương thích Spring Cloud OpenFeign, khiến proxy client không được khởi tạo dù RestClient cùng service vẫn chạy.
Một ứng dụng để Feign exception handler che toàn bộ lỗi dưới một loại thông báo chung, khiến đội trực không phân biệt trường hợp discovery rỗng, connection refused và HTTP 503.
Một hệ thống chạy OpenFeign trong ứng dụng nhiều tenant nhưng header mang tenant ID được lấy từ một field mutable singleton, khiến các request đồng thời có thể gửi sai tenant.
Một nhóm dùng cấu hình path của Feign client trong giai đoạn chuyển API, nhưng chỉ một phần instance đã có endpoint mới khiến một số request nhận 404 sau load balancing.
Một ứng dụng bật metric riêng cho Feign nhưng không gắn thông tin service ID, khiến dashboard chỉ cho biết method Java lỗi mà không xác định được dependency nào gặp sự cố.
Một dịch vụ có OpenFeign client và WebClient cùng gọi một service, nhưng các chính sách chọn instance khác nhau làm một tập khách gặp lỗi mà tập khác vẫn thành công.
Một hệ thống cho phép retry các request GET khi instance mất kết nối, nhưng không giới hạn tổng thời gian các attempt nên request thường vượt SLA dù từng timeout còn thấp.
Một ứng dụng dùng Retry cùng Spring Cloud LoadBalancer nhưng mỗi lần retry chọn lại cùng node lỗi, khiến tăng số attempt không làm cải thiện tỷ lệ thành công.
Một nhóm muốn retry sang instance khác nhưng cache instance chỉ có một node vì health filter đang loại hết phần còn lại, khiến các lần thử bị dồn lên node đó.
Một dịch vụ gặp connection refused khi instance cũ bị xóa, nhưng chính sách retry chỉ nhận HTTP 5xx nên không thử lại dù còn backend khác đang khỏe.
Một ứng dụng retry mọi HTTP 500 của API thanh toán, khiến lỗi nghiệp vụ không thể phục hồi cũng bị phát lại nhiều lần và tiêu tốn hạn mức đối tác.
Một hệ thống nhận HTTP 429 kèm Retry-After nhưng nhiều client đồng thời bỏ qua thời gian chờ, khiến backend tiếp tục từ chối khi các attempt dồn cùng lúc.
Một nhóm đặt cùng exponential backoff cho mọi replica, khiến sau đợt lỗi hàng nghìn request retry quay lại theo nhịp giống nhau và tái tạo tình trạng quá tải.
Một ứng dụng có retry ở gateway, Feign và load balancer, khiến một thao tác nghiệp vụ có thể tạo nhiều lời gọi hơn giới hạn cho phép của downstream.
Một dịch vụ gửi lệnh chuyển tiền và nhận timeout sau khi backend đã commit, khiến retry tới replica khác có nguy cơ chuyển tiền thêm lần nữa.
Một nhóm dùng circuit breaker bao quanh retry, khiến breaker chỉ ghi nhận kết quả cuối cùng và không phản ánh số lần downstream thất bại trong từng attempt.
Một ứng dụng đặt retry ở ngoài circuit breaker theo service ID, khiến khi breaker OPEN tầng retry tiếp tục lặp lại các lời gọi bị từ chối ngay lập tức.
Một hệ thống áp dụng TimeLimiter ở ngoài các attempt nhưng không thống nhất với connect timeout, khiến lần thử cuối bắt đầu dù thời gian yêu cầu gốc gần hết.
Một dịch vụ muốn tôn trọng deadline từ request gốc nhưng client không truyền thời gian còn lại, khiến retry của lời gọi con tiếp tục sau khi response HTTP đã kết thúc.
Một nhóm dùng retry cho API đọc dữ liệu nhưng kết quả thay đổi giữa các instance do replication lag, khiến một request nhận trạng thái mới hơn ở attempt đầu rồi cũ hơn ở attempt sau.
Một ứng dụng có fallback sang instance vùng khác khi zone chính lỗi, nhưng vùng dự phòng không có cùng quyền truy cập dữ liệu nên retry tiếp tục trả HTTP 403.
Một dịch vụ chuyển từ timeout lỗi sang fallback cache, nhưng không ghi metric phân biệt fallback và response thật khiến latency cải thiện che giấu chất lượng dữ liệu giảm.
Một nhóm tăng số lần retry để giảm lỗi mạng ngẫu nhiên, nhưng connection pool và thread count tăng đột biến khi service đối tác chỉ chậm nhẹ.
Một hệ thống có HTTP client tự động redirect tới một hostname vật lý khác, khiến lần gọi sau redirect không còn đi qua quy tắc service ID ban đầu.
Một ứng dụng thiết lập connect timeout rất ngắn nhưng read timeout rất dài, khiến việc bắt tay mạng ổn còn backend xử lý chậm vẫn giữ request vượt thời hạn.
Một nhóm dùng tổng timeout ở gateway ngắn hơn timeout ứng dụng, khiến phía Spring Cloud vẫn thực thi và ghi log lỗi sau khi caller đã ngắt kết nối.
Một dịch vụ sử dụng WebClient với timeout trên Mono chỉ bao phần xử lý response, nhưng thời gian chờ lấy instance ở discovery làm tổng latency vượt SLA.
Một ứng dụng có pool kết nối HTTP chỉ cho phép ít kết nối hơn concurrency do load balancer tạo, khiến request chờ trong pool và dashboard nhầm là backend phản hồi chậm.
Một nhóm triển khai hàng trăm caller mỗi caller có connection pool riêng, khiến số kết nối tới một backend vượt hạn mức dù load balancing phân phối request đều.
Một hệ thống chọn backend khỏe theo round-robin nhưng một node có DNS resolution chậm, khiến các request đến node đó vẫn timeout trước khi truyền dữ liệu.
Một dịch vụ thử gửi request tới instance khác sau lỗi TLS, nhưng mọi instance cùng dùng certificate hết hạn nên retry làm tăng tải mà không cải thiện kết quả.
Một nhóm đưa thông tin xác thực người dùng vào request header nhưng một lần retry thay instance khiến header bị filter nội bộ loại bỏ và backend mới trả HTTP 401.
Một ứng dụng gọi nhiều service nội bộ theo service ID và dùng một header tenant chung, khiến yêu cầu có nguy cơ vượt ranh giới tenant khi client bị cấu hình sai danh sách đích.
Một hệ thống có policy lựa chọn vùng dựa trên query parameter do người dùng gửi, khiến caller có thể tự chuyển dữ liệu tới hạ tầng không được phép xử lý.
Một ứng dụng dùng ServiceInstance metadata để tạo URL callback, nhưng giá trị metadata từ nguồn discovery không đáng tin cậy khiến callback có thể trỏ tới host ngoài.
Một nhóm dùng OpenFeign logging để ghi host thực được chọn sau load balancing, nhưng log đồng thời in bearer token và vi phạm chính sách bảo vệ credential.
Một dịch vụ có truststore khác nhau theo từng vùng, nhưng RestClient load balanced dùng chung một TLS config khiến chỉ một tập instance kết nối được.
Một ứng dụng cần mTLS giữa các service, nhưng khi client chọn IP Pod thay vì hostname được cấp chứng chỉ việc xác thực danh tính TLS thất bại.
Một nhóm cho phép gọi nhiều service ID động từ request mà không có allowlist, khiến người dùng có thể gián tiếp gửi request tới dịch vụ quản trị nội bộ.
Một hệ thống ghi thông tin tên Pod và địa chỉ IP vào metric tag cho mỗi request, khiến số series tăng mạnh sau những đợt scale-out và rolling deployment.
Một ứng dụng giám sát số request theo service ID nhưng không theo instance, khiến một node gây HTTP 500 liên tục bị che bởi tỷ lệ thành công cao của các node khác.
Một nhóm dùng metric số instance healthy từ discovery nhưng không đo latency HTTP thật, khiến lỗi xử lý chậm ở backend vẫn không kích hoạt cảnh báo.
Một dịch vụ dùng tracing với RestClient inbound và outbound, nhưng một builder thủ công không có observation khiến các span gọi downstream không xuất hiện trong trace.
Một ứng dụng retry lời gọi tới ba instance khác nhau, nhưng log chỉ chứa service ID và không ghi attempt hoặc instance cuối cùng khiến hậu kiểm không truy ra node lỗi.
Một nhóm thay đổi thuật toán load balancing trong một release, nhưng dashboard không đánh dấu phiên bản policy khiến việc so sánh tỷ lệ lỗi trước và sau thiếu căn cứ.
Một hệ thống chỉ dùng p95 latency chung cho một service ID, khiến một vùng có độ trễ rất cao bị che bởi phần lớn request nhanh ở vùng còn lại.
Một ứng dụng nhận fallback khi hết instance khỏe, nhưng metrics chỉ đếm response HTTP 200 nên dashboard báo chất lượng tốt dù dữ liệu phần lớn đến từ cache cũ.
Một dịch vụ log exception thiếu service ID và URL vật lý đã chọn, khiến đội trực không phân biệt lỗi do discovery hay lỗi do instance đang xử lý.
Một nhóm thu thập health check events nhưng không liên kết với trạng thái cache của instance supplier, khiến thời điểm Pod bị loại khỏi traffic khó được xác định.
Một hệ thống dùng metric đồng hồ lỗi theo từng instance nhưng mỗi node caller dùng đồng hồ khác nhau, khiến thứ tự sự kiện chuyển vùng và retry trên timeline bị lẫn.
Một ứng dụng bị quá tải CPU sau khi bật tracing cho mọi attempt retry, nhưng bộ test hiệu năng trước đó chỉ chạy đường thành công không retry.
Một dịch vụ có alert dựa vào số HTTP 503 từ downstream nhưng không tách lỗi không tìm được instance, khiến nhóm xử lý hậu kiểm nhầm nguyên nhân giữa registry và backend.
Một ứng dụng triển khai nhiều vùng nhưng không gắn zone cho metric của ServiceInstance, khiến sự cố kết nối liên vùng bị diễn giải thành lỗi ngẫu nhiên toàn cụm.
Một nhóm muốn theo dõi mức cân bằng số request theo backend nhưng chỉ có counter ở gateway, khiến đường gọi qua OpenFeign từ job nền không được đưa vào số liệu.
Một hệ thống đặt health probe và traffic nghiệp vụ chung một meter name, khiến số request đo tăng ngay cả khi người dùng không gửi yêu cầu mới.
Một ứng dụng có kịch bản instance đột ngột mất kết nối, nhưng bài test chỉ mock DiscoveryClient luôn trả đúng một backend khỏe nên không phát hiện lỗi failover.
Một nhóm kiểm tra round-robin bằng thứ tự kết quả trong danh sách cứng, nhưng discovery provider thực tế có thể trả danh sách theo thứ tự thay đổi trong lúc rollout.
Một dịch vụ test load-balanced RestClient bằng HTTP URL thật, khiến bài test pass nhờ DNS mà chưa xác nhận khả năng tìm service ID qua discovery.
Một ứng dụng dùng WebClient trong production nhưng bộ kiểm thử tạo client bằng WebClient.create, khiến các kiểm tra không đi qua cấu hình load balancing thực tế.
Một nhóm mock OpenFeign trả dữ liệu thành công nhưng không thử trường hợp không có ServiceInstance, khiến lỗi proxy hoặc fallback của client chưa được đánh giá.
Một bộ test chỉ có một instance nên không phát hiện chính sách ưu tiên zone đang loại sai toàn bộ backend ở vùng dự phòng.
Một ứng dụng kiểm thử health supplier khi tất cả probes đều thành công, khiến trường hợp một node mất readiness và danh sách đích bị thu hẹp chưa được xác minh.
Một nhóm dùng cache instance giả lập luôn mới, khiến việc chọn endpoint cũ sau Pod termination chỉ xuất hiện ở production dưới tải cao.
Một hệ thống test retry GET bằng mock server trả lỗi trước khi đọc request, khiến tình huống POST đã commit rồi response timeout không được kiểm tra.
Một ứng dụng dùng integration test gửi các lời gọi tuần tự, khiến sai lệch phân phối do connection pool và concurrency cao không xuất hiện trước khi triển khai.
Một nhóm kiểm thử WebClient Mono chỉ ở nhánh onNext, khiến lỗi DNS, không tìm thấy instance và hủy subscription chưa có assertion tương ứng.
Một dịch vụ test Feign theo profile local với URL cố định, khiến khi production bỏ URL để sử dụng discovery lỗi cấu hình service name chưa từng được kiểm tra.
Một ứng dụng chỉ test timeout ở HTTP client mà không cộng thời gian retry và chờ connection pool, khiến request thực vượt SLA dù mọi test thành phần đều pass.
Một nhóm chạy kiểm thử chuyển vùng bằng cách dừng backend nhưng không chờ cache instance hết hạn, khiến kết quả báo cáo failover không phân biệt chính sách mới với cache cũ.
Một hệ thống chỉ đo throughput trên một caller, khiến khi triển khai nhiều replica tổng số discovery queries và health probes vượt khả năng của registry.
Một ứng dụng test chính sách sticky session bằng một browser giữ cookie, nhưng không thử trường hợp cookie vắng mặt hoặc bị thay đổi khi chạy qua proxy.
Một nhóm kiểm thử weighted routing với lưu lượng rất thấp, khiến tỷ lệ request nhận được dao động lớn và một phép đo ngắn bị diễn giải thành cấu hình sai.
Một dịch vụ chạy test fault injection trả HTTP 500 từ tất cả instance, nhưng không thử trường hợp chỉ một node hỏng nên policy không được đánh giá khả năng tránh node xấu.
Một nhóm đánh giá timeout bằng mock response luôn đúng schema, khiến lỗi decoder Feign trên một subset instance sau rolling upgrade chỉ lộ khi production chạy thật.
Một ứng dụng kiểm tra request tracing trong controller nhưng không xác minh các outbound attempts, khiến trace của những request retry thiếu thông tin instance đã thử.
Một hệ thống test không có registry bằng cách trả danh sách instance tĩnh, khiến phần startup của discovery và hành vi lấy dữ liệu rỗng chưa được thực thi.
Một nhóm nâng Spring Cloud release train nhưng không chạy regression tests cho OpenFeign, RestClient và WebClient cùng service ID, khiến các đường HTTP client có thể khác nhau sau deploy.
Một dịch vụ bị lỗi định tuyến khi autoscaling nhưng log không có timestamp refresh của instance list, khiến việc tái hiện sự cố qua dữ liệu kiểm thử rất khó.
Một ứng dụng chỉ thử lỗi một backend đã dừng trước khi deploy, nhưng không mô phỏng instance mất kết nối giữa lúc request đang thực thi nên chưa kiểm tra kết quả retry.
Một nhóm benchmark load balancing chỉ dùng request nhỏ, khiến thời gian trả file lớn và mức tiêu thụ memory của các instance không được xem xét khi chọn policy.
Một hệ thống mở rộng từ một lên mười service instances nhưng không đo tỷ lệ request theo instance ở mỗi giai đoạn, khiến đội vận hành chưa biết bottleneck thật có được phân tán hay không.
Một ứng dụng dùng cùng supplier cho nhiều service ID nhưng một client có cấu hình health check riêng, khiến dữ liệu được chọn theo policy của service khác và gặp lỗi khó tái hiện.
Một nhóm chạy Kubernetes với Service DNS và Spring Cloud LoadBalancer cùng lúc nhưng chưa xác định lợi ích thực tế của từng lớp, khiến số lượng health probes và cache không cần thiết tăng theo số replica.
