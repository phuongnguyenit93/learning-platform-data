# Bộ phân tích văn bản, điểm liên quan và giới hạn tìm kiếm toàn văn

Tìm kiếm toàn văn (*full-text search*) trong Neo4j giúp tìm các node hoặc relationship dựa trên **nội dung văn bản**: tiêu đề bài viết, mô tả sản phẩm, ghi chú sự kiện, nội dung thảo luận... Thay vì yêu cầu chuỗi khớp hoàn toàn, hệ thống có thể chia văn bản thành từ, xử lý chúng bằng **analyzer**, đối chiếu với câu truy vấn và trả về **điểm liên quan** (*relevance score*) để xếp hạng kết quả.

Bài học thuộc chương **Tìm kiếm nâng cao** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng mô hình **property graph**, Cypher, index/constraint, Java Driver và Spring Data Neo4j để lưu trữ và truy vấn dữ liệu liên kết. Trong bối cảnh đó, full-text index có thể giúp tìm nhanh tập node/relationship ứng viên bằng từ khóa, rồi dùng các quan hệ trong đồ thị để tiếp tục lọc, điều hướng hoặc tổng hợp kết quả.

Sau bài này, bạn có thể:

- Giải thích cách **tokenization**, chuẩn hóa chữ, **stop words**, **stemming** và ngôn ngữ analyzer ảnh hưởng đến kết quả.
- Tạo full-text index, kiểm tra analyzer khả dụng, truy vấn bằng Cypher và đọc `score`.
- Thiết kế tìm kiếm có xếp hạng, lọc nghiệp vụ và phân trang.
- Nhận diện giới hạn của full-text search về ngữ nghĩa, ngôn ngữ, tính nhất quán, bảo mật và hiệu năng.
- Chọn lúc nào nên dùng full-text index, index thông thường hoặc tìm kiếm vector.

## 1. Tìm kiếm toàn văn hoạt động ở đâu trong property graph?

Giả sử ứng dụng quản lý nội dung có các node:

~~~text
(:Author)-[:WROTE]->(:Article {title, body, lang, published})
(:Article)-[:TAGGED_WITH]->(:Topic {name})
(:Article)-[:RELATED_TO]->(:Article)
~~~

Một câu hỏi như “tìm các bài viết về Neo4j, rồi hiển thị chủ đề liên quan” có hai phần:

1. **Tìm bằng văn bản:** lấy các node `Article` có `title` hoặc `body` phù hợp từ khóa, kèm điểm liên quan.
2. **Truy vấn đồ thị:** từ những node đã tìm được, đi theo `TAGGED_WITH`, `RELATED_TO` hoặc các quan hệ khác.

Đây là điểm mạnh khi kết hợp full-text search với Cypher: tìm kiếm văn bản xác định tập ứng viên, còn property graph mô tả những quan hệ và điều kiện nghiệp vụ cần kiểm tra tiếp.

| Cơ chế | Phù hợp khi | Không nên kỳ vọng |
| --- | --- | --- |
| So khớp thuộc tính bằng `=` và range/text index thông thường | Tra cứu mã định danh, email chuẩn hóa, khoảng thời gian và các điều kiện chính xác. | Tự tách từ, stemming hoặc xếp hạng độ liên quan. |
| Full-text index | Tìm từ/cụm từ trong tiêu đề và mô tả; hỗ trợ cú pháp truy vấn văn bản, phân tích từ và xếp hạng. | Hiểu đầy đủ ý nghĩa ngữ cảnh như một mô hình ngôn ngữ; kiểm tra uniqueness. |
| Vector index | Truy xuất nội dung tương đồng về biểu diễn embedding, khi hệ thống đã tạo vector thích hợp. | Tự bảo đảm so khớp từ khóa tuyệt đối hoặc dữ liệu có cấu trúc là chính xác. |

Neo4j sử dụng Lucene cho full-text index. Khác với một số index thông thường được bộ lập kế hoạch Cypher tự cân nhắc, full-text index thường được truy vấn **tường minh qua procedure** như `db.index.fulltext.queryNodes` hoặc `db.index.fulltext.queryRelationships`. Tạo full-text index không có nghĩa mọi biểu thức `CONTAINS` trong `MATCH ... WHERE` sẽ tự sử dụng index đó.

## 2. Analyzer: biến văn bản thành các token có thể tìm kiếm

**Analyzer** là bộ xử lý văn bản được dùng khi lập chỉ mục và khi phân tích truy vấn tìm kiếm. Tùy analyzer, quá trình có thể bao gồm:

~~~text
Văn bản gốc
   |
   v
Tokenizer: tách thành token
   |
   v
Token filters: chuyển chữ thường, bỏ stop word, stemming...
   |
   v
Các token được lưu và đối chiếu trong full-text index
~~~

Các bước cụ thể **khác nhau theo analyzer**; sơ đồ là mô hình khái quát, không phải lời khẳng định mọi analyzer đều áp dụng tất cả bộ lọc.

