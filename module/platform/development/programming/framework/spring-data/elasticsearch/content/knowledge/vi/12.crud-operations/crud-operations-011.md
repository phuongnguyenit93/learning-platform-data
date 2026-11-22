# Vì sao save không tương đương cập nhật một phần

Trong Spring Data Elasticsearch, `repository.save(entity)` là thao tác ghi document theo ID. Khi document đã tồn tại, thao tác này sử dụng semantics index của Elasticsearch: nội dung document được ghi lại theo biểu diễn của entity. Nó không có nghĩa là Spring Data chỉ gửi những thuộc tính Java vừa thay đổi.

Điều này khác với **partial update** của Elasticsearch Update API. Với partial update, ứng dụng gửi một phần document chứa các field cần thay đổi; những field không xuất hiện trong phần cập nhật được giữ nguyên. Update API cũng hỗ trợ script để thay đổi giá trị dựa trên nội dung document hiện tại.

Nếu ứng dụng tải một entity đầy đủ, thay đổi một thuộc tính rồi `save`, kết quả thường đúng như mong đợi vì các field khác vẫn có trong entity. Nhưng nếu ứng dụng tạo một entity mới chỉ chứa ID và một vài field, rồi gọi `save`, các field không có trong biểu diễn được ghi có thể biến mất khỏi `_source` của document. Đây là nguyên nhân phổ biến khiến dữ liệu bị mất ngoài ý muốn.

## 1. Hai thao tác có mục đích khác nhau

Giả sử document sản phẩm hiện tại trong index `products` là:

```json
{
  "sku": "SKU-1001",
  "name": "Bàn phím cơ",
  "price": 185000,
  "stock": 25,
  "description": "Bàn phím cơ switch brown",
  "active": true
}
```

Ứng dụng chỉ muốn đổi `stock` thành `20`.

**Ghi toàn bộ document bằng `save`:** entity được serialize thành document mới. Nếu entity gửi lên chỉ có `id`, `stock` và một vài field, các field khác không có trong document mới sẽ không còn trong `_source` sau khi ghi.

**Cập nhật một phần:** gửi một document con chỉ chứa `stock`. Elasticsearch áp dụng phần thay đổi vào document hiện có và giữ các field khác.

| Thao tác | Ý nghĩa | Field không được gửi |
|---|---|---|
| `save(entity)` | Index nội dung document theo entity và ID | Có thể bị loại khỏi document mới |
| Update API với `doc` | Merge phần document được gửi vào document hiện tại | Được giữ nguyên |
| Update API với `script` | Chạy logic thay đổi trên `_source` hiện tại | Được giữ nguyên nếu script không sửa/xóa |

Đây là khác biệt về semantics, không chỉ khác cú pháp Java.

## 2. `save` ghi document theo ID

Một repository Spring Data Elasticsearch thường được khai báo như sau:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Integer)
    private Integer stock;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    protected Product() {
    }

    // Constructors and accessors omitted for brevity.
}
```

Khi gọi:

```java
productRepository.save(product);
```

Spring Data chuyển entity thành document theo mapping metadata và gửi thao tác ghi tới index được xác định bởi `@Document`. Với một ID đã tồn tại, thao tác index ghi nội dung document mới dưới cùng ID. Các thuộc tính không được biểu diễn trong document mới không tự được lấy từ document cũ để ghép vào.

Ở tầng REST, semantics tương ứng gần với Index API:

```http
PUT /products/_doc/product-1001
{
  "sku": "SKU-1001",
  "name": "Bàn phím cơ",
  "price": 185000,
  "stock": 20,
  "description": "Bàn phím cơ switch brown",
  "active": true
}
```

Request gửi toàn bộ nội dung document mong muốn. Nếu lần ghi sau chỉ gửi `stock` và `name`, các field khác không có trong document mới có thể biến mất khỏi `_source`.

### 2.1 Ví dụ gây mất field khi save entity không đầy đủ

Giả sử code tạo một object chỉ có ID và stock:

```java
Product patch = new Product();
patch.setId("product-1001");
patch.setStock(20);

