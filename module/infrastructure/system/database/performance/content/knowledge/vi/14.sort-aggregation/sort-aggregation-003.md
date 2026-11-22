# Bộ nhớ sắp xếp, dữ liệu tạm và dấu hiệu tràn xuống đĩa

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích cách bộ máy cơ sở dữ liệu cấp phát bộ nhớ cho thao tác sắp xếp, nhóm dữ liệu và các toán tử cần vùng làm việc.
- Phân biệt dữ liệu tạm được tạo theo thiết kế với hiện tượng một thao tác tràn dữ liệu trung gian từ RAM xuống đĩa (spill).
- Nhận diện dấu hiệu sort hoặc hash spill qua execution plan, thống kê, log và hoạt động I/O.
- Xác định nguyên nhân như ước lượng cardinality sai, dữ liệu trung gian quá lớn, hàng rộng, thiếu chỉ mục hoặc áp lực đồng thời.
- Chọn biện pháp giảm bộ nhớ và I/O tạm mà không gây quá tải RAM khi nhiều truy vấn chạy cùng lúc.

## 1. Vì sao sắp xếp cần bộ nhớ?

Các truy vấn cơ sở dữ liệu thường cần sắp xếp kết quả cho `ORDER BY`, phân trang, xếp hạng, loại trùng hoặc phục vụ một số kiểu JOIN và phép tổng hợp. Bộ máy có thể phải giữ các khóa sắp xếp cùng thông tin hàng trong một vùng làm việc để so sánh và đổi vị trí dữ liệu.

Ví dụ:

```sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC;
```

Nếu đường truy cập đã cung cấp hàng theo đúng thứ tự `created_at DESC`, hệ quản trị có thể đọc theo thứ tự chỉ mục và tránh một bước sort riêng. Nếu không có đường truy cập phù hợp, hệ quản trị thường phải lấy các hàng thỏa điều kiện rồi sắp xếp chúng.

Bộ nhớ sắp xếp (sort memory hoặc sort workspace) là phần bộ nhớ dành cho thao tác đó. Nó chứa dữ liệu hoặc cấu trúc đại diện cho dữ liệu cần sắp. Kích thước cần dùng phụ thuộc vào:

- Số hàng đầu vào.
- Độ rộng hàng hoặc kích thước khóa sắp xếp và con trỏ đến hàng.
- Số cột và biểu thức dùng để sắp xếp.
- Thuật toán được chọn, chẳng hạn full sort hay top-N sort.
- Số thao tác sort/hash chạy đồng thời và cách hệ quản trị cấp phát bộ nhớ.

Khi tập dữ liệu trung gian vừa với ngân sách bộ nhớ, thao tác có thể hoàn tất trong RAM. Khi vượt ngân sách, hệ quản trị có thể ghi các phần dữ liệu đã xử lý ra vùng lưu trữ tạm rồi đọc lại để tiếp tục.

## 2. Dữ liệu tạm và spill là hai khái niệm khác nhau

Dữ liệu tạm (temporary data) là dữ liệu trung gian được tạo trong lúc thực thi truy vấn. Nó có thể được dùng cho sort, hash, materialization, bảng tạm nội bộ, window function hoặc các bước xử lý khác.

Spill (tràn xuống đĩa) xảy ra khi một toán tử cần nhiều bộ nhớ hơn phần được cấp hoặc phần có thể sử dụng, nên phải chuyển một phần dữ liệu trung gian sang vùng lưu trữ tạm. Tùy hệ quản trị, dữ liệu này có thể nằm trong file tạm, temporary tablespace hoặc `tempdb`.

Không phải mọi lần dùng dữ liệu tạm đều là sự cố:

- Một truy vấn có thể chủ động tạo bảng tạm hoặc materialize một tập kết quả theo thiết kế.
- Một sort lớn có thể dùng external merge sort như cách thực thi hợp lệ khi tập dữ liệu không vừa RAM.
- Một hash join hoặc hash aggregate có thể chia dữ liệu thành nhiều batch và xử lý lần lượt.
- Một số truy vấn cần file tạm ngay cả khi máy chủ còn nhiều RAM, do giới hạn memory grant, cấu hình vùng làm việc hoặc áp lực đồng thời.

Điều cần điều tra là dữ liệu tạm có tạo ra độ trễ, I/O, dung lượng hoặc cạnh tranh tài nguyên vượt mục tiêu hay không. Việc thấy có file tạm không đủ để kết luận truy vấn được tối ưu kém.

