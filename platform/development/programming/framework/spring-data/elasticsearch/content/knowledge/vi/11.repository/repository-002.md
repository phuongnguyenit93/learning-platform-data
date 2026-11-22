# Khai báo kiểu Document và kiểu khóa định danh

Trong Spring Data Elasticsearch, một lớp Java cần được mô tả là document được lưu trong Elasticsearch và một thuộc tính cần được xác định làm khóa định danh của document. Hai annotation quan trọng cho việc này là `@Document` và `@Id`.

`@Document` đánh dấu lớp domain được ánh xạ tới một index Elasticsearch. Annotation này cung cấp metadata như tên index và chính sách tạo index. `@Id` đánh dấu thuộc tính Java được ánh xạ tới metadata `_id` của document. Khi kết hợp với repository, kiểu của thuộc tính ID cần thống nhất với tham số ID trong khai báo repository, ví dụ `ElasticsearchRepository<Product, String>` nếu entity sử dụng `String` làm ID.

Hai annotation này không làm Elasticsearch trở thành cơ sở dữ liệu quan hệ. Index là nơi lưu và tìm kiếm document; `_id` là định danh duy nhất của document trong index; còn các thuộc tính nghiệp vụ như SKU, mã khách hàng hoặc số đơn hàng có thể được lưu thành các field riêng trong `_source` để tìm kiếm, lọc hoặc aggregation theo mapping phù hợp.

## 1. Từ lớp Java đến document Elasticsearch

Giả sử ứng dụng quản lý sản phẩm. Một sản phẩm có mã định danh, mã SKU, tên và giá. Ở phía Java, ta mô hình hóa dữ liệu bằng lớp `Product`:

```java
public class Product {
    private String id;
    private String sku;
    private String name;
    private Double price;
}
```

Elasticsearch lưu document dưới dạng JSON trong một index, ví dụ index `products`:

```json
{
  "sku": "SKU-1001",
  "name": "Bàn phím cơ",
  "price": 185000
}
```

Document còn có metadata do Elasticsearch quản lý, trong đó `_index` xác định index chứa document và `_id` xác định document trong index đó. Khi đọc document, response có thể có dạng:

```json
{
  "_index": "products",
  "_id": "product-1001",
  "_source": {
    "sku": "SKU-1001",
    "name": "Bàn phím cơ",
    "price": 185000
  }
}
```

`_id` là metadata định danh của Elasticsearch. Nó không đồng nghĩa với một field JSON có tên `id` trong `_source`. Spring Data có thể ánh xạ thuộc tính được đánh dấu `@Id` vào `_id`, còn các field nghiệp vụ khác được ánh xạ vào nội dung document.

Mối liên hệ tổng quát:

```mermaid
flowchart TD
    A[Java class Product] --> B[@Document indexName=products]
    A --> C[@Id property]
    B --> D[Index products]
    C --> E[Elasticsearch metadata _id]
    A --> F[Other mapped properties]
    F --> G[Document _source]
    D --> H[Stored document]
    E --> H
    G --> H
```

## 2. Khai báo `@Document`

`@Document` thuộc package `org.springframework.data.elasticsearch.annotations`. Annotation này đặt trên lớp Java đại diện cho document và cho Spring Data biết index đích khi lưu hoặc truy vấn entity.

