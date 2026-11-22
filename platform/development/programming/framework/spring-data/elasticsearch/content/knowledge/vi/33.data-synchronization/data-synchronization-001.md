# Chọn nguồn dữ liệu chuẩn và mô hình chiếu cho tìm kiếm

Trong kiến trúc có Elasticsearch, dữ liệu thường tồn tại ở ít nhất hai dạng: bản ghi nghiệp vụ trong hệ thống nguồn và document đã được chuẩn bị cho truy vấn tìm kiếm. Hai dạng này có mục đích khác nhau. Nguồn dữ liệu chuẩn (source of truth) giữ trạng thái nghiệp vụ có thẩm quyền; mô hình chiếu tìm kiếm (search projection/read model) được thiết kế để phục vụ truy vấn, lọc, sắp xếp, autocomplete và hiển thị nhanh.

Không nên coi Elasticsearch là bản sao nguyên xi của toàn bộ database. Một document tìm kiếm thường là dữ liệu đã chọn lọc, kết hợp hoặc biến đổi từ nhiều nguồn để phù hợp với các truy vấn thực tế. Khi thiết kế đồng bộ, cần xác định rõ dữ liệu nào có thẩm quyền, field nào do hệ thống nào sở hữu, cách cập nhật projection, cách xử lý sự kiện đến trễ và cách dựng lại index khi mapping hoặc mô hình tìm kiếm thay đổi.

Trong Spring Data Elasticsearch, cách tổ chức dễ kiểm soát là giữ domain model và search document tách biệt khi chúng phục vụ mục đích khác nhau. Service hoặc projection handler đọc dữ liệu chuẩn, tạo search document, rồi ghi vào Elasticsearch bằng repository hoặc `ElasticsearchOperations`. Cách này giúp tối ưu tìm kiếm mà không làm mô hình nghiệp vụ phụ thuộc vào mapping và cấu trúc index.

## 1. Source of truth là gì?

Source of truth là nơi có thẩm quyền cuối cùng đối với một loại dữ liệu nghiệp vụ. Khi có hai hệ thống đưa ra giá trị khác nhau, hệ thống được xác định là nguồn chuẩn quyết định giá trị đúng.

Ví dụ trong một hệ thống thương mại điện tử:

| Dữ liệu | Nguồn chuẩn có thể là | Vai trò của Elasticsearch |
|---|---|---|
| Tên, SKU và trạng thái sản phẩm | Product service/database | Lưu projection để tìm kiếm và lọc |
| Giá bán hiện hành | Pricing service/database | Denormalize giá vào document để sort/filter |
| Tồn kho có thể bán | Inventory service/database | Có thể hiển thị snapshot; quyết định đặt hàng vẫn kiểm tra nguồn tồn kho chuẩn |
| Đơn hàng và trạng thái thanh toán | Order/payment service | Tìm kiếm đơn hàng và dashboard |
| Hồ sơ người dùng | Identity/profile service | Tìm kiếm theo các field được phép lập chỉ mục |

Elasticsearch có thể chứa dữ liệu rất mới và trả lời query nhanh, nhưng điều đó không tự biến nó thành nguồn chuẩn cho giao dịch. Một search result có thể trễ hơn database vài mili giây hoặc vài giây, có thể bị thiếu trong lúc đồng bộ và có thể được dựng lại từ nguồn khác.

### Phân biệt nguồn chuẩn và bản chiếu

- Nguồn chuẩn chịu trách nhiệm bảo đảm quy tắc nghiệp vụ và tính nhất quán cần thiết cho giao dịch.
- Search projection chịu trách nhiệm làm dữ liệu dễ truy vấn theo các nhu cầu tìm kiếm.
- Projection có thể denormalize, đổi tên field, tạo field dẫn xuất hoặc bỏ field không cần tìm kiếm.
- Projection phải có thể tái tạo từ nguồn chuẩn hoặc từ event log đủ thông tin.

Nếu một ứng dụng cập nhật trực tiếp giá trị nghiệp vụ trong Elasticsearch rồi không cập nhật nguồn chuẩn, hai hệ thống sẽ lệch nhau. Lần đồng bộ kế tiếp có thể ghi đè thay đổi đó, hoặc thay đổi bị mất hoàn toàn khi index được rebuild.

## 2. Vì sao không dùng nguyên domain entity làm search document?

Domain entity thường phản ánh quy tắc và cấu trúc ghi của nghiệp vụ. Search document phản ánh cách truy vấn và hiển thị dữ liệu. Hai mô hình có thể trùng một phần nhưng không nhất thiết giống nhau.

Ví dụ domain model có thể tách sản phẩm, danh mục, thương hiệu và giá thành các bảng hoặc aggregate riêng:

```text
Product
  id
  name
  brandId
  categoryId

Brand
  id
  name

Category
  id
  displayName

Price
  productId
  amount
  currency
```

