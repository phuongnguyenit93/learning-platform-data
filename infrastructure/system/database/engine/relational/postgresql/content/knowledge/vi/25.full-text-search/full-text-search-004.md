# Parser, dictionary, stop word và text search configuration trong PostgreSQL

PostgreSQL có hệ thống **Full Text Search (FTS)** dùng để tìm tài liệu theo từ vựng và ngữ nghĩa tìm kiếm, thay vì chỉ so chuỗi con. Khi viết:

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'The runners are running quickly'
);
~~~

PostgreSQL không đơn thuần chuyển câu thành một chuỗi chữ thường. Nó **tách văn bản thành token**, xác định loại token, đưa token qua những **dictionary** được cấu hình, bỏ các **stop word** như `the` và `are`, đồng thời chuẩn hóa một số biến thể như `runners` và `running` thành **lexeme**.

Điều đó giải thích vì sao truy vấn tìm `run` có thể khớp câu chứa `running` khi dùng cấu hình tiếng Anh, nhưng không nhất thiết khớp khi dùng cấu hình `simple`.

Một đường xử lý FTS điển hình:

~~~text
                 văn bản đầu vào
                        |
                        v
                  TEXT SEARCH PARSER
             tách token + phân loại token
                        |
          +-------------+-------------+
          |             |             |
      asciiword       word          email/...
          |             |             |
          v             v             v
        MAPPING của TEXT SEARCH CONFIGURATION
          |             |             |
          v             v             v
     DICTIONARY 1 -> DICTIONARY 2 -> ...
          |             |             |
      lexeme(s)      stop word      không nhận
          |             |             |
          +-------------+-------------+
                        |
                        v
          TSVECTOR (lexeme, vị trí, trọng số)
                        ^
                        |
        TSQUERY được xử lý bằng cấu hình phù hợp
                        |
                        v
                  toán tử @@
~~~

**Bốn khái niệm không thể dùng thay cho nhau:**

- **Parser:** tách văn bản thành token và xác định *token type*; không tự quyết định từ nào là stop word.
- **Dictionary:** nhận token và chuẩn hóa thành lexeme, từ chối token để dictionary sau xử lý, hoặc coi token là stop word.
- **Stop word:** từ được dictionary loại khỏi các lexeme tìm kiếm theo quy tắc của ngôn ngữ/cấu hình.
- **Text search configuration:** nối parser với **chuỗi dictionary tương ứng từng loại token**, quyết định toàn bộ quá trình chuẩn hóa.

Bài này hướng dẫn cấu trúc FTS, những hàm quan sát và quản lý cấu hình, ảnh hưởng của stop word tới phrase search, tạo configuration riêng, gắn chỉ mục GIN, xử lý tiếng Việt/đa ngôn ngữ, kịch bản SQL và bài tập có lời giải.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt *token*, *token type*, *lexeme*, *tsvector* và *tsquery*.
2. Mô tả vai trò khác nhau của parser, dictionary, stop word và text search configuration.
3. Sử dụng `ts_parse`, `ts_token_type`, `ts_debug` và `ts_lexize` để quan sát pipeline.
4. Hiểu chuỗi dictionary: trả lexeme, trả danh sách rỗng khi gặp stop word hoặc trả SQL `NULL` khi không nhận diện.
5. So sánh cấu hình `simple` với `english` và giải thích việc stemming.
6. Tạo một text search configuration riêng bằng `CREATE TEXT SEARCH CONFIGURATION`.
7. Chỉnh ánh xạ token type bằng `ALTER TEXT SEARCH CONFIGURATION ... ALTER/ADD MAPPING`.
8. Hiểu stop word tác động tới `plainto_tsquery`, `phraseto_tsquery` và vị trí từ.
9. Dùng cấu hình tường minh để tạo `tsvector`, `tsquery` và chỉ mục GIN tương ứng.
10. Nhận ra vì sao một cột `tsvector` hoặc expression index có thể lỗi thời khi quy tắc dictionary thay đổi.
11. Phân tích giới hạn của stemming tiếng Anh đối với nội dung tiếng Việt.
12. Chọn thiết kế FTS phù hợp từ nhu cầu truy vấn, ngôn ngữ và chi phí cập nhật.

## 2. Khi nào dùng Full Text Search?

Giả sử có một bảng bài viết:

~~~sql
SELECT *
FROM articles
WHERE body ILIKE '%running%';
~~~

`ILIKE` kiểm tra chuỗi con không phân biệt hoa/thường (theo ngữ nghĩa liên quan). Nó không tự hiểu rằng `run`, `running` và `runs` cùng một họ từ.

FTS biểu diễn nhu cầu khác:

~~~sql
SELECT *
FROM articles
WHERE to_tsvector('pg_catalog.english', body)
      @@ plainto_tsquery('pg_catalog.english', 'running');
~~~

Đối với các từ tiếng Anh được dictionary chuẩn hóa phù hợp, một lexeme chung có thể giúp match các biến thể.

### 2.1. FTS không phải tìm mọi substring

Nếu người dùng tìm `gram` ở giữa từ `programming`, FTS thông thường **không tự coi đó là một từ độc lập**. Trường hợp cần tìm chuỗi con, có thể cân nhắc `LIKE`, `ILIKE` hoặc trigram index của `pg_trgm`.

### 2.2. FTS cũng không phải tìm kiếm ngữ nghĩa AI

FTS dựa trên token, dictionary, lexeme, toán tử logic, vị trí và ranking. Nó không tự diễn giải đồng nghĩa sâu hoặc ý nghĩa câu như embedding/vector search. Có thể mở rộng bằng synonym/thesaurus dictionary và những hệ thống khác, nhưng cần cấu hình rõ.

### 2.3. Một cấu hình phù hợp phụ thuộc ngôn ngữ

`english` có thuật toán stemming và stop words của tiếng Anh. Áp dụng cho nội dung tiếng Việt không tự tạo ra một hệ thống tách từ/chuẩn hóa tiếng Việt đầy đủ. Do đó cấu hình FTS **là một phần của thiết kế dữ liệu**, không chỉ một tham số kỹ thuật.

## 3. Các kiểu dữ liệu và toán tử cốt lõi

| Thành phần | Vai trò |
| --- | --- |
| `text` | Văn bản nguồn |
| `tsvector` | Tập lexeme đã chuẩn hóa, có thể giữ vị trí và trọng số |
| `tsquery` | Biểu thức tìm kiếm với lexeme và các toán tử |
| `to_tsvector` | Chuyển văn bản thành tsvector theo configuration |
| `to_tsquery` | Biến biểu thức có cú pháp tsquery thành truy vấn |
| `plainto_tsquery` | Chuẩn hóa văn bản người dùng thành truy vấn kết hợp AND |
| `phraseto_tsquery` | Tạo truy vấn quan tâm tới thứ tự/khoảng cách từ |
| `websearch_to_tsquery` | Nhận cú pháp tìm kiếm gần với web search |
| `@@` | Kiểm tra tsvector có khớp tsquery không |
| `ts_rank`, `ts_rank_cd` | Tính độ phù hợp dựa trên vector/query |
| `ts_headline` | Tạo đoạn văn bản có nhấn mạnh phần khớp |

### 3.1. Một ví dụ tối thiểu

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The quick brown fox jumps'
    ) AS document_vector,
    plainto_tsquery(
        'pg_catalog.english',
        'quick fox'
    ) AS search_query;
~~~

`to_tsvector` trả một cấu trúc chứa các lexeme được dictionary chấp nhận. `plainto_tsquery` tạo điều kiện tìm các lexeme tương ứng, thông thường kết hợp bằng toán tử `&`.

### 3.2. Kiểm tra @@

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The quick brown fox jumps'
    )
    @@ plainto_tsquery(
        'pg_catalog.english',
        'quick fox'
    ) AS matches;
~~~

Kết quả là `true` vì cả `quick` và `fox` có trong vector sau chuẩn hóa.

### 3.3. Tsvector không phải bản sao văn bản

Vector có thể đã bỏ stop words, gộp biến thể stemming và mất cách viết hoa/thường ban đầu. Vì vậy **không lưu riêng tsvector rồi xóa văn bản gốc** nếu cần hiển thị nội dung, audit, highlight hoặc khôi phục nguyên bản.

## 4. Token, token type và lexeme

**Token** là đoạn văn bản parser tách được từ đầu vào. Mỗi token được gán một **loại token** (*token type*).

Ví dụ câu:

~~~text
The runners are running at example.org
~~~

Parser có thể phân loại những từ tiếng Anh không dấu là `asciiword`, trong khi một địa chỉ web hoặc hostname có kiểu riêng.

**Lexeme** là chuỗi chuẩn hóa do dictionary tạo ra:

~~~text
Token           Dictionary        Lexeme
-------------------------------------------------
The             english_stem      (stop word)
runners         english_stem      runner
are             english_stem      (stop word)
running         english_stem      run
~~~

Tên lexeme cụ thể phụ thuộc dictionary và phiên bản tệp/ngôn ngữ liên quan.

### 4.1. Một token có thể tạo nhiều lexeme

Một số dictionary có thể chuyển một token thành nhiều lexeme hoặc trả lexeme có cấu trúc bổ sung theo tính năng từ điển. Không áp giả định “một token luôn đúng một lexeme” cho mọi configuration.

### 4.2. Một lexeme có thể xuất hiện nhiều vị trí

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'running runs run'
);
~~~

Nhiều biến thể có thể cùng chuyển thành lexeme `run`, với thông tin vị trí từ gốc. Vị trí đó quan trọng đối với phrase/proximity queries và một số ranking.

### 4.3. Token type không phải SQL type

`asciiword`, `word`, `email`, `host` là các **nhãn parser**. Chúng không phải kiểu cột SQL như `text`, `integer` hoặc `jsonb`.

## 5. Parser: phân tách và phân loại, không stemming

PostgreSQL có parser FTS mặc định tên `pg_catalog.default`, có khả năng phân loại nhiều loại token: từ, từ có dấu nối, số, email, URL, hostname...

### 5.1. Quan sát token bằng ts_parse

~~~sql
SELECT
    tokid,
    token
FROM ts_parse(
    'pg_catalog.default'::regparser,
    'The runner sent mail to team@example.org'
);
~~~

`ts_parse` trả **ID loại token** và nội dung token. Hàm này chưa dùng stop words hay stemming, nên các từ như `The` và `to` vẫn xuất hiện trong dòng token nếu parser nhận chúng.

### 5.2. Xem danh sách token types

~~~sql
SELECT
    tokid,
    alias,
    description
FROM ts_token_type(
    'pg_catalog.default'::regparser
)
ORDER BY tokid;
~~~

Các giá trị `alias` sẽ dùng khi khai báo mapping, chẳng hạn `asciiword` và `word`.

### 5.3. Liên kết ID token với tên

~~~sql
WITH parsed AS (
    SELECT *
    FROM ts_parse(
        'pg_catalog.default'::regparser,
        'PostgreSQL helps search e-mail@example.org'
    )
),
types AS (
    SELECT *
    FROM ts_token_type(
        'pg_catalog.default'::regparser
    )
)
SELECT
    p.tokid,
    t.alias,
    t.description,
    p.token
FROM parsed AS p
JOIN types AS t ON t.tokid = p.tokid;
~~~

### 5.4. Parser không biết “the” nên bị loại

Parser chịu trách nhiệm biến dòng văn bản thành token như `The`. Việc `The` trở thành stop word hay lexeme phụ thuộc **dictionary được configuration gán** cho token type đó.

### 5.5. Từ nối và nhiều loại token

Từ có dấu nối như `high-speed` có thể tạo token toàn phần và những token con theo cách parser mặc định được định nghĩa. Vì vậy một đoạn nguồn có thể tạo nhiều lexeme với vị trí đặc biệt; không nên đếm số token FTS bằng `string_to_array(text,' ')`.

## 6. Dictionary: chuẩn hóa token thành lexeme

Parser tạo token, nhưng **dictionary** quyết định cách xử lý token ấy.

