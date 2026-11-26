Câu 1. Spring Data KeyValue cung cấp giá trị chính nào cho ứng dụng Spring?
A. Một máy chủ database phân tán có cơ chế sao lưu riêng
B. Một SQL engine mặc định cho mọi loại kho key-value
C. Ánh xạ entity và repository cho các kho key-value
D. Một cache JVM tự động gắn TTL cho toàn bộ entity
Đáp án đúng: C

Câu 2. Vì sao Spring Data KeyValue không đồng nghĩa với một database cụ thể?
A. Hành vi lưu trữ phụ thuộc adapter và backend được cấu hình
B. Mọi repository tự động dùng cùng một server Redis có sẵn
C. Toàn bộ dữ liệu luôn được ghi xuống ổ đĩa của host JVM
D. Mỗi entity luôn được biến thành bảng trong cơ sở SQL
Đáp án đúng: A

Câu 3. Annotation @Id trên entity key-value thường đảm nhiệm việc gì?
A. Xác định định danh dùng truy cập bản ghi bằng key
B. Đặt tên namespace cho toàn bộ lớp entity được lưu
C. Chọn bộ lọc mặc định của derived query theo thuộc tính
D. Thiết lập version token cho mọi lần cập nhật entity
Đáp án đúng: A

Câu 4. Annotation @KeySpace có tác dụng gì với entity Spring Data KeyValue?
A. Tạo chỉ mục secondary cho tất cả thuộc tính của entity
B. Đặt tên không gian khóa dùng để phân nhóm entity
C. Đặt thời gian sống cho từng entry trong backing Map
D. Đăng ký transaction manager riêng cho mỗi lớp Java
Đáp án đúng: B

Câu 5. Trong một adapter có phân biệt keyspace, hai entity có cùng ID nhưng khác keyspace thường ra sao?
A. Cả hai buộc ánh xạ vào một entry duy nhất cùng địa chỉ
B. ID thứ hai luôn được SDK tăng tự động trước khi lưu
C. Chúng có thể được lưu trong hai vùng khóa riêng biệt
D. Keyspace sẽ bị bỏ qua khi lệnh findById được thực thi
Đáp án đúng: C

Câu 6. Thiết kế khóa định danh của entity nên ưu tiên tiêu chí nào?
A. Khóa ổn định, duy nhất trong keyspace và dễ tìm
B. Thay đổi theo thời điểm đọc để loại bỏ khóa trùng nhau
C. Dùng hashCode từ đối tượng mutable ở mỗi lần lưu
D. Đặt toàn bộ giá trị nhạy cảm vào key để dễ gỡ lỗi
Đáp án đúng: A

Câu 7. Một repository thường cần biết hai kiểu dữ liệu nào khi khai báo generic?
A. Kiểu HTTP request và kiểu HTTP response tương ứng
B. Kiểu transaction log và kiểu replication của store
C. Kiểu SQL row và kiểu khóa ngoại của từng collection
D. Kiểu entity và kiểu khóa định danh của entity đó
Đáp án đúng: D

Câu 8. Phương thức findById khi có key hợp lệ thường nhắm tới thao tác nào?
A. Quét mọi keyspace để tìm property gần giống tên key
B. Đọc entry đã biết định danh trong keyspace tương ứng
C. Tạo bản sao entity trước khi trả dữ liệu cho client
D. Ghi entry mới nếu không tìm thấy bản ghi đã chỉ định
Đáp án đúng: B

Câu 9. Khi lưu một entity đã có ID, điều nào cần được xem xét?
A. Save luôn tạo thêm bản ghi lịch sử cho từng lần gọi
B. Save luôn từ chối nếu ID có trong bất kỳ keyspace nào
C. Save theo key có thể ghi đè tùy semantics adapter
D. Save tự đặt TTL trước khi ghi mà không cần backend hỗ trợ
Đáp án đúng: C

Câu 10. Vai trò chính của KeyValueTemplate trong Spring Data KeyValue là gì?
A. Cung cấp thao tác dữ liệu cấp thấp hơn repository qua adapter
B. Phân phối request HTTP giữa các KeyValueRepository trong cluster
C. Tạo schema SQL tự động trước khi mỗi entity được lưu
D. Cấp phát bộ nhớ ngoài heap cho mọi object Java được ánh xạ
Đáp án đúng: A

