# Tài liệu hóa giả định, câu lệnh, kết quả mong đợi và giới hạn khi làm việc với SQL

Một truy vấn SQL có thể chạy đúng trên máy của người viết nhưng thất bại khi chuyển sang môi trường khác. Nguyên nhân có thể là dữ liệu khác, phiên bản DBMS khác, timezone khác, tham số khác, quyền truy cập khác hoặc một giả định nghiệp vụ chưa được ghi lại. Ngay cả khi truy vấn chạy thành công, người đọc vẫn có thể hiểu sai kết quả nếu không biết đơn vị tiền, cách lọc trạng thái, quy tắc NULL, thứ tự hàng và giới hạn dữ liệu.

**Tài liệu hóa SQL tốt phải giúp người khác hiểu vì sao câu lệnh tồn tại, điều kiện nào làm nó đúng, cách chạy lại và kết quả nào được xem là đúng.** Tài liệu cần nêu rõ giả định, schema và dữ liệu đầu vào, dialect/phiên bản, tham số, thứ tự thực thi, transaction, output contract, kết quả mong đợi, lỗi có thể gặp và giới hạn đã biết.

Bài học thuộc **Database SQL → Thực hành tổng hợp → Tài liệu hóa giả định, câu lệnh, kết quả mong đợi và giới hạn**. Nội dung trình bày phương pháp viết tài liệu có thể kiểm chứng, cách phân biệt sự thật với giả định, cách ghi câu lệnh và expected result, cách quản lý thay đổi, và một ví dụ thực hành hoàn chỉnh.

## 1. Vì sao phải tài liệu hóa SQL?

SQL thường không tồn tại độc lập. Nó phụ thuộc vào schema, dữ liệu, quyền, transaction, phiên bản DBMS và quy tắc nghiệp vụ. Một câu lệnh như:

~~~sql
SELECT customer_id, SUM(amount)
FROM orders
GROUP BY customer_id;
~~~

chưa đủ thông tin để người khác biết:
- Chỉ tính đơn đã xác nhận hay tính cả đơn nháp và đơn hủy?
- amount là tổng trước hay sau giảm giá?
- Tiền đang dùng đơn vị VND, USD hay đơn vị nhỏ nhất?
- Có tính đơn hoàn tiền không?
- Khoảng thời gian lọc theo UTC hay giờ địa phương?
- Khách hàng không có đơn có cần xuất hiện với tổng 0 không?
- Có yêu cầu thứ tự kết quả không?
- Có thể chạy trên PostgreSQL, MySQL hay SQL Server?
- Người chạy cần role và quyền nào?
- Kết quả nào xác nhận câu lệnh đang hoạt động đúng?

Nếu các câu trả lời chỉ nằm trong trí nhớ của tác giả, truy vấn rất dễ bị sử dụng sai khi tác giả rời dự án hoặc nghiệp vụ thay đổi.

Tài liệu hóa hỗ trợ:

- **Tái lập:** người khác có thể chạy lại cùng câu lệnh với cùng điều kiện.
- **Kiểm chứng:** expected result và invariant giúp nhận biết kết quả sai.
- **Bảo trì:** biết query phụ thuộc vào bảng/cột và quyết định nghiệp vụ nào.
- **Review:** reviewer có thể xem tác động, rủi ro và giới hạn.
- **Vận hành:** người trực hệ thống biết cách chạy, quan sát, dừng và xử lý lỗi.
- **Audit:** có thể truy lại phiên bản SQL, schema, tham số và bằng chứng thực thi.
- **Chuyển giao:** kiến thức không phụ thuộc một cá nhân.

Tài liệu không cần ghi lại mọi điều hiển nhiên của SQL. Nó cần ghi những điều người đọc không thể suy ra an toàn chỉ từ câu lệnh.

## 2. Một tài liệu SQL nên trả lời những câu hỏi nào?

Một hồ sơ SQL có thể được tổ chức theo các nhóm sau:

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| Mục đích | Truy vấn giải quyết nhu cầu nghiệp vụ nào? |
| Phạm vi | Bao gồm và loại trừ loại dữ liệu nào? |
| Giả định | Điều kiện nào phải đúng để kết quả có ý nghĩa? |
| Nguồn dữ liệu | Đọc/ghi bảng, view, function nào? |
| Môi trường | DBMS, version, schema, timezone, collation? |
| Tham số | Tên, kiểu, đơn vị, giá trị hợp lệ và mặc định? |
| Câu lệnh | SQL chính xác và thứ tự chạy? |
| Transaction | Cần cùng connection, commit/rollback ra sao? |
| Đầu ra | Tên cột, kiểu, NULL, đơn vị và thứ tự? |
| Kết quả mong đợi | Fixture nào và output chính xác là gì? |
| Kiểm tra | Invariant, row count, đối soát nào phải đúng? |
| Lỗi | Lỗi dự kiến và cách xử lý? |
| Giới hạn | Quy mô, độ sâu, thời gian, quyền và dialect? |
| Vận hành | Cách chạy, giám sát, dừng và phục hồi? |
| Lịch sử | Ai đổi, đổi gì, từ phiên bản nào và vì sao? |

Không phải mọi truy vấn cần một tài liệu dài như nhau. Một SELECT nhỏ có thể chỉ cần mục đích, tham số, output và ví dụ. Một migration, báo cáo tài chính hoặc job ghi dữ liệu cần nhiều chi tiết hơn.

## 3. Phân biệt giả định, sự thật và quyết định

Đây là phần cốt lõi. Một tài liệu dễ gây hiểu nhầm nếu viết giả định như thể đó là sự thật đã được xác nhận.

