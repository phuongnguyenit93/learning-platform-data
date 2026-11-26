Câu 01. Trong hệ Prometheus, nhiệm vụ chính của Alertmanager là gì?
A. Đánh giá biểu thức PromQL rồi thay thế toàn bộ alert rule.
B. Nhận alert rồi gom nhóm, khử trùng lặp và gửi thông báo.
C. Thu thập metric trực tiếp từ exporter rồi ghi vào TSDB.
D. Chạy truy vấn dashboard để xác định tình trạng của service.
Đáp án đúng: B

Câu 02. Thành phần nào thường đánh giá điều kiện của alerting rule trước khi báo Alertmanager?
A. Template notification tự truy vấn metric để phát hiện lỗi.
B. Alertmanager thực thi PromQL và tự truy vấn dữ liệu metric.
C. Receiver webhook chạy PromQL rồi tự định nghĩa severity.
D. Prometheus thực thi rule và chuyển alert đang firing đi.
Đáp án đúng: D

Câu 03. Khi cần route alert theo đội phụ trách, nên đặt thông tin nào trong labels?
A. Đặt biểu thức PromQL trong body để receiver suy ra đội.
B. Đặt thời gian đánh giá rule vào header của webhook gửi.
C. Đặt annotation summary để route phân tích nội dung tự do.
D. Đặt label team để chọn receiver đúng theo đội phụ trách.
Đáp án đúng: D

Câu 04. Trong Alertmanager, thay đổi annotation nhưng giữ nguyên labels có ảnh hưởng gì đến định danh alert?
A. Đổi annotation không tạo một fingerprint alert mới.
B. Annotation đổi luôn tạo fingerprint mới để route lại.
C. Annotation đổi khiến mọi silence đang chạy hết hạn.
D. Annotation đổi làm alert được chuyển thành resolved.
Đáp án đúng: A

Câu 05. Trạng thái firing và resolved của alert biểu thị điều gì?
A. Firing có nhãn severity; resolved không có label nào nữa.
B. Firing được gửi qua email; resolved chỉ được ghi trong TSDB.
C. Firing đang thỏa điều kiện; resolved là trạng thái đã hết.
D. Firing là cảnh báo bị silence; resolved là cảnh báo bị inhibit.
Đáp án đúng: C

Câu 06. Root route trong Alertmanager cần được cấu hình theo nguyên tắc nào?
A. Chỉ khớp một namespace và bắt buộc bật continue.
B. Không có receiver và chỉ gồm các child route rỗng.
C. Không có matcher và có receiver làm đích mặc định.
D. Chỉ khớp severity=critical và không khai báo receiver.
Đáp án đúng: C

Câu 07. Một child route không khai báo group_wait sẽ lấy giá trị nào?
A. Luôn sử dụng group_wait bằng không bất kể route cha.
B. Lấy group_wait ở route cha khi child chưa khai báo.
C. Luôn lấy group_wait từ cấu hình của receiver email.
D. Đọc group_wait từ annotation của alert hiện tại.
Đáp án đúng: B

Câu 08. Hai matcher trong cùng một route được đánh giá theo quy tắc nào?
A. Matcher thứ hai chỉ kiểm tra khi receiver gửi lỗi.
B. Alert cần thỏa đồng thời các matcher của route.
C. Chỉ cần thỏa một matcher bất kỳ là được chọn.
D. Chỉ matcher cuối cùng quyết định route được chọn.
Đáp án đúng: B

Câu 09. Matcher service=~"api|web" được dùng cho trường hợp nào?
A. Khớp label service có tên api và label khác tên web.
B. Khớp chuỗi annotation chứa api hoặc web thay vì label.
C. Khớp service bằng api hoặc web theo biểu thức regex RE2.
D. Khớp mọi giá trị service có chứa chuỗi api hoặc web ở giữa.
Đáp án đúng: C

Câu 10. Với hai sibling route cùng khớp, continue: true trên route đầu làm gì?
A. Cho phép xét sibling route tiếp để gửi thông báo bổ sung.
B. Buộc mọi alert luôn đi thẳng tới receiver của root route.
C. Chuyển alert đang firing thành resolved trước khi xét route.
D. Buộc receiver đầu chờ hết retry mới thử route còn lại.
Đáp án đúng: A

