Câu 1. Đặc trưng nào khiến ClickHouse phù hợp với truy vấn OLAP?
A. Cập nhật liên tục nhiều bản ghi đơn lẻ
B. Khóa từng bản ghi trong giao dịch dài
C. Xác thực tuần tự từng giao dịch ghi
D. Quét và tổng hợp dữ liệu theo cột
Đáp án đúng: D

Câu 2. Lưu trữ hướng cột giảm I/O trong truy vấn tổng hợp bằng cách nào?
A. Tạo khóa dòng riêng cho mọi điều kiện lọc
B. Chỉ đọc những cột được truy vấn sử dụng
C. Đọc nguyên bản ghi cho từng hàng dữ liệu
D. Đặt tất cả cột vào cùng trang dữ liệu
Đáp án đúng: B

Câu 3. Bảng chứa event được ghi nối tiếp và phân tích theo thời gian nên ưu tiên engine nào?
A. MergeTree để lưu và truy vấn sự kiện
B. Log để sắp xếp sự kiện theo khóa
C. Join để lưu sự kiện phân vùng
D. Memory để lưu sự kiện lâu dài
Đáp án đúng: A

Câu 4. Trong bảng MergeTree, ORDER BY (user_id, ts) chủ yếu điều khiển điều gì?
A. Quy tắc chia dữ liệu ra các shard mạng
B. Ràng buộc duy nhất trên các bản ghi
C. Thứ tự lưu các hàng trong từng part
D. Tần suất sao chép part sang replica
Đáp án đúng: C

Câu 5. PARTITION BY toYYYYMM(event_date) tạo phân vùng theo kỳ nào?
A. Mỗi ngày tạo một giá trị phân vùng
B. Mỗi tháng là một giá trị phân vùng
C. Mỗi năm tạo một giá trị phân vùng
D. Mỗi giờ tạo một giá trị phân vùng
Đáp án đúng: B

Câu 6. PRIMARY KEY của bảng MergeTree thường dùng để làm gì?
A. Bỏ qua granule nhờ sparse index
B. Đồng bộ transaction trên mọi replica
C. Bảo đảm mọi bản ghi có khóa duy nhất
D. Phân phối dữ liệu đồng đều giữa shard
Đáp án đúng: A

Câu 7. Khi nạp hàng triệu event, cách nào hạn chế tạo quá nhiều part nhỏ?
A. Chia từng batch vào nhiều partition nhỏ
B. Gọi OPTIMIZE FINAL sau mọi INSERT
C. Gộp bản ghi thành các batch INSERT lớn
D. Thực hiện một INSERT cho từng bản ghi
Đáp án đúng: C

Câu 8. Background merge của MergeTree thường thực hiện điều gì?
A. Hợp nhất các part để giảm phân mảnh
B. Viết đè từng hàng ngay khi có UPDATE
C. Chuyển mọi bảng sang định dạng hàng
D. Tự tạo replica cho mỗi part mới
Đáp án đúng: A

Câu 9. Với ReplacingMergeTree, khi nào bản ghi cùng sorting key có thể được gộp?
A. Trong merge nền hoặc khi đọc với FINAL
B. Ngay trước mọi INSERT bằng unique index
C. Khi hệ thống chạy SELECT không FINAL
D. Chỉ lúc thực hiện BACKUP bảng
Đáp án đúng: A

Câu 10. Vì sao PARTITION BY user_id với hàng triệu giá trị thường bất lợi?
A. Buộc mọi dữ liệu vào một shard
B. Tăng số partition và part nhỏ
C. Ngăn mọi truy vấn dùng ORDER BY
D. Vô hiệu mọi hàm tổng hợp SQL
Đáp án đúng: B

Câu 11. Bảng ORDER BY (tenant_id, event_time) thường tận dụng thứ tự tốt nhất với truy vấn nào?
A. Chỉ lọc giá trị source bất kỳ
B. Chỉ lọc giá trị status bất kỳ
C. Chỉ lọc giá trị amount bất kỳ
D. Lọc tenant_id và khoảng event_time
Đáp án đúng: D

Câu 12. Khi chỉ lọc event_time trên ORDER BY (tenant_id, event_time), vấn đề nào dễ gặp?
A. Phân vùng tự biến thành partition theo giờ
B. Khóa sắp xếp bị chuyển thành khóa duy nhất
C. ClickHouse tự tạo thêm index theo thời gian
D. Khó bỏ qua granule vì thiếu lọc tenant_id
Đáp án đúng: D

