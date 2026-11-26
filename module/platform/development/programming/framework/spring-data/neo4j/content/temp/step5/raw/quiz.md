Câu 1. Trong mô hình Neo4j, node thường biểu diễn thành phần nào?
A. Thực thể có label và các property tương ứng
B. Một bảng liên kết có khóa ngoại hai chiều
C. Một trang dữ liệu cố định của Query Service
D. Một transaction chứa toàn bộ graph đang xử lý
Đáp án đúng: A

Câu 2. Trong Spring Data Neo4j, @Node trên lớp miền thường dùng để làm gì?
A. Tạo quan hệ có hướng giữa hai bean Spring
B. Đặt loại transaction cho mọi repository query
C. Đánh dấu entity ánh xạ với node trong đồ thị
D. Khai báo index tự động cho toàn bộ thuộc tính
Đáp án đúng: C

Câu 3. Annotation @Id trên node entity xác định vai trò của thuộc tính nào?
A. Tên relationship type nối entity với node khác
B. Thuộc tính định danh node khi ánh xạ entity
C. Tên database được chọn cho mọi câu Cypher
D. Giá trị timeout của lần ghi transaction mới
Đáp án đúng: B

Câu 4. Khi kết hợp @Id với @GeneratedValue, mục tiêu chính là gì?
A. Tự sinh constraint unique cho tất cả field
B. Tự tạo relationship tới node vừa được lưu
C. Tự tăng version khi mọi Cypher query hoàn tất
D. Cách sinh giá trị ID cho entity khi lưu
Đáp án đúng: D

Câu 5. Muốn ánh xạ tên property Java sang tên property Neo4j khác, nên chọn gì?
A. @Property để cấu hình tên thuộc tính trên node
B. @Node để đổi tên từng thuộc tính của entity
C. @Id để chuyển toàn bộ property sang metadata
D. @Relationship để ghi đè alias của thuộc tính
Đáp án đúng: A

Câu 6. Annotation @Relationship trên một field thường biểu đạt điều gì?
A. Quan hệ giữa node hiện tại với node mục tiêu
B. Điều kiện filter của mọi truy vấn Cypher query
C. Một index riêng cho các property trên entity
D. Transaction boundary cho toàn bộ thao tác save
Đáp án đúng: A

Câu 7. Trong @Relationship, tham số direction có ý nghĩa gì?
A. Quy định thứ tự gọi hàm repository theo thời gian
B. Quy định thứ tự các node trả trong Cypher RETURN
C. Đặt chiều replicate của cluster Neo4j khi ghi
D. Mô tả hướng cạnh so với node entity đang ánh xạ
Đáp án đúng: D

Câu 8. Khi quan hệ có thuộc tính như since hay role, cách mapping nào phù hợp?
A. Gắn @Node lên field since để tạo node thuộc tính mới
B. Đổi field @Id thành Map chứa các quan hệ bên ngoài
C. Dùng lớp @RelationshipProperties để giữ metadata quan hệ
D. Gắn @GeneratedValue lên relationship type để lưu role
Đáp án đúng: C

Câu 9. Trong lớp @RelationshipProperties, @TargetNode giúp biểu thị điều gì?
A. Node đối tác ở đầu còn lại của relationship
B. Node đang giữ các property của chính lớp hiện tại
C. Tên database được Neo4j Driver dùng khi kết nối
D. Nhãn index mà transaction phải tạo trước khi save
Đáp án đúng: A

Câu 10. Để lưu thời điểm bắt đầu hợp tác của hai nhân viên, thiết kế nào đúng?
A. Đặt since trên relationship của hai nhân viên
B. Lưu since vào @Id của cả hai node để dùng chung
C. Lưu since trong label của node để tối ưu MATCH
D. Lưu since như tên relationship type mới mỗi ngày
Đáp án đúng: A

Câu 11. Khi một user có nhiều quan hệ FOLLOWS, field entity nào thường phù hợp?
A. Một biến long giữ số lượng node đang follow
B. Tập node đích với @Relationship phù hợp
C. Một @Property String chứa toàn bộ Cypher query
D. Một @Id chung cho user và mọi node được follow
Đáp án đúng: B

Câu 12. Khi hai node liên kết bằng cạnh có hướng, truy vấn muốn đảo chiều phải làm gì?
A. Đổi label của node để Neo4j tự đảo hướng cạnh
B. Thêm @GeneratedValue vào field relationship của Java
C. Dùng mẫu relationship với chiều traversal tương ứng
D. Thay mọi cạnh bằng property cùng tên trên hai node
Đáp án đúng: C

