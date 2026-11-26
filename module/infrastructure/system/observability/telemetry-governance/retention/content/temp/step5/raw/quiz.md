1. Chính sách retention cho telemetry nên dựa trên nhóm tiêu chí nào?
A. Mục đích, độ nhạy, nghĩa vụ và chi phí.
B. Dung lượng và công cụ lưu trữ hiện có.
C. Số dashboard và người dùng truy cập.
D. Giữ lâu nhất để tránh mất dữ liệu.
Đáp án đúng: A

2. Retention khác backup ở điểm cốt lõi nào?
A. Backup tạo bản sao; retention xóa dữ liệu khi hết hạn.
B. Hai thuật ngữ cùng mô tả thời hạn lưu trữ dữ liệu.
C. Retention giới hạn thời gian; backup phục vụ khôi phục.
D. Backup giữ dữ liệu thô, retention chỉ giữ số liệu tổng hợp.
Đáp án đúng: C

3. Một loại log chứa dữ liệu cá nhân chỉ cần phục vụ điều tra trong 30 ngày. Lựa chọn nào phù hợp?
A. Giữ 12 tháng để thuận tiện điều tra.
B. Giữ vô thời hạn cho sự cố hiếm gặp.
C. Xóa khi kho đạt ngưỡng dung lượng.
D. Đặt giới hạn 30 ngày theo nhu cầu và nghĩa vụ.
Đáp án đúng: D

4. Để ước tính chi phí lưu trữ telemetry, yếu tố nào cần tính đến?
A. Ingest rate, thời hạn, nén, bản sao và truy vấn.
B. Số dashboard cùng số người đăng nhập mỗi ngày.
C. Kích thước một file mẫu tại thời điểm triển khai.
D. Số alert firing và thời gian on-call phản hồi.
Đáp án đúng: A

5. Phân tầng hot, warm và cold storage thường nhằm mục đích gì?
A. Cân bằng tốc độ truy vấn, chi phí và mức truy cập.
B. Tách metrics, logs và traces thành ba giao thức riêng.
C. Tăng độ chính xác timestamp bằng cách đổi vùng lưu trữ.
D. Áp dụng cùng tốc độ truy vấn cho mọi dữ liệu.
Đáp án đúng: A

6. Một hệ thống cần dữ liệu chi tiết 7 ngày và xu hướng dài hạn 13 tháng. Cách thiết kế nào hợp lý?
A. Giữ raw 13 tháng để không cần tổng hợp.
B. Giữ raw ngắn hạn, dữ liệu tổng hợp dài hạn.
C. Chỉ giữ dữ liệu thô 7 ngày rồi xóa mọi xu hướng.
D. Tăng scrape interval sau khi dữ liệu đã được lưu.
Đáp án đúng: B

7. Khi có legal hold hợp lệ cho một tập log cụ thể, hệ thống nên làm gì?
A. Xóa theo lịch đã cấu hình trước.
B. Dừng xóa toàn bộ tenant dù hold chỉ cục bộ.
C. Tạm dừng xóa trong phạm vi hold đã duyệt.
D. Chuyển cold tier rồi coi dữ liệu đã xóa.
Đáp án đúng: C

8. Làm thế nào kiểm chứng một chính sách xóa telemetry thực sự hoạt động?
A. Thử dữ liệu hết hạn, truy vấn và dấu vết xóa.
B. Chỉ xem cấu hình retention có chứa số ngày mong muốn.
C. Kiểm tra dashboard không còn hiển thị panel cũ.
D. Xác nhận collector đã ngừng gửi dữ liệu mới.
Đáp án đúng: A

9. Một dataset có thời hạn lưu giữ theo quy định ngắn hơn mặc định nền tảng. Nên áp dụng thế nào?
A. Giữ mặc định nền tảng vì một cấu hình chung dễ vận hành.
B. Gia hạn dataset đến khi hết thời gian backup.
C. Áp quy tắc cụ thể trong giới hạn quản trị chung.
D. Xóa dataset ngay khi có bất kỳ thay đổi chính sách nào.
Đáp án đúng: C

