# `TextCriteria`, `TextQuery` và tìm kiếm toàn văn trong Spring Data MongoDB

Một ứng dụng quản lý bài viết có thể cần tìm nội dung chứa “truy vấn MongoDB”, ưu tiên tiêu đề có từ khóa phù hợp, loại trừ tài liệu cũ và phân trang kết quả. Lọc bằng phép so khớp chuỗi thông thường khó đáp ứng những yêu cầu này khi số document tăng. MongoDB hỗ trợ **text index** và toán tử **`$text`** để tìm theo từ được lập chỉ mục; **Spring Data MongoDB** cung cấp `TextCriteria` để biểu diễn điều kiện tìm kiếm, `TextQuery` để tạo truy vấn và `MongoTemplate` hoặc repository để đọc kết quả.

Bài học thuộc phần **Tìm kiếm nâng cao** của module `SPRING_DATA_MONGODB`. Sau bài này, bạn sẽ thiết kế text index, phân biệt từ khóa với cụm từ, tìm kiếm qua Spring Data, lấy điểm liên quan và xác minh kế hoạch thực thi. Ví dụ dùng tiếng Việt để làm rõ giới hạn của cơ chế phân tích ngôn ngữ trong MongoDB.

## 1. Tìm kiếm toàn văn hoạt động như thế nào?

Một **text index** tạo cấu trúc tra cứu theo các từ (*term*) lấy từ những trường chuỗi được chọn. Khi nhận truy vấn `$text`, MongoDB phân tích chuỗi tìm kiếm, dùng chỉ mục để tìm document chứa từ phù hợp rồi có thể tính **`textScore`** để xếp hạng. Khác với việc chỉ tìm một chuỗi con, hệ thống xử lý ở mức từ được tách ra; kết quả chịu ảnh hưởng của ngôn ngữ chỉ mục, *stop words*, *stemming*, trọng số trường và cú pháp tìm kiếm.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Text index | Chỉ rõ các trường được đưa vào chỉ mục toàn văn | `title`, `body` |
| `$text` | Điều kiện tìm kiếm trên các trường của text index | `{$text: {$search: "MongoDB index"}}` |
| `TextCriteria` | Xây dựng biểu thức tìm kiếm `$text` trong Java | `matchingAny("MongoDB", "Java")` |
| `TextQuery` | Đưa `TextCriteria` vào `Query`, có thể yêu cầu điểm và sắp xếp theo điểm | `TextQuery.queryText(criteria)` |
| `textScore` | Điểm tương quan của document với truy vấn, phục vụ xếp hạng | `{score: {$meta: "textScore"}}` |

**Giới hạn cần nắm:** `$text` là tìm kiếm theo từ; nó không mặc nhiên hỗ trợ sửa lỗi gõ, tìm chuỗi con giữa từ, autocomplete hay các bộ phân tích tiếng Việt chuyên sâu. Nếu sản phẩm cần tìm gần đúng, gợi ý tức thời hoặc pipeline xếp hạng phức tạp, hãy đánh giá thêm MongoDB Search (Atlas Search, dùng `$search`) hoặc một hệ thống tìm kiếm chuyên dụng. `$text` và aggregation `$search` là hai cơ chế khác nhau.

## 2. Chuẩn bị bộ dữ liệu mẫu

Các document sau mô phỏng một thư viện bài học. Dùng `mongosh` hoặc môi trường MongoDB có quyền ghi để chạy lần lượt các lệnh:

```javascript
db.articles.insertMany([
  {
    _id: "a1",
    title: "Tối ưu truy vấn MongoDB",
    body: "Học cách dùng chỉ mục, explain và đo hiệu năng truy vấn.",
    category: "database",
    published: true
  },
  {
    _id: "a2",
    title: "Tìm kiếm toàn văn với Spring Data MongoDB",
    body: "Sử dụng TextCriteria và TextQuery để tìm bài viết theo từ khóa.",
    category: "database",
    published: true
  },
  {
    _id: "a3",
    title: "Thiết kế ứng dụng Java",
    body: "Repository, kiểm thử và bảo trì ứng dụng Java.",
    category: "backend",
    published: true
  },
  {
    _id: "a4",
    title: "Truy vấn MongoDB cũ",
    body: "Tài liệu truy vấn cũ cần được cập nhật.",
    category: "database",
    published: false
  }
]);
```

