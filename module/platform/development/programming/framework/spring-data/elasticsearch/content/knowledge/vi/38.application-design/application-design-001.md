# Tách Document tìm kiếm khỏi Entity cơ sở dữ liệu nghiệp vụ

Trong một ứng dụng Spring, entity của database và document trong Elasticsearch thường phục vụ hai mục đích khác nhau. Entity nghiệp vụ mô tả dữ liệu có thẩm quyền, quy tắc và vòng đời của domain. Search document được tổ chức để truy vấn nhanh, lọc, sort, aggregation và hiển thị kết quả theo nhu cầu tìm kiếm.

Nếu dùng cùng một class cho cả hai nơi, mô hình lưu trữ của database sẽ dần bị chi phối bởi cách Elasticsearch cần dữ liệu; ngược lại, mapping tìm kiếm có thể bị giới hạn bởi cấu trúc chuẩn hóa của database. Khi thêm field phục vụ search, đổi analyzer, denormalize dữ liệu hoặc xây một index khác, thay đổi có thể lan sang entity nghiệp vụ và các luồng ghi không liên quan.

Một thiết kế rõ ràng tách ba khái niệm:

- **Domain model / database entity:** biểu diễn dữ liệu nghiệp vụ và là nguồn có thẩm quyền.
- **Search document:** projection được thiết kế riêng cho truy vấn đọc.
- **Projection pipeline:** cơ chế chuyển thay đổi nghiệp vụ thành document Elasticsearch, có thể chạy bất đồng bộ và xây dựng lại.

Đây là một ứng dụng phổ biến của CQRS: command side cập nhật trạng thái nghiệp vụ; query side đọc một mô hình được tối ưu riêng. Tách model không bắt buộc mọi ứng dụng phải triển khai CQRS phức tạp, nhưng giúp giữ ranh giới dữ liệu rõ khi search requirements khác với persistence requirements.

## 1. Vì sao không nên dùng chung một entity?

Giả sử hệ thống quản lý sản phẩm có database quan hệ:

~~~text
Product
  id
  sku
  name
  description
  category_id
  brand_id
  price
  status
  created_at
  updated_at

Category
  id
  name

Brand
  id
  name

Inventory
  product_id
  warehouse_id
  available_quantity
~~~

Database được chuẩn hóa để tránh lặp dữ liệu và bảo đảm quy tắc nghiệp vụ. Một trang tìm kiếm sản phẩm lại cần dữ liệu phẳng:

~~~json
{
  "id": "p-100",
  "sku": "KB-100",
  "name": "Wireless Keyboard",
  "description": "Compact keyboard for work",
  "categoryName": "Accessories",
  "brandName": "Northwind",
  "price": 49.90,
  "status": "ACTIVE",
  "available": true,
  "availableQuantity": 18,
  "searchText": "Wireless Keyboard Compact keyboard for work Northwind Accessories"
}
~~~

Search document có thể lặp categoryName, brandName và một số trường inventory để tránh join hoặc nhiều lần lookup khi truy vấn. searchText có thể là field được tạo riêng cho full-text search. Đây là một read model, không phải entity chuẩn hóa dùng để cập nhật nghiệp vụ.

Nếu dùng cùng class Product cho JPA và Elasticsearch:

- Annotation JPA và Elasticsearch cùng xuất hiện trong một model.
- Một thay đổi mapping Elasticsearch có thể tác động class persistence.
- Field denormalized có thể bị hiểu nhầm là dữ liệu gốc có thể ghi.
- Entity có thể mang quan hệ lazy hoặc proxy mà converter search không nên xử lý.
- Một thao tác save có nguy cơ cập nhật sai hệ thống hoặc ghi dữ liệu không đầy đủ.
- Nhiều index với cấu trúc khác nhau khó có model riêng.

Tách document giúp mỗi mô hình tiến hóa theo nhu cầu của nó.

## 2. Phân biệt Domain Entity, Database Entity và Search Document

Ba khái niệm có liên quan nhưng không nhất thiết là một class.

