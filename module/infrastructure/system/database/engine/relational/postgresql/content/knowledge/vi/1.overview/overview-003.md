# Bài toán phù hợp, giới hạn và tiêu chí lựa chọn PostgreSQL

Chọn hệ quản trị cơ sở dữ liệu không chỉ là chọn một sản phẩm có nhiều tính năng. Quyết định đúng phải bắt đầu từ **đặc điểm dữ liệu, yêu cầu nhất quán, kiểu truy vấn, quy mô tải, khả năng vận hành và chi phí thay đổi về sau**.

**PostgreSQL** là hệ quản trị cơ sở dữ liệu quan hệ mã nguồn mở, hỗ trợ SQL, giao dịch ACID, ràng buộc toàn vẹn, cơ chế điều khiển đồng thời MVCC, nhiều loại chỉ mục và khả năng mở rộng bằng extension. PostgreSQL phù hợp với nhiều ứng dụng nghiệp vụ cần dữ liệu có cấu trúc và tính đúng đắn cao, đồng thời vẫn xử lý được một phần dữ liệu bán cấu trúc qua `JSONB`.

Tuy nhiên, PostgreSQL không phải lựa chọn tối ưu cho **mọi** loại tải. Một hệ thống phân tích hàng petabyte, mạng sự kiện thời gian thực khổng lồ, kho đối tượng nhị phân lớn hoặc bài toán tìm kiếm ngữ nghĩa chuyên sâu có thể cần thành phần chuyên dụng hoặc một kiến trúc kết hợp.

Bài này giúp xác định **khi nào nên chọn PostgreSQL, khi nào cần cân nhắc công nghệ khác và phải kiểm chứng điều gì trước khi đưa vào sản xuất**. Ví dụ SQL dùng PostgreSQL hiện đại; hành vi cụ thể còn phụ thuộc phiên bản, cấu hình và extension đã cài.

## 1. Câu trả lời ngắn: PostgreSQL mạnh ở đâu?

PostgreSQL thường là ứng viên tốt khi hệ thống cần kết hợp:

- **Dữ liệu có quan hệ rõ ràng:** khách hàng–đơn hàng–dòng hàng–sản phẩm, tài khoản–giao dịch, lớp học–học viên–đăng ký.
- **Tính toàn vẹn dữ liệu:** `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK`, `NOT NULL` và transaction.
- **Truy vấn SQL linh hoạt:** `JOIN`, `GROUP BY`, CTE, window function, subquery, aggregate, truy vấn báo cáo.
- **Giao dịch đáng tin cậy:** nhiều thao tác ghi phải cùng thành công hoặc cùng thất bại.
- **Dữ liệu linh hoạt có kiểm soát:** một số thuộc tính không đồng nhất được lưu bằng `JSONB` và truy vấn với toán tử/chỉ mục thích hợp.
- **Khả năng phát triển lâu dài:** schema migration, extension, phân quyền, cơ chế backup/khôi phục và replication.
- **Khả năng giao dịch đồng thời:** nhiều người dùng đọc và ghi mà vẫn cần các ràng buộc và hành vi transaction rõ ràng.

Ví dụ: một ứng dụng quản lý đơn hàng cần bảo đảm **mỗi đơn thuộc khách hàng hợp lệ**, **mỗi dòng hàng tham chiếu sản phẩm tồn tại** và **không thể trừ tồn kho âm** trong các thao tác cập nhật cạnh tranh. PostgreSQL cung cấp những công cụ ở cấp database để diễn tả và bảo vệ phần lớn các bất biến này.

Ngược lại, nếu bài toán chủ yếu là phân phát nội dung tĩnh qua CDN, làm cache với độ trễ cực thấp hay lưu các file video lớn, PostgreSQL thường **không nên là thành phần duy nhất** đảm nhiệm mọi vai trò.

## 2. Xác định yêu cầu trước khi chọn hệ quản trị

Đừng bắt đầu bằng câu “PostgreSQL hay một database khác nhanh hơn?”. Hãy chuyển yêu cầu hệ thống thành câu hỏi có thể kiểm chứng.

| Trục đánh giá | Câu hỏi cần trả lời | Vì sao quan trọng |
| --- | --- | --- |
| Cấu trúc dữ liệu | Có nhiều thực thể liên quan và khóa ngoại không? | Quyết định giá trị của mô hình quan hệ |
| Tính nhất quán | Có cần transaction nhiều bảng, ngăn dữ liệu mồ côi/trùng không? | Ảnh hưởng cơ chế đồng thời và correctness |
| Kiểu truy vấn | Chủ yếu tra theo khóa, join, lọc, báo cáo, tìm từ hay tìm vector? | Quyết định chỉ mục và engine thích hợp |
| Tần suất ghi | Bao nhiêu thao tác ghi/giây, kích thước transaction, mức tranh chấp? | Ảnh hưởng kiến trúc primary, khóa, WAL, I/O |
| Kích thước | Dung lượng ban đầu, tăng trưởng 1–3 năm, hot/cold data? | Ảnh hưởng partition, backup, storage |
| Độ trễ | P95/P99, giới hạn thời gian cho API và báo cáo? | Ảnh hưởng cấu hình, index, cache và query plan |
| Tính sẵn sàng | RPO/RTO là bao nhiêu, có cần failover đa vùng không? | Quyết định replication, backup và orchestration |
| Vận hành | Đội ngũ có thể quản lý VACUUM, backup, nâng cấp, monitoring không? | Quyết định chi phí sở hữu thật |
| Tích hợp | ORM, CDC, BI, search, công cụ migration, extension nào cần? | Ảnh hưởng độ tương thích và phụ thuộc |
| Chi phí | Compute, RAM, SSD, replication, traffic, con người? | Ảnh hưởng hiệu quả dài hạn |

Không có công nghệ nào có thể trả lời thay cho các yêu cầu này. Ví dụ tải 10.000 giao dịch/giây với mỗi giao dịch chỉ cập nhật một hàng khác hẳn tải 10.000 giao dịch/giây cùng tranh chấp một bản ghi số dư.

## 3. Bài toán phù hợp số một: OLTP với dữ liệu quan hệ

**OLTP (Online Transaction Processing)** là kiểu tải xử lý nhiều thao tác nghiệp vụ nhỏ: thêm đơn, sửa trạng thái thanh toán, đặt lịch, cập nhật số lượng tồn kho, đăng ký tài khoản hoặc xác nhận giao dịch.

