# Collation, tiếng Việt và kiểm chứng chất lượng tách từ

MySQL Full-Text Search (FTS) có thể lập chỉ mục văn bản và xếp hạng kết quả theo mức độ liên quan. Tuy nhiên, kết quả tìm kiếm phụ thuộc nhiều vào cách văn bản được chia thành token, quy tắc so sánh ký tự của collation, danh sách stopword và giới hạn độ dài token. Với tiếng Việt, các yếu tố này đặc biệt quan trọng vì một từ có thể gồm nhiều âm tiết cách nhau bằng dấu cách, còn dấu thanh và dấu chữ có thể làm thay đổi nghĩa.

Cần phân biệt hai việc:

- **Collation** quy định cách so sánh và sắp xếp chuỗi, bao gồm phân biệt hoa/thường và dấu trong những collation có thuộc tính tương ứng.
- **Tokenizer/parser** quyết định văn bản được tách thành các token nào để đưa vào FULLTEXT index và xử lý truy vấn.

Collation không phải bộ tách từ tiếng Việt. Chọn collation đúng giúp kiểm soát cách so sánh dấu và chữ hoa/thường, nhưng không tự hiểu rằng “công nghệ thông tin” là một cụm từ gồm hai từ đa âm tiết. Để tìm kiếm tiếng Việt có chất lượng, cần kiểm chứng cả cấu hình MySQL lẫn quy trình chuẩn hóa và tách từ ở tầng ứng dụng.

Bài học thuộc phạm vi DATABASE_MYSQL: thiết kế FULLTEXT index cho văn bản tiếng Việt, chọn character set/collation, hiểu parser mặc định và ngram parser, quản lý stopword/token size, xây dựng bộ dữ liệu đánh giá và đo precision/recall trước khi đưa tìm kiếm vào production.

## 1. Những thành phần quyết định kết quả Full-Text Search

Một truy vấn FULLTEXT không đơn thuần tìm chuỗi con. MySQL xử lý nội dung qua nhiều bước:

1. Đọc văn bản đã được lập chỉ mục.
2. Parser chia văn bản thành token theo quy tắc của parser.
3. Token có thể bị loại nếu là stopword hoặc không đạt giới hạn độ dài.
4. Token được lưu trong inverted index cùng thông tin tài liệu/hàng chứa token.
5. Khi truy vấn, chuỗi tìm kiếm cũng được parser xử lý theo cấu hình tương ứng.
6. MySQL tìm token phù hợp và tính relevance score theo search mode.
7. Ứng dụng có thể lọc, sắp xếp, phân trang và bổ sung logic nghiệp vụ.

Các thành phần cần kiểm soát:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Character set | Có lưu đầy đủ tiếng Việt và ký tự Unicode không? |
| Collation | Có phân biệt hoa/thường và dấu không? |
| Parser | Tách theo từ, theo n-gram hay parser tùy chỉnh? |
| Token size | Từ ngắn nhất/dài nhất nào được đưa vào index? |
| Stopword | Từ nào bị loại khỏi index? |
| Query mode | Natural language, Boolean hay query expansion? |
| Dữ liệu đầu vào | Có chuẩn hóa Unicode và tách từ giống nhau không? |
| Đánh giá | Kết quả có đúng với bộ truy vấn và tài liệu chuẩn không? |

Một FULLTEXT index được tạo thành công chưa chứng minh tìm kiếm tiếng Việt tốt. Phải kiểm tra token thực tế và kết quả trên bộ dữ liệu đại diện.

## 2. Character set và collation cho tiếng Việt

### 2.1. Dùng utf8mb4

Văn bản tiếng Việt cần lưu được các ký tự Unicode có dấu. Với MySQL hiện đại, nên dùng utf8mb4 cho schema, bảng và cột văn bản.

Ví dụ:

~~~sql
CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

utf8mb4 hỗ trợ đầy đủ Unicode theo khả năng của phiên bản MySQL. Tránh dùng charset cũ hoặc charset chỉ hỗ trợ một phần Unicode nếu nội dung có tiếng Việt, emoji hoặc ký tự đa ngôn ngữ.

Kiểm tra cấu hình:

~~~sql
SELECT
    @@character_set_server,
    @@collation_server,
    @@character_set_database,
    @@collation_database,
    @@character_set_connection,
    @@collation_connection;
~~~

Kiểm tra cột:

~~~sql
SHOW FULL COLUMNS FROM article;
~~~

Cần kiểm tra cả charset/collation của cột thực tế. Giá trị mặc định của server không tự thay đổi collation của những cột đã được tạo trước đó.

### 2.2. Collation quyết định cách so sánh

Tên collation MySQL thường thể hiện các thuộc tính:

- ai: accent-insensitive, không phân biệt dấu theo quy tắc collation.
- as: accent-sensitive, phân biệt dấu.
- ci: case-insensitive, không phân biệt hoa/thường.
- cs: case-sensitive, phân biệt hoa/thường.
- bin: so sánh theo giá trị nhị phân/code point theo quy tắc của collation nhị phân.

Ví dụ các collation UCA 9.0 thường gặp trên MySQL 8.0:

| Collation | Đặc tính chính |
|---|---|
| utf8mb4_0900_ai_ci | Không phân biệt dấu và hoa/thường |
| utf8mb4_0900_as_ci | Phân biệt dấu, không phân biệt hoa/thường |
| utf8mb4_0900_ai_cs | Không phân biệt dấu, phân biệt hoa/thường |
| utf8mb4_0900_as_cs | Phân biệt dấu và hoa/thường |

Tên và danh sách collation có thể khác theo phiên bản. Kiểm tra trực tiếp server thay vì giả định mọi môi trường đều có cùng danh sách:

~~~sql
SHOW COLLATION LIKE 'utf8mb4%';
~~~

Nếu muốn tìm collation theo ngôn ngữ:

~~~sql
SHOW COLLATION LIKE 'utf8mb4%vi%';
~~~

Không phải mọi phiên bản hoặc bản phân phối MySQL đều có cùng bộ collation locale. Chỉ chọn collation sau khi xác nhận nó tồn tại trên server đích.

### 2.3. Dấu tiếng Việt có thể làm thay đổi nghĩa

Ví dụ các chuỗi:

- ma
- má
- mà
- mả
- mã
- mạ

Trong tiếng Việt, dấu thanh không chỉ là hình thức trình bày; chúng có thể phân biệt từ và nghĩa. Nếu dùng collation accent-insensitive, các dạng có dấu có thể được xem là tương đương trong phép so sánh. Điều đó có thể tăng độ bao phủ khi người dùng bỏ dấu, nhưng cũng tạo thêm kết quả không liên quan.

