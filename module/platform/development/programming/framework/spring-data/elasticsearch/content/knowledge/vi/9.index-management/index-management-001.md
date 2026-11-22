# Vai trò của IndexOperations và cách lấy indexOps

Spring Data Elasticsearch cung cấp **IndexOperations** để làm việc với cấu trúc và vòng đời của index Elasticsearch. Thông qua đối tượng này, ứng dụng có thể kiểm tra index đã tồn tại hay chưa, tạo hoặc xóa index, khai báo mapping, đọc settings và làm mới index. Để lấy đối tượng **IndexOperations**, ứng dụng gọi phương thức **indexOps(...)** trên **ElasticsearchOperations**.

Cần phân biệt hai cấp độ thao tác:

- **ElasticsearchOperations** làm việc với tài liệu: lưu, đọc, tìm kiếm, cập nhật và xóa tài liệu.
- **IndexOperations** làm việc với index: tạo index, quản lý settings, mapping và các thao tác quản trị liên quan.

Bài này dùng ví dụ index **products** chứa tài liệu sản phẩm. Ta sẽ tìm hiểu vai trò của IndexOperations, các cách gọi **indexOps**, cách tạo index từ metadata của lớp tài liệu và cách thao tác với index có tên được chỉ định rõ.

## 1. Index trong Elasticsearch là gì?

Elasticsearch tổ chức tài liệu trong các index. Có thể hình dung index tương tự một tập dữ liệu có cấu trúc, trong đó mỗi tài liệu là một đối tượng JSON. Index có tên riêng, settings và mapping.

Ví dụ, ứng dụng quản lý sản phẩm có thể lưu các tài liệu vào index **products**:

~~~json
{
  "id": "p-1001",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

Các thành phần chính của một index:

- **Tên index**: tên định danh mà ứng dụng dùng để truy cập, ví dụ **products**.
- **Settings**: các thiết lập vận hành như số shard, replica, refresh interval và analyzer.
- **Mapping**: định nghĩa kiểu dữ liệu và cách phân tích từng trường.
- **Documents**: các tài liệu JSON được lưu trong index.
- **Aliases**: tên tham chiếu có thể trỏ đến một hoặc nhiều index, thường dùng để chuyển đổi index mà không phải đổi tên trong ứng dụng.

Index là đối tượng quản trị ở cấp Elasticsearch. Khi cần thay đổi cấu trúc index, chẳng hạn tạo mapping hoặc đọc settings, ứng dụng sử dụng API quản lý index.

## 2. Vai trò của IndexOperations

**IndexOperations** là abstraction của Spring Data Elasticsearch dành cho các thao tác quản lý index. Nó che giấu phần lớn chi tiết giao tiếp với Elasticsearch và cung cấp các phương thức Java để thực hiện những công việc phổ biến.

Các nhóm chức năng thường dùng:

| Nhóm | Phương thức tiêu biểu | Mục đích |
|---|---|---|
| Kiểm tra | **exists()** | Kiểm tra index có tồn tại |
| Tạo | **create()**, **createWithMapping()** | Tạo index và cấu hình cần thiết |
| Mapping | **createMapping()**, **putMapping()**, **getMapping()** | Tạo, áp dụng hoặc đọc mapping |
| Settings | **getSettings()** | Đọc cấu hình index |
| Xóa | **delete()** | Xóa index |
| Làm mới | **refresh()** | Yêu cầu refresh index |
| Alias | Các phương thức alias được phiên bản hỗ trợ | Quản lý tên alias gắn với index |

Tên và chữ ký cụ thể của một số phương thức có thể thay đổi giữa các thế hệ Spring Data Elasticsearch. Hãy đối chiếu API của phiên bản thư viện mà dự án đang sử dụng.

### IndexOperations không thay thế ElasticsearchOperations

Hai abstraction có mục đích khác nhau:

| Tình huống | API nên dùng |
|---|---|
| Lưu một sản phẩm | **ElasticsearchOperations.save(...)** hoặc repository |
| Đọc sản phẩm theo ID | **ElasticsearchOperations.get(...)** hoặc repository |
| Tìm kiếm sản phẩm | **ElasticsearchOperations.search(...)** hoặc repository query |
| Xóa một tài liệu | **ElasticsearchOperations.delete(...)** hoặc repository |
| Kiểm tra index products | **IndexOperations.exists()** |
| Tạo index products | **IndexOperations.createWithMapping()** |
| Đọc mapping của products | **IndexOperations.getMapping()** |
| Xóa index products | **IndexOperations.delete()** |

Không nên dùng thao tác xóa index khi mục tiêu chỉ là xóa một tài liệu. Xóa index ảnh hưởng đến toàn bộ tài liệu trong index và cả cấu hình mapping, settings của index đó.

## 3. ElasticsearchOperations và phương thức indexOps(...)

Trong Spring Data Elasticsearch, **ElasticsearchOperations** là API cấp cao cho các thao tác với tài liệu và index. Phương thức **indexOps(...)** tạo một đối tượng **IndexOperations** gắn với index đích.

Có hai cách lấy phổ biến:

- Gọi **indexOps(Class<?> entityType)** để lấy index theo metadata của lớp tài liệu.
- Gọi **indexOps(IndexCoordinates indexCoordinates)** để chỉ định tên index hoặc tập index cần thao tác.

### Cách 1: Lấy index từ lớp tài liệu

Giả sử lớp tài liệu được khai báo như sau:

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
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    // Constructor, getter và setter được lược bỏ.
}
~~~

