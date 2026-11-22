# Stopword, độ dài token và cấu hình xây dựng chỉ mục

MySQL Full-Text Search không lập chỉ mục mọi chuỗi ký tự xuất hiện trong văn bản. Trước khi ghi một từ vào FULLTEXT index, bộ phân tích (parser) tách văn bản thành token, loại các stopword và bỏ những token nằm ngoài giới hạn độ dài được cấu hình. Vì vậy, một cụm từ có trong cột TEXT vẫn có thể không tìm thấy nếu nó là stopword, quá ngắn, quá dài hoặc không được parser nhận diện theo cách ứng dụng mong đợi.

Ba nhóm cấu hình ảnh hưởng trực tiếp đến kết quả là:

- **Stopword**: các từ phổ biến bị loại khỏi chỉ mục để giảm nhiễu.
- **Token length**: giới hạn độ dài token được phép đưa vào chỉ mục.
- **Parser và index build**: cách tách token, cấu hình áp dụng cho InnoDB/MyISAM/ngram và thời điểm phải tạo lại FULLTEXT index.

Các giá trị cấu hình của InnoDB và MyISAM không dùng chung. Ngram parser có quy tắc token riêng và bỏ qua các biến min/max word length thông thường. Thay đổi cấu hình sau khi index đã được tạo cũng không tự sửa lại các token cũ; cần xây dựng lại FULLTEXT index để dữ liệu chỉ mục phản ánh chính sách mới.

Bài học này tập trung vào việc hiểu pipeline tạo chỉ mục, chọn stopword và token size phù hợp với dữ liệu, cấu hình theo storage engine, xây dựng lại index an toàn và xác minh token thực tế mà MySQL đã lưu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích parser, token, stopword và inverted index trong MySQL Full-Text Search.
- Nhận biết vì sao từ xuất hiện trong văn bản nhưng không tìm được.
- Phân biệt danh sách stopword mặc định của InnoDB và MyISAM.
- Xem danh sách stopword mặc định của InnoDB.
- Tạo stopword table riêng cho toàn server hoặc cho một FULLTEXT index InnoDB cụ thể.
- Cấu hình stopword file của MyISAM và hiểu cách tắt stopword filtering.
- Phân biệt min/max token size của InnoDB và min/max word length của MyISAM.
- Hiểu tác động của token size lên kích thước index và khả năng tìm kiếm.
- Dùng ngram parser cho tiếng Trung, Nhật, Hàn và dữ liệu không phân tách từ bằng dấu cách.
- Giải thích cách ngram xử lý stopword và khoảng trắng.
- Tạo FULLTEXT index trên một hoặc nhiều cột.
- Xác định thay đổi cấu hình nào cần restart và thay đổi nào cần rebuild index.
- Rebuild FULLTEXT index InnoDB và MyISAM đúng cách.
- Kiểm tra token trong INFORMATION_SCHEMA và chẩn đoán kết quả tìm kiếm.
- Lập kế hoạch triển khai cấu hình index có kiểm soát trên production.

## 1. FULLTEXT index tạo token như thế nào?

FULLTEXT index là inverted index: thay vì lưu mỗi hàng rồi tìm văn bản bằng cách quét toàn bộ chuỗi, MySQL lưu quan hệ giữa token và các document/hàng chứa token đó.

Pipeline khái quát:

    Văn bản trong cột
          |
          v
      FULLTEXT parser
          |
          v
      Tách thành token
          |
          v
      Kiểm tra stopword
          |
          v
      Kiểm tra độ dài token
          |
          v
      Ghi token vào FULLTEXT index
          |
          v
      MATCH(...) AGAINST(...)

Ví dụ văn bản:

    MySQL is a relational database.

Parser chuẩn nhận diện các từ dựa trên ranh giới từ. Stopword như `a` có thể bị loại. Token ngắn hơn giới hạn hoặc dài hơn giới hạn có thể không được ghi vào index. Các token còn lại được lập chỉ mục để phục vụ MATCH ... AGAINST.

Do đó, việc một từ còn nhìn thấy trong SELECT body không chứng minh từ đó đã có trong FULLTEXT index.

### 1.1. Ba khái niệm cần tách biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Token | Đơn vị văn bản parser tạo ra | `database` |
| Stopword | Token bị loại theo danh sách stopword | `the`, `and` |
| Token length | Giới hạn độ dài token được lập chỉ mục | InnoDB mặc định tối thiểu 3 ký tự |

Stopword và token length là hai bộ lọc độc lập. Một token có thể đủ dài nhưng vẫn bị loại vì nằm trong stopword list. Ngược lại, một từ không phải stopword vẫn có thể bị loại vì quá ngắn hoặc quá dài.

### 1.2. Vì sao cần loại một số token?

Những từ xuất hiện quá thường xuyên thường ít giúp phân biệt tài liệu. Nếu mọi bài viết đều có `the`, `is` hoặc `and`, lập chỉ mục chúng có thể làm index lớn và giảm chất lượng xếp hạng.

Giới hạn độ dài cũng có tác dụng kiểm soát index. Các từ rất ngắn thường mang ít thông tin trong một số ngôn ngữ; các chuỗi quá dài có thể là mã, chuỗi ngẫu nhiên hoặc dữ liệu không phải từ tìm kiếm thông thường.

Tuy nhiên, chính sách mặc định không phù hợp với mọi miền dữ liệu. Trong tài liệu kỹ thuật, từ ngắn như `SQL`, `C++` hoặc mã sản phẩm có thể rất quan trọng. Trong tiếng Việt, tiếng Trung, tiếng Nhật hoặc tiếng Hàn, cách phân tách từ cũng cần được xem xét riêng.

## 2. Storage engine quyết định bộ cấu hình token

MySQL có các biến riêng cho FULLTEXT index của InnoDB và MyISAM:

| Nội dung | InnoDB | MyISAM |
|---|---|---|
| Token ngắn nhất | `innodb_ft_min_token_size` | `ft_min_word_len` |
| Token dài nhất | `innodb_ft_max_token_size` | `ft_max_word_len` |
| Stopword mặc định | Danh sách InnoDB tích hợp | Danh sách MyISAM tích hợp |
| Danh sách tùy chỉnh | Stopword table InnoDB | File do `ft_stopword_file` chỉ định |
| Tắt stopword | `innodb_ft_enable_stopword=OFF` | `ft_stopword_file=''` |
| Parser ngram | Có | Có |

Không thay `ft_min_word_len` rồi kỳ vọng FULLTEXT index InnoDB thay đổi. Ngược lại, `innodb_ft_min_token_size` không điều khiển index MyISAM.

### 2.1. Giá trị mặc định phổ biến

| Engine | Minimum | Maximum |
|---|---:|---:|
| InnoDB | 3 | 84 |
| MyISAM | 4 | 84 |

Đây là giá trị mặc định của MySQL 8.4. Hãy kiểm tra cấu hình thật trên server vì quản trị viên có thể đã thay đổi chúng.

Với cấu hình mặc định:

- InnoDB có thể lập chỉ mục từ `SQL` (3 ký tự), nhưng bỏ qua `DB` (2 ký tự).
- MyISAM mặc định bỏ qua cả `SQL` và `DB` vì minimum là 4.
- Từ dài hơn maximum có thể không được đưa vào FULLTEXT index.