Một dictionary nhận token và có thể:

1. **Nhận token:** trả một hoặc nhiều lexeme.
2. **Nhận token như stop word:** trả mảng lexeme rỗng.
3. **Không nhận token:** trả SQL `NULL` để dictionary tiếp theo trong mapping thử xử lý.
4. **Dictionary lọc (filtering dictionary):** biến đổi token rồi chuyển tiếp tới dictionary sau, tùy loại dictionary.

### 6.1. Dictionary simple

`pg_catalog.simple` thường chuyển token về chữ thường mà không stemming theo ngữ pháp tiếng Anh. Nếu không cấu hình stopword riêng, nó giữ nhiều từ chức năng mà cấu hình tiếng Anh loại bỏ.

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'The runners are running'
    ) AS simple_vector;
~~~

### 6.2. Dictionary english_stem

`pg_catalog.english_stem` dùng thuật toán stemming theo tiếng Anh, đồng thời có tập stop words tương ứng.

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS english_vector;
~~~

Hai vector khác nhau về lexeme: trong cấu hình tiếng Anh, `runners` có thể thành `runner`, `running` thành `run`; các từ chức năng như `the` và `are` bị loại.

### 6.3. Dictionary không phải hàm translate toàn văn

Stemming không dịch ngôn ngữ. `english_stem` không tự biến `mèo` thành `cat` hay `tìm kiếm` thành `search`. Đồng nghĩa/thesaurus cần cơ chế dictionary riêng hoặc cấu trúc tìm kiếm bổ sung.

## 7. ts_lexize: kiểm tra một dictionary riêng lẻ

`ts_lexize` dùng để gọi một text search dictionary với **một token**:

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.simple'::regdictionary,
        'Running'
    ) AS simple_lexeme,
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'Running'
    ) AS english_lexeme;
~~~

Thông thường:

- `simple` trả một lexeme dạng chữ thường gần nguyên bản như `running`.
- `english_stem` trả lexeme rút gọn như `run`.

### 7.1. Stop word trả mảng rỗng

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'the'
    ) AS english_stop_word;
~~~

Đây là stop word tiếng Anh thông dụng, nên dictionary trả **mảng rỗng** (đã nhận token nhưng không sinh lexeme).

### 7.2. SQL NULL khác mảng rỗng

- `NULL`: dictionary **không nhận diện** token, chuỗi dictionary có thể chuyển sang dictionary tiếp theo.
- `{}` (mảng rỗng): token đã được nhận là stop word, **không tiếp tục** thử các dictionary sau.
- `{run}`: token được xử lý thành một lexeme.

Phân biệt này rất quan trọng khi thiết kế dictionary chain.

### 7.3. ts_lexize không mô phỏng toàn parser

`ts_lexize` nhận một token đã chuẩn bị sẵn; nó không tự diễn giải mọi loại token trong cả đoạn văn bản. Nếu muốn thấy parser + mapping + dictionary cùng hoạt động, dùng `ts_debug`.

## 8. Text search configuration điều phối toàn pipeline

Một text search configuration chứa:

1. **Parser** được chọn.
2. **Mapping** từ mỗi token type mà parser phát ra tới một hoặc nhiều dictionaries, có thứ tự ưu tiên.

Ví dụ cấu hình `pg_catalog.english` dựa trên parser mặc định và dictionary có stemming tiếng Anh cho những nhóm token thích hợp.

### 8.1. Một token type có thể có dictionary chain

Minh họa:

~~~text
asciiword
    |
    v
dictionary A
    |
    +--> lexeme      : chấp nhận, dừng
    +--> stop word   : loại, dừng
    +--> NULL        : chuyển dictionary B
    +--> filter      : biến đổi rồi tiếp tục xử lý
    |
    v
dictionary B
~~~

Điểm quan trọng: **thứ tự dictionary trong mapping có thể làm thay đổi kết quả.**

### 8.2. Token type không có mapping

Nếu parser trả một loại token nhưng configuration không có mapping tương ứng, token có thể bị bỏ qua khi tạo tsvector/tsquery.

Ví dụ, nếu configuration tùy biến chỉ map `asciiword` mà dữ liệu chứa loại `word` với ký tự có dấu, những token ấy có thể không được xử lý như mong muốn.

### 8.3. Configuration là đối tượng schema

PostgreSQL quản lý text search configurations theo schema, có tên đủ định danh như:

~~~text
pg_catalog.english
pg_catalog.simple
fts_lab.en_no_stem
~~~

Khi đổi `search_path` hoặc cấu hình mặc định, tên không kèm schema có thể được giải quyết khác. Với index, migration và ứng dụng lớn, dùng **tên configuration tường minh** thường giúp hành vi dễ dự đoán.

## 9. Xem cấu hình mặc định hiện tại

~~~sql
SHOW default_text_search_config;
~~~

Thông số này chỉ ra configuration được dùng bởi một số hàm FTS khi **không truyền tên configuration**.

### 9.1. Hàm có và không có config tường minh

~~~sql
SELECT
    to_tsvector('The runners are running')
      AS dependent_on_session_default,
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS explicit_english;
~~~

Biểu thức thứ nhất phụ thuộc `default_text_search_config`. Biểu thức thứ hai không phụ thuộc lựa chọn mặc định của session.

### 9.2. Đặt tạm trong transaction

~~~sql
BEGIN;
SET LOCAL default_text_search_config = 'pg_catalog.simple';

SELECT to_tsvector('The runners are running');

ROLLBACK;
~~~

`SET LOCAL` có hiệu lực trong phạm vi transaction theo quy tắc của PostgreSQL. Ví dụ này cho thấy cùng văn bản nguồn nhưng **kết quả FTS có thể thay đổi do cấu hình**, không phải do dữ liệu đổi.

### 9.3. Vì sao query và index cần cùng configuration?

Nếu vector được tạo bằng `english` mà query được chuẩn hóa bằng `simple`, từ `running` có thể là `run` ở một phía nhưng `running` ở phía kia. Query có thể không khớp dù tài liệu “có từ ấy” theo cách người dùng đọc.

Do đó phải xác định **cấu hình tạo vector** và **cấu hình tạo query** tương thích về lexeme.

## 10. ts_debug: công cụ quan sát quan trọng nhất

`ts_debug` trả từng bước xử lý token trong một configuration:

~~~sql
SELECT
    alias,
    description,
    token,
    dictionaries,
    dictionary,
    lexemes
FROM ts_debug(
    'pg_catalog.english',
    'The runners are running quickly'
);
~~~

Những cột này có ý nghĩa:

| Cột | Ý nghĩa |
| --- | --- |
| `alias` | Tên token type do parser gán |
| `description` | Mô tả token type |
| `token` | Chuỗi token nguyên đầu vào |
| `dictionaries` | Các dictionaries được map cho token type |
| `dictionary` | Dictionary thực sự nhận token, nếu có |
| `lexemes` | Lexeme(s) cuối; mảng rỗng với stop word |

### 10.1. Quan sát stop words

Trong ví dụ `The runners are running quickly`, những token như `The` và `are` có thể được dictionary tiếng Anh nhận là stop words và không sinh lexeme.

### 10.2. Quan sát stemming

`runners` và `running` sẽ được xử lý theo quy tắc English stemmer, dẫn đến các lexeme ngắn hơn token gốc.

### 10.3. So sánh english với simple

~~~sql
SELECT
    alias,
    token,
    dictionary,
    lexemes
FROM ts_debug(
    'pg_catalog.simple',
    'The runners are running quickly'
);
~~~

Ở cấu hình `simple`, nhiều token được giữ dưới dạng chữ thường mà không stemming; stopword behavior khác.

### 10.4. Dùng đúng bài toán khi debug

Nếu một truy vấn trả thiếu tài liệu, đừng chỉ nhìn output tsvector. Hãy dùng `ts_debug` trên:

1. Văn bản nguồn cụ thể.
2. Cụm từ người dùng tìm.
3. Chính configuration được dùng để tạo index/tsvector.

Điều này giúp thấy token nào bị bỏ, token nào đổi thành lexeme nào, và dictionary nào tham gia.

## 11. Stop words là gì?

**Stop words** là những từ có tần suất cao hoặc ít giá trị phân biệt trong bối cảnh tìm kiếm, được một dictionary xác định để loại khỏi bộ lexeme.

Trong tiếng Anh, ví dụ thường gặp:

~~~text
the, a, an, and, of, to, are ...
~~~

Danh sách và hành vi thực tế phụ thuộc dictionary/phiên bản nguồn dữ liệu của hệ thống. Không tự suy mọi từ ngắn đều là stop word.

### 11.1. Ví dụ trực tiếp

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'the quick fox'
    ) AS english_vector,
    to_tsvector(
        'pg_catalog.simple',
        'the quick fox'
    ) AS simple_vector;
~~~

`english` bỏ lexeme `the`, còn `simple` thông thường giữ nó.

### 11.2. Stop words không xóa văn bản gốc

Việc bỏ stopword là bước tạo **tsvector/tsquery**; cột `text` ban đầu vẫn chứa từ ấy. Nếu `ts_headline` hiển thị văn bản, chữ `the` vẫn có thể xuất hiện trong đoạn gốc.

### 11.3. Chọn stop words không chỉ để giảm index size

Loại từ phổ biến có thể giảm kích thước vector và giảm những match ít giá trị. Nhưng với một số domain (luật, y tế, tên sản phẩm, mã lệnh, câu cố định), những từ thông dụng có thể **rất quan trọng**. Ví dụ cụm từ phủ định hoặc danh xưng có thể mất nghĩa khi bỏ token.

### 11.4. Stopword list phụ thuộc ngôn ngữ

Không đưa nguyên danh sách stopword tiếng Anh vào bài viết tiếng Việt rồi kỳ vọng tốt hơn. Cần xác định từ phổ biến trong corpus, ý định tìm kiếm và yêu cầu phrase search trước khi điều chỉnh.

## 12. Stop words và vị trí trong tsvector

Khi tạo vector, vị trí từ của văn bản vẫn ảnh hưởng tới proximity, kể cả khi một số token bị coi là stop word.

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'quick and brown'
);
~~~

Với parser/configuration tiếng Anh thông thường, lexeme `quick` và `brown` cách nhau **hai vị trí** vì token `and` nằm giữa đã bị loại khỏi lexeme.

### 12.1. Vì sao không đơn giản nối hai từ lại?

Nếu bỏ stopword mà cũng xóa khoảng vị trí, phrase search có thể coi:

~~~text
quick brown
quick and brown
~~~

hoàn toàn giống nhau về vị trí, dù người dùng có thể yêu cầu cụm từ liền kề. PostgreSQL giữ thông tin vị trí cần thiết trong tsvector/tsquery để phân biệt những trường hợp ấy theo điều kiện tìm kiếm.

### 12.2. Vị trí là metadata, không phải chuỗi trống

Trong `tsvector`, chỉ những lexeme được giữ mới xuất hiện, nhưng vị trí của chúng vẫn phản ánh tokenization và stopword gaps theo cơ chế FTS.

### 12.3. Cùng từ có thể nằm ở nhiều vị trí

~~~sql
SELECT to_tsvector(
    'pg_catalog.english',
    'quick fox and quick brown fox'
);
~~~

Lexeme `quick` và `fox` xuất hiện nhiều lần và có thể mang nhiều position entries. Điều này hỗ trợ ranking và phrase matching.

## 13. plainto_tsquery: tạo truy vấn từ câu thường

~~~sql
SELECT plainto_tsquery(
    'pg_catalog.english',
    'the quick brown fox'
);
~~~

`plainto_tsquery`:

1. Phân tích input theo configuration.
2. Chuẩn hóa bằng dictionaries.
3. Bỏ stop words theo quy tắc.
4. Kết hợp các lexeme còn lại theo **AND**.

### 13.1. Không cần tự ghép &

Người dùng nhập `quick brown fox`; ứng dụng có thể dùng:

~~~sql
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    $1
)
~~~

