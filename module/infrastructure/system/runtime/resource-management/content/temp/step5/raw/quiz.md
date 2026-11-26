Một dịch vụ Java trong container có CPU gần quota nhưng throughput giảm và độ trễ tăng. Chỉ số nào giúp phân biệt CPU-bound với CPU throttling?
A. CPU user/system cùng số runnable thread của JVM
B. Cgroup throttled time cùng CPU usage của JVM
C. GC CPU time cùng tỷ lệ safepoint theo tải
D. Load average của node và context switch của process
Đáp án đúng: B

Heap JVM ổn định nhưng RSS của process tăng liên tục khi tải xử lý dữ liệu nhị phân tăng. Nhóm chỉ số nào nên kiểm tra trước?
A. Heap allocation rate và occupancy sau GC
B. Metaspace usage cùng số class loader
C. Direct buffer và native memory metrics
D. Thread stack usage và native thread count
Đáp án đúng: C

Sau mỗi đợt tải, heap usage tăng rồi giảm khi GC chạy, nhưng mức heap còn sống sau GC tăng dần qua nhiều giờ. Bằng chứng nào phù hợp nhất để điều tra leak?
A. So sánh tổng số byte cấp phát giữa hai khoảng tải
B. Theo dõi số lần minor GC trong mỗi phút
C. Retained heap sau GC và đường tham chiếu tới GC root
D. Theo dõi số object cấp phát theo lớp trong thời gian tải
Đáp án đúng: C

Một thread pool có queue tăng liên tục trong khi worker đều bận và latency tăng. Thay đổi nào kiểm soát tài nguyên tốt nhất?
A. Tăng queue không giới hạn để tránh từ chối request
B. Tạo thread mới cho mỗi request đang chờ xử lý
C. Tăng timeout của caller để queue có thêm thời gian
D. Giới hạn queue, từ chối sớm hoặc backpressure
Đáp án đúng: D

Một tiến trình lâu ngày chạm giới hạn mở file dù heap và CPU bình thường. Cách kiểm tra nào xác định đúng loại tài nguyên bị rò rỉ?
A. Đếm FD process và phân loại handle đang mở
B. Theo dõi số thread và native stack theo thời gian
C. Đối chiếu socket state và connection pool usage
D. Đo heap occupancy cùng tốc độ cấp phát object
Đáp án đúng: A

Một API mở nhiều kết nối TCP đến dịch vụ bên ngoài; số socket ở CLOSE_WAIT tăng theo thời gian. Hướng điều tra nào phù hợp nhất?
A. Theo dõi số socket theo peer và tuổi kết nối
B. Đối chiếu TIME_WAIT với tốc độ mở kết nối
C. Kiểm tra nơi ứng dụng không đóng socket
D. Kiểm tra retransmission và lỗi connect trên network
Đáp án đúng: C

Request thường chờ lâu trước khi lấy được kết nối database dù truy vấn sau khi có kết nối khá nhanh. Nhóm chỉ số nào xác định đúng nút nghẽn?
A. Query execution time và lock wait trong database
B. Database CPU cùng số active transaction
C. Network round-trip và socket state tới database
D. Pool active/idle, pending và acquire latency
Đáp án đúng: D

Một ứng dụng dùng buffer pool để xử lý luồng dữ liệu; bộ nhớ sử dụng tăng sau mỗi batch dù số request ổn định. Cần kiểm tra điều gì?
A. Tăng kích thước buffer để giảm số lần cấp phát mới
B. Chuyển toàn bộ buffer sang heap để GC thu hồi nhanh hơn
C. Tăng số worker để mỗi buffer được xử lý trong thời gian ngắn
D. Đảm bảo buffer được trả lại pool sau mỗi batch
Đáp án đúng: D

Một request gọi qua nhiều dịch vụ phụ thuộc; đôi khi kết nối được nhưng response không bao giờ hoàn tất. Cách đặt timeout nào an toàn nhất?
A. Connect/read timeout cùng deadline tổng request
B. Chỉ đặt timeout cho kết nối đầu tiên đến dịch vụ đích
C. Đặt một timeout rất dài để tránh hủy request đang xử lý
D. Dùng cùng một timeout vô hạn cho mọi loại thao tác I/O
Đáp án đúng: A

