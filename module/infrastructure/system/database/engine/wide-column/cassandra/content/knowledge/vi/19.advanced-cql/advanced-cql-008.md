# Điều kiện tạo, cập nhật và giới hạn Materialized View theo phiên bản trong Apache Cassandra

> **Chương:** CQL nâng cao  
> **Phạm vi:** Materialized View (MV) của **Apache Cassandra**, tập trung cú pháp CQL, yêu cầu về khóa chính và WHERE, cơ chế đồng bộ từ bảng gốc, giới hạn an toàn và khác biệt giữa các dòng phiên bản. Các ví dụ dùng cấu trúc phù hợp Apache Cassandra 4.1/5.0 trong **lab được cho phép dùng MV**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **base table** và **materialized view**, hiểu vì sao view là một bản lưu vật lý có khóa chính khác, thay vì chỉ là câu SELECT được lưu.
2. Kiểm tra điều kiện hợp lệ của câu `CREATE MATERIALIZED VIEW`: `SELECT`, `WHERE`, `PRIMARY KEY`, keyspace và thuộc tính bảng.
3. Mô tả chính xác tác động của `INSERT`, `UPDATE`, `DELETE` và TTL lên dữ liệu của view; biết những gì **không được ghi trực tiếp** lên MV.
4. Giải thích giới hạn nhất quán của cập nhật base → view, quá trình build dữ liệu cũ và công cụ `nodetool viewbuildstatus`.
5. Đọc đúng thông điệp **experimental**, cấu hình bật/tắt và hạn chế theo phiên bản Cassandra 3.x, 4.0, 4.1, 5.0.
6. Thực hành một vòng đời MV bằng CQL và chọn phương án mô hình dữ liệu phù hợp cho ứng dụng Java.

## 2. Materialized View giải quyết bài toán gì?

Cassandra là cơ sở dữ liệu wide-column phân tán, tối ưu cho truy vấn có **partition key** phù hợp. Nếu bảng chính lưu đơn hàng theo `tenant_id` và `order_id`, tìm theo `customer_id` sẽ không có đường truy cập khóa phân vùng giống bảng gốc.

Materialized view (MV) cho phép tạo **một bảng dữ liệu được duy trì tự động** từ một base table, có thể sắp lại partition key và clustering key để phục vụ mẫu truy vấn khác.

~~~text
             Ứng dụng ghi base table
                       |
                       v
  orders  PRIMARY KEY ((tenant_id), order_id)
                       |
                 cập nhật MV
                       v
  orders_by_customer
  PRIMARY KEY ((customer_id), tenant_id, order_id)

Đọc theo tenant_id            Đọc theo customer_id
    -> orders                  -> orders_by_customer
~~~

**Khác nhau với CQL SELECT trực tiếp:** MV lưu dữ liệu thực sự, tạo SSTable và có replication/compaction như một bảng nội bộ. MV không tính lại SELECT tại thời điểm đọc. Vì vậy, mỗi view làm tăng **dung lượng lưu trữ và chi phí ghi**, đồng thời cần thời gian để cập nhật khi base table thay đổi.

### MV so với các lựa chọn khác

| Cách tiếp cận | Ai duy trì dữ liệu phụ? | Phù hợp khi | Giới hạn chính |
|---|---|---|---|
| Bảng denormalized do ứng dụng quản lý | Ứng dụng hoặc consumer/CDC | Cần kiểm soát lifecycle, retry, backfill, kiểm tra sai lệch | Phải tự thiết kế idempotency và đối soát |
| Materialized view | Cassandra tự sinh mutation cho view | Nghiên cứu hoặc hệ thống đã chấp nhận rủi ro MV của đúng phiên bản | Experimental; giới hạn khóa/WHERE; có độ trễ và nguy cơ lệch base-view |
| SAI (Cassandra 5.0+) | Cassandra duy trì secondary index gắn storage | Bộ lọc linh hoạt trên cột không phải partition key | Không đồng nghĩa có bảng vật lý với partition key tùy ý |
| Truy vấn base theo partition key | Không cần bản dữ liệu phụ | Đường truy cập chủ đạo đã biết partition | Không phục vụ mọi kiểu tra cứu ngược |

> **Trạng thái sản phẩm:** Tài liệu cấu hình chính thức của Apache Cassandra 4.1 và 5.0 xếp MV vào tính năng **experimental**, **không khuyến nghị production**; `materialized_views_enabled` mặc định là `false`. Việc CQL có lệnh MV không có nghĩa cụm Cassandra đang bật hoặc đủ an toàn để sử dụng. Phần thực hành dưới đây dành cho cluster lab.

## 3. Thiết kế bảng gốc cho ví dụ xuyên suốt

Trong lab một node (RF=1), tạo keyspace và bảng:

~~~sql
CREATE KEYSPACE IF NOT EXISTS mv_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS mv_lab.orders (
    tenant_id text,
    order_id uuid,
    customer_id text,
    amount int,
    state text,
    PRIMARY KEY ((tenant_id), order_id)
);
~~~

Ở bảng `orders`, một hàng được xác định bằng cặp khóa `(tenant_id, order_id)`, trong đó `tenant_id` là partition key. Cần truy vấn thứ hai: “Tìm đơn hàng của `customer_id`, không biết trước `tenant_id`”.