Câu 13. Trong ClickHouse, PREWHERE hữu ích nhất để làm gì?
A. Đọc sớm cột lọc để giảm I/O
B. Sắp xếp các part trước khi chạy SELECT
C. Ghi lại mọi bản ghi trước khi lọc WHERE
D. Gộp các replica trước khi tính GROUP BY
Đáp án đúng: A

Câu 14. Primary index dạng sparse của MergeTree chỉ trực tiếp tới đơn vị nào?
A. Từng truy vấn SQL trong query log
B. Từng hàng của mọi part chưa sắp xếp
C. Các mốc granule trong dữ liệu đã sắp xếp
D. Từng shard trong cả cụm phân tán
Đáp án đúng: C

Câu 15. Data-skipping index được dùng để làm gì?
A. Thay toàn bộ ORDER BY bằng hash index
B. Tự động phân phối bảng sang nhiều nút
C. Áp ràng buộc UNIQUE lên cột được chọn
D. Bỏ qua block có metadata loại trừ điều kiện lọc
Đáp án đúng: D

Câu 16. Muốn tính tổng doanh thu chỉ cho status='paid', biểu thức nào đúng?
A. `sum(amount, status = 'paid')`
B. `sumIf(amount, status = 'paid')`
C. `sumIf(status = 'paid', amount)`
D. `sumWhere(amount, status = 'paid')`
Đáp án đúng: B

Câu 17. Lọc nhóm có SUM(amount) > 1000 sau GROUP BY dùng mệnh đề nào?
A. `HAVING sum(amount) > 1000`
B. `WHERE sum(amount) > 1000`
C. `PREWHERE sum(amount) > 1000`
D. `ORDER BY sum(amount) > 1000`
Đáp án đúng: A

Câu 18. Cần đếm user_id khác nhau một cách chính xác, nên chọn hàm nào?
A. Dùng `uniqHLL12` để đếm chính xác
B. Dùng `uniq` để đếm chính xác
C. Dùng `uniqExact` để đếm chính xác
D. Dùng `uniqCombined` để đếm chính xác
Đáp án đúng: C

Câu 19. Muốn GROUP BY mỗi giờ từ event_time, hàm nào phù hợp?
A. `toStartOfHour(event_time)`
B. `toStartOfWeek(event_time)`
C. `toStartOfMonth(event_time)`
D. `toStartOfDay(event_time)`
Đáp án đúng: A

Câu 20. Materialized view thông thường cập nhật từ bảng nguồn vào lúc nào?
A. Khi người dùng SELECT trực tiếp bảng nguồn
B. Khi mọi part cũ hoàn tất backup định kỳ
C. Khi cluster chủ động cân bằng các shard
D. Khi dữ liệu được INSERT vào bảng nguồn
Đáp án đúng: D

Câu 21. Materialized view vào AggregatingMergeTree nên kết hợp hàm nào?
A. `sum` khi ghi và `sumIf` khi đọc
B. `sumState` khi ghi và `sumMerge` khi đọc
C. `count` khi ghi và `countIf` khi đọc
D. `avg` khi ghi và `avgIf` khi đọc
Đáp án đúng: B

Câu 22. SummingMergeTree có tính chất nào khi merge hàng cùng sorting key?
A. Lưu từng trạng thái aggregate chưa gộp
B. Đếm chính xác giá trị string khác nhau
C. Giữ bản ghi mới nhất theo cột version
D. Cộng các cột số được cấu hình để gộp
Đáp án đúng: D

Câu 23. Câu SQL nào hợp lý để chuyển dữ liệu từ staging sang fact_events?
A. `INSERT INTO fact_events SELECT ... FROM staging`
B. `DELETE FROM fact_events SELECT ... FROM staging`
C. `CREATE fact_events SELECT ... FROM staging`
D. `UPDATE fact_events SELECT ... FROM staging`
Đáp án đúng: A

Câu 24. Dạng input nào phù hợp để nạp mỗi object JSON trên một dòng?
A. `JSONCompactEachRow` cho object JSON từng dòng
B. `JSONColumns` cho object JSON từng dòng
C. `JSONEachRow` cho object JSON từng dòng
D. `JSON` cho object JSON từng dòng
Đáp án đúng: C

