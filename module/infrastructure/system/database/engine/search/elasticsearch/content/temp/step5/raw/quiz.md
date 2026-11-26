Câu 1. Trong Elasticsearch, bản ghi JSON được lập chỉ mục được gọi là gì?
A. Một row nằm trong một SQL table
B. Một segment nằm trong một shard
C. Một mapping được lưu trong một index
D. Một document nằm trong một index
Đáp án đúng: D

Câu 2. Mapping kiểu `text` phù hợp nhất với cách sử dụng nào?
A. Tối ưu gom nhóm trên chuỗi chưa phân tích
B. Áp ràng buộc duy nhất cho giá trị chuỗi
C. Phân tích token để tìm kiếm toàn văn
D. Lưu nguyên chuỗi để lọc giá trị chính xác
Đáp án đúng: C

Câu 3. Đối với trường `status` cần lọc và tổng hợp theo giá trị chính xác, kiểu nào thường hợp lý?
A. `nested` để lọc và aggregation theo giá trị
B. `text` để lọc và aggregation theo giá trị
C. `keyword` để lọc và aggregation theo giá trị
D. `object` để lọc và aggregation theo từng giá trị
Đáp án đúng: C

Câu 4. Trong custom analyzer, tokenizer có trách nhiệm nào?
A. Biến trường chuỗi thành số nguyên
B. Chia document thành nhiều shard
C. Ghi token thành các segment riêng
D. Chia văn bản đầu vào thành các token
Đáp án đúng: D

Câu 5. Token filter `lowercase` thường tác động ra sao?
A. Bỏ dấu tiếng Việt nhưng giữ chữ hoa
B. Chuyển ký tự trong token thành chữ thường
C. Tách token theo khoảng trắng trong trường
D. Loại bỏ mọi ký tự đặc biệt khỏi nguồn JSON
Đáp án đúng: B

Câu 6. Khi khai báo `search_analyzer`, nó được sử dụng vào thời điểm nào?
A. Phân tích shard lúc replica được cấp phát
B. Phân tích chuỗi nhập khi chạy truy vấn tìm kiếm
C. Phân tích dữ liệu lúc tạo document mới trong index
D. Phân tích segment lúc snapshot được tạo
Đáp án đúng: B

Câu 7. Multi-field `name` kết hợp `name.keyword` hỗ trợ tình huống nào?
A. Vừa tăng replica vừa giảm primary shard
B. Vừa gom index vừa nén văn bản thành số
C. Vừa chạy script vừa ép sort theo điểm
D. Vừa tìm toàn văn vừa lọc tên chính xác
Đáp án đúng: D

Câu 8. Mảng object cần giữ quan hệ các field cùng phần tử thì mapping nào phù hợp?
A. Kiểu `keyword` để lưu các phần tử mảng
B. Kiểu `flattened` để gộp các phần tử mảng
C. Kiểu `nested` để tách các phần tử mảng
D. Kiểu `object` để gộp các phần tử mảng
Đáp án đúng: C

Câu 9. Dynamic mapping hoạt động thế nào khi document có field mới?
A. Tự xóa field không thuộc mapping ban đầu
B. Tự đổi analyzer của mọi field đã có
C. Tự suy luận mapping cho field được phát hiện
D. Tự tạo shard mới cho mỗi field vừa được phát hiện
Đáp án đúng: C

Câu 10. Muốn đổi mapping của field từ `text` sang `date` khi đã có dữ liệu, nên làm gì?
A. Sửa field type trực tiếp trên index đang dùng
B. Tạo index mới và reindex với mapping mới
C. Đóng index để đổi type của field đã có
D. Gọi refresh để chuyển type của các document
Đáp án đúng: B

Câu 11. Với field `keyword`, cần lọc chuỗi theo giá trị chính xác, chọn query nào?
A. `fuzzy` query khớp theo khoảng cách ký tự
B. `match_phrase` query khớp các cụm từ
C. `match` query khớp các token văn bản
D. `term` query khớp đúng giá trị đã index
Đáp án đúng: D

Câu 12. Để tìm token theo đúng thứ tự tạo thành cụm từ, nên dùng query nào?
A. `match_phrase` kiểm soát trật tự token
B. `prefix` query kiểm soát trật tự của token
C. `match` kiểm soát trật tự token
D. `term` kiểm soát trật tự token
Đáp án đúng: A

Câu 13. Trong `bool` query, mệnh đề `filter` có đặc điểm nào?
A. Giới hạn kết quả và cộng thêm điểm liên quan
B. Giới hạn kết quả mà không cộng điểm liên quan
C. Ưu tiên kết quả bằng cách thay đổi analyzer
D. Ưu tiên kết quả bằng cách bỏ qua mọi cache
Đáp án đúng: B