Đây là dữ liệu minh họa; chạy `insertMany` lần thứ hai với cùng `_id` sẽ báo trùng khóa. Trong ứng dụng thực, nên tạo dữ liệu qua một quy trình seed có kiểm soát, sử dụng định danh ổn định và tránh vô tình nhân bản bản ghi.

## 3. Tạo text index đúng với nhu cầu tìm kiếm

### 3.1. Chọn trường, trọng số và ngôn ngữ

Ví dụ muốn tìm ở cả tiêu đề lẫn nội dung, đồng thời ưu tiên kết quả có từ khóa trong tiêu đề:

```javascript
db.articles.createIndex(
  { title: "text", body: "text" },
  {
    name: "articles_fulltext",
    weights: { title: 5, body: 1 },
    default_language: "none"
  }
);
```

Giải thích:

- `title: "text"` và `body: "text"` khai báo những trường được lập chỉ mục. Truy vấn `$text` tìm trong **tất cả trường thuộc text index** của collection này, chứ không chọn một trường tùy ý tại thời điểm truy vấn.
- `weights` tăng mức đóng góp của từ xuất hiện trong `title` so với `body` khi tính điểm. Trọng số hỗ trợ xếp hạng nhưng không đảm bảo một công thức điểm hay thứ tự cố định cho mọi dữ liệu và phiên bản.
- `default_language: "none"` tắt xử lý bỏ *stop words* và *stemming* theo một ngôn ngữ cụ thể. Đây là lựa chọn đáng xem xét với ví dụ tiếng Việt vì bộ *stemmer* tiếng Việt không được cung cấp như một ngôn ngữ được hỗ trợ trong text index cổ điển của MongoDB. Nó **không** bổ sung khả năng hiểu ngữ nghĩa hay tách từ ghép tiếng Việt.

Nếu bộ dữ liệu là tiếng Anh, bạn có thể chọn `default_language: "english"` để dùng các quy tắc ngôn ngữ tương ứng. Một collection đa ngôn ngữ có thể dùng trường ghi ngôn ngữ riêng cho từng document qua cấu hình `language_override`, nhưng chỉ sử dụng giá trị ngôn ngữ mà MongoDB hỗ trợ và kiểm thử kết quả trên dữ liệu thực.

**Ràng buộc quan trọng:** Mỗi collection chỉ có **một** text index cổ điển. Muốn tìm trên nhiều trường, đưa các trường vào cùng một chỉ mục. Không thể tạo một text index độc lập cho `title` và một text index độc lập khác cho `body` trên cùng collection. Việc thay đổi trường, trọng số hoặc cấu hình ngôn ngữ cần được thực hiện qua quy trình cập nhật chỉ mục; không giả định `createIndex` sẽ âm thầm thay thế chỉ mục cũ có cùng tập trường nhưng khác tùy chọn.

Để xem chỉ mục thực tế:

```javascript
db.articles.getIndexes();
```

### 3.2. Khi nào nên dùng chỉ mục ghép?

Nếu **mọi** truy vấn toàn văn đều bắt buộc giới hạn bởi một `tenantId`, có thể cân nhắc chỉ mục ghép có trường bằng ở đầu rồi tới các trường text:

```javascript
// Ví dụ thiết kế thay thế, KHÔNG chạy thêm trên collection
// articles đang có articles_fulltext: một collection chỉ có một text index.
db.tenant_articles.createIndex(
  { tenantId: 1, title: "text", body: "text" },
  { name: "tenant_articles_text", default_language: "none" }
);
```

Với text index ghép có trường thông thường đứng **trước** các trường text, truy vấn `$text` phải có điều kiện **bằng** trên các trường tiền tố đó để sử dụng chỉ mục. Chỉ chọn thiết kế này khi nghiệp vụ và các truy vấn thực tế nhất quán; đừng đặt trường tiền tố nếu ứng dụng còn cần tìm toàn văn trên toàn bộ collection mà không có giá trị của trường ấy.

## 4. Hiểu cú pháp `$text` trên MongoDB

### 4.1. Tìm theo các từ khóa

```javascript
db.articles.find({
  $text: { $search: "MongoDB Java" }
});
```