### 3.1. Sự thật đã xác nhận

Ví dụ:
- Bảng orders có khóa chính id.
- orders.customer_id tham chiếu customers.id.
- amount có kiểu NUMERIC(14,2).
- Truy vấn được chạy bằng PostgreSQL 16 trong môi trường staging.

Sự thật nên có nguồn xác nhận: schema migration, catalog, cấu hình triển khai, hợp đồng API hoặc người sở hữu nghiệp vụ.

### 3.2. Giả định cần được xác nhận

Ví dụ:
- Mỗi đơn CONFIRMED phải có ít nhất một dòng hàng.
- Đơn CANCELLED không được tính doanh thu.
- Tất cả amount trong báo cáo đều cùng một currency.
- Timestamp được lưu ở UTC.
- Dữ liệu đã backfill đầy đủ trước khi chạy báo cáo.

Nếu chưa có bằng chứng, ghi rõ đây là giả định và nêu hậu quả nếu giả định sai.

### 3.3. Quyết định nghiệp vụ

Ví dụ:
- Doanh thu ghi nhận tại thời điểm đơn chuyển sang CONFIRMED.
- Giao dịch hoàn tiền được trừ khỏi số đã thanh toán.
- Đơn hủy không xuất hiện trong báo cáo doanh thu.
- Báo cáo dùng ngày UTC, không dùng ngày địa phương của người dùng.

Quyết định nghiệp vụ nên trỏ tới tài liệu/spec/ticket hoặc người phê duyệt. SQL chỉ triển khai quyết định đó; câu SQL tự nó không phải nguồn thẩm quyền định nghĩa nghiệp vụ.

### 3.4. Bảng ghi nhận giả định

| ID | Nội dung | Loại | Nguồn/trạng thái | Ảnh hưởng nếu sai |
| --- | --- | --- | --- | --- |
| A-01 | Chỉ tính đơn CONFIRMED | Quyết định nghiệp vụ | Spec REV-12 | Doanh thu sai |
| A-02 | Amount dùng cùng currency | Giả định | Chờ xác nhận | Không thể cộng khác tiền |
| A-03 | created_at lưu UTC | Sự thật đã xác nhận | Schema/config | Lệch ngày báo cáo |
| A-04 | Đơn CONFIRMED có ít nhất một dòng | Giả định | Chưa xác nhận | Đơn không dòng bị loại |

Không ghi “đã xác nhận” nếu chỉ mới suy luận từ một vài hàng dữ liệu mẫu.

## 4. Xác định phạm vi và mục đích truy vấn

Mục đích nên mô tả hành vi có thể kiểm chứng, không chỉ nói tên kỹ thuật.

Mô tả yếu:

> Truy vấn doanh thu khách hàng.

Mô tả rõ hơn:

> Trả về tổng giá trị các đơn có trạng thái CONFIRMED theo từng khách hàng trong khoảng thời gian đầu vào. Khách hàng không có đơn phù hợp vẫn xuất hiện với tổng 0. Mỗi khách hàng có đúng một hàng. Giá trị là VND, scale hai chữ số.

Một mô tả tốt nên nêu:
- Ai sử dụng kết quả.
- Câu hỏi nghiệp vụ cần trả lời.
- Phạm vi dữ liệu.
- Quy tắc bao gồm/loại trừ.
- Mức tổng hợp: một hàng mỗi khách hàng, đơn, ngày hay sản phẩm.
- Thời điểm dữ liệu được chụp.
- Có phải truy vấn đọc hay có ghi dữ liệu.

### 4.1. Ghi rõ ngoài phạm vi

Ví dụ:
- Không quy đổi ngoại tệ.
- Không tính đơn hủy.
- Không tính thuế nếu thuế được lưu riêng.
- Không bao gồm dữ liệu archive.
- Không đảm bảo dữ liệu mới nhất nếu đọc từ replica có độ trễ.

Ghi ngoài phạm vi giúp ngăn consumer diễn giải kết quả vượt quá ý nghĩa thật.

## 5. Ghi môi trường và dialect

SQL là ngôn ngữ có nhiều dialect. Tài liệu cần ghi rõ nơi câu lệnh được hỗ trợ và những khác biệt có liên quan.

Các thông tin nên ghi:
- DBMS: PostgreSQL, MySQL, SQL Server, Oracle, SQLite...
- Phiên bản cụ thể hoặc dải version được hỗ trợ.
- Driver/ORM và version nếu câu lệnh chạy qua ứng dụng.
- Schema/database/catalog.
- Encoding và collation nếu xử lý chuỗi.
- Timezone session và timezone nghiệp vụ.
- Isolation level/autocommit nếu có transaction.
- Role/quyền cần thiết.
- Extension, function hoặc feature được bật.
- Cấu hình ảnh hưởng recursion, timeout hoặc query planner.

Ví dụ:

| Thuộc tính | Giá trị ví dụ |
| --- | --- |
| DBMS | PostgreSQL |
| Version | 16.x |
| Schema | public |
| Client | psql / psycopg 3 |
| Session timezone | UTC |
| Encoding | UTF-8 |
| Isolation | READ COMMITTED |
| Transaction mode | Autocommit cho SELECT độc lập |
| Role | report_reader |
| Extension | Không yêu cầu |

Đây là thông tin minh họa, không phải cấu hình mặc định cho mọi dự án.

### 5.1. Không ghi thông tin bí mật

