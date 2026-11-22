# Tràn sắp xếp hoặc phép nối xuống đĩa và cách chẩn đoán

Khi truy vấn cần sắp xếp nhiều hàng hoặc nối hai tập dữ liệu lớn, hệ quản trị thường dùng bộ nhớ làm việc để giữ dữ liệu trung gian. Nếu lượng dữ liệu vượt ngân sách dành cho thao tác, hệ quản trị có thể chia dữ liệu thành các phần, ghi tạm xuống đĩa rồi đọc lại để hoàn tất. Hiện tượng này gọi là spill to disk, sort spill hoặc hash spill. Nó làm tăng độ trễ, I/O và áp lực lên vùng lưu trữ tạm, nhất là khi nhiều truy vấn chạy đồng thời.

Trong chương **Bộ nhớ và bộ đệm** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn nhận diện tràn sắp xếp và phép nối, hiểu cơ chế cấp phát bộ nhớ, đọc kế hoạch thực thi và truy tìm nguyên nhân. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Chẩn đoán spill cần kết hợp kế hoạch, cardinality, độ rộng hàng, thống kê, memory grant và số liệu I/O thực tế.

## 1. Spill là gì?

Các toán tử như SORT, HASH JOIN, HASH AGGREGATE hoặc DISTINCT có thể cần giữ nhiều dữ liệu trung gian. Hệ quản trị ước lượng lượng bộ nhớ cần thiết và cấp phát ngân sách phù hợp với cấu hình, tải hiện tại và giới hạn tài nguyên.

Nếu dữ liệu thực tế lớn hơn lượng bộ nhớ có thể sử dụng, toán tử có thể chuyển sang thuật toán ngoài bộ nhớ:

- SORT chia dữ liệu thành các run đã sắp xếp trong bộ nhớ, ghi các run xuống vùng tạm rồi trộn chúng để tạo kết quả có thứ tự.
- HASH JOIN chia đầu vào thành nhiều partition hoặc batch, ghi các phần xuống vùng tạm rồi xử lý từng batch.
- HASH AGGREGATE có thể chia nhóm hoặc chuyển sang phương án khác khi bảng băm không vừa bộ nhớ.
- Một số toán tử khác cũng có thể tạo worktable hoặc temporary data khi vượt giới hạn.

Spill là cơ chế giúp truy vấn vẫn hoàn tất khi dữ liệu không vừa bộ nhớ, chứ không nhất thiết là lỗi. Tuy nhiên, ghi và đọc dữ liệu tạm tạo thêm I/O, có thể làm truy vấn chậm hơn nhiều so với xử lý hoàn toàn trong bộ nhớ.

Cần phân biệt ba khái niệm:

- **Buffer cache:** lưu các trang dữ liệu và chỉ mục để giảm đọc từ storage.
- **Query execution memory:** bộ nhớ làm việc cho sort, hash và các toán tử trung gian.
- **Temporary storage:** vùng lưu dữ liệu tạm khi thao tác cần spill hoặc tạo đối tượng tạm.

Tăng buffer cache không tự động làm sort hoặc hash có thêm bộ nhớ làm việc. Ngược lại, tăng memory dành cho từng toán tử có thể làm giảm cache còn lại hoặc gây áp lực RAM khi nhiều truy vấn chạy đồng thời.

## 2. Sort spill hoạt động như thế nào?

Một truy vấn dùng ORDER BY có thể cần sắp xếp toàn bộ tập kết quả nếu không có đường truy cập cung cấp sẵn thứ tự phù hợp.

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC;
~~~

Nếu hệ quản trị phải đọc hàng triệu hàng rồi sort, nó có thể dùng bộ nhớ để sắp xếp. Khi dữ liệu vượt ngân sách, thuật toán external sort tạo các run đã sắp xếp và ghi chúng xuống vùng tạm. Sau đó, hệ thống trộn các run để tạo thứ tự cuối cùng.

Dấu hiệu thường gặp:

- Sort method là external merge hoặc phương án ngoài bộ nhớ tương đương.
- Kế hoạch cho biết lượng disk hoặc temp space được sử dụng.
- Số lượt trộn (merge passes) tăng.
- Temp read/write tăng rõ rệt.
- Thời gian của toán tử sort lớn so với phần còn lại.

Không phải mọi ORDER BY đều gây spill. Nếu chỉ mục có thứ tự phù hợp và điều kiện lọc dùng được tiền tố của chỉ mục, hệ quản trị có thể đọc dữ liệu theo thứ tự cần thiết. Nếu truy vấn chỉ lấy một số hàng đầu, chiến lược top-N có thể giữ ít dữ liệu hơn so với sort toàn bộ, tùy hệ quản trị và kế hoạch.

