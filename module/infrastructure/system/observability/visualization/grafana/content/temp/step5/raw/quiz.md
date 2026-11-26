1. Trong dashboard Grafana, vì sao nên tham chiếu datasource bằng UID ổn định?
A. UID tự động sao chép dữ liệu giữa các datasource cùng loại.
B. UID quyết định quyền truy cập của mọi user vào backend.
C. UID buộc mọi panel dùng chung một truy vấn và khoảng thời gian.
D. UID giữ tham chiếu khi tên datasource thay đổi.
Đáp án đúng: D

2. Với metric Prometheus dạng counter, cách nào phù hợp để hiển thị tốc độ request mỗi giây?
A. Dùng `avg_over_time(counter[5m])` để suy ra số request mỗi giây.
B. Dùng `count_over_time(counter[5m])` để đếm số lần scrape.
C. Dùng `rate(counter[5m])` để tính tốc độ tăng trong cửa sổ.
D. Dùng `delta(counter[5m])` để lấy tổng tích lũy từ lúc khởi động.
Đáp án đúng: C

3. Khi tính p95 từ Prometheus histogram, truy vấn cần giữ label nào qua bước tổng hợp bucket?
A. Giữ label `__name__` để phân biệt các bucket theo metric.
B. Giữ `le` để `histogram_quantile` tính quantile.
C. Giữ label `instance` để mỗi pod tạo một quantile riêng.
D. Giữ label `job` để hàm tự suy ra ranh giới bucket.
Đáp án đúng: B

4. Trong LogQL, cách nào thường giảm lượng log Loki phải quét trước khi lọc nội dung?
A. Chọn stream bằng selector hẹp trước line filter.
B. Chạy regex trên toàn bộ message rồi mới chọn namespace.
C. Dùng `unwrap` trước selector để Loki lập chỉ mục message.
D. Bỏ selector và tăng limit để Loki tự tìm stream phù hợp.
Đáp án đúng: A

5. Một panel Loki cần trích trường JSON `status` rồi chỉ hiển thị lỗi 5xx. Cách viết pipeline nào phù hợp?
A. Dùng label selector `status=500` dù status chỉ nằm trong JSON.
B. Dùng `rate()` trên message để phân loại mã HTTP.
C. Dùng `| unwrap status` trước khi parse JSON của message.
D. Dùng `| json` để trích field, sau đó lọc theo `status`.
Đáp án đúng: D

6. Muốn mở trace từ một dòng log Loki có chứa trace ID, cấu hình nào hỗ trợ liên kết này?
A. Thiết lập transformation Reduce để ghép log với trace theo thời gian.
B. Thiết lập dashboard variable chỉ lấy tên service từ log stream.
C. Thiết lập derived field trích trace ID và trỏ tới Tempo datasource.
D. Thiết lập annotation query để chuyển message thành span tự động.
Đáp án đúng: C

7. Exemplar trong biểu đồ Prometheus hữu ích nhất khi nào?
A. Khi cần thay thế toàn bộ histogram bằng một metric Gauge.
B. Dùng điểm metric để mở trace mẫu liên quan.
C. Khi cần lưu mọi log của request vào chính time series metric.
D. Khi cần gộp nhiều datasource thành một query duy nhất.
Đáp án đúng: B

8. Một biến Grafana cho phép chọn nhiều service và dùng trong PromQL. Matcher nào thường phù hợp?
A. Dùng matcher phủ định `!~` để kết hợp các service được chọn.
B. Dùng matcher regex `=~` với định dạng biến nhiều giá trị.
C. Dùng phép so sánh số `>=` trên nhãn service.
D. Dùng matcher bằng `=` vì Grafana tự tách từng service.
Đáp án đúng: B

9. Trong truy vấn Prometheus dùng `rate()`, biến tích hợp nào tự điều chỉnh cửa sổ theo khoảng thời gian và độ phân giải?
A. `$__rate_interval` để chọn cửa sổ rate phù hợp.
B. `$__dashboard` để lấy khoảng thời gian của panel cha.
C. `$__from` để lấy thời gian bắt đầu của từng scrape.
D. `$__to` để đặt số mẫu tối đa cho mỗi series.
Đáp án đúng: A

