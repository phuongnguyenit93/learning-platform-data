Câu 01. Khi nhận cảnh báo độ trễ API tăng, bước khoanh vùng nào nên làm trước?
A. Khoanh vùng endpoint, mốc giờ và tập request bị lỗi.
B. Xem heap usage của một pod đơn lẻ để chốt nguyên nhân.
C. Đọc log khởi động của tất cả service chưa có lỗi.
D. Đổi cấu hình timeout trước khi xác định dịch vụ chậm.
Đáp án đúng: A

Câu 02. Bộ bốn golden signals thường giúp quan sát dịch vụ theo những trục nào?
A. Log volume, DNS TTL, node count và thời gian build.
B. Latency, phiên bản, số pod và tuổi chứng chỉ TLS.
C. Độ trễ, lưu lượng, lỗi và mức bão hòa tài nguyên.
D. CPU, RAM, dung lượng image và số lần triển khai.
Đáp án đúng: C

Câu 03. p99 latency tăng còn median gần như ổn định thường gợi ý điều gì?
A. Throughput đã tăng đúng bằng tỷ lệ thay đổi p99.
B. Nhóm request ở đuôi phân phối đang chậm rõ rệt.
C. Toàn bộ backend đều có CPU bị giới hạn bởi quota.
D. Tất cả request cùng tăng độ trễ gần như bằng nhau.
Đáp án đúng: B

Câu 04. Khi lỗi tăng ngay sau một lần deploy, cách kiểm chứng nào đáng ưu tiên?
A. Quy kết deploy gây lỗi mà không đối chiếu phân bố traffic.
B. So sánh theo mốc deploy, phiên bản và nhóm pod cũ/mới.
C. Tăng thời gian timeout để che lỗi ở bản mới đang chạy.
D. Chỉ xem một biểu đồ CPU tổng hợp của toàn bộ cluster.
Đáp án đúng: B

Câu 05. Với metric counter tăng dần nhưng có thể reset khi restart, nên tính gì?
A. Dùng giá trị hiện tại của counter như phần trăm lỗi.
B. Lấy hiệu số hai mẫu bất kỳ mà không xét reset.
C. Trung bình trực tiếp giá trị counter giữa các pod.
D. Dùng rate hoặc increase để tính mức tăng khi counter reset.
Đáp án đúng: D

Câu 06. Khi cần tìm nội dung lỗi cụ thể của một request 500, nguồn nào phù hợp?
A. Chỉ metric p95 latency không chứa ngữ cảnh từng request.
B. Chỉ biểu đồ phần trăm sử dụng disk theo từng volume.
C. Chỉ biểu đồ tổng số byte gửi qua cổng mạng của node.
D. Tìm log gắn request ID và lỗi tại đúng mốc thời gian.
Đáp án đúng: D

Câu 07. Distributed trace giúp định vị chặng chậm bằng thông tin nào?
A. Chỉ tổng số request theo phút trong namespace liên quan.
B. Span và quan hệ cha-con cùng thời lượng các chặng.
C. Chỉ số dòng log được ghi trong một ngày vận hành.
D. Chỉ dung lượng bộ nhớ đã cấp cho service đầu vào.
Đáp án đúng: B

Câu 08. Để ghép log của gateway và backend thuộc cùng request, cần làm gì?
A. Chỉ đồng bộ tên hostname giữa mọi instance backend.
B. Tạo log file chung bằng cách ghi vào một pod cố định.
C. Truyền request ID hoặc trace ID thống nhất qua tất cả các hop.
D. Nhóm log theo mức severity bất kể request nào gửi.
Đáp án đúng: C

Câu 09. Nếu timestamp của các node lệch nhau, phân tích trace/log bị ảnh hưởng ra sao?
A. Mốc log bị lệch, dễ dẫn đến thứ tự sự kiện sai.
B. Những request không còn được Prometheus thu thập.
C. Bộ nhớ heap của JVM tự tăng theo độ lệch đồng hồ.
D. Mọi HTTP status trong trace tự chuyển thành 500.
Đáp án đúng: A

Câu 10. Khi tracing có sampling, kết luận nào cần thận trọng?
A. Trace đã lấy mẫu có thể bỏ sót một số request hiếm.
B. Sampling bảo đảm mọi lỗi đều có trace trong kho lưu.
C. Sampling làm mọi request có thời lượng giống nhau.
D. Sampling thay thế được metric đo tổng tỷ lệ lỗi.
Đáp án đúng: A