Có thể lấy IndexOperations bằng cách inject **ElasticsearchOperations**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexService {

    private final ElasticsearchOperations operations;

    public ProductIndexService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean indexExists() {
        IndexOperations indexOperations = operations.indexOps(Product.class);
        return indexOperations.exists();
    }
}
~~~

Khi truyền **Product.class**, Spring Data Elasticsearch sử dụng metadata của lớp tài liệu, đặc biệt là tên index trong **@Document**. Trong ví dụ này, đối tượng IndexOperations thao tác với index **products**.

Ưu điểm của cách này là tên index được khai báo tập trung ở lớp tài liệu. Nếu tên index thay đổi trong annotation, các đoạn mã gọi **indexOps(Product.class)** vẫn sử dụng metadata mới mà không cần lặp lại tên chuỗi ở nhiều nơi.

Cách này đặc biệt phù hợp khi index gắn trực tiếp với một entity hoặc document class của ứng dụng.

### Cách 2: Lấy index bằng IndexCoordinates

Nếu cần thao tác với một index được xác định tại thời điểm chạy, có thể dùng **IndexCoordinates**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexCoordinates coordinates = IndexCoordinates.of("products");
IndexOperations indexOperations = operations.indexOps(coordinates);
~~~

**IndexCoordinates.of("products")** tạo đối tượng mô tả index có tên **products**. Cách này hữu ích khi ứng dụng làm việc với tên index khác tên khai báo mặc định của entity, chẳng hạn index theo phiên bản:

~~~java
IndexCoordinates currentIndex = IndexCoordinates.of("products-v2");
IndexOperations indexOperations = operations.indexOps(currentIndex);
~~~

Một số ứng dụng sử dụng index theo tenant hoặc theo thời gian. Khi đó, tên index có thể được xây dựng từ cấu hình hoặc ngữ cảnh nghiệp vụ. Cần xác thực và chuẩn hóa tên trước khi sử dụng, đồng thời bảo đảm tài khoản Elasticsearch chỉ có quyền trên các index được phép.

Lưu ý rằng **IndexCoordinates** chỉ xác định đích thao tác. Nó không tự tạo index, không kiểm tra index tồn tại và không tự suy ra mapping từ một lớp tài liệu. Những việc đó phải được thực hiện bằng các phương thức của IndexOperations và metadata phù hợp.

## 4. Lấy IndexOperations trong service hoặc component

Trong ứng dụng Spring, thường inject **ElasticsearchOperations** qua constructor. Sau đó, mỗi phương thức nghiệp vụ lấy IndexOperations cho index cần thao tác.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class IndexAdminService {

    private final ElasticsearchOperations operations;

    public IndexAdminService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean productsIndexExists() {
        return operations.indexOps(Product.class).exists();
    }

    public boolean archiveIndexExists() {
        return operations.indexOps(
                IndexCoordinates.of("products-archive")
        ).exists();
    }
}
~~~

