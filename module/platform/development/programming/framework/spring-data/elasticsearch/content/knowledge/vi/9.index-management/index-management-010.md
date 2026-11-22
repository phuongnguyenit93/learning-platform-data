# Ngăn tự tạo mapping ngoài ý muốn trong môi trường triển khai

Elasticsearch có thể tự tạo index và tự suy luận mapping khi nhận document mới, tùy cấu hình server và ứng dụng. Điều này thuận tiện trong môi trường thử nghiệm, nhưng có thể gây rủi ro khi triển khai: một index bị tạo sai tên, field có kiểu dữ liệu không mong muốn, mapping phát triển không kiểm soát hoặc ứng dụng vô tình ghi dữ liệu vào index chưa được chuẩn bị.

Spring Data Elasticsearch và Elasticsearch có các cơ chế riêng để kiểm soát việc này. Muốn ngăn tự tạo mapping ngoài ý muốn, cần phân biệt rõ:

1. Spring Data có tự tạo index/mapping khi khởi tạo repository hay không.
2. Elasticsearch có tự tạo index khi nhận lệnh ghi vào index chưa tồn tại hay không.
3. Elasticsearch có tự thêm field vào mapping của một index đang tồn tại hay không.
4. Ai chịu trách nhiệm tạo index, settings, mapping và alias trong quá trình triển khai.

## 1. Phân biệt ba cơ chế tự động

Có ba hành vi thường bị nhầm lẫn:

| Cơ chế | Xảy ra khi nào? | Cách kiểm soát |
|---|---|---|
| Spring Data tạo index và mapping | Khi hạ tầng/repository Spring Data khởi tạo và index được khai báo chưa tồn tại | `@Document(createIndex = false)` |
| Elasticsearch tự tạo index | Khi request ghi nhắm đến index chưa tồn tại và cluster cho phép auto-create | Cluster setting `action.auto_create_index` |
| Elasticsearch tự thêm field vào mapping | Khi document có field mới trong một index đang tồn tại và mapping cho phép dynamic mapping | `dynamic: strict`, `dynamic: false`, dynamic templates |

Ba cơ chế này độc lập. Ví dụ, tắt tạo index trong Spring Data không tự động ngăn Elasticsearch tạo index khi ứng dụng gửi request ghi vào một tên index chưa tồn tại. Tương tự, chặn auto-create index không ngăn dynamic mapping thêm field mới vào một index đã tồn tại.

Vì vậy, cần xác định rõ chính sách ở cả tầng ứng dụng lẫn cluster.

## 2. Spring Data Elasticsearch có thể tự tạo index khi khởi động

Spring Data Elasticsearch cho phép khai báo index trên entity bằng `@Document`:

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

    // Constructors, getters and setters
}
~~~

Với cấu hình mặc định của annotation `@Document`, `createIndex` là `true`. Spring Data có thể kiểm tra index khi khởi tạo repository và tạo index cùng mapping từ metadata của entity nếu index chưa tồn tại.

Hành vi này hữu ích khi phát triển local hoặc chạy integration test vì ứng dụng có thể tự chuẩn bị index. Trong production, nếu index phải được tạo theo migration hoặc hạ tầng đã phê duyệt, việc tự tạo trong lúc khởi động có thể làm ứng dụng trở thành chủ sở hữu mapping ngoài dự kiến.

### Tắt tạo index tự động bằng createIndex = false

Có thể khai báo:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

`createIndex = false` yêu cầu Spring Data không tự tạo index cho entity này trong quá trình khởi tạo repository.

Điều này có nghĩa:

- Ứng dụng mong đợi index đã tồn tại trước khi thao tác.
- Mapping cần được chuẩn bị bằng quy trình triển khai riêng.
- Repository vẫn có thể đọc/ghi khi index hoặc alias đích đã tồn tại và có mapping tương thích.
- Nếu index chưa tồn tại, thao tác có thể thất bại; ứng dụng không nên dựa vào repository để âm thầm sửa tình trạng thiếu index.

