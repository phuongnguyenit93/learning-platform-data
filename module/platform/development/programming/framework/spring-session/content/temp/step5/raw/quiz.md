Câu 01. Với ứng dụng Spring Boot triển khai trên nhiều instance, Spring Session chủ yếu giải quyết bài toán nào?
A. Lưu trạng thái HttpSession vào kho chung để các instance dùng cùng phiên
B. Lưu cache response HTTP theo user vào từng instance riêng lẻ
C. Cân bằng request dựa vào CPU để tránh tạo session mới mỗi lần
D. Đồng bộ mã nguồn controller giữa các instance qua Redis pub/sub
Đáp án đúng: A

Câu 02. Trong ứng dụng Servlet, Spring Session thay đổi cách HttpSession được truy cập thông qua thành phần nào?
A. `DispatcherServlet` tự thay SessionRepository theo cookie request
B. `SessionRepositoryFilter` bọc Servlet request để đọc Session từ repository
C. `OncePerRequestFilter` trực tiếp phân phối session sang Redis Cluster
D. `SecurityContextHolderFilter` tự cài JDBC SessionRepository cho app
Đáp án đúng: B

Câu 03. Bean `springSessionRepositoryFilter` của Spring Session thường được gắn vào Servlet filter chain bằng gì?
A. `CorsFilter` đọc SessionRepository rồi ghi cookie phản hồi
B. `DelegatingFilterProxy` nối Servlet filter với bean Spring
C. `HandlerMapping` chuyển filter bean thành một MVC controller
D. `WebMvcConfigurer` đăng ký filter qua interceptor chain
Đáp án đúng: B

Câu 04. Khi tự thao tác với `SessionRepository`, method nào tạo một Session instance mới?
A. `deleteById(id)` dựng Session thay thế session cũ
B. `getSession(id)` tạo một Session mới ngay trong Redis
C. `createSession()` tạo đối tượng Session có ID mới
D. `findById(id)` dựng Session mới khi không thấy ID
Đáp án đúng: C

Câu 05. Sau khi sửa các attributes trên Session được quản lý qua SessionRepository, method nào dùng để lưu phiên?
A. `deleteById(id)` flush Session trước khi xóa record
B. `save(session)` ghi Session đã sửa attributes trở lại repository
C. `createSession()` ghi đè Session vừa được tìm thấy
D. `findById(id)` thực hiện commit các attributes mới
Đáp án đúng: B

Câu 06. Muốn tìm một phiên theo session ID và nhận null nếu không tồn tại/hết hạn, API nào phù hợp?
A. `SessionRepository.createSession()` lấy Session theo ID
B. `SessionRepository.findById(id)` tìm phiên còn hiệu lực
C. `SessionRepository.save(id)` lấy lại Session từ Redis
D. `SessionRepository.getSessionsById(id)` lấy Session
Đáp án đúng: B

Câu 07. Khi cần thu hồi một Session theo ID trong repository, method nào đúng?
A. `SessionRepository.removeSession(id)` xóa session khỏi store
B. `SessionRepository.expireSession(id)` xóa session khỏi store
C. `SessionRepository.deleteById(id)` xóa session khỏi store
D. `SessionRepository.invalidate(id)` xóa session khỏi store
Đáp án đúng: C

Câu 08. Trong cấu hình Spring Session Servlet dùng Redis thủ công, annotation nào phù hợp?
A. `@EnableRedisHttpSession` cấu hình HTTP session trên Redis
B. `@EnableSpringHttpSession` chỉ kích hoạt local sessions
C. `@EnableJdbcHttpSession` cung cấp session store JDBC
D. `@EnableRedisWebSession` áp dụng cho reactive WebFlux
Đáp án đúng: A

Câu 09. Trong cấu hình Spring Session Servlet dùng JDBC thủ công, annotation nào phù hợp?
A. `@EnableRedisHttpSession` dùng session lưu vào Redis
B. `@EnableRedisWebSession` dùng session trong WebFlux
C. `@EnableJdbcHttpSession` cấu hình HTTP session với JDBC
D. `@EnableJdbcWebSession` dùng session bằng JDBC Reactor
Đáp án đúng: C

Câu 10. Lớp repository Spring Session nào lưu HTTP session trong database qua JDBC?
A. `MapSessionRepository` quản lý phiên trong memory local
B. `ReactiveRedisSessionRepository` quản lý phiên WebFlux
C. `RedisIndexedSessionRepository` quản lý phiên qua Redis
D. `JdbcIndexedSessionRepository` quản lý phiên bằng JDBC
Đáp án đúng: D