## 3. External sort hoạt động như thế nào?

Khi dữ liệu không vừa vùng nhớ, thuật toán external sort thường chia dữ liệu thành các phần:

1. Đọc một phần dữ liệu vào RAM và sắp xếp phần đó.
2. Ghi phần đã sắp xếp thành một run (chuỗi đã sắp) vào file tạm.
3. Lặp lại cho đến khi toàn bộ đầu vào được chuyển thành các run.
4. Đọc các run và trộn chúng theo thứ tự, có thể qua nhiều lượt merge.
5. Trả kết quả theo thứ tự yêu cầu và giải phóng dữ liệu tạm.

```text
Dữ liệu đầu vào
      |
      v
Chia thành các phần vừa bộ nhớ
      |
      v
Sắp xếp từng phần trong RAM
      |
      v
Ghi các sorted runs vào file tạm
      |
      v
Trộn các runs theo thứ tự
      |
      v
Kết quả đã sắp xếp
```

External sort giúp xử lý tập dữ liệu lớn hơn RAM nhưng phải trả thêm chi phí ghi và đọc file tạm, điều phối merge và có thể nhiều lượt I/O. Nếu storage tạm chậm hoặc nhiều truy vấn cùng spill, độ trễ có thể tăng mạnh.

### Full sort và top-N sort

Với `ORDER BY` không giới hạn, hệ quản trị có thể cần sắp xếp toàn bộ tập kết quả. Nếu truy vấn có `LIMIT`, hệ quản trị có thể chọn thuật toán top-N chỉ giữ các ứng viên tốt nhất trong bộ nhớ thay vì lưu toàn bộ thứ tự.

Ví dụ:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 4201
ORDER BY created_at DESC
LIMIT 20;
```

Top-N có thể giảm bộ nhớ và công việc sort, nhưng hệ thống vẫn có thể phải đọc nhiều hàng để xác định 20 hàng mới nhất nếu không có chỉ mục phù hợp. Chỉ mục `(customer_id, created_at DESC)` có thể cho phép đọc đúng vùng dữ liệu theo thứ tự và dừng sớm.

## 4. Bộ nhớ cho GROUP BY, DISTINCT và hash

Sắp xếp không phải toán tử duy nhất cần bộ nhớ. Các truy vấn sau có thể tạo dữ liệu trung gian lớn:

```sql
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;

SELECT DISTINCT customer_id
FROM orders;

SELECT c.customer_id, COUNT(o.order_id)
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Với GROUP BY hoặc DISTINCT, bộ tối ưu có thể chọn:

- **Sort-based aggregation:** sắp xếp theo khóa nhóm, sau đó gom các hàng liên tiếp cùng khóa.
- **Hash aggregation:** dùng bảng băm trong bộ nhớ để tích lũy kết quả theo khóa nhóm.

Hash join cũng cần vùng nhớ để giữ bảng băm của một đầu vào. Nếu số nhóm hoặc kích thước bảng băm vượt ngân sách, hệ quản trị có thể spill, chia batch hoặc dùng chiến lược khác.

Trong execution plan, cần xem cả toán tử sort lẫn hash. Một truy vấn không có `ORDER BY` vẫn có thể tạo spill do `GROUP BY`, `DISTINCT`, hash join, window function hoặc thao tác trung gian.

## 5. Dấu hiệu spill trong execution plan

Execution plan thường là nguồn chẩn đoán trực tiếp nhất. Dấu hiệu hiển thị tùy hệ quản trị và phiên bản.

| Hệ quản trị | Dấu hiệu thường gặp |
| --- | --- |
| PostgreSQL | `Sort Method: external merge` và thông tin `Disk`; buffer/temp read hoặc written; hash có nhiều batch |
| SQL Server | Cảnh báo spill của Sort hoặc Hash Match trong actual execution plan; thông tin memory grant và tempdb usage |
| MySQL | `Sort_merge_passes` tăng; bảng tạm nội bộ trên đĩa tăng; thông tin EXPLAIN/Performance Schema tùy phiên bản |

### PostgreSQL: sort dùng external merge

Chạy truy vấn với `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC;
```

Khi sort không vừa bộ nhớ, phần thông tin của node Sort có thể hiển thị dạng:

```text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: ...
```

