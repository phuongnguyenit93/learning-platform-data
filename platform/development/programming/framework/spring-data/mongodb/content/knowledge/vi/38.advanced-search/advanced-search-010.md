# Phân biệt khả năng của MongoDB Server, dịch vụ Search và API Spring Data

> **Chương:** Tìm kiếm nâng cao  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository. Thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Tách bạch **năng lực của MongoDB Database Server (mongod/mongos)**, **dịch vụ MongoDB Search/Vector Search (mongot)** và **API Spring Data MongoDB**; xác định đúng feature theo deployment/version; thiết kế truy vấn exact/range, `$regex`, `$text`, `$search`, `$searchMeta`, `$vectorSearch`; sử dụng `MongoTemplate`, repository và aggregation đúng contract; tổ chức Search index, score, phân trang, tenant filter, consistency, test và fallback một cách có kiểm chứng.

## 1. Ba lớp thường bị gộp làm một

Trong một ứng dụng Java dùng Spring Data MongoDB, developer có thể viết:

~~~java
mongoTemplate.aggregate(aggregation, ProductDocument.class, SearchHit.class);
~~~

Nhưng câu lệnh Java **không tự chứng minh** cluster có khả năng chạy mọi aggregation stage được gửi. Phải phân biệt:

1. **MongoDB Database Server**: chạy CRUD, aggregation phổ thông, query planner và các index B-tree/text/2dsphere/hashed/wildcard theo tính năng của phiên bản server.
2. **MongoDB Search / MongoDB Vector Search service**: một công cụ tìm kiếm/chỉ mục riêng (`mongot`) cung cấp lexical search, relevance, autocomplete, fuzzy, facets, semantic vector search… khi deployment đã triển khai và hỗ trợ.
3. **Spring Data MongoDB / Java Driver**: API phía client để tạo BSON query, quản lý search indexes và gửi command/aggregation tới server; hỗ trợ type mapping, repositories, reactive và tiện ích truy vấn, **không thay thế công cụ server-side**.

~~~mermaid
flowchart LR
    U["UI / HTTP API"] --> A["Spring service"]
    A --> D["Spring Data MongoDB / Java Driver"]
    D --> M["mongod / mongos"]
    M --> I["Database indexes: B-tree, text, geo..."]
    M -->|"Search stages khi có capability"| S["mongot / MongoDB Search"]
    S --> SI["Search / Vector indexes"]
    M --> C["Current documents"]
    S -. "Đồng bộ từ dữ liệu DB; có độ trễ index" .- C
~~~

**Điểm cốt lõi:** Spring Data có thể biểu diễn một `$search` stage thành BSON hợp lệ, nhưng MongoDB deployment thiếu Search service/index tương ứng vẫn không thực thi được. Tương tự, cài thư viện tìm kiếm/vector ở Java không có nghĩa mongod tự sinh các chỉ mục Search.

### 1.1. Sổ tay phân biệt nhanh

| Câu hỏi | Lớp quyết định |
| --- | --- |
| Có hỗ trợ `find({sku:"X"})` với B-tree index không? | MongoDB Server, index/plan |
| `$text` có dùng text index của collection không? | MongoDB Server, text index |
| Có chạy được `$search`, fuzzy/autocomplete/highlight không? | Search service + index + phiên bản/deployment |
| Có chạy được `$vectorSearch` và pre-filter vector không? | Vector Search service/index + phiên bản/deployment |
| Java có class `VectorSearchOperation` không? | Phiên bản Spring Data MongoDB |
| Query có đúng tên BSON field từ `@Field` không? | Mapping của Spring Data và cách xây BSON |
| Khi index mới tạo, tìm ngay thấy document chưa? | Search index synchronization/readiness |
| AI embedding có đúng kích thước và mô hình không? | Embedding pipeline, vector index, query input |
| Ai được nhìn thấy document của tenant khác? | Business authorization **và** điều kiện filter được thực thi tại search engine |

## 2. MongoDB Server và Search service không phải một index engine

### 2.1. Database query engine

Các cú pháp điển hình:

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  active: true,
  category: "laptop",
  price_vnd: { $gte: 10000000, $lte: 30000000 }
});
~~~

MongoDB Server có thể thực hiện query này bằng index phù hợp:

~~~javascript
db.catalog_advanced_010.createIndex(
  { tenant_id: 1, active: 1, category: 1, price_vnd: 1 },
  { name: "ix_catalog_tenant_active_cat_price" }
);
~~~

Đây là **database index**, không phải Search index. Tương tự, Server có `$regex` và `$text`, nhưng khả năng xử lý từ vựng, relevance và ranking **không đồng nhất** với một dịch vụ search chuyên dụng.

### 2.2. Search service

MongoDB Search dùng tiến trình `mongot` (xây trên Apache Lucene), đồng bộ thông tin chỉ mục từ dữ liệu MongoDB và xử lý `$search`/`$searchMeta`. MongoDB Vector Search dùng cơ chế Search để xử lý `$vectorSearch` trên vector indexes. Client vẫn gửi aggregation qua database endpoint: ứng dụng **không kết nối trực tiếp vào mongot**.

Các khả năng thường gắn với Search service:

- Analyzer/tokenization/ngôn ngữ, autocomplete, phrase, fuzzy, wildcard/regex trong **Search DSL**.
- Relevance scoring và các cơ chế score boosting/compound scoring.
- Highlight và search metadata/facets.
- Vector similarity/approximate nearest neighbors (ANN), exact nearest neighbors (ENN) khi phiên bản hỗ trợ.
- Search-index mappings riêng, status/build lifecycle riêng.

**Không suy** rằng một `createIndex({title:"text"})` tạo MongoDB Search index hoặc rằng `createSearchIndex(...)` tạo B-tree index.

### 2.3. Khác nhau về cập nhật chỉ mục

~~~text
MongoDB write acknowledged
        |
        +-- Database index được bảo trì theo đường ghi DB
        |
        +-- Search service đồng bộ từ dữ liệu mongod
                 -> thay đổi có thể xuất hiện muộn hơn trong Search results
~~~

Do đó, câu “vừa insert xong, `findById` thấy nhưng `$search` chưa thấy” **không tự chứng minh ứng dụng lỗi**. Cần kiểm Search index đang READY, mapping đúng, và Search indexing lag. Không xây quy tắc read-after-write nghiêm ngặt bằng cách mặc nhiên trông chờ Search index cập nhật tức thì.

## 3. Năng lực phụ thuộc **deployment và version**, không chỉ URI

Tên gọi đã phát triển: tài liệu cũ thường nói **Atlas Search/Atlas Vector Search**, còn tài liệu MongoDB hiện hành nói **MongoDB Search/MongoDB Vector Search** và mô tả thêm các deployment self-managed được hỗ trợ.

### 3.1. Ma trận triển khai cần nhớ

| Môi trường | CRUD/B-tree/`$text` | `$search`/`$searchMeta` | `$vectorSearch` | Yêu cầu kiểm thêm |
| --- | --- | --- | --- | --- |
| MongoDB Atlas cluster có Search được cấu hình | Có | Có khi Search index/service phù hợp | Có khi Vector index/service phù hợp | Cluster tier/region/version, index READY, quyền |
| MongoDB Community self-managed **trước 8.2** thông thường | Có | Không mặc nhiên hỗ trợ Search service | Không mặc nhiên hỗ trợ Vector Search service | Không coi `mongo:7/8.0` standalone là Atlas |
| MongoDB Community **8.2+** theo đường self-managed Search được hỗ trợ | Có | Có khi triển khai/configure `mongot` đúng | Có khi index/feature đúng | Kiểm guide self-managed, version/edition, resource |
| MongoDB Enterprise **8.2+** với Kubernetes Operator theo tài liệu hỗ trợ | Có | Có theo setup được hỗ trợ | Có theo setup được hỗ trợ | Kiểm operator, topology, điều kiện license/support |
| `mongodb-atlas-local` dành cho thử nghiệm | Có | Có theo image/config được cung cấp | Có theo image/config được cung cấp | Image dành phát triển, **không production HA** |

**Lưu ý quan trọng:** Các điều kiện trong bảng dựa trên tài liệu MongoDB hiện hành tại thời điểm soạn bài. Chúng **không khẳng định** “mọi Community 8.2+ chỉ cần nâng phiên bản mongod là có Search”. Self-managed Search cần triển khai/vận hành `mongot` theo hướng dẫn; các tính năng cụ thể có compatibility/limitations riêng. Ngoài ra một số tài liệu API Spring Data dùng diễn đạt “Atlas-only” từ trước khi MongoDB mở rộng self-managed; hãy kiểm đối chiếu **server docs + Spring Data version** thay vì suy luận từ một câu Javadoc.

### 3.2. Các version gate khác nhau

- `$search`, `$searchMeta`: yêu cầu Search deployment và Search index.
- `$vectorSearch`: yêu cầu môi trường/version Search + vector index, thông số vector/filter phù hợp.
- API `VectorSearchOperation` trong Spring Data được bổ sung ở dòng phiên bản mới hơn các API `TextQuery` cổ điển; **không** dùng code class đó với Spring Data cũ mà không kiểm dependencies.
- Repository `@VectorSearch`/`Vector`/`SearchResults<T>` là API của các phiên bản Spring Data mới; code sample từ tài liệu `current` không chắc compile với phiên bản project.
- Một số tính năng hybrid/fusion/pagination có version và index constraints riêng; nên feature detect/test ở môi trường đích.

### 3.3. Kiểm chứng deployment thay vì đoán

Trong `mongosh` trên một environment được phép:

~~~javascript
db.adminCommand({ buildInfo: 1 }).version;
db.adminCommand({ hello: 1 });

// Chỉ trên collection cụ thể và khi có quyền:
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: {} }
]);
~~~

`buildInfo` cho biết phiên bản mongod, **không bảo đảm mongot đã sẵn sàng**. `$listSearchIndexes` là bước kiểm index/status hữu ích khi deployment hỗ trợ Search; lệnh này có thể fail trên môi trường không có feature/quyền tương ứng. Không tự động coi lỗi `Unauthorized`, `Unknown pipeline stage` và `index not found` là cùng một nguyên nhân.

### 3.4. Capability checklist ngắn

1. MongoDB server version/edition/topology?
2. Search process/service được triển khai và healthy?
3. Có Search/Vector index đúng **collection, name, type, path**?
4. Index đã READY hay còn BUILDING/STALE?
5. Java Driver/Spring Data version có API cần dùng?
6. Query DSL và BSON fields đúng mapping?
7. Auth/tenant filter có được áp ở search stage?
8. Đã integration test với môi trường đại diện?

## 4. Chọn engine theo nhu cầu, không chọn theo cú pháp đẹp

