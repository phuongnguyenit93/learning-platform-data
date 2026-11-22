# Kết hợp điều kiện nghiệp vụ với kết quả tìm kiếm trong PostgreSQL

## 1. Tìm thấy văn bản chưa có nghĩa được phép hiển thị kết quả

Một người dùng tìm từ khóa **PostgreSQL** trên sàn học liệu. Cơ sở dữ liệu có nhiều sản phẩm chứa từ đó, nhưng không phải kết quả nào cũng nên xuất hiện:

- Sản phẩm thuộc **tenant khác**.
- Sản phẩm đang ở trạng thái nháp hoặc bị kiểm duyệt.
- Sản phẩm đã **xóa mềm**.
- Người bán chưa được xác minh hoặc tài khoản đang bị đình chỉ.
- Sản phẩm chưa tới thời điểm phát hành hoặc đã hết hạn.
- Hết hàng hoặc không hỗ trợ quốc gia của người mua.
- Giá nằm ngoài khoảng người dùng chọn.
- Không thuộc danh mục hoặc không có thẻ (*tag*) cần tìm.

Một search endpoint đúng không chỉ trả các hàng match từ khóa, mà trả **giao của tập được phép xem, tập đủ điều kiện nghiệp vụ và tập khớp tìm kiếm**, sau đó mới xếp hạng/phân trang.

```text
Toàn bộ sản phẩm
       |
       v
[Phạm vi truy cập: tenant, quyền, RLS]
       |
       v
[Điều kiện hiển thị: published, deleted, seller]
       |
       v
[Điều kiện kinh doanh: thời gian, stock, giá, vùng]
       |
       v
[Điều kiện tìm kiếm: FTS / LIKE / ILIKE / trigram]
       |
       v
[Điểm liên quan + quy tắc xếp hạng]
       |
       v
[ORDER BY ổn định + LIMIT / cursor]
       |
       v
Kết quả mà người dùng thực sự được xem
```

Sơ đồ mô tả **ngữ nghĩa mong muốn**, không có nghĩa PostgreSQL bắt buộc thực thi từng predicate theo đúng thứ tự vẽ. Planner có thể sắp xếp lại phép lọc và dùng index/joins miễn kết quả tuân thủ semantics và ràng buộc bảo mật thích hợp.

> **Nguyên tắc cốt lõi:** những điều kiện bắt buộc về tenant, quyền xem, trạng thái và hiệu lực phải áp dụng cho **toàn bộ tập ứng viên** trước khi xác định “20 kết quả tốt nhất”. Đừng lấy 20 hàng được xếp hạng từ toàn bảng rồi mới lọc điều kiện nghiệp vụ.

## 2. Mục tiêu bài học

Sau khi học, bạn có thể:

1. Phân biệt **search predicate**, **business eligibility**, **authorization** và **presentation filter**.
2. Kết hợp tìm kiếm văn bản với tenant, người bán, trạng thái, xóa mềm, thời gian, giá, khu vực và tồn kho.
3. Dùng `AND` / `OR` với dấu ngoặc để tránh trả ra dữ liệu không hợp lệ.
4. Dùng `JOIN`, `EXISTS`, `NOT EXISTS` và xử lý các quan hệ một-nhiều mà không nhân bản kết quả.
5. Viết câu SQL tham số hóa dùng PostgreSQL Full Text Search (FTS) và `websearch_to_tsquery`.
6. Kết hợp `ILIKE`/`pg_trgm` với FTS đúng semantics.
7. Phân biệt **lấy top N rồi lọc** với **lọc rồi lấy top N**.
8. Dùng `ts_rank`/`ts_rank_cd`, tín hiệu nghiệp vụ, thứ tự ổn định và pagination.
9. Tính total count và category facets trên đúng tập kết quả đã được lọc.
10. Chọn B-tree, GIN FTS, GIN trigram, composite/partial index phù hợp.
11. Đọc `EXPLAIN (ANALYZE, BUFFERS)` để biết điều kiện nào được áp dụng ở đâu.
12. Hiểu tác động của thống kê, skew và custom/generic prepared plans.
13. Giữ tenant isolation và quyền truy cập khi xây dựng truy vấn động.
14. Thiết kế API/JDBC với bind parameters, giới hạn kết quả và kiểm soát chi phí.
15. Biết khi nào cần kiểm tra lại giá/tồn kho ở transaction đặt hàng.
16. Tổ chức benchmark và đánh giá kết quả bằng dữ liệu, không chỉ bằng số dòng SQL.

## 3. Bốn lớp điều kiện không nên trộn lẫn

Một truy vấn tìm kiếm thường có bốn lớp khái niệm.

| Lớp | Ví dụ | Tính chất |
| --- | --- | --- |
| Authorization | `tenant_id = :tenant`, ACL, RLS | **Bắt buộc**, không do người dùng tự loại bỏ |
| Business eligibility | `status = 'PUBLISHED'`, người bán hợp lệ, không xóa mềm | Điều kiện sản phẩm có thể xuất hiện |
| User-selected filters | Danh mục, khoảng giá, vùng, thẻ, rating | Phụ thuộc bộ lọc do người dùng chọn |
| Text matching | FTS, `ILIKE`, trigram, regex | Xác định nội dung phù hợp từ khóa |
| Ranking/pagination | Relevance, mới nhất, `LIMIT 20` | Chỉ chọn thứ tự và một phần của tập hợp hợp lệ |

Về tập hợp, kết quả cần nằm trong:

```text
VisibleProducts
  ∩ EligibleProducts
  ∩ UserFilters
  ∩ TextMatches
```

Khi sau đó lấy top N, phải lấy **top N của giao tập hợp này**.

### 3.1. Những điều kiện có thể thay đổi theo tài khoản

- Một sản phẩm có thể được bán ở Việt Nam nhưng không có ở nước khác.
- Người mua A có thể nhìn tài liệu nội bộ mà người mua B không được nhìn.
- Người bán có thể chỉ được hiển thị khi đã qua xác minh.
- Một chiến dịch có thể chỉ áp dụng cho thành viên của một nhóm cụ thể.

Do đó, search results không chỉ phụ thuộc vào từ khóa; chúng còn phụ thuộc vào **ngữ cảnh người dùng đã được xác thực**.

### 3.2. Điều kiện tìm kiếm không thay thế kiểm soát truy cập

Đừng coi việc “người dùng không biết tên sản phẩm bí mật” là cơ chế bảo mật. Nếu API tìm kiếm bỏ lọc tenant, một keyword trùng nội dung có thể làm lộ tên, số lượng, xếp hạng hoặc thuộc tính từ tenant khác.

### 3.3. Điều kiện hiển thị không đồng nghĩa điều kiện đặt hàng

`stock_qty > 0` tại thời điểm tìm kiếm chỉ là **thông tin gợi ý**. Quyết định đặt hàng còn phải kiểm tra tồn kho, giá, quyền, hạn bán và các quy tắc khác trong transaction đặt hàng để tránh race condition.

## 4. Tạo schema thực hành có dữ liệu đa tenant

Toàn bộ ví dụ chạy trong **database lab**, không chạy DDL/nạp dữ liệu trên production.

Bài dùng schema `search_rules_lab` gồm:

- `sellers`: người bán, tenant, xác minh, đình chỉ.
- `products`: sản phẩm, thông tin tìm kiếm, trạng thái kinh doanh.
- `product_tags`: thẻ nhiều-một để luyện `EXISTS`.

### 4.1. Bảng người bán

```sql
CREATE SCHEMA IF NOT EXISTS search_rules_lab;

CREATE TABLE search_rules_lab.sellers (
    seller_id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    is_verified boolean NOT NULL DEFAULT false,
    suspended_at timestamptz,
    UNIQUE (tenant_id, seller_id)
);
```

`UNIQUE (tenant_id, seller_id)` được giữ để tạo khóa ngoại tổ hợp từ sản phẩm. Dù `seller_id` đã unique riêng, việc định nghĩa composite key ở đây cho phép bảo đảm **seller và product thuộc cùng tenant** ngay ở tầng dữ liệu.

### 4.2. Bảng sản phẩm và tsvector được lưu

```sql
CREATE TABLE search_rules_lab.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    seller_id integer NOT NULL,
    category_id integer NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'DRAFT',
            'PUBLISHED',
            'HIDDEN',
            'BLOCKED'
        )),
    deleted_at timestamptz,
    published_at timestamptz,
    available_until timestamptz,
    stock_qty integer NOT NULL
        CHECK (stock_qty >= 0),
    price numeric(12,2) NOT NULL
        CHECK (price >= 0),
    country_code text NOT NULL,
    rating numeric(3,2) NOT NULL
        CHECK (rating >= 0 AND rating <= 5),
    created_at timestamptz NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('simple', coalesce(name, '')),
            'A'
        )
        ||
        setweight(
            to_tsvector('simple', coalesce(description, '')),
            'B'
        )
    ) STORED,
    FOREIGN KEY (tenant_id, seller_id)
        REFERENCES search_rules_lab.sellers
            (tenant_id, seller_id)
);
```

Cột `search_vector` là `GENERATED ALWAYS AS ... STORED`, nên PostgreSQL tính và lưu `tsvector` khi dữ liệu `name`/`description` thay đổi.

- Trọng số `A` ưu tiên từ khóa trong tên.
- Trọng số `B` áp dụng cho mô tả.
- `simple` là text-search configuration cơ bản, **không bảo đảm stemming hoặc tách từ tiếng Việt theo ngữ nghĩa tự nhiên**.
- Cấu hình text search được viết **tường minh** để query và index sử dụng nhất quán.

`tsvector` làm tăng dung lượng và chi phí ghi khi văn bản thay đổi; nó không thay thế cột gốc.

### 4.3. Bảng thẻ

```sql
CREATE TABLE search_rules_lab.product_tags (
    product_id bigint NOT NULL
        REFERENCES search_rules_lab.products(product_id),
    tag text NOT NULL,
    PRIMARY KEY (product_id, tag)
);
```

Một sản phẩm có nhiều tags, nhưng cặp `(product_id, tag)` không trùng.

### 4.4. Tạo 400 người bán chia cho 4 tenant

```sql
INSERT INTO search_rules_lab.sellers (
    seller_id, tenant_id, is_verified, suspended_at
)
SELECT
    s,
    1 + (s % 4),
    s % 11 <> 0,
    CASE
        WHEN s % 29 = 0
            THEN timestamptz '2026-03-01 00:00:00+00'
        ELSE NULL
    END
FROM generate_series(1, 400) AS v(s);
```

Trong lab, một số sellers chưa verified hoặc đã suspended. Các sellers này sẽ có sản phẩm, nhưng sản phẩm của họ **không đủ điều kiện xuất hiện** trong kết quả công khai.

### 4.5. Tạo 80.000 sản phẩm

```sql
INSERT INTO search_rules_lab.products (
    tenant_id,
    seller_id,
    category_id,
    name,
    description,
    status,
    deleted_at,
    published_at,
    available_until,
    stock_qty,
    price,
    country_code,
    rating,
    created_at
)
SELECT
    1 + (v.seller_id % 4),
    v.seller_id,
    1 + (v.g % 8),
    CASE
        WHEN v.g % 13 = 0
            THEN 'PostgreSQL Tuning Handbook ' || v.g
        WHEN v.g % 11 = 0
            THEN 'Java Data Guide ' || v.g
        WHEN v.g % 7 = 0
            THEN 'SQL Index Workshop ' || v.g
        ELSE
            'Learning Database ' || v.g
    END,
    CASE
        WHEN v.g % 17 = 0
            THEN 'PostgreSQL search planner and performance'
        WHEN v.g % 19 = 0
            THEN 'Index design, ranking and query planning'
        ELSE
            'Database foundations and practical exercises'
    END,
    CASE
        WHEN v.g % 23 = 0 THEN 'BLOCKED'
        WHEN v.g % 9  = 0 THEN 'HIDDEN'
        WHEN v.g % 5  = 0 THEN 'DRAFT'
        ELSE 'PUBLISHED'
    END,
    CASE
        WHEN v.g % 31 = 0
            THEN timestamptz '2026-05-01 00:00:00+00'
        ELSE NULL
    END,
    CASE
        WHEN v.g % 41 = 0
            THEN timestamptz '2027-01-01 00:00:00+00'
        ELSE timestamptz '2026-01-01 00:00:00+00'
    END,
    CASE
        WHEN v.g % 43 = 0
            THEN timestamptz '2026-06-01 00:00:00+00'
        ELSE NULL
    END,
    v.g % 37,
    (v.g % 10000)::numeric / 10 + 1,
    CASE
        WHEN v.g % 3 = 0 THEN 'VN'
        ELSE 'US'
    END,
    (v.g % 51)::numeric / 10,
    timestamptz '2026-01-01 00:00:00+00'
        + (v.g % 200) * interval '1 hour'
FROM (
    SELECT
        g,
        ((g - 1) % 400) + 1 AS seller_id
    FROM generate_series(1, 80000) AS s(g)
) AS v;
```

Mỗi tenant có khoảng **20.000** sản phẩm. Dữ liệu được thiết kế có chủ đích để có cả:

- Hàng đủ điều kiện bán và hàng không đủ điều kiện.
- Người bán verified/chưa verified và suspended.
- Hàng chưa phát hành hoặc đã hết hạn.
- Sản phẩm có tồn kho bằng 0.
- Hai vùng `VN` / `US`.
- Từ khóa trong `name` và `description`.
- Mức giá, rating và category khác nhau.

Một điểm cần chú ý: vì `tenant_id` và `category_id` đều được sinh dựa trên `g`, **hai cột có tương quan**. Không nên giả định mọi tenant có đều cả tám categories. Đây cũng là tình huống để học về selectivity và extended statistics.

### 4.6. Nạp tags

```sql
INSERT INTO search_rules_lab.product_tags (
    product_id, tag
)
SELECT
    product_id,
    CASE
        WHEN product_id % 3 = 0 THEN 'premium'
        ELSE 'general'
    END
FROM search_rules_lab.products;

INSERT INTO search_rules_lab.product_tags (
    product_id, tag
)
SELECT product_id, 'discount'
FROM search_rules_lab.products
WHERE product_id % 17 = 0;
```

