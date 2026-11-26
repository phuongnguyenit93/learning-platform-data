Câu 01. API Gateway giữ vai trò chính nào giữa client và nhiều dịch vụ backend?
A. Tiếp nhận request, xử lý nghiệp vụ rồi ghi trực tiếp vào database.
B. Tiếp nhận request, áp chính sách chung rồi định tuyến đến dịch vụ.
C. Tiếp nhận request, lưu cache thay cho logic xử lý trong dịch vụ.
D. Tiếp nhận request, chọn backend theo DNS mà bỏ qua chính sách.
Đáp án đúng: B

Câu 02. Ranh giới trách nhiệm nào phù hợp giữa Gateway và dịch vụ đơn hàng?
A. Gateway ghi dữ liệu đơn hàng; dịch vụ chỉ thay đổi đường dẫn.
B. Gateway xác thực token; dịch vụ xét quyền sửa đơn cụ thể.
C. Gateway quyết định quyền sửa đơn; dịch vụ chỉ giải mã token.
D. Gateway xử lý đơn hoàn tiền; dịch vụ chỉ giới hạn tốc độ API.
Đáp án đúng: B

Câu 03. So với reverse proxy cơ bản, API Gateway thường bổ sung vai trò nào?
A. Chỉ chuyển tiếp request giữa mạng client và dịch vụ nội bộ.
B. Chỉ cân bằng tải theo số kết nối mà không xét chính sách API.
C. Quản lý chính sách API như xác thực, quota và quan sát lưu lượng.
D. Chỉ cache phản hồi theo URL mà không quản lý quota từng client.
Đáp án đúng: C

Câu 04. Một request GET /api/orders/42 cần đi tới dịch vụ orders. Gateway nên dựa vào gì?
A. Khớp path với route để chọn upstream orders phù hợp.
B. Đối chiếu cookie affinity mà bỏ qua route theo path cấu hình.
C. Chọn upstream theo status code mà backend đã trả lần gần nhất.
D. Chọn backend theo Host nhưng bỏ qua prefix path cần định tuyến.
Đáp án đúng: A

Câu 05. Khi dùng host-based routing, thông tin nào giúp chọn backend?
A. Query string, được đối chiếu với route theo tham số phiên bản.
B. Tên host yêu cầu, được đối chiếu với cấu hình route của gateway.
C. HTTP method yêu cầu, được đối chiếu với route theo phương thức.
D. Đường dẫn URL, được đối chiếu với route theo prefix của dịch vụ.
Đáp án đúng: B

Câu 06. Gateway có thể phân biệt GET và POST trên cùng một path bằng cách nào?
A. Dựa vào Content-Type để suy ra phương thức HTTP của request.
B. Dùng cả HTTP method trong điều kiện khớp route gửi upstream.
C. Chỉ dựa vào Content-Length để phân biệt yêu cầu đọc và ghi.
D. Chỉ dựa vào port của client để chọn backend cho từng phương thức.
Đáp án đúng: B

Câu 07. Tác dụng hợp lý của việc rewrite /api/v1/items thành /items là gì?
A. Thay đổi dữ liệu trong body theo schema bảng của service đích.
B. Thay method HTTP từ GET sang POST trong khi vẫn giữ nguyên path.
C. Bỏ bước xác thực vì đường dẫn nội bộ đã được rút gọn.
D. Giữ đường dẫn public ổn định và chuyển path backend cần nhận.
Đáp án đúng: D

Câu 08. Tại sao gateway thường gắn X-Request-ID cho request khi chuyển tiếp?
A. Để ép backend chỉ chạy một request trong một thời điểm.
B. Để tạo khóa cache duy nhất cho mọi lần gọi chung một endpoint.
C. Để dùng ID thay token đăng nhập khi xác thực mọi request.
D. Ghép log gateway với backend cho cùng một request.
Đáp án đúng: D

Câu 09. Khi gateway chuyển thông tin người dùng cho backend, phương án nào an toàn?
A. Xác thực token rồi kiểm soát header danh tính chuyển tiếp.
B. Đưa toàn bộ thông tin trong token vào query string công khai.
C. Bỏ quyền truy cập ở backend vì gateway đã xác thực tài khoản.
D. Tin mọi header danh tính do client cung cấp mà không kiểm tra.
Đáp án đúng: A

Câu 10. Trong xác thực JWT tại gateway, kiểm tra nào cần thực hiện?
A. Chỉ giải mã payload Base64 rồi chấp nhận mọi claim kèm theo.
B. Chỉ kiểm tra có header Authorization là cho phép đi tiếp.
C. Xác minh chữ ký và các claim như expiry, issuer, audience.
D. Chỉ so sánh độ dài JWT với độ dài token đã nhận trước đó.
Đáp án đúng: C