| Model | Mục tiêu | Ví dụ trách nhiệm |
|---|---|---|
| Domain entity/aggregate | Bảo vệ invariant và hành vi nghiệp vụ | Product đổi trạng thái, kiểm tra SKU |
| Database entity | Ánh xạ persistence schema | ProductEntity, CategoryEntity |
| Search document | Tối ưu truy vấn đọc | ProductSearchDocument |

Trong ứng dụng nhỏ, domain entity và database entity có thể dùng chung. Nhưng search document vẫn nên tách khi cấu trúc tìm kiếm khác rõ rệt.

Ví dụ domain:

~~~java
public class Product {

    private final ProductId id;
    private final Sku sku;
    private String name;
    private ProductStatus status;
    private Money price;

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Product name is required");
        }
        this.name = newName.trim();
    }

    public void activate() {
        this.status = ProductStatus.ACTIVE;
    }
}
~~~

Database entity có thể dùng annotation JPA và quan hệ:

~~~java
@Entity
@Table(name = "products")
public class ProductEntity {

    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    private CategoryEntity category;

    @ManyToOne(fetch = FetchType.LAZY)
    private BrandEntity brand;

    @Enumerated(EnumType.STRING)
    private ProductStatus status;

    private BigDecimal price;

    @Version
    private long version;
}
~~~

Search document có mapping riêng:

~~~java
@Document(indexName = "products-read")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String name;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String description;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Keyword)
    private String categoryName;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String brandName;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private boolean available;

    @Field(type = FieldType.Long)
    private long sourceVersion;
}
~~~

Các class là ví dụ minh họa; getter, constructor, mapping settings và kiểu ID cần phù hợp với dự án. Điểm quan trọng là ProductSearchDocument chứa các field phục vụ truy vấn và không có hành vi thay đổi trạng thái nghiệp vụ như aggregate Product.

## 3. Search document là projection, không phải nguồn dữ liệu gốc

Projection là biểu diễn được tạo từ dữ liệu có thẩm quyền. Với sản phẩm, projection có thể kết hợp:

- Product từ database.
- Category name từ bảng category.
- Brand name từ bảng brand.
- Trạng thái tồn kho từ inventory service hoặc database.
- Các field tìm kiếm được tạo từ name/description.

Một document có thể chứa dữ liệu của nhiều aggregate hoặc bảng. Điều này hợp lý cho read model vì mục tiêu là trả kết quả nhanh và phù hợp use case.

Tuy nhiên, khi document lặp dữ liệu từ nhiều nguồn, cần xác định:

- Nguồn nào sở hữu từng field.
- Event nào làm projection cần cập nhật.
- Dữ liệu có thể cũ tối đa bao lâu.
- Khi một nguồn thay đổi, projection được tính lại như thế nào.
- Có thể tái tạo toàn bộ document từ source of truth hay không.

Không cho phép API cập nhật trực tiếp categoryName trong search document nếu tên danh mục có thẩm quyền nằm ở CategoryEntity. Consumer cần đọc nguồn có thẩm quyền hoặc nhận event đủ thông tin để tạo projection đúng.

## 4. Thiết kế document theo query, không sao chép schema database

Search document nên phản ánh các truy vấn cần phục vụ.

Ví dụ màn hình tìm kiếm cần:

- Full-text search trên tên và mô tả.
- Filter theo category, brand và status.
- Range query theo price.
- Sort theo giá và ngày cập nhật.
- Aggregation đếm sản phẩm theo category.
- Hiển thị tên category và brand ngay trong kết quả.

Mapping tương ứng có thể là:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "product_text": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "sku": { "type": "keyword" },
      "name": {
        "type": "text",
        "analyzer": "product_text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "description": {
        "type": "text",
        "analyzer": "product_text"
      },
      "categoryId": { "type": "keyword" },
      "categoryName": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
      },
      "brandId": { "type": "keyword" },
      "brandName": { "type": "keyword" },
      "price": { "type": "scaled_float", "scaling_factor": 100 },
      "status": { "type": "keyword" },
      "available": { "type": "boolean" },
      "sourceVersion": { "type": "long" }
    }
  }
}
~~~

Mapping trên là ví dụ; chọn scaled_float, double hoặc kiểu số khác theo độ chính xác tiền tệ và cách query. Nếu dùng scaled_float, thống nhất scaling factor và quy tắc làm tròn. Không lưu tiền dưới dạng text nếu cần range/sort theo số.

