1. Log ứng dụng (application log) hữu ích nhất để ghi nhận loại sự kiện nào?
A. Ghi request HTTP ở biên cùng status và thời lượng xử lý.
B. Ghi sự kiện và kết quả xử lý bên trong logic ứng dụng.
C. Ghi hành động xác thực, phân quyền và sự kiện đáng ngờ.
D. Ghi sự kiện kernel, runtime và tài nguyên máy chủ.
Đáp án đúng: B

2. Access log của HTTP server thường ghi lại thông tin nào?
A. Exception, stack trace và thành phần phát sinh lỗi.
B. Actor, đối tượng và kết quả của thay đổi quyền truy cập.
C. Tên sự kiện nghiệp vụ cùng ID giao dịch được ghi nhận.
D. Method, path, status code và thời gian xử lý request.
Đáp án đúng: D

3. Error log khác access log ở điểm nào trong điều tra sự cố?
A. Ghi request, mã phản hồi và thời gian xử lý ở HTTP server.
B. Ghi hành động của người dùng trên dữ liệu cần kiểm toán.
C. Ghi lỗi, exception và ngữ cảnh xử lý thất bại.
D. Ghi mức dùng CPU, RAM và sự kiện từ kernel hệ điều hành.
Đáp án đúng: C

4. Security log nên ghi gì khi một lần đăng nhập bị từ chối?
A. Principal, nguồn truy cập, thời điểm, hành động và kết quả.
B. Mật khẩu người dùng nhập cùng cookie phiên và access token.
C. Toàn bộ nội dung request để người trực tự suy ra nguyên nhân.
D. Chỉ một dòng login failed, không cần thông tin bổ sung.
Đáp án đúng: A

5. Audit log được thiết kế chủ yếu để đáp ứng nhu cầu nào?
A. Đo latency của API cùng số request được xử lý mỗi giây.
B. Truy vết actor, action, target, thời điểm và outcome.
C. Lưu thông báo debug để lập trình viên tìm lỗi trong code.
D. Ghi trạng thái CPU và dung lượng ổ đĩa theo chu kỳ.
Đáp án đúng: B

6. Business log phù hợp nhất để biểu diễn sự kiện nào?
A. Một thread được tạo và đưa vào executor pool của ứng dụng.
B. Một container bị restart sau khi health check thất bại.
C. Đơn hàng được tạo, thanh toán, hủy hoặc hoàn tất.
D. Một HTTP connection đóng sau khi gửi response về client.
Đáp án đúng: C

7. Infrastructure log thường đến từ nguồn nào?
A. Quyết định nghiệp vụ cùng trạng thái đơn hàng của khách.
B. Lịch sử phê duyệt vai trò trong hệ thống quản trị truy cập.
C. Kernel, hệ điều hành, container runtime và nền tảng hạ tầng.
D. Thông tin request/response do logic ứng dụng xử lý.
Đáp án đúng: C

8. Một request tạo đơn thành công và cần được ghi nhận ở mức vận hành. Log level nào phù hợp?
A. INFO ghi nhận sự kiện bình thường có ý nghĩa vận hành.
B. ERROR dành cho mọi thao tác có tác động đến dữ liệu đơn.
C. DEBUG chỉ dùng khi muốn lưu từng biến cục bộ trong hàm.
D. FATAL phù hợp với mọi giao dịch có liên quan doanh thu.
Đáp án đúng: A

9. Ứng dụng không xử lý được request do database timeout. Log level nào phù hợp?
A. ERROR vì thao tác thất bại và cần được điều tra.
B. TRACE vì timeout chỉ là chi tiết nội bộ của một hàm.
C. INFO vì request vẫn được HTTP server tiếp nhận.
D. DEBUG vì lỗi database không liên quan tới người dùng.
Đáp án đúng: A

10. Bật DEBUG trên toàn bộ production có thể gây ra rủi ro nào?
A. Giảm cardinality metric vì log tự gộp những dòng giống nhau.
B. Chuyển log ứng dụng thành audit trail có chữ ký số.
C. Bắt buộc mọi request được lưu vào database nghiệp vụ.
D. Tăng dung lượng, chi phí xử lý và nguy cơ lộ dữ liệu.
Đáp án đúng: D