Câu 11. Đặt user_id làm label metric cho từng tài khoản có nguy cơ gì?
A. CPU ứng dụng sẽ luôn giảm vì không cần ghi access log.
B. Metric sẽ mất hoàn toàn khả năng tính rate theo thời gian.
C. Cardinality tăng mạnh, gây áp lực lưu trữ và truy vấn.
D. Prometheus tự loại bỏ tất cả chuỗi có label user_id.
Đáp án đúng: C

Câu 12. JVM có nhiều đợt stop-the-world GC đúng lúc p99 tăng. Giả thuyết nào hợp lý?
A. Thời gian chờ DB lock chắc chắn bằng thời lượng GC.
B. Độ trễ bị ảnh hưởng bởi các khoảng tạm dừng GC.
C. CPU throttle chắc chắn xuất hiện trên mọi pod JVM.
D. Latency chỉ tăng do lỗi TCP retransmission của node.
Đáp án đúng: B

Câu 13. Biểu đồ used heap sau full GC tăng dần qua nhiều chu kỳ gợi ý điều gì?
A. Khả năng giữ object lâu ngoài dự kiến cần điều tra.
B. Heap hoàn toàn khỏe khi mức dùng trước GC đang giảm dần.
C. Ứng dụng chắc chắn đang thiếu số luồng xử lý HTTP.
D. Network ingress đang giới hạn băng thông của pod.
Đáp án đúng: A

Câu 14. Khi JVM có RSS cao nhưng Java heap còn thấp, nên xem xét gì?
A. Chỉ số lượng request ghi vào cache của browser.
B. Chỉ số lượng object còn sống trong Java heap.
C. Kiểm tra native memory, direct buffer, thread stack và mmap.
D. Chỉ thời gian xử lý một câu truy vấn SQL bất kỳ.
Đáp án đúng: C

Câu 15. Khi lấy heap dump production để phân tích memory leak, cần lưu ý gì?
A. Dump không ảnh hưởng tài nguyên khi JVM đang tải cao.
B. Dump thay thế được việc so sánh allocation qua thời gian.
C. Dump chỉ chứa tên class nên không có nguy cơ lộ dữ liệu.
D. Heap dump có thể chứa dữ liệu nhạy cảm và gây tăng tải bộ nhớ.
Đáp án đúng: D

Câu 16. CPU profiling bằng flame graph hỗ trợ câu hỏi nào?
A. Những HTTP route nào đã bị CORS từ chối trên browser.
B. Những DNS record nào vừa được cập nhật trong cluster.
C. Những call stack nào tiêu tốn phần lớn CPU lấy mẫu.
D. Những replica nào có certificate issuer sắp hết hạn.
Đáp án đúng: C

Câu 17. Thread dump có nhiều luồng BLOCKED trên cùng monitor thường gợi ý gì?
A. CPU request của pod tự động được Kubernetes tăng.
B. Thread đang chờ DNS lookup trả về địa chỉ của upstream.
C. Heap đã được giải phóng hết sau khi chạy full GC.
D. Tranh chấp synchronized lock đang hạn chế thực thi.
Đáp án đúng: D

Câu 18. Executor queue ngày càng dài nhưng worker thread đều bận nên kiểm tra gì?
A. Chỉ thời hạn certificate TLS của HTTP client.
B. Chỉ thời điểm xoay vòng access log ở gateway.
C. Chỉ độ dài JSON response của một endpoint bất kỳ.
D. Xem thời gian task và số worker của executor.
Đáp án đúng: D

Câu 19. CPU sử dụng thấp nhưng iowait cao và truy vấn chậm có thể chỉ ra gì?
A. Các tác vụ đang chờ I/O thay vì bận tính toán CPU.
B. Tất cả CPU core đều bị giới hạn bởi cgroup quota.
C. Ứng dụng đã đạt throughput tối đa do CPU saturation.
D. Latency cao vì số lượng certificate TLS quá nhiều.
Đáp án đúng: A

Câu 20. Trong container, CPU throttling cao dù có demand lớn thường liên quan gì?
A. Bộ nhớ đệm filesystem không có trang nào được đọc.
B. CPU limit của cgroup đang giới hạn thời gian thực thi process.
C. Readiness probe đang trả HTTP 200 quá thường xuyên.
D. Database connection pool có nhiều kết nối rảnh.
Đáp án đúng: B

