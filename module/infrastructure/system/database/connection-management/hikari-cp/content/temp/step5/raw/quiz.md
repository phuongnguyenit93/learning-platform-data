Câu 1. Trong ứng dụng Java dùng HikariCP, điều gì xảy ra khi gọi `dataSource.getConnection()` lúc pool có kết nối rảnh?
A. Pool mở một TCP connection mới cho mọi lần gọi.
B. Pool cấp một connection khả dụng để mã ứng dụng mượn.
C. Pool dùng chung connection đang được một thread khác mượn.
D. Pool trả JDBC connection vật lý mà không dùng proxy.
Đáp án đúng: B

Câu 2. Khi xong công việc với `Connection` mượn từ HikariCP, cách trả về pool đúng là gì?
A. Gọi `commit()` để pool đánh dấu connection rảnh rồi tái sử dụng.
B. Gọi `setAutoCommit(true)` để đưa connection về pool.
C. Chờ `idleTimeout` để HikariCP thu hồi connection.
D. Gọi `close()` hoặc dùng try-with-resources trên Connection.
Đáp án đúng: D

Câu 3. Với HikariCP, khác biệt chính giữa handle được mượn và JDBC connection vật lý là gì?
A. Đóng handle được mượn luôn ngắt kết nối vật lý ngay lúc đó.
B. Đóng handle được mượn thường trả kết nối vật lý về pool.
C. Mỗi handle được mượn luôn tạo kết nối vật lý mới.
D. Connection vật lý được dùng đồng thời bởi mọi handle.
Đáp án đúng: B

Câu 4. Khi pool đã đạt `maximumPoolSize` và mọi connection đều đang bận, `getConnection()` xử lý thế nào?
A. Vượt mức pool và tạo thêm connection theo nhu cầu.
B. Đóng connection đang bận lâu nhất để cấp cho caller.
C. Trả connection đang được thread khác dùng cho caller kế tiếp.
D. Chờ connection được trả về, tối đa đến `connectionTimeout`.
Đáp án đúng: D

Câu 5. Ý nghĩa của `connectionTimeout` trong HikariCP là gì?
A. Giới hạn thời gian chạy một câu SQL trên server.
B. Giới hạn thời gian driver thiết lập TCP connection.
C. Giới hạn thời gian connection được phép tồn tại.
D. Giới hạn thời gian chờ mượn connection từ pool.
Đáp án đúng: D

Câu 6. Phát biểu nào về `validationTimeout` của HikariCP là đúng?
A. Giới hạn thời gian đợi connection được trả về pool.
B. Giới hạn thời gian kiểm tra một connection còn hợp lệ.
C. Giới hạn thời gian thực hiện mọi lệnh SQL của JDBC.
D. Giới hạn thời gian giữ connection trước khi bị thu hồi.
Đáp án đúng: B

Câu 7. Với `minimumIdle` thấp hơn `maximumPoolSize`, vai trò của `idleTimeout` là gì?
A. Có thể loại connection đang chạy vượt `maximumPoolSize`.
B. Có thể loại connection rảnh ngay khi chạm `maximumPoolSize`.
C. Có thể loại connection rảnh vượt mức `minimumIdle`.
D. Có thể loại connection đang mượn khi quá `idleTimeout`.
Đáp án đúng: C

Câu 8. Khi một connection đang được mượn vượt quá `maxLifetime`, HikariCP thường làm gì?
A. Đóng connection ngay giữa câu SQL đang thực thi.
B. Tái sử dụng connection không giới hạn sau thời điểm đó.
C. Chuyển connection thành idle dù transaction còn mở.
D. Đợi trả về pool rồi loại connection đó khỏi vòng đời.
Đáp án đúng: D

Câu 9. Mục đích chính của `keepaliveTime` trong HikariCP là gì?
A. Định kỳ kiểm tra connection đang rảnh để giữ chúng sống.
B. Định kỳ hủy transaction đang mở để giải phóng connection bận.
C. Định kỳ mở connection mới để vượt `maximumPoolSize`.
D. Định kỳ reset mọi connection sau mỗi lần truy vấn.
Đáp án đúng: A

Câu 10. Vì sao nên đặt `maxLifetime` thấp hơn giới hạn tuổi connection phía DB hoặc proxy, nếu có?
A. Để JDBC tăng thời lượng tối đa cho mỗi câu SQL.
B. Để pool thay connection trước khi phía ngoài chủ động đóng.
C. Để transaction không phải đóng sau mỗi lần commit.
D. Để pool giữ connection bận lâu hơn mức timeout.
Đáp án đúng: B

