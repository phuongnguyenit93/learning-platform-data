# Text index, `@TextIndexed` và `@Language` trong Spring Data MongoDB

## Mục tiêu và bối cảnh

Khi xây dựng chức năng tìm bài viết, tài liệu hoặc sản phẩm, người dùng nhập vài từ khóa thay vì biết chính xác giá trị của một trường. MongoDB cung cấp **text index** để tìm từ trong nội dung đã được phân tích, thông qua toán tử `$text`. Spring Data MongoDB hỗ trợ khai báo index bằng `@TextIndexed`, lựa chọn ngôn ngữ bằng `@Document(language = ...)` và `@Language`, cũng như tìm kiếm qua `MongoTemplate`, `TextCriteria` và `TextQuery`.

Sau bài học, bạn có thể giải thích cách text index hoạt động, tạo một index nhiều trường với trọng số phù hợp, phân biệt ngôn ngữ mặc định và ngôn ngữ theo document, truy vấn kèm điểm liên quan và chẩn đoán lỗi thực tế.

**Phạm vi:** Đây là text index *gốc* của MongoDB. **MongoDB Search** dùng chỉ mục và analyzer riêng với toán tử `$search`, phù hợp cho autocomplete, fuzzy matching, phân tích ngôn ngữ và xếp hạng phức tạp hơn.

## 1. Text index hoạt động như thế nào?

Ví dụ hệ thống lưu bài hướng dẫn trong collection `articles`:

```javascript
db.articles.insertMany([
  {
    title: "Spring Data MongoDB guide",
    body: "Create indexes and query MongoDB documents with Spring Data",
    contentLanguage: "english"
  },
  {
    title: "MongoDB search fundamentals",
    body: "Learn text indexing, search scoring and query design",
    contentLanguage: "english"
  },
  {
    title: "Introducción a MongoDB",
    body: "Aprende a buscar documentos con índices de texto",
    contentLanguage: "spanish"
  }
]);
```

Tạo một text index kết hợp hai trường:

```javascript
db.articles.createIndex(
  { title: "text", body: "text" },
  {
    name: "article_text_idx",
    weights: { title: 5, body: 1 },
    default_language: "english",
    language_override: "contentLanguage"
  }
);

db.articles.find({ $text: { $search: "mongodb" } });
```

MongoDB lập chỉ mục theo các **term** của văn bản và xử lý chúng theo ngôn ngữ: có thể bỏ các **stop words** như `the` trong tiếng Anh, và dùng **stemming** để quy các dạng từ về một gốc gần đúng. Vì vậy, `$text` tìm term đã được lập chỉ mục; nó **không phải** toán tử tìm chuỗi con bất kỳ như `contains`.

`weights` tăng mức đóng góp tương đối của một trường vào `textScore`. Trong ví dụ trên, từ khóa xuất hiện ở `title` thường có ảnh hưởng lớn hơn từ ở `body`, nhưng điểm cuối cùng còn phụ thuộc những thống kê và term của document.

| Cơ chế | Đặc điểm | Trường hợp sử dụng |
| --- | --- | --- |
| Index thông thường (`@Indexed`) | Hỗ trợ lọc bằng, khoảng giá trị và một số truy vấn tiền tố | Mã, ngày, trạng thái, khóa tra cứu |
| Text index + `$text` | Tìm các term trong nhiều trường theo ngôn ngữ | Tìm từ khóa cơ bản trong tiêu đề, nội dung |
| `$regex` | So khớp mẫu chuỗi; chỉ một số mẫu tận dụng index hiệu quả | Tìm mẫu hay tiền tố đơn giản |
| MongoDB Search | Search index và analyzer chuyên dụng | Autocomplete, fuzzy, synonym, ranking nâng cao |

Những điểm cốt lõi:

- Một collection chỉ có **tối đa một text index**, nhưng index đó có thể chứa nhiều trường.
- Các term trong chuỗi tìm kiếm `$search: "spring mongodb"` mặc định được kết hợp theo **OR**. Muốn tìm cụm từ, phải đặt cụm từ trong dấu ngoặc kép của chính chuỗi `$search`.
- Truy vấn `$text` yêu cầu text index đã tồn tại và kết quả không tự động sắp theo độ liên quan.
- Tùy text index version và tùy chọn truy vấn, tìm kiếm có thể không phân biệt hoa/thường và dấu. Cần kiểm tra trên dữ liệu thực tế.

