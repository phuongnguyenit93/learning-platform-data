# Shared buffers, bộ nhớ riêng của phiên và bộ nhớ hệ điều hành trong PostgreSQL

Khi ứng dụng thực thi một câu lệnh `SELECT`, dữ liệu không phải lúc nào cũng được đọc từ ổ đĩa vật lý. Trang dữ liệu có thể đã nằm trong **shared buffers** của PostgreSQL; nếu không, hệ điều hành có thể vẫn giữ nó trong **OS page cache**. Đồng thời, tiến trình thực thi truy vấn cần vùng bộ nhớ riêng để sắp xếp, kết hợp và tổng hợp dữ liệu. Khi nhu cầu vượt ngân sách bộ nhớ của một thao tác, PostgreSQL có thể sử dụng **temporary files** trên thiết bị lưu trữ.

Ba lớp này phải được phân biệt. Tăng `shared_buffers` không trực tiếp tăng bộ nhớ cho `SORT`; tăng `work_mem` không tạo một cache lớn dùng chung; `effective_cache_size` dù có chữ “cache” lại chỉ cung cấp **ước lượng cho planner**, không cấp phát RAM. Một cấu hình chạy nhanh với một báo cáo có thể gây thiếu bộ nhớ khi hàng trăm kết nối chạy nhiều phép sort/hash cùng lúc.

Bài học thuộc chương **Kiến trúc PostgreSQL**. Mục tiêu là hiểu đường đi của một trang dữ liệu qua các lớp cache, cấu trúc bộ nhớ của backend process, cách lập ngân sách RAM an toàn và công cụ quan sát để xác định nút thắt nằm ở cache, bộ nhớ xử lý truy vấn hay I/O.

## 1. Bản đồ bộ nhớ PostgreSQL

PostgreSQL truyền thống tổ chức server thành một tiến trình chính cùng các **backend processes** phục vụ kết nối, bên cạnh các tiến trình nền như checkpointer, background writer, WAL writer, autovacuum worker và các tiến trình khác tùy cấu hình.

Ở mức khái niệm:

~~~text
                Máy chủ hoặc container PostgreSQL
+----------------------------------------------------------------+
|                              RAM                               |
|                                                                |
| +------------------------------+ +----------------------------+ |
| | PostgreSQL shared memory     | | Bộ nhớ riêng các tiến trình| |
| |                              | |                            | |
| | shared_buffers               | | Backend A: sort, hash      | |
| | - trang heap/table           | | Backend B: aggregate       | |
| | - trang index                | | Backend C: session state   | |
| |                              | | Autovacuum/maintenance      | |
| | WAL buffers, locks, metadata | | Các tiến trình nền         | |
| +------------------------------+ +----------------------------+ |
|                                                                |
| +------------------------------------------------------------+ |
| | Hệ điều hành: filesystem page cache, kernel memory...       | |
| +------------------------------------------------------------+ |
+----------------------------------------------------------------+
                               |
                               v
+----------------------------------------------------------------+
| Data files, index files, WAL, temporary files, tablespaces      |
+----------------------------------------------------------------+
~~~

Đây là **sơ đồ logic**, không phải các hộp RAM luôn tách biệt tuyệt đối về cách hệ điều hành tính dung lượng. Shared memory được ánh xạ vào nhiều tiến trình; các công cụ thống kê tiến trình có thể đếm lại một số trang dùng chung.

| Lớp | Ai quản lý? | Dùng để làm gì? | Tham số liên quan |
|---|---|---|---|
| **Shared buffers** | PostgreSQL | Cache trang dữ liệu/index dùng chung | `shared_buffers` |
| **Bộ nhớ riêng của backend** | PostgreSQL và bộ cấp phát của từng process | Query execution, sort, hash, session state, temp table | `work_mem`, `temp_buffers` |
| **OS page cache** | Kernel/hệ điều hành | Cache trang file, giảm đọc vật lý | Không có một GUC đơn giản cấp phát trực tiếp |
| **WAL buffers** | PostgreSQL shared memory | Đệm WAL records | `wal_buffers` |
| **Bộ nhớ bảo trì** | Tiến trình thực hiện maintenance | VACUUM, CREATE INDEX... | `maintenance_work_mem`, `autovacuum_work_mem` |
| **Dynamic shared memory** | PostgreSQL | Một số cấu trúc trao đổi giữa các workers | Phụ thuộc kế hoạch parallel, không chỉ một tham số |

Một truy vấn có thể sử dụng nhiều lớp cùng lúc. Không thể suy ra toàn bộ RAM cần thiết chỉ bằng `shared_buffers + work_mem`.

## 2. Shared buffers là gì?

**Shared buffers** là vùng đệm trang relation ở **shared memory**, được các backend của cùng PostgreSQL instance dùng chung.

Giả sử PostgreSQL cần trang B-tree để tìm một đơn hàng:

~~~text
Backend cần đọc trang index
             |
             v
    Tra cứu shared buffers
         /          \
       HIT          MISS
        |             |
        v             v
   Trang đã có    Đọc qua OS/file
        |             |
        |        Nạp vào buffer
        +------+------+
               |
               v
          Dùng dữ liệu
~~~

Nếu **hit**, backend có thể truy cập trang đang nằm trong shared buffers. Nếu **miss**, PostgreSQL phải nạp trang qua tầng I/O. Tuy nhiên, **miss trong shared buffers không nhất thiết là đọc đĩa vật lý**: hệ điều hành có thể đã cache trang file đó.

Shared buffers không phải một cache toàn bộ **kết quả SQL**. Nó chủ yếu giữ **các trang dữ liệu** như trang heap và trang index. Hai câu SQL khác nhau có thể dùng chung các trang này khi truy cập cùng relation.

### 2.1. Kích thước trang

PostgreSQL thường được biên dịch với block/page mặc định **8 KiB**. Kiểm tra bản build của instance:

~~~sql
SHOW block_size;
~~~

Nếu page size là 8 KiB và `shared_buffers = 128MB`, lượng buffer page theo phép tính trực quan là:

~~~text
128 MiB / 8 KiB = 16.384 trang
~~~

Đây là phép ước lượng số trang ở vùng cache; PostgreSQL còn dùng bộ nhớ cho buffer descriptors, locks và các cấu trúc quản lý khác. Đừng nhầm cấu hình `shared_buffers` với tổng shared memory của server.

### 2.2. Các đối tượng được cache

Shared buffers có thể chứa trang của:

- Bảng heap thông thường.
- Index như B-tree, GIN hoặc cấu trúc thích hợp.
- Một số dạng relation và metadata page của engine.

Khi một backend sửa dữ liệu, các trang ở buffer có thể được đánh dấu **dirty**. Trang dirty chưa nhất thiết được ghi ngay về file dữ liệu khi transaction commit.

Ngược lại, các **temporary tables** có hệ thống **local buffers/temp_buffers** riêng theo session; các temporary files sinh từ sort/hash cũng không phải những trang dữ liệu thường được giữ trong shared buffers.

### 2.3. Shared buffers dùng chung ở cấp instance

Một PostgreSQL instance có thể chứa nhiều database và nhiều connection. Vùng `shared_buffers` được dùng chung ở cấp instance, không phải:

- 4 GiB riêng cho mỗi database nếu cấu hình là 4 GiB.
- 4 GiB riêng cho mỗi kết nối.
- Vùng riêng cho từng role hoặc từng schema.

Nhờ tính dùng chung, backend B có thể được hưởng lợi từ trang backend A đã nạp vào cache nếu đó là cùng trang dữ liệu. Nhưng workload khác cũng có thể tạo áp lực thay thế những trang đang nóng.

## 3. Đường đi của một câu SELECT

Ví dụ:

~~~sql
SELECT order_id, customer_id, amount
FROM shop.orders
WHERE order_id = 1001;
~~~

Giả sử bảng có primary key trên `order_id`, optimizer có thể chọn một index scan. Backend thực hiện các bước khái quát:

1. Parse và kiểm tra quyền đối với SQL.
2. Lập kế hoạch hoặc dùng kế hoạch phù hợp.
3. Đọc các trang index liên quan.
4. Đọc trang heap cần thiết nếu kế hoạch phải lấy dữ liệu từ heap.
5. Kiểm tra tính nhìn thấy của tuple theo MVCC.
6. Trả kết quả cho ứng dụng.

Khi đọc trang heap/index, đường đi cache có thể là:

~~~text
               Backend PostgreSQL
                       |
                       v
               Shared buffers
                 /          \
                / HIT        \ MISS
               v              v
          Trả trang       Yêu cầu đọc
                                 |
                                 v
                          OS page cache
                           /       \
                         HIT       MISS
                          |          |
                          |      SSD/HDD/storage
                          |          |
                          +-----+----+
                                |
                                v
                     Nạp vào shared buffers
~~~

Vì thế có **hai mức hit khác nhau**. Bộ đếm hits của shared buffers không tự đo mức hit OS page cache.

### 3.1. Hot working set

**Working set** là tập trang dữ liệu/index thường được truy cập trong một giai đoạn. Một bảng 500 GiB không nhất thiết cần RAM 500 GiB: nếu query thường xuyên chỉ dùng 2 GiB dữ liệu nóng, cache nhỏ hơn nhiều vẫn có thể mang lại hiệu quả.

Ngược lại, nếu nhiều query liên tục truy cập ngẫu nhiên trên tập trang rất lớn, áp lực cache miss có thể cao dù `shared_buffers` đã tăng.

Cần phân biệt:

- **Kích thước bảng:** bao nhiêu dữ liệu đang lưu trên đĩa.
- **Kích thước working set:** bao nhiêu trang được truy cập thường xuyên.
- **Dung lượng cache:** bao nhiêu trang có thể được giữ lại.
- **Tính chọn lọc của truy vấn:** bao nhiêu trang phải đọc để trả kết quả.

Không dự báo nhu cầu RAM chỉ từ kích thước tổng database.

### 3.2. Thay thế trang không phải LRU đơn giản

PostgreSQL dùng cơ chế quản lý buffer dựa trên mức sử dụng, thường được mô tả qua chiến lược **clock-sweep** và các **buffer access strategies**. Nó không nhất thiết áp dụng một hàng đợi LRU đơn giản cho mọi thao tác.

Một số hoạt động đọc tuần tự tập dữ liệu lớn có thể sử dụng ring buffer/access strategy để hạn chế làm nhiễu toàn bộ shared cache. Do đó, không nên khẳng định một lần sequential scan sẽ xóa sạch mọi trang được dùng thường xuyên.

## 4. Đường ghi: dirty buffers, WAL và checkpoint

Một `UPDATE` sửa bản ghi trong trang dữ liệu mà PostgreSQL quản lý. Những trang trong shared buffers có thể trở thành **dirty** sau khi thay đổi.

~~~text
UPDATE orders
      |
      v
 Thay đổi trang trong shared buffers
      |
      +----> Tạo WAL records cần thiết
      |
      v
 Trang dirty
      |
      +----> Có thể được ghi bởi background writer
      |
      +----> Có thể được ghi bởi backend/checkpointer
      |
      v
 Dữ liệu file được ghi theo cơ chế server
~~~

### 4.1. Vì sao COMMIT không có nghĩa ghi ngay mọi trang heap?

PostgreSQL dùng **WAL — Write-Ahead Logging**. Để bảo đảm recovery/durability theo cấu hình, WAL cần được ghi bền vững theo thứ tự và điều kiện thích hợp trước khi trang dữ liệu được xem là ghi bền vững.

Vì vậy, một transaction có thể `COMMIT` thành công trong khi những trang heap/index vừa thay đổi vẫn ở shared buffers và được ghi về data file sau đó. Nếu server crash, PostgreSQL có thể dùng WAL để phục hồi trạng thái phù hợp.

**WAL không thay thế backup.** Một lệnh xóa dữ liệu được commit do nhầm lẫn có thể được ghi vào WAL và nhân bản sang replica. Cần backup và quy trình phục hồi độc lập.

### 4.2. WAL buffers khác shared buffers

| Vùng | Giữ gì? | Vai trò |
|---|---|---|
| `shared_buffers` | Trang data/index | Cache và xử lý đọc/ghi dữ liệu |
| `wal_buffers` | WAL records đang được đệm | Hỗ trợ logging và recovery |
| OS page cache | Trang file do kernel cache | Có thể giảm đọc thiết bị vật lý |

Không cộng số WAL buffer pages vào số data buffer pages như thể chúng cùng giữ một loại đối tượng.

### 4.3. Background writer, checkpointer, backend writes

- **Background writer** có thể ghi sớm những dirty buffers để tạo chỗ tái sử dụng.
- **Checkpointer** thực hiện những công việc cần thiết cho checkpoint và khả năng recovery.
- **Backend** cũng có thể phải ghi trang trong các tình huống cần thiết.
- **WAL writer** tham gia ghi dữ liệu WAL theo cơ chế PostgreSQL.

Độ trễ ghi chịu tác động của workload, WAL, I/O thiết bị, tiến trình nền và cache. Tăng shared buffers có thể thay đổi hành vi ghi và checkpoint, nhưng không tự giải quyết mọi vấn đề write latency.

## 5. Cấu hình shared_buffers

Xem giá trị:

~~~sql
SHOW shared_buffers;
~~~

Hoặc truy vấn metadata cấu hình:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name = 'shared_buffers';
~~~

`shared_buffers` được cấu hình ở cấp server và thường cần **restart PostgreSQL** để thay đổi có hiệu lực. Không thể cấp phát lại vùng cache toàn server bằng một câu `SET shared_buffers` trong session thông thường.

### 5.1. Chọn dung lượng ban đầu thế nào?

Với máy chuyên chạy PostgreSQL, một điểm khởi đầu thường được nhắc đến là **khoảng 25% RAM** cho `shared_buffers`, sau đó đo và điều chỉnh. Đây không phải công thức tối ưu cho mọi workload.

Ví dụ máy có 32 GiB RAM:

~~~text
Điểm khởi đầu tham khảo:
  shared_buffers ~= 8 GiB

RAM còn cần cho:
  - Backend processes và query execution
  - Sort, hash, aggregate
  - Autovacuum và maintenance
  - WAL/shared memory khác
  - OS page cache
  - Kernel, monitoring agents, dịch vụ khác
~~~

Nếu PostgreSQL chạy trong container có memory limit 8 GiB trên host 64 GiB, cần lập ngân sách theo **giới hạn container**, không theo tổng RAM host.

### 5.2. Vì sao không tăng tới 90% RAM?

Khi shared_buffers chiếm quá nhiều RAM:

1. OS page cache có ít headroom.
2. Bộ nhớ riêng cho query có thể cạnh tranh gay gắt hơn.
3. Autovacuum, maintenance, parallel workers và các tiến trình nền có thể bị thiếu tài nguyên.
4. Nếu vấn đề là CPU, lock hoặc truy vấn quét dữ liệu không cần thiết, tăng cache không chữa được.
5. Có thể gây memory pressure hoặc OOM trong giờ tải cao.

Cấu hình hợp lý phải cân bằng **tất cả nhu cầu RAM**, không tối đa hóa một tham số.

## 6. Bộ nhớ riêng của backend process

Trong mô hình truyền thống, mỗi connection client có một backend process. Mỗi backend có bộ nhớ riêng cho:

- Parse, plan và execute SQL.
- Trạng thái transaction/session.
- Cấu trúc phục vụ sort, hash join, hash aggregate và các phép xử lý khác.
- Bộ nhớ cho temporary table khi được sử dụng.
- Các memory contexts nội bộ.
- Những cấu trúc của extension hoặc tính năng được bật.

~~~text
Backend A: ứng dụng bán hàng
   session state
   executor
   sort / hash nhỏ

Backend B: báo cáo phân tích
   session state
   nhiều sort / hash lớn

Backend C: kết nối idle
   bộ nhớ nền của process/session

Shared buffers:
   cùng một vùng cache cho A, B, C
~~~

