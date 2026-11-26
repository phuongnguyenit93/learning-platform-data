Bạn dựa trên những đặc điểm nghiệp vụ và yêu cầu vận hành nào để lựa chọn PostgreSQL làm hệ quản trị cơ sở dữ liệu?
Bạn phân chia schema và đặt tên bảng, cột, khóa, constraint như thế nào để hệ thống dễ mở rộng và bảo trì?
Bạn lựa chọn khóa chính tự nhiên hay khóa thay thế cho từng bảng dựa trên những đánh đổi nào?
Bạn quyết định mức độ chuẩn hóa dữ liệu và thời điểm chấp nhận phi chuẩn hóa dựa trên nhu cầu truy vấn như thế nào?
Bạn mô hình hóa quan hệ một-nhiều và nhiều-nhiều bằng khóa ngoại trong PostgreSQL như thế nào?
Bạn lựa chọn hành vi ON DELETE và ON UPDATE của foreign key như thế nào để bảo toàn dữ liệu nghiệp vụ?
Bạn kết hợp PRIMARY KEY, UNIQUE, CHECK, NOT NULL và FOREIGN KEY để bảo vệ những bất biến dữ liệu nào?
Khi nào bạn chọn UNIQUE constraint, và khi nào cần unique partial index để bảo vệ quy tắc chỉ áp dụng cho một phần dữ liệu?
Bạn chọn integer, bigint, numeric hay kiểu số thực cho các giá trị tiền tệ, định danh và phép tính như thế nào?
Bạn phân biệt timestamp with time zone và timestamp without time zone khi lưu thời điểm sự kiện như thế nào?
Bạn cân nhắc dùng text, varchar, enum, domain và check constraint cho dữ liệu có tập giá trị hữu hạn như thế nào?
Bạn quyết định lưu dữ liệu ở cột quan hệ truyền thống, array hay jsonb dựa trên nhu cầu cập nhật và truy vấn như thế nào?
Bạn xử lý giá trị NULL và logic ba giá trị trong thiết kế ràng buộc và điều kiện truy vấn ra sao?
Bạn dùng identity column, default và generated column trong những trường hợp nào?
Bạn thiết kế quy trình thay đổi schema cho bảng lớn để hạn chế thời gian khóa và rủi ro triển khai như thế nào?
Những tiêu chí nào giúp bạn quyết định có nên phân vùng bảng theo thời gian hoặc khóa nghiệp vụ trong PostgreSQL?
Bạn quản lý khóa phân vùng, tạo phân vùng mới và loại bỏ dữ liệu cũ như thế nào để tránh ảnh hưởng truy vấn?
Bạn viết và kiểm tra JOIN để tránh nhân bản dòng không mong muốn khi kết hợp nhiều bảng như thế nào?
Bạn so sánh EXISTS, IN và JOIN khi diễn đạt điều kiện tồn tại quan hệ dựa trên ngữ nghĩa và hiệu suất như thế nào?
Bạn phân biệt WHERE và HAVING khi lọc dữ liệu trước và sau phép tổng hợp như thế nào?
Bạn dùng window function để xếp hạng, tính tổng lũy kế hoặc lấy bản ghi mới nhất theo nhóm như thế nào?
Bạn lựa chọn CTE, subquery hay view dựa trên khả năng đọc hiểu và kế hoạch thực thi truy vấn như thế nào?
Bạn xây dựng phân trang ổn định bằng OFFSET/LIMIT hoặc keyset pagination theo những yêu cầu nào?
Bạn sử dụng INSERT ... ON CONFLICT và RETURNING để triển khai thao tác ghi lặp lại an toàn như thế nào?
Bạn thiết kế quy trình ghi theo lô và COPY để nhập dữ liệu lớn mà vẫn kiểm soát lỗi và tính nhất quán ra sao?
Bạn truyền tham số và phân quyền tài khoản ứng dụng như thế nào để giảm rủi ro SQL injection?
Bạn giải thích tính nguyên tử, nhất quán, cô lập và bền vững của transaction trong PostgreSQL qua một thao tác nghiệp vụ như thế nào?
Bạn xác định ranh giới transaction và xử lý lỗi khi một yêu cầu cập nhật nhiều bảng như thế nào?
MVCC trong PostgreSQL cho phép reader và writer tương tác với các phiên bản hàng dữ liệu như thế nào?
Snapshot của transaction ảnh hưởng thế nào đến những dòng mà một câu SELECT có thể nhìn thấy?
Bạn phân biệt các mức cô lập Read Committed, Repeatable Read và Serializable của PostgreSQL như thế nào?
Bạn nhận diện và tái hiện các hiện tượng đọc không lặp lại, ghi chồng và bất thường tuần tự hóa trong PostgreSQL ra sao?
Trong trường hợp nào bạn cần mức cô lập Serializable, và bạn thiết kế retry ra sao khi gặp lỗi serialization?
Bạn phân biệt row-level lock, table-level lock và các trạng thái chờ khóa khi nhiều transaction chạy đồng thời như thế nào?
Bạn dùng SELECT ... FOR UPDATE, NOWAIT và SKIP LOCKED để phối hợp các worker xử lý tác vụ như thế nào?
Bạn tìm nguyên nhân deadlock, tái hiện chuỗi khóa và chỉnh lại thứ tự cập nhật để giảm deadlock ra sao?
Những tác động nào xảy ra khi một transaction mở quá lâu dù không chạy truy vấn liên tục?
Bạn lựa chọn advisory lock thay vì khóa hàng dữ liệu trong những tình huống phối hợp nghiệp vụ nào?
Bạn dùng pg_stat_activity và pg_locks ra sao để xác định phiên đang chờ khóa và phiên đang chặn nó?
Bạn giải thích vì sao UPDATE và DELETE có thể tạo phiên bản hàng cũ cần được dọn dẹp trong mô hình MVCC như thế nào?
VACUUM thường và autovacuum duy trì khả năng tái sử dụng không gian và hiệu suất bảng như thế nào?
Bạn phát hiện và đánh giá table bloat hoặc index bloat trước khi quyết định biện pháp xử lý ra sao?
Khi autovacuum không theo kịp tốc độ cập nhật, bạn đánh giá ngưỡng kích hoạt, worker và chi phí I/O như thế nào?
Bạn phân biệt VACUUM, VACUUM FULL và REINDEX về lợi ích, chi phí và mức độ khóa như thế nào?
Vì sao việc đóng băng transaction ID và ngăn transaction ID wraparound lại quan trọng đối với PostgreSQL?
Bạn dùng ANALYZE và thống kê dữ liệu để giúp planner ước lượng số dòng chính xác hơn như thế nào?
UPDATE có thể sử dụng HOT update trong những điều kiện nào và điều đó liên quan thế nào đến index và fillfactor?
Những đặc điểm của điều kiện lọc, phép so sánh và sắp xếp nào khiến bạn chọn B-tree index?
Thứ tự cột trong composite index ảnh hưởng ra sao đến các mẫu truy vấn phổ biến của ứng dụng?
Bạn sử dụng covering index với INCLUDE và index-only scan để giảm truy cập heap trong trường hợp nào?
Bạn lựa chọn partial index hoặc expression index để tăng tốc một mẫu truy vấn cụ thể như thế nào?
Bạn so sánh B-tree, GIN, GiST và BRIN khi lập chỉ mục cho dữ liệu thông thường, jsonb, tìm kiếm và bảng rất lớn như thế nào?
Bạn cân bằng tốc độ đọc với chi phí ghi và không gian lưu trữ khi thêm hoặc xóa index như thế nào?
Bạn đọc các phần quan trọng của EXPLAIN để giải thích vì sao planner chọn sequential scan, index scan hoặc join cụ thể như thế nào?
EXPLAIN ANALYZE và BUFFERS giúp bạn so sánh ước lượng với thực tế và xác định chi phí I/O như thế nào?
Khi kế hoạch truy vấn ước lượng sai cardinality, bạn kiểm tra phân bố dữ liệu và các thống kê liên quan ra sao?
Bạn chẩn đoán tình huống sort hoặc hash operation tràn ra đĩa và đánh giá work_mem như thế nào?
Bạn phân tích tác động của nested loop, hash join và merge join lên thời gian xử lý ở các quy mô dữ liệu khác nhau như thế nào?
Bạn đánh giá việc chạy song song truy vấn hoặc thay đổi cấu hình planner dựa trên kết quả đo nào?
Bạn sử dụng pg_stat_statements và các chỉ số thời gian thực thi để xác định truy vấn gây tải lớn như thế nào?
Khi cùng một truy vấn đôi lúc nhanh và đôi lúc chậm, bạn kiểm tra parameter, plan cache, khóa và cache dữ liệu ra sao?
Bạn tổ chức thử nghiệm truy vấn trên dữ liệu đại diện để tránh kết luận sai khi dữ liệu production khác môi trường phát triển như thế nào?
WAL ghi nhận những thay đổi nào và hỗ trợ bảo đảm độ bền của transaction cùng khả năng phục hồi ra sao?
Bạn phân biệt vai trò của WAL, dữ liệu đã ghi xuống data file và checkpoint trong quá trình khôi phục sau crash như thế nào?
Bạn cân nhắc cấu hình synchronous_commit và fsync theo yêu cầu độ bền dữ liệu cùng rủi ro vận hành như thế nào?
Checkpoint quá thường xuyên hoặc quá thưa có thể tác động thế nào đến I/O, WAL và thời gian khôi phục?
Bạn xác định nguyên nhân WAL tăng bất thường và những yếu tố khiến dung lượng WAL không được giải phóng ra sao?
Bạn xây dựng kế hoạch lưu trữ WAL và archive để hỗ trợ khôi phục dữ liệu tới một thời điểm cụ thể như thế nào?
Bạn lựa chọn giữa pg_dump/pg_restore và sao lưu vật lý dựa trên kích thước dữ liệu, mục tiêu RPO và RTO như thế nào?
Bạn kiểm tra tính nhất quán của backup và thực hành restore định kỳ để xác nhận khả năng phục hồi như thế nào?
Bạn thực hiện Point-in-Time Recovery khi một thao tác xóa nhầm dữ liệu đã được commit theo quy trình nào?
Bạn quản lý lịch sử sao lưu, quyền truy cập, mã hóa và thời hạn lưu giữ để hạn chế rủi ro mất dữ liệu như thế nào?
Streaming replication trong PostgreSQL truyền thay đổi từ primary sang standby thông qua WAL như thế nào?
Bạn lựa chọn replication đồng bộ hay bất đồng bộ dựa trên yêu cầu độ trễ, tính sẵn sàng và khả năng mất dữ liệu như thế nào?
Bạn phân tích replication lag và tác động của nó đến kết quả đọc từ standby như thế nào?
Replication slot giúp theo dõi tiến độ tiêu thụ WAL như thế nào và có thể gây rủi ro dung lượng ra sao?
Bạn so sánh physical replication và logical replication để chọn cách nhân bản hoặc di chuyển một phần dữ liệu như thế nào?
Bạn thiết kế quy trình failover, promote standby và ngăn split-brain cho hệ thống PostgreSQL như thế nào?
Bạn đánh giá sự thay đổi timeline và cách đưa replica cũ trở lại sau failover như thế nào?
Bạn dùng pg_stat_replication và các chỉ số WAL để giám sát trạng thái primary và standby như thế nào?
Bạn sử dụng pg_stat_activity để phân biệt kết nối nhàn rỗi, truy vấn đang chạy và transaction nhàn rỗi nhưng chưa kết thúc như thế nào?
Bạn phối hợp giới hạn max_connections với connection pool của ứng dụng để tránh cạn tài nguyên như thế nào?
Bạn đánh giá shared_buffers, work_mem và memory cho các phiên đồng thời để tránh tình trạng sử dụng quá mức RAM như thế nào?
Bạn phân biệt sự cố do CPU, I/O lưu trữ, mạng, khóa hoặc truy vấn kém bằng các metric và log nào?
Bạn xây dựng cảnh báo cho lỗi kết nối, transaction lâu, autovacuum, WAL, dung lượng đĩa và replication lag như thế nào?
Bạn tổ chức role, quyền trên schema và bảng theo nguyên tắc tối thiểu đặc quyền trong PostgreSQL như thế nào?
Bạn kết hợp pg_hba.conf, TLS và chính sách xác thực để kiểm soát kết nối tới PostgreSQL như thế nào?
Row-level security hỗ trợ kiểm soát truy cập dữ liệu theo người dùng hoặc tenant như thế nào, và bạn kiểm tra chính sách đó ra sao?
Bạn đánh giá tương thích extension và triển khai nâng cấp phiên bản PostgreSQL với phương án kiểm thử và rollback như thế nào?
Khi một migration khiến transaction bị chờ khóa và dịch vụ tăng độ trễ, bạn điều tra và xử lý sự cố theo thứ tự nào?
Bạn thiết kế bài kiểm thử tải và khôi phục nào để chứng minh PostgreSQL đáp ứng các mục tiêu hiệu suất, RPO và RTO trước khi đưa vào production?
