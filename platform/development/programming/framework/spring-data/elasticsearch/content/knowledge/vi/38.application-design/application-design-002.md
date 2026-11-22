# Thiết kế mô hình phi chuẩn hóa theo trường hợp sử dụng

Elasticsearch là một search engine hướng document. Vì vậy, mô hình dữ liệu hiệu quả thường được thiết kế từ cách ứng dụng tìm kiếm và đọc dữ liệu, thay vì sao chép nguyên cấu trúc bảng quan hệ rồi kỳ vọng mọi truy vấn đều chạy tốt.

Phi chuẩn hóa (denormalization) là việc chủ động lưu cùng một thông tin ở nhiều document hoặc lặp lại một phần dữ liệu liên quan để một truy vấn có thể đọc kết quả trong ít bước hơn. Ví dụ, document sản phẩm có thể lưu sẵn tên thương hiệu và tên danh mục để trang catalog không phải tra cứu thêm nhiều resource mỗi lần hiển thị.

Phi chuẩn hóa giúp đọc nhanh và đơn giản hóa query, nhưng làm tăng trách nhiệm cập nhật, đồng bộ và kiểm soát dữ liệu trùng lặp. Một thiết kế tốt phải xác định rõ use case đọc nào được tối ưu, dữ liệu nào là nguồn chuẩn, thông tin nào được sao chép, mức độ trễ chấp nhận được và cách sửa sai khi projection bị lệch.

## 1. Tư duy thiết kế theo trường hợp sử dụng

### 1.1. Bắt đầu từ truy vấn, không bắt đầu từ bảng

Trong cơ sở dữ liệu quan hệ, mô hình thường được chuẩn hóa để tránh lặp dữ liệu và bảo đảm cập nhật nhất quán. Khi đọc, ứng dụng dùng JOIN để kết hợp các bảng.

Elasticsearch lưu document JSON và tối ưu cho tìm kiếm, lọc, sắp xếp, aggregation và trả về document phù hợp. Một query thường hoạt động tốt khi các field cần lọc hoặc hiển thị đã nằm trong document được tìm kiếm.

Ví dụ một trang catalog cần:

- Tìm sản phẩm theo từ khóa.
- Lọc theo danh mục và thương hiệu.
- Lọc theo trạng thái còn hàng.
- Sắp xếp theo giá hoặc điểm phổ biến.
- Hiển thị tên sản phẩm, tên thương hiệu, giá và ảnh ngay trong kết quả.

Nếu dữ liệu được lưu theo cấu trúc nhiều bảng riêng biệt, ứng dụng phải kết hợp sản phẩm, thương hiệu, danh mục và trạng thái kho. Với Elasticsearch, có thể thiết kế document catalog chứa các field đã được sao chép để query trả về đủ dữ liệu trong một lần search.

### 1.2. Một index không nhất thiết phải đại diện cho một bảng

Index nên đại diện cho một tập document phục vụ một hoặc nhiều use case có chung:

- Cách truy vấn.
- Mapping và kiểu dữ liệu.
- Vòng đời dữ liệu.
- Quyền truy cập.
- Yêu cầu freshness.
- Quy mô và đặc tính tải.

Một sản phẩm có thể xuất hiện trong nhiều projection:

| Projection | Mục tiêu | Field ưu tiên |
|---|---|---|
| Product catalog | Tìm kiếm và lọc sản phẩm | Tên, mô tả, thương hiệu, danh mục, giá, trạng thái |
| Product autocomplete | Gợi ý khi nhập | Tên chuẩn hóa, alias, từ khóa, popularity |
| Product analytics | Tổng hợp theo thời gian | Nhãn phân nhóm, category, brand, timestamp, metric |
| Product detail | Hiển thị trang chi tiết | Nội dung đầy đủ và các thông tin liên quan cần thiết |

Không nên ép một document duy nhất đáp ứng mọi truy vấn nếu các use case có yêu cầu field, freshness hoặc tải khác nhau đáng kể.

### 1.3. Mô hình đọc có thể khác mô hình ghi

Ứng dụng có thể giữ dữ liệu chuẩn trong relational database hoặc service sở hữu dữ liệu, rồi xây dựng một search projection trong Elasticsearch.

Đây là tư duy gần với CQRS (Command Query Responsibility Segregation):

- Write model xử lý quy tắc nghiệp vụ và là nơi sở hữu dữ liệu chuẩn.
- Read model được thiết kế để phục vụ truy vấn.
- Event hoặc change stream truyền thay đổi từ write model sang read model.
- Read model có thể trễ hơn nguồn chuẩn một khoảng thời gian được kiểm soát.

Elasticsearch thường phù hợp làm read model/search projection khi hệ thống cần tìm kiếm linh hoạt. Không nên coi index tìm kiếm là nguồn dữ liệu giao dịch duy nhất nếu nghiệp vụ cần transaction hoặc ràng buộc toàn vẹn mà Elasticsearch không cung cấp.

### 1.4. Sơ đồ kiến trúc điển hình

~~~mermaid
flowchart LR
    A[Order or Catalog Service] --> B[(Source of Truth)]
    B --> C[Outbox or Change Stream]
    C --> D[Projection Consumer]
    D --> E[Transform and Enrich]
    E --> F[(Elasticsearch Read Model)]
    G[Search API] --> F
    G --> H[Search Result DTO]
~~~

Write model sở hữu quy tắc nghiệp vụ. Projection consumer biến dữ liệu thành document phù hợp với query. Search API đọc projection và trả DTO cho giao diện.

### 1.5. Ghi rõ hợp đồng của từng use case

Trước khi chọn cấu trúc document, hãy mô tả:

- Ai đọc dữ liệu?
- Query cần field nào?
- Field nào dùng để filter, sort, aggregate hoặc full-text search?
- Kết quả có cần snapshot nhất quán hay chấp nhận eventual consistency?
- Dữ liệu thay đổi bao nhiêu lần mỗi phút/giờ?
- Một thay đổi nguồn ảnh hưởng bao nhiêu document?
- Document có thể lớn đến mức nào?
- Có cần truy vấn chéo giữa các nhóm document không?
- Có dữ liệu nhạy cảm nào không được sao chép?