Câu 11. Khi cần tìm session Redis theo principal và theo dõi expiration events, repository nào phù hợp?
A. `ReactiveRedisSessionRepository` dùng Servlet principal index
B. `MapSessionRepository` có Redis index và expiration events
C. `RedisIndexedSessionRepository` có index và event support
D. `JdbcIndexedSessionRepository` dùng Redis keyspace notifications
Đáp án đúng: C

Câu 12. Khi nhiều ứng dụng dùng cùng một Redis, cấu hình nào giúp tách prefix key Spring Session?
A. `spring.session.redis.namespace` đặt namespace key phù hợp
B. `spring.session.redis.database` đặt prefix key của session
C. `spring.session.redis.keyspace` là prefix chuẩn của session
D. `server.servlet.session.cookie.name` đặt Redis key prefix
Đáp án đúng: A

Câu 13. Theo schema JDBC thông dụng của Spring Session, bảng nào lưu dữ liệu attributes của phiên?
A. `SPRING_SECURITY_CONTEXT` lưu các session attributes
B. `SPRING_SESSION_PRINCIPALS` lưu attribute name/value
C. `SPRING_SESSION` lưu toàn bộ attribute value dạng blob
D. `SPRING_SESSION_ATTRIBUTES` lưu các thuộc tính của từng HTTP session
Đáp án đúng: D

Câu 14. Hai instance dùng chung Redis SessionRepository; yêu cầu nào giúp người dùng tiếp tục phiên khi chuyển node?
A. Load balancer cố định user vào một worker để đọc session
B. Mỗi instance tạo ID session mới nhưng dùng cùng username
C. Dùng chung session store và gửi cùng ID phiên qua các node
D. Mỗi instance chỉ lưu attributes trong RAM nội bộ của mình
Đáp án đúng: C

Câu 15. Trong Servlet, interface nào quyết định cách resolve session ID từ HTTP request và phản hồi?
A. `SessionRepository` quyết định header/cookie trực tiếp
B. `HttpSessionListener` quyết định vị trí lưu session ID
C. `CookieSerializer` truy vấn dữ liệu session qua JDBC
D. `HttpSessionIdResolver` xác định cách đọc và ghi ID phiên
Đáp án đúng: D

Câu 16. Khi muốn session ID nằm trong HTTP cookie, implementation nào phù hợp?
A. `DefaultCookieSerializer` thay thế SessionRepository
B. `CookieHttpSessionIdResolver` đọc ID từ cookie và ghi cookie khi cần
C. `WebSessionIdResolver` là resolver Servlet session ID
D. `HeaderHttpSessionIdResolver` đọc và ghi ID qua cookie
Đáp án đúng: B

Câu 17. Muốn sử dụng header `X-Auth-Token` làm session ID thay cho cookie, cấu hình nào đúng?
A. `DefaultCookieSerializer.xAuthToken()` giải mã header ID
B. `CookieHttpSessionIdResolver.xAuthToken()` giải mã header ID
C. `SessionRepositoryFilter.xAuthToken()` giải mã header ID
D. `HeaderHttpSessionIdResolver.xAuthToken()` đọc ID từ header
Đáp án đúng: D

Câu 18. Muốn tùy biến tên cookie, path và cờ Secure/HttpOnly cho Spring Session Servlet, bean nào hữu ích?
A. `JdbcIndexedSessionRepository` đặt thuộc tính cookie qua SQL
B. `FindByIndexNameSessionRepository` đặt cookie qua principal
C. `RedisIndexedSessionRepository` đặt cookie qua Redis config
D. `DefaultCookieSerializer` tùy biến thuộc tính session cookie
Đáp án đúng: D

Câu 19. Trong session cookie, cờ `HttpOnly` chủ yếu làm giảm rủi ro nào?
A. Cản JavaScript đọc cookie qua `document.cookie`
B. Trình duyệt gửi cookie trong yêu cầu cross-site ngoài ý muốn
C. Kho Redis có thể bị truy vấn từ máy chủ ứng dụng khác
D. Trình duyệt gửi cookie qua kết nối HTTP không dùng TLS
Đáp án đúng: A

Câu 20. Cờ `Secure` trên session cookie hướng tới hành vi nào của trình duyệt?
A. Mã hóa attributes của session khi truyền tới Redis store
B. Không cho JavaScript lấy giá trị cookie từ document.cookie
C. Chỉ gửi cookie trên kết nối HTTPS theo chính sách browser
D. Áp dụng SameSite để giới hạn các yêu cầu cookie cross-site
Đáp án đúng: C