## 2. Khai báo `@TextIndexed`, `@Language` và `@TextScore`

Thêm `spring-boot-starter-data-mongodb` tương thích với phiên bản Spring Boot đang dùng, cấu hình kết nối và tạo entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Language;
import org.springframework.data.mongodb.core.index.TextIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.TextScore;

@Document(collection = "articles", language = "english")
public class Article {

    @Id
    private String id;

    @TextIndexed(weight = 5)
    private String title;

    @TextIndexed
    private String body;

    @Language
    private String contentLanguage;

    @TextScore
    private Float score;

    // Constructors, getters và setters được lược bớt.
}
```

| Thành phần | Vai trò |
| --- | --- |
| `@Document(collection = "articles")` | Gắn entity với collection `articles` |
| `@Document(language = "english")` | Xác định **ngôn ngữ mặc định cho text index** được tạo từ entity |
| `@TextIndexed` | Gộp trường vào text index duy nhất của collection |
| `@TextIndexed(weight = 5)` | Đặt trọng số tương đối; mặc định là 1 |
| `@Language` | Đánh dấu property chứa **ngôn ngữ riêng của từng document**, dùng khi lập chỉ mục |
| `@TextScore` | Nhận metadata điểm liên quan của truy vấn `$text`; không ghi như trường dữ liệu thường |

Hai `@TextIndexed` trên tạo ra **một định nghĩa index**, không phải hai index độc lập. Với `@Language` đặt trên `contentLanguage`, Spring Data sử dụng property này làm trường ghi đè ngôn ngữ; trong MongoDB nó tương ứng tùy chọn `language_override: "contentLanguage"`. Ví dụ document có `contentLanguage: "spanish"` sẽ được phân tích theo tiếng Tây Ban Nha; document không có override dùng `default_language` là `english`.

**Phân biệt chính xác:** `@Language` không làm `contentLanguage` trở thành trường tìm kiếm toàn văn. Nó chỉ quyết định cách phân tích những trường `@TextIndexed`. Ngôn ngữ lưu trong document và ngôn ngữ của *truy vấn* là hai khái niệm khác nhau.

### Chỉ mục cho trường lồng nhau

```java
@Document(collection = "knowledge")
class KnowledgeItem {
    @TextIndexed(weight = 4)
    String title;

    Summary summary;
}

class Summary {
    @TextIndexed(weight = 2)
    String description;
}
```

Spring Data có thể lập chỉ mục cho các đường dẫn `title` và `summary.description`. Khi dùng `@Field` đổi tên trường, hãy đối chiếu tên thực tế của các key trong database. Không nên giả định mọi trường trong object lồng nhau tự động được đánh text index.

## 3. Tạo index thực sự trong MongoDB

Annotation chỉ là **metadata** cho Spring Data. Từ Spring Data MongoDB 3.0, cơ chế tạo index tự động mặc định **tắt**. Đối với môi trường học tập hoặc phát triển, có thể bật trong Spring Boot:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

Trong môi trường vận hành, nên tạo và thay đổi index qua migration hoặc quy trình triển khai có kiểm soát vì việc lập index trên collection lớn tốn tài nguyên.

Nếu muốn chủ động tạo index từ chính annotation của entity:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;
import org.springframework.stereotype.Component;

@Component
public class ArticleIndexInitializer {
    private final MongoTemplate mongoTemplate;

    public ArticleIndexInitializer(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void createIndexes() {
        var resolver = new MongoPersistentEntityIndexResolver(
            mongoTemplate.getConverter().getMappingContext()
        );

        resolver.resolveIndexFor(Article.class)
            .forEach(index -> mongoTemplate.indexOps(Article.class).ensureIndex(index));
    }
}
```

Đây là ví dụ cho **một** entity; khi áp dụng production cần chọn một nguồn quản lý index rõ ràng để tránh các cấu hình chồng nhau. Cũng có thể dùng lệnh `createIndex` trực tiếp ở mục 1 nếu cơ chế migration chịu trách nhiệm tạo chỉ mục.

Kiểm tra sau khi ứng dụng khởi động:

```javascript
db.articles.getIndexes();
```

Xem `weights` có cả `title` và `body`, cùng các tùy chọn `default_language` và `language_override`. Tùy phiên bản MongoDB, key nội bộ của text index có thể hiển thị dưới dạng `_fts`/`_ftsx` thay vì khai báo ban đầu.

Thay đổi danh sách trường, weight hoặc language trên annotation **không tự động thay đổi** index hiện hữu. Cần migration thích hợp (thường phải drop và tạo lại text index), xem xét dung lượng và thời gian xây dựng lại.

## 4. Tìm kiếm bằng `MongoTemplate` và xếp hạng theo `textScore`

Sử dụng `TextCriteria` và `TextQuery` để dựng truy vấn thay vì lắp ghép chuỗi BSON thủ công:

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;
import org.springframework.stereotype.Service;

@Service
public class ArticleSearchService {
    private final MongoTemplate mongoTemplate;

    public ArticleSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Article> search(String input, int requestedLimit) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Từ khóa không được để trống");
        }

        TextCriteria criteria = TextCriteria.forDefaultLanguage()
            .matching(input.trim());

        TextQuery query = TextQuery.queryText(criteria)
            .sortByScore()
            .includeScore();

        query.limit(Math.min(Math.max(requestedLimit, 1), 100));
        return mongoTemplate.find(query, Article.class);
    }
}
```

`sortByScore()` bổ sung sắp xếp theo metadata `textScore`; `includeScore()` đưa metadata này vào kết quả. Khi entity có `@TextScore Float score`, Spring Data ánh xạ điểm vào property `score`. Điểm số không phải xác suất và không phù hợp để so sánh tuyệt đối giữa các index hoặc bộ dữ liệu khác nhau. Đối với truy vấn đọc thông thường, `score` có thể là `null`.

Câu lệnh tương đương ở MongoDB:

```javascript
db.articles.find(
  { $text: { $search: "mongodb" } },
  { title: 1, body: 1, score: { $meta: "textScore" } }
).sort({ score: { $meta: "textScore" } });
```

### Các kiểu truy vấn thường gặp

```java
// Chứa ít nhất một trong các term.
TextCriteria any = TextCriteria.forDefaultLanguage()
    .matchingAny("spring", "mongodb");

// Chứa một cụm từ theo cơ chế phân tích term của $text.
TextCriteria phrase = TextCriteria.forDefaultLanguage()
    .matchingPhrase("spring data");

// Chứa mongodb, loại document có term legacy.
TextCriteria exclude = TextCriteria.forDefaultLanguage()
    .matching("mongodb")
    .notMatching("legacy");

// Phân tích term của truy vấn bằng tiếng Tây Ban Nha.
TextCriteria spanish = TextCriteria.forLanguage("spanish")
    .matching("documentos");

List<Article> matches = mongoTemplate.find(
    TextQuery.queryText(spanish).sortByScore(),
    Article.class
);
```

Tìm theo cụm bằng `matchingPhrase("spring data")` khác với OR của `matchingAny("spring", "data")`. Có thể dùng `caseSensitive(true)` và `diacriticSensitive(true)` trong `TextCriteria` nếu yêu cầu phân biệt kiểu chữ hoặc dấu; hãy kiểm chứng kết quả và chi phí truy vấn thực tế.

**`@Language` và `TextCriteria.forLanguage(...)` không thay thế nhau.** Annotation ảnh hưởng *cách lập chỉ mục document*, trong khi `forLanguage` ảnh hưởng *cách phân tích từ khóa gửi vào truy vấn*. Chọn đúng language ngay khi đánh chỉ mục dữ liệu rất quan trọng.

## 5. Ngôn ngữ và trường hợp tiếng Việt

MongoDB hỗ trợ một tập ngôn ngữ cụ thể cho text index gốc, chẳng hạn `english`, `spanish`, `french`, `german`, `portuguese`... Ngôn ngữ này chi phối stop words và stemming. Với tài liệu đa ngôn ngữ được hỗ trợ, mỗi document có thể chứa override:

```javascript
db.articles.insertOne({
  title: "Aprender Spring Data",
  body: "Guía para buscar documentos",
  contentLanguage: "spanish"
});