thay vì xây chuỗi `quick & brown & fox` thủ công.

### 13.2. Plain input không phải cú pháp tsquery đầy đủ

Nếu người dùng gõ các ký tự `&`, `|` hoặc ngoặc trong input thường, `plainto_tsquery` sẽ xử lý như văn bản theo quy tắc parser, không cho người dùng viết trực tiếp mọi toán tử tsquery.

### 13.3. Tìm các từ mà không cần đúng thứ tự

Với `plainto_tsquery('english','quick fox')`, vector chứa `fox` và `quick` có thể match ngay cả khi ở những vị trí khác nhau, vì mối quan hệ là AND, **không phải phrase liền kề**.

## 14. to_tsquery: cú pháp toán tử rõ ràng

`to_tsquery` dùng khi bạn muốn viết biểu thức với toán tử logic FTS:

~~~sql
SELECT to_tsquery(
    'pg_catalog.english',
    'fox & run'
);
~~~

Các toán tử thường gặp:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `&` | AND |
| `|` | OR |
| `!` | NOT |
| `<->` | FOLLOWED BY, khoảng cách một vị trí |
| `<N>` | FOLLOWED BY với khoảng cách N vị trí |
| `:*` | Prefix matching trên lexeme ở những ngữ cảnh phù hợp |

### 14.1. Ví dụ logic

~~~sql
SELECT to_tsquery(
    'pg_catalog.english',
    'postgresql & (search | index)'
);
~~~

Ý nghĩa: có lexeme PostgreSQL và ít nhất một trong search/index sau chuẩn hóa.

### 14.2. Cú pháp sai có thể gây lỗi

`to_tsquery` yêu cầu input hợp lệ theo ngữ pháp tsquery. Không truyền trực tiếp text tùy ý của người dùng vào hàm này rồi mặc định nó không thể lỗi cú pháp.

### 14.3. Không ghép chuỗi SQL

Ngay cả khi dùng `to_tsquery`, phải **bind parameters** để tránh SQL injection. Phần string tsquery vẫn cần được xử lý về mặt cú pháp và quyền cho phép các toán tử tìm kiếm.

## 15. phraseto_tsquery: thứ tự và khoảng cách

~~~sql
SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick fox'
);
~~~

Kết quả có thể mang cấu trúc như:

~~~text
'quick' <-> 'fox'
~~~

Đây là yêu cầu từ `quick` theo ngay sau bởi `fox` ở vị trí kế tiếp.

### 15.1. Stop words được phản ánh trong khoảng cách

~~~sql
SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick and fox'
);
~~~

Vì `and` là stopword, phrase query vẫn phản ánh khoảng cách vị trí, chẳng hạn dạng:

~~~text
'quick' <2> 'fox'
~~~

Do đó:

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'quick and fox'
    ) @@ phraseto_tsquery(
        'pg_catalog.english',
        'quick and fox'
    ) AS spaced_match;
~~~

có thể match dựa trên đúng vị trí, không yêu cầu lexeme `and` còn ở vector.

### 15.2. Phrase và AND khác nhau

~~~sql
SELECT
    to_tsvector('pg_catalog.english', 'fox is quick')
      @@ plainto_tsquery('pg_catalog.english', 'quick fox')
        AS and_match,
    to_tsvector('pg_catalog.english', 'fox is quick')
      @@ phraseto_tsquery('pg_catalog.english', 'quick fox')
        AS phrase_match;
~~~

Kết quả logic: AND có thể true vì có cả hai lexeme, nhưng phrase theo thứ tự `quick` rồi `fox` thì không.

### 15.3. Prefix không thay phrase

Tìm lexeme có tiền tố là vấn đề khác với “hai lexeme đứng cạnh nhau”. Cần chọn toán tử đúng nhu cầu, không dùng `:*` để thay `<->`.

## 16. websearch_to_tsquery: cú pháp gần với ô tìm kiếm

~~~sql
SELECT websearch_to_tsquery(
    'pg_catalog.english',
    '"quick fox" OR running -sleeping'
);
~~~

Hàm hỗ trợ một cú pháp tìm kiếm thân thiện hơn so với `to_tsquery`, chẳng hạn:

- Từ/cụm từ trong dấu ngoặc kép để tìm phrase.
- `OR` để diễn đạt lựa chọn.
- Dấu trừ trước từ để diễn đạt phủ định trong cú pháp được hỗ trợ.

### 16.1. Phù hợp với người dùng nhập chuỗi tự do

`websearch_to_tsquery` được thiết kế để xử lý input theo cú pháp kiểu web, thường tránh một số lỗi cú pháp mà `to_tsquery` dễ gặp khi đưa input không chuẩn.

### 16.2. Không phải công cụ hiểu ý định hoàn hảo

Nó vẫn dùng configuration, parser và dictionaries. Nếu query chỉ chứa stopwords, kết quả vẫn có thể không có lexeme tìm kiếm. Nó cũng không tự tìm các từ đồng nghĩa chưa được cấu hình.

### 16.3. Tách validation và parsing

Ứng dụng nên giới hạn độ dài input, xử lý truy vấn rỗng, bind parameters và áp chính sách bảo vệ chi phí truy vấn, thay vì chỉ dựa vào việc hàm ít gây lỗi cú pháp.

## 17. Khi input chỉ gồm stop words

~~~sql
SELECT
    plainto_tsquery(
        'pg_catalog.english',
        'the and of'
    ) AS only_stopwords;
~~~

Một tập từ chỉ gồm các stopwords của dictionary có thể tạo **tsquery rỗng**, không có lexeme hữu ích để match.

### 17.1. Kiểm tra số node

~~~sql
SELECT
    numnode(
        plainto_tsquery(
            'pg_catalog.english',
            'the and of'
        )
    ) AS query_nodes;
~~~

Với những từ được coi là stopwords, kết quả là `0` node.

### 17.2. Tình huống trong ứng dụng

Người dùng có thể nhập:

~~~text
the
and
of the
~~~

Nếu configuration bỏ toàn bộ token, ứng dụng nên xử lý một cách rõ ràng:

- Thông báo không có từ khóa hữu ích.
- Gợi ý bổ sung từ khóa khác.
- Chuyển sang chiến lược khác khi nghiệp vụ cần tìm chính xác cụm từ.

Không coi tsquery rỗng là yêu cầu “tìm tất cả hàng” trừ khi sản phẩm quyết định như vậy và có giới hạn chi phí.

## 18. Tạo database lab cho FTS

Các ví dụ sau chỉ dùng **schema thử nghiệm**, không đụng dữ liệu production.

~~~sql
CREATE SCHEMA fts_lab;

CREATE TABLE fts_lab.articles (
    article_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL,
    lang text NOT NULL DEFAULT 'en'
        CHECK (lang IN ('en','vi')),
    published_at timestamptz NOT NULL
);
~~~

### 18.1. Dữ liệu tiếng Anh và tiếng Việt

~~~sql
INSERT INTO fts_lab.articles
    (title, body, lang, published_at)
VALUES
    (
      'Running with the foxes',
      'The quick brown foxes are running across the field.',
      'en', '2026-01-01 08:00:00+00'
    ),
    (
      'PostgreSQL full text search',
      'A text search configuration connects a parser to dictionaries.',
      'en', '2026-01-02 08:00:00+00'
    ),
    (
      'Stemming and stop words',
      'An English dictionary can normalize running and remove the word the.',
      'en', '2026-01-03 08:00:00+00'
    ),
    (
      'Database indexes',
      'A GIN index can accelerate matching a tsvector with a tsquery.',
      'en', '2026-01-04 08:00:00+00'
    ),
    (
      'The little green house',
      'A greenhouse stands near a quiet garden.',
      'en', '2026-01-05 08:00:00+00'
    ),
    (
      'Colour and color',
      'Color and colour are different spellings in English.',
      'en', '2026-01-06 08:00:00+00'
    ),
    (
      'Tìm kiếm văn bản tiếng Việt',
      'PostgreSQL hỗ trợ tìm kiếm theo từ khóa và chỉ mục GIN.',
      'vi', '2026-01-07 08:00:00+00'
    ),
    (
      'Cơ sở dữ liệu và phân tích',
      'Cấu hình tìm kiếm phải phù hợp với ngôn ngữ của dữ liệu.',
      'vi', '2026-01-08 08:00:00+00'
    );
~~~

### 18.2. Xem dữ liệu gốc

~~~sql
SELECT
    article_id,
    title,
    lang,
    published_at
FROM fts_lab.articles
ORDER BY article_id;
~~~

Mỗi row là một tài liệu. Hai tài liệu `lang='vi'` được dùng để minh họa giới hạn cấu hình tiếng Anh, không phải để khẳng định PostgreSQL có sẵn bộ phân tách từ tiếng Việt chuyên nghiệp.

## 19. Thực hành parser: quan sát từng token

~~~sql
SELECT
    p.tokid,
    t.alias,
    p.token
FROM ts_parse(
    'pg_catalog.default'::regparser,
    'The quick fox runs at info@example.org'
) AS p
JOIN ts_token_type(
    'pg_catalog.default'::regparser
) AS t
    ON t.tokid = p.tokid;
~~~

Kết quả cho thấy token và alias tương ứng, bao gồm những loại token mà parser nhận biết từ văn bản.

### 19.1. Tại sao xem token type trước khi ALTER MAPPING?

`ALTER TEXT SEARCH CONFIGURATION ... MAPPING FOR ...` dùng **alias token type**, chẳng hạn `asciiword`, `word`, `email`. Nếu bạn nhầm alias, mapping có thể không tác động tới văn bản mong muốn hoặc lệnh sẽ không hợp lệ.

### 19.2. Parser đã xử lý dấu câu

Không cần tự:

~~~sql
regexp_replace(body, '[[:punct:]]', ' ', 'g')
~~~

trong mọi truy vấn trước `to_tsvector`. Parser FTS vốn có quy tắc tokenization. Tiền xử lý thủ công có thể làm mất URL, dấu nối, emoji và những đặc tính mà ứng dụng cần.

### 19.3. Parser mặc định không phải tokenizer ngôn ngữ chuyên sâu

Với tiếng Việt có khoảng trắng trong các từ ghép, parser mặc định không hiểu đầy đủ ranh giới từ theo nghĩa ngôn ngữ. FTS theo từng token có thể cần dictionary/tokenizer bên ngoài hoặc kiến trúc tìm kiếm khác khi yêu cầu recall/chất lượng tìm kiếm cao.

## 20. Thực hành dictionary: nhận diện stop word và stemming

~~~sql
SELECT
    token,
    ts_lexize(
        'pg_catalog.simple'::regdictionary,
        token
    ) AS simple_result,
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        token
    ) AS english_result
FROM (
    VALUES
        ('running'),
        ('runners'),
        ('the'),
        ('quickly'),
        ('foxes')
) AS sample(token);
~~~

### 20.1. Cách đọc kết quả

Quan sát:

- Token có bị đổi về lexeme gốc không?
- Có token nào bị bỏ dưới dạng mảng rỗng không?
- Có trường hợp dictionary không nhận diện trả SQL `NULL` không?

### 20.2. Kết quả không đồng nhất với dịch thuật

Nếu một dictionary đổi `running` thành `run`, đó là **stemming**. Nó không đồng nghĩa rằng có thể truy vấn mọi từ tương tự nghĩa chỉ với một dictionary mặc định.

### 20.3. Chú ý từ không phải tiếng Anh

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'tìm'
    ) AS english_on_vietnamese;
~~~

Kể cả khi dictionary trả một lexeme, điều đó không có nghĩa nó hiểu **ngữ pháp và từ ghép tiếng Việt**.

## 21. Thực hành ts_debug trên văn bản nhiều dạng

~~~sql
SELECT
    alias,
    token,
    dictionaries,
    dictionary,
    lexemes
FROM ts_debug(
    'pg_catalog.english',
    'Running, THE foxes; docs@example.org, high-speed.'
);
~~~

### 21.1. Những điều cần tìm

