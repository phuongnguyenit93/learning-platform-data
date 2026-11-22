# Chọn index qua kiểu Document hoặc IndexCoordinates

Spring Data Elasticsearch cần biết index đích khi lưu, đọc, xóa hoặc tìm kiếm document. Có hai cách phổ biến để xác định index:

- **Dựa trên kiểu entity có `@Document`**: tên index được khai báo trong metadata của lớp Java. Các thao tác repository và operations thông thường sử dụng tên này làm mặc định.
- **Truyền `IndexCoordinates`**: chỉ định index hoặc alias cụ thể tại thời điểm gọi thao tác. Cách này hữu ích khi một kiểu entity được lưu trong nhiều index, khi chuyển phiên bản index hoặc khi đích truy vấn được xác định lúc chạy.

Hai cách không thay thế nhau hoàn toàn. `@Document` mô tả mapping và index mặc định của entity; `IndexCoordinates` xác định đích cụ thể cho một thao tác. Dù chọn cách nào, index đích vẫn cần có mapping tương thích với entity.

## 1. Index mặc định từ @Document

Spring Data Elasticsearch sử dụng annotation `@Document` để mô tả một entity được lưu trong index nào.

~~~java
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

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

Trong ví dụ:

- `@Document(indexName = "products")` khai báo tên index mặc định là `products`.
- `@Id` ánh xạ thuộc tính `id` tới metadata document ID `_id`.
- `@Field` mô tả kiểu dữ liệu của các field.
- Mapping metadata của `ProductDocument` được dùng khi Spring Data chuyển đổi entity thành document và ngược lại.

Khi dùng repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Các thao tác như:

~~~java
ProductDocument saved = productRepository.save(product);
Optional<ProductDocument> found =
        productRepository.findById("P-1001");
productRepository.deleteById("P-1001");
~~~

sử dụng index mặc định từ metadata của `ProductDocument`, tức `products` trong ví dụ này.

Đây là cách phù hợp khi một entity luôn gắn với một index hoặc alias cố định trong suốt vòng đời ứng dụng.

## 2. IndexCoordinates là gì?

`IndexCoordinates` là đối tượng của Spring Data Elasticsearch dùng để chỉ định index hoặc các index đích cho một thao tác.

Import:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
~~~

Tạo đối tượng cho một index:

~~~java
IndexCoordinates index = IndexCoordinates.of("products-v2");
~~~

Có thể dùng tên alias thay cho tên index vật lý:

~~~java
IndexCoordinates index = IndexCoordinates.of("products");
~~~

Trong trường hợp `products` là alias trỏ đến `products-v2`, thao tác qua `IndexCoordinates.of("products")` sẽ nhắm đến alias đó.

`IndexCoordinates` chỉ mô tả đích thao tác. Nó không tự tạo index, không tự tạo alias và cũng không tự khai báo mapping. Index hoặc alias cần được provisioning trước, với cấu trúc tương thích với entity.

## 3. Dùng kiểu Document để chọn index

Khi gọi các API của `ElasticsearchOperations` mà chỉ truyền entity class, Spring Data lấy index từ metadata của lớp đó.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductDocument save(ProductDocument product) {
        return operations.save(product);
    }

    public ProductDocument find(String id) {
        return operations.get(id, ProductDocument.class);
    }

    public void delete(String id) {
        operations.delete(id, ProductDocument.class);
    }
}
~~~

Trong các lời gọi này:

- `operations.save(product)` lưu entity theo index mặc định từ `@Document`.
- `operations.get(id, ProductDocument.class)` đọc theo ID từ index mặc định của entity.
- `operations.delete(id, ProductDocument.class)` xóa theo ID trong index mặc định.

Cách này làm code ngắn gọn vì index được khai báo tập trung tại entity. Nó phù hợp khi ứng dụng có một document model tương ứng với một index mặc định.

Có thể lấy các thao tác quản lý index theo kiểu entity:

~~~java
IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);
~~~

`indexOps(ProductDocument.class)` sử dụng metadata của entity để xác định index tương ứng. Cách này hữu ích khi cần kiểm tra hoặc thao tác với index mặc định được khai báo trong `@Document`.

## 4. Dùng IndexCoordinates để chọn index tại thời điểm gọi

Khi muốn lưu cùng một kiểu entity vào một index khác với index mặc định, truyền `IndexCoordinates` vào overload tương ứng của `ElasticsearchOperations`.

Ví dụ lưu vào `products-v2`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductDocument saveToV2(ProductDocument product) {
        IndexCoordinates target =
                IndexCoordinates.of("products-v2");

        return operations.save(product, target);
    }
}
~~~

