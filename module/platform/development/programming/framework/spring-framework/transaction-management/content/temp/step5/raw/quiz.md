Câu 1. Trong một service Spring ghi hai bảng trong cùng transaction, Atomicity yêu cầu điều gì?
A. Lần ghi đầu luôn commit trước khi lần ghi sau bắt đầu
B. Mỗi bảng bắt buộc sử dụng một connection JDBC riêng
C. Hai lần ghi cùng commit hoặc cùng rollback nếu thất bại
D. Lần ghi thứ hai được retry mà không ảnh hưởng bảng đầu
Đáp án đúng: C

Câu 2. Khả năng Consistency của transaction trong hệ quan hệ gắn với điều gì?
A. Chặn mọi giao dịch song song đọc cùng một bảng
B. Giữ kết nối JDBC ở trạng thái mở vô thời hạn
C. Đảm bảo mọi request HTTP được xử lý theo một thứ tự
D. Giữ dữ liệu hợp lệ theo constraint khi commit
Đáp án đúng: D

Câu 3. Dirty read trong giao dịch xuất hiện khi nào?
A. Một transaction đọc dữ liệu chưa commit của transaction khác
B. Một transaction đọc hai giá trị khác nhau đã được commit
C. Truy vấn lần hai thấy thêm hàng mới khớp cùng predicate
D. Một transaction tự cập nhật lại hàng vừa đọc của chính nó
Đáp án đúng: A

Câu 4. Non-repeatable read mô tả tình huống nào?
A. Truy vấn cùng điều kiện hai lần và thấy thêm hàng mới
B. Đọc giá trị do transaction khác ghi nhưng chưa commit
C. Một INSERT bị từ chối vì vi phạm unique constraint
D. Đọc cùng một hàng hai lần nhưng thấy giá trị đã thay đổi
Đáp án đúng: D

Câu 5. Phantom read có thể nhận ra qua dấu hiệu nào?
A. Đọc cùng một hàng hai lần rồi thấy giá trị cột đã đổi
B. Đọc được thay đổi chưa commit của một transaction khác
C. Ghi một hàng nhưng câu UPDATE ảnh hưởng không hàng nào
D. Cùng điều kiện lọc nhưng số hàng khớp thay đổi giữa hai lần đọc
Đáp án đúng: D

Câu 6. Đối với READ_COMMITTED, kỳ vọng tối thiểu nào thường đúng?
A. Không đọc các thay đổi chưa commit của transaction khác
B. Giữ toàn bộ tập hàng thỏa predicate không đổi đến commit
C. Ngăn transaction khác cập nhật tất cả hàng đang được đọc
D. Đảm bảo mọi lệnh SELECT trả cùng snapshot trong toàn transaction
Đáp án đúng: A

Câu 7. PlatformTransactionManager trong Spring chủ yếu định nghĩa khả năng nào?
A. Chuyển câu SQL sang dạng JPQL trước khi thực thi
B. Bắt đầu, commit hoặc rollback giao dịch theo nền tảng
C. Tự chọn isolation mạnh nhất cho mọi service method
D. Quản lý việc phân phối response từ REST controller
Đáp án đúng: B

Câu 8. Với Spring JDBC dựa trên DataSource, transaction manager nào phù hợp?
A. JpaTransactionManager quản lý một EntityManager mặc định
B. JmsTransactionManager quản lý session của JMS provider
C. DataSourceTransactionManager quản lý giao dịch JDBC
D. ReactiveMongoTransactionManager quản lý JDBC Connection
Đáp án đúng: C

Câu 9. Khi ứng dụng dùng JPA EntityManagerFactory, thường chọn manager nào?
A. DataSourceTransactionManager để thay mọi JPA persistence context
B. R2dbcTransactionManager để sử dụng JPA EntityManager
C. JmsTransactionManager để đồng bộ JPA transaction
D. JpaTransactionManager cho giao dịch của tầng JPA
Đáp án đúng: D

