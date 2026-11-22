# Thiết kế khóa phân cụm cho điều kiện theo khoảng hoặc thứ tự

> **Chương:** Tối ưu truy vấn  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, hệ cơ sở dữ liệu phân tán wide-column; trọng tâm gồm khóa phân vùng, thiết kế bảng theo truy vấn, nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối ứng dụng Java.

Khi người dùng yêu cầu “lấy 50 sự kiện mới nhất của thiết bị” hoặc “tìm các giao dịch trong khoảng thời gian từ A đến B”, quyết định quan trọng nhất thường nằm ở **khóa chính của bảng**, đặc biệt là **clustering key**. Trong Apache Cassandra, partition key xác định partition và các replica chứa dữ liệu; các cột clustering xác định thứ tự **bên trong từng partition** và những điều kiện theo khoảng mà Cassandra có thể xử lý hiệu quả.

Một bảng có nhiều cột, index hoặc dữ liệu đã được nạp vẫn có thể không đáp ứng được `WHERE event_time >= ...` hay `ORDER BY event_time DESC` như mong đợi. Cassandra không phải cơ sở dữ liệu quan hệ tự tạo kế hoạch sắp xếp hoặc join tùy ý; mô hình thông dụng là **thiết kế bảng cho truy vấn cần phục vụ**.

Bài học hướng dẫn cách chọn **thứ tự clustering columns**, dùng tiền tố điều kiện bằng nhau (equality prefix), đặt cột cần lọc theo khoảng tiếp theo, quản lý thứ tự tăng/giảm, phân trang và kiểm chứng bằng dữ liệu thực thi.

## 1. Mục tiêu học tập

Hoàn thành bài, bạn có thể:

1. Phân biệt partition key, clustering key và các cột dữ liệu thường trong `PRIMARY KEY` của Cassandra.
2. Chọn thứ tự cột clustering cho truy vấn có điều kiện `=`, `>`, `>=`, `<`, `<=` và `ORDER BY`.
3. Giải thích tại sao điều kiện theo khoảng trên cột clustering thường cần **các cột clustering đứng trước bị ràng buộc bằng nhau**.
4. Dự đoán truy vấn nào có thể đọc tuần tự một đoạn trong partition, truy vấn nào cần mô hình bảng khác hoặc phải lọc tốn kém.
5. Chọn `CLUSTERING ORDER BY`, bucket thời gian và tie-breaker phù hợp để tránh partition quá rộng và thứ tự kết quả không xác định.
6. Thực hành CQL, quan sát tracing/metrics và đọc kết quả có phân trang từ Java Driver.

## 2. Hai phần của PRIMARY KEY phục vụ hai nhiệm vụ

Xét bảng sự kiện thiết bị:

~~~sql
CREATE TABLE events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Trong khai báo `PRIMARY KEY ((device_id, event_day), event_time, event_id)`:

| Thành phần | Vai trò | Tác động lên truy vấn |
|---|---|---|
| `(device_id, event_day)` | **Partition key tổng hợp** | Xác định partition cụ thể và token/replica; nên xuất hiện đầy đủ trong truy vấn cần truy cập trực tiếp |
| `event_time` | **Clustering column thứ nhất** | Sắp xếp thời gian trong một partition; hỗ trợ quét một khoảng thời gian sau khi biết partition |
| `event_id` | **Clustering column thứ hai** | Phân biệt nhiều sự kiện trùng timestamp và ổn định thứ tự trong nhóm cùng thời gian |
| `event_type, payload` | Cột dữ liệu thông thường | Không tự động tạo thứ tự truy cập hoặc cho phép lọc hiệu quả nếu không thiết kế thêm cơ chế |

**Đừng nhầm:** số cặp ngoặc trong `PRIMARY KEY` có ý nghĩa. Với `PRIMARY KEY ((device_id, event_day), event_time, event_id)`, hai cột đầu tạo **một partition key tổng hợp**, còn hai cột sau tạo **clustering key**. Điều đó khác với `PRIMARY KEY (device_id, event_day, event_time, event_id)`, nơi chỉ `device_id` là partition key.

Các hàng có cùng `device_id` và `event_day` nằm trong cùng partition, được truy xuất theo thứ tự khóa clustering. Cấu trúc SSTable, memtable và nhiều phiên bản dữ liệu có thể nằm ở các file khác nhau; hiểu “được sắp xếp” là **thứ tự logic trong partition**, không phải cam kết mọi bản ghi nằm liền trong một file vật lý.

~~~mermaid
flowchart TB
    Q["WHERE device_id = X AND event_day = D"] --> P["Partition (X, D)"]
    P --> A["event_time 09:05 — event_id 0a..."]
    A --> B["event_time 09:05 — event_id 9b..."]
    B --> C["event_time 08:42 — event_id 14..."]
    C --> D["event_time 08:01 — event_id 3e..."]