### 2.1. Tách từ (*tokenization*)

Với cụm “Graph databases and Neo4j”, một analyzer theo từ có thể chia thành những token gần như `graph`, `databases`, `and`, `neo4j`. Một analyzer dạng `keyword` có thể coi **cả chuỗi** như một token. Vì vậy, chọn analyzer là quyết định ảnh hưởng trực tiếp tới khả năng tìm kiếm từng phần hay toàn bộ văn bản.

Đối với ngôn ngữ như tiếng Việt, **ranh giới khoảng trắng không luôn là ranh giới từ vựng**. Ví dụ “cơ sở dữ liệu” gồm nhiều âm tiết nhưng biểu đạt một cụm thuật ngữ. Analyzer chỉ tách theo khoảng trắng có thể không nhận biết đây là một đơn vị ngữ nghĩa; điều đó ảnh hưởng tới truy vấn cụm từ, từ đồng nghĩa và đánh giá kết quả.

### 2.2. Chuẩn hóa chữ hoa/chữ thường

Nhiều analyzer chuẩn hóa `Neo4j` và `neo4j` về biểu diễn token tương tự nhau, giúp tìm kiếm không phụ thuộc cách viết hoa. Nhưng **không được giả định mọi analyzer đều giống nhau**, nhất là analyzer dạng `keyword` hoặc analyzer được cấu hình khác. Tương tự, việc xử lý dấu tiếng Việt không mặc nhiên đồng nghĩa với “bỏ dấu”; cần thử riêng các cặp `đồ thị`/`do thi`, `cơ sở`/`co so` trên analyzer thực tế.

### 2.3. Stop words

Stop words là những từ phổ biến có thể bị analyzer loại bỏ khỏi tập token, chẳng hạn một số từ chức năng trong tiếng Anh. Nếu chọn analyzer tiếng Anh có danh sách stop words, truy vấn chỉ gồm các từ bị loại bỏ có thể trả về rất ít hoặc không có kết quả.

Không phải mọi analyzer đều loại stop words. Ví dụ tên `standard-no-stop-words` thể hiện hướng xử lý không loại stop words. Tác động cụ thể còn tùy danh sách từ và phiên bản triển khai.

### 2.4. Stemming

Stemming đưa các biến thể hình thái về một dạng gốc gần đúng, ví dụ analyzer tiếng Anh có thể xử lý những biến thể như “connect”, “connected”, “connecting” theo cách giúp tìm kiếm rộng hơn. Stemming **không phải dịch nghĩa** và không thay thế tìm kiếm từ đồng nghĩa. Nó cũng có thể dẫn tới khớp rộng hơn mong muốn hoặc không phù hợp với một số tên riêng, thuật ngữ kỹ thuật.

### 2.5. Liệt kê analyzer khả dụng

Trước khi chọn analyzer, hãy hỏi chính database đang sử dụng:

~~~cypher
CALL db.index.fulltext.listAvailableAnalyzers();
~~~

Procedure này hiển thị tên analyzer khả dụng và thông tin mô tả (các cột có thể phụ thuộc phiên bản). Trong những bản Neo4j hỗ trợ, có thể chọn các analyzer như `english` hoặc `standard-no-stop-words`; **không tự giả định một analyzer tiếng Việt có sẵn** nếu chưa thấy trong kết quả.

Việc chọn analyzer cần dựa trên **ngôn ngữ dữ liệu, kiểu truy vấn người dùng nhập và kết quả thử nghiệm**. Chẳng hạn, một index cho tài liệu tiếng Anh có thể ưu tiên analyzer tiếng Anh để xử lý biến thể từ. Một kho tài liệu đa ngôn ngữ cần đánh giá sự đánh đổi giữa analyzer chung, phân tách theo ngôn ngữ hoặc chuẩn hóa riêng trước khi lập chỉ mục.

## 3. Bài thực hành: tạo bộ dữ liệu và full-text index

Các lệnh tạo/xóa trong bài chỉ nên chạy trên **database học tập**. Ví dụ dùng label `SearchDoc` để không ảnh hưởng node nghiệp vụ thực tế.

### 3.1. Chuẩn bị năm tài liệu minh họa

~~~cypher
UNWIND [
  {id: 'D01', title: 'Neo4j và Cypher cơ bản',
   body: 'Hướng dẫn truy vấn node và relationship trong đồ thị.', active: true},
  {id: 'D02', title: 'Tối ưu truy vấn Neo4j',
   body: 'Phân tích kế hoạch truy vấn Cypher và sử dụng index.', active: true},
  {id: 'D03', title: 'Mô hình dữ liệu đồ thị',
   body: 'Thiết kế node, relationship và property graph.', active: true},
  {id: 'D04', title: 'Cơ sở dữ liệu quan hệ',
   body: 'Giới thiệu SQL, bảng và khóa ngoại.', active: true},
  {id: 'D05', title: 'Neo4j full-text search',
   body: 'Tìm kiếm văn bản bằng Lucene, analyzer và điểm liên quan.', active: false}
] AS row
MERGE (d:SearchDoc {docId: row.id})
SET d.title = row.title,
    d.body = row.body,
    d.active = row.active;