`external merge` cho biết thao tác sort đã dùng phương pháp sắp xếp ngoài bộ nhớ; `Disk` cho biết lượng dữ liệu tạm liên quan theo cách báo cáo của phiên bản. Nếu sort hoàn tất trong RAM, có thể thấy `quicksort` hoặc một phương pháp khác cùng lượng bộ nhớ sử dụng. `top-N heapsort` cho thấy hệ thống dùng cách giữ các ứng viên đầu bảng khi có giới hạn phù hợp.

Đối với hash, số batch lớn hơn một có thể cho thấy dữ liệu đã được chia thành nhiều phần thay vì giữ toàn bộ trong một hash table. Hãy đọc thông tin actual plan và temp I/O đi kèm.

### SQL Server: spill warning và memory grant

Trong actual execution plan, mở chi tiết các operator Sort hoặc Hash Match. Tùy phiên bản và công cụ hiển thị, cảnh báo có thể mô tả dữ liệu bị spill sang tempdb, số lượt spill hoặc lượng dữ liệu được ghi/đọc.

Memory grant là vùng nhớ được cấp cho các operator cần bộ nhớ trong một truy vấn. Nếu grant thấp hơn nhu cầu thực tế, sort hoặc hash có thể spill. Nếu grant quá lớn so với nhu cầu, truy vấn giữ bộ nhớ không cần thiết và làm giảm số truy vấn khác có thể chạy đồng thời.

Đừng chỉ nhìn cảnh báo mà bỏ qua bối cảnh: xem requested, granted, used memory, thời gian chờ grant, cardinality ước lượng và actual rows. Một truy vấn có grant nhỏ nhưng xử lý ít hàng có thể hoàn toàn bình thường.

### MySQL: sort merge và bảng tạm trên đĩa

MySQL có thể dùng filesort khi thứ tự kết quả không được cung cấp bởi chỉ mục. Filesort là tên của cơ chế sắp xếp, không tự nó chứng minh có spill ra đĩa. Nếu cần nhiều lượt merge, chỉ số `Sort_merge_passes` có thể tăng.

MySQL cũng có thể tạo internal temporary table cho một số thao tác như GROUP BY, DISTINCT hoặc materialization. Một số bảng tạm có thể được chuyển từ bộ nhớ sang đĩa khi vượt giới hạn hoặc không đáp ứng điều kiện lưu trong RAM.

Do đó cần phân biệt:

- `Using filesort`: có bước sắp xếp do optimizer chọn; không nhất thiết đồng nghĩa đã spill.
- `Sort_merge_passes`: phản ánh số lượt merge của thuật toán sort, hữu ích để theo dõi áp lực sắp xếp.
- `Created_tmp_disk_tables`: đếm bảng tạm nội bộ được tạo trên đĩa theo phạm vi status; không phải bộ đếm riêng cho mọi sort spill.

## 6. Theo dõi temp I/O và thống kê ở cấp hệ thống

Một plan đơn lẻ cho biết một lần thực thi. Để tìm truy vấn gây áp lực thường xuyên, cần kết hợp thống kê theo query fingerprint và theo thời gian.

### PostgreSQL

`pg_stat_database` có các bộ đếm tổng hợp về file tạm và byte tạm theo database. Ví dụ:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes
FROM pg_stat_database
ORDER BY temp_bytes DESC;
```

Đây là bộ đếm tích lũy từ lần reset thống kê gần nhất; nó không chỉ ra một truy vấn duy nhất. Cần so sánh chênh lệch giữa hai thời điểm hoặc đối chiếu với thống kê truy vấn.

Nếu `pg_stat_statements` đã được bật và phiên bản cung cấp các cột tương ứng, có thể xếp hạng truy vấn theo số block tạm:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    temp_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
```

`temp_blks_read` và `temp_blks_written` cho biết block tạm được đọc/ghi ở mức thống kê của câu lệnh. Hãy kết hợp với calls, tổng thời gian và độ trễ trung bình để phân biệt một truy vấn hiếm nhưng rất lớn với truy vấn nhỏ chạy liên tục.

PostgreSQL cũng có tham số `log_temp_files` để ghi log file tạm theo ngưỡng kích thước. Giá trị và cách cấu hình phụ thuộc phiên bản và quyền vận hành; đặt ngưỡng phù hợp giúp điều tra file tạm lớn mà không tạo quá nhiều log.

