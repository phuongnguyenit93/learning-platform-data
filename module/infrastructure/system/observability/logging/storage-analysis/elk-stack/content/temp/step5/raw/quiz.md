Câu 1. Trong kiến trúc ELK, vai trò nào mô tả đúng Elasticsearch?
A. Index, lưu trữ và tìm kiếm tài liệu log
B. Thu thập log từ file và hệ điều hành
C. Chuyển đổi log thô thành cấu trúc trường
D. Hiển thị dashboard và truy vấn tương tác
Đáp án đúng: A

Câu 2. Elasticsearch lưu một document theo dạng dữ liệu nào?
A. Một tài liệu JSON trong một index
B. Một file nhị phân trong Logstash pipeline
C. Một bản ghi CSV trong Kibana dashboard
D. Một hàng SQL trong một database quan hệ
Đáp án đúng: A

Câu 3. Inverted index giúp Elasticsearch thực hiện thao tác nào?
A. Đồng bộ bản sao giữa các cluster Elasticsearch
B. Sắp xếp tài liệu theo thứ tự file được gửi
C. Nén toàn bộ document thành một trường duy nhất
D. Tìm document theo term đã được index
Đáp án đúng: D

Câu 4. Mapping trong Elasticsearch chủ yếu định nghĩa điều gì?
A. Thứ tự các bước trong Logstash pipeline
B. Lịch làm mới dashboard của Kibana
C. Địa chỉ mạng của từng Elasticsearch node
D. Kiểu dữ liệu và thuộc tính của field
Đáp án đúng: D

Câu 5. Dynamic mapping có thể tạo ra kết quả nào khi index document mới?
A. Cluster tự tạo replica cho từng document mới
B. Elasticsearch suy luận kiểu field từ dữ liệu
C. Kibana tự tạo dashboard từ mọi field mới
D. Logstash tự tạo output cho từng field mới
Đáp án đúng: B

Câu 6. Một analyzer cho trường text thường gồm các bước nào?
A. Input plugin, filter plugin và output plugin
B. Primary shard, replica shard và coordinator node
C. Character filters, tokenizer và token filters
D. Index template, data stream và lifecycle policy
Đáp án đúng: C

Câu 7. Khác biệt chính giữa `text` và `keyword` trong mapping là gì?
A. `text` chỉ nhận số, `keyword` chỉ nhận ngày giờ
B. `text` dùng cho metadata, `keyword` dùng cho JSON
C. `text` giữ nguyên giá trị, `keyword` tách thành token
D. `text` phân tích nội dung, `keyword` giữ giá trị nguyên
Đáp án đúng: D

Câu 8. Multi-field cho phép một giá trị được lập chỉ mục thế nào?
A. Hiển thị một field trên nhiều Kibana dashboard
B. Tạo nhiều bản sao vật lý của một document
C. Index cùng field theo nhiều kiểu con khác nhau
D. Gửi cùng log qua nhiều Logstash pipeline
Đáp án đúng: C

Câu 9. Primary shard trong Elasticsearch đảm nhiệm vai trò nào?
A. Điều phối truy vấn Kibana đến mọi data view
B. Nhận log thô trước khi Logstash parse chúng
C. Lưu bản sao dự phòng của mọi index trong cluster
D. Lưu một phần dữ liệu được phân vùng của index
Đáp án đúng: D

Câu 10. Replica shard mang lại lợi ích chính nào cho index?
A. Quản lý thời gian lưu log theo từng ngày
B. Dự phòng dữ liệu và hỗ trợ năng lực đọc
C. Thay thế mapping khi field đổi kiểu dữ liệu
D. Phân tích văn bản trước khi ghi document
Đáp án đúng: B

Câu 11. Khi một primary shard mất node, replica phù hợp có thể làm gì?
A. Được đổi thành index template cho index mới
B. Được gửi sang Kibana để dựng dashboard
C. Được nâng thành primary để duy trì hoạt động
D. Được chuyển thành Logstash persistent queue
Đáp án đúng: C

