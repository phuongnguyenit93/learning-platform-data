# sort_buffer_size, join_buffer_size và bộ nhớ nhân theo kết nối

Một máy chủ MySQL có thể còn nhiều RAM nhưng vẫn gặp lỗi cấp phát bộ nhớ khi tải tăng đột ngột. Nguyên nhân thường nằm ở cách nhiều phiên đồng thời thực hiện sort, join, đọc dữ liệu hoặc tạo bảng tạm. Các biến như sort_buffer_size và join_buffer_size điều khiển một phần bộ nhớ làm việc của những thao tác đó. Chúng có thể cải thiện một truy vấn cụ thể, nhưng nếu đặt quá lớn ở cấp GLOBAL, tổng mức dùng bộ nhớ khi nhiều truy vấn chạy cùng lúc có thể vượt xa dự tính.

Bài học này giải thích cách MySQL cấp phát bộ nhớ theo kết nối và theo thao tác, vai trò của sort_buffer_size và join_buffer_size, cách phân biệt bộ nhớ cục bộ với bộ nhớ toàn cục, và cách lập ngân sách bộ nhớ theo mức đồng thời. Các ví dụ hướng tới MySQL 8.0/8.4; thuật toán join, tên metric và một số biến có thể khác theo phiên bản. Luôn xác minh cấu hình và kế hoạch thực thi trên đúng phiên bản đang vận hành.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Giải thích vì sao số kết nối không đồng nghĩa với số bộ đệm lớn đã được cấp phát.
- Mô tả khi nào sort_buffer_size và join_buffer_size được sử dụng.
- Nhận diện các bộ đệm theo phiên khác như read_buffer_size, read_rnd_buffer_size và net_buffer_length.
- Phân biệt bộ nhớ theo kết nối, bộ nhớ theo thao tác và bộ nhớ dùng chung toàn server.
- Ước lượng đỉnh bộ nhớ theo số thao tác đồng thời thay vì nhân máy móc mọi biến với max_connections.
- Dùng Performance Schema, sys schema, status variables và công cụ hệ điều hành để đo bộ nhớ.
- Đọc EXPLAIN để tìm sort, full join và nguyên nhân truy vấn cần nhiều bộ nhớ.
- Thử thay đổi biến ở SESSION, đo kết quả và chỉ đưa cấu hình lên GLOBAL khi có bằng chứng.

## 2. Mô hình bộ nhớ của một MySQL server

Không có một biến duy nhất thể hiện toàn bộ RAM MySQL đang sử dụng. Có thể chia bộ nhớ thành ba nhóm:

1. **Bộ nhớ toàn cục**: được dùng chung hoặc phục vụ toàn server, ví dụ InnoDB buffer pool, log buffer, key buffer, data dictionary, table cache và một phần cấu trúc Performance Schema.
2. **Bộ nhớ theo kết nối hoặc thread**: phục vụ một phiên client, ví dụ thread stack, network buffer và một số cấu trúc phiên.
3. **Bộ nhớ theo thao tác**: được cấp phát khi một truy vấn cần sort, join, scan, đọc ngẫu nhiên hoặc tạo internal temporary table. Một phiên có thể cần nhiều vùng nhớ thao tác trong cùng một truy vấn.

Trong cấu hình mặc định one-thread-per-connection, mỗi kết nối đang được phục vụ thường gắn với một thread. Thread cache có thể tái sử dụng thread sau khi client ngắt kết nối; thread pool plugin thay đổi cách lập lịch thực thi. Vì vậy, cách gọi “bộ nhớ theo kết nối” là mô hình lập ngân sách dễ hiểu, còn số thread và cách cấp phát thực tế phụ thuộc cấu hình server.

~~~mermaid
flowchart TB
    A[MySQL process memory] --> B[Global memory]
    A --> C[Connection and thread memory]
    A --> D[Operation memory]
    B --> B1[InnoDB buffer pool]
    B --> B2[Log buffer and caches]
    B --> B3[Performance Schema and metadata]
    C --> C1[Thread stack]
    C --> C2[Network buffers]
    D --> D1[Sort buffer]
    D --> D2[Join buffers]
    D --> D3[Read buffers and temporary tables]
    E[Operating system and other processes] --> F[Available physical or cgroup memory]
    A --> F
~~~

Một phiên đang idle không nhất thiết giữ tất cả sort và join buffer ở mức tối đa. Nhiều bộ đệm chỉ được cấp phát khi một thao tác cần đến. Tuy nhiên, khi nhiều truy vấn cùng sort hoặc join, nhiều vùng nhớ có thể cùng tồn tại. Một số cấu trúc được giữ lại hoặc tái sử dụng trong vòng đời phiên; mức sử dụng sau truy vấn có thể không lập tức trở về đúng mức ban đầu.

## 3. Phân loại biến bộ nhớ quan trọng

