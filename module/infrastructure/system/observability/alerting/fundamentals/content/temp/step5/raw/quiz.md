1. Một nhóm muốn cảnh báo on-call ngay khi hệ thống ảnh hưởng khách hàng. Nguyên tắc chọn tín hiệu nào phù hợp nhất?
A. Ưu tiên mọi metric CPU tăng kể cả khi dịch vụ vẫn đáp ứng ổn.
B. Ưu tiên ảnh hưởng người dùng và hành động xử lý rõ ràng.
C. Ưu tiên mỗi lần triển khai thay đổi dù không xuất hiện sự cố.
D. Ưu tiên tăng số cảnh báo để bao phủ mọi phép đo có sẵn.
Đáp án đúng: B

2. Trong giám sát dịch vụ thanh toán, phát biểu nào mô tả đúng một SLI?
A. Tỷ lệ giao dịch thành công trong một cửa sổ đo.
B. Mục tiêu tỷ lệ thành công mà đội ngũ cam kết duy trì.
C. Quy trình liên lạc khi dịch vụ thanh toán bị gián đoạn.
D. Giới hạn số cảnh báo được phép gửi trong một ngày trực.
Đáp án đúng: A

3. Một dịch vụ có SLO availability 99,9% theo tháng. Cặp đo nào giúp tính SLI gần với mục tiêu?
A. CPU trung bình của Pod chia số Pod đang hoạt động.
B. Số alert đã resolve chia tổng alert từng xuất hiện.
C. Thời gian on-call có mặt chia tổng giờ trong tháng.
D. Tỷ lệ request thành công trên tổng request hợp lệ.
Đáp án đúng: D

4. Với SLO thành công 99,9%, ý nghĩa của error budget trong kỳ đánh giá là gì?
A. Tổng số lỗi sản phẩm mà nhóm được phép sửa trong kỳ.
B. Dung lượng dự phòng để chạy thêm các container giám sát.
C. Số cảnh báo được phép đóng mà chưa có người xác nhận.
D. Phần thất bại còn được phép trong kỳ SLO.
Đáp án đúng: D

5. Trong cảnh báo dựa trên SLO, burn rate thể hiện khái niệm nào?
A. Số lần chạy job giám sát trong một khoảng thời gian ngắn.
B. Số instance tự scale khi lưu lượng HTTP tăng theo ngày.
C. Mức tiêu hao error budget so với tốc độ cho phép.
D. Lượng CPU bị sử dụng bởi bộ thu thập metric mỗi phút.
Đáp án đúng: C

6. Hệ thống muốn bắt lỗi nghiêm trọng nhanh nhưng tránh báo động do spike rất ngắn. Cách đánh giá nào phù hợp?
A. Xem điểm đo tức thời rồi gửi pager ngay khi nó vượt ngưỡng.
B. Xem trung bình 30 ngày rồi bỏ qua mọi biến động ngắn hạn.
C. Kết hợp cửa sổ ngắn/dài để xác minh burn rate trước khi page.
D. Tăng ngưỡng đến mức gần như không bao giờ phát cảnh báo.
Đáp án đúng: C

7. CPU của một Pod tăng nhưng latency và lỗi vẫn ổn định. Quyết định cảnh báo nào hợp lý hơn?
A. Theo dõi CPU như tín hiệu chẩn đoán, page khi có ảnh hưởng.
B. Đánh thức trực ca ngay chỉ vì CPU từng vượt mức thông thường.
C. Tắt toàn bộ metric CPU để tránh làm dashboard rối mắt.
D. Đánh dấu outage dịch vụ dù request vẫn xử lý thành công.
Đáp án đúng: A

8. Bài test synthetic từ nhiều vùng không thể checkout dù metric host bình thường. Tín hiệu này có giá trị gì?
A. Phát hiện lỗi hành trình người dùng mà metric hạ tầng bỏ sót.
B. Chỉ phản ánh CPU máy chạy test nên không dùng làm cảnh báo.
C. Chứng minh mọi request ở production đều thất bại hoàn toàn.
D. Thay thế mọi phép đo giao dịch thực bằng một kết quả synthetic.
Đáp án đúng: A

