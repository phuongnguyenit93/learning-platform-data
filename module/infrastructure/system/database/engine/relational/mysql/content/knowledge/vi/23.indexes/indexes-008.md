# Prefix index cho chuỗi dài và giới hạn tính phân biệt

Prefix index là chỉ mục B-tree chỉ lưu một phần đầu của giá trị chuỗi thay vì toàn bộ chuỗi. Trong MySQL, cách này hữu ích khi một cột VARCHAR rất dài hoặc TEXT/BLOB chứa URL, đường dẫn, nội dung định danh hay chuỗi lớn mà truy vấn thường lọc theo phần đầu. Prefix index giúp giảm kích thước entry của index, nhưng đổi lại nhiều giá trị khác nhau có thể có cùng phần đầu được lập chỉ mục.

Vì vậy, câu hỏi quan trọng không chỉ là "nên lấy bao nhiêu ký tự?" mà còn là "bao nhiêu giá trị trong dữ liệu thực tế có phần đầu giống nhau?". Độ dài prefix cần được chọn dựa trên phân bố dữ liệu, collation, điều kiện truy vấn, giới hạn key length và chi phí ghi. Prefix quá ngắn làm index ít chọn lọc; prefix quá dài làm index lớn mà lợi ích bổ sung có thể rất nhỏ.

Trong module **DATABASE_MYSQL**, prefix index kết nối thiết kế kiểu dữ liệu, B-tree, composite index, selectivity và execution plan. Bài học này giải thích cách MySQL lưu và dùng prefix index, cách đo mức độ phân biệt của các độ dài khác nhau, giới hạn của UNIQUE prefix index, cùng quy trình chọn độ dài và xác minh bằng dữ liệu thực tế.

## 1. Prefix index là gì?

Với index thông thường trên cột chuỗi, B-tree lưu giá trị khóa của cột theo cấu trúc index. Với prefix index, chỉ N ký tự đầu của chuỗi (hoặc N byte với chuỗi nhị phân) được lưu làm key part.

Ví dụ:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(1000) NOT NULL,
    body LONGTEXT NOT NULL,
    PRIMARY KEY (article_id),
    KEY idx_tenant_title (tenant_id, title(80))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Index idx_tenant_title gồm:

- Toàn bộ giá trị tenant_id.
- 80 ký tự đầu của title.
- Khóa chính article_id được InnoDB lưu trong secondary index để định vị hàng.

Prefix title(80) không có nghĩa MySQL cắt title trong bảng. Giá trị title đầy đủ vẫn được lưu trong clustered record. Chỉ entry của secondary index giữ phần đầu được chỉ định.

Với các cột TEXT và BLOB, prefix length thường phải được chỉ định khi tạo index vì các kiểu này có thể chứa giá trị rất dài:

```sql
CREATE TABLE external_assets (
    asset_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    resource_url TEXT NOT NULL,
    PRIMARY KEY (asset_id),
    KEY idx_resource_url_prefix (resource_url(128))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Nếu chỉ mục đầy đủ trên chuỗi dài không phù hợp vì giới hạn key length hoặc chi phí lưu trữ, prefix index là một lựa chọn. Tuy nhiên, cần kiểm tra xem phần đầu của chuỗi có đủ khác nhau để thu hẹp tập ứng viên hay không.

## 2. Cú pháp tạo prefix index

Có thể tạo prefix index ngay khi khai báo bảng:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    path VARCHAR(2000) NOT NULL,
    PRIMARY KEY (document_id),
    KEY idx_path_prefix (path(120))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Hoặc thêm index sau khi bảng đã tồn tại:

```sql
CREATE INDEX idx_path_prefix
    ON documents (path(120));
```

Với composite index, prefix length được ghi ngay sau cột chuỗi tương ứng:

```sql
CREATE INDEX idx_tenant_path
    ON documents (tenant_id, path(120), created_at);