Câu 21. Pod bị OOMKilled còn node chưa hết RAM. Điều gì nên kiểm tra trước?
A. Chỉ thời gian DNS resolver giữ cache của node.
B. Chỉ mã HTTP cuối cùng do ingress trả cho client.
C. Chỉ tổng bộ nhớ RAM đã lắp trên toàn cluster.
D. Memory limit của container và mức đỉnh sử dụng.
Đáp án đúng: D

Câu 22. Truy vấn SQL chậm hơn sau tăng dữ liệu, nên phân tích gì?
A. Chỉ số lượng thread của ứng dụng frontend.
B. Xem execution plan, actual rows và thống kê của optimizer.
C. Chỉ kích thước bundle JavaScript phía browser.
D. Chỉ thời gian cấp phát IP của pod trong cluster.
Đáp án đúng: B

Câu 23. DB có lock wait tăng nhưng CPU còn thấp: hướng điều tra nào phù hợp?
A. Tìm transaction giữ khóa lâu và session đang chờ.
B. Xóa index trên bảng trước khi đọc thông tin lock.
C. Tăng CPU limit mọi pod trước khi kiểm tra transaction.
D. Đổi toàn bộ SELECT thành SELECT * để đọc nhanh hơn.
Đáp án đúng: A

Câu 24. Active connection trong pool chạm max và pending tăng liên tục gợi ý gì?
A. Database đã phản hồi mọi request không còn hàng đợi.
B. Client đều đang nhận cache hit nên không dùng DB.
C. Pool có dư nhiều kết nối rảnh và nên hạ max xuống.
D. Pool có thể bão hòa hoặc connection bị giữ quá lâu.
Đáp án đúng: D

Câu 25. ORM phát sinh một query cho danh sách rồi thêm query mỗi phần tử là gì?
A. Phân trang keyset giúp bỏ qua nhiều hàng không cần.
B. Cache stampede gây đồng loạt tính lại một mục dữ liệu.
C. Mẫu N+1 queries gây nhiều lượt round-trip tới database.
D. Transaction isolation làm mọi SELECT chờ commit.
Đáp án đúng: C

Câu 26. Disk await và queue depth tăng theo truy vấn báo cáo nên xem gì?
A. Chỉ trạng thái role binding trên API server.
B. Chỉ số lượng cookie đang lưu trong trình duyệt client.
C. Chỉ độ dài tên bảng trong câu SQL báo cáo.
D. Khối lượng I/O, kiểu scan và mức bão hòa thiết bị.
Đáp án đúng: D

Câu 27. Lỗi chỉ xảy ra khi resolver DNS chậm, nên thu thập chứng cứ gì?
A. Chỉ số lượng heap object được tạo ở backend.
B. Chỉ tổng số request hoàn tất thành công trong ngày.
C. Đo DNS lookup, lỗi phân giải và cấu hình resolver.
D. Chỉ CPU profiling của luồng đang parse JSON response.
Đáp án đúng: C

Câu 28. TCP retransmissions tăng cùng latency giữa hai service gợi ý điều gì?
A. Chắc chắn có deadlock ở transaction database.
B. Mất gói trên đường truyền cần kiểm chứng thêm.
C. Chắc chắn toàn bộ request gặp lỗi xác thực JWT.
D. Chắc chắn heap của mỗi JVM vượt memory limit.
Đáp án đúng: B

Câu 29. Khi TLS handshake lỗi sau khi đổi certificate, nên kiểm tra gì?
A. Chỉ số bản ghi đã insert vào bảng audit.
B. Chỉ thông số cache hit ratio trên reverse proxy.
C. Chỉ số lượng pod readiness false trong namespace.
D. Kiểm tra chain cert, hostname và trust store.
Đáp án đúng: D

Câu 30. Gateway báo p95 cao nhưng upstream service xử lý nhanh: nên đo thêm gì?
A. Chỉ thời gian chạy GC trong database server.
B. Đo queue, thời gian mở kết nối, TLS và buffering tại gateway.
C. Chỉ số truy vấn ghi trung bình của một replica.
D. Chỉ thời gian lưu log của thư viện trong backend.
Đáp án đúng: B