10. Khi cần lặp lại cùng một panel cho từng giá trị của biến `cluster`, nên dùng tính năng nào?
A. Transformation Reduce để nhân bản panel theo từng series.
B. Dashboard link để mở một trang mới cho từng cluster.
C. Annotation query để tạo panel từ các sự kiện deploy.
D. Panel repeat theo biến để tạo một panel cho mỗi giá trị.
Đáp án đúng: D

11. Hai query trả về bảng có trường `service` chung và cần ghép thành một bảng. Transformation nào phù hợp?
A. Reduce để cộng mọi trường có cùng tên giữa hai query.
B. Join by field theo khóa `service` giữa các frame.
C. Labels to fields để nối hai bảng theo thứ tự truy vấn.
D. Organize fields để tự ghép hàng theo nhãn service.
Đáp án đúng: B

12. Một panel Stat nhận nhiều time series và chỉ cần giá trị cuối của từng series. Transformation nào phù hợp?
A. Reduce dùng Last để lấy giá trị cuối mỗi series.
B. Series to rows để giữ toàn bộ mẫu trong từng series.
C. Outer join để nối các mẫu thời gian thành một cột cuối.
D. Filter data by values để giữ mọi mẫu có timestamp mới nhất.
Đáp án đúng: A

13. Khi ghép dữ liệu từ hai query có tập service không trùng hoàn toàn, phép join nào giữ cả các hàng không khớp?
A. Inner join để giữ mọi hàng có ít nhất một trường bất kỳ.
B. Outer join để giữ hàng từ cả hai phía dù thiếu đối tác.
C. Concatenate fields để loại các hàng không có khóa chung.
D. Reduce row để thay các hàng không khớp bằng giá trị trung bình.
Đáp án đúng: B

14. Panel nhận latency milliseconds và cần hiển thị đúng đơn vị. Cần làm gì?
A. Đặt min interval bằng một giây để Grafana tự đổi đơn vị.
B. Dùng threshold để chia mọi giá trị cho một nghìn khi hiển thị.
C. Đổi tên legend thành seconds mà không thay đổi unit của panel.
D. Đặt unit milliseconds hoặc đổi dữ liệu sang seconds.
Đáp án đúng: D

15. Data link trên một panel cần truyền giá trị của field đang được chọn sang URL đích. Nên dùng gì?
A. Biến liên kết của Grafana để chèn giá trị field hoặc series.
B. Annotation query để biến điểm đang chọn thành tham số URL.
C. Datasource UID để Grafana tự suy ra giá trị đang được chọn.
D. Panel repeat để truyền toàn bộ dữ liệu frame vào URL.
Đáp án đúng: A

16. Dashboard cần đánh dấu thời điểm deploy để đối chiếu với latency tăng. Thành phần nào phù hợp?
A. Threshold để lưu lịch sử deploy thành đường ngang cố định.
B. Transformation để đổi timestamp metric thành tên phiên bản.
C. Annotation để hiển thị mốc deploy trên trục thời gian.
D. Variable để chèn commit SHA vào mọi điểm dữ liệu.
Đáp án đúng: C

17. Khi điều tra một sự cố chưa có dashboard phù hợp, Grafana Explore hữu ích ở điểm nào?
A. Thay thế datasource bằng dữ liệu mẫu để tránh tải backend.
B. Cho phép chạy và tinh chỉnh query trực tiếp trên datasource.
C. Tự động sửa mọi query lỗi trước khi gửi tới datasource.
D. Tự động tạo dashboard production và provision file JSON.
Đáp án đúng: B

18. Panel trả dữ liệu khác với kỳ vọng. Công cụ nào giúp xem query thực gửi, request và response?
A. Playlist settings để xem thứ tự refresh các dashboard.
B. Dashboard version history để xem lịch sử sửa JSON.
C. Folder permissions để kiểm tra quyền của người tạo panel.
D. Query Inspector để kiểm tra truy vấn và phản hồi datasource.
Đáp án đúng: D