productRepository.save(patch);
```

Nếu entity được serialize thành:

```json
{
  "stock": 20
}
```

thì document sau thao tác ghi có thể chỉ còn nội dung đó (ngoài metadata `_id`). Các field `sku`, `name`, `price`, `description` và `active` không tự được giữ lại.

Đây là lý do không nên dùng `save` như một cách gửi DTO cập nhật một phần. `save` nhận một entity đại diện cho document cần ghi; nó không tự biết field nào người dùng muốn giữ nguyên, field nào chưa gửi và field nào muốn xóa.

### 2.2 Khi nào save là lựa chọn đúng?

Dùng `save` khi ứng dụng có trạng thái đầy đủ của document cần ghi và muốn ghi lại document đó:

- Tạo document mới.
- Thay thế nội dung document theo một entity đầy đủ.
- Đồng bộ lại toàn bộ document từ nguồn dữ liệu chuẩn.
- Ghi lại document sau khi đã đọc đầy đủ, thay đổi và kiểm soát concurrency phù hợp.

Nếu entity là projection, DTO từ request PATCH hoặc object chỉ chứa các field thay đổi, không nên coi nó là bản đại diện đầy đủ để gọi `save`.

## 3. Partial update bằng Elasticsearch Update API

Elasticsearch cung cấp endpoint `_update` để cập nhật một document hiện có. Request có thể chứa `doc` là phần document cần thay đổi:

```http
POST /products/_update/product-1001
{
  "doc": {
    "stock": 20
  }
}
```

Elasticsearch lấy document hiện tại, áp dụng phần `doc`, sau đó index lại document đã cập nhật. Các field không được nêu trong `doc` được giữ nguyên.

Sau request, document có thể là:

```json
{
  "sku": "SKU-1001",
  "name": "Bàn phím cơ",
  "price": 185000,
  "stock": 20,
  "description": "Bàn phím cơ switch brown",
  "active": true
}
```

Chỉ `stock` thay đổi. Các field còn lại vẫn được giữ lại.

### 3.1 Cập nhật nhiều field cùng lúc

```http
POST /products/_update/product-1001
{
  "doc": {
    "stock": 20,
    "active": false
  }
}
```

Request cập nhật `stock` và `active`, còn các field khác không được nêu thì giữ nguyên.

### 3.2 Field bị bỏ qua và field có giá trị null

Trong partial document, cần phân biệt:

- Field **không xuất hiện** trong `doc`: không yêu cầu thay đổi field đó.
- Field xuất hiện với một giá trị: cập nhật field đó.
- Field xuất hiện với `null`: đây là một giá trị được gửi tới update; không nên mặc định rằng nó tương đương với việc xóa field khỏi `_source`.

Nếu cần xóa một field khỏi `_source`, dùng script xóa rõ ràng:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "ctx._source.remove('description')"
  }
}
```

Điều này giúp API phân biệt rõ “không thay đổi”, “đặt giá trị null” và “xóa thuộc tính”. Nếu ứng dụng dùng null để biểu diễn field không được gửi trong PATCH request, cần thiết kế DTO/patch semantics riêng thay vì tự động chuyển mọi null thành thao tác update.

### 3.3 Cập nhật object con

Giả sử document có object địa chỉ:

```json
{
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 1",
    "street": "Le Loi"
  }
}
```

Một partial doc có thể cập nhật thuộc tính con:

```http
POST /customers/_update/customer-1001
{
  "doc": {
    "address": {
      "district": "District 3"
    }
  }
}
```

Update API áp dụng semantics merge cho phần document được gửi. Tuy nhiên, với object/array phức tạp, cần kiểm tra rõ cấu trúc được gửi và kết quả `_source`; đặc biệt không nên giả định một mảng sẽ được merge từng phần tử theo khóa nghiệp vụ.