MV tương ứng:

~~~sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_lab.orders_by_customer AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id)
    WITH comment = 'Lab: tra cuu don hang theo customer';
~~~

Quy tắc then chốt ở ví dụ:

- View dùng **cùng keyspace** `mv_lab` với base table.
- Tất cả khóa của base (`tenant_id`, `order_id`) **vẫn nằm trong PRIMARY KEY của view**, dù thứ tự thay đổi.
- View thêm **đúng một cột không thuộc primary key của base** (`customer_id`) vào khóa chính; ở đây dùng làm partition key mới.
- `WHERE` bảo đảm **mọi thành phần primary key của view đều không NULL**.
- `SELECT` chỉ chứa các cột base, bao gồm đủ khóa cần thiết.

Câu SELECT dùng sau khi view đã xây dựng và hội tụ:

~~~sql
SELECT tenant_id, order_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';
~~~

Không cần `ALLOW FILTERING` vì đã cung cấp partition key của **view**. Tuy nhiên, nếu một `customer_id` có quá nhiều đơn hàng, partition trong view cũng có thể trở nên lớn. Thiết kế MV không miễn trừ quy tắc tránh partition nóng và partition quá lớn.

## 4. Checklist hợp lệ của CREATE MATERIALIZED VIEW

### 4.1. Điều kiện với SELECT

Phần `SELECT` trong định nghĩa view có các hạn chế do Cassandra áp dụng:

- Chỉ được chọn **các cột có sẵn của base table**. Không dùng phép tính, aggregate, function, casting, literal hay alias kiểu `SELECT amount * 2 AS total`.
- Có thể dùng `SELECT *` **nếu không có static column** trong base table. **Static columns không được đưa vào MV**, vì vậy `SELECT *` sẽ không hợp lệ khi base có static column.
- Không dùng `ORDER BY`, `LIMIT` hoặc `ALLOW FILTERING` trong câu SELECT **định nghĩa** view.
- Không thể tạo view từ join hoặc kết quả một subquery; nguồn là một base table.

Ví dụ không hợp lệ:

~~~sql
-- KHÔNG HỢP LỆ: biểu thức được tính toán và alias trong SELECT.
CREATE MATERIALIZED VIEW mv_lab.orders_by_total AS
    SELECT tenant_id, order_id, customer_id, amount * 2 AS doubled
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id);
~~~

**Lưu ý:** Khi `SELECT` bỏ bớt cột không phải khóa, việc xóa một cột **không được chọn vào view** tại base có thể phát sinh vấn đề nhất quán trong một số phiên bản/tình huống repair hoặc hints (vấn đề CASSANDRA-13826). Phần 9 giải thích vì sao thiết kế này cần đặc biệt thận trọng.

### 4.2. Điều kiện với PRIMARY KEY

Mọi view phải có PRIMARY KEY thỏa các nguyên tắc:

1. Chứa **toàn bộ** thành phần PRIMARY KEY của base table, gồm partition key và clustering columns.
2. Chỉ được thêm **tối đa một cột không thuộc PRIMARY KEY của base** vào PRIMARY KEY của view, theo giới hạn chính thức của Apache Cassandra 5.0.
3. Có thể **đổi thứ tự và vai trò partition/clustering** của các thành phần được phép, để tạo đường truy cập mới.
4. Các cột được đưa vào khóa chính của view phải thuộc tập các cột được SELECT và không có giá trị NULL trong hàng được đưa vào view.

**Ví dụ hợp lệ** với base `PRIMARY KEY ((tenant_id), order_id)`:

~~~sql
-- Khóa của view sử dụng hai cột base và thêm customer_id.
PRIMARY KEY ((customer_id), tenant_id, order_id)

-- Chỉ đảo khóa base, không thêm cột mới.
PRIMARY KEY ((order_id), tenant_id)
~~~

**Ví dụ không hợp lệ:**

~~~sql
-- Sai: bỏ thiếu order_id, một khóa của base.
PRIMARY KEY ((customer_id), tenant_id)

-- Sai: thêm hai cột không thuộc khóa base vào khóa view.
PRIMARY KEY ((customer_id, state), tenant_id, order_id)
~~~

Không nên suy diễn quy tắc này từ tài liệu của bản phân phối Cassandra do nhà cung cấp khác tùy biến. Cần kiểm tra đúng **Apache Cassandra** và đúng version mình vận hành.

### 4.3. Điều kiện với WHERE

`WHERE` trong định nghĩa MV có luật khác WHERE của một SELECT thông thường:

- Phải bảo đảm các cột trong **view PRIMARY KEY** không NULL. Cách dễ review nhất là viết rõ `col IS NOT NULL` cho **tất cả** cột khóa view.
- Cột **không thuộc base PRIMARY KEY** chỉ được ràng buộc bằng `IS NOT NULL`; không dùng điều kiện giá trị như `state = 'PAID'` hoặc `amount > 100` để tạo MV lọc theo giá trị thông thường.
- Với cột thuộc **base PRIMARY KEY**, một số điều kiện khác `IS NOT NULL` có thể được CQL cho phép theo quy tắc MV của phiên bản, nhưng vẫn phải hợp lệ và không làm mất yêu cầu non-null. Trong bài này dùng toàn bộ `IS NOT NULL` để dễ kiểm chứng.
- Không có **bind marker** `?` trong phần định nghĩa, vì đây là schema DDL cố định, không phải prepared SELECT tham số hóa.
- Không có `ALLOW FILTERING` để bỏ qua giới hạn cú pháp.