**Không phải mỗi backend có một bản sao riêng của shared_buffers.** Tuy nhiên, nhiều backend vẫn tạo áp lực RAM lớn vì chi phí nền và bộ nhớ riêng của công việc.

### 6.1. Idle connection không mặc định chiếm hết work_mem

Một backend ở trạng thái `idle` vẫn cần bộ nhớ process/session. Nhưng nó **không được cấp phát toàn bộ work_mem** chỉ vì đã kết nối.

Ở chiều ngược lại, một backend active chạy query phức tạp có thể dùng nhiều lần ngân sách work_mem, do query có nhiều node dùng memory.

### 6.2. Memory contexts

PostgreSQL sử dụng **memory contexts** để quản lý vòng đời cấp phát bộ nhớ bên trong backend.

Ví dụ:

~~~text
Backend process
  |
  +-- Context cấp phiên
  |     |
  |     +-- Query/Executor contexts
  |     |      +-- Tuples, expression state
  |     |      +-- Sort/Hash allocations
  |     |
  |     +-- Transaction contexts
  |
  +-- Các internal contexts khác
~~~

Khi một query hoặc transaction kết thúc, các context liên quan có thể được giải phóng/reset theo vòng đời. Tuy nhiên, lượng **RSS do OS báo** không nhất thiết giảm từng byte tương ứng ngay lập tức, do allocator và cơ chế quản lý trang bộ nhớ.

## 7. work_mem: bộ nhớ theo thao tác, không phải ngân sách toàn session

`work_mem` xác định ngân sách cơ bản cho **mỗi thao tác xử lý** như sort hoặc hash trước khi PostgreSQL phải cân nhắc xử lý theo cách khác, bao gồm việc ghi dữ liệu ra tệp tạm đối với những thuật toán phù hợp.

~~~sql
SHOW work_mem;
~~~

Những điều không đúng:

- “work_mem là RAM tối đa của cả PostgreSQL”.
- “Mỗi connection chỉ dùng tối đa đúng một work_mem”.
- “Mở connection là PostgreSQL cấp đủ work_mem”.
- “Tăng work_mem sẽ làm shared buffers rộng hơn”.

### 7.1. Một query có thể có nhiều node dùng memory

Ví dụ:

~~~sql
SELECT
    c.region,
    COUNT(*) AS order_count,
    SUM(o.amount) AS revenue
FROM shop.orders AS o
JOIN shop.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY c.region
ORDER BY revenue DESC;
~~~

Tùy kế hoạch, PostgreSQL có thể dùng hash join, hash aggregate và sort:

~~~text
Sort (ORDER BY revenue)           -> vùng nhớ 1
        |
HashAggregate (GROUP BY)          -> vùng nhớ 2
        |
Hash Join                         -> vùng nhớ 3
        |
  Scan orders + customers
~~~

Một số vùng có thể cùng giữ memory trong quá trình thực thi. Vì vậy, tổng nhu cầu RAM của query có thể lớn hơn một lần `work_mem`.

### 7.2. hash_mem_multiplier

PostgreSQL có tham số:

~~~sql
SHOW hash_mem_multiplier;
~~~

Các thao tác hash có thể được phép dùng ngân sách bộ nhớ được tính theo `work_mem * hash_mem_multiplier`, theo quy tắc phiên bản và loại thao tác.

Ví dụ minh họa:

~~~text
work_mem = 64 MiB
hash_mem_multiplier = 2

Một thao tác hash có thể được lập ngân sách cao hơn,
khoảng 128 MiB, theo cơ chế áp dụng.
~~~

Điều đó **không có nghĩa mọi hash đều cấp phát 128 MiB**. Nó cũng không giới hạn toàn bộ query ở 128 MiB vì một query có thể có nhiều node/worker.

### 7.3. Parallel workers làm bài toán lớn hơn

Một kế hoạch parallel query có thể có leader và nhiều workers. Nhiều bước của kế hoạch tiêu thụ bộ nhớ trong từng worker; một số cấu trúc khác được chia sẻ bằng dynamic shared memory.

~~~sql
SHOW max_parallel_workers_per_gather;
~~~

Không áp dụng một phép nhân cố định cho tất cả query vì cơ chế của từng plan node khác nhau. Nhưng khi dự toán bộ nhớ, phải xét **mức song song và số query chạy đồng thời**.

### 7.4. Khi sort không vừa RAM

~~~text
ORDER BY trên nhiều hàng
          |
          v
  Bộ nhớ sort đủ?
      /       \
     Có       Không
     |           |
     v           v
  In-memory   External sort
     sort      và tệp tạm
      \         /
       \       /
        v     v
       Trả kết quả
~~~

Sort spill ra đĩa có thể gây I/O và chậm. Tăng `work_mem` đôi khi giúp, nhưng tăng trên toàn server rất dễ trở thành vấn đề nếu hàng chục query cùng dùng nhiều sort/hash nodes.

## 8. temp_buffers phục vụ temporary tables

`temp_buffers` là vùng đệm **theo session** dành cho các trang của **temporary tables**.

~~~sql
CREATE TEMP TABLE recent_order_ids (
    order_id BIGINT PRIMARY KEY
);

INSERT INTO recent_order_ids
VALUES (101), (102), (103);

SELECT *
FROM recent_order_ids;
~~~

~~~sql
SHOW temp_buffers;
~~~

Các điểm quan trọng:

- Buffer của temporary table là **local buffers**, không dùng cùng cơ chế shared buffers của bảng thông thường.
- Bộ nhớ được cấp theo nhu cầu; mở connection không mặc định sử dụng toàn bộ giá trị `temp_buffers`.
- Việc thay đổi `temp_buffers` trong một session có ràng buộc về thời điểm, nên đặt trước khi session lần đầu truy cập temporary table.
- Temporary tables có thể dùng không gian lưu trữ khi cần; không phải toàn bộ bảng tạm luôn nằm trong RAM.

### 8.1. Không nhầm temp_buffers và tệp tạm của ORDER BY

| Công việc | Nguồn bộ nhớ/chỗ lưu liên quan |
|---|---|
| Temporary table | Local temp buffers và temp relation storage |
| Sort/Hash spill | `work_mem`, hash multiplier, temporary files |
| Cache bảng thông thường | `shared_buffers` |
| Cache file ở OS | OS page cache |

Nếu truy vấn có `Sort Method: external merge`, tăng `temp_buffers` không phải cách khắc phục trực tiếp. Trước tiên xem `work_mem`, query plan và số hàng phải sort.

### 8.2. temp_file_limit

~~~sql
SHOW temp_file_limit;
~~~

Tham số `temp_file_limit` giới hạn dung lượng một số loại temporary files do một tiến trình sử dụng, nhằm tránh vài query tạo tệp tạm quá lớn. Nó **không phải giới hạn RAM** và không áp dụng đồng nhất cho mọi dạng temporary relation storage.

Đặt quá thấp có thể làm query hợp lệ bị hủy; đặt quá cao hoặc vô hạn có thể khiến thiếu đĩa nếu không có kiểm soát I/O và dung lượng.

## 9. maintenance_work_mem và autovacuum_work_mem

Các tác vụ bảo trì cũng dùng bộ nhớ:

~~~sql
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;
~~~

**`maintenance_work_mem`** là ngân sách cho những thao tác bảo trì phù hợp, ví dụ `VACUUM` hoặc `CREATE INDEX` theo cơ chế áp dụng.

**`autovacuum_work_mem`** điều khiển bộ nhớ dành cho autovacuum workers; cấu hình `-1` thường có nghĩa kế thừa `maintenance_work_mem`.

~~~text
Autovacuum worker A -> bộ nhớ bảo trì
Autovacuum worker B -> bộ nhớ bảo trì
Báo cáo SQL X       -> sort/hash
Báo cáo SQL Y       -> sort/hash
Shared buffers      -> vùng dùng chung
OS page cache       -> vùng OS có thể thu hồi
~~~

Tổng tài nguyên phải phù hợp RAM hiện có. Nếu nhiều autovacuum workers chạy đồng thời, nhu cầu bộ nhớ có thể tăng tương ứng với từng worker và công việc thực tế.