Trang tìm kiếm thường cần một document chứa sẵn tên thương hiệu, tên danh mục, giá và các field lọc:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse",
  "brand": {
    "id": "b-10",
    "name": "Acme"
  },
  "category": {
    "id": "c-20",
    "name": "Accessories"
  },
  "price": {
    "amount": 29.99,
    "currency": "USD"
  },
  "searchText": "Wireless Mouse Acme Accessories"
}
```

Document này là projection. Nó kết hợp dữ liệu từ nhiều aggregate để tránh phải thực hiện join ở mỗi lần tìm kiếm.

### Lợi ích khi tách hai mô hình

- Domain model không phải mang các field chỉ phục vụ search.
- Search mapping có thể thay đổi theo nhu cầu query mà không buộc thay đổi schema nghiệp vụ.
- Có thể tạo nhiều projection cho các use case khác nhau.
- Có thể rebuild index từ nguồn chuẩn khi analyzer hoặc mapping thay đổi.
- Quyền sở hữu dữ liệu và trách nhiệm đồng bộ rõ ràng hơn.

## 3. Chọn nguồn chuẩn theo từng field

Một document tìm kiếm có thể kết hợp dữ liệu từ nhiều service. Vì vậy, không chỉ xác định nguồn chuẩn cho toàn document; cần xác định nguồn sở hữu từng nhóm field.

Ví dụ:

| Field trong projection | Chủ sở hữu | Cách cập nhật |
|---|---|---|
| `name`, `description`, `sku` | Product service | Product created/updated event |
| `brandName` | Brand service | Brand changed event hoặc projection refresh |
| `price` | Pricing service | Price changed event |
| `availableQuantity` | Inventory service | Inventory snapshot/event nếu use case cần |
| `ratingAverage` | Review/rating service | Aggregate cập nhật theo review event |
| `searchKeywords` | Search projection logic | Tính lại từ các field nguồn |

Một field tổng hợp như `ratingAverage` không có bản ghi duy nhất tương ứng trong nguồn; nó được tính từ nhiều review. Hãy xác định service nào sở hữu phép tính hoặc aggregate này và cách projection nhận giá trị mới.

### Field có nhiều nguồn cập nhật

Nếu nhiều service cùng ghi một field trong Elasticsearch, quy tắc “ai thắng” sẽ không rõ ràng. Nên chỉ định một owner cho mỗi field hoặc nhóm field. Projection handler có thể nhận event từ nhiều nguồn, nhưng phải biết event nào được phép cập nhật field nào.

Ví dụ, event ProductUpdated không nên ghi đè giá hiện hành nếu giá thuộc Pricing service. Nó chỉ cập nhật phần product của projection, sau đó kết hợp với giá đã biết hoặc yêu cầu projection được làm mới từ nguồn giá chuẩn.

## 4. Search projection là read model

Trong kiến trúc CQRS, write model và read model có thể được thiết kế khác nhau:

```text
                 WRITE SIDE
Client -> Product Service -> Database chuẩn
                 |
                 | Outbox / CDC / Domain Event
                 v
              Event Stream
                 |
                 v
             Projector
                 |
                 v
          Elasticsearch Index
                 |
                 v
                 READ SIDE
Client -> Search API -> Search Projection
```

Write side xử lý lệnh nghiệp vụ và lưu dữ liệu chuẩn. Projector nhận thay đổi, biến đổi thành document tối ưu cho truy vấn rồi ghi vào Elasticsearch. Search API đọc projection thay vì thực hiện nhiều join tới các hệ thống nguồn.

Read model có thể trễ so với write model. Đây là eventual consistency. API cần hiểu đặc tính này và không dùng kết quả search làm căn cứ cuối cùng cho các thao tác cần trạng thái giao dịch mới nhất.

### Ví dụ một luồng nghiệp vụ

1. Người dùng đổi tên sản phẩm.
2. Product service kiểm tra quy tắc và lưu tên mới vào database.
3. Service ghi một event `ProductUpdated` cùng transaction hoặc phát event qua cơ chế tin cậy.
4. Projector nhận event, đọc hoặc lấy payload cần thiết.
5. Projector tạo lại search document và ghi vào index.
6. Người dùng tìm kiếm; sau khi projection được cập nhật, tên mới xuất hiện trong kết quả.

Nếu bước 4 hoặc 5 lỗi, event cần được retry hoặc replay. Không nên yêu cầu người dùng cập nhật lại sản phẩm chỉ để sửa một lần ghi search thất bại.

## 5. Các cách đồng bộ nguồn chuẩn sang Elasticsearch

Không có một cơ chế đồng bộ phù hợp cho mọi hệ thống. Các lựa chọn phổ biến:

| Cơ chế | Cách hoạt động | Ưu điểm | Hạn chế |
|---|---|---|---|
| Dual write trực tiếp | Service ghi database rồi ghi Elasticsearch | Dễ bắt đầu, ít thành phần | Hai lần ghi không có transaction chung; dễ lệch dữ liệu |
| Transactional outbox | Ghi dữ liệu và event vào cùng transaction DB; worker phát event | Không mất event giữa DB commit và publish nếu triển khai đúng | Cần outbox publisher, retry và quản lý event |
| CDC | Đọc transaction log của database | Bắt được thay đổi từ nhiều writer, giảm phụ thuộc code phát event | Cần hạ tầng CDC và xử lý schema/event semantics |
| Polling theo watermark | Định kỳ đọc bản ghi có `updatedAt` mới | Đơn giản, dễ triển khai cho hệ thống nhỏ | Có độ trễ, phải xử lý timestamp trùng và bản ghi bị xóa |
| Scheduled full rebuild | Quét toàn bộ nguồn và dựng lại index | Dễ tái tạo, hữu ích cho dữ liệu nhỏ hoặc batch | Tốn tài nguyên và không phù hợp yêu cầu gần realtime |

### Vì sao dual write dễ lỗi?

Ví dụ service thực hiện:

```java
productRepository.save(product);
searchRepository.save(toSearchDocument(product));
```

Nếu database commit thành công nhưng Elasticsearch timeout, hai hệ thống lệch nhau. Nếu đảo thứ tự và Elasticsearch thành công nhưng database rollback, search index chứa dữ liệu không có trong nguồn chuẩn. Không có transaction phân tán bao quanh cả hai hệ thống thì hai thao tác không nguyên tử.

Dual write có thể chấp nhận trong ứng dụng nhỏ nếu có cơ chế reconcile/rebuild và chấp nhận độ lệch tạm thời. Với dữ liệu quan trọng, transactional outbox hoặc CDC thường đáng tin cậy hơn.

## 6. Transactional outbox

Transactional outbox lưu thay đổi nghiệp vụ và event cần phát trong cùng transaction của database nguồn.

Ví dụ bảng:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(64) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload        JSON NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
```