11. Một validation từ chối input sai định dạng do client gửi. Cách log nào hợp lý?
A. Luôn ghi FATAL vì request không thể hoàn thành thành công.
B. Ghi INFO/WARN theo ngữ cảnh, không coi là lỗi hệ thống.
C. Ghi ERROR cho mọi lần người dùng nhập sai một trường.
D. Không ghi lại dù cần phát hiện hành vi lạm dụng lặp lại.
Đáp án đúng: B

12. Structured logging đem lại lợi ích trực tiếp nào?
A. Field rõ ràng giúp lọc, truy vấn và tổng hợp log tự động.
B. Mỗi loại log bắt buộc phải nằm trong một file văn bản riêng.
C. Log tự trở thành metric có nhãn và histogram sau khi ghi.
D. Người vận hành không cần schema hay quy ước đặt tên field.
Đáp án đúng: A

13. Một JSON log record thường nên có nhóm trường cơ bản nào?
A. Timestamp, severity, service, message và ngữ cảnh sự kiện.
B. Password, access token, request body và toàn bộ cookie.
C. Chỉ message tự do để tránh chi phí lưu từng field riêng.
D. Một blob nhị phân không tên trường để tiết kiệm dung lượng.
Đáp án đúng: A

14. Vì sao timestamp log nên chuẩn hóa UTC và định dạng rõ ràng?
A. Làm mọi máy ghi log cùng tốc độ và xử lý request như nhau.
B. Tự đồng bộ đồng hồ máy chủ mà không cần NTP hoặc chrony.
C. Bảo đảm log nhiều nguồn luôn có đúng thứ tự vật lý.
D. Dễ đối chiếu sự kiện từ nhiều máy, tránh nhầm múi giờ.
Đáp án đúng: D

15. Tên event trong log nên được thiết kế thế nào để truy vấn ổn định?
A. Tên event ổn định, tách khỏi message có dữ liệu động.
B. Nhúng giá trị người dùng vào tên để lọc theo từng lần.
C. Sinh tên ngẫu nhiên mỗi lần để tránh trùng event.
D. Dùng nguyên stack trace làm tên event cho exception.
Đáp án đúng: A

16. Log có trace_id và span_id giúp ích trực tiếp điều gì?
A. Thay thế timestamp và severity trong mọi bản ghi log.
B. Mã hóa nội dung log để người thiếu trace ID không đọc được.
C. Cho phép truy cập log mà không cần kiểm tra quyền người dùng.
D. Liên kết log với trace/span để lần theo luồng gọi liên dịch vụ.
Đáp án đúng: D

17. API nhận header X-Request-ID do client gửi. Cách sử dụng an toàn là gì?
A. Tin mọi giá trị để tạo tên index và đường dẫn lưu trữ.
B. Kiểm tra định dạng và độ dài trước khi dùng làm correlation ID.
C. Dùng ID đó làm quyền truy cập vào log của request.
D. Ghi nguyên giá trị vào SQL query mà không kiểm tra đầu vào.
Đáp án đúng: B

18. Thông tin nào tuyệt đối không nên ghi nguyên văn vào log thông thường?
A. Mã trạng thái HTTP cùng thời gian xử lý request của API.
B. Tên service và phiên bản ứng dụng đang phát sinh log.
C. Mật khẩu, access token và khóa bí mật đang có hiệu lực.
D. Mã lỗi chuẩn hóa và ID sự kiện không nhạy cảm.
Đáp án đúng: C

19. Log cần chứa email hoặc số điện thoại để hỗ trợ nghiệp vụ. Biện pháp nào phù hợp?
A. Ghi toàn bộ dữ liệu rồi dựa vào quyền đọc để giảm rủi ro.
B. Giảm thiểu trường, mask hoặc pseudonymize theo nhu cầu.
C. Mã hóa field bằng khóa hardcode trong source code ứng dụng.
D. Đổi tên trường thành metadata để dữ liệu hết nhạy cảm.
Đáp án đúng: B

20. Vì sao không nên log toàn bộ request body theo mặc định?
A. Body luôn thiếu thông tin cần thiết để chẩn đoán lỗi API.
B. Body làm mất trace_id khi request đi qua reverse proxy.
C. Body không thể được mã hóa khi ghi ra stdout container.
D. Body có thể chứa PII, secret, payload lớn và input không tin cậy.
Đáp án đúng: D