Các giới hạn được áp dụng khi xây dựng index. Chỉ thay biến cấu hình mà không rebuild index thì index cũ vẫn phản ánh chính sách cũ.

### 2.2. Kiểm tra cấu hình đang chạy

    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_min_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_max_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_enable_stopword';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_server_stopword_table';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_user_stopword_table';

    SHOW GLOBAL VARIABLES LIKE 'ft_min_word_len';
    SHOW GLOBAL VARIABLES LIKE 'ft_max_word_len';
    SHOW GLOBAL VARIABLES LIKE 'ft_stopword_file';
    SHOW GLOBAL VARIABLES LIKE 'ngram_token_size';

Có thể truy vấn nhiều biến trong một lần:

    SELECT
        @@GLOBAL.innodb_ft_min_token_size,
        @@GLOBAL.innodb_ft_max_token_size,
        @@GLOBAL.innodb_ft_enable_stopword,
        @@GLOBAL.ft_min_word_len,
        @@GLOBAL.ft_max_word_len,
        @@GLOBAL.ngram_token_size;

Nếu tài khoản không có quyền đọc một số biến hoặc metadata, hãy nhờ DBA kiểm tra theo quyền được cấp. Không suy ra cấu hình server chỉ từ một file my.cnf vì server có thể đọc nhiều option file hoặc nhận tham số khi khởi động.

## 3. Stopword là gì và ảnh hưởng đến kết quả tìm kiếm

Stopword là từ được loại khỏi FULLTEXT index theo danh sách cấu hình. Khi truy vấn, một từ bị loại khỏi index thường không thể tìm thấy theo cách tìm kiếm token thông thường, dù từ đó vẫn còn trong cột văn bản.

Ví dụ:

    CREATE TABLE articles (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        title VARCHAR(255),
        body TEXT,
        FULLTEXT KEY ft_articles (title, body)
    ) ENGINE=InnoDB;

Nếu body chứa:

    The database is available for SQL queries.

Các từ trong stopword list của InnoDB sẽ không được ghi vào FULLTEXT index. Tìm `database` có thể trả kết quả; tìm riêng một stopword như `the` có thể không trả hàng tương ứng.

### 3.1. Stopword không xóa văn bản gốc

Stopword filtering chỉ ảnh hưởng FULLTEXT index. Nội dung trong cột title/body vẫn nguyên vẹn:

    SELECT id, body
    FROM articles
    WHERE id = 1;

Stopword không bị xóa khỏi bảng, không bị sửa trong chuỗi và không ảnh hưởng đến phép so sánh LIKE thông thường. Nó chỉ không được đưa vào index theo cơ chế FULLTEXT.

### 3.2. Danh sách InnoDB và MyISAM khác nhau

InnoDB có danh sách mặc định tương đối ngắn. Danh sách này được thiết kế để giữ lại nhiều từ ngắn có thể có ý nghĩa trong tài liệu kỹ thuật, văn học hoặc cụm từ.

MyISAM có danh sách mặc định dài hơn và được quản lý qua cơ chế stopword file tích hợp.

Không giả định cùng một truy vấn sẽ có kết quả giống nhau trên hai engine nếu chúng sử dụng stopword mặc định khác nhau.

### 3.3. Xem stopword mặc định của InnoDB

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    ORDER BY value;

Bảng INFORMATION_SCHEMA này hiển thị danh sách stopword InnoDB mặc định. Tài khoản cần quyền phù hợp, trong đó tài liệu MySQL yêu cầu PROCESS để truy vấn bảng này.

Một số từ trong danh sách mặc định:

    a
    about
    an
    are
    as
    at
    be
    by
    for
    from
    in
    is
    it
    of
    on
    or
    the
    this
    to
    with

Đây chỉ là ví dụ minh họa. Hãy truy vấn INFORMATION_SCHEMA trên server để lấy danh sách chính xác của phiên bản đang chạy.

### 3.4. Collation ảnh hưởng việc so sánh stopword

Danh sách stopword được nạp và tra cứu theo character set/collation của server, cụ thể là `character_set_server` và `collation_server`.

Case sensitivity phụ thuộc collation:

- Collation không phân biệt hoa thường có thể xem `The` và `the` là tương đương.
- Collation phân biệt hoa thường hoặc binary có thể xem chúng là khác nhau.

Nếu stopword file hoặc stopword table dùng character set/collation khác với server hoặc cột được lập chỉ mục, có thể xuất hiện false hit hoặc false miss. Khi thiết kế custom stopword, hãy kiểm tra character set, collation và cách chuẩn hóa chữ hoa/thường.

## 4. Cấu hình stopword riêng cho InnoDB

InnoDB hỗ trợ ba cách xác định stopword list:

1. Dùng danh sách mặc định tích hợp.
2. Dùng stopword table toàn server qua `innodb_ft_server_stopword_table`.
3. Dùng stopword table cho index/table cụ thể qua `innodb_ft_user_stopword_table`.

`innodb_ft_enable_stopword` bật hoặc tắt việc gắn stopword list vào FULLTEXT index khi index được tạo.

Nếu cả user stopword table và server stopword table được cấu hình, InnoDB ưu tiên user stopword table. Nếu không có user table nhưng có server table, dùng server table. Nếu cả hai đều không có, dùng danh sách mặc định.

### 4.1. Tạo stopword table đúng cấu trúc

Stopword table phải:

- Dùng storage engine InnoDB.
- Có đúng một cột VARCHAR tên `value`.
- Được tạo trước khi cấu hình biến trỏ đến bảng.

Các ví dụ dưới đây giả định schema `app` đã tồn tại. Chọn schema đó trước khi chạy hoặc thay `app` bằng schema thực tế của bạn.

