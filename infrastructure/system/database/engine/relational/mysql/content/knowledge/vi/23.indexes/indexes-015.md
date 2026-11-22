# Phân biệt chỉ mục B-tree, FULLTEXT, SPATIAL và hash theo engine

MySQL có nhiều loại chỉ mục vì mỗi loại giải quyết một kiểu tìm kiếm khác nhau. B-tree phù hợp với tra cứu bằng, so sánh và quét theo khoảng; FULLTEXT phục vụ tìm kiếm từ và nội dung văn bản; SPATIAL hỗ trợ truy vấn dữ liệu hình học; hash phù hợp với phép so sánh bằng chính xác trên các engine có hỗ trợ.

Không phải engine nào cũng hỗ trợ mọi loại index. InnoDB, MyISAM, MEMORY và NDB Cluster có khả năng lưu trữ và cách triển khai chỉ mục khác nhau. Khi thiết kế bảng, cần chọn engine và loại index theo cả yêu cầu truy vấn, transaction, độ bền dữ liệu và giới hạn phiên bản MySQL.

## 1. Tổng quan các loại chỉ mục

| Loại chỉ mục | Cấu trúc/ý tưởng | Truy vấn phù hợp | Không phù hợp cho |
|---|---|---|---|
| B-tree | Cây cân bằng, trong InnoDB triển khai dạng B+Tree | `=`, `<`, `>`, `BETWEEN`, tiền tố `LIKE`, sắp xếp và quét theo khoảng | Tìm kiếm ngôn ngữ tự nhiên trong nội dung dài hoặc quan hệ không gian phức tạp |
| FULLTEXT | Chỉ mục đảo (inverted index) ánh xạ từ/token đến tài liệu hoặc hàng | Tìm từ, cụm từ và truy vấn văn bản theo chế độ FULLTEXT | So sánh số học, range scan hoặc sắp xếp tổng quát theo một cột |
| SPATIAL | Cấu trúc R-tree trên bounding rectangle của đối tượng không gian | Tìm đối tượng theo vùng, giao nhau hoặc quan hệ không gian | Tra cứu khóa chính thông thường hoặc tìm chuỗi văn bản |
| HASH | Hàm băm ánh xạ khóa sang bucket | So sánh bằng trên toàn bộ khóa | Range scan, thứ tự sắp xếp, tiền tố và so sánh lớn/nhỏ |

Các loại này không phải những lựa chọn thay thế trực tiếp cho nhau. Một bảng có thể có B-tree index trên khóa định danh, FULLTEXT index trên nội dung và SPATIAL index trên cột hình học nếu engine hỗ trợ và workload cần các kiểu tìm kiếm đó.

## 2. B-tree index: loại chỉ mục tổng quát

B-tree là loại index phổ biến nhất trong MySQL. InnoDB lưu dữ liệu của bảng trong clustered index và dùng B+Tree cho các chỉ mục của mình. Các trang trong cây giữ khóa theo thứ tự, giúp engine đi từ root đến leaf để tìm giá trị hoặc quét một phạm vi khóa.

Ví dụ:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status_created (status, created_at),
    KEY idx_orders_created (created_at)
) ENGINE = InnoDB;
```

B-tree có thể hỗ trợ các dạng truy vấn:

```sql
-- So sánh bằng
SELECT * FROM orders WHERE customer_id = 2001;

-- Quét theo khoảng
SELECT * FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';

-- So sánh lớn/nhỏ
SELECT * FROM orders WHERE order_id > 10000;

-- Tìm theo tiền tố chuỗi
SELECT * FROM orders WHERE status LIKE 'PAI%';