Với cú pháp thông thường, các từ được phân tích từ chuỗi tìm kiếm có ngữ nghĩa **OR**: document phù hợp với một trong các từ có thể được trả về. Truy vấn trên có thể khớp tài liệu chứa `MongoDB` hoặc `Java`; nó không buộc cả hai từ cùng xuất hiện. Nếu chức năng yêu cầu đúng một cụm từ, hãy dùng tìm kiếm cụm từ.

### 4.2. Tìm đúng cụm từ và loại trừ từ

```javascript
// Dấu ngoặc kép NẰM BÊN TRONG chuỗi $search.
db.articles.find({
  $text: { $search: '"truy vấn" -cũ' }
});
```

`"truy vấn"` yêu cầu cụm từ theo đúng thứ tự từ được lập chỉ mục. `-cũ` loại trừ tài liệu khớp với từ `cũ`. Với dữ liệu mẫu, đây là cách diễn đạt gần với yêu cầu “tìm bài chứa cụm truy vấn nhưng loại bài cũ”. Tuy nhiên, khớp cụm từ vẫn dựa trên bộ tách từ của text index; cần kiểm thử với dấu câu, tiếng Việt và trường văn bản dài.

Phân biệt ba nhu cầu:

| Yêu cầu | Cách biểu diễn phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Có ít nhất một từ trong `MongoDB Java` | `$search: "MongoDB Java"` | Ngữ nghĩa OR giữa các từ |
| Chứa cụm `truy vấn` | `$search: '\"truy vấn\"'` | Dấu nháy kép là một phần của chuỗi tìm kiếm |
| Chứa cụm `truy vấn`, loại từ `cũ` | `$search: '\"truy vấn\" -cũ'` | Ký hiệu `-` áp dụng cho term bị loại |

Về mặc định, tìm kiếm toàn văn của MongoDB thường không phân biệt chữ hoa/thường và dấu theo các quy tắc text index hiện đại; có thể điều chỉnh `$caseSensitive` và `$diacriticSensitive` khi cần. Không dựa vào hành vi mặc định để kiểm tra những tên riêng có yêu cầu khớp tuyệt đối; nếu nghiệp vụ cần khớp chính xác, hãy đánh giá trường chuẩn hóa hoặc điều kiện so sánh riêng.

### 4.3. Xếp hạng theo độ liên quan

Tìm kiếm toàn văn không mặc nhiên trả document theo thứ tự có ý nghĩa với người dùng. Hãy yêu cầu `textScore` và sắp xếp theo điểm:

```javascript
db.articles.find(
  { $text: { $search: "MongoDB truy vấn" } },
  {
    title: 1,
    category: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).limit(10);
```

Điểm số là thước đo **tương đối trong một truy vấn**, không phải xác suất đúng hoặc phần trăm phù hợp. Chỉ so sánh điểm của những document được đánh giá cho cùng một truy vấn và cấu hình index. Nếu nhiều document có điểm bằng nhau và cần phân trang ổn định, phải có chính sách sắp xếp phụ và kiểm thử kỹ tính ổn định khi dữ liệu thay đổi.

## 5. Ánh xạ entity và text index trong Spring Data MongoDB

Spring Data hỗ trợ `@TextIndexed` trên những thuộc tính muốn đưa vào text index và `@TextScore` cho thuộc tính nhận điểm tìm kiếm.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.TextIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.TextScore;

@Document(collection = "articles")
public class Article {
    @Id
    private String id;

    @TextIndexed(weight = 5)
    private String title;

    @TextIndexed
    private String body;

    private String category;
    private boolean published;

    @TextScore
    private Float score;

    protected Article() {}

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getBody() { return body; }
    public String getCategory() { return category; }
    public boolean isPublished() { return published; }
    public Float getScore() { return score; }
}
```

`@TextIndexed` mô tả những trường cần được lập chỉ mục, còn text index trong MongoDB phải thực sự tồn tại. Ở các phiên bản Spring Data MongoDB hiện đại, **tự động tạo index không được bật theo mặc định**. Cấu hình có thể bật trong môi trường phát triển:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

Trong ứng dụng có yêu cầu rõ về `default_language: "none"` và `weights`, cách đáng kiểm soát hơn là **quản lý chỉ mục qua migration** như lệnh `createIndex` ở mục 3. Nếu chọn bật tạo chỉ mục tự động theo annotation, cần cấu hình ngôn ngữ tương ứng và tránh để quá trình tự tạo đụng chỉ mục đã được quản lý bằng migration. Việc đổi annotation không đồng nghĩa MongoDB tự xóa và tái tạo chỉ mục cũ.

## 6. Viết truy vấn bằng `TextCriteria`

`TextCriteria` cung cấp API biểu đạt các thành phần của chuỗi `$search` mà không phải tự ghép chuỗi JSON truy vấn.

```java
import org.springframework.data.mongodb.core.query.TextCriteria;

