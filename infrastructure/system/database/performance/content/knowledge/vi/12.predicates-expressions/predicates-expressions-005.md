# LIKE, ký tự đại diện đầu chuỗi và giới hạn của chỉ mục thông thường

Tìm kiếm văn bản là thao tác phổ biến trong ứng dụng: tìm khách hàng theo tên, tìm mã đơn hàng theo tiền tố, tra cứu email, hoặc tìm một từ nằm ở bất kỳ vị trí nào trong mô tả. SQL cung cấp toán tử `LIKE` để so khớp chuỗi theo mẫu. Tuy nhiên, cách viết mẫu có ảnh hưởng lớn đến khả năng sử dụng chỉ mục B-tree thông thường.

Điều kiện `LIKE 'abc%'` bắt đầu bằng một chuỗi cố định nên bộ tối ưu thường có thể chuyển nó thành một khoảng khóa và thực hiện index range scan/seek. Ngược lại, `LIKE '%abc'` hoặc `LIKE '%abc%'` không xác định được điểm bắt đầu trong thứ tự từ điển của B-tree; hệ quản trị thường phải kiểm tra nhiều hoặc toàn bộ giá trị. Đây là giới hạn quan trọng khi tối ưu truy vấn văn bản.

Trong module **DATABASE_PERFORMANCE**, cần phân biệt tìm theo tiền tố, hậu tố và nội dung; hiểu tác động của wildcard, collation, kiểu dữ liệu và tham số; rồi chọn giữa B-tree, full-text index, trigram/ngram hoặc cách thiết kế dữ liệu khác. Không có một loại chỉ mục phù hợp cho mọi dạng tìm kiếm.

## 1. Cú pháp LIKE và ký tự đại diện

`LIKE` so sánh một giá trị chuỗi với mẫu. Hai ký tự đại diện phổ biến trong SQL là:

- `%`: khớp với không hoặc nhiều ký tự.
- `_`: khớp với đúng một ký tự theo quy tắc so khớp của hệ quản trị.

Ví dụ:

```sql
-- Tên bắt đầu bằng "An"
SELECT customer_id, full_name
FROM customer
WHERE full_name LIKE 'An%';

-- Tên kết thúc bằng "son"
SELECT customer_id, full_name
FROM customer
WHERE full_name LIKE '%son';

-- Chuỗi có "minh" ở bất kỳ vị trí nào
SELECT customer_id, full_name
FROM customer
WHERE full_name LIKE '%minh%';

-- Mã có đúng một ký tự bất kỳ ở vị trí thứ ba
SELECT product_id, product_code
FROM product
WHERE product_code LIKE 'AB_9%';
```

`LIKE` thường không phân biệt hoa thường hay có phân biệt hoa thường tùy collation và hệ quản trị. Một số hệ quản trị có toán tử hoặc kiểu so khớp riêng như `ILIKE` của PostgreSQL. Không nên suy luận rằng `LIKE` luôn có cùng ngữ nghĩa khi chuyển truy vấn giữa các môi trường.

### So sánh ba dạng mẫu thường gặp

| Dạng mẫu | Ví dụ | Ý nghĩa | Khả năng dùng B-tree thông thường |
|---|---|---|---|
| Tiền tố cố định | `'An%'` | Bắt đầu bằng `An` | Thường có thể dùng range scan/seek |
| Hậu tố cố định | `'%son'` | Kết thúc bằng `son` | Thường không thể seek từ đầu B-tree |
| Nội dung ở bất kỳ vị trí | `'%minh%'` | Có chứa `minh` | Thường phải quét hoặc dùng chỉ mục chuyên biệt |
| Không có wildcard đầu nhưng có `_` | `'A_n%'` | Ký tự thứ hai bất kỳ | Có thể dùng phần tiền tố cố định `A`, nhưng điều kiện còn lại phải lọc |
| Wildcard ngay đầu | `'_n%'` | Ký tự đầu bất kỳ | Không có tiền tố cố định đủ để seek hiệu quả |