Câu 11. Nếu continue không bật trên child route đã khớp thì điều gì xảy ra?
A. Ngừng toàn bộ Alertmanager cho tới lần reload kế.
B. Chuyển mọi alert tới tất cả receiver trong cấu hình.
C. Ngừng xét sibling tiếp theo tại cấp route đó.
D. Bỏ qua child route vừa khớp và dùng receiver root.
Đáp án đúng: C

Câu 12. group_by: [alertname, cluster] có tác động nào lên notification?
A. Gom tất cả alert thành một nhóm duy nhất toàn hệ.
B. Tách một nhóm riêng cho từng annotation description.
C. Phân nhóm theo message text và địa chỉ email nhận.
D. Gom nhóm theo cùng giá trị alertname và cluster.
Đáp án đúng: D

Câu 13. group_by: ['...'] có ý nghĩa nào trong routing Alertmanager?
A. Chỉ gộp theo label alertname và bỏ qua các label khác.
B. Chỉ tạo một nhóm duy nhất cho mọi alert đang firing.
C. Nhóm theo mọi label, gần như tắt việc gộp nhiều alert.
D. Gộp theo thời gian bắt đầu thay vì theo các alert labels.
Đáp án đúng: C

Câu 14. group_wait: 30s thường giúp giảm nhiễu bằng cách nào?
A. Chờ giữa mọi lần retry gửi cùng một webhook bị lỗi.
B. Chờ nhóm mới một khoảng để gom alert tới gần nhau.
C. Chờ mỗi alert 30 giây rồi tự động đổi sang resolved.
D. Chờ receiver trả kết quả trước khi áp matcher của route.
Đáp án đúng: B

Câu 15. Nếu một alert đã resolved trước khi hết group_wait của nhóm mới, điều gì có thể xảy ra?
A. Không cần gửi thông báo cho alert chỉ tồn tại rất ngắn.
B. Đổi severity của alert thành info trước khi gửi.
C. Đẩy alert qua route khác mà không xét matcher nữa.
D. Luôn gửi firing rồi resolved sau khi hết group_wait.
Đáp án đúng: A

Câu 16. group_interval trong Alertmanager điều chỉnh điều gì?
A. Khoảng chờ ban đầu từ lúc một nhóm vừa xuất hiện.
B. Thời hạn lưu lịch sử của alert đã resolved trên đĩa.
C. Khoảng thời gian Prometheus chạy biểu thức alert rule.
D. Định kỳ xét thay đổi nhóm sau khi gửi thông báo đầu.
Đáp án đúng: D

Câu 17. repeat_interval khác group_interval như thế nào?
A. Điều khiển khoảng scrape metric của Prometheus exporter.
B. Điều khiển lúc nhắc lại nhóm không có thay đổi mới.
C. Điều khiển lúc gom alert mới vào một nhóm chưa gửi lần đầu.
D. Điều khiển thời gian HTTP request được phép chờ receiver.
Đáp án đúng: B

Câu 18. Vì sao nên chọn repeat_interval là bội số của group_interval?
A. Vì việc nhắc lại được xét theo nhịp của group_interval.
B. Vì repeat_interval ngắn hơn sẽ vô hiệu hóa route tree.
C. Vì group_interval chỉ dùng khi repeat_interval là số lẻ.
D. Vì Alertmanager bắt buộc hai giá trị luôn bằng nhau.
Đáp án đúng: A

Câu 19. Một receiver Alertmanager có thể được cấu hình thế nào?
A. Một receiver luôn chỉ có một địa chỉ email và không có webhook.
B. Một receiver tự động nhận mọi alert dù route không trỏ tới.
C. Một receiver bắt buộc phải có một rule PromQL riêng biệt.
D. Một receiver được đặt tên và có thể chứa nhiều integration.
Đáp án đúng: D

Câu 20. Muốn cảnh báo critical tới kênh pager thay vì email thường, nên cấu hình gì?
A. Chỉ chỉnh group_by để một nhóm chứa mọi cảnh báo critical.
B. Đổi mọi annotation description thành văn bản critical.
C. Tạo child route khớp severity=critical và receiver pager.
D. Đổi repeat_interval thành 0 để chỉ gửi một lần duy nhất.
Đáp án đúng: C

