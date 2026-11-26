# Tạo bảng và nạp dữ liệu thử bằng cqlsh

**cqlsh (Cassandra Query Language Shell)** là công cụ dòng lệnh để kết nối đến Apache Cassandra, chạy câu lệnh CQL, xem schema và kiểm tra dữ liệu. Trước khi xây dựng ứng dụng bằng **Spring Data Cassandra**, nên tự tạo keyspace, định nghĩa bảng, ghi một tập dữ liệu nhỏ và chạy đúng các truy vấn mà ứng dụng sẽ dùng. Cách làm này giúp phát hiện sớm những sai lầm về **partition key**, **clustering columns**, kiểu dữ liệu và phạm vi truy vấn.

Trong bài thực hành này, chúng ta sẽ tạo bảng lưu đơn hàng **theo khách hàng và tháng**, nạp dữ liệu bằng `INSERT` hoặc `COPY FROM`, kiểm tra qua `SELECT`, rồi kết nối kiến thức đó với `CassandraRepository` và `CassandraTemplate`. Bài tập chỉ cần một node Cassandra dùng cho môi trường học; mọi cấu hình đơn node được nêu rõ để tránh áp dụng nhầm cho production.

## 1. Mục tiêu và kết quả cần đạt

Sau bài học, bạn có thể:

1. Mở `cqlsh` và xác nhận đang kết nối đến Cassandra mong muốn.
2. Tạo **keyspace** cho môi trường thử nghiệm với replication phù hợp một node.
3. Tạo bảng có **composite partition key** và **clustering columns** theo truy vấn dự kiến.
4. Nạp dữ liệu bằng CQL `INSERT`; biết khi nào có thể dùng `COPY FROM` với CSV.
5. Kiểm tra dữ liệu đã nạp, thứ tự trong partition và các ràng buộc CQL.
6. Lưu các lệnh tạo/nạp dữ liệu thành script `.cql` để chạy lại có kiểm soát.
7. Xác nhận bảng tạo bằng cqlsh có thể được ứng dụng Spring Data Cassandra truy cập.

Dữ liệu minh họa: hai khách hàng, mỗi khách có đơn hàng trong một hoặc nhiều tháng. Yêu cầu đọc chính là **“lấy các đơn mới nhất của một khách trong một tháng”**. Vì Cassandra thiết kế bảng theo truy vấn, chúng ta sẽ chọn khóa phù hợp ngay từ đầu.

## 2. Chuẩn bị Cassandra và cqlsh

### 2.1. Cần có gì?

- Một node hoặc cluster Cassandra đang chạy và có dịch vụ native transport/CQL trên cổng thường dùng **9042**.
- Công cụ `cqlsh` tương thích với phiên bản Cassandra đích. Khi dùng image Cassandra chính thức, `cqlsh` đã có sẵn trong container.
- Quyền tạo keyspace/table trong môi trường học. Nếu cluster bật xác thực, cần tài khoản được cấp quyền phù hợp.
- Khả năng chạy lệnh terminal; nếu dùng cách Docker, cần Docker Engine và đủ tài nguyên cho Cassandra.

**Ghi nhớ:** `cqlsh` là một *client*, còn Cassandra là một *database server*. Mở được cửa sổ cqlsh không có nghĩa đang kết nối đến node hoặc keyspace mong muốn; phải kiểm tra endpoint và schema.

### 2.2. Phương án A — Cassandra cục bộ bằng Docker

Ví dụ dùng image Cassandra **5.0** đã chọn cho phòng lab (không ngụ ý đây là bản mới nhất của mọi hệ thống):

```bash
docker run -d --name cassandra-lab \
  -p 127.0.0.1:9042:9042 \
  cassandra:5.0
```