9. Tải dịch vụ thay đổi mạnh theo giờ, ngưỡng QPS cố định liên tục báo giả. Nên cải tiến thế nào?
A. Giữ nguyên ngưỡng tĩnh và tăng số kênh thông báo dự phòng.
B. Đổi mức severity của mọi cảnh báo QPS thành cao nhất.
C. Bỏ metric request rate và chỉ báo khi máy chủ khởi động lại.
D. Dùng baseline theo giờ và xác nhận ảnh hưởng người dùng.
Đáp án đúng: D

10. Hàng đợi xử lý tăng nhanh và tuổi thông điệp lớn dần. Tín hiệu nào đáng cảnh báo hơn để đo backlog?
A. Đo tuổi phần tử cũ nhất và tốc độ xử lý hàng đợi.
B. Đếm tổng số worker từng được tạo ra trong Deployment.
C. Đo nhiệt độ máy chủ rồi suy ra tình trạng hàng đợi.
D. Đếm số namespace có chứa các job xử lý dữ liệu.
Đáp án đúng: A

11. Metric số lỗi HTTP là counter chỉ tăng. Để phát hiện lỗi gia tăng trong 5 phút, dùng gì?
A. So sánh trực tiếp giá trị counter tích lũy với số cố định.
B. Lấy tổng counter kể từ lúc khởi động và không xét reset.
C. Chỉ đọc nhãn instance thay cho số lần phát sinh lỗi mới.
D. Dùng rate hoặc increase cho counter trong 5 phút.
Đáp án đúng: D

12. Độ trễ trung bình vẫn thấp nhưng một nhóm request bị chậm nhiều. Nên theo dõi gì?
A. Theo dõi trung bình vì nó luôn thể hiện request chậm nhất.
B. Theo dõi CPU máy chủ thay cho latency của các request.
C. Theo dõi số replica mà bỏ qua thời gian phản hồi.
D. P95/P99 hoặc phân bố độ trễ phù hợp với SLO người dùng.
Đáp án đúng: D

13. Nguồn metric biến mất do exporter ngừng chạy, biểu thức lỗi trả về không có chuỗi dữ liệu. Cần xử lý ra sao?
A. Diễn giải không có mẫu là tỷ lệ lỗi bằng không chắc chắn.
B. Báo mất dữ liệu hoặc target down, tách khỏi lỗi request.
C. Tự thay số liệu vắng bằng thành công rồi kết luận hệ khỏe.
D. Bỏ qua exporter vì Alertmanager vẫn còn kết nối mạng.
Đáp án đúng: B

14. Một rule có điều kiện vượt ngưỡng liên tục và for: 5m. Khi nào alert chuyển sang firing?
A. Ngay khi một sample vượt ngưỡng, không phụ thuộc thời gian.
B. Sau khi alert đã resolved được năm phút liên tiếp.
C. Đợi điều kiện liên tục đúng đủ 5 phút khi rule được đánh giá.
D. Chỉ sau khi Alertmanager gửi lại notification lần thứ hai.
Đáp án đúng: C

15. Cảnh báo thường bật tắt quanh một ngưỡng do nhiễu đo. Cách giảm flapping nào hợp lý?
A. Dùng thời gian duy trì, ngưỡng trễ hoặc hysteresis có kiểm thử.
B. Giảm chu kỳ đánh giá về nhỏ nhất rồi page mỗi lần đổi trạng thái.
C. Giữ ngưỡng nhưng nhân đôi số lần thông báo cho từng sự kiện.
D. Tắt hoàn toàn điều kiện giải quyết alert khi metric trở lại tốt.
Đáp án đúng: A