### 2.1. Vì sao sort lớn hơn dự kiến?

Một sort cần giữ khóa sắp xếp và thường cả thông tin để trả về hàng. Độ rộng dữ liệu ảnh hưởng đáng kể đến bộ nhớ cần dùng. Nếu truy vấn chọn nhiều cột lớn như JSON, TEXT, BLOB hoặc payload dài, dữ liệu trung gian có thể lớn hơn nhiều so với số hàng gợi ý.

Nguyên nhân thường gặp:

- Điều kiện lọc trả về nhiều hàng hơn ước lượng.
- Truy vấn sắp xếp theo nhiều cột hoặc biểu thức.
- Hàng trung gian rộng do SELECT nhiều cột.
- JOIN tạo fan-out trước khi sort.
- DISTINCT hoặc GROUP BY tạo thêm thao tác sort.
- Không có chỉ mục hỗ trợ thứ tự.
- Phân bố dữ liệu lệch hoặc tham số làm thay đổi cardinality.

Hãy xem cả số hàng lẫn độ rộng hàng. Một triệu hàng nhỏ và một triệu hàng chứa nhiều cột lớn có nhu cầu bộ nhớ rất khác nhau.

## 3. Hash join spill hoạt động như thế nào?

Hash join thường xây dựng bảng băm từ một đầu vào (build side), sau đó dò tìm các hàng của đầu vào còn lại (probe side). Nếu bảng băm vừa bộ nhớ, phép nối có thể diễn ra hiệu quả mà không cần sắp xếp cả hai phía.

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= :start_time
  AND o.created_at < :end_time;
~~~

Tùy cardinality và chi phí, optimizer chọn phía build và probe. Nếu phía build lớn hơn dự kiến hoặc mỗi hàng chứa nhiều dữ liệu, hash table có thể vượt ngân sách. Hệ quản trị có thể chia dữ liệu thành nhiều batch, ghi một phần xuống temp storage rồi xử lý từng batch.

Dấu hiệu trong kế hoạch:

- Số hash batches lớn hơn một hoặc tăng theo tải.
- Có thông tin spill level, spilled bytes hoặc temp I/O.
- Hash join tiêu thụ bộ nhớ đáng kể.
- Số hàng build thực tế vượt xa estimated rows.
- Thời gian chờ đọc/ghi vùng tạm tăng.

Một hash join có nhiều batch không tự động chứng minh truy vấn được viết sai. Nó cho biết tập dữ liệu cần xử lý vượt khả năng xử lý trong bộ nhớ theo cấu hình và ngân sách tại thời điểm đó. Cần xác định vì sao tập dữ liệu lớn: lọc chưa đủ, thống kê sai, join order không phù hợp, hàng rộng hay bộ nhớ cấp phát thấp.

## 4. Phân biệt spill với các nguyên nhân chậm khác

Một truy vấn chậm không nhất thiết do spill. Hãy phân biệt:

| Hiện tượng | Dấu hiệu chính | Hướng điều tra |
|---|---|---|
| Sort/hash spill | Temp read/write, external sort, hash batches hoặc spill warning | Memory grant, cardinality, row width, temp I/O |
| Buffer cache miss | Đọc trang từ storage nhiều, cache hit giảm | Working set, index/table access, storage latency |
| Lock contention | Lock wait, blocking chain, transaction giữ khóa lâu | Transaction, isolation, truy cập đồng thời |
| CPU-bound | CPU cao, ít chờ I/O, toán tử tính toán tốn thời gian | Biểu thức, số hàng, thuật toán, song song |
| Storage-bound | I/O latency cao, queue dài, throughput giới hạn | Storage, scan volume, temp I/O |
| Network-bound | Thời gian truyền kết quả lớn, client đọc chậm | Số hàng/cột trả về, fetch size, network |
| Estimate error | Estimated rows khác actual rows lớn | Statistics, skew, parameter sensitivity |

Một spill nhỏ có thể không đáng quan tâm nếu truy vấn vẫn đạt mục tiêu độ trễ. Ngược lại, spill lặp lại trên truy vấn quan trọng có thể làm p95/p99 tăng mạnh và gây cạnh tranh temp storage. Đánh giá theo tác động thực tế, không chỉ theo sự xuất hiện của cảnh báo.

## 5. Memory grant và ngân sách bộ nhớ truy vấn

Nhiều hệ quản trị có cơ chế cấp phát bộ nhớ cho thao tác sort/hash. Ngân sách có thể được tính dựa trên estimated rows, row width, thuật toán, số luồng song song và giới hạn toàn hệ thống.

Cần hiểu ba giới hạn:

1. **Giới hạn cấu hình:** mức tối đa hoặc tham số cho phép thao tác dùng.
2. **Memory grant/work area:** lượng bộ nhớ thực tế được cấp cho truy vấn hoặc toán tử.
3. **Bộ nhớ sử dụng thực tế:** lượng bộ nhớ toán tử cần khi thực thi với dữ liệu thật.

Một grant thấp có thể gây spill dù máy còn RAM, vì hệ quản trị giới hạn lượng bộ nhớ được phép cấp để bảo vệ toàn hệ thống. Một grant quá lớn cũng có thể gây vấn đề: nhiều truy vấn đồng thời chờ cấp bộ nhớ hoặc chiếm phần lớn RAM.

Không nên tăng giới hạn toàn cục chỉ vì một truy vấn spill. Hãy xác định truy vấn nào cần bộ nhớ, số truy vấn đồng thời và tác động lên cache, hệ điều hành cùng các dịch vụ khác.

## 6. Cardinality estimate ảnh hưởng đến memory grant

Optimizer thường ước lượng số hàng và độ rộng dữ liệu trước khi thực thi. Các ước lượng này ảnh hưởng đến thuật toán nối, phía build của hash join, kích thước bảng băm, memory grant, số hàng trung gian và quyết định dùng index hay scan.

Nếu estimated rows thấp hơn actual rows nhiều lần, hệ quản trị có thể cấp ít bộ nhớ hơn cần thiết và gây spill. Nếu estimated rows cao hơn thực tế, grant có thể quá lớn, làm giảm khả năng chạy đồng thời.

Nguyên nhân sai lệch thường gồm:

- Thống kê đã lỗi thời sau bulk load hoặc thay đổi dữ liệu lớn.
- Histogram không mô tả tốt giá trị phổ biến hoặc hiếm.
- Các cột có tương quan nhưng optimizer giả định độc lập.
- Phân bố lệch giữa tenant hoặc partition.
- Tham số khác nhau tạo ra cardinality khác nhau.
- Biểu thức hoặc chuyển đổi kiểu khiến optimizer khó ước lượng.

Hãy tìm bước đầu tiên có estimated rows lệch đáng kể so với actual rows. Nếu sai lệch bắt đầu ở một scan/filter, giải quyết thống kê hoặc điều kiện đó có thể giúp toàn bộ kế hoạch, thay vì chỉ tăng memory grant ở toán tử spill cuối cùng.
## 7. Độ rộng hàng và tập dữ liệu trung gian

Một truy vấn có thể tạo hàng trung gian rộng không cần thiết. Nếu chỉ cần order_id để nối tiếp với bảng khác nhưng truy vấn kéo theo JSON payload, ghi chú dài và nhiều cột mô tả, các toán tử sort/hash có thể phải giữ nhiều dữ liệu hơn.

Các cách giảm độ rộng:

- Chỉ chọn cột thực sự cần ở từng bước.
- Đưa projection xuống trước sort/hash khi ngữ nghĩa cho phép.
- Lọc sớm để giảm số hàng.
- Tránh JOIN tạo fan-out trước khi tổng hợp.
- Tổng hợp về đúng grain trước khi nối nếu kết quả cần cấp tổng hợp.
- Không đưa cột LOB hoặc payload lớn vào sort key nếu không cần.
- Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại.

Ví dụ, thay vì nối toàn bộ hàng order_items với products rồi mới lấy danh sách order_id, có thể kiểm tra sự tồn tại:

~~~sql
SELECT o.order_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.order_id = o.order_id
);
~~~

Optimizer có thể triển khai bằng semi join, tránh tạo tất cả tổ hợp hàng con nếu truy vấn chỉ cần biết có ít nhất một dòng hàng.

Giảm số hàng và độ rộng hàng thường bền vững hơn việc tăng bộ nhớ. Nó giảm cả RAM, temp I/O và lượng dữ liệu truyền giữa các toán tử.

## 8. Tối ưu sort trước khi tăng bộ nhớ

Khi phát hiện sort spill, hãy kiểm tra liệu sort có thực sự cần thiết.

- Truy vấn có ORDER BY bắt buộc không?
- Chỉ mục có thể cung cấp thứ tự cần thiết không?
- Điều kiện lọc có dùng được tiền tố của chỉ mục không?
- Có thể dùng top-N hoặc LIMIT để tránh sort toàn bộ không?
- DISTINCT hoặc GROUP BY có tạo sort không cần thiết không?
- Sort có diễn ra sau JOIN làm tăng fan-out không?
- Có thể giảm số cột hoặc hàng trước sort không?

Ví dụ:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC
LIMIT 100;
~~~