Những đặc điểm làm PostgreSQL phù hợp:

1. Dữ liệu có khóa định danh rõ ràng và liên kết giữa các bảng.
2. Cần kiểm soát ràng buộc ngay tại database, không chỉ tin vào validation của ứng dụng.
3. Ghi dữ liệu cần tính nguyên tử.
4. Truy vấn thường có điều kiện lọc, sắp xếp, phân trang và `JOIN`.
5. Hệ thống cần schema thay đổi có kiểm soát qua migration.

### 3.1. Ví dụ cấu trúc đơn hàng

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

Đây là lược đồ minh họa nhỏ, chưa bao gồm phí vận chuyển, đơn giá nhiều lần mua cùng SKU hoặc chính sách hủy hoàn tiền. Điểm đáng chú ý:

- Một `order_line` không thể tham chiếu `order_id` hoặc `product_id` không tồn tại theo khóa ngoại đang áp dụng.
- `quantity` của dòng hàng phải lớn hơn 0; `stock_qty` của sản phẩm phải không âm.
- Email và SKU có ràng buộc duy nhất.
- `NUMERIC(12,2)` phù hợp các giá trị thập phân cần độ chính xác cao hơn kiểu số thực gần đúng.
- `TIMESTAMPTZ` lưu một thời điểm có thể quy đổi múi giờ; cách hiển thị chịu ảnh hưởng timezone của session.

**Giá trị chính của PostgreSQL ở đây là khả năng bảo vệ quy tắc dữ liệu tại database.** Hai service viết bằng hai ngôn ngữ khác nhau vẫn chịu cùng ràng buộc, kể cả khi một service quên validation.

### 3.2. Giao dịch nhiều bảng

Giả sử ứng dụng tạo đơn và trừ tồn kho. Các bước phải được đặt trong một transaction phù hợp:

~~~sql
BEGIN;

-- Chỉ giảm tồn kho khi còn đủ số lượng.
UPDATE products
SET stock_qty = stock_qty - 2
WHERE product_id = 101
  AND stock_qty >= 2
RETURNING product_id, stock_qty;

-- Ứng dụng phải xác nhận UPDATE trả về đúng một hàng
-- trước khi tiếp tục tạo đơn và dòng đơn.
-- INSERT INTO orders ... RETURNING order_id;
-- INSERT INTO order_lines ...;

COMMIT;
~~~

Ví dụ giả định sản phẩm `101` tồn tại. **Nếu câu `UPDATE ... RETURNING` không trả hàng nào, ứng dụng phải `ROLLBACK`**, không được mù quáng chạy tiếp rồi commit. Một transaction không tự hiểu rằng “sản phẩm hết hàng” là lý do phải hủy nếu code không kiểm tra kết quả.

Khi cạnh tranh cao, việc kiểm tra và cập nhật trong **cùng câu UPDATE** như trên tránh một dạng race condition phổ biến: hai request cùng đọc thấy đủ hàng rồi cùng trừ dựa trên kết quả cũ. Thiết kế đầy đủ vẫn cần xử lý khóa, deadlock, transaction retry và idempotency theo nghiệp vụ.

## 4. ACID và MVCC: ưu thế quan trọng nhưng cần hiểu đúng

PostgreSQL hỗ trợ transaction ACID:

| Thuộc tính | Ý nghĩa đối với ứng dụng |
| --- | --- |
| Atomicity | Các thay đổi của transaction cùng commit hoặc cùng rollback |
| Consistency | Các ràng buộc database được duy trì theo quy tắc của chúng |
| Isolation | Các transaction đồng thời được quan sát và điều phối theo isolation level |
| Durability | Thay đổi đã commit được bảo vệ theo cơ chế WAL/durability và cấu hình hệ thống |

### MVCC là gì?

**Multi-Version Concurrency Control (MVCC)** giúp PostgreSQL quản lý nhiều phiên bản hàng, để truy vấn đọc thông thường và các transaction ghi có thể cùng hoạt động mà không cần khóa mọi thao tác đọc theo kiểu độc quyền.

Ví dụ một transaction đang sửa trạng thái đơn nhưng chưa commit; một truy vấn `SELECT` thông thường ở session khác có thể thấy phiên bản đã commit phù hợp với snapshot của nó. Điều này hỗ trợ hiệu năng đọc đồng thời.

Nhưng MVCC **không loại bỏ mọi khóa hoặc mọi xung đột**:

- Hai transaction cùng `UPDATE` một hàng vẫn có thể phải chờ nhau.
- `SELECT ... FOR UPDATE` là locking read, chủ động lấy khóa hàng.
- DDL có thể cần khóa mạnh và chặn câu truy vấn khác.
- Các mức isolation mạnh hơn, nhất là `SERIALIZABLE`, có thể phát sinh lỗi cần **retry toàn bộ transaction**.
- Một transaction kéo dài có thể khiến các phiên bản hàng cũ chưa thể được thu hồi sớm.

Vì vậy, khi đánh giá PostgreSQL cho hệ thống ghi đồng thời, cần đo workload thật, tỷ lệ lock wait, deadlock, thời gian transaction và cơ chế retry của ứng dụng, không chỉ nhìn một biểu đồ throughput đơn giản.

### Isolation level cần chọn theo bất biến

PostgreSQL thường dùng `READ COMMITTED` mặc định. Có thể cân nhắc `REPEATABLE READ` hoặc `SERIALIZABLE` khi nghiệp vụ yêu cầu cách quan sát mạnh hơn, nhưng chúng có chi phí và hành vi retry khác nhau.

Ví dụ:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

-- Đọc, kiểm tra bất biến và cập nhật dữ liệu liên quan.
-- Một giao dịch đồng thời có thể khiến transaction này
-- nhận serialization_failure (SQLSTATE 40001).

COMMIT;
~~~

Chọn `SERIALIZABLE` không đồng nghĩa “không bao giờ có lỗi đồng thời”. Ứng dụng phải biết xử lý serialization failure bằng cách khởi tạo lại transaction, đọc lại dữ liệu và thực thi lại thao tác theo chính sách retry có giới hạn.

## 5. Truy vấn SQL phong phú: JOIN, CTE, window function và báo cáo

PostgreSQL phù hợp khi logic truy vấn vượt quá tra một bản ghi theo khóa:

- Ghép nhiều bảng bằng `JOIN`.
- Tổng hợp bằng `GROUP BY`, `HAVING` và các hàm aggregate.
- Dùng CTE để tổ chức truy vấn nhiều bước.
- Dùng window functions để xếp hạng, tính tổng lũy kế hoặc so sánh hàng với nhóm.
- Dùng kiểu dữ liệu ngày giờ, khoảng giá trị, mảng và JSON cho những nhu cầu cụ thể.
- Dùng materialized view khi muốn lưu kết quả truy vấn đã tính sẵn và có chiến lược refresh.

Ví dụ thống kê số đơn theo khách hàng:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY order_count DESC, c.customer_id;
~~~

Ví dụ chọn đơn mới nhất mỗi khách hàng qua window function:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM orders AS o
)
SELECT order_id, customer_id, status, created_at
FROM ranked_orders
WHERE rn = 1;
~~~

Điều này giúp đáp ứng các truy vấn nghiệp vụ phức tạp trong cùng hệ CSDL quan hệ, giảm nhu cầu chuyển mọi báo cáo nhỏ sang một hệ thống khác.

Tuy nhiên, **không nên biến primary OLTP thành kho phân tích nặng không giới hạn**. Một dashboard quét hàng tỷ dòng và cạnh tranh I/O với thao tác thanh toán có thể làm giảm chất lượng giao dịch. Khi tải phân tích tăng cao, có thể đưa dữ liệu sang replica, hệ phân tích chuyên dụng hoặc pipeline ETL/ELT.

## 6. JSONB: linh hoạt nhưng vẫn nằm trong database quan hệ

Một điểm mạnh của PostgreSQL là kiểu `JSONB` cho phép lưu đối tượng hoặc mảng JSON theo định dạng nhị phân đã được chuẩn hóa nội bộ, hỗ trợ toán tử truy vấn và các loại chỉ mục phù hợp.

Ví dụ hệ thống sản phẩm có các thuộc tính khác nhau theo loại hàng:

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (jsonb_typeof(attributes) = 'object')
);

INSERT INTO catalog_products (sku, name, category, attributes)
VALUES
    (
      'KB-01', 'Bàn phím cơ', 'keyboard',
      '{"switch":"brown","layout":"TKL","wireless":true}'
    ),
    (
      'BK-01', 'Sách SQL', 'book',
      '{"author":"Nguyen A","pages":320,"language":"vi"}'
    );
~~~

Truy vấn theo thuộc tính:

~~~sql
SELECT sku, name
FROM catalog_products
WHERE attributes ->> 'layout' = 'TKL';

SELECT sku, name
FROM catalog_products
WHERE attributes @> '{"wireless":true}'::jsonb;
~~~

Có thể lập GIN index cho nhiều phép truy vấn JSONB:

~~~sql
CREATE INDEX idx_catalog_attributes_gin
ON catalog_products
USING GIN (attributes);
~~~

Chỉ mục GIN tổng quát có thể hỗ trợ các phép so khớp JSONB thích hợp như containment `@>`. Nhưng không phải mọi phép toán `attributes ->> 'layout' = 'TKL'` tự động dùng hiệu quả chỉ mục GIN trên toàn bộ cột. Với một khóa truy vấn thường xuyên, có thể cân nhắc **expression index**:

~~~sql
CREATE INDEX idx_catalog_layout
ON catalog_products ((attributes ->> 'layout'));
~~~

### Khi nào JSONB là phù hợp?

- Một số thuộc tính mang tính tùy chọn hoặc khác nhau theo loại sản phẩm.
- Phần lõi vẫn có ID, quan hệ và ràng buộc ổn định.
- Có yêu cầu truy vấn một số đường dẫn JSON và có thể thiết kế index rõ ràng.
- Muốn tiến hóa các thuộc tính linh hoạt mà không liên tục thêm cột cho mọi biến thể.

### Khi nào không nên lạm dụng?

- Trường quan trọng cần `FOREIGN KEY`, `UNIQUE`, cập nhật và truy vấn rất thường xuyên.
- Hầu hết biểu thức nghiệp vụ đều phải trích/ép kiểu từ JSON.
- Dữ liệu JSON quá lớn, cập nhật liên tục và làm tăng chi phí ghi/WAL/bloat.
- Cấu trúc thật sự ổn định và dễ mô hình hóa thành bảng quan hệ.

**JSONB không biến PostgreSQL thành document database hoàn toàn giống mọi sản phẩm NoSQL.** PostgreSQL có thể xử lý dữ liệu bán cấu trúc tốt, nhưng thiết kế hợp lý thường là **khóa và thuộc tính cốt lõi ở cột quan hệ, thông tin biến thiên ở JSONB**.

## 7. Hệ sinh thái extension: khả năng mở rộng có điều kiện

PostgreSQL hỗ trợ extension để bổ sung kiểu dữ liệu, hàm, operator và tính năng khác. Những ví dụ phổ biến:

| Extension/khả năng | Bài toán có thể hỗ trợ | Điều cần kiểm tra |
| --- | --- | --- |
| PostGIS | Dữ liệu địa lý, hình học, phép đo và truy vấn không gian | Tài nguyên, indexing không gian, tương thích phiên bản |
| pg_trgm | Tìm kiếm chuỗi tương tự, trigram và một số mẫu `LIKE`/`ILIKE` | Kích thước index, chất lượng khớp |
| pgcrypto | Một số chức năng mã hóa/hash theo tài liệu extension | Quy tắc quản lý khóa, an toàn bảo mật toàn hệ thống |
| citext | So sánh văn bản không phân biệt hoa/thường cho một số trường hợp | Locale/collation và yêu cầu so sánh thực tế |
| Extension vector phù hợp | Lưu và tìm vector gần đúng/chính xác theo khả năng extension | Độ chính xác, chỉ mục, memory và khả năng triển khai |

Ví dụ nếu môi trường đã hỗ trợ `pg_trgm`, một truy vấn tìm tên tương tự có thể được tối ưu bằng index phù hợp thay vì quét một cột text lớn.

~~~sql
-- Chỉ chạy khi DBA xác nhận extension được phép triển khai.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_catalog_name_trgm
ON catalog_products
USING GIN (name gin_trgm_ops);

SELECT sku, name
FROM catalog_products
WHERE name ILIKE '%ban phim%';
~~~