16. Một metric gắn request_id làm label cho từng request. Vì sao cấu hình này không tốt?
A. Mọi request bị gộp thành cùng một series và mất khả năng đếm.
B. Số label giảm dần theo thời gian nên khó định tuyến alert.
C. Cardinality rất cao, tăng chi phí lưu trữ và đánh giá rule.
D. Metric tự chuyển thành log và không thể hiển thị trên dashboard.
Đáp án đúng: C

17. Dịch vụ đang ngừng nhận giao dịch, khách hàng không thanh toán được. Severity nào phù hợp nếu phải hành động ngay?
A. Gửi bản tin hàng tuần do có thể khắc phục vào giờ hành chính.
B. Đặt mức info vì biểu đồ chưa biết chính xác nguyên nhân.
C. Chỉ ghi log vào dashboard mà không có người nhận nhiệm vụ.
D. Page mức critical tới người trực có khả năng xử lý sự cố.
Đáp án đúng: D

18. Dung lượng đĩa còn đủ nhiều nhưng dự báo sẽ đầy sau ba tuần. Cách thông báo nào thường hợp lý?
A. Tạo ticket hoặc cảnh báo warning để lên kế hoạch mở rộng.
B. Page tất cả kỹ sư ngay trong đêm dù chưa có ảnh hưởng.
C. Dừng gửi thông báo vì chưa chạm 100% dung lượng.
D. Đánh dấu mọi dịch vụ liên quan là đang outage nghiêm trọng.
Đáp án đúng: A

19. Một cảnh báo liên tục page nhưng không có triệu chứng người dùng và không yêu cầu hành động. Đây là dấu hiệu gì?
A. Cảnh báo tốt vì luôn giữ đội on-call trong trạng thái chú ý.
B. Cảnh báo nghiêm trọng vì số lần page là thước đo độ tin cậy.
C. Cảnh báo nhiễu cần xem lại ngưỡng, mục tiêu và kênh gửi.
D. Cảnh báo đã resolved vì không có tác động tới người dùng.
Đáp án đúng: C

20. Hệ thống checkout thực sự lỗi nhưng không rule nào kích hoạt. Đây là vấn đề gì của alerting?
A. False positive, vì có cảnh báo dù dịch vụ vẫn bình thường.
B. Cảnh báo bị grouped nên chắc chắn không có lỗi monitoring.
C. Cảnh báo bị acknowledged và tự giải quyết lỗi ở backend.
D. False negative: cần bổ sung tín hiệu phát hiện lỗi checkout.
Đáp án đúng: D

21. Một alert cần tự động đến đúng đội. Label nào có ích nhất cho routing và ownership?
A. Request ID ngẫu nhiên được sinh khác nhau ở mỗi lần gọi.
B. Service, environment và owner/team được chuẩn hóa ổn định.
C. Timestamp của từng sample metric chính xác tới mili giây.
D. Địa chỉ IP client truy cập mỗi request với thời gian lưu ngắn.
Đáp án đúng: B

22. On-call mở alert mà không biết cần xác minh hay khắc phục điều gì. Nên thêm gì?
A. Danh sách toàn bộ metric hệ thống dù không liên quan đến alert.
B. Runbook gồm bước triage, dashboard, hành động và escalation.
C. URL trang chủ công ty và lịch nghỉ lễ của mọi nhóm kỹ thuật.
D. Bản sao file cấu hình mà không có hướng dẫn xử lý sự cố.
Đáp án đúng: B

23. Pager gửi cảnh báo nhưng người trực đầu tiên không xác nhận sau thời hạn SLA. Cơ chế nào cần có?
A. Tăng số lần page người đầu tiên nhưng không giới hạn thời gian.
B. Tự đánh dấu alert đã resolved để tránh làm phiền thêm.
C. Tắt receiver của nhóm trực cho đến ca làm việc tiếp theo.
D. Escalation chuyển tới người hoặc nhóm trực kế tiếp theo lịch.
Đáp án đúng: D

