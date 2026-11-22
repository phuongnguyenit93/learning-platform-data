# Định tuyến INSERT và UPDATE thay đổi khóa phân vùng trong PostgreSQL

Khi một bảng có hàng chục triệu hoặc hàng tỷ bản ghi, ứng dụng thường không muốn mọi thao tác đều đi qua một cấu trúc lưu trữ duy nhất. PostgreSQL hỗ trợ **declarative partitioning**: một **bảng phân vùng cha** (*partitioned table*) thể hiện một bảng logic, còn các **phân vùng con** (*partitions*) lưu những nhóm hàng khác nhau theo một **khóa phân vùng** (*partition key*).

Ví dụ, bảng đơn hàng được chia theo tháng:

~~~text
sales_events (bảng logic, PARTITION BY RANGE (event_date))
    |
    +-- sales_events_2026_01 : 01/01 <= event_date < 01/02
    |
    +-- sales_events_2026_02 : 01/02 <= event_date < 01/03
    |
    +-- sales_events_2026_03 : 01/03 <= event_date < 01/04
    |
    +-- sales_events_default : những giá trị chưa thuộc phân vùng trên
~~~

Câu hỏi đầu tiên là **khi INSERT vào bảng cha, hàng được gửi đến phân vùng nào?** Câu hỏi thứ hai khó hơn: **nếu UPDATE thay đổi `event_date` từ tháng 1 sang tháng 2, PostgreSQL xử lý thế nào để giữ đúng ranh giới phân vùng?**

Bài học thuộc chương **Phân vùng**, module **Database Engine Relational PostgreSQL**, và tập trung vào hai cơ chế đó. Sau bài này bạn sẽ hiểu:

- Cách PostgreSQL chọn phân vùng đích cho từng hàng `INSERT`.
- Vì sao biên của `RANGE` là **bao gồm cận dưới, loại trừ cận trên**.
- Cách quan sát phân vùng vật lý bằng `tableoid::regclass`.
- Điều gì xảy ra nếu không có phân vùng phù hợp, nếu có `DEFAULT` hoặc nếu giá trị khóa là `NULL`.
- Sự khác nhau giữa **UPDATE không đổi phân vùng** và **UPDATE khiến hàng chuyển phân vùng**.
- Vì sao chuyển hàng thường được triển khai dưới dạng **DELETE ở phân vùng nguồn + INSERT vào phân vùng đích** và những tác động đến trigger, index, WAL, khóa và transaction.
- Các giới hạn của `PRIMARY KEY`/`UNIQUE` khi dùng bảng phân vùng, và mối liên hệ với `ON CONFLICT`.
- Cách tránh lỗi khi nhiều transaction đồng thời cập nhật một hàng đang được chuyển phân vùng.
- Quy trình kiểm tra, sửa dữ liệu sai ngày, vận hành phân vùng mới và thực hành hai phiên PostgreSQL.

> **Điểm mấu chốt:** Với declarative partitioning, PostgreSQL định tuyến hàng theo **giá trị khóa phân vùng**. Đừng hiểu `UPDATE event_date = ...` chỉ là thay đổi một ô dữ liệu vô hại: nếu giá trị mới thuộc phân vùng khác, đó là một thay đổi vị trí lưu trữ của hàng logic.

## 1. Bảng cha logic và bảng con vật lý

Với bảng không phân vùng, một câu `INSERT INTO sales_events ...` thường ghi một tuple vào chính heap của bảng đó.

Với bảng phân vùng:

~~~sql
CREATE TABLE sales_events (
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    amount numeric(12,2) NOT NULL
) PARTITION BY RANGE (event_date);
~~~

bảng `sales_events` là **bảng cha phân vùng**. Các hàng được lưu ở các partition con tương ứng, không nằm trong heap dữ liệu thông thường của bảng cha.

~~~mermaid
flowchart TD
    I["INSERT INTO sales_events"] --> R["Partition routing theo event_date"]
    R --> J["Tháng 01: sales_events_2026_01"]
    R --> F["Tháng 02: sales_events_2026_02"]
    R --> M["Tháng 03: sales_events_2026_03"]
    R --> D["DEFAULT nếu không khớp các partition tường minh"]
~~~

Ứng dụng có thể truy vấn qua cha:

~~~sql
SELECT *
FROM sales_events
WHERE event_date >= DATE '2026-02-01'
  AND event_date < DATE '2026-03-01';
~~~

PostgreSQL sẽ xét các phân vùng cần thiết theo planner/executor. Những hàng trả về vẫn có cùng các cột logic dù thực tế lưu trong nhiều quan hệ con.

### Phân biệt ba việc

| Việc | Khi nào? | Mục tiêu |
| --- | --- | --- |
| **Partition routing** | `INSERT` và `UPDATE` khiến khóa phân vùng đổi | Chọn phân vùng **đích để ghi** |
| **Partition pruning** | Lập kế hoạch hoặc thực thi một truy vấn phù hợp | Bỏ qua các phân vùng **không cần đọc** |
| **Partition maintenance** | Tạo, đính kèm, tách, xóa, bảo trì partition | Quản lý **vòng đời cấu trúc và dữ liệu** |

Routing và pruning đều sử dụng thông tin partition bounds, nhưng không phải cùng một thao tác. Có index tốt không đồng nghĩa việc định tuyến INSERT trở nên không cần thiết.

## 2. Khóa phân vùng là gì?

Khóa phân vùng quyết định hàng thuộc nhóm nào. PostgreSQL có ba chiến lược declarative partitioning phổ biến:

| Kiểu | Cách phân chia | Ví dụ |
| --- | --- | --- |
| `RANGE` | Khoảng giá trị có cận | Đơn hàng theo ngày/tháng |
| `LIST` | Tập giá trị cụ thể | Đơn theo vùng hoặc loại trạng thái |
| `HASH` | Phân phối theo giá trị băm của khóa | Chia tải theo tenant ID |

Ví dụ:

~~~sql
PARTITION BY RANGE (event_date)
PARTITION BY LIST (region_code)
PARTITION BY HASH (tenant_id)
~~~

Với `RANGE (event_date)`, **mỗi hàng được định tuyến theo giá trị `event_date` của chính hàng đó**, không theo thời điểm nó được INSERT.

Một đơn tạo hôm nay nhưng có `event_date = DATE '2026-01-15'` vẫn được đưa vào phân vùng tháng 1, không phải phân vùng tháng hiện tại.

### Khóa phân vùng không đồng nghĩa primary key

- **Partition key** dùng để xác định **địa điểm lưu trữ**.
- **Primary key** dùng để định danh và bảo vệ tính duy nhất theo phạm vi ràng buộc.
- **Foreign key** dùng để bảo vệ quan hệ tham chiếu.

Một cột có thể tham gia nhiều vai trò, nhưng **không vì là partition key mà tự duy nhất**.

## 3. Cận RANGE: bao gồm dưới, loại trừ trên

Một partition theo tháng:

~~~sql
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
~~~

chứa những hàng có:

~~~text
2026-01-01 <= event_date < 2026-02-01
~~~

Vì vậy:

- `2026-01-01` thuộc tháng 1.
- `2026-01-31` thuộc tháng 1.
- `2026-02-01` **không** thuộc tháng 1; thuộc tháng 2 nếu tháng 2 đã được tạo.
- `2025-12-31` không thuộc tháng 1.

Quy tắc **[cận dưới, cận trên)** giúp các khoảng liên tiếp không trùng nhau:

~~~text
Jan: [2026-01-01, 2026-02-01)
Feb: [2026-02-01, 2026-03-01)
Mar: [2026-03-01, 2026-04-01)
~~~

Nếu dùng một giá trị kiểu `date`, không cần tự ghi `23:59:59` để chỉ cuối tháng. Cận trên loại trừ diễn đạt ranh giới chính xác hơn.

## 4. Dựng bộ dữ liệu lab

Các ví dụ dùng schema `partition_lab` riêng.

**Cảnh báo:** đoạn thiết lập sử dụng `DROP SCHEMA IF EXISTS partition_lab CASCADE`, xóa mọi đối tượng có sẵn trong schema đó. Chỉ chạy trong **database học tập do bạn quản lý**, không chạy trên production hoặc schema chứa dữ liệu cần giữ.

### 4.1. Tạo bảng cha phân vùng

~~~sql
-- CHỈ CHẠY TRONG DATABASE LAB.
DROP SCHEMA IF EXISTS partition_lab CASCADE;
CREATE SCHEMA partition_lab;

CREATE TABLE partition_lab.sales_events (
    event_date date NOT NULL,
    event_id bigint NOT NULL,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'paid', 'cancelled')),
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_sales_events
        PRIMARY KEY (event_date, event_id)
) PARTITION BY RANGE (event_date);
~~~

Hai quyết định quan trọng:

1. Bảng được phân vùng **theo ngày của sự kiện**, không theo `created_at` mặc định.
2. Primary key gồm **`event_date` và `event_id`**. Lý do ràng buộc có khóa phân vùng sẽ được giải thích ở phần `UNIQUE`.

### 4.2. Tạo các phân vùng tháng

~~~sql
CREATE TABLE partition_lab.sales_events_2026_01
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE partition_lab.sales_events_2026_02
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE partition_lab.sales_events_2026_03
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE partition_lab.sales_events_default
PARTITION OF partition_lab.sales_events
DEFAULT;
~~~

`DEFAULT` là phân vùng nhận những giá trị **không khớp partition tường minh nào**. Với schema này, đó có thể là ngày tháng 12/2025, tháng 4/2026 hoặc các ngày khác ngoài ba tháng đã định.

Việc có DEFAULT là lựa chọn thiết kế, **không phải yêu cầu bắt buộc** của mọi bảng phân vùng. Nó giúp không mất request do thiếu partition, nhưng cũng có thể che lỗi chưa tạo partition tháng tiếp theo.

### 4.3. Nạp dữ liệu qua bảng cha

~~~sql
INSERT INTO partition_lab.sales_events (
    event_date,
    event_id,
    tenant_id,
    status,
    amount,
    note
)
VALUES
    ('2026-01-05', 1001, 1, 'new',       120.00, 'Jan A'),
    ('2026-01-31', 1002, 1, 'paid',      250.00, 'Jan end'),
    ('2026-02-01', 1003, 2, 'new',       180.00, 'Feb start'),
    ('2026-02-18', 1004, 2, 'new',        90.00, 'Feb B'),
    ('2026-03-01', 1005, 1, 'paid',      350.00, 'Mar start'),
    ('2026-03-31', 1006, 3, 'new',        70.00, 'Mar end'),
    ('2026-04-01', 1007, 3, 'new',        40.00, 'Beyond explicit months');
~~~

Cả bảy hàng được gửi tới **một lệnh INSERT trên bảng cha**, nhưng PostgreSQL sẽ chọn partition riêng cho từng tuple theo `event_date`.

### 4.4. Quan sát vị trí vật lý

~~~sql
SELECT
    event_id,
    event_date,
    tenant_id,
    status,
    amount,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
ORDER BY event_date, event_id;
~~~

Kết quả dự kiến theo partition:

| event_id | event_date | Phân vùng |
| ---: | --- | --- |
| 1001 | 2026-01-05 | `partition_lab.sales_events_2026_01` |
| 1002 | 2026-01-31 | `partition_lab.sales_events_2026_01` |
| 1003 | 2026-02-01 | `partition_lab.sales_events_2026_02` |
| 1004 | 2026-02-18 | `partition_lab.sales_events_2026_02` |
| 1005 | 2026-03-01 | `partition_lab.sales_events_2026_03` |
| 1006 | 2026-03-31 | `partition_lab.sales_events_2026_03` |
| 1007 | 2026-04-01 | `partition_lab.sales_events_default` |

`tableoid` là **system column** giúp nhận biết quan hệ vật lý chứa tuple. Ép kiểu `::regclass` cho phép hiển thị tên quan hệ thay vì chỉ OID.

Tên có thể được hiển thị với hoặc không có prefix schema, tùy `search_path` và cách PostgreSQL render `regclass`.

## 5. Cơ chế định tuyến INSERT qua bảng cha

Khi ứng dụng thực thi:

~~~sql
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-10', 2001, 4, 99.00);
~~~

PostgreSQL:

1. Nhận một tuple với `event_date = 2026-02-10`.
2. Xác định partition key của bảng cha.
3. Tìm partition có bounds bao phủ giá trị đó.
4. Chèn tuple vào `sales_events_2026_02`.
5. Áp dụng những ràng buộc, index, trigger và kiểm tra cần thiết.
6. Cho transaction quyết định commit hoặc rollback.

