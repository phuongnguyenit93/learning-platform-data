# pg_trgm, độ tương đồng và tìm kiếm gần đúng trong PostgreSQL

Một người dùng tìm sản phẩm `"ban phim co"` trong ứng dụng thương mại điện tử. Danh mục lại lưu tên `"Bàn phím cơ không dây"`. Người khác nhập `"bluetooh"` thay vì `"bluetooth"` hoặc chỉ nhớ một phần tên `"mechanical keyboard"`. Truy vấn so khớp chính xác (`=`) có thể không tìm được kết quả mong muốn; còn `LIKE '%...%'` không nhất thiết chịu được lỗi gõ.

PostgreSQL có extension **`pg_trgm`** giúp so sánh các chuỗi theo những cụm **ba ký tự liên tiếp** (*trigrams*), tính điểm tương đồng và tìm những tên gần giống nhau. Khi kết hợp với **GIN** hoặc **GiST trigram indexes**, PostgreSQL có thể tìm ứng viên nhanh hơn việc tính điểm cho toàn bộ bảng trong những trường hợp phù hợp.

~~~sql
-- Ví dụ ý tưởng, sau khi cài pg_trgm:
SELECT
    product_id,
    product_name,
    similarity(product_name, 'ban phim co') AS score
FROM catalog_products
WHERE product_name % 'ban phim co'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Tuy nhiên, `pg_trgm` **không hiểu ngữ nghĩa tiếng Việt**, không tự bỏ dấu, không tự dịch ngôn ngữ và không thể khẳng định hai tên là cùng một thực thể. Nó cũng khác với full-text search (`tsvector`/`tsquery`): một cơ chế thiên về **giống nhau ở cấp ký tự**, cơ chế kia thiên về **token/lexeme và truy vấn từ vựng**.

Mục tiêu của bài là sử dụng công cụ đúng mục đích: hiểu điểm số và ngưỡng, viết SQL có thể tận dụng index, đánh giá kết quả bằng dữ liệu thật, và tránh biến tìm kiếm gần đúng thành một phép xác minh danh tính hoặc quyền truy cập thiếu an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả trigram và lý do sai một vài ký tự có thể vẫn cho độ tương đồng dương.
2. Cài đặt, kiểm tra và sử dụng extension `pg_trgm` trong database được phép.
3. Dùng `show_trgm`, `similarity`, `word_similarity` và `strict_word_similarity`.
4. Phân biệt so khớp cả chuỗi, một phần chuỗi và ranh giới từ.
5. Sử dụng các toán tử `%`, `<%`, `%>`, `<<%`, `%>>`.
6. Tính khoảng cách `<->`, `<<->`, `<<<->` và hiểu ý nghĩa `ORDER BY ... LIMIT`.
7. Điều chỉnh `pg_trgm.similarity_threshold`, `word_similarity_threshold`, `strict_word_similarity_threshold` trong phạm vi transaction.
8. Tạo `GIN ... gin_trgm_ops` và `GiST ... gist_trgm_ops`, so sánh điểm mạnh và giới hạn.
9. Hiểu vì sao **GiST** hỗ trợ tìm **nearest neighbors** trực tiếp theo khoảng cách hiệu quả, còn GIN thường dùng để lọc ứng viên.
10. Tìm substring bằng `LIKE`/`ILIKE` và hiểu giới hạn pattern quá ngắn hoặc không rút được trigrams.
11. Đọc `EXPLAIN (ANALYZE, BUFFERS)` để xác định index path, lọc lại và sort.
12. Tránh nhầm so khớp ký tự với tìm đồng nghĩa, tách từ, chuẩn hóa dấu hoặc full-text search.
13. Thiết kế chiến lược chuẩn hóa Unicode/tiếng Việt có kiểm soát khi cần.
14. Xây dựng API gợi ý chính tả và tìm sản phẩm gần đúng bằng prepared statements Java/JDBC.
15. Đánh giá precision/recall, false positives, threshold, tốc độ và chi phí bảo trì index.

## 2. Tìm kiếm chính xác, tìm chuỗi con và tìm gần đúng

Ba yêu cầu thường gặp nhưng khác bản chất:

| Yêu cầu | Ví dụ | Công cụ khởi đầu |
| --- | --- | --- |
| **Khớp chính xác** | SKU bằng `'KB-001'` | B-tree + `=` |
| **Khớp tiền tố/chuỗi con** | Tên chứa `'phím'` | `LIKE`/`ILIKE`; trigram index nếu phù hợp |
| **Khớp gần đúng** | `'bluetooh'` gần `'bluetooth'` | `pg_trgm` similarity/word similarity |
| **Tìm văn bản theo ý nghĩa từ vựng** | Văn bản chứa nhiều từ khóa, stemming | Full-text search `tsvector`/`tsquery` |
| **Đồng nghĩa hoặc ngữ nghĩa** | `'máy tính xách tay'` gần `'laptop'` | Từ điển đồng nghĩa, ứng dụng hoặc hệ tìm kiếm phù hợp |

**Đừng dùng `pg_trgm` để xác thực mã đơn hàng, quyền người dùng, token bảo mật hoặc khóa tham chiếu.** Những trường cần tính chính xác phải dùng so khớp chính xác và ràng buộc dữ liệu.

### 2.1. Vì sao LIKE chưa đủ?

~~~sql
WHERE product_name ILIKE '%bluetooth%'
~~~

có thể tìm tên chứa chuỗi `bluetooth`, không phân biệt hoa/thường theo ngữ nghĩa collation phù hợp. Nhưng người dùng nhập thiếu chữ `t` thành `bluetooh` thì substring gốc không còn xuất hiện. Trigram similarity có thể đưa hai từ vào một **nhóm ứng viên gần nhau**.

### 2.2. Vì sao full-text search chưa đủ?

Full-text search rất hữu ích khi cần tokenization, ranking theo lexeme và search nhiều từ, nhưng lỗi gõ khiến từ tìm kiếm không còn trùng lexeme có thể làm mất kết quả. Trigram có thể **gợi ý sửa từ gõ sai**, hoặc làm lớp fallback sau khi một full-text search chuẩn không đủ kết quả.

### 2.3. Kết quả gần đúng là ứng viên, không phải sự thật

Hai người tên `An` và `Anh` có thể gần về ký tự nhưng **không chắc là cùng người**. Hai sản phẩm `"Cáp USB-C 1m"` và `"Cáp USB-C 2m"` có thể rất giống, nhưng khác chiều dài và có thể khác giá. Kết quả tìm gần đúng phải được hiển thị, phân loại và xác nhận theo nghiệp vụ.

## 3. Cài đặt extension pg_trgm

`pg_trgm` là một extension được cung cấp cùng bộ PostgreSQL (contrib module), nhưng phải **được tạo trong từng database** trước khi dùng các functions/operators/index operator classes.

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

Lệnh có thể yêu cầu quyền `CREATE` trên database và chính sách của môi trường. Trong những phiên bản PostgreSQL hiện đại, `pg_trgm` được phân loại là extension **trusted**; role không phải superuser có quyền phù hợp có thể cài. Trên managed database, extension còn phụ thuộc danh sách được provider cho phép.

**Không tự chạy `CREATE EXTENSION` trên production** nếu chưa có quyền/chính sách thay đổi schema. Các ví dụ còn lại giả định đã có `pg_trgm`.

### 3.1. Kiểm tra extension đã có

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS installed_schema
FROM pg_catalog.pg_extension
WHERE extname = 'pg_trgm';
~~~

Nếu không trả hàng, extension chưa được cài trong database hiện tại. `CREATE EXTENSION IF NOT EXISTS` tránh lỗi khi đã có extension nhưng **không cam kết extension hiện tại nằm trong schema mà ứng dụng mong muốn**.

### 3.2. Phạm vi database và search_path

PostgreSQL extensions được cài **ở mức database**, không tự động xuất hiện trong các database khác cùng instance. Schema chứa functions/operators của extension và `search_path` có thể ảnh hưởng cách gọi tên không schema-qualified. Trong tài liệu, các ví dụ giả định extension được cài ở vị trí truy cập được qua `search_path` thông thường.

### 3.3. Kiểm tra functions

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS overall_similarity,
    show_trgm('cat') AS cat_trigrams;
~~~

`similarity` trả kiểu `real`, giá trị từ 0 đến 1. `show_trgm` trả `text[]`, thường dùng để **học và gỡ lỗi cách tách trigram**, không phải kết quả search cần gửi nguyên cho người dùng cuối.

## 4. Trigram là gì?

**Trigram** là một nhóm ba ký tự liên tiếp được dùng để đại diện cho những mảnh nhỏ của một chuỗi. Đối với mỗi *word*, `pg_trgm` thêm **hai dấu cách phía trước** và **một dấu cách phía sau**, rồi lấy các bộ ba liên tiếp. Các ký tự không phải ký tự của từ (*non-word characters*) được bỏ qua trong bước trích trigrams.

Ví dụ với `cat`:

~~~text
Chuỗi gốc:        cat
Chuỗi có padding: "  cat "

Các trigram:
  "  c"
  " ca"
  "cat"
  "at "
~~~

Với `cat` và `cut`, các trigram ở phần đầu/cuối có thể trùng nhau dù một ký tự ở giữa khác. Với chuỗi dài, một lỗi gõ thường làm thay đổi một phần nhỏ bộ trigrams chứ không thay toàn bộ.

### 4.1. Thực hành show_trgm

~~~sql
SELECT
    show_trgm('cat') AS trigrams_cat,
    show_trgm('cut') AS trigrams_cut,
    show_trgm('bluetooth') AS trigrams_bluetooth,
    show_trgm('bluetooh') AS trigrams_typo;
~~~

Hãy đối chiếu các phần tử của hai mảng trigrams. Số lượng/biểu diễn cụ thể với các ký tự đa byte có thể khác cách bạn tưởng nếu tự cắt chuỗi theo byte, nên **không tự viết bộ tách trigram bằng cách lấy ba bytes đầu tiên**.

### 4.2. Dấu câu không phải ký tự tìm kiếm độc lập

~~~sql
SELECT
    show_trgm('foo|bar') AS separated_words,
    show_trgm('foo bar') AS with_space;
~~~

Các ký tự phân tách không phải word characters sẽ không hoạt động như các ký tự bình thường khi xây trigram. Vì vậy `pg_trgm` **không luôn phân biệt mạnh dấu `-`, `|` hoặc các dấu câu** trong mã định danh.

Điều này là một lý do **không dùng similarity để xác minh SKU hay mã giao dịch**: `AB-123` và `AB123` có thể có điểm số khác điều nghiệp vụ mong muốn.

### 4.3. Trigram không phải embedding hoặc từ đồng nghĩa

~~~text
"laptop" vs "máy tính xách tay"
~~~

Hai cụm có thể chỉ rất ít trigrams chung dù cùng ý nghĩa. Tương tự, hai tên sản phẩm khác dung lượng/phân loại nhưng có phần lớn ký tự giống nhau có thể được điểm số khá cao.

**Tương đồng trigram là tín hiệu ở cấp ký tự, không phải chứng minh ngữ nghĩa.**

### 4.4. Vấn đề ngắn và dài

Với chuỗi quá ngắn như `"a"` hay `"an"`, chỉ có rất ít trigrams hữu ích; việc chọn kết quả gần đúng dễ nhiễu. Với một đoạn rất dài, `similarity` trên cả chuỗi có thể thấp dù người dùng gõ đúng một từ ở giữa. Đây là lý do cần thêm **word similarity**, **strict word similarity** và chiến lược fallback theo độ dài query.

## 5. similarity(text, text): so sánh toàn chuỗi

~~~sql
SELECT
    similarity('keyboard', 'keyboard') AS exact_score,
    similarity('keyboard', 'keybord') AS typo_score,
    similarity('keyboard', 'monitor') AS unrelated_score;
~~~

Điểm:

- Nằm trong khoảng **0 đến 1**.
- Điểm cao thường tương ứng có nhiều trigrams giống nhau.
- `1` nghĩa rất tương đồng theo bộ trigram đang dùng, **không thay cho phép kiểm tra chuỗi SQL bằng `=`** trong mọi hệ thống.
- Không chuyển đổi ra “xác suất 95% là cùng sản phẩm”.

### 5.1. similarity đối xứng

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS a_to_b,
    similarity('keybord', 'keyboard') AS b_to_a;
~~~

`similarity` trên hai tập trigram là phép đo đối xứng. Điều này khác với **word_similarity**: lời gọi có vai trò “từ/cụm tìm kiếm” ở đối số đầu và “chuỗi chứa đoạn cần dò” ở đối số thứ hai.

### 5.2. Điểm số cần được xếp hạng ổn định

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keyboard') AS score
FROM catalog_products
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Đây là dạng truy vấn lý tưởng hóa, sẽ được áp dụng trên bảng lab ở phần sau. `product_id` là tie-breaker: các hàng có score bằng nhau được sắp theo thứ tự xác định, hữu ích cho API và pagination.

### 5.3. Tại sao không luôn dùng similarity cả câu?

So sánh `"wireless"` với `"wireless mechanical keyboard"` có thể cho điểm khá thấp vì tên sản phẩm chứa nhiều trigrams khác. Nhưng người dùng chỉ nhớ một **từ nằm trong tên**, không nhất thiết muốn tên sản phẩm dài bị xếp hạng thấp. Khi đó `word_similarity('wireless', full_name)` có thể phù hợp hơn.

## 6. word_similarity(text, text): khớp một đoạn liên tục

`word_similarity(search_term, candidate_text)` tìm mức tương đồng cao nhất giữa bộ trigram của đối số đầu và **một đoạn liên tục trong dãy trigram có thứ tự** của đối số thứ hai.

~~~sql
SELECT
    similarity('word', 'two words') AS entire_string,
    word_similarity('word', 'two words') AS best_extent,
    word_similarity('words', 'two words') AS word_variant;
~~~

Theo ví dụ tài liệu chính thức, `word_similarity('word', 'two words')` là **0.8**; cách tính dựa trên những trigram liên tục tương đồng với `word`, không phải phép so sánh toàn chuỗi.

### 6.1. Hướng đối số quan trọng

~~~sql
SELECT
    word_similarity(
        'bluetooth',
        'Tai nghe bluetooth khong day'
    ) AS query_inside_title,
    word_similarity(
        'Tai nghe bluetooth khong day',
        'bluetooth'
    ) AS whole_title_inside_query;
~~~

Hai kết quả **không nhất thiết bằng nhau**. Tình huống search thông thường đặt **term người dùng ở đối số thứ nhất**, chuỗi tên sản phẩm/đoạn văn ở đối số thứ hai.

### 6.2. Word similarity không bắt buộc ranh giới nguyên từ

`word_similarity` tìm đoạn trigrams, và **không buộc** ranh giới của đoạn ấy trùng đầy đủ ranh giới từ. Điều này có thể tốt cho một từ người dùng chỉ gõ một phần, nhưng cũng dễ khớp một chuỗi con gây false positive.

~~~sql
SELECT
    word_similarity('key', 'keyboard') AS substring_match,
    strict_word_similarity('key', 'keyboard') AS whole_word_match;
~~~

Kết quả có thể khác đáng kể do strict version phải tôn trọng ranh giới từ trong chuỗi thứ hai.

### 6.3. Dùng khi nào?

`word_similarity` phù hợp khi query là **một từ/cụm ngắn** và tên/miêu tả có thể chứa nhiều từ. Không mặc định nó lý tưởng cho so sánh hai đoạn dài hoặc nhận diện thực thể có mã khác nhau.

