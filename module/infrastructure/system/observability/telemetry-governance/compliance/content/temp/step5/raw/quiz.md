Câu 1. Mục tiêu của purpose limitation khi xử lý telemetry là gì?
A. Thu thập mọi trường có thể hữu ích cho phân tích sau này.
B. Chỉ thu thập và dùng dữ liệu cho mục đích đã xác định.
C. Dùng chung telemetry cho mọi nhóm mà không cần xem xét mục đích.
D. Giữ dữ liệu vô thời hạn để tránh mất khả năng điều tra.
Đáp án đúng: B

Câu 2. Một inventory telemetry hữu ích cần ghi nhận những thông tin nào?
A. Chỉ tên dashboard, số panel và màu sắc biểu đồ đang dùng.
B. Chỉ địa chỉ IP của Collector và phiên bản agent đang chạy.
C. Chỉ tổng dung lượng TSDB và số lần scrape mỗi phút.
D. Ghi tín hiệu, trường, nguồn, đích nhận và retention.
Đáp án đúng: D

Câu 3. Khi phân loại telemetry, tiêu chí nào giúp phát hiện dữ liệu cá nhân?
A. Chỉ xem trường có tên `email` hoặc `phone` trong payload.
B. Xem định danh trực tiếp và dữ liệu có thể liên kết.
C. Chỉ xem logs vì metrics và traces không chứa dữ liệu cá nhân.
D. Chỉ xem dữ liệu được lưu trong database quan hệ.
Đáp án đúng: B

Câu 4. Data minimization trong thiết kế telemetry yêu cầu điều gì?
A. Chỉ ghi các thuộc tính cần thiết cho mục đích quan sát đã duyệt.
B. Ghi mọi header và payload để hỗ trợ debug mọi tình huống.
C. Giữ toàn bộ trace attributes rồi dựa vào quyền truy cập để hạn chế.
D. Thêm user identifier vào metric để phân tích chính xác hơn.
Đáp án đúng: A

Câu 5. Vì sao access logs và application logs cần được rà soát nội dung nhạy cảm?
A. Log chỉ lưu mã trạng thái nên không thể chứa thông tin nhạy cảm.
B. Log thường đã được mã hóa nên không cần phân loại nội dung.
C. Chỉ log ở môi trường production mới có thể chứa dữ liệu cá nhân.
D. Header, URL và message có thể chứa token hoặc dữ liệu cá nhân.
Đáp án đúng: D

Câu 6. Gắn `user_id` hoặc `session_id` làm label metrics có rủi ro nào?
A. Tạo nhiều series và đưa định danh vào metrics.
B. Làm Prometheus tự xóa các series cũ khi nhãn thay đổi.
C. Buộc exporter chuyển metric thành trace trước khi scrape.
D. Làm mọi giá trị Counter bị reset sau mỗi lần scrape.
Đáp án đúng: A

Câu 7. Khi trace span chứa query string hoặc baggage, cần đánh giá điều gì?
A. Chúng chỉ tồn tại trong JVM nguồn và không rời khỏi process.
B. Chúng luôn được Collector tự động xóa trước khi export.
C. Baggage và query string có thể lan truyền dữ liệu nhạy cảm.
D. Chúng không thể liên kết với một người dùng hoặc request.
Đáp án đúng: C

Câu 8. Vị trí phù hợp để redact dữ liệu nhạy cảm trước khi telemetry phân phối rộng là đâu?
A. Tại điểm thu thập hoặc pipeline sớm trước các exporter đích.
B. Chỉ tại dashboard cuối cùng sau khi mọi backend đã nhận dữ liệu.
C. Chỉ trong trình duyệt người vận hành khi mở trang truy vấn.
D. Sau khi hết retention để bản lưu trữ cũ tự biến mất.
Đáp án đúng: A

Câu 9. Pseudonymization khác anonymization ở điểm nào?
A. Pseudonymization luôn loại bỏ khả năng nhận diện trong mọi bối cảnh.
B. Pseudonymization vẫn liên kết lại được nhờ thông tin giữ riêng.
C. Anonymization chỉ thay ID bằng hash có khóa giữ nguyên ở cùng nơi.
D. Hai kỹ thuật đều bảo đảm dữ liệu không còn thuộc phạm vi bảo vệ.
Đáp án đúng: B

Câu 10. Khi đánh giá dữ liệu đã anonymize, cần kiểm tra rủi ro nào?
A. Chỉ việc tên trường có còn chứa chuỗi `user` hay không.
B. Chỉ việc dữ liệu được chuyển từ logs sang metrics hay chưa.
C. Đánh giá khả năng tái nhận diện khi kết hợp nguồn khác.
D. Chỉ việc dashboard có yêu cầu đăng nhập hay không.
Đáp án đúng: C

