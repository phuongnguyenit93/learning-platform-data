# $search, $searchMeta và ánh xạ kết quả về DTO

## Mục tiêu

Trong chương **Tìm kiếm nâng cao** của `SPRING_DATA_MONGODB`, sau khi biết cách kết nối và ánh xạ document qua Spring Data MongoDB, chúng ta xây dựng một API tìm kiếm bài viết có **xếp hạng theo độ liên quan**, **bộ lọc**, **tổng số kết quả** và **dữ liệu đầu ra DTO**. MongoDB Search cung cấp hai aggregation stage chính:

- `$search`: trả về các document phù hợp với truy vấn, cùng metadata như điểm liên quan `searchScore`.
- `$searchMeta`: trả về metadata của truy vấn, chẳng hạn tổng số kết quả và nhóm facet, **không trả danh sách document bài viết**.

Hai stage này thuộc **MongoDB Search** (trước đây thường gọi Atlas Search), sử dụng **Search index riêng**. Chúng khác với toán tử `$text` trên text index truyền thống, và không được tạo ra bằng annotation `@TextIndexed`. Chức năng có trên MongoDB Atlas và những môi trường self-managed/version hỗ trợ MongoDB Search; cần xác minh tính tương thích của deployment trước khi thực hành.

Kết thúc bài, người học có thể tự tạo Search index, chạy pipeline chứa `$search` và `$searchMeta`, đưa `searchScore` vào projection, trả về Java record/DTO bằng `MongoTemplate.aggregate()`, cũng như đánh giá phân trang, tính nhất quán và hiệu năng.

## 1. Chuẩn bị bộ dữ liệu và Search index

Giả sử ứng dụng quản lý tài liệu kỹ thuật có collection `articles`:

```javascript
db.articles.insertMany([
  {
    title: "Tìm kiếm với Spring Data MongoDB",
    summary: "Hướng dẫn tích hợp MongoTemplate và aggregation",
    category: "backend",
    published: true
  },
  {
    title: "Thiết kế MongoDB Search",
    summary: "Truy vấn text, chấm điểm, facet và metadata",
    category: "database",
    published: true
  },
  {
    title: "MongoDB aggregation patterns",
    summary: "Pipeline patterns for reporting and filtering",
    category: "database",
    published: true
  },
  {
    title: "Bản nháp: tìm kiếm nâng cao",
    summary: "Nội dung thử nghiệm chưa công khai",
    category: "backend",
    published: false
  }
]);
```

Tạo **MongoDB Search index** tên `article-search` (trong `mongosh` có hỗ trợ phương thức tạo Search index):

```javascript
db.articles.createSearchIndex("article-search", {
  mappings: {
    dynamic: false,
    fields: {
      title: { type: "string" },
      summary: { type: "string" },
      category: { type: "token" },
      published: { type: "boolean" }
    }
  }
});
```

Ý nghĩa mapping:

| Trường | Kiểu trong Search index | Cách sử dụng |
| --- | --- | --- |
| `title` | `string` | Tìm văn bản bằng `text` |
| `summary` | `string` | Tìm văn bản bằng `text` |
| `category` | `token` | Giá trị phân loại nguyên vẹn, dùng lọc bằng hoặc facet |
| `published` | `boolean` | Lọc tài liệu đã xuất bản bằng `equals` |

`dynamic: false` chỉ index những trường đã liệt kê. Nếu query đến trường chưa được index hoặc index sai kiểu, kết quả có thể không như kỳ vọng.

**Lưu ý về bộ dữ liệu:** ví dụ có cả tiếng Việt và tiếng Anh để minh họa kết nối kỹ thuật. Analyzer mặc định không bảo đảm tách từ, tìm không dấu hoặc hiểu đồng nghĩa tiếng Việt như một công cụ search đã được tối ưu cho tiếng Việt. Muốn tìm chính xác với văn bản Việt ở production, cần thiết kế và đánh giá analyzer phù hợp, thay vì giả định cấu hình ví dụ đã xử lý đủ mọi cách viết.