Dù entity khai báo `@Document(indexName = "products")`, thao tác `save(product, target)` sử dụng index được truyền trong `target` cho lần ghi đó.

Có thể đọc theo ID từ index cụ thể:

~~~java
IndexCoordinates target =
        IndexCoordinates.of("products-v2");

ProductDocument product =
        operations.get("P-1001", ProductDocument.class, target);
~~~

Xóa theo ID trong index cụ thể:

~~~java
operations.delete(
        "P-1001",
        ProductDocument.class,
        IndexCoordinates.of("products-v2")
);
~~~

Các overload có `IndexCoordinates` cho phép một lớp entity được tái sử dụng trong nhiều index mà không cần thay đổi annotation `@Document` mỗi lần.

Điều quan trọng là truyền đúng index ở mọi thao tác. Nếu ghi vào `products-v2` nhưng lại đọc bằng overload chỉ có `ProductDocument.class`, Spring Data sẽ quay về index mặc định `products` và có thể không tìm thấy document vừa ghi.

## 5. Tìm kiếm qua index được chọn bằng IndexCoordinates

`IndexCoordinates` cũng có thể được dùng khi tìm kiếm.

Ví dụ với `NativeQuery`:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public SearchHits<ProductDocument> searchProducts(
        ElasticsearchOperations operations,
        String keyword,
        String indexName
) {
    Query query = Query.of(q -> q
            .match(m -> m
                    .field("name")
                    .query(keyword)
            )
    );

    NativeQuery nativeQuery = NativeQuery.builder()
            .withQuery(query)
            .build();

    IndexCoordinates target = IndexCoordinates.of(indexName);

    return operations.search(
            nativeQuery,
            ProductDocument.class,
            target
    );
}
~~~

Trong ví dụ:

- `NativeQuery` mô tả điều kiện tìm kiếm.
- `ProductDocument.class` cho Spring Data biết kiểu entity để chuyển đổi kết quả.
- `IndexCoordinates.of(indexName)` xác định index mà Search API sẽ truy vấn.
- `SearchHits<ProductDocument>` chứa các kết quả cùng metadata tìm kiếm.

Có thể dùng cùng một query cho các index khác nhau nếu mapping của chúng tương thích với query và entity.

### Tìm theo nhiều điều kiện

Ví dụ lọc trạng thái và tìm nội dung:

~~~java
Query query = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("name")
                                .query("wireless keyboard")
                        )
                )
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value("PUBLISHED")
                        )
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(query)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(
                nativeQuery,
                ProductDocument.class,
                IndexCoordinates.of("products-v2")
        );
~~~

Index được chọn độc lập với query. Query xác định document cần tìm; `IndexCoordinates` xác định nơi tìm.

## 6. Phân biệt kiểu entity và IndexCoordinates

Hai tham số này có nhiệm vụ khác nhau:

| Thành phần | Vai trò |
|---|---|
| `ProductDocument.class` | Xác định kiểu entity, mapping metadata và cách chuyển đổi dữ liệu |
| `@Document(indexName = "products")` | Xác định index mặc định của entity |
| `IndexCoordinates.of("products-v2")` | Ghi đè đích index cho thao tác cụ thể |
| `NativeQuery` | Mô tả điều kiện tìm kiếm |
| `SearchHits<ProductDocument>` | Kết quả search đã được chuyển đổi thành entity |

Ví dụ:

~~~java
operations.search(
        nativeQuery,
        ProductDocument.class,
        IndexCoordinates.of("products-archive")
);
~~~

Spring Data vẫn dùng metadata của `ProductDocument` để ánh xạ kết quả thành object `ProductDocument`. Chỉ index đích được thay bằng `products-archive`.

Vì vậy, index đích cần có field và kiểu dữ liệu phù hợp với cách entity được chuyển đổi. `IndexCoordinates` không làm cho một mapping khác cấu trúc tự động tương thích với entity.

## 7. Dùng IndexCoordinates khi chuyển phiên bản index

Một trường hợp điển hình là ứng dụng có `products-v1` và `products-v2` trong giai đoạn migration.

Có thể dùng cùng một entity để đọc dữ liệu từ index cũ và ghi sang index mới:

~~~java
IndexCoordinates oldIndex =
        IndexCoordinates.of("products-v1");

IndexCoordinates newIndex =
        IndexCoordinates.of("products-v2");

ProductDocument oldProduct =
        operations.get("P-1001", ProductDocument.class, oldIndex);