Với nội dung cần phân biệt đúng từ tiếng Việt, hãy bắt đầu thử nghiệm bằng collation accent-sensitive. Nếu sản phẩm muốn hỗ trợ tìm kiếm không dấu, thiết kế thêm một chiến lược tìm kiếm không dấu có chủ đích và đo false positive.

Không mặc định rằng ai_ci luôn tốt hơn cho tìm kiếm hoặc as_cs luôn tốt hơn. Đó là quyết định sản phẩm dựa trên cách người dùng nhập truy vấn và mức chấp nhận kết quả gần đúng.

### 2.4. Collation không chuẩn hóa văn bản đã lưu

Collation quy định phép so sánh; nó không phải quy trình chuẩn hóa dữ liệu đầu vào và không viết lại chuỗi đã lưu về một dạng Unicode thống nhất.

Unicode có thể biểu diễn một ký tự có dấu theo dạng ký tự dựng sẵn hoặc dạng ký tự cơ sở cộng combining mark. Ví dụ, chữ có dấu có thể được biểu diễn bằng một code point hoặc nhiều code point kết hợp.

Nên thống nhất chuẩn Unicode ở tầng ứng dụng, thường dùng NFC trước khi lưu và trước khi xử lý truy vấn. Nếu dữ liệu cũ đã tồn tại, kiểm tra và chuẩn hóa có kế hoạch. Không chỉ dựa vào collation để giả định mọi chuỗi byte đã có cùng dạng.

Kiểm thử cả hai dạng Unicode tương đương về mặt hiển thị để xác nhận hành vi so sánh và FULLTEXT trên phiên bản/collation đang dùng.

## 3. Phân biệt collation với tokenizer

Hai khái niệm này giải quyết hai câu hỏi khác nhau.

| Ví dụ | Collation | Tokenizer |
|---|---|---|
| “SQL” và “sql” có được xem như nhau không? | Có ảnh hưởng | Không phải nhiệm vụ chính |
| “ma” và “má” có được xem như nhau không? | Có ảnh hưởng | Không phải nhiệm vụ chính |
| “công nghệ thông tin” được tách thành những token nào? | Không quyết định | Quyết định |
| Dấu câu có tạo ranh giới token không? | Không quyết định | Quyết định |
| “công_nghệ” có là một token không? | Không quyết định | Phụ thuộc parser |
| Từ nào bị loại khỏi index? | Không quyết định | Liên quan stopword và cấu hình FTS |

Đổi collation không tự tạo ra bộ tách từ tiếng Việt. Đổi parser cũng không tự quyết định phép so sánh hoa/thường hoặc dấu theo yêu cầu sản phẩm.

Khi chẩn đoán một từ không tìm thấy, hãy kiểm tra theo thứ tự:
1. Dữ liệu gốc có được lưu đúng Unicode không?
2. Cột được index có đúng charset/collation không?
3. Parser có tách token theo cách mong đợi không?
4. Token có bị loại vì quá ngắn/quá dài hoặc stopword không?
5. Query string có được chuẩn hóa và tách từ giống nội dung index không?
6. Search mode có yêu cầu đúng loại token không?

## 4. Parser mặc định của MySQL

MySQL FULLTEXT mặc định sử dụng built-in parser nếu không chỉ định parser khác. Parser này tách văn bản thành từ dựa trên ranh giới ký tự và dấu phân cách theo quy tắc của MySQL.

Các ký tự chữ, số, dấu gạch dưới và một số dấu nháy bên trong từ có thể được xem là thành phần của token. Dấu câu và khoảng trắng thường tạo ranh giới token. Quy tắc chính xác cần được kiểm tra với dữ liệu thực tế và phiên bản đang chạy.

Ví dụ văn bản:

~~~text
Học MySQL để xây dựng hệ thống cơ sở dữ liệu quan hệ.
~~~

Có thể được tách thành các token gần như:

~~~text
Học | MySQL | để | xây | dựng | hệ | thống | cơ | sở | dữ | liệu | quan | hệ
~~~

Đây là minh họa về ranh giới token, không phải kết quả của một bộ phân tích ngôn ngữ tiếng Việt. Parser mặc định không hiểu rằng “cơ sở dữ liệu” là một thuật ngữ gồm nhiều âm tiết và không tự nhận diện cụm “hệ thống quản trị cơ sở dữ liệu” như một khái niệm duy nhất.

### 4.1. Giới hạn độ dài token

InnoDB và MyISAM có biến cấu hình độ dài token riêng:

| Engine | Biến tối thiểu | Mặc định thường gặp | Biến tối đa |
|---|---|---:|---|
| InnoDB | innodb_ft_min_token_size | 3 | innodb_ft_max_token_size |
| MyISAM | ft_min_word_len | 4 | ft_max_word_len |

Giá trị mặc định có thể thay đổi theo cấu hình. Kiểm tra runtime:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'ft_min_word_len';
SHOW VARIABLES LIKE 'ft_max_word_len';
~~~

Nếu token ngắn hơn ngưỡng tối thiểu, nó có thể không được đưa vào FULLTEXT index. Điều này đặc biệt đáng chú ý với tiếng Việt và truy vấn có từ ngắn như “AI”, “IoT” hoặc mã viết tắt.

Không hạ ngưỡng token chỉ vì một truy vấn cụ thể không tìm thấy kết quả. Trước tiên xác định token có thực sự cần tìm, có bị stopword hay không và ảnh hưởng dung lượng index ra sao.

### 4.2. Từ quá ngắn và viết tắt

Ví dụ người dùng tìm “AI” nhưng InnoDB đang dùng min token size mặc định 3. Token hai ký tự có thể bị bỏ khỏi index. Kết quả là truy vấn không tìm thấy tài liệu dù chuỗi AI có trong body.

Các lựa chọn:
- Dùng một cột mã/keyword riêng có B-tree index nếu đây là mã định danh.
- Thiết kế parser hoặc chiến lược tìm kiếm khác cho từ viết tắt.
- Điều chỉnh token size nếu phù hợp với toàn bộ workload và chấp nhận chi phí index.
- Dùng bảng alias/keyword để ánh xạ thuật ngữ ngắn.
- Thử ngram parser nếu bài toán thực sự cần token ký tự ngắn, sau đó đánh giá chất lượng.

## 5. Stopword và ảnh hưởng tới tìm kiếm tiếng Việt

Stopword là các token bị loại khỏi FULLTEXT index vì được xem là quá phổ biến hoặc ít có giá trị phân biệt. MySQL cung cấp danh sách stopword mặc định và cơ chế cấu hình danh sách riêng.

Một số từ chức năng xuất hiện rất thường xuyên trong ngôn ngữ tự nhiên có thể ít giúp phân biệt tài liệu. Tuy nhiên, với tiếng Việt, không nên lấy danh sách stopword tiếng Anh mặc định rồi cho rằng nó phù hợp với corpus tiếng Việt.

