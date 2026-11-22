# Oracle Text: chỉ mục văn bản, lexer và đồng bộ chỉ mục

Oracle Text là công nghệ tìm kiếm văn bản trong Oracle Database. Thay vì chỉ so sánh giá trị bằng toán tử SQL thông thường, Oracle Text phân tích nội dung thành token, xây dựng inverted index và cung cấp ngôn ngữ truy vấn để tìm từ, cụm từ, quan hệ gần nhau, biến thể từ và vùng nội dung trong tài liệu.

Một truy vấn Oracle Text điển hình dùng hàm CONTAINS:

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE CONTAINS(content, 'oracle AND database', 1) > 0
ORDER BY relevance DESC;
~~~

Để vận hành đúng Oracle Text, cần hiểu cả ba phần:

- **Index architecture**: datastore lấy nội dung từ đâu, filter chuyển đổi định dạng nào, lexer tách token ra sao, wordlist và stoplist điều chỉnh tìm kiếm thế nào, section group mô tả vùng tài liệu nào.
- **Query behavior**: CONTAINS, SCORE, các toán tử tìm kiếm, structured filtering và cách kết quả được xếp hạng.
- **Index synchronization**: thay đổi DML được đưa vào hàng đợi pending ra sao, khi nào cần SYNC_INDEX, tối ưu index và giám sát lỗi indexing.

Oracle Text phù hợp với tìm kiếm tài liệu, nội dung CLOB, mô tả sản phẩm, hợp đồng, hồ sơ và các kho văn bản cần truy vấn theo từ khóa. Nó không tự động thay thế mọi hệ thống search chuyên dụng; lựa chọn phụ thuộc yêu cầu ranking, độ trễ cập nhật, phân tích ngôn ngữ, dung lượng và tích hợp ứng dụng.

## 1. Oracle Text hoạt động như thế nào?

Oracle Text xây dựng một inverted index. Thay vì lưu một danh sách từ cho mỗi lần tìm kiếm rồi quét toàn bộ bảng, quá trình index hóa lập ánh xạ từ token sang các document/row chứa token đó.

Ví dụ ba tài liệu:

| Document | Nội dung |
| --- | --- |
| 101 | Oracle Database supports text search |
| 102 | Oracle Text creates a text index |
| 103 | Database administration and backup |

Sau khi tokenization, inverted index khái niệm có thể là:

| Token | Document IDs |
| --- | --- |
| oracle | 101, 102 |
| database | 101, 103 |
| text | 102 |
| index | 102 |
| backup | 103 |

Khi tìm oracle AND database, Oracle Text kết hợp danh sách posting của hai token để xác định document 101.

Đây là mô hình khái niệm. Cấu trúc lưu trữ thật của Oracle Text phức tạp hơn, có các bảng index nội bộ, token metadata, posting lists và dữ liệu hỗ trợ scoring/optimization.

### 1.1. Luồng index hóa

~~~text
Bảng ứng dụng
     |
     v
Datastore
     |
     v
Filter (nếu nội dung là tài liệu nhị phân)
     |
     v
Lexer
     |
     +--> tokenization
     +--> case/accent handling
     +--> language rules
     |
     v
Stoplist / Wordlist / Section Group
     |
     v
Oracle Text inverted index
     |
     v
CONTAINS / CATSEARCH / MATCHES
~~~

Các thành phần có vai trò khác nhau:
- Datastore xác định cách lấy nội dung.
- Filter trích text từ định dạng như PDF, Word hoặc HTML khi được cấu hình.
- Lexer phân tích text thành token và áp dụng quy tắc ngôn ngữ.
- Stoplist loại từ không cần index/search theo chính sách.
- Wordlist điều khiển fuzzy, stemming, prefix và substring behavior.
- Section group xác định title, heading, body hoặc vùng XML/HTML.
- Storage preference điều khiển một số đặc tính lưu trữ index.

### 1.2. Inverted index khác B-tree index

B-tree index phù hợp với equality/range lookup trên giá trị có cấu trúc, ví dụ customer_id hoặc created_at. Oracle Text index phù hợp với tìm kiếm token và quan hệ giữa từ.

Một truy vấn có thể kết hợp cả hai:

~~~sql
SELECT document_id, SCORE(1)
FROM documents
WHERE status = 'PUBLISHED'
  AND CONTAINS(content, 'oracle AND recovery', 1) > 0;
~~~

Predicate status có thể dùng B-tree index thông thường; CONTAINS dùng Oracle Text index. Optimizer quyết định access path theo thống kê và chi phí.

### 1.3. Các loại index chính

Oracle Text có một số index type thường gặp:

| Index type | Mục đích điển hình | Ghi chú |
| --- | --- | --- |
| CONTEXT | Tìm kiếm toàn văn trên tài liệu/text lớn | Có quy trình đồng bộ index; phù hợp document search |
| CTXCAT | Catalog search kết hợp text với structured attributes | Có index set và semantics cập nhật riêng |
| CTXRULE | Lưu rule/query để phân loại văn bản mới | Dùng MATCHES để tìm rule phù hợp |

Chọn index type theo workload. Không thay CONTEXT bằng CTXCAT chỉ vì tên nghe phù hợp với catalog; kiểm tra giới hạn kiểu dữ liệu, query interface, update behavior và tài liệu phiên bản.

## 2. Chuẩn bị schema và dữ liệu

Ví dụ bảng tài liệu có một cột CLOB:

~~~sql
CREATE TABLE documents (
    document_id NUMBER
        CONSTRAINT documents_pk PRIMARY KEY,
    title       VARCHAR2(500),
    content     CLOB,
    status      VARCHAR2(20),
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

Nội dung CLOB có thể là plain text, HTML hoặc văn bản đã trích xuất từ hệ thống khác. Oracle Text cần biết cách diễn giải nội dung.

### 2.1. Kiểm tra kiểu dữ liệu

Oracle Text thường được dùng với VARCHAR2, CLOB và các loại dữ liệu tài liệu được hỗ trợ qua datastore/filter. Khả năng cụ thể tùy index type, datastore và release.

Kiểm tra metadata:

~~~sql
SELECT column_name,
       data_type,
       data_length,
       nullable
FROM user_tab_columns
WHERE table_name = 'DOCUMENTS'
ORDER BY column_id;
~~~

Nếu dữ liệu gốc nằm trong BLOB, phải xác định định dạng tài liệu và cách filter trích xuất text. Không thể giả định BLOB bytes là văn bản UTF-8 có thể index trực tiếp.

### 2.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO documents(document_id, title, content, status)
VALUES (
    101,
    'Oracle database overview',
    'Oracle Database provides indexing and text search capabilities.',
    'PUBLISHED'
);

INSERT INTO documents(document_id, title, content, status)
VALUES (
    102,
    'Text indexing guide',
    'Oracle Text uses a lexer to identify tokens in documents.',
    'PUBLISHED'
);

COMMIT;
~~~

Commit dữ liệu trước khi đồng bộ CONTEXT index theo cơ chế manual. Nếu cấu hình SYNC ON COMMIT, Oracle Text có thể đồng bộ theo commit semantics đã chọn.

## 3. Tạo CONTEXT index cơ bản

CONTEXT là lựa chọn phổ biến để tìm kiếm toàn văn trên CLOB hoặc nội dung tài liệu.

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT;
~~~

Sau khi tạo index, kiểm tra index:

~~~sql
SELECT index_name,
       index_type,
       status
FROM user_indexes
WHERE table_name = 'DOCUMENTS';
~~~

Tìm kiếm:

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE CONTAINS(content, 'oracle', 1) > 0
ORDER BY relevance DESC;
~~~

CONTAINS trả về giá trị dương khi document khớp query expression; giá trị 0 biểu thị không khớp trong điều kiện truy vấn. SCORE(label) lấy điểm liên quan ứng với label đã truyền vào CONTAINS. Label là số nguyên dùng để liên kết CONTAINS và SCORE trong cùng câu SQL.

### 3.1. Một câu truy vấn có nhiều CONTAINS

~~~sql
SELECT document_id,
       SCORE(1) AS title_score,
       SCORE(2) AS content_score
FROM documents
WHERE CONTAINS(title, 'oracle', 1) > 0
   OR CONTAINS(content, 'recovery', 2) > 0;
~~~

Mỗi CONTAINS dùng label riêng nếu cần lấy SCORE tương ứng. Label phải nhất quán giữa CONTAINS và SCORE.

### 3.2. Tìm kiếm cùng structured predicate

~~~sql
SELECT document_id,
       title,
       SCORE(1) AS relevance
FROM documents
WHERE status = 'PUBLISHED'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND CONTAINS(content, 'oracle AND text', 1) > 0
ORDER BY relevance DESC;
~~~

Structured predicate giúp giới hạn tập kết quả theo trạng thái và thời gian. Oracle có thể dùng B-tree index cho các cột đó tùy plan.

### 3.3. Không dùng LIKE như thay thế đầy đủ

~~~sql
SELECT *
FROM documents
WHERE content LIKE '%oracle%';
~~~

LIKE có thể phù hợp cho pattern đơn giản, nhưng thường không cung cấp tokenizer, stemming, fuzzy, section search hoặc relevance ranking như Oracle Text. Với CLOB lớn, wildcard đầu chuỗi cũng thường không có access path hiệu quả như Oracle Text.

## 4. Lexer — thành phần quyết định tokenization

Lexer phân tách nội dung thành token có thể index. Quy tắc lexer ảnh hưởng trực tiếp đến kết quả tìm kiếm.

Ví dụ chuỗi:

~~~text
Oracle-Database, text_search; version 26ai.
~~~

Lexer phải quyết định:
- Dấu gạch nối có tách hai token không?
- Underscore có được giữ trong token không?
- Chữ hoa/chữ thường có được phân biệt không?
- Dấu tiếng Việt có được chuẩn hóa không?
- Số và ký tự chữ được xử lý ra sao?
- Dấu câu nào được xem là separator/join character?

Nếu lexer thay đổi, tập token trong index có thể thay đổi. Vì vậy thay lexer preference thường cần đánh giá rebuild hoặc re-create index theo quy trình Oracle Text.

### 4.1. BASIC_LEXER

BASIC_LEXER là lexer phổ biến cho ngôn ngữ dựa trên Latin và các quy tắc cơ bản.

Tạo preference:

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE(
        'DOCS_LEXER',
        'BASIC_LEXER'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_LEXER',
        'MIXED_CASE',
        'NO'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_LEXER',
        'BASE_LETTER',
        'YES'
    );
END;
/
~~~

Ý nghĩa:
- MIXED_CASE=NO thường làm tìm kiếm không phân biệt chữ hoa/chữ thường.
- BASE_LETTER=YES cho phép chuẩn hóa một số ký tự có dấu về base letter theo quy tắc lexer.

BASE_LETTER có thể hữu ích cho tìm kiếm không dấu, nhưng cần kiểm tra ngôn ngữ. Trong tiếng Việt, dấu có thể phân biệt từ và nghĩa. Bỏ dấu làm tăng recall nhưng cũng có thể tăng false positives. Chọn theo yêu cầu sản phẩm, không bật chỉ vì dữ liệu có dấu.

### 4.2. PRINTJOINS và SKIPJOINS

BASIC_LEXER có các thuộc tính điều khiển ký tự nối từ. Ví dụ, dấu gạch nối có thể được coi là:
- Ký tự nối nằm bên trong token.
- Dấu phân tách tạo hai token.
- Ký tự bị bỏ qua trong tokenization.

Cấu hình phải dựa trên dữ liệu thực tế như:
- Mã sản phẩm.
- Email.
- Tên file.
- Số hợp đồng.
- Từ ghép có dấu gạch nối.
- Mã định danh chứa underscore.

Không thay đổi PRINTJOINS/SKIPJOINS mà chưa thử query regression, vì thay đổi này có thể làm một truy vấn cũ match thêm hoặc mất kết quả.

### 4.3. MULTI_LEXER

MULTI_LEXER dùng khi một tập dữ liệu chứa nhiều ngôn ngữ và mỗi document có thể khai báo language. Nó chọn lexer theo giá trị language column được cấu hình.

Mô hình khái niệm:
- Cột lang chứa mã ngôn ngữ.
- Preference MULTI_LEXER ánh xạ language code tới lexer preference.
- Document được token hóa bằng lexer tương ứng.

Ví dụ cấu hình chi tiết phụ thuộc các language mapping được Oracle hỗ trợ và cách lưu language code. Hãy kiểm tra tên language và thuộc tính của release đang chạy; không giả định mọi mã ISO đều tự động có lexer tương ứng.

### 4.4. AUTO_LEXER và WORLD_LEXER

Các lexer tự động/ngôn ngữ rộng có thể hữu ích khi nguồn dữ liệu đa ngôn ngữ hoặc không có metadata language đáng tin cậy. Chúng có chi phí và behavior riêng.

Trước khi chọn:
- Kiểm tra các ngôn ngữ được hỗ trợ.
- Đo chất lượng tokenization.
- Kiểm tra stemming/fuzzy behavior.
- Đánh giá CPU và thời gian index.
- So sánh kết quả với BASIC_LEXER hoặc MULTI_LEXER.
- Kiểm tra dữ liệu có trộn nhiều ngôn ngữ trong cùng document không.

### 4.5. Kiểm thử lexer

Tạo bộ test với:
- Chữ hoa/chữ thường.
- Dấu tiếng Việt.
- Tên riêng.
- Từ có dấu gạch nối.
- Email/URL.
- Mã sản phẩm.
- Số có dấu chấm/phẩy.
- Từ ghép và ký tự Unicode.
- Nội dung HTML/XML.
- Các ngôn ngữ khác nhau.

Dùng CTX_DOC hoặc truy vấn Oracle Text phù hợp để quan sát tokenization nếu cần. Kết quả phải được so với kỳ vọng nghiệp vụ, không chỉ nhìn preference đã tạo thành công.

## 5. Stoplist — loại bỏ từ không cần index

Stoplist chứa các từ Oracle Text bỏ qua khi index hoặc query theo cấu hình. Ví dụ tiếng Anh thường có các từ chức năng như "the", "and", "of". Tuy nhiên, stopword có thể quan trọng trong một số domain hoặc cụm từ.

### 5.1. Tạo BASIC_STOPLIST

~~~sql
BEGIN
    CTX_DDL.CREATE_STOPLIST(
        'DOCS_STOPLIST',
        'BASIC_STOPLIST'
    );

    CTX_DDL.ADD_STOPWORD(
        'DOCS_STOPLIST',
        'the'
    );

    CTX_DDL.ADD_STOPWORD(
        'DOCS_STOPLIST',
        'and'
    );
END;
/
~~~

Gắn stoplist vào CONTEXT index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'STOPLIST DOCS_STOPLIST'
);
~~~

