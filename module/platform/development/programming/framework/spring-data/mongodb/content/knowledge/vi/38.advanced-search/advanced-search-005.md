# Search index, analyzer và điều kiện hỗ trợ của môi trường triển khai

> **Phạm vi:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành truy vấn, aggregation, index, kiểm thử và chẩn đoán hiệu năng. Bài thuộc chương **Tìm kiếm nâng cao**, tập trung vào MongoDB Search (trước đây thường gọi là Atlas Search), cách phân tích văn bản và các yêu cầu để triển khai được tính năng này.

## 1. Mục tiêu và tình huống thực tế

Sau bài học, người đọc có thể:

1. Phân biệt **Search index** với chỉ mục B-tree, chỉ mục `text` thông thường và Vector Search index.
2. Thiết kế `mappings` theo trường cần tìm; chọn `analyzer` cho lúc lập chỉ mục và `searchAnalyzer` cho lúc truy vấn.
3. Tạo, kiểm tra trạng thái và sử dụng Search index với `$search` hoặc `$searchMeta`.
4. Gọi pipeline tìm kiếm bằng `MongoTemplate`, kiểm soát dữ liệu đầu vào và xử lý kết quả có điểm liên quan.
5. Kiểm tra điều kiện môi trường Atlas hoặc self-managed trước khi phụ thuộc vào Search trong ứng dụng.

**Ví dụ xuyên suốt:** một cửa hàng cần tìm sản phẩm theo tên và mô tả tiếng Việt, lọc theo nhóm hàng, tình trạng bán và mức giá. Người dùng có thể nhập “bàn phím”, “BÀN PHÍM” hoặc cụm gần giống. Truy vấn `findByNameContaining` đơn giản khó đáp ứng đồng thời phân tích từ, xếp hạng mức phù hợp và các điều kiện phức hợp.

## 2. Search index là gì và khác các index khác ra sao?

MongoDB Search sử dụng một chỉ mục chuyên cho tìm kiếm, tổ chức các **term/token** được trích từ nội dung tài liệu để phục vụ truy vấn từ khóa và xếp hạng mức liên quan. Chỉ mục Search được quản lý riêng với các chỉ mục thông thường của collection.

| Cơ chế | Dùng khi | Điểm khác biệt |
| --- | --- | --- |
| Chỉ mục B-tree tạo bởi `createIndex` hoặc `@Indexed` | Lọc bằng, so sánh khoảng, sắp xếp theo trường | Không tự cung cấp pipeline phân tích ngôn ngữ và chấm điểm tìm kiếm toàn văn |
| Text index của MongoDB (`createIndex({name: "text"})`, `@TextIndexed`) | Tìm từ khóa toàn văn cơ bản qua `$text` | API và khả năng cấu hình khác MongoDB Search; không dùng cho `$search` |
| **MongoDB Search index** (loại `search`) | Toàn văn, fuzzy, phrase, autocomplete, highlight, facet, relevance | Dùng `$search` / `$searchMeta`; cần môi trường Search được hỗ trợ |
| Vector Search index (loại `vectorSearch`) | Tìm tài liệu gần nhau theo embedding | Dùng `$vectorSearch` và cấu hình vector riêng; không thay thế Search index từ khóa |

**Điểm cần nhớ:** tạo một text index bằng `@TextIndexed` không làm cho `$search` hoạt động. Tương tự, gọi `mongoTemplate.indexOps(...)` để tạo chỉ mục B-tree không đồng nghĩa với tạo Search index.

### Ba phần của Search index

- **Định nghĩa index:** tên, `mappings` và các tùy chọn liên quan.
- **Field mapping:** đường dẫn dữ liệu, kiểu tìm kiếm (`string`, `token`, `number`, `boolean`, `date`, `autocomplete`, ...), cho phép các toán tử tương ứng.
- **Analyzer:** quy tắc chuyển văn bản thành token ở thời điểm lập chỉ mục và ở thời điểm tìm.

Luồng xử lý có thể hình dung:

```text
Document trong collection
    └─> mapping theo field ──> analyzer ──> token trong Search index
                                                    │
Người dùng nhập query ──> searchAnalyzer ──> token ─┘
                                                    ↓
                                        $search: so khớp và tính điểm
                                                    ↓
                                      $project / $limit / DTO
```

## 3. Thiết kế mapping: dynamic hay static?