Một số sản phẩm có cả tag `premium`/`general` và `discount`.

### 4.7. Tạo các chỉ mục cơ bản

```sql
CREATE INDEX products_search_gin_idx
ON search_rules_lab.products
USING gin (search_vector);

CREATE INDEX products_tenant_status_idx
ON search_rules_lab.products (
    tenant_id, status, category_id, price
);

CREATE INDEX products_seller_idx
ON search_rules_lab.products (
    tenant_id, seller_id
);

ANALYZE search_rules_lab.products;
ANALYZE search_rules_lab.sellers;
ANALYZE search_rules_lab.product_tags;
```

Các index phục vụ thực hành so sánh; chúng **không bảo đảm** mọi truy vấn đều dùng index. Trong production, tránh tạo nhiều index trùng chức năng nếu chưa đo workload.

### 4.8. Kiểm tra dữ liệu đã sinh

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS n
FROM search_rules_lab.products
GROUP BY tenant_id, status
ORDER BY tenant_id, status;

SELECT
    COUNT(*) AS all_products,
    COUNT(*) FILTER (
        WHERE stock_qty = 0
    ) AS out_of_stock,
    COUNT(*) FILTER (
        WHERE deleted_at IS NOT NULL
    ) AS soft_deleted,
    COUNT(*) FILTER (
        WHERE available_until IS NOT NULL
    ) AS with_end_date
FROM search_rules_lab.products;
```

## 5. Tìm kiếm văn bản cơ bản: tập ứng viên chưa phải kết quả nghiệp vụ

Đầu tiên, chỉ xem text matching:

```sql
SELECT
    product_id,
    tenant_id,
    name,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('simple', 'postgresql')
    ) AS relevance
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', 'postgresql')
ORDER BY relevance DESC, product_id DESC
LIMIT 20;
```

Giải thích:

- `websearch_to_tsquery` biến chuỗi tìm kiếm thông thường thành `tsquery` với cú pháp web-style được hỗ trợ.
- `@@` kiểm tra `tsvector` có khớp `tsquery`.
- `ts_rank_cd` đo mức liên quan theo cơ chế cover density và trọng số từ vựng.
- `ORDER BY relevance DESC` xếp kết quả theo điểm.
- `product_id DESC` là tie-breaker bảo đảm thứ tự xác định trong những kết quả cùng điểm.

**Vấn đề:** query chưa có điều kiện tenant, status, deleted, seller, stock, thời gian, giá và vùng. Nó chỉ là bước minh họa FTS. **Không đưa query này làm public endpoint**.

### 5.1. Kết quả FTS có thể gồm những hàng không được phép xem

Một tài liệu draft có `PostgreSQL` trong title vẫn có thể match `@@`. Search engine không tự biết trạng thái kinh doanh nào là công khai nếu không được chỉ định.

### 5.2. Search ranking không xác lập quyền truy cập

Một kết quả có relevance rất cao vẫn phải bị loại nếu tenant không được phép hoặc sản phẩm bị BLOCKED.

### 5.3. Filter không phải trang trí sau tìm kiếm

Kết quả đúng phải được xác định bằng **toàn bộ điều kiện** trước `ORDER BY ... LIMIT`, không phải chỉ thêm vài bước xử lý phía UI.

## 6. Định nghĩa tập sản phẩm đủ điều kiện hiển thị

Một quy tắc kinh doanh minh họa:

Sản phẩm được hiển thị công khai cho một người mua khi:

1. Thuộc tenant đã xác thực.
2. `status = 'PUBLISHED'`.
3. `deleted_at IS NULL`.
4. `published_at <= as_of`.
5. `available_until IS NULL OR available_until > as_of`.
6. `stock_qty > 0`.
7. Người bán `is_verified = true`.
8. Người bán chưa bị đình chỉ.
9. `country_code` nằm trong phạm vi bán cho người mua.

Dùng mốc thời gian cố định trong ví dụ để chạy lặp lại:

```sql
WITH context AS (
    SELECT
        2::integer AS tenant_id,
        'VN'::text AS country_code,
        timestamptz '2026-11-14 00:00:00+00'
            AS as_of
)
SELECT
    p.product_id,
    p.name,
    p.price,
    p.stock_qty
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN context AS c
WHERE p.tenant_id = c.tenant_id
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.published_at <= c.as_of
  AND (
      p.available_until IS NULL
      OR p.available_until > c.as_of
  )
  AND p.stock_qty > 0
  AND s.is_verified = true
  AND s.suspended_at IS NULL
  AND p.country_code = c.country_code
ORDER BY p.product_id DESC
LIMIT 20;
```

Đây là bộ lọc eligibility **không có keyword**. Ta sẽ kết hợp nó với text matching ở phần tiếp theo.

### 6.1. Vì sao join có cả tenant_id?

```sql
ON s.tenant_id = p.tenant_id
AND s.seller_id = p.seller_id
```

Ngoài khóa ngoại tổ hợp của lab, điều kiện này biểu thị rõ mối quan hệ theo tenant trong truy vấn. Trong hệ thống đa tenant, join sai khóa có thể dẫn đến dữ liệu lẫn tenant nếu schema cho phép identifiers trùng nhau.

### 6.2. `IS NULL` của xóa mềm

```sql
AND p.deleted_at IS NULL
```

Không dùng:

```sql
AND p.deleted_at = NULL
```

vì so sánh bằng NULL trong SQL thường trả UNKNOWN, không phải TRUE.

### 6.3. Điều kiện thời điểm kết thúc là nửa mở

```sql
p.available_until IS NULL OR p.available_until > as_of
```

nghĩa là nếu thời điểm kết thúc bằng đúng `as_of` thì sản phẩm **hết hiệu lực**.

Quy tắc này phải do nghiệp vụ xác định. Một số hệ thống muốn bao gồm cả thời điểm kết thúc; khi đó semantics thay đổi. Không thay `>` bằng `>=` tùy tiện.

### 6.4. Tồn kho và khả năng đặt hàng

`stock_qty > 0` chỉ mô tả một snapshot sản phẩm đủ điều kiện hiển thị. Tới lúc checkout, tồn kho có thể thay đổi. Không dựa vào kết quả search làm nguồn duy nhất để chốt giao dịch.

## 7. Kết hợp eligibility và tìm kiếm trong một query

Bây giờ thêm `@@` và ranking vào query đầy đủ.

```sql
WITH context AS (
    SELECT
        2::integer AS tenant_id,
        'VN'::text AS country_code,
        timestamptz '2026-11-14 00:00:00+00'
            AS as_of,
        websearch_to_tsquery(
            'simple', 'PostgreSQL'
        ) AS tsq
)
SELECT
    p.product_id,
    p.name,
    p.price,
    p.rating,
    p.created_at,
    ts_rank_cd(p.search_vector, c.tsq) AS relevance
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN context AS c
WHERE p.tenant_id = c.tenant_id
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.published_at <= c.as_of
  AND (
      p.available_until IS NULL
      OR p.available_until > c.as_of
  )
  AND p.stock_qty > 0
  AND p.country_code = c.country_code
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.search_vector @@ c.tsq
ORDER BY
    relevance DESC,
    p.created_at DESC,
    p.product_id DESC
LIMIT 20;
```

Đây là một **query nhất quán về điều kiện**: không hàng nào bị trả chỉ vì match keyword khi không đủ điều kiện kinh doanh.

### 7.1. CTE context nhằm thống nhất tham số

`context` giữ các giá trị ngữ cảnh của request:

- Tenant.
- Vùng.
- Mốc thời gian.
- Tsquery.

Cách viết này giúp minh họa semantics và tránh lặp `websearch_to_tsquery` khắp câu SQL.

### 7.2. Không giả định CTE là một bước vật lý chạy trước

Từ PostgreSQL 12, một số CTE có thể được inline tùy cấu trúc/optimizer. Quan trọng là **ngữ nghĩa tổng thể** của query, không phải tin rằng viết CTE trước sẽ bắt executor chạy nó trước.

### 7.3. Không bắt buộc cùng một path scan cho mọi keyword

Planner có thể chọn GIN search index, B-tree business index, bitmap kết hợp, hoặc Seq Scan tùy mức chọn lọc. Tối ưu đúng được đánh giá bằng `EXPLAIN`, không phải số điều kiện WHERE.

## 8. Tham số hóa query đầy đủ

Trong ứng dụng, không hardcode tenant từ client hoặc chèn raw user text vào SQL.

Ví dụ SQL-level `PREPARE`:

```sql
PREPARE search_products(
    integer,
    text,
    text,
    timestamptz,
    numeric,
    numeric
) AS
WITH q AS (
    SELECT websearch_to_tsquery('simple', $2) AS tsq
)
SELECT
    p.product_id,
    p.name,
    p.price,
    p.rating,
    ts_rank_cd(p.search_vector, q.tsq) AS relevance
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN q
WHERE p.tenant_id = $1
  AND p.country_code = $3
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.published_at <= $4
  AND (
      p.available_until IS NULL
      OR p.available_until > $4
  )
  AND p.stock_qty > 0
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.price >= $5
  AND p.price <= $6
  AND p.search_vector @@ q.tsq
ORDER BY
    relevance DESC,
    p.product_id DESC
LIMIT 20;
```

Thực thi:

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE search_products(
    2,
    'PostgreSQL',
    'VN',
    timestamptz '2026-11-14 00:00:00+00',
    10.00,
    500.00
);

DEALLOCATE search_products;
```

### 8.1. Tenant lấy từ context đã xác thực

`$1` phải được ứng dụng lấy từ **authorization context đã xác minh**, không tin trực tiếp một trường `tenant_id` người dùng tùy ý sửa trong HTTP request.

### 8.2. Giá và kiểu tham số

`numeric` được sử dụng cho khoảng tiền trong lab. Với hệ thống nhiều loại tiền tệ, cần có `currency_code` và quy tắc chuyển đổi/so sánh thống nhất; đừng so giá VND và USD như cùng một đơn vị.

### 8.3. Mốc thời gian từ request hoặc hệ thống

Trong API thực tế, `as_of` thường do server xác định, không cho user tùy chọn một mốc tương lai để xem hàng chưa được phát hành, trừ khi nghiệp vụ cho phép.

### 8.4. PREPARE chỉ tồn tại trong session

`PREPARE`/`EXECUTE` là cơ chế theo session PostgreSQL. Trong Java/JDBC, driver có thể quản lý prepared statements khác SQL-level `PREPARE`; parameterization không đảm bảo luôn dùng generic plan.

## 9. AND/OR: một dấu ngoặc có thể gây lộ kết quả

Đây là lỗi rất nghiêm trọng.

### 9.1. Sai: OR phá phạm vi tenant

```sql
-- SAI: nhánh sau OR không bị tenant/status giới hạn.
SELECT p.product_id, p.name, p.tenant_id
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.name ILIKE '%PostgreSQL%'
   OR p.description ILIKE '%PostgreSQL%';
```

Trong SQL, `AND` có độ ưu tiên cao hơn `OR`, nên câu trên được hiểu là:

```text
(tenant_id = 2
 AND status = PUBLISHED
 AND name ILIKE ...)
OR
(description ILIKE ...)
```

Nhánh thứ hai có thể trả sản phẩm từ **bất kỳ tenant**, kể cả draft/blocked/deleted nếu có keyword trong description.

### 9.2. Đúng: nhóm các nhánh tìm văn bản

```sql
SELECT p.product_id, p.name, p.tenant_id
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND (
      p.name ILIKE '%PostgreSQL%'
      OR p.description ILIKE '%PostgreSQL%'
  );
```

Lúc này tenant/status/deleted áp dụng cho **cả hai nhánh từ khóa**.

Đây vẫn chỉ là ví dụ boolean đúng về ba điều kiện, **chưa có seller/stock/time/country** như query công khai đầy đủ.

### 9.3. Quy tắc thực hành

Khi có nhiều nhánh keyword:

```sql
WHERE mandatory_condition_1
  AND mandatory_condition_2
  AND mandatory_condition_3
  AND (
      text_condition_A
      OR text_condition_B
  )
```

Đừng ghép các chuỗi điều kiện từ nhiều hàm ứng dụng mà không biết precedence.

### 9.4. OR phức tạp còn ảnh hưởng performance

`OR` giữa hai predicates có thể khiến planner chọn Seq Scan hoặc BitmapOr nếu indexes phù hợp. Ngay khi query đúng semantics, cần kiểm tra nó có index paths hiệu quả không.

## 10. Lọc rồi LIMIT khác hẳn LIMIT rồi lọc

Một lỗi phổ biến là lấy top 20 raw search matches rồi mới áp dụng business rules.

### 10.1. Ví dụ sai

```sql
WITH top_text_matches AS MATERIALIZED (
    SELECT
        p.product_id,
        p.name,
        p.status,
        p.deleted_at,
        p.stock_qty,
        ts_rank_cd(
            p.search_vector,
            websearch_to_tsquery('simple', 'PostgreSQL')
        ) AS relevance
    FROM search_rules_lab.products AS p
    WHERE p.search_vector @@
          websearch_to_tsquery('simple', 'PostgreSQL')
    ORDER BY relevance DESC, product_id DESC
    LIMIT 20
)
SELECT *
FROM top_text_matches
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND stock_qty > 0;
```

Câu này chỉ lọc sau khi đã **cắt tập ứng viên xuống 20 hàng**.

Ví dụ, nếu 18/20 raw matches thuộc trạng thái không hợp lệ, kết quả cuối cùng chỉ còn 2 hàng, dù bên dưới có thể có hàng nghìn sản phẩm đủ điều kiện và có relevance kế tiếp.

### 10.2. Ví dụ đúng

```sql
SELECT
    p.product_id,
    p.name,
    ts_rank_cd(
        p.search_vector,
        websearch_to_tsquery('simple', 'PostgreSQL')
    ) AS relevance
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND p.search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL')
ORDER BY relevance DESC, p.product_id DESC
LIMIT 20;
```

Ở đây toàn bộ điều kiện đã nằm **trong cùng tập kết quả trước LIMIT**.

*Lưu ý:* đây là ví dụ rút gọn cho lỗi LIMIT; query business công khai vẫn phải có điều kiện seller, thời gian và quốc gia theo phần 7.