~~~sql
-- KHÔNG HỢP LỆ: state không là thành phần khóa của base,
-- nên WHERE state = 'PAID' không được hỗ trợ cho MV như ví dụ này.
CREATE MATERIALIZED VIEW mv_lab.orders_paid_mv AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
      AND state = 'PAID'
    PRIMARY KEY ((customer_id), tenant_id, order_id);

-- KHÔNG HỢP LỆ: view PK chứa customer_id nhưng thiếu
-- điều kiện bảo đảm customer_id IS NOT NULL.
CREATE MATERIALIZED VIEW mv_lab.orders_bad_null AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id);
~~~

### 4.4. Điều kiện keyspace và thuộc tính

MV phải thuộc **cùng keyspace** với base table. MV được thực hiện nội bộ như một bảng, vì vậy có thể chỉ định một số **table options** (`WITH comment`, compaction/caching và những tùy chọn hợp lệ với phiên bản). Không suy đoán rằng mọi table option của base đều có thể sao chép sang view, hoặc view tự kế thừa toàn bộ tùy chọn base.

`IF NOT EXISTS` chỉ tránh lỗi khi **view cùng tên đã tồn tại**; nó **không** so sánh và nâng cấp định nghĩa cũ. Nếu tên đã có nhưng WHERE/PRIMARY KEY/SELECT khác ý định, lệnh vẫn có thể bỏ qua trong khi schema không đúng.

## 5. MV được duy trì như thế nào khi base thay đổi?

Materialized view **không phải view logic thực hiện lại SELECT mỗi lần đọc**. Base table tạo các view mutations tương ứng, và chúng cần được chuyển tới các replica phụ trách partition của view. Do partition key của view có thể khác partition key base, **tập replica lưu base và view có thể khác nhau**.

~~~text
Ứng dụng
   |
   | INSERT/UPDATE/DELETE vào orders
   v
Coordinator base
   |
   v
Replica của orders (theo tenant_id)
   |
   | Xét trạng thái hàng và view PK cần tạo/thay thế
   v
Mutation của orders_by_customer
   |
   v
Replica của view (theo customer_id)
   |
   v
Đọc SELECT từ view khi view mutation đã có hiệu lực
~~~

**Cập nhật view có tính bất đồng bộ** so với thành công của write tại base table. Một lệnh INSERT thành công với consistency level của base **không bảo đảm** SELECT ngay lập tức trên view đã thấy dữ liệu. Nếu base/view gặp lỗi node, network, hoặc mất một số mutation, view có thể trễ hoặc sai lệch và cần điều tra chuyên sâu.

### 5.1. INSERT: hàng chỉ vào view khi đủ khóa

~~~sql
INSERT INTO mv_lab.orders
    (tenant_id, order_id, customer_id, amount, state)
VALUES (
    'tenant-1',
    11111111-1111-1111-1111-111111111111,
    'customer-A', 150, 'NEW'
);

INSERT INTO mv_lab.orders
    (tenant_id, order_id, amount, state)
VALUES (
    'tenant-1',
    22222222-2222-2222-2222-222222222222,
    250, 'NEW'
);
~~~

Hàng `1111...` có `customer_id` không NULL nên đủ điều kiện đi vào MV. Hàng `2222...` **không có customer_id** nên **không nằm trong view**, dù vẫn tồn tại trong base.

~~~sql
SELECT * FROM mv_lab.orders
WHERE tenant_id = 'tenant-1';

SELECT * FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';
~~~

Thực hành nên kiểm tra view sau khi **initial build đã hoàn tất** và sau khi có thời gian cho view mutation được lan truyền. Không dùng việc một lần SELECT chưa thấy hàng như bằng chứng có thể xóa bản ghi base.

### 5.2. UPDATE cột thường: view giữ khóa, cập nhật giá trị

~~~sql
UPDATE mv_lab.orders
SET state = 'PAID', amount = 175
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`state` và `amount` là giá trị được SELECT vào view nhưng **không** nằm trong view PRIMARY KEY. Vì vậy cùng khóa `(customer-A, tenant-1, order_id)` sẽ phản ánh giá trị mới khi view mutation đã đến và có hiệu lực. Truy vấn base và view trong khoảng chuyển tiếp có thể thấy các phiên bản khác nhau.

### 5.3. UPDATE cột tham gia view PRIMARY KEY: hàng đổi vị trí

~~~sql
UPDATE mv_lab.orders
SET customer_id = 'customer-B'
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Base primary key giữ nguyên, nhưng **view partition key đổi**:

~~~text
Trước: orders_by_customer(customer-A, tenant-1, 1111...) -> hàng

UPDATE base customer_id = customer-B
    |
    +-> xóa/che khuất bản sao view theo khóa cũ customer-A
    +-> tạo bản sao view theo khóa mới customer-B

Sau khi hội tụ:
  customer-A -> không còn đơn 1111...
  customer-B -> có đơn 1111...