db.articles.find({
  $text: { $search: "documentos", $language: "spanish" }
});
```

Nếu document không có trường override, index dùng `default_language`. Đừng lưu giá trị ngôn ngữ tùy ý: MongoDB yêu cầu tên hoặc mã thuộc danh sách được hỗ trợ.

### Hạn chế quan trọng với dữ liệu tiếng Việt

**Text index gốc của MongoDB không có analyzer cho tiếng Việt.** Đặt `@Document(language = "vietnamese")` hoặc `TextCriteria.forLanguage("vi")` không cung cấp xử lý ngôn ngữ tiếng Việt và có thể gây lỗi ngôn ngữ không được hỗ trợ.

Nếu chỉ cần tìm các term đơn giản, chọn ngôn ngữ `none` để không áp dụng stop words và stemming của những ngôn ngữ khác:

```java
@Document(collection = "vietnamese_articles", language = "none")
class VietnameseArticle {
    @Id String id;
    @TextIndexed(weight = 4) String title;
    @TextIndexed String body;
}
```

Hoặc dùng `mongosh`:

```javascript
db.vietnamese_articles.createIndex(
  { title: "text", body: "text" },
  { default_language: "none", weights: { title: 4, body: 1 } }
);
```

`none` **không** biến MongoDB thành công cụ tách từ và hiểu ngữ nghĩa tiếng Việt: không tự xử lý chính xác từ đa âm tiết, đồng nghĩa, sai chính tả hoặc gợi ý khi nhập. Muốn triển khai tìm kiếm tiếng Việt chuyên sâu, cần thiết kế analyzer và quy trình search phù hợp (ví dụ MongoDB Search hoặc một search engine chuyên dụng). Nếu xây dựng trường văn bản chuẩn hóa để tìm không dấu, phải chuẩn hóa cùng quy tắc ở cả lúc lập chỉ mục lẫn lúc truy vấn, và kiểm thử với dữ liệu Việt thực tế.

| Dữ liệu | Cấu hình hợp lý | Giới hạn |
| --- | --- | --- |
| Chủ yếu tiếng Anh | `@Document(language = "english")` | Stop words và stemming tiếng Anh |
| Anh và Tây Ban Nha | Default `english`, `@Language` theo bản ghi | Truy vấn cần language phù hợp |
| Tiếng Việt, tìm term cơ bản | `@Document(language = "none")` | Không phân tích ngữ nghĩa tiếng Việt |
| Đa ngôn ngữ, tìm lỗi gõ và gợi ý | MongoDB Search/search engine | Đòi hỏi search index/analyzer riêng |

## 6. Kiểm chứng end-to-end và quan sát hiệu năng

Sau khi tạo index và thêm dữ liệu ở mục 1, chạy lần lượt:

```javascript
// Có một text index với hai trường và language override?
db.articles.getIndexes();

// Có tìm được term xuất hiện trong title hoặc body?
db.articles.find({ $text: { $search: "spring" } });

// Có tìm được cụm từ đứng liền nhau?
db.articles.find({ $text: { $search: '"spring data"' } });

// Score và thứ tự kết quả có hợp lý?
db.articles.find(
  { $text: { $search: "mongodb" } },
  { title: 1, score: { $meta: "textScore" } }
).sort({ score: { $meta: "textScore" } });

// Dùng kế hoạch và thống kê thực thi để chẩn đoán.
db.articles.find({ $text: { $search: "spring" } })
  .explain("executionStats");