Search index được xây dựng **không đồng bộ**. Có thể xem tiến độ và trạng thái bằng giao diện quản trị hoặc:

```javascript
db.articles.getSearchIndexes("article-search");
```

Hãy đợi index sẵn sàng truy vấn trước khi chạy những pipeline ở các phần sau. Câu lệnh `db.articles.getIndexes()` dùng để xem các MongoDB index truyền thống; nó không thay thế `getSearchIndexes()`.

## 2. Sử dụng $search để lấy danh sách kết quả

Một pipeline chỉ trả về các bài đã xuất bản, tìm từ khóa trong `title` và `summary`:

```javascript
db.articles.aggregate([
  {
    $search: {
      index: "article-search",
      compound: {
        must: [
          {
            text: {
              query: "MongoDB",
              path: ["title", "summary"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "published",
              value: true
            }
          }
        ]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 0,
      id: { $toString: "$_id" },
      title: 1,
      summary: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Dòng xử lý:

1. `$search` thực hiện tìm kiếm trên index `article-search`. Stage này **phải đứng đầu pipeline** (kể cả pipeline con được hỗ trợ).
2. `compound.must` yêu cầu document khớp phần tìm từ khóa. `compound.filter` chỉ giữ bản ghi có `published = true`; filter dùng để thu hẹp kết quả mà không chấm điểm liên quan như clause văn bản.
3. `$limit` hạn chế số document trước khi project, giúp tránh tải cả tập kết quả về ứng dụng.
4. `$project` quyết định chính xác dữ liệu trả cho frontend: bỏ `_id` gốc, tạo `id` dạng chuỗi, lấy các trường cần hiển thị và đưa metadata `searchScore` thành field `score`.

Kết quả minh họa (điểm chỉ là ví dụ, không phải giá trị cố định):

```json
[
  {
    "id": "673a11111111111111111111",
    "title": "Tìm kiếm với Spring Data MongoDB",
    "summary": "Hướng dẫn tích hợp MongoTemplate và aggregation",
    "category": "backend",
    "score": 2.18
  }
]
```

MongoDB Search mặc định xếp các hit theo **điểm liên quan giảm dần** khi không chỉ định sắp xếp khác. Điểm được tính từ truy vấn, analyzer, thống kê term và cấu hình scoring; nó không phải tỷ lệ phần trăm hay xác suất đúng. Khi hai document có score bằng nhau, thứ tự của chúng có thể không ổn định, điều cần cân nhắc khi phân trang.

### Một số toán tử phổ biến trong $search

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `text` | Tìm các term trên trường `string` được index | `text: {query: "mongo", path: "title"}` |
| `phrase` | Tìm cụm từ theo trình tự token | `phrase: {query: "spring data", path: "title"}` |
| `autocomplete` | Hỗ trợ hoàn thiện từ khi nhập | Cần mapping `autocomplete` tương ứng |
| `compound.must` | Các điều kiện bắt buộc cùng khớp | Từ khóa + điều kiện khác |
| `compound.should` | Điều kiện nên khớp để tăng độ phù hợp | Boost khi title chứa từ khóa |
| `compound.filter` | Điều kiện lọc, không đóng góp score | `published = true` |
| `equals` | So khớp bằng trên kiểu index tương ứng | `category` kiểu `token` |

Ví dụ thêm bộ lọc danh mục vào `filter`:

```javascript
filter: [
  { equals: { path: "published", value: true } },
  { equals: { path: "category", value: "backend" } }
]
```

Để dùng `fuzzy` (chấp nhận một số lỗi gõ) trong `text`, có thể bổ sung `fuzzy: { maxEdits: 1 }` vào cấu hình `text` khi phù hợp. Cần đánh giá chính xác sai số, chi phí và từ vựng của dữ liệu thực; không nên mặc định bật fuzzy cho mọi truy vấn.

## 3. Sử dụng $searchMeta để lấy tổng số và facet

`$searchMeta` dùng cùng tập toán tử tìm kiếm nhưng **trả metadata**, không trả bài viết. Ví dụ đếm chính xác số bài khớp từ khóa và bộ lọc:

```javascript
db.articles.aggregate([
  {
    $searchMeta: {
      index: "article-search",
      compound: {
        must: [
          { text: { query: "MongoDB", path: ["title", "summary"] } }
        ],
        filter: [
          { equals: { path: "published", value: true } }
        ]
      },
      count: { type: "total" }
    }
  }
]);
```

Kết quả có dạng:

```json
[
  { "count": { "total": 3 } }
]
```

Số `3` chỉ để minh họa cấu trúc, không khẳng định số hit thực tế của dữ liệu mẫu. Khi chạy, phải lấy số trả về từ MongoDB.

Có hai kiểu count phổ biến:

- `count: { type: "total" }` trả **số kết quả chính xác**, có thể tốn thời gian hơn với truy vấn lớn.
- `count: { type: "lowerBound" }` trả **cận dưới** trong field `count.lowerBound`, phục vụ giao diện chỉ cần biết tối thiểu có bao nhiêu kết quả; không được trình bày nó như tổng chính xác.

**Đừng lấy `count.lowerBound` rồi gán nhãn “Tổng cộng chính xác”**. Khi đặt cấu hình mặc định hoặc dùng lower bound, code phải đọc đúng tên field và thể hiện ý nghĩa ước lượng.

### Facet: thống kê theo danh mục

Khi cần giao diện lọc theo nhóm, `$searchMeta` có thể trả buckets đếm theo `category`. Trường này đã được đánh index kiểu `token`:

```javascript
db.articles.aggregate([
  {
    $searchMeta: {
      index: "article-search",
      facet: {
        operator: {
          compound: {
            must: [
              { text: { query: "MongoDB", path: ["title", "summary"] } }
            ],
            filter: [
              { equals: { path: "published", value: true } }
            ]
          }
        },
        facets: {
          byCategory: {
            type: "string",
            path: "category",
            numBuckets: 10
          }
        }
      },
      count: { type: "total" }
    }
  }
]);
```

Metadata trả về có `facet.byCategory.buckets`, mỗi bucket gồm giá trị `_id` và `count` tương ứng. Nếu frontend cần tổng số và danh mục gợi ý, API có thể ánh xạ cả `count` lẫn `facet` sang DTO metadata riêng. Lưu ý facet đếm trên toàn bộ tập document **khớp điều kiện tìm kiếm của facet**, không nhất thiết cùng một nhóm với các filter ứng dụng thêm ở phía sau pipeline.

### Dùng $search và $$SEARCH_META trong cùng pipeline

Nếu muốn có cả hits và metadata từ **cùng một truy vấn** trong một pipeline, có thể thêm `count` vào `$search`, rồi truy cập biến `$$SEARCH_META` ở stage hỗ trợ sau đó:

```javascript
db.articles.aggregate([
  {
    $search: {
      index: "article-search",
      text: { query: "MongoDB", path: ["title", "summary"] },
      count: { type: "total" }
    }
  },
  { $limit: 10 },
  {
    $facet: {
      hits: [
        {
          $project: {
            _id: 0,
            id: { $toString: "$_id" },
            title: 1,
            score: { $meta: "searchScore" }
          }
        }
      ],
      metadata: [
        { $replaceWith: "$$SEARCH_META" },
        { $limit: 1 }
      ]
    }
  }
]);
```

Cách này trả một object gồm mảng `hits` và `metadata`, giảm việc ứng dụng tự ghép hai lượt truy vấn. Ví dụ dùng truy vấn `text` đơn giản nên kết quả **khác** ví dụ `compound` có lọc `published`; khi áp dụng thật phải đưa cùng filter vào `$search` để API không hiển thị dữ liệu nháp. Với hệ thống cần rõ ràng về hiệu năng và cấu trúc DTO, có thể giữ hai pipeline như phần tiếp theo.

## 4. Ánh xạ kết quả $search thành Java DTO

### Vì sao nên dùng DTO?

Document trong MongoDB có thể chứa trường nhạy cảm hoặc trường nội bộ mà giao diện không cần. DTO định nghĩa hợp đồng đầu ra độc lập với entity đang lưu. Ví dụ:

```java
import java.util.List;

