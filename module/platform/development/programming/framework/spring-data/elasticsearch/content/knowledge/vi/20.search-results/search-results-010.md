# Giữ metadata cần thiết khi thiết kế phản hồi tìm kiếm

Một phản hồi tìm kiếm tốt cần giữ lại đủ thông tin để giao diện hiểu kết quả, hiển thị mức độ liên quan, phân trang đúng và tiếp tục truy vấn ở trang sau. Trong Spring Data Elasticsearch, dữ liệu này không chỉ nằm trong object entity. Mỗi kết quả tìm kiếm còn có metadata riêng như ID, score, sort values, highlight và các thông tin bổ sung từ Elasticsearch. Toàn bộ response cũng có metadata chung như tổng số hit, quan hệ của con số tổng, aggregations và suggest results.

Nếu service chuyển `SearchHits<T>` thành `List<T>` quá sớm, nhiều metadata có thể bị mất. API khi đó chỉ còn các field trong `_source` và không thể cung cấp một số chức năng mà giao diện cần. Ngược lại, trả nguyên toàn bộ response Elasticsearch cho client có thể làm lộ thông tin nội bộ, khiến hợp đồng API phụ thuộc thư viện và trả nhiều dữ liệu không cần thiết.

Thiết kế tốt là xác định metadata nào phục vụ một use case cụ thể, giữ metadata đó trong tầng service, rồi ánh xạ có chủ đích sang response DTO ổn định.

## 1. Phân biệt document content và search metadata

### 1.1. Document content đến từ _source

Một document Elasticsearch thường có nội dung được lưu trong `_source`. Ví dụ:

~~~json
{
  "id": "P1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORY",
  "price": 49.90,
  "available": true
}
~~~

Spring Data Elasticsearch ánh xạ phần source này thành entity Java:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;
}
~~~

Các property như name, category, price và available là dữ liệu nghiệp vụ. Chúng mô tả sản phẩm và có thể được dùng ở nhiều màn hình, không chỉ kết quả tìm kiếm.

### 1.2. Search metadata mô tả cách document xuất hiện trong kết quả

Khi Elasticsearch trả một hit, response có thể chứa các thông tin ngoài source:

~~~json
{
  "_index": "products",
  "_id": "P1001",
  "_score": 2.73,
  "_source": {
    "id": "P1001",
    "name": "Wireless Keyboard",
    "category": "ACCESSORY",
    "price": 49.90,
    "available": true
  },
  "sort": [2.73, "P1001"],
  "highlight": {
    "name": [
      "Wireless <em>Keyboard</em>"
    ]
  }
}
~~~

Trong ví dụ:

- `_index` cho biết index trả về hit.
- `_id` là ID của document trong Elasticsearch.
- `_score` là score do query tạo ra.
- `_source` là nội dung document.
- `sort` chứa sort values dùng để sắp xếp và có thể dùng làm cursor.
- `highlight` chứa các fragment được đánh dấu theo query.

Không phải response nào cũng có tất cả trường này. Score, sort values, highlight, explanation hoặc inner hits chỉ có khi query/request và mapping hỗ trợ hoặc yêu cầu chúng.

### 1.3. Metadata của từng hit và metadata của cả search response

Có hai cấp thông tin:

| Cấp | Ví dụ | Dùng để |
|---|---|---|
| Một hit | ID, score, highlight, sort values, inner hits | Hiển thị và xử lý từng kết quả |
| Toàn bộ search | Total hits, total-hit relation, aggregations, suggest, execution metadata | Phân trang, thống kê và điều khiển giao diện |

Cần giữ đúng cấp khi thiết kế DTO. Ví dụ score thuộc về từng sản phẩm, còn tổng số kết quả thuộc về cả trang tìm kiếm.

## 2. SearchHit và SearchHits trong Spring Data Elasticsearch

### 2.1. SearchHit<T> đại diện một kết quả

Spring Data Elasticsearch dùng `SearchHit<T>` để bọc entity content và metadata của một hit.

Ví dụ duyệt kết quả:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();

    System.out.println("ID: " + hit.getId());
    System.out.println("Score: " + hit.getScore());
    System.out.println("Name: " + product.getName());
}
~~~

`getContent()` trả entity được ánh xạ từ source. Các getter khác cung cấp metadata mà Elasticsearch trả về và Spring Data giữ lại.

Các thông tin thường cần xem xét:

- ID và index của hit.
- Score.
- Sort values.
- Highlight fields.
- Explanation nếu được yêu cầu.
- Matched query names nếu query đặt tên các clause.
- Inner hits nếu truy vấn nested hoặc parent/child yêu cầu.
- Routing hoặc thông tin bổ sung nếu API/phiên bản cung cấp.

