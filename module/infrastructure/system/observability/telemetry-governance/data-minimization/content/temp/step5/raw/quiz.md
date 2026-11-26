Câu 01. Mục tiêu cốt lõi của data minimization trong observability là gì?
A. Chỉ thu thập trường cần thiết để vận hành và điều tra.
B. Thu thập mọi trường rồi cấp quyền xem theo nhóm.
C. Giữ payload nguyên bản để mọi sự cố đều tái hiện được.
D. Chỉ giảm kích thước dữ liệu sau khi lưu vào kho.
Đáp án đúng: A

Câu 02. Trước khi đưa một trường vào log, nhóm nên xác định điều gì?
A. Số lượng collector sẽ nhận bản ghi từ ứng dụng.
B. Độ dài tối đa của chuỗi và kiểu mã hóa trong JSON.
C. Mức nhạy cảm, mục đích dùng và thời hạn cần giữ.
D. Tên dashboard sẽ hiển thị trường đó cho người trực.
Đáp án đúng: C

Câu 03. Schema log cần trường tùy chọn theo nguyên tắc nào?
A. Allowlist trường đã duyệt theo mục đích sử dụng.
B. Ghi toàn bộ object rồi để người truy vấn tự lọc.
C. Đưa mọi trường mới vào log trước khi review.
D. Denylist vài tên khóa phổ biến rồi cho phép phần còn lại.
Đáp án đúng: A

Câu 04. Vị trí nào thường tốt nhất để ngăn dữ liệu thừa phát sinh trong log?
A. Tại ứng dụng, trước khi dữ liệu được ghi ra.
B. Tại dashboard sau khi log đã được index.
C. Trong báo cáo cuối tháng sau khi xuất archive.
D. Ở người dùng truy vấn bằng cách bỏ field khỏi bảng.
Đáp án đúng: A

Câu 05. Khi ứng dụng cũ chưa thể sửa, collector có thể hỗ trợ gì?
A. Tự xác định mục đích hợp pháp cho mọi trường.
B. Khôi phục secret đã bị ứng dụng mã hóa trong log.
C. Che hoặc loại field nhạy cảm trước khi forward.
D. Thay quyền truy cập database của ứng dụng nguồn.
Đáp án đúng: C

Câu 06. Một API key xuất hiện trong exception message. Cách xử lý phù hợp là gì?
A. Mã hóa Base64 key để vẫn tìm kiếm được khi cần.
B. Chuyển key thành metric tag để giới hạn người xem.
C. Chỉ hạ severity xuống DEBUG rồi giữ nguyên chuỗi.
D. Loại secret trước khi ghi hoặc chuyển log đi.
Đáp án đúng: D

Câu 07. Với header Authorization trong access log, nên làm gì?
A. Giữ nguyên header nhưng bỏ tên người dùng khỏi log.
B. Chỉ ghi token khi response trả mã lỗi 5xx.
C. Hash token bằng SHA-1 rồi lưu vào label của metric.
D. Loại bỏ giá trị token hoặc thay bằng dấu che.
Đáp án đúng: D

Câu 08. URL có query parameter chứa email hoặc mã phiên nên được xử lý thế nào?
A. Chuyển toàn bộ URL thành tag để tìm kiếm nhanh.
B. Giữ nguyên URL vì query string không phải dữ liệu cá nhân.
C. Che hoặc bỏ các parameter nhạy cảm trước khi log URL.
D. Chỉ che hostname và giữ mọi query parameter còn lại.
Đáp án đúng: C

Câu 09. Khi cần chẩn đoán lỗi API, cách ghi request body nào hợp lý?
A. Ghi body nguyên vẹn riêng cho request có lỗi 4xx.
B. Chỉ ghi field allowlist hoặc metadata đã giảm thiểu.
C. Chuyển body sang trace baggage để tránh log storage.
D. Ghi toàn bộ body rồi dựa vào retention ngắn để bảo vệ.
Đáp án đúng: B

Câu 10. Vì sao stack trace cần được xem xét trước khi đưa vào telemetry?
A. Stack trace luôn bao gồm mật khẩu của mọi kết nối.
B. Collector không thể xử lý stack trace có nhiều dòng.
C. Stack trace làm mất timestamp của các log lân cận.
D. Message và giá trị exception có thể chứa dữ liệu nhạy cảm.
Đáp án đúng: D