Câu 13. Vì sao cần giới hạn phần graph được tải cùng một aggregate lớn?
A. Mọi relationship được Neo4j cache trong JVM vô thời hạn
B. Đọc quá nhiều relationship có thể tăng bộ nhớ và độ trễ
C. @Node bắt buộc load toàn bộ database trước khi query
D. Tải graph sâu sẽ tự mở thêm database riêng trong Neo4j
Đáp án đúng: B

Câu 14. Cypher nào chỉ tìm node Person theo id mà không tạo mới nếu thiếu?
A. MERGE (p:Person {id: $id}) RETURN p
B. MATCH (p:Person {id: $id}) RETURN p
C. CREATE (p:Person {id: $id}) RETURN p
D. MATCH (p:Person {email: $id}) RETURN p
Đáp án đúng: B

Câu 15. Mẫu Cypher (a:User)-[:FOLLOWS]->(b:User) biểu diễn gì?
A. User b có quan hệ FOLLOWS hướng tới user a
B. Hai node User buộc có cùng giá trị thuộc tính
C. Quan hệ FOLLOWS không xét hướng khi lọc dữ liệu
D. User a có quan hệ FOLLOWS hướng tới user b
Đáp án đúng: D

Câu 16. Mệnh đề WHERE trong Cypher thường phục vụ nhiệm vụ nào?
A. Tạo cạnh mới cho mọi node đã khớp với MATCH
B. Ghi lại metadata transaction sau khi RETURN
C. Lọc kết quả dựa trên điều kiện được khai báo
D. Định nghĩa schema constraint mới trong database
Đáp án đúng: C

Câu 17. OPTIONAL MATCH phù hợp khi cần xử lý trường hợp nào?
A. Bắt buộc node phải có đầy đủ mọi relationship
B. Trả node chính dù không có relationship tùy chọn
C. Tạo node bị thiếu trước khi xử lý mệnh đề WITH
D. Chuyển truy vấn read sang lệnh write transaction
Đáp án đúng: B

Câu 18. So với MATCH, CREATE trong Cypher có đặc điểm gì?
A. Tạo pattern mới thay vì chỉ tìm pattern có sẵn
B. Tìm node có cùng thuộc tính rồi bỏ qua thao tác ghi
C. Đọc index để phát hiện duplicate và tự từ chối
D. Tự mở transaction hai pha cho mọi node đã match
Đáp án đúng: A

Câu 19. Khi MERGE một node theo business key, cơ chế nào được mong đợi?
A. Chỉ chèn thêm node và bỏ qua tìm kiếm trước đó
B. Tự xóa bản sao node có trùng thuộc tính ở nơi khác
C. Tìm pattern phù hợp hoặc tạo mới khi chưa có
D. Tự tạo bookmark để read không cần index lần sau
Đáp án đúng: C

Câu 20. Vì sao MERGE theo business key nên đi cùng uniqueness constraint?
A. MERGE luôn ngầm tạo constraint cho từng property
B. Constraint thay thế được điều kiện MATCH của mọi query
C. Constraint hỗ trợ tính duy nhất khi ghi đồng thời
D. Constraint buộc mọi relationship dùng chung một ID
Đáp án đúng: C

Câu 21. Để cập nhật property status của node đã MATCH, dùng mệnh đề nào?
A. MATCH n.status = $status để thay nội dung node
B. UNWIND n.status = $status để cập nhật field
C. RETURN n.status = $status để lưu state mới
D. SET n.status = $status để gán giá trị mới
Đáp án đúng: D

Câu 22. Để xóa node vẫn còn relationship, mệnh đề nào thích hợp?
A. DELETE n để Neo4j tự bỏ qua các quan hệ hiện có
B. MERGE n để đánh dấu xóa khi transaction commit
C. UNWIND n để xóa node và tất cả nhãn của nó
D. DETACH DELETE để xóa node kèm các quan hệ
Đáp án đúng: D

Câu 23. WITH trong Cypher thường được dùng với mục đích nào?
A. Chuyển biến cùng kết quả trung gian sang bước sau
B. Đặt mật khẩu kết nối cho từng phần của một MATCH
C. Biến mọi mệnh đề read thành transaction ghi mới
D. Tạo uniqueness constraint cho từng biến đã khai báo
Đáp án đúng: A

Câu 24. UNWIND trong Cypher hữu ích khi xử lý dữ liệu gì?
A. Gộp nhiều node thành một JSON property duy nhất
B. Tách phần tử list thành từng hàng trong Cypher
C. Đặt thứ tự node theo khóa ID cho toàn bộ query
D. Tự tính đường đi ngắn nhất giữa mọi cặp node
Đáp án đúng: B

Câu 25. Khi MATCH tạo nhiều hàng do một node có nhiều quan hệ, cách đếm node duy nhất nào phù hợp?
A. Dùng count(n) vì Cypher tự gộp node trùng nhau
B. Dùng collect(n) để ép COUNT trả số phần tử riêng
C. Dùng LIMIT 1 trước COUNT cho toàn bộ graph
D. Dùng count(DISTINCT n) để loại các bản ghi lặp
Đáp án đúng: D

