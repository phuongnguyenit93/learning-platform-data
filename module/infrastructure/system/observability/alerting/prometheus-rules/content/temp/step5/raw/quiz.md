Câu 1. Recording rule của Prometheus được dùng chủ yếu để làm gì?
A. Gửi notification trực tiếp khi vượt một threshold
B. Thêm relabeling trước khi scrape metric nguồn
C. Duy trì trạng thái silence trong Alertmanager
D. Tạo time series mới từ biểu thức được tính trước
Đáp án đúng: D

Câu 2. Một recording rule dùng hai trường YAML cốt lõi nào?
A. Khai báo `receiver` và `expr` trong một rule
B. Khai báo `scrape` và `expr` trong cùng rule
C. Khai báo `record` và `expr` trong cùng một rule
D. Khai báo `alert` và `expr` trong cùng một rule
Đáp án đúng: C

Câu 3. Một alerting rule được nhận biết bởi những trường YAML nào?
A. Khai báo `alert` và `expr` cho điều kiện cảnh báo
B. Khai báo `route` và `expr` cho điều kiện cảnh báo
C. Khai báo `record` và `expr` cho điều kiện cảnh báo
D. Khai báo `target` và `expr` cho điều kiện cảnh báo
Đáp án đúng: A

Câu 4. Cấu trúc file rule Prometheus tổ chức nhiều rule ra sao?
A. Trong `groups`, mỗi nhóm có `name` và `rules`
B. Trong `targets`, mỗi nhóm có `name` và `rules`
C. Trong `receivers`, mỗi nhóm có `name` và `rules`
D. Trong `scrapes`, mỗi nhóm có `name` và `rules`
Đáp án đúng: A

Câu 5. Muốn đổi chu kỳ đánh giá riêng cho một rule group, nên làm gì?
A. Thiết lập `scrape_timeout` trên rule group
B. Thiết lập `for` trên rule group được chọn
C. Thiết lập `interval` trên rule group được chọn
D. Thiết lập `repeat_interval` trên rule group
Đáp án đúng: C

Câu 6. `for: 5m` trong alerting rule có ý nghĩa gì?
A. Thông báo được lặp mỗi năm phút sau firing
B. Điều kiện phải tiếp tục khớp đủ năm phút
C. Prometheus chỉ đánh giá rule mỗi năm phút
D. Biểu thức PromQL chỉ đọc dữ liệu năm phút
Đáp án đúng: B

Câu 7. Nếu alerting rule không khai báo `for`, khi nào alert có thể firing?
A. Sau khi Alertmanager gửi notification đầu
B. Sau khi target được scrape đủ năm phút
C. Sau ít nhất hai lần đánh giá thỏa biểu thức
D. Ngay tại lần đánh giá đầu tiên thỏa biểu thức
Đáp án đúng: D

Câu 8. `keep_firing_for: 3m` trong alerting rule hỗ trợ mục tiêu nào?
A. Lặp notification sau mỗi ba phút không đổi
B. Giữ trạng thái firing tạm thời sau khi điều kiện hết
C. Chờ ba phút trước khi một alert được firing
D. Đánh giá lại rule sau mỗi ba phút liên tục
Đáp án đúng: B

Câu 9. Trạng thái pending của một alert có `for` được hiểu như thế nào?
A. Alertmanager đã gửi thông báo nhưng đang đợi ACK
B. Target đã bị xóa khỏi toàn bộ service discovery
C. Điều kiện đã hết khớp sau khi từng firing trước đó
D. Điều kiện đang khớp nhưng chưa đủ thời gian `for`
Đáp án đúng: D

Câu 10. Biểu thức `up{job="api"} == 0` thường phát hiện trường hợp nào?
A. Target thuộc job api có latency request tăng cao
B. Target thuộc job api đã biến mất khỏi cấu hình scrape
C. Target thuộc job api trả về HTTP lỗi ở ứng dụng
D. Target thuộc job api có lần scrape không thành công
Đáp án đúng: D

Câu 11. Biểu thức `absent(up{job="api"})` hữu ích trong tình huống nào?
A. Có một time series `up` mang giá trị bằng 0
B. Có một time series `up` mang giá trị bằng 1
C. Không có time series `up` nào khớp job api
D. Có nhiều time series `up` đang đổi instance
Đáp án đúng: C

