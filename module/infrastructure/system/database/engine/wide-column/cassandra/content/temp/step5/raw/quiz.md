Câu 1. Trong kiến trúc Cassandra, node nào có thể đóng vai trò coordinator khi nhận request?
A. Node nhận request có thể đảm nhận vai trò coordinator.
B. Chỉ seed node được làm coordinator cho mọi request.
C. Chỉ node giữ toàn bộ dữ liệu mới làm coordinator.
D. Chỉ node đầu tiên của mỗi rack được nhận request.
Đáp án đúng: A

Câu 2. Yếu tố nào chủ yếu quyết định vị trí token của một partition trong Cassandra?
A. Giá trị của clustering key trên bản ghi được chọn.
B. Thời điểm tạo keyspace và tên đầu tiên của bảng.
C. Kích thước của các cột không thuộc primary key.
D. Token được tính qua hash của partition key.
Đáp án đúng: D

Câu 3. Mục đích của virtual nodes (vnodes) trong Cassandra là gì?
A. Buộc một node chỉ được sở hữu một partition dữ liệu.
B. Sao chép mọi partition tới mọi node dù RF nhỏ hơn.
C. Tự mở thêm datacenter khi phân vùng đầy dữ liệu.
D. Một node có thể nắm nhiều khoảng token trên vòng.
Đáp án đúng: D

Câu 4. Trong cluster nhiều datacenter, snitch giúp Cassandra làm gì?
A. Chọn replica dựa trên thông tin datacenter và rack.
B. Tính giá trị TTL cho từng cột được ghi vào bảng.
C. Điều chỉnh RF trực tiếp mà không cần sửa keyspace.
D. Tự xác định unique constraint cho mỗi partition key.
Đáp án đúng: A

Câu 5. Partition key và clustering key trong Cassandra khác nhau ở điểm nào?
A. Partition key sắp xếp hàng; clustering chọn replica lưu.
B. Partition key xác định TTL; clustering xác định RF.
C. Partition key phân phối, clustering sắp xếp hàng.
D. Cả hai chỉ tham gia thứ tự cột trong câu INSERT.
Đáp án đúng: C

Câu 6. Với `PRIMARY KEY ((tenant_id, day_bucket), ts)`, partition key là gì?
A. Chỉ cột `tenant_id`, còn `day_bucket` là clustering.
B. Chỉ cột `ts`, còn cặp cột đầu là clustering.
C. Partition key gồm `tenant_id` và `day_bucket`.
D. Cả ba cột đều thuộc cùng một composite partition key.
Đáp án đúng: C

Câu 7. Với bảng `PRIMARY KEY (user_id, event_time)`, cách lọc nào phù hợp với khóa?
A. Lọc riêng `event_time` rồi ORDER BY toàn cluster.
B. Lọc `user_id` rồi giới hạn khoảng `event_time`.
C. Lọc riêng `event_time` không cần biết partition.
D. Lọc bảng bất kỳ theo `user_id` bằng JOIN tự động.
Đáp án đúng: B

Câu 8. Vì sao Cassandra thường thiết kế bảng theo truy vấn ứng dụng?
A. Mọi truy vấn phức tạp đều được tối ưu bằng JOIN.
B. Mô hình chuẩn hóa 3NF luôn mang lại đọc nhanh nhất.
C. Mỗi đường truy vấn có thể cần bảng dữ liệu lặp riêng.
D. Mọi entity đều phải nằm trong một bảng duy nhất.
Đáp án đúng: C

Câu 9. Cách nào thường giúp phân tán tải khi một partition nhận quá nhiều ghi?
A. Thêm bucket vào partition key và phân phối dữ liệu.
B. Chỉ tăng RF mà giữ nguyên partition key đang nóng.
C. Chỉ thêm clustering key vào partition vốn đã nóng.
D. Chỉ giảm cỡ trang của CQL SELECT đang thực thi.
Đáp án đúng: A

Câu 10. Vấn đề phổ biến của partition quá lớn trong Cassandra là gì?
A. Nhiều partition tự động bị JOIN trên một coordinator.
B. Replica sẽ không thể nhận bất kỳ bản ghi mới nào.
C. Partition lớn có thể làm chậm đọc và compaction.
D. Clustering key bị đổi thành partition key ngẫu nhiên.
Đáp án đúng: C