Câu 11. Muốn liên kết sự kiện của cùng người dùng mà không lưu email, nên cân nhắc gì?
A. Dùng định danh giả ổn định với phạm vi và quyền truy cập rõ.
B. Tạo ID ngẫu nhiên mới cho từng log line độc lập.
C. Đưa email thô vào metric tag để truy vấn chéo nhanh.
D. Dùng IP công khai làm định danh lâu dài cho mọi thiết bị.
Đáp án đúng: A

Câu 12. Hash email đơn thuần có bảo đảm ẩn danh không?
A. Có; chỉ cần chuyển chữ thường trước khi hash là đủ.
B. Không; email dễ bị dò ngược bằng từ điển.
C. Không; vì mọi thuật toán hash đều lưu bản rõ bên cạnh.
D. Có; hash luôn không thể liên kết lại với người dùng.
Đáp án đúng: B

Câu 13. Khi cần pseudonym ổn định khó dò bằng từ điển, lựa chọn nào phù hợp hơn?
A. Dùng HMAC với khóa bí mật riêng được bảo vệ.
B. Dùng hash không khóa trên email đã chuyển chữ thường.
C. Dùng Base64 để thay thế chuỗi email trước khi lưu.
D. Dùng số thứ tự tăng dần chung cho mọi tenant.
Đáp án đúng: A

Câu 14. Mã hóa dữ liệu nhạy cảm trong kho telemetry có thay thế data minimization không?
A. Không; vẫn cần tránh thu thập trường không cần thiết.
B. Không; vì dữ liệu mã hóa không thể truy vấn bằng index.
C. Có; mã hóa đủ mạnh khiến mọi trường đều có thể giữ.
D. Có; chỉ cần mã hóa ở ổ đĩa của backend lưu trữ.
Đáp án đúng: A

Câu 15. Khi thiết kế metric labels, lựa chọn nào thường an toàn và hữu ích?
A. Dùng toàn bộ URL và query string làm label metric.
B. Dùng timestamp chính xác và UUID cho mỗi request.
C. Dùng user_id, request_id và session token cho từng mẫu.
D. Dùng dimension hữu hạn như service, env hoặc region.
Đáp án đúng: D

Câu 16. Vì sao label cardinality cao làm tăng chi phí metrics?
A. Nhiều label khiến timestamp của mẫu metric dài hơn.
B. Nhiều tổ hợp label tạo thêm time series phải lưu và xử lý.
C. Cardinality làm mọi metric chuyển thành log event riêng.
D. Nhiều label buộc Agent tạo thêm một dashboard mỗi lần.
Đáp án đúng: B

Câu 17. Khi cần quan sát số lượt lỗi theo khách hàng, cách giảm thiểu nào phù hợp?
A. Lưu toàn bộ request body cạnh mỗi counter tăng.
B. Tạo một time series riêng cho từng customer ID.
C. Tổng hợp theo nhóm cần thiết thay vì giữ ID từng khách.
D. Ghi email khách hàng vào annotation của mọi metric point.
Đáp án đúng: C

Câu 18. Muốn theo dõi phân vị độ trễ mà không giữ ID từng request, nên dùng gì?
A. Counter riêng cho mỗi giá trị latency và URL.
B. Log raw duration cùng toàn bộ payload cho mọi request.
C. Gauge gắn request_id để giữ mẫu của từng request.
D. Histogram hoặc distribution được tổng hợp phù hợp.
Đáp án đúng: D

Câu 19. Trong span attributes, nguyên tắc tối thiểu hóa nào phù hợp?
A. Sao chép toàn bộ request headers vào mọi span.
B. Đưa nội dung request body vào span để tìm kiếm thuận tiện.
C. Chỉ thêm thuộc tính cần cho truy vết và phân tích.
D. Thêm mọi biến môi trường của process vào span.
Đáp án đúng: C

Câu 20. Baggage trong distributed tracing cần được kiểm soát vì sao?
A. Nó thay thế trace_id nên không cần lọc thuộc tính.
B. Nó có thể lan truyền dữ liệu qua nhiều service và ranh giới tin cậy.
C. Nó chỉ tồn tại trong process nguồn và không qua network.
D. Nó tự mã hóa mọi giá trị trước khi gửi sang service khác.
Đáp án đúng: B