`createIndex = false` không phải lệnh tạo mapping và cũng không phải chính sách cluster. Nó chỉ kiểm soát hành vi tạo index tự động do Spring Data quản lý.

## 3. Ngăn Elasticsearch tự tạo index khi nhận request ghi

Ngay cả khi Spring Data không tự tạo index, một request ghi đến tên index chưa tồn tại vẫn có thể khiến Elasticsearch tạo index mới nếu cluster cho phép.

Ví dụ ứng dụng gửi request:

~~~http
POST /products/_doc
Content-Type: application/json

{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard"
}
~~~

Nếu `products` chưa tồn tại và server cho phép auto-create, Elasticsearch có thể tạo index `products` cùng mapping suy luận từ document.

Đây là tình huống nguy hiểm nếu `products` lẽ ra phải là alias trỏ đến `products-v1`. Một lần ghi sai thời điểm có thể tạo index thật mang tên alias dự kiến, khiến quy trình triển khai sau đó không thể tạo alias cùng tên.

### Cluster setting action.auto_create_index

Elasticsearch cung cấp cluster setting `action.auto_create_index` để kiểm soát việc tự tạo index như một hệ quả của thao tác ghi.

Có thể tắt auto-create ở cấp cluster bằng Cluster Settings API:

~~~http
PUT /_cluster/settings
Content-Type: application/json

{
  "persistent": {
    "action.auto_create_index": "false"
  }
}
~~~

Khi chính sách này được áp dụng, thao tác ghi vào một index chưa tồn tại sẽ không tự tạo index. Index phải được tạo rõ ràng trước đó bằng Create Index API hoặc quy trình provisioning được cấp quyền.

Cần hiểu đúng phạm vi:

- Setting này kiểm soát **tự động tạo index khi ghi**.
- Nó không thay thế việc tạo index chủ động bằng API quản trị.
- Nó không ngăn dynamic mapping thêm field vào một index đã tồn tại.
- Đây là cấu hình cấp cluster, có thể ảnh hưởng nhiều ứng dụng và hệ thống tích hợp cùng cluster.

Trong môi trường có nhiều hệ thống, tắt auto-create toàn cục có thể ảnh hưởng các index phục vụ logging, monitoring, security hoặc tích hợp khác. Hãy phối hợp với người quản trị Elasticsearch để thiết lập chính sách allowlist theo nhu cầu vận hành. `action.auto_create_index` cũng hỗ trợ mẫu tên cho phép/từ chối; thứ tự và quy tắc pattern cần được kiểm tra cẩn thận theo phiên bản Elasticsearch đang chạy.

## 4. Kiểm soát dynamic mapping trên index đã tồn tại

Một index có thể đã tồn tại nhưng vẫn tự thêm field mới khi document chứa thuộc tính chưa có trong mapping.

Ví dụ document đầu tiên:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard"
}
~~~

Nếu mapping chưa khai báo `name`, Elasticsearch có thể tự suy luận kiểu dữ liệu dựa trên giá trị. Sau đó, một document khác gửi thêm:

~~~json
{
  "sku": "KB-1002",
  "name": "Wireless Keyboard",
  "supplierNote": "Imported batch"
}
~~~

Với dynamic mapping mặc định, field `supplierNote` có thể được thêm vào mapping. Khi dữ liệu đầu vào thay đổi liên tục, mapping có thể phát triển ngoài dự kiến.

### dynamic: strict

Nếu muốn mọi field phải được khai báo rõ trong mapping, có thể dùng:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

Với `dynamic: strict`, document có field chưa được khai báo sẽ bị từ chối với lỗi mapping. Ví dụ `supplierNote` không có trong mapping nên request index sẽ thất bại.

Đây là lựa chọn phù hợp khi schema cần được kiểm soát nghiêm ngặt. Lỗi được phát hiện ngay tại thời điểm ghi thay vì âm thầm tạo field mới.

### dynamic: false