21. Cách xử lý nào phù hợp khi ghi stack trace của exception?
A. Lặp lại toàn bộ stack trace ở mọi tầng bắt rồi ném lại lỗi.
B. Chỉ ghi chữ error để không tốn dung lượng lưu trữ.
C. Ghi loại lỗi, thông điệp an toàn và stack trace cần thiết.
D. Ghi biến môi trường và secret để tái tạo chính xác lỗi.
Đáp án đúng: C

22. Log access ở reverse proxy và application có thể bổ sung nhau thế nào?
A. Hai nguồn luôn giống nhau nên có thể xóa một nguồn log.
B. Proxy ghi request tại biên; app ghi quá trình xử lý bên trong.
C. Application log thay thế được mọi thông tin mạng tại proxy.
D. Proxy log thể hiện đầy đủ kết quả nghiệp vụ của giao dịch.
Đáp án đúng: B

23. HTTP status 401 và 403 trong access log thường biểu thị điều gì?
A. 401 thiếu/sai xác thực; 403 bị từ chối quyền truy cập.
B. 401 server quá tải; 403 request đã được xử lý thành công.
C. 401 lỗi TCP; 403 DNS không phân giải được hostname.
D. Cả hai mã đều nghĩa request chưa tới HTTP server.
Đáp án đúng: A

24. Hệ thống ghi database query log để điều tra truy vấn chậm. Cách cấu hình nào giảm rủi ro?
A. Ưu tiên duration, query fingerprint và tham số đã lọc nhạy cảm.
B. Ghi mọi literal parameter gồm token và dữ liệu cá nhân.
C. Ghi toàn transaction cùng mọi dữ liệu trả về từ bảng.
D. Bật verbose cho mọi query và giữ log vô thời hạn.
Đáp án đúng: A

25. Audit event cho thao tác thay đổi quyền admin nên chứa gì?
A. Mật khẩu admin, secret key và toàn bộ phiên đăng nhập.
B. Chỉ tên tài khoản mới được cấp quyền, bỏ actor thao tác.
C. Actor, action, target, timestamp, outcome và nguồn thực hiện.
D. Số CPU và RAM tại máy thực hiện thay đổi quyền.
Đáp án đúng: C

26. Để tăng độ tin cậy của audit trail, biện pháp nào hữu ích?
A. Giới hạn quyền sửa/xóa và dùng lưu trữ append-only.
B. Cho phép ứng dụng ghi đè log cũ để giảm dung lượng lưu trữ.
C. Lưu audit trong thư mục tạm với quyền đọc ghi chung.
D. Chỉ giữ bản audit mới nhất để tránh truy vấn nhầm lịch sử.
Đáp án đúng: A

27. Khi một sự kiện nghiệp vụ được retry do timeout, trường nào giúp nhận diện trùng lặp?
A. Timestamp ở collector vì mọi lần retry luôn có cùng giờ.
B. Event ID hoặc idempotency key ổn định của thao tác.
C. Tên máy xử lý để bỏ mọi sự kiện từ máy khác.
D. Log level để phân biệt lần đầu với lần retry.
Đáp án đúng: B

28. Log hạ tầng ghi kernel OOM kill một container. Điều tra nên liên kết thêm dữ liệu nào?
A. Nội dung hóa đơn và trạng thái thanh toán của khách hàng.
B. Mật khẩu người vận hành đã đăng nhập vào cluster.
C. Thời điểm, workload/container ID và metric bộ nhớ liên quan.
D. Toàn bộ payload HTTP của mọi request đang xử lý.
Đáp án đúng: C

29. Container ghi log ra stdout/stderr. Vai trò thường gặp của runtime hoặc agent là gì?
A. Tự phân loại chính xác ý nghĩa nghiệp vụ của mọi dòng log.
B. Thu thập stream, gắn metadata và chuyển log tới backend.
C. Thay ứng dụng tạo timestamp và correlation ID cho mọi event.
D. Tự giữ log vô thời hạn bên trong filesystem container.
Đáp án đúng: B