Câu 10. Trong Spring reactive transaction, interface quản lý transaction phù hợp là gì?
A. PlatformTransactionManager chỉ dùng Reactor Context
B. EntityManagerFactory giữ trạng thái trên Flux pipeline
C. ReactiveTransactionManager tham gia luồng reactive
D. ConnectionFactory JDBC bọc Publisher khi subscribe
Đáp án đúng: C

Câu 11. Nếu @Transactional không chỉ rõ propagation, mode mặc định nào được dùng?
A. REQUIRES_NEW tạo transaction độc lập cho mọi lần gọi
B. NESTED luôn đặt savepoint trong transaction trước
C. REQUIRED tham gia transaction có sẵn hoặc tạo mới
D. SUPPORTS bỏ qua transaction dù caller đã tạo
Đáp án đúng: C

Câu 12. Khi method B @Transactional(REQUIRED) được gọi qua proxy từ method A đang có transaction, điều gì xảy ra?
A. B thường tham gia cùng transaction vật lý với A
B. B luôn tạo connection riêng và commit độc lập khỏi A
C. B chạy không transaction để tránh nested rollback
D. B mở transaction XA mới cho mỗi database resource
Đáp án đúng: A

Câu 13. Một inner REQUIRED tham gia transaction hiện có rồi đánh dấu rollback-only, outer vẫn cố commit thì sao?
A. Outer được phép commit vì đã bắt và ghi log lỗi của inner
B. Outer có thể nhận UnexpectedRollbackException khi commit
C. Inner rollback riêng qua savepoint nên outer commit như cũ
D. Spring tự đổi REQUIRED của inner sang REQUIRES_NEW
Đáp án đúng: B

Câu 14. Với REQUIRES_NEW khi caller đã có transaction, cách xử lý nào đúng?
A. Tạo savepoint bên trong cùng connection của transaction ngoài
B. Chạy không transaction rồi trả lại connection sau method
C. Tạm suspend transaction ngoài rồi mở transaction vật lý riêng
D. Gộp trạng thái rollback-only vào transaction caller ngay
Đáp án đúng: C

Câu 15. Nếu inner REQUIRES_NEW đã commit rồi outer transaction rollback, kết quả nào được chờ đợi?
A. Rollback của outer bắt buộc hoàn tác cả phần inner đã commit
B. Inner được giữ pending tới khi outer commit thành công
C. Commit của inner vẫn tồn tại độc lập với rollback của outer
D. Spring tự biến inner thành NESTED nếu outer bị rollback
Đáp án đúng: C

Câu 16. NESTED trong Spring thường được thực thi bằng cơ chế nào khi manager hỗ trợ?
A. Một transaction vật lý mới với connection thứ hai
B. Một JMS transaction chạy song song với JDBC transaction
C. Một callback sau commit để giả lập rollback riêng
D. Savepoint trong transaction vật lý hiện tại
Đáp án đúng: D

Câu 17. Với NESTED khi chưa tồn tại transaction phía caller, hành vi nào phù hợp?
A. Bắt buộc ném lỗi do chưa có savepoint của caller
B. Luôn chạy không transaction và bỏ qua propagation
C. Chỉ đăng ký savepoint ngay sau khi method trả về
D. Có thể bắt đầu transaction mới như REQUIRED
Đáp án đúng: D

Câu 18. Propagation SUPPORTS hoạt động thế nào khi không có transaction từ caller?
A. Chạy mà không chủ động tạo transaction mới
B. Ném lỗi vì caller bắt buộc phải có transaction
C. Tạo transaction mới rồi commit như REQUIRED
D. Suspend transaction hiện có và tạo session khác
Đáp án đúng: A

