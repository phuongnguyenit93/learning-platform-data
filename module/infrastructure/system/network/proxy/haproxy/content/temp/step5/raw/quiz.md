Câu 1. Trong HAProxy, khối `frontend` đảm nhiệm công việc chính nào?
A. Định nghĩa máy chủ ứng dụng cùng trọng số cân bằng.
B. Lưu dữ liệu phiên đăng nhập trong database backend.
C. Tạo chứng chỉ TLS cho từng máy chủ ứng dụng đích.
D. Nhận kết nối từ client rồi chọn backend theo điều kiện.
Đáp án đúng: D

Câu 2. Khối `backend` trong cấu hình HAProxy mô tả điều gì?
A. Cổng nghe từ client và quy tắc chọn tên miền HTTP.
B. Các tài khoản được phép sửa cấu hình runtime socket.
C. Khai báo nhóm server đích và thuật toán phân phối request.
D. Các chứng chỉ được phép cài trên hệ điều hành client.
Đáp án đúng: C

Câu 3. Khối `listen` trong HAProxy có đặc điểm thực dụng nào?
A. Chỉ định toàn bộ timeout mặc định cho mọi frontend.
B. Chỉ định mật khẩu đăng nhập vào trang thống kê HTTP.
C. Gộp cấu hình điểm nhận kết nối với server phía sau.
D. Chỉ khai báo hệ thống ghi log mà không thể proxy.
Đáp án đúng: C

Câu 4. Khi một proxy HAProxy chạy ở `mode tcp`, đặc điểm nào đúng?
A. Phân tích Host và path HTTP trước mỗi lần chuyển tiếp.
B. Chuyển tiếp luồng TCP mà không phân tích header HTTP.
C. Tự chèn cookie phiên HTTP vào response của backend.
D. Bắt buộc giải mã TLS ở frontend trước khi định tuyến.
Đáp án đúng: B

Câu 5. `mode http` mở ra khả năng nào so với xử lý thuần TCP?
A. Cho phép lọc HTTP theo method, header và URL path trong ACL.
B. Luôn chuyển TLS về HTTP không mã hóa cho backend.
C. Tự đồng bộ session của các server mà không cần app.
D. Buộc mọi kết nối phía client dùng giao thức HTTP/2.
Đáp án đúng: A

Câu 6. Cấu hình `bind :443 ssl crt /etc/haproxy/site.pem` thường có tác dụng gì?
A. Chuyển nguyên luồng TLS đến backend không giải mã.
B. Nhận và giải mã TLS ở frontend với chứng chỉ đã nạp.
C. Buộc backend trả chứng chỉ phía client qua TCP 443.
D. Tạo chứng chỉ mới sau mỗi lần frontend mở kết nối.
Đáp án đúng: B

Câu 7. Ý nghĩa của `default_backend web` trong một frontend là gì?
A. Ưu tiên backend web trước mọi điều kiện use_backend.
B. Tự biến frontend thành backend cùng tên web hiện có.
C. Dùng backend web mặc định khi không luật điều hướng nào khớp.
D. Chỉ nhận request từ server web rồi gửi trả cho client.
Đáp án đúng: C

Câu 8. Lệnh `use_backend api if is_api` trong frontend hoạt động thế nào?
A. Chọn backend api nếu điều kiện ACL có tên is_api khớp.
B. Chọn backend api bất kể kết quả của ACL is_api.
C. Thay thuật toán cân bằng tải của backend api.
D. Chuyển HTTP method sang API khi is_api phù hợp.
Đáp án đúng: A

Câu 9. Điều kiện `acl api_path path_beg /api` được dùng để khớp gì?
A. Header Host request chứa đúng tên miền `/api`.
B. Địa chỉ IP nguồn client nằm trong subnet `/api`.
C. Đường dẫn của request bắt đầu với tiền tố `/api`.
D. Một cookie phía client mang giá trị đúng `/api`.
Đáp án đúng: C

