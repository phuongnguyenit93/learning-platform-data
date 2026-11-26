Bạn giải thích Spring Data Neo4j giải quyết vấn đề gì khi xây dựng tầng dữ liệu đồ thị trong ứng dụng Spring Boot?
Bạn phân biệt mô hình property graph của Neo4j với mô hình quan hệ khi biểu diễn dữ liệu nhiều liên kết như thế nào?
Bạn sẽ đánh giá khi nào một bài toán phù hợp với Neo4j thay vì một database quan hệ ra sao?
Bạn giải thích vai trò của node, relationship, label và property trong mô hình dữ liệu Neo4j như thế nào?
Bạn phân biệt label của node với relationship type trong việc mô tả ngữ nghĩa nghiệp vụ ra sao?
Bạn sẽ xác định ranh giới aggregate cho một miền nghiệp vụ có nhiều node liên kết như thế nào?
Bạn phân tích đánh đổi giữa lưu một thuộc tính trực tiếp trên node và tạo node riêng để biểu diễn thuộc tính đó như thế nào?
Bạn sẽ thiết kế graph model cho hệ thống người dùng theo dõi nhau mà không tạo relationship type quá chi tiết ra sao?
Bạn phân biệt quan hệ có hướng và quan hệ cần được truy vấn cả hai hướng trong mô hình đồ thị như thế nào?
Bạn sẽ lựa chọn chiều relationship gốc dựa trên nghiệp vụ và truy vấn phổ biến ra sao?
Bạn giải thích vì sao hướng truy vấn relationship có thể khác cách diễn giải chiều quan hệ trong ngôn ngữ nghiệp vụ như thế nào?
Bạn đánh giá tác động khi một node trở thành điểm kết nối của hàng triệu relationship ra sao?
Bạn sẽ xác định những liên kết nào nên dùng relationship thay vì một mảng ID được lưu trong property như thế nào?
Bạn phân tích chi phí truy vấn đường đi dài và rủi ro kết quả tăng theo cấp số khi độ sâu mở rộng ra sao?
Bạn sẽ thiết kế quy tắc đặt tên labels và relationship types để nhiều nhóm phát triển hiểu thống nhất như thế nào?
Bạn phân biệt business key ổn định và identifier nội bộ được database quản lý như thế nào?
Bạn sẽ xác định chính sách xóa node khi nó còn liên kết với nhiều node khác như thế nào?
Bạn phân tích hậu quả của việc biểu diễn trạng thái quan hệ bằng relationship property thay vì tạo nhiều relationship type như thế nào?
Bạn sẽ lựa chọn mô hình đồ thị cho quyền truy cập phân cấp theo các tiêu chí nào?
Bạn giải thích điểm mạnh và giới hạn của graph traversal trong bài toán gợi ý bạn bè như thế nào?
Bạn phân biệt bài toán tìm đường đi ngắn với bài toán liệt kê toàn bộ đường đi hợp lệ như thế nào?
Bạn sẽ đánh giá khi nào một graph model quá liên kết làm truy vấn và cập nhật khó kiểm soát ra sao?
Bạn phân tích rủi ro mô hình hóa mỗi thuộc tính nhỏ thành một node riêng khiến graph trở nên quá phức tạp như thế nào?
Bạn sẽ thiết kế mô hình phiên bản hoặc hiệu lực theo thời gian cho một relationship như thế nào?
Bạn xác định cách tránh trùng dữ liệu khi hai sự kiện cùng tạo một quan hệ nghiệp vụ như thế nào?
Bạn sẽ lập kế hoạch chuyển một hệ dữ liệu quan hệ sang property graph dựa trên những điều kiện nào?
Bạn phân biệt Spring Data Neo4j với Neo4j Java Driver theo trách nhiệm ánh xạ và truy cập dữ liệu như thế nào?
Bạn mô tả những tầng cấu thành một lời gọi repository từ Spring service tới Neo4j database như thế nào?
Bạn sẽ quyết định khi nào nên dùng Spring Data Neo4j thay vì viết truy vấn qua driver trực tiếp ra sao?
Bạn phân tích ảnh hưởng của Spring Boot auto-configuration tới việc tạo driver, transaction manager và repository như thế nào?
Bạn sẽ kiểm tra phiên bản Spring Boot, Spring Data và Neo4j driver tương thích khi nâng cấp như thế nào?
Bạn xác định cách tách entity mô hình lưu trữ khỏi DTO trả cho REST API như thế nào?
Bạn giải thích vai trò của @Node khi đánh dấu một entity được lưu thành node Neo4j như thế nào?
Bạn phân biệt @Node với @Id khi định nghĩa danh tính và loại của một node entity ra sao?
Bạn sẽ thiết kế một entity có nhiều label cần thiết theo yêu cầu domain như thế nào?
Bạn xác định khi nào dùng một primary label và khi nào cần các label bổ sung cho mục đích truy vấn ra sao?
Bạn phân tích ảnh hưởng của việc đổi label entity đối với các node đã được tạo trước đó như thế nào?
Bạn giải thích vai trò của @Property khi ánh xạ field Java sang thuộc tính node như thế nào?
Bạn sẽ xác định cách ánh xạ tên property khác tên Java field mà vẫn dễ bảo trì ra sao?
Bạn mô tả cách @CompositeProperty hỗ trợ biểu diễn một nhóm thuộc tính vào các property của node như thế nào?
Bạn phân tích những hạn chế khi ánh xạ object lồng nhau vào node properties thay vì node quan hệ như thế nào?
Bạn sẽ lựa chọn kiểu Java phù hợp với các kiểu property mà Neo4j hỗ trợ như thế nào?
Bạn đánh giá cách lưu thời gian và múi giờ trong graph để truy vấn theo thời điểm chính xác như thế nào?
Bạn sẽ thiết kế converter cho một value object không được mapping mặc định hỗ trợ như thế nào?
Bạn phân biệt entity property không có giá trị và property không tồn tại trên node về ý nghĩa nghiệp vụ ra sao?
Bạn phân tích rủi ro schema evolution khi entity mới yêu cầu một field nhưng node cũ chưa có field đó như thế nào?
Bạn sẽ xây dựng chiến lược default value hoặc migration cho node thiếu property bắt buộc ra sao?
Bạn mô tả vai trò của @Id khi ánh xạ ID của một node entity vào Java class như thế nào?
Bạn phân biệt ID do ứng dụng sinh với ID do Neo4j quản lý theo độ ổn định qua các thao tác vận hành như thế nào?
Bạn sẽ xác định khi nào nên dùng business ID dạng String hoặc UUID cho node ra sao?
Bạn phân tích rủi ro dùng identifier nội bộ Neo4j làm mã nghiệp vụ công khai trong API như thế nào?
Bạn sẽ thiết kế cơ chế sinh khóa duy nhất khi nhiều instance ứng dụng cùng tạo node như thế nào?
Bạn giải thích @GeneratedValue ảnh hưởng cách cấp định danh entity trong Spring Data Neo4j như thế nào?
Bạn phân biệt một entity mới chưa có ID với entity đã tồn tại khi Spring Data quyết định lưu như thế nào?
Bạn sẽ đánh giá ảnh hưởng của custom ID generator tới khả năng import dữ liệu từ hệ thống cũ ra sao?
Bạn phân tích hậu quả khi hai node có cùng business ID mà schema chưa có uniqueness constraint như thế nào?
Bạn sẽ kiểm thử việc đọc lại node sau khi lưu mà không phụ thuộc vào ID nội bộ có thể thay đổi ra sao?
Bạn giải thích annotation @Relationship biểu diễn liên kết từ entity này đến entity khác như thế nào?
Bạn phân biệt @Relationship với property scalar thông thường trên node entity ra sao?
Bạn sẽ lựa chọn hướng OUTGOING hoặc INCOMING cho một @Relationship theo chiều graph đã thiết kế như thế nào?
Bạn mô tả cách mapping một relationship một-một và một-nhiều trong entity Java như thế nào?
Bạn phân tích rủi ro mapping relationship hai chiều gây vòng tham chiếu khi serialize entity thành JSON như thế nào?
Bạn sẽ thiết kế API DTO tránh tải hoặc serialize toàn bộ graph từ một node gốc như thế nào?
Bạn xác định khi nào relationship chỉ cần liên kết node đích và khi nào cần lưu thêm thuộc tính trên relationship ra sao?
Bạn giải thích vai trò của @RelationshipProperties trong việc mô hình hóa thuộc tính của một relationship như thế nào?
Bạn mô tả cách @TargetNode xác định node đầu kia của một entity relationship properties như thế nào?
Bạn phân biệt @RelationshipId với @Id của node entity theo mục đích ánh xạ định danh như thế nào?
Bạn sẽ thiết kế quan hệ FOLLOW có thời điểm tạo và trạng thái bằng relationship properties như thế nào?
Bạn phân tích nguy cơ sử dụng @RelationshipProperties cho mọi quan hệ kể cả quan hệ không có property như thế nào?
Bạn sẽ xác định cách mapping nhiều relationship cùng type nối cùng hai node nhưng có ý nghĩa nghiệp vụ khác như thế nào?
Bạn đánh giá khi nào nên biến một relationship có nhiều thuộc tính thành node trung gian như thế nào?
Bạn sẽ tổ chức entity để ngăn relationship bị tạo trùng trong một thao tác nghiệp vụ lặp lại ra sao?
Bạn phân tích rủi ro equals và hashCode của entity chứa relationship collection gây đệ quy như thế nào?
Bạn sẽ lựa chọn kiểu collection và quy tắc nhận dạng phần tử để tránh mất relationship khi lưu như thế nào?
Bạn xác định cách mapping nhiều loại relationship giữa hai loại node trong cùng một domain như thế nào?
Bạn sẽ thiết kế thay đổi direction của relationship mà vẫn tương thích với dữ liệu đã lưu ra sao?
Bạn phân tích ảnh hưởng khi node đích bị xóa nhưng entity nguồn vẫn đang giữ reference cũ như thế nào?
Bạn sẽ xử lý một relationship không còn hợp lệ mà không vô tình xóa node đích dùng chung như thế nào?
Bạn đánh giá cách phân tách aggregate root và node entity dùng chung khi nhiều repository quản lý graph chồng lấn như thế nào?
Bạn giải thích cơ chế mapping quan hệ của Spring Data Neo4j có thể tải nhiều node liên kết từ một truy vấn như thế nào?
Bạn phân tích rủi ro tải graph quá lớn khi entity có nhiều relationship và các node đích lại liên kết rộng ra sao?
Bạn sẽ thiết kế projection để giới hạn thông tin cần đọc thay vì materialize toàn bộ graph như thế nào?
Bạn phân biệt interface projection với DTO projection khi một endpoint chỉ cần vài thuộc tính như thế nào?
Bạn sẽ sử dụng kết quả truy vấn tùy chỉnh để trả DTO thay vì trả entity đồ thị trong tình huống nào?
Bạn phân tích cách mapping một partial graph rồi lưu lại có thể ảnh hưởng các relationship không được tải như thế nào?
Bạn xác định nguyên tắc không dùng thao tác save nguyên graph khi chỉ cần đổi một property nhỏ ra sao?
Bạn sẽ xây dựng thao tác cập nhật có chủ đích bằng Cypher để bảo toàn các relationship không liên quan như thế nào?
Bạn mô tả cách phát hiện một entity bị detach khỏi graph ban đầu sau khi qua nhiều tầng service như thế nào?
Bạn sẽ thiết kế load boundary phù hợp cho node có hàng chục nghìn relationship như thế nào?
Bạn đánh giá rủi ro truyền entity hai chiều qua REST dẫn tới stack overflow hoặc payload quá lớn ra sao?
Bạn sẽ dùng node ID và DTO tham chiếu để tách phần đọc graph khỏi phần ghi như thế nào?
Bạn giải thích vai trò của Neo4jRepository trong việc quản lý thao tác dữ liệu đồ thị theo mô hình Spring Data ra sao?
Bạn phân biệt Neo4jRepository với một CrudRepository chung theo năng lực và cơ chế mapping như thế nào?
Bạn sẽ định nghĩa repository cho một @Node entity có business ID như thế nào?
Bạn mô tả cách Spring Data tạo repository implementation khi ApplicationContext khởi động ra sao?
Bạn phân biệt findById với một repository method truy vấn theo property khác ID như thế nào?
Bạn xác định khi nào derived query đủ rõ và khi nào cần viết Cypher bằng @Query ra sao?
Bạn phân tích rủi ro một derived query đi qua relationship tạo quá nhiều kết quả trung gian như thế nào?
Bạn sẽ thiết kế repository method tìm tất cả node liên kết trong một bước mà không tải graph nhiều cấp ra sao?
Bạn phân biệt tìm theo nhãn và property với truy vấn duyệt quan hệ trong thiết kế method repository ra sao?
Bạn sẽ xử lý Optional.empty khi node không tồn tại mà không coi đó là lỗi kết nối như thế nào?
Bạn phân tích chi phí của repository.findAll khi label có hàng triệu node như thế nào?
Bạn sẽ thiết kế repository trả kết quả phân trang cùng thứ tự ổn định để phục vụ REST API ra sao?
Bạn đánh giá chi phí truy vấn COUNT khi ứng dụng yêu cầu Page thay vì Slice hoặc cursor ra sao?
Bạn sẽ lựa chọn keyset pagination thay offset pagination trong những tình huống nào?
Bạn mô tả cách kết hợp sorting với index để giảm chi phí truy vấn lớn như thế nào?
Bạn sẽ thiết kế repository method trả node và relationship properties cần thiết mà không ghép nhầm đường đi ra sao?
Bạn xác định những assertion cần có khi kiểm tra mapping một kết quả query trả nhiều hàng cho cùng node gốc như thế nào?
Bạn sẽ kiểm thử một repository method lọc theo tenant mà không truy cập nhầm subgraph của tenant khác ra sao?
Bạn phân tích rủi ro cung cấp method deleteById mà không xem xét relationship còn tồn tại như thế nào?
Bạn sẽ quyết định khi nào cần delete relationship trước khi xóa node thay vì dùng DETACH DELETE ra sao?
Bạn đánh giá cách đảm bảo hành vi repository không âm thầm xóa relationship do state collection chưa đầy đủ ra sao?
Bạn giải thích annotation @Query được dùng để viết truy vấn Cypher tùy chỉnh trong repository như thế nào?
Bạn sẽ dùng named parameters trong @Query để truyền giá trị mà không nối chuỗi Cypher từ input người dùng ra sao?
Bạn phân tích rủi ro Cypher injection khi tên label, relationship type hoặc ORDER BY được tạo động như thế nào?
Bạn sẽ thiết kế allowlist cho các phần cấu trúc câu Cypher không thể bind bằng parameter thông thường ra sao?
Bạn mô tả ý nghĩa của MATCH trong việc tìm pattern node và relationship như thế nào?
Bạn phân biệt MATCH với OPTIONAL MATCH khi một quan hệ có thể không tồn tại ra sao?
Bạn sẽ giải thích tác động của WHERE đặt trước hoặc sau một OPTIONAL MATCH tới số hàng trả về như thế nào?
Bạn phân tích khác biệt giữa CREATE và MERGE khi thiết kế thao tác tạo node và quan hệ tránh trùng ra sao?
Bạn sẽ quyết định khi nào MERGE cần kết hợp uniqueness constraint để an toàn dưới concurrency như thế nào?
Bạn mô tả cách SET và REMOVE cập nhật property trong một câu Cypher như thế nào?
Bạn phân biệt DELETE với DETACH DELETE theo điều kiện node còn relationship như thế nào?
Bạn sẽ dùng WITH để kiểm soát biến và ranh giới xử lý qua nhiều phần câu truy vấn ra sao?
Bạn phân tích vì sao RETURN DISTINCT có thể làm thay đổi cardinality kết quả và chi phí thực thi như thế nào?
Bạn sẽ sử dụng collect và UNWIND để thao tác nhóm hoặc danh sách node theo nhu cầu nào?
Bạn đánh giá khi nào UNWIND giúp ghi batch hiệu quả hơn việc gửi hàng nghìn câu truy vấn riêng lẻ ra sao?
Bạn sẽ thiết kế truy vấn variable-length path có giới hạn số bước để tránh mở rộng đồ thị vô hạn như thế nào?
Bạn phân tích rủi ro biến đường đi thành nhiều kết quả trùng node khi truy vấn pattern có nhiều nhánh như thế nào?
Bạn sẽ xây dựng truy vấn tìm bạn chung giữa hai người dùng dựa trên relationship patterns như thế nào?
Bạn mô tả cách kiểm soát đường đi theo relationship type để không duyệt nhầm liên kết không liên quan ra sao?
Bạn sẽ lựa chọn shortest path query cho bài toán đường đi giữa hai node theo giới hạn nghiệp vụ nào?
Bạn phân tích rủi ro truy vấn shortest path trên graph quá rộng mà không lọc node ứng viên như thế nào?
Bạn sẽ xây dựng truy vấn đếm số lượng relationship của một node và đánh giá chi phí ra sao?
Bạn phân biệt truy vấn trả node, relationship và path với projection DTO khi ánh xạ kết quả vào Spring Data như thế nào?
Bạn sẽ kiểm thử truy vấn custom trả đúng cấu trúc để SDN không bỏ sót relationship properties ra sao?
Bạn mô tả vai trò của Neo4jClient khi cần thực thi Cypher linh hoạt ngoài repository như thế nào?
Bạn phân biệt Neo4jClient với Neo4jTemplate theo mức ánh xạ dữ liệu và quyền kiểm soát truy vấn ra sao?
Bạn sẽ lựa chọn Neo4jTemplate hoặc Neo4jOperations khi cần thao tác entity có mapping Spring Data như thế nào?
Bạn mô tả khi nào cần truy cập Neo4j Java Driver trực tiếp thay vì dùng abstraction Spring Data ra sao?
Bạn phân tích hậu quả khi một service trộn nhiều cách truy cập graph mà không thống nhất transaction boundary như thế nào?
Bạn sẽ thiết kế adapter che giấu Neo4jClient để tầng nghiệp vụ chỉ nhận kết quả domain như thế nào?
Bạn xác định cách truyền parameter map cho Cypher qua Neo4jClient để tránh injection ra sao?
Bạn sẽ ánh xạ một record gồm node và số lượng quan hệ thành DTO tùy chỉnh bằng cơ chế nào?
Bạn phân tích những trường hợp mapping entity đầy đủ không phù hợp với truy vấn tổng hợp hay đồ thị nhiều nhánh như thế nào?
Bạn sẽ xây dựng thao tác update một property của node bằng Cypher mà không load toàn bộ relationship ra sao?
Bạn so sánh chi phí của gọi repository.save với cập nhật có chủ đích bằng Cypher trong bài toán sửa một field ra sao?
Bạn sẽ kiểm tra một thao tác update Cypher có ảnh hưởng đúng số node mong đợi như thế nào?
Bạn xác định cách xử lý khi database không tìm thấy node ở thời điểm cập nhật có điều kiện ra sao?
Bạn sẽ thiết kế dịch vụ dùng Neo4jClient chỉ trả về scalar hoặc DTO để giảm memory như thế nào?
Bạn phân tích cách custom Cypher truy vấn nhiều graph components có thể sinh Cartesian product như thế nào?
Bạn sẽ bảo đảm consistency giữa các repository và client API khi cùng cập nhật node chung như thế nào?
Bạn giải thích transaction giúp bảo đảm thay đổi đồng bộ nhiều node và relationship trong Neo4j như thế nào?
Bạn phân biệt transaction của Neo4j với một chuỗi lệnh Cypher được chạy độc lập như thế nào?
Bạn sẽ xác định ranh giới @Transactional ở tầng service cho một thao tác liên kết hai node ra sao?
Bạn phân tích rủi ro ghi node thành công nhưng thêm relationship thất bại nếu không có transaction như thế nào?
Bạn mô tả vai trò của Neo4jTransactionManager trong ứng dụng Spring Data Neo4j như thế nào?
Bạn sẽ đánh giá khi nào Spring transaction phải bao trùm nhiều repository operations như thế nào?
Bạn phân biệt read-only transaction với write transaction khi tối ưu truy vấn như thế nào?
Bạn sẽ lựa chọn isolation và consistency phù hợp khi nhiều request cùng sửa một node như thế nào?
Bạn phân tích trường hợp @Transactional không có hiệu lực do self-invocation trong một Spring bean ra sao?
Bạn sẽ thiết kế rollback khi một bước nghiệp vụ ném exception sau khi đã tạo relationship như thế nào?
Bạn đánh giá rủi ro ném checked exception nhưng transaction chưa rollback theo cấu hình mặc định ra sao?
Bạn sẽ xử lý một transient transaction error và quyết định retry theo giới hạn nào?
Bạn phân biệt retry toàn transaction với retry một câu Cypher độc lập khi có tác dụng phụ nhiều bước ra sao?
Bạn sẽ thiết kế logic transaction có khả năng chạy lại mà không gửi trùng email hoặc message ra sao?
Bạn phân tích lý do không nên gọi dịch vụ ngoài có tác dụng phụ khó rollback bên trong transaction dài như thế nào?
Bạn sẽ chọn phương án outbox hoặc saga khi cần đồng bộ kết quả Neo4j với hệ thống bên ngoài như thế nào?
Bạn giải thích vai trò của @Version trong optimistic locking cho node entity như thế nào?
Bạn phân biệt @Version và một property version dùng cho lịch sử nghiệp vụ như thế nào?
Bạn sẽ xử lý optimistic locking conflict khi hai request đồng thời cập nhật cùng một node ra sao?
Bạn phân tích nguy cơ retry thiếu backoff làm tăng tranh chấp trên node có nhiều lượt ghi như thế nào?
Bạn sẽ thiết kế test cạnh tranh cập nhật để xác minh không xảy ra lost update như thế nào?
Bạn xác định khi nào constraint và transaction chưa đủ để giải quyết race condition cấp nghiệp vụ ra sao?
Bạn sẽ đánh giá tác động của lock contention khi nhiều transaction ghi relationship tới cùng một hub node như thế nào?
Bạn mô tả vai trò của bookmarks trong causal consistency giữa các phiên giao dịch đọc và ghi Neo4j như thế nào?
Bạn phân biệt causal consistency với đọc từ một replica có thể chưa theo kịp thay đổi như thế nào?
Bạn sẽ kiểm tra hành vi read-after-write khi client dùng nhiều session hoặc nhiều instance ứng dụng ra sao?
Bạn phân tích cách transaction timeout và lock timeout ảnh hưởng đến trải nghiệm người dùng như thế nào?
Bạn sẽ thiết kế transaction đủ ngắn để không giữ lock khi phải xử lý nhiều dữ liệu không liên quan ra sao?
Bạn xác định cách ứng dụng phản ánh một transaction đã commit nhưng response bị mất qua network như thế nào?
Bạn sẽ thiết kế idempotency key cho thao tác tạo relationship có thể được retry ra sao?
Bạn phân biệt tính nguyên tử của transaction Neo4j với yêu cầu exactly-once khi caller retry HTTP như thế nào?
Bạn sẽ kiểm thử một transaction thất bại giữa nhiều thao tác và không để graph ở trạng thái nửa hoàn thành ra sao?
Bạn giải thích index và constraint trong Neo4j giúp bảo đảm truy xuất và dữ liệu hợp lệ như thế nào?
Bạn phân biệt index dùng tăng tốc tìm kiếm với uniqueness constraint dùng bảo vệ danh tính như thế nào?
Bạn sẽ thiết kế uniqueness constraint cho business ID của node label quan trọng ra sao?
Bạn phân tích tại sao kiểm tra ID chưa tồn tại rồi CREATE node có thể sinh trùng khi thiếu constraint như thế nào?
Bạn lựa chọn range index hoặc text index cho các predicate khác nhau dựa trên truy vấn thực tế như thế nào?
Bạn sẽ xác định khi nào full-text search phù hợp hơn so sánh property bằng biểu thức đơn giản ra sao?
Bạn phân tích vai trò của composite index khi câu truy vấn thường lọc nhiều property như thế nào?
Bạn sẽ chọn thứ tự property trong index theo query workload và độ chọn lọc ra sao?
Bạn mô tả cách dùng EXPLAIN để xem kế hoạch thực thi của một Cypher query như thế nào?
Bạn phân biệt EXPLAIN với PROFILE khi cần phân tích query plan và công việc thực tế của database ra sao?
Bạn sẽ nhận diện NodeByLabelScan hoặc index seek trong kế hoạch truy vấn như thế nào?
Bạn phân tích những trường hợp planner phải quét quá nhiều node do không có predicate selective ra sao?
Bạn sẽ tìm nguyên nhân Cartesian product trong Cypher và giảm số kết quả trung gian như thế nào?
Bạn đánh giá rủi ro dùng OPTIONAL MATCH nhiều lần làm bùng nổ số hàng và kết quả lặp như thế nào?
Bạn sẽ phân tích tác động của eager operation hoặc sort lớn đối với memory của query engine ra sao?
Bạn xác định cách giảm số node và relationship được trả về để tiết kiệm băng thông và mapping cost như thế nào?
Bạn sẽ lựa chọn LIMIT và ORDER BY ổn định khi cần phân trang kết quả như thế nào?
Bạn phân tích vì sao OFFSET sâu có thể tốn kém trên tập kết quả lớn và cần pagination khác ra sao?
Bạn sẽ thiết kế truy vấn theo hướng relationship và label cụ thể để giảm số cạnh cần duyệt như thế nào?
Bạn đánh giá ảnh hưởng của relationship fan-out rất lớn tới độ trễ truy vấn duyệt nhiều bước như thế nào?
Bạn sẽ xác định giới hạn độ sâu hợp lý cho recommendation traversal trên dữ liệu thực tế ra sao?
Bạn phân tích chi phí tạo graph projection lớn so với việc truy vấn từng node liên kết theo nhu cầu như thế nào?
Bạn sẽ sử dụng UNWIND và parameterized query để thực hiện bulk write an toàn như thế nào?
Bạn xác định batch size phù hợp để nhập hàng triệu node và relationship mà không tạo transaction quá dài ra sao?
Bạn phân tích rủi ro MERGE pattern phức tạp dẫn tới tạo relationship hoặc node không mong muốn như thế nào?
Bạn sẽ thiết kế quá trình import graph sao cho chạy lại không nhân đôi node và relationship ra sao?
Bạn đánh giá hiệu năng của thao tác xóa node có số relationship rất lớn như thế nào?
Bạn sẽ xây dựng benchmark query với dữ liệu có phân bố bậc node và density giống production ra sao?
Bạn mô tả cách Spring Data Neo4j hỗ trợ ReactiveNeo4jRepository trong ứng dụng Spring WebFlux như thế nào?
Bạn phân biệt Neo4jRepository blocking với ReactiveNeo4jRepository về kiểu trả về và quản lý tài nguyên như thế nào?
Bạn sẽ lựa chọn giữa API blocking và reactive theo thread model của ứng dụng như thế nào?
Bạn giải thích Mono và Flux phù hợp với truy vấn trả một node hay nhiều node như thế nào?
Bạn phân biệt empty Mono do node không tồn tại với error signal do kết nối Neo4j thất bại ra sao?
Bạn sẽ thiết kế một reactive service thực thi Cypher nhưng không chặn event loop như thế nào?
Bạn phân tích lý do gọi block trong WebFlux request có thể gây nghẽn dù driver hỗ trợ reactive như thế nào?
Bạn sẽ giới hạn concurrency khi dùng flatMap để ghi nhiều relationship vào graph như thế nào?
Bạn xác định cách xử lý backpressure khi Flux trả rất nhiều node từ một traversal rộng ra sao?
Bạn phân tích rủi ro collectList gom toàn bộ kết quả graph lớn vào heap như thế nào?
Bạn sẽ thiết kế phân trang hoặc streaming kết quả reactive để tránh tạo payload quá lớn ra sao?
Bạn mô tả reactive transaction boundary ảnh hưởng vòng đời subscription và commit như thế nào?
Bạn phân biệt retryWhen cho reactive read với retry reactive write có side effect như thế nào?
Bạn sẽ kiểm tra cancellation từ client có dừng pipeline và giải phóng Neo4j session đúng cách hay không như thế nào?
Bạn phân tích khi nào Reactor Context cần được giữ qua thread boundary để bảo toàn tracing ra sao?
Bạn sẽ dùng StepVerifier để kiểm thử truy vấn reactive trả một entity và hoàn thành đúng tín hiệu như thế nào?
Bạn sẽ thiết kế StepVerifier test khi constraint violation làm publisher trả lỗi như thế nào?
Bạn phân tích khả năng throughput cao của reactive I/O có thể bị giới hạn bởi lock hoặc query engine như thế nào?
Bạn sẽ xác định khi nào API đồng bộ đơn giản hơn mà vẫn đáp ứng throughput yêu cầu ra sao?
Bạn giải thích driver Neo4j dùng Bolt protocol để kết nối application với database như thế nào?
Bạn phân biệt kết nối Bolt với truy cập Neo4j Browser phục vụ quản trị và thử nghiệm truy vấn như thế nào?
Bạn sẽ cấu hình URI, username, password và database name trong Spring Boot mà không lưu secret vào repository ra sao?
Bạn phân tích cách lựa chọn kết nối neo4j scheme hoặc bolt scheme theo đặc điểm cluster như thế nào?
Bạn sẽ bảo đảm TLS và kiểm tra chứng chỉ khi kết nối Neo4j Aura hoặc cluster bên ngoài như thế nào?
Bạn xác định cách tách quyền của account đọc dữ liệu với account được phép ghi hoặc chỉnh schema như thế nào?
Bạn sẽ xây dựng nguyên tắc least privilege theo database hoặc loại thao tác Neo4j như thế nào?
Bạn phân tích nguy cơ một query dùng input người dùng để chọn label tùy ý truy cập subgraph ngoài quyền như thế nào?
Bạn sẽ thiết kế filter tenant trong Cypher mà không dựa duy nhất vào input tenantId không được xác thực ra sao?
Bạn đánh giá rủi ro hai tenant dùng chung graph nhưng relationship nối sang tenant khác ngoài dự kiến như thế nào?
Bạn sẽ kiểm thử không có đường traversal nào trả node thuộc tenant khác như thế nào?
Bạn phân biệt authentication với Neo4j và authorization nghiệp vụ trên một node hoặc relationship ra sao?
Bạn sẽ thiết kế audit log cho các thao tác xóa node hoặc relationship nhạy cảm mà không ghi lộ dữ liệu cá nhân ra sao?
Bạn phân tích hậu quả khi trả trực tiếp graph entities cho API và làm lộ relationship không được phép xem như thế nào?
Bạn sẽ thiết kế projection DTO theo quyền người dùng và chỉ trả các relationship đã được xác minh ra sao?
Bạn xác định cách kiểm soát query timeout và giới hạn độ sâu để chống truy vấn quá tốn tài nguyên như thế nào?
Bạn sẽ áp dụng rate limit hoặc query budget cho endpoint cho phép người dùng tìm path như thế nào?
Bạn phân tích rủi ro query với pattern do người dùng đưa vào gây tải CPU và memory lớn như thế nào?
Bạn sẽ thiết kế whitelist relationship types và giới hạn số hop khi cung cấp API tìm đường đi ra sao?
Bạn xác định các chỉ số quan sát kết nối, pool và transaction Neo4j giúp điều tra lỗi như thế nào?
Bạn sẽ sử dụng Micrometer và Spring Boot Actuator để theo dõi latency, throughput và lỗi truy cập graph ra sao?
Bạn phân biệt thời gian chờ connection pool với thời gian chạy Cypher query khi một request chậm như thế nào?
Bạn sẽ theo dõi query execution time, DB hits và số row trả về để xác định bottleneck ra sao?
Bạn phân tích ảnh hưởng của nhiều slow queries tới connection pool và thời gian phản hồi của các request khác như thế nào?
Bạn xác định cách đặt tag metrics theo operation và query type mà không dùng ID node làm label cardinality cao như thế nào?
Bạn sẽ gắn correlation ID và trace ID để theo dõi từ HTTP request tới database operation ra sao?
Bạn đánh giá rủi ro ghi raw Cypher parameters chứa PII hoặc credential trong log như thế nào?
Bạn sẽ bảo vệ dữ liệu nhạy cảm khi bật query logging để phân tích performance như thế nào?
Bạn phân biệt readiness và liveness của Spring Boot khi Neo4j bị outage tạm thời như thế nào?
Bạn sẽ cấu hình health check không thực thi graph traversal nặng gây tải cho cluster như thế nào?
Bạn phân tích rủi ro liveness phụ thuộc database khiến nhiều instance bị restart hàng loạt như thế nào?
Bạn sẽ giám sát lock contention và deadlock dưới workload cập nhật nhiều hub nodes như thế nào?
Bạn xác định cách quan sát sự kiện cluster failover hoặc leader change liên quan tới transaction retries ra sao?
Bạn sẽ thiết kế chính sách timeout, exponential backoff và circuit breaker khi kết nối Neo4j lỗi tạm thời như thế nào?
Bạn phân tích nguy cơ retry storm khi cluster vừa phục hồi sau gián đoạn như thế nào?
Bạn đánh giá kế hoạch capacity cho số node, relationships, index và query concurrency như thế nào?
Bạn sẽ lập runbook điều tra tình huống một truy vấn Cypher vốn nhanh đột nhiên chậm sau import dữ liệu như thế nào?
Bạn phân biệt lỗi do thiếu index với lỗi do network latency trong số liệu production như thế nào?
Bạn sẽ kiểm soát schema migrations cho index và constraint trước khi phát hành code query mới như thế nào?
Bạn phân tích nguy cơ thay đổi relationship type trong một bản deploy khi còn các instance chạy mã cũ ra sao?
Bạn sẽ thiết kế rollout canary cho query mới và phương án rollback an toàn như thế nào?
Bạn phân biệt unit test cho service với integration test chạy Neo4j thật theo mục tiêu xác minh như thế nào?
Bạn sẽ dùng mock Neo4jRepository để kiểm thử logic nghiệp vụ mà không phụ thuộc database như thế nào?
Bạn thiết kế test mapping @Node, @Id và @Relationship cho graph có nhiều loại node như thế nào?
Bạn sẽ kiểm thử @RelationshipProperties và @TargetNode để xác minh các property trên edge được đọc ghi đúng ra sao?
Bạn xác định cách kiểm thử direction INCOMING và OUTGOING để không đảo ngược relationship ngoài ý muốn như thế nào?
Bạn sẽ dùng Testcontainers Neo4j để chạy integration test độc lập và tái lập như thế nào?
Bạn phân tích ưu điểm của một test database Neo4j thực so với giả lập Cypher trong repository test như thế nào?
Bạn sẽ tạo schema constraints và indexes cho container test trước khi chạy queries như thế nào?
Bạn thiết kế test tạo hai node và relationship trong một transaction rồi đọc lại đầy đủ ra sao?
Bạn sẽ kiểm thử một transaction bị rollback sau khi đã tạo node nhưng chưa kịp tạo relationship như thế nào?
Bạn kiểm tra optimistic locking với @Version khi hai request cùng chỉnh sửa node bằng phương pháp nào?
Bạn sẽ kiểm thử save entity chỉ tải một phần graph không vô tình xóa các relationship khác như thế nào?
Bạn thiết kế test cho @Query dùng parameter binding để xác minh input đặc biệt không làm thay đổi cấu trúc Cypher ra sao?
Bạn kiểm thử OPTIONAL MATCH khi node thiếu relationship mà vẫn trả đúng dữ liệu gốc như thế nào?
Bạn sẽ tạo bài test phát hiện kết quả bị nhân bản do MATCH nhiều nhánh và JOIN pattern như thế nào?
Bạn xác định cách kiểm thử UNWIND bulk import không tạo node trùng khi chạy lại cùng tập dữ liệu ra sao?
Bạn sẽ viết test constraint uniqueness khi hai transaction đồng thời MERGE cùng business ID ra sao?
Bạn phân tích cách kiểm thử kết quả path traversal khi graph có chu trình và nhiều đường đi khác nhau như thế nào?
Bạn sẽ kiểm thử giới hạn depth và số kết quả của API tìm đường đi để tránh traversal không kiểm soát ra sao?
Bạn thiết kế test query paginated trả thứ tự ổn định khi nhiều node cùng giá trị sort như thế nào?
Bạn sẽ xác minh custom Cypher projection được ánh xạ đúng vào DTO mà không materialize toàn bộ graph ra sao?
Bạn phân tích cách sử dụng PROFILE để so sánh query plan trước và sau khi tạo index trên dữ liệu test như thế nào?
Bạn sẽ xây dựng performance test trên graph có hub nodes nhằm phát hiện traversal bùng nổ như thế nào?
Bạn kiểm thử reactive repository với StepVerifier khi node không tồn tại hoặc lỗi constraint như thế nào?
Bạn sẽ mô phỏng Neo4j connection timeout để xác minh API trả lỗi có kiểm soát thay vì treo vô hạn như thế nào?
Bạn xác định cách kiểm thử transaction retry không gửi trùng side effects tới dịch vụ bên ngoài ra sao?
Bạn thiết kế bài kiểm tra phân quyền tránh query trả node hoặc relationship của tenant khác như thế nào?
Bạn sẽ tạo chaos test mô phỏng cluster failover trong lúc ứng dụng tạo quan hệ mới ra sao?
Bạn đánh giá tiêu chí nghiệm thu trước production về schema, mapping, index, transaction, security và telemetry như thế nào?
Nếu một truy vấn MATCH chậm sau khi dữ liệu tăng gấp nhiều lần, bạn sẽ dùng EXPLAIN và PROFILE để khoanh vùng ra sao?
Nếu một node có hàng trăm nghìn quan hệ và API tải entity quá chậm, bạn sẽ thay đổi cách truy vấn hoặc projection như thế nào?
Nếu lưu một entity chỉ chứa một phần relationship làm mất các liên kết khác, bạn sẽ kiểm tra mapping và thay thao tác ghi ra sao?
Nếu cùng business ID được tạo trùng bởi hai request, bạn sẽ phối hợp uniqueness constraint, MERGE và retry như thế nào?
Nếu quan hệ FOLLOW bị tạo ngược chiều, bạn sẽ kiểm tra @Relationship và câu Cypher theo hướng nào?
Nếu một custom @Query trả node nhưng relationship properties bị thiếu, bạn sẽ phân tích cấu trúc record trả về như thế nào?
Nếu transaction tạo node và relationship bị lỗi giữa chừng, bạn sẽ kiểm tra rollback và trạng thái graph ra sao?
Nếu hai người cùng chỉnh sửa một node và gặp optimistic locking conflict, bạn sẽ thiết kế cách thông báo hoặc retry như thế nào?
Nếu truy vấn tìm bạn chung trả kết quả trùng nhau, bạn sẽ kiểm tra các pattern và DISTINCT như thế nào?
Nếu path search gây tăng CPU đột biến, bạn sẽ đặt giới hạn số hop, loại relationship và số kết quả ra sao?
Nếu truy vấn thông thường chạy nhanh nhưng một hub node làm timeout, bạn sẽ thay đổi graph model hoặc chiến lược traversal như thế nào?
Nếu WebFlux endpoint gọi Neo4jRepository blocking, bạn sẽ đánh giá chuyển sang ReactiveNeo4jRepository hoặc cô lập blocking như thế nào?
Nếu một giao dịch đã commit nhưng client timeout và gửi lại yêu cầu tạo quan hệ, bạn sẽ bảo đảm idempotency ra sao?
Nếu ứng dụng có nhiều tenant dùng chung graph, bạn sẽ thiết kế điều kiện truy vấn và kiểm tra phân quyền traversal như thế nào?
Nếu một bản nâng cấp đổi label hoặc relationship type khi code cũ còn chạy, bạn sẽ triển khai migration và rollout như thế nào?
Nếu Neo4j cluster failover gây tăng transient errors, bạn sẽ kiểm tra driver, timeout và retry như thế nào?
Nếu API trả về JSON bị đệ quy vì entity mapping hai chiều, bạn sẽ tổ chức DTO và giới hạn graph trả về ra sao?
Nếu cần xây dựng tầng truy cập Neo4j mới trong Spring Boot, bạn sẽ tổ chức entity, repository, Cypher, transaction, index, test và quan sát như thế nào?