## 7. strict_word_similarity(text, text): ranh giới từ

`strict_word_similarity(search_term, candidate_text)` có cùng ý tưởng “tìm phần tương đồng nhất trong chuỗi thứ hai”, nhưng yêu cầu đoạn được chọn trùng với **ranh giới từ**.

~~~sql
SELECT
    strict_word_similarity('word', 'two words')
        AS strict_score,
    similarity('word', 'words')
        AS simple_score;
~~~

Trong ví dụ tài liệu chính thức, hai giá trị đều khoảng **0.571429**. Kết quả này giúp thấy strict word similarity chọn **toàn từ** `words` thay vì một extent giữa từ.

### 7.1. Chọn giữa similarity, word_similarity, strict_word_similarity

| Hàm | So sánh gì? | Trường hợp phù hợp |
| --- | --- | --- |
| `similarity(a,b)` | Tương đồng của hai chuỗi theo trigram sets | So hai tên có độ dài tương tự, dedup candidates |
| `word_similarity(a,b)` | Đoạn liên tục tốt nhất của `b`, có thể ở giữa từ | Autocomplete/partial-word fuzzy matching |
| `strict_word_similarity(a,b)` | Đoạn liên tục theo **ranh giới toàn từ** của `b` | So từ/cụm tìm kiếm với một nhóm từ hoàn chỉnh |

### 7.2. “Strict” không có nghĩa exact

`strict_word_similarity` vẫn là **độ tương đồng gần đúng**, không phải phép kiểm tra từ khóa trùng 100%. Một lỗi gõ trong một từ vẫn có thể khớp nếu điểm đủ cao.

### 7.3. Khi người dùng nhập tên dài

Với input `"chuot gaming khong day"`, full-string similarity, word similarity và strict word similarity có thể xếp các sản phẩm theo thứ tự khác nhau. Để quyết định dùng cách nào, hãy **đánh giá search relevance bằng bộ query thực** thay vì coi một hàm là mặc định tốt nhất cho mọi tên.

## 8. Bảng dữ liệu thực hành

Ta dùng schema riêng `trgm_lab_327` và một bảng sản phẩm có tên tiếng Việt, tên tiếng Anh, các trường hợp typo và tên gần nhau nhưng khác thông số.

### 8.1. Tạo schema và bảng

~~~sql
-- Phải cài trong database bằng tài khoản được phép:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA trgm_lab_327;

CREATE TABLE trgm_lab_327.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
~~~

### 8.2. Nạp bộ dữ liệu minh họa

~~~sql
INSERT INTO trgm_lab_327.products
    (product_id, sku, product_name, category, description, is_active)
VALUES
    (1, 'KB-001', 'Bàn phím cơ không dây', 'keyboard',
        'Bàn phím mechanical kết nối Bluetooth', TRUE),
    (2, 'KB-002', 'Bàn phím cơ có dây', 'keyboard',
        'Mechanical keyboard dùng cáp USB-C', TRUE),
    (3, 'KB-003', 'Bàn phím văn phòng', 'keyboard',
        'Bàn phím phổ thông gõ văn bản', TRUE),
    (4, 'KB-004', 'Wireless mechanical keyboard', 'keyboard',
        'Compact keyboard with Bluetooth', TRUE),
    (5, 'KB-005', 'Mechanical keyboard RGB', 'keyboard',
        'Gaming keyboard 87 keys', TRUE),
    (6, 'MS-001', 'Chuột không dây Bluetooth', 'mouse',
        'Chuột máy tính kết nối Bluetooth', TRUE),
    (7, 'MS-002', 'Chuột gaming không dây', 'mouse',
        'Wireless gaming mouse', TRUE),
    (8, 'MS-003', 'Chuột gaming có dây', 'mouse',
        'Wired gaming mouse', TRUE),
    (9, 'HD-001', 'Tai nghe Bluetooth không dây', 'headphone',
        'Tai nghe chụp tai có microphone', TRUE),
    (10, 'HD-002', 'Tai nghe Bluetooh thể thao', 'headphone',
        'Tên có typo có chủ ý để kiểm thử', TRUE),
    (11, 'CB-001', 'Cáp USB-C 1m', 'cable',
        'Cáp sạc dài một mét', TRUE),
    (12, 'CB-002', 'Cáp USB-C 2m', 'cable',
        'Cáp sạc dài hai mét', TRUE),
    (13, 'LB-001', 'Laptop văn phòng 14 inch', 'laptop',
        'Máy tính xách tay phục vụ công việc', TRUE),
    (14, 'LB-002', 'Máy tính xách tay đồ họa', 'laptop',
        'Laptop GPU rời', TRUE),
    (15, 'DP-001', 'Màn hình máy tính 24 inch', 'monitor',
        'Màn hình độ phân giải Full HD', TRUE),
    (16, 'DP-002', 'Màn hình máy tính 27 inch', 'monitor',
        'Màn hình độ phân giải QHD', TRUE),
    (17, 'KB-006', 'Ban phim co khong day', 'keyboard',
        'Tên không dấu có chủ ý', TRUE),
    (18, 'KB-007', 'Bàn phím cơ không dây mini', 'keyboard',
        'Bàn phím nhỏ gọn', TRUE),
    (19, 'MS-004', 'Chuột Bluetooth', 'mouse',
        'Phiên bản cũ ngừng bán', FALSE),
    (20, 'HD-003', 'Headphones wireless noise cancelling', 'headphone',
        'Over-ear headset', TRUE);

ANALYZE trgm_lab_327.products;
~~~

Tất cả sản phẩm đều có `product_id` và `sku` không trùng. `sku` được dùng để minh họa **tìm chính xác**, không dùng similarity để xác minh mã. `is_active` cho phép bài thực hành chỉ tìm sản phẩm còn bán.

### 8.3. Kết quả search là dữ liệu phụ thuộc ngưỡng

Các truy vấn similarity phía dưới thường dùng `ORDER BY score DESC` hoặc `distance ASC`. **Thứ tự và số lượng hàng chính xác cần được đo bằng PostgreSQL thực tế**, không tự suy đoán ngưỡng 0.3 phải cho đúng mười kết quả với mọi ngôn ngữ/collation.

### 8.4. Vì sao có cả có dấu và không dấu?

`'Bàn phím cơ không dây'` và `'Ban phim co khong day'` có phần ký tự khác nhau. Trigram so sánh các ký tự, **không tự “biết” rằng chúng tương đương khi bỏ dấu**. Việc tạo một bản chuẩn hóa không dấu là quyết định dữ liệu riêng, sẽ được trình bày ở phần sau.

## 9. Truy vấn đơn giản: hiển thị điểm gần đúng

~~~sql
SELECT
    product_id,
    product_name,
    ROUND(
        similarity(product_name, 'bluetooh')::numeric,
        3
    ) AS score
FROM trgm_lab_327.products
WHERE is_active
ORDER BY
    similarity(product_name, 'bluetooh') DESC,
    product_id
LIMIT 10;
~~~

Query này **chỉ xếp hạng toàn bộ các sản phẩm active** theo điểm, ngay cả những sản phẩm rất không liên quan có thể vẫn hiện trong top 10 nếu không có ngưỡng lọc.

### 9.1. Thêm ngưỡng điểm

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'bluetooh') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND similarity(product_name, 'bluetooh') >= 0.3
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Đây là cách diễn đạt ngưỡng **cố định trong biểu thức** rất dễ hiểu. Tuy nhiên, dạng `similarity(...) >= ...` **không phải toán tử lọc trigram được thiết kế để dùng index theo ngưỡng** như `%`. Với bảng lớn, nên ưu tiên dạng operator có index support hoặc chiến lược top-N phù hợp.

### 9.2. Một điểm cao không xác nhận đúng sản phẩm

`'Cáp USB-C 1m'` và `'Cáp USB-C 2m'` có phần lớn trigrams tương đồng nhưng đại diện hai thông số hàng hóa khác nhau. Không tự động đổi mục hàng trong giỏ hàng dựa trên `similarity`; hãy yêu cầu lựa chọn `product_id`/`sku` cụ thể.

## 10. Toán tử %: lọc theo ngưỡng similarity

Toán tử:

~~~sql
text_expression % text_expression
~~~

trả SQL `boolean`, kiểm tra độ tương đồng của hai đối số có vượt qua **`pg_trgm.similarity_threshold`** hiện tại không. Mặc định trong tài liệu PostgreSQL hiện hành thường là **0.3**.

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'bluetooh') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'bluetooh'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Điểm đặc biệt là `%` **có index support** từ các operator classes `gin_trgm_ops` và `gist_trgm_ops` khi có index/plan phù hợp. Việc viết `similarity(product_name, 'bluetooh') > 0.3` ở WHERE không đảm bảo planner tạo cùng indexed access path.

### 10.1. Biểu diễn tương đương về mục tiêu, khác khả năng dùng index

~~~sql
-- Lọc bằng toán tử có index support:
WHERE product_name % 'bluetooh'

-- Tự tính điểm để so với số cố định:
WHERE similarity(product_name, 'bluetooh') >= 0.3
~~~

Hai biểu thức **không hoàn toàn đồng nhất** vì toán tử dựa vào threshold hiện thời và dùng điều kiện vượt threshold, còn dạng thứ hai có ngưỡng 0.3 và so sánh `>=`; cũng không có cùng điều kiện sargability cho trigram index.

### 10.2. Không đặt câu trả lời chỉ dựa trên dấu %

Nếu độ tương đồng ngưỡng 0.3 đưa vào những sản phẩm không liên quan, giảm hay tăng threshold là một quyết định **chất lượng gợi ý**. Lý tưởng là đo **precision/recall** và trải nghiệm người dùng trước khi lựa chọn.

### 10.3. Ngưỡng quá thấp có thể tăng chi phí

Khi threshold thấp, nhiều hàng hơn thỏa `%`. Index có thể trả nhiều ứng viên cần heap recheck, query còn phải tính điểm/sort, nên không mặc định cứ có GIN là search luôn nhanh.

## 11. Toán tử <% và %>: word similarity

Word similarity có các toán tử:

| Toán tử | Ý nghĩa |
| --- | --- |
| `query <% candidate` | Kiểm tra `word_similarity(query, candidate)` vượt ngưỡng |
| `candidate %> query` | **Commutator** của `query <% candidate` |

Ngưỡng được điều khiển bởi `pg_trgm.word_similarity_threshold`, mặc định thường **0.6**.

### 11.1. Tìm từ gần giống nằm trong tên dài