~~~

`MERGE` giúp minh họa chạy lại bài tập khi mỗi `docId` chỉ ứng với một node. Trong dữ liệu thật, nên dùng uniqueness constraint cho khóa nghiệp vụ để bảo vệ trước các yêu cầu ghi đồng thời; `MERGE` đơn lẻ không thay thế constraint.

### 3.2. Tạo full-text index có tên

~~~cypher
CREATE FULLTEXT INDEX search_docs_ft IF NOT EXISTS
FOR (d:SearchDoc)
ON EACH [d.title, d.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words'
  }
};
~~~

Trong đoạn code, `ON EACH [d.title, d.body]` cho biết cả hai thuộc tính văn bản đều được lập chỉ mục. Nếu node thiếu `title` nhưng có `body` dạng chuỗi hợp lệ, nó vẫn có thể được đưa vào index. Index này **không kiểm tra tính duy nhất** của tiêu đề.

Neo4j lập full-text index cho thuộc tính văn bản thích hợp (chuỗi hoặc danh sách chuỗi được hỗ trợ), không chuyển mọi kiểu dữ liệu tùy ý thành văn bản để tìm kiếm. Khi một node có nhiều label, nó vẫn chỉ phải khớp phạm vi label được khai báo để có thể được lập chỉ mục theo index tương ứng.

Tên analyzer được viết bằng khóa cấu hình `fulltext.analyzer` đặt trong dấu backtick vì chứa dấu chấm. Ở ví dụ này ta chọn `standard-no-stop-words` để dễ quan sát truy vấn từ khóa trong một kho nội dung tiếng Việt; lựa chọn này **không có nghĩa Neo4j hiểu cấu trúc ngữ nghĩa tiếng Việt**.

### 3.3. Chờ index sẵn sàng và xem metadata

Sau khi tạo, index có thể cần thời gian để lập chỉ mục dữ liệu hiện có. Với môi trường thực hành, có thể chờ các index trong database hoàn tất:

~~~cypher
CALL db.awaitIndexes();
~~~

Hoặc kiểm tra thông tin index:

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties, options
WHERE name = 'search_docs_ft'
RETURN name, type, state, populationPercent, labelsOrTypes, properties, options;
~~~

Kiểm tra `type` là `FULLTEXT`, `state` là `ONLINE`, các thuộc tính đúng và `options` có analyzer đã chọn. Giá trị và các trường metadata có thể khác giữa phiên bản Neo4j; kiểm tra trên database thực tế thay vì chỉ dựa vào thông báo thành công của `IF NOT EXISTS`.

### 3.4. Truy vấn từ khóa và trả điểm liên quan

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', 'Neo4j')
YIELD node, score
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score AS diemLienQuan
ORDER BY diemLienQuan DESC, maTaiLieu ASC
LIMIT 10;
~~~

Với dữ liệu mẫu, các tài liệu có từ “Neo4j” như D01, D02 và D05 là những ứng viên phù hợp. **Không ấn định điểm số hoặc thứ hạng chính xác trong tài liệu học**, vì điểm phụ thuộc analyzer, đặc điểm tập văn bản và cách Lucene tính điểm ở phiên bản chạy thực tế. D05 vẫn có thể xuất hiện dù `active = false` vì index tìm kiếm văn bản không tự hiểu trạng thái xuất bản.

## 4. Điểm liên quan (*relevance score*) có ý nghĩa gì?

Procedure `db.index.fulltext.queryNodes` trả về `node` cùng một số `score`. Điểm này là **thước đo xếp hạng mức khớp theo cơ chế tìm kiếm văn bản** của Lucene, không phải xác suất nội dung đúng, mức độ tin cậy của tài liệu hay độ tương đồng ngữ nghĩa tuyệt đối.

Những yếu tố có thể ảnh hưởng điểm:

- **Từ khóa khớp:** số lượng và đặc điểm token được tìm thấy.
- **Mức phổ biến của token:** một từ hiếm trong tập chỉ mục có thể đóng góp khác với một từ rất phổ biến.
- **Độ dài và phân bố văn bản:** các văn bản ngắn/dài và tần suất token có thể được đánh trọng số khác nhau.
- **Cú pháp query:** phép kết hợp từ khóa, cụm từ và trọng số tăng cường (*boost*) làm thay đổi cách tính điểm.
- **Trạng thái chỉ mục:** thêm, sửa, xóa tài liệu hoặc đổi analyzer/index có thể làm điểm và thứ tự thay đổi.

Vì vậy, hãy diễn giải score theo **cùng một truy vấn và cùng một index tại thời điểm nhất định**. Không nên mặc định rằng `score = 3.5` có nghĩa tài liệu liên quan “35%”, hoặc rằng 3.5 ở hai index khác nhau có cùng ý nghĩa.

