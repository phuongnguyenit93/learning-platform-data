1. Một ứng dụng cần Servlet, CDI, JPA, JTA và JMS được triển khai trên nền tảng nào phù hợp nhất?
A. Servlet container cung cấp web runtime; CDI, JPA và messaging được bổ sung riêng.
B. Reverse proxy chỉ định tuyến HTTP; component và transaction do ứng dụng tự quản lý.
C. Application server tích hợp dịch vụ Jakarta EE và quản lý tài nguyên dùng chung.
D. JVM cùng thư viện đóng gói trong WAR tự triển khai naming, messaging và transaction.
Đáp án đúng: C

2. Khi chọn bản Jakarta EE cho một ứng dụng, tổ hợp tương thích nào cần được xác minh trước?
A. Phiên bản Jakarta EE, JDK và tập API mà server hỗ trợ đồng thời.
B. Khớp JDK và Jakarta EE API, rồi giả định server hỗ trợ đủ mọi API.
C. Chọn bản server mới nhất, sau đó dùng JDK của máy phát triển để build.
D. Chỉ đối chiếu database driver và HTTP protocol mà load balancer đang dùng.
Đáp án đúng: A

3. Trong mô hình đóng gói Jakarta EE, lựa chọn nào mô tả đúng vai trò của WAR và EAR?
A. EAR là web deployment unit; WAR tổng hợp EJB, client và resource adapter.
B. WAR đóng gói web module; EAR có thể gom nhiều module ứng dụng.
C. WAR và EAR có thể thay thế nhau vì context root quyết định loại module.
D. EAR chỉ giữ descriptor; từng module bên trong luôn phải deploy độc lập.
Đáp án đúng: B

4. Một ứng dụng chuyển từ Java EE cũ sang Jakarta EE mới gặp lỗi namespace khi triển khai; cần xử lý gì?
A. Cập nhật import, dependency và descriptor sang namespace Jakarta tương thích.
B. Chỉ nâng server lên bản Jakarta EE mới vì server sẽ tự đổi namespace javax lúc deploy.
C. Giữ import javax rồi thêm Jakarta API vào dependency để server tự chọn.
D. Chỉ đổi package trong source; descriptor và thư viện cũ vẫn dùng nguyên.
Đáp án đúng: A

5. Hai ứng dụng cần các phiên bản thư viện khác nhau trên WildFly; cơ chế nào giúp cô lập dependency?
A. Đặt thư viện vào module dùng chung để mọi deployment tự nhận cùng một bản tương thích.
B. Dùng thread context classloader chung để mọi ứng dụng thấy cùng dependency.
C. Chỉ đổi tên file JAR để tránh trùng lặp mà không cần chỉnh module graph.
D. Khai báo module dependency và kiểm soát class visibility của từng deployment.
Đáp án đúng: D

6. Sau redeploy, ứng dụng phát sinh NoSuchMethodError dù thư viện có mặt; bước điều tra nào phù hợp nhất?
A. Kiểm tra classpath runtime cùng module visibility trước khi đổi mã ứng dụng.
B. Đổi JDK patch level vì lỗi liên kết thường do runtime không hỗ trợ bytecode.
C. Xóa cache build để buộc server dùng class đã biên dịch mới.
D. Đối chiếu class thực tế được nạp, phiên bản dependency và thứ tự phân giải.
Đáp án đúng: D

7. Đội vận hành muốn triển khai artifact bất biến qua CI/CD trên nhiều môi trường; cách nào phù hợp nhất?
A. Dùng deployment scanner theo dõi thư mục rồi đồng bộ archive build riêng cho từng môi trường.
B. Dùng management CLI hoặc API và kiểm tra trạng thái deployment sau triển khai.
C. Chỉnh file WAR theo từng môi trường trước khi chép vào thư mục deployments.
D. Để từng node tự tải bản mới nhất từ URL mutable khi server khởi động.
Đáp án đúng: B

8. Một node mở cổng HTTP nhưng datasource chưa kết nối được; readiness check nên trả kết quả nào?
A. Đánh dấu sẵn sàng ngay khi JVM và socket HTTP đã khởi động thành công.
B. Chỉ kiểm tra process và socket HTTP vì readiness không nên phụ thuộc datasource.
C. Chưa nhận traffic cho đến khi các dependency thiết yếu của ứng dụng sẵn sàng.
D. Dựa vào deployment success trên console mà không kiểm tra dependency runtime.
Đáp án đúng: C