Câu 21. Khi phải dùng `SameSite=None` để gửi cookie cross-site trên trình duyệt hiện đại, điều kiện nào đi kèm?
A. Đánh dấu `HttpOnly` thay cho `Secure` để browser nhận cookie
B. Đặt `Max-Age=0` để trình duyệt chuyển cookie qua cross-site
C. Đổi tên cookie từ SESSION thành JSESSIONID để giữ trạng thái
D. Kết hợp `SameSite=None` với `Secure` và HTTPS
Đáp án đúng: D

Câu 22. Cấu hình cookie `Path` trên session ID nên được chọn dựa trên yếu tố nào?
A. Đặt Path theo vùng URL browser cần gửi session cookie
B. Tên Redis namespace của session store trong cụm server
C. Thời gian maxInactiveInterval đã được đặt cho Session
D. Tên bảng JDBC chứa các session đang mở trong database
Đáp án đúng: A

Câu 23. Trong Spring Session, thuộc tính nào xác định giới hạn thời gian không hoạt động trước khi phiên hết hạn?
A. `id` thể hiện khoảng timeout dựa vào chiều dài session key
B. `maxInactiveInterval` đặt khoảng idle timeout của session
C. `creationTime` thể hiện khoảng idle timeout của Session
D. `lastAccessedTime` thể hiện toàn bộ thời gian sống cố định
Đáp án đúng: B

Câu 24. Giá trị `lastAccessedTime` của Session hỗ trợ kiểm soát điều gì?
A. Xác định lần đầu user đăng nhập từ OIDC provider
B. Xác định khi nào cần xoay vòng chứng thư ký JWT
C. Xác định phiên bản JSON serializer của Redis session
D. Dựa vào lần truy cập cuối để xác định phiên hết idle
Đáp án đúng: D

Câu 25. Khi cookie trình duyệt vẫn còn nhưng bản ghi session đã hết TTL trong Redis, hệ quả nào hợp lý?
A. Load balancer định tuyến user về instance từng đọc session
B. Session ID cũ không khôi phục được phiên đã hết hạn từ store
C. Framework bỏ qua TTL và lấy phiên chỉ từ browser cookie
D. Cookie còn tồn tại nên Redis phục hồi attributes của phiên cũ
Đáp án đúng: B

Câu 26. Trong Servlet, khi thực thi `HttpSession.invalidate()` trên session do Spring Session quản lý, kỳ vọng gì?
A. Chỉ đổi session ID mới và giữ lại toàn bộ phiên cũ
B. Chỉ xóa cookie browser, session vẫn được giữ trong kho
C. `HttpSession.invalidate()` vô hiệu session trong repository
D. Chỉ xóa SecurityContext nhưng giữ session ID trong store
Đáp án đúng: C

Câu 27. Sau khi user đăng nhập, `HttpServletRequest.changeSessionId()` giúp giảm rủi ro nào?
A. CSRF do token form không khớp với cookie trình duyệt
B. Redis key collision khi hai ứng dụng dùng cùng namespace
C. JDBC deadlock khi hai giao dịch cập nhật chung một bảng
D. Đổi ID phiên khi login để phòng session fixation
Đáp án đúng: D

Câu 28. Vì sao xóa cookie trên browser chưa đủ để đảm bảo logout thu hồi phiên ở mọi client?
A. Cookie bị xóa khiến Spring Security phát hành refresh token
B. Load balancer giữ cache cookie rồi tự đăng xuất các node
C. Browser xóa cookie làm Redis xóa cả session và indices
D. Backend session có thể tồn tại, ID bị lộ vẫn dùng lại được
Đáp án đúng: D

Câu 29. Interface nào của Spring Session hỗ trợ tìm các phiên theo tên principal để quản lý nhiều lần đăng nhập?
A. `FindByIndexNameSessionRepository` hỗ trợ index principal
B. `SessionRepositoryFilter` tự duy trì principal-index map
C. `SessionRepository` cung cấp trực tiếp findByPrincipalName
D. `CookieHttpSessionIdResolver` truy vấn session theo HTTP cookie
Đáp án đúng: A

Câu 30. Khi kết hợp Spring Security session concurrency với Spring Session, adapter nào cung cấp SessionRegistry?
A. `JdbcIndexedSessionRepository` tự là một Spring Security SessionRegistry
B. `DefaultCookieSerializer` trả các principal và active sessions
C. `SpringSessionBackedSessionRegistry` kết nối principal-index repository
D. `SessionRepositoryFilter` trực tiếp quản lý session concurrency
Đáp án đúng: C

