# Kiến thức Java, Spring, HTTP, JSON và tìm kiếm cần chuẩn bị

Spring Data Elasticsearch nằm ở giao điểm của Java, Spring Data, giao tiếp HTTP/JSON và tư duy tìm kiếm. Muốn học phần này thuận lợi, bạn nên hiểu dữ liệu được biểu diễn trong ứng dụng Java như thế nào, Spring quản lý các thành phần ra sao, ứng dụng trao đổi dữ liệu qua HTTP/JSON thế nào và một công cụ tìm kiếm xử lý văn bản khác cơ sở dữ liệu quan hệ ở điểm nào.

Bài này hệ thống lại những kiến thức nền cần có trước khi đi sâu vào cấu hình, mapping, repository và truy vấn Elasticsearch. Bạn không cần trở thành chuyên gia của cả năm mảng trước khi bắt đầu. Mục tiêu là nhận diện được vai trò của từng thành phần, đọc được ví dụ cơ bản và hiểu những khái niệm sẽ xuất hiện trong các bài tiếp theo.

## 1. Spring Data Elasticsearch đứng ở đâu trong ứng dụng?

Elasticsearch là một công cụ phân tán dùng để lưu trữ, tìm kiếm và phân tích dữ liệu. Ứng dụng thường gửi tài liệu và truy vấn đến Elasticsearch qua API HTTP. Dữ liệu trao đổi thường có định dạng JSON.

Spring Data Elasticsearch cung cấp lớp tích hợp để ứng dụng Java làm việc với Elasticsearch theo cách quen thuộc của hệ sinh thái Spring Data. Nó hỗ trợ ánh xạ đối tượng Java thành tài liệu, khai báo repository, thực hiện truy vấn và sử dụng các API thao tác cấp cao.

Có thể hình dung luồng xử lý trong một ứng dụng Spring Boot như sau:

~~~mermaid
flowchart TD
    A[HTTP request từ client] --> B[Spring MVC Controller]
    B --> C[Service xử lý nghiệp vụ]
    C --> D[Spring Data Elasticsearch]
    D --> E[Elasticsearch cluster]
    E --> D
    D --> C
    C --> B
    B --> F[HTTP response]
~~~

Mỗi thành phần có trách nhiệm riêng:

- **Controller** tiếp nhận yêu cầu HTTP, đọc tham số và trả kết quả cho client.
- **Service** thực hiện nghiệp vụ, kết hợp dữ liệu và quyết định cách xử lý.
- **Spring Data Elasticsearch** chuyển thao tác ở mức đối tượng Java thành các thao tác phù hợp với Elasticsearch.
- **Elasticsearch** lưu tài liệu, xây dựng cấu trúc phục vụ tìm kiếm và thực thi truy vấn.
- **JSON** là định dạng phổ biến để biểu diễn tài liệu, truy vấn và phản hồi giữa các hệ thống.

Spring Data Elasticsearch không thay thế Elasticsearch server. Thư viện này là lớp tích hợp phía ứng dụng Java; Elasticsearch vẫn là một dịch vụ riêng cần được khởi chạy và kết nối.

## 2. Kiến thức Java cần nắm

### 2.1. Class, object và mô hình dữ liệu

Java biểu diễn dữ liệu bằng class và object. Một class mô tả cấu trúc, còn object là một thể hiện cụ thể của cấu trúc đó.

Ví dụ, một sản phẩm có thể có mã định danh, tên, danh mục và giá:

~~~java
public class Product {
    private String id;
    private String name;
    private String category;
    private BigDecimal price;

    public Product() {
    }