```

Trong ví dụ trên:

- tenant_id được index đầy đủ.
- path chỉ lấy 120 ký tự đầu.
- created_at được index đầy đủ.

Prefix length chỉ áp dụng cho key part kiểu chuỗi có thể dùng prefix. Không chỉ định prefix length cho cột số, ngày giờ hoặc các kiểu không hỗ trợ dạng prefix.

### 2.1. Độ dài prefix tính theo ký tự hay byte?

Cách tính phụ thuộc loại chuỗi:

| Kiểu dữ liệu | Đơn vị prefix length |
|---|---|
| CHAR, VARCHAR, TEXT và kiểu chuỗi không nhị phân | Ký tự |
| BINARY, VARBINARY, BLOB và kiểu chuỗi nhị phân | Byte |

Với charset đa byte như utf8mb4, một ký tự có thể chiếm tối đa 4 byte. Vì vậy, prefix 100 ký tự không đồng nghĩa index chỉ chiếm 100 byte. Dung lượng key thực tế phụ thuộc ký tự được lưu, charset, collation, kiểu cột, khóa chính đi kèm và cấu trúc index.

Ví dụ, path(120) trên VARCHAR dùng utf8mb4 có thể cần tối đa khoảng 480 byte cho phần ký tự, chưa tính các key part khác và overhead nội bộ.

### 2.2. Giới hạn key length

InnoDB giới hạn tổng độ dài key của một index. Mức tối đa phụ thuộc phiên bản MySQL, kích thước page, row format và cấu hình engine.

Với InnoDB page size 16 KB, giới hạn thường gặp ở cấu hình hiện đại là 3072 byte cho index key; page size 8 KB và 4 KB có giới hạn thấp hơn tương ứng. Một số cấu hình hoặc row format cũ có giới hạn 767 byte. Với composite index, cần tính tổng byte của tất cả key part, không chỉ prefix của một cột.

Không lấy 3072 byte làm giả định cho mọi server. Kiểm tra row format, page size, charset và phiên bản thực tế trước khi tạo index. Lỗi "Specified key was too long" thường cho thấy tổng key length vượt giới hạn đang áp dụng.

Con số 191 thường xuất hiện trong ví dụ utf8mb4 vì 191 × 4 = 764 byte, nằm dưới giới hạn lịch sử 767 byte. Đây là một giải pháp tương thích với một số cấu hình cũ, không phải độ dài tối ưu mặc định cho mọi prefix index hiện đại.

## 3. Prefix index hoạt động với truy vấn như thế nào?

Giả sử index chỉ lưu 12 ký tự đầu của resource_url. Khi truy vấn tìm một URL đầy đủ:

```sql
SELECT asset_id, resource_url
FROM external_assets
WHERE resource_url =
      'https://cdn.example.com/images/2026/product/large-photo.png';
```

MySQL có thể dùng phần prefix trong B-tree để tìm các entry có cùng phần đầu. Nếu nhiều hàng có cùng prefix, engine phải kiểm tra giá trị đầy đủ của hàng ứng viên để xác nhận điều kiện WHERE.

Điều đó có nghĩa prefix index là một bộ lọc giúp thu hẹp tập ứng viên. Nó không biến những chuỗi có cùng prefix thành cùng một giá trị trong bảng và không làm mất phần dữ liệu phía sau.

### 3.1. Equality lookup

Với điều kiện bằng:

```sql
SELECT asset_id
FROM external_assets
WHERE resource_url = 'https://cdn.example.com/a/very/long/resource-name.json';
```

Prefix index có thể hỗ trợ tìm ứng viên. Nếu nhiều URL cùng 128 ký tự đầu, server phải kiểm tra thêm phần còn lại để phân biệt chúng. Prefix càng ít phân biệt thì số ứng viên phải kiểm tra càng lớn.

### 3.2. LIKE với phần đầu cố định

B-tree có thể hỗ trợ điều kiện LIKE bắt đầu bằng một chuỗi cố định:

```sql
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE 'https://cdn.example.com/images/%';
```

Optimizer có thể chuyển phần đầu cố định thành một range trên index. Prefix index vẫn chỉ lưu phần đầu; nếu pattern dài hơn prefix, index có thể thu hẹp một phần rồi điều kiện còn lại được kiểm tra trên giá trị đầy đủ.

### 3.3. LIKE có wildcard ở đầu

Điều kiện sau thường không thể dùng B-tree prefix index để tạo range hiệu quả:

```sql
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE '%/product/%';
```

Vì ký tự đầu tiên không cố định, MySQL không biết bắt đầu tìm từ vùng nào trong thứ tự B-tree. Cần xem xét full-text search, cột dẫn xuất hoặc cấu trúc dữ liệu khác nếu tìm kiếm chuỗi con là yêu cầu thường xuyên.

Prefix index không phải FULLTEXT index. Nó không tách token, không tìm từ ở giữa chuỗi và không cung cấp tìm kiếm ngôn ngữ tự nhiên.

### 3.4. Điều kiện có hàm trên cột

Bọc cột trong hàm có thể làm index thông thường không được dùng làm range access trực tiếp:

```sql
-- Có thể không dùng được range access của prefix index
SELECT asset_id
FROM external_assets
WHERE LOWER(resource_url) = LOWER(?);