Không đưa vào tài liệu:
- Password.
- Access token.
- Connection string có credential.
- Private key.
- Dữ liệu cá nhân không cần thiết.
- Giá trị production nhạy cảm.

Có thể ghi tên biến môi trường như `DATABASE_URL`, tên secret trong secret manager hoặc tên role; không ghi giá trị bí mật.

## 6. Mô tả schema và nguồn dữ liệu

Người đọc cần biết truy vấn phụ thuộc vào đối tượng nào và quan hệ giữa chúng.

Một bảng mô tả:

| Bảng | Cột sử dụng | Vai trò | Khóa/quan hệ |
| --- | --- | --- | --- |
| customers | id, name | Khách hàng | PK id |
| orders | id, customer_id, status, created_at | Header đơn | PK id, FK customer_id |
| order_lines | order_id, quantity, unit_price | Dòng hàng | FK order_id |

Nên nêu:
- PK/FK và cardinality.
- Unique constraints.
- Nullable columns.
- Kiểu dữ liệu quan trọng.
- Soft-delete convention.
- Status enum/domain.
- Currency và đơn vị.
- Partitioning/retention nếu có.
- View hoặc derived table nào đang được sử dụng.

Không nhất thiết copy toàn bộ DDL nếu schema lớn. Có thể trỏ tới migration/version hoặc tài liệu schema có version, nhưng phải chỉ ra phần liên quan.

### 6.1. Ghi cardinality rõ ràng

Ví dụ:
- Một customer có 0-n orders.
- Một order có 1-n order_lines.
- Một order có 0-n payments.
- Mỗi payment thuộc đúng một order.

Cardinality quyết định JOIN có thể nhân bản hàng hay không. Đây là một trong những giả định quan trọng nhất khi viết truy vấn tổng hợp.

## 7. Tài liệu hóa tham số

Mỗi tham số nên có tên, kiểu, đơn vị, miền hợp lệ, default và cách xử lý NULL.

| Tham số | Kiểu | Ý nghĩa | Hợp lệ | Default |
| --- | --- | --- | --- | --- |
| start_at | timestamp | Đầu khoảng thời gian | Bắt buộc | Không có |
| end_at | timestamp | Cuối khoảng thời gian | Lớn hơn start_at | Không có |
| status | varchar | Trạng thái đơn | CONFIRMED | CONFIRMED |
| customer_id | bigint | Lọc một khách | Số dương hoặc NULL | NULL = tất cả |

Cần nói rõ khoảng thời gian là inclusive/exclusive. Một quy ước phổ biến là khoảng nửa mở:

~~~sql
WHERE created_at >= :start_at
  AND created_at < :end_at
~~~

Nếu start_at là đầu ngày và end_at là đầu ngày kế tiếp, cách này tránh phải đoán độ chính xác của timestamp cuối ngày.

### 7.1. Bind parameter, không nối chuỗi

Nên dùng parameter binding:

~~~sql
SELECT id, status
FROM orders
WHERE customer_id = :customer_id;
~~~

Placeholder cụ thể tùy driver. Không nối input người dùng trực tiếp vào SQL. Parameter binding thường dùng cho **value**; tên bảng, tên cột và hướng ORDER BY thường là identifier/syntax, cần whitelist hoặc ánh xạ từ lựa chọn cho phép.

### 7.2. Ghi giá trị test riêng với giá trị production

Tài liệu có thể ghi:
- Giá trị mẫu dùng trong test.
- Ví dụ lệnh chạy với placeholder.
- Giá trị production được cấp từ cấu hình runtime.

Không sao chép PII hoặc dữ liệu thanh toán production vào ví dụ tài liệu.

## 8. Ghi câu lệnh chính xác và thứ tự thực thi

Đừng chỉ mô tả “chạy query báo cáo”. Ghi SQL nguyên văn hoặc tham chiếu tới file SQL có version/hash.

Với workflow nhiều câu lệnh, ghi thứ tự và dependency:

1. Kiểm tra tham số.
2. Bắt đầu transaction nếu cần.
3. Đọc/khóa dữ liệu.
4. Chạy câu lệnh cập nhật hoặc tổng hợp.
5. Kiểm tra số hàng và invariant.
6. Commit hoặc rollback.
7. Ghi nhận kết quả và release connection.

Ví dụ tài liệu cho một câu SELECT:

~~~sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COUNT(o.id) AS confirmed_order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.id
 AND o.status = 'CONFIRMED'
GROUP BY c.id, c.name
ORDER BY c.id;
~~~

Ghi rõ vì sao điều kiện status nằm trong ON: LEFT JOIN vẫn giữ khách không có đơn CONFIRMED. Nếu chuyển điều kiện đó xuống WHERE, kết quả sẽ loại khách không có đơn và thay đổi semantics.

### 8.1. SQL nhiều bước

Nếu nhiều statement phụ thuộc nhau, tài liệu phải nói rõ:
- Chạy trên cùng connection/session hay không.
- Có transaction tường minh không.
- Autocommit bật/tắt.
- Statement nào phải chạy trước.
- Statement nào được phép retry.
- Điều kiện commit.
- Khi lỗi thì rollback phần nào.
- Có side effect ngoài DB không.

### 8.2. Dynamic SQL

Nếu câu lệnh được sinh động, ghi:
- Các phần SQL nào thay đổi.
- Các identifier được phép.
- Cách whitelist/escape identifier.
- Value được bind như thế nào.
- Một ví dụ SQL sau khi render.
- Các hình dạng query có thể sinh.
- Cách log fingerprint mà không lộ dữ liệu nhạy cảm.

Không chỉ ghi template code rồi giả định người đọc biết SQL cuối cùng trông ra sao.

