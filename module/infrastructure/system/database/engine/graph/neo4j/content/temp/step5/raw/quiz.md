Câu 1. Trong property graph của Neo4j, thành phần nào có thể mang property?
A. Chỉ node được gắn property trong property graph.
B. Node và relationship đều có thể mang property.
C. Chỉ relationship được gắn property trong graph.
D. Chỉ label mới có thể chứa property trong graph.
Đáp án đúng: B

Câu 2. Trong Neo4j, label `:Person` trên node có vai trò chính nào?
A. Định danh duy nhất node, thay cho thuộc tính ID.
B. Biểu thị chiều đi của relationship giữa các node.
C. Phân nhóm node để lọc và áp dụng schema theo label.
D. Lưu toàn bộ property của node dưới dạng văn bản.
Đáp án đúng: C

Câu 3. Với mẫu Cypher `(a)-[:FOLLOWS]->(b)`, hướng relationship được hiểu ra sao?
A. Relationship `FOLLOWS` đi từ node `b` đến node `a`.
B. Relationship `FOLLOWS` tồn tại đồng thời ở hai chiều.
C. Relationship `FOLLOWS` không có hướng lưu trong graph.
D. Relationship `FOLLOWS` đi từ node `a` đến node `b`.
Đáp án đúng: D

Câu 4. Mệnh đề `MATCH (p:Person {id: $id})` trong Cypher tìm dữ liệu theo điều kiện nào?
A. Node có loại relationship `Person` và ID nội bộ bằng tham số.
B. Node có tên biến `Person` và property `id` bất kỳ.
C. Node có label `id` và property `Person` bằng tham số.
D. Node có label `Person` và property `id` bằng tham số.
Đáp án đúng: D

Câu 5. `OPTIONAL MATCH` xử lý thế nào khi một relationship cần tìm không tồn tại?
A. Giữ hàng đầu vào; biến không khớp nhận `null`.
B. Loại hàng đầu vào nếu relationship không tồn tại.
C. Tạo relationship còn thiếu để hoàn chỉnh mẫu truy vấn.
D. Báo lỗi ngay khi relationship tùy chọn không tồn tại.
Đáp án đúng: A

Câu 6. Với `MERGE (p:Person {email: $email})`, hành vi cốt lõi của `MERGE` là gì?
A. Luôn tạo một node mới dù đã có node phù hợp.
B. Luôn cập nhật mọi property của node đã tìm thấy.
C. Tìm mẫu phù hợp; nếu không thấy thì tạo mẫu đó.
D. Chỉ tìm node hiện hữu và không bao giờ tạo node.
Đáp án đúng: C

Câu 7. Constraint duy nhất cho `Person.email` chủ yếu đảm bảo điều gì?
A. Không có hai node `Person` trùng `email` khác null.
B. Mọi node `Person` đều bắt buộc phải có property `email`.
C. Mọi node đều có property `email` duy nhất toàn graph.
D. Mỗi giá trị `email` được tự sinh khi tạo node mới.
Đáp án đúng: A

Câu 8. Khác biệt cơ bản của `CREATE` so với `MERGE` khi tạo node là gì?
A. `CREATE` chỉ tạo mẫu khi không tìm thấy mẫu trùng.
B. `CREATE` cập nhật mẫu hiện có nếu property thay đổi.
C. `CREATE` tạo mẫu mới mà không tìm mẫu đã tồn tại.
D. `CREATE` bắt buộc dùng constraint trước khi tạo node.
Đáp án đúng: C

Câu 9. Khi truy vấn Neo4j từ ứng dụng, lợi ích chính của tham số `$name` là gì?
A. Cho phép đổi tên label theo giá trị tham số tự động.
B. Bỏ qua kiểm tra quyền truy cập đối với dữ liệu nhập.
C. Tách giá trị khỏi Cypher và giúp tái sử dụng kế hoạch.
D. Tạo index tạm cho property có tham số trong câu lệnh.
Đáp án đúng: C

Câu 10. `UNWIND $rows AS row` trong Cypher thường dùng để làm gì?
A. Biến các phần tử của danh sách thành các hàng.
B. Gom toàn bộ hàng kết quả thành một danh sách.
C. Loại các phần tử trùng lặp khỏi danh sách đầu vào.
D. Sắp xếp các phần tử của danh sách theo thứ tự.
Đáp án đúng: A