Dấu `\` dùng để nối dòng trong shell kiểu Bash. Nếu chạy lệnh trên **PowerShell**, có thể viết trên một dòng:

```powershell
docker run -d --name cassandra-lab -p 127.0.0.1:9042:9042 cassandra:5.0
```

Cổng host chỉ lắng nghe trên `127.0.0.1` trong ví dụ này để dùng cho môi trường học trên máy cá nhân. Cassandra thường cần thời gian khởi động, vì vậy kiểm tra trạng thái node trước khi tạo bảng:

```bash
docker exec cassandra-lab nodetool status
```

Trong kết quả, trạng thái **`UN` (Up/Normal)** biểu thị node đang hoạt động bình thường trong ring. Nếu lệnh báo Cassandra chưa sẵn sàng, kiểm tra log khởi động:

```bash
docker logs cassandra-lab
```

Sau khi node sẵn sàng, mở cqlsh từ **bên trong container**:

```bash
docker exec -it cassandra-lab cqlsh
```

Bạn sẽ thấy prompt tương tự `cqlsh>`. Để thoát:

```sql
EXIT;
```

Nếu container tên `cassandra-lab` đã tồn tại từ buổi học trước, có thể khởi động lại bằng `docker start cassandra-lab`, rồi kiểm tra lại trạng thái. Không cần tạo container khác cho mỗi lần mở cqlsh.

### 2.3. Phương án B — Kết nối Cassandra đã có sẵn

Nếu `cqlsh` đã được cài trên máy và server cho phép kết nối TCP:

```bash
cqlsh 127.0.0.1 9042
```

Đổi host và port nếu môi trường có endpoint khác. Nếu cluster yêu cầu authentication/TLS, hãy dùng cấu hình cqlsh tương ứng với môi trường; **không đưa mật khẩu vào tài liệu, repository hoặc lịch sử lệnh shell**. Với cluster nhiều datacenter, xác nhận chính sách kết nối và quyền trước khi tạo schema.

Có thể xem thông tin cơ bản:

```sql
SHOW VERSION;
DESCRIBE KEYSPACES;
SELECT cluster_name, data_center, release_version FROM system.local;
```

- `SHOW VERSION` và `DESCRIBE` là **lệnh của cqlsh**, hỗ trợ khám phá và mô tả schema.
- `SELECT ... FROM system.local` là **CQL**, truy vấn metadata node mà client kết nối.
- Dấu `;` kết thúc câu lệnh CQL; đừng ghép lệnh terminal như `docker exec` vào prompt `cqlsh>`.

> Mọi lệnh tiếp theo giả định đã ở trong prompt `cqlsh>`, trừ khi có nhãn **Terminal** hoặc chú thích khác.

## 3. Tạo keyspace cho phòng lab

Keyspace là không gian tên cho các bảng và cũng chứa cấu hình **replication**. Với **một node chỉ để thực hành**, tạo keyspace như sau:

```sql
CREATE KEYSPACE IF NOT EXISTS sdc_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE sdc_lab;
```

`SimpleStrategy` cùng `replication_factor: 1` phù hợp cho bài tập một node. **Không dùng nguyên cấu hình này cho production nhiều datacenter**: ở đó thường cần `NetworkTopologyStrategy` và replication factor được lựa chọn theo kiến trúc thực tế, yêu cầu nhất quán và mức chịu lỗi.

Kiểm tra keyspace:

```sql
DESCRIBE KEYSPACE sdc_lab;
```

Kết quả nên có phần `CREATE KEYSPACE sdc_lab ...`. Lệnh `USE sdc_lab;` đặt keyspace mặc định cho session hiện tại. Nó **không** đổi keyspace mặc định của một kết nối Spring Data Cassandra ở nơi khác.

Nếu khi tạo keyspace nhận lỗi quyền truy cập, cần người quản trị cấp quyền thích hợp cho tài khoản học; không thử tạo keyspace khác trên một cluster chia sẻ nếu chưa được cho phép.

## 4. Từ yêu cầu đọc đến thiết kế bảng

Yêu cầu mẫu:

> Ứng dụng cần lấy **20 đơn hàng mới nhất của một khách hàng trong tháng được chọn**, và thỉnh thoảng cần xem đơn hàng từ một khoảng thời gian trong tháng đó.

Vì mọi truy vấn đều biết khách hàng và tháng, chọn **partition key** là `(customer_id, order_month)`. Trong partition, sắp đơn theo thời điểm tạo giảm dần; dùng `order_id` để phân biệt những đơn có cùng thời điểm.

| Cột | Kiểu CQL | Vai trò | Vì sao có trong bảng? |
|---|---|---|---|
| `customer_id` | `uuid` | Partition key, phần 1 | Xác định khách hàng |
| `order_month` | `text` | Partition key, phần 2 | Chia dữ liệu theo tháng |
| `ordered_at` | `timestamp` | Clustering column, phần 1 | Lấy đơn gần nhất trước |
| `order_id` | `uuid` | Clustering column, phần 2 | Bảo đảm phân biệt đơn cùng thời điểm |
| `status` | `text` | Regular column | Trạng thái đơn |
| `amount` | `decimal` | Regular column | Số tiền của đơn |

**Primary key đầy đủ:** `((customer_id, order_month), ordered_at, order_id)`.

Lưu ý về cú pháp:

- `PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)`: hai cột đầu tạo thành **một partition key kết hợp**; hai cột sau là **clustering columns**.
- `PRIMARY KEY (customer_id, order_month, ordered_at, order_id)`: chỉ `customer_id` là partition key; ba cột còn lại thành clustering. Đây là một **thiết kế khác**, không thể tự ý thay thế.
- Các row có cùng `customer_id` và `order_month` thuộc cùng **partition logic**, nhưng có thể khác `ordered_at` và `order_id`.

### 4.1. Tạo bảng bằng cqlsh

```sql
CREATE TABLE IF NOT EXISTS sdc_lab.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    ordered_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY (
        (customer_id, order_month),
        ordered_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
```

Ở đây:

- `WITH CLUSTERING ORDER BY` sắp row **trong từng partition**, không sắp dữ liệu toàn cluster.
- `ordered_at DESC` giúp lấy dữ liệu mới trước mà không cần sắp xếp tất cả kết quả bên ứng dụng.
- `order_id ASC` xác định thứ tự ổn định giữa những row có cùng `ordered_at`.
- `IF NOT EXISTS` giúp chạy lại script mà không lỗi khi bảng đã tồn tại; nó **không kiểm tra** xem bảng cũ có cấu trúc giống CQL hiện tại hay không. Vì vậy phải xem lại schema nếu bạn vừa thay đổi thiết kế.

Xem schema thực tế:

```sql
DESCRIBE TABLE sdc_lab.orders_by_customer_month;
```

Kiểm tra bảng có đúng composite partition key, đúng hai clustering columns và chiều `DESC/ASC`. Một lỗi nhỏ ở dấu ngoặc của `PRIMARY KEY` có thể khiến dữ liệu được phân vùng hoàn toàn khác dự kiến.

## 5. Nạp dữ liệu mẫu bằng INSERT

### 5.1. Quy tắc viết literal CQL

| Kiểu | Ví dụ trong CQL | Lưu ý |
|---|---|---|
| `uuid` | `d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001` | Định dạng UUID hợp lệ, không cần nháy đơn khi dùng dạng literal |
| `text` | `'2026-11'`, `'PAID'` | Dùng nháy đơn; nháy đơn bên trong giá trị được escape bằng cách nhân đôi |
| `timestamp` | `'2026-11-25T03:30:00Z'` | Có timezone `Z` để tránh nhập nhằng múi giờ |
| `decimal` | `199000.00` | Số thập phân, không đặt dấu phân cách hàng nghìn |
| `null` | `null` | Không dùng cho các cột primary key |

`timestamp` là một thời điểm; chuỗi `order_month` ở đây chỉ là **bucket của mô hình đọc**, phải được ứng dụng tính thống nhất từ thời điểm đơn hàng theo múi giờ đã quy ước. Trong demo, các mốc thời gian dùng UTC để dữ liệu dễ lặp lại.

### 5.2. Ghi sáu đơn hàng

Chạy các câu sau trong cqlsh. Mỗi `INSERT` là một mutation độc lập; việc viết nhiều câu liên tiếp **không tự tạo một transaction nhiều hàng**.

```sql
INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,
    '2026-11',
    '2026-11-25T03:30:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0001,
    'PAID',
    199000.00
);

INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,
    '2026-11',
    '2026-11-24T09:10:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0002,
    'CREATED',
    85000.50
);

INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,
    '2026-11',
    '2026-11-10T18:00:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0003,
    'SHIPPED',
    450000.00
);

INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,
    '2026-10',
    '2026-10-29T08:45:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0004,
    'PAID',
    120000.00
);

INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600002,
    '2026-11',
    '2026-11-25T11:45:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0005,
    'CREATED',
    99000.00
);

INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600002,
    '2026-11',
    '2026-11-21T06:20:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0006,
    'PAID',
    55000.00
);
```

Dữ liệu vừa nạp gồm ba partition:

| Partition key logic | Số row | `ordered_at` dự kiến, mới đến cũ |
|---|---:|---|
| Khách `...0001`, tháng `2026-11` | 3 | 25/11 → 24/11 → 10/11 |
| Khách `...0001`, tháng `2026-10` | 1 | 29/10 |
| Khách `...0002`, tháng `2026-11` | 2 | 25/11 → 21/11 |

Các ID và số tiền chỉ dùng cho môi trường học; chúng không đại diện dữ liệu khách hàng thật.

### 5.3. Hiểu INSERT trong Cassandra

Cassandra thực hiện **upsert**: ghi lại cùng **toàn bộ primary key** sẽ cập nhật row hiện có theo timestamp/luật hòa giải, không nhân đôi row đó. Ví dụ:

```sql
INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,
    '2026-11',
    '2026-11-24T09:10:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0002,
    'PAID',
    85000.50
);
```

Sau lệnh này, đơn `...0002` của khách `...0001` được cập nhật thành `PAID` (giả sử không có ghi cạnh tranh với timestamp lớn hơn). Thực hiện lại toàn bộ script seed cũng không tự động tạo thêm sáu row vì các khóa không đổi.

Không dùng cập nhật cột primary key như cách đổi regular column. Nếu thời điểm đặt hàng/đơn vị bucket thay đổi, cần cân nhắc tạo row ở khóa mới và xử lý row ở khóa cũ, cùng các read model liên quan.

## 6. Kiểm tra dữ liệu bằng SELECT

### 6.1. Đọc đúng một partition

```sql
SELECT customer_id, order_month, ordered_at, order_id, status, amount
FROM sdc_lab.orders_by_customer_month
WHERE customer_id = d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001
  AND order_month = '2026-11'
