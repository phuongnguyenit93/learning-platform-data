# Chỉ mục, khóa duy nhất và giới hạn trên bảng phân vùng trong PostgreSQL

## 1. Bài toán: phân vùng bảng lớn nhưng vẫn phải bảo đảm tính đúng

Một hệ thống ghi nhận sự kiện có hàng trăm triệu bản ghi. Để giảm chi phí bảo trì và truy vấn theo ngày, nhóm phát triển chia bảng theo tháng:

```text
events (bảng phân vùng cha)
  |
  +-- events_2026_01  [2026-01-01, 2026-02-01)
  |
  +-- events_2026_02  [2026-02-01, 2026-03-01)
  |
  +-- events_2026_03  [2026-03-01, 2026-04-01)
  |
  +-- ...
```

Câu hỏi đầu tiên: nếu trước khi phân vùng bảng có:

```sql
PRIMARY KEY (event_id)
```

thì sau khi chuyển sang **RANGE partitioning theo ngày**, có thể giữ nguyên khóa chính `event_id` trên bảng cha không?

Với mô hình **declarative partitioning thông thường** của PostgreSQL, không thể tự tạo `PRIMARY KEY (event_id)` trên bảng cha phân vùng theo `event_date`, vì khóa duy nhất/khóa chính ở bảng cha phải chứa **tất cả các cột khóa phân vùng**. PostgreSQL quản lý các chỉ mục vật lý theo từng partition, thay vì có một B-tree duy nhất bao phủ tất cả partition.

Một thiết kế hợp lệ là:

```sql
PRIMARY KEY (event_date, event_id)
```

nhưng đây là một **quy tắc khác**:

- Nó bảo đảm mỗi cặp `(event_date, event_id)` chỉ xuất hiện một lần.
- Nó **không** bảo đảm `event_id` không bị lặp ở **hai ngày hoặc hai tháng khác nhau**.

Vì thế, phân vùng không chỉ là quyết định hiệu năng. Nó có thể ảnh hưởng đến **khóa chính, khóa ngoại, UPSERT, mô hình ID, tính duy nhất và giao thức ghi dữ liệu**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **partitioned table**, partition vật lý và chỉ mục trên bảng cha.
2. Hiểu chỉ mục khai báo trên bảng cha được triển khai qua các chỉ mục tương ứng trên partition.
3. Nêu chính xác yêu cầu của `UNIQUE` và `PRIMARY KEY` trên bảng phân vùng.
4. Nhận biết vì sao **unique theo từng partition** khác **unique toàn bộ tập dữ liệu**.
5. Thiết kế khóa `(partition_key, id)`, khóa tự nhiên nhiều cột và khóa tham chiếu phù hợp.
6. Hiểu giới hạn với partition key dạng biểu thức, phân vùng nhiều cấp và nullable columns.
7. Tạo chỉ mục chung từ bảng cha và chỉ mục cục bộ chuyên biệt cho từng partition.
8. Hiểu vì sao `CREATE INDEX CONCURRENTLY` trực tiếp trên partitioned parent bị giới hạn, và cách triển khai theo từng partition.
9. Dùng `ALTER INDEX ... ATTACH PARTITION` để kết nối chỉ mục con với chỉ mục cha.
10. Phân biệt **partition pruning** với **index scan** và nhận biết truy vấn chỉ theo ID có thể phải thăm nhiều partition.
11. Hiểu tác động tới `FOREIGN KEY`, `ON CONFLICT`, `CHECK` và `NOT NULL`.
12. Chọn phương án khi nghiệp vụ **bắt buộc ID duy nhất toàn cục**.
13. Quan sát cấu trúc partition/index bằng catalog và `EXPLAIN`.
14. Lập kế hoạch vận hành, mở rộng partition, bảo trì và kiểm tra ràng buộc an toàn.

---

## 2. Declarative partitioning trong PostgreSQL

Bảng được khai báo:

```sql
CREATE TABLE ... (
    ...
) PARTITION BY RANGE (event_date);
```

là một **partitioned table**. Nó biểu diễn một quan hệ logic với tên bảng chung, nhưng bản thân bảng cha **không chứa các hàng dữ liệu theo cách một bảng heap thông thường chứa hàng**.

Các hàng được định tuyến tới những partition cụ thể theo giá trị partition key.

Ví dụ:

```text
INSERT event_date = 2026-01-12
    -> events_2026_01

INSERT event_date = 2026-02-18
    -> events_2026_02
```

PostgreSQL hỗ trợ các chiến lược phổ biến:

| Kiểu | Ví dụ | Khi phù hợp |
|---|---|---|
| `RANGE` | Ngày/tháng, dải ID | Truy vấn và dọn dữ liệu theo khoảng |
| `LIST` | Khu vực, loại dữ liệu | Một tập giá trị phân loại rõ |
| `HASH` | Hash của tenant ID, event ID | Chia tải theo khóa có phân bố phù hợp |

### 2.1. Partition là bảng dữ liệu thật

Một partition thường là một bảng có lưu trữ vật lý riêng:

```text
events (partitioned parent: quan hệ logic)
    |
    +-- events_2026_01 (bảng vật lý + index vật lý)
    |
    +-- events_2026_02 (bảng vật lý + index vật lý)
```

Mỗi partition có thể có:

- Các trang dữ liệu heap của nó.
- Chỉ mục vật lý riêng.
- Thống kê và thông tin bảo trì liên quan.
- Tham số lưu trữ, tablespace hoặc quyết định bảo trì thích hợp.
- Một ràng buộc phạm vi partition do PostgreSQL quản lý.

Không nên hình dung có một heap lớn duy nhất với các chỉ mục nhỏ như nhãn trang. Việc phân vùng thực sự thay đổi cấu trúc quan hệ và đường truy cập.

### 2.2. Định tuyến INSERT và pruning khi SELECT

- **INSERT routing:** PostgreSQL chọn partition phù hợp cho hàng được ghi.
- **Partition pruning:** PostgreSQL có thể bỏ qua những partition không thể chứa hàng thỏa điều kiện truy vấn.
- **Index access:** sau khi đã xác định partition nào cần truy cập, PostgreSQL chọn Seq Scan, Index Scan, Bitmap Scan hoặc kế hoạch khác bên trong partition.

Ba quá trình này **không giống nhau**. Việc có index không làm partition pruning tự xuất hiện nếu truy vấn không có điều kiện phù hợp trên partition key.

## 3. Chỉ mục trên bảng cha không phải một global B-tree

Khi tạo index trên bảng cha:

```sql
CREATE INDEX idx_events_tenant_date
ON part298.events(tenant_id, event_date);
```

PostgreSQL tạo một **định nghĩa index ở cấp bảng phân vùng** và các **index tương ứng ở những partition** của nó, khi dùng hình thức thông thường và các thao tác thành công.

Sơ đồ:

```text
part298.events
  |
  +-- idx_events_tenant_date (partitioned index, logic)
          |
          +-- index vật lý của events_2026_01
          |
          +-- index vật lý của events_2026_02
          |
          +-- index vật lý của events_2026_03
```

**Không có một cây B-tree toàn cục** mà một lần tìm khóa `tenant_id` sẽ tự truy cập trực tiếp mọi tháng như tìm trong một index không phân vùng.

Khi query cần nhiều partition, planner/executor có thể cần quét những index của **nhiều partition** rồi kết hợp kết quả.

### 3.1. Chỉ mục cha có tác dụng gì?

Nó đóng vai trò định nghĩa logic và mối liên kết quản lý cho các chỉ mục partition. Nó giúp:

- Khai báo chính sách chỉ mục nhất quán cho các partition.
- Tạo/đính kèm index tương ứng ở partition.
- Liên kết cấu trúc index với khóa chính hoặc UNIQUE khi đủ điều kiện.
- Để các partition mới được thêm phù hợp với các định nghĩa index trên cha.

Điều này **không** đồng nghĩa chỉ mục cha lưu từng khóa của mọi partition dưới một cấu trúc vật lý duy nhất.

### 3.2. Chỉ mục con có thể tồn tại độc lập

Một partition cụ thể vẫn có thể có một index cục bộ riêng, không nhất thiết có định nghĩa tương ứng ở bảng cha, ví dụ index dành riêng cho một tháng hoặc một nhóm truy vấn.

Đó là **local index**, và phạm vi tác dụng của nó không được tự mở rộng thành ràng buộc toàn bảng cha.

## 4. Chuẩn bị schema thực hành

Các câu SQL dưới đây dành cho **database học tập**, không chạy trên bảng production hoặc schema chứa dữ liệu quan trọng.

### 4.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS part298;
```

### 4.2. Tạo bảng sự kiện phân vùng theo ngày

```sql
CREATE TABLE part298.events (
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    tenant_id integer NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_date, event_id)
) PARTITION BY RANGE (event_date);
```

Lưu ý ngay từ DDL:

- Partition key là `event_date`.
- Khóa chính chứa **cả event_date và event_id**.
- Khóa chính bảo đảm hai cột NOT NULL và tính duy nhất của **cặp**.
- Đây **chưa** phải bảo đảm `event_id` duy nhất toàn cục.

### 4.3. Tạo các partition tháng

```sql
CREATE TABLE part298.events_2026_01
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-01-01')
           TO   (DATE '2026-02-01');

CREATE TABLE part298.events_2026_02
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-02-01')
           TO   (DATE '2026-03-01');

CREATE TABLE part298.events_2026_03
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-03-01')
           TO   (DATE '2026-04-01');
```

Với RANGE, cận dưới **bao gồm**, cận trên **không bao gồm**.

Vì vậy:

```text
2026-01-31 thuộc events_2026_01
2026-02-01 thuộc events_2026_02
2026-03-01 thuộc events_2026_03
```

### 4.4. Chèn dữ liệu đi qua bảng cha

```sql
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type, payload
)
VALUES
    (DATE '2026-01-10', 1001, 7, 'LOGIN',   '{"ok":true}'),
    (DATE '2026-01-10', 1002, 7, 'PAYMENT', '{"amount":150}'),
    (DATE '2026-02-10', 1003, 7, 'LOGIN',   '{"ok":true}'),
    (DATE '2026-02-20', 1004, 8, 'PAYMENT', '{"amount":300}'),
    (DATE '2026-03-03', 1005, 8, 'LOGIN',   '{"ok":true}');
```

PostgreSQL định tuyến từng hàng tới partition đúng ngày.

### 4.5. Quan sát partition chứa hàng

```sql
SELECT
    tableoid::regclass AS physical_partition,
    event_date,
    event_id,
    tenant_id,
    event_type
FROM part298.events
ORDER BY event_date, event_id;
```

Cột hệ thống `tableoid` có thể cho biết partition vật lý thực sự lưu hàng. Trong lab, các hàng tháng 1 nằm ở `events_2026_01`, tháng 2 ở `events_2026_02` và tháng 3 ở `events_2026_03`.

### 4.6. Nếu INSERT ngày chưa có partition?

Ví dụ:

```sql
-- Chỉ chạy riêng để quan sát lỗi mong đợi:
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (DATE '2026-04-01', 1006, 7, 'LOGIN');
```

Trong fixture hiện tại **chưa có partition tháng 4 và chưa có DEFAULT partition**. Lệnh dự kiến thất bại vì không tìm thấy partition cho hàng.

Việc có hay không partition mặc định ảnh hưởng khả năng nhận dữ liệu mới; nó **không thay đổi** yêu cầu về khóa UNIQUE trên bảng cha.

## 5. PostgreSQL đã tạo index nào cho PRIMARY KEY?

Sau khi tạo bảng cha có `PRIMARY KEY (event_date,event_id)`, PostgreSQL cần các chỉ mục duy nhất phù hợp để thực thi ràng buộc tại từng partition.

Kiểm tra:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'part298'
  AND tablename IN (
      'events',
      'events_2026_01',
      'events_2026_02',
      'events_2026_03'
  )
ORDER BY tablename, indexname;
```