name là text để full-text search và có multi-field keyword cho exact sort/aggregation. categoryId là keyword để filter chính xác. categoryName có thể là text hoặc keyword tùy yêu cầu tìm kiếm và aggregation.

## 5. Denormalization có chủ đích

Database thường chuẩn hóa dữ liệu, trong khi search document thường denormalize để tối ưu đọc. Denormalization không phải lỗi thiết kế nếu có quy tắc đồng bộ rõ ràng.

Ví dụ categoryName được sao chép vào nhiều product documents. Khi category đổi tên:

~~~text
Category "Accessories" -> "Computer Accessories"
                 |
                 v
          CategoryRenamed event
                 |
                 v
       Find affected product IDs
                 |
                 v
      Update product search documents
~~~

Có một số cách cập nhật:

1. Consumer nhận event và cập nhật các product document liên quan.
2. Consumer nhận event rồi đọc lại category và các product từ database để dựng projection mới.
3. Tạo một index read model khác hoặc dùng query-time enrichment nếu số lượng dữ liệu và SLA cho phép.

Nếu category có rất nhiều sản phẩm, một event đổi tên có thể kích hoạt lượng lớn cập nhật. Cần xử lý theo batch, checkpoint và retry, không giữ một request đồng bộ mở để cập nhật tất cả.

### 5.1. Lưu ID và label cùng lúc

Search document thường nên giữ cả ID và tên hiển thị:

~~~json
{
  "categoryId": "cat-7",
  "categoryName": "Accessories"
}
~~~

ID dùng cho filter chính xác, routing tới domain/API và đồng bộ. Tên dùng hiển thị, full-text search hoặc aggregation. Chỉ lưu tên có thể gây khó xử lý khi tên thay đổi hoặc trùng nhau.

### 5.2. Chọn nested, object hay flatten

Nếu document chứa danh sách biến thể:

~~~json
{
  "variants": [
    { "color": "black", "size": "M", "stock": 5 },
    { "color": "white", "size": "L", "stock": 2 }
  ]
}
~~~

Nếu cần bảo toàn quan hệ giữa field của cùng một phần tử khi query (ví dụ color black và size M phải thuộc cùng variant), cân nhắc mapping nested. Với object thông thường, các giá trị mảng có thể bị flatten và query kết hợp field có thể khớp chéo giữa các phần tử.

nested có chi phí lưu trữ và query riêng. Không chọn nó chỉ vì JSON có mảng object; chọn dựa trên ngữ nghĩa truy vấn. Search document là mô hình đọc nên có thể cấu trúc khác database, miễn đáp ứng đúng điều kiện tìm kiếm.

## 6. Xây projection từ database entity

Không nên để controller hoặc repository search tự chuyển đổi tùy tiện entity database thành document. Tạo mapper hoặc projection factory có trách nhiệm rõ ràng:

~~~java
public class ProductSearchDocumentMapper {

    public ProductSearchDocument toDocument(
            ProductEntity product,
            CategoryEntity category,
            BrandEntity brand,
            InventorySummary inventory
    ) {
        ProductSearchDocument document =
                new ProductSearchDocument();

        document.setId(product.getId().toString());
        document.setSku(product.getSku());
        document.setName(product.getName());
        document.setDescription(product.getDescription());
        document.setCategoryId(category.getId().toString());
        document.setCategoryName(category.getName());
        document.setBrandId(brand.getId().toString());
        document.setBrandName(brand.getName());
        document.setPrice(product.getPrice());
        document.setStatus(product.getStatus().name());
        document.setAvailable(inventory.availableQuantity() > 0);
        document.setSourceVersion(product.getVersion());

        return document;
    }
}
~~~

Mapper chỉ nên làm chuyển đổi dữ liệu. Quyết định lấy nguồn nào, xử lý dữ liệu thiếu và bảo đảm version mới nhất thuộc về projection service hoặc query handler.

Nếu cần nhiều bảng, tránh gọi repository lặp lại cho từng product gây N+1 query. Có thể lấy dữ liệu bằng join/projection query ở database hoặc batch-load các reference theo tập ID rồi map trong bộ nhớ.