Tên và mức độ hỗ trợ getter cụ thể phụ thuộc phiên bản Spring Data Elasticsearch. Hãy kiểm tra API của dependency đang dùng thay vì giả định mọi phiên bản có cùng tập metadata.

### 2.2. SearchHits<T> đại diện toàn bộ response

`SearchHits<T>` bao bọc danh sách hit và metadata chung:

~~~java
long totalHits = searchHits.getTotalHits();
float maxScore = searchHits.getMaxScore();

List<SearchHit<ProductDocument>> hits =
    searchHits.getSearchHits();
~~~

Thông tin thường có ý nghĩa:

- `getSearchHits()` trả danh sách hit của response hiện tại.
- `getTotalHits()` trả tổng số hit được báo cáo theo query và cấu hình total-hit tracking.
- `getMaxScore()` trả score cao nhất trong các hit được trả về khi score có ý nghĩa.
- Aggregations và suggest có thể được giữ trong response nếu query yêu cầu.
- Một số phiên bản cung cấp thêm total-hit relation, execution duration hoặc PIT metadata.

Danh sách hit là phần dữ liệu của trang hiện tại. Total hits là số lượng kết quả phù hợp được báo cáo; hai con số này không nhất thiết bằng nhau.

### 2.3. Không chuyển sang List<T> quá sớm

Đoạn code sau đơn giản nhưng bỏ phần metadata của từng hit:

~~~java
List<ProductDocument> products = searchHits.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

Sau phép chuyển đổi này, danh sách chỉ còn entity content. Service không còn score, highlight hoặc sort values nếu không giữ chúng ở một cấu trúc khác.

Nếu API chỉ hiển thị dữ liệu sản phẩm và không cần metadata tìm kiếm, chuyển thành danh sách entity có thể hoàn toàn phù hợp. Nhưng nếu giao diện cần đánh dấu từ khóa, giải thích độ liên quan hoặc tạo cursor trang tiếp theo, hãy giữ `SearchHit` đến khi hoàn tất việc tạo response.

### 2.4. SearchPage kết hợp hit với thông tin phân trang

Spring Data có `SearchPage<T>` để kết hợp nội dung SearchHit với metadata phân trang:

~~~java
SearchPage<ProductDocument> searchPage =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

Tùy cách sử dụng, `SearchPage` cho phép truy cập page metadata như page number, size, total elements và content vẫn là các SearchHit. Đây là lựa chọn hữu ích khi ứng dụng muốn giữ metadata hit trong khi cung cấp cấu trúc phân trang quen thuộc.

Nếu chỉ cần page of entity, có thể chuyển content sau khi đã quyết định metadata nào cần giữ. Đừng để thao tác chuyển đổi làm mất dữ liệu cần thiết cho response.

## 3. Chọn metadata theo chức năng giao diện

Không phải API nào cũng cần toàn bộ metadata. Trước khi thiết kế DTO, hãy bắt đầu từ hành vi người dùng.

| Chức năng | Metadata cần cân nhắc |
|---|---|
| Danh sách kết quả đơn giản | ID, content, page/size |
| Sắp xếp theo relevance | Score hoặc thứ tự hit đã được xếp hạng |
| Hiển thị đoạn trích có từ khóa | Highlight fragments |
| Phân trang offset | Page number, size, total hits nếu cần |
| Cuộn kết quả sâu | Sort values và cursor |
| Giải thích vì sao một kết quả đứng đầu | Explanation trong chế độ debug |
| Kết quả từ nested document | Inner hits |
| Bộ lọc tổng hợp theo nhóm | Aggregations |
| Gợi ý tìm kiếm | Suggest response |
| Theo dõi query diagnostics | Execution duration và trạng thái timeout nếu được expose |

Metadata cần thiết phụ thuộc hợp đồng API. Ví dụ, giao diện thông thường không cần nhận raw explanation hoặc tên index nội bộ. Một công cụ quản trị tìm kiếm có thể cần những thông tin đó trong endpoint riêng có kiểm soát quyền.

## 4. Score và thứ tự relevance

### 4.1. Score là tín hiệu xếp hạng

`_score` là giá trị Elasticsearch dùng để biểu diễn mức độ phù hợp của document với query. Với full-text search, score phụ thuộc query, analyzer, term statistics và các yếu tố scoring khác.

Một hit có score 4.2 không có nghĩa nó đúng 84% hoặc có xác suất đúng 4.2. Score chỉ có ý nghĩa tương đối trong bối cảnh query và chiến lược ranking đang dùng.

Nếu giao diện cần hiển thị “độ liên quan”, thường nên dùng thứ tự kết quả hoặc nhãn nghiệp vụ đã được chuẩn hóa thay vì hiển thị số score thô cho người dùng cuối.

### 4.2. Giữ score trong DTO khi thực sự cần

Ví dụ DTO:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    Float score
) {
}
~~~

Ánh xạ từ SearchHit:

~~~java
ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
    ProductDocument product = hit.getContent();

    return new ProductSearchItem(
        hit.getId(),
        product.getName(),
        product.getPrice(),
        hit.getScore()
    );
}
~~~

Dùng kiểu nullable như `Float` nếu score có thể không được cung cấp hoặc không có ý nghĩa trong query cụ thể. Nếu API đảm bảo mọi query đều có scoring, có thể chọn kiểu phù hợp và kiểm tra điều kiện đó ở service.

### 4.3. Khi sort theo field, không mặc định score là tín hiệu chính

Nếu request sort theo giá, ngày hoặc tên, thứ tự hit có thể được quyết định bởi field sort thay vì relevance. Trong trường hợp này score có thể không được theo dõi hoặc không có ý nghĩa như thứ tự xếp hạng chính.

Nếu UI hiển thị score, hãy xác định rõ query có yêu cầu score và sort đang dùng. Không dùng score để tái tạo thứ tự kết quả khi Elasticsearch đã sắp xếp theo một field khác.

### 4.4. Max score thuộc response chung

`getMaxScore()` là metadata toàn search response. Nó không phải score của một hit cụ thể. Score từng document nằm trên từng SearchHit.

Thông thường API người dùng cuối không cần trả max score. Nó hữu ích hơn cho diagnostics, quan sát ranking hoặc công cụ nội bộ.

## 5. Total hits và quan hệ của con số tổng

### 5.1. Total hits không phải số phần tử hiện tại

Ví dụ query tìm được 430 document, nhưng page size là 20:

- Danh sách hit hiện tại chứa tối đa 20 kết quả.
- Total hits có thể là 430.
- Trang tiếp theo lấy phần kết quả kế tiếp theo cùng điều kiện và thứ tự.

DTO nên phân biệt rõ:

~~~java
public record SearchPageResponse<T>(
    List<T> items,
    long totalHits,
    int page,
    int size
) {
}
~~~

Không tính total bằng `items.size()` vì giá trị đó chỉ là số phần tử đã trả về trong trang.

### 5.2. Total hits có thể là con số chính xác hoặc cận dưới

Elasticsearch có thể giới hạn việc đếm total hits để tiết kiệm chi phí. Khi total-hit tracking được giới hạn, response có thể biểu thị quan hệ `eq` (đếm chính xác) hoặc `gte` (số được báo cáo là cận dưới).

Ví dụ:

- `eq` với 430 nghĩa là tổng được xác nhận chính xác là 430.
- `gte` với 10.000 nghĩa là có ít nhất 10.000 hit; tổng thực có thể cao hơn.

Spring Data Elasticsearch có thể expose relation này qua API SearchHits tùy phiên bản. Khi API nghiệp vụ hiển thị tổng, hãy giữ cả giá trị lẫn relation nếu có thể nhận được. Nếu chỉ trả một số không kèm relation, client có thể hiểu nhầm cận dưới thành tổng chính xác.

### 5.3. track_total_hits và chi phí

Request search có thể cấu hình theo dõi total hits chính xác hoặc giới hạn số lượng cần đếm. Việc đếm chính xác trên tập dữ liệu lớn có thể tăng chi phí.

Hãy chọn theo nhu cầu giao diện:

- Nếu cần số trang chính xác, có thể cần total-hit tracking đầy đủ.
- Nếu chỉ cần hiển thị một trang và nút “xem thêm”, có thể không cần tổng chính xác.
- Nếu chỉ cần biết còn kết quả hay không, lấy thêm một hit hoặc dùng cách phân trang phù hợp có thể đủ.
- Nếu chỉ cần số lượng theo một điều kiện riêng, dùng Count API.

Không gọi count riêng khi SearchHits đã có total chính xác đáp ứng yêu cầu. Ngược lại, không dùng một total bị giới hạn để tính tổng số trang chính xác.

### 5.4. DTO biểu diễn relation

Có thể thiết kế:

~~~java
public enum TotalRelation {
    EXACT,
    LOWER_BOUND,
    UNKNOWN
}

public record SearchTotal(
    long value,
    TotalRelation relation
) {
}
~~~

Service chuyển enum/metadata của Spring Data sang enum API của ứng dụng. Nếu phiên bản không expose relation, hãy đặt trạng thái phù hợp hoặc không tuyên bố con số là exact. Không tự suy luận relation chỉ từ việc số total bằng page size hoặc một ngưỡng quen thuộc.

## 6. Sort values và cursor cho trang tiếp theo

### 6.1. Sort values là metadata của hit

Khi query có sort, mỗi hit có thể mang danh sách sort values. Các giá trị này phản ánh chính xác những field sort đã dùng cho hit đó.

Ví dụ request sort theo timestamp rồi ID:

~~~json
{
  "sort": [
    { "createdAt": "asc" },
    { "productId": "asc" }
  ]
}
~~~

Một hit có thể trả:

~~~json
{
  "sort": [
    "2026-01-15T10:00:00Z",
    "P1001"
  ]
}
~~~

Sort values cần được giữ đúng thứ tự và kiểu dữ liệu để dùng trong `search_after` cho request kế tiếp.

### 6.2. Không tự dựng cursor từ content

Nếu sort theo ngày và ID, đừng tạo cursor bằng cách đọc field trong entity rồi tự serialize lại theo một định dạng mới. Hãy lấy sort values do Elasticsearch trả về, vì đó là giá trị gắn với request sort thực tế.

Ví dụ đọc sort values:

~~~java
List<Object> sortValues = hit.getSortValues();
~~~

Kiểu dữ liệu và biểu diễn của từng phần tử có thể phụ thuộc mapping, client và phiên bản. Giữ nguyên thông tin theo cách API Spring Data cung cấp, rồi serialize thành cursor opaque theo hợp đồng của ứng dụng.

### 6.3. Cursor nên là token opaque

Thay vì yêu cầu client gửi từng sort value, API có thể đóng gói chúng thành cursor:

~~~java
public record SearchCursor(
    String token
) {
}
~~~

Cursor có thể chứa hoặc tham chiếu:

- Sort values của hit cuối trang.
- Query/filter fingerprint.
- Sort definition/version.
- PIT ID nếu dùng point-in-time.
- Thời điểm hết hạn hoặc version của cursor format.

Nên ký hoặc bảo vệ token để client không thể tự sửa cursor thành một truy vấn khác. Nếu cursor chứa PIT ID hoặc dữ liệu nội bộ, không trả raw value nếu không cần; có thể dùng token được mã hóa/ký hoặc lưu trạng thái cursor phía server.

### 6.4. Cursor phải gắn với cùng query và sort

Trang tiếp theo phải dùng cùng điều kiện query và thứ tự sort với trang trước. Nếu client đổi keyword, filter hoặc sort giữa chừng, cursor cũ không còn hợp lệ.

Có thể lưu fingerprint của query/filter/sort trong cursor và xác minh khi nhận request tiếp theo. Nếu không khớp, yêu cầu client bắt đầu một phiên tìm kiếm mới.

### 6.5. Tie-breaker và PIT

Sort cần có tie-breaker ổn định, thường là một field duy nhất có doc values. Nếu nhiều document có cùng timestamp hoặc giá, thứ tự giữa chúng có thể thay đổi.

Với dữ liệu thay đổi trong lúc người dùng cuộn trang, dùng PIT kết hợp search_after khi cần góc nhìn ổn định. Cursor khi đó cần mang hoặc tham chiếu PIT ID và có thời hạn. Đóng PIT khi hoàn tất hoặc khi phiên tìm kiếm hết hạn.

## 7. Highlight fragments

### 7.1. Highlight là dữ liệu trình bày từ query

Highlight giúp giao diện chỉ ra phần nội dung khớp với từ khóa. Elasticsearch trả fragment theo field được yêu cầu, ví dụ:

~~~json
{
  "highlight": {
    "description": [
      "Compact wireless <mark>keyboard</mark> for travel"
    ]
  }
}
~~~

Trong Spring Data, SearchHit có thể cung cấp highlight field theo tên field:

~~~java
List<String> fragments =
    hit.getHighlightField("description");
~~~

Một field có thể trả nhiều fragment. DTO nên dùng danh sách để không giả định chỉ có một đoạn.

### 7.2. Không nhầm highlight với source

Highlight fragment được tạo theo query và cấu hình highlighter. Nó không thay thế giá trị gốc trong entity. Cần giữ cả hai nếu giao diện cần hiển thị nội dung đầy đủ và đoạn trích.

Ví dụ DTO:

~~~java
public record HighlightedText(
    String field,
    List<String> fragments
) {
}
~~~

Ánh xạ:

~~~java
HighlightedText descriptionHighlight =
    new HighlightedText(
        "description",
        hit.getHighlightField("description")
    );
~~~

Nếu field không được highlight, danh sách có thể rỗng. Hãy thiết kế client để xử lý trạng thái không có fragment.

### 7.3. Xử lý HTML an toàn

Một số highlighter trả fragment có tag đánh dấu. Nếu đưa fragment trực tiếp vào HTML, nội dung document có thể chứa markup hoặc ký tự không tin cậy.

Chọn chiến lược rõ ràng:

- Cấu hình pre/post tags riêng, đơn giản và có kiểm soát.
- Escape nội dung trước khi render và chỉ cho phép markup đánh dấu đã xác định.
- Dùng component hiển thị text an toàn, không render HTML tùy ý.
- Không xem fragment từ document là HTML đáng tin cậy.