### 3.4 Mảng và nested object

Với một field mảng như `variants`, partial update không phải cơ chế tự động tìm một phần tử theo `sku` rồi sửa riêng phần tử đó. Khi gửi giá trị mới cho field mảng, hãy coi đó là thay thế giá trị của field mảng, trừ khi dùng script để thao tác trên phần tử cụ thể.

Ví dụ cập nhật toàn bộ mảng:

```http
POST /products/_update/product-1001
{
  "doc": {
    "tags": ["keyboard", "wireless"]
  }
}
```

Nếu cần thay đổi `stock` của một variant trong mảng nested, có thể dùng script duyệt mảng và sửa phần tử khớp:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "for (def variant : ctx._source.variants) { if (variant.sku == params.sku) { variant.stock = params.stock; } }",
    "params": {
      "sku": "SKU-RED-M",
      "stock": 12
    }
  }
}
```

Script chỉ sửa phần tử có SKU phù hợp. Trong ứng dụng thực tế, nên quyết định rõ hành vi khi không tìm thấy phần tử, có nhiều phần tử trùng SKU hoặc cần thêm mới một variant. Mapping `nested` hỗ trợ truy vấn giữ quan hệ giữa các phần tử; nó không tự biến update document thành một thao tác patch theo phần tử.

## 4. Dùng partial update qua Spring Data Elasticsearch

`ElasticsearchRepository` cung cấp `save` cho thao tác ghi entity, nhưng không nên giả định nó có một method `savePartial` tự động merge các field. Khi cần update một phần, có thể dùng `ElasticsearchOperations` cùng `UpdateQuery`.

Ví dụ cập nhật stock:

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.stereotype.Service;

@Service
public class ProductUpdateService {

    private final ElasticsearchOperations operations;

    public ProductUpdateService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void updateStock(String productId, int newStock) {
        Document partialDocument = Document.from(
            Map.of("stock", newStock)
        );

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
            .withDocument(partialDocument)
            .build();

        operations.update(updateQuery, IndexCoordinates.of("products"));
    }
}
```

`Document` ở đây chỉ chứa field cần thay đổi. `UpdateQuery` gắn document con với ID cần cập nhật. `ElasticsearchOperations.update(...)` gửi thao tác update tới index được chỉ định.

API builder có thể có thêm tùy chọn như routing, retry on conflict, upsert hoặc script. Tên package và overload cần được đối chiếu với phiên bản Spring Data Elasticsearch của dự án, nhưng nguyên tắc là: truyền partial document vào Update API thay vì serialize một entity thiếu field qua `save`.

### 4.1 Tách DTO PATCH khỏi entity lưu trữ

REST API thường nhận request chỉ có field người dùng muốn thay đổi. Ví dụ:

```java
public record UpdateStockRequest(Integer stock) {
}
```

Service có thể chuyển request thành partial document:

```java
public void updateStock(String productId, UpdateStockRequest request) {
    if (request.stock() == null || request.stock() < 0) {
        throw new IllegalArgumentException("stock must be non-negative");
    }

    Document partialDocument = Document.from(
        Map.of("stock", request.stock())
    );

    UpdateQuery query = UpdateQuery.builder(productId)
        .withDocument(partialDocument)
        .build();

    operations.update(query, IndexCoordinates.of("products"));
}
```

DTO PATCH diễn đạt phần dữ liệu client gửi lên. Entity `Product` vẫn là mô hình đầy đủ của document. Không nên tạo entity giả chỉ chứa một vài field rồi gọi `save`.

### 4.2 Upsert: tạo nếu chưa tồn tại

Mặc định, Update API yêu cầu document đã tồn tại. Nếu không có document tương ứng, thao tác update có thể trả lỗi not found. Khi muốn tạo document nếu chưa có, Elasticsearch hỗ trợ `doc_as_upsert` hoặc `upsert`:

```http
POST /products/_update/product-1001
{
  "doc": {
    "stock": 20
  },
  "doc_as_upsert": true
}
```

Nếu document đã tồn tại, `stock` được cập nhật và các field khác được giữ. Nếu chưa tồn tại, phần `doc` được dùng để tạo document mới. Trong ví dụ này document mới chỉ có `stock`; nó không tự có `sku`, `name` hoặc `price`.

Vì vậy, `doc_as_upsert` chỉ phù hợp nếu partial document cũng đủ để tạo một document hợp lệ khi thiếu ID. Nếu document mới cần nhiều field bắt buộc, hãy cung cấp một `upsert` document đầy đủ hoặc kiểm tra tồn tại và tạo theo luồng nghiệp vụ riêng.

## 5. Update bằng script

Partial `doc` phù hợp khi biết giá trị mới của một số field. Script phù hợp khi cần thay đổi dựa trên giá trị hiện tại, tính toán hoặc thao tác có điều kiện.

### 5.1 Tăng số lượng tồn kho

Nếu muốn tăng stock thêm một lượng thay vì ghi một giá trị tuyệt đối:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 5
    }
  }
}
```

Script đọc giá trị hiện tại trong `_source` rồi cộng thêm `delta`. Đây là cách phù hợp hơn việc ứng dụng đọc stock cũ, cộng 5 ở Java rồi ghi lại, vì giữa lúc đọc và ghi có thể có một request khác cập nhật stock.

Nếu `stock` có thể null hoặc chưa tồn tại, script cần xử lý trường hợp đó rõ ràng:

```json
{
  "script": {
    "source": "if (ctx._source.stock == null) { ctx._source.stock = params.delta; } else { ctx._source.stock += params.delta; }",
    "params": {
      "delta": 5
    }
  }
}
```

### 5.2 Cập nhật có điều kiện

Ví dụ chỉ cập nhật giá nếu giá hiện tại nhỏ hơn một ngưỡng:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "if (ctx._source.price < params.limit) { ctx._source.price = params.newPrice; } else { ctx.op = 'noop'; }",
    "params": {
      "limit": 200000,
      "newPrice": 199000
    }
  }
}
```

`ctx.op = 'noop'` cho Elasticsearch biết không cần ghi lại document nếu điều kiện không thỏa. Script cần được kiểm soát chặt chẽ; không nối chuỗi đầu vào người dùng trực tiếp vào source. Dùng params để truyền dữ liệu.

### 5.3 Script và hiệu năng

Script update có thể thực hiện logic linh hoạt nhưng phải chạy trên shard chứa document. Với số lượng document lớn, update-by-query hoặc bulk update có thể tạo tải đáng kể. Hãy giới hạn phạm vi, theo dõi thời gian xử lý, version conflict và throttling. Không dùng script chỉ để thay một giá trị tĩnh đơn giản nếu partial `doc` đã đủ.

## 6. Save, partial update và update-by-query

Elasticsearch có nhiều cách thay đổi document. Chọn theo phạm vi và ý nghĩa dữ liệu:

| Cách làm | Phạm vi | Trường hợp phù hợp |
|---|---|---|
| `repository.save(entity)` | Một document, ghi nội dung entity | Tạo hoặc ghi lại document đầy đủ |
| `POST /index/_update/id` với `doc` | Một document, cập nhật một phần | Thay một số field đã biết |
| `_update` với script | Một document, logic dựa trên trạng thái hiện tại | Tăng/giảm, điều kiện, sửa một phần tử mảng |
| `_update_by_query` | Nhiều document thỏa query | Cập nhật hàng loạt theo điều kiện |
| Bulk API | Nhiều thao tác ghi/update/delete | Ingest hoặc cập nhật số lượng lớn theo batch |

`_update_by_query` không phải cách thay thế `save` cho mọi trường hợp. Nó đọc các document thỏa query rồi áp dụng script hoặc partial update trên từng document. Cần quản lý version conflict, số lượng document và tải cluster.

