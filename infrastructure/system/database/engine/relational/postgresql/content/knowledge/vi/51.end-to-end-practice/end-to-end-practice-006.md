# Xây tìm kiếm toàn văn và tìm kiếm gần đúng cho danh mục

Một danh mục sản phẩm, tài liệu hoặc nội dung thường cần hỗ trợ hai kiểu tìm kiếm. Tìm kiếm toàn văn (full-text search) tìm các từ và cụm từ trong nhiều trường, hiểu toán tử tìm kiếm và xếp hạng kết quả theo mức độ liên quan. Tìm kiếm gần đúng (fuzzy search) giúp tìm được mục có tên gần giống khi người dùng gõ sai chính tả, thiếu dấu hoặc nhớ không chính xác tên.

PostgreSQL cung cấp hai nhóm công cụ phù hợp cho bài toán này: Full Text Search với các kiểu dữ liệu tsvector, tsquery và chỉ mục GIN; cùng extension pg_trgm để so sánh độ tương đồng theo trigram. Kết hợp hai nhóm công cụ giúp xây dựng tìm kiếm danh mục ngay trong database, giữ được bộ lọc dữ liệu và thứ tự kết quả nhất quán.

Bài học sử dụng bảng danh mục giả định tên catalog_items, gồm tên, thương hiệu, loại và mô tả. Các ví dụ có thể điều chỉnh cho danh mục bài viết, tài liệu, khách hàng hoặc dữ liệu nghiệp vụ khác.

## 1. Chọn đúng loại tìm kiếm

Hai kỹ thuật giải quyết hai nhu cầu khác nhau:

| Nhu cầu | Full-text search | Fuzzy search |
|---|---|---|
| Tìm một từ trong mô tả dài | Phù hợp | Không phải mục tiêu chính |
| Tìm nhiều từ theo cú pháp AND/OR | Có hỗ trợ qua tsquery | Không biểu diễn ý nghĩa từ như vậy |
| Tìm cụm từ | Có phrase query | Có thể so độ gần chuỗi |
| Xếp hạng theo mức độ liên quan của từ | Có ts_rank / ts_rank_cd | Có similarity và distance |
| Sửa lỗi gõ gần đúng | Hạn chế | Phù hợp |
| Tìm chuỗi con trong tên | Không phải chức năng chính | Có thể dùng trigram với LIKE/ILIKE hoặc word similarity |
| Tìm tên ngắn | Phụ thuộc token | Trigram có thể kém hiệu quả với chuỗi quá ngắn |

Ví dụ người dùng tìm tai nghe bluetooth:

- Full-text search có thể tìm sản phẩm có đủ các từ trong tên, thương hiệu, loại hoặc mô tả.
- Fuzzy search có thể tìm Tai nghe Bluetooh dù người dùng đảo hoặc gõ sai một vài ký tự trong tên.
- Một hệ thống thực tế thường lấy ứng viên từ cả hai kỹ thuật, sau đó hợp nhất và xếp hạng.

Không nên dùng fuzzy search để thay thế full-text search trên mô tả dài. Trigram đo sự giống nhau của chuỗi, không hiểu đầy đủ quan hệ ngữ nghĩa hoặc ý định của người dùng.

## 2. PostgreSQL Full Text Search hoạt động thế nào?

Full Text Search chuyển văn bản thành một biểu diễn có thể tìm kiếm hiệu quả.

- tsvector lưu các lexeme (dạng từ đã được chuẩn hóa) cùng vị trí xuất hiện.
- tsquery biểu diễn điều kiện tìm kiếm, gồm từ, toán tử AND, OR, phủ định và tìm cụm.
- Toán tử @@ kiểm tra một tsvector có khớp tsquery hay không.
- to_tsvector chuyển văn bản thành vector.
- plainto_tsquery, phraseto_tsquery và websearch_to_tsquery chuyển truy vấn người dùng thành query có cấu trúc.

Ví dụ đơn giản:

~~~sql
SELECT
    to_tsvector('english', 'PostgreSQL supports full text search')
        AS document_vector,
    plainto_tsquery('english', 'text search')
        AS search_query;
~~~

Có thể kiểm tra phép khớp:

~~~sql
SELECT
    to_tsvector('english', 'PostgreSQL supports full text search')
    @@ plainto_tsquery('english', 'text search')
    AS matched;
~~~

Kết quả là true vì tài liệu chứa các từ cần tìm.

### 2.1. Cấu hình text search

Tham số đầu tiên của các hàm text search là cấu hình ngôn ngữ (regconfig). Cấu hình quyết định cách tách token, chuẩn hóa từ, loại stop word và stemming.

Xem các cấu hình có sẵn:

~~~sql
SELECT
    cfgname,
    cfgnamespace::regnamespace AS schema_name
FROM pg_ts_config
ORDER BY cfgname;
~~~