Ví dụ cơ bản:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String sku;
    private String name;
    private Double price;
}
```

Trong ví dụ, entity `Product` được ánh xạ tới index `products`. Khi Spring Data thực hiện thao tác lưu hoặc tìm kiếm theo kiểu `Product`, metadata của `@Document` được dùng để xác định index tương ứng.

### 2.1 `indexName`

`indexName` là tên index hoặc alias mà entity sử dụng. Tên index Elasticsearch phải tuân theo quy tắc đặt tên của Elasticsearch; thông thường nên dùng chữ thường, dấu gạch ngang và quy ước rõ ràng về phiên bản index.

Ví dụ:

```java
@Document(indexName = "products")
public class Product {
    // fields
}
```

Với một index có version:

```java
@Document(indexName = "products-v2")
public class Product {
    // fields
}
```

Trong hệ thống cần migration, ứng dụng thường nên tham chiếu một alias ổn định như `products` thay vì gắn cứng vào tên vật lý `products-v1` hoặc `products-v2`. Alias có thể được chuyển từ index cũ sang index mới khi migration hoàn tất, trong khi code repository vẫn sử dụng cùng tên logic.

Ví dụ:

```java
@Document(indexName = "products")
public class Product {
    // fields
}
```

Ở cluster, alias `products` có thể trỏ tới index vật lý `products-v2`. Khi chuyển alias sang index khác, repository vẫn truy cập thông qua `products`.

### 2.2 `createIndex`

`@Document` có thuộc tính `createIndex` để kiểm soát việc Spring Data có tạo index khi khởi tạo mapping/repository hay không. Giá trị mặc định trong các phiên bản Spring Data Elasticsearch hiện đại thường là `true`.

Ví dụ:

```java
@Document(
    indexName = "products",
    createIndex = false
)
public class Product {
    // fields
}
```

`createIndex = false` phù hợp khi index được tạo và quản lý bởi một quy trình triển khai riêng, chẳng hạn index template, migration hoặc công cụ quản trị hạ tầng. Khi đó, ứng dụng không nên tự tạo index trong lúc khởi động.

Nếu dùng `createIndex = true`, Spring Data có thể tạo index và mapping dựa trên metadata entity khi index chưa tồn tại, tùy cấu hình và phiên bản. Điều này thuận tiện trong môi trường phát triển hoặc ứng dụng nhỏ. Với production, các index có analyzer tùy chỉnh, settings đặc biệt, alias và quy trình versioning thường nên được quản lý bằng migration có kiểm soát.

`createIndex` không có nghĩa Spring Data sẽ tự động thay đổi mọi mapping hiện có để khớp với annotation mới. Nếu index đã tồn tại với kiểu field không tương thích, việc sửa entity không tự migrate dữ liệu hay đổi kiểu field trên cluster.

### 2.3 `@Document` không phải `@Entity` của JPA

Spring Data Elasticsearch dùng `@Document`, trong khi JPA dùng `@Entity` và `@Table`. Hai hệ thống có mô hình lưu trữ khác nhau:

| Annotation | Hệ thống | Ý nghĩa |
|---|---|---|
| `@Document` | Spring Data Elasticsearch | Ánh xạ lớp Java tới Elasticsearch index |
| `@Entity` | JPA | Đánh dấu lớp persistent entity trong mô hình quan hệ |
| `@Table` | JPA | Chỉ định bảng quan hệ |
| `@Id` | Spring Data | Đánh dấu thuộc tính ID cho mapping Spring Data |

Không nên thêm annotation JPA chỉ vì tên của nó quen thuộc. Nếu lớp cần được lưu ở cả relational database và Elasticsearch, cần thiết kế mapping cho từng persistence technology một cách rõ ràng và tránh nhầm lẫn annotation hoặc lifecycle.

## 3. Khai báo `@Id`

`@Id` dùng để đánh dấu thuộc tính Java ánh xạ tới định danh `_id` của document. Annotation Spring Data nằm trong package `org.springframework.data.annotation.Id`.

```java
import org.springframework.data.annotation.Id;

public class Product {

    @Id
    private String id;

    private String name;
}
```

Khi ghi document, giá trị của `id` được dùng làm `_id`. Khi đọc document, Spring Data lấy `_id` và gán lại cho thuộc tính được đánh dấu `@Id`.

### 3.1 Tên thuộc tính Java không bắt buộc là `id`

Thuộc tính ID có thể có tên mang ý nghĩa nghiệp vụ hơn:

```java
@Id
private String productId;
```

Spring Data nhận biết định danh dựa trên annotation, không phụ thuộc tên thuộc tính. Giá trị `productId` vẫn được ánh xạ tới metadata `_id` của Elasticsearch.

Tuy nhiên, nếu không dùng `@Id`, không nên mặc định rằng một thuộc tính tên `id` hoặc `productId` tự động trở thành `_id`. Hãy đánh dấu tường minh để mapping không phụ thuộc vào suy luận tên field.

### 3.2 `_id` khác field nghiệp vụ trong `_source`

Giả sử entity có:

```java
@Id
private String id;