~~~

Vì đây là **hai khóa view khác nhau**, không được kỳ vọng chuyển dịch nguyên tử đối với mọi client đọc view. Trong thời gian lan truyền có thể xảy ra khoảng trễ, thiếu hàng tạm thời hoặc dữ liệu cũ còn được nhìn thấy. Với nghiệp vụ yêu cầu duy nhất và tức thời, cần thiết kế một cơ chế nhất quán được kiểm chứng riêng.

### 5.4. UPDATE thành NULL, DELETE, TTL

Nếu đặt cột thêm vào khóa view thành NULL, hàng không còn thỏa điều kiện WHERE của MV và cần được xóa khỏi view:

~~~sql
UPDATE mv_lab.orders
SET customer_id = null
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Đây là xóa giá trị cột bằng tombstone trong base; không phải thay đổi `tenant_id` hay `order_id`. Khi xóa **toàn bộ hàng base** bằng DELETE, các hàng tương ứng trong view cũng cần bị xóa:

~~~sql
DELETE FROM mv_lab.orders
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Với TTL, các giá trị base hết hạn theo quy tắc TTL/tombstone; view cũng phải phản ánh việc dữ liệu không còn hợp lệ. **Đừng cho rằng các mutation TTL khác nhau hoặc tổ hợp UPDATE/DELETE ở mọi version tạo ra thời điểm hết hạn của base và MV trùng tuyệt đối.** Các lỗi lịch sử về row liveness và repair là một lý do MV vẫn bị coi là experimental.

### 5.5. Không thể ghi trực tiếp vào MV

~~~sql
-- KHÔNG HỢP LỆ: view là đối tượng chỉ đọc từ phía CQL.
INSERT INTO mv_lab.orders_by_customer
    (customer_id, tenant_id, order_id, amount, state)
VALUES ('customer-C', 'tenant-1',
        33333333-3333-3333-3333-333333333333, 500, 'NEW');

-- KHÔNG HỢP LỆ: không cập nhật dữ liệu view trực tiếp.
UPDATE mv_lab.orders_by_customer
SET amount = 500
WHERE customer_id = 'customer-A'
  AND tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Ứng dụng phải thực hiện thay đổi dữ liệu qua **base table**. Mọi truy vấn SELECT lên MV là độc lập với việc application đã write đến base ở consistency level nào.

## 6. CREATE VIEW với dữ liệu đã tồn tại: initial build

MV có thể được tạo **sau khi base đã có dữ liệu**. Cassandra phải **đọc dữ liệu lịch sử để build** trạng thái ban đầu của view, đồng thời theo dõi các ghi mới vào base.

~~~text
Base đã có 3 triệu hàng
          |
CREATE MATERIALIZED VIEW
          |
          +---- backfill: duyệt base và tạo view rows
          |
          +---- mutation mới tiếp tục tới base
          |                   |
          |                   v
          |          sinh view updates
          v
Initial build hoàn tất + view updates dần hội tụ
          |
Ứng dụng mới nên phụ thuộc vào kết quả view
~~~

Trong thực tế, phải xem **trạng thái build**:

~~~bash
nodetool viewbuildstatus mv_lab orders_by_customer
~~~

Lệnh hỗ trợ dạng `nodetool viewbuildstatus <keyspace> <view>` và được ghi nhận trong tài liệu Apache Cassandra 5.0. Điều cần kiểm tra là kết quả hoàn tất trên những node liên quan và không có lỗi build, không chỉ việc câu `CREATE MATERIALIZED VIEW` đã trả thành công. Nếu lượng dữ liệu lớn, build có thể tốn CPU/disk/network; Cassandra có tham số `concurrent_materialized_view_builders` và các lệnh `getconcurrentviewbuilders`/`setconcurrentviewbuilders`, nhưng thay đổi concurrency cần đánh giá riêng.

**Không dùng một lần COUNT hoặc SELECT đơn lẻ để khẳng định MV đã đầy đủ.** Với view có số partition cao, COUNT trên toàn view có thể là truy vấn đắt và tự nó không bảo đảm phát hiện sai lệch theo hàng.

## 7. ALTER và DROP MATERIALIZED VIEW

`ALTER MATERIALIZED VIEW` dùng để thay **table options** mà phiên bản hỗ trợ, không phải để sửa SELECT, WHERE hay PRIMARY KEY của view.

~~~sql
-- Hợp lệ: đổi comment thuộc tính view.
ALTER MATERIALIZED VIEW mv_lab.orders_by_customer
WITH comment = 'Lab view: query by customer';
~~~

Muốn chuyển view từ `PRIMARY KEY ((customer_id), tenant_id, order_id)` sang partition key khác hoặc đổi tập cột/điều kiện lọc? Cần **thiết kế một view mới và xây dựng lại** (hoặc drop/recreate có kế hoạch), vì ALTER không thay được những thành phần định nghĩa đó.

~~~sql
-- Dọn môi trường lab sau khi đã kiểm tra.
DROP MATERIALIZED VIEW IF EXISTS mv_lab.orders_by_customer;

-- Sau đó mới xóa base table/keyspace nếu không còn dùng.
~~~