Một chỉ mục phù hợp như (tenant_id, created_at DESC) có thể giúp tìm vùng tenant và đọc 100 hàng theo thứ tự, thay vì sort toàn bộ tập đơn hàng của tenant. Khả năng thực tế phụ thuộc hệ quản trị, phân bố dữ liệu và kế hoạch.

Không tạo index chỉ để loại bỏ một sort nhỏ nếu chi phí duy trì index lớn hơn lợi ích. Đo số hàng được đọc, số hàng trả về và tác động lên INSERT/UPDATE/DELETE.

## 9. Tối ưu hash join và hash aggregate

Khi hash spill xuất hiện, hãy kiểm tra:

- Phía build có được chọn đúng theo cardinality thực tế không?
- Có thể lọc đầu vào trước khi xây dựng hash table không?
- Có cột nào không cần nhưng đang được giữ trong hash row không?
- Join key có kiểu dữ liệu tương thích không?
- Thống kê và histogram có phản ánh phân bố thực tế không?
- Có thể thay đổi thứ tự nối hoặc pre-aggregate để giảm đầu vào không?
- Có nhiều hash operation cùng cạnh tranh bộ nhớ không?
- Truy vấn có chạy song song với nhiều worker làm tăng tổng bộ nhớ không?

Nếu một bảng lớn được nối với tập khóa nhỏ, lọc hoặc thu gọn tập khóa trước khi join có thể giảm hash table. Nếu truy vấn chỉ cần kiểm tra tồn tại, EXISTS/semi join có thể tránh materialize mọi cặp khớp.

Không ép join algorithm bằng hint chỉ dựa trên một lần đo. Một hash join có spill ở tải thấp có thể hoạt động khác khi cache nóng hoặc dữ liệu thay đổi. Hãy kiểm tra nhiều nhóm tham số và tải đồng thời.

## 10. Chẩn đoán trên PostgreSQL

PostgreSQL cung cấp thông tin về sort method, hash batches và temporary block trong kế hoạch hoặc thống kê.

### 10.1. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC;
~~~

Trong kết quả, chú ý:

- Sort Method: quicksort thường cho biết sort trong bộ nhớ; external merge cho biết sort dùng vùng tạm.
- Disk: lượng dung lượng tạm mà sort sử dụng nếu được báo cáo.
- Hash: số buckets, batches và memory usage.
- Buffers: shared/local/temp blocks read và written.
- Actual Rows và estimated rows ở từng node.
- Workers planned/launched nếu truy vấn song song.

EXPLAIN ANALYZE thực thi câu lệnh. Với câu lệnh ghi hoặc truy vấn có hàm gây tác dụng phụ, cần đánh giá tác động và dùng môi trường hoặc transaction an toàn. Không chạy phân tích trên production nếu chưa hiểu tải và hành vi truy vấn.

### 10.2. work_mem và hash_mem_multiplier

work_mem là ngân sách bộ nhớ cơ bản cho một số thao tác sort và hash, không phải tổng bộ nhớ cho cả server hoặc một kết nối. Một truy vấn có thể có nhiều thao tác sort/hash; truy vấn song song có thể có nhiều worker; nhiều session có thể chạy cùng lúc. Vì vậy, tăng work_mem toàn cục có thể làm tổng nhu cầu bộ nhớ tăng theo số thao tác và mức đồng thời.

PostgreSQL có hash_mem_multiplier để điều chỉnh giới hạn bộ nhớ cho các thao tác hash so với work_mem. Giá trị mặc định và hành vi phụ thuộc phiên bản. Hãy xem tài liệu phiên bản đang dùng và đo trước khi thay đổi.

Có thể thử một giá trị riêng cho session hoặc transaction khi đã xác định truy vấn cần thêm bộ nhớ, nhưng phải tính đến số toán tử và số truy vấn đồng thời. Không đặt work_mem rất lớn cho mọi kết nối chỉ để xử lý một truy vấn hiếm.

### 10.3. Theo dõi temporary file và thống kê

Một số công cụ quan sát PostgreSQL:

- log_temp_files có thể ghi nhận temporary file vượt ngưỡng cấu hình.
- pg_stat_database cung cấp temp_files và temp_bytes theo database.
- pg_stat_statements, nếu được bật và cấu hình phù hợp, có thể cung cấp temp_blks_read và temp_blks_written theo query.
- EXPLAIN (ANALYZE, BUFFERS) giúp xác định node tạo temp I/O.

Các bộ đếm thống kê thường tích lũy từ lần reset gần nhất. Hãy ghi nhận thời điểm reset và so sánh theo khoảng thời gian tương đương. Tổng temp_bytes tăng không tự chỉ ra câu truy vấn gây ra; cần liên kết với query fingerprint hoặc log.