10. Prometheus local TSDB thường giới hạn retention theo cách nào?
A. Đặt TTL riêng trên từng label của mỗi time series.
B. Dùng scrape interval làm thời hạn xóa block cũ.
C. Cấu hình thời gian giữ riêng cho từng sample.
D. Giới hạn theo thời gian hoặc dung lượng lưu trữ.
Đáp án đúng: D

11. Nếu Prometheus cấu hình cả retention time và retention size, điều gì có thể xảy ra?
A. Retention size chỉ hoạt động khi time hết hạn.
B. Chỉ retention time chạy sau khi size vượt ngưỡng.
C. Xóa block cũ khi một trong hai giới hạn chạm ngưỡng.
D. Hai giới hạn được cộng lại thành thời hạn dài hơn.
Đáp án đúng: C

12. WAL của Prometheus chủ yếu phục vụ mục đích nào?
A. Lưu trữ dài hạn thay thế hoàn toàn các TSDB block.
B. Làm bản backup độc lập có thể khôi phục mọi block đã xóa.
C. Áp thời hạn retention riêng cho từng metric name.
D. WAL ghi mẫu mới và hỗ trợ phục hồi sau khi tiến trình khởi động lại.
Đáp án đúng: D

13. Khi Prometheus gửi samples qua remote_write, retention tại remote backend được quản lý ra sao?
A. Tự động kế thừa retention của local Prometheus TSDB.
B. Remote backend cần retention riêng, độc lập với local TSDB.
C. Dựa vào thời hạn giữ WAL trên máy gửi dữ liệu.
D. Không cần retention vì remote_write chỉ gửi dữ liệu mới.
Đáp án đúng: B

14. Cardinality của metrics tăng mạnh thường tác động thế nào tới lưu trữ?
A. Giảm kích thước block vì mỗi label tạo thêm khả năng nén.
B. Tăng số series, index, memory và disk.
C. Chỉ ảnh hưởng dashboard, không làm đổi dung lượng TSDB.
D. Tự rút ngắn retention time để giữ nguyên chi phí.
Đáp án đúng: B

15. Trong Loki, thành phần nào thực thi quá trình retention cho log đã lưu?
A. Compactor thực thi retention trên backend log.
B. Distributor tự xóa từng dòng ngay khi nhận log mới.
C. Query frontend xóa chunk sau khi người dùng xem xong.
D. Promtail agent xóa dữ liệu cũ trong object storage.
Đáp án đúng: A

16. Muốn đặt thời hạn khác nhau cho một nhóm log trong Loki, cách tiếp cận nào phù hợp?
A. Tạo một tenant mới cho từng giá trị log level.
B. Dùng selector cho stream và default toàn cục.
C. Đặt thời gian lưu trong nội dung message của mỗi dòng.
D. Dùng query range để thay đổi thời hạn dữ liệu đã lưu.
Đáp án đúng: B

17. Loki có retention period nhưng compactor retention chưa được bật hoặc cấu hình đầy đủ. Rủi ro nào xảy ra?
A. Log có thể không được xóa theo thời hạn mong muốn.
B. Mọi log mới sẽ bị từ chối ngay tại distributor.
C. Label của stream tự chuyển thành dữ liệu đã mã hóa.
D. Query API sẽ tự xóa dữ liệu khi trả kết quả.
Đáp án đúng: A

18. Một yêu cầu xóa log theo tenant đang chờ xử lý trong Loki. Cách kiểm soát nào hữu ích?
A. Chỉ xóa dashboard có query trỏ tới tenant đó.
B. Xóa credential ingest để buộc backend xóa các chunk cũ.
C. Theo dõi delete request và trạng thái compactor.
D. Đổi tên tenant để mọi truy vấn cũ không còn khớp.
Đáp án đúng: C