Transaction nghiệp vụ:

```text
BEGIN
  UPDATE product ...
  INSERT INTO outbox_event (... ProductUpdated ...)
COMMIT
```

Nếu transaction rollback, cả product update và outbox event đều rollback. Nếu commit thành công, event vẫn nằm trong outbox để publisher có thể phát lại sau khi broker hoặc Elasticsearch phục hồi.

### Publisher và projector

Outbox publisher đọc event chưa phát, gửi tới broker hoặc trực tiếp tới worker rồi đánh dấu đã phát. Projector nhận event, cập nhật projection trong Elasticsearch.

Các yêu cầu vận hành:

- Event có ID duy nhất để deduplicate.
- Có retry/backoff khi publish hoặc project thất bại.
- Không đánh dấu event hoàn tất trước khi bước cần thiết thành công.
- Có cơ chế xử lý event poison hoặc không hợp lệ.
- Có retention/cleanup cho outbox đã xử lý.
- Theo dõi độ trễ từ lúc commit đến lúc projection searchable.

Outbox thường cung cấp at-least-once delivery. Vì vậy projector phải idempotent; không giả định một event chỉ được giao đúng một lần.

## 7. CDC và polling

### Change Data Capture

CDC đọc transaction log của database để phát hiện insert, update và delete. Nó phù hợp khi nhiều ứng dụng cùng ghi database hoặc không thể sửa tất cả writer để phát domain event.

CDC cung cấp thay đổi ở mức dữ liệu. Một row change không phải lúc nào cũng mang đầy đủ ngữ nghĩa nghiệp vụ. Projector có thể cần đọc thêm các bảng liên quan hoặc kết hợp nhiều change thành một projection hoàn chỉnh.

### Polling theo `updatedAt`

Với hệ thống nhỏ, có thể lưu watermark và định kỳ truy vấn:

```sql
SELECT *
FROM product
WHERE updated_at >= :watermark
ORDER BY updated_at, id
LIMIT :batch_size;
```

Không nên chỉ dùng `updated_at > :watermark` nếu nhiều bản ghi có cùng timestamp hoặc precision của database thấp. Một cursor ổn định có thể là cặp `(updated_at, id)`, hoặc dùng overlap window rồi deduplicate bằng version/ID.

Polling cũng cần xử lý delete. Một row bị xóa vật lý sẽ không còn xuất hiện trong query `updated_at`; cần soft delete, deletion log, outbox hoặc CDC để biết document nào phải xóa khỏi Elasticsearch.

## 8. Thiết kế search document theo query, không theo cấu trúc bảng

Search projection nên bắt đầu từ những câu hỏi mà API tìm kiếm phải trả lời:

- Người dùng tìm theo tên, SKU hay mô tả?
- Cần lọc theo brand, category, status, tenant hay thời gian?
- Cần sort theo giá, ngày cập nhật hay độ phổ biến?
- Có cần autocomplete hoặc synonym không?
- Có cần giữ quan hệ giữa các thuộc tính trong cùng một item không?
- Kết quả cần hiển thị field nào mà không gọi thêm service?

Từ query patterns đó, chọn field, mapping và hình dạng document. Không nên bê toàn bộ schema database vào Elasticsearch rồi mới tìm cách truy vấn.

### Ví dụ projection cho trang sản phẩm

```json
{
  "id": "p-100",
  "sku": "WM-100",
  "name": "Wireless Mouse",
  "nameSuggest": ["Wireless Mouse", "Mouse Wireless"],
  "description": "Compact wireless mouse with USB receiver",
  "brand": {
    "id": "b-10",
    "name": "Acme"
  },
  "categories": [
    { "id": "c-20", "name": "Accessories" },
    { "id": "c-21", "name": "Computer" }
  ],
  "priceAmount": 29.99,
  "currency": "USD",
  "status": "ACTIVE",
  "updatedAt": "2026-11-13T10:30:00Z"
}
```