Một định nghĩa tối giản có thể bật dynamic mapping:

```javascript
db.products.createSearchIndex("products_dynamic", {
  mappings: { dynamic: true }
});
```

Khi `dynamic: true`, Search tự ánh xạ những kiểu trường có thể lập chỉ mục. Cách này thuận tiện để thử nghiệm nhưng có thể lập chỉ mục cả các trường không phục vụ truy vấn, làm tăng kích thước, tài nguyên và rủi ro thay đổi hành vi khi schema document biến động.

Trong ứng dụng thực tế, thường bắt đầu từ `dynamic: false` và liệt kê trường cần tìm:

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      name: { type: "string" },
      description: { type: "string" },
      category: { type: "token" },
      price: { type: "number" },
      available: { type: "boolean" }
    }
  }
}
```

Ý nghĩa các lựa chọn:

- `string` phù hợp với tìm toàn văn theo token và mức liên quan.
- `token` phù hợp với giá trị phân loại cần khớp chính xác, như mã nhóm hoặc mã tenant.
- `number`, `date` phục vụ lọc hoặc truy vấn theo khoảng khi toán tử hỗ trợ.
- `boolean` phục vụ điều kiện đúng/sai.
- `autocomplete` dành cho gợi ý khi đang nhập, dùng cấu hình và toán tử riêng.

`dynamic: false` giúp kiểm soát schema tìm kiếm. Đổi tên trường trong document hoặc trong annotation `@Field` có thể khiến truy vấn không còn khớp đường dẫn đã lập chỉ mục; phải đánh giá lại cả index definition và câu lệnh `$search`.

## 4. Analyzer hoạt động như thế nào?

Một **analyzer** biến chuỗi thành các token có thể so khớp. Với analyzer tùy chỉnh, quá trình thường gồm:

1. `charFilters` (tùy chọn): biến đổi văn bản đầu vào trước khi tách token.
2. `tokenizer`: chia văn bản thành token, ví dụ theo ranh giới từ.
3. `tokenFilters` (tùy chọn): viết thường, loại stop word, stemming, chuẩn hóa dấu hoặc sinh n-gram.

Ví dụ đơn giản: “Bàn Phím Cơ” có thể được tách thành các token theo từ, rồi chuyển về chữ thường. Quy tắc tách từ phụ thuộc tokenizer; **tokenizer chuẩn không phải bộ tách từ tiếng Việt theo ngữ nghĩa**, vì vậy không nên kỳ vọng tự hiểu mọi từ ghép nhiều âm tiết.

### `analyzer` và `searchAnalyzer`

- `analyzer` chạy khi lập chỉ mục dữ liệu từ document.
- `searchAnalyzer` chạy khi xử lý văn bản truy vấn, đặc biệt đối với toán tử `text`.
- Nếu không khai báo `searchAnalyzer`, Search thường dùng cùng analyzer của trường; nếu không khai báo cả hai thì dùng analyzer chuẩn mặc định.

Hai phía phải tạo ra token tương thích. Chẳng hạn, index có chuẩn hóa dấu nhưng query giữ nguyên chuỗi theo một quy tắc quá khác có thể giảm recall. Ngược lại, analyzer tách quá nhiều token thường mang lại kết quả nhiễu.

| Analyzer / kỹ thuật | Phù hợp | Lưu ý |
| --- | --- | --- |
| Chuẩn (`lucene.standard`) | Tìm kiếm từ thông thường | Không tự xử lý toàn bộ nhu cầu ngôn ngữ tiếng Việt |
| Keyword (`lucene.keyword`) | Một chuỗi như một token | Không phù hợp để tìm từng từ trong đoạn dài |
| Lowercase | Không phân biệt hoa/thường | Là token filter trong custom analyzer |
| `asciiFolding` hoặc `icuFolding` | Thử chuẩn hóa dấu/ký tự Unicode | Kiểm thử với tập dữ liệu tiếng Việt, đặc biệt các ký tự và dấu đặc thù |
| N-gram, edge-gram hoặc `autocomplete` mapping | Gợi ý theo tiền tố/chuỗi con | Có chi phí chỉ mục và đánh đổi chất lượng riêng; không mặc nhiên giống tìm toàn văn |

### Ví dụ custom analyzer cho tiếng Việt

Một cách tiếp cận thực dụng là dùng tokenizer `standard`, chuyển thành chữ thường và thử `asciiFolding`. Trong ví dụ sau, `originalTokens: "include"` giữ token gốc song song với bản được chuyển đổi (khi có thể):

```javascript
{
  analyzers: [
    {
      name: "vi_fold",
      tokenizer: { type: "standard" },
      tokenFilters: [
        { type: "lowercase" },
        { type: "asciiFolding", originalTokens: "include" }
      ]
    }
  ],
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      },
      description: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      }
    }
  }
}
```

Đây là **cấu hình minh họa**, không phải lời bảo đảm tìm kiếm tiếng Việt không dấu luôn đạt chất lượng mong muốn. Cần đối chiếu token và kết quả thực tế cho các cặp như “bàn/ban”, “điện/dien”, “máy/may”, tên thương hiệu có dấu và cụm từ nhiều âm tiết. Khi cần tách từ tiếng Việt chuyên sâu, phải khảo sát phương án xử lý ngôn ngữ và khả năng analyzer được môi trường hỗ trợ.

## 5. Ví dụ đầy đủ trong `mongosh`

Các lệnh sau cần được chạy trên môi trường đã hỗ trợ MongoDB Search, bằng tài khoản có quyền tạo Search index. Chọn database thực hành:

```javascript
use shop_demo