30. Log multiline như Java stack trace cần được xử lý thế nào?
A. Tách mỗi dòng stack trace thành một request độc lập.
B. Bỏ dòng bắt đầu bằng at vì chúng không phải log hợp lệ.
C. Ghép các dòng liên quan thành một event theo quy tắc parser.
D. Chuyển stack trace thành metric label để tìm kiếm nhanh.
Đáp án đúng: C

31. Một trường user_id xuất hiện trong log với giá trị khác nhau ở mỗi user. Cách index nào hợp lý?
A. Tạo một index riêng cho mỗi user_id để truy vấn nhanh.
B. Giữ field để lọc, tránh index nóng riêng theo từng user.
C. Loại bỏ mọi user_id kể cả khi điều tra cần kiểm soát.
D. Dùng user_id làm severity để nhóm các bản ghi cùng người.
Đáp án đúng: B

32. Một dịch vụ cần giữ access log 30 ngày và audit log 1 năm. Cách đặt retention phù hợp là gì?
A. Dùng một thời hạn ngắn giống nhau cho mọi nguồn log.
B. Áp retention riêng theo loại log, mục đích và nghĩa vụ.
C. Giữ mọi log vô thời hạn vì lưu trữ rẻ hơn điều tra.
D. Xóa audit sớm hơn access vì audit ít được truy vấn.
Đáp án đúng: B

33. Hot, warm và cold storage trong nền tảng log thường khác nhau ở đâu?
A. Phân biệt dữ liệu công khai, nội bộ và dữ liệu bí mật.
B. Xác định log level DEBUG, INFO và ERROR theo nguồn.
C. Chọn giao thức UDP, TCP hay HTTP cho từng log.
D. Đánh đổi tốc độ truy vấn, chi phí và thời gian lưu giữ.
Đáp án đúng: D

34. Log rotation và retention giải quyết hai vấn đề nào?
A. Rotation mã hóa log; retention ký số từng bản ghi.
B. Rotation phân loại severity; retention gán trace ID cho log.
C. Cả hai chỉ đổi định dạng JSON thành văn bản.
D. Rotation thay/chia file; retention quyết định thời gian giữ.
Đáp án đúng: D

35. Máy chủ sắp hết đĩa do log tăng bất thường. Hành động vận hành phù hợp là gì?
A. Xóa ngẫu nhiên các tệp log đang mở để giải phóng ngay.
B. Tìm nguồn tăng, kiểm tra rotation/retention và giữ dung lượng dự phòng.
C. Tắt log trên mọi dịch vụ mà không điều tra nguyên nhân.
D. Tăng DEBUG để có thêm thông tin trước khi xử lý dung lượng.
Đáp án đúng: B

36. Nhiều nguồn log dùng timestamp, time và @timestamp khác nhau. Trước khi điều tra tập trung cần làm gì?
A. Giữ nguyên mọi tên và kiểu vì backend tự hiểu ngữ nghĩa.
B. Xóa timestamp của nguồn ít quan trọng để tránh xung đột.
C. Chuyển mọi giá trị thời gian thành message dạng văn bản.
D. Chuẩn hóa schema và ánh xạ tên, kiểu trường về quy ước chung.
Đáp án đúng: D

37. Khi liên kết application, access và audit log cho một sự cố, trường nào hữu ích?
A. Timestamp chuẩn, service, request/trace ID và actor nếu có.
B. Tên file riêng của mỗi nguồn vì log thường nằm tách biệt.
C. Mức severity giống nhau vì cùng severity chứng minh cùng sự kiện.
D. IP nguồn vì một địa chỉ luôn đại diện một người dùng duy nhất.
Đáp án đúng: A

38. Đồng hồ giữa các host lệch vài phút gây khó khăn gì khi dựng timeline?
A. Thứ tự sự kiện có thể sai; cần đồng bộ clock và xét sai số.
B. Trace ID giữa các dịch vụ tự đổi sau mỗi lần lệch giờ.
C. Audit log tự sửa timestamp dựa vào thời điểm truy vấn.
D. Access log bỏ status code nếu clock không đồng bộ.
Đáp án đúng: A

39. Một hệ thống cần điều tra ai đã đọc hồ sơ khách hàng, loại log nào quan trọng?
A. Application debug log ghi mọi biến cục bộ của hàm đọc hồ sơ.
B. Infrastructure log ghi CPU và I/O của máy chứa hồ sơ.
C. Business log ghi đơn hàng sau khi hồ sơ được đọc.
D. Audit log ghi actor, tài nguyên, thao tác đọc và kết quả.
Đáp án đúng: D