public record ArticleHit(
    String id,
    String title,
    String summary,
    String category,
    Double score
) {}

public record ArticleSearchResult(
    List<ArticleHit> hits,
    long total,
    int page,
    int size
) {}
```

Đây là hai Java record riêng biệt trong cùng package, mỗi loại đặt vào file `.java` tương ứng. Với Java record, Spring Data MongoDB có thể ánh xạ kết quả aggregation vào constructor theo tên các trường.

Ở pipeline Java, cần làm rõ một số ánh xạ:

| Nguồn MongoDB | Field projection | DTO |
| --- | --- | --- |
| `_id` kiểu ObjectId | `id: {$toString: "$_id"}` | `String id` |
| `title` | `title: 1` | `String title` |
| `summary` | `summary: 1` | `String summary` |
| `category` | `category: 1` | `String category` |
| `{$meta: "searchScore"}` | `score` | `Double score` |

Không nên kỳ vọng `@TextScore` (dành cho text search truyền thống) tự động lấy metadata của MongoDB Search. Trong ví dụ này, chính `$project` đưa `searchScore` thành field thường tên `score`, sau đó `MongoTemplate` ánh xạ sang DTO.

### Triển khai MongoTemplate: lấy hits và total

Ví dụ sau dùng `org.bson.Document` để dựng các stage MongoDB Search; cách này tránh đưa trực tiếp chuỗi input của người dùng vào một đoạn JSON ghép bằng phép cộng chuỗi. Giữ `$search` và `$searchMeta` là **stage đầu tiên** ở mỗi pipeline.

```java
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

