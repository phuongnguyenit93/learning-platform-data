Câu 1. Vai trò chính của Hawtio trong hệ sinh thái ứng dụng Java là gì?
A. Quan sát và quản trị ứng dụng Java qua JMX trên web console.
B. Thay thế JVM bằng một tiến trình quản lý chạy ngoài máy chủ.
C. Tạo dashboard nghiệp vụ mà không cần ứng dụng phát dữ liệu.
D. Tự cân bằng tải và điều phối request giữa các service.
Đáp án đúng: A

Câu 2. Trong JMX, một MBean thường cung cấp loại giao diện nào cho công cụ quản trị?
A. Chỉ các HTTP endpoint và JSON schema của ứng dụng.
B. Attributes, operations và có thể cả notifications.
C. Các bảng dữ liệu quan hệ cùng câu lệnh SQL được hỗ trợ.
D. Các route mạng và chính sách firewall của máy chủ.
Đáp án đúng: B

Câu 3. Thành phần JMX nào đăng ký và quản lý các MBean trong một JVM?
A. Jolokia agent lưu toàn bộ MBean vào cơ sở dữ liệu riêng.
B. Hawtio browser trực tiếp tạo MBean trong JVM từ xa.
C. JVM garbage collector quản lý tên và vòng đời mọi MBean.
D. MBeanServer giữ registry và cung cấp quyền truy cập MBean.
Đáp án đúng: D

Câu 4. Một JMX ObjectName thường có cấu trúc nào?
A. Domain kèm tập thuộc tính dạng key=value.
B. URL HTTP gồm scheme, host, path và query string.
C. Tên Java package kèm method và kiểu tham số.
D. Đường dẫn filesystem kèm tên process và PID.
Đáp án đúng: A

Câu 5. Trong ObjectName `java.lang:type=Memory`, phần `type=Memory` biểu thị điều gì?
A. Tên operation mà Hawtio sẽ gọi trên MBean đó.
B. Địa chỉ HTTP mà Jolokia dùng để đọc memory.
C. Tên class Java dùng để khởi chạy ứng dụng.
D. Key property xác định loại MBean thuộc domain.
Đáp án đúng: D

Câu 6. Khi xem một MBean trong Hawtio, thao tác đọc Attribute thường có ý nghĩa nào?
A. Đọc trạng thái hoặc cấu hình do MBean công bố.
B. Gọi một method làm thay đổi trạng thái của ứng dụng.
C. Tạo mới một MBean trong MBeanServer của JVM.
D. Gửi notification tới mọi listener đang đăng ký.
Đáp án đúng: A

Câu 7. Khi người vận hành gọi một operation trên MBean, điều gì xảy ra?
A. MBean thực thi operation với các tham số đã nhận.
B. Jolokia tự tạo một bản sao MBean trong trình duyệt.
C. Hawtio chỉ đọc cache của attribute và không gọi JVM.
D. MBeanServer tự đổi tên ObjectName theo tên operation.
Đáp án đúng: A

Câu 8. JMX notification thường được dùng để biểu diễn loại thông tin nào?
A. Giá trị cấu hình tĩnh được đọc từ mọi MBean mỗi giây.
B. Sự kiện bất đồng bộ do MBean phát tới listener đăng ký.
C. Kết quả truy vấn SQL do Hawtio chạy trên database.
D. Bản sao đầy đủ của heap dump gửi tới browser console.
Đáp án đúng: B

Câu 9. Jolokia đóng vai trò gì khi Hawtio truy cập JMX qua HTTP?
A. Thay thế MBeanServer bằng giao thức quản trị dựa trên SQL.
B. Mã hóa mọi attribute bằng TLS trước khi lưu vào JVM.
C. Cung cấp cầu nối HTTP/JSON tới các thao tác JMX.
D. Tạo dashboard và lưu trữ metric time series cho Hawtio.
Đáp án đúng: C

Câu 10. Một Jolokia read request thường được dùng để làm gì?
A. Gọi operation thay đổi trạng thái của một MBean.
B. Đăng ký MBean mới vào JVM đang được giám sát.
C. Đọc attribute của một MBean được chỉ định.
D. Xóa toàn bộ notification listener của MBeanServer.
Đáp án đúng: C