Câu 11. KeyValueOperations thường được dùng để thể hiện khái niệm nào?
A. API chuyên thiết lập kết nối TCP đến service registry
B. Một cơ chế cache annotation cho các HTTP controller
C. Bộ lọc bảo mật tự động áp dụng cho mọi key trong Map
D. Hợp đồng thao tác key-value do template triển khai
Đáp án đúng: D

Câu 12. Vai trò của KeyValueAdapter trong thiết kế Spring Data KeyValue là gì?
A. Tự động chuyển mọi query field thành câu SQL quan hệ
B. Nối abstraction lưu trữ với các thao tác của backend cụ thể
C. Cấu hình HTTP server cho việc đọc ghi entity từ xa
D. Quản lý release train cho từng dependency Spring Data
Đáp án đúng: B

Câu 13. MapKeyValueAdapter thường lưu dữ liệu dựa trên thành phần nào?
A. Database file trên ổ cứng được đồng bộ mỗi giây
B. Bảng quan hệ có transaction log và khóa ngoại
C. Map trong bộ nhớ được dùng làm nơi chứa entry
D. Object storage phân tán với replication tự động
Đáp án đúng: C

Câu 14. Khi repository dùng MapKeyValueAdapter, dữ liệu sống bao lâu theo mặc định?
A. Được giữ vĩnh viễn qua mọi lần khởi động JVM mới
B. Tự động đồng bộ sang các Pod khác cùng ứng dụng
C. Sống theo vòng đời của Map trong process hiện tại
D. Được duy trì đến khi cluster Redis xóa theo TTL
Đáp án đúng: C

Câu 15. Vì sao Map-backed repository phù hợp để thử nghiệm hơn kho lưu trữ nghiệp vụ bền vững?
A. Tự tạo cơ chế replication đủ tin cậy cho production
B. Tự sinh index phức hợp cho từng truy vấn ở runtime
C. Duy trì transaction phân tán cho mọi repository method
D. Không cần server nhưng dữ liệu mất khi process kết thúc
Đáp án đúng: D

Câu 16. Muốn kích hoạt repository dùng adapter Map, thiết lập nào cần đúng?
A. Thêm @EnableJpaRepositories để Map thành bảng SQL
B. Tạo PostgreSQL DataSource dùng chung với entity Map
C. Khai spring.jpa.hibernate.ddl-auto để cấp keyspace
D. Cấu hình repository scanning cùng adapter Map phù hợp
Đáp án đúng: D

Câu 17. Điều gì quyết định entity được đổi thành biểu diễn lưu trữ phù hợp?
A. Tên của HTTP endpoint đã đăng ký trong DispatcherServlet
B. Chỉ số TTL từ remote configuration server
C. Mapping metadata và converter của Spring Data
D. Thứ tự thread pool khởi chạy trong ApplicationContext
Đáp án đúng: C

Câu 18. Khi kiểu giá trị riêng không thể ánh xạ đúng theo mặc định, cách xử lý phù hợp?
A. Cấu hình converter thích hợp cho chiều đọc và ghi
B. Tạo keyspace phụ cho từng lần thay đổi kiểu Java
C. Dùng cache eviction để bỏ qua bước chuyển đổi dữ liệu
D. Đổi repository thành controller để tránh entity mapping
Đáp án đúng: A

Câu 19. Khi khai báo phương thức repository tìm theo thuộc tính khác ID, yếu tố nào quan trọng?
A. Mọi backend đều mặc định có B-tree index cho thuộc tính
B. Repository sẽ luôn chuyển query sang JDBC PreparedStatement
C. Khả năng query của adapter và chi phí lọc tập entry
D. findById tự động giải quyết mọi predicate của thuộc tính
Đáp án đúng: C

Câu 20. Vì sao lọc một field không nằm trong key có thể tốn kém trên Map-backed store?
A. Dữ liệu luôn bị ghi lại vào Map trong mỗi lần đọc field
B. Mọi trường phải được gửi tới một Query Service phân tán
C. Lookup theo key luôn tốn nhiều hơn quét toàn keyspace
D. Có thể phải duyệt nhiều entry nếu không có index hỗ trợ
Đáp án đúng: D

