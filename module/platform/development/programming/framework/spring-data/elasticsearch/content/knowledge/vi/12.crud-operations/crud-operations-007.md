# `deleteById`, `delete` và `deleteAll`

Spring Data Elasticsearch cung cấp các phương thức repository để xóa document theo ID, theo entity hoặc xóa toàn bộ dữ liệu trong phạm vi repository. Những method này có tên gần giống nhau nhưng phạm vi tác động khác nhau. Chọn sai method có thể khiến ứng dụng xóa nhiều document hơn dự kiến hoặc nhầm lẫn giữa việc xóa document với xóa index.

Bài học này giải thích cách dùng `deleteById`, `delete`, `deleteAll` và các biến thể liên quan; cách Spring Data xác định index và document cần xóa; ý nghĩa của kết quả khi ID không tồn tại; ảnh hưởng của refresh; và cách thực hiện xóa theo điều kiện bằng `ElasticsearchOperations`.

## 1. Xóa dữ liệu trong Elasticsearch có những phạm vi nào?

Trong Elasticsearch, cần phân biệt ít nhất ba thao tác:

1. **Xóa một document:** xóa tài liệu theo `_id` trong một index.
2. **Xóa nhiều document:** xóa một tập document theo danh sách ID hoặc theo query.
3. **Xóa index:** xóa toàn bộ index cùng mapping, settings và dữ liệu của index đó.

Repository CRUD chủ yếu làm việc với document. Ví dụ `deleteAll()` của repository xóa document trong phạm vi index mà repository quản lý; nó không tương đương với API xóa index của Elasticsearch.

```text
ProductRepository
      |
      +-- deleteById(id) --------> Xóa một document theo _id
      |
      +-- delete(entity) --------> Xóa document theo ID của entity
      |
      +-- deleteAll(entities) ---> Xóa các entity được truyền vào
      |
      +-- deleteAll() -----------> Xóa toàn bộ document trong index đích

IndexOperations.delete() -------> Xóa cả index, mapping và settings
```

## 2. Repository mẫu

Giả sử ứng dụng quản lý sản phẩm bằng entity `Product`:

```java
package com.example.catalog.domain;

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
    private String category;

    public Product() {
    }

    public Product(String id, String name, String category) {
        this.id = id;
        this.name = name;
        this.category = category;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }
}
```

Repository:

```java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

`@Document(indexName = "products")` xác định index mặc định của entity. `@Id` đánh dấu thuộc tính được dùng làm document ID. Repository có thể kế thừa các method CRUD chuẩn từ Spring Data.

## 3. `deleteById`: xóa một document theo ID

`deleteById(ID id)` nhận document ID và yêu cầu xóa document tương ứng trong index mà repository quản lý.

```java
productRepository.deleteById("p-100");
```

Về mặt khái niệm, thao tác tương ứng với lệnh Elasticsearch:

```http
DELETE products/_doc/p-100
```

Spring Data lấy index từ metadata của entity hoặc cấu hình repository, rồi gửi thao tác xóa tới Elasticsearch. Ứng dụng không cần tự ghép URL REST nếu đang dùng repository abstraction.

### 3.1. Không cần tải entity trước khi xóa

Nếu đã biết ID, `deleteById` là lựa chọn trực tiếp:

```java
public void removeProduct(String id) {
    productRepository.deleteById(id);
}
```

Không cần gọi `findById` chỉ để lấy entity rồi mới xóa. Làm như vậy tạo thêm một request đọc và có thể phát sinh tình huống document thay đổi giữa lúc đọc và lúc xóa.

### 3.2. ID không tồn tại

Theo contract repository CRUD của Spring Data, `deleteById` không yêu cầu phải có document tương ứng; nếu không tìm thấy entity thì thao tác thường được bỏ qua một cách im lặng. Ở tầng Elasticsearch, delete response có thể thể hiện kết quả `not_found` thay vì `deleted`.

Do đó, không nên dùng việc `deleteById` không ném exception để kết luận rằng document đã tồn tại và bị xóa. Nếu API cần phản hồi rõ “đã xóa” hay “không tìm thấy”, cần thiết kế cách kiểm tra kết quả phù hợp.

Ví dụ kiểm tra trước:

```java
public boolean deleteIfExists(String id) {
    if (!productRepository.existsById(id)) {
        return false;
    }

    productRepository.deleteById(id);
    return true;
}
```

Đoạn code này minh họa cách tạo phản hồi đơn giản, nhưng phép kiểm tra và phép xóa là hai request riêng biệt. Trong môi trường có nhiều tiến trình cập nhật đồng thời, document có thể bị xóa sau bước `existsById` hoặc thay đổi trước khi thao tác xóa hoàn tất. Nếu cần biết chính xác kết quả của một lệnh xóa duy nhất, hãy dùng API cấp thấp hơn có trả về delete result và xử lý theo phiên bản client đang sử dụng.

### 3.3. ID phải đúng với index và routing

ID chỉ xác định document trong phạm vi index. Hai index khác nhau có thể có document cùng `_id` mà không liên quan đến nhau.

Nếu ứng dụng dùng custom routing khi ghi document, thao tác xóa cũng cần routing tương ứng. Cùng một ID nhưng routing sai có thể khiến Elasticsearch không tìm thấy document tại shard được chỉ định. Hãy bảo đảm cách tạo, đọc và xóa document dùng cùng quy tắc routing.

## 4. `delete(entity)`: xóa theo ID của entity

`delete(T entity)` nhận một object Java và xóa document tương ứng dựa trên định danh của entity. Spring Data đọc giá trị từ thuộc tính được đánh dấu `@Id` để xác định document cần xóa.

```java
Product product = productRepository.findById("p-100")
        .orElseThrow(() -> new IllegalArgumentException("Product not found"));