Câu 11. Một Jolokia exec request thường thực hiện tác vụ nào?
A. Chỉ truy vấn attribute mà không gọi method quản trị.
B. Gọi operation của MBean với các tham số tương ứng.
C. Tạo mới một kết nối TCP tới cổng ứng dụng Java.
D. Xuất toàn bộ log file của JVM sang định dạng JSON.
Đáp án đúng: B

Câu 12. Khi cần tìm các MBean theo mẫu ObjectName, loại thao tác Jolokia nào phù hợp?
A. Search theo ObjectName pattern để liệt kê MBean phù hợp.
B. Exec theo operation name để liệt kê mọi MBean phù hợp.
C. Write theo attribute value để liệt kê mọi MBean phù hợp.
D. Version theo JVM PID để liệt kê mọi MBean phù hợp.
Đáp án đúng: A

Câu 13. Vì sao không nên xem Jolokia endpoint như một API công khai thông thường?
A. Nó chỉ trả về nội dung tĩnh và không thể tác động ứng dụng.
B. Nó chỉ phục vụ health check và không truy cập JMX MBean.
C. Nó có thể phơi bày dữ liệu runtime và thao tác quản trị JVM.
D. Nó tự động giới hạn mọi request vào các phép đọc an toàn.
Đáp án đúng: C

Câu 14. Hawtio hiển thị cây MBean và thuộc tính chủ yếu dựa vào nguồn nào?
A. Metadata JMX mà MBeanServer công bố qua Jolokia.
B. Danh sách Java class được quét từ source repository.
C. OpenAPI schema do controller REST của ứng dụng cung cấp.
D. Bản ghi DNS SRV mà JVM đăng ký khi khởi động.
Đáp án đúng: A

Câu 15. Standard MBean trong JMX thường tuân theo quy ước nào?
A. Implementation phải kế thừa `JolokiaMBean` trong mọi trường hợp.
B. Interface phải được sinh từ OpenAPI trước khi đăng ký.
C. Interface kết thúc bằng `MBean` đi với implementation.
D. Class phải được đánh dấu `@RestController` để JMX nhận diện.
Đáp án đúng: C

Câu 16. Dynamic MBean khác Standard MBean ở điểm nào?
A. Nó chỉ có thể đăng ký trước khi JVM khởi động.
B. Nó không thể công bố operation hoặc attribute cho client.
C. Metadata MBean có thể được cung cấp động lúc chạy.
D. Nó bắt buộc dùng HTTP endpoint thay cho MBeanServer.
Đáp án đúng: C

Câu 17. Platform MBeans của JVM hữu ích để quan sát nhóm thông tin nào?
A. DNS resolver, routing table, TCP sockets và TLS certificates.
B. Database schema, SQL plans, replication lag và row locks.
C. HTTP routes, user sessions, browser cache và cookies.
D. Memory, threads, class loading và garbage collection.
Đáp án đúng: D

Câu 18. MBean `java.lang:type=Memory` cung cấp thông tin nào?
A. Số lượng request HTTP đang chờ trong reverse proxy.
B. Dung lượng đĩa còn trống trên host chạy ứng dụng Java.
C. Heap và non-heap memory usage của JVM.
D. Thời gian phản hồi của mọi endpoint REST trong service.
Đáp án đúng: C

Câu 19. Khi thread count tăng liên tục, MBean nào nên được xem cùng thread dump?
A. MemoryPool MBean để đọc kích thước từng vùng heap.
B. Compilation MBean để xem số lượng class đã nạp.
C. Threading MBean theo dõi số lượng và trạng thái thread.
D. OperatingSystem MBean để đọc địa chỉ IP của từng thread.
Đáp án đúng: C

Câu 20. Thread dump hữu ích nhất khi điều tra loại vấn đề nào?
A. Cardinality cao của Prometheus label theo từng request.
B. DNS cache cũ trên recursive resolver của mạng nội bộ.
C. Chứng chỉ TLS thiếu SAN trong reverse proxy phía trước.
D. Deadlock, thread bị block hoặc pool cạn worker.
Đáp án đúng: D

Câu 21. Heap dump nên được tạo khi nào và cần cân nhắc điều gì?
A. Mỗi khi request latency tăng nhẹ để kiểm tra network route.
B. Trước mọi lần deploy vì dump luôn không ảnh hưởng runtime.
C. Khi muốn xem nội dung HTTP header của client đang kết nối.
D. Khi phân tích memory leak, do dump có thể lớn và nhạy cảm.
Đáp án đúng: D