    public Product(String id, String name, String category, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Khi làm việc với Spring Data Elasticsearch, bạn sẽ gặp các class đại diện cho tài liệu được lưu trong một index. Thư viện cần biết trường nào là mã định danh, trường nào là văn bản, ngày tháng hoặc kiểu dữ liệu khác. Các annotation của Spring Data Elasticsearch cung cấp metadata cho việc ánh xạ đó.

Bạn nên hiểu:

- Class, object, field, constructor và phương thức.
- Kiểu dữ liệu cơ bản và kiểu tham chiếu.
- Encapsulation và cách truy cập thuộc tính.
- Interface và cách một class triển khai interface.
- Generic type, vì repository thường khai báo kiểu tài liệu và kiểu ID.
- Annotation, vì Spring dùng annotation để bổ sung metadata cho class và field.

### 2.2. Collection và generic

Kết quả tìm kiếm thường gồm nhiều tài liệu. Vì vậy, bạn cần quen với các collection như List, Set và Map.

Ví dụ:

~~~java
List<Product> products = new ArrayList<>();
Map<String, Product> productsById = new HashMap<>();
~~~

Bạn cũng nên đọc được khai báo generic:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Trong ví dụ trên:

- Product là kiểu đối tượng mà repository thao tác.
- String là kiểu của mã định danh.
- ElasticsearchRepository là interface tổng quát cung cấp các thao tác repository cơ bản.

Kiểu ID phải phù hợp với trường định danh của tài liệu. Nếu ứng dụng dùng UUID hoặc kiểu khác, phần khai báo repository cũng phải phản ánh đúng kiểu đó.

### 2.3. Optional, exception và xử lý kết quả

Một thao tác tìm theo ID có thể không tìm thấy tài liệu. Java thường biểu diễn trường hợp có thể thiếu kết quả bằng Optional:

~~~java
Optional<Product> product = productRepository.findById(id);

product.ifPresent(found -> {
    System.out.println(found.getName());
});
~~~

Bạn cần hiểu sự khác nhau giữa:

- Không có kết quả.
- Có kết quả nhưng một field của tài liệu đang là null.
- Có lỗi khi kết nối hoặc thực thi truy vấn.

Không nên xem mọi trường hợp không có dữ liệu là lỗi hệ thống. Ngược lại, lỗi kết nối, lỗi cấu hình hoặc lỗi truy vấn cần được xử lý và quan sát riêng.

Nắm được exception, try/catch và cách truyền lỗi qua các tầng service/controller sẽ giúp bạn hiểu các tình huống Elasticsearch không sẵn sàng hoặc từ chối một yêu cầu.

### 2.4. Kiểu dữ liệu và chuyển đổi dữ liệu

Các kiểu Java cần nhận diện gồm:

| Java | Ý nghĩa thường gặp trong tài liệu |
|---|---|
| String | Văn bản, mã hoặc giá trị phân loại |
| Integer, Long | Số nguyên |
| Double, BigDecimal | Số thập phân |
| Boolean | Đúng hoặc sai |
| LocalDate, LocalDateTime, Instant | Ngày hoặc thời điểm |
| List, Set | Danh sách giá trị |
| Object hoặc class lồng nhau | Đối tượng lồng trong tài liệu |
| Enum | Một tập giá trị hữu hạn |

Không phải kiểu Java nào cũng được lưu nguyên dạng trong Elasticsearch. Ứng dụng phải chuyển đổi object thành biểu diễn dữ liệu phù hợp, thường là JSON. Kiểu Java và kiểu field trong mapping cần tương thích để tránh lỗi chuyển đổi hoặc kết quả tìm kiếm sai.

Với dữ liệu tiền tệ, hãy chú ý độ chính xác số học. BigDecimal thường phù hợp hơn double ở tầng nghiệp vụ. Khi thiết kế mapping Elasticsearch, cần chọn kiểu số và cách lưu phù hợp với độ chính xác, phạm vi và phép tính mà ứng dụng yêu cầu.

### 2.5. Annotation và serialization

Annotation là metadata gắn trên class, field hoặc phương thức. Spring sử dụng chúng để nhận diện thành phần và hành vi cần áp dụng.

Serialization là quá trình chuyển object thành định dạng có thể truyền hoặc lưu trữ. Deserialization là quá trình chuyển dữ liệu đã nhận về object.

Ví dụ về một tài liệu Spring Data Elasticsearch:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    public ProductDocument() {
    }

    // Constructor, getter và setter được lược bỏ trong ví dụ.
}
~~~

Các annotation trên có ý nghĩa:

- **@Document** đánh dấu class đại diện cho tài liệu trong index có tên products.
- **@Id** đánh dấu trường định danh của tài liệu.
- **@Field** mô tả kiểu field trong Elasticsearch.
- **FieldType.Text** phù hợp với văn bản cần phân tích để tìm kiếm toàn văn.
- **FieldType.Keyword** phù hợp với giá trị cần so khớp chính xác như mã hoặc danh mục.
- **FieldType.Double** biểu diễn giá trị số thập phân theo mapping đã chọn.

Ví dụ chỉ minh họa metadata ánh xạ. Một class dùng trong ứng dụng thực tế còn cần constructor và cách truy cập thuộc tính phù hợp với cơ chế mapping đang sử dụng. Annotation cũng không thay thế việc thiết kế mapping đúng với mục đích truy vấn.

## 3. Kiến thức Spring và Spring Boot cần nắm

### 3.1. IoC và Dependency Injection

Spring quản lý vòng đời của các đối tượng được gọi là bean. Thay vì tự tạo mọi dependency bằng toán tử new ở khắp nơi, class có thể khai báo dependency và để Spring cung cấp đối tượng phù hợp. Cơ chế này thường được gọi là Dependency Injection (DI), nằm trong nguyên lý Inversion of Control (IoC).

Ví dụ, service cần một repository:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Optional<Product> findById(String id) {
        return productRepository.findById(id);
    }
}
~~~