Câu 19. Propagation MANDATORY áp dụng khi caller không có transaction thì sao?
A. Tạo transaction mới rồi tham gia như REQUIRED
B. Báo lỗi vì yêu cầu phải tồn tại transaction
C. Cho chạy không transaction như SUPPORTS
D. Tạo savepoint rỗng để chờ caller commit
Đáp án đúng: B

Câu 20. Propagation NOT_SUPPORTED khi caller đang có transaction sẽ làm gì?
A. Suspend transaction đang có để chạy ngoài transaction
B. Tạo một transaction riêng giống REQUIRES_NEW
C. Tham gia cùng transaction hiện tại như REQUIRED
D. Tạo savepoint để có thể rollback phần lệnh này
Đáp án đúng: A

Câu 21. Propagation NEVER khi được gọi trong transaction có sẵn sẽ ra sao?
A. Suspend transaction và tiếp tục giống NOT_SUPPORTED
B. Tạo transaction độc lập rồi hủy transaction cũ
C. Lỗi khi method chạy trong transaction có sẵn
D. Chuyển transaction hiện tại sang chế độ chỉ đọc
Đáp án đúng: C

Câu 22. Vì sao REQUIRES_NEW có thể gây áp lực lên connection pool?
A. Inner luôn tái sử dụng connection đang gắn với transaction outer
B. Inner cần connection khi outer vẫn giữ connection
C. Transaction outer sẽ tự đóng trước khi inner bắt đầu
D. Spring sẽ không cấp connection cho inner khi pool đầy
Đáp án đúng: B

Câu 23. Khi bean dùng this.save() để gọi method @Transactional trong chính class, hệ quả thường là gì?
A. Spring tự tạo proxy mới cho từng lệnh gọi qua this
B. Annotation @Transactional được JVM thực thi ở mọi self-call
C. Container tự đổi self-call thành event sau commit
D. Self-call qua this bỏ qua Spring transaction proxy
Đáp án đúng: D

Câu 24. Cách thiết kế nào thường xử lý việc self-invocation bỏ qua transaction proxy?
A. Đưa method có transaction sang bean khác rồi gọi qua Spring proxy
B. Đánh dấu class là final để Spring buộc method được intercept
C. Gọi private method thay public method để kích hoạt proxy
D. Thay this.save() thành super.save() trong cùng class
Đáp án đúng: A

Câu 25. Để annotation @Transactional được áp qua proxy ở Spring thuần, điều kiện nào cần thiết?
A. Chỉ khai annotation rồi khởi tạo target bằng new trong service
B. Đặt annotation ở interface thì mọi lời gọi private đều được chặn
C. Dùng một DataSource bean là đủ dù không bật transaction advice
D. Có transaction infrastructure và lời gọi đi qua bean proxy
Đáp án đúng: D

Câu 26. Với Spring transaction proxy thông thường, method private có được advice trực tiếp không?
A. Có, nếu private method được @Transactional(readOnly=true)
B. Không, proxy không chặn trực tiếp private method
C. Có, khi caller cũng có @Transactional trên class
D. Có, nếu đặt @Primary lên transaction manager bean
Đáp án đúng: B

Câu 27. Theo mặc định, Spring rollback khi loại lỗi nào thoát khỏi @Transactional method?
A. Mọi checked exception được method khai báo throws
B. Chỉ SQLException mà JdbcTemplate chuyển đổi
C. RuntimeException hoặc Error chưa được xử lý
D. Chỉ IOException khi @Transactional có readOnly=false
Đáp án đúng: C

Câu 28. Nếu muốn checked IOException cũng khiến @Transactional rollback, khai báo gì?
A. @Transactional(rollbackFor = IOException.class)
B. @Transactional(noRollbackFor = IOException.class)
C. @Transactional(propagation = Propagation.SUPPORTS)
D. @Transactional(isolation = Isolation.DEFAULT)
Đáp án đúng: A

Câu 29. Khi muốn một RuntimeException xác định không gây rollback, dùng thuộc tính nào?
A. noRollbackFor trên annotation @Transactional
B. rollbackFor trên annotation @Transactional
C. transactionManager trên annotation @Transactional
D. timeout trên annotation @Transactional
Đáp án đúng: A