@Service
public class ArticleSearchService {
    private static final String COLLECTION = "articles";
    private static final String SEARCH_INDEX = "article-search";

    private final MongoTemplate mongoTemplate;

    public ArticleSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public ArticleSearchResult search(String keyword, int page, int pageSize) {
        if (keyword == null || keyword.isBlank() || keyword.length() > 200) {
            throw new IllegalArgumentException("Từ khóa phải có 1-200 ký tự");
        }
        if (page < 0) {
            throw new IllegalArgumentException("page không được âm");
        }
        if (pageSize < 1 || pageSize > 50) {
            throw new IllegalArgumentException("pageSize phải từ 1 đến 50");
        }

        long skip = (long) page * pageSize;
        if (skip > 1000) {
            throw new IllegalArgumentException(
                "Phân trang sâu cần dùng cơ chế searchAfter"
            );
        }

        Document conditions = searchConditions(keyword.trim());

        AggregationOperation searchStage = context -> new Document(
            "$search",
            new Document("index", SEARCH_INDEX)
                .append("compound", conditions)
        );

        AggregationOperation skipStage =
            context -> new Document("$skip", skip);
        AggregationOperation limitStage =
            context -> new Document("$limit", pageSize);

        AggregationOperation projectStage = context -> new Document(
            "$project",
            new Document("_id", 0)
                .append("id", new Document("$toString", "$_id"))
                .append("title", 1)
                .append("summary", 1)
                .append("category", 1)
                .append("score", new Document("$meta", "searchScore"))
        );

        Aggregation hitsPipeline = Aggregation.newAggregation(
            searchStage, skipStage, limitStage, projectStage
        );

        List<ArticleHit> hits = mongoTemplate
            .aggregate(hitsPipeline, COLLECTION, ArticleHit.class)
            .getMappedResults();

        AggregationOperation metaStage = context -> new Document(
            "$searchMeta",
            new Document("index", SEARCH_INDEX)
                .append("compound", conditions)
                .append("count", new Document("type", "total"))
        );

        Document metadata = mongoTemplate.aggregate(
            Aggregation.newAggregation(metaStage),
            COLLECTION,
            Document.class
        ).getUniqueMappedResult();

        long total = 0;
        if (metadata != null) {
            Document count = metadata.get("count", Document.class);
            if (count != null && count.get("total") instanceof Number number) {
                total = number.longValue();
            }
        }

        return new ArticleSearchResult(hits, total, page, pageSize);
    }