## 9. Kết quả mong đợi phải cụ thể

Expected result nên nêu:
- Số hàng.
- Tên và kiểu cột.
- Các hàng mẫu hoặc toàn bộ hàng với fixture nhỏ.
- Thứ tự nếu có contract.
- NULL/default.
- Đơn vị và rounding.
- Invariant liên quan.
- Kết quả lỗi nếu input không hợp lệ.

Mô tả yếu:

> Query trả về doanh thu đúng.

Mô tả có thể kiểm chứng:

> Với fixture ở mục 10, query trả đúng 3 hàng theo customer_id tăng dần. An có 125.00, Bình có 120.00, Chi có 0.00. Cột revenue có kiểu NUMERIC và không NULL. Đơn CONFIRMED được tính; CANCELLED và DRAFT bị loại.

### 9.1. Không tạo thứ tự giả

Nếu query không có ORDER BY, không ghi expected như một danh sách có thứ tự bắt buộc. Có thể ghi “3 hàng, so sánh theo customer_id” hoặc bổ sung ORDER BY vào query nếu thứ tự là yêu cầu.

### 9.2. Expected result khác expected error

Đối với input sai, kết quả mong đợi có thể là:
- Validation error ở ứng dụng trước khi gửi SQL.
- Constraint violation từ DBMS.
- 0 hàng được cập nhật.
- Timeout theo ngưỡng.
- Permission denied.

Ghi rõ lỗi nào được xem là bình thường và tầng nào chịu trách nhiệm xử lý. Không nuốt lỗi rồi mô tả như kết quả thành công.

## 10. Ví dụ xuyên suốt: báo cáo tổng tiền theo khách hàng

Ta dùng PostgreSQL làm dialect minh họa. Đây là schema nhỏ, có fixture cố định và output cụ thể để người khác chạy lại.

### 10.1. Mục đích

Trả về tổng giá trị các đơn CONFIRMED theo từng khách hàng. Khách không có đơn CONFIRMED vẫn xuất hiện với tổng 0. Mỗi khách hàng có đúng một hàng. Giá trị tiền dùng đơn vị mẫu và hai chữ số thập phân.

### 10.2. Giả định và quyết định

| ID | Nội dung | Loại |
| --- | --- | --- |
| A-01 | Chỉ tính đơn có status CONFIRMED | Quyết định ví dụ |
| A-02 | DRAFT và CANCELLED không tính | Quyết định ví dụ |
| A-03 | Mỗi đơn được tính bằng tổng quantity × unit_price của các dòng | Giả định mô hình |
| A-04 | Mọi giá trong fixture cùng một currency | Giả định ví dụ |
| A-05 | Đơn CONFIRMED phải có ít nhất một dòng hàng | Giả định cần xác nhận trong hệ thống thật |
| A-06 | Không áp dụng thuế, vận chuyển hoặc chiết khấu trong ví dụ | Giới hạn ví dụ |

### 10.3. Schema và fixture

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0)
);

INSERT INTO customers (id, name) VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO orders (id, customer_id, status, created_at) VALUES
    (101, 1, 'CONFIRMED', '2026-01-05 10:00:00+00'),
    (102, 1, 'CANCELLED', '2026-01-10 10:00:00+00'),
    (103, 2, 'CONFIRMED', '2026-01-12 10:00:00+00'),
    (104, 3, 'DRAFT',     '2026-02-01 10:00:00+00');

INSERT INTO order_lines (id, order_id, quantity, unit_price) VALUES
    (1001, 101, 2, 50.00),
    (1002, 101, 1, 25.00),
    (1003, 102, 1, 80.00),
    (1004, 103, 3, 40.00),
    (1005, 104, 2, 30.00);
~~~

### 10.4. Tính expected bằng tay

- Đơn 101 của An: 2 × 50.00 + 1 × 25.00 = 125.00.
- Đơn 102 bị CANCELLED: không tính.
- Đơn 103 của Bình: 3 × 40.00 = 120.00.
- Đơn 104 của Chi ở trạng thái DRAFT: không tính.
- Chi vẫn phải xuất hiện vì báo cáo giữ mọi khách hàng, tổng bằng 0.

Expected:

| customer_id | customer_name | revenue |
| ---: | --- | ---: |
| 1 | An | 125.00 |
| 2 | Binh | 120.00 |
| 3 | Chi | 0.00 |

Số hàng kỳ vọng: 3. Tổng revenue kỳ vọng: 245.00.

### 10.5. Câu SQL

~~~sql
WITH order_totals AS (
    SELECT
        o.id AS order_id,
        o.customer_id,
        SUM(ol.quantity * ol.unit_price) AS order_total
    FROM orders AS o
    JOIN order_lines AS ol
      ON ol.order_id = o.id
    WHERE o.status = 'CONFIRMED'
    GROUP BY o.id, o.customer_id
)
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COALESCE(SUM(ot.order_total), 0)::NUMERIC(14,2) AS revenue
FROM customers AS c
LEFT JOIN order_totals AS ot
  ON ot.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;
~~~

### 10.6. Vì sao viết theo hai tầng?

CTE order_totals tính tổng từng đơn trước. SELECT ngoài cộng các đơn theo khách hàng. LEFT JOIN giữ khách không có đơn phù hợp.

Cách này làm rõ grain của mỗi bước:
- order_totals: một hàng mỗi đơn CONFIRMED có ít nhất một order line.
- SELECT cuối: một hàng mỗi customer.