Câu 21. Khi thực hiện findAll trên một Map chứa nhiều entity, rủi ro nào cần lưu ý?
A. findAll luôn tải dữ liệu trực tiếp từ một ổ cứng xa
B. Số lượng object và thời gian duyệt có thể gây tải bộ nhớ
C. findAll tự gộp mọi keyspace bất kể entity đang truy vấn
D. findAll tự đánh dấu các document thành expired sau khi đọc
Đáp án đúng: B

Câu 22. Phân trang hoặc sắp xếp dựa trên thuộc tính cần đánh giá vấn đề nào?
A. Chi phí xử lý và mức độ hỗ trợ query từ adapter thực tế
B. Tính toàn vẹn khóa ngoại do Hibernate đang quản lý
C. Khả năng ánh xạ URL thành service ID của LoadBalancer
D. Số lượng SQL connection bắt buộc trên mỗi trang kết quả
Đáp án đúng: A

Câu 23. Trong KeyValueTemplate, vì sao keyspace là tham số quan trọng khi thao tác?
A. Keyspace thay thế ID khi mọi entity không có định danh
B. Keyspace buộc Map tạo transaction mới cho mỗi lần get
C. Tên keyspace quyết định tốc độ CPU của Java collector
D. Cùng một key có thể hiện diện trong các không gian khác nhau
Đáp án đúng: D

Câu 24. Khi đổi @KeySpace trên entity sau khi đã lưu dữ liệu, rủi ro chính là gì?
A. Mọi entry cũ tự động được chuyển sang keyspace mới
B. Map tự tạo bản sao để cân bằng tải giữa hai keyspace
C. Repository luôn giữ alias từ keyspace cũ mà không cấu hình
D. Lookup theo keyspace mới có thể không tìm thấy dữ liệu cũ
Đáp án đúng: D

Câu 25. Khi hai loại entity dùng cùng keyspace và cùng ID, điều gì cần đề phòng?
A. Map sẽ tạo hai namespace bằng tên lớp Java tự động
B. Có thể ghi đè nếu hai loại entity chia cùng keyspace
C. Mỗi entity sẽ nhận một CAS version mới để chống trùng
D. Repository tự chuyển kiểu của key để tránh mọi va chạm
Đáp án đúng: B

Câu 26. Với key-value storage, để tìm nhanh theo một giá trị không phải key, nên cân nhắc gì?
A. Thiết kế khóa hoặc cấu trúc tra cứu phụ theo nhu cầu
B. Thêm @Id lên field tìm kiếm để giữ cả ID hiện tại
C. Chỉ tăng kích thước heap để tự tạo index thuộc tính
D. Dùng HTTP cache header để tối ưu mọi query repository
Đáp án đúng: A

Câu 27. Khi dùng một ConcurrentHashMap làm backing Map, điều gì được bảo đảm ở mức cơ bản?
A. Các thao tác đơn lẻ của ConcurrentHashMap thread-safe
B. Mọi chuỗi read-modify-write trở thành transaction ACID
C. Mọi lần save entity đều tự tạo snapshot để rollback
D. Map tự đồng bộ trạng thái tới nhiều tiến trình JVM khác
Đáp án đúng: A

Câu 28. Hai thread cùng đọc rồi cập nhật một entity trên backing Map có nguy cơ nào?
A. Cả hai bắt buộc bị rollback theo một transaction phân tán
B. Dữ liệu tự đồng bộ bằng optimistic locking của Redis
C. ConcurrentHashMap tự lưu audit log cho cả hai thao tác
D. Lost update nếu không có cơ chế phối hợp cập nhật phù hợp
Đáp án đúng: D

Câu 29. Vì sao không nên xem @Version luôn đủ để bảo vệ mọi Map-backed adapter?
A. @Version luôn tự bật cluster transaction bất kể adapter
B. Xác minh adapter có hỗ trợ optimistic locking
C. Mỗi bản cập nhật tự lưu lịch sử phiên bản vào disk
D. Version field luôn được xử lý bằng SQL++ trong Map
Đáp án đúng: B