Các câu trả lời này quyết định nên embed, duplicate field, tạo projection riêng hay giữ reference.

## 2. Chuẩn hóa và phi chuẩn hóa

### 2.1. Chuẩn hóa giảm dữ liệu trùng lặp

Một mô hình chuẩn hóa thường tách các thực thể:

~~~text
Product(id, name, brand_id, category_id)
Brand(id, name)
Category(id, name)
Inventory(product_id, available_quantity)
Price(product_id, amount, currency)
~~~

Mỗi thông tin có một nơi sở hữu. Đổi tên thương hiệu chỉ cần cập nhật một record Brand.

Cách này giảm dữ liệu trùng lặp và phù hợp với write model quan hệ. Tuy nhiên, để trả trang catalog, ứng dụng cần kết hợp nhiều nguồn.

### 2.2. Phi chuẩn hóa tối ưu đường đọc

Document catalog có thể chứa thông tin liên quan:

~~~json
{
  "productId": "P1001",
  "name": "Wireless Keyboard",
  "brand": {
    "id": "B10",
    "name": "Northwind"
  },
  "category": {
    "id": "C20",
    "name": "Computer Accessories"
  },
  "price": {
    "amount": 49.9,
    "currency": "USD"
  },
  "availability": {
    "inStock": true,
    "quantity": 42
  }
}
~~~

Trang catalog có thể filter theo brand.name, category.name, price.amount và availability.inStock mà không cần gọi thêm service chỉ để lấy các field đó.

### 2.3. Trade-off của dữ liệu trùng lặp

| Khía cạnh | Mô hình chuẩn hóa | Mô hình phi chuẩn hóa |
|---|---|---|
| Dữ liệu trùng lặp | Ít | Có chủ đích |
| Query đọc nhiều thực thể | Cần JOIN hoặc nhiều request | Thường đọc một document |
| Cập nhật field dùng chung | Một nơi | Có thể fan-out nhiều document |
| Độ phức tạp write | Thường tập trung | Có thêm đồng bộ projection |
| Độ trễ đọc | Có thể tăng do kết hợp dữ liệu | Thường thấp hơn cho query đã thiết kế |
| Consistency | Dễ kiểm soát trong một transaction | Thường eventual consistency giữa các projection |
| Mapping theo use case | Ít linh hoạt hơn | Linh hoạt theo read model |

Phi chuẩn hóa không phải mục tiêu tự thân. Chỉ sao chép dữ liệu khi lợi ích đọc hoặc khả năng cô lập use case đáng giá hơn chi phí đồng bộ.

## 3. Quyết định embed, reference hay duplicate field

### 3.1. Embed object khi dữ liệu đi cùng vòng đời

Embed một object phù hợp khi:

- Object con nhỏ.
- Thường được đọc cùng object cha.
- Có vòng đời gắn với object cha.
- Không cần truy vấn độc lập thường xuyên.
- Số lượng object con được giới hạn hợp lý.

Ví dụ địa chỉ giao hàng snapshot trong đơn hàng:

~~~json
{
  "orderId": "O1001",
  "customerId": "C100",
  "shippingAddress": {
    "recipient": "Alex",
    "city": "Ho Chi Minh City",
    "district": "District 1",
    "postalCode": "700000"
  }
}
~~~

Địa chỉ được snapshot theo thời điểm đặt hàng. Nếu khách hàng đổi địa chỉ hồ sơ sau đó, đơn hàng cũ vẫn cần giữ địa chỉ đã dùng khi giao dịch.

Đây là một ví dụ phi chuẩn hóa có ý nghĩa nghiệp vụ, không chỉ là tối ưu query.

### 3.2. Dùng reference khi dữ liệu lớn hoặc thay đổi độc lập

Nếu document liên quan lớn, có vòng đời độc lập hoặc được cập nhật thường xuyên, có thể chỉ lưu ID:

~~~json
{
  "orderId": "O1001",
  "customerId": "C100"
}
~~~

Ứng dụng lấy customer profile từ service sở hữu dữ liệu khi cần. Cách này giảm dữ liệu sao chép nhưng tạo thêm network call và coupling lúc đọc.

Một lựa chọn khác là copy một số field ổn định/cần hiển thị và giữ ID để tra cứu chi tiết:

~~~json
{
  "orderId": "O1001",
  "customer": {
    "id": "C100",
    "displayName": "Alex",
    "membershipTier": "Gold"
  }
}
~~~

### 3.3. Duplicate field khi query cần filter hoặc sort

Nếu trang catalog lọc theo thương hiệu, hãy copy brandId và brandName vào product document. Nếu chỉ hiển thị tên thương hiệu sau khi người dùng mở trang chi tiết, có thể chỉ cần reference.

Không sao chép mọi field của Brand vào mọi product. Chọn field theo query:

- brandId: filter và liên kết.
- brandName: hiển thị, aggregation hoặc sort nếu cần.
- brandLogoUrl: hiển thị card nếu use case yêu cầu.
- Các thông tin quản trị nội bộ: thường không cần trong search document.

### 3.4. Snapshot và live data có ý nghĩa khác nhau

Không phải dữ liệu sao chép nào cũng cần cập nhật khi nguồn đổi.

Ví dụ:

- Tên thương hiệu trong catalog thường cần cập nhật khi thương hiệu đổi tên.
- Địa chỉ giao hàng trong đơn đã đặt thường phải giữ snapshot.
- Tên sản phẩm trong invoice lịch sử có thể cần giữ tên tại thời điểm bán.
- Trạng thái tồn kho cần freshness cao hơn tên mô tả.

Hãy phân loại field thành snapshot, live projection hoặc derived value. Điều này quyết định có cần fan-out update hay không.