Nếu JOIN trực tiếp nhiều bảng 1-n khác (ví dụ order_lines và payments) rồi SUM order line, một đơn có nhiều payment có thể nhân bản dòng hàng. Tách aggregate theo grain giúp tránh lỗi đó.

### 10.7. Kiểm tra bổ sung

Kiểm tra số hàng:

~~~sql
SELECT COUNT(*) AS result_rows
FROM customers;
~~~

Vì truy vấn chính phải trả một hàng mỗi customer, expected row count bằng số customer trong fixture: 3.

Kiểm tra tổng:

~~~sql
WITH result AS (
    WITH order_totals AS (
        SELECT
            o.id AS order_id,
            o.customer_id,
            SUM(ol.quantity * ol.unit_price) AS order_total
        FROM orders o
        JOIN order_lines ol ON ol.order_id = o.id
        WHERE o.status = 'CONFIRMED'
        GROUP BY o.id, o.customer_id
    )
    SELECT
        c.id,
        COALESCE(SUM(ot.order_total), 0) AS revenue
    FROM customers c
    LEFT JOIN order_totals ot ON ot.customer_id = c.id
    GROUP BY c.id
)
SELECT SUM(revenue) AS total_revenue
FROM result;
~~~

Expected total_revenue = 245.00. Đây là assertion phụ, không thay so sánh từng khách hàng vì tổng đúng vẫn có thể che việc phân bổ sai giữa các khách.

### 10.8. Output contract

| Cột | Kiểu kỳ vọng | NULL? | Ý nghĩa |
| --- | --- | --- | --- |
| customer_id | BIGINT | Không | Khóa khách |
| customer_name | VARCHAR(100) | Không | Tên hiển thị |
| revenue | NUMERIC(14,2) | Không | Tổng đơn CONFIRMED |

Thứ tự output: customer_id tăng dần. Currency: giả định một currency trong fixture; hệ thống thật phải có quy tắc currency rõ ràng.

## 11. Ghi rõ giới hạn của câu lệnh

Giới hạn không chỉ là giới hạn kỹ thuật. Nó có thể là ranh giới nghiệp vụ, dữ liệu hoặc vận hành.

Các nhóm thường gặp:

### 11.1. Giới hạn nghiệp vụ

- Chỉ tính một tập status.
- Không xử lý multi-currency.
- Không tính thuế/phí/voucher.
- Không bao gồm dữ liệu archive.
- Không hỗ trợ hoàn tiền hoặc chargeback.
- Không hỗ trợ đơn được chỉnh sửa hồi tố.

### 11.2. Giới hạn dữ liệu

- Giả định FK đã được enforce.
- Giả định dữ liệu cũ đã backfill.
- Giả định không có orphan.
- Giả định mọi đơn CONFIRMED có dòng hàng.
- Giả định quantity và unit_price hợp lệ.

### 11.3. Giới hạn kỹ thuật

- Chỉ chạy trên PostgreSQL 16+.
- Cần quyền SELECT trên các bảng nguồn.
- Cần index theo khóa JOIN và bộ lọc.
- Không hỗ trợ dynamic schema name.
- Không chạy trong transaction read-only nếu truy vấn cần ghi.
- Timeout hoặc giới hạn số hàng.
- Có thể không dùng được trên replica có lag nếu yêu cầu dữ liệu tức thời.

### 11.4. Giới hạn hiệu năng

Ghi dataset đã đo, môi trường, latency, concurrency và ngưỡng chấp nhận. Ví dụ:
- Dataset: 5 triệu orders, 20 triệu order_lines.
- Môi trường: staging cấu hình tương đương production.
- p95: mục tiêu dưới 500 ms.
- Query timeout: 3 giây.
- Index kỳ vọng: orders(status, customer_id), order_lines(order_id).

Đây chỉ là ví dụ. Không khẳng định index bắt buộc nếu chưa kiểm tra query plan trên workload thật.

### 11.5. Giới hạn kết quả

- Không có ORDER BY thì không cam kết thứ tự.
- SUM có thể trả NULL khi không có input; cần COALESCE nếu contract yêu cầu 0.
- LEFT JOIN và điều kiện ở ON/WHERE ảnh hưởng việc giữ hàng không có quan hệ.
- Decimal rounding phải theo quy tắc được công bố.
- Replica có thể trả dữ liệu trễ.
- Pagination có thể bỏ/nhân bản hàng nếu sort key không ổn định khi dữ liệu thay đổi.

Ghi giới hạn bằng câu có thể kiểm chứng, tránh những câu mơ hồ như “query có thể chậm khi dữ liệu lớn”.

## 12. Ghi expected error và hành vi khi thất bại

Tài liệu vận hành cần nói câu lệnh có thể thất bại thế nào.

Ví dụ:

| Tình huống | Hành vi mong đợi | Xử lý |
| --- | --- | --- |
| start_at >= end_at | Validation error | Không gửi SQL |
| Thiếu quyền SELECT | Permission error | Cấp role đúng qua quy trình |
| Timeout | Query bị hủy theo policy | Ghi log, điều tra plan |
| Schema version không phù hợp | Migration/version check fail | Không chạy query |
| Connection lost | Kết quả có thể không xác định với write | Reconcile theo operation ID |
| Constraint violation | Statement/transaction fail theo DBMS | Rollback và báo lỗi |

Với SELECT thuần, mất kết nối thường khiến client không nhận kết quả; với câu ghi, mất kết nối khi COMMIT có thể tạo outcome không xác định. Không khuyến khích retry mù quáng một thao tác ghi không idempotent.

### 12.1. SQLSTATE/error code

