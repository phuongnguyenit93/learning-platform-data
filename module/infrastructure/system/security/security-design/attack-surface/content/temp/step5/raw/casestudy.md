Một doanh nghiệp mở thêm cổng đối tác nhưng CMDB chưa cập nhật hostname, API gateway và địa chỉ IP mới; nhóm bảo mật chỉ quét các tài sản đã có trong danh sách cũ.
Đội vận hành phát hiện một subdomain trỏ đến máy chủ thử nghiệm đã ngừng quản lý; dịch vụ vẫn truy cập được từ Internet và chứa bản build cũ có dữ liệu mẫu gần giống production.
Một nhóm sản phẩm tạo môi trường demo trên cloud bằng tài khoản cá nhân; tài nguyên không gắn tag owner hoặc thời hạn nên không xuất hiện trong quy trình kiểm kê tập trung.
DNS zone có nhiều bản ghi CNAME và wildcard được tạo qua nhiều năm; một số hostname không còn chủ sở hữu nhưng vẫn trỏ đến dịch vụ bên thứ ba có thể bị chiếm quyền cấu hình.
Một địa chỉ IP public phục vụ nhiều virtual host; việc kiểm kê chỉ ghi nhận IP mà không liệt kê hostname, cổng và ứng dụng tương ứng khiến một ứng dụng quản trị bị bỏ sót.
Ứng dụng có IPv6 được bật tự động trên máy chủ nhưng firewall và công cụ quét chỉ kiểm tra IPv4; dịch vụ quản trị vô tình lộ qua địa chỉ IPv6 công khai.
Một load balancer cũ vẫn có listener cho giao thức và cổng không còn dùng; nhóm ứng dụng đã xóa route ở frontend nhưng listener backend vẫn chuyển tiếp đến dịch vụ nội bộ.
API gateway công bố danh sách route mới nhưng tài liệu OpenAPI và inventory chưa cập nhật; endpoint thử nghiệm có chức năng quản trị vẫn được truy cập bằng URL trực tiếp.
Một API phiên bản cũ bị đánh dấu deprecated nhưng không có ngày ngừng hoạt động; client bên ngoài tiếp tục gọi endpoint cũ với cơ chế xác thực yếu hơn API hiện tại.
Ứng dụng di động gọi trực tiếp một endpoint backend không đi qua API gateway; nhóm thiết kế chỉ đánh giá các điểm vào được ghi nhận trong gateway.
GraphQL endpoint cho phép introspection và truy vấn lồng sâu trên production; nhóm bảo mật chưa đánh giá chi phí truy vấn hoặc các object có thể truy cập qua quan hệ.
Một webhook nhận sự kiện từ đối tác được triển khai ở endpoint public; sơ đồ luồng dữ liệu không thể hiện nguồn gửi, cơ chế xác minh chữ ký và hệ thống nội bộ nhận payload.
Ứng dụng tải URL do người dùng cung cấp để lấy ảnh đại diện; máy chủ có thể truy cập metadata service và các dải mạng nội bộ nhưng luồng này chưa được đưa vào threat model.
Một chức năng export cho phép người dùng chỉ định tên máy chủ lưu trữ; nhóm thiết kế chưa kiểm tra việc truy cập các dịch vụ nội bộ qua DNS hoặc địa chỉ IP sau redirect.
Luồng dữ liệu từ Internet đi qua CDN, WAF, reverse proxy và service mesh nhưng sơ đồ tin cậy chỉ thể hiện trình duyệt và ứng dụng; header định danh có thể bị tin cậy sai tại hop trung gian.
Một hệ thống microservices chia sẻ cùng network segment; dịch vụ xử lý ảnh bị xâm nhập có thể kết nối trực tiếp đến cơ sở dữ liệu và dịch vụ quản trị không cần qua policy trung gian.
Nhóm kiến trúc đánh dấu subnet là private nên cho rằng tài nguyên không thể bị truy cập từ Internet; route table và NAT gateway thực tế cho phép một số luồng outbound không được giới hạn.
Security group của một workload cho phép inbound từ toàn bộ dải mạng nội bộ; dải này bao gồm cả máy trạm người dùng và môi trường thử nghiệm không cùng mức tin cậy.
Một cổng quản trị chỉ được giới hạn theo IP văn phòng nhưng nhân viên có thể truy cập qua VPN dùng chung; sơ đồ đường đi tấn công chưa thể hiện thiết bị đầu cuối và danh tính người dùng.
Dịch vụ DNS nội bộ cho phép recursive query từ nhiều mạng không cần thiết; một máy chủ bị chiếm dụng có thể dùng resolver này để hỗ trợ dò quét hoặc tunnel dữ liệu.
Một tài khoản cloud có quyền liệt kê và đọc nhiều storage bucket; attack path từ credential của workload phát triển đến dữ liệu production chưa được mô hình hóa.
Role của máy ảo cloud có quyền đọc metadata và secret của nhiều dịch vụ; ứng dụng có SSRF có thể tiếp cận endpoint metadata để lấy credential ngoài dự kiến.
Bucket chứa bản sao dữ liệu production được cấu hình public-read để phục vụ kiểm thử tích hợp; thay đổi này không được phát hiện vì scanner chỉ đánh giá bucket chính.
Snapshot volume và image máy ảo cũ vẫn tồn tại sau khi hệ thống nguồn bị xóa; các bản sao này chứa dữ liệu, khóa hoặc cấu hình nhạy cảm nhưng không nằm trong inventory.
Cloud control plane cho phép tạo access key dài hạn và policy wildcard; một credential bị lộ từ môi trường build có thể thay đổi cấu hình mạng của production.
Một workload dùng chung service account với nhiều ứng dụng; khi một ứng dụng bị xâm nhập, nhóm không thể xác định những tài nguyên khác có thể bị truy cập theo cùng danh tính.
Quy trình đăng nhập quản trị tập trung qua SSO nhưng một giao diện quản trị cũ vẫn hỗ trợ tài khoản local; điểm vào này không nằm trong sơ đồ định danh và không áp dụng MFA.
Một nhân viên có quyền truy cập hệ thống production qua nhiều nhóm lồng nhau; inventory quyền chỉ ghi role trực tiếp nên không phát hiện đường dẫn đặc quyền gián tiếp.
Token của pipeline CI có quyền publish image và cập nhật deployment trên nhiều namespace; nhóm bảo mật chưa lập bản đồ đường đi từ repository bên ngoài đến cluster production.
Runner CI dùng chung cho nhiều repository và có thể truy cập network nội bộ; một job xử lý pull request không tin cậy có thể tiếp cận dịch vụ quản trị qua runner.
Artifact được tải từ registry bên ngoài mà không xác minh chữ ký hoặc provenance; dependency bị thay thế có thể đi vào image production qua pipeline phát hành.
Một thư viện nội bộ được phân phối qua package registry dùng chung; namespace package có thể bị chiếm do tên chưa được bảo vệ và quy trình publish không yêu cầu xác thực mạnh.
Nhà cung cấp SaaS có quyền truy cập dữ liệu khách hàng qua OAuth integration; inventory bên thứ ba chỉ ghi tên nhà cung cấp mà không thể hiện scope token và dữ liệu được chia sẻ.
Một hệ thống phân tích gửi bản sao dữ liệu production đến dịch vụ telemetry bên ngoài; data flow diagram không ghi endpoint đích, trường dữ liệu hoặc thời hạn lưu trữ.
Khóa ký phần mềm được lưu trong máy build có nhiều người truy cập; đường tấn công từ tài khoản developer đến quy trình ký và phát hành chưa được đánh giá.
Thiết bị IoT trong mạng văn phòng chạy firmware cũ và có dịch vụ quản trị mặc định; thiết bị không được đưa vào inventory vì không thuộc nhóm máy chủ truyền thống.
Một cluster Kubernetes có nhiều ingress controller và service type LoadBalancer; inventory chỉ ghi endpoint của ingress chính nên các service phụ vẫn lộ ra Internet.
Node Kubernetes cho phép pod dùng hostPath và hostNetwork; một workload có quyền thấp có thể tiếp cận tài nguyên host hoặc dịch vụ node ngoài phạm vi dự kiến.
Admission policy chỉ áp dụng cho namespace production mới; namespace cũ vẫn cho phép deploy image không rõ nguồn gốc và container privileged.
Endpoint debug và metrics được bật trên production để hỗ trợ sự cố; chúng tiết lộ biến môi trường, topology hoặc thông tin nội bộ nhưng không được xem là điểm vào trong danh mục tài sản.
Một trang quản trị chỉ ẩn khỏi menu người dùng nhưng URL vẫn truy cập được; nhóm đánh giá attack surface dựa trên giao diện hiển thị thay vì endpoint và kiểm soát truy cập thực tế.
Chức năng upload chấp nhận nhiều loại tệp và chuyển tệp qua dịch vụ parse nội bộ; sơ đồ dữ liệu không ghi parser, thư mục tạm và quyền truy cập giữa các bước xử lý.
Một luồng export dữ liệu đi qua hàng đợi, worker và object storage; quyền đọc object được cấp rộng hơn quyền gọi API ban đầu nên dữ liệu có thể bị truy cập theo đường khác.
Certificate của một hostname phụ đã hết hạn nhưng DNS vẫn trỏ đến endpoint cũ; endpoint này tiếp tục phục vụ ứng dụng với cấu hình TLS và header lỗi thời.
Một endpoint hỗ trợ giao thức cũ được mở tạm để tương thích đối tác; không có ngày hết hạn hoặc owner theo dõi nên ngoại lệ tồn tại sau khi tích hợp kết thúc.
Đợt quét bề mặt tấn công phát hiện nhiều cổng mở nhưng không phân biệt listener cần thiết, dịch vụ giả mạo và tài sản dùng chung; nhóm vận hành định đóng hàng loạt mà chưa đánh giá phụ thuộc.
Nhóm kiểm thử chỉ quét tài sản có hostname public; các endpoint quản trị qua VPN, API private và đường truy cập từ workload nội bộ bị bỏ khỏi phạm vi.
Một finding được xếp ưu tiên theo mức độ nghiêm trọng kỹ thuật mà không xét khả năng tiếp cận, mức nhạy cảm dữ liệu, quyền có thể đạt được và tác động kinh doanh.
Attack path từ tài khoản developer đến secret CI, registry image, cluster deploy role và database production gồm nhiều bước nhỏ; mỗi nhóm chỉ đánh giá quyền trong hệ thống mình phụ trách.
Một thay đổi DNS và routing được triển khai để chuyển vùng dự phòng; luồng mới vô tình cho phép truy cập trực tiếp backend bỏ qua WAF và API gateway.
Đội nền tảng tự động tạo ephemeral environment cho mỗi pull request; môi trường có public endpoint và dữ liệu sao chép nhưng không có lịch tự hủy hoặc cập nhật inventory.
Một dự án mua lại công ty khác và kết nối hai mạng qua VPN site-to-site; các dải mạng, DNS trust và tài khoản quản trị được nối với nhau trước khi hoàn tất đánh giá attack surface.
Máy chủ cũ được decommission khỏi hệ thống giám sát nhưng vẫn còn bản ghi DNS, firewall rule và credential tích hợp; các đường truy cập tồn dư không được phát hiện.
Nhóm bảo mật so sánh attack surface giữa hai kỳ đánh giá nhưng công cụ đổi cách chuẩn hóa hostname và asset ID; báo cáo cho thấy số lượng giảm dù tài sản thực tế không thay đổi.
Continuous discovery phát hiện endpoint mới nhưng không gắn owner hoặc phân loại dữ liệu; cảnh báo được gửi nhiều lần và cuối cùng bị bỏ qua do thiếu ngữ cảnh ưu tiên.
Một API mới được thêm sau release nhưng không kích hoạt quy trình review; không có thay đổi trong ticket kiến trúc nên nhóm assurance không biết phạm vi kiểm thử cần mở rộng.
Một ứng dụng dùng nhiều tenant nhưng API gateway chỉ xác thực người gọi; sơ đồ attack surface không biểu diễn ranh giới tenant và các đường truy cập chéo qua object identifier.
Một đối tác được cấp VPN và tài khoản hỗ trợ trong thời gian triển khai; sau khi dự án kết thúc, các đường truy cập và quyền tạm thời vẫn hoạt động.
Một bản đồ attack surface liệt kê đầy đủ hostname và port nhưng thiếu luồng dữ liệu, danh tính dịch vụ và trust boundary; nhóm không thể xác định đường đi từ điểm vào đến tài sản nhạy cảm.
Một nhóm muốn giới hạn penetration test vào một số hostname đã biết; các hostname có thể chuyển hướng sang tài sản mới trong thời gian kiểm thử và chưa có quy tắc xác nhận phạm vi an toàn.
Một thay đổi cấu hình WAF giảm false positive nhưng đồng thời bỏ qua một nhóm route nhạy cảm; việc đánh giá thay đổi không so sánh lại các điểm vào và attack path liên quan.