Câu 22. Khi kết nối Hawtio tới JVM từ xa bằng JMX/RMI, điều gì cần cấu hình đúng?
A. Chỉ URL trang chủ Hawtio mà không cần connector phía JVM.
B. Chỉ tên MBean domain và một HTTP path bất kỳ.
C. JMX service URL, cổng và hostname RMI có thể truy cập.
D. Chỉ cổng debug của JVM mà không cần JMX connector.
Đáp án đúng: C

Câu 23. Vì sao kết nối JMX/RMI từ xa đôi khi cần mở thêm cổng ngoài registry port?
A. JMX luôn chuyển tiếp HTTP qua cổng ngẫu nhiên của browser.
B. Jolokia bắt buộc mở thêm cổng UDP cho từng MBean.
C. Java agent tự tạo một cổng SQL để đọc attribute.
D. RMI có thể trả về cổng server riêng cho phiên kết nối.
Đáp án đúng: D

Câu 24. Khi dùng Jolokia agent gắn trong ứng dụng, Hawtio thường truy cập JMX theo cách nào?
A. Kết nối trực tiếp vào heap memory qua giao thức TCP thô.
B. Đọc file `.class` của MBean từ thư mục triển khai.
C. Truy vấn trực tiếp database mà ứng dụng đang sử dụng.
D. Gọi HTTP endpoint của agent để đọc và gọi MBean.
Đáp án đúng: D

Câu 25. Nếu Hawtio không hiển thị MBean mong đợi, bước kiểm tra nào hợp lý?
A. Khởi động lại browser nhiều lần để tạo lại MBean tự động.
B. Xác minh MBean đã đăng ký và Jolokia được phép truy cập.
C. Đổi tên domain của tất cả MBean trước khi xem lại.
D. Tăng heap JVM vì MBean không xuất hiện do thiếu RAM.
Đáp án đúng: B

Câu 26. Phân biệt authentication và authorization khi bảo vệ Hawtio như thế nào?
A. Authentication quyết định quyền; authorization xác minh danh tính.
B. Authentication xác minh danh tính; authorization quyết định quyền.
C. Cả hai chỉ mã hóa kết nối giữa browser và Jolokia agent.
D. Authentication chỉ áp dụng JMX; authorization chỉ áp dụng HTTP.
Đáp án đúng: B

Câu 27. Vì sao Hawtio console cần được giới hạn truy cập theo least privilege?
A. Quyền quản trị có thể làm đổi trạng thái runtime.
B. Console chỉ đọc thông tin tĩnh nên không có rủi ro quản trị.
C. Jolokia tự chặn mọi operation có thể thay đổi ứng dụng.
D. JMX chỉ cho phép tài khoản hệ điều hành root xem MBean.
Đáp án đúng: A

Câu 28. Khi triển khai Hawtio qua mạng, biện pháp nào bảo vệ dữ liệu quản trị khi truyền?
A. Chỉ đổi port mặc định sang số ngẫu nhiên là đủ an toàn.
B. Dùng HTTPS/TLS và xác thực client hoặc người dùng phù hợp.
C. Chỉ ẩn đường dẫn console khỏi menu điều hướng của website.
D. Chỉ bật CORS wildcard để browser kết nối không bị lỗi.
Đáp án đúng: B

Câu 29. Jolokia access policy nên được cấu hình theo nguyên tắc nào?
A. Chỉ cho phép origin, MBean và command thực sự cần thiết.
B. Cho phép mọi origin và mọi command để tránh lỗi plugin.
C. Chặn mọi lệnh read nhưng cho phép exec không giới hạn.
D. Chỉ kiểm tra tên browser mà không xác thực người dùng.
Đáp án đúng: A

Câu 30. Vì sao nên phân biệt quyền read với write/exec trong JMX console?
A. Read luôn xóa attribute cũ còn exec chỉ xem metadata.
B. Write chỉ đọc trạng thái còn read luôn gọi operation.
C. Write/exec có thể đổi cấu hình hoặc trạng thái runtime.
D. Ba loại quyền có tác động giống nhau trên mọi MBean.
Đáp án đúng: C