productRepository.delete(product);
```

Về mặt khái niệm, thao tác vẫn xóa document theo `_id` trong index `products`. Nó không so sánh toàn bộ thuộc tính `name`, `category` để tìm document giống object.

### 4.1. Entity cần có ID hợp lệ

Vì Spring Data cần biết document nào cần xóa, entity truyền vào phải có ID hợp lệ. Ví dụ:

```java
Product product = new Product("p-100", null, null);
productRepository.delete(product);
```

Nếu mapping và phiên bản Spring Data cho phép lấy ID từ object chỉ có ID, các thuộc tính khác không cần được nạp chỉ để thực hiện xóa. Tuy nhiên, trong mã nghiệp vụ, nên dùng object có nguồn gốc rõ ràng và tránh tạo entity rỗng nếu điều đó làm người đọc hiểu nhầm rằng toàn bộ entity được so sánh.

Không truyền entity chưa có ID:

```java
Product product = new Product(null, "Keyboard", "accessories");
productRepository.delete(product);
```

Một entity không có ID không xác định được document mục tiêu. Tùy phiên bản và đường đi mapping, Spring Data có thể từ chối thao tác do ID null hoặc không thể tạo request xóa hợp lệ.

### 4.2. `delete(entity)` không phải xóa theo nội dung object

Giả sử hai document có cùng tên nhưng ID khác nhau:

```json
{"_id": "p-100", "name": "Keyboard", "category": "accessories"}
{"_id": "p-200", "name": "Keyboard", "category": "accessories"}
```

Gọi `delete` với entity có ID `p-100` chỉ nhắm tới document `p-100`. Document `p-200` vẫn tồn tại.

Nếu mục tiêu là xóa mọi document có `category = accessories`, cần dùng query-based delete, không dùng `delete(entity)`.

## 5. `deleteAll(Iterable)`: xóa một tập entity được chỉ định

Repository CRUD có biến thể nhận danh sách entity:

```java
List<Product> products = List.of(
        new Product("p-100", "Keyboard", "accessories"),
        new Product("p-200", "Mouse", "accessories")
);