~~~sql
SELECT
    product_id,
    product_name,
    word_similarity('bluetooh', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND 'bluetooh' <% product_name
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Ở đây:

- `'bluetooh'` là **term người dùng** (bên trái);
- `product_name` là **văn bản cần tìm đoạn giống nhất** (bên phải).

Khi có trigram index trên `product_name`, toán tử word-similarity có thể dùng index để giảm ứng viên.

### 11.2. Đảo thứ tự bằng commutator

~~~sql
SELECT
    product_id,
    product_name,
    word_similarity('bluetooh', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name %> 'bluetooh'
ORDER BY score DESC, product_id;
~~~

`%>` là cách viết **đảo vị trí hai đối số** của `<%`, không phải một họ similarity mới.

### 11.3. Đảo hàm không phải commutator

~~~sql
word_similarity('bluetooh', product_name)
~~~

và:

~~~sql
word_similarity(product_name, 'bluetooh')
~~~

không nhất thiết cho cùng kết quả. Muốn đổi cách trình bày điều kiện để đặt cột ở bên trái, dùng **toán tử commutator `%>`**, không âm thầm đảo hai đối số rồi giữ `<%`.

### 11.4. Dùng word similarity cho tên mô tả dài

~~~sql
SELECT
    product_id,
    product_name,
    word_similarity('wireless', description) AS description_score
FROM trgm_lab_327.products
WHERE word_similarity('wireless', description) > 0.5
ORDER BY description_score DESC, product_id;
~~~

Ví dụ này tính score trên `description`; nếu muốn lọc bằng trigram index thì cần index **trên chính `description`** hoặc biểu thức tương ứng, và dùng toán tử word-similarity phù hợp với threshold cài đặt.

## 12. Toán tử <<% và %>>: strict word similarity

| Toán tử | Ý nghĩa |
| --- | --- |
| `query <<% candidate` | `strict_word_similarity(query,candidate)` vượt ngưỡng |
| `candidate %>> query` | Commutator của `<<%` |

Ngưỡng bởi `pg_trgm.strict_word_similarity_threshold`, mặc định thường **0.5**.

~~~sql
SELECT
    product_id,
    product_name,
    strict_word_similarity('gaming', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND 'gaming' <<% product_name
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Toán tử này hữu ích khi bạn không muốn một đoạn **giữa từ** được coi là điểm khớp tốt nhất; nhưng vẫn là so khớp gần đúng theo từ, không phải exact word match.

### 12.1. So với word similarity

~~~sql
SELECT
    product_name,
    word_similarity('key', product_name) AS loose_score,
    strict_word_similarity('key', product_name) AS strict_score
FROM trgm_lab_327.products
WHERE product_id IN (4, 5)
ORDER BY product_id;
~~~

Mục đích là quan sát sự khác biệt giữa một đoạn `key` nằm trong `keyboard` và yêu cầu ranh giới từ hoàn chỉnh. **Không kết luận điểm strict phải bằng 0**, vì điểm tương đồng giữa `key` và cả từ `keyboard` vẫn có thể dương.

### 12.2. Chọn ngưỡng strict bằng dữ liệu thật

Ngưỡng 0.5 chỉ là điểm xuất phát. Một tên sản phẩm chứa chữ viết tắt, nhãn hiệu, số model hay từ nhiều âm tiết có thể cần chính sách khác. Không lấy một ngưỡng cho cả tên sản phẩm, mô tả dài, email và tên người nếu chưa đo độ phù hợp.

## 13. Các tham số ngưỡng trong pg_trgm

Ba ngưỡng độc lập:

| GUC | Toán tử sử dụng | Mặc định tham khảo |
| --- | --- | ---: |
| `pg_trgm.similarity_threshold` | `%` | 0.3 |
| `pg_trgm.word_similarity_threshold` | `<%` và `%>` | 0.6 |
| `pg_trgm.strict_word_similarity_threshold` | `<<%` và `%>>` | 0.5 |

### 13.1. Xem ngưỡng hiện tại

~~~sql
SHOW pg_trgm.similarity_threshold;
SHOW pg_trgm.word_similarity_threshold;
SHOW pg_trgm.strict_word_similarity_threshold;
~~~

### 13.2. Thử thay đổi chỉ trong transaction

~~~sql
BEGIN;

SET LOCAL pg_trgm.similarity_threshold = 0.45;

SELECT
    product_id,
    product_name,
    similarity(product_name, 'bluetooh') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'bluetooh'
ORDER BY score DESC, product_id;

ROLLBACK;
~~~

Sau `ROLLBACK`, giá trị `SET LOCAL` không còn áp dụng. Cách này thích hợp cho thí nghiệm không làm thay đổi ngưỡng tìm kiếm ở những request khác hoặc trên connection pool về sau.

### 13.3. Thử word similarity

~~~sql
BEGIN;

SET LOCAL pg_trgm.word_similarity_threshold = 0.5;

SELECT
    product_id,
    product_name,
    word_similarity('bluetooh', product_name) AS score
FROM trgm_lab_327.products
WHERE 'bluetooh' <% product_name
ORDER BY score DESC, product_id;

ROLLBACK;
~~~

### 13.4. Thử strict word similarity

~~~sql
BEGIN;

SET LOCAL pg_trgm.strict_word_similarity_threshold = 0.65;

SELECT
    product_id,
    product_name,
    strict_word_similarity('gaming', product_name) AS score
FROM trgm_lab_327.products
WHERE 'gaming' <<% product_name
ORDER BY score DESC, product_id;

ROLLBACK;
~~~

### 13.5. Đừng dùng set_limit/show_limit cho code mới

Các hàm `set_limit(real)` và `show_limit()` là API cũ liên quan threshold `%` và được đánh dấu **deprecated**. Trên phiên bản hỗ trợ GUC, ưu tiên `SHOW` và `SET LOCAL pg_trgm.similarity_threshold` thay vì rải `set_limit` trong logic ứng dụng.

### 13.6. Vấn đề connection pool

Lệnh `SET pg_trgm.similarity_threshold = 0.4` ở mức **session** có thể còn trên connection được pool tái sử dụng. Kết quả search của request sau sẽ thay đổi ngoài ý muốn nếu pool không reset session state.

**Nguyên tắc:** thực nghiệm bằng transaction + `SET LOCAL`, hoặc cấu hình ngưỡng được quản lý rõ ràng cho từng loại query/session. Không ghi thay đổi ngưỡng toàn server chỉ để thử một truy vấn.

### 13.7. Không biến threshold thành ngưỡng xác minh định danh

Ngưỡng 0.8 hay 0.95 không có nghĩa “độ tin cậy 80%/95%”. Chỉ dùng ngưỡng để **lọc ứng viên search**; nếu cần nhận diện sản phẩm/chủ thể, còn phải kiểm tra các thuộc tính chính xác khác.

## 14. Khoảng cách trigram: <->, <<-> và <<<->

Ngoài điểm `similarity` càng lớn càng giống, `pg_trgm` còn có các toán tử **distance** càng nhỏ càng giống.

| Toán tử | Công thức logic | Hướng |
| --- | --- | --- |
| `a <-> b` | `1 - similarity(a,b)` | Đối xứng |
| `a <<-> b` | `1 - word_similarity(a,b)` | `a` là term, `b` là candidate |
| `a <->> b` | Commutator của `b <<-> a` | Đổi vị trí đối số |
| `a <<<-> b` | `1 - strict_word_similarity(a,b)` | `a` là term, `b` là candidate |
| `a <->>> b` | Commutator của `b <<<-> a` | Đổi vị trí đối số |

Các distance thường nằm trong khoảng **0 đến 1**. Điểm 0 nghĩa hai chuỗi có độ tương đồng 1 theo metric tương ứng, **không phải bảo đảm chúng có đúng cùng ký tự**.

### 14.1. Kiểm tra tính nhất quán score và distance

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS score,
    'keyboard' <-> 'keybord' AS distance,
    similarity('keyboard', 'keybord')
        + ('keyboard' <-> 'keybord') AS sum_to_one;
~~~

Về ý nghĩa, `score + distance = 1`; do kiểu `real` có làm tròn số floating-point, không dùng phép kiểm tra bằng chính xác từng bit như một business constraint.

### 14.2. Sắp xếp nearest neighbor

~~~sql
SELECT
    product_id,
    product_name,
    product_name <-> 'Ban phim co khong day'
        AS distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY
    product_name <-> 'Ban phim co khong day',
    product_id
LIMIT 10;
~~~

Truy vấn này yêu cầu **10 hàng có khoảng cách nhỏ nhất** trong tập active, không yêu cầu một threshold cố định. Nếu không có đường access hỗ trợ thứ tự distance, PostgreSQL có thể phải tính điểm trên nhiều hàng rồi sort.

### 14.3. Word-distance với thứ tự đối số

~~~sql
SELECT
    product_id,
    product_name,
    'bluetooh' <<-> product_name AS word_distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY 'bluetooh' <<-> product_name, product_id
LIMIT 10;
~~~

Để tìm đoạn trong tên sản phẩm gần term `bluetooh`, đặt term bên trái, candidate bên phải như `word_similarity`. Có thể dùng commutator `product_name <->> 'bluetooh'` nhưng phải giữ đúng ngữ nghĩa hướng.

### 14.4. Strict word-distance

~~~sql
SELECT
    product_id,
    product_name,
    'gaming' <<<-> product_name AS strict_distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY 'gaming' <<<-> product_name, product_id
LIMIT 10;
~~~

GiST có thể hỗ trợ nearest-neighbor ordering cho các distance operators phù hợp; GIN trigram index không có cùng khả năng **KNN index-order scan**.

## 15. Tại sao lọc bằng % và ORDER BY similarity thường đi cùng nhau?

Một thiết kế phổ biến:

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Hai công đoạn:

1. **Lọc ứng viên:** `product_name % 'keybord'` giữ những hàng trên ngưỡng.
2. **Xếp hạng:** `similarity` sắp ứng viên từ gần nhất đến xa hơn.

Một GIN/GiST trigram index có thể giúp giảm lượng hàng cần kiểm tra, nhưng `ORDER BY similarity(...) DESC` vẫn có thể cần **Sort**. Chỉ có index hỗ trợ operator filter không tự bảo đảm rows đã ra đúng thứ tự score.

### 15.1. Nếu chỉ cần top-K gần nhất

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE is_active
ORDER BY product_name <-> 'keybord'
LIMIT 10;
~~~

Với **GiST trigram index**, PostgreSQL có thể dùng KNN index scan giúp lấy nearest neighbors mà không phải sort toàn bộ bảng theo distance. Đây là một khác biệt then chốt khi lựa chọn GIN hay GiST.

### 15.2. Nếu muốn vừa threshold vừa top-K

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord'
ORDER BY product_name <-> 'keybord', product_id
LIMIT 10;
~~~

Hãy đọc plan xem index thực sự xử lý lọc/ngữ nghĩa thứ tự như kỳ vọng không; các predicate ngoài trigram như `is_active` cũng ảnh hưởng đến khả năng dừng sớm và số heap fetches.

### 15.3. Ties cần khóa phụ

Các sản phẩm có thể có distance bằng nhau. `ORDER BY distance, product_id` tạo thứ tự ổn định ở mức SQL. Thêm tie-break có thể khiến planner phải sắp xếp/hoàn thiện thứ tự ties ở một node khác; hãy ưu tiên tính đúng rồi đo chi phí.

## 16. So khớp không phân biệt chữ hoa/thường và tiếng Việt

`pg_trgm` mặc định có phép so sánh tương đồng **không phân biệt hoa/thường** trong bản build thông thường, nhưng chi tiết phụ thuộc môi trường/collation/build. Đừng suy ra **không phân biệt dấu tiếng Việt**.

~~~sql
SELECT
    similarity('Bluetooth', 'bluetooth') AS case_variant,
    similarity('ban phim', 'bàn phím') AS accent_variant,
    similarity('laptop', 'máy tính xách tay') AS synonym_variant;
~~~

Kết quả minh họa ba khía cạnh khác nhau:

- **Case**: chữ hoa/chữ thường;
- **Accent**: dấu tiếng Việt;
- **Synonym/meaning**: từ khác nhau nhưng cùng chỉ một loại sản phẩm.

Không có cơ chế duy nhất tự xử lý đúng cả ba trong `pg_trgm`.

### 16.1. Unicode normalization

Chuỗi hiển thị giống nhau có thể được biểu diễn bằng các dãy Unicode khác nhau, ví dụ một ký tự có dấu dựng sẵn so với ký tự cơ sở + dấu kết hợp. Để so khớp ổn định:

- Chọn chuẩn Unicode normalization (thường NFC) khi ingest/search;
- Tương thích giữa ứng dụng Java, PostgreSQL và index;
- Test các ký tự tiếng Việt có dấu ở cả hai dạng biểu diễn;
- Không tự xóa ký tự tùy tiện trong một lĩnh vực mà dấu có ý nghĩa pháp lý/định danh.

Trên PostgreSQL có hỗ trợ hàm `normalize(text, form)` trong encoding phù hợp, có thể nghiên cứu để chuẩn hóa Unicode; nhưng điều đó **không phải thao tác bỏ dấu**.

### 16.2. Accent-insensitive search là quyết định bổ sung

Để `"ban phim"` tìm `"bàn phím"` nhất quán, có thể thiết kế trường **`search_name`** đã được chuẩn hóa không dấu và case theo chính sách sản phẩm.

Ví dụ bản ghi:

~~~text
product_name: "Bàn phím cơ không dây"
search_name:  "ban phim co khong day"
~~~

Sau đó xây trigram index trên `search_name`, và normalize **cả query đầu vào** bằng cùng thuật toán/version.

### 16.3. Cẩn thận với extension unaccent

PostgreSQL có extension `unaccent` hỗ trợ loại bỏ dấu dựa trên rules/dictionary, nhưng **đừng vội tạo expression index trên `unaccent(product_name)`**. Các định nghĩa `unaccent` thông dụng không được đánh dấu IMMUTABLE vì phụ thuộc cấu hình/dictionary; expression index yêu cầu các hàm tham gia bất biến đúng nghĩa.

Một cách chắc chắn hơn khi rules có thể thay đổi là **lưu cột normalized value như dữ liệu được ứng dụng/ETL quản lý**, tái tính và rebuild index theo migration khi thay đổi rules. **Không tạo UDF wrapper khai báo `IMMUTABLE` sai chỉ để lách kiểm tra index**.

### 16.4. Chuẩn hóa quá mạnh có thể làm mất ý nghĩa

Việc bỏ dấu, bỏ dấu gạch nối, xóa whitespace hoặc chuyển các ký hiệu có thể gộp những mã/tên trước đây phân biệt được. Với tìm SKU/model, phải giữ kênh **exact matching** không phụ thuộc vào cột fuzzy normalized.

### 16.5. Gợi ý xử lý tiếng Việt

Một pipeline thường hợp lý:

~~~text
User query
    |
    +-- Trim / giới hạn độ dài / Unicode normalization
    |
    +-- Exact SKU or identifier search (ưu tiên nếu cú pháp phù hợp)
    |
    +-- Search tiếng Việt có dấu, LIKE/FTS/trigram
    |
    +-- Search trên cột không dấu đã được chuẩn hóa
    |
    +-- Combine, rerank, loại trùng, lọc active/tenant
    |
    +-- Hiển thị các ứng viên, không tự chọn thay user
~~~

Chỉ triển khai các bước thực sự cần, có benchmark và kiểm thử chất lượng tìm kiếm.

## 17. Trigram index là gì?

`pg_trgm` cung cấp hai **operator classes** dành cho index:

- `gin_trgm_ops` dùng với **GIN** (*Generalized Inverted Index*);
- `gist_trgm_ops` dùng với **GiST** (*Generalized Search Tree*).

Chúng cho phép planner sử dụng index để hỗ trợ các toán tử similarity, và cả một số truy vấn pattern matching như `LIKE`, `ILIKE`, `~`, `~*` và `=`. Tuy vậy, **index support không đảm bảo planner phải chọn index**: số hàng, độ chọn lọc, kích thước bảng, thống kê và cost vẫn quyết định.

### 17.1. GIN: truy từ trigram sang ứng viên

Có thể hình dung GIN như cấu trúc để từ các trigrams của từ tìm kiếm xác định **những hàng có chứa các trigrams ứng viên**. Sau đó PostgreSQL kiểm tra lại điều kiện cần thiết để trả kết quả chính xác theo operator.

~~~sql
CREATE INDEX idx_products_name_gin_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops);
~~~

Ví dụ:

~~~sql
SELECT
    product_id,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE product_name % 'keybord'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Với GIN index trên `product_name`, phần điều kiện `%` có thể tận dụng index để tìm candidates. `ORDER BY score DESC` vẫn có thể phải sort những candidates đó.

### 17.2. GiST: chữ ký trigrams và nearest-neighbor ordering

~~~sql
CREATE INDEX idx_products_name_gist_327
ON trgm_lab_327.products
USING gist (product_name gist_trgm_ops);
~~~

GiST trigram opclass biểu diễn các trigrams bằng **bitmap signature gần đúng**. Có thể xảy ra false positives trong quá trình truy cập index, nên executor cần **recheck** predicate trên dữ liệu thực.

GiST đặc biệt có giá trị cho:

~~~sql
SELECT
    product_id,
    product_name,
    product_name <-> 'keybord' AS distance
FROM trgm_lab_327.products
ORDER BY product_name <-> 'keybord'
LIMIT 10;
~~~

PostgreSQL có thể thực hiện **KNN GiST index scan** theo khoảng cách, tránh việc tính và sort toàn bộ bảng cho mọi query top-K trong những điều kiện thuận lợi.

### 17.3. Không hiểu GiST như một index luôn có kết quả chính xác sẵn

Signature là cấu trúc **xấp xỉ trong index**, không có nghĩa kết quả SQL được phép sai: index tìm ứng viên và PostgreSQL vẫn kiểm tra điều kiện/giá trị cần thiết khi thực thi.

### 17.4. GIN và GiST đều không thay B-tree cho exact equality phổ biến

~~~sql
SELECT product_id
FROM trgm_lab_327.products
WHERE sku = 'KB-001';
~~~

Index `UNIQUE` B-tree trên `sku` có lợi thế tự nhiên cho so sánh chính xác và ràng buộc uniqueness. Mặc dù trigram indexes có thể hỗ trợ `=` trên text, chúng thường **không hiệu quả bằng B-tree** cho equality đơn giản.

## 18. So sánh GIN và GiST cho pg_trgm

| Tiêu chí | GIN `gin_trgm_ops` | GiST `gist_trgm_ops` |
| --- | --- | --- |
| Mục tiêu chính | Lọc candidates theo trigrams/operators | Lọc candidates và tìm hàng gần nhất theo distance |
| `WHERE name % query` | Có index support | Có index support |
| `LIKE`/`ILIKE`/regex phù hợp | Có index support | Có index support |
| `ORDER BY name <-> query LIMIT K` | **Không** có hỗ trợ KNN index ordering tương tự GiST | **Có** khả năng KNN GiST |
| Cấu trúc | Inverted index | Signature tree |
| False-positive/recheck | Có thể cần recheck theo operator | Signature gần đúng có thể cần recheck |
| Dung lượng | Tùy dữ liệu và cấu hình | Tùy dữ liệu và `siglen` |
| Chi phí insert/update | Phụ thuộc pending list/maintenance và workload | Phụ thuộc cây GiST và workload |
| Khi dùng nhiều | Cần lọc substring/similarity trong tập lớn | Cần top-K nearest neighbors theo distance |

Không tồn tại kết luận “GIN luôn nhanh hơn GiST” hoặc ngược lại. Cần đo truy vấn thực tế, mức cập nhật, kích thước index, memory, số rows được trả và concurrency.

### 18.1. Không tạo cả hai trên production chỉ để chắc chắn

Hai chỉ mục trên cùng cột có thể tạo thêm:

- Dung lượng đĩa;
- WAL và ghi đĩa mỗi lần INSERT/UPDATE;
- Công việc VACUUM/maintenance;
- Khóa hoặc ảnh hưởng vận hành khi build;
- Chi phí lưu trong cache.

Trong lab có thể tạo cả hai để quan sát; trên production nên chọn dựa trên query families và benchmark.

### 18.2. GiST siglen tùy chỉnh

~~~sql
CREATE INDEX idx_products_name_gist32_327
ON trgm_lab_327.products
USING gist (
    product_name gist_trgm_ops(siglen=32)
);
~~~

Theo tài liệu PostgreSQL hiện hành, chữ ký mặc định **12 bytes**, và `siglen` có thể tăng trong phạm vi opclass hỗ trợ (ví dụ 32 bytes). Chữ ký dài hơn thường **giảm mức false-positive và heap access** khi tìm kiếm, đổi lại **index lớn hơn**.

**Không chồng nhiều GiST index với các `siglen` khác nhau trên cùng bảng production** nếu chưa đo chi phí và không có mục tiêu rõ ràng. Có thể dùng một bảng lab/benchmark riêng để so.

### 18.3. Lọc nhiều vs lấy top-K

Thí nghiệm thiết kế:

~~~sql
-- Candidate filtering:
SELECT product_id
FROM trgm_lab_327.products
WHERE product_name % 'keybord';

-- Nearest neighbors:
SELECT product_id
FROM trgm_lab_327.products
ORDER BY product_name <-> 'keybord'
LIMIT 5;
~~~

Hai query có **ngữ nghĩa kết quả khác nhau**:

- Query thứ nhất trả tất cả những hàng vượt threshold hiện tại;
- Query thứ hai luôn cố trả tối đa 5 hàng gần nhất, kể cả chúng có điểm thấp nếu dữ liệu không có ứng viên tốt.

Với autocomplete gợi ý chính tả, cần quyết định có áp ngưỡng tối thiểu để tránh gợi ý vô nghĩa hay không.

## 19. GiST KNN: ORDER BY distance LIMIT

Đây là một use case quan trọng của GiST:

~~~sql
EXPLAIN
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
ORDER BY product_name <-> 'bluetooh'
LIMIT 5;
~~~

Nếu planner dùng GiST KNN index, một dạng plan minh họa:

~~~text
Limit
  -> Index Scan using idx_products_name_gist_327 on products
       Order By: (product_name <-> 'bluetooh'::text)
~~~

Đây là **plan mẫu**, không phải output được cam kết trên bảng 20 hàng. Với bảng rất nhỏ, Seq Scan + Sort có thể rẻ hơn.

### 19.1. Vì sao ORDER BY distance khác ORDER BY score?

~~~sql
ORDER BY product_name <-> 'bluetooh'
~~~

được xây bằng distance operator mà GiST opclass hỗ trợ. Còn:

~~~sql
ORDER BY similarity(product_name, 'bluetooh') DESC
~~~

có cùng mục tiêu ranking chung nhưng không phải hình thức **KNN index-order operator** thông thường. Với GiST cần top-K, viết `ORDER BY indexed_column <-> query` theo hướng operator được hỗ trợ.

### 19.2. Top-K theo word similarity

~~~sql
SELECT
    product_id,
    product_name,
    'bluetooh' <<-> product_name AS distance
FROM trgm_lab_327.products
WHERE is_active
ORDER BY 'bluetooh' <<-> product_name
LIMIT 5;
~~~

Query này yêu cầu tìm một đoạn liên tục trong tên sản phẩm gần `bluetooh`. Theo tài liệu `pg_trgm`, các word/strict-word distance operators cũng có đường hỗ trợ KNN qua GiST. Thứ tự đối số **không được đảo tùy tiện**.

### 19.3. Tie-break và KNN

~~~sql
SELECT
    product_id,
    product_name,
    product_name <-> 'bluetooh' AS distance
FROM trgm_lab_327.products
ORDER BY product_name <-> 'bluetooh', product_id
LIMIT 5;
~~~

Thêm `product_id` làm tie-break đảm bảo kết quả được sắp ổn định theo SQL. Planner có thể phải thêm một bước xử lý thứ tự phụ; **giữ kết quả đúng trước rồi xem `EXPLAIN` để đánh giá hiệu năng**.

### 19.4. KNN không thay business filters

Nếu chỉ bán những sản phẩm active của tenant hiện tại, vẫn phải đặt:

~~~sql
WHERE is_active
  AND tenant_id = $1
~~~

theo schema thực tế. **Không lấy top-K toàn database rồi mới loại tenant phía ứng dụng**, vì có thể lộ dữ liệu và làm kết quả sau lọc không còn top-K của tập được phép.

## 20. LIKE và ILIKE với trigram index

`pg_trgm` không chỉ làm fuzzy similarity; GIN/GiST trigram opclasses có thể hỗ trợ **pattern matching** kể cả khi wildcard nằm đầu chuỗi.

### 20.1. Tìm substring bằng ILIKE

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ILIKE '%keyboard%'
ORDER BY product_id;
~~~

Một B-tree thông thường không tối ưu tốt mọi `ILIKE '%...%'` với leading wildcard; trigram index có thể trích các trigram từ phần cố định của pattern và tìm ứng viên hiệu quả hơn.

### 20.2. Không cần prefix anchor như B-tree

~~~sql
-- Chứa cụm ở giữa tên:
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ILIKE '%gaming%'
ORDER BY product_id;
~~~

Khi pattern có đủ trigrams hữu ích, planner có thể dùng GIN/GiST index ngay cả khi có `%` trước và sau text.

### 20.3. LIKE không sửa được typo

~~~sql
WHERE product_name ILIKE '%bluetooh%'
~~~

chỉ match tên có chuỗi `bluetooh` như được viết, **không tự gợi ý `bluetooth`**. Nếu muốn chịu lỗi gõ, sử dụng `%`, `<%`, `<<%` hoặc KNN distance.

### 20.4. ILIKE phụ thuộc kiểu/collation

Với tên tiếng Việt, `ILIKE` và quy tắc casefold có thể phụ thuộc collation/provider, và một số kiểu collation có giới hạn đối với pattern operators. Trước khi triển khai production, kiểm tra collation cột, PostgreSQL version và trường hợp Unicode cụ thể.

### 20.5. Pattern quá ngắn

~~~sql
SELECT product_id
FROM trgm_lab_327.products
WHERE product_name ILIKE '%a%';
~~~

Với pattern có rất ít hoặc **không rút được trigram hữu ích**, tìm kiếm qua trigram index có thể suy biến thành một **full-index scan** hoặc planner chọn Seq Scan. Chỉ nhìn thấy index tồn tại không đảm bảo tăng tốc.

Một policy hợp lý là:

- Đầu vào 0 ký tự: không làm fuzzy search toàn danh mục;
- Đầu vào 1–2 ký tự: ưu tiên prefix search/autocomplete đã giới hạn;
- Đầu vào đủ dài: bật trigram filter/word similarity;
- Đầu vào cực dài: giới hạn kích thước và chọn cách search phù hợp.

Ngưỡng độ dài là quyết định ứng dụng, không phải quy tắc rằng **mọi search dưới 3 ký tự luôn không thể dùng index**: padding/pattern và operator có thể tạo các trường hợp khác nhau. Nhưng với những pattern không chứa trigram trích xuất được, index search không hữu ích.

### 20.6. LIKE metacharacters từ người dùng

Bind parameter **chống SQL injection**, nhưng không tự biến các ký tự `%` và `_` thành ký tự literal trong mẫu LIKE.

Ví dụ query từ người dùng `"50%"`, nếu được nối thành `ILIKE '%50%%'`, dấu % do người dùng nhập cũng là wildcard. Nếu cần tìm **đúng dấu phần trăm**, phải escape ký tự wildcard theo quy tắc LIKE, đặt `ESCAPE` phù hợp và kiểm thử backslash/Unicode.

Với fuzzy `%` operator, input là **text để tính similarity**, không phải một LIKE pattern, nên hai luồng search nên có xử lý input riêng.

## 21. Regex ~ và ~* qua trigram index

`pg_trgm` còn có thể giúp những regex queries khi PostgreSQL rút ra được các trigrams cố định:

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ~* '(keyboard|bluetooth)'
ORDER BY product_id;
~~~

Toán tử:

| Toán tử | Ý nghĩa |
| --- | --- |
| `~` | Match regular expression, có phân biệt hoa/thường theo ngữ nghĩa phù hợp |
| `~*` | Match regular expression, không phân biệt hoa/thường |

### 21.1. Index support không có nghĩa mọi regex được tăng tốc

Một regex quá tổng quát như `'.*'`, pattern chỉ một vài ký tự, hoặc dạng không trích được trigrams cần thiết có thể buộc PostgreSQL đọc phần lớn index/bảng để xác định match.

### 21.2. Regex từ input không tin cậy

Không cho người dùng tùy ý nhập regex rồi thực thi không giới hạn trên tập dữ liệu lớn:

- Pattern quá phức tạp có thể rất tốn CPU;
- Người dùng có thể tạo truy vấn gây từ chối dịch vụ;
- Kết quả có thể tiết lộ những chuỗi mà user không được phép tìm;
- Không nên lạm dụng regex cho bài toán simple substring/fuzzy.

Giới hạn độ dài, thời gian thực thi, quyền dữ liệu; ưu tiên bound parameters và chính sách cho những dạng pattern được phép.

## 22. Partial trigram index trên dữ liệu active

Nếu ứng dụng chỉ tìm sản phẩm đang bán, có thể cân nhắc **partial trigram index**:

~~~sql
CREATE INDEX idx_products_active_name_gin_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops)
WHERE is_active;
~~~

Truy vấn có điều kiện:

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord';
~~~

Planner có thể sử dụng partial index khi chứng minh được query predicate **hàm ý `is_active`** và cost phù hợp.

### 22.1. Khi nào partial index giúp?

Nếu chỉ 20% catalog active, partial index có thể nhỏ hơn index toàn bảng đáng kể. Nếu 99% active, lợi ích giảm dung lượng có thể thấp; đổi lại vẫn phải bảo trì index khi trạng thái active hoặc name đổi.

### 22.2. Generic plan với tham số điều kiện active

Nếu query có `is_active = $1` trong một generic plan, planner không luôn biết `$1` bằng true lúc chọn plan. Partial predicate `WHERE is_active` có thể khó được suy luận cho mọi trường hợp tham số. **Đo generic/custom prepared plans** khi query dùng partial index và tham số bind.

### 22.3. Đừng loại hàng active ở ứng dụng sau khi LIMIT

~~~text
Sai:
  top 10 gần nhất trong toàn catalog
  → phía Java loại sản phẩm inactive
  → có thể còn 1–2 kết quả và lộ dữ liệu không được phép.

Đúng:
  SQL WHERE is_active / tenant_id / visibility
  → tìm và xếp hạng trên tập được phép
  → LIMIT 10
~~~

Điều kiện nghiệp vụ/quyền truy cập phải nằm trong truy vấn dữ liệu đúng cấp.

## 23. Index trên biểu thức chuẩn hóa

Giả sử ứng dụng lưu:

~~~sql
ALTER TABLE trgm_lab_327.products
ADD COLUMN search_name TEXT;
~~~

Sau đó ứng dụng/ETL có thể điền bản chuẩn hóa không dấu theo chính sách đã duyệt. **SQL minh họa gán một số record trong lab**:

~~~sql
UPDATE trgm_lab_327.products
SET search_name = CASE product_id
    WHEN 1 THEN 'ban phim co khong day'
    WHEN 2 THEN 'ban phim co co day'
    WHEN 3 THEN 'ban phim van phong'
    WHEN 17 THEN 'ban phim co khong day'
    WHEN 18 THEN 'ban phim co khong day mini'
    ELSE lower(product_name)
END;
~~~

Đây **không phải một pipeline bỏ dấu hoàn chỉnh**: chỉ một số record được gán thủ công để minh họa. Production phải có một bộ chuẩn hóa nhất quán cho **mọi** hàng và input, có quản lý version/rules.

### 23.1. Index trên cột normalized

~~~sql
CREATE INDEX idx_products_search_name_gin_327
ON trgm_lab_327.products
USING gin (search_name gin_trgm_ops);
~~~

~~~sql
SELECT
    product_id,
    product_name,
    similarity(search_name, 'ban phim co') AS score
FROM trgm_lab_327.products
WHERE search_name % 'ban phim co'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Ứng dụng có thể hiển thị `product_name` gốc có dấu, còn `search_name` chỉ dùng cho tìm kiếm. Việc chuẩn hóa input `'ban phim co'` phải cùng quy tắc với cột.

### 23.2. Index trên lower(product_name)

Với quy tắc chỉ đổi thành chữ thường ổn định:

~~~sql
CREATE INDEX idx_products_lower_name_gin_327
ON trgm_lab_327.products
USING gin (lower(product_name) gin_trgm_ops);
~~~

Query tương ứng:

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE lower(product_name) % lower('Bluetooth')
ORDER BY product_id;
~~~

Không mặc định index trên `lower(product_name)` sẽ được planner dùng cho `product_name % 'Bluetooth'`: **đây là biểu thức index khác**. Mặc định trigram comparison đã có tính không phân biệt case ở nhiều bản build, nên thêm `lower` có thể dư thừa; dùng khi có yêu cầu chuẩn hóa nhất quán rõ ràng.

### 23.3. Cột normalized phải được duy trì đúng

Nếu rename sản phẩm mà không update `search_name`, tìm kiếm theo cột normalized sẽ dùng dữ liệu stale. Cần:

- Application write-path luôn cập nhật cùng transaction;
- Hoặc trigger/generated mechanism nếu đúng điều kiện immutability;
- Job kiểm tra độ lệch và backfill;
- Migration/reindex khi đổi thuật toán chuẩn hóa;
- Test Unicode/accent/đặc điểm mã SKU.

### 23.4. Không nhầm normalization với business semantics

Đổi `"Cáp USB-C 1m"` thành `"cap usb c 1m"` không có nghĩa có thể bỏ khác biệt giữa `1m` và `2m`. Cần giữ cấu trúc đặc tính sản phẩm như độ dài, dung lượng, mã model để rerank/filter chính xác.

## 24. Tạo index online và công việc bảo trì

Trên bảng lớn có ghi liên tục, lệnh `CREATE INDEX` thông thường có thể chặn những hoạt động ghi trong giai đoạn build. PostgreSQL hỗ trợ:

~~~sql
CREATE INDEX CONCURRENTLY idx_products_name_gin_online_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops);
~~~