    private Document searchConditions(String keyword) {
        Document text = new Document("query", keyword)
            .append("path", List.of("title", "summary"));

        Document published = new Document("path", "published")
            .append("value", true);

        return new Document("must", List.of(
            new Document("text", text)
        )).append("filter", List.of(
            new Document("equals", published)
        ));
    }
}
```

**Những điểm cần kiểm tra khi đọc code:**

- `searchConditions()` tập trung định nghĩa cùng điều kiện tìm kiếm cho cả hai pipeline, giúp `hits` và `total` tuân theo cùng bộ lọc.
- `AggregationOperation` có thể tạo stage không có DSL chuyên dụng bằng `Document`, trong khi Spring Data vẫn cung cấp cơ chế thực thi aggregation và ánh xạ kết quả. Trong các phiên bản hỗ trợ, `Aggregation.stage(...)` cũng là một lựa chọn cho stage BSON/JSON tùy chỉnh.
- `$search` đứng đầu pipeline hit, tiếp theo là `$skip`, `$limit` và `$project`. Giới hạn `skip` nhằm tránh phân trang sâu với offset lớn.
- `$searchMeta` đứng đầu pipeline metadata, trả `count.total`. Code đọc dạng `Number` vì driver có thể trả kiểu số BSON khác nhau.
- Trường `id` được chuyển từ `_id` sang chuỗi ngay trong projection. Nếu hệ thống dùng ID khác ObjectId/String hoặc ID có thể `null`, phải điều chỉnh phép chuyển kiểu.
- Hai pipeline chạy trong **hai lệnh aggregation khác nhau**. Nếu dữ liệu hoặc Search index thay đổi giữa hai lệnh, `total` và `hits` có thể lệch nhau trong một khoảng ngắn; cần xác định mức nhất quán chấp nhận được ở UI.

Một REST controller có thể trả DTO trực tiếp:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
public class ArticleSearchController {
    private final ArticleSearchService service;

    public ArticleSearchController(ArticleSearchService service) {
        this.service = service;
    }

    @GetMapping("/search")
    public ArticleSearchResult search(
        @RequestParam String q,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "10") int size
    ) {
        return service.search(q, page, size);
    }
}
```

Ví dụ gọi `GET /api/articles/search?q=mongodb&page=0&size=10`. Controller ở đây tập trung minh họa luồng tìm kiếm; ứng dụng thực tế cần xử lý lỗi HTTP phù hợp cho `IllegalArgumentException`, kiểm soát truy cập theo dữ liệu người dùng và giám sát thời gian phản hồi.

## 5. Khi nào dùng Repository @Aggregation?

Nếu pipeline cố định và chỉ cần truyền từ khóa hoặc giới hạn, Spring Data MongoDB cho phép khai báo `@Aggregation` trên repository:

```java
import java.util.List;

import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ArticleRepository
        extends MongoRepository<ArticleDocument, String> {

    @Aggregation(pipeline = {
        "{ $search: { " +
            "index: 'article-search', " +
            "text: { query: ?0, path: ['title', 'summary'] } " +
          "} }",
        "{ $limit: ?1 }",
        "{ $project: { " +
            "_id: 0, id: { $toString: '$_id' }, " +
            "title: 1, summary: 1, category: 1, " +
            "score: { $meta: 'searchScore' } " +
          "} }"
    })
    List<ArticleHit> searchByText(String keyword, int limit);
}
```