Nếu index đã tồn tại, không tạo index thứ hai cùng tên. Cấu hình preference cần được lên kế hoạch trước khi create/recreate.

### 5.2. Stopword có ảnh hưởng tới search semantics

Nếu từ "and" bị stoplist loại bỏ, truy vấn AND là toán tử logic trong query grammar, không phải từ văn bản. Các từ chức năng trong tài liệu có thể không được lưu như token bình thường.

Không thêm stopword chỉ để giảm kích thước index. Việc loại từ có thể làm một số cụm từ hoặc truy vấn chính xác không hoạt động như mong đợi.

### 5.3. Stoplist theo ngôn ngữ

Dữ liệu đa ngôn ngữ cần stoplist phù hợp. Không áp dụng danh sách tiếng Anh cho tài liệu tiếng Việt rồi kỳ vọng chất lượng tìm kiếm tốt. Kiểm tra cách lexer nhận diện từ và các từ cần giữ trong domain.

## 6. Wordlist — fuzzy, stemming, prefix và substring

Wordlist điều khiển các tính năng mở rộng truy vấn.

### 6.1. BASIC_WORDLIST

Ví dụ:

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE(
        'DOCS_WORDLIST',
        'BASIC_WORDLIST'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_WORDLIST',
        'PREFIX_INDEX',
        'YES'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_WORDLIST',
        'PREFIX_MIN_LENGTH',
        '2'
    );

    CTX_DDL.SET_ATTRIBUTE(
        'DOCS_WORDLIST',
        'PREFIX_MAX_LENGTH',
        '5'
    );
END;
/
~~~

Gắn vào index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'WORDLIST DOCS_WORDLIST'
);
~~~

Đây là ví dụ riêng cho wordlist; khi dùng nhiều preference, kết hợp chúng trong một PARAMETERS string.

### 6.2. Prefix indexing

Prefix index hỗ trợ tìm kiếm từ bắt đầu bằng một chuỗi. Ví dụ truy vấn prefix có thể tìm database, databases hoặc database-related token theo cú pháp wildcard Oracle Text được hỗ trợ.

Prefix index làm tăng kích thước index và thời gian index hóa. Chọn min/max prefix length theo query pattern thực tế.

### 6.3. Substring indexing

Substring index hỗ trợ một số kiểu tìm kiếm chuỗi con ở giữa token. Nó có thể hữu ích với mã sản phẩm hoặc thuật ngữ cần partial matching, nhưng làm tăng storage và maintenance cost đáng kể.

Không bật substring indexing cho mọi corpus lớn nếu workload chỉ cần tìm từ đầy đủ.

### 6.4. Stemming

Stemming tìm các biến thể hình thái của một từ theo ngôn ngữ, ví dụ một số dạng số ít/số nhiều hoặc biến thể động từ trong tiếng Anh.

Stemming phụ thuộc language support. Không giả định stemming tiếng Anh hoạt động tương tự với tiếng Việt. Kiểm tra tài liệu Oracle Text của release và chạy test trên từ vựng domain.

### 6.5. Fuzzy matching

Fuzzy matching giúp tìm các từ gần giống về mặt chữ viết để chịu lỗi chính tả hoặc biến thể nhỏ. Nó hữu ích với tên riêng hoặc truy vấn người dùng nhập tự do, nhưng có thể tạo nhiều kết quả không liên quan.

Fuzzy behavior có thể được điều khiển bởi wordlist preference và query operator. Đặt threshold theo chất lượng dữ liệu; không mặc định fuzzy là tìm kiếm đồng nghĩa.

## 7. Datastore và filter

Datastore cho Oracle Text biết nơi lấy nội dung để index. Filter trích xuất text từ một số định dạng tài liệu.

### 7.1. DIRECT_DATASTORE

DIRECT_DATASTORE thường dùng khi text đã nằm trong cột của bảng, ví dụ CLOB/VARCHAR2. Đây là lựa chọn mặc định cho bảng lưu nội dung trực tiếp.

### 7.2. MULTI_COLUMN_DATASTORE

MULTI_COLUMN_DATASTORE kết hợp nội dung từ nhiều cột thành một document để index.

Ví dụ tài liệu có:
- title
- abstract
- body

Có thể tạo preference để ghép các cột vào một document, rồi dùng section group để tìm theo vùng title/body nếu cấu hình phù hợp.

Lợi ích:
- Một index phục vụ nhiều trường text.
- Có thể tìm kiếm toàn document.
- Có thể giữ ngữ nghĩa field/section cho query.

Cần xác định cách xử lý NULL, delimiter và section boundary. Không ghép các giá trị mà không có ranh giới vì token ở cuối cột này có thể dính với token đầu cột khác trong một số trường hợp.

### 7.3. FILE_DATASTORE

FILE_DATASTORE dùng khi bảng lưu thông tin tham chiếu tới file bên ngoài, thường qua directory object và tên file. Oracle Text đọc file từ filesystem theo cấu hình.

Cần:
- Oracle DIRECTORY object.
- Quyền READ phù hợp.
- File tồn tại và database server process truy cập được.
- File path được kiểm soát.
- Chính sách bảo mật và giới hạn kích thước.
- Quy trình xử lý file đã bị xóa hoặc di chuyển.

Đường dẫn trên máy ứng dụng không tự động là đường dẫn trên database server.

### 7.4. USER_DATASTORE

USER_DATASTORE cho phép ứng dụng cung cấp nội dung qua procedure do người dùng định nghĩa. Nó phù hợp với nguồn dữ liệu tổng hợp hoặc cần logic lấy nội dung riêng.

Procedure phải:
- Trả nội dung đúng contract Oracle Text yêu cầu.
- Xử lý exception rõ ràng.
- Có quyền đọc nguồn dữ liệu.
- Không thực hiện side effect ngoài ý muốn.
- Có performance phù hợp khi index nhiều row.

### 7.5. AUTO_FILTER

AUTO_FILTER chuyển một số định dạng tài liệu sang text để Oracle Text index. Tùy phiên bản và cài đặt, các định dạng văn phòng/PDF/HTML có thể được hỗ trợ.

Nếu dùng BLOB chứa file:
- Lưu MIME/content type hoặc metadata định dạng.
- Chọn filter phù hợp.
- Kiểm tra filter có hỗ trợ file đó.
- Kiểm tra file mã hóa/password protected.
- Kiểm tra tài liệu hỏng hoặc không hợp lệ.
- Kiểm soát kích thước và thời gian xử lý.