**Chỉ triển khai nếu cần, có quyền và đã đánh giá workload.** `CREATE INDEX CONCURRENTLY` giảm chặn ghi kéo dài nhưng có thể tốn nhiều thời gian, I/O/CPU và có các pha chờ transactions.

### 24.1. Không chạy trong explicit transaction block

~~~sql
-- Không hợp lệ:
-- BEGIN;
-- CREATE INDEX CONCURRENTLY ...
-- COMMIT;
~~~

### 24.2. Có thể để lại invalid index nếu thất bại

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
    ON c.oid = i.indrelid
WHERE c.oid = 'trgm_lab_327.products'::regclass
ORDER BY index_name;
~~~

Nếu concurrent build thất bại, đừng giả định không còn gì. Cần đọc log/lỗi, kiểm tra invalid index và có kế hoạch drop/rebuild an toàn phù hợp phiên bản.

### 24.3. Tác động của nhiều index

Mỗi INSERT/UPDATE tên sản phẩm có thể phải cập nhật B-tree và mọi GIN/GiST trên cùng cột. Với danh mục ít sửa và đọc nhiều, đây có thể là trade-off tốt. Với stream log cập nhật hàng trăm nghìn events mỗi giây, nhiều trigram indexes có thể gây write amplification đáng kể.