Câu truy vấn mẫu là tìm chuỗi không dấu trong `name`; dữ liệu mẫu `'Bàn phím cơ'` có dấu, nên kết quả **không tự được bảo đảm**. `pg_trgm` tăng khả năng indexing kiểu tìm chuỗi, **không tự chuyển nội dung có dấu thành không dấu**. Nếu nghiệp vụ cần tìm có/không dấu tương đương, cần thiết kế chuẩn hóa văn bản và collation tương ứng.

**Extension không mặc nhiên có sẵn trên mọi dịch vụ PostgreSQL managed.** Cần kiểm tra danh sách extension được hỗ trợ, quyền cài, chính sách nâng cấp và rủi ro vendor lock-in. Không chọn sản phẩm chỉ vì “PostgreSQL có extension X” nếu môi trường dự định thuê không cho cài extension đó.

## 8. Tìm kiếm toàn văn, địa lý và các nhu cầu đặc biệt

PostgreSQL có các tính năng phong phú ngoài giao dịch quan hệ:

### Full-text search

Có thể dùng `tsvector`, `tsquery` và GIN index để tìm văn bản theo token và cấu hình từ điển:

~~~sql
CREATE TABLE knowledge_articles (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE INDEX idx_knowledge_fts
ON knowledge_articles
USING GIN (
    to_tsvector('simple', title || ' ' || body)
);

SELECT article_id, title
FROM knowledge_articles
WHERE to_tsvector('simple', title || ' ' || body)
      @@ plainto_tsquery('simple', 'postgresql index');
~~~

Đây là minh họa dùng cấu hình `simple`; khả năng tách từ, xử lý dấu, stemming và độ liên quan trong tiếng Việt phải được đánh giá theo bộ dữ liệu và cấu hình thực tế. PostgreSQL hỗ trợ full-text search, nhưng không tự cung cấp mọi tính năng như typo tolerance, autocomplete chuyên sâu, phân tích ngôn ngữ đa dạng hoặc ranking tùy biến ở quy mô lớn.

### Dữ liệu địa lý

Với PostGIS, PostgreSQL có thể trở thành nền tảng mạnh cho truy vấn giao cắt vùng, khoảng cách, tọa độ và hình học không gian. Đây là lý do đáng cân nhắc nếu ứng dụng vừa cần quan hệ giao dịch vừa cần GIS trong một database.

Tuy nhiên, hệ thống GIS quy mô lớn cần kiểm chứng định dạng tọa độ/SRID, chỉ mục, chất lượng dữ liệu và tài nguyên; việc cài PostGIS không thay thế mô hình hóa địa lý đúng.

### Vector và tìm kiếm tương đồng

Có các extension trong hệ sinh thái hỗ trợ lưu/tìm vector. Chúng có thể phù hợp khi quy mô và yêu cầu không quá khác biệt với workload quan hệ. Nếu số vector rất lớn, tốc độ cập nhật cao hoặc thuật toán tìm kiếm có yêu cầu đặc biệt, cần thử nghiệm độ trễ, recall, dung lượng và chi phí so với hệ chuyên dụng.

## 9. Giới hạn quan trọng: PostgreSQL không tự mở rộng ghi ngang vô hạn

Một PostgreSQL instance thường có **một primary nhận ghi** trong topology replication truyền thống. Việc thêm read replica giúp phân tải **một phần truy vấn đọc**, nhưng không tự tăng năng lực ghi cho primary theo tỷ lệ số replica.

Các vấn đề cần xét:

- CPU, RAM, SSD và mạng của primary có giới hạn.
- WAL, fsync, replication và checkpointer tạo chi phí I/O.
- Hot row/hot index có thể tạo tranh chấp dù tổng số transaction không quá lớn.
- Một transaction cập nhật nhiều hàng hoặc giữ khóa lâu ảnh hưởng latency của transaction khác.
- Chỉ mục tăng tốc đọc nhưng làm tăng chi phí ghi và dung lượng.

### Vertical scaling, partitioning và sharding là khác nhau

| Cách tiếp cận | Giải quyết chủ yếu | Không tự giải quyết |
| --- | --- | --- |
| Tăng CPU/RAM/SSD của primary | Tăng tài nguyên cho một instance | Không xóa hot row hoặc giới hạn kiến trúc |
| Read replica | Chia bớt truy vấn đọc, phục vụ HA | Không tự chia ghi |
| Partitioning bản địa | Quản lý bảng lớn, giảm phạm vi truy vấn phù hợp, vòng đời dữ liệu | Không biến một primary thành nhiều writer độc lập |
| Sharding | Phân bố dữ liệu/tải ghi sang nhiều node | Đòi hỏi định tuyến, xử lý transaction cross-shard và vận hành phức tạp |
| Cache | Giảm lượt truy vấn lặp lại | Không thay cơ sở dữ liệu nguồn có tính nhất quán |

PostgreSQL có **declarative partitioning** hữu ích khi dữ liệu có khóa phân vùng hợp lý, ví dụ nhật ký sự kiện theo tháng. Nhưng partitioning không phải nút bấm làm mọi truy vấn nhanh hơn; cần kiểm tra partition pruning, số partition, thiết kế index và ràng buộc toàn cục.

Nếu dự báo cần ghi hàng triệu sự kiện/giây trên nhiều vùng và không thể gom ở một writer, hãy làm proof of concept sớm cho kiến trúc phân tán, event ingestion hoặc sharding thay vì giả định PostgreSQL đơn lẻ sẽ đáp ứng.

## 10. MVCC đi kèm trách nhiệm VACUUM và quản lý bloat

Một đặc trưng quan trọng của PostgreSQL là các transaction cập nhật/xóa có thể để lại các phiên bản hàng cũ. PostgreSQL sử dụng **VACUUM** để thu hồi khả năng tái sử dụng không gian và duy trì thông tin cần thiết cho hệ thống.

**Autovacuum** tự động thực hiện nhiều công việc bảo trì cần thiết, nhưng không có nghĩa hệ thống hoàn toàn không phải quan tâm:

- Bảng cập nhật/xóa thường xuyên có thể tăng dead tuples và bloat.
- Transaction dài giữ snapshot cũ có thể cản việc thu hồi các phiên bản hàng.
- Replication slot bị bỏ quên hoặc một số cơ chế giữ snapshot/WAL có thể tạo áp lực lưu trữ.
- Thống kê planner cần cập nhật để optimizer chọn kế hoạch phù hợp.
- Giám sát tuổi transaction ID và tình trạng chống wraparound là trách nhiệm vận hành nghiêm túc.

Quan sát sơ bộ trạng thái bảng:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Các số hàng trong thống kê thường là **ước lượng**, không phải phép đếm chính xác theo một snapshot. Không nên tắt autovacuum để “tăng hiệu năng ghi” mà không hiểu ảnh hưởng lâu dài, đặc biệt nguy cơ liên quan đến transaction ID wraparound.

Một đội ngũ quen với database khác cần tính vào chi phí học và giám sát riêng cho MVCC, VACUUM, WAL và replication của PostgreSQL.

## 11. Chỉ mục giúp nhanh hơn nhưng cũng có giá

PostgreSQL hỗ trợ nhiều phương pháp chỉ mục phù hợp với các loại truy vấn khác nhau:

| Loại index | Trường hợp điển hình |
| --- | --- |
| B-tree | So sánh bằng, phạm vi, sắp xếp theo thứ tự |
| GIN | JSONB containment, full-text search, mảng với operator phù hợp |
| GiST | Một số dữ liệu không gian, range type và phép so khớp đặc biệt |
| BRIN | Bảng rất lớn có dữ liệu tương quan với thứ tự vật lý, ví dụ timestamp tăng dần |
| Partial index | Chỉ lập chỉ mục tập hàng thỏa một predicate |
| Expression index | Lập chỉ mục giá trị tính từ biểu thức, ví dụ `lower(email)` |

Ví dụ index hỗ trợ truy vấn đơn đang chờ xử lý:

~~~sql
CREATE INDEX idx_orders_pending_created
ON orders (created_at)
WHERE status = 'pending';
~~~

Nó có thể phù hợp nếu chỉ một phần nhỏ đơn ở trạng thái `pending` và ứng dụng thường tìm đơn chờ theo thời gian. Nhưng nếu phần lớn truy vấn dùng trạng thái khác, cần đánh giá thêm trước khi tạo nhiều index.

Đo đường truy cập bằng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE status = 'pending'
ORDER BY created_at
LIMIT 50;
~~~

`EXPLAIN ANALYZE` **thực sự chạy câu SQL**, nên với DML cần đặc biệt thận trọng; ví dụ trên chỉ dùng `SELECT`. Kế hoạch cho bảng lab nhỏ có thể khác production vì thống kê và độ chọn lọc khác nhau.

Không kết luận “PostgreSQL chậm” khi một truy vấn chạy thiếu index hoặc thiết kế sai; cũng không kết luận “PostgreSQL nhanh” chỉ từ demo vài chục dòng. Đánh giá phải theo dữ liệu, workload và cấu hình tương ứng.

## 12. Khả dụng cao và khôi phục: có công cụ, không tự vận hành thay bạn

PostgreSQL sử dụng **Write-Ahead Logging (WAL)** để hỗ trợ crash recovery, backup vật lý và replication theo cơ chế phù hợp.

Những năng lực thường dùng:

- **Streaming physical replication:** replica có thể nhận và phát lại WAL từ primary.
- **Read replica:** phục vụ một phần tải đọc, chấp nhận được độ trễ theo yêu cầu.
- **Point-in-time recovery (PITR):** khôi phục backup nền và phát lại WAL archive tới một thời điểm/điểm dừng đã chọn.
- **Logical replication:** sao chép những thay đổi ở mức logic theo publication/subscription trong phạm vi được hỗ trợ.
- **Backup logical:** ví dụ `pg_dump`, hữu ích cho xuất dữ liệu/schema và một số kịch bản di chuyển.
- **Backup physical:** phục vụ bảo vệ cluster ở mức tệp/WAL theo quy trình tương thích.

### Các giới hạn cần hiểu

- Asynchronous replica có thể **chậm hơn primary**; failover có nguy cơ mất một phần giao dịch chưa được sao chép.
- Synchronous replication có thể giảm một số rủi ro mất dữ liệu nhưng đổi lại bằng latency/availability tùy quorum và cấu hình.
- Việc chuyển primary an toàn đòi hỏi cơ chế **election/fencing** để tránh split-brain; PostgreSQL đơn lẻ không thay thế hệ điều phối HA.
- `pg_dump` không tự cung cấp một quy trình PITR đầy đủ như backup vật lý kèm WAL archive.
- WAL cần được lưu đủ cho replica và backup; cấu hình archive/replication slot sai có thể làm đầy đĩa.
- Khả năng tạo backup không đồng nghĩa khả năng **restore được trong RTO**; cần diễn tập phục hồi.

Nếu yêu cầu ứng dụng là RPO bằng 0 và RTO chỉ vài giây trên nhiều vùng địa lý, phải đánh giá topology, độ trễ mạng, cơ chế consensus/replication và nhà cung cấp cụ thể. Không được suy từ “PostgreSQL hỗ trợ replication” rằng mọi mức SLA đều đạt được.

## 13. PostgreSQL không thay mọi hệ thống dữ liệu chuyên dụng

Một kiến trúc thực tế thường kết hợp nhiều công cụ, mỗi công cụ xử lý một phần bài toán:

| Hệ thống/loại workload | PostgreSQL có thể làm gì? | Khi nào cần cân nhắc thành phần khác? |
| --- | --- | --- |
| Ứng dụng web OLTP | Nguồn dữ liệu quan hệ chính, transaction, ràng buộc | Khi chia ghi toàn cầu/đa vùng phức tạp |
| Phân tích nhẹ/trung bình | SQL aggregate, CTE, materialized view, báo cáo | Khi quét lượng dữ liệu cực lớn và cần warehouse/OLAP |
| Cache truy cập nóng | Lưu dữ liệu nguồn với consistency | Khi cần cache có TTL, eviction, latency cực thấp |
| Tìm kiếm văn bản | Built-in FTS, trigram extension | Khi cần search engine có ranking, typo, phân tích ngôn ngữ nâng cao |
| Tìm kiếm vector | Một số extension phù hợp | Khi scale/recall/latency yêu cầu hệ vector chuyên dụng |
| GIS | PostGIS là lựa chọn mạnh khi được hỗ trợ | Khi xử lý ảnh viễn thám/hệ chuyên biệt vượt DB SQL |
| Streaming events | Có thể là nguồn dữ liệu và cung cấp thay đổi qua CDC | Khi cần event broker, replay/consumer groups ở quy mô lớn |
| Lưu ảnh/video/file lớn | Có thể lưu metadata, một số binary data | Khi object storage/CDN thích hợp hơn |
| Telemetry/time-series | SQL, partition và extension có thể đáp ứng nhiều tải | Khi ingest cực cao, retention/compression/rollup cần engine chuyên biệt |

Kiến trúc kết hợp không có nghĩa luôn cần nhiều database từ ngày đầu. Với nhóm nhỏ, **một PostgreSQL quản trị tốt thường đơn giản hơn phân tán dữ liệu quá sớm**. Nhưng cần thiết kế điểm mở rộng khi workload thật cho thấy giới hạn.

## 14. So sánh định hướng với các lựa chọn thường gặp

Bảng dưới đây so sánh **nhóm nhu cầu**, không phải xếp hạng tuyệt đối công nghệ.

| Lựa chọn | Điểm thuận lợi điển hình | Điều cần đánh giá so với PostgreSQL |
| --- | --- | --- |
| PostgreSQL | SQL phong phú, toàn vẹn quan hệ, extensibility, JSONB, hệ sinh thái | Chi phí vận hành, scale ghi, tuning, HA |
| MySQL | OLTP quan hệ phổ biến, hệ sinh thái ứng dụng lớn, nhiều dịch vụ managed | Độ phù hợp kiểu truy vấn/tính năng SQL và vận hành cụ thể |
| SQLite | Nhúng trực tiếp vào ứng dụng, đơn giản, không cần server riêng | Mô hình nhiều client ghi vào service tập trung và vận hành server |
| Document database | Mô hình tài liệu linh hoạt, truy cập dựa trên document | Join/constraint/transaction nhiều thực thể, truy vấn báo cáo |
| Kho phân tích cột/warehouse | Quét và tổng hợp dữ liệu lớn hiệu quả | Transaction OLTP và chi phí duy trì pipeline |
| Search engine | Search/ranking/analyzer chuyên sâu | Nguồn sự thật giao dịch, ràng buộc quan hệ |
| Distributed SQL | Một số thiết kế hỗ trợ phân tán dữ liệu/ghi | Độ trễ, giới hạn tính năng SQL, độ phức tạp và chi phí |

Không nên kết luận “PostgreSQL luôn tốt hơn MySQL” hoặc “NoSQL luôn nhanh hơn SQL”. Hiệu năng còn phụ thuộc **schema, truy vấn, chỉ mục, dữ liệu, cấu hình và mục tiêu nhất quán**. Một hệ thống dùng PostgreSQL tối ưu tốt có thể vượt hệ khác ở workload này nhưng kém ở workload khác.

## 15. Tiêu chí chọn theo từng loại ứng dụng

### 15.1. Thương mại điện tử hoặc SaaS nghiệp vụ

**Phù hợp khi:** quan hệ khách hàng–đơn–sản phẩm rõ ràng, thao tác giao dịch nhiều bảng, yêu cầu dữ liệu không trùng/mồ côi, cần SQL báo cáo, có một luồng ghi chính.

**Cần kiểm chứng:** p95/p99 khi đặt hàng đồng thời, tồn kho là hot row, logic xử lý retry, phân quyền theo tenant, phương án HA và backup. Có thể lưu thông số sản phẩm linh hoạt ở `JSONB` nhưng giữ các khóa nghiệp vụ cốt lõi dạng cột.

### 15.2. Hệ thống kế toán, thanh toán, đặt chỗ

**Phù hợp khi:** tính đúng đắn transaction và ràng buộc được ưu tiên, cần kiểm toán nghiệp vụ, sự nhất quán giữa nhiều bản ghi.

**Cần kiểm chứng:** isolation, mô hình số dư/sổ cái, idempotency, concurrency test, audit trail. PostgreSQL cung cấp primitive mạnh nhưng không tự thiết kế một sổ cái đúng hoặc quy trình thanh toán an toàn thay ứng dụng.

### 15.3. Dashboard và reporting

**Phù hợp khi:** báo cáo có khối lượng vừa, cần join với OLTP và độ trễ chấp nhận được.

**Cần cân nhắc hệ khác khi:** cần quét dữ liệu khổng lồ thường xuyên, nhiều truy vấn BI phức tạp cạnh tranh tài nguyên với giao dịch chính. Khi đó có thể tách analytical workload để bảo vệ primary.

### 15.4. Hệ thống quản lý nội dung

**Phù hợp khi:** bài viết, người viết, quyền, tag, comment có quan hệ rõ; một phần metadata thay đổi linh hoạt.

**Cần kiểm chứng:** search quality, quản lý file/media, hot reads, cache/CDN. Không nên đưa mọi ảnh/video lớn vào hàng PostgreSQL nếu object storage phù hợp hơn.

### 15.5. Telemetry, clickstream, log và sự kiện

**Có thể phù hợp khi:** quy mô vừa, cần truy vấn SQL, retention rõ và partition theo thời gian.

**Cần cân nhắc lại khi:** nguồn sinh sự kiện liên tục cực lớn, retention dài, query chủ yếu quét/tổng hợp nhiều tỷ hàng. Chiến lược partition, compression, streaming và OLAP có thể quan trọng hơn các ràng buộc giao dịch quan hệ.

## 16. Khả năng bảo mật và đa tenant

PostgreSQL có hệ thống role, privilege, schema và **Row-Level Security (RLS)**, hữu ích trong ứng dụng đa người thuê dữ liệu.

Ví dụ bảng có khóa tenant:

~~~sql
CREATE TABLE tenant_documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    title TEXT NOT NULL
);