## 2. Vì sao B-tree hỗ trợ tiền tố nhưng khó hỗ trợ wildcard đầu?

B-tree sắp xếp khóa theo thứ tự. Khi truy vấn tìm `LIKE 'An%'`, mọi chuỗi phù hợp thường nằm trong một vùng liên tiếp của thứ tự khóa: bắt đầu từ vị trí của `An` và kết thúc trước tiền tố kế tiếp theo quy tắc so sánh. Bộ tối ưu có thể tìm điểm đầu rồi đọc lần lượt các khóa trong vùng đó.

Với `LIKE '%son'`, ký tự đầu tiên có thể là bất kỳ ký tự nào. Các giá trị kết thúc bằng `son` có thể nằm rải rác ở nhiều vị trí trong B-tree. Không có một khoảng liên tiếp đơn giản bắt đầu bằng `son` để đọc. Tương tự, `LIKE '%minh%'` có thể khớp chuỗi nằm ở bất kỳ vị trí nào nên B-tree trên chuỗi gốc không cung cấp một điểm bắt đầu hữu ích.

Ví dụ với B-tree sắp xếp theo chuỗi gốc:

```text
An, Anh, Annam, Bao, Binh, Minh, Nam, Thanh, Xuan
|---- các khóa có tiền tố "An" ----|

LIKE 'An%'    -> có thể đọc một khoảng liên tiếp
LIKE '%inh'   -> các khóa phù hợp có thể nằm ở nhiều vùng
LIKE '%inh%'  -> các khóa phù hợp có thể nằm ở nhiều vùng
```

Đây là cách giải thích trực giác; thứ tự thực tế còn phụ thuộc collation, mã hóa, kiểu dữ liệu và cách hệ quản trị xác định khoảng khóa. Một kế hoạch có thể dùng index scan toàn bộ chỉ mục rồi lọc, nhưng điều đó khác với index seek/range scan chỉ đọc một phần nhỏ của chỉ mục.

### Tiền tố cố định và điều kiện bổ sung

Với mẫu `LIKE 'AB_9%'`, B-tree có thể tận dụng tiền tố `AB` để thu hẹp vùng đọc, sau đó kiểm tra `_9%` trên các ứng viên. Hiệu quả phụ thuộc độ chọn lọc của tiền tố. Nếu hầu hết bản ghi đều bắt đầu bằng `A`, lợi ích có thể nhỏ.

Một điều kiện `LIKE 'A%'` có thể dùng chỉ mục nhưng vẫn đọc rất nhiều hàng nếu phần lớn dữ liệu bắt đầu bằng `A`. Khả năng dùng chỉ mục và hiệu quả thực tế là hai câu hỏi khác nhau. Hãy xem actual rows, logical reads và thời gian thực thi.

## 3. Thiết kế B-tree cho tìm kiếm tiền tố

Nếu nghiệp vụ chủ yếu tìm theo phần đầu của chuỗi, B-tree trên cột tìm kiếm thường là lựa chọn đơn giản và hiệu quả.

```sql
CREATE INDEX ix_customer_full_name
ON customer (full_name);

SELECT customer_id, full_name
FROM customer
WHERE full_name LIKE 'Nguyen%';
```

Truy vấn có thể thực hiện index range scan/seek nếu kiểu dữ liệu, collation, toán tử và cấu hình hệ quản trị cho phép. Nếu cần lấy thêm cột không có trong chỉ mục, hệ quản trị có thể truy cập bảng để lấy dữ liệu còn thiếu.

### Chỉ mục ghép

Nếu truy vấn luôn giới hạn theo tenant hoặc trạng thái trước khi tìm tiền tố, có thể cân nhắc chỉ mục ghép:

```sql
CREATE INDEX ix_customer_tenant_name
ON customer (tenant_id, full_name);

SELECT customer_id, full_name
FROM customer
WHERE tenant_id = ?
  AND full_name LIKE 'Nguyen%';
```