Document đã phẳng hóa một số dữ liệu quan hệ để search và hiển thị không cần join. Cấu trúc có thể khác domain model và database schema.

## 9. Denormalization: sao chép field để truy vấn nhanh

Elasticsearch được tối ưu cho truy vấn trên document. Việc sao chép các field liên quan vào search document giúp tránh join ở thời điểm đọc.

Ví dụ mỗi product document lưu `brandName` thay vì chỉ lưu `brandId`. Khi query lọc hoặc hiển thị, API có thể dùng trực tiếp `brandName`.

Ưu điểm:

- Search query đơn giản và thường nhanh hơn.
- Có thể filter, sort và aggregate trên field đã denormalize.
- Search response có đủ dữ liệu hiển thị cơ bản.
- Giảm số lần gọi tới các service khác trong request tìm kiếm.

Chi phí:

- Một thay đổi ở nguồn liên quan có thể cần cập nhật nhiều projection.
- Dữ liệu lặp có thể tạm thời không đồng nhất.
- Rebuild cần kết hợp dữ liệu từ nhiều nguồn.
- Cần xác định rõ ownership và version cho từng phần projection.

Denormalization là quyết định có chủ đích cho read performance. Nó không làm mất yêu cầu đồng bộ; nó chuyển chi phí từ query time sang projection/update time.

## 10. Chọn object phẳng, nested hay join field

Mô hình projection cần phù hợp với ngữ nghĩa truy vấn.

| Hình dạng | Dùng khi | Ví dụ |
|---|---|---|
| Field phẳng | Chỉ cần lọc/sort theo thuộc tính độc lập | `brandName`, `status`, `priceAmount` |
| Object thường | Các field con được truy vấn độc lập, không cần ràng buộc cùng object | `brand.id`, `brand.name` |
| `nested` | Cần các điều kiện cùng khớp trên một phần tử của mảng object | Một variant có size và color cụ thể |
| Parent-child join | Child có vòng đời độc lập và cần truy vấn hai chiều theo quan hệ | Product với hàng triệu review độc lập, nếu workload chứng minh phù hợp |

### Lỗi phổ biến với object array

Giả sử product có hai variant:

```json
{
  "variants": [
    { "color": "red", "size": "S" },
    { "color": "blue", "size": "L" }
  ]
}
```

Nếu `variants` là object thường, Elasticsearch có thể làm phẳng field thành các mảng giá trị. Query `color=red AND size=L` có thể khớp document dù không có variant nào vừa đỏ vừa size L. Nếu điều kiện phải khớp trên cùng một variant, dùng `nested` mapping/query.

Không dùng `nested` chỉ vì JSON có mảng object. Hãy dùng khi truy vấn cần giữ quan hệ giữa các field trong cùng phần tử.

## 11. Spring Data Elasticsearch: tách domain entity và projection document

Có thể định nghĩa một model nguồn trong service/domain layer và một document riêng cho Elasticsearch.

Domain model (minh họa):

```java
public record Product(
    String id,
    String sku,
    String name,
    String brandId,
    String categoryId,
    ProductStatus status,
    long version) {
}
```

Search document:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-read")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

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

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private Double priceAmount;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    @Field(type = FieldType.Long)
    private Long sourceVersion;

    // Constructors, getters and setters
}
```

`ProductSearchDocument` có field đã denormalize và `sourceVersion` để theo dõi phiên bản nghiệp vụ. `sourceVersion` là field do ứng dụng quản lý trong projection, khác với `_version`, `_seq_no` và `_primary_term` của Elasticsearch.

### Mapper tạo projection

```java
public ProductSearchDocument toSearchDocument(
        Product product,
        Brand brand,
        Category category,
        Price price) {

    ProductSearchDocument doc = new ProductSearchDocument();
    doc.setId(product.id());
    doc.setSku(product.sku());
    doc.setName(product.name());
    doc.setBrandId(brand.id());
    doc.setBrandName(brand.name());
    doc.setCategoryId(category.id());
    doc.setCategoryName(category.displayName());
    doc.setStatus(product.status().name());
    doc.setPriceAmount(price.amount());
    doc.setUpdatedAt(Instant.now());
    doc.setSourceVersion(product.version());
    return doc;
}
```

Mapper là nơi chuyển đổi từ mô hình chuẩn sang mô hình search. Trong production, nên tiêm `Clock` thay vì gọi `Instant.now()` trực tiếp nếu cần kiểm thử thời gian; `updatedAt` cũng cần được định nghĩa rõ là thời gian nguồn hay thời gian projector cập nhật.

## 12. Ghi projection qua `ElasticsearchOperations`

Sau khi tạo search document, ghi vào index:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductProjectionWriter {

    private final ElasticsearchOperations operations;

    public ProductProjectionWriter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void upsert(ProductSearchDocument document) {
        operations.save(
            document,
            IndexCoordinates.of("products-read")
        );
    }
}
```