### 10.3. Có thể lấy top K ứng viên trước khi lọc để tăng tốc không?

Đó là kỹ thuật **candidate retrieval/overfetch** đôi khi dùng trong search systems. Nhưng nếu giới hạn K trước khi áp dụng điều kiện bắt buộc, nó **không bảo đảm** trả đủ top N hợp lệ và có thể tạo rủi ro quyền truy cập nếu phạm vi truy xuất không an toàn.

Nếu sản phẩm cho phép approximate search, phải định nghĩa rõ quality/recall và **không bao giờ coi bước candidate filtering sau cùng là cơ chế bảo vệ duy nhất đối với dữ liệu không được phép truy xuất**.

### 10.4. Vì sao `MATERIALIZED` được dùng trong ví dụ sai?

Nó làm rõ ranh giới lấy `top_text_matches` trước; PostgreSQL phải tôn trọng semantics `LIMIT` bên trong subquery/CTE.

Dù CTE được inline hay không ở ví dụ khác, việc `LIMIT` trong subquery trước WHERE ngoài vẫn có thể tạo semantics “top K trước, lọc sau”.

### 10.5. Không cần ép MATERIALIZED cho query đúng

`WITH ... MATERIALIZED` đôi khi ngăn tối ưu/predicate pushdown và làm materialize nhiều hàng. Chỉ dùng khi có lý do đo được; viết business predicates cùng cấp với search matching thường rõ hơn.

## 11. JOIN một-nhiều có thể nhân bản sản phẩm

Giả sử UI cho phép lọc theo tag.

### 11.1. JOIN trực tiếp mọi tags

```sql
SELECT
    p.product_id,
    p.name,
    t.tag
FROM search_rules_lab.products AS p
JOIN search_rules_lab.product_tags AS t
  ON t.product_id = p.product_id
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
ORDER BY p.product_id
LIMIT 20;
```

Một sản phẩm có hai tags sẽ xuất hiện **hai lần**.

Nếu pagination được thực hiện sau join, 20 rows **không còn là 20 sản phẩm độc lập**.

### 11.2. Khi chỉ cần kiểm tra có tag: dùng EXISTS

```sql
SELECT
    p.product_id,
    p.name
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'discount'
  )
ORDER BY p.product_id DESC
LIMIT 20;
```

`EXISTS` trả một giá trị boolean cho từng sản phẩm. Nó không nhân số hàng chỉ vì product có nhiều tags.

### 11.3. Nếu cần xuất danh sách tags

Có thể lấy danh sách tags bằng subquery aggregate sau khi đã chọn đúng products, hoặc dùng `array_agg` với `GROUP BY` phù hợp. Phải chú ý GROUP BY/aggregate không vô tình đổi semantics ranking và pagination.

### 11.4. DISTINCT không luôn là cách sửa đúng

Thêm:

```sql
SELECT DISTINCT p.product_id, p.name ...
```

có thể che triệu chứng trùng hàng nhưng tạo extra hash/sort và không giải quyết được trường hợp một-nhiều khác làm thay đổi `COUNT`/ranking.

Hãy phân biệt:

- Cần **lọc theo sự tồn tại**: `EXISTS`.
- Cần lấy một bản ghi theo quan hệ xác định: JOIN với unique key.
- Cần tính nhiều tags: aggregate có chủ đích.

## 12. EXISTS với nhiều lựa chọn tags

### 12.1. Một trong các tags

```sql
SELECT p.product_id, p.name
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = ANY(
            ARRAY['discount', 'premium']::text[]
        )
  );
```

Đây là semantics **OR giữa tags**: tồn tại ít nhất một tag thuộc danh sách.

### 12.2. Phải có cả hai tags

```sql
SELECT p.product_id, p.name
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'premium'
  )
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'discount'
  );
```

Khác với `ANY` ở trên, hai `EXISTS` nghĩa là **AND giữa tags**.

### 12.3. Không có tag bị cấm

```sql
AND NOT EXISTS (
    SELECT 1
    FROM search_rules_lab.product_tags AS t
    WHERE t.product_id = p.product_id
      AND t.tag = 'restricted'
)
```

Đây là cú pháp dùng để **thêm vào WHERE đầy đủ** nếu nghiệp vụ cấm tag `restricted`.

### 12.4. Vì sao nên cẩn thận với NOT IN?

`NOT IN (subquery)` có semantics ba giá trị khi tập con chứa NULL. `NOT EXISTS` thường diễn đạt anti-join rõ hơn khi kiểm tra “không tồn tại hàng liên quan”.

### 12.5. Index cho lọc tag theo cả hai hướng

Trong lab, primary key `(product_id, tag)` giúp tra tags của một product. Nếu workload rất hay tìm **mọi product có một tag**, có thể cân nhắc index:

```sql
CREATE INDEX product_tags_tag_product_idx
ON search_rules_lab.product_tags (tag, product_id);
```

Thứ tự index keys ảnh hưởng khả năng truy vấn theo `tag` trước. Đừng tự tạo mọi index trong production mà chưa đo.

## 13. JOIN người bán: các điều kiện bắt buộc

Trong query công khai:

```sql
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
...
AND s.is_verified
AND s.suspended_at IS NULL
```

Điều này đảm bảo sản phẩm không xuất hiện nếu seller chưa verified hoặc đang suspended.

### 13.1. Một-nhiều và nhiều-một

Mỗi sản phẩm tham chiếu một seller theo composite foreign key; seller key là unique nên JOIN này **không nhân bản product**.

Nếu thay seller bằng bảng nhiều lịch sử trạng thái cho một seller, JOIN thiếu điều kiện chọn phiên bản hiệu lực có thể gây duplicate rows và sai kết quả.

### 13.2. EXISTS khi chỉ cần kiểm tra trạng thái seller

Có thể viết:

```sql
AND EXISTS (
    SELECT 1
    FROM search_rules_lab.sellers AS s
    WHERE s.tenant_id = p.tenant_id
      AND s.seller_id = p.seller_id
      AND s.is_verified
      AND s.suspended_at IS NULL
)
```

Cú pháp này thích hợp nếu chỉ cần xác nhận seller tồn tại và hợp lệ, không cần trả cột seller.

### 13.3. Đừng dùng LEFT JOIN rồi kiểm tra điều kiện không rõ nghĩa

Ví dụ:

```sql
FROM products p
LEFT JOIN sellers s ON ...
WHERE s.is_verified = true
```

thường loại những rows không có seller, khiến phần LEFT JOIN có hiệu ứng gần giống INNER JOIN cho điều kiện đó.

Điều này có thể **đúng** nếu sản phẩm bắt buộc phải có seller verified, nhưng không đúng nếu nghiệp vụ muốn giữ cả các sản phẩm không có thông tin seller. Hãy viết rõ yêu cầu trước khi chọn JOIN type.

### 13.4. LEFT JOIN cho thông tin hiển thị tùy chọn

Ví dụ product có thể không có một promotion row. Nếu promotion là dữ liệu phụ trợ, `LEFT JOIN` có thể phù hợp; nhưng đừng đặt một điều kiện trên bảng promotion trong WHERE rồi vô tình loại toàn bộ products không có promotion.

## 14. Dynamic filters: chỉ thêm predicate thực sự được chọn

Một API có thể nhận:

- `category_id` tùy chọn.
- `min_price` / `max_price`.
- Danh sách tags.
- `min_rating`.
- Country.
- Text query.

Có hai cách phổ biến:

1. Một câu SQL khổng lồ chứa nhiều `OR $n IS NULL`.
2. Tạo một số query variants hoặc xây dựng predicates có kiểm soát, **luôn bind values**.

### 14.1. Mẫu optional filter

```sql
WHERE p.tenant_id = $1
  AND ($2 IS NULL OR p.category_id = $2)
  AND ($3 IS NULL OR p.price >= $3)
  AND ($4 IS NULL OR p.price <= $4)
```

Cú pháp này đúng semantics nếu NULL nghĩa là “không lọc”. Nhưng nó có thể làm **generic prepared plan** khó chọn index path tối ưu cho cả NULL và non-NULL.

### 14.2. Query variants có thể dễ tối ưu hơn

Giả sử endpoint có hai chế độ:

```sql
-- Có category:
WHERE p.tenant_id = $1
  AND p.category_id = $2

-- Không có category:
WHERE p.tenant_id = $1
```

Ứng dụng có thể chọn một trong **hai SQL templates được quản lý sẵn**, bind parameters theo đúng thứ tự. Đây không phải việc chèn raw user input vào SQL.

### 14.3. Tránh bùng nổ mọi tổ hợp filters

Nếu có mười filter tùy chọn, không nhất thiết viết 2^10 query templates thủ công. Có thể xây SQL với danh sách clauses **được allowlist**, còn mọi values vẫn truyền qua bind parameters.

Cần giữ **mandatory predicates** ở mọi nhánh; không có query variant nào được phép bỏ tenant hoặc eligibility.

### 14.4. Kiểu NULL và điều kiện

`min_price = NULL` phải được định nghĩa rõ là “không giới hạn dưới”, không tự lấy 0 nếu 0 có nghĩa kinh doanh khác.

`category_id = NULL` khác với “category rỗng”. Một mảng categories rỗng có thể nghĩa “không chọn category nào” hoặc “không filter”; API phải quy định tường minh.

### 14.5. Không dùng Boolean logic không có ngoặc

Những đoạn SQL động nên được tạo thành từng predicate có ngoặc khi chứa OR:

```sql
AND (
    p.category_id = $n
    OR p.category_id = $m
)
```

Không nối `OR ...` ở cuối WHERE mà không nhóm để tránh vô hiệu hóa tenant/status predicates.

## 15. Thời gian hiệu lực và timezone

Một sản phẩm có thể:

- Đã được duyệt nhưng chưa đến giờ phát hành.
- Đang bán.
- Đã hết chương trình.
- Chỉ bán trong một khoảng ngày theo giờ địa phương.

### 15.1. Cột `timestamptz` và mốc as_of

Trong lab:

```sql
p.published_at <= $as_of
AND (
    p.available_until IS NULL
    OR p.available_until > $as_of
)
```

Các cột dùng `timestamptz` để so một **thời điểm tuyệt đối**. Query nên dùng một mốc `as_of` thống nhất cho cả điều kiện.

### 15.2. Query tại một thời điểm lặp được

```sql
SELECT COUNT(*)
FROM search_rules_lab.products AS p
WHERE p.published_at <=
      timestamptz '2026-11-14 00:00:00+00'
  AND (
      p.available_until IS NULL
      OR p.available_until >
         timestamptz '2026-11-14 00:00:00+00'
  );
```

Khi test với thời gian cố định, kết quả không phụ thuộc đồng hồ server lúc chạy.

### 15.3. Trong production

Có thể lấy `as_of` từ server hoặc truyền một thời điểm đã được xác thực. Trong transaction, `now()`/`CURRENT_TIMESTAMP` là thời gian bắt đầu transaction theo semantics PostgreSQL; một transaction kéo dài có thể dùng mốc cũ.

Nếu cần thời điểm hiện tại thật tại một bước cụ thể, xem xét hàm/thời điểm phù hợp với yêu cầu nhất quán và hiệu năng, nhưng không gọi `clock_timestamp()` trên mỗi row trong WHERE khi không cần.

### 15.4. Khoảng ngày theo giờ người dùng

Nếu UI chọn “ngày 14/11 theo giờ Việt Nam”, phải chuyển biên ngày địa phương sang **khoảng timestamptz chuẩn**:

```sql
WHERE created_at >=
      (timestamp '2026-11-14 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND created_at <
      (timestamp '2026-11-15 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
```

Dùng nửa khoảng `[start, end)` để tránh bỏ sót fractional seconds. Không ngầm coi ngày địa phương là ngày UTC.

### 15.5. Không tạo partial index có predicate thời gian “now()”

Một ý tưởng sai:

```sql
-- KHÔNG dùng:
CREATE INDEX ...
ON products (...)
WHERE available_until > now();
```

Predicate của index cần tính bất biến phù hợp; `now()` không immutable và tập hàng “còn hiệu lực lúc này” thay đổi theo thời gian ngay cả khi row không được cập nhật.

Hãy index những thành phần ổn định có ích rồi lọc điều kiện thời gian động khi truy vấn.

## 16. Giá, tiền tệ và điều kiện business có NULL

### 16.1. Khoảng giá

```sql
AND p.price >= $min_price
AND p.price <= $max_price
```

Cần xác định rõ biên bao gồm hay không, và xử lý min > max từ ứng dụng.

### 16.2. Currency

Nếu sản phẩm có nhiều loại tiền tệ, filter giá phải:

- Chọn đúng currency.
- Hoặc chuyển đổi theo tỷ giá có phiên bản/thời điểm xác định.
- Tránh so đơn vị tiền khác nhau như cùng một thang đo.

Không có index nào sửa được lỗi semantics “500 VND” so với “500 USD”.

### 16.3. Tìm hàng không có giá

Trong schema lab `price NOT NULL`. Nếu hệ thống thật cho phép `price NULL`, `price >= 100` sẽ loại các rows NULL do logic ba giá trị.

Phải quyết định sản phẩm “liên hệ để báo giá” có được hiển thị trong một khoảng giá hay không; đừng dựa vào hành vi NULL ngầm.

### 16.4. Rating và NULL

Nếu một sản phẩm chưa được đánh giá, nên mô hình hóa `rating NULL` hoặc có `review_count` theo quy tắc dữ liệu, thay vì gán điểm 0 rồi nhầm với sản phẩm thật sự bị đánh giá 0.

Schema lab chọn số rating cố định để minh họa ORDER BY; nó không định nghĩa chính sách review thực tế.

## 17. FTS, ILIKE và trigram: chọn đúng điều kiện text

### 17.1. Full Text Search

```sql
p.search_vector @@
websearch_to_tsquery('simple', $text)
```

FTS làm việc theo lexemes/tokens. Nó có thể hữu ích khi người dùng tìm theo **từ khóa** hơn là chuỗi con ở giữa từ.

### 17.2. Contains literal với ILIKE

```sql
p.name ILIKE '%postgresql%'
```