## 7. Cập nhật một phần và vấn đề concurrency

Partial update giúp tránh ghi lại những field không liên quan, nhưng không tự giải quyết mọi vấn đề đồng thời.

### 7.1 Lost update khi đọc-sửa-save

Giả sử hai request cùng đọc một document có `stock = 10`:

1. Request A đọc `10`, muốn giảm 2.
2. Request B đọc `10`, muốn giảm 3.
3. A tính `8` và save.
4. B tính `7` và save.

Kết quả cuối cùng có thể là `7`, trong khi tổng hai thao tác giảm đáng lẽ tạo ra `5`. Đây là lost update do cả hai request tính toán trên cùng một giá trị cũ.

Nếu nghiệp vụ là tăng/giảm tương đối, script update trên server có thể thực hiện phép tính trên trạng thái hiện tại. Tuy nhiên, cần định nghĩa tính idempotent và retry cho nghiệp vụ, vì request có thể được gửi lại sau timeout.

### 7.2 Optimistic concurrency control

Elasticsearch hỗ trợ optimistic concurrency control bằng `_seq_no` và `_primary_term`. Client có thể yêu cầu update chỉ thành công nếu document vẫn ở phiên bản mà nó đã đọc. Nếu document đã thay đổi, Elasticsearch trả version conflict để ứng dụng quyết định đọc lại và thử lại hoặc báo xung đột.

Spring Data Elasticsearch cũng hỗ trợ version property qua annotation `@Version` trong các API phù hợp. Khi sử dụng, cần hiểu contract của phiên bản Spring Data và cách version được truyền vào thao tác ghi/update.

Optimistic locking phù hợp khi cần bảo đảm không ghi đè thay đổi của người khác mà không biết. Nó không thay thế thiết kế atomic update cho phép cộng/trừ hoặc các thao tác cần tính trên giá trị hiện tại.

### 7.3 Retry on conflict

Update API hỗ trợ `retry_on_conflict` để thử lại khi có xung đột version trong quá trình update. Cơ chế này giúp một số thao tác update có thể chạy lại trên phiên bản mới hơn của document.

Không bật retry vô hạn. Script cần an toàn khi chạy lại, và số lần retry cần phù hợp với concurrency. Một script tăng số lượng thêm 1 có semantics khác với việc đặt stock thành một giá trị tuyệt đối; phải hiểu thao tác nào được phép lặp.

## 8. Read-after-write và refresh

Elasticsearch là hệ thống near real-time cho search. `save` hoặc update có thể trả về thành công trước khi thay đổi xuất hiện trong kết quả `_search`, vì search cần refresh. Đọc document theo ID bằng GET có semantics real-time theo mặc định, khác với query search.

Nếu nghiệp vụ cần search thấy thay đổi ngay sau update, có thể dùng refresh policy phù hợp hoặc refresh index sau một nhóm thao tác. Không nên ép refresh sau mọi request ghi nếu không cần thiết, vì refresh thường xuyên làm giảm hiệu quả indexing.

Trong Spring Data Elasticsearch, có thể cấu hình refresh policy trên thao tác/entity theo khả năng phiên bản, hoặc sử dụng API update có hỗ trợ refresh option. Hãy phân biệt yêu cầu search visibility với yêu cầu durability; refresh không phải là commit hay transaction.

## 9. Thiết kế API PATCH ở tầng ứng dụng

HTTP `PUT` thường biểu diễn việc thay thế representation của resource, trong khi `PATCH` biểu diễn thay đổi một phần. Cách ánh xạ chính xác còn tùy contract API, nhưng sự phân biệt này tương ứng khá rõ với `save` và Update API.

Ví dụ DTO:

```java
public record UpdateProductRequest(
    String name,
    Double price,
    Integer stock
) {
}
```