Không cần tự khởi tạo **ElasticsearchOperations** bằng toán tử **new**. Spring Boot và Spring Data Elasticsearch cấu hình bean kết nối dựa trên cấu hình ứng dụng. Constructor injection giúp service dễ kiểm thử và tách biệt logic nghiệp vụ với cách tạo client.

Việc gọi **indexOps(...)** chỉ lấy đối tượng thao tác tương ứng. Các lệnh như **exists()**, **create()**, **getMapping()** mới thực hiện công việc với Elasticsearch.

## 5. Kiểm tra index bằng exists()

Trước khi tạo index, ứng dụng thường kiểm tra index đã tồn tại chưa:

~~~java
IndexOperations indexOperations = operations.indexOps(Product.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

Phương thức **exists()** trả về giá trị boolean:

- **true**: index đã tồn tại.
- **false**: index chưa tồn tại hoặc không được Elasticsearch nhận diện là tồn tại.

Sau khi kiểm tra, ứng dụng có thể quyết định tạo index. Cách này tránh gửi lệnh tạo index lặp lại khi ứng dụng khởi động nhiều lần.

Tuy nhiên, kiểm tra rồi tạo là hai request riêng biệt. Nếu nhiều instance ứng dụng khởi động đồng thời, có thể xảy ra tình huống cả hai cùng thấy index chưa tồn tại rồi cùng gửi lệnh tạo. Trong hệ thống có nhiều instance, nên dùng quy trình migration hoặc khởi tạo index được điều phối để tránh cạnh tranh.

Cũng cần phân biệt trường hợp index không tồn tại với trường hợp ứng dụng không có quyền truy cập hoặc Elasticsearch không kết nối được. Lỗi kết nối và lỗi quyền thường được trả về dưới dạng exception, không nên tự động coi mọi lỗi đều có nghĩa index chưa tồn tại.

## 6. Tạo index với settings và mapping

Index thường cần settings và mapping ngay từ đầu. Nếu lớp tài liệu có **@Document**, **@Setting** và **@Mapping**, Spring Data Elasticsearch có thể lấy metadata để tạo index tương ứng.

Ví dụ lớp tài liệu:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Mapping;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products", createIndex = false)
@Setting(settingPath = "/elasticsearch/products-settings.json")
@Mapping(mappingPath = "/elasticsearch/products-mapping.json")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    // Constructor, getter và setter được lược bỏ.
}
~~~

Có thể chủ động tạo index bằng:

~~~java
IndexOperations indexOperations = operations.indexOps(Product.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

**createWithMapping()** tạo index với settings và mapping lấy từ metadata của lớp tài liệu. Đây là lựa chọn thuận tiện khi muốn khai báo cấu hình index gần với entity và để Spring Data nạp các tài nguyên được chỉ định.

Một cách khác là tách riêng hai bước:

~~~java
IndexOperations indexOperations = operations.indexOps(Product.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping();
}
~~~

Trong cách này:

- **create()** tạo index với settings được lấy từ metadata.
- **putMapping()** áp dụng mapping được suy ra từ metadata lớp tài liệu.

Khi dùng API này, hãy kiểm tra chữ ký phương thức và hành vi cụ thể trong phiên bản Spring Data Elasticsearch của dự án. Với mapping phức tạp, tệp JSON ngoài hoặc cấu hình có nhiều tùy chọn, **createWithMapping()** thường thể hiện rõ ý định tạo index đầy đủ hơn.

## 7. Đọc mapping và settings của index

Sau khi index tồn tại, có thể dùng IndexOperations để xem cấu hình hiện tại.

### Đọc mapping

~~~java
import java.util.Map;

IndexOperations indexOperations = operations.indexOps(Product.class);

if (indexOperations.exists()) {
    Map<String, Object> mapping = indexOperations.getMapping();
    System.out.println(mapping);
}
~~~

**getMapping()** trả về cấu trúc mapping hiện tại của index. Có thể dùng dữ liệu này để kiểm tra trường, kiểu dữ liệu, analyzer và các multi-field đã được áp dụng.

### Đọc settings

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

IndexOperations indexOperations = operations.indexOps(Product.class);

if (indexOperations.exists()) {
    Document settings = indexOperations.getSettings();
    System.out.println(settings);
}
~~~

Settings có thể bao gồm cấu hình shard, replica, refresh interval và analysis. Một số API cho phép lấy cả default settings hoặc chỉ settings đã được cấu hình tường minh; chi tiết phụ thuộc phiên bản.

Trong Spring Data Elasticsearch, **Document** là cấu trúc dữ liệu được dùng để biểu diễn nội dung JSON linh hoạt. Nếu cần đọc hoặc xử lý kết quả, hãy dùng đúng kiểu trả về trong API phiên bản dự án.

Đọc settings và mapping hữu ích cho tác vụ quản trị, kiểm tra môi trường triển khai hoặc chẩn đoán khi truy vấn không hoạt động như mong đợi.

## 8. Tạo mapping riêng và áp dụng bằng putMapping

Trong một số trường hợp, ứng dụng muốn tạo mapping từ metadata của entity nhưng kiểm soát riêng thời điểm áp dụng. Có thể lấy mapping bằng **createMapping()** rồi truyền cho **putMapping(...)**:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

IndexOperations indexOperations = operations.indexOps(Product.class);

Document mapping = indexOperations.createMapping();

if (!indexOperations.exists()) {
    indexOperations.create();
}

indexOperations.putMapping(mapping);
~~~

Đoạn mã minh họa hai thao tác riêng biệt:

1. **createMapping()** tạo biểu diễn mapping dựa trên metadata của entity.
2. **putMapping(mapping)** gửi mapping đến index đích.

Trong thực tế, phải bảo đảm index đã được tạo trước khi gọi **putMapping**. Có thể dùng **createWithMapping()** nếu muốn thực hiện toàn bộ quá trình trong một lệnh.

Nếu mapping được lưu trong tài nguyên JSON thông qua **@Mapping**, metadata của entity có thể đọc nội dung đó khi tạo mapping. Vì vậy, cần đặt đúng file trong classpath và kiểm tra tên đường dẫn trong annotation.

## 9. Xóa index bằng delete()

**IndexOperations.delete()** xóa index được đại diện bởi đối tượng IndexOperations:

~~~java
IndexOperations indexOperations = operations.indexOps(Product.class);

if (indexOperations.exists()) {
    indexOperations.delete();
}
~~~

Đây là thao tác quản trị có phạm vi lớn. Xóa index sẽ xóa toàn bộ tài liệu cùng mapping và settings của index đó. Sau khi xóa, các truy vấn trên index sẽ thất bại cho đến khi index được tạo lại.

Không nên gọi **delete()** trong luồng xử lý thông thường của một request người dùng nếu nghiệp vụ chỉ yêu cầu xóa một sản phẩm. Để xóa một tài liệu, dùng repository hoặc **ElasticsearchOperations.delete(...)**.

Khi xóa index theo tên động, hãy xác thực tên index và giới hạn quyền truy cập. Tránh ghép trực tiếp giá trị do người dùng nhập vào lệnh quản trị index.

## 10. Refresh index

Elasticsearch có cơ chế near real-time. Sau khi ghi tài liệu, dữ liệu có thể chưa xuất hiện ngay trong kết quả tìm kiếm cho đến khi index được refresh.

Có thể gọi:

~~~java
IndexOperations indexOperations = operations.indexOps(Product.class);
indexOperations.refresh();
~~~

**refresh()** yêu cầu Elasticsearch làm mới index để các thay đổi đã ghi có thể được tìm kiếm. Thao tác này hữu ích trong một số bài kiểm thử hoặc luồng cần đọc lại dữ liệu ngay sau khi ghi.

Không nên gọi refresh sau mỗi lần ghi trong môi trường có tải cao. Refresh thường xuyên có thể làm tăng chi phí xử lý và giảm hiệu năng ghi. Trong ứng dụng bình thường, nên để Elasticsearch quản lý refresh theo chu kỳ cấu hình, hoặc chỉ yêu cầu refresh khi thực sự cần.

Refresh cũng không giống flush hay force merge. Refresh làm cho dữ liệu mới có thể tìm kiếm; flush liên quan đến việc ghi các thay đổi vào Lucene commit và translog; force merge hợp nhất segment. Đây là các thao tác khác nhau và không nên dùng thay thế cho nhau.

## 11. Làm việc với tên index tường minh và index theo phiên bản

Khi index có tên cố định theo **@Document**, dùng **indexOps(Product.class)** là lựa chọn rõ ràng. Nhưng trong hệ thống triển khai nhiều phiên bản index, có thể cần thao tác với tên cụ thể:

~~~java
IndexCoordinates v1 = IndexCoordinates.of("products-v1");
IndexCoordinates v2 = IndexCoordinates.of("products-v2");

IndexOperations oldIndex = operations.indexOps(v1);
IndexOperations newIndex = operations.indexOps(v2);
~~~

Có thể kiểm tra hoặc xóa từng index độc lập. Nếu cần tạo index mới bằng mapping của entity, có thể lấy mapping từ đối tượng index theo lớp tài liệu rồi áp dụng vào index theo tên cụ thể:

~~~java
IndexOperations entityIndex = operations.indexOps(Product.class);
IndexOperations versionedIndex =
        operations.indexOps(IndexCoordinates.of("products-v2"));

if (!versionedIndex.exists()) {
    versionedIndex.create();
    versionedIndex.putMapping(entityIndex.createMapping());
}
~~~

Ví dụ này giả định mapping của **Product** tương thích với index mới và các settings cần thiết đã được tạo phù hợp. Nếu index mới cần analyzer hoặc shard settings riêng, hãy tạo index với settings tương ứng trước khi áp dụng mapping. Không dùng mapping của index cũ một cách máy móc khi schema đã thay đổi.

### Alias và chuyển đổi index

Trong hệ thống vận hành lâu dài, ứng dụng có thể truy cập index qua alias, ví dụ **products-current**. Alias cho phép chuyển từ **products-v1** sang **products-v2** mà ứng dụng không cần thay đổi tên truy cập.

Quy trình điển hình:

1. Tạo **products-v2** với settings và mapping mới.
2. Reindex dữ liệu từ **products-v1** sang **products-v2**.
3. Kiểm tra dữ liệu và truy vấn trên index mới.
4. Chuyển alias **products-current** sang index mới bằng thao tác alias phù hợp.
5. Sau khi xác nhận, xử lý index cũ theo chính sách lưu giữ.

Các phiên bản Spring Data Elasticsearch có thể cung cấp các phương thức alias khác nhau trên IndexOperations. Nếu cần thao tác alias phức tạp hoặc cần điều khiển nguyên tử nhiều action, có thể dùng API quản trị index của Elasticsearch Java Client tương ứng với phiên bản đang chạy.

## 12. Ví dụ hoàn chỉnh: dịch vụ quản lý index sản phẩm

Ví dụ sau gom các thao tác phổ biến vào một service:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexAdminService {

    private final ElasticsearchOperations operations;

    public ProductIndexAdminService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public boolean exists() {
        return operations.indexOps(Product.class).exists();
    }

    public void createIfMissing() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }

    public Map<String, Object> getMapping() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            throw new IllegalStateException("Index products chưa tồn tại");
        }

        return indexOperations.getMapping();
    }

    public void refresh() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (indexOperations.exists()) {
            indexOperations.refresh();
        }
    }

    public void deleteIndex() {
        IndexOperations indexOperations = operations.indexOps(Product.class);

        if (indexOperations.exists()) {
            indexOperations.delete();
        }
    }
}
~~~