Câu 10. Fetch `hdr(host)` trong ACL HTTP của HAProxy đọc thông tin nào?
A. Địa chỉ IP gốc của client theo transport layer.
B. Thời gian chờ connect của server phía sau proxy.
C. Đọc giá trị Host header có trong request do client gửi.
D. Tên server backend đang được chọn để cân bằng.
Đáp án đúng: C

Câu 11. Khi có nhiều `use_backend ... if ...` trong frontend, thứ tự khai báo ảnh hưởng thế nào?
A. Luật khớp sau luôn ghi đè luật đã khớp trước đó.
B. Luật khớp trước được chọn trước các luật phía sau.
C. Luật có tên backend dài hơn luôn được ưu tiên.
D. HAProxy bắt buộc đánh giá toàn bộ rồi bốc ngẫu nhiên.
Đáp án đúng: B

Câu 12. `http-request deny deny_status 403 if blocked` chủ yếu làm gì?
A. Chuyển request bị chặn đến một backend dự phòng.
B. Chỉ ghi log request mà vẫn cho phép proxy tiếp.
C. Chỉ trả 403 sau khi server backend đã phản hồi.
D. Chặn request khớp ACL blocked và trả response HTTP 403.
Đáp án đúng: D

Câu 13. `http-request set-header X-Env prod` thường có hiệu lực ở đâu?
A. Đặt cookie X-Env trong response trả về client.
B. Đặt server weight theo giá trị header X-Env.
C. Đặt header X-Env vào request gửi backend.
D. Đặt ACL X-Env cho toàn bộ máy chủ đang chạy.
Đáp án đúng: C

Câu 14. `option forwardfor` thường phục vụ nhu cầu nào của backend HTTP?
A. Nhận địa chỉ IP thật qua cookie do proxy tạo.
B. Nhận IP client gốc qua header X-Forwarded-For.
C. Nhận khóa TLS của client trong header HTTP.
D. Nhận số lượng request qua header Authorization.
Đáp án đúng: B

Câu 15. Thuật toán `balance roundrobin` phân phối kết nối mới theo cách nào?
A. Chọn server có ít kết nối hoạt động nhất.
B. Chọn server nhờ hash IP nguồn của client.
C. Luân phiên chọn server theo trọng số.
D. Chọn server có thời gian đáp ứng thấp nhất.
Đáp án đúng: C

Câu 16. Thuật toán `balance leastconn` ưu tiên server theo tiêu chí nào?
A. Thứ tự xuất hiện của server trong cấu hình.
B. Hash của địa chỉ IP nguồn của từng client.
C. Ít kết nối hoạt động sau khi xét trọng số.
D. Thời gian TTL nhỏ nhất trên từng server.
Đáp án đúng: C

Câu 17. Thuật toán `balance source` thường chọn server dựa trên gì?
A. Thứ tự số lần request đến ở frontend.
B. Địa chỉ IP đích đã được DNS resolver trả.
C. Tốc độ CPU hiện tại của các server backend.
D. Giá trị hash của địa chỉ IP nguồn client.
Đáp án đúng: D

Câu 18. Khi dùng persistence bằng cookie trong HAProxy HTTP, mục đích là gì?
A. Giữ client quay lại cùng server qua cookie.
B. Tự chia đều từng request lên server khác nhau.
C. Luôn bắt client đăng nhập lại sau mỗi response.
D. Chặn mọi request nếu browser không hỗ trợ TLS.
Đáp án đúng: A

Câu 19. Stick-table của HAProxy thường phù hợp để lưu loại trạng thái nào?
A. Nội dung HTML đầy đủ để cache thay server ứng dụng.
B. Chứng chỉ TLS gốc từ tất cả backend trong mạng.
C. Toàn bộ log truy cập để thay thế hệ thống lưu log.
D. Thống kê theo client như số kết nối hoặc tốc độ.
Đáp án đúng: D

Câu 20. `http-request track-sc0 src` thường giúp thực hiện thao tác gì?
A. Theo dõi IP nguồn qua stick-table.
B. Chuyển request sang backend có tên là sc0.
C. Đổi source IP của client thành IP frontend.
D. Xóa bản ghi stick-table khi client gửi request.
Đáp án đúng: A