| Nhu cầu | Phương án ưu tiên | Tại sao |
| --- | --- | --- |
| Tra cứu `_id`, SKU, email canonical | Database exact match + B-tree | Chính xác, index phù hợp |
| Filter ngày, giá, trạng thái và sort | Database query/aggregation + compound index | Không cần Search engine |
| Tiền tố mã SKU giới hạn | Anchored `$regex` hoặc search prefix theo yêu cầu index/collation | Simple prefix có thể đủ |
| Tìm nhiều từ trong title/description cơ bản | Database `$text` + text index nếu phù hợp | Cơ chế có sẵn, tính năng giới hạn |
| Autocomplete, fuzzy typo, analyzer/ngôn ngữ, highlight | MongoDB Search `$search` | Search-specific index/operator |
| Facet theo category/brand từ kết quả tìm kiếm | `$searchMeta` facet hoặc `$search` + metadata | Search facet semantics |
| “Sản phẩm tương tự về nghĩa” với embedding | MongoDB Vector Search `$vectorSearch` | Truy vấn vector similarity |
| Kết hợp keyword relevance và vector relevance | Search/hybrid/fusion theo feature version; hoặc fusion ở app | Ranking needs; kiểm capability |
| Ghi order, transaction, optimistic locking | MongoDB Server + Spring Data CRUD/tx | Không giải bằng Search index |
| Kết quả phải thấy ngay sau một write quan trọng | Query DB chính theo ID/status hoặc thiết kế freshness rõ | Search indexing có độ trễ |

### 4.1. Một quy trình quyết định

~~~mermaid
flowchart TD
    A["Yêu cầu tìm kiếm"] --> B{"Đúng mã / filter cấu trúc?"}
    B -->|"Có"| C["MongoDB find / aggregation + indexes"]
    B -->|"Không"| D{"Từ khóa đơn giản?"}
    D -->|"Có, chấp nhận giới hạn"| E["$text + text index"]
    D -->|"Cần fuzzy/autocomplete/relevance"| F["MongoDB Search $search"]
    D -->|"Cần tương đồng ngữ nghĩa"| G["MongoDB Vector Search $vectorSearch"]
    F --> H{"Deployment/index hỗ trợ?"}
    G --> H
    H -->|"Không"| I["Đổi deployment, hoặc fallback có contract rõ"]
    H -->|"Có"| J["Dùng Spring Data / Driver để gửi pipeline"]
~~~

Đừng thay `$text` bằng `$search` chỉ vì tên có vẻ “mạnh hơn” nếu sản phẩm chỉ cần lọc chính xác. Ngược lại, đừng cố tạo autocomplete quality cao bằng regex scan toàn bộ collection nếu yêu cầu thực là search-as-you-type có scoring.

## 5. Bộ dữ liệu xuyên suốt: catalog đa tenant

Tạo collection test:

~~~javascript
use spring_data_mongodb_lab

db.createCollection("catalog_advanced_010");

db.catalog_advanced_010.insertMany([
  {
    _id: "p010-01",
    tenant_id: "t01",
    sku: "LT-A100",
    title: "Laptop văn phòng 14 inch",
    description: "Máy nhẹ, pin lâu, phù hợp văn phòng",
    category: "laptop",
    active: true,
    price_vnd: NumberLong(18500000),
    tags: ["văn phòng", "mỏng nhẹ"],
    embedding: [0.14, 0.31, 0.07, 0.92]
  },
  {
    _id: "p010-02",
    tenant_id: "t01",
    sku: "LT-B200",
    title: "Laptop đồ họa 16 inch",
    description: "GPU hiệu năng cao cho thiết kế hình ảnh",
    category: "laptop",
    active: true,
    price_vnd: NumberLong(29800000),
    tags: ["đồ họa", "GPU"],
    embedding: [0.81, 0.12, 0.73, 0.05]
  },
  {
    _id: "p010-03",
    tenant_id: "t01",
    sku: "TB-C300",
    title: "Bàn phím cơ không dây",
    description: "Gõ êm, kết nối bluetooth",
    category: "peripheral",
    active: false,
    price_vnd: NumberLong(1650000),
    tags: ["bàn phím", "không dây"],
    embedding: [0.06, 0.88, 0.15, 0.19]
  },
  {
    _id: "p010-04",
    tenant_id: "t02",
    sku: "LT-A100",
    title: "Laptop văn phòng cho doanh nghiệp",
    description: "Máy tính công việc",
    category: "laptop",
    active: true,
    price_vnd: NumberLong(17200000),
    tags: ["văn phòng"],
    embedding: [0.17, 0.33, 0.08, 0.88]
  }
]);
~~~

**Không chạy trên production hoặc database dùng chung.** Nếu đã chạy fixture một lần, lần thứ hai trùng `_id` sẽ phát lỗi duplicate; hãy dùng test database sạch/ID riêng và cleanup có giới hạn, không tùy tiện `dropDatabase()`.

### 5.1. Vì sao embedding chỉ dài 4 chiều?

Các vector `[0.14,0.31,0.07,0.92]` chỉ là **số giả lập để minh họa cú pháp**. Chúng **không phải embedding ngữ nghĩa được huấn luyện** và không chứng minh rằng laptop/keyboard có quan hệ semantic đúng.

Ứng dụng thật phải chọn embedding model, số chiều nhất quán, normalizations, version và lưu vector cho **mọi document cần tìm**. Query vector phải sinh từ **cùng model/không gian** với indexed vectors và có đúng dimension.

### 5.2. Index database cho filter

~~~javascript
db.catalog_advanced_010.createIndex(
  { tenant_id: 1, active: 1, category: 1, price_vnd: 1 },
  { name: "ix_tenant_active_category_price" }
);

db.catalog_advanced_010.createIndex(
  { tenant_id: 1, sku: 1 },
  { unique: true, name: "uq_tenant_sku" }
);
~~~

Không nhầm hai index này với Search indexes; chúng là database indexes sử dụng trong `find`/aggregation thông thường và uniqueness.

### 5.3. Schema Java cơ bản

~~~java
// CatalogProduct.java
package com.example.advancedsearch;

import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_advanced_010")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String sku;
    private String title;
    private String description;
    private String category;
    private boolean active;

    @Field("price_vnd")
    private long priceVnd;

    private List<String> tags;
    private List<Double> embedding;

    protected CatalogProduct() {}

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getTitle() { return title; }
    public String getDescription() { return description; }
    public String getCategory() { return category; }
    public boolean isActive() { return active; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

`@MongoId(FieldType.STRING)` chọn `_id` dạng string theo fixture. `@Field("tenant_id")`/`@Field("price_vnd")` minh họa khác biệt **Java property** với **BSON field path**; phần query raw Document cần dùng tên BSON đúng, không dựa vào mapping tự động của mọi API.

## 6. Tìm chính xác và lọc cấu trúc: `find` + B-tree index

### 6.1. MongoDB server query

~~~javascript
db.catalog_advanced_010.find(
  {
    tenant_id: "t01",
    active: true,
    sku: "LT-A100"
  },
  {
    _id: 1,
    sku: 1,
    title: 1,
    price_vnd: 1
  }
);
~~~

Khi cần lọc chính xác và phép so sánh thông thường, không cần Search index, không cần embedding model.

### 6.2. Spring Data `Query`/`Criteria`

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("active").is(true)
        .and("category").is("laptop")
        .and("priceVnd").gte(10000000L).lte(30000000L)
).limit(20);

List<CatalogProduct> products =
    mongoTemplate.find(query, CatalogProduct.class);
~~~

Trong entity-aware query, `tenantId` và `priceVnd` có thể được Spring Data map sang `tenant_id` và `price_vnd`. Kết quả MongoDB thực tế phụ thuộc dữ liệu/index, không phải chỉ vì một API Java tên `find`.

### 6.3. Repository derived query

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogRepository
        extends MongoRepository<CatalogProduct, String> {

    List<CatalogProduct> findTop20ByTenantIdAndActiveTrueAndCategoryOrderByPriceVndAsc(
        String tenantId,
        String category
    );
}
~~~

Đây là Spring Data query derivation tạo database query; nó **không** phát sinh `$search` hay dùng Lucene Search index. Repository method name thể hiện intent nhưng hiệu năng vẫn phụ thuộc query planner và MongoDB indexes.

### 6.4. Đo bằng `explain`

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  active: true,
  category: "laptop"
}).explain("executionStats");
~~~