## 4. Chọn cấu trúc object, nested và document riêng

### 4.1. Object phù hợp với object con thông thường

Ví dụ mapping entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Object)
    private BrandSnapshot brand;
}

public class BrandSnapshot {

    @Field(type = FieldType.Keyword)
    private String id;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

Object mapping phù hợp khi mỗi field con được truy cập như một thuộc tính của cùng document. Các object array mặc định có thể được flatten theo cách khiến điều kiện trên nhiều field không còn ràng buộc cùng một phần tử.

### 4.2. Vấn đề với array of objects

Giả sử sản phẩm có các offer:

~~~json
{
  "offers": [
    { "seller": "A", "price": 100 },
    { "seller": "B", "price": 200 }
  ]
}
~~~

Nếu offers được mapping thành object thông thường, Elasticsearch có thể flatten field thành các mảng giá trị. Query yêu cầu seller = A và price = 200 có thể khớp document dù hai điều kiện nằm ở hai offer khác nhau.

Đây là cross-object matching.

### 4.3. Dùng nested khi cần giữ quan hệ trong từng phần tử

Nếu cần bảo đảm điều kiện khớp trên cùng một offer, dùng nested mapping:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<Offer> offers;
}

public class Offer {

    @Field(type = FieldType.Keyword)
    private String seller;

    @Field(type = FieldType.Double)
    private Double price;
}
~~~

Nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "bool": {
          "filter": [
            { "term": { "offers.seller": "A" } },
            { "range": { "offers.price": { "lte": 150 } } }
          ]
        }
      }
    }
  }
}
~~~

Nested lưu mỗi phần tử dưới dạng nested Lucene document riêng và giữ quan hệ giữa các field trong phần tử. Điều này tăng chi phí index và query so với object thường.

Chỉ dùng nested khi semantics của truy vấn thật sự cần ràng buộc cùng phần tử. Không chọn nested chỉ vì JSON có mảng object.

### 4.4. Tạo document riêng khi object con có truy vấn và vòng đời riêng

Nếu offer được cập nhật độc lập, có số lượng lớn hoặc được tìm kiếm như một thực thể riêng, cân nhắc index offer riêng:

~~~json
{
  "offerId": "OF100",
  "productId": "P1001",
  "sellerId": "S10",
  "sellerName": "Seller A",
  "price": 100,
  "currency": "USD"
}
~~~

Khi đó offer có thể được cập nhật mà không phải ghi lại product document lớn. Đổi lại, query cần thông tin sản phẩm có thể phải dựa vào field được duplicate hoặc thực hiện nhiều bước ở tầng ứng dụng.

### 4.5. Parent-child không phải giải pháp mặc định

Elasticsearch hỗ trợ join field cho quan hệ parent-child trong cùng một index. Parent và child cần được định tuyến về cùng shard.

Parent-child có thể phù hợp khi:

- Một parent có rất nhiều child.
- Child được cập nhật độc lập.
- Không thể hoặc không muốn duplicate toàn bộ parent vào child.
- Query cần join theo quan hệ này.

Nhược điểm gồm join query tốn chi phí, yêu cầu routing và chi phí quản lý global ordinals. Với nhiều use case tìm kiếm thông thường, denormalize field cần thiết vào document đọc sẽ đơn giản hơn.

## 5. Thiết kế document theo query

### 5.1. Ví dụ use case catalog

Giả sử API catalog hỗ trợ:

- Full-text search theo tên và mô tả.
- Filter theo brand, category, trạng thái còn hàng.
- Sort theo giá và popularity.
- Hiển thị card sản phẩm.
- Mở trang chi tiết bằng product ID.

Một document có thể được thiết kế:

~~~json
{
  "id": "P1001",
  "name": "Wireless Keyboard",
  "description": "Compact wireless keyboard",
  "brandId": "B10",
  "brandName": "Northwind",
  "categoryId": "C20",
  "categoryName": "Computer Accessories",
  "priceAmount": 49.9,
  "currency": "USD",
  "inStock": true,
  "availableQuantity": 42,
  "popularityScore": 87,
  "thumbnailUrl": "https://cdn.example.test/p1001.jpg",
  "updatedAt": "2026-11-13T10:00:00Z"
}
~~~

Document này chứa đủ field cho catalog card và filter. Không nhất thiết chứa toàn bộ lịch sử giá, mọi kho hàng hoặc toàn bộ thông tin thương hiệu.

### 5.2. Chọn field type theo thao tác query

| Field | Kiểu gợi ý | Vì sao |
|---|---|---|
| id, brandId, categoryId | keyword | Exact match và aggregation |
| name | text | Full-text search |
| name.keyword | keyword multi-field | Sort hoặc aggregation theo tên |
| description | text | Full-text search |
| priceAmount | scaled_float hoặc double | Range filter và sort |
| currency | keyword | Exact filter |
| inStock | boolean | Filter |
| availableQuantity | integer/long | Range và sort |
| popularityScore | integer/float | Sort hoặc ranking |
| updatedAt | date | Range và sort |

Kiểu chính xác phụ thuộc độ chính xác số, cách tính tiền và yêu cầu query. Với tiền tệ, nên lưu amount theo quy tắc precision rõ ràng và luôn lưu currency; không cộng các amount khác currency trong cùng aggregation nếu chưa quy đổi.

### 5.3. Dùng multi-field khi một giá trị phục vụ nhiều kiểu query

Tên sản phẩm có thể cần full-text search và exact sort:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Multi-field cho phép cùng một giá trị được index theo nhiều cách. Field text dùng cho search; subfield keyword dùng cho exact matching, sort hoặc aggregation.

Không cần tạo multi-field cho mọi string. Mỗi subfield tăng mapping và index size, vì vậy chỉ khai báo khi query cần.

### 5.4. Lưu giá trị dẫn xuất khi nó phục vụ query thường xuyên

Ví dụ inStock có thể được tính từ availableQuantity lớn hơn 0. Nếu gần như mọi query catalog đều filter theo trạng thái còn hàng, lưu sẵn boolean giúp query đơn giản.