19. Tempo lưu trace blocks trong object storage. Thiết lập retention ở đâu là phù hợp?
A. Đặt TTL trong traceparent header do client gửi tới gateway.
B. Dùng thời gian span duration làm thời hạn lưu trace block.
C. Cấu hình ở compactor, đồng bộ object lifecycle.
D. Đặt retention tại Grafana dashboard đang hiển thị trace.
Đáp án đúng: C

20. Khi cấu hình Tempo compactor retention, đối tượng dữ liệu nào được quản lý?
A. Trace blocks trong backend theo chính sách compaction.
B. Mỗi span riêng lẻ trong bộ nhớ của ứng dụng gửi trace.
C. Các log dòng được Loki lưu trong cùng bucket.
D. Metrics sample được Prometheus remote_write gửi tới Tempo.
Đáp án đúng: A

21. Object storage có lifecycle rule xóa object sớm hơn Tempo retention. Hậu quả nào có thể xảy ra?
A. Tempo tự tái tạo mọi block từ traceparent của request.
B. Object có thể mất trước hạn retention do Tempo đặt.
C. Compactor tự gia hạn object khi nhận truy vấn mới.
D. Chỉ ảnh hưởng tên bucket, không ảnh hưởng truy vấn trace.
Đáp án đúng: B

22. Elasticsearch ILM thường dùng để tự động hóa công việc nào?
A. Tạo span cha/con và inject trace context vào HTTP.
B. Tổng hợp metric thành recording rule theo lịch.
C. Chuẩn hóa JSON log trước khi ingest vào cluster.
D. Rollover, chuyển tier và xóa index theo policy.
Đáp án đúng: D

23. Trong Elasticsearch ILM, hot, warm, cold và delete biểu thị điều gì?
A. Các giai đoạn vòng đời index với hành động lưu trữ.
B. Các log level tăng dần từ INFO đến FATAL.
C. Bốn tenant mặc định được tạo cho mỗi data stream.
D. Các bản sao snapshot cần được phục hồi theo thứ tự.
Đáp án đúng: A

24. Một index lớn cần rollover trước khi chuyển sang warm tier. Điều kiện nào thường dùng?
A. Số dashboard đang truy vấn và số người dùng trực tuyến.
B. Mức severity trung bình của các log trong index.
C. Số lần snapshot đã được tải về trong ngày.
D. Tuổi, dung lượng hoặc số document của index.
Đáp án đúng: D

25. Một ILM policy đặt min_age cho delete phase sau khi index rollover. Mốc tuổi thường được tính từ đâu?
A. Từ thời điểm document đầu tiên được truy vấn.
B. Từ lần gần nhất một người dùng mở dashboard.
C. Từ thời điểm rollover khi index đã rollover.
D. Từ lúc snapshot gần nhất hoàn tất thành công.
Đáp án đúng: C

26. Elasticsearch data stream dùng ILM. Policy thường gắn với thành phần nào?
A. Mỗi document riêng lẻ bằng trường message.
B. Client query để quyết định document nào được giữ.
C. Snapshot repository thay cho lifecycle policy.
D. Index template để policy áp dụng cho backing indices.
Đáp án đúng: D

27. Snapshot Elasticsearch có nghĩa là index nguồn đã hết retention và có thể xóa mọi bản sao?
A. Không; snapshot có vòng đời riêng với index nguồn.
B. Có; rollover sẽ xóa snapshot liên quan.
C. Có; snapshot chỉ lưu metadata của index.
D. Không; snapshot tự hết hạn theo ILM.
Đáp án đúng: A

28. Một tổ chức muốn chuyển log ít truy cập sang tier rẻ hơn trước khi xóa. Cách làm nào phù hợp?
A. Giảm log level của các document cũ trước khi lưu.
B. Chuyển index qua warm/cold trước delete.
C. Đổi tên index để backend tự chuyển sang tier chi phí thấp.
D. Tạo snapshot mới mỗi ngày và không bao giờ xóa index.
Đáp án đúng: B