LIMIT 20;
```

Kỳ vọng: **3 row** của khách thứ nhất trong tháng 11, theo `ordered_at` giảm dần, với trạng thái đơn `...0002` là `PAID` nếu đã chạy ví dụ cập nhật ở trên. Không cần `ORDER BY` khi muốn thứ tự đúng với clustering order đã khai báo.

Truy vấn này xác định đủ **hai thành phần partition key**. Coordinator biết replica chịu trách nhiệm cho partition; các SSTable/caches tại replica sẽ được dùng theo đường đọc thực tế.

### 6.2. Giới hạn theo clustering column đầu tiên

```sql
SELECT ordered_at, order_id, status, amount
FROM sdc_lab.orders_by_customer_month
WHERE customer_id = d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001
  AND order_month = '2026-11'
  AND ordered_at >= '2026-11-20T00:00:00Z'
  AND ordered_at <  '2026-11-26T00:00:00Z';
```

Kỳ vọng: **2 row** vào ngày 24 và 25/11. `ordered_at` là clustering column đầu tiên, vì vậy ràng buộc một khoảng thời gian trong partition phù hợp với khóa đã thiết kế.

Lưu ý: `ORDER BY` của Cassandra chỉ hỗ trợ các cách sắp xếp phù hợp clustering và các điều kiện trên partition key. Nó không hoạt động như `ORDER BY` tùy ý của SQL quan hệ.

### 6.3. So sánh ba partition

Có thể chạy thêm ba truy vấn riêng để thấy ranh giới partition:

```sql
SELECT ordered_at, order_id, status
FROM sdc_lab.orders_by_customer_month
WHERE customer_id = d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001
  AND order_month = '2026-10';