Nhưng nếu lưu cả availableQuantity và inStock, phải xác định nguồn cập nhật để hai field không lệch nhau. Có thể tính inStock tại projection consumer từ quantity mỗi lần build document.

### 5.5. Denormalize label cho aggregation

Nếu báo cáo thường xuyên nhóm theo tên danh mục, có thể lưu categoryName bên cạnh categoryId. Dùng ID làm khóa ổn định, tên làm nhãn hiển thị.

Nếu tên category đổi, projection có thể được cập nhật theo event. Nếu aggregation cần phân tích lịch sử theo nhãn tại thời điểm giao dịch, phải lưu snapshot thay vì cập nhật tên cũ.

## 6. Ví dụ Spring Data Elasticsearch cho read model

### 6.1. Tạo entity riêng cho search projection

Không nhất thiết dùng entity của relational database làm entity Elasticsearch. Tạo một document class phản ánh use case tìm kiếm:

~~~java
@Document(indexName = "products-catalog-v1")
public class ProductCatalogDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String brandName;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Keyword)
    private String categoryName;

    @Field(type = FieldType.Double)
    private Double priceAmount;

    @Field(type = FieldType.Keyword)
    private String currency;

    @Field(type = FieldType.Boolean)
    private Boolean inStock;

    @Field(type = FieldType.Date)
    private Instant updatedAt;
}
~~~

Class này là read model. Nó có thể khác entity Product trong domain hoặc entity JPA. Sự tách biệt giúp search mapping thay đổi theo query mà không buộc thay đổi mô hình nghiệp vụ.

### 6.2. Repository cho use case đọc

~~~java
public interface ProductCatalogRepository
        extends ElasticsearchRepository<ProductCatalogDocument, String> {

    List<ProductCatalogDocument> findByBrandId(String brandId);

    List<ProductCatalogDocument> findByCategoryIdAndInStockTrue(
        String categoryId
    );
}
~~~

Derived query phù hợp cho điều kiện đơn giản. Với query nhiều filter, nested, aggregation hoặc ranking, có thể dùng ElasticsearchOperations và query builder của phiên bản Spring Data đang dùng.

### 6.3. Tạo projection từ dữ liệu nguồn

Một mapper có thể biến dữ liệu nguồn thành document:

~~~java
public ProductCatalogDocument toCatalogDocument(
        Product product,
        Brand brand,
        Category category,
        Inventory inventory) {

    ProductCatalogDocument document =
        new ProductCatalogDocument();

    document.setId(product.getId());
    document.setName(product.getName());
    document.setBrandId(brand.getId());
    document.setBrandName(brand.getName());
    document.setCategoryId(category.getId());
    document.setCategoryName(category.getName());
    document.setPriceAmount(product.getPrice());
    document.setCurrency(product.getCurrency());
    document.setInStock(inventory.getAvailableQuantity() > 0);
    document.setUpdatedAt(Instant.now());

    return document;
}
~~~

Đây là ví dụ mapping ở tầng projection. Trong production, tránh gọi từng service liên quan cho mỗi product nếu có thể batch dữ liệu hoặc nhận event đã chứa snapshot cần thiết. Nếu mapper dùng Instant.now(), cần phân biệt thời điểm build projection với thời điểm nguồn thay đổi.

### 6.4. Dùng ElasticsearchOperations khi cần điều khiển rõ hơn

Repository phù hợp với CRUD và query đơn giản. Với bulk indexing, index operations, update query hoặc thao tác projection nâng cao, ElasticsearchOperations cung cấp abstraction phù hợp.

~~~java
@Service
public class ProductCatalogIndexer {

    private final ElasticsearchOperations operations;

    public ProductCatalogIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductCatalogDocument index(
            ProductCatalogDocument document) {
        return operations.save(document);
    }
}
~~~

Khi dùng save, document cùng ID được ghi theo semantics index operation. Nếu cần cập nhật một vài field mà không thay toàn bộ source, dùng update API/UpdateQuery tương ứng với phiên bản thay vì giả định save luôn merge field.

### 6.5. Tách entity nguồn và projection

Một service có thể có:

- Product là domain/write model.
- ProductEntity là JPA persistence model.
- ProductCatalogDocument là Elasticsearch read model.
- ProductSuggestionDocument là autocomplete model.

Không cần một class duy nhất đại diện cho tất cả. Tách model giúp tránh việc một thay đổi mapping tìm kiếm làm ảnh hưởng schema giao dịch.

## 7. Cập nhật dữ liệu đã phi chuẩn hóa

### 7.1. Thách thức fan-out update

Giả sử một thương hiệu có 10.000 sản phẩm và tên thương hiệu được copy vào từng product document. Khi thương hiệu đổi tên, projection phải cập nhật các document liên quan.

Đây là fan-out update:

~~~mermaid
flowchart TD
    A[Brand name changed] --> B[BrandUpdated event]
    B --> C[Find affected product IDs]
    C --> D[Build update batches]
    D --> E[Bulk update catalog documents]
    E --> F[Record failures and retry]
~~~

Nếu chỉ lưu brandId, không cần fan-out để đổi tên, nhưng query catalog phải lookup thương hiệu khi hiển thị. Chọn cách nào phụ thuộc tần suất đọc, tần suất đổi tên và độ trễ chấp nhận được.

### 7.2. Cập nhật đồng bộ trong cùng request

Có thể cập nhật nguồn và Elasticsearch ngay trong cùng luồng application service. Cách này dễ hiểu nhưng hai hệ thống không có transaction ACID chung.

Nếu database commit thành công nhưng Elasticsearch update thất bại, dữ liệu bị lệch. Nếu cập nhật Elasticsearch trước rồi database rollback, search projection lại chứa dữ liệu chưa được commit.

Chỉ dùng dual write đồng bộ khi chấp nhận và có cơ chế xử lý trạng thái một phần. Với hệ thống quan trọng, outbox thường an toàn hơn.