Với điều kiện bằng trên cột dẫn đầu và điều kiện tiền tố trên cột kế tiếp, nhiều hệ quản trị có thể dùng một vùng khóa hẹp hơn. Thứ tự cột cần dựa trên mẫu truy vấn thực tế. Chỉ mục `(tenant_id, full_name)` không nhất thiết hỗ trợ tốt truy vấn chỉ tìm `full_name` mà không có `tenant_id`.

Nếu truy vấn cần trả về nhiều cột, một số hệ quản trị hỗ trợ cột INCLUDE hoặc cơ chế chỉ mục phủ để giảm lookup. Cân nhắc kích thước chỉ mục và chi phí ghi trước khi thêm nhiều cột vào khóa.

### Kiểu dữ liệu và collation

Khả năng range scan của `LIKE 'prefix%'` phụ thuộc cách hệ quản trị sắp xếp và so sánh chuỗi. Với một số collation ngôn ngữ, thứ tự ký tự không tương đương thứ tự byte đơn giản. Một số hệ quản trị cần operator class hoặc collation cụ thể để dùng B-tree cho pattern matching.

Đừng đổi collation chỉ để ép truy vấn dùng index mà chưa đánh giá ngữ nghĩa so sánh, Unicode và tính duy nhất. Hãy xác minh bằng kế hoạch thực thi trên đúng phiên bản và collation production.

## 4. Wildcard đầu chuỗi và tìm kiếm chứa chuỗi

Truy vấn tìm chuỗi ở bất kỳ vị trí nào thường có dạng:

```sql
SELECT document_id, title
FROM document
WHERE title LIKE '%database%';
```

Một B-tree thông thường trên `title` không có tiền tố cố định để xác định khoảng khóa. Với bảng lớn, truy vấn có thể đọc nhiều trang, CPU phải kiểm tra mẫu trên từng giá trị và độ trễ tăng theo quy mô dữ liệu.

Trước khi thay đổi cấu trúc, cần xác định yêu cầu tìm kiếm:

- Người dùng cần tìm từ ở đầu chuỗi hay bất kỳ vị trí nào?
- Có cần tìm nguyên từ, tiền tố của từ, cụm từ hay chuỗi ký tự con bất kỳ?
- Có cần không phân biệt hoa thường, dấu, dấu câu hoặc khoảng trắng không?
- Ngôn ngữ có cần tách từ, stemming, stop words hoặc xử lý dấu tiếng Việt không?
- Kết quả cần sắp xếp theo mức liên quan hay chỉ cần kiểm tra có chứa chuỗi?

Những yêu cầu này quyết định nên dùng B-tree, full-text search, trigram/ngram hay giải pháp khác.

### Khi nào vẫn có thể chấp nhận scan?

Quét bảng có thể hợp lý nếu bảng nhỏ, truy vấn ít chạy, tỷ lệ dữ liệu khớp cao hoặc dữ liệu đã nằm trong cache. Một index chuyên biệt cũng có chi phí xây dựng, lưu trữ và cập nhật. Đừng tạo chỉ mục phức tạp cho một truy vấn hiếm nếu scan hiện tại đáp ứng mục tiêu.

Với workload lớn, hãy đo số lần truy vấn, tổng thời gian CPU, logical reads, p95/p99 và ảnh hưởng đến truy vấn khác. Một truy vấn scan mất 50 ms nhưng chạy hàng chục nghìn lần mỗi phút có thể quan trọng hơn một truy vấn 2 giây chỉ chạy một lần mỗi ngày.

## 5. Các lựa chọn cho tìm kiếm chứa chuỗi

### Full-text index

Full-text search xây dựng cấu trúc phục vụ tìm kiếm theo từ hoặc token, thường có phân tích ngôn ngữ, tách từ, stop words và xếp hạng liên quan. Nó phù hợp khi yêu cầu là tìm từ, cụm từ hoặc nội dung văn bản theo ngữ nghĩa của bộ phân tích.