Một worker đọc file rồi gọi xử lý mạng; khi có exception, file handle và socket đôi khi vẫn bị giữ. Cách quản lý vòng đời nào đúng?
A. Đóng tài nguyên khi JVM thực hiện lần garbage collection tiếp theo
B. Dùng try-with-resources hoặc cơ chế tương đương
C. Chỉ đóng tài nguyên khi toàn bộ worker pool dừng hoạt động
D. Tăng giới hạn file descriptor để giảm ảnh hưởng của handle bị giữ
Đáp án đúng: B

Một dịch vụ có allocation rate cao nhưng heap sau GC trở về mức ổn định. Kết luận nào hợp lý nhất?
A. Đây là memory leak vì tổng số byte đã cấp phát tăng liên tục
B. Đây là thread leak vì GC phải xử lý nhiều object tạm thời
C. Đây là native memory leak vì heap sau GC không giảm về zero
D. Allocation cao chưa đủ kết luận leak nếu heap sau GC ổn định
Đáp án đúng: D

Heap còn nhiều dung lượng nhưng direct memory tăng dần và cuối cùng phát sinh lỗi cấp phát buffer. Cần tập trung vào đâu?
A. Heap histogram để tìm object buffer còn được giữ
B. Metaspace usage và class unloading theo thời gian
C. Native thread stack cùng PID limit của container
D. Direct buffer pool cùng các tham chiếu còn giữ buffer
Đáp án đúng: D

Số thread của JVM tăng đều sau mỗi đợt xử lý và không giảm về mức nền. Bằng chứng nào hữu ích nhất?
A. Heap histogram và tỷ lệ object sống sau full GC
B. Thread count theo thời gian kết hợp thread dump và tên nhóm thread
C. Số file descriptor cùng tỷ lệ socket ở trạng thái ESTABLISHED
D. CPU utilization và số lần context switch của từng container
Đáp án đúng: B

Một container tạo quá nhiều platform thread và bị lỗi không thể tạo thread mới dù heap còn trống. Yếu tố nào cần xem xét?
A. Heap headroom và allocation rate của ứng dụng
B. Metaspace usage cùng số class đang được nạp
C. Stack mỗi thread và giới hạn PID hệ điều hành
D. File descriptor limit và số socket đang mở
Đáp án đúng: C

JVM chạy trong container có memory limit 2 GiB. Cách đặt Xmx nào phản ánh đúng ngân sách bộ nhớ?
A. Đặt Xmx bằng toàn bộ 2 GiB vì heap là vùng duy nhất JVM dùng
B. Chừa ngân sách cho metaspace, thread stack, direct và native memory
C. Đặt Xms bằng 2 GiB và để phần native memory vượt giới hạn container
D. Chỉ theo dõi heap used vì RSS không liên quan đến giới hạn container
Đáp án đúng: B

Pod có CPU request thấp và CPU limit cố định; khi nhiều workload cùng node, latency tăng dù ứng dụng không đổi. Chỉ số nào giải thích rõ nhất?
A. Process CPU usage và số runnable thread
B. Node load average cùng run queue length
C. Cgroup throttling và process CPU usage
D. GC CPU time và tỷ lệ safepoint của JVM
Đáp án đúng: C

Một dịch vụ dùng database có giới hạn connection thấp; nhóm vận hành muốn tăng pool size để giảm thời gian chờ. Nguyên tắc nào nên dẫn dắt lựa chọn?
A. Đặt pool bằng số request tối đa để không request nào phải chờ
B. Cân đối pool với năng lực database và mức đồng thời thực tế
C. Đặt pool bằng số thread của JVM để mọi thread có connection riêng
D. Tăng pool đến khi số connection idle luôn bằng không trong giờ cao điểm
Đáp án đúng: B

Một API nhận burst lớn và hàng đợi xử lý tăng nhanh hơn tốc độ worker tiêu thụ. Thiết kế nào tránh tích lũy bộ nhớ không giới hạn?
A. Bounded queue, giới hạn dung lượng và rejection
B. Dùng unbounded queue để giữ mọi request đến khi worker rảnh
C. Tăng timeout queue để request chờ lâu hơn trước khi bị hủy
D. Lưu mọi request đang chờ vào heap rồi tăng Xmx khi cần
Đáp án đúng: A