`save` với ID ổn định giúp ghi projection cho cùng entity ID vào cùng document. Nếu dùng alias, truyền `IndexCoordinates` theo alias được cấu hình cho ứng dụng. Hãy tách writer khỏi domain repository để rõ ràng đây là một read model.

Với lượng dữ liệu lớn, có thể dùng bulk indexing qua `ElasticsearchOperations` để giảm round trip. Khi dùng bulk, kiểm tra từng item response và retry lỗi phù hợp; không coi một bulk request là transaction nguyên tử.

## 13. Projector nhận event và tạo lại document

Một projector có thể nhận event chứa ID và version, sau đó đọc trạng thái mới nhất từ nguồn chuẩn rồi tạo projection:

```java
public class ProductProjectionHandler {

    private final ProductReadService productReadService;
    private final ProductProjectionMapper mapper;
    private final ProductProjectionWriter writer;

    public void onProductChanged(ProductChanged event) {
        Product product = productReadService.getById(event.productId());
        Brand brand = productReadService.getBrand(product.brandId());
        Category category = productReadService.getCategory(product.categoryId());
        Price price = productReadService.getCurrentPrice(product.id());

        ProductSearchDocument document =
            mapper.toSearchDocument(product, brand, category, price);

        writer.upsert(document);
    }
}
```

Đọc trạng thái mới nhất từ nguồn chuẩn giúp projector không phụ thuộc hoàn toàn vào payload event cũ. Tuy nhiên, cần bảo đảm các nguồn liên quan có thể được đọc nhất quán ở mức cần thiết và event có version để không ghi đè projection mới bằng một lần xử lý cũ.

Một lựa chọn khác là event mang đầy đủ dữ liệu cần thiết để dựng projection. Cách này giảm số lần gọi nguồn nhưng làm event payload lớn hơn và cần quản lý schema/version của event.

## 14. Idempotency: xử lý cùng event nhiều lần

Event có thể được giao lại khi worker crash sau khi xử lý nhưng trước khi acknowledge. Vì vậy, projector cần idempotent: nhận cùng event nhiều lần không tạo kết quả sai hoặc duplicate.

Với projection một document trên mỗi product, dùng product ID làm Elasticsearch `_id` giúp ghi lại cùng document thay vì tạo bản ghi mới có ID ngẫu nhiên.

```java
document.setId(event.productId());
operations.save(document, indexCoordinates);
```

Tuy nhiên, chỉ dùng ID ổn định chưa đủ khi event có thể đến sai thứ tự. Event cũ có thể ghi đè projection mới. Cần kết hợp version hoặc sequence nghiệp vụ.

### Dùng source version để chặn event cũ

Ví dụ event:

```json
{
  "eventId": "evt-9001",
  "aggregateId": "p-100",
  "aggregateVersion": 12,
  "eventType": "ProductUpdated"
}
```

Projection lưu `sourceVersion = 12`. Nếu event version 11 đến sau, projector không nên ghi đè document version 12. Có thể kiểm tra version hiện tại và bỏ qua event cũ, hoặc dùng conditional update/optimistic concurrency phù hợp để bảo đảm kiểm tra và ghi là an toàn khi có nhiều projector chạy đồng thời.

Không nhầm `aggregateVersion` do nguồn chuẩn phát hành với `_version` hoặc `_seq_no` do Elasticsearch quản lý. Chúng có phạm vi và ý nghĩa khác nhau.

## 15. Thứ tự event và cập nhật cạnh tranh

Giả sử ProductUpdated version 12 được xử lý trước version 11 vì worker chạy song song:

```text
Event version 11 -----------+----> đến chậm
                            |
Event version 12 ----> xử lý trước ----> projection version 12
                            |
Event version 11 ----------------------> không được ghi đè version 12
```

Các cách xử lý:

- Partition event theo aggregate ID để giữ thứ tự trong cùng aggregate.
- Dùng aggregate version tăng đơn điệu.
- Bỏ qua event có version nhỏ hơn hoặc bằng projection version hiện tại.
- Dùng Elasticsearch optimistic concurrency hoặc update script để kiểm tra version nguyên tử khi có nhiều writer.
- Giới hạn một projector xử lý mỗi key tại một thời điểm nếu kiến trúc cho phép.

Nếu kiểm tra version bằng một lần GET rồi save không điều kiện, hai worker vẫn có thể race. Khi cần bảo đảm, việc kiểm tra version và ghi phải được thực hiện theo một thao tác có điều kiện hoặc cơ chế serialize theo key.

## 16. Projection từ nhiều nguồn dữ liệu

Một document có thể phụ thuộc vào Product, Brand, Price, Inventory và Rating. Khi một nguồn thay đổi, projector phải cập nhật đúng phần projection liên quan.

```text
Product events ----+
Brand events ------+
Price events ------+----> Projection coordinator
Inventory events -+              |
Rating events -----+              v
                         ProductSearchDocument
```

Có hai chiến lược thường gặp:

### Đọc lại toàn bộ projection

Mỗi event kích hoạt việc đọc lại tất cả nguồn cần thiết rồi tạo document mới. Cách này đơn giản về logic và giảm nguy cơ merge sai field, nhưng có thể tạo nhiều read traffic và yêu cầu các service nguồn sẵn sàng.