Câu 12. `absent_over_time(foo[10m])` kiểm tra điều kiện nào?
A. Không có mẫu foo nào trong khoảng mười phút
B. Giá trị foo trung bình giảm trong mười phút
C. Giá trị foo cực đại vượt ngưỡng mười phút
D. Có mẫu foo bằng không trong mười phút liên tiếp
Đáp án đúng: A

Câu 13. Vì sao so sánh `http_requests_total == 0` không đủ để nhận biết metric biến mất?
A. Series không tồn tại luôn được tự đổi thành 0
B. Series không tồn tại có thể khiến kết quả rỗng
C. Series không tồn tại luôn có nhãn severity cao
D. Series không tồn tại luôn được Alertmanager tạo
Đáp án đúng: B

Câu 14. Rủi ro khi dùng `metric or vector(0)` không kiểm soát trong alert là gì?
A. Có thể sửa nhãn instance của metric nguồn
B. Có thể buộc mọi counter quay về giá trị đầu
C. Có thể che việc mất metric bằng giá trị mặc định 0
D. Có thể tự tạo lại target không còn được scrape
Đáp án đúng: C

Câu 15. `rate(http_requests_total[5m])` thường ước tính giá trị gì?
A. Số lượng instance còn healthy trong 5 phút
B. Tổng số request tuyệt đối kể từ khi server chạy
C. Độ trễ trung bình của các request trong 5 phút
D. Tốc độ tăng counter mỗi giây trên cửa sổ 5 phút
Đáp án đúng: D

Câu 16. `increase(errors_total[1h])` chủ yếu dùng để tính gì?
A. Tốc độ tăng counter mỗi giây của một giờ
B. Lượng tăng counter ước tính trong một giờ
C. Giá trị trung bình gauge trong một giờ
D. Số lượng label khác nhau trong một giờ
Đáp án đúng: B

Câu 17. Biểu thức `sum by (job) (rate(requests_total[5m]))` trả về dữ liệu gì?
A. Tốc độ request cộng theo mỗi nhãn job
B. Trung vị thời gian phản hồi theo mỗi job
C. Tốc độ request riêng theo mỗi nhãn instance
D. Tổng số request đã ghi theo mỗi nhãn job
Đáp án đúng: A

Câu 18. Cách tính tỷ lệ lỗi HTTP 5xx bằng PromQL nào phù hợp nhất?
A. Lấy tổng counter 5xx cộng tổng counter 2xx
B. Lấy rate 5xx chia số instance đang healthy
C. Lấy tổng latency 5xx chia tổng latency 2xx
D. Lấy tổng rate 5xx chia tổng rate mọi request
Đáp án đúng: D

Câu 19. Muốn ước lượng p95 latency bằng histogram cổ điển, dùng cách nào?
A. Dùng `increase` của metric tổng số request
B. Dùng `histogram_quantile` trên rate bucket cộng gộp
C. Dùng `quantile` trực tiếp trên metric `_count`
D. Dùng `avg_over_time` trực tiếp trên counter bucket
Đáp án đúng: B

Câu 20. Khi gom histogram bucket theo service để tính quantile, nhãn nào cần được giữ?
A. Giữ nhãn `version` nhưng bỏ nhãn `le`
B. Giữ nhãn `instance` nhưng bỏ nhãn `le`
C. Giữ nhãn `le` cùng nhãn gom service
D. Giữ nhãn `pod` nhưng bỏ nhãn `le`
Đáp án đúng: C

Câu 21. Hàm `avg_over_time(cpu_usage[10m])` phù hợp cho trường hợp nào?
A. Tính trung bình gauge CPU trong mười phút
B. Tính tổng số bucket CPU trong mười phút
C. Tính tốc độ scrape CPU trong mười phút
D. Tính lượng tăng counter CPU trong mười phút
Đáp án đúng: A

Câu 22. Khác nhau chính giữa `for: 10m` và `rate(counter[10m])` là gì?
A. `for` đổi lịch scrape; `rate` đổi lịch evaluation
B. `for` tính tốc độ cửa sổ; `rate` trì hoãn firing
C. `for` chỉ dùng khi có counter; `rate` chỉ dùng gauge
D. `for` đòi điều kiện bền; `rate` tính tốc độ cửa sổ
Đáp án đúng: D