CREATE INDEX idx_tenant_documents_tenant
ON tenant_documents (tenant_id);
~~~

Bước đầu quan trọng là **mọi truy vấn ứng dụng phải hạn chế theo tenant hợp lệ**:

~~~sql
SELECT document_id, title
FROM tenant_documents
WHERE tenant_id = $1;
~~~

`$1` ở đây là placeholder của một prepared statement PostgreSQL theo cú pháp tham số phù hợp với driver/protocol; không đưa trực tiếp tenant ID do client tự khai báo mà chưa xác thực.

RLS có thể bổ sung một lớp bảo vệ database, nhưng cần hiểu thiết lập policy, quyền owner, superuser, role có `BYPASSRLS` và ngữ cảnh session/connection pool. **Bật RLS mà cấu hình sai không tự bảo đảm cô lập tenant.**

Nếu ứng dụng cần tuân thủ kiểm toán, mã hóa dữ liệu, quản lý khóa, vùng lưu trữ và kiểm soát truy cập chặt chẽ, đánh giá thêm nhà cung cấp hạ tầng và quy trình vận hành. DBMS là một lớp, không thay toàn bộ mô hình bảo mật.

## 17. Chọn managed PostgreSQL hay tự quản trị?

### Managed service

Ưu điểm thường là giảm khối lượng vận hành ở các mảng như provision instance, snapshot, patching/monitoring và một số cơ chế HA tùy gói dịch vụ.

