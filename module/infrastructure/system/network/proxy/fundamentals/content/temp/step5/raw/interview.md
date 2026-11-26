Bạn sẽ dựa trên những yêu cầu nào để quyết định triển khai proxy giữa client và dịch vụ đích?
Bạn sẽ giải thích proxy khác với kết nối trực tiếp client-server về đường đi của request và quyền kiểm soát lưu lượng như thế nào?
Bạn sẽ phân biệt forward proxy và reverse proxy thông qua vị trí triển khai, đối tượng sử dụng và mục đích hoạt động ra sao?
Bạn sẽ so sánh proxy, NAT, firewall và load balancer để xác định thành phần phù hợp cho một kiến trúc mạng như thế nào?
Bạn sẽ giải thích vai trò của proxy tại tầng ứng dụng so với thiết bị chuyển tiếp lưu lượng ở tầng mạng như thế nào?
Bạn sẽ mô tả luồng request và response đi qua hai lớp proxy liên tiếp từ client đến backend ra sao?
Bạn sẽ xác định những trách nhiệm nào nên đặt tại proxy và những trách nhiệm nào thuộc về ứng dụng backend?
Bạn sẽ cân nhắc triển khai một proxy tập trung hay nhiều proxy theo từng miền dịch vụ dựa trên tiêu chí nào?
Bạn sẽ lựa chọn proxy đặt ở biên Internet, trong mạng nội bộ hoặc bên cạnh ứng dụng theo các ràng buộc nào?
Bạn sẽ giải thích các nguy cơ khi biến một proxy thành điểm lỗi đơn cho toàn bộ hệ thống như thế nào?
Bạn sẽ xác định chỉ số thông lượng, độ trễ và số kết nối cần thu thập trước khi thiết kế proxy như thế nào?
Bạn sẽ so sánh ưu nhược điểm của cấu hình proxy tĩnh và quản lý cấu hình bằng service discovery ra sao?
Bạn sẽ lựa chọn giữa proxy tự quản lý và dịch vụ proxy được quản lý dựa trên khả năng vận hành, chi phí và giới hạn kiểm soát như thế nào?
Bạn sẽ thiết kế sơ đồ phân tách traffic inbound và outbound để kiểm soát những đường đi nào?
Bạn sẽ phân tích ảnh hưởng của nhiều hop proxy đến độ trễ, quan sát log và xử lý sự cố như thế nào?
Bạn sẽ mô tả cách ứng dụng hoặc trình duyệt được cấu hình sử dụng một forward proxy tường minh như thế nào?
Bạn sẽ phân biệt forward proxy tường minh và transparent proxy về cách client nhận biết và giới hạn giao thức ra sao?
Bạn sẽ giải thích cơ chế HTTP CONNECT giúp client thiết lập một đường hầm đến máy chủ đích như thế nào?
Bạn sẽ phân biệt chuyển tiếp HTTP thông thường với HTTPS tunneling qua CONNECT khi xét khả năng nhìn thấy nội dung như thế nào?
Bạn sẽ giải thích sự khác nhau giữa tunnel và giải mã kiểm tra TLS tại proxy về bảo mật và quyền riêng tư ra sao?
Bạn sẽ xác định điều kiện nào khiến một proxy không thể đọc được path, header hoặc body của HTTPS request?
Bạn sẽ thiết kế chính sách truy cập Internet qua forward proxy theo tài khoản, nhóm người dùng và domain như thế nào?
Bạn sẽ kiểm soát truy cập đến cổng hoặc địa chỉ IP không được phép qua HTTP CONNECT như thế nào?
Bạn sẽ lựa chọn quy tắc bypass proxy cho tài nguyên nội bộ mà vẫn tránh tạo lỗ hổng kiểm soát ra sao?
Bạn sẽ phân biệt biến môi trường HTTP_PROXY, HTTPS_PROXY và NO_PROXY trong việc điều khiển kết nối từ ứng dụng như thế nào?
Bạn sẽ kiểm tra vì sao một ứng dụng dùng forward proxy thành công nhưng ứng dụng khác bỏ qua cấu hình proxy ra sao?
Bạn sẽ đánh giá lợi ích và giới hạn của PAC file hoặc WPAD khi tự động chọn proxy cho nhiều client như thế nào?
Bạn sẽ thiết kế proxy outbound cho dịch vụ chạy trong mạng riêng nhưng cần truy cập API bên ngoài ra sao?
Bạn sẽ theo dõi và giới hạn lưu lượng ra ngoài theo đích để kiểm tra bất thường hoặc ngăn lạm dụng như thế nào?
Bạn sẽ xử lý trường hợp forward proxy phải truy cập tài nguyên dùng IPv6 trong khi môi trường có cả IPv4 như thế nào?
Bạn sẽ mô tả cách reverse proxy nhận request theo hostname và chuyển đến backend tương ứng như thế nào?
Bạn sẽ thiết kế reverse proxy công khai nhiều website trên cùng địa chỉ IP bằng Host header và SNI ra sao?
Bạn sẽ phân biệt virtual host routing theo domain với path-based routing khi các ứng dụng có đường dẫn trùng nhau như thế nào?
Bạn sẽ tổ chức path prefix và rewrite rule để backend nhận đúng đường dẫn mong đợi như thế nào?
Bạn sẽ phát hiện lỗi double-prefix hoặc missing-prefix khi reverse proxy chuyển tiếp đường dẫn như thế nào?
Bạn sẽ thiết kế quy tắc redirect từ HTTP sang HTTPS ở proxy mà không tạo vòng lặp chuyển hướng ra sao?
Bạn sẽ phân tích khác biệt giữa client URL và upstream URL khi backend sinh link tuyệt đối hoặc chuyển hướng như thế nào?
Bạn sẽ lựa chọn chính sách giữ nguyên Host header hay thay thành hostname backend theo yêu cầu ứng dụng ra sao?
Bạn sẽ xây dựng health check cho upstream để ngừng gửi lưu lượng đến backend không đáp ứng như thế nào?
Bạn sẽ phân biệt active health check và passive health check khi chọn endpoint còn khỏe mạnh như thế nào?
Bạn sẽ cấu hình reverse proxy phục vụ file tĩnh và chuyển tiếp API động theo yêu cầu hiệu năng ra sao?
Bạn sẽ cân nhắc đặt chức năng nén response tại reverse proxy, backend hay client dựa trên chi phí và khả năng tương thích ra sao?
Bạn sẽ tổ chức nhiều reverse proxy trước backend để đảm bảo sẵn sàng cao và giảm rủi ro thay đổi cấu hình ra sao?
Bạn sẽ xác định những giới hạn khi reverse proxy phải chuyển tiếp WebSocket, Server-Sent Events hoặc long polling như thế nào?
Bạn sẽ thiết kế proxy cho kết nối gRPC hoặc HTTP/2 mà vẫn bảo đảm hỗ trợ streaming và metadata ra sao?
Bạn sẽ giải thích cách proxy ở Layer 4 khác với Layer 7 trong quyết định định tuyến và quan sát nội dung như thế nào?
Bạn sẽ so sánh TCP proxy và HTTP reverse proxy trong việc kiểm tra request, giữ kết nối và trả lỗi cho client ra sao?
Bạn sẽ xử lý một kết nối TCP tồn tại lâu khi upstream bị thay thế hoặc proxy cần khởi động lại như thế nào?
Bạn sẽ phân biệt HTTP/1.1 keep-alive và HTTP/2 multiplexing khi proxy quản lý số kết nối ra sao?
Bạn sẽ lựa chọn cấu hình connection pool và connection reuse từ proxy đến upstream để giảm chi phí bắt tay như thế nào?
Bạn sẽ giải thích sự khác nhau giữa end-to-end header và hop-by-hop header khi chuyển tiếp qua proxy như thế nào?
Bạn sẽ xử lý các header Connection, Keep-Alive và Transfer-Encoding để tránh chuyển tiếp sai ngữ nghĩa HTTP ra sao?
Bạn sẽ xây dựng quy tắc giữ nguyên hoặc cập nhật X-Forwarded-For, X-Forwarded-Proto và X-Forwarded-Host trên từng hop proxy ra sao?
Bạn sẽ mô tả cách tạo và đọc chuỗi X-Forwarded-For qua nhiều proxy mà không đánh mất địa chỉ nguồn tin cậy ra sao?
Bạn sẽ xác định danh sách trusted proxies trước khi sử dụng địa chỉ IP từ forwarded headers cho phân quyền như thế nào?
Bạn sẽ phân biệt header Forwarded theo chuẩn với các header X-Forwarded-* về cấu trúc và khả năng tương thích ra sao?
Bạn sẽ thiết kế cách truyền trace ID hoặc request ID xuyên qua proxy và backend để theo dõi một request như thế nào?
Bạn sẽ xử lý trường hợp client tự gửi X-Forwarded-For hoặc X-Request-ID nhằm giả mạo thông tin do proxy tạo ra sao?
Bạn sẽ giải thích PROXY protocol giúp truyền địa chỉ nguồn qua TCP proxy trong những tình huống nào?
Bạn sẽ kiểm tra lỗi khi một upstream không hỗ trợ PROXY protocol nhưng proxy vẫn gửi phần mở đầu giao thức đó như thế nào?
Bạn sẽ đánh giá tác động của việc thay đổi Content-Length, chunked transfer và request buffering đến ứng dụng ra sao?
Bạn sẽ lựa chọn buffering request body tại proxy hay truyền theo luồng đối với upload dung lượng lớn như thế nào?
Bạn sẽ xác định giới hạn kích thước header, body và URL để bảo vệ proxy nhưng không chặn yêu cầu hợp lệ ra sao?
Bạn sẽ phát hiện và xử lý khác biệt cách parse HTTP giữa proxy và backend có nguy cơ gây request smuggling như thế nào?
Bạn sẽ phân biệt HTTP 400, 413, 431 và 502 theo thành phần phát hiện lỗi và nguyên nhân thường gặp ra sao?
Bạn sẽ xác định cách proxy xử lý DNS lookup cho upstream khi địa chỉ backend thay đổi theo thời gian như thế nào?
Bạn sẽ phân tích tình huống proxy vẫn sử dụng IP cũ dù DNS upstream đã cập nhật và đưa ra cách khắc phục ra sao?
Bạn sẽ mô tả luồng TLS handshake khi reverse proxy thực hiện TLS termination trước backend như thế nào?
Bạn sẽ quyết định điểm kết thúc TLS tại load balancer, reverse proxy hoặc backend dựa trên yêu cầu tin cậy nào?
Bạn sẽ thiết kế re-encryption từ reverse proxy đến backend để bảo vệ dữ liệu đi qua mạng nội bộ như thế nào?
Bạn sẽ phân biệt TLS passthrough và TLS termination về khả năng định tuyến theo Host/path và quan sát traffic ra sao?
Bạn sẽ giải thích SNI giúp proxy chọn chứng chỉ hoặc upstream cho nhiều hostname trên cùng cổng như thế nào?
Bạn sẽ triển khai chính sách xác thực chứng chỉ backend khi proxy kết nối TLS upstream để tránh giả mạo dịch vụ ra sao?
Bạn sẽ lựa chọn cơ chế mutual TLS giữa proxy và backend để xác minh danh tính hai đầu kết nối như thế nào?
Bạn sẽ quản lý gia hạn, thay khóa và triển khai chứng chỉ TLS ở proxy để tránh gián đoạn dịch vụ ra sao?
Bạn sẽ kiểm tra lỗi chứng chỉ không khớp hostname khi proxy dùng một tên để định tuyến nhưng kết nối đến tên khác như thế nào?
Bạn sẽ đánh giá tác động của TLS session resumption và kết nối dài đến CPU và độ trễ proxy ra sao?
Bạn sẽ lựa chọn chính sách HSTS và redirect HTTPS ở proxy dựa trên yêu cầu bảo mật và giai đoạn triển khai ra sao?
Bạn sẽ xử lý kết nối từ client dùng TLS phiên bản cũ theo yêu cầu bảo mật và tính tương thích như thế nào?
Bạn sẽ phân biệt lỗi TLS handshake phía client-proxy với lỗi TLS handshake phía proxy-backend qua log và phép thử nào?
Bạn sẽ giải thích caching tại forward proxy và reverse proxy phục vụ những mục tiêu hiệu năng khác nhau như thế nào?
Bạn sẽ đánh giá tính hợp lệ của việc cache một response dựa trên HTTP method, status code và Cache-Control ra sao?
Bạn sẽ phân biệt public, private, no-store và no-cache khi thiết kế chính sách cache qua proxy ra sao?
Bạn sẽ xử lý Vary và các header thương lượng nội dung để tránh phục vụ sai phiên bản response được cache như thế nào?
Bạn sẽ giải thích vai trò của ETag và Last-Modified khi proxy gửi conditional request đến upstream như thế nào?
Bạn sẽ đánh giá cách TTL của cache và chính sách hết hạn ảnh hưởng đến độ mới dữ liệu và tải backend ra sao?
Bạn sẽ thiết kế cache key có xét hostname, path, query parameter và header cần thiết như thế nào?
Bạn sẽ ngăn dữ liệu cá nhân hoặc response đã xác thực bị đưa vào cache dùng chung cho nhiều người dùng ra sao?
Bạn sẽ giải thích cache hit, cache miss, stale response và revalidation trong một request đi qua proxy như thế nào?
Bạn sẽ xử lý cache stampede khi một nội dung phổ biến hết hạn và nhiều client đồng thời truy cập như thế nào?
Bạn sẽ thiết kế cache purge hoặc invalidation khi backend cập nhật dữ liệu cần hiển thị ngay như thế nào?
Bạn sẽ lựa chọn stale-while-revalidate hoặc stale-if-error theo yêu cầu về độ mới dữ liệu và khả năng phục vụ ra sao?
Bạn sẽ đo hiệu quả cache bằng hit ratio, byte hit ratio và độ trễ backend được giảm như thế nào?
Bạn sẽ phân tích trường hợp response không được cache dù cấu hình proxy cho phép cache để tìm nguyên nhân ra sao?
Bạn sẽ đánh giá cache dung lượng lớn có gây cạnh tranh bộ nhớ, dung lượng đĩa hoặc I/O với hoạt động proxy như thế nào?
Bạn sẽ lựa chọn thuật toán round robin, least connections hay weighted load balancing dựa trên đặc điểm upstream ra sao?
Bạn sẽ thiết kế upstream pool với các backend có năng lực xử lý khác nhau để phân phối tải hợp lý như thế nào?
Bạn sẽ phân biệt cân bằng tải theo request và theo kết nối khi client giữ nhiều kết nối lâu như thế nào?
Bạn sẽ đánh giá ảnh hưởng của session affinity đến khả năng mở rộng và phục hồi khi một backend hỏng ra sao?
Bạn sẽ thiết lập timeout kết nối, timeout đọc và idle timeout riêng cho từng nhóm backend như thế nào?
Bạn sẽ phân biệt timeout của proxy, timeout của backend và timeout của client khi request thất bại như thế nào?
Bạn sẽ lựa chọn retry tự động ở proxy dựa trên loại lỗi và tính idempotent của request ra sao?
Bạn sẽ thiết kế retry budget, backoff và giới hạn số lần thử để tránh làm quá tải backend đang gặp lỗi như thế nào?
Bạn sẽ giải thích vì sao retry một HTTP POST có thể tạo giao dịch trùng nếu backend chưa có cơ chế bảo vệ ra sao?
Bạn sẽ triển khai circuit breaker hoặc giới hạn kết nối để ngăn một upstream lỗi làm ảnh hưởng toàn bộ hệ thống như thế nào?
Bạn sẽ xử lý tình huống tất cả backend trong upstream pool không còn healthy và trả kết quả cho client như thế nào?
Bạn sẽ định nghĩa hành vi drain kết nối khi cần đưa một backend ra khỏi nhóm để bảo trì như thế nào?
Bạn sẽ thiết kế chính sách giới hạn truy cập theo IP, tài khoản hoặc đường dẫn mà không nhầm địa chỉ thật của client ra sao?
Bạn sẽ phân biệt proxy authentication với authentication của ứng dụng đích theo phạm vi quyền hạn như thế nào?
Bạn sẽ giải thích vai trò của HTTP 407 Proxy Authentication Required so với HTTP 401 trong tình huống nào?
Bạn sẽ tổ chức danh sách cho phép và chặn theo domain, IP hoặc mạng CIDR cho forward proxy như thế nào?
Bạn sẽ ngăn forward proxy trở thành open proxy cho các client không được cấp quyền như thế nào?
Bạn sẽ thiết kế xác thực hoặc hạn chế mạng để chỉ reverse proxy mới có thể gọi trực tiếp backend ra sao?
Bạn sẽ bảo vệ proxy khỏi truy cập đến metadata endpoint, địa chỉ loopback hoặc tài nguyên nội bộ ngoài ý muốn như thế nào?
Bạn sẽ lựa chọn cách lọc Host header và đường dẫn bất thường để giảm nguy cơ chuyển request sai upstream ra sao?
Bạn sẽ kiểm soát header chứa token, cookie hoặc thông tin cá nhân trước khi ghi access log hay gửi sang upstream như thế nào?
Bạn sẽ xác định giới hạn của việc kiểm tra nội dung HTTPS khi proxy chỉ thực hiện TCP tunneling như thế nào?
Bạn sẽ phân biệt chính sách bảo mật đặt ở proxy và các kiểm tra phân quyền bắt buộc phải duy trì trong backend như thế nào?
Bạn sẽ cấu hình bảo vệ giao diện quản trị và quyền thay đổi cấu hình proxy theo nhóm người vận hành ra sao?
Bạn sẽ phát hiện và giảm thiểu tác động của nhiều client gửi request chậm hoặc giữ kết nối lâu gây cạn tài nguyên proxy như thế nào?
Bạn sẽ xác định những metric nào phản ánh request rate, active connections, queue depth và trạng thái upstream của proxy?
Bạn sẽ sử dụng access log và error log để tái hiện đường đi của một request qua nhiều lớp proxy như thế nào?
Bạn sẽ phân biệt tổng thời gian xử lý tại proxy với thời gian kết nối và thời gian phản hồi upstream bằng metric nào?
Bạn sẽ thiết kế dashboard cho HTTP 4xx, 5xx, 499 hoặc mã tương đương theo route và upstream ra sao?
Bạn sẽ đánh giá p95 và p99 latency của proxy để tìm các request bất thường mà số trung bình che khuất như thế nào?
Bạn sẽ giới hạn nhãn metric và nội dung log để tránh dữ liệu có cardinality cao hoặc lộ thông tin nhạy cảm ra sao?
Bạn sẽ sử dụng correlation ID và distributed tracing để xác định độ trễ tăng tại lớp proxy hay backend như thế nào?
Bạn sẽ kiểm tra kết nối từ client đến proxy bằng curl và các tùy chọn chỉ định proxy như thế nào?
Bạn sẽ dùng curl để phân biệt lỗi kết nối đến forward proxy, lỗi CONNECT và lỗi TLS với máy chủ đích ra sao?
Bạn sẽ kết hợp dig hoặc nslookup, traceroute và tcpdump để xác định nơi thất bại trong chuỗi proxy như thế nào?
Bạn sẽ phân tích packet capture để phát hiện TCP reset, retransmission hoặc handshake timeout giữa proxy và upstream ra sao?
Bạn sẽ giải thích ý nghĩa của các mã HTTP 502, 503 và 504 khi reverse proxy gặp những loại lỗi upstream nào?
Bạn sẽ thiết kế kiểm thử tải để tìm giới hạn CPU, TLS handshake, connection pool và băng thông của proxy như thế nào?
Bạn sẽ xác định ngưỡng cảnh báo khi upstream liên tục bị đánh dấu unhealthy hoặc tỷ lệ kết nối thất bại tăng ra sao?
Bạn sẽ quản lý thay đổi cấu hình proxy bằng kiểm tra cú pháp, cấu hình phiên bản và rollback như thế nào?
Bạn sẽ triển khai thay đổi cấu hình hoặc reload proxy mà vẫn giữ các kết nối đang phục vụ ra sao?
Bạn sẽ phân biệt các bước chẩn đoán khi reverse proxy trả về trang mặc định thay vì website đúng hostname như thế nào?
Nếu client truy cập website trực tiếp thành công nhưng qua forward proxy bị HTTP 407, bạn sẽ lần theo cấu hình xác thực và quyền truy cập ra sao?
Nếu ứng dụng báo sai địa chỉ IP người dùng khi đi qua hai reverse proxy, bạn sẽ kiểm tra chuỗi forwarded headers và trust boundary như thế nào?
Nếu website liên tục redirect giữa HTTP và HTTPS sau khi thêm reverse proxy, bạn sẽ kiểm tra những thành phần nào?
Nếu một file tải lên lớn thất bại tại proxy nhưng upload trực tiếp backend thành công, bạn sẽ điều tra giới hạn kích thước và buffering ra sao?
Nếu reverse proxy trả HTTP 504 vào giờ cao điểm, bạn sẽ phân biệt thiếu tài nguyên proxy, nghẽn mạng và backend xử lý chậm như thế nào?
Nếu cache phục vụ nội dung của tài khoản này cho tài khoản khác, bạn sẽ khôi phục an toàn và sửa cache policy như thế nào?
Nếu backend được thay IP sau khi triển khai mà proxy vẫn gọi địa chỉ cũ, bạn sẽ kiểm tra DNS caching và service discovery ra sao?
Nếu kết nối WebSocket ngắt đúng một khoảng thời gian cố định, bạn sẽ kiểm tra idle timeout và connection upgrade ở những lớp nào?
Bạn sẽ đề xuất kiến trúc kết hợp forward proxy cho lưu lượng outbound và reverse proxy cho dịch vụ công khai với TLS, cache, cân bằng tải và giám sát như thế nào?