24. Hai sự cố cùng tăng error rate: một ảnh hưởng toàn vùng, một ảnh hưởng 1% request thử nghiệm. Xếp mức ưu tiên theo gì?
A. Dựa vào CPU host có nhiều core hơn trong hai sự cố.
B. Đo phạm vi người dùng bị ảnh hưởng cùng độ nghiêm trọng.
C. Dựa vào thứ tự alert được tạo ở hệ thống cảnh báo.
D. Dựa vào tên ứng dụng đứng trước theo thứ tự ABC.
Đáp án đúng: B

25. Một cụm có 50 Pod cùng báo HTTP 5xx, on-call nhận 50 thông báo giống nhau. Tổ chức alert thế nào?
A. Group theo request_id để tạo riêng một nhóm cho mỗi request.
B. Group theo pod_uid để bảo đảm mọi lần restart tạo một nhóm.
C. Group theo service và env để giảm thông báo trùng lặp.
D. Group theo timestamp của từng sample để giữ đủ thông báo.
Đáp án đúng: C

26. Hai rule tạo alert cùng bộ label xác định danh tính một alert. Hệ thống xử lý trùng lặp thế nào?
A. Luôn sinh hai incident riêng dù label và trạng thái trùng nhau.
B. Dedup theo danh tính alert để tránh gửi lặp cùng một sự kiện.
C. Gộp nội dung hai biểu thức thành một giá trị metric mới.
D. Chuyển cả hai sang resolved ngay vì cùng tên alert.
Đáp án đúng: B

27. Group mới vừa xuất hiện nhiều alert gần nhau. group_wait được dùng nhằm mục đích gì?
A. Đợi giữa các lần lặp của cùng notification đã gửi.
B. Đợi ngắn trước notification đầu để gom alert cùng nhóm.
C. Quy định thời gian im lặng của silence được tạo thủ công.
D. Chặn alert con khi một alert cha vẫn đang firing.
Đáp án đúng: B

28. Sau lần notification đầu, nhóm có thêm alert mới. group_interval thường quy định gì?
A. Khoảng trì hoãn trước lần notification đầu của nhóm mới.
B. Thời lượng một điều kiện metric phải đúng để alert firing.
C. Thời gian giữ silence sau khi cảnh báo đã resolved.
D. Khoảng chờ giữa cập nhật một group khi có alert mới.
Đáp án đúng: D

29. Một nhóm alert không đổi và vẫn firing, muốn nhắc lại sau chu kỳ định trước. Dùng tham số nào?
A. group_wait để giữ mọi lần nhắc lại đến đầu ca tiếp theo.
B. repeat_interval nhắc lại group vẫn firing chưa đổi.
C. for của rule để quyết định người nhận của từng thông báo.
D. group_by để đặt số phút chờ trước khi gửi lần thứ hai.
Đáp án đúng: B

30. Critical của production cần pager; warning của staging cần chat. Cấu hình nào phù hợp?
A. Routing theo severity và environment tới receiver tương ứng.
B. Dùng một receiver pager cho mọi namespace rồi dựa vào người đọc.
C. Chỉ group alert theo hostname rồi chọn người nhận ngẫu nhiên.
D. Tạo silence toàn bộ staging nên warning không thể đến chat.
Đáp án đúng: A

31. Một alert DatabaseDown critical đang firing; nhiều warning DatabaseLatency cùng database cũng firing. Khi nào nên inhibit warning?
A. Khi một silence bất kỳ được tạo cho toàn bộ environment.
B. Khi warning có thời gian tạo sớm hơn nguồn critical.
C. Khi metric database được scrape từ nhiều exporter khác nhau.
D. Khi critical cùng database/cluster vẫn đang firing.
Đáp án đúng: D

32. Bảo trì cụm DB đã lên lịch, muốn không gửi cảnh báo trong khung giờ xác định. Dùng gì?
A. Dùng inhibition nhưng không cần alert nguồn nào đang firing.
B. Xóa toàn bộ rule để tránh khôi phục khi bảo trì xong.
C. Tạo silence có matcher và thời gian bắt đầu/kết thúc rõ.
D. Đặt severity critical cho tất cả cảnh báo trong bảo trì.
Đáp án đúng: C