`ILIKE` dùng wildcard pattern; không phân biệt hoa/thường theo locale/collation liên quan.

### 17.3. Escape chữ người dùng muốn tìm nguyên văn

Nếu input chứa `%` hoặc `_` mà người dùng muốn tìm **đúng ký tự**, phải escape chúng:

```sql
p.name ILIKE $pattern ESCAPE '!'
```

Ứng dụng biến literal `pg_trgm` thành `%pg!_trgm%` khi muốn contains, theo escape character `!`.

Parameter binding ngăn SQL injection nhưng **không tự escape wildcard**.

### 17.4. Trigram index hỗ trợ substring

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX products_name_trgm_idx
ON search_rules_lab.products
USING gin (name gin_trgm_ops);
```

GIN trigram index có thể hỗ trợ `LIKE`/`ILIKE` với mẫu chứa literal đủ chọn lọc, nhưng **không bảo đảm hiệu quả với pattern quá ngắn hoặc mơ hồ**.

### 17.5. FTS không thay thế contains substring

Người dùng gõ `gres` và muốn tìm sản phẩm tên `PostgreSQL`: FTS theo lexeme không nhất thiết match một đoạn ở giữa từ. `ILIKE '%gres%'` với trigram index có thể phù hợp hơn.

### 17.6. ILIKE không tự tìm không dấu

Case-insensitive không mặc định đồng nghĩa accent-insensitive, không tự normalize Unicode. Nếu UX yêu cầu `cafe` tìm ra `Café`, cần thiết kế normalization/collation/search dictionary có chủ đích.

### 17.7. Kiểm soát input rỗng

`websearch_to_tsquery('simple', '')` có thể tạo tsquery không có nodes hữu ích. API cần quy định:

- Input rỗng là hiển thị danh sách sản phẩm hợp lệ?
- Hay yêu cầu người dùng nhập từ khóa?
- Hay chỉ cho search sau tối thiểu số ký tự?

Không tự thay từ khóa rỗng thành `ILIKE '%%'` rồi quét cả bảng với mỗi lượt gõ.

## 18. Kết hợp FTS và ILIKE bằng OR

Một ứng dụng có thể muốn:

- Ưu tiên FTS theo từ.
- Vẫn tìm được những cụm substring ở title.

Ví dụ:

```sql
WITH q AS (
    SELECT
        websearch_to_tsquery('simple', 'PostgreSQL')
            AS tsq,
        '%PostgreSQL%'::text AS title_pattern
)
SELECT
    p.product_id,
    p.name,
    ts_rank_cd(p.search_vector, q.tsq) AS fts_rank
FROM search_rules_lab.products AS p
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND (
      p.search_vector @@ q.tsq
      OR p.name ILIKE q.title_pattern
  )
ORDER BY
    fts_rank DESC,
    p.product_id DESC
LIMIT 20;
```

**Đây là ví dụ ghép hai kiểu text matching**, chưa gồm tất cả business filters; hãy giữ seller/stock/time/country ở query công khai hoàn chỉnh.

### 18.1. OR cần được nhóm

Ngoặc quanh hai text predicates bảo đảm những điều kiện tenant/status áp dụng cho cả hai nhánh.

### 18.2. Khi FTS không match nhưng ILIKE có match

`ts_rank_cd` có thể trả điểm 0 cho hàng không match FTS nhưng được đưa vào kết quả bởi ILIKE. Nếu muốn những hàng này có điểm phụ, hãy định nghĩa ranking rõ.

### 18.3. Ranking kết hợp phải có business meaning

Ví dụ định nghĩa:

```sql
CASE
    WHEN p.search_vector @@ q.tsq
      THEN ts_rank_cd(p.search_vector, q.tsq)
    ELSE 0
END
+
CASE
    WHEN p.name ILIKE q.title_pattern
      THEN 0.2
    ELSE 0
END AS relevance
```

Hằng `0.2` chỉ là **ví dụ thiết kế**, không phải mức boost tối ưu chung. Điểm FTS và điểm business không nhất thiết cùng thang đo. Cần đo chất lượng kết quả, không chỉ latency.

### 18.4. Index path với OR

Nếu có GIN FTS index và GIN trigram index trên name, planner có thể cân nhắc những bitmap paths tương ứng, thậm chí BitmapOr trong điều kiện thích hợp. Nó cũng có thể dùng Seq Scan nếu điều kiện quá rộng hoặc chi phí index không cạnh tranh.

### 18.5. UNION / UNION ALL

Có thể tách hai nhánh search bằng `UNION` hoặc `UNION ALL` khi cần điều khiển query shape, nhưng phải:

- Áp dụng **cùng mandatory business filters** cho cả hai nhánh.
- Tránh một product xuất hiện hai lần nếu match cả hai.
- Hợp nhất relevance theo quy tắc rõ.
- **Không LIMIT từng nhánh quá sớm** khiến mất top N toàn cục.

Tách OR thành UNION không tự động là tối ưu tốt hơn; cần benchmark.

## 19. Xếp hạng: relevance khác ưu tiên nghiệp vụ

`ts_rank_cd` cho một điểm liên quan theo văn bản. Sản phẩm còn có thể được ưu tiên theo:

- Chất lượng và số lượng đánh giá.
- Độ mới.
- Tình trạng khuyến mại.
- Tính đầy đủ nội dung.
- Hệ số ưu tiên của một chiến dịch hợp lệ.
- Sự phù hợp khu vực/ngôn ngữ.

### 19.1. Một công thức minh họa

```sql
WITH q AS (
    SELECT websearch_to_tsquery('simple', 'PostgreSQL') AS tsq
)
SELECT
    p.product_id,
    p.name,
    ts_rank_cd(p.search_vector, q.tsq)
        AS text_rank,
    (
        ts_rank_cd(p.search_vector, q.tsq)
        + (p.rating::real * 0.02::real)
    ) AS combined_score
FROM search_rules_lab.products AS p
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.search_vector @@ q.tsq
ORDER BY
    combined_score DESC,
    p.product_id DESC
LIMIT 20;
```

Đây là ví dụ **kỹ thuật tính điểm**, không phải thiết kế ranking đã được kiểm nghiệm.

### 19.2. Boost không thể vượt authorization

Nếu người bán bị suspended, dù text rank/ratings cao đến đâu, sản phẩm vẫn phải bị loại theo quy tắc nghiệp vụ.

### 19.3. Tránh bias quá mức

Nếu điểm rating đè hoàn toàn FTS, người dùng tìm từ khóa cụ thể có thể thấy kết quả liên quan thấp nhưng đánh giá cao. Cần test quality/precision với bộ truy vấn thật.

### 19.4. Có thể xếp hạng theo thứ tự ưu tiên

Thay vì cộng điểm chưa cùng thang đo:

```sql
ORDER BY
    text_rank DESC,
    p.rating DESC,
    p.created_at DESC,
    p.product_id DESC
```

Semantics này rõ: text rank là tiêu chí chính, rating chỉ phân thứ tự khi text rank bằng nhau.

### 19.5. Tie-breaker duy nhất là thiết yếu

Nếu chỉ `ORDER BY relevance DESC`, hai kết quả cùng điểm có thể đảo thứ tự qua những lần chạy. Thêm `product_id` để có total order trong cùng một snapshot và tập dữ liệu.

## 20. Cấu trúc ranking sau khi đủ điều kiện

Một cách tổ chức dễ đọc:

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
),
eligible_matches AS (
    SELECT
        p.product_id,
        p.name,
        p.price,
        p.rating,
        p.created_at,
        ts_rank_cd(p.search_vector, q.tsq) AS text_rank
    FROM search_rules_lab.products AS p
    JOIN search_rules_lab.sellers AS s
      ON s.tenant_id = p.tenant_id
     AND s.seller_id = p.seller_id
    CROSS JOIN q
    WHERE p.tenant_id = 2
      AND p.status = 'PUBLISHED'
      AND p.deleted_at IS NULL
      AND p.stock_qty > 0
      AND p.country_code = 'VN'
      AND s.is_verified
      AND s.suspended_at IS NULL
      AND p.published_at <=
          timestamptz '2026-11-14 00:00:00+00'
      AND (
          p.available_until IS NULL
          OR p.available_until >
             timestamptz '2026-11-14 00:00:00+00'
      )
      AND p.search_vector @@ q.tsq
)
SELECT *
FROM eligible_matches
ORDER BY
    text_rank DESC,
    rating DESC,
    created_at DESC,
    product_id DESC
LIMIT 20;
```

### 20.1. Lợi ích

- Tên `eligible_matches` nhấn mạnh điều kiện mandatory.
- Ranking chỉ làm việc trên rows đúng chính sách.
- Không có `LIMIT` bên trong CTE ứng viên.
- Dễ thêm category/price/tags vào cùng WHERE.

### 20.2. CTE không tự là security boundary

PostgreSQL có optimizer và CTE inlining; một CTE được đặt tên `eligible_matches` **không thay thế authorization hoặc RLS**. Bảo mật đòi hỏi quyền và ràng buộc hợp lệ ở cả query/app/database.

### 20.3. CTE không tự materialize theo kỳ vọng cũ

Trên các PostgreSQL hiện đại, nonrecursive side-effect-free CTE có thể được inline. Đừng dùng CTE chỉ để “ép lọc tenant trước” vì tưởng executor buộc thực thi theo thứ tự dòng SQL.

## 21. Pagination: lọc đúng nhưng thứ tự vẫn có thể không ổn định

### 21.1. LIMIT/OFFSET

```sql
SELECT product_id, name, price
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND status = 'PUBLISHED'
  AND deleted_at IS NULL
ORDER BY created_at DESC, product_id DESC
LIMIT 20 OFFSET 40;
```

Semantics: bỏ qua 40 kết quả đầu theo order, lấy 20 hàng tiếp theo.

**Nhược điểm:**

- OFFSET càng sâu, query có thể phải xử lý nhiều rows trước khi trả trang.
- Nếu dữ liệu thay đổi giữa các request, user có thể thấy sản phẩm lặp hoặc bị bỏ sót.
- Nếu không có tie-breaker, các rows cùng `created_at` có thể bị đảo thứ tự.

### 21.2. Keyset pagination cho thứ tự cố định

Với sort `created_at DESC, product_id DESC`:

```sql
SELECT product_id, name, created_at
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND (created_at, product_id) <
      (
          timestamptz '2026-01-05 00:00:00+00',
          5000::bigint
      )
ORDER BY created_at DESC, product_id DESC
LIMIT 20;
```

Cursor ở đây là một ví dụ; client phải lấy cặp values từ **item cuối của trang trước**, không dùng giá trị bịa đặt như một cursor production.

### 21.3. Keyset khi sort theo relevance

Với:

```sql
ORDER BY text_rank DESC,
         created_at DESC,
         product_id DESC
```

có thể dùng cursor chứa cả `text_rank`, `created_at` và `product_id`, rồi áp điều kiện so sánh tuple tương ứng nếu các kiểu/thứ tự phù hợp.

Nhưng `ts_rank_cd` phụ thuộc keyword và dữ liệu, có thể thay đổi khi sản phẩm cập nhật. Cursor phải gắn với **cùng keyword, cùng filters, cùng sort config**, và cần chính sách khi dữ liệu thay đổi.

### 21.4. Không dùng cursor từ tenant/filters khác

Cursor nên được gắn với search context hoặc kiểm tra signature/hash các filters/sort, tránh dùng lại token từ truy vấn khác tạo thứ tự sai. Giá trị cursor không được phép làm vô hiệu hóa tenant/authorization.

### 21.5. Snapshot nhất quán

Trong READ COMMITTED, mỗi statement có snapshot riêng. Search kết quả và count qua hai statements có thể không hoàn toàn cùng thời điểm nếu dữ liệu thay đổi.

Nếu nghiệp vụ yêu cầu cùng một snapshot, cần thiết kế transaction isolation thích hợp, cân nhắc chi phí giữ transaction, hoặc chấp nhận tính gần đúng/staleness đã định nghĩa cho UX.

## 22. COUNT và total hits phải theo cùng business filters

Một sai lầm thường gặp là UI hiển thị:

```text
Tìm thấy 8.000 kết quả.
```

nhưng chỉ có 200 sản phẩm được phép xem vì COUNT tính trên toàn bảng còn list query lọc tenant/eligibility.

### 22.1. Đúng: COUNT trên tập đã lọc

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
)
SELECT COUNT(*) AS total_matches
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND p.country_code = 'VN'
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.published_at <=
      timestamptz '2026-11-14 00:00:00+00'
  AND (
      p.available_until IS NULL
      OR p.available_until >
         timestamptz '2026-11-14 00:00:00+00'
  )
  AND p.search_vector @@ q.tsq;
```

Đây là COUNT của tập đúng các mandatory predicates, trước khi thêm filters tùy chọn. Nếu list còn lọc category/price/tags, COUNT phải chứa **cùng các filters đó** theo semantics của total hits.

### 22.2. COUNT toàn bộ có thể tốn chi phí

`COUNT(*)` phải xét tập candidates thỏa điều kiện để tính chính xác. Một index giúp lọc chưa chắc làm count rẻ nếu hàng triệu matches.

UX có thể dùng:

- Total count chính xác khi cần.
- Estimate/hạn chế hiển thị khi sản phẩm cho phép.
- “Có thêm kết quả” bằng cơ chế phân trang.
- Cache count theo scope và TTL nếu chấp nhận stale.

Không tự giới thiệu một estimate là con số exact.

### 22.3. `COUNT(*) OVER()`

Có thể viết:

```sql
SELECT
    p.product_id,
    p.name,
    COUNT(*) OVER () AS total_matches
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
ORDER BY p.product_id DESC
LIMIT 20;
```

Window count được tính trên tập sau WHERE, trước LIMIT ở query level này.

Nhưng **để tính total**, executor có thể phải xử lý toàn tập phù hợp, làm mất lợi ích dừng sớm của LIMIT. Và nếu trang không có hàng, client không nhận được total qua row nào.

### 22.4. Đừng COUNT sau JOIN tags sai cardinality

`COUNT(*)` trên JOIN một-nhiều có thể đếm số product-tag rows, **không phải số products**. Nếu chỉ filter theo tag, dùng `EXISTS` giúp giữ một hàng mỗi product.

## 23. Facets theo danh mục: tập đếm phải nhất quán

Search UI thường hiển thị:

```text
Kết quả tìm kiếm “PostgreSQL”
  Danh mục 2: 25
  Danh mục 6: 18
  ...