Trong ví dụ, `ArticleDocument` là entity đã được khai báo `@Document(collection = "articles")` với `@Id String id` và các trường tương ứng. Đây là một phương án **minh họa pipeline cố định**; muốn giống API ở phần 4, cần bổ sung `compound.filter` cho `published = true` và cùng quy trình đếm bằng `$searchMeta`. Không nên sao chép method này vào API công khai nếu yêu cầu ẩn bản nháp mà chưa bổ sung filter.

Chọn `MongoTemplate` khi có nhiều điều kiện tùy chọn, pagination và metadata phức tạp; chọn `@Aggregation` khi pipeline ngắn, ít thay đổi và mapping có thể biểu đạt rõ ràng. Với cách nào cũng cần kiểm tra DTO có được ánh xạ đúng tên field sau `$project`.

## 6. Kiểm tra kết quả và chẩn đoán lỗi

Một quy trình kiểm tra có thể tiến hành như sau:

1. Đảm bảo deployment hỗ trợ MongoDB Search, Search index `article-search` tồn tại trên đúng collection và đã sẵn sàng.
2. Chạy `$search` trong `mongosh`, quan sát document hit và score.
3. Chạy `$searchMeta` với **cùng truy vấn và filter**; ghi lại `count.total` hoặc `count.lowerBound` đúng theo kiểu đã yêu cầu.
4. Gọi API Spring, kiểm tra `id` là chuỗi, `score` là số và không lộ những trường không có trong DTO.
5. Thêm document `published: false` có từ khóa rõ ràng, xác minh nó không có trong hits và không được đếm vào total.
6. Kiểm tra truy vấn rỗng, trang âm, page size vượt giới hạn, không có kết quả và kết quả có score bằng nhau.
7. Đo thời gian thực thi trên dữ liệu có kích thước thật; không kết luận từ vài document ví dụ.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `$search` không chạy trên MongoDB cục bộ | Deployment chưa hỗ trợ MongoDB Search | Kiểm tra nền tảng và version, triển khai dịch vụ Search phù hợp |
| Không tìm thấy Search index | Sai tên hoặc index chưa sẵn sàng | Xem `getSearchIndexes()`, tên collection, trạng thái index |
| Sai thứ tự pipeline | Có `$match` hoặc `$project` trước `$search` | Đưa `$search` hoặc `$searchMeta` lên đầu pipeline |
| Query từ khóa không ra kết quả | Trường chưa được index kiểu `string` hoặc analyzer không phù hợp | Kiểm tra mappings và dữ liệu mẫu |
| Lọc `category` không như mong đợi | Chưa index category kiểu `token` cho `equals` | Sửa mapping rồi chờ index cập nhật |
| DTO thiếu `id` hoặc `score` | Quên `$toString`, quên `$meta` hoặc alias sai | Kiểm tra output của `$project` trước khi mapping |
| `total = 0` dù có hits | Code đọc `total` nhưng query trả `lowerBound`, hoặc các filter khác nhau | Khớp cấu trúc metadata và dùng chung điều kiện |
| `total` và `hits` đôi lúc khác | Hai aggregation riêng, Search index cập nhật không tức thời | Chấp nhận độ trễ hoặc dùng chiến lược lấy metadata chung |
| Phân trang chậm khi page cao | `$skip` trên tập hit lớn | Dùng phân trang tham chiếu `searchAfter` khi khả dụng và thiết kế sort ổn định |

### Hiệu năng, tính nhất quán và an toàn