Không giả định mọi PDF/Office document đều extract được như nhau. Test các file thực tế, đặc biệt font nhúng, scan ảnh, OCR, password và tài liệu nhiều ngôn ngữ.

### 7.6. Filter không phải OCR

Filter thường trích xuất text có sẵn trong tài liệu. PDF scan chỉ chứa hình ảnh có thể không có text layer. Muốn tìm nội dung trong ảnh scan cần OCR pipeline riêng, sau đó lưu text đã nhận dạng vào cột hoặc datastore được index.

## 8. Section group — tìm kiếm theo vùng tài liệu

Section group mô tả cấu trúc bên trong document để query có thể giới hạn theo vùng.

Ví dụ HTML:

~~~html
<html>
  <head><title>Oracle Text Guide</title></head>
  <body>
    <h1>Index synchronization</h1>
    <p>Use CTX_DDL.SYNC_INDEX.</p>
  </body>
</html>
~~~

Có thể cần tìm từ Oracle trong title, hoặc tìm từ SYNC_INDEX trong body.

### 8.1. Các loại section group

Một số loại thường gặp:
- NULL_SECTION_GROUP: không khai báo section.
- BASIC_SECTION_GROUP: tạo section theo cấu hình thủ công.
- HTML_SECTION_GROUP: nhận diện section trong HTML.
- AUTO_SECTION_GROUP: tự động nhận diện một số vùng HTML/XML.
- XML_SECTION_GROUP: xử lý XML section.
- PATH_SECTION_GROUP: hỗ trợ truy vấn theo XML path trong trường hợp phù hợp.
- NEWS_SECTION_GROUP: nhóm section phục vụ định dạng news/document có cấu trúc theo khả năng release.

Tên và khả năng cụ thể cần đối chiếu tài liệu release đang chạy.

### 8.2. Tạo section group cho HTML

Ví dụ:

~~~sql
BEGIN
    CTX_DDL.CREATE_SECTION_GROUP(
        'DOCS_HTML_SECTIONS',
        'HTML_SECTION_GROUP'
    );
END;
/
~~~

Sau đó gắn vào CONTEXT index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'SECTION GROUP DOCS_HTML_SECTIONS'
);
~~~

Với HTML đã được filter hoặc lưu trong CLOB, Oracle Text có thể nhận biết các tag theo section group. Kiểm tra tài liệu về cách xử lý tag, field section và visibility.

### 8.3. Tìm trong section

Nếu section group khai báo section title, có thể query theo section name:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(
        content,
        'oracle WITHIN title',
        1
      ) > 0;
~~~

Tên section phải trùng tên được định nghĩa trong section group. Không dùng query section nếu index không có section group tương ứng.

### 8.4. Field section và zone section

Field section thường biểu diễn một vùng có giới hạn cấu trúc như title/meta field; zone section biểu diễn một vùng có thể chứa nhiều phần tử/nội dung hơn. Semantics cụ thể phụ thuộc loại section group và cấu hình.

Section giúp tăng độ chính xác: tìm từ khóa trong title có thể có trọng số/ngữ nghĩa khác với tìm trong body.

## 9. Kết hợp preference trong một CONTEXT index

Có thể tạo các preference trước, sau đó gắn trong PARAMETERS.

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE('DOCS_LEXER', 'BASIC_LEXER');
    CTX_DDL.SET_ATTRIBUTE('DOCS_LEXER', 'MIXED_CASE', 'NO');
    CTX_DDL.SET_ATTRIBUTE('DOCS_LEXER', 'BASE_LETTER', 'YES');

    CTX_DDL.CREATE_PREFERENCE('DOCS_WORDLIST', 'BASIC_WORDLIST');
    CTX_DDL.SET_ATTRIBUTE('DOCS_WORDLIST', 'PREFIX_INDEX', 'YES');
    CTX_DDL.SET_ATTRIBUTE('DOCS_WORDLIST', 'PREFIX_MIN_LENGTH', '2');
    CTX_DDL.SET_ATTRIBUTE('DOCS_WORDLIST', 'PREFIX_MAX_LENGTH', '5');

    CTX_DDL.CREATE_STOPLIST('DOCS_STOPLIST', 'BASIC_STOPLIST');
    CTX_DDL.ADD_STOPWORD('DOCS_STOPLIST', 'the');

    CTX_DDL.CREATE_SECTION_GROUP(
        'DOCS_HTML_SECTIONS',
        'HTML_SECTION_GROUP'
    );
END;
/
~~~

Tạo index:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'LEXER DOCS_LEXER
     WORDLIST DOCS_WORDLIST
     STOPLIST DOCS_STOPLIST
     SECTION GROUP DOCS_HTML_SECTIONS
     SYNC (MANUAL)'
);
~~~

Lưu ý:
- Preference name được tham chiếu trong index parameters.
- Preference phải tồn tại và user có quyền sử dụng.
- Dùng tên preference rõ ràng theo schema/application.
- Thay đổi preference sau khi index đã tạo không phải lúc nào cũng tự thay đổi nội dung index hiện có; kiểm tra yêu cầu rebuild/recreate theo thuộc tính và release.
- Giữ script tạo preference cùng migration/schema deployment.

## 10. Đồng bộ CONTEXT index

Một điểm vận hành quan trọng của CONTEXT index là DML trên bảng nguồn không nhất thiết xuất hiện ngay trong text index. Oracle Text có cơ chế pending queue và đồng bộ index.

### 10.1. Manual sync

Với cấu hình manual, sau INSERT/UPDATE/DELETE và COMMIT, thay đổi được ghi nhận để đồng bộ sau.

Chạy:

~~~sql
BEGIN
    CTX_DDL.SYNC_INDEX('DOCUMENTS_TEXT_IDX');
END;
/
~~~

Sau sync, truy vấn Oracle Text có thể tìm thấy nội dung mới theo trạng thái index đã cập nhật.

Tên index truyền vào phải đúng tên index. Thường gọi trong schema sở hữu index hoặc dùng quyền phù hợp.

### 10.2. SYNC ON COMMIT

Có thể cấu hình đồng bộ index theo commit:

~~~sql
CREATE INDEX documents_text_idx
ON documents(content)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'SYNC (ON COMMIT)'
);
~~~

Khi đó thao tác đồng bộ gắn với commit của DML theo semantics Oracle Text. Cần đo chi phí vì commit latency có thể tăng, đặc biệt khi một transaction cập nhật nhiều document hoặc document lớn.

SYNC ON COMMIT không phải lúc nào cũng phù hợp cho workload write-heavy. Nếu độ trễ tìm kiếm chấp nhận được, manual hoặc periodic sync có thể giảm áp lực trên transaction path.

### 10.3. Periodic sync

Có thể dùng DBMS_SCHEDULER để chạy SYNC_INDEX theo lịch:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'SYNC_DOCUMENTS_TEXT',
        job_type        => 'PLSQL_BLOCK',
        job_action      =>
            'BEGIN CTX_DDL.SYNC_INDEX(''DOCUMENTS_TEXT_IDX''); END;',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=MINUTELY;INTERVAL=5',
        enabled         => TRUE
    );
END;
/
~~~

