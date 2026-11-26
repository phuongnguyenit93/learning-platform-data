Service discovery giải quyết vấn đề gì khi địa chỉ và số lượng instance của một dịch vụ thay đổi liên tục?
Bạn sẽ mô tả hành trình một request tìm đến instance của dịch vụ đích trong hệ thống microservice như thế nào?
Bạn sẽ phân biệt service name, instance ID, endpoint, địa chỉ IP và cổng kết nối trong một bản ghi discovery ra sao?
Những thay đổi nào khi autoscaling, rolling deployment hoặc instance bị lỗi khiến danh sách endpoint cần cập nhật?
Bạn sẽ phân biệt service discovery với service routing và load balancing theo trách nhiệm từng thành phần như thế nào?
Bạn sẽ so sánh cách cấu hình địa chỉ dịch vụ cố định với tra cứu endpoint động khi triển khai nhiều instance ra sao?
Bạn sẽ thiết kế quy ước đặt tên dịch vụ sao cho không nhầm môi trường development, staging và production như thế nào?
Bạn sẽ xác định các thông tin metadata nào cần gắn với endpoint để client chọn được instance phù hợp?
Bạn sẽ đánh giá yêu cầu về độ mới của kết quả discovery đối với dịch vụ có tần suất thay đổi instance cao như thế nào?
Bạn sẽ mô tả các bước client cần thực hiện từ lúc nhận tên dịch vụ đến khi mở kết nối mạng với một endpoint ra sao?
Bạn sẽ phân biệt client-side discovery và server-side discovery bằng đường đi request cụ thể như thế nào?
Bạn sẽ chọn client-side hay server-side discovery theo khả năng kiểm soát client, hệ thống proxy và môi trường triển khai ra sao?
Bạn sẽ giải thích vai trò của service registry và sự khác biệt giữa đăng ký, tra cứu và hủy đăng ký dịch vụ như thế nào?
Bạn sẽ mô tả thông tin một service instance cần đăng ký vào registry để client có thể truy cập đúng như thế nào?
Bạn sẽ thiết kế vòng đời đăng ký khi một instance khởi động nhưng chưa sẵn sàng tiếp nhận lưu lượng ra sao?
Bạn sẽ quyết định thời điểm hủy đăng ký khi ứng dụng dừng có kiểm soát như thế nào để giảm request thất bại?
Khi một instance chết đột ngột mà không hủy đăng ký, cơ chế nào cần được xem xét để loại endpoint cũ?
Bạn sẽ phân biệt mô hình instance tự đăng ký với mô hình thành phần bên ngoài đăng ký hộ instance như thế nào?
Bạn sẽ lựa chọn đẩy cập nhật hay để client định kỳ kéo danh sách instance từ registry dựa trên những tiêu chí nào?
Bạn sẽ kiểm tra những rủi ro nào khi nhiều bản ghi trùng hoặc thiếu thông tin nhận dạng instance trong registry?
Bạn sẽ phân tích điều gì xảy ra nếu một dịch vụ đăng ký địa chỉ chỉ truy cập được từ mạng nội bộ sai phạm vi?
Bạn sẽ phân biệt tra cứu bằng DNS với truy vấn registry qua HTTP API về cách nhận dữ liệu endpoint ra sao?
Bạn sẽ thiết kế DNS naming cho dịch vụ nội bộ cần phân biệt môi trường, namespace và khu vực như thế nào?
Bạn sẽ phân biệt vai trò bản ghi A, AAAA và SRV khi mô tả địa chỉ và cổng dịch vụ như thế nào?
Bạn sẽ xác định khi nào một tên DNS ánh xạ nhiều địa chỉ IP và client lựa chọn địa chỉ bằng cách nào?
Bạn sẽ đánh giá ảnh hưởng của DNS TTL lên độ trễ phát hiện instance mới và thời gian giữ endpoint đã hỏng ra sao?
Bạn sẽ phân tích sự khác nhau giữa cache DNS tại ứng dụng, hệ điều hành và recursive resolver như thế nào?
Bạn sẽ kiểm tra điều gì khi TTL được cấu hình thấp nhưng client vẫn tiếp tục truy cập địa chỉ cũ?
Bạn sẽ mô tả tác động của negative DNS caching khi tên dịch vụ vừa được tạo nhưng trước đó tra cứu thất bại như thế nào?
Bạn sẽ phân biệt việc DNS trả lời thành công với việc endpoint thực sự đủ khỏe để nhận request ra sao?
Bạn sẽ đánh giá giới hạn của DNS round-robin nếu một instance trả lỗi hoặc có thời gian đáp ứng cao như thế nào?
Bạn sẽ xác định khi nào cần thêm proxy hoặc load balancer phía sau tên DNS để quản lý lưu lượng hiệu quả hơn?
Bạn sẽ thiết kế chiến lược xử lý khi DNS resolver tạm thời không phản hồi nhưng ứng dụng còn cache endpoint cũ như thế nào?
Bạn sẽ dùng dig hoặc nslookup để xác minh những bản ghi DNS mà client thực sự nhận được như thế nào?
Bạn sẽ chẩn đoán tình huống tên dịch vụ phân giải đúng ở một máy nhưng thất bại trên máy khác theo những bước nào?
Bạn sẽ đánh giá ảnh hưởng của DNS search domain và tên đầy đủ FQDN khi truy cập dịch vụ nội bộ như thế nào?
Bạn sẽ so sánh DNS-based discovery với registry-based discovery về thông tin health, metadata và độ trễ cập nhật ra sao?
Bạn sẽ xác định điều kiện nào khiến việc duy trì đồng thời DNS và registry gây sai lệch danh sách endpoint?
Bạn sẽ mô tả những trạng thái cần theo dõi trong vòng đời của một bản ghi service registry như thế nào?
Bạn sẽ giải thích sự khác biệt giữa việc instance gửi heartbeat và hệ thống chủ động thực hiện health check ra sao?
Bạn sẽ lựa chọn HTTP, TCP hoặc kiểm tra tùy chỉnh cho health check dựa trên kiểu dịch vụ như thế nào?
Bạn sẽ phân biệt liveness, readiness và khả năng phục vụ request thực tế khi thiết kế kiểm tra sức khỏe như thế nào?
Bạn sẽ phân tích tình huống tiến trình còn chạy nhưng đã mất quyền truy cập database và ảnh hưởng đến health status ra sao?
Bạn sẽ thiết kế ngưỡng số lần lỗi và khoảng thời gian kiểm tra để tránh loại instance vì nhiễu mạng ngắn như thế nào?
Bạn sẽ đánh giá rủi ro của health check quá tốn tài nguyên khi số instance tăng nhanh như thế nào?
Bạn sẽ giải thích cơ chế lease hoặc TTL dùng để phát hiện instance ngừng gửi tín hiệu sống như thế nào?
Bạn sẽ phân biệt instance không khỏe với tình huống registry không thể liên lạc đến instance do phân hoạch mạng ra sao?
Bạn sẽ thiết kế trạng thái draining để instance ngừng nhận request mới nhưng hoàn tất request đang chạy như thế nào?
Bạn sẽ xác định thời điểm nào nên đánh dấu endpoint không sẵn sàng trong quá trình rolling update?
Bạn sẽ kiểm chứng thời gian từ lúc một instance lỗi đến khi client không còn chọn endpoint đó như thế nào?
Bạn sẽ phân tích cách health check không ổn định gây dao động danh sách endpoint và làm tăng tải hệ thống ra sao?
Bạn sẽ thiết kế cơ chế phục hồi endpoint khi instance khỏe lại mà tránh đưa nó trở lại nhận tải quá sớm như thế nào?
Bạn sẽ mô tả vai trò của Consul agent, catalog và dịch vụ discovery trong một cụm ứng dụng như thế nào?
Bạn sẽ so sánh việc đăng ký một service qua Consul agent với khai báo qua cấu hình triển khai về vòng đời quản lý ra sao?
Bạn sẽ chọn những trường nào trong service definition của Consul để mô tả instance, port, tag và health check?
Bạn sẽ giải thích cách Consul sử dụng health check để lọc các endpoint không khỏe khi tra cứu dịch vụ như thế nào?
Bạn sẽ so sánh truy vấn Consul bằng DNS với HTTP API về dữ liệu trả về và khả năng lựa chọn instance ra sao?
Bạn sẽ đánh giá vai trò của tags hoặc metadata trong Consul khi cần định tuyến theo phiên bản ứng dụng như thế nào?
Bạn sẽ mô tả cách Consul agent giao tiếp và cập nhật thông tin thành viên khi các nút tham gia hoặc rời cụm ra sao?
Bạn sẽ phân biệt thành viên Consul cluster còn sống với trạng thái khỏe của service instance được đăng ký như thế nào?
Bạn sẽ xác định cách client phát hiện thay đổi dịch vụ qua truy vấn định kỳ hoặc cơ chế blocking query của Consul ra sao?
Bạn sẽ phân tích điều gì xảy ra với tra cứu Consul khi một phần hạ tầng hoặc leader của cụm gặp sự cố?
Bạn sẽ đánh giá các điều kiện cần để triển khai Consul có khả năng chịu lỗi và quorum phù hợp như thế nào?
Bạn sẽ thiết kế chính sách truy cập catalog và API của Consul để mỗi ứng dụng chỉ xem được thông tin cần thiết ra sao?
Bạn sẽ xử lý trường hợp Consul vẫn trả bản ghi service nhưng endpoint thực tế liên tục lỗi theo quy trình nào?
Bạn sẽ mô tả cách một ứng dụng sử dụng Eureka để đăng ký và nhận danh sách instance của dịch vụ khác như thế nào?
Bạn sẽ giải thích vai trò của heartbeat và lease renewal trong quá trình Eureka theo dõi service instance ra sao?
Bạn sẽ phân biệt register, renew, fetch registry và deregister trong vòng đời Eureka client như thế nào?
Bạn sẽ phân tích ảnh hưởng của chu kỳ fetch registry và bộ nhớ đệm client đến độ mới danh sách endpoint như thế nào?
Bạn sẽ đánh giá lý do Eureka có cơ chế self-preservation và tác động đến các bản ghi có thể đã lỗi như thế nào?
Bạn sẽ thiết kế hành vi client khi Eureka server không khả dụng trong thời gian ngắn nhưng cache registry vẫn còn như thế nào?
Bạn sẽ phân biệt trạng thái instance do Eureka ghi nhận với kiểm tra readiness thực tế trước khi gửi request ra sao?
Bạn sẽ giải thích cách nhiều Eureka server hỗ trợ khả dụng của discovery và những trường hợp đồng bộ có thể chậm như thế nào?
Bạn sẽ lựa chọn các thông tin instance ID, hostname, port và metadata cho Eureka trong môi trường nhiều container ra sao?
Bạn sẽ kiểm tra điều gì khi Eureka hiển thị instance UP nhưng client vẫn không kết nối được?
Bạn sẽ so sánh Consul và Eureka về mô hình health, cách client lấy cập nhật và phạm vi áp dụng như thế nào?
Bạn sẽ đánh giá khác biệt vận hành giữa service registry riêng và cơ chế discovery được tích hợp trong nền tảng orchestration ra sao?
Bạn sẽ mô tả cách Kubernetes Service cung cấp địa chỉ ổn định cho tập Pod có vòng đời thay đổi như thế nào?
Label selector quyết định những Pod nào thuộc phạm vi phục vụ của một Kubernetes Service theo cơ chế nào?
Bạn sẽ phân biệt Service, Pod IP và EndpointSlice trong cơ chế theo dõi endpoint của Kubernetes như thế nào?
Bạn sẽ xác định Pod readiness ảnh hưởng đến việc một endpoint có được đưa vào tập phục vụ traffic như thế nào?
Bạn sẽ mô tả luồng từ client Pod truy vấn DNS tên Service đến lúc kết nối đến Pod đích ra sao?
Bạn sẽ phân biệt ClusterIP Service và headless Service theo kết quả DNS và trách nhiệm chọn endpoint như thế nào?
Bạn sẽ giải thích cách client kết nối qua ClusterIP và cơ chế chuyển tiếp đến backend ở tầng mạng ra sao?
Bạn sẽ đánh giá khi nào nên dùng headless Service cho ứng dụng cần biết từng instance thay vì một địa chỉ logic?
Bạn sẽ phân biệt vai trò của CoreDNS với cơ chế quản lý endpoint trong control plane Kubernetes như thế nào?
Bạn sẽ kiểm tra hành vi DNS của Service khi sử dụng tên ngắn, namespace và tên miền cụm đầy đủ ra sao?
Bạn sẽ phân biệt Kubernetes Service type ClusterIP, NodePort và LoadBalancer theo phạm vi truy cập ra sao?
Bạn sẽ mô tả quá trình scale Deployment tăng Pod và cách danh sách endpoint của Service được cập nhật như thế nào?
Bạn sẽ xử lý việc một Pod đang terminating vẫn còn kết nối dài và traffic đang xử lý bằng cách nào?
Bạn sẽ xác định vì sao Service không có endpoint dù các Pod đã được tạo thành công như thế nào?
Bạn sẽ kiểm tra mối liên hệ giữa readiness probe, label và EndpointSlice khi một số Pod không nhận traffic ra sao?
Bạn sẽ phân biệt DNS của headless Service và load balancing ở phía client khi kết quả chứa nhiều Pod IP như thế nào?
Bạn sẽ phân tích sự cố một số client dùng cache DNS quá lâu trong lúc Pod phía sau headless Service được thay thế ra sao?
Bạn sẽ đánh giá vai trò của NetworkPolicy trong việc cho phép client truy cập Service và Pod đích như thế nào?
Bạn sẽ so sánh cách phát hiện endpoint trong Kubernetes với việc duy trì Eureka hoặc Consul trong một cluster ra sao?
Bạn sẽ lựa chọn cách discovery cho dịch vụ nằm ngoài Kubernetes nhưng cần được truy cập từ các Pod như thế nào?
Bạn sẽ so sánh lựa chọn một endpoint ngẫu nhiên, round-robin và weighted routing dựa trên tính đồng nhất của instance ra sao?
Bạn sẽ đánh giá vai trò của health state và độ trễ trong chiến lược cân bằng tải phía client như thế nào?
Bạn sẽ xác định khi nào cần zone-aware routing để giảm độ trễ và chi phí trao đổi giữa các vùng ra sao?
Bạn sẽ phân tích hiện tượng tất cả client đồng loạt gọi một instance sau thay đổi registry gây mất cân bằng tải như thế nào?
Bạn sẽ lựa chọn cơ chế giới hạn kết nối, timeout và retry của client để tránh dồn tải lên endpoint đang lỗi ra sao?
Bạn sẽ thiết kế retry sang endpoint khác mà vẫn giữ tính an toàn của các request không có tính idempotent như thế nào?
Bạn sẽ đánh giá khi nào circuit breaker cần loại tạm một endpoint mà không sửa trạng thái chung trong registry ra sao?
Bạn sẽ phân biệt service discovery chọn nơi kết nối với các cơ chế định tuyến HTTP theo nội dung request như thế nào?
Bạn sẽ phân tích tác động của connection pooling và keep-alive đến việc cập nhật endpoint khi registry đã đổi như thế nào?
Bạn sẽ xử lý kết nối lâu tới instance cũ khi danh sách endpoint mới đã loại instance đó ra sao?
Bạn sẽ chọn TTL hoặc thời hạn cache cho danh sách endpoint bằng cách cân bằng độ mới và tải lên registry như thế nào?
Bạn sẽ mô tả các chiến lược invalidation, refresh và watch khi cache discovery ở phía ứng dụng như thế nào?
Bạn sẽ xác định ảnh hưởng của stale cache với dịch vụ đã scale down hoặc thay đổi địa chỉ IP như thế nào?
Bạn sẽ phân tích tình huống registry đang phân hoạch mạng khiến hai nhóm client nhìn thấy tập endpoint khác nhau ra sao?
Bạn sẽ đánh giá ưu tiên tính nhất quán hay tính khả dụng của dữ liệu discovery theo yêu cầu hệ thống như thế nào?
Bạn sẽ thiết kế hành vi fail-open hoặc fail-closed khi thông tin health hoặc discovery không còn cập nhật như thế nào?
Bạn sẽ xây dựng cơ chế fallback khi registry hoặc DNS gặp sự cố nhưng client đã có danh sách endpoint tin cậy ra sao?
Bạn sẽ đánh giá rủi ro của việc hardcode endpoint dự phòng so với duy trì cache đã có thời hạn như thế nào?
Bạn sẽ thiết kế quy tắc loại instance lỗi mà không loại toàn bộ cụm vì sự cố giám sát chung ra sao?
Bạn sẽ giải thích vì sao registry có nhiều replica vẫn có thể trở thành điểm nghẽn nếu client truy vấn quá thường xuyên?
Bạn sẽ lựa chọn và đo những chỉ số nào để xác định độ trễ lan truyền cập nhật registry đến từng client?
Bạn sẽ thiết kế kiểm soát danh tính của service instance trước khi cho phép đăng ký endpoint vào registry ra sao?
Bạn sẽ phân quyền đăng ký, cập nhật, hủy đăng ký và đọc thông tin discovery theo nguyên tắc tối thiểu quyền như thế nào?
Bạn sẽ dùng TLS hoặc mTLS để bảo vệ kết nối đến registry và xác thực các thành phần tham gia ra sao?
Bạn sẽ đánh giá rủi ro khi một bên trái phép đăng ký endpoint giả mạo dưới tên dịch vụ hợp lệ như thế nào?
Bạn sẽ phân tích những loại metadata nhạy cảm không nên công khai qua DNS hoặc catalog dịch vụ ra sao?
Bạn sẽ quản lý và xoay vòng token, ACL credential hoặc chứng chỉ của discovery client như thế nào?
Bạn sẽ cân nhắc bảo vệ DNS nội bộ trước thay đổi trái phép và dữ liệu tra cứu bị làm giả theo những cơ chế nào?
Bạn sẽ xác định cách tách thông tin discovery giữa tenant, namespace và môi trường để giảm nguy cơ truy cập chéo như thế nào?
Bạn sẽ thiết kế nhật ký kiểm toán cho hoạt động đăng ký và thay đổi endpoint nhằm hỗ trợ điều tra sự cố ra sao?
Bạn sẽ lập quy trình chẩn đoán khi client báo không tìm thấy service name dù instance đang chạy như thế nào?
Bạn sẽ phân biệt lỗi không phân giải được tên, lỗi không có endpoint khỏe và lỗi kết nối mạng đến endpoint ra sao?
Bạn sẽ kết hợp kết quả DNS, thông tin registry, health check và log client để tìm nguyên nhân request thất bại như thế nào?
Bạn sẽ dùng dig hoặc nslookup để kiểm tra địa chỉ Service và so sánh với EndpointSlice hoặc registry như thế nào?
Bạn sẽ xác định bằng chứng nào cho thấy client sử dụng cache endpoint cũ sau một lần rollout ra sao?
Bạn sẽ đo khoảng thời gian từ lúc Pod hoặc instance được đánh dấu không khỏe đến lúc traffic thực sự ngừng gửi đến đó như thế nào?
Bạn sẽ chẩn đoán trường hợp health check thành công nhưng yêu cầu nghiệp vụ vẫn trả lỗi 5xx theo những bước nào?
Bạn sẽ phân tích tình huống một số instance không xuất hiện trong registry vì sai cổng, hostname hoặc metadata như thế nào?
Bạn sẽ phân biệt sự cố truy cập registry chỉ xảy ra ở một khu vực mạng với lỗi chung của hệ thống như thế nào?
Bạn sẽ thiết kế thí nghiệm scale up và scale down để xác minh danh sách endpoint cùng phân phối tải thay đổi đúng như thế nào?
Bạn sẽ kiểm thử sự cố DNS, mất kết nối registry và instance crash để đo ảnh hưởng của thời gian cache như thế nào?
Bạn sẽ theo dõi số endpoint khỏe, tỷ lệ tra cứu thất bại, độ trễ discovery và thời gian ổn định sau lỗi bằng chỉ số nào?
Bạn sẽ đặt cảnh báo gì khi tỷ lệ endpoint không khỏe tăng cùng lúc hoặc tốc độ cập nhật registry bị chậm?
Bạn sẽ tổ chức diễn tập rolling deployment có graceful shutdown để kiểm tra không còn request mới đến instance sắp dừng ra sao?
Bạn sẽ so sánh kết quả thử tải khi dùng DNS round-robin với client-side load balancing theo độ lệch tải giữa các instance như thế nào?
Bạn sẽ xác định các tiêu chí nghiệm thu về thời gian phát hiện instance mới, loại instance lỗi, an toàn truy cập và tính sẵn sàng của service discovery như thế nào?