Câu 11. Trước khi thu thập telemetry có dữ liệu cá nhân, tổ chức nên làm gì?
A. Mặc định dựa trên consent cho mọi loại telemetry nội bộ.
B. Xác định mục đích và căn cứ xử lý phù hợp bối cảnh áp dụng.
C. Thu thập trước rồi quyết định căn cứ sau khi có dữ liệu.
D. Coi việc vận hành hệ thống luôn miễn mọi nghĩa vụ xử lý.
Đáp án đúng: B

Câu 12. Khi xác định vai trò controller và processor, yếu tố nào quan trọng?
A. Ai sở hữu máy chủ có dung lượng lưu telemetry lớn nhất.
B. Ai viết PromQL query và ai trực ca vận hành dashboard.
C. Dựa vào bên quyết định mục đích và bên xử lý theo chỉ dẫn.
D. Ai cấp tài khoản đăng nhập cho người dùng cuối của ứng dụng.
Đáp án đúng: C

Câu 13. Khi thuê nhà cung cấp lưu trữ telemetry, hợp đồng cần làm rõ điều gì?
A. Chỉ mức băng thông, dung lượng và thời gian uptime cam kết.
B. Làm rõ phạm vi, bảo mật, quyền dữ liệu và xóa dữ liệu.
C. Chỉ phiên bản API và lịch bảo trì của nền tảng lưu trữ.
D. Chỉ quyền truy cập dashboard của nhóm vận hành nội bộ.
Đáp án đúng: B

Câu 14. Data flow map cho telemetry nên thể hiện thành phần nào?
A. Chỉ các service có endpoint HTTP và cổng đang mở.
B. Thể hiện nguồn, pipeline, backend, người nhận và vùng lưu.
C. Chỉ tên metric, dashboard và số lần alert được kích hoạt.
D. Chỉ tài khoản có quyền admin trên cụm Kubernetes.
Đáp án đúng: B

Câu 15. Khi telemetry đi qua biên giới quốc gia, bước đánh giá nào cần thực hiện?
A. Xác định nơi dữ liệu đi qua và áp dụng yêu cầu chuyển giao liên quan.
B. Giả định mã hóa TLS tự động đáp ứng mọi yêu cầu chuyển dữ liệu.
C. Chỉ kiểm tra quốc gia đặt dashboard mà bỏ qua nơi lưu trữ.
D. Đổi tên trường dữ liệu để không cần xem xét luồng chuyển giao.
Đáp án đúng: A

Câu 16. Data residency khác cross-border transfer ở điểm nào?
A. Residency nói nơi người dùng đăng nhập; transfer nói vị trí dashboard.
B. Residency là nơi lưu; transfer là luồng qua biên giới.
C. Residency chỉ áp dụng logs; transfer chỉ áp dụng metrics.
D. Hai khái niệm luôn đồng nghĩa khi dùng dịch vụ cloud.
Đáp án đúng: B

Câu 17. Retention schedule cho logs, metrics và traces nên dựa trên yếu tố nào?
A. Mục đích, nghĩa vụ áp dụng, nhu cầu vận hành và rủi ro lưu giữ.
B. Một thời hạn chung dài nhất để mọi nhóm dễ cấu hình.
C. Dung lượng ổ đĩa còn trống tại thời điểm triển khai Collector.
D. Mặc định thời hạn của vendor mà không cần rà soát nội bộ.
Đáp án đúng: A

Câu 18. Legal hold ảnh hưởng quy trình xóa telemetry như thế nào?
A. Tạm giữ dữ liệu thuộc phạm vi hold theo phê duyệt và ghi nhận rõ.
B. Tự động xóa toàn bộ telemetry ngay khi có yêu cầu pháp lý.
C. Giữ vĩnh viễn mọi dữ liệu của mọi hệ thống không phân biệt phạm vi.
D. Bỏ qua lịch sử truy cập vì dữ liệu đã được khóa lưu giữ.
Đáp án đúng: A

Câu 19. Khi hết thời hạn lưu giữ, quy trình deletion có kiểm soát cần làm gì?
A. Chỉ ẩn dữ liệu khỏi dashboard nhưng giữ nguyên bản lưu trữ.
B. Đổi tên series hoặc index để người dùng không tìm thấy nữa.
C. Xóa hoặc làm mất khả năng truy cập theo chính sách và xác minh kết quả.
D. Chỉ xóa bản production và bỏ qua bản sao downstream.
Đáp án đúng: C

Câu 20. Vì sao backup telemetry cần có chính sách retention và deletion riêng?
A. Backup chỉ lưu cấu hình nên không thể chứa telemetry đã thu thập.
B. Bản sao lưu có thể tiếp tục chứa dữ liệu sau khi kho chính đã xóa.
C. Xóa dữ liệu trong TSDB luôn tự xóa mọi bản backup ngoại tuyến.
D. Backup được mã hóa nên không cần kiểm soát vòng đời dữ liệu.
Đáp án đúng: B