Nếu muốn giữ dữ liệu không biết trước trong `_source` nhưng không lập chỉ mục các field đó, có thể dùng:

~~~json
{
  "mappings": {
    "dynamic": false,
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

Với `dynamic: false`, field chưa khai báo không được thêm vào mapping. Giá trị vẫn có thể nằm trong `_source`, nhưng không được lập chỉ mục để truy vấn như field thông thường.

Chọn `false` khi ứng dụng cần lưu lại phần dữ liệu mở rộng mà không cần tìm kiếm theo các field đó. Nếu mọi field lạ đều phải bị từ chối, dùng `strict`.

### So sánh các chế độ dynamic

| Giá trị | Hành vi khi gặp field chưa khai báo |
|---|---|
| `true` | Tự thêm field vào mapping theo quy tắc suy luận |
| `false` | Không thêm field vào mapping; giá trị vẫn có thể nằm trong `_source` |
| `strict` | Từ chối document có field chưa khai báo |
| `runtime` | Có thể tạo runtime field thay vì lập chỉ mục field theo cách thông thường |

`dynamic` có thể được đặt ở cấp mapping hoặc cấp object để kiểm soát phạm vi cụ thể. Một object lồng nhau có thể có chính sách dynamic riêng. Hãy kiểm tra mapping thực tế để biết chính sách nào đang áp dụng cho từng phần document.

## 5. Dùng dynamic templates khi cần dữ liệu động có kiểm soát

Không phải ứng dụng nào cũng có schema hoàn toàn cố định. Một số hệ thống có tập thuộc tính mở nhưng vẫn muốn quy định cách mapping nhất quán.

**Dynamic templates** cho phép định nghĩa quy tắc ánh xạ dựa trên tên field hoặc kiểu dữ liệu mà Elasticsearch phát hiện.

Ví dụ, các field chuỗi động có thể được map thành keyword:

~~~json
{
  "mappings": {
    "dynamic_templates": [
      {
        "string_fields_as_keyword": {
          "match_mapping_type": "string",
          "mapping": {
            "type": "keyword"
          }
        }
      }
    ],
    "properties": {
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

Dynamic template không tắt dynamic mapping. Nó chỉ quy định kiểu dữ liệu được tạo cho field mới phù hợp với điều kiện. Field không khớp template vẫn có thể được ánh xạ theo quy tắc dynamic mặc định.

Nếu yêu cầu là từ chối mọi field ngoài schema, dùng `dynamic: strict`. Nếu cần một vùng dữ liệu động, có thể giới hạn vùng đó thành object riêng và định nghĩa template hoặc kiểu dữ liệu phù hợp.

### Dùng flattened cho object có nhiều key động

Nếu document chứa một map có nhiều key tùy ý, ví dụ thuộc tính mở rộng theo từng đối tác:

~~~json
{
  "attributes": {
    "color": "black",
    "layout": "ANSI",
    "vendorFeatureCode": "X-91"
  }
}
~~~

Nếu mỗi key trở thành một field mapping riêng, số lượng field có thể tăng nhanh. Elasticsearch có kiểu `flattened` để lưu và tìm kiếm cấu trúc object có nhiều key mà không tạo mapping riêng cho từng key.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "attributes": {
        "type": "flattened"
      }
    }
  }
}
~~~

`flattened` phù hợp cho metadata mở cần tra cứu theo key/value ở mức cơ bản. Nó có các giới hạn về kiểu truy vấn và khả năng phân tích so với các field được mapping riêng. Nếu cần range query, numeric aggregation hoặc analyzer chuyên biệt cho từng thuộc tính, nên khai báo field có kiểu cụ thể.

## 6. Chuẩn bị index bằng quy trình provisioning riêng

Trong production, index settings và mapping nên được tạo trước khi ứng dụng phục vụ request. Có thể quản lý chúng bằng:

- Script triển khai sử dụng Elasticsearch API.
- Infrastructure as Code hoặc công cụ quản trị cluster.
- Job migration riêng có quyền tạo index và cập nhật mapping.
- Index template được quản lý theo phiên bản.

Ứng dụng runtime chỉ cần quyền đọc/ghi trên index hoặc alias cần thiết. Việc tách quyền này giúp tránh trường hợp một lỗi cấu hình trong ứng dụng có thể tạo index hoặc thay đổi cấu trúc cluster.

### Tạo index rõ ràng bằng Elasticsearch API

Ví dụ tạo index versioned với mapping strict:

~~~http
PUT /products-v1
Content-Type: application/json

{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 1
  },
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
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

Trong ví dụ:

- `products-v1` là index vật lý có phiên bản.
- `products` là alias mà ứng dụng sử dụng.
- `dynamic: strict` từ chối field ngoài schema.
- Các field được khai báo tường minh với kiểu dữ liệu phù hợp.
- Alias `products` được tạo cùng index, tránh khoảng thời gian ứng dụng nhìn thấy index nhưng chưa có alias.

Ứng dụng có thể khai báo `@Document(indexName = "products", createIndex = false)` để sử dụng alias đã được provisioning.

### Index template có vai trò gì?

Index template áp dụng settings, mappings và aliases cho index mới có tên khớp với pattern.

Ví dụ:

~~~http
PUT /_index_template/products-template
Content-Type: application/json

{
  "index_patterns": ["products-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    },
    "mappings": {
      "dynamic": "strict",
      "properties": {
        "sku": {
          "type": "keyword"
        },
        "name": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword"
            }
          }
        },
        "status": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Template không tự tạo index. Nó chỉ được áp dụng khi index phù hợp được tạo. Ví dụ, sau khi cài template, quy trình provisioning vẫn cần tạo `products-v1` hoặc một index có tên phù hợp.

Điều này cho phép cùng một chính sách mapping được áp dụng nhất quán cho các index phiên bản mới.

## 7. Tạo index tường minh bằng Spring Data Elasticsearch

Nếu quy trình provisioning được triển khai bằng Java, Spring Data cung cấp `IndexOperations` để quản lý index và mapping.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductIndexProvisioner {

    private final ElasticsearchOperations operations;

    public ProductIndexProvisioner(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndexIfMissing() {
        IndexOperations indexOperations =
                operations.indexOps(ProductDocument.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

`createWithMapping()` tạo index cùng mapping được suy ra từ metadata của entity. Nếu entity có cấu hình settings phù hợp, quy trình tạo index cũng có thể sử dụng settings tương ứng.

Đây là ví dụ cho một job provisioning có chủ đích. Không nên để mọi instance ứng dụng production tự chạy đoạn code này khi khởi động nếu index được quản lý bởi pipeline triển khai riêng.

Lưu ý thêm:

- `exists()` chỉ kiểm tra trạng thái tại thời điểm gọi; hai instance có thể cùng thấy index chưa tồn tại.
- Cần có một chủ thể provisioning duy nhất hoặc xử lý xung đột tạo index một cách có kiểm soát.
- Tài khoản chạy provisioning cần quyền tạo index và quản lý mapping.
- Tài khoản runtime nên có quyền tối thiểu cần thiết để đọc/ghi dữ liệu.

Nếu dùng alias làm `indexName`, không gọi `createWithMapping()` trên alias đã tồn tại như thể đó là index vật lý cần tạo mới. Hãy tạo index versioned và alias bằng quy trình provisioning tương ứng.

## 8. Cấu hình entity cho môi trường triển khai

Một entity có thể mô tả mapping mong muốn nhưng tắt việc tự tạo index:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;
}
~~~

`indexName = "products"` có thể là alias được provisioning tạo trước. `createIndex = false` giúp repository không tự tạo index khi khởi tạo.

Cấu hình này không thay thế mapping đã được tạo trên Elasticsearch. Mapping thực tế của alias đích cần tương thích với cách Spring Data chuyển đổi entity.

Có thể tổ chức cấu hình theo môi trường:

| Môi trường | Chính sách thường dùng |
|---|---|
| Local development | Có thể cho phép tạo index tự động để tiện thử nghiệm |
| Integration test | Tạo index trong setup test và xóa theo vòng đời test |
| Staging | Dùng migration/provisioning trước khi triển khai ứng dụng |
| Production | Tắt Spring Data create index, kiểm soát auto-create ở cluster, mapping được quản lý tường minh |

Nếu dùng profile riêng, cần bảo đảm profile production thực sự được kích hoạt trong pipeline triển khai. Không nên dựa vào giá trị mặc định của local để suy luận cấu hình production.

## 9. Kiểm tra quyền của tài khoản runtime

Ngay cả khi đã tắt các cơ chế tự động, tài khoản ứng dụng có thể vẫn có quyền tạo index hoặc cập nhật mapping. Nếu muốn bảo vệ cấu trúc index, hãy cấp quyền theo nguyên tắc tối thiểu.

Một tài khoản runtime thường chỉ cần các quyền phù hợp với thao tác của ứng dụng, ví dụ đọc, tìm kiếm, index/update/delete trên alias hoặc index được chỉ định. Tài khoản provisioning riêng mới cần quyền tạo index, cập nhật mapping, tạo template hoặc thay đổi alias.

Quyền cụ thể phụ thuộc loại thao tác và phiên bản Elasticsearch. Hãy đối chiếu privilege API của phiên bản cluster đang chạy và kiểm tra bằng tài khoản thực tế.

Không nên dùng tài khoản superuser cho kết nối ứng dụng thông thường. Nếu runtime có quyền quản trị rộng, một lỗi trong tên index hoặc request có thể tạo hoặc thay đổi tài nguyên ngoài dự kiến.

## 10. Quản lý thay đổi mapping bằng versioned index và alias

Khi mapping thay đổi không tương thích, không nên sửa index đang phục vụ production một cách tùy tiện.

Một quy trình thường dùng:

~~~mermaid
flowchart TD
    A["Mapping v1 đang phục vụ qua alias products"] --> B["Tạo products-v2 với mapping mới"]
    B --> C["Reindex dữ liệu từ products-v1 sang products-v2"]
    C --> D["Kiểm tra số lượng và truy vấn"]
    D --> E["Chuyển alias products sang products-v2"]
    E --> F["Ứng dụng tiếp tục dùng alias products"]
~~~

Ví dụ chuyển alias:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Alias giúp ứng dụng không cần biết index vật lý đang mang phiên bản nào. Ứng dụng tiếp tục dùng `products`; pipeline triển khai chịu trách nhiệm tạo index mới, reindex và chuyển alias.

Nếu ứng dụng đang ghi trong lúc reindex, cần thiết kế chiến lược đồng bộ thay đổi phát sinh, tạm dừng ghi hoặc dùng cơ chế dual-write có kiểm soát. Chỉ chuyển alias sau khi dữ liệu đã được xác nhận.

## 11. Kiểm tra mapping và index thực tế

Không nên chỉ nhìn annotation Java để kết luận mapping trong cluster đã đúng. Hãy kiểm tra trực tiếp Elasticsearch.

### Kiểm tra index hoặc alias

~~~http
GET /_resolve/index/products
~~~

API này giúp xác định tên `products` đang phân giải thành index vật lý nào hoặc alias nào.

### Kiểm tra mapping

~~~http
GET /products/_mapping
~~~

Kiểm tra:

- Field có kiểu dữ liệu như dự kiến không?
- Mapping có `dynamic: strict` hay chính sách mong muốn không?
- Có field ngoài dự kiến đã xuất hiện không?
- Multi-field và analyzer có đúng không?

### Kiểm tra index template

~~~http
GET /_index_template/products-template
~~~

Kiểm tra template được cài đặt đúng pattern, settings và mapping chưa.

### Kiểm tra danh sách index

~~~http
GET /_cat/indices/products*?v
~~~

Lệnh này giúp phát hiện index vật lý được tạo ngoài dự kiến, chẳng hạn `products` xuất hiện bên cạnh `products-v1` dù ứng dụng dự kiến chỉ sử dụng alias.

## 12. Những lỗi triển khai thường gặp

### Chỉ đặt createIndex = false và nghĩ rằng đã chặn mọi auto-create

Annotation chỉ kiểm soát hành vi tạo index của Spring Data. Nếu cluster vẫn cho phép auto-create, một request ghi vào index không tồn tại vẫn có thể tạo index.

Cần kiểm soát thêm `action.auto_create_index` ở cluster.

### Tắt auto-create nhưng quên provisioning

Khi index chưa được tạo, ứng dụng ghi dữ liệu sẽ nhận lỗi thay vì tự tạo index. Đây là hành vi có chủ đích của chính sách, nhưng pipeline phải tạo index trước khi ứng dụng bắt đầu nhận traffic.

### Tắt dynamic mapping nhưng không kiểm tra field

`dynamic: false` không báo lỗi khi có field lạ; nó chỉ không lập chỉ mục field đó. Nếu muốn phát hiện payload sai schema, dùng `dynamic: strict` và xử lý lỗi ghi phù hợp.

### Dùng strict nhưng thiếu field hợp lệ

Nếu một phiên bản ứng dụng gửi thêm field mới trước khi mapping được cập nhật, Elasticsearch từ chối document. Cần triển khai mapping tương thích trước code sử dụng field mới.

### Dùng index name cố định trong khi muốn versioned index

Nếu ứng dụng ghi trực tiếp vào `products-v1`, việc đổi index cần thay cấu hình ứng dụng. Dùng alias ổn định giúp giảm sự phụ thuộc này.

### Để runtime user có quyền quản trị index

Một lỗi trong tên index hoặc request có thể tạo tài nguyên ngoài dự kiến. Tách tài khoản provisioning và runtime giúp giảm phạm vi ảnh hưởng.

### Tạo mapping khác nhau giữa các môi trường

Nếu local dùng dynamic mapping còn production dùng strict mapping, code có thể chạy local nhưng thất bại khi triển khai. Cần đưa settings/mapping vào cùng quy trình quản lý phiên bản và kiểm tra ở staging.

## 13. Quy trình triển khai đề xuất

Khi chuẩn bị một thay đổi index cho production:

1. Xác định schema và các field cần được lập chỉ mục.
2. Khai báo mapping, analyzer, settings và chính sách dynamic.
3. Đưa index template hoặc mapping vào source-controlled migration.
4. Tạo index vật lý trước khi triển khai ứng dụng.
5. Tạo alias nếu ứng dụng sử dụng alias ổn định.
6. Cấu hình entity với `@Document(createIndex = false)`.
7. Kiểm soát `action.auto_create_index` ở cấp cluster theo chính sách chung.
8. Cấp quyền provisioning và runtime riêng biệt.
9. Kiểm tra mapping, alias và index bằng Elasticsearch API.
10. Triển khai ứng dụng sau khi index sẵn sàng.
11. Theo dõi lỗi mapping khi ghi document.
12. Khi thay đổi mapping không tương thích, tạo index phiên bản mới, reindex và chuyển alias theo kế hoạch.

## Kết luận

Ngăn tự tạo mapping ngoài ý muốn cần kiểm soát nhiều lớp. Dùng `@Document(createIndex = false)` để Spring Data không tự tạo index khi khởi tạo repository; cấu hình `action.auto_create_index` để kiểm soát việc Elasticsearch tự tạo index khi ghi vào tên chưa tồn tại; dùng `dynamic: strict` hoặc `false` để kiểm soát field mới trong index đã tồn tại. Trong production, nên tạo index, settings, mapping và alias bằng quy trình provisioning có phiên bản, cấp quyền riêng cho provisioning và runtime, rồi mới triển khai ứng dụng.