-- So sánh trực tiếp theo collation của cột nếu phù hợp
SELECT asset_id
FROM external_assets
WHERE resource_url = ?;
```

Nếu nghiệp vụ cần tìm trên giá trị đã chuẩn hóa, cân nhắc lưu cột chuẩn hóa riêng hoặc dùng generated column có index theo khả năng của phiên bản MySQL. Cần giữ nhất quán quy tắc chuẩn hóa giữa lúc ghi và lúc truy vấn.

## 4. Tính phân biệt và selectivity của prefix

Selectivity mô tả mức độ một điều kiện hoặc key part thu hẹp được tập dữ liệu. Với prefix index, cần xem có bao nhiêu prefix khác nhau trong tập giá trị.

Một cách ước lượng đơn giản:

\[
\text{Prefix selectivity}
=
\frac{\text{Số prefix khác nhau}}
{\text{Số giá trị không NULL}}
\]

Tỷ lệ càng gần 1 thì phần đầu càng phân biệt tốt trong dữ liệu đang đo. Tỷ lệ thấp cho thấy nhiều hàng dùng chung một prefix.

Ví dụ bảng có 1.000.000 URL không NULL:

| Prefix length | Prefix khác nhau (ước lượng ví dụ) | Selectivity |
|---:|---:|---:|
| 8 | 20.000 | 0,02 |
| 16 | 250.000 | 0,25 |
| 32 | 820.000 | 0,82 |
| 64 | 970.000 | 0,97 |

Với prefix 8, trung bình có nhiều URL chia sẻ phần đầu. Prefix 32 đã phân biệt phần lớn giá trị; tăng lên 64 chỉ cải thiện thêm một phần nhỏ nhưng index key dài hơn.

Đây chỉ là ví dụ minh họa. Dữ liệu thực tế có thể phân bố rất khác, đặc biệt với URL, email, đường dẫn hoặc mã định danh có phần đầu lặp lại.

### 4.1. Đo số prefix khác nhau

Có thể đo một số độ dài ứng viên trên dữ liệu thực tế:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(resource_url) AS non_null_values,
    COUNT(DISTINCT LEFT(resource_url, 8)) AS distinct_8,
    COUNT(DISTINCT LEFT(resource_url, 16)) AS distinct_16,
    COUNT(DISTINCT LEFT(resource_url, 32)) AS distinct_32,
    COUNT(DISTINCT LEFT(resource_url, 64)) AS distinct_64
FROM external_assets;
```

Tính tỷ lệ trên số giá trị không NULL:

```sql
SELECT
    COUNT(DISTINCT LEFT(resource_url, 16))
        / NULLIF(COUNT(resource_url), 0) AS selectivity_16,
    COUNT(DISTINCT LEFT(resource_url, 32))
        / NULLIF(COUNT(resource_url), 0) AS selectivity_32,
    COUNT(DISTINCT LEFT(resource_url, 64))
        / NULLIF(COUNT(resource_url), 0) AS selectivity_64
FROM external_assets;
```

COUNT(DISTINCT ...) bỏ qua NULL; dùng COUNT(resource_url) làm mẫu số để tỷ lệ không bị giảm giả tạo bởi các hàng NULL. Nếu cột NOT NULL, COUNT(*) và COUNT(column) cho cùng số hàng.

LEFT() ở đây được dùng để khảo sát dữ liệu, không phải để chứng minh optimizer sẽ dùng index theo cùng cách. Trên bảng lớn, các phép COUNT(DISTINCT) có thể đọc nhiều dữ liệu và cần bộ nhớ hoặc temporary structure. Hãy chạy trên bản sao/staging hoặc trong cửa sổ phù hợp với tải hệ thống.

### 4.2. Xem nhóm prefix có nhiều va chạm

Tỷ lệ distinct tổng thể có thể che khuất một số nhóm prefix rất phổ biến. Kiểm tra các nhóm có nhiều hàng cùng phần đầu:

```sql
SELECT
    LEFT(resource_url, 16) AS url_prefix,
    COUNT(*) AS rows_in_group
FROM external_assets
WHERE resource_url IS NOT NULL
GROUP BY LEFT(resource_url, 16)
ORDER BY rows_in_group DESC
LIMIT 20;
```

Nếu một số prefix chiếm tỷ trọng rất lớn, truy vấn thường xuyên nhắm vào các nhóm đó có thể vẫn phải kiểm tra nhiều ứng viên. Đánh giá cả phân bố truy vấn thực tế, không chỉ một tỷ lệ trung bình.

### 4.3. Chọn prefix theo điểm lợi ích giảm dần

Khi tăng prefix length:

- Số prefix khác nhau thường tăng hoặc giữ nguyên.
- Số hàng trung bình chia sẻ một prefix thường giảm.
- Key entry dài hơn và index lớn hơn.
- Cache chứa được ít entry hơn nếu index phình to.
- INSERT/UPDATE có thể tốn thêm công việc bảo trì index.