Full-text search không tương đương hoàn toàn với `LIKE '%abc%'`. Ví dụ, tìm từ `data` trong full-text index có thể không tìm thấy chuỗi con nằm bên trong `metadata`; ngược lại, `LIKE '%data%'` có thể khớp chuỗi con ở mọi vị trí. Hãy xác định đúng semantics trước khi thay thế.

Full-text index thường phù hợp cho mô tả sản phẩm, bài viết, tài liệu, nội dung hỗ trợ và trường văn bản dài. Nó có thể cung cấp xếp hạng kết quả, nhưng việc cập nhật chỉ mục, đồng bộ dữ liệu và cấu hình ngôn ngữ cần được quản lý.

### Trigram hoặc n-gram index

Trigram chia chuỗi thành các nhóm ba ký tự liên tiếp. Ví dụ chuỗi `database` có các trigram `dat`, `ata`, `tab`, `aba`, `bas`, `ase`. Chỉ mục lưu thông tin về các nhóm này để nhanh chóng tìm các hàng có khả năng chứa mẫu cần tìm. Sau bước lọc ứng viên, hệ quản trị vẫn kiểm tra điều kiện thực tế để loại kết quả không khớp.

Trigram hữu ích cho tìm chuỗi con, tìm gần đúng hoặc so khớp văn bản ngắn. N-gram tổng quát dùng nhóm N ký tự và có thể được cấu hình theo ngôn ngữ hoặc nhu cầu. Đổi lại, chỉ mục có thể lớn, cập nhật tốn kém và mẫu quá ngắn có ít thông tin để thu hẹp ứng viên.

### Chỉ mục đảo hoặc cấu trúc chuyên dụng

Một số hệ quản trị và hệ tìm kiếm cung cấp inverted index, token index hoặc cấu trúc chuyên biệt cho dữ liệu văn bản, JSON hay mảng. Chúng phù hợp với kiểu truy vấn cụ thể và không nhất thiết thay thế B-tree cho so sánh bằng hoặc range.

Chọn cấu trúc theo ngữ nghĩa truy vấn và khả năng vận hành của nền tảng. Nếu cần tìm chính xác một chuỗi con tùy ý, trigram/ngram thường phù hợp hơn full-text tokenization. Nếu cần tìm từ theo ngôn ngữ và xếp hạng, full-text thường phù hợp hơn.

## 6. PostgreSQL: B-tree, pattern operator class và pg_trgm

PostgreSQL có thể dùng B-tree cho một số mẫu `LIKE` có tiền tố cố định. Trong một số locale/collation, cần operator class như `text_pattern_ops` hoặc `varchar_pattern_ops` để hỗ trợ pattern matching theo cách phù hợp.

```sql
CREATE INDEX ix_customer_name_pattern
ON customer (name text_pattern_ops);

SELECT customer_id, name
FROM customer
WHERE name LIKE 'Nguyen%';
```

Hãy xác minh kế hoạch bằng `EXPLAIN (ANALYZE, BUFFERS)`; operator class này có thể ảnh hưởng khả năng sử dụng chỉ mục cho các phép so sánh theo collation thông thường.

Với tìm kiếm chứa chuỗi hoặc mẫu có wildcard đầu, extension `pg_trgm` cung cấp trigram index. Ví dụ dùng GIN:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX ix_document_title_trgm
ON document USING GIN (title gin_trgm_ops);