| Biến | Phạm vi sử dụng | Khi nào cần chú ý |
|---|---|---|
| sort_buffer_size | Bộ đệm sort cho phiên thực hiện sort | ORDER BY, GROUP BY hoặc filesort |
| join_buffer_size | Bộ đệm cho một số thuật toán join không dùng index trực tiếp, gồm các trường hợp hash join/BKA tùy phiên bản và kế hoạch | Join cần scan hoặc hash dữ liệu |
| read_buffer_size | Bộ đệm đọc tuần tự cho một số table scan | Scan lớn, đọc tuần tự |
| read_rnd_buffer_size | Bộ đệm đọc hàng theo thứ tự sau một số thao tác sort | Đọc lại hàng theo thứ tự sort |
| thread_stack | Stack cho thread xử lý | Số thread, độ sâu call stack và giới hạn hệ thống |
| net_buffer_length | Kích thước khởi đầu của communication buffer | Kết nối client/server và gói tin |
| max_allowed_packet | Giới hạn kích thước packet/message | Truyền BLOB, JSON hoặc câu lệnh lớn |
| tmp_table_size | Giới hạn kích thước của một số internal temporary table trong bộ nhớ | GROUP BY, DISTINCT, UNION và truy vấn trung gian |
| max_heap_table_size | Giới hạn của bảng MEMORY; cũng tham gia giới hạn một số internal temporary table | Bảng MEMORY và temporary table theo engine |
| temptable_max_ram | Ngân sách RAM của TempTable engine trong các phiên bản hỗ trợ | Internal temporary table dùng TempTable |
| binlog_cache_size | Bộ đệm transaction cho binary log | Transaction ghi nhiều dữ liệu trước commit |

Không cộng tất cả các giá trị trong bảng để ra RAM bắt buộc cho mỗi kết nối. Các biến có điều kiện kích hoạt, phạm vi khác nhau và một số giới hạn áp dụng theo engine hoặc toàn server. Hãy kiểm tra tài liệu đúng phiên bản trước khi đưa một biến vào mô hình ngân sách.

## 4. sort_buffer_size

sort_buffer_size quy định kích thước bộ đệm sort mà một session có thể dùng khi MySQL thực hiện thao tác sort. Bộ đệm được cấp phát khi cần sort; kết nối không sort không mặc nhiên tiêu thụ toàn bộ giá trị này chỉ vì biến được đặt lớn.

Các trường hợp thường cần sort gồm:

- ORDER BY không thể lấy thứ tự trực tiếp từ index.
- GROUP BY cần sắp xếp theo một kế hoạch thực thi nhất định.
- Một số thao tác DISTINCT, UNION hoặc xử lý trung gian.
- Một phần của kế hoạch join hoặc xử lý kết quả cần filesort.

MySQL có thể dùng index để đáp ứng thứ tự. Khi không thể, optimizer có thể chọn thuật toán filesort. Tên “filesort” không có nghĩa mọi lần sort đều ghi ra đĩa: thuật toán có thể hoàn thành trong bộ nhớ hoặc dùng file tạm khi dữ liệu không vừa bộ đệm hay cần nhiều merge pass.

### 4.1. Dấu hiệu sort cần điều tra

Một số status variable hữu ích:

- Sort_rows: số hàng đã được sắp xếp.
- Sort_scan: số lần sort bắt đầu bằng table scan.
- Sort_range: số lần sort bắt đầu bằng range scan.
- Sort_merge_passes: số merge pass của thuật toán sort.

Các biến trên thường là counter tích lũy. Hãy đo delta hoặc rate trong cùng khoảng thời gian. Nếu Sort_merge_passes tăng nhanh cùng latency và I/O tạm, bộ đệm có thể quá nhỏ cho workload đó; nhưng đây chưa phải bằng chứng đủ để tăng cấu hình. Trước tiên hãy xem số hàng, độ rộng hàng, index và kế hoạch thực thi.

Ví dụ kiểm tra:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_scan',
  'Sort_range',
  'Sort_merge_passes'
);

SHOW SESSION STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_scan',
  'Sort_range',
  'Sort_merge_passes'
);
~~~

Global status giúp quan sát toàn server; session status phù hợp để đo một truy vấn trong chính phiên đang chạy. Ghi lại giá trị trước và sau khi chạy truy vấn rồi tính chênh lệch. Tránh so sánh counter global sau restart với dữ liệu trước restart mà không xử lý reset.

### 4.2. Đọc EXPLAIN

Ví dụ:

~~~sql
EXPLAIN
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

Nếu Extra hoặc cây thực thi cho thấy filesort, hãy kiểm tra:

- Có index phù hợp cho điều kiện lọc và thứ tự nhóm không?
- Số hàng sau WHERE có quá lớn không?
- Có thể lọc sớm hơn hoặc giảm số cột cần xử lý không?
- ORDER BY theo biểu thức tổng hợp có bắt buộc phải sort kết quả trung gian không?
- Truy vấn có trả về nhiều hàng hơn nhu cầu thực tế không?

EXPLAIN ANALYZE có thể thực thi truy vấn để đo thời gian và số hàng thực tế. Chỉ dùng trên môi trường và dữ liệu phù hợp, bởi câu lệnh này chạy truy vấn thật. So sánh estimated rows với actual rows để phát hiện sai lệch thống kê hoặc giả định optimizer.

### 4.3. Tăng sort buffer có giới hạn

Tăng sort_buffer_size có thể giảm merge pass cho một số sort lớn, nhưng lợi ích thường có giới hạn. Khi sort đã vừa bộ đệm, tăng thêm không làm truy vấn nhanh hơn đáng kể. Giá trị quá lớn khiến mỗi sort đồng thời có thể giữ nhiều RAM, làm giảm bộ nhớ dành cho buffer pool hoặc hệ điều hành.