Có thể xem cách PostgreSQL phân tích một câu:

~~~sql
SELECT *
FROM ts_debug('simple', 'Tai nghe khong day cho dien thoai');
~~~

simple là cấu hình đơn giản, phù hợp khi muốn giữ từ ở dạng cơ bản và không cần stemming theo ngôn ngữ. Các cấu hình như english có từ điển và quy tắc chuẩn hóa dành cho tiếng Anh.

Không nên giả định PostgreSQL cài sẵn cấu hình stemming tiếng Việt. Với nội dung tiếng Việt, cần kiểm tra cấu hình thực tế trong pg_ts_config; nếu không có bộ phân tích tiếng Việt phù hợp, simple là lựa chọn khởi đầu dễ dự đoán. Nó không thực hiện đầy đủ tách từ tiếng Việt theo ngữ nghĩa hoặc chuyển các biến thể từ về một gốc từ. Nếu cần chất lượng tìm kiếm tiếng Việt cao hơn, có thể chuẩn hóa/tách từ ở tầng ứng dụng hoặc tích hợp bộ phân tích phù hợp, sau đó lưu trường tìm kiếm đã xử lý.

Dùng cùng một cấu hình cho lúc tạo vector và lúc tạo query. Nếu vector được tạo bằng simple nhưng query lại dùng english, kết quả có thể không như mong đợi.

### 2.2. Chuyển truy vấn người dùng thành tsquery

Các hàm tạo query có hành vi khác nhau:

| Hàm | Cách xử lý |
|---|---|
| plainto_tsquery(config, text) | Xem đầu vào là văn bản thường; các từ được nối bằng AND |
| phraseto_tsquery(config, text) | Tạo truy vấn cụm từ theo thứ tự |
| websearch_to_tsquery(config, text) | Hỗ trợ cú pháp gần với công cụ tìm kiếm web như dấu ngoặc kép, OR và dấu trừ |
| to_tsquery(config, text) | Nhận cú pháp tsquery rõ ràng, gồm toán tử; đầu vào cần được kiểm soát |

Ví dụ:

~~~sql
SELECT plainto_tsquery('simple', 'tai nghe bluetooth');

SELECT phraseto_tsquery('simple', 'tai nghe bluetooth');

SELECT websearch_to_tsquery(
    'simple',
    '"tai nghe" bluetooth -co day'
);
~~~

Với truy vấn do người dùng nhập, websearch_to_tsquery thường dễ dùng hơn to_tsquery vì người dùng không cần biết cú pháp toán tử nội bộ của PostgreSQL. Nếu cần cú pháp nâng cao, hãy định nghĩa rõ grammar và validate đầu vào.

Không nối chuỗi truy vấn trực tiếp vào SQL. Dùng bind parameter của driver hoặc prepared statement để tránh SQL injection. to_tsquery cũng không nên nhận nguyên văn đầu vào tự do nếu người dùng không được hướng dẫn cú pháp, vì ký tự toán tử không hợp lệ có thể gây lỗi parse.

## 3. Thiết kế bảng danh mục và search vector

Giả sử danh mục có các trường:

- name: tên sản phẩm, có trọng số cao nhất.
- brand: thương hiệu.
- category: loại sản phẩm.
- description: mô tả dài, có trọng số thấp hơn.

Có thể lưu một cột tsvector được PostgreSQL tự tạo bằng generated column:

~~~sql
CREATE TABLE catalog_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    brand text,
    category text,
    description text,
    active boolean NOT NULL DEFAULT true,

    search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(
                to_tsvector('simple', coalesce(name, '')),
                'A'
            )
            ||
            setweight(
                to_tsvector('simple', coalesce(brand, '')),
                'B'
            )
            ||
            setweight(
                to_tsvector('simple', coalesce(category, '')),
                'B'
            )
            ||
            setweight(
                to_tsvector('simple', coalesce(description, '')),
                'C'
            )
        ) STORED
);
~~~

coalesce biến giá trị NULL thành chuỗi rỗng để hàm chuyển đổi luôn nhận được text. Toán tử || ghép các vector. setweight đánh dấu mức quan trọng của từ:

- A: quan trọng nhất, dùng cho tên.
- B: quan trọng vừa, dùng cho thương hiệu và loại.
- C: thấp hơn, dùng cho mô tả.
- D: mức thấp nhất, thường là mặc định.

Trọng số không thay đổi dữ liệu gốc. Nó được dùng khi tính điểm xếp hạng như ts_rank hoặc ts_rank_cd.

Thêm một số dữ liệu mẫu:

~~~sql
INSERT INTO catalog_items (name, brand, category, description)
VALUES
(
    'Tai nghe Bluetooth X100',
    'Acme',
    'Tai nghe khong day',
    'Tai nghe chong on, pin lau, ket noi dien thoai'
),
(
    'Ban phim co K80',
    'KeyPro',
    'Phu kien may tinh',
    'Ban phim co ket noi USB va Bluetooth'
),
(
    'Chuot khong day M2',
    'Acme',
    'Phu kien may tinh',
    'Chuot quang khong day cho laptop'
),
(
    'Loa Bluetooth Mini',
    'SoundBox',
    'Loa',
    'Loa di dong pin sac, ket noi Bluetooth'
);
~~~

Ví dụ này dùng văn bản không dấu để minh họa rõ cách hoạt động với cấu hình simple. Khi triển khai tiếng Việt có dấu, cần quyết định chính sách chuẩn hóa dấu như phần tìm kiếm không phân biệt dấu ở dưới.

### 3.1. Tạo GIN index

GIN là loại chỉ mục phù hợp cho truy vấn containment trên tsvector:

~~~sql
CREATE INDEX catalog_items_search_vector_gin
ON catalog_items
USING GIN (search_vector);
~~~

GIN lưu quan hệ giữa lexeme và các vị trí xuất hiện trong tập vector. Khi truy vấn dùng search_vector @@ tsquery, PostgreSQL có thể tìm các hàng ứng viên bằng index thay vì đọc toàn bộ bảng.

GIN không lưu sẵn thứ tự xếp hạng. PostgreSQL vẫn phải tính ts_rank hoặc ts_rank_cd trên các hàng phù hợp rồi sắp xếp. Với bảng nhỏ, planner có thể chọn sequential scan vì chi phí thấp hơn; điều đó không có nghĩa index sai.

## 4. Thực hiện tìm kiếm toàn văn và xếp hạng

Truy vấn sau nhận từ khóa bằng tham số $1, tìm các hàng khớp và xếp hạng theo độ liên quan:

~~~sql
WITH query_input AS (
    SELECT websearch_to_tsquery('simple', $1) AS query
)
SELECT
    item.id,
    item.name,
    item.brand,
    item.category,
    ts_rank_cd(item.search_vector, query_input.query) AS relevance
FROM catalog_items AS item
CROSS JOIN query_input
WHERE item.active
  AND numnode(query_input.query) > 0
  AND item.search_vector @@ query_input.query
ORDER BY relevance DESC, item.id
LIMIT 20;
~~~

numnode đếm số node trong tsquery. Điều kiện này giúp bỏ qua query rỗng, ví dụ khi người dùng gửi chuỗi trống hoặc chỉ có nội dung bị loại theo cấu hình từ điển.

ts_rank_cd tính điểm dựa trên tần suất và độ gần nhau của các lexeme. Có thể dùng ts_rank nếu không cần tính độ gần vị trí. Điểm số không phải xác suất; hãy xem nó là giá trị tương đối để sắp xếp các kết quả trong cùng một chiến lược tìm kiếm.

### 4.1. Tìm cụm từ

Dùng phraseto_tsquery khi thứ tự từ có ý nghĩa:

~~~sql
SELECT
    id,
    name
FROM catalog_items
WHERE search_vector @@
      phraseto_tsquery('simple', $1);
~~~

Ví dụ người dùng tìm cụm tai nghe, kết quả cần chứa hai từ theo đúng thứ tự và khoảng cách phù hợp với phrase query. Hành vi chi tiết phụ thuộc tokenization và cấu hình từ điển.

### 4.2. Tìm bằng OR và loại trừ từ

websearch_to_tsquery hỗ trợ cú pháp quen thuộc:

~~~sql
SELECT
    id,
    name,
    ts_rank_cd(
        search_vector,
        websearch_to_tsquery('simple', $1)
    ) AS relevance
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', $1)
ORDER BY relevance DESC, id;
~~~

Ví dụ đầu vào:

- bluetooth tai nghe: tìm các từ theo mặc định AND.
- bluetooth OR loa: tìm một trong hai nhánh.
- "tai nghe": tìm cụm từ.
- bluetooth -co day: loại các tài liệu có từ bị loại.

Cần kiểm tra các query có nhiều từ phủ định hoặc query quá rộng. Không nên trả về toàn bộ danh mục chỉ vì điều kiện tìm kiếm rỗng hoặc chỉ chứa toán tử loại trừ.

### 4.3. Trọng số và hiển thị đoạn trích

Trọng số A/B/C/D cho phép tên sản phẩm ảnh hưởng đến thứ tự cao hơn mô tả. Có thể thay đổi trọng số trong ts_rank_cd:

~~~sql
SELECT
    id,
    name,
    ts_rank_cd(
        ARRAY[0.1, 0.2, 0.4, 1.0],
        search_vector,
        websearch_to_tsquery('simple', $1)
    ) AS relevance
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', $1)
ORDER BY relevance DESC, id;
~~~