Câu 23. Các rule trong cùng một group Prometheus thường được đánh giá theo cách nào?
A. Đánh giá ngẫu nhiên không theo thứ tự khai báo
B. Đánh giá tuần tự theo thứ tự rule trong group
C. Đánh giá theo severity từ thấp đến cao trong group
D. Đánh giá khi Alertmanager yêu cầu từng rule
Đáp án đúng: B

Câu 24. Nếu điều kiện PromQL hết khớp khi alert vẫn pending, thời gian `for` sẽ thế nào?
A. Khoảng chờ pending bị đặt lại cho lần khớp sau
B. Khoảng chờ pending chuyển sang Alertmanager lưu
C. Khoảng chờ pending được tăng gấp đôi khi sai
D. Khoảng chờ pending tiếp tục cộng qua mọi lần sai
Đáp án đúng: A

Câu 25. Nhãn `severity: critical` trên alert thường hữu ích cho việc gì?
A. Phân loại và định tuyến cảnh báo theo mức độ
B. Định nghĩa thời gian đánh giá theo mức độ
C. Thay đổi cửa sổ range selector của PromQL
D. Tự đổi số lần retry scrape theo mức độ
Đáp án đúng: A

Câu 26. Annotation `runbook_url` trong rule nên chứa nội dung gì?
A. Cấu hình scrape job và danh sách target
B. Liên kết hướng dẫn điều tra và xử lý sự cố
C. Tên receiver mặc định trong Alertmanager
D. Giá trị nhãn dùng để phân biệt từng instance
Đáp án đúng: B

Câu 27. Trong annotation, mẫu `{{ $labels.instance }}` thường dùng để làm gì?
A. Chèn số lần rule được Prometheus reload
B. Chèn giá trị toàn bộ counter ở thời điểm scrape
C. Chèn giá trị nhãn instance của alert hiện tại
D. Chèn địa chỉ IP của Alertmanager đang chạy
Đáp án đúng: C

Câu 28. Khi một nhãn nhận diện alert đổi giá trị, hệ quả thường gặp là gì?
A. Alert luôn giữ nguyên danh tính qua mọi nhãn đổi
B. Alert được chuyển thẳng thành recording rule mới
C. Alert tự mất toàn bộ annotation trong cấu hình
D. Alert có thể được nhận diện như một thực thể mới
Đáp án đúng: D

Câu 29. Vì sao không nên dùng giá trị biến động liên tục làm label của alert?
A. Dễ tạo nhiều danh tính alert và notification nhiễu
B. Buộc Alertmanager tự tăng scrape interval
C. Giúp mọi alert có chung danh tính không đổi
D. Làm rule group luôn đánh giá đúng một lần
Đáp án đúng: A

Câu 30. Vai trò chính của Alertmanager so với Prometheus alerting rules là gì?
A. Đọc biểu thức PromQL và quyết định alert pending
B. Thu thập metric nguồn từ các exporter đang chạy
C. Lưu mẫu recording rule thành chuỗi thời gian
D. Định tuyến, gom nhóm, khử trùng và gửi thông báo
Đáp án đúng: D

Câu 31. Silence trong Alertmanager tác động như thế nào đến alert đang firing?
A. Đổi biểu thức của alerting rule sang giá trị sai
B. Chặn notification khớp nhãn trong khoảng đã đặt
C. Ngừng mọi chu kỳ evaluation trên Prometheus
D. Xóa bản ghi time series gốc khỏi Prometheus
Đáp án đúng: B

Câu 32. Inhibition trong Alertmanager được dùng để làm gì?
A. Thay nhãn service bằng nhãn receiver của nhóm
B. Hoãn toàn bộ việc scrape target đang bị cảnh báo
C. Xóa rule group khi một alert đã gửi notification
D. Ức chế alert phụ khi alert khác thỏa điều kiện
Đáp án đúng: D

Câu 33. Tham số `group_wait` của Alertmanager kiểm soát thời điểm nào?
A. Khoảng đợi trước khi alerting rule đạt trạng thái firing
B. Khoảng lặp thông báo cũ của một nhóm không đổi
C. Khoảng đợi trước notification đầu của một nhóm
D. Khoảng cách tối thiểu giữa hai lần scrape target
Đáp án đúng: C