productRepository.deleteAll(products);
```

Phương thức này xóa những entity được truyền vào dựa trên ID của từng entity. Nó không có nghĩa là xóa toàn bộ document trong index.

Hãy bảo đảm danh sách chỉ chứa entity có ID đúng và thuộc index mà repository đang quản lý. Với tập dữ liệu lớn, cân nhắc chi phí request và cách triển khai bulk phù hợp với phiên bản Spring Data Elasticsearch/client.

## 6. `deleteAllById`: xóa một tập document theo ID

Các phiên bản Spring Data hiện đại có contract `deleteAllById(Iterable<? extends ID> ids)` trong repository CRUD hierarchy. Khi được cung cấp bởi interface repository của phiên bản dự án, method này xóa những document có ID trong danh sách:

```java
productRepository.deleteAllById(List.of("p-100", "p-200", "p-300"));
```

Đây là lựa chọn phù hợp khi ứng dụng có danh sách ID nhưng không cần tải entity tương ứng. Hãy kiểm tra `ElasticsearchRepository` và các interface cha của đúng release train đang dùng để xác nhận method có sẵn.

Nếu phiên bản đang dùng chưa có `deleteAllById`, có thể lặp qua danh sách và gọi `deleteById`, hoặc dùng API bulk/delete phù hợp. Với số lượng ID lớn, không nên gửi một request riêng cho mỗi ID nếu có phương án bulk hiệu quả hơn.

## 7. `deleteAll()`: xóa toàn bộ document trong phạm vi repository

`deleteAll()` là phương thức có phạm vi tác động lớn nhất trong nhóm repository CRUD:

```java
productRepository.deleteAll();
```

Trong Spring Data Elasticsearch, thao tác này được thực hiện trên index mà repository đang quản lý và xóa các document trong phạm vi đó. Việc triển khai thường dựa trên delete-by-query với query khớp tất cả document.

Lệnh Elasticsearch tương ứng về mặt ý tưởng:

```http
POST products/_delete_by_query
{
  "query": {
    "match_all": {}
  }
}
```

`deleteAll()` không xóa cấu trúc index. Index `products`, mapping, settings và aliases vẫn tồn tại sau khi các document bị xóa.

### 7.1. Cẩn thận khi nhiều entity dùng chung một index

Elasticsearch hiện đại không dùng document type để cô lập entity như các phiên bản Elasticsearch rất cũ. Nếu nhiều entity class cùng trỏ tới một index, `deleteAll()` có thể xóa tất cả document trong index đó, kể cả document được ghi từ entity khác.

Ví dụ:

```java
@Document(indexName = "catalog")
public class Product { ... }

@Document(indexName = "catalog")
public class Category { ... }
```

Nếu `ProductRepository` gọi `deleteAll()` trên index `catalog`, không nên giả định thao tác chỉ xóa những document được tạo từ class `Product`. Query xóa toàn index không có bộ lọc theo Java class tự động.

Vì vậy, chỉ dùng `deleteAll()` khi chắc chắn toàn bộ dữ liệu trong index đích thuộc phạm vi cần xóa. Nếu index được dùng chung, hãy dùng query có điều kiện rõ ràng hoặc tách index theo ranh giới dữ liệu.

### 7.2. `deleteAll()` khác với `IndexOperations.delete()`

Hai method có phạm vi hoàn toàn khác nhau:

| Method | Tác động | Index còn tồn tại? |
|---|---|---:|
| `repository.deleteAll()` | Xóa document trong phạm vi index của repository | Có |
| `repository.deleteAll(entities)` | Xóa các document có ID trong iterable | Có |
| `indexOperations.delete()` | Xóa index cùng dữ liệu, mapping và settings | Không |

Ví dụ xóa index bằng `IndexOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexAdminService {

    private final ElasticsearchOperations operations;

    public ProductIndexAdminService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean deleteProductsIndex() {
        IndexOperations indexOperations = operations.indexOps(
                IndexCoordinates.of("products"));
        return indexOperations.delete();
    }
}
```

Đây là thao tác quản trị index, cần được kiểm soát quyền và không nên đặt sau một endpoint CRUD thông thường. Sau khi index bị xóa, ứng dụng cần tạo lại index/mapping trước khi tiếp tục ghi dữ liệu.

## 8. So sánh các method xóa

| Method | Đầu vào | Phạm vi xóa | Cần tải entity? |
|---|---|---|---:|
| `deleteById(id)` | Một ID | Một document | Không |
| `delete(entity)` | Một entity có ID | Một document theo ID entity | Không nhất thiết |
| `deleteAll(entities)` | Iterable entity | Các document theo ID trong iterable | Có object/ID |
| `deleteAllById(ids)` | Iterable ID | Các document theo ID trong iterable | Không |
| `deleteAll()` | Không có | Toàn bộ document trong index đích | Không |
| `IndexOperations.delete()` | Không có | Cả index | Không |

Chọn method dựa trên tập dữ liệu cần xóa. Nếu chỉ biết ID, dùng method theo ID. Nếu đã có entity và muốn xóa đúng document đó, dùng `delete(entity)`. Nếu muốn xóa theo điều kiện nghiệp vụ, dùng query-based delete. Chỉ dùng `deleteAll()` khi toàn bộ document trong index thực sự cần được loại bỏ.

## 9. Xóa document theo điều kiện bằng `ElasticsearchOperations`

Các method repository CRUD không đủ linh hoạt cho mọi trường hợp. Nếu cần xóa tất cả document thỏa một điều kiện, có thể dùng `ElasticsearchOperations.delete(Query, Class, IndexCoordinates)`.

Ví dụ xóa sản phẩm thuộc danh mục `discontinued`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.stereotype.Service;

@Service
public class ProductCleanupService {

    private final ElasticsearchOperations operations;

    public ProductCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void deleteDiscontinuedProducts() {
        Criteria criteria = new Criteria("category").is("discontinued");
        CriteriaQuery query = new CriteriaQuery(criteria);

        operations.delete(
                query,
                Product.class,
                IndexCoordinates.of("products"));
    }
}
```