Đọc `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và `executionTimeMillis` trong bối cảnh. Một số metric phụ thuộc version/execution engine. `COLLSCAN` không phải lúc nào cũng sai với fixture 4 documents; với production dataset lớn, cần xem độ chọn lọc và chi phí index.

## 7. `$regex`: tìm chuỗi không phải full-text search engine

### 7.1. Prefix regex đơn giản

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  sku: { $regex: "^LT-" }
});
~~~

Regex có anchor `^` cho prefix, kết hợp index và collation phù hợp có thể tối ưu hơn một regex không anchor như `.*LT.*`. Tuy nhiên hiệu năng vẫn phụ thuộc pattern, case sensitivity, index và query planner.

### 7.2. Regex chứa từ bất kỳ

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  description: { $regex: "văn phòng", $options: "i" }
});
~~~

Đây là một cách so khớp pattern, **không** có tokenizer, relevance ranking, fuzzy/edit distance hoặc semantic search tương đương MongoDB Search. `$regex` case-insensitive cũng không tự tương đương analyzer tiếng Việt có dấu/không dấu.

### 7.3. Cảnh báo bảo mật/hiệu năng

**Không** nối một chuỗi regex tùy ý của người dùng vào query nếu không có validation/escape và giới hạn:

- Regex phức tạp có thể tiêu tốn CPU và dẫn tới full collection scan.
- Phải giới hạn độ dài input/pattern và timeout thích hợp.
- Nếu chỉ cần prefix literal, escape regex metacharacters trước khi ghép `^`.
- Phải giữ tenant filter; không lấy 10 results toàn cluster rồi lọc tenant sau.

Ví dụ Java chỉ dùng prefix literal:

~~~java
import java.util.regex.Pattern;

String userPrefix = "LT-";
Pattern safePrefix = Pattern.compile(
    "^" + Pattern.quote(userPrefix)
);

Query query = Query.query(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("sku").regex(safePrefix)
).limit(20);
~~~

`authenticatedTenantId` phải đến từ principal/context đã xác thực, không phải field tenant do client tự nhập. Regex được escape để người dùng không tự chèn pattern phức tạp.

## 8. `$text` là text search **của MongoDB Server**

### 8.1. Tạo **text index** thông thường

~~~javascript
db.catalog_advanced_010.createIndex(
  { title: "text", description: "text" },
  {
    name: "ix_catalog_text",
    weights: { title: 5, description: 1 }
  }
);
~~~

Một collection MongoDB Server có giới hạn text index (thông thường **một text index mỗi collection**, có thể chứa nhiều fields), và `$text` có các hạn chế operator/hint/sort. Index vừa tạo **khác** index `type: "search"` được xây bằng Search service.

### 8.2. Truy vấn và sort theo `textScore`

~~~javascript
db.catalog_advanced_010.find(
  {
    tenant_id: "t01",
    active: true,
    $text: { $search: "laptop văn phòng" }
  },
  {
    title: 1,
    sku: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).limit(10);
~~~

Trong trường hợp `$text`, điểm relevance lấy bằng `$meta: "textScore"`, **khác** `$meta: "searchScore"` của MongoDB Search hay `"vectorSearchScore"` của Vector Search.

### 8.3. Những giới hạn quan trọng

- `$text` dựa trên text index MongoDB Server, không phải Search index/mongot.
- Tokenization/stemming/language support không đồng nhất với Search analyzers.
- `$text` không biến thành fuzzy/autocomplete Search DSL chỉ nhờ thêm `$regex`.
- Trong aggregation, `$match` chứa `$text` phải là stage đầu của pipeline tương ứng và có restrictions.
- Mặc định kết quả `$text` không được tự sắp theo relevance nếu không yêu cầu sort score.
- Tìm kiếm tiếng Việt có dấu/không dấu phải được **thử trên dữ liệu thật**; không giả định text analyzer mặc định xử lý mọi biến thể tiếng Việt như người dùng mong muốn.

### 8.4. Khi nào vẫn nên dùng `$text`?

Khi bài toán chủ yếu là tìm một số từ khóa trong dữ liệu nhỏ/vừa, có thể chấp nhận semantics text index và không muốn vận hành Search service. Phải benchmark/tính đến deployment version và yêu cầu relevance; không nên khẳng định `$text` luôn “đủ tốt” cho một giao diện search thương mại điện tử với typo/autocomplete/phân tích tiếng Việt phức tạp.

## 9. Spring Data `TextCriteria`/`TextQuery` vẫn là API cho MongoDB `$text`

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;

TextCriteria criteria = new TextCriteria()
    .matchingAny("laptop", "văn phòng");

TextQuery query = TextQuery.queryText(criteria)
    .sortByScore()
    .includeScore();

// Kết hợp tenant + active trong cùng query.
query.addCriteria(
    Criteria.where("tenantId").is(authenticatedTenantId)
        .and("active").is(true)
);
query.limit(10);

List<CatalogProduct> results =
    mongoTemplate.find(query, CatalogProduct.class);
~~~

`TextQuery`/`TextCriteria` là abstraction đặc thù của **database `$text`**, không phát ra `$search`. Tên Java method có chữ “Text” hay “Search” không quyết định layer thực thi; xem query BSON và index thực tế.

### 9.1. Text score có nằm trong entity không?

`TextQuery.includeScore()` yêu cầu include metadata score, nhưng entity `CatalogProduct` ở mục 5 không định nghĩa field score tương ứng. Đừng kỳ vọng `getScore()` tự xuất hiện hoặc tự ánh xạ nếu chưa cấu hình DTO/projection metadata theo version.

Để xem rõ raw BSON khi học:

~~~java
List<org.bson.Document> documents = mongoTemplate.find(
    query,
    org.bson.Document.class,
    "catalog_advanced_010"
);
~~~

**Caveat về mapping:** Query viết theo tên property entity (`tenantId`) được map khi chạy với `CatalogProduct.class`; nếu đổi sang `Document.class` raw, cần truyền đúng tên BSON (`tenant_id`). Không copy nguyên query Java ở trên sang raw Document mode rồi ngạc nhiên nếu filter tenant không match. Trong trường hợp cần raw, tạo `TextQuery` và filter `tenant_id` tường minh.

### 9.2. Repo `@TextScore` không có nghĩa Atlas Search score

Spring Data có các tiện ích ánh xạ text score của `$text` ở một số phiên bản, nhưng không nên trộn với `searchScore`/`vectorSearchScore`. Cơ chế score và shape kết quả khác nhau:

~~~text
MongoDB text index -> $text -> $meta "textScore"
MongoDB Search      -> $search -> $meta "searchScore"
MongoDB Vector      -> $vectorSearch -> $meta "vectorSearchScore"
~~~

Điểm số từ các engine khác nhau **không cùng thang đo/ý nghĩa**; không lấy tổng hay so sánh trực tiếp nếu chưa có chiến lược chuẩn hóa/ranking.

## 10. MongoDB Search index: mapping chuyên biệt và trạng thái READY

MongoDB Search sử dụng một **Search index definition** khác B-tree/text index. Với fixture `catalog_advanced_010`, tạo index tên `catalog_lexical` trên deployment hỗ trợ Search:

~~~javascript
db.catalog_advanced_010.createSearchIndex(
  "catalog_lexical",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        description: { type: "string" },
        tags: { type: "string" },
        tenant_id: { type: "token" },
        active: { type: "boolean" },
        category: { type: "token" },
        price_vnd: { type: "number" }
      }
    }
  }
);
~~~

Ví dụ dùng `token` cho field lọc chính xác (tenant/category) và `string` cho field cần analyzer/text search. Cấu hình chính xác của analyzer, normalizer, facets, sortable fields, nested documents và field types phụ thuộc feature version. Khi search tiếng Việt, nên thiết kế analyzer/synonym riêng rồi đo chất lượng; không giả định standard analyzer xử lý mọi dạng dấu/biến thể như mong đợi.

### 10.1. Kiểm READY

~~~javascript
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: {} }
]);
~~~

Lọc index cần kiểm trong kết quả:

~~~javascript
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: { name: "catalog_lexical" } }
]);
~~~

Tạo index thành công hoặc API `exists` trả true **không đồng nghĩa chỉ mục đã phục vụ query**. Cần kiểm trạng thái xây dựng/READY (và thông tin queryable tương ứng với phiên bản/deployment), nhất là CI và ngay sau deployment.

### 10.2. Search index không dùng cùng query planner với B-tree index

~~~text
db.collection.createIndex({sku:1})
    -> Database B-tree / classic query plan.

db.collection.createIndex({title:"text"})
    -> Database text index cho $text.

db.collection.createSearchIndex("catalog_lexical", {...})
    -> MongoDB Search index cho $search/$searchMeta.

db.collection.createSearchIndex("catalog_vector", "vectorSearch", {...})
    -> Vector Search index cho $vectorSearch.
~~~

`hint("catalog_lexical")` trong `find` không biến query thường thành Search query. Tương tự, `$search` không tự chọn B-tree `ix_tenant_active_category_price` để làm lexical search; Search cần fields được index theo **Search index definition**.

### 10.3. Đổi Search index definition là hoạt động vận hành

Đổi analyzer, field mapping hoặc similarity có thể kích hoạt rebuild/reindex. Cần:

- Version quản lý index definition qua migration/infra.
- Thời điểm rollout và kiểm trạng thái ready.
- Test đúng production-like Search environment.
- Khi có nhiều index version, chuyển query từ tên cũ sang tên mới theo kế hoạch.
- Có rollback plan và dự trù chi phí index build/search nodes.

Không tạo/drop Search index mỗi HTTP request hoặc trong transaction nghiệp vụ.

## 11. `$search` là aggregation stage của Search service

### 11.1. Ví dụ lexical search có tenant filter

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $search: {
      index: "catalog_lexical",
      compound: {
        must: [
          {
            text: {
              query: "laptop",
              path: ["title", "description", "tags"]
            }
          }
        ],
        filter: [
          { equals: { path: "tenant_id", value: "t01" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      sku: 1,
      price_vnd: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
~~~

**Ý nghĩa từng phần:**

- `$search` là stage đầu pipeline.
- `index` là **tên Search index**, không phải database index name.
- `text.query` và `path` mô tả lexical query.
- `compound.must` là điều kiện có ý nghĩa tìm kiếm/scoring.
- `compound.filter` là điều kiện không làm tăng score, thích hợp tenant/active/ACL metadata.
- `$meta: "searchScore"` trả relevance score để hiển thị/điều chỉnh ranking.
- `$limit` giới hạn output, tránh trả hàng nghìn documents không cần thiết.

### 11.2. Vì sao tenant filter phải nằm trong `$search`?

Nguy hiểm:

~~~javascript
db.catalog_advanced_010.aggregate([
  { $search: {
      index: "catalog_lexical",
      text: { query: "laptop", path: "title" }
  }},
  { $limit: 5 },
  { $match: { tenant_id: "t01" } }
]);
~~~

Nếu Search trả top 5 toàn bộ tenants rồi mới lọc, bạn có thể nhận **ít hơn 5 kết quả hợp lệ dù tenant t01 còn nhiều match ở vị trí 6+**. Query còn có nguy cơ thực hiện ranking/candidate retrieval trên dữ liệu không thuộc tenant cần truy cập.

Nên đẩy tenant/ACL filter vào **Search DSL trước topK/ranking**, với fields được index để lọc. Có thể cần thêm `$match` bảo vệ sau Search khi policy yêu cầu, nhưng không thay thế filter sớm bằng post-filter nếu cần tính đúng đắn topK.

### 11.3. Search-index field type phải tương ứng operator

Ví dụ `equals:{path:"tenant_id",value:"t01"}` cần field được index dưới kiểu hỗ trợ exact matching, điển hình `token`. Nếu chỉ index `tenant_id` như analyzed `string` nhưng dùng `equals` sai kiểu, query có thể fail/không match tùy mapping/version.

Tương tự:

- `range` trên giá cần number mapping.
- `exists`/boolean filters yêu cầu field mapping phù hợp.
- Autocomplete cần field type/operator thích hợp thay vì dùng mặc định `text`.
- Facet trên string cần index mapping hỗ trợ token/facet theo phiên bản.

### 11.4. Relevance không đồng nghĩa sort nghiệp vụ

Nếu user muốn “giá thấp nhất trong sản phẩm phù hợp”, cần quyết định:

1. Giữ topK theo relevance rồi sort giá trong topK?
2. Sort giá trên mọi match, không trọng relevance?
3. Combine score và business signals?

Ba lựa chọn **khác nhau**. Ví dụ `$sort:{price_vnd:1}` sau `$limit:10` chỉ sắp xếp **10 kết quả đã lấy**, không tìm 10 sản phẩm rẻ nhất toàn tập match.

### 11.5. Stage ordering

`$search` phải là **stage đầu của pipeline con chứa nó** theo quy tắc MongoDB Search. Không đặt `$match`/`$project` trước `$search` trong cùng pipeline và kỳ vọng Search vẫn chạy. Các pipeline con trong `$lookup`/`$unionWith` có những quy định riêng theo version; đừng mặc nhiên coi mọi nested stage luôn hỗ trợ như nhau.

## 12. `$searchMeta`: metadata/facet/count khác với danh sách hits

### 12.1. Count của kết quả Search

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $searchMeta: {
      index: "catalog_lexical",
      text: {
        query: "laptop",
        path: ["title", "description"]
      },
      count: { type: "total" }
    }
  }
]);
~~~

`$searchMeta` trả metadata document(s), **không** trả danh sách product hits như `$search`. Khi dùng count `lowerBound` thay vì `total`, hãy hiển thị/diễn giải là **ước lượng cận dưới**, không báo “chính xác 18.204 kết quả”.

### 12.2. Facet theo category

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $searchMeta: {
      index: "catalog_lexical",
      facet: {
        operator: {
          compound: {
            must: [
              { text: {
                  query: "laptop",
                  path: ["title", "description"]
              }}
            ],
            filter: [
              { equals: { path: "tenant_id", value: "t01" } },
              { equals: { path: "active", value: true } }
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
      }
    }
  }
]);
~~~

Facet có semantics và index mapping riêng; cần kiểm field category có thể facet bằng định nghĩa phù hợp với feature version, không mặc định mọi analyzed string đều facet được.

### 12.3. `$$SEARCH_META`

Sau một `$search`, aggregation có thể dùng `$$SEARCH_META` để truy xuất metadata của query theo các stage được phép. Nhưng **không** dùng nó tùy tiện sau `$lookup`/`$unionWith` khi các stage làm metadata context không còn hợp lệ; xem quy tắc MongoDB Search theo version.

### 12.4. Phân biệt ba cách đếm

| Cách | Đếm cái gì? |
| --- | --- |
| `db.collection.countDocuments({tenant_id:"t01"})` | Documents match DB predicate |
| `$searchMeta.count` | Matches của Search query/index, theo `total`/`lowerBound` |
| `$count` sau `$search` và sau filters | Documents đã đi qua các stage trong pipeline tới điểm đếm |

Nếu filter sau Search/limit, kết quả count có thể không giống `$searchMeta`. Search index lag cũng làm `countDocuments` và `$searchMeta` có thể khác nhau tạm thời.

## 13. Search scoring, highlight và phân trang

### 13.1. Mọi score đều có ngữ cảnh

~~~text
$text          -> textScore
$search        -> searchScore
$vectorSearch  -> vectorSearchScore
~~~

Điểm Search không phải xác suất “người dùng chắc chắn muốn sản phẩm này”. Nó là tín hiệu ranking theo operator, index, analyzer, scoring options và dữ liệu. Score có thể thay đổi khi đổi index/engine và không so trực tiếp giữa hai query khác nhau.

### 13.2. Boost title so với description

Ví dụ Search DSL:

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $search: {
      index: "catalog_lexical",
      compound: {
        should: [
          { text: {
              query: "laptop",
              path: "title",
              score: { boost: { value: 4 } }
          }},
          { text: {
              query: "laptop",
              path: "description"
          }}
        ],
        minimumShouldMatch: 1,
        filter: [
          { equals: { path: "tenant_id", value: "t01" } },
          { equals: { path: "active", value: true } }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
~~~

`boost` tăng vai trò của match ở title so với description, nhưng không bảo đảm kết quả đầu luôn là title match nếu các tín hiệu khác chi phối. Cần đo relevance quality bằng query set và human judgments.

### 13.3. Highlight không phải metadata mặc định của mọi Search query

Để lấy snippets/hit highlights, cần Search `highlight` option và projection metadata tương ứng trong `$search` (nếu field/operator hỗ trợ). Không tự suy từ `$search` trả document rằng title đã được “đánh dấu từ trùng”.

### 13.4. Pagination kiểu offset có chi phí

~~~javascript
[
  { $search: {/* lexical query */} },
  { $skip: 10000 },
  { $limit: 20 }
]
~~~

Offset lớn thường làm tăng chi phí và dễ không ổn định khi dữ liệu/search index thay đổi. MongoDB Search cung cấp `searchAfter`/`searchBefore` token-based pagination trên các phiên bản phù hợp, nhưng:

- Token không phải `_id` tự chế từ last hit.
- Cần dùng sort/ranking deterministic theo contract.
- Search index thay đổi có thể khiến pagination qua nhiều requests không phải snapshot nhất quán tuyệt đối.
- Phải tính token lifecycle, query consistency và filter tenant/ACL.

**Không dùng** cursor pagination như cam kết có snapshot isolation trên Search results.

### 13.5. Khi nào cần ổn định hơn?

Nếu khách hàng đã chọn sản phẩm và thực hiện checkout, hãy đọc **current state từ MongoDB Server** theo ID, kiểm giá/active/tenant/stock trong business transaction, chứ không dùng Search hit làm nguồn sự thật cho giao dịch.

## 14. Vector Search: “tương đồng ngữ nghĩa” là một hệ thống riêng

Lexical search tìm từ/cụm từ. Vector search tìm **biểu diễn số** gần nhau trong không gian embedding. Một vector:

~~~javascript
embedding: [0.14, 0.31, 0.07, 0.92]
~~~

không tự mang “ý nghĩa laptop” nếu không được tạo từ embedding model phù hợp. MongoDB cung cấp **lưu trữ, index và tìm kiếm vector**; pipeline tạo embedding, versioning và evaluation vẫn là trách nhiệm của ứng dụng hoặc một dịch vụ embedding riêng.

### 14.1. Các thành phần

~~~mermaid
flowchart LR
    P["Product title + description"] --> EM["Embedding model / pipeline"]
    EM --> V["Vector trong MongoDB document"]
    V --> VI["MongoDB Vector Search index"]
    Q["Câu hỏi người dùng"] --> QM["Cùng embedding model"]
    QM --> VS["$vectorSearch"]
    VI --> VS
    VS --> R["Top-K tương đồng + score"]
~~~

### 14.2. Những tham số tối quan trọng

| Tham số | Ý nghĩa |
| --- | --- |
| `path` | Trường embedding được index |
| `numDimensions` | Kích thước mỗi vector; query phải tương ứng |
| `similarity` | Cách đo gần nhau (`cosine`, `dotProduct`, `euclidean` theo index) |
| `queryVector` | Vector của câu truy vấn cùng embedding space |
| `limit` | Số kết quả mong muốn |
| `numCandidates` | Candidate pool cho approximate search trong các chế độ yêu cầu |
| `filter` | Điều kiện pre-filter trên các field được index kiểu filter |
| `exact` | Chế độ exact nearest neighbors nếu server/search version hỗ trợ |

**Không** so điểm Search lexical với vector score như hai giá trị xác suất cùng thang đo.

### 14.3. ANN và ENN

**ANN** ưu tiên hiệu năng bằng việc xấp xỉ hàng xóm gần nhất; có trade-off recall/speed theo `numCandidates`/index/data. **ENN** (exact) có thể xem xét nhiều vector hơn để tìm hàng xóm chính xác nhưng thường tốn tài nguyên hơn, và khả năng/giới hạn tùy phiên bản.

Không chọn `numCandidates=limit` theo thói quen rồi mong recall tốt. Hãy benchmark trên ground-truth dataset với các chỉ số Recall@K, nDCG@K, latency p95 và tenant-filtered candidate cardinality.

## 15. Tạo **Vector Search index**, không phải B-tree index

Với fixture 4 chiều:

~~~javascript
db.catalog_advanced_010.createSearchIndex(
  "catalog_vector",
  "vectorSearch",
  {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      { type: "filter", path: "tenant_id" },
      { type: "filter", path: "active" },
      { type: "filter", path: "category" }
    ]
  }
);
~~~

Cú pháp ba tham số `name, type, definition` của `createSearchIndex()` phải được dùng với phiên bản `mongosh`/server hỗ trợ. Những ví dụ trên dùng vector bốn chiều nhằm chạy thử cú pháp; production thường dùng vector hàng trăm/nghìn chiều theo embedding model tương ứng và phải đáp ứng giới hạn dimension/format do server version đặt ra.

### 15.1. Vì sao cần `filter` fields riêng?

Index vector không tự cho phép dùng mọi field MongoDB trong `$vectorSearch.filter`. Các field cần dùng pre-filter như `tenant_id`, `active`, `category` phải được định nghĩa kiểu `filter` trong vector index và dùng kiểu BSON phù hợp.

Nếu bỏ `tenant_id` filter field khỏi index rồi đặt tenant filter trong `$match` **sau** topK, application có nguy cơ trả thiếu kết quả hợp lệ và thực hiện ANN trên tập dữ liệu không thuộc tenant.

### 15.2. Kiểm status trước khi query

~~~javascript
db.catalog_advanced_010.aggregate([
  { $listSearchIndexes: { name: "catalog_vector" } }
]);
~~~

Chỉ gửi query nghiệp vụ khi index đã sẵn sàng và deployment hỗ trợ stage. `createSearchIndex()` trả về không đồng nghĩa toàn bộ vector đã được index ngay lập tức.

## 16. Truy vấn `$vectorSearch` với filter đúng

~~~javascript
db.catalog_advanced_010.aggregate([
  {
    $vectorSearch: {
      index: "catalog_vector",
      path: "embedding",
      queryVector: [0.15, 0.32, 0.06, 0.90],
      numCandidates: 100,
      limit: 5,
      filter: {
        tenant_id: "t01",
        active: true
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

**Đọc đúng semantics:**

- `$vectorSearch` dùng Vector Search index `catalog_vector`.
- `queryVector` ở đây là **vector giả định** và không chứng minh semantic correctness.
- `numCandidates`/`limit` điều chỉnh candidate set/kết quả.
- `filter` ở **trong stage**, trước khi topK được chọn, sử dụng indexed filter fields.
- `$meta: "vectorSearchScore"` lấy vector score, không phải `searchScore`/`textScore`.

### 16.1. Stage restrictions

`$vectorSearch` có vị trí và composition restrictions khác với aggregation stages thông thường; theo tài liệu MongoDB hiện hành, không dùng `$vectorSearch` bên trong `$facet` hoặc `$lookup`. Một số hình thức composition như `$unionWith` được hỗ trợ ở các server version nhất định (MongoDB 8.0+ theo tài liệu) nhưng phải kiểm chính xác môi trường đích.

Không giả định “aggregate stage nào cũng lồng được stage nào” chỉ vì Spring Data có API `AggregationOperation`.

### 16.2. Khác biệt giữa vector score và lexical score

~~~javascript
{ $meta: "textScore" }         // database $text
{ $meta: "searchScore" }       // Search $search
{ $meta: "vectorSearchScore" } // Vector Search $vectorSearch
~~~

Khi trộn kết quả, cần chuẩn hóa/ranking method phù hợp thay vì cộng trực tiếp ba số. Query vector “gần” về không gian embedding không có nghĩa document thỏa exact business predicates nếu thiếu pre-filter.

### 16.3. Không dùng vector search cho mọi bài toán

Tra cứu `sku="LT-A100"` bằng cosine similarity vừa tốn embedding, vừa có thể đưa ra sản phẩm “gần giống” nhưng **không phải mã cần tìm**. Exact IDs, ACL, tenant, stock và transaction predicates nên do database business queries quyết định. Vector Search đóng vai trò retrieval/ranking cho nhu cầu phù hợp, không thay source-of-truth validation.

## 17. Hybrid search: phối hợp lexical và semantic theo ranking strategy

Một người dùng gõ “laptop mỏng nhẹ cho văn phòng” có thể muốn cả kết quả **chứa từ khóa** và sản phẩm **tương đồng ngữ nghĩa**.

~~~text
User query
   |
   +-- lexical $search  -> ranked list A
   |
   +-- embed(query) -> $vectorSearch -> ranked list B
                                  |
                         Fusion / reranking
                                  |
                            top-K results
~~~

| Phương pháp | Ý tưởng | Điều kiện |
| --- | --- | --- |
| Reciprocal Rank Fusion (RRF) | Dựa trên thứ hạng, không phụ thuộc raw score | Có hai ranked lists có thể đối chiếu ID |
| Weighted score fusion | Chuẩn hóa scores rồi kết hợp | Calibration/evaluation đúng dữ liệu |
| Native search fusion stage | Dùng MongoDB stage theo phiên bản hỗ trợ | Kiểm phiên bản Search/DB và giới hạn stage |
| Application-side fusion | Gọi riêng hai queries và hợp nhất tại Java | Trả thêm latency và consistency trade-off |

**Không** cộng thẳng `searchScore + vectorSearchScore` rồi gọi là “độ phù hợp 90%”. Hai scores khác thang đo, model/index/operator và cách scoring.

### 17.1. Lưu ý deployment/version

Các MongoDB versions có thể cung cấp các stage fusion chuyên dụng, hoặc cho phép composition qua `$unionWith` theo điều kiện riêng. Một số cải tiến hybrid xuất hiện sau các phiên bản tài liệu Java Driver/Spring Data cũ. Không cố định một cú pháp fusion cho mọi MongoDB server; đọc tài liệu của **đúng version production** và integration test trước khi bật feature.

### 17.2. Candidate filtering trước fusion

Mỗi nhánh retrieval cần lọc **tenant, active, visibility và ACL** khi lấy candidates. Nếu nhánh vector tìm top 10 toàn cluster rồi mới filter tenant t01, một số sản phẩm t01 có score tốt sẽ bị loại do nằm sau vị trí 10; fusion không thể khôi phục item chưa được lấy.

### 17.3. Đánh giá chất lượng

Với 100 truy vấn đại diện đã gán nhãn:

- Recall@K: bao nhiêu kết quả liên quan được tìm thấy?
- nDCG@K/MRR: thứ hạng có phù hợp không?
- P95 latency: kết quả trả đủ nhanh?
- No-result rate: query không match có được fallback?
- Tenant leakage: có một document khác tenant lọt ra ngoài không?
- Freshness: thay đổi dữ liệu gần đây xuất hiện với độ trễ bao nhiêu?

Không chọn trọng số fusion chỉ vì một ví dụ tìm kiếm “có vẻ đẹp”.

## 18. Spring Data `MongoTemplate.aggregate` có thể gửi Search stage raw

Spring Data MongoDB cung cấp `AggregationOperation` để xây một aggregation pipeline. Khi một Search DSL feature chưa có type-safe builder trong Spring Data version đang dùng, có thể tạo BSON bằng `org.bson.Document`.

### 18.1. Service search lexical có tenant filter

~~~java
// CatalogSearchService.java
package com.example.advancedsearch;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

@Service
public class CatalogSearchService {
    private final MongoTemplate mongo;

    public CatalogSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<Document> lexicalSearch(
            String trustedTenantId, String keyword, int limit) {
        if (trustedTenantId == null || trustedTenantId.isBlank()
                || keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant and keyword are required");
        }

        int safeLimit = Math.max(1, Math.min(limit, 20));
        Document text = new Document("text",
            new Document("query", keyword)
                .append("path", List.of("title", "description")));

        Document tenant = new Document("equals",
            new Document("path", "tenant_id")
                .append("value", trustedTenantId));
        Document active = new Document("equals",
            new Document("path", "active")
                .append("value", true));

        Document searchSpec = new Document(
            "index", "catalog_lexical")
            .append("compound", new Document("must", List.of(text))
                .append("filter", List.of(tenant, active)));

        AggregationOperation search =
            context -> new Document("$search", searchSpec);

        AggregationOperation project =
            context -> new Document("$project",
                new Document("title", 1)
                    .append("sku", 1)
                    .append("price_vnd", 1)
                    .append("score",
                        new Document("$meta", "searchScore")));

        Aggregation pipeline = Aggregation.newAggregation(
            search, project, Aggregation.limit(safeLimit)
        );

        return mongo.aggregate(
            pipeline, "catalog_advanced_010", Document.class
        ).getMappedResults();
    }
}
~~~

**Đây là một ví dụ tương đối portable** vì:

- Keyword là **BSON value**, không bị nối thành cú pháp JSON string.
- Tenant do caller tin cậy cung cấp, nhưng controller phải lấy nó từ **authenticated principal**, không từ body tùy ý.
- Các path Search fields là constants và đã được định nghĩa trong Search index.
- Search stage ở **đầu** pipeline.
- Giới hạn tối đa 20 kết quả để tránh tải lớn.

Tuy nhiên code Java compile được **không** đảm bảo server có `$search`. Trên MongoDB standalone không có Search service/index, aggregate sẽ thất bại.

### 18.2. Cảnh báo `@Field` mapping khi dùng raw `Document`

Trong entity:

~~~java
@Field("tenant_id")
private String tenantId;
~~~

Nhưng custom `AggregationOperation` trên tạo trực tiếp một BSON `Document`. Do đó:

~~~text
Java property: tenantId
Raw BSON path: tenant_id
~~~

Không viết `"tenantId"` trong `$search.compound.filter.path` chỉ vì API Java dùng property ấy, trừ khi mapping/index định nghĩa path theo đúng tên đó. Trái lại, các builder type-aware của Spring Data có thể map property paths bằng entity mapping context.

### 18.3. Spring Data không tự sửa stage order

Sai:

~~~java
Aggregation wrong = Aggregation.newAggregation(
    Aggregation.match(
        org.springframework.data.mongodb.core.query.Criteria
            .where("tenantId").is("t01")),
    search
);
~~~

`$search` phải là stage đầu pipeline chứa nó. Filter tenant nên nằm trong `compound.filter` của Search stage. Chèn `$match` trước Search không trở thành hợp lệ chỉ vì dùng Java DSL.

### 18.4. Đừng trả raw BSON thẳng cho client

Projection ở trên cố ý chỉ lấy `title`, `sku`, `price_vnd`, `score`. Trong API thật nên map ra DTO riêng; không trả nguyên full MongoDB Document chứa `embedding`, private metadata hoặc fields không được phép hiển thị.

## 19. Spring Data type-safe `VectorSearchOperation` và `SearchIndexOperations`

Spring Data MongoDB từ dòng phiên bản hỗ trợ Vector Search có `VectorSearchOperation`, `VectorIndex`, `SearchIndexOperations`. Đây là **abstractions client-side**, vẫn đòi Search service và Vector index thực.

### 19.1. Tạo Vector Index bằng Spring Data

~~~java
import org.springframework.data.mongodb.core.index.VectorIndex;
import static org.springframework.data.mongodb.core.index.VectorIndex.SimilarityFunction.COSINE;

VectorIndex definition = new VectorIndex("catalog_vector")
    .addVector("embedding",
        v -> v.dimensions(4).similarity(COSINE))
    .addFilter("tenantId")
    .addFilter("active");

String name = mongoTemplate
    .searchIndexOps(CatalogProduct.class)
    .createIndex(definition);
~~~

Khi dùng `searchIndexOps(CatalogProduct.class)`, entity mapping context cho phép ánh xạ property `tenantId` sang BSON `tenant_id` khi tạo index definition. Đây là điểm khác với raw mongosh `createSearchIndex(...)` ở mục 15.

### 19.2. Kiểm Search index readiness

~~~java
var ops = mongoTemplate.searchIndexOps(CatalogProduct.class);
boolean exists = ops.exists("catalog_vector");
var status = ops.status("catalog_vector");
~~~

`exists==true` chưa chắc index **READY**; đọc status thực, đặt deadline và xác định hành vi degraded nếu index đang build/rebuild. Không tạo/drop Search index mỗi HTTP request.

### 19.3. Query bằng VectorSearchOperation

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.newAggregation;
import org.springframework.data.mongodb.core.aggregation.VectorSearchOperation;
import org.bson.Document;

// queryVector: vector thuộc API type được hỗ trợ bởi phiên bản Spring Data.
VectorSearchOperation vectorStage = VectorSearchOperation
    .search("catalog_vector")
    .path("embedding")
    .vector(queryVector)
    .numCandidates(100)
    .limit(5)
    .filter(new Document("tenant_id", trustedTenantId)
        .append("active", true))
    .withSearchScore("score");

var results = mongoTemplate.aggregate(
    newAggregation(CatalogProduct.class, vectorStage),
    Document.class
).getMappedResults();
~~~

Ở đây `queryVector` là biến đã được tạo trước, đúng overload/type trong **Javadoc dependency version thực tế** (một số phiên bản chấp nhận `Vector`, arrays/collection). Dùng ví dụ này như một **sơ đồ API**, không copy mà thiếu biến hoặc mismatch version. `VectorSearchOperation` là một builder giúp tạo `$vectorSearch`, **không tạo vector embedding**, không tự xác định tenant của người gọi và không thay kiểm dimension.

### 19.4. Vì sao class Java mới không đủ?

~~~text
Spring Data có VectorSearchOperation
                 |
                 v
Driver gửi BSON $vectorSearch
                 |
                 v
MongoDB Server / Search service KHÔNG hỗ trợ
                 |
                 v
Operation thất bại tại runtime
~~~

Một test compile trên Java và một unit test mock repository **không chứng minh** Search feature chạy trên môi trường thật.

### 19.5. Version note

Spring Data `VectorIndex`/`VectorSearchOperation` có thể có các API overload khác nhau giữa 4.5, 5.0, 5.1 và phiên bản mới. Đọc Javadoc **đúng release** cho imports, `.vector(...)`, search score, index status và repository support; nếu cần cú pháp MongoDB mới chưa được builder hỗ trợ, dùng raw `AggregationOperation` với BSON và test trên deployment đích.

## 20. Repository `@Aggregation` và `@VectorSearch` là hai cách khác nhau

### 20.1. `@Aggregation` với Search DSL

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogSearchRepository
        extends MongoRepository<CatalogProduct, String> {

    @Aggregation(pipeline = {
      "{ '$search': { 'index': 'catalog_lexical', " +
      "  'compound': { " +
      "    'must': [ { 'text': { " +
      "      'query': ?1, 'path': 'title' " +
      "    }} ], " +
      "    'filter': [ " +
      "      { 'equals': { 'path': 'tenant_id', 'value': ?0 } }, " +
      "      { 'equals': { 'path': 'active', 'value': true } } " +
      "    ] " +
      "  } " +
      "} }",
      "{ '$limit': 10 }"
    })
    List<CatalogProduct> searchTitleByTenant(
        String trustedTenantId,
        String keyword
    );
}
~~~

`@Aggregation` khai báo BSON aggregation; `?0`/`?1` được Spring Data bind theo query annotation semantics. Nó vẫn cần Search index `catalog_lexical` và Search-capable server. Với DSL lớn, `MongoTemplate`/custom repository implementation thường dễ review/test hơn annotation string dài.

### 20.2. Repository query derivation thường là Database Query

~~~java
List<CatalogProduct> findByTitleContaining(String term);
~~~

Method derived query trên tạo query theo **MongoDB repository query derivation** (có thể dùng regex depending keyword semantics), **không tự động chạy mongot** hay `$search` chỉ vì tên method có chữ `find`.

### 20.3. Repository `@VectorSearch` theo phiên bản Spring Data

Các bản Spring Data MongoDB mới có abstraction `@VectorSearch` và `SearchResults<T>`/`Vector`. Theo tài liệu chính thức, một ví dụ dạng:

~~~java
import org.springframework.data.mongodb.repository.VectorSearch;
import org.springframework.data.domain.Vector;
import org.springframework.data.domain.Score;
import org.springframework.data.domain.SearchResults;

public interface SimilarityRepository
        extends org.springframework.data.repository.Repository<CatalogProduct, String> {

    @VectorSearch(
        indexName = "catalog_vector",
        numCandidates = "200"
    )
    SearchResults<CatalogProduct> searchTop10ByEmbeddingNear(
        Vector vector,
        Score score
    );
}
~~~

**Kiểm API theo phiên bản:** tên package `Vector`/`Score` và method signature phải đối chiếu với Spring Data release của project. Repository vector query cần index tên đúng, vector đúng dimension và đủ parameters giới hạn score/limit theo semantics API; ví dụ đơn giản không đặt tenant filter, **không phù hợp endpoint multi-tenant nếu dùng trực tiếp**.

Trong production có thể dùng `@VectorSearch(filter=...)` hoặc derived pre-filter trong những phiên bản hỗ trợ; ưu tiên test đúng BSON để chứng minh tenant thực sự được đưa vào `$vectorSearch.filter`, thay vì chỉ hậu lọc sau topK.

### 20.4. Phân biệt ba API Spring

| API Spring Data | MongoDB command/stage dự kiến | Đòi Search service? |
| --- | --- | --- |
| `MongoRepository.findBy...` | `find`/query predicates | Không cho filter thông thường |
| `TextQuery`/`TextCriteria` | `$text` | Không, cần database text index |
| `MongoTemplate.aggregate` chứa `$search` | `aggregate: [$search,...]` | **Có** |
| `MongoTemplate.aggregate` chứa `$vectorSearch` | `aggregate: [$vectorSearch,...]` | **Có** |
| `VectorSearchOperation` | Builder cho `$vectorSearch` | **Có** |
| `SearchIndexOperations` | Search index management commands | **Có** để thành công |
| `@Aggregation` có `$search` | Aggregation BSON của annotation | **Có** |
| `@VectorSearch` | Vector-search repository pipeline | **Có** |

## 21. Reactive Search dùng cùng server capability, khác execution model

Spring Data reactive cung cấp `ReactiveMongoTemplate`, reactive repository và Reactor `Mono`/`Flux`. Chúng làm I/O bất đồng bộ, **không thêm Search service** và không tạo Search index.

### 21.1. Gửi Search pipeline qua reactive API

~~~java
// Trong reactive service có injected ReactiveMongoTemplate.
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<Document> searchReactive(
        Aggregation tenantScopedPipeline) {
    return reactiveMongoTemplate.aggregate(
        tenantScopedPipeline,
        "catalog_advanced_010",
        Document.class
    );
}
~~~

`tenantScopedPipeline` phải có Search/Vector filter tenant và limit như các phần trước. Reactive MongoDB Driver gửi cùng BSON stage tới MongoDB deployment; nếu Search index không tồn tại, reactive publisher phát lỗi khi thực thi.

### 21.2. Publisher thường lazy

~~~java
Flux<Document> hits = reactiveMongoTemplate.aggregate(
    pipeline, "catalog_advanced_010", Document.class
);
// Chưa chắc đã gửi lệnh tới server trước khi subscribe.
~~~

Trong WebFlux, trả Publisher ra controller để framework subscribe. Không gọi `subscribe()` trong service rồi return `Flux.empty()` — điều đó làm lỗi, deadline, context và kết quả rời khỏi caller.

### 21.3. `block()` không biến Search thành sync transaction

~~~java
// Tránh trên WebFlux event loop:
// hits.collectList().block();
~~~

Blocking có thể gây thread starvation; nó cũng không tạo index hoặc làm Search result “tươi” hơn. Dùng `flatMap`/`collectList` có giới hạn nếu endpoint cần `Mono<List<DTO>>`; nếu stream results, phải kiểm behavior khi client disconnect.

### 21.4. Cancellation và timeout

Một client HTTP có thể ngắt kết nối giữa lúc Search đang chạy. `Flux.timeout` hoặc cancellation ảnh hưởng lifecycle client/driver, **không bảo đảm server Search engine lập tức giải phóng mọi tài nguyên**. Đặt deadline, max query length, result cap, rate limit và theo dõi Search query latency/queue.

### 21.5. Streaming kết quả không thay index consistency

Search index cập nhật bất đồng bộ từ database. Việc reactive stream trả từng hit không tạo snapshot read-after-write như một transaction MongoDB. Khi cần giá/stock mới nhất để checkout, phải đọc lại current document bằng database query và kiểm version/business constraints.

## 22. Thiết kế bảo mật: tenant, ACL và injection

### 22.1. Tenant được xác thực ở cả truy vấn và search engine

~~~text
Authenticated principal -> tenantId t01
                             |
             Build Search DSL with tenant filter
                             |
                   $search / $vectorSearch
                             |
                 topK của tenant t01
                             |
              Project whitelisted fields
~~~

Không tin `tenantId` do user gửi trong body. Không chạy Search toàn cluster rồi chỉ lọc `tenant_id` sau `$limit` vì sẽ sai topK và tiêu tốn work trên dữ liệu ngoài tenant. Với ACL theo user/role, cần đưa các predicate được Search service hỗ trợ vào phần pre-filter tương ứng, và đọc/kiểm lại quyền ở DB business boundary nếu cần.

### 22.2. Search score không phải permission check

Một document có score cao không có nghĩa người dùng được phép xem. `$search.compound.filter` hoặc `$vectorSearch.filter` phải bảo đảm candidate set hợp lệ. Ngoài ra, vì Search index có thể chậm cập nhật trạng thái `active/visibility`, một ứng dụng yêu cầu thu hồi quyền tức thì nên **revalidate quyền/current state trước khi trả dữ liệu nhạy cảm**.

### 22.3. Không đưa input vào JSON DSL thô

Sai:

~~~java
// KHÔNG làm:
// String json = "{'$search': {'text': {'query': '"
//     + userInput + "', 'path': '" + userPath + "'}}}";
~~~

Input chứa ký tự đặc biệt có thể gây lỗi parser; user-controlled index/path/operator có thể mở rộng phạm vi query ngoài ý định.

Đúng về nguyên tắc:

~~~java
Document text = new Document("query", userKeyword)
    .append("path", "title");

Document stage = new Document("$search",
    new Document("index", "catalog_lexical")
        .append("text", text));
~~~

Keyword được gán làm **giá trị BSON**; index/path là constants/allowlist. Nhưng query string vẫn có semantics của Search operator; nếu API muốn tìm literal theo cách đơn giản, cần validation/escaping/syntax policy. Không coi parameter binding là phép kiểm quyền.

### 22.4. Resource-exhaustion và expensive queries

Giới hạn độ dài query, số clauses/path, `limit`, `numCandidates`, kích thước vector, fuzzy/wildcard complexity, số request đồng thời và pagination depth. Theo dõi timeout, Search query CPU/memory/queue và apply per-tenant quotas. Không mở đường cho client tự chọn `numCandidates=1000000` hoặc raw Search DSL tùy ý nếu endpoint không phải admin đáng tin cậy.

### 22.5. Embedding vẫn cần privacy control

Embedding là biểu diễn số nhưng vẫn có thể tiết lộ thuộc tính/ngữ cảnh văn bản gốc qua phân tích tùy threat model. Không coi vector là dữ liệu “không thể định danh”. Áp access control, retention/xóa, tách tenant, giới hạn logging và đánh giá bên cung cấp embedding model.

## 23. Tính mới của dữ liệu: Search không phải read-your-writes

~~~text
t0: insert product p010-05 vào MongoDB.
t1: MongoDB acknowledge write.
t2: findById("p010-05") thấy document.
t3: $search query có thể CHƯA thấy p010-05.
t4: Search index đồng bộ xong.
t5: $search bắt đầu trả p010-05.
~~~

**Không** suy rằng MongoDB Search/Vector Search bảo đảm transaction read-after-write giống primary DB query ở mọi thời điểm.

### 23.1. Khác biệt index update

| Cơ chế | Tính mới cần hiểu |
| --- | --- |
| Database B-tree / `find` theo acknowledged write | Query DB theo read concern/read preference phù hợp |
| Database `$text` | Dựa trên text index cập nhật trong engine database |
| MongoDB Search/Vector Search | Chỉ mục Search đồng bộ từ dữ liệu, có indexing lag |
| Search index vừa create/rebuild | Có trạng thái build/READY và lag ban đầu |
| Embedding mới chưa được tạo | Vector Search không thể tìm theo embedding chưa tồn tại |

### 23.2. “Đã xóa nhưng vẫn thấy trong Search”

Search index có thể chưa bắt kịp thao tác delete/visibility update. Vì vậy Search result **không được dùng làm nguồn xác thực quyền cuối cùng** cho tài liệu nhạy cảm. Có thể cần canonical DB/security validation ở ranh giới trả dữ liệu/đọc object thực.

### 23.3. Tách search với transaction

~~~text
Search retrieval -> user chọn product ID
    -> kiểm lại current document/tenant/price/stock
    -> chạy guarded write/transaction của nghiệp vụ
~~~

`$search` phù hợp **tìm kiếm/gợi ý**, không thay `findOneAndUpdate` guarded stock reservation hoặc unique constraints.

### 23.4. Nếu “vừa tạo rồi phải tìm thấy ngay” là yêu cầu bắt buộc

Các lựa chọn:

1. API tạo trả product ID/detail trực tiếp, không đợi Search.
2. UI optimistic view hoặc pinned recent item theo ID.
3. Nhánh đọc primary DB theo ID cho records vừa tạo.
4. Thiết kế wait-for-index với deadline nếu Search subsystem có cơ chế kiểm đáng tin cậy, không polling vô hạn.

Không cam kết indexing lag bằng không nếu deployment không bảo đảm.

## 24. Điều tra performance đúng engine

### 24.1. Database `find`/`$text`

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  category: "laptop",
  active: true
}).explain("executionStats");
~~~

Quan sát `winningPlan`/`totalKeysExamined`/`totalDocsExamined`/`nReturned`, index selectivity, sort/limit và query shape. Nhưng database explain không mô tả đầy đủ Lucene Search engine internals; đừng dùng một chỉ số `COLLSCAN` của query khác để kết luận `$search` chắc đang hoạt động sai.

### 24.2. Search metrics

Nên theo dõi:

- Search index health/build/ready status và indexing lag.
- Search query latency p50/p95/p99, timeout/failure rates.
- Search node CPU/memory, queue depth, concurrent load.
- Candidate count, facets/highlights cost, query complexity.
- Results returned vs limit/filter, no-result rate.
- Index version/analyzer và relevance scores sau rollout.

### 24.3. Vector-specific metrics

Đo thêm dimension/index size, `numCandidates`, topK, recall@K, filter selectivity theo tenant/category, embedding latency, model error rate và ANN resource trade-off. Không chỉ đo latency MongoDB mà bỏ qua thời gian sinh query vector bằng model hoặc gọi embedding API bên ngoài.

### 24.4. Benchmark theo mode

~~~text
mode: EXACT / TEXT_BASIC / LEXICAL / SEMANTIC / HYBRID
serverVersion:
springDataVersion:
indexDefinitionVersion:
datasetSize:
tenantCardinality:
queryP95Ms:
throughput:
recallAt10:
timeoutRate:
indexLagP95Ms:
~~~

Dữ liệu benchmark phải đại diện về kích thước, độ dài title, tỉ lệ tenant, index definitions và Search node configuration. Không thay đồng thời model/index/query rồi suy mọi cải thiện do một yếu tố.

### 24.5. Giới hạn Search trên Search nodes

Không phải cứ tăng `numCandidates`/fuzzy complexity là relevance tốt không giới hạn. Quá nhiều candidates tăng CPU và latency, giảm concurrency mà Search node xử lý được. Khi p99 tăng và queue dài, cần phân tích capacity/index/query shapes trước khi tự tăng connection pool Java.

## 25. Kiểm thử phân biệt MongoDB Server và Search service

### 25.1. Tối thiểu hai loại test environments

| Environment | Nên kiểm điều gì? |
| --- | --- |
| MongoDB local/CI thông thường | CRUD, exact/range, `$regex`, `$text`, typed Spring mapping |
| MongoDB deployment có Search/mongot | `$search`, `$searchMeta`, `$vectorSearch`, index readiness/score/filter |
| MongoDB replica set có transaction | Business consistency và guarded updates |
| Production-like Search | Index freshness, latency, resource load, fallback/recovery |

Không dùng “CI MongoDB Docker đã chạy” làm bằng chứng mọi Search stage hỗ trợ. Với local Search có thể dùng môi trường Atlas test hoặc image `mongodb-atlas-local` được MongoDB giới thiệu cho phát triển; image đơn node đó không phải production HA.

### 25.2. Database-only integration test

~~~java
// Snippet trong test có injected MongoTemplate + AssertJ
@Test
void exactLookupUsesDatabaseQuery() {
    Query q = Query.query(
        Criteria.where("tenantId").is("t01")
            .and("sku").is("LT-A100")
    );

    CatalogProduct result =
        mongoTemplate.findOne(q, CatalogProduct.class);

    assertThat(result).isNotNull();
    assertThat(result.getTenantId()).isEqualTo("t01");
    assertThat(result.getSku()).isEqualTo("LT-A100");
}
~~~

Test chỉ cần database indexes và fixture; nó không chứng minh Search index/score hoạt động.

### 25.3. Search integration test checklist

1. Provision Search-capable test deployment.
2. Seed fixture với ít nhất hai tenants có title/embedding rất giống nhau.
3. Apply Search index/Vector index definitions.
4. Chờ index READY bằng deadline hữu hạn.
5. Chờ/kiểm ingestion fixture, tránh assertion chạy quá sớm vì indexing async.
6. Chạy bounded `$search`/`$vectorSearch` và lọc tenant ngay trong stage.
7. Assert **không có document khác tenant** và response fields đúng.
8. Kiểm score field/metadata output nếu API cần hiển thị score.
9. Dọn đúng records/index do test sở hữu; không drop dữ liệu dùng chung.

### 25.4. Test capability và fallback

~~~text
GET /catalog/search?mode=lexical
  -> FEATURE_UNAVAILABLE / SERVICE_UNAVAILABLE khi thiếu Search.

GET /catalog/search?mode=exact
  -> Vẫn chạy theo database query.
~~~

Nếu sản phẩm chủ đích có fallback lexical→basic text, response/UX phải hiển thị rõ mode thực dùng, không giả rằng quality/semantics tương đương.

### 25.5. Test field mappings

Với `CatalogProduct.tenantId` gắn `@Field("tenant_id")`:

- `Criteria.where("tenantId")` của typed `Query` map sang `tenant_id`.
- Raw `$search.compound.filter.path` phải là `tenant_id`.
- Vector index field tạo trong mongosh phải là `tenant_id`.
- Java `VectorIndex.addFilter("tenantId")` có thể được map khi gắn entity context.

Test kết quả với ít nhất hai tenants để phát hiện thiếu điều kiện hoặc sai tên field. Chỉ có fixture tenant t01 thì không thể phát hiện bug vô tình bỏ tenant filter.

### 25.6. Kiểm relevance bằng golden queries

Một integration test assert `result.size()>0` không chứng minh Search hữu ích. Xây tập dữ liệu/query được gán nhãn:

~~~text
query="laptop văn phòng" -> expected relevant IDs/ranking band
query="laptpo"           -> expected fuzzy matches (nếu feature bật)
query="máy tính đồ họa"  -> expected semantic matches
query="LT-A100"          -> expected exact SKU lookup
~~~

Chạy regression mỗi lần đổi analyzer, index schema, boosting hay embedding model. Đo recall/ranking + latency, không chỉ code compile.

## 26. Lỗi thường gặp: xác định lỗi ở đúng tầng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `findById` chạy, `$search` báo unknown stage | Deployment không có Search stage/mongot/version | MongoDB compatibility + Search setup |
| `$search` báo index not found | Sai tên/collection, chưa tạo index | `$listSearchIndexes` |
| Tạo Search index thành công nhưng query chưa thấy record | Index chưa READY hoặc ingestion lag | Status, readiness, delay/metrics |
| `$text` chạy nhưng `$search` lỗi | Database text index không phải Search index | Tạo Search index đúng loại |
| `$search` chạy nhưng `$text` lỗi | Thiếu database text index | `createIndex({field:"text"})` |
| `$vectorSearch` sai dimensions | Query vector khác index model/dimension | Check model/dimensions/format |
| Vector score thấp hoặc kết quả vô nghĩa | Embedding model mismatch hoặc vectors giả | Verify embedding pipeline, evaluate recall |
| Search trả empty dù title rõ có từ | Analyzer/mapping/path/index/tenant filter sai | List index definition, test từng filter |
| `equals` tenant không match | `tenant_id` index type sai, dùng Java field name | Token/filter mapping + BSON paths |
| Có kết quả tenant khác | Thiếu/đặt muộn tenant filter | Filter trong `$search`/`$vectorSearch` |
| TopK thiếu nhiều item hợp lệ | `$limit` trước postfilter tenant | Filter trước candidate ranking |
| `$text` score không giống `$search` score | Khác engine và `$meta` name | `textScore` vs `searchScore` |
| `$searchMeta` không trả products | Metadata stage không phải hits stage | Dùng `$search` để lấy documents |
| Facet không có category | Facet index field type/mapping sai | Check Search facet mapping |
| `$vectorSearch` trong `$lookup` lỗi | Stage composition restriction | Dùng supported pipeline/topology |
| Spring Data class có nhưng runtime lỗi | API client mới hơn capability deployment | Capability matrix + feature test |
| Spring Data version cũ không có `VectorIndex` | API chưa tồn tại ở dependency đó | Align versions, dùng raw BSON |
| `TextQuery` không kích hoạt autocomplete | `TextQuery` là `$text` | Dùng Search autocomplete index/operator |
| `@Aggregation` trả empty dù mongosh query có hits | Field name mapping hoặc annotation binding | Inspect generated BSON + tenant |
| Search result vừa xóa vẫn xuất hiện | Search index lag | Revalidate current state/ACL |
| Index tốn bộ nhớ/CPU tăng nhanh | Dynamic mapping, vector cardinality, analyzer/index churn | Index capacity/definition audit |
| Fuzzy query chậm | Query complexity và candidate explosion | Input limits, fuzzy settings, profiling |
| Local test pass nhưng prod không hỗ trợ feature | Khác topology/version/index/service | Integration tests trên deployment thực |
| HTTP 200 [] khi Search service down | Catch-all exception che unavailable | Error classification/degraded response |

### 26.1. Chuỗi chẩn đoán đề xuất

~~~text
Lỗi Search query
  |
  +-- Stage không được nhận diện?
  |      -> Server version/deployment/service.
  |
  +-- Stage hợp lệ nhưng báo index not found?
  |      -> Collection, index name/type/READY.
  |
  +-- Query chạy nhưng không match?
  |      -> Index mappings, analyzer, BSON fields, filter.
  |
  +-- Match sai tenant?
  |      -> Security/tenant filter placement và mapping.
  |
  +-- Kết quả đúng nhưng chậm?
         -> Index size, candidate limit, search nodes, network,
            embedding latency, query shape và p95/p99.
~~~

Không dùng một khối `catch(Exception) { return Collections.emptyList(); }` để “ổn định API”; nó biến Search outage thành kết quả không match và che khả năng phục hồi.

## 27. Checklist triển khai một search feature

1. Xác nhận **requirement**: exact filter, `$text`, lexical, autocomplete, semantic hay hybrid?
2. Xác nhận **MongoDB Server version/edition/topology**.
3. Xác nhận **mongot/Search service** đã triển khai/healthy trên environment cần dùng.
4. Xác nhận **Spring Data/Java Driver version** có API cần dùng.
5. Thiết kế database indexes cho exact/range queries.
6. Thiết kế text index riêng khi dùng `$text`, không nhầm với Search index.
7. Tạo Search/Vector indexes đúng name/type/definition, version hóa rollout.
8. Chờ Search index READY với deadline và health status rõ ràng.
9. Tạo tenant/ACL filters **trong search/vector stage**, trước topK.
10. Không dùng raw user input để chọn index/path/operator.
11. Validate độ dài query, clauses, candidate count và result limit.
12. Định nghĩa analyzer, synonym/fuzzy/autocomplete behavior theo ngôn ngữ người dùng.
13. Với vector, dùng cùng embedding model/dimension cho query và document.
14. Đặt `$search`/`$searchMeta`/`$vectorSearch` ở vị trí aggregation hợp lệ.
15. Truy xuất đúng `textScore`/`searchScore`/`vectorSearchScore` và không cộng trực tiếp.
16. Định nghĩa pagination/sort, không mặc nhiên tính snapshot stability.
17. Giữ projections/DTO whitelist; không lộ embedding/private metadata.
18. Không dùng Search result làm permission check hoặc stock/price source of truth.
19. Cân nhắc Search indexing lag trong UI và API contracts.
20. Theo dõi latency/recall/no-match/index readiness bằng metrics.
21. Kiểm test capabilities trên **Search-enabled environment**, không chỉ mongod local.
22. Test hai tenants, wrong index name, field mapping và vector dimension mismatch.
23. Quản lý degraded/fallback behavior rõ ràng.
24. Chuẩn bị rollback plan khi đổi index definition/analyzer/model.

## 28. Bài thực hành có đáp án

### Bài 1 — Ba lớp của một Search request

Ứng dụng Spring Data MongoDB có repository method trả `List<CatalogProduct>`. Có thể suy từ type trả về rằng nó dùng Atlas/MongoDB Search?

**Đáp án:** Không. Phải xem BSON query/stage thực tế: repository derived find thường tạo MongoDB database query, trong khi `$search`/`$vectorSearch` chỉ xuất hiện khi code yêu cầu. Search service/index và Spring client API là hai lớp khác nhau.

### Bài 2 — Tìm SKU

Người dùng nhập chính xác `LT-A100`, cần duy nhất một SKU trong tenant t01. Chọn `$vectorSearch` hay database `find`?

**Đáp án:** Database `find` với `{tenant_id:"t01",sku:"LT-A100"}` và unique/compound index `{tenant_id:1,sku:1}`. Vector Search có thể trả kết quả gần nghĩa nhưng **không đúng mã**, không thay unique constraints.

### Bài 3 — Tìm mọi laptop theo giá

Yêu cầu `category=laptop`, `active=true`, giá 10–30 triệu; có cần tạo Search index không?

**Đáp án:** Không mặc định. MongoDB Server query + compound index phù hợp hỗ trợ filter/range. Chỉ chọn Search nếu thêm yêu cầu lexical/fuzzy/relevance hoặc faceting Search-specific.

### Bài 4 — Prefix regex

Tìm SKU bắt đầu bằng `LT-` bằng regex nào?

**Đáp án:**

~~~javascript
db.catalog_advanced_010.find({
  tenant_id: "t01",
  sku: { $regex: "^LT-" }
});
~~~

Với input do user cung cấp, escape regex metacharacters và giới hạn độ dài để tránh regex tùy ý. Prefix anchored có thể tận dụng index tốt hơn nhiều regex không anchored, nhưng phải xem `explain`.

### Bài 5 — `$text` dùng index nào?

Lệnh `db.collection.createIndex({title:"text"})` có tạo `catalog_lexical` cho `$search` không?

**Đáp án:** Không. Nó tạo MongoDB **database text index** cho `$text`; Search index được tạo bằng `createSearchIndex` trên deployment có Search service.

### Bài 6 — Điểm relevance

`$text` sử dụng tên `$meta` nào để trả score? `$search` thì sao?

**Đáp án:** `"textScore"` cho `$text` và `"searchScore"` cho `$search`. Vector Search dùng `"vectorSearchScore"`. Không trộn trực tiếp các giá trị score.

### Bài 7 — Spring `TextQuery`

`TextQuery.queryText(...)` có thực hiện `$search` và hỗ trợ highlight Search DSL không?

**Đáp án:** Không. `TextQuery`/`TextCriteria` là API Spring Data cho **MongoDB `$text`**. Search highlight cần Search service/index và DSL `$search` phù hợp.

### Bài 8 — Phiên bản self-managed

Có đúng là `$search` và `$vectorSearch` luôn chỉ có ở MongoDB Atlas không?

**Đáp án:** Không còn đúng khi nói tuyệt đối. Tài liệu MongoDB hiện hành mô tả self-managed MongoDB Community 8.2+ và Enterprise 8.2+ theo đường được hỗ trợ, với **mongot riêng** và điều kiện edition/operator. Một server Community 8.0 standalone thông thường **không** tự có Search chỉ nhờ chạy Spring Data phiên bản mới.

### Bài 9 — Java API có nhưng server không có

Lập trình viên dùng `VectorSearchOperation` của Spring Data và unit test compile. Production chỉ là mongod không triển khai mongot. Điều gì xảy ra?

**Đáp án:** Query có thể thất bại khi thực thi `$vectorSearch` vì server/deployment không hỗ trợ. Java builder không cài Search service, không tạo vector index và không thay MongoDB version gate.

### Bài 10 — Thứ tự `$search`

Có thể đặt `$match:{tenant_id:"t01"}` trước `$search` trong cùng aggregation pipeline không?

**Đáp án:** Không theo quy tắc `$search` phải là stage đầu pipeline chứa nó. Đưa tenant filter vào `$search.compound.filter`, có index field type phù hợp, trước ranking/limit.

### Bài 11 — Post-filter sau topK

Pipeline Search top 5 toàn cluster rồi `$match` tenant t01. Nếu tenant t01 có 100 sản phẩm match nhưng toàn bộ nằm ngoài top 5 toàn cluster, API trả bao nhiêu?

**Đáp án:** Có thể trả **0** — một kết quả thiếu dù tenant có nhiều match. Tenant pre-filter phải ở trong search stage, không sau topK.

### Bài 12 — Index string type

Search index khai báo `tenant_id` như analyzed `string` nhưng query sử dụng `equals` exact token. Có thể mặc định đúng không?

**Đáp án:** Không. `equals` yêu cầu field được mapping theo kiểu hỗ trợ exact matching (ví dụ `token`); phải kiểm Search index definition/operator compatibility.

### Bài 13 — Search index READY

`createSearchIndex()` trả success và `exists("catalog_lexical")==true`. Có thể tuyên bố index đã sẵn sàng query ngay?

**Đáp án:** Không. Index có build/sync lifecycle; kiểm status như `$listSearchIndexes` hoặc Spring Data `SearchIndexOperations.status(...)`, đợi READY với deadline.

### Bài 14 — `$searchMeta`

Muốn lấy các bucket category và số kết quả tìm kiếm, dùng `$searchMeta` hay `$text`?

**Đáp án:** `$searchMeta` với Search facet/count khi Search index/service hỗ trợ. `$searchMeta` trả **metadata**, không phải danh sách hits. Lưu ý `count.lowerBound` không phải exact total.

### Bài 15 — Facet khi field không được index

Search facet theo category trả sai/không có dữ liệu. Có phải Spring Data projection sai?

**Đáp án:** Chưa chắc. Trước hết kiểm Search index field mappings/facet-compatible type, index readiness, operator path, Search DSL. Java DTO mapping là bước sau.

### Bài 16 — Embedding sai kích thước

Vector index khai báo `numDimensions=4` nhưng query vector có 1536 giá trị. Server có tự cắt vector không?

**Đáp án:** Không nên kỳ vọng. Query phải đúng dimensions/format và embedding space; mismatch gây lỗi hoặc không hợp lệ. Cần validate model version và vector length trước query.

### Bài 17 — Vector pre-filter

Vector index chỉ có `embedding`, thiếu field `tenant_id` kiểu filter. App chạy top 10 toàn cluster rồi lọc tenant. Vấn đề?

**Đáp án:** Sai candidate set, có thể bỏ sót sản phẩm tenant cần và xử lý dữ liệu ngoài tenant. Thêm `tenant_id` vào vector index kiểu filter và đưa điều kiện vào `$vectorSearch.filter`.

### Bài 18 — ANN vs ENN

Nếu query đòi search nearest neighbor chính xác tuyệt đối, có nên mặc định chạy ANN với `numCandidates=limit`?

**Đáp án:** Không. ANN có recall/speed trade-off; ENN/exact mode cần kiểm server/version và tài nguyên. Đánh giá recall@K và latency; ANN không bảo đảm exact topK chỉ nhờ số candidates nhỏ.

### Bài 19 — Score fusion

Search lexical trả score 5.2, vector trả 0.88. Có thể cộng và tuyên bố score 6.08 tốt hơn score khác không?

**Đáp án:** Không. Thang đo khác nhau. Cần rank fusion (như RRF), score normalization với evaluation hoặc native fusion stage phù hợp version.

### Bài 20 — Spring raw path mapping

Entity Java field `tenantId` có `@Field("tenant_id")`. Trong raw BSON `$search.compound.filter.equals.path` cần dùng gì?

**Đáp án:** Dùng `"tenant_id"` đúng tên BSON/Search index mapping. Đừng giả định raw `Document` được Spring tự map như typed `Criteria.where("tenantId")`.

### Bài 21 — Spring repository

Method `findByTitleContaining("laptop")` mặc định bật fuzzy/typo matching của MongoDB Search không?

**Đáp án:** Không. Đó là derived database query, có thể dùng regex theo keyword semantics. Muốn fuzzy/autocomplete cần Search-specific index và stage/API.

### Bài 22 — Reactive Search

`ReactiveMongoTemplate.aggregate(...)` trả `Flux<Document>`. Nó có làm Search index cập nhật đồng bộ hơn so với `MongoTemplate` không?

**Đáp án:** Không. Reactive chỉ khác I/O/lifecycle ở client. Search service/index và consistency là server-side capability riêng.

### Bài 23 — Indexing lag

Sau `repository.insert(product)`, `findById` thấy document nhưng `$search` chưa thấy. Có nên retry `insert` cho tới khi Search thấy?

**Đáp án:** Không. Có thể gây duplicate/side effect. Hãy kiểm Search readiness/lag và thiết kế UI read-by-ID, optimistic recent item hoặc đợi có deadline, không lặp business write.

### Bài 24 — ACL khi Search lag

User bị thu hồi quyền xem document, nhưng Search index chưa cập nhật visibility. Query có thể trả result cũ. Làm thế nào bảo vệ?

**Đáp án:** Không dựa Search index làm permission source of truth cuối cùng; revalidate quyền/current DB state trước khi trả dữ liệu nhạy cảm. Có thể giữ visibility filter trong Search để giảm candidates nhưng vẫn tính đến lag.

### Bài 25 — Test phù hợp

Một test `@DataMongoTest` trên mongod Docker cũ chạy `findBySku` thành công. Đã chứng minh `$search`/`$vectorSearch` chạy tốt chưa?

**Đáp án:** Chưa. Cần Search-enabled environment (Atlas/mongot self-managed/atlas-local phù hợp), indexes READY và integration test trực tiếp stages tương ứng.

### Bài 26 — Search outage

API khi mongot lỗi lại trả `200 OK []`. Vấn đề gì?

**Đáp án:** Nó đánh đồng “không có kết quả” với “dịch vụ không khả dụng”, gây sai UI/analytics và che lỗi vận hành. Trả error/degraded mode có contract rõ, không swallow mọi exception.

### Bài 27 — Phân trang

`$search` trả 10.000 matches. Client dùng `$skip:9900` rồi `$limit:20`. Có nên coi đây là lựa chọn ổn định/hiệu quả mặc định?

**Đáp án:** Không. Offset sâu có chi phí và kết quả có thể thay đổi khi index/dữ liệu thay đổi. Cân nhắc Search pagination token (`searchAfter/searchBefore` khi version hỗ trợ), sort/ranking và consistency policy.

### Bài 28 — Quyền tạo index

Một controller cho user nhập tùy ý Search index definition rồi gọi `searchIndexOps.createIndex(...)`. Rủi ro?

**Đáp án:** Mở đường thay đổi schema/quyền, tiêu tốn tài nguyên và có thể lộ dữ liệu. Quản lý index qua migration/infra với quyền giới hạn và review/rollout, không tạo mỗi request.

## Tài liệu tham khảo

Các tài liệu sau là nguồn chính thức; kiểm **version mà dự án thực sự dùng** vì MongoDB Search (đặc biệt self-managed, vector và hybrid) đang phát triển, còn một số Spring Data/Javadoc vẫn dùng tên “Atlas Search”:

- [MongoDB Manual — Index Types](https://www.mongodb.com/docs/manual/core/indexes/index-types/): B-tree, multikey, text, geospatial, wildcard và cách phân loại database indexes.
- [MongoDB Manual — Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/): `$text` và giới hạn text index.
- [MongoDB Manual — `$text` in Aggregation](https://www.mongodb.com/docs/manual/tutorial/text-search-in-aggregation/): `$match`, `textScore` và stage restrictions.
- [MongoDB Search — Self-managed Deployments](https://www.mongodb.com/docs/search/self-managed/current/): `mongot`, Community/Enterprise 8.2+, local testing và production deployment paths.
- [MongoDB Search — Self-managed Feature Limitations](https://www.mongodb.com/docs/search/self-managed/current/limitations/): những điểm tương đồng/khác biệt với Atlas.
- [MongoDB Search — `$search`](https://www.mongodb.com/docs/search/query/aggregation-stages/search/): lexical Search DSL, index, query operators, stage position và scoring.
- [MongoDB Search — `$searchMeta`](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/): metadata, facets, counts và restrictions.
- [MongoDB Search — Counting Results](https://www.mongodb.com/docs/search/query/counting/): `total` vs `lowerBound`, `$$SEARCH_META`.
- [MongoDB Search — Create Search Index](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/): syntax `createSearchIndex`, Search/Vector types và index build.
- [MongoDB Search — Search Query Syntax](https://www.mongodb.com/docs/search/query/query-syntax/): lựa chọn `$search`/`$searchMeta` và pipeline composition.
- [MongoDB Manual — `$vectorSearch`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/vectorsearch/): compatibility, query syntax, pre-filter và stage limitations.
- [MongoDB Search — Feature Compatibility](https://www.mongodb.com/docs/search/deployment/feature-compatibility/): capability theo deployment/version.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Criteria`, `TextQuery`, `TextCriteria`, score và query mapping.
- [Spring Data MongoDB — MongoDB Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mongo-search-indexes.html): `VectorIndex`, `SearchIndexOperations`, `VectorSearchOperation`.
- [Spring Data MongoDB — Repository Vector Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/vector-search.html): `@VectorSearch`, `Vector`, `Score`, `SearchResults<T>`.
- [Spring Data MongoDB — `VectorSearchOperation` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/VectorSearchOperation.html): builder, filters, score, version-specific API.
- [Spring Data MongoDB — `VectorIndex` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/VectorIndex.html): vector/filter fields và similarity config.
- [Spring Data MongoDB — `SearchIndexOperations` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/SearchIndexOperations.html): create/update/status/exists Search indexes.