Mảng trọng số theo thứ tự D, C, B, A. Giá trị càng cao thì lexeme có trọng số tương ứng đóng góp càng lớn vào rank. Hãy đo chất lượng bằng bộ truy vấn mẫu và kết quả mong muốn thay vì chọn trọng số theo cảm tính.

Có thể tạo đoạn trích có đánh dấu từ khớp bằng ts_headline:

~~~sql
SELECT
    id,
    ts_headline(
        'simple',
        coalesce(description, ''),
        websearch_to_tsquery('simple', $1),
        'StartSel=<mark>, StopSel=</mark>, MaxWords=25, MinWords=8'
    ) AS excerpt
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', $1);
~~~

ts_headline tạo nội dung hiển thị từ văn bản gốc. Nếu đưa kết quả vào HTML, hãy escape hoặc sanitize đúng cách; không xem đoạn trích là HTML đáng tin cậy chỉ vì marker được cấu hình trong SQL.

## 5. Tìm kiếm gần đúng với pg_trgm

Extension pg_trgm chia chuỗi thành các trigram, tức nhóm ba ký tự liên tiếp có bổ sung khoảng trắng biên theo thuật toán của extension. PostgreSQL so sánh các trigram chung giữa hai chuỗi để tính mức độ tương đồng.

Cài extension trong database cần tìm kiếm:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
~~~

Các hàm và toán tử thường dùng:

| Thành phần | Ý nghĩa |
|---|---|
| similarity(a, b) | Trả điểm tương đồng giữa hai chuỗi, từ 0 đến 1 |
| a % b | Kiểm tra similarity có vượt ngưỡng hiện hành hay không |
| word_similarity(a, b) | So chuỗi đầu với một đoạn liên tiếp trong chuỗi thứ hai |
| a <% b | Kiểm tra word similarity theo ngưỡng |
| strict_word_similarity(a, b) | So độ tương đồng theo ranh giới từ |
| a <<% b | Kiểm tra strict word similarity theo ngưỡng |
| a <-> b | Khoảng cách trigram, tương đương 1 trừ similarity |

Điểm similarity càng gần 1 thì hai chuỗi càng giống nhau. Ngưỡng mặc định của toán tử % thường là 0.3; có thể điều chỉnh bằng cấu hình pg_trgm.similarity_threshold cho session hoặc transaction.

### 5.1. Tìm tên gần giống

Tạo GIN index trên tên đã chuyển về chữ thường:

~~~sql
CREATE INDEX catalog_items_name_trgm_gin
ON catalog_items
USING GIN (lower(name) gin_trgm_ops);
~~~

Truy vấn:

~~~sql
SELECT
    id,
    name,
    similarity(lower(name), lower($1)) AS similarity_score
FROM catalog_items
WHERE active
  AND lower(name) % lower($1)
ORDER BY similarity_score DESC, id
LIMIT 10;
~~~

Nếu người dùng nhập sai một vài ký tự, các tên có nhiều trigram chung có thể xuất hiện trong kết quả. GIN index hỗ trợ lọc ứng viên bằng toán tử similarity; sau đó PostgreSQL tính điểm và sắp xếp.

Có thể điều chỉnh ngưỡng trong transaction:

~~~sql
BEGIN;

SET LOCAL pg_trgm.similarity_threshold = 0.25;

SELECT
    id,
    name,
    similarity(lower(name), lower($1)) AS score
FROM catalog_items
WHERE lower(name) % lower($1)
ORDER BY score DESC
LIMIT 10;

COMMIT;
~~~

Ngưỡng thấp hơn thường trả nhiều ứng viên hơn, nhưng cũng làm tăng kết quả không liên quan. Ngưỡng cao hơn giảm nhiễu nhưng có thể bỏ sót lỗi gõ. Nên chọn theo tập truy vấn thực tế, độ dài tên và yêu cầu trải nghiệm.

### 5.2. Tìm từ trong một phần tên dài

word_similarity phù hợp khi chuỗi người dùng nhập có thể tương đồng với một đoạn trong tên hoặc mô tả dài hơn:

~~~sql
SELECT
    id,
    name,
    word_similarity(lower($1), lower(name)) AS score
FROM catalog_items
WHERE lower($1) <% lower(name)
ORDER BY score DESC, id
LIMIT 10;
~~~

<% có hướng tham số: chuỗi bên trái được so với một extent trong chuỗi bên phải. Nếu đảo vị trí hai toán hạng, ý nghĩa có thể thay đổi.

strict_word_similarity so sánh theo ranh giới từ nghiêm ngặt hơn:

~~~sql
SELECT
    id,
    name,
    strict_word_similarity(lower($1), lower(name)) AS score
FROM catalog_items
WHERE lower($1) <<% lower(name)
ORDER BY score DESC, id
LIMIT 10;
~~~