Không tự động suy luận mọi tác vụ `CREATE INDEX` hoặc mọi parallel maintenance worker đều sử dụng đúng bằng `maintenance_work_mem`. Chi tiết khác nhau theo thao tác và phiên bản.

## 10. OS page cache là gì?

Khi PostgreSQL đọc file dữ liệu, hệ điều hành có thể cache nội dung file ở RAM. Đây là **OS page cache**, khác vùng shared buffers do PostgreSQL quản lý.

~~~text
Backend query
    |
    v
Shared buffers ---- HIT ---> Trả trang
    |
   MISS
    |
    v
OS page cache ----- HIT ---> Trả trang
    |
   MISS
    |
    v
Thiết bị lưu trữ
    |
    v
Nạp dữ liệu vào cache
~~~

Với kiểu I/O qua filesystem thông thường, trang dữ liệu có thể tồn tại trong cả bộ đệm PostgreSQL và cache OS. Hai lớp có cách quản lý và mục tiêu khác nhau.

### 10.1. OS page cache có thể thu hồi

Hệ điều hành thường dùng RAM chưa cần cho những nhu cầu bắt buộc để cache file. Khi tiến trình cần RAM, kernel có thể thu hồi những trang cache phù hợp.

Do đó, trên Linux **RAM free thấp không nhất thiết đồng nghĩa thiếu bộ nhớ**. Một phần lớn RAM có thể đang nằm trong cache có thể thu hồi, và `available` vẫn cao.

Nhưng nếu áp lực RAM kéo dài, page cache bị thu hồi liên tục, swap in/out tăng hoặc OOM-kill xuất hiện, hiệu năng và tính ổn định có thể bị ảnh hưởng.

### 10.2. Không thể tính OS cache là RAM trống hoàn toàn

OS page cache có thể được thu hồi nhưng vẫn mang giá trị hiệu năng. Nếu tăng shared_buffers làm giảm mạnh cache OS, tổng I/O của hệ thống có thể **không giảm** hoặc còn xấu hơn.

Vì vậy, cần đo cả cache PostgreSQL, memory available và chỉ số I/O vật lý, không chỉ xem shared-buffer hit ratio.

### 10.3. Container và cgroup

Khi PostgreSQL chạy trong container, tài nguyên thường bị giới hạn bởi cgroup. Một host có 64 GiB RAM không bảo đảm container giới hạn 8 GiB có thể dùng hơn 8 GiB.

Nên theo dõi:

- Giới hạn bộ nhớ thực tế của container.
- Memory usage và các chỉ số cgroup.
- Swap và tình trạng OOM-kill.
- Private memory của backend và shared memory.
- Cache file được tính vào ngân sách container theo nền tảng thực tế.

Cấu hình `shared_buffers` nên được đánh giá theo **giới hạn bộ nhớ khả dụng của workload**, không chỉ RAM host.

## 11. effective_cache_size không phải vùng RAM được cấp phát

~~~sql
SHOW effective_cache_size;
~~~

**`effective_cache_size`** cung cấp một **ước lượng cho query planner** về dung lượng cache có thể hữu ích khi truy cập dữ liệu. Nó liên quan tới shared buffers, page cache OS và mức bộ nhớ có thể được sử dụng hiệu quả, nhưng **không cấp phát bộ nhớ**.

Ví dụ:

~~~text
shared_buffers       = 4 GiB
effective_cache_size = 10 GiB
~~~

Không thể kết luận PostgreSQL đã cấp phát **14 GiB**. Trong ví dụ, `4 GiB` là cấu hình buffer cache nội bộ, còn `10 GiB` là giả định planner có thể dùng để ước tính chi phí các kế hoạch.

### 11.1. Vì sao tham số này ảnh hưởng EXPLAIN?

Nếu planner kỳ vọng nhiều trang file có sẵn trong cache, nó có thể đánh giá chi phí các cách đọc index khác với khi kỳ vọng nhiều I/O ngẫu nhiên đắt đỏ.

Điều này có thể làm thay đổi lựa chọn giữa các plan phù hợp, nhưng việc tăng `effective_cache_size` không tự nạp thêm trang hoặc biến truy vấn chậm thành nhanh.

### 11.2. Đặt giá trị bao nhiêu?

Không dùng một công thức cứng cho mọi hệ thống. Hãy ước lượng lượng cache có thể phục vụ dữ liệu của workload khi đã tính các nhu cầu RAM riêng của backend, bảo trì, OS và các dịch vụ khác.

Một số hướng dẫn bắt đầu từ tỷ lệ khá lớn của RAM trên máy chuyên database, nhưng quyết định cuối cùng phải dựa trên cấu hình, OS cache, loại query và kết quả đo thực tế.

## 12. Vì sao công thức RAM = shared_buffers + connections × work_mem là sai?

Một phép nhân thường thấy:

~~~text
RAM dự kiến = shared_buffers + max_connections * work_mem
~~~

Đây **không phải công thức chính xác** vì:

1. Không phải mọi connection đều chạy query hay dùng work_mem.
2. Một query có thể có **nhiều sort/hash operations**.
3. Hash có thể được phép dùng ngân sách lớn hơn nhờ `hash_mem_multiplier`.
4. Parallel workers có nhu cầu riêng và có thể có dynamic shared memory.
5. Temporary tables dùng `temp_buffers` và tài nguyên khác.
6. Backend luôn có memory contexts/trạng thái riêng ngoài work_mem.
7. Autovacuum và maintenance cũng có ngân sách.
8. WAL, locks và những cấu trúc shared memory khác cần RAM.
9. OS page cache, kernel và các dịch vụ ngoài PostgreSQL cần RAM.
10. Cgroup có thể đặt memory limit thấp hơn RAM vật lý.

Dù không có công thức đơn giản, có thể lập **kịch bản tải đồng thời** để dự toán headroom.

### 12.1. Ví dụ máy 16 GiB RAM

Giả sử:

| Thành phần | Giá trị minh họa |
|---|---|
| RAM tổng | 16 GiB |
| shared_buffers | 4 GiB |
| effective_cache_size | 10 GiB — chỉ là giả định planner |
| Backend connections mở | 100 |
| Query báo cáo chạy đồng thời | 8 |
| Sort nodes có thể giữ RAM đồng thời/query | 2 |
| work_mem | 64 MiB |

Trong kịch bản lý tưởng hóa, riêng các sort có thể cần:

~~~text
8 query x 2 sort x 64 MiB = 1.024 MiB (~1 GiB)
~~~

Con số này **không phải mức sử dụng đo được hay giới hạn trên của toàn workload**. Nếu có thêm hash, parallel workers hoặc nhiều node giữ memory đồng thời, nhu cầu có thể tăng.

Máy còn cần bộ nhớ nền của 100 backend, autovacuum, shared memory khác, OS cache và kernel. **Không cộng thêm 10 GiB effective_cache_size** vì nó không được cấp phát.

### 12.2. Concurrency quan trọng hơn giới hạn kết nối

Hai hệ thống cùng `max_connections = 300` có thể khác nhau hoàn toàn:

- Hệ A: hầu hết kết nối idle, mỗi lúc chỉ có 10 query nhẹ.
- Hệ B: 100 query báo cáo đồng thời với nhiều hash/sort và parallel workers.

Áp lực RAM/CPU/I/O của hệ B có thể cao hơn rất nhiều. Cần đo **active concurrency và loại query**, không suy luận tải từ `max_connections`.

### 12.3. Connection pool

Connection pool ở ứng dụng hoặc proxy phù hợp giúp giới hạn số backend thật và giảm chi phí duy trì quá nhiều phiên. Nhưng pooling không tự sửa một query dùng quá nhiều RAM; vẫn cần giới hạn số báo cáo đồng thời và phân tích kế hoạch.

Nếu dùng transaction pooling, phải hiểu các hạn chế đối với state theo session, prepared statements và temporary tables theo cách triển khai cụ thể.

