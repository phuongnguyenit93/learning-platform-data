# Inverted index và cơ chế tìm kiếm văn bản

Elasticsearch được thiết kế để tìm kiếm trên lượng lớn dữ liệu văn bản. Khi một ứng dụng gửi truy vấn như `"spring data"`, Elasticsearch không cần mở lần lượt từng tài liệu rồi so sánh toàn bộ nội dung. Thay vào đó, nó tra cứu một cấu trúc dữ liệu đã được chuẩn bị trong quá trình lập chỉ mục: **inverted index** (chỉ mục đảo).

Inverted index ánh xạ một thuật ngữ về những tài liệu có chứa thuật ngữ đó. Cấu trúc này giúp Elasticsearch nhanh chóng xác định tập tài liệu ứng viên, kết hợp kết quả của nhiều thuật ngữ và xếp hạng chúng theo mức độ phù hợp. Để hiểu cơ chế tìm kiếm văn bản trong Spring Data Elasticsearch, cần nắm được cách văn bản được phân tích khi ghi dữ liệu, cách inverted index lưu thông tin, cách truy vấn được phân tích và cách mapping quyết định hành vi tìm kiếm.

## 1. Vì sao cần inverted index?

Giả sử hệ thống có ba tài liệu:

| ID | Nội dung |
|---|---|
| D1 | Spring Data Elasticsearch |
| D2 | Elasticsearch full text search |
| D3 | Spring repository |

Nếu lưu tài liệu theo dạng thông thường, một cách tìm kiếm đơn giản là đọc từng tài liệu và kiểm tra xem nội dung có chứa từ cần tìm hay không. Cách này có thể phải quét rất nhiều nội dung mỗi khi có truy vấn. Khi số tài liệu và độ dài văn bản tăng lên, chi phí đọc và so sánh cũng tăng.

Inverted index đảo chiều cách tổ chức thông tin. Thay vì chỉ biết mỗi tài liệu chứa những từ nào, chỉ mục còn cho phép tra từ khóa để tìm ra tài liệu liên quan:

| Thuật ngữ | Danh sách tài liệu chứa thuật ngữ |
|---|---|
| `data` | D1 |
| `elasticsearch` | D1, D2 |
| `full` | D2 |
| `repository` | D3 |
| `spring` | D1, D3 |
| `text` | D2 |
| `search` | D2 |

Ví dụ, khi tìm `elasticsearch`, hệ thống có thể tra mục từ `elasticsearch` và nhận được D1 cùng D2. Khi tìm đồng thời `spring` và `elasticsearch`, hệ thống kết hợp các danh sách tài liệu tương ứng để xác định tài liệu thỏa điều kiện.

Đây là ví dụ giản lược. Trong Elasticsearch thực tế, việc phân tích văn bản có thể biến đổi nội dung thành nhiều token, còn postings list lưu thêm thông tin như tần suất xuất hiện và vị trí của token.

## 2. Từ văn bản đến inverted index

Quá trình biến văn bản thành dữ liệu có thể tìm kiếm được gọi là **analysis**. Một analyzer nhận văn bản đầu vào và tạo ra chuỗi token. Các token sau đó được dùng để xây dựng inverted index cho field tương ứng.

Một analyzer thường gồm ba thành phần, theo thứ tự:

1. **Character filters**: biến đổi văn bản trước khi tách token, chẳng hạn loại bỏ thẻ HTML hoặc thay thế một mẫu ký tự.
2. **Tokenizer**: chia văn bản thành các token theo quy tắc nhất định, chẳng hạn tách theo ranh giới từ.
3. **Token filters**: biến đổi, loại bỏ hoặc bổ sung token, chẳng hạn chuyển chữ thường, bỏ stop words, stemming hoặc áp dụng synonym.

Sơ đồ tổng quát:

```text
Văn bản gốc
    |
    v
Character filters
    |
    v
Tokenizer
    |
    v
Token filters
    |
    v
Chuỗi token
    |
    v
Inverted index
```

### 2.1. Character filters

Character filter xử lý chuỗi ký tự trước khi tokenizer chia văn bản. Một số tình huống thường gặp:

- Loại bỏ hoặc xử lý HTML markup để nội dung như `<p>Spring</p>` không bị xem là văn bản cần tìm.
- Chuẩn hóa một số ký tự hoặc thay thế mẫu ký tự theo quy tắc.
- Chuyển các dạng biểu diễn đặc biệt thành văn bản mà tokenizer có thể xử lý nhất quán.

Character filter không trực tiếp tạo danh sách từ. Nó chuẩn bị chuỗi đầu vào cho tokenizer.

### 2.2. Tokenizer

Tokenizer xác định ranh giới token. Ví dụ, tokenizer có thể chia câu `Spring Data Elasticsearch` thành ba token:

```text
Spring | Data | Elasticsearch
```

Tokenization phụ thuộc tokenizer được cấu hình. Một tokenizer dựa trên ranh giới từ có thể xử lý dấu câu và khoảng trắng theo quy tắc của nó; tokenizer chuyên biệt có thể xử lý cấu trúc văn bản khác.

Với tiếng Việt, cần chú ý rằng khoảng trắng thường phân tách âm tiết, trong khi một từ có nghĩa có thể gồm nhiều âm tiết. Analyzer tiêu chuẩn có thể tách `cơ chế tìm kiếm` thành các token gần với `cơ`, `chế`, `tìm`, `kiếm`; nó không mặc nhiên thực hiện phân đoạn từ tiếng Việt theo từ điển hoặc hiểu mọi cụm nhiều âm tiết là một đơn vị từ vựng. Nếu ứng dụng cần chất lượng tìm kiếm tiếng Việt cao, cần đánh giá analyzer phù hợp, plugin hoặc pipeline xử lý ngôn ngữ riêng dựa trên dữ liệu thực tế.

### 2.3. Token filters

Token filter nhận các token do tokenizer tạo ra rồi biến đổi chúng. Một số filter phổ biến:

| Filter | Tác dụng | Ví dụ minh họa |
|---|---|---|
| `lowercase` | Chuyển token thành chữ thường | `Spring` → `spring` |
| `stop` | Loại bỏ các từ dừng theo danh sách cấu hình | Một số từ phổ biến có thể bị bỏ qua |
| `asciifolding` | Chuyển một số ký tự có dấu về dạng ASCII tương ứng | `café` → `cafe` |
| `stemmer` | Đưa từ về dạng gốc gần đúng theo thuật toán stemming | `running` → `run` trong cấu hình phù hợp |
| `synonym` | Mở rộng hoặc thay thế token theo từ điển đồng nghĩa | `car` có thể liên hệ với `automobile` |

Các ví dụ trên chỉ mô tả mục đích của filter; kết quả thực tế phụ thuộc ngôn ngữ, cấu hình và thứ tự filter. Không nên bật stemming, stop words hay synonym theo mặc định cho mọi field. Những biến đổi này có thể làm thay đổi ý nghĩa, độ chính xác hoặc khả năng khớp cụm từ của truy vấn.

### 2.4. Analyzer khi lập chỉ mục và khi tìm kiếm

Elasticsearch có thể dùng analyzer ở hai thời điểm:

- **Index-time analyzer** phân tích giá trị field khi tài liệu được lập chỉ mục và tạo token để lưu vào inverted index.
- **Search-time analyzer** phân tích chuỗi truy vấn trước khi tra inverted index.

Thông thường hai analyzer nên tương thích để token trong truy vấn có thể khớp với token đã được lập chỉ mục. Mapping cho phép khai báo `analyzer` và, khi cần, `search_analyzer` riêng. Ví dụ, hệ thống có thể chuẩn hóa văn bản mạnh hơn khi lập chỉ mục nhưng dùng quy tắc nhẹ hơn khi tìm kiếm. Cấu hình khác nhau cần được thiết kế có chủ đích; nếu token đầu ra không tương thích, truy vấn có thể bỏ sót kết quả.

## 3. Cấu trúc inverted index

Inverted index thường được mô tả qua hai thành phần chính:

- **Term dictionary**: từ điển các thuật ngữ đã được lập chỉ mục trong một field.
- **Postings list**: danh sách các tài liệu chứa một thuật ngữ, kèm metadata phục vụ truy vấn.