Câu 14. Với `minimum_should_match: 2`, yêu cầu nào được áp dụng cho `should`?
A. Ít nhất hai shard phải trả về kết quả
B. Ít nhất hai token phải nằm cạnh nhau
C. Ít nhất hai điều kiện `must` đều phải khớp
D. Ít nhất hai điều kiện `should` phải khớp
Đáp án đúng: D

Câu 15. Mệnh đề `must_not` trong `bool` query thường làm gì?
A. Thay analyzer của field khi document khớp
B. Loại document khớp điều kiện được nêu
C. Cộng điểm cho document khớp điều kiện
D. Chỉ chạy aggregation trên document bị loại
Đáp án đúng: B

Câu 16. Trong range query, kết hợp `gte` và `lt` có ý nghĩa gì?
A. Loại cận dưới và gồm cận trên của khoảng
B. Loại cả hai cận dưới và trên của khoảng
C. Gồm cận dưới và loại cận trên của khoảng
D. Gồm cả hai cận dưới và trên của khoảng
Đáp án đúng: C

Câu 17. Muốn tìm cùng chuỗi trên `title` và `body`, lựa chọn nào phù hợp?
A. Đặt cả hai field vào `multi_match` query
B. Đặt cả hai field vào `range` query
C. Đặt cả hai field vào `exists` query để tìm
D. Đặt cả hai field vào `term` query
Đáp án đúng: A

Câu 18. Điểm liên quan BM25 dựa chủ yếu trên những yếu tố nào?
A. Tần suất từ, độ hiếm và độ dài trường
B. Phiên bản mapping, refresh và trạng thái index
C. Số replica, mức nén và thời gian refresh
D. Số shard, kích thước heap và thời gian merge
Đáp án đúng: A

Câu 19. Tùy chọn `explain` trong tìm kiếm giúp làm rõ điều gì?
A. Vì sao shard được chuyển sang node khác
B. Vì sao index nhận thêm một segment mới
C. Vì sao document nhận một mức điểm truy vấn
D. Vì sao snapshot được lưu tại một repository cụ thể
Đáp án đúng: C

Câu 20. Profile API giúp phân tích phần nào của truy vấn chậm?
A. Trạng thái lưu trữ của từng repository
B. Phiên bản mapping của từng data stream
C. Quyền truy cập index của từng tài khoản đăng nhập
D. Thời gian thực thi từng thành phần truy vấn
Đáp án đúng: D

Câu 21. `terms` aggregation chủ yếu trả về dạng kết quả nào?
A. Các segment theo thứ tự lần merge cuối
B. Các bucket theo giá trị phân biệt của field
C. Các document theo thứ tự điểm liên quan
D. Các shard theo thứ tự sức chứa còn trống
Đáp án đúng: B

Câu 22. Muốn đếm sự kiện theo từng ngày, aggregation nào phù hợp?
A. `date_histogram` dùng khoảng thời gian ngày
B. `terms` dùng khoảng thời gian ngày
C. `range` dùng khoảng thời gian ngày
D. `histogram` dùng khoảng thời gian ngày
Đáp án đúng: A

Câu 23. Muốn tính trung bình `price` của document khớp truy vấn, chọn gì?
A. `max` metric aggregation trên trường giá
B. `value_count` aggregation trên trường giá
C. `sum` metric aggregation trên trường giá
D. `avg` metric aggregation trên trường giá
Đáp án đúng: D

Câu 24. `cardinality` aggregation trả về đại lượng nào?
A. Đo dung lượng lưu trữ của từng shard
B. Đếm chính xác document theo từng giá trị trong index
C. Ước lượng số giá trị phân biệt của field
D. Tính tổng mọi giá trị số của một field
Đáp án đúng: C

Câu 25. Vì sao `doc_values` thường có lợi khi sort và aggregation?
A. Cung cấp dữ liệu theo cột cho thao tác đọc
B. Cung cấp tokenizer tùy chỉnh khi truy vấn
C. Cung cấp replica dự phòng cho dữ liệu gốc
D. Cung cấp snapshot theo chu kỳ cho index
Đáp án đúng: A

Câu 26. Kiểu field nào phù hợp để lưu embedding cho vector search?
A. `text` lưu các thành phần embedding
B. `object` lưu các thành phần embedding
C. `dense_vector` lưu các thành phần embedding
D. `keyword` lưu từng thành phần của embedding
Đáp án đúng: C