### SQL Server

Có thể dùng actual execution plan để xem spill, DMV về memory grant để quan sát truy vấn đang xin hoặc giữ bộ nhớ, và thống kê không gian phiên/tác vụ trong tempdb để tìm session tạo nhiều dữ liệu tạm.

Ví dụ kiểm tra các memory grant đang hoạt động:

```sql
SELECT
    session_id,
    request_time,
    grant_time,
    requested_memory_kb,
    granted_memory_kb,
    used_memory_kb,
    max_used_memory_kb,
    wait_time_ms
FROM sys.dm_exec_query_memory_grants
ORDER BY requested_memory_kb DESC;
```

DMV này phản ánh các grant đang hoạt động tại thời điểm truy vấn DMV. Nó không phải lịch sử đầy đủ mọi spill đã xảy ra. Để điều tra lịch sử, có thể dùng Query Store, actual plan được lưu hoặc Extended Events phù hợp với phiên bản, đồng thời xem dung lượng và I/O của tempdb.

### MySQL

Có thể lấy status counters ở phạm vi session hoặc global:

```sql
SHOW GLOBAL STATUS LIKE 'Sort_merge_passes';
SHOW GLOBAL STATUS LIKE 'Created_tmp_disk_tables';
SHOW GLOBAL STATUS LIKE 'Created_tmp_tables';
```

Để hiểu mức tăng do một workload, ghi lại giá trị trước và sau cửa sổ chạy. Global counters có thể bị ảnh hưởng bởi mọi session, vì vậy nếu cần quy trách nhiệm cho truy vấn, hãy kết hợp Performance Schema statement digest và quan sát ở phạm vi session.

## 7. Vì sao sort hoặc hash bị spill?

Spill thường là kết quả của một hoặc nhiều yếu tố:

### Số hàng đầu vào lớn hơn dự kiến

Nếu thống kê cũ hoặc thiếu thông tin, bộ tối ưu có thể ước lượng số hàng quá thấp. Memory grant hoặc chiến lược sort/hash dựa trên ước lượng đó có thể không đủ cho dữ liệu thực tế.

Ví dụ, bộ tối ưu ước lượng một truy vấn chỉ trả về 5.000 đơn hàng nhưng thực tế trả 2 triệu hàng do phân bố trạng thái bị lệch. Sort được cấp phát ít bộ nhớ hơn nhu cầu thực.

### Hàng trung gian quá rộng

Sort có thể cần giữ khóa sắp xếp và phần dữ liệu cần thiết cho kết quả. Nếu truy vấn dùng `SELECT *` và mỗi hàng chứa JSON, văn bản dài hoặc payload lớn, vùng nhớ và file tạm có thể phình to.

Chỉ lấy các cột cần thiết, hoặc tách bước lấy khóa trước rồi truy xuất payload sau khi đã giới hạn số hàng, có thể giảm dữ liệu trung gian. Cần bảo đảm cách viết lại giữ nguyên ngữ nghĩa và không tạo thêm quá nhiều lookup.

### Thiếu đường truy cập có thứ tự

Nếu chỉ mục có thể cung cấp hàng theo thứ tự cần thiết, hệ quản trị có thể tránh sort. Thiếu chỉ mục phù hợp hoặc thứ tự cột không khớp với truy vấn có thể khiến hệ thống phải sort nhiều hàng.

### Cardinality và số nhóm lớn

GROUP BY trên hàng triệu khóa khác nhau có thể cần hash table rất lớn. DISTINCT trên tập có nhiều giá trị duy nhất cũng cần giữ nhiều trạng thái. Khi số nhóm tăng, bộ nhớ cần cho hash aggregate tăng theo.

### Tải đồng thời và giới hạn cấp phát

Mỗi truy vấn có thể có ngân sách bộ nhớ riêng, nhưng tổng bộ nhớ khả dụng của máy chủ vẫn hữu hạn. Nhiều sort/hash chạy đồng thời có thể cạnh tranh bộ nhớ; hệ quản trị phải cấp grant có kiểm soát hoặc dùng spill để bảo vệ hệ thống.

### TEMP storage chậm hoặc bị tranh chấp

Ngay cả khi lượng spill không lớn, file tạm nằm trên thiết bị chậm hoặc cùng thiết bị với dữ liệu chính có thể làm tăng độ trễ. Nhiều truy vấn cùng ghi file tạm cũng tạo hàng đợi I/O và cạnh tranh băng thông.