9. Trong CDI, scope nào phù hợp để giữ dữ liệu riêng cho một HTTP request?
A. Session scope giữ bean qua nhiều request của cùng một người dùng đăng nhập.
B. Request scope gắn vòng đời bean với request HTTP hiện tại.
C. Application scope chia sẻ bean instance cho mọi request trong ứng dụng.
D. Dependent scope giữ bean đến khi toàn bộ application server dừng hoạt động.
Đáp án đúng: B

10. Một EJB xử lý nhiều request độc lập và không giữ trạng thái hội thoại giữa các lần gọi; loại nào phù hợp?
A. Stateful session bean lưu conversational state riêng cho từng client qua các lần gọi.
B. Singleton session bean tạo instance mới cho mỗi request để tránh chia sẻ state.
C. Stateless session bean được container quản lý và có thể dùng qua pool instance.
D. Message-driven bean nhận lời gọi đồng bộ từ servlet và trả kết quả ngay.
Đáp án đúng: C

11. Một quy trình cần giữ trạng thái hội thoại qua nhiều lần gọi EJB của cùng client; lựa chọn nào phù hợp?
A. Stateful session bean duy trì conversational state theo phiên làm việc.
B. Stateless session bean giữ trạng thái client trong một instance bất kỳ của pool.
C. Singleton session bean tạo bản sao trạng thái riêng cho từng client kết nối.
D. Message-driven bean lưu hội thoại theo HTTP session của người gọi.
Đáp án đúng: A

12. Trong Jakarta Persistence, persistence context chủ yếu đảm nhiệm chức năng nào?
A. Theo dõi identity, lifecycle và thay đổi của các entity đang được quản lý.
B. Lưu bản sao dữ liệu bền vững trên mọi node application server trong cluster.
C. Thay thế datasource pool và quản lý socket tới database cho ứng dụng.
D. Đồng bộ entity giữa các tenant mà không cần transaction hoặc flush.
Đáp án đúng: A

13. Một entity cần được quản lý qua nhiều transaction trong một hội thoại dài; lựa chọn nào phù hợp?
A. Transaction-scoped persistence context luôn tồn tại đến khi server dừng và chia sẻ qua mọi request.
B. Shared cache cấp hai giữ entity managed qua mọi transaction và mọi request.
C. Entity detached tự duy trì dirty checking cho đến khi ứng dụng undeploy.
D. Extended persistence context có thể tồn tại qua ranh giới nhiều transaction.
Đáp án đúng: D

14. Khi một nghiệp vụ phối hợp cập nhật database và gửi message qua nhiều resource manager, loại transaction nào phù hợp?
A. Local transaction chỉ quản lý một resource manager trong một kết nối JDBC.
B. Read-only transaction đồng bộ commit database và broker sau khi xử lý xong.
C. JTA điều phối transaction giữa các tài nguyên được enlist tham gia.
D. Container transaction chỉ bao phủ database và không enlist JMS session.
Đáp án đúng: C

15. Trong XA two-phase commit, transaction coordinator thực hiện trình tự nào?
A. Commit từng resource độc lập rồi mới đối chiếu kết quả của toàn giao dịch.
B. Rollback tất cả resource trước khi hỏi từng bên có thể commit hay không.
C. Gửi message trước và bỏ qua trạng thái prepare của database resource.
D. Giai đoạn prepare thu nhận phiếu tham gia trước khi quyết định commit.
Đáp án đúng: D

16. Ứng dụng cập nhật database rồi cần phát sự kiện nhưng không muốn mất event khi publish lỗi; mẫu nào phù hợp?
A. Publish message sau commit rồi ghi event log trong một transaction riêng.
B. Ghi business data và outbox record trong cùng một database transaction.
C. Gửi message trước transaction và xóa message nếu database rollback sau đó.
D. Dùng thread nền gửi event mà không lưu trạng thái chờ trong database.
Đáp án đúng: B

17. Datasource pool thường xuyên quá tải dù database còn khả năng xử lý; yếu tố nào cần xem xét khi đặt pool size?
A. Số worker HTTP tối đa và tỷ lệ request tĩnh trong tổng traffic trên từng node.
B. Mức đồng thời, thời gian giữ connection và giới hạn kết nối của database.
C. Mức đồng thời trung bình, bỏ qua peak load và giới hạn kết nối database.
D. Số lần JNDI lookup mỗi request thay cho thời gian giữ connection.
Đáp án đúng: B

18. Số kết nối đang mượn tăng liên tục và không quay về pool sau request; dấu hiệu nào cần điều tra?
A. Connection leak khi đường xử lý không đóng hoặc trả connection đúng cách.
B. Connection validation chạy quá nhanh nên pool liên tục tạo kết nối thay thế.
C. Statement cache quá nhỏ khiến connection chuyển sang trạng thái đang sử dụng.
D. JNDI lookup nhiều lần làm database giữ socket dù ứng dụng đã trả connection.
Đáp án đúng: A