Câu 11. Claim aud của JWT giúp gateway kiểm tra điều gì?
A. Token có được truyền qua đường kết nối TLS trong lần gửi hiện tại.
B. Token có phải được cấp bởi khóa RSA dài tối thiểu 2048 bit.
C. Token có được phát hành cho đúng đối tượng nhận dự kiến hay không.
D. Token có số lượng quyền hạn phù hợp với toàn bộ hệ thống hay không.
Đáp án đúng: C

Câu 12. Khi bên cấp token xoay vòng khóa ký JWT, gateway nên làm gì?
A. Dùng JWKS phù hợp, tra key theo kid và làm mới cache an toàn.
B. Giữ khóa đã xóa vĩnh viễn để tránh lỗi xác thực request cũ.
C. Đổi toàn bộ token người dùng thành API key cố định tại gateway.
D. Tắt xác minh chữ ký cho tới khi mọi client đổi được token.
Đáp án đúng: A

Câu 13. Trong bảo vệ API, API key thường có hạn chế nào so với token người dùng?
A. Nhận diện client hay ứng dụng nhưng có thể thiếu ngữ cảnh user.
B. Luôn mang đầy đủ claim người dùng và quyền truy cập từng bản ghi.
C. Luôn có chữ ký số và thời hạn được xác nhận theo chuẩn JWT.
D. Đảm bảo chính sách quyền theo từng tài nguyên phía backend.
Đáp án đúng: A

Câu 14. Khi áp mTLS giữa client và gateway, chứng chỉ phía client dùng để làm gì?
A. Giúp gateway tự cấp JWT người dùng mà không cần danh tính.
B. Giúp gateway thay thế toàn bộ kiểm tra quyền theo tài nguyên.
C. Dùng chứng chỉ client để xác định quyền với từng bản ghi nghiệp vụ.
D. Xác thực danh tính client bằng chứng chỉ được tin cậy.
Đáp án đúng: D

Câu 15. Nếu gateway kết thúc TLS phía client, muốn mã hóa tiếp tới backend cần gì?
A. Thiết lập TLS cho kết nối từ gateway tới upstream tương ứng.
B. Chỉ nén HTTP body là đường truyền nội bộ đã được bảo vệ.
C. Chỉ thêm header X-Forwarded-Proto mà không cần TLS upstream.
D. Chỉ bật HTTPS phía client là dữ liệu tới backend tự mã hóa.
Đáp án đúng: A

Câu 16. Khi trình duyệt gửi CORS preflight OPTIONS, gateway cần xử lý thế nào?
A. Chuyển OPTIONS thành POST để backend trả nội dung tài nguyên.
B. Cho phép mọi origin mặc định nếu request đã có cookie đăng nhập.
C. Bỏ CORS trên mọi route để trình duyệt tự quyết định quyền đọc.
D. Áp chính sách CORS cho origin, method và header được cho phép.
Đáp án đúng: D

Câu 17. Token bucket dùng để rate limit có đặc điểm nào?
A. Đếm số request theo cửa sổ cố định và reset cùng một thời điểm.
B. Mỗi request phải cách đều nhau, không cho phép burst ngắn hạn.
C. Token được nạp lại theo thời gian và cho phép burst có giới hạn.
D. Giới hạn số kết nối TCP thay cho số request vào gateway.
Đáp án đúng: C

Câu 18. Nhược điểm của bộ đếm fixed-window rate limiting là gì?
A. Request có thể dồn gần ranh giới giữa hai cửa sổ liên tiếp.
B. Request không thể dùng chung quota trên nhiều instance gateway.
C. Request bắt buộc chờ hết phiên TCP mới được tính vào quota.
D. Request luôn được phép vượt quota ở mọi thời điểm trong cửa sổ.
Đáp án đúng: A

Câu 19. Khi một client vượt quota request, mã HTTP nào thường phù hợp?
A. Trả 401 Unauthorized vì token của client vừa hết hạn.
B. Trả 404 Not Found vì backend không có route tương ứng.
C. Trả 409 Conflict vì đã xảy ra xung đột cập nhật bản ghi.
D. Trả 429 Too Many Requests và có thể kèm Retry-After.
Đáp án đúng: D

Câu 20. Trong hệ gateway chạy nhiều replica, rate limit toàn cục cần lưu ý gì?
A. Dựa vào cache trình duyệt để chia quota giữa các replica.
B. Đồng bộ trạng thái đếm hoặc quota giữa các gateway replica.
C. Tạo một bộ đếm riêng không đồng bộ trên từng gateway replica.
D. Giảm thời gian timeout của upstream để mỗi replica tự giới hạn.
Đáp án đúng: B