db.products.insertMany([
  {
    _id: 1,
    name: "Bàn phím cơ không dây",
    description: "Bàn phím gõ êm cho văn phòng",
    category: "keyboard",
    price: 1250000,
    available: true
  },
  {
    _id: 2,
    name: "Chuột không dây",
    description: "Chuột dùng cho văn phòng",
    category: "mouse",
    price: 550000,
    available: true
  },
  {
    _id: 3,
    name: "Bàn phím cơ có dây",
    description: "Bàn phím cho gaming",
    category: "keyboard",
    price: 890000,
    available: false
  }
]);
```

Tạo Search index tên `products_text_v1`. Tên index do ứng dụng chỉ định; không phụ thuộc vào `_id` hay tên một chỉ mục B-tree.

```javascript
db.products.createSearchIndex("products_text_v1", {
  analyzers: [
    {
      name: "vi_fold",
      tokenizer: { type: "standard" },
      tokenFilters: [
        { type: "lowercase" },
        { type: "asciiFolding", originalTokens: "include" }
      ]
    }
  ],
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      },
      description: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      },
      category: { type: "token" },
      price: { type: "number" },
      available: { type: "boolean" }
    }
  }
});
```

**Tạo index là thao tác bất đồng bộ.** Lệnh trả về không có nghĩa toàn bộ dữ liệu đã sẵn sàng để tìm. Kiểm tra:

```javascript
db.products.getSearchIndexes("products_text_v1");
```

Xem `status` và `queryable` của kết quả. Trạng thái `READY` cho biết index có thể phục vụ truy vấn; `BUILDING` có thể chưa queryable đối với index mới. Trạng thái `FAILED` cần kiểm tra lỗi cấu hình; `STALE` cảnh báo index có thể trả về dữ liệu cũ. Lệnh `getIndexes()` thông thường không liệt kê Search index.

### Tìm toàn văn kèm điều kiện lọc

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        must: [
          {
            text: {
              query: "bàn phím",
              path: ["name", "description"]
            }
          }
        ],
        filter: [
          { equals: { path: "category", value: "keyboard" } },
          { equals: { path: "available", value: true } },
          { range: { path: "price", lte: 1500000 } }
        ]
      }
    }
  },
  {
    $project: {
      name: 1,
      description: 1,
      price: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
```

Giải thích:

- `text` truy vấn trường văn bản đã lập chỉ mục; `path` phải trùng tên field lưu trong MongoDB.
- `compound.must` yêu cầu điều kiện tìm kiếm; `compound.filter` dùng điều kiện lọc mà không trực tiếp cộng điểm liên quan.
- `score` lấy từ metadata `searchScore` để quan sát thứ tự phù hợp; điểm này không phải xác suất và không có thang cố định giữa các cấu hình khác nhau.
- `$search` phải đứng đầu pipeline mà nó xuất hiện. Sau đó có thể dùng `$project`, `$limit` và các aggregation stage phù hợp.

Với dữ liệu mẫu, mục tiêu là trả về sản phẩm bàn phím còn bán, có giá không quá 1.500.000. Kết quả thực tế phụ thuộc việc index đã `READY` và cách analyzer sinh token.