private String sku;
```

Một document có thể có metadata:

```json
{
  "_id": "product-1001",
  "_source": {
    "sku": "SKU-1001"
  }
}
```

Ở đây:

- `_id` là định danh Elasticsearch.
- `sku` là field nghiệp vụ trong `_source`.
- Hai giá trị có thể giống nhau nhưng không bắt buộc phải giống.

Nếu ứng dụng cần tìm kiếm, lọc, sort hoặc aggregation theo SKU, hãy lưu SKU thành một field riêng và khai báo mapping phù hợp, thường là `keyword` khi cần so khớp chính xác. Không nên coi `_id` như một field nghiệp vụ thông thường để thực hiện mọi kiểu query hoặc aggregation.

### 3.3 Một document chỉ có một `_id`

Mỗi document trong một index có một định danh `_id`. Một entity có thể có nhiều thuộc tính định danh nghiệp vụ, nhưng chỉ một thuộc tính được dùng làm ID của document trong mapping Spring Data.

Ví dụ một sản phẩm có `id`, `sku`, `barcode` và `externalReference`. Chỉ `id` được đánh dấu `@Id`; các giá trị còn lại là field thông thường trong `_source` nếu cần lưu và truy vấn.

```java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String barcode;

    @Field(type = FieldType.Keyword)
    private String externalReference;
}
```

Không đánh dấu nhiều thuộc tính bằng `@Id` trong cùng một entity. Nếu cần một khóa tổng hợp, hãy tạo một giá trị định danh duy nhất ở phía ứng dụng, ví dụ ghép các thành phần theo quy tắc có escaping và separator rõ ràng, hoặc dùng UUID.

## 4. Chọn kiểu dữ liệu cho ID

Trong nhiều ứng dụng, `String` là lựa chọn đơn giản và linh hoạt cho ID của Elasticsearch. Nó có thể chứa UUID, mã định danh do ứng dụng tạo hoặc một chuỗi ổn định khác.

Ví dụ:

```java
@Id
private String id;
```

Elasticsearch biểu diễn `_id` dưới dạng chuỗi ở API. Vì vậy, dùng `String` giúp tránh phụ thuộc vào kiểu số của một nguồn dữ liệu cụ thể và thuận tiện khi tích hợp với hệ thống khác.

### 4.1 ID do ứng dụng cấp

Ứng dụng có thể tự tạo ID trước khi lưu:

```java
Product product = new Product(
    "product-1001",
    "SKU-1001",
    "Bàn phím cơ",
    185000.0
);

repository.save(product);
```

Khi ID đã xác định, thao tác ghi có thể nhắm tới đúng document. Nếu lưu lại cùng ID, thao tác index thường ghi document dưới cùng định danh và thay thế nội dung document theo semantics của thao tác được sử dụng.

ID do ứng dụng cấp phù hợp khi cần:

- Đồng bộ dữ liệu từ hệ thống nguồn.
- Retry thao tác ghi theo cách idempotent hơn.
- Tham chiếu document từ API hoặc event.
- Đảm bảo một thực thể nghiệp vụ luôn ánh xạ tới cùng document.
- Tạo index đích/reindex mà vẫn giữ định danh cũ.

Nếu ID là một business key như SKU, cần xem xét tính ổn định và duy nhất của nó. Nếu SKU có thể đổi, dùng SKU làm `_id` có thể khiến thao tác đổi SKU trở thành một document mới và cần xóa document cũ. Một ID nội bộ ổn định thường phù hợp hơn, còn SKU được lưu thành field riêng.

### 4.2 ID do Elasticsearch tạo

Elasticsearch có thể tạo `_id` tự sinh khi thao tác index không cung cấp ID. Cách này hữu ích khi ứng dụng không cần xác định trước ID và chỉ cần lưu document mới.

Tuy nhiên, với nghiệp vụ cần retry, đồng bộ hoặc chống tạo trùng, ID tự sinh có thể gây khó khăn: nếu server đã lưu document nhưng response bị mất, lần retry có thể tạo thêm document mới với ID khác. Với ID do ứng dụng cấp, retry cùng ID thường dễ kiểm soát hơn.

Hành vi cụ thể khi ID null còn phụ thuộc API ghi và phiên bản Spring Data Elasticsearch. Hãy xác nhận cách repository/operations đang sử dụng xử lý ID trống, và nếu cần ID trả về từ Elasticsearch, hãy dùng kết quả của thao tác ghi theo đúng API thay vì giả định object đầu vào luôn được cập nhật giống nhau ở mọi phiên bản.

### 4.3 UUID làm ID

UUID thường được dùng khi cần định danh duy nhất không phụ thuộc vào database trung tâm:

```java
import java.util.UUID;