`CriteriaQuery` biểu diễn điều kiện xóa, còn `IndexCoordinates` xác định index mục tiêu. API và kiểu query builder có thể khác giữa các release train; hãy đối chiếu Javadoc của phiên bản Spring Data Elasticsearch trong dự án.

Trước khi thực hiện xóa theo query, nên chạy query tìm kiếm tương ứng để xem tập document sẽ bị ảnh hưởng. Với thao tác có phạm vi lớn, hãy ghi log điều kiện, index đích, số lượng dự kiến và người/tiến trình yêu cầu.

### 9.1. Xóa theo query và Delete By Query API

Delete By Query tìm các document khớp query rồi xóa chúng. Đây là thao tác khác với xóa một document theo ID. Nó có thể tiêu tốn tài nguyên khi tập kết quả lớn và chịu ảnh hưởng của refresh, conflict hoặc việc dữ liệu tiếp tục được ghi trong lúc thao tác chạy.

Ở REST API, ví dụ xóa sản phẩm có trạng thái `INACTIVE`:

```http
POST products/_delete_by_query
{
  "query": {
    "term": {
      "status": "INACTIVE"
    }
  }
}
```

Không gửi `match_all` nếu mục tiêu chỉ là xóa một nhóm dữ liệu. Kiểm tra query trước bằng `_search` để xác nhận phạm vi.

## 10. Xóa trong service và REST API

Một service có thể bao bọc thao tác repository và quy định cách ứng dụng phản hồi:

```java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public void deleteById(String id) {
        repository.deleteById(id);
    }

    public void delete(Product product) {
        repository.delete(product);
    }

    public void deleteAll() {
        repository.deleteAll();
    }
}
```

Controller có thể công khai endpoint xóa một sản phẩm:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        service.deleteById(id);
        return ResponseEntity.noContent().build();
    }
}
```

Ví dụ trả `204 No Content` sau khi gọi `deleteById` theo semantics idempotent của endpoint. Nếu API cần trả `404 Not Found` khi document không tồn tại, service phải có chiến lược kiểm tra hoặc dùng delete result từ API cấp thấp hơn. Phép kiểm tra `existsById` trước khi xóa có thể gặp race condition nếu dữ liệu thay đổi đồng thời.

Không nên công khai `deleteAll()` như endpoint CRUD thông thường. Nếu có chức năng xóa hàng loạt, cần xác thực, phân quyền, xác nhận phạm vi, giới hạn số lượng và audit rõ ràng.

## 11. Refresh và khả năng nhìn thấy kết quả xóa

Elasticsearch là hệ thống tìm kiếm near-real-time. Một thao tác delete có thể đã được chấp nhận nhưng kết quả tìm kiếm chưa phản ánh ngay cho tới khi shard được refresh.

Điều này tạo ra khác biệt giữa:

- Kết quả của lệnh delete: Elasticsearch đã xử lý yêu cầu xóa.
- Kết quả của search: document chỉ biến mất khỏi kết quả tìm kiếm sau khi refresh làm thay đổi khả năng nhìn thấy của searcher.

Trong kiểm thử, nếu xóa document rồi gọi `_search` ngay, có thể cần refresh index trước khi xác nhận kết quả:

```http
POST products/_refresh
```

Spring Data Elasticsearch có `RefreshPolicy` để điều khiển hành vi refresh cho các thao tác ghi/xóa theo cấu hình của entity hoặc operations, tùy phiên bản. Những lựa chọn phổ biến của Elasticsearch là:

| Refresh policy | Ý nghĩa khái quát |
|---|---|
| `NONE` | Không yêu cầu refresh đặc biệt; search thấy thay đổi ở lần refresh tiếp theo |
| `IMMEDIATE` | Yêu cầu refresh ngay để thay đổi nhanh chóng có thể được tìm thấy |
| `WAIT_UNTIL` | Chờ tới lần refresh kế tiếp thay vì chủ động ép refresh ngay |

Ví dụ khai báo policy trên entity trong các phiên bản Spring Data hỗ trợ:

```java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