Nếu vận hành dựa vào mã lỗi, ghi DBMS và nhóm mã cụ thể. Không giả định cùng một lỗi có cùng mã giữa PostgreSQL, MySQL, SQL Server và Oracle. Tài liệu ứng dụng nên mô tả adapter ánh xạ lỗi DBMS thành loại lỗi nghiệp vụ nào.

### 12.2. Partial failure

Nếu workflow có nhiều câu SQL, ghi:
- Statement nào đã chạy.
- Transaction có bao phủ tất cả không.
- Có thể rollback không.
- Side effect ngoài database có xảy ra không.
- Cách kiểm tra trạng thái sau khi mất kết nối.
- Có idempotency key hay operation ID không.

## 13. Ghi transaction và quyền sở hữu connection

Với workflow nhiều câu lệnh, cần ghi rõ connection affinity:

~~~text
Checkout connection C1
BEGIN
Statement A trên C1
Statement B trên C1
Kiểm tra invariant trên C1
COMMIT hoặc ROLLBACK trên C1
Release C1
~~~

Không mở BEGIN trên connection A rồi chạy UPDATE qua connection B. Với connection pool, checkout một client rồi dùng nó cho mọi statement trong transaction.

Tài liệu transaction nên nêu:
- Autocommit ban đầu.
- Isolation level.
- Thời gian transaction dự kiến.
- Lock được lấy.
- Thứ tự lock.
- Commit condition.
- Rollback condition.
- Retryable error.
- Idempotency strategy.
- Cleanup và connection discard khi rollback thất bại.

Nếu chỉ có SELECT độc lập, không cần tạo transaction tường minh trừ khi có yêu cầu snapshot nhất quán nhiều statement.

## 14. Tài liệu hóa bảo mật và quyền

Một câu lệnh có thể đúng nhưng chạy bằng role quá rộng hoặc nhận input không an toàn.

Ghi:
- Role tối thiểu cần thiết.
- SELECT/INSERT/UPDATE/DELETE trên object nào.
- Có dùng SECURITY DEFINER hoặc elevated privilege không.
- Parameter binding.
- Whitelist identifier trong dynamic SQL.
- Tenant/data isolation.
- Row-level security policy nếu có.
- Dữ liệu nhạy cảm trong output.
- Quy tắc log/redaction.

Không ghi credential trong tài liệu. Ví dụ chạy nên dùng placeholder và secret manager.

## 15. Tài liệu hóa hiệu năng và quan sát

Không cần lưu toàn bộ execution plan cho mọi query, nhưng truy vấn quan trọng nên có thông tin để nhận biết khi workload thay đổi.

Có thể ghi:
- Query ID hoặc tên nghiệp vụ.
- Bảng lớn và index quan trọng.
- Ước lượng cardinality.
- Latency baseline và p95/p99.
- Số hàng đọc/ghi.
- Lock wait/timeout.
- Query plan link hoặc artifact có version.
- Ngày benchmark và DBMS version.
- Dataset scale.
- Điều kiện tái chạy benchmark.

Ví dụ PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    SUM(amount)
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
GROUP BY customer_id;
~~~

EXPLAIN ANALYZE thực thi truy vấn. Dùng trên môi trường phù hợp; không chạy câu lệnh có side effect chỉ để lấy plan mà không hiểu hậu quả.

Tránh khẳng định một plan text cụ thể sẽ luôn tồn tại. Optimizer có thể thay đổi plan hợp lệ theo thống kê, version, cấu hình và dữ liệu. Tài liệu nên ghi mục tiêu hiệu năng và những guardrail có ý nghĩa.

## 16. Tái lập kết quả ở môi trường khác

Để một người khác chạy lại, tài liệu nên cung cấp đủ điều kiện:

1. DBMS và version.
2. Schema/migration version.
3. Fixture hoặc nguồn dữ liệu thử đã được phép.
4. Role/quyền.
5. Session timezone/collation/isolation.
6. Tham số và kiểu tham số.
7. SQL nguyên văn.
8. Thứ tự thực thi.
9. Expected result.
10. Cách cleanup và cách xác nhận thành công.

Không hứa tái lập byte-for-byte trên mọi DBMS nếu semantics khác. Hãy xác định một dialect chuẩn và mô tả adapter/fallback cho dialect còn lại.

### 16.1. Fixture có thể chạy lại

Fixture nên:
- Có ID xác định.
- Có cleanup.
- Không đụng dữ liệu thật.
- Có thể chạy nhiều lần hoặc có bước reset rõ.
- Không phụ thuộc thứ tự test.
- Không phụ thuộc sequence cụ thể.
- Ghi rõ version fixture.

Với dữ liệu lớn, ghi cách lấy snapshot đã ẩn danh, checksum và thời điểm tạo.

### 16.2. Snapshot kết quả

Snapshot có thể là CSV/JSON hoặc bảng expected. Ghi:
- Query version.
- Schema version.
- DBMS/version.
- Parameter set.
- Chuẩn hóa decimal/timezone.
- Có sort hay không.
- Cách bỏ dữ liệu nhạy cảm.
- Người review baseline.

Snapshot không thay thế spec; nó là bằng chứng cho một tập input xác định.

## 17. Quản lý version và thay đổi tài liệu

SQL và tài liệu phải thay đổi cùng nhau khi semantics thay đổi.

Một hồ sơ nên có:
- Query ID ổn định.
- Owner/team.
- Version hoặc commit SHA.
- Schema/migration version hỗ trợ.
- Ngày cập nhật.
- Người review.
- Link tới spec/ticket.
- Change log.
- Trạng thái: draft, approved, deprecated.