```

Các số đếm này gọi là **facets**.

### 23.1. Đếm theo category sau business filters + keyword

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
),
eligible_matches AS (
    SELECT p.product_id, p.category_id
    FROM search_rules_lab.products AS p
    JOIN search_rules_lab.sellers AS s
      ON s.tenant_id = p.tenant_id
     AND s.seller_id = p.seller_id
    CROSS JOIN q
    WHERE p.tenant_id = 2
      AND p.status = 'PUBLISHED'
      AND p.deleted_at IS NULL
      AND p.stock_qty > 0
      AND p.country_code = 'VN'
      AND s.is_verified
      AND s.suspended_at IS NULL
      AND p.published_at <=
          timestamptz '2026-11-14 00:00:00+00'
      AND (
          p.available_until IS NULL
          OR p.available_until >
             timestamptz '2026-11-14 00:00:00+00'
      )
      AND p.search_vector @@ q.tsq
)
SELECT
    category_id,
    COUNT(*) AS product_count
FROM eligible_matches
GROUP BY category_id
ORDER BY product_count DESC, category_id;
```

### 23.2. Không tính facet sau LIMIT

Sai:

```sql
WITH first_page AS (
    SELECT *
    FROM search_rules_lab.products
    WHERE tenant_id = 2
    ORDER BY product_id DESC
    LIMIT 20
)
SELECT category_id, COUNT(*)
FROM first_page
GROUP BY category_id;
```

Đây chỉ là thống kê **20 sản phẩm ở trang đầu**, không phải facet của toàn bộ kết quả tìm kiếm.

### 23.3. Self-excluding facets

Có hai semantics thường gặp khi user đang chọn category 2:

1. **Conjunctive facet:** tính categories sau khi đã áp category = 2, nên chỉ còn category 2.
2. **Disjunctive/self-excluding facet:** tính category counts với **mọi điều kiện khác**, nhưng tạm bỏ filter category đang hiển thị, để user thấy số lượng nếu chọn category khác.

Không có một hành vi mặc định đúng cho mọi UX. Phải định nghĩa trước và viết SQL tương ứng.

### 23.4. Hai dạng query count

- Query danh sách kết quả: bắt buộc mọi filters, kể cả category hiện chọn.
- Query facet category: tùy UX, có thể bỏ **chỉ** category filter, nhưng tuyệt đối giữ tenant, status, seller và các điều kiện authorization/eligibility.

Không bao giờ tính facets trên raw search matches thuộc tenant khác; ngay cả counts cũng có thể làm lộ thông tin gián tiếp.

### 23.5. Facet với tags

Nếu một product có nhiều tags, số đếm per tag có thể hợp lý khi mỗi product đóng góp một lần cho **mỗi tag**. Tuy nhiên, tổng các tag counts có thể lớn hơn total products.

Cần phân biệt “mỗi danh mục sản phẩm chỉ thuộc một category” và “một sản phẩm có nhiều tags”.

## 24. Điều kiện phân quyền và RLS

Tenant filtering trong application SQL là cần thiết nhưng không đủ để thiết kế an toàn nếu ứng dụng có nhiều truy vấn, reports hoặc endpoint.

PostgreSQL hỗ trợ **Row-Level Security (RLS)** làm lớp bảo vệ ở database khi cấu hình đúng.

### 24.1. Ý tưởng policy

Về khái niệm:

```text
Đăng nhập đã được xác minh
       |
       v
Server xác định tenant được phép
       |
       v
Role/session context tin cậy
       |
       v
RLS policy giới hạn hàng nhìn thấy
       |
       v
Query text search + business filters
```

### 24.2. Một minh họa RLS cần điều kiện triển khai

```sql
-- Ví dụ kiến trúc, không tự chạy trên lab shared role:
ALTER TABLE search_rules_lab.products
ENABLE ROW LEVEL SECURITY;

CREATE POLICY products_tenant_select_policy
ON search_rules_lab.products
FOR SELECT
USING (
    tenant_id =
    NULLIF(
        current_setting('app.tenant_id', true),
        ''
    )::integer
);
```

Trong ví dụ này, policy dùng biến cấu hình session `app.tenant_id`. **Đây không tự là cơ chế tin cậy** nếu untrusted user có thể gửi SQL trực tiếp hoặc tự thay đổi custom setting.

Để sử dụng an toàn phải thiết kế:

- Database roles và quyền connection phù hợp.
- Server xác thực tenant; không tin request-supplied tenant ID.
- Không cho khách hàng untrusted tự thực thi SQL/SET tùy ý.
- Session state được đặt/reset chính xác trong connection pool.
- Không dùng owner/superuser/role có `BYPASSRLS` để truy cập như một end-user role, trừ khi hiểu rõ semantics.
- Có chính sách cho seller data và các bảng liên quan.
- Kiểm thử policy khi query không có WHERE tenant.

### 24.3. Table owner và FORCE ROW LEVEL SECURITY

Table owner thường có thể bypass RLS theo quy tắc PostgreSQL, trừ các lựa chọn như `FORCE ROW LEVEL SECURITY` khi áp dụng; superusers và roles có `BYPASSRLS` có hành vi riêng.

Không giả định “đã ENABLE RLS thì mọi connection tuyệt đối bị hạn chế như nhau”.

### 24.4. Connection pool và SET LOCAL

Nếu dựa trên context theo transaction:

```sql
BEGIN;

SET LOCAL app.tenant_id = '2';

-- Những queries của tenant 2 trong cùng transaction.

COMMIT;
```

Phải đảm bảo query chạy **cùng connection và transaction** và app.tenant_id được lấy từ server authorization.

Đừng dùng `SET LOCAL` ngoài transaction riêng rồi kỳ vọng context tồn tại cho statement kế tiếp ở autocommit mode.

### 24.5. RLS không thay thế business eligibility

RLS tenant có thể chỉ cho xem products của tenant 2 nhưng không tự loại:

- Draft.
- Blocked.
- Đã xóa mềm.
- Seller bị suspended.
- Hết hạn.
- Hết hàng.

Nếu các thuộc tính này cũng là security rules, policy hoặc một tầng kiểm soát khác cần được thiết kế rõ, không chỉ phụ thuộc UI.

### 24.6. Không cho dùng ranking hoặc facets vượt khỏi tập được phép

Cơ chế quyền cần áp dụng cho **cả danh sách, autocomplete, suggestions, counts, facets và exports**. Một endpoint chỉ trả số đếm vẫn có thể tiết lộ sự tồn tại hoặc quy mô dữ liệu không được phép.

## 25. Không trộn filter với hậu xử lý tại ứng dụng

Giả sử API chạy:

```sql
SELECT *
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', $1)
ORDER BY product_id
LIMIT 100;
```

Sau đó Java loop:

```text
if product.tenant == currentTenant
   && product.status == PUBLISHED
   && seller.isVerified
   && stock > 0:
      show product
```

Vấn đề:

1. Database đã lấy lên hàng **ngoài phạm vi được phép**.
2. Có thể làm lộ dữ liệu trong logs/caches/serialization nếu code sai.
3. `LIMIT 100` áp trước eligibility nên không đủ top N hợp lệ.
4. Có thêm network/object allocation.
5. Count và facets nếu chạy riêng dễ không đồng bộ.
6. Ứng dụng phải tải thông tin seller cho nhiều products không đủ điều kiện.

**Giải pháp:** đưa predicates eligibility và authorization vào truy vấn database, và dùng RLS/DB roles phù hợp như defense-in-depth. Hậu xử lý chỉ dành cho các thao tác hiển thị không làm thay đổi tập hợp được phép xem.

## 26. Planner có chạy WHERE theo thứ tự viết không?

Không. SQL là declarative.

```sql
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.search_vector @@ q.tsq
```

không bảo đảm executor luôn lọc tenant trước, rồi status, rồi mới chạy FTS. PostgreSQL có thể:

- Dùng GIN index tạo candidates theo text.
- Dùng B-tree/partial index theo tenant/status.
- BitmapAnd một số bitmap indexes khi thích hợp.
- Seq Scan rồi Filter.
- Đổi join order theo thống kê.
- Push predicates vào các scan nodes trong điều kiện hợp lệ.

### 26.1. Lập kế hoạch không được làm sai semantics

Dù tối ưu thứ tự evaluation, query hợp lệ vẫn phải trả đúng tập hàng theo WHERE và JOIN semantics, với các ràng buộc SQL và security rules thích hợp.

### 26.2. Không dựa vào thứ tự WHERE để ngăn hàm nguy hiểm

Không dùng thứ tự conditions như cơ chế bảo mật hoặc để tin rằng một hàm có side effects/errors không bao giờ chạy trên rows không hợp lệ. Đối với logic bảo mật, dùng roles, policies, các biên bảo vệ thích hợp; đối với biểu thức có thể lỗi, thiết kế expression an toàn với các điều kiện type/NULL rõ ràng.

### 26.3. CTE MATERIALIZED không phải giải pháp bảo mật phổ quát

Ép materialize một tập có thể làm giảm predicate pushdown và tăng memory/temp I/O. Nó không thay thế RLS hoặc authorization và không sửa query thiếu tenant ở một nhánh UNION/OR.

## 27. Index strategy: lọc business và tìm kiếm phải phối hợp

Query kết hợp có thể dùng nhiều loại index khác nhau.

### 27.1. B-tree cho điều kiện có tính phân loại/range

```sql
CREATE INDEX products_tenant_status_category_price_idx
ON search_rules_lab.products (
    tenant_id,
    status,
    category_id,
    price
);
```

Đây là một **phương án tham khảo**. Trong lab đã có `products_tenant_status_idx` với cùng định nghĩa; không tạo index trùng này lần nữa.

B-tree thuận lợi với equality/range/order theo keys thích hợp, đặc biệt khi filter chọn rất ít rows.

### 27.2. GIN tsvector

```sql
CREATE INDEX products_search_gin_idx
ON search_rules_lab.products
USING gin (search_vector);
```

GIN giúp tìm postings/ứng viên theo lexemes. Nó không tự lưu quan hệ seller verified hay giá động để giải quyết mọi điều kiện.

### 27.3. GIN trigram cho name

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX products_name_trgm_idx
ON search_rules_lab.products
USING gin (name gin_trgm_ops);
```

Hữu ích với contains/ILIKE có literals phù hợp. Patterns quá ngắn hoặc quá phổ biến có thể không hưởng lợi.

### 27.4. Index trên seller

Lab có:

```sql
PRIMARY KEY (seller_id)
UNIQUE (tenant_id, seller_id)
```

Khi join bằng cả tenant_id/seller_id, PostgreSQL có những unique index paths phù hợp. Nhưng nếu query lọc sellers theo `is_verified` trước khi join, việc index thêm trên các trạng thái Boolean ít chọn lọc không tự bảo đảm tốt hơn.

### 27.5. Index cho tags

`PRIMARY KEY (product_id, tag)` hữu ích khi xác định tags của một product. Nếu tìm từ tag -> danh sách products là workload chủ đạo, index `(tag, product_id)` có thể đáng thử.

### 27.6. Một index không giải quyết mọi thứ

PostgreSQL có thể đi từ search GIN index, rồi lọc tenant/business, hoặc đi B-tree tenant/status rồi áp text match trên ít rows. Chọn chiến lược bằng **độ chọn lọc kết hợp**, không chỉ nhìn một predicate.

## 28. Partial indexes cho những điều kiện ít thay đổi

Một query công khai hầu như luôn cần:

```sql
status = 'PUBLISHED'
AND deleted_at IS NULL
```

Có thể tạo partial index:

```sql
CREATE INDEX products_visible_tenant_category_price_idx
ON search_rules_lab.products (
    tenant_id, category_id, price
)
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL;
```

### 28.1. Partial B-tree có thể nhỏ hơn full index

Nó chỉ chứa những rows thỏa static predicate. Nếu tỷ lệ draft/hidden/deleted cao, kích thước và scan cost có thể giảm.

### 28.2. Partial GIN cho FTS

```sql
CREATE INDEX products_visible_search_gin_idx
ON search_rules_lab.products
USING gin (search_vector)
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL;
```

Nếu hầu hết search đều chỉ cần published/not deleted, partial GIN có thể giảm số entries phải quản lý.

**Không mặc định giữ cả full GIN và partial GIN** cho production. Hai index cùng cột có thể tăng đáng kể write amplification; lựa chọn dựa trên các query cần tìm cả draft/internal.

### 28.3. Generic prepared plan và predicate

Nếu query có:

```sql
WHERE status = $1
  AND deleted_at IS NULL
```

generic plan không thể giả định `$1 = 'PUBLISHED'` cho mọi lần thực thi, nên partial index `WHERE status='PUBLISHED'` có thể không khả dụng.

Nếu endpoint **luôn tìm public products**, viết hằng nghiệp vụ:

```sql
WHERE status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND tenant_id = $1
```

vẫn bind tenant và keyword, cho phép planner xét predicate của partial index.

### 28.4. Không cho NOW() vào partial predicate

Không dùng:

```sql
-- Không hợp lệ như một index predicate bất biến:
WHERE available_until > now()
```

Tính hiệu lực thay đổi theo thời gian ngay cả khi row không update; PostgreSQL yêu cầu expressions/index predicates đủ immutable.

### 28.5. Partial index không phải policy quyền truy cập

Index predicate chỉ giới hạn những entries nằm trong index; nó **không chặn một query khác truy cập những hàng chưa public**. Quyền phải đến từ RLS/roles/app authorization phù hợp.

## 29. Có nên dùng multicolumn GIN hoặc BitmapAnd?

PostgreSQL có extension và operator classes để hỗ trợ những tổ hợp khác nhau, ví dụ `btree_gin` cho một số scalar keys trong GIN. Tuy nhiên, **multicolumn GIN** không tự thắng tổ hợp:

- GIN full-text.
- B-tree tenant/category/price.
- Bitmap Index Scan theo điều kiện đủ chọn lọc.
- BitmapAnd hoặc filter sau scan.

### 29.1. BitmapAnd là một khả năng

Một plan có thể có dạng:

```text
Bitmap Heap Scan on products
  Recheck Cond: ...
  Filter: ...
  -> BitmapAnd
       -> Bitmap Index Scan on products_search_gin_idx
       -> Bitmap Index Scan on products_tenant_status_idx