Câu 21. Muốn gửi thông báo khi alert hết firing, cần kiểm tra tùy chọn nào?
A. Bật continue trên root route của mọi cấu hình.
B. Bật source_matchers trong tất cả inhibit rule.
C. Bật send_resolved trong integration receiver hỗ trợ.
D. Bật group_by cho từng instance đang được cảnh báo.
Đáp án đúng: C

Câu 22. Template thông báo Alertmanager được viết chủ yếu bằng cơ chế nào?
A. Dùng Go templates để render dữ liệu của alert group.
B. Dùng trực tiếp câu truy vấn PromQL để dựng nội dung.
C. Dùng JavaScript chạy trong browser của người trực ca.
D. Dùng SQL trigger trên storage của Prometheus metrics.
Đáp án đúng: A

Câu 23. Trong notification template, .GroupLabels thường biểu diễn gì?
A. Tập label chung đã dùng làm khóa để nhóm alert.
B. Toàn bộ label chỉ xuất hiện ở một alert riêng lẻ.
C. Tất cả annotation của alert mới nhất trong nhóm.
D. Danh sách receiver đã thử gửi trong cùng một lượt.
Đáp án đúng: A

Câu 24. Trong template, .CommonLabels khác .GroupLabels ở điểm nào?
A. CommonLabels chỉ chứa annotation summary của từng alert.
B. CommonLabels chỉ có những label khác nhau giữa các alert.
C. CommonLabels chỉ giữ các label xuất hiện trong group_by.
D. CommonLabels gồm các label giống nhau ở mọi alert của nhóm.
Đáp án đúng: D

Câu 25. Biểu thức template .Alerts.Firing hỗ trợ thao tác nào?
A. Duyệt toàn bộ rule đang được Prometheus tải vào RAM.
B. Duyệt alert còn firing trong nhóm được gửi thông báo.
C. Duyệt các silence đã hết hạn của mọi receiver.
D. Duyệt những alert đã resolved ở các nhóm trước.
Đáp án đúng: B

Câu 26. Trong inhibition, source_matchers và target_matchers có vai trò nào?
A. Source chọn route cha; target chọn thời gian lưu alert.
B. Source chọn receiver email; target chọn webhook đích.
C. Source chọn Prometheus server; target chọn dashboard metric.
D. Source chọn alert gây ức chế; target chọn alert bị ức chế.
Đáp án đúng: D

Câu 27. Muốn critical kìm warning của cùng service và cluster, equal nên đặt gì?
A. equal gồm service và cluster để hai alert phải trùng nhãn.
B. equal chỉ gồm instance dù các instance thuộc service khác.
C. equal gồm description để so sánh nội dung văn bản tự do.
D. equal chỉ gồm severity để critical và warning được coi là một.
Đáp án đúng: A

Câu 28. Nếu hai alert đều thiếu một label trong equal của inhibition, điều gì đáng chú ý?
A. Alert thiếu label luôn bị loại khỏi mọi rule inhibition.
B. Alert thiếu label tự động nhận tên route làm giá trị.
C. Hai alert cùng thiếu label vẫn có thể được coi là bằng.
D. Label thiếu làm rule tự chuyển sang silence có thời hạn.
Đáp án đúng: C

Câu 29. Silence trong Alertmanager thường được tạo dựa trên gì?
A. Trạng thái filesystem và quota lưu alert trên server.
B. Câu PromQL và số chu kỳ scrape của exporter tương ứng.
C. Dùng matcher label và khoảng thời gian hiệu lực.
D. IP của dashboard và kích thước notification template.
Đáp án đúng: C

Câu 30. Cảnh báo đang bị silence có được coi là resolved tự động không?
A. Có; silence xóa metric nguồn khỏi Prometheus TSDB.
B. Không; silence chặn gửi chứ không đổi trạng thái alert.
C. Không; silence chỉ đổi receiver nhưng vẫn gửi như cũ.
D. Có; silence gửi yêu cầu đổi rule thành resolved ngay.
Đáp án đúng: B

