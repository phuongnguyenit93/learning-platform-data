# Chọn id do ứng dụng cấp hoặc id do Elasticsearch sinh

Mỗi document trong Elasticsearch có một định danh `_id` trong phạm vi index. Khi lưu document qua Spring Data Elasticsearch, ứng dụng có thể tự cấp ID trước khi ghi hoặc để Elasticsearch sinh ID khi nhận request. Hai lựa chọn đều hợp lệ, nhưng ảnh hưởng khác nhau đến khả năng retry, chống ghi trùng, liên kết dữ liệu và cách ứng dụng tham chiếu document.

Trong Spring Data Elasticsearch, property được đánh dấu `@Id` ánh xạ tới metadata `_id` của document. Nếu property đã có giá trị, Spring Data dùng giá trị đó làm ID. Nếu ID chưa được cung cấp, thao tác index có thể để Elasticsearch sinh một ID mới; ứng dụng cần lấy ID từ kết quả lưu để dùng cho các lần đọc, cập nhật hoặc xóa sau này.

```text
Ứng dụng tạo entity
        |
        v
   Có giá trị @Id?
       /     \
     Có       Không
      |          |
      v          v
 Dùng ID       Gửi request không có ID
 ứng dụng      |
      |        v
      |    Elasticsearch sinh _id
      |        |
      +--------+
           |
           v
     Lưu document
           |
           v
     Nhận ID đã lưu
```

## 1. `_id` là gì?

`_id` là định danh document do Elasticsearch quản lý trong một index. Nó được dùng để lấy trực tiếp document, cập nhật hoặc xóa document theo ID. Ví dụ một document có thể được trả về như sau:

```json
{
  "_index": "products",
  "_id": "P-100",
  "_version": 1,
  "_source": {
    "sku": "SKU-100",
    "name": "Mechanical Keyboard"
  }
}
```

Trong ví dụ này:

- `_index` là index vật lý đã lưu document.
- `_id` là định danh document trong index đó.
- `_source` là nội dung JSON của document.
- `_version` là metadata version do Elasticsearch quản lý.

`_id` là metadata, không phải một field thông thường trong `_source`. Nếu ứng dụng cần tìm kiếm, lọc, sort hoặc aggregation trên mã nghiệp vụ, hãy lưu mã đó thành field riêng, ví dụ `sku`, bên cạnh `@Id`.

ID duy nhất trong phạm vi một index. Nếu alias trỏ đến nhiều index, cùng một giá trị `_id` có thể xuất hiện ở nhiều index khác nhau. Vì vậy, không nên hiểu `_id` là khóa duy nhất toàn cluster hoặc toàn bộ alias.

## 2. Khai báo ID trong Spring Data Elasticsearch

Spring Data dùng annotation `@Id` để xác định property làm document ID:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // constructors, getters, setters
}
```

Property `id` được dùng làm `_id`. Các property `sku` và `name` là field trong `_source` theo mapping tương ứng.

Ví dụ nếu entity có `id = "P-100"`, document được ghi với `_id` là `P-100`. Nếu `id` là `null` và thao tác được thực hiện qua Spring Data Elasticsearch theo cơ chế hỗ trợ ID tự sinh, Elasticsearch có thể tạo ID mới.

Thông thường nên dùng `String` cho property ID vì Elasticsearch biểu diễn `_id` dưới dạng chuỗi. Ứng dụng cũng có thể dùng kiểu định danh khác nếu converter của phiên bản Spring Data hỗ trợ, nhưng cần kiểm tra cách chuyển đổi và giá trị thực tế được gửi lên cluster.

## 3. Cách 1: ứng dụng tự cấp ID

Khi ứng dụng tự cấp ID, giá trị đã có trước khi gửi request đến Elasticsearch. ID có thể là:

- Mã nghiệp vụ ổn định, ví dụ `orderId`, `customerCode` hoặc `sku`.
- UUID/ULID do ứng dụng tạo.
- ID tổng hợp từ tenant và định danh entity.
- Một định danh khác được tạo bởi hệ thống nguồn.

### Dùng mã nghiệp vụ làm ID

Nếu mỗi sản phẩm có một SKU duy nhất và SKU không thay đổi trong suốt vòng đời sản phẩm, có thể dùng SKU làm `_id`:

```java
ProductDocument product = new ProductDocument();
product.setId("SKU-100");
product.setSku("SKU-100");
product.setName("Mechanical Keyboard");