Câu 11. Khi Cassandra không hỗ trợ JOIN tổng quát như RDBMS, thiết kế nào thích hợp?
A. Tạo foreign key để driver tự động thực hiện JOIN.
B. Dùng `GROUP BY` nối các bảng theo partition key.
C. Dùng `ORDER BY` ghép các bảng khác keyspace.
D. Tạo các bảng riêng cho nhu cầu tra cứu trong app.
Đáp án đúng: D

Câu 12. Vì sao cần cân nhắc trước khi dùng `ALLOW FILTERING` trong CQL?
A. Luôn bảo đảm chỉ truy cập đúng một partition cụ thể.
B. Tự động tạo chỉ mục mới cho mỗi predicate sử dụng.
C. Có thể quét thêm dữ liệu rồi mới lọc ra kết quả.
D. Luôn xử lý câu truy vấn ở replica gần client nhất.
Đáp án đúng: C

Câu 13. Với khóa clustering `ts`, `ORDER BY ts DESC` trong CQL thường có phạm vi nào?
A. Chỉ sắp xếp bản ghi theo `ts` trong từng partition.
B. Sắp xếp tất cả partition trên cluster theo token.
C. Sắp xếp các node vật lý theo địa chỉ mạng tăng dần.
D. Sắp xếp mọi keyspace thành một kết quả toàn cluster.
Đáp án đúng: A

Câu 14. Nếu CQL `INSERT` dùng primary key đã tồn tại, kết quả cơ bản là gì?
A. Luôn báo lỗi trùng khóa như unique constraint SQL.
B. Luôn tạo hàng mới bên cạnh hàng có primary key cũ.
C. Luôn khóa tất cả replica để chạy transaction SQL.
D. Ghi đè các cột được chỉ định theo khóa của hàng.
Đáp án đúng: D

Câu 15. `USING TTL 3600` trong câu ghi CQL biểu thị điều gì?
A. Thời gian đợi coordinator phản hồi tối đa 3600 giây.
B. Dữ liệu sẽ được nhân thành 3600 bản sao ở replica.
C. Kết nối client sẽ tự đóng sau khoảng 3600 giây.
D. Dữ liệu được ghi hết hạn sau khoảng 3600 giây.
Đáp án đúng: D

Câu 16. Khi cần `INSERT ... IF NOT EXISTS` thực sự có điều kiện, Cassandra dùng cơ chế nào?
A. Dùng LWT qua đồng thuận, có thêm độ trễ.
B. Ghi thường với consistency ONE và không kiểm tra.
C. Dùng `ALLOW FILTERING` để khóa partition trước ghi.
D. Tăng RF để đảm bảo mọi INSERT đều không bị trùng.
Đáp án đúng: A

Câu 17. Replication factor trong Cassandra mô tả thông tin gì?
A. Số bản sao mỗi partition theo cấu hình keyspace.
B. Số connection mỗi client giữ đến các node replica.
C. Số lần retry được phép khi truy vấn vượt timeout.
D. Số hàng tối đa được ghi trong một lần batch.
Đáp án đúng: A

Câu 18. Với nhiều datacenter, `NetworkTopologyStrategy` cho phép cấu hình gì?
A. Một partition key riêng cho từng truy vấn vào cluster.
B. Độ dài TTL riêng cho từng rack của mỗi datacenter.
C. Cho phép khai báo RF riêng cho từng datacenter.
D. Clustering order riêng cho những node đang offline.
Đáp án đúng: C

Câu 19. Với RF bằng 3, `QUORUM` đòi tối thiểu bao nhiêu replica xác nhận?
A. Chỉ một replica của partition phản hồi thành công.
B. Cần hai replica xác nhận request đã thành công.
C. Cả ba replica của partition phải phản hồi thành công.
D. Mọi node trong toàn cluster phải phản hồi thành công.
Đáp án đúng: B

Câu 20. Trong Cassandra nhiều DC, `LOCAL_QUORUM` yêu cầu điều gì?
A. Đa số replica tính trên tất cả datacenter cùng lúc.
B. Chờ đa số replica tại datacenter cục bộ phản hồi.
C. Đúng một replica trong từng datacenter phản hồi.
D. Toàn bộ replica của partition trên mọi datacenter.
Đáp án đúng: B