Nếu chỉ một báo cáo lớn cần bộ đệm lớn, thử điều chỉnh ở SESSION cho đúng phiên đó. Không nâng GLOBAL chỉ vì một truy vấn đặc biệt. Đồng thời xem lại index, cardinality, filesort, số hàng và thiết kế báo cáo.

## 5. join_buffer_size

join_buffer_size quy định dung lượng bộ đệm được sử dụng trong một số phép join. Trường hợp điển hình là join không thể dùng index thích hợp cho điều kiện nối và phải xử lý nhiều hàng từ một phía. Các phiên bản MySQL mới có thể dùng hash join; BKA (Batched Key Access) và các thuật toán join khác cũng có thể sử dụng join buffer theo điều kiện và optimizer.

Ý nghĩa thực tế của biến phụ thuộc thuật toán join được chọn:

- Với nested-loop join, thiếu index có thể khiến MySQL phải lặp scan bảng trong; join buffer có thể giảm số lần truy cập theo từng khối.
- Với hash join, bộ nhớ được dùng để xây hoặc xử lý hash table; nếu dữ liệu không vừa vùng nhớ, thuật toán có thể cần xử lý theo batch hoặc dùng tài nguyên tạm.
- Với BKA, join buffer gom khóa để truy xuất hàng loạt qua index.

Trong các phiên bản MySQL 8.0, optimizer và thuật toán join đã thay đổi theo từng bản phát hành. Không suy luận thuật toán chỉ từ giá trị join_buffer_size; hãy đọc EXPLAIN FORMAT=TREE hoặc EXPLAIN ANALYZE trên phiên bản đang chạy.

### 5.1. Một buffer có thể không chỉ dành cho cả truy vấn

Một truy vấn có nhiều phép join. Tùy kế hoạch, MySQL có thể cần nhiều join buffer cho các bước khác nhau. Vì vậy, không nên mô hình hóa chi phí bằng một join_buffer_size duy nhất cho mỗi kết nối trong mọi trường hợp.

Nếu join buffer quá nhỏ so với tập dữ liệu được xử lý, truy vấn có thể phải xử lý theo nhiều batch và chậm hơn. Tăng buffer có thể giúp một số truy vấn, nhưng join buffer lớn không sửa được index thiếu, điều kiện nối không chọn lọc hoặc thiết kế schema chưa phù hợp.

### 5.2. Kiểm tra join có vấn đề

Các status variable có thể giúp tìm dấu hiệu:

- Select_full_join: số join không dùng index.
- Select_range_check: số join mà optimizer phải kiểm tra range index theo từng hàng.

Đây là counter tích lũy. Xem delta theo thời gian, sau đó tìm digest truy vấn tương ứng trong Performance Schema.

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Select_full_join',
  'Select_range_check'
);

SELECT
  DIGEST_TEXT,
  COUNT_STAR,
  SUM_SELECT_FULL_JOIN,
  SUM_SELECT_RANGE_CHECK,
  SUM_ROWS_EXAMINED,
  SUM_TIMER_WAIT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_SELECT_FULL_JOIN DESC, SUM_ROWS_EXAMINED DESC
LIMIT 20;
~~~

Nếu truy vấn dùng join không có index, kiểm tra kiểu dữ liệu hai cột nối, collation, biểu thức hoặc hàm áp dụng lên cột, thứ tự join và index ghép. Kiểu dữ liệu không tương thích có thể khiến optimizer không tận dụng index như mong đợi.

### 5.3. Ví dụ kế hoạch join

~~~sql
EXPLAIN FORMAT=TREE
SELECT
  c.customer_id,
  c.segment,
  o.order_id,
  o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_code = c.customer_code
WHERE c.segment = 'business'
  AND o.created_at >= '2026-01-01';
~~~

Nếu hai bảng lớn và cột customer_code ở orders không có index phù hợp, optimizer có thể phải dùng hash join hoặc kế hoạch scan tốn kém. Hãy xem số hàng ước tính/thực tế, điều kiện lọc và access path trước khi tăng join_buffer_size.

Một index ứng viên có thể là:

~~~sql
CREATE INDEX ix_orders_customer_code_created_at
  ON orders (customer_code, created_at);
~~~

Index trên chỉ là ví dụ. Chọn thứ tự cột theo điều kiện truy vấn, tính chọn lọc, workload ghi và các truy vấn khác. Dùng EXPLAIN để xác nhận optimizer thực sự chọn index; không tạo index chỉ dựa trên một truy vấn giả định.

## 6. Những bộ đệm theo session khác

sort_buffer_size và join_buffer_size chỉ là một phần trong bộ nhớ làm việc của truy vấn.

### 6.1. read_buffer_size

read_buffer_size cung cấp bộ đệm cho một số table scan tuần tự. Mỗi session thực hiện scan có thể cần vùng nhớ này. Tăng nó có thể giúp một số scan tuần tự lớn, nhưng scan không cần thiết thường là vấn đề cần xử lý bằng index hoặc lọc dữ liệu sớm.

### 6.2. read_rnd_buffer_size

read_rnd_buffer_size được dùng trong một số trường hợp đọc hàng theo thứ tự sau khi sort. Giá trị lớn có thể giúp workload đọc ngẫu nhiên theo thứ tự sort, nhưng cũng làm tăng chi phí bộ nhớ khi nhiều phiên đồng thời thực hiện thao tác tương ứng.

