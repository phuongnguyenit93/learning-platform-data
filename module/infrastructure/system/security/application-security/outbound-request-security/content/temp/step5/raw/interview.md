Bạn xác định những chức năng ứng dụng nào tạo ra outbound HTTP request và vì sao mỗi chức năng cần được xem xét dưới góc độ SSRF?
Bạn mô tả SSRF và phân biệt server-side request forgery với client-side request forgery theo vị trí thực hiện request như thế nào?
Bạn phân tích những rủi ro khi ứng dụng tải ảnh, tạo preview URL, nhập webhook hoặc đọc tài liệu từ địa chỉ do người dùng cung cấp như thế nào?
Bạn xây dựng mô hình đe dọa cho một tính năng fetch URL để xác định tài nguyên nội bộ hoặc dữ liệu nhạy cảm có thể bị truy cập ra sao?
Bạn phân biệt SSRF có thể đọc response với SSRF blind chỉ quan sát được tác động phụ và lựa chọn tín hiệu phát hiện phù hợp như thế nào?
Bạn xác định vì sao kiểm tra URL bằng một biểu thức chính quy đơn giản không đủ để ngăn SSRF như thế nào?
Bạn lựa chọn parser URL chuẩn và quy trình canonicalization để các lớp kiểm tra và HTTP client diễn giải cùng một đích đến như thế nào?
Bạn kiểm tra parser mà lớp validation sử dụng có cùng cách diễn giải URL với HTTP client thực tế hay không bằng cách nào?
Bạn xử lý scheme, hostname, port, userinfo, path, query và fragment khi phân tích URL đầu vào như thế nào?
Bạn kiểm soát URL chứa username hoặc password trước dấu @ để tránh nhầm lẫn giữa phần userinfo và hostname như thế nào?
Bạn chuẩn hóa hostname về chữ thường, IDN hoặc punycode và xử lý dấu chấm cuối tên miền trước khi so khớp allowlist như thế nào?
Bạn xác định rủi ro từ URL có percent-encoding, dấu gạch chéo ngược hoặc ký tự Unicode khiến parser khác nhau diễn giải khác nhau như thế nào?
Bạn phân biệt hostname chính xác với kiểm tra suffix để tránh cho phép nhầm tên miền có phần cuối giống domain tin cậy như thế nào?
Bạn thiết kế allowlist hostname và port để hỗ trợ các dịch vụ đối tác cần thiết mà không cho phép toàn bộ domain hoặc cổng tùy ý như thế nào?
Bạn lựa chọn scheme được phép cho outbound request và giải thích vì sao thường cần giới hạn vào HTTPS hoặc một tập giao thức rất nhỏ như thế nào?
Bạn xử lý URL dùng IP literal thay vì hostname để bảo đảm chính sách đích đến vẫn được áp dụng như thế nào?
Bạn nhận diện địa chỉ IPv4 private, loopback, link-local, multicast, unspecified và các dải không thể định tuyến công khai để từ chối truy cập như thế nào?
Bạn đánh giá các dải IPv6 loopback, link-local, unique-local, multicast và IPv4-mapped IPv6 trong chính sách chống SSRF như thế nào?
Bạn xử lý địa chỉ IP biểu diễn ở dạng thập phân, bát phân, hexadecimal hoặc dạng rút gọn để tránh parser và validator hiểu khác nhau như thế nào?
Bạn quyết định cách xử lý hostname có nhiều bản ghi A hoặc AAAA khi chỉ một địa chỉ phân giải nằm trong dải bị cấm như thế nào?
Bạn kiểm tra toàn bộ chuỗi CNAME và kết quả DNS cuối cùng trước khi cho phép kết nối tới hostname như thế nào?
Bạn giải thích DNS rebinding và vì sao kiểm tra hostname một lần trước request vẫn có thể bị vượt qua như thế nào?
Bạn ngăn TOCTOU giữa thời điểm validate DNS và thời điểm HTTP client thực sự kết nối tới địa chỉ IP như thế nào?
Bạn thiết kế cơ chế pin kết quả DNS đã kiểm tra vào kết nối nhưng vẫn giữ đúng Host header, SNI và hostname verification của TLS như thế nào?
Bạn xác định cách xử lý DNS cache, connection pool và DNS refresh để địa chỉ đích không thay đổi ngoài chính sách đã duyệt như thế nào?
Bạn đánh giá rủi ro khi DNS resolver nội bộ, proxy hoặc service mesh phân giải hostname khác với resolver mà ứng dụng đã dùng để validate như thế nào?
Bạn phân biệt kiểm tra địa chỉ đích trước kết nối với kiểm soát network egress ở tầng hạ tầng và giải thích vì sao cần phối hợp cả hai như thế nào?
Bạn xác định các địa chỉ metadata của cloud, control plane, loopback và endpoint quản trị nào cần được bảo vệ khỏi outbound request do người dùng kích hoạt như thế nào?
Bạn thiết kế chính sách chặn truy cập tới metadata service và các mạng quản trị mà không làm gián đoạn workload hợp lệ như thế nào?
Bạn kết hợp chặn egress tới metadata service với cơ chế bảo vệ metadata ở nền tảng cloud như token bắt buộc và hop limit như thế nào?
Bạn lựa chọn network segmentation, firewall rule, egress gateway hoặc Kubernetes NetworkPolicy để giới hạn nơi ứng dụng được phép kết nối như thế nào?
Bạn phân biệt allowlist ở tầng ứng dụng với egress allowlist ở firewall hoặc service mesh về khả năng bao phủ và nguy cơ bypass như thế nào?
Bạn xử lý trường hợp ứng dụng dùng HTTP proxy hoặc proxy được cấu hình qua biến môi trường khiến kết nối thực tế đi qua một đường khác như thế nào?
Bạn kiểm soát proxy bypass, NO_PROXY và cấu hình proxy theo từng môi trường để không tạo đường đi ngoài chính sách egress như thế nào?
Bạn thiết kế egress gateway tập trung để áp dụng allowlist hostname, logging và giới hạn lưu lượng cho nhiều dịch vụ như thế nào?
Bạn xác định cách ngăn ứng dụng truy cập trực tiếp mạng nội bộ khi outbound traffic bắt buộc phải đi qua proxy được kiểm soát như thế nào?
Bạn đánh giá rủi ro SSRF tới dịch vụ nội bộ dùng xác thực dựa trên network location hoặc trust nội bộ như thế nào?
Bạn xác định chính sách xử lý redirect khi HTTP client nhận mã 301, 302, 303, 307 hoặc 308 từ máy chủ bên ngoài như thế nào?
Bạn kiểm tra lại scheme, hostname, port và DNS của từng Location redirect trước khi cho phép request tiếp theo như thế nào?
Bạn giới hạn số hop redirect và phát hiện redirect loop để tránh request kéo dài hoặc vượt khỏi phạm vi đích đã duyệt như thế nào?
Bạn xử lý relative redirect và canonicalize URL đích mới trước khi áp dụng lại chính sách outbound như thế nào?
Bạn ngăn redirect từ một hostname công khai được cho phép sang địa chỉ loopback, private hoặc metadata như thế nào?
Bạn xác định khi nào nên tắt automatic redirect của HTTP client và tự điều khiển từng bước redirect để bảo đảm kiểm tra đích đến như thế nào?
Bạn rà soát cấu hình redirect, proxy và DNS của JDK HttpClient, Apache HttpClient hoặc Spring WebClient để bảo đảm chúng không bỏ qua outbound policy như thế nào?
Bạn kiểm soát việc chuyển tiếp Authorization header, cookie và custom credential khi redirect sang origin khác như thế nào?
Bạn phân biệt hành vi chuyển method và body giữa các mã redirect 301, 302, 303, 307 và 308 khi đánh giá tác động bảo mật như thế nào?
Bạn thiết kế policy để redirect không thể thay đổi đích đến hoặc phương thức ngoài ý định nghiệp vụ như thế nào?
Bạn xác minh chứng chỉ TLS, hostname và chuỗi tin cậy cho outbound HTTPS request như thế nào?
Bạn giải thích vì sao tắt certificate validation hoặc chấp nhận mọi hostname làm mất khả năng chống giả mạo máy chủ như thế nào?
Bạn xử lý SNI, hostname verification và kết nối tới IP đã pin để vừa chống DNS rebinding vừa xác thực đúng máy chủ như thế nào?
Bạn lựa chọn trust store và quản lý CA nội bộ cho outbound request đến dịch vụ đối tác hoặc dịch vụ doanh nghiệp như thế nào?
Bạn thiết kế mTLS cho outbound request khi dịch vụ đích yêu cầu xác thực client certificate như thế nào?
Bạn quản lý vòng đời client certificate, private key và secret dùng cho outbound request để tránh rò rỉ credential như thế nào?
Bạn xác định cách giới hạn credential theo hostname, service hoặc audience để token của một đối tác không bị gửi sang đích khác như thế nào?
Bạn ngăn token, API key, cookie hoặc thông tin xác thực bị rò rỉ qua URL query, redirect, exception message hoặc access log như thế nào?
Bạn lựa chọn header được phép gửi ra ngoài thay vì chuyển tiếp toàn bộ header từ inbound request để giảm nguy cơ credential leakage như thế nào?
Bạn kiểm soát việc forward X-Forwarded-For, Host, Authorization và các header do client tự cung cấp khi tạo outbound request như thế nào?
Bạn xác định khi nào cần xóa inbound cookies và headers trước khi gọi dịch vụ bên ngoài để tránh chuyển tiếp danh tính người dùng ngoài ý muốn như thế nào?
Bạn thiết kế quản lý secret và token cho webhook hoặc tích hợp đối tác để credential không bị gắn cố định vào URL hoặc source code như thế nào?
Bạn giới hạn HTTP method, request body size và content type được phép khi ứng dụng gửi dữ liệu tới một URL được người dùng cấu hình như thế nào?
Bạn kiểm tra nội dung response theo Content-Type và định dạng mong đợi trước khi chuyển cho parser hoặc thành phần xử lý tiếp theo như thế nào?
Bạn cấu hình XML hoặc HTML parser để response không tin cậy không kích hoạt external entity resolution hoặc tải tài nguyên phụ ngoài chính sách như thế nào?
Bạn giới hạn response body theo số byte thực tế sau giải nén để phòng response quá lớn hoặc compression bomb như thế nào?
Bạn thiết lập connect timeout, read timeout, request deadline và tổng thời gian xử lý để outbound request không chiếm tài nguyên vô hạn như thế nào?
Bạn giới hạn số redirect, số kết nối đồng thời và tốc độ request theo người dùng hoặc tích hợp để chống cạn kiệt tài nguyên như thế nào?
Bạn xử lý response stream lớn theo kiểu streaming có giới hạn và bảo đảm đóng body hoặc giải phóng connection khi xảy ra lỗi như thế nào?
Bạn phân biệt timeout kết nối, timeout đọc dữ liệu và timeout tổng thể để xác định đúng nguyên nhân một outbound request bị treo như thế nào?
Bạn đánh giá rủi ro khi retry outbound request có side effect và thiết kế idempotency hoặc retry policy an toàn như thế nào?
Bạn giới hạn retry theo lỗi tạm thời, exponential backoff và retry budget để một sự cố đích đến không tạo request storm như thế nào?
Bạn thiết kế circuit breaker và bulkhead cho outbound integration để lỗi một đối tác không làm cạn thread hoặc connection của toàn ứng dụng như thế nào?
Bạn ghi log và audit outbound request đủ để điều tra đích đến, kết quả và thời gian mà không lưu token hoặc response nhạy cảm như thế nào?
Bạn xây dựng metric theo hostname đã phân loại, status code, latency và lỗi kết nối mà không đưa URL hoặc dữ liệu người dùng vào label như thế nào?
Bạn sử dụng trace để theo dõi outbound dependency và xác định request nội bộ nào đã kích hoạt kết nối tới đích ngoài như thế nào?
Bạn thiết kế allowlist theo chức năng nghiệp vụ và chủ sở hữu tích hợp để có thể rà soát, hết hạn và thu hồi quyền truy cập đích đến như thế nào?
Bạn quản lý ngoại lệ cho một endpoint đối tác mới với phạm vi hostname, port, path và thời hạn cụ thể như thế nào?
Bạn kiểm soát thay đổi allowlist và egress policy qua review, version control và kiểm thử tự động như thế nào?
Bạn xây dựng outbound HTTP client wrapper dùng chung để mọi module áp dụng cùng URL validation, redirect policy, TLS và giới hạn tài nguyên như thế nào?
Bạn xác định cách kiểm thử URL parser differential bằng các bộ URL tổng hợp có encoding, IDN, IP literal và redirect mà không gửi request ra mạng thật như thế nào?
Bạn xây dựng kiểm thử DNS rebinding bằng resolver và server giả lập để xác nhận địa chỉ kết nối luôn thuộc tập IP đã được phê duyệt như thế nào?
Bạn kiểm thử redirect chain có đích công khai, đích nội bộ và nhiều bước để chứng minh mọi hop đều được validate như thế nào?
Bạn thiết kế kiểm thử chứng chỉ hết hạn, sai hostname, CA không tin cậy và mTLS thất bại để xác nhận TLS validation hoạt động như thế nào?
Bạn kiểm thử việc credential bị loại bỏ khi redirect đổi origin và xác minh token không xuất hiện trong log hoặc trace như thế nào?
Bạn sử dụng mock HTTP server, DNS fixture và network sandbox để kiểm thử SSRF mà không truy cập hệ thống nội bộ thật như thế nào?
Bạn đánh giá các đường tấn công SSRF qua webhook, URL preview, PDF/image fetcher, import file và callback integration như thế nào?
Bạn điều tra sự cố ứng dụng gọi được địa chỉ nội bộ dù URL allowlist chỉ chứa hostname công khai bằng cách kiểm tra parser, DNS, redirect và proxy như thế nào?
Bạn phân biệt lỗi outbound do DNS, TCP connect, TLS handshake, HTTP status và response parser bằng những bằng chứng nào?
Bạn xác định vì sao request đã qua URL validation nhưng kết nối cuối cùng vẫn tới IP ngoài dự kiến bằng cách đối chiếu DNS answer và socket peer address như thế nào?
Bạn xây dựng runbook khi phát hiện outbound request truy cập metadata endpoint hoặc mạng private để chặn, xác định phạm vi và thu hồi credential như thế nào?
Bạn xác lập tiêu chí nghiệm thu end-to-end để chứng minh outbound request chỉ tới đích được phép, xác minh TLS, giới hạn tài nguyên và không làm lộ dữ liệu như thế nào?