## 13. Kiểm tra cấu hình trực tiếp bằng pg_settings

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'wal_buffers',
    'work_mem',
    'hash_mem_multiplier',
    'temp_buffers',
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'effective_cache_size',
    'max_connections',
    'max_parallel_workers_per_gather',
    'huge_pages'
)
ORDER BY name;
~~~

| Trường | Cách hiểu |
|---|---|
| `name` | Tên cấu hình |
| `setting` | Giá trị ở dạng được PostgreSQL báo |
| `unit` | Đơn vị tương ứng khi có |
| `context` | Phạm vi/thời điểm thay đổi được phép |
| `source` | Nguồn đang quyết định giá trị |
| `pending_restart` | Có cấu hình cần restart mới áp dụng hay không |

**Không đọc `setting = 16384` rồi suy ra 16.384 MiB** nếu chưa xem `unit`. Với mục tiêu đọc nhanh, các câu `SHOW work_mem;`, `SHOW shared_buffers;` thường dễ hiểu hơn.

### 13.1. Đổi work_mem cục bộ

Trong một transaction thử nghiệm:

~~~sql
BEGIN;

SET LOCAL work_mem = '32MB';

SHOW work_mem;

-- Query kiểm tra được thực thi ở đây.

ROLLBACK;
~~~

`SET LOCAL` có hiệu lực trong transaction hiện tại. Sau khi kết thúc transaction, giá trị cục bộ không trở thành cấu hình cố định của toàn server.

Với query report riêng cần nhiều bộ nhớ, điều chỉnh cục bộ có thể phù hợp hơn tăng `work_mem` cho tất cả backend. Nhưng phải tính nhiều node và nhiều query đồng thời.

### 13.2. shared_buffers thường cần restart

Không dùng `SET LOCAL shared_buffers` để thử tăng shared cache. Đây là cấu hình liên quan khởi động server/shared memory. Hãy xem `pg_settings.context` và lập kế hoạch restart/rollback nếu thật sự cần thay đổi.

## 14. Shared-buffer hit ratio đo gì?