### 7.3. Transactional outbox

Outbox ghi thay đổi nghiệp vụ và event vào cùng transaction database. Một publisher đọc outbox rồi gửi event tới broker hoặc projection worker.

~~~mermaid
flowchart TD
    A[Application command] --> B[(Database transaction)]
    B --> C[Update source rows]
    B --> D[Insert outbox event]
    D --> E[Outbox publisher]
    E --> F[Message broker]
    F --> G[Projection consumer]
    G --> H[Elasticsearch]
~~~

Outbox giảm nguy cơ database đã commit nhưng event bị mất. Consumer vẫn cần idempotency vì message có thể được gửi lại.

### 7.4. CDC và change stream

Change Data Capture (CDC) có thể đọc log thay đổi của database và phát event cho projection. CDC phù hợp khi muốn xây read model từ thay đổi dữ liệu nguồn mà không phải thêm event publish vào mọi service method.

Tuy nhiên, row-level change không luôn chứa đủ dữ liệu liên quan để xây document. Consumer có thể cần enrich từ nguồn hoặc giữ state để tái tạo projection.

### 7.5. Chọn event payload theo nhu cầu projection

Có hai kiểu phổ biến:

- Event chỉ chứa entity ID và version; consumer đọc lại nguồn chuẩn để build projection.
- Event chứa snapshot đủ field cần thiết; consumer có thể cập nhật projection mà không gọi nhiều service.

Event snapshot giúp giảm lookup nhưng tăng kích thước và trách nhiệm versioning. Event chỉ chứa ID giảm coupling payload nhưng có thể đọc nhầm trạng thái mới hơn nếu event cũ được xử lý trễ.

Hãy ghi rõ event version, aggregate ID, event ID và thời điểm/sequence nguồn.

## 8. Bảo đảm thứ tự và tính idempotent

### 8.1. Event có thể đến trùng hoặc sai thứ tự

Message broker thường cung cấp ít nhất một lần giao nhận trong nhiều cấu hình. Consumer có thể xử lý lại message sau crash hoặc timeout.

Nếu event cũ đến sau event mới, projection có thể bị quay về trạng thái cũ.

Cần có một quy tắc ordering:

- Version tăng đơn điệu của aggregate.
- Sequence number từ nguồn.
- Event timestamp được kiểm soát.
- Partition key theo aggregate để giữ thứ tự trong partition, nếu broker hỗ trợ.

Timestamp client không đáng tin cậy có thể không đủ để xác định thứ tự.

### 8.2. Lưu projection version

Document có thể chứa version nguồn:

~~~json
{
  "id": "P1001",
  "sourceVersion": 42,
  "name": "Wireless Keyboard",
  "brandName": "Northwind"
}
~~~

Khi nhận event version 41 sau version 42, consumer bỏ qua event cũ. Việc kiểm tra version và ghi document cần được thực hiện theo cơ chế atomic phù hợp để tránh hai consumer cùng vượt qua check.

Có thể dùng external versioning của Elasticsearch nếu version nguồn đáp ứng semantics yêu cầu, hoặc dùng OCC/conditional update để bảo vệ projection.

### 8.3. Idempotency theo event ID

Nếu một event có thể được xử lý nhiều lần, hãy dùng event ID để deduplicate hoặc thiết kế phép ghi projection có kết quả cuối giống nhau khi chạy lại.

Index document với ID ổn định và payload snapshot có version thường dễ idempotent hơn script tăng counter hoặc append mảng.

Không dùng một operation chỉ cộng dồn mà không có deduplication nếu message có thể được redeliver.

### 8.4. Fan-out update cần batch và retry từng item

Một event đổi tên thương hiệu có thể ảnh hưởng hàng nghìn product document. Không gửi một request khổng lồ hoặc tạo một request cho mỗi product không giới hạn.

Dùng:

- Batch ID ổn định.
- Bulk request có kích thước giới hạn.
- Concurrency có giới hạn.
- Retry theo item lỗi.
- Dead-letter queue cho lỗi cố định.
- Checkpoint hoặc progress marker để tiếp tục sau crash.

Bulk HTTP 200 không bảo đảm mọi item thành công; phải đọc errors và từng item response.

### 8.5. Xử lý partial failure

Nếu 9.900 trong 10.000 document được cập nhật, không chạy lại cả batch một cách mù quáng. Ghi lại item lỗi và phân loại:

- 409: conflict/version.
- 404: document hoặc index missing.
- 429: overload, backoff.
- 400: mapping/payload.
- 401/403: credential/privilege.

Chỉ retry lỗi có thể phục hồi và bảo đảm operation idempotent.

## 9. Denormalization cho dữ liệu thay đổi thường xuyên

### 9.1. Field biến động nhanh có thể tạo fan-out quá lớn

Nếu tồn kho thay đổi liên tục và một sản phẩm xuất hiện trong nhiều projection, mỗi thay đổi có thể tạo nhiều write.

Hãy xem xét:

- Có cần hiển thị quantity chính xác trong search result không?
- Có thể chỉ lưu inStock với mức freshness chấp nhận được không?
- Có thể lấy quantity mới nhất từ inventory service khi người dùng mở chi tiết không?
- Có thể tách inventory index hoặc dùng một projection riêng không?
- Có thể gộp nhiều event thành một lần cập nhật không?

Đừng sao chép field có tốc độ thay đổi cao vào mọi document nếu query không thực sự cần.

### 9.2. Dùng trạng thái thô hoặc bucket thay vì mọi chi tiết

Nếu catalog chỉ cần biết còn hàng hay hết hàng, một boolean inStock có thể đủ. Nếu cần lọc theo mức tồn kho, có thể dùng bucket:

- out_of_stock
- low_stock
- available

Bucket giảm tần suất cập nhật khi quantity thay đổi nhưng không đổi nhóm.