Câu 21. Hệ quả cần cân nhắc khi đọc với consistency `ONE` là gì?
A. Đảm bảo phải đợi đa số replica trước khi trả dữ liệu.
B. Chặn mọi writer để bản đọc luôn là snapshot mới.
C. Tự dùng lightweight transaction cho từng lệnh SELECT.
D. Trả nhanh hơn nhưng có nguy cơ đọc replica còn cũ.
Đáp án đúng: D

Câu 22. Lỗi `Unavailable` khi truy vấn Cassandra thường biểu thị điều gì?
A. Đủ replica nhưng tất cả phản hồi chậm hơn timeout.
B. Câu `IF NOT EXISTS` thất bại khi hàng đã tồn tại.
C. Không đủ replica sống đáp ứng consistency yêu cầu.
D. Java Driver nhận một cột thiếu trong bản ghi trả về.
Đáp án đúng: C

Câu 23. Lỗi `ReadTimeout` trong Cassandra thường xuất hiện trong tình huống nào?
A. Không có đủ replica đang sống ngay khi nhận yêu cầu.
B. Không nhận kịp số phản hồi cần thiết cho lần đọc.
C. Truy vấn thiếu partition key nên bị lỗi cú pháp.
D. Câu `IF` của một lightweight transaction là sai.
Đáp án đúng: B

Câu 24. Cơ chế gossip của Cassandra chủ yếu phục vụ việc gì?
A. Đồng bộ toàn bộ SSTable của mọi replica theo lịch.
B. Lan truyền thông tin trạng thái node trong cluster.
C. Thay thế compaction để loại bỏ tombstone trên node.
D. Tự động tạo prepared statement từ query log.
Đáp án đúng: B

Câu 25. Hinted handoff trong Cassandra chủ yếu xử lý tình huống nào?
A. Thay thế hoàn toàn repair cho mọi replica lệch dữ liệu.
B. Chặn mọi client ghi cho đến khi replica lỗi trở lại.
C. Giữ tạm ghi bị lỡ và chuyển lại khi replica hồi phục.
D. Khôi phục snapshot toàn bộ keyspace sau khi node lỗi.
Đáp án đúng: C

Câu 26. Đường ghi cơ bản của Cassandra đi qua những cấu phần nào?
A. Chỉ ghi trực tiếp SSTable, không cần log hay memtable.
B. Chỉ ghi secondary index rồi tạo bản sao từ index.
C. Ghi commit log và memtable, sau đó flush ra SSTable.
D. Ghi toàn bộ vào cache client trước khi nhận ở node.
Đáp án đúng: C

Câu 27. Tính chất quan trọng của SSTable trong Cassandra là gì?
A. SSTable bất biến; thay đổi được ghi thành file mới.
B. SSTable được sửa tại chỗ mỗi khi giá trị cột thay đổi.
C. SSTable tự chuyển thành memtable khi query có WHERE.
D. SSTable được xóa ngay khi một hàng có tombstone.
Đáp án đúng: A

Câu 28. Compaction của Cassandra có nhiệm vụ chính nào?
A. Hợp nhất SSTable và dọn bản cũ khi điều kiện cho phép.
B. Tăng RF rồi gửi toàn bộ dữ liệu sang datacenter khác.
C. Tạo schema mới khi phát hiện cột xuất hiện trong hàng.
D. Thực thi lightweight transaction mà không cần network.
Đáp án đúng: A

Câu 29. Chiến lược TimeWindowCompactionStrategy thường hợp với dạng dữ liệu nào?
A. Bảng cập nhật dữ liệu lịch sử tùy ý ở mọi thời điểm.
B. Bảng luôn thay đổi nhiều cột cùng khóa giữa các cửa sổ.
C. Chuỗi thời gian ghi tuần tự, có vòng đời dữ liệu tương tự.
D. Bảng dùng transaction nhiều partition thay cho time series.
Đáp án đúng: C

Câu 30. Vì sao nhiều tombstone có thể gây sự cố truy vấn Cassandra?
A. Tombstone tự được loại bỏ ngay tại lúc DELETE commit.
B. Đọc phải xử lý nhiều dấu xóa, tăng độ trễ và timeout.
C. Tombstone không phát sinh khi TTL của ô đã hết hạn.
D. Tombstone tự tạo index nên luôn làm SELECT nhanh hơn.
Đáp án đúng: B