-- Sắp xếp theo cột index khi điều kiện và thứ tự phù hợp
SELECT order_id, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC;
```

Với index ghép, quy tắc leftmost prefix vẫn áp dụng. Chẳng hạn `(status, created_at)` có thể phục vụ điều kiện bắt đầu bằng `status`, rồi đến `created_at`. Index không tự nhiên phục vụ truy vấn chỉ lọc theo `created_at` với cùng hiệu quả.

### Ưu điểm và chi phí

- Hỗ trợ nhiều toán tử so sánh và truy vấn khoảng.
- Có thể hỗ trợ `ORDER BY`, `GROUP BY` và covering query khi thứ tự cột phù hợp.
- Có thể được dùng trong các phép join theo khóa.
- Cần dung lượng lưu trữ và được cập nhật mỗi khi giá trị khóa liên quan thay đổi.
- Quá nhiều index hoặc index quá rộng làm tăng chi phí `INSERT`, `UPDATE`, `DELETE`.

Trong InnoDB, clustered index là B+Tree chứa hàng dữ liệu ở leaf page; secondary index cũng là B+Tree và mang khóa chính để tìm hàng. Đây là đặc điểm lưu trữ của InnoDB, không phải cách mọi engine triển khai B-tree giống hệt nhau.

## 3. FULLTEXT index: tìm kiếm nội dung văn bản

FULLTEXT index được thiết kế để tìm từ và token trong nội dung văn bản. Thay vì sắp xếp toàn bộ giá trị cột như B-tree, FULLTEXT dùng cấu trúc chỉ mục đảo để liên kết từ xuất hiện với các hàng chứa từ đó.

MySQL hỗ trợ FULLTEXT trên các cột `CHAR`, `VARCHAR` và `TEXT`. InnoDB và MyISAM hỗ trợ FULLTEXT; các chi tiết tokenization, stopword và cấu hình có thể khác theo engine và phiên bản.

Ví dụ tạo bảng bài viết với FULLTEXT index:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    published_at DATETIME NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_articles_title_body (title, body)
) ENGINE = InnoDB;
```

Tìm kiếm theo natural language mode:

```sql
SELECT article_id, title,
       MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE) AS relevance
FROM articles
WHERE MATCH(title, body) AGAINST ('mysql index' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
```

`MATCH()` chỉ định các cột FULLTEXT cần tìm; danh sách cột phải tương ứng với một FULLTEXT index phù hợp. `AGAINST()` cung cấp chuỗi tìm kiếm và chế độ tìm kiếm.

### Các chế độ FULLTEXT thường dùng

**Natural language mode** là chế độ mặc định, xếp hạng kết quả dựa trên mức liên quan của từ trong tài liệu và tập dữ liệu:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('transaction isolation' IN NATURAL LANGUAGE MODE);
```

**Boolean mode** cho phép dùng toán tử để yêu cầu hoặc loại từ:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('+mysql +index -oracle' IN BOOLEAN MODE);
```

Trong ví dụ, `+mysql` và `+index` yêu cầu các từ đó xuất hiện, còn `-oracle` loại kết quả có từ `oracle`. Boolean mode có cú pháp riêng và không dùng cách xếp hạng giống natural language mode trong mọi trường hợp.

**Query expansion** mở rộng tìm kiếm dựa trên các tài liệu liên quan ở lượt tìm đầu, có thể giúp tìm thêm nội dung liên quan nhưng cũng có thể đưa vào kết quả ít sát ý định hơn:

```sql
SELECT article_id, title
FROM articles
WHERE MATCH(title, body)
      AGAINST ('deadlock' WITH QUERY EXPANSION);
```

### Token, stopword và ngôn ngữ

FULLTEXT không nhất thiết lập chỉ mục mọi chuỗi ký tự. Các từ quá ngắn hoặc nằm trong danh sách stopword có thể bị bỏ qua tùy engine, parser và cấu hình. InnoDB và MyISAM có thiết lập liên quan đến độ dài token và stopword riêng.