Câu 31. Silence và inhibition khác nhau cơ bản ở điểm nào?
A. Silence phụ thuộc alert critical; inhibition dùng lịch tắt thủ công.
B. Silence tắt scrape metric; inhibition xóa rule khỏi Prometheus.
C. Silence có matcher/thời hạn; inhibition phụ thuộc alert nguồn.
D. Silence thay receiver; inhibition chỉ đổi thông báo sang email.
Đáp án đúng: C

Câu 32. mute_time_intervals trên một child route dùng để làm gì?
A. Điều chỉnh khoảng scrape của exporter theo giờ trực ca.
B. Xóa tất cả các alert thuộc route khỏi Prometheus sau mỗi khoảng.
C. Thay đổi nhãn severity của alert theo lịch được cấu hình.
D. Tạm ngừng notification theo lịch đã khai báo trên route.
Đáp án đúng: D

Câu 33. active_time_intervals trên child route có ý nghĩa nào?
A. Chỉ gửi thông báo khi đang trong khoảng thời gian chỉ định.
B. Chỉ cho receiver gửi webhook khi Prometheus ở chế độ HA.
C. Bật ghi lại mọi notification trong TSDB ở giờ làm việc.
D. Bắt mọi alert mới phải chờ đến cuối một group_interval.
Đáp án đúng: A

Câu 34. Trong HA Alertmanager, các instance thường chia sẻ trạng thái bằng cách nào?
A. Dùng cùng file SQLite trên volume của pod primary duy nhất.
B. Gossip chia sẻ silences và notification log giữa các node.
C. Dùng PromQL recording rule để đồng bộ receiver qua TSDB.
D. Dùng DNS round-robin để sao chép cấu hình và state liên tục.
Đáp án đúng: B

Câu 35. Khi cấu hình Prometheus gửi alert tới cụm Alertmanager HA, nên làm gì?
A. Chỉ gửi đến instance leader và để instance khác không nhận.
B. Chỉ gửi đến một instance ngẫu nhiên qua load balancer chung.
C. Chỉ gửi đến Alertmanager có uptime cao nhất khi cài đặt.
D. Prometheus nên gửi alert tới tất cả node Alertmanager HA.
Đáp án đúng: D

Câu 36. Nếu cụm Alertmanager HA bị phân vùng mạng, điều gì có thể xảy ra?
A. Mọi receiver tự chuyển thành chế độ im lặng vô thời hạn.
B. Thông báo có thể bị lặp vì đồng bộ trạng thái chậm.
C. Mọi rule Prometheus dừng đánh giá tới khi cluster hợp nhất.
D. Mọi alert vẫn được bảo đảm gửi đúng một lần tuyệt đối.
Đáp án đúng: B

Câu 37. Trước khi đưa file alertmanager.yml lên production, dùng lệnh nào?
A. promtool tsdb analyze để kiểm tra receiver và inhibit rule.
B. alertmanager --dry-run-migrate để chạy giả lập toàn bộ route.
C. promtool test rules để kiểm tra cấu hình SMTP receiver.
D. Dùng amtool check-config để kiểm tra file YAML có hợp lệ.
Đáp án đúng: D

Câu 38. Để xác minh alert có labels cụ thể sẽ vào receiver nào, nên dùng gì?
A. amtool config routes test cùng bộ label của alert.
B. alertmanager --version để in cây route và matching receiver.
C. amtool silence add để kiểm tra routing mà không tạo silence.
D. promtool query instant để tra notification log của receiver.
Đáp án đúng: A

Câu 39. Sau khi chỉnh cấu hình Alertmanager, cách reload được hỗ trợ là gì?
A. Chỉ sửa file trên đĩa và đợi mọi receiver tự reload tức thì.
B. Gửi SIGHUP hoặc POST tới endpoint /-/reload.
C. Gọi HTTP DELETE tới /api/v2/alerts để cập nhật route tree.
D. Xóa mọi active silence để tiến trình tự phát hiện file mới.
Đáp án đúng: B

Câu 40. Trong kiểm thử luồng cảnh báo end-to-end, cần kiểm tra tổ hợp nào?
A. Đúng receiver, grouping, silence/inhibition và trạng thái resolved.
B. Chỉ số lượng dashboard đang mở và mức CPU của máy giám sát.
C. Chỉ kích thước file cấu hình và thứ tự email trong receiver.
D. Chỉ kết quả PromQL tức thời mà không thử gửi notification.
Đáp án đúng: A