Câu 26. Với pattern độ dài biến thiên, vì sao nên đặt giới hạn số hop?
A. Bảo đảm query không sử dụng index trên node đầu
B. Buộc mọi node phải có cùng label trong traversal
C. Tránh số đường đi và chi phí duyệt tăng quá lớn
D. Tự khóa graph để ngăn concurrent transaction
Đáp án đúng: C

Câu 27. Vì sao hai MATCH pattern không liên kết có thể gây chậm query?
A. Chúng có thể tạo tích Descartes của các tập node
B. Cypher sẽ tự sinh relationship nối hai tập kết quả
C. Neo4j buộc chạy theo thứ tự khóa ID của các node
D. Tất cả pattern sẽ chuyển sang index lookup tức thì
Đáp án đúng: A

Câu 28. Khi Cypher nhận email từ API, cách nào giảm nguy cơ injection?
A. Chèn email vào label trước khi gọi Neo4j Driver
B. Bind email qua parameter thay vì nối chuỗi truy vấn
C. Đặt email vào tên relationship type do user nhập
D. Bỏ parameter và dùng LIMIT để giới hạn dữ liệu
Đáp án đúng: B

Câu 29. Khi ứng dụng phải chọn label từ input bên ngoài, nguyên tắc nào an toàn?
A. Nối trực tiếp input vào câu Cypher để giảm parse cost
B. Bỏ kiểm tra label nếu query chỉ được dùng để đọc
C. Đổi tên parameter thành label để tự cấp quyền dữ liệu
D. Ràng buộc vào tập label cho phép và xử lý Cypher an toàn
Đáp án đúng: D

Câu 30. Khi phân trang Cypher bằng SKIP và LIMIT, vì sao nên dùng ORDER BY ổn định?
A. SKIP tự tạo index theo thứ tự property vừa truyền
B. Giảm kết quả trùng hoặc thiếu vì thứ tự không xác định
C. LIMIT bảo đảm dữ liệu không thay đổi giữa các trang
D. ORDER BY biến toàn bộ transaction thành snapshot read
Đáp án đúng: B

Câu 31. findById trong Neo4jRepository thường dựa vào thông tin nào?
A. Tên relationship của entity được chọn trong Cypher
B. Giá trị @Version của tất cả node đã đọc gần đây
C. Định danh entity được mapping bằng @Id
D. Trường firstName dù entity khai @Id ở thuộc tính khác
Đáp án đúng: C

Câu 32. Một derived repository method tìm theo họ cần điều kiện gì?
A. Tên method phải luôn chứa toàn bộ câu Cypher đầy đủ
B. Tất cả node phải có @RelationshipProperties để tìm theo họ
C. Tên property mapping hợp lệ và dữ liệu có thể truy vấn
D. Phải tạo database mới cho từng phương thức repository
Đáp án đúng: C

Câu 33. Khi cần truy vấn graph không biểu diễn tốt bằng derived method, dùng gì?
A. Khai báo @Query với Cypher và parameter phù hợp
B. Chỉ đổi @Node thành @Relationship để query theo cạnh
C. Thêm @GeneratedValue trên repository interface
D. Gọi findAll rồi lọc trong bộ nhớ cho mọi trường hợp
Đáp án đúng: A

Câu 34. Neo4jClient thường hữu ích trong trường hợp nào?
A. Thay thế driver protocol bằng HTTP thuần cho mọi query
B. Tạo index tự động cho mọi property trong entity
C. Thực hiện câu Cypher tùy biến bằng API fluent phù hợp
D. Bật retry cho tất cả transaction khi context startup
Đáp án đúng: C

Câu 35. Neo4jTemplate trong Spring Data Neo4j chủ yếu cung cấp gì?
A. Một bộ cron scheduler cho các truy vấn graph dài
B. Một service registry tìm database instance gần nhất
C. Một nơi lưu cache toàn bộ Cypher query đã chạy
D. Thao tác dữ liệu có tích hợp ánh xạ entity Neo4j
Đáp án đúng: D

Câu 36. Với custom @Query cần dựng graph entity có quan hệ, điều gì nên được trả về?
A. Chỉ trả về count(*) rồi mapper suy ra toàn bộ relationship
B. Root node và các quan hệ/target cần thiết để mapper dựng graph
C. Chỉ trả về label name mà không có node hay relationship
D. Chỉ trả về độ dài path rồi mapper gọi thêm mọi dữ liệu
Đáp án đúng: B