Với ngôn ngữ không phân tách từ bằng dấu cách, chẳng hạn tiếng Trung, Nhật hoặc một số nội dung đa ngôn ngữ, parser mặc định có thể không tạo token như mong đợi. MySQL cung cấp ngram full-text parser cho một số ngôn ngữ này. Hãy thử với dữ liệu thật và kiểm tra cấu hình parser, stopword, độ dài token trước khi kết luận một từ không được tìm thấy là do thiếu dữ liệu.

FULLTEXT phù hợp với tìm kiếm nội dung, nhưng không thay thế B-tree cho điều kiện như `created_at >= ...`, `price BETWEEN ...` hoặc join theo khóa ngoại.

## 4. SPATIAL index: tìm kiếm dữ liệu không gian

SPATIAL index hỗ trợ các kiểu dữ liệu hình học như `POINT`, `LINESTRING`, `POLYGON` và các geometry collection. Với InnoDB và MyISAM, spatial index sử dụng cấu trúc R-tree trên minimum bounding rectangle (MBR) của đối tượng.

MBR là hình chữ nhật nhỏ nhất bao quanh một đối tượng hình học. Tìm kiếm theo MBR giúp nhanh chóng loại bỏ phần lớn đối tượng không thể giao với vùng tìm kiếm. Sau bước lọc sơ bộ, có thể cần kiểm tra quan hệ hình học chính xác.

Ví dụ tạo bảng địa điểm dùng InnoDB và cột `POINT` giới hạn SRID:

```sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    place_name VARCHAR(150) NOT NULL,
    position POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id),
    SPATIAL INDEX sp_places_position (position)
) ENGINE = InnoDB;
```

Với InnoDB, spatial index yêu cầu cột geometry có SRID cố định (SRID-restricted). Khai báo SRID giúp engine biết hệ tọa độ và hỗ trợ tối ưu truy vấn không gian phù hợp. Cần thống nhất hệ tọa độ giữa dữ liệu lưu trữ và geometry truyền vào truy vấn.

Ví dụ tìm các điểm nằm trong vùng tìm kiếm:

```sql
SET @search_area = ST_GeomFromText(
    'POLYGON((106.60 10.70, 106.80 10.70, 106.80 10.90,
             106.60 10.90, 106.60 10.70))',
    4326
);

SELECT place_id, place_name
FROM places
WHERE MBRContains(@search_area, position)
  AND ST_Within(position, @search_area);
```

`MBRContains()` kiểm tra điểm có nằm trong bounding rectangle của vùng hay không; điều kiện `ST_Within()` kiểm tra quan hệ hình học chính xác với polygon. Khi dùng SRID địa lý, cần chú ý thứ tự trục theo định nghĩa SRS và cách truyền WKT; ví dụ trên minh họa thứ tự kinh độ/vĩ độ, nên cần xác nhận `axis-order` phù hợp với dữ liệu thực tế.

SPATIAL index không thay thế B-tree trên `place_id`, cũng không tự giải quyết mọi phép tính khoảng cách. Với truy vấn gần nhất theo khoảng cách, cần thiết kế bước lọc vùng ứng viên, sau đó tính khoảng cách chính xác và sắp xếp theo yêu cầu nghiệp vụ.

## 5. HASH index: tra cứu bằng chính xác

Hash index dùng hàm băm để ánh xạ khóa sang bucket. Nó được tối ưu cho phép so sánh bằng trên toàn bộ khóa, ví dụ `WHERE token = ...`. Khi có va chạm hash, engine vẫn phải kiểm tra giá trị khóa thực tế để xác nhận hàng phù hợp.

Hash index không giữ thứ tự khóa, vì vậy không phù hợp cho:

- `BETWEEN`, `<`, `>`, `<=`, `>=`.
- `ORDER BY` theo khóa.
- Tìm kiếm tiền tố như `LIKE 'abc%'`.
- Dò một phần của khóa ghép khi không cung cấp toàn bộ khóa.

Engine MEMORY hỗ trợ cả HASH và BTREE; HASH là loại mặc định của index trong MEMORY nếu không chỉ định khác. Có thể khai báo tường minh:

```sql
CREATE TABLE session_lookup (
    token VARBINARY(32) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    PRIMARY KEY (token) USING HASH,
    KEY idx_session_expiry (expires_at) USING BTREE
) ENGINE = MEMORY;
```

Hoặc dùng index phụ HASH:

```sql
CREATE TABLE feature_flags_cache (
    flag_key VARCHAR(100) NOT NULL,
    flag_value VARCHAR(255) NOT NULL,
    KEY idx_flag_key (flag_key) USING HASH
) ENGINE = MEMORY;
```

Trong ví dụ, HASH phù hợp với việc tìm một `flag_key` bằng chính xác. Nếu cần quét theo `expires_at` hoặc sắp xếp theo thời gian, B-tree phù hợp hơn.

### HASH trong MEMORY không giống adaptive hash của InnoDB

InnoDB có cơ chế Adaptive Hash Index (AHI) nội bộ. InnoDB có thể tự tạo cấu trúc hash trong bộ nhớ dựa trên những trang B-tree được truy cập thường xuyên để tăng tốc một số phép tra cứu. AHI do engine quản lý; đây không phải index mà ứng dụng khai báo bằng `CREATE INDEX ... USING HASH` trên bảng InnoDB.

Vì vậy, không thể đổi một secondary B-tree của InnoDB thành HASH chỉ bằng cách thêm `USING HASH`. Nếu workload InnoDB chủ yếu là equality lookup, B-tree vẫn là lựa chọn index thông thường; engine có thể áp dụng AHI nội bộ khi phù hợp.

## 6. Khả năng hỗ trợ theo storage engine

Bảng sau tóm tắt các khả năng thường gặp trong MySQL 8.x. Khả năng cụ thể cần được xác nhận theo phiên bản và biến thể engine đang triển khai.

| Storage engine | B-tree / ordered index | HASH | FULLTEXT | SPATIAL | Ghi chú |
|---|---|---|---|---|---|
| InnoDB | Có; clustered và secondary B+Tree | Không khai báo HASH index trực tiếp; có Adaptive Hash Index nội bộ | Có | Có; cột geometry cần SRID cố định để dùng spatial index | Engine giao dịch phổ biến, hỗ trợ ACID và khóa hàng |
| MyISAM | Có | Không hỗ trợ HASH index thông thường | Có | Có | Không cung cấp transaction và foreign key như InnoDB |
| MEMORY | Có, dùng `USING BTREE` | Có; mặc định cho index nếu không chỉ định | Không | Không | Dữ liệu bảng lưu trong bộ nhớ và mất khi server khởi động lại |
| NDB Cluster | Có ordered index | Có hash index theo đặc tính NDB | Không hỗ trợ FULLTEXT như InnoDB/MyISAM | Không phải lựa chọn SPATIAL index thông thường | Cơ chế index và cú pháp có khác biệt theo NDB; kiểm tra tài liệu đúng phiên bản |

Không chọn engine chỉ vì một loại index. Ví dụ, MEMORY có HASH index nhưng dữ liệu trong bảng MEMORY không bền qua lần khởi động lại server và engine có giới hạn kiểu dữ liệu, kích thước và tính năng. Nếu dữ liệu nghiệp vụ cần transaction, khóa ngoại và độ bền, InnoDB thường phù hợp hơn.

## 7. Chọn loại index theo bài toán

| Nhu cầu | Loại index nên xem xét | Ví dụ |
|---|---|---|
| Tìm theo khóa, so sánh khoảng, sắp xếp | B-tree | Tìm đơn hàng theo `customer_id` hoặc `created_at` |
| Tìm từ trong tiêu đề và nội dung | FULLTEXT | Tìm bài viết chứa `transaction isolation` |
| Tìm điểm trong vùng hoặc đối tượng giao nhau | SPATIAL | Tìm địa điểm nằm trong một polygon |
| Tra cứu khóa đầy đủ bằng chính xác trong bảng MEMORY | HASH | Tra cứu token hoặc cache key |