### Khi nào dùng `$searchMeta`?

`$searchMeta` trả metadata như số lượng kết quả hoặc facet thay vì danh sách document phù hợp. Ví dụ đếm tổng số sản phẩm có tên chứa từ cần tìm:

```javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_text_v1",
      text: { query: "bàn phím", path: "name" },
      count: { type: "total" }
    }
  }
]);
```

Cân nhắc chi phí của đếm chính xác đối với tập dữ liệu lớn; trong một số tình huống có thể dùng lower bound. `$searchMeta` cũng phải là stage đầu tiên trong pipeline của nó.

### Tìm gợi ý lúc đang nhập

Nếu yêu cầu là gợi ý tên khi người dùng nhập từng ký tự, lập một index `autocomplete` riêng thay vì kỳ vọng analyzer toàn văn tự xử lý hành vi này:

```javascript
db.products.createSearchIndex("products_suggest_v1", {
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "autocomplete",
        tokenization: "edgeGram",
        minGrams: 2,
        maxGrams: 15
      }
    }
  }
});

db.products.aggregate([
  {
    $search: {
      index: "products_suggest_v1",
      autocomplete: { path: "name", query: "bàn ph" }
    }
  },
  { $limit: 5 }
]);
```

Với autocomplete, cần thiết kế lại cách xử lý dấu, độ dài tiền tố và cách xếp hạng theo dữ liệu người dùng. Có thể thử mapping đa cách cho cùng field khi cần phục vụ cả `text` lẫn `autocomplete`.

## 6. Gọi Search bằng Spring Data MongoDB

`MongoTemplate` có thể thực thi aggregation chứa stage `$search`. Việc dùng `Document` giúp ứng dụng truyền biểu thức MongoDB Search khi API cấp cao của Spring Data chưa bao phủ hết toán tử cần dùng.

Ví dụ service sau tạo một Search stage có tham số từ người dùng, thêm điểm liên quan và giới hạn số dòng. Giả định collection lưu đúng các tên trường `name`, `description` và `available` như ví dụ phía trên.

```java
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final MongoTemplate mongoTemplate;

    public ProductSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> searchProducts(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return List.of();
        }

        String query = keyword.trim();

        Document text = new Document("text",
                new Document("query", query)
                        .append("path", List.of("name", "description")));

        Document available = new Document("equals",
                new Document("path", "available")
                        .append("value", true));

        Document compound = new Document("must", List.of(text))
                .append("filter", List.of(available));

        AggregationOperation searchStage = context ->
                new Document("$search",
                        new Document("index", "products_text_v1")
                                .append("compound", compound));

        AggregationOperation projectStage = context ->
                new Document("$project",
                        new Document("name", 1)
                                .append("description", 1)
                                .append("price", 1)
                                .append("score",
                                        new Document("$meta", "searchScore")));

        Aggregation pipeline = Aggregation.newAggregation(
                searchStage,
                projectStage,
                Aggregation.limit(10)
        );

        return mongoTemplate
                .aggregate(pipeline, "products", Document.class)
                .getMappedResults();
    }
}
```

**Lưu ý khi tích hợp:**

- `MongoTemplate` vẫn đi qua MongoDB Java Driver và cần connection string, quyền, SSL/TLS và môi trường hỗ trợ Search phù hợp.
- Đoạn `Document` trên biểu diễn **tên field thực trong collection**. Nếu entity dùng `@Field("product_name")` thì phải sửa `path` và projection tương ứng; không giả định mọi chuỗi trong raw stage đều được Spring ánh xạ lại.
- Giới hạn kích thước chuỗi truy vấn, giới hạn kết quả, kiểm tra quyền người dùng và loại bỏ trường nhạy cảm trước khi trả API. Không ghép JSON thủ công bằng chuỗi nối từ dữ liệu người dùng.
- Nếu muốn ánh xạ sang DTO, có thể dùng `AggregationResults<YourDto>` sau khi xác nhận kiểu `_id` và field projection khớp constructor/mapper.
- Tùy phiên bản, Spring Data cung cấp `SearchIndexOperations` để quản lý một số loại Search index. Hãy kiểm tra API tương ứng với phiên bản dependency; ví dụ dùng `mongosh` để khai báo index đầy đủ giúp tách hạ tầng khỏi quá trình đọc dữ liệu.
- Repository `MongoRepository` hỗ trợ truy vấn CRUD rất tốt, nhưng method suy diễn tên như `findByNameContaining` không tự biến thành toán tử `$search`. Dùng custom repository hoặc service với `MongoTemplate` khi cần pipeline Search.