## 8. Phân biệt spill do thiếu bộ nhớ với kế hoạch kém

Tăng bộ nhớ có thể giảm spill, nhưng không phải lúc nào cũng xử lý đúng nguyên nhân. Hãy phân loại:

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Actual rows cao hơn estimate nhiều lần | Thống kê hoặc cardinality estimate sai | Kiểm tra thống kê, histogram, skew và tương quan cột |
| Sort xử lý rất nhiều hàng dù chỉ cần vài chục hàng đầu | Thiếu index order, filter chưa được đẩy xuống hoặc LIMIT không được tận dụng | Xem access path, composite index và top-N |
| Sort spill nhưng hàng đầu vào rộng | Projection lấy quá nhiều cột hoặc payload lớn | Thu hẹp projection, tách payload, kiểm tra lookup |
| Hash aggregate spill với số nhóm rất lớn | Cardinality nhóm cao | Giảm dữ liệu trước GROUP BY, tổng hợp theo phân vùng hoặc thiết kế lại báo cáo |
| Spill tăng mạnh khi concurrency tăng | Áp lực tổng bộ nhớ hoặc memory grant | Xem số truy vấn đồng thời, grant wait và cấu hình ngân sách |
| Temp I/O cao nhưng plan không có một truy vấn nổi bật | Nhiều truy vấn vừa và nhỏ hoặc workload nền | Tổng hợp theo digest, session và thời gian |

Đừng xem một chỉ số riêng lẻ như `temp_bytes` hoặc `Sort_merge_passes` là bằng chứng đủ để tăng memory. Cần xác định truy vấn, operator, số hàng và chi phí trên workload thực.

## 9. Giảm lượng dữ liệu phải sort hoặc group

Trước khi tăng bộ nhớ, hãy giảm khối lượng công việc cần đưa vào operator.

### Lọc sớm và dùng điều kiện có tính chọn lọc

Đưa điều kiện lọc vào đúng vị trí để hệ quản trị loại hàng sớm. Ví dụ, nếu chỉ cần đơn của một khách hàng trong một khoảng ngày, lọc theo `customer_id` và `created_at` trước khi sort thay vì sort toàn bộ đơn hàng.

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
  AND created_at >= ?
ORDER BY created_at DESC
LIMIT 50;
```

Chỉ mục ghép `(customer_id, created_at DESC)` có thể hỗ trợ lọc và thứ tự. Hiệu quả phụ thuộc phân bố dữ liệu, chiều sort, điều kiện range và hệ quản trị.

### Thu hẹp projection

```sql
-- Tránh mang payload lớn qua bước sort nếu không cần
SELECT order_id, created_at, payload
FROM events
WHERE event_type = 'payment'
ORDER BY created_at DESC
LIMIT 100;