## 11. Chẩn đoán trên SQL Server

SQL Server cấp memory grant cho các truy vấn cần sort/hash. Actual execution plan có thể hiển thị memory grant requested, granted và used, cùng cảnh báo spill ở các toán tử.

Cần kiểm tra:

- Sort Warning hoặc Hash Warning trong execution plan.
- Spill level và số trang/byte ghi ra tempdb nếu có thông tin.
- Requested memory, granted memory và max used memory.
- Estimated rows so với actual rows.
- Memory grant wait và các truy vấn khác đang giữ grant.
- Tempdb data file I/O, dung lượng và contention.

Các phiên bản SQL Server mới có thể hỗ trợ memory grant feedback để điều chỉnh grant cho các lần thực thi sau. Tính năng, giới hạn và hành vi phụ thuộc phiên bản, compatibility level và loại truy vấn. Không coi memory grant feedback là thay thế cho việc sửa cardinality estimate hoặc giảm dữ liệu trung gian.

Nếu truy vấn có grant lớn nhưng chỉ dùng một phần nhỏ, nó có thể làm các truy vấn khác chờ cấp bộ nhớ. Nếu grant nhỏ, sort/hash có thể spill. Hãy xem cả memory grant và concurrency thay vì chỉ tập trung vào một câu lệnh.

## 12. Chẩn đoán trên MySQL

MySQL có thể dùng vùng nhớ cho sort và internal temporary table, sau đó chuyển một số thao tác sang temporary storage khi vượt giới hạn hoặc khi loại dữ liệu không phù hợp lưu trong bộ nhớ.

Các thông tin có thể hữu ích tùy phiên bản:

- EXPLAIN và EXPLAIN ANALYZE để xem iterator, actual rows và thời gian.
- SHOW SESSION STATUS hoặc SHOW GLOBAL STATUS với các biến như Created_tmp_tables, Created_tmp_disk_tables, Sort_merge_passes và Sort_rows.
- Performance Schema để liên kết hoạt động với statement và thời gian chờ.
- Cấu hình TempTable, tmp_table_size, max_heap_table_size hoặc các tham số liên quan theo phiên bản.

Created_tmp_disk_tables không chỉ ra mọi dạng sort spill; nó phản ánh các internal temporary table được ghi ra disk theo định nghĩa của MySQL. Sort_merge_passes liên quan đến merge pass của filesort. Hãy đọc tài liệu phiên bản cụ thể và không gộp mọi counter thành một chỉ số spill duy nhất.

Nếu temporary table chuyển sang disk, kiểm tra kích thước kết quả trung gian, kiểu cột, các cột lớn và giới hạn cấu hình. Nếu filesort có nhiều merge pass, kiểm tra số hàng, độ rộng khóa và khả năng tận dụng index ordering.

## 13. Chẩn đoán trên Oracle

Oracle sử dụng PGA work areas cho các thao tác như sort, hash join và bitmap operations. Work area có thể chạy ở chế độ optimal, one-pass hoặc multi-pass tùy lượng bộ nhớ và dữ liệu cần xử lý.

Một số view và công cụ thường được dùng:

- V$SQL_WORKAREA và V$SQL_WORKAREA_ACTIVE để quan sát work area.
- V$SQL_PLAN hoặc actual execution plan để xem các toán tử.
- SQL Monitor trong môi trường và phiên bản có hỗ trợ.
- Thống kê temp usage và các wait event liên quan đến direct path read/write temp.

Nếu work area chạy one-pass hoặc multi-pass, thao tác phải dùng TEMP tablespace. Multi-pass thường có thể làm tăng đáng kể I/O và thời gian. Cần kiểm tra PGA target/limit, mức sử dụng đồng thời và các giới hạn tài nguyên của instance.

Không tăng PGA_AGGREGATE_TARGET hoặc giới hạn PGA chỉ dựa trên một SQL. Một thay đổi ảnh hưởng đến toàn instance và có thể gây áp lực bộ nhớ. Hãy xem workload tổng thể, số work area hoạt động đồng thời và chính sách quản trị tài nguyên.
## 14. Temp storage có thể trở thành nút thắt mới

Khi nhiều truy vấn spill cùng lúc, vùng lưu trữ tạm có thể trở thành điểm nghẽn độc lập. Ngay cả khi từng truy vấn chỉ ghi một lượng dữ liệu vừa phải, tổng temp I/O từ nhiều session có thể làm tăng độ trễ.

Các dấu hiệu:

- Temp read/write tăng cùng thời điểm p95/p99 tăng.
- I/O latency của temp volume cao.
- Tempdb hoặc TEMP tablespace tăng dung lượng nhanh.
- Truy vấn không spill trước đây bắt đầu spill khi concurrency tăng.
- Sort/hash wait hoặc memory grant wait tăng.
- Các workload khác bị chậm dù không trực tiếp dùng sort lớn.

Cần phân biệt temp I/O với data I/O. Một truy vấn có thể đọc ít trang bảng nhưng ghi hàng gigabyte vào temp storage. Nếu chỉ xem logical reads hoặc buffer cache hit, nguyên nhân sẽ bị bỏ sót.

Theo dõi cả dung lượng, throughput, latency, queue depth và giới hạn dung lượng temp. Đảm bảo vùng tạm có đủ không gian, nhưng không xem việc mở rộng temp storage là cách khắc phục gốc cho truy vấn tạo dữ liệu trung gian quá lớn.

## 15. Ảnh hưởng của concurrency và parallelism

Ngân sách bộ nhớ được cấp cho một toán tử cần được đặt trong bối cảnh toàn hệ thống. Nếu 20 truy vấn cùng lúc chạy sort lớn, tổng nhu cầu có thể vượt RAM dù từng truy vấn riêng lẻ chạy tốt.

Parallel execution cũng có thể làm tăng số thao tác hoặc worker sử dụng bộ nhớ. Một số hệ quản trị chia grant giữa worker; một số cấu hình hoặc toán tử có thể nhân mức tiêu thụ theo số worker. Không giả định memory grant của truy vấn song song bằng truy vấn đơn luồng.

Khi điều tra, hãy so sánh:

- Một truy vấn chạy đơn lẻ với cùng truy vấn dưới concurrency thực tế.
- Grant được yêu cầu/cấp so với bộ nhớ sử dụng.
- Số worker planned và launched.
- Temp I/O tổng theo thời gian.
- Thời gian chờ cấp bộ nhớ.
- Các query khác đang chạy cùng lúc.
- CPU saturation và storage queue.

Nếu spill chỉ xuất hiện khi tải đồng thời cao, tăng bộ nhớ cho từng truy vấn có thể làm tình trạng nghiêm trọng hơn. Có thể cần giới hạn concurrency, điều chỉnh workload scheduling, giảm kích thước truy vấn hoặc tối ưu truy vấn ưu tiên.

## 16. Quy trình chẩn đoán có hệ thống

Khi phát hiện sort hoặc hash spill, hãy đi theo thứ tự:

1. **Xác định truy vấn:** lấy query fingerprint, tham số, tần suất và mức độ ảnh hưởng đến người dùng.
2. **Xác nhận spill:** dùng actual plan, log hoặc thống kê engine để xác định node, lượng temp I/O và thời gian.
3. **Tìm sai lệch đầu tiên:** so sánh estimated rows với actual rows từ scan/filter đầu tiên đến node spill.
4. **Kiểm tra row width:** xem cột lớn, payload, biểu thức và số cột được giữ qua toán tử.
5. **Kiểm tra thứ tự và fan-out:** xác định JOIN, GROUP BY, DISTINCT hoặc ORDER BY có tạo tập trung gian lớn không.
6. **Kiểm tra thống kê:** xem thời điểm cập nhật, histogram, skew và tương quan cột.
7. **Kiểm tra memory grant/work area:** requested, granted, used và giới hạn cấu hình.
8. **Kiểm tra concurrency:** số truy vấn đồng thời, worker và memory grant wait.
9. **Kiểm tra temp storage:** read/write, latency, queue và dung lượng.
10. **Đưa ra giả thuyết:** nêu rõ thay đổi nào sẽ giảm hàng, giảm độ rộng, tránh sort hoặc tăng grant có kiểm soát.
11. **Thử nghiệm:** dùng dữ liệu, tham số và mức tải đại diện; lưu kế hoạch trước/sau.
12. **Đo lại:** p50/p95/p99, CPU, I/O, temp bytes, throughput và tác động truy vấn khác.
13. **Theo dõi:** kiểm tra spill có tái diễn ở các nhóm tham số hoặc chu kỳ tải khác không.

Không bắt đầu bằng cách tăng tất cả giới hạn bộ nhớ. Trước tiên xác định node spill và lý do nó cần lượng dữ liệu lớn.

## 17. Thứ tự khắc phục ưu tiên

### 17.1. Giảm số hàng trước toán tử

- Đưa điều kiện lọc hợp lệ đến gần bảng nguồn.
- Dùng khoảng thời gian sargable thay cho hàm trên cột.
- Loại bỏ JOIN không cần thiết.
- Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại.
- Tổng hợp trước khi nối nếu grain cho phép.
- Kiểm tra partition pruning.