```

Đây chỉ là **kế hoạch minh họa**; planner có thể chọn path khác tùy thống kê.

### 29.2. Điều kiện tenant không tự là phần của GIN FTS

GIN index trên `search_vector` cho postings của lexeme; khi match rất phổ biến trên nhiều tenant, số candidates có thể lớn. Có thể cân nhắc chiến lược partial/partition/index khác tùy workload.

### 29.3. Không mặc định multicolumn GIN giải quyết ORDER BY

Thứ tự `ORDER BY relevance DESC` phụ thuộc keyword nên thường cần tính rank các candidates. B-tree/Gin indexes không tự cho sẵn một thứ tự relevance bất biến cho mọi truy vấn.

### 29.4. Partition by tenant có cần không?

Nếu dữ liệu cực lớn và truy vấn luôn giới hạn tenant, partitioning có thể đáng xem xét, nhưng nó mang chi phí catalog/DDL/maintenance. Không chia một bảng thành hàng nghìn partitions chỉ để tránh một truy vấn cần index tốt.

## 30. EXPLAIN khi kết hợp tìm kiếm với business predicates

Dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    p.product_id,
    p.name
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL')
ORDER BY p.product_id DESC
LIMIT 20;
```

Quan sát các yếu tố:

| Trong EXPLAIN | Cần hỏi |
| --- | --- |
| `Seq Scan` | Vì sao quét tuần tự rẻ hơn index? |
| `Bitmap Index Scan` | Index nào tìm candidates? |
| `Bitmap Heap Scan` | Heap pages nào được đọc/recheck? |
| `Index Cond` | Điều kiện nào giới hạn access qua index? |
| `Filter` | Những business/text predicates nào lọc sau scan? |
| `Rows Removed by Filter` | Có nhiều candidates bị loại vì business rules? |
| `Recheck Cond` | Điều kiện index nào được xác minh lại? |
| `Hash Join` / `Nested Loop` | Seller join được thực hiện như thế nào? |
| `rows` / `actual rows` | Planner ước lượng có sát không? |
| `Buffers` | Bao nhiêu shared hits/reads? |
| `Sort` / top-N sort | Chi phí xếp hạng và ORDER BY? |
| `Planning Time` | Có tốn nhiều thời gian lên plan không? |
| `Execution Time` | Runtime server-side của câu truy vấn? |
| `loops` | Một index/join node có bị gọi lặp nhiều lần không? |

### 30.1. Cost không phải milliseconds

`cost=0.00..1000.00` là đơn vị chi phí ước lượng của planner, không có nghĩa 1000 ms.

### 30.2. Buffers không phải số lần đọc physical disk chính xác

`shared read` nghĩa là block được đọc vào shared buffer cache; OS filesystem cache có thể phục vụ lần đọc. Lượt chạy đầu và lượt sau khác nhau vì cache state.

### 30.3. Plan có Seq Scan không tự là lỗi

Nếu keyword rất phổ biến, filter theo tenant chọn phần lớn dữ liệu hoặc bảng nhỏ, Seq Scan có thể hợp lý.

### 30.4. GIN index không đảm bảo truy vấn sẽ dùng nó

Planner so chi phí tìm candidate text, business filters, join seller, sắp xếp/giới hạn. Một index có sẵn nhưng quá ít chọn lọc có thể bị bỏ qua.

### 30.5. EXPLAIN ANALYZE thật sự chạy câu SQL

Với SELECT nó thực thi và đo. Với UPDATE/DELETE, EXPLAIN ANALYZE **thực hiện thay đổi** theo transaction. Không chạy DML có side effects trên production chỉ để xem plan.

## 31. Statistics và dữ liệu lệch

Trong lab, tenant/category/status có thể có phân bố tương quan. Sự thiếu chính xác về selectivity kết hợp có thể khiến planner chọn join/scan không tối ưu.

### 31.1. Xem thống kê cột

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname = 'search_rules_lab'
  AND tablename = 'products'
  AND attname IN (
      'tenant_id',
      'category_id',
      'status',
      'country_code'
  )
ORDER BY attname;
```

### 31.2. MCV và business values

Nếu `PUBLISHED` chiếm phần lớn rows, một B-tree index trên `status` đơn có thể không chọn lọc bằng một partial/composite index phù hợp.

Nếu một tenant cực lớn, generic plan theo tenant có thể không hiệu quả cho cả tenant lớn lẫn nhỏ.

### 31.3. Extended statistics cho cột liên quan

```sql
CREATE STATISTICS products_tenant_category_stats
    (mcv, dependencies)
ON tenant_id, category_id
FROM search_rules_lab.products;

ANALYZE search_rules_lab.products;
```

Thống kê nhiều cột có thể giúp estimates tốt hơn cho các predicates tương ứng. Nó **không tạo index** và không thay thế quyền truy cập.

### 31.4. Statistics stale

Sau bulk load, delete hoặc thay đổi phân bố lớn, chạy `ANALYZE` thích hợp. Một query trả 100 hàng nhưng planner ước lượng 100.000 có thể chọn đường truy cập không hợp lý.

### 31.5. Custom vs generic prepared plan

Truy vấn tham số hóa theo tenant/keyword/range có thể dùng custom hoặc generic plan. Với `plan_cache_mode` trong lab:

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

-- EXPLAIN (ANALYZE, BUFFERS)
-- EXECUTE search_products(...);

ROLLBACK;
```

Tương tự có thể thử `force_generic_plan`. **Không để ép custom/generic toàn database** chỉ vì một truy vấn có vấn đề; hãy đo planning overhead và execution cho nhóm tham số đại diện.

## 32. Cùng kết quả nghiệp vụ, nhiều cách thực thi

Có một vài chiến lược phổ biến:

### 32.1. GIN-first

```text
Tìm document IDs match lexeme từ GIN
    |
Đọc heap candidates
    |
Lọc tenant, status, deleted, seller, stock, time
    |
Rank và sort
```

Phù hợp khi keyword rất chọn lọc, nhưng nếu keyword cực phổ biến trong toàn bộ tenants thì ứng viên lớn.

### 32.2. Business-index-first

```text
B-tree lọc tenant/category/status
    |
Lấy tập sản phẩm nhỏ
    |
Kiểm tra text matching
    |
Rank/sort
```

Có thể tốt khi business filters rất chọn lọc.

### 32.3. Bitmap combination

```text
GIN bitmap text candidates
          +
B-tree bitmap business candidates
          |
        BitmapAnd
          |
     Bitmap Heap Scan
          |
     Recheck/other filters
```

Đây là một access path PostgreSQL có thể cân nhắc, không phải flow bắt buộc.

### 32.4. Index phù hợp không xóa chi phí ranking

Search relevance thường phụ thuộc keyword tại runtime. Dù candidates được tìm nhanh, xếp hạng hàng chục nghìn matches vẫn có CPU/sort cost.

### 32.5. Chọn bằng số liệu

Không thay `WHERE` bằng một đống CTE `MATERIALIZED` để ép join/scan order theo cảm tính. Hãy đo `EXPLAIN (ANALYZE, BUFFERS)`, kiểm tra stats và thay đổi một yếu tố có lý do.

## 33. Java/JDBC: query an toàn với tenant và bộ lọc bắt buộc

Ví dụ dùng `PreparedStatement` với business filters tĩnh và tham số từ context đáng tin cậy.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import javax.sql.DataSource;

public final class ProductSearchService {
    private final DataSource dataSource;

