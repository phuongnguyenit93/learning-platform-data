Câu 01. Khi Nginx làm reverse proxy, nhiệm vụ chính của nó là gì?
A. Nhận request rồi xử lý nghiệp vụ thay cho ứng dụng backend.
B. Nhận request rồi chuyển tới backend theo cấu hình route.
C. Nhận request rồi ghi dữ liệu trực tiếp vào database nội bộ.
D. Nhận request rồi tự tạo bản build của ứng dụng cần phục vụ.
Đáp án đúng: B

Câu 02. Trong cấu hình Nginx HTTP, quan hệ context nào là đúng?
A. Khối http thuộc server; khối location thuộc upstream.
B. Khối location thuộc http; khối server thuộc events.
C. Khối server thuộc http; khối location thuộc server.
D. Khối upstream thuộc server; khối events thuộc location.
Đáp án đúng: C

Câu 03. Trong virtual hosting, server_name được dùng để làm gì?
A. Khớp HTTP method với danh sách location được phép.
B. Khớp mã response với cấu hình error_page đã khai báo.
C. Khớp địa chỉ client với danh sách upstream khả dụng.
D. Khớp tên host yêu cầu với server block thích hợp.
Đáp án đúng: D

Câu 04. Ý nghĩa của listen 80 default_server trong một server block là gì?
A. Buộc mọi virtual host trên máy chủ dùng chung server_name.
B. Chọn server mặc định khi Host không khớp tên cấu hình.
C. Đặt tất cả upstream chuyển qua cổng 80 khi backend lỗi.
D. Chỉ chấp nhận request HTTP có header Host là localhost.
Đáp án đúng: B

Câu 05. Với location = /health, request nào khớp trực tiếp location đó?
A. Request có query mang chuỗi health dù path là /status.
B. Request có path bắt đầu bằng /health, gồm /health/live.
C. Chỉ khớp path /health, không khớp path /health/live.
D. Request có path kết thúc bằng /health, gồm /api/health.
Đáp án đúng: C

Câu 06. Trong Nginx, modifier ^~ ở location dạng prefix có vai trò nào?
A. Nếu prefix đó được chọn dài nhất, bỏ qua bước xét regex.
B. Chỉ cho phép request phương thức HEAD đi qua location.
C. Chuyển mọi path khớp prefix sang HTTPS theo mặc định.
D. Bắt buộc chỉ khớp đúng path, không nhận các path con.
Đáp án đúng: A

Câu 07. Location ~* \.png$ có hành vi so khớp nào?
A. Dùng regex có phân biệt chữ hoa chữ thường để khớp path.
B. Dùng so khớp prefix thuần túy thay cho biểu thức chính quy.
C. Dùng so khớp chính xác toàn path mà không cần regex.
D. Dùng regex không phân biệt chữ hoa chữ thường để khớp path.
Đáp án đúng: D

Câu 08. Với location /img/ { root /srv/www; }, /img/a.png được tìm ở đâu?
A. Tệp /srv/www/img/img/a.png khi prefix được nối hai lần.
B. Tệp /srv/www/a.png khi phần location bị thay bằng root.
C. Tệp /srv/www/img/a.png khi đường dẫn được nối với root.
D. Tệp /img/srv/www/a.png khi root nối sau prefix location.
Đáp án đúng: C

Câu 09. Với location /img/ { alias /data/pics/; }, /img/a.png ở đâu?
A. Tệp /img/data/pics/a.png vì URI đứng trước alias.
B. Tệp /data/pics/img/img/a.png vì prefix được lặp lại.
C. Tệp /data/pics/img/a.png vì alias cộng toàn URI.
D. Tệp /data/pics/a.png do alias thay prefix /img/.
Đáp án đúng: D

Câu 10. Chỉ thị try_files $uri $uri/ =404 trong Nginx dùng để làm gì?
A. Thử đường dẫn tệp/thư mục theo thứ tự trước khi trả 404.
B. Thử mọi upstream theo thứ tự trước khi trả lỗi kết nối.
C. Thử các phương thức GET và HEAD trước khi gửi status 404.
D. Thử xác thực client trước khi xác nhận file có tồn tại.
Đáp án đúng: A

Câu 11. Trong location proxy, proxy_pass http://orders; có vai trò gì?
A. Chuyển request tới upstream orders được khai báo phù hợp.
B. Đặt trang lỗi tĩnh khi upstream orders trả mã trạng thái 500.
C. Thiết lập chứng chỉ HTTPS riêng cho dịch vụ orders đích.
D. Giới hạn số request mỗi giây đến tất cả dịch vụ orders.
Đáp án đúng: A