PostgreSQL có view thống kê `pg_stat_database`:

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    ROUND(
        100.0 * blks_hit
        / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

- `blks_hit`: những block accesses được phục vụ từ shared buffer cache theo phạm vi thống kê.
- `blks_read`: block accesses cần đọc qua đường đọc relation được theo dõi.
- Tỷ lệ trên là **chỉ số cache hit ở cấp shared buffers**, không phải tỷ lệ “không cần đọc SSD” của mọi hoạt động PostgreSQL.

### 14.1. Vì sao hit 99% chưa bảo đảm hệ thống nhanh?

- Query có thể dùng nhiều CPU để lọc/tính toán.
- Sort/hash có thể ghi temporary files.
- Transaction có thể chờ row lock hoặc DDL lock.
- Một query quan trọng có thể bị cache miss nhiều nhưng bị che bởi số hits lớn của query khác.
- Counter là số **tích lũy** từ nhiều giờ/ngày hoặc kể từ lần reset.
- WAL, checkpoint và I/O khác không được mô tả đầy đủ chỉ bằng tỷ lệ này.

Đừng tối ưu hệ thống chỉ dựa trên một tỷ lệ hit cao/thấp.

### 14.2. blks_read không bằng physical disk reads

Shared-buffer miss dẫn đến một lần đọc theo tầng PostgreSQL, nhưng OS page cache có thể đã có block. Vì vậy `blks_read` không tự chứng minh thiết bị lưu trữ đã đọc vật lý đúng số lượng đó.

Muốn biết I/O thiết bị cần bổ sung metric filesystem/OS/cloud và các số liệu I/O chi tiết khác theo phiên bản.

### 14.3. Snapshot theo thời gian

Nếu muốn đo tỷ lệ trong một giờ, cần lấy hiệu của hai snapshot:

~~~text
hits_in_window  = hits_at_end  - hits_at_start
reads_in_window = reads_at_end - reads_at_start

hit_pct_window =
  100 * hits_in_window /
  (hits_in_window + reads_in_window)
~~~

Kiểm tra `stats_reset` trước khi trừ; nếu counter bị reset giữa hai snapshot, công thức hiệu có thể cho kết quả sai.

## 15. Thống kê cache theo bảng

Để quan sát một số bảng người dùng:

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit
FROM pg_statio_user_tables
WHERE schemaname = 'public'
ORDER BY
    COALESCE(heap_blks_read, 0) +
    COALESCE(idx_blks_read, 0) DESC
LIMIT 20;
~~~

Những nhóm chỉ số:

- `heap_blks_read/hit`: đọc/hit với heap của bảng.
- `idx_blks_read/hit`: hoạt động đọc/hit liên quan các index của bảng.
- `toast_blks_read/hit`: TOAST storage khi có dữ liệu lớn cần lưu ngoài hàng.

Các counter tích lũy này giúp tìm bảng có nhiều block accesses, nhưng **không xác định được truy vấn nào gây ra**. Cần kết hợp query logging, `pg_stat_statements` (nếu đã cấu hình), và `EXPLAIN`.

Không so số hits tuyệt đối giữa hai bảng rồi kết luận bảng nhiều hits hơn có cache kém/tốt hơn; số lượt truy cập và kích thước working set khác nhau.

## 16. EXPLAIN (ANALYZE, BUFFERS): thấy cache trong kế hoạch

Một ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id
FROM shop.orders
WHERE customer_id = 42;
~~~

Output có thể chứa:

~~~text
Buffers: shared hit=120 read=15
~~~

Cách đọc:

- `shared hit=120` cho thấy các lần truy cập buffer được phục vụ từ shared buffers ở phạm vi thống kê được báo.
- `read=15` nghĩa là cần đọc khối ở đường I/O relation tương ứng.
- Đây không phải chứng cứ chính xác về số lần đọc thiết bị vật lý.

**`EXPLAIN (ANALYZE)` thực sự thực thi câu SQL**. Với câu lệnh DML, điều này có thể tạo thay đổi thật. Không thử `EXPLAIN (ANALYZE) DELETE ...` trên production như thể là lệnh chỉ đọc.

### 16.1. Đọc các node của kế hoạch

Kế hoạch có nhiều node con/cha. Các số liệu buffer ở một số dòng đã được tổng hợp theo subtree của node, nên không nên cộng mù quáng mọi con số trong các node để ra tổng mới.

Một số output còn có `Buffers: local ...` hoặc `Buffers: temp ...`, tương ứng với các nhóm buffer/file khác.

### 16.2. Nhìn sort trong RAM hay spill

Một node có thể báo:

~~~text
Sort Method: quicksort  Memory: 2048kB
~~~

hoặc:

~~~text
Sort Method: external merge  Disk: 8192kB
Buffers: shared hit=... read=..., temp read=... written=...
~~~

Dòng `external merge` và `temp read/written` gợi ý sort phải dùng tệp tạm. `Memory</BT> trong một sort node không phải tổng RAM của backend.

Nếu query chủ yếu chậm do sort spill, tăng shared_buffers không phải phương án trực tiếp. Cần xem `work_mem`, số hàng, planner và khả năng hỗ trợ bằng index.

## 17. Thực hành với một bảng giả lập

Chạy các lệnh này trong **database PostgreSQL thử nghiệm**, không phải production. Đối tượng được đặt ở schema `memory_lab` để tránh nhầm với dữ liệu ứng dụng.

### 17.1. Tạo bảng

~~~sql
CREATE SCHEMA IF NOT EXISTS memory_lab;

CREATE TABLE memory_lab.sale_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);
~~~

Tạo 50.000 hàng mẫu:

~~~sql
INSERT INTO memory_lab.sale_events (
    customer_id, category, amount, occurred_at
)
SELECT
    (g % 1000) + 1,
    'category-' || (g % 20),
    ((g % 25000) / 100.0)::NUMERIC(12, 2),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second'
FROM generate_series(1, 50000) AS g;

ANALYZE memory_lab.sale_events;
~~~

Có thể giảm số hàng nếu máy học tập hạn chế tài nguyên. Dữ liệu nhỏ không phải benchmark về hiệu năng production.

### 17.2. Quan sát dung lượng bảng/index

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('memory_lab.sale_events')
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('memory_lab.sale_events')
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('memory_lab.sale_events')
    ) AS total_size;
~~~

Kích thước relation trên đĩa không đồng nghĩa toàn bộ dữ liệu đang nằm trong shared buffers.

### 17.3. Xem dữ liệu theo primary key

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, customer_id, amount
FROM memory_lab.sale_events
WHERE event_id BETWEEN 1000 AND 2000;
~~~

Chạy lại query trong môi trường thử nghiệm có thể thấy các chỉ số hit/read thay đổi vì trang đã có trong cache. Nhưng không bảo đảm kế hoạch và con số giống nhau ở mọi hệ thống.

### 17.4. Thử sort với work_mem thấp

~~~sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    event_id,
    customer_id,
    category,
    amount,
    occurred_at
FROM memory_lab.sale_events
ORDER BY category, amount DESC, occurred_at;

ROLLBACK;
~~~

Với dữ liệu đủ lớn, có thể xuất hiện `external merge` và temporary file I/O. Tuy nhiên, điều này phụ thuộc kích thước dữ liệu, planner, parallelism và bộ nhớ thực tế.

### 17.5. Thử ngân sách lớn hơn

~~~sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    event_id,
    customer_id,
    category,
    amount,
    occurred_at
FROM memory_lab.sale_events
ORDER BY category, amount DESC, occurred_at;

ROLLBACK;
~~~

So sánh output:

| Dấu hiệu | work_mem thấp | work_mem lớn hơn |
|---|---|---|
| Sort Method | Có thể external merge | Có thể quicksort/in-memory |
| Temp read/written | Có thể tăng | Có thể giảm |
| Memory ở sort node | Bị ngân sách giới hạn | Có thể cao hơn |
| Execution Time | Có thể bị ảnh hưởng tệp tạm | Có thể cải thiện, cần đo |
| RAM toàn server | Không suy từ một query | Rủi ro tăng nếu áp dụng toàn cục |

Hai transaction trên thay đổi `work_mem` **cục bộ**; bảng `sale_events` được tạo trước đó vẫn tồn tại.

## 18. Theo dõi temporary files theo thời gian

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes_written,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

`temp_files` và `temp_bytes` là counter tích lũy, **không phải lượng đĩa tạm đang chiếm tại đúng thời điểm truy vấn**.

Nếu chỉ số tăng nhanh, cần tìm những câu SQL tạo:

- Sort lớn.
- Hash join/aggregate vượt ngân sách.
- Tập trung gian rất lớn do điều kiện JOIN hoặc bộ lọc thiếu chọn lọc.
- Báo cáo chạy song song hoặc nhiều session đồng thời.

### 18.1. log_temp_files

~~~sql
SHOW log_temp_files;
~~~

Khi cấu hình phù hợp, PostgreSQL có thể ghi log các tệp tạm vượt ngưỡng. Đây là một cách xác định query gây spill. Nhưng mức ngưỡng quá thấp có thể tạo lượng log rất lớn, ảnh hưởng I/O và bảo mật.

Không tự bật logging chi tiết trên production mà chưa đánh giá log retention và phạm vi dữ liệu.

### 18.2. pg_stat_statements

Nếu extension `pg_stat_statements` đã được cài và cấu hình, nó có thể tổng hợp thông tin theo mẫu truy vấn, gồm các bộ đếm shared/temp blocks ở những phiên bản hỗ trợ.

Lưu ý:

- Không phải server nào cũng bật extension.
- Có thể cần cấu hình khởi động và quyền phù hợp.
- Counter tích lũy từ lần reset.
- Query text có thể chứa thông tin nhạy cảm.

Không cần cài extension chỉ để hiểu ba lớp bộ nhớ.

## 19. Quan sát số backend và connection

Một query đơn giản:

~~~sql
SELECT
    backend_type,
    state,
    COUNT(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type, state
ORDER BY backend_type, state;
~~~

Nếu muốn đếm riêng kết nối client:

~~~sql
SELECT
    state,
    COUNT(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY state;
~~~

Các trạng thái thường gặp:

- `active`: backend đang thực thi hoặc xử lý yêu cầu.
- `idle`: chờ yêu cầu mới.
- `idle in transaction`: transaction đang mở dù session hiện không thực thi SQL.

Không thể suy ra memory footprint chính xác từ `state`. Một session idle không nhất thiết dùng nhiều RAM, nhưng nó vẫn có chi phí nền và có thể giữ tài nguyên sau truy vấn theo cách allocator quản lý.

### 19.1. Transaction dài

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Transaction dài có thể ảnh hưởng MVCC/VACUUM và khóa. Đó là vấn đề vận hành liên quan nhưng không phải bằng chứng trực tiếp rằng session đang dùng nhiều sort memory.

Không tự hủy backend production chỉ dựa vào tuổi transaction mà chưa xác định trách nhiệm và hậu quả.

## 20. Bộ nhớ bên trong backend: pg_backend_memory_contexts

Với những phiên bản PostgreSQL hỗ trợ view **`pg_backend_memory_contexts`** và tài khoản có quyền phù hợp:

~~~sql
SELECT
    name,
    parent,
    level,
    pg_size_pretty(total_bytes) AS total_size,
    pg_size_pretty(used_bytes) AS used_size,
    pg_size_pretty(free_bytes) AS free_size
FROM pg_backend_memory_contexts
ORDER BY total_bytes DESC
LIMIT 20;
~~~

View mô tả các memory contexts của **backend hiện tại**, không phải một bảng thống kê tổng bộ nhớ của mọi backend trong server.

Các cột giúp quan sát bộ nhớ đã cấp cho context, phần đang dùng và phần trống trong phạm vi context. Chúng không tương đương trực tiếp với RSS theo hệ điều hành.

Một số phiên bản còn có công cụ yêu cầu ghi memory context của backend vào log với quyền thích hợp; đó là thao tác điều tra nâng cao cần cân nhắc bảo mật và chi phí, không phải bước quan sát thường xuyên của người mới học.

## 21. Đọc bộ nhớ từ hệ điều hành

Trong Linux, người vận hành có thể dùng:

~~~bash
free -h
vmstat 1 5
ps -eo pid,rss,cmd
~~~

Các chỉ số cần hiểu:

| Metric | Điều nên xem |
|---|---|
| Memory available | RAM có thể cung cấp thêm theo ước lượng kernel |
| Page cache/buffers | RAM đang được OS dùng để cache file |
| RSS của process | Resident memory nhìn từ process, có thể chứa shared pages |
| Swap in/out | Hoạt động hoán đổi, đặc biệt nếu tăng liên tục |
| OOM-kill | Dấu hiệu vượt memory limit hoặc thiếu RAM nghiêm trọng |
| Disk latency/throughput | Bổ sung dữ liệu để xác định I/O thật |

### 21.1. Cộng RSS của mọi tiến trình PostgreSQL có thể đếm trùng

Shared memory được ánh xạ vào nhiều backend. Vì thế, nếu cộng RSS của 100 tiến trình, cùng một số trang shared có thể bị **đếm lặp nhiều lần**.

Để đánh giá sử dụng bộ nhớ hệ thống, cần kết hợp tổng RAM/cgroup metrics với công cụ phân biệt private/shared. Trên Linux, PSS (*proportional set size*) có thể hữu ích trong những công cụ hỗ trợ.

### 21.2. Free thấp không chắc thiếu RAM

Linux thường dùng RAM rảnh cho file cache. Một server có free thấp nhưng available cao và swap gần như không hoạt động có thể hoàn toàn bình thường.

Ngược lại, nếu available thấp kéo dài, swap tăng, latency tăng hoặc container bị OOM-kill, cần kiểm tra ngân sách RAM.

### 21.3. Huge pages

~~~sql
SHOW huge_pages;
~~~

Huge pages có thể giảm chi phí quản lý bảng trang đối với shared memory lớn trên nền tảng hỗ trợ. Nhưng nó cần cấu hình OS thích hợp; đặt chế độ bắt buộc khi thiếu huge pages có thể khiến server không khởi động được.

Đừng nhầm huge pages cấu hình có chủ đích với transparent huge pages của OS. Cần kế hoạch vận hành khi thay đổi.

## 22. Những tình huống chẩn đoán

### 22.1. Shared-buffer reads cao, query chậm

Có thể do working set lớn hoặc truy vấn phải đọc nhiều trang không cần thiết. Trước khi tăng shared_buffers:

- Kiểm tra điều kiện `WHERE` và index.
- Xem số hàng/khối được đọc.
- Xác định tuần tự quét dữ liệu có cần thiết không.
- Kiểm tra OS page cache và I/O vật lý.
- Xem liệu dữ liệu nóng có thể nằm trong cache khi tăng hợp lý không.

Tối ưu SQL có thể hiệu quả hơn tăng RAM nếu truy vấn đang quét một lượng dữ liệu không cần thiết.

### 22.2. Hit ratio cao nhưng query vẫn chậm

Có thể do:

- CPU xử lý quá nhiều tuple.
- Sort/hash spill ra tệp tạm.
- Lock wait hoặc deadlock.
- Query plan join không tốt.
- Kết quả quá lớn khiến network/client chậm.

Hãy xem `EXPLAIN (ANALYZE, BUFFERS)`, temp counters và wait events.

### 22.3. Báo cáo chạy đơn lẻ nhanh, giờ cao điểm OOM

Rất có thể nhiều query memory-intensive đang chạy đồng thời. Cần xét:

1. Số query active.
2. Work_mem theo từng operation.
3. hash_mem_multiplier.
4. Parallel workers.
5. Backend private memory.
6. Autovacuum/maintenance.
7. Cgroup limit và OS available.

Không tăng thêm `work_mem` toàn cục khi chưa hiểu nguyên nhân.

### 22.4. Nhiều temporary files

Tệp tạm của sort/hash không được giải quyết trực tiếp bằng `temp_buffers`. Cần kiểm tra query plan, sort, hash, số hàng trung gian, `work_mem` và tính phù hợp của index.

### 22.5. I/O tăng vào checkpoint

Nếu I/O tăng theo nhịp ghi dirty pages/checkpoint, hãy xem các thống kê checkpoint, WAL, backend writes và năng lực thiết bị theo phiên bản PostgreSQL.

Không mặc định tăng work_mem hoặc temp_buffers sẽ sửa được vấn đề checkpoint I/O.

### 22.6. OS cache giảm sau khi shared_buffers tăng

Nếu server có RAM cố định, tăng vùng shared buffers có thể làm giảm headroom cho OS file cache và backend. Kết quả có thể cải thiện hoặc xấu đi tùy truy cập dữ liệu.

Phải đo toàn hệ thống trước/sau, không chỉ một tham số.

## 23. Quy trình điều chỉnh bộ nhớ an toàn

Một trình tự vận hành:

**Bước 1 — Xác định triệu chứng.** Query chậm, temp files nhiều, I/O vật lý tăng hay OOM?

**Bước 2 — Ghi cấu hình hiện tại.**

~~~sql
SELECT name, setting, unit, context, source
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'hash_mem_multiplier',
    'temp_buffers',
    'maintenance_work_mem',
    'effective_cache_size',
    'max_connections'
)
ORDER BY name;
~~~

**Bước 3 — Quan sát workload.** Số backend active, các báo cáo chạy đồng thời, các node sort/hash và tác vụ maintenance.

**Bước 4 — Phân tích query trọng điểm.** Dùng `EXPLAIN (ANALYZE, BUFFERS)` ở môi trường an toàn, xem shared hits/reads và temp read/write.

**Bước 5 — Lập ngân sách RAM.** Tính shared memory, backend private memory, maintenance, OS cache và vùng dự phòng; dùng giới hạn container nếu có.

**Bước 6 — Thay đổi phạm vi nhỏ nhất.** Nếu chỉ một báo cáo cần sort memory cao hơn, thử `SET LOCAL work_mem` dưới concurrency được kiểm soát trước khi thay đổi toàn hệ thống.

**Bước 7 — Nếu đổi shared_buffers, có kế hoạch restart.** Xác định thời điểm triển khai, mức sử dụng bộ nhớ của OS và cách quay về cấu hình cũ.

**Bước 8 — Đo trước/sau.** Độ trễ, disk/temp I/O, memory available, swap, OOM, CPU, workload và độ ổn định.

Đừng thay đổi cùng lúc mọi tham số. Nếu tăng shared_buffers, work_mem, max_connections và parallel workers trong một lần, rất khó xác định sự thay đổi nào đem lại lợi ích hoặc gây sự cố.

## 24. Những sai lầm phổ biến

### 24.1. “Shared buffers là cache duy nhất”

Sai. OS page cache cũng có thể giữ trang file. Shared-buffer miss không đảm bảo có physical disk read.

### 24.2. “effective_cache_size cấp RAM”

Sai. Đây là ước lượng dành cho planner, không phải bộ nhớ được cấp phát.

### 24.3. “work_mem là giới hạn cho toàn session”

Sai. Nó là ngân sách cho từng thao tác phù hợp; query có thể có nhiều node và workers.

### 24.4. “Mỗi connection cấp đủ work_mem ngay khi mở”

Sai. Bộ nhớ phục vụ sort/hash thường được cấp theo nhu cầu. Nhưng connection vẫn có chi phí nền.

### 24.5. “Tăng temp_buffers chữa ORDER BY spill”

Không trực tiếp. Sort/hash spill thường liên quan `work_mem` và plan; temp_buffers phục vụ trang temporary table.

### 24.6. “blks_read bằng physical disk reads”

Không chắc. OS cache có thể cung cấp dữ liệu dù shared-buffer miss được ghi nhận.

### 24.7. “Hit ratio 99% là hệ thống hoàn toàn khỏe”

Không đủ. Query còn có CPU, locks, temp I/O, WAL và chi phí khác.

### 24.8. “Cộng RSS các postgres process là ra RAM dùng thật”

Có thể đếm lặp shared memory. Cần metric toàn hệ thống/cgroup và phân biệt private/shared phù hợp.

### 24.9. “Free RAM thấp là luôn thiếu RAM”

Không. Cache OS có thể thu hồi. Xem available, swap và memory pressure.

### 24.10. “Shared buffers càng lớn càng nhanh”

Không có quy tắc như vậy. Tăng quá mức làm giảm headroom cho các phần còn lại.

### 24.11. “Có VACUUM tự động nên không cần tính RAM bảo trì”

Autovacuum workers vẫn dùng tài nguyên, có thể chạy đồng thời và ảnh hưởng ngân sách RAM.

### 24.12. “max_connections tăng thì throughput tăng tương ứng”

Không chắc. Quá nhiều backend có thể gây cạnh tranh RAM, CPU, I/O; connection pooling thường giúp kiểm soát hơn.

### 24.13. “EXPLAIN ANALYZE chỉ phân tích, không thực thi”

Sai. Nó thực sự thực thi SQL. Với DML, thao tác có thể thay đổi dữ liệu.

### 24.14. “Đặt work_mem hàng trăm MB cho mọi session là cách tối ưu nhanh nhất”

Có thể tạo OOM khi nhiều query cùng có nhiều sort/hash nodes. Thay đổi theo workload, query và concurrency.

## 25. Bảng so sánh các tham số cốt lõi

| Tham số | Vai trò | Phạm vi/chú ý |
|---|---|---|
| `shared_buffers` | Cache trang table/index | Dùng chung toàn instance, thường cần restart |
| `wal_buffers` | Đệm WAL records | Vùng dùng chung, liên quan logging/recovery |
| `work_mem` | Bộ nhớ cơ bản cho sort/hash operation | Theo thao tác, không phải toàn session |
| `hash_mem_multiplier` | Ngân sách bổ sung cho hash | Không phải một cache được cấp phát riêng |
| `temp_buffers` | Cache trang temporary table | Cục bộ theo session, cấp theo nhu cầu |
| `maintenance_work_mem` | Bộ nhớ cho một số công việc bảo trì | Phụ thuộc thao tác/cấu hình |
| `autovacuum_work_mem` | Bộ nhớ cho autovacuum workers | Có thể kế thừa maintenance_work_mem |
| `effective_cache_size` | Ước lượng cache cho planner | **Không cấp phát RAM** |
| `max_connections` | Giới hạn kết nối | Ảnh hưởng concurrency và chi phí backend |
| `max_parallel_workers_per_gather` | Giới hạn song song theo kế hoạch | Có thể tăng nhu cầu memory |
| `temp_file_limit` | Giới hạn một số tệp tạm trên đĩa | Không phải RAM và không bao trùm mọi temp storage |
| `huge_pages` | Cách quản lý shared memory trên nền tảng hỗ trợ | Có thể cần chuẩn bị OS |

## 26. Bài tập vận dụng

### Bài 1 — Cache hit và disk read

Một query báo `Buffers: shared hit=300 read=40`. Có thể kết luận SSD đã thực hiện đúng 40 lượt đọc vật lý không?

**Gợi ý:** Không. OS page cache có thể phục vụ block mà shared buffers chưa giữ.

### Bài 2 — effective_cache_size

Máy có `shared_buffers = 2GB` và `effective_cache_size = 8GB`. Có phải PostgreSQL đã cấp phát 10 GiB cho hai vùng này?

**Gợi ý:** Không. effective_cache_size là ước lượng planner.

### Bài 3 — Nhiều work_mem

Một query có hai sort node và một hash join. Vì sao một session có thể sử dụng nhiều hơn `work_mem`?

**Gợi ý:** Có nhiều thao tác riêng và hash multiplier; một số node có thể giữ memory đồng thời.

### Bài 4 — Temp table và sort spill

Trường hợp nào liên quan `temp_buffers`, trường hợp nào liên quan `work_mem`: tạo temporary table để lưu ID, hay sort một triệu hàng và ghi temporary file?

**Gợi ý:** Temp table dùng local buffers; sort dùng work_mem.

### Bài 5 — 200 connection

Server có `max_connections = 200` nhưng chỉ 15 backend active. Có thể nhân `200 * work_mem` để kết luận RAM hiện tại đang dùng không?

**Gợi ý:** Không, vì work_mem cấp theo thao tác và nhu cầu thực tế; backend idle vẫn có bộ nhớ nền.

### Bài 6 — Đọc sort trong EXPLAIN

Bạn thấy `Sort Method: external merge</BT> và `temp written</BT> lớn. Những cấu hình và yếu tố nào nên xem trước?

**Gợi ý:** work_mem, query plan, số hàng trung gian, index, parallelism và concurrency.

### Bài 7 — OS page cache

Linux báo RAM free thấp nhưng available khá cao, swap không tăng. Có thể kết luận máy thiếu RAM không?

**Gợi ý:** Chưa. OS có thể dùng RAM làm page cache có thể thu hồi.

### Bài 8 — Commit và WAL

Transaction commit thành công trong khi một dirty heap page còn trong shared buffers. Điều này có nhất thiết làm mất tính bền vững không?

**Gợi ý:** Không. WAL và chính sách durability cho phép trang dữ liệu được ghi về file sau theo cơ chế PostgreSQL.

### Bài 9 — OOM giờ cao điểm

Sau khi nâng work_mem toàn cục, báo cáo đơn lẻ nhanh hơn nhưng server bị OOM khi 30 báo cáo chạy đồng thời. Hãy đề xuất cách giảm rủi ro.

**Gợi ý:** Giảm cấu hình toàn cục, tăng cục bộ cho job cần thiết, giới hạn query concurrency, xem parallel workers/hash multiplier, và tối ưu SQL.

### Bài 10 — Phép đo shared hit

Viết truy vấn lấy tỷ lệ shared-buffer hit và `stats_reset` từ `pg_stat_database`. Vì sao nên so chênh lệch giữa hai snapshot?

**Gợi ý:** Counter tích lũy có thể che khuất biến động gần đây; sau reset phải bắt đầu mốc mới.

### Bài 11 — Lập ngân sách

Server có 32 GiB RAM và shared_buffers = 8 GiB. Nêu ít nhất sáu nhóm RAM khác cần xét trước khi tăng shared_buffers lên 24 GiB.

**Gợi ý:** OS page cache, backend state, sort/hash, autovacuum, WAL/shared structures, parallel workers, kernel/agents và headroom.

### Bài 12 — Đo backend memory

View `pg_backend_memory_contexts` có cho biết bộ nhớ của tất cả kết nối trong cluster không?

**Gợi ý:** Không. Nó chủ yếu phản ánh memory contexts của backend hiện tại theo quyền và phiên bản hỗ trợ.

## 27. Ghi nhớ nhanh

| Câu hỏi | Đáp án |
|---|---|
| Shared buffers chứa gì? | Trang table/index được cache dùng chung |
| Shared buffers cấp theo connection? | Không, ở cấp PostgreSQL instance |
| Shared-buffer miss có nghĩa SSD đọc? | Không nhất thiết; còn OS page cache |
| Cache hit cao có nghĩa query luôn nhanh? | Không |
| work_mem là ngân sách của gì? | Mỗi sort/hash operation phù hợp |
| Một query có thể dùng nhiều work_mem? | Có, vì nhiều node/worker |
| temp_buffers dùng cho gì? | Temporary tables của session |
| Sort spill có liên quan temp_buffers trực tiếp? | Không, chủ yếu xem work_mem và plan |
| maintenance_work_mem dùng cho gì? | Một số thao tác bảo trì |
| effective_cache_size có cấp phát bộ nhớ? | Không, phục vụ planner |
| WAL buffers giống shared_buffers? | Không |
| Đo hit/read ở đâu? | pg_stat_database, pg_statio..., EXPLAIN BUFFERS |
| Đo temp file ở đâu? | pg_stat_database, EXPLAIN và log_temp_files |
| Có nên cộng RSS của mọi backend? | Không máy móc vì shared pages có thể bị đếm nhiều lần |
| max_connections bằng concurrent heavy queries? | Không |
| Tăng shared_buffers luôn tốt? | Không, phải cân bằng tài nguyên |
| Kiểm tra cấu hình ở đâu? | SHOW và pg_settings |
| Lệnh EXPLAIN ANALYZE có chạy query? | Có |
| Khi OOM cần quan sát gì? | OS/cgroup, backend concurrency, work_mem, maintenance, parallel và plan |

---

## Kết luận

PostgreSQL sử dụng **nhiều lớp bộ nhớ phối hợp**. **Shared buffers** cache trang relation cho các backend cùng dùng; **bộ nhớ riêng của backend** phục vụ trạng thái phiên và các phép xử lý như sort/hash; còn **OS page cache** giữ trang file ở tầng hệ điều hành và có thể giúp tránh I/O vật lý ngay cả khi PostgreSQL ghi nhận shared-buffer miss. WAL buffers và các cấu trúc dùng chung khác phục vụ những mục tiêu riêng của engine.

Khi điều chỉnh bộ nhớ, phải phân biệt **tham số cấp phát thực sự** với **tham số ước lượng** như `effective_cache_size`; phân biệt **work_mem theo thao tác** với ngân sách toàn session; và phân biệt **cache miss** với **đọc thiết bị**. Một báo cáo đơn lẻ nhanh không bảo đảm hệ thống ổn định khi nhiều query đồng thời cần RAM.

Cách tiếp cận đáng tin cậy là quan sát cấu hình qua `pg_settings`, số liệu shared hits/reads và temporary files qua các statistics views, kế hoạch truy vấn qua `EXPLAIN (ANALYZE, BUFFERS)`, rồi kết hợp memory available, swap, I/O và giới hạn container. Chỉ sau khi hiểu workload và headroom mới quyết định thay đổi. Nắm vững ba lớp bộ nhớ giúp tối ưu PostgreSQL dựa trên số đo thay vì tăng các tham số theo cảm tính.