Giảm số hàng thường làm sort/hash nhỏ hơn và có thể loại bỏ spill mà không cần thêm bộ nhớ.

### 17.2. Giảm độ rộng hàng

- Chỉ chọn cột cần thiết.
- Không mang LOB hoặc JSON qua sort/hash nếu không cần.
- Tránh giữ cột lớn trong hash build side.
- Tách bước lấy khóa khỏi bước lấy payload nếu điều đó giảm đáng kể dữ liệu trung gian.

### 17.3. Cải thiện đường truy cập

- Tạo hoặc điều chỉnh chỉ mục để hỗ trợ ORDER BY khi workload chứng minh lợi ích.
- Chọn thứ tự cột phù hợp với điều kiện lọc và nối.
- Kiểm tra covering index có làm chỉ mục quá rộng không.
- Cân nhắc index access so với sequential scan bằng kế hoạch thực tế.

### 17.4. Sửa thống kê và ước lượng

- Cập nhật thống kê sau bulk load hoặc thay đổi dữ liệu lớn.
- Xem histogram cho giá trị phổ biến/hiếm.
- Xem thống kê đa cột khi có tương quan.
- Kiểm tra parameter-sensitive plan.
- Đảm bảo thống kê trên partition hoặc bảng tạm phù hợp.

### 17.5. Điều chỉnh memory có kiểm soát

Chỉ sau khi hiểu query và workload, mới cân nhắc tăng memory cho thao tác hoặc truy vấn cụ thể. Đánh giá số truy vấn đồng thời, số sort/hash operation, worker, RAM còn lại và ảnh hưởng lên cache.

### 17.6. Bảo đảm temp storage phù hợp

Nếu spill là không thể tránh với workload hợp lệ, bảo đảm temp storage đủ dung lượng và có I/O phù hợp. Đây là biện pháp vận hành để hệ thống xử lý tải ổn định, không thay thế tối ưu cardinality và dữ liệu trung gian.

## 18. Ví dụ: hash join và sort cùng spill

Giả sử báo cáo lấy đơn hàng hoàn tất của một tenant, nối với khách hàng và dòng hàng, sau đó sắp xếp theo tổng giá trị:

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.tenant_id = :tenant_id
  AND o.status = 'COMPLETED'
  AND o.created_at >= :start_time
  AND o.created_at < :end_time
GROUP BY o.order_id, c.customer_name
ORDER BY item_total DESC
LIMIT 100;
~~~

Kế hoạch cho thấy:

- Bộ lọc orders ước lượng 20.000 hàng nhưng thực tế trả 900.000 hàng.
- Hash join với order_items tạo lượng hàng lớn.
- Hash aggregate cần nhiều batch và ghi temp.
- Sort cuối dùng external merge và ghi thêm temp data.

Không nên lập tức tăng memory cho cả hash và sort. Điều tra theo các bước:

**Bước 1: Kiểm tra cardinality.** Sai lệch bắt đầu ở filter orders. Kiểm tra thống kê tenant_id, status, created_at và phân bố theo tenant. Nếu dữ liệu mới hoặc lệch mạnh, cập nhật thống kê phù hợp.

**Bước 2: Giảm tập orders.** Xác nhận điều kiện thời gian và tenant được áp dụng sớm. Kiểm tra partition pruning nếu bảng phân vùng theo created_at. Đánh giá chỉ mục (tenant_id, status, created_at) theo workload và tỷ lệ ghi.

**Bước 3: Kiểm tra fan-out.** order_items có nhiều hàng cho mỗi order. Truy vấn cần tổng theo order nên có thể tổng hợp order_items theo order_id trước khi nối, sau khi giới hạn tập order cần thiết.

**Bước 4: Giảm độ rộng.** Chỉ giữ order_id, customer_id, quantity và unit_price trong giai đoạn tính tổng; không kéo payload không cần qua hash/sort.

**Bước 5: Xem sort cuối.** Nếu cần top 100 theo item_total, optimizer có thể dùng chiến lược top-N nhưng vẫn phải tính tổng cho các đơn đủ điều kiện. Kiểm tra kế hoạch có sort toàn bộ kết quả hay top-N và lượng dữ liệu trung gian.

**Bước 6: Đo lại dưới concurrency.** So sánh temp bytes, hash batches, sort method, CPU, I/O, p95/p99 và các truy vấn khác. Nếu vẫn có spill nhỏ nhưng truy vấn đạt mục tiêu và không gây nghẽn temp storage, có thể chấp nhận thay vì tăng bộ nhớ toàn hệ thống.