Không xóa toàn bộ tag bằng replace đơn giản nếu điều đó có thể làm hỏng nội dung hoặc cho phép markup lạ lọt qua. Hãy dùng sanitizer/renderer phù hợp với nền tảng giao diện.

### 7.4. Highlight có chi phí

Highlight có thể làm tăng công việc của search request, đặc biệt trên field dài hoặc nhiều fragment. Chỉ yêu cầu highlight cho các field giao diện thực sự hiển thị và giới hạn fragment/fragment size theo nhu cầu.

Không bật highlight toàn bộ field trong mọi endpoint tìm kiếm nếu chỉ một màn hình cần tính năng đó.

## 8. Explanation, matched queries và inner hits

### 8.1. Explanation để chẩn đoán score

Explanation mô tả các thành phần góp phần tạo score của một hit. Đây là thông tin hữu ích khi debug vì sao một document được xếp cao hoặc thấp.

Nó có thể rất dài và tạo overhead. Chỉ bật trong endpoint quản trị hoặc chế độ debug có kiểm soát. Không trả explanation mặc định cho mọi người dùng.

### 8.2. Matched query names

Có thể đặt tên cho một số query clause và nhận biết hit khớp với clause nào nếu request sử dụng tính năng matched queries. Điều này hữu ích khi giao diện cần hiển thị nhãn lý do, ví dụ “khớp tên”, “khớp thương hiệu” hoặc “khớp từ khóa phụ”.

Tên matched query nên được định nghĩa trong server code. Không dùng nó như dữ liệu phân quyền và không cho client tự tạo tên để điều khiển logic truy cập.

### 8.3. Inner hits cho nested documents

Khi query nested hoặc parent/child yêu cầu inner hits, response có thể chứa các document con khớp bên trong document cha.

Ví dụ sản phẩm có nhiều offer, query có thể tìm offer thuộc nhà bán cụ thể. Inner hits giúp giao diện biết offer nào đã khớp thay vì chỉ biết sản phẩm cha phù hợp.

Inner hits có thể tăng kích thước response. Giới hạn số inner hit, chỉ yêu cầu field cần thiết và ánh xạ chúng thành DTO riêng. Không mặc định mọi hit đều có inner hits.

## 9. Aggregations và suggest không phải metadata của một hit

### 9.1. Aggregations thuộc toàn response

Aggregation trả số liệu tổng hợp như số sản phẩm theo danh mục, histogram giá hoặc thống kê theo thương hiệu. Chúng thuộc toàn bộ search response, không thuộc về một document riêng.

Ví dụ một response có thể chứa 20 hit và aggregation đếm số sản phẩm trong từng category. DTO nên tách:

- Danh sách hit.
- Metadata phân trang.
- Aggregation buckets/statistics.

Không gắn aggregation vào từng item chỉ để đơn giản hóa JSON nếu dữ liệu đó thực chất thuộc toàn query.

### 9.2. Suggest là một nhóm kết quả riêng

Suggest response có thể cung cấp gợi ý từ khóa hoặc completion options. Nó có cấu trúc khác với SearchHit thông thường.

Nếu API trả cả kết quả tìm kiếm và gợi ý, hãy biểu diễn thành hai phần rõ ràng trong response DTO. Đừng giả định suggest là một loại highlight hoặc một danh sách document.

## 10. Thiết kế response DTO

### 10.1. Không trả trực tiếp đối tượng framework

Không nên để controller trả trực tiếp SearchHits hoặc SearchHit như hợp đồng API lâu dài. Những kiểu này thuộc thư viện Spring Data và có thể thay đổi theo phiên bản.

DTO do ứng dụng sở hữu giúp:

- Giữ hợp đồng API ổn định khi nâng Spring Data.
- Chỉ expose metadata đã được chọn.
- Đặt tên field theo ngôn ngữ nghiệp vụ.
- Kiểm soát nullability và kiểu dữ liệu.
- Không làm lộ index name, raw explanation hoặc thông tin nội bộ.
- Dễ viết contract test và tài liệu API.

### 10.2. Ví dụ response cho tìm kiếm sản phẩm

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    Float score,
    List<String> nameHighlights
) {
}

public record SearchPageMetadata(
    long totalHits,
    String totalRelation,
    int page,
    int size,
    boolean hasNext
) {
}

public record ProductSearchResponse(
    List<ProductSearchItem> items,
    SearchPageMetadata page
) {
}
~~~

Đây là hợp đồng minh họa. Nếu API không cung cấp total relation, có thể bỏ field đó hoặc biểu diễn trạng thái unknown một cách rõ ràng. Không gán exact khi chưa xác minh.

### 10.3. Chuyển đổi từ SearchHits

