# `@Id` và ánh xạ định danh tài liệu

Trong Elasticsearch, mỗi document có một định danh riêng gọi là **document ID**, được lưu trong metadata field `_id`. Spring Data Elasticsearch cung cấp annotation `@Id` để ánh xạ một thuộc tính Java vào định danh này.

`@Id` có vai trò quan trọng khi lưu, đọc, cập nhật và xóa document. Nó giúp Spring Data biết giá trị nào của entity đại diện cho document ID để gọi đúng API Elasticsearch.

Cần phân biệt ba khái niệm:

- **Document ID (`_id`)**: định danh metadata do Elasticsearch quản lý cho mỗi document trong một index.
- **Thuộc tính ID trong entity**: thuộc tính Java được đánh dấu bằng `@Id`, dùng để trao đổi giá trị document ID với Spring Data.
- **Business ID**: mã nghiệp vụ như SKU, mã khách hàng hoặc mã đơn hàng. Business ID có thể trùng với document ID theo thiết kế, nhưng không bắt buộc.

## 1. `_id` trong Elasticsearch là gì?

Mỗi document được lưu trong một index cần có định danh để Elasticsearch có thể xác định document khi đọc, ghi đè, cập nhật hoặc xóa.

Ví dụ, một document sản phẩm có thể được lưu vào index `products` với ID là `product-1001`:

~~~http
PUT /products/_doc/product-1001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-1001",
  "price": 129.99
}
~~~

Trong request này:

- `products` là index.
- `_doc` là endpoint document API.
- `product-1001` là document ID.
- Phần JSON là nội dung document, thường được lưu trong `_source`.

Document có thể được đọc trực tiếp bằng ID:

~~~http
GET /products/_doc/product-1001
~~~

Hoặc xóa bằng ID:

~~~http
DELETE /products/_doc/product-1001
~~~

`_id` là metadata field do Elasticsearch quản lý, không phải một field thông thường cần khai báo trong mapping `properties`. Mapping có thể mô tả các thuộc tính dữ liệu như `name`, `sku`, `price`, nhưng không khai báo `_id` như một field nghiệp vụ.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "sku": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

Document ID được Elasticsearch sử dụng để định danh document. Nó không tự động trở thành một thuộc tính có thể dùng cho mọi thao tác như sort hoặc aggregation. Nếu cần lọc, thống kê hoặc sắp xếp theo một mã nghiệp vụ, hãy lưu mã đó thành một field phù hợp, thường là `keyword`.

## 2. `@Id` trong Spring Data Elasticsearch

Spring Data Elasticsearch sử dụng annotation `@Id` để đánh dấu thuộc tính Java ánh xạ tới document ID `_id`.

Annotation cần import từ package của Spring Data:

~~~java
import org.springframework.data.annotation.Id;
~~~

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    public Product(String id, String name, String sku, Double price) {
        this.id = id;
        this.name = name;
        this.sku = sku;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    // Các getter và setter còn lại
}
~~~

Trong ví dụ:

- `@Document(indexName = "products")` xác định index mà entity đại diện.
- `@Id` đánh dấu `id` là document ID.
- `@Field` mô tả mapping của các thuộc tính dữ liệu như tên, SKU và giá.
- `String` là kiểu Java phổ biến để biểu diễn document ID vì Elasticsearch nhận ID dưới dạng chuỗi.

Spring Data cũng có quy ước nhận diện thuộc tính tên `id` khi entity không khai báo annotation `@Id`. Tuy nhiên, dùng `@Id` làm ý định ánh xạ rõ ràng hơn, đặc biệt khi tên thuộc tính Java là `productId`, `documentKey` hoặc một tên khác.

### Chọn đúng annotation

`@Id` trong ví dụ là:

~~~java
import org.springframework.data.annotation.Id;
~~~

Không nên nhầm với annotation cùng tên trong JPA:

~~~java
import jakarta.persistence.Id;
~~~

`jakarta.persistence.Id` phục vụ ánh xạ khóa chính của JPA. Khi mô tả entity Spring Data Elasticsearch, hãy dùng annotation ID thuộc Spring Data để đảm bảo mapping metadata được hiểu đúng theo cơ chế của Spring Data Elasticsearch.

## 3. Thuộc tính `@Id` khác gì với field thông thường?

`@Id` ánh xạ giá trị thuộc tính Java vào metadata document ID `_id`. Nó không phải cách khai báo một field `keyword` trong `_source`.

Ví dụ entity:

~~~java
@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String customerCode;

    @Field(type = FieldType.Text)
    private String fullName;
}
~~~

Có thể hiểu:

| Thuộc tính | Vai trò |
|---|---|
| `id` | Document ID, được ánh xạ tới metadata `_id` |
| `customerCode` | Mã nghiệp vụ, là field dữ liệu kiểu `keyword` |
| `fullName` | Dữ liệu tên khách hàng, là field `text` |

Nếu cần tìm kiếm, lọc, sort hoặc aggregation theo `customerCode`, hãy truy vấn field `customerCode`. Không nên dựa vào `_id` như một field dữ liệu thông thường.

`_id` có thể được dùng trong các thao tác định danh hoặc truy vấn IDs. Nhưng Elasticsearch giới hạn các thao tác trên metadata field này; chẳng hạn không dùng `_id` cho aggregation hoặc sort như một field `keyword` thông thường.

## 4. Kiểu dữ liệu ID trong entity và Repository

Document ID của Elasticsearch được biểu diễn dưới dạng chuỗi. Trong Spring Data Elasticsearch, `String` là lựa chọn đơn giản và phổ biến nhất.

Repository cần khai báo kiểu ID tương ứng với thuộc tính ID của entity:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Tham số generic thứ nhất là entity; tham số thứ hai là kiểu Java của ID.

| Entity | Repository |
|---|---|
| `Product` có `String id` | `ElasticsearchRepository<Product, String>` |
| `Customer` có `Long id` | `ElasticsearchRepository<Customer, Long>` |
| `Order` có `UUID id` | `ElasticsearchRepository<Order, UUID>` nếu kiểu đó được mapping/conversion hỗ trợ trong phiên bản đang dùng |

Dù dùng kiểu Java nào, giá trị cuối cùng của document ID vẫn được chuyển đổi thành chuỗi để giao tiếp với Elasticsearch. Cần bảo đảm kiểu ID trong repository nhất quán với thuộc tính ID của entity và conversion mà Spring Data hỗ trợ.

Trong ứng dụng mới, dùng `String` hoặc UUID được chuyển đổi rõ ràng sang chuỗi thường giúp mô hình định danh dễ hiểu và dễ tích hợp.

## 5. Tự gán ID từ ứng dụng

Ứng dụng có thể tạo ID trước khi lưu document. Cách này hữu ích khi hệ thống đã có mã định danh nghiệp vụ ổn định hoặc cần kiểm soát ID để retry một thao tác.

Ví dụ tạo ID bằng UUID:

~~~java
import java.util.UUID;

Product product = new Product(
        UUID.randomUUID().toString(),
        "Mechanical Keyboard",
        "KB-1001",
        129.99
);

Product saved = productRepository.save(product);
~~~

Khi lưu entity, Spring Data dùng giá trị `id` làm document ID.

Một số trường hợp nên tự gán ID:

- Dữ liệu có ID ổn định từ hệ thống nguồn.
- Muốn dùng cùng một ID khi đồng bộ lại dữ liệu.
- Cần tránh tạo document trùng khi một request được gửi lại.
- Muốn có thể tham chiếu document ngay từ trước khi lưu.

### Dùng business key làm document ID

Ví dụ SKU là duy nhất và ổn định trong phạm vi index:

~~~java
Product product = new Product(
        "KB-1001",
        "Mechanical Keyboard",
        "KB-1001",
        129.99
);
~~~

Trong thiết kế này, document ID và SKU có cùng giá trị nhưng vẫn có hai vai trò:

- `id` dùng để định danh document.
- `sku` là field nghiệp vụ để tìm kiếm và lọc.

Giữ `sku` thành field `keyword` giúp ứng dụng truy vấn, thống kê hoặc hiển thị SKU mà không phụ thuộc vào metadata `_id`.

Không nên dùng business key làm document ID nếu giá trị có thể thay đổi thường xuyên. Thay đổi ID đồng nghĩa với việc document được định danh dưới một khóa khác; cần xử lý việc tạo document mới và xóa hoặc thay thế document cũ.

## 6. Để Elasticsearch tạo ID

Elasticsearch có thể tự sinh document ID khi request index không cung cấp ID. Đây là lựa chọn phù hợp khi ứng dụng không cần tự kiểm soát định danh trước khi lưu.

Ví dụ entity chưa có ID:

~~~java
Product product = new Product(
        null,
        "Mechanical Keyboard",
        "KB-1001",
        129.99
);

Product saved = productRepository.save(product);
~~~

Khi ID không được cung cấp, thao tác lưu có thể để Elasticsearch sinh ID. Spring Data Elasticsearch nhận ID từ phản hồi lưu và ánh xạ vào entity theo cơ chế của phiên bản đang sử dụng.