Ví dụ cho thấy spill là triệu chứng ở cuối một chuỗi nguyên nhân. Sửa cardinality và giảm dữ liệu trung gian có thể giải quyết đồng thời hash spill, sort spill và lượng I/O.

## 19. Những sai lầm thường gặp

- **Tăng work_mem hoặc memory grant toàn cục ngay lập tức.** Có thể làm tổng nhu cầu RAM vượt giới hạn khi nhiều truy vấn đồng thời.
- **Nhầm buffer cache với query work memory.** Hai loại bộ nhớ phục vụ mục đích khác nhau.
- **Chỉ xem node spill cuối cùng.** Sai lệch cardinality có thể bắt đầu từ scan/filter trước đó.
- **Bỏ qua độ rộng hàng.** Nhiều cột lớn làm hash table và sort run phình to.
- **Tạo index cho mọi ORDER BY.** Index làm tăng chi phí ghi và không phải lúc nào cũng rẻ hơn sort.
- **Ép join algorithm bằng hint.** Có thể tốt cho một nhóm tham số nhưng gây hồi quy ở nhóm khác.
- **Cho rằng temp I/O chỉ là buffer cache miss.** Spill có thể ghi lượng dữ liệu tạm lớn dù data reads thấp.
- **Chỉ đo truy vấn đơn lẻ.** Spill và memory wait thường chỉ xuất hiện khi concurrency tăng.
- **Bỏ qua thống kê sau bulk load.** Optimizer có thể cấp grant dựa trên cardinality quá thấp hoặc quá cao.
- **Chỉ tăng temp storage.** Mở rộng dung lượng không giảm lượng công việc lặp hoặc I/O không cần thiết.
- **Coi mọi spill là lỗi cần loại bỏ.** Một spill nhỏ có thể là lựa chọn hợp lý khi chi phí tránh spill cao hơn lợi ích.
- **Không đo toàn workload sau điều chỉnh.** Một truy vấn nhanh hơn có thể làm các truy vấn khác thiếu bộ nhớ hoặc cache.

## 20. Checklist chẩn đoán sort/hash spill

- [ ] Đã xác định query fingerprint, tham số và mức độ ảnh hưởng.
- [ ] Đã xác nhận node spill bằng actual plan, log hoặc thống kê phù hợp.
- [ ] Đã ghi nhận temp read/write hoặc spilled bytes.
- [ ] Đã so sánh estimated rows với actual rows ở từng bước.
- [ ] Đã tìm bước đầu tiên có cardinality sai lệch đáng kể.
- [ ] Đã kiểm tra row width, cột lớn và dữ liệu trung gian.
- [ ] Đã kiểm tra JOIN fan-out, GROUP BY, DISTINCT và ORDER BY.
- [ ] Đã xem khả năng lọc sớm, pre-aggregation và partition pruning.
- [ ] Đã kiểm tra chỉ mục có thể cung cấp thứ tự hoặc đường truy cập phù hợp.
- [ ] Đã kiểm tra statistics, histogram, skew và parameter sensitivity.
- [ ] Đã kiểm tra requested/granted/used memory hoặc work area.
- [ ] Đã đo concurrency, parallel workers và memory grant wait.
- [ ] Đã kiểm tra temp storage latency, throughput, queue và dung lượng.
- [ ] Đã thử điều chỉnh theo từng giả thuyết và lưu kế hoạch trước/sau.
- [ ] Đã đo p50/p95/p99, CPU, I/O, temp bytes và tác động workload khác.
- [ ] Đã xác định spill còn lại có chấp nhận được theo SLO hay không.

## 21. Nguyên tắc cần ghi nhớ

Sort hoặc hash spill xảy ra khi dữ liệu trung gian vượt ngân sách bộ nhớ dành cho thao tác và hệ quản trị phải dùng vùng lưu trữ tạm. Spill có thể làm tăng I/O và độ trễ, nhưng nguyên nhân gốc thường liên quan đến cardinality estimate, độ rộng hàng, fan-out, thiếu lọc sớm, thống kê hoặc memory grant dưới tải đồng thời.

Hãy xác nhận spill bằng kế hoạch và số liệu temp I/O, tìm bước đầu tiên có ước lượng sai, giảm số hàng và độ rộng dữ liệu trước khi cân nhắc tăng bộ nhớ. Đánh giá cả concurrency, parallelism, temp storage và ảnh hưởng lên truy vấn khác. Sau mỗi điều chỉnh, so sánh kết quả và p95/p99 trên workload đại diện. Mục tiêu là đưa truy vấn về mức tài nguyên phù hợp và ổn định, không phải loại bỏ mọi spill bằng cách cấp phát bộ nhớ không giới hạn.