Bạn sẽ thấy các định nghĩa index liên quan tới khóa chính ở bảng cha và những partition, với tên có thể khác tùy cách PostgreSQL tự đặt và lịch sử DDL.

### 5.1. PRIMARY KEY không chỉ là một tên hiển thị

Khi khai báo khóa chính trên bảng cha phân vùng:

- PostgreSQL ghi nhận ràng buộc ở cấp cha.
- Các partition cần ràng buộc/index tương ứng.
- Khóa phân vùng làm cho **hai hàng có cùng toàn bộ khóa chính** không thể nằm ở các partition khác nhau một cách hợp lệ.
- Chỉ mục con sẽ phát hiện trùng cặp khóa trong partition thực tế.

Cơ sở để chứng minh tính duy nhất trên toàn bảng chính là **partition routing theo khóa phân vùng kết hợp index duy nhất ở từng partition**.

## 6. Quy tắc cốt lõi: UNIQUE/PRIMARY KEY phải chứa khóa phân vùng

Đối với declarative partitioning PostgreSQL, khi tạo ràng buộc `PRIMARY KEY` hoặc `UNIQUE` trên **partitioned parent**, các cột khai báo phải **bao gồm toàn bộ cột partition key**.

Nếu partition theo:

```sql
PARTITION BY RANGE (event_date)
```

thì các dạng sau về cấu trúc khóa có thể hợp lệ:

```sql
PRIMARY KEY (event_date, event_id)

UNIQUE (event_date, tenant_id, event_id)

UNIQUE (event_date, event_type, event_id)
```

với điều kiện những ràng buộc, cột và cấu trúc phân vùng khác cũng thỏa yêu cầu liên quan.

Nhưng:

```sql
UNIQUE (event_id)
```

**không thể được khai báo làm ràng buộc unique trên parent** chỉ phân vùng theo `event_date`.

### 6.1. Thử tạo unique index chỉ theo ID trên parent

Với bảng lab đã có PK composite:

```sql
-- Chỉ chạy riêng để quan sát lỗi mong đợi:
CREATE UNIQUE INDEX idx_events_global_event_id
ON part298.events(event_id);
```

PostgreSQL sẽ từ chối dạng chỉ mục duy nhất trên partitioned parent vì `event_date`, cột partition key, không nằm trong khóa duy nhất.

Thông báo có thể có ý:

```text
unique constraint on partitioned table must include
all partitioning columns
```

Câu chữ hoặc chi tiết lỗi thay đổi theo phiên bản. Đây là **giới hạn thiết kế**, không phải cú pháp `CREATE UNIQUE INDEX` bị gõ sai.

### 6.2. Thử tạo khóa chính chỉ theo ID trên một bảng cha khác

Nếu một bảng mới là:

```sql
CREATE TABLE part298.events_bad_design (
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    PRIMARY KEY (event_id)
) PARTITION BY RANGE (event_date);
```

DDL này dự kiến bị từ chối ngay ở bước khai báo PK. Phải sửa mô hình khóa hoặc khóa phân vùng, không phải thêm một option để PostgreSQL “tự kiểm tra tất cả partition”.

## 7. Vì sao UNIQUE theo từng partition chưa đủ?

Hãy nhìn hai hàng:

```text
(event_date=2026-01-10, event_id=2000)
(event_date=2026-02-10, event_id=2000)
```

Hai giá trị `event_id` giống nhau nhưng định tuyến vào **hai partition khác nhau**.

Giả sử mỗi partition có:

```sql
CREATE UNIQUE INDEX ... ON partition(event_id);
```

Index ở tháng 1 thấy ID 2000 một lần. Index ở tháng 2 cũng thấy ID 2000 một lần. Không index nào có toàn bộ tập hàng để phát hiện **trùng giữa hai tháng**.

Sơ đồ:

```text
events_2026_01
  UNIQUE(event_id)
       2000 -> hợp lệ

events_2026_02
  UNIQUE(event_id)
       2000 -> hợp lệ

Ghép logic qua parent:
       event_id=2000 xuất hiện hai lần
       nhưng không có global unique index phát hiện
```

### 7.1. Tự thử với PRIMARY KEY composite hợp lệ

Trong fixture, có thể thêm hai hàng với cùng event_id nhưng ngày khác:

```sql
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES
    (DATE '2026-01-12', 9000, 7, 'LOGIN'),
    (DATE '2026-02-12', 9000, 7, 'LOGIN');
```

**Hai hàng đều hợp lệ** theo `PRIMARY KEY (event_date,event_id)` vì cặp khóa khác nhau.

Kiểm chứng:

```sql
SELECT event_id, COUNT(*) AS occurrences
FROM part298.events
WHERE event_id = 9000
GROUP BY event_id;
```

Kết quả trong lab sau khi chèn: `occurrences = 2`.

Điều này chứng minh:

> **Khóa (event_date,event_id) duy nhất không có nghĩa event_id duy nhất.**

### 7.2. Trùng cùng cặp khóa sẽ bị từ chối

Ví dụ đã có hàng `(2026-01-12,9000)`:

```sql
-- Chạy riêng để thấy unique_violation mong đợi:
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (DATE '2026-01-12', 9000, 7, 'LOGIN');
```

Lệnh dự kiến thất bại với mã SQLSTATE `23505` do trùng **toàn bộ khóa chính**.

Nếu thử các câu SQL chủ đích gây lỗi trong một transaction được BEGIN rõ ràng, phải `ROLLBACK` hoặc xử lý savepoint thích hợp trước khi chạy các câu tiếp theo.

## 8. Phạm vi khóa duy nhất: bảng cha và bảng con

Cần phân biệt ba trường hợp:

| Cấu trúc | Giới hạn được bảo vệ | Có bảo đảm event_id duy nhất giữa các tháng? |
|---|---|---|
| Parent `PRIMARY KEY (event_date,event_id)` | Mỗi **cặp** ngày + ID duy nhất | **Không** |
| Index `UNIQUE(event_id)` chỉ trên partition tháng 1 | ID duy nhất **trong tháng 1** | **Không** |
| Bảng không phân vùng có `UNIQUE(event_id)` | ID duy nhất trong toàn bảng đó | Có |
| Bảng partition theo `HASH(event_id)` và parent `PRIMARY KEY(event_id)` | ID được định tuyến theo chính event_id | Có, trong phạm vi bảng phân vùng và ràng buộc |
| Bảng registry ID không phân vùng có `PRIMARY KEY(event_id)` | ID duy nhất trong registry | Có trong registry; phải bảo đảm đồng bộ với bảng events |

Khi thảo luận “global uniqueness”, hãy hỏi:

- **Duy nhất theo cột nào?**
- **Trong phạm vi nào?** Một tháng, một tenant hay toàn hệ thống?
- **Ai thực thi ràng buộc?** PostgreSQL constraint hay quy ước ứng dụng?
- **Khi ghi đồng thời thì sao?**
- **Khóa ngoại cần tham chiếu một cột hay nhiều cột?**

## 9. Quy tắc khóa phân vùng dạng biểu thức

Một hạn chế quan trọng: khi dùng `UNIQUE` hoặc `PRIMARY KEY` trên partitioned parent, **partition key phải dựa trên các cột**, không phải biểu thức hoặc lời gọi hàm trong khóa phân vùng, theo giới hạn PostgreSQL đối với việc kiểm chứng duy nhất bằng cấu trúc index partition.

Ví dụ thiết kế partition theo một biểu thức:

```sql
-- Ví dụ cấu trúc để thảo luận, không dùng làm schema lab:
CREATE TABLE demo_region_events (
    event_id bigint NOT NULL,
    region_code text NOT NULL
)
PARTITION BY LIST ((lower(region_code)));
```

Ngay cả khi một unique index cố gắng chứa `region_code` gốc, partition routing thực tế dùng **`lower(region_code)`**. PostgreSQL không đơn giản suy luận mọi quan hệ biểu thức để chứng minh unique toàn parent qua các index cục bộ.

### 9.1. Cách khắc phục theo mô hình

Nếu business cần unique ở parent, có thể:

- Lưu giá trị chuẩn hóa thành **cột dữ liệu thực** có quy tắc cập nhật/kiểm tra thích hợp.
- Partition theo chính cột chuẩn hóa đó, thay vì biểu thức.
- Khai báo UNIQUE/PK có đủ các cột partition key cần thiết.
- Dùng một mô hình ID/registry khác nếu điều kiện duy nhất không tương thích với partition key.

Không nên tạo một hàm “kiểm tra trùng trên toàn bộ partition” rồi giả định nó tương đương một UNIQUE constraint an toàn dưới concurrency.

## 10. Bảng phân vùng nhiều cấp: phải xét toàn bộ cây

PostgreSQL cho phép **subpartitioning**.

Ví dụ:

```text
orders_parent
    PARTITION BY LIST (tenant_id)
        |
        +-- orders_tenant_7
              PARTITION BY RANGE (ordered_on)
                  |
                  +-- orders_tenant_7_2026_01
                  +-- orders_tenant_7_2026_02
        |
        +-- orders_tenant_8
              PARTITION BY RANGE (ordered_on)
                  |
                  +-- orders_tenant_8_2026_01
```

Nếu tạo unique/PK ở cấp cha và cần ràng buộc có thể được thực thi bằng chỉ mục ở các partition lá, phải xét **cả các khóa phân vùng của những cấp liên quan**.

Một khóa chỉ chứa `tenant_id` có thể giúp phân biệt hai partition tenant nhưng không tự bảo vệ việc cùng khóa lặp ở hai tháng **trong một tenant**, khi các lá tiếp tục phân vùng theo ngày.

### 10.1. Ví dụ khóa ứng viên

Với mục đích **mỗi cặp tenant + ngày + order ID duy nhất**:

```text
UNIQUE (tenant_id, ordered_on, order_id)
```

là hướng cấu trúc có đầy đủ các cột khóa phân vùng được nêu trong cây ví dụ.

Trong thiết kế thật, PostgreSQL kiểm tra các yêu cầu ở từng cấp khi tạo/đính kèm ràng buộc và index. Không dựa vào một ví dụ DDL hai cấp chưa được kiểm chứng để khẳng định mọi cấu trúc cây đều cho phép một unique index cụ thể.

### 10.2. Tính duy nhất theo tenant khác toàn hệ thống

`UNIQUE(tenant_id,order_id)`, khi được mô hình hóa và thực thi phù hợp, cho phép:

```text
tenant=7, order_id=100
tenant=8, order_id=100
```

Điều này **đúng** nếu business định nghĩa ID duy nhất **trong một tenant**.

Nó **sai** nếu yêu cầu một `order_id` không được lặp ở bất kỳ tenant nào.

## 11. PRIMARY KEY còn kéo theo NOT NULL và khóa ngoại

Một khóa chính có hai khía cạnh:

1. Các cột khóa **NOT NULL**.
2. Tổ hợp khóa **không trùng**.

Với fixture:

```sql
PRIMARY KEY (event_date, event_id)
```

một tham chiếu đến bản ghi event bằng **event_id** đơn lẻ **không đủ** để định danh đúng một event theo ràng buộc đã khai báo.