Chỉ dùng bucket nếu nghiệp vụ chấp nhận mất độ chi tiết. Khi đặt hàng, inventory service vẫn phải xác nhận quantity chính xác.

### 9.3. Dữ liệu giá và currency

Giá thường thay đổi theo thị trường, thời điểm và loại khách hàng. Trước khi denormalize giá, xác định:

- Giá chuẩn hay giá theo customer segment?
- Currency có đồng nhất không?
- Giá có thời gian hiệu lực?
- Query cần sort theo giá hiện tại hay giá lịch sử?
- Thuế/discount có được tính trong projection không?

Một field price mơ hồ dễ dẫn tới kết quả sai. Đặt tên rõ như listPriceAmount, salePriceAmount, currency, priceEffectiveAt.

### 9.4. Dữ liệu thời gian và snapshot

Với dữ liệu giao dịch lịch sử, lưu snapshot các nhãn quan trọng tại thời điểm giao dịch. Nếu chỉ lưu ID và lookup tên hiện tại, báo cáo lịch sử có thể thay đổi khi tên danh mục hoặc khách hàng đổi.

Ví dụ order line có thể giữ:

~~~json
{
  "productId": "P1001",
  "productNameAtPurchase": "Wireless Keyboard",
  "unitPriceAtPurchase": 49.9,
  "currency": "USD",
  "quantity": 2
}
~~~

Đây là snapshot có chủ đích. Không nên cập nhật lại các field này khi catalog thay đổi.

## 10. Giới hạn kích thước và độ phức tạp document

### 10.1. Không embed danh sách không giới hạn

Nếu một product document chứa toàn bộ review, lịch sử giá, mọi inventory movement và mọi offer trong nhiều năm, document sẽ lớn dần và mỗi update có thể tốn kém.

Tách thành index riêng khi collection:

- Có thể tăng không giới hạn.
- Được truy vấn độc lập.
- Có tốc độ cập nhật khác parent.
- Có quyền truy cập khác.
- Có retention khác.
- Không cần đọc toàn bộ cùng parent.

### 10.2. Tránh document quá rộng và mapping explosion

Không tạo field name động theo từng key người dùng hoặc từng thuộc tính không kiểm soát. Mỗi field mapping mới có chi phí và có thể làm số field tăng rất lớn.

Nếu cần lưu metadata động nhiều key, xem xét flattened field type (nếu phiên bản Elasticsearch/Spring Data hỗ trợ) hoặc lưu một cấu trúc opaque phù hợp với query. Flattened phù hợp với metadata key-value có cấu trúc linh hoạt nhưng có giới hạn về kiểu query so với mapping từng field.

### 10.3. Nested document có chi phí riêng

Mỗi nested object được index như nested Lucene document. Một parent chứa hàng nghìn nested entries có thể làm tăng số Lucene documents và chi phí cập nhật.

Nếu mảng lớn và cập nhật độc lập, index con riêng thường phù hợp hơn.

### 10.4. Chọn _source và stored fields theo nhu cầu

_source thường được giữ để trả document, reindex và xử lý update. Không tắt _source chỉ để tiết kiệm dung lượng nếu ứng dụng cần update, reindex hoặc trả document đầy đủ.

Chỉ tối ưu source/stored/doc values sau khi đo và xác định rõ query nào cần chúng.

## 11. Multi-tenant và bảo mật khi sao chép dữ liệu

### 11.1. Không sao chép field nhạy cảm nếu query không cần

Khi build projection, chỉ đưa field phục vụ search/read use case. Không copy email, số điện thoại, địa chỉ hoặc dữ liệu nhạy cảm vào mọi document nếu giao diện không cần.

Dữ liệu sao chép làm tăng phạm vi ảnh hưởng khi một index hoặc API key bị truy cập trái phép.

### 11.2. Giữ tenant ID trong document

Nếu index chứa nhiều tenant, document thường cần field tenant ID để filter và kiểm tra quyền. Tuy nhiên, query filter do client tự gửi không phải lớp bảo mật duy nhất.

Dùng authorization ở service và Elasticsearch security phù hợp. Nếu cần isolation mạnh, cân nhắc index riêng, API key riêng hoặc document-level security theo license/capability.

### 11.3. Field copy phải giữ đúng ranh giới tenant

Một projection consumer có thể join/enrich dữ liệu từ nhiều nguồn. Phải kiểm tra tenant ownership khi kết hợp record. Không lấy brand/category từ tenant khác chỉ vì ID trùng hoặc lookup không có tenant filter.

### 11.4. Xóa dữ liệu và quyền riêng tư

Khi dữ liệu nguồn bị xóa theo yêu cầu privacy, cần xác định mọi projection chứa bản sao field đó và xóa hoặc làm ẩn tương ứng.

Một field đã được duplicate vào catalog, autocomplete, analytics và cache không tự biến mất khi xóa record nguồn.

Duy trì danh sách projection phụ thuộc và quy trình deletion propagation có thể kiểm chứng.

## 12. Rebuild và versioning read model

### 12.1. Projection cần có khả năng dựng lại

Nếu Elasticsearch là read model, nên có khả năng rebuild từ nguồn chuẩn hoặc event log có thể replay.

Rebuild hữu ích khi:

- Mapping thay đổi.
- Logic projection được sửa.
- Field denormalized bị lệch.
- Analyzer thay đổi.
- Cần backfill field mới.
- Index bị hỏng hoặc dữ liệu bị xóa nhầm.

Nếu không thể rebuild, projection có thể trở thành nguồn dữ liệu duy nhất trên thực tế dù kiến trúc không chủ đích như vậy.

### 12.2. Dùng index version mới khi mapping thay đổi lớn

Ví dụ:

- products-catalog-v1
- products-catalog-v2

Tạo index mới với mapping mới, backfill dữ liệu, bắt kịp event mới và chuyển alias khi đã xác minh.

~~~mermaid
flowchart TD
    A[Source of truth] --> B[Build products-catalog-v2]
    A --> C[Continue event stream]
    C --> B
    B --> D[Validate counts and queries]
    D --> E[Switch read alias]
    E --> F[Retire v1 after rollback window]