19. Dashboard được dùng bởi nhóm ở nhiều múi giờ. Cách nào giúp thống nhất cách diễn giải thời điểm?
A. Chọn timezone dashboard hoặc browser theo quy ước của nhóm.
B. Đổi timestamp trong từng query bằng offset cố định cho mọi người.
C. Đặt refresh interval bằng UTC để Grafana đổi múi giờ tự động.
D. Dùng annotation để thay thế timezone của datasource.
Đáp án đúng: A

20. Một panel truy vấn 30 ngày nhưng cần giới hạn số điểm trả về theo kích thước hiển thị. Thiết lập nào có tác động trực tiếp?
A. Max data points để giới hạn số điểm theo độ phân giải panel.
B. Dashboard UID để giới hạn số timestamp trong query.
C. Panel description để đặt bước lấy mẫu cho datasource.
D. Legend placement để giảm số mẫu Prometheus trả về.
Đáp án đúng: A

21. Dashboard có nhiều panel và tự refresh mỗi giây dù không có người theo dõi liên tục. Cách nào giảm tải truy vấn?
A. Đặt unit chung để Grafana cache mọi truy vấn khác nhau.
B. Giảm refresh interval để mỗi query xử lý ít dữ liệu hơn.
C. Tăng refresh interval và tối ưu query theo nhu cầu quan sát.
D. Bật repeat panel cho mọi biến để chia tải giữa các panel.
Đáp án đúng: C

22. Biến `namespace` cần lọc danh sách theo lựa chọn `cluster`. Cách nào phù hợp?
A. Dùng query biến namespace tham chiếu `$cluster` để lọc danh sách.
B. Tắt refresh của biến namespace để giữ lựa chọn người dùng.
C. Dùng biến All cố định để namespace không phụ thuộc cluster.
D. Chuyển namespace thành annotation để tự cập nhật theo thời gian.
Đáp án đúng: A

23. Một dashboard cần query Prometheus và Loki trong cùng một panel. Cách nào phù hợp?
A. Dùng một query PromQL để đọc trực tiếp cả log stream Loki.
B. Tạo hai panel tách biệt vì Grafana không hỗ trợ nhiều datasource.
C. Đổi Loki thành Prometheus datasource để dùng chung cú pháp query.
D. Dùng Mixed datasource cho các query riêng rồi ghép dữ liệu khi cần.
Đáp án đúng: D

24. Datasource Grafana dùng chế độ proxy access. Đặc điểm nào đúng?
A. Proxy access tự động mã hóa dữ liệu lưu trong datasource.
B. Browser kết nối trực tiếp backend và đọc credential từ dashboard JSON.
C. Grafana server gửi request tới backend thay vì browser gọi trực tiếp.
D. Proxy access buộc backend chỉ nhận truy vấn từ người dùng đăng nhập.
Đáp án đúng: C

25. Dashboard được provision từ file JSON trong repository. Cách nào giúp giữ liên kết ổn định giữa các môi trường?
A. Đặt UID dashboard ổn định và quản lý JSON trong source control.
B. Để Grafana sinh UID ngẫu nhiên mỗi lần import dashboard.
C. Dùng tên folder làm UID và đổi tên folder theo từng môi trường.
D. Lưu dashboard trong browser local storage của người tạo.
Đáp án đúng: A

26. Một dashboard được provision từ file và thường xuyên được triển khai lại. Nguồn nào nên là nơi quản lý thay đổi chính?
A. Snapshot công khai được tạo sau mỗi lần người dùng mở dashboard.
B. Bộ nhớ cache của browser để giữ phiên bản mới nhất.
C. Bản chỉnh sửa trực tiếp trên UI của một replica Grafana bất kỳ.
D. File provisioning trong source control theo quy trình review và deploy.
Đáp án đúng: D

27. Khi provision datasource có credential, cách nào giảm nguy cơ lộ secret trong cấu hình?
A. Dùng UID datasource làm khóa bí mật thay cho credential backend.
B. Lấy secret từ secret store hoặc biến môi trường và tránh commit giá trị rõ.
C. Ghi token trực tiếp trong JSON dashboard để panel tự xác thực.
D. Đưa mật khẩu vào tên datasource để không cần trường credential.
Đáp án đúng: B