### 11.1. Tạo bảng tham chiếu theo khóa composite

```sql
CREATE TABLE part298.event_comments (
    comment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    comment_text text NOT NULL,
    FOREIGN KEY (event_date, event_id)
        REFERENCES part298.events(event_date, event_id)
);
```

Bảng comment lưu đủ khóa để tham chiếu đúng một event theo khóa chính của parent.

Ví dụ:

```sql
INSERT INTO part298.event_comments(
    event_date, event_id, comment_text
)
VALUES (
    DATE '2026-01-10',
    1001,
    'Đã kiểm tra sự kiện'
);
```

### 11.2. Vì sao FOREIGN KEY(event_id) không thể dùng trực tiếp?

Thử thiết kế:

```sql
-- Ví dụ DDL sẽ không có khóa duy nhất tương ứng trên parent:
FOREIGN KEY (event_id)
REFERENCES part298.events(event_id)
```

Parent không có ràng buộc UNIQUE/PRIMARY KEY hợp lệ chỉ trên `event_id`, nên PostgreSQL không thể dùng `event_id` làm khóa tham chiếu duy nhất.

PostgreSQL hiện đại hỗ trợ **foreign keys tham chiếu partitioned tables** và foreign keys trên các mô hình partitioned tables thích hợp, nhưng vẫn cần **khóa được tham chiếu phải có tính duy nhất hợp lệ** và thỏa điều kiện phiên bản/cấu trúc.

Không coi partitioning là lý do tự động mất toàn bộ hỗ trợ foreign key; giới hạn trọng tâm ở đây là **định nghĩa khóa duy nhất mà FK cần tham chiếu**.

### 11.3. Hệ quả đối với API và ORM

Nếu trước đây endpoint chỉ nhận:

```text
GET /events/1001
```

nhưng sau phân vùng `event_id=1001` có thể có ở nhiều tháng, endpoint **không còn xác định một event duy nhất** chỉ bằng ID.

Các lựa chọn:

- Nhận thêm partition key: `event_date + event_id`.
- Bảo đảm ID toàn cục bằng mô hình khác.
- Thay cách partition sao cho `event_id` là một phần của khóa phân vùng.
- Dùng registry/lookup ngoài partitioned parent.

Không thay khóa chính thành composite rồi giữ nguyên giả định “event_id một mình xác định tất cả” trong application.

## 12. UNIQUE có NULL: phân biệt với PRIMARY KEY

`PRIMARY KEY` không cho phép NULL ở các cột khóa. `UNIQUE` thông thường lại có semantics NULL riêng.

Ví dụ bảng phân vùng có:

```sql
UNIQUE (event_date, external_code)
```

và `external_code` nullable. Trong cách xử lý unique mặc định của PostgreSQL, các giá trị NULL **không bị coi là bằng nhau** trong việc kiểm tra trùng theo cách thông thường.

Các phiên bản PostgreSQL hiện đại hỗ trợ `NULLS NOT DISTINCT` ở UNIQUE constraint/index để xem NULL là giá trị trùng khi cần.

Điều cần nhớ:

- Thêm NULLS NOT DISTINCT **không tạo global index**.
- Unique parent vẫn phải đáp ứng yêu cầu chứa partition key.
- Null semantics không phải cách né việc thiếu partition key.
- Nếu business không cho phép một phần khóa NULL, khai báo NOT NULL rõ.
- Cột partition key có thể có quy tắc định tuyến NULL khác theo RANGE/LIST/HASH và default partition; đừng dựa vào phép so sánh NULL như “khóa tự động duy nhất”.

## 13. CREATE INDEX trên bảng cha phân vùng

Chỉ mục **không unique** trên parent thường linh hoạt hơn unique index: nó **không bắt buộc** chứa toàn bộ partition key.

Ví dụ:

```sql
CREATE INDEX idx_part298_events_tenant
ON part298.events(tenant_id);
```

DDL này là hợp lệ về nguyên tắc dù partition key là `event_date`.

PostgreSQL tạo index partitioned parent và index tương ứng ở các partition hiện hữu, nếu tạo thành công.

### 13.1. Index này phục vụ truy vấn nào?

```sql
SELECT event_date, event_id, event_type
FROM part298.events
WHERE tenant_id = 7;
```

Các index cục bộ trên `tenant_id` có thể giúp tìm hàng tenant 7 **bên trong từng partition**, nhưng vì WHERE không giới hạn `event_date`, query vẫn có thể phải xét **nhiều hoặc tất cả partition**.

Nếu truy vấn là:

```sql
SELECT event_date, event_id, event_type
FROM part298.events
WHERE tenant_id = 7
  AND event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01';
```

PostgreSQL có thể **prune** chỉ còn tháng 2 rồi dùng index ở tháng 2 nếu chi phí phù hợp.

### 13.2. Parent index không giống một “index scan toàn cục”

Không nên mô tả:

```text
Index(tenant_id) trên parent
    -> một lần lookup
    -> trả mọi tháng
```

Mô hình đúng hơn:

```text
Xác định các partition phải đọc
    |
    +-- partition tháng 1: local index/scan
    +-- partition tháng 2: local index/scan
    +-- partition tháng 3: local index/scan
    |
Kết hợp các hàng phù hợp
```

Planner có thể dùng những node như `Append`, `Merge Append` và các scan ở từng partition. Kế hoạch cụ thể phụ thuộc phiên bản, dữ liệu và điều kiện.

## 14. Index ghép và thứ tự cột trên partition

Xét những truy vấn nóng:

```sql
SELECT event_id, event_date, event_type
FROM part298.events
WHERE tenant_id = 7
  AND event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01'
ORDER BY event_date DESC, event_id DESC
LIMIT 20;
```

Một chỉ mục có thể phù hợp:

```sql
CREATE INDEX idx_part298_events_tenant_date_id
ON part298.events(
    tenant_id,
    event_date DESC,
    event_id DESC
);
```

Tùy dữ liệu và kế hoạch:

1. `event_date` giúp **partition pruning**.
2. Index ở partition còn lại dùng `tenant_id` làm equality.
3. Các khóa `event_date DESC, event_id DESC` có thể hỗ trợ order và LIMIT.
4. Planner có thể tránh Sort hoặc giảm số hàng phải đọc.

### 14.1. Đừng chỉ thêm partition key vào mọi index

Nếu phần lớn truy vấn **luôn có đúng một partition** rồi lọc `event_id`, local index trên `event_id` có thể đủ cho đường tìm trong partition.

Ngược lại, nếu truy vấn nhiều partition và cần ORDER BY trên ngày, thứ tự cột có thể rất quan trọng.

Không có một quy tắc “mọi index trên partition đều phải bắt đầu bằng partition key”. Phân biệt:

- Yêu cầu **bắt buộc** của parent UNIQUE/PRIMARY KEY.
- Quyết định **hiệu năng** của nonunique B-tree index.

### 14.2. PRIMARY KEY cũng là một index

`PRIMARY KEY (event_date,event_id)` đã có B-tree theo thứ tự ấy. Nếu query thường xuyên tìm:

```sql
WHERE event_date = DATE '2026-02-10'
  AND event_id = 1003
```

PK index có thể phục vụ tốt.

Nhưng nếu chỉ:

```sql
WHERE event_id = 1003
```

thứ tự PK bắt đầu bằng `event_date` có thể không phù hợp để tìm trên mọi partition. Đôi khi cần thêm nonunique index `(event_id)`, song điều đó vẫn **không tự làm event_id unique toàn cục**.

## 15. Partition pruning không phải index scan

Hai quyết định có thể độc lập:

### 15.1. Pruning tốt, vẫn Seq Scan

```sql
SELECT *
FROM part298.events
WHERE event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01';
```

PostgreSQL có thể chỉ đọc `events_2026_02`. Nếu partition tháng 2 rất nhỏ hoặc query cần gần như toàn bộ hàng tháng 2, **Seq Scan ở đúng một partition** hoàn toàn có thể là plan tốt.

### 15.2. Không pruning, vẫn dùng index ở nhiều partition

```sql
SELECT *
FROM part298.events
WHERE event_id = 9000;
```

Vì không có điều kiện `event_date`, PostgreSQL không thể dựa vào date range để biết ID thuộc tháng nào. Nếu các partition có index `event_id`, có thể cần thực hiện nhiều index lookups ở nhiều partition.

### 15.3. Vì sao điều này quan trọng với API theo ID?

Một API chỉ biết event_id không thể tự tìm đúng tháng để prune, trừ khi:

- ID tự mã hóa hoặc ánh xạ tới partition key và ứng dụng dùng thông tin đó trong query.
- Có registry/lookup để tra event_date từ event_id.
- Dùng chiến lược partition dựa trên ID.
- Có yêu cầu truy vấn cho phép tìm trên mọi partition và chi phí được chấp nhận.

Partition theo thời gian thường hợp lý cho **retention/range queries**, nhưng có thể bất tiện cho **đọc theo ID không biết ngày**.

## 16. Dùng EXPLAIN để quan sát partition pruning

Sau khi có dữ liệu lab:

```sql
ANALYZE part298.events;
```

Query có điều kiện tháng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_date, event_id, tenant_id
FROM part298.events
WHERE event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01'
  AND tenant_id = 7;
```

Quan sát:

- Số partition xuất hiện trong plan.
- Có `Seq Scan`, `Index Scan` hoặc `Bitmap Heap Scan` ở partition nào.
- `actual rows` và `Buffers`.
- Điều kiện nào là `Index Cond`, điều kiện nào là `Filter`.

### 16.1. So với query không có ngày

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_date, event_id, tenant_id
FROM part298.events
WHERE tenant_id = 7;
```

Ở đây planner có thể cần xét ba partition vì tenant_id không quyết định khoảng partition theo date.

### 16.2. Planner có thể prune lúc lập kế hoạch hoặc lúc chạy

Với constant rõ ràng, pruning thường có thể diễn ra từ giai đoạn lập kế hoạch.

Trong prepared statements hoặc một số kế hoạch có tham số runtime, PostgreSQL cũng có cơ chế **execution-time partition pruning** phù hợp. Vì vậy không được kết luận “thấy nhiều partition trong khung plan ban đầu nghĩa là tất cả đều thực sự chạy đủ” khi có runtime parameters.

Dùng `EXPLAIN (ANALYZE, BUFFERS)` và các thông tin actual/subplans phù hợp của phiên bản PostgreSQL để đánh giá thực tế.

### 16.3. Cẩn thận với biểu thức trên partition key

```sql
WHERE date_trunc('month', some_timestamp) = ...
```

không tự tương đương một điều kiện range có thể prune nếu partition key, kiểu và biểu thức không khớp. Khi phân vùng theo cột ngày, ưu tiên điều kiện sargable trực tiếp theo giá trị ngày nếu đúng nghiệp vụ.

## 17. Chỉ mục riêng trên một partition

Có thể tạo index chỉ ở một partition:

```sql
CREATE INDEX idx_part298_events_2026_02_type
ON part298.events_2026_02(event_type);
```

Index này chỉ giúp truy vấn liên quan tháng 2. Nó không được tự tạo cho tháng 1, tháng 3 hoặc các tháng tương lai.

### 17.1. Khi nào index cục bộ riêng có ích?

Ví dụ:

- Partition lịch sử rất ít đọc, không cần tất cả index cho workload hiện tại.
- Partition mới nhất có nhiều truy vấn theo một cột chuyên biệt.
- Một partition có phân bố dữ liệu khác biệt.
- Một chiến dịch báo cáo chỉ truy cập một năm/tháng nhất định.