Câu 30. Nếu method @Transactional bắt exception và không ném lại, transaction thường ra sao?
A. Spring tự biết catch block và rollback transaction
B. Có thể commit nếu chưa bị đánh dấu rollback-only
C. Transaction luôn bị suspend do đã có exception
D. Mọi lần catch đều tạo savepoint mới cho transaction
Đáp án đúng: B

Câu 31. Trong code chủ động cần hủy transaction hiện tại mà không ném exception, cách nào phù hợp?
A. Gọi EntityManager.flush() rồi chờ commit mặc định
B. Đặt rollback-only lên TransactionStatus hiện tại
C. Đặt readOnly=true sau khi query đã chạy xong
D. Bật propagation SUPPORTS trên method caller
Đáp án đúng: B

Câu 32. Khi Spring @Transactional timeout=5 được cấu hình, ý nghĩa thường là gì?
A. Đảm bảo mọi câu SQL sẽ tự dừng sau đúng năm giây
B. Áp timeout mới lên transaction ngoài đã tồn tại
C. Đặt thời hạn transaction mới nếu manager hỗ trợ
D. Buộc retry transaction tối đa năm lần khi lock fail
Đáp án đúng: C

Câu 33. @Transactional(readOnly=true) nên được hiểu thế nào trong Spring?
A. Một transaction không thể phát bất kỳ SQL UPDATE nào
B. Một cách buộc SQL driver trả về dữ liệu từ cache
C. readOnly là hint, không mặc định ngăn thao tác write
D. Một flag thay propagation REQUIRED thành SUPPORTS
Đáp án đúng: C

Câu 34. Với Isolation.READ_COMMITTED, loại bất thường nào vẫn có thể xuất hiện?
A. Dirty read của dữ liệu chưa được transaction khác commit
B. Mọi phantom read đều bị DB tự động loại bỏ
C. Mọi transaction đồng thời được tuần tự hóa hoàn toàn
D. Vẫn có thể gặp non-repeatable read sau commit khác
Đáp án đúng: D

Câu 35. Khi muốn tránh non-repeatable read, mức isolation phổ biến nào phù hợp hơn READ_COMMITTED?
A. READ_UNCOMMITTED nhằm đọc thay đổi nhanh hơn
B. REPEATABLE_READ nhằm ổn định việc đọc lại cùng hàng
C. DEFAULT luôn mang ý nghĩa SERIALIZABLE với mọi DB
D. NOT_SUPPORTED nhằm giảm transaction contention
Đáp án đúng: B

Câu 36. Mức SERIALIZABLE giúp gì và có đánh đổi nào?
A. Tự làm transaction idempotent với mọi service HTTP
B. Loại hoàn toàn deadlock và rollback trong mọi database
C. Mạnh về cô lập nhưng có thể tăng contention và retry
D. Chuyển mọi lệnh SQL sang batch để đạt throughput cao
Đáp án đúng: C

Câu 37. Khi isolation=Isolation.DEFAULT trên @Transactional, mức thực tế lấy từ đâu?
A. Mặc định của resource hoặc database đang dùng
B. Giá trị SERIALIZABLE cố định trong Spring Framework
C. Giá trị của annotation @Primary trên bean service
D. Trạng thái HTTP session được gắn với từng request
Đáp án đúng: A

Câu 38. TransactionTemplate trong Spring phù hợp với trường hợp nào?
A. Tạo JPA entity mapping không cần EntityManagerFactory
B. Bao một đoạn xử lý bằng transaction theo cách lập trình
C. Tự đăng ký mọi method service thành listener JMS
D. Bật reactive transaction bằng một WebSocket channel
Đáp án đúng: B