### 6.3. thread_stack

thread_stack quy định stack cho mỗi thread. Đây là bộ nhớ nền cần tính khi ước lượng thread đồng thời. Tăng stack chỉ khi có bằng chứng về nhu cầu call stack hoặc lỗi stack overflow; đặt quá cao nhân theo số thread có thể tốn RAM đáng kể.

### 6.4. net_buffer_length và max_allowed_packet

net_buffer_length là kích thước khởi đầu của communication buffer. Buffer có thể tăng khi cần truyền message lớn, đến giới hạn max_allowed_packet. max_allowed_packet là giới hạn packet, không có nghĩa mỗi kết nối lập tức cấp phát toàn bộ dung lượng đó.

Khi ứng dụng truyền BLOB, JSON hoặc câu lệnh lớn, hãy xem kích thước payload, số client đồng thời và lỗi packet. Không nâng max_allowed_packet lên rất lớn nếu ứng dụng không cần; đồng thời không coi nó là biến dự báo chính xác RAM được cấp phát.

### 6.5. Internal temporary table

GROUP BY, DISTINCT, UNION và một số truy vấn trung gian có thể tạo internal temporary table. Giới hạn và đường đi lưu trữ phụ thuộc engine và phiên bản:

- tmp_table_size và max_heap_table_size liên quan đến giới hạn của một số temporary table trong bộ nhớ.
- MySQL 8.0 sử dụng TempTable engine cho nhiều internal temporary table; temptable_max_ram và các biến liên quan có thể chi phối ngân sách TempTable ở cấp server.
- Temporary table vượt giới hạn bộ nhớ có thể được chuyển sang dạng lưu trữ khác hoặc sử dụng tài nguyên tạm trên đĩa, tùy phiên bản và loại dữ liệu.

Không áp dụng một công thức chung cho mọi bảng tạm. Đọc tài liệu internal temporary tables của phiên bản cụ thể và theo dõi Created_tmp_tables, Created_tmp_disk_tables cùng metric TempTable nếu exporter hỗ trợ.

### 6.6. binlog_cache_size

Khi binary logging được bật, transaction có thể dùng binlog cache để lưu sự kiện trước commit. Transaction lớn có thể vượt bộ đệm ban đầu và dùng file tạm. Theo dõi Binlog_cache_use và Binlog_cache_disk_use để biết mức độ sử dụng cache và spill. Đây là một nhóm bộ nhớ/đệm theo transaction, không phải lý do để tăng sort hoặc join buffer.

## 7. Bộ nhớ toàn cục và bộ nhớ ngoài MySQL

Ngân sách server còn phải tính các vùng dùng chung:

- innodb_buffer_pool_size: vùng cache dữ liệu và index lớn nhất trong nhiều hệ thống InnoDB.
- innodb_log_buffer_size: vùng đệm redo log.
- key_buffer_size: cache index của MyISAM.
- table_open_cache và table_definition_cache: cache metadata và table handle.
- Performance Schema: bộ nhớ cho instrumentation, history và summary.
- Bộ nhớ dictionary, connection manager, replication, plugin và các cấu trúc nội bộ khác.

Ngoài mysqld, host còn cần RAM cho kernel, filesystem cache, agent giám sát, backup, proxy, sidecar và các tiến trình khác. Trong container, giới hạn cgroup có thể thấp hơn RAM vật lý của máy. Một process có thể bị OOM kill dù host vẫn còn RAM nếu container chạm memory.max.

Không dùng RSS của mysqld làm đồng nghĩa chính xác với tổng dung lượng logic từng biến. RSS, virtual memory, page cache, shared memory và bộ nhớ được instrument có cách tính khác nhau. Hãy đối chiếu nhiều nguồn.

## 8. Lập ngân sách bộ nhớ theo mức đồng thời

Một mô hình ước lượng đơn giản:

~~~text
M_peak ≈ M_global
       + N_threads × M_base_thread
       + N_active_sorts × sort_buffer_size
       + N_active_join_buffers × join_buffer_size
       + M_internal_temp_tables
       + M_other
~~~

Trong đó:

- M_global là bộ nhớ dùng chung của MySQL.
- N_threads là số thread cần tính tại thời điểm tải cao; có thể gần số kết nối hoạt động nhưng không luôn bằng max_connections.
- M_base_thread là bộ nhớ nền của thread/session, gồm stack và phần connection buffer thực tế.
- N_active_sorts là số sort đang chạy đồng thời, không phải tổng số kết nối.
- N_active_join_buffers là số join buffer thực tế đang được giữ bởi các phép join đang chạy; một truy vấn có thể cần nhiều hơn một buffer.
- M_internal_temp_tables là tổng bộ nhớ của các temporary table và cấu trúc trung gian đang tồn tại.
- M_other gồm allocator overhead, plugin, replication, bộ nhớ không được instrument và các thành phần khác.

Đây là mô hình để đặt câu hỏi và tạo headroom, không phải giới hạn cứng của MySQL. Các thành phần có thể được cấp phát theo điều kiện, được tái sử dụng hoặc chồng lấp theo cách không thể suy ra chính xác chỉ từ giá trị cấu hình.

### 8.1. Vì sao max_connections không phải số nhân cho mọi buffer