Spring tạo và quản lý các bean phù hợp, sau đó truyền ProductRepository vào constructor của ProductService. Đây là constructor injection.

Bạn nên hiểu:

- Bean là gì và Spring quản lý bean như thế nào.
- Component scanning và các annotation như @Component, @Service, @Repository.
- Constructor injection.
- Vì sao dependency nên được khai báo qua interface khi phù hợp.
- Application context là nơi Spring quản lý các bean và cấu hình.

### 3.2. Spring Boot và auto-configuration

Spring Boot giúp giảm cấu hình thủ công bằng cách tự động cấu hình dựa trên dependency có trong classpath và các thuộc tính cấu hình.

Khi thêm starter Spring Data Elasticsearch phù hợp với phiên bản Spring Boot, ứng dụng có thể được cấu hình để tạo các thành phần kết nối và tích hợp cần thiết. Cấu hình kết nối thường được đặt trong application.yml hoặc application.properties.

Ví dụ cấu hình URI của Elasticsearch:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

Địa chỉ trên chỉ là ví dụ cho môi trường phát triển chạy Elasticsearch tại máy cục bộ. Môi trường khác cần dùng địa chỉ, thông tin xác thực và thiết lập bảo mật tương ứng.

Bạn nên phân biệt ba phần:

1. **Dependency**: thư viện cần có để ứng dụng sử dụng Spring Data Elasticsearch.
2. **Configuration**: địa chỉ và thông tin cần thiết để kết nối đến Elasticsearch.
3. **Elasticsearch service**: máy chủ hoặc cluster thực sự nhận và xử lý yêu cầu.

Chỉ thêm dependency vào dự án không có nghĩa là Elasticsearch server đã được cài đặt hoặc đang chạy.

### 3.3. Spring Data và Repository

Spring Data cung cấp mô hình repository để giảm mã truy cập dữ liệu lặp lại. Thay vì tự viết toàn bộ thao tác tìm, lưu và xóa, ứng dụng có thể kế thừa một repository interface.

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategory(String category);
}
~~~

Spring Data có thể tạo triển khai cho repository dựa trên metadata và quy ước tên phương thức. Phương thức findByCategory là một ví dụ về query derivation: tên phương thức mô tả điều kiện tìm kiếm.

Bạn cần hiểu:

- Repository là lớp trừu tượng truy cập dữ liệu.
- Interface có thể kế thừa interface repository có sẵn.
- Generic type xác định kiểu tài liệu và kiểu ID.
- Query derivation tạo truy vấn từ tên phương thức trong phạm vi các quy tắc được hỗ trợ.
- Truy vấn phức tạp có thể cần annotation truy vấn, ElasticsearchOperations hoặc API phù hợp khác.

Repository không phải nơi chứa toàn bộ nghiệp vụ của ứng dụng. Thông thường, service gọi repository, xử lý kết quả và áp dụng quy tắc nghiệp vụ.

