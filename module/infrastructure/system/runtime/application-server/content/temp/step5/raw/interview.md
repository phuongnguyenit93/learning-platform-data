Bạn phân biệt Java application server với servlet container về phạm vi dịch vụ nền tảng mà ứng dụng được cung cấp như thế nào?
Bạn giải thích kiến trúc Jakarta EE và vai trò của application server trong vòng đời ứng dụng như thế nào?
Bạn lựa chọn phiên bản Jakarta EE và JDK tương thích với WildFly hoặc Payara dựa trên những tiêu chí nào?
Bạn đánh giá tác động của chuyển đổi namespace từ javax sang jakarta khi nâng cấp ứng dụng như thế nào?
Bạn phân biệt các profile hoặc tập tính năng Jakarta EE theo nhu cầu của một ứng dụng ra sao?
Bạn mô tả các thành phần web, business và persistence trong một ứng dụng Jakarta EE được đóng gói như thế nào?
Bạn lựa chọn đóng gói WAR, EJB JAR hoặc EAR theo ranh giới module và yêu cầu triển khai nào?
Bạn xác định trách nhiệm của application server đối với dependency injection, transaction, security và resource management như thế nào?
Bạn giải thích vòng đời deploy, start, stop, undeploy và redeploy của một ứng dụng như thế nào?
Bạn tổ chức cấu hình ứng dụng tách khỏi artifact để cùng một bản build có thể chạy ở nhiều môi trường ra sao?
Bạn kiểm tra khả năng tương thích giữa thư viện ứng dụng và các API do server cung cấp như thế nào?
Bạn lựa chọn cách quản lý thư viện dùng chung và thư viện đóng gói riêng trong ứng dụng như thế nào?
Bạn phân tích cách classloader của application server nạp lớp và cô lập module như thế nào?
Bạn xác định nguyên nhân lỗi ClassNotFoundException, NoClassDefFoundError hoặc LinkageError trong môi trường server ra sao?
Bạn điều tra xung đột phiên bản thư viện khi ứng dụng chạy trên WildFly hoặc Payara như thế nào?
Bạn đánh giá tác động của classloader leak sau nhiều lần redeploy tới bộ nhớ JVM ra sao?
Bạn phân biệt lỗi cấu hình deployment descriptor với lỗi thiếu dependency hoặc API không tương thích như thế nào?
Bạn thiết kế quy trình build và triển khai artifact có thể tái lập giữa development, staging và production ra sao?
Bạn lựa chọn deployment scanner, management CLI, console hoặc API để triển khai ứng dụng theo quy trình nào?
Bạn kiểm tra trạng thái deployment và xác nhận ứng dụng thực sự sẵn sàng phục vụ request bằng cách nào?
Bạn thiết kế chiến lược rolling deployment để giảm gián đoạn khi cập nhật phiên bản ứng dụng như thế nào?
Bạn xác định điều kiện rollback khi phiên bản mới khởi động được nhưng lỗi trong xử lý nghiệp vụ ra sao?
Bạn giải thích CDI container quản lý bean discovery, injection và scope trong Jakarta EE như thế nào?
Bạn phân biệt CDI managed bean với EJB về lifecycle, transaction và các dịch vụ container cung cấp ra sao?
Bạn lựa chọn scope CDI phù hợp cho dữ liệu request, session và application như thế nào?
Bạn xác định nguyên nhân dependency injection thất bại do qualifier, bean discovery hoặc ambiguous resolution ra sao?
Bạn giải thích cách application server quản lý EJB stateless, stateful và singleton như thế nào?
Bạn lựa chọn loại EJB theo trạng thái nghiệp vụ, concurrency và mô hình xử lý request nào?
Bạn đánh giá tác động của transaction attribute và concurrency management lên hành vi EJB ra sao?
Bạn thiết kế ứng dụng Jakarta Persistence với EntityManager và persistence context do container quản lý như thế nào?
Bạn phân biệt transaction-scoped với extended persistence context trong các luồng nghiệp vụ ra sao?
Bạn xác định nguyên nhân lazy loading thất bại khi entity được truy cập ngoài persistence context như thế nào?
Bạn cấu hình JNDI datasource để ứng dụng tra cứu kết nối database do server quản lý ra sao?
Bạn lựa chọn pool size, connection timeout và validation query dựa trên tải ứng dụng và giới hạn database như thế nào?
Bạn phát hiện connection pool exhaustion và phân biệt với database từ chối kết nối như thế nào?
Bạn xác định connection leak từ số kết nối đang dùng, thời gian giữ kết nối và log pool như thế nào?
Bạn đánh giá tác động của statement cache và prepared statement pooling tới hiệu năng ứng dụng ra sao?
Bạn giải thích JTA transaction manager phối hợp giao dịch giữa nhiều tài nguyên như thế nào?
Bạn phân biệt local transaction với JTA transaction khi ứng dụng truy cập một hoặc nhiều resource manager ra sao?
Bạn lựa chọn transaction boundary để tránh giữ kết nối database quá lâu như thế nào?
Bạn xử lý rollback khi một thao tác database thành công nhưng gửi message thất bại ra sao?
Bạn giải thích vai trò của XA resource và two-phase commit trong giao dịch phân tán như thế nào?
Bạn đánh giá trade-off giữa XA transaction và transactional outbox cho tích hợp database với messaging ra sao?
Bạn chẩn đoán transaction timeout, rollback-only và heuristic outcome từ log của server như thế nào?
Bạn xác định nguyên nhân transaction bị treo do lock contention hoặc resource không phản hồi như thế nào?
Bạn cấu hình Jakarta Messaging connection factory và destination trong application server như thế nào?
Bạn phân biệt queue và topic trong messaging theo mô hình consumer và yêu cầu phân phối message ra sao?
Bạn thiết kế MDB hoặc message-driven consumer để xử lý message bất đồng bộ và kiểm soát concurrency như thế nào?
Bạn xác định nguyên nhân message backlog tăng dù consumer đang hoạt động như thế nào?
Bạn xử lý redelivery, retry và dead-letter queue để tránh message lỗi lặp vô hạn ra sao?
Bạn đánh giá tác động của transaction giữa message consumption và cập nhật database tới khả năng xử lý trùng như thế nào?
Bạn cấu hình JNDI naming và tra cứu tài nguyên theo namespace phù hợp giữa ứng dụng và server như thế nào?
Bạn giải thích vai trò của server-managed executors và managed concurrency trong ứng dụng Jakarta EE ra sao?
Bạn lựa chọn ManagedExecutorService hoặc managed scheduled executor thay cho tự tạo thread trong container khi nào?
Bạn xác định rủi ro tạo thread thủ công làm mất context, transaction hoặc lifecycle management như thế nào?
Bạn cấu hình security realm hoặc identity store để xác thực người dùng ứng dụng theo nền tảng triển khai ra sao?
Bạn phân biệt authentication với authorization và cách ánh xạ role ứng dụng sang quyền truy cập tài nguyên như thế nào?
Bạn thiết kế bảo mật endpoint quản trị application server tách biệt với bảo mật ứng dụng như thế nào?
Bạn quản lý secret, keystore và truststore cho kết nối HTTPS hoặc kết nối backend ra sao?
Bạn cấu hình TLS và kiểm tra chứng chỉ, cipher suite cùng hostname verification như thế nào?
Bạn đánh giá nguy cơ chạy console hoặc management API trên mạng công khai và cách giới hạn truy cập ra sao?
Bạn phân biệt cấu hình standalone mode với domain mode trong WildFly hoặc các mô hình quản trị tập trung tương ứng như thế nào?
Bạn tổ chức server group, profile và cấu hình nhiều instance để triển khai các ứng dụng khác nhau ra sao?
Bạn lựa chọn management CLI, administration console hoặc file configuration để quản lý thay đổi theo môi trường như thế nào?
Bạn xác định cách lưu version và review cấu hình server để phát hiện configuration drift ra sao?
Bạn thiết kế clustering và session replication để ứng dụng duy trì phiên khi một node gặp sự cố như thế nào?
Bạn phân biệt load balancing với clustering và session failover trong kiến trúc nhiều application server ra sao?
Bạn lựa chọn sticky session hay session replication dựa trên đặc điểm ứng dụng và yêu cầu khả dụng nào?
Bạn đánh giá giới hạn của distributed session state khi ứng dụng lưu nhiều dữ liệu hoặc object không serialize được như thế nào?
Bạn kiểm tra health check và readiness của từng node trước khi load balancer đưa traffic vào như thế nào?
Bạn xác định hành vi khi một node rời cluster trong lúc đang xử lý request hoặc transaction ra sao?
Bạn thiết kế rolling upgrade cho cluster để duy trì khả năng phục vụ và tương thích session như thế nào?
Bạn theo dõi heap, garbage collection, thread pool và connection pool để đánh giá sức khỏe application server ra sao?
Bạn xác định dấu hiệu thread pool saturation từ active thread, queue length và request latency như thế nào?
Bạn phân tích deadlock hoặc thread starvation từ thread dump khi server phản hồi chậm ra sao?
Bạn xác định memory leak do static reference, application classloader hoặc session state qua heap dump như thế nào?
Bạn phân biệt CPU-bound, lock contention, GC pressure và downstream latency khi response time tăng như thế nào?
Bạn sử dụng server log, access log, metrics và trace để dựng lại luồng một request lỗi như thế nào?
Bạn xác định nguyên nhân deployment thất bại từ server log và trạng thái service thay vì chỉ dựa vào thông báo trên console như thế nào?
Bạn điều tra lỗi datasource, transaction, JMS và security theo thứ tự bằng chứng nào khi ứng dụng khởi động nhưng không xử lý được nghiệp vụ?
Bạn đánh giá tác động của logging level quá chi tiết tới hiệu năng và dung lượng lưu trữ như thế nào?
Bạn thiết kế dashboard và alert cho request rate, error rate, latency, pool utilization và JVM health ra sao?
Bạn lựa chọn cách cấu hình health endpoint để phân biệt tiến trình còn sống với ứng dụng đã sẵn sàng phục vụ như thế nào?
Bạn xác minh nguyên nhân gốc và hiệu quả khắc phục sau khi thay đổi cấu hình hoặc nâng cấp application server bằng phép thử nào?