Ví dụ change log:

| Version | Thay đổi | Lý do | Tác động | Người duyệt |
| --- | --- | --- | --- | --- |
| 1.0 | Tạo báo cáo theo khách | Yêu cầu ban đầu | API báo cáo | Team Data |
| 1.1 | Loại đơn CANCELLED | Sửa rule doanh thu | Thay output | Owner nghiệp vụ |
| 1.2 | Thêm currency | Hỗ trợ nhiều tiền tệ | Output contract đổi | Finance |

Không chỉ ghi “updated SQL”. Hãy ghi điều gì đổi và kết quả nào thay đổi.

### 17.1. Khi query deprecated

Ghi:
- Ngày không còn được dùng.
- Consumer thay thế.
- Version cuối được hỗ trợ.
- Có thể xóa object nào.
- Điều kiện xác nhận không còn caller.
- Cách rollback nếu consumer cũ xuất hiện.

## 18. Template tài liệu SQL có thể tái sử dụng

Dưới đây là một mẫu có thể sao chép cho mỗi truy vấn quan trọng. Bỏ các mục không áp dụng, nhưng giữ các mục contract, assumptions, SQL và expected result.

~~~markdown
# [Query ID] — [Tên truy vấn]

## 1. Metadata
- Owner:
- Status:
- Version / commit:
- DBMS và version:
- Schema/migration version:
- Last reviewed:
- Related spec/ticket:

## 2. Mục đích
- Consumer:
- Câu hỏi nghiệp vụ:
- Grain: một hàng mỗi ...
- In scope:
- Out of scope:

## 3. Giả định và quyết định
| ID | Nội dung | Loại | Nguồn/trạng thái | Ảnh hưởng |
| --- | --- | --- | --- | --- |

## 4. Nguồn dữ liệu
| Object | Cột | Vai trò | PK/FK/cardinality |
| --- | --- | --- | --- |

## 5. Môi trường
- DBMS/version:
- Driver/ORM:
- Timezone:
- Collation/encoding:
- Isolation/autocommit:
- Role/permissions:
- Extensions/config:

## 6. Tham số
| Name | SQL type | Required | Unit/domain | Default |
| --- | --- | --- | --- | --- |

## 7. Câu lệnh
~~~sql
-- SQL nguyên văn ở đây
~~~

- Execution order:
- Connection/transaction:
- Bind parameters:
- Retry/rollback:

## 8. Output contract
| Column | Type | Nullable | Meaning/unit |
| --- | --- | --- | --- |

- Row grain:
- Ordering:
- Precision/rounding:
- Timezone:
- NULL behavior:

## 9. Fixture và cách chạy
- Schema/migration:
- Seed data:
- Run command:
- Cleanup:

## 10. Expected result
- Expected row count:
- Expected rows:
- Invariants:
- Expected errors:

## 11. Giới hạn và rủi ro
- Business limits:
- Data assumptions:
- DBMS/version limits:
- Performance budget:
- Permissions/security:
- Consistency/replica lag:

## 12. Vận hành và debug
- Query ID/fingerprint:
- Logs/metrics:
- Timeout:
- Recovery/reconciliation:

## 13. Change log
| Version | Change | Reason | Impact | Reviewer |
| --- | --- | --- | --- | --- |
~~~

## 19. Ví dụ tài liệu cho câu lệnh ghi dữ liệu

Với câu lệnh ghi, expected result không chỉ là result set. Phải mô tả trạng thái dữ liệu trước/sau và transaction.

Ví dụ cập nhật trạng thái đơn:

~~~sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE id = :order_id
  AND status = 'DRAFT';
~~~

Tài liệu cần ghi:
- order_id là BIGINT và bắt buộc.
- Chỉ DRAFT được chuyển sang CONFIRMED.
- Kỳ vọng affected rows = 1 nếu chuyển thành công.
- Affected rows = 0 nếu đơn không tồn tại hoặc trạng thái không còn DRAFT.
- Không tự chuyển trạng thái khác.
- Có trigger/audit nào chạy hay không.
- Có cần transaction chung với ghi lịch sử không.
- Retry có an toàn không.

Expected:
| Trạng thái trước | Số hàng ảnh hưởng | Trạng thái sau |
| --- | ---: | --- |
| DRAFT | 1 | CONFIRMED |
| CONFIRMED | 0 | CONFIRMED |
| CANCELLED | 0 | CANCELLED |
| ID không tồn tại | 0 | Không có hàng |

Nếu ghi lịch sử là bắt buộc, hai câu lệnh phải cùng transaction:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE id = :order_id
  AND status = 'DRAFT';

-- Ứng dụng kiểm tra affected rows = 1.
-- Nếu không đúng: ROLLBACK.

INSERT INTO order_history(order_id, action)
VALUES (:order_id, 'CONFIRMED');

COMMIT;
~~~

Các comment không tự kiểm tra row count. Ứng dụng phải đọc kết quả UPDATE và quyết định COMMIT hay ROLLBACK trên cùng connection.

## 20. Ví dụ tài liệu cho migration

Một migration cần có thông tin bổ sung so với SELECT:
- Phiên bản schema trước/sau.
- DDL chính xác.
- Có implicit commit hay không theo DBMS.
- Lock và downtime dự kiến.
- Dữ liệu backfill.
- Batch size và resume marker.
- Khả năng chạy lại.
- Kiểm tra count/checksum.
- Tương thích app cũ/mới.
- Rollback hoặc forward-fix.
- Backup/recovery.
- Điều kiện contract/xóa cột cũ.

