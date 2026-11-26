Một công ty đưa ba website lên cùng máy Nginx và cùng địa chỉ IP; request gửi Host không khớp server_name nào vẫn nhận nội dung trang nội bộ mặc định thay vì trang lỗi được đội vận hành dự kiến.
Gateway Nginx phục vụ shop.example.com và api.example.com trên cùng cổng 443; sau khi đổi cấu hình virtual host, chỉ người dùng API nhận chứng chỉ TLS của website bán hàng.
Nhóm dùng server_name dạng wildcard cho các subdomain của doanh nghiệp; một subdomain nhiều cấp không khớp với khối server như kỳ vọng nên request bị xử lý bởi virtual host khác.
Trang chủ có cả example.com và www.example.com; sau khi thêm quy tắc chuyển hướng HTTPS, trình duyệt gặp vòng lặp chuyển hướng giữa hai tên miền qua nhiều lớp proxy.
Một web server Nginx nghe IPv4 trên cổng 80 nhưng thiếu cấu hình nhận kết nối IPv6; người dùng có mạng ưu tiên bản ghi AAAA gặp lỗi không đồng đều dù truy cập bằng IPv4 bình thường.
Một website tĩnh được đặt dưới thư mục mới nhưng Nginx vẫn trả 404 cho tệp có thật; đường dẫn URL với phần root trong khối location tạo ra đường dẫn tệp khác với cấu trúc đĩa.
Đội kỹ thuật dùng alias để phục vụ ảnh tại /media/ nhưng cấu hình đường dẫn có dấu gạch chéo cuối không phù hợp; một số URL ảnh được ánh xạ sai và trả 404 sau khi chuyển máy chủ.
Một ứng dụng SPA sử dụng try_files để trả về index.html cho các đường dẫn frontend; khi backend mất route /api/orders, gateway lại trả HTML với status 200 khiến ứng dụng mobile báo lỗi giải mã JSON.
Trang web có location tiền tố /images/ và location regex cho các phần mở rộng tệp; một request đến ảnh riêng tư bị xử lý theo nhánh regex chứa chính sách cache công khai khác dự kiến.
Nhóm thêm location khớp chính xác cho /health nhưng vẫn đặt quy tắc chuyển hướng toàn bộ request ở khối server; công cụ kiểm tra sức khỏe nhận 301 thay vì nội dung trạng thái.
Một bản phát hành đổi tên thư mục chứa asset nhưng cấu hình include cũ vẫn tồn tại trong Nginx; nhiều location chồng lấn khiến chỉ một số asset dùng đường dẫn mới.
Website trả tệp JavaScript với Content-Type không đúng sau khi chuyển sang cấu hình Nginx tối giản; trình duyệt bật kiểm tra MIME nghiêm ngặt và từ chối thực thi script.
Ứng dụng frontend phát hành các tệp CSS và JavaScript có tên chứa hash, nhưng trình duyệt vẫn dùng index.html được cache rất lâu; sau phát hành người dùng tải trang tham chiếu các asset không còn trên máy chủ.
Nhóm bật nén nội dung tại Nginx cho API JSON; băng thông giảm trong thử nghiệm nhưng CPU gateway tăng rõ khi hàng nghìn response lớn được tạo đồng thời.
Máy chủ công khai vô tình bật liệt kê thư mục khi không có tệp index; người dùng truy cập một đường dẫn tài nguyên có thể thấy danh sách tên tệp chưa dự định công bố.
Web server Nginx chạy bằng tài khoản dịch vụ ít quyền; sau khi chuyển dữ liệu tĩnh sang ổ đĩa khác, một số ảnh nhận 403 dù tệp vẫn tồn tại và truy cập được bằng tài khoản quản trị.
Một môi trường Linux có chính sách SELinux áp dụng cho Nginx; sau khi thay vị trí thư mục web và cổng upstream, request trả 403 hoặc 502 dù quyền tệp và kết nối thử từ shell có vẻ hợp lệ.
Nginx trả 413 khi người dùng tải ảnh hồ sơ dung lượng 15 MB; backend Spring Boot chấp nhận tệp 20 MB nhưng giới hạn client_max_body_size ở proxy chưa được đối chiếu với backend.
Gateway Nginx nhận nhiều bản tải lên dung lượng lớn với proxy_request_buffering đang bật và đệm request body vào tệp tạm trước khi chuyển tiếp; ổ đĩa dành cho dữ liệu tạm gần đầy dù backend còn đủ tài nguyên.
Dịch vụ cần xử lý tệp theo luồng ngay khi client gửi dữ liệu; sau khi đi qua reverse proxy, backend chỉ bắt đầu nhận body muộn hơn đáng kể so với kết nối trực tiếp.
API xuất dữ liệu trả response lớn theo từng phần, nhưng Nginx bật proxy_buffering và đệm nội dung trước khi đẩy tới trình duyệt; người dùng không thấy dữ liệu tiến triển đều dù backend đã gửi các phần nhỏ.
Một hệ thống gửi thông báo bằng Server-Sent Events; kết nối HTTP được giữ nhưng sự kiện đến trình duyệt thành từng đợt sau nhiều giây kể từ khi backend phát ra.
Ứng dụng chuyển từ chạy trực tiếp sang sau /app/ trên Nginx; đường dẫn proxy_pass có phần URI và dấu gạch chéo cuối khiến backend nhận đường dẫn khác với khi gọi trực tiếp.
Một dịch vụ backend mong nhận /v1/orders còn Nginx rewrite hai lần với tiền tố /api; chỉ route có nhiều cấp đường dẫn gặp 404 sau khi thêm quy tắc chuyển đường dẫn.
Ứng dụng tạo liên kết tuyệt đối dựa trên Host nhận được; sau khi triển khai reverse proxy, email xác nhận chứa địa chỉ tên máy nội bộ của backend thay vì tên miền công khai.
Backend nhận request HTTPS từ client qua Nginx nhưng tạo redirect về HTTP; phía Nginx kết thúc TLS rồi chuyển request HTTP mà thông tin giao thức gốc không được chuyển tiếp đúng.
Ứng dụng xác thực dùng cookie Secure và callback OAuth; sau khi thay reverse proxy, đăng nhập lặp vòng vì backend không xác định chính xác scheme và host phía client.
Nhóm thêm X-Forwarded-For để backend ghi IP người dùng; một client tự gửi sẵn header này và log ghi nhận IP giả do chuỗi proxy tin tưởng đầu vào chưa được xác định.
Nginx nằm sau bộ cân bằng tải nhưng quy tắc cho phép IP nội bộ vẫn dựa vào remote_addr trực tiếp; tất cả request trông như đến từ một IP của load balancer.
Ứng dụng web ở miền khác gửi preflight OPTIONS có Authorization và header tùy chỉnh; browser chặn request trước khi gọi backend vì response CORS do Nginx trả không khớp chính sách.
Một API trả lỗi 401 nhưng response thiếu các header CORS vốn chỉ được thêm cho response thành công; trình duyệt hiện lỗi mạng chung và frontend không đọc được nội dung lỗi xác thực.
Đội vận hành chuyển trang quản trị sang đường dẫn /admin và bật xác thực cơ bản ở một location; một đường dẫn khác đi tới cùng backend không nằm trong vùng áp dụng chính sách này.
Nginx dùng auth_request gọi dịch vụ kiểm tra quyền trước khi proxy đến backend; khi dịch vụ xác thực phản hồi chậm, latency của mọi API bảo vệ tăng dù upstream nghiệp vụ vẫn khỏe.
Gateway kiểm tra token qua dịch vụ xác thực bên ngoài; khi dịch vụ xác thực ngừng hoạt động, nhiều endpoint trả lỗi ngoài dự kiến và nhóm chưa thống nhất cách báo lỗi tới client.
Một đối tác tích hợp dùng chứng chỉ máy khách để xác thực mTLS tại Nginx; sau khi xoay CA phía đối tác, chỉ các request từ hệ thống đó thất bại trước khi backend ghi nhận truy cập.
Nginx dùng chung mTLS với hai nhóm đối tác nhưng ứng dụng backend phân quyền theo header tên đối tác; một request đi qua tuyến chưa loại bỏ header tự gửi gây nhầm lẫn danh tính được xác thực.
Trang đăng nhập được giới hạn 20 request mỗi phút theo IP; hàng trăm nhân viên truy cập qua cùng NAT của văn phòng đồng loạt nhận phản hồi 429 mặc dù từng người không thử nhiều lần.
API công khai dùng rate limiting theo API key nhưng key không được trích xuất đúng ở một route; nhiều khách hàng bị gom vào cùng bộ đếm và chặn lẫn nhau khi lưu lượng tăng.
Nginx có hai máy proxy cùng xử lý API nhưng mỗi máy giữ bộ đếm giới hạn lưu lượng riêng; cùng một đối tác gửi tổng số request vượt giới hạn công bố khi traffic chia đều hai máy.
Nhóm cấu hình rate limiting với vùng đếm và burst nhỏ; một màn hình frontend tải đồng thời nhiều tài nguyên hợp lệ bị giới hạn dù tổng lưu lượng trung bình theo phút không cao.
Dịch vụ cung cấp kết nối long polling nhiều phút; chính sách giới hạn số kết nối của Nginx áp dụng giống với các request ngắn khiến người dùng mở nhiều tab nhận lỗi dưới tải cao.
Máy Nginx trả 503 khi một request bị giới hạn bởi chính sách limit_req mặc định, trong khi client chỉ có xử lý thử lại theo mã 429 mà tài liệu API công bố.
Nginx cân bằng tải round-robin giữa ba phiên bản backend; một instance có CPU yếu xử lý request chậm hơn nhiều, làm p95 dao động theo instance được chọn.
Dịch vụ báo cáo có request dài ngắn khác nhau nhưng Nginx phân phối đều theo số request; một upstream giữ nhiều tác vụ nặng trong khi upstream khác phần lớn nhàn rỗi.
Phiên mua hàng được lưu cục bộ trong bộ nhớ backend; sau khi Nginx cân bằng tải giữa nhiều instance, giỏ hàng của một số khách biến mất khi request tiếp theo đi đến instance khác.
Nhóm thêm một backend mới vào nhóm upstream và đưa vào cân bằng tải ngay khi process vừa khởi động; health endpoint trả 200 trước khi kết nối cơ sở dữ liệu sẵn sàng nên một phần request lỗi.
Một upstream ngừng lắng nghe cổng ứng dụng, nhưng vẫn được Nginx đưa vào thử kết nối trong một số khoảng thời gian; client nhìn thấy lỗi 502 ngắt quãng trong khi các instance khác hoạt động.
Dịch vụ có endpoint báo sẵn sàng nhưng Nginx bản triển khai hiện tại chỉ dựa vào lỗi kết nối hoặc phản hồi thực tế để loại bỏ upstream; backend chưa sẵn sàng vẫn thỉnh thoảng được chọn.
Nhóm dùng tên DNS của dịch vụ trong upstream, sau khi chuyển pod sang địa chỉ mới thì Nginx tiếp tục thử một địa chỉ cũ; các lần gọi trực tiếp tới tên miền từ máy quản trị lại phân giải ra IP mới.
Một instance ứng dụng chủ động đóng kết nối keep-alive sớm hơn dự kiến, trong khi Nginx tái sử dụng kết nối upstream; dưới tải có một tỷ lệ nhỏ request trả 502 và retry ngay sau đó thành công.
Gateway mở nhiều kết nối mới tới backend cho mỗi request dù client thường gửi liên tiếp; CPU và số socket ở backend tăng mạnh sau khi nhóm thay đổi cài đặt keep-alive upstream.
Nginx trả 504 sau khi backend không gửi thêm dữ liệu trong khoảng proxy_read_timeout 30 giây cho API tạo báo cáo; backend vẫn tiếp tục chạy công việc hơn một phút và ghi kết quả thành công, khiến người dùng tưởng thất bại rồi gửi lại yêu cầu.
Client thấy 502 ngay khi gửi request tới endpoint có upstream cấu hình HTTPS; backend lại chỉ phục vụ HTTP trên cổng đó và log ứng dụng không ghi được nội dung request hợp lệ.
Một số request trả 502 với thông báo upstream prematurely closed connection trong error log; cùng thời điểm backend bị khởi động lại do thiếu bộ nhớ khi xử lý báo cáo lớn.
Nginx gửi một request cập nhật tới upstream nhưng mất kết nối trước khi nhận response; client thử lại và phát sinh hai tác vụ vì giao dịch đầu đã hoàn tất tại backend.
Nhóm bật cơ chế chuyển sang upstream khác khi có lỗi mạng cho API ghi dữ liệu; đối tác phản ánh số đơn hàng trùng tăng trong giai đoạn backend chập chờn.
Trình duyệt đóng tab giữa lúc tải báo cáo, Nginx ghi nhận 499 còn backend tiếp tục chạy truy vấn nặng; đội vận hành nhầm mã này là lỗi do upstream trả về.
Ứng dụng WebSocket kết nối qua Nginx trả phản hồi HTTP thông thường thay vì chuyển giao thức; khi gọi trực tiếp backend thì kết nối được nâng cấp thành công.
WebSocket được thiết lập qua Nginx nhưng thường đóng sau khoảng một phút không có tin nhắn; thời gian ping của ứng dụng và ngưỡng chờ đọc từ upstream chưa được điều chỉnh đồng bộ.
Một ứng dụng chat chạy WebSocket trên Nginx với nhiều worker; sau đợt phát hành, các kết nối mới hoạt động nhưng một số kết nối lâu dài vẫn bị đóng khi proxy reload liên tục.
Backend gRPC dùng HTTP/2 hoạt động khi gọi trực tiếp nhưng không hoạt động qua location dành cho proxy HTTP thông thường; log ghi nhận lỗi giao thức giữa Nginx và upstream.
Gateway công bố gRPC qua TLS nhưng một đường route thiếu cấu hình HTTP/2 phù hợp ở phía client; một số SDK nhận lỗi kết nối hoặc không thương lượng được giao thức mong đợi.
Ứng dụng gRPC streaming truyền dữ liệu trong nhiều phút; một số luồng bị ngắt khi backend chưa trả thông điệp trong khoảng thời gian Nginx chờ, dù TCP còn kết nối.
Nhóm cập nhật chứng chỉ HTTPS trên một máy Nginx trong cụm; cùng hostname nhưng người dùng nhận chứng chỉ cũ hoặc mới tùy máy cân bằng tải phía trước chọn.
Nginx chuyển hướng toàn bộ HTTP sang HTTPS nhưng trang web vẫn tải JavaScript qua URL HTTP tuyệt đối; trình duyệt chặn một phần nội dung vì mixed content sau khi thêm TLS.
Trang HTTPS hoạt động từ trình duyệt đã truy cập trước đó, nhưng máy mới dùng OpenSSL báo thiếu intermediate CA; chuỗi chứng chỉ mà Nginx gửi chưa đầy đủ.
Nginx dùng chứng chỉ có SAN cho tên miền sản phẩm nhưng quản trị viên kiểm tra HTTPS qua IP trực tiếp; quá trình xác minh tên máy chủ thất bại dù chứng chỉ còn hạn.
Nginx proxy đến backend HTTPS sử dụng CA nội bộ; sau khi bật xác minh chứng chỉ upstream, chỉ tuyến này trả 502 vì kho CA tin cậy chưa có chứng chỉ cần thiết.
Nginx tiếp nhận HTTPS từ client nhưng kết nối không mã hóa đến upstream qua một mạng khác vùng tin cậy; nhóm bảo mật phát hiện hành vi khác với yêu cầu mã hóa đầu cuối trên đường truyền.
Doanh nghiệp thay cấu hình TLS để vô hiệu hóa phiên bản và cipher suite yếu; một nhóm thiết bị cũ không còn kết nối được dù máy tính hiện đại vẫn truy cập ổn định.
Nhóm bật HSTS cho website chính rồi đổi thử sang một máy chủ dự phòng có chứng chỉ hết hạn; người dùng truy cập bằng HTTPS không thể bỏ qua cảnh báo như ở môi trường thử nghiệm.
Nginx cache kết quả GET thông tin tài khoản nhưng cache key không phân biệt danh tính đã xác thực; người dùng đôi khi nhìn thấy nội dung response của tài khoản khác.
API danh mục sản phẩm có nhiều tham số sắp xếp và lọc; sau khi thêm cache tại Nginx, request có query string khác nhau vẫn trả cùng một tập kết quả do cache key chưa phản ánh các tham số quan trọng.
Một trang đa ngôn ngữ chọn nội dung theo Accept-Language; sau khi proxy cache được bật, khách dùng tiếng Anh đôi lúc nhận bản tiếng Việt vì biến thể nội dung chưa được phân biệt.
Cache tĩnh tại Nginx có TTL dài; sau khi backend đổi giá sản phẩm, API vẫn trả nội dung cũ cho một số request dù cập nhật trong cơ sở dữ liệu đã thành công.
Sau khi hết hạn cache của một tài nguyên rất phổ biến, nhiều request đồng thời cùng đổ về backend để lấy lại nội dung; CPU backend tăng đột biến vài giây dù lưu lượng người dùng không đổi.
Backend đôi khi trả 500 cho API báo cáo; Nginx đang cache cả một số phản hồi lỗi, khiến nhiều client liên tiếp nhận dữ liệu lỗi sau khi backend đã phục hồi.
Nhóm cấu hình proxy cache cho endpoint có cookie phiên; dashboard báo tỉ lệ HIT cao nhưng nội dung phản hồi cá nhân hóa không phù hợp với người dùng mới.
Nhóm bật nén và cache cho ảnh lớn trên Nginx; dung lượng đĩa và I/O ghi tăng, trong khi băng thông giảm ít do nội dung ảnh vốn đã được nén.
Đội vận hành cần phân tích lỗi 502 và 504 nhưng cấu hình logging trong access log chỉ ghi status cuối và thời gian tổng, không có thời gian kết nối, thời gian trả lời hoặc status của upstream được chọn.
Ứng dụng backend báo tất cả request đến từ IP của Nginx; báo cáo chống gian lận theo IP không chính xác và log chưa xác định được chuỗi proxy đáng tin cậy.
Nhóm dùng toàn bộ URI chứa mã đơn hàng làm nhãn metric theo route; số chuỗi thời gian tăng nhanh khi lưu lượng lớn và hệ thống quan sát tiêu thụ nhiều bộ nhớ.
Nginx ghi toàn bộ header Authorization và cookie vào log để hỗ trợ tìm lỗi đăng nhập; tệp log được chuyển sang hệ thống quan sát mà nhiều đội có thể đọc.
Dashboard cho thấy p99 từ client qua Nginx tăng lên 3 giây trong khi p99 backend chỉ 200 ms; nhóm thiếu dữ liệu để phân biệt kết nối phía client, hàng đợi, buffering và thời gian upstream.
Một container Nginx chạy với giới hạn file descriptor thấp; ở giờ cao điểm, error log xuất hiện lỗi không mở được socket mới dù CPU và bộ nhớ của proxy chưa đạt ngưỡng.
Nhóm chỉnh sửa tệp cấu hình Nginx thủ công rồi gửi reload ngay; cú pháp sai khiến cấu hình mới không được nạp, nhưng dashboard phát hành vẫn báo thành công và các request tiếp tục chạy theo cấu hình cũ.
Hệ thống nhiều máy Nginx dùng cấu hình được phân phối không đồng đều; cùng URL có lúc đi vào route canary, lúc vào route cũ và logs trên mỗi máy phản ánh một phiên bản cấu hình khác nhau.