### Cập nhật một phần projection

Mỗi event chỉ cập nhật các field do source đó sở hữu. Cách này giảm số lần đọc, nhưng cần quản lý rõ field ownership, version từng phần và khả năng event đến sai thứ tự.

Với dữ liệu ít thay đổi hoặc projection nhỏ, rebuild document từ nguồn chuẩn thường dễ duy trì hơn. Với event volume cao và nhiều source, có thể cần projection state riêng hoặc event model được thiết kế để merge an toàn.

### Không để event một source ghi đè field của source khác

Nếu ProductUpdated tạo lại document mà không đọc lại Price, nó có thể ghi giá cũ. Nếu PriceChanged ghi một partial document không cẩn thận, nó có thể làm mất các field sản phẩm. Cần có một trong các cơ chế:

- Rebuild đầy đủ từ các nguồn chuẩn.
- Lưu projection state và cập nhật field theo owner.
- Gửi event chứa snapshot đủ thông tin.
- Tách projection theo use case/source nếu một document quá khó đồng bộ.

## 17. Xóa dữ liệu và tombstone

Delete event cần được xử lý như một thay đổi dữ liệu, không phải một trường hợp bỏ qua. Nếu projector không nhận biết delete, document cũ vẫn tồn tại trong Elasticsearch và tiếp tục xuất hiện trong search.

Ví dụ event:

```json
{
  "eventId": "evt-9010",
  "aggregateId": "p-100",
  "aggregateVersion": 13,
  "eventType": "ProductDeleted",
  "occurredAt": "2026-11-13T11:00:00Z"
}
```

Projector có thể xóa document:

```java
operations.delete(
    event.productId(),
    ProductSearchDocument.class,
    IndexCoordinates.of("products-read")
);
```

Nếu có khả năng event cũ đến sau delete, xóa vật lý có thể làm mất version marker cần thiết để chặn event cũ tái tạo document. Khi đó có thể dùng tombstone:

```json
{
  "id": "p-100",
  "sourceVersion": 13,
  "deleted": true,
  "deletedAt": "2026-11-13T11:00:00Z"
}
```

Search query lọc `deleted=false`; tombstone được giữ đủ lâu để event cũ không thể hồi sinh document. Sau khoảng retention và khi chắc chắn không còn event cũ/replay cần thiết, có thể dọn tombstone.

## 18. Backfill ban đầu và đồng bộ thay đổi trong lúc quét

Khi tạo index mới, cần nạp toàn bộ dữ liệu hiện có (backfill) rồi tiếp tục áp dụng thay đổi mới. Một lỗi phổ biến là quét snapshot trước, sau đó mới bắt đầu nhận event; thay đổi phát sinh trong khoảng giữa hai bước có thể bị mất.

Một trình tự an toàn hơn:

```text
1. Xác định watermark/offset bắt đầu bắt thay đổi
             |
             v
2. Bắt đầu giữ event/CDC từ watermark đó
             |
             v
3. Quét snapshot nguồn chuẩn
             |
             v
4. Ghi projection theo batch
             |
             v
5. Phát lại event sau watermark
             |
             v
6. Áp dụng version/order để event cũ không ghi đè mới
             |
             v
7. Theo dõi lag và chuyển sang xử lý liên tục
```

Chi tiết snapshot/offset phụ thuộc database, CDC hoặc broker. Mục tiêu là không có khoảng trống giữa dữ liệu snapshot và luồng thay đổi.

### Không chỉ dựa vào `updatedAt` nếu cần không bỏ sót

Timestamp có thể trùng, precision thấp hoặc đồng hồ giữa hệ thống lệch nhau. Dùng cursor ổn định, overlap window, event ID hoặc database log position theo cơ chế nguồn hỗ trợ. Projector cần idempotent để xử lý lại vùng overlap.

## 19. Reconciliation: phát hiện projection bị lệch

Ngay cả khi có outbox/CDC, projection vẫn có thể lệch do bug, mapping lỗi, event poison, thao tác ghi thủ công hoặc một lần outage kéo dài. Reconciliation là quá trình so sánh và sửa projection dựa trên nguồn chuẩn.

Một số cách:

- So sánh số lượng bản ghi theo tenant/status/partition.
- So sánh source version giữa nguồn và projection.
- Lấy danh sách ID đã thay đổi trong một khoảng thời gian rồi dựng lại.
- Quét partition và upsert lại projection.
- Kiểm tra document thiếu hoặc tombstone không hợp lệ.
- Định kỳ rebuild toàn index khi quy mô cho phép.

Không nhất thiết so sánh toàn bộ JSON nếu document có field dẫn xuất hoặc analyzer-specific. Có thể so sánh source version, hash của các field projection hoặc các invariant nghiệp vụ quan trọng.

### Rebuild index không nên làm mất index đang phục vụ

Một chiến lược phổ biến là tạo index version mới, nạp backfill, áp dụng event mới đến, kiểm tra rồi chuyển alias đọc sang index mới. Index cũ giữ nguyên trong thời gian rollback nếu cần.

## 20. Versioned index và alias cho projection