### 6.1. Tránh phụ thuộc lazy proxy

JPA entity có quan hệ LAZY. Nếu mapper truy cập quan hệ sau khi transaction đóng, có thể gặp LazyInitializationException. Nếu map bên trong transaction nhưng mỗi entity kích hoạt query riêng, có thể gây N+1.

Giải pháp:

- Dùng query projection/DTO ở database để lấy đúng dữ liệu cần cho search document.
- Fetch join hoặc entity graph khi phù hợp.
- Batch-load category/brand/inventory theo danh sách ID.
- Chỉ tạo search document từ dữ liệu đã được nạp đầy đủ.

Không nên serialize trực tiếp toàn bộ JPA entity sang Elasticsearch. Điều đó có thể kéo theo proxy, quan hệ vòng, field nội bộ và dữ liệu không cần thiết.

## 7. Đồng bộ database và Elasticsearch: tránh dual write

Một cách tưởng như đơn giản:

~~~java
@Transactional
public void renameProduct(UUID id, String newName) {
    ProductEntity product = productRepository.findById(id)
            .orElseThrow();

    product.setName(newName);
    productRepository.save(product);

    elasticsearchOperations.save(
            mapper.toDocument(product)
    );
}
~~~

Đoạn code này có rủi ro dual write. Database và Elasticsearch là hai hệ thống độc lập. Một tình huống:

1. Database commit thành công.
2. Elasticsearch unavailable.
3. Method ném exception.
4. Transaction database có thể đã commit tùy thứ tự và transaction manager; không có rollback chung bảo đảm cả hai nơi trở lại trạng thái trước.

Hoặc Elasticsearch ghi thành công nhưng database rollback. Hai nơi sẽ lệch nhau.

Không nên dựa vào một annotation @Transactional thông thường để làm hai hệ thống commit nguyên tử. Cần một cơ chế đồng bộ có thể phục hồi.

## 8. Transactional Outbox cho projection

Outbox giải quyết khoảng trống giữa commit database và publish event bằng cách ghi event trong cùng transaction với thay đổi nghiệp vụ.

Luồng:

~~~text
Command
  |
  v
Database transaction
  |                    |
  v                    v
Update Product      Insert Outbox Event
  |                    |
  +---------+----------+
            |
            v
          Commit
            |
            v
      Outbox Publisher
            |
            v
        Message/Event
            |
            v
     Projection Consumer
            |
            v
  Build ProductSearchDocument
            |
            v
   ElasticsearchOperations.save
~~~

Ví dụ:

~~~java
@Transactional
public void renameProduct(UUID productId, String newName) {
    ProductEntity product = productRepository.findById(productId)
            .orElseThrow();

    product.rename(newName);
    productRepository.save(product);

    outboxRepository.save(
            OutboxEvent.productChanged(
                    product.getId(),
                    product.getVersion()
            )
    );
}
~~~

Publisher đọc event đã commit rồi gửi tới broker hoặc consumer. Consumer có thể nhận ID và version, đọc dữ liệu hiện tại từ database, dựng lại ProductSearchDocument và ghi vào Elasticsearch.

Outbox không làm Elasticsearch trở thành một phần của database transaction. Nó bảo đảm event được lưu bền vững cùng thay đổi nguồn, để publisher có thể gửi lại sau lỗi.

### 8.1. Event mang dữ liệu hay chỉ mang ID?

Có hai dạng thường gặp:

**Event mang snapshot/payload:** chứa dữ liệu cần cho projection. Consumer không cần đọc lại nhiều bảng, nhưng event có thể lớn và phải quản lý schema/version.

**Event chỉ mang aggregate ID và version:** consumer đọc lại dữ liệu hiện tại từ source of truth. Event nhỏ và projection luôn dựa trên trạng thái mới nhất, nhưng consumer cần truy cập database và phải xử lý trường hợp có nhiều event dồn lại.

Ví dụ event tối giản:

~~~java
public record ProductChanged(
        UUID productId,
        long aggregateVersion,
        Instant occurredAt
) {
}
~~~