### 4.1. Xếp hạng ổn định khi điểm bằng nhau

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', 'Cypher')
YIELD node, score
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score
ORDER BY score DESC, maTaiLieu ASC
LIMIT 5;
~~~

Sắp xếp chính theo `score DESC` để lấy kết quả liên quan nhất, sắp xếp phụ theo `docId ASC` để tạo thứ tự rõ ràng khi hai điểm bằng nhau. Chỉ dùng `LIMIT 5` mà không quy định thứ tự ở cuối truy vấn sẽ khiến cách hiển thị/phân trang khó kiểm soát nếu thêm các bước Cypher khác.

### 4.2. Có nên đặt ngưỡng score?

Có thể lọc theo ngưỡng trong một bài toán đã đo đạc:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $query)
YIELD node, score
WITH node, score
WHERE score >= $minScore
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC
LIMIT $topN;
~~~

Các tham số được ứng dụng truyền vào; `$minScore` và `$topN` **không có giá trị mặc định** trong câu Cypher này. Cần kiểm tra kiểu dữ liệu và miền giá trị trước khi gọi.

Ngưỡng điểm phải được xác định bằng đánh giá thực nghiệm trên truy vấn và dữ liệu đại diện. Nó có thể cần điều chỉnh khi thay analyzer, thuộc tính chỉ mục, tập tài liệu hoặc phiên bản triển khai. Một ngưỡng cố định lấy từ ví dụ học tập dễ làm mất những kết quả hữu ích trong hệ thống thật.

## 5. Cú pháp tìm kiếm: từ khóa, cụm từ và phép kết hợp

Tham số query của full-text procedure dùng cú pháp tìm kiếm do Lucene hỗ trợ. Một số dạng thường gặp:

| Ý định | Chuỗi truy vấn minh họa | Chú ý |
| --- | --- | --- |
| Từ khóa | `Neo4j` | Tìm token phù hợp theo analyzer của index. |
| Hai từ bắt buộc | `Neo4j AND Cypher` | Cả hai điều kiện cần được thỏa theo cơ chế query. |
| Một trong hai từ | `Neo4j OR Cypher` | Mở rộng tập ứng viên. |
| Cụm từ | `"property graph"` | Tìm một chuỗi token/cụm từ; kết quả còn tùy phân tích token. |
| Chỉ tìm trong trường | `title:Neo4j` | Áp dụng cho trường thuộc tính được lập chỉ mục tương ứng. |
| Tiền tố | `graph*` | Mở rộng theo tiền tố token; có thể tốn chi phí. |
| Gần đúng ký tự | `grahp~1` | Fuzzy matching có thể giúp với lỗi gõ; không đồng nghĩa tìm theo nghĩa. |
| Tăng trọng số | `title:Neo4j^3 OR body:Neo4j` | Boost ưu tiên khớp trong tiêu đề; không bảo đảm xếp hạng tuyệt đối. |

Ví dụ chạy trực tiếp để tìm cụm từ:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', '"property graph"')
YIELD node, score
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC;
~~~

Ví dụ ưu tiên tiêu đề:

~~~cypher
CALL db.index.fulltext.queryNodes(
  'search_docs_ft',
  'title:Neo4j^3 OR body:Neo4j'
)
YIELD node, score
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC
LIMIT 10;
~~~

**Điểm cần phân biệt:** `AND` và `OR` trong chuỗi query là cú pháp truy vấn Lucene, không phải mệnh đề `WHERE` Cypher. Các toán tử, ký tự đặc biệt, wildcard và dấu ngoặc kép cần được xử lý đúng. Truy vấn do người dùng nhập nên đi qua lớp kiểm soát cú pháp, escaping hoặc công cụ dựng query phù hợp với tính năng sản phẩm. Dùng tham số Cypher để tránh ghép chuỗi Cypher động:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $searchQuery)
YIELD node, score
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC
LIMIT $pageSize;
~~~

Truyền qua `$searchQuery` bảo vệ cấu trúc câu Cypher khỏi việc nối trực tiếp dữ liệu vào câu lệnh, **nhưng không tự vô hiệu hóa các toán tử Lucene trong nội dung tham số**. Nếu ứng dụng muốn tìm đúng chuỗi văn bản do người dùng gõ, phải kiểm soát cách diễn giải ký tự đặc biệt theo thiết kế tìm kiếm.

## 6. Giới hạn kết quả, lọc nghiệp vụ và phân trang

Tìm kiếm thường chỉ hiển thị 10–20 tài liệu đầu tiên. Tuy nhiên, phải xác định rõ thứ tự của các bước **tìm kiếm → lọc → xếp hạng → giới hạn**.

### 6.1. Lọc trước khi LIMIT