Câu 21. Nếu ACL xác định client vượt mức request-rate, cấu hình deny-status nào thường phù hợp?
A. Trả HTTP 301 để chuyển sang backend khác.
B. Trả HTTP 204 để báo request đã được xử lý.
C. Trả HTTP 101 để nâng cấp kết nối WebSocket.
D. Trả HTTP 429 khi vượt giới hạn request.
Đáp án đúng: D

Câu 22. `maxconn` ở mức global của HAProxy giúp kiểm soát điều gì?
A. Giới hạn số kết nối đồng thời proxy phục vụ.
B. Giới hạn số server trong một khối backend.
C. Giới hạn số lần kiểm tra sức khỏe của Target.
D. Giới hạn số đường dẫn HTTP trong frontend.
Đáp án đúng: A

Câu 23. Ý nghĩa thường dùng của `timeout connect` là gì?
A. Giới hạn thời gian client gửi toàn bộ header.
B. Giới hạn thời gian chờ kết nối tới backend.
C. Giới hạn thời gian server trả dữ liệu HTTP.
D. Giới hạn thời gian phiên TLS còn hợp lệ.
Đáp án đúng: B

Câu 24. `timeout client` thường dùng để xử lý tình huống nào?
A. Đóng phiên nếu phía client bất hoạt quá thời hạn.
B. Đóng phiên nếu backend bắt tay TLS vượt thời hạn.
C. Đóng phiên khi DNS resolver trả về nhiều IP.
D. Đóng phiên khi client đổi header Host của request.
Đáp án đúng: A

Câu 25. `timeout server` ảnh hưởng đến điều gì trong đường proxy?
A. Thời gian bất hoạt tối đa từ server.
B. Thời gian chờ TCP accept ở cổng frontend.
C. Thời gian cache certificate do client cấp.
D. Thời gian chờ người dùng đăng nhập trang stats.
Đáp án đúng: A

Câu 26. Khai báo `server app1 10.0.0.5:8080 check` bật chức năng nào?
A. Tự bật TLS hai chiều ở server app1.
B. Tự theo dõi cookie session của server app1.
C. Kiểm tra ACL của request ngay trên app1.
D. Bật health check cho server app1.
Đáp án đúng: D

Câu 27. `option httpchk GET /health` thường được dùng để làm gì?
A. Gửi probe GET `/health` tới server.
B. Buộc mọi client gửi request đến path `/health`.
C. Chuyển request lỗi sang backend tên `/health`.
D. Ghi response `/health` vào log của frontend.
Đáp án đúng: A

Câu 28. Trong health check, các tham số `inter`, `fall`, `rise` phối hợp để làm gì?
A. Đặt giới hạn request HTTP mỗi giây và phút.
B. Đặt nhịp probe và ngưỡng xác nhận DOWN/UP.
C. Đặt mức TLS tối thiểu cho client và backend.
D. Đặt timeout riêng cho kết nối WebSocket.
Đáp án đúng: B

Câu 29. Khi cấu hình `server standby ... backup`, server standby thường được dùng lúc nào?
A. Khi một request có header Host đúng bằng standby.
B. Khi nhóm server thường đã không sẵn sàng.
C. Khi frontend nhận một request có method POST.
D. Khi client đã duy trì session đủ thời gian.
Đáp án đúng: B

Câu 30. Khi triển khai HAProxy reload đúng cơ chế graceful, ưu điểm chính là gì?
A. Xóa hết kết nối cũ trước khi mở listener mới.
B. Thực thi lại mọi request đã được backend xử lý.
C. Khởi tạo chứng chỉ TLS mới cho mỗi kết nối.
D. Nạp config mới mà hạn chế ngắt kết nối cũ.
Đáp án đúng: D