Nếu consumer nhận event version 8 nhưng database đã ở version 10, nó có thể dựng projection từ trạng thái version 10. Điều này phù hợp khi mục tiêu là cập nhật read model tới trạng thái mới nhất, không phải phát lại mọi trạng thái trung gian.

Nếu cần phản ánh chính xác từng transition, audit hoặc side effect, event cần mang đủ thông tin và được xử lý theo thứ tự.

## 9. Consumer idempotent và xử lý event đến trùng

Outbox publisher thường hoạt động theo at-least-once delivery: nếu không chắc đã publish thành công, nó có thể gửi lại. Consumer phải chịu được event trùng.

Với projection kiểu trạng thái tuyệt đối:

- Dùng document ID ổn định, ví dụ product ID.
- Lưu sourceVersion trong search document.
- Không áp dụng event có version cũ hơn version đã được index.
- Nếu event trùng cùng version và cùng nội dung, ghi lại hoặc bỏ qua đều phải giữ kết quả nhất quán.

Pseudo-code:

~~~java
public void handle(ProductChanged event) {
    ProductEntity current =
            productRepository.findById(event.productId())
                    .orElseThrow();

    ProductSearchDocument candidate =
            mapper.toDocument(current);

    ProductSearchDocument indexed =
            searchDocumentReader.findById(candidate.getId());

    if (indexed != null
            && indexed.getSourceVersion() >= candidate.getSourceVersion()) {
        return;
    }

    elasticsearchOperations.save(candidate);
}
~~~

Đây là minh họa logic, chưa phải thao tác compare-and-set nguyên tử. Hai consumer đồng thời có thể cùng đọc version cũ rồi ghi theo thứ tự không mong muốn. Với concurrency thực tế, cần serialize theo aggregate key, dùng external versioning hoặc optimistic concurrency ở Elasticsearch, hoặc một cơ chế update có điều kiện nguyên tử.

Không dùng một lần get rồi save như thể đó là compare-and-set. Giữa hai thao tác vẫn có race condition.

### 9.1. External versioning và optimistic concurrency

Elasticsearch hỗ trợ các cơ chế kiểm soát version ở cấp document. Có thể dùng if_seq_no/if_primary_term cho thao tác dựa trên phiên bản document đã đọc, hoặc external versioning khi version nghiệp vụ đáp ứng yêu cầu và API hỗ trợ.

Chọn cơ chế dựa trên semantics:

- Elasticsearch internal version bảo vệ thao tác theo phiên bản storage đã đọc.
- Aggregate version trong event cho biết thứ tự trạng thái nghiệp vụ.
- External version có thể từ chối ghi một version cũ hơn nếu dùng đúng mode.

Hai loại version không đồng nghĩa. @Version trên entity Spring Data Elasticsearch thường dùng cho optimistic locking của document, không tự động là aggregate version từ database. Nếu cần bảo vệ projection theo database version, hãy ánh xạ và áp dụng version nghiệp vụ một cách tường minh.

## 10. Xử lý update và delete trong projection

Projection consumer phải xử lý mọi loại thay đổi:

| Domain event | Hành động trên search index |
|---|---|
| ProductCreated | Tạo document |
| ProductRenamed | Cập nhật document |
| ProductPriceChanged | Cập nhật price và version |
| ProductDeactivated | Cập nhật status hoặc xóa theo yêu cầu search |
| ProductDeleted | Xóa document hoặc tạo tombstone |
| CategoryRenamed | Cập nhật categoryName trên document liên quan |

### 10.1. Delete và event đến trễ

Giả sử ProductDeleted version 12 đến trước ProductUpdated version 11. Nếu consumer xóa document rồi event cũ version 11 đến, nó có thể tạo lại document đã xóa.

Để tránh resurrection:

- Giữ version/tombstone của entity đã xóa trong một khoảng thời gian cần thiết.
- Bỏ qua event có version thấp hơn hoặc bằng tombstone version.
- Hoặc đảm bảo thứ tự event theo aggregate ID và consumer xử lý tuần tự.

Nếu xóa hẳn document, metadata version có thể không còn để so sánh event cũ. Một tombstone projection có thể giữ ID, deleted=true và sourceVersion để chặn event trễ. Sau thời gian retention, có thể purge tombstone khi chắc chắn event cũ không còn được replay.