    public ProductSearchService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void search(
        int authenticatedTenantId,
        String queryText,
        String country,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Instant asOf
    ) throws SQLException {

        String sql = """
            WITH q AS (
                SELECT websearch_to_tsquery(
                    'simple', ?
                ) AS tsq
            )
            SELECT
                p.product_id,
                p.name,
                p.price,
                ts_rank_cd(p.search_vector, q.tsq) AS score
            FROM search_rules_lab.products AS p
            JOIN search_rules_lab.sellers AS s
              ON s.tenant_id = p.tenant_id
             AND s.seller_id = p.seller_id
            CROSS JOIN q
            WHERE p.tenant_id = ?
              AND p.country_code = ?
              AND p.status = 'PUBLISHED'
              AND p.deleted_at IS NULL
              AND p.stock_qty > 0
              AND s.is_verified
              AND s.suspended_at IS NULL
              AND p.published_at <= ?
              AND (
                  p.available_until IS NULL
                  OR p.available_until > ?
              )
              AND p.price >= ?
              AND p.price <= ?
              AND p.search_vector @@ q.tsq
            ORDER BY
                score DESC,
                p.product_id DESC
            LIMIT 20
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setString(1, queryText);
            ps.setInt(2, authenticatedTenantId);
            ps.setString(3, country);
            ps.setTimestamp(4, Timestamp.from(asOf));
            ps.setTimestamp(5, Timestamp.from(asOf));
            ps.setBigDecimal(6, minPrice);
            ps.setBigDecimal(7, maxPrice);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong("product_id")
                        + ": "
                        + rs.getString("name")
                    );
                }
            }
        }
    }
}
```

### 33.1. Không nhận tenant ID như một giá trị tùy ý từ HTTP body

`authenticatedTenantId` phải đến từ security context của server sau xác thực/ủy quyền.

### 33.2. Bind values, không nối chuỗi

`setString`, `setInt`, `setBigDecimal` và `setTimestamp` gửi data tách khỏi SQL structure. Không nối `queryText` thành SQL literal hoặc regex source trong câu SQL.

### 33.3. Validate input trước truy vấn

Cần kiểm tra:

- Keyword length và trường hợp rỗng.
- Giá min/max và currency.
- Country code nằm trong allowlist theo nghiệp vụ.
- Số lượng category/tag filters.
- Page size tối đa.
- Tham số thời gian do server kiểm soát.

### 33.4. Khi cần dynamic query builder

Chỉ ghép **những đoạn SQL cố định/allowlisted** do ứng dụng quản lý, chẳng hạn:

```java
StringBuilder sql = new StringBuilder(
    "SELECT product_id, name " +
    "FROM search_rules_lab.products " +
    "WHERE tenant_id = ? " +
    "AND status = 'PUBLISHED' " +
    "AND deleted_at IS NULL"
);

if (categoryId != null) {
    sql.append(" AND category_id = ?");
}
```

Sau đó bind các giá trị tương ứng. Ví dụ chỉ minh họa fragment; endpoint thực tế phải thêm seller/stock/time/country và text matching. Không để query builder có nhánh nào bỏ bắt buộc tenant/security clauses.

### 33.5. Không cho user truyền raw ORDER BY expression

Các tên cột/keywords của SQL không được bind như value parameters theo cùng cách. Với sort options, dùng allowlist:

```text
sort=relevance -> ORDER BY text_rank DESC, product_id DESC
sort=newest    -> ORDER BY created_at DESC, product_id DESC
sort=price_asc -> ORDER BY price ASC, product_id ASC
```

Không ghép nguyên một chuỗi `sort` lấy từ request vào SQL.

## 34. Tính nhất quán và concurrency: search không phải checkout

### 34.1. Kết quả tìm kiếm là một snapshot

Ở thời điểm T1, product có `stock_qty = 1`.

- User A search và thấy product.
- User B đặt mua và giảm stock về 0.
- User A bấm mua ở T2.

Search result tại T1 không còn phản ánh tồn kho ở T2.

### 34.2. Checkout cần giao dịch bảo vệ invariant

Một cách minh họa cho việc giữ tồn kho không âm:

```sql
BEGIN;

UPDATE search_rules_lab.products
SET stock_qty = stock_qty - 1
WHERE product_id = 1001
  AND tenant_id = 2
  AND status = 'PUBLISHED'
  AND deleted_at IS NULL
  AND stock_qty >= 1
RETURNING product_id, stock_qty;

-- Chỉ hoàn tất bước đặt hàng nếu UPDATE trả đúng 1 row,
-- đồng thời kiểm tra các quy tắc nghiệp vụ khác.
-- COMMIT hoặc ROLLBACK tùy kết quả.
ROLLBACK;
```

Đây là **thí nghiệm**, không phải quy trình checkout hoàn chỉnh. Nó cho thấy update có điều kiện kiểm tra tồn kho tại thời điểm ghi.

### 34.3. Không dùng `SELECT stock_qty` riêng rồi UPDATE vô điều kiện

Hai giao dịch đồng thời có thể cùng đọc stock=1 rồi cùng cố mua, tạo oversell nếu không có điều kiện/locking/transaction strategy phù hợp.

### 34.4. Giá và quyền cần kiểm tra lại

Giá, promotion, seller status, giới hạn mua, country policy và authorization cũng có thể thay đổi giữa search và checkout.

### 34.5. Không khóa hàng loạt products khi chạy public search

`SELECT ... FOR UPDATE` trên hàng nghìn sản phẩm trong search endpoint có thể tạo contention nghiêm trọng. Hàng đợi đặt hàng và reservation thuộc một workflow khác với tìm kiếm đọc.

## 35. Testing theo ma trận nghiệp vụ

Một query có thể trả đúng top 20 trong happy path nhưng sai trong những trường hợp biên.

| Case | Kỳ vọng |
| --- | --- |
| Product match keyword thuộc tenant khác | Không xuất hiện |
| Product ở `DRAFT` | Không xuất hiện trong public search |
| Product `BLOCKED` | Không xuất hiện |
| Product có `deleted_at` | Không xuất hiện |
| Seller chưa verified | Không xuất hiện |
| Seller bị suspended | Không xuất hiện |
| `published_at` nằm trong tương lai | Không xuất hiện |
| `available_until = as_of` | Không xuất hiện nếu rule dùng `>` |
| `available_until IS NULL` | Được coi là không có hạn kết thúc theo rule |
| `stock_qty = 0` | Không xuất hiện nếu yêu cầu còn hàng |
| `country_code` khác region | Không xuất hiện |
| Giá dưới min/trên max | Không xuất hiện |
| Hai tags phù hợp trên cùng product | Không trùng product |
| Chọn tag `discount` | Chỉ products có tag đó |
| FTS match description nhưng không name | Có thể xuất hiện nếu đủ eligibility |
| Keyword chứa `%` hoặc `_` | Đúng literal semantics nếu UI yêu cầu literal |
| Keyword rỗng | Theo policy rõ ràng, không tự quét vô hạn |
| Tất cả top raw matches bị hidden | Search vẫn tìm đủ top eligible nếu tồn tại |
| Two products bằng relevance | Stable tie-break theo ID |
| Count/facets | Không bao gồm dữ liệu ngoài phạm vi |
| Dữ liệu thay đổi giữa hai trang | Theo consistency policy đã định |

### 35.1. Kiểm tra tenant isolation bằng dữ liệu cố ý trùng keyword

Tạo hai sản phẩm cùng tên ở hai tenants, sau đó chạy search với tenant A và khẳng định **không nhận product của tenant B**.

### 35.2. Kiểm tra OR precedence

Tạo product ở tenant B có keyword chỉ trong description. Nếu query sai dạng `tenant AND name_match OR description_match`, test sẽ bắt được lỗi lộ tenant.

### 35.3. Kiểm tra LIMIT-before-filter

Tạo hơn 20 raw matches có relevance cao nhưng không đủ eligibility, và 20 matches hợp lệ có relevance thấp hơn. Search đúng phải trả đủ các matches hợp lệ theo score, không chỉ lấy rồi lọc raw top 20.

### 35.4. Kiểm tra nhiều tags

Một product match cả `premium` và `discount`. Kết quả danh sách không được xuất hiện hai lần; total count phải đếm product một lần.

### 35.5. Kiểm tra timezone

Với sản phẩm phát hành đúng mốc UTC tương ứng 00:00 ở giờ địa phương, bảo đảm điều kiện as_of và bộ lọc ngày phù hợp.

## 36. Quan sát hệ thống và kiểm soát chi phí

Trong production, tối ưu endpoint search cần số liệu thực tế:

- p50, p95, p99 latency.
- Tần suất request.
- Số rows returned.
- Tỷ lệ keyword ngắn/dài.
- Tỷ lệ FTS/ILIKE/regex.
- Số filters thường dùng.
- Số tenant nóng/lạnh.
- Buffers hit/read, CPU và I/O.
- Planning Time và Execution Time.
- Dung lượng GIN/B-tree indexes.
- Query cancellation/timeouts.
- Concurrent active search queries.
- Trạng thái autovacuum/ANALYZE.
- Chất lượng kết quả/ranking.

### 36.1. `pg_stat_statements` có thể giúp

Nếu extension đã được cài và cấu hình:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Các cột/quyền có thể khác theo phiên bản. `pg_stat_statements` thường tổng hợp normalized queries, không mặc định lưu tách từng keyword/tenant/country của mọi request.

### 36.2. Xây các nhóm benchmark

Nên thử:

- Keyword ít gặp / rất phổ biến.
- Input 1–2 ký tự / 10 ký tự / cụm nhiều từ.
- Tenant có vài nghìn hay hàng triệu sản phẩm.
- Có/không chọn category.
- Khoảng giá hẹp/rộng.
- Product tags rất phổ biến/hiếm.
- Sort relevance/newest/price.
- Trang đầu/trang sâu.
- Có seller join và stock/date predicates đầy đủ.
- Concurrent requests, không chỉ một query đơn lẻ.

### 36.3. `statement_timeout`

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

-- Chạy SELECT tìm kiếm cần đo trong transaction này.

ROLLBACK;
```

Timeout có thể ngắt một query quá lâu, **không khiến query tự tối ưu**. Với connection pool cần đúng transaction scope và cleanup.

### 36.4. Rate limit và debounce

Autocomplete không nên quét dữ liệu sau **mỗi ký tự** mà không có debounce, minimum length, pagination và concurrency limits.

### 36.5. Không log keyword/tenant nhạy cảm tùy tiện

Search queries có thể chứa thông tin cá nhân/bí mật. Quan sát bằng độ dài mẫu, loại query, số lượng kết quả hoặc hashes an toàn khi đủ, thay vì in mọi tham số nguyên văn trong logs.

## 37. Những sai lầm thường gặp

| Ngộ nhận hoặc lỗi | Hệ quả / cách hiểu đúng |
| --- | --- |
| “Match keyword thì được hiển thị” | Phải áp authorization và eligibility |
| Lọc tenant chỉ ở UI | Có thể lộ dữ liệu qua API/logs/cache |
| `tenant AND title OR description` | OR có thể vượt phạm vi tenant |
| LIMIT raw matches trước business filters | Trả thiếu top N hợp lệ |
| JOIN tags rồi LIMIT | Một product có thể chiếm nhiều rows |
| Dùng DISTINCT để chữa mọi duplicate | Có thể tốn sort/hash và che nguyên nhân |
| COUNT raw FTS matches | Phản ánh cả dữ liệu không hiển thị |
| COUNT sau LIMIT 20 | Chỉ đếm trang hiện tại |
| Facet category tính trên mọi tenant | Rò thông tin qua số liệu |
| Một product có 3 tags thì total=3 | Phải phân biệt product count và tag count |
| Status PUBLISHED là đủ | Seller, deleted, time, stock, region còn quan trọng |
| Có GIN FTS thì mọi query nhanh | Keyword phổ biến/business filters/join/sort vẫn đắt |
| Có B-tree tenant thì GIN không cần | Hai indexes phục vụ các tập predicates khác nhau |
| GIN trigram luôn tăng tốc mẫu hai ký tự | Có thể thiếu trigrams chọn lọc |
| ILIKE là tìm không dấu | Không có bảo đảm accent-insensitive |
| `websearch_to_tsquery` hiểu mọi ngôn ngữ | Tùy text search configuration/tokenization |
| CTE tên eligible là security boundary | Không thay RLS/authorization |
| WHERE chạy đúng thứ tự viết | Planner có thể tối ưu thứ tự đánh giá |
| Generic plan luôn dùng partial index status=$1 | Không thể giả định $1 là hằng PUBLISHED |
| Partial index với `now()` là tốt | Time-sensitive predicate không immutable |
| Thêm index cho mọi cột | Tăng WAL/write/storage/maintenance |
| OFFSET sâu vẫn miễn phí nhờ LIMIT | Có thể phải đi qua rất nhiều hàng |
| Không cần tie-breaker khi rank trùng | Trang kết quả có thể đổi thứ tự |
| Cursor dùng lại cho keyword khác | Có thể tạo pagination sai |
| `COUNT(*) OVER()` luôn nhanh | Có thể phải xử lý toàn tập trước LIMIT |
| Stock>0 ở search bảo đảm đặt mua được | Checkout phải xác minh lại trong transaction |
| Bind parameter escape `%`/`_` | Không; LIKE wildcard vẫn có semantics |
| `SET LOCAL` dùng ngoài transaction vẫn tồn tại | Cần transaction phù hợp |
| `EXPLAIN ANALYZE` không thực thi DML | Nó thực thi, có thể thay dữ liệu |
| Plan có Seq Scan là bug | Có thể tối ưu cho dữ liệu/độ chọn lọc hiện tại |
| Rank cao vượt qua trạng thái BLOCKED | Mandatory eligibility luôn ưu tiên |

## 38. Bài tập thực hành có lời giải

Các bài dựa trên `search_rules_lab`. Với DDL, chỉ chạy một lần trong lab; mọi query rút gọn chỉ để minh họa một khía cạnh phải được bổ sung mandatory filters nếu dùng trong endpoint thật.

### Bài 1. Vì sao search kết quả không chỉ là `@@`?

**Đáp án:** `@@` chỉ đánh giá match lexeme. Public search còn phải thỏa tenant, quyền, trạng thái, seller, soft delete, stock, thời gian, vùng và các filter khác.

### Bài 2. Tìm những products match PostgreSQL của tenant 2

```sql
SELECT product_id, name
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

**Đáp án:** đây là tập match có tenant filter; để công khai còn cần eligibility đầy đủ.

### Bài 3. Vì sao một sản phẩm DRAFT có thể match keyword?

**Đáp án:** các từ trong `name`/`description` vẫn có trong `search_vector`; status không tự được tính đến khi dùng FTS.

### Bài 4. Xóa mềm được lọc thế nào?

```sql
AND deleted_at IS NULL
```

**Đáp án:** dùng `IS NULL`, không `= NULL`.

### Bài 5. Điều kiện sale end inclusive hay exclusive?

```sql
AND (
    available_until IS NULL
    OR available_until > $as_of
)
```

**Đáp án:** ví dụ dùng biên cuối exclusive: nếu đúng bằng `as_of` thì hết hiệu lực.

### Bài 6. Viết điều kiện seller được xác minh

**Đáp án:** join bằng tenant_id/seller_id rồi lọc `s.is_verified AND s.suspended_at IS NULL`.

### Bài 7. Vì sao JOIN seller theo seller_id nhưng bỏ tenant_id có thể nguy hiểm?

**Đáp án:** với schema cho phép seller IDs trùng tenant, join có thể gắn product với seller sai phạm vi. Lab dùng FK tổ hợp; vẫn nên biểu diễn đúng relation key trong query.

### Bài 8. Nêu lỗi của `tenant = 2 AND name ILIKE X OR description ILIKE X`

**Đáp án:** SQL hiểu nhánh description riêng ngoài tenant; có thể lộ sản phẩm tenant khác.

### Bài 9. Sửa precedence

```sql
WHERE tenant_id = 2
  AND (
      name ILIKE '%PostgreSQL%'
      OR description ILIKE '%PostgreSQL%'
  )
```

**Đáp án:** bọc OR, sau đó áp thêm mọi mandatory filters còn lại.

### Bài 10. Vì sao lấy top 20 trước status filter là sai?

**Đáp án:** một số top matches không hợp lệ sẽ bị loại, khiến thiếu top 20 hợp lệ dù còn đủ candidates ở bên dưới.

### Bài 11. CTE MATERIALIZED có thay authorization không?

**Đáp án:** không; nó chỉ là một cơ chế thực thi/tối ưu, không đảm bảo quyền hoặc thay RLS.

### Bài 12. Nếu product có hai tags, JOIN trực tiếp có thể trả bao nhiêu rows?

**Đáp án:** hai rows cho một product, nếu cả hai tags join được; phải dùng EXISTS hoặc aggregate theo mục đích.

### Bài 13. Lọc products có tag discount

```sql
SELECT p.product_id
FROM search_rules_lab.products AS p
WHERE p.tenant_id = 2
  AND EXISTS (
      SELECT 1
      FROM search_rules_lab.product_tags AS t
      WHERE t.product_id = p.product_id
        AND t.tag = 'discount'
  );
```

**Đáp án:** dùng `EXISTS` giữ mỗi product một row.

### Bài 14. Phải có cả premium và discount thì làm thế nào?

**Đáp án:** dùng hai `EXISTS` nối bằng `AND` (hoặc aggregate được thiết kế cho “tất cả tags”).

### Bài 15. Chỉ cần một trong hai tags thì sao?

**Đáp án:** một `EXISTS` với `t.tag = ANY(ARRAY['premium','discount'])` là một cách.

### Bài 16. Vì sao NOT EXISTS hữu ích khi cấm tag?

**Đáp án:** diễn đạt anti-join rõ và tránh nhiều vấn đề NULL semantics của `NOT IN`.

### Bài 17. Viết query chỉ lấy stock > 0

**Đáp án:** thêm `AND p.stock_qty > 0` vào WHERE chung; vẫn phải xác minh tồn kho khi checkout.

### Bài 18. Vì sao stock trong search có thể lỗi thời?

**Đáp án:** giao dịch khác có thể bán sản phẩm sau snapshot của search; search không giữ lock/reserve stock.

### Bài 19. Dùng FTS lấy điểm liên quan

```sql
SELECT
    product_id,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('simple', 'PostgreSQL')
    ) AS score
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

**Đáp án:** `@@` lọc, `ts_rank_cd` xếp hạng; query còn cần business predicates để công khai.

### Bài 20. FTS có tự match mọi substring giữa một từ không?

**Đáp án:** không. FTS xử lý lexemes; contains substring có thể cần ILIKE/trigram.

### Bài 21. Escape underscore trong ILIKE literal

**Đáp án:** bind pattern `%pg!_trgm%` và viết `ILIKE $1 ESCAPE '!'`.

### Bài 22. Bind parameter có tự biến % thành literal không?

**Đáp án:** không; pattern semantics vẫn áp dụng. Bind chống SQL injection, không tự escape LIKE wildcard.

### Bài 23. Ghép FTS và ILIKE bằng OR cần chú ý gì?

**Đáp án:** nhóm OR bằng ngoặc bên trong mandatory tenant/eligibility filters, và định nghĩa rank cho những hàng chỉ match một trong hai nhánh.

### Bài 24. Vì sao ranking không thể đưa BLOCKED product lên đầu?

**Đáp án:** blocked product phải bị loại trước khi xếp hạng, bất kể điểm text/business cao.

### Bài 25. Vì sao ORDER BY cần tie-breaker?

**Đáp án:** hai sản phẩm cùng relevance có thể đảo thứ tự; `product_id` tạo thứ tự ổn định trong cùng snapshot.

### Bài 26. OFFSET 100000 có vấn đề gì?

**Đáp án:** vẫn có thể cần đi qua rất nhiều rows trước khi lấy một trang nhỏ và dữ liệu thay đổi có thể làm phân trang không ổn định.

### Bài 27. Keyset cursor có cần gắn với keyword/filter không?

**Đáp án:** có; cursor của thứ tự relevance phụ thuộc keyword và filters, không nên dùng lại cho request khác.

### Bài 28. Vì sao COUNT phải tính trên tập eligible matches?

**Đáp án:** COUNT raw FTS có thể bao gồm dữ liệu tenant khác, draft, blocked hoặc hết hạn, làm UI báo sai và có thể rò thông tin.

### Bài 29. COUNT(*) OVER() luôn miễn phí không?

**Đáp án:** không; tính total có thể cần duyệt mọi matching rows và làm mất lợi ích dừng sớm của LIMIT.

### Bài 30. Facet theo category có tính sau LIMIT không?

**Đáp án:** không nếu muốn count toàn bộ tập search; chỉ tính sau LIMIT nếu UI cố ý hiển thị “facets của trang này”.

### Bài 31. Self-excluding facet là gì?

**Đáp án:** khi tính số đếm cho category facet, bỏ **riêng filter category đang chọn** nhưng giữ keyword, tenant, eligibility và mọi filters còn lại theo UX.

### Bài 32. Có thể xóa tenant filter khỏi facet để “đủ số liệu” không?

**Đáp án:** không. Có thể làm lộ lượng dữ liệu không thuộc phạm vi quyền truy cập.

### Bài 33. GIN trên search_vector hỗ trợ gì?

**Đáp án:** tìm ứng viên theo lexemes/`@@`; không tự xác minh seller/stock/region.

### Bài 34. Khi nào dùng B-tree kết hợp tenant/category/price?

**Đáp án:** khi các business predicates đủ chọn lọc; thứ tự keys cần phù hợp equality/range/query patterns thực tế.

### Bài 35. Khi nào dùng partial index public products?

**Đáp án:** khi nhiều queries luôn có hằng `status='PUBLISHED' AND deleted_at IS NULL` và index nhỏ hơn hữu ích; không phải cơ chế authorization.

### Bài 36. Generic plan với `status=$1` có mặc định dùng partial index published không?

**Đáp án:** không được giả định `$1` luôn PUBLISHED; với query variant hằng status thì planner dễ chứng minh index predicate hơn.

### Bài 37. Vì sao không dùng `now()` trong partial index predicate?

**Đáp án:** tập sản phẩm chưa hết hạn thay đổi theo thời gian dù không UPDATE, và index predicate cần immutable expressions phù hợp.

### Bài 38. Vì sao Seq Scan có thể vẫn tốt khi đã có GIN?

**Đáp án:** keyword match quá nhiều rows hoặc các điều kiện khác khiến quét tuần tự có cost thấp hơn index-driven access.

### Bài 39. RLS có thay business eligibility không?

**Đáp án:** không tự động. Tenant RLS có thể giới hạn scope nhưng vẫn cần trạng thái public, seller verified, stock/time/region theo chính sách.

### Bài 40. Có thể tin `SET app.tenant_id` do user gửi không?

**Đáp án:** không. Context tenant phải được xác thực và bảo vệ ở server/DB role; custom GUC do untrusted session tự chỉnh không phải security boundary.

### Bài 41. Vì sao search query cần xét nhiều locale/timezone?

**Đáp án:** ngày hiệu lực và vùng bán có semantics nghiệp vụ, nhất là cửa sổ theo ngày địa phương; không tự coi ngày local là UTC.

### Bài 42. Vì sao không nên ghép raw SORT từ request vào ORDER BY?

**Đáp án:** column identifiers/SQL expressions không được bind như values; dùng allowlist các lựa chọn sắp xếp.

### Bài 43. Query builder optional filters có được bỏ status vì “UI đã ẩn” không?

**Đáp án:** không. Mandatory filters phải có ở mọi query variant, bất kể UI.

### Bài 44. Vì sao EXPLAIN phải xem Rows Removed by Filter?

**Đáp án:** nó cho biết scan tạo bao nhiêu candidates bị loại do những điều kiện khác, gợi ý có cần access path/index phù hợp hơn.

### Bài 45. `cost=500` nghĩa 500 ms?

**Đáp án:** không; đây là đơn vị cost của planner. Dùng actual time trong `EXPLAIN ANALYZE` để quan sát runtime.

### Bài 46. Tại sao cần so p95/p99 và concurrency?

**Đáp án:** keyword hiếm có thể nhanh nhưng keyword rất phổ biến hoặc nhiều concurrent requests gây tail latency; một lượt chạy đơn không đại diện.

### Bài 47. Vì sao giá trong search cần kiểm tra lại khi checkout?

**Đáp án:** giá, khuyến mại hoặc quyền bán có thể đổi giữa hai thời điểm. Checkout cần invariant/transaction riêng.

### Bài 48. Viết checklist triển khai endpoint đúng

**Đáp án gợi ý:**

1. Định nghĩa authorization, eligibility, user filters, text matching và ranking.
2. Dùng tenant ID từ auth context; bảo vệ thêm bằng roles/RLS khi phù hợp.
3. Gom OR keyword trong ngoặc, giữ mandatory conditions cho mọi nhánh.
4. Lọc trước ORDER BY/LIMIT; không cắt raw top-K rồi lọc.
5. Dùng EXISTS cho quan hệ một-nhiều khi chỉ cần kiểm tra membership.
6. Đồng bộ semantics giữa danh sách, total count, facets và suggestions.
7. Xây index FTS/business/partial/trigram theo workload; không tạo trùng vô cớ.
8. Đo `EXPLAIN ANALYZE BUFFERS` với keywords và filters chọn lọc khác nhau.
9. Bind values, allowlist sort, escape LIKE literal.
10. Giới hạn keyword/page size, timeout, rate-limit và log an toàn.
11. Kiểm thử tenant isolation, blocked/draft/deleted/expired/stock0.
12. Kiểm tra lại giá và tồn kho tại checkout.

## 39. Quy trình benchmark từ đầu đến cuối

Sau khi đã tạo schema và indexes trong lab:

### Bước 1. Đếm raw text matches

```sql
SELECT COUNT(*)
FROM search_rules_lab.products
WHERE search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

Đây là số raw matches, **không phải kết quả được phép xem**.

### Bước 2. Đếm matches có tenant

```sql
SELECT COUNT(*)
FROM search_rules_lab.products
WHERE tenant_id = 2
  AND search_vector @@
      websearch_to_tsquery('simple', 'PostgreSQL');
```

So sánh số lượng để thấy business scope thu hẹp tập ứng viên.

### Bước 3. Đếm eligible matches đầy đủ

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'simple', 'PostgreSQL'
    ) AS tsq
)
SELECT COUNT(*)
FROM search_rules_lab.products AS p
JOIN search_rules_lab.sellers AS s
  ON s.tenant_id = p.tenant_id
 AND s.seller_id = p.seller_id
CROSS JOIN q
WHERE p.tenant_id = 2
  AND p.status = 'PUBLISHED'
  AND p.deleted_at IS NULL
  AND p.stock_qty > 0
  AND p.country_code = 'VN'
  AND p.published_at <=
      timestamptz '2026-11-14 00:00:00+00'
  AND (
      p.available_until IS NULL
      OR p.available_until >
         timestamptz '2026-11-14 00:00:00+00'
  )
  AND s.is_verified
  AND s.suspended_at IS NULL
  AND p.search_vector @@ q.tsq;
```

### Bước 4. Lấy plan thực tế cho list query

Dùng query ở phần 7, thêm `EXPLAIN (ANALYZE, BUFFERS)` và ghi scan/join/sort/rows/buffers/time.

### Bước 5. Thử nhiều filter chọn lọc

- Không lọc category, giá rộng.
- Category = 2 và giá hẹp.
- Tag = discount.
- Country = VN/US.
- Keyword rất phổ biến như database.
- Keyword ít gặp như postgresql.
- Keyword không có kết quả.

Quan sát cách planner thay đổi access paths.

### Bước 6. Thử phương án index có lý do

Ví dụ partial index cho published/not deleted hoặc trigram index nếu product muốn ILIKE contains. Không tạo nhiều index có nội dung tương đương chỉ để đổi tên.

### Bước 7. Đo lại và đánh giá hệ thống

Ghi cùng:

| Biến | Trước | Sau |
| --- | --- | --- |
| SQL/filters | Ghi nguyên dạng, bind values | Cùng workload |
| Actual rows | Tự đo | Tự đo |
| Plan nodes | Tự đo | Tự đo |
| Buffer hits/reads | Tự đo | Tự đo |
| Planning Time | Tự đo | Tự đo |
| Execution Time | Tự đo nhiều lần | Tự đo nhiều lần |
| Index size | Tự đo | Tự đo |
| Insert/update latency | Tự đo | Tự đo |
| Result correctness | Test ma trận | Phải giữ nguyên |
| Tenant isolation | Test quyền | Tuyệt đối không hồi quy |
| p95/p99 | Tự đo | Tự đo |

Nếu query nhanh hơn nhưng trả thiếu sản phẩm hợp lệ hoặc lọt sản phẩm tenant khác, thay đổi đó **không chấp nhận được**.

## 40. Checklist triển khai

| Câu hỏi | Hành động |
| --- | --- |
| Tenant hiện tại lấy từ đâu? | Chỉ từ auth context tin cậy |
| Có RLS/DB permissions phù hợp? | Kiểm thử role thực tế và pool |
| Có bảo vệ tất cả query variants? | Không bỏ mandatory predicates |
| Có nhóm các nhánh OR? | Dùng ngoặc chính xác |
| Có product ở DRAFT/HIDDEN/BLOCKED? | Bị loại khỏi public search |
| Có xóa mềm? | `deleted_at IS NULL` |
| Seller có verified? | JOIN/EXISTS theo khóa đúng tenant |
| Seller suspended? | Loại từ kết quả |
| Sản phẩm chưa phát hành? | So `published_at` với as_of |
| Đã hết hạn? | So end exclusive và NULL |
| Có stock threshold? | Giới hạn hiển thị; checkout kiểm tra lại |
| Country/region đúng? | Chỉ hiện nơi được bán |
| Tiền tệ và khoảng giá nhất quán? | Không so đơn vị khác nhau |
| Tag filter có nhân bản hàng? | Dùng EXISTS/aggregate theo semantics |
| FTS config có đúng ngôn ngữ? | Test tokenization/lexeme |
| LIKE input có wildcard? | Escape khi tìm literal |
| Có ILIKE contains/regex? | Đánh giá trigram và query cost |
| Có keyword rất ngắn/rỗng? | Áp policy kiểm soát |
| Có ranking boost? | Không cho vượt business eligibility |
| Có total order? | Tie-breaker unique |
| LIMIT có áp sau lọc? | Không lấy raw top-K trước |
| Count/list có cùng filters? | Đồng bộ semantics |
| Facets có tiết lộ dữ liệu khác tenant? | Cùng authorization scope |
| Self-excluding facets đã định nghĩa? | Chỉ loại filter facet được yêu cầu |
| Có pagination sâu? | Cân nhắc keyset |
| Có nhiều query async liên tục? | Debounce/rate limit |
| Có index search? | GIN tsvector hoặc trigram thích hợp |
| Có business index? | B-tree composite/partial có lý do |
| Có index trùng? | Xem write/storage cost |
| Có cập nhật statistics? | ANALYZE theo workload |
| Đã xem EXPLAIN thật? | Rows/buffers/join/Sort |
| Có prepared generic plan? | Test parameter skew |
| Có timeout/quotas? | Không cho regex/search quá rộng |
| Có log PII/keyword nhạy cảm? | Redact/aggregate |
| Có kiểm tra đồng thời? | Stock/price checkout transaction |
| Có test kết quả đúng? | Ma trận quyền và business cases |
| Có canary/rollback? | Giám sát trước và sau deploy |

## 41. Tổng kết

Kết hợp điều kiện nghiệp vụ với kết quả tìm kiếm trong PostgreSQL đòi hỏi **cả tính đúng đắn và hiệu năng**:

1. **Bắt đầu từ quyền truy cập.** Tenant/ACL/RLS là ràng buộc bắt buộc, không phải filter UI.
2. **Thể hiện eligibility rõ ràng.** Published, soft delete, seller verified, thời gian hiệu lực, stock và country cần được kiểm tra theo đúng chính sách.
3. **Chỉ sau đó mới chọn match.** FTS `@@`, `ILIKE` và trigram giải quyết những semantics tìm kiếm khác nhau.
4. **Nhóm OR chính xác.** Một `OR` thiếu ngoặc có thể vô hiệu hóa tenant/status constraints.
5. **Không LIMIT trước eligibility.** Top N phải là top N trong tập **eligible matches**.
6. **Tránh JOIN nhân bản hàng.** Dùng `EXISTS` nếu chỉ cần kiểm tra một product có tag/membership liên quan.
7. **Đồng bộ count/facets/list.** Không tính total hay facets trên raw data ngoài phạm vi; không đếm sau LIMIT nếu cần total hits.
8. **Ranking không được vượt qua business rules.** Điểm cao không thể giúp một product blocked trở thành công khai.
9. **Pagination phải ổn định.** Dùng total order và thiết kế cursor/snapshot phù hợp.
10. **Index chỉ là công cụ.** GIN cho text, B-tree cho business keys, trigram cho substring, partial index cho predicates ổn định; vẫn phải đo.
11. **Planner được tối ưu thứ tự thực thi.** Thứ tự WHERE không phải security boundary.
12. **Giữ SQL an toàn.** Bind parameters, escape LIKE literal khi cần, allowlist ORDER BY và giữ tenant từ auth context.
13. **Search chỉ là snapshot.** Giá/tồn kho/khả năng đặt mua phải kiểm tra lại ở transaction checkout.
14. **Đo toàn hệ thống.** EXPLAIN, buffers, latency, write cost và test tenant isolation đều quan trọng.

Mẫu tư duy cuối cùng:

```text
User query + authenticated context
                |
                v
   Mandatory authorization scope
                |
                v
  Business eligibility + user filters
                |
                v
      Full-text/substring matches
                |
                v
      Relevance + business ranking
                |
                v
        Stable ORDER BY + LIMIT
                |
                v
          Visible result page

Cùng phạm vi/filter đó
       |
       +--> total matches
       |
       +--> category/tag facets theo UX
```

**Quy tắc cốt lõi:** một truy vấn tìm kiếm được coi là tốt khi nó trả **đúng những hàng người dùng được phép xem, đúng điều kiện kinh doanh, đúng thứ tự và đúng số lượng**, đồng thời có độ trễ/chi phí phù hợp. Chỉ làm cho `@@` hoặc `ILIKE` chạy nhanh hơn chưa đủ để tạo ra một search endpoint đáng tin cậy.