### 17.2. Rủi ro không nhất quán

Nếu cùng một query có thể đi qua nhiều partition mà mỗi partition có tập index khác nhau, plan và latency có thể khác nhiều theo tháng.

Phải theo dõi:

- Partition nào thiếu index.
- Chính sách index nào thuộc bảng cha.
- Index nào chỉ là ngoại lệ cục bộ.
- Chi phí tạo mới/duy trì từng index.
- Những partition mới có tự được áp index theo chính sách không.

Không xem một index local là một ràng buộc hoặc policy chung cho toàn parent.

## 18. Partial index trên bảng phân vùng

Một workload chỉ tìm những event loại PAYMENT:

```sql
SELECT event_date, event_id, tenant_id
FROM part298.events
WHERE event_type = 'PAYMENT'
  AND event_date >= DATE '2026-02-01'
  AND event_date <  DATE '2026-03-01';
```

Có thể cân nhắc một partial index:

```sql
CREATE INDEX idx_part298_payment_tenant_date
ON part298.events(tenant_id, event_date)
WHERE event_type = 'PAYMENT';
```

Định nghĩa trên bảng cha có thể tạo các partial indexes tương ứng ở partition.

### 18.1. Predicate phải khớp query

Planner chỉ dùng partial index khi có thể chứng minh query không cần những hàng ngoài predicate của index.

Một query:

```sql
WHERE event_type = 'PAYMENT'
```

có khả năng khớp predicate.

Nhưng một prepared generic plan với:

```sql
WHERE event_type = $1
```

không nhất thiết chứng minh `$1` luôn là PAYMENT, nên không bảo đảm planner chọn partial index.

### 18.2. Partial UNIQUE không phải một global unique index

Không nên nghĩ:

```sql
CREATE UNIQUE INDEX ... ON parent(event_id)
WHERE event_type='PAYMENT';
```

sẽ né được yêu cầu về partition key chỉ vì predicate thu hẹp dữ liệu. Tính duy nhất vẫn được thực thi qua các index cục bộ và phải tương thích với quy tắc partition key của PostgreSQL.

### 18.3. Phân biệt constraint và partial unique index

Một **partial unique index** có thể thực thi một quy tắc “tối đa một hàng thỏa predicate” trong phạm vi các khóa/partition có thể chứng minh hợp lệ. Nó không hoàn toàn tương đương một `UNIQUE CONSTRAINT` thông thường cho mọi mục đích, ví dụ các yêu cầu làm target khóa ngoại hoặc một số dạng inference.

Trước khi dùng, xác minh rằng ràng buộc được chọn đáp ứng đúng nhu cầu tham chiếu và nghiệp vụ.

## 19. INCLUDE và covering index trên partition

Chỉ mục B-tree có thể chứa cột payload:

```sql
CREATE INDEX idx_part298_events_tenant_date_cover
ON part298.events(tenant_id, event_date DESC, event_id DESC)
INCLUDE (event_type);
```

Ở mỗi partition tương ứng, index lưu:

- **Key columns:** tenant_id, event_date, event_id.
- **Included column:** event_type.

Truy vấn:

```sql
SELECT event_date, event_id, event_type
FROM part298.events
WHERE tenant_id = 7
  AND event_date >= DATE '2026-01-01'
  AND event_date <  DATE '2026-02-01'
ORDER BY event_date DESC, event_id DESC
LIMIT 20;
```

có thể dùng index để lọc, giữ thứ tự và có đủ các cột trả về.

### 19.1. INCLUDE không thay khóa tìm kiếm

Nếu `event_type` chỉ nằm trong INCLUDE, nó **không** trở thành cột khóa B-tree giúp giới hạn scan giống `event_type` trong danh sách key columns.

### 19.2. Index Only Scan vẫn có thể đọc heap

PostgreSQL dùng visibility map/MVCC để xác định có thể trả dữ liệu mà không kiểm tra heap hay không. Nếu các trang heap chưa all-visible, node `Index Only Scan` vẫn có thể ghi nhận `Heap Fetches`.

Vì mỗi partition có trạng thái VACUUM/visibility riêng, cùng một truy vấn theo tháng có thể có tỷ lệ heap fetch khác nhau.

### 19.3. Không INCLUDE toàn bộ payload lớn

Cột JSONB lớn không nên được thêm vào mọi B-tree INCLUDE để “đỡ đọc bảng” mà không đánh giá kích thước index, giới hạn kích thước entry, chi phí ghi và cấu trúc truy vấn.

## 20. Không thể CREATE INDEX CONCURRENTLY trực tiếp trên partitioned parent theo cách thông thường

Trên một bảng heap không phân vùng, cú pháp:

```sql
CREATE INDEX CONCURRENTLY idx_name
ON schema.table_name(column_name);
```

giúp giảm mức cản trở ghi dữ liệu so với tạo index thông thường, với các điều kiện/hạn chế riêng.

Nhưng trên **partitioned parent**, PostgreSQL hiện có hạn chế quan trọng: **`CREATE INDEX CONCURRENTLY` không được hỗ trợ trực tiếp theo cách tạo toàn bộ cây index trên parent**.

Điều này đặc biệt quan trọng khi bảng đã có hàng trăm partition lớn và ứng dụng ghi liên tục.

### 20.1. Vì sao không nên chỉ chạy CREATE INDEX thường trong giờ cao điểm?

Một lệnh trên parent có thể cần tạo index trên tất cả partition hiện hữu, với khóa và thời gian hoàn thành phụ thuộc dữ liệu và thao tác liên quan. Việc này có thể gây tác động DML đáng kể.

Với hệ thống hoạt động liên tục, cần kế hoạch:

- Tạo index **CONCURRENTLY** ở từng partition vật lý khi được hỗ trợ.
- Khai báo index cha ở trạng thái chưa valid bằng `ON ONLY`.
- Đính kèm index con vào index cha.
- Kiểm tra khi đã đính kèm đủ tất cả partition.

Đó là quy trình PostgreSQL thường được dùng để xây dựng partitioned index mà không buộc xây toàn bộ cây bằng một CREATE INDEX thường trên parent.

## 21. Quy trình tạo index parent bằng ON ONLY + ATTACH PARTITION

Phần này dùng một bảng lab riêng để tránh đụng những index đã tạo ở bảng events.

### 21.1. Tạo bảng measurements

```sql
CREATE TABLE part298.measurements (
    measured_on date NOT NULL,
    device_id integer NOT NULL,
    measured_value double precision NOT NULL
) PARTITION BY RANGE (measured_on);

CREATE TABLE part298.measurements_2026_01
PARTITION OF part298.measurements
FOR VALUES FROM (DATE '2026-01-01')
           TO   (DATE '2026-02-01');

CREATE TABLE part298.measurements_2026_02
PARTITION OF part298.measurements
FOR VALUES FROM (DATE '2026-02-01')
           TO   (DATE '2026-03-01');
```

### 21.2. Tạo định nghĩa index trên ONLY parent

```sql
CREATE INDEX idx_part298_measurements_device_time
ON ONLY part298.measurements(device_id, measured_on);
```

Ý nghĩa:

- Tạo **partitioned index definition** ở bảng cha.
- **Không** tự xây index trên các partition hiện tại.
- Index cha ở trạng thái **chưa valid** cho đến khi mọi partition cần thiết có index tương ứng được đính kèm.

Một index cha chưa valid không có nghĩa index ở từng partition không thể được dùng; các index con được xây hợp lệ vẫn có thể dùng cục bộ. Nó có nghĩa toàn bộ cấu trúc khai báo của parent **chưa hoàn thiện**.

### 21.3. Tạo index CONCURRENTLY ở từng partition

Chạy các lệnh sau riêng, không đặt trong explicit transaction block:

```sql
CREATE INDEX CONCURRENTLY idx_part298_measurements_2026_01_device_time
ON part298.measurements_2026_01(device_id, measured_on);

CREATE INDEX CONCURRENTLY idx_part298_measurements_2026_02_device_time
ON part298.measurements_2026_02(device_id, measured_on);
```

**Chú ý:**

- `CREATE INDEX CONCURRENTLY` không chạy trong transaction block thông thường.
- Mỗi partition là một bảng vật lý thích hợp cho thao tác riêng.
- Trên dữ liệu lớn, cần theo dõi từng index build và xử lý thất bại.
- Nếu concurrent index build thất bại, có thể còn một index invalid cục bộ; không ATTACH cho tới khi đã xử lý và xác minh hợp lệ.

### 21.4. ATTACH các chỉ mục con

```sql
ALTER INDEX part298.idx_part298_measurements_device_time
ATTACH PARTITION
    part298.idx_part298_measurements_2026_01_device_time;

ALTER INDEX part298.idx_part298_measurements_device_time
ATTACH PARTITION
    part298.idx_part298_measurements_2026_02_device_time;
```

PostgreSQL xác minh tính tương thích của các index và ghi nhận quan hệ partitioned index.

Khi **đã có đầy đủ các partition index cần thiết** được ATTACH, parent partitioned index được đánh dấu valid.

### 21.5. Kiểm tra indisvalid

```sql
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c
    ON c.oid = i.indexrelid
WHERE i.indexrelid =
    'part298.idx_part298_measurements_device_time'::regclass;
```

Sau khi index cha được hoàn thiện đúng cấu trúc, `indisvalid` được kỳ vọng là TRUE.

### 21.6. Với rất nhiều partition

Quy trình cần theo dõi danh sách partition hiện hữu và index tương ứng; nếu mới hoàn thành một phần, **không báo đã tạo xong toàn bộ index parent**.

Khi tạo partition mới sau này, phải bảo đảm index policy của cha tiếp tục được áp dụng. Nếu một partition chưa có index khớp hoặc một thao tác ATTACH thất bại, trạng thái cấu trúc phải được kiểm tra lại theo quy trình vận hành.

## 22. Giới hạn của CREATE INDEX CONCURRENTLY

Ngay cả khi thực thi trên partition vật lý, CONCURRENTLY có những đặc điểm đáng lưu ý:

- Không chạy bên trong explicit transaction block.
- Có thêm các giai đoạn quét/chờ cần thiết, có thể mất nhiều thời gian hơn CREATE INDEX thường.
- Có thể thất bại và để lại index invalid.
- Phải tránh chạy các lần tạo index đồng thời xung đột trên cùng bảng theo cách không được hỗ trợ.
- Một số thao tác duy trì uniqueness trong lúc tạo unique index concurrently có chi tiết xử lý phức tạp; lỗi duplicate phải được quản lý.
- Trên bảng lớn, I/O, WAL và dung lượng lưu trữ vẫn đáng kể dù DML ít bị chặn hơn.

**Không có nghĩa “CONCURRENTLY = hoàn toàn không khóa và không ảnh hưởng production”.** Nó giảm một số loại chặn, không loại mọi chi phí.

### 22.1. Có thể dùng quy trình ATTACH cho UNIQUE không?

Có thể xây dựng **partitioned unique index** theo quy trình thích hợp khi cấu trúc UNIQUE đáp ứng yêu cầu có partition key và những giới hạn của PostgreSQL. Nhưng không vì tạo unique index trên từng partition thành công mà suy ra một UNIQUE thiếu partition key có thể ATTACH thành index cha hợp lệ.

Tính đúng phải được chứng minh bởi **khóa duy nhất tương thích partition routing**, không phải bằng thủ thuật ATTACH.

### 22.2. Ràng buộc PRIMARY KEY/UNIQUE và CREATE INDEX USING INDEX