Câu 21. Khi giới hạn theo IP client sau nhiều lớp proxy, gateway nên làm gì?
A. Dùng địa chỉ của reverse proxy cuối cùng làm IP của mọi client.
B. Đọc IP từ query parameter tùy ý do người dùng gửi lên gateway.
C. Chỉ tin IP header do proxy đáng tin cậy chuyển tới.
D. Tin header X-Forwarded-For bất kể request tới từ mạng nào.
Đáp án đúng: C

Câu 22. Khác biệt giữa concurrency limit và rate limit là gì?
A. Concurrency limit chặn số request đang xử lý tại một thời điểm.
B. Concurrency limit tính tổng request trong từng phút cố định.
C. Concurrency limit chỉ đếm số response lỗi sau khi xử lý.
D. Concurrency limit chỉ áp dụng cho những request đã vào cache.
Đáp án đúng: A

Câu 23. Vì sao nên giới hạn kích thước request body tại gateway?
A. Giúp tất cả request được xử lý đúng thứ tự gửi tới gateway.
B. Giúp backend tự động kiểm tra logic nghiệp vụ của mỗi request.
C. Giảm nguy cơ request lớn chiếm băng thông và tài nguyên xử lý.
D. Giúp gateway bỏ bước kiểm tra quyền truy cập vào từng tài nguyên.
Đáp án đúng: C

Câu 24. Round-robin load balancing thường chọn backend ra sao?
A. Chọn lần lượt các instance đủ điều kiện theo vòng luân phiên.
B. Chọn instance có số CPU nhàn rỗi lớn nhất theo số liệu thời gian thực.
C. Chọn instance theo hash của user ID để cố định phiên truy cập.
D. Chọn instance có ít kết nối đang hoạt động nhất tại mọi lúc.
Đáp án đúng: A

Câu 25. Least-connections load balancing ưu tiên instance nào?
A. Instance có tỷ lệ CPU sử dụng thấp nhất ở lần đo gần đây.
B. Instance đang có ít kết nối hoạt động theo bộ đếm của cân bằng tải.
C. Instance có thời gian phản hồi trung bình thấp nhất vừa đo.
D. Instance có tổng request ít nhất trong cửa sổ thời gian cố định.
Đáp án đúng: B

Câu 26. Khi một backend instance trượt health check, gateway nên làm gì?
A. Xóa route public để toàn bộ client nhận 404 cho tới khi phục hồi.
B. Tiếp tục gửi đều request vào instance đó để duy trì round-robin.
C. Đóng tất cả kết nối đang phục vụ ở mọi instance còn khỏe.
D. Tạm loại instance lỗi khỏi danh sách đích được định tuyến mới.
Đáp án đúng: D

Câu 27. Sticky session trong cân bằng tải có đánh đổi nào?
A. Bảo đảm client luôn tìm được instance cũ sau khi instance hỏng.
B. Loại bỏ hoàn toàn nhu cầu kiểm tra sức khỏe của upstream.
C. Tự biến mọi backend thành stateless nên không cần session store.
D. Duy trì affinity tới instance có thể gây phân bố tải không đều.
Đáp án đúng: D

Câu 28. Khi rollout canary một phiên bản backend mới, gateway có thể làm gì?
A. Chuyển toàn bộ traffic tới bản mới trước khi đo tỷ lệ lỗi.
B. Bỏ health check trong thời gian chuyển tiếp để tránh nhiễu.
C. Định tuyến một phần nhỏ traffic tới bản mới rồi quan sát.
D. Chạy migration dữ liệu bằng cách sao chép mọi request POST.
Đáp án đúng: C

Câu 29. Khi cache GET ở gateway, cache key cần xét những thành phần nào?
A. Chỉ tên service backend để mọi endpoint dùng cùng một bản cache.
B. Path, query và ngữ cảnh biến thiên theo header hoặc quyền truy cập.
C. Chỉ địa chỉ IP gateway để mọi client chia cùng một response.
D. Chỉ độ dài response body để các dữ liệu bằng kích thước dùng chung.
Đáp án đúng: B

Câu 30. Khi backend cập nhật dữ liệu nhưng gateway có cache, vấn đề gì cần giải quyết?
A. Chính sách round-robin để mọi cache entry được tạo trên từng node.
B. Chính sách nén để nội dung đã cache tự chuyển sang bản mới.
C. Chính sách TTL hoặc invalidation để tránh trả dữ liệu lỗi thời.
D. Chính sách retry GET để sửa dữ liệu ngay trong database gốc.
Đáp án đúng: C