~~~

Đây là chiều đọc mặc định do `WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)`: thời gian mới trước, và nếu cùng thời gian thì event_id tăng dần.

## 3. Quy tắc equality prefix và range: thứ tự cột quan trọng

### 3.1. Một quy tắc thiết kế hữu ích

Với clustering key nhiều cột `(c1, c2, c3)`, dạng truy vấn tự nhiên nhất là:

~~~text
Partition key: đầy đủ giá trị cụ thể
Clustering:    c1 = ... AND c2 = ... AND c3 >= lower AND c3 < upper
                              ^^^^^^^^^^^^^^^       ^^^^^^^^^^^^^^^
                              tiền tố bằng nhau      cột đầu tiên dùng range
~~~

Cassandra có thể định vị phần đầu của đoạn clustering dựa trên tiền tố `c1, c2`, rồi quét đoạn thỏa điều kiện khoảng của `c3`. Nếu bỏ qua `c1` để lọc `c2` theo khoảng, dữ liệu theo `c2` thường nằm trong nhiều nhóm `c1`, không còn tạo thành một đoạn liên tục cho cách truy cập này.

**Nguyên tắc thực dụng:** đặt các cột thường được giới hạn bằng `=` ở đầu clustering key; đặt cột dùng range hoặc ordering ngay sau tiền tố đó. Sau một điều kiện range, đừng giả định có thể tiếp tục lọc/sắp xếp tùy ý theo các cột clustering đứng sau như một truy vấn SQL quan hệ. CQL có một số dạng so sánh tuple hoặc giới hạn khác theo phiên bản, nhưng cần kiểm tra tính hợp lệ và tính hữu dụng riêng cho từng truy vấn.

### 3.2. Ví dụ với (event_time, event_id)

Giả sử truy vấn chỉ cần thiết bị X, ngày D và khoảng giờ 08:00–09:00:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
ORDER BY event_time DESC, event_id ASC
LIMIT 50;
~~~

Truy vấn này có ba đặc điểm đáng chú ý:

1. `WHERE` cho đủ hai cột partition key nên Cassandra biết partition cần đọc.
2. `event_time` là clustering column đầu tiên; hai biên tạo thành một **đoạn liên tục** theo thứ tự clustering trong partition.
3. `ORDER BY` đúng với thứ tự đã khai báo, nên hệ thống có thể trả kết quả theo thứ tự clustering mà không cần sort tùy ý toàn bộ tập bản ghi.

Dùng khoảng **nửa mở** `[start, end)` (bao gồm đầu, loại trừ cuối) giúp nối nhiều cửa sổ liên tiếp mà không đếm hai lần sự kiện tại biên. Ví dụ 08:00–09:00 dùng `>= 08:00` và `< 09:00`; 09:00–10:00 bắt đầu từ `>= 09:00`.

Với nhiều sự kiện có cùng `event_time`, `event_id` là tie-breaker. Nếu chỉ đặt `event_time` làm clustering key thì mọi lần ghi có cùng partition và cùng timestamp thành **cùng một hàng logic** (update/upsert), dễ làm mất nhiều sự kiện độc lập. Thêm `event_id` vào clustering key cho phép lưu từng sự kiện riêng.

### 3.3. Hai thứ tự clustering không tương đương nhau

Giả sử có các truy vấn:

- **Q1:** “Cho biết mọi sự kiện của thiết bị X trong ngày D, theo thời gian mới nhất.”
- **Q2:** “Cho biết các sự kiện `ERROR` của thiết bị X trong ngày D, theo thời gian.”

Mô hình A:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

Mô hình B:

~~~sql
PRIMARY KEY ((device_id, event_day), event_type, event_time, event_id)
~~~

So sánh:

| Truy vấn | Mô hình A: `(event_time, event_id)` | Mô hình B: `(event_type, event_time, event_id)` |
|---|---|---|
| Q1: mọi type, quét thời gian | **Phù hợp:** time là clustering đầu tiên | **Không phù hợp trực tiếp:** dữ liệu được nhóm theo event_type trước thời gian |
| Q2: chỉ `ERROR` và thời gian | Muốn lọc `event_type` phải có cách khác hoặc đọc/rà các hàng rồi lọc phía ứng dụng | **Phù hợp:** `event_type = 'ERROR'`, sau đó range trên `event_time` |
| Thứ tự toàn bộ event theo thời gian | Có trong từng partition | Không có trên toàn partition vì thứ tự chính là `event_type` |