1. Từ `Running` đi qua dictionary nào?
2. `THE` có bị xem là stop word không?
3. Parser xem email là loại token nào?
4. `high-speed` tạo những token nào?
5. Những token khác nhau có thể sinh lexeme trùng không?

### 21.2. Không đánh giá từ output một bản PostgreSQL duy nhất

Cách phân loại/chuẩn hóa token chịu ảnh hưởng phiên bản parser và dictionary. Dùng `ts_debug` làm **bằng chứng của môi trường thực tế** thay vì ghi cứng mọi tên token/lexeme trong ứng dụng.

## 22. Tạo một text search configuration riêng

Giả sử muốn giữ nguyên dạng từ để tìm kiếm chính xác hơn theo từ, không dùng stemming tiếng Anh cho nhóm token thông thường.

### 22.1. Sao chép configuration có sẵn

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.en_no_stem (
    COPY = pg_catalog.english
);
~~~

`COPY` tạo cấu hình mới dựa trên một configuration có sẵn; sau đó có thể chỉnh mapping **của cấu hình mới** mà không sửa `pg_catalog.english` dùng chung.

### 22.2. Đổi mapping cho những token type thông thường

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.en_no_stem
ALTER MAPPING FOR asciiword, word
WITH pg_catalog.simple;
~~~

Nghĩa là token thuộc những type này được xử lý bằng dictionary `simple` thay cho danh sách dictionary trước đó.

### 22.3. So sánh kết quả

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS english_vector,
    to_tsvector(
        'fts_lab.en_no_stem',
        'The runners are running'
    ) AS no_stem_vector;
~~~

Vì các token ví dụ là từ ASCII không dấu, mapping đã đổi sẽ khiến `The`/`are` được giữ bởi `simple` và `runners`/`running` không còn qua English stemmer ở hai token types ấy.

### 22.4. Tại sao tên cấu hình là en_no_stem, không phải simple?

Ta **sao chép** cấu hình tiếng Anh rồi chỉ đổi mapping của `asciiword` và `word`. Các token types khác vẫn kế thừa mapping từ cấu hình gốc. Vì vậy configuration mới **không hoàn toàn đồng nhất với `pg_catalog.simple`**.

### 22.5. Không chỉnh pg_catalog.english trực tiếp

Không dùng:

~~~sql
-- Không làm trong môi trường dùng chung:
ALTER TEXT SEARCH CONFIGURATION pg_catalog.english ...
~~~

Thay đổi configuration hệ thống/chia sẻ có thể ảnh hưởng nhiều ứng dụng, biểu thức index và kết quả tìm kiếm. Dùng configuration riêng trong schema ứng dụng.

## 23. Tạo configuration từ parser

Một cách khác là tạo configuration **chưa có mapping**, sau đó thêm mapping từng token type.

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.lab_words (
    PARSER = pg_catalog.default
);
~~~

### 23.1. Thêm mapping

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.lab_words
ADD MAPPING FOR asciiword, word
WITH pg_catalog.simple;
~~~

### 23.2. Kiểm tra

~~~sql
SELECT
    to_tsvector(
        'fts_lab.lab_words',
        'Simple running café and email@example.org'
    ) AS partial_mapped;
~~~

Chỉ những token types có mapping mới được xử lý theo configuration này. Ví dụ parser có thể phát ra token type cho email và các nhóm token khác chưa được map; chúng có thể không xuất hiện trong tsvector.

### 23.3. Khi nào phù hợp?

Cấu hình từ `PARSER` hữu ích nếu bạn muốn **chủ động chọn từng loại token**, ví dụ chỉ lập index những nhóm từ văn bản thông thường và bỏ qua token types không liên quan.

### 23.4. Đánh đổi

Rất dễ bỏ quên một token type thực sự quan trọng như email, số hoặc từ có dấu nối. Với yêu cầu gần một cấu hình sẵn có, `COPY` rồi chỉnh các mapping cần thiết thường dễ hiểu hơn.

## 24. Điều chỉnh chuỗi dictionary bằng ALTER MAPPING

Cú pháp tổng quát:

~~~sql
ALTER TEXT SEARCH CONFIGURATION config_name
ALTER MAPPING FOR token_type [, ...]
WITH dictionary_name [, ...];
~~~

### 24.1. Thứ tự dictionaries có nghĩa

Nếu mapping chứa:

~~~text
dictionary_A, dictionary_B
~~~

thì dictionary A được thử trước. Nếu A nhận token và trả lexeme hoặc stopword, B không được thử theo kiểu fallback bình thường.

### 24.2. Lỗi: đặt simple ở đầu chuỗi và chờ stemming

Giả sử:

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.en_no_stem
ALTER MAPPING FOR asciiword
WITH pg_catalog.simple, pg_catalog.english_stem;
~~~

`simple` thông thường **nhận hầu hết token** thuộc nhóm ấy và trả dạng chữ thường. Vì nó đã nhận token, `english_stem` phía sau thường không có cơ hội xử lý.

**Đặt thêm một stemmer ở cuối không tự khiến stemming diễn ra.**

### 24.3. Trường hợp dictionary đầu trả SQL NULL

Một dictionary chuyên biệt có thể chỉ nhận một số token, trả SQL `NULL` với token khác; khi ấy dictionary sau là **fallback thật sự**.

### 24.4. Filtering dictionary là trường hợp khác

Filtering dictionary, ví dụ `unaccent` khi cài extension, có thể biến đổi token rồi cho các dictionary sau tiếp tục xử lý. Đây không giống một dictionary thông thường trả lexeme và kết thúc.

### 24.5. Không dựng chain theo thứ tự ngẫu nhiên

Trước khi cấu hình:

- Dictionary nào có nhiệm vụ **lọc/chuẩn hóa trước**?
- Dictionary nào có nhiệm vụ **stemming**?
- Dictionary nào là **fallback**?
- Stopwords cần được nhận ở bước nào?

Hãy thử từng trường hợp bằng `ts_debug` và `ts_lexize`.

## 25. Tạo simple dictionary với stop words

PostgreSQL có template `pg_catalog.simple` và có thể dùng tệp stopwords thích hợp để tạo một dictionary mới.

Ví dụ dùng danh sách stopwords tiếng Anh thường được phân phối với PostgreSQL:

~~~sql
CREATE TEXT SEARCH DICTIONARY fts_lab.stop_only_en (
    TEMPLATE = pg_catalog.simple,
    StopWords = english
);
~~~

### 25.1. Dictionary này khác english_stem

`stop_only_en` dùng template simple, kết hợp danh sách stopwords; nó không tự biến thành Snowball English stemmer.

~~~sql
SELECT
    ts_lexize(
        'fts_lab.stop_only_en'::regdictionary,
        'the'
    ) AS stopword_result,
    ts_lexize(
        'fts_lab.stop_only_en'::regdictionary,
        'running'
    ) AS ordinary_result;
~~~

Dự kiến `the` được loại bởi danh sách stopwords; `running` được giữ dưới dạng chữ thường, không tự thành `run`.

### 25.2. Tạo configuration dùng dictionary này

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.stop_words_only (
    PARSER = pg_catalog.default
);

ALTER TEXT SEARCH CONFIGURATION fts_lab.stop_words_only
ADD MAPPING FOR asciiword, word
WITH fts_lab.stop_only_en;
~~~

### 25.3. So sánh ba chiến lược

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'The runners are running'
    ) AS simple,
    to_tsvector(
        'fts_lab.stop_words_only',
        'The runners are running'
    ) AS stop_without_stem,
    to_tsvector(
        'pg_catalog.english',
        'The runners are running'
    ) AS english_stemmed;
~~~

Ý nghĩa:

- `simple`: thường giữ cả stopwords, không stemming.
- `stop_words_only`: bỏ stopwords đã cấu hình, không stemming.
- `english`: có stopwords và stemming tiếng Anh.

### 25.4. Phụ thuộc tệp trên máy chủ

Tùy chọn `StopWords = english` tham chiếu tệp danh sách stopwords trên **máy chủ PostgreSQL**, không phải một bảng SQL hoặc đường dẫn local của ứng dụng. Tập tệp/khả năng cài đặt và quyền có thể khác theo bản đóng gói; nếu môi trường thiếu tệp hoặc quyền, bước tạo dictionary cần được xử lý bởi DBA.

### 25.5. Không chỉnh tệp stopwords tùy tiện trên production

Thay nội dung tệp dictionary có thể làm thay đổi lexeme của dữ liệu dù SQL không đổi. Các bước triển khai phải bao gồm phiên bản cấu hình, tái tạo vector/index và rollout an toàn.

## 26. Stemming, synonym và thesaurus khác nhau

| Cơ chế | Ví dụ ý tưởng | Mục tiêu |
| --- | --- | --- |
| Lowercasing | `Running` → `running` | Không phân biệt hoa/thường ở mức token |
| Stemming | `running` → `run` | Gom biến thể hình thái |
| Stop words | `the` → không có lexeme | Bỏ những từ ít giá trị phân biệt |
| Synonym dictionary | `db` → `database` | Chuẩn hóa biến thể viết tắt/từ đồng nghĩa xác định |
| Thesaurus dictionary | Một cụm nhiều từ → cách biểu diễn khác | Chuẩn hóa cụm từ/ngữ nghĩa từ điển |
| Unaccent filtering | `café` → `cafe` | Loại dấu khi yêu cầu |

### 26.1. English stemmer không tạo synonym tùy ý

`colour` và `color` không nên mặc định được coi như một lexeme chỉ vì cả hai thuộc tiếng Anh. Nếu ứng dụng muốn khớp hai biến thể, cần kiểm tra dictionary thực tế hoặc cấu hình synonym riêng.

### 26.2. Synonym dictionary cần tài nguyên và quy trình riêng

Một synonym dictionary thông thường dựa trên tệp định nghĩa trên máy chủ. Nó không tự xuất hiện chỉ vì bạn viết `CREATE TEXT SEARCH CONFIGURATION`. Việc thêm quy tắc đồng nghĩa phải được kiểm tra để tránh làm mất nghĩa phân biệt của domain.

### 26.3. Thesaurus không thay parser

Thesaurus có thể xử lý một số cụm nhiều từ ở tầng dictionary, nhưng parser vẫn quyết định những token nào được tạo và loại token tương ứng.

### 26.4. Không loại dấu cho mọi nghiệp vụ

Đối với tiếng Việt, dấu là một phần thông tin ngôn ngữ. Tìm kiếm không phân biệt dấu có thể cải thiện trải nghiệm trong một số sản phẩm, nhưng cũng có thể tăng match không mong muốn. Cần cân nhắc yêu cầu chính xác và kiểm thử dữ liệu thực.

## 27. unaccent: filtering dictionary tùy chọn

Extension `unaccent` cung cấp một filtering dictionary có thể loại dấu/biến đổi ký tự trước khi dictionary tiếp theo thực hiện stemming.

Trong môi trường có quyền cài extension:

~~~sql
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;
~~~

**Lưu ý:** Nếu extension đã được cài vào schema khác, tên dictionary phải tham chiếu đúng schema thực tế. Đoạn SQL dưới đây giả định extension được cài trong `public`.

### 27.1. Sao chép configuration tiếng Anh

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.en_unaccent (
    COPY = pg_catalog.english
);
~~~

### 27.2. Sử dụng unaccent trước english_stem

~~~sql
ALTER TEXT SEARCH CONFIGURATION fts_lab.en_unaccent
ALTER MAPPING FOR word, asciiword
WITH public.unaccent, pg_catalog.english_stem;
~~~

### 27.3. Vì sao thứ tự này quan trọng?

`unaccent` là filtering dictionary, có thể chuyển token có dấu thành dạng không dấu rồi tiếp tục đưa token cho `english_stem`. Nếu thay bằng một dictionary thường luôn nhận token đứng đầu, dictionary phía sau có thể không được gọi.

### 27.4. Thử nghiệm

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'café'
    ) AS original_config,
    to_tsvector(
        'fts_lab.en_unaccent',
        'café'
    ) AS normalized_config;