## 7. Điều kiện hỗ trợ theo môi trường triển khai

**Không thể suy ra Search có sẵn chỉ từ việc kết nối MongoDB thành công.** Phải xác nhận loại triển khai, phiên bản server, dịch vụ/chương trình Search và quyền quản lý index.

| Môi trường | Có thể dùng MongoDB Search? | Điều kiện cần kiểm tra |
| --- | --- | --- |
| MongoDB Atlas Free / Flex | Có, cho thử nghiệm theo giới hạn từng loại cluster | Cluster hoạt động, Search index được tạo, phiên bản và tài nguyên đáp ứng chức năng đang dùng |
| MongoDB Atlas Dedicated | Có, phù hợp nhu cầu vận hành lớn hơn | Search index, cấu hình/chi phí tài nguyên, Search Nodes nếu dùng, phân quyền và giám sát |
| Atlas local deployment | Có trong các lựa chọn local được MongoDB cung cấp | Dùng đúng bản phân phối/cấu hình local hỗ trợ Search; không đánh đồng với một tiến trình `mongod` bất kỳ |
| MongoDB Community self-managed | Có ở các phiên bản/phần triển khai hỗ trợ MongoDB Search (bắt đầu được giới thiệu từ 8.2) | Cần cấu hình thành phần Search (`mongot`), hệ điều hành và cặp phiên bản tương thích; tài liệu hiện hành yêu cầu kiểm tra bảng compatibility |
| MongoDB Enterprise self-managed | Có với topology/phiên bản được tài liệu hỗ trợ, gồm phương án điều phối bằng Kubernetes | Điều kiện về MongoDB Server, `mongot`, operator, quyền và topology; không mặc định mọi máy Enterprise đều sẵn Search |
| MongoDB cũ hoặc local chỉ có `mongod` không cấu hình Search | Không thể mặc nhiên dùng `$search` | Cần chuyển sang môi trường được hỗ trợ hoặc cân nhắc `$text` / truy vấn khác tùy yêu cầu |