40. Để tìm nguyên nhân request chậm, cách kết hợp log nào có giá trị nhất?
A. Audit log thường ghi thay đổi quyền, không ghi duration request.
B. Security log tập trung hành vi bất thường, không thay thế trace.
C. Business log ghi trạng thái đơn hàng, không chứa latency kỹ thuật.
D. Access log có duration, app log có thao tác và trace liên kết.
Đáp án đúng: D

41. Log gửi qua mạng tới collector tập trung nên được bảo vệ thế nào?
A. Dùng HTTP plaintext trong mạng riêng vì log không phải dữ liệu ứng dụng.
B. Đặt mật khẩu collector trong từng dòng log để xác minh nguồn.
C. Dùng TLS và xác thực agent hoặc endpoint nhận log.
D. Dùng UDP broadcast để mọi máy trong subnet đều nhận được.
Đáp án đúng: C

42. Ai nên có quyền truy cập audit log và security log?
A. Nhóm được ủy quyền theo vai trò, có kiểm soát truy cập.
B. Mọi developer và người dùng cuối để tự tra cứu mọi sự kiện.
C. Một tài khoản root dùng chung, không lưu lịch sử truy cập.
D. Bất kỳ dịch vụ gửi log nào cũng đọc được toàn bộ kho.
Đáp án đúng: A

43. Một pipeline log có quyền ghi và xóa bằng cùng tài khoản collector. Rủi ro nào cần giảm?
A. Log tự được phân loại thành business event thay vì audit.
B. Collector không thể nhận dữ liệu mới khi tài khoản có quyền xóa.
C. Kẻ chiếm quyền ghi có thể sửa hoặc xóa bằng chứng đã gửi.
D. Mọi log tự động chuyển sang cold storage sau khi ghi.
Đáp án đúng: C

44. Trong incident security, vì sao nên bảo toàn bản log gốc trước khi phân tích?
A. Để chỉnh sửa nội dung rồi tái hiện sự kiện chính xác.
B. Để bỏ qua timestamp và xác minh bằng màu sắc của log.
C. Giữ tính toàn vẹn và nguồn gốc làm bằng chứng điều tra.
D. Để mọi người cùng thay đổi bản ghi theo giả thuyết.
Đáp án đúng: C

45. Trước khi phát hành thay đổi schema log cho nhiều service, nên kiểm tra gì?
A. Chỉ kiểm tra ứng dụng biên dịch với phiên bản mới.
B. Tính tương thích parser, field bắt buộc và truy vấn downstream.
C. Xóa index cũ rồi mới xem dashboard còn hoạt động không.
D. Bỏ version schema vì consumer tự nhận dạng mọi field mới.
Đáp án đúng: B

46. Khi sampling access log do lưu lượng rất lớn, loại sự kiện nào cần giữ theo chính sách đầy đủ?
A. Request health check nội bộ đã có metric riêng để theo dõi.
B. Các dòng debug lặp lại từ vòng lặp xử lý nền.
C. Request tĩnh thành công, không có thay đổi nghiệp vụ.
D. Audit và security event cần truy vết trách nhiệm hoặc điều tra.
Đáp án đúng: D

47. Log event timestamp và ingest timestamp khác nhau ở điểm nào?
A. Event time do collector tạo; ingest time lấy từ đồng hồ ứng dụng.
B. Hai timestamp luôn bằng nhau nếu log được gửi bằng TLS.
C. Ingest time là thời điểm log được truy vấn lần đầu.
D. Event time là lúc phát sinh; ingest time là lúc collector nhận.
Đáp án đúng: D

48. Retention hết hạn nhưng bản ghi đang thuộc legal hold đã được phê duyệt. Nên xử lý thế nào?
A. Xóa theo lịch retention mà không cần kiểm tra legal hold.
B. Giữ mọi log của toàn hệ thống vô thời hạn.
C. Tạm dừng xóa bản ghi trong phạm vi legal hold được duyệt.
D. Chỉ chuyển log sang cold storage rồi xóa bản gốc.
Đáp án đúng: C