Câu 21. Để đáp ứng yêu cầu truy cập dữ liệu cá nhân trong telemetry, tổ chức cần gì?
A. Một dashboard tổng hợp không có filter theo định danh hoặc thời gian.
B. Chỉ quyền đọc Prometheus vì mọi dữ liệu khác đều phi cá nhân.
C. Khả năng tìm kiếm theo định danh đã kiểm soát trên các kho liên quan.
D. Một bản export toàn bộ logs không cần xác minh người yêu cầu.
Đáp án đúng: C

Câu 22. RBAC và least privilege trong nền tảng telemetry nhằm bảo đảm điều gì?
A. Mọi kỹ sư có quyền admin để giảm thời gian xử lý sự cố.
B. Quyền đọc và quyền xóa được gộp để đơn giản hóa vận hành.
C. Quyền truy cập được cấp theo tên host thay vì danh tính người dùng.
D. Mỗi vai trò chỉ truy cập dữ liệu và thao tác cần cho nhiệm vụ.
Đáp án đúng: D

Câu 23. Tài khoản break-glass nên được quản lý theo cách nào?
A. Dùng làm tài khoản thường trực để tránh chờ phê duyệt.
B. Chia sẻ mật khẩu giữa các nhóm và đổi khi có người nghỉ việc.
C. Cấp quyền khẩn cấp có thời hạn, lý do và audit sau sử dụng.
D. Tắt audit để thao tác khẩn cấp không bị gián đoạn.
Đáp án đúng: C

Câu 24. Separation of duties trong quản trị telemetry có lợi ích gì?
A. Cho phép một quản trị viên tự yêu cầu và tự duyệt mọi thay đổi.
B. Chuyển trách nhiệm kiểm soát truy cập sang nhà cung cấp cloud.
C. Tách người yêu cầu, phê duyệt và thực hiện thao tác nhạy cảm.
D. Đảm bảo mọi thay đổi retention được triển khai không cần review.
Đáp án đúng: C

Câu 25. Mã hóa in transit cho telemetry nên được áp dụng ở đâu?
A. Chỉ ở giao diện web người dùng xem dashboard.
B. Chỉ trên ổ đĩa nơi Prometheus lưu TSDB block.
C. Chỉ trên backup sau khi dữ liệu đã được truyền đi.
D. Dùng TLS trên các kết nối truyền telemetry.
Đáp án đúng: D

Câu 26. Mã hóa at rest cần đi kèm biện pháp quản lý nào?
A. Quản lý khóa, phân quyền sử dụng và vòng đời xoay khóa.
B. Đặt khóa mã hóa trong cùng file cấu hình công khai của agent.
C. Dùng một khóa chung không đổi cho mọi môi trường và vendor.
D. Chỉ mã hóa tên file, giữ payload telemetry ở dạng rõ.
Đáp án đúng: A

Câu 27. Vì sao nên tách quyền quản lý encryption key khỏi quyền đọc telemetry?
A. Để mọi kỹ sư có thể tự khôi phục khóa khi quên mật khẩu.
B. Để bỏ yêu cầu audit đối với các thao tác đọc telemetry.
C. Để tăng cardinality của metric theo từng key đang sử dụng.
D. Tách quyền đọc dữ liệu khỏi quyền quản lý khóa.
Đáp án đúng: D

Câu 28. Audit log cho thao tác quản trị telemetry nên ghi những gì?
A. Toàn bộ payload logs và traces của người dùng được quản trị.
B. Actor, hành động, đối tượng, thời điểm và kết quả thao tác.
C. Chỉ địa chỉ IP của máy chủ lưu trữ và dung lượng còn lại.
D. Chỉ tên dashboard đã mở trong phiên làm việc.
Đáp án đúng: B

Câu 29. Bằng chứng kiểm toán về cấu hình retention nên gồm những gì?
A. Ảnh chụp dashboard hiện tại không kèm thời gian hoặc phiên bản.
B. Một email xác nhận miệng không gắn với thay đổi cụ thể.
C. Chỉ giá trị retention đang chạy mà không lưu lịch sử thay đổi.
D. Phiên bản policy, phê duyệt, cấu hình triển khai và kết quả kiểm tra.
Đáp án đúng: D

Câu 30. Để chứng minh evidence không bị thay đổi sau khi thu thập, có thể làm gì?
A. Tạo checksum, kiểm soát truy cập và lưu lịch sử bàn giao.
B. Đặt tên file có chữ `final` rồi gửi qua chat nhóm.
C. Nén file bằng ZIP mà không kiểm tra tính toàn vẹn sau đó.
D. Lưu bằng chứng trong thư mục chia sẻ có quyền sửa cho mọi người.
Đáp án đúng: A

