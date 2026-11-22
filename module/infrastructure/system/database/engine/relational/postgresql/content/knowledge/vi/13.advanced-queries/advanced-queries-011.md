# Phân trang theo khóa và so sánh với OFFSET trong PostgreSQL

Khi một ứng dụng có hàng triệu đơn hàng, nhật ký sự kiện hoặc bài viết, việc trả toàn bộ dữ liệu trong một request không hiệu quả. Giao diện thường chỉ cần 20, 50 hoặc 100 hàng mỗi lần. PostgreSQL hỗ trợ hai chiến lược phổ biến: **phân trang theo vị trí bằng LIMIT/OFFSET** và **phân trang theo khóa bằng keyset/seek pagination**.

Hai chiến lược đều sử dụng `ORDER BY` và `LIMIT`, nhưng khác nhau ở cách xác định vị trí bắt đầu của trang kế tiếp. OFFSET đếm và bỏ qua các hàng đứng trước trang; keyset lưu dấu **giá trị khóa sắp xếp của hàng cuối trang hiện tại**, rồi truy vấn tiếp từ dấu đó.

Sự khác nhau ảnh hưởng đến hiệu năng, độ ổn định giữa các request và trải nghiệm của người dùng khi dữ liệu đang được chèn, sửa hoặc xóa.

Bài học thuộc chương **Truy vấn nâng cao**, module **Database Engine Relational PostgreSQL**, trình bày:

- Cách hoạt động và chi phí của `LIMIT/OFFSET`.
- Cách thiết kế keyset cho `ORDER BY` tăng/giảm và khóa ghép.
- Vai trò của **tie-breaker duy nhất**, row-value comparison và chỉ mục B-tree.
- Cách xử lý sắp xếp hỗn hợp, `NULL`, filter, trang trước và trang cuối.
- Tác động của MVCC, transaction isolation và thay đổi dữ liệu đồng thời.
- Cách đưa cursor vào API/Java JDBC, bảo vệ token và đo bằng `EXPLAIN`.
- Những tình huống vẫn nên dùng OFFSET thay vì cố chuyển mọi thứ sang keyset.

## 1. Phân trang phải bắt đầu từ thứ tự xác định

Câu SQL:

~~~sql
SELECT id, created_at
FROM orders
LIMIT 20;
~~~

không bảo đảm “20 đơn mới nhất”, vì không có `ORDER BY`. PostgreSQL có thể trả hàng theo thứ tự index, heap hoặc kế hoạch thực thi khác.

Nếu ứng dụng muốn đơn mới nhất trước:

~~~sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Ở đây:

- `created_at DESC`: thời điểm tạo mới hơn đứng trước.
- `id DESC`: khi nhiều đơn cùng timestamp, ID lớn hơn đứng trước.
- `LIMIT 20`: trả tối đa 20 hàng.

Cột `id` giữ vai trò **tie-breaker**. Nếu `id` là primary key và `created_at` không NULL, cặp `(created_at,id)` xác định một thứ tự toàn phần: hai hàng khác nhau sẽ không có cùng toàn bộ cặp khóa.

**Nguyên tắc quan trọng nhất:** phân trang không chỉ cần giới hạn số hàng; nó phải định nghĩa **thứ tự các hàng** và **vị trí của trang trong thứ tự đó**.

## 2. Tạo dữ liệu thực hành

Các ví dụ sử dụng bảng đơn hàng riêng trong một database học tập. Không thực hiện trên production. Lệnh `CREATE SCHEMA` dưới đây chỉ phù hợp nếu schema chưa tồn tại; nếu đã có, hãy dùng một database lab mới thay vì xóa schema đang dùng.

~~~sql
CREATE SCHEMA pagination_lab;

CREATE TABLE pagination_lab.orders (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);

INSERT INTO pagination_lab.orders
    (id, created_at, status, total_amount)
VALUES
    (100, TIMESTAMPTZ '2026-02-10 10:02:00+00', 'paid',       100000.00),
    (101, TIMESTAMPTZ '2026-02-10 10:03:00+00', 'new',        120000.00),
    (102, TIMESTAMPTZ '2026-02-10 10:03:00+00', 'paid',       140000.00),
    (103, TIMESTAMPTZ '2026-02-10 10:04:00+00', 'cancelled',  160000.00),
    (104, TIMESTAMPTZ '2026-02-10 10:04:00+00', 'paid',       180000.00),
    (105, TIMESTAMPTZ '2026-02-10 10:04:00+00', 'new',        200000.00),
    (106, TIMESTAMPTZ '2026-02-10 10:05:00+00', 'paid',       220000.00);

CREATE INDEX idx_orders_created_id_desc
ON pagination_lab.orders (created_at DESC, id DESC);
~~~

Truy vấn kiểm tra:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC;
~~~

Thứ tự ID kỳ vọng:

~~~text
106  10:05
105  10:04
104  10:04
103  10:04
102  10:03
101  10:03
100  10:02
~~~

Các timestamp cùng ngày 2026-02-10 và cùng múi giờ UTC. Cố ý có các nhóm trùng timestamp để quan sát lý do cần khóa phụ `id`.

## 3. OFFSET pagination: bỏ qua số hàng

OFFSET sử dụng cú pháp:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;
~~~

Đây là trang đầu, gồm ID `106,105,104`.

Trang thứ hai:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;
~~~

Kết quả là `103,102,101`.

Trang thứ ba:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 6;
~~~

Chỉ còn ID `100`.

Với số trang bắt đầu từ 1:

\[
\text{offset}=(\text{pageNumber}-1)\times\text{pageSize}
\]

Ví dụ trang 3 với pageSize 3 có offset 6.

### 3.1. Ưu điểm thực tế của OFFSET

- Câu SQL đơn giản, dễ tích hợp giao diện có số trang.
- Có thể nhảy trực tiếp tới trang N bằng cách tính offset.
- Không phải nhớ khóa cuối của trang trước.
- Phù hợp bảng nhỏ, tập dữ liệu giới hạn, báo cáo quản trị hoặc chỉ truy cập các trang đầu.
- Có thể dùng với nhiều cách sort mà không phải tự xây dựng predicate seek cho từng kiểu.

Không nên kết luận OFFSET là kỹ thuật sai. Nó là một công cụ hợp lệ khi chi phí và semantics phù hợp yêu cầu.

## 4. Vì sao OFFSET sâu thường tốn công việc?

Xét một bảng có hàng triệu hàng:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
~~~

Mặc dù chỉ trả tối đa 20 hàng, PostgreSQL vẫn phải xác định và bỏ qua các hàng đứng trước vị trí offset trong kết quả có thứ tự. Với một index scan phù hợp, engine có thể tránh sort toàn bộ bảng nhưng vẫn thường phải **đi qua nhiều index entries/hàng bị bỏ qua**.

Ví dụ khái niệm:

~~~text
OFFSET 0       -> bắt đầu gần đầu danh sách, trả 20 hàng
OFFSET 1000    -> đi qua khoảng 1000 hàng trước, trả 20 hàng
OFFSET 100000  -> đi qua khoảng 100000 hàng trước, trả 20 hàng
~~~

Đây là trực giác về lượng công việc, không phải một công thức chi phí tuyệt đối cho mọi kế hoạch PostgreSQL. Thời gian thực còn phụ thuộc WHERE, index, sorting, visibility, cache và số hàng bị lọc.