Ví dụ, sau khi dùng analyzer chuyển chữ thường và tách từ, tài liệu D1 có thể tạo ra các token `spring`, `data`, `elasticsearch`. Term dictionary có mục `spring`; postings list của mục đó cho biết D1 chứa token này. Tương tự, mục `elasticsearch` có postings list gồm D1 và D2.

Postings list thực tế có thể lưu nhiều thông tin hơn ID tài liệu:

- **Document ID** nội bộ: xác định tài liệu trong segment của Lucene. ID này không phải giá trị `_id` mà ứng dụng đặt cho entity.
- **Term frequency**: số lần thuật ngữ xuất hiện trong một tài liệu. Thông tin này hỗ trợ tính điểm liên quan.
- **Positions**: vị trí token trong field. Thông tin này cần thiết cho truy vấn cụm từ và một số truy vấn lân cận.
- **Offsets**: vị trí bắt đầu và kết thúc của token trong chuỗi gốc đã phân tích. Thông tin này có thể hỗ trợ highlighting.

Không phải mọi field đều cần lưu mọi loại metadata. Cấu hình `index_options` của field ảnh hưởng đến mức thông tin được lưu trong chỉ mục. Field `text` thường lưu positions để hỗ trợ tìm cụm từ; các kiểu field khác có thể dùng mức thông tin đơn giản hơn.

### 3.1. Ví dụ về vị trí token

Giả sử analyzer tạo token như sau:

```text
D1: spring(0) data(1) elasticsearch(2)
D2: elasticsearch(0) full(1) text(2) search(3)
D3: spring(0) repository(1)
```

Postings list minh họa cho `spring` có thể biểu diễn như sau:

```text
spring ->
  D1: frequency = 1, positions = [0]
  D3: frequency = 1, positions = [0]
```

Với `elasticsearch`:

```text
elasticsearch ->
  D1: frequency = 1, positions = [2]
  D2: frequency = 1, positions = [0]
```

Positions giúp phân biệt việc hai token chỉ cùng xuất hiện trong một tài liệu với việc chúng xuất hiện cạnh nhau theo đúng thứ tự. Ví dụ, truy vấn cụm từ `spring data` cần kiểm tra vị trí của `spring` và `data`, chứ không chỉ kiểm tra xem cả hai token có nằm trong cùng tài liệu hay không.

### 3.2. Inverted index nằm ở đâu trong Elasticsearch?

Elasticsearch sử dụng Apache Lucene làm engine lập chỉ mục và tìm kiếm ở mỗi shard. Lucene tổ chức dữ liệu đã lập chỉ mục thành các **segment**. Segment là đơn vị chỉ mục bất biến sau khi được ghi; các lần ghi tiếp theo tạo dữ liệu mới và quá trình merge có thể gộp những segment nhỏ thành segment lớn hơn.

Ở mức khái niệm, mỗi segment có term dictionary và postings list riêng. Khi tìm kiếm, Lucene tra cứu các segment liên quan rồi kết hợp kết quả. Cơ chế segment và merge giúp Lucene quản lý việc ghi mới, đọc đồng thời và tối ưu kích thước chỉ mục.

Một số cấu trúc khác có vai trò riêng, không nên nhầm với inverted index:

| Cấu trúc | Mục đích chính |
|---|---|
| `_source` | Lưu nội dung JSON gốc để trả lại tài liệu hoặc phục vụ thao tác khác |
| Inverted index | Tìm tài liệu theo token trong field |
| `doc_values` | Lưu dữ liệu theo hướng cột, thường dùng cho sort, aggregation và một số truy vấn/script |
| Stored fields | Lưu các field được yêu cầu lưu riêng để đọc lại |

Ví dụ, một field `text` có thể được tìm bằng inverted index. Nếu cần sắp xếp hoặc aggregation theo giá trị nguyên bản, ứng dụng thường tạo thêm một field `keyword` hoặc cấu hình cấu trúc phù hợp. `doc_values` không thay thế inverted index cho tìm kiếm toàn văn.

## 4. Cơ chế thực thi một truy vấn văn bản

Khi nhận một truy vấn, Elasticsearch thực hiện các bước khái quát sau:

1. Xác định field và loại query theo Query DSL.
2. Phân tích chuỗi truy vấn bằng search analyzer của field (nếu query hỗ trợ phân tích văn bản).
3. Tra term dictionary để tìm các thuật ngữ tương ứng.
4. Đọc postings list để lấy những tài liệu có token phù hợp.
5. Kết hợp các tập tài liệu theo điều kiện của query, chẳng hạn AND, OR hoặc cụm từ.
6. Tính điểm liên quan nếu query có tính điểm, sau đó chọn các kết quả phù hợp nhất.
7. Với chỉ mục phân tán, các shard xử lý phần dữ liệu của mình; Elasticsearch tổng hợp các kết quả để trả về cho client.

Sơ đồ đơn giản:

```text
Chuỗi truy vấn
      |
      v
Search analyzer
      |
      v
Các token truy vấn
      |
      v
Term dictionary
      |
      v
Postings lists
      |
      v
Kết hợp tài liệu phù hợp
      |
      v
Tính điểm và xếp hạng
      |
      v
Kết quả tìm kiếm
```

### 4.1. Match query

`match` là query thường dùng cho tìm kiếm toàn văn. Nó phân tích chuỗi truy vấn theo analyzer của field rồi tìm các token tương ứng.

Ví dụ tìm bài viết có nội dung liên quan đến `spring data`:

```http
GET articles/_search
{
  "query": {
    "match": {
      "title": "spring data"
    }
  }
}
```

Theo mặc định, `match` kết hợp các token theo toán tử OR. Vì vậy, tài liệu khớp một trong các token vẫn có thể được trả về. Có thể yêu cầu tất cả token phải khớp bằng `operator: "and"`:

```http
GET articles/_search
{
  "query": {
    "match": {
      "title": {
        "query": "spring data",
        "operator": "and"
      }
    }
  }
}
```

Khi cần quy tắc linh hoạt hơn, `minimum_should_match` cho phép quy định số lượng hoặc tỷ lệ token tối thiểu phải khớp.

### 4.2. Term query

`term` tìm một giá trị term chính xác trong inverted index và không tự phân tích chuỗi đầu vào như `match`. Vì thế, nó thường phù hợp với field `keyword`, mã định danh, trạng thái hoặc giá trị đã được chuẩn hóa trước.

```http
GET articles/_search
{
  "query": {
    "term": {
      "category.keyword": "tutorial"
    }
  }
}
```

Nếu field `category` là `text`, giá trị được lập chỉ mục có thể đã bị tách thành nhiều token và chuyển chữ thường. Gửi `term` với chuỗi nguyên bản như `Spring Data` có thể không khớp token nào. Đây là lý do cần chọn đúng query theo kiểu field và analyzer.

### 4.3. Match phrase query

`match_phrase` tìm các token theo thứ tự và quan hệ vị trí phù hợp với cụm từ đã phân tích. Query này sử dụng thông tin positions trong inverted index.

```http
GET articles/_search
{
  "query": {
    "match_phrase": {
      "title": "spring data"
    }
  }
}
```

Nếu một tài liệu có cả `spring` và `data` nhưng hai token cách xa nhau hoặc xuất hiện sai thứ tự, tài liệu đó có thể không khớp cụm từ. `slop` có thể nới lỏng khoảng cách cho một số trường hợp, nhưng cần cân nhắc để tránh trả về những kết quả không còn sát với cụm từ người dùng nhập.

### 4.4. Kết hợp nhiều điều kiện

Bool query cho phép kết hợp các query con:

- `must`: điều kiện phải khớp và có thể đóng góp vào điểm liên quan.
- `should`: điều kiện nên khớp; tác động bắt buộc hay tùy chọn phụ thuộc các mệnh đề khác và `minimum_should_match`.
- `filter`: điều kiện phải thỏa mãn nhưng không tính điểm liên quan; phù hợp với bộ lọc như trạng thái, tenant hoặc ngày tháng.
- `must_not`: loại bỏ tài liệu khớp điều kiện.

Ví dụ tìm bài viết có cụm `spring data` trong tiêu đề và chỉ lấy bài đang xuất bản:

```http
GET articles/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match_phrase": {
            "title": "spring data"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        }
      ]
    }
  }
}
```

## 5. Elasticsearch xếp hạng kết quả như thế nào?