Một ứng dụng gọi ba dịch vụ phụ thuộc; dịch vụ báo cáo chậm làm cạn toàn bộ worker và ảnh hưởng cả chức năng đăng nhập. Kiến trúc nào giảm lan truyền nghẽn?
A. Dùng chung một pool lớn để các chức năng chia sẻ worker
B. Tăng retry cho dịch vụ báo cáo để nhanh chóng lấy lại phản hồi
C. Tách pool và concurrency budget theo dependency
D. Tăng timeout chung để mọi chức năng có thêm thời gian hoàn tất
Đáp án đúng: C

Một endpoint xử lý ảnh cần giới hạn tối đa 20 tác vụ đồng thời dù có nhiều request đến. Cơ chế nào thể hiện giới hạn này trực tiếp?
A. Semaphore giới hạn in-flight và trả permit đúng lúc
B. Rate limit số request trong mỗi khoảng thời gian
C. Fixed worker pool nhưng queue không giới hạn
D. Giới hạn connection pool theo số kết nối tối đa
Đáp án đúng: A

Một pipeline reactive nhận dữ liệu nhanh hơn downstream có thể xử lý. Cách nào thể hiện backpressure đúng?
A. Propagate demand và giới hạn số phần tử phát ra
B. Tạo buffer lớn dần cho đến khi downstream bắt kịp tốc độ
C. Tăng số thread ở upstream mỗi khi queue vượt ngưỡng
D. Retry mọi phần tử chưa xử lý cho đến khi có kết quả
Đáp án đúng: A

Một dịch vụ gần chạm giới hạn CPU và queue đã đầy; request ưu tiên thấp tiếp tục làm request quan trọng timeout. Cơ chế nào phù hợp?
A. Tăng retry cho tất cả request để tận dụng thời gian còn lại
B. Tăng queue và giữ mọi request cho đến khi CPU rảnh
C. Tăng timeout đồng loạt để giảm số lỗi trả về cho client
D. Load shedding để từ chối sớm request ít ưu tiên
Đáp án đúng: D

Một dependency thường xuyên timeout; client tự retry nhiều lần khiến lưu lượng tăng mạnh đúng lúc dependency đang quá tải. Cách nào giảm retry storm?
A. Giới hạn số retry, exponential backoff và jitter trong ngân sách retry
B. Retry ngay lập tức để tận dụng mọi khoảng trống của dependency
C. Tăng số worker và số connection cho mọi lần retry tiếp theo
D. Đặt timeout dài hơn nhưng vẫn retry không giới hạn khi lỗi
Đáp án đúng: A

Một dịch vụ phụ thuộc liên tục trả lỗi; ứng dụng vẫn gửi request mới và tiêu tốn worker chờ timeout. Cơ chế nào giúp tạm ngừng gọi dependency?
A. Circuit breaker mở theo ngưỡng, half-open có kiểm soát
B. Connection pool tăng kích thước khi số request lỗi tăng lên
C. Retry mọi request với cùng thời gian chờ cố định
D. Cache tất cả response lỗi vô thời hạn để không gọi lại
Đáp án đúng: A

Sau khi thay đổi workload, latency tăng theo từng đợt GC và request timeout xuất hiện thành cụm. Bộ chỉ số nào nên đối chiếu?
A. GC count cùng heap committed trong mỗi khoảng đo
B. GC pause, allocation rate và heap sau GC
C. Metaspace usage và số class loader tồn tại
D. CPU throttling và số lần container restart
Đáp án đúng: B

CPU tăng nhưng chưa rõ do allocation, lock contention hay xử lý tính toán. Công cụ nào cung cấp bằng chứng ở mức runtime?
A. Heap dump để liệt kê object còn sống tại một thời điểm
B. GC log để xem thời điểm và nguyên nhân thu hồi bộ nhớ
C. JFR cho CPU, allocation và lock events
D. Thread count để đếm số luồng được tạo trong tiến trình
Đáp án đúng: C

Một heap dump lớn được thu thập sau khi heap tăng bất thường. Phân tích nào giúp tìm object giữ nhiều bộ nhớ nhất?
A. Heap histogram theo số lượng object từng lớp
B. GC log về heap occupancy trước và sau collection
C. Dùng dominator tree, retained size và đường dẫn tới GC roots
D. JFR allocation profile theo class và call site
Đáp án đúng: C