Phép tính max_connections × sort_buffer_size × join_buffer_size thường sai vì:

1. Kết nối idle không chạy sort hoặc join.
2. Không phải mọi truy vấn đều cần cùng loại buffer.
3. Một số buffer được cấp phát khi thao tác bắt đầu, không phải lúc connect.
4. Một truy vấn có thể tạo nhiều thao tác/buffer; một truy vấn khác không cần buffer đó.
5. Một số giới hạn áp dụng cho temporary table hoặc engine ở phạm vi khác.
6. max_connections là trần số kết nối được phép, không phải dự báo số thao tác đồng thời.

Tuy vậy, dùng max_connections để đánh giá tình huống xấu nhất vẫn có ích nếu mô hình giả định rõ rằng nhiều phiên cùng hoạt động. Không được xem phép tính đó là lượng RAM chắc chắn sẽ cấp phát hoặc là mức tiêu thụ thực tế.

### 8.2. Ví dụ ngân sách minh họa

Giả sử một instance có buffer pool 12 GiB và các vùng global khác được đo khoảng 2 GiB. Trong giờ cao điểm, quan sát thấy:

- 80 thread hoạt động hoặc giữ session resources.
- 20 sort đang chạy đồng thời, với sort buffer 2 MiB.
- 35 join buffer đang được sử dụng, với join buffer 1 MiB.
- Temporary table và cấu trúc trung gian đang dùng khoảng 1 GiB.
- Các vùng khác, allocator overhead và bộ nhớ chưa phân loại cần dự phòng 2 GiB.

Ước lượng phần được liệt kê:

| Thành phần | Ước lượng |
|---|---:|
| Buffer pool | 12 GiB |
| Global memory khác | 2 GiB |
| Sort buffers: 20 × 2 MiB | 40 MiB |
| Join buffers: 35 × 1 MiB | 35 MiB |
| Temporary tables | 1 GiB |
| Headroom cho phần khác | 2 GiB |

Ví dụ này chưa tính chi tiết bộ nhớ nền của 80 thread; phải đo và bổ sung vào M_base_thread. Số 20 sort và 35 join buffer là số thao tác đồng thời giả định từ quan sát, không phải 80 kết nối đều dùng buffer. Nếu nâng sort buffer lên 16 MiB, riêng 20 sort đồng thời sẽ cần khoảng 320 MiB thay vì 40 MiB. Tác động tăng theo concurrency.

### 8.3. Dự phòng và headroom

Không lập ngân sách sát đúng mức RAM vật lý. Cần headroom cho burst, transaction lớn, backup, replication catch-up, restart và cache warm-up. Với container, giữ khoảng dự phòng dưới memory.max để tránh OOM kill. Với host dùng chung, dành RAM cho kernel và các process khác.

Hãy mô hình hóa ít nhất ba kịch bản:

- Bình thường: concurrency và query mix thường gặp.
- Cao điểm: số sort/join/temporary table đồng thời tăng.
- Sự cố hoặc failover: tải dồn lên primary hoặc node còn sống.

## 9. Đo bộ nhớ bằng Performance Schema và sys schema

Performance Schema có các bảng memory summary khi instrumentation tương ứng được hỗ trợ và bật. Các số liệu này giúp xem phần bộ nhớ đã được instrument, không nhất thiết bao phủ mọi allocation của process.

Kiểm tra instrument memory:

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'memory/%'
ORDER BY NAME
LIMIT 50;
~~~

Tổng hợp theo event:

~~~sql
SELECT
  EVENT_NAME,
  CURRENT_NUMBER_OF_BYTES_USED,
  HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
~~~

Xem theo thread và liên kết với thông tin phiên:

~~~sql
SELECT
  t.PROCESSLIST_ID,
  t.PROCESSLIST_USER,
  t.PROCESSLIST_HOST,
  m.EVENT_NAME,
  m.CURRENT_NUMBER_OF_BYTES_USED,
  m.HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_by_thread_by_event_name AS m
JOIN performance_schema.threads AS t
  ON t.THREAD_ID = m.THREAD_ID
WHERE m.CURRENT_NUMBER_OF_BYTES_USED > 0
ORDER BY m.CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 30;
~~~

sys schema có các view thuận tiện như sys.memory_global_by_current_bytes, sys.memory_global_total và sys.memory_by_thread_by_current_bytes. Ví dụ:

~~~sql
SELECT *
FROM sys.memory_by_thread_by_current_bytes
ORDER BY current_allocated DESC
LIMIT 20;
~~~

Tên cột của view có thể khác giữa phiên bản sys schema. Kiểm tra DESCRIBE hoặc định nghĩa view trên server nếu truy vấn mẫu không khớp.

### 9.1. Giới hạn của số liệu instrument

Performance Schema chỉ báo cáo allocation thuộc các instrument được hỗ trợ và đang bật. Nếu instrument memory tắt hoặc một thư viện cấp phát ngoài cơ chế instrument, số liệu có thể thấp hơn RSS của process. Không kết luận MySQL không dùng RAM chỉ vì summary trống.

Khi bật instrument để điều tra, ghi lại trạng thái ban đầu, bật đúng nhóm cần thiết, đo overhead và khôi phục cấu hình theo quy trình. Không bật hàng loạt instrument trên production chỉ để thử nếu chưa đánh giá chi phí.