Câu 11. Với `WITH p.city AS city, count(*) AS n`, Cypher tính `n` theo cách nào?
A. Đếm số hàng toàn truy vấn rồi gán cho từng `city`.
B. Đếm số relationship của từng node đang mang `city`.
C. Đếm số property của mỗi node có giá trị `city`.
D. Đếm hàng theo từng giá trị `city` được nhóm.
Đáp án đúng: D

Câu 12. `RETURN DISTINCT p.city` có tác dụng gì đối với kết quả?
A. Loại các giá trị `city` trùng trong kết quả trả về.
B. Xóa các node `p` có cùng giá trị `city` trong graph.
C. Chỉ trả các node có ràng buộc duy nhất trên `city`.
D. Tạo một unique constraint tạm thời trên `city`.
Đáp án đúng: A

Câu 13. Mẫu relationship `[:KNOWS*1..3]` biểu thị độ dài đường đi nào?
A. Các đường đi gồm chính xác ba relationship `KNOWS`.
B. Đường đi gồm từ một đến ba relationship `KNOWS`.
C. Các đường đi gồm từ không đến ba relationship `KNOWS`.
D. Các đường đi gồm từ ba relationship `KNOWS` trở lên.
Đáp án đúng: B

Câu 14. Trong Cypher, `shortestPath((a)-[:ROAD*]-(b))` ưu tiên đường đi theo tiêu chí nào?
A. Ít bước relationship nhất trong mẫu được xét.
B. Nhỏ nhất theo tổng trọng số `cost` trên các cạnh.
C. Nhỏ nhất theo tổng thời gian lưu trong các node.
D. Ít node có property nhất trong đường đi truy vấn.
Đáp án đúng: A

Câu 15. Mẫu Cypher `(a)-[:KNOWS]-(b)` khác mẫu có mũi tên ở điểm nào?
A. Tạo một relationship vật lý không có hướng trong graph.
B. Yêu cầu tồn tại đồng thời hai relationship ngược chiều.
C. Chỉ khớp các relationship nối một node với chính nó.
D. Khớp relationship theo cả hai hướng khi duyệt mẫu.
Đáp án đúng: D

Câu 16. Khi xóa node vẫn đang có relationship, cú pháp nào xóa được cả node và quan hệ nối?
A. `DELETE n` tự xóa node cùng mọi relationship đang nối.
B. `REMOVE n` loại node cùng các relationship hiện có.
C. `DROP n` xóa hẳn node và các relationship đang nối.
D. `DETACH DELETE n` xóa node và các quan hệ đang nối.
Đáp án đúng: D

Câu 17. Vì sao traversal từ node có bậc rất cao dễ làm truy vấn chậm?
A. Neo4j phải tạo index mới cho mỗi cạnh được duyệt.
B. Số nhánh mở rộng tăng mạnh khi duyệt nhiều bước.
C. Mỗi bước duyệt đều cần mở một kết nối mạng mới.
D. Mọi node liên quan phải được ghi lại vào transaction.
Đáp án đúng: B

Câu 18. Index trên label và property thường giúp Cypher trong tình huống nào?
A. Tăng tốc mọi phép duyệt dù không có điều kiện lọc.
B. Tự động đảm bảo các property được lập chỉ mục duy nhất.
C. Loại bỏ nhu cầu dùng label trong các mẫu truy vấn.
D. Tìm node đầu vào theo bộ lọc property có tính chọn lọc.
Đáp án đúng: D

Câu 19. Điểm khác nhau chính giữa index thông thường và unique constraint là gì?
A. Index chặn trùng; unique constraint chỉ hỗ trợ truy xuất.
B. Cả hai luôn bắt buộc property có giá trị khác null.
C. Cả hai đều buộc mỗi node có đúng một relationship.
D. Index tăng tốc tìm kiếm; constraint còn chặn trùng.
Đáp án đúng: D

Câu 20. Đặt `EXPLAIN` trước câu Cypher thường cho biết điều gì?
A. Số hàng thực tế mỗi operator sau khi chạy truy vấn.
B. Các property vừa được ghi bởi câu truy vấn đó.
C. Kế hoạch thực thi ước lượng mà không chạy truy vấn.
D. Nội dung cache thực tế đã dùng sau khi chạy truy vấn.
Đáp án đúng: C