Các toán tử này có ngưỡng riêng. Khi dùng trong ứng dụng, hãy cấu hình và kiểm thử ngưỡng nhất quán với cách xếp hạng.

### 5.3. Tìm top gần nhất bằng GiST

GIN phù hợp để lọc các hàng vượt ngưỡng. Nếu mục tiêu là lấy những chuỗi gần nhất theo distance, GiST có thể hỗ trợ K-nearest-neighbor ordering:

~~~sql
CREATE INDEX catalog_items_name_trgm_gist
ON catalog_items
USING GIST (lower(name) gist_trgm_ops);
~~~

Truy vấn top gần nhất:

~~~sql
SELECT
    id,
    name,
    lower(name) <-> lower($1) AS distance
FROM catalog_items
ORDER BY lower(name) <-> lower($1)
LIMIT 10;
~~~

Distance càng nhỏ thì chuỗi càng giống. GiST có thể hỗ trợ thứ tự KNN theo toán tử <->; hãy kiểm tra kế hoạch bằng EXPLAIN để xác nhận planner thực sự sử dụng index.

Không nhất thiết phải tạo cả GIN và GiST cho mọi bảng. Chọn theo workload: truy vấn lọc similarity theo ngưỡng, truy vấn top gần nhất, tần suất ghi và dung lượng index.

## 6. Tìm kiếm không phân biệt chữ hoa và dấu

lower() giúp chuẩn hóa chữ hoa/thường cho ví dụ fuzzy search. Tuy nhiên, nó không tự bỏ dấu tiếng Việt. Ví dụ ca phe và cà phê có thể có các trigram khác nhau.

Extension unaccent cung cấp hàm bỏ dấu:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent;
~~~

Kiểm tra:

~~~sql
SELECT
    unaccent('Cà phê rang xay') AS normalized_text;
~~~

Một điểm quan trọng về index: unaccent là hàm phụ thuộc từ điển và không được xem là immutable trong cấu hình thông thường. PostgreSQL yêu cầu biểu thức index phải có hàm immutable. Vì vậy, không thể tùy tiện tạo index trực tiếp trên unaccent(name) như thể hàm luôn bất biến.

Có hai hướng phổ biến:

1. **Lưu trường tìm kiếm đã chuẩn hóa:** ứng dụng hoặc trigger ghi name_search bằng cách chuyển chữ thường và bỏ dấu khi INSERT/UPDATE. Tạo trigram index trên cột lưu sẵn đó.
2. **Tạo wrapper immutable có kiểm soát:** chỉ dùng khi chấp nhận cam kết từ điển unaccent không đổi trong vòng đời index. Nếu thay từ điển, cần cập nhật dữ liệu và rebuild index. Không khai báo immutable chỉ để vượt qua lỗi tạo index mà không quản lý hệ quả.

Ví dụ hướng lưu cột chuẩn hóa bằng trigger:

~~~sql
ALTER TABLE catalog_items
ADD COLUMN name_search text NOT NULL DEFAULT '';

CREATE OR REPLACE FUNCTION catalog_items_set_name_search()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.name_search :=
        lower(unaccent('public.unaccent'::regdictionary, coalesce(NEW.name, '')));
    RETURN NEW;
END;
$$;

CREATE TRIGGER catalog_items_name_search_trg
BEFORE INSERT OR UPDATE OF name
ON catalog_items
FOR EACH ROW
EXECUTE FUNCTION catalog_items_set_name_search();
~~~

Ví dụ giả định extension unaccent được cài trong schema public; nếu cài ở schema khác, cần đổi tên dictionary cho đúng. Sau khi thêm trigger, cần backfill các hàng đã tồn tại:

~~~sql
UPDATE catalog_items
SET name = name;
~~~

Câu lệnh trên kích hoạt trigger cho các hàng hiện tại vì cột name được cập nhật. Với bảng lớn, hãy lập kế hoạch batch và kiểm soát tải thay vì cập nhật toàn bảng trong giờ cao điểm.

Tạo index trên trường chuẩn hóa:

~~~sql
CREATE INDEX catalog_items_name_search_trgm_gin
ON catalog_items
USING GIN (name_search gin_trgm_ops);
~~~

Tìm kiếm:

~~~sql
SELECT
    id,
    name,
    similarity(name_search, lower(unaccent($1))) AS score
FROM catalog_items
WHERE name_search % lower(unaccent($1))
ORDER BY score DESC, id
LIMIT 10;
~~~

Ở ví dụ này, biểu thức chuẩn hóa phía tham số được tính khi truy vấn, còn cột đã được chuẩn hóa và đánh index. Nếu dùng unaccent ở phía tham số, vẫn có thể dùng index trên cột name_search.

