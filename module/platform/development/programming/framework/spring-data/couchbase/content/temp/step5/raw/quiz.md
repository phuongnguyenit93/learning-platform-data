Câu 1. @Document trong Spring Data Couchbase có vai trò gì?
A. Đánh dấu entity được map thành document Couchbase
B. Chỉ định collection đích cho mọi repository method
C. Bật optimistic locking dù entity không có version
D. Đặt expiry bắt buộc cho mọi document khi lưu
Đáp án đúng: A

Câu 2. Annotation @Id trên entity Couchbase thường xác định điều gì?
A. Tên field được dùng làm secondary index mặc định
B. Mã CAS được dùng trong mỗi lần cập nhật document
C. Tên scope cần chọn khi repository khởi tạo
D. Document key dùng đọc và ghi bản ghi qua KV
Đáp án đúng: D

Câu 3. Khi property Java cần tên trường JSON khác, nên dùng gì?
A. @Id để đổi tên các thuộc tính JSON trên entity
B. @Version để đăng ký alias của field trong index
C. @Field để ánh xạ sang tên trường trong document
D. @Expiry để chọn tên field khi tạo SQL++ query
Đáp án đúng: C

Câu 4. Khi entity chứa object con được hỗ trợ mapping, kết quả lưu phổ biến là gì?
A. Object con tự động thành document ở collection khác
B. Object con được lưu làm metadata CAS của entity
C. Object con được biểu diễn dạng JSON lồng nhau
D. Object con được tách thành các field cấp bucket
Đáp án đúng: C

Câu 5. Vì sao metadata kiểu có thể hữu ích khi ánh xạ entity đa hình?
A. Giúp converter chọn đúng kiểu Java khi đọc dữ liệu
B. Cho phép @Id tự chọn bucket theo tên class con
C. Buộc SQL++ dùng index của từng kiểu Java khi query
D. Tạo collection mới cho mỗi lớp kế thừa khi save
Đáp án đúng: A

Câu 6. Nếu một kiểu giá trị chưa được chuyển đổi đúng qua mapper, cách nào phù hợp?
A. Đặt CAS bằng không để SDK bỏ qua chuyển đổi field
B. Tạo primary index trước khi serialize property Java
C. Chỉ tăng expiry để JSON lưu được kiểu dữ liệu mới
D. Đăng ký converter tùy chỉnh cho chiều đọc và ghi
Đáp án đúng: D

Câu 7. CouchbaseRepository giúp triển khai thao tác nào thuận tiện?
A. Tạo bucket mới khi lần đầu gọi save trên entity
B. Phát hành transaction nhiều cluster qua một method
C. Quản lý index tự động cho mọi câu SQL++ tùy biến
D. CRUD và khai báo query theo interface repository
Đáp án đúng: D

Câu 8. Khi đã biết document ID, repository.findById thường tận dụng gì?
A. Đọc theo document key qua dịch vụ key-value
B. Dò document bằng primary index của Query Service
C. Lấy tất cả document rồi lọc ID ở client Java
D. Tạo secondary index mới theo ID trước khi đọc
Đáp án đúng: A

Câu 9. Derived query tìm theo trường status thay vì ID thường cần gì?
A. Truy vấn SQL++ với index phù hợp điều kiện status
B. KV get trực tiếp dù status không nằm trong key
C. Tra CAS token rồi lọc trạng thái trong Java SDK
D. Index trên trường expiry thay cho điều kiện status
Đáp án đúng: A

Câu 10. Để viết SQL++ cho một repository method, nên dùng cơ chế nào?
A. @Field trên method để chọn biểu thức WHERE tùy ý
B. @Query khai báo SQL++ và tham số cần truy vấn
C. @Id trên repository method để tạo SELECT mặc định
D. @Version trên method để chọn tên secondary index
Đáp án đúng: B

Câu 11. Vì sao nên bind tham số thay vì nối input vào chuỗi SQL++?
A. Buộc SQL++ chạy qua dịch vụ KV thay Query Service
B. Tạo covering index cho mọi giá trị input khác nhau
C. Tách giá trị khỏi cú pháp và giảm rủi ro injection
D. Đảm bảo transaction được tự mở cho từng câu SQL++
Đáp án đúng: C

Câu 12. Khi cần nhiều thao tác đọc ghi linh hoạt ngoài query method, dùng gì?
A. CouchbaseRepository vì template chỉ hỗ trợ read
B. Một primary index để thay toàn bộ logic thao tác
C. Chỉ SDK transaction callback để làm CRUD đơn giản
D. CouchbaseTemplate cho thao tác dữ liệu tùy biến
Đáp án đúng: D