Câu 31. Trước khi gọi operation có thể restart hoặc stop service, người vận hành nên làm gì?
A. Xác nhận đúng MBean, tác động và quyền phê duyệt thao tác.
B. Chạy operation trên mọi instance để xem instance nào phản hồi.
C. Ẩn notification để thao tác không xuất hiện trong audit.
D. Thử với tham số bất kỳ rồi hoàn tác nếu có lỗi.
Đáp án đúng: A

Câu 32. Hawtio Camel plugin thường giúp quan sát thành phần nào?
A. Spring Security users, OAuth scopes và JWT signing keys.
B. Camel contexts, routes, endpoints và trạng thái xử lý.
C. Kubernetes nodes, persistent volumes và pod scheduling.
D. Database tables, indexes, replication slots và SQL locks.
Đáp án đúng: B

Câu 33. Khi một Camel route bị dừng ngoài dự kiến, thông tin nào hữu ích để kiểm tra?
A. Chỉ heap size tổng mà không xem log của route.
B. Camel contexts, routes, endpoints và trạng thái.
C. Chỉ cổng RMI của JVM mà không xem route metadata.
D. Chỉ số class đã nạp từ khi process khởi động.
Đáp án đúng: B

Câu 34. Thao tác suspend một Camel route khác stop route ở điểm nào?
A. Suspend tạm ngừng nhận xử lý mới theo cơ chế route.
B. Stop chỉ tạm ngừng nhận xử lý mới nhưng vẫn giữ trạng thái chạy.
C. Suspend xóa route khỏi CamelContext và đăng ký lại sau.
D. Stop chỉ tắt plugin Hawtio mà không tác động route.
Đáp án đúng: A

Câu 35. Thông tin inflight exchanges của Camel route giúp trả lời câu hỏi nào?
A. Có bao nhiêu MBean đã đăng ký trong toàn bộ JVM.
B. Kiểm tra plugin tương thích và Camel MBeans đã expose.
C. Có bao nhiêu user đang đăng nhập vào Hawtio console.
D. Có bao nhiêu class Java được garbage collector thu hồi.
Đáp án đúng: B

Câu 36. Khi Hawtio Camel plugin không hiển thị route, nên kiểm tra điều gì?
A. JMX memory pool đã được đặt giới hạn heap lớn hơn.
B. Trình duyệt đã bật cache cho toàn bộ file JavaScript.
C. JVM đã mở cổng debug và cho phép remote attach.
D. Mở rộng console bằng màn hình quản trị theo công nghệ.
Đáp án đúng: D

Câu 37. Hawtio plugin architecture chủ yếu mang lại khả năng nào?
A. Thay đổi bytecode mọi ứng dụng Java ngay khi đang chạy.
B. Mở rộng console bằng các màn hình quản trị theo công nghệ.
C. Thay thế JMX bằng một database schema dùng chung.
D. Biến mọi MBean thành REST controller mà không cần adapter.
Đáp án đúng: B

Câu 38. Khi vận hành console, log/audit trail của thao tác quản trị có ích gì?
A. Đảm bảo operation luôn thành công và không thể rollback.
B. Thay thế việc phân quyền bằng cách lưu lịch sử đầy đủ.
C. Truy lại ai đã thao tác, lúc nào và trên đối tượng nào.
D. Ngăn mọi MBean phát notification trong thời gian quản trị.
Đáp án đúng: C

Câu 39. Một trang Hawtio tải được nhưng thao tác JMX bị lỗi 403; nên xem gì trước?
A. Dung lượng heap đã cấp cho JVM và số GC cycle.
B. Phiên bản Camel route và số lượng inflight exchange.
C. DNS TTL của hostname được ghi trong ObjectName.
D. Quyền người dùng và policy Jolokia cho request đó.
Đáp án đúng: D

Câu 40. Khi dùng console quản trị trên production, cách sử dụng nào phù hợp nhất?
A. Phơi console ra Internet công khai để tiện hỗ trợ từ xa.
B. Dùng chung tài khoản admin không hết hạn cho cả nhóm.
C. Tắt TLS và audit để giảm độ trễ khi mở trang MBean.
D. Dùng mạng quản trị, quyền tối thiểu và thao tác kiểm soát.
Đáp án đúng: D