Nếu muốn full-text search cũng không phân biệt dấu, có thể duy trì các trường văn bản đã chuẩn hóa rồi tạo tsvector từ chúng. Generated column không nên gọi trực tiếp một hàm unaccent không immutable. Có thể dùng trigger duy trì vector hoặc lưu search text đã chuẩn hóa rồi tạo generated vector từ trường đó. Cần bảo đảm dữ liệu chuẩn hóa và vector được cập nhật cùng transaction với dữ liệu gốc.

## 7. Kết hợp full-text và fuzzy search

Danh mục thường cần kết quả tốt cho cả truy vấn đúng từ và lỗi gõ. Một cách triển khai là tạo hai tập ứng viên:

- Full-text candidates: các hàng khớp search_vector.
- Fuzzy candidates: các hàng có tên tương đồng với chuỗi tìm kiếm.

Sau đó hợp nhất theo ID và tính điểm kết hợp. Ví dụ sau dùng điểm full-text đã chuẩn hóa và điểm trigram:

~~~sql
WITH query_input AS (
    SELECT
        websearch_to_tsquery('simple', $1) AS query,
        lower($1) AS needle
),
full_text_matches AS (
    SELECT
        item.id,
        ts_rank_cd(item.search_vector, q.query) AS text_rank
    FROM catalog_items AS item
    CROSS JOIN query_input AS q
    WHERE item.active
      AND numnode(q.query) > 0
      AND item.search_vector @@ q.query
),
fuzzy_matches AS (
    SELECT
        item.id,
        similarity(lower(item.name), q.needle) AS trigram_score
    FROM catalog_items AS item
    CROSS JOIN query_input AS q
    WHERE item.active
      AND lower(item.name) % q.needle
),
candidate_scores AS (
    SELECT
        id,
        0.7 * (text_rank / (1.0 + text_rank)) AS score
    FROM full_text_matches

    UNION ALL

    SELECT
        id,
        0.3 * trigram_score AS score
    FROM fuzzy_matches
),
combined AS (
    SELECT
        id,
        sum(score) AS relevance
    FROM candidate_scores
    GROUP BY id
)
SELECT
    item.id,
    item.name,
    item.brand,
    item.category,
    combined.relevance
FROM combined
JOIN catalog_items AS item
  ON item.id = combined.id
WHERE item.active
ORDER BY combined.relevance DESC, item.id
LIMIT 20;
~~~

Các hệ số 0.7 và 0.3 chỉ là giá trị minh họa. Full-text rank và trigram similarity có thang điểm khác nhau; công thức chuẩn hóa giúp dễ kết hợp hơn nhưng vẫn phải đánh giá bằng dữ liệu thật. Nếu một hàng khớp cả hai kỹ thuật, điểm được cộng lại để phản ánh hai tín hiệu cùng ủng hộ kết quả.

Trong hệ thống thực tế, có thể bổ sung tín hiệu:

- Tên khớp chính xác.
- Tên bắt đầu bằng chuỗi truy vấn.
- Thương hiệu hoặc loại khớp.
- Mục đang hoạt động và còn hàng.
- Mức độ phổ biến hoặc độ mới.
- Quyền truy cập và tenant của người dùng.

Điều kiện bảo mật và phạm vi dữ liệu phải được áp dụng trước khi trả kết quả. Không để một fuzzy candidate từ tenant khác xuất hiện chỉ vì điểm similarity cao.

## 8. Tối ưu hiệu năng và kế hoạch truy vấn

Tìm kiếm cần được đánh giá bằng kích thước dữ liệu và truy vấn gần với production.

### 8.1. Dùng EXPLAIN

Kiểm tra kế hoạch:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name
FROM catalog_items
WHERE search_vector @@
      websearch_to_tsquery('simple', 'bluetooth tai nghe');
~~~

Với fuzzy search:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name
FROM catalog_items
WHERE lower(name) % lower('bluetooh');
~~~

Đọc các thông tin:

- Seq Scan: đọc tuần tự bảng; có thể hợp lý với bảng nhỏ hoặc điều kiện chọn nhiều hàng.
- Bitmap Index Scan: lấy các vị trí hàng từ index, thường gặp với GIN.
- Bitmap Heap Scan: đọc heap theo các block tìm được.
- Index Scan: đọc hàng qua index.
- Rows Removed by Filter: số hàng bị loại sau điều kiện.
- Buffers: số buffer được đọc hoặc tìm thấy trong cache.
- Execution Time: thời gian thực thi trong lần đo đó.

Không kết luận hiệu năng chỉ từ một lần chạy. Cache nóng/lạnh, statistics, độ chọn lọc và số lượng dữ liệu ảnh hưởng lớn đến kế hoạch.

### 8.2. Giữ statistics cập nhật

Sau khi import nhiều dữ liệu hoặc thay đổi đáng kể phân bố dữ liệu, chạy ANALYZE hoặc để autovacuum/analyze thực hiện theo cấu hình:

~~~sql
ANALYZE catalog_items;
~~~

Statistics giúp planner ước lượng số hàng phù hợp và chọn kế hoạch phù hợp. Nếu bảng tăng trưởng nhanh nhưng statistics cũ, planner có thể chọn sequential scan hoặc index scan không tối ưu.

### 8.3. Chi phí GIN và GiST

GIN thường phù hợp với tìm kiếm nhiều token hoặc trigram threshold. Nó có thể chiếm dung lượng đáng kể và tăng chi phí ghi vì một hàng cập nhật có thể làm thay đổi nhiều entry index. fastupdate và pending list ảnh hưởng cách GIN xử lý ghi; cần theo dõi vacuum, latency và dung lượng.

GiST có lợi thế với KNN distance ordering trong pg_trgm, nhưng hiệu quả phụ thuộc phân bố dữ liệu và cấu hình index. Đo trên workload thực tế trước khi chọn.

Không tạo index cho mọi trường chỉ vì có thể tìm kiếm trường đó. Mỗi index làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE. Xác định các trường người dùng thật sự tìm kiếm, kiểu truy vấn và tần suất sử dụng.

### 8.4. Giới hạn kết quả và phân trang

Luôn đặt giới hạn kết quả phù hợp. Nếu danh mục lớn, tránh trả hàng nghìn kết quả cho một truy vấn ngắn. Dùng ORDER BY relevance DESC, id để có thứ tự ổn định khi nhiều hàng cùng điểm.

Với phân trang sâu, OFFSET lớn có thể tốn chi phí vì database vẫn phải bỏ qua nhiều hàng đã sắp xếp. Có thể dùng keyset pagination dựa trên điểm và ID, nhưng cần đảm bảo điểm được tính nhất quán giữa các trang. Nếu dữ liệu thay đổi thường xuyên, cân nhắc snapshot hoặc cursor theo transaction khi yêu cầu trải nghiệm cần kết quả nhất quán.

### 8.5. Xử lý truy vấn quá ngắn hoặc quá rộng

Trigram ít hữu ích với chuỗi một hoặc hai ký tự vì số lượng trigram rất nhỏ. Full-text search với từ quá phổ biến có thể trả về phần lớn danh mục. Hãy đặt chính sách:

- Không thực hiện fuzzy search cho input quá ngắn.
- Giới hạn số từ hoặc độ dài query.
- Không tìm kiếm khi query rỗng.
- Giới hạn số ứng viên từ mỗi phương pháp.
- Đặt statement timeout phù hợp cho endpoint tìm kiếm.
- Theo dõi các truy vấn có thời gian hoặc số hàng quét bất thường.

Không cắt ngắn query theo cách làm thay đổi ý nghĩa mà không thông báo hoặc không có quy tắc rõ ràng.

## 9. Thiết kế API tìm kiếm cho danh mục

Một API tìm kiếm có thể nhận:

~~~json
{
  "query": "tai nghe bluetooh",
  "category": "audio",
  "activeOnly": true,
  "limit": 20,
  "cursor": null
}
~~~

Backend cần:

1. Validate độ dài và định dạng query.
2. Xác định tenant và phạm vi quyền từ danh tính đã xác thực.
3. Chuẩn hóa query theo chính sách dấu và chữ hoa/thường.
4. Chọn full-text, fuzzy hoặc kết hợp tùy độ dài và loại truy vấn.
5. Áp dụng filter category, active, tenant và quyền truy cập.
6. Tính điểm, sắp xếp ổn định và giới hạn kết quả.
7. Trả kết quả cùng thông tin phân trang cần thiết.

Không nhận tenant_id hoặc quyền lọc dữ liệu nhạy cảm từ client như một nguồn tin cậy. Backend phải xác định phạm vi truy cập dựa trên danh tính đã xác thực.

Nếu API hỗ trợ chế độ tìm chính xác và tìm gần đúng, hãy phân biệt rõ để frontend có thể hiển thị gợi ý phù hợp. Có thể trả thêm matchType như full_text, fuzzy hoặc exact, nhưng không tiết lộ thông tin nội bộ về dữ liệu mà người dùng không có quyền xem.

## 10. Kiểm thử chất lượng tìm kiếm

Tìm kiếm là tính năng có yếu tố đánh giá chất lượng, không chỉ là kiểm tra SQL chạy không lỗi. Hãy chuẩn bị tập query đại diện và danh sách kết quả mong muốn.

Một ma trận kiểm thử có thể gồm:

| Trường hợp | Ví dụ đầu vào | Kết quả cần xác nhận |
|---|---|---|
| Khớp chính xác tên | Tai nghe Bluetooth X100 | Mục chính xác đứng đầu |
| Nhiều từ trong mô tả | pin lau bluetooth | Mục có các từ trong mô tả xuất hiện |
| Cụm từ | tai nghe | Kết quả thỏa phrase query |
| OR | bluetooth OR loa | Kết quả khớp một trong các nhánh |
| Loại trừ | bluetooth -co day | Hàng có từ bị loại không xuất hiện |
| Lỗi gõ | bluetooh | Tên gần giống được gợi ý |
| Sai một phần tên | tai nghe X10 | Kết quả gần đúng được xếp hạng hợp lý |
| Khác dấu | ca phe và cà phê | Đúng chính sách chuẩn hóa dấu |
| Chuỗi ngắn | a, xy | Không gây quá nhiều kết quả nhiễu |
| Query rỗng | chuỗi rỗng | Trả rỗng hoặc yêu cầu nhập từ khóa |
| Không có kết quả | Từ không tồn tại | Trả danh sách rỗng, không lỗi |
| Quyền/tenant | Query trùng dữ liệu tenant khác | Không rò dữ liệu ngoài phạm vi |

Đánh giá bằng các chỉ số như Precision@K (tỷ lệ kết quả đúng trong top K) và Recall@K (tỷ lệ mục liên quan tìm được trong top K) nếu danh mục có bộ nhãn đánh giá. Có thể thêm MRR hoặc NDCG khi thứ tự kết quả quan trọng.

Khi thay đổi trọng số, ngưỡng trigram hoặc cấu hình text search, chạy lại cùng tập query để so sánh. Không tối ưu theo một ví dụ duy nhất.

## 11. Các lỗi thường gặp

- Dùng to_tsquery với văn bản tự do: ký tự đặc biệt hoặc cú pháp không hợp lệ có thể gây lỗi; dùng websearch_to_tsquery hoặc validate grammar.
- Tạo vector và query bằng cấu hình khác nhau: từ được chuẩn hóa không giống nhau nên không khớp.
- Không có GIN index: truy vấn @@ có thể phải quét toàn bộ bảng khi dữ liệu lớn.
- Tưởng GIN tự sắp xếp theo rank: GIN lọc ứng viên, ranking vẫn cần tính và sort.
- Dùng trigram cho chuỗi quá ngắn: ít trigram khiến kết quả không ổn định hoặc quá rộng.
- Đặt ngưỡng fuzzy quá thấp: tăng số kết quả không liên quan.
- Chỉ lower() nhưng kỳ vọng bỏ dấu: chữ thường không đồng nghĩa không dấu.
- Đưa unaccent vào expression index mà không xét volatility: PostgreSQL yêu cầu hàm trong index expression phải immutable.
- Không cập nhật vector hoặc trường chuẩn hóa: dữ liệu mới có thể không được tìm thấy nếu trigger/app không đồng bộ.
- Không ANALYZE sau import lớn: planner có thể chọn kế hoạch không phù hợp.
- Trả quá nhiều hàng: làm tăng latency, tải database và chi phí truyền dữ liệu.
- Bỏ qua filter bảo mật: fuzzy search có thể làm lộ tên hoặc nội dung của hàng ngoài phạm vi truy cập.

## 12. Quy trình triển khai từng bước

Một lộ trình triển khai an toàn cho danh mục:

1. Xác định trường cần tìm, ngôn ngữ, chính sách dấu và yêu cầu autocomplete/fuzzy.
2. Chọn cấu hình text search và kiểm tra bằng ts_debug.
3. Thiết kế tsvector có trọng số cho tên, thương hiệu, loại và mô tả.
4. Tạo GIN index và đo truy vấn full-text.
5. Cài pg_trgm, tạo GIN hoặc GiST index theo kiểu fuzzy query.
6. Nếu cần không phân biệt dấu, thiết kế trường chuẩn hóa và cơ chế cập nhật nhất quán.
7. Viết truy vấn kết hợp, giới hạn ứng viên và xếp hạng.
8. Áp dụng filter tenant, quyền, category và trạng thái trước khi trả dữ liệu.
9. Kiểm thử query đúng, query sai, query rỗng, chuỗi ngắn và trường hợp không có kết quả.
10. Đo EXPLAIN (ANALYZE, BUFFERS) trên dữ liệu gần production.
11. Theo dõi latency, số hàng trả về, cache, dung lượng index và chi phí ghi.
12. Điều chỉnh trọng số/ngưỡng dựa trên tập query đánh giá và triển khai có thể rollback.

Full-text search và trigram là nền tảng mạnh cho tìm kiếm danh mục trong PostgreSQL. Full-text search hiểu từ và cú pháp truy vấn, còn trigram giúp tìm các tên gần giống khi người dùng gõ sai. Khi thiết kế vector, chuẩn hóa dấu, index, ranking và bộ lọc quyền cùng nhau, hệ thống có thể trả kết quả phù hợp mà vẫn giữ được hiệu năng và ranh giới dữ liệu.