### 10.2. Soft delete và filter tìm kiếm

Nếu database dùng soft delete, search document cần thể hiện trạng thái tương ứng. Có thể:

- Không index document đã xóa.
- Giữ document với deleted=true và thêm filter bắt buộc ở query.
- Giữ tombstone riêng để bảo vệ version/order.

Chọn theo yêu cầu audit, restore và search. Nếu dùng deleted=true, mọi query public phải luôn thêm filter server-side để không lộ record đã xóa.

## 11. Search API đọc document, command API đọc entity nghiệp vụ

Khi tách model, các API nên dùng đúng nguồn:

~~~text
Command: đổi tên sản phẩm
    |
    v
Product application service
    |
    v
Domain / database repository
    |
    v
Database transaction + outbox

Query: tìm kiếm sản phẩm
    |
    v
Product search service
    |
    v
ElasticsearchRepository / ElasticsearchOperations
    |
    v
ProductSearchDocument
~~~

Command API cần kiểm tra invariant và cập nhật source of truth. Search API cần truy vấn projection tối ưu cho đọc. Nếu user mở trang chi tiết cần dữ liệu chính xác mới nhất, có thể lấy ID từ search result rồi đọc entity nghiệp vụ từ database.

Một mẫu kết hợp:

1. Search Elasticsearch trả ID, score và các field tóm tắt.
2. Người dùng chọn một sản phẩm.
3. Detail service đọc product từ database theo ID.
4. Business action được thực hiện trên domain entity/database.

Không dùng search document làm đầu vào trực tiếp cho command quan trọng nếu nó có thể stale hoặc thiếu field nghiệp vụ.

## 12. Search document có thể khác nhau theo use case

Không nhất thiết chỉ có một document cho mỗi aggregate. Các màn hình có thể cần read model khác nhau:

- ProductSearchDocument: tìm kiếm sản phẩm.
- ProductSuggestionDocument: autocomplete/suggest.
- ProductInventoryDocument: tra cứu tồn kho theo kho hàng.
- CatalogLandingDocument: dữ liệu đã tổng hợp cho trang danh mục.

Mỗi projection có thể có index, analyzer và field riêng. Tránh tạo quá nhiều index trùng lặp nếu query có thể phục vụ từ một document hợp lý; nhưng cũng không ép một document phình to để đáp ứng mọi màn hình.

Quyết định dựa trên query pattern và SLA, tần suất cập nhật từng nguồn, kích thước document và số lượng bản sao dữ liệu, chi phí fan-out update, khả năng rebuild, yêu cầu bảo mật và retention.

## 13. Không đưa mọi dữ liệu liên quan vào một document

Denormalization giúp giảm lookup nhưng làm tăng chi phí cập nhật. Nếu một sản phẩm có hàng triệu lượt xem và mỗi lượt xem thay đổi một counter, cập nhật document product liên tục có thể gây contention.

Hãy cân nhắc:

- Field nào cần filter/sort/aggregation trực tiếp.
- Field nào có thể lấy từ API detail sau khi search.
- Field nào có thể tính theo batch.
- Field nào cần cập nhật real-time và field nào chấp nhận trễ.
- Có cần tách read model theo tần suất cập nhật hay không.

Không index một object khổng lồ chỉ vì database entity có nhiều quan hệ. Mỗi field thêm vào document đều ảnh hưởng dung lượng, mapping, indexing cost và tốc độ update.

## 14. Rebuild search index từ source of truth

Một lợi ích lớn của việc tách projection là có thể xóa và xây lại search index từ database/event history.

Quy trình rebuild cơ bản:

1. Tạo index mới với mapping/settings mới.
2. Đọc dữ liệu nguồn theo batch và dựng search documents.
3. Bulk index vào index mới.
4. Theo dõi lỗi từng item, retry item tạm thời và lưu checkpoint.
5. Đồng bộ các thay đổi phát sinh trong lúc backfill.
6. Kiểm tra số lượng, version, các query quan trọng và dữ liệu mẫu.
7. Chuyển read alias sang index mới.
8. Giữ index cũ một khoảng thời gian để rollback nếu cần.