Câu 12. Refresh trong Elasticsearch ảnh hưởng điều gì?
A. Làm thay đổi gần đây có thể được tìm kiếm
B. Chuyển replica thành primary trong mọi trường hợp
C. Xóa document hết hạn theo chính sách ILM
D. Ghi snapshot đầy đủ lên kho lưu trữ từ xa
Đáp án đúng: A

Câu 13. Bulk API thường cải thiện ingest bằng cách nào?
A. Gửi từng document qua một request riêng
B. Gửi nhiều thao tác index trong một request
C. Gộp nhiều index thành một shard duy nhất
D. Đưa toàn bộ log vào một field text duy nhất
Đáp án đúng: B

Câu 14. Trường `_source` trong document thường lưu nội dung gì?
A. Trạng thái replica của shard đang lưu document
B. Thống kê thời gian xử lý của Logstash filter
C. Danh sách term của inverted index đã tạo
D. Nội dung document gốc được gửi để index
Đáp án đúng: D

Câu 15. Ingest pipeline của Elasticsearch xử lý document ở thời điểm nào?
A. Định tuyến alert sau khi Kibana phát hiện lỗi
B. Áp dụng processor trước khi document được index
C. Chạy truy vấn sau khi document đã được tìm kiếm
D. Tạo snapshot sau khi index đã rollover
Đáp án đúng: B

Câu 16. Trong Logstash, pipeline tiêu chuẩn gồm những phần nào?
A. `source`, `mapping` và `dashboard`
B. `primary`, `replica` và `coordinator`
C. `input`, `filter` và `output`
D. `agent`, `fleet` và `integration`
Đáp án đúng: C

Câu 17. Grok filter trong Logstash thường dùng để làm gì?
A. Tạo biểu đồ thời gian từ dữ liệu đã index
B. Mã hóa TLS cho kết nối giữa các Elasticsearch node
C. Chia index thành primary shard và replica shard
D. Trích xuất field từ dòng log có cấu trúc mẫu
Đáp án đúng: D

Câu 18. Mutate filter của Logstash thường hỗ trợ thao tác nào?
A. Tạo snapshot và phục hồi một Elasticsearch index
B. Phân phối replica shard sang node khác
C. Đổi tên, xóa hoặc chuyển kiểu field
D. Tạo role và API key trong Kibana
Đáp án đúng: C

Câu 19. Date filter trong Logstash hữu ích nhất cho công việc nào?
A. Đo thời gian chạy của từng filter plugin
B. Phân tích timestamp và gán thời gian sự kiện
C. Định tuyến log đến dashboard theo người dùng
D. Tạo lịch rollover cho index theo dung lượng
Đáp án đúng: B

Câu 20. Persistent queue của Logstash chủ yếu giúp ích điều gì?
A. Thay thế hoàn toàn cơ chế retry của output
B. Đệm event trên đĩa khi output chậm hoặc gián đoạn
C. Lưu bản sao index Elasticsearch sang vùng khác
D. Giữ lịch sử truy vấn KQL trên Kibana
Đáp án đúng: B

Câu 21. Dead letter queue của Logstash phù hợp lưu loại event nào?
A. Mọi event đang chờ được đọc từ file đầu vào
B. Mọi event có thời gian xử lý filter dưới một giây
C. Event bị từ chối do lỗi không thể retry như mapping
D. Mọi event đã được index thành công vào Elasticsearch
Đáp án đúng: C

Câu 22. Beats truyền thống được thiết kế chủ yếu cho vai trò nào?
A. Engine xử lý truy vấn SQL trên dữ liệu log
B. Agent nhẹ thu thập và gửi dữ liệu đến hệ thống
C. Cơ sở dữ liệu phân tán lưu và tìm kiếm document
D. Công cụ dashboard phân tích log trên trình duyệt
Đáp án đúng: B

