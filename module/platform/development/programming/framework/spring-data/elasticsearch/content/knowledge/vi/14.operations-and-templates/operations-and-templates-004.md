# Lưu, lấy, kiểm tra tồn tại và xóa tài liệu qua Operations

Spring Data Elasticsearch cung cấp **ElasticsearchOperations** để thao tác trực tiếp với tài liệu mà không cần khai báo repository method cho từng hành động. Qua Operations, ứng dụng có thể lưu một tài liệu, lấy tài liệu theo ID, kiểm tra ID có tồn tại hay không và xóa tài liệu theo ID hoặc entity.

Các thao tác này phù hợp khi service cần chủ động điều khiển index đích, xử lý dữ liệu theo luồng nghiệp vụ hoặc kết hợp CRUD với những API tìm kiếm khác. Repository vẫn hữu ích cho các truy vấn có tên phương thức rõ ràng; **ElasticsearchOperations** bổ sung một API linh hoạt hơn ở tầng service.

Bài này sử dụng index **products** và lớp tài liệu **Product**. Ví dụ tập trung vào bốn thao tác cơ bản: **save**, **get**, **exists** và **delete**, đồng thời giải thích cách chọn index bằng **IndexCoordinates**, xử lý tài liệu không tồn tại và cập nhật một phần dữ liệu an toàn.

## 1. ElasticsearchOperations là gì?

**ElasticsearchOperations** là abstraction cấp cao của Spring Data Elasticsearch. Nó cung cấp API để làm việc với tài liệu, truy vấn và một số thao tác liên quan đến index. Spring Boot thường cấu hình implementation và các thành phần kết nối dựa trên dependency cùng cấu hình ứng dụng.

Trong service, inject **ElasticsearchOperations** qua constructor:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Không cần tự tạo client Elasticsearch bằng toán tử **new** trong từng service. Constructor injection giúp các lớp nghiệp vụ dùng chung cấu hình kết nối do Spring quản lý và thuận tiện thay thế dependency khi viết kiểm thử.

Các thao tác CRUD thường dùng:

| Nhu cầu | Phương thức Operations | Ý nghĩa |
|---|---|---|
| Lưu tài liệu | **save(entity)** | Ghi tài liệu theo metadata của entity |
| Lưu vào index chỉ định | **save(entity, index)** | Ghi tài liệu vào index hoặc alias được chỉ định |
| Lấy theo ID | **get(id, entityClass)** | Đọc tài liệu theo định danh |
| Kiểm tra tồn tại | **exists(id, index)** | Kiểm tra tài liệu có ID trong index hay không |
| Xóa theo ID | **delete(id, index)** | Xóa tài liệu có định danh tương ứng |
| Xóa entity | **delete(entity)** | Xóa tài liệu dựa trên ID của entity |

Tên overload và chữ ký chính xác có thể khác theo phiên bản Spring Data Elasticsearch. Các ví dụ bên dưới dùng cách truyền **IndexCoordinates** tường minh ở những thao tác cần xác định index đích.

## 2. Khai báo lớp tài liệu Product

Trước khi thao tác, cần có một lớp Java ánh xạ với tài liệu Elasticsearch. Annotation **@Document** xác định index mặc định, **@Id** đánh dấu định danh và **@Field** mô tả kiểu dữ liệu của các trường.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products", createIndex = false)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    public Product() {
    }

    public Product(String id, String sku, String name,
                   String category, Double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.category = category;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
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

    public Double getPrice() {
        return price;
    }

    public void setPrice(Double price) {
        this.price = price;
    }
}
~~~

Trong ví dụ:

- **@Document(indexName = "products")** liên kết lớp Product với index products.
- **createIndex = false** cho biết ứng dụng không tự tạo index theo annotation khi khởi tạo metadata/repository. Index cần được tạo bởi quy trình quản trị hoặc migration đã định.
- **@Id** ánh xạ thuộc tính **id** vào trường định danh **_id** của Elasticsearch.
- **sku** và **category** là **Keyword**, phù hợp với so khớp chính xác.
- **name** là **Text**, phù hợp với tìm kiếm toàn văn.
- **price** là trường số.