Câu 31. Với TLS passthrough qua HAProxy, mô tả nào chính xác?
A. HAProxy bắt buộc giải mã rồi ký lại HTTP request.
B. HAProxy luôn chèn header X-Forwarded-For vào TLS.
C. HAProxy chuyển luồng TLS để backend tự xử lý.
D. HAProxy luôn dùng HTTP ACL để lọc đường dẫn.
Đáp án đúng: C

Câu 32. Trong TCP TLS passthrough, ACL đọc SNI từ ClientHello hữu ích để làm gì?
A. Định tuyến theo URL path trong payload đã mã hóa.
B. Định tuyến theo mã trạng thái HTTP của backend.
C. Định tuyến theo hostname trước khi giải mã HTTP.
D. Định tuyến theo HTTP cookie do client trả về.
Đáp án đúng: C

Câu 33. Khi HAProxy nối HTTPS đến backend với kiểm tra chứng chỉ, cấu hình nào quan trọng?
A. `ssl verify none` để buộc xác thực CA backend.
B. `send-proxy` để bắt backend xác thực chứng chỉ.
C. `balance source` để bật kiểm tra TLS backend.
D. `ssl verify required ca-file` để kiểm CA backend.
Đáp án đúng: D

Câu 34. Tùy chọn `send-proxy` tới backend hỗ trợ PROXY protocol có tác dụng gì?
A. Gửi IP/port gốc qua header của PROXY protocol.
B. Thêm header HTTP X-Forwarded-For vào request.
C. Đổi toàn bộ TCP thành HTTP trước khi chuyển.
D. Đẩy certificate của frontend sang ứng dụng.
Đáp án đúng: A

Câu 35. Để kiểm tra cú pháp trước khi áp dụng cấu hình, lệnh nào thường dùng?
A. `haproxy -p -f /etc/haproxy/haproxy.cfg`.
B. `haproxy -s -f /etc/haproxy/haproxy.cfg`.
C. `haproxy -r -f /etc/haproxy/haproxy.cfg`.
D. `haproxy -c -f /etc/haproxy/haproxy.cfg`.
Đáp án đúng: D

Câu 36. Runtime stats socket của HAProxy chủ yếu hỗ trợ nhu cầu nào?
A. Tạo schema database cho từng phiên kết nối.
B. Tự cấp quyền đăng nhập Unix cho mọi client.
C. Lưu file chứng chỉ dùng trong TLS termination.
D. Xem thống kê và đổi trạng thái server lúc chạy.
Đáp án đúng: D

Câu 37. `option httplog` thường giúp gì trong việc quan sát proxy?
A. Chỉ ghi số byte TCP mà không có status HTTP.
B. Log status HTTP, thời gian và nội dung request.
C. Ghi mật khẩu HTTP của client để phục vụ điều tra.
D. Đẩy toàn bộ nội dung response vào database.
Đáp án đúng: B

Câu 38. Nếu HAProxy không còn server backend khả dụng để phục vụ request, HTTP status nào thường gặp?
A. HTTP 201 cho biết tài nguyên đã được tạo thành công.
B. HTTP 503 cho biết dịch vụ hiện không khả dụng.
C. HTTP 304 cho biết dữ liệu cache chưa thay đổi.
D. HTTP 101 cho biết kết nối đã được nâng cấp.
Đáp án đúng: B

Câu 39. Khi HAProxy trả HTTP 502, nguyên nhân khả dĩ nào liên quan phía upstream?
A. Response server sai định dạng hoặc có lỗi proxy.
B. Backend trả về HTTP 200 với nội dung hợp lệ.
C. Frontend ACL chọn backend đang phục vụ bình thường.
D. Client gửi request hợp lệ theo HTTP/1.1.
Đáp án đúng: A

Câu 40. Muốn chẩn đoán backend quá tải trong HAProxy, nhóm metric nào nên xem cùng nhau?
A. Chỉ số lượng file cấu hình và số frontend.
B. Queue, sessions, tỷ lệ lỗi và độ trễ.
C. Chỉ số lượng người truy cập trang stats.
D. Chỉ số certificate đã cài trong thư mục.
Đáp án đúng: B