String id = UUID.randomUUID().toString();
```

UUID dạng chuỗi phù hợp với `_id`. Nếu ứng dụng dùng UUID, hãy thống nhất dạng biểu diễn (chữ thường/chữ hoa, có dấu gạch ngang hay không) để tránh cùng một giá trị logic được tạo thành hai chuỗi khác nhau.

### 4.4 ID số và kiểu repository

Có thể gặp domain model dùng kiểu số làm ID. Dù `_id` ở Elasticsearch được biểu diễn dưới dạng chuỗi, Spring Data có thể chuyển đổi ID qua conversion service theo kiểu được hỗ trợ. Dù vậy, nếu dùng kiểu ID khác `String`, cần xác nhận converter và hành vi đọc/ghi của phiên bản đang sử dụng.

Điều quan trọng là kiểu ID trong entity và kiểu ID trong repository phải khớp nhau. Ví dụ:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, Long> {
}
```

chỉ hợp lý khi thuộc tính được đánh dấu `@Id` của `Product` có kiểu `Long` và conversion tương ứng hoạt động đúng. Không khai báo repository dùng `String` trong khi entity dùng `Long` chỉ vì `_id` ở Elasticsearch là chuỗi; hãy chọn một kiểu domain nhất quán.

## 5. Khai báo Repository với kiểu ID tương ứng

Spring Data Elasticsearch cung cấp `ElasticsearchRepository<T, ID>`. Tham số đầu là kiểu entity; tham số thứ hai là kiểu của thuộc tính ID.

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Với khai báo này:

- `Product` là entity được quản lý.
- `String` là kiểu định danh.
- `findById` nhận `String`.
- `deleteById` nhận `String`.
- `save` nhận và trả về `Product` theo contract repository.

Ví dụ sử dụng:

```java
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product save(Product product) {
        return repository.save(product);
    }

    public Optional<Product> findById(String id) {
        return repository.findById(id);
    }

    public void delete(String id) {
        repository.deleteById(id);
    }
}
```

Nếu repository khai báo sai kiểu ID, code có thể không biên dịch khi gọi các method với kiểu tham số không phù hợp, hoặc dẫn đến conversion không mong muốn nếu có ép kiểu thủ công. Hãy để generic type phản ánh đúng kiểu domain.

## 6. Ví dụ entity hoàn chỉnh

Một entity thường kết hợp `@Document`, `@Id` và `@Field` để mô tả index, định danh và các field còn lại.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(
    indexName = "products",
    createIndex = false
)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    protected Product() {
    }

    public Product(String id, String sku, String name, Double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public Double getPrice() {
        return price;
    }
}
```

Ở đây `createIndex = false` thể hiện index được quản lý bên ngoài ứng dụng. Nếu muốn Spring Data tạo index từ metadata trong môi trường phát triển, có thể bỏ thuộc tính này hoặc đặt `createIndex = true` theo nhu cầu.

Mapping dự kiến:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "sku": { "type": "keyword" },
      "name": { "type": "text" },
      "price": { "type": "double" }
    }
  }
}
```

Lưu ý rằng `id` được dùng làm `_id` metadata. Mapping trên không cần khai báo một property `id` thông thường trong `_source` nếu ứng dụng không có nhu cầu lưu thêm một field ID riêng.

## 7. Phân biệt ID Elasticsearch và khóa nghiệp vụ

Một ứng dụng có thể có nhiều khái niệm khóa:

- Elasticsearch document ID (`_id`): định danh document trong index.
- Primary key của cơ sở dữ liệu quan hệ: định danh row trong bảng nguồn.
- Business key: mã nghiệp vụ như SKU, số hợp đồng, mã đơn hàng.
- External reference: ID do hệ thống khác cấp.

Các giá trị này có thể giống nhau, nhưng không bắt buộc. Chọn một business key làm `_id` chỉ hợp lý nếu nó duy nhất trong phạm vi index, ổn định và phù hợp với vòng đời document.

Ví dụ:

```java
@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String orderNumber;

    @Field(type = FieldType.Keyword)
    private String customerId;
}
```

`id` có thể là UUID nội bộ của document; `orderNumber` là số đơn hàng hiển thị cho người dùng; `customerId` là tham chiếu khách hàng. Nếu cần lọc theo số đơn hàng hoặc khách hàng, các thuộc tính nghiệp vụ này phải có mapping phù hợp trong `_source`.

### 7.1 ID có phạm vi duy nhất theo index

Elasticsearch yêu cầu `_id` duy nhất trong phạm vi một index. Hai index khác nhau có thể có document cùng `_id` mà không xung đột.

Ví dụ:

```text
products-v1 / _id = product-1001
products-v2 / _id = product-1001
```

Điều này hữu ích khi reindex hoặc chuyển đổi phiên bản index: index mới có thể giữ nguyên `_id` của document nguồn. Tuy nhiên, nếu ứng dụng truy vấn qua alias trỏ tới nhiều index, cần hiểu cách kết quả được kết hợp và tránh tạo ID trùng không mong muốn giữa các index trong cùng alias.