Không tự suy luận rằng cú pháp thêm constraint bằng `USING INDEX` của bảng thường áp dụng y nguyên cho partitioned parent trên mọi phiên bản. Partitioned indexes và constraints có quy tắc DDL riêng; kiểm tra tài liệu `ALTER TABLE` của phiên bản PostgreSQL đang chạy.

Với yêu cầu migration PK/UNIQUE trên dữ liệu lớn, nên lập kế hoạch và kiểm thử riêng, thay vì copy mù một quy trình nonunique index.

## 23. Thêm partition và chỉ mục về sau

Giả sử đến tháng 4, hệ thống cần partition mới:

```sql
CREATE TABLE part298.events_2026_04
PARTITION OF part298.events
FOR VALUES FROM (DATE '2026-04-01')
           TO   (DATE '2026-05-01');
```

Với mô hình declarative partitioning, những ràng buộc/index được định nghĩa ở bảng cha theo cách hợp lệ sẽ cần được phản ánh ở partition mới.

### 23.1. Không giả định index local riêng cũng được sao chép

Index tạo riêng trên `events_2026_02` **không tự động** trở thành policy cho `events_2026_04`.

Nếu có các index local chuyên biệt, quy trình provisioning partition cần biết tháng nào cần tạo.

### 23.2. ATTACH một bảng đã có dữ liệu

Khi dùng `ALTER TABLE ... ATTACH PARTITION` cho một bảng hiện hữu, PostgreSQL có thể cần xác minh các hàng nằm đúng bounds, xử lý constraint, index và lock theo quy tắc.

Quá trình validation có thể quét bảng lớn. Có thể chuẩn bị CHECK constraint tương thích để giảm một số bước scan trong các tình huống được hỗ trợ, nhưng không nên tự giả định ATTACH luôn tức thời.

### 23.3. DEFAULT partition

DEFAULT partition nhận những hàng không khớp các partition tường minh.

Nhưng khi về sau tạo một partition mới chồng vào phạm vi dữ liệu đang nằm trong DEFAULT, bạn có thể phải di chuyển/loại các hàng ấy và xử lý constraint trước khi tạo/attach partition mới.

DEFAULT partition giúp tránh thiếu partition khi INSERT, nhưng **không thay thế quản lý lịch partition** hoặc giải quyết global uniqueness.

## 24. UNIQUE, PRIMARY KEY và ON CONFLICT

PostgreSQL cho phép dùng `INSERT ... ON CONFLICT` với ràng buộc hoặc unique index phù hợp.

Fixture có khóa:

```sql
PRIMARY KEY (event_date, event_id)
```

Nên có thể viết:

```sql
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type, payload
)
VALUES (
    DATE '2026-02-10', 1003, 7, 'LOGIN',
    '{"ok":false}'::jsonb
)
ON CONFLICT (event_date, event_id)
DO UPDATE SET
    payload = EXCLUDED.payload;
```

Đây là UPSERT theo **cặp ngày + ID**, không phải theo event_id đơn lẻ.

### 24.1. ON CONFLICT(event_id) không tự hoạt động

Với schema hiện tại:

```sql
-- Không có unique constraint/index thích hợp trên parent(event_id):
INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (DATE '2026-02-11', 1003, 7, 'LOGIN')
ON CONFLICT (event_id)
DO NOTHING;
```

Vì không có unique arbiter phù hợp chỉ trên `event_id` ở parent, dạng chỉ định conflict target này không được hỗ trợ theo giả định schema.

### 24.2. DO NOTHING không làm ID duy nhất toàn cục

Ngay cả khi dùng `ON CONFLICT DO NOTHING` không nêu conflict target, PostgreSQL chỉ xử lý những conflict được xác định bởi ràng buộc/index đang có. Nó **không** tạo ra quy tắc unique(event_id) mà schema chưa hề bảo vệ.

Nếu hai hàng có cùng event_id nhưng event_date khác, chúng không xung đột với khóa chính composite.

### 24.3. UPDATE làm thay đổi partition key

PostgreSQL có khả năng chuyển hàng giữa partition trong những tình huống UPDATE partition key được hỗ trợ, nhưng thao tác `ON CONFLICT DO UPDATE` có **giới hạn** đối với việc cập nhật partition key của hàng xung đột sao cho hàng phải chuyển sang partition khác.

Khi thiết kế UPSERT với time partitioning:

- Đừng mặc định có thể “dời sự kiện sang ngày khác” trong cùng một ON CONFLICT DO UPDATE.
- Đọc tài liệu phiên bản và kiểm thử riêng.
- Nếu event_date là thành phần định danh, đổi ngày có thể làm thay đổi chính khóa composite và quan hệ tham chiếu.

## 25. CHECK và NOT NULL trên partitioned table

Các ràng buộc như `CHECK` và `NOT NULL` có thể được khai báo trên bảng cha để bảo vệ các hàng trong hệ phân vùng theo quy tắc inheritance/declarative partitioning.

Ví dụ:

```sql
ALTER TABLE part298.events
ADD CONSTRAINT event_type_not_blank
CHECK (length(btrim(event_type)) > 0);
```

Mục tiêu là mọi hàng sự kiện phải có `event_type` không rỗng sau khi trim.

### 25.1. CHECK kiểm tra từng hàng, không bảo đảm tính duy nhất xuyên partition

Ví dụ:

```sql
CHECK (tenant_id > 0)
```

là một quy tắc trên hàng.

Nhưng:

```text
Mỗi event_id chỉ xuất hiện tối đa một lần trên toàn hệ thống.
```

là quy tắc **giữa nhiều hàng**. Không thể biến nó thành một CHECK đơn giản có subquery tra toàn bộ partition rồi coi là an toàn dưới concurrency.

### 25.2. CHECK của child và parent

Khi dùng declarative partitioning, những ràng buộc parent cần được tuân thủ ở các partition tương ứng. Những kiểm tra thêm riêng cho child có thể giới hạn dữ liệu hơn nữa khi được phép.

Không được tự ý bỏ constraint của parent khỏi child để “tăng tốc import” nếu làm vậy phá ngữ nghĩa bảng chung.

### 25.3. Constraint validation khi attach

Khi gắn partition chứa sẵn dữ liệu, PostgreSQL có thể cần xác nhận dữ liệu đáp ứng bounds/constraints. Đây là lý do một migration partition không chỉ là đổi metadata tên bảng.

## 26. EXCLUDE constraint và các giới hạn tương tự

`EXCLUDE` là cơ chế constraint hữu ích cho một số bài toán như **không cho hai khoảng thời gian chồng lấn** khi toán tử/index method phù hợp.

Ví dụ trong bảng không phân vùng, có thể dùng GiST + range operators để biểu đạt một số quy tắc không overlap. Nhưng ở partitioned parent, bạn vẫn phải xét:

- Cách chia partition có đảm bảo các hàng có thể xung đột sẽ được đưa vào cùng partition phù hợp hay không?
- Những cột partition key có tham gia constraint với phép so sánh được yêu cầu không?
- Phiên bản PostgreSQL đang dùng có hỗ trợ EXCLUDE trên partitioned parent theo đúng cấu trúc này không?
- Có cần extension như `btree_gist` cho equality trên kiểu scalar không?

Ở những phiên bản hỗ trợ EXCLUDE trên partitioned table, các cột partition key cần tham gia constraint theo cách giúp đảm bảo **các hàng thuộc partition khác nhau không thể xung đột**, thường là **so sánh bằng** trên khóa phân vùng.

**Không nên coi EXCLUDE là một global uniqueness/overlap index tùy ý** có thể kiểm tra mọi cặp hàng giữa các partition mà không xét partition key.

### 26.1. Ví dụ giới hạn ngữ nghĩa

Giả sử chia lịch phòng họp theo **tháng bắt đầu**, nhưng một cuộc họp có thể kéo dài qua ranh giới tháng. Hai cuộc họp cùng phòng có khoảng thời gian chồng lấn nhưng ngày bắt đầu nằm ở **hai partition khác nhau**.

Một constraint chỉ kiểm tra overlap bên trong từng partition có thể bỏ sót xung đột xuyên tháng. Cần thiết kế partition key/constraint hoặc cơ chế điều phối khác để bảo vệ invariant thật.

## 27. Khi business yêu cầu event_id duy nhất toàn cục

Đây là quyết định kiến trúc quan trọng nhất của bài.

Yêu cầu:

```text
Mỗi event_id chỉ xuất hiện tối đa một lần trong toàn bộ events,
bất kể ngày, tháng, tenant hay partition.
```

Phân vùng theo event_date và dùng PK(event_date,event_id) **không đáp ứng** yêu cầu đó.

Có một số hướng thiết kế.

### 27.1. Hướng A — Đổi chiến lược partition theo event_id

Nếu partition theo **HASH(event_id)**:

```sql
CREATE TABLE part298.events_by_hash (
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    event_type text NOT NULL,
    PRIMARY KEY (event_id)
) PARTITION BY HASH (event_id);
```

Tạo bốn partition:

```sql
CREATE TABLE part298.events_by_hash_p0
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE part298.events_by_hash_p1
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE part298.events_by_hash_p2
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE part298.events_by_hash_p3
PARTITION OF part298.events_by_hash
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

Ở đây partition key là `event_id`, nên `PRIMARY KEY(event_id)` phù hợp.

**Vì sao unique toàn cục đúng?**

Hai hàng có cùng event_id sẽ được hàm partitioning định tuyến tới **cùng một partition**, rồi unique index cục bộ ở partition đó phát hiện trùng. Không cần một index global vật lý.

Trade-off:

- Tìm theo event_id thuận lợi vì có thể prune theo hash key.
- Dọn dữ liệu theo tháng bằng DETACH/DROP partition không còn đơn giản như RANGE(date).
- Truy vấn chỉ theo ngày có thể cần xét nhiều hash partitions.

### 27.2. Hướng B — Chấp nhận khóa composite

Giữ RANGE(date) và định nghĩa định danh nghiệp vụ là:

```text
(event_date, event_id)
```

Tất cả API, FK, lookup, cache key và external references phải hiểu hai thành phần.

Ưu điểm:

- Partition theo ngày phục vụ retention và truy vấn thời gian.
- Ràng buộc thực thi trực tiếp bằng parent PK.

Nhược điểm:

- ID một mình không xác định được hàng.
- Khóa ngoại trở thành composite.
- ORM, URL, upsert và các consumer cần mang thêm ngày.

**Chỉ chọn nếu nghiệp vụ thực sự chấp nhận composite identity.**

### 27.3. Hướng C — Registry ID không phân vùng

Tạo một bảng có UNIQUE/PK thực sự trên ID:

```sql
CREATE TABLE part298.event_id_registry (
    event_id bigint PRIMARY KEY,
    event_date date NOT NULL
);
```

Quy trình ghi:

```sql
BEGIN;

INSERT INTO part298.event_id_registry(event_id, event_date)
VALUES (50001, DATE '2026-02-15');

INSERT INTO part298.events(
    event_date, event_id, tenant_id, event_type
)
VALUES (
    DATE '2026-02-15', 50001, 7, 'LOGIN'
);