**Giới hạn và thứ tự:** dùng `$limit` khi trả hits, cân nhắc `$search` với sort/score và `searchAfter` cho trang sâu thay vì tăng `$skip` vô hạn. Nếu yêu cầu phân trang nhất quán, thiết kế tie-breaker khi nhiều kết quả đồng điểm, kiểm tra cách MongoDB Search hỗ trợ sắp xếp và token phân trang ở phiên bản đang sử dụng.

**Count:** `total` có thể tốn tài nguyên với tập hit lớn; `lowerBound` hợp lý hơn với UI chỉ cần “có ít nhất N kết quả”. Để phân tích scoring, có thể bật `scoreDetails: true` trong `$search` và project metadata `searchScoreDetails`, nhưng nên giới hạn cho môi trường chẩn đoán do tăng kích thước kết quả.

**Dữ liệu nhạy cảm:** chỉ trả các trường mà client cần qua `$project` và DTO. Đưa điều kiện kiểm soát đối tượng được phép xem vào chính truy vấn Search; không lấy tất cả hits rồi lọc dữ liệu bí mật ở application sau khi đã phân trang. Kiểm tra khả năng Search index cập nhật trễ so với collection gốc nếu nghiệp vụ yêu cầu thu hồi quyền truy cập tức thì.

**Quan sát:** đo latency phần tìm kiếm, đếm, phân phối size/keyword, trường hợp không có hit và lỗi của Search index. Theo dõi độ lớn index và tốc độ cập nhật khi dữ liệu nhiều. Với bài toán tiếng Việt, xây bộ truy vấn đánh giá precision/recall, cách tách từ, dấu, đồng nghĩa và hiệu năng trên bộ dữ liệu đủ đại diện.

## 7. Bài tập vận dụng

**Bài 1 — Search hits:** Tạo Search index cho `articles` với `title`, `summary`, `category` và `published`. Viết pipeline `$search` có `text` và `compound.filter`. Project kết quả thành DTO với `id` dạng chuỗi và `score` lấy từ `searchScore`.

**Bài 2 — Total và lower bound:** Chạy `$searchMeta` với `count.total` và `count.lowerBound` trên cùng từ khóa. Quan sát cấu trúc JSON khác nhau và giải thích vì sao không thể hiển thị lower bound như số chính xác.

**Bài 3 — Facet:** Sử dụng `$searchMeta.facet` để trả các bucket `category`. Thêm bộ lọc danh mục và xác minh facet, hits, total được định nghĩa theo cùng điều kiện nghiệp vụ.

**Bài 4 — DTO và API:** Viết `ArticleSearchService` và API `GET /api/articles/search`. Kiểm tra mapping `_id -> id`, `$meta -> score`, page size tối đa, từ khóa rỗng và các bài `published = false`.

**Bài 5 — Vận hành:** So sánh pipeline tách biệt `$search`/`$searchMeta` với pipeline `$search` + `$$SEARCH_META`. Phân tích lượt truy vấn, độ trễ, tính nhất quán, độ phức tạp DTO và chọn cách triển khai phù hợp cho giao diện có tổng số kết quả.

**Tiêu chí hoàn thành:** có thể tạo và xác minh Search index; giải thích khác biệt `$search` và `$searchMeta`; viết được pipeline có score và count; ánh xạ đúng về DTO Spring Data MongoDB; nhận diện rủi ro về paging, lọc dữ liệu và Search index cập nhật không đồng bộ.

## Tài liệu tham khảo

- [MongoDB Search — $search aggregation stage](https://www.mongodb.com/docs/search/query/aggregation-stages/search/)
- [MongoDB Search — $searchMeta aggregation stage](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/)
- [MongoDB Search — Count MongoDB Search Results](https://www.mongodb.com/docs/search/query/counting/)
- [MongoDB Search — facet operator](https://www.mongodb.com/docs/search/query/operators-collectors/facet/)
- [MongoDB Search — Create a Search Index](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/)
- [MongoDB Search — Query Reference](https://www.mongodb.com/docs/search/query/query-ref/)
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — Aggregation Repository Annotation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