### 7.2 Không dùng ID như cơ chế quan hệ tự động

Elasticsearch không tự tạo foreign key hoặc cascade relationship giống một relational database chỉ vì hai document có field chứa cùng ID. Nếu document đơn hàng có `customerId`, ứng dụng phải tự quản lý cách lấy thông tin khách hàng, denormalize dữ liệu hoặc thực hiện query phù hợp.

`@Id` chỉ xác định document hiện tại. Nó không định nghĩa quan hệ giữa các entity khác.

## 8. `@Document` và index alias/versioning

Trong production, index thường được version hóa để thay đổi mapping an toàn. Ứng dụng dùng một alias ổn định:

```text
products          -> alias ổn định
products-v1       -> index vật lý cũ
products-v2       -> index vật lý mới
```

Entity giữ:

```java
@Document(indexName = "products")
public class Product {
    // fields
}
```

Khi tạo `products-v2`, hệ thống có thể reindex dữ liệu từ `products-v1`, xác nhận mapping/query, rồi chuyển alias `products` sang index mới. Repository không cần biết tên index vật lý.

Điều này tách tên logic trong ứng dụng khỏi tên index vật lý. Nó cũng giúp rollback có thể thực hiện bằng cách chuyển alias trở lại, nhưng chỉ an toàn nếu đã xử lý các write phát sinh sau cutover. Alias không tự đồng bộ dữ liệu giữa các index.

Nếu alias trỏ tới nhiều index để phục vụ đọc, hãy cấu hình write index rõ ràng khi ứng dụng ghi. Tránh để thao tác ghi qua alias có nhiều đích mà không xác định index nhận write.

## 9. Tạo index từ metadata entity