SELECT ordered_at, order_id, status
FROM sdc_lab.orders_by_customer_month
WHERE customer_id = d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600002
  AND order_month = '2026-11';
```

Kỳ vọng lần lượt **1 row** và **2 row**. Một khách có nhiều tháng nghĩa là nhiều partition; dữ liệu của khách thứ hai không trộn vào partition của khách thứ nhất.

Nếu cần thống kê trên tập dữ liệu nhỏ, có thể dùng:

```sql
SELECT COUNT(*)
FROM sdc_lab.orders_by_customer_month
WHERE customer_id = d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001
  AND order_month = '2026-11';
```

Kỳ vọng `3` row. Tuy nhiên, `COUNT(*)` vẫn phải xử lý dữ liệu thuộc phạm vi truy vấn; **không xem đây là phép đếm O(1)** cho partition lớn hoặc dùng làm thống kê cho mọi API production.

### 6.4. Ví dụ truy vấn sai và vì sao sai

```sql
-- Thiếu thành phần order_month của composite partition key
SELECT * FROM sdc_lab.orders_by_customer_month
WHERE customer_id = d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001;

-- order_id là clustering column, không phải partition key
SELECT * FROM sdc_lab.orders_by_customer_month
WHERE order_id = 0e9ac839-6ec8-43a4-88b4-a1960b0f0001;

-- status là regular column, không phải clustering column
SELECT * FROM sdc_lab.orders_by_customer_month
WHERE customer_id = d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001
  AND order_month = '2026-11'
ORDER BY status;
```

Với schema hiện tại, các câu trên **không có đường truy vấn CQL thông thường hợp lệ** và sẽ bị từ chối (thông báo cụ thể tùy phiên bản). Không cố thêm `ALLOW FILTERING` cho mọi truy vấn thiếu khóa: điều đó có thể làm tăng lượng dữ liệu phải quét và gây độ trễ khó kiểm soát.

Nếu nghiệp vụ cần tra đơn theo `order_id` độc lập, hãy xem xét bảng đọc riêng `orders_by_id` hoặc cơ chế index phù hợp với yêu cầu và phiên bản triển khai.

## 7. Cách nạp dữ liệu thứ hai: COPY FROM CSV

`INSERT` phù hợp cho dữ liệu ví dụ ngắn và dễ đọc. Khi dữ liệu thử có nhiều dòng, `cqlsh` hỗ trợ lệnh **`COPY FROM`** để nhập CSV.

### 7.1. Chuẩn bị tệp CSV

Tạo file văn bản tên `orders.csv` với UTF-8 và nội dung ví dụ sau. Đây là **phương án thay thế** cho seed bằng `INSERT`: nếu đã chạy các lệnh trên, nhập lại những khóa tương tự là upsert, không tạo row khác với cùng primary key.

```csv
customer_id,order_month,ordered_at,order_id,status,amount
d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,2026-11,2026-11-25T03:30:00Z,0e9ac839-6ec8-43a4-88b4-a1960b0f0001,PAID,199000.00
d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,2026-11,2026-11-24T09:10:00Z,0e9ac839-6ec8-43a4-88b4-a1960b0f0002,PAID,85000.50
d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,2026-11,2026-11-10T18:00:00Z,0e9ac839-6ec8-43a4-88b4-a1960b0f0003,SHIPPED,450000.00
d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,2026-10,2026-10-29T08:45:00Z,0e9ac839-6ec8-43a4-88b4-a1960b0f0004,PAID,120000.00
d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600002,2026-11,2026-11-25T11:45:00Z,0e9ac839-6ec8-43a4-88b4-a1960b0f0005,CREATED,99000.00
d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600002,2026-11,2026-11-21T06:20:00Z,0e9ac839-6ec8-43a4-88b4-a1960b0f0006,PAID,55000.00
```

Nếu cqlsh chạy **trong container**, lệnh `COPY` sẽ đọc đường dẫn trong **container**, không phải file trên host. Đưa file vào container từ terminal máy chủ:

```bash
docker cp orders.csv cassandra-lab:/tmp/orders.csv
```

Sau đó, tại prompt `cqlsh>` bên trong container:

```sql
COPY sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
FROM '/tmp/orders.csv'
WITH HEADER = TRUE;
```

Nếu cqlsh chạy trên host, đổi đường dẫn sang đường dẫn file CSV mà **quá trình cqlsh trên host** nhìn thấy. `HEADER = TRUE` nói rằng dòng đầu chứa tên cột. Danh sách cột trong `COPY` phải khớp thứ tự trường trong CSV.

### 7.2. Kiểm tra sau khi import

Khi `COPY FROM` báo hoàn tất, **không chỉ tin vào số dòng đã gửi**. Hãy chạy lại các truy vấn ở mục 6 để xác nhận:

- Partition của khách thứ nhất, tháng 11 có **3 row**.
- Các cột `status`, `amount` và `ordered_at` đúng định dạng.
- Thứ tự theo `ordered_at DESC` đúng như thiết kế.
- Nếu có lỗi parse CSV, kiểm tra delimiter, quotation, header, kiểu UUID, decimal và timestamp.

Đối với dữ liệu rất lớn hoặc import liên tục, `COPY FROM` không phải giải pháp nạp dữ liệu phân tán hiệu năng cao mặc định. Hãy đánh giá công cụ/luồng ingestion phù hợp với khối lượng và phiên bản Cassandra, cũng như giới hạn tải ghi cho cluster.

## 8. Chạy lại bài thực hành từ file .cql

Khi đã thử tương tác thành công, nên lưu schema và seed thành file để cả nhóm dùng lại. Ví dụ tạo file `seed.cql` chứa:

```sql
CREATE KEYSPACE IF NOT EXISTS sdc_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS sdc_lab.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    ordered_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);