ProductDocument saved = productRepository.save(product);
```

Document có `_id = "SKU-100"`. Lần sau ứng dụng lưu một entity khác có cùng ID, thao tác index thông thường sẽ ghi vào cùng document đó.

Điều này phù hợp nếu định danh nghiệp vụ thực sự ổn định và duy nhất trong index. Không nên dùng tên sản phẩm, email hoặc thuộc tính có thể thay đổi làm ID nếu việc đổi giá trị sẽ khiến ứng dụng không còn tìm thấy document theo ID cũ.

### Dùng UUID do ứng dụng tạo

Nếu không có khóa nghiệp vụ phù hợp, ứng dụng có thể tạo UUID trước khi lưu:

```java
import java.util.UUID;

ProductDocument product = new ProductDocument();
product.setId(UUID.randomUUID().toString());
product.setSku("SKU-100");
product.setName("Mechanical Keyboard");

ProductDocument saved = productRepository.save(product);
```

ID đã có trước khi gửi request, vì vậy ứng dụng có thể ghi ID vào log, lưu vào hệ thống nguồn hoặc gửi nó cho thành phần khác ngay từ đầu.

UUID ngẫu nhiên tạo ID có xác suất va chạm rất thấp, nhưng mỗi lần gọi `UUID.randomUUID()` sẽ tạo một giá trị mới. Nếu request ghi dữ liệu bị timeout và ứng dụng tạo UUID mới để retry, lần retry có thể tạo một document thứ hai. Muốn retry an toàn, hãy tạo ID một lần ở ranh giới nghiệp vụ rồi giữ lại và dùng lại ID đó cho mọi lần thử của cùng một thao tác.

### Dùng ID tổng hợp cho dữ liệu đa tenant

Nếu nhiều tenant cùng lưu entity có ID cục bộ như `42`, có thể tạo ID tổng hợp:

```java
String documentId = tenantId + ":" + orderId;
```

Ví dụ `tenant-7:42` và `tenant-9:42` trở thành hai ID khác nhau trong cùng index. Có thể dùng cách mã hóa hoặc hash ổn định nếu thành phần ID chứa ký tự không phù hợp hoặc quá dài. Cần chọn một quy tắc nhất quán và giữ nguyên quy tắc đó trong các lần ghi, đọc, cập nhật và xóa.

## 4. Cách 2: để Elasticsearch sinh ID

Elasticsearch có thể tự sinh ID khi nhận thao tác index không chỉ định `_id`. Với REST API, cách phổ biến là dùng `POST /<index>/_doc`:

```http
POST /products/_doc
Content-Type: application/json

{
  "sku": "SKU-200",
  "name": "Wireless Mouse"
}
```

Response thành công chứa ID được tạo:

```json
{
  "_index": "products",
  "_id": "generated-id-from-elasticsearch",
  "_version": 1,
  "result": "created"
}
```

Giá trị `_id` trong ví dụ chỉ là minh họa; ứng dụng phải lấy giá trị thật từ response. Với REST API, endpoint có ID như `PUT /products/_doc/P-200` sử dụng ID do client chỉ định. Endpoint `PUT /products/_create/P-200` hoặc `PUT /products/_doc/P-200?op_type=create` yêu cầu tạo mới và trả conflict nếu ID đã tồn tại.

### Để Spring Data Elasticsearch sinh ID

Với entity có property `@Id`, có thể để ID là `null` khi tạo entity:

```java
ProductDocument product = new ProductDocument();
product.setId(null);
product.setSku("SKU-200");
product.setName("Wireless Mouse");