Tài liệu D05 có `active = false`. Nếu giao diện chỉ hiển thị tài liệu đang hoạt động:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $searchQuery)
YIELD node, score
WITH node, score
WHERE node.active = true
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score
ORDER BY score DESC, maTaiLieu ASC
LIMIT $pageSize;
~~~

Đặt `WHERE node.active = true` trước giới hạn giúp lấy **tối đa N tài liệu đang hoạt động** từ tập kết quả phù hợp. Nếu giới hạn trước rồi mới lọc, một vài tài liệu bị loại có thể khiến trang hiển thị ít hơn N kết quả dù vẫn còn kết quả hợp lệ ở phía sau.

Tuy vậy, lọc qua Cypher **sau khi** truy vấn full-text có thể yêu cầu xử lý nhiều hit rồi mới trả đủ số lượng. Trên dữ liệu lớn, cần đánh giá kế hoạch, thiết kế quyền truy cập và cấu trúc chỉ mục để tránh truy xuất quá nhiều ứng viên.

### 6.2. Kết hợp tìm kiếm văn bản với đường đi trong đồ thị

Giả sử ứng dụng thật có `(:Article)-[:TAGGED_WITH]->(:Topic)`, một query có thể tìm bài viết qua full-text index `article_text_ft` rồi kiểm tra chủ đề:

~~~cypher
CALL db.index.fulltext.queryNodes('article_text_ft', $query)
YIELD node AS article, score
MATCH (article)-[:TAGGED_WITH]->(topic:Topic)
WHERE article.published = true
  AND topic.name = $topicName
WITH DISTINCT article, score
RETURN article.title AS tieuDe, score
ORDER BY score DESC, tieuDe ASC
LIMIT $topN;
~~~

Index `article_text_ft` là tên minh họa cho ứng dụng thật, **không phải index đã tạo cho `SearchDoc` ở mục 3**. Ở đây, `DISTINCT` ngăn bài viết bị lặp nếu mô hình có nhiều quan hệ/nhánh phù hợp trong truy vấn. Khi bổ sung `MATCH` hay tổng hợp, phải xác nhận rằng số hàng và ý nghĩa `score` đang được giữ đúng trước khi giới hạn.

### 6.3. Phân trang theo score

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $searchQuery)
YIELD node, score
WITH node, score
WHERE node.active = true
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score
ORDER BY score DESC, maTaiLieu ASC
SKIP $offset
LIMIT $pageSize;
~~~

Với `$offset = 0`, `$pageSize = 10`, ứng dụng lấy trang đầu; `$offset = 10` lấy trang tiếp. Các tham số phải là số nguyên không âm, và cần hạn chế `pageSize` tối đa theo chính sách API.

Lưu ý khi dữ liệu/index thay đổi giữa hai lần đọc, **điểm và thứ hạng có thể thay đổi**, gây lặp hoặc thiếu bản ghi giữa các trang. `SKIP` lớn cũng có thể làm việc truy vấn chậm hơn. Với kết quả nhạy cảm về thứ tự, cân nhắc trải nghiệm tải thêm, giới hạn độ sâu phân trang, cache kết quả hoặc giải pháp snapshot/cursor được thiết kế và kiểm chứng theo cách tính score hiện tại. Không coi `score` là khóa phân trang bất biến.

## 7. Giới hạn thực tế của tìm kiếm toàn văn

### 7.1. Khớp từ vựng không đồng nghĩa hiểu ngữ nghĩa

Truy vấn “cách tăng tốc database đồ thị” có thể không tìm thấy một bài dùng cụm “tối ưu truy vấn Cypher” dù cả hai gần nhau về nghĩa nếu không có token trùng hoặc quy tắc mở rộng phù hợp. Full-text index **không tự hiểu từ đồng nghĩa, ý định người dùng hay nội dung paraphrase**.

Một hệ thống có thể kết hợp full-text search với vector search hoặc cơ chế xếp hạng lại, nhưng cần đánh giá chất lượng, chi phí và phạm vi dữ liệu. Những kỹ thuật đó không thay thế kiểm tra quyền truy cập và điều kiện nghiệp vụ trên đồ thị.

### 7.2. Analyzer không tự giải quyết mọi ngôn ngữ

Chọn `english` cho nội dung tiếng Việt có thể gây vấn đề về stop words, stemming hoặc cách tách token. Ngược lại, analyzer chung có thể thiếu hiểu biết về hình thái từ tiếng Anh. Với kho đa ngôn ngữ, cân nhắc tách chỉ mục theo tập node/label ngôn ngữ, chuẩn hóa dữ liệu, cấu hình analyzer khả dụng, hoặc dùng một tầng tìm kiếm chuyên biệt nếu yêu cầu phân đoạn từ phức tạp.

Nên xây dựng bộ truy vấn đánh giá chứa lỗi dấu, tên riêng, từ ghép, chữ viết tắt và nội dung đa ngôn ngữ. Không khẳng định “hỗ trợ tiếng Việt đầy đủ” chỉ vì truy vấn một từ có dấu trả về kết quả.