Không nên xóa index đang phục vụ production trước khi index mới được kiểm chứng. Dùng alias để chuyển đổi:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    }
  ]
}
~~~

Alias switch trong một request là thao tác phù hợp để chuyển read target. Cần bảo đảm alias tồn tại đúng và index mới đã hoàn tất backfill/validation trước khi chuyển.

### 14.1. Đồng bộ thay đổi trong lúc backfill

Nếu chỉ scan database rồi cuối cùng đổi alias, thay đổi phát sinh trong lúc scan có thể không có trong index mới hoặc bị ghi đè bởi snapshot cũ.

Một cách phổ biến:

- Ghi nhận watermark/event position trước khi bắt đầu backfill.
- Backfill snapshot theo batch.
- Replay event từ watermark để áp dụng thay đổi mới.
- Dùng aggregate version để bỏ qua event cũ hoặc phát hiện khoảng trống.
- Chỉ chuyển alias khi projection bắt kịp.

Một lựa chọn khác là dual projection tạm thời sang index cũ và index mới, nhưng cần kiểm soát thứ tự và idempotency. Không nên ghi đồng thời hai index một cách tùy tiện trong request nghiệp vụ nếu chưa có cơ chế phục hồi.

## 15. Version schema của search document

Search document có thể thay đổi độc lập với database entity. Ví dụ:

- v1 lưu categoryName.
- v2 thêm categoryPath và đổi analyzer.
- v3 tách suggestName thành field riêng.

Không nên giả định một class thay đổi mapping sẽ tự cập nhật index đang tồn tại. Một số thay đổi field type/analyzer yêu cầu tạo index mới và reindex.

Quản lý:

- Version mapping/index.
- Version event schema nếu event chứa snapshot.
- Mapper từ database/domain sang từng projection version.
- Quy trình backfill/rebuild.
- Alias read/write và thời điểm cutover.

Nếu event chỉ mang ID và version rồi consumer đọc source hiện tại, rebuild document version mới có thể đơn giản hơn vì mapper mới tạo projection mới từ cùng dữ liệu nguồn.

## 16. Kiểm thử ranh giới giữa hai model

Nên có các nhóm test:

### 16.1. Mapper test

Đưa database entity/DTO và các reference vào mapper, xác nhận search document có đúng field, ID, version, status và giá trị denormalized.

Kiểm tra trường hợp category/brand không tồn tại hoặc đã bị xóa, inventory chưa có dữ liệu, price/currency có scale khác, status không được phép search và field nullable.

### 16.2. Projection consumer test

Xác nhận event hợp lệ tạo/cập nhật đúng document ID; event trùng không tạo tác động lặp; event cũ không ghi đè version mới; delete event tạo tombstone hoặc xóa đúng theo chính sách; lỗi Elasticsearch được retry hoặc đưa vào trạng thái pending.

### 16.3. Integration test với Elasticsearch

Dùng Elasticsearch thật tương thích để xác nhận mapping và analyzer được cài đúng, document được serialize đúng, query filter/sort/full-text trả kết quả mong muốn, aggregation dùng đúng field, bulk partial failure được xử lý theo item và alias trỏ tới index đúng.

### 16.4. End-to-end consistency test

Thực hiện command cập nhật database, đợi outbox consumer xử lý, rồi truy vấn Elasticsearch:

~~~text
Rename product in database
          |
          v
Outbox event committed
          |
          v
Consumer processes event
          |
          v
Search document updated
          |
          v
Search API returns new name
~~~

Test nên có timeout chờ có giới hạn và báo trạng thái nếu projection không hội tụ. Không dùng sleep cố định dài để giả định event đã được xử lý; có thể poll điều kiện với deadline hoặc chờ tín hiệu test-specific.

## 17. Bảo mật và dữ liệu nhạy cảm trong projection

Search document thường sao chép dữ liệu từ nhiều nguồn. Điều đó làm tăng số nơi lưu dữ liệu và cần chính sách bảo mật rõ ràng.