### 3.4. Repository và ElasticsearchOperations

Spring Data Elasticsearch có nhiều cách để thao tác dữ liệu. Hai cách thường gặp là:

- **ElasticsearchRepository**: phù hợp với các thao tác repository quen thuộc và các phương thức truy vấn được khai báo trước.
- **ElasticsearchOperations**: cung cấp API thao tác linh hoạt hơn khi cần điều khiển chi tiết quá trình lưu, tìm, xóa hoặc xây dựng truy vấn.

Không cần học sâu cả hai ngay từ đầu. Trước tiên hãy hiểu repository giải quyết nhu cầu truy cập dữ liệu phổ biến; sau đó tìm hiểu API cấp thấp hơn khi bài toán yêu cầu khả năng kiểm soát truy vấn.

## 4. Kiến thức HTTP và REST API

### 4.1. HTTP là giao thức trao đổi request và response

Ứng dụng Java thường giao tiếp với Elasticsearch qua HTTP. Một HTTP request gồm phương thức, URL, header và có thể có body. Server trả về HTTP response với status code, header và nội dung phản hồi.

Ví dụ một yêu cầu tìm kiếm:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Trong ví dụ:

- POST là phương thức HTTP.
- /products/_search là endpoint tìm kiếm trên index products.
- Content-Type cho biết body được gửi dưới dạng JSON.
- Body mô tả điều kiện tìm kiếm theo field name.

Các phương thức HTTP thường gặp:

| Phương thức | Mục đích thường gặp |
|---|---|
| GET | Đọc tài nguyên hoặc lấy thông tin |
| POST | Gửi dữ liệu hoặc thực hiện thao tác được mô tả trong body |
| PUT | Tạo hoặc thay thế tài nguyên tại một địa chỉ xác định, tùy API |
| PATCH | Cập nhật một phần tài nguyên, nếu API hỗ trợ |
| DELETE | Xóa tài nguyên |

Elasticsearch có các endpoint riêng và quy ước API riêng. Vì vậy, hãy đọc đúng API được gọi thay vì suy luận rằng mọi endpoint đều tuân theo cách thiết kế REST của một ứng dụng CRUD thông thường.

### 4.2. Status code và lỗi HTTP

Một số status code cần nhận diện:

| Status code | Ý nghĩa khái quát |
|---|---|
| 200 OK | Yêu cầu được xử lý thành công |
| 201 Created | Tài nguyên được tạo thành công |
| 400 Bad Request | Yêu cầu hoặc dữ liệu không hợp lệ |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực |
| 403 Forbidden | Không có quyền thực hiện thao tác |
| 404 Not Found | Không tìm thấy tài nguyên hoặc endpoint |
| 409 Conflict | Có xung đột với trạng thái hiện tại |
| 500 Internal Server Error | Lỗi phía server |
| 503 Service Unavailable | Dịch vụ tạm thời không sẵn sàng |

Khi tích hợp Elasticsearch, lỗi có thể xuất phát từ nhiều lớp: ứng dụng gửi request sai, mapping không tương thích, tài khoản không đủ quyền, endpoint không tồn tại hoặc cluster không sẵn sàng.

Đừng chỉ nhìn status code. Hãy đọc response body và log để tìm nguyên nhân cụ thể. Một HTTP 400 có thể chứa thông tin về field hoặc kiểu dữ liệu khiến truy vấn bị từ chối.

### 4.3. URL, path và query parameter

URL xác định tài nguyên hoặc endpoint. Path thường chỉ ra index hay loại thao tác; query parameter bổ sung tùy chọn cho request.

Ví dụ một URL có thể chứa:

~~~text
/products/_search?pretty=true
~~~

Trong đó products là index, _search là endpoint tìm kiếm và pretty=true yêu cầu phản hồi được định dạng dễ đọc trong những API hỗ trợ tùy chọn này.

Bạn nên quen với việc đọc URL, phân biệt path với query parameter và hiểu body của request. Trong các API tìm kiếm, điều kiện phức tạp thường nằm trong JSON body thay vì được mã hóa toàn bộ trên URL.