ProductDocument saved = productRepository.save(product);
String generatedId = saved.getId();
```

Trong Spring Data Elasticsearch, thao tác lưu trả về entity đã lưu và có thể được populate ID do Elasticsearch trả về. Hãy sử dụng entity được trả về từ `save`, đặc biệt với entity bất biến hoặc record, thay vì giả định object truyền vào luôn bị thay đổi tại chỗ. Nên có integration test với đúng phiên bản Spring Data và Elasticsearch của dự án để xác nhận hành vi ID tự sinh của cấu hình đang dùng.

Nếu ứng dụng gọi Elasticsearch Java API Client trực tiếp, response của index request có trường `id`:

```java
IndexResponse response = client.index(request -> request
        .index("products")
        .document(productPayload)
);

String generatedId = response.id();
```

Ở ví dụ này request không gọi `.id(...)`, do đó Elasticsearch sinh ID. Ứng dụng phải lưu `generatedId` nếu cần tham chiếu document về sau.

## 5. So sánh hai cách cấp ID

| Tiêu chí | ID do ứng dụng cấp | ID do Elasticsearch sinh |
|---|---|---|
| Thời điểm biết ID | Biết trước khi gửi request. | Chỉ biết sau khi nhận response thành công. |
| Retry sau timeout | Có thể ghi lại cùng ID để tránh tạo document thứ hai. | Gửi lại request không ID có thể tạo document mới. |
| Idempotency | Dễ thiết kế nếu ID được tạo một lần và tái sử dụng. | Không tự có idempotency khi mỗi lần retry đều tạo ID mới. |
| Tham chiếu từ hệ thống khác | Có thể truyền ID trước khi ghi. | Cần chờ response và lưu ID sinh ra. |
| Phù hợp với khóa nghiệp vụ | Có thể dùng trực tiếp khóa ổn định. | Không phụ thuộc khóa nghiệp vụ. |
| Khả năng ghi trùng | Cùng ID ghi lại cùng document; cần hiểu semantics overwrite/create. | Mỗi lần tạo mới thường có ID khác, nên retry có thể sinh bản sao. |
| Độ phức tạp | Ứng dụng chịu trách nhiệm tạo, quản lý và tránh va chạm ID. | Elasticsearch đảm nhiệm sinh ID; ứng dụng quản lý ID sau khi nhận. |

Không có lựa chọn đúng cho mọi hệ thống. Hãy chọn dựa trên yêu cầu về tính duy nhất, retry, liên kết dữ liệu và khả năng truy xuất.

## 6. `save` là upsert theo ID, không mặc định là insert-only

Một điểm quan trọng khi dùng ID do ứng dụng cấp là hiểu hành vi của thao tác lưu. Repository `save(entity)` của Spring Data Elasticsearch thường thực hiện thao tác index theo ID. Nếu ID chưa tồn tại, document được tạo; nếu ID đã tồn tại, nội dung document được ghi đè theo semantics của index operation.

Ví dụ:

```java
ProductDocument first = new ProductDocument();
first.setId("SKU-100");
first.setSku("SKU-100");
first.setName("Keyboard");
productRepository.save(first);

ProductDocument second = new ProductDocument();
second.setId("SKU-100");
second.setSku("SKU-100");
second.setName("Keyboard Pro");
productRepository.save(second);
```

Lần lưu thứ hai ghi document có cùng `_id`; kết quả là nội dung hiện tại mang tên `Keyboard Pro`. Đây là hành vi hữu ích cho cập nhật theo ID, nhưng không phù hợp nếu nghiệp vụ yêu cầu từ chối mọi bản ghi trùng.

### Khi cần chỉ tạo mới

Nếu phải bảo đảm ID chưa tồn tại, dùng create-only operation. Ví dụ REST API:

```http
PUT /products/_create/SKU-100
Content-Type: application/json