~~~mermaid
flowchart TD
    A["INSERT vào parent"] --> B["Đọc event_date của tuple"]
    B --> C{"Trong Jan?"}
    C -->|"Có"| J["INSERT partition Jan"]
    C -->|"Không"| D{"Trong Feb?"}
    D -->|"Có"| F["INSERT partition Feb"]
    D -->|"Không"| E{"Trong Mar?"}
    E -->|"Có"| M["INSERT partition Mar"]
    E -->|"Không"| G{"Có DEFAULT?"}
    G -->|"Có"| H["INSERT partition DEFAULT"]
    G -->|"Không"| X["Lỗi không có partition phù hợp"]
~~~

Mỗi hàng trong một batch được xét theo giá trị khóa phân vùng riêng. Đây không phải thao tác COPY toàn bộ dữ liệu tới mọi child rồi lọc sau.

### Kiểm tra bằng RETURNING

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-10', 2001, 4, 99.00)
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

`RETURNING` trả dữ liệu của hàng được tạo, bao gồm partition chứa tuple theo ngữ nghĩa PostgreSQL. `ROLLBACK` giữ nguyên dataset ban đầu.

## 6. Một INSERT nhiều hàng có thể đi vào nhiều phân vùng

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES
    ('2026-01-10', 2011, 4, 10.00),
    ('2026-02-10', 2012, 4, 20.00),
    ('2026-03-10', 2013, 4, 30.00),
    ('2026-04-10', 2014, 4, 40.00)
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

Bốn hàng sẽ được định tuyến lần lượt tới Jan, Feb, Mar và DEFAULT.

### Tính nguyên tử của statement

Một câu `INSERT` nhiều hàng là một statement SQL. Nếu **một hàng gây lỗi làm toàn statement thất bại** mà không được xử lý theo cơ chế hợp lệ, không nên kỳ vọng các hàng đầu của statement đã được commit thành công riêng.

Trong transaction thông thường, statement lỗi còn có thể khiến transaction ở trạng thái aborted cho tới `ROLLBACK` hoặc rollback về savepoint phù hợp.

Vì vậy với dữ liệu nhập từ nhiều nguồn, cần quyết định:

- Muốn **toàn batch cùng thành công/cùng thất bại**?
- Hay muốn **chia batch và thu thập hàng lỗi** theo giao thức import riêng?
- Dữ liệu sai thời gian nên bị từ chối, sửa trước khi INSERT hay được lưu vào một vùng quarantine có kiểm soát?

Không coi DEFAULT là cơ chế thu thập lỗi hoàn chỉnh nếu chưa có bước giám sát và phân loại.

## 7. INSERT trực tiếp vào phân vùng con khác gì INSERT qua cha?

Thông thường nên ghi qua bảng cha:

~~~sql
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-20', 2021, 2, 55.00);
~~~

PostgreSQL tự chọn partition.