Những điều vẫn phải quyết định:

- Kích thước instance, chỉ mục, SQL và mô hình transaction.
- RPO/RTO thực tế so với cam kết của nhà cung cấp.
- Khả năng restore theo thời điểm và kiểm tra backup.
- Giới hạn extension, quyền superuser và khả năng custom tuning.
- Chi phí I/O, lưu trữ, snapshot, replica, network egress.
- Rủi ro phụ thuộc vào các tính năng đặc thù của nền tảng.

### Tự quản trị

Có nhiều khả năng kiểm soát cấu hình, extension, network và quy trình HA/backup hơn, nhưng phải chịu trách nhiệm lớn hơn đối với security patching, recovery, monitoring, capacity planning, failover và diễn tập sự cố.

**Chi phí sở hữu (TCO)** phải gồm cả thời gian kỹ sư trực vận hành. Một dịch vụ có phí thuê cao hơn đôi khi rẻ hơn phương án tự quản trị khi tính đầy đủ công sức và rủi ro.

## 18. Checklist kỹ thuật của một proof of concept

Trước khi chọn PostgreSQL cho một hệ thống quan trọng, nên có PoC với dữ liệu và kiểu tải gần thực tế.

### 18.1. Mô tả workload

Thu thập:

- Số hàng và kích thước trung bình/tối đa ở từng bảng.
- Tỷ lệ đọc/ghi và các thao tác phổ biến.
- Những truy vấn quan trọng, join và sort.
- Số transaction đồng thời, tỷ lệ update cùng một bản ghi.
- Mục tiêu p50/p95/p99 cho các API trọng yếu.
- Tốc độ tăng trưởng dữ liệu và thời gian cần lưu.
- Mức chậm replica chấp nhận được, RPO/RTO.