Câu 13. Khi chọn repository và CouchbaseTemplate, nhận định nào phù hợp?
A. Template chỉ mapping entity, không có thao tác ghi
B. Repository không dùng được query lọc theo field
C. Template phải quét primary index khi get theo ID
D. Repository tiện CRUD; template cho thao tác tùy biến
Đáp án đúng: D

Câu 14. Vì sao primary index dễ là nút thắt với SQL++ production?
A. Không thể truy vấn collection khi có primary index
B. Có thể dẫn đến quét nhiều entry không liên quan
C. Bắt buộc mọi getById chờ cập nhật chỉ mục trước
D. Chỉ sử dụng được khi document key là kiểu số
Đáp án đúng: B

Câu 15. Secondary index trên status phù hợp nhất với tác vụ nào?
A. Lấy document đã biết ID bằng KV lookup trực tiếp
B. Kiểm tra CAS khi save đồng thời lên một document
C. Tìm document bằng SQL++ lọc theo field status
D. Gia hạn TTL cho các document theo giá trị status
Đáp án đúng: C

Câu 16. Khi thiết kế composite index, yếu tố nào thường quan trọng?
A. Thứ tự các field Java trong entity source code
B. Tên bean repository được tạo lúc Spring khởi động
C. Thứ tự document được ghi trong collection theo TTL
D. Thứ tự field so với predicate và sort của query
Đáp án đúng: D

Câu 17. Lợi ích chính của covering index là gì khi chạy SQL++?
A. Bảo đảm mutation đã replicate tới mọi data node
B. Trả field từ index mà không cần fetch document
C. Chuyển SQL++ query thành KV lookup theo ID
D. Tự ngăn xung đột CAS khi cập nhật document
Đáp án đúng: B

Câu 18. Muốn xem index được chọn và bước FETCH của SQL++, nên dùng gì?
A. EXPLAIN để kiểm tra execution plan của truy vấn
B. @Version để ghi thông tin Query Service vào entity
C. CAS để xem các field đã được index cập nhật chưa
D. TTL để xuất kế hoạch SELECT kèm thời hạn lưu
Đáp án đúng: A

Câu 19. Khi phân trang dữ liệu thường xuyên thay đổi, vì sao cần ORDER BY ổn định?
A. Tăng số bản sao được dùng để đọc dữ liệu SQL++
B. Giữ CAS của các document cùng một giá trị để sort
C. Buộc Query Service đọc toàn bộ document theo key
D. Giảm trùng, sót khi thứ tự trả về có thể biến đổi
Đáp án đúng: D

Câu 20. Với truy vấn LIMIT/OFFSET có OFFSET rất lớn, rủi ro nào xuất hiện?
A. SDK buộc tăng TTL của document mỗi khi qua trang
B. CAS tự thay đổi khi bỏ qua một hàng trong kết quả
C. Phải bỏ qua nhiều hàng nên query tốn thêm tài nguyên
D. Query Service tự chuyển OFFSET thành thao tác KV get
Đáp án đúng: C

Câu 21. Trong Couchbase, bucket có vị trí nào trong cấu trúc dữ liệu?
A. Cấp chứa các scope và collection dùng lưu document
B. Một trường JSON bắt buộc có trên mọi entity Couchbase
C. Một index chuyên dụng dùng để sắp xếp SQL++ query
D. Một đơn vị transaction được tạo theo mỗi repository call
Đáp án đúng: A

Câu 22. Scope trong Couchbase được dùng để tổ chức như thế nào?
A. Nhóm nhiều bucket khác cluster vào một keyspace
B. Định nghĩa CAS dùng chung cho toàn bộ document
C. Đặt expiry chung cho tất cả bucket không liên quan
D. Nhóm nhiều collection liên quan trong cùng bucket
Đáp án đúng: D

Câu 23. Collection trong Couchbase chủ yếu chứa loại đối tượng nào?
A. Một danh sách repository bean của từng entity Java
B. Các transaction log dùng để commit nhiều bucket
C. Các document thuộc một scope và bucket xác định
D. Một bộ index không phụ thuộc document trong bucket
Đáp án đúng: C

Câu 24. Để map entity vào scope và collection riêng, cách nào phù hợp?
A. Gắn @Version bằng đường dẫn bucket.scope.collection
B. Đặt @Id thành tên collection trước khi gọi save
C. Gắn @Field lên entity class thay vì property Java
D. Dùng @Scope và @Collection theo cấu hình mapping
Đáp án đúng: D

Câu 25. Khi truy vấn SQL++ trên collection khác default, điều gì cần đúng?
A. CAS của các document phải trùng ở nhiều collection
B. Keyspace hoặc query context trỏ đúng collection
C. TTL của scope phải được tắt trước khi chạy SELECT
D. @Id của entity phải trùng tên của collection đích
Đáp án đúng: B