Service này minh họa cách lấy IndexOperations một lần trong mỗi thao tác quản trị. Phương thức **createIfMissing()** tạo index cùng mapping; **getMapping()** đọc mapping; **refresh()** yêu cầu refresh; **deleteIndex()** xóa index nếu tồn tại.

Nếu muốn đọc settings, có thể bổ sung phương thức trả về **Document** theo API phiên bản đang dùng. Không nên trả trực tiếp toàn bộ cấu hình index cho người dùng cuối nếu ứng dụng có yêu cầu bảo mật hoặc phân quyền quản trị.

## 13. Khi nào dùng indexOps(Class) và khi nào dùng indexOps(IndexCoordinates)?

Hai overload giải quyết hai tình huống khác nhau:

| Tiêu chí | **indexOps(Product.class)** | **indexOps(IndexCoordinates.of("products-v2"))** |
|---|---|---|
| Xác định index | Từ metadata **@Document** của entity | Từ tên index được chỉ định |
| Mapping từ entity | Có thể dùng metadata của lớp tài liệu | Không tự xác định entity |
| Tên index động | Không phải mục đích chính | Phù hợp với tên được xác định khi chạy |
| Index theo phiên bản | Cần metadata phù hợp hoặc cách quản lý riêng | Có thể chỉ định rõ từng index |
| Tính dễ đọc | Rõ ràng khi index gắn với entity | Rõ ràng khi thao tác index cụ thể |