### 7.3. Full-text index không phải ràng buộc dữ liệu

Full-text index không tự bảo đảm email duy nhất, ngày tạo tồn tại, khóa kiểu đúng hoặc quan hệ hợp lệ. Những bất biến đó cần constraint, kiểm tra nghiệp vụ và mô hình dữ liệu phù hợp. Một thuộc tính không được lập chỉ mục, giá trị null hoặc kiểu không hỗ trợ có thể không đóng góp token; index không tự động báo lỗi hợp lệ dữ liệu cho mọi trường hợp như constraint.

### 7.4. Không phải truy vấn con chuỗi tùy ý

Analyzer có thể tách chuỗi tại dấu câu, bỏ từ dừng hoặc biến đổi token. Do đó, full-text search khác với phép kiểm tra “chuỗi A có nằm nguyên văn trong B không?”. Các truy vấn wildcard quá rộng (đặc biệt khi dùng tiền tố rỗng hoặc wildcard ở đầu) có thể tiêu tốn tài nguyên. Nếu cần tra cứu mã đơn, số điện thoại chuẩn hóa hoặc mã định danh khớp hoàn toàn, index thông thường và `=` thường rõ ràng hơn.

### 7.5. Score không so sánh tùy ý giữa các query/index

Score là tín hiệu xếp hạng, không phải thước đo chất lượng tuyệt đối. Việc đổi tập tài liệu, thêm thuộc tính, đổi analyzer hoặc phiên bản Lucene có thể khiến các score thay đổi. Đừng lấy `score` của nhiều index khác nhau rồi sắp xếp chung như thể cùng một thang đo nếu chưa có phương pháp hiệu chỉnh.

### 7.6. Phải kiểm soát an toàn và giới hạn tài nguyên

Người dùng có thể nhập query quá dài, nhiều phép `OR`, wildcard/fuzzy rộng hoặc biểu thức đặc biệt làm tăng chi phí. Ứng dụng nên giới hạn độ dài và độ phức tạp query, kiểm soát tham số phân trang, giới hạn thời gian và số kết quả, ghi nhận quan sát hiệu năng khi vận hành.

Nếu dữ liệu có **tenant** hoặc quyền đọc khác nhau, kết quả phải được lọc theo quyền và ngữ cảnh người dùng ở tầng được tin cậy. Không lộ `score`, nội dung hay số lượng kết quả của tài liệu không được phép truy cập. Việc lọc tenant sau procedure cần đánh giá cả tính đúng đắn, tài nguyên và khả năng tiết lộ thông tin qua thời gian/metadata nếu hệ thống có yêu cầu cách ly nghiêm ngặt.

## 8. Tính nhất quán, bảo trì index và thay analyzer

### 8.1. Đồng bộ mặc định và cập nhật eventual consistency

Trong cấu hình full-text index thông thường, các thay đổi được áp dụng cùng cơ chế cập nhật chỉ mục của database. Neo4j cũng cung cấp lựa chọn **eventual consistency** để đưa việc cập nhật full-text index ra khỏi đường ghi đồng bộ:

~~~cypher
CREATE FULLTEXT INDEX search_docs_async_ft IF NOT EXISTS
FOR (d:SearchDoc)
ON EACH [d.title, d.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words',
    `fulltext.eventually_consistent`: true
  }
};
~~~

Với tùy chọn này, ứng dụng **không nên giả định ghi xong là tìm thấy ngay**: cập nhật có thể được đưa vào index sau đó. Nếu một bài kiểm tra cần đợi cập nhật eventual-consistent hoàn tất, Neo4j cung cấp procedure:

~~~cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
~~~

Procedure giúp đồng bộ mục tiêu kiểm thử/vận hành ở thời điểm gọi, không có nghĩa nên gọi sau mọi request ghi trong ứng dụng production. Hiệu năng, khả năng hiển thị của thay đổi và ngữ nghĩa giao dịch cần được kiểm chứng trên phiên bản Neo4j thực tế.

### 8.2. Đổi analyzer là thay đổi schema

Analyzer được cấu hình khi tạo index. Khi cần thay cách tách từ hoặc stemming, hãy lập kế hoạch **tạo index mới với tên mới**, xác minh index đạt `ONLINE` và thử cùng tập query đánh giá, chuyển ứng dụng sang index mới rồi mới xóa index cũ. Cách chuyển dần này có thể giảm gián đoạn đọc nếu schema và tài nguyên cho phép.

Ví dụ tạo index thứ hai dùng analyzer tiếng Anh cho tập dữ liệu **phù hợp ngôn ngữ**:

~~~cypher
CREATE FULLTEXT INDEX search_docs_english_ft IF NOT EXISTS
FOR (d:SearchDoc)
ON EACH [d.title, d.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'english'
  }
};
~~~