Trong Cassandra, nếu cả Q1 và Q2 đều quan trọng với khối lượng lớn, giải pháp thường là **hai bảng được thiết kế theo hai truy vấn**, ví dụ `events_by_device_day` và `events_by_device_type_day`. Ứng dụng ghi cùng sự kiện logic vào cả hai; chi phí là thêm dung lượng, write amplification, kế hoạch duy trì dữ liệu và quy tắc retry/idempotency.

## 4. CLUSTERING ORDER BY: chiều đọc trong một partition

### 4.1. Mặc định ASC; khai báo DESC theo nhu cầu thường dùng

Nếu không khai báo `WITH CLUSTERING ORDER BY`, cột clustering mặc định có chiều tăng (ASC). Với feed sự kiện mà UI thường lấy các bản ghi mới nhất, khai báo:

~~~sql
WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
~~~

giúp việc đọc từ đầu partition theo chiều **mới → cũ** phù hợp yêu cầu. Nếu đọc từ cũ → mới, Cassandra có thể đọc theo thứ tự đảo ngược phù hợp:

~~~sql
SELECT event_time, event_id, payload
FROM events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
ORDER BY event_time ASC, event_id DESC;
~~~

Hai thứ tự ở trên là **thứ tự khai báo** và **thứ tự đảo của toàn bộ chuỗi clustering**, không phải quyền chọn ASC/DESC tùy ý và độc lập cho từng cột. Với bảng có chiều hỗn hợp `(DESC, ASC)`, chiều đảo phù hợp là `(ASC, DESC)`. Đảo chiều đọc có thể có chi phí khác nhau theo workload và cấu trúc SSTable; nên đo trên dữ liệu đại diện.

### 4.2. Giới hạn của ORDER BY trong Cassandra

Các quy tắc căn bản:

- `ORDER BY` thông thường chỉ áp dụng cho **clustering columns** trong partition có **partition key được xác định đầy đủ**.
- Thứ tự sắp xếp bị ràng buộc bởi cách khai báo clustering key và chiều đảo hợp lệ; nó **không** cho phép `ORDER BY payload` tùy ý khi `payload` là cột thường.
- Một partition theo `device_id + event_day` chỉ đảm bảo thứ tự **trong ngày đó**. Nó không tạo kết quả toàn cục đã sắp xếp trên nhiều ngày, thiết bị hoặc node.
- Chỉ mục thứ cấp/SAI có thể giúp tìm theo một số điều kiện, nhưng không tự biến Cassandra thành một công cụ sort tùy ý trên nhiều partition.
- `ALLOW FILTERING` cho phép một số dạng truy vấn cần lọc nhiều dữ liệu; nó **không** sửa mô hình thứ tự của clustering key và thường không thích hợp làm giải pháp hiệu năng dài hạn.

Ví dụ sau **không phải** truy vấn phù hợp với bảng hiện tại:

~~~sql
-- Minh họa một yêu cầu cần mô hình khác; không chạy như truy vấn lab hợp lệ.
SELECT event_time, payload
FROM events_by_device_day
ORDER BY event_time DESC;
~~~

Thiếu `WHERE` giới hạn partition key: Cassandra không thể đưa ra thứ tự thời gian tổng thể qua tất cả partition bằng một lệnh `ORDER BY` như trong cơ sở dữ liệu quan hệ.

### 4.3. LIMIT không phải phép sắp xếp

`LIMIT 50` chỉ giới hạn lượng kết quả trả về. Nếu thứ tự clustering không tương ứng với “50 bản ghi mới nhất”, thêm `LIMIT 50` **không sửa được**. Một index hoặc lọc phía server cũng không làm `LIMIT 50` trở thành “top 50” đúng nghiệp vụ nếu thiếu cơ chế ordering phù hợp.

Ví dụ:

| Khóa clustering | `LIMIT 50` trả gì? |
|---|---|
| `(event_time DESC, event_id ASC)` | 50 sự kiện đầu tiên theo thời gian mới nhất trong partition |
| `(event_type ASC, event_time DESC)` không có `event_type = ?` | 50 hàng đầu tiên của các nhóm type đứng trước; **không** phải 50 sự kiện mới nhất của mọi type |
| Không có giới hạn partition | Không có bảo đảm global top 50 chỉ bằng `ORDER BY` thông thường |

## 5. Thiết kế cột clustering khi có nhiều điều kiện lọc

### 5.1. Trường hợp tiền tố bằng nhau rồi đến khoảng

Khi chức năng yêu cầu “sự kiện `ERROR` của tenant T trong ngày D từ 08:00 đến 09:00”, có thể chọn:

~~~sql
CREATE TABLE events_by_tenant_type_day (
    tenant_id uuid,
    event_day date,
    event_type text,
    event_time timestamp,
    event_id uuid,
    message text,
    PRIMARY KEY ((tenant_id, event_day), event_type, event_time, event_id)
) WITH CLUSTERING ORDER BY (
    event_type ASC,
    event_time DESC,
    event_id ASC
);
~~~

Truy vấn phù hợp:

~~~sql
SELECT event_time, event_id, message
FROM events_by_tenant_type_day
WHERE tenant_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_type = 'ERROR'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z';
~~~

Vì `event_type` đứng trước `event_time` trong clustering key và được ràng buộc bằng nhau, các sự kiện `ERROR` trong khoảng giờ là một đoạn có thể quét hiệu quả theo thứ tự thời gian đã khai báo.

Truy vấn **không phù hợp trực tiếp**:

~~~sql
-- Minh họa anti-pattern; có thể bị Cassandra từ chối.
SELECT event_time, event_id, message
FROM events_by_tenant_type_day
WHERE tenant_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z';
~~~

Ở đây thiếu điều kiện bằng nhau cho cột clustering đứng trước là `event_type`. Hệ thống không thể giả định các hàng được sắp xếp toàn partition theo `event_time`. Không dùng `ALLOW FILTERING` để che đi một thiết kế ngược với truy vấn chính.

### 5.2. Chọn thứ tự cột dựa trên loại phép so sánh

| Nhu cầu | Gợi ý thiết kế | Lý do |
|---|---|---|
| Lấy lịch sử của một thiết bị trong một ngày | Partition `(device_id, day)`; clustering `(event_time, event_id)` | Range và ordering theo thời gian trực tiếp |
| Lấy lịch sử theo **loại** và thời gian | Partition `(device_id, day)`; clustering `(event_type, event_time, event_id)` | Equality trên type, range trên time |
| Lấy lịch sử theo **trạng thái** và thời gian | Cân nhắc partition `(tenant_id, status, bucket)`; clustering `(updated_at, row_id)` | Theo status là truy vấn chủ lực, nhóm từ partition key |
| Lấy sự kiện mới nhất của **tất cả** thiết bị | Cần bảng/aggregate theo phạm vi nghiệp vụ (nhóm, ngày, shard) rồi merge | Không thể có global ordering chỉ từ bảng phân vùng theo thiết bị |
| Tìm mọi event theo `event_id` | Bảng tra cứu theo `event_id` hoặc cơ chế truy cập phù hợp | event_id clustering thứ hai không tạo lookup toàn cụm độc lập |

Một cột có cardinality lớn không nhất thiết phải đặt trước, và một cột có cardinality nhỏ không nhất thiết đặt sau. Thứ tự phụ thuộc **mẫu `WHERE`**: những điều kiện có equality ổn định đứng trước range, kết hợp với kích thước partition và khả năng cập nhật khóa.

### 5.3. Cột clustering có xu hướng thay đổi là lựa chọn rủi ro

Giả sử dùng `updated_at` làm clustering column cho một hàng ticket và mỗi lần sửa ticket lại thay `updated_at`. Trong Cassandra, **clustering key là một phần định danh hàng**. Thay đổi giá trị clustering không phải cập nhật vị trí của cùng hàng: ứng dụng thường phải **DELETE khóa cũ và INSERT khóa mới**.

Điều đó có thể sinh tombstone, ghi nhiều lần và trạng thái tạm lệch khi ứng dụng dual-write. Với dữ liệu dạng sự kiện **append-only**, `event_time` là lựa chọn tự nhiên; với bản ghi mutable như ticket, cân nhắc tách bảng theo ID làm source of truth và bảng read model theo cập nhật mới nhất, kèm cơ chế đồng bộ/idempotency.

## 6. Chọn partition key và time bucket trước khi tối ưu range

Clustering key không giải quyết được partition quá lớn hoặc nóng. Nếu tạo bảng:

~~~sql
PRIMARY KEY ((device_id), event_time, event_id)
~~~

thì toàn bộ lịch sử của thiết bị dồn vào một partition. Truy vấn theo thời gian vẫn hợp lệ về mặt CQL, nhưng với hàng triệu/billions sự kiện, partition có thể rất rộng; nhiều mutation cùng thiết bị đổ lên cùng một nhóm replica, gây hot partition, chi phí compaction/tombstone và read amplification.

Thêm bucket ngày:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

giới hạn vòng đời/khối lượng của mỗi partition theo ngày nhưng yêu cầu client **biết ngày** trong truy vấn. Nếu người dùng hỏi “50 sự kiện mới nhất, có thể nằm ở nhiều ngày”, ứng dụng cần:

1. Đọc partition của ngày hiện tại theo `event_time DESC`, dùng `LIMIT` hợp lý.
2. Nếu chưa đủ 50 hàng, đọc partition ngày trước đó; tiếp tục cho tới khi đủ hoặc đạt giới hạn truy vấn.
3. Nếu phải gộp nhiều device/shard, merge các stream theo cùng tiêu chí thời gian và tie-breaker ở ứng dụng/dịch vụ tổng hợp.
4. Quản lý fan-out, request concurrency, timeout và token/phân trang; không quét hàng nghìn bucket cho mỗi lần mở màn hình nếu có thể duy trì read model thích hợp.

### 6.1. Chọn độ rộng bucket dựa trên số liệu

| Bucket | Ưu điểm | Chi phí |
|---|---|---|
| Theo tháng | Ít partition, truy vấn khoảng dài cần ít request | Partition lớn hơn, hot key dễ xảy ra |
| Theo ngày | Cân bằng cho nhiều workload thời gian | Truy vấn xuyên ngày cần phối hợp |
| Theo giờ | Phân tán dữ liệu của thiết bị tần suất cao | Nhiều partition, nhiều request nếu truy vấn dài |
| Theo giờ + shard | Chia tải của một thiết bị quá nóng | Phải tra nhiều shard và merge kết quả theo thứ tự |

Ví dụ 3.600 sự kiện/giờ với payload trung bình 500 byte tương đương **khoảng 1,8 MB payload/giờ** trước overhead metadata, index, compression và replica; dữ liệu 30 ngày không thể suy chính xác dung lượng SSTable chỉ từ phép nhân này. Hãy đo kích thước partition thực bằng `nodetool tablehistograms`, bộ chỉ số per-table và phân phối p95/p99 của khối lượng ghi theo thiết bị.

### 6.2. Truy vấn giao hai ngày không phải một đoạn clustering liên tục

Ví dụ “từ 23:50 ngày 20 đến 00:10 ngày 21” với partition key `(device_id, event_day)`:

~~~text
Partition ngày 20: event_time >= 23:50 và < 24:00
Partition ngày 21: event_time >= 00:00 và < 00:10
Ứng dụng hợp nhất hai tập đã sắp xếp theo event_time
~~~

Mỗi partition có thứ tự riêng. Cassandra **không cung cấp global ORDER BY** giữa hai partition này; chỉ viết thêm `ORDER BY event_time DESC` vào một câu có hai partition không bảo đảm kết quả toàn cục như yêu cầu.

## 7. Lab CQL: tạo bảng, nạp dữ liệu và kiểm tra khoảng/thứ tự

### 7.1. Chuẩn bị

Thực hành trên Cassandra 4.x–5.x trong **cluster lab**, có `cqlsh` và `nodetool`. Ví dụ sau giả định datacenter thật sự tên `dc1` và có ít nhất ba node; xác minh bằng `nodetool status`, sau đó chỉnh RF/DC cho đúng trước khi chạy:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_query_tuning
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_query_tuning.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Chú ý:** `IF NOT EXISTS` không thay schema của keyspace hoặc bảng đã tồn tại; cần `DESCRIBE TABLE lab_query_tuning.events_by_device_day` để xác nhận khóa và chiều clustering thật. Không dùng cấu hình RF cao hơn số node khả dụng rồi suy diễn độ trễ hay tính sẵn sàng từ lab.

### 7.2. Chèn dữ liệu có một cặp trùng timestamp

~~~sql
INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T07:45:00Z',
    49dc0401-2d82-48ae-96cb-c397150639ce,
    'INFO',
    'boot'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    080d0004-4dd6-49e4-8759-28e8365c4101,
    'WARN',
    'voltage-low'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    ed2c3c12-e91a-47de-8c30-c58353014a2b,
    'ERROR',
    'sensor-timeout'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:42:00Z',
    6db5b4cc-e3d7-4ab0-a5f4-2350d4d6b24c,
    'INFO',
    'recovered'
);

INSERT INTO lab_query_tuning.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T09:15:00Z',
    38444992-e82b-4adb-97a6-7546cc5fb03c,
    'INFO',
    'periodic-sample'
);
~~~

Tất cả năm hàng thuộc cùng một partition. Hai sự kiện lúc `08:05` có event_id khác nhau nên **không ghi đè nhau**.

### 7.3. Kiểm tra ba kiểu SELECT

**A — Mới nhất trong ngày:**

~~~sql
SELECT event_time, event_id, event_type, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
LIMIT 3;
~~~

Theo thứ tự mặc định `DESC, ASC`, kết quả dự kiến gồm `09:15`, `08:42`, rồi một trong hai sự kiện `08:05` theo thứ tự event_id tăng. Nếu cần cả hai sự kiện cùng thời điểm, dùng `LIMIT 4`. Đây là minh họa về **tie-breaker** và ý nghĩa của `LIMIT`.