Hãy tìm điểm mà tăng thêm vài ký tự chỉ cải thiện rất ít selectivity. Không nhất thiết chọn prefix có selectivity gần 1 nếu lợi ích truy vấn không đáng với chi phí lưu trữ và ghi.

## 5. Collation và character set ảnh hưởng tính phân biệt

Prefix index tuân theo cách so sánh của collation trên cột. Với collation không phân biệt hoa/thường, các giá trị chỉ khác chữ hoa/chữ thường có thể được xem là bằng nhau trong so sánh. Với collation không phân biệt dấu, một số ký tự có dấu và không dấu có thể được xem là tương đương.

Ví dụ, nếu cột dùng collation case-insensitive, hai chuỗi có cùng chữ cái nhưng khác cách viết hoa có thể cùng nhóm theo quy tắc collation. Do đó, COUNT(DISTINCT LEFT(column, n)) phản ánh tính phân biệt theo collation hiện hành, không nhất thiết theo byte hoặc so sánh nhị phân.

Kiểm tra charset và collation:

```sql
SHOW FULL COLUMNS FROM external_assets;
```

Hoặc xem metadata của cột:

```sql
SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    CHARACTER_MAXIMUM_LENGTH,
    CHARACTER_OCTET_LENGTH
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_assets'
  AND COLUMN_NAME = 'resource_url';
```

Nếu ứng dụng truy vấn với collation khác hoặc chuyển đổi kiểu dữ liệu, optimizer có thể phải chuyển đổi giá trị và khả năng dùng index có thể thay đổi. Thiết kế prefix cần dựa trên semantics so sánh thật của ứng dụng.

Đừng chuyển sang collation binary chỉ để tăng số prefix khác nhau nếu nghiệp vụ cần so sánh không phân biệt hoa/thường hoặc dấu. Thay đổi collation có thể thay đổi kết quả so sánh, uniqueness và thứ tự sắp xếp của dữ liệu.

## 6. Prefix index và UNIQUE constraint

Có thể tạo UNIQUE prefix index:

```sql
CREATE UNIQUE INDEX uq_external_url_prefix
    ON external_assets (resource_url(64));
```

Nhưng constraint này bảo đảm phần 64 ký tự đầu không trùng giữa các hàng, không phải toàn bộ resource_url là duy nhất.

Ví dụ hai giá trị:

- https://cdn.example.com/files/customer/1001/report.pdf
- https://cdn.example.com/files/customer/1001/report-final.pdf

Nếu cả hai cùng có 64 ký tự đầu giống nhau, UNIQUE prefix index từ chối hàng thứ hai dù hai URL đầy đủ khác nhau.

Đây là điểm cần hiểu rõ:

- UNIQUE trên toàn bộ giá trị bảo đảm không có hai giá trị đầy đủ trùng theo semantics của collation.
- UNIQUE trên prefix bảo đảm không có hai giá trị cùng prefix được index.
- UNIQUE prefix có thể từ chối các giá trị khác nhau chỉ vì phần đầu giống nhau.

Vì vậy, không dùng UNIQUE prefix index để thay thế uniqueness của một chuỗi dài nếu nghiệp vụ cho phép các giá trị có chung phần đầu. Chỉ dùng khi quy tắc nghiệp vụ thực sự yêu cầu phần prefix đó phải duy nhất.

Nếu cần bảo đảm toàn bộ chuỗi dài duy nhất nhưng không thể tạo full unique index do giới hạn key length, hãy thiết kế một khóa định danh/chuẩn hóa phù hợp và có cơ chế xử lý va chạm được chứng minh đúng. Một digest hash đơn thuần có xác suất va chạm rất thấp nhưng không tạo ra bảo đảm toán học tuyệt đối; nếu dùng hash làm UNIQUE key, phải chấp nhận rủi ro hoặc có chiến lược collision handling phù hợp với yêu cầu dữ liệu.

## 7. Prefix index trong composite index

Prefix index có thể là một key part của composite index:

```sql
CREATE INDEX idx_tenant_path_time
    ON documents (
        tenant_id,
        path(120),
        created_at
    );
```

Index này phù hợp với truy vấn có tenant_id và điều kiện trên phần đầu của path, có thể kết hợp created_at tùy cấu trúc điều kiện:

```sql
SELECT document_id, created_at
FROM documents
WHERE tenant_id = 7
  AND path LIKE '/customers/active/%'
  AND created_at >= '2026-01-01';
```

Các nguyên tắc vẫn giống composite index thông thường:

1. Key part đầu tiên quyết định vùng tìm kiếm chính.
2. Equality prefix thường đứng trước range key part.
3. Prefix của chuỗi chỉ lưu phần đầu, nên các giá trị trùng prefix có thể tạo nhiều ứng viên.
4. Key part sau range thường không tiếp tục thu hẹp range theo cách đơn giản như equality prefix.
5. Cần kiểm tra key_len, rows, filtered và Extra bằng EXPLAIN.

Không thêm prefix length vào mọi cột chuỗi trong composite index một cách máy móc. Chỉ dùng prefix cho cột thực sự dài và khi mức độ phân biệt đủ tốt.

## 8. Giới hạn của prefix index với covering, ORDER BY và GROUP BY

### 8.1. Covering index

Vì prefix index không lưu toàn bộ giá trị chuỗi, truy vấn cần lấy toàn bộ cột đó thường phải đọc clustered record để lấy phần còn lại.

Ví dụ:

```sql
SELECT resource_url
FROM external_assets
WHERE resource_url = 'https://cdn.example.com/a/very/long/resource-name.json';
```

Index resource_url(128) có thể giúp tìm ứng viên, nhưng không chứa toàn bộ resource_url để trả kết quả đầy đủ. InnoDB cần truy cập hàng trong clustered index để lấy chuỗi đầy đủ.

Nếu truy vấn chỉ cần các cột có trong index, index vẫn có thể phục vụ như covering index cho truy vấn đó. Ví dụ chỉ lấy asset_id (primary key được lưu trong secondary index) có thể không cần đọc thêm clustered record, tùy access path và điều kiện.

### 8.2. ORDER BY

Index prefix chỉ sắp xếp theo phần đầu được lưu. Khi nhiều giá trị có cùng prefix, index không cung cấp đủ thông tin để xác định thứ tự đầy đủ của toàn bộ chuỗi trong nhóm đó. Truy vấn ORDER BY trên toàn bộ cột có thể cần bước sort bổ sung.

```sql
SELECT resource_url
FROM external_assets
ORDER BY resource_url;
```

Không giả định prefix index sẽ loại bỏ filesort cho thứ tự toàn bộ chuỗi. Hãy xem Extra trong EXPLAIN và kiểm tra kết quả trên dữ liệu thực tế.

### 8.3. GROUP BY và DISTINCT

Hai giá trị có cùng prefix không nhất thiết là cùng một chuỗi đầy đủ. Vì thế, prefix index không thể coi mọi giá trị cùng prefix là một nhóm duy nhất khi truy vấn cần semantics trên toàn bộ chuỗi.

```sql
SELECT resource_url, COUNT(*)
FROM external_assets
GROUP BY resource_url;
```

MySQL vẫn phải phân biệt các giá trị đầy đủ theo collation của cột. Prefix index có thể hỗ trợ một phần access path, nhưng không thay thế phép so sánh đầy đủ để xác định nhóm.

## 9. Chọn độ dài prefix theo workload

Không có một prefix length tối ưu cho mọi cột. Hãy chọn theo cách sau:

1. **Xác định truy vấn chính.** Là equality, LIKE prefix, range, ORDER BY hay GROUP BY?
2. **Khảo sát dữ liệu.** Đo distinct prefix ở nhiều độ dài ứng viên.
3. **Kiểm tra va chạm.** Tìm các prefix có nhiều hàng cùng nhóm và xem chúng có xuất hiện thường xuyên trong truy vấn không.
4. **Xem collation.** Tính phân biệt phải theo semantics so sánh thật.
5. **Tính key length theo byte.** Bao gồm mọi key part trong composite index và khóa chính được lưu ở secondary index.
6. **Tạo index trong staging.** Xác nhận DDL thành công và kiểm tra dung lượng.
7. **Đọc execution plan.** Kiểm tra index được chọn và ước lượng rows.
8. **Đo truy vấn thật.** Dùng EXPLAIN ANALYZE cho SELECT phù hợp và benchmark workload đại diện.
9. **Đo chi phí ghi.** Theo dõi INSERT/UPDATE, dung lượng index và buffer pool.
10. **Chọn điểm cân bằng.** Chọn prefix ngắn nhất vẫn đáp ứng yêu cầu hiệu năng và semantics.

### 9.1. Ví dụ so sánh prefix 16, 32 và 64

Giả sử bảng URL có 5 triệu hàng. Bạn đo được:

| Độ dài | Prefix khác nhau | Selectivity |
|---:|---:|---:|
| 16 | 1,2 triệu | 0,24 |
| 32 | 4,1 triệu | 0,82 |
| 64 | 4,8 triệu | 0,96 |