Ví dụ:

    USE app;

    CREATE TABLE app_search_stopwords (
        value VARCHAR(100) NOT NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    INSERT INTO app_search_stopwords(value)
    VALUES
        ('internal'),
        ('draft'),
        ('placeholder');

Danh sách ví dụ trên phù hợp với một ứng dụng giả định. Không sao chép stopword của miền khác mà không đánh giá ý nghĩa nghiệp vụ.

### 4.2. Dùng stopword table toàn server

Đặt biến global trước khi tạo FULLTEXT index:

    SET GLOBAL innodb_ft_enable_stopword = ON;

    SET GLOBAL innodb_ft_server_stopword_table =
        'app/app_search_stopwords';

Sau đó tạo index:

    CREATE FULLTEXT INDEX ft_articles
    ON articles(title, body);

Stopword table phải tồn tại trước khi cấu hình biến. Biến server stopword table áp dụng cho các FULLTEXT index InnoDB được tạo theo cấu hình đó.

Việc thay đổi biến không tự cập nhật những token đã được ghi vào index cũ. Nếu muốn index hiện có dùng danh sách mới, phải rebuild index.

### 4.3. Dùng stopword table cho một bảng cụ thể

Có thể dùng `innodb_ft_user_stopword_table` để chỉ định danh sách cho một index/table. Biến này hỗ trợ SESSION và GLOBAL; cách thường dùng để giới hạn ảnh hưởng là đặt SESSION trong connection tạo index:

    CREATE TABLE article_search_stopwords (
        value VARCHAR(100) NOT NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    INSERT INTO article_search_stopwords(value)
    VALUES ('internal'), ('draft');

    CREATE TABLE articles_custom (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        title VARCHAR(255),
        body TEXT
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    SET SESSION innodb_ft_enable_stopword = ON;

    SET SESSION innodb_ft_user_stopword_table =
        'app/article_search_stopwords';

    CREATE FULLTEXT INDEX ft_article_search
    ON articles_custom(title, body);

User stopword table được gắn với bảng InnoDB cụ thể khi tạo FULLTEXT index. Đảm bảo câu CREATE FULLTEXT INDEX chạy trong cùng session đã đặt user stopword table. Hãy ghi lại cấu hình dùng để tạo index trong migration hoặc tài liệu vận hành.

### 4.4. Tắt stopword filtering trong InnoDB

Nếu nghiệp vụ cần tìm cả các từ thường gặp, có thể tắt stopword filtering:

    SET GLOBAL innodb_ft_enable_stopword = OFF;

Hoặc đặt trong cấu hình phù hợp trước khi tạo index:

    [mysqld]
    innodb_ft_enable_stopword=OFF

Biến này có thể thay đổi động, nhưng FULLTEXT index hiện có vẫn cần được rebuild để chính sách mới có hiệu lực trên dữ liệu đã lập chỉ mục.

Tắt stopword có thể làm index lớn hơn và tăng số token phổ biến được tìm thấy. Hãy đo dung lượng, thời gian build và chất lượng kết quả trước khi áp dụng trên toàn hệ thống.

## 5. Cấu hình stopword cho MyISAM

MyISAM sử dụng biến `ft_stopword_file` để chọn file stopword.

- Nếu dùng tên file tương đối, server tìm file trong data directory.
- Có thể dùng đường dẫn tuyệt đối để chỉ định vị trí khác.
- File chứa danh sách stopword; các từ được phân tách bằng ký tự không phải chữ/số như newline, dấu cách hoặc dấu phẩy.
- Dấu gạch dưới và dấu nháy đơn có quy tắc riêng: chúng được xem là thành phần của từ.
- File dùng character set mặc định của server.

Ví dụ file:

    /etc/mysql/myisam-stopwords.txt

Nội dung:

    internal
    draft
    placeholder

Trong option file:

    [mysqld]
    ft_stopword_file=/etc/mysql/myisam-stopwords.txt

Server cần đọc được file theo quyền của tài khoản hệ điều hành chạy MySQL.

### 5.1. Tắt stopword filtering cho MyISAM

Đặt biến thành chuỗi rỗng:

    [mysqld]
    ft_stopword_file=''

Điều này tắt stopword filtering cho MyISAM FULLTEXT index. Không áp dụng cách này để cấu hình InnoDB.

### 5.2. Thay file stopword

Khi thay đường dẫn hoặc nội dung file:

1. Chuẩn bị file mới và xác nhận quyền đọc của MySQL.
2. Cập nhật option file hoặc tham số khởi động.
3. Restart MySQL để nạp cấu hình/file mới.
4. Rebuild các MyISAM FULLTEXT index bị ảnh hưởng.
5. Kiểm tra truy vấn với các từ trước đây bị loại và các từ mới được loại.

Chỉ sửa file trên đĩa mà không restart/rebuild không làm index cũ tự thay đổi.

## 6. Độ dài token của InnoDB

InnoDB dùng hai biến:

- `innodb_ft_min_token_size`: độ dài tối thiểu.
- `innodb_ft_max_token_size`: độ dài tối đa.

Mặc định:

| Biến | Giá trị mặc định | Phạm vi MySQL 8.4 |
|---|---:|---:|
| innodb_ft_min_token_size | 3 | 0 đến 16 |
| innodb_ft_max_token_size | 84 | 10 đến 84 |

Đây là biến GLOBAL, không dynamic; cần cấu hình lúc server khởi động. `innodb_ft_min_token_size` là số ký tự tối thiểu của từ được lưu vào InnoDB FULLTEXT index. `innodb_ft_max_token_size` là độ dài ký tự tối đa.

### 6.1. Ví dụ thay đổi minimum token size

Giả sử tài liệu kỹ thuật cần tìm được mã ngắn `DB` và `UI`. Minimum mặc định 3 sẽ bỏ qua token 2 ký tự.

Trong option file:

    [mysqld]
    innodb_ft_min_token_size=2
    innodb_ft_max_token_size=84

Sau khi lưu cấu hình:

1. Restart MySQL.
2. Xác nhận giá trị thực bằng SHOW VARIABLES.
3. Rebuild FULLTEXT index của các bảng InnoDB liên quan.
4. Chạy kiểm thử với token 2 ký tự.

Không chỉ restart rồi kết luận hoàn tất. Index cũ được xây dựng với ngưỡng cũ nên cần rebuild.

### 6.2. Tăng minimum để giảm kích thước index

Nếu hệ thống chỉ tìm kiếm từ dài hơn 4 ký tự, tăng minimum có thể giảm số token được lưu và dung lượng index. Tuy nhiên, từ ngắn có ý nghĩa như mã lỗi, tên sản phẩm hoặc từ kỹ thuật có thể bị loại.

Trước khi tăng minimum, thống kê các truy vấn thực tế để tìm token ngắn quan trọng. Không quyết định chỉ dựa trên kích thước index.

### 6.3. Maximum token size

Token dài hơn `innodb_ft_max_token_size` không được đưa vào index. Giảm maximum có thể giảm index size nhưng làm mất khả năng tìm chuỗi định danh dài.

Không chọn maximum nhỏ chỉ vì phần lớn từ ngôn ngữ tự nhiên ngắn. Hãy kiểm tra mã sản phẩm, URL, tên package, identifier và thuật ngữ miền nghiệp vụ.

## 7. Độ dài từ của MyISAM

MyISAM dùng:

- `ft_min_word_len`: độ dài từ tối thiểu.
- `ft_max_word_len`: độ dài từ tối đa.

Mặc định:

| Biến | Giá trị mặc định | Phạm vi MySQL 8.4 |
|---|---:|---:|
| ft_min_word_len | 4 | 1 đến 82 |
| ft_max_word_len | 84 | 10 đến 84 |

Hai biến này GLOBAL, không dynamic. Chúng được đọc khi server khởi động.

Ví dụ cấu hình:

    [mysqld]
    ft_min_word_len=2
    ft_max_word_len=84

Sau khi restart, MyISAM FULLTEXT index phải được rebuild.

### 7.1. Rebuild MyISAM sau khi thay token size

Có thể dùng:

    REPAIR TABLE articles QUICK;

Hoặc dùng ALTER TABLE để drop và tạo lại FULLTEXT index. Tài liệu MySQL chỉ ra QUICK repair là đủ để rebuild MyISAM FULLTEXT index sau các thay đổi liên quan.

Nếu dùng chương trình myisamchk để sửa index bên ngoài server, cần truyền các giá trị ft_min_word_len, ft_max_word_len và ft_stopword_file tương ứng với cấu hình server. Nếu không, myisamchk có thể tạo lại index bằng giá trị mặc định và làm kết quả tìm kiếm sai.

### 7.2. Không nhầm cấu hình MyISAM với InnoDB

Ví dụ:

- `ft_min_word_len=2` chỉ ảnh hưởng MyISAM.
- `innodb_ft_min_token_size=2` chỉ ảnh hưởng InnoDB.

Nếu ứng dụng đang dùng cả hai engine, cần cấu hình và rebuild từng nhóm index theo đúng engine.

## 8. Ngram parser và token size

Parser chuẩn dựa vào ranh giới từ. Với tiếng Trung, tiếng Nhật, tiếng Hàn và nội dung không có khoảng trắng phân tách từ rõ ràng, parser chuẩn có thể không tạo token như mong muốn.

MySQL cung cấp ngram parser tích hợp. Ngram chia chuỗi thành các nhóm ký tự có độ dài cố định, thường gọi là n-gram.

Với `ngram_token_size=2`, chuỗi:

    database

được phân thành:

    da
    at
    ta
    ab
    ba
    as
    se

Với chuỗi `abc def`, ngram parser tạo các token `ab`, `bc`, `de`, `ef`; khoảng trắng bị loại trong quá trình phân tích.

### 8.1. Cấu hình ngram_token_size

Mặc định:

| Biến | Giá trị |
|---|---:|
| ngram_token_size | 2 |
| Minimum | 1 |
| Maximum | 10 |

`ngram_token_size` là biến read-only, chỉ cấu hình lúc server khởi động qua option file hoặc tham số dòng lệnh.

Ví dụ:

    [mysqld]
    ngram_token_size=2

Thay đổi ngram_token_size yêu cầu restart server và rebuild FULLTEXT index sử dụng ngram parser.

### 8.2. Minimum/maximum word length không áp dụng cho ngram

Với FULLTEXT index dùng ngram parser, các biến sau bị bỏ qua:

- `innodb_ft_min_token_size`
- `innodb_ft_max_token_size`
- `ft_min_word_len`
- `ft_max_word_len`

Độ dài token của ngram chỉ do `ngram_token_size` điều khiển. Không giảm innodb_ft_min_token_size để sửa lỗi tìm kiếm tiếng Trung khi index đang dùng ngram; hãy kiểm tra ngram_token_size và rebuild index.

### 8.3. Tạo FULLTEXT index với ngram

    CREATE TABLE articles_cjk (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(200),
        body TEXT,
        FULLTEXT KEY ft_articles_cjk (title, body)
            WITH PARSER ngram
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

Hoặc thêm vào bảng hiện có:

    ALTER TABLE articles_cjk
    ADD FULLTEXT INDEX ft_articles_cjk (title, body)
        WITH PARSER ngram;

Ngram parser được tích hợp sẵn trong MySQL; không cần cài plugin riêng để sử dụng.

### 8.4. Chọn ngram_token_size

Token size nhỏ:

- Tạo nhiều token chồng lấn hơn.
- Có thể hỗ trợ truy vấn ngắn hơn.
- Thường làm index lớn hơn và tăng chi phí xử lý.

Token size lớn:

- Tạo ít token hơn.
- Có thể giảm index size.
- Không phù hợp nếu ứng dụng cần tìm cụm rất ngắn.

Hãy chọn theo độ dài cụm tìm kiếm thực tế, ngôn ngữ và workload. Không có một giá trị tối ưu cho mọi bộ dữ liệu.

### 8.5. Lưu ý riêng khi tìm kiếm tiếng Việt

Parser chuẩn phân tách văn bản theo ranh giới từ mà MySQL nhận diện, thường là khoảng trắng và dấu phân cách. Trong tiếng Việt, một từ có thể gồm nhiều âm tiết viết cách nhau bằng dấu cách. Ví dụ cụm `cơ sở dữ liệu` có thể được tách thành các token `cơ`, `sở`, `dữ` và `liệu` thay vì một token duy nhất đại diện cho cả khái niệm.

Với minimum mặc định của InnoDB là 3, nhiều âm tiết hai ký tự như `cơ`, `sở` hoặc `dữ` có thể bị bỏ khỏi index. Giảm minimum xuống 2 giúp lập chỉ mục các âm tiết đó nhưng cũng làm tăng số token phổ biến. Stopword mặc định thiên về tiếng Anh, vì vậy không nên giả định nó loại được các hư từ tiếng Việt theo đúng ngữ nghĩa.

Ngram parser tạo các nhóm ký tự có độ dài cố định, không phải bộ tách từ tiếng Việt. Nó có thể hỗ trợ tìm chuỗi con nhưng cũng tạo token chồng lấn và có thể trả kết quả khác với tìm kiếm theo từ. Nếu ứng dụng cần phân đoạn từ tiếng Việt theo ngữ nghĩa, hãy cân nhắc tokenizer ở tầng ứng dụng hoặc pipeline tìm kiếm chuyên dụng; khi dùng FULLTEXT của MySQL, hãy thử corpus tiếng Việt thực tế và đo false positive/false negative trước khi chọn parser.

## 9. Stopword với ngram có quy tắc khác

Parser chuẩn loại token nếu token bằng một mục trong stopword list.

Ngram parser xử lý khác: nó loại token ngram nếu token đó **chứa** một stopword. Vì vậy, một stopword ngắn có thể làm nhiều ngram bị loại.

Ví dụ với `ngram_token_size=2`, văn bản `a,b` tạo token `a,` và `,b`. Nếu dấu phẩy được định nghĩa là stopword, cả hai token đều bị loại vì mỗi token chứa dấu phẩy.

### 9.1. Stopword mặc định của ngram

Ngram parser mặc định dùng danh sách stopword mặc định của MySQL, vốn chứa các stopword tiếng Anh. Với tiếng Trung, tiếng Nhật hoặc tiếng Hàn, cần cân nhắc danh sách stopword riêng phù hợp ngôn ngữ.

Stopword dài hơn `ngram_token_size` bị bỏ qua. Ví dụ token size 2 thì stopword dài 3 ký tự không được dùng để lọc ngram.

### 9.2. Ví dụ ảnh hưởng của stopword

Giả sử:

    ngram_token_size=2

và stopword list có từ `a`. Một văn bản có thể tạo các bigram chứa ký tự a; các token chứa stopword đó bị loại. Vì vậy, tìm kiếm một từ ngắn có nhiều ký tự trùng stopword có thể cho kết quả khác mong đợi.

Khi cấu hình ngram cho dữ liệu CJK, không chỉ xem số lượng stopword. Hãy thử index các cụm đại diện, quan sát token thực tế và xác nhận kết quả tìm kiếm.

### 9.3. Stopword list không phù hợp có thể làm mất tín hiệu

Nếu danh sách stopword chứa dấu câu, ký hiệu hoặc ký tự phổ biến trong mã sản phẩm, ngram parser có thể loại nhiều token hữu ích. Không thêm dấu phân cách vào stopword list một cách tùy tiện.

## 10. Xây dựng FULLTEXT index

FULLTEXT index hỗ trợ các cột kiểu CHAR, VARCHAR hoặc TEXT trên storage engine hỗ trợ FULLTEXT như InnoDB và MyISAM.

### 10.1. Tạo bảng và index InnoDB

    CREATE TABLE articles (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        body MEDIUMTEXT NOT NULL,
        published_at DATETIME NOT NULL,
        FULLTEXT KEY ft_title_body (title, body)
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

FULLTEXT index có thể bao gồm nhiều cột. Khi truy vấn MATCH(), danh sách cột phải khớp với danh sách cột của FULLTEXT index phù hợp.

Ví dụ:

    SELECT
        id,
        MATCH(title, body)
            AGAINST ('database indexing' IN NATURAL LANGUAGE MODE)
            AS relevance
    FROM articles
    WHERE MATCH(title, body)
        AGAINST ('database indexing' IN NATURAL LANGUAGE MODE)
    ORDER BY relevance DESC;

### 10.2. Tạo index sau khi bảng đã có dữ liệu

    ALTER TABLE articles
    ADD FULLTEXT INDEX ft_title_body (title, body);

Khi tạo FULLTEXT index, MySQL phải đọc dữ liệu hiện có, tokenize và xây dựng inverted index. Bảng lớn có thể tiêu tốn đáng kể CPU, I/O, bộ nhớ và dung lượng đĩa.

### 10.3. Index MyISAM

Ví dụ:

    CREATE TABLE legacy_articles (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255),
        body TEXT,
        FULLTEXT KEY ft_legacy_articles (title, body)
    ) ENGINE=MyISAM
      DEFAULT CHARSET=utf8mb4;

Các cấu hình token size và stopword của MyISAM được áp dụng riêng như các phần trước.

### 10.4. Index dùng ngram

    CREATE TABLE product_descriptions (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        product_name VARCHAR(255),
        description TEXT,
        FULLTEXT KEY ft_product_text (product_name, description)
            WITH PARSER ngram
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

Chọn parser trước khi tạo index. Nếu thay đổi parser hoặc ngram_token_size, phải rebuild index tương ứng.

## 11. Cấu hình trước khi tạo index

Một lỗi triển khai phổ biến là tạo FULLTEXT index trước, sau đó mới chỉnh token size hoặc stopword list. Index lúc đó đã được tạo theo cấu hình cũ.

Quy trình nên là:

1. Xác định storage engine.
2. Xác định parser chuẩn hay ngram.
3. Xác định token ngắn nhất/dài nhất cần tìm.
4. Xác định stopword list.
5. Cấu hình biến hệ thống và option file.
6. Restart nếu biến yêu cầu startup.
7. Tạo hoặc rebuild FULLTEXT index.
8. Kiểm tra token và kết quả tìm kiếm.

### 11.1. Ví dụ cấu hình InnoDB cho token 2 ký tự

    [mysqld]
    innodb_ft_min_token_size=2
    innodb_ft_max_token_size=84

Sau khi restart, rebuild FULLTEXT index InnoDB:

    ALTER TABLE articles
    DROP INDEX ft_title_body,
    ADD FULLTEXT INDEX ft_title_body (title, body);

Thực hiện trong maintenance window nếu thời gian rebuild hoặc tác động DDL đáng kể.

### 11.2. Ví dụ cấu hình MyISAM cho token 2 ký tự

    [mysqld]
    ft_min_word_len=2
    ft_max_word_len=84
    ft_stopword_file=/etc/mysql/myisam-stopwords.txt

Sau khi restart:

    REPAIR TABLE legacy_articles QUICK;

Nếu có nhiều bảng MyISAM chứa FULLTEXT index, rebuild từng bảng bị ảnh hưởng. Không chỉ repair một bảng mẫu rồi bỏ qua các bảng còn lại.

### 11.3. Ví dụ cấu hình ngram

    [mysqld]
    ngram_token_size=2

Sau khi restart, rebuild các FULLTEXT index dùng ngram parser. Thay đổi ngram_token_size không làm thay đổi các FULLTEXT index được tạo trước đó.

## 12. Những thay đổi nào cần restart và rebuild?

| Thay đổi | Restart server | Rebuild FULLTEXT index |
|---|---|---|
| InnoDB innodb_ft_min_token_size | Có | Có |
| InnoDB innodb_ft_max_token_size | Có | Có |
| InnoDB innodb_ft_server_stopword_table | Không bắt buộc theo biến dynamic | Có |
| InnoDB innodb_ft_user_stopword_table | Không bắt buộc theo biến dynamic | Có |
| InnoDB innodb_ft_enable_stopword | Không bắt buộc theo biến dynamic | Có |
| InnoDB ngram_token_size | Có | Có |
| MyISAM ft_min_word_len | Có | Có |
| MyISAM ft_max_word_len | Có | Có |
| MyISAM ft_stopword_file hoặc nội dung file | Có | Có |

Các biến stopword InnoDB nêu trên có thể dynamic theo phạm vi được tài liệu chỉ định. Dù không cần restart, index hiện có vẫn cần rebuild để thay đổi chính sách token.

Với MyISAM, sau khi đổi token length hoặc stopword file, server phải restart rồi rebuild FULLTEXT index.

## 13. Rebuild FULLTEXT index InnoDB

MySQL yêu cầu rebuild FULLTEXT index InnoDB sau khi thay đổi bất kỳ biến sau:

- innodb_ft_min_token_size
- innodb_ft_max_token_size
- innodb_ft_server_stopword_table
- innodb_ft_user_stopword_table
- innodb_ft_enable_stopword
- ngram_token_size

Đối với thay đổi min/max token size hoặc ngram_token_size, cần restart server. Các thay đổi stopword có thể dynamic nhưng vẫn yêu cầu rebuild.

### 13.1. Drop và tạo lại index

    ALTER TABLE articles
    DROP INDEX ft_title_body,
    ADD FULLTEXT INDEX ft_title_body (title, body);

Nếu muốn tách thành hai bước:

    ALTER TABLE articles
    DROP INDEX ft_title_body;

    ALTER TABLE articles
    ADD FULLTEXT INDEX ft_title_body (title, body);

Hai bước tách rời tạo khoảng thời gian bảng không có FULLTEXT index đó. Lên kế hoạch ứng dụng và thời gian bảo trì phù hợp.

### 13.2. Kiểm soát tác động rebuild

Trước khi rebuild:

- Đo kích thước bảng và index.
- Kiểm tra dung lượng đĩa còn trống.
- Xác định thời gian DDL và ảnh hưởng đến workload.
- Kiểm tra replica lag nếu có replication.
- Lên kế hoạch rollback cấu hình nếu kết quả tìm kiếm xấu hơn.
- Sao lưu hoặc xác nhận khả năng khôi phục.

Không mặc định việc tạo lại FULLTEXT index luôn online hoặc không khóa. Hành vi DDL phụ thuộc phiên bản, engine, cấu trúc bảng và loại thay đổi; kiểm thử trên môi trường tương đương production.

### 13.3. OPTIMIZE TABLE không thay thế mọi lần rebuild cấu hình

OPTIMIZE TABLE trên bảng InnoDB có FULLTEXT index có thể rebuild index để loại Document ID đã xóa và hợp nhất entry. Đây là thao tác tối ưu index, không nên nhầm với việc chỉ đổi cấu hình token mà không thực hiện đúng quy trình rebuild được yêu cầu.

Khi thay đổi token size hoặc stopword policy, dùng quy trình drop/re-create FULLTEXT index được tài liệu chỉ định.

## 14. Rebuild FULLTEXT index MyISAM

Sau khi thay đổi `ft_min_word_len`, `ft_max_word_len`, `ft_stopword_file` hoặc nội dung stopword file:

1. Restart MySQL.
2. Rebuild FULLTEXT index trên từng bảng MyISAM liên quan.

Cách đơn giản:

    REPAIR TABLE legacy_articles QUICK;

Có thể dùng ALTER TABLE để drop và tạo lại index. REPAIR TABLE, ANALYZE TABLE, OPTIMIZE TABLE hoặc ALTER TABLE đều được thực thi bởi server và sử dụng cấu hình full-text của server.

### 14.1. Lưu ý khi dùng myisamchk

Nếu dùng myisamchk để thao tác index MyISAM bên ngoài server, chương trình cần nhận cùng các giá trị full-text mà mysqld sử dụng.

Ví dụ option file:

    [mysqld]
    ft_min_word_len=3
    ft_max_word_len=84

    [myisamchk]
    ft_min_word_len=3
    ft_max_word_len=84

Nếu không truyền đúng tham số, myisamchk có thể rebuild index bằng giá trị mặc định, làm kết quả tìm kiếm không khớp với server. Ưu tiên thao tác qua server nếu không có lý do vận hành đặc biệt để dùng myisamchk.

## 15. Kiểm tra token thực tế trong InnoDB

Chỉ kiểm tra biến cấu hình là chưa đủ. Hãy xem token MySQL thực sự đưa vào FULLTEXT index.

### 15.1. Chọn bảng cần kiểm tra

    SET GLOBAL innodb_ft_aux_table = 'app/articles';

`innodb_ft_aux_table` trỏ đến bảng InnoDB cần quan sát. Việc đọc các bảng INFORMATION_SCHEMA FTS có thể yêu cầu quyền PROCESS.

### 15.2. Xem token trong index

    SELECT
        word,
        doc_count
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_TABLE
    ORDER BY word;

INNODB_FT_INDEX_TABLE cung cấp thông tin inverted index đang dùng để xử lý tìm kiếm.

### 15.3. Xem token mới trong cache

    SELECT
        word,
        doc_id,
        position
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_CACHE
    ORDER BY doc_id, position;

Các token mới được thêm có thể nằm trong index cache trước khi được đồng bộ vào main full-text index. Cache được hợp nhất khi OPTIMIZE TABLE chạy, khi server shutdown hoặc khi cache vượt giới hạn được cấu hình. Vì vậy, không thấy token trong INDEX_TABLE chưa đủ kết luận token không được tạo; hãy kiểm tra INDEX_CACHE và trạng thái đồng bộ.

### 15.4. Xem stopword mặc định

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    ORDER BY value;

Đối chiếu từ bị thiếu với stopword list và token size. Đây là cách nhanh để phân biệt lỗi parser với lỗi cấu hình.

## 16. Kiểm tra FULLTEXT index và cấu hình bảng

Xem DDL:

    SHOW CREATE TABLE articles;

Xem index:

    SHOW INDEX FROM articles;

Hoặc:

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        INDEX_NAME,
        COLUMN_NAME,
        SEQ_IN_INDEX,
        INDEX_TYPE
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'articles'
    ORDER BY INDEX_NAME, SEQ_IN_INDEX;

FULLTEXT index có INDEX_TYPE là FULLTEXT. Kiểm tra danh sách cột và parser trong DDL khi cần xác nhận cấu hình index.

### 16.1. Xác nhận engine

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        ENGINE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'articles';

Engine quyết định biến token length và cơ chế stopword nào có hiệu lực.

### 16.2. Xác nhận character set/collation

    SHOW FULL COLUMNS FROM articles;

Hoặc:

    SELECT
        COLUMN_NAME,
        CHARACTER_SET_NAME,
        COLLATION_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'articles';

Character set/collation có thể ảnh hưởng cách parser phân loại ký tự và cách so sánh stopword. Khi kết quả khác kỳ vọng, kiểm tra cấu hình cột cùng server collation.

## 17. Chẩn đoán từ có trong văn bản nhưng không tìm thấy

Khi một từ nhìn thấy trong title/body nhưng MATCH ... AGAINST không trả hàng, kiểm tra theo thứ tự:

1. Cột đã nằm trong FULLTEXT index đúng chưa?
2. Câu MATCH() có dùng đúng danh sách cột của index không?
3. Storage engine là InnoDB hay MyISAM?
4. Token có ngắn hơn minimum hoặc dài hơn maximum không?
5. Token có nằm trong stopword list không?
6. Index có được rebuild sau lần thay đổi cấu hình gần nhất không?
7. Parser có tách từ theo ngôn ngữ của dữ liệu không?
8. Nếu dùng ngram, ngram_token_size và stopword behavior có phù hợp không?
9. Character set/collation có gây khác biệt khi token hóa hoặc so sánh không?
10. Truy vấn có bị ảnh hưởng bởi chế độ natural language/boolean và quy tắc riêng của chế độ đó không?

### 17.1. Ví dụ từ quá ngắn

Giả sử InnoDB đang dùng minimum mặc định 3. Từ `DB` có 2 ký tự nên không được lập chỉ mục bằng parser chuẩn.

Nếu dữ liệu chứa:

    DB server configuration

thì tìm `DB` có thể không trả hàng, trong khi tìm `server` có kết quả.

Giải pháp có thể là giảm `innodb_ft_min_token_size` và rebuild index, hoặc thiết kế một trường/index khác cho mã ngắn. Không thay cấu hình nếu phần lớn truy vấn không cần các token ngắn vì index có thể lớn hơn.

### 17.2. Ví dụ stopword

Nếu từ `the` nằm trong stopword list, nó bị loại dù dài hơn minimum. Hãy kiểm tra:

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    WHERE value = 'the';

Nếu đang dùng custom list, kiểm tra chính stopword table được gắn với index.

### 17.3. Ví dụ sai parser

Văn bản tiếng Trung hoặc tiếng Nhật không có khoảng trắng phân tách từ như tiếng Anh. Nếu dùng parser chuẩn, token có thể không được tạo như ứng dụng mong muốn.

Thử tạo FULLTEXT index với ngram parser trên môi trường thử nghiệm, chọn ngram_token_size, rebuild và kiểm tra token thực tế.

## 18. Tác động của cấu hình lên chất lượng và chi phí

Không có cấu hình token size tối ưu cho mọi hệ thống. Mỗi lựa chọn là sự đánh đổi:

| Thay đổi | Lợi ích có thể có | Rủi ro/chi phí |
|---|---|---|
| Giảm minimum token size | Tìm được mã/từ ngắn | Index lớn hơn, nhiều token phổ biến |
| Tăng minimum token size | Index nhỏ hơn, ít nhiễu | Mất từ ngắn có ý nghĩa |
| Giảm maximum token size | Bỏ chuỗi rất dài ít hữu ích | Mất identifier dài |
| Tắt stopword | Tìm được từ phổ biến | Index lớn hơn, kết quả nhiễu |
| Thêm custom stopword | Loại từ riêng của miền nghiệp vụ | Có thể loại nhầm từ quan trọng |
| Giảm ngram_token_size | Tìm cụm ngắn hơn | Nhiều token chồng lấn, index lớn |
| Tăng ngram_token_size | Ít token hơn | Khó tìm cụm ngắn, có thể bỏ sót |

### 18.1. Tác động lên dung lượng và thời gian build

Giảm minimum token size thường làm tăng số token được index. Ngram size nhỏ tạo nhiều ngram chồng lấn hơn. Cả hai có thể làm FULLTEXT index lớn hơn, tăng chi phí build và duy trì index khi INSERT/UPDATE/DELETE.

Khi thay đổi cấu hình, đo:

- Kích thước index trước và sau.
- Thời gian tạo lại index.
- CPU, I/O và memory trong quá trình build.
- Thời gian phản hồi truy vấn.
- Số kết quả và relevance của các truy vấn đại diện.
- Replica lag và dung lượng binary log nếu có replication.

### 18.2. MyISAM natural language threshold

MyISAM natural language search có quy tắc ngưỡng 50% theo weighting scheme mặc định. Một từ xuất hiện trong hơn một nửa số hàng có thể không được trả về trong natural language mode, dù token có trong index.

Đây là quy tắc tìm kiếm riêng, khác stopword và token length. Khi kiểm tra token, hãy phân biệt “token không có trong index” với “token có nhưng chế độ tìm kiếm loại do ngưỡng”.

Không sửa mã nguồn MySQL để thay weighting scheme chỉ nhằm khắc phục một truy vấn trước khi hiểu đầy đủ tác động lên relevance. Nếu cần tìm từ phổ biến, cân nhắc boolean mode và kiểm thử hành vi phù hợp.

## 19. Thiết kế stopword list cho dữ liệu thực tế

Stopword list nên được xây dựng từ truy vấn và corpus của ứng dụng, không chỉ sao chép danh sách tiếng Anh mặc định.

### 19.1. Phân loại từ trước khi thêm vào stopword

Xem xét:

- Tần suất xuất hiện trong corpus.
- Tần suất người dùng tìm kiếm từ đó.
- Từ có mang ý nghĩa phân biệt tài liệu không.
- Từ có phải tên sản phẩm, mã lỗi, thuật ngữ kỹ thuật hoặc tên riêng không.
- Từ có thể là thành phần của cụm tìm kiếm quan trọng không.

Từ xuất hiện nhiều không mặc nhiên là stopword. Ví dụ `SQL` có thể xuất hiện trong nhiều bài viết kỹ thuật nhưng vẫn là từ khóa quan trọng.

### 19.2. Stopword theo ngôn ngữ

Một danh sách tiếng Anh không thể thay thế danh sách phù hợp tiếng Việt, tiếng Trung, tiếng Nhật hoặc tiếng Hàn. Cần xét cách parser phân tách ngôn ngữ, dấu câu, biến thể từ và collation.

Với ngram, cần nhớ token bị loại khi chứa stopword; do đó danh sách quá rộng hoặc có ký tự đơn có thể loại nhiều token hơn dự kiến.

### 19.3. Version hóa stopword list

Quản lý stopword list như một phần của schema/index configuration:

- Lưu thay đổi trong migration hoặc configuration management.
- Ghi ngày áp dụng và lý do thêm/xóa từ.
- Ghi rõ index nào được tạo bằng danh sách đó.
- Kiểm thử tập truy vấn trước và sau.
- Lên kế hoạch rebuild khi danh sách thay đổi.

Không sửa stopword table trực tiếp trong production mà không ghi lại migration và kế hoạch rebuild.

## 20. Quy trình triển khai thay đổi FULLTEXT configuration

Một lần thay đổi stopword/token size có thể ảnh hưởng mọi truy vấn sử dụng index. Hãy triển khai có kiểm soát.

### Bước 1: xác định engine và index bị ảnh hưởng

    SELECT
        TABLE_NAME,
        ENGINE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'app'
      AND TABLE_NAME IN ('articles', 'product_descriptions');

    SHOW CREATE TABLE app.articles;

Ghi lại FULLTEXT index, cột, parser và storage engine.

### Bước 2: thu thập baseline

Lưu lại:

- Giá trị system variables.
- Stopword list hiện tại.
- Kích thước index.
- Một bộ truy vấn đại diện và kết quả.
- Thời gian phản hồi và relevance.

### Bước 3: thử cấu hình trên môi trường staging

Thử các giá trị token size, stopword list hoặc ngram_token_size. Không thay đổi đồng thời nhiều tham số nếu cần xác định nguyên nhân thay đổi kết quả.

### Bước 4: cấu hình server

Sửa option file hoặc thiết lập dynamic variables theo đúng scope. Với biến startup-only, lên kế hoạch restart.

### Bước 5: restart nếu cần

Kiểm tra server khởi động thành công và biến đang chạy đúng giá trị mong muốn.

### Bước 6: rebuild index

Rebuild từng FULLTEXT index bị ảnh hưởng theo engine:

- InnoDB: ALTER TABLE DROP INDEX và ADD FULLTEXT INDEX.
- MyISAM: REPAIR TABLE ... QUICK hoặc ALTER TABLE theo kế hoạch.

### Bước 7: xác minh

Kiểm tra:

- SHOW CREATE TABLE và SHOW INDEX.
- INFORMATION_SCHEMA.INNODB_FT_INDEX_TABLE/INDEX_CACHE với InnoDB.
- Truy vấn chứa từ ngắn, từ stopword, từ dài và từ chuyên ngành.
- Truy vấn CJK nếu dùng ngram.
- Kết quả và relevance so với baseline.

### Bước 8: ghi nhận và theo dõi

Ghi lại cấu hình, thời gian rebuild, dung lượng index, thời gian truy vấn và các vấn đề phát sinh. Theo dõi tải server và replication sau triển khai.

## 21. Lab thực hành: kiểm tra token size và stopword

Lab này dùng InnoDB trên database thử nghiệm. Không thay đổi biến toàn server production chỉ để làm bài thực hành.

### Bước 1: tạo bảng

    USE app;

    CREATE TABLE fts_lab (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255),
        body TEXT,
        FULLTEXT KEY ft_lab (title, body)
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

### Bước 2: thêm dữ liệu

    INSERT INTO fts_lab(title, body)
    VALUES
        ('DB and SQL', 'The DB server stores SQL data.'),
        ('Database guide', 'A database index helps search.'),
        ('Search engine', 'Full text indexing uses tokens.');

### Bước 3: xem cấu hình

    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_min_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_max_token_size';
    SHOW GLOBAL VARIABLES LIKE 'innodb_ft_enable_stopword';

### Bước 4: tìm từ ngắn và stopword

    SELECT id,
           MATCH(title, body)
               AGAINST ('DB' IN NATURAL LANGUAGE MODE) AS score
    FROM fts_lab
    WHERE MATCH(title, body)
        AGAINST ('DB' IN NATURAL LANGUAGE MODE);

    SELECT id,
           MATCH(title, body)
               AGAINST ('the' IN NATURAL LANGUAGE MODE) AS score
    FROM fts_lab
    WHERE MATCH(title, body)
        AGAINST ('the' IN NATURAL LANGUAGE MODE);

Quan sát kết quả theo cấu hình đang chạy. Nếu DB quá ngắn hoặc the là stopword, chúng có thể không được tìm thấy.

### Bước 5: kiểm tra stopword mặc định

    SELECT value
    FROM INFORMATION_SCHEMA.INNODB_FT_DEFAULT_STOPWORD
    WHERE value IN ('the', 'and', 'a', 'to');

### Bước 6: xem token đã index

    SET GLOBAL innodb_ft_aux_table = 'app/fts_lab';

    SELECT word, doc_count
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_TABLE
    ORDER BY word;

Nếu token mới chưa xuất hiện trong INDEX_TABLE, kiểm tra INDEX_CACHE.

### Bước 7: thử custom stopword table

    CREATE TABLE fts_lab_stopwords (
        value VARCHAR(100) NOT NULL
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

    INSERT INTO fts_lab_stopwords(value)
    VALUES ('database');

Trong cùng session, bỏ index hiện tại, đặt user stopword table rồi tạo lại FULLTEXT index cho bảng:

    ALTER TABLE fts_lab
    DROP INDEX ft_lab;

    SET SESSION innodb_ft_enable_stopword = ON;
    SET SESSION innodb_ft_user_stopword_table =
        'app/fts_lab_stopwords';

    ALTER TABLE fts_lab
    ADD FULLTEXT INDEX ft_lab (title, body);

Index được tạo lại dùng stopword table được chỉ định. Với bảng có nhiều FULLTEXT index, hãy áp dụng một chính sách stopword nhất quán cho bảng và rebuild các index liên quan theo cùng cấu hình.

### Bước 8: đối chiếu kết quả

Chạy lại truy vấn với database, DB, SQL và the. Ghi nhận token nào được tìm thấy, token nào bị loại và lý do.

## 22. Lab thực hành: ngram và tiếng CJK

Lab này cần server thử nghiệm có thể restart để cấu hình ngram_token_size.

### Bước 1: cấu hình ngram

    [mysqld]
    ngram_token_size=2

Restart server rồi xác nhận:

    SHOW GLOBAL VARIABLES LIKE 'ngram_token_size';

### Bước 2: tạo bảng ngram

    USE app;

    CREATE TABLE cjk_articles (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(200),
        body TEXT,
        FULLTEXT KEY ft_cjk (title, body)
            WITH PARSER ngram
    ) ENGINE=InnoDB
      DEFAULT CHARSET=utf8mb4;

### Bước 3: thêm văn bản

    INSERT INTO cjk_articles(title, body)
    VALUES
        ('数据库管理', '数据库管理和应用开发'),
        ('数据库应用', '学习数据库应用程序开发');

### Bước 4: quan sát token

    SET GLOBAL innodb_ft_aux_table = 'app/cjk_articles';

    SELECT word, doc_id, position
    FROM INFORMATION_SCHEMA.INNODB_FT_INDEX_CACHE
    ORDER BY doc_id, position;

Nếu cache đã đồng bộ, kiểm tra INDEX_TABLE.

### Bước 5: thử truy vấn

    SELECT
        id,
        MATCH(title, body)
            AGAINST ('数据库' IN NATURAL LANGUAGE MODE) AS score
    FROM cjk_articles
    WHERE MATCH(title, body)
        AGAINST ('数据库' IN NATURAL LANGUAGE MODE);

Thử thêm các cụm có độ dài khác nhau và ghi lại token mà ngram tạo ra.

### Bước 6: thay ngram_token_size trên staging

Đổi thành giá trị 1 hoặc 3 trong option file, restart, rebuild FULLTEXT index và so sánh:

- Số token được tạo.
- Kích thước index.
- Số hàng được tìm thấy.
- Thời gian truy vấn.

Không chỉ chọn giá trị làm truy vấn mẫu có kết quả; cần kiểm tra tập truy vấn thực tế của ứng dụng.

## 23. Các lỗi thường gặp

- Nghĩ từ có trong cột thì chắc chắn có trong FULLTEXT index.
- Dùng biến InnoDB để điều khiển index MyISAM hoặc ngược lại.
- Quên stopword list khi điều tra từ không tìm thấy.
- Nghĩ stopword bị xóa khỏi dữ liệu gốc.
- Thay stopword table nhưng không rebuild FULLTEXT index.
- Thay token size nhưng chỉ restart, không rebuild.
- Chỉ sửa file stopword MyISAM mà không restart/rebuild.
- Dùng myisamchk với giá trị full-text khác mysqld.
- Nghĩ ngram dùng innodb_ft_min_token_size hoặc ft_min_word_len.
- Quên ngram_token_size chỉ thay đổi lúc khởi động.
- Dùng stopword tiếng Anh cho dữ liệu CJK mà không kiểm thử.
- Không hiểu ngram loại token có chứa stopword.
- Thêm dấu câu vào ngram stopword list và vô tình loại nhiều token.
- Không kiểm tra character set/collation của server và stopword list.
- Không phân biệt token không có trong index với token bị loại bởi natural-language threshold.
- Tạo FULLTEXT index nhưng MATCH() dùng danh sách cột không khớp.
- Rebuild index trên production mà không dự trù dung lượng, CPU, I/O và thời gian DDL.
- Chỉ kiểm tra SHOW VARIABLES mà không quan sát token thực tế.

## 24. Checklist vận hành

- Đã xác định storage engine của từng bảng có FULLTEXT index.
- Đã xác nhận parser đang dùng: parser chuẩn hay ngram.
- Đã kiểm tra min/max token size đúng engine.
- Đã kiểm tra stopword list đang áp dụng cho index.
- Đã kiểm tra character set và collation.
- Đã xác định từ ngắn, từ dài và stopword quan trọng với nghiệp vụ.
- Đã thử các từ đại diện trên corpus thật.
- Đã cấu hình biến startup-only trong option file và lên lịch restart.
- Đã cấu hình dynamic stopword variables đúng scope.
- Đã tạo stopword table/file đúng cấu trúc và quyền truy cập.
- Đã rebuild tất cả FULLTEXT index bị ảnh hưởng.
- Đã kiểm tra token trong INFORMATION_SCHEMA nếu dùng InnoDB.
- Đã xác minh truy vấn MATCH ... AGAINST sau rebuild.
- Đã đo dung lượng index và chi phí tìm kiếm.
- Đã kiểm tra replication và backup/restore plan.
- Đã ghi cấu hình cùng quy trình rebuild vào migration/runbook.

## 25. Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Full-Text Stopwords: https://dev.mysql.com/doc/refman/8.4/en/fulltext-stopwords.html
- MySQL 8.4 Reference Manual — Fine-Tuning MySQL Full-Text Search: https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html
- MySQL 8.4 Reference Manual — ngram Full-Text Parser: https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html
- MySQL 8.4 Reference Manual — Natural Language Full-Text Searches: https://dev.mysql.com/doc/refman/8.4/en/fulltext-natural-language.html
- MySQL 8.4 Reference Manual — InnoDB Startup Options and System Variables: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html
- MySQL 8.4 Reference Manual — Server System Variables: https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html
- MySQL 8.4 Reference Manual — InnoDB INFORMATION_SCHEMA FULLTEXT Index Tables: https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-fulltext_index-tables.html

Stopword, token length và parser cùng quyết định token nào được đưa vào FULLTEXT index. InnoDB và MyISAM có biến cấu hình và danh sách stopword riêng; ngram lại dùng ngram_token_size và quy tắc lọc stopword theo token chứa stopword. Mọi thay đổi ảnh hưởng đến token đã lập chỉ mục đều cần rebuild FULLTEXT index, và một số biến còn yêu cầu restart server. Hãy xác định engine, parser, ngôn ngữ và truy vấn thực tế trước khi chọn cấu hình; sau khi tạo lại index, kiểm tra token trong INFORMATION_SCHEMA và chạy lại bộ truy vấn đại diện để xác nhận cả độ chính xác lẫn chi phí vận hành.