Đây là ví dụ cú pháp; **không nên triển khai analyzer tiếng Anh cho toàn bộ dữ liệu tiếng Việt trong ví dụ học tập mà không đo chất lượng**. Nếu chỉ mục mới cùng label/thuộc tính với chỉ mục cũ, hai index vẫn có thể trả kết quả khác nhau vì cách phân tích token.

Sau khi hoàn tất chuyển đổi và xác nhận không còn luồng đọc sử dụng tên cũ:

~~~cypher
DROP INDEX search_docs_ft IF EXISTS;
~~~

Lệnh `DROP INDEX` xóa cấu trúc chỉ mục, **không xóa node hay thuộc tính gốc**. Tuy nhiên, các query vẫn gọi tên index đã xóa sẽ thất bại. Cần quản lý việc đổi tên index và cập nhật code Java Driver/Spring Data Neo4j thông qua quy trình migration rõ ràng.

### 8.3. Quan sát lỗi index

Khi tìm kiếm không có kết quả dù dữ liệu tồn tại, nên kiểm tra:

1. Index đã được tạo trên đúng database, đúng label/type và thuộc tính chưa?
2. Trạng thái index đã `ONLINE` chưa, có lỗi khi populate hoặc cập nhật không?
3. Analyzer hiện tại biến văn bản và query thành token như thế nào?
4. Thuộc tính có đúng kiểu chuỗi/danh sách chuỗi và có giá trị thực không?
5. Có bật eventual consistency nên chưa thấy bản ghi mới không?
6. Sau khi tìm được ứng viên, các điều kiện `WHERE`, `MATCH`, `DISTINCT`, `LIMIT` có loại bớt hàng hay không?

Không bắt đầu bằng việc drop/recreate index khi chưa biết nguyên nhân; việc tạo lại trên dữ liệu lớn có thể tốn thời gian và tài nguyên.

## 9. Tìm kiếm trên relationship

Full-text index có thể được tạo cả cho các thuộc tính văn bản của relationship. Ví dụ nghiệp vụ lưu đánh giá bằng `[:REVIEWED {comment}]`:

~~~cypher
CREATE FULLTEXT INDEX review_comments_ft IF NOT EXISTS
FOR ()-[r:REVIEWED]-()
ON EACH [r.comment]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words'
  }
};
~~~

Truy vấn bằng procedure riêng cho relationship:

~~~cypher
CALL db.index.fulltext.queryRelationships('review_comments_ft', $query)
YIELD relationship, score
RETURN relationship.comment AS binhLuan, score
ORDER BY score DESC
LIMIT $topN;
~~~

Nếu cần biết ai đánh giá sản phẩm nào, tiếp tục dùng các node đầu/cuối của relationship và kiểm soát quyền truy cập trên đồ thị. Điểm của relationship không nên so sánh trực tiếp với điểm của node từ một index khác vì môi trường tính score khác nhau.

## 10. Sử dụng từ Java Driver và Spring Data Neo4j

Ứng dụng có thể dùng Java Driver để gọi procedure, truyền từ khóa qua tham số, rồi xử lý các hàng `node` và `score`. Ví dụ rút gọn sau chỉ lấy các trường cần hiển thị:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

import java.util.List;
import java.util.Map;

public class SearchRepository {
    private final Driver driver;

    public SearchRepository(Driver driver) {
        this.driver = driver;
    }