-- Chỉ lấy các cột cần cho danh sách
SELECT order_id, created_at
FROM events
WHERE event_type = 'payment'
ORDER BY created_at DESC
LIMIT 100;
```

Nếu sau đó cần payload, có thể truy xuất theo 100 khóa đã chọn. Cách hai bước chỉ có lợi khi giảm đáng kể lượng dữ liệu rộng phải sort và chi phí lookup bổ sung thấp; hãy đo thay vì mặc định.

### Dùng chỉ mục cung cấp thứ tự

Chỉ mục có thể tránh sort khi thứ tự khóa tương thích với ORDER BY, gồm thứ tự cột, chiều ASC/DESC, NULL ordering và collation. Với truy vấn lọc theo một cột bằng nhau rồi sắp xếp theo cột khác, composite index thường là lựa chọn cần xem xét.

Không tạo chỉ mục chỉ để loại một sort nhỏ. Chỉ mục làm tăng chi phí ghi, dung lượng và bảo trì; nếu truy vấn ít chạy hoặc sort nhỏ vừa RAM, lợi ích có thể không bù chi phí.

### Tận dụng LIMIT và top-N

LIMIT có thể giúp hệ quản trị chọn top-N sort hoặc dừng sớm khi chỉ mục cung cấp thứ tự. Nếu truy vấn có OFFSET rất lớn, hệ thống vẫn phải bỏ qua nhiều hàng. Keyset pagination dựa trên khóa sắp xếp có thể giảm công việc khi phù hợp với ngữ nghĩa phân trang.

### Giảm dữ liệu trước GROUP BY

Nếu nghiệp vụ cho phép, hãy lọc theo thời gian, tenant hoặc trạng thái trước khi nhóm. Có thể tổng hợp dữ liệu theo ngày/tháng hoặc theo partition rồi kết hợp kết quả, nhưng phải giữ đúng độ chính xác của phép tổng hợp và xử lý dữ liệu đến muộn.

## 10. Điều chỉnh bộ nhớ đúng phạm vi

Chỉ sau khi hiểu nguyên nhân và giảm dữ liệu trung gian, mới xem xét điều chỉnh bộ nhớ cho sort/hash. Cần nhớ rằng giới hạn bộ nhớ của một thao tác không đồng nghĩa giới hạn tổng bộ nhớ của toàn máy chủ.

### PostgreSQL: work_mem

`work_mem` là lượng bộ nhớ cơ sở cho một số thao tác nội bộ như sort và hash trước khi phải dùng file tạm. Nó áp dụng theo từng operation, không phải một ngân sách duy nhất cho toàn bộ truy vấn hoặc toàn máy chủ. Một truy vấn có nhiều operator và parallel worker có thể dùng nhiều lần phần ngân sách này.

`hash_mem_multiplier` trong các phiên bản PostgreSQL hỗ trợ điều chỉnh ngân sách hash so với `work_mem`. Cần kiểm tra giá trị và hành vi của phiên bản đang chạy.

Có thể thử tăng `work_mem` cục bộ trong một transaction để đo một truy vấn cụ thể:

```sql
BEGIN;
SET LOCAL work_mem = '128MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC;

COMMIT;
```

`128MB` chỉ là giá trị minh họa, không phải khuyến nghị chung. `SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Tránh tăng `work_mem` toàn cục một cách tùy tiện vì nhiều sort/hash đồng thời có thể nhân tổng mức sử dụng RAM.

### SQL Server: memory grant

SQL Server ước lượng nhu cầu bộ nhớ cho các operator như Sort và Hash, sau đó xin memory grant. Cần xem:

- Requested memory: lượng truy vấn yêu cầu.
- Granted memory: lượng được cấp.
- Used/max used memory: lượng thực tế đã dùng.
- Grant wait: thời gian chờ để được cấp bộ nhớ.
- Spill warning: dấu hiệu operator phải dùng tempdb.

Nếu grant quá nhỏ, sort/hash có thể spill. Nếu grant quá lớn, ít truy vấn khác có thể nhận grant cùng lúc và xuất hiện memory grant wait. Hãy kiểm tra thống kê, cardinality, actual plan, Query Store và các tính năng memory grant feedback nếu phiên bản hỗ trợ trước khi cân nhắc thay đổi cấu hình.

### MySQL: sort buffer và temporary table

`sort_buffer_size` điều khiển vùng đệm sort theo phạm vi kết nối/hoạt động của MySQL. Tăng quá cao ở cấu hình toàn cục có thể tiêu tốn nhiều RAM khi có nhiều session đồng thời.

`tmp_table_size` và các giới hạn liên quan đến internal temporary table ảnh hưởng khả năng giữ bảng tạm trong bộ nhớ; tên tham số, engine và cách kết hợp giới hạn thay đổi theo phiên bản. Trong MySQL 8.0, TempTable engine và `temptable_max_ram` là các yếu tố cần xem xét.

Hãy phân biệt bộ nhớ dùng cho filesort với giới hạn của internal temporary table. Thay đổi một tham số không nhất thiết giải quyết mọi loại spill. Đo status counters và memory theo tải đồng thời trước/sau.

## 11. TEMP storage và quản lý I/O

Khi spill không thể tránh, vùng lưu trữ tạm cần đủ dung lượng và hiệu năng. Cần theo dõi:

- Throughput và latency đọc/ghi trên volume chứa temp files hoặc tempdb.
- Dung lượng tạm cực đại, tốc độ tăng và nguy cơ đầy đĩa.
- Số truy vấn đồng thời tạo dữ liệu tạm.
- Queue depth, IOPS và độ trễ thiết bị.
- Retry, lỗi ghi file tạm và ảnh hưởng tới workload nghiệp vụ.