29. Retention được cấu hình trên primary storage nhưng replica và cache vẫn giữ bản sao. Cần lưu ý gì?
A. Chỉ cần xóa primary vì mọi replica lập tức mất dữ liệu.
B. Kiểm tra xóa trên replica và cache liên quan.
C. Cache không thể chứa log hoặc trace đã bị xóa ở nguồn.
D. Replica tự có retention ngắn hơn primary theo mặc định.
Đáp án đúng: B

30. Một yêu cầu xóa dữ liệu cá nhân phải bao phủ các bản xuất và bản backup. Chính sách nên quy định gì?
A. Dashboard ẩn bản ghi nhưng không xóa dữ liệu nguồn.
B. Giữ bản backup vô thời hạn vì không truy cập trực tiếp.
C. Collector xóa dữ liệu mà không cần xét backend.
D. Quy định bản sao, hạn backup và quy trình xóa.
Đáp án đúng: D

31. Khi rút ngắn retention để giảm chi phí, chỉ số nào cần theo dõi?
A. Số lượng dashboard được tạo trong mỗi tuần.
B. Số màu được dùng trên biểu đồ log volume.
C. Số lần collector được restart trong tháng.
D. Điều tra, tuân thủ, chi phí và khả năng truy vấn.
Đáp án đúng: D

32. Thời điểm retention nên dựa trên event time hay ingest time?
A. Dựa ingest time vì event time không đáng tin cậy.
B. Chọn mốc rõ ràng, xử lý event đến trễ và lệch clock.
C. Event time đủ dùng, không cần timestamp collector.
D. Dùng thời gian truy vấn lần cuối để mọi dữ liệu được gia hạn.
Đáp án đúng: B

33. Một tenant có yêu cầu lưu traces ngắn hơn các tenant khác. Thiết kế nào phù hợp?
A. Tách tenant sang dashboard khác nhưng dùng cùng retention.
B. Yêu cầu tenant tự xóa trace bằng query API sau mỗi lần xem.
C. Tăng retention toàn hệ thống để giữ chính sách thống nhất.
D. Dùng tenant override có kiểm soát khi backend hỗ trợ.
Đáp án đúng: D

34. Ngoại lệ retention do điều tra sự cố được phê duyệt nên được quản lý thế nào?
A. Đặt thời hạn vô hạn để không phải gia hạn khi điều tra kéo dài.
B. Ghi phạm vi, lý do, người duyệt và thời hạn.
C. Tắt audit log của dữ liệu đang thuộc ngoại lệ.
D. Áp dụng ngoại lệ cho toàn bộ tenant để tránh cấu hình phức tạp.
Đáp án đúng: B

35. Sau khi thay đổi retention, cách rollout an toàn nào phù hợp?
A. Kiểm thử cấu hình, dữ liệu mẫu và kết quả xóa thực tế.
B. Triển khai đồng thời mọi nơi rồi đợi người dùng báo mất dữ liệu.
C. Xóa ngay toàn bộ block cũ trước khi kiểm tra chính sách.
D. Chỉ xác nhận dịch vụ khởi động thành công, bỏ kiểm tra dữ liệu.
Đáp án đúng: A

36. Prometheus đạt retention size trước retention time. Dữ liệu nào thường bị loại bỏ để giảm dung lượng?
A. Các series mới nhất có giá trị sample lớn nhất.
B. Mọi series có cardinality thấp trong lần compaction kế tiếp.
C. Khi retention size chạm ngưỡng, Prometheus loại bỏ TSDB block cũ nhất.
D. Các mẫu đang nằm trong WAL mà không xét block cũ.
Đáp án đúng: C

37. Khi legal hold được gỡ bỏ, xử lý nào phù hợp với dữ liệu liên quan?
A. Giữ toàn bộ dữ liệu vĩnh viễn vì từng có legal hold.
B. Xóa ngay mọi bản ghi mà không xét retention thông thường.
C. Đánh giá lại thời hạn còn lại và tiếp tục xóa theo policy.
D. Tắt chính sách retention để tránh xóa nhầm lần nữa.
Đáp án đúng: C