Câu 26. Một chiến lược thiết kế document key cho nhiều tenant nên ưu tiên gì?
A. Key bằng CAS vì CAS không đổi giữa các mutation
B. Key ổn định và phân biệt tenant, loại bản ghi
C. Một key chung cho mọi tenant trong cùng collection
D. Chỉ dùng timestamp đến giây làm khóa duy nhất
Đáp án đúng: B

Câu 27. Nếu hai entity sử dụng cùng document ID trong một collection, hệ quả nào có thể gặp?
A. SDK tự thêm hậu tố để lưu hai document khác nhau
B. Couchbase tự chuyển entity thứ hai sang scope mới
C. Cùng nhắm một document, dễ ghi đè hoặc xung đột
D. Repository ghép cả hai thành hai record độc lập
Đáp án đúng: C

Câu 28. TTL thường phù hợp với loại dữ liệu Couchbase nào?
A. Dữ liệu tạm thời cần tự hết hạn theo chính sách
B. Dữ liệu cần tạo covering index cho mọi query
C. Dữ liệu chỉ cập nhật bằng CAS và giữ lâu dài
D. Dữ liệu cần bảo đảm read consistency mạnh
Đáp án đúng: A

Câu 29. Annotation @Expiry trong Spring Data Couchbase liên quan đến gì?
A. Chọn index mặc định cho repository query theo ID
B. Thiết lập thời hạn tồn tại của document được lưu
C. Đánh dấu field cần so sánh CAS khi cập nhật
D. Chỉ định tên bucket truy xuất trong SQL++ query
Đáp án đúng: B

Câu 30. Khi document đã hết hạn TTL, thao tác đọc hợp lệ thường thế nào?
A. KV đọc được bản ghi nhưng SQL++ mặc định không đọc
B. Không còn trả document như dữ liệu đang có hiệu lực
C. Document được phục hồi tự động từ bản sao gần nhất
D. Document vẫn trả nội dung nhưng metadata TTL bị xóa
Đáp án đúng: B

Câu 31. Khi update document đang có TTL, điều gì cần chủ động xác minh?
A. Kiểm tra thao tác ghi giữ hay đặt lại expiry
B. Mọi update đều giữ nguyên TTL bất kể loại API
C. Mọi update sẽ xóa TTL theo mặc định ở mọi phiên bản
D. CAS token tự quyết định số giây TTL còn lại
Đáp án đúng: A

Câu 32. CAS của Couchbase chủ yếu giúp xử lý vấn đề nào?
A. Đảm bảo mọi SQL++ index đã cập nhật sau khi ghi
B. Phát hiện ghi đè dựa trên phiên bản document cũ
C. Phân quyền đọc dữ liệu tại từng scope, collection
D. Phân trang truy vấn bằng thứ tự key tăng dần
Đáp án đúng: B

Câu 33. Khi Spring Data Couchbase entity dùng @Version, cơ chế nào liên quan?
A. Cơ chế tự nâng phiên bản schema của bucket đã chọn
B. Optimistic locking dựa trên giá trị CAS của document
C. Định nghĩa secondary index ưu tiên cho truy vấn entity
D. Cơ chế expiry tự động sau một số lần cập nhật field
Đáp án đúng: B

Câu 34. Hai client đọc cùng một document rồi ghi với CAS cũ, tình huống nào xảy ra?
A. Cả hai ghi thành công và tự merge khác biệt field
B. Couchbase tự tăng transaction ID của lần ghi sau
C. Lần ghi sau có thể bị conflict vì CAS không khớp
D. Query Service chuyển lần ghi thứ hai thành INSERT
Đáp án đúng: C

Câu 35. Khi bị optimistic-lock conflict, hướng xử lý nào an toàn hơn?
A. Retry lại cùng CAS cũ liên tục đến khi ghi thành công
B. Đọc lại document mới, merge hoặc retry có giới hạn
C. Bỏ kiểm tra CAS rồi ghi đè để loại trạng thái lỗi
D. Tăng index replica để CAS cũ trở thành hợp lệ
Đáp án đúng: B

Câu 36. Khi nghiệp vụ cần cập nhật nhiều document như một đơn vị ACID, nên xem xét gì?
A. Dùng tính năng transaction Couchbase khi phù hợp
B. Dùng chung một CAS token để khóa mọi document
C. Tạo primary index cho nhóm document cần cập nhật
D. Dùng TTL bằng không thay transaction nhiều document
Đáp án đúng: A