Tìm được tài liệu chứa token mới chỉ là một phần của tìm kiếm. Với các query có tính điểm, Elasticsearch còn cần ước lượng tài liệu nào liên quan hơn để sắp xếp kết quả. Lucene mặc định sử dụng **BM25** làm similarity phổ biến cho các field văn bản.

BM25 cân nhắc các yếu tố chính:

- **Term frequency (TF)**: một thuật ngữ xuất hiện nhiều lần trong tài liệu có thể làm tài liệu liên quan hơn, nhưng lợi ích tăng thêm sẽ giảm dần.
- **Inverse document frequency (IDF)**: thuật ngữ hiếm trong toàn bộ tập tài liệu thường có giá trị phân biệt cao hơn thuật ngữ xuất hiện ở hầu hết tài liệu.
- **Field length normalization**: độ dài field ảnh hưởng đến điểm; việc một từ xuất hiện trong field ngắn có thể được đánh giá khác với cùng tần suất trong field rất dài.

Ví dụ, với truy vấn `elasticsearch`, một tài liệu có thuật ngữ này nhiều lần có thể nhận điểm cao hơn. Tuy nhiên, nếu thuật ngữ xuất hiện trong gần như mọi tài liệu thì khả năng phân biệt của nó thấp. Một tài liệu ngắn có thể được đánh giá khác tài liệu dài có cùng số lần xuất hiện.

Điểm BM25 là điểm phù hợp thống kê dựa trên nội dung đã được phân tích, không phải hiểu biết ngữ nghĩa như con người. Hai câu có ý nghĩa gần nhau nhưng không có token tương thích có thể không được tìm thấy bằng truy vấn toàn văn thông thường. Khi cần tìm kiếm theo ý nghĩa, có thể phải kết hợp synonym, query expansion hoặc vector search tùy yêu cầu sản phẩm.

## 6. Mapping quyết định cách một field được tìm kiếm

Mapping mô tả kiểu dữ liệu và cách Elasticsearch lập chỉ mục field. Đối với tìm kiếm văn bản, hai kiểu quan trọng nhất là `text` và `keyword`.

| Kiểu field | Cách lập chỉ mục | Trường hợp sử dụng |
|---|---|---|
| `text` | Phân tích chuỗi thành token bằng analyzer | Tiêu đề, mô tả, nội dung bài viết cần tìm toàn văn |
| `keyword` | Xem toàn bộ giá trị như một term, có thể áp dụng normalizer | Trạng thái, mã, tên nhóm, danh mục cần so khớp chính xác hoặc aggregation |

Ví dụ mapping:

```http
PUT articles
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "status": {
        "type": "keyword"
      },
      "publishedAt": {
        "type": "date"
      }
    }
  }
}
```

Trong ví dụ này, `title` có thể được tìm toàn văn qua analyzer. Field con `title.keyword` lưu thêm giá trị dạng keyword để dùng cho các thao tác cần giá trị nguyên bản, chẳng hạn sort hoặc aggregation. Đây là **multi-fields**: một giá trị trong `_source` được lập chỉ mục theo nhiều cách ở các field khác nhau.

Không nên mặc định mọi chuỗi đều là `text`. Ví dụ `status = PUBLISHED` thường cần khớp chính xác, nên `keyword` phù hợp hơn. Ngược lại, nội dung mô tả dài thường cần `text`.

### 6.1. Phân biệt analyzer và normalizer

Analyzer xử lý văn bản thành một hoặc nhiều token và thường được dùng cho field `text`. Normalizer dành cho field `keyword`; nó chuẩn hóa toàn bộ giá trị thành một token duy nhất. Ví dụ, một normalizer có filter `lowercase` có thể giúp giá trị keyword được so khớp không phân biệt chữ hoa chữ thường, trong khi vẫn giữ nguyên tính chất một giá trị.

### 6.2. Thay đổi analyzer và reindex

Analyzer dùng khi lập chỉ mục quyết định token đã lưu trong inverted index. Nếu muốn thay đổi cách tách từ hoặc chuẩn hóa token, chỉ sửa cấu hình ứng dụng là chưa đủ để làm thay đổi những token đã được tạo trước đó. Thông thường cần tạo index mới với mapping/settings mong muốn, chạy `_reindex` từ index cũ sang index mới rồi chuyển alias hoặc cập nhật ứng dụng theo quy trình triển khai phù hợp.