Trước khi tạo index, hãy trả lời các câu hỏi:

1. Truy vấn cần so sánh chính xác, range, tìm từ hay quan hệ hình học?
2. Storage engine của bảng có hỗ trợ loại index đó không?
3. Truy vấn có cần sắp xếp, lọc thêm hoặc trả về nhiều cột ngoài index không?
4. Index có làm tăng đáng kể chi phí ghi và dung lượng không?
5. Phiên bản MySQL và cấu hình parser/SRID có đáp ứng yêu cầu không?

## 8. Kiểm tra index và kế hoạch thực thi

`SHOW INDEX` cho biết các index đang có trên bảng, bao gồm tên, loại và thứ tự cột:

```sql
SHOW INDEX FROM orders;
SHOW INDEX FROM articles;
SHOW INDEX FROM places;
```

Trường `Index_type` giúp nhận biết loại index như `BTREE`, `HASH` hoặc `RTREE` tùy engine và index. `Seq_in_index` thể hiện vị trí của cột trong index ghép.

Sử dụng `EXPLAIN` để xem optimizer có chọn index phù hợp hay không:

```sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE customer_id = 2001;
```

Với FULLTEXT, kiểm tra câu `MATCH ... AGAINST` và xác nhận truy vấn sử dụng FULLTEXT index theo kế hoạch phù hợp. Với SPATIAL, kiểm tra điều kiện MBR và SRID để bảo đảm optimizer có thể khai thác spatial index. Với HASH trên MEMORY, kiểm tra truy vấn equality trên toàn bộ khóa; không mong đợi range scan hoặc thứ tự kết quả từ HASH.

## 9. Những nhầm lẫn thường gặp

**Cho rằng mọi engine hỗ trợ cùng loại index.** MEMORY có HASH và BTREE; InnoDB có B-tree, FULLTEXT và SPATIAL nhưng không cho khai báo HASH index thông thường. Hãy kiểm tra engine cụ thể.

**Dùng FULLTEXT cho điều kiện số hoặc ngày tháng.** FULLTEXT tìm token trong văn bản; B-tree phù hợp hơn cho khoảng ngày, số tiền và so sánh thông thường.

**Dùng HASH cho range query.** Hash không lưu thứ tự khóa nên không hỗ trợ quét khoảng hay `ORDER BY` theo khóa.

**Cho rằng SPATIAL trả kết quả hình học chính xác chỉ từ MBR.** MBR là vùng chữ nhật bao quanh; có thể cần thêm hàm hình học chính xác để loại các trường hợp chỉ giao bounding rectangle.

**Nhầm Adaptive Hash Index với HASH index do người dùng tạo.** AHI là cơ chế nội bộ của InnoDB; không thể tạo nó bằng `CREATE INDEX ... USING HASH` trên InnoDB.

**Chọn MEMORY chỉ vì HASH lookup nhanh.** Cần cân nhắc dữ liệu mất khi restart, giới hạn engine và việc bảng MEMORY không thay thế bảng giao dịch InnoDB.

## 10. Tự kiểm tra

1. B-tree hỗ trợ những kiểu điều kiện truy vấn nào mà HASH không hỗ trợ?
2. Vì sao FULLTEXT phù hợp với tìm kiếm nội dung văn bản hơn B-tree thông thường?
3. SPATIAL index dựa trên cấu trúc nào và MBR có ý nghĩa gì?
4. Engine MEMORY hỗ trợ những loại index nào và loại nào là mặc định?
5. Vì sao không thể khai báo HASH index thông thường cho bảng InnoDB?
6. Adaptive Hash Index của InnoDB khác HASH index của MEMORY như thế nào?
7. Vì sao invisible hoặc tồn tại một index không đồng nghĩa optimizer chắc chắn dùng nó?