Câu 11. Giá trị `maximumPoolSize` của HikariCP kiểm soát điều gì?
A. Giới hạn số thread Java có thể gọi JDBC đồng thời.
B. Giới hạn số SQL statement được chạy trên mỗi connection.
C. Giới hạn tổng connection vật lý trong pool, gồm bận và rảnh.
D. Giới hạn số lần kết nối lại khi database bị lỗi.
Đáp án đúng: C

Câu 12. Nếu không khai báo `minimumIdle`, mặc định HikariCP xử lý thế nào?
A. Luôn đặt `minimumIdle` bằng 0 để pool thu nhỏ khi tải giảm.
B. Dùng giá trị `maximumPoolSize`, thường giữ pool cố định.
C. Luôn đặt `minimumIdle` bằng 1 để có một connection.
D. Đặt `minimumIdle` theo số core của máy chủ ứng dụng.
Đáp án đúng: B

Câu 13. Trong Spring Boot dùng HikariCP, cấu hình nào đặt giới hạn kích thước pool?
A. `spring.jpa.properties.hibernate.connection.pool_size`
B. `spring.datasource.hikari.connection-timeout`
C. `spring.datasource.hikari.maximum-pool-size`
D. `spring.datasource.hikari.minimum-idle`
Đáp án đúng: C

Câu 14. Điều kiện nào khiến Spring Boot thường tự cấu hình HikariCP làm JDBC DataSource?
A. Có HikariCP trên classpath và app chưa khai báo DataSource.
B. Đã bật JPA nhưng không có JDBC driver trong classpath.
C. Đã cấu hình Redis và chưa khai báo `JdbcTemplate`.
D. Đã khai báo một `DataSource` tùy chỉnh trong ứng dụng.
Đáp án đúng: A

Câu 15. Ứng dụng Spring Data JPA sử dụng HikariCP theo cơ chế nào?
A. EntityManager tự duy trì TCP pool tách khỏi DataSource.
B. Mỗi repository tự tạo một HikariDataSource độc lập.
C. Hibernate mượn JDBC connection qua DataSource được cấu hình.
D. Spring Data JPA chỉ dùng HikariCP khi không có transaction.
Đáp án đúng: C

Câu 16. Ảnh hưởng nào dễ xảy ra khi đặt một giao dịch `@Transactional` quá dài?
A. Connection có thể bị giữ lâu, làm giảm số connection sẵn có.
B. Pool lập tức tăng `maximumPoolSize` cho giao dịch đó.
C. Mọi connection bị đóng khi transaction bắt đầu.
D. Hibernate không cần JDBC connection trong toàn giao dịch.
Đáp án đúng: A

Câu 17. Chỉ số `active` của HikariCP biểu thị điều gì?
A. Số connection đang được tạo thêm vào pool.
B. Số connection hiện chờ được ứng dụng mượn từ pool.
C. Số connection hiện được ứng dụng mượn từ pool.
D. Số connection đã bị pool loại sau timeout.
Đáp án đúng: C

Câu 18. Chỉ số `idle` của HikariCP biểu thị điều gì?
A. Số connection đang được ứng dụng mượn từ pool.
B. Số thread đang chờ mượn connection.
C. Số connection rảnh đang sẵn sàng được mượn.
D. Số connection đã bị DB ngắt kết nối.
Đáp án đúng: C

Câu 19. Chỉ số `pending` của HikariCP tăng cho thấy điều gì?
A. Có các thread đang chờ lấy connection từ pool.
B. Có các connection đang chờ bị hủy vì `maxLifetime`.
C. Có các transaction vừa commit và chờ flush.
D. Có các truy vấn đã hoàn tất nhưng chờ ghi log.
Đáp án đúng: A

Câu 20. Khi `active` chạm `maximumPoolSize`, `idle = 0` và `pending` tăng, nhận định nào phù hợp?
A. Pool dư connection; cần giảm thời gian giữ connection trong cache.
B. Pool bão hòa; cần kiểm tra thời gian giữ connection và tải DB.
C. Pool cần mở thêm connection ngay mà không cần đo tải DB.
D. DB chắc chắn mất mạng; bỏ qua phân tích thời gian truy vấn.
Đáp án đúng: B

Câu 21. Metrics nào của Micrometer/Spring Boot phản ánh số connection đang được mượn?
A. `hikaricp.connections.active`
B. `hikaricp.connections.idle`
C. `hikaricp.connections.pending`
D. `hikaricp.connections.timeout`
Đáp án đúng: A

Câu 22. HikariCP `leakDetectionThreshold` chủ yếu hỗ trợ việc gì?
A. Tự đóng mọi connection vượt ngưỡng đang được mượn.
B. Tự tăng pool khi một connection vượt ngưỡng chờ.
C. Tự rollback tất cả transaction quá ngưỡng SQL.
D. Cảnh báo khi một connection bị giữ vượt ngưỡng cấu hình.
Đáp án đúng: D