Không thể tùy ý đổi kiểu field hoặc index-time analyzer của một field đã được tạo và lập chỉ mục trong index hiện hữu. Vì vậy cần xác định mapping và analyzer trước khi đưa dữ liệu vào môi trường vận hành.

## 7. Khai báo mapping bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp annotation để mô tả index và field ngay trên entity. Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "articles")
public class Article {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String title;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
```

Các annotation thể hiện ý định mapping:

- `@Document` khai báo index gắn với entity.
- `@Id` đánh dấu trường định danh của entity.
- `@Field(type = FieldType.Text)` khai báo field cần phân tích văn bản.
- `analyzer` chỉ định analyzer dùng khi lập chỉ mục.
- `@MultiField` khai báo nhiều cách lập chỉ mục cho cùng một thuộc tính.
- `@InnerField` khai báo field phụ, trong ví dụ là `category.keyword` kiểu `keyword`.

Tên analyzer khai báo trong annotation phải tồn tại trong settings của index. Nếu dùng analyzer tự định nghĩa, cần cấu hình nó trong index settings trước khi dữ liệu được lập chỉ mục. Có thể quản lý settings bằng file cấu hình của index hoặc bằng quy trình tạo index riêng của ứng dụng; chi tiết API và annotation có thể thay đổi theo phiên bản Spring Data Elasticsearch đang sử dụng.

## 8. Thực hiện tìm kiếm từ repository

Khi đã có mapping, repository có thể khai báo truy vấn dựa trên Elasticsearch Query DSL bằng annotation `@Query`:

```java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.annotations.Query;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    @Query("{\"match\": {\"title\": {\"query\": \"?0\"}}}")
    List<Article> searchTitle(String text);