## 10. Đọc status và gắn với truy vấn

Để xem các chỉ số sort/join:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_scan',
  'Sort_range',
  'Sort_merge_passes',
  'Select_full_join',
  'Select_range_check',
  'Created_tmp_tables',
  'Created_tmp_disk_tables',
  'Threads_connected',
  'Threads_running'
);
~~~

Performance Schema digest giúp tìm nhóm truy vấn có sort hoặc full join:

~~~sql
SELECT
  DIGEST_TEXT,
  COUNT_STAR,
  SUM_SORT_ROWS,
  SUM_SORT_MERGE_PASSES,
  SUM_SELECT_FULL_JOIN,
  SUM_ROWS_EXAMINED,
  SUM_TIMER_WAIT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_SORT_MERGE_PASSES DESC, SUM_SELECT_FULL_JOIN DESC
LIMIT 20;
~~~

Các summary có thể reset khi server restart hoặc khi summary bị truncate/reset. Chúng thường tổng hợp từ lúc khởi động hoặc từ lần reset gần nhất; hãy lưu mốc thời gian khi so sánh. Không biến DIGEST_TEXT thành label của metric có cardinality cao; dùng query trực tiếp trong Performance Schema hoặc công cụ log để điều tra.

## 11. Tìm nguyên nhân trước khi tăng buffer

Khi thấy sort hoặc join chậm, thực hiện theo trình tự:

1. Xác định truy vấn/digest và tần suất chạy.
2. Đọc EXPLAIN hoặc EXPLAIN FORMAT=TREE; dùng EXPLAIN ANALYZE trên môi trường phù hợp để đo hàng thực tế.
3. Kiểm tra index, điều kiện nối, kiểu dữ liệu, collation và biểu thức trên cột.
4. Xem số hàng được đọc, sort, join, temporary table và rows examined.
5. Đo Sort_merge_passes, Select_full_join và latency trước/sau trên cùng workload.
6. Chỉ thử thay đổi session buffer nếu có giả thuyết rằng buffer là nút thắt.
7. Đo thời gian, memory peak, disk I/O và tác động đến truy vấn đồng thời.

Một truy vấn full scan trên bảng rất lớn có thể chậm dù join buffer tăng nhiều lần. Một truy vấn ORDER BY trả về hàng triệu hàng có thể cần thiết kế lại phân trang hoặc index. Sửa access path thường bền vững hơn việc tăng bộ nhớ.

## 12. Phạm vi SESSION và GLOBAL

sort_buffer_size, join_buffer_size và nhiều biến buffer có phạm vi GLOBAL và SESSION. Giá trị GLOBAL là mặc định cho các session mới; thay đổi GLOBAL không nhất thiết thay đổi giá trị SESSION đã được tạo trong các kết nối đang tồn tại. Giá trị SESSION tác động đến kết nối hiện tại.

Kiểm tra cả hai phạm vi:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'sort_buffer_size',
  'join_buffer_size',
  'read_buffer_size',
  'read_rnd_buffer_size',
  'thread_stack',
  'net_buffer_length',
  'max_allowed_packet',
  'tmp_table_size',
  'max_heap_table_size'
);

SHOW SESSION VARIABLES
WHERE Variable_name IN (
  'sort_buffer_size',
  'join_buffer_size',
  'read_buffer_size',
  'read_rnd_buffer_size'
);
~~~

Thử nghiệm trong một session:

~~~sql
SET SESSION sort_buffer_size = 2 * 1024 * 1024;
SET SESSION join_buffer_size = 2 * 1024 * 1024;

SELECT @@SESSION.sort_buffer_size,
       @@SESSION.join_buffer_size;
~~~

Giá trị 2 MiB chỉ là ví dụ trong lab, không phải khuyến nghị production. So sánh kết quả với session gốc và ghi nhận mức dùng RAM. Khi kết thúc, đóng session hoặc khôi phục giá trị ban đầu.

SET GLOBAL thay đổi mặc định cho session mới và có thể yêu cầu quyền quản trị phù hợp. SET PERSIST có thể ghi thay đổi vào cấu hình lưu bền qua restart trên phiên bản hỗ trợ. Thay đổi toàn cục cần qua review, kiểm tra khả năng rollback và đánh giá tác động đồng thời. Không chạy SET GLOBAL/SET PERSIST trên production chỉ để thử một truy vấn.

## 13. Thử nghiệm sort buffer trong một session

Tạo dữ liệu kiểm thử có kích thước vừa đủ trên môi trường lab. Truy vấn có thể buộc filesort:

~~~sql
EXPLAIN
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-01-01'
ORDER BY total_amount DESC
LIMIT 1000;
~~~

Ghi nhận SESSION status trước khi chạy:

~~~sql
SHOW SESSION STATUS
WHERE Variable_name IN (
  'Sort_rows',
  'Sort_merge_passes'
);
~~~

Chạy truy vấn, ghi lại thời gian và status sau đó. Lặp lại với sort_buffer_size ở mức ban đầu và một mức thử nghiệm có kiểm soát. Giữ nguyên dữ liệu, cache state và tải nền càng nhiều càng tốt. So sánh:

- Thời gian thực thi.
- Sort_merge_passes và Sort_rows.
- Rows examined và số hàng trả về.
- RAM của process hoặc session instrumentation nếu có.
- Ảnh hưởng đến các truy vấn khác khi có concurrency.