Kiểm tra danh sách InnoDB mặc định:

~~~sql
SELECT value
FROM information_schema.innodb_ft_default_stopword
ORDER BY value;
~~~

Kiểm tra cấu hình:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
SHOW VARIABLES LIKE 'innodb_ft_server_stopword_table';
SHOW VARIABLES LIKE 'innodb_ft_user_stopword_table';
~~~

### 5.1. Tại sao stopword có thể làm sai kết quả?

Nếu một thuật ngữ quan trọng trong miền nghiệp vụ bị đưa vào stopword list, FULLTEXT có thể không index thuật ngữ đó. Ví dụ một từ viết tắt hoặc từ chuyên ngành phổ biến trong tài liệu nội bộ có thể là từ khóa rất quan trọng với người dùng.

Ngược lại, nếu không loại các từ quá phổ biến, chúng có thể tạo nhiều kết quả nhiễu và làm giảm chất lượng xếp hạng.

Hãy xây stopword list từ corpus thực tế:
1. Thống kê tần suất token.
2. Xem xét giá trị phân biệt của token.
3. Trao đổi với chuyên gia miền nghiệp vụ.
4. Kiểm tra truy vấn mà người dùng thực sự nhập.
5. Đo precision/recall trước và sau khi thay đổi.

### 5.2. Thay đổi stopword cần xây dựng lại FULLTEXT index

Thay danh sách stopword hoặc cấu hình stopword không tự tái tạo toàn bộ token đã được index trước đó. Sau khi đổi cấu hình, cần rebuild FULLTEXT index theo quy trình phù hợp với engine và phiên bản.

Không chỉ đổi biến cấu hình rồi kết luận index cũ đã dùng danh sách mới. Ghi lại cấu hình, thời điểm rebuild và số lượng hàng được index để có thể tái hiện kết quả.

## 6. Vấn đề riêng của tiếng Việt: một từ có thể gồm nhiều âm tiết

Tiếng Việt dùng dấu cách giữa các âm tiết. Nhiều từ đa âm tiết được tạo thành từ hai hoặc nhiều âm tiết:

- công nghệ
- thông tin
- cơ sở dữ liệu
- quản trị hệ thống
- trí tuệ nhân tạo
- học máy
- ngôn ngữ tự nhiên

Built-in parser thường nhìn thấy các phần cách nhau bằng dấu cách như các token riêng. Ví dụ “cơ sở dữ liệu” có thể thành bốn token “cơ”, “sở”, “dữ”, “liệu”.

Điều này tạo ra một số vấn đề:
- Truy vấn một âm tiết có thể khớp nhiều ngữ cảnh không liên quan.
- Từ ghép đa âm tiết không được biểu diễn như một token ngữ nghĩa.
- Từ ngắn có thể bị loại bởi min token size.
- Relevance score có thể ưu tiên tài liệu chứa nhiều âm tiết phổ biến thay vì đúng thuật ngữ.
- Người dùng nhập biến thể có dấu hoặc không dấu có thể nhận tập kết quả khác nhau.

### 6.1. Ví dụ về kết quả nhiễu

Giả sử hai tài liệu:

~~~text
A: Hướng dẫn cơ sở dữ liệu MySQL cho người mới học.
B: Cơ sở vật chất của trường học được nâng cấp.
~~~

Người dùng tìm “cơ sở dữ liệu”. Parser mặc định có thể xử lý thành các token riêng. Tùy search mode, stopword và relevance, tài liệu B có thể được xem xét vì chứa “cơ sở” dù không nói về database.

Cụm từ Boolean phrase có thể giúp giới hạn theo chuỗi token liền nhau, nhưng nó không thay thế hiểu biết ngôn ngữ. Tài liệu có cùng cụm âm tiết trong một ngữ cảnh khác vẫn có thể được trả về.

## 7. Tiền xử lý và tách từ ở tầng ứng dụng

Một cách thực tế để nâng chất lượng tìm kiếm tiếng Việt là dùng bộ tách từ ở tầng ứng dụng, sau đó lưu văn bản đã tách vào một cột tìm kiếm riêng.

Giữ nguyên nội dung hiển thị và tạo cột search_text:

~~~sql
CREATE TABLE article_search (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    search_text MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_article_search (search_text)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

Ví dụ nội dung gốc:

~~~text
Học cơ sở dữ liệu và công nghệ thông tin với MySQL.
~~~

Sau khi chuẩn hóa Unicode và tách từ bằng công cụ phù hợp với tiếng Việt, ứng dụng có thể tạo search_text:

~~~text
học cơ_sở_dữ_liệu và công_nghệ_thông_tin với MySQL
~~~

Dấu gạch dưới được dùng ở đây như một quy ước để nối các âm tiết thuộc cùng một từ. Built-in parser coi dấu gạch dưới là ký tự có thể nằm trong token, nhưng phải xác minh kết quả tokenization trên server thực tế.

Truy vấn cũng phải được xử lý qua cùng bộ tách từ:

~~~text
Truy vấn người dùng: cơ sở dữ liệu
Chuỗi sau tách từ: cơ_sở_dữ_liệu
~~~

Nếu chỉ tiền xử lý tài liệu mà không tiền xử lý truy vấn, hai phía có thể không tạo ra token giống nhau và chất lượng tìm kiếm giảm.

### 7.1. Không thay đổi văn bản gốc

Nên lưu:
- original title/body để hiển thị và chỉnh sửa.
- search_text để phục vụ tìm kiếm.
- tokenizer_version để biết văn bản được tạo bằng phiên bản bộ tách từ nào, nếu cần quản lý migration.

Không ghi đè nội dung gốc bằng văn bản đã nối âm tiết. Cột search_text là representation phục vụ truy vấn.

### 7.2. Chuẩn hóa nhất quán hai phía

Pipeline nên có các bước:
1. Kiểm tra đầu vào là UTF-8 hợp lệ.
2. Chuẩn hóa Unicode về một dạng thống nhất, thường là NFC.
3. Chuẩn hóa khoảng trắng và ký tự điều khiển theo quy tắc sản phẩm.
4. Tách từ tiếng Việt.
5. Chuẩn hóa chữ hoa/thường theo chiến lược tìm kiếm.
6. Tạo search_text.
7. Lưu original và search_text trong cùng transaction.
8. Khi người dùng tìm kiếm, áp dụng cùng pipeline cho query.

Không loại dấu tiếng Việt một cách mặc định. Nếu muốn hỗ trợ truy vấn không dấu, nên thiết kế một search representation riêng và đo độ nhiễu.

### 7.3. Ví dụ về dữ liệu song song có dấu và không dấu

Có thể lưu hai cột tìm kiếm:

~~~sql
CREATE TABLE article_search_variant (
    article_id BIGINT UNSIGNED NOT NULL,
    original_text MEDIUMTEXT NOT NULL,
    search_text_accented MEDIUMTEXT NOT NULL,
    search_text_folded MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_accented (search_text_accented),
    FULLTEXT KEY ft_folded (search_text_folded)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

- search_text_accented giữ dấu và có thể dùng accent-sensitive collation.
- search_text_folded được tạo bằng pipeline bỏ dấu có kiểm soát.
- original_text giữ nội dung hiển thị.

Nếu chạy cả hai tìm kiếm, cần hợp nhất kết quả và xử lý trùng article_id, relevance score và ưu tiên kết quả có dấu chính xác. Không cộng điểm một cách tùy tiện; hãy định nghĩa ranking rule và đánh giá trên tập truy vấn chuẩn.

## 8. Tạo FULLTEXT index với parser mặc định

Ví dụ bảng tài liệu:

~~~sql
CREATE TABLE knowledge_article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    search_text MEDIUMTEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_knowledge_search (search_text)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_cs;
~~~

In dữ liệu:

~~~sql
INSERT INTO knowledge_article(title, body, search_text)
VALUES
(
    'Cơ sở dữ liệu MySQL',
    'Tài liệu giới thiệu hệ quản trị cơ sở dữ liệu quan hệ.',
    'tài_liệu giới_thiệu hệ_quản_trị cơ_sở_dữ_liệu quan_hệ'
),
(
    'Công nghệ thông tin',
    'Khái niệm công nghệ thông tin và hệ thống phần mềm.',
    'khái_niệm công_nghệ_thông_tin và hệ_thống phần_mềm'
);
~~~

Tìm kiếm tự nhiên:

~~~sql
SELECT
    article_id,
    title,
    MATCH(search_text)
        AGAINST ('cơ_sở_dữ_liệu' IN NATURAL LANGUAGE MODE) AS relevance
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('cơ_sở_dữ_liệu' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
~~~

Trong ví dụ, search_text đã được tiền xử lý. Nếu dùng body gốc, kết quả tokenization sẽ khác và phải đánh giá theo parser mặc định.

### 8.1. MATCH phải tương ứng với FULLTEXT index

Danh sách cột trong MATCH() cần tương ứng với một FULLTEXT index có sẵn. Nếu index được tạo trên (title, body), truy vấn thường dùng:

~~~sql
MATCH(title, body) AGAINST ('mysql database' IN NATURAL LANGUAGE MODE)
~~~

Không giả định FULLTEXT index trên search_text có thể phục vụ MATCH(body) hoặc MATCH(title, body). Kiểm tra định nghĩa bằng:

~~~sql
SHOW INDEX FROM knowledge_article;
~~~

## 9. Natural language mode, Boolean mode và phrase search

### 9.1. Natural language mode

Đây là mode mặc định nếu không chỉ định mode khác:

~~~sql
SELECT
    article_id,
    title,
    MATCH(search_text)
        AGAINST ('cơ_sở_dữ_liệu mysql' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('cơ_sở_dữ_liệu mysql' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

Natural language mode tính relevance dựa trên token và phân bố trong tập tài liệu. Nó phù hợp với tìm kiếm tự nhiên, nhưng không bảo đảm cụm từ phải xuất hiện nguyên vẹn theo thứ tự.

Với InnoDB, không áp dụng quy tắc ngưỡng 50% giống MyISAM natural language search. Hành vi giữa engine có thể khác; kiểm tra engine thực tế khi chuyển hệ thống.

### 9.2. Boolean mode

Boolean mode cho phép điều khiển token cần có, không được có hoặc prefix:

~~~sql
SELECT article_id, title
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('+cơ_sở_dữ_liệu +mysql -giải_trí' IN BOOLEAN MODE);
~~~

Một số toán tử:
- +term: term phải xuất hiện.
- -term: term không được xuất hiện.
- term*: tìm token có prefix phù hợp.
- "phrase": tìm cụm token theo thứ tự liền nhau theo semantics phrase search.
- Các toán tử khác có quy tắc riêng về nhóm, trọng số và loại trừ.

Cú pháp Boolean mode của MySQL không giống hoàn toàn cú pháp của các search engine khác. Hãy kiểm thử các toán tử cần dùng trước khi expose cho người dùng.

### 9.3. Phrase search

Ví dụ tìm cụm đã tách:

~~~sql
SELECT article_id, title
FROM knowledge_article
WHERE MATCH(search_text)
    AGAINST ('"cơ_sở_dữ_liệu"' IN BOOLEAN MODE);
~~~

Phrase search kiểm tra chuỗi token theo thứ tự. Nếu nội dung và query dùng quy tắc tách từ khác nhau, phrase search có thể không khớp như mong đợi.

Phrase search không phải semantic search. Nó không tự hiểu từ đồng nghĩa, biến thể chính tả hoặc ý định người dùng.

### 9.4. Query expansion

Query expansion có thể mở rộng kết quả dựa trên các tài liệu phù hợp ở bước đầu. Nó có thể tìm thêm tài liệu có token liên quan nhưng cũng tăng kết quả nhiễu. Chỉ bật nếu sản phẩm cần mở rộng truy vấn và đã đánh giá trên bộ dữ liệu chuẩn.

## 10. Ngram parser và giới hạn với tiếng Việt

MySQL cung cấp ngram full-text parser plugin, hữu ích cho ngôn ngữ không phân tách từ bằng dấu cách như tiếng Trung, Nhật hoặc Hàn. Ngram parser chia chuỗi thành các chuỗi ký tự liên tiếp có độ dài N.

Tạo FULLTEXT index:

~~~sql
CREATE TABLE article_ngram (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    content TEXT NOT NULL,
    PRIMARY KEY (article_id),
    FULLTEXT KEY ft_article_ngram (content) WITH PARSER ngram
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4;
~~~

Biến cấu hình:

~~~sql
SHOW VARIABLES LIKE 'ngram_token_size';
~~~

ngram_token_size xác định số ký tự trong mỗi n-gram; giá trị mặc định thường là 2. Cần kiểm tra cấu hình runtime và tài liệu đúng phiên bản.

### 10.1. Ngram không phải bộ tách từ tiếng Việt

Tiếng Việt có dấu cách giữa âm tiết, nhưng từ đa âm tiết có thể tạo thành một đơn vị từ vựng. Ngram parser tạo các chuỗi ký tự theo kích thước N, không hiểu cấu trúc từ ghép và ngữ nghĩa tiếng Việt.

Ví dụ “công nghệ thông tin” có thể tạo nhiều n-gram ký tự. Tìm một n-gram ngắn có thể trả về nhiều tài liệu chứa cùng chuỗi ký tự trong những từ khác nhau. Điều này hữu ích cho một số bài toán substring/prefix hoặc ngôn ngữ không có ranh giới từ rõ, nhưng không tự giải quyết phân đoạn từ tiếng Việt.

### 10.2. Khi nào thử ngram?

Có thể thử nếu:
- Ứng dụng cần tìm chuỗi con hoặc cụm ký tự.
- Từ khóa rất ngắn thường xuyên xuất hiện.
- Dữ liệu đa ngôn ngữ có phần nội dung CJK.
- Bộ tách từ ngoài không đáp ứng yêu cầu vận hành.
- Đội ngũ chấp nhận index lớn và đánh giá false positive.

Không chọn ngram chỉ vì tìm kiếm tiếng Việt có dấu. Với tìm kiếm theo từ/cụm từ tiếng Việt, bộ tách từ ở tầng ứng dụng thường biểu diễn ý nghĩa từ ghép rõ hơn.

### 10.3. Chi phí và giới hạn

Ngram tạo nhiều token hơn parser theo từ, đặc biệt khi token size nhỏ. Điều này có thể:
- Làm FULLTEXT index lớn hơn.
- Tăng chi phí INSERT/UPDATE.
- Tăng số candidate khi truy vấn.
- Tăng kết quả nhiễu.
- Làm ranking khó kiểm soát hơn.

Thay đổi ngram_token_size cần kế hoạch rebuild FULLTEXT index để index được tạo theo cấu hình mới. Không đổi cấu hình production mà chưa benchmark kích thước index và latency.

## 11. Kiểm soát stopword và token size cho corpus tiếng Việt

Trước khi điều chỉnh cấu hình, tạo một bảng thử nghiệm với các nhóm từ:

| Nhóm | Ví dụ | Câu hỏi |
|---|---|---|
| Từ đơn ngắn | AI, C, Go | Có bị loại do min token size không? |
| Từ đơn dài | database, transaction | Parser có index như mong đợi không? |
| Từ đa âm tiết | công nghệ, học máy | Có cần tách từ ở ứng dụng không? |
| Cụm chuyên ngành | cơ sở dữ liệu, kiểm soát đồng thời | Cần phrase search hay token nối? |
| Từ rất phổ biến | và, là, của | Có bị stopword loại không? |
| Mã kỹ thuật | SQL, C++, utf8mb4 | Dấu câu và ký tự đặc biệt được xử lý thế nào? |
| Từ có dấu | máy, mây, may | Collation có phân biệt theo yêu cầu không? |

### 11.1. Cấu hình InnoDB

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_%';
~~~

Một số biến quan trọng:
- innodb_ft_min_token_size.
- innodb_ft_max_token_size.
- innodb_ft_enable_stopword.
- innodb_ft_server_stopword_table.
- innodb_ft_user_stopword_table.

Không phải biến nào cũng có cùng scope hoặc khả năng thay đổi động. Xác nhận tài liệu phiên bản trước khi thay đổi. Một số cấu hình phải đặt khi server khởi động hoặc chỉ có hiệu lực khi tạo/rebuild index.

### 11.2. Cấu hình MyISAM

Nếu hệ thống dùng MyISAM, kiểm tra:
- ft_min_word_len.
- ft_max_word_len.
- ft_stopword_file.

Các biến này khác biến InnoDB. Không dùng tên biến InnoDB để suy ra hành vi MyISAM.

### 11.3. Thay đổi cấu hình cần rebuild

Sau khi đổi min token size, max token size, stopword hoặc parser configuration:
1. Xác định FULLTEXT index nào chịu ảnh hưởng.
2. Lưu cấu hình cũ.
3. Lên kế hoạch rebuild.
4. Thử trên staging với bản sao dữ liệu đại diện.
5. So sánh số token/kích thước index và kết quả tìm kiếm.
6. Triển khai trong cửa sổ phù hợp.
7. Kiểm tra lại truy vấn và relevance.
8. Có phương án khôi phục cấu hình và index.

Nếu chỉ đổi biến mà không rebuild, index cũ có thể vẫn chứa token theo quy tắc trước đó.

## 12. Collation và kiểm thử truy vấn có dấu/không dấu

Không chỉ kiểm tra bằng SELECT thường. Hãy kiểm tra trực tiếp FULLTEXT với các truy vấn có dấu, không dấu, hoa/thường và dạng Unicode khác nhau.

Ví dụ tạo dữ liệu:

~~~sql
INSERT INTO knowledge_article(title, body, search_text)
VALUES
('Máy học', 'Giới thiệu máy học và dữ liệu.', 'máy_học giới_thiệu máy_học dữ_liệu'),
('Mây dữ liệu', 'Lưu trữ dữ liệu trên nền tảng đám mây.', 'mây dữ_liệu lưu_trữ dữ_liệu nền_tảng đám_mây'),
('May mặc', 'Quy trình sản xuất hàng may mặc.', 'may_mặc quy_trình sản_xuất hàng may_mặc');
~~~

Truy vấn từng biến thể:

~~~sql
SELECT article_id, title,
       MATCH(search_text) AGAINST ('máy_học' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_article
WHERE MATCH(search_text) AGAINST ('máy_học' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

~~~sql
SELECT article_id, title,
       MATCH(search_text) AGAINST ('may_hoc' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_article
WHERE MATCH(search_text) AGAINST ('may_hoc' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

Kết quả phụ thuộc cách tạo search_text, collation, parser, stopword và token size. Không kết luận từ một ví dụ rằng mọi từ không dấu sẽ tự động khớp bản có dấu.

### 12.1. Ma trận truy vấn tối thiểu

| Truy vấn | Điều cần xác minh |
|---|---|
| máy học | Khớp cụm có dấu |
| may hoc | Hành vi tìm kiếm không dấu |
| MÁY HỌC | Case sensitivity |
| Máy_học | Quy ước nối token |
| máy | Token ngắn và kết quả nhiễu |
| học máy | Đảo thứ tự token |
| "máy học" | Phrase search |
| máy học -quảng cáo | Boolean exclusion |
| SQL | Từ viết tắt kỹ thuật |
| C++ | Dấu câu trong token kỹ thuật |

Mỗi truy vấn phải có danh sách tài liệu mong đợi và tài liệu không mong đợi để đánh giá false positive/false negative.

## 13. Kiểm chứng Unicode normalization

Cùng một từ hiển thị có thể được nhập từ nhiều nguồn:
- Form web.
- File CSV/Excel.
- API bên thứ ba.
- Nội dung copy từ trình soạn thảo.
- Dữ liệu import cũ.

Nếu pipeline chuẩn hóa không đồng nhất, truy vấn có thể không khớp dù giao diện hiển thị giống nhau.

Ở tầng ứng dụng:
- Chuẩn hóa văn bản trước khi lưu, thường là NFC.
- Chuẩn hóa query theo cùng quy tắc.
- Không thay đổi nội dung gốc nếu cần bảo toàn byte/nguồn.
- Có thể lưu hash hoặc version pipeline để theo dõi migration.
- Kiểm thử chuỗi có combining mark.

SQL có thể giúp kiểm tra độ dài ký tự và byte:

~~~sql
SELECT
    title,
    CHAR_LENGTH(title) AS character_count,
    LENGTH(title) AS byte_count,
    HEX(title) AS utf8_bytes
FROM knowledge_article
WHERE article_id = 1;
~~~

CHAR_LENGTH đếm ký tự theo chuỗi; LENGTH đếm byte. HEX giúp quan sát biểu diễn byte khi điều tra dữ liệu Unicode. Các hàm này không thay thế Unicode normalization trong ứng dụng.

## 14. Đánh giá chất lượng tìm kiếm bằng bộ truy vấn chuẩn

Không đánh giá chất lượng chỉ bằng cách gõ vài truy vấn và nhìn kết quả. Hãy tạo bộ test gồm query và các tài liệu liên quan đã được con người gán nhãn.

Ví dụ cấu trúc:

| query_id | query_text | relevant_article_ids | intent |
|---|---|---|---|
| Q001 | cơ sở dữ liệu | 10, 12, 19 | Khái niệm database |
| Q002 | công nghệ thông tin | 21, 22 | Thuật ngữ đa âm tiết |
| Q003 | máy học | 30, 31 | Thuật ngữ có dấu |
| Q004 | may hoc | 30, 31 | Truy vấn không dấu |
| Q005 | SQL | 42, 45 | Từ viết tắt ngắn |
| Q006 | kiểm soát đồng thời | 51, 53 | Cụm chuyên ngành |

Tập đánh giá nên bao gồm:
- Truy vấn ngắn và dài.
- Có dấu/không dấu.
- Chữ hoa/thường.
- Từ đơn và từ đa âm tiết.
- Cụm chuyên ngành.
- Từ viết tắt.
- Lỗi gõ phổ biến.
- Dấu câu và mã kỹ thuật.
- Truy vấn có nhiều ý định.
- Truy vấn không có kết quả phù hợp.

### 14.1. Precision@K

Precision@K đo tỷ lệ kết quả phù hợp trong K kết quả đầu:

[
Precision@K = rac{	ext{số kết quả phù hợp trong top K}}{K}
]

Ví dụ top 5 có 4 tài liệu liên quan:

[
Precision@5 = rac{4}{5} = 0.8
]

Precision cao nghĩa là ít kết quả nhiễu trong nhóm đầu.

### 14.2. Recall@K

Recall@K đo tỷ lệ tài liệu phù hợp được tìm thấy trong top K:

[
Recall@K = rac{	ext{số tài liệu phù hợp trong top K}}{	ext{tổng số tài liệu phù hợp đã gán nhãn}}
]

Nếu có 10 tài liệu phù hợp và top 10 tìm được 6:

[
Recall@10 = rac{6}{10} = 0.6
]

Recall thấp có thể do tokenizer bỏ token, stopword, min token size hoặc truy vấn chưa được chuẩn hóa đúng.

### 14.3. MRR

Mean Reciprocal Rank đánh giá vị trí của kết quả phù hợp đầu tiên:

[
RR(q) = rac{1}{rank của kết quả phù hợp đầu tiên}
]

MRR là trung bình RR trên toàn bộ truy vấn. Nếu tài liệu phù hợp đầu tiên đứng thứ nhất, RR=1; đứng thứ tư, RR=0.25.

MRR hữu ích khi người dùng thường chỉ xem một vài kết quả đầu.

### 14.4. nDCG

Normalized Discounted Cumulative Gain đánh giá ranking với mức độ liên quan nhiều cấp. Một tài liệu rất phù hợp có thể được gán điểm 3, phù hợp một phần điểm 1, không liên quan điểm 0. nDCG phạt kết quả phù hợp xuất hiện quá thấp trong danh sách.

Dùng nDCG khi nhóm đánh giá cần phân biệt tài liệu rất liên quan với tài liệu chỉ có từ khóa trùng.

### 14.5. Đánh giá theo từng nhóm lỗi

Không chỉ tính một điểm trung bình. Hãy chia theo nhóm:
- Có dấu.
- Không dấu.
- Case variation.
- Unicode normalization.
- Từ đa âm tiết.
- Từ viết tắt.
- Stopword.
- Token ngắn.
- Phrase.
- Typo.

Một cấu hình có precision tổng thể cao nhưng recall rất thấp với truy vấn không dấu vẫn có thể không đạt yêu cầu sản phẩm.

## 15. So sánh các chiến lược tokenization

Nên so sánh ít nhất ba baseline:

| Chiến lược | Cách làm | Điểm mạnh | Rủi ro |
|---|---|---|---|
| Built-in parser | Index văn bản gốc theo parser mặc định | Đơn giản, ít thành phần | Không hiểu từ ghép tiếng Việt |
| Application word segmentation | Tách từ tiếng Việt rồi lưu search_text | Giữ được đơn vị từ vựng tốt hơn | Phải đồng bộ tokenizer cho index và query |
| Ngram parser | Chia chuỗi thành n-gram ký tự | Có thể hỗ trợ tìm kiếm ký tự/substring và CJK | Index lớn, dễ nhiễu, không hiểu ngữ nghĩa từ tiếng Việt |

So sánh bằng cùng một corpus, cùng query set, cùng tiêu chí relevance và cùng phần cứng. Không so sánh latency của một cấu hình trên cache nóng với cấu hình khác trên cache lạnh.

Ghi lại:
- Precision@5 và Precision@10.
- Recall@10.
- MRR hoặc nDCG.
- p50/p95 latency.
- Kích thước FULLTEXT index.
- Thời gian nạp/rebuild.
- Chi phí INSERT/UPDATE.
- Tỷ lệ query không có kết quả.

## 16. Kiểm tra FULLTEXT index và cấu hình runtime

Các lệnh chẩn đoán:

~~~sql
SHOW CREATE TABLE knowledge_article;
SHOW INDEX FROM knowledge_article;
SHOW FULL COLUMNS FROM knowledge_article;
~~~

Kiểm tra engine, charset và collation:

~~~sql
SELECT
    TABLE_NAME,
    ENGINE,
    TABLE_COLLATION
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'knowledge_article';
~~~

~~~sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'knowledge_article';
~~~

Kiểm tra FULLTEXT token size và stopword:

~~~sql
SHOW VARIABLES LIKE 'innodb_ft_min_token_size';
SHOW VARIABLES LIKE 'innodb_ft_max_token_size';
SHOW VARIABLES LIKE 'innodb_ft_enable_stopword';
SHOW VARIABLES LIKE 'ngram_token_size';
~~~

InnoDB cung cấp INFORMATION_SCHEMA views để quan sát token đã index trong một số tình huống chẩn đoán:

~~~sql
SET GLOBAL innodb_ft_aux_table = 'app_db/knowledge_article';

SELECT
    WORD,
    DOC_COUNT,
    DOC_ID
FROM information_schema.innodb_ft_index_table
ORDER BY WORD;
~~~

innodb_ft_aux_table là biến phục vụ chẩn đoán InnoDB FULLTEXT; việc đọc các auxiliary table có yêu cầu quyền và trạng thái phù hợp. Không bật hoặc thay đổi cấu hình global tùy tiện trên production. Kiểm tra tài liệu đúng phiên bản trước khi sử dụng.

Nếu không nhìn thấy token mong đợi, kiểm tra stopword, token size, parser và trạng thái index trước khi thay đổi dữ liệu.

## 17. Thay đổi collation, parser và rebuild index

Thay collation của cột có thể làm thay đổi semantics so sánh và cách FULLTEXT xử lý từ. Thay parser hoặc token-size/stopword configuration cũng ảnh hưởng tập token được index.

Một migration có kiểm soát:
1. Lưu SHOW CREATE TABLE và cấu hình FTS hiện tại.
2. Tạo bản sao dữ liệu hoặc staging để thử.
3. Thay đổi charset/collation/parser/configuration trên staging.
4. Rebuild FULLTEXT index.
5. Chạy bộ truy vấn chuẩn.
6. So sánh precision/recall, relevance và latency.
7. Ước lượng dung lượng index và thời gian build.
8. Lên cửa sổ triển khai và phương án rollback.
9. Thực hiện migration production.
10. Xác minh index, collation và kết quả sau triển khai.

Ví dụ xóa và tạo lại FULLTEXT index:

~~~sql
ALTER TABLE knowledge_article
    DROP INDEX ft_knowledge_search;

ALTER TABLE knowledge_article
    ADD FULLTEXT INDEX ft_knowledge_search (search_text);
~~~

Nếu dùng ngram:

~~~sql
ALTER TABLE article_ngram
    ADD FULLTEXT INDEX ft_article_ngram_v2 (content) WITH PARSER ngram;
~~~

Lệnh DDL cụ thể và mức độ khóa/online phụ thuộc phiên bản, engine, kích thước bảng và loại thay đổi. Không mặc định việc tạo lại FULLTEXT index là không gây gián đoạn.

## 18. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Collation tự tách từ tiếng Việt | Collation chỉ quy định so sánh/sắp xếp | Dùng tokenizer phù hợp |
| utf8mb4 tự bảo đảm tìm kiếm tiếng Việt tốt | Charset chỉ bảo đảm khả năng lưu ký tự | Kiểm thử parser, collation và token |
| ai_ci luôn tốt nhất | Bỏ dấu có thể làm tăng false positive | Đánh giá accent-sensitive và insensitive |
| as_cs luôn bắt buộc | Sản phẩm có thể cần truy vấn không dấu | Thiết kế search variant có kiểm soát |
| MySQL hiểu “cơ sở dữ liệu” là một từ | Built-in parser chủ yếu chia token theo ranh giới ký tự | Dùng word segmentation hoặc quy ước nối token |
| Ngram là bộ tách từ tiếng Việt | Ngram chia chuỗi ký tự theo N | Dùng khi bài toán cần n-gram, không kỳ vọng hiểu ngữ nghĩa |
| Từ nào có trong body cũng được index | Token có thể bị loại do độ dài hoặc stopword | Kiểm tra cấu hình FTS |
| Đổi stopword là index cũ tự cập nhật | Index cũ cần được rebuild theo cấu hình mới | Lập kế hoạch rebuild |
| Đổi collation chỉ thay cách hiển thị | Collation ảnh hưởng semantics so sánh và index | Kiểm thử và rebuild phù hợp |
| Tìm kiếm không dấu luôn khớp bản có dấu | Phụ thuộc collation, parser và pipeline | Test query có dấu/không dấu |
| Phrase search hiểu ngữ nghĩa | Phrase search kiểm tra chuỗi token theo thứ tự | Dùng relevance/semantic layer nếu cần |
| FULLTEXT index được tạo nghĩa là optimizer luôn dùng | Kế hoạch phụ thuộc query và cost | Kiểm tra EXPLAIN |
| Một điểm relevance cao nghĩa là kết quả đúng | Relevance chỉ là ranking nội bộ | Đánh giá bằng bộ truy vấn gán nhãn |
| MyISAM và InnoDB có mọi quy tắc FTS giống nhau | Token size, stopword và một số semantics khác nhau | Kiểm tra engine cụ thể |
| Thay min token size không cần rebuild | Index cũ có thể vẫn theo cấu hình trước | Rebuild và kiểm thử lại |

## 19. Quy trình kiểm chứng chất lượng tách từ tiếng Việt

1. Thu thập một corpus đại diện cho nội dung thật.
2. Tạo danh sách truy vấn có dấu, không dấu, từ ghép, viết tắt và thuật ngữ chuyên ngành.
3. Gán nhãn tài liệu liên quan theo mức độ liên quan.
4. Chuẩn hóa Unicode cho tài liệu và truy vấn theo cùng pipeline.
5. Chạy baseline với built-in parser.
6. Kiểm tra token size và stopword có làm mất từ quan trọng không.
7. Thử collation accent-sensitive và accent-insensitive.
8. Thử application word segmentation và tạo search_text riêng.
9. Nếu cần, thử ngram parser như baseline bổ sung.
10. Chạy cùng query set trên từng cấu hình.
11. Tính Precision@K, Recall@K, MRR và nDCG.
12. Phân tích false positive/false negative theo nhóm truy vấn.
13. Đo p50/p95 latency và kích thước index.
14. Đo chi phí ghi và rebuild.
15. Chọn cấu hình có cân bằng chất lượng, tốc độ và khả năng vận hành phù hợp.
16. Lưu tokenizer version, collation, stopword và token-size config cùng kết quả đánh giá.
17. Chạy regression test sau mỗi lần thay đổi pipeline hoặc MySQL version.

## 20. Bài tập thực hành

### Bài 1: So sánh collation

Tạo hai bảng hoặc hai cột với utf8mb4_0900_ai_ci và utf8mb4_0900_as_cs. Chèn các biến thể “ma”, “má”, “mà”, “mã”, “mạ”. So sánh phép bằng thông thường và FULLTEXT. Ghi lại khác biệt.

### Bài 2: Kiểm tra hoa/thường

Tìm cùng một tài liệu bằng “MySQL”, “mysql” và “MYSQL” trên các collation khác nhau. Xác định collation nào phù hợp yêu cầu sản phẩm.

### Bài 3: Built-in parser

Tạo FULLTEXT index trên body gốc. Tìm “cơ sở dữ liệu”, “cơ_sở_dữ_liệu”, “cơ sở” và “dữ liệu”. Quan sát kết quả và giải thích vì sao parser mặc định không hiểu từ ghép.

### Bài 4: Token size

Kiểm tra innodb_ft_min_token_size. Thử truy vấn “AI”, “IoT” và “SQL”. Xác định token nào bị loại, sau đó thiết kế cách xử lý mà không làm thay đổi cấu hình production.

### Bài 5: Stopword

Kiểm tra default stopword table. Tạo corpus có một từ chuyên ngành xuất hiện nhiều. Đánh giá nếu từ đó bị loại khỏi index thì truy vấn sẽ thay đổi thế nào.

### Bài 6: Tách từ ứng dụng

Dùng bộ tách từ tiếng Việt để tạo search_text với quy ước nối âm tiết bằng underscore. Tạo FULLTEXT index và so sánh truy vấn với baseline built-in parser.

### Bài 7: Chuẩn hóa Unicode

Tạo hai chuỗi hiển thị giống nhau nhưng một chuỗi dùng ký tự dựng sẵn và chuỗi kia dùng combining mark. Kiểm tra CHAR_LENGTH, LENGTH, HEX và hành vi tìm kiếm trước/sau khi chuẩn hóa NFC ở ứng dụng.

### Bài 8: Accent folding

Tạo cột search_text_accented và search_text_folded. So sánh truy vấn có dấu và không dấu. Ghi nhận false positive khi bỏ dấu và đề xuất ranking ưu tiên kết quả chính xác.

### Bài 9: Ngram parser

Tạo FULLTEXT index WITH PARSER ngram. Kiểm tra ngram_token_size, tìm các cụm ký tự ngắn và so sánh kích thước index với parser mặc định.

### Bài 10: Boolean và phrase search

Thử +term, -term, prefix wildcard và phrase search trên dữ liệu đã tách từ. Kiểm tra cú pháp và kết quả trên các truy vấn có dấu.

### Bài 11: Bộ đánh giá chất lượng

Tạo ít nhất 30 truy vấn, mỗi truy vấn có tập tài liệu liên quan được gán nhãn. Tính Precision@5, Recall@10 và MRR cho hai cấu hình tokenizer.

### Bài 12: Regression test

Lưu cấu hình collation, parser, token size, stopword và tokenizer version. Thay một cấu hình trong staging, rebuild index và chạy lại toàn bộ query set. Báo cáo chất lượng và latency trước/sau.

## 21. Checklist trước khi triển khai Full-Text Search tiếng Việt

- [ ] Các cột văn bản dùng charset utf8mb4.
- [ ] Đã xác nhận collation thực tế của từng cột FULLTEXT.
- [ ] Đã hiểu ai/ as và ci/cs ảnh hưởng thế nào tới yêu cầu tìm kiếm.
- [ ] Đã kiểm tra danh sách collation có sẵn trên đúng server.
- [ ] Đã phân biệt collation với tokenizer.
- [ ] Đã kiểm tra parser mặc định trên corpus tiếng Việt.
- [ ] Đã đánh giá từ đa âm tiết và cụm chuyên ngành.
- [ ] Đã kiểm tra innodb_ft_min_token_size hoặc ft_min_word_len theo engine.
- [ ] Đã kiểm tra stopword và từ chuyên ngành bị loại.
- [ ] Đã thống nhất Unicode normalization cho tài liệu và query.
- [ ] Đã cân nhắc tách từ ở tầng ứng dụng.
- [ ] Đã giữ nội dung gốc riêng với search_text.
- [ ] Đã dùng cùng tokenizer cho nội dung và truy vấn.
- [ ] Đã đánh giá tìm kiếm có dấu và không dấu.
- [ ] Đã chỉ dùng ngram khi bài toán phù hợp và đã đo false positive.
- [ ] Đã xác nhận MATCH() khớp với FULLTEXT index.
- [ ] Đã kiểm tra Natural Language, Boolean và phrase search.
- [ ] Đã xây query set có relevance labels.
- [ ] Đã đo Precision@K, Recall@K, MRR hoặc nDCG.
- [ ] Đã đo latency, kích thước index và chi phí ghi.
- [ ] Đã lập kế hoạch rebuild sau thay đổi collation/parser/stopword/token size.
- [ ] Đã chạy regression test trên đúng phiên bản MySQL production.

## 22. Kết luận

Chất lượng Full-Text Search tiếng Việt phụ thuộc đồng thời vào charset, collation, parser, token size, stopword và cách chuẩn hóa văn bản. utf8mb4 giúp lưu đầy đủ Unicode; collation quyết định quy tắc so sánh hoa/thường và dấu; parser quyết định cách tách token. Hai cơ chế này không thay thế nhau.

Built-in parser đơn giản nhưng thường tách tiếng Việt theo âm tiết, không tự nhận diện từ ghép đa âm tiết. Ngram parser tạo chuỗi ký tự theo N và phù hợp hơn với một số bài toán CJK/substring; nó không phải bộ tách từ có hiểu biết tiếng Việt. Với tìm kiếm thuật ngữ tiếng Việt, một hướng thực tế là chuẩn hóa Unicode và tách từ ở tầng ứng dụng, lưu search_text riêng, rồi dùng cùng pipeline cho query.

Không chọn collation hoặc tokenizer chỉ dựa trên cảm giác. Hãy tạo corpus và query set có nhãn, kiểm tra biến thể có dấu/không dấu, từ ngắn, stopword, từ ghép và mã kỹ thuật. Đo precision, recall, ranking, latency, kích thước index và chi phí ghi. Sau mọi thay đổi parser, stopword, token size hoặc collation, rebuild index theo kế hoạch và chạy regression test trước khi phát hành.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Full-Text Search Functions](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search.html)
- [MySQL 8.4 Reference Manual – Full-Text Stopwords](https://dev.mysql.com/doc/refman/8.4/en/fulltext-stopwords.html)
- [MySQL 8.4 Reference Manual – Fine-Tuning MySQL Full-Text Search](https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html)
- [MySQL 8.4 Reference Manual – ngram Full-Text Parser](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html)
- [MySQL 8.4 Reference Manual – Full-Text Parser Plugins](https://dev.mysql.com/doc/refman/8.4/en/plugin-types.html)
- [MySQL 8.4 Reference Manual – Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual – Unicode Character Sets](https://dev.mysql.com/doc/refman/8.4/en/charset-unicode.html)
- [MySQL 8.4 Reference Manual – SHOW COLLATION](https://dev.mysql.com/doc/refman/8.4/en/show-collation.html)
- [MySQL 8.4 Reference Manual – InnoDB INFORMATION_SCHEMA FULLTEXT Tables](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-fulltext-tables.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)