~~~

Cách này giúp tránh thay mapping không tương thích trên index hiện tại và có đường rollback rõ ràng.

### 12.3. Alias tách tên logic khỏi tên vật lý

Ứng dụng có thể query alias products-catalog trong khi alias trỏ tới index versioned.

Alias cho phép chuyển read target sau khi rebuild mà không phải thay mọi client. Với write alias, cần xác định write index và quyền tương ứng.

### 12.4. Backfill phải phối hợp với event mới

Nếu bắt đầu backfill trong lúc nguồn tiếp tục thay đổi, cần bảo đảm event không bị mất hoặc ghi đè sai thứ tự.

Một số chiến lược:

- Ghi checkpoint nguồn, backfill tới checkpoint, rồi replay event sau checkpoint.
- Chạy dual-write có kiểm soát trong giai đoạn chuyển đổi.
- Dùng source version để loại bỏ event cũ.
- Rebuild từ snapshot nhất quán rồi bắt kịp change stream.

Không chỉ chạy scan toàn bộ nguồn và chuyển alias ngay sau khi scan kết thúc nếu dữ liệu có thể đã đổi trong lúc scan.

### 12.5. Kiểm chứng projection trước khi chuyển alias

So sánh:

- Số document theo tenant/category.
- Số ID bị thiếu hoặc trùng.
- Một tập query đại diện.
- Aggregation quan trọng.
- Mapping và analyzer.
- Freshness của projection.
- Lỗi indexing và dead-letter backlog.

Chuyển alias khi các kiểm tra đạt tiêu chí đã định nghĩa.

## 13. Xóa, soft delete và tombstone

### 13.1. Delete phải lan tới mọi projection

Nếu product bị xóa ở nguồn, consumer cần xóa document tương ứng khỏi catalog và autocomplete. Nếu chỉ xóa nguồn, search projection vẫn có thể trả kết quả cũ.

Có thể phát event ProductDeleted với ID, tenant và version để mọi projection xử lý.

### 13.2. Tombstone ngăn event cũ tái tạo dữ liệu

Một event update đến trễ có thể upsert document đã bị xóa. Tombstone hoặc deletion version giúp consumer biết entity đã bị xóa ở version nào và bỏ qua event cũ.

Nếu dùng soft delete, document có thể lưu deleted=true và search query luôn filter deleted=false. Cần kiểm tra tất cả query path và aggregation đều áp dụng điều kiện này.

### 13.3. Xóa vật lý và yêu cầu privacy

Soft delete không đủ cho yêu cầu xóa dữ liệu nhạy cảm nếu nội dung vẫn còn trong _source. Cần xóa hoặc ẩn dữ liệu theo chính sách retention/privacy, đồng thời xử lý snapshot, backup và index cũ.

## 14. Quan sát chất lượng projection

### 14.1. Freshness

Theo dõi khoảng cách giữa thời điểm nguồn thay đổi và thời điểm projection được cập nhật. Có thể lưu:

- sourceUpdatedAt
- projectedAt
- sourceVersion
- eventId

Không dùng riêng projectedAt để khẳng định dữ liệu mới nhất nếu event có thể đến sai thứ tự.

### 14.2. Đồng bộ và dead-letter

Theo dõi:

- Event lag.
- Consumer lag.
- Số projection update thành công/thất bại.
- Bulk item failure theo error type.
- Retry count.
- Dead-letter queue size.
- Thời gian rebuild/backfill.
- Số document chưa đồng bộ.

Nếu queue lỗi tăng nhưng search API vẫn trả 200, read model có thể đang stale dù hệ thống trông có vẻ khỏe.

### 14.3. Kiểm tra consistency theo mẫu

Có thể chạy job đối soát:

1. Lấy mẫu ID từ nguồn chuẩn.
2. Đọc document tương ứng trong Elasticsearch.
3. So sánh các field được định nghĩa là phải đồng nhất.
4. Phân nhóm mismatch.
5. Rebuild hoặc repair document.
6. Ghi nhận metric và audit.

Không so sánh mọi field nếu projection cố ý biến đổi hoặc snapshot. Định nghĩa rõ field nào cần equality và field nào có semantics khác.

### 14.4. Phân biệt projection stale với query sai

Khi kết quả search thiếu hoặc cũ, kiểm tra:

- Event đã được phát chưa?
- Consumer đã xử lý chưa?
- Document có được index đúng ID không?
- Refresh đã làm document searchable chưa?
- Query có filter đúng tenant/status không?
- Alias có trỏ đúng index version không?

Không kết luận query DSL sai khi nguyên nhân là projection chưa cập nhật.

## 15. Kiểm thử mô hình phi chuẩn hóa

### 15.1. Test mapper projection

Kiểm tra dữ liệu nguồn được biến đổi thành document đúng:

- ID ổn định.
- Field được duplicate đúng.
- Derived field được tính đúng.
- Snapshot field giữ giá trị tại thời điểm nghiệp vụ.
- Tenant ID không bị mất.
- Null/missing được xử lý nhất quán.

### 15.2. Integration test query trên Elasticsearch thật

Dùng Testcontainers hoặc môi trường Elasticsearch tương thích để xác nhận:

- Mapping object/nested.
- Nested query không cross-match.
- Keyword filter và aggregation.
- Multi-field search/sort.
- Range query theo số và ngày.
- Alias và index version.
- Upsert/update semantics.

### 15.3. Test event duplicate và out-of-order

Gửi cùng event hai lần và xác nhận projection không thay đổi sai. Gửi event version cũ sau event mới và xác nhận document không bị rollback về trạng thái cũ.

### 15.4. Test fan-out update

Tạo nhiều product dùng chung một brand. Đổi tên brand và xác nhận tất cả projection liên quan được cập nhật theo batch.

Mô phỏng một số item lỗi để kiểm tra retry/dead-letter mà không cập nhật lại item đã thành công.