Nếu cần dùng ID sau khi lưu, hãy lấy từ entity được trả về hoặc kiểm tra trạng thái entity sau thao tác save:

~~~java
Product saved = productRepository.save(product);
String generatedId = saved.getId();
~~~

Không nên giả định ID đã tồn tại trước khi gọi save. Nếu nghiệp vụ cần một ID ổn định để retry hoặc tham chiếu trước khi lưu, hãy tạo ID ở tầng ứng dụng.

## 7. Dùng ID với ElasticsearchRepository

Khi đã khai báo ID đúng, các phương thức CRUD của repository làm việc dựa trên document ID.

~~~java
import java.util.Optional;

Optional<Product> product = productRepository.findById("KB-1001");

boolean exists = productRepository.existsById("KB-1001");

productRepository.deleteById("KB-1001");
~~~

Các thao tác tương ứng:

| Phương thức | Ý nghĩa |
|---|---|
| `save(entity)` | Lưu document theo ID của entity; nếu ID đã tồn tại trong index, document cùng ID được ghi lại |
| `findById(id)` | Đọc document theo ID |
| `existsById(id)` | Kiểm tra document có tồn tại theo ID |
| `deleteById(id)` | Xóa document theo ID |
| `findAllById(ids)` | Đọc nhiều document theo danh sách ID |

Ví dụ service:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductService {

    private final ProductRepository productRepository;

    public Product create(Product product) {
        return productRepository.save(product);
    }

    public Product getRequired(String id) {
        return productRepository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));
    }

    public void delete(String id) {
        productRepository.deleteById(id);
    }
}
~~~

Kiểu ID trong các lời gọi repository phải phù hợp với generic ID đã khai báo. Với repository `ProductRepository` ở trên, ID được truyền vào là `String`.

## 8. Dùng ID với ElasticsearchOperations

Ngoài repository, Spring Data cung cấp `ElasticsearchOperations` để thao tác trực tiếp với entity và document.

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductDocumentService {

    private final ElasticsearchOperations operations;

    public Product findById(String id) {
        return operations.get(id, Product.class);
    }

    public void deleteById(String id) {
        operations.delete(id, Product.class);
    }
}
~~~

`operations.get(id, Product.class)` đọc document theo ID và chuyển đổi kết quả thành entity `Product`.

`operations.delete(id, Product.class)` xóa document theo ID trong index tương ứng với metadata của entity.

Repository phù hợp với các thao tác CRUD và truy vấn theo abstraction repository. `ElasticsearchOperations` phù hợp khi cần điều khiển chi tiết hơn quá trình tìm kiếm, mapping hoặc thao tác document.

## 9. Truy vấn document theo ID bằng Elasticsearch API

Elasticsearch cung cấp API lấy document trực tiếp:

~~~http
GET /products/_doc/KB-1001
~~~

Khi cần tìm nhiều document theo ID trong một truy vấn search, có thể sử dụng `ids` query:

~~~json
{
  "query": {
    "ids": {
      "values": ["KB-1001", "KB-1002", "KB-1003"]
    }
  }
}
~~~

`ids` query kiểm tra document ID. Nó không tìm theo giá trị của field `sku` trong `_source`.

Nếu muốn tìm theo SKU, hãy dùng `term` trên field `sku`:

~~~json
{
  "query": {
    "term": {
      "sku": "KB-1001"
    }
  }
}
~~~

Hai truy vấn có thể trả về cùng một document nếu ứng dụng đã chọn SKU làm document ID và đồng thời lưu SKU thành field. Tuy nhiên, ý nghĩa của hai truy vấn khác nhau:

- `ids`: tìm theo metadata document ID.
- `term`: tìm theo giá trị field trong mapping.

## 10. Điều gì xảy ra khi lưu nhiều lần cùng một ID?

Trong Elasticsearch, document ID xác định document trong index. Khi gửi thao tác index với cùng một ID, document hiện tại được thay thế bằng nội dung document mới theo semantics của Index API.

Ví dụ lần đầu lưu:

~~~http
PUT /products/_doc/KB-1001
Content-Type: application/json

{
  "name": "Mechanical Keyboard",
  "sku": "KB-1001",
  "price": 129.99
}
~~~

Lần tiếp theo dùng cùng ID:

~~~http
PUT /products/_doc/KB-1001
Content-Type: application/json

{
  "name": "Mechanical Keyboard Pro",
  "sku": "KB-1001",
  "price": 159.99
}
~~~

Document tại ID `KB-1001` được ghi lại với nội dung mới. Những field không có trong document mới có thể không còn trong `_source` sau thao tác index.