@Document(
    indexName = "products",
    refreshPolicy = RefreshPolicy.WAIT_UNTIL
)
public class Product {
    // Fields
}
```

Hãy kiểm tra package và API của `RefreshPolicy` trong phiên bản đang dùng. Không nên đặt `IMMEDIATE` cho mọi thao tác production chỉ để search thấy thay đổi ngay; refresh thường xuyên có thể làm giảm hiệu năng indexing. Chỉ chọn policy theo yêu cầu nhất quán của nghiệp vụ.

## 12. Bulk delete, hiệu năng và giới hạn

Xóa từng ID có thể tạo nhiều request nếu ứng dụng xử lý một danh sách lớn:

```java
for (String id : ids) {
    productRepository.deleteById(id);
}
```

Với tập ID lớn, cân nhắc `deleteAllById`, `deleteAll(entities)`, Bulk API hoặc Delete By Query tùy cấu trúc dữ liệu và phiên bản. Những cách này có thể giảm số lần round-trip, nhưng không có nghĩa thao tác miễn phí: Elasticsearch vẫn phải xử lý delete operation, cập nhật segment metadata và thực hiện merge khi cần.

Một số điểm cần cân nhắc:

- Chia lô với kích thước hợp lý thay vì gửi một danh sách cực lớn.
- Theo dõi số document bị xóa, số conflict và lỗi từng item nếu dùng bulk.
- Tránh chạy nhiều delete-by-query lớn đồng thời trên cùng index.
- Xác định rõ chính sách xử lý khi có document được cập nhật trong lúc delete-by-query đang chạy.
- Không refresh sau từng document nếu không có yêu cầu nghiệp vụ cụ thể.
- Dùng quyền xóa tối thiểu cần thiết cho tài khoản ứng dụng.

Nếu mục tiêu là loại bỏ toàn bộ index cũ theo vòng đời dữ liệu, xóa index hoặc dùng ILM/data stream lifecycle có thể phù hợp hơn xóa từng document. Đây là quyết định quản trị dữ liệu, không chỉ là thay một repository method bằng method khác.

## 13. Quyền truy cập và bảo vệ thao tác xóa

Elasticsearch phân biệt quyền xóa document với quyền xóa index. Một tài khoản ứng dụng có thể được cấp quyền xóa document trên index cụ thể mà không có quyền xóa index hoặc quản trị cluster.

Trong ứng dụng thực tế:

- Cấp quyền `delete` hoặc quyền phù hợp với API xóa mà ứng dụng sử dụng trên index cần thiết.
- Chỉ cấp quyền `delete_index` cho tiến trình quản trị index nếu thật sự cần.
- Tách tài khoản runtime khỏi tài khoản migration/administration.
- Ghi audit cho thao tác xóa hàng loạt và xóa dữ liệu nhạy cảm.
- Kiểm tra index/alias đích trước khi chạy job cleanup.
- Không cho phép người dùng truyền tên index tùy ý vào API xóa nếu chưa có kiểm soát.

Nếu repository trỏ tới alias thay vì index cụ thể, cần hiểu alias đang trỏ tới index nào và thao tác xóa sẽ tác động tới tài liệu trong các index đích ra sao.

## 14. Các lỗi thường gặp

### Gọi `delete(entity)` với ID null

Spring Data không thể xác định document cần xóa. Hãy bảo đảm entity có giá trị `@Id` trước khi gọi method.

### Nghĩ `delete(entity)` xóa theo tất cả thuộc tính

Method xóa document theo ID của entity. Muốn xóa theo điều kiện field, dùng query-based delete qua `ElasticsearchOperations` hoặc Delete By Query API.

### Gọi `deleteAll()` nhưng chỉ muốn xóa một nhóm document

`deleteAll()` có phạm vi toàn bộ document trong index đích. Dùng query có điều kiện hoặc danh sách ID để giới hạn phạm vi.

### Nhầm xóa document với xóa index

`repository.deleteAll()` giữ index và mapping. `IndexOperations.delete()` xóa cả index. Chọn đúng thao tác theo mục tiêu.

### Search vẫn trả document ngay sau khi xóa

Đây có thể là độ trễ refresh của Elasticsearch. Kiểm tra delete response và refresh policy, sau đó refresh trong kiểm thử nếu cần.

### Dùng sai routing

Nếu document được ghi với custom routing, thao tác xóa phải sử dụng routing tương ứng. Kiểm tra metadata/routing và cách cấu hình repository hoặc operations.

### Không có quyền xóa

Lỗi authorization có thể xuất hiện nếu role không có quyền xóa document hoặc quyền delete-by-query. Cấp đúng privilege cho index cụ thể; không giải quyết bằng cách dùng tài khoản quản trị cho mọi ứng dụng.

## 15. Kiểm thử thao tác xóa

Khi kiểm thử với Elasticsearch thật hoặc Testcontainers, nên xác minh cả document lẫn index:

```java
@Test
void deleteByIdRemovesTheDocument() {
    Product product = new Product("p-100", "Keyboard", "accessories");
    productRepository.save(product);

    productRepository.deleteById("p-100");

    // Refresh or wait for the configured refresh policy before a search-based assertion.
    assertThat(productRepository.existsById("p-100")).isFalse();
}
```

Đoạn code minh họa luồng kiểm thử; cách chờ refresh và khởi tạo Elasticsearch phụ thuộc cấu hình test của dự án. Có thể kiểm tra thêm:

- `delete(entity)` chỉ xóa document có ID của entity.
- `deleteAll(entities)` chỉ xóa các ID được truyền vào.
- `deleteAll()` xóa document trong index đích nhưng index vẫn tồn tại.
- `IndexOperations.exists()` vẫn trả về `true` sau `repository.deleteAll()`.
- Query-based delete chỉ xóa những document khớp điều kiện.
- Hành vi với ID không tồn tại phù hợp contract mà API ứng dụng mong muốn.

Không chỉ mock repository nếu mục tiêu kiểm tra là xác minh Elasticsearch thực sự xóa document hoặc refresh hoạt động. Integration test với Elasticsearch thật giúp phát hiện vấn đề mapping, index coordinates, routing và quyền truy cập.

## 16. Quy trình chọn và thực hiện thao tác xóa

Trước khi xóa, xác định rõ mục tiêu:

1. Nếu biết một ID, dùng `deleteById(id)`.
2. Nếu đã có entity và muốn xóa document theo ID của entity, dùng `delete(entity)`.
3. Nếu có danh sách ID, dùng `deleteAllById(ids)` khi phiên bản hỗ trợ.
4. Nếu có danh sách entity, dùng `deleteAll(entities)`.
5. Nếu cần xóa theo điều kiện, tạo query rõ ràng và dùng `ElasticsearchOperations.delete(...)` hoặc Delete By Query API.
6. Chỉ dùng `deleteAll()` khi toàn bộ document trong index đích cần được xóa.
7. Chỉ dùng `IndexOperations.delete()` khi chủ đích là xóa cả index và metadata của nó.
8. Xác định refresh policy và cách xác nhận kết quả phù hợp với yêu cầu nhất quán.
9. Kiểm tra quyền truy cập, routing, alias và phạm vi index trước khi chạy thao tác có ảnh hưởng lớn.

## 17. Tổng kết

`deleteById` xóa một document theo ID; `delete(entity)` xóa document theo ID được lấy từ entity; `deleteAll(entities)` hoặc `deleteAllById(ids)` xóa một tập document được chỉ định. `deleteAll()` xóa toàn bộ document trong phạm vi index mà repository quản lý, nhưng không xóa index. Muốn xóa cả index, cần dùng `IndexOperations.delete()` hoặc API quản trị index tương ứng.

Khi chọn thao tác xóa, cần quan tâm tới index đích, ID, custom routing, refresh và quyền Elasticsearch. Đặc biệt, không dùng `deleteAll()` cho một index dùng chung nếu chỉ muốn xóa dữ liệu của một entity class. Với điều kiện nghiệp vụ hoặc tập dữ liệu lớn, query-based delete và bulk APIs cung cấp cách kiểm soát phù hợp hơn. Hiểu đúng phạm vi của từng method giúp thao tác CRUD an toàn và dự đoán được trong Spring Data Elasticsearch.