### 24.4. GIN pending list và VACUUM

GIN có cơ chế **fastupdate** và pending list giúp cải thiện một số write workloads, nhưng pending list cũng cần được hợp nhất/bảo trì. Khi truy vấn đột nhiên chậm hoặc writes bị spike, xem autovacuum, pending-list behavior và cài đặt GIN theo tài liệu PostgreSQL hiện hành trước khi thay bừa một tham số toàn server.

### 24.5. GiST siglen/false positives

Nếu GiST signature dẫn tới nhiều rows cần recheck, tăng `siglen` trên index mới (có benchmark) có thể giảm số candidate false positives nhưng tăng index size. Không quy toàn bộ `Rows Removed by Index Recheck` cho một lỗi dữ liệu.

## 25. EXPLAIN: tìm xem index thực sự có được dùng

~~~sql
ANALYZE trgm_lab_327.products;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
WHERE product_name % 'keybord';
~~~

Một kế hoạch minh họa nếu dùng GIN:

~~~text
Bitmap Heap Scan on products
  Recheck Cond: (product_name % 'keybord'::text)
  -> Bitmap Index Scan on idx_products_name_gin_327
       Index Cond: (product_name % 'keybord'::text)
~~~

Nếu chọn GiST, cũng có thể thấy `Bitmap Index Scan`/`Index Scan` với những thuộc tính khác nhau. Trên 20 hàng, PostgreSQL nhiều khả năng chỉ dùng `Seq Scan` vì chi phí đọc toàn bảng rất thấp.

### 25.1. Bitmap recheck

GIN/GiST index hỗ trợ tìm những ứng viên thỏa toán tử, nhưng executor có thể cần **kiểm tra lại điều kiện** trên heap. Trong `EXPLAIN ANALYZE`, đọc:

- `Recheck Cond`;
- `Rows Removed by Index Recheck` khi có;
- `Heap Blocks: exact=... lossy=...`;
- `Buffers: shared hit/read`;
- `actual rows`, `loops` và thời gian.

### 25.2. KNN GiST plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
ORDER BY product_name <-> 'keybord'
LIMIT 10;
~~~

Nếu thấy:

~~~text
Index Scan using idx_products_name_gist_327 on products
  Order By: (product_name <-> 'keybord'::text)
~~~

đó là dấu hiệu GiST index cung cấp thứ tự khoảng cách. Nếu thấy `Seq Scan -> Sort -> Limit` trên bảng vài chục hàng, điều đó không tự chứng minh GiST không hỗ trợ KNN.

### 25.3. Chỉ số cost không phải milliseconds

~~~text
cost=100.00..500.00
actual time=1.234..12.345
~~~

`cost` là ước lượng tương đối của planner; `actual time` là số đo runtime trong một lượt EXPLAIN ANALYZE, tính theo milliseconds. So sánh nhiều lần và ghi môi trường cache/concurrency trước khi kết luận.

### 25.4. EXPLAIN ANALYZE thực thi SQL

`EXPLAIN (ANALYZE)` **thực thi câu SQL**, không chỉ in plan. Trên SELECT lab không có side effect thì tương đối an toàn, nhưng tránh áp trực tiếp vào `UPDATE`/`DELETE` trên production vì chúng sẽ ghi dữ liệu thật.

## 26. Tạo dữ liệu benchmark lớn hơn (tùy chọn)

Với 20 hàng, planner không có lý do rõ để dùng index. Nếu máy lab đủ RAM/đĩa và bạn muốn quan sát khác biệt, có thể tạo một bảng benchmark **100.000 hàng** riêng thay vì làm phình bảng demo:

~~~sql
CREATE TABLE trgm_lab_327.large_products AS
SELECT
    g::bigint AS product_id,
    p.product_name || ' ref ' || g::text AS product_name,
    p.category,
    p.is_active
FROM generate_series(1, 100000) AS gs(g)
JOIN trgm_lab_327.products AS p
    ON p.product_id = ((g - 1) % 20 + 1);

ANALYZE trgm_lab_327.large_products;

CREATE INDEX idx_large_products_gin_327
ON trgm_lab_327.large_products
USING gin (product_name gin_trgm_ops);

CREATE INDEX idx_large_products_gist_327
ON trgm_lab_327.large_products
USING gist (product_name gist_trgm_ops);
~~~

**Không bắt buộc chạy nếu môi trường hạn chế tài nguyên**. Tạo dữ liệu và index có thể tiêu tốn WAL, RAM và đĩa. Dữ liệu tổng hợp lặp tên sản phẩm cộng `ref` không phản ánh mọi phân bố thực tế; đây chỉ là bảng làm quen với khả năng planner dùng index.

### 26.1. Lọc kiểu GIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.large_products
WHERE product_name ILIKE '%mechanical%';
~~~

### 26.2. Lọc theo %

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.large_products
WHERE product_name % 'bluetooh';
~~~

### 26.3. GiST top-K

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.large_products
ORDER BY product_name <-> 'bluetooh'
LIMIT 10;
~~~

### 26.4. Vì sao thứ tự chạy và cache ảnh hưởng kết quả?

Nếu bạn benchmark GIN trước rồi GiST, các heap/index blocks có thể đã vào shared buffers/OS cache. Hãy chạy nhiều lượt, xen kẽ phép thử, xem shared hits/reads và quan sát CPU/đĩa. Không lấy một lần nhanh hơn vài milliseconds làm kết luận GIN/GiST tốt hơn ở mọi workload.

### 26.5. Không ép planner để “thấy đúng index”

Các `enable_*` planner switches có thể dùng chẩn đoán trong `SET LOCAL`, nhưng **không nên tắt Seq Scan toàn server** chỉ để plan trông đúng kỳ vọng. Nếu scan toàn bảng thực sự rẻ hơn do selectivity thấp, planner chọn nó có thể là đúng.

## 27. Kết hợp pg_trgm với Full-Text Search

**Full-text search** của PostgreSQL và **trigram similarity** giải những bài toán khác nhau:

| Thuộc tính | Full-text search | Trigram similarity |
| --- | --- | --- |
| Đơn vị biểu diễn chính | Token/lexeme, từ điển, stop words/stemming tùy config | Những cụm ba ký tự |
| Truy vấn phù hợp | Nhiều từ khóa, tài liệu dài, ranking theo từ vựng | Lỗi gõ, tên gần giống, substring/partial word |
| `laptop` vs `máy tính xách tay` | Cũng cần synonyms/thông số ngôn ngữ nếu muốn hiểu tương đương | Không tự hiểu nghĩa |
| Gõ nhầm `bluetooh` | Có thể không khớp lexeme `bluetooth` | Có thể gợi ý chính tả gần `bluetooth` |
| Index | Thường GIN trên `tsvector` | GIN/GiST với `gin_trgm_ops`/`gist_trgm_ops` |

### 27.1. Một câu full-text search cơ bản

~~~sql
SELECT
    product_id,
    product_name
FROM trgm_lab_327.products
WHERE to_tsvector(
    'simple',
    product_name || ' ' || description
) @@ plainto_tsquery('simple', 'mechanical keyboard')
ORDER BY product_id;
~~~

`simple` là cấu hình tách lexeme đơn giản, không tự dịch `"bàn phím"` thành `"keyboard"`. Tùy yêu cầu, ứng dụng có thể có cấu hình từ điển/synonym riêng.

### 27.2. Trigram hỗ trợ sửa chính tả trước/sau FTS

Một workflow có thể là:

1. Chạy exact/prefix/FTS cho query người dùng;
2. Nếu ít kết quả, truy xuất **các gợi ý từ gần đúng** từ từ điển từ khóa;
3. Hiển thị `"Có phải bạn muốn tìm bluetooth?"`;
4. Để user xác nhận/nhấn vào gợi ý hoặc kết hợp rerank có kiểm soát;
5. Không tự sửa keyword có thể là tên người, mã model hoặc mã thuốc.

### 27.3. Tạo từ điển thuật ngữ phụ trợ

Theo hướng dẫn PostgreSQL, một bảng chứa các từ riêng có thể được trích từ text search documents. Ví dụ trên lab:

~~~sql
CREATE TABLE trgm_lab_327.search_words AS
SELECT word
FROM ts_stat(
    'SELECT to_tsvector(''simple'', description)
     FROM trgm_lab_327.products'
);

CREATE UNIQUE INDEX idx_search_words_exact_327
ON trgm_lab_327.search_words (word);

CREATE INDEX idx_search_words_trgm_327
ON trgm_lab_327.search_words
USING gin (word gin_trgm_ops);
~~~

`ts_stat` thu thập word statistics từ kết quả tsvector; dữ liệu từ điển phụ trợ này có thể không tự phản ánh những từ mới khi danh mục thay đổi. Cần **refresh/update process** nếu áp dụng production. Trong lab trên, nó chỉ dùng dữ liệu `description` tại thời điểm tạo bảng.

### 27.4. Gợi ý spelling từ bảng từ vựng

~~~sql
SELECT
    word,
    similarity(word, 'bluetooh') AS score
FROM trgm_lab_327.search_words
WHERE word % 'bluetooh'
ORDER BY score DESC, word
LIMIT 5;
~~~

Nếu `bluetooth` xuất hiện trong descriptions, nó có thể là một candidate. Bộ từ vựng nào được đưa vào dictionary sẽ ảnh hưởng chất lượng gợi ý; chỉ index những từ trong `description` có thể bỏ lỡ brand/model chỉ xuất hiện ở `product_name`.

### 27.5. Cẩn thận tokenization tiếng Việt

`simple` tách token theo parser mặc định, không tự bảo đảm **phân đoạn từ tiếng Việt đa âm tiết** đúng ngữ nghĩa. Một cụm như `"máy tính xách tay"` có nhiều đơn vị từ theo cách viết có dấu cách; search theo ngữ nghĩa cần từ điển/tiền xử lý phù hợp.

### 27.6. Không ghép SQL động từ input trong ts_stat

`ts_stat` nhận một **câu query dạng text** để đọc tsvector. Chỉ dùng SQL constant/nguồn trusted được kiểm soát; không nối input người dùng thành câu SQL đưa vào `ts_stat`. Trong ứng dụng, `ts_stat` là công cụ xây dictionary/analysis, **không phải API trực tiếp cho mỗi request người dùng**.

## 28. Pipeline tìm kiếm sản phẩm thực tế

Một luồng tìm kiếm tốt thường ưu tiên **đúng nghiệp vụ** trước khi áp dụng fuzzy matching:

~~~mermaid
flowchart TD
    Q["Người dùng nhập query"] --> V["Validate độ dài / Unicode / quyền"]
    V --> E{"Nhận diện query là SKU/mã?"}
    E -->|Có| X["Exact match bằng B-tree"]
    E -->|Không| P["Prefix / substring / FTS"]
    X --> R["Tập ứng viên được phép xem"]
    P --> F{"Đủ kết quả liên quan?"}
    F -->|Có| R
    F -->|Không| T["Fuzzy pg_trgm / word similarity"]
    T --> R
    R --> C["Rerank / lọc business attributes"]
    C --> L["LIMIT, thứ tự ổn định, UI gợi ý"]
~~~

### 28.1. Exact SKU phải có ưu tiên riêng

~~~sql
SELECT
    product_id,
    sku,
    product_name
FROM trgm_lab_327.products
WHERE is_active
  AND sku = 'KB-001';
~~~

Nếu query là SKU đã tồn tại, kết quả chính xác phải được ưu tiên. Không dùng `sku % 'KB-001'` để xác định SKU nào người dùng có quyền mua.

### 28.2. Fuzzy search giới hạn category

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    similarity(product_name, 'keybord') AS score
FROM trgm_lab_327.products
WHERE is_active
  AND category = 'keyboard'
  AND product_name % 'keybord'
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Filter `category` phản ánh sự lựa chọn người dùng/luồng sản phẩm, không phải một thay đổi ranking thuần túy. Nếu category từ người dùng, dùng bound parameter.

### 28.3. Kết hợp chính xác và fuzzy trong một API

Một ứng dụng có thể chạy hai query có mục tiêu rõ ràng:

- Query **exact SKU**: tối đa một kết quả, độ chính xác cao.
- Query **fuzzy names**: một shortlist có score, threshold, LIMIT.

Sau đó ứng dụng gộp theo **product_id**, ưu tiên exact và hiển thị fuzzy suggestions có nhãn. Đừng chọn một kết quả fuzzy rồi âm thầm thay mã hàng trong đơn đặt mua.

### 28.4. Rerank theo thuộc tính sản phẩm

Tên gần giống nhưng khác thông số sản phẩm có thể cần điều kiện/điểm phụ:

- Kích thước, dung lượng, màu sắc, đời model;
- Hãng/brand, tình trạng hàng;
- Mã sản phẩm chính xác;
- Ngôn ngữ và cách viết tên;
- Mức độ liên quan theo category.

Ví dụ `"Cáp USB-C 1m"` và `"Cáp USB-C 2m"` có thể có trigram score rất gần nhau. Nếu user đã chọn `length_m=2`, cần lọc/rerank theo độ dài như **thuộc tính có kiểu**, không để một sai khác chữ số bị che bởi similarity.

### 28.5. Nhiều ngôn ngữ

Nếu có tên tiếng Việt/Anh, có thể lưu các alias/synonyms trong một bảng quan hệ con thay vì nối mọi tên thành một chuỗi dài. Mỗi alias có ngôn ngữ, loại, version, search text; mỗi kết quả tìm được liên kết trở lại product_id.

**Fuzzy trên alias** tìm ra cách viết thay thế; **exact constraint trên product_id/SKU** vẫn bảo vệ danh tính sản phẩm.

## 29. Tìm trùng lặp gần đúng (*near-duplicate detection*)

Một tác vụ khác là hỗ trợ quản trị viên phát hiện tên sản phẩm gần giống hoặc có thể bị nhập hai lần:

~~~sql
SELECT
    a.product_id AS left_id,
    a.product_name AS left_name,
    b.product_id AS right_id,
    b.product_name AS right_name,
    similarity(a.product_name, b.product_name) AS score
FROM trgm_lab_327.products AS a
JOIN trgm_lab_327.products AS b
    ON a.product_id < b.product_id
   AND a.category = b.category
   AND a.product_name % b.product_name
ORDER BY score DESC, left_id, right_id
LIMIT 50;
~~~

### 29.1. Vì sao `a.product_id < b.product_id`?

Điều kiện này tránh:

- Ghép một sản phẩm với chính nó;
- Lặp lại cả cặp `(A,B)` và `(B,A)`.

Nhưng nó **không chứng minh hai records là duplicate**. Quản trị viên vẫn cần so mã model, brand, thông số và lịch sử.

### 29.2. Chi phí self-join

Với `N` sản phẩm, số cặp có thể tới khoảng `N(N-1)/2` nếu không có lọc hiệu quả. Trên bảng hàng triệu rows, không chạy self-join fuzzy toàn bộ mà thiếu chiến lược chặn (*blocking*) theo category/brand/những dấu hiệu khác.

Một cách tổ chức:

1. Chia tập theo category/brand/khóa blocking;
2. Chỉ so cặp trong vùng có khả năng trùng;
3. Dùng index hỗ trợ tìm ứng viên;
4. Giới hạn batch/statement timeout phù hợp;
5. Lưu candidate pairs và trạng thái review;
6. Không tự merge hai thực thể chỉ vì score cao.

### 29.3. Khi nào không dùng pg_trgm cho dedup?