Không nên gắn ứng dụng trực tiếp với tên index vật lý nếu cần rebuild hoặc thay mapping. Dùng alias giúp chuyển read target mà không đổi API của ứng dụng.

Ví dụ:

```text
products-v1  <--- products-read

Rebuild:
products-v2  <--- nạp dữ liệu và đồng bộ event

Sau khi xác nhận:
products-read -> products-v2
```

Alias có thể được chuyển bằng một `_aliases` request nguyên tử:

```http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "products-v1", "alias": "products-read" } },
    { "add": { "index": "products-v2", "alias": "products-read" } }
  ]
}
```

Nếu cần alias ghi riêng, có thể dùng `products-write` trỏ tới index write hiện hành. Cần phân biệt alias đọc, alias ghi và write index trong môi trường rollover hoặc nhiều index.

## 21. Schema evolution của search projection

Search document có thể thay đổi khi yêu cầu tìm kiếm mới xuất hiện:

- Thêm field filter hoặc sort.
- Đổi analyzer hoặc normalizer.
- Thêm autocomplete field.
- Thay object thường bằng nested.
- Đổi kiểu dữ liệu hoặc tên field.
- Bổ sung dữ liệu denormalized từ một service mới.

Không phải mọi thay đổi mapping đều có thể áp dụng trực tiếp lên field hiện hữu. Đổi analyzer hoặc kiểu field thường cần tạo index mới và reindex. Vì vậy, search projection nên có version/schema version rõ ràng.

Ví dụ document có thể lưu `projectionVersion` để hỗ trợ kiểm tra:

```json
{
  "id": "p-100",
  "projectionVersion": 3,
  "sourceVersion": 42,
  "name": "Wireless Mouse"
}
```

`projectionVersion` cho biết cấu trúc/logic projection; `sourceVersion` cho biết trạng thái nguồn đã được áp dụng. Hai giá trị giải quyết hai câu hỏi khác nhau.

## 22. Chọn dữ liệu nào không đưa vào projection

Không phải field nào trong database cũng nên index vào Elasticsearch.

Nên cân nhắc loại bỏ:

- Secret, password hash hoặc token xác thực.
- Field không dùng để search, filter, sort, aggregate hay hiển thị.
- Blob hoặc nội dung lớn chỉ được tải khi mở chi tiết.
- Dữ liệu cá nhân không cần thiết cho use case tìm kiếm.
- Field có tần suất cập nhật rất cao nhưng ít giá trị trong search projection.
- Dữ liệu chỉ có thể truy cập theo quyền hạn động nếu chưa có cơ chế bảo vệ phù hợp.

Projection nhỏ hơn thường giảm dung lượng index, network payload và chi phí cập nhật. Source filtering cũng có thể giới hạn dữ liệu trả về, nhưng không thay thế việc quyết định field nào thực sự cần được lập chỉ mục.

## 23. Quyền truy cập và multi-tenancy

Nếu search projection chứa dữ liệu của nhiều tenant, tenant ID cần được lập chỉ mục và filter bắt buộc trong mọi query phù hợp. Không dựa vào UI để ẩn kết quả của tenant khác.

Ví dụ document:

```json
{
  "id": "p-100",
  "tenantId": "tenant-42",
  "name": "Wireless Mouse"
}
```