Câu 37. Vì sao transaction Couchbase không tự bao gồm HTTP call ra hệ thống ngoài?
A. Mọi HTTP client mặc định tham gia commit KV transaction
B. CAS token tự hoàn tác request bên ngoài khi rollback
C. Query Service ghi lại response để compensation tự động
D. Transaction DB không rollback được side effect HTTP
Đáp án đúng: D

Câu 38. Nếu logic transaction có thể được thực thi lại sau conflict, cần chú ý gì?
A. Tạo order ID mới mỗi lần callback được thực thi lại
B. Gửi payment request một lần ở từng attempt transaction
C. Bỏ business validation khi conflict để giảm lỗi retry
D. Tránh side effect không idempotent khi retry callback
Đáp án đúng: D

Câu 39. Vì sao SQL++ có thể chưa thấy một KV mutation vừa thành công?
A. KV mutation chỉ tồn tại sau khi tạo primary index
B. SQL++ mặc định đọc snapshot của lần backup trước
C. Index SQL++ cập nhật không đồng bộ sau KV ghi
D. Couchbase chỉ query document đã có CAS bằng không
Đáp án đúng: C

Câu 40. Khi cần SQL++ đợi các index bắt kịp mutation hiện có, nên cân nhắc gì?
A. Scan consistency REQUEST_PLUS với chi phí chờ phù hợp
B. Tắt secondary index để mỗi SELECT đọc KV trực tiếp
C. Dùng CAS của document làm giá trị tham số OFFSET
D. Đặt expiry về zero cho toàn bộ document được query
Đáp án đúng: A

Câu 41. Khi đã biết document ID và muốn tránh độ trễ cập nhật index, nên làm gì?
A. Dùng SQL++ qua primary index rồi lọc ID trong Java
B. Đọc bằng KV theo ID thay cho SQL++ lọc theo field
C. Tạo composite index riêng cho mỗi document key mới
D. Dùng SQL++ có OFFSET bằng không để bỏ qua index
Đáp án đúng: B

Câu 42. Durability level của một thao tác ghi Couchbase nói về điều gì?
A. Mức xác nhận ghi tới replica hoặc vùng lưu trữ
B. Mức đồng bộ cập nhật secondary index của SQL++
C. Số lần retry của optimistic locking khi conflict
D. Thứ tự ưu tiên Query Service và KV Service
Đáp án đúng: A

Câu 43. ReactiveCouchbaseRepository thường dùng Mono cho kiểu kết quả nào?
A. Luồng nhiều document luôn được trả qua một subscription
B. Danh sách entity đã lấy xong bằng blocking JDBC
C. Kết quả không quá một entity theo cách bất đồng bộ
D. Đối tượng transaction chứa tất cả entity trong scope
Đáp án đúng: C

Câu 44. Với truy vấn reactive trả về nhiều document, kiểu kết quả phù hợp là gì?
A. Mono chỉ có một document và bỏ các bản ghi còn lại
B. Optional chờ Query Service bằng một lời gọi blocking
C. Flux phát nhiều phần tử theo luồng bất đồng bộ
D. List tạo sẵn và trả đồng bộ qua Repository<T,ID>
Đáp án đúng: C

Câu 45. Vì sao tránh block() trong pipeline WebFlux gọi Couchbase reactive?
A. Không chiếm event-loop thread chờ I/O hoàn tất
B. Block khiến CAS tự reset cho mọi document được đọc
C. Block tự mở transaction mới mỗi lần subscribe lại
D. Block làm SDK chuyển query sang KV dù cần SQL++
Đáp án đúng: A

Câu 46. Khi Couchbase có dấu hiệu quá tải, hướng vận hành nào an toàn?
A. Gửi retry không giới hạn để tận dụng hết connection
B. Tăng timeout vô hạn để tránh lỗi trả về client
C. Bỏ giới hạn số query đồng thời để tăng throughput
D. Giới hạn concurrent calls, timeout và retry có backoff
Đáp án đúng: D

Câu 47. Khi kiểm thử repository query theo field, cần xác minh điều gì?
A. Mock mỗi getById là đủ cho mọi repository query khác
B. SQL++ và index thực sự chạy đúng với dữ liệu kiểm thử
C. Chỉ kiểm tra bean repository được khởi tạo không lỗi
D. Chỉ đo thời gian build JAR thay cho thời gian SQL++
Đáp án đúng: B

Câu 48. Để vận hành kết nối Couchbase an toàn, nên áp dụng gì?
A. Dùng quyền administrator cho mọi ứng dụng để tránh 403
B. Ghi credential và query input vào log INFO khi lỗi
C. Quyền tối thiểu theo bucket/scope và quan sát lỗi, latency
D. Gắn document key chứa thông tin cá nhân làm metric tag
Đáp án đúng: C