Đưa temp storage sang thiết bị riêng có thể giảm cạnh tranh với data files hoặc transaction log trong một số kiến trúc, nhưng không tự loại bỏ chi phí spill. Thiết kế cần xét giới hạn IOPS, độ bền, khả năng mở rộng và cách hệ quản trị sử dụng nhiều file hoặc tablespace.

Không xóa file tạm đang được hệ quản trị sử dụng hoặc tự ý di chuyển thư mục temp khi dịch vụ đang chạy. Thay đổi vị trí tempdb, tablespace hoặc temp directory cần theo quy trình vận hành của sản phẩm.

## 12. Đọc các dấu hiệu khác ngoài execution plan

Spill có thể xuất hiện cùng một số tín hiệu:

- Độ trễ p95/p99 tăng khi truy vấn lớn hoặc tải đồng thời tăng.
- Temp read/write tăng cùng lúc với query latency.
- I/O trên volume temp tăng cao dù I/O dữ liệu chính ổn định.
- SQL Server xuất hiện memory grant wait hoặc tempdb contention.
- PostgreSQL tăng `temp_files`/`temp_bytes` hoặc `temp_blks_written`.
- MySQL tăng `Sort_merge_passes` hoặc `Created_tmp_disk_tables`.
- CPU tăng do nhiều lượt sort/merge hoặc hash partition.

Những tín hiệu này cần được đối chiếu theo cùng cửa sổ thời gian. Ví dụ, temp bytes tăng nhưng p95 không đổi có thể chỉ phản ánh báo cáo nền đã được thiết kế để dùng external sort; ngược lại, một lượng temp I/O nhỏ nhưng trên thiết bị có độ trễ cao có thể tác động lớn đến truy vấn.

## 13. Quy trình điều tra một truy vấn bị spill

1. **Chọn query fingerprint.** Xác định truy vấn có spill, số lần gọi, tổng thời gian và mức ảnh hưởng đến người dùng.
2. **Lấy execution plan thực tế.** Xác định operator Sort/Hash nào spill, số hàng thực tế, số batch, dung lượng temp và vị trí trong plan.
3. **So sánh estimate với actual.** Kiểm tra thống kê, histogram, skew, tương quan cột và kiểu tham số.
4. **Đo kích thước dữ liệu trung gian.** Xem số hàng, độ rộng hàng, số cột và cardinality nhóm.
5. **Kiểm tra access path.** Xác định chỉ mục có thể cung cấp thứ tự hoặc lọc sớm hơn không.
6. **Đánh giá concurrency.** Ghi nhận số truy vấn cùng chạy, memory grant, wait và áp lực temp storage.
7. **Thử thay đổi nhỏ.** Thu hẹp projection, thêm điều kiện lọc, điều chỉnh chỉ mục hoặc tăng memory cục bộ trong môi trường thử nghiệm.
8. **Chạy lại workload tương đương.** Giữ dữ liệu, tham số, cache, thời lượng và concurrency phù hợp.
9. **So sánh toàn diện.** Đo p50/p95/p99, throughput, CPU, logical/physical reads, temp I/O, RAM và ảnh hưởng truy vấn khác.
10. **Theo dõi sau triển khai.** Kiểm tra spill, temp storage, memory pressure và plan regression qua các cửa sổ tải.

## 14. Ví dụ thực tế: báo cáo đơn hàng theo khách hàng

Giả sử báo cáo tính tổng doanh thu theo khách hàng cho toàn bộ đơn đã thanh toán:

```sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY revenue DESC;
```

Truy vấn có thể cần đọc nhiều đơn, nhóm theo customer_id rồi sắp xếp các nhóm theo revenue. Ngay cả khi có chỉ mục trên `(status, customer_id)`, thứ tự đầu ra theo giá trị SUM(revenue) vẫn chưa có sẵn trong chỉ mục vì revenue là kết quả tổng hợp.

Để điều tra:

1. Xem plan có HashAggregate hay Sort + GroupAggregate, và node sort nào spill.
2. Kiểm tra số đơn đã thanh toán và số khách hàng thực tế; nếu gần như mọi khách hàng đều có đơn, số nhóm có thể rất lớn.
3. Xem độ rộng hàng trung gian; truy vấn chỉ cần customer_id và total_amount nên không nên mang thêm payload.
4. Kiểm tra thống kê status và phân bố số đơn theo khách hàng.
5. Nếu báo cáo chạy thường xuyên, cân nhắc bảng tổng hợp hoặc materialized view được cập nhật theo quy tắc nhất quán phù hợp.
6. Nếu chỉ cần top 100 khách hàng, thêm `LIMIT 100` có thể giúp giảm công việc sort cuối; phép tổng hợp vẫn cần xử lý đủ dữ liệu đầu vào trừ khi có dữ liệu tổng hợp sẵn hoặc một cách truy cập khác.