Nếu ghi **trực tiếp vào child**:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events_2026_02 (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-20', 2022, 2, 55.00);

ROLLBACK;
~~~

câu lệnh nhắm thẳng vào một quan hệ có ràng buộc phân vùng. Giá trị `2026-02-20` thuộc bounds của Feb nên hợp lệ.

Nhưng:

~~~sql
-- CỐ Ý SAI: không được định tuyến sang March vì nhắm thẳng Feb.
INSERT INTO partition_lab.sales_events_2026_02 (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-03-10', 2023, 2, 55.00);
~~~

phải bị từ chối vì hàng không thỏa partition constraint của Feb.

**Nguyên tắc:** dùng **bảng cha** làm điểm ghi thống nhất, trừ khi bạn có lý do vận hành rõ ràng để ghi trực tiếp child và đã bảo đảm bounds. Ghi trực tiếp không phải cách buộc PostgreSQL cất một hàng “sai tháng” trong partition mong muốn.

## 8. Không có partition phù hợp thì điều gì xảy ra?

Trong lab hiện tại có DEFAULT, nên ngày ngoài Jan–Mar thường được đưa vào `sales_events_default`.

Để quan sát trường hợp **không có DEFAULT**, tạo bảng thử riêng:

~~~sql
CREATE TABLE partition_lab.missing_destination_demo (
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    description text
) PARTITION BY RANGE (event_date);

CREATE TABLE partition_lab.missing_destination_jan
PARTITION OF partition_lab.missing_destination_demo
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

INSERT thuộc tháng 1:

~~~sql
BEGIN;

INSERT INTO partition_lab.missing_destination_demo (
    event_id, event_date, description
)
VALUES (1, '2026-01-15', 'inside bounds');

ROLLBACK;
~~~

INSERT thuộc tháng 2:

~~~sql
-- CỐ Ý GÂY LỖI: bảng demo chỉ có partition tháng 1.
INSERT INTO partition_lab.missing_destination_demo (
    event_id, event_date, description
)
VALUES (2, '2026-02-15', 'no target partition');
~~~

PostgreSQL sẽ báo lỗi vì **không tìm được partition đích** cho giá trị đó. Nếu đang ở trong transaction explicit, rollback trước khi tiếp tục khi transaction đã aborted.

### Lỗi thiếu partition không phải lý do tự đổi event_date

Không nên sửa ngày 15/02 thành 31/01 chỉ để INSERT thành công. Làm vậy thay đổi **sự thật nghiệp vụ**.

Giải pháp đúng có thể là:

- Tạo partition tháng 2.
- Dùng chính sách DEFAULT đã được thiết kế và giám sát.
- Từ chối dữ liệu ngoài vùng được hỗ trợ.
- Chuyển dữ liệu không hợp lệ vào staging/quarantine riêng để xử lý.

## 9. DEFAULT: an toàn trước lỗi thiếu phân vùng nhưng có chi phí vận hành

Trong lab:

~~~sql
SELECT
    event_id,
    event_date,
    tableoid::regclass AS stored_in
FROM partition_lab.sales_events
WHERE event_id = 1007;
~~~

Hàng ngày 01/04 nằm trong `sales_events_default`.

DEFAULT có hai mặt:

**Lợi ích:**

- INSERT vẫn có nơi lưu khi partition tháng tới chưa tạo kịp.
- Hạn chế lỗi trong ingestion pipeline.
- Cho phép định nghĩa quy trình kiểm tra dữ liệu ngoài bounds.

**Rủi ro:**

- Có thể che việc lịch tạo partition đã thất bại.
- DEFAULT có thể lớn dần, khiến truy vấn phải xử lý dữ liệu ngoài phân vùng dự kiến.
- Khi thêm partition tường minh mới, PostgreSQL phải bảo đảm DEFAULT **không chứa hàng thuộc bounds mới**.
- Nếu DEFAULT đang chứa hàng tháng 4, không thể chỉ giả định tạo partition Apr mới là những hàng ấy tự động chuyển sang partition mới.

### Quan sát lượng dữ liệu trong DEFAULT

~~~sql
SELECT
    COUNT(*) AS default_rows,
    MIN(event_date) AS min_date,
    MAX(event_date) AS max_date
FROM partition_lab.sales_events_default;
~~~

Với seed ban đầu, `default_rows = 1`.

Hệ thống thật nên giám sát số hàng trong DEFAULT và cảnh báo khi tăng bất thường. DEFAULT không phải thay thế vĩnh viễn cho quản lý partition theo thời gian.

## 10. Thêm partition mới khi DEFAULT đã chứa dữ liệu tương ứng

Giả sử cần tạo partition tháng 4:

~~~sql
-- Chỉ là cú pháp mục tiêu; không chạy trực tiếp nếu DEFAULT
-- đã có hàng thuộc tháng 4 mà chưa chuẩn bị migration.
CREATE TABLE partition_lab.sales_events_2026_04
PARTITION OF partition_lab.sales_events
FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
~~~

Bởi `sales_events_default` hiện có hàng ngày `2026-04-01`, PostgreSQL phải kiểm tra các ràng buộc phân vùng và có thể **từ chối thao tác** nếu việc định nghĩa partition mới xung đột với dữ liệu đang lưu trong DEFAULT.

**PostgreSQL không tự di chuyển toàn bộ hàng đã lưu trong DEFAULT sang partition mới chỉ vì bạn thêm DDL.**

Quy trình migration cần được thiết kế riêng, chẳng hạn:

1. Xác định các hàng DEFAULT thuộc tháng 4.
2. Lập kế hoạch khóa và giao dịch, tránh concurrent INSERT vào cùng khoảng ngày.
3. Chuyển dữ liệu đang nằm sai vị trí phân vùng sang nơi thích hợp bằng quy trình được kiểm soát.
4. Đảm bảo DEFAULT không còn chứa giá trị thuộc bounds mới.
5. Tạo/ATTACH partition tháng 4 theo quy tắc phù hợp.
6. Kiểm tra tính đầy đủ, uniqueness và ứng dụng sau thay đổi.

Đây có thể là thao tác nhạy cảm trên bảng lớn vì `ATTACH PARTITION` hoặc thao tác sửa bounds cần validation và khóa. Không tự áp một script “xóa rồi chèn lại” lên production mà chưa có phương án bảo toàn dữ liệu và downtime/lock budget.

## 11. NULL trong khóa phân vùng

Trong lab:

~~~sql
event_date date NOT NULL
~~~

vì vậy một INSERT với `event_date = NULL` sẽ vi phạm `NOT NULL`:

~~~sql
-- CỐ Ý SAI: ngày NULL không hợp lệ theo schema.
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES (NULL, 3001, 1, 10.00);
~~~

Nếu một bảng phân vùng khác **cho phép khóa phân vùng NULL**, quy tắc routing phụ thuộc chiến lược và các partition đã khai báo. Với `RANGE` và `LIST`, DEFAULT có thể nhận một số giá trị không khớp partition tường minh, bao gồm NULL khi được phép. Với `LIST` còn có thể khai báo partition dành cho giá trị NULL theo cú pháp phù hợp.

Trong nghiệp vụ ngày tháng, lựa chọn tốt thường là **khóa phân vùng NOT NULL và có chính sách xử lý giá trị không xác định rõ ràng**, tránh để NULL âm thầm đi vào một DEFAULT vô hạn.

## 12. UPDATE không thay đổi khóa phân vùng

Ví dụ đổi trạng thái một sự kiện tháng 1:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    status = 'paid',
    amount = 130.00,
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING
    event_id,
    event_date,
    status,
    amount,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

`event_date` vẫn là 05/01/2026. Hàng logic vẫn thuộc partition Jan.

Điều đó **không có nghĩa PostgreSQL sửa tuple tại chỗ**. Cơ chế MVCC thông thường của `UPDATE` vẫn áp dụng: có thể tạo phiên bản tuple mới trong heap của partition Jan.

Điểm phân biệt là **hàng không phải chuyển sang quan hệ con khác** vì khóa phân vùng không vượt bounds.

### UPDATE khóa nhưng vẫn ở cùng partition

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-01-20'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

Ngày đổi từ 05/01 sang 20/01, nhưng vẫn nằm trong khoảng Jan. Đây là UPDATE của khóa phân vùng **không phải row movement**.

**Chỉ khi giá trị mới thuộc một partition khác thì có chuyển phân vùng.**

## 13. UPDATE làm thay đổi khóa sang partition khác

Đây là cơ chế trung tâm của bài học.

Giả sử hàng `event_id = 1001` đang ở Jan:

~~~text
event_id   = 1001
event_date = 2026-01-05
partition  = sales_events_2026_01
~~~

Một nghiệp vụ sửa ngày sự kiện:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    event_date = DATE '2026-02-12',
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

SELECT
    event_id,
    event_date,
    status,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_id = 1001;

ROLLBACK;
~~~

Trong transaction, `RETURNING` và `SELECT` sau đó sẽ cho thấy hàng logic 1001 có `event_date = 2026-02-12` ở **partition Feb**.

Sau `ROLLBACK`, dữ liệu đã commit của lab lại ở ngày 05/01 trong Jan.

### Tại sao không thể để nguyên trong Jan?

Partition Jan có bounds:

~~~text
2026-01-01 <= event_date < 2026-02-01
~~~

Hàng có ngày 12/02 **không còn thỏa ràng buộc của Jan**. PostgreSQL phải bảo đảm mỗi partition chỉ chứa những hàng hợp lệ theo partition constraint.

Vì vậy, khi hỗ trợ row movement cho UPDATE qua bảng phân vùng, PostgreSQL phải tìm partition đích dựa vào **giá trị khóa sau cập nhật**.

## 14. Row movement thực chất là DELETE + INSERT ở mức lưu trữ

Một UPDATE làm hàng đổi partition không chỉ là sửa con trỏ trong metadata. PostgreSQL thực hiện cơ chế di chuyển có ý nghĩa tương tự:

~~~text
1. Xác định hàng nguồn trong partition Jan.
2. Áp giá trị UPDATE: event_date = 2026-02-12.
3. Kiểm tra hàng mới thuộc partition Feb.
4. Xóa phiên bản hàng logic ở partition Jan.
5. Chèn phiên bản tương ứng vào partition Feb.
6. Bảo vệ bằng cùng transaction, constraints và các lock thích hợp.
~~~

~~~mermaid
flowchart LR
    A["Jan: event 1001, 2026-01-05"] --> U["UPDATE event_date = 2026-02-12"]
    U --> D["DELETE tuple nguồn ở Jan"]
    U --> I["INSERT tuple đích ở Feb"]
    D --> T["Cùng một transaction"]
    I --> T
    T --> R["Sau COMMIT: một hàng logic ở Feb"]
~~~

Về ngữ nghĩa SQL ứng dụng, bạn đã chạy **một câu UPDATE**. Về thực thi bên trong và tác động row-level trigger/index, đó có thể là **một DELETE và một INSERT ở hai relation khác nhau**.

### Không phải hai commit độc lập

Nếu câu UPDATE/transaction thất bại, PostgreSQL không được phép chỉ commit phần DELETE ở nguồn mà bỏ phần INSERT ở đích trong một transaction nguyên tử.

**Atomicity vẫn được giữ**: chuyển hàng không được làm mất dữ liệu vì hệ thống “xóa thành công rồi quên chèn” chỉ do một exception thông thường bên trong statement.

Điều này không loại bỏ các tác động ngoài database nếu trigger hoặc ứng dụng gọi API bên ngoài một cách không an toàn; các side effect đó phải được thiết kế riêng.

## 15. Kiểm tra số hàng trước và sau chuyển vùng

Một bài thực hành để xác nhận tính nhất quán:

~~~sql
BEGIN;

SELECT
    event_id,
    event_date,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_id = 1001;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-03-15'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

SELECT COUNT(*) AS total_logical_rows
FROM partition_lab.sales_events
WHERE event_id = 1001;

SELECT
    COUNT(*) FILTER (
        WHERE tableoid = 'partition_lab.sales_events_2026_01'::regclass
    ) AS in_jan,
    COUNT(*) FILTER (
        WHERE tableoid = 'partition_lab.sales_events_2026_03'::regclass
    ) AS in_mar
FROM partition_lab.sales_events
WHERE event_id = 1001;

ROLLBACK;
~~~

Trong transaction, dự kiến:

- `total_logical_rows = 1`.
- `in_jan = 0`.
- `in_mar = 1`.

Điều này xác nhận hàng logic đã được chuyển, không bị nhân đôi vì UPDATE.

**Lưu ý:** primary key của lab là `(event_date,event_id)`. Nó không cấm một hàng khác có `event_id = 1001` ở ngày khác nếu ứng dụng cố INSERT riêng. Vì vậy việc đếm `event_id` trong bài chỉ có ý nghĩa khi dataset đã biết không có ID trùng ở ngày khác.

## 16. UPDATE qua bảng cha hay trực tiếp partition?

Khi cần sửa ngày có khả năng vượt bounds, câu lệnh nên nhắm vào **bảng cha phân vùng**:

~~~sql
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-15'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;
~~~

Lý do:

- Bảng cha biết toàn bộ cây partition cần xét.
- Hệ thống có đủ thông tin để chọn đích mới.
- Câu SQL không gắn cứng logic nghiệp vụ với một child cụ thể.
- Dễ giữ cùng một interface DML khi thêm partition mới.

Không nên viết:

~~~sql
-- Không dùng như cách chung để chuyển hàng sang Feb.
UPDATE partition_lab.sales_events_2026_01
SET event_date = DATE '2026-02-15'
WHERE event_id = 1001;
~~~

rồi mặc định kết quả sẽ được định tuyến như khi thao tác qua bảng cha. Khi nhắm trực tiếp vào một leaf, các ràng buộc/đường thực thi phụ thuộc cấu trúc và phiên bản; để code ổn định, **hãy dùng parent làm điểm ghi cho những nghiệp vụ có thể đổi partition**.

### Không cập nhật bảng con chỉ để “tăng tốc chắc chắn”

Truy vấn tới partition cụ thể có thể giảm công việc của planner trong một số trường hợp, nhưng tăng coupling với tên partition. PostgreSQL có partition pruning để tránh đọc những child không liên quan khi query qua parent được viết phù hợp.

## 17. Chuyển từ Jan sang Feb hay từ Jan sang DEFAULT

Nếu update ngày sang một partition tường minh:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-21'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

đích là partition Feb.

Nếu update sang ngày chưa có partition tường minh:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-05-15'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

đích là `sales_events_default`.

Nếu bảng **không có DEFAULT** và không có partition phù hợp, UPDATE chuyển khóa có thể **thất bại** vì không xác định được đích. Việc UPDATE tự động sinh partition mới là điều **không có** trong declarative partitioning mặc định.

## 18. Lỗi khi chuyển tới partition không tồn tại

Dùng bảng `missing_destination_demo` chỉ có partition Jan.

~~~sql
BEGIN;

INSERT INTO partition_lab.missing_destination_demo (
    event_id, event_date
)
VALUES (11, '2026-01-10');

-- CỐ Ý GÂY LỖI: không có Feb và không có DEFAULT.
UPDATE partition_lab.missing_destination_demo
SET event_date = DATE '2026-02-10'
WHERE event_date = DATE '2026-01-10'
  AND event_id = 11;

-- Sau lỗi, phải ROLLBACK transaction.
ROLLBACK;
~~~

Khi không có đích mới, PostgreSQL không thể lưu hàng trong Jan vì giá trị mới không thuộc bounds của Jan. Transaction không được coi là đã hoàn thành thành công.

### Cần phân biệt với UPDATE không tìm thấy hàng

~~~sql
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-10'
WHERE event_date = DATE '2026-01-09'
  AND event_id = 1001;
~~~

Câu này có thể cập nhật **0 hàng** vì `WHERE` không khớp. Đó là trường hợp khác với “đã tìm thấy hàng nhưng không có partition đích”.

Ứng dụng nên dùng `UPDATE ... RETURNING` hoặc số hàng bị tác động để phân biệt yêu cầu không còn đúng trạng thái ban đầu với lỗi cấu trúc phân vùng.

## 19. PRIMARY KEY và UNIQUE trên bảng phân vùng

Một ràng buộc `PRIMARY KEY` hoặc `UNIQUE` khai báo ở **bảng cha phân vùng** cần đáp ứng quy tắc PostgreSQL cho declarative partitioning: các cột khóa phân vùng **phải được bao gồm trong ràng buộc duy nhất**. Với khóa phân vùng dùng biểu thức/hàm, còn có các giới hạn riêng khi khai báo các ràng buộc này.

Vì sao?

PostgreSQL chủ yếu duy trì các **index trên từng partition**. Nếu chỉ `UNIQUE(event_id)` trong khi bảng chia theo `event_date`, hai hàng cùng `event_id` nhưng hai ngày khác nhau có thể nằm ở hai partition và các unique index cục bộ không tự nhìn thấy nhau.

Trong lab, vì vậy chúng ta chọn:

~~~sql
PRIMARY KEY (event_date, event_id)
~~~

thay vì:

~~~sql
-- CỐ Ý SAI cho bảng phân vùng theo event_date:
ALTER TABLE partition_lab.sales_events
ADD CONSTRAINT uq_only_event_id UNIQUE (event_id);
~~~

Constraint chỉ trên `event_id` không bao gồm partition key, nên không đáp ứng điều kiện unique của parent partitioned table.

### Composite PK không bảo đảm event_id duy nhất toàn bảng

Hai bản ghi:

~~~text
event_date = 2026-01-05, event_id = 9001
event_date = 2026-02-05, event_id = 9001
~~~

**khác composite key**, vì ngày khác nhau. Chúng có thể cùng tồn tại theo ràng buộc chính của bảng, dù về nghiệp vụ bạn có thể không muốn vậy.

Không được dùng `PRIMARY KEY (event_date,event_id)` rồi tuyên bố PostgreSQL đã bảo đảm **`event_id` đơn lẻ** duy nhất toàn hệ thống.

## 20. Cần duy nhất event_id toàn hệ thống thì thiết kế sao?

Nếu nghiệp vụ yêu cầu ID không được lặp giữa các tháng, có một vài chiến lược:

1. **Chọn partition key phù hợp với khóa duy nhất**, ví dụ partition theo hash của ID nếu không cần range-by-date cho mục tiêu lưu trữ.
2. **Thiết kế khóa nghiệp vụ gồm date/tenant** nếu đó thật sự là định danh tự nhiên của đối tượng.
3. **Dùng bảng registry không phân vùng có `PRIMARY KEY(event_id)`**, ghi registry và hàng partitioned trong cùng transaction.
4. **Dùng sequence/UUID để giảm xác suất trùng khi sinh ID**, nhưng nhớ rằng việc sinh ID theo quy ước không tự bằng một ràng buộc unique toàn bảng nếu ID khác nguồn có thể được đưa vào.
5. **Đổi mô hình dữ liệu** nếu việc thường xuyên sửa ngày đang xung đột với yêu cầu identity ổn định.

Ví dụ registry:

~~~sql
CREATE TABLE partition_lab.event_identity_registry (
    event_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Một luồng tạo mới có thể:

~~~sql
BEGIN;

INSERT INTO partition_lab.event_identity_registry(event_id)
VALUES (6001);

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-18', 6001, 1, 10.00);

COMMIT;
~~~

Nếu hai transaction cố nhận cùng `event_id`, registry có unique key chặn một bên. Tuy nhiên ứng dụng phải **bắt buộc mọi luồng ghi tuân cùng giao thức**, tránh bypass registry, và cần chính sách xóa/cập nhật registry khi dữ liệu partitioned thay đổi.

### Vì sao registry phải cùng transaction?

Nếu INSERT registry commit trước rồi INSERT partitioned row lỗi, bạn có thể có một ID “được giữ chỗ” nhưng không có sự kiện tương ứng. Có workflow cố ý cho phép trạng thái đó, nhưng phải thiết kế rõ recovery. Với bài toán tạo một event nguyên tử, đặt hai INSERT trong cùng transaction là cách cơ bản.

## 21. UPDATE ngày và xung đột với composite primary key

Giả sử đã có:

~~~text
(2026-01-05, event_id=1001)
(2026-02-18, event_id=1004)
~~~

Bạn cố chuyển event 1001 sang ngày 18/02 mà giữ ID 1001 thì **chưa xung đột** với event 1004 vì cặp khóa khác nhau.

Nhưng nếu đã có một event khác với khóa:

~~~text
(2026-02-18, event_id=1001)
~~~

thì việc chuyển event 1001 từ Jan sang `(2026-02-18,1001)` phải vi phạm uniqueness của composite PK.

Có thể thử an toàn trên lab:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-18', 1001, 1, 5.00);

-- CỐ Ý GÂY LỖI: đích (2026-02-18,1001) đã tồn tại.
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-18'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;

ROLLBACK;
~~~

Nếu có unique violation, transaction sẽ bị lỗi và cần rollback. PostgreSQL không tự hợp nhất hai hàng chỉ vì event_id trông giống nhau.

## 22. ON CONFLICT xử lý duplicate trong INSERT như thế nào?

Với composite PK:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-01-05', 1001, 1, 120.00)
ON CONFLICT (event_date, event_id)
DO NOTHING
RETURNING event_id, event_date;

ROLLBACK;
~~~

Vì hàng `(2026-01-05,1001)` đã tồn tại, nhánh `DO NOTHING` trả **0 hàng**.

Một upsert cập nhật trường không-key:

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-01-05', 1001, 1, 135.00)
ON CONFLICT (event_date, event_id)
DO UPDATE
SET
    amount = EXCLUDED.amount,
    updated_at = clock_timestamp()
RETURNING
    event_id, event_date, amount,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

Ở đây hàng xung đột nằm ở Jan, nhánh UPDATE chỉ sửa amount, không thay ngày, nên **không cần chuyển partition**.

### Cùng event_id nhưng ngày khác không được xem là conflict

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-02-05', 1001, 1, 135.00)
ON CONFLICT (event_date, event_id) DO NOTHING
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

Dù `event_id = 1001` đã có ở Jan, cặp `(event_date,event_id)` mới **khác**, nên INSERT có thể tạo **hàng thứ hai**. Điều này đúng theo constraint, dù có thể sai theo định danh nghiệp vụ bạn muốn.

## 23. Một giới hạn quan trọng của ON CONFLICT DO UPDATE

Với PostgreSQL trong các phiên bản hỗ trợ declarative partitioned upsert hiện đại, `INSERT ... ON CONFLICT DO UPDATE` **không hỗ trợ chuyển chính hàng xung đột sang partition khác** bằng cách đổi partition key trong nhánh UPDATE.

Ví dụ dễ gây nhầm:

~~~sql
-- CỐ Ý SAI: nhánh DO UPDATE cố đổi partition key
-- của hàng xung đột từ Jan sang Feb.
INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-01-05', 1001, 1, 140.00)
ON CONFLICT (event_date, event_id)
DO UPDATE
SET event_date = DATE '2026-02-05';
~~~

Điều này **không tương đương** một câu `UPDATE` bình thường nhắm vào bảng cha và cho phép row movement.

Cách làm đúng khi nghiệp vụ thực sự muốn sửa ngày:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    event_date = DATE '2026-02-05',
    amount = 140.00
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

### Kết luận cho upsert

- `INSERT` mới: route theo khóa mới.
- `ON CONFLICT DO NOTHING`: bỏ qua hàng trùng composite key.
- `ON CONFLICT DO UPDATE`: thích hợp cho update tại partition đang chứa hàng xung đột; không dựa vào nó để di chuyển hàng sang partition khác.
- `UPDATE` qua parent: con đường rõ ràng để thay partition key và cho phép row movement theo phiên bản PostgreSQL hỗ trợ.

Đừng viết “UPSERT sẽ tự tìm hàng theo event_id rồi dời sang tháng mới” nếu unique key thực tế là cặp `(event_date,event_id)`.

## 24. Trigger khi UPDATE làm chuyển partition

Row movement có tác động đặc biệt đến trigger.

Về nguyên tắc trong PostgreSQL, vì một UPDATE chuyển partition được thực hiện theo luồng **DELETE nguồn + INSERT đích**, những trigger mức hàng có thể được kích hoạt khác với một UPDATE ở cùng partition.

Với cơ chế row movement thông thường:

- Row-level **BEFORE UPDATE** của partition nguồn được xét.
- Row-level **BEFORE DELETE** của partition nguồn được xét.
- Row-level **BEFORE INSERT** của partition đích được xét.
- Về hậu xử lý mức hàng, **AFTER DELETE** ở nguồn và **AFTER INSERT** ở đích có thể được kích hoạt thay cho **AFTER UPDATE** của cùng một hàng di chuyển.
- Statement-level trigger liên quan câu `UPDATE` được xử lý theo quy tắc statement trigger trên bảng đích SQL; không được coi một UPDATE đã chuyển vùng là hai câu lệnh SQL riêng do ứng dụng gửi.

**Chi tiết trigger là lý do phải đọc tài liệu đúng PostgreSQL major version**, đặc biệt khi hệ thống có audit, outbox hoặc các trigger cập nhật bảng khác.

### Không biến một UPDATE thành hai tác động nghiệp vụ ngoài ý muốn

Nếu ứng dụng có trigger AFTER INSERT phát event “đơn vừa được tạo” và AFTER DELETE phát event “đơn bị xóa”, một thao tác **sửa ngày sự kiện** có thể bị hiểu sai là **hủy đơn cũ và tạo đơn mới** ở consumer nếu trigger/outbox không phân biệt row movement.

Hãy xác định rõ:

- Event “row inserted physically” hay “business entity created”?
- Event “row deleted physically” hay “business entity cancelled”?
- Một chuyển partition có nên phát event nghiệp vụ riêng `event.date_corrected`?
- Consumer có idempotency/deduplication theo business key không?

Không dựa chỉ vào `TG_OP` của row trigger để suy ra chính xác ý nghĩa nghiệp vụ ở mọi tình huống.

## 25. Lab trigger: quan sát DELETE và INSERT khi chuyển vùng

Tạo log thực hành, **không có tích hợp gửi email hay gọi hệ thống bên ngoài**.

~~~sql
CREATE TABLE partition_lab.dml_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action text NOT NULL,
    relation_name text NOT NULL,
    event_id bigint NOT NULL,
    event_date date NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION partition_lab.log_sales_event_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO partition_lab.dml_log(
            action, relation_name, event_id, event_date
        )
        VALUES (
            TG_OP,
            TG_RELID::regclass::text,
            OLD.event_id,
            OLD.event_date
        );
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO partition_lab.dml_log(
            action, relation_name, event_id, event_date
        )
        VALUES (
            TG_OP,
            TG_RELID::regclass::text,
            NEW.event_id,
            NEW.event_date
        );
    END IF;

    -- Return value của AFTER ROW trigger không được dùng.
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_sales_event_audit_ins_del
AFTER INSERT OR DELETE
ON partition_lab.sales_events
FOR EACH ROW
EXECUTE FUNCTION partition_lab.log_sales_event_row();
~~~

Trong declarative partitioning, row-level triggers khai báo trên bảng cha được áp dụng qua các partition theo cơ chế PostgreSQL.

Thử:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-12'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;

SELECT
    action,
    relation_name,
    event_id,
    event_date
FROM partition_lab.dml_log
ORDER BY log_id;

ROLLBACK;
~~~

Bạn có thể quan sát **hành động DELETE ở Jan và INSERT ở Feb** tương ứng row movement. Các dòng log được chèn trong cùng transaction, nên rollback hoàn tác cả log lẫn thay đổi ngày.

### Không chạy trigger này trên bảng production chỉ để xem thử

Trigger log vào bảng khác cũng làm tăng WAL, thời gian thực thi và lock/constraint. Trên production, việc thêm trigger để quan sát có thể làm thay đổi chính workload đang đo.

Sau bài lab, chỉ dùng schema thực hành đã được cô lập. Nếu muốn xóa toàn bộ dữ liệu lab, chỉ thực hiện lệnh reset schema theo quy trình bạn đã xác nhận.

## 26. BEFORE trigger có được đổi đích partition tùy ý không?

Một ý tưởng nguy hiểm:

> “Tôi sẽ luôn INSERT vào tháng hiện tại, rồi trong BEFORE INSERT trigger tự sửa `event_date` sang tháng khác để PostgreSQL định tuyến lại.”

Không nên thiết kế dựa trên giả định này. PostgreSQL áp dụng những giới hạn khi **BEFORE ROW trigger** cố thay đổi partition key theo hướng làm hàng thuộc một partition khác với đường routing đã chọn; nó không phải cơ chế chung để trigger tự định tuyến lại vô hạn.

Cách an toàn là:

1. **Chuẩn hóa và xác định khóa phân vùng trước khi gửi INSERT**.
2. Đưa dữ liệu qua **bảng cha**.
3. Cho PostgreSQL route theo khóa đã xác định.
4. Dùng constraint và trigger để validate/nghiệp vụ, **không để trigger tự “bẻ” phân vùng bất ngờ**.

Với UPDATE cũng cần xét tương tác giữa BEFORE triggers và row movement. Nếu trigger sửa các trường liên quan partition key, kiểm tra behavior đúng phiên bản và có test rõ ràng.

## 27. Foreign key và row movement

Một event có thể được bảng khác tham chiếu.

Nếu khóa định danh là:

~~~text
(event_date, event_id)
~~~

và một bảng child dùng foreign key tới cặp này, thì việc sửa `event_date` **cũng là sửa một phần khóa tham chiếu**.

Các hệ quả có thể có:

- Foreign key cần được kiểm tra ở bảng con.
- Nếu thiết kế `ON UPDATE CASCADE`, việc đổi key có thể kéo theo cập nhật hàng con.
- Nếu có `RESTRICT`/`NO ACTION` theo điều kiện cụ thể, transaction có thể thất bại nếu làm child tham chiếu sai.
- Chi phí thực thi có thể tăng đáng kể nếu rất nhiều bảng con/tham chiếu.
- Mức khóa và concurrency có thể phức tạp hơn một UPDATE cột thông thường.

**Bài học thiết kế:** nếu ngày sự kiện thường bị sửa, việc đưa ngày vào primary key có thể khiến toàn bộ mô hình foreign key phải chịu chi phí di chuyển khóa. Cần xem lại cách định danh đối tượng và chiến lược phân vùng trước khi chọn date-based composite PK chỉ vì cú pháp thuận tiện.

### Không hiểu “row movement” là identity của đối tượng tự đổi

Ứng dụng có thể coi event_id là một đối tượng duy nhất, trong khi database dùng composite PK để bảo đảm uniqueness trong phạm vi partition. Hai cách nhìn phải được thiết kế nhất quán; không tự dựa vào `ctid` hoặc `tableoid` như business ID lâu dài.

## 28. UPDATE FROM và nguy cơ một hàng có nhiều nguồn

PostgreSQL hỗ trợ cập nhật theo bảng nguồn:

~~~sql
WITH date_corrections (
    event_id,
    old_date,
    new_date
) AS (
    VALUES
        (1001::bigint, DATE '2026-01-05', DATE '2026-02-12'),
        (1002::bigint, DATE '2026-01-31', DATE '2026-03-05')
)
UPDATE partition_lab.sales_events AS e
SET
    event_date = c.new_date,
    updated_at = clock_timestamp()
FROM date_corrections AS c
WHERE e.event_id = c.event_id
  AND e.event_date = c.old_date
RETURNING
    e.event_id,
    e.event_date,
    e.tableoid::regclass AS physical_partition;
~~~

Khi chạy trên lab, bọc bằng `BEGIN ... ROLLBACK` để không sửa seed.

### Một nguy cơ riêng của UPDATE FROM

Nếu bảng `date_corrections` có **nhiều hàng nguồn** khớp cùng một hàng đích với `new_date` khác nhau, kết quả UPDATE có thể không như bạn mong đợi; PostgreSQL không cam kết lấy hàng nguồn nào để áp cho một hàng đích theo ý nghĩa nghiệp vụ nếu JOIN không duy nhất.

Vì vậy cần:

- Bảo đảm một correction xác định cho mỗi khóa đích.
- Có unique constraint trên khóa correction nếu lưu thành bảng.
- Hoặc chọn bản ghi ưu tiên bằng `ROW_NUMBER`/`DISTINCT ON` theo quy tắc rõ ràng.
- Xác định old_date thực sự khớp để tránh sửa nhầm một event_id xuất hiện ở nhiều partition.

**Đổi ngày sai trong hàng triệu bản ghi không nên bắt đầu bằng UPDATE FROM khi nguồn chưa được dedupe.**

## 29. UPDATE nhiều hàng có thể gửi tới nhiều partition đích

Một statement:

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = event_date + 31
WHERE event_date >= DATE '2026-01-01'
  AND event_date < DATE '2026-02-01'
RETURNING
    event_id,
    event_date,
    tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

Với seed:

- Jan 05 + 31 ngày → Feb 05.
- Jan 31 + 31 ngày → Mar 03.

Cùng một `UPDATE` có thể chuyển **các hàng nguồn Jan sang nhiều partition đích khác nhau**. Mỗi hàng được xét theo giá trị khóa phân vùng mới.

Điều này khác với việc “đổi tên partition Jan thành Feb”: đổi tên bảng chỉ tác động metadata, không sửa giá trị `event_date` và không phải là cách dịch ngày cho từng hàng.

### Cần cân nhắc hiệu năng

Một UPDATE hàng loạt chuyển hàng qua partition có thể gây:

- Nhiều thao tác DELETE/INSERT vật lý.
- WAL, index maintenance ở cả nguồn và đích.
- Row triggers, FK checks.
- Lock contention.
- Dead tuples tại partition nguồn.
- Áp lực VACUUM và replication.
- Transaction dài nếu cập nhật hàng triệu dòng một lần.

Hãy đánh giá batch size và kế hoạch vận hành trước khi migration số lượng lớn.

## 30. Transaction đồng thời: row movement có thể gây serialization failure

Phân vùng không loại bỏ MVCC và row-level locks. Khi hai transaction cùng tác động một hàng, hệ thống vẫn phải phối hợp.

Có một tình huống đặc biệt: một transaction **di chuyển hàng sang partition khác**, trong khi transaction thứ hai đã bắt đầu thao tác UPDATE/DELETE đối với phiên bản cũ.

Trong các phiên bản PostgreSQL hỗ trợ row movement, tình huống cạnh tranh nhất định có thể gây lỗi như:

~~~text
ERROR: tuple to be updated was already moved to another partition
SQLSTATE: 40001 (serialization_failure)
~~~

Thông điệp cụ thể phụ thuộc phiên bản/câu lệnh, nhưng điểm cần hiểu là **khi hàng đã được chuyển, PostgreSQL không luôn có thể tự tái áp một UPDATE/DELETE đồng thời trên cùng hàng như trường hợp cập nhật không đổi partition**.

### Vì sao không thể chỉ “chờ rồi UPDATE tiếp”?

Một row movement thay đổi quan hệ vật lý nguồn/đích. Transaction còn lại có thể đã bắt đầu tìm hàng trong một partition cụ thể và có snapshot/điều kiện cũ. Việc tự động đuổi theo hàng sang partition khác trong mọi tình huống có thể vi phạm ngữ nghĩa concurrency.

Giải pháp an toàn khi nhận `40001` là **rollback rồi retry toàn transaction**, đọc lại hàng và quyết định nghiệp vụ theo trạng thái mới.

## 31. Thực hành hai phiên: UPDATE chạm hàng đang chuyển partition

Mở hai cửa sổ `psql` kết nối cùng database lab.

**Lưu ý:** Ví dụ này dùng `COMMIT` thật để thể hiện concurrency. Chỉ chạy khi lab còn đúng seed `(2026-01-05,1001)`, không có thao tác khác trên hàng này, và không dùng trên production.

**Phiên A:**

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-12'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

-- Chưa COMMIT; giữ transaction A mở.
~~~

**Phiên B, chạy khi A chưa commit:**

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET
    status = 'paid',
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, status;

-- Có thể phải chờ A.
~~~

**Phiên A kết thúc:**

~~~sql
COMMIT;
~~~

Sau khi A commit, statement B đang chờ **có thể nhận lỗi concurrency/serialization** vì hàng đã chuyển sang partition khác. Trong những lịch thực thi khác (ví dụ B chỉ bắt đầu sau A commit), B có thể đơn giản cập nhật 0 hàng do `WHERE event_date='2026-01-05'` không còn khớp.

Nếu B báo lỗi:

~~~sql
ROLLBACK;
~~~

Nếu B không lỗi, kết thúc transaction B phù hợp với kết quả quan sát, rồi kiểm tra bằng một transaction mới.

### Kiểm tra trạng thái sau cuộc đua

~~~sql
SELECT
    event_id,
    event_date,
    status,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_id = 1001;
~~~

Sau đó chỉ trong lab, khi tất cả các phiên đã kết thúc, có thể khôi phục ngày và status:

~~~sql
UPDATE partition_lab.sales_events
SET
    event_date = DATE '2026-01-05',
    status = 'new',
    updated_at = clock_timestamp()
WHERE event_date = DATE '2026-02-12'
  AND event_id = 1001;
~~~

### Bài học concurrency

- Một UPDATE thành công không có nghĩa mọi transaction khác cũng tự động “đi theo” hàng vừa chuyển.
- Một lỗi `40001` là tín hiệu cần **retry transaction**, không phải thêm `ON CONFLICT DO NOTHING` vào một câu UPDATE.
- Nếu client luôn gửi lại `old_date` cũ, sau retry nó có thể nhận 0 hàng. Phải quyết định nghiệp vụ: “chỉ sửa nếu ngày chưa đổi” hay “tìm theo event_id để áp sửa mới”.
- Với hệ thống ngoài database, retry cần idempotency để không phát side effect lặp.

## 32. SERIALIZABLE, REPEATABLE READ và READ COMMITTED

Mức isolation ảnh hưởng cách PostgreSQL xử lý snapshot và xung đột:

| Mức isolation | Điểm cần nhớ khi UPDATE chuyển partition |
| --- | --- |
| `READ COMMITTED` | Statement mới có snapshot mới; trong cuộc đua row movement vẫn có thể gặp `40001` trong trường hợp đặc biệt |
| `REPEATABLE READ` | Snapshot transaction nhất quán; xung đột cập nhật từ transaction khác có thể làm transaction abort thay vì tự dùng phiên bản mới |
| `SERIALIZABLE` | Có thêm phát hiện serialization anomalies; cần sẵn sàng retry khi `40001` |

Với mọi mức isolation, **row movement vẫn phải tôn trọng bounds và constraints**. Isolation không cho phép đặt dữ liệu sai phân vùng.

### Retry cái gì?

Đúng:

~~~text
BEGIN transaction mới
  SELECT dữ liệu mới/các điều kiện nghiệp vụ cần thiết
  Kiểm tra trạng thái và quyền
  UPDATE nếu hợp lệ
COMMIT
~~~

Sai:

~~~text
Giữ lại quyết định tính từ snapshot cũ
Chỉ lặp đúng câu UPDATE cuối
Giả định event_date cũ vẫn đúng
~~~

Nếu một thay đổi ngày đã được transaction khác commit, nghiệp vụ cần quyết định nên báo conflict, chấp nhận ngày mới hay yêu cầu người dùng xác nhận.

## 33. Đừng dùng tableoid/ctid làm định danh bền vững

Trong một truy vấn kiểm tra, `tableoid::regclass` hữu ích để thấy hàng đang nằm ở partition nào.

Nhưng:

- `tableoid` phản ánh OID relation vật lý, có thể thay đổi ý nghĩa khi bảo trì/attach/detach/rebuild hoặc chuyển phân vùng.
- `ctid` là vị trí tuple vật lý, có thể thay đổi sau UPDATE/VACUUM FULL và row movement.
- `xmin` là metadata transaction của tuple version, không phải business ID ổn định.

Khi row movement xảy ra, đừng lưu `(tableoid,ctid)` làm khóa API vĩnh viễn. Dùng business identifier và ràng buộc hợp lý.

**Thực tế quan trọng:** nếu primary key vật lý là cặp `(event_date,event_id)` và event_date có thể đổi, hãy thiết kế cách tìm đối tượng ổn định ở tầng API; không mặc định `event_id` đã unique toàn partitioned table.

## 34. Query phải lọc theo khóa phân vùng để pruning có hiệu quả

Một query:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM partition_lab.sales_events
WHERE event_date >= DATE '2026-02-01'
  AND event_date < DATE '2026-03-01';
~~~

có cơ hội để PostgreSQL **prune** các partition không giao với khoảng Feb.

Ngược lại:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM partition_lab.sales_events
WHERE date_trunc('month', event_date) =
      timestamp '2026-02-01 00:00:00';
~~~

dùng biểu thức trên partition key, nên không thể mặc định planner nhận ra cùng điều kiện bounds và bỏ các partition không liên quan hiệu quả như predicate range trực tiếp.

### Routing khác pruning

- `INSERT` với ngày Feb cần route tới Feb.
- `UPDATE` đổi Jan → Feb cần route phiên bản mới tới Feb.
- `SELECT` chỉ đọc Feb cần prune Jan/Mar/DEFAULT khi điều kiện cho phép.

Tất cả cùng liên quan khóa phân vùng nhưng phục vụ mục tiêu khác nhau.

### Không cần truy vấn bảng con để “đúng partition”

Dùng query qua parent với predicate rõ ràng. Truy vấn trực tiếp child có thể hữu ích trong maintenance/diagnostics, nhưng khiến ứng dụng phụ thuộc cấu trúc partition thủ công.

## 35. EXPLAIN khi INSERT/UPDATE trên partitioned table

Với SELECT, dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, event_date, amount
FROM partition_lab.sales_events
WHERE event_date = DATE '2026-02-18';
~~~

Với UPDATE, có thể xem plan:

~~~sql
EXPLAIN
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-22'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;
~~~

`EXPLAIN` không có `ANALYZE` chỉ cho kế hoạch ước lượng và không thực thi UPDATE.

Nếu muốn đo thực tế:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-22'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001;

ROLLBACK;
~~~

`EXPLAIN ANALYZE` **thực thi câu UPDATE thật**, do đó chỉ thử với transaction rollback trong lab hoặc database disposable được kiểm soát.

Tùy chọn `WAL` có trong các phiên bản PostgreSQL hỗ trợ (PostgreSQL 13+). Tên node/chi tiết plan khác nhau theo phiên bản và planner; không bắt buộc kết quả phải giống một output chụp từ máy khác.

## 36. Chi phí của INSERT được định tuyến

Partitioning có lợi khi giúp quản lý dữ liệu theo vùng và query pruning, nhưng INSERT phải thực hiện thêm những việc:

1. Xác định partition key sau xử lý đầu vào.
2. Chọn đúng partition đích.
3. Kiểm tra partition bounds/constraint.
4. Ghi tuple vào heap của partition.
5. Duy trì các index trên partition phù hợp.
6. Ghi WAL và thực hiện trigger/FK/constraint liên quan.
7. Xử lý concurrency và commit.

Chi phí thực tế phụ thuộc số phân vùng, cấu trúc partition tree, số index, độ rộng hàng, key distribution, buffer cache và concurrency.

### Một INSERT nhiều hàng không phải 100 lệnh ghi vào 100 partition

PostgreSQL có thể thực thi một statement INSERT đa hàng và route từng tuple. Nó vẫn là một transaction/statement ở mức SQL, không phải ứng dụng tự phát 100 network round trips chỉ vì có 100 partition.

### Có quá nhiều partition sẽ ra sao?

Hàng nghìn partition không có quy tắc “luôn nhanh”. Có thể tăng:

- Chi phí planner/catalog/metadata.
- Thời gian startup/memory cho một số kế hoạch.
- Số object/index cần bảo trì.
- Chi phí DDL, autovacuum, backup/monitoring.
- Khả năng connection/workload chạm rất nhiều partition cùng lúc.

Chọn granularity (ngày/tuần/tháng) dựa trên volume, retention, query pattern, mức tải và vận hành, không chỉ vì tiện đặt tên.

## 37. Chi phí đặc biệt của UPDATE chuyển phân vùng

Khi một UPDATE chỉ thay `status` và giữ ngày trong Jan, đó thường là UPDATE tuple trong heap của Jan.

Khi UPDATE đổi ngày Jan → Feb, PostgreSQL phải xử lý row movement giữa hai quan hệ:

| Khía cạnh | UPDATE cùng partition | UPDATE chuyển partition |
| --- | --- | --- |
| Vị trí dữ liệu | Giữ trong cùng child | Chuyển source → destination |
| Cơ chế MVCC | Tuple version mới | Xóa ở source, chèn ở destination theo semantics |
| Index | Bảo trì theo cột bị thay đổi và HOT nếu đủ điều kiện | Index ở nguồn/đích và cleanup liên quan |
| Trigger | Thường theo luồng row UPDATE | Có thể kích hoạt row DELETE/INSERT tương ứng |
| WAL | Phụ thuộc số hàng/index/tuple | Có thể cao hơn vì ghi ở hai quan hệ |
| FK / constraints | Kiểm tra theo thay đổi | Có thể thêm kiểm tra vì đổi key/chuyển relation |
| Lock/concurrency | Row conflicts thông thường | Có thêm tình huống row movement `40001` |
| Vacuum | Phiên bản cũ cần dọn | Source có hàng xóa, destination có hàng mới |

Đây là so sánh khái niệm, không phải bảo đảm một UPDATE chuyển vùng luôn chậm hơn theo một hệ số cố định. Cần đo trên workload thật.

### Có nên thường xuyên sửa partition key không?

Nếu 30% sự kiện mỗi ngày bị thay đổi ngày sang tháng khác, phân vùng theo `event_date` có thể tạo write amplification lớn.

Cần xem lại:

- Partition key có thật sự ổn định không?
- Có thể phân vùng theo `ingested_at`/`created_at` không?
- Có thể sửa ngày logic ở một cột **khác** với khóa vật lý không?
- Query/retention có yêu cầu partitioning theo ngày nghiệp vụ không?
- Tính nhất quán của FK/global ID sẽ xử lý thế nào?

**Khóa phân vùng thường được chọn tốt khi phù hợp truy vấn và tương đối ổn định**. Không phải bất kỳ cột ngày nào cũng nên làm partition key.

## 38. Khi nào cần sửa event_date, khi nào không nên?

Những lý do hợp lệ để UPDATE partition key:

- Dữ liệu được nhập với ngày sai và đã được xác minh cần sửa.
- Một sự kiện có “ngày hiệu lực” được điều chỉnh theo quy tắc nghiệp vụ.
- Cần chuyển hàng từ DEFAULT về phân vùng thời gian chuẩn trong migration có kiểm soát.

Những tình huống không nên lạm dụng UPDATE partition key:

- Chỉ muốn xóa dữ liệu cũ theo retention.
- Muốn đổi tên partition hoặc thay layout storage.
- Muốn chuyển toàn bộ dữ liệu tháng 1 thành dữ liệu tháng 2 mà không có sự thay đổi ý nghĩa nghiệp vụ.
- Muốn “dồn” partition nhỏ vào partition lớn không qua kế hoạch dữ liệu.

Đối với retention theo tháng, **DETACH/DROP partition cũ** thường là chiến lược vận hành khác hẳn việc UPDATE hàng triệu event_date. Retention cần xóa hoặc archive partition cũ, không cần đổi lịch sử ngày nghiệp vụ.

## 39. Batch UPDATE khi có hàng triệu bản ghi

PostgreSQL không hỗ trợ cú pháp `UPDATE ... LIMIT n` trực tiếp như một số hệ quản trị khác.

Nếu phải chuyển một tập lớn hàng, có thể chọn **một batch khóa xác định** rồi UPDATE, ví dụ trong database lab:

~~~sql
BEGIN;

WITH picked AS (
    SELECT
        event_date AS old_date,
        event_id
    FROM partition_lab.sales_events
    WHERE event_date >= DATE '2026-01-01'
      AND event_date <  DATE '2026-02-01'
    ORDER BY event_date, event_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE partition_lab.sales_events AS e
SET
    event_date = e.event_date + 31,
    updated_at = clock_timestamp()
FROM picked AS p
WHERE e.event_date = p.old_date
  AND e.event_id = p.event_id
RETURNING
    e.event_id,
    e.event_date,
    e.tableoid::regclass AS physical_partition;

ROLLBACK;
~~~

Đây là **mẫu minh họa cú pháp**, không phải một hệ thống migration hoàn chỉnh.

Cần xác định thêm:

- Thứ tự batch và điều kiện kết thúc.
- Đồng thời với ingestion vào tháng cũ/mới.
- Nếu dùng `SKIP LOCKED`, những hàng bị khóa có được xét lại ở lượt sau không.
- Số hàng cập nhật/commit mỗi batch, lock timeout và WAL.
- Unique conflict ở partition đích.
- Trạng thái phục hồi nếu job chết giữa chừng.
- Idempotency của phép dịch ngày (cộng 31 ngày hai lần **không idempotent**).

### Không lặp phép cộng ngày vô điều kiện khi retry

~~~sql
SET event_date = event_date + 31
~~~

nếu chạy hai lần có thể làm hàng chuyển tiếp sang tháng khác thêm một lần. Một migration retry-safe nên có điều kiện xác nhận **ngày nguồn cụ thể** hoặc mapping `old_date → new_date` ổn định, cùng checkpoint và transaction phù hợp.

## 40. COPY và nhập dữ liệu hàng loạt

Với ingestion lớn, PostgreSQL hỗ trợ `COPY FROM` vào bảng phân vùng cha theo những điều kiện/cú pháp áp dụng cho partitioned tables trong phiên bản sử dụng. Hàng cũng cần được định tuyến tới partition đích thích hợp.

Ý tưởng:

~~~sql
-- Minh họa cú pháp; yêu cầu file thực tế và quyền phù hợp.
COPY partition_lab.sales_events (
    event_date, event_id, tenant_id, status, amount
)
FROM '/path/to/events.csv'
WITH (FORMAT csv, HEADER true);
~~~

Đường dẫn `/path/to/events.csv` chỉ là placeholder, **không chạy nguyên văn**. `COPY FROM 'file'` ở server cần quyền và file trên máy database server; `\copy` của psql là workflow khác dùng file ở phía client.

### Khi bulk load phải chuẩn bị gì?

1. Tạo đủ partition cho toàn bộ khoảng ngày sẽ nhập.
2. Nếu có DEFAULT, giám sát số hàng lọt vào đó.
3. Chuẩn hóa timezone/ngày trước khi copy.
4. Kiểm tra unique keys và dữ liệu tham chiếu.
5. Có chiến lược xử lý lỗi batch.
6. Xem tác động index/WAL/replica.
7. Dùng staging table khi cần validate/dedupe trước.
8. `ANALYZE` các bảng liên quan sau nạp lượng dữ liệu lớn khi phù hợp.

Không nên bỏ constraint hoặc tắt các cơ chế an toàn một cách tùy tiện chỉ để tăng tốc bulk load.

## 41. CREATE INDEX trên parent và các partition

Partitioned parent bản thân không chứa heap dữ liệu thông thường. Khi tạo index theo PostgreSQL declarative partitioning, hệ thống quản lý một **partitioned index** trên parent cùng các index tương ứng trên partition con theo cơ chế DDL hỗ trợ.

Ví dụ:

~~~sql
CREATE INDEX idx_sales_events_tenant_date
ON partition_lab.sales_events (
    tenant_id,
    event_date DESC,
    event_id
);
~~~

Index này có thể giúp:

~~~sql
SELECT event_id, event_date, amount
FROM partition_lab.sales_events
WHERE tenant_id = 1
  AND event_date >= DATE '2026-01-01'
  AND event_date < DATE '2026-02-01'
ORDER BY event_date DESC, event_id
LIMIT 20;
~~~

Không nhầm **partition routing** với **index lookup**:

- Router dùng `event_date` để tìm child.
- Index của child giúp tìm/đọc nhanh hơn **bên trong child** khi query pattern phù hợp.

Một INSERT vẫn cần route tới đúng child và duy trì các index tương ứng.

### Kiểm tra các index

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partition_lab'
  AND tablename LIKE 'sales_events%'
ORDER BY tablename, indexname;
~~~

Nếu đã tạo primary key ở parent, các partition cũng có cấu trúc hỗ trợ uniqueness theo cơ chế partitioned constraint/index. Không tự tạo thêm index trùng chức năng khi chưa kiểm tra.

## 42. Vì sao index không thay thế điều kiện phân vùng?

Một index trên `event_date` không cho phép bạn chèn ngày 15/02 vào partition Jan.

Ngược lại, partition pruning tốt không có nghĩa mọi truy vấn bên trong partition đều nhanh; một partition chứa 100 triệu rows vẫn có thể cần B-tree, BRIN hoặc loại index phù hợp.

Những câu hỏi riêng:

1. **Tôi có đủ partition để route dữ liệu ghi không?**
2. **Predicate của SELECT có giúp prune partition không?**
3. **Mỗi partition có index phù hợp các điều kiện truy vấn sau khi prune không?**
4. **Giá khi ghi một tuple vào child gồm bao nhiêu index?**

Giải quyết cả bốn tốt hơn việc chỉ tăng số partition.

## 43. Tác động đến logical replication và CDC

Các hệ thống downstream có thể nhận thay đổi từ PostgreSQL qua logical replication/CDC. Row movement vật lý là một yếu tố quan trọng khi thiết kế bản tin thay đổi.

Tùy PostgreSQL version, cấu hình publication và cơ chế connector, một UPDATE đổi partition có thể được biểu diễn/quan sát theo cách liên quan thao tác **DELETE ở source và INSERT ở destination**, hoặc được connector xử lý/ánh xạ thành sự kiện logic khác.

Vì vậy khi có Kafka/CDC/outbox:

- Xác nhận event type thực tế mà connector phát.
- Xác nhận business key có ổn định sau khi đổi ngày không.
- Không tự coi “DELETE+INSERT” là khách hàng thực sự hủy đơn rồi tạo đơn mới.
- Định nghĩa quy trình reconcile khi consumer thấy sự kiện out of order.
- Có idempotency cho việc xử lý lại event.
- Kiểm tra replica identity và khóa mà CDC dùng để nhận biết hàng trước/sau.

Không suy từ một sơ đồ MVCC rằng mọi phiên bản PostgreSQL/connector chắc chắn phát đúng cùng một chuỗi event ra bên ngoài. **Phải thử bằng stack replication đang dùng.**

## 44. Row movement và các tác động side effect

Một UPDATE chuyển partition có thể chạm:

- Row-level triggers trên nguồn/đích.
- Foreign key checks, bao gồm cascades nếu có.
- Audit logging.
- WAL và physical/logical replication.
- Chỉ mục của hai partition.
- Workload autovacuum.
- Các listener dựa vào CDC.
- Business caches dùng composite key.
- Những bảng giữ tham chiếu tới `(event_date,event_id)`.

Trong một ứng dụng, cần hỏi:

> Nếu sửa ngày của sự kiện, mọi nơi khác đang lưu tham chiếu tới nó có còn tìm đúng đối tượng không?

Nếu API chỉ sử dụng `event_id` còn database cho phép cùng ID xuất hiện ở nhiều ngày khác nhau, việc sửa ngày hoặc chuyển partition có thể làm một câu SELECT chỉ theo ID trở nên mơ hồ.

Không để thiết kế phân vùng phá vỡ **hợp đồng định danh nghiệp vụ**.

## 45. Date, timestamp và timezone khi partition theo thời gian

Lab dùng kiểu `date` để ranh giới rõ ràng. Với production, nhiều bảng dùng `timestamptz`.

Ví dụ:

~~~sql
PARTITION BY RANGE (occurred_at)
~~~

với các bound kiểu:

~~~sql
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO ('2026-02-01 00:00:00+00')
~~~

Thời điểm thực tế phải tính đến:

- Dữ liệu lưu là thời điểm UTC hay ngày nghiệp vụ địa phương?
- Sự kiện ở múi giờ khác nhau có dùng cùng ngày hiệu lực không?
- Chuyển đổi `timestamp without time zone` và `timestamptz` diễn ra ở đâu?
- Khi cắt tháng theo múi giờ có DST, thời điểm ranh giới có được quy đổi đúng không?
- Ứng dụng có vô tình gửi string không có timezone và phụ thuộc `TimeZone` của session không?

Nếu nghiệp vụ chia theo “ngày thanh toán ở Việt Nam”, hãy định nghĩa rõ cách chuyển timestamp thực sang ngày nghiệp vụ rồi mới route. Không mặc định “ngày UTC” và “ngày địa phương” là như nhau.

### Đừng đổi kiểu khóa phân vùng để chữa lỗi timezone một cách vội vàng

Việc đổi kiểu ngày có thể ảnh hưởng index, bounds, CHECK, query plans, replication và migration dữ liệu. Cần xác định **ngữ nghĩa thời gian** trước, rồi mới thiết kế partition key.

## 46. LIST và HASH có gì khác với RANGE?

### LIST

Ví dụ:

~~~sql
CREATE TABLE partition_lab.region_events (
    event_id bigint NOT NULL,
    region_code text NOT NULL,
    description text
) PARTITION BY LIST (region_code);

CREATE TABLE partition_lab.region_events_north
PARTITION OF partition_lab.region_events
FOR VALUES IN ('NORTH');

CREATE TABLE partition_lab.region_events_south
PARTITION OF partition_lab.region_events
FOR VALUES IN ('SOUTH');

CREATE TABLE partition_lab.region_events_default
PARTITION OF partition_lab.region_events
DEFAULT;
~~~

Một `INSERT` có `region_code = 'SOUTH'` được route đến child South. Nếu `UPDATE` đổi `region_code` thành NORTH qua parent, hàng có thể phải chuyển sang child North.

### HASH

Ví dụ cú pháp:

~~~sql
CREATE TABLE partition_lab.tenant_events (
    tenant_id integer NOT NULL,
    event_id bigint NOT NULL,
    payload text
) PARTITION BY HASH (tenant_id);

CREATE TABLE partition_lab.tenant_events_p0
PARTITION OF partition_lab.tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE partition_lab.tenant_events_p1
PARTITION OF partition_lab.tenant_events
FOR VALUES WITH (MODULUS 2, REMAINDER 1);
~~~

PostgreSQL route theo kết quả hash của partition key. Nếu UPDATE làm thay đổi tenant ID và hash phân vào partition khác, cũng là trường hợp cần xét row movement.

**Khác biệt:** partition DEFAULT được dùng cho `RANGE`/`LIST` theo cú pháp hỗ trợ; đừng giả định HASH có cơ chế DEFAULT giống hai kiểu đó.

### Dù RANGE/LIST/HASH, hãy giữ bất biến nghiệp vụ

Chỉ vì có thể UPDATE partition key không có nghĩa nên cho phép sửa `tenant_id` của một bản ghi mà không kiểm tra authorization và các FK/unique liên quan.

## 47. Quan sát cây phân vùng

PostgreSQL có các catalog và helper functions để khảo sát cấu trúc.

Với những phiên bản hỗ trợ `pg_partition_tree`:

~~~sql
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_relation,
    isleaf,
    level
FROM pg_partition_tree(
    'partition_lab.sales_events'::regclass
)
ORDER BY level, relation_name;
~~~

Nếu một version không hỗ trợ helper này, có thể xem catalog `pg_inherits` hoặc query metadata phù hợp.

Kiểm tra bounds thông qua `pg_class.relpartbound` có thể dùng hàm hiển thị expression:

~~~sql
SELECT
    c.oid::regclass AS partition_name,
    pg_get_expr(c.relpartbound, c.oid) AS partition_bound
FROM pg_class AS c
JOIN pg_inherits AS i
    ON i.inhrelid = c.oid
WHERE i.inhparent = 'partition_lab.sales_events'::regclass
ORDER BY c.oid::regclass::text;
~~~

Metadata giúp phát hiện:

- Có tạo đủ tháng chưa?
- Có partition DEFAULT không?
- Bounds liền mạch không?
- Có child sai tên hoặc bị quên không?
- Có bản phân vùng trung gian/subpartition không?

Không chỉ kiểm tra “table có tồn tại” mà cần xác nhận bounds đúng.

## 48. Giám sát dữ liệu đang nằm ở đâu

Thống kê số hàng theo partition thực:

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS logical_rows,
    MIN(event_date) AS oldest_date,
    MAX(event_date) AS newest_date
FROM partition_lab.sales_events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
~~~

Truy vấn này đọc dữ liệu thật và đếm theo partition. Trên hệ thống hàng tỷ hàng có thể tốn I/O; không chạy mỗi giây chỉ để monitor. Có thể dùng thống kê ước lượng theo catalog cho dashboard thường xuyên, kết hợp kiểm tra chính xác khi cần.

### So với pg_stat_user_tables

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_analyze
FROM pg_stat_user_tables
WHERE schemaname = 'partition_lab'
  AND relname LIKE 'sales_events%'
ORDER BY relname;
~~~

`n_live_tup`/`n_dead_tup` là ước lượng, không phải số hàng chính xác tuyệt đối. Khi một partition chịu nhiều row movement ra ngoài, `n_dead_tup` có thể tăng và cần được autovacuum/maintenance xử lý.

## 49. Khi nào cần tạo phân vùng mới?

Với chiến lược RANGE theo tháng, nên có quy trình:

1. Tạo trước các partition của tháng sắp tới.
2. Xác nhận bounds chính xác và không overlap.
3. Đảm bảo index/constraints/privileges/triggers áp dụng như mong muốn.
4. Kiểm tra migration có DEFAULT data liên quan không.
5. Test INSERT vào ngày đầu, ngày cuối và ngày cận biên của mỗi partition.
6. Giám sát lượng hàng vào DEFAULT.
7. Có cảnh báo trước khi hết khoảng ngày đã khai báo.
8. Có chiến lược retention/DETACH/ARCHIVE cho tháng cũ.
9. Xác nhận rollback plan cho DDL bị lỗi.
10. Không tự thay đổi bounds bằng script chạy khi bảng đang ghi mạnh mà chưa đánh giá lock.

### Ví dụ kiểm tra trước khi đến tháng mới

~~~sql
SELECT
    event_id,
    event_date,
    tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
WHERE event_date >= DATE '2026-04-01'
ORDER BY event_date, event_id;
~~~

Với seed ban đầu, có hàng tháng 4 trong DEFAULT. Đây là tín hiệu cần migration khi muốn thêm partition Apr, **không phải lý do xóa hàng DEFAULT vô điều kiện**.

## 50. Truyền dữ liệu phân vùng qua JDBC

Với Java/JDBC, ứng dụng nên INSERT qua bảng cha và truyền giá trị khóa phân vùng bằng kiểu SQL phù hợp.

Ví dụ Java:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

public record InsertedEvent(
    long eventId,
    LocalDate eventDate,
    String partitionName
) {}

public static InsertedEvent insertEvent(
        Connection connection,
        long eventId,
        LocalDate eventDate,
        int tenantId,
        BigDecimal amount
) throws SQLException {

    String sql = """
        INSERT INTO partition_lab.sales_events (
            event_date,
            event_id,
            tenant_id,
            amount
        )
        VALUES (?, ?, ?, ?)
        RETURNING
            event_id,
            event_date,
            tableoid::regclass::text AS partition_name
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {

        ps.setDate(1, Date.valueOf(eventDate));
        ps.setLong(2, eventId);
        ps.setInt(3, tenantId);
        ps.setBigDecimal(4, amount);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "INSERT did not return an event"
                );
            }

            return new InsertedEvent(
                rs.getLong("event_id"),
                rs.getDate("event_date").toLocalDate(),
                rs.getString("partition_name")
            );
        }
    }
}
~~~

Ví dụ truyền `LocalDate` vào cột `date`. pgJDBC còn có thể hỗ trợ `setObject` với các kiểu `java.time` tùy driver/version; chọn cách nhất quán với hệ thống đang dùng.

### Không gửi tên partition từ client như tên bảng SQL

Một anti-pattern:

~~~java
// Không nội suy tên partition tùy tiện từ input người dùng:
String sql = "INSERT INTO " + userSuppliedPartition + " ...";
~~~

Thao tác này vừa làm application phụ thuộc chi tiết lưu trữ, vừa mở rủi ro SQL injection nếu identifier không được kiểm soát đúng.

Dùng `INSERT INTO partition_lab.sales_events ...` và truyền **giá trị event_date như tham số**, để database quyết định đích.

## 51. JDBC: chuyển ngày và xử lý số hàng ảnh hưởng

~~~java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

public static boolean moveEventDate(
        Connection connection,
        long eventId,
        LocalDate oldDate,
        LocalDate newDate
) throws SQLException {

    String sql = """
        UPDATE partition_lab.sales_events
        SET
            event_date = ?,
            updated_at = clock_timestamp()
        WHERE event_date = ?
          AND event_id = ?
        RETURNING event_id
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setDate(1, Date.valueOf(newDate));
        ps.setDate(2, Date.valueOf(oldDate));
        ps.setLong(3, eventId);

        try (ResultSet rs = ps.executeQuery()) {
            return rs.next();
        }
    }
}
~~~

Giá trị trả về:

- `true`: câu UPDATE tìm thấy hàng và trả một hàng đã cập nhật.
- `false`: không có hàng khớp điều kiện; cần xem đó là stale oldDate, không tồn tại hay thiếu quyền.
- `SQLException`: có thể do thiếu partition, unique violation, FK, serialization failure, deadlock hoặc lỗi khác.

**Không tự đổi `oldDate` khi retry một cách tùy tiện.** Nếu người khác đã sửa ngày trước, ứng dụng có thể cần trả conflict để người dùng quyết định.

### Transaction ownership

Method repository không nên tự commit/rollback nếu transaction do service/framework quản lý. Một nghiệp vụ có nhiều câu SQL cần chúng nằm trong transaction do caller kiểm soát rõ ràng.

## 52. Phân loại lỗi cần xử lý

| Tình huống | Tín hiệu thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không có partition đích | Lỗi routing/partition constraint | Tạo partition hoặc từ chối/đưa staging theo chính sách |
| Direct INSERT sai bounds | Partition constraint violation | Sửa điểm ghi, dùng parent hoặc dữ liệu đúng bounds |
| Trùng composite PK ở đích | `23505` unique_violation | Kiểm tra business identity và xung đột thực |
| FK bị phá vỡ khi đổi khóa | `23503` foreign_key_violation | Rà tham chiếu và quy tắc ON UPDATE |
| Row movement concurrency | Có thể `40001` serialization_failure | Rollback và retry toàn transaction khi an toàn |
| Deadlock | `40P01` deadlock_detected | Rollback và retry có giới hạn |
| Không lấy được lock | `55P03` lock_not_available | Retry/backoff hoặc xử lý bận |
| WHERE không khớp | UPDATE trả 0 hàng | Kiểm tra stale state/old_date hoặc not found |
| Trigger lỗi | SQLException theo exception | Kiểm tra trigger, data và giao thức nghiệp vụ |

Không được gộp mọi `SQLException` thành một vòng retry vô hạn. Unique violation thường là xung đột dữ liệu cần xử lý, không phải sự cố tạm thời tự hết khi thử lại.

Với retry transaction, cần giới hạn số lần, backoff, logging và idempotency nếu nghiệp vụ đã tạo side effect ngoài PostgreSQL.

## 53. Những sai lầm phổ biến

### 53.1. Nghĩ INSERT vào parent lưu hàng ở parent heap

Partitioned parent thể hiện bảng logic; tuple được route vào partition con.

### 53.2. Nhầm routing với pruning

Routing chọn đích khi ghi; pruning giảm partition cần đọc.

### 53.3. Nghĩ cận TO được bao gồm

`FROM` bao gồm cận dưới, `TO` loại trừ cận trên đối với RANGE.

### 53.4. Ghi trực tiếp child rồi hy vọng PostgreSQL tự chuyển sang sibling

Direct INSERT vào partition không phải con đường chung để reroute dữ liệu sai bounds.

### 53.5. Không có partition tháng tới mà vẫn nhận INSERT

Nếu không có DEFAULT, có thể lỗi; nếu có DEFAULT, data có thể tích tụ sai vùng mong muốn.

### 53.6. Nghĩ DEFAULT tự chuyển hàng khi tạo partition mới

Thêm partition không tự migration các tuple đã lưu ở DEFAULT.

### 53.7. Nghĩ UPDATE partition key chỉ sửa một ô trong cùng heap

Nếu giá trị mới thuộc partition khác, PostgreSQL thực hiện row movement.

### 53.8. Nghĩ UPDATE chuyển vùng không ảnh hưởng trigger

Row movement có hành vi DELETE/INSERT mức hàng; audit/outbox có thể bị ảnh hưởng.

### 53.9. Nghĩ UPDATE row movement là hai transaction riêng

Nó vẫn thuộc transaction nguyên tử của câu SQL; không được commit nửa chừng.

### 53.10. Nghĩ UNIQUE(event_id) có thể khai báo trên parent phân vùng theo date

Ràng buộc unique trên partitioned parent phải bao gồm partition key theo quy tắc PostgreSQL.

### 53.11. Nghĩ PRIMARY KEY(event_date,event_id) bảo đảm event_id duy nhất toàn bảng

Hai ngày khác nhau vẫn cho phép cùng event_id theo composite key.

### 53.12. Dùng ON CONFLICT DO UPDATE để tự đổi partition của hàng xung đột

Nhánh upsert có giới hạn khi đổi partition key dẫn tới row movement; dùng UPDATE qua parent khi đúng nghiệp vụ.

### 53.13. Quên kiểm tra row movement concurrency

Một transaction khác đã chuyển hàng có thể khiến UPDATE/DELETE đồng thời gặp `40001` hoặc 0 hàng.

### 53.14. Retry chỉ statement cuối sau `40001`

Cần rollback và đánh giá lại toàn transaction cùng dữ liệu mới.

### 53.15. Dùng ctid/tableoid như khóa API lâu dài

Chúng là thông tin vật lý, thay đổi khi chuyển partition hoặc bảo trì.

### 53.16. Chuyển hàng triệu bản ghi bằng một transaction rất dài

Có thể gây WAL/lock/replica lag/VACUUM pressure; cần kế hoạch batch và recovery.

### 53.17. Cộng ngày nhiều lần khi retry migration

`SET event_date = event_date + 31` không idempotent; phải có mapping old→new và checkpoint.

### 53.18. Partition theo cột ngày thường xuyên bị thay đổi

Có thể tạo write amplification lớn; cân nhắc partition key ổn định hơn.

### 53.19. Không tính đến timezone và biên tháng

Một timestamp có thể thuộc tháng khác nếu tính theo UTC so với giờ nghiệp vụ địa phương.

### 53.20. Nghĩ index giải quyết việc thiếu partition

Index giúp tra cứu trong partition; không tự tạo đích cho routing.

### 53.21. Không giám sát DEFAULT

DEFAULT tăng âm thầm có thể che thiếu partition và làm maintenance khó hơn.

### 53.22. Test EXPLAIN ANALYZE UPDATE trên production như dry run

`ANALYZE` thực thi DML, có thể tạo tác động thật.

### 53.23. Dùng trigger tự thay partition key sau khi router đã chọn đích

BEFORE trigger có giới hạn khi làm hàng chuyển sang đích khác; thiết kế nguồn dữ liệu đúng partition key trước.

### 53.24. Bỏ qua FOREIGN KEY khi sửa composite PK

Đổi event_date có thể đổi khóa mà bảng con tham chiếu, dẫn đến constraint errors hoặc cascades.

### 53.25. Nghĩ partitioning tự tăng tốc mọi query

Query không lọc theo partition key có thể phải xét nhiều child, và index/plan vẫn cần tối ưu.

## 54. Bài tập thực hành có đáp án

Các bài dưới đây dựa trên `partition_lab` từ mục 4. Khi ví dụ có DML, dùng `BEGIN ... ROLLBACK` để giữ dataset. Những lệnh **cố ý lỗi** cần chạy riêng hoặc rollback ngay sau lỗi.

### Bài 1. Xác định partition của ngày đầu tháng

**Câu hỏi:** `event_date = 2026-02-01` được route vào Jan hay Feb?

**Đáp án:** Feb. Bound Jan là `[2026-01-01,2026-02-01)` nên không bao gồm ngày 01/02.

### Bài 2. Xác định partition của ngày cuối tháng

**Câu hỏi:** Ngày `2026-01-31` nằm ở đâu?

**Đáp án:** `sales_events_2026_01`.

### Bài 3. Quan sát tableoid

~~~sql
SELECT event_id, event_date,
       tableoid::regclass AS physical_partition
FROM partition_lab.sales_events
ORDER BY event_id;
~~~

**Đáp án:** 1001/1002 thuộc Jan; 1003/1004 Feb; 1005/1006 Mar; 1007 DEFAULT.

### Bài 4. INSERT nhiều tháng trong cùng statement

~~~sql
BEGIN;

INSERT INTO partition_lab.sales_events (
    event_date, event_id, tenant_id, amount
)
VALUES
    ('2026-01-10', 7001, 1, 10),
    ('2026-02-10', 7002, 1, 20),
    ('2026-03-10', 7003, 1, 30)
RETURNING event_id, tableoid::regclass;

ROLLBACK;
~~~

**Đáp án:** Ba hàng được route tới Jan, Feb, Mar tương ứng.

### Bài 5. UPDATE không chuyển partition

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET status = 'paid'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING tableoid::regclass;

ROLLBACK;
~~~

**Đáp án:** Vẫn là partition Jan vì khóa ngày không đổi.

### Bài 6. UPDATE khóa nhưng vẫn trong Jan

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-01-20'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_date, tableoid::regclass;

ROLLBACK;
~~~

**Đáp án:** Hàng vẫn ở Jan vì 20/01 thuộc bounds của Jan.

### Bài 7. UPDATE chuyển sang Feb

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = DATE '2026-02-20'
WHERE event_date = DATE '2026-01-05'
  AND event_id = 1001
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

**Đáp án:** Trong transaction hàng 1001 nằm ở Feb, sau rollback trở lại Jan.

### Bài 8. UPDATE ngày sang tháng 4

**Câu hỏi:** Nếu chuyển `event_id 1001` sang `2026-04-10` thì đích nào?

**Đáp án:** `sales_events_default`, vì lab chỉ khai báo Jan–Mar và DEFAULT.

### Bài 9. Thiếu DEFAULT

**Câu hỏi:** Bảng `missing_destination_demo` chỉ có Jan; INSERT Feb thành công không?

**Đáp án:** Không. Không có partition phù hợp, PostgreSQL báo lỗi routing.

### Bài 10. Direct child INSERT sai bounds

~~~sql
INSERT INTO partition_lab.sales_events_2026_02 (
    event_date, event_id, tenant_id, amount
)
VALUES ('2026-03-01', 7101, 1, 15.00);
~~~

**Đáp án:** Không hợp lệ vì row nằm ngoài bounds Feb. Ghi qua parent mới là cách PostgreSQL route đến Mar.

### Bài 11. Composite primary key cấm gì?

**Câu hỏi:** Hai hàng `(2026-01-05,9001)` và `(2026-02-05,9001)` có vi phạm `PRIMARY KEY(event_date,event_id)` không?

**Đáp án:** Không, vì cặp khóa khác nhau. Muốn bảo đảm event_id duy nhất toàn cục cần thiết kế khác.

### Bài 12. Một UPDATE có thể đi nhiều đích không?

~~~sql
BEGIN;

UPDATE partition_lab.sales_events
SET event_date = event_date + 31
WHERE event_date >= DATE '2026-01-01'
  AND event_date < DATE '2026-02-01'
RETURNING event_id, event_date, tableoid::regclass;

ROLLBACK;
~~~

**Đáp án:** Có. Với seed, 1001 sang Feb còn 1002 sang Mar.

### Bài 13. ON CONFLICT với composite key

**Câu hỏi:** INSERT `(2026-02-05,1001)` có conflict với `(2026-01-05,1001)` không?

**Đáp án:** Không, vì partition key date là một phần của composite PK.

### Bài 14. ON CONFLICT DO UPDATE di chuyển partition?

**Đáp án:** Không dùng nhánh `ON CONFLICT DO UPDATE` để đổi khóa hàng xung đột sang partition khác; đường UPDATE qua parent phù hợp hơn theo cơ chế hỗ trợ.

### Bài 15. AFTER ROW trigger quan sát gì?

**Câu hỏi:** UPDATE một hàng Jan → Feb có thể tạo entry nào trong log trigger AFTER INSERT/DELETE?

**Đáp án:** Một row DELETE ở nguồn Jan và một row INSERT ở đích Feb theo row movement semantics. Đây là lý do không tự xem cả hai entry là hai hành động nghiệp vụ độc lập.

### Bài 16. WHERE old_date quan trọng thế nào?

**Đáp án:** Điều kiện `event_date = old_date AND event_id = ...` giúp phát hiện trạng thái đã đổi. Khi transaction khác chuyển hàng, UPDATE có thể trả 0 hàng hoặc gặp concurrency error; ứng dụng phải xử lý không đoán mò.

### Bài 17. SQLSTATE khi concurrent row movement

**Câu hỏi:** Lỗi `40001` yêu cầu gì?

**Đáp án:** Rollback rồi retry **toàn transaction** khi được phép, đọc lại khóa phân vùng và các quyết định nghiệp vụ. Không chỉ lặp UPDATE cũ vô điều kiện.

### Bài 18. Vì sao không UPDATE hàng triệu dòng trong một transaction?

**Đáp án:** Row movement tạo DELETE+INSERT, gây lock/WAL/index/FK/trigger, có thể tạo transaction dài, bloat và replication lag. Cần batch/checkpoint và giám sát.

### Bài 19. Vì sao DEFAULT phải được giám sát?

**Đáp án:** Nếu nhiều dữ liệu đổ vào DEFAULT vì thiếu partition, sau này tạo partition tường minh khó hơn và query/maintenance có thể xấu. DEFAULT không tự repartition dữ liệu cũ.

### Bài 20. Lọc Feb sao cho pruning hiệu quả?

~~~sql
SELECT *
FROM partition_lab.sales_events
WHERE event_date >= DATE '2026-02-01'
  AND event_date < DATE '2026-03-01';
~~~

**Đáp án:** Predicate range trực tiếp trên partition key giúp planner/executor dễ xác định các child không cần đọc.

### Bài 21. Index có thay thế partition routing không?

**Đáp án:** Không. Index được dùng tìm/duy trì dữ liệu trong partition; routing chọn đích dựa partition bounds.

### Bài 22. Khi nào dùng bảng registry?

**Đáp án:** Khi cần bảo đảm event_id duy nhất toàn hệ thống dù dữ liệu range-partitioned theo event_date mà composite PK chỉ duy nhất theo cặp. Registry có unique PK và phải được sử dụng cùng transaction/giao thức nhất quán.

### Bài 23. Chuyển partition có phải hai transaction độc lập?

**Đáp án:** Không. Một câu UPDATE làm row movement được thực hiện trong transaction SQL hiện tại, với atomicity cho thay đổi database.

### Bài 24. Timezone ảnh hưởng partition theo timestamp thế nào?

**Đáp án:** Một thời điểm UTC có thể rơi vào ngày/tháng địa phương khác. Cần quy định timezone/ngày nghiệp vụ, kiểu `timestamptz` và bounds rõ ràng trước khi thiết kế.

### Bài 25. Phân biệt LIST/HASH/RANGE

**Đáp án:** RANGE chọn child theo khoảng, LIST theo giá trị liệt kê, HASH theo hash của khóa. Mỗi loại vẫn có partition routing; DEFAULT áp dụng theo quy tắc RANGE/LIST, không mặc định có ở HASH.

### Bài 26. Có nên dùng tableoid làm public ID?

**Đáp án:** Không. `tableoid` là định danh relation vật lý, có thể thay đổi khi row movement/maintenance; business ID cần cơ chế định danh ổn định riêng.

## 55. Checklist trước khi đưa vào production

1. **Xác định partition key** theo truy vấn, retention và mức độ ổn định giá trị.
2. **Định nghĩa chính xác bounds**, đặc biệt cận trên loại trừ và timezone.
3. **Có đủ partition tương lai** để tránh lỗi ghi bất ngờ.
4. **Xác định rõ có DEFAULT hay không**, cùng cảnh báo khi DEFAULT nhận hàng.
5. **Dùng parent làm điểm ghi chính**, tránh hard-code child trong API.
6. **Kiểm tra routing ở ngày đầu/cuối mỗi partition**, kể cả leap day và mốc timezone phù hợp.
7. **Test INSERT nhiều hàng** rải trên nhiều partition.
8. **Test UPDATE khóa trong cùng partition** và **UPDATE chuyển partition**.
9. **Đọc RETURNING/tableoid** trong lab để xác minh đích.
10. **Kiểm tra uniqueness của parent**: các cột partition key phải nằm trong PK/UNIQUE theo quy tắc.
11. **Thiết kế business ID toàn cục** nếu composite PK theo date không đủ.
12. **Không dựa vào ON CONFLICT DO UPDATE** để chuyển hàng xung đột qua partition.
13. **Kiểm thử row triggers** để tránh phát side effect nghiệp vụ sai.
14. **Đánh giá FK/ON UPDATE** khi partition key là một phần khóa tham chiếu.
15. **Kiểm thử concurrency** và xử lý `40001` bằng retry transaction.
16. **Lập kế hoạch batch** khi sửa ngày của nhiều hàng.
17. **Tránh phép chuyển ngày không idempotent** khi migration có thể retry.
18. **Đo WAL/index/lock/vacuum/replica lag** của row movement lớn.
19. **Đảm bảo query pruning** với predicate trên partition key.
20. **Lập lịch CREATE/ATTACH/DETACH partition** với đánh giá locking và dữ liệu DEFAULT.
21. **Quan sát theo child**: số hàng, dead tuples, thống kê và index size.
22. **Đảm bảo JDBC/ORM dùng tham số ngày đúng kiểu** và transaction boundary rõ ràng.
23. **Không dùng tableoid/ctid/xmin như khóa nghiệp vụ ổn định**.
24. **Có runbook** cho thiếu partition, lỗi routing, unique conflict, 40001 và dữ liệu DEFAULT.
25. **Đánh giá hành vi với CDC/replication** nếu consumer phân biệt DELETE/INSERT với UPDATE.

## 56. Tài liệu PostgreSQL chính thức

Khi triển khai, hãy đọc tài liệu đúng **major version PostgreSQL đang chạy**, vì declarative partitioning và khả năng chuyển hàng đã phát triển qua các phiên bản:

- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — declarative partitioning, bounds, routing, pruning và giới hạn.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — INSERT vào partitioned table, RETURNING và ON CONFLICT.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — UPDATE thay đổi partition key, row movement và concurrency.
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html) — PARTITION BY, PARTITION OF, DEFAULT, FROM/TO và constraints.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — ATTACH/DETACH PARTITION và các tác động DDL.
- [Triggers](https://www.postgresql.org/docs/current/trigger-definition.html) — trigger execution, thay đổi giữa các partition và các mức trigger.
- [Partitioning and Constraint Limitations](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE-LIMITATIONS) — những giới hạn PK/UNIQUE và đặc điểm partitioned indexes.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — snapshot, concurrency và lỗi serialization.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row/table locks và deadlock.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — xem plan và lưu ý ANALYZE chạy DML thật.
- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — tableoid/ctid/xmin.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dọn tuple sau UPDATE/DELETE.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html) — 23505, 23503, 40001 và các lỗi cần phân loại.

`/current/` dẫn đến trang tài liệu hiện hành; với hệ thống có phiên bản PostgreSQL cụ thể, chọn tài liệu **đúng version** trước khi dùng một tính năng/giới hạn trong migration.

## 57. Tổng kết

Định tuyến INSERT và UPDATE thay đổi khóa phân vùng là cơ chế nền tảng của declarative partitioning trong PostgreSQL.

Những nguyên tắc quan trọng nhất:

1. **INSERT vào bảng cha được route theo giá trị partition key của từng hàng.** RANGE có cận dưới bao gồm và cận trên loại trừ; DEFAULT chỉ nhận giá trị không khớp partition tường minh.
2. **Không có partition đích phù hợp thì ghi có thể lỗi.** Có DEFAULT thì dữ liệu đi vào DEFAULT, nhưng không tự chuyển sang partition mới khi DDL được tạo về sau.
3. **UPDATE đổi khóa trong cùng bounds không cần chuyển child.** Nếu giá trị mới thuộc child khác, PostgreSQL hỗ trợ **row movement**, có bản chất DELETE ở nguồn và INSERT ở đích trong cùng transaction.
4. **Row movement có tác động thực tế** lên row triggers, constraints, indexes, WAL, vacuum, replication và concurrency. Không được xem nó như sửa metadata đơn giản.
5. **PK/UNIQUE trên parent có giới hạn theo partition key.** Composite PK theo date không tự bảo đảm event_id duy nhất giữa mọi partition.
6. **ON CONFLICT DO UPDATE không phải cách tổng quát để chuyển hàng đang xung đột sang partition khác.** Dùng UPDATE qua parent khi đúng nghiệp vụ.
7. **Concurrent UPDATE/DELETE và row movement có thể tạo `40001`.** Cần rollback/retry toàn transaction khi an toàn, kiểm tra lại ngày nguồn và định danh hàng.
8. **Partitioning không miễn phí.** Chọn khóa ổn định, tạo trước bounds tương lai, giám sát DEFAULT, tổ chức batch và đo tác động của row movement lớn.

Khi hiểu đúng cách PostgreSQL **định tuyến hàng lúc INSERT và tìm lại phân vùng đích khi UPDATE thay đổi khóa**, bạn có thể thiết kế bảng phân vùng mà vẫn bảo vệ tính đúng của dữ liệu, tránh các lỗi concurrency khó tái hiện và quản lý dữ liệu theo thời gian một cách có kiểm soát.