19. Ứng dụng tra cứu datasource do application server quản lý thông qua cơ chế nào?
A. Đọc trực tiếp file cấu hình database trong thư mục cài đặt của từng deployment.
B. Tạo socket tới database bằng tên class của datasource implementation.
C. Tra cứu logical resource name trong naming service theo cấu hình server.
D. Lấy connection từ HTTP connector dựa trên context path của ứng dụng.
Đáp án đúng: C

20. Trong Jakarta Messaging, mô tả nào phân biệt đúng queue và topic?
A. Queue dùng competing consumers; topic hỗ trợ mô hình publish-subscribe.
B. Queue phát bản sao tới mọi subscriber; topic giao mỗi message cho một consumer.
C. Queue lưu trạng thái transaction; topic chỉ dùng cho message không bền.
D. Queue xử lý đồng bộ; topic bắt buộc gọi consumer bằng HTTP callback.
Đáp án đúng: A

21. Một message bị lỗi nghiệp vụ và liên tục được broker giao lại; cách xử lý vận hành nào phù hợp?
A. Tắt acknowledgement để broker xóa message ngay khi consumer nhận lần đầu.
B. Tăng concurrency không giới hạn để message lỗi được xử lý nhanh hơn.
C. Rollback mọi lần nhận mà không đặt giới hạn retry hoặc phân loại lỗi.
D. Giới hạn redelivery và chuyển message độc hại sang dead-letter queue.
Đáp án đúng: D

22. Một tác vụ nền cần chạy trong môi trường Jakarta EE và sử dụng context do container quản lý; lựa chọn nào phù hợp?
A. Tạo thread toàn cục rồi tự giữ đến khi JVM kết thúc tiến trình.
B. Dùng thread của HTTP connector cho mọi tác vụ nền chạy dài hạn.
C. Dùng managed executor do application server cung cấp và quản lý vòng đời.
D. Khởi chạy process hệ điều hành riêng cho từng tác vụ nhỏ để container không quản lý thread.
Đáp án đúng: C

23. Request latency tăng khi active worker đạt giới hạn và hàng đợi tiếp tục dài ra; hiện tượng nào phù hợp nhất?
A. Thread pool saturation làm request chờ trước khi có worker xử lý.
B. Datasource pool exhaustion khiến worker bị chặn khi chờ connection.
C. GC pause kéo dài làm throughput giảm dù active worker có thể đạt trần.
D. Selector saturation làm request chậm trước khi được chuyển tới worker.
Đáp án đúng: A

24. Điểm khác biệt chính giữa WildFly standalone mode và domain mode là gì?
A. Standalone chỉ chạy web application; domain chỉ chạy ứng dụng xử lý batch.
B. Standalone bắt buộc một JVM; domain bắt buộc một JVM cho toàn cluster.
C. Standalone không hỗ trợ CLI; domain chỉ cấu hình qua console vì thay đổi phải đi qua controller.
D. Standalone quản trị một server độc lập; domain hỗ trợ quản trị tập trung nhiều server.
Đáp án đúng: D

25. Trong WildFly domain mode, server group chủ yếu dùng để làm gì?
A. Nhóm người dùng dùng chung role và quyền truy cập database của tổ chức.
B. Nhóm datasource chia sẻ một connection vật lý cho mọi deployment trong nhóm.
C. Nhóm classloader gom WAR để các ứng dụng dùng chung session và heap.
D. Nhóm server dùng chung profile cấu hình và chính sách triển khai ứng dụng.
Đáp án đúng: D

26. Khi triển khai cùng ứng dụng trên nhiều node, sticky session chủ yếu bảo đảm điều gì?
A. Mọi node đồng bộ tức thời toàn bộ session state qua database dùng chung.
B. Mỗi request được phát đồng thời tới tất cả node trong cluster ứng dụng.
C. Load balancer ưu tiên gửi request tiếp theo về node đang giữ session.
D. Session tồn tại nguyên vẹn ngay cả khi mọi node cùng dừng đột ngột.
Đáp án đúng: C

27. Một cluster cần khôi phục session khi node lỗi; điều kiện nào quan trọng với session replication?
A. Session attribute phải là kết nối JDBC đang mở tới database để node khác tái sử dụng.
B. Session attributes cần tương thích và có thể serialize theo cơ chế replication.
C. Mỗi session phải gắn với một thread cố định trên mọi node trong cluster.
D. Các node phải dùng chung một heap để đọc trực tiếp object của nhau.
Đáp án đúng: B