28. Cần giới hạn một nhóm chỉ xem dashboard trong folder của team. Cơ chế nào phù hợp?
A. Ẩn tên folder khỏi menu nhưng giữ quyền truy cập mặc định.
B. Đổi datasource UID để người dùng không tìm được dashboard.
C. Gán quyền folder cho team với role chỉ xem cần thiết.
D. Tắt Explore toàn cục để thay thế mọi quyền folder.
Đáp án đúng: C

29. Người dùng chỉ được xem dashboard nhưng có thể truy vấn trực tiếp datasource ngoài phạm vi team. Cần kiểm tra gì?
A. Quyền datasource và quyền Explore ngoài quyền xem folder.
B. UID dashboard và thứ tự panel trong folder của team.
C. Refresh interval và max data points của các panel liên quan.
D. Màu threshold và unit của panel đang hiển thị dữ liệu.
Đáp án đúng: A

30. Grafana dùng OIDC và cần gán role theo nhóm từ identity provider. Cấu hình nào liên quan trực tiếp?
A. Annotation query đồng bộ nhóm người dùng theo thời gian.
B. Dashboard variable lấy danh sách group từ Prometheus label.
C. Datasource transformation chuyển group name thành quyền folder.
D. Role mapping dựa trên group claim trong thông tin xác thực.
Đáp án đúng: D

31. Một integration chỉ cần tạo và cập nhật dashboard qua Grafana API. Nên cấp credential thế nào?
A. Dùng token Admin chung để mọi API endpoint luôn truy cập được.
B. Dùng mật khẩu của người quản trị đang đăng nhập trên trình duyệt.
C. Dùng UID của datasource để thay thế token khi gọi Grafana API.
D. Dùng service account token với quyền tối thiểu cho thao tác cần thiết.
Đáp án đúng: D

32. Một alert rule cần phát hiện error rate cao theo service. Thiết kế nào phù hợp?
A. Dùng dashboard variable để tự gửi notification khi người dùng đổi service.
B. Dựa vào số lần refresh dashboard để xác định error rate tăng.
C. Tạo query và expression trong alert rule rồi đặt điều kiện ngưỡng.
D. Dùng màu đỏ của panel làm điều kiện kích hoạt cảnh báo.
Đáp án đúng: C

33. Một Grafana alert rule trả về No Data khi datasource không có mẫu. Nên cấu hình gì?
A. Tắt đánh giá rule cho tới khi có người mở dashboard.
B. Đặt hành vi No Data riêng để phân biệt thiếu dữ liệu với trạng thái OK.
C. Coi No Data luôn là OK để tránh mọi cảnh báo ngoài ý muốn.
D. Thay mọi giá trị thiếu bằng zero trước khi đánh giá rule.
Đáp án đúng: B

34. Nhiều panel Prometheus truy vấn cùng metric thô trên khoảng thời gian dài. Cách nào giảm tải backend hiệu quả?
A. Tăng số panel để chia truy vấn lớn thành nhiều truy vấn nhỏ.
B. Đặt refresh interval thấp để Prometheus giữ cache nóng hơn.
C. Tối ưu selector và step, cân nhắc recording rules cho phép tính lặp.
D. Ẩn legend để giảm lượng dữ liệu Prometheus phải tính toán.
Đáp án đúng: C

35. Dashboard hiển thị No data trong khi datasource có dữ liệu. Trình tự kiểm tra nào hữu ích nhất?
A. Tăng timeout mọi datasource trước khi xem nội dung truy vấn.
B. Đổi panel sang Stat vì Time series có thể không nhận dữ liệu rỗng.
C. Kiểm tra time range, biến, query và datasource bằng Explore hoặc Inspector.
D. Xóa dashboard rồi tạo lại để Grafana dựng query mặc định mới.
Đáp án đúng: C

36. Một dashboard có nhiều người dùng đồng thời và Grafana cần chạy nhiều replica. Thành phần nào nên dùng chung?
A. Một thư mục tạm riêng cho từng replica để lưu user và datasource.
B. Cơ sở dữ liệu Grafana bên ngoài được các replica cùng truy cập.
C. SQLite riêng trong writable layer của từng replica Grafana.
D. Browser local storage đồng bộ dashboard giữa các replica.
Đáp án đúng: B