Câu 12. Với location /api/ và proxy_pass http://app/;, request /api/items thành gì?
A. Upstream nhận path /app/api/items vì tên upstream thành prefix.
B. Upstream nhận path /api/api/items vì location được nối hai lần.
C. Upstream nhận path /api/items vì prefix luôn được giữ nguyên.
D. Upstream nhận path /items do URI của proxy_pass thay prefix.
Đáp án đúng: D

Câu 13. Vì sao proxy_set_header Host $host thường được cấu hình?
A. Để backend luôn nhận IP máy Nginx thay cho hostname client.
B. Để backend tự xác thực cookie mà không cần header khác.
C. Để backend nhận hostname đã được Nginx xác định từ request.
D. Để Nginx thay tên upstream thành tên DNS của proxy nội bộ.
Đáp án đúng: C

Câu 14. Biến $proxy_add_x_forwarded_for thường được dùng để làm gì?
A. Thêm IP client vào chuỗi X-Forwarded-For đang được chuyển tiếp.
B. Xóa mọi địa chỉ proxy trước đó khỏi chuỗi X-Forwarded-For.
C. Đổi giá trị Host thành IP client trước khi gửi request tới đích.
D. Thay IP nguồn của kết nối TCP bằng địa chỉ trong X-Forwarded-For.
Đáp án đúng: A

Câu 15. Khi Nginx ở sau load balancer, cấu hình real IP nào an toàn hơn?
A. Chọn IP đầu tiên trong header bất kể địa chỉ peer kết nối.
B. Tự cho phép mọi địa chỉ private ghi đè IP client qua header.
C. Tin X-Forwarded-For của mọi client vì đã qua mạng Internet.
D. Chỉ tin header IP từ proxy đã cấu hình tin cậy.
Đáp án đúng: D

Câu 16. Mặc định, một upstream có nhiều server thường được Nginx phân phối thế nào?
A. Dùng least_conn trên mọi upstream dù không có chỉ thị tương ứng.
B. Dùng ip_hash để bắt buộc mỗi client giữ nguyên backend từ đầu.
C. Dùng round-robin nếu không chọn phương pháp cân bằng tải khác.
D. Dùng random two choices như lựa chọn mặc định của mọi upstream.
Đáp án đúng: C

Câu 17. Chỉ thị least_conn trong upstream giúp chọn server nào?
A. Server đang có ít kết nối hoạt động theo phương pháp least_conn.
B. Server có thời gian khởi động ngắn nhất trong upstream đang chạy.
C. Server có ít request ghi trong ngày dựa vào access log của Nginx.
D. Server có số byte response nhỏ nhất trong lịch sử giám sát.
Đáp án đúng: A

Câu 18. Chỉ thị ip_hash trong upstream chủ yếu nhằm mục đích nào?
A. Phân phối request theo trọng số CPU thay vì IP của client.
B. Buộc mỗi yêu cầu tạo kết nối mới đến server được lựa chọn.
C. Giữ client có cùng IP tới backend tương đối ổn định.
D. Chọn server có ít TCP connection đang mở nhất hiện tại.
Đáp án đúng: C

Câu 19. Khi khai báo keepalive trong upstream HTTP, lợi ích chính nào?
A. Giữ một request HTTP chạy vô hạn không cần timeout phía client.
B. Có thể tái sử dụng kết nối tới backend thay vì tạo mới liên tục.
C. Tự cân bằng số kết nối đang mở giữa tất cả backend tương ứng.
D. Đảm bảo phiên ứng dụng không mất nếu một backend gặp sự cố.
Đáp án đúng: B

Câu 20. Trong HTTPS termination, cặp chỉ thị nào cấu hình certificate và key?
A. ssl_certificate cùng ssl_certificate_key trong server dùng TLS.
B. server_name cùng root trong server để chọn khóa riêng TLS.
C. proxy_pass cùng proxy_set_header trong location reverse proxy.
D. access_log cùng error_log ở tầng server để ghi chứng chỉ.
Đáp án đúng: A

Câu 21. Nginx đã terminate HTTPS từ client; muốn TLS tới backend cần làm gì?
A. Chỉ bật ssl_certificate trên Nginx là tự mã hóa toàn tuyến.
B. Dùng proxy_pass https://... và xác minh TLS tới backend.
C. Đặt gzip on trong location để proxy tự mã hóa request body.
D. Chỉ đặt X-Forwarded-Proto=https rồi gửi HTTP tới backend.
Đáp án đúng: B