**B — Khoảng [08:00, 09:00):**

~~~sql
SELECT event_time, event_id, event_type, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
ORDER BY event_time DESC, event_id ASC;
~~~

Kết quả dự kiến: `08:42` rồi **hai hàng** ở `08:05`; không có `07:45` và `09:15`. Cùng partition và cùng tiêu chí, chỉ thay các biên sẽ làm thay đổi đoạn quét.

**C — Đảo chiều đọc:**

~~~sql
SELECT event_time, event_id, event_type
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
ORDER BY event_time ASC, event_id DESC;
~~~

Kết quả thời gian đi từ `07:45` đến `09:15`; khi hai hàng có cùng thời gian, event_id được lấy theo chiều giảm. Để kiểm tra, đối chiếu chuỗi thời gian và các event_id, không chỉ đếm số hàng.

### 7.4. Bài thử “truy vấn không hợp lệ hoặc tốn chi phí”

Đọc hai câu sau như **tình huống phân tích**, không dùng chúng làm workload production:

~~~sql
-- Thiếu event_day trong partition key tổng hợp:
SELECT event_time, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_time >= '2026-11-21T08:00:00Z';

-- event_type là cột thường, không phải prefix clustering:
SELECT event_time, payload
FROM lab_query_tuning.events_by_device_day
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_type = 'ERROR';
~~~

Cassandra thường từ chối các dạng này nếu không có cơ chế lập chỉ mục/lọc thích hợp. Ngay cả nếu thêm `ALLOW FILTERING` để thử được ở lab, nguy cơ quét nhiều dữ liệu vẫn còn. Đề xuất thiết kế đúng phải xuất phát từ truy vấn thực: bổ sung điều kiện partition key, tạo bảng theo type/ngày, hoặc xem xét index khi phù hợp workload và đã đo.

### 7.5. Tracing và số liệu để xác nhận lợi ích