COMMIT;
```

Nếu hai transaction cùng cố đăng ký event_id=50001, PK của registry khiến một transaction không thể commit một hàng registry thứ hai có cùng ID.

Điều kiện bắt buộc:

- **Mọi đường tạo event phải đăng ký ID trong cùng transaction**.
- Nếu INSERT event thất bại, registry insert phải rollback theo.
- Cần quy trình quản lý việc xóa/sửa date, retention và tái sử dụng ID.
- Registry có thể trở thành điểm nóng hoặc làm tăng chi phí ghi.
- Cần thiết kế tham chiếu và cleanup nhất quán.

### 27.4. Registry không tự tạo FK event_id → events

Nếu các bảng khác tham chiếu `event_id_registry(event_id)`, FK chứng minh **ID tồn tại trong registry**, không tự chứng minh hàng chi tiết còn tồn tại trong `events` nếu workflow cho phép chỉ còn registry.

Ứng dụng phải định nghĩa registry là sổ định danh lâu dài hay bản ánh xạ đúng một event hiện hữu, rồi bảo vệ quan hệ đó trong các thao tác tạo/xóa/migrate.

### 27.5. Hướng D — ID sinh từ sequence/UUID

Một sequence chung:

```sql
CREATE SEQUENCE part298.event_id_seq;
```

hoặc ID từ UUID giúp **giảm nguy cơ trùng** hoặc cung cấp cơ chế cấp ID nhất quán, nhưng cần phân biệt:

- Một sequence cấp giá trị mới khi gọi `nextval` theo semantics của sequence.
- Application/admin vẫn có thể ghi tay một ID trùng nếu schema cho phép.
- Sequence có thể bị thay đổi/reset và không tự ràng buộc mọi INSERT ở tất cả partition.
- UUID ngẫu nhiên có xác suất va chạm rất thấp nhưng không phải lời chứng minh ràng buộc UNIQUE của PostgreSQL trên parent.

**Sinh ID khác nhau và cưỡng chế UNIQUE là hai đảm bảo khác nhau.** Nếu yêu cầu dữ liệu tuyệt đối không được trùng, thiết kế cần cơ chế constraint/giao thức tương ứng.

## 28. Chọn partition key theo điều kiện truy vấn và tính duy nhất

Một lựa chọn partition key ảnh hưởng đồng thời:

| Mục tiêu | RANGE(event_date) | HASH(event_id) |
|---|---|---|
| Truy vấn theo tháng | Pruning tốt khi có điều kiện date | Thường quét nhiều hash partitions |
| Giữ/xóa dữ liệu theo tháng | Dễ DETACH/DROP partition tháng | Không thuận tiện |
| Tìm một event_id | Nếu không biết date có thể quét nhiều tháng | Pruning theo event_id |
| Parent PK(event_id) | Không hợp lệ nếu thiếu date | Hợp lệ theo hash key |
| Parent PK(event_date,event_id) | Hợp lệ | Có thể hợp lệ vì chứa event_id |
| Local index theo tenant | Có thể tạo ở mỗi tháng | Có thể tạo ở mỗi hash partition |
| Tăng số partition | Theo lịch thời gian | Theo chiến lược hash modulus |
| Chi phí thiết kế khóa ngoại | Có thể cần composite date+id | Có thể dùng event_id nếu PK(id) |

Không nên chọn phân vùng **chỉ** vì “bảng có nhiều hàng”. Trước tiên xác định:

1. Các truy vấn chính lọc cột nào?
2. Dữ liệu thường được xóa/di chuyển theo thời gian hay theo tenant?
3. ID nào cần duy nhất toàn cục?
4. FK từ những bảng nào phải tham chiếu?
5. Có thường đọc event bằng ID mà không biết date không?
6. Có thể thay đổi composite identity trong toàn bộ application không?
7. Số lượng partition và index có vận hành nổi không?

## 29. Multi-tenant: duy nhất trong tenant hay toàn hệ thống?

Ví dụ bảng đơn nhiều tenant partition theo tenant:

```sql
CREATE TABLE part298.tenant_orders (
    tenant_id integer NOT NULL,
    order_id bigint NOT NULL,
    ordered_on date NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
    PRIMARY KEY (tenant_id, order_id)
) PARTITION BY HASH (tenant_id);
```

Cách này hợp lệ về hướng thiết kế vì parent PK chứa partition key `tenant_id`.

Tính duy nhất là:

```text
UNIQUE (tenant_id, order_id)
```

Vì vậy:

```text
tenant=7, order_id=42 -> hợp lệ
tenant=8, order_id=42 -> cũng hợp lệ
```

### 29.1. Không lấy order_id đơn lẻ để định danh toàn hệ thống

Nếu ứng dụng truy vấn:

```sql
SELECT *
FROM part298.tenant_orders
WHERE order_id = 42;
```

có thể trả nhiều tenant và quét nhiều partition. Đây không chỉ là vấn đề hiệu năng mà còn là **rủi ro phạm vi dữ liệu** nếu thiếu điều kiện tenant.

Truy vấn đúng với tenant được xác thực:

```sql
SELECT *
FROM part298.tenant_orders
WHERE tenant_id = 7
  AND order_id = 42;
```

Trong hệ thống thật, tenant_id phải đến từ ngữ cảnh xác thực/ủy quyền đáng tin cậy, không chỉ tin tham số do client tự khai.

### 29.2. RLS không thay UNIQUE theo tenant

Row Level Security có thể hạn chế quyền nhìn/ghi các hàng, nhưng nó không tự thay đổi cấu trúc uniqueness do partition key quyết định. Constraint, partition routing và RLS giải quyết các vấn đề khác nhau.

## 30. Kiểm tra catalog: bảng nào là partition, index nào là partitioned index?

### 30.1. Liệt kê cây partition

PostgreSQL có hàm hỗ trợ xem cây phân vùng:

```sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_relation,
    isleaf,
    level
FROM pg_partition_tree('part298.events'::regclass)
ORDER BY level, relation_name;
```

Kết quả có bảng cha và các partition lá, với thông tin cấp độ.

### 30.2. Dùng pg_inherits

```sql
SELECT
    parent.oid::regclass AS parent_table,
    child.oid::regclass AS child_table
FROM pg_inherits AS inh
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
WHERE parent.oid = 'part298.events'::regclass
ORDER BY child.relname;
```

Catalog `pg_inherits` còn chứa quan hệ inheritance/attachment ở các ngữ cảnh khác; lọc đúng parent khi điều tra.

### 30.3. Phân biệt index cha và index con

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS index_name,
    c.relkind,
    t.relname AS indexed_table,
    i.indisunique,
    i.indisprimary,
    i.indisvalid
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_index AS i
    ON i.indexrelid = c.oid
JOIN pg_class AS t
    ON t.oid = i.indrelid
WHERE n.nspname = 'part298'
ORDER BY t.relname, c.relname;
```

Các giá trị `pg_class.relkind` liên quan:

- `I`: partitioned index.
- `i`: index thông thường có lưu trữ vật lý.

Đọc kết quả theo cả relkind, bảng được index và trạng thái constraint; không chỉ nhìn tên index.

### 30.4. Xem quan hệ index partition

```sql
SELECT
    pi.inhparent::regclass AS parent_index,
    pi.inhrelid::regclass AS child_index
FROM pg_inherits AS pi
WHERE pi.inhparent =
    'part298.idx_part298_measurements_device_time'::regclass
ORDER BY child_index;
```

Sau bài lab `ATTACH PARTITION` ở phần 21, query cho thấy các index con đã được đính kèm với index cha.

## 31. Theo dõi hiệu quả index tại từng partition

Xem thống kê:

```sql
SELECT
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'part298'
ORDER BY relname, indexrelname;
```

Vì scan dữ liệu diễn ra ở các partition vật lý, cần quan sát **chỉ mục của những partition thực sự được scan**. Không chỉ nhìn một chỉ số thống kê của partitioned parent rồi kết luận index không bao giờ được sử dụng.

### 31.1. Tên index không đủ chứng minh performance

Một index có thể tồn tại hợp lệ nhưng query không chọn nó vì:

- Partition quá nhỏ.
- Điều kiện lọc trả phần lớn hàng.
- Index không khớp toán tử/cột.
- Không có điều kiện pruning.
- Cần đọc quá nhiều heap pages.
- Có kế hoạch Sort/Seq Scan rẻ hơn.
- Thống kê sai lệch hoặc chưa được cập nhật.

Dùng `EXPLAIN (ANALYZE, BUFFERS)` với dữ liệu đại diện trước khi đánh giá.

### 31.2. Kích thước từng partition và index

```sql
SELECT
    c.oid::regclass AS relation_name,
    pg_size_pretty(pg_relation_size(c.oid)) AS relation_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'part298'
  AND c.relkind IN ('r', 'i', 'I', 'p')
ORDER BY c.relname;
```

Partitioned parent/index logic có thể không có dung lượng lưu trữ heap/index như partition con. Khi cần tổng dung lượng thực tế, tính các partition/index vật lý phù hợp, tránh nhìn kích thước parent và kết luận toàn bộ dữ liệu không tốn chỗ.

## 32. Các chi phí vận hành của nhiều partition/index

Partitioning có lợi nhưng không miễn phí:

- Mỗi partition là một relation với metadata riêng.
- Mỗi partition có thể cần nhiều index riêng.
- Lập kế hoạch query trên quá nhiều partition có thể tăng chi phí.
- DDL trên parent có thể kéo theo thao tác ở nhiều partition.
- ANALYZE/VACUUM/autovacuum và thống kê cần được xem ở cấp phù hợp.
- BACKUP, restore, schema migration và retention có nhiều đối tượng hơn.
- Partition bị thiếu/misconfigured có thể khiến INSERT thất bại.
- Local index policy không nhất quán làm hiệu năng giữa tháng khác nhau.

### 32.1. Quá nhiều index trên mỗi partition

Nếu có 120 partition và mỗi partition có 8 index, toàn hệ thống có thể có khoảng **960 index vật lý**, chưa tính index ở cấp cha và cấu trúc khác.

Đây chỉ là ví dụ số học, không phải ngưỡng kỹ thuật PostgreSQL.

Thêm một index cha có thể tương ứng với tạo thêm rất nhiều index con. Hãy dự trù:

- Thời gian build.
- Dung lượng lưu trữ.
- WAL và I/O.
- Tác động INSERT/UPDATE/DELETE.
- Chi phí maintenance.
- Thời gian triển khai partition mới.

### 32.2. Retention nhanh nhưng có điều kiện

Một ưu điểm của RANGE(date) là có thể DETACH/DROP các partition lịch sử theo chính sách. Nhưng:

- Cần xem FK/constraint và các liên kết dữ liệu.
- Cần đảm bảo đúng retention/legal hold.
- Các thao tác DDL có yêu cầu lock/quyền.
- Không tự ý loại partition có dữ liệu được bảng khác tham chiếu.
- Quy trình backup/restore và registry ID phải nhất quán với việc xóa lịch sử.

“DROP partition nhanh” không phải giấy phép bỏ qua ràng buộc tham chiếu.

## 33. Vận hành UNIQUE/PK khi thêm hoặc attach partition

Với parent có PRIMARY KEY hoặc UNIQUE hợp lệ:

1. Xác minh partition mới có đúng cấu trúc cột/kiểu/NOT NULL.
2. Xác minh bounds không chồng lấn.
3. Xem những hàng hiện hữu có vi phạm ràng buộc không.
4. Đảm bảo index tương thích đã có hoặc sẽ được tạo/đính kèm đúng.
5. Theo dõi lock và thời gian validation khi ATTACH.
6. Kiểm tra lại trạng thái index parent/child sau thao tác.
7. Chạy truy vấn đại diện với `EXPLAIN` khi cần.
8. Không báo migration thành công chỉ vì partition có tên trong catalog.

### 33.1. Với bảng mới tạo bằng PARTITION OF

PostgreSQL xử lý việc bảo đảm các index/constraints tương ứng với định nghĩa parent theo đường DDL declarative partitioning.