Câu 37. Trong Spring Data Neo4j, @Transactional giúp xử lý điều gì?
A. Tự tạo index cho mọi Cypher đã chạy trong phương thức
B. Bảo đảm HTTP call ngoài Neo4j rollback theo graph
C. Buộc mọi truy vấn chỉ đọc trên một node leader
D. Gom các thao tác dữ liệu vào phạm vi transaction
Đáp án đúng: D

Câu 38. Khi transaction chứa hai lần ghi và lỗi làm rollback, điều gì được kỳ vọng?
A. Các thao tác trong transaction cùng commit hoặc rollback
B. Lần ghi đầu sẽ luôn được commit dù lần thứ hai lỗi
C. Neo4j sẽ tự chuyển thao tác còn lại thành retry HTTP
D. Transaction chỉ có tác dụng với lệnh MATCH không ghi
Đáp án đúng: A

Câu 39. Vì sao không nên gọi dịch vụ thanh toán trực tiếp trong callback transaction có retry?
A. Neo4j sẽ hoàn tác HTTP payment khi transaction rollback
B. Cypher tự chặn mọi HTTP request trong callback Java
C. HTTP side effect không thể rollback cùng Neo4j
D. Callback luôn chạy đúng một lần bất kể xung đột
Đáp án đúng: C

Câu 40. Dùng @Version trên node entity có thể hỗ trợ cơ chế nào?
A. Phát hiện xung đột cập nhật bằng optimistic locking
B. Cấp số thứ tự database để chọn query router phù hợp
C. Tạo relationship versioned giữa các node vừa đọc
D. Đặt TTL của node dựa trên số lần cập nhật entity
Đáp án đúng: A

Câu 41. Hai request cùng đọc một node version cũ rồi lưu, tình huống nào có thể xảy ra?
A. Neo4j bắt buộc gộp cả hai thay đổi thành một commit
B. Mọi lần save sẽ tạo node mới để tránh version conflict
C. Driver tự sửa business key để tăng tốc transaction
D. Một lần ghi bị từ chối do version không còn khớp
Đáp án đúng: D

Câu 42. Bookmark trong Neo4j driver thường hỗ trợ mục tiêu nào?
A. Tạo secondary index theo vị trí node được bookmark
B. Khóa một relationship để ngăn mọi cập nhật đồng thời
C. Thay @Id trong repository bằng vị trí dữ liệu vật lý
D. Duy trì causal consistency giữa các session liên tiếp
Đáp án đúng: D

Câu 43. Index trên property thường đem lại hiệu quả nào?
A. Buộc mọi MATCH phải đọc toàn bộ relationship trước
B. Tự bảo đảm transaction nhiều node thành exactly-once
C. Giúp tìm node theo điều kiện phù hợp mà giảm scan
D. Làm dữ liệu label được mã hóa trước khi trả kết quả
Đáp án đúng: C

Câu 44. Unique constraint trên email của node User phục vụ nhu cầu nào?
A. Tự thêm email vào mọi node chưa có thuộc tính này
B. Đảm bảo mỗi user chỉ có một relationship trong graph
C. Cho phép đọc email mà bỏ qua phân quyền database
D. Ngăn hai node cùng label có email trùng hợp lệ
Đáp án đúng: D

Câu 45. EXPLAIN và PROFILE khác nhau thế nào khi phân tích Cypher?
A. EXPLAIN tự tạo index; PROFILE xóa index chưa dùng
B. EXPLAIN lên kế hoạch; PROFILE chạy và đo số liệu
C. EXPLAIN chỉ chạy write; PROFILE chỉ dùng read query
D. EXPLAIN bắt buộc commit; PROFILE bắt buộc rollback
Đáp án đúng: B

Câu 46. Khi tối ưu truy vấn nhiều hop, cần kiểm tra tín hiệu nào?
A. Theo dõi số hàng trung gian, index và traversal
B. Tên bean controller và số lượng HTTP thread rảnh
C. Số lần JVM garbage collect sau khi compile project
D. Tên file repository được Spring tải trong IDE
Đáp án đúng: A

Câu 47. Trong ReactiveNeo4jRepository, kiểu trả về nào phù hợp cho nhiều node?
A. Mono trả tất cả entity như một list mặc định
B. Flux phát nhiều entity theo luồng bất đồng bộ
C. Optional chặn thread đến khi query hoàn thành
D. List trả trực tiếp trước khi subscription được tạo
Đáp án đúng: B

Câu 48. Để kiểm thử @Query phức tạp ánh xạ quan hệ, cách nào đáng tin cậy?
A. Chỉ assert @Query có mặt mà không thực thi Cypher
B. Chạy query với Neo4j Testcontainers và dữ liệu mẫu
C. Mock repository trả entity cố định không có quan hệ
D. Chỉ kiểm tra ApplicationContext khởi tạo bean repository
Đáp án đúng: B