~~~java
ProductSearchResponse toResponse(
        SearchHits<ProductDocument> hits,
        Pageable pageable,
        boolean hasNext) {

    List<ProductSearchItem> items = hits.getSearchHits()
        .stream()
        .map(hit -> {
            ProductDocument product = hit.getContent();

            return new ProductSearchItem(
                hit.getId(),
                product.getName(),
                product.getPrice(),
                hit.getScore(),
                hit.getHighlightField("name")
            );
        })
        .toList();

    SearchPageMetadata page = new SearchPageMetadata(
        hits.getTotalHits(),
        "UNKNOWN",
        pageable.getPageNumber(),
        pageable.getPageSize(),
        hasNext
    );

    return new ProductSearchResponse(items, page);
}
~~~

Trong code thực tế, thay "UNKNOWN" bằng relation đã ánh xạ từ API Spring Data/Elasticsearch của phiên bản dự án. Nếu không cần total relation, loại bỏ thuộc tính thay vì trả một giá trị giả định.

hasNext nên được tính từ metadata phân trang hoặc chiến lược cursor phù hợp. Đừng suy ra nó chỉ từ total nếu total có thể là cận dưới.

### 10.4. Response cho cursor pagination

Một response dùng cursor có thể có dạng:

~~~java
public record CursorSearchResponse<T>(
    List<T> items,
    String nextCursor,
    boolean hasMore
) {
}
~~~

Cursor được tạo từ sort values của hit cuối cùng, cùng query fingerprint và PIT metadata nếu có. Nếu không còn kết quả tiếp theo, nextCursor có thể là null.

Không để client tự ghép sort values hoặc PIT ID từ các field rời rạc. Một token opaque giúp server kiểm soát format và tính hợp lệ của cursor.

### 10.5. Response cho trang có aggregation

Nếu màn hình cần cả danh sách và facet filter:

~~~java
public record ProductFacet(
    String category,
    long count
) {
}

public record ProductSearchWithFacetsResponse(
    List<ProductSearchItem> items,
    SearchPageMetadata page,
    List<ProductFacet> categories
) {
}
~~~

Aggregation buckets được ánh xạ riêng. Điều này làm rõ rằng category counts mô tả tập kết quả của query chứ không phải metadata của từng sản phẩm.
## 11. Source filtering và nguy cơ entity không đầy đủ

### 11.1. Chỉ lấy field cần thiết

Elasticsearch cho phép source filtering để chỉ trả những field cần cho một màn hình. Điều này có thể giảm kích thước response và chi phí truyền dữ liệu.

Ví dụ màn hình gợi ý chỉ cần ID và name. Tuy nhiên, nếu Spring Data vẫn ánh xạ response thành `ProductDocument`, các field bị lược bỏ sẽ có giá trị null hoặc mặc định.

### 11.2. Không dùng entity đầy đủ như thể source đã đầy đủ

Nếu query chỉ lấy name và price, đừng truyền entity đó sang service nghiệp vụ như một ProductDocument hoàn chỉnh. Một method khác có thể hiểu nhầm `available == false` là giá trị thật, trong khi field đơn giản là không được tải.

Có thể:

- Dùng projection/DTO riêng cho màn hình.
- Giữ rõ thông tin source projection trong kiểu trả về.
- Chỉ gọi thao tác cần field đã được chọn.
- Không lưu lại entity partial bằng `save`, vì việc ghi object thiếu field có thể làm mất dữ liệu cũ.

### 11.3. Phân biệt field bị thiếu với field bị lược bỏ

Một giá trị null có thể có nhiều ý nghĩa:

- Document thật sự không có field.
- Field có trong source nhưng giá trị null.
- Query source filtering đã loại field.
- Mapping converter không ánh xạ field do tên hoặc kiểu không khớp.

API cần tránh nhập nhằng các trường hợp này nếu nghiệp vụ cần phân biệt. DTO có thể dùng trạng thái rõ ràng hoặc projection chỉ chứa các field chắc chắn được lấy.

## 12. Bảo mật và quyền riêng tư của metadata

### 12.1. Chỉ expose metadata có ích

Một số metadata hữu ích cho debug nhưng không nên công khai:

- Tên index vật lý.
- Routing hoặc shard-related details.
- Explanation đầy đủ.
- Raw query hoặc matched query nội bộ.
- Script details và thông tin diagnostics.
- PIT ID hoặc token cursor chưa được bảo vệ.

Endpoint quản trị có thể cần một số thông tin đó, nhưng phải được bảo vệ bằng authorization phù hợp.

### 12.2. Metadata không thay thế authorization

Search query phải áp dụng filter phân quyền ở server. Không chỉ trả kết quả rồi hy vọng client ẩn các item không được phép xem.

Ví dụ, filter tenant và access scope cần nằm trong query hoặc cơ chế bảo đảm quyền tương ứng. Highlight, inner hits và aggregations cũng có thể tiết lộ dữ liệu; phải áp dụng cùng phạm vi quyền cho toàn response.