if (oldProduct != null) {
    operations.save(oldProduct, newIndex);
}
~~~

Đây là ví dụ minh họa thao tác một document. Với migration thực tế, cần xử lý phân trang/batch, lỗi từng document, mapping khác nhau và dữ liệu được cập nhật đồng thời trong quá trình chuyển đổi.

Nếu cấu trúc v2 thay đổi so với entity cũ, nên dùng mapper chuyển đổi giữa model cũ và model mới thay vì giả định có thể ghi nguyên entity cũ sang mapping mới.

## 8. Dùng IndexCoordinates với alias

Trong production, ứng dụng thường nên truy cập index qua alias ổn định:

~~~java
IndexCoordinates products =
        IndexCoordinates.of("products");
~~~

Alias `products` có thể trỏ tới `products-v1` hoặc `products-v2`. Ứng dụng không cần đổi code khi alias được chuyển sang index vật lý mới.

Ví dụ tạo index và alias bằng Elasticsearch API:

~~~http
PUT /products-v2
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "status": {
        "type": "keyword"
      }
    }
  },
  "aliases": {
    "products": {
      "is_write_index": true
    }
  }
}
~~~

Sau khi alias đã tồn tại, ứng dụng có thể dùng:

~~~java
operations.save(product, IndexCoordinates.of("products"));
~~~

Đối với thao tác ghi, nếu alias trỏ tới nhiều index, cần có write index được xác định rõ. Không nên giả định mọi alias đều có thể nhận ghi một cách không mơ hồ.

Nếu alias trỏ tới nhiều index, Search API có thể tìm trên phạm vi các index được alias đại diện. Cần bảo đảm mapping tương thích trên các index đó và kết quả không bị hiểu nhầm là một index duy nhất.

## 9. Quản lý IndexOperations theo kiểu entity hoặc coordinates

Spring Data cung cấp hai cách lấy `IndexOperations`:

~~~java
IndexOperations byEntity =
        operations.indexOps(ProductDocument.class);

IndexOperations byCoordinates =
        operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

- `indexOps(ProductDocument.class)` lấy index operations dựa trên metadata của entity.
- `indexOps(IndexCoordinates.of("products-v2"))` nhắm tới index được chỉ định.

Các thao tác như kiểm tra index tồn tại, xóa index hoặc quản lý mapping cần được thực hiện có chủ đích và theo quyền phù hợp.

Ví dụ kiểm tra:

~~~java
boolean defaultIndexExists =
        operations.indexOps(ProductDocument.class).exists();

boolean version2Exists =
        operations.indexOps(
                IndexCoordinates.of("products-v2")
        ).exists();
~~~

Không nên coi việc có `IndexOperations` là bằng chứng index đã được tạo. `IndexCoordinates` chỉ xác định đích. Nếu index chưa tồn tại, cần tạo index trước bằng migration, provisioning hoặc API quản trị phù hợp.

## 10. Khi nào dùng kiểu Document, khi nào dùng IndexCoordinates?

| Nhu cầu | Cách chọn index |
|---|---|
| Entity luôn lưu vào một index mặc định | Dùng `@Document(indexName = "...")` và overload theo class |
| Repository CRUD thông thường | Dùng `@Document` metadata |
| Một entity cần ghi vào index phiên bản khác | Dùng `IndexCoordinates` với `ElasticsearchOperations` |
| Chọn index theo tenant hoặc thời điểm chạy | Dùng `IndexCoordinates` sau khi xác thực tên đích |
| Đọc dữ liệu từ index archive | Dùng `IndexCoordinates` |
| Tìm kiếm qua alias ổn định | Dùng `IndexCoordinates.of("alias")` |
| Quản lý index mặc định của entity | `operations.indexOps(Entity.class)` |
| Quản lý một index cụ thể | `operations.indexOps(IndexCoordinates)` |

Repository abstraction thường gắn với index metadata của entity. Khi index đích cần thay đổi theo request hoặc theo tenant, dùng `ElasticsearchOperations` hoặc custom repository fragment để thể hiện rõ lựa chọn đó.

## 11. Lưu ý khi chọn index động theo tenant

Một ứng dụng multi-tenant có thể muốn lưu dữ liệu từng tenant vào index riêng, ví dụ:

- `products-tenant-a`
- `products-tenant-b`
- `products-tenant-c`

Có thể tạo coordinates tại runtime:

~~~java
IndexCoordinates target =
        IndexCoordinates.of("products-" + tenantId);

operations.save(product, target);
~~~

Tuy nhiên, không nên ghép trực tiếp chuỗi do client gửi vào tên index. Cần:

1. Xác thực tenant ID dựa trên danh tính đã được xác thực.
2. Ánh xạ tenant tới index được cấp phép.
3. Chỉ cho phép thao tác trên danh sách index/alias đã quản lý.
4. Bảo đảm index được tạo trước với mapping tương thích.
5. Cấp quyền Elasticsearch phù hợp với phạm vi tenant.
6. Truyền cùng index target vào tất cả thao tác đọc, ghi, cập nhật và xóa.

Ví dụ dùng một resolver:

~~~java
public class TenantIndexResolver {

    public IndexCoordinates resolve(String tenantId) {
        String indexName = switch (tenantId) {
            case "tenant-a" -> "products-tenant-a";
            case "tenant-b" -> "products-tenant-b";
            default -> throw new IllegalArgumentException(
                    "Unknown tenant: " + tenantId
            );
        };

        return IndexCoordinates.of(indexName);
    }
}
~~~

Sau đó service sử dụng kết quả resolver:

~~~java
IndexCoordinates target = tenantIndexResolver.resolve(tenantId);
ProductDocument saved = operations.save(product, target);
~~~

Ví dụ này minh họa allowlist tĩnh. Hệ thống nhiều tenant có thể dùng registry hoặc cấu hình lưu trữ để ánh xạ tenant tới index. Điều quan trọng là index target phải được quyết định từ ngữ cảnh đã xác thực, không lấy tùy ý từ request.

## 12. Những lỗi thường gặp

### Ghi vào index động nhưng đọc theo metadata mặc định

Ví dụ:

~~~java
operations.save(product, IndexCoordinates.of("products-v2"));

ProductDocument found =
        operations.get("P-1001", ProductDocument.class);
~~~

Lệnh save ghi vào `products-v2`, nhưng lệnh get dùng index mặc định `products`. Nếu muốn đọc đúng document vừa ghi, phải truyền cùng coordinates:

~~~java
ProductDocument found = operations.get(
        "P-1001",
        ProductDocument.class,
        IndexCoordinates.of("products-v2")
);
~~~

### Nghĩ rằng IndexCoordinates tự tạo mapping

`IndexCoordinates.of("products-v2")` không tạo index hoặc mapping. Hãy provision index và mapping trước khi ghi dữ liệu.

### Mapping index đích không tương thích entity

Cùng một entity được gửi vào index có field type khác nhau có thể gây lỗi khi ghi hoặc đọc. Kiểm tra mapping của từng index và dùng document mapper riêng nếu schema khác nhau.

### Dùng alias ghi nhưng không có write index

Nếu alias trỏ tới nhiều index mà không xác định write index, thao tác ghi có thể bị từ chối. Cấu hình alias với `is_write_index` khi cần.

### Dùng index name không được kiểm soát

Nếu index name được ghép từ request không đáng tin cậy, ứng dụng có thể thao tác nhầm index. Dùng resolver/allowlist và quyền Elasticsearch giới hạn.

### Dùng class entity như thể nó là tên index

`ProductDocument.class` cung cấp mapping metadata, không phải index target tùy ý. Muốn chọn index khác, hãy truyền `IndexCoordinates` rõ ràng.

## 13. Quy trình lựa chọn và sử dụng

Khi viết service thao tác Elasticsearch:

1. Xác định entity có một index mặc định hay cần nhiều index.
2. Khai báo `@Document(indexName = "...")` cho index mặc định.
3. Dùng overload theo class cho CRUD thông thường.
4. Khi cần chọn index tại runtime, tạo `IndexCoordinates` từ cấu hình hoặc resolver đã xác thực.
5. Truyền coordinates vào các thao tác save, get, delete và search tương ứng.
6. Bảo đảm index/alias đích tồn tại và mapping tương thích.
7. Nếu dùng alias để rollout phiên bản, xác định write index và kế hoạch chuyển alias.
8. Nếu mapping khác nhau giữa các index, dùng document projection/mapper phù hợp.
9. Kiểm tra index đích thực tế bằng Elasticsearch API trong môi trường triển khai.

## Kết luận

Kiểu entity có `@Document` xác định index mặc định và mapping metadata mà Spring Data sử dụng để chuyển đổi document. `IndexCoordinates` cho phép chỉ định index hoặc alias cụ thể tại thời điểm gọi `ElasticsearchOperations`, rất hữu ích cho index versioning, archive hoặc lựa chọn target theo runtime. Khi dùng coordinates, hãy truyền nhất quán qua các thao tác và bảo đảm index đích đã được provisioning với mapping tương thích.