Câu 23. Khi log cảnh báo leak từ HikariCP xuất hiện, cách hiểu nào đúng nhất?
A. Connection bị giữ lâu; cần tăng `maximumPoolSize` ngay.
B. Connection bị giữ lâu; cần kiểm tra stack trace và giao dịch.
C. Pool cấp connection chậm; cần tăng `connectionTimeout` ngay.
D. DB thường đóng connection; cần tăng `maxLifetime` ngay.
Đáp án đúng: B

Câu 24. Để tránh trả connection muộn do ngoại lệ khi gọi JDBC, lựa chọn nào tốt nhất?
A. Chỉ gọi `close()` khi mọi lệnh SQL hoàn thành.
B. Đợi garbage collector thu hồi handle của pool.
C. Bọc việc mượn `Connection` bằng try-with-resources.
D. Tăng `leakDetectionThreshold` đến khi không còn log.
Đáp án đúng: C

Câu 25. Một pool quá lớn có thể gây tác hại gì với hệ quản trị cơ sở dữ liệu?
A. Giảm số session nhưng tăng số lần mở TCP connection.
B. Loại bỏ nhu cầu đồng bộ trong transaction của database.
C. Đảm bảo mọi truy vấn nhanh hơn vì có nhiều connection.
D. Tăng cạnh tranh tài nguyên và số session đồng thời.
Đáp án đúng: D

Câu 26. Khi định cỡ `maximumPoolSize`, dữ liệu nào nên được ưu tiên?
A. Tải đồng thời, thời gian giữ connection và giới hạn DB.
B. Chỉ số thread tối đa mà JVM có thể tạo khi khởi động.
C. Dung lượng đĩa cùng số lượng bảng trong database.
D. Tổng API endpoint cùng số class repository của ứng dụng.
Đáp án đúng: A

Câu 27. Một dịch vụ có 4 instance, mỗi instance đặt `maximumPoolSize = 20`. Tình huống nào cần chú ý?
A. Mọi instance chia sẻ đúng 20 connection từ một pool.
B. Mỗi instance tự giới hạn toàn hệ thống còn 5 connection.
C. Có thể tạo đến 80 connection DB từ các instance này.
D. Tổng connection DB luôn bằng số HTTP thread đang chạy.
Đáp án đúng: C

Câu 28. Khi tăng `maximumPoolSize` mà timeout vẫn tăng, bước điều tra nào hữu ích?
A. Tăng tiếp số thread gọi JDBC mà không cần đo thêm.
B. Tắt metric `pending` vì tăng chi phí ghi nhận kết nối.
C. Chuyển sang auto-commit để bỏ qua SQL chạy chậm.
D. Đo thời gian giữ connection, truy vấn chậm và tải DB.
Đáp án đúng: D

Câu 29. Nếu DB thỉnh thoảng đóng connection nhàn rỗi, nên xem xét nhóm cài đặt nào?
A. `connectionTimeout`, `minimumIdle` và timeout của HTTP.
B. `leakDetectionThreshold`, `maximumPoolSize` và timeout SQL.
C. `validationTimeout`, `autoCommit` và timeout của executor.
D. `maxLifetime`, `keepaliveTime` và timeout của DB/proxy.
Đáp án đúng: D

Câu 30. Trong sự cố mất kết nối DB, dấu hiệu nào giúp phân biệt lỗi kết nối với thiếu pool?
A. Đối chiếu exception JDBC, log kết nối và `active`/`pending`.
B. Chỉ so sánh `maximumPoolSize` với số HTTP worker hiện có.
C. Chỉ xem `pending` và tăng pool nếu có thread đang chờ.
D. Chỉ đếm số bean `EntityManager` của Spring khi startup.
Đáp án đúng: A

Câu 31. Cấu hình `connectionTestQuery` phù hợp nhất khi nào?
A. Driver đã có `Connection.isValid()` và dùng ổn định.
B. Driver thiếu hỗ trợ kiểm tra connection hợp lệ qua JDBC4.
C. Muốn giới hạn thời gian chạy mọi câu truy vấn trong JPA.
D. Muốn tăng số connection vật lý vượt giới hạn pool.
Đáp án đúng: B

Câu 32. Khi ứng dụng dừng và muốn đóng toàn bộ pool HikariCP, thao tác nào phù hợp?
A. Đóng `HikariDataSource` để pool hủy các kết nối của nó.
B. Đóng một `Connection` mượn để pool dừng hoàn toàn.
C. Gọi `commit()` cho transaction cuối để pool tự dừng.
D. Gọi `getConnection()` đến khi pool hết tài nguyên rồi dừng.
Đáp án đúng: A