~~~

Kết quả cho thấy mức ảnh hưởng của unaccent trong môi trường hỗ trợ. Dùng `ts_debug('fts_lab.en_unaccent',...)` để kiểm tra dictionary chain thay vì đoán kết quả từ tên cấu hình.

### 27.5. Phân biệt với hàm unaccent(text)

Extension cũng có chức năng xử lý chuỗi ở cấp hàm SQL. Nhưng **dùng filtering dictionary trong pipeline FTS** là thiết kế khác với `WHERE unaccent(col) LIKE ...` và cần index strategy tương ứng.

### 27.6. Không coi unaccent là tokenizer tiếng Việt đầy đủ

`unaccent` chủ yếu xử lý dấu/ký tự theo rules của extension. Nó không tự phân đoạn các từ ghép tiếng Việt thành đơn vị tìm kiếm chuẩn ngôn ngữ và không hiểu đồng nghĩa của mọi từ.

## 28. Xem configurations trong catalog

PostgreSQL lưu metadata FTS ở các system catalogs.

~~~sql
SELECT
    n.nspname AS config_schema,
    c.cfgname AS config_name,
    p.prsname AS parser_name
FROM pg_ts_config AS c
JOIN pg_namespace AS n
    ON n.oid = c.cfgnamespace
JOIN pg_ts_parser AS p
    ON p.oid = c.cfgparser
WHERE n.nspname IN ('pg_catalog','fts_lab')
ORDER BY n.nspname, c.cfgname;
~~~

### 28.1. Các catalog chính

| Catalog | Chứa thông tin |
| --- | --- |
| `pg_ts_parser` | Text search parsers |
| `pg_ts_config` | Configurations và parser được chọn |
| `pg_ts_config_map` | Mapping từ token type tới dictionaries theo thứ tự |
| `pg_ts_dict` | Tên dictionary và tùy chọn |
| `pg_ts_template` | Dictionary templates |
| `pg_namespace` | Schema của các đối tượng |

### 28.2. Không chỉnh trực tiếp catalog

Catalog dùng để **đọc metadata**. Muốn thay mapping, dùng SQL DDL chuyên dụng như `ALTER TEXT SEARCH CONFIGURATION`, không sửa trực tiếp `pg_ts_config_map`.

## 29. Xem mapping dictionary thực tế

Query sau cho biết dictionary nào được áp dụng theo từng token type của `pg_catalog.english`:

~~~sql
SELECT
    t.alias AS token_type,
    m.mapseqno AS dictionary_order,
    nd.nspname || '.' || d.dictname AS dictionary_name
FROM pg_ts_config AS c
JOIN pg_ts_config_map AS m
    ON m.mapcfg = c.oid
JOIN pg_ts_dict AS d
    ON d.oid = m.mapdict
JOIN pg_namespace AS nd
    ON nd.oid = d.dictnamespace
CROSS JOIN LATERAL ts_token_type(
    c.cfgparser::regparser
) AS t
WHERE c.oid = 'pg_catalog.english'::regconfig
  AND t.tokid = m.maptokentype
ORDER BY t.alias, m.mapseqno;
~~~

### 29.1. Ý nghĩa mapseqno

`mapseqno` cho biết **thứ tự dictionary** đối với cùng một token type. Trong chuỗi lookup bình thường, dictionary đứng trước có cơ hội nhận token trước.

### 29.2. Vì sao kết hợp ts_token_type?

`pg_ts_config_map.maptokentype` lưu mã loại token. Hàm `ts_token_type` chuyển mã ấy thành alias dễ đọc như `asciiword`.

### 29.3. Tìm cấu hình tùy chỉnh

Đổi:

~~~sql
WHERE c.oid = 'pg_catalog.english'::regconfig
~~~

thành:

~~~sql
WHERE c.oid = 'fts_lab.en_no_stem'::regconfig
~~~

để xem mapping sau khi bạn ALTER.

### 29.4. Metadata không thay thế ts_debug

Catalog cho biết dictionary nào được map và theo thứ tự. `ts_debug` cho biết **với token thực tế**, dictionary nào nhận token và lexeme cuối cùng là gì. Cần cả hai khi điều tra lỗi FTS.

## 30. Query với configuration tường minh

Đối với bài viết tiếng Anh:

~~~sql
SELECT
    article_id,
    title
FROM fts_lab.articles
WHERE lang = 'en'
  AND to_tsvector(
      'pg_catalog.english',
      title || ' ' || body
  ) @@ plainto_tsquery(
      'pg_catalog.english',
      'running fox'
  )
ORDER BY article_id;
~~~

### 30.1. Tại sao dùng cùng configuration?

Cả hai phía được chuẩn hóa theo `english`; cách stemming và stopwords nhất quán.

### 30.2. Nếu dùng simple ở query

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'runners are running'
    ) @@ plainto_tsquery(
        'pg_catalog.simple',
        'running'
    ) AS mismatched_config;
~~~

Vì vector tiếng Anh có thể lưu lexeme `run` trong khi query simple dùng `running`, kết quả có thể **không match**. Đây là lỗi phổ biến khi index tạo bằng configuration A nhưng API dùng configuration B.

### 30.3. Hai config khác nhau không luôn sai

Đôi khi cấu hình cố ý khác nhưng tương thích ở nhóm lexeme nhất định. Tuy nhiên, muốn bảo đảm recall nhất quán thì cần **quy tắc thiết kế và kiểm thử cụ thể**, không dựa vào may mắn.

## 31. Tạo cột tsvector lưu sẵn

Nếu ứng dụng tìm nhiều lần trên cùng tài liệu, việc tạo lại `to_tsvector` cho mọi row trong mỗi query có thể tốn CPU.

Một lựa chọn là **generated tsvector column**:

~~~sql
ALTER TABLE fts_lab.articles
ADD COLUMN search_vector tsvector
GENERATED ALWAYS AS (
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(title, '')
        ),
        'A'
    )
    ||
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(body, '')
        ),
        'B'
    )
) STORED;
~~~

### 31.1. Hai điểm thiết kế

- Dùng `english` **tường minh**, không phụ thuộc session default.
- Tạo vector riêng cho `title` và `body` rồi áp **trọng số A/B** trước khi nối, giúp ranking ưu tiên match trong tiêu đề.

### 31.2. Giới hạn ngôn ngữ của lab

Cột `search_vector` trên dùng English cho **mọi bài**, kể cả `lang='vi'`. Nó đủ để minh họa generated column và GIN, nhưng không phải cấu hình đa ngôn ngữ tối ưu. Phần sau sẽ trình bày query/index khác cho tiếng Việt.

### 31.3. Stored generated column

`STORED` nghĩa là giá trị vector được lưu khi tạo/cập nhật hàng, không phải tính lại cho mỗi lần `SELECT`. Nó tăng dung lượng và chi phí ghi nhưng có thể giảm CPU ở truy vấn tìm kiếm lặp.

### 31.4. Tại sao không dùng to_tsvector(body) không truyền config?

Biểu thức với config ngầm phụ thuộc `default_text_search_config` của session. Đối với generated column/expression index, nên dùng hàm với **configuration cố định** để đáp ứng yêu cầu về tính bất biến của biểu thức và tránh thay đổi ngữ nghĩa giữa các session.

## 32. GIN index cho tsvector

~~~sql
CREATE INDEX idx_articles_search_vector
ON fts_lab.articles
USING gin (search_vector);

ANALYZE fts_lab.articles;
~~~

Truy vấn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    article_id,
    title
FROM fts_lab.articles
WHERE lang = 'en'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.english',
      'running fox'
  );
~~~

### 32.1. GIN tìm lexeme, không tự sắp thứ tự ranking

GIN giúp truy cập tài liệu chứa những lexeme phù hợp. Nếu query yêu cầu:

~~~sql
ORDER BY ts_rank(search_vector, query) DESC
~~~

planner vẫn có thể cần tính điểm và sắp xếp những tài liệu match; GIN không tự đảm bảo thứ tự ranking mong muốn.

### 32.2. Query có đúng tsvector?

Nếu bạn tạo index trên `search_vector` nhưng query lại:

~~~sql
WHERE to_tsvector('pg_catalog.simple', body) @@ ...
~~~

đó là **biểu thức khác**, không mặc nhiên dùng GIN trên `search_vector`.

### 32.3. Bảng nhỏ thường Seq Scan

Lab có tám bài viết, nên PostgreSQL hoàn toàn có thể chọn `Seq Scan` rẻ hơn GIN. Không kết luận chỉ mục bị lỗi nếu planner không dùng nó cho vài dòng.

## 33. Expression GIN index không cần cột tsvector

Nếu không muốn lưu `tsvector` riêng:

~~~sql
CREATE INDEX idx_articles_body_english_fts
ON fts_lab.articles
USING gin (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        body
    )
);
~~~

Query khớp biểu thức:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE to_tsvector(
        'pg_catalog.english'::regconfig,
        body
    ) @@ plainto_tsquery(
        'pg_catalog.english',
        'dictionary parser'
    );
~~~

### 33.1. Expression của index và query phải tương thích

Một index trên `to_tsvector('english',body)` không tự là index của `to_tsvector('english',title||' '||body)`.

### 33.2. Không cần tạo cả hai loại index trong production

Trong bài có **cả generated-column GIN lẫn expression GIN** để phân biệt hai thiết kế. Một hệ thống thật thường chọn theo workload, tần suất cập nhật, lưu trữ, ranking và query patterns. Giữ index trùng mục đích làm tăng chi phí ghi.

### 33.3. Cập nhật từ nguồn

Expression index được PostgreSQL duy trì khi các cột ảnh hưởng thay đổi; stored vector cũng được tính lại theo biểu thức generated column. Nhưng khi **chính mapping/dictionary rules thay đổi**, cơ chế tự cập nhật row do DML **không có nghĩa toàn bộ dữ liệu cũ lập tức tái chuẩn hóa**.

## 34. Ranking bằng ts_rank

~~~sql
WITH q AS (
    SELECT plainto_tsquery(
        'pg_catalog.english',
        'search parser'
    ) AS query
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, q.query) AS rank
FROM fts_lab.articles AS a
CROSS JOIN q
WHERE a.lang = 'en'
  AND a.search_vector @@ q.query
ORDER BY rank DESC, a.article_id;
~~~

### 34.1. Tại sao title có trọng số A?

Trong generated column, lexeme từ tiêu đề nhận weight `A` và từ body nhận `B`. Một hàm ranking có thể tận dụng weight để ưu tiên match từ các vùng quan trọng hơn.

### 34.2. Ranking không bằng độ đúng tuyệt đối

`ts_rank`/`ts_rank_cd` cung cấp các mô hình tính điểm từ thông tin lexeme, frequency, weights và vị trí. Chúng không đánh giá mọi yếu tố nghiệp vụ như độ mới, uy tín nguồn hoặc mức độ cá nhân hóa.

### 34.3. LIMIT và số tài liệu được xét

~~~sql
ORDER BY rank DESC
LIMIT 20
~~~

giới hạn số dòng cuối, nhưng PostgreSQL vẫn có thể phải tính rank của **nhiều tài liệu match** rồi chọn top 20. GIN giúp lọc candidates, không tự khiến tính rank miễn phí.

## 35. Highlight bằng ts_headline

~~~sql
SELECT
    article_id,
    title,
    ts_headline(
        'pg_catalog.english',
        body,
        plainto_tsquery(
            'pg_catalog.english',
            'running fox'
        )
    ) AS excerpt
FROM fts_lab.articles
WHERE lang = 'en'
  AND search_vector @@ plainto_tsquery(
      'pg_catalog.english',
      'running fox'
  );
~~~

`ts_headline` tạo đoạn văn bản có nhấn mạnh phần match theo các tùy chọn. Kết quả của nó là **text có markup**, không phải HTML đã được sanitize mặc định cho mọi ứng dụng.

### 35.1. Cẩn thận khi hiển thị trên web