RSS tăng trong khi heap và metaspace tương đối ổn định. Nhóm công cụ nào phù hợp để phân rã native memory theo loại cấp phát?
A. NMT cùng RSS để phân loại native memory
B. Heap dump và histogram để tìm retained objects
C. JFR allocation events cùng class histogram
D. Thread dump và stack usage theo thread
Đáp án đúng: A

Một dịch vụ tạo file tạm cho mỗi request; sau lỗi xử lý, các file vẫn còn và dung lượng volume tăng. Biện pháp nào xử lý đúng vòng đời?
A. Tăng dung lượng volume để giữ file lỗi lâu hơn
B. Chuyển file tạm sang thư mục log để tiện theo dõi
C. Xóa file theo lịch cố định mà không xét job còn hoạt động
D. Cleanup khi xong hoặc lỗi, TTL dọn file mồ côi
Đáp án đúng: D

Connection pool thường trả về socket đã bị server đóng sau thời gian idle dài. Cấu hình nào giải quyết phù hợp nhất?
A. Tăng pool size để luôn có kết nối thay thế sẵn sàng
B. Tắt timeout để connection không bị loại khỏi pool
C. Max lifetime cùng kiểm tra kết nối idle
D. Giảm số worker để mọi connection được giữ lâu hơn
Đáp án đúng: C

Một service xử lý message bằng buffer pool; khi tăng throughput, direct memory vượt ngân sách. Tham số nào cần được quản lý cùng nhau?
A. Heap Xmx, metaspace max và số class loader đang tồn tại
B. Số thread, stack size và thời gian chờ monitor
C. Pool connection, query timeout và số socket outbound
D. Buffer size, số buffer đồng thời và direct memory cap
Đáp án đúng: D

Một workload không tin cậy chạy chung node với dịch vụ quan trọng. Cách nào đặt giới hạn tài nguyên ở cấp hệ điều hành/container?
A. Chỉ đặt Xmx và để CPU, PID cùng file descriptor không giới hạn
B. Chỉ đặt timeout request và theo dõi heap sau mỗi lần GC
C. Tăng số worker để workload hoàn tất trước khi dùng hết tài nguyên
D. Cgroup CPU/memory, PID controller và ulimit nofile
Đáp án đúng: D

Một ứng dụng cần dừng phiên bản cũ khi triển khai mới nhưng vẫn phải hoàn tất request đang chạy. Trình tự nào phù hợp?
A. Kill process ngay rồi để client tự gửi lại mọi request
B. Ngừng nhận mới, drain request rồi đóng tài nguyên
C. Xóa queue trước khi thông báo worker ngừng nhận công việc
D. Đóng database pool trước khi hoàn tất các request hiện tại
Đáp án đúng: B

Một dịch vụ nghi có leak socket và file handle chỉ xuất hiện sau nhiều giờ. Cách kiểm thử nào cho bằng chứng tốt?
A. Chạy một request đơn lẻ rồi kiểm tra heap ngay sau khi trả kết quả
B. So mức tài nguyên sau cleanup qua nhiều chu kỳ tải
C. Tăng giới hạn handle rồi xác nhận dịch vụ không còn báo lỗi
D. Chạy benchmark CPU ngắn và so sánh throughput giữa hai lần
Đáp án đúng: B

Một nền tảng đa tenant có tenant tạo burst request lớn và chiếm phần lớn worker. Chính sách nào cải thiện fairness?
A. Quota cùng concurrency budget theo từng tenant
B. Dùng một queue chung không giới hạn để mọi tenant được chờ như nhau
C. Cấp pool riêng bằng nhau cho từng tenant bất kể mức sử dụng
D. Ưu tiên tenant có nhiều request nhất để giảm queue tổng thể
Đáp án đúng: A

Trong sự cố latency tăng, nhóm vận hành chỉ xem CPU và heap tổng thể nên chưa tìm được nút nghẽn. Cách quan sát nào hữu ích hơn?
A. Chỉ tăng tần suất scrape CPU và bỏ qua số liệu tài nguyên khác
B. Kết hợp CPU, GC, thread, FD, socket, pool pending và trace latency
C. Chỉ chụp heap dump mỗi phút để theo dõi mọi loại tài nguyên
D. Theo dõi số request tổng và số lần deploy trong cùng khoảng thời gian
Đáp án đúng: B