Nếu truy vấn equality thường tìm theo URL đầy đủ, prefix 32 có thể đã loại bỏ phần lớn ứng viên. Prefix 64 chỉ cải thiện selectivity từ 0,82 lên 0,96 nhưng làm index entry dài hơn gấp đôi so với 32. Cần benchmark để xác định lợi ích thực tế.

Nếu truy vấn chủ yếu nhắm vào URL bắt đầu bằng một domain phổ biến, selectivity tổng thể có thể không phản ánh tốt workload. Hãy kiểm tra các nhóm prefix phổ biến và tần suất truy vấn của chúng.

## 10. Kiểm tra index sau khi tạo

Dùng SHOW INDEX để xem index:

```sql
SHOW INDEX FROM external_assets;
```

Cột Sub_part cho biết độ dài prefix của key part; NULL thường biểu thị index toàn bộ cột. Cardinality là ước lượng số giá trị khác nhau trong index và có thể thay đổi theo thống kê.

Có thể truy vấn metadata:

```sql
SELECT
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX,
    SUB_PART,
    COLLATION,
    CARDINALITY
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_assets'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Sau khi tạo index hoặc khi dữ liệu thay đổi đáng kể, có thể cập nhật thống kê:

```sql
ANALYZE TABLE external_assets;
```

ANALYZE TABLE cập nhật thống kê optimizer; nó không tự chọn prefix length thay bạn. Sau khi cập nhật, đọc lại EXPLAIN vì plan có thể thay đổi.

### 10.1. Đọc EXPLAIN cho truy vấn equality

```sql
EXPLAIN
SELECT asset_id
FROM external_assets
WHERE resource_url =
      'https://cdn.example.com/a/very/long/resource-name.json';