Nếu merge pass giảm nhưng latency không cải thiện, nút thắt có thể nằm ở I/O, scan hoặc CPU. Nếu truy vấn nhanh hơn riêng lẻ nhưng server thiếu RAM khi chạy đồng thời, thay đổi không phù hợp với production.

## 14. Thử nghiệm join buffer trong một session

Chọn truy vấn join trên dữ liệu lab. Đọc EXPLAIN FORMAT=TREE để biết optimizer dùng nested loop, hash join hay access path khác:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
  a.code,
  a.description,
  b.amount
FROM source_a AS a
JOIN source_b AS b
  ON b.code = a.code
WHERE a.category = 'active';
~~~

Nếu truy vấn cần join buffer, ghi nhận thời gian, số hàng đọc, actual rows, memory và kế hoạch. Thử thay đổi join_buffer_size ở SESSION trong một phiên riêng rồi chạy lại cùng điều kiện.

Sau đó thử một index phù hợp với điều kiện join trên bảng bên trong, nếu dữ liệu và nghiệp vụ cho phép. So sánh:

- Kế hoạch join trước và sau.
- Số hàng scan và rows examined.
- Latency và I/O.
- Bộ nhớ đồng thời.
- Chi phí ghi và dung lượng index mới.

Mục tiêu là hiểu vì sao optimizer chọn thuật toán và buffer ảnh hưởng thế nào. Không mặc định hash join hoặc join buffer luôn nhanh hơn index lookup.

## 15. Chọn cách tiếp cận theo workload

| Workload | Hướng quan sát | Cách điều chỉnh |
|---|---|---|
| OLTP nhiều kết nối | Connection concurrency, latency, memory peak, pool wait | Giữ buffer vừa phải; ưu tiên index và truy vấn ngắn |
| Báo cáo lớn | Sort rows, merge passes, temporary table, scan | Thử session buffer cho job riêng; tối ưu lọc, grouping và phân trang |
| ETL/batch | Batch concurrency, packet size, binlog cache, temporary table | Giới hạn số job đồng thời; đo theo batch và transaction |
| Join dữ liệu lớn | Full join, hash join, rows examined, index | Kiểm tra access path, thống kê và index trước khi tăng join buffer |
| Container có memory limit | cgroup memory, OOM events, RSS và headroom | Lập ngân sách theo giới hạn container, không theo RAM host |

Một instance OLTP thường ưu tiên ổn định khi có nhiều kết nối cùng lúc. Một truy vấn báo cáo đặc biệt có thể cần nhiều bộ nhớ nhưng nên chạy với concurrency được kiểm soát hoặc trên replica phân tích. Tách workload thường dễ quản lý hơn việc đặt buffer toàn cục rất lớn cho mọi phiên.

## 16. Cảnh báo và theo dõi vận hành

Không có một metric duy nhất cho biết sort_buffer_size hoặc join_buffer_size đang gây thiếu RAM. Theo dõi kết hợp:

- Số thread và kết nối đồng thời.
- RSS/working set của mysqld, memory.current và memory.max nếu chạy container.
- Available memory, swap, major page faults và OOM events của hệ điều hành.
- Sort_merge_passes, Select_full_join và Created_tmp_disk_tables theo tốc độ tăng.
- Performance Schema memory current/high water mark theo event và thread.
- Query latency, rows examined, disk I/O và số job báo cáo đang chạy.

Đặt cảnh báo theo triệu chứng: memory headroom thấp kéo dài, OOM kill, swap tăng, latency tăng hoặc số temporary table disk spill tăng đồng thời với tác động dịch vụ. Một counter tăng đơn lẻ có thể là hành vi bình thường của workload.

Khi xây dashboard, dùng nhãn ổn định như environment, cluster, instance và role. Tránh tạo một time series cho mỗi connection ID hoặc SQL literal. Chi tiết phiên và digest nên được truy vấn từ Performance Schema hoặc log khi điều tra.

## 17. Các lỗi cấu hình thường gặp

### 17.1. Tăng sort_buffer_size toàn cục để sửa một báo cáo

Nếu nhiều session đồng thời sort, tổng bộ nhớ tăng theo số thao tác đang chạy. Hãy thử SESSION trên một kết nối, đo peak memory và cân nhắc giới hạn concurrency của báo cáo.

### 17.2. Tăng join_buffer_size để che index thiếu

Một join lớn không có access path tốt vẫn phải xử lý nhiều hàng. Kiểm tra kiểu dữ liệu, index, thứ tự join và EXPLAIN trước khi tăng buffer.

### 17.3. Lấy max_connections nhân mọi buffer

Đây là ước lượng bảo thủ nhưng dễ sai nếu xem như mức cấp phát thực tế. Hãy mô hình hóa số sort, join, scan và temporary table đồng thời; đồng thời vẫn thử kịch bản burst có nhiều phiên cùng hoạt động.

### 17.4. Chỉ nhìn RSS hoặc chỉ nhìn Performance Schema

RSS có thể gồm allocator arena, page được giữ lại và các vùng không thuộc instrument. Performance Schema có thể bỏ sót allocation chưa được instrument. Dùng cả số liệu MySQL và OS để giải thích chênh lệch.

### 17.5. Bỏ qua giới hạn container