Câu 21. Head-based sampling thường quyết định giữ trace ở thời điểm nào?
A. Khi log index hoàn tất và dashboard được tải lần đầu.
B. Sau khi retention xóa các trace quá thời hạn.
C. Sau khi mọi span kết thúc và đã được gom về một nơi.
D. Khi trace bắt đầu, trước khi biết kết quả toàn bộ request.
Đáp án đúng: D

Câu 22. Tail-based sampling hữu ích trong trường hợp nào?
A. Quyết định sampling chỉ dựa trên span đầu tiên được tạo.
B. Giữ trace chậm hoặc lỗi sau khi quan sát toàn bộ trace.
C. Loại bỏ trace ngay khi request bắt đầu để giảm bộ nhớ.
D. Chọn trace theo tên dashboard đang được người dùng mở.
Đáp án đúng: B

Câu 23. Để tail sampling hoạt động nhất quán, kiến trúc cần lưu ý gì?
A. Đặt sampling rate khác nhau ngẫu nhiên ở mỗi service.
B. Mỗi collector tự quyết định độc lập cho từng span.
C. Chỉ gửi root span; các child span không cần tập hợp.
D. Các span của trace cần tới cùng điểm quyết định sampling.
Đáp án đúng: D

Câu 24. Có nên áp dụng sampling ngẫu nhiên giống nhau cho audit events không?
A. Có; chỉ cần tăng sample rate khi có incident.
B. Không; sự kiện audit bắt buộc cần chính sách lưu giữ riêng.
C. Không; audit events phải được ghi vào metric counter.
D. Có; audit log cũng chỉ là telemetry có thể lấy mẫu.
Đáp án đúng: B

Câu 25. Khi lấy mẫu trace để giảm chi phí, tiêu chí nào có ích?
A. Giữ trace lỗi, chậm theo tiêu chí đã cấu hình.
B. Chỉ giữ request có payload lớn nhất trong mỗi phút.
C. Chỉ giữ trace theo thứ tự đến collector đầu tiên.
D. Loại trace có status lỗi để giảm dữ liệu nhạy cảm.
Đáp án đúng: A

Câu 26. Retention cho log, metric và trace nên được thiết kế thế nào?
A. Chọn ngắn nhất có thể mà không cần xem yêu cầu vận hành.
B. Dùng cùng thời hạn tối đa cho mọi dữ liệu để dễ quản lý.
C. Giữ vô thời hạn rồi dựa vào quyền truy cập để hạn chế.
D. Theo mục đích, độ nhạy cảm và nhu cầu điều tra của từng loại.
Đáp án đúng: D

Câu 27. Vì sao nên tách retention cho audit log và debug log?
A. Debug log bắt buộc lưu lâu hơn để tái hiện sự cố cũ.
B. Hai loại log phải cùng retention để tránh lệch timestamp.
C. Chúng có mục đích, yêu cầu kiểm soát và thời hạn khác nhau.
D. Audit log luôn ít nhạy cảm hơn debug log trong mọi hệ thống.
Đáp án đúng: C

Câu 28. Khi hết hạn retention, điều gì cần được tính đến ngoài bản dữ liệu chính?
A. Chỉ dashboard đang mở trên trình duyệt người vận hành.
B. Bản sao, archive, export và các bản lưu dự phòng liên quan.
C. Chỉ cache DNS của collector và địa chỉ IP của host.
D. Chỉ các metric đã được chuyển thành alert.
Đáp án đúng: B

Câu 29. Nguyên tắc cấp quyền truy cập telemetry nào phù hợp?
A. Chỉ phân quyền theo tên dashboard, không xét dữ liệu nguồn.
B. Cấp quyền đọc toàn bộ log cho mọi kỹ sư để thuận tiện.
C. Least privilege theo vai trò, mục đích và phạm vi dữ liệu.
D. Dùng chung một tài khoản admin cho collector và người dùng.
Đáp án đúng: C

Câu 30. Nếu nhiều khách hàng dùng chung nền tảng observability, cần bảo đảm điều gì?
A. Dùng chung API key cho mọi tenant để đơn giản vận hành.
B. Ranh giới tenant và kiểm tra quyền ở cả query lẫn ingest.
C. Ẩn tenant_id trên dashboard là đủ ngăn truy cập chéo.
D. Chỉ đặt tenant_id thành label rồi tin client tự khai báo.
Đáp án đúng: B