### 33.2. Với bảng có sẵn đưa vào bằng ATTACH PARTITION

Việc tương thích constraint/index có thể cần kiểm tra và xây dựng cấu trúc bổ sung. Đừng mặc định việc attach một bảng trống và attach một bảng 100 triệu hàng có cùng tác động vận hành.

### 33.3. Khóa duy nhất cục bộ không tự nâng thành UNIQUE parent

Nếu partition tháng 1, 2, 3 đều có UNIQUE(event_id), vẫn chưa đủ chứng minh `event_id` không lặp giữa các tháng. Không dùng việc “mỗi partition đều có unique index” làm bằng chứng global uniqueness nếu không có partition-routing theo chính khóa đó.

## 34. Phân biệt idempotency, uniqueness và ordering

Ba yêu cầu dễ bị trộn lẫn:

**Uniqueness:**

```text
Không tồn tại hai hàng cùng khóa theo định nghĩa constraint.
```

**Idempotency:**

```text
Gửi lại cùng một request không gây tác động nghiệp vụ lặp.
```

**Ordering:**

```text
Có thể sắp kết quả theo thời gian/ID và chọn đúng top-N.
```

Một UNIQUE constraint có thể là thành phần để xây dựng idempotency, nhưng:

- Unique(event_date,event_id) vẫn cho phép cùng event_id ở hai ngày.
- Nếu client retry cùng event_id nhưng tự gán event_date mới, nó có thể tạo sự kiện thứ hai.
- Nếu dùng registry unique(event_id), cần gắn request key và payload phù hợp để phân biệt retry hợp lệ với xung đột thực.
- Một chỉ mục theo event_date có thể giúp ORDER BY nhưng không bảo đảm event_id duy nhất.

Không dùng cùng một index như câu trả lời cho mọi loại yêu cầu.

## 35. Thiết kế test cho ràng buộc và partition routing

Một bộ test nên có:

| Test | Kết quả kỳ vọng |
|---|---|
| Insert hai cặp (date,id) giống nhau | Bị từ chối bởi composite PK |
| Insert cùng id ở hai ngày khác nhau | Có thể thành công nếu PK chỉ là (date,id) |
| CREATE UNIQUE(id) trên parent RANGE(date) | Bị từ chối vì thiếu partition key |
| CREATE INDEX(id) không unique trên parent | Có thể tạo |
| Unique(id) trên từng child khác tháng | Không chặn ID trùng giữa children |
| WHERE date nằm trong một tháng | Có thể prune các tháng khác |
| WHERE id đơn lẻ | Không tự prune RANGE(date) |
| UPSERT với (date,id) | Conflict theo composite key |
| UPSERT chỉ conflict target (id) | Không có unique arbiter tương ứng |
| Foreign key(date,id) tới parent | Phù hợp với composite PK |
| Foreign key(id) tới parent | Không có unique key id ở parent |
| Thêm partition mới | Index/constraints parent phản ánh đúng |
| Index local chỉ ở một tháng | Không tự xuất hiện ở các tháng khác |
| Parent index ON ONLY | Ban đầu chưa valid |
| ATTACH đầy đủ child indexes | Parent index chuyển valid |
| Concurrent index build thất bại | Không đánh dấu hoàn tất; xử lý invalid |
| Đổi partition key trong UPDATE/UPSERT | Kiểm tra giới hạn và semantics cụ thể |
| Insert ngày ngoài mọi RANGE bound | Lỗi nếu không có DEFAULT phù hợp |
| Registry ID và insert event cùng transaction | Giữ consistency nếu mọi writer tuân thủ |
| Ghi đồng thời cùng ID vào registry | Unique registry chặn trùng |
| Phân vùng nhiều cấp | Constraint bao gồm khóa phân vùng các cấp liên quan |

### 35.1. Test đồng thời là bắt buộc cho global ID registry

Không chỉ test hai INSERT chạy tuần tự. Cần:

- Hai connection.
- Hai transaction cùng cố đăng ký event_id giống nhau.
- Xác nhận không cả hai transaction commit hai registry rows trùng ID.
- Xác nhận event row và registry row rollback/commit cùng nhau.
- Test retry khi request mất kết nối gần COMMIT.
- Test xóa và tạo lại ID theo chính sách retention.

**Một CHECK hoặc SELECT NOT EXISTS trước INSERT không thay thế UNIQUE constraint khi có ghi đồng thời.**

## 36. Những lỗi thường gặp

### Lỗi 1 — Nghĩ parent index là một global B-tree vật lý

Thực tế index partitioned parent là cấu trúc logic với các index vật lý theo partition.

### Lỗi 2 — Tạo PRIMARY KEY(id) trên bảng RANGE(date)

Parent PK thiếu partition key, bị PostgreSQL từ chối.

### Lỗi 3 — Thêm date vào PK rồi vẫn tuyên bố ID duy nhất toàn cục

`PRIMARY KEY(date,id)` chỉ unique cặp date+id.

### Lỗi 4 — Tạo UNIQUE(id) riêng ở mọi partition và nghĩ đã global

Hai partition khác nhau vẫn có thể chứa cùng id.

### Lỗi 5 — Xem sequence/UUID như UNIQUE constraint tuyệt đối

ID generation và uniqueness enforcement không phải cùng một cơ chế.

### Lỗi 6 — Dùng biểu thức partition key rồi kỳ vọng parent UNIQUE tự hiểu

Parent UNIQUE/PK có giới hạn với partition keys dùng biểu thức/hàm.

### Lỗi 7 — Bỏ qua subpartition key ở cây nhiều cấp

Một parent constraint có thể không hợp lệ nếu cấp con phân vùng tiếp theo cột chưa được đưa vào unique key.

### Lỗi 8 — Quên thay khóa ngoại khi PK thành composite

Bảng tham chiếu theo id đơn lẻ không còn bảo đảm định danh một event duy nhất.

### Lỗi 9 — ON CONFLICT(id) nhưng chỉ có PK(date,id)

Không có arbiter unique id đơn lẻ.

### Lỗi 10 — ON CONFLICT DO NOTHING và nghĩ sẽ tự ngăn ID trùng mọi tháng

DO NOTHING chỉ xử lý những conflict hiện có; không tạo global uniqueness.

### Lỗi 11 — Chỉ lọc id, không có partition key, rồi kỳ vọng pruning

RANGE(date) cần điều kiện date phù hợp để loại bớt partition.

### Lỗi 12 — Thấy partition pruning thì nghĩ chắc chắn Index Scan

Planner có thể dùng Seq Scan trong một partition nhỏ; pruning và index access khác nhau.

### Lỗi 13 — Đặt tất cả index nonunique phải có partition key

Đây là ràng buộc với UNIQUE/PK parent, không phải yêu cầu cho mọi nonunique index.

### Lỗi 14 — CREATE INDEX CONCURRENTLY trực tiếp trên parent

Đây là thao tác bị giới hạn; cần quy trình tạo index theo từng partition khi phù hợp.

### Lỗi 15 — Tạo parent ON ONLY rồi không ATTACH đủ child indexes

Index parent có thể chưa valid, migration chưa hoàn tất.

### Lỗi 16 — ATTACH một concurrent index build thất bại

Index con invalid không được coi là hoàn thành.

### Lỗi 17 — Nghĩ index local tháng 2 sẽ tự lan sang tháng 3

Index chỉ tạo cục bộ trên một child không phải policy parent.

### Lỗi 18 — Quên DEFAULT partition và provisioning tháng mới

INSERT ngày chưa được phủ bởi partition sẽ lỗi.

### Lỗi 19 — CHECK đếm tất cả partition rồi gọi đó là unique

CHECK row-level không thay thế cross-row UNIQUE constraint và không tự ngăn race.

### Lỗi 20 — Giữ tất cả index dù query không còn dùng

Nhiều index tăng chi phí ghi, WAL, storage và maintenance.

### Lỗi 21 — Nhìn chỉ số scan parent index và kết luận không dùng

Cần xem index scan thực tế trên các partition con và plan.

### Lỗi 22 — Thay đổi partition strategy mà không xét retention

HASH(id) giúp unique(id), nhưng dọn dữ liệu theo tháng khó hơn RANGE(date).

### Lỗi 23 — Registry có unique nhưng không ghi trong cùng transaction

Có thể còn registry không có event hoặc event không được đăng ký theo giao thức.

### Lỗi 24 — Xóa partition lịch sử mà bỏ qua foreign keys

Có thể phá quan hệ hoặc vướng constraint; cần kế hoạch retention nhất quán.

### Lỗi 25 — Tin rằng mỗi constraint đều chỉ được xác định bằng DDL parent

Cần kiểm chứng thực tế cấu trúc child, tính valid và các đường ghi/migration trong vận hành.

## 37. Bài tập thực hành có lời giải

### Bài 1. Partitioned index cha có chứa mọi index entry không?

**Đáp án:** không như một global B-tree vật lý duy nhất; các partition có index vật lý riêng.

### Bài 2. Vì sao UNIQUE(event_id) trên parent RANGE(event_date) không hợp lệ?

**Đáp án:** unique key thiếu partition key event_date, nên hai hàng cùng event_id có thể nằm ở hai partition khác nhau mà local indexes không phát hiện trùng.

### Bài 3. Viết PK hợp lệ cho events RANGE(event_date)

```sql
PRIMARY KEY (event_date, event_id)
```

**Đáp án:** đủ khóa phân vùng. Không bảo đảm event_id unique toàn cục.

### Bài 4. Hai hàng cùng event_id khác ngày có được phép không?

**Đáp án:** có thể, nếu PK chỉ (event_date,event_id) và các constraint khác không chặn.

### Bài 5. Hai hàng cùng cặp event_date,event_id?

**Đáp án:** không, bị PK từ chối.

### Bài 6. Chỉ mục nonunique có bắt buộc chứa event_date không?

**Đáp án:** không. `CREATE INDEX ON parent(event_id)` là khả năng hợp lệ.

### Bài 7. Truy vấn chỉ theo event_id có chắc prune được RANGE(event_date)?

**Đáp án:** không. Thiếu điều kiện date, PostgreSQL không xác định được một tháng duy nhất chỉ từ event_id theo schema này.

### Bài 8. Truy vấn lọc tháng 2 và tenant 7 có những cơ chế nào?

**Đáp án:** partition pruning có thể loại tháng 1, tháng 3; trong tháng 2 planner có thể dùng index hoặc Seq Scan theo chi phí.

### Bài 9. Tạo local index chỉ cho tháng 2

```sql
CREATE INDEX idx_part298_events_feb_event_type_lab
ON part298.events_2026_02(event_type);
```

**Đáp án:** index phục vụ tháng 2, không tự áp dụng các tháng khác.

### Bài 10. Parent partial index có tác dụng thế nào?

**Đáp án:** có thể tạo các partial indexes tương ứng trên children; query phải hàm ý predicate để planner sử dụng. Không biến partial unique thiếu partition key thành global unique.

### Bài 11. INCLUDE(event_type) có là khóa tìm B-tree không?

**Đáp án:** không. INCLUDE là payload giúp đọc, không phải key column dẫn đường hoặc phần khóa unique.

### Bài 12. Tại sao Index Only Scan vẫn có heap fetches?

**Đáp án:** PostgreSQL cần kiểm tra visibility MVCC khi heap page chưa all-visible.

### Bài 13. Có thể CREATE INDEX CONCURRENTLY trực tiếp trên partitioned parent không?