Câu 25. Dữ liệu đến thành nhiều INSERT rất nhỏ; cơ chế nào giúp gom trước khi ghi?
A. Bật FINAL cho mọi truy vấn đọc bảng
B. Bật optimize_on_insert để tạo shard
C. Bật async_insert để gom lệnh ghi
D. Bật JOIN cho mỗi thao tác INSERT
Đáp án đúng: C

Câu 26. LowCardinality(String) thường hiệu quả nhất cho loại cột nào?
A. Cột payload JSON hầu như luôn khác nhau
B. Cột chuỗi lặp nhiều giá trị như country
C. Cột UUID gần như mỗi dòng một giá trị
D. Cột timestamp tăng liên tục từng mili giây
Đáp án đúng: B

Câu 27. TTL trên MergeTree có thể xử lý dữ liệu cũ ra sao?
A. Tự động thêm khóa duy nhất theo thời gian
B. Tự động thay mọi SQL bằng phép tổng hợp
C. Tự động tạo bản sao mới cho mỗi truy vấn
D. Tự động xóa hoặc chuyển dữ liệu khi đủ tuổi
Đáp án đúng: D

Câu 28. Khi khai báo CODEC(ZSTD) cho cột, đánh đổi chính là gì?
A. Giảm số shard nhưng tăng khóa giao dịch
B. Tăng tính duy nhất nhưng giảm tốc độ JOIN
C. Giảm số partition nhưng tăng phí replication
D. Tiết kiệm dung lượng nhưng tốn CPU nén và giải nén
Đáp án đúng: D

Câu 29. Muốn tìm bảng có nhiều active parts, nên kiểm tra nguồn nào?
A. Bảng hệ thống `system.users`
B. Bảng hệ thống `system.parts`
C. Bảng hệ thống `system.roles`
D. Bảng hệ thống `system.settings`
Đáp án đúng: B

Câu 30. Nguồn nào hữu ích để phân tích thời gian và số hàng đọc của truy vấn?
A. `system.columns` sau khi log được ghi
B. `system.clusters` sau khi log được ghi
C. `system.tables` sau khi log được ghi
D. `system.query_log` sau khi log được ghi
Đáp án đúng: D

Câu 31. Trước khi tối ưu truy vấn, cách nào xem việc dùng index?
A. Chạy `SYSTEM FLUSH LOGS` trên truy vấn
B. Chạy `BACKUP TABLE` trên truy vấn
C. Chạy `EXPLAIN indexes = 1` trên truy vấn
D. Chạy `OPTIMIZE TABLE FINAL` trên truy vấn
Đáp án đúng: C

Câu 32. ReplicatedMergeTree phối hợp ClickHouse Keeper để làm gì?
A. Thực hiện khóa giao dịch trên từng row
B. Phối hợp sao chép part giữa replica
C. Tự động chọn khóa sắp xếp cho bảng
D. Tự động chia bảng thành các shard mới
Đáp án đúng: B

Câu 33. Đối với bảng Distributed, vai trò chính là gì?
A. Nén mỗi cột của bảng theo mã hóa ZSTD
B. Định tuyến truy vấn qua các shard cấu hình
C. Lưu tất cả part trên một nút duy nhất
D. Xác thực khóa duy nhất cho mỗi hàng
Đáp án đúng: B

Câu 34. Khi chọn sharding key cho event lớn, ưu tiên điều gì?
A. Phân bố tải đều và ổn định theo khóa
B. Bảo đảm sort key luôn bằng shard key
C. Tạo nhiều partition nhất trên một nút
D. Dồn mọi event mới vào shard đầu tiên
Đáp án đúng: A

Câu 35. Để có thể khôi phục sau lỗi mất dữ liệu, cần chuẩn bị gì?
A. Chỉ tăng số partition để tránh mất dữ liệu
B. Chỉ bật optimize_on_insert khi ghi bảng
C. Backup định kỳ và thử restore từ bản sao
D. Chỉ dùng replication và bỏ mọi backup
Đáp án đúng: C

Câu 36. Tại sao không nên chạy OPTIMIZE TABLE ... FINAL sau mỗi INSERT?
A. Vì tự tạo nhiều shard ngoài cấu hình cluster
B. Vì vô hiệu hoàn toàn chỉ mục của MergeTree
C. Vì ép merge lớn và tiêu tốn tài nguyên
D. Vì tự xóa toàn bộ part chưa được replicated
Đáp án đúng: C
