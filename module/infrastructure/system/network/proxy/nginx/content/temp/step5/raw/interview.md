Bạn lựa chọn Nginx làm web server, reverse proxy hay load balancer dựa trên yêu cầu hệ thống như thế nào?
Bạn phân biệt nhiệm vụ của Nginx ở tầng HTTP với proxy hoạt động ở tầng TCP như thế nào?
Bạn mô tả đường đi của một HTTP request từ client qua Nginx đến backend và trở về như thế nào?
Bạn giải thích sự khác biệt giữa phục vụ file tĩnh trực tiếp và chuyển tiếp yêu cầu đến ứng dụng ra sao?
Bạn dựa vào những yêu cầu nào để quyết định đặt Nginx trước nhiều dịch vụ ứng dụng?
Bạn phân tích vai trò của master process và worker process đối với hoạt động của Nginx ra sao?
Bạn giải thích mô hình event-driven giúp Nginx xử lý nhiều kết nối đồng thời như thế nào?
Bạn xác định giới hạn thực tế của số kết nối Nginx từ worker, file descriptor và tài nguyên hệ điều hành ra sao?
Bạn lựa chọn cách tổ chức file cấu hình chính và các file include theo môi trường như thế nào?
Bạn xác định các context main, events, http, server và location khi đọc một cấu hình Nginx ra sao?
Bạn phân biệt phạm vi áp dụng và kế thừa directive giữa các context Nginx như thế nào?
Bạn kiểm tra một directive có hợp lệ trong context đang khai báo bằng cách nào?
Bạn nhận diện sự khác nhau giữa một cấu hình được include nhiều lần và các block server độc lập như thế nào?
Bạn sử dụng lệnh kiểm tra cú pháp và dump cấu hình hiệu lực trước khi triển khai bằng cách nào?
Bạn kiểm tra Nginx đang nạp file cấu hình nào khi có nhiều bản cài trên cùng máy ra sao?
Bạn xây dựng cấu trúc cấu hình có thể review, tái sử dụng và thay đổi an toàn như thế nào?
Bạn đánh giá ảnh hưởng của số worker và worker_connections lên tải thực tế ra sao?
Bạn xác định thời điểm cần tinh chỉnh giới hạn file descriptor của tiến trình Nginx như thế nào?
Bạn kiểm chứng Nginx đang lắng nghe đúng địa chỉ và cổng của dịch vụ bằng cách nào?
Bạn xác định lý do Nginx không khởi động được khi một cổng đã được tiến trình khác chiếm như thế nào?
Bạn thiết kế nhiều virtual host dùng chung một địa chỉ IP và cổng HTTPS như thế nào?
Bạn phân biệt cách Nginx chọn server block theo listen, server_name và default_server ra sao?
Bạn điều tra trường hợp request tới hostname hợp lệ nhưng Nginx trả nội dung của virtual host khác như thế nào?
Bạn thiết kế cấu hình catch-all cho host không được phép truy cập dịch vụ như thế nào?
Bạn phân biệt exact name, wildcard name và tên theo biểu thức chính quy trong server_name như thế nào?
Bạn kiểm tra request có Host header không như dự kiến hoặc Host header giả mạo bằng cách nào?
Bạn xác định ảnh hưởng của cấu hình listen IPv4 và IPv6 đến khả năng truy cập theo DNS như thế nào?
Bạn lựa chọn root và alias để ánh xạ đường dẫn URL tới file trên đĩa theo những nguyên tắc nào?
Bạn phân tích sự khác biệt giữa root và alias trong location prefix bằng một ví dụ đường dẫn như thế nào?
Bạn xử lý lỗi 404 do alias, dấu gạch chéo hoặc đường dẫn file được ghép sai như thế nào?
Bạn thiết kế location phục vụ tài nguyên tĩnh với cache header và quyền truy cập phù hợp ra sao?
Bạn sử dụng index và try_files để triển khai website tĩnh hoặc single-page application như thế nào?
Bạn phân biệt fallback của try_files với việc trả trực tiếp một mã lỗi HTTP như thế nào?
Bạn xác định nguyên nhân cấu hình SPA làm trả HTML cho yêu cầu tài nguyên JavaScript không tồn tại ra sao?
Bạn giới hạn quyền truy cập file ẩn và các thư mục chứa bí mật cấu hình như thế nào?
Bạn đánh giá rủi ro directory listing và lựa chọn cách cấu hình autoindex phù hợp ra sao?
Bạn xử lý quyền đọc file và quyền truy cập thư mục của worker Nginx khi gặp lỗi 403 như thế nào?
Bạn cấu hình trang lỗi tùy chỉnh mà vẫn giữ mã trạng thái chính xác như thế nào?
Bạn phân biệt rewrite URL với redirect HTTP về cách client nhìn thấy địa chỉ mới ra sao?
Bạn lựa chọn mã 301, 302, 307 hoặc 308 theo yêu cầu giữ phương thức và hành vi cache như thế nào?
Bạn thiết kế redirect từ HTTP sang HTTPS mà không gây vòng lặp chuyển hướng như thế nào?
Bạn xác định đường dẫn cuối cùng sau một chuỗi rewrite và internal redirect bằng cách nào?
Bạn phân tích thứ tự chọn location exact, prefix và regex khi nhiều location cùng khớp như thế nào?
Bạn xác định tác động của modifier ^~ và các location regex đối với rule prefix như thế nào?
Bạn kiểm tra vì sao một rule location tưởng đúng nhưng không được áp dụng trên request cụ thể ra sao?
Bạn tổ chức các route API, file tĩnh và trang fallback để tránh chồng lấn location như thế nào?
Bạn quyết định khi nào dùng map thay cho nhiều điều kiện if phức tạp trong Nginx như thế nào?
Bạn kiểm tra ảnh hưởng của regex và rewrite phức tạp lên khả năng bảo trì cấu hình như thế nào?
Bạn xác định các biến $host, $http_host, $request_uri và $uri khác nhau ra sao khi rewrite?
Bạn lựa chọn cách chuyển tiếp một prefix URL sang backend mà giữ hoặc bỏ prefix theo yêu cầu như thế nào?
Bạn phân tích dấu gạch chéo cuối trong proxy_pass và ảnh hưởng đến URI gửi lên backend ra sao?
Bạn xác định cách proxy_pass sử dụng URI khi location có hoặc không có rewrite như thế nào?
Bạn thiết kế reverse proxy cho một backend chỉ lắng nghe trên localhost như thế nào?
Bạn kiểm tra upstream HTTP hoạt động độc lập trước khi thêm Nginx làm lớp proxy ra sao?
Bạn phân biệt proxy_set_header Host và header Host mà upstream nhận khi proxy_pass như thế nào?
Bạn xác định những header nào cần chuyển tiếp để backend biết giao thức, host và IP client ban đầu ra sao?
Bạn xây dựng chuỗi X-Forwarded-For khi request đi qua nhiều proxy đáng tin cậy như thế nào?
Bạn phân biệt X-Forwarded-Proto và Forwarded trong trường hợp TLS được kết thúc tại Nginx ra sao?
Bạn ngăn backend tin một X-Forwarded-For do client tùy ý cung cấp như thế nào?
Bạn sử dụng cấu hình real IP để phục hồi IP client thật chỉ từ các proxy tin cậy ra sao?
Bạn đánh giá hậu quả khi backend tạo redirect sai giao thức vì không nhận được thông tin HTTPS như thế nào?
Bạn thiết kế reverse proxy cho API có path parameter và query string mà không làm thay đổi ý nghĩa request như thế nào?
Bạn xác định cách Nginx chuyển tiếp method, body và header trong request có nội dung lớn ra sao?
Bạn kiểm tra sự khác nhau giữa proxy_request_buffering và proxy_buffering theo hướng luồng dữ liệu như thế nào?
Bạn lựa chọn bật hoặc tắt request buffering khi backend cần nhận dữ liệu upload dạng streaming như thế nào?
Bạn đánh giá ảnh hưởng của response buffering đến latency, RAM và file tạm khi backend trả nội dung lớn ra sao?
Bạn xử lý lỗi 413 khi người dùng gửi file vượt quá giới hạn body Nginx như thế nào?
Bạn quyết định giới hạn client_max_body_size cho từng API hoặc virtual host dựa trên tiêu chí nào?
Bạn xác định nơi lưu file tạm của proxy và nguy cơ đầy đĩa khi lưu lượng tăng ra sao?
Bạn phân biệt proxy_connect_timeout, proxy_send_timeout và proxy_read_timeout trong các giai đoạn xử lý như thế nào?
Bạn điều tra request trả 504 sau một khoảng thời gian cố định bằng cách đối chiếu timeout ở các hop như thế nào?
Bạn phân biệt 502 do backend đóng kết nối sớm với 504 do quá thời gian chờ như thế nào?
Bạn kiểm tra ý nghĩa các lỗi upstream prematurely closed connection hoặc connection refused trong error log như thế nào?
Bạn thiết kế timeout sao cho Nginx, load balancer bên ngoài và ứng dụng không chờ nhau vô hạn ra sao?
Bạn đánh giá khi nào proxy_next_upstream có thể thử backend khác và rủi ro gửi lại thao tác ghi như thế nào?
Bạn xác định chính sách retry phù hợp cho GET so với các request có tác dụng phụ ra sao?
Bạn tổ chức upstream block để gom nhiều instance cùng phục vụ một ứng dụng như thế nào?
Bạn lựa chọn thuật toán round-robin, least_conn hoặc ip_hash theo kiểu tải và trạng thái phiên như thế nào?
Bạn đặt weight cho các backend có năng lực xử lý khác nhau dựa trên số liệu nào?
Bạn sử dụng tham số backup để dự phòng upstream khi các instance chính không khả dụng như thế nào?
Bạn phân biệt cân bằng tải ở request level với kết nối keepalive tới upstream như thế nào?
Bạn xác định cách cấu hình upstream keepalive giảm số lần thiết lập TCP như thế nào?
Bạn kiểm tra backend nào đã nhận một request cụ thể bằng biến upstream và access log ra sao?
Bạn phân tích một backend chậm làm ảnh hưởng phân bố tải của các request như thế nào?
Bạn thiết kế passive health checking qua các tham số max_fails và fail_timeout theo giới hạn nào?
Bạn phân biệt health check thụ động với health check chủ động và các khả năng phụ thuộc phiên bản Nginx ra sao?
Bạn xử lý tình huống backend còn mở cổng nhưng logic ứng dụng không thể phục vụ request như thế nào?
Bạn xác định cách tránh gửi request mới tới backend đang được đưa ra khỏi vòng phục vụ ra sao?
Bạn quản lý DNS của upstream khi IP backend thay đổi mà Nginx không tự cập nhật như dự kiến như thế nào?
Bạn xác định khi nào cần cấu hình resolver và cơ chế resolve tên upstream theo khả năng bản Nginx đang dùng ra sao?
Bạn xử lý tình trạng một upstream ngừng hoạt động trong lúc Nginx đang duy trì kết nối keepalive như thế nào?
Bạn phân tích giới hạn của sticky session khi backend lưu session trong bộ nhớ cục bộ ra sao?
Bạn đánh giá ảnh hưởng của cân bằng tải tới WebSocket hoặc kết nối HTTP lâu dài như thế nào?
Bạn quyết định lúc nào cần tách upstream cho traffic API và traffic xử lý tác vụ dài như thế nào?
Bạn tổ chức reverse proxy tới ứng dụng chạy trên Unix domain socket trong trường hợp nào?
Bạn xác định ảnh hưởng của worker_connections và giới hạn kết nối backend khi số client tăng mạnh ra sao?
Bạn lựa chọn các chỉ số lỗi, độ trễ và tỷ lệ kết nối để đánh giá sức khỏe upstream như thế nào?
Bạn giải thích TLS termination tại Nginx khác gì với TLS passthrough về khả năng quan sát request như thế nào?
Bạn thiết kế chứng chỉ HTTPS cho nhiều domain trên cùng máy bằng SNI như thế nào?
Bạn kiểm tra certificate chain và hostname khi trình duyệt báo chứng chỉ không đáng tin cậy ra sao?
Bạn xác định nguyên nhân chứng chỉ được nạp vào Nginx nhưng domain vẫn trả chứng chỉ cũ như thế nào?
Bạn quản lý vòng đời gia hạn và reload chứng chỉ mà không làm gián đoạn kết nối hiện có như thế nào?
Bạn lựa chọn phiên bản TLS và cipher suite dựa trên yêu cầu bảo mật và khả năng tương thích ra sao?
Bạn kiểm tra sự khác nhau giữa lỗi TCP, lỗi TLS handshake và lỗi HTTP khi chẩn đoán HTTPS như thế nào?
Bạn thiết kế HTTP Strict Transport Security và xác định rủi ro khi bật includeSubDomains hoặc preload ra sao?
Bạn cân nhắc khi nào redirect HTTP sang HTTPS cần đi kèm chính sách HSTS như thế nào?
Bạn cấu hình chứng chỉ client trong mTLS để xác thực dịch vụ gọi API như thế nào?
Bạn tổ chức truyền thông tin xác thực client certificate tới backend mà tránh giả mạo header ra sao?
Bạn xác minh chứng chỉ upstream khi Nginx proxy tới backend qua HTTPS như thế nào?
Bạn đánh giá rủi ro của việc tắt xác minh TLS certificate đối với kết nối proxy tới backend ra sao?
Bạn xác định cấu hình proxy_ssl_server_name và tên xác minh khi upstream phục vụ nhiều hostname như thế nào?
Bạn phân biệt TLS session reuse với connection keepalive khi tối ưu chi phí bắt tay như thế nào?
Bạn đo độ trễ DNS, TCP, TLS và phản hồi upstream để xác định nguyên nhân HTTPS chậm ra sao?
Bạn kiểm tra HTTP/2 đã được thương lượng giữa client và Nginx bằng cách nào?
Bạn đánh giá giới hạn khả năng hỗ trợ HTTP/2 hoặc HTTP/3 theo phiên bản và bản build của Nginx ra sao?
Bạn quyết định có bật HTTP/3/QUIC khi mạng khách hàng có thể chặn UDP/443 như thế nào?
Bạn xử lý trường hợp HTTPS hoạt động qua HTTP/1.1 nhưng client HTTP/2 gặp lỗi ra sao?
Bạn thiết kế reverse proxy cho WebSocket với các header Upgrade và Connection phù hợp như thế nào?
Bạn giải thích vì sao WebSocket cần chuyển giao thức trên HTTP/1.1 và duy trì kết nối lâu dài ra sao?
Bạn nhận diện handshake WebSocket thất bại khi server trả mã HTTP khác 101 bằng cách nào?
Bạn phân tích việc proxy_read_timeout làm ngắt WebSocket không có lưu lượng trong thời gian dài ra sao?
Bạn lựa chọn ping/pong của ứng dụng và timeout proxy để phát hiện WebSocket bị đứt như thế nào?
Bạn xử lý cân bằng tải WebSocket khi client cần duy trì session trên backend ra sao?
Bạn đánh giá khả năng mở rộng số lượng WebSocket lâu dài từ worker và file descriptor như thế nào?
Bạn cấu hình gRPC proxying bằng grpc_pass và phân biệt với proxy_pass trong tình huống nào?
Bạn kiểm tra các yêu cầu HTTP/2 đối với đường kết nối gRPC client đến Nginx và Nginx đến backend như thế nào?
Bạn xác định nguyên nhân gRPC trả trạng thái lỗi dù Nginx ghi nhận HTTP status thành công như thế nào?
Bạn thiết kế timeout và giới hạn kích thước thông điệp cho gRPC streaming ra sao?
Bạn đánh giá tác động của buffering tới server-sent events hoặc phản hồi streaming như thế nào?
Bạn xác định các header hoặc thiết lập cần kiểm tra khi SSE bị dồn lại thành từng đợt thay vì phát liên tục như thế nào?
Bạn phân biệt WebSocket, SSE và HTTP long polling khi cấu hình proxy cho cập nhật thời gian thực ra sao?
Bạn thiết kế proxy tới dịch vụ hỗ trợ HTTP keepalive và streaming để tránh ngắt kết nối ngoài ý muốn như thế nào?
Bạn kiểm tra sự khác nhau giữa lỗi gRPC do chứng chỉ TLS và lỗi do route upstream sai ra sao?
Bạn quyết định trường hợp nào nên dùng Nginx stream proxy cho TCP/UDP thay cho HTTP reverse proxy như thế nào?
Bạn phân biệt proxy ở stream context với proxy HTTP về header và khả năng định tuyến ra sao?
Bạn xác định cách chuyển tiếp một dịch vụ TCP hoặc UDP bằng Nginx stream mà không giả định có HTTP path như thế nào?
Bạn lựa chọn cách thu thập địa chỉ IP client khi proxy kết nối TCP qua nhiều hop như thế nào?
Bạn thiết kế giới hạn cho kết nối dài trong stream module dựa trên tài nguyên thực tế ra sao?
Bạn phân biệt cache phía trình duyệt với proxy cache của Nginx và ảnh hưởng đến tính mới dữ liệu như thế nào?
Bạn xác định endpoint nào phù hợp để cache theo tính công khai, tần suất đọc và tốc độ thay đổi như thế nào?
Bạn thiết kế proxy_cache_path và phân vùng lưu trữ cache khi dung lượng tăng lớn như thế nào?
Bạn lựa chọn proxy_cache_key để phân biệt URL, query parameter, host và biến thể nội dung như thế nào?
Bạn kiểm tra nguy cơ rò dữ liệu cá nhân nếu nhiều người dùng dùng chung cache key ra sao?
Bạn xác định khi nào header Cache-Control, Expires hoặc Set-Cookie phải ảnh hưởng đến việc cache như thế nào?
Bạn thiết kế bypass cache cho request có thông tin xác thực hoặc nội dung riêng người dùng như thế nào?
Bạn phân biệt proxy_cache_bypass và proxy_no_cache ở các giai đoạn đọc và ghi cache ra sao?
Bạn lựa chọn TTL riêng cho phản hồi thành công, 404 hoặc lỗi tạm thời dựa trên yêu cầu nghiệp vụ như thế nào?
Bạn sử dụng proxy_cache_use_stale để giảm tác động khi upstream gặp sự cố trong giới hạn nào?
Bạn kiểm tra tác động của stale content đến dữ liệu nhạy cảm thời gian hoặc nghiệp vụ như thế nào?
Bạn thiết kế cơ chế tránh nhiều request đồng thời cùng làm nóng một cache key như thế nào?
Bạn giải thích tác dụng của proxy_cache_lock khi một đối tượng phổ biến hết hạn như thế nào?
Bạn kiểm tra header Vary và nội dung nén khi nhiều loại client dùng chung cache như thế nào?
Bạn tổ chức invalidation khi dữ liệu nguồn thay đổi mà không phụ thuộc hoàn toàn vào TTL ra sao?
Bạn xác định tính khả dụng của purge cache theo bản build hoặc module Nginx đang chạy như thế nào?
Bạn phân tích log cache HIT, MISS, BYPASS và EXPIRED để tìm lý do tỷ lệ hit thấp ra sao?
Bạn đánh giá ảnh hưởng của proxy_cache_min_uses đến nội dung ít được truy cập như thế nào?
Bạn quyết định khi nào nên cache file tĩnh từ Nginx trực tiếp và khi nào nên cache phản hồi backend ra sao?
Bạn thiết kế kiểm tra sự tương thích của Range request với cache khi phục vụ nội dung lớn như thế nào?
Bạn ước lượng dung lượng cache cần thiết từ lưu lượng, kích thước object và tỷ lệ hit mong muốn ra sao?
Bạn xác định tác động của nén gzip đối với dung lượng truyền, CPU và cache như thế nào?
Bạn kiểm tra khả năng Brotli phụ thuộc module được cài đặt trước khi bật nén như thế nào?
Bạn lựa chọn mime type và mức nén để tránh nén lặp các định dạng vốn đã nén ra sao?
Bạn đánh giá vai trò của sendfile, tcp_nopush và tcp_nodelay khi phục vụ file tĩnh như thế nào?
Bạn kiểm tra lý do file tĩnh trả sai Content-Type làm trình duyệt từ chối nội dung ra sao?
Bạn phân biệt việc thiết lập ETag và Last-Modified cho tài nguyên tĩnh với cache proxy như thế nào?
Bạn thiết kế cơ chế đổi tên file theo hash để giữ cache lâu mà vẫn phát hành phiên bản mới ra sao?
Bạn hạn chế đường dẫn file bị truy cập trái phép thông qua cấu hình root, alias và location như thế nào?
Bạn áp dụng allow và deny để giới hạn truy cập endpoint quản trị theo IP như thế nào?
Bạn phân biệt Basic Auth, auth_request và cơ chế xác thực tại backend khi bảo vệ API ra sao?
Bạn thiết kế xác thực tại proxy mà vẫn bảo đảm backend kiểm tra quyền trên tài nguyên như thế nào?
Bạn xác định rủi ro khi Nginx chuyển tiếp header chứa danh tính người dùng nhưng backend tin header từ nguồn không đáng tin ra sao?
Bạn cấu hình giới hạn tần suất request bằng limit_req_zone và limit_req theo khóa nào?
Bạn lựa chọn burst và nodelay trong rate limiting dựa trên tính chất request như thế nào?
Bạn xác định ảnh hưởng của việc đặt khóa giới hạn theo IP khi nhiều người dùng ở sau cùng một NAT như thế nào?
Bạn phân biệt limit_req với limit_conn khi bảo vệ ứng dụng trước tải đột biến ra sao?
Bạn thiết kế phản hồi khi request bị rate limit để client biết khi nào cần thử lại như thế nào?
Bạn kiểm tra các mã trạng thái và metric liên quan đến giới hạn lưu lượng khi khách hàng nhận lỗi ngẫu nhiên ra sao?
Bạn đánh giá khi nào Nginx rate limiting đủ đáp ứng và khi nào cần bộ giới hạn tập trung nhiều node như thế nào?
Bạn ngăn một upstream bị quá tải mà không loại bỏ nhầm toàn bộ lưu lượng hợp lệ như thế nào?
Bạn lựa chọn giới hạn kích thước header, body và thời gian đọc request để giảm rủi ro khai thác tài nguyên như thế nào?
Bạn kiểm tra tác động của client_header_timeout và client_body_timeout với kết nối chậm ra sao?
Bạn đánh giá phương án giới hạn đồng thời các request upload có dung lượng lớn như thế nào?
Bạn lựa chọn các security header phù hợp để tăng bảo vệ trình duyệt mà không làm hỏng ứng dụng như thế nào?
Bạn phân biệt cách triển khai Content-Security-Policy tại Nginx và tại ứng dụng khi nội dung thay đổi ra sao?
Bạn xử lý header CORS cho nhiều origin được phép mà không mở quyền truy cập quá rộng như thế nào?
Bạn xác định lý do browser báo lỗi CORS dù curl gọi API vẫn thành công như thế nào?
Bạn kiểm tra preflight OPTIONS có được Nginx xử lý hoặc chuyển đúng tới backend ra sao?
Bạn tránh lộ thông tin phiên bản và các đường dẫn nội bộ qua response header hoặc trang lỗi như thế nào?
Bạn thiết kế phân quyền file cấu hình và private key TLS cho tiến trình Nginx như thế nào?
Bạn xác định nguy cơ proxy mở cho bất kỳ đích nào và cách giới hạn truy cập để tránh thành open proxy ra sao?
Bạn lựa chọn log_format để ghi method, URI, status, bytes, request time và upstream time như thế nào?
Bạn phân biệt access log với error log khi bắt đầu chẩn đoán yêu cầu thất bại ra sao?
Bạn sử dụng các biến $request_time, $upstream_response_time và $upstream_connect_time để phân tích độ trễ như thế nào?
Bạn kiểm tra sự khác nhau giữa mã $status ở Nginx và $upstream_status khi có nhiều lần thử backend ra sao?
Bạn gắn request ID xuyên Nginx và ứng dụng để truy vết một giao dịch bằng cách nào?
Bạn lựa chọn cách ẩn token, cookie và query parameter nhạy cảm trước khi ghi log như thế nào?
Bạn thiết kế log JSON có thể thu thập tập trung và phân tích mà không làm tăng tải quá mức ra sao?
Bạn xác định thời điểm nâng mức error_log để chẩn đoán nhưng vẫn kiểm soát chi phí log như thế nào?
Bạn kiểm tra log rotation để tránh đầy đĩa mà tiến trình Nginx vẫn tiếp tục ghi log như thế nào?
Bạn đánh giá chỉ số request rate, active connections, status distribution và upstream latency như thế nào?
Bạn xác định khác biệt giữa số lượng kết nối client và số kết nối Nginx tới backend trong một proxy nhiều worker ra sao?
Bạn giám sát cache hit ratio, lượng dữ liệu ghi và trạng thái dung lượng ổ đĩa để điều chỉnh cache ra sao?
Bạn thiết kế cảnh báo khi tỷ lệ 502 hoặc 504 tăng nhưng 200 vẫn chiếm đa số như thế nào?
Bạn phân biệt lỗi xảy ra trước khi request tới upstream với lỗi backend trả về từ access và error log như thế nào?
Bạn điều tra lỗi 502 bad gateway ngay sau một đợt triển khai ứng dụng theo những bước nào?
Bạn xác định nguyên nhân lỗi 504 gateway timeout bằng cách đối chiếu thời gian xử lý ở các thành phần như thế nào?
Bạn phân tích trường hợp 404 do Nginx tạo khác gì với 404 do backend trả về ra sao?
Bạn xác định lý do lỗi 403 chỉ xảy ra với một location hoặc thư mục tĩnh như thế nào?
Bạn kiểm tra lỗi 413 request entity too large qua cấu hình Nginx và các proxy đứng trước ra sao?
Bạn điều tra lỗi 499 khi client ngắt kết nối trước khi Nginx hoàn tất response như thế nào?
Bạn phân biệt sự cố upstream reset connection với client tự hủy request bằng bằng chứng nào?
Bạn kiểm tra lỗi 502 do Nginx không có quyền mở Unix socket của backend ra sao?
Bạn phân tích trường hợp backend chỉ bind 127.0.0.1 trong container và proxy ngoài container không truy cập được như thế nào?
Bạn xác định nguyên nhân upstream domain phân giải sai trong một môi trường container hoặc Kubernetes như thế nào?
Bạn phân biệt lỗi chứng chỉ upstream với lỗi DNS hoặc kết nối TCP khi proxy tới HTTPS backend ra sao?
Bạn xử lý việc một backend trả phản hồi quá chậm nhưng các backend còn lại vẫn khỏe như thế nào?
Bạn kiểm tra nguyên nhân Nginx báo upstream sent too big header và đánh giá giới hạn bộ đệm ra sao?
Bạn phân biệt timeout do response streaming với lỗi proxy buffering khi download tệp lớn như thế nào?
Bạn xác định lý do WebSocket chỉ ngắt khi im lặng một thời gian cố định ra sao?
Bạn kiểm tra lỗi gRPC do HTTP/2 hoặc cấu hình grpc_pass sai bằng cách nào?
Bạn xác định vì sao một bản cấu hình qua nginx -t nhưng vẫn tạo hành vi route sai như thế nào?
Bạn thiết kế kiểm thử smoke test cho HTTP, HTTPS, WebSocket và API trước khi phát hành cấu hình mới ra sao?
Bạn thay đổi cấu hình rồi reload Nginx an toàn và kiểm tra worker cũ đang xử lý kết nối như thế nào?
Bạn phân biệt reload cấu hình với restart tiến trình về tác động tới kết nối đang tồn tại như thế nào?
Bạn thiết kế phương án hoàn nguyên cấu hình khi reload thành công nhưng lưu lượng bắt đầu lỗi ra sao?
Bạn kiểm tra phiên bản Nginx và các module có sẵn trước khi sử dụng một directive mới như thế nào?
Bạn quản lý cấu hình Nginx bằng Git và CI để giảm sai lệch giữa staging và production như thế nào?
Bạn xây dựng kiểm thử tự động cho quy tắc location, redirect và proxy header trong pipeline như thế nào?
Bạn tổ chức cấu hình Nginx trong container để phù hợp volume, image và vòng đời triển khai như thế nào?
Bạn phân biệt cấu hình Nginx standalone với Nginx Ingress Controller trên Kubernetes về cơ chế quản lý ra sao?
Bạn kiểm tra ingress annotation hoặc cấu hình sinh ra khi hành vi thực tế khác manifest mong đợi như thế nào?
Bạn thiết kế chạy Nginx với quyền tối thiểu mà vẫn có thể bind cổng và đọc chứng chỉ như thế nào?
Bạn đánh giá ảnh hưởng của số node proxy và điểm kết thúc TLS đối với năng lực chịu tải và khả năng phục hồi ra sao?
Bạn lập kế hoạch canary cho cấu hình Nginx mới và lựa chọn chỉ số nào để quyết định mở rộng phạm vi triển khai?
Bạn kiểm thử khi một upstream mất kết nối đột ngột để kiểm chứng chính sách failover và retry ra sao?
Bạn xây dựng runbook phân tích lỗi từ DNS, kết nối TCP, TLS, location, proxy tới backend bằng cách nào?
Bạn lựa chọn chỉ tiêu nghiệm thu cho Nginx dựa trên độ trễ, tỷ lệ lỗi, an toàn truy cập và khả năng phục hồi như thế nào?