Ví dụ chạy mỗi 5 phút chỉ là lịch minh họa. Chọn interval theo yêu cầu freshness, số DML, kích thước document và khả năng xử lý. Kiểm tra job owner, quyền, lỗi run và thời gian thực hiện.

### 10.4. SYNC với memory

SYNC_INDEX có thể nhận tham số memory để điều khiển tài nguyên cho quá trình đồng bộ theo cú pháp của release. Ví dụ:

~~~sql
BEGIN
    CTX_DDL.SYNC_INDEX(
        'DOCUMENTS_TEXT_IDX',
        '64M'
    );
END;
/
~~~

Memory lớn hơn có thể cải thiện throughput trong một số workload nhưng không phải càng lớn càng tốt. Đo thời gian, PGA, CPU, I/O và contention trước khi thay đổi.

### 10.5. Pending queue

Oracle Text giữ các row cần đồng bộ trong pending queue. Xem:

~~~sql
SELECT *
FROM ctx_user_pending;
~~~

View này giúp biết còn thay đổi chờ index. Cột cụ thể tùy release; xem dictionary description nếu cần truy vấn chi tiết.

Nếu pending queue tăng liên tục:
- Sync job có thể không chạy.
- Sync bị lỗi.
- DML rate vượt năng lực sync.
- Document lớn hoặc filter chậm.
- Một số row lỗi làm quá trình indexing không hoàn tất như mong đợi.

### 10.6. Delete và update

Khi row bị xóa hoặc nội dung thay đổi, Oracle Text cần đồng bộ để cập nhật inverted index. Với manual sync, kết quả search có thể chưa phản ánh trạng thái mới ngay sau commit.

Thiết kế SLA freshness rõ ràng: ví dụ tài liệu mới phải searchable trong vòng 2 phút, hoặc chỉ cần cập nhật theo batch mỗi giờ. Không gọi SYNC_INDEX sau từng row trong workload write-heavy nếu chưa đo chi phí.

## 11. Tối ưu CONTEXT index

Qua thời gian, các lần sync có thể tạo nhiều phần index cần merge/optimize. Oracle Text cung cấp CTX_DDL.OPTIMIZE_INDEX.

### 11.1. Optimize FULL

~~~sql
BEGIN
    CTX_DDL.OPTIMIZE_INDEX(
        'DOCUMENTS_TEXT_IDX',
        'FULL'
    );
END;
/
~~~

FULL thực hiện tối ưu/merge index theo semantics Oracle Text. Có thể tiêu thụ CPU, I/O và thời gian đáng kể. Lên lịch ngoài giờ cao điểm và theo dõi workload.

### 11.2. Optimize FAST

~~~sql
BEGIN
    CTX_DDL.OPTIMIZE_INDEX(
        'DOCUMENTS_TEXT_IDX',
        'FAST'
    );
END;
/
~~~

FAST tập trung vào việc merge các phần cần thiết theo behavior của Oracle Text. Hiệu quả phụ thuộc index fragmentation và release.

### 11.3. Optimize TOKEN

Một số release hỗ trợ optimize theo token với tham số token. Dùng khi cần xử lý một token cụ thể và đã hiểu cú pháp release. Không dùng TOKEN như một lệnh thay thế tổng quát cho FULL.

### 11.4. Lịch optimize

Có thể lập job riêng:
- SYNC thường xuyên theo freshness SLA.
- OPTIMIZE theo lượng pending/fragmentation và workload.
- Theo dõi duration, CPU, I/O và lock.
- Tránh chạy nhiều optimize đồng thời trên cùng index.
- Kiểm tra ảnh hưởng tới truy vấn search.

Không cần chạy FULL sau mọi lần SYNC. Hãy đo lợi ích và chi phí trước khi đưa vào lịch.

## 12. Ngôn ngữ truy vấn Oracle Text

CONTAINS nhận query expression theo cú pháp Oracle Text. Chuỗi query không phải SQL predicate thông thường; nó có toán tử riêng.

### 12.1. AND, OR, NOT

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'oracle AND database', 1) > 0;
~~~

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'oracle OR database', 1) > 0;
~~~

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'oracle NOT backup', 1) > 0;
~~~

Dùng ngoặc để thể hiện thứ tự logic rõ ràng khi biểu thức phức tạp.

### 12.2. Phrase search

Tìm cụm từ:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, '"oracle database"', 1) > 0;
~~~

Cú pháp phrase phụ thuộc Oracle Text query grammar; kiểm tra escape/quoting khi ứng dụng tạo query từ input người dùng.

### 12.3. NEAR

NEAR tìm các từ xuất hiện gần nhau theo khoảng cách và thứ tự được cấu hình:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(
        content,
        'NEAR((oracle,database), 5, TRUE)',
        1
      ) > 0;
~~~

Tham số và cú pháp NEAR cần theo Oracle Text query syntax của release. Dùng NEAR khi khoảng cách từ quan trọng; nó không giống phép AND đơn giản.

### 12.4. ABOUT

ABOUT tìm theo chủ đề/theme khi index được cấu hình hỗ trợ theme indexing:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'ABOUT(backup recovery)', 1) > 0;
~~~

ABOUT không chỉ là tìm chuỗi literal. Chất lượng theme phụ thuộc language knowledge base và cấu hình; kiểm tra availability và hỗ trợ ngôn ngữ.

### 12.5. STEM và FUZZY

Một số toán tử Oracle Text mở rộng tìm kiếm theo word stem hoặc từ gần giống. Ví dụ query có thể dùng STEM hoặc FUZZY theo grammar được hỗ trợ.

Trước khi bật:
- Xác nhận wordlist có cấu hình cần thiết.
- Kiểm tra ngôn ngữ.
- Kiểm tra false positive.
- Đo chi phí query.
- Giới hạn query complexity nếu input do người dùng cung cấp.

### 12.6. Wildcard và prefix

Prefix search có thể tìm token bắt đầu bằng một chuỗi khi wordlist hỗ trợ prefix index. Ví dụ:

~~~sql
SELECT document_id
FROM documents
WHERE CONTAINS(content, 'datab%', 1) > 0;
~~~

Cú pháp wildcard cụ thể và hiệu năng phụ thuộc wordlist. Prefix query ngắn có thể tạo tập kết quả rất lớn; áp dụng giới hạn độ dài và structured filter phù hợp.

## 13. Ranking và SCORE

Oracle Text có thể xếp hạng document theo mức liên quan dựa trên query và nội dung được index.

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE CONTAINS(content, 'oracle AND text', 1) > 0
ORDER BY relevance DESC;
~~~

SCORE trả điểm cho label tương ứng. Điểm là giá trị ranking nội bộ, không phải xác suất đúng hoặc phần trăm liên quan.

### 13.1. Kết hợp score với business sorting

Ví dụ ưu tiên relevance rồi mới tới ngày tạo:

~~~sql
SELECT document_id,
       title,
       created_at,
       SCORE(1) AS relevance
FROM documents
WHERE status = 'PUBLISHED'
  AND CONTAINS(content, 'oracle text', 1) > 0
ORDER BY relevance DESC,
         created_at DESC;
~~~