Khi dữ liệu chứa mã định danh chính xác, địa chỉ chuẩn hóa, email, số điện thoại hoặc pháp nhân, cần mô hình đối chiếu dữ liệu khác và quy trình kiểm chứng. Tương đồng ký tự không thay thế xác thực quyền sở hữu/identity.

## 30. Đánh giá kết quả bằng precision, recall và ranking

Tối ưu fuzzy search có **hai chiều độc lập**:

1. **Độ liên quan** của những ứng viên được trả.
2. **Hiệu năng** tìm và xếp hạng các ứng viên đó.

Không thể gọi giải pháp “tốt” nếu query chạy 10 ms nhưng trả những sản phẩm sai với nhu cầu người dùng.

### 30.1. Precision@K

Giả sử 10 kết quả đầu có 7 sản phẩm được chuyên gia gắn nhãn là relevant:

\[
\mathrm{Precision@10} = \frac{7}{10}=0.7
\]

Đây là tỷ lệ kết quả liên quan trong 10 vị trí đầu, **không phải độ tin cậy do similarity score trả ra**.

### 30.2. Recall@K

Giả sử tập được gắn nhãn có 14 sản phẩm relevant, và top 10 tìm được 7 sản phẩm:

\[
\mathrm{Recall@10}=\frac{7}{14}=0.5
\]

Khi tăng threshold, có thể cải thiện precision bằng cách loại bớt false positives nhưng lại mất các kết quả relevant có score thấp, khiến recall giảm. Đây là **trade-off** cần định lượng.

### 30.3. Bộ query đánh giá

Nên có bộ truy vấn đại diện:

| Loại query | Ví dụ | Điều cần đo |
| --- | --- | --- |
| Đúng chính tả | `keyboard` | Exact/near matches phải xếp tốt |
| Một lỗi gõ | `keybord` | Có gợi ý keyboard không |
| Nhiều lỗi gõ | `bluetooh` | Có false positives nhiều không |
| Tiếng Việt có dấu | `bàn phím` | Có phân biệt đúng tên/sản phẩm |
| Không dấu | `ban phim` | Có cần normalized column không |
| Từ giữa tên dài | `mechanical` | Word similarity phù hợp không |
| Query rất ngắn | `ph` | Có cần giới hạn/prefix fallback |
| Mã sản phẩm | `KB-001` | Exact SKU được ưu tiên |
| SKU có dấu câu | `USB-C` | Không để tokenizer làm mất mã |
| Sản phẩm giống tên khác cấu hình | `USB-C 2m` | Có chọn đúng độ dài không |
| Alias/đồng nghĩa | `laptop` vs `máy tính xách tay` | Không trông đợi trigram tự dịch |
| Nhiều ký tự đặc biệt | `C++`, `50%` | Escape/pattern semantics |

### 30.4. Độ đo ranking khác

Với kết quả có mức liên quan khác nhau (rất đúng, đúng một phần, không đúng), có thể dùng **MRR**, **MAP**, **nDCG@K** hoặc tiêu chí click/convert được thiết kế phù hợp. Không cần triển khai mọi metric nếu sản phẩm chỉ cần “did-you-mean” đơn giản, nhưng ít nhất phải đo **top-K relevance và false-positive rate**.

### 30.5. Threshold không ổn định giữa mọi trường dữ liệu

Ngưỡng 0.4 với tên tiếng Anh dài có thể có hành vi khác ngưỡng 0.4 cho tên tiếng Việt ngắn. Khi sản phẩm có nhiều ngôn ngữ/cột/kiểu query, có thể cần threshold được **calibrate riêng theo nhóm trường/độ dài/ngữ cảnh**, không sử dụng một hằng số như chuẩn phổ quát.

### 30.6. Benchmark latency

Đo:

- p50/p95/p99 latency;
- Số candidates trước và sau filter;
- Total buffer hits/reads và temp I/O;
- Index size/maintenance cost;
- Concurrency, CPU và memory;
- Tỷ lệ query dùng GIN/GiST/Seq Scan;
- Tỷ lệ search trả 0 kết quả hoặc quá nhiều kết quả;
- Precision/recall@K.

Một threshold quá thấp có thể tăng CPU/sort cost và giảm precision; một threshold quá cao có thể loại các từ gõ sai mà người dùng thực sự muốn tìm.

## 31. Java/JDBC: fuzzy search có tham số

Đối với ứng dụng Java, nên gửi search term qua **`PreparedStatement`**, không nối trực tiếp vào SQL.

### 31.1. API mẫu với toán tử %

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public class ProductFuzzySearch {
    public record Candidate(
            long productId,
            String sku,
            String productName,
            double similarity) {}

    public static List<Candidate> search(
            Connection connection,
            String query,
            int requestedLimit) throws SQLException {

        if (query == null || query.isBlank()) {
            return List.of();
        }

        String normalizedInput = query.strip();
        if (normalizedInput.length() < 3
                || normalizedInput.length() > 100) {
            return List.of(); // Chính sách lab: search 3..100 ký tự.
        }

        int limit = Math.max(1, Math.min(requestedLimit, 20));
        String sql = """
            SELECT
                product_id,
                sku,
                product_name,
                similarity(product_name, ?) AS score
            FROM trgm_lab_327.products
            WHERE is_active
              AND product_name % ?
            ORDER BY score DESC, product_id
            LIMIT ?
            """;

        List<Candidate> results = new ArrayList<>();
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setString(1, normalizedInput);
            ps.setString(2, normalizedInput);
            ps.setInt(3, limit);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    results.add(new Candidate(
                            rs.getLong("product_id"),
                            rs.getString("sku"),
                            rs.getString("product_name"),
                            rs.getDouble("score")));
                }
            }
        }
        return results;
    }
}
~~~

Ví dụ dùng Java **record** và text blocks (cần phiên bản Java phù hợp, ví dụ Java 17+). Nếu dự án dùng Java thấp hơn, thay record/text block bằng class/string tương ứng.

### 31.2. Vì sao bind query hai lần?

Hai placeholder tương ứng với:

~~~sql
similarity(product_name, ?)
product_name % ?
~~~

JDBC không mặc định “một biến query tự lặp cho mọi dấu ?” trong SQL. Phải bind tất cả placeholders theo vị trí.

### 31.3. Không gắn threshold cứng vào từng session bất cẩn

Nếu ứng dụng cần threshold khác mặc định, `SET LOCAL` phải được chạy trong **cùng transaction** với query.

~~~java
// Minh họa quy trình transaction:
// connection.setAutoCommit(false);
// try (Statement st = connection.createStatement()) {
//     st.execute("SET LOCAL pg_trgm.similarity_threshold = 0.45");
// }
// ... run PreparedStatement ...
// connection.commit(); // Hoặc rollback nếu chỉ thử nghiệm.
~~~

Phải xử lý exception, rollback và khôi phục auto-commit theo quy tắc connection pool. Không dùng lệnh `SET` tồn tại ở session rồi trả connection vào pool khi không reset session state.

### 31.4. User-provided query là text, không phải SQL

Một người dùng nhập ký tự `'`, `%`, `_` hoặc Unicode không được làm thay đổi cấu trúc câu SQL ở ví dụ prepared statement. `%` trigram operator dùng query như text đầu vào; nhưng khi chuyển sang `LIKE`/`ILIKE`, `%` và `_` vẫn có vai trò wildcard và cần chính sách escape riêng.

### 31.5. Authorization nằm trước LIMIT

Nếu bảng thực tế có `tenant_id`/`visibility`/`is_active`, SQL phải lọc tập hợp mà người dùng được xem **trước khi ranking/LIMIT**. Đừng fetch 20 kết quả nearest từ tất cả tenant rồi chỉ trả 5 sau Java filtering: vừa bỏ qua những kết quả hợp lệ, vừa có nguy cơ lộ thông tin trong log/telemetry.

### 31.6. Query ngắn và response timeouts

Áp dụng:

- Giới hạn độ dài input;
- Giới hạn `LIMIT`;
- Timeouts/statement timeout theo chính sách;
- Rate limit và query budget;
- Caching phù hợp nếu workload lặp;
- Không search toàn văn bản rất dài cho từng ký tự gõ nếu chưa debounce/giới hạn.

Đây là bảo vệ tài nguyên khi nhiều người dùng gửi autocomplete requests đồng thời.

## 32. SQL API trả ranked candidates kèm nguồn điểm

Một ứng dụng có thể cần giải thích tại sao một kết quả hiện ra. Ví dụ:

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    similarity(product_name, 'ban phim co') AS full_score,
    word_similarity('ban phim co', product_name) AS partial_score,
    strict_word_similarity('ban phim co', product_name)
        AS strict_score
FROM trgm_lab_327.products
WHERE is_active
  AND category = 'keyboard'
ORDER BY
    word_similarity('ban phim co', product_name) DESC,
    product_id
LIMIT 10;
~~~

Đây là một query **phân tích kết quả cho bộ catalog nhỏ**; ở bảng lớn, `ORDER BY word_similarity(...)` trên mọi hàng có thể gây scan/sort toàn bộ, nên cần operator index-supported để tìm ứng viên trước.

### 32.1. Lọc ứng viên trước khi tính nhiều score

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    word_similarity('ban phim co', product_name) AS score
FROM trgm_lab_327.products
WHERE is_active
  AND category = 'keyboard'
  AND 'ban phim co' <% product_name
ORDER BY score DESC, product_id
LIMIT 10;
~~~

Với index trên `product_name`, `<%` có thể giúp giảm candidates. Kết quả cuối vẫn là **điểm gần đúng**, không phải xác suất người dùng muốn mua sản phẩm ấy.

### 32.2. Một điểm tổng hợp không có nghĩa thống kê xác suất

Ứng dụng có thể xây:

~~~text
rank = w1 * full_similarity
     + w2 * word_similarity
     + w3 * category_match
     + w4 * inventory_signal
~~~

Nhưng các trọng số cần học/đánh giá qua dữ liệu click/feedback và tập benchmark có nhãn. Việc tổng hợp số học thuần túy không khiến rank trở thành “probability of relevance”.

## 33. Các điều kiện kỹ thuật ảnh hưởng tính đúng

### 33.1. Chuỗi NULL

~~~sql
SELECT
    similarity(NULL::text, 'keyboard') AS null_similarity;
~~~

Kết quả là SQL NULL. Nếu cột sản phẩm nullable, `product_name % 'keyboard'` cũng có thể cho UNKNOWN đối với NULL và không vượt WHERE; nên định nghĩa `NOT NULL` nếu tên bắt buộc.

### 33.2. Chuỗi rỗng

~~~sql
SELECT
    similarity('', 'keyboard') AS empty_score,
    show_trgm('') AS empty_trigrams;
~~~

Input rỗng không có đủ thông tin để fuzzy search hữu ích. API nên trả dữ liệu mặc định được quy định riêng hoặc không search, thay vì tính điểm toàn catalog.

### 33.3. Dấu câu và khoảng trắng

Trigram word extraction bỏ qua non-word characters, thêm padding từng từ. Việc thay `-`, `|`, khoảng trắng hoặc ký hiệu đặc thù trong mã sản phẩm có thể tác động điểm theo cách không phản ánh nghiệp vụ. Đặc biệt với mã model, cần exact path.

### 33.4. Unicode normalization và collation upgrades

Thay đổi collation/provider ICU/libc, cách normalize input hoặc hàm tạo search_name có thể tác động **giá trị index/search semantics**. Khi có migration quy tắc chữ, cần:

1. Xác định indexes phụ thuộc;
2. Tính lại normalized fields theo version mới;
3. Rebuild indexes khi cần;
4. Test relevance và uniqueness/business constraints;
5. Có cách rollback và kiểm tra dữ liệu trước/sau.

### 33.5. Không lạm dụng fuzzy trên thông tin cá nhân

Tìm gần đúng theo tên người có thể trả nhiều cá nhân khác nhau. Nó không chứng minh cùng danh tính, không dùng để vượt kiểm soát truy cập và cần tuân thủ chính sách dữ liệu cá nhân. Với dữ liệu tài chính, y tế hoặc khách hàng, gợi ý kết quả cần được xác thực bằng thông tin chính xác trong workflow được phép.

### 33.6. Tính đúng qua quyền tenant/role

Trong multi-tenant SaaS, `pg_trgm` là một access method tối ưu truy vấn, **không có cơ chế authorization riêng**. SQL/Row-Level Security phải bảo vệ dữ liệu, và query chỉ nên tính rank/trả ứng viên trong tập mà session có quyền.

## 34. Runbook chẩn đoán khi fuzzy search chậm

### Bước 1 — Xác định dạng query

Là `LIKE '%abc%'`, `ILIKE`, `%`, `<%`, `<<%`, hay `ORDER BY <-> LIMIT`?

**Không tối ưu sai toán tử:** GIN giúp lọc `%` nhưng không phải cách tối ưu KNN ordering giống GiST.

### Bước 2 — Xem kích thước/độ chọn lọc

- Bảng có vài chục, vài nghìn hay hàng triệu dòng?
- Term dài đủ để trích trigrams hữu ích?
- Threshold có quá thấp và tạo rất nhiều candidates?
- Có filter category/is_active/tenant không?
- Query trả bao nhiêu hàng, limit bao nhiêu?

### Bước 3 — Đọc EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE is_active
  AND product_name % 'keybord'
ORDER BY similarity(product_name, 'keybord') DESC
LIMIT 10;
~~~

Quan sát index cond, bitmap recheck, Filter, actual rows, sort method, buffer reads.

### Bước 4 — Kiểm tra index thật

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'trgm_lab_327'
ORDER BY tablename, indexname;
~~~

Xem có `gin_trgm_ops`/`gist_trgm_ops` đúng cột/expression và predicate partial hay không.