33. Điểm khác nhau chính giữa silence và inhibition trong Alertmanager là gì?
A. Silence chủ động theo thời hạn; inhibition phụ thuộc alert nguồn.
B. Silence phụ thuộc SLO; inhibition phụ thuộc ngày hết hạn của cert.
C. Silence thay đổi metric; inhibition đổi truy vấn dashboard.
D. Silence xử lý root cause; inhibition tự khởi động lại dịch vụ.
Đáp án đúng: A

34. Tạo silence severity=warning trên toàn công ty khi chỉ bảo trì một dịch vụ. Nguy cơ là gì?
A. Tăng số thông báo critical vì warning luôn biến thành critical.
B. Che cả warning không liên quan; cần matcher giới hạn phạm vi.
C. Tự đổi nhãn service của mọi alert đang firing thành warning.
D. Khiến Prometheus ngừng thu thập dữ liệu của các dịch vụ.
Đáp án đúng: B

35. Đội trực đã acknowledge một incident nhưng metric vẫn vi phạm SLO. Nhận định nào đúng?
A. Ack tự làm metric trở về ngưỡng bình thường trên toàn hệ.
B. Ack tương đương xóa rule nên alert sẽ không được đánh giá.
C. Ack nghĩa là đã nhận xử lý, không đồng nghĩa điều kiện hết lỗi.
D. Ack sẽ buộc mọi receiver gửi thông báo resolved tức thì.
Đáp án đúng: C

36. Một alert vừa hồi phục, đội xử lý cần biết sự cố đã kết thúc. Nên cấu hình gì?
A. Gửi resolved notification khi hệ thống/kênh có hỗ trợ.
B. Gửi repeat notification của alert firing và bỏ trạng thái resolved.
C. Giữ silence vô thời hạn sau mỗi lần khôi phục thành công.
D. Đổi severity alert từ warning thành info để giả lập resolved.
Đáp án đúng: A

37. DB primary hỏng làm hàng trăm dịch vụ báo timeout. Cách giảm bão thông báo hợp lý?
A. Tăng mọi retry để dịch vụ khỏi tạo metric báo timeout mới.
B. Tắt toàn bộ alert HTTP của ứng dụng trong mọi tình huống.
C. Inhibit symptom khi root-cause alert cùng phạm vi đang firing.
D. Bỏ group labels để từng Pod phải gửi một notification riêng.
Đáp án đúng: C

38. Nhóm nhận hàng trăm notification không khẩn cấp ngoài giờ. Nên điều chỉnh cách gửi ra sao?
A. Chuyển mọi warning lên critical để on-call chú ý đồng đều.
B. Gửi cả resolved và firing vào mọi kênh để tăng sự bao phủ.
C. Thêm nhiều receiver pager cho tất cả alert có severity info.
D. Page sự cố cần xử lý ngay; còn lại gửi qua chat hoặc ticket.
Đáp án đúng: D

39. Bảo trì được lên lịch thường xuyên. Cách quản lý silence nào giảm rủi ro bỏ sót sự cố sau bảo trì?
A. Tạo silence không hết hạn để không phải cập nhật lịch.
B. Tắt alert rule trong source control mà không có rollback.
C. Đặt matcher hẹp, có hạn hết và rà soát thời điểm bỏ silence.
D. Silence toàn bộ cluster khi chỉ nâng cấp một service nhỏ.
Đáp án đúng: C

40. Muốn biết đường routing mới có gửi critical tới pager đúng không trước khi áp dụng rộng. Cách kiểm thử nào hữu ích?
A. Sửa production trực tiếp rồi đợi một sự cố thật xảy ra.
B. Dựa vào số lượng metric đang thu thập để kết luận routing.
C. Tạo silence cho toàn bộ route rồi xem notification có xuất hiện.
D. Tạo alert thử và kiểm tra receiver trong môi trường test.
Đáp án đúng: D