Câu 22. Khi Nginx yêu cầu client certificate (mTLS), cần điều gì?
A. Chỉ đặt proxy_ssl_verify on cho request từ browser tới proxy.
B. Chỉ đặt ssl_certificate_key là đủ xác minh client certificate.
C. Chỉ khai báo Host header có hostname hợp lệ là đủ thay mTLS.
D. Khai báo CA tin cậy và bật ssl_verify_client trong TLS server.
Đáp án đúng: D

Câu 23. Chỉ thị proxy_cache_path thường đảm nhiệm nhiệm vụ nào?
A. Đặt TTL giống nhau cho mọi loại response HTTP từ backend.
B. Định nghĩa nơi lưu cache và vùng keys_zone trong context http.
C. Bật cache cho mọi location bất kể cấu hình proxy_cache hiện có.
D. Chỉ định upstream được chọn khi cache hết thời gian lưu trữ.
Đáp án đúng: B

Câu 24. Khi proxy cache tài nguyên có dữ liệu riêng của từng user, cần ưu tiên gì?
A. Bỏ qua Cache-Control riêng tư để shared cache nhận mọi response.
B. Kiểm soát cache key và tránh shared-cache sai dữ liệu cá nhân.
C. Cho mọi phiên dùng chung cookie và Authorization khi lấy cache.
D. Dùng một cache key theo path để tăng hit ratio giữa mọi user.
Đáp án đúng: B

Câu 25. proxy_cache_valid 200 10m trong cấu hình cache mang ý nghĩa nào?
A. Cho phép cache mọi status và mọi response trong 10 phút.
B. Buộc upstream trả 200 trong 10 phút sau lần gọi thành công.
C. Buộc client lưu response 200 vào browser cache trong 10 phút.
D. Cho phép cache response 200 với thời gian hợp lệ 10 phút.
Đáp án đúng: D

Câu 26. WebSocket qua Nginx reverse proxy cần lưu ý cấu hình nào?
A. Chuyển mọi request Upgrade sang HTTP POST ở tầng upstream.
B. Chỉ đặt proxy_buffering on là đủ mở kênh WebSocket hai chiều.
C. Chỉ đặt proxy_cache on là đủ để duy trì handshake WebSocket.
D. Chuyển Upgrade và Connection phù hợp với HTTP/1.1 upstream.
Đáp án đúng: D

Câu 27. Để proxy tới backend gRPC, Nginx sử dụng directive nào?
A. fastcgi_pass tới backend gRPC theo giao thức FastCGI.
B. uwsgi_pass tới backend gRPC theo giao thức uWSGI.
C. grpc_pass tới upstream gRPC với transport HTTP/2 phù hợp.
D. proxy_pass tới backend gRPC qua HTTP/1.0 theo mặc định.
Đáp án đúng: C

Câu 28. Với Server-Sent Events, proxy_buffering off thường giúp gì?
A. Buộc toàn bộ response chuyển sang WebSocket hai chiều.
B. Giảm việc giữ event trong buffer trước khi gửi tới client.
C. Buộc server đặt Content-Length ngay khi stream chưa kết thúc.
D. Giúp proxy tự chuyển mọi dòng SSE thành HTTP/2 stream mới.
Đáp án đúng: B

Câu 29. client_max_body_size trong Nginx liên quan đến giới hạn nào?
A. Kích thước request body; quá giới hạn có thể bị trả 413.
B. Số kết nối đồng thời; quá giới hạn bị trả mã 503.
C. Kích thước response body; quá giới hạn bị trả mã 304.
D. Số lượng request mỗi giây; quá giới hạn bị trả mã 429.
Đáp án đúng: A

Câu 30. Để rate limit theo IP với limit_req, quy trình nào phù hợp?
A. Định nghĩa limit_req_zone rồi áp limit_req tại server/location.
B. Đặt proxy_read_timeout là Nginx tự giới hạn request mỗi giây.
C. Đặt limit_conn_zone là Nginx tự giới hạn mọi request mỗi phút.
D. Chỉ tạo upstream zone là Nginx tự giới hạn request theo IP.
Đáp án đúng: A