Vì vậy:

- Chỉ dùng `save` khi muốn lưu trạng thái đầy đủ của entity.
- Nếu cần cập nhật một vài field mà giữ nguyên phần còn lại, hãy dùng API update/partial update phù hợp.
- Bảo đảm ID ổn định và không vô tình dùng chung ID cho hai thực thể khác nhau.

Document ID chỉ duy nhất trong phạm vi một index. Hai index khác nhau có thể có document cùng ID mà không xung đột.

## 11. Những lưu ý về giới hạn của `_id`

`_id` rất hữu ích cho định danh, nhưng không nên dùng nó thay thế mọi field nghiệp vụ.

### Không dùng `_id` cho aggregation hoặc sorting

Elasticsearch hỗ trợ truy vấn document theo ID, nhưng `_id` không được thiết kế để làm field phân tích thông thường. Không nên dựa vào `_id` để:

- Nhóm document bằng terms aggregation.
- Sắp xếp kết quả theo giá trị ID.
- Thực hiện các phép phân tích cần doc values.

Nếu cần các thao tác trên, hãy lưu một field nghiệp vụ riêng với kiểu dữ liệu phù hợp, thường là `keyword`.

### Không thay đổi ID tùy tiện

Nếu một entity đã được lưu với ID `A`, việc thay ID thành `B` rồi save sẽ tạo hoặc ghi document dưới ID `B`. Document cũ dưới ID `A` không tự biến mất chỉ vì entity đã đổi ID.

Muốn đổi ID, ứng dụng phải xác định rõ quy trình: đọc document cũ, tạo document mới với ID mới, xác nhận lưu thành công rồi xóa document cũ nếu cần.

### ID phải ổn định và duy nhất trong index

Nếu hai entity khác nhau dùng cùng ID trong một index, thao tác lưu sau có thể ghi đè document trước. Hãy chọn chiến lược định danh phù hợp:

- UUID do ứng dụng sinh.
- ID ổn định từ hệ thống nguồn.
- Business key chỉ khi tính duy nhất và tính ổn định được bảo đảm.

### Phân biệt document ID với khóa chính quan hệ

Elasticsearch không phải cơ sở dữ liệu quan hệ. `@Id` không tạo foreign key, không bảo đảm quan hệ tham chiếu giữa các document và không cung cấp transaction nhiều document giống cơ sở dữ liệu quan hệ.

Nếu một document chứa ID của document khác, đó là dữ liệu tham chiếu do ứng dụng quản lý. Việc kiểm tra tính tồn tại, đồng bộ và xóa dây chuyền cần được thiết kế riêng.

## 12. Quy trình thiết kế ID cho entity

Khi thiết kế một entity Spring Data Elasticsearch, có thể thực hiện theo các bước:

1. Xác định document có cần ID ổn định do ứng dụng cấp hay có thể dùng ID tự sinh.
2. Chọn thuộc tính Java đại diện cho ID và đánh dấu bằng `@Id`.
3. Chọn kiểu Java phù hợp, thường là `String`.
4. Khai báo generic ID của `ElasticsearchRepository` trùng với kiểu thuộc tính.
5. Xác định business key có cần được lưu thành field riêng để tìm kiếm, lọc hoặc aggregation hay không.
6. Kiểm tra hành vi save nhiều lần cùng ID và quy trình đổi ID.
7. Kiểm tra đọc, tồn tại và xóa theo ID trên index thực tế.

Bảng quyết định nhanh:

| Nhu cầu | Chiến lược |
|---|---|
| Cần ID trước khi lưu | Ứng dụng sinh UUID hoặc ID ổn định |
| Muốn Elasticsearch tự sinh ID | Để ID null khi tạo document và lấy ID sau save |
| Cần retry không tạo document mới | Dùng ID ổn định, xác định trước |
| Cần tìm theo mã nghiệp vụ | Lưu thêm business key kiểu `keyword` |
| Cần sort/aggregation theo mã | Dùng field `keyword` riêng |
| Cần đổi mã định danh | Thực hiện quy trình tạo document mới và xử lý document cũ |

## Kết luận

`@Id` đánh dấu thuộc tính Java ánh xạ tới document ID `_id` của Elasticsearch. Spring Data sử dụng giá trị này cho các thao tác lưu, đọc, kiểm tra tồn tại và xóa document. Document ID là metadata định danh, còn business key là dữ liệu nghiệp vụ có thể cần được lưu thành field riêng. Hãy chọn ID ổn định, khai báo kiểu ID nhất quán giữa entity và repository, và chỉ dùng `_id` cho mục đích định danh document.