Câu 30. Khi cần thực hiện nhiều lần ghi như một đơn vị nguyên tử, cần đánh giá gì?
A. Chỉ cần dùng cùng keyspace là các lệnh cùng commit
B. Mọi KeyValueRepository cung cấp rollback xuyên process
C. Dùng cùng một @Id cho tất cả entity để tạo transaction
D. Khả năng transaction thực tế của adapter hoặc backend
Đáp án đúng: D

Câu 31. Khi tiến trình Map-backed Task bị crash, điều gì xảy ra với trạng thái chưa lưu bền vững?
A. Toàn bộ trạng thái được khôi phục từ TaskRepository tự động
B. Dữ liệu được phát lại từ HTTP request log của container
C. Các Pod khác nhận bản sao dữ liệu do JVM đã replicate
D. Dữ liệu trong heap có thể mất và không tự phục hồi sau restart
Đáp án đúng: D

Câu 32. Khi chạy hai replica với hai backing Map độc lập, cách hiểu nào đúng?
A. Hai replica tự nhìn thấy thay đổi nhờ cùng tên @KeySpace
B. Service discovery đồng bộ nội dung Map giữa các Pod
C. Các replica giữ Map riêng khi không chia sẻ dữ liệu
D. Spring Data KeyValue tự tạo quorum cho mọi write
Đáp án đúng: C

Câu 33. Nếu ứng dụng phải giữ dữ liệu sau khi khởi động lại, hướng nào phù hợp?
A. Tăng số bean repository để JVM không xóa dữ liệu cũ
B. Chọn backend bền vững hoặc chủ động thiết kế cơ chế lưu bền
C. Dùng tên keyspace cố định để Map tồn tại sau restart
D. Chỉ chuyển Map sang synchronizedMap để lưu được trên disk
Đáp án đúng: B

Câu 34. Muốn tự động hết hạn entry trong một MapKeyValueAdapter mặc định, cần lưu ý gì?
A. Mọi Map entry tự hết hạn nhờ annotation @KeySpace
B. Không nên giả định TTL sẵn có nếu chưa có cơ chế hỗ trợ
C. Spring Data KeyValue mặc định tạo timer xóa sau mỗi save
D. Mọi backing Map đều có eviction policy tích hợp sẵn
Đáp án đúng: B

Câu 35. Vì sao dùng MapKeyValueAdapter làm cache có thể cần bổ sung chính sách riêng?
A. KeyValueTemplate luôn xóa bản ghi cũ nhất khi memory đầy
B. Map tự tạo least-recently-used index theo keyspace
C. CrudRepository tự đặt TTL bằng thời gian gọi method
D. Map không mặc định có eviction theo nghiệp vụ
Đáp án đúng: D

Câu 36. Khi lượng entry tăng nhanh trong heap, tín hiệu nào nên giám sát?
A. Theo dõi số entry, heap và garbage collection
B. Số SQL transaction đang chờ ở một database không tồn tại
C. Số lần gửi Kafka event của Spring Data repository
D. Số lượng route được đăng ký bởi service discovery
Đáp án đúng: A

Câu 37. Nếu backing Map là bean singleton và không bị thay, dữ liệu Map-backed tồn tại trong khoảng nào?
A. Đến khi từng request HTTP hoàn tất rồi tự xóa entry
B. Mãi mãi dù JVM process đã dừng và host restart
C. Đến khi tên repository bị đổi trong file cấu hình
D. Sống theo vòng đời Map mà context đang giữ
Đáp án đúng: D

Câu 38. Khi tạo ApplicationContext mới với backing Map mới trong test, kết quả nào hợp lý?
A. Repository sẽ tự nạp mọi entry test cũ từ metadata
B. KeyValueTemplate sẽ luôn chia sẻ một static Map toàn JVM
C. Các entry từ context cũ không tự có trong Map mới
D. @KeySpace tự restore dữ liệu từ folder build/test
Đáp án đúng: C