Spring Data Elasticsearch có thể sử dụng metadata từ `@Document` và `@Field` để tạo mapping. Với `ElasticsearchOperations`, có thể lấy `IndexOperations` tương ứng với entity:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndexIfMissing() {
        IndexOperations indexOps = operations.indexOps(Product.class);

        if (!indexOps.exists()) {
            indexOps.create();
            indexOps.putMapping(indexOps.createMapping());
        }
    }
}
```

Đây là ví dụ cơ bản minh họa cách dùng metadata entity để tạo index và mapping. Trong thực tế, cần xác định rõ ai quản lý settings, analyzer, alias, template và migration. Với index đã tồn tại, `createIndexIfMissing()` không chuyển đổi mapping cũ để khớp với class mới.

### 9.1 Kiểm tra mapping thực tế

Sau khi tạo index, dùng API:

```http
GET /products/_mapping
GET /products/_settings
```

Mapping thực tế trên cluster quyết định cách Elasticsearch index và query dữ liệu. Đừng chỉ dựa vào annotation trong code khi điều tra lỗi kiểu dữ liệu hoặc kết quả tìm kiếm.

### 9.2 Tên index phải khớp giữa entity và hạ tầng

Nếu entity khai báo `indexName = "products"` nhưng hạ tầng chỉ tạo index `product`, repository có thể không tìm thấy index đích hoặc ghi vào một tên khác nếu quyền và cấu hình cho phép tạo tự động. Cần thống nhất tên index/alias giữa ứng dụng, migration và cấu hình cluster.

## 10. Những nhầm lẫn thường gặp

### 10.1 Dùng nhầm `jakarta.persistence.Id`

Trong Spring Data Elasticsearch, nên dùng:

```java
import org.springframework.data.annotation.Id;
```

Không tự thay bằng `jakarta.persistence.Id` chỉ vì dự án cũng có JPA. Hai annotation thuộc hai persistence model khác nhau; mapping Elasticsearch cần nhận đúng metadata Spring Data Elasticsearch sử dụng.

### 10.2 Cho rằng field tên `id` tự động là `_id`

Hãy dùng `@Id` để đánh dấu rõ thuộc tính định danh. Tên thuộc tính Java có thể là `id`, `productId` hoặc tên khác; annotation mới là dấu hiệu mapping.

### 10.3 Cho rằng `_id` là field bình thường trong `_source`

`_id` là metadata của Elasticsearch. Nếu cần một field ID có thể truy vấn, sort hoặc aggregation theo mapping thông thường, hãy lưu một thuộc tính riêng trong `_source`.

### 10.4 Dùng SKU làm `_id` dù SKU có thể thay đổi

Nếu SKU thay đổi, document có thể được ghi dưới một ID mới và document cũ cần được xử lý riêng. Hãy chọn ID ổn định theo vòng đời thực thể và lưu SKU như field nghiệp vụ nếu cần.

### 10.5 Khai báo sai generic ID của repository

Nếu entity dùng `String` nhưng repository khai báo `Long`, API repository không phản ánh đúng domain model. Kiểu generic thứ hai phải khớp với kiểu thuộc tính `@Id`.

### 10.6 Nghĩ `createIndex = true` luôn cập nhật mapping

Thuộc tính này liên quan đến việc tạo index khi chưa có theo metadata. Nó không cho phép thay đổi tùy ý kiểu field đã lập chỉ mục và không phải migration engine.

### 10.7 Dùng tên index vật lý trong code ở mọi nơi

Gắn cứng `products-v1` vào entity làm code phụ thuộc phiên bản index. Alias ổn định giúp tách biệt tên logic và index vật lý khi migration.

## 11. Cách chẩn đoán khi repository không tìm thấy document

Khi `findById` trả về `Optional.empty()` hoặc thao tác save không vào đúng index, hãy kiểm tra theo thứ tự:

1. Kiểm tra `@Document(indexName = ...)` của entity.
2. Kiểm tra repository generic ID type có khớp thuộc tính `@Id` không.
3. Xác nhận giá trị ID truyền vào chính xác, gồm cả chữ hoa/thường và khoảng trắng nếu có.
4. Kiểm tra index/alias đang trỏ tới index vật lý nào.
5. Dùng `GET /index/_doc/<id>` để kiểm tra document trực tiếp.
6. Dùng `GET /_cat/indices?v` hoặc `GET /_alias` để xác nhận index/alias tồn tại.
7. Kiểm tra quyền truy cập, endpoint và cấu hình client.
8. Kiểm tra dữ liệu `_source` và mapping nếu entity đọc được nhưng field bị thiếu hoặc sai kiểu.

Ví dụ:

```http
GET /products/_doc/product-1001
GET /_alias/products
GET /_cat/indices/products*?v
```

Nếu API trực tiếp tìm thấy document nhưng repository không tìm thấy, hãy kiểm tra index name mà entity thực sự sử dụng, kiểu ID và mapping converter. Nếu cả API trực tiếp cũng không thấy, kiểm tra document đã được ghi vào index nào và ID nào.

## 12. Nguyên tắc lựa chọn

Khi khai báo document và định danh, hãy quyết định rõ:

- Lớp Java nào đại diện cho document và index/alias logic nào chứa nó.
- Index được tạo bởi Spring Data hay được quản lý bằng migration/hạ tầng.
- Thuộc tính nào là `_id`, kiểu Java của ID là gì và repository generic có khớp không.
- ID do ứng dụng cấp hay Elasticsearch tạo; nghiệp vụ có yêu cầu idempotency hay đồng bộ không.
- Business key nào cần lưu thành field riêng để tìm kiếm/lọc.
- Index có versioning/alias để thay đổi mapping an toàn không.
- Mapping thực tế trên cluster có đồng nhất với metadata entity không.

Một cấu hình rõ ràng giúp code repository dễ hiểu, thao tác lưu/xóa/tìm theo ID có semantics ổn định và quy trình migration index không bị gắn chặt với tên vật lý.

## 13. Tổng kết

`@Document` khai báo lớp Java được ánh xạ tới một Elasticsearch index hoặc alias thông qua `indexName`. Thuộc tính `createIndex` điều khiển việc tạo index theo metadata khi index chưa tồn tại, nhưng không phải công cụ tự động migrate mapping. `@Id` đánh dấu thuộc tính dùng làm metadata `_id` của document; tên thuộc tính Java không bắt buộc là `id` và `_id` không đồng nghĩa với một field nghiệp vụ trong `_source`.

Khi dùng `ElasticsearchRepository<T, ID>`, kiểu `ID` cần thống nhất với kiểu thuộc tính được đánh dấu `@Id`. Nên chọn ID ổn định, cân nhắc ID do ứng dụng cấp khi cần retry và đồng bộ, đồng thời lưu business key như SKU thành field riêng nếu cần tìm kiếm hoặc lọc. Trong production, alias ổn định và quy trình quản lý index có version giúp tách code ứng dụng khỏi tên index vật lý và hỗ trợ migration an toàn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch Reference — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch Reference — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Elasticsearch — Document metadata fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-fields.html)
- [Elasticsearch — Index aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html)