INSERT INTO sdc_lab.orders_by_customer_month
(customer_id, order_month, ordered_at, order_id, status, amount)
VALUES (
    d9f0c9a7-33e8-4b0e-a8ad-7fc7b2600001,
    '2026-11',
    '2026-11-25T03:30:00Z',
    0e9ac839-6ec8-43a4-88b4-a1960b0f0001,
    'PAID',
    199000.00
);

-- Bổ sung các INSERT ở mục 5.2 nếu cần nạp đủ sáu row.
```

Trên máy có `cqlsh`:

```bash
cqlsh 127.0.0.1 9042 -f seed.cql
```

Nếu chỉ sử dụng `cqlsh` trong Docker, chuyển file vào container và chạy:

```bash
docker cp seed.cql cassandra-lab:/tmp/seed.cql
docker exec cassandra-lab cqlsh -f /tmp/seed.cql
```

**Giới hạn cần biết:** `seed.cql` ví dụ này chỉ chứa một câu `INSERT` để minh họa cách chạy file. Muốn nạp đủ sáu row, phải bổ sung phần `INSERT` còn lại hoặc dùng `COPY FROM` ở mục 7. `CREATE TABLE IF NOT EXISTS` giúp chạy lặp lại khi schema không đổi, nhưng **không phải migration** cho những thay đổi primary key/table schema. Sau khi chạy file, luôn kiểm tra lỗi hiển thị và đọc lại dữ liệu.

Trong team, có thể tách file `schema.cql` và `seed.cql` để dễ quản lý, nhưng ứng dụng Spring Data không nên tự ý xóa/tạo lại bảng production mỗi khi khởi động.

## 9. Kiểm tra từ Spring Data Cassandra

Sau khi tạo bảng bằng cqlsh, ứng dụng Spring Boot dùng Spring Data Cassandra có thể kết nối cùng keyspace. Với môi trường Spring Boot có hỗ trợ nhóm cấu hình `spring.cassandra` (như Spring Boot 3.x), ví dụ `application.yml`:

```yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    keyspace-name: sdc_lab
    local-datacenter: datacenter1