Câu 21. Đặt `PROFILE` trước câu Cypher thường hỗ trợ điều gì?
A. Chạy query và xem hàng thực tế cùng số liệu thực thi.
B. Chỉ dự đoán kế hoạch truy vấn mà không chạy câu lệnh.
C. Tự tạo index theo operator có chi phí lớn nhất.
D. Tự sửa điều kiện `MATCH` để giảm số kết quả.
Đáp án đúng: A

Câu 22. Operator `CartesianProduct` trong query plan thường gợi ý tình huống nào?
A. Các mẫu MATCH luôn được nối bằng cùng một biến node.
B. Các mẫu MATCH độc lập kết hợp mọi cặp hàng kết quả.
C. Kết quả đã được nhóm theo một property có index.
D. Cypher đã loại hàng trùng trước khi chạy expansion.
Đáp án đúng: B

Câu 23. Tác động nào có thể xảy ra khi viết `WHERE toLower(n.email) = $email` với index trên `n.email`?
A. Index chắc chắn tự chuyển mọi giá trị thành chữ thường.
B. Hệ thống chắc chắn tạo full-text index cho `n.email`.
C. Hàm trên property có thể khiến index seek khó được dùng.
D. Hàm sẽ cập nhật property `email` thành chữ thường.
Đáp án đúng: C

Câu 24. Sau `OPTIONAL MATCH ...` không có kết quả, khác biệt giữa `count(r)` và `count(*)` là gì?
A. `count(r)` đếm hàng null; `count(*)` bỏ hàng null.
B. Cả hai luôn đếm bằng số relationship toàn database.
C. Cả hai đều loại hàng chưa khớp trước khi đếm.
D. `count(r)` bỏ giá trị null; `count(*)` vẫn đếm hàng.
Đáp án đúng: D

Câu 25. `LOAD CSV WITH HEADERS` trong Neo4j giúp xử lý nguồn dữ liệu như thế nào?
A. Đọc CSV và truy cập trường mỗi hàng theo tên cột.
B. Đọc CSV và tự tạo unique constraint trên mọi cột.
C. Đọc CSV và tự phát hiện kiểu property cho mọi cột.
D. Đọc CSV và tự tạo relationship theo tên mỗi cột.
Đáp án đúng: A

Câu 26. Trường hợp nào phù hợp với `neo4j-admin database import`?
A. Nhập CSV vào database đang phục vụ truy vấn trực tuyến.
B. Thực hiện transaction cập nhật online với commit từng dòng.
C. Nhập khối lượng CSV lớn để khởi tạo database mới.
D. Khôi phục database từ tệp backup của công cụ sao lưu.
Đáp án đúng: C

Câu 27. Vì sao nên chia quá trình nạp hàng triệu hàng CSV thành nhiều transaction?
A. Bảo đảm mọi hàng được commit nguyên tử cùng một lần.
B. Giảm dữ liệu giữ trong một transaction và dễ xử lý lỗi.
C. Buộc tất cả relationship nằm trong cùng một transaction.
D. Tránh hoàn toàn việc dùng index trong quá trình nhập.
Đáp án đúng: B

Câu 28. Khi hai node `a`, `b` đã được tìm thấy, cách tránh tạo lặp relationship `R` giữa chúng là gì?
A. Dùng `CREATE (a)-[:R]->(b)` mỗi lần nhận bản ghi.
B. Dùng `MATCH (a)-[:R]->(b)` để tạo quan hệ còn thiếu.
C. Dùng `SET (a)-[:R]->(b)` để ghi quan hệ mới.
D. Dùng `MERGE (a)-[:R]->(b)` khi hai node đã ràng buộc.
Đáp án đúng: D

Câu 29. Với Neo4j Java Driver, cách quản lý đối tượng `Driver` thường được khuyến nghị là gì?
A. Tái sử dụng Driver cho ứng dụng và đóng khi dừng.
B. Tạo Driver mới mỗi request để cô lập các phiên truy cập.
C. Tạo Driver riêng theo mỗi thread để tránh tranh chấp.
D. Dùng chung một Session toàn ứng dụng, thay cho Driver.
Đáp án đúng: A

Câu 30. Với Neo4j Java Driver, thực hành đúng khi dùng `Session` trong nhiều thread là gì?
A. Dùng một Session chung vì Session an toàn đa luồng.
B. Mỗi tác vụ dùng Session ngắn hạn riêng, không chia sẻ.
C. Mỗi câu lệnh phải mở Driver mới thay vì mở Session.
D. Mỗi thread phải chia sẻ cùng transaction đang mở.
Đáp án đúng: B