{
  "sku": "SKU-100",
  "name": "Keyboard"
}
```

Nếu ID đã tồn tại, Elasticsearch trả lỗi HTTP `409 Conflict`. Có thể dùng `op_type=create` với Index API tương ứng. Khi dùng Java API Client, có thể cấu hình operation type là `create` cho index request.

Repository `save` không nên được xem là thao tác insert-only. Nếu cần ngữ nghĩa create-only, hãy dùng API hỗ trợ op type `create` hoặc một abstraction cụ thể của phiên bản Spring Data đang dùng, rồi xử lý conflict rõ ràng.

## 7. ID và khả năng retry an toàn

Một tình huống phổ biến: ứng dụng gửi request ghi document, Elasticsearch đã ghi thành công nhưng response bị mất do network timeout. Ứng dụng không biết chắc thao tác đã thành công hay chưa.

### Với ID do Elasticsearch sinh

```text
Ứng dụng                 Elasticsearch
    |                           |
    | POST /products/_doc       |
    |-------------------------->| tạo document ID=A
    |                           |
    |        response mất       |
    |< - - - - - - - - - - - - X
    |
    | retry POST không ID       |
    |-------------------------->| tạo document ID=B
    |<--------------------------| trả ID=B
```

Hai document có thể cùng đại diện cho một sự kiện nghiệp vụ. Elasticsearch không thể tự biết request thứ hai là retry của request đầu vì cả hai đều không có ID hoặc idempotency key chung.

### Với ID do ứng dụng cấp và tái sử dụng

```text
Ứng dụng                 Elasticsearch
    |                           |
    | PUT /products/_doc/P-100  |
    |-------------------------->| tạo/cập nhật P-100
    |                           |
    |        response mất       |
    |< - - - - - - - - - - - - X
    |
    | retry cùng ID P-100      |
    |-------------------------->| ghi lại P-100
    |<--------------------------| trả kết quả P-100
```

Retry cùng ID tránh tạo thêm một document có ID khác. Tuy nhiên, nếu dùng thao tác index thông thường, retry vẫn có thể ghi lại toàn bộ document. Nếu nội dung retry cũ hơn một bản cập nhật mới hơn, nó có thể ghi đè dữ liệu mới. Với dữ liệu cập nhật đồng thời, cần thêm versioning hoặc optimistic concurrency control.

### Các cách thiết kế idempotency

- Tạo ID ổn định từ khóa nghiệp vụ hoặc idempotency key.
- Sinh UUID một lần trước lần ghi đầu tiên, lưu nó ở hệ thống nguồn và dùng lại khi retry.
- Dùng create-only khi muốn request thứ hai nhận conflict nếu document đã tồn tại.
- Lưu trạng thái xử lý của event ở hệ thống nguồn/outbox để consumer có thể phát lại cùng định danh.
- Với cập nhật có thứ tự, lưu source version và kiểm tra version trước khi ghi.

Chỉ dùng UUID ngẫu nhiên không tự bảo đảm idempotency nếu ứng dụng sinh UUID mới cho mỗi lần retry.

## 8. ID, cập nhật đồng thời và optimistic concurrency

ID xác định document cần thao tác; nó không tự giải quyết xung đột khi nhiều request cùng sửa document đó. Nếu hai request cùng ghi một `_id`, thao tác đến sau có thể ghi đè thao tác trước theo semantics thông thường.

Elasticsearch hỗ trợ optimistic concurrency control bằng `_seq_no` và `_primary_term`. Ứng dụng đọc document, giữ hai metadata này và gửi lại khi cập nhật. Nếu document đã thay đổi kể từ lần đọc, thao tác có điều kiện bị từ chối để ứng dụng xử lý xung đột.

Ví dụ request:

```http
PUT /products/_doc/P-100?if_seq_no=12&if_primary_term=3
Content-Type: application/json

