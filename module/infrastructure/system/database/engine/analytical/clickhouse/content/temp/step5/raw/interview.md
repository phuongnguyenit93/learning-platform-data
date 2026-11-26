Bạn sẽ dựa vào những tiêu chí nào để quyết định dùng ClickHouse cho một hệ thống phân tích dữ liệu thay vì cơ sở dữ liệu giao dịch?
Kiến trúc lưu trữ hướng cột giúp ClickHouse xử lý truy vấn OLAP nhanh hơn lưu trữ hướng hàng như thế nào?
Cách nén dữ liệu theo cột ảnh hưởng ra sao đến dung lượng lưu trữ và tốc độ đọc dữ liệu phân tích?
Bạn sẽ giải thích luồng thực thi một truy vấn phân tích trong ClickHouse từ khi nhận SQL đến khi trả kết quả như thế nào?
Những đặc điểm nào của khối lượng công việc khiến ClickHouse không phải lựa chọn phù hợp cho một bảng nghiệp vụ?
Bạn sẽ xác định chỉ số nào để đo khả năng nạp dữ liệu, độ trễ truy vấn và chi phí của một cụm ClickHouse?
Họ bảng MergeTree giải quyết những bài toán lưu trữ và truy vấn nào trong ClickHouse?
ClickHouse tạo các data part và hợp nhất chúng ở nền như thế nào, và điều gì xảy ra khi số lượng part tăng quá nhanh?
Chỉ mục khóa chính dạng sparse index trong MergeTree hoạt động như thế nào khi lọc dữ liệu?
Bạn phân biệt vai trò của ORDER BY và PRIMARY KEY trong định nghĩa bảng MergeTree như thế nào?
Bạn sẽ chọn khóa sắp xếp cho bảng sự kiện có hàng tỷ bản ghi dựa trên mẫu WHERE và GROUP BY ra sao?
Độ chọn lọc và thứ tự các cột trong khóa sắp xếp ảnh hưởng đến lượng dữ liệu cần quét như thế nào?
Bạn sẽ thiết kế PARTITION BY cho dữ liệu sự kiện theo thời gian như thế nào để cân bằng truy vấn, bảo trì và lưu trữ?
Những vấn đề nào xuất hiện khi một bảng có quá nhiều phân vùng nhỏ và bạn sẽ phát hiện chúng ra sao?
Bạn sẽ lựa chọn giữa phân vùng theo ngày, tháng hoặc một khóa nghiệp vụ dựa trên những yêu cầu nào?
Bạn sẽ sử dụng TTL như thế nào để tự động xóa hoặc di chuyển dữ liệu theo chính sách lưu giữ?
Bạn sẽ tổ chức schema cho bảng ghi nhận lượt xem trang gồm thời gian, người dùng, phiên và thuộc tính sự kiện ra sao?
Bạn sẽ chọn kiểu số nguyên, số thực hoặc Decimal như thế nào để lưu các chỉ số về tiền và phép tính tổng hợp?
Bạn sẽ xử lý múi giờ và độ chính xác thời gian như thế nào khi dùng DateTime và DateTime64?
Kiểu LowCardinality phù hợp với những cột nào và bạn sẽ đánh giá hiệu quả của nó ra sao?
Bạn sẽ quyết định giữa Nullable và giá trị mặc định như thế nào để giữ đúng ngữ nghĩa dữ liệu và hiệu năng?
Bạn sẽ chọn Array, Map, Tuple hoặc Nested cho dữ liệu sự kiện có thuộc tính linh hoạt dựa trên tiêu chí nào?
Bạn sẽ triển khai thay đổi schema khi luồng nạp dữ liệu liên tục hoạt động như thế nào?
Bạn sẽ đánh giá và lựa chọn compression codec cho từng cột dựa trên dữ liệu thực tế ra sao?
Bạn sẽ kiểm chứng rằng cấu hình TTL đáp ứng yêu cầu lưu giữ mà không gây áp lực merge quá mức như thế nào?
ReplacingMergeTree xử lý nhiều phiên bản của cùng một bản ghi như thế nào và các giới hạn nhất quán cần lưu ý là gì?
Bạn sẽ chọn cột phiên bản và khóa sắp xếp cho ReplacingMergeTree như thế nào để tránh giữ bản ghi trùng ngoài ý muốn?
Bạn sẽ thiết kế truy vấn đúng khi các bản ghi trong ReplacingMergeTree chưa được hợp nhất như thế nào?
SummingMergeTree phù hợp với bài toán tổng hợp nào và các trường hợp nào cần tránh dùng nó?
Bạn sẽ dùng AggregatingMergeTree và các trạng thái hàm tổng hợp như thế nào để xây dựng bảng báo cáo nhiều cấp?
Bạn sẽ lựa chọn giữa ghi thêm sự kiện mới và UPDATE/DELETE mutation theo yêu cầu nghiệp vụ ra sao?
Bạn sẽ xử lý việc sửa hoặc xóa dữ liệu theo yêu cầu người dùng mà vẫn kiểm soát tác động đến truy vấn như thế nào?
Bạn sẽ xây dựng cơ chế chống nạp trùng khi một batch bị gửi lại do lỗi mạng như thế nào?
Bạn sẽ nạp dữ liệu từ CSV, JSONEachRow và Parquet như thế nào và chọn định dạng dựa trên yếu tố nào?
Kích thước và tần suất của batch INSERT ảnh hưởng đến số lượng part và thông lượng ghi như thế nào?
Bạn sẽ áp dụng asynchronous insert trong tình huống nào và theo dõi rủi ro mất dữ liệu chưa flush ra sao?
Bạn sẽ thiết kế luồng dữ liệu Kafka vào ClickHouse và kiểm soát lỗi tiêu thụ thông điệp như thế nào?
Bạn sẽ tổ chức checkpoint, retry và tính idempotent cho một pipeline nạp dữ liệu ClickHouse ra sao?
Bạn sẽ kiểm tra chất lượng dữ liệu đầu vào khi trường bắt buộc bị thiếu, sai kiểu hoặc có giá trị bất thường như thế nào?
Bạn sẽ xử lý dữ liệu đến trễ và sự kiện không theo thứ tự thời gian trong báo cáo theo giờ như thế nào?
Bạn sẽ lựa chọn giữa mô hình bảng sự kiện dạng rộng và mô hình fact-dimension dựa trên mẫu truy vấn ra sao?
Những yếu tố nào khiến bạn ưu tiên phi chuẩn hóa dữ liệu thay vì JOIN trong ClickHouse?
Bạn sẽ chọn chiến lược JOIN và phân bổ dữ liệu như thế nào khi bảng fact lớn cần kết hợp bảng dimension?
Bạn sẽ sử dụng dictionary trong ClickHouse cho bài toán tra cứu thuộc tính nào và xử lý dữ liệu dictionary bị cũ ra sao?
Bạn sẽ viết truy vấn tính doanh thu, số đơn và số khách hàng duy nhất theo ngày để tránh đếm sai như thế nào?
Các hàm tổng hợp có điều kiện như sumIf và countIf giúp đơn giản hóa báo cáo phân đoạn như thế nào?
Bạn sẽ cân nhắc giữa uniqExact và các hàm đếm gần đúng khi phân tích người dùng duy nhất ra sao?
Bạn sẽ lựa chọn hàm tính quantile cho báo cáo độ trễ với yêu cầu chính xác và hiệu năng khác nhau như thế nào?
Bạn sẽ dùng window function để tính tăng trưởng, xếp hạng hoặc trung bình trượt trong ClickHouse ra sao?
Bạn sẽ nhóm dữ liệu thành các khoảng thời gian nhất quán cho báo cáo theo giờ, ngày và tuần như thế nào?
Bạn sẽ kiểm tra sai lệch giữa các phép tổng hợp trên dữ liệu chi tiết và dữ liệu đã tổng hợp trước ra sao?
Materialized view trong ClickHouse được kích hoạt bởi dữ liệu đầu vào như thế nào và điều đó ảnh hưởng đến thiết kế pipeline ra sao?
Bạn sẽ tạo materialized view để duy trì số liệu theo phút mà không quét lại toàn bộ bảng nguồn như thế nào?
Bạn sẽ nạp lại dữ liệu lịch sử cho materialized view đang phục vụ dữ liệu mới như thế nào để không đếm trùng?
Bạn sẽ lựa chọn giữa materialized view, bảng tổng hợp do pipeline tự ghi và truy vấn trực tiếp trong trường hợp nào?
Bạn sẽ phối hợp AggregateFunction và các hàm State/Merge khi lưu và truy vấn trạng thái tổng hợp như thế nào?
Bạn sẽ đánh giá khả năng dùng projection để tăng tốc truy vấn so với tạo bảng tổng hợp riêng ra sao?
Data skipping index có thể loại bỏ các vùng dữ liệu không liên quan như thế nào trong một bảng MergeTree?
Bạn sẽ chọn minmax, set hoặc Bloom filter skipping index dựa trên phân bố dữ liệu và biểu thức lọc ra sao?
Bạn sẽ xác định index_granularity phù hợp với kích thước dữ liệu và mẫu truy vấn bằng thực nghiệm như thế nào?
Bạn sẽ sử dụng EXPLAIN để xác định ClickHouse đã loại bỏ phân vùng và granule như kỳ vọng ra sao?
Bạn sẽ khai thác system.query_log và các bảng system để tìm nguyên nhân truy vấn chậm như thế nào?
Bạn sẽ phân biệt truy vấn chậm do đọc quá nhiều cột với truy vấn chậm do lọc không khớp khóa sắp xếp ra sao?
Bạn sẽ tối ưu một truy vấn GROUP BY có cardinality cao và sử dụng nhiều bộ nhớ như thế nào?
Bạn sẽ kiểm soát tràn bộ nhớ khi sắp xếp, JOIN hoặc tổng hợp trên tập dữ liệu lớn ra sao?
Bạn sẽ thay đổi cách tính top N hoặc phân trang trên tập dữ liệu lớn để giảm chi phí truy vấn như thế nào?
Bạn sẽ xác định mức song song và giới hạn tài nguyên truy vấn phù hợp khi có nhiều người dùng đồng thời ra sao?
Bạn sẽ thiết kế kiểm thử hiệu năng với dữ liệu và phân bố truy vấn đại diện cho môi trường thực tế như thế nào?
Bạn sẽ tìm nguyên nhân của hiện tượng too many parts và khôi phục khả năng nạp dữ liệu ổn định ra sao?
Bạn sẽ theo dõi tiến trình merge, kích thước part và dung lượng đĩa để dự đoán nghẽn tài nguyên như thế nào?
Bạn sẽ đánh giá tác động của việc chạy OPTIMIZE hoặc FINAL đối với độ trễ, CPU và I/O như thế nào?
Bạn sẽ quyết định thời điểm tách shard hoặc tăng replica dựa trên tải ghi, tải đọc và nhu cầu sẵn sàng ra sao?
ReplicatedMergeTree phối hợp giữa các replica như thế nào và bạn sẽ xử lý tình huống một replica bị chậm ra sao?
Bạn sẽ chọn sharding key như thế nào để tránh lệch tải và vẫn đáp ứng những truy vấn thường dùng?
Bảng Distributed định tuyến truy vấn và dữ liệu qua nhiều shard như thế nào trong kiến trúc ClickHouse?
Bạn sẽ thiết kế truy vấn tổng hợp trên nhiều shard để kiểm tra độ đúng và chi phí trao đổi dữ liệu ra sao?
Bạn sẽ giải thích các giới hạn nhất quán của bản sao và kết quả truy vấn trong một cụm ClickHouse đang nạp dữ liệu như thế nào?
Bạn sẽ triển khai sao lưu và khôi phục bảng ClickHouse như thế nào để đáp ứng mục tiêu RPO và RTO?
Bạn sẽ kiểm chứng tính toàn vẹn của bản sao lưu và quy trình khôi phục trong một bài diễn tập sự cố ra sao?
Bạn sẽ lập kế hoạch nâng cấp phiên bản ClickHouse với khả năng quay lui và kiểm tra tương thích như thế nào?
Bạn sẽ giám sát những metric và log nào để phát hiện sớm lỗi nạp dữ liệu, truy vấn chậm và áp lực tài nguyên?
Bạn sẽ phân quyền đọc, ghi, quản trị và giới hạn tài nguyên theo nhóm người dùng như thế nào?
Bạn sẽ bảo vệ dữ liệu nhạy cảm khi truy cập, truyền tải và sao lưu trong môi trường ClickHouse ra sao?
Bạn sẽ thiết kế cơ chế cảnh báo khi chênh lệch số liệu giữa nguồn và ClickHouse vượt ngưỡng như thế nào?
Bạn sẽ xác định nguyên nhân một dashboard đột ngột trả về số liệu thấp hơn nguồn trong khi pipeline vẫn chạy như thế nào?
Bạn sẽ xây dựng lộ trình chuyển một hệ thống báo cáo từ cơ sở dữ liệu quan hệ sang ClickHouse với thời gian gián đoạn tối thiểu ra sao?
Bạn sẽ định lượng lợi ích và chi phí của việc tăng số replica, tạo bảng tổng hợp hoặc lưu dữ liệu lâu hơn như thế nào?
Bạn sẽ đề xuất kiến trúc ClickHouse cho hệ thống phân tích sự kiện thời gian gần thực với lượng truy cập tăng đột biến như thế nào?
Nếu một truy vấn chạy nhanh trên dữ liệu thử nhưng chậm trên dữ liệu thật, bạn sẽ thiết kế các bước chẩn đoán và kiểm chứng giả thuyết ra sao?