`DROP MATERIALIZED VIEW` chỉ bỏ view và dữ liệu view, **không xóa dữ liệu bảng gốc**. Ngược lại, thay đổi schema base khi có view đang phụ thuộc có thể bị hạn chế, đặc biệt DROP cột; không xem việc ALTER base là thao tác độc lập khỏi các view.

## 8. Giới hạn và thay đổi theo phiên bản Apache Cassandra

MV có lịch sử lâu hơn SAI nhưng độ trưởng thành sản phẩm khác nhau. **Cú pháp xuất hiện từ Cassandra 3.0 không đồng nghĩa đã trở thành tính năng production-ready ở dòng 4.x hoặc 5.0.**

| Dòng phiên bản | Khả năng MV và tình trạng | Cấu hình/cú pháp cần lưu ý |
|---|---|---|
| **3.0** | Có Materialized View từ dòng 3.x; thiết kế và lỗi nhất quán còn thay đổi qua các bản sau | Không áp dụng máy móc ví dụ/giả định của 5.0 cho 3.0 |
| **3.11** | MV đã được coi là experimental; hạn chế lọc trên cột thường được siết | NEWS của Cassandra 3.11 nêu việc **tắt khả năng lọc view theo điều kiện giá trị trên cột không thuộc base PK** |
| **4.0** | MV vẫn experimental, có cảnh báo khi tạo; quy tắc tạo view được siết rõ hơn | Bắt buộc viết rõ các base PK column trong view và điều kiện NOT NULL; tham số legacy `enable_materialized_views` được dùng trong những bản này |
| **4.1** | Tài liệu Apache khuyến cáo **không dùng production**, mặc định không cho phép tạo | `materialized_views_enabled: false` theo cấu hình mặc định; tên tham số thay đổi so với legacy |
| **5.0** | Vẫn **experimental**, dù CQL hỗ trợ CREATE/ALTER/DROP MV | `materialized_views_enabled: false` mặc định; kiểm tra `nodetool viewbuildstatus` và giới hạn của tài liệu 5.0 |

### 8.1. Tại sao lại phải quan tâm chính xác minor version?

Các bản sửa lỗi về MV đã động chạm tới **timestamp, row liveness, xóa cột và repair**. Ví dụ NEWS dòng 4.x có các cảnh báo về trường hợp deletion của cột khóa view khi repair sau upgrade, và **CASSANDRA-13826** liên quan xóa cột base không được SELECT vào view. Khi nâng cấp cluster cũ có MV, cần đọc NEWS của **tất cả phiên bản đi qua**, biết chính xác view nào dùng cột không phải khóa làm view PK, và đánh giá repair/rebuild theo hướng dẫn phát hành.

**Không kết luận “Cassandra 5.0 đã sửa hết lỗi MV”** chỉ vì phiên bản mới hơn. Trong tài liệu chính thức 5.0, MV vẫn được đánh dấu experimental.

### 8.2. Cờ bật MV và ranh giới an toàn của bài lab

Cấu hình mẫu cho cluster lab **đã được phép thử tính năng experimental**:

~~~yaml
# cassandra.yaml (Cassandra 4.1/5.0; minh họa trong lab)
materialized_views_enabled: true
~~~

Nếu giữ mặc định `false`, câu CREATE VIEW có thể bị từ chối; cần xem lỗi trả về và cấu hình trên node. Thay đổi `cassandra.yaml` và restart theo quy trình phiên bản đang dùng **không được thực hiện tùy tiện trên production**. Đối với một cluster nhiều node, việc cùng lúc có node bật và node tắt có thể khiến schema/cập nhật không vận hành như kỳ vọng; phải kiểm tra cấu hình trên toàn cụm theo thủ tục vận hành.

Do tham số đã được đổi tên giữa các thế hệ, đừng sao chép cấu hình 4.1/5.0 vào 3.x/4.0 mà không đối chiếu tài liệu đúng version. Trên Cassandra 4.1/5.0, tham số `materialized_views_enabled` **chỉ cho phép tạo MV**, không biến việc cập nhật MV thành giao dịch đồng bộ với base.

## 9. Giới hạn nhất quán và các tình huống cần đặc biệt cảnh giác

### 9.1. Base và view không tạo thành giao dịch ACID liên bảng

Giả sử:

~~~text
App: INSERT base order
      |
      v
Base replica đủ ACK theo CL -> App nhận SUCCESS
      |
      |   khoảng trễ / lỗi truyền update
      v
View replica mới nhận và áp dụng mutation
      |
      v
App: SELECT từ view -> thấy order
~~~

Vì view dùng partition key có thể khác, một yêu cầu `LOCAL_QUORUM` với base **không có nghĩa** `LOCAL_QUORUM` đọc view ngay lập tức nhìn thấy kết quả write mới. Các luật quorum thường áp dụng cho **cùng bảng/tập replica**, không tự chuyển thành cam kết đồng bộ giữa hai bảng vật lý.

Trong hệ thống có node chết, hints, repair, bootstrap hoặc lịch sử lỗi phiên bản, view còn có thể sai lệch lâu hơn thời gian truyền bình thường. Do đó không dùng MV cho yêu cầu như **ràng buộc duy nhất, số dư tài chính nhất quán tức thời, hoặc xác nhận đơn hàng đã chuyển trạng thái không thể đọc sai** mà không có cơ chế đảm bảo bổ sung.