Câu 31. Một ma trận nghĩa vụ telemetry hữu ích nên liên kết những yếu tố nào?
A. Nối yêu cầu, dữ liệu, kiểm soát, owner và bằng chứng.
B. Tên vendor, màu dashboard, số panel và tần suất refresh.
C. Địa chỉ IP, hostname, cổng mạng và phiên bản JVM.
D. Tên nhóm, lịch trực, số lượng Pod và dung lượng RAM.
Đáp án đúng: A

Câu 32. Collector pipeline có thể hỗ trợ governance bằng cách nào?
A. Tự xác định căn cứ pháp lý cho mọi trường dữ liệu thu thập.
B. Tự phê duyệt yêu cầu truy cập của chủ thể dữ liệu.
C. Tự xóa mọi bản backup của backend bên ngoài.
D. Lọc, redact và phân tuyến trước khi export.
Đáp án đúng: D

Câu 33. Khi dùng sampling để giảm lượng traces, điều gì vẫn phải được bảo đảm?
A. Sampling tự động làm mọi trace còn lại trở thành anonymized.
B. Sampling không cho phép giữ dữ liệu ngoài mục đích.
C. Chỉ cần giảm tỷ lệ sample là không cần retention policy.
D. Trace không được sample không thể tồn tại trong log khác.
Đáp án đúng: B

Câu 34. Policy-as-code cho telemetry governance đem lại lợi ích nào?
A. Thay thế hoàn toàn việc rà soát pháp lý và phê duyệt của con người.
B. Cho phép exporter tự mở rộng quyền truy cập khi bị lỗi.
C. Đảm bảo mọi yêu cầu tuân thủ giống nhau ở mọi quốc gia.
D. Kiểm tra quy tắc nhất quán ngay trong pipeline triển khai.
Đáp án đúng: D

Câu 35. Rà soát quyền truy cập định kỳ nên tập trung vào việc gì?
A. Tăng quyền admin cho tài khoản hoạt động thường xuyên.
B. Xóa tài khoản ít đăng nhập mà không hỏi chủ sở hữu.
C. Xác nhận quyền còn cần thiết và thu hồi quyền dư thừa.
D. Chỉ kiểm tra quyền của nhân viên mới trong tháng đầu.
Đáp án đúng: C

Câu 36. Vì sao dữ liệu telemetry ở môi trường dev/test nên được làm sạch hoặc tổng hợp?
A. Để giữ nguyên mọi payload production cho việc tái hiện lỗi chính xác.
B. Để các môi trường dùng chung một tài khoản truy cập backend.
C. Tránh đưa dữ liệu production nhạy cảm sang môi trường thử.
D. Để bỏ qua kiểm tra phân loại dữ liệu trong pipeline thử nghiệm.
Đáp án đúng: C

Câu 37. Khi phát hiện telemetry nhạy cảm bị gửi nhầm tới vendor, bước đầu phù hợp là gì?
A. Xóa audit log ngay để tránh dữ liệu nhạy cảm bị xem lại.
B. Tiếp tục gửi dữ liệu cho đến khi có báo cáo kiểm toán cuối cùng.
C. Chỉ đổi tên dashboard để người dùng không thấy dữ liệu đó.
D. Khoanh vùng luồng, hạn chế truy cập và giữ bằng chứng.
Đáp án đúng: D

Câu 38. Đánh giá một sự cố lộ telemetry cần xác định những yếu tố nào?
A. Xác định dữ liệu, phạm vi, người nhận và nghĩa vụ.
B. Chỉ số lượng dashboard bị ảnh hưởng và thời gian tải trang.
C. Chỉ số lượng Pod đã restart trong khoảng thời gian xảy ra sự cố.
D. Chỉ phiên bản exporter và số lần scrape thất bại.
Đáp án đúng: A

Câu 39. Khi sử dụng subprocessor mới cho telemetry, việc kiểm soát nào cần cập nhật?
A. Chỉ dashboard của nhóm vận hành và tên datasource Grafana.
B. Chỉ địa chỉ endpoint mới trong file cấu hình scrape.
C. Cập nhật vendor, luồng dữ liệu, rủi ro và hợp đồng.
D. Chỉ tên metric prefix để phân biệt vendor cũ và mới.
Đáp án đúng: C

Câu 40. Vì sao yêu cầu tuân thủ cần được đánh giá theo bối cảnh và khu vực áp dụng?
A. Mọi tổ chức xử lý telemetry đều chịu cùng một bộ nghĩa vụ.
B. Chỉ nơi đặt máy chủ quyết định toàn bộ nghĩa vụ pháp lý.
C. Một chứng chỉ bảo mật của vendor tự động bao phủ mọi yêu cầu.
D. Phạm vi, vai trò, loại dữ liệu và quy định có thể khác nhau.
Đáp án đúng: D