Câu 27. Mục đích chính của tìm kiếm kNN trên vector là gì?
A. Tìm vector gần truy vấn theo độ tương đồng
B. Tìm shard gần node theo độ trễ network
C. Tìm token gần từ khóa theo thứ tự vị trí văn bản
D. Tìm document gần nhau theo timestamp
Đáp án đúng: A

Câu 28. Kết hợp BM25 và kNN trong hybrid search có ý nghĩa gì?
A. Phối hợp primary và replica theo điểm
B. Phối hợp mapping và analyzer theo node
C. Phối hợp tín hiệu từ khóa và ngữ nghĩa
D. Phối hợp cache segment và filesystem
Đáp án đúng: C

Câu 29. Vai trò của primary shard trong một index là gì?
A. Lưu một phần dữ liệu chính của index
B. Chỉ lưu các request tìm kiếm đã cache
C. Chỉ lưu metadata về các node cluster
D. Chỉ lưu bản sao dự phòng của index
Đáp án đúng: A

Câu 30. Replica shard chủ yếu giúp cải thiện điều gì?
A. Chia document mới thành nhiều index con
B. Thay mapping để tối ưu các field đã có
C. Thay primary shard trong mọi lần ghi
D. Tăng độ sẵn sàng và năng lực tìm kiếm
Đáp án đúng: D

Câu 31. Mặc định Elasticsearch phân phối document đến primary shard thế nào?
A. Sort timestamp để chọn primary shard
B. Hash `_id` để chọn primary shard
C. Round-robin request tới primary shard
D. Hash tên field để chọn primary shard
Đáp án đúng: B

Câu 32. Sau khi ghi document, thao tác nào giúp dữ liệu trở nên tìm kiếm được?
A. Chờ hoặc gọi `snapshot` trên index
B. Chờ hoặc gọi `refresh` trên index
C. Chờ hoặc gọi `rollover` trên index
D. Chờ hoặc gọi `flush` trên index
Đáp án đúng: B

Câu 33. Khi cần gửi nhiều thao tác ghi trong một lần, API nào phù hợp?
A. Bulk API gom các thao tác ghi thành batch
B. Profile API gom các thao tác ghi thành batch
C. Search API gom các thao tác ghi thành batch
D. Analyze API gom các thao tác ghi thành batch
Đáp án đúng: A

Câu 34. Muốn phân trang sâu với ảnh chụp kết quả ổn định, kết hợp nào thích hợp?
A. `from` kết hợp scroll và refresh liên tục
B. `size` kết hợp force merge định kỳ
C. `sort` kết hợp đổi mapping giữa trang
D. `search_after` kết hợp point-in-time (PIT)
Đáp án đúng: D

Câu 35. Index Lifecycle Management tự động hóa việc nào?
A. Tăng điểm BM25 cho document theo policy
B. Chuyển pha lưu trữ và xóa index theo policy
C. Chặn truy vấn thiếu user ID theo policy
D. Chuyển mọi field thành keyword theo policy
Đáp án đúng: B

Câu 36. Alias ghi kết hợp rollover được dùng với mục đích nào?
A. Đổi query DSL thành SQL khi tổng hợp
B. Đổi type field trên index cũ khi quá tải
C. Đổi index nhận dữ liệu khi đạt điều kiện
D. Đổi token trong analyzer vào lúc truy vấn
Đáp án đúng: C

Câu 37. Cách nào phù hợp để backup và khôi phục index giữa cluster?
A. Lưu cache tìm kiếm vào hệ thống tệp
B. Tạo snapshot index vào repository hỗ trợ
C. Sao chép các file segment đang mở một cách thủ công
D. Gọi refresh để đồng bộ sang cluster khác
Đáp án đúng: B

Câu 38. Khi cấp API key dùng cho ứng dụng đọc dữ liệu, nguyên tắc nào nên áp dụng?
A. Chia sẻ chung một API key cho mọi môi trường
B. Tắt phân quyền với các endpoint nội bộ
C. Cấp quyền quản trị toàn cluster cho ứng dụng
D. Giới hạn quyền đọc trên các index cần thiết
Đáp án đúng: D

Câu 39. Java API Client của Elasticsearch hỗ trợ công việc nào?
A. Gửi request có kiểu dữ liệu qua client Java
B. Tạo mapping trong Spring không cần kết nối
C. Biên dịch truy vấn Query DSL thành Java bytecode
D. Chuyển index Elasticsearch thành bảng JDBC
Đáp án đúng: A

Câu 40. Trong Spring Data Elasticsearch, `@Document(indexName=...)` dùng để làm gì?
A. Gắn entity Java với tên index Elasticsearch
B. Gắn repository method với profile truy vấn
C. Gắn shard replica với node đang chạy Spring
D. Gắn cấu hình TLS với index Elasticsearch
Đáp án đúng: A