Index và mapping phải tồn tại trước khi ứng dụng ghi tài liệu. Có thể tạo index bằng **IndexOperations**, cấu hình **@Setting**/**@Mapping**, hoặc một quy trình migration riêng. **ElasticsearchOperations.save(...)** không thay thế việc thiết kế mapping.

## 3. Chỉ định index bằng IndexCoordinates

Khi thao tác qua Operations, có thể lấy index từ metadata của lớp tài liệu hoặc truyền index tường minh bằng **IndexCoordinates**.

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");
~~~

Sau đó dùng **PRODUCTS** trong các phương thức Operations:

~~~java
operations.save(product, PRODUCTS);
operations.get(productId, Product.class, PRODUCTS);
operations.exists(productId, PRODUCTS);
operations.delete(productId, PRODUCTS);
~~~

Cách truyền index tường minh hữu ích khi:

- Một entity có thể được lưu ở các index khác nhau.
- Ứng dụng dùng alias thay cho tên index vật lý.
- Index được phân phiên bản như **products-v1**, **products-v2**.
- Dịch vụ cần thao tác trên index archive hoặc index theo tenant.

Nếu entity có **@Document(indexName = "products")**, các overload dựa trên entity metadata có thể tự xác định index. Tuy nhiên, khi cần rõ ràng về đích thao tác, truyền **IndexCoordinates** giúp người đọc mã nhìn thấy index được sử dụng ngay tại lời gọi.

**IndexCoordinates** chỉ mô tả đích thao tác. Nó không tự tạo index, không kiểm tra mapping và không bảo đảm index đã tồn tại.

## 4. Lưu một tài liệu bằng save()

Phương thức **save(...)** chuyển đối tượng Java thành tài liệu JSON rồi gửi thao tác ghi đến Elasticsearch.

Ví dụ lưu một sản phẩm:

~~~java
Product product = new Product(
        "p-1001",
        "KB-1001",
        "Mechanical Keyboard",
        "accessories",
        89.50
);

Product saved = operations.save(product, PRODUCTS);
~~~

Trong ví dụ, **PRODUCTS** là hằng IndexCoordinates đã khai báo ở phần trước. Spring Data sử dụng metadata của Product để chuyển đổi đối tượng thành tài liệu.

Tài liệu tương ứng có thể có dạng:

~~~json
{
  "id": "p-1001",
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

Elasticsearch dùng giá trị **@Id** làm định danh tài liệu. Nếu ứng dụng tự gán ID, hãy bảo đảm ID duy nhất theo quy tắc nghiệp vụ. Nếu để Elasticsearch sinh ID, cần dùng giá trị ID trả về từ thao tác lưu theo hợp đồng API của phiên bản đang dùng.

### save có thể tạo mới hoặc ghi lại tài liệu

**save** ghi tài liệu theo ID:

- Nếu ID chưa có, Elasticsearch tạo tài liệu mới.
- Nếu ID đã có, nội dung tài liệu được ghi lại theo đối tượng được truyền vào.

Ví dụ lưu lại một đối tượng có cùng ID:

~~~java
Product product = new Product(
        "p-1001",
        "KB-1001",
        "Mechanical Keyboard Pro",
        "accessories",
        109.00
);

operations.save(product, PRODUCTS);
~~~

Tài liệu có ID **p-1001** được ghi với nội dung mới. Vì vậy, nếu đối tượng chỉ chứa ID và một trường vừa thay đổi, các trường còn lại có thể bị mất khỏi tài liệu sau khi ghi.

Nếu cần cập nhật một vài trường, hãy đọc tài liệu hiện tại, thay đổi thuộc tính rồi lưu lại, hoặc dùng API cập nhật từng phần.

## 5. Lưu nhiều tài liệu

Operations cũng hỗ trợ lưu một tập entity. Điều này hữu ích khi import dữ liệu hoặc xử lý một lô tài liệu trong service.

~~~java
List<Product> products = List.of(
        new Product("p-1001", "KB-1001",
                "Mechanical Keyboard", "accessories", 89.50),
        new Product("p-1002", "MS-1002",
                "Wireless Mouse", "accessories", 29.00),
        new Product("p-1003", "HD-1003",
                "External SSD", "storage", 119.00)
);

Iterable<Product> savedProducts = operations.save(products, PRODUCTS);
~~~

Phương thức lưu theo lô giúp giảm việc gọi từng thao tác lưu riêng lẻ từ mã ứng dụng. Tuy nhiên, kích thước lô cần phù hợp với tài nguyên và kích thước tài liệu. Không nên gửi một lô quá lớn nếu có thể chia thành các batch vừa phải.

Khi import dữ liệu, cần xác định rõ chiến lược ID. Nếu ID ổn định, chạy lại cùng một batch có thể ghi lại tài liệu cùng ID. Nếu mỗi lần import tạo ID mới, dữ liệu có thể bị nhân bản.

## 6. Lấy tài liệu theo ID bằng get()

Phương thức **get(...)** đọc tài liệu theo định danh và chuyển đổi source JSON thành đối tượng Java.

~~~java
Product product = operations.get(
        "p-1001",
        Product.class,
        PRODUCTS
);
~~~

Nếu tìm thấy tài liệu, kết quả là một đối tượng Product. Nếu không tìm thấy, API get thông thường trả về **null**. Vì vậy, cần kiểm tra null trước khi sử dụng:

~~~java
Product product = operations.get(
        productId,
        Product.class,
        PRODUCTS
);

if (product == null) {
    System.out.println("Không tìm thấy sản phẩm");
} else {
    System.out.println(product.getName());
}
~~~

Đây là điểm khác biệt đáng chú ý so với repository method **findById(...)**, vốn trả về **Optional<Product>**. Khi dùng Operations, caller cần xử lý hợp đồng null của phương thức get.

Có thể đóng gói việc đọc bắt buộc vào service:

~~~java
public Product getRequired(String id) {
    Product product = operations.get(id, Product.class, PRODUCTS);

    if (product == null) {
        throw new ProductNotFoundException(id);
    }

    return product;
}
~~~

Exception nghiệp vụ:

~~~java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String id) {
        super("Không tìm thấy sản phẩm: " + id);
    }
}
~~~

Cách đóng gói này giúp controller và các service khác không phải lặp lại kiểm tra null.

### Đọc theo ID có gì khác tìm kiếm?

Đọc trực tiếp theo ID là thao tác lấy một tài liệu đã biết định danh. Nó không cần xây dựng query trên các trường như name hoặc category.

Tìm kiếm theo điều kiện cần dùng API query, ví dụ **search(...)** hoặc repository method. Không nên gọi **get(...)** nếu chỉ biết SKU hoặc tên sản phẩm mà chưa biết ID.

Elasticsearch hỗ trợ đọc tài liệu theo ID theo cơ chế realtime mặc định của Get API. Tìm kiếm trên inverted index là near real-time và có thể cần chờ refresh sau khi ghi. Do đó, kết quả get theo ID và kết quả search ngay sau khi save có thể có thời điểm hiển thị khác nhau.

## 7. Kiểm tra tài liệu tồn tại bằng exists()

Nếu chỉ cần biết một ID có tài liệu tương ứng hay không, dùng **exists(...)** thay vì tải toàn bộ Product:

~~~java
boolean exists = operations.exists("p-1001", PRODUCTS);

if (exists) {
    System.out.println("Sản phẩm đã tồn tại");
} else {
    System.out.println("Sản phẩm chưa tồn tại");
}
~~~

Phương thức này trả về boolean:

- **true**: tài liệu với ID đã cho tồn tại trong index đích.
- **false**: không tìm thấy tài liệu tương ứng.

Dùng **exists** khi nghiệp vụ chỉ cần câu trả lời có/không. Nếu cần nội dung tài liệu, gọi **get** và kiểm tra null.

### Không nên gọi exists trước mọi lần get

Một cách viết thường gặp là:

~~~java
if (operations.exists(productId, PRODUCTS)) {
    Product product = operations.get(
            productId,
            Product.class,
            PRODUCTS
    );
}
~~~

Đoạn mã này có thể hữu ích nếu ứng dụng chỉ cần kiểm tra tồn tại và sau đó thực hiện một hành động khác. Nhưng nếu mục tiêu là lấy tài liệu, gọi **exists** rồi **get** tạo hai request trong khi **get** đã cho biết tài liệu có tồn tại hay không.

Có thể viết trực tiếp:

~~~java
Product product = operations.get(
        productId,
        Product.class,
        PRODUCTS
);

if (product == null) {
    // Xử lý trường hợp không tìm thấy.
}
~~~

Ngoài ra, kết quả exists có thể trở nên lỗi thời ngay sau khi trả về vì một tiến trình khác có thể xóa tài liệu. Không dùng exists như một cơ chế khóa hoặc bảo đảm rằng tài liệu sẽ còn tồn tại ở thao tác tiếp theo.

## 8. Xóa tài liệu theo ID bằng delete()

Khi đã biết ID, dùng **delete(...)** để xóa tài liệu khỏi index:

~~~java
operations.delete("p-1001", PRODUCTS);
~~~

Thao tác này nhắm đến một tài liệu theo định danh. Ứng dụng không cần tải entity trước khi xóa.

Nếu đang có entity, có thể dùng overload xóa entity:

~~~java
Product product = operations.get(
        "p-1002",
        Product.class,
        PRODUCTS
);

if (product != null) {
    operations.delete(product, PRODUCTS);
}
~~~

Xóa theo ID thường phù hợp hơn khi chỉ cần định danh. Xóa entity hữu ích khi service đã có đối tượng và muốn dùng ID của chính đối tượng đó.

Hành vi với ID không tồn tại và kiểu dữ liệu trả về của delete có thể phụ thuộc overload hoặc phiên bản thư viện. Nếu nghiệp vụ cần thông báo rõ tài liệu có được xóa hay không, hãy xác định hợp đồng từ API đang dùng và xử lý phản hồi tương ứng; không nên giả định mọi lời gọi delete đều chứng minh một tài liệu đã tồn tại trước đó.

### Xóa và kiểm tra tồn tại

Nếu nghiệp vụ yêu cầu phân biệt tài liệu có trước khi xóa:

~~~java
public boolean deleteIfExists(String id) {
    if (!operations.exists(id, PRODUCTS)) {
        return false;
    }

    operations.delete(id, PRODUCTS);
    return true;
}
~~~

Đây là ví dụ minh họa cho hợp đồng nghiệp vụ. Trong môi trường có nhiều tiến trình đồng thời, giữa bước exists và delete, tài liệu có thể bị xóa hoặc thay đổi. Vì vậy, kết quả **true** ở đây chỉ có nghĩa bước kiểm tra đã thấy tài liệu và service đã gửi lệnh xóa; không phải một giao dịch khóa tài liệu xuyên suốt hai request.

Nếu không cần phân biệt trường hợp không tồn tại, gọi delete trực tiếp sẽ đơn giản hơn và tránh request exists bổ sung.

## 9. Cập nhật tài liệu bằng get rồi save

Một quy trình cập nhật đơn giản là:

1. Đọc tài liệu theo ID.
2. Xử lý trường hợp không tồn tại.
3. Thay đổi các thuộc tính cần cập nhật.
4. Gọi save để ghi lại tài liệu.

Ví dụ cập nhật giá:

~~~java
public Product updatePrice(String id, Double newPrice) {
    Product product = operations.get(id, Product.class, PRODUCTS);

    if (product == null) {
        throw new ProductNotFoundException(id);
    }

    product.setPrice(newPrice);

    return operations.save(product, PRODUCTS);
}
~~~

Cách này giữ lại các trường khác vì service thay đổi trên đối tượng đã đọc. Tuy nhiên, nếu một tiến trình khác cập nhật cùng tài liệu giữa bước get và save, lần save sau có thể ghi đè thay đổi của tiến trình kia.

Với dữ liệu có cập nhật đồng thời, cần xem xét cơ chế optimistic concurrency, version hoặc API update từng phần được Spring Data Elasticsearch và Elasticsearch hỗ trợ. Việc lựa chọn phụ thuộc yêu cầu nghiệp vụ và phiên bản client.

### Vì sao không nên save một entity chỉ có một trường?

Giả sử tài liệu hiện tại:

~~~json
{
  "id": "p-1001",
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "category": "accessories",
  "price": 89.5
}
~~~

Nếu tạo đối tượng mới chỉ có ID và giá:

~~~java
Product partial = new Product();
partial.setId("p-1001");
partial.setPrice(79.90);

operations.save(partial, PRODUCTS);
~~~

Lệnh save ghi tài liệu theo đối tượng đã chuyển đổi. Những trường không có trong đối tượng có thể không còn trong source sau khi ghi. Để cập nhật một trường, hãy đọc trước rồi sửa hoặc dùng API update phù hợp.

## 10. Gom CRUD vào một service

Ví dụ sau thể hiện các thao tác lưu, lấy, kiểm tra tồn tại, cập nhật và xóa trong cùng một service:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class ProductOperationsService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductOperationsService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Product save(Product product) {
        return operations.save(product, PRODUCTS);
    }

    public List<Product> saveAll(List<Product> products) {
        List<Product> saved = new ArrayList<>();
        operations.save(products, PRODUCTS).forEach(saved::add);
        return saved;
    }

    public Product findById(String id) {
        return operations.get(id, Product.class, PRODUCTS);
    }

    public boolean existsById(String id) {
        return operations.exists(id, PRODUCTS);
    }

    public Product updatePrice(String id, Double newPrice) {
        Product product = findById(id);

        if (product == null) {
            throw new ProductNotFoundException(id);
        }

        product.setPrice(newPrice);
        return save(product);
    }

    public void deleteById(String id) {
        operations.delete(id, PRODUCTS);
    }

    public void delete(Product product) {
        operations.delete(product, PRODUCTS);
    }
}
~~~

Service này giữ tên index ở một vị trí duy nhất. Các phương thức nghiệp vụ không phải tự xây dựng IndexCoordinates mỗi lần gọi.

Trong dự án thực tế, có thể tách riêng exception, kiểm tra dữ liệu đầu vào và xử lý lỗi từ Elasticsearch. Không nên để controller tự thực hiện trực tiếp mọi thao tác Operations nếu logic nghiệp vụ cần được tái sử dụng.

## 11. Sử dụng Operations qua alias

Ứng dụng có thể làm việc qua alias thay vì tên index vật lý. Ví dụ alias **products-current** trỏ đến index đang hoạt động.

~~~java
private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products-current");
~~~

Các thao tác CRUD không đổi:

~~~java
operations.save(product, PRODUCTS);

Product product = operations.get(
        productId,
        Product.class,
        PRODUCTS
);

boolean exists = operations.exists(productId, PRODUCTS);

operations.delete(productId, PRODUCTS);
~~~

Elasticsearch sẽ định tuyến request thông qua alias. Nếu alias trỏ đến nhiều index, cần xác định rõ write index cho thao tác ghi. Alias đọc có thể trỏ đến nhiều index, nhưng alias ghi phải có quy tắc định tuyến ghi rõ ràng.

Cách dùng alias giúp ứng dụng giữ nguyên tên truy cập khi index vật lý được thay phiên bản. Việc tạo index mới, reindex và chuyển alias thuộc quy trình quản lý index, không phải trách nhiệm của các lệnh save/get/exists/delete.

## 12. Phân biệt Operations và Repository trong CRUD

Cả **ElasticsearchOperations** và **ElasticsearchRepository** đều có thể thực hiện CRUD, nhưng cách tổ chức mã khác nhau.

| Tiêu chí | Repository | ElasticsearchOperations |
|---|---|---|
| Cách sử dụng | Khai báo interface kế thừa repository | Inject API vào service |
| Lưu tài liệu | **save(entity)** | **save(entity, index)** |
| Đọc theo ID | **findById(id)** trả Optional | **get(id, class, index)** thường trả entity hoặc null |
| Kiểm tra tồn tại | **existsById(id)** | **exists(id, index)** |
| Xóa theo ID | **deleteById(id)** | **delete(id, index)** |
| Truy vấn theo thuộc tính | Derived query hoặc @Query | CriteriaQuery, NativeQuery và search API |
| Chọn index | Thường theo metadata entity | Có thể chỉ định IndexCoordinates |
| Metadata tìm kiếm | Tùy kiểu trả về repository | Có thể nhận SearchHits và metadata chi tiết |

Nên dùng repository cho các thao tác CRUD và truy vấn có cấu trúc ổn định, tên phương thức dễ hiểu. Dùng Operations khi service cần kiểm soát index đích, xây dựng query động, kết hợp nhiều thao tác hoặc làm việc với metadata tìm kiếm.

Hai cách tiếp cận có thể cùng tồn tại. Không cần chuyển toàn bộ repository sang Operations chỉ vì một vài trường hợp cần API cấp thấp hơn.

## 13. Lỗi thường gặp khi thao tác CRUD qua Operations

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Save báo lỗi index không tồn tại | Index chưa được tạo hoặc tên index sai | Kiểm tra **@Document**, IndexCoordinates và quy trình tạo index |
| Save lỗi mapping | Kiểu Java không phù hợp mapping thực tế | Đối chiếu mapping, annotation và giá trị gửi đi |
| Get trả về null | ID không tồn tại trong index được chỉ định | Xử lý trường hợp không có tài liệu |
| Exists trả về false | ID không tồn tại hoặc đang kiểm tra nhầm index/alias | Kiểm tra ID và IndexCoordinates |
| Delete không xóa tài liệu mong muốn | Chọn nhầm index hoặc truyền sai ID | Kiểm tra đích thao tác và định danh |
| Save làm mất các trường khác | Ghi lại entity chỉ chứa một phần dữ liệu | Get trước khi sửa rồi save, hoặc dùng update từng phần |
| Get không tìm thấy sau khi lưu | Sai index, ID hoặc metadata chuyển đổi | Kiểm tra ID trả về, IndexCoordinates và mapping |
| Search chưa thấy tài liệu vừa lưu | Index chưa refresh | Hiểu khác biệt giữa get theo ID và tìm kiếm near real-time |
| Lỗi kết nối hoặc xác thực | URI, TLS, thông tin đăng nhập hoặc quyền sai | Kiểm tra cấu hình client và quyền index |
| Thao tác trên alias ghi bị lỗi | Alias nhiều index nhưng chưa có write index | Đặt write index phù hợp |

Khi chẩn đoán, nên xem exception gốc và phản hồi Elasticsearch. Không nên bắt tất cả exception rồi trả về null hoặc false, vì điều đó có thể biến lỗi kết nối thành thông báo sai rằng tài liệu không tồn tại.

## 14. Nguyên tắc sử dụng Operations trong service

Khi triển khai các thao tác CRUD, có thể áp dụng các nguyên tắc sau:

1. Inject **ElasticsearchOperations** qua constructor.
2. Khai báo **IndexCoordinates** rõ ràng khi cần kiểm soát index hoặc alias đích.
3. Dùng **save** để tạo hoặc ghi lại tài liệu theo ID.
4. Dùng **get** khi cần nội dung tài liệu; xử lý kết quả null nếu không tìm thấy.
5. Dùng **exists** khi chỉ cần câu trả lời có/không.
6. Dùng **delete(id, index)** khi đã biết ID và cần xóa một tài liệu.
7. Dùng **delete(entity, index)** khi đã có entity cần xóa.
8. Đọc tài liệu trước khi save nếu chỉ muốn thay đổi một vài thuộc tính.
9. Không xem exists rồi get/delete là một giao dịch nguyên tử; dữ liệu có thể thay đổi giữa các request.
10. Phân biệt lỗi không tồn tại với lỗi kết nối, quyền truy cập hoặc mapping.
11. Đảm bảo index và mapping đã sẵn sàng trước khi ghi.
12. Dùng alias ổn định nếu ứng dụng cần thay phiên bản index mà không thay mã truy cập.

**ElasticsearchOperations** cung cấp một cách trực tiếp để lưu, lấy, kiểm tra và xóa tài liệu trong Spring Data Elasticsearch. **save** ghi tài liệu theo ID; **get** lấy tài liệu và cần xử lý trường hợp null; **exists** trả lời câu hỏi về sự tồn tại; **delete** xóa theo ID hoặc entity. Khi kết hợp các phương thức này với **IndexCoordinates**, service có thể điều khiển rõ index hoặc alias đích và tổ chức các quy tắc CRUD theo nghiệp vụ của ứng dụng.