Trong `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
TRACING ON
~~~

Chạy từng câu truy vấn hợp lệ A/B/C, ghi lại trace, rồi tắt:

~~~text
TRACING OFF
~~~

Lệnh `CONSISTENCY` và `TRACING` là **lệnh của cqlsh**, không phải CQL DDL. CL `LOCAL_QUORUM` chỉ thích hợp khi keyspace/driver/DC lab được cấu hình đúng; khi đo phải giữ CL nhất quán giữa các biến thể.

Trên node Cassandra:

~~~bash
nodetool tablehistograms lab_query_tuning events_by_device_day
nodetool tablestats lab_query_tuning.events_by_device_day
nodetool tpstats
~~~

| Nguồn quan sát | Metric/chi tiết cần ghi | Điều có thể rút ra |
|---|---|---|
| Tracing | Replica tham gia, các bước đọc và thời gian từng pha | Đường xử lý thực tế của request |
| Java client | p50/p95/p99 end-to-end, timeout, số hàng và số trang | Trải nghiệm người dùng dưới tải |
| `tablehistograms` | Kích thước partition, SSTables per read, latency cục bộ | Partition quá lớn hoặc read amplification |
| `tablestats` | SSTables, read/write latency, thống kê bảng | Chi phí lưu trữ và đường đọc |
| `tpstats` | Pending/blocked/completed theo stage | Hàng đợi hoặc bottleneck ở node |

Không thể chứng minh một thiết kế “nhanh hơn” bằng việc hai câu chạy nhanh với năm hàng. Nạp nhiều partition với kích thước và phân phối đại diện, so cùng RF/CL và số hàng cần đọc; đo p95/p99 ở mức tải giống ứng dụng thực. Tracing có overhead; dùng trên mẫu request, không bật đại trà trong load test.

## 8. Phân trang: giữ đúng thứ tự khi dữ liệu tăng

### 8.1. LIMIT và fetch size không giống nhau

Trong Java Driver, `LIMIT 50` là **giới hạn số hàng của kết quả CQL**, còn `page size = 20` là gợi ý cách driver lấy **từng trang** trong quá trình đọc. Một truy vấn có thể trả 50 hàng qua nhiều trang; nếu đo đến trang đầu mà quên các trang sau, độ trễ thực tế sẽ bị đánh giá thấp.

Trên các partition lớn, tránh kiểu phân trang SQL `OFFSET 100000` rồi chọn hàng tiếp theo: Cassandra không cung cấp offset ngẫu nhiên hiệu quả cho từng trang như một B-tree index. Thông thường nên dùng **paging state** của driver (có ràng buộc query/parameters phù hợp) hoặc chiến lược **cursor theo clustering key** được thiết kế và kiểm chứng cho ứng dụng.

### 8.2. Java Driver 4.x: truy vấn theo partition/range có paging

Ví dụ sau giả định đã tạo `CqlSession session` và local datacenter đúng với keyspace:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, event_type, payload " +
    "FROM lab_query_tuning.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? " +
    "ORDER BY event_time DESC, event_id ASC LIMIT ?");

UUID deviceId =
    UUID.fromString("0f94e3b9-0b36-4930-91f2-606b44b5231b");
BoundStatement statement = prepared.bind(
        deviceId,
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T08:00:00Z"),
        Instant.parse("2026-11-21T09:00:00Z"),
        50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(20);

ResultSet result = session.execute(statement);
int count = 0;
for (Row row : result) {
    UUID id = row.getUuid("event_id");
    Instant eventTime = row.getInstant("event_time");
    // Xử lý id/eventTime và các trường thực sự cần cho nghiệp vụ.
    count++;
}
// Nếu có nhiều trang, vòng lặp ResultSet sẽ tải thêm khi cần.
~~~

Cần đo **thời gian và số trang thực tiêu thụ**, không chỉ thời gian lệnh `execute()` trả về. Paging state là con trỏ phụ thuộc truy vấn/bind variables và driver/protocol; không tái sử dụng tùy tiện cho truy vấn khác. Khi dữ liệu được chèn/xóa giữa các lần lấy trang, kết quả có thể thay đổi; Cassandra paging thông thường **không phải snapshot giao dịch**.

### 8.3. Tránh trôi trang khi có dữ liệu mới

Với feed “mới nhất trước”, sự kiện mới tiếp tục xuất hiện ở đầu partition trong khi người dùng đang cuộn. Có thể:

- Định nghĩa **high-watermark** ở lần lấy đầu tiên, ví dụ chỉ đọc `event_time < cutoff` cho các trang tiếp theo (đặt quy tắc biên và tie-breaker rõ ràng).
- Dùng paging state được phát ra từ truy vấn gốc và giữ nguyên filter/cutoff; chấp nhận rằng dữ liệu đồng thời có thể ảnh hưởng kết quả.
- Với yêu cầu chính xác cao, thiết kế cursor bằng toàn bộ khóa clustering, xử lý timestamp trùng nhau bằng `event_id` và kiểm tra cú pháp CQL/tuple comparison theo phiên bản thay vì chỉ dùng `WHERE event_time < last_time` (cách này có thể bỏ sót sự kiện có cùng timestamp).

Không nên dùng `OFFSET` mô phỏng bằng cách tải toàn bộ hàng rồi bỏ qua trên client nếu dữ liệu lớn: chi phí mạng, RAM và thời gian tăng theo vị trí trang.

## 9. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Đưa `event_time` làm cột thường rồi kỳ vọng `ORDER BY event_time` | CQL không có sorting tùy ý trên cột thường | Đưa time vào clustering key của bảng phục vụ truy vấn |
| Chọn `(event_type, event_time)` cho màn hình xem **mọi type** mới nhất | Dữ liệu nhóm theo type trước, không theo thời gian toàn partition | Dùng bảng có time đứng đầu hoặc read model chuyên dụng |
| Bỏ một phần partition key tổng hợp | Không định vị được partition theo truy vấn thông thường | Cung cấp đủ key hoặc thiết kế bảng mới |
| Range trên clustering thứ hai mà không giới hạn cột thứ nhất | Không có đoạn quét liên tục theo thứ tự hiện tại | Đặt equality prefix phù hợp hoặc đổi thứ tự clustering |
| Đặt mỗi `event_time` làm clustering key khi timestamp có thể trùng | Sự kiện trùng timestamp trở thành cùng một hàng logic | Thêm `event_id` để định danh duy nhất và làm tie-breaker |
| Dồn toàn bộ lịch sử vào một partition | Hot partition, đọc/compaction/tombstone lớn | Dùng time bucket hoặc sharding có mục đích |
| Giả định `ORDER BY` tạo thứ tự toàn bộ cluster | Sai khi có nhiều partition | Truy vấn từng partition và merge hoặc tạo read model |
| Giả định `LIMIT 50` luôn là 50 bản ghi mới nhất | Lấy theo thứ tự clustering hiện có | Chọn đúng clustering order và cố định ngữ nghĩa |
| Dùng `ALLOW FILTERING` để “chữa” truy vấn | Có thể quét nhiều hàng trước khi trả kết quả | Thiết kế bảng theo truy vấn, đo các giải pháp index nếu cần |
| Đưa `updated_at` biến đổi liên tục vào khóa chính | Mỗi lần đổi khóa phải chuyển hàng; tăng tombstone/dual-write | Tách identity table và read model nếu cần |
| Chỉ đo thời gian request đầu tiên | Che chi phí paging, tail latency và disk | Đo end-to-end nhiều request, nhiều partition |

## 10. Bài tập thiết kế và tự kiểm tra

### Bài 1 — Chọn clustering key

Một bảng cần phục vụ:

> “Liệt kê các đơn hàng của khách C trong tháng M, chỉ đơn có `status = 'PAID'`, sắp theo `created_at` mới nhất và có lọc từ ngày A đến B.”

Hãy chọn partition key và clustering key; mô tả chuyện gì xảy ra khi có thêm màn hình liệt kê **mọi trạng thái** theo thời gian.

**Gợi ý:** với truy vấn chỉ `PAID`, có thể phân vùng theo `(customer_id, month_bucket)` và clustering `(status, created_at, order_id)`, với `status = 'PAID'` trước range `created_at`. Nhưng để xem **mọi trạng thái** theo time, bảng này không cung cấp thứ tự toàn cục theo time trong partition; nên cân nhắc bảng thứ hai `(created_at, order_id)`.

### Bài 2 — Giải thích điều kiện thiếu prefix

Với:

~~~sql
PRIMARY KEY ((tenant_id, event_day), event_type, event_time, event_id)
~~~

Điều kiện `WHERE tenant_id = ? AND event_day = ? AND event_time >= ?` có vấn đề gì?

**Đáp án:** thiếu equality trên `event_type` đứng trước `event_time`. Trong partition, dữ liệu được nhóm theo type trước thời gian. Cần thêm điều kiện `event_type = ?` hoặc dùng bảng có time clustering đầu tiên cho yêu cầu quét mọi type.

### Bài 3 — Thứ tự đảo

Nếu `CLUSTERING ORDER BY (event_time DESC, event_id ASC)`, chiều đảo hợp lệ theo cùng chuỗi clustering là gì? Có thể nói rằng `ORDER BY event_id DESC` một mình sẽ sort toàn partition theo event_id không?

**Đáp án:** chiều đảo là `(event_time ASC, event_id DESC)`. `event_id` là clustering column thứ hai; không thể coi nó là tiêu chí sort độc lập của toàn partition trong khi `event_time` đứng trước.

### Bài 4 — Bucket và global top N

Thiết bị có 100.000 sự kiện/ngày. Màn hình cần “20 sự kiện mới nhất từ bảy ngày qua” với p99 thấp. Thiết kế bucket ngày hay tuần? Thử nghiệm nào giúp quyết định?

**Gợi ý:** tạo bảng theo bucket ngày như một ứng viên, đọc ngày mới nhất trước và lùi ngày khi chưa đủ 20 hàng. So với bucket tuần về kích thước partition, số request, fan-out, p99, write hotspot và compaction. Không có một đáp án đúng nếu chưa đo phân phối tải và tần suất sự kiện thật.

### Bài 5 — Đọc kết quả lab

Với năm hàng mẫu tại 07:45, 08:05 (hai event), 08:42 và 09:15, truy vấn range `[08:00, 09:00)` trả mấy hàng? Truy vấn `LIMIT 3` theo thứ tự mặc định lấy những thời điểm nào?

**Đáp án:** range trả **ba hàng**: 08:42 và hai hàng 08:05. `LIMIT 3` trả 09:15, 08:42 và một hàng 08:05 (theo event_id ASC).

### Checklist hoàn thành

- [ ] Phân biệt partition key tổng hợp với các clustering columns.
- [ ] Giải thích thứ tự equality-prefix rồi range và nhận biết truy vấn thiếu prefix.
- [ ] Chọn `CLUSTERING ORDER BY` và tie-breaker đúng với yêu cầu mới nhất/cũ nhất.
- [ ] Không nhầm `ORDER BY` trong partition với global sorting trên nhiều partition.
- [ ] Thiết kế bucket đủ nhỏ cho lưu lượng/partition size thật nhưng kiểm soát fan-out khi đọc dài ngày.
- [ ] Chạy CQL lab và xác minh số hàng/thứ tự, kể cả timestamp trùng nhau.
- [ ] Biết phân biệt `LIMIT`, fetch size, paging state và cursor.
- [ ] Dùng tracing, `nodetool` và latency Java để so sánh thiết kế dưới tải thực tế.

## 11. Tài liệu tham khảo

1. Apache Cassandra Documentation — [CQL Data Definition: PRIMARY KEY và CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html).
2. Apache Cassandra Documentation — [CQL Data Manipulation: SELECT, WHERE, ORDER BY và LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
3. Apache Cassandra Documentation — [Storage Engine và thứ tự trong SSTable](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html).
4. Apache Cassandra Documentation — [cqlsh: tracing và consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html).
5. Apache Cassandra Documentation — [Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).