Câu 31. Khác biệt quan trọng giữa limit_conn và limit_req là gì?
A. limit_conn hạn lưu lượng byte; limit_req hạn kích thước body.
B. limit_conn hạn số upstream; limit_req hạn thời gian chờ TCP.
C. limit_conn hạn kết nối; limit_req hạn tốc độ xử lý request.
D. limit_conn hạn tên server; limit_req hạn số vị trí location.
Đáp án đúng: C

Câu 32. Cặp chỉ thị auth_basic và auth_basic_user_file hỗ trợ việc gì?
A. Bật kiểm tra mTLS client certificate từ tệp key upstream.
B. Bật xác thực JWT bằng JWKS và công khai mọi khóa ký hiện hữu.
C. Bật kiểm tra IP bằng subnet trong tệp deny của backend.
D. Bật HTTP Basic Auth với tệp tài khoản được cấu hình.
Đáp án đúng: D

Câu 33. Chỉ thị allow và deny trong location Nginx chủ yếu dùng để làm gì?
A. Áp điều kiện bảo mật theo vai trò nghiệp vụ từ JWT claim.
B. Áp quy tắc truy cập theo địa chỉ IP hoặc dải mạng của client.
C. Áp quy tắc nén phản hồi theo media type của request.
D. Áp quota request mỗi giây theo user trong HTTP cookie.
Đáp án đúng: B

Câu 34. proxy_connect_timeout khác proxy_read_timeout ở điểm nào?
A. Connect giới hạn gửi body; read giới hạn DNS lookup trên client.
B. Connect giới hạn giữ cache; read giới hạn số request trong pool.
C. Connect giới hạn TLS của browser; read giới hạn TTL của proxy.
D. Connect giới hạn kết nối tới upstream; read giới hạn chờ dữ liệu.
Đáp án đúng: D

Câu 35. proxy_read_timeout trong Nginx nên được hiểu theo cách nào?
A. Giới hạn thời gian Nginx chờ ghi hết response xuống ổ đĩa.
B. Giới hạn thời gian giữa các lần đọc từ upstream, không phải tổng.
C. Giới hạn toàn bộ thời gian xử lý request kể từ lần accept TCP.
D. Giới hạn khoảng thời gian client được giữ cookie đăng nhập.
Đáp án đúng: B

Câu 36. Khi Nginx trả 502 Bad Gateway, nguyên nhân nào đáng kiểm tra?
A. Upstream gửi phản hồi không hợp lệ hoặc kết nối bị reset.
B. Client được xác thực nhưng không có quyền truy cập tài nguyên.
C. Nginx đang trả dữ liệu tươi từ cache mà không gọi upstream.
D. Client đã gửi request vượt quota nên bị chặn theo limit_req.
Đáp án đúng: A

Câu 37. Khi Nginx trả 504 Gateway Timeout, hướng điều tra nào hợp lý?
A. Xem cấu hình cookie SameSite vì client chưa chứng minh danh tính.
B. Xem lỗi cú pháp URI vì client đã gửi body vượt mức cho phép.
C. Xem thời gian chờ phản hồi upstream và các timeout liên quan.
D. Xem Content-Type vì cache không hỗ trợ kiểu dữ liệu response.
Đáp án đúng: C

Câu 38. Khi phân tích access log Nginx, cặp biến nào giúp tách thời gian?
A. $request_time và $upstream_response_time để so phần tổng/upstream.
B. $host và $server_name để tính thời gian TLS handshake phía client.
C. $remote_addr và $http_user_agent để đo RTT theo từng đường mạng.
D. $status và $upstream_status để đo số mili giây kết nối DNS.
Đáp án đúng: A

Câu 39. Trước khi kích hoạt thay đổi cấu hình, nginx -t chủ yếu làm gì?
A. Khởi động lại mọi worker và ngắt các kết nối đang hoạt động.
B. Tự động sửa mọi đường dẫn upstream bị sai trong nginx.conf.
C. Kiểm tra cú pháp và khả năng mở các tệp được cấu hình.
D. Chạy thử từng request thực tế để đánh giá latency upstream.
Đáp án đúng: C

Câu 40. Sau khi kiểm tra cấu hình hợp lệ, nginx -s reload nhằm mục đích gì?
A. Xóa sạch proxy cache và bắt tất cả client đăng nhập lại.
B. Nạp cấu hình mới và chuyển worker theo cơ chế reload nhẹ.
C. Dừng ngay mọi kết nối đang mở rồi khởi động mới toàn bộ Nginx.
D. Chuyển mọi backend không khỏe sang healthy mà không cần probe.
Đáp án đúng: B