Ví dụ thêm cột mới:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(200);
~~~

Tài liệu không nên chỉ nói “thêm display_name”. Cần nêu:
- Giá trị cũ được backfill từ đâu.
- Có cho phép NULL trong giai đoạn đầu không.
- App nào bắt đầu ghi cột mới.
- Khi nào cột được đặt NOT NULL.
- Có index không, và index có được tạo online/concurrently không.
- Consumer nào vẫn đọc cột cũ.
- Điều kiện để xóa cột cũ.

## 21. Các lỗi tài liệu hóa thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ ghi câu SQL | Không biết mục đích và rule | Viết purpose, scope và grain |
| Không ghi DBMS/version | Người khác chạy sai dialect | Ghi môi trường |
| Giả định không có nguồn | Kết quả bị hiểu sai | Gắn loại và trạng thái giả định |
| Không ghi parameter type/unit | Bind sai hoặc lệch thời gian/tiền | Bảng parameter contract |
| Expected chỉ ghi “đúng” | Không thể assert | Ghi row count, rows, invariants |
| Expected dùng cùng logic query | Hai bên cùng sai | Tính độc lập trên fixture |
| Không ghi ORDER BY | Test phụ thuộc thứ tự ngẫu nhiên | Nêu thứ tự hoặc so sánh theo key |
| Không ghi grain | JOIN nhân bản mà không nhận ra | Một hàng mỗi thực thể nào |
| Bỏ qua NULL | Khác biệt COUNT/SUM/LEFT JOIN | Ghi NULL/default semantics |
| Không ghi currency/timezone | Tổng hoặc ngày sai | Ghi unit và timezone |
| Chỉ test schema rỗng | Bỏ sót backfill | Test dữ liệu cũ |
| Không ghi transaction | Partial write | Nêu connection, commit/rollback |
| Không ghi giới hạn | Dùng sai quy mô/DBMS | Nêu data/performance/version boundary |
| Không cập nhật tài liệu | SQL và tài liệu lệch nhau | Review đồng thời |
| Lưu credential trong ví dụ | Lộ bí mật | Placeholder/secret manager |
| Không có owner | Không biết ai xác nhận | Owner và reviewer |
| Snapshot không review | Hợp thức hóa regression | Review diff và lý do |
| Chỉ ghi một lần chạy | Không tái lập được | Fixture, version, parameters, environment |

## 22. Checklist review một tài liệu SQL

### Mục đích và giả định
- [ ] Tên và mục đích truy vấn rõ ràng.
- [ ] Consumer và grain được xác định.
- [ ] In-scope/out-of-scope được ghi.
- [ ] Sự thật, giả định và quyết định được phân biệt.
- [ ] Nguồn xác nhận cho rule nghiệp vụ được dẫn.

### Môi trường và đầu vào
- [ ] DBMS/version được ghi.
- [ ] Schema/migration version được ghi.
- [ ] Driver/ORM và session settings liên quan được ghi.
- [ ] Timezone/collation/encoding được ghi nếu có ảnh hưởng.
- [ ] Role/quyền tối thiểu được nêu.
- [ ] Parameter có type, unit, domain, default.

### SQL và transaction
- [ ] SQL nguyên văn hoặc file version được tham chiếu.
- [ ] Thứ tự statement được ghi.
- [ ] Dynamic SQL có quy tắc whitelist.
- [ ] Transaction owner/connection được nêu.
- [ ] Commit/rollback và retry được mô tả.
- [ ] Side effects ngoài database được nhận diện.

### Kết quả và giới hạn
- [ ] Tên, kiểu, nullability và đơn vị output rõ.
- [ ] Row grain và cardinality rõ.
- [ ] ORDER BY/tie-break được ghi nếu cần.
- [ ] Expected result cụ thể.
- [ ] Invariants và expected errors rõ.
- [ ] Giới hạn dữ liệu, nghiệp vụ, version và performance được ghi.
- [ ] Cách chạy lại và cleanup được mô tả.

### Quản lý
- [ ] Owner, reviewer và version có mặt.
- [ ] Change log giải thích thay đổi.
- [ ] Không có secret hoặc PII không cần thiết.
- [ ] Bằng chứng thực thi được lưu an toàn.
- [ ] Tài liệu được cập nhật cùng thay đổi SQL/schema.

## 23. Kết luận

Một tài liệu SQL có thể sử dụng lâu dài phải làm rõ bốn phần:

1. **Giả định và phạm vi:** dữ liệu nào được tính, quy tắc nghiệp vụ nào được áp dụng, điều kiện nào phải đúng.
2. **Câu lệnh và môi trường:** DBMS/version, schema, tham số, quyền, thứ tự statement và transaction.
3. **Kết quả mong đợi:** output contract, row count, giá trị mẫu, invariant và hành vi lỗi.
4. **Giới hạn:** dialect, dữ liệu, hiệu năng, consistency, quyền và những trường hợp chưa được hỗ trợ.

Hãy viết tài liệu đủ cụ thể để một đồng nghiệp có thể chuẩn bị đúng môi trường, chạy đúng câu lệnh, kiểm tra kết quả và nhận ra khi nào kết quả nằm ngoài phạm vi đã cam kết. Khi SQL, schema hoặc quy tắc nghiệp vụ thay đổi, cập nhật tài liệu trong cùng thay đổi và lưu lại version/reviewer. Khi đó tài liệu trở thành một phần của hợp đồng kỹ thuật có thể kiểm chứng, thay vì chỉ là ghi chú giải thích sau khi viết code.