## 5. Kiến thức JSON cần nắm

### 5.1. Cấu trúc JSON

JSON là định dạng văn bản dùng để biểu diễn dữ liệu có cấu trúc. Một JSON object chứa các cặp key-value; value có thể là chuỗi, số, boolean, null, object hoặc array.

Ví dụ một tài liệu sản phẩm:

~~~json
{
  "id": "P1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORY",
  "price": 49.9,
  "available": true,
  "tags": ["wireless", "keyboard"],
  "brand": {
    "id": "B01",
    "name": "Example"
  },
  "createdAt": "2026-11-13T10:30:00Z"
}
~~~

Các cấu trúc cần nhận diện:

- Object dùng dấu ngoặc nhọn và chứa các cặp key-value.
- Array dùng dấu ngoặc vuông và chứa danh sách value.
- String luôn được đặt trong dấu ngoặc kép.
- Number không đặt trong dấu ngoặc kép.
- Boolean có giá trị true hoặc false.
- null biểu thị một giá trị rỗng được khai báo rõ ràng.

Tên field và kiểu dữ liệu phải nhất quán giữa dữ liệu được gửi lên, mapping và truy vấn.

### 5.2. JSON và object Java

Khi ứng dụng gửi một ProductDocument đến Elasticsearch, object Java được chuyển thành biểu diễn JSON. Khi nhận kết quả, dữ liệu JSON được ánh xạ ngược thành object Java.

Có thể hình dung:

~~~text
ProductDocument (Java)
        |
        | serialization / mapping
        v
JSON document
        |
        | HTTP request
        v
Elasticsearch index
        |
        | search response
        v
JSON response
        |
        | deserialization / mapping
        v
ProductDocument (Java)
~~~

Một số khác biệt cần chú ý:

- Java có nhiều kiểu số cụ thể; JSON chỉ biểu diễn number mà không ghi rõ Integer, Long hay BigDecimal.
- Java có LocalDate, Instant và nhiều kiểu thời gian; JSON thường biểu diễn thời gian bằng chuỗi hoặc số theo quy ước.
- Java có thể có field không được gửi đi; JSON có thể thiếu key hoặc có key với giá trị null.
- Tên field Java có thể được tùy chỉnh khi chuyển thành JSON hoặc khi mapping.

Thiếu field và field có giá trị null là hai trạng thái khác nhau. Khi thiết kế truy vấn và mapping, bạn cần biết dữ liệu thực tế đang được gửi theo cách nào.

### 5.3. Định dạng ngày giờ

Ngày giờ thường được biểu diễn bằng chuỗi theo chuẩn ISO 8601, ví dụ:

~~~json
{
  "createdAt": "2026-11-13T10:30:00Z"
}
~~~

Ký tự Z thể hiện thời điểm theo UTC. Một chuỗi có offset như +07:00 cũng biểu diễn múi giờ rõ ràng.

Khi làm việc với ngày giờ, cần thống nhất:

- Ứng dụng đang dùng LocalDate, LocalDateTime hay Instant.
- Dữ liệu được gửi theo UTC hay kèm offset.
- Mapping Elasticsearch chấp nhận định dạng nào.
- Khi hiển thị cho người dùng, ứng dụng chuyển đổi múi giờ ra sao.

Sai lệch về múi giờ hoặc định dạng có thể khiến truy vấn khoảng thời gian trả về kết quả thiếu hoặc thừa.

## 6. Kiến thức nền về tìm kiếm và Elasticsearch

### 6.1. Index, document và field

Elasticsearch lưu dữ liệu dưới dạng document JSON.

| Khái niệm | Cách hiểu |
|---|---|
| Cluster | Tập hợp một hoặc nhiều node cùng vận hành |
| Node | Một tiến trình Elasticsearch tham gia cluster |
| Index | Không gian lưu trữ và tìm kiếm một nhóm document |
| Document | Một bản ghi JSON có cấu trúc |
| Field | Một thuộc tính trong document |
| Mapping | Quy định cách Elasticsearch hiểu và xử lý các field |
| Shard | Phân vùng dữ liệu của index |
| Replica | Bản sao shard phục vụ tính sẵn sàng và khả năng đọc |