Quy tắc lựa chọn thực tế:

- Dùng **indexOps(Product.class)** khi index được gắn với một lớp tài liệu và cấu hình nằm trong annotation.
- Dùng **indexOps(IndexCoordinates.of(...))** khi cần thao tác với tên index cụ thể, index theo phiên bản hoặc alias.
- Nếu cần tạo index theo tên động nhưng dùng mapping của entity, hãy chủ động lấy mapping từ metadata entity và áp dụng cho index đích.
- Nếu cần quản lý nhiều index, nên đóng gói quy tắc xác định tên index vào một service thay vì rải chuỗi tên index trong nhiều lớp.

## 14. Lỗi thường gặp khi sử dụng IndexOperations

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| **exists()** trả về false | Index chưa được tạo hoặc tên index được xác định sai | Kiểm tra **@Document**, **IndexCoordinates** và index trên Elasticsearch |
| Tạo index báo đã tồn tại | Một tiến trình khác đã tạo index giữa bước kiểm tra và tạo | Dùng migration hoặc quy trình khởi tạo được điều phối |
| Index được tạo nhưng thiếu mapping | Chỉ gọi **create()** mà chưa áp dụng mapping | Dùng **createWithMapping()** hoặc gọi **putMapping()** sau khi tạo |
| Không tìm thấy tệp settings/mapping | Sai đường dẫn classpath hoặc file không được đóng gói | Kiểm tra resources và đường dẫn annotation |
| Mapping không thay đổi sau khi sửa entity | Index đã tồn tại nên thao tác tạo không chạy lại | Đọc mapping hiện tại; lập kế hoạch cập nhật hoặc reindex |
| **putMapping()** báo lỗi | Index chưa tồn tại hoặc mapping không tương thích | Kiểm tra thứ tự tạo index và kiểu trường |
| Không có quyền quản trị index | Tài khoản chỉ được cấp quyền đọc/ghi tài liệu | Cấp quyền index phù hợp theo chính sách bảo mật |
| Xóa index làm ứng dụng lỗi | Ứng dụng vẫn truy cập index vừa bị xóa | Chỉ xóa trong quy trình quản trị và tạo lại trước khi ứng dụng sử dụng |

Khi chẩn đoán, hãy phân biệt lỗi từ Spring Data, lỗi kết nối và lỗi Elasticsearch trả về. Kiểm tra log ứng dụng, quyền của tài khoản, tên index thực tế và phản hồi của API quản trị.

## 15. Lưu ý về phiên bản và vận hành

Spring Data Elasticsearch đã có nhiều thay đổi API qua các phiên bản. Những điểm cần kiểm tra khi áp dụng:

- Package và chữ ký của **ElasticsearchOperations**, **IndexOperations** và **IndexCoordinates**.
- Hành vi của **createWithMapping()**, **create()** và **putMapping()** trong phiên bản đang dùng.
- Cách nạp settings/mapping từ **@Setting** và **@Mapping**.
- Khả năng tương thích giữa phiên bản Spring Data Elasticsearch và Elasticsearch cluster.
- Các phương thức alias và kiểu dữ liệu trả về khi đọc settings hoặc mapping.

Không nên cho rằng sửa annotation hoặc file JSON sẽ tự động cập nhật index đã tồn tại. Nhiều thay đổi mapping cần tạo index mới và chuyển dữ liệu. Hãy quản lý cấu hình index như một phần của quy trình triển khai, đặc biệt khi ứng dụng chạy nhiều instance.

**IndexOperations** cung cấp lớp API quản trị index trong Spring Data Elasticsearch. Ứng dụng lấy nó từ **ElasticsearchOperations.indexOps(...)**, chọn overload theo lớp tài liệu hoặc tên index tường minh. Sau đó, các phương thức như **exists()**, **createWithMapping()**, **getMapping()**, **getSettings()**, **refresh()** và **delete()** cho phép quản lý vòng đời index. Khi tách rõ thao tác index khỏi thao tác tài liệu, mã nguồn dễ tổ chức và việc triển khai mapping, settings cũng dễ kiểm soát hơn.