Câu 31. Một user đăng nhập đồng thời từ nhiều thiết bị; cách áp dụng giới hạn số phiên bằng Spring Security là gì?
A. Dùng Redis namespace riêng cho từng tab trong cùng trình duyệt
B. Chặn các request không có IP giống lần đăng nhập đầu tiên
C. Dùng SessionRegistry tích hợp để kiểm soát active sessions
D. Đặt TTL cookie ngắn hơn để chỉ còn một phiên tồn tại
Đáp án đúng: C

Câu 32. Trong Spring Session, event nào biểu thị một phiên bị hủy hoặc hết hạn ở mức abstraction chung?
A. `SessionDestroyedEvent` báo phiên đã kết thúc
B. `SessionAccessedEvent` đại diện cho session hết timeout
C. `SessionCreatedEvent` đại diện cho session đã kết thúc
D. `SessionSavedEvent` đại diện cho session kết thúc do logout
Đáp án đúng: A

Câu 33. Khi cần phân biệt phiên chủ động bị xóa với phiên hết hạn, cặp event nào đúng?
A. `SessionCreatedEvent` và `SessionSavedEvent` cho hai tình huống
B. `SessionDeletedEvent` và `SessionExpiredEvent` cho hai tình huống
C. `SessionAccessedEvent` và `SessionRenamedEvent` cho hai tình huống
D. `HttpSessionEvent` và `CookieEvent` cho hai tình huống
Đáp án đúng: B

Câu 34. Với Redis indexed session events, điều gì cần lưu ý về Redis keyspace expiration notifications?
A. Redis phát keyspace events mà không cần thiết lập notifications
B. Cấu hình Redis keyspace notifications; không giả định event đến ngay
C. Redis TTL không liên quan đến SessionExpiredEvent trong Spring
D. Session expiration event được phát đúng tại giây TTL chạm 0
Đáp án đúng: B

Câu 35. Với session attributes lưu trong Redis, việc nâng cấp class Java cần chú ý điều gì?
A. SessionRepositoryFilter bỏ qua dữ liệu không còn field cũ
B. TTL cookie tăng theo số lượng field trong object được lưu
C. Kiểm khả năng đọc attributes cũ sau khi đổi schema Java
D. Load balancer tự migrate binary data từ Redis sang JDBC
Đáp án đúng: C

Câu 36. Trong JDBC-backed Spring Session, vì sao cần job xóa bản ghi phiên đã hết hạn?
A. Để bảng SESSION không nhận thêm session sau mỗi lần login
B. Lập lịch dọn bản ghi hết hạn, tách khỏi kiểm tra TTL
C. Để trình duyệt đồng bộ cookie expiry với JDBC transaction
D. Để thiết lập JWT signature verification cho session ID
Đáp án đúng: B

Câu 37. Khi thiết kế session attributes của ứng dụng tài chính, nguyên tắc nào phù hợp?
A. Hạn chế dữ liệu nhạy cảm và bảo vệ quyền truy cập store
B. Ghi access token vào log mỗi lần SessionRepository.save
C. Dùng session ID làm khóa mã hóa dữ liệu lưu trong Redis
D. Đưa mật khẩu người dùng vào session để giảm truy vấn DB
Đáp án đúng: A

Câu 38. Hai request cập nhật cùng một session trên hai instance gần như đồng thời; nguy cơ nào cần test?
A. Trình duyệt tự merge hai bản thuộc tính và ghi ngược server
B. Load balancer sticky tuần tự hóa cập nhật chung session ID
C. Redis TTL ngăn được sự cố ghi đè khi cùng session ID
D. Lost update khi hai bản session cũ ghi đè attributes
Đáp án đúng: D

Câu 39. Khi kho Redis/JDBC session tạm ngưng hoạt động, hành vi an toàn cho request cần xác thực là gì?
A. Từ chối request cần phiên nếu store lỗi, không bỏ qua auth
B. Bỏ qua xác thực nếu Redis timeout để giảm lỗi HTTP phía client
C. Tạo principal ADMIN tạm thời cho user đã có cookie SESSION
D. Dùng session ID cookie để suy ra toàn bộ roles không cần store
Đáp án đúng: A

Câu 40. Để kiểm chứng session dùng chung thực sự hoạt động khi load balancer chuyển node, test nào phù hợp?
A. Login tại node A, chuyển cùng session ID sang B và kiểm lại
B. Chỉ xác minh mỗi instance có cookie với tên SESSION giống nhau
C. Chỉ gọi Redis ping rồi suy ra login state đã được chia sẻ
D. Chỉ chạy MockMvc in-memory với một application instance
Đáp án đúng: A