Nếu query không có index hỗ trợ `ORDER BY`, PostgreSQL có thể phải đọc và sắp một lượng dữ liệu lớn để xác định trang đích.

**LIMIT không làm biến mất chi phí tìm vị trí sau OFFSET.** Nó giới hạn số hàng trả về, nhưng không tự đưa con trỏ đến hàng thứ 100001 của một tập kết quả động.

## 5. OFFSET có thể lặp hoặc bỏ sót dữ liệu giữa các trang

Tại thời điểm T1:

~~~text
[106, 105, 104, 103, 102, 101, 100]

Trang 1, LIMIT 3 OFFSET 0 -> [106, 105, 104]
~~~

Sau đó một transaction khác chèn đơn mới ID 107 có `created_at` lớn hơn:

~~~text
T2:
[107, 106, 105, 104, 103, 102, 101, 100]
~~~

Client lấy trang thứ hai:

~~~text
LIMIT 3 OFFSET 3 -> [104, 103, 102]
~~~

**ID 104 bị trả lại lần nữa** dù đã có ở trang đầu. Lý do: một hàng mới được chèn trước vị trí offset làm các hàng cũ dịch xuống.

Nếu một hàng phía trước ranh giới bị xóa, các hàng phía sau dịch lên và OFFSET có thể làm client **bỏ qua** hàng chưa xem.

Đây không phải lỗi tính toán offset. OFFSET có nghĩa là bỏ qua N hàng **trong kết quả hiện tại**; nó không nhớ client đã nhìn thấy bản ghi nào ở request trước.

## 6. Keyset/seek pagination là gì?

Keyset không lưu “đã bỏ qua 3 hàng”, mà lưu **“hàng cuối vừa hiển thị có khóa (created_at,id) nào?”**.

Với dữ liệu demo:

~~~sql
-- Trang đầu:
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

Kết quả `106,105,104`. Cursor nằm ở **hàng cuối**:

~~~text
created_at = 2026-02-10 10:04:00+00
id         = 104
~~~

Vì danh sách giảm dần, hàng nằm **sau cursor** nếu thời gian nhỏ hơn, hoặc cùng thời gian nhưng ID nhỏ hơn:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
WHERE
    created_at < TIMESTAMPTZ '2026-02-10 10:04:00+00'
    OR (
        created_at = TIMESTAMPTZ '2026-02-10 10:04:00+00'
        AND id < 104
    )
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

Kết quả là `103,102,101`.

Sơ đồ:

~~~text
106 (10:05)
105 (10:04)
104 (10:04)  <- cursor của trang 1
------------------------------
103 (10:04)
102 (10:03)
101 (10:03)  <- cursor của trang 2
------------------------------
100 (10:02)
~~~

Với index hỗ trợ, PostgreSQL có thể dùng điều kiện khóa để tìm vùng tiếp theo thay vì duyệt một đoạn rất dài trước đó.

## 7. PostgreSQL hỗ trợ so sánh bộ giá trị (row-value comparison)

Điều kiện dài:

~~~sql
WHERE
    created_at < :last_created_at
    OR (
        created_at = :last_created_at
        AND id < :last_id
    )
~~~

có thể rút thành:

~~~sql
WHERE (created_at, id) < (:last_created_at, :last_id)
~~~

Đây là so sánh tuple theo thứ tự từ điển (lexicographic): so cột đầu; nếu bằng thì so cột tiếp theo.