### 9.2. Nguy cơ xóa cột không được đưa vào SELECT

Tài liệu MV chính thức của Cassandra có ghi nhận hạn chế **CASSANDRA-13826**: thao tác xóa một cột của base **không được chọn vào view** có thể che khuất một số mutation trễ của cột khác nhận qua hints/repair. Khi base có view và workload thường xuyên xóa lẻ từng cột, đây là vấn đề thiết kế cần đánh giá cụ thể; việc SELECT hết cột giúp tránh chính lớp rủi ro do **unselected column**, nhưng không biến MV thành cơ chế nhất quán tuyệt đối.

Ví dụ rủi ro theo khái niệm:

~~~sql
-- Giả sử view chỉ SELECT tenant_id, order_id, customer_id,
-- không SELECT amount; đây là ví dụ thao tác trên base:
DELETE amount
FROM mv_lab.orders
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Không tự khẳng định rằng mọi phiên bản hay mọi lần chạy DELETE đều làm view sai. Hạn chế là **tình huống mất tương thích với mutation bị trễ**, không phải tất cả thao tác xóa sẽ thất bại ngay.

### 9.3. Đừng nhầm repair của base với tự sửa mọi sai lệch của view

Repair đồng bộ dữ liệu giữa replica của bảng liên quan; do view mutation có logic dẫn xuất riêng từ base, không thể khẳng định `nodetool repair` trên base luôn tái tạo chính xác mọi mutation view từng thất lạc. Một số phiên bản/config có cơ chế replay view mutation trong quá trình streaming; tham số `materialized_views_on_repair_enabled` cần được đánh giá theo version và trạng thái dữ liệu. Không thay đổi cờ repair chỉ để giảm tải nếu chưa hiểu rủi ro nhất quán.

Nếu nghi ngờ view đã lệch dữ liệu, cần xác định **phiên bản, cách xây view, thay đổi topology, lỗi node, hints, repair và các trường hợp xóa/TTL**. Biện pháp khôi phục phụ thuộc lỗi cụ thể và có thể bao gồm kiểm kê base-view, sửa dữ liệu, hoặc xây lại view có kế hoạch. Không “sửa” bằng UPDATE trực tiếp vào view.

### 9.4. Chi phí thực thi

| Tác động | Nguồn chi phí | Kết quả có thể quan sát |
|---|---|---|
| Ghi chậm hoặc timeout | Đọc trạng thái hàng base để quyết định view mutation và ghi sang view replicas | Base write latency/timeout tăng |
| Dùng thêm đĩa | View lưu row/SSTable, có replication và compaction riêng | Tăng disk, compaction backlog |
| Nóng partition view | Key view có phân bố kém, ví dụ view partition chỉ theo status | Một số node/partition chịu nhiều read/write |
| Initial build kéo dài | Quét dữ liệu base đã tồn tại | CPU/disk/network tăng, view chưa đầy đủ |
| Kết quả đọc chậm hội tụ | Propagation bất đồng bộ, node/hints/repair | SELECT view tạm thiếu hoặc thừa dữ liệu |

**Đổi khóa view không tự tối ưu phân bố dữ liệu.** Chẳng hạn view có partition key là `state` với chỉ vài giá trị 'NEW'/'PAID'/'FAILED' có thể tạo partition rất lớn; nên chọn partition key theo độ phân tán và đường truy vấn thực tế.

## 10. Bài thực hành đầu-cuối trên Cassandra 4.1/5.0

**Yêu cầu:** cluster lab đã cấu hình cho phép MV; không thực hiện thay đổi cờ experimental trên production. Dùng keyspace `mv_lab` và bảng `orders` ở phần 3.

### Bước 1: kiểm tra version và trạng thái node

~~~bash
nodetool version
nodetool status
~~~

Đối chiếu tên tham số trong `cassandra.yaml` của phiên bản chạy. Cassandra 4.1/5.0 thông thường cần `materialized_views_enabled: true` để CREATE MV trong lab; nếu CREATE báo tính năng bị tắt, ghi nhận lỗi đó rồi kiểm tra môi trường, không tự đổi cluster ngoài phạm vi cho phép.

### Bước 2: ghi hàng trước khi tạo MV, rồi tạo view

~~~sql
INSERT INTO mv_lab.orders
    (tenant_id, order_id, customer_id, amount, state)
VALUES ('tenant-1',
        11111111-1111-1111-1111-111111111111,
        'customer-A', 150, 'NEW');

INSERT INTO mv_lab.orders
    (tenant_id, order_id, amount, state)
VALUES ('tenant-1',
        22222222-2222-2222-2222-222222222222,
        250, 'NEW');

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_lab.orders_by_customer AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id)
    WITH comment = 'Lab view by customer';
~~~

Đây là bài toán **initial build**: hàng đã tồn tại trước CREATE phải được đưa vào MV nếu thỏa WHERE.

### Bước 3: xác nhận build trước khi đọc

~~~bash
nodetool viewbuildstatus mv_lab orders_by_customer
~~~

Khi trạng thái cho thấy việc build hoàn tất trên phạm vi cần thiết, kiểm tra:

~~~sql
SELECT tenant_id, order_id, customer_id, amount, state
FROM mv_lab.orders
WHERE tenant_id = 'tenant-1';

SELECT tenant_id, order_id, customer_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';
~~~

**Kỳ vọng khi hội tụ:** View có đơn `1111...` ở customer-A; đơn `2222...` không được đưa vào vì không có customer_id. Tại thời điểm build hoặc propagation chưa hoàn tất, kết quả có thể chưa đạt kỳ vọng.

### Bước 4: cập nhật cột thường và khóa view

~~~sql
UPDATE mv_lab.orders
SET amount = 175, state = 'PAID'
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;

UPDATE mv_lab.orders
SET customer_id = 'customer-B'
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT order_id, customer_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';

SELECT order_id, customer_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-B';
~~~

**Kỳ vọng khi hội tụ:** Khóa view cũ ở customer-A biến mất; customer-B có đơn `1111...` với `amount=175` và `state='PAID'`. Lặp kiểm tra có kiểm soát trong lab để quan sát độ trễ; không biến việc đọc lại liên tục thành cơ chế đảm bảo nhất quán của ứng dụng.

### Bước 5: đưa hàng trước đó chưa đủ điều kiện vào MV

~~~sql
UPDATE mv_lab.orders
SET customer_id = 'customer-B'
WHERE tenant_id = 'tenant-1'
  AND order_id = 22222222-2222-2222-2222-222222222222;

SELECT order_id, customer_id, amount
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-B';
~~~

Hàng `2222...` có `customer_id` mới, nên được đưa vào view khi mutation được xử lý. Sau đó thử xóa:

~~~sql
DELETE FROM mv_lab.orders
WHERE tenant_id = 'tenant-1'
  AND order_id = 22222222-2222-2222-2222-222222222222;

SELECT order_id, customer_id, amount
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-B';
~~~

Sau khi hội tụ, hàng `2222...` không còn trong view. Đừng thử `DELETE FROM mv_lab.orders_by_customer` vì view không ghi trực tiếp được.

### Bước 6: ALTER thuộc tính, DROP khi xong lab

~~~sql
ALTER MATERIALIZED VIEW mv_lab.orders_by_customer
WITH comment = 'Lab completed';

DROP MATERIALIZED VIEW IF EXISTS mv_lab.orders_by_customer;
~~~

Xác minh base vẫn tồn tại:

~~~sql
SELECT * FROM mv_lab.orders
WHERE tenant_id = 'tenant-1';
~~~

Mỗi thao tác CQL ở đây có thể thực hiện ở lab độc lập. Nếu đã có đối tượng tên trùng do buổi thực hành trước, `IF NOT EXISTS` không kiểm tra sự giống nhau của schema: trước khi chạy UPDATE, hãy xem lại định nghĩa bảng/view thực tế.

## 11. Dùng Java Driver với base table và view

Java Driver 4.x gửi các câu CQL như bình thường. Ứng dụng ghi **base table** và đọc **view** bằng SELECT; không có API đặc biệt để “refresh MV” thủ công.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