**Đáp án:** không theo hình thức tạo cả cây trực tiếp; dùng ON ONLY parent + concurrent indexes từng child + ATTACH phù hợp.

### Bài 14. Vì sao parent index ON ONLY ban đầu invalid?

**Đáp án:** các child indexes chưa được tạo/đính kèm đầy đủ, nên partitioned index definition chưa hoàn thiện.

### Bài 15. Khi nào index parent ON ONLY chuyển valid?

**Đáp án:** khi các partition index tương ứng cần thiết đã được attach đầy đủ và cấu trúc hợp lệ.

### Bài 16. Một child index CONCURRENTLY thất bại thì làm gì?

**Đáp án:** kiểm tra trạng thái index con, xử lý/xây lại theo runbook; không ATTACH và tuyên bố hoàn tất khi còn invalid.

### Bài 17. Viết FK hợp lệ tham chiếu events PK composite

```sql
FOREIGN KEY (event_date, event_id)
REFERENCES part298.events(event_date, event_id)
```

**Đáp án:** phù hợp với parent PK.

### Bài 18. Tại sao FK(event_id) không đủ trong schema?

**Đáp án:** parent không có unique key riêng trên event_id.

### Bài 19. ON CONFLICT theo khóa nào?

```sql
ON CONFLICT (event_date, event_id)
DO NOTHING
```

**Đáp án:** theo cặp khóa được PK bảo vệ, không theo event_id đơn lẻ.

### Bài 20. Nếu bắt buộc PK(event_id), đổi partition thế nào?

**Đáp án:** một phương án là HASH(event_id) với PK(event_id) và các hash partitions đầy đủ. Cân nhắc trade-off retention theo ngày.

### Bài 21. Registry ID bảo đảm gì?

**Đáp án:** bảng registry có PK(event_id) ngăn ID trùng trong registry; mọi writer events phải đăng ký ID trong cùng transaction mới biến nó thành protocol bảo vệ dữ liệu events.

### Bài 22. UUID có làm UNIQUE constraint không cần thiết?

**Đáp án:** không nếu nghiệp vụ yêu cầu ràng buộc tuyệt đối do database thực thi. UUID có xác suất va chạm thấp, không tương đương một constraint cross-partition.

### Bài 23. Tenant 7 và 8 cùng order_id có thể cùng tồn tại với PK(tenant_id,order_id)?

**Đáp án:** có, vì khóa chính bao gồm tenant_id. Đây là unique theo tenant, không phải global order_id.

### Bài 24. Partition nhiều cấp cần xét gì ở UNIQUE?

**Đáp án:** các khóa phân vùng ở các cấp liên quan phải được bao gồm theo những ràng buộc mà PostgreSQL có thể thực thi trên cây partition.

### Bài 25. Unique với NULL khác PK thế nào?

**Đáp án:** PK không cho NULL; UNIQUE có semantics NULL riêng, có thể dùng NULLS NOT DISTINCT theo phiên bản. Các lựa chọn đó không bỏ giới hạn partition key.

### Bài 26. Hàng tháng 4 INSERT vào fixture hiện tại được không?

**Đáp án:** không nếu chưa có partition tháng 4 và không có DEFAULT. Cần tạo partition mới.

### Bài 27. Xem các partition bằng SQL

```sql
SELECT relid::regclass, parentrelid::regclass, isleaf
FROM pg_partition_tree('part298.events'::regclass);
```

**Đáp án:** xem cây partition và mức lá.

### Bài 28. Kiểm tra valid của index parent

```sql
SELECT i.indisvalid
FROM pg_index AS i
WHERE i.indexrelid =
  'part298.idx_part298_measurements_device_time'::regclass;
```

**Đáp án:** parent được kỳ vọng valid sau khi ATTACH đủ child indexes.

### Bài 29. Viết query nhận biết trùng event_id toàn events

```sql
SELECT event_id, COUNT(*) AS n
FROM part298.events
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY event_id;
```

**Đáp án:** query **phát hiện** ID lặp; không tự ngăn hai transaction concurrent cùng tạo ID trùng.

### Bài 30. Vì sao không dùng một CHECK để ngăn trùng giữa các partitions?

**Đáp án:** CHECK không phải cross-row global uniqueness mechanism, và một phép SELECT COUNT trong kiểm tra tự viết có thể mắc race nếu không có cơ chế tương tranh thích hợp.

### Bài 31. Có thể xóa local index riêng trong một partition mà không ảnh hưởng parent không?

**Đáp án:** nếu là index độc lập không attached và không phục vụ constraint, có thể quản lý riêng theo quyền và DDL. Nếu là index con attached vào parent index hoặc constraint, phải xem dependency; không tự drop tùy tiện.

### Bài 32. Tại sao index bị ít scan không chắc dư thừa?

**Đáp án:** có thể phục vụ UNIQUE/PK/FK workload hiếm hoặc khoảng thời gian thống kê chưa đủ; phải kiểm tra constraint/dependencies và workload trước khi xóa.

## 38. Checklist trước khi đưa partitioned table vào production

| Câu hỏi | Lý do |
|---|---|
| Partition key là cột hay biểu thức? | Quyết định khả năng parent UNIQUE/PK |
| Các cấp subpartition dùng những khóa nào? | Unique có thể phải chứa khóa ở nhiều cấp |
| Business cần ID unique theo ngày, tenant hay toàn cục? | Chọn đúng schema |
| PK hiện tại có bị đổi nghĩa khi thêm partition key không? | Tránh trùng ID giữa các partition |
| FK bên ngoài có đủ composite key không? | Giữ tham chiếu hợp lệ |
| API tìm theo ID có biết partition key không? | Tránh scan tất cả partitions |
| Query nóng có điều kiện pruning phù hợp không? | Hạn chế số partition phải đọc |
| Nonunique index cần cột nào và thứ tự nào? | Tối ưu trong partition |
| Parent indexes và local-only indexes được quản lý ra sao? | Tránh thiếu/duplicate index |
| Có partial predicate hoặc INCLUDE nào đáng dùng? | Phù hợp workload, tránh index quá lớn |
| Có cần triển khai CONCURRENTLY từng partition không? | Giảm tác động DML |
| Parent index đã indisvalid=TRUE chưa? | Xác nhận build/ATTACH hoàn tất |
| Có xử lý index build thất bại/invalid không? | Tránh migration dở dang |
| Tạo/ATTACH partition có validation scan/lock nào? | Lập kế hoạch production |
| Có lịch tạo partition tương lai không? | Tránh INSERT không tìm thấy partition |
| DEFAULT partition có thể chứa dữ liệu cần chuyển khi mở partition mới? | Tránh overlap/attach lỗi |
| ON CONFLICT dùng đúng composite arbiter chưa? | Tránh UPSERT sai |
| Có UPDATE partition key cần di chuyển hàng không? | Hiểu giới hạn DML |
| Registry ID có giao thức ghi atomic chưa? | Bảo vệ global uniqueness |
| Có test nhiều connection cùng ID không? | Phát hiện race |
| Retention có tác động FK/registry/backup không? | Tránh mất tính nhất quán |
| Có theo dõi index size, usage và maintenance theo child không? | Tối ưu vận hành lâu dài |

## 39. Tài liệu PostgreSQL chính thức

Đối chiếu với phiên bản PostgreSQL đang dùng; cú pháp và một số khả năng trên partitioned table thay đổi theo phiên bản:

- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partition routing, indexes, unique/primary keys và giới hạn partitioned table.
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html): PARTITION BY, PARTITION OF và constraint.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index methods, INCLUDE, UNIQUE và CONCURRENTLY.
- [ALTER INDEX](https://www.postgresql.org/docs/current/sql-alterindex.html): ATTACH PARTITION cho index.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): ATTACH/DETACH PARTITION và constraints.
- [Partition Pruning](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING): loại bỏ partitions không liên quan.
- [Indexes](https://www.postgresql.org/docs/current/indexes.html): lựa chọn index, multicolumn, partial/index-only scans.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): UNIQUE, PRIMARY KEY, FK, CHECK và các ngữ nghĩa ràng buộc.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT` và những giới hạn của upsert.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): đọc kế hoạch, pruning và index scans.

Kiểm tra version:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

Các ví dụ được trình bày để học tập. Không coi chúng là kết quả thực thi trên một server cụ thể hoặc một migration production đã được kiểm thử.

## 40. Tổng kết

Đối với PostgreSQL declarative partitioning, hãy giữ bốn ý:

### 40.1. Index parent là logic, index con là vật lý

```text
events parent
   |
   +-- index partitioned parent
          |
          +-- local index tháng 1
          +-- local index tháng 2
          +-- local index tháng 3
```

Chỉ mục cha không tự trở thành một B-tree global bao phủ tất cả các tháng.

### 40.2. UNIQUE/PK cần chứa partition key

```text
PARTITION BY RANGE(event_date)

PRIMARY KEY(event_id)             -> Không hợp lệ ở parent
PRIMARY KEY(event_date,event_id)  -> Hợp lệ
```

Nhưng:

```text
UNIQUE(event_date,event_id)
    không đồng nghĩa UNIQUE(event_id)
```

### 40.3. Partition pruning và local index là hai tầng

```text
WHERE event_date = ...
    -> có thể prune tới partition phù hợp

WHERE tenant_id = ...
    -> có thể dùng local indexes ở nhiều partition

WHERE event_id = ...
    -> nếu thiếu date, có thể phải xét mọi tháng
```

### 40.4. Global ID cần một quyết định kiến trúc

Các lựa chọn chính:

- Partition theo chính `event_id` để parent PK(event_id) có thể được thực thi.
- Chấp nhận composite identity `(event_date,event_id)` và cập nhật FK/API tương ứng.
- Dùng registry ID không phân vùng với unique constraint cùng protocol ghi atomic.
- Dùng sequence/UUID làm cơ chế cấp ID, nhưng không nhầm nó với cưỡng chế UNIQUE toàn cục.

### Những nguyên tắc cần ghi nhớ

1. **Chọn partition key có xét cả dữ liệu và ràng buộc nghiệp vụ.**
2. **Parent UNIQUE và PRIMARY KEY phải bao gồm toàn bộ partition key phù hợp**; nếu partition key là biểu thức, có thêm giới hạn quan trọng.
3. **Chỉ mục unique từng partition không chứng minh unique toàn cục** cho khóa không quyết định partition.
4. **Foreign key và ON CONFLICT phải dùng đúng khóa thực sự duy nhất.**
5. **Nonunique index không có yêu cầu cứng giống unique index**, nhưng kế hoạch truy cập phải xét partition pruning.
6. **CREATE INDEX CONCURRENTLY trực tiếp trên parent bị hạn chế**; có thể xây từng child rồi ATTACH vào index parent ON ONLY.
7. **Thêm partition phải gắn với index/constraint policy và kiểm tra valid.**
8. **Bảng lớn không có nghĩa mọi query sẽ nhanh hơn sau phân vùng**; nhiều partition/index còn có chi phí planning và vận hành.
9. **CHECK, sequence, UUID, SELECT NOT EXISTS không tự thay global UNIQUE constraint** trong mọi lịch ghi đồng thời.
10. **Kiểm chứng bằng catalog, EXPLAIN và test concurrency** trước khi thay đổi production.

**Một câu để nhớ:** PostgreSQL phân vùng dữ liệu thành những bảng vật lý có index riêng; muốn ràng buộc duy nhất ở bảng cha, **khóa duy nhất phải tương thích với cách định tuyến partition**, nếu không bạn phải đổi mô hình định danh hoặc xây cơ chế global uniqueness khác.