Truy vấn chạy trực tiếp được trong `psql`:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
WHERE
    (created_at, id)
        < (TIMESTAMPTZ '2026-02-10 10:04:00+00', 104::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

Trong các ví dụ có `:last_created_at`, ký hiệu dấu hai chấm chỉ **tham số khái niệm ở tầng ứng dụng**. Nó không phải placeholder SQL chuẩn mà server PostgreSQL tự hiểu khi copy nguyên văn. JDBC dùng `?` và bind giá trị; `psql` có cú pháp biến riêng.

### 7.1. Vì sao tuple comparison đúng trong trường hợp này?

Với:

~~~text
A = (10:04, 103)
B = (10:04, 104)
~~~

`A < B` vì thời gian bằng nhau nhưng 103 nhỏ hơn 104.

Với:

~~~text
A = (10:03, 9999)
B = (10:04, 104)
~~~

`A < B` vì thời gian nhỏ hơn, bất kể ID của A lớn.

Các cột đều sắp **DESC**, và cả hai đều **NOT NULL**, nên `<` của tuple phù hợp với ý nghĩa “đứng sau cursor”.

### 7.2. Điều kiện để dùng cách rút gọn

- Các sort key trong tuple cùng chiều **ASC** hoặc cùng chiều **DESC**.
- Có kiểu so sánh phù hợp và không có trường hợp `NULL` chưa xử lý.
- Cursor chứa **toàn bộ khóa** dùng trong ORDER BY.
- Có tie-breaker độc nhất để tránh bỏ sót hàng trùng khóa.

Với sắp xếp pha trộn chiều hoặc `NULLS FIRST/LAST`, phải thiết kế điều kiện riêng.

## 8. Vì sao phải có tie-breaker duy nhất?

Một lỗi phổ biến:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC
LIMIT 3;
~~~

Dữ liệu có ba hàng trùng timestamp `10:04`. Nếu chỉ lưu cursor thời gian, ví dụ `10:04`, rồi query:

~~~sql
WHERE created_at < TIMESTAMPTZ '2026-02-10 10:04:00+00'
~~~

thì những hàng khác có timestamp `10:04` nhưng chưa xem sẽ **không bao giờ được trả**.

Nếu đổi thành `<=`, các hàng đã xem có thể xuất hiện lại.

Giải pháp:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

và cursor mang cả:

~~~text
(last_created_at, last_id)
~~~

`id` là primary key nên không trùng, không NULL và thường không thay đổi. Đây là tie-breaker tiện dụng, nhưng có thể dùng một khóa duy nhất khác nếu phản ánh yêu cầu thiết kế.

**Không mặc định rằng chỉ thêm `user_id` hoặc `status` là đủ:** nhiều hàng hoàn toàn có thể trùng hai trường này.

## 9. Keyset chỉ dùng một cột ID

Nếu thứ tự nghiệp vụ thật sự là ID giảm dần:

~~~sql
SELECT id, status
FROM pagination_lab.orders
ORDER BY id DESC
LIMIT 3;
~~~

Sau khi trang đầu kết thúc ở ID 104:

~~~sql
SELECT id, status
FROM pagination_lab.orders
WHERE id < 104
ORDER BY id DESC
LIMIT 3;
~~~

Đây là keyset một cột và rất đơn giản. Primary key B-tree thường có sẵn.

Nhưng **ID tăng dần không đồng nghĩa thứ tự tạo hay thứ tự commit tuyệt đối**. PostgreSQL sequence có thể cấp ID ở transaction này trước nhưng transaction đó commit sau transaction khác. Một số ứng dụng dùng UUID hoặc ID từ hệ thống ngoài còn không có quan hệ rõ ràng với thời gian.

Chỉ sắp theo ID khi chính thứ tự ID là thứ tự cần hiển thị hoặc có bảo đảm đủ rõ trong kiến trúc.

## 10. Keyset khi ORDER BY ASC

Muốn xem đơn **cũ trước, mới sau**:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at ASC, id ASC
LIMIT 3;
~~~

Trang đầu là `100,101,102`. Cursor của hàng cuối là `(10:03,102)`.

Trang sau:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
WHERE
    (created_at, id)
        > (TIMESTAMPTZ '2026-02-10 10:03:00+00', 102::BIGINT)
ORDER BY created_at ASC, id ASC
LIMIT 3;
~~~

Kết quả `103,104,105`.

Quy tắc:

| Thứ tự | Predicate trang **tiếp theo** |
|---|---|
| `a ASC, b ASC` | `(a,b) > (:a,:b)` |
| `a DESC, b DESC` | `(a,b) < (:a,:b)` |
| `a DESC, b ASC` | Phải xây predicate pha trộn |
| `a ASC, b DESC` | Phải xây predicate pha trộn |

## 11. Sắp xếp hỗn hợp: DESC và ASC

Giả sử một danh sách nhiệm vụ cần ưu tiên cao trước, nhưng trong cùng mức ưu tiên thì ID nhỏ trước:

~~~sql
CREATE TABLE pagination_lab.tasks (
    task_id BIGINT PRIMARY KEY,
    priority INTEGER NOT NULL,
    task_name TEXT NOT NULL
);

INSERT INTO pagination_lab.tasks
    (task_id, priority, task_name)
VALUES
    (10, 3, 'A'),
    (11, 3, 'B'),
    (20, 2, 'C'),
    (21, 2, 'D'),
    (30, 1, 'E');

CREATE INDEX idx_tasks_priority_id
ON pagination_lab.tasks (priority DESC, task_id ASC);
~~~

Thứ tự:

~~~sql
SELECT task_id, priority
FROM pagination_lab.tasks
ORDER BY priority DESC, task_id ASC;
~~~

Kết quả:

~~~text
(priority=3,id=10)
(priority=3,id=11)
(priority=2,id=20)
(priority=2,id=21)
(priority=1,id=30)
~~~

Nếu cursor ở `(priority=3,id=11)`, hàng tiếp theo phải thỏa:

~~~sql
SELECT task_id, priority, task_name
FROM pagination_lab.tasks
WHERE
    priority < 3
    OR (priority = 3 AND task_id > 11)
ORDER BY priority DESC, task_id ASC
LIMIT 2;
~~~

Điều kiện chính xác là **priority nhỏ hơn**, hoặc **priority bằng và ID lớn hơn**.

Không viết:

~~~sql
-- Sai với thứ tự priority DESC, task_id ASC:
-- WHERE (priority, task_id) < (3, 11)
~~~

vì điều kiện đó có thể chọn task ID 10 (đứng trước cursor), không phải chỉ những task đứng sau.

Index `(priority DESC, task_id ASC)` phản ánh cách sắp xếp hỗn hợp. Một index mọi cột ASC không tự đáp ứng thứ tự DESC/ASC chỉ bằng việc quét ngược toàn bộ.

## 12. NULLS FIRST/LAST và cursor

Khi sort key cho phép `NULL`, row comparison đơn giản có thể không phản ánh thứ tự NULL trong `ORDER BY`.

Ví dụ:

~~~sql
CREATE TABLE pagination_lab.shipments (
    shipment_id BIGINT PRIMARY KEY,
    shipped_at TIMESTAMPTZ,
    tracking_code TEXT NOT NULL
);

INSERT INTO pagination_lab.shipments
    (shipment_id, shipped_at, tracking_code)
VALUES
    (1, TIMESTAMPTZ '2026-04-02 09:00:00+00', 'A'),
    (2, NULL, 'B'),
    (3, TIMESTAMPTZ '2026-04-01 09:00:00+00', 'C'),
    (4, NULL, 'D');
~~~

Thứ tự yêu cầu:

~~~sql
ORDER BY shipped_at DESC NULLS LAST, shipment_id DESC
~~~

Kỳ vọng: ID `1,3,4,2`.

### 12.1. Cursor nằm ở vùng có timestamp

Nếu cursor là `(2026-04-01 09:00, ID 3)`, những hàng tiếp theo gồm timestamp thấp hơn, cùng timestamp ID nhỏ hơn **và** toàn bộ hàng `shipped_at IS NULL` ở cuối.

~~~sql
SELECT shipment_id, shipped_at
FROM pagination_lab.shipments
WHERE
    (
        shipped_at IS NOT NULL
        AND (shipped_at, shipment_id)
            < (TIMESTAMPTZ '2026-04-01 09:00:00+00', 3::BIGINT)
    )
    OR shipped_at IS NULL
ORDER BY shipped_at DESC NULLS LAST, shipment_id DESC
LIMIT 3;
~~~

### 12.2. Cursor đã thuộc vùng NULL

Nếu cursor nằm ở ID 4 có `shipped_at IS NULL`:

~~~sql
SELECT shipment_id, shipped_at
FROM pagination_lab.shipments
WHERE
    shipped_at IS NULL
    AND shipment_id < 4
ORDER BY shipped_at DESC NULLS LAST, shipment_id DESC
LIMIT 3;
~~~

Kết quả là ID 2.

Index tương ứng:

~~~sql
CREATE INDEX idx_shipments_shipped_id
ON pagination_lab.shipments (
    shipped_at DESC NULLS LAST,
    shipment_id DESC
);
~~~

Không giả định thứ tự mặc định của NULL luôn là `NULLS LAST` khi DESC. Nên ghi rõ ở SQL/index khi semantics yêu cầu.

**Giải pháp đơn giản nhất** nếu nghiệp vụ cho phép là dùng sort key `NOT NULL`. Nếu không, cursor cần đánh dấu trường hợp khóa ở vùng NULL hay không và chọn predicate tương ứng.

## 13. Phân trang ngược: nút Previous

Với danh sách chuẩn `ORDER BY created_at DESC, id DESC`, trang hiện tại là:

~~~text
[103,102,101]
~~~

Muốn lấy ba hàng ngay trước đó, dùng cursor từ **hàng đầu** ID 103, không phải từ hàng cuối ID 101.

Các hàng trước cursor có khóa **lớn hơn**. Nhưng để lấy đúng ba hàng *gần nhất* trước cursor, phải tạm đảo chiều:

~~~sql
SELECT p.id, p.created_at
FROM (
    SELECT id, created_at
    FROM pagination_lab.orders
    WHERE
        (created_at, id)
            > (TIMESTAMPTZ '2026-02-10 10:04:00+00', 103::BIGINT)
    ORDER BY created_at ASC, id ASC
    LIMIT 3
) AS p
ORDER BY p.created_at DESC, p.id DESC;
~~~

Kết quả là `106,105,104` theo thứ tự hiển thị ban đầu.

Nếu giữ `ORDER BY DESC LIMIT 3` ngay ở truy vấn trong cùng với predicate `>`, với một danh sách dài có thể lấy ba hàng ở **đầu toàn danh sách**, không phải ba hàng sát cursor.

Quy tắc thực hành:

- **Next:** cursor từ hàng cuối, điều kiện đi xuôi, sort xuôi.
- **Previous:** cursor từ hàng đầu, điều kiện đi ngược, sort ngược để lấy N hàng gần nhất, sau đó đảo kết quả về thứ tự chuẩn.

## 14. Bộ lọc phải nhất quán qua các trang

Giả sử chỉ xem đơn đã thanh toán:

~~~sql
SELECT id, created_at, total_amount
FROM pagination_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, id DESC
LIMIT 2;
~~~

Nếu trang sau bỏ điều kiện `status = 'paid'` thì tập dữ liệu đã thay đổi. Cursor vốn là vị trí trong tập “paid”, không phải một vị trí có ý nghĩa tương tự ở mọi tập khác.

Truy vấn tiếp đúng:

~~~sql
SELECT id, created_at, total_amount
FROM pagination_lab.orders
WHERE status = 'paid'
  AND (created_at, id)
      < (TIMESTAMPTZ '2026-02-10 10:04:00+00', 104::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 2;
~~~

Nếu người dùng đổi filter sang `status='new'` hoặc đổi sort sang giá cao trước, ứng dụng nên **reset cursor** hoặc từ chối token không khớp cấu hình mới.

Ngoài filter hiển thị, còn cần giữ phạm vi tenant, quyền truy cập và các điều kiện server xác minh.

## 15. Index B-tree cho keyset

Index cơ bản đã tạo:

~~~sql
CREATE INDEX idx_orders_created_id_desc
ON pagination_lab.orders (created_at DESC, id DESC);
~~~

Có thể hỗ trợ:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
WHERE (created_at, id) < (:created_at, :id)
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Index phù hợp cho phép PostgreSQL tìm ranh giới khóa và duyệt phần dữ liệu cần lấy trong nhiều trường hợp, thay vì phải đi qua một lượng lớn hàng như OFFSET sâu.

### 15.1. Equality filter nên được cân nhắc trong index

Nếu truy vấn chủ yếu theo trạng thái:

~~~sql
WHERE status = 'paid'
  AND (created_at, id) < (...)
ORDER BY created_at DESC, id DESC
~~~

có thể cân nhắc:

~~~sql
CREATE INDEX idx_orders_status_seek
ON pagination_lab.orders (
    status,
    created_at DESC,
    id DESC
);
~~~

`status` là cột dẫn phục vụ equality filter, phần sau phục vụ khóa sắp xếp.

Nhưng nếu query xem **tất cả status** theo thời gian, index bắt đầu bằng status không nhất thiết hỗ trợ thứ tự toàn cục theo created_at mà không phải sort/hợp nhất thêm.

### 15.2. Partial index cho một trạng thái thường gặp

~~~sql
CREATE INDEX idx_orders_paid_seek
ON pagination_lab.orders (created_at DESC, id DESC)
WHERE status = 'paid';
~~~

Một partial index có thể nhỏ hơn và hiệu quả khi request chủ yếu hỏi `status='paid'`. Tuy nhiên planner phải chứng minh WHERE của truy vấn đáp ứng predicate của partial index. Một prepared statement có generic plan hoặc tham số hóa quá chung có thể không tận dụng nó như mong muốn.

### 15.3. INCLUDE không phải khóa sort

Nếu chỉ cần thêm các cột hiển thị:

~~~sql
CREATE INDEX idx_orders_cover_seek
ON pagination_lab.orders (created_at DESC, id DESC)
INCLUDE (status, total_amount);
~~~

`INCLUDE` bổ sung dữ liệu vào index nhưng **không biến status/total_amount thành khóa sắp xếp**. Nó có thể hỗ trợ một số index-only scan, nhưng visibility map/MVCC vẫn quyết định có cần đọc heap không; index rộng hơn cũng tăng chi phí lưu trữ và ghi.

Không tạo tất cả index ví dụ này trên production. Hãy chọn dựa vào workload và đo kế hoạch.

## 16. EXPLAIN: so sánh công việc thực thi

Với bảng nhỏ, hai query có thể đều nhanh và PostgreSQL có thể chọn sequential scan. `EXPLAIN` giúp xem kế hoạch thay vì đoán.

OFFSET:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;
~~~

Keyset:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders
WHERE
    (created_at, id)
        < (TIMESTAMPTZ '2026-02-10 10:04:00+00', 104::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

Quan sát:

- `Index Scan` hoặc `Index Only Scan` so với `Seq Scan`.
- `Index Cond` có mang điều kiện tuple không.
- Có node `Sort` hay không.
- Số `actual rows` mà các node tạo/đọc.
- `Rows Removed by Filter` khi có.
- `Buffers: shared hit/read`.
- Tổng thời gian, tác động cache, độ chọn lọc WHERE.

`EXPLAIN ANALYZE` **thực thi câu lệnh**. Trong bài này dùng với `SELECT`. Khi dùng với DML trên môi trường thật, phải hiểu lệnh có thể thay đổi dữ liệu; không tự chạy `EXPLAIN ANALYZE DELETE/UPDATE` chỉ để xem kế hoạch.

## 17. Tạo dữ liệu lớn để so sánh OFFSET 90000 và keyset

Trên database học tập có dung lượng phù hợp:

~~~sql
CREATE TABLE pagination_lab.orders_bench (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO pagination_lab.orders_bench
    (id, created_at, status, total_amount)
SELECT
    g::BIGINT,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + ((g - 1) / 20) * INTERVAL '1 second',
    CASE
        WHEN g % 4 = 0 THEN 'paid'
        ELSE 'new'
    END,
    (10000 + (g % 50000))::NUMERIC(12, 2)
FROM generate_series(1, 100000) AS g;

CREATE INDEX idx_orders_bench_seek
ON pagination_lab.orders_bench (created_at DESC, id DESC);

ANALYZE pagination_lab.orders_bench;
~~~

Bảng benchmark có 100.000 hàng, mỗi nhóm 20 hàng cùng timestamp, giá trị cố định theo ID. Nó chỉ là dữ liệu tổng hợp để quan sát truy vấn, không đại diện phân bố production.

### 17.1. OFFSET sâu

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders_bench
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 90000;
~~~

### 17.2. Keyset tại cùng vị trí

Với tập dữ liệu trên không bị thay đổi, hàng ngay trước vùng kết quả đó là ID 10001 có timestamp `2026-01-01 00:08:20+00`.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders_bench
WHERE
    (created_at, id)
        < (TIMESTAMPTZ '2026-01-01 00:08:20+00', 10001::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Kết quả kỳ vọng của cả hai câu trong trạng thái dữ liệu cố định là ID từ **10000 xuống 9981**.

So sánh số index entries/hàng thực sự đi qua và thời gian thực thi trong nhiều lần chạy. Keyset có thể tìm đến vùng khóa thích hợp qua index; OFFSET sâu thường vẫn phải đi qua phần lớn 90.000 hàng trước nó.

**Chỉ trong ví dụ đo này ta hardcode cursor** để có hai query tương đương; ứng dụng thật phải nhận cursor từ hàng cuối trang trước, không đoán ID dựa trên vị trí.

## 18. Keyset không tự làm mọi query nhanh

Keyset đặc biệt có lợi khi:

- WHERE và ORDER BY khớp index phù hợp.
- Tập dữ liệu lớn.
- Các trang sâu được truy cập liên tục.
- Truy vấn theo một thứ tự và khóa ổn định.

Nhưng nếu:

- Query tính `ORDER BY expensive_function(...)` mà không có cách index thích hợp.
- JOIN/aggregation rất phức tạp.
- Filter không có index và phải quét phần lớn bảng.
- Planner không thể đẩy seek predicate thành điều kiện chỉ mục.
- Bảng chỉ vài chục hàng.

thì lợi ích có thể ít hoặc không rõ.

**Index và predicate phải được thiết kế cùng nhau**, không chỉ đổi `OFFSET n` thành `WHERE id < x` rồi mặc định đã tối ưu.

## 19. Cursor cần chứa đủ thông tin gì?

Một cursor logic có thể gồm:

~~~text
version          = 1
sort             = created_at_desc_id_desc
last_created_at  = 2026-02-10T10:04:00.000000Z
last_id          = 104
status_filter    = paid
direction        = next
~~~

Tùy API, có thể thêm tenant, expiry hoặc định danh cấu hình lọc. Không nhất thiết lộ những trường này cho client dưới dạng JSON thuần.

Yêu cầu thiết kế:

1. **Đủ sort keys:** mọi cột cần để so sánh ranh giới, gồm tie-breaker.
2. **Không mất precision:** timestamp và số nguyên phải được encode/decode chính xác.
3. **Ràng buộc filter/sort:** token không hợp lệ khi đổi danh sách đang duyệt.
4. **Có version:** để thay đổi cấu trúc token.
5. **Không tin client:** xác thực tính toàn vẹn token và quyền truy cập ở server.
6. **Giới hạn tuổi thọ** nếu ứng dụng không muốn cursor tồn tại vô thời hạn.

### 19.1. Base64URL không phải mã hóa hoặc chữ ký

Một API thường trả:

~~~text
GET /api/orders?limit=20&after=<opaque-cursor>
~~~

Base64URL chỉ giúp chuyển payload thành chuỗi an toàn cho URL. Client vẫn có thể decode hoặc sửa nội dung nếu token không được bảo vệ.

Một cách làm:

- Serialize cursor có version.
- Ký payload bằng HMAC với khóa bí mật ở server.
- Encode payload và chữ ký thành chuỗi opaque.
- Khi nhận lại, verify chữ ký và expiry, so sánh filter/sort với request.
- Áp dụng authorization và tenant restriction từ phiên người dùng hiện tại.

**Chữ ký không che giấu nội dung.** Không đặt secret hoặc dữ liệu cá nhân nhạy cảm trong payload không mã hóa. Nếu cần bí mật, dùng thiết kế token mã hóa hoặc lưu trạng thái cursor phía server.

### 19.2. Cursor không thay thế authorization

Dù token hợp lệ, server vẫn phải ràng buộc query vào user/tenant được phép. Không lấy `tenant_id` do client tự gửi hoặc sửa trong token rồi xem đó là quyền truy cập.

Với multi-tenant, index có thể cần:

~~~sql
-- Mẫu ý tưởng khi bảng có cột tenant_id:
CREATE INDEX idx_orders_tenant_created_id
ON orders (tenant_id, created_at DESC, id DESC);
~~~

Truy vấn thực tế phải có predicate `tenant_id = :authorized_tenant_id`, giá trị do server xác thực. Đây là mẫu cho bảng có tenant_id, **không chạy nguyên văn trên bảng demo không có cột đó**.

## 20. API phân trang và kỹ thuật LIMIT N+1

Giả sử client yêu cầu `pageSize=20`. Server có thể lấy **21 hàng**:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

Ứng dụng:

1. Đọc tối đa 21 hàng.
2. Nếu thực sự nhận 21 hàng, đặt `hasNextPage=true`.
3. Trả tối đa **20 hàng đầu** cho client.
4. Dùng **hàng thứ 20 đã trả** làm cursor để lấy trang sau.
5. Nếu nhận ít hơn hoặc bằng 20 hàng, `hasNextPage=false` trong snapshot của truy vấn.
6. Nếu trang rỗng, trả cursor null/vắng mặt theo contract.

**Không lấy cursor từ hàng thứ 21** bị giữ lại: hàng đó chưa được hiển thị, và trang sau dùng ranh giới của nó sẽ bỏ sót hàng đó.

Một response minh họa cấu trúc:

~~~json
{
  "data": [
    {"id": 106, "createdAt": "2026-02-10T10:05:00Z"}
  ],
  "pageInfo": {
    "hasNextPage": false,
    "endCursor": "<opaque-or-null-cursor>"
  }
}
~~~

Đây là **hình dạng JSON mẫu**, không phải kết quả trực tiếp của `LIMIT 21` trên bộ dữ liệu demo; giá trị hasNextPage phải được tính bằng kết quả SQL thực tế.

### 20.1. Không tin trực tiếp pageSize

Server cần:

- Giá trị mặc định.
- Giới hạn tối đa.
- Xử lý số âm, 0, chữ, overflow.
- Rate limit/timeout khi phù hợp.

Ví dụ API có thể cho `1 <= pageSize <= 100`; con số là chính sách của ứng dụng, không phải giới hạn PostgreSQL bắt buộc.

## 21. Java/JDBC: PreparedStatement với cursor

Ở tầng Java, dùng `PreparedStatement` để bind filter và cursor thay vì nối giá trị từ request vào chuỗi SQL.

Ví dụ cho PostgreSQL JDBC driver có hỗ trợ `OffsetDateTime`, Java 17 trở lên và một `DataSource` đã cấu hình:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class OrderPager {
    public record SortCursor(OffsetDateTime createdAt, long id) {}
    public record OrderRow(long id, OffsetDateTime createdAt, String status) {}
    public record Page(List<OrderRow> rows, boolean hasNext, SortCursor endCursor) {}

    private final DataSource dataSource;

    public OrderPager(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Page fetch(String status, SortCursor after, int pageSize)
        throws SQLException {

        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page size");
        }

        String sql = after == null
            ? """
              SELECT id, created_at, status
              FROM pagination_lab.orders
              WHERE status = ?
              ORDER BY created_at DESC, id DESC
              LIMIT ?
              """
            : """
              SELECT id, created_at, status
              FROM pagination_lab.orders
              WHERE status = ?
                AND (created_at, id) < (?, ?)
              ORDER BY created_at DESC, id DESC
              LIMIT ?
              """;

        List<OrderRow> fetched = new ArrayList<>();

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            int param = 1;
            ps.setString(param++, status);
            if (after != null) {
                ps.setObject(param++, after.createdAt());
                ps.setLong(param++, after.id());
            }
            ps.setInt(param, pageSize + 1);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    fetched.add(new OrderRow(
                        rs.getLong("id"),
                        rs.getObject("created_at", OffsetDateTime.class),
                        rs.getString("status")
                    ));
                }
            }
        }

        boolean hasNext = fetched.size() > pageSize;
        List<OrderRow> rows = new ArrayList<>(
            fetched.subList(0, Math.min(pageSize, fetched.size()))
        );

        SortCursor endCursor = rows.isEmpty()
            ? null
            : new SortCursor(
                rows.get(rows.size() - 1).createdAt(),
                rows.get(rows.size() - 1).id()
            );

        return new Page(rows, hasNext, endCursor);
    }
}
~~~

Các chi tiết:

- Trang đầu và trang có cursor dùng **hai câu SQL** rõ ràng, tránh điều kiện `OR :cursor IS NULL` không cần thiết.
- `status` luôn có mặt trong filter.
- `OffsetDateTime` giữ semantics thời điểm; không cần tự cắt chuỗi timestamp.
- `setLong` truyền ID.
- `pageSize+1` dùng để phát hiện còn trang.
- Cursor tạo từ **hàng cuối đã trả**.
- Lớp API ở ngoài phải verify token/filter/authorization **trước khi gọi** phương thức.

Mã chỉ minh họa luồng truy vấn; triển khai thật còn cần TLS, connection pool, xử lý timeout, logging an toàn và token signing.

### 21.1. Không bind ORDER BY bằng placeholder giá trị

Không thể dùng dấu `?` thay trực tiếp tên cột hoặc từ khóa `ASC/DESC` theo cách tham số hóa giá trị. Nếu cho phép nhiều kiểu sort, server nên **whitelist** các template:

~~~text
newest    -> ORDER BY created_at DESC, id DESC
oldest    -> ORDER BY created_at ASC, id ASC
highValue -> ORDER BY total_amount DESC, id DESC
~~~

Mỗi template phải có cursor và điều kiện seek tương ứng. Không ghép tên cột tùy ý từ chuỗi người dùng.

## 22. Precision của timestamp ảnh hưởng tính đúng của cursor

PostgreSQL `TIMESTAMPTZ` thường có độ chính xác tới microsecond. Một giá trị:

~~~text
2026-02-10T10:04:00.123456Z
~~~

nếu bị serializer làm tròn/cắt về:

~~~text
2026-02-10T10:04:00.123Z
~~~

sẽ không còn cùng vị trí trong `ORDER BY`. Khi nhiều hàng chỉ khác nhau vài microsecond, truy vấn tiếp sau cursor bị mất precision có thể bỏ sót hoặc lặp hàng.

Cần:

- Serialize đủ precision của sort key.
- Decode vào loại thời gian đúng với PostgreSQL.
- Không phụ thuộc timezone mặc định của máy client.
- Giữ nguyên ID số lớn (không chuyển qua kiểu số dễ mất precision).
- Test các cursor có timestamp rất sát nhau.

Giá trị hiển thị trên UI có thể chỉ cần giây, nhưng **giá trị trong cursor phải giữ đủ độ chính xác của phép so sánh trong database**.

## 23. Keyset làm gì khi có INSERT đồng thời?

Trang đầu:

~~~text
[106,105,104]  cursor=(10:04,104)
~~~

Transaction khác chèn ID 107 có timestamp `10:06`, đứng **trước cursor** trong thứ tự DESC. Trang kế tiếp keyset:

~~~sql
WHERE (created_at, id) < (:last_created_at, :last_id)
~~~

tiếp tục ở `103,102,101`. Việc thêm một hàng trước cursor không làm thay đổi ranh giới số khóa, nên không lặp ID 104 như OFFSET.

Nhưng keyset **không bảo đảm mọi lần đọc thuộc cùng một snapshot**:

- Hàng mới chèn với sort key **nằm sau cursor** có thể xuất hiện ở trang sau.
- Hàng chưa xem bị xóa có thể không còn xuất hiện.
- Hàng thay `updated_at`, score, priority hoặc filter có thể di chuyển qua biên, gây lặp/skip.
- Thay đổi quyền hoặc tenant visibility cũng làm tập kết quả thay đổi.

Đây là sự ổn định theo khóa sắp xếp, không phải một danh sách bị đóng băng.

## 24. MVCC và transaction isolation

PostgreSQL sử dụng **MVCC**. Ở mức isolation `READ COMMITTED` mặc định, mỗi statement SELECT nhìn thấy snapshot phù hợp với thời điểm bắt đầu statement. Hai request HTTP khác nhau thường không có chung snapshot.

Một transaction `REPEATABLE READ` có thể giúp các SELECT trong **cùng transaction** thấy một snapshot nhất quán theo quy tắc PostgreSQL:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3;

-- Các SELECT khác trong transaction dùng snapshot nhất quán.

COMMIT;
~~~

Nhưng **không nên giữ transaction PostgreSQL mở trong nhiều phút** chỉ vì user đọc trang 1 rồi mới bấm Next:

- Chiếm connection trong pool.
- Có thể giữ snapshot lâu và cản trở VACUUM.
- Khó mở rộng với nhiều user.
- Khó quản lý khi request timeout hoặc người dùng đóng trình duyệt.

Nếu nghiệp vụ yêu cầu **xuất chính xác một tập cố định**, cân nhắc materialize ID/kết quả, cơ chế export/cursor server-side với vòng đời có giới hạn, hoặc một thiết kế snapshot/version được kiểm soát.

### 24.1. High-water mark có phải snapshot không?

Có thể lưu khóa lớn nhất tại lúc bắt đầu và giới hạn các trang theo ranh giới đó. Điều này giúp ngăn các hàng **mới hơn mốc ban đầu** lọt vào kết quả.

Nhưng hàng có timestamp cũ được chèn trễ, hàng bị sửa sort key, status thay đổi hoặc bản ghi bị xóa vẫn ảnh hưởng. Vì vậy high-water mark chỉ là **một ranh giới**, không phải ảnh chụp toàn bộ dữ liệu tại thời điểm T.

## 25. Sort key thay đổi gây duplicate/skip ngay cả với keyset

Giả sử trang đầu đã hiển thị `A,B,C` theo `updated_at DESC`. Một hàng D chưa hiển thị được cập nhật, khiến `updated_at` của nó mới hơn C. Lúc lấy trang sau theo điều kiện “cũ hơn C”, D không còn thuộc vùng đó và có thể bị bỏ sót.

Ngược lại, B đã xem có thể được sửa để `updated_at` trở nên cũ hơn C; B có thể xuất hiện lại.

Để giảm vấn đề:

1. Ưu tiên sort key tương đối **bất biến** như `created_at` khi đúng nghiệp vụ.
2. Định nghĩa rõ feed đang hiển thị danh sách **live** có thể thay đổi.
3. Nếu cần nhất quán chặt, dùng snapshot/materialization/version.
4. Nếu client cần tránh hiển thị lại cùng ID, có thể lọc ID đã nhận nhưng phải giới hạn bộ nhớ và hiểu đây không phải snapshot.
5. Thử concurrency khi một hàng chuyển qua biên cursor.

Không tuyên bố “keyset luôn không trùng và không thiếu hàng” nếu sort key hoặc tập kết quả có thể biến động.

## 26. Trang số, COUNT(*) và nhảy trực tiếp tới trang N

Keyset thường có giao diện:

~~~text
Tải thêm
Next / Previous
Infinite scroll
~~~

Nó không tự biết vị trí để nhảy thẳng tới “trang 900” nếu chưa có cursor của vùng đó.

OFFSET dễ mô tả vị trí trang 900:

~~~text
offset = (900 - 1) * pageSize
~~~

Đổi lại, việc đọc trang sâu có thể tốn chi phí.

Nếu UI cần tổng số hàng:

~~~sql
SELECT COUNT(*)
FROM pagination_lab.orders
WHERE status = 'paid';
~~~

`COUNT(*)` chính xác có thể tốn công việc đáng kể trên dữ liệu lớn. Nó cũng phản ánh snapshot của câu đếm, có thể khác các trang đọc sau.

`pg_class.reltuples` chỉ là **ước lượng thống kê**, không thay thế COUNT chính xác cho một filter bất kỳ.

### 26.1. Nên chọn cách nào cho từng UI?

| Tình huống | Chiến lược thường phù hợp |
|---|---|
| Feed sự kiện liên tục được chèn | Keyset |
| Infinite scroll rất dài | Keyset |
| API xuất tuần tự theo khóa ổn định | Keyset, hoặc quy trình export chuyên dụng |
| Danh sách đơn hàng mới nhất | Keyset |
| Bảng quản trị vài trăm hàng, nhảy trang số | OFFSET có thể đơn giản hơn |
| Trang dữ liệu giới hạn ở 5–10 trang đầu | OFFSET có thể đủ tốt |
| Báo cáo cần tổng chính xác và nhảy vị trí | OFFSET/thiết kế báo cáo riêng |
| Yêu cầu snapshot bất biến khi duyệt | Cơ chế snapshot/materialization, không chỉ OFFSET hay keyset |

Không có chiến lược tốt nhất cho mọi bài toán. Cần xét UX, quy mô, độ biến động và giới hạn nhất quán.

## 27. Keyset khi JOIN bảng khác

Một API có thể muốn hiển thị đơn cùng tên khách. Nếu JOIN một-nhiều trước khi LIMIT, một đơn có nhiều dòng con có thể chiếm nhiều vị trí, khiến “20 hàng JOIN” không tương đương “20 đơn”.

Một hướng thiết kế khi filter chính thuộc bảng đơn:

~~~sql
-- Mẫu khái niệm cho schema orders/customers thật.
WITH page_orders AS (
    SELECT id, customer_id, created_at
    FROM orders
    WHERE
        (created_at, id)
            < (:last_created_at, :last_id)
    ORDER BY created_at DESC, id DESC
    LIMIT :page_size
)
SELECT
    p.id,
    p.created_at,
    c.name AS customer_name
FROM page_orders AS p
JOIN customers AS c
    ON c.id = p.customer_id
ORDER BY p.created_at DESC, p.id DESC;
~~~

Đoạn này **không chạy trực tiếp trên bảng pagination_lab.orders** vì bảng demo không có `customer_id`; đây là mẫu minh họa kiến trúc.

Cần lưu ý:

- Nếu JOIN làm loại đơn vì thiếu bản ghi liên quan, trang cuối có thể trả ít hơn N đơn.
- Nếu filter phụ thuộc bảng JOIN, phải áp dụng filter đúng **trước khi chọn page**.
- Nếu JOIN tới nhiều dòng chi tiết, có thể nhân hàng; cần xác định đơn vị phân trang.
- Lớp query ngoài vẫn cần `ORDER BY` nếu kết quả phải có thứ tự.
- CTE/subquery có LIMIT ảnh hưởng không gian tối ưu hóa, nên đo kế hoạch thực.

Không áp dụng công thức “LIMIT trước mọi JOIN” một cách máy móc.

## 28. Các lỗi thường gặp

### Lỗi 1 — Không có ORDER BY

Thứ tự hàng không được bảo đảm. **Khắc phục:** xác định ORDER BY phù hợp nghiệp vụ.

### Lỗi 2 — Chỉ sort theo created_at

Hàng trùng timestamp có thể bị bỏ sót khi seek. **Khắc phục:** thêm tie-breaker duy nhất `id` vào ORDER BY và cursor.

### Lỗi 3 — DESC nhưng dùng dấu >

Lấy hàng trước cursor, không phải sau. **Khắc phục:** với tất cả sort key DESC, dùng `<` cho Next.

### Lỗi 4 — Mixed ASC/DESC nhưng dùng tuple <

Predicate có thể trả sai thứ tự. **Khắc phục:** dùng so sánh lexicographic đúng chiều từng cột.

### Lỗi 5 — Không xử lý NULL

So sánh tuple với NULL trả UNKNOWN, bỏ qua một phần danh sách. **Khắc phục:** thiết kế nhánh NULLS FIRST/LAST hoặc dùng khóa NOT NULL.

### Lỗi 6 — Cursor thiếu một cột trong ORDER BY

Không phân biệt được những hàng trùng phần khóa. **Khắc phục:** mang đủ các cột, gồm khóa phụ duy nhất.

### Lỗi 7 — Lấy cursor từ hàng N+1

Hàng thứ N+1 chưa được trả sẽ bị nhảy qua. **Khắc phục:** cursor từ hàng N đã trả.

### Lỗi 8 — Cắt timestamp thành milliseconds

Ranh giới seek lệch so với giá trị microsecond của DB. **Khắc phục:** giữ đủ precision.

### Lỗi 9 — Đổi filter/sort nhưng giữ cursor cũ

Cursor không còn thuộc cùng tập dữ liệu. **Khắc phục:** reset/từ chối cursor.

### Lỗi 10 — Tin Base64 là bảo mật

Client có thể sửa nội dung token. **Khắc phục:** chữ ký/verify hoặc state server-side, authorization luôn ở server.

### Lỗi 11 — Tưởng keyset là snapshot

INSERT cũ, UPDATE, DELETE vẫn ảnh hưởng. **Khắc phục:** định nghĩa live semantics hoặc snapshot riêng.

### Lỗi 12 — Sắp theo updated_at nhưng giả định khóa bất biến

Hàng di chuyển qua biên cursor. **Khắc phục:** chấp nhận semantics đó hoặc thiết kế version/snapshot.

### Lỗi 13 — Không có index phù hợp

Keyset có thể vẫn scan/sort lớn. **Khắc phục:** index theo filter và ORDER BY rồi đo EXPLAIN.

### Lỗi 14 — Dùng COUNT mỗi lần cuộn

Tăng tải không cần thiết cho feed chỉ cần có trang sau. **Khắc phục:** có thể dùng LIMIT N+1.

### Lỗi 15 — OFFSET rất sâu trên bảng lớn

Engine phải đi qua nhiều hàng trước. **Khắc phục:** keyset cho luồng tuần tự hoặc giới hạn độ sâu.

### Lỗi 16 — Không giới hạn pageSize

Một request có thể yêu cầu quá nhiều hàng. **Khắc phục:** kiểm tra giới hạn tại API.

### Lỗi 17 — Dùng ID làm timestamp tuyệt đối

Sequence và transaction không bảo đảm ID lớn luôn commit muộn hơn. **Khắc phục:** sort theo tiêu chí nghiệp vụ.

### Lỗi 18 — JOIN làm nhân hàng trước LIMIT

Một thực thể chiếm nhiều hàng trong trang. **Khắc phục:** xác định đơn vị phân trang và vị trí áp dụng LIMIT đúng.

## 29. Checklist triển khai endpoint keyset

**Bước 1:** Xác định thực thể được phân trang: đơn, khách hàng, sự kiện hay kết quả tổng hợp.

**Bước 2:** Xác định filter bắt buộc và phạm vi quyền/tenant từ server.

**Bước 3:** Chọn thứ tự phản ánh UI: mới nhất, ưu tiên, giá trị, v.v.

**Bước 4:** Thêm tie-breaker duy nhất, thường là primary key.

**Bước 5:** Xử lý NULL và chiều ASC/DESC của từng sort key.

**Bước 6:** Viết query trang đầu và query next có predicate seek tương ứng.

**Bước 7:** Tạo index B-tree theo filter và ORDER BY nếu workload cần.

**Bước 8:** Fetch N+1, trả N và tạo cursor từ hàng cuối đã trả.

**Bước 9:** Serialize đủ precision; ký/verify token và ràng buộc filter/sort.

**Bước 10:** Hỗ trợ Previous với query ngược và đảo thứ tự kết quả.

**Bước 11:** Xác định hành vi khi INSERT/UPDATE/DELETE giữa các request.

**Bước 12:** Đo `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện, bao gồm các trang sâu và các filter phổ biến.

## 30. Bài tập tự luyện

### Bài 1 — OFFSET trang 3

Viết SQL lấy trang 3 với pageSize 2 theo `created_at DESC,id DESC`.

**Gợi ý:** `LIMIT 2 OFFSET 4`.

### Bài 2 — Tie-breaker

Vì sao `ORDER BY created_at DESC` không đủ khi ID 103,104,105 có cùng timestamp?

**Gợi ý:** thứ tự giữa các hàng bằng timestamp không xác định.

### Bài 3 — Next cursor

Trang 1 gồm `106,105,104`. Viết query lấy ba hàng sau ID 104.

**Gợi ý:** `(created_at,id) < (TIMESTAMPTZ '2026-02-10 10:04:00+00',104)`.

### Bài 4 — ASC

Với `ORDER BY created_at ASC,id ASC`, sau cursor ID 102 nên dùng `<` hay `>`?

**Gợi ý:** `>`.

### Bài 5 — ID-only

Viết keyset theo `ORDER BY id DESC` với cursor ID 104.

**Gợi ý:** `WHERE id < 104`.

### Bài 6 — Mixed sort

Bảng tasks sắp `priority DESC,task_id ASC`. Viết predicate sau `(3,11)`.

**Gợi ý:** `priority < 3 OR (priority=3 AND task_id>11)`.

### Bài 7 — NULLS LAST

Cursor shipment `(shipped_at=NULL,shipment_id=4)`. Query tiếp theo nên lọc gì?

**Gợi ý:** `shipped_at IS NULL AND shipment_id<4`.

### Bài 8 — Previous

Với trang hiện tại `103,102,101`, lấy ba hàng ngay trước ID 103 và trả theo DESC.

**Gợi ý:** tuple `>`, sort ASC trong subquery, sort DESC ngoài.

### Bài 9 — Index

Đề xuất index cho `WHERE status='paid' ORDER BY created_at DESC,id DESC`.

**Gợi ý:** `(status,created_at DESC,id DESC)` hoặc partial index dành cho paid.

### Bài 10 — OFFSET dưới concurrent INSERT

Thêm ID 107 vào đầu sau khi client đã nhận `106,105,104`. OFFSET 3 sẽ trả ID nào?

**Gợi ý:** `104,103,102`; lặp ID 104.

### Bài 11 — Keyset dưới concurrent INSERT

Trong cùng tình huống, keyset sau ID 104 tiếp tục thế nào?

**Gợi ý:** không phụ thuộc vị trí 3; tiếp tục `103,102,101`.

### Bài 12 — Sort key thay đổi

Một hàng có `updated_at` mới được đưa từ trang sau lên trước cursor. Keyset có bảo đảm không bỏ sót không?

**Gợi ý:** không.

### Bài 13 — N+1

API pageSize=20 fetch 21 hàng. Cursor trang sau lấy từ hàng thứ 20 hay 21?

**Gợi ý:** hàng thứ 20 đã trả.

### Bài 14 — Precision

Cursor lưu milliseconds thay vì microseconds. Tại sao có thể sai?

**Gợi ý:** giá trị so sánh không còn khớp DB.

### Bài 15 — Bảo mật cursor

Nếu token Base64 có tenant ID, server có thể tin nó để phân quyền không?

**Gợi ý:** không; verify token và authorization từ session hiện tại.

### Bài 16 — Benchmark

Dùng `generate_series` theo mục 17 và `EXPLAIN (ANALYZE, BUFFERS)` so sánh OFFSET 90000 với keyset cùng vị trí.

**Gợi ý:** so số hàng/index entries thực sự phải đi qua và thời gian.

### Bài 17 — COUNT(*)

`hasNextPage` từ N+1 có tự cho biết tổng số trang không?

**Gợi ý:** không; tổng số kết quả cần cách tính riêng.

### Bài 18 — Snapshot

High-water mark có bảo đảm không có hàng mới với timestamp cũ xuất hiện ở trang sau không?

**Gợi ý:** không; nó không phải snapshot toàn bộ.

### Bài 19 — Giao diện trang số

Bảng quản trị 200 hàng cho phép nhảy thẳng trang 5. OFFSET hay keyset đơn giản hơn?

**Gợi ý:** OFFSET có thể phù hợp nếu chi phí nhỏ và có ORDER BY ổn định.

### Bài 20 — Thiết kế API

Đề xuất endpoint `GET /orders` có status filter, sort newest, maxPageSize 100, cursor ký HMAC và nút Previous.

**Gợi ý:** định nghĩa khóa, query first/next/previous, N+1, cursor version, precision, filter consistency và quyền.

## 31. Tổng kết

- **OFFSET** phân trang theo **vị trí hàng** bằng `LIMIT ... OFFSET ...`, dễ đánh số trang nhưng có thể tốn công việc khi bỏ qua hàng rất sâu.
- **Keyset** phân trang theo **giá trị khóa**, tránh lệ thuộc vào số lượng hàng đứng trước và có thể tận dụng index để tìm vùng tiếp theo hiệu quả.
- Cả hai cần `ORDER BY` ổn định. Với keyset, phải có **tie-breaker duy nhất** và đưa đầy đủ khóa vào cursor.
- Với `ORDER BY created_at DESC,id DESC`, trang tiếp theo dùng `WHERE (created_at,id) < (:created_at,:id)`; với hai cột ASC dùng `>`.
- **Mixed ASC/DESC**, **NULLS FIRST/LAST** và **Previous** yêu cầu predicate và thứ tự truy vấn tương ứng.
- Filter, sort, tenant và quyền truy cập phải nhất quán giữa các trang; cursor token cần giữ precision và được kiểm tra toàn vẹn.
- Chọn composite B-tree index theo truy vấn thực tế; dùng `EXPLAIN (ANALYZE, BUFFERS)` để kiểm tra.
- Fetch **N+1** để xác định có trang sau, nhưng cursor lấy từ **hàng cuối thật sự trả về**.
- Keyset **không tạo snapshot**. Hàng bị chèn ở vị trí cũ, sửa sort key hoặc xóa vẫn có thể thay đổi những trang sau.
- OFFSET vẫn hữu ích cho bảng nhỏ, trang số và nhảy ngẫu nhiên. Keyset thường thích hợp hơn cho feed lớn và infinite scroll.

Điều quan trọng không phải áp dụng một kỹ thuật cho mọi truy vấn, mà là **xác định đúng thứ tự, ranh giới, chi phí và mức nhất quán ứng dụng cần cam kết**. Khi các yếu tố đó rõ ràng, PostgreSQL cho phép thiết kế phân trang vừa dễ hiểu, vừa có khả năng mở rộng và tránh các lỗi lặp/bỏ sót do cách dùng OFFSET không phù hợp.