// Tìm document chứa ít nhất một trong các từ được phân tích.
TextCriteria anyWord = TextCriteria.forDefaultLanguage()
    .matchingAny("MongoDB", "Java");

// Tìm cụm từ "truy vấn" và loại trừ term "cũ".
TextCriteria phraseWithoutOld = TextCriteria.forDefaultLanguage()
    .matchingPhrase("truy vấn")
    .notMatching("cũ");

// Tìm theo ngôn ngữ chỉ định khi index hỗ trợ ngôn ngữ đó.
TextCriteria english = TextCriteria.forLanguage("english")
    .matching("query");
```

| API | Ý nghĩa | Tương ứng về mặt ý định |
| --- | --- | --- |
| `forDefaultLanguage()` | Dùng ngôn ngữ mặc định của chỉ mục | Không cần cung cấp `$language` riêng |
| `forLanguage("english")` | Chỉ định ngôn ngữ cho truy vấn | `$language: "english"` |
| `matching("MongoDB")` | Thêm từ/cụm term thông thường | Một term trong `$search` |
| `matchingAny("MongoDB", "Java")` | Tìm một trong các term | Nhiều term có ngữ nghĩa OR |
| `matchingPhrase("truy vấn")` | Tìm cụm từ | Cụm trong dấu nháy kép |
| `notMatching("cũ")` | Loại trừ term | Term có tiền tố `-` |

`TextCriteria` mô tả cú pháp tìm kiếm của MongoDB, không tự bổ sung điều kiện `published = true` hay `category = "database"`. Những điều kiện nghiệp vụ đó được bổ sung vào `Query` bằng `Criteria` trong bước tiếp theo.

## 7. Dùng `TextQuery` và `MongoTemplate` để lấy kết quả

Ví dụ service nhận đầu vào là cụm từ, lọc những bài đã xuất bản thuộc nhóm `database`, xếp hạng theo điểm và giới hạn 10 kết quả:

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;

public class ArticleSearchService {
    private final MongoTemplate mongoTemplate;

    public ArticleSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Article> searchPublishedArticles(String phrase) {
        TextCriteria textCriteria = TextCriteria.forDefaultLanguage()
            .matchingPhrase(phrase);

        TextQuery query = TextQuery.queryText(textCriteria)
            .sortByScore()
            .includeScore();

        query.addCriteria(Criteria.where("published").is(true)
            .and("category").is("database"));
        query.limit(10);

        return mongoTemplate.find(query, Article.class);
    }
}
```

Ví dụ gọi:

```java
List<Article> articles = articleSearchService
    .searchPublishedArticles("truy vấn");

for (Article article : articles) {
    System.out.printf("%s | score=%s%n",
        article.getTitle(), article.getScore());
}
```

Các điểm cần hiểu:

1. `TextQuery.queryText(textCriteria)` tạo `Query` có điều kiện `$text`.
2. `sortByScore()` yêu cầu thứ tự theo độ liên quan, còn `includeScore()` đưa điểm vào projection để ánh xạ đến thuộc tính có `@TextScore`.
3. `Criteria` thêm điều kiện lọc thông thường; nó không thay đổi cú pháp cụm từ trong `TextCriteria`.
4. `limit(10)` giới hạn số document trả về. Với dữ liệu nhiều trang, cần quy định rõ điều kiện sắp xếp và biến động dữ liệu để tránh kết quả lặp/thiếu giữa các trang.

Trong dự án thật, hãy kiểm soát độ dài chuỗi tìm kiếm, tránh cho người dùng vô tình nhập cú pháp như `-term` hoặc dấu nháy khi giao diện chỉ mong nhận văn bản thuần. `TextCriteria` giúp xây cấu trúc truy vấn nhưng vẫn giữ nguyên ngữ nghĩa tìm kiếm toàn văn của chuỗi đầu vào.