Có thể so sánh ở mức nhập môn:

- Index gần với khái niệm bảng trong cơ sở dữ liệu quan hệ.
- Document gần với một dòng dữ liệu.
- Field gần với một cột.

Đây chỉ là phép so sánh để dễ hình dung. Elasticsearch là hệ thống tìm kiếm tài liệu; cách lưu trữ, truy vấn, quan hệ dữ liệu và cập nhật không giống hoàn toàn cơ sở dữ liệu quan hệ.

Một document có thể chứa object lồng nhau hoặc danh sách giá trị. Thiết kế document thường ưu tiên cách đọc và tìm kiếm mà ứng dụng cần, đôi khi chấp nhận lưu lặp dữ liệu để tránh phải kết hợp nhiều nguồn khi truy vấn.

### 6.2. Mapping và kiểu field

Mapping cho Elasticsearch biết cách diễn giải từng field. Việc chọn kiểu field ảnh hưởng trực tiếp đến cách dữ liệu được lập chỉ mục, tìm kiếm, sắp xếp và tổng hợp.

Một số kiểu thường gặp:

| Kiểu field | Mục đích thường gặp |
|---|---|
| text | Văn bản cần được phân tích để tìm kiếm toàn văn |
| keyword | Chuỗi cần so khớp chính xác, lọc, nhóm hoặc sắp xếp |
| long, integer | Số nguyên |
| float, double | Số thực |
| boolean | Giá trị đúng/sai |
| date | Ngày hoặc thời điểm |
| object | Đối tượng JSON lồng nhau |
| nested | Danh sách object cần giữ quan hệ field trong từng phần tử khi truy vấn |

Hai kiểu text và keyword đặc biệt quan trọng:

- **text** thường được đưa qua analyzer trước khi lập chỉ mục. Nó phù hợp với nội dung như tên sản phẩm, mô tả hoặc bài viết.
- **keyword** được lập chỉ mục như một giá trị không phân tích thành các token từ. Nó phù hợp với mã sản phẩm, trạng thái, danh mục hoặc email khi cần so khớp nguyên giá trị.

Ví dụ, field category có các giá trị ACCESSORY, BOOK và COMPUTER thường phù hợp với keyword. Field description chứa câu văn thường phù hợp với text.

Chọn sai kiểu field có thể làm truy vấn không cho kết quả như mong đợi. Ví dụ, dùng term query trên một field text đã được phân tích có thể không khớp với chuỗi ban đầu vì dữ liệu được lập chỉ mục thành các token.

Mapping nên được thiết kế dựa trên cách dữ liệu được truy vấn. Không nên chọn kiểu field chỉ dựa vào kiểu Java hoặc tên thuộc tính.

### 6.3. Analyzer và quá trình phân tích văn bản

Analyzer là thành phần xử lý văn bản trước khi đưa vào inverted index. Một analyzer thường gồm:

1. Character filter: xử lý chuỗi đầu vào trước khi tách token.
2. Tokenizer: tách văn bản thành các token.
3. Token filter: biến đổi hoặc loại bỏ token, chẳng hạn chuyển chữ thường hoặc loại bỏ stop word theo cấu hình.

Ví dụ, văn bản:

~~~text
"Wireless Keyboard for Office"
~~~

có thể được phân tích thành các token:

~~~text
["wireless", "keyboard", "for", "office"]
~~~

Đây chỉ là ví dụ minh họa. Kết quả thực tế phụ thuộc analyzer được cấu hình, ngôn ngữ và bộ lọc sử dụng.

Analyzer ảnh hưởng đến khả năng tìm kiếm. Với tiếng Anh, các analyzer phổ biến có thể tách từ và chuẩn hóa chữ hoa/thường. Với tiếng Việt, cần quan tâm cách xử lý dấu, từ ghép và ranh giới từ; analyzer mặc định không nhất thiết đáp ứng tốt mọi yêu cầu ngôn ngữ. Thiết kế analyzer cho tiếng Việt cần được kiểm tra bằng dữ liệu và truy vấn thực tế.

### 6.4. Exact search và full-text search