Nếu dùng pagination, cần thứ tự ổn định. Thêm khóa phụ như document_id để tránh thứ tự không xác định khi điểm bằng nhau.

### 13.2. Score không thay thế relevance evaluation

Đánh giá search quality bằng tập query và expected result:
- Precision: kết quả trả về có liên quan không?
- Recall: tài liệu liên quan có bị bỏ sót không?
- Ranking quality: tài liệu tốt có nằm ở đầu danh sách không?
- Latency: query mất bao lâu?
- Freshness: nội dung mới mất bao lâu để searchable?

Không đặt threshold SCORE tùy tiện khi chưa đo trên corpus thực.

## 14. CTXCAT cho catalog search

CTXCAT phù hợp với một số ứng dụng catalog cần tìm kiếm text kết hợp thuộc tính có cấu trúc như category, price, date hoặc status. Nó sử dụng index set để định nghĩa các structured columns đi cùng text index.

### 14.1. Tạo index set

Ví dụ:

~~~sql
BEGIN
    CTX_DDL.CREATE_INDEX_SET('PRODUCT_CATALOG_SET');

    CTX_DDL.ADD_INDEX(
        'PRODUCT_CATALOG_SET',
        'CATEGORY_ID'
    );

    CTX_DDL.ADD_INDEX(
        'PRODUCT_CATALOG_SET',
        'PRICE'
    );
END;
/
~~~

Tạo CTXCAT index:

~~~sql
CREATE INDEX product_catalog_text_idx
ON products(description)
INDEXTYPE IS CTXSYS.CTXCAT
PARAMETERS (
    'INDEX SET PRODUCT_CATALOG_SET'
);
~~~

Cú pháp index set và các loại structured index được hỗ trợ cần đối chiếu đúng release. Chỉ thêm các cột thực sự tham gia catalog search.

### 14.2. CATSEARCH

CTXCAT thường được truy vấn bằng CATSEARCH:

~~~sql
SELECT product_id,
       price
FROM products
WHERE CATSEARCH(
        description,
        'wireless headphones',
        'category_id = 10 AND price < 200'
      ) > 0;
~~~

Structured clause của CATSEARCH có grammar riêng; không truyền tùy ý một đoạn SQL đầy đủ. Kiểm tra kiểu dữ liệu và cú pháp được hỗ trợ.

### 14.3. Khi nào chọn CONTEXT hay CTXCAT?

- CONTEXT: document/full-text search tổng quát, có preference phong phú và sync lifecycle.
- CTXCAT: catalog-style query kết hợp text và structured attributes theo index set.
- Nếu workload cần query SQL linh hoạt với nhiều structured predicate, đánh giá plan và thiết kế index tổng thể; không giả định CTXCAT luôn nhanh hơn.

## 15. CTXRULE cho phân loại văn bản

CTXRULE cho phép lưu các query/rule để áp dụng lên văn bản mới. Thay vì người dùng tìm document, hệ thống kiểm tra document mới phù hợp với những rule nào.

Ví dụ use case:
- Phân loại ticket theo từ khóa.
- Gắn nhãn email theo chủ đề.
- Nhận diện hồ sơ thuộc nhóm nghiệp vụ.
- Phân luồng tài liệu đến bộ phận xử lý.

Mô hình:
1. Lưu mỗi rule như một query expression.
2. Tạo CTXRULE index trên cột rule.
3. Dùng MATCHES để tìm rule khớp với document text.
4. Lưu kết quả classification.

CTXRULE có query/index semantics riêng. Kiểm tra cách tạo rule index và MATCHES theo tài liệu release, không dùng CONTAINS thay thế cho classification rule lookup.

## 16. Đồng bộ index và tính nhất quán kết quả

Một câu hỏi vận hành quan trọng: sau khi INSERT/UPDATE/DELETE, khi nào CONTAINS nhìn thấy thay đổi?

### 16.1. CONTEXT với manual sync

Với manual sync:
- DML cập nhật bảng nguồn.
- Transaction commit.
- Thay đổi chờ trong Oracle Text pending queue.
- SYNC_INDEX xử lý các thay đổi.
- Truy vấn CONTAINS sau sync nhìn thấy nội dung đã index.

Nếu ứng dụng cần search-after-write tức thời, manual sync có thể không đáp ứng SLA nếu sync chạy theo lịch.

### 16.2. SYNC ON COMMIT

SYNC ON COMMIT có thể đưa công việc đồng bộ vào commit path. Điều này giảm độ trễ stale search nhưng tăng chi phí commit và có thể ảnh hưởng throughput.

Test:
- Transaction ghi một document nhỏ.
- Transaction ghi nhiều document.
- Document lớn.
- Concurrent writers.
- Commit latency và rollback behavior.
- Search ngay sau commit.
- Error khi filter/indexing không thành công.

### 16.3. Commit và rollback

Chỉ dữ liệu đã commit mới là trạng thái bền vững của bảng nguồn. Oracle Text sync xử lý các thay đổi theo transaction/indexing semantics của index. Không giả định một lần SYNC_INDEX có thể làm dữ liệu chưa commit trở nên searchable.

### 16.4. Tách write path và search freshness

Nếu ứng dụng có write throughput cao:
- Commit DML nhanh.
- Sync theo lịch ngắn hoặc worker.
- Theo dõi pending backlog.
- Thông báo cho UI rằng search index có độ trễ nếu cần.
- Dùng truy vấn SQL trực tiếp cho lookup theo primary key ngay sau write khi search index chưa sync.

Không dùng Oracle Text index như nguồn sự thật thay cho bảng quan hệ.

## 17. Giám sát Oracle Text

Oracle Text có dictionary views để theo dõi index, preference, pending work và lỗi.

### 17.1. Indexes

~~~sql
SELECT *
FROM ctx_user_indexes;
~~~

DBA có thể xem các view DBA_CTX_* hoặc ALL_CTX_* theo quyền và release. Dùng dictionary description để kiểm tra column names.

### 17.2. Pending queue

~~~sql
SELECT *
FROM ctx_user_pending;
~~~

Pending queue tăng lâu có thể là dấu hiệu sync không chạy hoặc không theo kịp.

### 17.3. Index errors

~~~sql
SELECT *
FROM ctx_user_index_errors;
~~~

View này hỗ trợ điều tra lỗi phát sinh trong quá trình index hóa. Kiểm tra rowid, error code/message và thời điểm nếu các cột đó có trong release đang dùng.

### 17.4. Index objects

~~~sql
SELECT *
FROM ctx_user_index_objects;
~~~

View giúp quan sát các object Oracle Text liên quan tới index. Không sửa/xóa các bảng nội bộ của Oracle Text trực tiếp.

### 17.5. Job monitoring

Nếu SYNC/OPTIMIZE chạy bằng DBMS_SCHEDULER, kiểm tra:

~~~sql
SELECT job_name,
       status,
       actual_start_date,
       run_duration,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name = 'SYNC_DOCUMENTS_TEXT'
ORDER BY log_date DESC;
~~~

Tên cột có thể khác theo release/view. Kiểm tra scheduler run details, job log và alert log nếu sync thất bại.

## 18. Troubleshooting lỗi Oracle Text