Câu 31. HTTP 504 xuất hiện ở gateway còn backend vẫn có log xử lý muộn. Điều gì hợp lý?
A. Upstream vượt deadline của gateway mà vẫn chạy tiếp.
B. Gateway đã từ chối vì client không có quyền truy cập.
C. Backend trả 200 cho client trước khi kết nối được mở.
D. Gateway bỏ qua timeout vì request đã có trace ID.
Đáp án đúng: A

Câu 32. Mất gói chỉ xảy ra giữa hai zone: cách khoanh vùng nào tốt?
A. So RTT, retransmit và tuyến mạng theo từng zone.
B. Chỉ xem một trace thành công không đi qua hai zone.
C. Chỉ tăng timeout toàn hệ trước khi đo đường truyền.
D. Chỉ xem tổng CPU usage của một node ngẫu nhiên.
Đáp án đúng: A

Câu 33. Pod liên tục CrashLoopBackOff: bước chẩn đoán nào hữu ích?
A. Chỉ sửa Service type từ ClusterIP thành NodePort.
B. Chỉ xóa liveness probe rồi xem sự cố đã hết.
C. Đọc last termination, previous logs và pod events.
D. Chỉ tăng replica count mà bỏ qua nguyên nhân crash.
Đáp án đúng: C

Câu 34. Pod ở trạng thái Pending lâu: cần xem bằng chứng nào?
A. Xem Kubernetes events, resource requests và taints của pod.
B. Chỉ access log từ Ingress vì pod chưa có container.
C. Chỉ tỷ lệ HTTP 200 của service khác cùng namespace.
D. Chỉ heap histogram JVM của pod đang Pending.
Đáp án đúng: A

Câu 35. Readiness probe thất bại nhưng liveness thành công có ý nghĩa gì?
A. Container luôn bị OOMKilled nếu readiness không đạt.
B. Pod còn chạy nhưng readiness loại pod khỏi endpoint phục vụ.
C. Pod chắc chắn đã dừng process và cần restart tức thì.
D. Kubernetes sẽ tự xóa Deployment khi readiness thất bại.
Đáp án đúng: B

Câu 36. Muốn xem log container ở lần chạy trước sau restart, dùng lệnh nào?
A. kubectl top pod --previous để xem stack trace cũ.
B. kubectl rollout history --previous để xem log container cũ.
C. kubectl logs <pod> --previous để xem lần chạy trước.
D. kubectl get service --previous để xem request cũ.
Đáp án đúng: C

Câu 37. Container bị giới hạn CPU thường xuyên: metric nào giúp phân biệt demand và throttling?
A. Chỉ số lượng HTTP 404 và kích thước response.
B. Chỉ số lượng PVC và dung lượng đĩa đã cấp.
C. CPU usage với throttled periods từ cgroup.
D. Chỉ số Pod IP được phân bổ từ CNI plugin.
Đáp án đúng: C

Câu 38. Khi nhiều service đồng loạt lỗi sau thay đổi DNS, nên lập timeline thế nào?
A. Chỉ xem thứ tự của các service trong dashboard.
B. Chỉ dùng sự kiện alert xuất hiện đầu tiên làm nguyên nhân.
C. Chỉ lấy thời gian ứng dụng cuối cùng được build.
D. So mốc đổi DNS, lỗi resolver và trace liên quan.
Đáp án đúng: D

Câu 39. Để kiểm định giả thuyết lock contention là nguyên nhân p99 cao, nên làm gì?
A. Đối chiếu lock wait, trace chậm và tác động sau giảm tranh chấp.
B. Chỉ xem một lần truy vấn nhanh nhất trên môi trường dev.
C. Chỉ khởi động lại DB mà không ghi nhận chỉ số trước sau.
D. Chỉ tăng số connection pool để chứng minh nút thắt đã hết.
Đáp án đúng: A

Câu 40. Sau khi khắc phục sự cố, tiêu chí xác minh nào đáng tin cậy nhất?
A. Chỉ xem một request nhanh bất kỳ đã nhận HTTP 200.
B. So latency, lỗi và mức bão hòa dưới tải so sánh.
C. Chỉ xác nhận dashboard đổi màu cảnh báo sang xanh.
D. Chỉ xác nhận phiên bản ứng dụng mới đã được deploy.
Đáp án đúng: B