### 18.2. Tạo schema và chỉ mục thật

Đừng benchmark bằng một bảng `id, value` nếu hệ thống có 15 bảng quan hệ, JSONB, báo cáo và cập nhật tồn kho. Thiết kế schema đại diện, gồm constraint, index và tỷ lệ dữ liệu gần production.

### 18.3. Đo truy vấn với EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, o.created_at, c.email
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'pending'
ORDER BY o.created_at
LIMIT 100;
~~~

Quan sát số hàng thực tế, kế hoạch dùng index, join strategy và chi phí I/O. Không chỉ nhìn “total execution time” ở bảng rất nhỏ có dữ liệu hoàn toàn nằm trong cache.

### 18.4. Đo write contention và transaction

Chạy các transaction thực tế dưới số connection tương ứng workload. Đánh giá số lỗi serialization/deadlock, lock wait, throughput và latency ở p99. Điều chỉnh transaction duration và connection pool trước khi tăng kích thước instance.

### 18.5. Diễn tập backup và failover

Một PoC hạ tầng có thể mô phỏng:

1. Mất primary trong môi trường thử nghiệm.
2. Promote replica theo cơ chế điều phối đã chọn.
3. Bảo đảm writer cũ được fencing, không split-brain.
4. Chuyển endpoint ứng dụng và xác minh giao dịch.
5. Restore từ backup và WAL archive tới điểm thời gian định trước.
6. Đo RTO và lượng giao dịch thực tế có nguy cơ mất.

Chỉ có tài liệu “có replication” không thay thế diễn tập.

### 18.6. Đánh giá vận hành

~~~sql
SELECT version();

SHOW server_version;

SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

Các thông số này là điểm khởi đầu để quan sát, không tạo thành báo cáo hiệu năng đầy đủ. Cần bổ sung monitoring, CPU/memory/IOPS, slow queries, WAL/archive status, autovacuum, kết nối và backup health.

## 19. Ma trận ra quyết định có trọng số

Một cách thực dụng là chấm điểm PostgreSQL và các lựa chọn khác **theo yêu cầu cụ thể**. Ví dụ dưới đây chỉ minh họa phương pháp, không phải điểm số khách quan của sản phẩm.

| Tiêu chí | Trọng số ví dụ | PostgreSQL cần chứng minh điều gì? |
| --- | ---: | --- |
| Tính toàn vẹn và transaction | 25% | Constraints + concurrency test đạt |
| Độ phù hợp truy vấn | 20% | SQL/JSONB/index đúng với workload |
| Hiệu năng/khả năng mở rộng | 20% | P95/P99 và throughput đạt ở tải dự báo |
| Backup và độ sẵn sàng | 15% | Restore/failover đạt RPO/RTO |
| Năng lực vận hành đội ngũ | 10% | Có owner, runbook, monitoring |
| Chi phí và rủi ro phụ thuộc | 10% | TCO, extension, migration hợp lý |

Với từng phương án, chấm điểm từ 1 đến 5 dựa trên **bằng chứng thử nghiệm**. Điểm tổng có thể tính bằng tổng `trọng số × điểm`. Tiêu chí bắt buộc như tính toàn vẹn, tuân thủ pháp lý hoặc RPO có thể là **điều kiện loại trực tiếp**, không nên cho phép một điểm tổng cao che khuất thất bại ở yêu cầu sống còn.

Ví dụ: nếu công ty bắt buộc ghi đa vùng với độ trễ cực thấp và RPO rất chặt, PostgreSQL single-primary có thể cần kiến trúc bổ sung hoặc không đạt tiêu chí cứng — dù SQL và extensibility rất mạnh.

## 20. Những hiểu lầm phổ biến

### “PostgreSQL là SQL nên không xử lý được JSON”