### 18.1. CONTAINS không tìm thấy document mới

Kiểm tra:
1. DML đã commit chưa?
2. Index type có cần sync không?
3. SYNC_INDEX có chạy thành công?
4. Row có xuất hiện trong CTX_USER_PENDING không?
5. Có lỗi index trong CTX_USER_INDEX_ERRORS không?
6. Document có rỗng hoặc chỉ chứa stopwords không?
7. Lexer có tách token như kỳ vọng không?
8. Query grammar có đúng không?

### 18.2. ORA-20000 hoặc DRG-... errors

Oracle Text thường phát ra lỗi DRG- và có thể được bọc trong ORA-20000. Đọc toàn bộ error stack; phần DRG thường chỉ ra preference, lexer, filter, query parser hoặc index operation gây lỗi.

Không xử lý bằng cách xóa index nội bộ hoặc bảng DR$ trực tiếp.

### 18.3. Document không index được

Nguyên nhân:
- Filter không hỗ trợ định dạng.
- BLOB/file hỏng hoặc có password.
- Datastore không tìm thấy file.
- Thiếu quyền DIRECTORY.
- User-defined procedure lỗi.
- Character set/encoding không hợp lệ.
- Document quá lớn hoặc timeout.
- Preference sai tên hoặc thuộc tính không hợp lệ.

Kiểm tra CTX_USER_INDEX_ERRORS, alert log, filter configuration và quyền truy cập nguồn.

### 18.4. Kết quả tìm kiếm sai

Điều tra:
- Lexer case/accent/joins.
- Stoplist.
- Wordlist và stemming/fuzzy.
- Section group.
- Document source/filter.
- Index có được sync không.
- Query expression và escaping.
- Structured predicate và data type.

Tạo một tập document nhỏ tái hiện, xác định tokenization và query semantics trước khi sửa preference trên index production.

### 18.5. SYNC_INDEX chậm

Kiểm tra:
- Pending queue growth.
- Số row DML.
- Kích thước document.
- Filter time.
- CPU/PGA/I/O.
- Concurrent sync.
- Index fragmentation và optimize schedule.
- Storage placement và tablespace.

Không tăng memory hoặc chạy nhiều SYNC song song mà chưa đo bottleneck.

### 18.6. Index invalid hoặc create index thất bại

Đọc lỗi đầy đủ, kiểm tra:
- CTXSYS component/install status.
- Quyền execute package CTX_DDL.
- Tablespace/storage.
- Preference names và attributes.
- Column datatype.
- Filter availability.
- Index errors và database alert log.

Không cấp quyền CTXAPP/CTX_DDL rộng rãi cho mọi user. Dùng quyền tối thiểu cần thiết.

## 19. Bảo mật và an toàn query

Oracle Text query expression có grammar riêng. Nếu ứng dụng ghép trực tiếp input người dùng vào query string, người dùng có thể tạo expression phức tạp ngoài ý muốn.

### 19.1. Kiểm soát input

- Giới hạn độ dài query.
- Validate operator được phép.
- Escape hoặc quote literal theo Oracle Text query grammar.
- Không nối input thành SQL text.
- Dùng bind variable cho tham số CONTAINS.
- Giới hạn wildcard/fuzzy/expansion có chi phí cao.
- Có timeout/rate limit theo use case.
- Không để user truy vấn ngoài phạm vi tenant/authorization.

Bind variable ngăn SQL injection ở lớp SQL nhưng không tự vô hiệu hóa mọi operator trong Oracle Text query grammar. Cần xử lý riêng ngôn ngữ truy vấn.

### 19.2. Row-level authorization

CONTAINS không tự đảm bảo người dùng chỉ nhìn thấy document họ được phép đọc. Kết hợp predicate authorization/tenant:

~~~sql
SELECT document_id,
       SCORE(1) AS relevance
FROM documents
WHERE tenant_id = :tenant_id
  AND status = 'PUBLISHED'
  AND CONTAINS(content, :text_query, 1) > 0
ORDER BY relevance DESC;
~~~

Authorization phải được kiểm soát ở server side. Không dựa vào filter do browser gửi.

### 19.3. File datastore

Nếu dùng FILE_DATASTORE:
- Hạn chế DIRECTORY object.
- Không cho user nhập path tùy ý.
- Kiểm tra symlink/path traversal ở ingestion layer.
- Hạn chế file type và size.
- Quét malware theo chính sách.
- Không để database process đọc mọi thư mục trên host.

## 20. Thiết kế vận hành và capacity

Oracle Text index có chi phí storage và maintenance riêng. Dự báo:
- Số document.
- Tổng dung lượng text sau filter.
- Số token duy nhất.
- Tần suất DML.
- Tỷ lệ update/delete.
- Tần suất sync.
- Fuzzy/prefix/substring requirements.
- Số ngôn ngữ.
- Filter CPU.
- Query concurrency.

### 20.1. Index growth

Inverted index có thể lớn hơn hoặc nhỏ hơn dữ liệu text tùy token distribution, metadata, wordlist và cấu trúc lưu trữ. Không lấy một hệ số cố định để dự báo mọi corpus.

Tạo thử nghiệm với mẫu đại diện và đo:
- Segment size.
- Pending queue.
- Sync throughput.
- Optimize duration.
- Query latency.
- DML commit latency.

### 20.2. Backup và recovery

Oracle Text index là database object có thể được bảo vệ qua backup database. Sau restore/recovery, xác nhận component, index status, preferences, source data và khả năng query. Nếu cần rebuild index, phải dự báo thời gian và tài nguyên.

Không backup riêng các bảng DR$ nội bộ bằng script ứng dụng rồi coi đó là phương án restore được hỗ trợ.

### 20.3. Partitioning

Một số kiến trúc có thể dùng local/domain index hoặc chiến lược partition phù hợp. Khả năng Oracle Text partitioned index thay đổi theo index type và release. Kiểm tra tài liệu phiên bản và giới hạn partition trước khi thiết kế; không giả định mọi CONTEXT index có thể partition theo cùng cách B-tree.

## 21. Quy trình triển khai preference/index có kiểm soát

Một migration Oracle Text nên có các bước:

1. Kiểm tra CTXSYS component và quyền.
2. Kiểm tra datatype và nguồn nội dung.
3. Tạo preference với tên versioned.
4. Kiểm tra lexer/stoplist/wordlist/section group trên dữ liệu mẫu.
5. Tạo index trên môi trường test.
6. Chạy query regression.
7. Đo index build, sync, optimize và query time.
8. Kiểm tra DML và search freshness.
9. Triển khai index production trong maintenance window nếu cần.
10. Thiết lập SYNC job và monitoring.
11. Lưu script rollback/drop index.
12. Theo dõi pending/errors sau cutover.

### 21.1. Thay đổi preference

Khi thay lexer/wordlist/stoplist/section group, xác định thay đổi có yêu cầu rebuild/recreate index hay không. Không cho rằng thay preference object sẽ tự tái token hóa toàn bộ dữ liệu đã index.

Dùng tên preference versioned, ví dụ DOCS_LEXER_V2, để thử cấu hình mới và có thể so sánh với cấu hình cũ trên clone.