Câu 34. Tham số `repeat_interval` trong Alertmanager kiểm soát điều gì?
A. Khi recording rule tạo mẫu time series mới
B. Khi chuyển alert pending sang trạng thái firing
C. Khi lặp notification cho một nhóm chưa đổi
D. Khi bắt đầu scrape lại một target lỗi
Đáp án đúng: C

Câu 35. Cấu hình `group_by: ['service']` trong Alertmanager chủ yếu nhằm mục đích gì?
A. Gom time series cùng service để tăng tốc PromQL
B. Gom alert có cùng nhãn service vào một nhóm
C. Gom rule group cùng service thành một file YAML
D. Gom target cùng service để thay đổi scrape interval
Đáp án đúng: B

Câu 36. Khi alert bị silence, trạng thái đánh giá của Prometheus thường ra sao?
A. Alert tự động bị xóa khỏi bộ nhớ Prometheus
B. Alert vẫn có thể firing dù notification bị chặn
C. Metric nguồn tự đổi về số không trong PromQL
D. Prometheus ngừng đánh giá rule tương ứng ngay
Đáp án đúng: B

Câu 37. Với mục tiêu availability 99,9%, tỷ lệ lỗi được phép theo ngân sách là bao nhiêu?
A. Khoảng 1,0% lượng request trong kỳ SLO
B. Khoảng 9,9% lượng request trong kỳ SLO
C. Khoảng 0,01% lượng request trong kỳ SLO
D. Khoảng 0,1% lượng request trong kỳ SLO
Đáp án đúng: D

Câu 38. Burn rate bằng 10 đối với error budget SLO biểu thị điều gì?
A. Đang có mười lỗi tuyệt đối trong mỗi phút
B. Đang tiêu ngân sách lỗi nhanh gấp mười lần
C. Đang có mười phần trăm request lỗi cố định
D. Đang giảm ngân sách lỗi xuống còn mười phần
Đáp án đúng: B

Câu 39. Multi-window burn-rate alert thường dùng hai cửa sổ dài và ngắn để làm gì?
A. Giữ mọi alert ở pending qua toàn bộ chu kỳ SLO
B. Loại bỏ nhu cầu đo tỷ lệ lỗi thực từ các request
C. Kết hợp độ bền tín hiệu với phát hiện lỗi đang xảy ra
D. Bảo đảm mọi sự cố kéo dài dưới một phút đều firing
Đáp án đúng: C

Câu 40. Khi một target biến mất khỏi discovery, cách theo dõi nào giảm nguy cơ bỏ sót?
A. Chỉ theo dõi biểu thức `up == 0` trên target
B. Chỉ dùng annotation chứa hostname target
C. Giám sát cả sự vắng mặt series và lỗi scrape
D. Chỉ tăng mức severity cho mọi metric có sẵn
Đáp án đúng: C

Câu 41. Lệnh `promtool check rules` dùng trong CI có chức năng chính gì?
A. Kiểm tra cú pháp và cấu trúc file rule Prometheus
B. Khởi chạy một Alertmanager với cấu hình mặc định
C. Chạy mô phỏng chuỗi mẫu và so đáp án alert
D. Triển khai rule lên production và gửi notification
Đáp án đúng: A

Câu 42. Lệnh `promtool test rules` giúp xác minh khía cạnh nào?
A. Chỉ kiểm tra một file YAML có thể parse hay không
B. Chỉ tải cấu hình Alertmanager lên service cloud
C. Chạy test rule trên dữ liệu đầu vào và kỳ vọng
D. Chỉ đo CPU của Prometheus khi scrape dữ liệu
Đáp án đúng: C

Câu 43. Trường `rule_files` trong cấu hình Prometheus có tác dụng gì?
A. Chỉ định các file chứa recording và alerting rules
B. Chỉ định URL receiver của từng nhóm thông báo
C. Chỉ định danh sách endpoint để service discovery
D. Chỉ định nơi lưu dữ liệu TSDB theo từng block
Đáp án đúng: A

Câu 44. Quy trình CI/CD nào phù hợp nhất trước khi phát hành rule cảnh báo mới?
A. Lint, test rule, review thay đổi và quan sát sau deploy
B. Chỉ tăng ngưỡng alert và không kiểm tra SLO hiện tại
C. Deploy thẳng production rồi tắt đánh giá nếu nhiễu
D. Chỉ đối chiếu tên file rồi bỏ qua tình huống thiếu dữ liệu
Đáp án đúng: A