### 15.5. Test deletion propagation

Xóa entity ở nguồn và xác nhận:

- Catalog document không còn được trả.
- Autocomplete projection được cập nhật.
- Các index analytics có semantics retention/snapshot đúng.
- Event cũ không tái tạo document đã xóa.

### 15.6. Test hiệu năng theo query thực

Đo query latency, indexing throughput, document size và chi phí fan-out với dữ liệu có quy mô gần thực tế. Một mô hình nhỏ có thể chạy tốt nhưng gặp vấn đề khi một brand có hàng triệu product hoặc một product có rất nhiều nested offers.

## 16. Các lỗi thiết kế thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Query cần nhiều service call | Document thiếu field phục vụ use case | Denormalize đúng field cần đọc |
| Tên brand trong kết quả bị cũ | Copy field nhưng không có update propagation | Event fan-out hoặc snapshot semantics rõ ràng |
| Update một child làm document rất lớn phải ghi lại | Embed collection thay đổi độc lập | Tách child index hoặc thiết kế projection khác |
| Nested query chậm | Quá nhiều nested entries hoặc nested không cần thiết | Dùng object thường hoặc index riêng |
| Query nested trả kết quả sai | Dùng object array thường gây cross-object matching | Dùng nested khi điều kiện phải khớp cùng phần tử |
| Mapping explosion | Field động không kiểm soát | Whitelist field hoặc flattened phù hợp |
| Document tăng kích thước liên tục | Embed lịch sử/danh sách không giới hạn | Tách index theo vòng đời và query |
| Nhiều document stale sau event | Consumer lỗi, event bị mất hoặc version ordering sai | Outbox/CDC, retry, checkpoint và reconciliation |
| Event cũ ghi đè dữ liệu mới | Không kiểm tra source version | Version ordering hoặc conditional write |
| Retry làm tăng counter nhiều lần | Update không idempotent | Event ID và deduplication |
| Rebuild tạo dữ liệu lệch | Backfill không phối hợp event mới | Checkpoint và replay theo version |
| Search trả dữ liệu đã xóa | Delete không lan tới mọi projection | Deletion event và tombstone |
| Lộ dữ liệu giữa tenant | Projection enrichment thiếu tenant boundary | Kiểm tra tenant ownership và authorization |
| Projection lưu dữ liệu nhạy cảm không cần thiết | Copy toàn bộ entity nguồn | Chỉ project field theo use case |
| Write amplification quá cao | Một field thay đổi làm fan-out quá nhiều | Tách projection, bucket hóa hoặc lookup live |

## 17. Quy trình thiết kế theo use case

Khi thiết kế document model cho một ứng dụng Spring Data Elasticsearch:

1. Liệt kê query thực tế và field cần filter, sort, aggregate, search hoặc hiển thị.
2. Xác định nguồn dữ liệu chuẩn và service sở hữu từng field.
3. Phân loại field thành snapshot, live projection hoặc derived value.
4. Chọn embed object, nested, duplicate field, reference hoặc document riêng.
5. Đánh giá kích thước document, cardinality và tần suất cập nhật.
6. Tạo read model riêng cho use case nếu mapping hoặc freshness khác biệt đáng kể.
7. Chọn field type và analyzer theo query.
8. Thiết kế event/outbox/CDC để cập nhật projection.
9. Bảo đảm event ordering, idempotency và source version.
10. Xử lý fan-out theo batch, concurrency limit và item-level retry.
11. Thiết kế delete propagation, tombstone và privacy cleanup.
12. Version hóa index và dùng alias cho mapping migration.
13. Đo query latency, indexing throughput, projection lag và document size.
14. Test query, mapping, duplicate event, out-of-order event và rebuild bằng Elasticsearch thật.
15. Đối soát định kỳ để phát hiện projection bị lệch.

## 18. Những điểm cần ghi nhớ

- Thiết kế Elasticsearch theo query và use case, không sao chép nguyên mô hình bảng quan hệ.
- Phi chuẩn hóa giúp một query đọc được nhiều field liên quan, nhưng tạo chi phí đồng bộ dữ liệu trùng lặp.
- Tách write model/source of truth khỏi read model/search projection khi cần.
- Embed object khi dữ liệu nhỏ và có vòng đời đi cùng parent; dùng reference khi dữ liệu lớn hoặc thay đổi độc lập.
- Duplicate field chỉ khi query cần filter, sort, aggregation hoặc hiển thị.
- Object array có thể gây cross-object matching; dùng nested khi điều kiện phải khớp cùng một phần tử.
- Tách document riêng khi child có query, volume, update hoặc lifecycle độc lập.
- Parent-child có chi phí join và routing; không phải lựa chọn mặc định.
- Dùng ID ổn định, source version, idempotency và event ordering để bảo vệ projection.
- Fan-out update cần batch, concurrency limit và retry từng item.
- Outbox hoặc CDC giảm nguy cơ mất thay đổi khi cập nhật nguồn và Elasticsearch.
- Snapshot lịch sử và live projection có semantics khác nhau; không cập nhật nhầm snapshot.
- Version hóa index, backfill, đối soát rồi chuyển alias khi mapping thay đổi lớn.
- Delete phải lan tới mọi projection; tombstone ngăn event cũ tái tạo dữ liệu.
- Chỉ sao chép field cần thiết và giữ tenant/security boundary.
- Theo dõi freshness, consumer lag, bulk errors, dead-letter và consistency drift.

Mô hình phi chuẩn hóa tốt là mô hình trả lời nhanh những truy vấn mà ứng dụng thực sự cần, đồng thời có chủ sở hữu dữ liệu và quy trình đồng bộ rõ ràng. Khi quyết định embed, duplicate hay tách document dựa trên query, vòng đời và tốc độ thay đổi của từng field, Spring Data Elasticsearch có thể phục vụ read workload hiệu quả mà vẫn giữ được khả năng rebuild và kiểm soát tính nhất quán.