Có hai nhu cầu tìm kiếm cơ bản:

**Exact search** tìm giá trị chính xác, thường dùng cho mã, trạng thái, danh mục hoặc các trường định danh nghiệp vụ.

**Full-text search** tìm nội dung văn bản theo từ hoặc cụm từ, có xét đến quá trình phân tích văn bản và mức độ liên quan.

Elasticsearch có nhiều loại query. Hai query cần phân biệt ở mức nhập môn là term và match:

- **term query** tìm token/giá trị chính xác đã được lập chỉ mục; nó không phân tích chuỗi đầu vào như full-text query.
- **match query** phân tích chuỗi truy vấn theo analyzer phù hợp với field rồi tìm các token tương ứng.

Ví dụ, với field category có kiểu keyword, một truy vấn term phù hợp để tìm đúng danh mục ACCESSORY. Với field name có kiểu text, match phù hợp để tìm các sản phẩm liên quan đến cụm từ wireless keyboard.

Đừng mặc định term luôn có nghĩa là so sánh nguyên chuỗi ban đầu của người dùng. Kết quả phụ thuộc kiểu field và dữ liệu đã được lập chỉ mục như thế nào.

### 6.5. Relevance và score

Trong full-text search, Elasticsearch có thể tính điểm liên quan cho từng kết quả. Điểm này thường được gọi là _score.

Kết quả có score cao hơn thường được xếp trước vì phù hợp hơn với truy vấn theo thuật toán tính điểm đang dùng. Tuy nhiên, score không phải là một thước đo nghiệp vụ tuyệt đối và không nên được hiểu là phần trăm chính xác.

Ví dụ, khi người dùng tìm "wireless keyboard", một tài liệu có cả hai từ trong tên sản phẩm có thể được xếp cao hơn tài liệu chỉ chứa một từ trong phần mô tả. Cách xếp hạng thực tế phụ thuộc analyzer, query, cấu hình similarity và nội dung index.

### 6.6. Filter, sort và pagination

Một trang tìm kiếm thường cần nhiều hơn điều kiện tìm văn bản:

- **Filter** giới hạn tập kết quả theo điều kiện như category, available hoặc khoảng giá.
- **Sort** sắp xếp theo giá, ngày tạo hoặc score.
- **Pagination** chia kết quả thành nhiều trang.
- **Aggregation** tính toán thống kê như số lượng sản phẩm theo danh mục hoặc khoảng giá.

Cần phân biệt filter với điều kiện full-text. Filter thường dùng cho điều kiện đúng/sai và không nhằm tính điểm liên quan. Full-text query thường tham gia vào việc tính score.

Phân trang cơ bản có thể dùng số lượng kết quả và vị trí bắt đầu. Với tập dữ liệu lớn, việc lấy các trang rất sâu có giới hạn về hiệu năng và có thể cần cơ chế phân trang khác như search_after. Phần này sẽ được tìm hiểu khi học các API truy vấn cụ thể.

## 7. Ghép các kiến thức thành một luồng xử lý

Giả sử ứng dụng cần tìm sản phẩm theo tên và lọc theo danh mục.

1. Client gửi HTTP request đến Controller.
2. Controller đọc từ khóa, danh mục và thông tin phân trang.
3. Service kiểm tra tham số và áp dụng quy tắc nghiệp vụ.
4. Repository hoặc ElasticsearchOperations tạo thao tác tìm kiếm.
5. Spring Data Elasticsearch chuyển thông tin đối tượng/truy vấn thành request phù hợp.
6. Elasticsearch phân tích từ khóa, áp dụng mapping, tìm document và xếp hạng kết quả.
7. Elasticsearch trả response JSON.
8. Spring Data ánh xạ kết quả về object Java.
9. Service và Controller trả dữ liệu cho client.

Luồng này kết nối các kiến thức đã học:

| Kiến thức | Vai trò trong luồng |
|---|---|
| Java class và object | Biểu diễn tài liệu và kết quả tìm kiếm |
| Generic và interface | Khai báo repository với kiểu document và ID |
| Annotation | Cung cấp metadata cho mapping và Spring |
| Spring DI | Cung cấp repository cho service |
| HTTP | Truyền request và response giữa ứng dụng với Elasticsearch |
| JSON | Biểu diễn document, query và kết quả |
| Mapping | Quy định cách Elasticsearch hiểu field |
| Analyzer và query | Xác định cách tìm kiếm văn bản |
| Filter, sort, pagination | Điều khiển tập kết quả trả về |

Hiểu luồng này giúp bạn biết nên tìm nguyên nhân ở đâu khi kết quả không đúng: dữ liệu Java, quá trình chuyển đổi JSON, mapping, analyzer, query hay cấu hình kết nối.

## 8. Những nhầm lẫn phổ biến cần tránh

**Cho rằng Elasticsearch là một cơ sở dữ liệu quan hệ.** Elasticsearch hỗ trợ lưu trữ và truy vấn tài liệu, nhưng không nên áp dụng máy móc tư duy join, transaction và chuẩn hóa dữ liệu của hệ quản trị quan hệ.

**Cho rằng mọi chuỗi đều nên dùng text.** Mã, trạng thái và danh mục thường cần keyword để lọc hoặc so khớp chính xác.

**Cho rằng term và match có thể thay thế nhau.** Chúng có cách xử lý đầu vào khác nhau. Cần chọn query theo kiểu field và mục đích tìm kiếm.

**Cho rằng thêm starter là đủ để chạy.** Ứng dụng vẫn cần Elasticsearch server có thể truy cập được và cấu hình kết nối phù hợp.

**Cho rằng tên field Java quyết định toàn bộ mapping.** Tên thuộc tính, annotation, mapping thực tế và JSON được gửi đi cần nhất quán; không nên suy luận kiểu field chỉ từ tên hoặc kiểu Java.

**Cho rằng không có kết quả đồng nghĩa với lỗi.** Một truy vấn hợp lệ có thể trả về danh sách rỗng. Cần phân biệt kết quả rỗng với lỗi HTTP, lỗi mapping hoặc lỗi kết nối.

**Bỏ qua ngôn ngữ của dữ liệu.** Analyzer phù hợp với tiếng Anh có thể không xử lý tiếng Việt theo cách người dùng mong đợi. Hãy kiểm tra bằng từ khóa và dữ liệu thực tế.

**Không kiểm tra dữ liệu JSON thực tế.** Khi truy vấn không hoạt động, hãy xem document đã được index và response thực tế. Đừng chỉ dựa vào class Java mà đoán dữ liệu lưu trữ.

## 9. Lộ trình ôn tập trước khi học các bài tiếp theo

Bạn có thể tự đánh giá mức sẵn sàng bằng các câu hỏi sau:

- Tôi có thể tạo một class Java biểu diễn tài liệu gồm ID, chuỗi, số, boolean và danh sách không?
- Tôi hiểu interface, generic và có thể đọc khai báo repository với hai tham số kiểu không?
- Tôi hiểu constructor injection và vai trò của Controller, Service, Repository trong ứng dụng Spring không?
- Tôi biết Spring Boot đọc cấu hình từ application.yml và phân biệt dependency với dịch vụ Elasticsearch đang chạy không?
- Tôi có thể đọc một HTTP request gồm method, URL, header và JSON body không?
- Tôi có thể đọc JSON object, array, string, number, boolean và null không?
- Tôi phân biệt được index, document, field và mapping không?
- Tôi hiểu vì sao text và keyword phục vụ hai nhu cầu tìm kiếm khác nhau không?
- Tôi phân biệt được exact search với full-text search, term query với match query không?
- Tôi hiểu filter, sort, pagination và relevance score ở mức khái niệm không?

Nếu còn vướng, hãy ôn phần tương ứng trước hoặc song song với các bài thực hành. Bạn không cần thuộc mọi API ngay từ đầu; điều quan trọng là hiểu dữ liệu đi qua những lớp nào và mỗi lớp chịu trách nhiệm cho việc gì.

Khi đã nắm được nền tảng này, bạn có thể tiếp tục học cách kết nối Spring Boot với Elasticsearch, khai báo document và mapping, thao tác repository, xây dựng truy vấn và xử lý kết quả tìm kiếm.