Câu 31. Audit trail của thay đổi chính sách data minimization nên ghi gì?
A. Toàn bộ secret đã bị che để người review khôi phục.
B. Chỉ số lượng log bị xóa mà không ghi người thực hiện.
C. Ai đổi, trường nào đổi, thời điểm và lý do thay đổi.
D. Nội dung mọi request của người quản trị trong ngày.
Đáp án đúng: C

Câu 32. Vì sao mã hóa khi truyền và khi lưu vẫn chưa đủ?
A. Nó không ngăn việc thu thập quá mức hoặc cấp quyền sai.
B. Nó tự loại bỏ dữ liệu cá nhân khỏi trace attributes.
C. Mã hóa làm mọi field nhạy cảm tự biến thành dữ liệu tổng hợp.
D. Mã hóa khiến retention không còn cần thiết trong telemetry.
Đáp án đúng: A

Câu 33. Policy as code hỗ trợ quản trị dữ liệu telemetry ra sao?
A. Thay thế kiểm thử pipeline bằng một file cấu hình duy nhất.
B. Đưa quy tắc allowlist, redaction và retention vào kiểm soát phiên bản.
C. Cho phép mọi service tự bỏ qua policy khi có lỗi.
D. Tự quyết định trường nào hợp pháp mà không cần người phụ trách.
Đáp án đúng: B

Câu 34. Cách kiểm tra redaction có hiệu quả trong pipeline là gì?
A. Dùng dữ liệu khách hàng thật và tìm thủ công trong dashboard.
B. Chỉ kiểm tra cấu hình regex mà không chạy log qua pipeline.
C. Tắt collector rồi xác nhận kho log không nhận dữ liệu mới.
D. Gửi giá trị canary giả rồi xác nhận không xuất hiện ở đầu ra.
Đáp án đúng: D

Câu 35. Khi thử nghiệm policy trên telemetry, dữ liệu đầu vào nào nên ưu tiên?
A. Dữ liệu tổng hợp hoặc synthetic có giá trị nhạy cảm giả lập.
B. Bản sao toàn bộ trace production không giới hạn truy cập.
C. Bản dump production đầy đủ gồm token và thông tin cá nhân.
D. Dữ liệu thật đã export sang máy cá nhân của người phát triển.
Đáp án đúng: A

Câu 36. Redaction quá rộng có thể gây tác động nào tới observability?
A. Tăng độ chính xác trace sampling trong mọi trường hợp.
B. Làm mất trường cần để phân loại lỗi và liên kết tín hiệu.
C. Làm tăng độ phân giải metric dù đã bỏ label.
D. Tự giảm latency ứng dụng vì log line ngắn hơn.
Đáp án đúng: B

Câu 37. Sau khi loại bỏ PII, trường nào có thể giữ để hỗ trợ điều tra?
A. Toàn bộ cookie, email và payload của request lỗi.
B. Access token đã mã hóa Base64 cùng request body.
C. Mã định danh trực tiếp của khách hàng trong mọi span.
D. Status code, service, phiên bản và nhóm lỗi phù hợp.
Đáp án đúng: D

Câu 38. Muốn phát hiện collector vô tình ngừng che một trường nhạy cảm, nên làm gì?
A. Tắt parse error để tránh báo động khi schema thay đổi.
B. Chỉ theo dõi CPU của collector và dung lượng ổ đĩa.
C. Theo dõi kiểm thử canary và kiểm tra đầu ra định kỳ.
D. Tăng thời hạn retention để có nhiều log cho người kiểm tra.
Đáp án đúng: C

Câu 39. Chỉ số nào giúp đánh giá pipeline minimization mà không làm lộ dữ liệu?
A. Nội dung request đầy đủ trước và sau mỗi lần xử lý.
B. Danh sách email và ID người dùng có xuất hiện trong log.
C. Số trường bị redact, drop và tỷ lệ lỗi xử lý theo nguồn.
D. Giá trị bản rõ của token đã bị che trong từng sự kiện.
Đáp án đúng: C

Câu 40. Sau khi triển khai policy mới, cách xác minh cân bằng quyền riêng tư và chất lượng tín hiệu là gì?
A. Đo privacy reduction cùng độ phủ tín hiệu cần thiết.
B. Chỉ đếm số byte giảm được, không xem nội dung bị mất.
C. Chỉ kiểm tra dashboard còn mở mà không đối chiếu log.
D. Giữ nguyên mọi trường để so sánh rồi bỏ qua policy.
Đáp án đúng: A