Câu 31. `gc_grace_seconds` cần được phối hợp với repair vì lý do nào?
A. Giữ tombstone đủ lâu để tránh dữ liệu bị hồi sinh.
B. Cho phép giảm về 0 mà không cần đồng bộ các replica.
C. Tự chuyển mọi tombstone thành giá trị NULL ngay tức thì.
D. Buộc compaction xóa mọi dấu xóa dù node chưa đồng bộ.
Đáp án đúng: A

Câu 32. `nodetool repair` thường được dùng để thực hiện nhiệm vụ gì?
A. Tạo index trên tất cả cột thiếu partition key.
B. So sánh và sửa dữ liệu chênh lệch giữa replica.
C. Tự tăng RF và phân lại token mà không sửa cấu hình.
D. Xóa mọi tombstone ngay cả khi node còn offline.
Đáp án đúng: B

Câu 33. `nodetool status` giúp kỹ sư vận hành kiểm tra điều gì?
A. Chi tiết truy vấn CQL hiện được Java Driver bind.
B. Tốc độ mạng của từng thread trong ứng dụng Java.
C. Nội dung backup snapshot của mỗi SSTable đã lưu.
D. Xem node đang Up/Down và giai đoạn hoạt động.
Đáp án đúng: D

Câu 34. `nodetool compactionstats` phù hợp để quan sát điều gì?
A. Quyền `GRANT` của từng tài khoản trên các keyspace.
B. Compaction đang chạy cùng số tác vụ còn chờ xử lý.
C. Các hàng đang bị khóa bởi transaction SQL dài.
D. Danh sách prepared statement trong mỗi Java session.
Đáp án đúng: B

Câu 35. Snapshot của Cassandra chủ yếu hữu ích trong việc nào?
A. Chụp SSTable để dùng trong backup và restore.
B. Tự tạo replica online để thay thế quá trình repair.
C. Giữ một transaction phân tán khóa mọi ghi client.
D. Xóa hết tombstone bằng compaction trên toàn cluster.
Đáp án đúng: A

Câu 36. Khi latency p99 tăng cùng số timeout, nhóm tín hiệu nào nên đối chiếu?
A. Chỉ thông lượng trung bình mà bỏ qua các lỗi đã đếm.
B. Chỉ số bảng và số keyspace, không xem tốc độ truy vấn.
C. Chỉ phiên bản Java mà không đo áp lực phía server.
D. Xem p99, timeout, compaction backlog và tải node.
Đáp án đúng: D

Câu 37. Trong Java Driver Cassandra, `CqlSession` nên được quản lý ra sao?
A. Tạo mới sau mỗi row để tránh dùng lại cùng connection.
B. Tái sử dụng theo vòng đời ứng dụng rồi đóng khi dừng.
C. Chỉ mở sau khi câu CQL đã chạy hoàn thành ở server.
D. Dùng chung một `Row` để thay cho mọi `CqlSession`.
Đáp án đúng: B

Câu 38. Lợi ích của prepared statement và bind trong Cassandra Java Driver là gì?
A. Thay đổi tự động partition key của mọi bảng đã tạo.
B. Tái sử dụng CQL và truyền giá trị dưới dạng tham số.
C. Bỏ qua kiểm tra consistency khi bind giá trị truy vấn.
D. Tự sửa RF của keyspace sau lần prepare đầu tiên.
Đáp án đúng: B

Câu 39. Khi gọi `executeAsync()` qua Java Driver, ứng dụng nhận được khả năng gì?
A. Buộc toàn bộ replica thực thi truy vấn trên một thread.
B. Tự chuyển mọi SELECT thành lightweight transaction.
C. Buộc kết quả toàn cluster được tải vào RAM trước khi trả.
D. Nhận kết quả qua API bất đồng bộ, không chặn thread gọi.
Đáp án đúng: D

Câu 40. Khi đọc nhiều hàng bằng Java Driver, phân trang kết quả giúp điều gì?
A. Tự phân tán partition nóng sang những token mới.
B. Tạo index trên mọi cột của bảng trước khi SELECT.
C. Làm tất cả SELECT có consistency SERIAL tự động.
D. Chia kết quả thành trang để giảm tải bộ nhớ.
Đáp án đúng: D