```

Hãy thêm một document chỉ chứa từ khóa trong `body` và một document chứa từ khóa trong `title` để chứng minh cả hai trường đều được đánh chỉ mục. So sánh kết quả trước và sau khi thay đổi weight **trong môi trường thử nghiệm**; các score có thể thay đổi theo nội dung và tần suất term, nên không thể khẳng định một document luôn đứng đầu chỉ vì có weight cao.

Đọc `explain("executionStats")` để so sánh số lượng document/index entry được quét cùng chi phí thực thi. Các stage bên trong execution plan phụ thuộc phiên bản MongoDB; đừng dựa vào một tên stage duy nhất trong mọi môi trường. Khi đo hiệu năng, dùng tập dữ liệu có kích thước thực tế thay vì chỉ vài document.

## 7. Giới hạn và lỗi hay gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `text index required for $text query` | Collection chưa có text index | Kiểm tra `getIndexes()`, tên collection và quy trình tạo index |
| Có `@TextIndexed` mà database chưa có index | Tạo index tự động bị tắt | Bật có chủ đích khi phát triển hoặc dùng migration/`IndexResolver` |
| Không tạo được text index thứ hai | Một collection chỉ có tối đa một text index | Gộp trường vào index duy nhất hoặc thực hiện migration |
| Tìm term phổ biến không ra | Term thuộc stop words của language | Kiểm tra `default_language` và `@Language` |
| Tìm tiếng Việt không như mong đợi | Không có analyzer tiếng Việt trong text index gốc | Thử `none` hoặc chuyển sang search chuyên dụng |
| `score == null` | Truy vấn không phải `$text` hoặc không yêu cầu score | Dùng `TextQuery.includeScore()` hoặc `sortByScore()` |
| Đổi weight nhưng kết quả vẫn như cũ | Index cũ chưa được tạo lại | Migration cho index, xác minh `getIndexes()` |
| Tìm `data` không thấy `database` | `$text` không tìm chuỗi con tùy ý | Chọn cơ chế tìm kiếm phù hợp với yêu cầu |

Một số hạn chế bổ sung của text index MongoDB:

1. **Một text index cho mỗi collection.** Truy vấn chứa `$text` không được gọi `hint()` để ép dùng index khác.
2. **Text index không cải thiện phép sắp xếp thông thường.** Sắp theo ngày, tên hoặc trường khác cần cân nhắc index và kế hoạch truy vấn riêng.
3. **Compound text index có quy tắc nghiêm ngặt.** Nếu có key thông thường đứng trước key text, truy vấn `$text` phải có điều kiện bằng trên các key đứng trước; các key text phải liền nhau. Không thể trộn tùy ý với nhiều loại index đặc biệt.
4. **Index có chi phí lưu trữ và ghi.** Cập nhật nội dung văn bản kéo theo cập nhật index; xây dựng lại index trên collection lớn cần kế hoạch vận hành.
5. **Phân trang cần thứ tự ổn định.** Hai document có thể cùng `textScore`; nếu phân trang kết quả, cần tính toán tiêu chí tie-breaker, giới hạn input, số kết quả và kiểm chứng trên phiên bản server/driver sử dụng.

## 8. Bài tập vận dụng

**Bài 1 — Cấu hình:** Tạo collection `knowledge_items` với `title`, `description`, `tags` và `contentLanguage`. Cấu hình title weight 8 và description weight 2. Tạo index bằng annotation, xác minh các trường và weight qua `getIndexes()`. Giải thích vì sao chỉ có một text index.

**Bài 2 — Ngôn ngữ:** Thêm bài tiếng Anh và Tây Ban Nha. Gắn `@Language` và so sánh các truy vấn `forDefaultLanguage()` với `forLanguage("spanish")`. Xác định trường hợp stop words hoặc stemming làm thay đổi kết quả.

**Bài 3 — Ranking:** Thêm bài chỉ có term trong title, bài chỉ có term trong body và bài chứa term ở cả hai. Trả về `textScore`, đo thứ tự thực tế và mô tả ảnh hưởng của trọng số. Thử thay đổi index qua migration trên dữ liệu test.

**Bài 4 — Tiếng Việt:** Tạo collection riêng với `language = "none"`. Thử từ đơn, cụm nhiều âm tiết, biến thể có/không dấu và từ đồng nghĩa. Ghi lại khả năng/giới hạn, rồi đề xuất lúc nào cần MongoDB Search.

**Kết quả cần đạt:** có thể tạo, kiểm tra, truy vấn và giải thích được text index; phân biệt `@TextIndexed`, `@Language`, ngôn ngữ của query và `textScore`; nêu được giới hạn với tiếng Việt.

## 9. Tài liệu tham khảo

- [Spring Data MongoDB — Index Creation / Text Indexes](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
- [Spring Data MongoDB — Full-text Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data MongoDB — TextCriteria API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/TextCriteria.html)
- [MongoDB Manual — $text Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Manual — Text Search Languages](https://www.mongodb.com/docs/manual/reference/text-search-languages/)
- [MongoDB Manual — Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/)