**Về self-managed:** khả năng Search đã mở rộng sang Community từ nhánh MongoDB 8.2, nhưng việc **được giới thiệu trong một phiên bản** khác với một tổ hợp phiên bản **còn nằm trong danh sách hỗ trợ hiện tại**. Tại thời điểm soạn, tài liệu tương thích của MongoDB Search mô tả các cặp MongoDB Server và `mongot` cụ thể, yêu cầu cho bản mới hơn và giới hạn nền tảng. Trước khi triển khai production, đối chiếu trực tiếp trang [Compatibility and Requirements for mongot](https://www.mongodb.com/docs/search/self-managed/current/deployment/compatibility-requirements/) thay vì chỉ kiểm tra `db.version()`.

Đối với Community self-managed, tài liệu sản phẩm nêu các hệ Linux được hỗ trợ và các hình thức triển khai tương ứng; không nên coi MongoDB Community chạy trực tiếp trên Windows hoặc macOS là môi trường hỗ trợ Search self-managed tương đương. Khi phát triển trên những máy này, cân nhắc Atlas hoặc môi trường Linux/container được tài liệu cho phép.

### Checklist trước khi bật tính năng

1. **Server và Search:** ghi nhận Atlas tier hoặc bản MongoDB Server, `mongot`, topology và hệ điều hành được hỗ trợ.
2. **Kết nối:** ứng dụng truy cập được database/collection đúng, dùng TLS và cấu hình xác thực phù hợp.
3. **Quyền:** tài khoản triển khai có `createSearchIndexes`, `updateSearchIndex`, `listSearchIndexes` khi cần; tài khoản chỉ đọc/ứng dụng runtime có quyền đọc và thực thi truy vấn tương ứng. Ví dụ role `readWrite` thường đủ để quản lý index trên phạm vi collection phù hợp.
4. **Sẵn sàng:** định nghĩa Search index đúng collection, đã `READY` và `queryable: true`.
5. **Phiên bản client:** `mongosh`, Java Driver và Spring Data MongoDB hỗ trợ các lệnh/API ứng dụng thực tế dùng; không suy ra hỗ trợ toàn bộ Search từ một annotation đơn lẻ.
6. **Giới hạn và chi phí:** thử dữ liệu thật, đo kích thước index, CPU/RAM, tốc độ lập chỉ mục, độ trễ tìm kiếm và các giới hạn của tier.

Nếu không đáp ứng điều kiện Search, ứng dụng có thể chọn luồng tìm kiếm dự phòng có chủ đích bằng `$text` hoặc truy vấn thường; cần kiểm thử khác biệt về cú pháp, mức liên quan và tính năng. Không được âm thầm giả định kết quả hai cơ chế tương đương.

## 8. Vận hành, cập nhật index và hiệu năng

### Tạo và cập nhật index là bất đồng bộ

Sau khi tạo hoặc thay đổi index, hệ thống cần thời gian xây dựng lại cấu trúc Search. Khi cập nhật index đang tồn tại, có thể còn dùng định nghĩa cũ trong khi xây dựng định nghĩa mới. Trạng thái thường gặp:

| Trạng thái | Cách hiểu và hành động |
| --- | --- |
| `PENDING` | Chưa bắt đầu xây dựng; chưa truy vấn được index mới |
| `BUILDING` | Đang tạo hoặc xây dựng lại; kiểm tra `queryable` trước khi dùng |
| `READY` | Index sẵn sàng phục vụ truy vấn |
| `FAILED` | Kiểm tra định nghĩa, trường và thông tin lỗi |
| `STALE` | Có thể truy vấn nhưng dữ liệu Search có nguy cơ trễ so với collection |
| `DELETING` / `DOES_NOT_EXIST` | Không dùng index này cho truy vấn |

**Tính nhất quán:** Search index được đồng bộ từ dữ liệu nguồn nhưng không nên dùng kết quả tìm kiếm như bảo đảm read-after-write tuyệt đối ngay sau một ghi dữ liệu. Nếu nghiệp vụ cần xác nhận giao dịch hoặc quyền truy cập tức thì, đọc lại document nguồn bằng truy vấn thích hợp.

### Giảm chi phí và tăng chất lượng

- Chọn `dynamic: false` cho schema ổn định; lập chỉ mục đúng field và đúng kiểu truy vấn.
- Dùng `compound.filter` cho lọc bắt buộc, để tránh tác động không cần thiết vào relevance score.
- Giới hạn số bản ghi, phân trang với cơ chế MongoDB Search hỗ trợ; tránh lấy toàn bộ kết quả rồi phân trang trong Java.
- Cẩn trọng với fuzzy, wildcard, nhiều gram và index trên mô tả dài; đo latency p50/p95 với truy vấn thực tế.
- Khi thay đổi analyzer, tokenization hoặc mapping, lên kế hoạch xây dựng lại index và thử phiên bản index mới (`_v2`) trước khi đổi tên index trong cấu hình ứng dụng.
- Theo dõi index status, lỗi truy vấn, tài nguyên Search node/`mongot`, chênh lệch thời điểm ghi và thời điểm tìm thấy tài liệu.
- Với dữ liệu nhiều tenant, luôn áp dụng ràng buộc tenant và quyền từ backend. Có thể lập chỉ mục `tenantId` kiểu `token` để lọc trong `$search.compound.filter`, đồng thời kiểm tra quyền trước khi trả dữ liệu.

## 9. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xác minh / hướng xử lý |
| --- | --- | --- |
| Lỗi `$search` không được hỗ trợ | Đang chạy MongoDB không có Search hoặc topology sai | Kiểm tra loại deployment, phiên bản và thành phần Search |
| Tạo index thành công nhưng không có kết quả | Index đang `BUILDING`, tên index sai hoặc field chưa được mapping | Gọi `getSearchIndexes(...)`, so sánh `index` và `path` |
| Query có dấu được, không dấu không được | Analyzer/tokenization chưa chuẩn hóa như kỳ vọng | Thử các cặp dấu, kiểm tra analyzer hai phía, đo precision/recall |
| Kết quả quá rộng hoặc thứ tự khó hiểu | Analyzer tách token quá rộng, điều kiện nằm trong `should` hoặc score bị ảnh hưởng | Kiểm tra `must` / `filter`, thuật toán relevance và dữ liệu mẫu |
| Lọc theo category không khớp | Field không phải kiểu tương thích với `equals` hoặc giá trị sai | Kiểm tra mapping `token` và giá trị lưu trữ |
| Không thấy Search index trong `getIndexes()` | Search index không nằm trong danh sách index thường | Dùng `getSearchIndexes()` hoặc `$listSearchIndexes` |
| Search index cũ sau khi sửa cấu hình | Quá trình rebuild chưa xong | Quan sát trạng thái, chờ `READY` rồi mới đối chiếu kết quả |
| Lỗi quyền khi tạo/cập nhật | Database user thiếu privilege quản lý Search index | Kiểm tra role cho database/collection và cơ chế triển khai |
| Latency tăng mạnh | Quá nhiều trường, n-gram/fuzzy, kết quả quá lớn, tài nguyên Search thiếu | Thu gọn mapping, đo truy vấn, áp giới hạn và đánh giá tài nguyên |

## 10. Bài thực hành tự kiểm tra

**Nhiệm vụ A — Mapping:** bổ sung trường `brand` vào collection sản phẩm. Thiết kế một mapping `token` nếu cần lọc thương hiệu đúng mã, và cân nhắc thêm mapping `string` riêng nếu muốn tìm kiếm thương hiệu theo từ khóa. Giải thích vì sao chọn hai kiểu truy vấn khác nhau.

**Nhiệm vụ B — Analyzer:** tạo một phiên bản index dùng `lucene.standard` và một phiên bản dùng `vi_fold`. Với ít nhất 20 sản phẩm, thử các chuỗi có dấu/không dấu, tên viết hoa, tên ghép và lỗi gõ. Ghi lại số kết quả đúng, sai và latency. Không kết luận analyzer nào tốt hơn chỉ từ một ví dụ.

**Nhiệm vụ C — Spring Data:** mở rộng service để nhận `category`, `maxPrice` và `limit`. Kiểm tra giá trị đầu vào, giới hạn `limit` ở ngưỡng hợp lý và sử dụng `compound.filter`. Kiểm thử bằng integration test trên môi trường Search thật hoặc môi trường local được tài liệu hỗ trợ. Một MongoDB container thông thường chưa cài Search không đủ để kiểm thử `$search`.

**Nhiệm vụ D — Triển khai:** lập bảng ghi Atlas tier hoặc MongoDB Server/`mongot` version, hệ điều hành, quyền database, index name, trạng thái index và kết quả truy vấn thử. Nếu một điều kiện không đạt, ghi rõ tác động đến chức năng tìm kiếm trước khi bật feature flag.

**Tiêu chí hoàn thành:** có định nghĩa Search index cụ thể, giải thích được analyzer dùng lúc index và query, chạy được `$search` qua `MongoTemplate`, đồng thời chứng minh đã kiểm tra môi trường và trạng thái `READY`.

## 11. Tài liệu chính thức

- [MongoDB Search — Index Reference](https://www.mongodb.com/docs/search/indexes/index-definitions/): `mappings`, analyzer và các tùy chọn định nghĩa.
- [MongoDB Search — Token Filters](https://www.mongodb.com/docs/search/indexes/analyzers/token-filters/): `lowercase`, `asciiFolding`, `icuFolding`.
- [MongoDB — `$search`](https://www.mongodb.com/docs/search/query/aggregation-stages/search/): cú pháp, giới hạn pipeline và score.
- [MongoDB — `$searchMeta`](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/): metadata, count và facet.
- [MongoDB — Manage Search Indexes](https://www.mongodb.com/docs/search/indexes/manage-indexes/): tạo, sửa, liệt kê và trạng thái Search index.
- [MongoDB Search — Deployment Options](https://www.mongodb.com/docs/search/deployment/deployment-options/): cách thử nghiệm với Atlas và local.
- [MongoDB Search Self-Managed — Compatibility Requirements](https://www.mongodb.com/docs/search/self-managed/current/deployment/compatibility-requirements/): đối chiếu điều kiện hỗ trợ theo phiên bản.
- [Spring Data MongoDB — MongoDB Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mongo-search-indexes.html): API quản lý/search index theo phiên bản Spring Data đang dùng.

> Ghi nhớ: danh sách phiên bản, tier, phần mềm điều phối và giới hạn Search thay đổi theo thời gian. Luôn kiểm tra trang compatibility hiện hành khi triển khai, đặc biệt với self-managed.