public final class OrderQueries {
    // CqlSession được tạo và tái sử dụng bởi ứng dụng.
    public static void updateState(
            CqlSession session, String tenantId, UUID orderId, String state) {
        SimpleStatement update = SimpleStatement.builder(
                "UPDATE mv_lab.orders SET state = ? " +
                "WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(state, tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();
        session.execute(update);
    }

    public static ResultSet findByCustomer(
            CqlSession session, String customerId) {
        SimpleStatement read = SimpleStatement.builder(
                "SELECT order_id, tenant_id, state " +
                "FROM mv_lab.orders_by_customer WHERE customer_id = ?")
            .addPositionalValue(customerId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(100)
            .build();
        return session.execute(read);
    }
}
~~~

**Cảnh báo cho ví dụ:** Lab `mv_lab` được tạo với RF=1, vì vậy `LOCAL_QUORUM` tương đương một replica trong lab đó. Với RF lớn hơn, đọc view LOCAL_QUORUM **vẫn không** tự đảm bảo vừa ghi base xong đã thấy ngay view. Với yêu cầu đọc-sau-ghi nghiêm ngặt, truy vấn lại **base bằng khóa gốc** hoặc dùng một cơ chế dữ liệu có đồng bộ/đối soát rõ ràng.

Driver cần cấu hình local datacenter, timeout, retry và paging hợp lý. Không đưa các câu UPDATE/INSERT trực tiếp tới MV; kiểm soát rollout tính năng mới để ứng dụng không phụ thuộc vào view đang initial build.

## 12. Tình huống phỏng vấn và lỗi hay gặp

| Tình huống | Giải thích và hướng xử lý |
|---|---|
| CREATE MV báo feature disabled | Cassandra 4.1/5.0 mặc định tắt MV; kiểm tra chính xác version/cấu hình và chính sách môi trường |
| WHERE thiếu điều kiện NOT NULL của cột view PK | Viết điều kiện IS NOT NULL phù hợp cho **mọi** thành phần khóa view |
| PRIMARY KEY thiếu một cột khóa của base | MV phải chứa **toàn bộ** base PK, kể cả clustering columns |
| PRIMARY KEY thêm hai cột base không thuộc khóa | Apache Cassandra MV chỉ cho thêm **một** non-base-PK column |
| CREATE MV dùng `WHERE state='PAID'` khi state không thuộc base PK | Không cho lọc bằng giá trị trên cột base thường; chỉ IS NOT NULL theo giới hạn MV |
| Ghi INSERT trực tiếp vào MV | View chỉ được đọc qua CQL; ghi lên **base table** |
| Ghi base thành công nhưng SELECT MV chưa thấy ngay | Propagation bất đồng bộ và initial build; CL của base không bảo đảm view tức thì |
| Thay customer_id làm hàng tạm xuất hiện ở khóa cũ/mới | View key di chuyển và mutations cho khóa cũ/mới không phải giao dịch toàn cục |
| ALTER MV để sửa PRIMARY KEY | ALTER chỉ cập nhật options; muốn đổi khóa/WHERE cần xây view mới |
| Đã DROP MV nhưng base vẫn còn | DROP MATERIALIZED VIEW không xóa base table |
| Chỉ chạy repair base rồi cho rằng MV luôn khớp | Repair dữ liệu không bảo đảm tái tạo mọi view mutation mất trước đó; phải kiểm chứng |
| Muốn bật MV trên cụm 5.0 production mới | Đối chiếu cảnh báo experimental chính thức; ưu tiên thiết kế khác có kiểm soát |

### Tự kiểm tra

1. Base có `PRIMARY KEY ((company_id, shard), event_id)` và cột thường `kind`. Một MV muốn phân vùng theo `kind` phải chứa những cột nào trong view PRIMARY KEY?
2. Một MV có thể thêm cả `kind` và `severity` (đều là cột thường) vào PRIMARY KEY không? Vì sao?
3. Khi UPDATE `customer_id` từ A sang B, có bao nhiêu vị trí khóa view bị ảnh hưởng?
4. Tại sao `LOCAL_QUORUM` khi đọc MV không bảo đảm đọc-sau-ghi tức thời từ base?
5. Tại sao `CREATE MATERIALIZED VIEW IF NOT EXISTS` không phải công cụ migration schema?
6. Kể một tình huống cần đọc `nodetool viewbuildstatus` trước khi triển khai truy vấn Java.

**Đáp án định hướng:** (1) company_id, shard, event_id và kind; (2) không theo hạn chế tối đa một non-base-PK column; (3) khóa A cần loại và khóa B cần thêm; (4) base và view có tập replica/propagation riêng; (5) không so khớp định nghĩa đang tồn tại; (6) khi tạo MV trên bảng đã có dữ liệu cần initial build.

## 13. Những điều phải nhớ

~~~text
MV hợp lệ:
  SELECT chỉ lấy cột gốc, không aggregate/function/static
  WHERE đủ IS NOT NULL cho các cột view PK
  PRIMARY KEY view chứa toàn bộ base PK
  PRIMARY KEY view thêm tối đa 1 cột không thuộc base PK
  View ở cùng keyspace với base

Ghi dữ liệu:
  Ghi INSERT/UPDATE/DELETE vào base
  Base mutation -> view mutation (có thể đến sau)
  Không write trực tiếp MV, không coi CL base = CL view

Vòng đời:
  CREATE -> initial build -> kiểm viewbuildstatus -> ứng dụng đọc view
  ALTER chỉ đổi options -> DROP view không DROP base

Phiên bản:
  Apache Cassandra 4.1/5.0: MV experimental, mặc định disabled
  Dòng 3.x/4.x cũ: luôn đọc NEWS và tài liệu đúng version
~~~

Cassandra được thiết kế quanh **partition key và bảng theo truy vấn**; MV là một cơ chế duy trì bảng phụ có giới hạn và rủi ro cần hiểu rõ. Với sản phẩm thực tế đòi hỏi nhất quán cao, hãy so sánh chi phí và khả năng kiểm soát của bảng denormalized do ứng dụng quản lý, CDC/consumer có đối soát và SAI (nếu phù hợp Cassandra 5.0), rồi lựa chọn theo yêu cầu nhất quán, truy vấn và phiên bản.

## Tài liệu tham khảo

- [Apache Cassandra 5.0 — Materialized Views](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/mvs.html) — SELECT, WHERE, PRIMARY KEY, ALTER/DROP và hạn chế CASSANDRA-13826.
- [Apache Cassandra 4.1 — cassandra.yaml, materialized_views_enabled](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html) — trạng thái experimental và mặc định false.
- [Apache Cassandra 5.0 — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — cảnh báo production, tham số MV/repair.
- [Apache Cassandra 5.0 — nodetool viewbuildstatus](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/viewbuildstatus.html) — kiểm tra tiến độ initial build.
- [Apache Cassandra 4.1 — Configuration parameter naming](https://cassandra.apache.org/doc/4.1/cassandra/configuration/configuration.html) — đổi tên `enable_materialized_views` thành `materialized_views_enabled`.
- [Apache Cassandra NEWS (4.1 branch)](https://apache.googlesource.com/cassandra/+/refs/heads/cassandra-4.1/NEWS.txt) — cảnh báo experimental, thay đổi quy tắc tạo view và giới hạn từ các dòng cũ.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — INSERT, UPDATE, DELETE, TTL và timestamp.