41. Trong unit test một alert rule có for: 10m, điều gì phải được xác minh?
A. Rule luôn firing ở lần đánh giá đầu không cần chờ mười phút.
B. Rule chỉ gửi notification sau khi Prometheus đã restart.
C. Rule pending trước mốc đủ điều kiện và firing khi đủ thời gian.
D. Rule sẽ đổi receiver nếu thời gian đánh giá dài hơn chu kỳ scrape.
Đáp án đúng: C

42. Khi thay đổi nhãn, route và ngưỡng cảnh báo qua Git, cách rollout nào an toàn?
A. Review, thử rule/route, triển khai có giám sát và rollback.
B. Push thẳng mọi rule vào production và bỏ theo dõi sau deploy.
C. Chỉ kiểm tra YAML parse được mà không chạy thử routing.
D. Tắt mọi cảnh báo sau mỗi thay đổi để tránh sai ngưỡng.
Đáp án đúng: A

43. Alert đang firing nhưng người trực không biết xem dữ liệu liên quan ở đâu. Nội dung nào nên có trong annotation?
A. Gắn request_id thay đổi từng giây làm nhãn routing chính.
B. Dùng tên ngẫu nhiên thay summary để tránh trùng tên alert.
C. Mô tả triệu chứng, impact, link dashboard và runbook phù hợp.
D. Chứa password để on-call truy cập ngay mà không cần quản lý bí mật.
Đáp án đúng: C

44. Bộ thu thập alert chết nhưng dịch vụ ứng dụng vẫn khỏe, làm sao phát hiện đường giám sát không còn sống?
A. Tắt tất cả exporter để xác nhận không có alert xuất hiện.
B. Thiết kế heartbeat/dead-man check với kênh theo dõi độc lập.
C. Dùng latency từ ứng dụng làm bằng chứng pipeline luôn hoạt động.
D. Chỉ mở rộng CPU máy Prometheus vì lỗi nào cũng do tải cao.
Đáp án đúng: B

45. Sau một quý, đội muốn đo chất lượng hệ thống alerting. Chỉ số nào nên đánh giá?
A. Theo dõi false page, ack time, alert hữu ích và outage bỏ sót.
B. Tổng số label ở mọi metric mà không xem có người xử lý không.
C. Số dashboard được tạo trong quý bất kể ảnh hưởng tới vận hành.
D. Số message trong chat mà không phân loại tín hiệu cảnh báo.
Đáp án đúng: A

46. Sau incident, một alert đến muộn còn runbook thiếu bước khôi phục. Cải tiến tiếp theo nào phù hợp?
A. Tăng số người trong mọi kênh mà không xem lại tín hiệu kích hoạt.
B. Dùng timeline sự cố để sửa ngưỡng, rule và runbook rồi test lại.
C. Xóa tất cả historical alert để dashboard không hiện lỗi cũ.
D. Giữ nguyên rule nếu incident đã khép lại và SLO chưa đổi.
Đáp án đúng: B

47. Dịch vụ ít traffic có một lỗi trong vài phút khiến tỷ lệ lỗi tăng vọt. Nên đánh giá alert theo cách nào?
A. Dựa vào tỷ lệ tại một điểm đo mà bỏ số lượng request.
B. Kết hợp tỷ lệ lỗi với số mẫu và cửa sổ phù hợp mức ảnh hưởng.
C. Đo CPU thay cho lỗi request khi lưu lượng đang rất thấp.
D. Bỏ mọi cảnh báo cho dịch vụ ít request trong toàn bộ kỳ SLO.
Đáp án đúng: B

48. Một alert không khớp nhánh routing chuyên biệt nào trong cây route. Điều gì cần được kiểm thử?
A. Receiver mặc định ở tuyến gốc sẽ nhận và xử lý alert đúng.
B. Alert luôn bị loại khỏi hệ thống vì không có route nhánh khớp.
C. Alert tự được chuyển tới tất cả receiver đã cấu hình trong hệ.
D. Prometheus tự viết lại nhãn severity để khớp một route khác.
Đáp án đúng: A