```

Tên datacenter thực tế phải khớp kết quả:

```sql
SELECT data_center FROM system.local;
```

Nếu kết quả khác `datacenter1`, chỉnh `local-datacenter` theo môi trường. Khi ứng dụng chạy trong **một container khác**, `127.0.0.1` là chính container ứng dụng; phải dùng DNS/địa chỉ Cassandra mà container có thể truy cập qua mạng của chúng.

Với bảng hiện tại, khóa Java cần thể hiện đủ:

- Partition columns: `customer_id`, `order_month`.
- Clustering columns: `ordered_at`, `order_id`.
- Regular columns: `status`, `amount`.

Trong Spring Data Cassandra, có thể dùng `@PrimaryKeyClass` và `@PrimaryKeyColumn(type = PARTITIONED/CLUSTERED)` để ánh xạ khóa kết hợp, rồi định nghĩa entity với `@PrimaryKey` và repository tương ứng. Khi đọc qua `CassandraTemplate` hoặc repository, **CQL phía server vẫn đòi đúng các ràng buộc partition/clustering** như lúc thử trong cqlsh.

Ví dụ query mục tiêu của một method repository là:

```sql
SELECT *
FROM sdc_lab.orders_by_customer_month
WHERE customer_id = ?
  AND order_month = ?
LIMIT 20;
```

Dấu `?` trong ví dụ đại diện **bind marker của prepared statement** ở driver, không phải một câu lệnh đầy đủ để chép trực tiếp vào cqlsh và nhận kết quả. Trong cqlsh, bạn đã thay chúng bằng UUID và tháng thật ở mục 6.

Nếu query chạy tốt trong cqlsh nhưng ứng dụng lỗi, kiểm tra theo thứ tự: endpoint, keyspace, datacenter, credentials/TLS, mapping field/primary key, serialization của `timestamp` và truy vấn sinh ra. Không mặc định lỗi nằm ở database server.

## 10. Lỗi thường gặp khi thực hành

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Connection refused` / `Unable to connect` | Cassandra chưa chạy, chưa sẵn sàng, sai host/port hoặc kết nối bị chặn | Kiểm tra `docker logs`, `nodetool status`, cổng 9042 và endpoint |
| `Unauthorized` hoặc `AuthenticationFailed` | Chưa đăng nhập đúng hoặc tài khoản thiếu quyền | Dùng account/phương án xác thực được cấp; kiểm tra quyền keyspace |
| `Keyspace ... does not exist` | Chưa tạo keyspace, gõ sai tên hoặc kết nối nhầm cluster | `DESCRIBE KEYSPACES;` và `DESCRIBE KEYSPACE sdc_lab;` |
| `Unconfigured table` | Bảng chưa được tạo, sai keyspace/table | `DESCRIBE TABLE sdc_lab.orders_by_customer_month;` |
| `SyntaxException` khi tạo bảng | Thiếu dấu phẩy, ngoặc hoặc dấu `;` | Kiểm tra cú pháp `PRIMARY KEY ((...), ..., ...)` và thứ tự các cột |
| `InvalidRequest` do thiếu partition key | `WHERE` không cung cấp đủ `customer_id` và `order_month` | Thêm đủ hai điều kiện hoặc thiết kế bảng theo truy vấn |
| `InvalidRequest` ở `ORDER BY status` | Sắp xếp theo regular column | Sắp theo clustering hợp lệ hoặc tạo read model khác |
| `Invalid literal` / parse CSV error | UUID, timestamp, decimal hoặc số cột CSV sai | Kiểm tra từng giá trị, header và định dạng UTC |
| `COPY FROM` không thấy file | Tệp CSV không nằm trên máy/container chạy **cqlsh** | Chuyển file đúng vị trí, dùng đường dẫn tuyệt đối cqlsh có thể đọc |
| `CREATE TABLE IF NOT EXISTS` chạy nhưng schema không đổi | Bảng đã tồn tại với cấu trúc cũ | `DESCRIBE TABLE`; xử lý schema bằng migration có chủ đích |

### 10.1. Tránh những thói quen khó kiểm soát