MySQL có thể bị OOM kill khi chạm memory cgroup dù máy chủ vật lý còn RAM. Lập ngân sách theo giới hạn thực tế của process/container và dành headroom cho sidecar, agent cùng page cache.

## 18. Runbook khi MySQL tăng bộ nhớ bất thường

1. Xác định instance, role, thời điểm bắt đầu và mức ảnh hưởng đến ứng dụng.
2. Kiểm tra RAM khả dụng, swap, OOM log, cgroup limit và RSS/working set của mysqld.
3. Kiểm tra Threads_connected, Threads_running, số truy vấn chạy và pool của ứng dụng.
4. Xem Performance Schema memory summary theo event và thread; xác minh instrument đang bật.
5. Xem statement digest, Sort_merge_passes, Select_full_join và temporary table.
6. Kiểm tra deploy, batch job, báo cáo mới, transaction lớn hoặc thay đổi cấu hình gần đây.
7. Thu thập EXPLAIN/EXPLAIN ANALYZE phù hợp và xác định truy vấn gây sort/join/scan lớn.
8. Giảm concurrency hoặc tạm dừng job theo runbook nếu có nguy cơ OOM; tránh restart vội khi chưa thu thập bằng chứng.
9. Thử tối ưu index/truy vấn hoặc giới hạn SESSION cho job cụ thể.
10. Theo dõi memory peak, latency và error rate sau thay đổi; ghi lại cấu hình và rollback plan.

Nếu server đang sát OOM, ưu tiên giảm tải có kiểm soát và bảo vệ khả năng phục vụ. Không thay đổi đồng thời nhiều biến bộ nhớ vì sẽ khó xác định thay đổi nào tạo ra tác động.

## 19. Bài tập tự kiểm tra

1. Vì sao một server có 500 kết nối idle không nhất thiết đã cấp phát 500 sort buffer?
2. Một truy vấn có ba phép join cần join buffer. Vì sao mô hình một join_buffer_size cho mỗi kết nối có thể đánh giá thấp bộ nhớ?
3. EXPLAIN hiển thị filesort. Điều đó có chứng minh dữ liệu đã được sort hoàn toàn trên đĩa không?
4. Sort_merge_passes tăng nhanh nhưng latency ổn định. Bạn sẽ kiểm tra thêm những metric nào?
5. Một truy vấn dùng hash join. Bạn sẽ xác minh vai trò join_buffer_size và memory peak bằng cách nào?
6. Vì sao tăng max_allowed_packet không đồng nghĩa mỗi session lập tức cấp phát từng ấy RAM?
7. Hãy lập ngân sách bộ nhớ cho 100 thread, trong đó 15 sort và 20 join buffer hoạt động đồng thời.
8. Nếu Performance Schema memory summary thấp hơn RSS của mysqld, những nguyên nhân nào có thể giải thích chênh lệch?
9. Khi nào nên dùng SET SESSION thay vì SET GLOBAL?
10. Một container bị OOM kill dù host còn RAM. Bạn sẽ kiểm tra memory.max, memory.current và headroom ra sao?

## 20. Checklist trước khi thay đổi buffer

- [ ] Xác định truy vấn hoặc workload thực sự cần sort/join buffer.
- [ ] Đọc EXPLAIN hoặc EXPLAIN ANALYZE và kiểm tra index/access path.
- [ ] Đo concurrency và số thao tác buffer đang hoạt động.
- [ ] Ghi lại giá trị SESSION và GLOBAL hiện tại.
- [ ] Xác minh đơn vị, phạm vi và hành vi của biến trên phiên bản MySQL đang dùng.
- [ ] Thử thay đổi SESSION trước và so sánh cùng một workload.
- [ ] Đo latency, rows examined, merge pass, I/O và memory peak.
- [ ] Tính headroom cho burst, failover và giới hạn container.
- [ ] Có kế hoạch rollback và người chịu trách nhiệm thay đổi.
- [ ] Chỉ áp dụng GLOBAL/PERSIST sau khi có bằng chứng từ thử nghiệm.

## 21. Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Server System Variables](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)
- [MySQL 8.4 Reference Manual — Optimizing Server Parameters](https://dev.mysql.com/doc/refman/8.4/en/optimization-server-parameters.html)
- [MySQL 8.4 Reference Manual — ORDER BY Optimization](https://dev.mysql.com/doc/refman/8.4/en/order-by-optimization.html)
- [MySQL 8.4 Reference Manual — Nested-Loop Joins](https://dev.mysql.com/doc/refman/8.4/en/nested-loop-joins.html)
- [MySQL 8.4 Reference Manual — Hash Joins](https://dev.mysql.com/doc/refman/8.4/en/hash-joins.html)
- [MySQL 8.4 Reference Manual — Performance Schema Memory Summary Tables](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-memory-summary-tables.html)
- [MySQL 8.4 Reference Manual — Internal Temporary Tables](https://dev.mysql.com/doc/refman/8.4/en/internal-temporary-tables.html)
- [MySQL 8.4 Reference Manual — Connection Interfaces](https://dev.mysql.com/doc/refman/8.4/en/connection-interfaces.html)

Tên biến, thuật toán optimizer và mức độ instrumentation có thể thay đổi theo phiên bản. Dùng tài liệu khớp với server đang chạy và kiểm tra kế hoạch thực thi thực tế trước khi thay đổi cấu hình.