SELECT document_id, title
FROM document
WHERE title ILIKE '%database%';
```

GIN phù hợp cho nhiều phép tìm kiếm thành viên trigram; GiST cũng có thể dùng với `pg_trgm` và có các đặc tính khác, đặc biệt trong một số truy vấn khoảng cách/tương đồng. Mẫu quá ngắn hoặc không chứa đủ trigram có thể không giúp thu hẹp nhiều. Hệ thống vẫn cần kiểm tra lại điều kiện `LIKE`/`ILIKE` để bảo đảm kết quả chính xác.

Nếu cần tìm theo từ và xếp hạng, PostgreSQL có full-text search với `tsvector`, `tsquery` và GIN index. Đây là mô hình token-based; hãy chọn theo yêu cầu tìm từ thay vì chuỗi con tùy ý.

## 7. SQL Server: prefix seek và Full-Text Search

SQL Server thường có thể dùng index seek cho `LIKE 'prefix%'` trên cột có chỉ mục phù hợp. Với wildcard đầu như `LIKE '%text%'`, index seek thông thường không thể xác định điểm bắt đầu; kế hoạch có thể là scan và filter.

```sql
CREATE INDEX IX_Product_Name
ON dbo.Product (ProductName);

SELECT ProductId, ProductName
FROM dbo.Product
WHERE ProductName LIKE N'Phone%';
```

Nếu nhu cầu là tìm từ trong nội dung, SQL Server cung cấp Full-Text Search với full-text catalog và full-text index. Truy vấn dùng `CONTAINS` hoặc `FREETEXT` thay cho `LIKE` tùy yêu cầu. Full-text search áp dụng quy tắc word breaker, ngôn ngữ và token; nó không phải tìm chuỗi con tùy ý giống `%abc%`.

Với tìm hậu tố, có thể cân nhắc lưu thêm cột đảo chuỗi được tính toán và lập chỉ mục trên cột đó, nếu phép đảo và collation đáp ứng yêu cầu. Khi truy vấn hậu tố `'%xyz'`, đảo cả giá trị lẫn mẫu thành `'zyx%'` để dùng tiền tố. Cách này chỉ giải quyết tìm hậu tố, không giải quyết tìm chuỗi ở bất kỳ vị trí nào. Cần xác minh hàm đảo chuỗi, Unicode/surrogate pair và cách chuẩn hóa ký tự.

## 8. MySQL: range optimization và FULLTEXT

MySQL có thể tối ưu `LIKE` với mẫu không bắt đầu bằng wildcard bằng range access trên chỉ mục phù hợp, tùy collation, kiểu dữ liệu và dạng biểu thức. Ví dụ:

```sql
CREATE INDEX ix_product_name
ON product (product_name);

SELECT product_id, product_name
FROM product
WHERE product_name LIKE 'Phone%';
```

Với `LIKE '%phone%'`, B-tree trên `product_name` thông thường không cung cấp range seek theo tiền tố. Có thể xem `EXPLAIN` hoặc `EXPLAIN ANALYZE` phù hợp phiên bản để xác định access type và số hàng ước lượng.

MySQL/InnoDB hỗ trợ FULLTEXT index cho các kiểu cột và engine được hỗ trợ:

```sql
ALTER TABLE article
ADD FULLTEXT INDEX ft_article_content (title, body);

SELECT article_id, title
FROM article
WHERE MATCH(title, body)
      AGAINST ('database performance' IN NATURAL LANGUAGE MODE);
```

FULLTEXT dùng parser/tokenization và cấu hình ngôn ngữ, độ dài token tối thiểu/tối đa cùng stopword. Nó phù hợp tìm từ hoặc nội dung theo token, không thay thế hoàn toàn `LIKE '%...%'`. Cần kiểm tra parser mặc định hoặc ngram parser nếu tìm kiếm ngôn ngữ và chuỗi con yêu cầu khác biệt.

## 9. Oracle Database: B-tree, function-based index và Oracle Text

Oracle có thể sử dụng B-tree index cho `LIKE` có tiền tố cố định khi kiểu dữ liệu, collation và điều kiện phù hợp. Với tìm kiếm không phân biệt hoa thường, có thể cân nhắc function-based index trên `LOWER(column)` và viết truy vấn dùng cùng biểu thức:

```sql
CREATE INDEX ix_customer_name_lower
ON customer (LOWER(full_name));