### Bước 5 — Xác định vấn đề

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Seq Scan` trên 20 hàng | Scan toàn bảng rẻ | Không cần ép index |
| `Seq Scan` trên 10 triệu hàng | Thiếu index, threshold quá rộng, term ngắn | Xem plan/selectivity/index/pattern |
| Query `similarity(...) >= 0.3` chậm | Không dùng operator index-supported để filter | Thử `%` cùng threshold tương ứng |
| KNN query với GIN index | GIN không hỗ trợ index-order distance như GiST | Cân nhắc GiST |
| LIKE pattern rất ngắn | Không rút trigrams hữu ích | Prefix search, hạn chế đầu vào |
| GIN bitmap trả quá nhiều rows | Threshold thấp, match rộng | Điều chỉnh threshold/query/filter |
| GiST recheck nhiều | Signature lossy / selectivity | Thử siglen/cost/index phù hợp |
| Truy vấn normalized column trả sai | search_name stale/quy tắc khác input | Đồng bộ normalization/backfill |
| CPU tăng khi autocomplete | Too many requests, query length, concurrency | Debounce/rate-limit/caching |
| Response API chậm nhưng SQL nhanh | Network/JSON/ORM/connection pool | Đo tầng ứng dụng |

### Bước 6 — Benchmark nhiều thuật ngữ

Không chỉ đo `'keyboard'`; test typo, tiếng Việt có dấu/không dấu, query rất ngắn, tên sản phẩm có mã, query theo category và sản phẩm ngừng bán.

### Bước 7 — Kiểm tra tác động ghi và vận hành

GIN/GiST index size, insert/update latency, WAL, autovacuum, rebuild/concurrent index maintenance, và p95 latency dưới concurrency đều là một phần của quyết định tối ưu.

### Bước 8 — Có rollback

Mọi thay đổi extension/index/normalized column/query ranking nên có migration, kế hoạch rollback và test kết quả trước/sau. Không tăng `similarity_threshold` toàn server rồi coi search regression là lỗi ngẫu nhiên.

## 35. Lỗi thường gặp với pg_trgm

| Ngộ nhận / lỗi | Vì sao nguy hiểm hoặc không đúng | Cách xử lý |
| --- | --- | --- |
| `pg_trgm` tự hiểu đồng nghĩa | So trigrams, không hiểu nghĩa từ | FTS + từ điển/alias hoặc lớp semantic riêng |
| Tìm `ban phim` tự khớp hoàn hảo `bàn phím` | Không tự bỏ dấu | Unicode/accent normalization có kiểm soát |
| similarity score 0.9 nghĩa 90% chắc cùng sản phẩm | Không phải xác suất | Chỉ xem là tín hiệu xếp hạng |
| `similarity` luôn tốt cho query ngắn trong tên dài | Bị giảm điểm bởi những từ khác | Thử `word_similarity`/`strict_word_similarity` |
| `word_similarity(a,b) = word_similarity(b,a)` | Word similarity có vai trò đối số khác nhau | Term bên trái, candidate bên phải |
| `strict_word_similarity` yêu cầu exact word | Vẫn là fuzzy, chỉ giới hạn ranh giới extent | Dùng `=` hoặc token comparison khi cần exact |
| `%` là phép toán modulo | Trong pg_trgm với `text`, là similarity threshold operator | Kiểm tra kiểu và extension |
| Mọi `%` luôn dùng threshold 0.3 | Ngưỡng có thể bị session/transaction đổi | Xem `SHOW pg_trgm.similarity_threshold` |
| `<%` dùng threshold giống `%` | Word similarity có GUC riêng | Xem `word_similarity_threshold` |
| `<<%` dùng cùng ngưỡng với `<%` | Strict word có GUC riêng | Xem `strict_word_similarity_threshold` |
| Đảo hai đối số word_similarity mà không đổi ngữ nghĩa | Kết quả có thể khác | Dùng commutator đúng `%>`/`%>>` |
| Distance càng lớn càng giống | Distance = 1 - similarity | `ORDER BY distance ASC` |
| `ORDER BY similarity DESC` tự thành KNN GiST | KNN cần distance operator phù hợp | Dùng `ORDER BY column <-> query LIMIT` |
| GIN hỗ trợ KNN top-K giống GiST | GIN không có index-order search tương tự | Chọn GiST cho nearest-neighbor |
| GiST luôn nhanh hơn GIN | Phụ thuộc workload, filter vs KNN | Benchmark query thật |
| GIN luôn nhanh hơn GiST | Nhiều trường hợp KNN/siglen khác nhau | Benchmark |
| B-tree trên name đủ cho `ILIKE '%abc%'` | Leading wildcard hạn chế B-tree | Cân nhắc trigram |
| Trigram index tăng tốc mọi pattern ngắn | Ít/không có trigrams để trích | Prefix search/giới hạn query |
| `ILIKE` tự sửa typo | Chỉ so pattern, không fuzzy | `%`, `<%` hoặc KNN |
| Regex bất kỳ sẽ dùng trigram index | Có pattern không rút được trigrams | Giới hạn regex, đọc `EXPLAIN` |
| `LIKE '%50%%'` tìm dấu % literal | Wildcard vẫn có ý nghĩa | Escape metacharacters |
| `similarity(...) >= 0.3` luôn dùng GIN như `%` | Hàm so sánh có thể đòi tính score trên nhiều rows | Lọc candidates bằng operator |
| `SHOW pg_trgm.similarity_threshold` cho một giá trị cố định toàn cluster | GUC có thể bị đổi ở session/transaction | Xem nguồn cấu hình, dùng `SET LOCAL` khi thử |
| `set_limit` là API nên dùng | API cũ deprecated | Ưu tiên GUC `SET`/`SHOW` |
| `SET` trên pooled connection tự được reset | Có thể còn session state | `SET LOCAL` transaction và pool reset |
| GiST bitmap signature không bao giờ false positive | Có thể cần recheck | Xem `Rows Removed by Index Recheck` |
| Tăng `siglen` luôn làm mọi query nhanh | Tăng index size và chi phí khác | Benchmark |
| `CREATE INDEX CONCURRENTLY` không có rủi ro | Có thể để lại invalid index | Theo dõi logs/`pg_index` |
| `CREATE INDEX CONCURRENTLY` chạy trong `BEGIN` | PostgreSQL không hỗ trợ | Chạy ngoài explicit transaction |
| Nhiều trigram index không ảnh hưởng writes | Tăng maintenance/WAL | Đo INSERT/UPDATE |
| Có index thì planner chắc chắn dùng | Cost/selectivity có thể ưu tiên Seq Scan | Xem `EXPLAIN`, đặc biệt bảng nhỏ |
| `pg_trgm` index chỉ áp dụng khi LIKE không có wildcard đầu | Trigram có thể hỗ trợ leading wildcard | Dùng pattern đủ trigrams hữu ích |
| Partial GIN active được dùng với mọi query | Query phải chứng minh predicate active | Ghi đúng filter/kiểm tra generic plan |
| Lọc tenant ở Java sau LIMIT là tương đương | Sai top-K và rủi ro lộ dữ liệu | Filter ngay trong SQL |
| Fuzzy trên SKU đủ thay unique constraint | Không có tính xác thực/uniqueness | B-tree exact `=` và constraint |
| `unaccent` có thể ép IMMUTABLE tùy ý để tạo index | Rules/dictionary có thể thay đổi | Lưu normalized text và migration |
| Bỏ dấu không có tác dụng phụ | Có thể gộp những từ/mã khác nhau | Giữ dữ liệu gốc, kiểm thử |
| `pg_trgm` xử lý tốt mọi tên tiếng Việt | Trigram không đảm bảo phân đoạn/ý nghĩa tiếng Việt | Đánh giá trên bộ test tiếng Việt |
| Top 10 luôn có 10 kết quả relevant | KNN có thể trả gần nhất dù tất cả đều không liên quan | Threshold tối thiểu + empty state |
| `ORDER BY score` đủ ổn định khi score bằng nhau | Ties không có thứ tự xác định | Thêm product_id tie-break |
| Đánh giá bằng một query `keyboard` | Không đại diện typo, ngôn ngữ, độ dài | Bộ benchmark có nhãn |
| Chỉ đo latency, bỏ precision | Search nhanh nhưng kết quả sai | Đo relevance và hiệu năng |
| `pg_stat_user_indexes.idx_scan=0` nghĩa index vô ích | Có thể reset stats, thiếu workload hoặc index unique | Quan sát dài hạn và constraint |
| Query PostgreSQL nhanh thì API chắc chắn nhanh | Pool/network/mapping có thể chậm | Trace end-to-end |
| SQL bound parameter tự giới hạn quyền tìm | Injection safety khác authorization | Filter tenant/RLS/visibility |

## 36. Bài tập thực hành

Các bài tập dùng bảng `trgm_lab_327.products` và những indexes đã minh họa. Đối với một số bài, câu trả lời là **cách suy luận/chọn công cụ**, không phải một con số similarity cố định: kết quả thực tế cần xem từ PostgreSQL, không được đoán. Những lệnh thay GUC nên chạy trong transaction lab với `SET LOCAL` và `ROLLBACK`.

### Bài 1 — Kiểm tra extension

Viết SQL xác nhận `pg_trgm` đã được cài trong database hiện tại, xem version và schema chứa extension.

**Gợi ý:** `pg_extension`.

### Bài 2 — Xem trigrams của một từ

~~~sql
SELECT show_trgm('cat');
~~~

**Câu hỏi:** vì sao `cat` có các trigrams bắt đầu/kết thúc bằng dấu cách? Quy tắc padding có mấy dấu cách ở đầu và cuối?

**Đáp án:** hai ở đầu, một ở cuối **mỗi word**.

### Bài 3 — Lỗi gõ một ký tự

So:

~~~sql
SELECT
    similarity('keyboard', 'keybord') AS typo_score,
    similarity('keyboard', 'monitor') AS unrelated_score;
~~~

**Bài tập:** giải thích dựa trên trigram overlap, không suy đoán một số điểm chính xác nếu chưa chạy.

### Bài 4 — Whole-string vs word match

Tính:

~~~sql
SELECT
    similarity('wireless', 'wireless mechanical keyboard'),
    word_similarity('wireless', 'wireless mechanical keyboard'),
    strict_word_similarity('wireless', 'wireless mechanical keyboard');
~~~

**Câu hỏi:** tại sao cả chuỗi dài thường khiến full similarity khác word/strict similarity?

### Bài 5 — Đảo đối số

So `word_similarity('bluetooth', product_name)` với `word_similarity(product_name,'bluetooth')` cho một tên dài.

**Kết luận:** word similarity không đương nhiên đối xứng. Trường nào là query, trường nào là candidate?

### Bài 6 — Strict word boundary

So `word_similarity('key','keyboard')` và `strict_word_similarity('key','keyboard')`.

**Câu hỏi:** strict chọn extent theo quy tắc gì, và có đồng nghĩa với exact match không?

### Bài 7 — Xem ba ngưỡng

Chạy:

~~~sql
SHOW pg_trgm.similarity_threshold;
SHOW pg_trgm.word_similarity_threshold;
SHOW pg_trgm.strict_word_similarity_threshold;
~~~

**Gợi ý:** mặc định tham khảo lần lượt 0.3, 0.6 và 0.5; giá trị thực tế có thể đã được đổi.

### Bài 8 — % operator

Viết query lọc danh mục bằng `product_name % 'bluetooh'`, rồi sắp theo `similarity(...) DESC`.

**Câu hỏi:** vì sao toán tử `%` có lợi hơn điều kiện `similarity(...) >= threshold` cho việc dùng trigram index?

### Bài 9 — Tuning ngưỡng trong transaction

~~~sql
BEGIN;
SET LOCAL pg_trgm.similarity_threshold = 0.6;
SELECT product_id
FROM trgm_lab_327.products
WHERE product_name % 'bluetooh';
ROLLBACK;
~~~

**Câu hỏi:** sau `ROLLBACK` có còn ngưỡng 0.6 không?

**Đáp án:** không; `SET LOCAL` chỉ áp dụng trong transaction.

### Bài 10 — Word similarity operator

Viết query dùng `'bluetooh' <% product_name` và hiển thị `word_similarity('bluetooh', product_name)`.

**Câu hỏi:** toán tử nào là commutator khi muốn đặt `product_name` bên trái?

**Đáp án:** `product_name %> 'bluetooh'`.

### Bài 11 — Strict word operator

Viết query dùng `'gaming' <<% product_name` và xếp theo `strict_word_similarity`.

**Câu hỏi:** GUC nào điều khiển threshold?

### Bài 12 — So sánh % với <% và <<%

Trên query `'mechanical'` và các tên tiếng Anh dài, chạy ba truy vấn với `%`, `<%`, `<<%`.

**Câu hỏi:** khác nhau về ứng viên có liên quan đến loại điểm và ranh giới từ như thế nào?

### Bài 13 — Distance

Tính:

~~~sql
SELECT
    similarity('keyboard','keybord') AS sim,
    'keyboard' <-> 'keybord' AS dist;
~~~

**Đáp án định hướng:** về toán học `dist = 1 - sim`, có sai khác làm tròn floating-point.

### Bài 14 — Top-K bằng distance

Viết query lấy năm sản phẩm gần nhất với `'keybord'`, dùng `ORDER BY product_name <-> 'keybord' LIMIT 5`.

**Câu hỏi:** khác gì với `WHERE product_name % 'keybord'`?

### Bài 15 — Word distance

Viết `ORDER BY 'bluetooh' <<-> product_name`.

**Câu hỏi:** tại sao term nên ở bên trái? Cú pháp commutator là gì?

### Bài 16 — Strict word distance

Viết `ORDER BY 'gaming' <<<-> product_name` cho top 5. Hãy nêu khác biệt giữa phép đo này và full-string `<->`.

### Bài 17 — GIN index

Tạo:

~~~sql
CREATE INDEX idx_practice_name_gin_327
ON trgm_lab_327.products
USING gin (product_name gin_trgm_ops);
~~~

**Câu hỏi:** trường hợp nào GIN có thể giúp lọc ứng viên? Chỉ có index đã đảm bảo Query Planner dùng không?

### Bài 18 — GiST index

Tạo:

~~~sql
CREATE INDEX idx_practice_name_gist_327
ON trgm_lab_327.products
USING gist (product_name gist_trgm_ops);
~~~

**Câu hỏi:** vì sao GiST có thể thích hợp cho nearest neighbors?

### Bài 19 — GIN và ORDER BY distance

Chỉ có GIN index. Query `ORDER BY product_name <-> 'keybord' LIMIT 10` có thể tận dụng KNN index ordering như GiST không?

**Đáp án:** không theo cơ chế GiST KNN; planner có thể phải tính điểm/sort các hàng.

### Bài 20 — GiST siglen

Nêu ý nghĩa của `gist_trgm_ops(siglen=32)` và trade-off giữa index size với độ chính xác chữ ký/heap rechecks.

### Bài 21 — LIKE với wildcard đầu

~~~sql
SELECT product_id, product_name
FROM trgm_lab_327.products
WHERE product_name ILIKE '%keyboard%';
~~~

**Câu hỏi:** trigram index có thể hỗ trợ điều gì mà B-tree thông thường khó làm với pattern leading `%`?

### Bài 22 — ILIKE không phải fuzzy

Tìm `'%bluetooh%'` bằng `ILIKE` và bằng `product_name % 'bluetooh'`.

**Câu hỏi:** vì sao thứ nhất không tự sửa typo `bluetooth` còn thứ hai có thể tìm gần đúng?

### Bài 23 — Pattern quá ngắn

Với `ILIKE '%a%'`, giải thích vì sao không thể mặc định GIN trigram index hiệu quả. Đề xuất chính sách autocomplete cho query dài 1–2 ký tự.

### Bài 24 — Regex

Viết query dùng `~* '(keyboard|bluetooth)'`.

**Câu hỏi:** một regex `'.*'` có thể tạo đủ trigrams cho index selective search không?

### Bài 25 — Exact SKU

~~~sql
SELECT product_id
FROM trgm_lab_327.products
WHERE sku = 'KB-001';
~~~

**Câu hỏi:** tại sao phải dùng unique/B-tree exact lookup thay vì `sku % 'KB-001'`?

### Bài 26 — Sản phẩm có tên gần như trùng

So `'Cáp USB-C 1m'` với `'Cáp USB-C 2m'`.

**Câu hỏi:** score cao có đủ để đổi mục hàng trong giỏ không? Nêu business attributes cần kiểm tra.

### Bài 27 — Sản phẩm inactive

Viết fuzzy search có `WHERE is_active`.

**Câu hỏi:** vì sao filter sau `LIMIT` trong Java vừa sai top-K vừa có thể gây rủi ro quyền dữ liệu?

### Bài 28 — Partial GIN index

Tạo partial GIN `WHERE is_active` và giải thích khi nào query được planner xem là phù hợp. Nếu generic plan dùng `is_active=$1`, tình huống nào khiến partial index không áp dụng được?

### Bài 29 — Unicode NFC và dấu

Giải thích tại sao `'bàn phím'` và `'ban phim'` không được `pg_trgm` tự coi là cùng một dạng. Phân biệt **Unicode normalization** với **bỏ dấu**.

### Bài 30 — unaccent và IMMUTABLE

Một developer viết UDF gọi `unaccent` rồi khai báo `IMMUTABLE` để lập index.

**Bài tập:** giải thích vì sao rules/dictionary có thể thay đổi khiến function không bất biến thật sự; đề xuất lưu `search_name` được duy trì/migration.

### Bài 31 — search_name có thể stale

Sau khi đổi `product_name` mà không update `search_name`, query nào sẽ trả dữ liệu cũ? Làm thế nào kiểm soát write-path, backfill và rule version?

### Bài 32 — Full-text search và typo

So cách tìm từ `'bluetooth'` bằng `to_tsvector ... @@ ...` và từ `'bluetooh'` bằng trigram correction.

**Câu hỏi:** vì sao trigram có thể bổ sung full-text search mà không thay thế nó?

### Bài 33 — Từ điển gợi ý

Tạo bảng từ vựng từ `ts_stat`, lập GIN trigram index trên `word` và query `word % 'bluetooh'`.

**Câu hỏi:** khi descriptions được cập nhật, bảng từ vựng có tự thay đổi không?

**Đáp án:** không trong thiết kế materialized table đơn giản ở lab; cần quy trình refresh/sync.

### Bài 34 — Gợi ý tên sản phẩm và từ đồng nghĩa

Người dùng nhập `'laptop'` nhưng tên sản phẩm là `'máy tính xách tay'`. Vì sao similarity không đủ? Nêu phương án alias/synonym/từ điển ngữ nghĩa.

### Bài 35 — Candidate score và relevance

Một query trả 10 kết quả, 7 được gắn nhãn relevant. Tính Precision@10.

**Đáp án:** 0.7. Có thể diễn giải similarity score cao nhất thành precision không?

**Đáp án:** không, đây là hai loại đại lượng khác nhau.

### Bài 36 — Recall@10

Nếu có 14 sản phẩm relevant và top 10 tìm được 7, tính Recall@10.

**Đáp án:** 0.5. Vì sao giảm threshold có thể tăng recall nhưng cũng tăng false positives?

### Bài 37 — Top-K với ngưỡng quá thấp

Một query KNN trả 5 sản phẩm gần nhất dù tất cả rất ít tương đồng. Bạn sẽ thêm chính sách confidence/empty-state thế nào mà **không** tự đánh đồng score với xác suất?

### Bài 38 — Nhiều ngôn ngữ

Thiết kế bảng product aliases có `product_id`, `locale`, `alias_name`, `search_name`. Nêu ưu điểm so với nối mọi alias vào một chuỗi tìm kiếm duy nhất.

### Bài 39 — Self join near-duplicates

Viết query nối `products a JOIN products b` trên `a.product_id < b.product_id` cùng category và `a.product_name % b.product_name`.

**Câu hỏi:** vì sao trên một triệu sản phẩm cần blocking, giới hạn batch và review?

### Bài 40 — EXPLAIN với GIN

Trên bảng benchmark (nếu đã tạo), dùng `EXPLAIN (ANALYZE,BUFFERS)` cho `product_name ILIKE '%mechanical%'`.

**Câu hỏi:** phân biệt `Bitmap Index Scan`, `Bitmap Heap Scan`, `Recheck Cond` và `Sort`.

### Bài 41 — EXPLAIN với GiST KNN

Trên benchmark, dùng `EXPLAIN` cho `ORDER BY product_name <-> 'keybord' LIMIT 5`.

**Câu hỏi:** nếu thấy `Index Scan ... Order By` có ý nghĩa gì? Nếu thấy Seq Scan + Sort ở bảng nhỏ, có chứng minh GiST không hoạt động không?

### Bài 42 — Chi phí writes

Một bảng có 10 triệu products và hàng trăm nghìn updates mỗi giờ, team muốn thêm GIN + hai GiST trigram indexes trên cùng cột.

**Bài tập:** nêu các số đo cần có trước khi triển khai: index size, WAL, INSERT/UPDATE latency, VACUUM, read p95, query count và rollback.

### Bài 43 — CREATE INDEX CONCURRENTLY

Giải thích ưu nhược `CREATE INDEX CONCURRENTLY` trên production và vì sao không chạy trong explicit transaction.

**Câu hỏi:** nếu command lỗi, phải kiểm tra `pg_index.indisvalid`/`indisready` và làm gì trước khi tạo lại?

### Bài 44 — SET LOCAL trong connection pool

Một ứng dụng gọi `SET pg_trgm.similarity_threshold=0.1` rồi trả connection về pool.

**Câu hỏi:** request kế tiếp có nguy cơ gì? Viết quy trình transaction dùng `SET LOCAL` để cô lập ngưỡng.

### Bài 45 — PreparedStatement an toàn

Viết phương thức Java nhận term và limit, dùng hai placeholders cho `similarity(name, ?)` và `name % ?`, cùng một placeholder cho `LIMIT ?`.

**Yêu cầu:** validate độ dài, bind parameters, đóng `PreparedStatement`/`ResultSet` và giới hạn số kết quả.

### Bài 46 — LIKE wildcard từ user input

User tìm literal `'50%'`. Tại sao nối thành `ILIKE '%50%%'` không có nghĩa đúng? Phân biệt **SQL injection** với **LIKE wildcard escaping**.

### Bài 47 — Multi-tenant security

Một query fuzzy tìm tất cả customers của mọi tenant rồi chỉ lọc tenant trong Java sau khi `LIMIT 10`.

**Bài tập:** giải thích tại sao sai, và chuyển điều kiện `tenant_id`/quyền vào SQL trước ranking.

### Bài 48 — Tên người không phải identity

Hai khách hàng có tên gần giống và trigram similarity 0.97.

**Câu hỏi:** có thể tự động merge hồ sơ không? Vì sao cần xác minh bằng quy trình nghiệp vụ và dữ liệu chính xác khác?

### Bài 49 — Benchmark không công bằng

Nhóm A đo GIN ở lần truy vấn đầu (cold cache), nhóm B đo GiST ở lần hai (warm cache) rồi kết luận GiST nhanh gấp 3.

**Bài tập:** thiết kế lại benchmark A/B: cùng SQL/term/rows, thứ tự xen kẽ, `EXPLAIN BUFFERS`, index size, throughput và nhiều lượt chạy.

### Bài 50 — Capstone: tìm sản phẩm gần đúng

Thiết kế API tìm sản phẩm với các yêu cầu:

- Nếu query khớp SKU thì ưu tiên **exact B-tree lookup**.
- Nếu query là từ khóa có dấu/không dấu, normalize theo quy tắc nhất quán, vẫn hiển thị tên gốc.
- Với query từ đơn nằm trong tên dài, cân nhắc `word_similarity`/`strict_word_similarity`.
- Với tên gần giống nhau, dùng `similarity` hoặc KNN theo `<->`.
- Với lỗi gõ, dùng trigram fallback hoặc gợi ý chính tả.
- Với query quá ngắn, không thực hiện fuzzy full-table scan không giới hạn.
- Chỉ tìm những sản phẩm `is_active` mà người dùng được phép xem.
- Có tối đa 10 kết quả, có tie-break `product_id` và có empty-state khi không đủ relevance.
- Chọn GIN hay GiST theo filter/trigram vs nearest-neighbor ordering.
- Dùng prepared statements; không nối input vào SQL/LIKE/regex tùy tiện.
- Đo Precision@10, Recall@10, p95 latency, buffer reads, index size và write cost.
- Có migration cho normalized fields, collation/Unicode và extension/index upgrades.

**Đầu ra mong đợi:** sơ đồ luồng xử lý, hai hoặc ba câu SQL chính, chiến lược index, ma trận test query có nhãn, chính sách threshold và kế hoạch rollback khi search relevance giảm.

## 37. Checklist triển khai pg_trgm

1. [ ] Extension `pg_trgm` có trong database và schema được truy cập đúng.
2. [ ] Đã xác định search là exact, substring, prefix, fuzzy hay semantic.
3. [ ] Không dùng fuzzy cho SKU/transaction key/security token.
4. [ ] Hiểu trigram padding và non-word character behavior.
5. [ ] Đã chọn `similarity`, `word_similarity` hay `strict_word_similarity` theo use case.
6. [ ] Dùng đúng thứ tự đối số của `<%`/`<<%` và các commutators.
7. [ ] Đã biết ba GUC thresholds riêng và ghi rõ môi trường thử.
8. [ ] Thử nghiệm bằng `SET LOCAL`, không làm rò session state.
9. [ ] Có chính sách Unicode normalization và/hoặc bỏ dấu nếu cần.
10. [ ] Không ép UDF dựa trên `unaccent` thành IMMUTABLE giả.
11. [ ] Có phương án duy trì normalized search_name và rule version.
12. [ ] Có đường exact lookup/aliases cho business identifiers.
13. [ ] Đã chọn GIN cho filter/substrings hay GiST cho nearest neighbors khi phù hợp.
14. [ ] Không kỳ vọng GIN hỗ trợ KNN index ordering như GiST.
15. [ ] Biết GiST `siglen` đánh đổi precision của signature với kích thước.
16. [ ] Đã kiểm tra các pattern rất ngắn và regex không rút được trigrams.
17. [ ] Đã escape LIKE wildcards nếu input phải được hiểu literal.
18. [ ] Có filter `is_active`/`tenant_id`/authorization trước `LIMIT`.
19. [ ] Đã xem partial index có được planner suy luận predicate không.
20. [ ] Đã đọc `EXPLAIN`, buffer counts, rechecks, sort, actual rows.
21. [ ] Đã benchmark trên tập lớn và phân phối dữ liệu gần workload thực.
22. [ ] Đã cân nhắc GIN pending-list và GiST signature maintenance.
23. [ ] Đã đo thêm chi phí INSERT/UPDATE, WAL, VACUUM và index size.
24. [ ] Có testing relevance: typo, Unicode, query ngắn/dài, tên gần giống khác model.
25. [ ] Đã đo precision/recall@K và p95 latency.
26. [ ] Đã dùng bound parameters và giới hạn độ dài input/LIMIT.
27. [ ] Có rate limit, timeout và query budget cho autocomplete.
28. [ ] Có logging/metrics nhưng không vô tình ghi dữ liệu nhạy cảm.
29. [ ] Có kế hoạch cập nhật dictionary/aliases/synonyms.
30. [ ] Có migration/rollback cho extensions, indexes và normalization changes.

## 38. Tài liệu chính thức PostgreSQL

Các ví dụ trong bài áp dụng cho PostgreSQL hiện đại; cần kiểm tra **đúng major version** của hệ thống vì function/operator/index features và cách planner chọn plan có thể thay đổi.

- [`pg_trgm` — similarity, operators, thresholds, GiST/GIN](https://www.postgresql.org/docs/current/pgtrgm.html): tài liệu chính của extension, bao gồm `show_trgm`, `similarity`, `word_similarity`, `strict_word_similarity`, toán tử distance, `siglen` và KNN index scan.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html): cài extension, schema và quyền.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `USING gin/gist`, operator class, partial index, `CONCURRENTLY`.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, GiST, GIN và các điều kiện truy cập được hỗ trợ.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): lập index trên `lower(name)` và normalized fields.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): predicate implication và giới hạn dùng partial index.
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html): GIN structure, maintenance và đặc điểm index.
- [GIN Tips and Tricks](https://www.postgresql.org/docs/current/gin-tips.html): pending list và hiệu năng ghi/đọc.
- [GiST Indexes](https://www.postgresql.org/docs/current/gist.html): khái niệm GiST/operator classes.
- [Pattern Matching](https://www.postgresql.org/docs/current/functions-matching.html): `LIKE`, `ILIKE` và regular expressions.
- [Text Search](https://www.postgresql.org/docs/current/textsearch.html): `tsvector`, `tsquery`, configurations và ranking.
- [Text Search Functions and Operators](https://www.postgresql.org/docs/current/functions-textsearch.html): `to_tsvector`, `plainto_tsquery`, `ts_stat`.
- [Data Type Character Sets / Collations](https://www.postgresql.org/docs/current/collation.html): collation behavior và nâng cấp collation.
- [String Functions](https://www.postgresql.org/docs/current/functions-string.html): chuẩn hóa/chuyển đổi chuỗi và những giới hạn.
- [unaccent](https://www.postgresql.org/docs/current/unaccent.html): text search dictionary và hàm hỗ trợ bỏ dấu; cân nhắc volatility khi lập expression index.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): `ANALYZE`, `BUFFERS`, `SETTINGS` và cách đo plan.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): estimated cost, actual rows, Seq/Index/Bitmap scans.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): prepared statements và generic/custom plan khi tham số ảnh hưởng planner.

Tài liệu URL `/docs/current/` trỏ tới PostgreSQL version hiện hành. Trên môi trường chạy PostgreSQL 14, 15, 16, 17, 18 hoặc version khác, hãy mở bộ tài liệu mang **số phiên bản chính xác** trước khi áp dụng những GUC/cú pháp có thể thay đổi.

## 39. Tổng kết

**`pg_trgm`** hỗ trợ **tìm kiếm gần đúng ở cấp ký tự** bằng các trigrams. Ba hàm trọng tâm là `similarity(a,b)` cho toàn chuỗi, `word_similarity(a,b)` cho đoạn liên tục tương đồng nhất trong `b`, và `strict_word_similarity(a,b)` cho đoạn khớp theo **ranh giới từ**. Chúng trả điểm từ 0 đến 1; điểm cao nghĩa tương đồng theo metric trigram, **không phải xác suất cùng đối tượng**.

Trong SQL, `%`, `<%`/`%>` và `<<%`/`%>>` lọc ứng viên theo **ba ngưỡng cấu hình riêng**. Các toán tử khoảng cách `<->`, `<<->` và `<<<->` đo `1 - similarity` tương ứng; vì vậy **khoảng cách nhỏ hơn là tốt hơn**. Khi cần top-K kết quả gần nhất, `ORDER BY indexed_column <-> query LIMIT K` có thể tận dụng **GiST KNN**. Khi cần lọc nhiều ứng viên hoặc tìm substring bằng `LIKE`/`ILIKE`, **GIN trigram** có thể là lựa chọn phù hợp. Không mặc định GIN hỗ trợ KNN ordering giống GiST hoặc mọi pattern ngắn đều được tăng tốc.

Đối với tiếng Việt, `pg_trgm` không tự bỏ dấu, không tự phân đoạn từ theo ngữ nghĩa và không dịch đồng nghĩa. Muốn hỗ trợ tìm **không dấu**, hãy thiết kế normalizer thống nhất và quản lý dữ liệu `search_name`/migration thay vì khai báo sai một UDF phụ thuộc `unaccent` là IMMUTABLE. Với SKU, mã model, tên sản phẩm khác dung lượng hoặc danh tính khách hàng, luôn giữ **đường so khớp chính xác và các kiểm tra nghiệp vụ**.

Một giải pháp fuzzy search tốt cần cả **relevance lẫn performance**: tập test typo và Unicode có nhãn, Precision/Recall@K, ngưỡng được hiệu chỉnh, `EXPLAIN`/buffers, giới hạn input/LIMIT, cơ chế authorization, monitoring write cost và rollback. `pg_trgm` hiệu quả nhất khi được dùng làm **bộ tìm ứng viên/gợi ý chính tả có kiểm soát**, kết hợp exact match, full-text search và business filters thay vì coi nó như công cụ hiểu ngôn ngữ hay xác minh thực thể.