Câu 31. Gateway nhận phản hồi không hợp lệ từ upstream và trả 502. Ý nghĩa nào phù hợp?
A. Gateway đã chặn request vì client vượt hạn mức quota.
B. Gateway không thể xác thực token do claim audience sai.
C. Gateway đã xử lý hoàn tất nhưng trình duyệt từ chối CORS.
D. Gateway gặp lỗi khi lấy phản hồi hợp lệ từ dịch vụ upstream.
Đáp án đúng: D

Câu 32. HTTP 504 từ gateway thường gắn với tình huống nào?
A. Gateway hết thời gian chờ phản hồi từ upstream phù hợp.
B. Gateway phát hiện client đã gửi quá nhiều request trong phút.
C. Gateway từ chối vì phương thức HTTP không được cấp quyền.
D. Gateway thiếu cấu hình route cho đường dẫn public đã gọi.
Đáp án đúng: A

Câu 33. Nếu không còn backend khỏe để nhận request, gateway thường có thể trả gì?
A. 401 Unauthorized vì client chưa gửi bearer token hợp lệ.
B. 503 Service Unavailable để báo dịch vụ tạm không phục vụ.
C. 409 Conflict vì backend vừa sửa dữ liệu ở cùng bản ghi.
D. 400 Bad Request vì payload không đúng schema nghiệp vụ.
Đáp án đúng: B

Câu 34. Khi cấu hình timeout nhiều tầng, nguyên tắc nào phù hợp?
A. Để mọi upstream timeout vô hạn để tránh lỗi do mạng chậm.
B. Đặt retry timeout dài hơn deadline tổng để yêu cầu chắc thành công.
C. Chỉ đặt timeout phía trình duyệt và bỏ timeout tại gateway.
D. Phân bổ ngân sách thời gian request nhất quán giữa các hop.
Đáp án đúng: D

Câu 35. Vì sao không nên retry POST tạo đơn hàng tùy ý sau timeout?
A. Timeout luôn chứng tỏ backend chưa nhận được request ban đầu.
B. HTTP POST luôn idempotent nên retry không gây tác dụng phụ.
C. Request có thể đã thành công, retry dễ tạo bản ghi trùng.
D. Gateway sẽ tự rollback lệnh ghi dù backend đã trả thành công.
Đáp án đúng: C

Câu 36. Circuit breaker tại gateway giúp bảo vệ hệ thống như thế nào?
A. Tự tăng số replica backend khi có bất kỳ request bị lỗi.
B. Ngắt gọi tạm thời tới upstream lỗi nhiều để giảm tải dây chuyền.
C. Bỏ kiểm tra token khi một dịch vụ cần phục hồi sau sự cố.
D. Thay thế mọi health check và luôn giữ một kết nối TCP cố định.
Đáp án đúng: B

Câu 37. Khi truyền traceparent qua gateway, mục đích chính là gì?
A. Liên kết các span để theo dõi đường đi request xuyên dịch vụ.
B. Truyền quyền truy cập của user thay cho Authorization header.
C. Truyền cấu hình timeout của mọi service dưới dạng token bí mật.
D. Chỉ truyền định danh instance chạy gateway vào backend.
Đáp án đúng: A

Câu 38. Nếu p95 gateway cao nhưng p95 upstream thấp, nên xem xét thêm gì?
A. Chỉ khoảng TTL của cache backend vì gateway không thể có queue.
B. Chỉ dữ liệu khóa ngoại của database vì upstream luôn là nút thắt.
C. Đo queue, thời gian policy và truyền dữ liệu tại gateway.
D. Chỉ số lượng tài khoản quản trị vì gateway không có latency riêng.
Đáp án đúng: C

Câu 39. Khi ghi access log Gateway, nguyên tắc nào phù hợp với dữ liệu nhạy cảm?
A. Ghi đầy đủ password trong body để xác định lỗi xác thực.
B. Ghi metadata cần chẩn đoán, che token và dữ liệu cá nhân.
C. Ghi toàn bộ cookie đăng nhập vào log ở mọi môi trường.
D. Ghi nguyên Authorization header để thuận tiện phát lại request.
Đáp án đúng: B

Câu 40. Để thay đổi routing và policy gateway an toàn, quy trình nào phù hợp?
A. Thay trực tiếp tất cả route production mà không cần kiểm thử.
B. Giữ cấu hình riêng từng node và chỉnh tay khi có sự cố.
C. Chỉ dùng khả năng reload nhanh, không theo dõi lỗi sau rollout.
D. Version hóa cấu hình, kiểm thử và rollout có giám sát để rollback.
Đáp án đúng: D