Không đúng. `JSON` và `JSONB` là kiểu dữ liệu chính thức, có toán tử và chỉ mục phù hợp. Tuy nhiên, nên giữ cấu trúc quan hệ cho các khóa và bất biến cốt lõi.

### “Có MVCC thì đọc/ghi không bao giờ chặn nhau”

Không đúng. MVCC hỗ trợ consistent reads, nhưng update cùng hàng, locking reads và DDL vẫn có thể tạo lock wait. Transaction dài còn gây áp lực VACUUM.

### “Thêm nhiều read replica sẽ tăng khả năng ghi”

Không đúng với topology single-primary thông thường. Replica phân tải đọc và hỗ trợ HA; mọi ghi vẫn đi vào primary. Scale ghi ngang là bài toán kiến trúc riêng.

### “Partitioning giải quyết tất cả bảng lớn”

Không. Partitioning hữu ích khi khóa phân vùng và truy vấn phù hợp. Nó có thể làm quản trị phức tạp hơn nếu tạo quá nhiều partition hoặc dữ liệu không được lọc theo partition key.

### “Có streaming replication nghĩa là không thể mất dữ liệu”

Không. Async replication có độ trễ; failover có thể mất giao dịch chưa đến replica. RPO phụ thuộc chế độ replication, cấu hình và quy trình chuyển vai trò.

### “Có backup tự động nghĩa là phục hồi chắc chắn”

Không. Cần kiểm tra backup đúng phạm vi, WAL archive liên tục, khả năng restore và thời gian đạt RTO bằng diễn tập.

### “JSONB thay thế hoàn toàn thiết kế schema”

Không. JSONB tăng linh hoạt nhưng việc tham chiếu khóa, enforce uniqueness, tối ưu kiểu số và chuẩn hóa dữ liệu vẫn cần thiết kế kỹ.

### “PostgreSQL miễn phí nên tổng chi phí bằng không”

Phần mềm có giấy phép nguồn mở thân thiện, nhưng vận hành, ổ đĩa, CPU, replication, backup, kỹ sư và ứng phó sự cố vẫn có chi phí.

### “Mỗi tính năng cần một extension là tốt hơn”

Không nhất thiết. Extension mở rộng năng lực nhưng mang thêm vòng đời nâng cấp, khả năng tương thích và giới hạn của dịch vụ triển khai.

## 21. Tình huống chọn kiến trúc

**Tình huống A — Ứng dụng bán hàng của nhóm nhỏ:** Có khách hàng, giỏ hàng, đơn hàng, chi tiết đơn, thanh toán; vài triệu bản ghi, cần transaction và SQL báo cáo. **PostgreSQL thường là một lựa chọn rất hợp lý**. Bắt đầu với schema quan hệ, index và backup/monitoring trước khi thêm dịch vụ dữ liệu khác.

**Tình huống B — Kho dữ liệu phân tích hành vi hàng trăm tỷ sự kiện:** Chủ yếu quét tập dữ liệu lớn để tính aggregate, ít cập nhật từng hàng, ưu tiên query columnar. **Cần đánh giá warehouse/OLAP chuyên dụng**, có thể giữ PostgreSQL làm nguồn giao dịch và đẩy sự kiện sang hệ phân tích.

**Tình huống C — Hệ thống đặt chỗ nhiều người đồng thời:** Cần tránh bán trùng chỗ, commit nhiều thay đổi cùng nhau. PostgreSQL phù hợp về transaction và constraints, nhưng phải thiết kế khóa, isolation và retry đúng. Không có DBMS nào tự hiểu toàn bộ bất biến nghiệp vụ nếu schema/câu lệnh sai.

**Tình huống D — Danh mục sản phẩm có thông số biến thiên:** Phần cơ bản là bảng quan hệ, thuộc tính khác nhau theo nhóm sản phẩm. PostgreSQL cùng `JSONB` có thể cung cấp mô hình hỗn hợp đơn giản. Nếu phần lớn truy vấn là tìm kiếm tài liệu ngôn ngữ tự nhiên nâng cao, cân nhắc công cụ search riêng.

**Tình huống E — Ứng dụng di động chạy offline:** Cần database nhúng trực tiếp trên thiết bị. SQLite hoặc cơ chế lưu trữ cục bộ thường phù hợp hơn PostgreSQL server; PostgreSQL vẫn có thể đóng vai trò backend đồng bộ.

**Tình huống F — Hệ thống phân tán ghi trên nhiều khu vực địa lý:** Nhiều writer độc lập, mất kết nối liên vùng, latency chặt. **Không tự giả định PostgreSQL một primary giải quyết yêu cầu**. Cần đánh giá distributed SQL, phân vùng/sharding và những đánh đổi nhất quán–sẵn sàng.

## 22. Kết luận: chọn PostgreSQL khi các giá trị cốt lõi khớp nhu cầu

PostgreSQL là lựa chọn mạnh khi bạn cần **một nền tảng dữ liệu quan hệ đáng tin cậy**, SQL phong phú, transaction rõ ràng, ràng buộc toàn vẹn và khả năng tiến hóa schema. `JSONB` và extension mở rộng phạm vi ứng dụng nhưng không xóa bỏ nhu cầu mô hình hóa dữ liệu hoặc đánh giá giới hạn.

Trước khi quyết định, hãy có câu trả lời bằng số liệu cho năm câu hỏi:

1. **Dữ liệu và bất biến nghiệp vụ** có được PostgreSQL diễn tả và bảo vệ tốt không?
2. **Các truy vấn và transaction quan trọng** có đạt độ trễ/throughput ở tải dự báo không?
3. **Tăng trưởng và đồng thời** có được xử lý bằng index, tài nguyên, partition/replica hoặc kiến trúc được chứng minh không?
4. **Backup, failover và vận hành** có đáp ứng RPO/RTO, nguồn lực và tiêu chuẩn bảo mật không?
5. **Tổng chi phí và khả năng thay đổi** có hợp lý hơn các lựa chọn thay thế đối với chính bài toán này không?

Nếu các câu trả lời dựa trên một PoC đại diện đều đạt, PostgreSQL là nền tảng rất đáng tin cậy cho nhiều ứng dụng nghiệp vụ. Nếu có tiêu chí cứng không đạt, nên điều chỉnh kiến trúc hoặc chọn công nghệ phù hợp hơn, thay vì cố ép mọi loại dữ liệu và tải truy vấn vào cùng một hệ quản trị.