Query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "match": { "name": "wireless" } }
      ]
    }
  }
}
```

Tenant ID nên được lấy từ security context đã xác thực ở server, không tin trực tiếp giá trị tenant do client gửi. Nếu dùng routing theo tenant, vẫn giữ filter tenant trong query để thể hiện phạm vi dữ liệu và hỗ trợ kiểm soát quyền.

## 24. Theo dõi sức khỏe đồng bộ

Một hệ thống projection cần metrics riêng, không chỉ dựa vào trạng thái Elasticsearch cluster.

Các chỉ số hữu ích:

- Số event nhận, thành công, retry và dead-letter.
- Consumer lag hoặc độ trễ event.
- Thời gian từ source commit đến projection update.
- Số document upsert/delete.
- Số event bị bỏ qua do version cũ.
- Số lỗi mapping/serialization.
- Bulk item failure và retry count.
- Số document theo `projectionVersion`.
- Số document theo source version hoặc partition.
- Reconciliation mismatch count.
- Backfill progress và thời gian hoàn tất.

Log nên có event ID, aggregate ID, source version, projection index/version và correlation ID. Tránh ghi toàn bộ payload nhạy cảm vào log.

### Độ trễ projection

Đo khoảng cách giữa thời điểm nguồn commit và thời điểm document được ghi/refresh để search. Có thể phân biệt:

- Event delivery lag: event chưa tới projector.
- Processing lag: projector nhận event nhưng chưa xử lý xong.
- Elasticsearch write latency: request ghi chậm hoặc retry.
- Search visibility lag: document đã ghi nhưng chưa refresh.

Phân tách các loại lag giúp xác định nút thắt ở broker, projector, Elasticsearch hay refresh policy.

## 25. Kiểm thử projection

Kiểm thử không chỉ xác nhận `repository.save()` không ném exception. Cần kiểm tra nội dung projection và hành vi khi đồng bộ bất thường.

Các trường hợp nên có:

1. Product event tạo đúng document và ID ổn định.
2. Brand/Category/Price được denormalize đúng vào projection.
3. Event trùng không tạo duplicate hoặc làm sai dữ liệu.
4. Event version cũ không ghi đè version mới.
5. Event update và delete được áp dụng đúng.
6. Event lỗi được retry và chuyển dead-letter khi vượt chính sách.
7. Backfill không bỏ mất thay đổi phát sinh trong lúc quét.
8. Reconciliation sửa được document thiếu/lệch.
9. Mapping và analyzer đáp ứng query patterns.
10. Tenant filter không trả dữ liệu chéo tenant.
11. Rebuild index mới có thể chuyển alias sau khi đồng bộ.

Với integration test Elasticsearch, kiểm tra search visibility bằng refresh policy phù hợp hoặc refresh index sau khi nạp fixture. Không dùng sleep cố định để chờ document xuất hiện.

## 26. Những lỗi thiết kế thường gặp

### Coi Elasticsearch là nguồn chuẩn cho giao dịch

Search projection có thể trễ và có thể rebuild. Với quyết định cần trạng thái mới nhất, đọc hoặc xác nhận từ nguồn nghiệp vụ chuẩn.

### Ghi database và Elasticsearch như một transaction

Hai hệ thống không tự chia sẻ transaction ACID. Dual write có thể lệch khi một bên lỗi. Dùng outbox/CDC hoặc có reconcile rõ ràng.

### Dùng domain entity trực tiếp cho mọi index

Domain model và search document có mục tiêu khác nhau. Tách projection khi cần denormalize, mapping hoặc schema riêng.

### Không có owner cho field denormalized

Nhiều event có thể ghi đè field của nhau. Xác định source owner và cách cập nhật projection.

### Không xử lý event trùng hoặc sai thứ tự

At-least-once delivery và worker song song có thể tạo duplicate/out-of-order update. Dùng ID ổn định, version và idempotency.

### Xóa vật lý nhưng không giữ dấu version

Event cũ có thể tái tạo document đã xóa. Cân nhắc tombstone hoặc cơ chế versioned delete.

### Backfill trước rồi mới bật event consumer

Thay đổi phát sinh trong khoảng giữa hai bước có thể bị mất. Chốt watermark/offset và replay event sau snapshot.

### Không có reconciliation

Một số lỗi hiếm hoặc thao tác thủ công có thể làm projection lệch lâu dài. Có job đối soát theo version/hash/partition.

### Rebuild index ngay trên index đang phục vụ

Thay mapping hoặc xóa index có thể gây downtime. Dùng versioned index và alias switch.

## 27. Quy trình thiết kế nguồn và projection

Khi bắt đầu một use case tìm kiếm, có thể đi theo trình tự:

1. Liệt kê truy vấn, filter, sort, aggregation và field hiển thị của search API.
2. Xác định nguồn chuẩn cho từng field và owner chịu trách nhiệm cập nhật.
3. Chọn projection riêng phản ánh query patterns, không sao chép máy móc schema database.
4. Quyết định field nào denormalize, field nào nested và field nào không đưa vào index.
5. Chọn cơ chế đồng bộ: outbox, CDC, polling hoặc batch theo mức độ tin cậy/độ trễ yêu cầu.
6. Thiết kế event ID, aggregate ID, source version và idempotency.
7. Xử lý thứ tự event, concurrent projector và deletion/tombstone.
8. Thiết kế backfill có watermark/offset để không bỏ lỡ thay đổi mới.
9. Dùng mapper/projector riêng và ghi bằng ID ổn định qua Spring Data Elasticsearch.
10. Thiết lập retry, dead-letter, reconciliation và metrics.
11. Dùng index version và alias cho thay đổi mapping/rebuild.
12. Kiểm thử consistency, replay, tenant isolation và search visibility.

## 28. Kết luận

Nguồn dữ liệu chuẩn giữ trạng thái nghiệp vụ có thẩm quyền; search projection là read model được tối ưu cho truy vấn và có thể được dựng lại. Chọn nguồn chuẩn theo từng field, xác định owner cho dữ liệu denormalized và thiết kế projection theo query patterns giúp tránh biến Elasticsearch thành một bản sao database khó đồng bộ.

Trong Spring Data Elasticsearch, nên dùng search document riêng khi cấu trúc tìm kiếm khác domain model, tạo mapper/projector để chuyển dữ liệu từ nguồn chuẩn và ghi projection bằng ID ổn định. Đồng bộ có thể dùng outbox, CDC, polling hoặc batch; bất kể cơ chế nào, cần xử lý event trùng/sai thứ tự, version, delete, backfill và reconciliation. Khi mapping thay đổi, dựng index version mới rồi chuyển alias sau khi kiểm tra. Elasticsearch phục vụ đọc nhanh; các quyết định giao dịch quan trọng vẫn phải dựa vào nguồn nghiệp vụ có thẩm quyền.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Elasticsearch – Index aliases](https://www.elastic.co/docs/manage-data/data-store/aliases)
- [Elasticsearch – Reindex API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex)
- [Debezium – Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Debezium – Change data capture concepts](https://debezium.io/documentation/reference/stable/)