Câu 39. Để bảo đảm unit test Map repository độc lập, nên làm gì?
A. Tạo Map sạch hoặc reset dữ liệu giữa các test case
B. Dùng chung Map lâu dài và phụ thuộc thứ tự chạy test
C. Chỉ đổi tên test method để làm mới namespace
D. Tắt assertions về dữ liệu để tránh phụ thuộc context
Đáp án đúng: A

Câu 40. Khi kiểm thử hai entity có cùng ID ở hai keyspace, assertion nào có giá trị?
A. Hai entity bắt buộc dùng chung một bản ghi trong Map
B. Truy xuất đúng entity ở từng keyspace mà không lẫn kết quả
C. findById cần trả mọi entity có cùng ID từ mọi keyspace
D. Repository phải tự thay đổi ID của entity được ghi sau
Đáp án đúng: B

Câu 41. Khi test thao tác update bị lỗi giữa nhiều bước, cần kiểm tra điều gì?
A. MapKeyValueAdapter tự rollback toàn bộ bước đã thành công
B. Spring Data Commons tự thêm transaction log ở JVM heap
C. Trạng thái cuối và cách ứng dụng xử lý update dở dang
D. Một lỗi giữa chừng tự hoàn tác các request external API
Đáp án đúng: C

Câu 42. Khi thêm kho khóa–giá trị mới vào Spring Data KeyValue, hướng mở rộng nào phù hợp?
A. Viết adapter phù hợp các thao tác lưu và query
B. Viết một controller kế thừa JdbcTemplate để tạo keyspace
C. Đổi toàn bộ entity thành JPA @Table mà không adapter
D. Gắn @KeySpace lên interface Repository để mở backend
Đáp án đúng: A

Câu 43. Khi custom adapter tích hợp remote store, phần nào cần được kiểm soát?
A. Chỉ cần tạo bean repository vì adapter không gọi backend
B. Ánh xạ keyspace/key, lỗi backend và semantics đọc ghi
C. Mọi query bắt buộc dịch được sang ANSI SQL trước khi chạy
D. Mọi lỗi mạng được tự động biến thành kết quả thành công
Đáp án đúng: B

Câu 44. Tại sao không thể suy ra backend mới có durability chỉ vì sử dụng KeyValueTemplate?
A. Template luôn đồng bộ ghi ra ổ đĩa cho từng lệnh save
B. Durability phụ thuộc backend của adapter
C. @Id tự bật replication từ một bản thành ba bản
D. Keyspace luôn tạo snapshot xuyên JVM mỗi phút
Đáp án đúng: B

Câu 45. Khi chuyển từ Map adapter sang kho dữ liệu có persistence, điều gì cần kiểm thử lại?
A. Thử lại mapping, keyspace, query, lỗi và concurrency
B. Chỉ kiểm tra bean name vì CRUD luôn giống nhau hoàn toàn
C. Bỏ test lưu và đọc vì template che mọi khác biệt
D. Chỉ đo số class trên classpath sau khi thêm starter
Đáp án đúng: A

Câu 46. Để tránh lộ dữ liệu khi log thao tác key-value, nguyên tắc nào phù hợp?
A. In toàn bộ backing Map khi truy vấn không tìm thấy key
B. Gắn user token làm tag metrics cho mỗi lần repository save
C. Che nội dung nhạy cảm trong key, value và thông tin truy vết
D. Ghi nguyên mật khẩu vào log khi converter ném exception
Đáp án đúng: C

Câu 47. Một ứng dụng cần dữ liệu sống lâu, query phong phú và nhiều replica nên chọn cách nào?
A. Dùng MapKeyValueAdapter cục bộ trên từng replica độc lập
B. Đánh giá backend bền vững có query và replication phù hợp
C. Chỉ đổi @KeySpace để tự bật index và đồng bộ dữ liệu
D. Tăng heap mãi để Map tự bảo đảm nhất quán nhiều node
Đáp án đúng: B

Câu 48. Khi gọi deleteById trong repository Map-backed, cách hiểu nào phù hợp?
A. Xóa mọi entry cùng ID ở mọi keyspace trên JVM
B. Đặt TTL rồi chờ garbage collector xóa bản ghi
C. Xóa key trong keyspace của repository đang dùng
D. Tạo tombstone bền vững để các replica đồng bộ
Đáp án đúng: C