Nếu ứng dụng render HTML, cần xử lý escaping/sanitization đúng ngữ cảnh để tránh XSS khi nội dung nguồn không đáng tin. Không chèn thẳng một chuỗi highlight vào DOM như HTML an toàn.

### 35.2. Dùng cùng configuration

Để highlight nhất quán, truyền configuration phù hợp với vector/query và dữ liệu nguồn.

### 35.3. Highlight không thay văn bản gốc

`ts_headline` đọc nội dung gốc và sinh đoạn hiển thị; tsvector không đủ để khôi phục nguyên văn mọi từ, dấu câu, định dạng.

## 36. FTS tiếng Việt: cần hiểu giới hạn

Thử:

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.simple',
        'Tìm kiếm văn bản tiếng Việt'
    ) AS simple_vi;
~~~

Configuration `simple` có thể giữ những token văn bản ở dạng chữ thường mà không áp stemming tiếng Anh.

### 36.1. Dấu tiếng Việt và tokenization

Parser mặc định xử lý các ký tự Unicode theo quy tắc của nó, nhưng **không tự hiểu đầy đủ tất cả từ ghép tiếng Việt**. Cụm `cơ sở dữ liệu` có thể được tách thành nhiều token theo khoảng trắng, trong khi về ngôn ngữ có những đơn vị nhiều âm tiết.

### 36.2. English stemming có thể làm sai kỳ vọng

~~~sql
SELECT
    to_tsvector(
        'pg_catalog.english',
        'Tìm kiếm dữ liệu'
    ) AS english_on_vi,
    to_tsvector(
        'pg_catalog.simple',
        'Tìm kiếm dữ liệu'
    ) AS simple_on_vi;
~~~

Không coi sự xuất hiện của lexemes trong cả hai kết quả là bằng chứng English stemmer hiểu tiếng Việt.

### 36.3. Unaccent có đánh đổi

Nếu yêu cầu tìm không phân biệt dấu, extension `unaccent` hoặc normalization tương ứng có thể là một thành phần. Tuy nhiên việc bỏ dấu làm một số từ khác nghĩa trở nên giống nhau, và không thay giải pháp tách từ/ngữ nghĩa tiếng Việt.

### 36.4. Tùy mức yêu cầu

Một số hướng:

- Dùng `simple` với tokenization mặc định và xác minh chất lượng trên corpus thực.
- Sử dụng dictionary/tokenizer dành cho tiếng Việt (nếu có extension phù hợp).
- Dùng trigram cho chuỗi con/tìm tên.
- Dùng một search service có tokenizer và ranking chuyên biệt khi yêu cầu cao.

Không có một configuration duy nhất tối ưu đồng thời cho mọi ngôn ngữ và domain.

## 37. Thực hành chỉ mục riêng cho tài liệu tiếng Việt

Trong lab đã có vector generated theo English. Với những tài liệu `lang='vi'`, có thể thử **expression GIN index** theo `simple`:

~~~sql
CREATE INDEX idx_articles_vi_simple_fts
ON fts_lab.articles
USING gin (
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        title || ' ' || body
    )
)
WHERE lang = 'vi';
~~~

Query tương ứng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE lang = 'vi'
  AND to_tsvector(
      'pg_catalog.simple'::regconfig,
      title || ' ' || body
  ) @@ plainto_tsquery(
      'pg_catalog.simple',
      'tìm kiếm'
  );
~~~

### 37.1. Vì sao partial index?

Chỉ mục này tập trung vào hàng có `lang='vi'`. Query phải có điều kiện ngôn ngữ phù hợp để planner nhận ra những hàng trong partial index bao phủ yêu cầu.

### 37.2. Vì sao không dùng chỉ mục English generated?

Vector `search_vector` trong lab được tạo bằng English cho cả tài liệu tiếng Việt. Một query normalize bằng `simple` có thể sinh lexemes khác, nên không nên dùng hai cấu hình bất nhất.

### 37.3. Phạm vi hỗ trợ

Đây là cách **thiết kế kỹ thuật tối thiểu**, không đảm bảo chất lượng tìm kiếm tiếng Việt ở cấp ngôn ngữ. Cần bộ thử nghiệm từ khóa có dấu/không dấu, cụm từ nhiều âm tiết, tên riêng, tiếng lóng và từ viết tắt.

## 38. Thiết kế đa ngôn ngữ với config theo từng hàng

Nếu bảng có cột `lang`, có thể chọn configuration theo ngôn ngữ.

Ví dụ truy vấn:

~~~sql
SELECT article_id, title, lang
FROM fts_lab.articles
WHERE (
    lang = 'en'
    AND search_vector @@ plainto_tsquery(
        'pg_catalog.english',
        'database'
    )
)
OR (
    lang = 'vi'
    AND to_tsvector(
        'pg_catalog.simple',
        title || ' ' || body
    ) @@ plainto_tsquery(
        'pg_catalog.simple',
        'cơ sở dữ liệu'
    )
);
~~~

### 38.1. Hai nhánh có hai chiến lược

- English: dùng stored vector + GIN tương ứng.
- Vietnamese: dùng expression với `simple` và có thể tận dụng partial GIN index tiếng Việt vừa tạo.

### 38.2. Query hỗn hợp phức tạp hơn query một ngôn ngữ

Trong ứng dụng, nếu ngôn ngữ tìm kiếm đã biết, thường có thể giới hạn truy vấn ở một nhánh và configuration tương ứng. Nếu không biết, cần quy tắc detect/người dùng chọn ngôn ngữ và cách hợp nhất/rank kết quả.

### 38.3. Không so rank giữa ngôn ngữ như con số tuyệt đối

Các từ điển có mức stemming, stopwords và tokenization khác nhau, khiến phân bố điểm rank có thể khác đáng kể. Nếu gộp đa ngôn ngữ, nên thiết kế công thức ranking/normalization của ứng dụng có kiểm thử.

## 39. Thay đổi configuration khi đã có index: rủi ro dữ liệu cũ

Giả sử bạn xây index trên:

~~~sql
to_tsvector('fts_lab.en_no_stem'::regconfig, body)
~~~

rồi thay mapping của `fts_lab.en_no_stem` từ `simple` sang `english_stem`.

### 39.1. Vấn đề

Lexeme được tạo **theo mapping cũ** có thể khác mapping mới:

~~~text
Mapping cũ: running -> running
Mapping mới: running -> run
~~~

Nhưng dữ liệu trong **expression index** đã được dựng theo quy tắc cũ và không tự biến đổi chỉ vì bạn đổi mapping.

### 39.2. Cần lên kế hoạch rebuild

Nếu một expression GIN index phụ thuộc configuration đã đổi, cần đánh giá việc **REINDEX** index tương ứng để biểu thức được tính lại trên dữ liệu gốc theo quy tắc mới.

### 39.3. Stored tsvector khác expression index

Nếu bảng đã lưu `tsvector` trong cột generated STORED, thay mapping **không tự kích hoạt UPDATE mọi hàng cũ**. Cần có kế hoạch **tái tính dữ liệu vector** từ text nguồn (chẳng hạn thông qua backfill/update/đổi biểu thức theo cơ chế migration phù hợp), rồi đảm bảo index trên vector được đồng bộ.

**REINDEX một index trên cột tsvector đã lưu không tự tái tạo lexeme từ văn bản nguồn**; nó chỉ index lại **giá trị tsvector đang được lưu**.

### 39.4. Nếu dùng trigger để cập nhật tsvector

Với thiết kế dùng trigger/manual update thay vì generated column, cần chạy backfill tương ứng và kiểm tra trigger sử dụng configuration tường minh. Nếu trigger thay đổi mà hàng cũ không được cập nhật, index có thể chứa lexemes thuộc nhiều thế hệ chuẩn hóa khác nhau.

### 39.5. Tệp dictionary/stopwords cũng là một phần versioning

Ngay cả khi SQL configuration không đổi, một bản nâng cấp/thay thế tệp dictionary hoặc extension có thể ảnh hưởng kết quả lexeme. Quản lý FTS migrations nên bao gồm **phiên bản cấu hình và quy trình rebuild/backfill**.

## 40. Đo hiệu năng và đọc EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    'parser dictionary'
);
~~~

Các thông tin cần quan sát:

| Thành phần | Cách hiểu |
| --- | --- |
| `Seq Scan` | PostgreSQL quét tuần tự bảng; thường hợp lý với bảng nhỏ |
| `Bitmap Index Scan` | Tận dụng GIN để tìm tài liệu/tuple candidates |
| `Bitmap Heap Scan` | Lấy tuple tại các heap blocks có khả năng match |
| `Index Cond` | Điều kiện được index hỗ trợ |
| `Recheck Cond` | Điều kiện được kiểm tra lại theo kế hoạch |
| `Filter` | Điều kiện xử lý thêm sau phần truy cập |
| `actual rows` | Hàng node thực sự trả trung bình mỗi loop |
| `loops` | Số lần node được thực thi |
| `Buffers: shared hit/read` | Hoạt động trên các block/buffers |
| `Execution Time` | Thời gian thực thi tổng của statement theo instrumentation |

### 40.1. GIN không đảm bảo planner dùng nó

Với tám hàng, `Seq Scan` có thể nhanh hơn GIN. Trên bảng nhiều triệu tài liệu, index GIN có thể hữu ích cho những lexeme chọn lọc cao, nhưng truy vấn từ quá phổ biến vẫn có thể phải đọc nhiều kết quả.

### 40.2. Ranking có thể cần Sort

Ngay cả khi GIN lọc candidates, `ORDER BY ts_rank(...) DESC` có thể đòi tính điểm và sort. Không coi “dùng index” là “không có Sort”.

### 40.3. Stopwords ảnh hưởng selectivity

Nếu một từ được loại thành stopword, nó không thể được dùng như một lexeme độc lập để giảm số kết quả. Một query chỉ chứa stopwords không được coi như truy vấn có selective index condition.

### 40.4. Buffers không phải số hàng

`shared hit=100` nghĩa là các lượt truy cập shared buffers, không phải có đúng 100 tài liệu được đọc. Một block có thể chứa nhiều tuple, và các node cha/con có thống kê buffers mang tính inclusive.

## 41. An toàn khi nhận query từ người dùng

### 41.1. Luôn bind tham số

Ví dụ chuẩn bị statement:

~~~sql
PREPARE search_articles(text) AS
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english',
    $1
);

EXECUTE search_articles('running fox');
~~~

### 41.2. Không nối input thành SQL

Không ghép:

~~~text
"... @@ to_tsquery('english','" + user_input + "')"
~~~

vì có nguy cơ SQL injection và lỗi escaping/cú pháp. Sử dụng parameterized SQL đúng kiểu.

### 41.3. FTS vẫn có thể bị lạm dụng về tài nguyên

Người dùng có thể gửi truy vấn rất dài, nhiều OR/NOT hoặc từ khóa cực phổ biến. Các trường hợp này có thể gây CPU, memory, số candidates lớn hoặc ranking tốn kém. Nên giới hạn kích thước input, page size, statement timeout và tần suất query theo nhu cầu.

### 41.4. Không cho xem tài liệu không có quyền

FTS là cơ chế tìm kiếm, không phải permission boundary. Các predicate tenant, ownership, RLS hoặc ACL vẫn phải được áp đúng cho từng query.

### 41.5. Highlight cần escaping

Không nhúng trực tiếp output chứa markup của `ts_headline` vào HTML không được xử lý, nhất là khi body do người dùng nhập.

## 42. Các lỗi thường gặp

### Lỗi 1. Nghĩ parser thực hiện stemming

Parser chỉ tách và phân loại token; dictionary mới chuẩn hóa lexeme hoặc loại stopword.

### Lỗi 2. Nghĩ dictionary quyết định token type

Token type do parser phân loại. Configuration dùng token type đó để chọn dictionary chain.

### Lỗi 3. Nghĩ mọi token sinh một lexeme

Dictionary có thể sinh nhiều lexeme, không lexeme, hoặc từ chối token để dictionary khác xử lý.

### Lỗi 4. Nhầm SQL NULL với mảng rỗng của ts_lexize