    @Query("{\"match_phrase\": {\"title\": \"?0\"}}")
    List<Article> searchTitlePhrase(String phrase);
}
```

`searchTitle` sử dụng `match`, vì vậy chuỗi truyền vào được phân tích theo analyzer phù hợp với field `title`. `searchTitlePhrase` sử dụng `match_phrase` để tìm cụm từ theo thứ tự và vị trí token.

Một repository method dẫn xuất từ tên phương thức có thể tiện cho các điều kiện đơn giản, nhưng không nên suy luận rằng mọi method `findBy...` đều tạo ra cùng loại truy vấn toàn văn. Khi cần kiểm soát rõ semantics của `match`, `term`, `match_phrase`, bool query hoặc filter, hãy khai báo query tường minh hoặc dùng API truy vấn của `ElasticsearchOperations`/`NativeQuery` phù hợp với phiên bản thư viện.

## 9. Thử nghiệm analyzer và truy vấn

Khi kết quả tìm kiếm không như mong đợi, nên kiểm tra token thực tế trước khi thay đổi query. Elasticsearch cung cấp Analyze API:

```http
POST articles/_analyze
{
  "field": "title",
  "text": "Spring Data Elasticsearch"
}
```

API này cho biết analyzer của field tạo ra token nào. Có thể dùng nó để xác minh việc chuyển chữ thường, tách từ, stop words hoặc synonym.

Tiếp theo, kiểm tra mapping:

```http
GET articles/_mapping
```

Và kiểm tra kết quả tìm kiếm:

```http
GET articles/_search
{
  "query": {
    "match": {
      "title": "Spring Data"
    }
  }
}
```

Khi kiểm tra, cần xác định rõ:

- Field đang được khai báo là `text` hay `keyword`?
- Analyzer nào được dùng lúc lập chỉ mục và lúc tìm kiếm?
- Query có phân tích đầu vào hay yêu cầu term chính xác?
- Query cần khớp một token, mọi token hay cả cụm từ theo thứ tự?
- Token cần tìm có thực sự tồn tại trong index không?
- Dữ liệu mới đã được refresh để có thể tìm thấy chưa?

Elasticsearch là hệ thống tìm kiếm gần thời gian thực. Sau khi ghi tài liệu, tài liệu thường chỉ xuất hiện trong kết quả tìm kiếm sau lần refresh tiếp theo. Vì vậy, việc vừa lưu entity xong rồi tìm ngay mà chưa thấy kết quả không nhất thiết là lỗi mapping hoặc inverted index. Có thể dùng refresh phù hợp trong kiểm thử; trong vận hành, cần cân nhắc chi phí khi yêu cầu refresh quá thường xuyên.

## 10. Những lỗi thiết kế thường gặp

### Dùng `term` cho field `text`

`term` không phân tích chuỗi truy vấn như `match`. Nếu field đã được lowercase hoặc tách thành nhiều token, term nguyên bản có thể không tồn tại trong index. Hãy dùng `match` cho tìm kiếm toàn văn và `term` cho giá trị chính xác đã được lập chỉ mục theo cách tương ứng.

### Dùng `match` cho field `keyword` với kỳ vọng tìm từng từ

Field `keyword` giữ nguyên giá trị thành một term. `match` trên field này không biến nó thành field toàn văn theo cách một field `text` được phân tích. Nếu cần vừa tìm toàn văn vừa so khớp chính xác, hãy cân nhắc multi-fields.

### Không kiểm tra analyzer

Hai chuỗi nhìn giống nhau với người dùng vẫn có thể tạo ra token khác nhau do chữ hoa/thường, dấu, dấu câu, stop words, synonym hoặc quy tắc tách từ. Dùng Analyze API để xem token đầu ra thay vì đoán.

### Chọn analyzer không phù hợp với tiếng Việt

Việc tách theo khoảng trắng có thể chưa đủ cho truy vấn theo cụm từ hoặc từ ghép tiếng Việt. Chất lượng tìm kiếm phụ thuộc dữ liệu, cách người dùng nhập truy vấn và yêu cầu nghiệp vụ. Cần thử với tập truy vấn đại diện trước khi chọn analyzer hoặc plugin.

### Mong đợi analyzer mới tự áp dụng lên dữ liệu cũ

Token đã lập chỉ mục không tự thay đổi khi mã Java được cập nhật. Khi thay đổi quy tắc index-time analysis, cần lập kế hoạch tạo index và reindex dữ liệu.

### Nhầm inverted index với dữ liệu phục vụ sort và aggregation

Inverted index phục vụ tra cứu term. Sort và aggregation trên field chuỗi thường cần `keyword` cùng `doc_values`. Thiết kế mapping nên xét cả cách tìm kiếm lẫn cách đọc và tổng hợp dữ liệu.

## 11. Cách lựa chọn query theo nhu cầu

| Nhu cầu | Query/field thường dùng | Lưu ý |
|---|---|---|
| Tìm nội dung có các từ người dùng nhập | `match` trên `text` | Chú ý toán tử OR/AND và analyzer |
| Tìm đúng cụm từ theo thứ tự | `match_phrase` trên `text` | Cần positions phù hợp |
| Lọc trạng thái hoặc mã chính xác | `term` trên `keyword` | Giá trị phải khớp term đã lập chỉ mục |
| Kết hợp tìm văn bản và lọc metadata | `bool` với `must` và `filter` | Điều kiện filter không đóng góp điểm relevance |
| Tìm trên nhiều field văn bản | `multi_match` | Cần chọn field và cách kết hợp điểm phù hợp |
| Sắp xếp hoặc aggregation theo chuỗi | `keyword` | Thường dùng `doc_values` |

## 12. Tổng kết

Inverted index là nền tảng của tìm kiếm toàn văn trong Elasticsearch. Khi ghi dữ liệu, analyzer chuyển văn bản thành token; term dictionary ánh xạ thuật ngữ đến postings list; postings list cho biết tài liệu và metadata liên quan. Khi tìm kiếm, analyzer xử lý chuỗi truy vấn, Elasticsearch tra các term, kết hợp danh sách tài liệu và tính điểm để xếp hạng kết quả.

Trong Spring Data Elasticsearch, mapping của entity quyết định kiểu field và analyzer mà Elasticsearch sử dụng. `text` phù hợp với tìm kiếm toàn văn, `keyword` phù hợp với giá trị cần so khớp chính xác, còn multi-fields cho phép một thuộc tính hỗ trợ cả hai nhu cầu. Chọn đúng mapping, analyzer và query giúp kết quả tìm kiếm nhất quán, dễ dự đoán và phù hợp với dữ liệu thực tế.