### 7.1. Tìm theo nhiều từ thay vì cụm từ

Khi ô tìm kiếm cần lấy tài liệu chứa *một trong* các từ người dùng chọn, dùng `matchingAny`:

```java
TextCriteria criteria = TextCriteria.forDefaultLanguage()
    .matchingAny("MongoDB", "Java");

TextQuery query = TextQuery.queryText(criteria)
    .sortByScore()
    .includeScore();
query.limit(20);

List<Article> results = mongoTemplate.find(query, Article.class);
```

Kết quả `matchingAny` thường rộng hơn `matchingPhrase`. Khi đánh giá mức độ chính xác của tìm kiếm, nên so sánh hai truy vấn trên cùng bộ dữ liệu, đồng thời giải thích cho người dùng liệu ô tìm kiếm đang tìm từ bất kỳ hay tìm cụm từ.

## 8. Tìm toàn văn bằng repository khi nào phù hợp?

Repository có thể cung cấp một phương thức dùng `@Query` với điều kiện `$text` đơn giản:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ArticleRepository extends MongoRepository<Article, String> {
    @Query("{ '$text': { '$search': ?0 } }")
    List<Article> searchText(String searchExpression);
}
```

Lệnh gọi `searchText("MongoDB Java")` dùng ngữ nghĩa các term như MongoDB `$text`. Đây là ví dụ cho truy vấn đơn giản; nó **không tự bảo đảm sắp xếp theo `textScore` hoặc đưa điểm vào projection**. Khi cần lọc động, truy vấn cụm từ, điều chỉnh projection hay sắp xếp theo độ liên quan, `TextCriteria` + `TextQuery` + `MongoTemplate` thường rõ ràng và dễ kiểm soát hơn. Có thể xây custom repository để đóng gói logic ấy cho tầng nghiệp vụ.

Với phương thức repository hoặc service, tránh coi `$text` là một bộ lọc chuỗi con. Ví dụ, tìm `Mongo` không nhất thiết khớp từ `MongoDB`; muốn kiểu tìm tiền tố hoặc từ gần đúng thì cần thiết kế công cụ khác.

## 9. Đọc `explain()` và chẩn đoán hiệu năng

Một phép đo đơn giản trên MongoDB:

```javascript
db.articles.find(
  {
    $text: { $search: "MongoDB truy vấn" },
    published: true,
    category: "database"
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).limit(10).explain("executionStats");
```

Trong kết quả `explain`, hãy xác nhận truy vấn dùng text index dự kiến và quan sát `nReturned`, `totalKeysExamined`, `totalDocsExamined` cùng thông tin stage tìm kiếm toàn văn. Tên các stage như `TEXT_MATCH` có thể khác giữa các phiên bản MongoDB; đánh giá **kế hoạch thực tế và số lượng bản ghi xét**, không gắn logic chẩn đoán vào một chuỗi tên stage duy nhất.

Những cách tối ưu thường hiệu quả:

- **Chọn trường được lập chỉ mục có chủ đích.** Đưa mọi trường văn bản vào index làm tăng dung lượng và chi phí cập nhật, trong khi không phải trường nào cũng giúp tăng chất lượng kết quả.
- **Dùng trọng số phù hợp.** Với bài viết, từ khóa ở tiêu đề thường có giá trị hơn cùng từ khóa xuất hiện trong nội dung dài; điều chỉnh weights theo dữ liệu và tiêu chí đánh giá.
- **Kết hợp bộ lọc nghiệp vụ.** Điều kiện `published`, `category` hoặc quyền truy cập phải được áp dụng cùng truy vấn; đừng lấy nhiều kết quả rồi lọc toàn bộ trong Java.
- **Giới hạn projection và số kết quả.** Chỉ trả những trường cần hiển thị, đồng thời cân nhắc kích thước dữ liệu khi người dùng lật nhiều trang.
- **Đo chất lượng lẫn tốc độ.** Text index có thể nhanh nhưng chưa chắc trả đúng những bài người dùng mong đợi. Chuẩn bị tập câu hỏi và kết quả kỳ vọng để đánh giá cùng số liệu `explain`.

Lưu ý: Nếu collection dùng một text index ghép có trường tiền tố thông thường, truy vấn phải có điều kiện bằng trên các trường tiền tố thì mới dùng được index. Đồng thời, không thể cải thiện mọi truy vấn bằng cách tạo thêm text index độc lập trên cùng collection.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| `$text` báo thiếu text index | Chưa tạo index hoặc kết nối nhầm collection/database | Kiểm tra `db.articles.getIndexes()` và đúng database của ứng dụng |
| Kết quả không theo độ liên quan | Không sort bằng `$meta: "textScore"` | Dùng `sortByScore()` hoặc sort theo `$meta` |
| `score` luôn `null` trong entity | Không projection điểm hoặc mapping không phù hợp | Kiểm tra `@TextScore`, `includeScore()` và dữ liệu trả về |
| Tìm “truy vấn” khớp quá nhiều bài | Các từ rời trong chuỗi có ngữ nghĩa OR | Chuyển sang `matchingPhrase("truy vấn")` khi muốn cụm từ |
| Từ tiếng Việt không được phân tích như mong đợi | Dùng stemming/stop words tiếng Anh hoặc cơ chế tách từ không phù hợp tiếng Việt | Rà soát `default_language`, cân nhắc `none`, kiểm thử bộ từ khóa thực tế |
| Truy vấn không khớp từ viết thiếu một vài ký tự | `$text` không hỗ trợ fuzzy/substring theo mặc định | Cân nhắc MongoDB Search/autocomplete hoặc công cụ phù hợp |
| Muốn tạo thêm một text index nhưng lỗi | MongoDB giới hạn một text index cổ điển trên collection | Thiết kế lại index đang có để chứa các trường cần tìm |
| Kết quả có bài không được phép xem | Truy vấn chỉ có `$text`, thiếu điều kiện quyền truy cập | Bổ sung điều kiện tenant, công khai và phân quyền trước khi trả kết quả |

## 11. Thực hành: xây chức năng tìm bài học

1. Chạy `insertMany` ở mục 2 và tạo text index có `weights` cùng `default_language: "none"` ở mục 3. Xác minh bằng `getIndexes()`.
2. Dùng `$text` tìm `MongoDB Java` và đối chiếu kết quả với tìm cụm `"truy vấn"`. Giải thích vì sao hai truy vấn có tập kết quả khác nhau.
3. Thử `"truy vấn" -cũ` rồi thêm `published: true` để xem điều kiện toàn văn và điều kiện nghiệp vụ bổ sung cho nhau thế nào.
4. Chạy `TextCriteria.forDefaultLanguage().matchingPhrase("truy vấn")` qua `TextQuery`; gọi `sortByScore()` và `includeScore()`, sau đó in tiêu đề và điểm từ `@TextScore`.
5. Chạy `explain("executionStats")`, ghi lại index được sử dụng và số document kiểm tra. Điều chỉnh thử weights trên môi trường thực hành bằng cách quản lý lại text index, rồi so sánh thứ tự kết quả.
6. Tự thử các chuỗi `Mongo`, `MongoDB`, `java`, `Java`, từ có dấu và không dấu. Ghi lại những hành vi gây bất ngờ; dùng chúng để xác định yêu cầu tìm kiếm tiếng Việt của sản phẩm.

## 12. Tổng kết quyết định thiết kế

Chọn **text index + `$text`** khi cần tìm các term trong một hoặc nhiều trường văn bản và muốn triển khai trực tiếp với MongoDB. Trong Spring Data MongoDB, dùng **`TextCriteria`** để biểu diễn từ, cụm từ và loại trừ; dùng **`TextQuery`** để đưa điều kiện vào truy vấn, sắp xếp theo `textScore` và lấy điểm về entity. Với dữ liệu tiếng Việt, cấu hình ngôn ngữ và phép tách từ cần được kiểm thử kỹ; text index cổ điển không thay thế một công cụ tìm kiếm ngôn ngữ tự nhiên đầy đủ. Khi sản phẩm cần autocomplete, fuzzy search hoặc xếp hạng nâng cao, hãy đánh giá hệ thống tìm kiếm chuyên dụng dựa trên yêu cầu thực tế.