Nếu mọi thuộc tính null đều có nghĩa “không gửi”, có thể tạo partial document chỉ từ các giá trị khác null. Nhưng cách này không cho phép client chủ động xóa field bằng null. Nếu API cần ba trạng thái “không gửi”, “đặt null” và “xóa”, cần một kiểu patch representation riêng hoặc dùng JSON Merge Patch/JSON Patch theo contract rõ ràng.

Ví dụ đơn giản chỉ cập nhật field được gửi và không hỗ trợ xóa:

```java
Map<String, Object> changes = new HashMap<>();

if (request.name() != null) {
    changes.put("name", request.name());
}
if (request.price() != null) {
    changes.put("price", request.price());
}
if (request.stock() != null) {
    changes.put("stock", request.stock());
}

if (!changes.isEmpty()) {
    UpdateQuery query = UpdateQuery.builder(productId)
        .withDocument(Document.from(changes))
        .build();
    operations.update(query, IndexCoordinates.of("products"));
}
```

Đoạn code minh họa cách xây dựng partial document. Ứng dụng thực tế cần validate từng field, giới hạn field được phép sửa và xử lý rõ trường hợp không có thay đổi. Không nhận một map tùy ý từ client rồi gửi thẳng vào `_update`, vì client có thể thay đổi các field hệ thống hoặc field không được phép sửa.

## 10. Khi nào nên đọc entity rồi save lại?

Đọc entity đầy đủ, thay đổi một thuộc tính rồi save có thể phù hợp nếu:

- Entity thực sự chứa toàn bộ document cần giữ.
- Không có projection hoặc mapping bỏ qua các field cần bảo toàn.
- Ứng dụng chấp nhận ghi lại toàn bộ document.
- Có kiểm soát concurrency nếu nhiều request có thể cập nhật cùng lúc.

Ví dụ:

```java
Product product = productRepository.findById(id)
    .orElseThrow(() -> new ProductNotFoundException(id));

product.setStock(20);
productRepository.save(product);
```

Đoạn này khác hoàn toàn việc tạo một `Product` mới chỉ có ID và stock. Entity đã được đọc đầy đủ nên các thuộc tính khác vẫn hiện diện khi serialize, giả sử mapping/converter đọc chúng đúng.

Tuy nhiên, đọc-sửa-save vẫn có một khoảng thời gian giữa read và write. Một request khác có thể cập nhật document trong khoảng đó. Nếu cần tránh ghi đè thay đổi đồng thời, hãy dùng optimistic concurrency control hoặc thiết kế thao tác update nguyên tử phù hợp.

## 11. Những sai lầm thường gặp

### 11.1 Dùng save với DTO PATCH

DTO PATCH thường chỉ chứa các field client muốn thay đổi. Chuyển DTO thành entity không đầy đủ rồi gọi `save` có thể làm mất các field không được gửi. Hãy tạo partial `Document` và dùng Update API.

### 11.2 Nghĩ field null đồng nghĩa không thay đổi

Khi serialize entity, field null có thể bị bỏ qua hoặc được biểu diễn tùy mapping/converter/configuration. Dù thế nào, `save` vẫn không tự hiểu ý định PATCH của client. Hãy định nghĩa rõ trạng thái field và tạo partial update có chủ đích.

### 11.3 Nghĩ field bị bỏ khỏi JSON update sẽ bị xóa

Với partial `doc`, field không xuất hiện thường được giữ nguyên. Muốn xóa field, dùng script `ctx._source.remove(...)` hoặc cơ chế tương ứng.

### 11.4 Cập nhật một phần tử mảng bằng partial JSON

Gửi một mảng mới cho field mảng có thể thay thế toàn bộ giá trị field đó. Nếu cần cập nhật một phần tử theo khóa, dùng script hoặc thiết kế dữ liệu con thành document độc lập.

### 11.5 Dùng script cho mọi update