Ví dụ này cho thấy thêm chỉ mục không thể loại bỏ mọi sort. Khi thứ tự phụ thuộc kết quả aggregate, có thể cần giảm đầu vào, dùng dữ liệu tổng hợp hoặc thay đổi cách phục vụ báo cáo.

## 15. Những sai lầm thường gặp

- **Tăng bộ nhớ toàn cục ngay khi thấy spill.** Tổng RAM tiêu thụ có thể tăng theo số operator và truy vấn đồng thời, gây áp lực bộ nhớ nghiêm trọng hơn.
- **Coi mọi temporary file là lỗi.** External sort hoặc materialization có thể là cách thực thi hợp lệ; cần đo tác động.
- **Nhầm `Using filesort` với disk spill trong MySQL.** Filesort chỉ nói có bước sắp xếp; cần thêm counters và quan sát phù hợp.
- **Chỉ xem tổng temp bytes.** Bộ đếm tích lũy không chỉ ra query cụ thể; cần lấy chênh lệch theo thời gian và theo fingerprint.
- **Bỏ qua cardinality estimate.** Tăng memory có thể che vấn đề thống kê sai và làm kế hoạch tiếp tục kém hiệu quả.
- **Để `SELECT *` mang payload lớn qua sort.** Dữ liệu trung gian rộng làm tăng bộ nhớ và I/O tạm.
- **Tạo chỉ mục chỉ để tránh một sort nhỏ.** Chi phí ghi và bảo trì có thể lớn hơn lợi ích.
- **Tối ưu một truy vấn mà bỏ qua concurrency.** Một cấu hình tốt khi chạy đơn lẻ có thể làm cạn RAM khi nhiều session cùng chạy.
- **Chỉ đo thời gian elapsed.** Cần xem temp I/O, CPU, memory grant, logical reads và ảnh hưởng đến workload khác.
- **Không kiểm tra kết quả sau khi viết lại.** Thay đổi lọc, phân trang hoặc tổng hợp có thể làm sai ngữ nghĩa dù nhanh hơn.

## 16. Danh sách kiểm tra khi xử lý sort spill

- [ ] Đã xác định query fingerprint và operator gây spill.
- [ ] Có actual rows, estimated rows và kích thước dữ liệu trung gian.
- [ ] Đã kiểm tra độ rộng hàng và projection.
- [ ] Đã xác định sort có thể tránh bằng index order hay không.
- [ ] Đã xem xét top-N, LIMIT hoặc keyset pagination nếu phù hợp.
- [ ] Đã kiểm tra thống kê, skew và cardinality nhóm.
- [ ] Đã phân biệt sort spill, hash spill và internal temporary table.
- [ ] Đã theo dõi temp read/write và hiệu năng thiết bị chứa dữ liệu tạm.
- [ ] Đã đánh giá memory grant/work_mem/sort buffer cùng mức đồng thời.
- [ ] Đã thử thay đổi trong điều kiện có thể tái lập.
- [ ] Đã đo p95/p99, throughput, CPU, RAM, I/O và lỗi trước/sau.
- [ ] Đã xác nhận các truy vấn khác không bị suy giảm do cấp phát bộ nhớ.

## Kết luận

Bộ nhớ sắp xếp và các vùng làm việc cho hash giúp cơ sở dữ liệu xử lý ORDER BY, GROUP BY, DISTINCT và JOIN. Khi dữ liệu trung gian vượt ngân sách, hệ quản trị có thể spill ra file tạm hoặc tempdb, tạo thêm I/O và độ trễ. Hãy nhận diện đúng operator qua execution plan và thống kê, kiểm tra cardinality, độ rộng hàng, access path và mức đồng thời. Ưu tiên giảm số hàng và byte phải xử lý, tận dụng thứ tự từ chỉ mục khi phù hợp, rồi mới điều chỉnh bộ nhớ trong phạm vi có kiểm soát. Kết quả cần được xác nhận bằng workload đại diện, bao gồm độ trễ, throughput, RAM, temp I/O và tác động đến các truy vấn khác.