Câu 39. Trong TransactionTemplate.execute, callback thường nhận gì để điều khiển rollback?
A. TransactionStatus có thể gọi setRollbackOnly()
B. JmsMessage có thể gọi acknowledge() cho SQL
C. EntityManagerFactory có thể đóng ApplicationContext
D. WebRequest có thể thêm header rollback vào response
Đáp án đúng: A

Câu 40. TransactionTemplate mặc định dùng propagation nào nếu không sửa cấu hình?
A. REQUIRED tham gia transaction có sẵn hoặc tạo mới
B. NEVER luôn chạy ngoài transaction của caller
C. MANDATORY đòi caller đang mở transaction
D. NESTED tạo savepoint ngay cả khi không có transaction
Đáp án đúng: A

Câu 41. Trong giao dịch JDBC do Spring quản lý, việc chia sẻ connection cùng transaction thường dựa vào gì?
A. Mỗi JdbcTemplate mới tự tạo một transaction độc lập
B. DataSource chỉ cấp một connection cho toàn JVM
C. Reactor Context luôn được JDBC dùng thay ThreadLocal
D. TransactionSynchronizationManager gắn resource theo thread
Đáp án đúng: D

Câu 42. Vì sao code JDBC tự gọi dataSource.getConnection() tùy ý có thể lệch transaction Spring?
A. Mọi connection của DataSource đều tham gia transaction caller
B. Lời gọi trực tiếp tự nối vào transaction đang suspended
C. Connection mới sẽ commit đồng thời dù manager khác
D. Không tự bảo đảm lấy connection đang được Spring bind
Đáp án đúng: D

Câu 43. Khi cần xử lý hành động sau commit thành công của transaction, cơ chế nào của Spring phù hợp?
A. @PostConstruct trên service được gọi sau mỗi lần commit
B. TransactionSynchronization.afterCommit() sau khi commit
C. @AfterReturning của Aspect tự chứng nhận DB đã commit
D. @DependsOn đánh dấu callback chạy sau commit DB
Đáp án đúng: B

Câu 44. @TransactionalEventListener(phase = AFTER_COMMIT) thường được gọi khi nào?
A. Ngay lúc publisher gửi event dù transaction còn mở
B. Trước khi transaction bắt đầu để tránh lock
C. Sau khi transaction gắn với sự kiện đã commit
D. Ngay sau khi rollback mà không cần phase khác
Đáp án đúng: C

Câu 45. Nếu phát event ngoài transaction và @TransactionalEventListener không bật fallbackExecution, điều gì xảy ra?
A. Listener thông thường không được gọi cho event đó
B. Listener luôn tạo một transaction mới rồi xử lý event
C. Event được giữ chờ transaction kế tiếp mở
D. Spring tự chuyển callback sang @EventListener thường
Đáp án đúng: A

Câu 46. Trong Spring reactive, giao dịch được gắn với luồng xử lý bằng gì?
A. ThreadLocal được giữ cố định qua mọi reactive operator
B. Reactor Context đi theo subscriber thay cho ThreadLocal
C. HTTP session được dùng để chứa connection hiện tại
D. Một global static field dùng chung cho mọi Mono
Đáp án đúng: B

Câu 47. Với reactive @Transactional, phương thức nên trả kết quả thế nào?
A. Gọi subscribe thủ công rồi trả void cho caller
B. Gọi block trên event-loop để giữ ThreadLocal
C. Trả Future và để Spring dùng JDBC transaction manager
D. Trả Publisher để transaction đi cùng subscription
Đáp án đúng: D

Câu 48. Trong kiểm thử tích hợp có @Transactional trên test và rollback mặc định, lưu ý nào đúng?
A. REQUIRES_NEW luôn rollback cùng transaction của test method
B. REQUIRES_NEW có thể commit ngoài rollback của test
C. Mọi HTTP thread do test tạo tự tham gia transaction test
D. Test framework tự rollback cả hệ thống message broker
Đáp án đúng: B