    public List<Record> search(String query, int limit) {
        if (query == null || query.isBlank() || limit < 1 || limit > 50) {
            throw new IllegalArgumentException("Từ khóa hoặc giới hạn không hợp lệ");
        }

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                    CALL db.index.fulltext.queryNodes('search_docs_ft', $query)
                    YIELD node, score
                    WHERE node.active = true
                    RETURN node.docId AS docId, node.title AS title, score
                    ORDER BY score DESC, docId ASC
                    LIMIT $limit
                    """, Map.of("query", query, "limit", limit)).list();
        }
    }
}
~~~

Đoạn code giả định ứng dụng đã khởi tạo và quản lý vòng đời `Driver`; database `neo4j` chỉ là tên minh họa. Trong dự án thực, nên chuyển `Record` thành DTO và xử lý lỗi/timeout quan sát được. Đoạn này giới hạn số ký tự query ở mức nghiệp vụ chưa được bổ sung; ứng dụng sản xuất cần kiểm soát cả chiều dài và độ phức tạp cú pháp Lucene của query.

Với Spring Data Neo4j, có thể thực thi một truy vấn Cypher gọi procedure thông qua repository hoặc client theo phiên bản thư viện đang dùng. Việc đánh dấu entity để ánh xạ dữ liệu không tự tạo quy tắc phân tích từ, score hay full-text index mong muốn; schema index vẫn cần quản lý và kiểm chứng tường minh.

## 11. Những sai lầm phổ biến

| Hiện tượng | Giải thích thường gặp | Cách xử lý |
| --- | --- | --- |
| Tài liệu có chữ cần tìm nhưng không ra kết quả | Analyzer bỏ token, biến đổi từ, index chưa `ONLINE` hoặc index không bao phủ thuộc tính. | Xem analyzer, trạng thái, label/type/thuộc tính và chạy query nhỏ để kiểm chứng. |
| Tìm `Neo4j` ra kết quả, nhưng tìm không dấu tiếng Việt lại không ra | Khả năng xử lý dấu/ngôn ngữ của analyzer chưa khớp kỳ vọng. | Kiểm tra bằng bộ truy vấn mẫu; chuẩn hóa hoặc thiết kế analyzer thích hợp. |
| Thêm tài liệu xong chưa tìm thấy ngay | Index đang populate hoặc có eventual consistency. | Xem trạng thái index; nếu dùng eventual consistency, đo độ trễ/đợi refresh khi cần. |
| Score thay đổi khi dữ liệu phát triển | Điểm phụ thuộc thống kê và cơ chế xếp hạng của Lucene. | Đánh giá thứ hạng và chất lượng tìm kiếm, tránh ngưỡng điểm tùy tiện. |
| Trang 2 có bản ghi lặp của trang 1 | Score/index/dữ liệu đổi giữa hai lần truy vấn; thứ tự phụ chưa cố định. | Thêm khóa phụ, quản lý độ ổn định của kết quả và chiến lược phân trang. |
| Giới hạn 10 rồi lọc quyền chỉ còn 2 tài liệu | `LIMIT` đặt trước lọc nghiệp vụ. | Lọc trước khi giới hạn; kiểm tra hiệu năng và cách ly dữ liệu. |
| Truy vấn có wildcard chạy rất chậm | Biểu thức mở rộng quá nhiều token/hit. | Giới hạn cú pháp, thời gian, phạm vi dữ liệu và đo tải thực. |
| `WHERE title CONTAINS ...` không dùng full-text index | Full-text index được gọi tường minh qua procedure, có cơ chế khác biểu thức chuỗi Cypher. | Dùng `db.index.fulltext.queryNodes` hoặc chọn index và truy vấn khớp nhu cầu. |
| Đổi analyzer nhưng kết quả không đổi | Chỉnh code/query mà chưa xây dựng lại index với analyzer mới. | Tạo index mới có cấu hình mới, xác minh và chuyển đổi có kiểm soát. |

## 12. Bài tập áp dụng

**Bài 1 — Giải thích analyzer:** Cho hai query `Neo4j AND Cypher` và `"Neo4j Cypher"`. Giải thích tại sao cùng một tài liệu có thể khớp query thứ nhất nhưng không khớp query thứ hai. Sau đó thử trên `SearchDoc` và quan sát kết quả thực tế của analyzer đã chọn.

**Bài 2 — Top-3 bài viết công khai:** Dùng index `search_docs_ft` để tìm tài liệu liên quan `Neo4j`, chỉ lấy node có `active = true` và trả tối đa ba kết quả theo score giảm dần, phá hòa bằng `docId`.

Gợi ý:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', 'Neo4j')
YIELD node, score
WITH node, score
WHERE node.active = true
RETURN node.docId AS docId, node.title AS title, score
ORDER BY score DESC, docId ASC
LIMIT 3;
~~~

**Bài 3 — Tối ưu hiển thị:** Một trang tìm kiếm có `$offset = 10000` và `$pageSize = 20`, trong khi nội dung được cập nhật liên tục. Hãy giải thích hai vấn đề về chi phí và độ ổn định thứ tự, rồi đề xuất cách giới hạn độ sâu phân trang và kiểm nghiệm phương án.

**Bài 4 — Kho tài liệu tiếng Việt:** Thiết kế tập kiểm thử gồm câu không dấu, có dấu, từ ghép, tên riêng và lỗi gõ. Trình bày cách so sánh một analyzer chung với analyzer khác (nếu khả dụng) dựa trên **precision** (tỷ lệ kết quả trả về là hữu ích), **recall** (tỷ lệ kết quả hữu ích được tìm thấy) và độ trễ truy vấn. Không kết luận chỉ từ một query mẫu.

**Bài 5 — Di chuyển index:** Mô tả kế hoạch đổi analyzer cho index đang phục vụ người dùng: tạo index mới, đợi `ONLINE`, chạy bộ kiểm thử, đổi luồng đọc, quan sát chất lượng/hiệu năng và xóa index cũ khi an toàn.

Nếu đã hoàn thành, hãy tự trả lời ba câu hỏi trước mỗi tính năng tìm kiếm trong Neo4j: **Analyzer có xử lý văn bản đúng ngôn ngữ và cách người dùng tìm kiếm không? Score có được dùng như tín hiệu xếp hạng thay vì giá trị tuyệt đối không? Những giới hạn về quyền truy cập, cập nhật chỉ mục và tài nguyên đã được kiểm soát chưa?** Khi các câu hỏi này rõ ràng, full-text search trở thành một công cụ hữu ích để dẫn người dùng từ văn bản vào đúng phần dữ liệu liên kết của property graph.