Câu 23. Elastic Agent khác cách triển khai nhiều Beat riêng lẻ ở điểm nào?
A. Một agent chỉ hỗ trợ đúng một loại log file
B. Một agent thay thế Elasticsearch data node
C. Một agent lưu dashboard thay cho Kibana
D. Một agent hợp nhất nhiều chức năng thu thập
Đáp án đúng: D

Câu 24. Fleet trong Elastic Stack giúp quản lý điều gì?
A. Chính sách và vòng đời của Elastic Agent
B. Truy vấn KQL và dashboard của người dùng
C. Snapshot repository của cluster Elasticsearch
D. Mapping và replica của từng Elasticsearch index
Đáp án đúng: A

Câu 25. Data view trong Kibana cung cấp khả năng nào?
A. Chọn tập index hoặc data stream để khám phá
B. Tạo primary shard cho một index mới
C. Định nghĩa processor chạy trong Logstash
D. Quản lý API key cho từng Elasticsearch node
Đáp án đúng: A

Câu 26. KQL trong Kibana thường được dùng cho mục đích gì?
A. Định nghĩa pipeline xử lý event trong Logstash
B. Lọc và tìm kiếm document theo field
C. Quản lý shard allocation giữa các node
D. Tạo mapping và analyzer cho index mới
Đáp án đúng: B

Câu 27. Dashboard trong Kibana giúp người vận hành làm gì?
A. Tạo chứng chỉ TLS cho Elasticsearch cluster
B. Kết hợp biểu đồ và dữ liệu thành màn hình theo dõi
C. Chuyển document thành inverted index trên node
D. Phân phối event giữa các Logstash worker
Đáp án đúng: B

Câu 28. Elastic Common Schema (ECS) giúp hệ thống logging đạt mục tiêu nào?
A. Nén mọi event thành một định dạng nhị phân
B. Đồng bộ thời gian scrape của các Beats agent
C. Giới hạn mọi index chỉ có một primary shard
D. Chuẩn hóa tên field giữa các nguồn log
Đáp án đúng: D

Câu 29. Index Lifecycle Management (ILM) hỗ trợ tự động hóa việc gì?
A. Đăng ký Elastic Agent với Fleet Server
B. Phân tích nội dung log thành token tìm kiếm
C. Định tuyến từng request KQL đến Kibana node
D. Chuyển index qua các giai đoạn lưu trữ và xóa
Đáp án đúng: D

Câu 30. Rollover action trong ILM thường tạo kết quả nào?
A. Tạo index ghi mới khi index hiện tại đạt điều kiện
B. Tạo snapshot mới mỗi khi có document được index
C. Đổi mọi field text thành keyword trong index
D. Chuyển tất cả replica shard thành primary shard
Đáp án đúng: A

Câu 31. Data stream phù hợp nhất với kiểu dữ liệu nào?
A. Dữ liệu quan hệ có nhiều khóa ngoại bắt buộc
B. Dữ liệu nhị phân không có timestamp sự kiện
C. Dữ liệu giao dịch cần cập nhật tại chỗ thường xuyên
D. Dữ liệu sự kiện append theo thời gian
Đáp án đúng: D

Câu 32. Snapshot Elasticsearch nên được hiểu là gì?
A. Bản sao lưu index và trạng thái cluster được chọn
B. File log tạm do Logstash ghi trước khi gửi
C. Replica shard luôn đồng bộ trong cùng cluster
D. Cache của các truy vấn KQL gần đây
Đáp án đúng: A

Câu 33. Muốn phục hồi dữ liệu sau khi cluster gặp sự cố, cần chuẩn bị gì?
A. Kibana dashboard đã export thành file JSON
B. Snapshot repository đã cấu hình và snapshot hợp lệ
C. Logstash pipeline đã giữ lại mọi event đã xử lý
D. Replica shard duy nhất còn nằm trên node lỗi
Đáp án đúng: B

Câu 34. ILM cold hoặc frozen phase thường phục vụ mục tiêu nào?
A. Loại bỏ nhu cầu snapshot và backup định kỳ
B. Tăng tốc ghi cho dữ liệu mới đến liên tục
C. Giảm chi phí cho dữ liệu ít được truy cập
D. Giữ toàn bộ dữ liệu trong bộ nhớ nóng
Đáp án đúng: C