SQL `NULL` thường biểu thị dictionary không nhận token; mảng rỗng biểu thị token được nhận là stop word.

### Lỗi 5. Đặt simple ở đầu chain rồi mong english_stem chạy

`simple` thường nhận token, nên dictionary phía sau không được gọi theo cơ chế fallback thường.

### Lỗi 6. Dùng COPY rồi nghĩ configuration mới hoàn toàn độc lập về mọi file

COPY tạo mapping riêng, nhưng dictionaries có thể vẫn tham chiếu đối tượng/tệp từ điển chung. Thay đổi dictionary/rules phụ thuộc có thể ảnh hưởng nhiều configurations.

### Lỗi 7. Bỏ mapping cho token type quan trọng

Token types không có mapping có thể bị bỏ khỏi tsvector. Xem `ts_token_type` và `ts_debug`.

### Lỗi 8. Coi stopwords như xóa từ khỏi body

Stopwords ảnh hưởng tsvector/tsquery; văn bản nguồn vẫn giữ nguyên.

### Lỗi 9. Nghĩ stopwords không ảnh hưởng phrase distance

Các vị trí có thể vẫn phản ánh khoảng cách token bị loại; `phraseto_tsquery` biểu diễn những khoảng cách đó.

### Lỗi 10. Dùng plainto_tsquery khi muốn phrase liền nhau

`plainto_tsquery` thường kết hợp lexeme bằng AND, không bắt buộc đúng thứ tự. Dùng `phraseto_tsquery` hoặc cú pháp phrase phù hợp.

### Lỗi 11. Truyền raw input vào to_tsquery

`to_tsquery` đòi cú pháp hợp lệ; input người dùng có thể làm lỗi. Cân nhắc `plainto_tsquery`/`websearch_to_tsquery`.

### Lỗi 12. Bỏ qua tsquery rỗng

Input chỉ có stopwords có thể tạo query không có lexeme, cần ứng dụng xử lý rõ.

### Lỗi 13. Dùng default_text_search_config ngầm ở mọi nơi

Các session có thể khác cấu hình; query và index tạo lexeme khác nhau. Dùng configuration tường minh cho dữ liệu/index quan trọng.

### Lỗi 14. Dùng simple ở query, english ở vector

Stemming khác nhau khiến một số từ không match dù hình thức gần giống.

### Lỗi 15. Nghĩ english là tokenizer tiếng Việt đầy đủ

Không. Cần xem yêu cầu tách từ, từ ghép, bỏ dấu và ranking theo corpus tiếng Việt.

### Lỗi 16. Nghĩ unaccent hiểu đồng nghĩa/ngữ nghĩa

Unaccent là biến đổi ký tự/dấu theo rules, không phải bộ từ điển từ ghép hoặc semantic search.

### Lỗi 17. Nghĩ mọi từ có nghĩa gần nhau được English stemmer gộp

Stemming xử lý biến thể hình thái, không phải danh sách synonym toàn diện.

### Lỗi 18. Đổi mapping rồi không rebuild index/vector

Lexeme của dữ liệu cũ có thể không khớp query mới. Cần kế hoạch reindex/backfill.

### Lỗi 19. REINDEX cột tsvector cũ rồi tưởng dữ liệu được chuẩn hóa lại

REINDEX trên stored tsvector chỉ dùng lại lexemes đang lưu. Phải tái tính vector từ text nguồn nếu dictionary thay đổi.

### Lỗi 20. Nghĩ GIN tự sort theo rank

GIN giúp tìm lexemes/candidates, không trả thứ tự `ts_rank` miễn phí.

### Lỗi 21. Coi Seq Scan trên bảng nhỏ là thất bại

Planner có thể đúng khi đọc tuần tự vài dòng; cần đo trên dữ liệu đại diện.

### Lỗi 22. Chỉ đo tốc độ, không kiểm thử chất lượng tìm kiếm

Index rất nhanh nhưng dictionary bỏ từ quan trọng hoặc query không match thì trải nghiệm vẫn kém. Cần tập truy vấn mẫu với expected documents.

### Lỗi 23. Dùng one-arg to_tsvector trong expression index

Biểu thức phụ thuộc default configuration không thích hợp cho index bất biến/ổn định logic. Nên truyền regconfig cố định.

### Lỗi 24. Nghĩ ts_headline là HTML an toàn

Đây là text có markup do FTS tạo; ứng dụng phải xử lý escaping/sanitization phù hợp trước khi render.

### Lỗi 25. Cập nhật từ điển không có quy trình phiên bản

Thay stopwords/synonym/extension có thể làm thay đổi lexeme của dữ liệu cũ. Dùng migration và rollback plan.

### Lỗi 26. Xem token bằng split theo dấu cách

Parser hỗ trợ email, URL, dấu nối và nhiều token types; dấu cách không mô phỏng được.

## 43. Bài tập thực hành

Các bài áp dụng với PostgreSQL và schema `fts_lab`. Những câu lệnh thay cấu hình/chỉ mục chỉ nên thực hiện trong **database lab** hoặc môi trường đã được cho phép.

### Bài 1. Bốn vai trò

Giải thích vai trò của parser, dictionary, stop word và text search configuration trong một câu.

### Bài 2. Token vs lexeme

Sự khác nhau giữa token `running` và lexeme `run` là gì?

### Bài 3. Token type

Viết SQL xem các token types của parser mặc định.

### Bài 4. ts_parse

Viết SQL tách token từ câu `The user emailed team@example.org`.

### Bài 5. ts_debug

Viết SQL xem token, dictionary và lexeme khi xử lý `The runners are running` bằng `english`.

### Bài 6. ts_lexize

So sánh kết quả `ts_lexize` cho `Running` với dictionary `simple` và `english_stem`.

### Bài 7. Stopword

Vì sao `ts_lexize('english_stem','the')` có thể trả mảng rỗng chứ không phải SQL NULL?

### Bài 8. Thứ tự dictionary

Vì sao mapping `simple, english_stem` thường không cho kết quả stemming đối với token `running`?

### Bài 9. Không có mapping

Điều gì xảy ra với một token type mà configuration không gán dictionary?

### Bài 10. Xem default config

Viết SQL xem `default_text_search_config` của session.

### Bài 11. Cùng config hai phía

Vì sao `to_tsvector('english', ...) @@ plainto_tsquery('simple', ...)` dễ gây false negatives?

### Bài 12. Plain query

Viết truy vấn tìm những tài liệu có cả `parser` và `dictionary` qua `plainto_tsquery`.

### Bài 13. To_tsquery logic

Viết `to_tsquery` cho “postgresql AND (search OR index)”.

### Bài 14. Phrase

Viết `phraseto_tsquery` tìm cụm `quick fox` và nêu khác biệt với plain query.

### Bài 15. Stopwords và phrase

Với cụm `quick and fox`, vì sao phrase query có thể giữ khoảng cách hai vị trí?

### Bài 16. Truy vấn stopwords rỗng

Viết SQL dùng `numnode` để phát hiện input `the and of` không có lexeme hữu ích theo English.

### Bài 17. Web search

Viết `websearch_to_tsquery` cho input có phrase `"quick fox"` hoặc `running`.

### Bài 18. CREATE CONFIGURATION COPY

Tạo configuration `fts_lab.my_english` dựa trên `pg_catalog.english`.

### Bài 19. ALTER MAPPING

Đổi mapping `asciiword` và `word` sang `pg_catalog.simple`.

### Bài 20. PARSER config

Tạo configuration mới dùng `pg_catalog.default` parser, rồi thêm mapping `asciiword` với dictionary `simple`.

### Bài 21. Dictionary stopwords

Tạo một dictionary từ template `simple` với stopword file `english` và giải thích nó khác English stemmer thế nào.

### Bài 22. Catalog mapping

Viết SQL tìm các dictionary mapped với token type `asciiword` trong `pg_catalog.english`.

### Bài 23. Generated tsvector

Viết DDL thêm stored generated tsvector từ `title` và `body` theo English config; title weight A, body weight B.

### Bài 24. GIN

Tạo GIN index trên cột `search_vector`.

### Bài 25. Expression GIN

Tạo expression GIN index trên `to_tsvector('english',body)` dùng configuration tường minh.

### Bài 26. Rank

Viết query lọc và sắp xếp bài viết theo `ts_rank` với từ khóa `parser dictionary`.

### Bài 27. Highlight

Viết query dùng `ts_headline` và nêu điều cần làm khi đưa kết quả lên HTML.

### Bài 28. Tiếng Việt

Vì sao `simple` là một điểm bắt đầu để thử FTS tiếng Việt nhưng không đủ thay tokenizer tiếng Việt chuyên dụng?

### Bài 29. Đa ngôn ngữ

Nếu English dùng `english`, Vietnamese dùng `simple`, vì sao cả vector lẫn tsquery phải theo cùng một chính sách cho mỗi ngôn ngữ?

### Bài 30. Dictionary migration

Khi dictionary đổi `running` từ lexeme `running` sang `run`, cần làm gì với expression index và stored tsvector?

### Bài 31. EXPLAIN

Viết `EXPLAIN (ANALYZE, BUFFERS)` kiểm tra query trên `search_vector` và nêu hai dấu hiệu dùng GIN.

### Bài 32. Phân biệt FTS và substring

Người dùng muốn tìm mọi tài liệu có chuỗi `gram` ở giữa `programming`. Vì sao FTS mặc định chưa chắc phù hợp?

### Bài 33. Query parameter

Viết prepared statement với `websearch_to_tsquery` nhận input kiểu `text`, không ghép SQL thủ công.

### Bài 34. Check quyền dữ liệu

FTS index có tự bảo đảm người dùng chỉ xem bài viết được phép không? Phải bổ sung điều gì?

## 44. Gợi ý lời giải

### Bài 1–2. Chuỗi xử lý

Parser tách và phân loại token; configuration gán token types cho chuỗi dictionary; dictionary biến token thành lexeme hoặc stopword; stopword bị loại nhưng có thể ảnh hưởng vị trí. `running` là token nguồn; `run` là lexeme chuẩn hóa theo stemming tiếng Anh.

### Bài 3. Token types

~~~sql
SELECT tokid, alias, description
FROM ts_token_type('pg_catalog.default'::regparser)
ORDER BY tokid;
~~~

### Bài 4. Parser

~~~sql
SELECT tokid, token
FROM ts_parse(
    'pg_catalog.default'::regparser,
    'The user emailed team@example.org'
);
~~~

### Bài 5. ts_debug

~~~sql
SELECT alias, token, dictionaries, dictionary, lexemes
FROM ts_debug(
    'pg_catalog.english',
    'The runners are running'
);
~~~

### Bài 6–8. Dictionary chain

~~~sql
SELECT
    ts_lexize(
        'pg_catalog.simple'::regdictionary,
        'Running'
    ),
    ts_lexize(
        'pg_catalog.english_stem'::regdictionary,
        'Running'
    );
~~~

`simple` thường nhận và lowercase token thành `running`; `english_stem` có thể stem thành `run`. Dictionary trả mảng rỗng là **đã nhận stopword**, không phải không nhận token. Nếu `simple` đứng trước và đã nhận token, stemmer sau không chạy theo chuỗi fallback thông thường.

### Bài 9–11. Mapping và config

Token type không có mapping có thể bị bỏ khỏi vector/query. Xem:

~~~sql
SHOW default_text_search_config;
~~~

Vector English và query Simple có thể khác lexemes, gây false negatives.

### Bài 12. Plain query

~~~sql
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    'parser dictionary'
);
~~~

### Bài 13. Logic

~~~sql
SELECT to_tsquery(
    'pg_catalog.english',
    'postgresql & (search | index)'
);
~~~

### Bài 14–15. Phrase

~~~sql
SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick fox'
);

SELECT phraseto_tsquery(
    'pg_catalog.english',
    'quick and fox'
);
~~~