### 21.2. Drop index

~~~sql
DROP INDEX documents_text_idx;
~~~

Drop index xóa search index, không xóa bảng documents. Trước khi drop:
- Xác nhận ứng dụng không còn phụ thuộc query.
- Có kế hoạch create lại.
- Ước lượng thời gian build.
- Lưu preference definitions.
- Xác nhận storage và maintenance window.

Không xóa các bảng DR$ nội bộ trực tiếp.

## 22. Ví dụ hoàn chỉnh: tìm kiếm tài liệu

Tạo bảng:

~~~sql
CREATE TABLE knowledge_documents (
    document_id NUMBER PRIMARY KEY,
    title       VARCHAR2(300),
    body        CLOB,
    category    VARCHAR2(40),
    status      VARCHAR2(20),
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

Tạo lexer và wordlist:

~~~sql
BEGIN
    CTX_DDL.CREATE_PREFERENCE('KNOWLEDGE_LEXER', 'BASIC_LEXER');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_LEXER', 'MIXED_CASE', 'NO');

    CTX_DDL.CREATE_PREFERENCE('KNOWLEDGE_WORDLIST', 'BASIC_WORDLIST');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_WORDLIST', 'PREFIX_INDEX', 'YES');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_WORDLIST', 'PREFIX_MIN_LENGTH', '2');
    CTX_DDL.SET_ATTRIBUTE('KNOWLEDGE_WORDLIST', 'PREFIX_MAX_LENGTH', '5');
END;
/
~~~

Tạo CONTEXT index:

~~~sql
CREATE INDEX knowledge_body_text_idx
ON knowledge_documents(body)
INDEXTYPE IS CTXSYS.CONTEXT
PARAMETERS (
    'LEXER KNOWLEDGE_LEXER
     WORDLIST KNOWLEDGE_WORDLIST
     SYNC (MANUAL)'
);
~~~

Thêm document:

~~~sql
INSERT INTO knowledge_documents(
    document_id, title, body, category, status
)
VALUES (
    1,
    'Oracle Text operations',
    'Oracle Text indexes documents using a lexer and inverted index.',
    'DATABASE',
    'PUBLISHED'
);

COMMIT;
~~~

Đồng bộ:

~~~sql
BEGIN
    CTX_DDL.SYNC_INDEX('KNOWLEDGE_BODY_TEXT_IDX');
END;
/
~~~

Tìm kiếm:

~~~sql
SELECT document_id,
       title,
       SCORE(1) AS relevance
FROM knowledge_documents
WHERE category = 'DATABASE'
  AND status = 'PUBLISHED'
  AND CONTAINS(body, 'oracle AND lexer', 1) > 0
ORDER BY relevance DESC,
         document_id;
~~~

Kiểm tra pending/errors:

~~~sql
SELECT * FROM ctx_user_pending;

SELECT *
FROM ctx_user_index_errors
WHERE err_index_name = 'KNOWLEDGE_BODY_TEXT_IDX';
~~~

Tên cột trong view lỗi có thể khác giữa release; nếu query cột cụ thể không chạy, xem dictionary description của view trước khi điều chỉnh.

## 23. Checklist vận hành Oracle Text

- [ ] Xác nhận index type phù hợp: CONTEXT, CTXCAT hay CTXRULE.
- [ ] Xác nhận cột và datastore đúng.
- [ ] Xác nhận filter hỗ trợ định dạng nguồn.
- [ ] Xác nhận lexer và language mapping.
- [ ] Kiểm thử case/accent/joins với dữ liệu thật.
- [ ] Xác nhận stoplist không loại từ nghiệp vụ cần tìm.
- [ ] Cấu hình wordlist theo nhu cầu fuzzy/stem/prefix/substring.
- [ ] Cấu hình section group nếu cần field/zone search.
- [ ] Lưu script tạo preference và index.
- [ ] Chọn manual, periodic hay ON COMMIT sync.
- [ ] Đo commit latency và search freshness.
- [ ] Theo dõi CTX_USER_PENDING.
- [ ] Theo dõi CTX_USER_INDEX_ERRORS.
- [ ] Lên lịch optimize theo workload.
- [ ] Kiểm tra query plan và SCORE behavior.
- [ ] Kiểm soát query grammar từ input người dùng.
- [ ] Kết hợp tenant/authorization predicate.
- [ ] Kiểm tra backup/recovery và khả năng rebuild.
- [ ] Có capacity estimate và maintenance window.
- [ ] Kiểm thử lại sau khi đổi preference hoặc Oracle RU.

## 24. Bài tập tự luyện

1. Oracle Text giải quyết loại workload tìm kiếm nào?
2. Inverted index khác B-tree index ra sao?
3. Vẽ luồng datastore, filter, lexer, wordlist và inverted index.
4. Phân biệt CONTEXT, CTXCAT và CTXRULE.
5. Viết lệnh tạo CONTEXT index trên CLOB.
6. CONTAINS và SCORE liên kết với nhau bằng cách nào?
7. Vì sao SCORE không phải xác suất relevance?
8. Lexer có nhiệm vụ gì?
9. MIXED_CASE và BASE_LETTER ảnh hưởng tìm kiếm thế nào?
10. Vì sao BASE_LETTER có thể làm tăng false positives với tiếng Việt?
11. PRINTJOINS và SKIPJOINS ảnh hưởng tokenization ra sao?
12. Khi nào dùng MULTI_LEXER?
13. Stoplist có thể làm thay đổi kết quả tìm kiếm như thế nào?
14. Wordlist hỗ trợ những tính năng nào?
15. Prefix indexing làm tăng chi phí gì?
16. Stemming khác fuzzy matching ra sao?
17. Phân biệt DIRECT_DATASTORE và FILE_DATASTORE.
18. AUTO_FILTER có thay thế OCR không?
19. Section group dùng để làm gì?
20. Viết truy vấn tìm token trong section title.
21. Manual sync hoạt động như thế nào?
22. SYNC ON COMMIT có ảnh hưởng commit latency ra sao?
23. Viết lệnh CTX_DDL.SYNC_INDEX.
24. CTX_USER_PENDING và CTX_USER_INDEX_ERRORS dùng để làm gì?
25. Khi nào cần OPTIMIZE_INDEX?
26. Phân biệt CONTEXT query và CATSEARCH.
27. CTXRULE/MATCHES giải quyết bài toán nào?
28. Vì sao bind SQL không tự loại bỏ query operator injection trong Oracle Text grammar?
29. Thiết kế lịch sync/optimize cho một kho tài liệu có nhiều DML.
30. Lập test plan cho thay đổi lexer từ MIXED_CASE=YES sang NO và BASE_LETTER=YES.

**Oracle Text biến nội dung thành inverted index thông qua datastore, filter và lexer; wordlist, stoplist cùng section group quyết định cách token được lưu và tìm kiếm.** Với CONTEXT index, hãy thiết kế rõ freshness contract và chọn manual, periodic hoặc ON COMMIT sync theo workload; theo dõi pending queue, indexing errors và optimize cost. Khi thay lexer hoặc preference, kiểm thử tokenization và query regression trước khi áp dụng lên index production.