28. Trong rolling deployment, vì sao cần chú ý tương thích session giữa hai phiên bản ứng dụng?
A. Load balancer chuyển toàn bộ session sang node mới trước khi bắt đầu deploy.
B. Request có thể tới node mới nhưng mang session được tạo bởi phiên bản cũ.
C. Session replication tự chuyển đổi mọi object khi cấu trúc class thay đổi.
D. Servlet container xóa session cũ ngay khi một node bắt đầu shutdown.
Đáp án đúng: B

29. Trong cấu hình TLS của application server, keystore và truststore có vai trò nào?
A. Keystore giữ private key cùng certificate; truststore chứa chứng thư hoặc CA tin cậy.
B. Keystore lưu CA của client; truststore giữ private key và certificate server để xác thực hai chiều.
C. Keystore lưu server certificate; truststore giữ session key được tạo cho mỗi HTTP request.
D. Keystore quản lý password người dùng; truststore quản lý role ứng dụng.
Đáp án đúng: A

30. Console quản trị application server cần được bảo vệ tách biệt với endpoint ứng dụng; cấu hình nào phù hợp?
A. Dùng public listener và dựa vào URL khó đoán cùng TLS để hạn chế truy cập quản trị.
B. Ẩn liên kết console khỏi trang chủ nhưng vẫn mở cổng quản trị công khai.
C. Chỉ bật TLS cho ứng dụng và cho phép management API truy cập ẩn danh.
D. Giới hạn management interface vào mạng quản trị và áp dụng xác thực, phân quyền riêng.
Đáp án đúng: D

31. Người dùng đã xác thực nhưng không được phép gọi chức năng phê duyệt; lớp kiểm soát nào quyết định?
A. Authentication xác minh mật khẩu rồi tự cấp quyền cho mọi nghiệp vụ.
B. Authorization ánh xạ danh tính sang role hoặc permission được phép thực hiện.
C. TLS xác minh certificate server và quyết định quyền phê duyệt giao dịch.
D. Session replication đồng bộ role giữa các node rồi quyết định quyền cho từng thao tác nghiệp vụ.
Đáp án đúng: B

32. Đội vận hành cần biết pool nào gây chậm request; tập metric nào hữu ích nhất?
A. Pool size, số connection được tạo và database CPU theo từng node.
B. Active, idle, pending acquisition và thời gian chờ lấy connection.
C. HTTP request rate, status code và p99 latency của endpoint ứng dụng.
D. Heap usage, GC pause và số worker thread đang hoạt động trên server.
Đáp án đúng: B

33. Thread dump cho thấy nhiều worker chờ cùng một lock và một thread giữ lock lâu; bước phân tích nào phù hợp?
A. Tăng heap vì lock contention có thể xuất hiện cùng các đợt GC pause dài.
B. Xóa datasource rồi tạo pool mới vì monitor lock luôn thuộc database connector.
C. Đối chiếu stack trace, lock owner và nhiều dump theo thời điểm để tìm critical section.
D. Tăng HTTP keep-alive để worker không phải chờ lock trong ứng dụng.
Đáp án đúng: C

34. Sau nhiều lần redeploy, bộ nhớ không giảm và classloader cũ vẫn còn trong heap; nguyên nhân nào thường gặp?
A. Thread nền hoặc static reference còn giữ object thuộc classloader ứng dụng cũ.
B. JNDI name đăng ký một lần khiến bytecode của deployment luôn nằm trong heap.
C. TLS certificate hết hạn khiến class metadata không được garbage collector thu hồi.
D. Connection validation query khiến JVM giữ lại mọi class của ứng dụng cũ.
Đáp án đúng: A

35. Khi cần dừng một node để bảo trì mà không làm rơi request đang chạy, quy trình nào phù hợp?
A. Kill JVM ngay sau khi load balancer đánh dấu node đang bảo trì.
B. Xóa deployment trước rồi chờ client tự gửi lại request đã bị ngắt.
C. Ngừng nhận traffic mới, drain request đang chạy rồi dừng server trong giới hạn chờ.
D. Đóng database trước rồi chờ request đang chạy tự giải phóng connection.
Đáp án đúng: C

36. Phiên bản mới triển khai thành công nhưng tỷ lệ lỗi nghiệp vụ tăng sau vài phút; quyết định rollback nên dựa vào điều gì?
A. Chỉ dựa vào deployment state vẫn báo successful trên management console.
B. Chờ đến khi toàn bộ người dùng báo lỗi rồi mới quyết định rollback phiên bản.
C. Giữ phiên bản mới nếu CPU thấp dù request thất bại tăng và deployment vẫn báo healthy.
D. Ngưỡng health và error rate đã định trước cùng khả năng quay lại artifact tốt.
Đáp án đúng: D