`quick fox` thường là `'quick' <-> 'fox'`; `quick and fox` có stopword `and` khiến khoảng cách vị trí được phản ánh qua `<2>`. Plain query không yêu cầu lexemes ở cạnh nhau.

### Bài 16. Empty tsquery

~~~sql
SELECT numnode(
    plainto_tsquery(
        'pg_catalog.english',
        'the and of'
    )
);
~~~

Nếu đều là stopwords, kết quả bằng 0.

### Bài 17. Web input

~~~sql
SELECT websearch_to_tsquery(
    'pg_catalog.english',
    '"quick fox" OR running'
);
~~~

### Bài 18–19. COPY và ALTER

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.my_english (
    COPY = pg_catalog.english
);

ALTER TEXT SEARCH CONFIGURATION fts_lab.my_english
ALTER MAPPING FOR asciiword, word
WITH pg_catalog.simple;
~~~

### Bài 20. Parser-based configuration

~~~sql
CREATE TEXT SEARCH CONFIGURATION fts_lab.only_ascii (
    PARSER = pg_catalog.default
);

ALTER TEXT SEARCH CONFIGURATION fts_lab.only_ascii
ADD MAPPING FOR asciiword
WITH pg_catalog.simple;
~~~

### Bài 21. Dictionary stopwords

~~~sql
CREATE TEXT SEARCH DICTIONARY fts_lab.stop_en_answer (
    TEMPLATE = pg_catalog.simple,
    StopWords = english
);
~~~

Nó loại stopwords theo danh sách, không tự stemming như `english_stem`. Cần tệp stopwords phù hợp có sẵn trên PostgreSQL server.

### Bài 22. Catalog

~~~sql
SELECT
    t.alias,
    m.mapseqno,
    d.dictname
FROM pg_ts_config AS c
JOIN pg_ts_config_map AS m
    ON m.mapcfg = c.oid
JOIN pg_ts_dict AS d
    ON d.oid = m.mapdict
CROSS JOIN LATERAL ts_token_type(
    c.cfgparser::regparser
) AS t
WHERE c.oid = 'pg_catalog.english'::regconfig
  AND t.tokid = m.maptokentype
  AND t.alias = 'asciiword'
ORDER BY m.mapseqno;
~~~

### Bài 23. Stored vector

~~~sql
ALTER TABLE fts_lab.articles
ADD COLUMN search_vector_answer tsvector
GENERATED ALWAYS AS (
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(title, '')
        ), 'A'
    ) ||
    setweight(
        to_tsvector(
            'pg_catalog.english'::regconfig,
            coalesce(body, '')
        ), 'B'
    )
) STORED;
~~~

Đây là ví dụ bài tập thêm **cột thứ hai**, khác `search_vector` đã tạo trong lab. Nếu không muốn thêm cột trùng mục đích, chỉ cần dùng câu lệnh làm mẫu.

### Bài 24–25. GIN

~~~sql
CREATE INDEX idx_articles_search_answer
ON fts_lab.articles USING gin (search_vector);

CREATE INDEX idx_articles_body_answer
ON fts_lab.articles
USING gin (
    to_tsvector(
        'pg_catalog.english'::regconfig,
        body
    )
);
~~~

Trong lab có thể đã có index tương đương. Không tạo nhiều index gần trùng trong production.

### Bài 26. Ranking

~~~sql
WITH query AS (
    SELECT plainto_tsquery(
        'pg_catalog.english',
        'parser dictionary'
    ) AS q
)
SELECT
    a.article_id,
    a.title,
    ts_rank(a.search_vector, query.q) AS score
FROM fts_lab.articles AS a
CROSS JOIN query
WHERE a.search_vector @@ query.q
ORDER BY score DESC, a.article_id;
~~~

### Bài 27. Highlight

~~~sql
SELECT
    article_id,
    ts_headline(
        'pg_catalog.english',
        body,
        plainto_tsquery(
            'pg_catalog.english',
            'running fox'
        )
    ) AS excerpt
FROM fts_lab.articles;
~~~

Nếu hiển thị kết quả trong HTML, phải escaping/sanitization đúng ngữ cảnh và không coi markup từ nguồn không đáng tin là an toàn.

### Bài 28–29. Tiếng Việt và đa ngôn ngữ

`simple` có thể giữ nhiều token tiếng Việt nhưng không có tokenizer từ ghép/stemming tiếng Việt hoàn chỉnh. Với mỗi ngôn ngữ, phải thống nhất configuration của vector và tsquery; một vector English không tự tương thích với query Simple.

### Bài 30. Migration

Với **expression index**, cần đánh giá `REINDEX` sau khi đổi mapping/dictionary. Với **stored tsvector**, cần **tái tính giá trị vector từ text gốc** rồi đồng bộ index; REINDEX trên cột vector cũ không sửa nội dung lexeme đã lưu.

### Bài 31. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ plainto_tsquery(
    'pg_catalog.english',
    'database'
);
~~~

Trong một plan dùng GIN thường có thể thấy `Bitmap Index Scan` trên index GIN và `Bitmap Heap Scan` để kiểm tra/lấy hàng. Nhưng bảng tám dòng có thể dùng Seq Scan và vẫn hợp lý.

### Bài 32. FTS không phải substring

FTS tìm lexemes/từ đã chuẩn hóa, không mặc định tìm mọi đoạn nằm trong từ lớn. Nếu nhu cầu là `'%gram%'`, xem `LIKE`/`ILIKE` và `pg_trgm` theo workload.

### Bài 33. Prepared statement

~~~sql
PREPARE search_articles_answer(text) AS
SELECT article_id, title
FROM fts_lab.articles
WHERE search_vector @@ websearch_to_tsquery(
    'pg_catalog.english',
    $1
);

EXECUTE search_articles_answer('"quick fox"');
~~~

### Bài 34. Access control

Không. FTS/GIN chỉ tìm theo nội dung. Query vẫn cần predicate phân quyền/tenant hoặc cơ chế RLS/ACL phù hợp để không trả tài liệu mà người dùng không có quyền xem.

## 45. Bảng tra cứu nhanh

| Muốn làm gì? | Công cụ/cú pháp |
| --- | --- |
| Xem parser token types | `ts_token_type('pg_catalog.default'::regparser)` |
| Tách một văn bản thành token | `ts_parse('pg_catalog.default'::regparser, text)` |
| Xem chi tiết pipeline | `ts_debug('pg_catalog.english', text)` |
| Thử riêng dictionary | `ts_lexize('pg_catalog.english_stem'::regdictionary, token)` |
| Xem config mặc định | `SHOW default_text_search_config` |
| Tokenize/stem văn bản | `to_tsvector('pg_catalog.english', text)` |
| Giữ tokens đơn giản | `to_tsvector('pg_catalog.simple', text)` |
| Tạo query từ câu thường | `plainto_tsquery(config, text)` |
| Tạo query phrase | `phraseto_tsquery(config, text)` |
| Tạo query cú pháp web | `websearch_to_tsquery(config, text)` |
| Tạo query có toán tử FTS | `to_tsquery(config, expression)` |
| Kiểm tra match | `tsvector @@ tsquery` |
| Kiểm tra tsquery rỗng | `numnode(tsquery)` |
| Tạo configuration theo mẫu | `CREATE TEXT SEARCH CONFIGURATION ... (COPY = ...)` |
| Tạo configuration từ parser | `CREATE TEXT SEARCH CONFIGURATION ... (PARSER = ...)` |
| Thay mapping | `ALTER TEXT SEARCH CONFIGURATION ... ALTER MAPPING ... WITH ...` |
| Thêm mapping | `ALTER TEXT SEARCH CONFIGURATION ... ADD MAPPING ... WITH ...` |
| Dictionary bỏ stopwords | `CREATE TEXT SEARCH DICTIONARY ... (TEMPLATE = simple, StopWords = ...)` |
| Xem danh sách mapping | `pg_ts_config_map` + `pg_ts_dict` |
| Xem configs | `pg_ts_config` + `pg_ts_parser` |
| Chỉ mục full text | `CREATE INDEX ... USING gin (tsvector)` |
| Index trực tiếp expression | `USING gin (to_tsvector('english'::regconfig, body))` |
| Trọng số title/body | `setweight(...,'A')`, `setweight(...,'B')` |
| Xếp hạng | `ts_rank(vector, query)` |
| Highlight | `ts_headline(config, text, query)` |
| Đo plan | `EXPLAIN (ANALYZE, BUFFERS)` |
| Đổi dictionary có index cũ | `REINDEX`/backfill theo loại index/vector |

## 46. Checklist thiết kế FTS

1. Người dùng tìm theo **từ**, **cụm từ**, **chuỗi con** hay **ngữ nghĩa**?
2. Ngôn ngữ tài liệu và từ khóa là gì? Có nhiều ngôn ngữ trộn lẫn không?
3. Parser có phân loại đúng email, dấu nối, từ Unicode và các loại token quan trọng không?
4. Mapping đã bao phủ những token types cần thiết chưa?
5. Dictionary có stemming/stopwords phù hợp miền dữ liệu không?
6. Thứ tự dictionary chain có làm dictionary sau bị bỏ qua không?
7. Stopwords có loại mất từ quan trọng của domain không?
8. Phrase queries có cần giữ khoảng cách qua stopwords không?
9. Query chỉ gồm stopwords được ứng dụng xử lý thế nào?
10. `to_tsvector` và `tsquery` có dùng configuration tương thích không?
11. Index/generation có dùng configuration tường minh không?
12. Khi có tiếng Việt, đã kiểm tra từ ghép, dấu và recall trên corpus thực chưa?
13. Nếu dùng unaccent, đã đánh giá tác động tới precision chưa?
14. GIN index nằm trên đúng tsvector/expression mà query thực dùng không?
15. Có chỉ mục gần trùng cần loại bỏ không?
16. Ranking có ưu tiên title và những field quan trọng phù hợp không?
17. Highlight có được render an toàn không?
18. Search endpoint có bind parameters, giới hạn query/page size và phân quyền không?
19. Migration dictionary/stopword/config có kế hoạch REINDEX/backfill không?
20. Đã đo `EXPLAIN`, chất lượng match và latency với corpus đại diện chưa?

## 47. Tổng kết

Full Text Search trong PostgreSQL là một **pipeline có cấu hình**, không chỉ là hàm tìm chuỗi:

1. **Parser** nhận văn bản và tạo các token có loại cụ thể.
2. **Text search configuration** ánh xạ từng token type tới **chuỗi dictionaries**.
3. **Dictionary** chuẩn hóa token thành lexeme, từ chối để dictionary kế tiếp xử lý hoặc loại token như **stop word**; filtering dictionary có thể biến đổi rồi chuyển tiếp.
4. **Stop words** giảm những lexeme không cần thiết nhưng vẫn có thể ảnh hưởng khoảng cách vị trí trong phrase search.
5. **`tsvector` và `tsquery`** phải được tạo với quy tắc tương thích để toán tử `@@` tìm đúng tài liệu.

Muốn hiểu vì sao một từ được tìm thấy hoặc bị bỏ sót, hãy bắt đầu bằng `ts_parse` để xem token, `ts_token_type` để xác định loại, `ts_lexize` để quan sát dictionary, và `ts_debug` để thấy đầy đủ đường đi theo configuration.

Khi đưa FTS vào sản phẩm, **đừng chỉ tập trung vào GIN index**. Index giúp tìm nhanh những lexemes đã được chuẩn hóa; chất lượng kết quả phụ thuộc từ điển, stopwords, ngôn ngữ và consistency giữa vector/query. Mỗi lần thay quy tắc configuration, phải quản lý **rebuild index và tái tính stored vectors** như một migration dữ liệu có tác động tới kết quả.

Nguyên tắc thực hành: **quan sát token → xác định dictionary/stopwords → tạo configuration tường minh → lập vector/query nhất quán → tạo index → đo plan và chất lượng tìm kiếm**. Khi hiểu trọn luồng này, bạn có thể cải thiện cả tốc độ, độ chính xác lẫn khả năng bảo trì của tìm kiếm toàn văn PostgreSQL.