Câu 35. Role-based access control trong Elasticsearch giúp kiểm soát điều gì?
A. Quyền đọc, ghi và quản trị theo vai trò
B. Tốc độ refresh của từng primary shard
C. Số lượng event Logstash nhận mỗi giây
D. Thứ tự field được Kibana hiển thị mặc định
Đáp án đúng: A

Câu 36. TLS giữa Beats hoặc Logstash và Elasticsearch bảo vệ điều gì?
A. Mapping khỏi mọi thay đổi của quản trị viên
B. Replica shard khỏi lỗi phần cứng của node
C. Dữ liệu và thông tin xác thực khi truyền
D. Dữ liệu đã index khỏi mọi thao tác xóa
Đáp án đúng: C

Câu 37. Khi log có password hoặc token, nên xử lý ở bước nào?
A. Loại bỏ hoặc che dữ liệu nhạy cảm trước lưu trữ
B. Đưa bí mật vào tên index để dễ tìm kiếm
C. Thêm bí mật thành tag cho mọi event liên quan
D. Giữ nguyên bí mật rồi chỉ ẩn trên dashboard
Đáp án đúng: A

Câu 38. Vì sao dynamic field tùy ý từ log có thể gây mapping explosion?
A. Nhiều tên field mới làm mapping phình lớn
B. Nhiều replica shard làm Kibana ngừng truy vấn
C. Nhiều pipeline output làm timestamp tự đổi
D. Nhiều document cùng index làm mất inverted index
Đáp án đúng: A

Câu 39. Khi field đã có kiểu dữ liệu sai trong index hiện tại, cách sửa phổ biến là gì?
A. Xóa analyzer rồi refresh index đang có
B. Đổi trực tiếp kiểu field đã tồn tại tại chỗ
C. Tạo index mới với mapping đúng rồi reindex
D. Đổi tên data view để mapping tự cập nhật
Đáp án đúng: C

Câu 40. Index template thường được áp dụng vào thời điểm nào?
A. Khi mỗi document được truy vấn bằng KQL
B. Khi snapshot được phục hồi vào repository
C. Khi một shard replica chuyển thành primary
D. Khi index mới được tạo và khớp pattern
Đáp án đúng: D

Câu 41. Elasticsearch trả HTTP 429 khi ingest tải cao thường báo hiệu điều gì?
A. Index không có mapping cho bất kỳ field nào
B. Node từ chối tạm thời do áp lực tài nguyên
C. Document có JSON sai cú pháp trong request
D. Client thiếu quyền đọc data view trong Kibana
Đáp án đúng: B

Câu 42. Khi Elasticsearch trả lỗi mapping cho một event Logstash, bước xử lý nào phù hợp?
A. Tăng số replica để tự sửa kiểu field sai
B. Xóa toàn bộ pipeline rồi gửi lại mọi event
C. Kiểm tra field và mapping, định tuyến lỗi để xử lý
D. Ẩn lỗi trong Kibana và bỏ qua dữ liệu bị từ chối
Đáp án đúng: C

Câu 43. Khi log đến chậm hơn thời điểm sự kiện, field nào nên giữ timestamp gốc?
A. `_index` thể hiện thời điểm sự kiện đã xảy ra
B. `_routing` thể hiện thời điểm sự kiện đã xảy ra
C. `@timestamp` thể hiện thời điểm sự kiện đã xảy ra
D. `_id` thể hiện thời điểm sự kiện đã xảy ra
Đáp án đúng: C

Câu 44. Filebeat registry lưu thông tin nào để tiếp tục đọc file sau khi khởi động lại?
A. Vị trí đọc của file đã được harvest
B. Danh sách dashboard đang mở trong Kibana
C. Mapping của index nhận log từ file
D. Trạng thái replica của Elasticsearch shard
Đáp án đúng: A