```

Kiểm tra:

- key có phải idx_resource_url_prefix hay không.
- type có phải ref hoặc range phù hợp không.
- rows ước lượng có hợp lý không.
- Extra có cho biết điều kiện còn phải lọc hay không.
- Có full scan dù index tồn tại hay không.

Index tồn tại không đồng nghĩa optimizer luôn chọn nó. Nếu prefix ít chọn lọc hoặc bảng nhỏ, full scan có thể rẻ hơn theo ước lượng.

### 10.2. So sánh với truy vấn LIKE

```sql
EXPLAIN
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE 'https://cdn.example.com/images/%';
```

Kiểm tra xem prefix cố định có cho phép range access hay không. Thay đổi pattern thành '%images%' để thấy khác biệt:

```sql
EXPLAIN
SELECT asset_id
FROM external_assets
WHERE resource_url LIKE '%images%';
```

Kế hoạch cụ thể phụ thuộc phiên bản, collation, kiểu cột và dữ liệu. Không kết luận chỉ dựa trên cú pháp; hãy đọc key và rows.

## 11. Khi prefix index không phải lựa chọn tốt

### 11.1. Chuỗi có phần đầu giống nhau

URL thường bắt đầu bằng scheme và domain phổ biến; đường dẫn có thể bắt đầu bằng cùng thư mục gốc. Prefix ngắn khi đó có selectivity thấp.

Ví dụ các giá trị:

- https://cdn.example.com/images/users/...
- https://cdn.example.com/images/products/...
- https://cdn.example.com/images/archive/...

Prefix 16 có thể giống nhau gần như toàn bộ. Tăng độ dài đến phần phân nhánh có thể cải thiện selectivity, nhưng cần đo trên dữ liệu.

Nếu phần đầu cố định quá dài, hãy cân nhắc index một thuộc tính có ý nghĩa hơn như tenant_id, domain, resource_type hoặc một cột chuẩn hóa riêng.

### 11.2. Truy vấn tìm kiếm chuỗi con

Nếu workload chủ yếu dùng LIKE '%word%', B-tree prefix index không giải quyết được. Cân nhắc FULLTEXT, ngram parser phù hợp hoặc công cụ tìm kiếm chuyên dụng tùy ngôn ngữ và yêu cầu.

### 11.3. Cần uniqueness trên toàn bộ giá trị

UNIQUE prefix có semantics khác UNIQUE full value và có thể từ chối dữ liệu hợp lệ. Cần một thiết kế khóa duy nhất đúng nghiệp vụ, không chọn prefix chỉ vì DDL dễ tạo.

### 11.4. Cần sort hoặc group chính xác theo toàn bộ chuỗi

Prefix index có thể không cung cấp thứ tự đầy đủ khi nhiều giá trị trùng phần đầu. Nếu ORDER BY/GROUP BY toàn bộ chuỗi là workload quan trọng, benchmark với full index hoặc một thiết kế khác.

## 12. Các phương án thay thế

| Nhu cầu | Phương án có thể phù hợp |
|---|---|
| Chuỗi VARCHAR dài nhưng vẫn nằm trong giới hạn key | Full-column index |
| Tìm theo domain của email hoặc host của URL | Generated column/cột chuẩn hóa có index |
| Tìm token hoặc từ trong nội dung | FULLTEXT hoặc search engine |
| Equality lookup trên chuỗi rất dài | Digest/hash index không unique kết hợp so sánh giá trị gốc |
| Định danh tài nguyên ổn định | Surrogate key hoặc mã nghiệp vụ ngắn |
| Tìm suffix | Cột đảo chuỗi được chuẩn hóa hoặc giải pháp tìm kiếm phù hợp |

### 12.1. Generated column cho thuộc tính có ý nghĩa

Ví dụ truy vấn thường xuyên theo domain email:

```sql
CREATE TABLE contacts (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    email_domain VARCHAR(255)
        GENERATED ALWAYS AS (
            SUBSTRING_INDEX(email, '@', -1)
        ) STORED,
    PRIMARY KEY (contact_id),
    KEY idx_email_domain (email_domain)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
```

Truy vấn:

```sql
SELECT contact_id, email
FROM contacts
WHERE email_domain = 'example.com';
```

Cách này lập index trên thuộc tính nghiệp vụ cần tìm thay vì một prefix tùy ý của toàn bộ email. Cần xác thực email và chuẩn hóa domain theo đúng quy tắc ứng dụng; generated column ở ví dụ chỉ minh họa cách tách domain đơn giản.

### 12.2. Digest/hash để lọc ứng viên

Với chuỗi rất dài cần equality lookup, có thể lưu digest như SHA-256 trong cột BINARY(32) và tạo index trên digest. Truy vấn dùng digest để thu hẹp ứng viên, sau đó so sánh giá trị gốc:

Ví dụ bổ sung cột digest và index cho bảng external_assets đã tạo ở phần trước:

```sql
ALTER TABLE external_assets
    ADD COLUMN url_sha256 BINARY(32) NULL,
    ADD KEY idx_external_assets_url_sha256 (url_sha256);

UPDATE external_assets
SET url_sha256 = UNHEX(SHA2(resource_url, 256))
WHERE url_sha256 IS NULL;
```

Với bảng lớn, hãy backfill theo batch có kiểm soát. Sau đó, ứng dụng phải cập nhật url_sha256 đồng thời mỗi khi resource_url được insert hoặc update; có thể dùng logic ứng dụng hoặc cơ chế database đã được kiểm thử để duy trì hai giá trị nhất quán.

```sql
SELECT asset_id, resource_url
FROM external_assets
WHERE url_sha256 = UNHEX(SHA2(?, 256))
  AND resource_url = ?;
```

Digest cần được tính nhất quán khi ghi và có index phù hợp. Không dùng digest đơn thuần làm bằng chứng tuyệt đối rằng hai chuỗi giống nhau; nếu cần tính đúng tuyệt đối, luôn so sánh giá trị gốc sau bước lọc. Cũng không tạo UNIQUE trên digest nếu hệ thống không có chính sách xử lý va chạm phù hợp.

## 13. Tác động của prefix index đến ghi và lưu trữ

Prefix index nhỏ hơn full-column index khi chuỗi dài và prefix được chọn ngắn hơn đáng kể. Điều này có thể giúp:

- Giảm dung lượng B-tree.
- Tăng số entry có thể nằm trong một page.
- Giảm áp lực buffer pool.
- Giảm một phần chi phí ghi và bảo trì index.

Nhưng prefix index vẫn là một secondary index cần cập nhật khi giá trị prefix thay đổi. INSERT thêm entry; UPDATE phần đầu của chuỗi có thể phải thay entry; DELETE đánh dấu entry tương ứng để purge dọn sau.

Nếu UPDATE chỉ thay phần sau prefix và phần prefix không đổi, engine có thể không cần thay key part đó, nhưng vẫn phải cập nhật clustered record. Không nên suy luận rằng mọi thay đổi ở phần sau đều miễn phí; còn phụ thuộc cột khác trong index, clustered record, transaction và cấu trúc page.

Prefix ngắn hơn không phải lúc nào cũng làm truy vấn nhanh hơn. Nếu một prefix quá phổ biến, server phải kiểm tra nhiều clustered record và hiệu năng có thể kém hơn một index dài hơn.

## 14. Checklist chọn và vận hành prefix index

Trước khi tạo:

- Xác định truy vấn equality, LIKE prefix, range, ORDER BY hoặc GROUP BY nào cần hỗ trợ.
- Kiểm tra độ dài dữ liệu, charset và collation.
- Đo số prefix khác nhau ở nhiều độ dài.
- Kiểm tra nhóm prefix có số hàng trùng lớn.
- Xem xét semantics UNIQUE nếu định tạo unique prefix.
- Tính tổng key length theo byte cho toàn composite index.
- So sánh với full-column index, generated column hoặc FULLTEXT khi phù hợp.

Sau khi tạo:

- Kiểm tra Sub_part bằng SHOW INDEX hoặc information_schema.STATISTICS.
- Chạy ANALYZE TABLE khi cần cập nhật thống kê.
- Đọc EXPLAIN và xác nhận optimizer dùng index đúng mục đích.
- Benchmark truy vấn với tham số và dữ liệu đại diện.
- Theo dõi rows examined, latency, index size và chi phí DML.
- Đánh giá lại khi phân bố chuỗi thay đổi đáng kể.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chọn prefix 10 hoặc 20 ký tự theo cảm tính | Có thể trùng quá nhiều giá trị | Đo distinct prefix trên dữ liệu |
| Nghĩ prefix index lưu chuỗi đầy đủ | Bỏ sót việc phải đọc clustered record | Hiểu index chỉ lưu phần đầu |
| Dùng UNIQUE prefix để bảo đảm chuỗi đầy đủ duy nhất | Từ chối hai giá trị khác nhau có cùng prefix | Chọn khóa duy nhất theo semantics nghiệp vụ |
| Nghĩ prefix càng ngắn càng tốt | Selectivity thấp, nhiều ứng viên | Tìm điểm cân bằng kích thước và phân biệt |
| Nghĩ prefix càng dài luôn tốt hơn | Index phình to, lợi ích tăng thêm có thể nhỏ | Đo lợi ích biên của từng độ dài |
| Dùng prefix index cho LIKE '%abc%' | B-tree không tạo range từ wildcard đầu | Dùng FULLTEXT hoặc cấu trúc tìm kiếm khác |
| Bỏ qua collation | Ước lượng selectivity không đúng semantics so sánh | Đo theo collation của cột |
| Chỉ tính số ký tự, quên số byte | Vượt giới hạn index key length | Tính charset, page size, row format và composite key |
| Cho rằng prefix index luôn covering | Query cần chuỗi đầy đủ vẫn phải đọc hàng | Kiểm tra cột được lưu trong index |
| Dùng prefix index để thay full-text search | Không tìm token hoặc substring tùy ý | Chọn công cụ theo kiểu tìm kiếm |

## 16. Ghi nhớ

- Prefix index lưu một phần đầu của chuỗi trong B-tree; dữ liệu đầy đủ vẫn nằm trong hàng.
- Prefix length tính theo ký tự với CHAR/VARCHAR/TEXT và theo byte với BINARY/VARBINARY/BLOB.
- Với utf8mb4, một ký tự có thể cần tối đa 4 byte; phải tính tổng key length của composite index.
- Prefix index giúp giảm kích thước entry nhưng có thể tạo nhiều ứng viên cùng prefix.
- Selectivity của prefix có thể ước lượng bằng số prefix khác nhau chia cho số giá trị không NULL.
- Đo nhiều độ dài và kiểm tra các nhóm prefix phổ biến trước khi chọn.
- Collation ảnh hưởng cách so sánh và tính phân biệt; phải đo theo semantics thực tế.
- Equality lookup và LIKE với phần đầu cố định có thể dùng prefix index; wildcard đầu chuỗi thường không tạo được B-tree range.
- UNIQUE prefix chỉ bảo đảm prefix duy nhất, không phải semantics UNIQUE của toàn bộ chuỗi.
- Prefix index không tự bảo đảm covering hoặc sort/group đầy đủ trên giá trị chuỗi gốc.
- Dùng SHOW INDEX, information_schema.STATISTICS, EXPLAIN và benchmark để xác minh index.
- Cân nhắc full index, generated column, FULLTEXT hoặc digest/hash khi workload phù hợp hơn.

Prefix index hiệu quả khi phần đầu của chuỗi có đủ tính phân biệt đối với workload thực tế. Hãy đo dữ liệu, xét collation và tính key length trước khi chọn; sau đó xác minh bằng execution plan và benchmark để cân bằng tốc độ truy vấn, dung lượng index và chi phí ghi.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — Column Indexes: https://dev.mysql.com/doc/refman/8.0/en/column-indexes.html
- MySQL 8.0 Reference Manual — InnoDB Limits: https://dev.mysql.com/doc/refman/8.0/en/innodb-limits.html
- MySQL 8.0 Reference Manual — CREATE INDEX Statement: https://dev.mysql.com/doc/refman/8.0/en/create-index.html
- MySQL 8.0 Reference Manual — Character Sets and Collations: https://dev.mysql.com/doc/refman/8.0/en/charset.html