{
  "sku": "SKU-100",
  "name": "Keyboard Pro"
}
```

Các giá trị sequence number và primary term chỉ là ví dụ; ứng dụng phải lấy chúng từ response của lần đọc trước đó. Nếu có xung đột, cần đọc lại document và quyết định tính lại thay đổi, retry có giới hạn hoặc trả lỗi cho tầng nghiệp vụ.

ID ứng dụng cấp giúp xác định đích ổn định, còn optimistic concurrency giúp bảo vệ cập nhật khỏi ghi đè thay đổi mới hơn. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 9. ID không thay thế field nghiệp vụ

`_id` có thể dùng để lấy document trực tiếp hoặc query bằng IDs query, nhưng không phải field thông thường để aggregation, sort hoặc phân tích như `keyword`. Nếu ứng dụng cần truy vấn theo SKU, email hoặc mã khách hàng, hãy lưu giá trị đó thành field riêng:

```java
@Document(indexName = "customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field(name = "customer_code", type = FieldType.Keyword)
    private String customerCode;

    @Field(type = FieldType.Keyword)
    private String email;
}
```

Có thể dùng `customerCode` làm `_id` nếu đó là khóa ổn định, đồng thời lưu lại `customer_code` để hỗ trợ truy vấn/aggregation. Việc lưu lặp ID vào `_source` là lựa chọn mô hình dữ liệu; Spring Data không tự biến metadata `_id` thành một field tìm kiếm thông thường.

Tránh dùng dữ liệu cá nhân nhạy cảm như email hoặc số điện thoại làm `_id` nếu không cần thiết. ID thường xuất hiện trong log, URL hoặc trace; dùng định danh opaque như UUID hoặc mã nội bộ sẽ hạn chế việc lộ thông tin và giúp đổi dữ liệu cá nhân mà không phải đổi định danh document.

Elasticsearch giới hạn độ dài `_id` (tối đa 512 byte trong các phiên bản hiện đại). Không nên nhét toàn bộ JSON, tên người dùng dài hoặc chuỗi ghép không giới hạn vào ID. Nếu cần ID tổng hợp, hãy giới hạn độ dài và dùng hash ổn định khi phù hợp.

## 10. Chọn ID trong các tình huống thường gặp

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Đồng bộ sản phẩm từ database có khóa chính ổn định | Dùng khóa nguồn hoặc ID được ánh xạ ổn định. | Reindex/đồng bộ lặp lại cùng entity vào cùng document. |
| Đơn hàng có `orderId` duy nhất | Dùng `orderId` làm ID nếu phạm vi uniqueness phù hợp. | Dễ tham chiếu và retry theo cùng đơn hàng. |
| Log/event cần ghi nhanh, không có khóa nguồn | Có thể để Elasticsearch sinh ID. | Không cần xây dựng ID nghiệp vụ nếu không cần tham chiếu lại. |
| Event phải chống ghi trùng khi consumer retry | Dùng event ID/idempotency key ổn định do nguồn cấp. | Cùng event luôn nhắm đến cùng document. |
| Tài liệu nội bộ không có định danh tự nhiên | Sinh UUID/ULID ở ứng dụng. | Ứng dụng biết ID trước khi ghi và có thể tái sử dụng. |
| Multi-tenant với ID cục bộ có thể trùng | Dùng ID tổng hợp có namespace tenant hoặc khóa toàn cục. | Tránh ghi đè document của tenant khác trong cùng index. |
| Một alias đọc nhiều index lịch sử | Thiết kế ID và truy vấn có xét index; không giả định `_id` duy nhất trên alias. | ID chỉ duy nhất trong từng index. |
| Cần từ chối bản ghi có ID đã tồn tại | Dùng create-only operation. | `save` thông thường có semantics index/upsert. |

## 11. Tích hợp với Spring Data Repository

Một repository đơn giản:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
```

Với ID do ứng dụng cấp:

```java
public ProductDocument createProduct(String sku, String name) {
    ProductDocument document = new ProductDocument();
    document.setId(sku);
    document.setSku(sku);
    document.setName(name);

    return productRepository.save(document);
}
```

Với ID do Elasticsearch sinh:

```java
public ProductDocument createProduct(String sku, String name) {
    ProductDocument document = new ProductDocument();
    document.setId(null);
    document.setSku(sku);
    document.setName(name);

    ProductDocument saved = productRepository.save(document);
    return saved;
}
```

Trong trường hợp thứ hai, tầng gọi cần giữ `saved.getId()` nếu muốn đọc, cập nhật hoặc xóa document sau này. Với API service, có thể trả ID trong response hoặc lưu ID vào database nghiệp vụ. Nếu ID chỉ nằm trong object tạm thời và bị bỏ đi, ứng dụng sẽ khó tham chiếu document đã tạo.

### Dùng ElasticsearchOperations

`ElasticsearchOperations` cung cấp API thao tác document ở mức thấp hơn repository, nhưng vẫn giữ mapping/converter của Spring Data:

```java
@Service
public class ProductDocumentService {

    private final ElasticsearchOperations operations;

    public ProductDocumentService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductDocument save(ProductDocument document) {
        return operations.save(document);
    }
}
```

Kết quả trả về là entity đã lưu; dùng nó để lấy ID được populate nếu server sinh ID. Nếu cần create-only, custom routing, concurrency condition hoặc các tham số Index API chuyên biệt, hãy dùng API tương ứng mà phiên bản Spring Data cung cấp hoặc gọi Elasticsearch Java API Client trực tiếp.

### Dùng Java API Client khi cần kiểm soát request

Ví dụ chỉ định ID do ứng dụng cấp:

```java
IndexResponse response = client.index(request -> request
        .index("products")
        .id("P-100")
        .document(productPayload)
);
```

Ví dụ để Elasticsearch sinh ID:

```java
IndexResponse response = client.index(request -> request
        .index("products")
        .document(productPayload)
);

String id = response.id();
```

Nếu dùng Java API Client trực tiếp, ứng dụng chịu trách nhiệm chuyển đổi payload, chọn index/alias, xử lý response và giữ ID. Không nên tạo một client mới cho mỗi thao tác; hãy inject client do Spring Boot quản lý.

## 12. Những điểm cần kiểm thử

ID strategy ảnh hưởng đến các luồng quan trọng, vì vậy integration test nên kiểm tra:

1. Khi ID được cấp, document được ghi vào đúng `_id`.
2. Khi ID là `null`, thao tác hỗ trợ auto-generated ID trả về một ID không rỗng.
3. Entity trả về từ `save` có ID có thể dùng cho `findById` và `deleteById`.
4. Lưu lại cùng ID có hành vi ghi đè/upsert như thiết kế.
5. Create-only với ID đã tồn tại trả conflict và không ghi đè document cũ.
6. Retry cùng ID không tạo thêm document ID khác.
7. Retry với ID tự sinh có thể tạo bản ghi khác, nếu ứng dụng không dùng idempotency key.
8. Khi alias trỏ nhiều index, kiểm tra phạm vi uniqueness và hành vi query theo đúng thiết kế.

Ví dụ kiểm thử hành vi ID tự sinh ở mức ý tưởng:

```java
@Test
void saveWithoutIdShouldReturnGeneratedId() {
    ProductDocument draft = new ProductDocument();
    draft.setId(null);
    draft.setSku("SKU-200");
    draft.setName("Wireless Mouse");

    ProductDocument saved = productRepository.save(draft);

    assertThat(saved.getId()).isNotBlank();
    assertThat(productRepository.findById(saved.getId())).isPresent();
}
```