Câu 31. Lợi ích của managed transaction như `executeWrite()` trong Neo4j Java Driver là gì?
A. Driver có thể thử lại transaction khi gặp lỗi tạm thời.
B. Driver tự tạo index theo các property vừa ghi.
C. Driver chạy mọi transaction mà không cần commit.
D. Driver tự lưu transaction thành backup sau mỗi lần chạy.
Đáp án đúng: A

Câu 32. Vì sao cần xử lý `Result` trước khi đóng `Session` trong Neo4j Java Driver?
A. Result có thể được đọc dần khi Session còn mở.
B. Result luôn được nạp đủ khi `session.run()` trả về.
C. Session đóng sẽ tự cache các record còn chưa đọc.
D. Session đóng không ảnh hưởng việc duyệt Result sau đó.
Đáp án đúng: A

Câu 33. Bookmark trong Neo4j Driver chủ yếu giúp đảm bảo điều gì?
A. Mọi phiên đều được chuyển đến cùng một cluster member.
B. Phiên đọc sau thấy các lần ghi trước theo thứ tự.
C. Bookmark khóa cứng dữ liệu trong suốt các phiên đọc.
D. Bookmark đảm bảo không có transaction nào bị rollback.
Đáp án đúng: B

Câu 34. Trong Spring Data Neo4j, `@Node` thường đánh dấu thành phần nào?
A. Một phương thức Java tạo kết nối TCP vào Neo4j.
B. Một lớp đối tượng được ánh xạ thành node của graph.
C. Một thuộc tính Java chứa câu truy vấn Cypher thô.
D. Một lớp ánh xạ kết quả truy vấn mà không lưu vào graph.
Đáp án đúng: B

Câu 35. Trong Spring Data Neo4j, `@Relationship` trên field có chức năng gì?
A. Đánh dấu property của node cần unique constraint.
B. Gắn nhãn node mặc định cho tất cả entity của ứng dụng.
C. Cấu hình hướng lan truyền transaction giữa hai entity.
D. Ánh xạ quan hệ giữa entity đang xét và entity liên quan.
Đáp án đúng: D

Câu 36. Trong entity Spring Data Neo4j, cặp `@Id` và `@GeneratedValue` thể hiện điều gì?
A. Đánh dấu một label và yêu cầu sinh index tự động.
B. Đánh dấu định danh và yêu cầu cơ chế sinh giá trị ID.
C. Đánh dấu relationship và yêu cầu tạo hai chiều.
D. Đánh dấu transaction và yêu cầu commit tự động.
Đáp án đúng: B

Câu 37. `Neo4jRepository` của Spring Data Neo4j thường cung cấp khả năng nào?
A. Quản lý tiến trình Neo4j server cùng mọi phiên truy cập.
B. Tạo index và constraint trong graph khi ứng dụng khởi động.
C. Các thao tác CRUD và phương thức truy vấn theo repository.
D. Thay thế Cypher bằng các lệnh SQL do Hibernate sinh.
Đáp án đúng: C

Câu 38. Với Spring Data Neo4j, `@Transactional` giúp xác định điều gì?
A. Giới hạn số connection chờ trong driver connection pool.
B. Cách kết hợp commit giữa các phiên thuộc nhiều driver.
C. Ranh giới giao dịch cho các thao tác dữ liệu liên quan.
D. Thời điểm Spring sinh index cho property của entity.
Đáp án đúng: C

Câu 39. Trong vận hành Neo4j, tập tín hiệu nào hữu ích khi truy vấn chậm tăng đột biến?
A. Số node, số label, tỷ lệ node không có relationship.
B. Độ trễ truy vấn, DB hits, page cache và giao dịch chạy.
C. Số repository, số method Java và thời gian biên dịch.
D. Số constraint, số index và phiên bản Cypher đã cài.
Đáp án đúng: B

Câu 40. Để khôi phục Neo4j sau sự cố dữ liệu, thực hành nào đáng tin cậy nhất?
A. Chỉ dựa vào replica mà không chuẩn bị bản backup.
B. Chỉ dựa vào transaction log để thay mọi bản backup.
C. Tạo backup phù hợp và định kỳ thử restore từ bản đó.
D. Sao chép file store tùy ý khi database đang chạy.
Đáp án đúng: C