- Không dùng `ALLOW FILTERING` để che mọi lỗi thiếu partition key; cách đó có thể tăng lượng dữ liệu phải quét.
- Không dùng `SELECT *` trên toàn bảng lớn trong production chỉ để “xem dữ liệu”. Với bài lab, ưu tiên `SELECT` theo partition key.
- Không coi `TRUNCATE` hoặc `DROP KEYSPACE` là bước dọn dẹp vô hại: chúng xóa dữ liệu trên phạm vi lớn. Với keyspace phòng lab, chỉ thực hiện khi chắc chắn môi trường và dữ liệu thuộc quyền quản lý của bạn.
- Không suy luận rằng `INSERT` đã ghi đúng chỉ vì cqlsh không in gì: đọc lại partition và so sánh khóa/giá trị.
- Không copy schema có `SimpleStrategy` và RF=1 từ lab lên cluster đa node mà chưa thiết kế replication, consistency và quyền truy cập.

## 11. Bài tập củng cố

**Bài tập 1 — Đổi dữ liệu:** thêm một đơn thứ bảy cho khách `...0002`, tháng 11. Dùng timestamp trong tháng 11 và một `order_id` chưa tồn tại. Chạy lại truy vấn partition đó và xác nhận nó có thêm một row, đúng thứ tự thời gian.

**Bài tập 2 — Phân biệt khóa:** tạo một đơn có **cùng `customer_id + order_month + ordered_at`** với đơn đã có, nhưng `order_id` mới. Hỏi: đây là row mới hay upsert? Sau đó ghi lại đúng `order_id` cũ để so sánh. *Gợi ý:* row được xác định bằng toàn bộ primary key.

**Bài tập 3 — Ranh giới partition:** thử truy vấn chỉ theo `customer_id` rồi giải thích vì sao thiếu `order_month`. Đề xuất thay đổi **mẫu truy vấn** hoặc read model nếu ứng dụng cần lịch sử của khách qua nhiều tháng.

**Bài tập 4 — CSV:** tạo file `orders.csv` với ít nhất hai dòng mới, dùng `COPY FROM`, xem kết quả import và xác minh bằng `SELECT` có đủ partition key.

**Bài tập 5 — Spring Data:** viết phác thảo một entity có khóa kết hợp và truy vấn repository để lấy đơn trong một tháng. Kiểm tra xem trường trong mapping và tên cột CQL có khớp nhau không; giải thích vì sao một method `findByStatus` đơn thuần không đủ cho bảng này.

### Câu hỏi tự kiểm tra

1. **Tại sao phải tạo keyspace trước khi tạo bảng?** Vì bảng thuộc keyspace; keyspace xác định namespace và replication của dữ liệu.
2. **`PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)` có bao nhiêu thành phần partition key?** Hai: `customer_id` và `order_month`. Hai cột còn lại là clustering.
3. **Tại sao các đơn của cùng khách ở hai tháng không cùng partition?** Vì `order_month` tham gia partition key.
4. **Chạy lại `INSERT` có cùng toàn bộ primary key sẽ tạo row thứ hai không?** Không; đó là upsert của cùng row.
5. **Tại sao `COPY FROM '/tmp/orders.csv'` trong container báo không có file dù file ở máy host?** Vì đường dẫn được giải quyết theo filesystem nơi **client cqlsh** đang chạy.
6. **Nếu query chạy trong cqlsh nhưng repository lỗi, nên kiểm tra gì trước?** Kiểm tra kết nối, keyspace, datacenter, mapping primary key/kiểu dữ liệu và CQL thực tế mà ứng dụng phát ra.

## Tài liệu tham khảo

- [Apache Cassandra — Getting Started](https://cassandra.apache.org/doc/stable/cassandra/getting-started/index.html): bắt đầu chạy Cassandra và các công cụ cơ bản.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): cách kết nối, câu lệnh shell, `COPY` và chạy script.
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): `CREATE KEYSPACE`, `CREATE TABLE` và `PRIMARY KEY`.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `SELECT`, `WHERE`, `ORDER BY` và `LIMIT`.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): thiết kế bảng theo truy vấn và kiểm soát partition.
- [Spring Data for Apache Cassandra — Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/): mapping entity, repository và template.