Đây là ví dụ minh họa; cần cấu hình Elasticsearch integration test và mapping/index trước khi chạy. Nếu dùng entity immutable hoặc record, kiểm tra entity trả về từ repository thay vì object draft ban đầu.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi lần retry lại xuất hiện một document mới | ID do Elasticsearch sinh lại ở mỗi request. | Tạo ID ổn định hoặc idempotency key ở ứng dụng và tái sử dụng khi retry. |
| Lưu document mới ghi đè document cũ | Hai entity dùng cùng `_id` và `save` dùng index/upsert semantics. | Kiểm tra quy tắc tạo ID; dùng create-only nếu cần từ chối trùng. |
| Không đọc được document sau khi save | Ứng dụng không lưu ID Elasticsearch trả về hoặc dùng nhầm index/alias. | Dùng entity trả về từ `save` và lưu `getId()`. |
| Tìm kiếm theo `_id` bằng aggregation không hoạt động | `_id` là metadata, không phải field aggregation thông thường. | Lưu ID nghiệp vụ thành field `keyword` riêng. |
| Hai tenant ghi đè dữ liệu của nhau | Dùng cùng ID cục bộ trong cùng index. | Thêm tenant namespace vào ID hoặc tạo ID toàn cục. |
| Alias đọc trả về document trùng ID | Cùng `_id` tồn tại ở nhiều index mà alias đang trỏ tới. | Xem lại chiến lược index/alias và định danh, hoặc giới hạn index truy vấn. |
| Đổi email khiến không tìm thấy document theo ID | Email mutable được dùng làm `_id`. | Dùng ID ổn định; lưu email thành field riêng. |
| Entity đầu vào vẫn có ID null sau save | Code đọc object đầu vào thay vì entity trả về hoặc behavior khác theo phiên bản/entity type. | Dùng giá trị trả về và xác minh bằng integration test. |

## 14. Quy trình ra quyết định

Trước khi chọn cách cấp ID, hãy xác định:

1. Document có khóa nghiệp vụ ổn định không?
2. Các hệ thống khác có cần biết ID trước khi ghi không?
3. Request có thể retry sau timeout hoặc được phát lại từ queue không?
4. Retry phải cập nhật cùng document hay phải tạo một sự kiện mới?
5. Có yêu cầu từ chối document trùng thay vì ghi đè không?
6. ID có duy nhất trong phạm vi index, tenant hay toàn hệ thống?
7. Có cần tìm kiếm, sort hoặc aggregation theo mã nghiệp vụ không?
8. Ứng dụng có lưu lại ID được sinh từ Elasticsearch không?

Nếu cần retry an toàn hoặc liên kết dữ liệu giữa nhiều hệ thống, ID ổn định do ứng dụng cấp thường dễ kiểm soát hơn. Nếu document độc lập, không cần biết ID trước khi ghi và duplicate được xử lý theo cách khác, ID tự sinh của Elasticsearch có thể đơn giản hơn.

## 15. Những điểm cần nhớ

- `@Id` ánh xạ property Java tới metadata `_id` của document.
- ID do ứng dụng cấp có thể là khóa nghiệp vụ ổn định, UUID/ULID hoặc ID tổng hợp.
- Khi không cung cấp ID, Elasticsearch có thể sinh ID; hãy lấy ID từ entity trả về hoặc response của client.
- Dùng ID ổn định và tái sử dụng khi retry để tránh tạo document thứ hai cho cùng một thao tác.
- UUID mới cho mỗi lần retry vẫn có thể tạo bản ghi trùng; UUID chỉ hữu ích cho idempotency khi được tạo một lần và lưu lại.
- `save` thường có semantics index/upsert theo ID; không mặc định là insert-only.
- Dùng create-only operation khi phải từ chối ID đã tồn tại.
- `_id` duy nhất trong từng index, không đảm bảo duy nhất trên alias trỏ nhiều index.
- Lưu mã nghiệp vụ thành field riêng nếu cần filter, sort hoặc aggregation; `_id` không thay thế field `keyword`.
- ID strategy và optimistic concurrency là hai vấn đề riêng: một xác định document, một bảo vệ cập nhật đồng thời.

Chọn đúng chiến lược ID giúp Spring Data Elasticsearch xử lý ghi mới, cập nhật và retry theo đúng nghiệp vụ. Hãy quyết định ID dựa trên tính ổn định của định danh, nhu cầu tham chiếu và cách hệ thống phục hồi khi request thất bại; sau đó xác minh hành vi bằng integration test trên đúng phiên bản Spring Data Elasticsearch và cluster đang triển khai.