SELECT customer_id, full_name
FROM customer
WHERE LOWER(full_name) LIKE LOWER(:prefix) || '%';
```

Đối với tìm kiếm văn bản phong phú, Oracle Text cung cấp các loại index và toán tử tìm kiếm phù hợp. Oracle Text hỗ trợ token, cụm từ, fuzzy và các chế độ tìm kiếm khác tùy cấu hình lexer, wordlist và datastore. Đây là mô hình tìm kiếm văn bản chuyên biệt, không đồng nghĩa với tìm chuỗi con tùy ý bằng `LIKE '%abc%'`.

Hãy xem execution plan, cấu hình collation, lexer và cách đồng bộ Oracle Text index. Việc cập nhật chỉ mục văn bản có thể dùng cơ chế đồng bộ khác với B-tree thông thường.

## 10. Tối ưu tìm kiếm hậu tố

Tìm chuỗi kết thúc bằng một hậu tố, ví dụ `LIKE '%@example.test'`, không thể seek hiệu quả bằng B-tree thông thường trên chuỗi gốc. Nếu nghiệp vụ chỉ cần tìm theo hậu tố cố định hoặc một số hậu tố có giới hạn, có thể lưu thêm giá trị đảo ngược:

```text
Giá trị gốc:       user@example.test
Giá trị đảo:       tset.elpmaxe@resu
Mẫu hậu tố:        %@example.test
Mẫu đảo tương ứng: tset.elpmaxe@%
```

Khi đó có thể tìm theo tiền tố trên cột đảo:

```sql
SELECT customer_id, email
FROM customer
WHERE reversed_email LIKE 'tset.elpmaxe@%';
```

Ví dụ chỉ minh họa ý tưởng. Cần dùng một hàm đảo chuỗi hoặc cột sinh phù hợp với hệ quản trị, bảo đảm cách đảo Unicode đúng với đơn vị ký tự mà nghiệp vụ mong muốn, và tạo index trên cột đảo. Nếu dữ liệu thay đổi, cột đảo phải được cập nhật nhất quán. Với email, cân nhắc chuẩn hóa domain và dùng điều kiện miền riêng có thể đơn giản hơn việc tìm mọi hậu tố.

Không dùng phương pháp đảo chuỗi cho `LIKE '%abc%'`, vì đảo chuỗi vẫn để wildcard ở đầu khi tìm nội dung bất kỳ. Phương pháp này chỉ chuyển một bài toán hậu tố thành bài toán tiền tố.

## 11. An toàn khi xây dựng mẫu LIKE

Tham số hóa truy vấn giúp ngăn việc nối dữ liệu đầu vào trực tiếp vào câu SQL, nhưng ký tự `%` và `_` trong giá trị tham số vẫn là wildcard của `LIKE`. Nếu người dùng nhập `%`, truy vấn có thể khớp gần như mọi chuỗi thay vì tìm ký tự phần trăm theo nghĩa đen.

Hãy định nghĩa ký tự escape và thoát các ký tự đặc biệt khi nghiệp vụ muốn tìm literal. Ví dụ dùng `!` làm ký tự escape:

```sql
SELECT product_id, product_name
FROM product
WHERE product_name LIKE ? ESCAPE '!';
```

Trước khi bind tham số, ứng dụng cần thay `!` thành `!!`, `%` thành `!%` và `_` thành `!_`; sau đó thêm wildcard do ứng dụng chủ động quyết định. Thứ tự thay thế cần tránh escape lại ký tự vừa được thêm. Quy tắc escape có thể khác đôi chút theo hệ quản trị, nên cần kiểm thử với dữ liệu chứa ký tự escape và wildcard.

Ví dụ nếu người dùng muốn tìm literal `A_100%`, mẫu sau khi escape và thêm wildcard tiền tố/hậu tố sẽ biểu diễn việc tìm chuỗi con:

```text
Đầu vào:          A_100%
Sau khi escape:   A!_100!%
Mẫu tìm contains: %A!_100!%%
Mệnh đề:          LIKE ? ESCAPE '!'
```

Nếu mục đích là tìm tiền tố, chỉ thêm `%` ở cuối. Không nên cho phép client tự gửi một mẫu tùy ý nếu nghiệp vụ không cần chức năng đó. Với SQL động, tham số hóa giá trị và allowlist các tên cột/sắp xếp; tên cột không thể thay bằng bind parameter thông thường.

## 12. Tham số hóa, kế hoạch thực thi và độ chọn lọc

Kế hoạch của `LIKE` có thể phụ thuộc mẫu cụ thể. `LIKE 'A%'` và `LIKE '%A%'` có khả năng truy cập dữ liệu rất khác nhau. Khi mẫu được truyền qua bind parameter, khả năng bộ tối ưu biết tiền tố lúc biên dịch phụ thuộc hệ quản trị, driver, prepared statement và cơ chế plan cache.

Trong một số tình huống, kế hoạch được biên dịch khi chưa biết mẫu cụ thể có thể không phản ánh tốt độ chọn lọc thực tế. Một kế hoạch phù hợp với tiền tố rất chọn lọc có thể không tốt cho tiền tố phổ biến; kế hoạch cho wildcard đầu có thể phải scan. Hãy kiểm tra tham số lúc biên dịch và lúc thực thi, thống kê, plan reuse và actual plan theo các mẫu đại diện.

Các mẫu kiểm thử nên gồm:

- Tiền tố hiếm, chẳng hạn `Qzx%`.
- Tiền tố phổ biến, chẳng hạn `A%`.
- Tiền tố dài và ngắn.
- Mẫu có `_` ở vị trí đầu hoặc sau tiền tố cố định.
- Mẫu bắt đầu bằng `%` và mẫu chứa `%` ở giữa.
- Giá trị có chữ hoa/thường, dấu, Unicode và ký tự escape.

Đừng đánh giá index chỉ bằng một mẫu kiểm thử. Một truy vấn tiền tố có thể nhanh với một chữ cái hiếm nhưng chậm với tiền tố phổ biến vì số hàng khớp lớn. Hãy đo p95/p99, logical reads, CPU, số hàng trả về và throughput.

## 13. Quy trình chọn giải pháp tìm kiếm

1. **Mô tả ngữ nghĩa:** xác định tiền tố, hậu tố, token, cụm từ hay chuỗi con tùy ý.
2. **Đo workload:** tần suất truy vấn, kích thước bảng, độ dài văn bản, phân bố tiền tố và tỷ lệ kết quả khớp.
3. **Kiểm tra chỉ mục hiện tại:** B-tree, composite index, collation và khả năng range scan.
4. **Thử viết lại điều kiện:** nếu tìm ngày hoặc mã theo khoảng có thể chuyển sang range predicate trên cột gốc.
5. **Chọn cấu trúc:** B-tree cho tiền tố; full-text cho token/ngôn ngữ; trigram/ngram cho chuỗi con; cột đảo cho hậu tố có quy tắc.
6. **Tạo thử trong môi trường kiểm thử:** ghi nhận chi phí xây dựng, dung lượng và tác động ghi.
7. **Đo actual plan:** xác nhận access path, estimated/actual rows, logical reads và CPU.
8. **Kiểm thử ngữ nghĩa:** dấu, Unicode, collation, `NULL`, wildcard literal và chuỗi rỗng.
9. **Đo dưới tải đồng thời:** p95/p99, throughput đọc/ghi, I/O và ảnh hưởng đến các truy vấn khác.
10. **Theo dõi vận hành:** độ mới của index chuyên biệt, độ trễ đồng bộ và thay đổi phân bố dữ liệu.

### Bảng chọn nhanh

| Yêu cầu | Giải pháp nên đánh giá đầu tiên | Lưu ý |
|---|---|---|
| Tìm mã/tên bắt đầu bằng chuỗi | B-tree trên cột hoặc chỉ mục ghép | Kiểm tra collation và độ chọn lọc tiền tố |
| Tìm chuỗi kết thúc bằng hậu tố | Cột đảo có B-tree hoặc cấu trúc chuyên biệt | Chỉ chuyển suffix thành prefix; kiểm tra Unicode |
| Tìm từ trong tài liệu | Full-text index | Ngữ nghĩa theo token, parser và ngôn ngữ |
| Tìm chuỗi con bất kỳ | Trigram/ngram index | Chỉ mục lớn hơn; mẫu ngắn có thể ít chọn lọc |
| Tìm gần đúng hoặc tương đồng | Trigram/fuzzy search hoặc công cụ tìm kiếm | Cần xác định ngưỡng và xếp hạng |
| Bảng nhỏ, truy vấn hiếm | Scan có thể đủ | Đo tổng chi phí trước khi thêm index |

## 14. Những sai lầm thường gặp

1. **Cho rằng mọi `LIKE` đều dùng B-tree:** wildcard đầu làm mất tiền tố cố định để seek.
2. **Nhầm index scan với index seek:** quét toàn bộ index vẫn có thể tốn chi phí gần với quét bảng.
3. **Dùng full-text thay cho contains mà không kiểm tra ngữ nghĩa:** token search không khớp mọi chuỗi con.
4. **Dùng trigram cho mẫu quá ngắn:** không đủ trigram để loại nhiều ứng viên.
5. **Bỏ qua collation:** cùng một mẫu có thể cho kết quả và kế hoạch khác giữa môi trường.
6. **Nối trực tiếp đầu vào vào SQL:** tạo nguy cơ injection và wildcard không mong muốn.
7. **Quên escape `%` và `_`:** ký tự người dùng nhập bị hiểu thành wildcard.
8. **Tạo index chuyên biệt mà không đo ghi:** dung lượng và chi phí cập nhật có thể lớn.
9. **Chỉ kiểm thử một tiền tố:** không phát hiện khác biệt về độ chọn lọc và kế hoạch theo mẫu.
10. **Không xem actual plan:** có index không đồng nghĩa bộ tối ưu sẽ chọn index đó.

## 15. Danh sách kiểm tra trước khi tối ưu LIKE

- [ ] Đã xác định chính xác tìm tiền tố, hậu tố, từ hay chuỗi con tùy ý.
- [ ] Đã phân biệt mẫu có tiền tố cố định với mẫu có wildcard đầu.
- [ ] Đã kiểm tra B-tree và thứ tự cột của chỉ mục ghép hiện tại.
- [ ] Đã xác minh collation, kiểu dữ liệu và ngữ nghĩa hoa thường/Unicode.
- [ ] Đã đánh giá full-text, trigram/ngram hoặc cột đảo theo yêu cầu thực tế.
- [ ] Đã tham số hóa truy vấn và escape wildcard literal khi cần.
- [ ] Đã kiểm thử mẫu hiếm, phổ biến, ngắn, dài và có ký tự đặc biệt.
- [ ] Đã so sánh estimated rows với actual rows và kiểm tra access path.
- [ ] Đã đo p95/p99, logical reads, CPU, throughput và chi phí ghi.
- [ ] Đã xác định cách cập nhật, đồng bộ và bảo trì chỉ mục chuyên biệt.

`LIKE` rất hữu ích nhưng hình dạng mẫu quyết định khả năng tối ưu. Mẫu có tiền tố cố định như `'abc%'` thường có thể tận dụng B-tree bằng một khoảng khóa; mẫu có wildcard đầu như `'%abc'` hoặc `'%abc%'` thường không thể seek hiệu quả trên B-tree của chuỗi gốc. Hãy chọn cấu trúc theo đúng ngữ nghĩa tìm kiếm: B-tree cho tiền tố, cột đảo cho hậu tố có quy tắc, full-text cho từ và cụm từ, trigram/ngram cho chuỗi con. Cuối cùng, kiểm chứng execution plan và đo cả chi phí đọc lẫn ghi trên workload đại diện.