Script hữu ích cho logic động, nhưng tăng độ phức tạp và chi phí. Nếu chỉ đặt một vài field thành giá trị mới, partial `doc` thường đơn giản hơn.

### 11.6 Không xử lý version conflict

Khi có concurrent update, request có thể gặp conflict hoặc ghi đè dữ liệu theo thứ tự hoàn tất. Xác định rõ semantics nghiệp vụ và dùng optimistic locking, script update hoặc retry phù hợp.

### 11.7 Nhầm lỗi timeout với update chưa được thực hiện

Client có thể timeout sau khi Elasticsearch đã áp dụng update nhưng response không tới được ứng dụng. Retry thao tác tăng/giảm có thể áp dụng lần thứ hai. Hãy thiết kế idempotency key, version check hoặc logic update phù hợp.

## 12. Cách kiểm tra khi field khác bị mất sau save

Nếu một field biến mất sau khi gọi `save`, hãy kiểm tra:

1. `_source` trước khi ghi để xác nhận field tồn tại.
2. Entity thực tế được truyền vào `save` có chứa field đó không.
3. Mapping converter và custom conversions có bỏ qua hoặc đổi tên field không.
4. Entity có phải projection/DTO chỉ chứa một phần dữ liệu không.
5. Có nhiều request ghi cùng ID và request nào hoàn tất sau cùng không.
6. Có alias trỏ tới nhiều index hoặc ghi nhầm index không.

Đọc document trực tiếp:

```http
GET /products/_doc/product-1001
```

Kiểm tra thao tác update bằng `_update` trên một document thử nghiệm và so sánh `_source` trước/sau. Nếu cần quan sát request, bật log HTTP client trong môi trường phát triển với dữ liệu giả; tránh ghi payload nhạy cảm vào log production.

## 13. Nguyên tắc lựa chọn

- Dùng `save` khi entity đại diện cho toàn bộ document cần ghi.
- Dùng Update API với `doc` khi chỉ cần thay đổi một số field đã biết.
- Dùng script khi cần tính toán hoặc sửa dữ liệu dựa trên `_source` hiện tại.
- Dùng `doc_as_upsert` hoặc `upsert` chỉ khi dữ liệu dùng để tạo document mới cũng hợp lệ.
- Không coi null, field vắng mặt và thao tác xóa là cùng một ý nghĩa.
- Với mảng/nested, không giả định update JSON sẽ merge từng phần tử; dùng script hoặc mô hình hóa riêng khi cần.
- Thiết kế concurrency và retry để tránh lost update hoặc áp dụng thao tác lặp.
- Phân biệt write acknowledgement với thời điểm search nhìn thấy thay đổi sau refresh.
- Dùng DTO PATCH riêng, validate field được phép sửa và chuyển thành partial update tường minh.

## 14. Tổng kết

`save(entity)` trong Spring Data Elasticsearch ghi document theo ID với nội dung được tạo từ entity. Khi document đã tồn tại, thao tác này không tự động lấy document cũ rồi ghép những field còn thiếu trong entity; vì vậy, một entity không đầy đủ có thể làm mất các field không được serialize vào document mới.

Partial update qua Elasticsearch Update API gửi `doc` chỉ chứa field cần đổi hoặc một script thao tác trên `_source` hiện tại. Field không được gửi được giữ nguyên; field null, field bị xóa và field không được đề cập cần có semantics riêng. Với mảng và nested object, cần chủ động cập nhật phần tử bằng script hoặc thay thế field mảng theo chủ đích.

Trong Spring Data Elasticsearch, dùng `ElasticsearchOperations.update(UpdateQuery, IndexCoordinates)` khi cần cập nhật một phần. Dùng `save` cho document đầy đủ, thiết kế concurrency và retry phù hợp, và kiểm tra `_source` thực tế khi điều tra mất dữ liệu. Hiểu đúng khác biệt này giúp tránh lỗi ghi đè, mất field và sai lệch dữ liệu trong các API cập nhật.