### 12.3. Cursor cần được bảo vệ

Nếu cursor chứa sort values, query state hoặc PIT ID, client có thể sửa token nếu nó chỉ là JSON base64. Base64 không phải mã hóa hoặc chữ ký.

Có thể dùng token ký HMAC, mã hóa authenticated hoặc lưu cursor state phía server. Cần kiểm tra chữ ký, thời hạn và query fingerprint khi nhận cursor.

### 12.4. Tránh trả raw score như dữ liệu nghiệp vụ

Score thay đổi khi query, analyzer, index statistics hoặc ranking function thay đổi. Nếu client lưu score như một thuộc tính bền vững của sản phẩm, dữ liệu sẽ gây hiểu nhầm.

Hãy coi score là metadata của một lần tìm kiếm. Nếu nghiệp vụ cần một điểm chất lượng ổn định, hãy lưu một field riêng với định nghĩa và vòng đời rõ ràng.

## 13. Hiệu năng và lựa chọn metadata

### 13.1. Chỉ yêu cầu phần thực sự dùng

Metadata có chi phí. Một số nguyên tắc:

- Không bật explanation trong request người dùng cuối.
- Chỉ yêu cầu highlight cho field cần hiển thị.
- Giới hạn số fragment và độ dài fragment.
- Giới hạn inner hits.
- Chọn total-hit tracking theo nhu cầu.
- Không trả sort values nếu API không cần cursor hoặc diagnostics.
- Dùng source filtering/projection khi response source lớn.
- Tránh aggregations nặng nếu màn hình không sử dụng.

### 13.2. Total-hit tracking

Nếu giao diện chỉ cần nút “xem thêm”, việc đếm chính xác toàn bộ kết quả có thể không cần thiết. Có thể chọn cách theo dõi tổng phù hợp hoặc lấy thêm một hit để xác định có trang sau.

Nếu UI hiển thị “1–20 trong 430 kết quả” hoặc số trang cuối, cần total phù hợp với yêu cầu chính xác. Hãy hiểu relation của total trước khi đưa vào hợp đồng API.

### 13.3. Highlight và inner hits

Highlight trên nhiều field hoặc nội dung rất dài có thể tăng CPU và response size. Inner hits với nhiều nested children có thể làm response phình lớn.

Chọn số lượng vừa đủ cho UI. Nếu màn hình cần xem chi tiết các nested item, có thể tải chúng ở endpoint chi tiết thay vì trả tất cả trong danh sách search.

### 13.4. Sort values và cursor

Sort values có kích thước nhỏ so với source lớn, nhưng cursor có thể chứa nhiều thông tin hơn khi dùng PIT và query state. Giới hạn độ dài token, đặt TTL và không giữ PIT vô hạn.

## 14. Kiểm thử metadata và response contract

### 14.1. Unit test cho mapper

Mapper từ SearchHit sang DTO có thể được kiểm thử độc lập:

- ID được ánh xạ đúng.
- Content fields được chọn đúng.
- Score được giữ khi có.
- Highlight list rỗng được xử lý.
- Metadata không được phép expose không xuất hiện trong DTO.
- Nullability và total relation được biểu diễn đúng.

Có thể mock SearchHit hoặc tạo fixture theo API phiên bản đang dùng. Test này xác minh logic ánh xạ, không xác minh Elasticsearch trả metadata.

### 14.2. Integration test cho SearchHits

Chạy với Elasticsearch tương thích để xác minh:

1. Query có scoring trả score như mong đợi.
2. Query có sort trả sort values.
3. Highlight request trả fragment ở đúng field.
4. Total-hit tracking trả relation phù hợp.
5. Inner hits có dữ liệu khi query nested yêu cầu.
6. Aggregations được giữ ở response nếu có.
7. Source filtering không tạo entity partial bị sử dụng sai.
8. Cursor dùng sort values thực tế để lấy trang tiếp theo.

Không chỉ mock `ElasticsearchOperations` rồi kết luận metadata đã được ánh xạ chính xác.

### 14.3. Contract test cho API

Kiểm tra JSON response của controller:

- Tên field ổn định.
- Field nullable có quy ước.
- Total relation không bị bỏ mất khi cần.
- Cursor không lộ dữ liệu nội bộ.
- Score có mô tả đúng semantics.
- Highlight được xử lý an toàn.
- Không xuất hiện metadata nội bộ ngoài hợp đồng.

Khi nâng Spring Data Elasticsearch, contract test giúp phát hiện thay đổi ở tầng mapper trước khi ảnh hưởng client.

### 14.4. Kiểm thử trường hợp biên

Nên có dữ liệu kiểm thử:

- Không có kết quả.
- Một kết quả.
- Nhiều kết quả với score trùng.
- Field bị thiếu.
- Highlight không có fragment.
- Document có nested children.
- Total hits bị giới hạn.
- Sort values có date, number và keyword.
- PIT hết hạn.
- Query bị timeout hoặc trả trạng thái không hoàn chỉnh.

## 15. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| API chỉ còn field của entity | Service đã map SearchHits thành List content quá sớm | Giữ SearchHit đến khi tạo DTO |
| Score không có hoặc không hữu ích | Query không scoring hoặc request sort theo field | Xác định có cần score và cách sort |
| Total hits bằng số item hiện tại | Dùng items.size thay cho metadata tổng | Dùng total hits và giữ total relation |
| Client tính sai số trang | Total hits là cận dưới nhưng bị hiểu là exact | Trả relation hoặc chọn total tracking phù hợp |
| Highlight không xuất hiện | Query chưa yêu cầu highlight hoặc field không phù hợp | Kiểm tra highlight request và mapping |
| Highlight gây lỗi HTML | Fragment được render như HTML tin cậy | Escape/sanitize và chỉ cho phép tag đánh dấu |
| Cursor trang sau trả kết quả lặp | Cursor được dựng từ content hoặc sort thiếu tie-breaker | Dùng hit sort values và sort ổn định |
| Cursor không dùng được sau khi filter thay đổi | Cursor không gắn với query fingerprint | Kiểm tra query/sort state trong cursor |
| Entity có field null sau source filtering | Field đã bị lược bỏ khỏi source | Dùng projection DTO và không xem entity là đầy đủ |
| Inner hits hoặc aggregations không có | Query không yêu cầu hoặc API không giữ phần response đó | Kiểm tra DSL và API version |
| Response quá lớn | Trả explanation, nhiều highlight hoặc inner hits không giới hạn | Chỉ yêu cầu metadata cần thiết và đặt giới hạn |
| Nâng Spring Data làm mapper lỗi | Giả định getter hoặc kiểu metadata không ổn định | Kiểm tra API phiên bản và contract test |

## 16. Quy trình thiết kế phản hồi tìm kiếm

Khi xây một endpoint search, có thể đi theo trình tự:

1. Xác định dữ liệu nghiệp vụ nào cần trả trong mỗi item.
2. Xác định metadata hit nào hỗ trợ UI: score, highlight, sort values hay inner hits.
3. Xác định metadata toàn response: total hits, relation, page, aggregations hoặc suggest.
4. Chọn query options để yêu cầu đúng metadata.
5. Giữ `SearchHits`/`SearchHit` trong tầng service cho đến khi ánh xạ xong.
6. Tạo DTO do ứng dụng sở hữu, không trả trực tiếp object framework.
7. Bảo vệ cursor và loại bỏ metadata nội bộ không cần expose.
8. Kiểm tra source filtering để tránh dùng entity partial như entity đầy đủ.
9. Viết unit test cho mapper và contract test cho response.
10. Integration test trên Elasticsearch để xác minh metadata thực sự có mặt và đúng semantics.
11. Đo kích thước response và chi phí của highlight, total tracking, inner hits hoặc explanation.
12. Giữ hợp đồng API ổn định khi nâng phiên bản Spring Data Elasticsearch.

## 17. Những điểm cần ghi nhớ

- Entity content đến từ `_source`; search metadata mô tả hit và toàn bộ response.
- `SearchHit<T>` giữ content cùng metadata của một document; `SearchHits<T>` giữ danh sách hit và metadata chung.
- Không chuyển thành `List<T>` trước khi đã lấy các metadata cần thiết.
- Score là tín hiệu xếp hạng tương đối, không phải xác suất.
- Total hits có thể exact hoặc lower bound; đừng mặc định mọi con số tổng đều chính xác.
- Sort values cần được giữ nguyên để xây cursor cho `search_after`.
- Highlight fragments là dữ liệu trình bày, cần xử lý HTML an toàn.
- Explanation, matched queries và inner hits chỉ nên bật khi use case cần.
- Aggregations và suggest thuộc response chung, không phải metadata của một hit.
- DTO riêng giúp kiểm soát hợp đồng API, nullability và thông tin được expose.
- Source filtering có thể tạo entity partial; không dùng entity đó như dữ liệu đầy đủ hoặc lưu ngược bằng `save`.
- Cursor cần gắn với query/sort, có thời hạn và được bảo vệ.
- Kiểm thử cả mapper lẫn response thực tế với Elasticsearch tương thích.

Khi xác định rõ metadata nào phục vụ chức năng nào, service có thể giữ đúng thông tin trong suốt quá trình xử lý và chỉ trả phần cần thiết cho client. Kết quả tìm kiếm khi đó vừa có đủ dữ liệu để hiển thị, phân trang và giải thích, vừa có hợp đồng API rõ ràng và dễ duy trì.