- Không đưa password, token, secret hoặc field không cần tìm kiếm vào document.
- Không index thông tin cá nhân chỉ vì nó có sẵn trong entity.
- Xác định field nào được hiển thị cho từng nhóm người dùng.
- Áp dụng tenant/security filter bắt buộc ở server-side query.
- Xóa hoặc cập nhật projection khi quyền truy cập hoặc trạng thái dữ liệu thay đổi.
- Đặt retention và quy trình xóa dữ liệu phù hợp với source of truth.

Nếu search document chứa dữ liệu nhạy cảm được sao chép, xóa ở database nhưng quên xóa ở Elasticsearch vẫn có thể để lộ dữ liệu qua search. Projection pipeline cần xử lý delete/privacy event và có cơ chế kiểm tra/repair.

## 18. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Dùng JPA entity trực tiếp làm search document | Model gắn chặt hai storage, mapping khó đổi | Tạo projection class riêng |
| Ghi database và Elasticsearch tuần tự trong cùng service | Dual-write inconsistency khi một bên lỗi | Transactional outbox |
| Search document được dùng làm source of truth | Dữ liệu stale có thể điều khiển nghiệp vụ | Command đọc/cập nhật source of truth |
| Denormalize nhưng không theo dõi nguồn field | Field lặp bị cũ khi dữ liệu gốc đổi | Event và projection rebuild |
| Map JPA lazy relation trực tiếp | N+1 hoặc lazy initialization error | Projection query/batch fetch |
| Consumer không idempotent | Event trùng tạo trạng thái sai | Event ID, version và idempotent write |
| Event cũ ghi sau event mới | Search document bị lùi dữ liệu | Aggregate version/ordering |
| Delete không có tombstone hoặc version | Event update cũ có thể tạo lại document | Tombstone và stale-event guard |
| Rebuild ghi đè thay đổi mới | Index mới thiếu cập nhật | Watermark và event replay |
| Thay mapping trên index đang chạy | Mapping không tương thích hoặc lỗi index | Versioned index và alias switch |
| Index mọi field của entity | Tăng chi phí và lộ dữ liệu | Chỉ đưa field phục vụ query vào projection |

## 19. Quy trình thiết kế một Search Document

1. Liệt kê query/use case mà index cần phục vụ.
2. Xác định field cần full-text, exact filter, sort, aggregation và display.
3. Xác định source of truth cho từng field.
4. Thiết kế document phẳng/denormalized theo query.
5. Chọn mapping, analyzer, nested/object và multi-field.
6. Tạo class search document riêng, không tái sử dụng entity nghiệp vụ khi hai mô hình khác mục đích.
7. Viết mapper/projection factory từ nguồn dữ liệu.
8. Chọn event payload hoặc ID+version cho projection pipeline.
9. Dùng outbox hoặc cơ chế delivery bền vững.
10. Làm consumer idempotent và bảo vệ event ordering/version.
11. Xử lý update, delete, retry và lỗi partial bulk.
12. Có quy trình rebuild, backfill, versioned index và alias cutover.
13. Kiểm thử mapper, consumer, mapping/search và eventual consistency.
14. Theo dõi projection lag, lỗi consumer và số document lệch.

## 20. Kết luận

Database entity và Elasticsearch search document phục vụ hai mục đích khác nhau. Entity nghiệp vụ bảo vệ dữ liệu có thẩm quyền và invariant; search document là projection được tổ chức theo query pattern, có thể denormalize và thay đổi độc lập. Tách hai model giúp mapping, analyzer, field phục vụ tìm kiếm và nhiều read model phát triển mà không làm rối domain persistence.

Projection cần được cập nhật bằng một pipeline có thể phục hồi. Khi database là source of truth, transactional outbox giúp lưu thay đổi nghiệp vụ và event trong cùng transaction; consumer chuyển event thành search document, xử lý duplicate, thứ tự event, version và delete. Không dựa vào dual write hoặc @Transactional thông thường để commit database và Elasticsearch như một transaction chung.

Thiết kế search document theo truy vấn thực tế, xác định nguồn của từng field denormalized, kiểm soát concurrency và có thể rebuild index từ dữ liệu gốc. Khi search index chỉ là read model có thể tái tạo, ứng dụng giữ được ranh giới rõ: command bảo vệ nghiệp vụ, projection phục vụ tìm kiếm và eventual consistency được quản lý bằng event, version và quy trình vận hành.
